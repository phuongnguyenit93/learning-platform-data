# Viết, trao đổi và chia lát user story có tiêu chí chấp nhận

Một nhóm phát triển nền tảng học Java nhận yêu cầu từ giảng viên: **“Cần tính năng tiếp tục học để học viên không phải tìm lại bài đang xem.”** Product Owner ghi vào backlog: “Làm module Progress đầy đủ”, gắn nhãn ưu tiên cao và chuyển cho Developers. Người làm backend hiểu đó là API lưu thời gian xem video; người làm giao diện nghĩ phải có dashboard toàn bộ khóa học; QA dự kiến kiểm tra thanh tiến độ, còn giảng viên mong người học mở lại đúng đoạn video sau khi đăng nhập từ thiết bị khác.

Hai tuần sau, cả nhóm đã có nhiều mã nguồn nhưng chưa có chức năng đầu cuối sử dụng được. Mỗi người đã giải quyết một phần của một **giả định khác nhau**.

Làm Agile không phải viết thật nhiều “As a…, I want…, so that…” rồi chuyển chúng qua bảng công việc. Kỹ năng quan trọng là **chuyển nhu cầu thành một cuộc trao đổi có thể ra quyết định, chia thành những phần giá trị đủ nhỏ và xác định cách kiểm chứng kết quả**.

Bài **“Viết, trao đổi và chia lát user story có tiêu chí chấp nhận”** nằm trong chương **Thực hành tổng hợp** thuộc module **AGILE_DEVELOPMENT**. Module tập trung vào giá trị, nguyên tắc Agile; phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc. Trong bài này, những kiến thức đó được nối thành một **quy trình thực hành trọn vẹn**, thay vì trình bày user story như một mẫu câu độc lập.

**Tình huống xuyên suốt:** một nền tảng học Java cần giúp học viên quay lại đúng phần bài đang học. Chúng ta sẽ mô phỏng cuộc trao đổi giữa học viên, Product Owner, Developers, QA và giảng viên; sau đó tạo story map, các lát ưu tiên, acceptance criteria, Gherkin scenarios, kế hoạch kiểm chứng, phản hồi và quyết định điều chỉnh backlog.

## Kết quả học tập và sản phẩm thực hành

Sau khi học, bạn có thể:

1. Phân biệt **user story, epic, task kỹ thuật, acceptance criteria, Definition of Done, Product Goal và Sprint Goal**.
2. Viết user story mô tả **người hưởng lợi, năng lực cần có và giá trị/kết quả**, không chỉ công nghệ phải xây.
3. Áp dụng **3C: Card – Conversation – Confirmation**, không biến story card thành hợp đồng đầy đủ.
4. Đặt câu hỏi khám phá nhu cầu, quan sát quy trình hiện tại và phân biệt **fact, assumption, open question, decision**.
5. Dùng **INVEST** để đánh giá khả năng chia lát mà không áp dụng từng chữ cái như điều kiện máy móc.
6. Tạo **story map** từ hành trình người dùng, xác định đường đi tối thiểu có giá trị.
7. Chia một yêu cầu lớn theo **biến thể hành vi, quy tắc, dữ liệu, vai trò, trường hợp biên và mức độ tự động hóa**, nhưng giữ lát **end-to-end**.
8. Viết acceptance criteria **rõ, kiểm chứng được, có success/error/boundary/security phù hợp**, phân biệt với chi tiết triển khai.
9. Dùng **Given–When–Then** và example mapping để tạo hiểu biết chung, hỗ trợ kiểm thử và TDD/BDD khi thích hợp.
10. Liên kết stories với **Definition of Done, kiểm thử tích hợp, phân quyền, Sprint Goal, Product Backlog và release**.
11. Thực hiện refinement, ước lượng/forecast và ưu tiên theo rủi ro/giá trị mà không coi story points là mục tiêu.
12. Sử dụng phản hồi người dùng và flow metrics để đánh giá một lát đã giao có thực sự hữu ích không.
13. Tổ chức một buổi workshop, hoàn thành các mẫu biểu, bài tập và tự đánh giá chất lượng story.

**Đầu ra tối thiểu của workshop:** một Product Goal có ngữ cảnh; một story card lớn ban đầu; bản ghi các câu hỏi/giả định/quyết định; story map; ít nhất ba lát dọc có thứ tự; một story đủ điều kiện refinement với acceptance criteria kiểm thử được; và kế hoạch nhận phản hồi sau bàn giao.

## 1. Từ yêu cầu tính năng sang kết quả người dùng

Yêu cầu “xây module Progress” mô tả **một giải pháp**, chưa mô tả đầy đủ điều gì sẽ cải thiện cho người học.

Hãy xem các câu khác nhau:

| Câu | Loại thông tin | Có giúp quyết định ưu tiên và kiểm chứng? |
| --- | --- | --- |
| “Tạo bảng PROGRESS và REST API.” | Task/đề xuất kỹ thuật. | Chưa rõ ai được hưởng lợi và hành vi cuối. |
| “Làm dashboard theo dõi học tập đầy đủ.” | Yêu cầu tính năng lớn, phạm vi mơ hồ. | Khó biết phần nào là giá trị tối thiểu. |
| “Học viên thường phải tìm lại bài sau khi rời trình duyệt.” | Quan sát vấn đề. | Hữu ích để khám phá nhu cầu. |
| “Học viên quay lại đúng bài và vị trí đã dừng mà không phải tìm thủ công.” | Kết quả mong muốn. | Có thể chia thành hành vi và kiểm chứng. |
| “80% học viên thử hoàn thành tác vụ mở lại bài đúng chỗ.” | Ví dụ tiêu chí đo trải nghiệm, cần định nghĩa mẫu và phương pháp. | Hữu ích cho thử nghiệm, chưa tự là acceptance criterion của mọi PBI. |

Mỗi câu có thể có vai trò trong phát triển. Vấn đề phát sinh khi **task kỹ thuật được báo cáo như giá trị người dùng** hoặc **chỉ số giả định được coi là điều bắt buộc đã xác minh**.

### 1.1. Câu hỏi xuất phát

> “Ai đang gặp khó khăn gì, trong tình huống nào, và làm sao biết phần mềm đã giúp họ?”

Đó là câu hỏi nên dẫn dắt việc viết user story. Không nhất thiết phải có câu trả lời hoàn hảo trước khi bắt đầu; những chỗ chưa chắc chắn cần được ghi thành **giả định hoặc câu hỏi cần kiểm chứng**.

### 1.2. Một Product Goal minh họa

> **Product Goal:** Giúp học viên đang theo học Java quay lại hoạt động học dở dễ dàng, với dữ liệu tiến độ chính xác và chỉ hiển thị cho người có quyền.

Product Goal này không bắt buộc tất cả tính năng dashboard, huy hiệu, AI gợi ý và đồng bộ offline đều phải có từ lát đầu. Nó tạo **định hướng** để nhóm cùng chọn phần giá trị tiếp theo.

### 1.3. Chỉ số giá trị phải được kiểm chứng riêng

Trong một thử nghiệm usability, có thể đo học viên có mở lại được bài trong điều kiện được định nghĩa, thời gian hoàn thành tác vụ, số lần phải tìm thủ công và cảm nhận của họ. Những chỉ số này giúp PO đánh giá **outcome**; không nên nhầm với việc test một API trả HTTP 200.

## 2. Các khái niệm dễ bị trộn lẫn

| Khái niệm | Mục đích chính | Ví dụ “Học tiếp” |
| --- | --- | --- |
| **Product Goal** | Mục tiêu lâu dài cho sản phẩm. | Giúp học viên tiếp tục việc học thuận tiện, tin cậy. |
| **Epic/nhóm story** | Gom phạm vi lớn cần chia nhỏ; không phải thành phần bắt buộc của Scrum Guide. | Toàn bộ trải nghiệm “Học tiếp” trên nhiều loại nội dung. |
| **User story** | Mảnh nhu cầu làm chất xúc tác trao đổi và bàn giao giá trị. | Học viên mở lại một video từ vị trí đã lưu. |
| **Acceptance criteria (AC)** | Điều kiện để kiểm tra hành vi riêng của story. | Video mở đúng vị trí; xử lý chưa có dữ liệu; từ chối sai quyền. |
| **Task** | Hoạt động thực hiện giải pháp. | Thêm migration, endpoint, UI component, unit tests. |
| **Definition of Done (DoD)** | Chuẩn chất lượng chung để Increment được coi là hoàn tất. | Tích hợp, kiểm thử, quyền, hồi quy và điều kiện chất lượng áp dụng. |
| **Increment** | Bước tiến có thể sử dụng của sản phẩm, đáp ứng DoD trong Scrum. | Một luồng “Học tiếp” hoạt động với nội dung trong phạm vi. |
| **Sprint Goal** | Mục đích chung của Sprint trong Scrum. | Học viên có thể trở lại video từ vị trí đã lưu qua đăng nhập. |
| **Release** | Mở khả năng cho một nhóm người dùng cụ thể khi đủ điều kiện. | Mở cho cohort học viên thử nghiệm có quyền. |

**Story không đồng nghĩa task**, và **acceptance criteria không thay DoD**. Một story có thể có vài task kỹ thuật, nhưng giá trị của story cần thể hiện ở hành vi và kết quả tích hợp.

### Ví dụ phân biệt

- “Tạo index cho bảng tiến độ” là task kỹ thuật.
- “Là học viên, tôi muốn tiếp tục xem một video từ vị trí đã lưu để không mất thời gian tìm lại” là user story ứng viên.
- “Khi học viên khác cố đọc tiến độ này, hệ thống từ chối” là acceptance criterion hoặc kịch bản kiểm thử liên quan.
- “Tính năng đạt chuẩn kiểm thử quyền, tích hợp và hồi quy của sản phẩm” là phần của DoD chung khi áp dụng.

Không cần ép mọi công việc cơ sở hạ tầng vào câu “Là người dùng…”. Công việc bảo mật, migration, vận hành và giảm nợ kỹ thuật có thể được thể hiện rõ trong Product Backlog và giải thích **giá trị/rủi ro** nó giải quyết.

## 3. 3C: Card – Conversation – Confirmation

3C là một cách hiểu rất hữu ích về user story:

1. **Card:** ghi ngắn nhu cầu hoặc khả năng cần có, làm lời nhắc trao đổi.
2. **Conversation:** trao đổi giữa người hiểu nhu cầu và những người xây/kiểm tra, làm rõ quy tắc, ví dụ, giới hạn, rủi ro và lựa chọn.
3. **Confirmation:** xác nhận các ví dụ và điều kiện để kiểm tra story đã đáp ứng nhu cầu trong phạm vi thống nhất hay chưa.

~~~mermaid
flowchart LR
    A["Card: ai, muốn gì, vì sao"] --> B["Conversation: ví dụ, quy tắc, câu hỏi, rủi ro"]
    B --> C["Confirmation: acceptance criteria + kiểm chứng"]
    C --> D["Increment đạt DoD"]
    D --> E["Feedback người dùng và sản phẩm"]
    E --> A
~~~

**3C không phải ba tài liệu cần ký tuần tự.** Nhóm có thể quay lại Conversation sau khi viết criteria và khám phá thêm trường hợp mới. Giá trị nằm ở **hiểu biết chung và khả năng kiểm chứng**, không phải đầy đủ ô trống.

### 3.1. Một card quá dài có thể che nhu cầu trao đổi

Card chứa 40 dòng quy tắc, 12 ảnh giao diện và 25 trường bắt buộc chưa chắc rõ hơn một card ngắn cùng vài examples tốt. Đặc biệt với quy tắc chưa thống nhất, viết thật dài có thể chỉ đóng băng một giả định.

### 3.2. Một card quá ngắn cũng không đủ

“Làm Học tiếp” có thể là tên một epic/ý tưởng, nhưng không đủ để Developers độc lập chọn điều kiện hoàn tất. Hãy **nêu ai, hành vi, giá trị** và liên kết các quyết định/acceptance examples khi đã được làm rõ.

## 4. Trước khi viết: hiểu vai trò và hành trình người dùng

Một user story có ý nghĩa khi xuất phát từ người dùng hoặc bên hưởng lợi thực tế. Có thể có nhiều vai trò:

| Vai trò | Nhu cầu có thể khác nhau |
| --- | --- |
| **Học viên** | Tìm lại bài dở, không mất tiến độ, biết khi nào đã lưu. |
| **Giảng viên** | Biết học viên đã tới đâu để hỗ trợ phù hợp, đúng quyền. |
| **Người hỗ trợ học viên** | Chẩn đoán vì sao người học không tiếp tục được. |
| **Quản trị viên được phép** | Quản lý quyền hoặc cấu hình nội dung theo thẩm quyền. |
| **Đội vận hành** | Phát hiện lỗi ghi tiến độ, khôi phục an toàn. |

Đừng tạo một vai “người dùng” chung cho tất cả nếu các nhóm có **quyền và mục tiêu mâu thuẫn**. Ví dụ học viên có thể xem tiến độ của mình, nhưng điều đó không tự cấp quyền cho giảng viên xem toàn bộ thông tin riêng tư.

### 4.1. Hành trình hiện tại minh họa

1. Học viên mở một khóa Java.
2. Chọn bài và xem video.
3. Dừng giữa chừng hoặc mất kết nối.
4. Ngày hôm sau đăng nhập lại.
5. Tìm khóa, chương, bài.
6. Dò video tới gần vị trí đã xem.
7. Tiếp tục học.

Bất tiện chính nằm ở **bước 4–6**. Nhóm nên hiểu trường hợp nào phổ biến và tốn công nhất trước khi tự kết luận cần một dashboard phức tạp.

### 4.2. Thu thập bằng chứng, không chỉ suy đoán persona

Có thể quan sát nhiệm vụ thử, trao đổi với học viên và đội hỗ trợ, xem khiếu nại phù hợp hoặc telemetry đã được phép thu. Cần ghi rõ:

- **Fact:** “Trong ba buổi quan sát, có hai người mất thời gian tìm lại video.”
- **Assumption:** “Hầu hết học viên cần khôi phục tới từng giây.”
- **Open question:** “Nếu video đã được chỉnh sửa, vị trí cũ phải xử lý ra sao?”
- **Decision:** “Lát đầu chỉ hỗ trợ video không thay đổi phiên bản; nội dung đã sửa có chính sách riêng cần làm rõ.”

Mẫu ba người **không đại diện toàn bộ người dùng**. Nó có thể gợi ý vấn đề cần khám phá, không tự chứng minh tỷ lệ cho tất cả.

## 5. Viết story card: ai – muốn gì – để làm gì

Cấu trúc phổ biến:

> **Là [vai trò], tôi muốn [năng lực/hành vi], để [giá trị/kết quả].**

Ví dụ:

> **Là học viên đang học Java, tôi muốn mở lại video từ vị trí đã lưu để tiếp tục học mà không phải dò tìm thủ công.**

Mẫu câu giúp nhóm suy nghĩ về **giá trị**, nhưng không phải yêu cầu kỹ thuật bắt buộc. Một câu viết tự nhiên ngắn vẫn được nếu thể hiện nhu cầu rõ và kích hoạt Conversation.

### 5.1. Từ card yếu tới card tốt hơn

| Card yếu | Vấn đề | Cải thiện |
| --- | --- | --- |
| “Làm bảng progress.” | Chỉ giải pháp kỹ thuật. | Học viên mở lại video dở theo quyền. |
| “Là người dùng, tôi muốn app nhanh.” | Vai trò, hành vi và mục đích quá mơ hồ. | Học viên quay lại bài đã học mà không qua nhiều bước tìm kiếm. |
| “Là API, tôi muốn lưu timestamp.” | Gắn người dùng giả cho implementation. | Giữ task kỹ thuật dưới story tạo hành vi cho học viên. |
| “Là học viên, tôi muốn AI, dashboard, lịch sử, huy hiệu và offline.” | Nhiều outcome/rủi ro trong một card. | Tách theo hành vi và thứ tự học hỏi. |
| “Là học viên, tôi muốn được lưu tiến độ để hệ thống hiện đại.” | Lợi ích không liên quan nhu cầu thật. | Nêu tiết kiệm thời gian và liên tục học. |
| “Là học viên, tôi muốn xem tiến độ bạn khác.” | Có thể vi phạm quyền. | Làm rõ người có quyền, mục tiêu và chính sách trước. |

