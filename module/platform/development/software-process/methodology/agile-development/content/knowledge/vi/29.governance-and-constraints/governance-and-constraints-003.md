# Quản lý rủi ro bằng bàn giao nhỏ cùng phản hồi sớm

Một nhóm phát triển nền tảng học Java được giao xây tính năng **thi trực tuyến và cấp chứng nhận hoàn thành khóa học**. Kế hoạch ban đầu kéo dài ba tháng: nhóm thiết kế toàn bộ ngân hàng câu hỏi, hệ thống chấm điểm, phát hành chứng nhận, phân quyền giảng viên, báo cáo và tích hợp nhà cung cấp gửi email, rồi mới cho học viên dùng. Đến tháng cuối, nhóm mới phát hiện ba vấn đề: học viên hiểu nhầm trạng thái nộp bài, việc gửi sự kiện hoàn thành bị lặp làm cấp hai chứng nhận, và một số tài khoản có thể truy cập kết quả của người khác.

Một cách ứng phó phản xạ là thêm nhiều cuộc họp phê duyệt, biểu mẫu và cổng kiểm tra cuối dự án. Những biện pháp đó có thể phát hiện một số lỗi, nhưng **không thay thế được việc kiểm chứng giả định khi còn dễ thay đổi**.

Nhóm có thể chọn cách khác: trước tiên giao một **lát nhỏ nhưng trọn vẹn** — học viên được phép làm một bài kiểm tra ngắn, nộp, nhận kết quả đúng và được bảo vệ dữ liệu — rồi thử trong phạm vi an toàn. Sau đó nhóm kiểm chứng luồng cấp chứng nhận qua một trường hợp thật, kiểm thử bản tin gửi trùng, mở dần nhóm học viên và theo dõi tỷ lệ lỗi, thời gian xử lý cùng trải nghiệm. Mỗi bước vừa tạo giá trị, vừa **làm rõ hoặc giảm một tập rủi ro cụ thể**.

Điểm then chốt: **bàn giao nhỏ không tự động giảm mọi rủi ro**. Một lỗi phân quyền nghiêm trọng có thể gây hại dù chỉ mở cho một người. Một hệ thống kiểm thử chưa đạt DoD không được hợp thức hóa chỉ vì muốn lấy phản hồi sớm. Quản lý rủi ro theo Agile là **xác định điều chưa biết, đưa bằng chứng đến sớm, giới hạn phạm vi tác động và duy trì những ràng buộc an toàn bắt buộc**.

Bài **“Quản lý rủi ro bằng bàn giao nhỏ cùng phản hồi sớm”** thuộc chương **Quản trị và ràng buộc** của module **AGILE_DEVELOPMENT**. Định hướng module là hiểu giá trị, nguyên tắc Agile qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc để lựa chọn cách phối hợp phù hợp. Trong bối cảnh đó, quản trị tốt không phải đối lập với Agile: **ràng buộc minh bạch và phản hồi nhanh là cách bảo vệ người dùng, ngân sách và giá trị khi điều kiện thay đổi**.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **rủi ro là sự bất định có thể ảnh hưởng mục tiêu**, khác với sự cố đã xảy ra, một giả định chưa kiểm chứng và một phụ thuộc.
2. Phân loại rủi ro **giá trị, khả năng sử dụng, kỹ thuật, chất lượng, bảo mật, dữ liệu, tuân thủ, tích hợp, vận hành và giao hàng**.
3. Chọn các **lát dọc nhỏ có thể sử dụng** để tạo Increment, giảm mức độ phơi nhiễm và học trước khi mở rộng đầu tư.
4. Phân biệt **prototype, spike, MVP, Increment đạt Definition of Done, deploy và release**, để không báo cáo sai mức độ hoàn tất.
5. Liên kết từng rủi ro với **giả thuyết, phương pháp kiểm chứng, bằng chứng mong muốn, người chịu trách nhiệm và quyết định tiếp theo**.
6. Thiết kế **release theo giai đoạn** với guardrails, feature flag, nhóm dùng thử, điều kiện dừng và kế hoạch phục hồi phù hợp.
7. Tích hợp kiểm soát **phân quyền, chất lượng, riêng tư, tương thích và truy vết** vào từng Increment, không đợi “giai đoạn tuân thủ cuối”.
8. Duy trì một **risk register/decision log gọn nhẹ**, cập nhật qua dữ liệu thật và phân biệt xử lý, chấp nhận rủi ro còn lại hoặc chuyển cấp.
9. Dùng Scrum, Kanban, XP và flow metrics để **giảm thời gian đến bằng chứng và xử lý điểm nghẽn**, không tối ưu số story points bằng mọi giá.
10. Thực hành thiết kế một lộ trình giao nhỏ, nhận phản hồi và báo cáo rủi ro cho sản phẩm cụ thể.

## 1. Rủi ro trong phát triển phần mềm là gì?

**Rủi ro (risk)** là ảnh hưởng không chắc chắn lên một hoặc nhiều mục tiêu. Nó có thể liên quan tới cơ hội cũng như tác động bất lợi; trong quản trị phát triển phần mềm, ta thường tập trung vào khả năng **không đạt giá trị, chất lượng, an toàn, thời điểm hoặc nghĩa vụ đã xác định**.

Ví dụ với nền tảng học:

- Học viên **có thể không cần** bảng xếp hạng dù nhóm đầu tư lớn.
- Hệ thống **có thể chấm sai** khi một lần làm bài được gửi lại.
- Dịch vụ email bên ngoài **có thể chậm hoặc mất kết nối** lúc cấp chứng nhận.
- Một thay đổi API **có thể làm gãy consumer** chưa được nâng cấp.
- Dữ liệu kết quả **có thể lộ** qua yêu cầu không được kiểm tra quyền.
- Mốc khai giảng **có thể không đủ thời gian** cho toàn bộ phạm vi mong muốn.

Rủi ro **không phải** câu khẳng định “sự cố chắc chắn sẽ xảy ra”. Cần nói rõ:

- **Nguyên nhân/điều kiện:** điều gì tạo ra bất định?
- **Sự kiện có thể xảy ra:** chuyện gì có thể xảy ra?
- **Hệ quả:** nếu xảy ra, mục tiêu nào bị ảnh hưởng?
- **Dấu hiệu sớm:** làm sao biết mức rủi ro đang tăng?
- **Cách ứng phó:** làm gì để giảm xác suất, tác động hoặc phát hiện sớm?

### 1.1. Risk khác issue, assumption và dependency

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Risk — rủi ro** | Điều gì *có thể* xảy ra và gây ảnh hưởng? | “Nếu event được giao trùng, học viên có thể nhận hai chứng nhận.” |
| **Issue — vấn đề/sự cố hiện hữu** | Điều gì *đã* xảy ra và cần xử lý? | “Trong test, consumer thực sự cấp hai chứng nhận.” |
| **Assumption — giả định** | Điều ta đang tin nhưng chưa có bằng chứng đủ? | “Học viên cần chứng nhận gửi qua email ngay sau khi thi.” |
| **Dependency — phụ thuộc** | Việc nào cần dữ liệu, công việc hoặc quyết định từ nơi khác? | “Phải có hợp đồng API của nhà cung cấp email.” |
| **Constraint — ràng buộc** | Điều kiện nào phải tuân thủ? | “Không được tiết lộ kết quả của học viên khác.” |
| **Decision — quyết định** | Đã chọn gì trong phạm vi thẩm quyền? | “Consumer phải idempotent theo certificateRequestId.” |

Một phụ thuộc chưa giải quyết có thể **tạo rủi ro chậm bàn giao**, nhưng hai khái niệm không đồng nghĩa. Một issue vừa xảy ra cần quản lý theo quy trình xử lý vấn đề/sự cố, không chỉ được ghi vào danh sách rủi ro rồi chờ Sprint tới.

### 1.2. Cấu trúc câu rủi ro dễ hành động

> “Vì **[nguyên nhân chưa chắc]**, **[sự kiện]** có thể xảy ra, dẫn tới **[tác động lên mục tiêu]**; tín hiệu cần theo dõi là **[bằng chứng]**.”

**Mơ hồ:** “Có rủi ro hệ thống.”

**Rõ hơn:** “Vì chưa kiểm chứng retry của dịch vụ gửi chứng nhận, cùng một yêu cầu có thể xử lý nhiều lần, gây cấp chứng nhận trùng; theo dõi số lần xử lý lặp và kiểm thử idempotency trước khi release.”

Mục đích không phải câu chữ cầu kỳ. Một câu rõ khiến nhóm biết **phải thử gì sớm**.

## 2. Vì sao giao trọn một gói lớn làm rủi ro tích tụ?

Khi mọi chức năng được xây xong rồi mới tích hợp hoặc kiểm tra với người dùng, nhóm có thể có **nhiều đầu việc đã thực hiện nhưng ít giả định đã được xác nhận**.

### Những rủi ro của lô công việc lớn

1. **Rủi ro giá trị:** nhiều tuần xây thứ người dùng ít cần.
2. **Rủi ro tích hợp:** các phần được hiểu khác về hợp đồng, lỗi xuất hiện khi ghép.
3. **Rủi ro chất lượng:** kiểm thử quan trọng bị dồn cuối, khó chẩn đoán nguyên nhân.
4. **Rủi ro phối hợp:** phụ thuộc và quyết định chưa rõ được phát hiện khi đã gần deadline.
5. **Rủi ro tài chính:** chi phí đã phát sinh lớn trước khi biết hướng đi có đúng.
6. **Rủi ro vận hành:** hệ thống chạy được ở môi trường thử nhưng chưa được quan sát tải, lỗi và phục hồi phù hợp.
7. **Rủi ro tuân thủ:** kiến trúc hoặc dữ liệu được thiết kế mà chưa tính đến nghĩa vụ bắt buộc, dẫn tới làm lại.

### So sánh hai cách làm

| Góc nhìn | Bàn giao toàn bộ một lần | Bàn giao các lát nhỏ có chất lượng |
| --- | --- | --- |
| **Phản hồi người dùng** | Đến sau khi nhiều giả định được xây thành sản phẩm. | Có thể quan sát sau từng lát đủ điều kiện. |
| **Kiểm thử tích hợp** | Tập trung vào cuối, nhiều lỗi chồng nhau. | Tích hợp dần, dễ xác định thay đổi gây vấn đề. |
| **Chi phí đổi hướng** | Có thể cao vì kiến trúc và nội dung đã mở rộng. | Có thể dừng hoặc đổi trước khi triển khai phần lớn phạm vi. |
| **Phạm vi khi lỗi xuất hiện** | Nhiều chức năng cùng thay đổi. | Thường dễ giới hạn nếu lát nhỏ và rollout có kiểm soát. |
| **Kiểm soát an toàn** | Dễ trở thành cổng kiểm cuối. | Có thể đưa thành DoD, CI và điều kiện release lặp lại. |
| **Chi phí phối hợp** | Nhiều bàn giao lớn và đợi ghép. | Cần kỷ luật liên tục, contract và quan sát; không tự miễn phí. |

**Quan hệ không tuyệt đối.** Một lát nhỏ nhưng thiết kế sai ranh giới dữ liệu có thể gây rủi ro lớn. Một giải pháp nhiều thành phần có thể cần một số quyết định kiến trúc quan trọng ngay từ đầu. Điều Agile khuyến khích là **đưa bằng chứng và các quyết định quan trọng đến đúng thời điểm, đồng thời không khóa toàn bộ tương lai bằng giả định yếu**.

## 3. Hai chiều của rủi ro: điều chưa biết và mức tác động

Để chọn việc cần học sớm, cần xét cả:

- **Mức bất định:** nhóm có bằng chứng gì, còn bao nhiêu điều chưa hiểu?
- **Mức tác động nếu sai:** người dùng, dữ liệu, mục tiêu và chi phí chịu hậu quả lớn đến đâu?

Một giả định có tác động rất lớn nhưng đã được xác nhận qua bằng chứng đáng tin có thể cần giám sát khác với một giả định ít tốn kém nhưng chưa rõ.

### Ma trận định tính minh họa

| | **Tác động thấp** | **Tác động cao** |
| --- | --- | --- |
| **Bất định thấp** | Duy trì kiểm soát thông thường. | Bảo đảm guardrail, theo dõi vì hậu quả nghiêm trọng. |
| **Bất định cao** | Thử nhanh, chi phí thấp và học sớm. | Ưu tiên giảm rủi ro: bằng chứng, kiểm chứng chuyên môn, lát nhỏ an toàn. |

Các mức **cao/thấp** phải có định nghĩa theo bối cảnh. **Không nên dùng màu “đỏ/vàng/xanh” thay cho việc giải thích tác động và cách xử lý**.

### 3.1. Ví dụ phân loại giả định

| Giả định hoặc nguy cơ | Bất định | Tác động nếu sai | Phép kiểm tra sớm |
| --- | --- | --- | --- |
| Học viên hiểu thông báo “Đã nộp thành công”. | Cao nếu chưa thử. | Trung bình đến cao vì có thể mất niềm tin. | Thử tác vụ trên giao diện và hành vi nộp thật. |
| Chứng nhận sẽ không được cấp trùng khi retry. | Cao nếu chưa kiểm thử. | Cao vì tính đúng đắn và vận hành. | Integration test duplicate/retry và đối soát. |
| Người học muốn huy hiệu trước lời giải đáp án. | Cao. | Thường thấp hơn rủi ro dữ liệu. | Phỏng vấn/prototype để hiểu nhu cầu. |
| Mọi đường đọc kết quả đều kiểm tra quyền. | Phải được kiểm chứng, không dựa vào niềm tin. | Rất cao trong dữ liệu riêng tư. | Threat review và negative authorization tests. |
| Nhà cung cấp email đáp ứng ngay mọi lúc. | Tùy bằng chứng vận hành. | Có thể cao khi cấp chứng nhận phụ thuộc trực tiếp. | Thử timeout/retry; thiết kế trải nghiệm khi email trễ. |

### 3.2. Không để trung bình che sự cố nghiêm trọng

Một thí nghiệm đạt 95% lượt thao tác tốt vẫn **không chấp nhận được** nếu 5% còn lại có thể lộ dữ liệu cá nhân trái quyền. Rủi ro an toàn và tuân thủ thường cần **giới hạn bắt buộc**, không thể được “bù” bằng số click hoặc doanh thu tốt.

## 4. Phân loại rủi ro để chọn loại phản hồi đúng

Không có một phép thử nào trả lời mọi rủi ro. Có những vấn đề cần người dùng thử, vấn đề khác cần test tự động, chuyên gia bảo mật hoặc diễn tập sự cố.

| Nhóm rủi ro | Câu hỏi chính | Kênh phản hồi phù hợp |
| --- | --- | --- |
| **Nhu cầu/giá trị** | Có thực sự cần tính năng; nó giải quyết vấn đề không? | Phỏng vấn, quan sát, thử lát nhỏ với người dùng phù hợp. |
| **Usability/khả năng tiếp cận** | Người dùng hiểu và thao tác được không? | Usability test, accessibility review, quan sát nhiệm vụ. |
| **Nghiệp vụ/tính đúng đắn** | Quy tắc chấm điểm, hoàn thành, cấp chứng nhận có đúng không? | Ví dụ nghiệp vụ, acceptance tests, kiểm thử trường hợp biên. |
| **Kỹ thuật/kiến trúc** | Có tích hợp, thay đổi và mở rộng an toàn được không? | Spike, contract tests, thử thay đổi tương thích. |
| **Bảo mật/dữ liệu** | Có truy cập trái quyền, lộ dữ liệu, mất toàn vẹn không? | Threat modeling, negative tests, review chuyên môn. |
| **Tuân thủ** | Nghĩa vụ áp dụng có được đáp ứng và chứng minh không? | Làm rõ với người có thẩm quyền; kiểm soát và bằng chứng được lưu. |
| **Vận hành/độ tin cậy** | Lỗi, tải, retry, khôi phục có vận hành được không? | Load/resilience tests, telemetry, diễn tập thích hợp. |
| **Bên thứ ba/phụ thuộc** | Hợp đồng và API đối tác có ổn định không? | Contract/integration tests, thử timeout, thỏa thuận fallback. |
| **Delivery/tiến độ** | Có đủ capacity và thứ tự phạm vi cho mốc thật không? | Flow metrics, forecast có giả định, slicing và cập nhật backlog. |
| **Thay đổi tổ chức** | Những người triển khai có cùng mục tiêu và thẩm quyền không? | Working agreement, decision log, kiểm tra blocked time. |

