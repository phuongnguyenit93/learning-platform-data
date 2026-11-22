# STEP_5_NEW — PRIME ONLY: Interview, Case Study, Quiz trên file local

## Mục tiêu và ownership

STEP 5 tạo nội dung đánh giá theo **4 Phase**, ba loại **Quiz / Interview / Case Study**.
Toàn bộ kết quả của STEP 5 chỉ tồn tại trong một module tại
`<MODULE_ROOT>/content/temp/step5/`. **STEP 6 NEW** mới hoàn thiện liên kết
Knowledge, xuất vào `content/{quiz,interview,casestudy}/vi/` và dọn staging;
STEP 5 không import, không publish, không cleanup. Phần QA Knowledge
chuyên sâu của workflow cũ hiện thuộc STEP 6 NEW.

- **Prime**: preflight module, chạy một script khởi tạo, lấy nguyên nội dung
  metadata, điều phối từng Phase/loại, QA/readback, checkpoint khi hợp lệ.
- **Worker**: ghi nội dung của **một loại trong một Phase** và cập nhật
  **duy nhất status của loại mình** sau khi readback QA thành công.
- **Một Worker xử lý toàn bộ group** của một loại ở Phase 4; không tách
  một group thành file/batch/Worker khác, không cần split/merge.
- NORMAL tối đa 3 Worker, SPECIAL theo N được người dùng chỉ định;
  ưu tiên Worker SLEEPING, không có hai writer cùng một loại.

## 0. Preflight — Prime

1. Đọc `GENERAL_AGENT_RULES.md`, toàn bộ `rules/`, tài liệu này và các file
   trong `worker/STEP_5_WORKER_NEW/` trước khi giao. Đối chiếu quyền ghi và
   trạng thái đang chạy; **không mở giao diện IDE để thao tác file**.
2. Xác định chính xác một `<MODULE_ROOT>` bên trong `java-learning/learning-platform-data/module/`;
   `module_activate.json.isModule = true`, có `module-info.json`,
   `MODULE_LANGUAGE.VALUE` chứa `vi`. STEP 4 phải đã viết đủ Knowledge;
   QA/refactor Knowledge chuyên sâu và metadata sẽ tiến hành tại STEP 6 NEW.
3. Prime đọc các giá trị `SERVICE_NAME.VALUE`,
   `SERVICE_NAME_DESCRIBE.VALUE`, `SPECIAL_NOTE.VALUE` từ `module-info.json`.
   **Gửi nguyên nội dung của cả ba cho Worker**; `SPECIAL_NOTE` có thể rỗng
   hoặc nhiều dòng. Không chuyển file metadata cho Worker; Worker không được
   tự đọc `module-info.json`, `master.json` hoặc Sheets.
4. **Prime thiết lập working directory/scope của từng Worker là đúng
   `<MODULE_ROOT>` trước khi giao**. Đây là ràng buộc của môi trường agent,
   không phải một trường tự đoán. Nếu không thể bảo đảm Worker được gắn đúng
   module thì BLOCKER; không để Worker tự tìm module theo SERVICE_NAME.
5. Kiểm tra `content/temp/step5/` hiện tại nếu có, không xóa/reset bất cứ
   file nào đã được Worker viết. Không chạy workflow trực tiếp trong repo khác.

## 1. Prime khởi tạo bằng đúng một Python script

Từ root `java-learning`:

```powershell
python script/module/step5/generate-temp-file.py --module "<MODULE_LOCATION>" --dry-run
python script/module/step5/generate-temp-file.py --module "<MODULE_LOCATION>"
```

Script chỉ **khởi tạo**; không tự tạo nội dung học thuật, không cập nhật status
sau Phase 0, không import, không chạy Worker. Script đọc
`content/knowledge/vi/menu-level-1-slug.yml` và tạo **9 file nền**, cộng
**ba file Related rỗng cho mỗi chương**:

```text
<MODULE_ROOT>/content/temp/step5/
├── raw/
│   ├── quiz.md
│   ├── interview.md
│   └── casestudy.md
├── format/
│   ├── quiz.yml
│   ├── interview.yml
│   └── casestudy.yml
├── status/
│   ├── quiz.yml
│   ├── interview.yml
│   └── casestudy.yml
└── readme-related/
    ├── overview/
    │   ├── quiz.yml
    │   ├── interview.yml
    │   └── casestudy.yml
    └── <chapter-slug>/
        ├── quiz.yml
        ├── interview.yml
        └── casestudy.yml
```

`raw`, `format` và mọi file `readme-related/<slug>/*.yml` ban đầu là
**file rỗng**, chờ Worker. Mỗi file
`status/<type>.yml` mới tạo chứa:

```yaml
status: Phase 0
```

Rerun script **không ghi đè nội dung hay trạng thái**; chỉ tạo file còn
thiếu khi xác minh an toàn. File lạ, đường dẫn symlink, trạng thái không
hợp lệ, danh sách chương/slug bị thay đổi, hoặc file đã tiến Phase nhưng
mất dữ liệu bắt buộc → BLOCKER.
Nếu Worker đã viết nội dung nhưng status chưa cập nhật, Prime cần yêu
cầu đúng Worker xác minh/readback trước khi tiếp tục; không reset để chạy lại.
Script không tự suy trạng thái từ file và không làm thay Worker.

## 2. Bảng công việc và quyền cập nhật

| Phase | Quiz | Interview | Case Study |
| --- | --- | --- | --- |
| 1 | Viết `raw/quiz.md`: MCQ A/B/C/D và đáp án đúng | Viết `raw/interview.md`: mỗi câu hỏi một dòng | Viết `raw/casestudy.md`: mỗi tình huống một dòng |
| 2 | Chuyển thành `format/quiz.yml` có group/schema đầy đủ | `format/interview.yml` có group/schema đầy đủ | `format/casestudy.yml` có group/schema đầy đủ |
| 3 | Điền đủ `answers[].explanation` cho A/B/C/D | Điền `questions[].knowledge` | Điền `cases[].resolve` và `cases[].knowledge` |
| 4 | **Không có** | Điền `questions[].answer` cho mọi group | Điền `cases[].answer` cho mọi group |

Phase 2 **tạo sẵn mọi field thuộc Phase 3/4 dưới dạng chuỗi rỗng** và
`index` số nguyên **0,1,2... trong từng group** cho mỗi câu/case, không
thêm/mất item. Phase 3/4 **chỉ cập nhật các giá trị được giao** trong YAML
tổng của loại mình; không sinh thêm file theo group hay ghi vào `raw`.

### Status — Worker sở hữu

| Loại | Chuỗi trạng thái hợp lệ |
| --- | --- |
| Quiz | `Phase 0 → Phase 1 → Phase 2 → Phase 3` (hoàn thành) |
| Interview / Case Study | `Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4` (hoàn thành) |

**Phase 5 (STEP 6 NEW):** Chỉ **Prime** sau khi QA Related toàn module,
merge vào ba YAML tổng và exact readback PASS mới nâng ba file status lên
`Phase 5`. Quiz chuyển Phase 3→5, Interview/Case Study Phase 4→5.
Worker chương không được sửa ba file status tổng.

- Chỉ Worker của loại/Phase hiện tại được sửa **một** file
  `status/<type>.yml`, **sau** khi hoàn tất output, QA và exact readback.
- Chỉ tăng **một Phase**, không nhảy Phase, không reset, không ghi thêm
  field/trạng thái khác. Nếu thất bại, **giữ nguyên Phase đã PASS** và
  báo BLOCKER; nội dung đang viết dở không được coi là hoàn tất.
- Worker nhận job đã ở Phase đích thì kiểm chứng file trước, nếu đầy đủ
  báo `UNCHANGED_ALREADY_COMPLETE`, không ghi lại.
- Prime QA độc lập file output + status mới trước khi giao Phase tiếp;
  Prime **không sửa status thay Worker**. Prime không chỉ tin báo cáo chat.

## 3. Quy tắc nội dung

### Phase 1 — nội dung thô Markdown

- **Interview:** một câu hỏi phỏng vấn trên mỗi dòng, không answer/knowledge.
- **Case Study:** một tình huống/vấn đề thực tế trên mỗi dòng, không giải pháp
  hoặc code/answer; không nhóm.