### 5.2. Một story nên có thông tin gì?

Card tối thiểu có **tên dễ hiểu, vai trò/năng lực/giá trị, link mục tiêu, trạng thái và người trao đổi**. Khi chuẩn bị thực hiện, thêm **acceptance criteria, những câu hỏi còn mở, phụ thuộc, giả định và bằng chứng** phù hợp.

Không cần đưa toàn bộ thiết kế database vào card nếu có quyết định kỹ thuật riêng được liên kết. Đừng để việc điền mẫu biến thành mục tiêu độc lập.

## 6. Viết story không đồng nghĩa hiểu story

Một card có thể có đúng ba vế nhưng các bên vẫn hiểu khác nhau:

> “Là học viên, tôi muốn lưu tiến độ học, để tiếp tục dễ dàng.”

Người A nghĩ chỉ lưu khi bấm nút, người B nghĩ tự lưu mỗi giây, người C nghĩ giữa nhiều thiết bị, người D nghĩ cả video, bài đọc và quiz. Vì vậy cần Conversation.

### 6.1. Những trục cần hỏi

- **Ai:** học viên đã đăng nhập hay khách? quyền của giảng viên?
- **Khi nào:** khi nhấn Pause, rời trang, mỗi vài giây, kết thúc video?
- **Ở đâu:** một thiết bị, nhiều thiết bị, offline/online?
- **Dữ liệu gì:** bài đang học, thời điểm video, phần đã hoàn thành?
- **Thành công:** quay lại đúng bài hay đúng từng giây?
- **Lỗi:** mạng đứt, API timeout, lưu lặp, phiên đăng nhập hết hạn?
- **Biên:** chưa từng học, video đã xóa, vị trí lưu vượt thời lượng?
- **Giới hạn:** loại nội dung nào ở lát đầu? người nào được phép?
- **Quyết định:** ai có thẩm quyền chọn rule nghiệp vụ, ai triển khai?
- **Phản hồi:** hành vi nào chứng minh người học được giúp?

### 6.2. Không tự chọn đáp án cho mọi câu hỏi

Ví dụ “sau khi bấm Pause phải lưu ngay?” là quyết định sản phẩm/nghiệp vụ cần PO trao đổi với người liên quan; Developers có thể đưa các lựa chọn, độ trễ và rủi ro kỹ thuật. **Không tự biến một giả định thành acceptance criterion đã được chốt**.

## 7. Mô phỏng một cuộc Conversation có mục tiêu

Một buổi refinement có thể có Product Owner, một hoặc nhiều Developers, QA và khi cần giảng viên/học viên. Không cần mọi bên tham gia toàn thời gian; cần đúng người giải được các câu hỏi quan trọng.

### 7.1. Kịch bản trao đổi

**PO:** “Học viên không phải tìm lại video khi quay lại học.”

**Developer:** “Giá trị quan trọng nhất là quay lại đúng bài hay đúng giây đã dừng?”

**PO:** “Trước mắt đúng bài và gần đúng vị trí; tôi cần xác minh mức chính xác với học viên.”

**QA:** “Nếu chưa có vị trí lưu thì sao? Nếu vị trí vượt thời lượng vì video được chỉnh sửa?”

**PO:** “Chưa có vị trí thì bắt đầu từ đầu. Video bị chỉnh sửa cần một quy tắc riêng; đừng đoán.”

**Developer:** “Có cần hỗ trợ khách chưa đăng nhập và đa thiết bị ở lát đầu không?”

**PO:** “Lát đầu là học viên đã đăng nhập, video của một khóa có quyền. Việc đa thiết bị là ứng viên ưu tiên cao nhưng phải kiểm tra yêu cầu và chi phí.”

**QA:** “Nếu lưu thất bại mà UI vẫn báo ‘Đã lưu’ thì không đúng. Chúng ta cần xác định trạng thái lỗi.”

**PO:** “Đúng, không được báo lưu thành công sai. Hãy làm rõ thông điệp ngắn với UX.”

**Developer:** “Giới hạn quyền? Có thể đọc tiến độ bằng một learnerId bất kỳ không?”

**PO:** “Không. Mỗi người chỉ đọc và sửa tiến độ được phép của mình; thẩm quyền giảng viên là chuyện khác.”

### 7.2. Đầu ra của cuộc trao đổi

| Loại | Nội dung |
| --- | --- |
| **Rule đã rõ** | Chưa có tiến độ: mở video từ đầu. |
| **Rule đã rõ** | Không báo “Đã lưu” nếu chưa xác nhận ghi thành công. |
| **Giới hạn lát đầu** | Học viên đăng nhập; video được phép; chưa xử lý mọi loại nội dung. |
| **Guardrail** | Không đọc/sửa tiến độ học viên khác trái quyền. |
| **Câu hỏi còn mở** | Vị trí lưu gần đúng đến mức nào? xử lý video sửa đổi ra sao? |
| **Giả định cần thử** | Khôi phục vị trí là giá trị đáng ưu tiên hơn dashboard. |
| **Quyết định công việc** | Chia lát đầu, lên mẫu kiểm chứng và làm rõ những câu hỏi ảnh hưởng DoD trước khi chọn PBI. |

Cuộc trao đổi tốt **giảm bất định, ghi người cần ra quyết định và cho thấy điều chưa biết**, chứ không cố gắng ép mọi thứ “đã rõ” để qua cổng refinement.

## 8. Example mapping: Rule, Example, Question

**Example mapping** là kỹ thuật đặt các ví dụ cụ thể cạnh quy tắc và câu hỏi để phát hiện cách hiểu khác nhau.

Với story “Học tiếp”:

| Rule | Ví dụ xác nhận hành vi | Question hoặc quyết định cần làm rõ |
| --- | --- | --- |
| Người có quyền được khôi phục vị trí đã lưu. | Đã lưu ở 05:20, mở lại video được tiếp tục theo vị trí đó. | Sai số cho phép là bao nhiêu? |
| Chưa có tiến độ thì bắt đầu từ đầu. | Video mới chưa lưu → 00:00. | Có cần hiển thị thông báo “chưa có tiến độ”? |
| Không báo thành công giả khi ghi lỗi. | API timeout → UI không hiện “Đã lưu” như thể ghi thành công. | Nên hiện “Đang lưu”, “Thử lại” hay thông báo khác? |
| Không lộ dữ liệu của người khác. | Tài khoản A yêu cầu tiến độ của B → bị từ chối. | Quyền giảng viên/giám hộ được quản lý thế nào? |
| Vị trí không vượt thời lượng. | Video dài 12 phút nhưng dữ liệu lưu 20 phút. | Reset về 00:00 hay giới hạn ở điểm cuối? |
| Lát đầu không hỗ trợ offline. | Mất mạng: không khẳng định đã đồng bộ trên server. | Có lưu tạm cục bộ để sau này đồng bộ không? |

### 8.1. Quy tắc cần nhất quán, ví dụ cần phân biệt hành vi

Không cần 20 ví dụ đều kiểm cùng happy path. Hãy chọn **phân vùng hành vi khác nhau**: lần đầu, quay lại, hết quyền, lỗi mạng, dữ liệu biên, hai lần ghi liên tiếp.

### 8.2. Một câu hỏi mở quan trọng có thể cản “Ready”

Nếu chưa biết xử lý video bị thay phiên bản ra sao nhưng lát đầu **không đụng loại video đó**, nhóm có thể cắt phạm vi rõ và làm tiếp. Ngược lại, nếu quyền đọc tiến độ chưa xác định, không nên đưa vào Sprint rồi hy vọng sẽ biết khi release.

### 8.3. Câu trả lời phải có nơi lưu

Khi đã quyết, cập nhật **acceptance criteria, nguồn quy tắc và test liên quan**. Không để decision chỉ trong chat của người đang vắng mặt.

## 9. INVEST: một bộ câu hỏi để đánh giá story

INVEST thường được hiểu là:

| Chữ | Nguyên tắc | Câu hỏi khi review story |
| --- | --- | --- |
| **I — Independent** | Tương đối độc lập. | Có thể hoàn tất lát này mà không phải chờ cả epic? |
| **N — Negotiable** | Có thể thương lượng giải pháp và phạm vi. | Card mô tả nhu cầu hay khóa cứng một phương án? |
| **V — Valuable** | Có giá trị cho người dùng/bên hưởng lợi. | Ai nhận được hành vi hay rủi ro nào được giảm? |
| **E — Estimable** | Đủ hiểu để nhóm ước lượng/forecast khi cần. | Còn câu hỏi lớn chưa được xử lý? |
| **S — Small** | Đủ nhỏ để hoàn thành và nhận phản hồi sớm. | Có nhiều biến thể hoặc phụ thuộc cần tách không? |
| **T — Testable** | Có thể kiểm chứng. | Có examples cho success/error và tiêu chí rõ? |

### 9.1. INVEST là hướng dẫn, không phải luật cứng

**Independent** không có nghĩa mỗi story bắt buộc không có bất kỳ phụ thuộc nào; phần mềm có kiến trúc và dữ liệu chung. Cần làm **phụ thuộc rõ và giảm rủi ro chờ**, không làm giả sự độc lập.

**Estimable** không buộc mọi story phải có story points. Một nhóm Kanban có thể dùng throughput/cycle time hoặc cách dự báo khác. Điều cốt lõi là đủ hiểu để **ra quyết định làm hay tiếp tục chia**.

**Negotiable** không nghĩa các nghĩa vụ bảo mật có thể thương lượng bỏ. Có thể thương lượng **cách triển khai hoặc giảm phạm vi**, nhưng không hạ những điều kiện an toàn bắt buộc.

### 9.2. Đánh giá card lớn ban đầu

Card “Là học viên, tôi muốn đồng bộ mọi tiến độ trên mọi thiết bị, mọi loại nội dung, có offline và dashboard để học tốt hơn” có thể có Value nhưng thường **chưa Small, chưa Estimable, chưa Testable**. Nên dùng story mapping và ví dụ để chia trước.

## 10. User story mapping: nhìn hành trình thay vì một danh sách ticket rời

**Story mapping** đặt các hoạt động và bước của người dùng theo hành trình, rồi đặt các biến thể/lát công việc phía dưới để nhóm thấy trải nghiệm đầu cuối.

Hành trình ví dụ:

1. **Vào khóa học.**
2. **Chọn bài.**
3. **Xem nội dung.**
4. **Dừng hoặc rời.**
5. **Quay lại.**
6. **Tiếp tục.**

Trong mỗi hoạt động có thể có biến thể:

| Hoạt động | Hành vi cơ bản | Biến thể/ý tưởng về sau |
| --- | --- | --- |
| Vào khóa | Đăng nhập, có quyền mở khóa. | Mời học viên, quyền nhiều tổ chức. |
| Chọn bài | Chọn bài từ danh sách khóa. | Tìm kiếm toàn bộ hệ thống. |
| Xem video | Phát video trong một khóa. | Chất lượng mạng thích ứng, phụ đề nhiều ngôn ngữ. |
| Dừng | Lưu một vị trí hợp lệ. | Autosave thông minh, offline local cache. |
| Quay lại | Mở lại từ khóa/bài đã học. | Cross-device conflict resolution. |
| Tiếp tục | Bắt đầu từ vị trí đã lưu. | Gợi ý nội dung tiếp theo. |

### 10.1. Story map đơn giản hóa theo release slices

~~~text
HÀNH TRÌNH: Vào khóa → Chọn bài → Xem → Dừng → Quay lại → Tiếp tục

LÁT 1:    Có quyền → 1 video → phát → lưu điểm dừng → mở bài → resume
          ----- một đường đi đầu cuối có thể sử dụng -----

LÁT 2:    Có quyền → nhiều video → xem → tự lưu → danh sách bài → resume
          ----- giảm thao tác, mở rộng biến thể -----

LÁT 3:    Có quyền → nhiều thiết bị → xem → đồng bộ → xử lý xung đột
          ----- tích hợp và dữ liệu phức tạp hơn -----

Ý TƯỞNG SAU:
          Offline, bài đọc, quiz, bảng tiến độ, gợi ý học.
~~~

Story map không phải một kế hoạch bất biến. Nó cho thấy **những đường đi có thể hoàn tất** và tạo chỗ cho phản hồi làm thay đổi thứ tự.

### 10.2. Đường đi tối thiểu không phải đường đi “thiếu an toàn”

Một lát hỗ trợ **chỉ một loại video** có thể là phạm vi hợp lý; nhưng **bỏ kiểm tra quyền** hoặc lưu dữ liệu sai không phải cách rút gọn hợp lệ. Giảm phạm vi tính năng, không giảm tính đúng đắn của hành vi đang giao.

## 11. Chia lát dọc và chia ngang: phân biệt bằng kết quả cuối

Một sai lầm phổ biến là tách epic như sau:

- Story 1: thiết kế database.
- Story 2: viết backend.
- Story 3: làm frontend.
- Story 4: kiểm thử.
- Story 5: tích hợp.

Mỗi story có thể “xong” theo một bộ phận nhưng **chưa ai hoàn thành hành vi của học viên**. Rủi ro tích hợp và phản hồi bị dồn cuối.

**Lát dọc** là một phần nhỏ của **hành vi có giá trị, chạy qua các lớp cần thiết**, có thể kiểm chứng và đáp ứng DoD.

~~~mermaid
flowchart LR
    subgraph H["Chia ngang: tích hợp về cuối"]
      A["Toàn bộ DB"] --> B["Toàn bộ API"]
      B --> C["Toàn bộ UI"]
      C --> D["Kiểm thử sau"]
    end
    subgraph V["Chia dọc: nhận phản hồi theo lát"]
      E["Lát 1: resume một video có quyền"] --> F["Lát 2: gợi ý bài dở trong khóa"]
      F --> G["Lát 3: đồng bộ đa thiết bị"]
    end
~~~

### 11.1. Task kỹ thuật vẫn cần thiết

Vertical slicing **không loại bỏ** migration, API, UI, tests hay telemetry. Những việc đó có thể là **tasks bên dưới một story** hoặc một luồng công việc kỹ thuật minh bạch khác. Không nên gọi từng task riêng là giá trị người dùng đã bàn giao nếu chưa tạo hành vi.

### 11.2. Một story dọc có thể phụ thuộc nền tảng chung

Có thể cần một thay đổi nền tảng trước. Hãy hỏi có thể tạo **một lát end-to-end nhỏ với rủi ro tích hợp thực** thay vì xây toàn bộ nền tảng. Nếu thật sự có việc nền tảng độc lập, hãy mô tả mục tiêu giảm rủi ro và điều kiện hoàn tất của nó, không giả làm user story học viên.

## 12. Chọn cách chia lát: các mẫu thực dụng

| Cách chia | Story lớn | Lát nhỏ ứng viên | Điều cần chú ý |
| --- | --- | --- | --- |
| **Theo biến thể nội dung** | Hỗ trợ mọi loại bài. | Video trước; bài đọc/quiz sau. | Mỗi loại phải đúng quyền và dữ liệu. |
| **Theo hành vi chính/phụ** | Lưu, resume, dashboard, nhắc học. | Resume một video trước; dashboard sau. | Lát đầu phải trọn đường đi có giá trị. |
| **Theo quy tắc nghiệp vụ** | Tự động hóa mọi chính sách tiến độ. | Một quy tắc lưu khi Pause; autosave sau. | Phải nói rõ giới hạn để không gây hiểu sai. |
| **Theo workflow** | Học, dừng, resume, xem báo cáo. | Đường tối thiểu học–dừng–resume. | Đừng tách đến mức mất hành vi cuối. |
| **Theo dữ liệu đầu vào** | Mọi trạng thái dữ liệu. | Một định dạng đã được hỗ trợ rõ. | Xử lý lỗi/biên áp dụng ngay, không trì hoãn bảo mật. |
| **Theo role có quyền** | Học viên, giảng viên, admin. | Học viên xem của mình; quyền giảng viên sau. | Không dùng role slicing để phá quyền. |
| **Theo mức tự động hóa** | Tự động tất cả trạng thái. | Thao tác tối thiểu được xác nhận; tự động nâng cao sau. | Tránh quy trình thủ công không an toàn hoặc không khả thi. |
| **Theo tích hợp** | Kết nối nhiều dịch vụ. | Tích hợp một nguồn thật có contract rõ. | Mock không thay bằng chứng tích hợp thật. |
| **Theo mức phản hồi** | Mọi thiết bị và hoàn cảnh. | Lát online cho học viên đăng nhập; offline sau. | Không báo thành công đồng bộ khi chưa lưu. |
| **Theo quy mô rollout** | Mở toàn bộ học viên ngay. | Mở cohort được phép sau DoD. | Release slicing khác với cắt thiếu chức năng. |