**Phản hồi sớm không chỉ là thu ý kiến khách hàng.** Dữ liệu từ CI, contract tests, thử lỗi mạng, kiểm tra quyền và người hỗ trợ sản phẩm đều có thể là phản hồi có giá trị về rủi ro cụ thể.

## 5. Phân biệt các loại bàn giao và thí nghiệm

Nếu gọi mọi prototype là “Increment đã Done”, nhóm đánh mất khả năng nhìn rủi ro thực sự.

| Khái niệm | Mục đích | Có nhất thiết đủ điều kiện vận hành cho người dùng? |
| --- | --- | --- |
| **User story/PBI** | Diễn đạt nhu cầu và công việc để tạo giá trị. | Không; là công việc cần thực hiện. |
| **Task** | Một phần triển khai như viết API hoặc cấu hình CI. | Không; task xong có thể chưa có hành vi. |
| **Prototype** | Thử hiểu nhu cầu hoặc tương tác, có thể mô phỏng. | Không; phải nói rõ giới hạn. |
| **Spike** | Giảm bất định kỹ thuật có thời hạn. | Không nhất thiết; kết quả có thể là bằng chứng và quyết định. |
| **MVP** | Phiên bản/phép thử tối thiểu để kiểm chứng giả thuyết giá trị quan trọng. | Tùy hình thức, đối tượng và điều kiện an toàn. |
| **Increment trong Scrum** | Bước tiến cụ thể hướng Product Goal, tích hợp với các Increment trước, đáp ứng Definition of Done. | **Phải có thể sử dụng** trong phạm vi đã định nghĩa. |
| **Deployment** | Đưa mã lên môi trường. | Có thể chưa mở cho người dùng. |
| **Release** | Mở khả năng cho một nhóm người dùng cụ thể. | Có, trong phạm vi được mở và đủ điều kiện. |
| **Experiment** | Quy trình kiểm tra một giả thuyết với bằng chứng. | Có thể dùng phỏng vấn, prototype hoặc Increment. |

### Một ví dụ

- **Prototype** giao diện chứng nhận: quan sát xem học viên hiểu các thông báo.
- **Spike** thử retry của nhà cung cấp email: biết khả năng kỹ thuật, chưa cấp chứng nhận thật.
- **Increment I1:** học viên có quyền nộp một bài kiểm tra ngắn và nhận kết quả đúng, tích hợp và đạt DoD.
- **Increment I2:** sau khi đạt quy tắc hoàn thành, tạo một chứng nhận đúng và kiểm soát cấp trùng.
- **Release:** mở I1 cho nhóm lớp thử khi đủ điều kiện, chứ không phải khi bản mock chạy.

Không nên cố định rằng một MVP phải là một Sprint hoặc chỉ một Increment. Một giả thuyết cần kiểm chứng có thể đòi hỏi nhiều Increment, hoặc có thể kiểm tra trước bằng nghiên cứu không cần code.

## 6. Bàn giao nhỏ là “lát dọc có giá trị”, không chỉ một task kỹ thuật

Một yêu cầu lớn thường dễ bị chia ngang theo chuyên môn:

> Database → Backend → Frontend → QA → Security → Integration.

Mỗi đội có thể xong phần mình nhưng **chưa ai sử dụng được hành vi trọn vẹn**. Rủi ro tích hợp và tính đúng đắn vẫn nằm ở cuối.

**Vertical slicing (chia lát dọc)** nghĩa là chọn **một hành vi người dùng hoặc năng lực sản phẩm hoàn chỉnh trong phạm vi nhỏ**, đi qua các lớp cần thiết và đạt điều kiện chất lượng.

~~~mermaid
flowchart LR
    subgraph H["Chia ngang: rủi ro tích hợp dồn cuối"]
      DB["Toàn bộ database"] --> API["Toàn bộ API"] --> UI["Toàn bộ giao diện"] --> QA["Kiểm thử cuối"]
    end
    subgraph V["Chia dọc: phản hồi theo lát"]
      S1["Lát 1: làm một bài, nhận kết quả đúng"] --> S2["Lát 2: lưu kết quả, xem lại"]
      S2 --> S3["Lát 3: cấp một chứng nhận an toàn"]
    end
~~~

Sơ đồ mang tính minh họa; trong thực tế các công việc bên trong lát vẫn có thể thực hiện song song.

### Sáu tiêu chí của lát nhỏ có ích

1. **Người nhận giá trị rõ:** học viên/giảng viên/đội vận hành có khả năng cụ thể.
2. **Tích hợp thật:** UI, nghiệp vụ, dữ liệu và phụ thuộc cần thiết hoạt động cùng nhau.
3. **Phạm vi nhỏ:** đủ để hoàn tất, kiểm tra và học trước khi làm phần lớn roadmap.
4. **Chất lượng không bị hạ:** DoD, quyền, tính đúng đắn và an toàn áp dụng được giữ.
5. **Có câu hỏi kiểm chứng:** biết muốn học điều gì và thu bằng chứng ra sao.
6. **Có lựa chọn tiếp theo:** giữ, mở rộng, sửa hoặc dừng hướng đầu tư.

**Lát nhỏ không có nghĩa tính năng dở dang.** Giới hạn số loại bài kiểm tra được hỗ trợ là hợp lý nếu được công bố rõ; bỏ kiểm tra quyền rồi hứa làm Sprint sau thì không.

## 7. Từ bản đồ rủi ro tới thứ tự lát bàn giao

Một lộ trình Agile tốt không chỉ sắp tính năng theo độ hấp dẫn. Nó có thể **chọn lát giúp giảm rủi ro lớn trước khi đầu tư tiếp**.

### Tình huống: thi Java và chứng nhận

| Lát | Hành vi có thể sử dụng sau khi Done | Rủi ro muốn giảm | Phản hồi/bằng chứng |
| --- | --- | --- | --- |
| **I1: Một bài trắc nghiệm ngắn** | Học viên có quyền trả lời, nộp và xem đúng/sai rõ. | Usability, chấm điểm, kiểm tra quyền, lỗi nộp. | Acceptance + negative tests, usability test với nhóm phù hợp. |
| **I2: Lưu và xem lại một kết quả** | Học viên xem đúng kết quả đã ghi qua phiên. | Toàn vẹn dữ liệu, riêng tư, truy vấn sai người. | Integration tests, quyền, retry, phản hồi người học. |
| **I3: Cấp một chứng nhận** | Học viên đủ điều kiện nhận một chứng nhận hợp lệ. | Quy tắc nghiệp vụ, duplicate, dữ liệu chứng nhận. | Tests idempotency, đối soát, review nghiệp vụ. |
| **I4: Thông báo chứng nhận** | Học viên nhận thông báo, có đường xem lại dù email trễ. | Phụ thuộc nhà cung cấp, timeout, retry, vận hành. | Contract/resilience tests, telemetry và trải nghiệm chờ. |
| **I5: Mở rộng quy tắc/đối tượng** | Nhiều loại bài/khóa theo nhu cầu đã xác nhận. | Scaling, chi phí nội dung, công bằng trải nghiệm. | Rollout dần, chất lượng và outcome theo nhóm. |

**Chuỗi trên là ứng viên**, không phải kế hoạch bất biến. Nếu I1 cho thấy học viên cần lời giải sau khi nộp sai hơn là chứng nhận, PO có thể ưu tiên một lát giải thích trước I3, trong khi vẫn giữ các nghĩa vụ chất lượng.

### 7.1. “Risk-first” không có nghĩa lúc nào cũng làm kỹ thuật khó nhất trước

Một spike công nghệ có thể có giá trị nếu bỏ qua sẽ khóa hướng kiến trúc tốn kém. Nhưng nếu rủi ro lớn nhất là **không ai cần tính năng**, làm kiến trúc phức tạp trước khi hỏi người dùng là lãng phí.

Hãy hỏi **bằng chứng nào làm thay đổi quyết định đầu tư nhiều nhất**, rồi chọn cách rẻ và an toàn nhất để có bằng chứng đó.

### 7.2. Nếu lát đầu còn quá lớn?

Có thể chia theo:

- Quy trình: nộp và xem kết quả trước, xem lịch sử sau.
- Biến thể: một câu một đáp án trước, loại nhiều đáp án sau.
- Quy tắc: một điều kiện cấp chứng nhận trước, chính sách phức tạp sau.
- Nhóm người dùng: lớp được cấp quyền thử trước, mở rộng sau.
- Nội dung: khóa Java cơ bản trước, khóa khác sau.
- Mức tự động hóa: kiểm duyệt nội dung thủ công trong phạm vi nhỏ trước AI.
- Phụ thuộc: thử một hợp đồng tích hợp thật trước khi mở nhiều đối tác.

**Không được chia** bằng cách đẩy rủi ro mất dữ liệu, kiểm tra quyền hoặc các nghĩa vụ bắt buộc thành “tính năng sau”.

## 8. Biến giả thuyết thành thí nghiệm có thể quyết định

Một vòng quản lý rủi ro bằng phản hồi gồm:

1. **Nêu rủi ro/giả định:** điều gì chưa biết ảnh hưởng mục tiêu?
2. **Chọn phương pháp kiểm chứng:** phỏng vấn, prototype, spike, test hoặc Increment.
3. **Định nghĩa tiêu chí và guardrail:** bằng chứng thế nào đủ cho quyết định, điều gì không được đánh đổi?
4. **Giảm phạm vi:** chọn lát hoặc đối tượng nhỏ nhất an toàn và có ý nghĩa.
5. **Thực hiện/quan sát:** kiểm tra dữ liệu thật, test, lỗi và phản hồi định tính.
6. **Đánh giá mức tin cậy:** bằng chứng có đại diện, đo đúng và đủ chưa?
7. **Chọn hành động:** tiếp tục, điều chỉnh, tăng kiểm soát, thay phương án hoặc dừng.
8. **Cập nhật risk register/backlog/decision log:** không để bài học nằm trong chat rồi biến mất.

~~~mermaid
flowchart TD
    A["Product Goal + ràng buộc"] --> B["Rủi ro hoặc giả thuyết chưa rõ"]
    B --> C["Phép kiểm chứng / lát dọc nhỏ"]
    C --> D["Tạo Increment và bằng chứng chất lượng"]
    D --> E{"Đạt DoD và điều kiện thử/release?"}
    E -->|"Không"| F["Khắc phục hoặc đổi phạm vi an toàn"]
    F --> E
    E -->|"Có"| G["Thử trong phạm vi phù hợp"]
    G --> H["Kiểm tra hành vi, lỗi, chất lượng, chi phí"]
    H --> I{"Bằng chứng cho thấy điều gì?"}
    I -->|"Đủ tốt"| J["Mở rộng có kiểm soát"]
    I -->|"Chưa rõ"| K["Đổi phép thử, giảm bất định"]
    I -->|"Rủi ro cao / giả định sai"| L["Sửa, dừng hoặc chuyển cấp"]
    J --> M["Cập nhật backlog, risk, decision"]
    K --> M
    L --> M
    M --> B
~~~

**Không bắt mọi rủi ro phải được thử trên người dùng thật.** Ví dụ rò rỉ dữ liệu hoặc lỗi cấp chứng nhận trùng cần kiểm thử, review và điều kiện an toàn trước khi có bất kỳ rollout nào.

## 9. Bảng liên kết rủi ro — thí nghiệm — quyết định

Thay vì tách risk register khỏi Product Backlog, có thể ghi một bảng quan hệ ngắn:

| Rủi ro/giả thuyết | Lát hoặc phép thử | Điều quan sát | Guardrail | Quyết định nếu không đạt |
| --- | --- | --- | --- | --- |
| Người học không hiểu đã nộp hay chưa. | I1 và usability test theo tác vụ. | Người học có mô tả đúng trạng thái và thao tác tiếp không? | Không xác nhận sai thành công. | Sửa phản hồi/giao diện trước khi thêm tính năng. |
| Kết quả có thể lộ cho tài khoản khác. | I1/I2 với negative authorization tests. | Mọi đường đọc/ghi liên quan từ chối trái quyền. | Không có vi phạm phân quyền. | **Chặn release**, sửa và kiểm chứng lại. |
| Retry gây cấp chứng nhận trùng. | I3 với duplicate/replay tests. | Một yêu cầu hợp lệ chỉ tạo một chứng nhận theo quy tắc. | Không tạo bản ghi trùng trái quy tắc. | Sửa idempotency, dữ liệu và đối soát. |
| Email nhà cung cấp chậm. | I4 và thử timeout/hỏng kết nối. | Người học có đường xem chứng nhận, backlog xử lý ổn? | Không mất trạng thái cấp chứng nhận. | Thiết kế fallback/retry hoặc đổi phương án. |
| Học viên ít cần chứng nhận email. | Prototype/phỏng vấn, sau đó lát nhỏ an toàn. | Nhu cầu, hành vi sử dụng và phản hồi. | Không thu dữ liệu thừa. | Giảm ưu tiên email, chọn giá trị khác. |
| Mốc khai giảng không đủ toàn bộ phạm vi. | Forecast theo lát và review định kỳ. | Throughput/cycle time, blockers, mức ưu tiên. | DoD và điều kiện phát hành giữ nguyên. | Thương lượng phạm vi, không ép hạ chất lượng. |

Mỗi hàng nên liên kết tới **PBI, test, dữ liệu và quyết định** khi có; risk register không thay backlog, và backlog không thay việc ghi rủi ro có chủ sở hữu.

## 10. Acceptance criteria và DoD bảo vệ lát nhỏ

**Acceptance criteria** mô tả hành vi mong đợi của một PBI; **Definition of Done (DoD)** mô tả tiêu chuẩn chất lượng để Increment được xem là hoàn tất trong Scrum.

Theo Scrum Guide 2020, Increment phải **có thể sử dụng**, được tích hợp với các Increment trước và đáp ứng DoD. Có thể có nhiều Increment trong một Sprint. PBI chưa đáp ứng DoD **không thể được coi là một phần của Increment**.

### DoD minh họa cho bài thi Java

| Mảng | Điều kiện chất lượng |
| --- | --- |
| **Nghiệp vụ** | Chấm điểm theo quy tắc đã thống nhất; không nộp thành công giả. |
| **Tích hợp** | UI/API/dữ liệu chạy cùng phiên bản sản phẩm hiện tại. |
| **Quyền truy cập** | Học viên không được đọc/sửa kết quả của người khác trái quyền. |
| **Toàn vẹn** | Xử lý retry/duplicate và giao dịch phù hợp với phạm vi đã hỗ trợ. |
| **Kiểm thử** | Acceptance, integration, security negative cases và hồi quy phù hợp đạt. |
| **Vận hành** | Có log/telemetry và khả năng xử lý lỗi tương xứng, không lộ dữ liệu riêng. |
| **Hỗ trợ** | Nội dung thông báo lỗi, hướng dẫn và hạn chế sản phẩm được công bố đúng. |
| **Tương thích** | Không phá Increment trước hoặc hợp đồng với consumer đang sử dụng. |