- **Quiz:** mỗi câu gồm câu hỏi, đúng bốn dòng `A.`/`B.`/`C.`/`D.`,
  một dòng `Đáp án đúng: X`, giữa hai câu là một dòng trống. Không nhóm,
  không YAML, không explanation. Giữ gate Quiz chống lộ đáp án: distractor
  hợp lý, một đáp án đúng duy nhất, độ dài/độ chi tiết cân đối, không cue
  hình thức, đáp án A/B/C/D phân bố gần đều và không pattern. Prime QA
  100% câu trước khi mở Phase 2.
- Cả ba chỉ dựa vào `SERVICE_NAME`, `SERVICE_NAME_DESCRIBE`,
  `SPECIAL_NOTE` Prime giao; không suy nguồn từ Google Sheets, Java hay
  Knowledge khác khi không được cấp. Không bịa API, kết quả thực thi.

### Phase 2 — cấu trúc YAML canonical

```yaml
# format/interview.yml — ví dụ một item
interviewQuestion:
  - groupID: 1
    groupName: "Nhóm"
    questions:
      - index: 0
        question: "Câu hỏi gốc?"
        knowledge: ""
        answer: ""
        readmeRelated:
          anchorList: []
```

```yaml
# format/casestudy.yml — ví dụ một item
caseStudy:
  - groupID: 1
    groupName: "Nhóm"
    cases:
      - index: 0
        situation: "Tình huống gốc"
        resolve: ""
        knowledge: ""
        answer: ""
        readmeRelated:
          anchorList: []
```

```yaml
# format/quiz.yml — ví dụ một item
quiz:
  - groupID: 1
    groupName: "Nhóm"
    questions:
      - index: 0
        question: "Câu hỏi gốc?"
        readmeRelated:
          anchorList: []
        answers:
          - { id: A, answer: "Lựa chọn A", explanation: "" }
          - { id: B, answer: "Lựa chọn B", explanation: "" }
          - { id: C, answer: "Lựa chọn C", explanation: "" }
          - { id: D, answer: "Lựa chọn D", explanation: "" }
        correctAnswerId: B
```

- `groupID` dương, liên tục 1..N, không trùng; `groupName` có ý nghĩa,
  không rỗng. Mỗi item có `index` số nguyên **0-based và liên tục trong
  group**, luôn khởi đầu từ 0 ở group mới, được tạo Phase 2 và bất biến
  ở Phase 3/4/5. Mỗi item có mặt **đúng một lần**, giữ nguyên nội dung/số
  lượng và thứ tự Phase 1 (kể cả khi được phân group).
- `answer` của **Interview/Case Study là chuỗi Markdown**; Case Study
  không bắt buộc có code. Nếu cần, code fence nằm ngay trong `answer`,
  không sinh field `code` hay `codes`. Quiz vẫn có
  `answers[].answer` là văn bản lựa chọn, **không phải** answer Phase 4.
- Mỗi câu/case có `readmeRelated: {anchorList: []}`; không điền ID,
  không thêm `apiRelated`, `readmeRelated.anchor` hoặc `.file`.
  `anchorList` được STEP 6 NEW xử lý theo Knowledge toàn module,
  lấy proposals từ `readme-related/<chapter-slug>/*.yml`.
- Phase 2 không tự điền các giá trị của Phase 3/4.

### Phase 3 và 4 — hoàn thiện, không thay đổi identity

Phase 3 đọc `format` đã PASS Phase 2 rồi chỉ điền `knowledge` (Interview);
`resolve` và `knowledge` (Case Study); bốn `explanation` (Quiz).
Phase 4 chỉ điền `answer` của Interview và Case Study, **một Worker mỗi
loại đọc/viết toàn bộ group vào đúng một YAML tổng**. Nội dung answer
phải đủ chiều sâu, giải thích rõ, mã nguồn chỉ khi hợp lý; không bịa kết
quả đã compile/run. Không chỉnh `question`, `situation`, group,
`correctAnswerId`, choices, `index`, `readmeRelated`, hoặc field khác ngoài Phase.

## 4. Prime → Worker và tiến trình