### 12.1. Đừng chia chỉ theo happy path rồi gọi lỗi là “story sau”

Một lát “resume video” không có nghĩa cố tình để UI báo sai khi lưu thất bại hoặc cho người lạ đọc vị trí. Những điều kiện cơ bản **phải được bảo vệ trong cùng lát**. Có thể chia biến thể sản phẩm nâng cao, **không chia an toàn tối thiểu**.

### 12.2. Lát nhỏ nhất không phải lúc nào cũng là lát tốt nhất

Lát quá nhỏ, không có hành vi đáng quan sát, có thể tăng overhead và không tạo bằng chứng người dùng. Kích thước phù hợp là **đủ nhỏ để hoàn tất, đủ trọn vẹn để học và đủ an toàn để sử dụng**.

## 13. Từ epic “Học tiếp” đến backlog các lát dọc có thứ tự

Từ story map và Conversation, nhóm có thể lập một số story ứng viên. **Thứ tự dưới đây là ví dụ**, không phải cam kết roadmap; Product Owner cần cân nhắc giá trị, rủi ro, phụ thuộc và bằng chứng thực tế.

| ID | Story ứng viên | Hành vi được giao khi Done | Rủi ro học được |
| --- | --- | --- | --- |
| **CONT-01** | Học viên tiếp tục một video trong khóa có quyền từ vị trí đã lưu. | Có thể xem, lưu vị trí hợp lệ, quay lại và tiếp tục. | Tính đúng đắn lưu/đọc, quyền, trạng thái lỗi và nhu cầu resume. |
| **CONT-02** | Học viên tìm nhanh bài dở của mình trong một khóa. | Có một đường vào rõ tới bài đang dở. | Khả năng tìm thấy, ưu tiên UI, dữ liệu tổng hợp. |
| **CONT-03** | Học viên tiếp tục bài từ một thiết bị khác sau đăng nhập. | Dữ liệu giữa các phiên/thiết bị có quy tắc rõ. | Đồng bộ, độ trễ, xung đột cập nhật. |
| **CONT-04** | Học viên lưu tiến độ tự động ở các điểm hợp lý. | Giảm thao tác Pause thủ công, không xác nhận lưu giả. | Hiệu năng ghi, mạng chập chờn, trải nghiệm. |
| **CONT-05** | Học viên xem tiến độ nhiều loại nội dung. | Video, bài đọc và quiz theo quy tắc riêng. | Khác biệt domain, tránh ép mô hình video vào quiz. |
| **CONT-06** | Học viên dùng một phần chức năng khi offline. | Có hành vi offline rõ và chính sách đồng bộ/xung đột. | Dữ liệu cục bộ, bảo mật, tranh chấp khi nối mạng. |
| **CONT-07** | Giảng viên được phép xem tiến độ học viên trong phạm vi được giao. | Xem thông tin theo đúng quyền và mục đích. | Chính sách quyền, riêng tư, khả năng diễn giải. |

### 13.1. Story CONT-01 thực sự có hành vi trọn vẹn

**Card:**

> Là học viên đã đăng nhập và có quyền xem một video Java, tôi muốn quay lại video từ vị trí đã lưu để tiếp tục học mà không phải dò thủ công.

**Điều được giao:** người học dừng video, vị trí hợp lệ được ghi nhận, khi quay lại video trong phạm vi hỗ trợ có thể tiếp tục ở vị trí đó. Bộ test tích hợp chứng minh đường đi và DoD bảo vệ chất lượng.

**Điều chưa giao:** dashboard toàn khóa, nhiều loại nội dung, offline, thống kê giảng viên. Những điều đó không được giả vờ đã có.

### 13.2. Lát CONT-01 còn quá lớn thì sao?

Có thể chia tiếp thành một lát với **một video trong một khóa** và một chính sách ghi/khôi phục đơn giản, giữ end-to-end và an toàn. Không nên chia thành “lưu được nhưng chưa đọc được tới Sprint sau”, nếu không ai có thể sử dụng khả năng **tiếp tục học** được mong đợi.

### 13.3. Lát CONT-02 có thể mang giá trị riêng

Sau khi CONT-01 đủ tin cậy, học viên vẫn phải tìm bài trong khóa. CONT-02 tập trung vào **tìm đường vào bài dở**; một thử nghiệm usability có thể cho thấy phần này mang giá trị hơn việc đồng bộ nâng cao.

### 13.4. Lát CONT-03 cần làm rõ ngữ nghĩa cập nhật

Nếu thiết bị A lưu 05:20 rồi thiết bị B lưu 03:10 sau, nên lấy lần cập nhật mới nhất theo server, tiến độ xa nhất hay hỏi người học? Không có một câu trả lời đúng cho mọi sản phẩm. Đây là **quyết định nghiệp vụ/dữ liệu** cần Conversation, tests và phương án xử lý an toàn, không phải một task ngầm của backend.

## 14. Chọn “lát đầu” bằng giá trị, học hỏi và khả năng hoàn tất

Chia được nhiều story chưa đủ; cần **đưa một hoặc một vài lát vào thứ tự hợp lý**.

Các câu hỏi chọn lát:

1. **Giá trị sớm:** có người dùng cụ thể hưởng lợi khi lát Done?
2. **Giả định lớn:** lát giúp kiểm chứng điều chưa biết nào quan trọng?
3. **Rủi ro kỹ thuật:** có thể tích hợp thật để kiểm hợp đồng và dữ liệu sớm?
4. **Điều kiện chất lượng:** có thể đạt DoD và quyền/trạng thái lỗi trong phạm vi?
5. **Phụ thuộc:** cần bên nào, có cách rút phạm vi mà không đánh lừa người dùng?
6. **Kích thước:** có thể hoàn tất trong chu kỳ nhóm sử dụng, không đẩy việc kiểm thử sang sau?
7. **Phản hồi:** sau khi Done/release, có phương pháp kiểm chứng giá trị?
8. **Đánh đổi:** bỏ lát nào khỏi phạm vi hiện tại mà không làm hỏng lát được giao?

### 14.1. Ma trận ưu tiên minh họa

| Lát | Giá trị sớm | Độ bất định cần học | Độ phức tạp/rủi ro | Quyết định minh họa |
| --- | --- | --- | --- | --- |
| CONT-01 | Cao | Cao | Có thể kiểm soát nếu giới hạn một loại video. | Thử trước với DoD đầy đủ. |
| CONT-02 | Cao | Trung bình | UI và dữ liệu tổng hợp. | Lát kế nếu tìm bài còn bất tiện. |
| CONT-03 | Có thể cao | Cao | Đồng bộ/xung đột khó hơn. | Làm rõ chính sách, có thể spike nhỏ trước. |
| CONT-05 | Chưa rõ | Cao | Nhiều rule domain. | Nghiên cứu nhu cầu, chưa mở rộng vội. |
| CONT-06 | Có thể cao ở người học thiếu mạng | Cao | Dữ liệu và bảo mật phức tạp. | Khám phá riêng, không gắn ngầm vào CONT-01. |

Mức “cao/trung bình” mang tính thảo luận, **không phải dữ liệu nghiên cứu thực**. Chọn thứ tự cuối cần dựa trên Product Goal và thông tin PO có được.

### 14.2. Khi một spike hợp lý

Nếu chưa rõ player hỗ trợ lưu vị trí hoặc contract qua hệ thống hiện tại, có thể làm **spike có giới hạn** nhằm kiểm chứng khả thi. Spike nên có câu hỏi và đầu ra (kết quả thử, quyết định, rủi ro), nhưng **không mặc nhiên là Increment có thể sử dụng**. Sau spike, team vẫn cần thực hiện story đạt DoD để giao giá trị.

## 15. Viết acceptance criteria: điều kiện để xác nhận hành vi

**Acceptance criteria** là các điều kiện **cụ thể, có thể kiểm tra** để xác nhận story cung cấp hành vi mong muốn trong phạm vi đã thống nhất. Chúng bổ trợ Conversation và thường làm cơ sở cho acceptance tests.

Một tiêu chí hữu ích:

- Nêu **đầu vào/bối cảnh có ý nghĩa**.
- Nêu **hành động hoặc sự kiện**.
- Nêu **kết quả quan sát được**.
- Giới hạn phạm vi và trường hợp áp dụng.
- Không khóa cứng chi tiết triển khai khi không cần.
- Có thể được kiểm bởi Developers, QA và PO với cùng cách hiểu.
- Bảo vệ trường hợp lỗi, quyền và biên tương xứng rủi ro.
- Không mâu thuẫn Product Goal, quy tắc có thẩm quyền hoặc DoD.

### 15.1. Tiêu chí mơ hồ và tiêu chí có thể kiểm chứng

| Tiêu chí mơ hồ | Vì sao khó kiểm? | Ví dụ cải thiện |
| --- | --- | --- |
| “Video phải mở nhanh.” | Không rõ mốc đo, điều kiện và ngưỡng. | “Trong điều kiện thử được định nghĩa, yêu cầu khôi phục trả kết quả trong giới hạn hiệu năng được nhóm thống nhất.” |
| “Tiến độ phải chính xác.” | Không rõ thế nào là đúng. | “Đã lưu vị trí 05:20 trong video đang hỗ trợ; mở lại trả vị trí theo quy tắc cho phép.” |
| “Phải thân thiện.” | Thuần cảm giác, thiếu tác vụ. | “Trong buổi thử có kịch bản, học viên tìm và tiếp tục bài dở mà không cần chỉ dẫn.” |
| “Mọi lỗi phải được xử lý.” | Phạm vi bất khả xác định. | “Nếu ghi vị trí thất bại, giao diện không báo đã lưu thành công.” |
| “Bảo mật tuyệt đối.” | Không thể kiểm chứng tuyệt đối từ một test. | “Tài khoản không có quyền đọc/sửa tiến độ người khác bị từ chối và không trả dữ liệu riêng tư.” |
| “Ứng dụng dùng MongoDB.” | Là giải pháp, không phải hành vi. | Ghi như ràng buộc kiến trúc có thẩm quyền nếu bắt buộc, không ngụy trang thành AC giá trị. |
| “Code coverage 100%.” | Đo thực hiện, không mô tả nhu cầu. | Đặt chính sách kiểm thử theo rủi ro trong DoD; AC mô tả hành vi. |

### 15.2. Không cần mọi criterion là Gherkin

Một bảng ví dụ, quy tắc nghiệp vụ kèm dữ liệu hay danh sách rõ cũng có thể tốt. **Given–When–Then** đặc biệt hữu ích khi nhiều nhánh hành vi cần có ngữ nghĩa thống nhất. Dùng hình thức giúp hiểu, không dùng vì phong trào.

### 15.3. Không chốt ngưỡng hiệu năng bằng con số bịa

Nếu chưa có mục tiêu hiệu năng được thống nhất, viết **question/risk và một hoạt động quyết định** thay vì âm thầm ghi “100 ms” như sự thật. Khi chọn ngưỡng phải rõ điều kiện tải, percentile và nơi đo.

## 16. Bộ acceptance criteria cho CONT-01

**Story CONT-01:**

> Là học viên đã đăng nhập có quyền với video trong khóa Java, tôi muốn quay lại từ vị trí đã lưu, để tiếp tục học mà không dò thủ công.

**Phạm vi giả định đã được chốt cho ví dụ:** video được hỗ trợ trong một khóa; người học đăng nhập; vị trí được lưu sau một thao tác có chủ đích; chưa có offline và chưa có xử lý xung đột đa thiết bị nâng cao. Những giả định này phải được PO/nhóm kiểm tra trước khi dùng ở sản phẩm thật.

| Mã | Tiêu chí chấp nhận của lát đầu | Cách kiểm chứng |
| --- | --- | --- |
| **AC-01** | Khi học viên có quyền xem video và lưu vị trí hợp lệ thành công, lần mở tiếp theo có thể tiếp tục từ vị trí đã lưu theo quy tắc. | Acceptance/integration test và thử UI. |
| **AC-02** | Nếu video chưa có vị trí đã lưu, nó bắt đầu từ đầu, không báo đã khôi phục. | Test lần học đầu. |
| **AC-03** | Khi ghi vị trí thất bại hoặc chưa được xác nhận, UI không báo “Đã lưu” như thể thao tác đã thành công. | Test timeout/lỗi API. |
| **AC-04** | Tài khoản không có quyền đọc hoặc sửa tiến độ của người khác bị từ chối, không nhận dữ liệu riêng. | Negative authorization tests. |
| **AC-05** | Vị trí không hợp lệ được xử lý theo một chính sách rõ; không gây lỗi hiển thị không kiểm soát. | Ví dụ boundary sau khi thống nhất rule. |
| **AC-06** | Học viên không được phép xem video không thể tạo/sửa tiến độ của video đó. | Negative test role/content rights. |
| **AC-07** | Người dùng có thể phân biệt trạng thái đang lưu, đã lưu, không thể lưu trong phạm vi được hỗ trợ. | Test hành vi UI/khả năng tiếp cận theo thiết kế. |
| **AC-08** | Khi thực hiện lại một yêu cầu ghi đã xử lý, dữ liệu không hỏng hoặc tạo tác dụng phụ sai quy tắc. | Integration tests phù hợp với identity của request. |

**Lưu ý quan trọng:** AC-05 chưa hoàn tất nếu nhóm chưa quyết định vị trí vượt thời lượng xử lý thế nào. Trong bài học, điều đó là một **open question**. Không nên đánh dấu PBI sẵn sàng phát triển nếu quy tắc này có thể ảnh hưởng triển khai và DoD của lát đang chọn.

### 16.1. Một quyết định minh họa cho AC-05

Sau Conversation, nhóm có thể chọn:

> “Đối với video chưa đổi phiên bản, vị trí lưu âm hoặc vượt thời lượng bị từ chối; khi dữ liệu cũ không hợp lệ được đọc, áp dụng fallback đã được Product Owner và Developers xác nhận, không báo đã khôi phục từ dữ liệu hỏng.”

Đây chỉ là **một phương án để viết tiêu chí có thể thử**, không phải quy tắc phổ quát. Cần thống nhất trường hợp video bị thay đổi, quyền và cách phục hồi dữ liệu.

### 16.2. Đừng ép mọi rủi ro tương lai vào lát đầu

Không nhất thiết AC-01 phải giải quyết đồng bộ ba thiết bị, offline queue, AI gợi ý và giảng viên xem thống kê. Các điều đó nên thành **story hoặc spike riêng** nếu Product Goal/ưu tiên đòi hỏi.

## 17. Given–When–Then: biến criteria thành ví dụ thực thi được

Gherkin thường dùng các bước:

- **Given:** ngữ cảnh/điều kiện trước.
- **When:** hành động/sự kiện.
- **Then:** kết quả quan sát mong đợi.
- **And/But:** bổ sung điều kiện hoặc kết quả.

Gherkin **có thể** được tự động hóa bằng công cụ BDD phù hợp, nhưng một đoạn text có từ Given–When–Then **không tự là test chạy được** nếu chưa nối với code, fixture và môi trường.

### 17.1. Kịch bản thành công

~~~gherkin
Feature: Học viên tiếp tục video từ vị trí đã lưu

Scenario: Mở lại một video đã lưu vị trí
  Given học viên "An" đã đăng nhập và có quyền xem "Java Video 01"
  And video có thời lượng 12 phút
  And vị trí 05:20 của An đã được lưu thành công cho video đó
  When An mở lại "Java Video 01"
  Then video sẵn sàng tiếp tục từ vị trí đã lưu theo quy tắc của sản phẩm
  And dữ liệu tiến độ của học viên khác không được tiết lộ

Scenario: Lần đầu xem video
  Given học viên "An" có quyền xem "Java Video 02"
  And chưa có vị trí đã lưu cho An trong video đó
  When An mở "Java Video 02"
  Then video bắt đầu từ đầu
  And ứng dụng không thông báo đã khôi phục tiến độ
~~~

### 17.2. Kịch bản lỗi mạng và trạng thái thật