Đây là **bộ ví dụ**, không phải DoD bắt buộc cho mọi dự án. Tiêu chuẩn tổ chức áp dụng phải được tuân thủ; nhóm chỉ có thể mở rộng DoD phù hợp chứ không được âm thầm hạ mức an toàn.

### 10.1. Những việc không được hoãn sang lát sau

- Phân quyền khi truy cập kết quả học viên.
- Tính đúng đắn cơ bản của điểm và trạng thái nộp bài.
- Ngăn truy cập dữ liệu nhạy cảm qua ID người dùng tự gửi.
- Không cấp chứng nhận trùng trái quy tắc ở lát cấp chứng nhận.
- Không tuyên bố lưu thành công khi giao dịch chưa được xác nhận.
- Những kiểm soát bảo mật/tuân thủ bắt buộc theo chính sách áp dụng.

**Giảm tính năng, không giảm sự đúng đắn của tính năng đang giao.**

## 11. Gherkin cho rủi ro nộp bài và cấp chứng nhận

Ví dụ hành vi được xác định như sau:

~~~gherkin
Feature: Nộp bài kiểm tra và nhận kết quả đúng

Scenario: Học viên nộp bài hợp lệ
  Given học viên đã đăng nhập và được phép làm bài "Java căn bản"
  And bài kiểm tra chỉ chứa các loại câu hỏi được hỗ trợ
  When học viên nộp đáp án hợp lệ
  Then hệ thống chấm theo quy tắc đã thống nhất
  And ghi nhận một kết quả hợp lệ
  And hiển thị phản hồi nộp bài chính xác

Scenario: Yêu cầu bị gửi lại sau khi đã ghi kết quả
  Given một yêu cầu nộp bài có mã nhận diện đã được xử lý thành công
  When cùng yêu cầu đó được gửi lại
  Then hệ thống áp dụng chính sách idempotency hoặc lần nộp đã thống nhất
  And không tạo dữ liệu trùng trái quy tắc nghiệp vụ
  And không báo thành công cho thao tác thực tế thất bại

Scenario: Không có quyền đọc kết quả người khác
  Given tài khoản không có quyền xem kết quả của học viên khác
  When tài khoản đó yêu cầu kết quả theo một ID học viên khác
  Then hệ thống từ chối theo chính sách
  And không tiết lộ điểm hoặc đáp án riêng tư

Scenario: Chưa thể lưu kết quả
  Given học viên được phép nộp bài
  And dịch vụ lưu dữ liệu tạm thời không thể hoàn tất
  When học viên gửi bài
  Then hệ thống không xác nhận đã lưu thành công sai sự thật
  And cung cấp trạng thái và hướng xử lý phù hợp
~~~

Ví dụ cho lát cấp chứng nhận:

~~~gherkin
Feature: Cấp chứng nhận một lần theo điều kiện hợp lệ

Scenario: Học viên đủ điều kiện được cấp chứng nhận
  Given học viên đáp ứng quy tắc hoàn thành khóa học
  And chưa có chứng nhận hợp lệ cho cùng lần đủ điều kiện
  When hệ thống xử lý yêu cầu cấp chứng nhận
  Then một chứng nhận hợp lệ được ghi nhận
  And học viên có thể xem chứng nhận theo quyền của mình

Scenario: Bản tin cấp chứng nhận đến trùng
  Given yêu cầu cấp chứng nhận "cert-request-42" đã được xử lý
  When cùng yêu cầu "cert-request-42" được giao lại
  Then hệ thống không tạo thêm chứng nhận trùng trái quy tắc
  And trạng thái vẫn có thể đối soát với kết quả ban đầu

Scenario: Chứng nhận bị từ chối vì chưa đủ điều kiện
  Given học viên chưa đáp ứng quy tắc hoàn thành đã thống nhất
  When hệ thống nhận yêu cầu cấp chứng nhận
  Then hệ thống không cấp chứng nhận
  And ghi trạng thái từ chối phù hợp, không lộ dữ liệu trái quyền
~~~

Những kịch bản là **mẫu thảo luận và kiểm thử**. Sản phẩm thực phải xác định quy tắc lần nộp, điều kiện cấp lại/chỉnh sửa chứng nhận, giao dịch dữ liệu và chính sách quyền cụ thể. Chúng không thay thế mọi kiểm thử bảo mật, vận hành hoặc phê duyệt bắt buộc.

## 12. Đo rủi ro bằng bằng chứng, không chỉ bằng cảm giác

Một risk register có thể dùng mức **khả năng xảy ra** và **tác động** theo thang định tính. Nhưng khi chỉ có nhãn 1–5, phép nhân điểm không tự trở thành xác suất hoặc chi phí thực.

### 12.1. Đánh giá định tính có hiệu quả hơn khi định nghĩa mức

Ví dụ:

- **Khả năng thấp:** đã có kiểm soát và dữ liệu hỗ trợ rằng sự kiện khó xảy ra trong phạm vi tương ứng; vẫn cần xem lại.
- **Khả năng trung bình:** có điều kiện khiến nó có thể xảy ra, bằng chứng chưa đủ.
- **Khả năng cao:** nhiều tín hiệu lỗi hoặc giả định quan trọng chưa kiểm chứng trong một luồng thường gặp.

Về tác động:

- **Thấp:** ảnh hưởng giới hạn, phục hồi đơn giản, ít người dùng.
- **Trung bình:** làm gián đoạn một luồng giá trị hoặc cần rework đáng kể.
- **Cao/nghiêm trọng:** ảnh hưởng quyền, mất dữ liệu, nghĩa vụ hoặc khả năng vận hành lớn.

Các mức này **không phải tiêu chuẩn thống nhất toàn ngành**; tổ chức phải xác định phù hợp sản phẩm và nghĩa vụ.

### 12.2. Ví dụ bảng risk register giản lược

| ID | Rủi ro | Khả năng | Tác động | Owner | Phép kiểm chứng/đáp ứng | Trạng thái |
| --- | --- | --- | --- | --- | --- | --- |
| **R-01** | Kết quả nộp bài bị lưu trùng. | Chưa rõ | Cao | Assessment Developers | Test retry, constraint dữ liệu, quan sát duplicate. | Open |
| **R-02** | Học viên hiểu nhầm đã nộp thành công. | Trung bình | Trung bình | PO/UX và nhóm thực hiện | Thử tác vụ I1, kiểm tra thông điệp lỗi. | Testing |
| **R-03** | Xem được điểm người khác. | Chưa rõ, không được suy là an toàn | Nghiêm trọng | Nhóm sở hữu luồng + Security | Negative tests, review quyền, chặn release khi chưa đạt. | Open |
| **R-04** | Dịch vụ email chậm hoặc không sẵn sàng. | Trung bình | Trung bình | Integration/Operations | Thử timeout, retry, giám sát và fallback. | Mitigating |
| **R-05** | Phạm vi trước khai giảng quá lớn. | Trung bình | Cao | PO với Developers | Chia lát, forecast và kiểm tra sau mỗi Increment. | Monitoring |

Chữ **Owner** ở đây là người chịu trách nhiệm **theo dõi, kích hoạt cách xử lý và truyền thông**, không nhất thiết là người có thẩm quyền **chấp nhận mọi mức rủi ro**. Với bảo mật hoặc tuân thủ, quyền chấp nhận rủi ro còn lại thường được định nghĩa riêng theo tổ chức.

### 12.3. Khi có dữ liệu xác suất và tác động thực

Trong một số bối cảnh, có thể sử dụng phép tính **tổn thất kỳ vọng**:

\[
E[L] = P(\text{sự kiện}) \times L(\text{nếu xảy ra})
\]

Nếu có cơ sở thực tế rằng một lỗi ít nghiêm trọng có xác suất khoảng 10% trong một đợt và tổn thất quy đổi theo cùng đơn vị là 20 đơn vị chi phí, giá trị kỳ vọng minh họa là **2 đơn vị**. Nhưng phép nhân chỉ có ý nghĩa khi **đầu vào là ước lượng xác suất/tổn thất có cơ sở**, không phải lấy điểm “3/5 × 4/5” rồi gọi là tiền dự kiến mất.

**Rủi ro hiếm nhưng hậu quả nghiêm trọng** có thể cần guardrails bắt buộc dù giá trị kỳ vọng trung bình nhỏ.

## 13. Bàn giao và phát hành nhỏ: giảm bán kính ảnh hưởng, không bỏ kiểm soát

Một Increment nhỏ đã đạt DoD có thể được **release theo giai đoạn** để kiểm soát phạm vi ảnh hưởng và nhận phản hồi trước khi mở rộng.

Các phương thức thường gặp:

| Phương thức | Giá trị | Giới hạn |
| --- | --- | --- |
| **Thử nội bộ** | Phát hiện lỗi cơ bản, hiểu giao diện. | Người nội bộ có thể không đại diện người học. |
| **Nhóm học viên thử được cấp quyền** | Phản hồi hành vi thật, giới hạn số người bị ảnh hưởng. | Vẫn phải giữ quyền riêng tư và điều kiện chất lượng. |
| **Canary rollout** | Quan sát một phần lưu lượng trước mở rộng. | Không thay test bắt buộc; mẫu nhỏ có thể bỏ sót vấn đề. |
| **Feature flag** | Tách deployment khỏi mở chức năng. | Không khôi phục dữ liệu đã hỏng hoặc sự kiện đã phát. |
| **Blue/green hoặc rolling deployment** | Hỗ trợ chuyển phiên bản có kế hoạch. | Cần tương thích schema, session và data migration. |
| **Prototype/usability test** | Học nhu cầu trước khi xây production. | Không thay bằng chứng vận hành thật. |
| **Gradual enablement theo quyền** | Mở cho nhóm người dùng có điều kiện rõ. | Cần kiểm soát target và đo lường đúng cohort. |

### Điều kiện release minh bạch

Trước khi bật cho lớp học thử, xác minh:

1. **Increment đã đạt DoD** và không có lỗi chất lượng bắt buộc còn mở?
2. **Thẩm quyền phát hành** theo chính sách tổ chức đã được xác nhận?
3. **Đối tượng** được mở có rõ, có quyền và được thông tin đúng phạm vi?
4. **Telemetry** theo dõi lỗi, độ trễ, dữ liệu và hành vi cần thiết đã đủ?
5. **Điều kiện dừng/rollback/khôi phục** có phù hợp rủi ro dữ liệu và bên thứ ba?
6. **Người xử lý sự cố và kênh hỗ trợ** có rõ trong giai đoạn thử?
7. **Điều kiện mở rộng** dựa trên bằng chứng gì, ai quyết?
8. **Các nghĩa vụ bảo mật và riêng tư** có được bảo vệ ngay ở nhóm nhỏ?

Không nên cho rằng “mở cho 1% người dùng” hợp thức hóa một lỗ hổng phân quyền có thể dự kiến hoặc đã biết.

### Sơ đồ rollout có kiểm soát

~~~mermaid
flowchart TD
    A["Increment đạt DoD + kiểm tra điều kiện release"] --> B{"Rủi ro/an toàn được kiểm soát?"}
    B -->|"Không"| C["Dừng, sửa hoặc đổi phương án"]
    C --> A
    B -->|"Có"| D["Mở cohort nhỏ được phép"]
    D --> E["Quan sát guardrails + outcome"]
    E --> F{"Có tín hiệu phải dừng?"}
    F -->|"Có"| G["Dừng rollout, xử lý sự cố, phục hồi dữ liệu nếu cần"]
    F -->|"Không"| H{"Đủ bằng chứng mở rộng?"}
    H -->|"Chưa"| I["Quan sát thêm / cải thiện phép đo"]
    I --> E
    H -->|"Có"| J["Mở rộng dần theo quyền và capacity"]
    J --> E
    G --> K["Post-incident learning + cập nhật risk/decision"]
~~~

**Quy trình minh họa**; thứ tự cụ thể phụ thuộc hạ tầng, chính sách và loại sản phẩm. Với rủi ro nghiêm trọng, không thể chờ telemetry production chứng minh vấn đề rồi mới xử lý: phải kiểm thử và ngăn chặn ngay từ trước.

## 14. Guardrails: điều tuyệt đối không đem ra đánh đổi để “học nhanh”

Trong quản trị Agile, **ràng buộc tốt** giải thích điều gì cần bảo vệ và cách kiểm chứng, không đơn giản là một bước ký duyệt không có tiêu chí.

| Guardrail minh họa | Bảo vệ điều gì? | Bằng chứng trước hoặc trong release |
| --- | --- | --- |
| **Không truy cập kết quả trái quyền** | Quyền riêng tư và bảo mật. | Negative authorization tests, review chính sách quyền. |
| **Không cấp chứng nhận trùng trái quy tắc** | Tính đúng đắn nghiệp vụ/toàn vẹn. | Idempotency, uniqueness, duplicate/replay tests. |
| **Không xác nhận sai trạng thái đã nộp** | Niềm tin, khả năng tiếp tục học. | Acceptance tests trong trường hợp lỗi mạng. |
| **Không ghi dữ liệu nhạy cảm không cần thiết** | Giới hạn mục đích, giảm lộ thông tin. | Review telemetry, log masking và quyền truy cập. |
| **Hợp đồng thay đổi có kế hoạch tương thích** | An toàn tích hợp liên nhóm. | Schema/contract tests, kiểm tra consumer. |
| **Quan sát được luồng quan trọng** | Phát hiện và chẩn đoán sự cố. | Kiểm tra tracing, errors, alerts, runbooks cần thiết. |
| **Increment đáp ứng DoD** | Chất lượng bền vững. | CI/test/review và tiêu chuẩn tổ chức. |
| **Ngoại lệ theo đúng thẩm quyền** | Tuân thủ và trách nhiệm giải trình. | Decision/approval có scope, owner và thời hạn. |

### Không biến guardrail thành khóa công nghệ không cần thiết

“Phải dùng thư viện X trong mọi service” chỉ hợp lý nếu đó là một chuẩn bắt buộc có cơ sở. Thường hữu ích hơn là đặt mục tiêu **“Mọi dịch vụ cần mang được trace context theo hợp đồng thống nhất”**, cùng phép kiểm chứng, để Developers chọn triển khai phù hợp trong ranh giới đã chấp nhận.

### Với nghĩa vụ bắt buộc, phương án đúng là giảm phạm vi

Nếu I3 chưa đạt kiểm thử cấp chứng nhận trùng, không nên cho chạy production “để lấy dữ liệu thực” rồi sửa sau. Hãy giảm phạm vi release về **I1/I2 đã an toàn**, hoặc thực hiện thử nghiệm kỹ thuật trong môi trường phù hợp không gây hại.

## 15. Đưa kiểm soát và bằng chứng vào từng Increment

Một mô hình “làm xong sản phẩm rồi mới kiểm bảo mật và tuân thủ” thường đẩy vấn đề sang cuối. Trong Agile, có thể đưa nhiều kiểm soát **gần nơi thay đổi phát sinh**:

| Kiểm soát | Thực hành đưa phản hồi sớm |
| --- | --- |
| **Chất lượng logic** | Unit/acceptance tests, review và CI trên thay đổi. |
| **Phân quyền** | Negative tests ở các ranh giới đọc/ghi và review quyền. |
| **Hợp đồng tích hợp** | Contract tests theo phiên bản producer/consumer. |
| **Toàn vẹn dữ liệu** | Constraints giao dịch, retry/duplicate/replay tests. |
| **Thư viện/phụ thuộc** | Kiểm tra lỗ hổng và chính sách theo quy mô, ưu tiên rủi ro thực tế. |
| **Hạ tầng cấu hình** | Review cấu hình/IaC, secret handling và kiểm tra môi trường. |
| **Vận hành** | Observability, alerts, runbook và diễn tập lỗi tương xứng. |
| **Nghĩa vụ tổ chức** | Evidence link tới kiểm soát, owner, thời điểm và phê duyệt khi áp dụng. |