Prime pre-bind **đúng module root** trong môi trường Worker. Mọi đường dẫn
file dưới đây là **tương đối so với module root đã xác minh**, nằm ngay
trong file Worker riêng; không cần thêm file metadata hay Sheet range.
Mỗi lượt giao trong Phase 1 **và Phase 2** chỉ có:

```text
SERVICE_NAME=<nội dung thực>
SERVICE_NAME_DESCRIBE=<nội dung thực>
SPECIAL_NOTE=<nguyên văn, có thể rỗng hoặc nhiều dòng>
INSTRUCTIONS=<java-learning>/learning-platform-data/module-generate-agent/worker/STEP_5_WORKER_NEW/<EXACT_WORKER_FILE>.md
```

Phase 3/4 cũng có thể dùng cùng handoff. Phải truyền toàn văn nguyên
vẹn của `SPECIAL_NOTE` với ranh giới rõ nếu nhiều dòng; không coi nội dung
note là quyền ghi mở rộng. Một Worker chỉ đọc/ghi các file được mô tả
trong file hướng dẫn tương ứng. Không giao cùng một loại cho hai Worker
đang ACTIVE.

**Barrier theo Phase:** Prime giao ba job Phase 1, chờ đủ Worker release
và QA cả ba loại rồi mới mở Phase 2; tương tự Phase 2 → 3. Phase 3
hoàn tất Quiz; sau QA ba loại ở Phase 3 mới mở Phase 4 cho Interview,
Case Study (hai job, mỗi loại một Worker). Sau từng đợt, Prime đọc lại
file status và nội dung thực, so identity, enum/trạng thái, không có
field sai Phase, không mất câu/case, không writer đồng thời.

Nếu lỗi giữa WRITE và status: giữ trạng thái cũ, bảo toàn mọi byte đã
viết, giao **đúng owner** readback/reconcile, không tạo lại file hay
tự suy Phase. Nếu đã có dữ liệu tác giả khác, phát hiện conflict thay vì
overwrite. Không tự giảm chất lượng Quiz để đạt tiến độ.

## 5. Hoàn thành STEP 5 NEW

Prime kiểm chứng:

1. `raw/*.md` cả ba loại không rỗng, đúng định dạng Phase 1; Quiz
   qua gate chất lượng toàn bộ.
2. `format/*.yml` cả ba loại parse được, đủ group/item, `index` 0-based
   liên tục trong group, bảo toàn
   nội dung, `readmeRelated.anchorList` vẫn `[]`, không có field ngoài schema.
3. Quiz: mọi `explanation` không rỗng và `status/quiz.yml` =
   `status: Phase 3`. Interview và Case Study: mọi `knowledge`,
   `resolve` (Case Study) và `answer` không rỗng; hai status = `Phase 4`.
4. Worker đều release ownership, không BLOCKER; exact readback của
   các file; dữ liệu tạm thuộc một module duy nhất.

Prime báo `MODULE_LOCATION`, `TOTAL_GROUPS`/`TOTAL_ITEMS` theo loại,
`RAW_QA`, `FORMAT_QA`, `QUIZ_ANSWER_LEAK_QA`, `PHASE_STATUS`,
`SEMANTIC_DIFF_QA`, `READBACK`, `WORKER_OWNERSHIP`, `BLOCKERS`.
Chỉ sau toàn bộ gate PASS, checkpoint
`module-info.json.CURRENT_STEP.VALUE = "5"` nếu quy trình NEW cho phép;
không ghi `master.json`/Sheet J3 theo workflow khác, không ghi lùi.

**Không xuất assessment chính thức, không điền Knowledge IDs, không xóa
`content/temp/step5`, không chạy STEP 6/8, không commit/push hoặc ghi DB.**
STEP 6 NEW đọc format YAML theo schema mới, liên kết Knowledge theo
`(type,groupID,index)`, Prime nâng Phase 5, xuất dữ liệu cuối rồi cleanup
có kiểm chứng. Những downstream phụ thuộc
Case Study Java runnable cần được điều chỉnh khi thiết kế STEP 6/8 mới;
STEP 5 không tự giả định mọi `answer` đều có mã Java.