~~~gherkin
Feature: Phản hồi lưu tiến độ minh bạch

Scenario: Dịch vụ ghi tiến độ không thể hoàn tất
  Given học viên "An" đã đăng nhập và có quyền xem video
  And dịch vụ ghi vị trí không thể xác nhận thao tác
  When An yêu cầu lưu một vị trí hợp lệ
  Then giao diện không báo rằng vị trí đã được lưu thành công
  And giao diện cung cấp trạng thái và hướng xử lý phù hợp
  And không làm mất dữ liệu đã lưu hợp lệ trước đó ngoài quy tắc đã xác nhận
~~~

**Cần làm rõ ngữ nghĩa timeout**: có thể server đã ghi nhưng phản hồi bị mất. UI không nên khẳng định thành công khi chưa có xác nhận, đồng thời cách retry phải tránh tạo dữ liệu sai. Đây là ví dụ vì sao AC và thiết kế kỹ thuật cần thảo luận cùng nhau.

### 17.3. Kịch bản quyền truy cập

~~~gherkin
Feature: Tiến độ học tập chỉ được truy cập theo quyền

Scenario: Từ chối đọc tiến độ của người khác
  Given học viên "An" không được phép đọc tiến độ của "Bình"
  When An yêu cầu tiến độ của Bình bằng một ID bất kỳ
  Then hệ thống từ chối theo chính sách
  And không trả vị trí xem hoặc dữ liệu riêng tư của Bình

Scenario: Từ chối ghi tiến độ vào nội dung không được phép
  Given học viên "An" không có quyền xem "Java Video 99"
  When An yêu cầu lưu một vị trí cho "Java Video 99"
  Then hệ thống từ chối theo chính sách
  And không tạo hoặc thay đổi bản ghi tiến độ của An cho video đó
~~~

### 17.4. Kịch bản dữ liệu biên

~~~gherkin
Feature: Giá trị vị trí video hợp lệ

Scenario: Vị trí âm bị từ chối
  Given học viên có quyền và video dài 12 phút
  When học viên yêu cầu lưu vị trí âm 10 giây
  Then hệ thống từ chối giá trị không hợp lệ theo hợp đồng đã thống nhất
  And không thay thế vị trí hợp lệ đã lưu trước đó

Scenario: Vị trí vượt thời lượng bị từ chối
  Given học viên có quyền và video dài 12 phút
  When học viên yêu cầu lưu vị trí 20 phút
  Then hệ thống từ chối giá trị vượt phạm vi theo hợp đồng đã thống nhất
  And không ghi vị trí không hợp lệ
~~~

Các scenarios biên minh họa **một rule đã chọn**; nếu PO quyết định cách khác, cập nhật acceptance examples và tests. Không để ví dụ mẫu biến thành quy tắc không được chất vấn.

## 18. Dùng bảng quyết định khi tổ hợp điều kiện phức tạp

Khi có nhiều trạng thái, một bảng quyết định có thể dễ rà soát hơn 30 kịch bản lặp lời.

Ví dụ quyền và vị trí:

| Đăng nhập? | Có quyền xem video? | Vị trí lưu hợp lệ? | Kết quả mong đợi |
| --- | --- | --- | --- |
| Không | Không xác định | Bất kỳ | Từ chối theo cơ chế xác thực/ủy quyền áp dụng; không tiết lộ tiến độ riêng. |
| Có | Không | Bất kỳ | Từ chối đọc/ghi dữ liệu tiến độ trái quyền. |
| Có | Có | Chưa có | Video bắt đầu từ đầu. |
| Có | Có | Có | Khôi phục theo vị trí đã lưu. |
| Có | Có | Không hợp lệ | Xử lý theo rule lỗi dữ liệu đã thống nhất; không làm hỏng trạng thái hợp lệ. |

### 18.1. Một bảng cần ranh giới rõ

Nếu cột “đăng nhập” dùng cả trường hợp phiên hết hạn và người chưa từng đăng nhập, có thể cần chia thêm theo quyền. Bảng hữu ích khi **phân vùng đầu vào đầy đủ và không mâu thuẫn**, nhưng không nên áp đặt mọi trạng thái đều được giải quyết trong cùng một PBI.

### 18.2. Ví dụ không phải oracle tuyệt đối

Một table có thể được nhất trí rồi vẫn sai với người dùng thật. Confirmation xác nhận **hiểu biết hiện tại**, sau khi giao vẫn cần feedback về giá trị và chất lượng.

## 19. Acceptance criteria và Definition of Done bổ trợ nhau thế nào?

Một story có thể có acceptance criteria rất rõ nhưng Increment vẫn **chưa Done** nếu code chưa tích hợp hoặc vi phạm tiêu chuẩn chất lượng chung.

| Phạm vi | Acceptance criteria của CONT-01 | Definition of Done của sản phẩm |
| --- | --- | --- |
| **Hành vi riêng** | Đã lưu 05:20 → có thể tiếp tục từ vị trí đã lưu. | Code và dữ liệu mới tích hợp cùng sản phẩm hiện tại. |
| **Trường hợp lần đầu** | Chưa lưu → video từ đầu. | Kiểm thử phù hợp và hồi quy đạt. |
| **Lỗi mạng** | Không báo thành công giả. | Có khả năng quan sát lỗi và hỗ trợ phù hợp. |
| **Quyền** | Không đọc/sửa tiến độ người khác. | Các tiêu chuẩn quyền/bảo mật chung áp dụng cho Increment đều đạt. |
| **Biên** | Vị trí âm/vượt thời lượng xử lý theo rule. | Không phá những Increment trước; tương thích dữ liệu/hợp đồng áp dụng. |
| **Trải nghiệm** | Trạng thái lưu/khôi phục có nghĩa với người dùng. | Hướng dẫn, accessibility và chính sách tổ chức phù hợp. |

Trong Scrum Guide, **Definition of Done là commitment của Increment**. Increment phải có thể sử dụng và phù hợp với các Increment trước; PBI chưa đạt DoD **không được coi là một phần của Increment**.

### 19.1. Không biến AC thành checklist code chi tiết

“Hàm ProgressService phải có 3 interface và dùng thư viện X” thường là lựa chọn thiết kế hoặc ràng buộc kiến trúc, không phải tiêu chí chấp nhận hành vi. Có thể ghi **technical decision/standard** ở nơi phù hợp và liên kết.

### 19.2. Không dùng AC để hạ DoD

Nếu story không nói rõ kiểm thử quyền nhưng DoD tổ chức đòi hỏi bảo vệ dữ liệu, nhóm vẫn phải tuân thủ. **Không liệt kê trong card** không có nghĩa **được bỏ kiểm soát bắt buộc**.

## 20. Làm cho tiêu chí chấp nhận có thể kiểm chứng ở đúng tầng

Không phải mọi AC nên được kiểm chỉ bằng UI end-to-end. Chọn tầng theo rủi ro:

| Hành vi | Tầng kiểm chứng phù hợp | Bằng chứng |
| --- | --- | --- |
| Vị trí âm/vượt thời lượng bị từ chối. | Unit/component + API contract/integration. | Test rule giá trị và hệ quả lưu. |
| Lưu/đọc tiến độ qua phiên. | Integration/end-to-end. | Bằng chứng API–database–UI hoạt động. |
| Không có dữ liệu → bắt đầu từ đầu. | Component/integration, có thể UI acceptance. | Test lần đầu. |
| Không đọc tiến độ người khác. | Negative authorization integration/security tests. | Tài khoản trái quyền không lấy được dữ liệu. |
| Mất mạng không báo đã lưu. | UI behavior test và integration simulation. | Trạng thái giao diện đúng. |
| Học viên thực sự tìm thấy đường “Học tiếp”. | Usability test, telemetry hợp lệ, phỏng vấn. | Quan sát task success, khó khăn và phản hồi. |
| Không phá video player hiện tại. | Regression tests và review tích hợp. | Các luồng cũ còn hoạt động. |
| Chịu tải trong phạm vi đã thống nhất. | Performance/resilience tests. | Kết quả với môi trường, tải và ngưỡng được định nghĩa. |

### 20.1. Bộ test tự động không thay hiểu biết nghiệp vụ

Có thể viết rất nhiều tests cho cách resume sai. **PO và người hiểu nhu cầu cần xác nhận ví dụ**, Developers và QA đưa bằng chứng về khả thi và rủi ro. Mọi người có trách nhiệm tạo hiểu biết chung; không chuyển toàn bộ công việc “viết acceptance criteria” cho QA để họ đoán.

### 20.2. Khi nào TDD hỗ trợ câu chuyện?

Với rule “giới hạn vị trí video hợp lệ”, Developers có thể:

1. Viết test cho vị trí hợp lệ.
2. Thấy fail vì code chưa hỗ trợ.
3. Viết logic nhỏ nhất cho test đạt.
4. Refactor không đổi hành vi.
5. Thêm test vị trí âm, vượt thời lượng và dữ liệu rỗng.
6. Kết nối với integration/acceptance tests toàn luồng.

**TDD là thực hành kỹ thuật XP**, giúp điều chỉnh thiết kế, nhưng không chọn hộ Product Goal hoặc điều kiện nghiệp vụ đúng.

## 21. Ví dụ kiểm thử rule bằng mã Java đơn giản

Giả sử cả nhóm đã chốt **vị trí hợp lệ nằm từ 0 tới thời lượng video, tính bằng giây** cho lát đầu.

Một thành phần Java thuần có thể kiểm quy tắc:

~~~java
public final class VideoPositionPolicy {
    public boolean isValid(
        long durationSeconds,
        long positionSeconds
    ) {
        return durationSeconds > 0
                && positionSeconds >= 0
                && positionSeconds <= durationSeconds;
    }
}
~~~

Với JUnit 5, các ví dụ kiểm chứng:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class VideoPositionPolicyTest {
    private final VideoPositionPolicy policy =
            new VideoPositionPolicy();

    @Test
    void allowsPositionWithinVideoDuration() {
        assertTrue(policy.isValid(720, 320));
    }

    @Test
    void allowsStartOfVideo() {
        assertTrue(policy.isValid(720, 0));
    }

    @Test
    void rejectsNegativePosition() {
        assertFalse(policy.isValid(720, -10));
    }

    @Test
    void rejectsPositionPastEnd() {
        assertFalse(policy.isValid(720, 1200));
    }

    @Test
    void rejectsInvalidDuration() {
        assertFalse(policy.isValid(0, 0));
    }
}
~~~

**Giới hạn:** hai lớp trên chỉ kiểm một rule dữ liệu. Chúng **không** xác thực quyền, không chứng minh request đã ghi vào database, không kiểm rollback khi lỗi, không xử lý video thay phiên bản và không đảm bảo trải nghiệm người dùng. Phải bổ sung tests phù hợp và DoD trước khi gọi CONT-01 Done.

### 21.1. Quy tắc đơn giản cũng cần được quyết định

Có sản phẩm cho phép vị trí bằng thời lượng video như dấu hiệu hoàn thành; sản phẩm khác sẽ định nghĩa “hoàn thành” bằng sự kiện riêng. Đoạn mã học tập **không phải chuẩn nghiệp vụ phổ quát**. Nếu rule thay đổi, cần cập nhật example/acceptance criteria trước khi sửa code.

## 22. Tiêu chí chấp nhận phải đi cùng quyền và dữ liệu

Những câu hỏi bảo mật thường dễ bị bỏ sót khi nhóm chỉ tập trung happy path:

- Ai được lưu tiến độ của ai?
- ID học viên do client gửi có được tin trực tiếp không?
- Một giảng viên được cấp quyền xem tiến độ của lớp nào?
- Khi học viên rời khóa, quyền truy cập cũ thay đổi thế nào?
- Dữ liệu tiến độ có được lưu trong logs/traces không?
- Có thông tin cá nhân không cần thiết trong telemetry?
- Retry có tạo nhiều bản ghi không?
- Khi vị trí không hợp lệ, có làm mất vị trí trước đó không?

### 22.1. Không có “cohort nhỏ nên không cần bảo mật”

Mở cho năm học viên thử không làm việc **đọc tiến độ sai quyền** trở nên hợp lệ. Scope nhỏ giúp nhận feedback sớm nhưng phải giữ **guardrails áp dụng**.

### 22.2. Khi một quy tắc cần phê duyệt ngoài nhóm

Các điều kiện pháp lý, dữ liệu riêng tư, bảo mật hoặc hợp đồng có thể đòi thẩm quyền khác. Product Owner không tự có quyền bỏ các nghĩa vụ đó; Developers cũng không nên tự suy đoán. Cần ghi **người có quyền quyết, bằng chứng và trạng thái** thay vì để story mơ hồ.

### 22.3. Lát nhỏ không xóa rủi ro dữ liệu

Ví dụ vị trí video được cập nhật qua nhiều thiết bị có thể gặp tranh chấp khi ghi. Nếu CONT-01 chưa hỗ trợ đa thiết bị, phạm vi cần được mô tả rõ và không tự tuyên bố “đồng bộ đầy đủ”. Khi tới CONT-03, cần Conversation về conflict resolution, test concurrency và đối soát dữ liệu.

## 23. Chất lượng Conversation: kiểm tra bằng teach-back và quyết định rõ

Một cách thực tế để biết mọi người hiểu giống nhau là yêu cầu mỗi vai trò **diễn đạt lại kết quả**:

**PO:** “Người học sẽ làm gì được ở cuối lát đầu?”

**Developer:** “Một học viên có quyền xem video, lưu vị trí và quay lại đúng đoạn; không cần dashboard toàn khóa.”

**QA:** “Nếu chưa lưu, mở từ đầu; nếu ghi lỗi, không báo đã lưu; truy cập trái quyền bị từ chối; vị trí không hợp lệ theo rule đã chốt.”

**UX:** “Trạng thái lưu phải hiểu được với cả người dùng bàn phím và công nghệ hỗ trợ, trong phạm vi thiết kế sản phẩm.”

**PO:** “Đúng. Riêng ngưỡng ‘đúng vị trí’ và thông báo lỗi cần xác nhận bằng ví dụ cụ thể trước khi đưa PBI vào làm.”

**Giá trị của teach-back:** phát hiện “nghe giống nhau” nhưng thực tế khác nhau trước khi xây.

### 23.1. Bản ghi quyết định sau Conversation

~~~text
STORY: CONT-01
DECISION: DEC-021
STATUS: ACCEPTED (minh họa)
BỐI CẢNH:
  Học viên mất thời gian tìm lại vị trí video.

PHẠM VI:
  Học viên đã đăng nhập, video được phép,
  một loại nội dung video và quy tắc lưu đã thống nhất.

QUY TẮC:
  - Chưa có tiến độ: bắt đầu từ đầu.
  - Không báo thành công khi ghi chưa được xác nhận.
  - Không đọc/sửa dữ liệu sai quyền.
  - Vị trí hợp lệ theo chính sách thời lượng.

CHƯA LÀM:
  Dashboard toàn khóa, offline, xung đột đa thiết bị.

NGƯỜI CÓ QUYỀN CHỐT:
  Xác định theo phạm vi sản phẩm/nghiệp vụ và tổ chức.

BẰNG CHỨNG:
  Link example map, PBI, acceptance scenarios, tests.

XEM LẠI:
  Khi có phản hồi học viên hoặc thay chính sách nội dung video.
~~~

Không cần tạo ADR dài cho mọi story nhỏ; mẫu giúp làm rõ **câu trả lời nào đã có hiệu lực** và ai có quyền điều chỉnh, nhất là khi nhiều nhóm hoặc múi giờ cùng làm.

## 24. Từ câu chuyện đang khám phá tới câu chuyện đủ rõ để thực hiện

Một user story có thể ở nhiều mức độ hiểu:

- **Ý tưởng:** có nhu cầu được ghi, chưa rõ người dùng/giá trị.
- **Đang khám phá:** có card và một số câu hỏi mở, cần tìm hiểu.
- **Ứng viên chia lát:** đã thấy các biến thể nhưng còn phạm vi lớn.
- **Đủ rõ để cân nhắc làm:** có hành vi, acceptance examples, rủi ro/phụ thuộc quan trọng và phạm vi phù hợp.
- **Đang làm:** Developers đang tạo Increment theo kế hoạch phù hợp.
- **Done:** phần được giao đáp ứng Definition of Done.
- **Đã phát hành/nhận feedback:** các mốc khác Done, tùy quy trình sản phẩm.