**Continuous compliance** ở đây là cách làm **duy trì bằng chứng đáp ứng kiểm soát liên tục**, không phải tuyên bố mọi tổ chức phải triển khai một công cụ cố định hay mọi yêu cầu pháp lý đều có thể tự động hóa.

### Ví dụ pipeline phản hồi

~~~text
Pull request tạo/cập nhật PBI:
  - Lint / static checks phù hợp
  - Unit + integration tests cần thiết
  - Authorization negative tests
  - API/event contract checks
  - Build artifact & kiểm tra cấu hình/secret
  - Review theo rủi ro và tiêu chuẩn nhóm

Nếu bắt buộc có phê duyệt chuyên môn:
  - Ghi rõ người có thẩm quyền, tiêu chí và bằng chứng
  - Không dùng merge Green để thay phê duyệt chính thức

Sau triển khai thử:
  - Kiểm tra telemetry, chất lượng, truy cập và rollback readiness
  - Lưu evidence liên quan release/risk
~~~

Cần chọn mức kiểm soát **tương xứng loại thay đổi**. Một sửa typo không nhất thiết cần hội đồng kiến trúc; một thay đổi quyền truy cập dữ liệu riêng tư cần review nghiêm túc. Nhưng **không có mức “rủi ro thấp” cho việc cố ý bỏ yêu cầu bắt buộc đã biết**.

## 16. Rủi ro bên thứ ba và phụ thuộc liên nhóm: thử đường tích hợp thật sớm

Tính năng cấp chứng nhận có thể cần dịch vụ email, kho file, chữ ký số hoặc hệ thống quản lý học tập ngoài. Nếu chỉ giả lập toàn bộ cho tới ngày gần release, nhóm có thể phát hiện hạn chế hợp đồng quá muộn.

### Những câu hỏi cần xác minh

- Hợp đồng API và SLA/SLO thực tế nói gì?
- Hệ thống ngoài có timeout, retry, giới hạn tốc độ hoặc lỗi tạm thời ra sao?
- Tính nhất quán dữ liệu và thứ tự sự kiện được bảo đảm ở mức nào?
- Khi gửi email thất bại, chứng nhận đã cấp vẫn có thể xem được không?
- Nếu yêu cầu gửi trùng, hệ thống có phát sinh tác dụng phụ trùng?
- Dữ liệu nào gửi ra ngoài, có được phép theo chính sách?
- Ai được quyền quyết định đổi nhà cung cấp, chấp nhận rủi ro hoặc chi phí?
- Có môi trường sandbox/bản hợp đồng thử đáng tin không?

### Các bước bàn giao nhỏ giảm rủi ro tích hợp

| Bước | Điều cần làm | Bằng chứng |
| --- | --- | --- |
| **1. Làm rõ hợp đồng** | Thống nhất payload tối thiểu, lỗi, quyền, retry, version. | Contract/document có owner và consumer. |
| **2. Spike có giới hạn** | Thử một yêu cầu trong sandbox với trường hợp thành công và lỗi. | Kết quả kiểm thử, quyết định về khả thi. |
| **3. Tích hợp lát đầu** | Một luồng cấp chứng nhận có thể dùng được theo DoD. | End-to-end tests, dữ liệu không trùng. |
| **4. Thử hỏng kết nối** | Timeout, retry, duplicate, mất mạng và đối soát. | Logs/metrics, runbook, test. |
| **5. Release có điều kiện** | Mở nhóm nhỏ, quan sát lỗi và phản hồi. | Telemetry và bằng chứng quyền/chi phí. |
| **6. Mở rộng hoặc đổi hướng** | Quyết định theo kết quả và mức rủi ro còn lại. | Risk/ADR/backlog được cập nhật. |

**Mock là công cụ học**, không phải bằng chứng duy nhất rằng đối tác thật hoạt động. Cần tích hợp một đường thật đủ sớm trong điều kiện được phép và an toàn.

## 17. Risk owner, decision owner và thẩm quyền chấp nhận rủi ro

Một tổ chức có thể có các vai trò Scrum, quản lý dự án, bảo mật, pháp lý, vận hành và nhóm kỹ thuật. Cần phân biệt ba loại trách nhiệm:

1. **Người theo dõi rủi ro (risk owner):** giữ rủi ro hiển thị, thu bằng chứng, đề xuất và theo dõi hành động.
2. **Người thực hiện kiểm soát (action/control owner):** triển khai test, thay đổi kiến trúc, tài liệu hoặc bước bảo vệ.
3. **Người có quyền quyết định/chấp nhận rủi ro còn lại (decision/risk acceptance authority):** chấp thuận phương án hoặc ngoại lệ theo chính sách.

Một người có thể mang nhiều vai trong tổ chức nhỏ, nhưng **không nên tự suy rằng Product Owner được miễn kiểm soát pháp lý hoặc Developers có quyền chấp nhận mọi rủi ro bảo mật**.

### Scrum và quyền quản trị

- **Product Owner** chịu trách nhiệm tối đa hóa giá trị, thứ tự Product Backlog. Rủi ro sản phẩm và tác động tới người dùng cần đi vào lựa chọn ưu tiên.
- **Developers** chịu trách nhiệm tạo Increment đạt DoD, kế hoạch kỹ thuật và chất lượng thực thi.
- **Scrum Master** giúp Scrum Team/tổ chức áp dụng Scrum hiệu quả và tháo trở ngại, không phải kiểm toán viên ký thay cơ quan có quyền.
- **Thẩm quyền pháp lý, bảo mật, hợp đồng, ngân sách, release** cần được xác định theo chính sách tổ chức, không tự phát sinh chỉ vì một vai trò Scrum.

### Ví dụ bảng quyền quyết định

| Quyết định | Đầu mối chịu trách nhiệm | Người cần tham vấn |
| --- | --- | --- |
| Thứ tự PBI để giảm rủi ro giá trị | Product Owner trong Scrum. | Developers, người dùng/stakeholders, chuyên gia rủi ro. |
| Chọn test và cách chia lát kỹ thuật | Developers. | PO, QA/security/ops theo tác động. |
| Thay đổi API cấp chứng nhận | Owner hợp đồng theo cơ chế tổ chức. | Consumers, bảo mật, vận hành. |
| Release cho cohort thật | Người có thẩm quyền phát hành. | PO, Developers, ops/security. |
| Ngoại lệ điều khoản hợp đồng | Người có thẩm quyền hợp đồng/pháp lý. | PO, người triển khai, đối tác. |
| Chấp nhận rủi ro dữ liệu còn lại | Người được giao thẩm quyền theo chính sách, nếu được phép. | Security/privacy và các bên chịu tác động. |
| Chuyển cấp sự cố nghiêm trọng | Incident owner/commander theo quy trình. | Nhóm dịch vụ, hỗ trợ, chuyên gia liên quan. |

**Một risk register có owner mà không có người được quyền quyết là chưa đủ.** Nếu một rủi ro nghiêm trọng bị treo vì không rõ ai có thẩm quyền, chính **cơ chế quản trị** đã trở thành một điểm nghẽn cần giải quyết.

## 18. Các chiến lược ứng phó rủi ro: tránh, giảm, chuyển, chấp nhận và chuẩn bị

Không phải mọi rủi ro đều cần cùng hành động. Sau khi đã rõ **mục tiêu, tác động và nguồn bất định**, nhóm cân nhắc những chiến lược phù hợp.

| Chiến lược | Ý nghĩa | Ví dụ trong nền tảng học | Lưu ý |
| --- | --- | --- | --- |
| **Tránh (avoid)** | Thay phạm vi hoặc cách tiếp cận để loại bỏ một nguồn rủi ro. | Không đưa tính năng chấm code chưa an toàn vào đợt thử đầu. | Có thể từ bỏ giá trị; cần PO và thẩm quyền liên quan quyết định. |
| **Giảm (mitigate)** | Giảm khả năng xảy ra hoặc tác động bằng kiểm soát, thiết kế và phản hồi. | Kiểm thử quyền, idempotency và tích hợp sớm. | Kiểm soát cần được kiểm chứng, không chỉ ghi trong tài liệu. |
| **Chuyển/chia sẻ (transfer/share)** | Phân bổ hậu quả/trách nhiệm qua hợp đồng, bảo hiểm hoặc đối tác phù hợp. | Có thỏa thuận hỗ trợ với nhà cung cấp email. | **Không chuyển được mọi nghĩa vụ hay trách nhiệm bảo vệ người dùng**. |
| **Chấp nhận có ý thức (accept)** | Chấp nhận phần rủi ro còn lại trong giới hạn/thẩm quyền với lý do rõ. | Chấp nhận email có thể tới trễ nếu chứng nhận vẫn xem được trên hệ thống. | Không có nghĩa được bỏ yêu cầu an toàn/tuân thủ bắt buộc. |
| **Dự phòng (contingency)** | Chuẩn bị hành động khi rủi ro thành sự cố. | Queue và cơ chế gửi lại; hỗ trợ xem chứng nhận trên web khi email lỗi. | Có owner, điều kiện kích hoạt, thử nghiệm phục hồi. |
| **Theo dõi (monitor)** | Quan sát tín hiệu khi chi phí xử lý ngay chưa hợp lý. | Theo dõi thời gian phản hồi nhà cung cấp trước khi mở rộng. | Phải có trigger rõ; “theo dõi” không phải để quên. |

### 18.1. Rủi ro còn lại phải được gọi đúng tên

Sau khi có kiểm thử retry, vẫn có khả năng nhà cung cấp email bị gián đoạn kéo dài. Đó là **rủi ro còn lại (residual risk)**. Nhóm nên biết:

- Rủi ro còn lại là gì, khác rủi ro ban đầu ra sao?
- Có phù hợp ngưỡng chấp nhận và nghĩa vụ áp dụng?
- Ai có thẩm quyền chấp nhận?
- Trường hợp nào buộc dừng/mở lại quyết định?
- Phương án dự phòng có được thử không?

Không nên biến “CI Green” thành “không còn rủi ro”. Kiểm thử cung cấp bằng chứng cho một tập tình huống, không chứng minh an toàn tuyệt đối.

### 18.2. Một quyết định chấp nhận rủi ro có điều kiện

> “Trong nhóm dùng thử được phép, tính năng cho phép học viên xem chứng nhận ngay trên web, dù thông báo email có thể bị trễ. Chúng tôi chấp nhận độ trễ email theo tiêu chí sản phẩm vì dữ liệu chứng nhận được ghi và kiểm chứng riêng, có hàng đợi retry và kênh hỗ trợ. Không chấp nhận cấp chứng nhận trùng hoặc truy cập trái quyền. Quyết định được xem lại khi tỷ lệ email chậm vượt ngưỡng đã thống nhất hoặc khi nhà cung cấp thay hợp đồng.”

Đây là **ví dụ**, không tự thay phê duyệt có thẩm quyền của sản phẩm thật.

## 19. Trigger, checkpoint và escalation: rủi ro phải có hành động khi thay đổi

Một risk register không hữu ích nếu chỉ được cập nhật trước buổi báo cáo tháng. Mỗi rủi ro đáng kể nên có **tín hiệu kích hoạt (trigger)** và **mốc kiểm tra lại (checkpoint)**.

### Mẫu trigger theo từng loại

| Rủi ro | Trigger | Hành động dự kiến |
| --- | --- | --- |
| **Lộ dữ liệu kết quả** | Một negative test quyền thất bại hoặc phát hiện truy cập sai. | Dừng release/giới hạn ảnh hưởng, xử lý theo chính sách security/incident. |
| **Cấp chứng nhận trùng** | Integration test duplicate thất bại hoặc có bản ghi trùng thực tế. | Chặn đường cấp trùng, đối soát, sửa idempotency trước mở rộng. |
| **Lỗi nhà cung cấp email** | Timeout/retry hoặc queue lag vượt ngưỡng đã định nghĩa. | Kích hoạt fallback, cảnh báo owner, điều tra và cập nhật rollout. |
| **Scope trượt mốc khai giảng** | Forecast cho lát cốt lõi vượt thời gian còn lại. | PO cùng Developers điều chỉnh phạm vi, nêu lựa chọn và tác động. |
| **Không đủ phản hồi giá trị** | Nhóm thử quá nhỏ hoặc hành vi/khảo sát không rõ. | Bổ sung quan sát định tính, cải thiện cách đo hoặc đổi thí nghiệm. |
| **Rủi ro tích hợp bị treo** | Chủ sở hữu contract không trả lời theo checkpoint. | Chuyển cấp đúng thẩm quyền; chọn lát ít phụ thuộc nếu phù hợp. |

### 19.1. Đường chuyển cấp không nên mơ hồ

Một quy trình đơn giản:

1. **Người phát hiện** cập nhật bằng chứng và tác động.
2. **Risk owner** xác nhận mức nghiêm trọng và hành động gần nhất.
3. **Action owner** thực hiện kiểm soát/điều tra.
4. Nếu **ngoài thẩm quyền hoặc mức chấp nhận**, chuyển tới người có quyền quyết định; không tự thay chính sách.
5. Nếu là **issue/sự cố đang diễn ra**, dùng quy trình incident hoặc khôi phục phù hợp, không chỉ hẹn Sprint Review.
6. Sau xử lý, cập nhật **risk register, decision log, Product Backlog và bài học**.

### 19.2. Đừng chờ cuộc họp định kỳ để xử lý nguy cơ đã rõ

Nếu test phân quyền thất bại hôm nay, đợi cuộc họp quản trị tháng sau mới quyết định có release hay không là không phù hợp. Cần **cơ chế phản ứng theo mức độ rủi ro**, với quyền rõ và thời gian phản hồi tương xứng.

Ngược lại, không biến mọi chỉnh sửa giao diện nhỏ thành sự cố cần họp khẩn. **Governance theo rủi ro** bảo vệ thời gian tập trung của nhóm.

## 20. Phản hồi sớm phải đủ đáng tin để thay đổi quyết định

Một phép thử nhanh nhưng sai thiết kế có thể khiến nhóm **tự tin hơn vào một kết luận không đúng**.

### 20.1. Phản hồi định tính và định lượng bổ trợ nhau

| Loại bằng chứng | Giúp hiểu | Giới hạn |
| --- | --- | --- |
| **Phỏng vấn người học** | Nhu cầu, ngôn ngữ, bối cảnh, động cơ. | Người dùng có thể nói khác với hành vi thật. |
| **Quan sát làm tác vụ** | Có tìm, hiểu và thực hiện được thao tác? | Mẫu nhỏ có thể chưa đại diện đa dạng. |
| **Telemetry hành vi** | Người dùng thực sự làm gì, ở bước nào bỏ dở? | Cần định nghĩa sự kiện đúng và tuân thủ riêng tư. |
| **Acceptance/integration tests** | Quy tắc và giao tiếp được mã hóa có đúng trong trường hợp kiểm? | Không tự chứng minh nhu cầu sản phẩm. |
| **Security/quality review** | Rủi ro và thiếu sót kỹ thuật có thể dự báo. | Phụ thuộc vào phạm vi, chuyên môn, bằng chứng. |
| **Production SLIs/SLOs** | Độ trễ, lỗi và vận hành theo thời gian. | Không nói nguyên nhân hoặc giá trị nếu thiếu ngữ cảnh. |
| **Đối soát dữ liệu** | Trạng thái giữa các hệ có nhất quán? | Cần quy tắc so sánh và thời điểm rõ. |

