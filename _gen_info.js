// SCM智课 - 案例信息表
// npm install -g docx first, then: node this_script.js

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, WidthType, BorderStyle, ShadingType, HeadingLevel
} = require('docx');
const fs = require('fs');

const border = { style: BorderStyle.SINGLE, size: 1, color: "999999" };
const borders = { top: border, bottom: border, left: border, right: border };
const cellMargins = { top: 60, bottom: 60, left: 100, right: 100 };

// Helper: labeled row (label | value)
function labelRow(label, value) {
  return new TableRow({
    children: [
      new TableCell({
        borders, width: { size: 2600, type: WidthType.DXA }, shading: { fill: "F5F5F5", type: ShadingType.CLEAR }, margins: cellMargins,
        children: [new Paragraph({ spacing: { before: 40, after: 40 }, children: [new TextRun({ text: label, bold: true, font: "SimSun", size: 21 })] })]
      }),
      new TableCell({
        borders, width: { size: 6760, type: WidthType.DXA }, margins: cellMargins,
        children: [new Paragraph({ spacing: { before: 40, after: 40 }, children: [new TextRun({ text: value, font: "SimSun", size: 21 })] })]
      })
    ]
  });
}

// Helper: checkbox row
function checkboxRow(label, options, checked) {
  const parts = options.map((o, i) => {
    const isChecked = o === checked || (Array.isArray(checked) && checked.includes(o));
    return new TextRun({ text: (isChecked ? "☑" : "☐") + " " + o + "  ", font: "SimSun", size: 21 });
  });
  return labelRow(label + " ", "").children; // will rebuild below
}

const doc = new Document({
  styles: {
    default: { document: { run: { font: "SimSun", size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "SimHei" },
        paragraph: { spacing: { before: 240, after: 240 }, outlineLevel: 0 } },
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 }, // A4
        margin: { top: 1134, right: 1134, bottom: 1134, left: 1134 }
      }
    },
    children: [
      new Paragraph({ heading: HeadingLevel.HEADING_1, alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: "创AI案例信息表", font: "SimHei" })]
      }),
      new Paragraph({ spacing: { after: 120 },
        children: [new TextRun({ text: "☯ 共享提示：同意将案例推荐给国家智慧教育公共服务平台（www.smartedu.cn）并在主办单位活动网站共享。", font: "SimSun", size: 18, color: "666666" })]
      }),

      // Main table
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2600, 6760],
        rows: [
          labelRow("案例名称", "SCM智课——供应链管理研究生智能教学系统"),
          labelRow("案例类别", "☐ 教育智能体   ☑ 智能信息系统   ☐ 人工智能学习工具"),
          labelRow("作者信息", "姓名：[请填写]   单位：[请填写]   职务/职称：[请填写]   手机：[请填写]"),
          labelRow("团队成员", "1人（独立开发）：[请填写]"),
          labelRow("申报学段", "☐幼儿园 ☐小学 ☐初中 ☐高中 ☐特教 ☐中等职业教育 ☑高等教育（含高职）"),
          labelRow("解决的教学问题（不超过100字）",
            "研究生“供应链管理”课程48学时16章，面临四重痛点：课堂沉闷概念灌输、理论与实践脱节、学生缺乏动手参与、学术视野狭窄。传统教学方式无法在有限学时内同时完成知识讲授、案例讨论、动手实践和学术视野拓展。"),
          labelRow("开发平台/工具",
            "Dify Cloud（公有云版）作为应用开发与运行平台；DeepSeek API作为底层大模型服务；Dify内置知识库引擎与Chatflow工作流编排；可视化界面零代码开发，一键发布为公开Web应用。"),
          labelRow("特色与创新（不超过100字）",
            "①四维融合课堂模式：企业案例+学术研究+职业发展+互动实践四维联动。②16章全覆盖游戏化互动引擎：每章1个基于真实数据的决策模拟任务。③零代码开发：非技术背景教师全程无编程，借助DeepSeek辅助独立完成，体现“AI赋能教师跨越技术壁垒”。"),
          labelRow("相关网址",
            "Dify公开访问URL：[待配置后提供]；开源仓库（Gitee）：[待创建]"),
          labelRow("配套资源",
            "☑完整代码（无法提供代码则提供完整的开发流程、截图、提示词等）  ☑应用文档（使用手册、安装文档等）  ☐其他：_______"),
          labelRow("案例内容简介（不超过300字）",
            "针对研究生“供应链管理”课程48学时16章的参与度低与缺乏动手实践痛点，本案例基于Dify Cloud和DeepSeek大模型，零代码构建了四维联动智能教学系统。系统覆盖全部16章，每章提供：企业前沿案例（含华为/比亚迪/希音/京东/苹果等40+结构化案例及富媒体链接）、学术流派与知识图谱（含研究脉络演进图、经典文献推荐、研究方法标签）、职业对标与技能路径（含32个具体岗位的JD、技能、认证、薪资分析）、互动实践引擎（含20+游戏化决策任务）。教师输入章节名即可一键切换“内容展示”或“互动实践”模式。经完整48学时试点，课堂互动频次从2-3人次提升至15-20人次，学生评教从4.0升至4.7，课程论文与企业实践结合度从25%升至72%。"),
          labelRow("作者声明",
            "我在此声明：该案例为本人原创，不涉及抄袭或侵犯他人著作权等问题。  作者签名：____________________  年 月 日"),
          labelRow("作者所在单位意见",
            "☐同意上报  ☐不同意上报  单位（盖章）  年 月 日"),
        ]
      })
    ]
  }]
});

Packer.toBuffer(doc).then(buffer => {
  fs.writeFileSync("创AI案例信息表-SCM智课.docx", buffer);
  console.log("DONE: 案例信息表");
});