Tên các trạng thái có thể khác nhau theo nhóm. Đây là **mô hình minh họa**, không phải các trạng thái bắt buộc của Scrum.

### 24.1. Một checklist gọn trước khi chọn làm

- [ ] Người hưởng lợi và kết quả có ý nghĩa được mô tả.
- [ ] Story có liên kết với Product Goal/mục tiêu luồng phù hợp.
- [ ] Phạm vi lát có thể tạo hành vi đầu cuối.
- [ ] Những quy tắc cần thiết đã được thảo luận với đúng người.
- [ ] Có acceptance examples cho đường chính và rủi ro quan trọng.
- [ ] Câu hỏi mở ảnh hưởng trực tiếp tới giải pháp/DoD đã có hướng xử lý.
- [ ] Phụ thuộc lớn được nhận diện, người có thể trả lời rõ.
- [ ] Các guardrails bảo mật, chất lượng và dữ liệu không bị bỏ qua.
- [ ] Nhóm đủ hiểu để forecast hoặc quyết định kéo vào làm theo cách đang sử dụng.
- [ ] Có một đường nhận phản hồi sau khi giao.

Đây có thể là **working agreement** hoặc chính sách luồng tùy chọn, không nên dựng “Definition of Ready bắt buộc” như một cổng cố định thay thế trao đổi. Scrum Guide không bắt buộc một Definition of Ready chính thức.

### 24.2. “Đủ rõ” không có nghĩa không còn bất định

Một Product Backlog Item luôn có thể xuất hiện câu hỏi mới. Hãy phân biệt:

- **Bất định có thể giải quyết trong khi làm**, không ảnh hưởng mục tiêu/DoD quá lớn.
- **Bất định khiến chưa thể xác định hành vi đúng**, cần Conversation, ví dụ hoặc phép thử trước.
- **Ràng buộc an toàn chưa rõ**, cần người có thẩm quyền trước khi release.

Nếu một story cần “đoán phần còn thiếu” ở chỗ quyết định quyền truy cập, chưa nên báo đã Ready.

## 25. Refinement: hoạt động trao đổi liên tục, không phải buổi ký duyệt

Trong Scrum, **Product Backlog refinement** là hoạt động liên tục làm rõ và chia nhỏ các Product Backlog Items, bổ sung chi tiết, thứ tự và kích thước theo nhu cầu. Không phải một sự kiện Scrum bắt buộc với thời lượng cố định.

Một refinement hiệu quả:

1. **PO nêu giá trị và bối cảnh** chứ không chỉ đọc tiêu đề ticket.
2. **Developers và người kiểm thử nêu giả định**, trường hợp lỗi, phụ thuộc.
3. **Nhóm kể ví dụ cụ thể** về hành vi thành công và chưa thành công.
4. **Chia lát hoặc đổi thứ tự** nếu story còn quá lớn.
5. **Ghi decisions/open questions** ở nơi mọi người tìm được.
6. **Đánh giá rủi ro và công việc đạt DoD**, không chỉ code.
7. **Dừng khi đủ để quyết định bước tiếp**, không cố thiết kế toàn bộ tương lai.

### 25.1. Một kịch bản 30 phút minh họa

| Giai đoạn | Mục tiêu | Kết quả cần lưu |
| --- | --- | --- |
| 0–5 phút | PO nêu người dùng, vấn đề và giá trị. | Card ngắn, Product Goal liên quan. |
| 5–12 phút | Nhóm đưa ví dụ thật và câu hỏi. | Rule, Example, Question. |
| 12–20 phút | Story mapping/chia lát. | 2–4 stories có thứ tự ứng viên. |
| 20–26 phút | Chọn lát đầu, bàn quyền/lỗi/dữ liệu. | AC, risks, phụ thuộc, decision owner. |
| 26–30 phút | Xác nhận bước tiếp và ai trả lời gì. | PBI cập nhật, câu hỏi mở có owner. |

Đây là phương án tổ chức, **không phải quy tắc 30 phút của Scrum**. Khi vấn đề đơn giản có thể làm ngắn hơn; khi rủi ro lớn có thể cần nghiên cứu hoặc phê duyệt ngoài nhóm.

### 25.2. Không biến refinement thành cuộc họp cập nhật status

Câu hỏi chính không phải “mỗi người hoàn thành bao nhiêu phần trăm?”, mà là **“điều gì giúp chúng ta hiểu và giao phần giá trị kế tiếp an toàn hơn?”**.

## 26. Kỹ thuật chọn lát khi cuộc trao đổi xuất hiện quá nhiều biến thể

Giả sử người dùng nêu thêm:

- Học viên mở lại video trên điện thoại và laptop.
- Khóa học cho phép video, bài đọc, quiz và live class.
- Học viên có thể tải một số nội dung offline.
- Giảng viên cần dashboard lớp.
- Người học muốn nhắc học cá nhân hóa.
- Một số học viên có quyền truy cập giới hạn theo gói.

Đây có thể là nhiều stories, không nên gộp vào CONT-01.

### 26.1. Phân theo **hành vi khác nhau**

“Tiếp tục video” và “xem thống kê lớp” phục vụ **người hưởng lợi khác** và có chính sách quyền khác. Chúng không phải hai tasks của một story học viên.

### 26.2. Phân theo **biến thể đầu vào**

Video trước; bài đọc và quiz sau. Chú ý quiz có thể cần trạng thái “đã trả lời/chưa nộp”, không thể dùng cùng một con số timestamp của video.

### 26.3. Phân theo **độ phức tạp nghiệp vụ**

Một phiên đăng nhập online trước, xung đột giữa thiết bị sau. Tuy vậy lát đầu phải xử lý retry theo quy tắc tối thiểu để không làm sai dữ liệu.

### 26.4. Phân theo **người dùng được phép**

Có thể mở cho một nhóm lớp trước khi mở cho toàn sản phẩm. Nhưng **giới hạn rollout** là phương pháp phát hành, không tự biến một task backend thành story có giá trị.

### 26.5. Phân theo **mức tự động hóa**

Một thao tác có chủ đích “Lưu vị trí” trước, autosave sau, nếu trải nghiệm đầu vẫn có giá trị. Không được bỏ phản hồi lỗi hoặc ghi dữ liệu không nhất quán.

### 26.6. Phân theo **rủi ro cần học**

Nếu bất định lớn là học viên có dùng nút “Học tiếp” hay không, một lát UI với luồng thật và nhóm thử có thể có giá trị. Nếu bất định lớn là conflict resolution, spike + acceptance examples về xung đột có thể cần trước khi chọn kỹ thuật.

### 26.7. Đừng chia thành lát làm đẹp số

Một story “tạo cột positionSeconds” rồi một story “tạo entity Progress” và một story “tạo DTO” có thể làm throughput tăng, nhưng người dùng vẫn chưa được giúp. Chỉ số số story Done **không thay câu hỏi về Increment dùng được**.

## 27. Ước lượng và forecast khi đã chia lát

Khi một story còn quá lớn, Developers thường khó ước lượng vì nhiều giả định và biến thể chưa rõ. Việc chia lát có thể làm **độ bất định giảm**, nhưng không tự biến estimate thành cam kết chắc chắn.

### 27.1. Các cách đánh giá kích thước

- **So sánh tương đối:** story này lớn hơn/nhỏ hơn một lát tương tự đã làm?
- **Story points:** một cách đo tương đối nội bộ nếu nhóm chọn; không phải giờ và không được so sánh máy móc giữa nhóm.
- **T-shirt sizing:** XS/S/M/L để xác định story nào cần chia nữa.
- **Không dùng points:** một nhóm Kanban có thể dự báo từ throughput/cycle time lịch sử và đặc tính work item.
- **Phân tách rủi ro:** nếu ước lượng cao do hợp đồng chưa biết, cần làm rõ rủi ro, không đơn giản cộng thêm points.

### 27.2. Forecast dựa trên điều kiện

Một báo cáo hữu ích:

> “Nhóm dự kiến có thể hoàn tất CONT-01 trong chu kỳ tới nếu API quyền và môi trường kiểm thử sẵn sàng; còn quy tắc video đổi phiên bản phải được chốt trước khi mở rộng. Nếu phụ thuộc không sẵn, chúng tôi sẽ cập nhật forecast và thảo luận thứ tự Product Backlog.”

Nó có **giả định, giới hạn và lựa chọn thích ứng**. Không nên biến “5 points” thành “chắc chắn 5 ngày”.

### 27.3. Một lát có thể nhỏ về code nhưng lớn về kiểm chứng

Có chức năng chỉ vài dòng thay đổi nhưng cần kiểm tra cạnh tranh ghi, quyền, migration dữ liệu hoặc hợp đồng đối tác. Khi đánh giá khả năng Done, phải tính **mọi công việc chất lượng áp dụng**, không chỉ số dòng code.

### 27.4. Không dùng points làm hạn ngạch cá nhân

Nếu ép mỗi Developer đạt 20 points, nhóm có thể chia ticket vụn, hạ mức kiểm thử hoặc né hỗ trợ đồng đội. Dữ liệu ước lượng nên phục vụ **ra quyết định phạm vi và dự báo**, không xếp hạng năng lực cá nhân.

## 28. Phụ thuộc liên nhóm và quyết định trong user story

Một story nhỏ vẫn có thể bị chặn vì:

- API Identity cần xác nhận quyền.
- Video player có contract vị trí khác.
- Thiết kế trạng thái lỗi cần UX thống nhất.
- Chính sách lưu dữ liệu và thời hạn giữ cần người có thẩm quyền.
- Test environment không có dữ liệu video phù hợp.
- Contract cũ của mobile client chưa thể đổi ngay.

### Một dependency card ngắn

~~~text
DEPENDENCY: DEP-CONT-01-IDENTITY

Story: CONT-01
Cần: Hợp đồng xác minh quyền xem/lưu tiến độ video.
Câu hỏi: Token hết quyền phải trả trạng thái nào?
Consumer: Nhóm Learning.
Provider/owner: Nhóm Identity theo phân công.
Bằng chứng: Contract proposal, failing integration test.
Tác động: Không thể kiểm AC quyền và DoD.
Next action: Identity xác nhận contract; Learning chạy lại test.
Checkpoint: Theo working agreement của hai nhóm.
Escalation: Đầu mối có thẩm quyền nếu rủi ro tăng/quá hạn.
~~~

**Blocked** phải nêu lý do, hành động và owner, không chỉ gắn nhãn “đang chờ backend”.

### 28.1. Thảo luận khi phụ thuộc còn quá lớn

Có thể đổi thứ tự lát, làm spike hoặc giảm phạm vi nội dung để tích hợp một đường thật. Không được tạo API giả cố định rồi báo full Increment Done khi hợp đồng thật là điều kiện cần thiết cho hành vi đã cam kết.

### 28.2. Quyết định phải có hiệu lực và phạm vi

Nếu PO thay quy tắc “chưa có tiến độ” giữa Sprint, cần cập nhật AC/test và trao đổi tác động Sprint Goal/DoD. Không chỉ gửi tin nhắn riêng rồi để mỗi người làm theo một phiên bản.

## 29. Đưa story đã refine vào Scrum một cách đúng nghĩa

Nếu nhóm áp dụng Scrum đầy đủ:

- **Product Owner** chịu trách nhiệm tối đa hóa giá trị và Product Backlog, gồm sắp thứ tự PBI.
- **Developers** chịu trách nhiệm tạo Increment đáp ứng Definition of Done và tự quản kế hoạch thực hiện.
- **Scrum Master** chịu trách nhiệm về hiệu quả Scrum và hỗ trợ tháo trở ngại.
- **Product Goal** là commitment của Product Backlog.
- **Sprint Goal** là commitment của Sprint Backlog.
- **Definition of Done** là commitment của Increment.

### 29.1. Sprint Planning

PO cùng Developers trao đổi **vì sao Sprint có giá trị**; Scrum Team xác định Sprint Goal. Developers chọn PBIs cho Sprint trong bối cảnh năng lực và DoD rồi lập kế hoạch cách tạo Increment.

**Ví dụ Sprint Goal:**

> “Học viên đã đăng nhập có thể quay lại một video Java từ vị trí đã lưu, với phản hồi lỗi và quyền truy cập đáng tin.”

Nhóm có thể chọn CONT-01 cùng các tasks để đạt mục tiêu; không biến “đóng 25 story points” thành Sprint Goal.

### 29.2. Daily Scrum

Daily Scrum là sự kiện 15 phút của Developers để kiểm tra tiến độ hướng Sprint Goal và điều chỉnh Sprint Backlog. Nếu CONT-01 bị blocked vì quyền, sự kiện giúp nhìn tác động và quyết định bước phối hợp; không phải cuộc đọc báo cáo phần trăm từng cá nhân cho quản lý.

### 29.3. Sprint Review

Sprint Review xem kết quả, bối cảnh, Increment và phản hồi với stakeholders, rồi thích ứng Product Backlog. Không phải một cổng release bắt buộc. Increment đạt DoD có thể bàn giao sớm hơn khi điều kiện phát hành phù hợp.

### 29.4. Sprint Retrospective

Nhóm xem cách refinement, story slicing, acceptance examples và kiểm thử có giúp ít rework hơn không. Chọn một cải tiến thực tế như **example mapping trước khi kéo PBI rủi ro cao**, đo kết quả ở các chu kỳ tiếp theo.

### 29.5. Story chưa đạt DoD không được tính vào Increment

Dù UI đã hiển thị nút Resume, nếu lưu vị trí chưa tích hợp hoặc test quyền thất bại, **không coi story hoàn thành** chỉ vì đã đi tới ngày Sprint cuối. Cần minh bạch trạng thái thật và thích ứng.

## 30. Trong Kanban: story thành work item có quy tắc luồng rõ

Một nhóm dùng Kanban có thể không tổ chức Sprint. Các stories vẫn có ích để diễn đạt giá trị; bảng Kanban giúp nhìn **dòng công việc, WIP và điểm nghẽn**.

~~~text
Product Goal: Học viên quay lại bài học dễ dàng

Ready -> Develop (WIP <= 3) -> Review (WIP <= 2)
                                  |
                                  v
                              Verify -> Done

CONT-01  Verify   - Resume một video, chờ auth negative test
CONT-02  Ready    - Đường vào bài dở của khóa
CONT-03  Blocked  - Quy tắc xung đột đa thiết bị chưa rõ
CONT-04  Idea     - Autosave sau khi phản hồi CONT-01
~~~

Giới hạn WIP là **ví dụ**, không phải con số tiêu chuẩn. Nhóm cần **Definition of Workflow** với Started/Finished, trạng thái, chính sách WIP và blocked rõ.

### 30.1. User story không tự biến mọi work item thành giống nhau

Kanban có thể quản lý bug, risk reduction, technical debt và support requests bên cạnh stories. Cần chính sách phân loại, nhưng không giả gắn “người dùng” lên một việc kỹ thuật thuần để trông giống user story.

### 30.2. Flow metrics để kiểm tra việc chia lát

- **Cycle time:** từ Started tới Done theo ranh giới được định nghĩa.
- **Throughput:** số work items Done trong một khoảng.
- **WIP:** số việc đã bắt đầu nhưng chưa xong.
- **Work item age:** tuổi của việc đang dở.
- **Blocked time:** thời gian chờ nguyên nhân cụ thể khi được ghi đáng tin.

Nếu chia lát tốt, **work item có thể hoàn tất và nhận feedback đều hơn**. Nhưng nếu nhóm chỉ đổi cách chia ticket, số throughput tăng không tự chứng minh giá trị tăng.

## 31. Bàn giao, phát hành và phản hồi: story Done chưa kết thúc học hỏi

Một story được chấp nhận theo các AC và đạt DoD **chưa có nghĩa người dùng thật đã trải nghiệm**. Nên phân biệt:

| Mốc | Ý nghĩa |
| --- | --- |
| **Done** | Increment đạt Definition of Done và có thể sử dụng. |
| **Deployed** | Phiên bản có mặt trên môi trường tương ứng. |
| **Released** | Khả năng đã mở cho nhóm người dùng xác định. |
| **Feedback observed** | Nhóm có dữ liệu hoặc nhận xét thực để kiểm tra giả thuyết giá trị. |

### 31.1. Kế hoạch phản hồi sau CONT-01

**Giả thuyết:** học viên giảm thời gian tìm lại vị trí video khi có Resume.