### 20.2. Đừng nhầm “nhiều click” với giá trị

Sau I1, số lượt nộp bài tăng có thể vì giao diện tốt hơn, hoặc vì học viên phải nộp lại nhiều lần do lỗi. Vì vậy cần phân biệt sự kiện:

- **SubmissionAttempted:** người dùng/ứng dụng gửi yêu cầu.
- **SubmissionSucceeded:** kết quả được ghi hợp lệ.
- **SubmissionFailed:** lỗi được phân loại theo nguyên nhân.
- **FeedbackViewed:** phản hồi được hiển thị cho người có quyền.
- **NextPracticeStarted:** học viên bắt đầu hoạt động tiếp theo.

Một event tên “Submitted” cho cả **bấm nút** và **ghi thành công** tạo số liệu có thể đánh lừa.

### 20.3. Định nghĩa phép đo

Một chỉ số hữu ích phải có:

1. **Đối tượng:** ai được tính vào mẫu?
2. **Hành vi:** điều gì được coi là thành công?
3. **Đơn vị:** người học, phiên, attempt hay request?
4. **Cửa sổ thời gian:** tính theo ngày, giờ, hay sau một sự kiện nào?
5. **Loại trừ hợp lệ:** bot, dữ liệu thử, request trùng xử lý ra sao?
6. **Nguồn:** telemetry, phỏng vấn, CI hay hệ thống ghi nhận?
7. **Giới hạn:** sai lệch mẫu, dữ liệu thiếu, ảnh hưởng mùa thi/giảng viên?
8. **Quyền riêng tư:** cần thu những thuộc tính nào, ai được xem?

### 20.4. Dữ liệu thí nghiệm không tự chứng minh nhân quả

Giả sử với hai nhóm thử, tỷ lệ hoàn tất luồng nộp bài lần lượt là **76%** và **87%**. Chênh lệch quan sát là **11 điểm phần trăm**. Nhưng nếu nhóm sau học viên quen nền tảng hơn, bài dễ hơn hoặc thiết bị khác, chưa thể kết luận cải tiến UI **gây ra** toàn bộ mức tăng.

Nếu cần đánh giá tác động nhân quả, có thể dùng thử nghiệm có đối chứng, phân nhóm và phương pháp phân tích phù hợp. Với lỗi usability hiển nhiên, một lần quan sát nhóm nhỏ **có thể đủ để sửa lỗi**, không cần chờ phân tích thống kê phức tạp trước khi cải thiện.

### 20.5. Thí nghiệm phải có điều kiện an toàn và đạo đức

Không nên cố ý mở một phiên bản có lỗ hổng truy cập dữ liệu để “so sánh tỉ lệ lỗi”, không đánh lừa người học về điểm hoặc chứng nhận, và không thu dữ liệu nhạy cảm không cần thiết.

Phản hồi sớm phải diễn ra **trong quyền tham gia, phạm vi và nghĩa vụ áp dụng**. Những điều kiện này cần được làm rõ với người có thẩm quyền, không suy diễn rằng mọi thử nghiệm Agile đều được miễn thủ tục.

## 21. Quản lý rủi ro tiến độ bằng phạm vi nhỏ và dự báo trung thực

Agile không xóa những mốc có thật như **ngày khai giảng, nghĩa vụ hợp đồng hoặc thay đổi hệ thống bên thứ ba**. Nhưng estimate không trở thành sự thật chỉ vì quản lý đặt một ngày trên kế hoạch.

Một cách làm có ích:

1. Xác định **mốc và lý do**: cố định do sự kiện, luật, hợp đồng hay chỉ là mong muốn?
2. Đặt **kết quả tối thiểu có giá trị và an toàn** trước mốc.
3. Chia thành **lát dọc** và xác định phụ thuộc/nghĩa vụ.
4. Dùng dữ liệu gần đây của **chính nhóm**: throughput, cycle time, velocity nếu quy ước phù hợp.
5. Nêu giả định về **capacity, phạm vi và bất định**.
6. Cập nhật forecast khi có Increment và bằng chứng mới.
7. Khi rủi ro tăng, đưa **lựa chọn đổi phạm vi hoặc cách phát hành** ra sớm.
8. Không hạ DoD hoặc bỏ kiểm soát để làm biểu đồ đẹp.

### 21.1. Ví dụ scope trước khai giảng

| Mức độ | Hành vi | Quyết định dựa trên rủi ro |
| --- | --- | --- |
| **Cốt lõi** | Học viên có quyền thi một bài và xem kết quả đúng. | Là lát tạo giá trị cần hoàn tất đúng chuẩn. |
| **Cốt lõi nếu chính sách yêu cầu** | Không cấp chứng nhận sai/trùng hoặc truy cập trái quyền. | Là điều kiện an toàn bắt buộc của lát có chứng nhận. |
| **Có giá trị cao** | Xem chứng nhận đã cấp trên trang tài khoản. | Có thể ưu tiên trước email bên thứ ba. |
| **Có thể phát hành sau** | Email thông báo, nhiều mẫu chứng nhận, thống kê nâng cao. | Cân nhắc giá trị và sự phụ thuộc đối tác. |
| **Khám phá sau** | Chứng nhận dùng một mô hình AI phức tạp để đánh giá tự động. | Cần kiểm chứng giá trị, khả thi và rủi ro riêng. |

**Giảm scope** khác hoàn toàn với **bỏ an toàn**. Nếu chỉ có thời gian làm I1 đúng, có thể release I1 cho đúng đối tượng mà không công bố tính năng cấp chứng nhận chưa có.

### 21.2. Velocity và story points không phải hạn chót

Một nhóm dùng Scrum có thể ước lượng bằng points và xem velocity lịch sử của chính mình. Nhưng **points không phải giờ**, không có thang chung giữa nhóm, và velocity không là KPI năng suất cá nhân.

Nếu cần forecast phức tạp hơn, có thể dùng lịch sử throughput/cycle time, dự báo kịch bản hoặc Monte Carlo **khi dữ liệu và giả định phù hợp**. Công cụ thống kê không cứu được dữ liệu không đồng dạng hoặc backlog thiếu rõ.

### 21.3. Dự báo phải công bố giới hạn

Ví dụ:

> “Với phạm vi I1/I2 đã được làm rõ và capacity hiện tại, nhóm dự kiến có thể giao lát đầu để thử trước mốc khai giảng. I3 còn rủi ro idempotency, I4 phụ thuộc hợp đồng email; chúng tôi chưa thể hứa ngày phát hành hai lát này. Sau mỗi Sprint hoặc khi test tích hợp có kết quả, PO cùng nhóm sẽ xem lại phạm vi và cập nhật mức rủi ro.”

Báo cáo này có giá trị hơn việc nói “mọi thứ 80% và sẽ xong đúng hạn” khi chưa có Increment đạt DoD.

## 22. Scrum: kiểm tra và thích ứng rủi ro qua mục tiêu, Sprint và Increment

Trong Scrum, **minh bạch, kiểm tra và thích ứng** giúp các thành viên nhìn bằng chứng thường xuyên. Scrum **không bắt buộc một risk register, ma trận xác suất hay bộ story points** cụ thể; nhóm có thể chọn công cụ quản trị để phục vụ công việc.

### 22.1. Kết nối risk với ba commitments

| Commitment | Câu hỏi về rủi ro |
| --- | --- |
| **Product Goal** | Rủi ro nào khiến sản phẩm không tạo giá trị hoặc mất niềm tin của người học? |
| **Sprint Goal** | Trong Sprint này, điều chưa biết nào có thể ngăn hoàn tất lát giá trị? |
| **Definition of Done** | Những điều kiện nào đảm bảo Increment có thể sử dụng và không che rủi ro chất lượng? |

### 22.2. Product Backlog Refinement

Refinement giúp chia PBI, làm rõ hành vi, độ lớn, thứ tự và các rủi ro phụ thuộc. Một epic “Toàn bộ hệ thống chứng nhận” có thể được chia thành các lát nhỏ. PO có thể cân nhắc thứ tự không chỉ theo “tính năng hấp dẫn”, mà còn theo **rủi ro giá trị và kỹ thuật**.

### 22.3. Sprint Planning

- **Product Owner** làm rõ giá trị, thứ tự và Product Goal liên quan.
- **Developers** đánh giá khả năng hoàn tất, DoD, phụ thuộc và kế hoạch kỹ thuật, chọn PBIs phù hợp để hướng Sprint Goal.
- Cả Scrum Team xây **Sprint Goal** có ý nghĩa.
- Nếu một PBI có bất định lớn, có thể chia lát hoặc làm spike phù hợp; không buộc kéo cả khối chưa hiểu vào Sprint.

### 22.4. Daily Scrum

Daily Scrum là sự kiện **15 phút của Developers** để kiểm tra tiến độ hướng Sprint Goal và điều chỉnh Sprint Backlog. Một risk đang tăng hoặc blocker liên nhóm nên được làm rõ ở mức ảnh hưởng tới mục tiêu, không biến sự kiện thành báo cáo “ai làm được bao nhiêu điểm”.

Vấn đề khẩn có thể cần xử lý ngay **ngoài sự kiện** theo quyền và quy trình phù hợp, không chờ Daily Scrum.

### 22.5. Sprint Review và Retrospective

- **Sprint Review:** xem kết quả Sprint, Increment, phản hồi và bối cảnh thay đổi, rồi thích ứng Product Backlog. Không phải cổng bắt buộc để release.
- **Sprint Retrospective:** cải tiến chất lượng và hiệu quả, chẳng hạn điều chỉnh cách phát hiện rủi ro tích hợp hoặc đưa contract tests chạy sớm.

Một Sprint có thể tạo **nhiều Increment**, giúp kiểm tra những lát an toàn sớm hơn ngày cuối Sprint.

## 23. Kanban, XP và Lean: quản lý rủi ro trong dòng công việc

### 23.1. Kanban phơi bày sự chờ đợi

Một bảng ví dụ:

~~~text
Ready -> Develop (WIP <= 3) -> Review (WIP <= 2)
                                  |
                                  v
                           Verify -> Done

Risk / blocked:
  CERT-18  Waiting for duplicate-event test
  EMAIL-08 Waiting for vendor contract
  ASMT-12  Waiting for authorization review
~~~

Những WIP limits là **minh họa**, không phải thông số tiêu chuẩn. Điều quan trọng là **Definition of Workflow**, chính sách blocked, ngưỡng WIP và khả năng nhìn công việc quá tuổi.

Khi thấy nhiều mục chờ contract, nhóm có thể chuyển sang **làm rõ API và test tương thích trước khi mở thêm feature**.

### 23.2. XP giúp rủi ro kỹ thuật lộ sớm

- **TDD:** viết kiểm thử hành vi trước, triển khai vừa đủ, refactor.
- **Continuous Integration:** tích hợp thường xuyên để phát hiện lỗi sớm.
- **Pair programming/review:** chia sẻ hiểu biết về quy tắc quan trọng và giảm phụ thuộc một người.
- **Refactoring:** giảm độ khó thay đổi khi phản hồi khiến cần đổi thiết kế.
- **Simple design:** không xây kiến trúc tương lai lớn khi một lát nhỏ đủ kiểm chứng giả định.
- **Small releases:** tạo cơ hội phản hồi sớm khi đã đạt DoD và điều kiện phát hành.

**Refactoring và CI không tự chứng minh tính năng có giá trị**; chúng giúp thử, sửa và tích hợp an toàn hơn.

### 23.3. Lean tập trung vào chi phí chờ và công việc dở

Một luồng có thể đi:

> Nhu cầu → quyết định backlog → làm rõ rủi ro → phát triển → test/DoD → release → feedback → quyết định mới.

Nếu thời gian xây chỉ hai ngày nhưng chờ hợp đồng, review và release ba tuần, tối ưu mỗi người code nhanh hơn có thể ít tác dụng. Cần nhìn **toàn bộ thời gian đến bằng chứng**, giới hạn WIP và loại bỏ bàn giao không tạo giá trị.

### 23.4. Không dùng flow metrics làm KPI cá nhân

Nếu thưởng theo số ticket Done, nhóm có thể chia ticket vụn. Nếu thưởng theo cycle time, có thể trì hoãn việc chuyển trạng thái Started. Hãy đo **hệ thống và kết quả**, cùng chất lượng và outcome để giảm động cơ “làm đẹp số”.

## 24. Những số đo nào báo hiệu quản lý rủi ro đang tốt lên?

Một dashboard hữu ích nên có ít chỉ số **liên kết với quyết định** và **rõ ranh giới đo**, không phải càng nhiều biểu đồ càng tốt.

| Nhóm | Số đo minh họa | Cách diễn giải có ích |
| --- | --- | --- |
| **Học hỏi/giá trị** | Thời gian từ giả thuyết đến bằng chứng đủ để quyết định. | Có biết cần đổi hướng trước khi đầu tư lớn? |
| **Khả năng sử dụng** | Tỷ lệ hoàn thành tác vụ nộp bài hợp lệ trong mẫu thử. | Người học có thực hiện được hành vi dự định? |
| **Chất lượng** | Lỗi chấm sai, cấp chứng nhận trùng, lỗi hồi quy. | Increment có làm tăng rủi ro sai dữ liệu? |
| **Bảo mật** | Negative tests không đạt; sự cố quyền/truy cập. | Có đường chưa bảo vệ? Số sự cố 0 chưa tự chứng minh an toàn. |
| **Vận hành** | Error rate, latency, retry lag, thời gian phục hồi. | Có đạt điều kiện phục vụ đã xác định? |
| **Flow** | WIP, cycle time, throughput, work item age. | Việc có hoàn tất đều hay đang chờ? |
| **Phụ thuộc** | Blocked time theo nguyên nhân, số contract chưa rõ. | Nút thắt ở đâu cần cải tiến? |
| **Rủi ro** | Rủi ro lớn chưa có kiểm chứng/owner, ngày quá hạn trigger. | Các bất định quan trọng có được xử lý kịp không? |
| **Quản trị** | Thời gian chờ quyết định có thẩm quyền, bằng chứng kiểm soát còn thiếu. | Cổng kiểm có cần phân tầng hay tự động hóa không? |

### 24.1. Chỉ số đầu vào, tín hiệu sớm và kết quả trễ

- **Hành động:** đã viết contract tests, đã có telemetry, đã chia lát.
- **Tín hiệu sớm:** số case lỗi được phát hiện trước merge, blocked time, độ trễ sự kiện.
- **Kết quả:** tỷ lệ nộp bài đúng, số lỗi sau release, người học tiếp tục làm bài, mức phục hồi sự cố.

Không nên chỉ đếm số tests hoặc số risk log entries như bằng chứng thành công. Một bộ test có thể nhiều nhưng không kiểm tra **đúng thuộc tính rủi ro cao**.

### 24.2. Ví dụ tính tốc độ phản hồi

Một lát I1 có thời gian minh họa:

| Hoạt động | Thời gian làm việc (ngày) |
| --- | ---: |
| Làm rõ quy tắc và chia lát | 0,5 |
| Chờ quyết định nội dung | 1,0 |
| Code và test | 1,5 |
| Chờ review | 1,0 |
| Tích hợp và DoD | 0,5 |
| Chờ release cho cohort thử | 0,5 |
| Quan sát tác vụ và tổng hợp phản hồi | 1,0 |
| **Tổng** | **6,0** |

Phần **thời gian chờ** ở đây là:

\[
1{,}0+1{,}0+0{,}5=2{,}5\ \text{ngày}
\]

Nếu giảm code từ 1,5 xuống 1 ngày nhưng không thay các hàng chờ, thời gian đến phản hồi chỉ giảm **0,5 ngày**. Nhóm có thể ưu tiên **làm rõ quyết định sớm, review thường xuyên và tạo đường release có kiểm soát**.