**Phép thử có thể dùng:**

1. Mời nhóm học viên được phép và có thông tin thử nghiệm phù hợp.
2. Cho họ xem một video, dừng ở khoảng giữa, rời trang.
3. Yêu cầu quay lại và tiếp tục mà không chỉ dẫn chi tiết.
4. Quan sát liệu họ tìm được đường Resume, có hiểu trạng thái lưu không.
5. Ghi phản hồi ngôn ngữ của học viên và những khó khăn.
6. Theo dõi lỗi kỹ thuật, từ chối quyền và trạng thái ghi thất bại.
7. PO cùng nhóm đánh giá: cải thiện CONT-01, ưu tiên CONT-02 hay chuyển sang vấn đề khác?

### 31.2. Chọn số đo có định nghĩa

Ví dụ:

- **Task success:** tỷ lệ học viên hoàn thành tác vụ quay lại đúng video/vị trí trong bối cảnh thử có quy tắc rõ.
- **Task completion time:** thời gian từ yêu cầu quay lại tới lúc tiếp tục video, đo nhất quán.
- **Error rate:** tỷ lệ thao tác ghi thất bại theo định nghĩa request và cửa sổ đo.
- **Support contact:** số tình huống phải hỏi hỗ trợ, có phân loại nguyên nhân.
- **Qualitative feedback:** người dùng mô tả điều gì khiến họ khó hiểu.

Nếu nhóm chỉ thử với vài người, đó có thể là **bằng chứng khám phá**, không đủ để tuyên bố tỷ lệ thành công toàn bộ người học.

### 31.3. Phản hồi có thể khiến lát tiếp theo thay đổi

Nếu người học vẫn không tìm thấy bài dở, CONT-02 có thể được đẩy lên trước CONT-03. Nếu họ quan tâm nhiều tới quiz hơn video, Product Backlog có thể đổi. **Mục tiêu của chia lát là cho phép học và thay đổi lựa chọn trước khi xây toàn bộ epic**.

### 31.4. Feature flag không thay chất lượng

Bật cho một cohort nhỏ có thể giới hạn phạm vi ảnh hưởng, nhưng không hợp thức hóa lỗi phân quyền đã biết hoặc dữ liệu bị hỏng. Tắt flag cũng không tự sửa bản ghi sai. Cần **DoD, điều kiện release, giám sát và kế hoạch khôi phục** tương xứng.

## 32. Tổ chức workshop thực hành tích hợp trong một buổi

Đây là một **kịch bản 90–120 phút minh họa**, có thể rút ngắn/mở rộng theo kinh nghiệm nhóm và mức độ phức tạp.

### 32.1. Vai trò mô phỏng

| Vai | Trách nhiệm trong workshop |
| --- | --- |
| **Người đóng vai học viên** | Mô tả trải nghiệm, nhu cầu, khó khăn không cần biết giải pháp kỹ thuật. |
| **Product Owner** | Nêu Product Goal, sắp thứ tự giá trị, làm rõ quy tắc trong quyền. |
| **Developers** | Khám phá tính khả thi, phụ thuộc, cách chia lát và DoD. |
| **QA/người kiểm chứng** | Đưa trường hợp thành công, lỗi, biên và quyền. |
| **UX/giảng viên** | Kiểm tra ngôn ngữ, hành trình và cách tiếp cận. |
| **Facilitator/Scrum Master nếu dùng Scrum** | Giúp trao đổi có mục đích, ghi câu hỏi và trở ngại, không chốt thay các vai có quyền. |

Một người có thể đóng nhiều vai trong workshop học tập, nhưng cần **nói rõ đó là mô phỏng** để không nhập nhằng thẩm quyền trong dự án thật.

### 32.2. Lịch thực hành

| Giai đoạn | Thời lượng minh họa | Hoạt động | Đầu ra |
| --- | --- | --- | --- |
| **Khởi động** | 10 phút | Đọc bối cảnh, Product Goal, vấn đề người dùng. | Giả thuyết giá trị và phạm vi. |
| **Viết card** | 10 phút | Viết 2–3 story cards, nhận phản biện. | Card được sửa. |
| **Conversation** | 20 phút | Role-play 3C, hỏi về quyền/lỗi/biên và quyết định. | Rule–Example–Question. |
| **Story map** | 15 phút | Vẽ hành trình và biến thể. | Map và đường end-to-end. |
| **Chia lát** | 15 phút | Đề xuất 3–5 lát, dùng INVEST và ưu tiên. | Backlog lát dọc ứng viên. |
| **Acceptance criteria** | 15 phút | Chọn lát đầu, viết testable criteria và Gherkin. | AC + scenario set. |
| **Review chéo** | 10 phút | Nhóm khác tìm lỗ hổng hoặc mâu thuẫn. | Câu hỏi/sửa criteria. |
| **Kế hoạch giao và feedback** | 10 phút | Liên kết DoD, thử nghiệm và bước kế. | Plan ngắn, owner. |

Tổng thời gian minh họa là 105 phút. Không cần sử dụng stopwatch cứng nếu mục tiêu học tập cần trao đổi thêm. Phần quan trọng là **mỗi vòng tạo một đầu ra có thể kiểm tra**.

### 32.3. Luật thảo luận

- Hỏi “vì sao” trước khi đề xuất giải pháp.
- Nêu ví dụ cụ thể thay vì chỉ tranh luận tính từ.
- Đừng biến câu hỏi chưa trả lời thành điều kiện đã chốt.
- Không đổ lỗi khi người khác phát hiện một trường hợp biên.
- Ưu tiên một lát sử dụng được thay vì danh sách task hoàn tất giả.
- Giữ quyền, tính đúng đắn và DoD.
- Cuối buổi phải rõ **ai làm gì tiếp, ai quyết điều gì và ở đâu lưu**.

## 33. Mẫu thực hành: từ card tới confirmation

Bạn có thể dùng mẫu sau ngay trong một PBI hoặc tài liệu làm việc nhỏ, không cần tạo nhiều bản sao.

~~~text
STORY-ID:
Tên ngắn:

CARD:
  Là [người hưởng lợi và bối cảnh],
  tôi muốn [hành vi],
  để [giá trị].

LIÊN KẾT MỤC TIÊU:
  Product Goal / Sprint Goal / mục tiêu luồng:

CONVERSATION:
  Những fact đã quan sát:
  Assumptions chưa xác nhận:
  Rules đã chốt:
  Examples phân biệt các hành vi:
  Questions còn mở + owner + checkpoint:
  Decisions có hiệu lực + link:
  Phụ thuộc và rủi ro:

PHẠM VI LÁT:
  Có trong lát này:
  Chủ động chưa làm:
  Cách kiểm soát quyền/dữ liệu/chất lượng:

CONFIRMATION:
  AC-01:
  AC-02:
  AC-03:
  Success scenario:
  Error scenario:
  Boundary/security scenario khi áp dụng:

DELIVERY:
  Definition of Done tham chiếu:
  Tests/evidence dự kiến:
  Bước tiếp hoặc người cần trả lời:
  Cách đánh giá Increment:

FEEDBACK:
  Nhóm người dùng được phép:
  Giả thuyết giá trị:
  Số đo/quan sát:
  Điều kiện đổi ưu tiên:
~~~

Nếu một story rất nhỏ, một card, vài ví dụ và link DoD có thể đủ. Mẫu này **không phải bộ trường bắt buộc** cho mọi story trong Scrum.

## 34. Đánh giá chéo: phản biện story của nhóm khác

Khi nhận story của một nhóm khác, đừng chỉ kiểm “có đủ As a/I want/So that”. Hãy hỏi:

1. **Giá trị:** nếu Done, ai thực sự làm được điều mới?
2. **Khả năng sử dụng:** có đường end-to-end hay chỉ một phần kỹ thuật?
3. **Biến thể:** story đang chứa bao nhiêu hành vi khác nhau?
4. **Điều chưa rõ:** những giả định nào có thể làm sai toàn bộ giải pháp?
5. **AC:** có đầu vào, hành động và kết quả kiểm tra được?
6. **Lỗi/biên:** đã xét failure, first-time, retry, dữ liệu không hợp lệ chưa?
7. **Quyền:** có đường truy cập trái quyền nào có thể bị bỏ sót?
8. **DoD:** có khả năng tích hợp/kiểm thử trong chu kỳ không?
9. **Phụ thuộc:** ai cần trả lời hoặc quyết?
10. **Phản hồi:** sau release, học được điều gì về nhu cầu?
11. **Thứ tự:** có một lát nhỏ hơn mà vẫn hữu ích?
12. **Ngôn ngữ:** người không dự Conversation có hiểu bối cảnh và quyết định?

### 34.1. Mẫu phản hồi xây dựng

**Không hữu ích:** “Story này không INVEST, viết lại.”

**Hữu ích:**

> “Card có người dùng và giá trị rõ nhưng gộp resume video với đồng bộ offline. Hai hành vi có rủi ro khác nhau. Đề xuất lát đầu cho video online có quyền và xử lý lỗi ghi; offline là story sau. AC hiện chưa nói trường hợp chưa có vị trí và yêu cầu sai quyền. Nhóm có thể bổ sung hai ví dụ và xác định người chốt rule về vị trí vượt thời lượng.”

Điều đó giúp nhóm **cải thiện story**, không chỉ nhận đánh giá đạt/trượt.

## 35. Xử lý xung đột trong Conversation

Không phải ai cũng đồng ý ngay. Một số bất đồng thực sự là **khác mục tiêu hoặc quyền quyết định**, không thể giải bằng thêm Gherkin.

### Tình huống 1 — PO muốn nhiều chức năng, Developers thấy quá lớn

PO: “Cần offline, dashboard và đa thiết bị ngay.”

Developers: “Một lát này có nhiều rủi ro, không thể chắc đạt DoD trong chu kỳ.”

**Cách xử lý:** cùng chỉ ra hành vi nào tạo giá trị trước, phơi bày rủi ro, chia thành các lát có thể dùng, nêu forecast và cách kiểm chứng. PO chịu trách nhiệm thứ tự giá trị; Developers tự quản cách thực hiện và chất lượng. Không ép nhóm hứa phạm vi bằng cách thay estimate thành deadline.

### Tình huống 2 — QA và Developer bất đồng về retry

QA: “Gửi lại request không được tạo trạng thái sai.”

Developer: “Hệ thống có thể xử lý hai request gần đồng thời.”

**Cách xử lý:** làm rõ contract request identity, chính sách ghi, kịch bản concurrency, bằng chứng test và ranh giới transaction. Đưa vào AC/DoD theo rủi ro. Không coi hai câu nói đối lập là lỗi cá nhân.

### Tình huống 3 — UX và PO khác nhau về thông báo lỗi

UX muốn “Lưu tạm trên thiết bị”; PO muốn “Đã lưu” dù chưa lên server.

**Cách xử lý:** phân biệt **lưu cục bộ** và **đã đồng bộ server**; kiểm tra hệ thống thật có hỗ trợ lưu cục bộ không và ngôn ngữ nào không đánh lừa người dùng. Quyết định trong phạm vi thẩm quyền, ghi ví dụ lỗi và xem trải nghiệm với học viên.

### Tình huống 4 — Stakeholder muốn xem tiến độ học viên ngoài quyền

Phải làm rõ chính sách quyền, mục đích, nghĩa vụ riêng tư và người có thẩm quyền. Không bổ sung một AC cho phép truy cập trái quyền chỉ vì một stakeholder cấp cao yêu cầu trong workshop.

### Tình huống 5 — Một nhóm không dự được do múi giờ

Ghi rule, example, question và proposed decision ở nguồn chung; cho người bị ảnh hưởng góp ý bất đồng bộ. Sau khi chốt, thông báo **quyết định có hiệu lực và link**. Không xem sự im lặng là phê duyệt khi cần thẩm quyền chính thức.

## 36. Bài tập tổng hợp: từ yêu cầu “làm hệ thống thi Java” đến lát có thể bàn giao

Một Product Owner của nền tảng học Java nhận yêu cầu:

> “Trước đợt khai giảng tiếp theo, chúng ta cần hệ thống thi cuối khóa thật đầy đủ: trắc nghiệm, câu hỏi viết mã, bảng xếp hạng, tự chấm, nộp lại khi mất mạng, chứng nhận PDF, email thông báo và thống kê cho giảng viên.”

Nhóm có nhiều ý kiến khác nhau:

- Giảng viên nói học viên cần biết **mình sai ở đâu**.
- Nhóm hỗ trợ cho biết có học viên **không rõ bài đã được nộp thành công hay chưa**.
- Developers biết dịch vụ gửi email có thể timeout; hợp đồng retry chưa rõ.
- QA phát hiện hai request nộp cùng lần thi có thể cùng được ghi.
- Product Owner nghĩ việc mở tính năng cho **một lớp nhỏ** sẽ đủ an toàn để lấy phản hồi.
- Nhóm bảo mật hỏi ai được phép **đọc kết quả của học viên khác**.
- Một stakeholder muốn **bảng xếp hạng** xuất hiện trước vì dễ trình diễn.
- Ngày khai giảng là một mốc thực, nhưng phạm vi bắt buộc theo hợp đồng chưa được xác nhận.
- Nhóm có Sprint hai tuần; một số thành viên làm việc từ múi giờ khác.
- Bảng công việc hiện chia theo các mục “database”, “backend”, “frontend”, “test” và “release”.

### 36.1. Dữ kiện bổ sung cho mô phỏng

Giả sử:

1. Học viên đăng nhập vào một khóa Java và có thể được phép hoặc không được phép làm bài thi cuối khóa.
2. Bài trắc nghiệm đầu tiên có mười câu, mỗi câu một đáp án đúng; cách tính điểm một số trường hợp đặc biệt chưa được chốt.
3. Nền tảng hiện có cơ chế đăng nhập và danh sách khóa học; chính sách quyền chi tiết vẫn phải kiểm chứng.
4. Hệ thống chưa có giao dịch nộp bài được thiết kế bảo đảm idempotency.
5. Học viên dùng cả điện thoại và laptop, nhiều người có kết nối mạng không ổn định.
6. Nhóm chưa có dữ liệu đáng tin về nhu cầu bảng xếp hạng và email chứng nhận.
7. Bảo mật, tính đúng đắn điểm, điều kiện cấp chứng nhận và quyền riêng tư là ràng buộc phải giữ trong mọi lát có liên quan.
8. Việc phát hành cho lớp học thật cần quyết định đúng thẩm quyền của tổ chức.
9. Không được tự suy ra rằng mười câu trắc nghiệm có thể áp dụng cùng một rule cho việc chấm code.
10. Đầu ra của workshop là một **đề xuất**, không tự được coi là thỏa thuận sản phẩm thật khi người có quyền chưa xác nhận.

### 36.2. Nhiệm vụ A — Khám phá nhu cầu

1. Viết **một Product Goal** theo kết quả học viên có thể quan sát.
2. Phân biệt ít nhất **bốn fact, bốn assumptions và bốn questions** cần giải đáp.
3. Chỉ ra những mục trong yêu cầu ban đầu **là giải pháp hoặc ý tưởng**, chưa chứng minh giá trị.
4. Đề xuất ba câu hỏi muốn hỏi trực tiếp học viên/giảng viên trước khi chốt ưu tiên.
5. Tạo một **story card ban đầu** cho yêu cầu lớn, chỉ rõ vì sao nó chưa phù hợp để thực hiện nguyên khối.
6. Ghi những **quyết định cần PO, người sở hữu nghiệp vụ hoặc thẩm quyền khác** giải quyết.

### 36.3. Nhiệm vụ B — Conversation và story map

7. Mô phỏng một cuộc trao đổi 3C có PO, Developer, QA và người hiểu nghiệp vụ; ghi tối thiểu **ba rules, năm examples, ba open questions**.
8. Lập story map theo hành trình **mở bài → trả lời → nộp → nhận kết quả → xem lại → tiếp tục học**.
9. Chia epic thành **ít nhất bốn lát dọc**, mỗi lát có **người hưởng lợi và hành vi có thể sử dụng**.
10. Xác định **lát đầu** và những chức năng cố ý chưa làm; giải thích cách chọn theo giá trị và rủi ro.
11. Chỉ ra **hai cách chia ngang sai**, rồi sửa thành lát dọc phù hợp.
12. Đánh giá lát đầu theo **INVEST**, nêu điều nào còn chưa đạt hoặc cần làm rõ.

### 36.4. Nhiệm vụ C — Confirmation

13. Viết **ít nhất sáu acceptance criteria** cho lát đầu, bao gồm happy path, lần đầu/biên, timeout/retry, phân quyền và trạng thái thật.
14. Viết **ít nhất ba scenarios Given–When–Then** cho các trường hợp có hành vi khác nhau.
15. Phân biệt **AC của lát đầu** với **DoD chung**, nêu năm điều kiện chất lượng cần kiểm tra.
16. Chọn tầng kiểm chứng cho mỗi tiêu chí: unit, integration, contract, security, usability hoặc vận hành.
17. Cho biết điều gì **không được tách sang story sau** chỉ để giảm size hoặc đạt velocity.

### 36.5. Nhiệm vụ D — Kế hoạch delivery và học hỏi

18. Viết **Sprint Goal** phù hợp nếu dùng Scrum.
19. Lập một đoạn bàn giao/phụ thuộc cho dịch vụ email hoặc chính sách quyền còn chưa rõ.
20. Phân biệt **Done, Deployed, Released, Feedback Observed** trong kịch bản ra mắt cho một lớp.
21. Chọn hai flow metrics, hai quality guardrails, một outcome metric và một kênh feedback định tính.
22. Phản hồi đề xuất “bật cho 5% người dùng khi chưa đạt kiểm thử quyền”.
23. Nếu người học thử cho rằng **lời giải thích đáp án sai** hữu ích hơn bảng xếp hạng, hãy đề xuất thay đổi Product Backlog và cách thông báo quyết định.
24. Đề xuất một cải tiến trong Retrospective khi nhóm liên tục tranh luận lại rule sau khi code đã merge.

**Yêu cầu chất lượng bài làm:** không cần đoán một rule chưa được chốt; khi đưa ra lựa chọn minh họa, hãy ghi **“giả định đã được xác nhận trong mô phỏng”** hoặc **“cần quyết định”**. Bài làm tốt thể hiện cả **giá trị, rủi ro, người có quyền và bằng chứng**, không chỉ đủ số câu.

## 37. Hướng giải tham khảo cho bài tập tổng hợp

Đây là **một phương án hợp lý**, không phải đáp án duy nhất. Một nhóm có thể chọn lát khác nếu giải thích thuyết phục về giá trị, rủi ro, tính độc lập và DoD.

### 37.1. Product Goal và thông tin cần kiểm chứng

**Product Goal ứng viên:**

> “Giúp học viên đủ điều kiện hoàn thành một bài đánh giá Java và nhận kết quả chính xác, dễ hiểu, an toàn; từ đó họ biết cần học tiếp phần nào.”

Mục tiêu này không cam kết ngay bảng xếp hạng, AI chấm code, email hay toàn bộ thống kê. Những chức năng đó có thể được ưu tiên sau khi xác nhận nhu cầu và nghĩa vụ.

| Fact trong tình huống mô phỏng | Assumption chưa đủ bằng chứng | Question cần trả lời |
| --- | --- | --- |
| Nền tảng có đăng nhập và danh sách khóa. | Mọi học viên cần bảng xếp hạng. | Học viên cần nhìn điều gì ngay sau nộp bài? |
| Học viên dùng nhiều thiết bị. | Offline nộp bài là bắt buộc ở release đầu. | Khi timeout, người học cần biết trạng thái thế nào? |
| Hợp đồng retry email chưa rõ. | Email chứng nhận quan trọng hơn trang xem kết quả. | Mốc khai giảng bắt buộc những khả năng nào? |
| Hai request có thể cùng được ghi trong đường hiện tại. | Quy tắc retake sẽ giống mọi khóa học. | Một lần nộp được xác định bằng ID và điều kiện nào? |
| Một số học viên không rõ đã nộp chưa theo hỗ trợ. | Học viên hiểu “Đang xử lý” giống ý nhóm. | Khi mất mạng mà server đã ghi, UI nên kiểm tra lại ra sao? |
| Có yêu cầu giới hạn quyền theo vai trò. | Giảng viên có quyền xem mọi kết quả trên toàn hệ thống. | Ai có quyền xem/sửa/thu hồi kết quả theo lớp? |

**Phân biệt:** lời “hai request có thể cùng được ghi” là tín hiệu lỗi có cơ sở trong mô phỏng; nếu kiểm thử cho thấy đã ghi trùng thực, đó là **issue/defect**, không chỉ giả định rủi ro.

### 37.2. Ba câu hỏi với học viên và giảng viên

1. “Lần cuối nộp bài mà mạng chậm, bạn đã làm gì để biết bài được ghi chưa? Bạn lo điều gì nhất?”
2. “Sau khi xem điểm, điều gì giúp bạn quyết định học tiếp: số điểm, câu sai và lời giải, chứng nhận hay vị trí so sánh với người khác?”
3. “Trong trường hợp học viên được phép nộp lại, quy tắc nào về lần nộp, thời hạn và kết quả cuối phải áp dụng?”

Cần hỏi thêm đơn vị sở hữu hợp đồng về phạm vi tối thiểu trước mốc khai giảng, bộ phận có thẩm quyền về quyền dữ liệu và đội tích hợp về khả năng đối tác.

### 37.3. Card lớn ban đầu

> Là học viên Java, tôi muốn làm bài cuối khóa, nhận điểm, chứng nhận và các thông tin liên quan để biết kết quả học của mình.

Card này quá lớn vì gồm **nhiều outcome** và rủi ro: nộp, tính điểm, lưu lịch sử, cấp chứng nhận, email, thống kê và quyền. Theo INVEST, nó chưa Small, chưa đủ Estimable và chưa có Confirmation rõ.

### 37.4. Example mapping mẫu

| Rule | Example | Question |
| --- | --- | --- |
| Học viên đủ quyền mới được nộp. | Không có quyền → bị từ chối, không ghi điểm. | Ai định nghĩa quyền theo khóa và kỳ thi? |
| Một yêu cầu nộp hợp lệ không tạo bản ghi trùng trái rule. | Retry requestId cũ → cùng kết quả logic, không duplicate. | Một lần nộp có được phép sửa đáp án sau khi ghi không? |
| Chỉ xác nhận đã nộp khi trạng thái được biết. | Timeout chưa xác nhận → UI không báo chắc chắn thành công. | Phải kiểm tra lại bằng token nào và sau bao lâu? |
| Học viên xem được kết quả của chính mình. | Đăng nhập đúng → xem điểm trong phạm vi được phép. | Bao giờ hiển thị đáp án và lời giải? |
| Bài có đáp án được chấm theo rule thống nhất. | 8 đúng/10 câu → điểm theo công thức đã chốt. | Có điểm phạt, câu nhiều đáp án hoặc thời gian không? |
| Kết quả không lộ cho người khác. | Truy cập attemptId của học viên khác → bị từ chối. | Giảng viên được xem theo phạm vi nào? |

**Open questions ưu tiên:** quyền; idempotency/retake; xử lý timeout; ngưỡng hoàn thành và công thức điểm. Những câu này ảnh hưởng trực tiếp tới lát đầu và nên được giải quyết trước khi gọi PBI đủ rõ.

### 37.5. Story map và các lát dọc

~~~text
HÀNH TRÌNH: Mở bài → Trả lời → Nộp → Nhận kết quả → Xem lại → Học tiếp

LÁT I1:
  Được phép → một loại trắc nghiệm → chọn đáp án → nộp an toàn
  → xem điểm chính xác và trạng thái thật
  (tích hợp, phân quyền, retry, lỗi và DoD trong phạm vi)

LÁT I2:
  Được phép → bài đã nộp → xem lại một kết quả đã lưu
  → nhận biết chính xác bài nào đã hoàn tất

LÁT I3:
  Kết quả đúng → xem lời giải cho một loại câu sai
  → biết phần kiến thức cần ôn

LÁT I4:
  Đủ điều kiện → nhận và xem một chứng nhận hợp lệ
  → không trùng và theo chính sách quyền

LÁT I5 / Ý TƯỞNG SAU:
  Email, bảng xếp hạng, bài viết mã, offline và thống kê nâng cao
  (ưu tiên theo phản hồi/điều kiện hợp đồng)
~~~

**Hai cách chia ngang sai:** “tạo toàn bộ database điểm” hoặc “xây toàn bộ backend thi” rồi gọi mỗi phần là story có giá trị. Chúng có thể là tasks cần làm, nhưng chưa tạo hành vi đầu cuối để học viên sử dụng.

### 37.6. Card cho lát I1

> Là học viên đã đăng nhập và được phép làm bài trắc nghiệm Java, tôi muốn nộp một bài có các câu hỏi được hỗ trợ và nhận kết quả đúng, để biết mình đã hoàn thành bài và cần học tiếp như thế nào.

**Phạm vi được chốt trong mô phỏng:** một loại câu hỏi một đáp án; quy tắc điểm đã được giảng viên/PO xác nhận; online; chưa có câu hỏi viết mã, offline hoặc email. **Không được bỏ** chính sách quyền, xử lý retry hợp lệ, tính đúng đắn và phản hồi lỗi.

### 37.7. Acceptance criteria I1

| Mã | Điều kiện kiểm chứng |
| --- | --- |
| **AC-01** | Học viên có quyền nộp một bài trắc nghiệm hợp lệ và nhận kết quả theo rule điểm đã chốt. |
| **AC-02** | Khi chưa chọn câu trả lời cho một câu, hệ thống xử lý theo rule bỏ trống đã xác nhận; không tự phỏng đoán điểm. |
| **AC-03** | Gửi lại một request đã xử lý không tạo kết quả trùng trái quy tắc và trả trạng thái phù hợp. |
| **AC-04** | Không có quyền làm bài → yêu cầu bị từ chối, không ghi kết quả. |
| **AC-05** | Không có quyền xem kết quả người khác → từ chối và không lộ dữ liệu. |
| **AC-06** | Khi server không thể xác nhận đã ghi kết quả, UI không báo sai rằng đã nộp thành công. |
| **AC-07** | Kết quả của một lần nộp có định danh rõ để người học có thể tra cứu trạng thái theo quyền nếu hợp đồng cho phép. |
| **AC-08** | Các trạng thái “Đang xử lý/Đã nộp/Chưa xác nhận” được trình bày hiểu được trong phạm vi UX đã thống nhất. |

**Chưa chốt trước:** cách tính điểm khi bỏ trống, chính sách retake và hành vi kiểm tra lại sau timeout. Chúng phải được làm rõ trong Conversation trước khi AC được coi là đủ dùng.

### 37.8. Gherkin mẫu

~~~gherkin
Feature: Nộp bài Java đúng và an toàn

Scenario: Học viên có quyền nộp một bài hợp lệ
  Given học viên "An" đã đăng nhập và được phép làm bài "Java 01"
  And bài có mười câu một đáp án đúng với quy tắc điểm đã chốt
  When An gửi lần nộp hợp lệ
  Then hệ thống ghi một kết quả theo quy tắc đã xác nhận
  And trả trạng thái nộp thành công chính xác
  And An có thể xem kết quả được phép của mình

Scenario: Request bị gửi lại sau một lần đã hoàn tất
  Given yêu cầu "req-100" của An đã được ghi thành công
  When cùng yêu cầu "req-100" được gửi lại
  Then hệ thống không tạo kết quả trùng trái quy tắc
  And kết quả phản hồi nhất quán theo hợp đồng retry

Scenario: Không có quyền xem kết quả
  Given học viên "Bình" không có quyền đọc kết quả của An
  When Bình yêu cầu kết quả nộp bài của An
  Then hệ thống từ chối theo chính sách
  And không tiết lộ điểm hoặc đáp án riêng tư của An

Scenario: Không thể xác nhận đã ghi
  Given An được phép nộp bài
  And hệ thống không thể xác nhận việc lưu kết quả
  When An gửi bài
  Then giao diện không báo chắc chắn rằng bài đã được nộp thành công
  And cung cấp trạng thái và bước kiểm tra/thử lại phù hợp
~~~

### 37.9. Phân biệt AC và DoD

**AC** xác nhận hành vi nộp, điểm, retry, quyền và thông báo trong **story I1**. **DoD** của Increment có thể yêu cầu thêm: code tích hợp, review, test suite phù hợp, không phá chức năng cũ, quản lý dữ liệu/log, khả năng quan sát lỗi, hướng dẫn hỗ trợ và các tiêu chuẩn bảo mật/tổ chức hiện hành.

TDD có thể hỗ trợ rule điểm; **integration tests** kiểm database/transaction/retry; **contract tests** kiểm UI/API; **negative security tests** kiểm quyền; **usability** kiểm trạng thái dễ hiểu. Không dùng unit tests xanh để tuyên bố toàn bộ luồng Done.

### 37.10. Sprint Goal, phụ thuộc và phát hành

**Sprint Goal ứng viên:**

> “Học viên được phép có thể nộp một bài trắc nghiệm Java trong phạm vi hỗ trợ và nhận trạng thái/kết quả chính xác, kể cả khi có yêu cầu lặp hoặc lỗi mạng.”

**Phụ thuộc:** chính sách quyền từ Identity và quyết định retake; mỗi phụ thuộc có câu hỏi, owner, deadline/checkpoint, bằng chứng và kế hoạch xử lý khi blocked.

**Mốc:**

- **Done:** Increment đạt DoD.
- **Deployed:** bản build có trên môi trường.
- **Released:** tính năng mở cho lớp có quyền sau khi đạt điều kiện và thẩm quyền.
- **Feedback observed:** có dữ liệu/quan sát học viên thật để điều chỉnh backlog.

**Đề xuất mở 5% khi chưa đạt test quyền:** không phù hợp. Quy mô nhỏ không hợp thức hóa lỗi có thể gây lộ dữ liệu. Phải sửa và kiểm chứng trước khi release.

### 37.11. Flow, outcome và cải tiến

**Flow metrics:** cycle time Started → Done; blocked time chờ rule/quyền hoặc review.

**Quality guardrails:** không ghi kết quả trùng trái quy tắc; không truy cập điểm trái quyền. Đồng thời theo dõi lỗi tính điểm và trạng thái thành công giả.

**Outcome:** tỷ lệ học viên hoàn thành một tác vụ nộp bài hợp lệ và hiểu trạng thái/kết quả theo định nghĩa thử rõ.

**Định tính:** quan sát học viên thử tác vụ khi mạng chậm trong môi trường được phép; hỏi họ hiểu “Đang xử lý”/“Đã nộp” và mong muốn bước tiếp theo là gì.

**Phản hồi ưu tiên:** nếu lời giải cho câu sai được chứng minh quan trọng hơn bảng xếp hạng, PO có thể ưu tiên I3 trước dashboard; cập nhật Product Backlog và thông báo lý do, không chỉ thay ticket trong chat riêng.

**Retrospective improvement:** tổ chức **example mapping cho stories có thay đổi quy tắc quan trọng** trước khi Developers bắt đầu; quan sát rework và lỗi do hiểu sai ở những chu kỳ sau.

## 38. Thang tự đánh giá sản phẩm workshop

Bài thực hành có thể được phản biện theo các tiêu chí dưới đây. Điểm chỉ để **người học tự nhìn chỗ cần cải thiện**, không phải hệ thống chấm hiệu suất cá nhân.

| Tiêu chí | Điểm gợi ý | Biểu hiện đạt tốt |
| --- | ---: | --- |
| **Giá trị và bối cảnh** | 15 | Product Goal, người dùng, khó khăn và outcome được diễn đạt rõ. |
| **Card và 3C** | 15 | Story không khóa giải pháp; Conversation ghi rule/example/question/decision đúng. |
| **Story map và lát dọc** | 20 | Có hành trình, các lát đầu cuối nhỏ, thứ tự và phạm vi chưa làm minh bạch. |
| **Acceptance criteria** | 20 | Tiêu chí kiểm thử được, có success/error/biên/quyền phù hợp, không mâu thuẫn. |
| **DoD và rủi ro** | 10 | Phân biệt AC/DoD, không bỏ chất lượng hoặc ràng buộc. |
| **Kế hoạch giao và feedback** | 10 | Sprint Goal/flow phù hợp, phụ thuộc, phản hồi và cách thích ứng rõ. |
| **Trao đổi, minh bạch quyết định** | 10 | Có câu hỏi mở, owner, quyết định có thẩm quyền và phản biện xây dựng. |
| **Tổng** | **100** | Nhận xét dựa trên sản phẩm thực hành và bằng chứng. |