Đây là các số liệu **giả định**, không phải chuẩn năng lực hoặc dữ liệu thực của tổ chức.

### 24.3. SLO phải có ngữ nghĩa đo

Một SLO minh họa:

> “Trong điều kiện tải đã định nghĩa, 95% yêu cầu nộp bài hợp lệ hoàn tất xử lý trong dưới 1 giây, đo tại API theo cửa sổ giám sát đã thống nhất, đồng thời không có lỗi phân quyền được biết chưa khắc phục.”

Ngưỡng và percentile trên chỉ là **ví dụ thiết kế**. Phải làm rõ endpoint, phân loại request, cửa sổ thời gian, lỗi nào tính, và mức rủi ro nào đòi dừng. Không nên cộng các p95 của từng service rồi coi kết quả là p95 end-to-end.

## 25. Đánh giá rủi ro cần nhìn xu hướng và bối cảnh, không chỉ số điểm màu đỏ

Một buổi review risk nên hỏi:

1. Những **giả định quan trọng nhất** hiện đã có bằng chứng gì?
2. Có rủi ro nào chuyển từ “có thể xảy ra” sang **issue thực sự**?
3. Kiểm soát hiện tại có phát hiện/sửa lỗi sớm hơn không?
4. Có tạo **rủi ro mới** khi giảm rủi ro cũ không?
5. Rủi ro còn lại có người được quyền chấp nhận và trigger rõ?
6. Có lát nào phát hành được để **học có giá trị hơn** trước khi mở rộng?
7. Có thay đổi scope, nhà cung cấp, luật áp dụng hoặc điều kiện vận hành?
8. Dữ liệu và cách đo có còn nhất quán với giai đoạn trước?
9. Quyết định nào cần thay thế, ngoại lệ nào hết hạn?
10. Hành động cụ thể tới lần kiểm tra tiếp theo là gì?

### 25.1. Lỗi “risk register toàn màu xanh”

Nếu mọi hàng đều xanh trước ngày audit nhưng integration tests vẫn thất bại và người dùng phản ánh lỗi, **tín hiệu thực mới là điều cần xử lý**. Trạng thái risk phải thay đổi theo bằng chứng, không theo nhu cầu trình bày đẹp.

### 25.2. Risk register không nên trở thành danh sách mọi điều có thể sai

Nếu một nhóm nhỏ có 200 mục rủi ro không có owner hoặc hành động, danh sách có thể che những vấn đề quan trọng nhất. Nên ưu tiên **rủi ro có tác động đến quyết định gần**, lưu chi tiết nơi phù hợp và rà soát định kỳ các giả định đã lỗi thời.

### 25.3. Bằng chứng không có nghĩa chắc chắn tuyệt đối

Không ai có thể kiểm thử tất cả trạng thái production. Mục tiêu quản trị là **hiểu giới hạn bằng chứng, áp dụng guardrails tương xứng và đưa ra quyết định chịu trách nhiệm**, không hứa sẽ loại bỏ 100% rủi ro.

## 26. Tình huống hoàn chỉnh: nền tảng học Java cấp chứng nhận trong sáu tuần

Một nhóm sản phẩm có mốc mở chương trình học mới sau **sáu tuần**. Các bên liên quan đề xuất: thi trắc nghiệm, tự chấm, lưu lịch sử, cấp chứng nhận PDF, gửi email, phân quyền giảng viên, bảng xếp hạng và thống kê.

Nhóm chưa biết:

- Người học có cần email chứng nhận ngay hay chỉ cần trang tải chứng nhận?
- Đáp án và trạng thái nộp có rõ khi mạng không ổn định?
- Kết quả có bị lưu hai lần khi request retry?
- API email đối tác có giới hạn nào?
- Ai có quyền xem, sửa hoặc thu hồi chứng nhận?
- Kiểm soát dữ liệu nào là nghĩa vụ bắt buộc?
- Có thể phát hành **một lát an toàn** trước khi toàn bộ tính năng hoàn tất?

### 26.1. Product Goal ứng viên

> “Học viên đủ điều kiện có thể hoàn tất một bài đánh giá Java và nhận bằng chứng hoàn thành chính xác, dễ truy cập, trong khi dữ liệu và quyền được bảo vệ.”

Đây là mục tiêu sản phẩm minh họa, chưa là lời hứa chắc rằng mọi chức năng nâng cao sẽ có trong sáu tuần.

### 26.2. Bản đồ rủi ro và phương án

| Rủi ro | Tác động | Kiểm chứng sớm | Quyết định/ứng phó |
| --- | --- | --- | --- |
| **R1:** học viên không hiểu trạng thái nộp. | Nộp lặp, mất niềm tin. | I1 và usability test. | Sửa UX/lỗi trước mở rộng. |
| **R2:** kết quả bị ghi trùng/sai. | Chứng nhận sai, rework. | Retry/idempotency tests ở I1/I2. | Chặn release nếu tính đúng đắn chưa đạt. |
| **R3:** đọc điểm người khác. | Lộ dữ liệu riêng tư. | Negative tests, security review. | Guardrail bắt buộc, chuyển cấp nếu phát hiện. |
| **R4:** điều kiện chứng nhận chưa thống nhất. | Cấp sai đối tượng. | Example mapping và acceptance tests. | PO làm rõ quy tắc, owner nghiệp vụ xác nhận. |
| **R5:** email vendor không đáng tin. | Chứng nhận chậm, hỗ trợ tăng. | Spike/contract/resilience tests. | Giữ chứng nhận xem được trên web, email là kênh bổ sung nếu được chấp nhận. |
| **R6:** phạm vi lớn trước mốc. | Chưa có Increment dùng được. | Chia lát, theo dõi Done/cycle time. | Ưu tiên I1–I3, thương lượng phần còn lại. |

### 26.3. Lộ trình bàn giao an toàn

| Giai đoạn ứng viên | Increment hoặc phép thử | Bằng chứng cần đạt trước bước kế |
| --- | --- | --- |
| **Tuần đầu** | Phỏng vấn/prototype cho trạng thái nộp; spike API email nếu cần. | Hiểu bất định và giới hạn, chưa gọi prototype là Increment Done. |
| **Giai đoạn 1** | **I1:** nộp một bài ngắn và xem kết quả đúng, tích hợp thật. | DoD, phân quyền, lỗi mạng, quan sát tác vụ. |
| **Giai đoạn 2** | **I2:** xem lại kết quả đã lưu qua phiên. | Toàn vẹn/riêng tư, retry và test tích hợp. |
| **Giai đoạn 3** | **I3:** cấp và xem một chứng nhận hợp lệ. | Quy tắc nghiệp vụ, idempotency, không trùng, review thẩm quyền. |
| **Giai đoạn 4** | **I4:** thông báo qua email nếu hợp đồng và giá trị được xác nhận. | Vendor tests, retry/fallback, chi phí và telemetry. |
| **Sau phản hồi** | Mở rộng câu hỏi, dashboard, huy hiệu nếu ưu tiên. | Bằng chứng người dùng, forecast, rủi ro còn lại. |

**Thứ tự có thể thay đổi.** Nếu test I1 chưa an toàn hoặc người dùng hiểu sai trạng thái, nhóm **không thể chỉ tiếp tục chạy lịch I2–I4 và bỏ qua tín hiệu**.

### 26.4. Luồng rủi ro được xử lý trong quá trình làm

~~~mermaid
sequenceDiagram
    actor Learner as Học viên
    participant UI as Giao diện
    participant Exam as Assessment
    participant Cert as Certificate
    participant Email as Email provider

    Learner->>UI: Nộp bài đánh giá Java
    UI->>Exam: Submit attempt với quyền hợp lệ
    Exam->>Exam: Kiểm tra quyền, dữ liệu, idempotency
    Exam-->>UI: Kết quả hoặc trạng thái lỗi rõ
    Exam->>Cert: Yêu cầu chứng nhận khi đủ điều kiện
    Cert->>Cert: Kiểm tra điều kiện, chống trùng và lưu dữ liệu
    Cert-->>UI: Chứng nhận có thể xem theo quyền
    Cert->>Email: Thử gửi thông báo nếu được bật
    alt Email thành công
       Email-->>Cert: Xác nhận nhận yêu cầu
    else Email timeout/lỗi
       Email-->>Cert: Lỗi hoặc chưa xác nhận
       Cert->>Cert: Ghi trạng thái retry và cảnh báo phù hợp
    end
~~~

Sơ đồ chỉ minh họa kiến trúc có thể có. Trong một hệ thống thực, đường gửi email có thể bất đồng bộ sau commit, phải xử lý outbox, bản tin trùng, thứ tự, quyền truy cập và các tác dụng phụ. **Không giả định mọi lần gọi HTTP phải đi tuần tự như sơ đồ**, và không coi thông báo email là nguồn xác nhận cấp chứng nhận duy nhất.

### 26.5. Sprint Review kiểm tra điều gì?

Ở mỗi Sprint, các bên xem:

- Increment nào **thực sự Done**, có thể dùng được?
- Giá trị cho học viên nào đã được kiểm chứng?
- Rủi ro lớn nào đã được giảm bởi **bằng chứng**, rủi ro nào còn mở?
- Những giả định nào đã sai hoặc thay đổi?
- Nếu sáu tuần không đủ toàn bộ phạm vi, nên ưu tiên **lát nào**?
- Những điều kiện release bắt buộc và quyền quyết định đã rõ chưa?

**Không dùng Sprint Review để hợp thức hóa việc hạ DoD** hoặc coi bản demo prototype là chứng cứ sản phẩm đã an toàn.

### 26.6. Phản hồi dẫn đến đổi hướng

Giả sử I1 cho thấy học viên hiểu trạng thái nộp nhưng **nhiều người không biết vì sao họ sai**. PO có thể ưu tiên một lát lời giải do giảng viên biên soạn trước bảng xếp hạng. Nếu I3 an toàn và chứng nhận có thể xem trên web, nhưng email vendor chậm và người học không thật sự quan tâm email, nhóm có thể hoãn I4.

**Đây là rủi ro giá trị được giảm bằng học hỏi**, không phải “lệch kế hoạch” cần che khỏi stakeholder.

### 26.7. Đường xử lý khi test phát hiện sai quyền

Nếu negative test cho thấy học viên có thể truy cập kết quả người khác, rủi ro **không còn là suy đoán**. Nhóm phải:

1. Đánh dấu kết quả kiểm thử và ảnh hưởng rõ.
2. Chặn release phần bị ảnh hưởng; nếu đã production, dùng quy trình sự cố.
3. Xác định phạm vi lỗ hổng và dữ liệu bị tác động theo thẩm quyền.
4. Sửa, bổ sung regression tests và xác minh độc lập phù hợp.
5. Cập nhật risk/issue log, quyết định và người cần thông báo theo chính sách.
6. Chỉ mở lại khi điều kiện an toàn và phê duyệt áp dụng được đáp ứng.

Không có cơ chế “cho 10 người dùng thử” hợp lệ nếu đã biết đường truy cập trái quyền.

## 27. Tình huống biên: khi bàn giao nhỏ không đơn giản

### 27.1. Thay đổi dữ liệu khó đảo ngược

Giả sử nhóm đổi khóa định danh chứng nhận. Nếu đã ghi dữ liệu mới, **rollback mã** chưa chắc hoàn tác dữ liệu hay tương thích với phiên bản cũ. Một kế hoạch an toàn có thể dùng **expand–migrate–contract**:

1. Mở đường hỗ trợ cả dữ liệu cũ và mới.
2. Chuyển consumer dần theo hợp đồng tương thích.
3. Đối soát dữ liệu trong quá trình migration.
4. Chuyển hướng đọc/ghi khi kiểm chứng đạt.
5. Chỉ bỏ hỗ trợ cũ khi không còn phụ thuộc hợp lệ.

Với dữ liệu đã tác động bên ngoài, có thể cần **compensating action**, không giả định luôn có nút hoàn tác hoàn hảo.

### 27.2. Sự kiện có thể đến trùng hoặc sai thứ tự

Ở hệ thống giao nhận bản tin có thể lặp, consumer cần **idempotency** và quy tắc xử lý sự kiện trùng, tới muộn hoặc sai thứ tự. Không nên hứa “exactly once trong mọi điều kiện” chỉ vì thư viện có tùy chọn tên như vậy.

Kiểm thử với duplicate, replay, mất kết nối và đối soát dữ liệu giúp **giảm rủi ro sớm** trước rollout nhiều người.

### 27.3. Một dependency khiến Increment chưa thể đứng riêng

Nếu chứng nhận cần chữ ký bên thứ ba, nhóm có thể làm prototype hoặc spike để học trước, nhưng không nên báo Increment cấp chứng nhận **đã Done** khi hợp đồng ký thực tế chưa hoạt động và điều đó là điều kiện của sản phẩm.

Có thể chọn **lát khác có giá trị thật** ít phụ thuộc hơn, hoặc làm rõ phụ thuộc trước. Bàn giao nhỏ không có nghĩa giả mạo trạng thái hoàn tất.

### 27.4. Sản phẩm có ràng buộc nghiêm ngặt

Trong môi trường điều chỉnh bởi hợp đồng, dữ liệu hoặc quy định đặc biệt, một số kiểm tra và phê duyệt có thể không được rút ngắn tùy tiện. Agile có thể **rút ngắn chu kỳ chuẩn bị bằng chứng**, tích hợp kiểm soát vào CI và phát hiện sai sớm; **không được thay thẩm quyền hợp pháp bằng vote trong Sprint**.

### 27.5. Thử nghiệm gây ảnh hưởng không công bằng

Nếu chỉ thử trên học viên dùng thiết bị cao cấp, phản hồi có thể bỏ sót người học dùng thiết bị phổ thông hoặc công nghệ hỗ trợ. Chọn cohort phải cân nhắc **mục tiêu, khả năng tiếp cận, quyền tham gia và bias**.

### 27.6. Khủng hoảng sản phẩm làm thay đổi thứ tự

Nếu production phát hiện lỗi phân quyền, nhóm có thể cần ưu tiên xử lý issue trước tính năng mới. Velocity giảm không tự động là thất bại, vì **bảo vệ người dùng và giảm rủi ro hệ thống** có thể tạo giá trị rất lớn dù không tăng số điểm Sprint.

## 28. Anti-patterns khi gọi “Agile” nhưng quản lý rủi ro kém

| Anti-pattern | Vì sao gây hại | Cách thay |
| --- | --- | --- |
| **Risk register chỉ cập nhật trước audit** | Rủi ro không được theo dõi khi quyết định còn rẻ. | Link risk với PBI, trigger, DoD và release. |
| **Mọi thứ đều ghi risk mức trung bình** | Che rủi ro cao, không tạo thứ tự xử lý. | Xác định tác động, bất định và bằng chứng cụ thể. |
| **Chia việc theo tầng rồi gọi là Increment** | Chưa có hành vi đầu cuối, phản hồi tích hợp muộn. | Chia lát dọc có thể sử dụng. |
| **Prototype được báo “Done production”** | Stakeholder tưởng phần mềm đã kiểm chứng chất lượng. | Phân biệt prototype/spike và Increment đạt DoD. |
| **“MVP” là bản bỏ kiểm tra quyền** | Rủi ro mất niềm tin, dữ liệu và nghĩa vụ. | Giảm tính năng, không hạ an toàn. |
| **Release nhanh bằng cách bỏ CI** | Lỗi hồi quy và rework tăng. | Giữ DoD, tự động hóa kiểm tra phù hợp. |
| **Một lần thử nhỏ rồi khẳng định thành công** | Mẫu không đại diện hoặc kết quả bị confounding. | Kết hợp định tính, định lượng và bối cảnh. |
| **Chỉ dùng điểm rủi ro 1–5 để tính xác suất** | Tạo độ chính xác giả. | Dùng thang định tính có giải thích; số học khi có cơ sở. |
| **Không có risk owner** | Không ai theo dõi bằng chứng và hành động. | Gán owner và checkpoint. |
| **Owner tự cấp mọi ngoại lệ** | Quyền chấp nhận rủi ro có thể không đúng. | Phân định action owner và risk acceptance authority. |
| **Người dùng thử chịu rủi ro đã biết** | Vi phạm an toàn dù cohort nhỏ. | Chặn release, kiểm chứng trước. |
| **Coi feature flag là rollback dữ liệu** | Dữ liệu/sự kiện đã phát không tự hoàn tác. | Kế hoạch migration, đối soát, compensation. |
| **Chọn toàn event-driven vì “hiện đại”** | Có thể thêm lag/retry/chi phí vận hành không cần thiết. | Chọn theo yêu cầu nhất quán, rủi ro và năng lực. |
| **Chỉ nhìn velocity** | Bỏ qua chất lượng, WIP, sự cố và giá trị. | Dùng flow, guardrails và outcome. |
| **Họp duyệt mọi thay đổi nhỏ** | Hàng chờ quyết định lớn, phản hồi chậm. | Phân tầng quyền và kiểm soát theo rủi ro. |
| **Không có đường chuyển cấp** | Issue/risk nghiêm trọng bị treo. | Trigger, owner, incident process. |
| **Đặt deadline thay estimate** | Ép hạ DoD và che bất định. | Forecast có điều kiện, thương lượng scope. |
| **Không thay backlog dù giả thuyết sai** | Nhận phản hồi nhưng vẫn xây thứ ít giá trị. | PO và nhóm kiểm tra lại thứ tự đầu tư. |
| **Lẫn Done với Released** | Báo giá trị đã đến người dùng khi còn tắt flag. | Tách trạng thái và kế hoạch feedback. |
| **Chỉ tối ưu số bug được phát hiện** | Có thể khuyến khích tạo/đếm lỗi thay vì giảm hậu quả. | Theo dõi mức nghiêm trọng, phòng ngừa và kết quả. |
| **Ghi “risk closed” sau một test Green** | Che giới hạn của phép kiểm và rủi ro còn lại. | Ghi bằng chứng, phạm vi và residual risk. |
| **Giữ mọi ngoại lệ vô thời hạn** | Guardrail bị vô hiệu trong thực tế. | Scope, owner, expiry/review. |

## 29. Mẫu kế hoạch bàn giao theo rủi ro — dùng được ngay

Mẫu dưới đây có thể là một trang ngắn liên kết tới backlog và decision log. Không phải hiện vật bắt buộc của Scrum.

~~~text
RISK-BASED INCREMENT PLAN

SẢN PHẨM / PRODUCT GOAL:
  Ai được phục vụ và kết quả gì cần đạt?

PHẠM VI LÁT HIỆN TẠI:
  Người dùng có thể làm hành vi cụ thể nào?
  Điều gì chưa làm nhưng không ảnh hưởng tính đúng đắn trong phạm vi?

RỦI RO QUAN TRỌNG:
  ID:
  Nguyên nhân / sự kiện / tác động:
  Bất định hiện tại và bằng chứng đang có:
  Risk owner / action owner / người có thẩm quyền quyết định:

GIẢ THUYẾT CẦN KIỂM CHỨNG:
  Nếu làm X cho nhóm Y, chúng ta kỳ vọng quan sát điều Z.
  Điều gì có thể khiến giả thuyết sai?

PHÉP KIỂM:
  Prototype, spike, acceptance test, security test,
  contract test, integration, usability test hay rollout?

TIÊU CHÍ HOÀN TẤT:
  Acceptance criteria:
  Definition of Done:
  Guardrails chất lượng, quyền, dữ liệu, vận hành:

PHÁT HÀNH:
  Phạm vi cohort và điều kiện mở:
  Quyền quyết định:
  Telemetry/feedback:
  Điều kiện dừng, rollback, khôi phục/đối soát:
  Người xử lý sự cố:

RỦI RO CÒN LẠI:
  Còn điều gì chưa được loại bỏ?
  Ai có quyền chấp nhận trong phạm vi nào?
  Trigger/checkpoint xem lại:

QUYẾT ĐỊNH TIẾP:
  Tiếp tục, sửa, giới hạn, mở rộng, dừng?
  PBI/ADR/decision nào cần cập nhật?
~~~

### Tại sao mẫu ngắn hữu ích?

- Giúp nhìn rõ **rủi ro nào đang được xử lý bởi lát nào**.
- Ngăn nhầm prototype với Increment.
- Kết nối acceptance criteria, DoD, release và thẩm quyền.
- Buộc nhóm nói về **rủi ro còn lại và phản hồi** sau thử nghiệm.
- Tránh lập một bảng risk độc lập không bao giờ ảnh hưởng thứ tự Product Backlog.

Nếu mỗi PBI nhỏ đã có thông tin đầy đủ trong công cụ chung, chỉ cần liên kết thay vì sao chép lại biểu mẫu.

## 30. Workshop: từ epic lớn thành chuỗi rủi ro giảm dần

Một workshop có thể gồm Product Owner, Developers, người hiểu nghiệp vụ, QA và những chuyên gia rủi ro liên quan. Scrum Master hoặc người hỗ trợ phối hợp có thể giúp cuộc trao đổi tập trung.

### Bước 1 — Chọn kết quả người dùng

Viết:

> “Chúng ta muốn **[nhóm người dùng]** đạt được **[kết quả]** vì hiện họ gặp **[vấn đề quan sát]**.”

Tránh mở bằng “triển khai toàn bộ hệ thống công nghệ X”.

### Bước 2 — Viết giả định và rủi ro lớn nhất

Mỗi người ghi:

- Rủi ro giá trị/nhu cầu.
- Rủi ro sử dụng và khả năng tiếp cận.
- Rủi ro nghiệp vụ/tính đúng đắn.
- Bảo mật/dữ liệu/tuân thủ.
- Tích hợp/đối tác và vận hành.
- Giao hàng/capacity/điểm nghẽn tổ chức.

Gom nhóm, chọn **ít mục tác động lớn và chưa đủ bằng chứng** trước, không cố chấm điểm mọi khả năng trong vũ trụ.

### Bước 3 — Gắn bằng chứng cho mỗi rủi ro

Hỏi: **“Bằng chứng rẻ nhất đủ đáng tin để thay đổi quyết định là gì?”** Với giá trị có thể phỏng vấn trước khi code; với tính đúng đắn phải kiểm thử; với quyền riêng tư phải đáp ứng kiểm soát chính thức.

### Bước 4 — Vẽ hành trình người dùng

Ví dụ:

> Mở bài → nộp → xem kết quả → hiểu điều kiện hoàn thành → nhận chứng nhận → xem lại.

Tìm **lát đầu cuối nhỏ nhất có thể hoàn tất và dùng được**, không chia cơ học theo DB/API/UI.

### Bước 5 — Định nghĩa guardrail và DoD

Từng lát cần trả lời: điều gì bắt buộc đúng ngay? Điều gì chưa làm nhưng có thể bỏ khỏi phạm vi mà không gây hiểu nhầm hoặc mất an toàn?

### Bước 6 — Chọn release và kênh phản hồi

Làm rõ đối tượng, thẩm quyền, môi trường, telemetry, điều kiện dừng/khôi phục và người xem kết quả.

### Bước 7 — Ghi quyết định và rủi ro còn lại

Mỗi lát/experiment phải có:

- Owner của hành động/rủi ro.
- Bằng chứng cần thu.
- Trigger và checkpoint.
- Lựa chọn tiếp tục/sửa/mở rộng/dừng.
- Liên kết tới backlog, test và decision record.

### Bước 8 — Xem lại sau Increment, không đợi kết thúc roadmap

Nếu bằng chứng mới làm thay ưu tiên, PO cập nhật thứ tự backlog trong Scrum, Developers điều chỉnh cách triển khai và nhóm giữ các ràng buộc cần thiết.

## 31. Bài tập tình huống: mở tính năng nộp bài và chứng nhận cho ba trường

Một công ty cung cấp nền tảng học Java chuẩn bị mở tính năng thi cuối khóa cho **ba trường học**. Mốc khai giảng còn **năm tuần**. Product Owner muốn có một trải nghiệm đáng tin; quản lý hợp đồng muốn báo cáo đúng thời hạn; Developers muốn giảm rủi ro tích hợp.

### Dữ liệu bài tập

1. Epic gồm nộp bài trắc nghiệm, chấm tự động, lưu điểm, cấp PDF chứng nhận, gửi email, dashboard giáo viên và xác minh chứng nhận.
2. API của nhà cung cấp email chưa có sandbox đáng tin; tài liệu retry chưa rõ.
3. Hai nhóm dùng cùng dữ liệu điểm nhưng chưa xác định ai có quyền ghi và sửa.
4. Người học có thể nộp lại do mạng chập chờn; hiện chưa có kiểm thử duplicate.
5. Trang kết quả cho phép truyền learnerId qua URL; chưa có negative authorization test.
6. Trước đây hệ thống từng báo “Nộp thành công” dù request lưu điểm timeout.
7. Một nhóm nhỏ học viên phản ánh khó hiểu điều kiện để có chứng nhận; chưa có thử nghiệm theo tác vụ.
8. CI có unit tests, nhưng integration suite cho luồng nộp chưa được chạy trong mỗi merge.
9. Quản lý muốn mọi PBI được ghi “80% Done” để chứng minh tiến độ.
10. Nhóm có một cuộc họp phê duyệt release duy nhất vào tuần thứ năm, không có tiêu chí rõ.
11. Một deadline với ba trường là nghĩa vụ hợp đồng thật, nhưng chưa có định nghĩa “phạm vi tối thiểu phải có” cho mốc này.
12. Có người đề xuất bật tính năng cho 5% học viên dù test quyền chưa đạt, vì “canary sẽ giới hạn thiệt hại”.
13. Product Owner đã xếp dashboard giáo viên trước chức năng xử lý lỗi nộp bài vì stakeholder cấp cao yêu cầu.
14. Chưa có owner rõ cho những rủi ro bảo mật và quyết định chấp nhận rủi ro còn lại.

### Nhiệm vụ

1. Phân biệt **risk, issue, assumption, dependency và constraint** từ những dữ kiện trên; mỗi loại ít nhất một ví dụ.
2. Viết **Product Goal** có thể kiểm tra, gắn với học viên và độ tin cậy.
3. Chọn **năm rủi ro lớn**, nêu nguyên nhân, tác động và phương án kiểm chứng.
4. Chia epic thành **bốn Increment dọc** và ít nhất một spike/prototype; mô tả hành vi sau mỗi Increment.
5. Chỉ ra những điều **không được để sang Increment sau** vì là điều kiện an toàn của lát hiện tại.
6. Viết **ba acceptance scenarios**, bao gồm retry/duplicate, quyền truy cập và timeout.
7. Chọn cách xử lý nhà cung cấp email khi chưa rõ hợp đồng; nêu fallback và tiêu chí không phụ thuộc vendor.
8. Thiết kế **release theo giai đoạn** với stop conditions và người có quyền quyết định.
9. Đề xuất cấu trúc **risk register** có owner và trigger; chỉ rõ ai có quyền chấp nhận rủi ro.
10. Nếu mốc năm tuần không đủ toàn bộ epic, chọn phương án **giảm phạm vi an toàn**.
11. Nêu hai số đo flow, hai số đo chất lượng, một outcome giá trị và một cách thu phản hồi định tính.
12. Trả lời đề xuất “80% Done” và “mở 5% dù chưa đạt test quyền” bằng lập luận Agile.
13. Mô tả cách đưa rủi ro vào Sprint Planning, Daily Scrum, Sprint Review và Retrospective mà không biến các sự kiện thành cổng hành chính.
14. Viết một cập nhật cho stakeholder gồm bằng chứng, điều chưa biết, lựa chọn và quyết định cần chốt.

## 32. Hướng giải tham khảo cho bài tập

### 32.1. Phân loại sự kiện và mục tiêu

| Dữ kiện | Cách phân loại phù hợp |
| --- | --- |
| Retry chưa được kiểm chứng có thể lưu điểm trùng. | **Risk** về toàn vẹn dữ liệu. |
| Hệ thống từng báo nộp thành công trong khi lưu timeout, nếu lỗi vẫn tồn tại. | **Issue/defect** cần xác minh và xử lý. |
| Học viên chắc chắn muốn email ngay lập tức. | **Assumption** về giá trị chưa có bằng chứng. |
| Nhà cung cấp email chưa rõ API và sandbox. | **Dependency** đồng thời tạo risk tích hợp. |
| Không được để người không có quyền xem điểm người khác. | **Constraint/guardrail** bảo mật. |
| Mốc năm tuần theo hợp đồng. | **Constraint** về thời gian, tạo risk nếu scope không khả thi. |

**Product Goal minh họa:**

> “Học viên của các trường tham gia có thể nộp bài đánh giá Java và nhận kết quả chính xác, được bảo vệ; những người đủ điều kiện có thể truy cập chứng nhận hợp lệ với trạng thái minh bạch.”

Không cần ép mọi tính năng dashboard, email và xác minh nâng cao nằm trong Product Goal đầu nếu chưa được xác nhận là giá trị cốt lõi.

### 32.2. Năm rủi ro và phép kiểm chứng

| Rủi ro | Tác động | Kiểm chứng/hành động |
| --- | --- | --- |
| **R1 — lỗi phân quyền qua learnerId** | Lộ điểm và thông tin riêng tư. | Negative tests, review chính sách, chặn release khi chưa đạt. |
| **R2 — duplicate khi retry** | Lưu điểm hoặc cấp chứng nhận trùng. | Idempotency/transaction tests, đối soát. |
| **R3 — trạng thái nộp sai khi timeout** | Người học mất niềm tin và nộp lại. | Acceptance/integration tests lỗi mạng, thiết kế UI trạng thái. |
| **R4 — email vendor không đáng tin** | Thông báo trễ, hỗ trợ tăng. | Spike sandbox, contract/resilience tests, fallback. |
| **R5 — scope quá lớn trước mốc** | Không có Increment dùng được, ảnh hưởng hợp đồng. | Chia lát, forecast cập nhật, làm rõ scope bắt buộc. |

Nên xem thêm rủi ro quy tắc chứng nhận chưa rõ và chủ sở hữu dữ liệu điểm; năm mục chỉ là **bài tập ưu tiên**, không có nghĩa các rủi ro khác được bỏ qua.

### 32.3. Lát dọc và khám phá

- **Prototype:** màn hình trạng thái nộp, cho học viên thực hiện tác vụ và diễn đạt hiểu biết; chưa gọi là Increment Done.
- **Spike:** kết nối vendor sandbox/contract và thử timeout, giới hạn thời gian, có quyết định sau thử.
- **I1:** học viên có quyền nộp một bài trắc nghiệm ngắn, được chấm và xem phản hồi đúng, xử lý timeout/duplicate/permission trong phạm vi.
- **I2:** học viên xem lại kết quả đã ghi qua phiên; quyền và toàn vẹn được bảo vệ.
- **I3:** người đủ điều kiện được cấp và xem **một chứng nhận hợp lệ**, không trùng và có cơ chế kiểm tra/thu hồi trong phạm vi chính sách bắt buộc.
- **I4:** nếu giá trị/hợp đồng phù hợp, gửi thông báo email hoặc mở rộng trải nghiệm, có retry/quan sát và fallback.

Một câu trả lời khác có thể được chấp nhận nếu **mỗi lát thật sự có thể sử dụng, đạt DoD, an toàn và giảm rủi ro quan trọng**.