### 38.1. Cách dùng thang điểm

- **Mức khởi đầu:** đủ mẫu câu nhưng còn nhiều giả định, lát kỹ thuật, AC khó test.
- **Mức đang phát triển:** nêu được outcome và vài lát dùng được, nhưng thiếu lỗi/biên/quyền hoặc cách nhận feedback.
- **Mức vững:** cả 3C, story map, AC, DoD, rủi ro và thứ tự đều có lý do rõ.
- **Mức nâng cao:** biết làm rõ thẩm quyền, trade-offs, dữ liệu phản hồi và khả năng đổi ưu tiên theo bằng chứng.

Không có tỷ lệ điểm nào thay thế review về **tính đúng đắn sản phẩm và an toàn dữ liệu**. Một bài đạt điểm cao nhưng cho phép đọc điểm trái quyền cần được sửa.

## 39. Những cách làm sai thường gặp khi thực hành user stories

| Anti-pattern | Vì sao gây hại? | Cách thay |
| --- | --- | --- |
| **Viết câu As a/I want/So that mà không Conversation.** | Đúng mẫu nhưng hiểu khác nhau. | Dùng 3C, example mapping và teach-back. |
| **Chọn “user” quá chung.** | Mơ hồ quyền và kết quả. | Xác định người hưởng lợi/bối cảnh. |
| **Story mô tả database hoặc endpoint.** | Khó thấy giá trị người dùng. | Đặt task dưới một lát hành vi đầu cuối. |
| **Một story ôm cả roadmap.** | Chưa Small/Testable, rủi ro dồn cuối. | Story mapping và chia biến thể. |
| **Chia ngang DB/API/UI/QA.** | Không có Increment có thể dùng cho tới cuối. | Chia lát dọc, giữ tasks kỹ thuật bên dưới. |
| **Chia story quá nhỏ, không có outcome.** | Tăng số ticket nhưng thiếu feedback giá trị. | Giữ lát nhỏ nhất có thể dùng và học. |
| **Chỉ viết happy path.** | Lỗi mạng, quyền và dữ liệu xuất hiện muộn. | Thêm examples cho rủi ro áp dụng. |
| **Bỏ kiểm tra quyền để giảm story size.** | Rủi ro lộ dữ liệu không hợp lệ. | Giảm tính năng, không giảm chất lượng. |
| **AC là câu “hệ thống phải tốt”.** | Không thể kiểm. | Nêu ngữ cảnh, hành động, kết quả. |
| **AC khóa thư viện/kiến trúc chưa cần.** | Giảm khả năng thương lượng và đổi thiết kế. | Ghi quyết định kỹ thuật riêng khi có cơ sở. |
| **Gherkin đầy đủ nhưng không có rule nghiệp vụ đúng.** | Tests xanh cho hành vi sai. | Trao đổi với người hiểu nhu cầu trước. |
| **Mọi question đều bị giả vờ đã quyết.** | Bất định bị ẩn, lỗi xuất hiện khi code. | Ghi open question/owner/checkpoint. |
| **AC trùng DoD hoặc cố thay DoD.** | Chất lượng chung bị phân mảnh. | Phân biệt behavior từng story với chuẩn Increment. |
| **Lấy story points làm Sprint Goal.** | Tối ưu output thay vì giá trị. | Sprint Goal hướng tới kết quả có nghĩa. |
| **Estimate bị biến thành deadline cá nhân.** | Khuyến khích che rủi ro và hạ DoD. | Forecast có giả định và quản lý scope. |
| **Story Ready là bất biến.** | Không thích ứng khi có thông tin mới. | Tiếp tục trao đổi và làm rõ tác động. |
| **Feedback chỉ là ký nghiệm thu.** | Không học về hành vi và giá trị người dùng. | Quan sát tác vụ và Product Goal sau release. |
| **Done được dùng cho code đã merge.** | Increment chưa tích hợp/đủ chuẩn. | Giữ Definition of Done và bằng chứng. |
| **Deployed bị báo là Released.** | Stakeholders tưởng người dùng đã có tính năng. | Tách trạng thái và cohort mở. |
| **Một quyền quyết định bị tự suy ra.** | Có thể bỏ yêu cầu bảo mật/pháp lý. | Xác định thẩm quyền tổ chức thực tế. |
| **Bài tập chỉ tính số stories được viết.** | Khuyến khích chia vụn và viết theo mẫu. | Đánh giá giá trị, khả năng kiểm chứng và feedback. |
| **Retrospective nói “viết story rõ hơn” rồi thôi.** | Không có cải tiến cụ thể. | Thử example mapping/peer review và đo rework. |

## 40. Tự kiểm tra kiến thức

**Câu 1.** Một user story có bắt buộc phải theo đúng ba vế “Là…, tôi muốn…, để…” không?

**Đáp án:** Không. Đó là mẫu hữu ích để nêu người hưởng lợi, hành vi và giá trị. Điều quan trọng là kích hoạt Conversation và có Confirmation kiểm chứng được.

**Câu 2.** 3C gồm gì và vì sao card ngắn chưa đủ?

**Đáp án:** Card – Conversation – Confirmation. Card là lời nhắc nhu cầu; trao đổi làm rõ quy tắc/rủi ro; confirmation xác nhận bằng ví dụ và tiêu chí có thể kiểm.

**Câu 3.** User story khác task kỹ thuật thế nào?

**Đáp án:** Story mô tả nhu cầu/năng lực tạo giá trị cho bên hưởng lợi, còn task là hoạt động để thực hiện giải pháp. Task xong chưa chắc có hành vi người dùng dùng được.

**Câu 4.** INVEST có yêu cầu story tuyệt đối không có phụ thuộc?

**Đáp án:** Không. Independent là hướng giảm phụ thuộc và khả năng hoàn tất riêng tương đối, không xóa phụ thuộc kiến trúc/thẩm quyền thực tế.

**Câu 5.** Vì sao “tạo DB rồi API rồi UI” thường không là chia lát dọc?

**Đáp án:** Từng phần chưa tạo hành vi đầu cuối cho người dùng; lỗi tích hợp và phản hồi bị dồn đến cuối.

**Câu 6.** Một lát chỉ hỗ trợ một loại video có thể là story hợp lệ không?

**Đáp án:** Có, nếu người dùng thực sự dùng được chức năng trong phạm vi đó, đạt DoD và giới hạn được truyền đạt rõ.

**Câu 7.** Có thể để kiểm tra quyền sang Sprint sau để làm story nhỏ hơn không?

**Đáp án:** Không nếu đó là điều kiện an toàn của hành vi hiện tại. Giảm phạm vi tính năng, không bỏ guardrails.

**Câu 8.** Acceptance criteria và Definition of Done khác nhau?

**Đáp án:** AC mô tả hành vi/điều kiện kiểm tra riêng của PBI; DoD là chuẩn chất lượng chung của Increment. Cả hai cùng cần thiết.

**Câu 9.** Tại sao “video phải tải nhanh” chưa phải AC tốt?

**Đáp án:** Thiếu ngưỡng, điều kiện và phương pháp đo. Cần làm rõ theo nhu cầu và quyết định, không bịa số.

**Câu 10.** Given–When–Then có tự động trở thành test chạy được?

**Đáp án:** Không. Cần step definitions, môi trường, dữ liệu thử và cách kiểm. Nó trước tiên giúp diễn đạt ví dụ có ngữ nghĩa chung.

**Câu 11.** Test đơn vị vị trí video có đủ gọi CONT-01 Done không?

**Đáp án:** Không. Còn tích hợp lưu/đọc, quyền, lỗi mạng, UI và DoD toàn sản phẩm.

**Câu 12.** Nếu PO và Developers hiểu khác về autosave, nên làm gì trước khi code?

**Đáp án:** Conversation với các ví dụ và rủi ro, xác định rule/phạm vi có thẩm quyền; tách autosave ra một story nếu phù hợp.

**Câu 13.** Khi nào story chưa đủ để chọn làm?

**Đáp án:** Khi chưa xác định được hành vi đúng, phụ thuộc/ràng buộc quan trọng không có cách xử lý hoặc kích thước/điều kiện hoàn tất quá mơ hồ.

**Câu 14.** Refinement có phải một sự kiện Scrum bắt buộc với thời lượng cố định?

**Đáp án:** Không. Đó là hoạt động liên tục làm rõ/chia nhỏ Product Backlog Items, được thực hiện khi có ích.

**Câu 15.** Tại sao không nên dùng story points làm Sprint Goal?

**Đáp án:** Points không mô tả giá trị hay hành vi người dùng. Sprint Goal cần một mục đích có ý nghĩa; estimates chỉ hỗ trợ forecast khi dùng phù hợp.

**Câu 16.** Một story đã Done nhưng feature flag còn tắt có phải Released không?

**Đáp án:** Không. Done là đạt DoD; Deployed là có trên môi trường; Released là mở cho nhóm người dùng đã xác định.

**Câu 17.** Nếu usability test cho thấy học viên không tìm được đường vào bài dở, nhóm nên làm gì?

**Đáp án:** Ghi bằng chứng, xem lại giả thuyết và để PO cân nhắc tăng ưu tiên lát tìm đường vào so với các tính năng ít giá trị hơn.

**Câu 18.** Vì sao cần ghi open questions và người có quyền quyết?

**Đáp án:** Để không biến giả định thành rule đã chốt, tránh mỗi thành viên thực hiện một phiên bản và bảo đảm điều kiện an toàn/tuân thủ được phê duyệt đúng thẩm quyền.

**Câu 19.** Một story có 20 AC chi tiết có luôn tốt hơn story có 5 AC rõ?

**Đáp án:** Không. Số lượng không tự tạo chất lượng. Cần độ phủ hành vi và rủi ro phù hợp, ngôn ngữ dễ hiểu, không lặp và có thể kiểm.

**Câu 20.** Vì sao phản hồi sau release vẫn quan trọng dù mọi acceptance tests đều xanh?

**Đáp án:** Tests cho biết hành vi được mô tả có được đáp ứng trong những điều kiện đã kiểm; không tự chứng minh người dùng cần hoặc hiểu tính năng đó. Phản hồi thực hỗ trợ quyết định ưu tiên tiếp theo.

## 41. Checklist cuối bài: story có thể bàn giao và học hỏi chưa?

### Nhu cầu và card

- [ ] Product Goal hoặc mục tiêu giá trị đã rõ.
- [ ] Có người dùng/bên hưởng lợi và bối cảnh cụ thể.
- [ ] Card nêu năng lực và giá trị, không chỉ giải pháp kỹ thuật.
- [ ] Story không gom quá nhiều outcome hoặc vai trò không liên quan.
- [ ] Task kỹ thuật được phân biệt với lát người dùng có thể sử dụng.

### Conversation

- [ ] Người có kiến thức nghiệp vụ và người xây/kiểm có cơ hội trao đổi.
- [ ] Có ví dụ thực tế, không chỉ những từ chung như “nhanh”, “dễ”.
- [ ] Fact, assumption, question và decision được phân biệt.
- [ ] Open questions có người trả lời và checkpoint.
- [ ] Quyết định quan trọng được ghi ở nguồn có thẩm quyền.
- [ ] Bảo mật, quyền, dữ liệu và rủi ro tích hợp được nêu khi áp dụng.
- [ ] Người không dự họp có thể đọc lại và hiểu ngữ nghĩa.

### Story mapping và slicing

- [ ] Có hành trình người dùng và một đường đi tối thiểu có giá trị.
- [ ] Các lát được chia dọc qua những lớp cần thiết.
- [ ] Mỗi lát tạo khả năng sử dụng và phản hồi có ý nghĩa.
- [ ] Những chức năng chưa làm được nêu minh bạch.
- [ ] Không hạ DoD/guardrails để tạo story nhỏ.
- [ ] Lát đầu được chọn vì giá trị, rủi ro và khả năng học.
- [ ] Có thể đổi thứ tự backlog theo bằng chứng mới.
- [ ] INVEST được sử dụng như bộ câu hỏi, không phải thủ tục máy móc.

### Acceptance và kiểm chứng

- [ ] AC nêu điều kiện, hành động và kết quả quan sát.
- [ ] Có happy path và biên/lỗi/quyền phù hợp rủi ro.
- [ ] Các quy tắc quan trọng đã được người có quyền xác nhận.
- [ ] Chưa bịa ngưỡng hiệu năng hay chính sách còn mở.
- [ ] Có example/Gherkin hoặc bảng quyết định khi hữu ích.
- [ ] Tầng tests phù hợp với điều cần chứng minh.
- [ ] AC và DoD không bị trộn hoặc dùng thay nhau.
- [ ] Increment mới tương thích với phần đã Done trước.

### Giao hàng và học hỏi

- [ ] Cách chọn vào Sprint hoặc flow đã rõ theo phương pháp nhóm dùng.
- [ ] Phụ thuộc/blocked có owner và bước tiếp.
- [ ] Sprint Goal nếu dùng Scrum nêu kết quả có ý nghĩa.
- [ ] Không coi story points/velocity là mục tiêu cá nhân.
- [ ] Done, Deployed và Released được báo cáo riêng.
- [ ] Cohort/thẩm quyền và điều kiện release được tôn trọng.
- [ ] Có phương pháp nhận phản hồi giá trị và chất lượng.
- [ ] Feedback quay lại Product Backlog và quyết định tiếp theo.
- [ ] Nhóm thử một cải tiến refinement/slicing nếu còn nhiều rework.

Checklist này là **công cụ học và ra quyết định**, không phải yêu cầu điền cùng một lượng thông tin vào mọi ticket. Câu chuyện nhỏ có thể cần ít ghi chép, nhưng vẫn phải làm rõ những điều **không được phép đoán hoặc bỏ qua**.

## 42. Tổng kết: câu chuyện tốt bắt đầu bằng trao đổi và kết thúc bằng bằng chứng

- **User story là lời mời trao đổi về một nhu cầu có giá trị**, không phải hợp đồng hoàn chỉnh và không phải task kỹ thuật đổi tên.
- **3C — Card, Conversation, Confirmation** giúp biến nhu cầu thành ví dụ và điều kiện có thể kiểm chứng.
- **Hỏi về người dùng, hoàn cảnh và outcome trước khi chọn database, API hoặc giao diện.**
- **Rule–Example–Question** làm lộ những điều mỗi bên hiểu khác, những giả định chưa xác nhận và quyết định cần owner.
- **INVEST giúp đặt câu hỏi về chất lượng story**, nhưng không xóa phụ thuộc thực tế, không bắt story points và không cho phép bỏ an toàn.
- **Story mapping cho thấy hành trình**, giúp chọn lát đầu cuối có thể dùng thay vì chia theo bộ phận kỹ thuật.
- **Lát nhỏ phải có giá trị, tích hợp và đạt DoD**; không tách lỗi mạng, dữ liệu sai hay quyền truy cập thành “việc tùy chọn sau”.
- **Acceptance criteria mô tả hành vi riêng của story** với success, failure, boundary và security khi phù hợp; **DoD bảo vệ chất lượng chung**.
- **Given–When–Then, bảng quyết định và tests** giúp Confirmation đáng tin nhưng không thay người hiểu nghiệp vụ hoặc phản hồi người dùng.
- **Refinement là hoạt động làm rõ liên tục**; Sprint/Kanban giúp điều phối, XP/TDD/CI giúp kiểm chứng kỹ thuật.
- **Done khác Deployed và Released**; sau khi release, nhóm còn cần quan sát để biết tính năng có giúp người dùng thật không.
- **Story tốt có thể được điều chỉnh khi bằng chứng mới xuất hiện**, không coi backlog ban đầu là kế hoạch không thể thay đổi.

Khi nhận một yêu cầu lớn, hãy bắt đầu bằng câu hỏi: **“Người dùng đang cần đạt điều gì, ví dụ nào chứng minh chúng ta hiểu đúng, và lát nhỏ nhất nào có thể giao an toàn để học từ phản hồi sớm?”**. Trả lời câu hỏi đó bằng một **card rõ, cuộc Conversation có ví dụ, acceptance criteria kiểm chứng được và Increment đạt DoD** chính là cách thực hành Agile có giá trị: giao sản phẩm tăng dần, giảm bất định và cải tiến liên tục.