### 32.4. Gherkin cho ba rủi ro

~~~gherkin
Feature: Nộp bài thi Java đáng tin và riêng tư

Scenario: Một yêu cầu nộp bài bị gửi lại
  Given học viên có quyền và đã nộp hợp lệ request "req-42"
  And hệ thống đã ghi kết quả của request đó
  When request "req-42" được gửi lại do retry
  Then hệ thống tuân thủ chính sách idempotency đã thống nhất
  And không tạo dữ liệu kết quả trùng trái quy tắc

Scenario: Không được xem điểm người khác
  Given tài khoản không có quyền xem kết quả của học viên khác
  When tài khoản đó yêu cầu điểm bằng learnerId của người khác
  Then hệ thống từ chối theo chính sách
  And không tiết lộ điểm hoặc đáp án riêng tư

Scenario: Timeout khi nộp bài
  Given học viên được phép làm bài
  And hệ thống chưa thể xác nhận đã ghi kết quả
  When request nộp bài bị timeout
  Then giao diện không báo sai rằng bài đã nộp thành công
  And cung cấp trạng thái và hướng thử lại hoặc kiểm tra kết quả phù hợp
~~~

### 32.5. Vendor, release và quyền quyết định

**Vendor:** không chặn toàn bộ giá trị người học vào email nếu có đường xem chứng nhận trên web được chấp nhận. Làm spike và xác minh hợp đồng, thử lỗi mạng, retry, giới hạn tốc độ, đối soát; chỉ đưa email vào scope bắt buộc nếu hợp đồng/giá trị thật yêu cầu.

**Release theo giai đoạn:** sau khi Increment đạt DoD và điều kiện tổ chức, mở cho cohort nhỏ được phép, theo dõi lỗi, quyền, kết quả và phản hồi. **Dừng release** khi có lỗi phân quyền, tính đúng đắn, chứng nhận trùng hoặc vi phạm guardrail đã thống nhất. Người có thẩm quyền phát hành và risk acceptance được chỉ định theo tổ chức; PO quản lý giá trị/thứ tự backlog, Developers bảo đảm chất lượng Increment.

**Mốc năm tuần:** làm rõ phạm vi tối thiểu theo hợp đồng với người có quyền, ưu tiên nộp bài đúng và truy cập kết quả/chứng nhận hợp lệ, xem email/dashboard là ứng viên có thể tách nếu không bắt buộc. Nếu cả phạm vi tối thiểu không khả thi an toàn, **báo sớm và thương lượng lựa chọn**, không hứa theo cảm giác.

### 32.6. Dữ liệu và phản hồi

- **Flow:** cycle time Started → Done; blocked time chờ quyền/hợp đồng vendor.
- **Chất lượng:** lỗi chấm/lưu sai hoặc cấp trùng; thất bại negative authorization tests/sự cố quyền.
- **Outcome:** tỷ lệ học viên hoàn tất nộp bài hợp lệ và hiểu trạng thái trong tác vụ được định nghĩa, không suy từ số click.
- **Định tính:** quan sát học viên thực hiện luồng nộp trong phạm vi được phép; hỏi họ hiểu “Đã nộp” và bước tiếp theo thế nào.

**“80% Done”** có thể diễn đạt tiến bộ nội bộ nhưng **không được thay DoD**, không phải cơ sở ghi Increment. **Mở 5% dù biết test quyền thất bại** là không phù hợp: quy mô nhỏ không cho phép làm hại dữ liệu và quyền người học.

### 32.7. Báo cáo stakeholder mẫu

> “Mục tiêu mốc năm tuần là người học nộp bài đúng và xem kết quả/chứng nhận hợp lệ theo quyền. Chúng tôi đã xác định các rủi ro ưu tiên: phân quyền learnerId, retry/duplicate, trạng thái nộp khi timeout, phụ thuộc email và phạm vi. Chưa chấp nhận release khi kiểm thử quyền chưa đạt. Nhóm đang thực hiện I1 kèm kiểm thử và spike vendor; chúng tôi đề xuất chốt phạm vi hợp đồng tối thiểu, cân nhắc dời email/dashboard nếu không bắt buộc, rồi cập nhật forecast khi có kết quả tích hợp. Quyết định cần người có thẩm quyền xác nhận là phạm vi release theo hợp đồng và cách xử lý residual risk vendor.”

Đó là một báo cáo **có bằng chứng, điều chưa biết, lựa chọn và quyết định**, không biến rủi ro thành phần trăm tiến độ giả.

## 33. Tự kiểm tra kiến thức

**Câu 1.** Vì sao một Increment nhỏ có thể giảm rủi ro hơn gói chức năng lớn?

**Đáp án:** Nó cho phép tích hợp, kiểm thử, giao giá trị và kiểm chứng giả định khi chi phí thay đổi còn thấp; tuy nhiên chỉ có ích nếu lát có thể sử dụng và đáp ứng chất lượng.

**Câu 2.** Bàn giao nhỏ có nghĩa có thể hoãn phân quyền tới Sprint sau không?

**Đáp án:** Không. Ràng buộc an toàn và DoD áp dụng cho lát hiện tại không được hạ vì muốn nhanh.

**Câu 3.** Một prototype giao diện đẹp đã chạy có được coi là Increment Done?

**Đáp án:** Không tự động. Prototype chủ yếu giúp khám phá; Increment phải tích hợp, có thể sử dụng và đạt Definition of Done.

**Câu 4.** Risk khác issue ở điểm nào?

**Đáp án:** Risk là điều không chắc có thể ảnh hưởng mục tiêu; issue là vấn đề đã xảy ra cần xử lý. Risk được hiện thực hóa có thể trở thành issue/incident.

**Câu 5.** Vì sao risk owner không tự động là người có quyền chấp nhận mọi rủi ro còn lại?

**Đáp án:** Theo dõi và xử lý là trách nhiệm khác với quyền phê duyệt an toàn, hợp đồng hoặc tuân thủ. Cần cơ chế thẩm quyền của tổ chức.

**Câu 6.** Nếu rollout 1% vẫn có khả năng lộ dữ liệu trái quyền đã biết, có nên mở không?

**Đáp án:** Không. Canary chỉ giảm số người tiếp xúc, không hợp thức hóa vi phạm quyền hoặc thiếu DoD bắt buộc.

**Câu 7.** Có thể khẳng định “nguy cơ bằng 3 × 4 = 12” là xác suất 12% không?

**Đáp án:** Không. Điểm ordinal định tính không tự có đơn vị xác suất hay tiền. Cần giải thích mức và bằng chứng; định lượng thật phải có cơ sở.

**Câu 8.** Phản hồi của 20 học viên có thể chứng minh tính năng tăng hiệu quả học tập toàn bộ sản phẩm không?

**Đáp án:** Không tự động. Cần xem cách chọn mẫu, hành vi thực, độ khó, ngữ cảnh và phương pháp đánh giá; dữ liệu nhỏ có thể đủ phát hiện lỗi usability nhưng chưa chứng minh nhân quả rộng.

**Câu 9.** Vì sao cần phân biệt Done với Released?

**Đáp án:** Done cho biết Increment đạt DoD; Released cho biết chức năng đã mở tới người dùng. Không thể suy người học đã nhận giá trị chỉ từ trạng thái Done.

**Câu 10.** Rủi ro đối tác email nên kiểm chứng bằng gì?

**Đáp án:** Hợp đồng, integration/sandbox tests, timeout/retry, hạn mức, khả năng đối soát, giám sát vận hành; đồng thời xem đường fallback và giá trị email đối với người học.

**Câu 11.** Nếu có deadline hợp đồng thật, Agile nên làm gì?

**Đáp án:** Làm rõ mốc và phạm vi bắt buộc, chia lát giá trị, forecast có điều kiện, kiểm chứng rủi ro sớm và thương lượng phạm vi/giải pháp; không bỏ an toàn hoặc gọi estimate thành lời hứa chắc chắn.

**Câu 12.** Có phải mọi risk cần một cuộc họp hội đồng kiến trúc?

**Đáp án:** Không. Phân tầng quyết định theo tác động, thẩm quyền và khả năng đảo ngược; local risk có thể xử lý bằng test/CI, high-risk cần tham vấn/phê duyệt tương ứng.

**Câu 13.** Tại sao “CI Green” không đồng nghĩa rủi ro đã biến mất?

**Đáp án:** Kiểm thử có phạm vi và giới hạn; còn rủi ro chưa thử, vận hành thật, dữ liệu và các điều kiện thay đổi. Cần nêu residual risk, trigger và giám sát.

**Câu 14.** Kanban giúp giảm rủi ro bằng cách nào?

**Đáp án:** Làm rõ WIP, blocked, cycle time và tuổi công việc; phát hiện hàng chờ để ưu tiên hoàn tất/integrate thay vì bắt đầu thêm nhiều việc.

**Câu 15.** Tại sao Product Backlog phải thay đổi sau phản hồi?

**Đáp án:** Bằng chứng mới có thể thay giả định về giá trị và rủi ro. PO cần cân nhắc thứ tự mới để tối đa hóa giá trị và thích ứng, không chỉ thực hiện roadmap ban đầu.

**Câu 16.** Đo nhiều lỗi trong CI hơn có chắc chứng minh chất lượng tệ đi không?

**Đáp án:** Không. Có thể kiểm soát mới phát hiện lỗi sớm hơn. Cần xem mức nghiêm trọng, lỗi sau release, loại việc và xu hướng cùng bối cảnh.

## 34. Checklist quản lý rủi ro theo Increment

### Vấn đề, mục tiêu và giả định

- [ ] Product Goal và người dùng chịu ảnh hưởng được mô tả rõ.
- [ ] Rủi ro ưu tiên có nguyên nhân, sự kiện, tác động và bằng chứng hiện tại.
- [ ] Risk, issue, assumption, dependency và constraint không bị trộn lẫn.
- [ ] Có chủ sở hữu rủi ro, hành động, trigger và checkpoint.
- [ ] Các nghĩa vụ và thẩm quyền bắt buộc được xác định.
- [ ] Biết giả thuyết nào nếu sai sẽ làm đổi quyết định đầu tư.

### Chia lát và kiểm soát chất lượng

- [ ] Lát là hành vi đầu cuối có thể dùng, không chỉ một task kỹ thuật.
- [ ] Phạm vi được giới hạn rõ, không gây hiểu nhầm hoặc mất an toàn.
- [ ] Acceptance criteria có trường hợp chính, lỗi và rủi ro quan trọng.
- [ ] DoD được áp dụng đầy đủ; không dùng “gần xong” thành Done.
- [ ] Phân quyền, dữ liệu, retry, hợp đồng và vận hành được kiểm chứng theo rủi ro.
- [ ] Prototype/spike được gọi đúng tên, không báo Increment production giả.
- [ ] Contract với đối tác và phụ thuộc được thử đủ sớm.
- [ ] Increment mới tích hợp được với những phần đã Done trước.

### Release và phản hồi

- [ ] Có quyền quyết định release và điều kiện chất lượng minh bạch.
- [ ] Đối tượng dùng thử được xác định, có quyền và thông tin phù hợp.
- [ ] Có telemetry và cách hỏi/quan sát đáp ứng câu hỏi cần học.
- [ ] Có stop conditions, owner và đường xử lý incident.
- [ ] Tắt flag/rollback không bị hiểu nhầm là đã phục hồi dữ liệu.
- [ ] Không đưa rủi ro đã biết về quyền/riêng tư tới production chỉ để “học”.
- [ ] Phản hồi có được liên kết và dùng để đổi thứ tự Product Backlog?
- [ ] Cách đo có nguồn, đơn vị, cửa sổ và giới hạn suy diễn rõ.

### Quản trị và cải tiến

- [ ] Người giữ risk log khác quyền chấp nhận rủi ro nếu chính sách quy định.
- [ ] Residual risk có lý do, thẩm quyền và điều kiện xem lại.
- [ ] Không phải mọi thay đổi đều chờ hội đồng phê duyệt nếu rủi ro nhỏ.
- [ ] Vấn đề nghiêm trọng được chuyển cấp tức thời theo quy trình.
- [ ] Có forecast theo scope/capacity/bằng chứng, không ép points thành deadline.
- [ ] Theo dõi flow, blocked time, chất lượng và outcome ở cấp hệ thống.
- [ ] Thử một cải tiến nhỏ rồi kiểm tra hiệu quả, không chỉ ghi trong Retrospective.
- [ ] Ngoại lệ hết hạn hoặc quyết định cũ được thay thế có lưu dấu vết.

Checklist là **công cụ thảo luận và quyết định**, không phải quy trình điền biểu mẫu mới cho mọi sửa đổi nhỏ. Những kiểm soát bắt buộc vẫn phải giữ, còn phần thủ tục có thể tinh gọn dựa trên tác động.

## 35. Ghi nhớ trọng tâm

- **Rủi ro là bất định có tác động tới mục tiêu**, khác issue đã xảy ra, giả định, phụ thuộc và ràng buộc.
- **Bàn giao nhỏ giảm chi phí phát hiện sai muộn** khi mỗi lát thật sự tích hợp, có thể dùng và đạt DoD.
- **Phản hồi sớm không chỉ từ người dùng**: acceptance tests, security reviews, contract tests, dữ liệu vận hành và đối soát đều giúp giảm bất định.
- **Ưu tiên giả định tác động lớn, chưa đủ bằng chứng**, nhưng không đem nghĩa vụ an toàn bắt buộc ra thử trên người dùng.
- **Prototype, spike, MVP, Increment, deployment và release không đồng nghĩa**; phải báo cáo đúng mức độ hoàn tất.
- **Chia lát dọc theo hành vi**, không chỉ chia DB/API/UI rồi dồn tích hợp cuối.
- **Guardrails bảo vệ quyền, dữ liệu, chất lượng và tuân thủ ngay ở lát đầu**, không hạ DoD để tăng velocity.
- **Release theo giai đoạn giới hạn mức phơi nhiễm**, nhưng không thay bảo mật, kiểm thử hoặc thẩm quyền.
- **Risk register cần owner, evidence, action, trigger và checkpoint**, không phải danh sách màu được làm đẹp trước audit.
- **Thẩm quyền quyết định và chấp nhận residual risk phải rõ**; PO/Developers/SM giữ accountabilities của Scrum nhưng không tự vượt luật hoặc chính sách tổ chức.
- **Deadline thật cần thương lượng phạm vi và forecast trung thực**, không biến estimate thành lời hứa tuyệt đối.
- **Kanban nhìn thấy WIP và hàng chờ; XP tạo phản hồi kỹ thuật sớm; Scrum kiểm tra Increment và thích ứng backlog; Lean tối ưu toàn bộ thời gian tới bằng chứng**.
- **Đo hiệu quả bằng chất lượng, flow và giá trị cho người dùng**, không chỉ điểm story, số release hoặc số rủi ro đã được đóng.
- **Quản trị tốt không phải nhiều cổng duyệt**, mà là kiểm soát có lý do, bằng chứng sớm và quyết định đúng thẩm quyền tại đúng thời điểm.

Khi đứng trước một yêu cầu lớn, hãy hỏi: **“Rủi ro quan trọng nhất nếu chúng ta đang hiểu sai là gì, và phần nhỏ nhất có thể giao hoặc thử một cách an toàn để sớm có bằng chứng là phần nào?”**. Câu trả lời nối **rủi ro, giá trị, trách nhiệm và học hỏi** thành một dòng làm việc. Nhóm có thể thay đổi hướng sớm khi giả định sai, bảo vệ tiêu chuẩn cần thiết và tạo phần mềm tăng dần mà không dồn mọi bất ngờ đến cuối dự án.
