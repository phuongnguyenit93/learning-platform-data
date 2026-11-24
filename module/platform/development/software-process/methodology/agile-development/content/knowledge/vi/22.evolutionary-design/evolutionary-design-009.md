# Thiết kế tiến hóa: Lưu quyết định kiến trúc và kiểm chứng các giả định quan trọng

Một nhóm phát triển phần mềm đăng ký workshop cần giải quyết tình huống nhiều học viên đăng ký cùng lúc. Một lập trình viên đề xuất dùng hàng đợi; người khác muốn giao dịch cơ sở dữ liệu; người thứ ba nói “cứ dùng microservices để sau này dễ mở rộng”. Nhóm chọn một phương án trong cuộc họp, nhưng không lưu lý do. Ba tháng sau, một thành viên mới nhìn thấy cấu trúc hiện tại mà không biết nó giải quyết rủi ro nào. Khi tải tăng, nhóm vừa phải đoán lại giả định cũ, vừa sợ thay đổi vì không biết điều gì sẽ bị phá vỡ.

**Thiết kế tiến hóa (evolutionary design)** không coi kiến trúc là bản vẽ hoàn chỉnh phải được dự đoán đúng từ đầu. Thiết kế được điều chỉnh khi nhóm hiểu rõ hơn về sản phẩm, chất lượng, ràng buộc và công nghệ. Tuy nhiên, **tiến hóa có kiểm soát không có nghĩa quyết định tùy hứng hoặc thiếu hồ sơ**. Nhóm cần biết đã chọn gì, vì sao chọn, đang giả định điều gì, có bằng chứng nào, và sự kiện nào khiến phải xem lại.

Hai thực hành hỗ trợ nhau:

1. **Lưu quyết định kiến trúc** bằng một bản ghi ngắn, có ngữ cảnh và hệ quả, thường gọi là **Architecture Decision Record (ADR)**.
2. **Kiểm chứng các giả định quan trọng** bằng thử nghiệm có mục đích, quan sát trong hệ thống thật hoặc gần thật, các kiểm tra kiến trúc tự động và phản hồi của người dùng.

Bài học thuộc mô-đun **AGILE_DEVELOPMENT**: phát triển thích ứng qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; kết hợp user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc. Trọng tâm ở đây là **làm thế nào để quyết định kiến trúc có thể truy vết, kiểm tra và thay đổi khi học thêm**, thay vì biến ADR thành thủ tục phê duyệt hoặc xem mọi giả định chưa kiểm chứng là sự thật.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích thiết kế tiến hóa và sự khác biệt với **thiết kế tùy hứng** hoặc **khóa cứng toàn bộ kiến trúc từ đầu**.
2. Phân biệt **vấn đề, ràng buộc, giả định, giả thuyết, quyết định, bằng chứng và hệ quả**.
3. Viết một **ADR** ngắn nhưng đủ bối cảnh: trạng thái, phương án, lập luận, đánh đổi và điều kiện xem lại.
4. Quản lý vòng đời quyết định: **đề xuất – chấp nhận – áp dụng – kiểm chứng – thay thế** mà vẫn giữ lịch sử.
5. Xác định và ưu tiên **giả định có rủi ro lớn**, đặc biệt các giả định về dữ liệu, bảo mật, hiệu năng, tính sẵn sàng và khả năng thay đổi.
6. Thiết kế **spike, prototype, integration test, performance test và architectural fitness function** để tìm bằng chứng phù hợp.
7. Phân biệt thử nghiệm chứng minh điều gì, điều gì **chưa thể kết luận**, và khi nào dữ liệu cần được xem lại.
8. Kết nối ADR với code, test, CI, Product Backlog, Sprint Review/Retrospective, dòng công việc Kanban và thực hành XP.
9. Lập kế hoạch thay thế một quyết định cũ bằng thay đổi tăng dần, an toàn dữ liệu và có phương án quay lui.
10. Thực hành một trường hợp kiến trúc ứng dụng đăng ký workshop từ quyết định ban đầu đến kiểm chứng và thay đổi.

## 2. Thiết kế tiến hóa là gì?

### 2.1. Thiết kế là chuỗi quyết định có thể thích ứng

Trong thiết kế tiến hóa, nhóm chủ động xây **cấu trúc đơn giản đáp ứng nhu cầu hiện tại**, bảo vệ những thuộc tính quan trọng và tiếp tục điều chỉnh khi có bằng chứng mới. Thiết kế không ngừng lại sau một buổi vẽ sơ đồ.

Một vòng thường gặp:

~~~mermaid
flowchart TD
    A[Hiểu mục tiêu sản phẩm và ràng buộc] --> B[Nhận diện quyết định kiến trúc]
    B --> C[Ghi phương án, giả định, rủi ro vào ADR]
    C --> D[Thử nghiệm hoặc triển khai lát cắt nhỏ]
    D --> E[Kiểm chứng bằng test, vận hành, phản hồi]
    E --> F{Giả định còn đứng vững?}
    F -->|Có| G[Tiếp tục và theo dõi điều kiện thay đổi]
    F -->|Không| H[Đề xuất thay thế, ghi ADR mới, di chuyển an toàn]
    G --> A
    H --> A
~~~

Đây là **chu trình học hỏi minh họa**, không phải quy trình bắt buộc của một framework kiến trúc. Một quyết định nhỏ có thể được chốt và kiểm tra rất nhanh; quyết định liên quan đến dữ liệu nhạy cảm hoặc đổi nền tảng có thể cần nhiều bước đánh giá hơn.

### 2.2. Hai cực đoan cần tránh

| Cực đoan | Biểu hiện | Hậu quả |
| --- | --- | --- |
| **Thiết kế toàn bộ trước khi học** | Chọn sẵn hàng chục dịch vụ, database, queue, nền tảng mở rộng dù chưa có số liệu | Chi phí xây và bảo trì cao, khó bỏ lựa chọn sai |
| **Không thiết kế, chỉ sửa cho chạy** | Mỗi story thêm điều kiện ở bất kỳ đâu; không có ranh giới phụ thuộc và bất biến | Nợ kỹ thuật, lỗi hồi quy, dữ liệu khó khôi phục, phụ thuộc cá nhân |
| **Thiết kế tiến hóa có kiểm soát** | Chốt điều cần chốt, ghi quyết định có ảnh hưởng, kiểm tra rủi ro, thay đổi qua lát cắt nhỏ | Có thể duy trì chất lượng và khả năng học khi bối cảnh đổi |

**Đơn giản** không đồng nghĩa **thiếu tính đúng đắn**. Sản phẩm còn nhỏ vẫn cần bảo vệ quyền dữ liệu, giao dịch và các bất biến quan trọng; không cần sớm xây một nền tảng phân tán chỉ vì có thể tăng trưởng sau này.

### 2.3. Kiến trúc cũng tạo ra các lựa chọn và giới hạn

Một quyết định kiến trúc có thể làm thay đổi:
- Khả năng kiểm thử và tích hợp.
- Cách dữ liệu được lưu, đồng bộ, khôi phục.
- Độ tin cậy và giới hạn tải.
- Chi phí đưa một tính năng mới vào sản phẩm.
- Cách một nhóm triển khai, quan sát và xử lý sự cố.
- Mức độ phụ thuộc vào một nhà cung cấp hoặc một chuyên gia.
- Khả năng thay thế thành phần với chi phí chấp nhận được.

Vì vậy ADR không chỉ dành cho “chọn ngôn ngữ lập trình”; các quyết định về **ranh giới module, sở hữu dữ liệu, giao dịch, event, kết nối bên thứ ba, yêu cầu an toàn** cũng có thể đáng ghi.

## 3. Phân biệt vấn đề, giả định, quyết định và bằng chứng

Một phần lớn tranh cãi kiến trúc đến từ việc các khái niệm này bị trộn lẫn.

| Thành phần | Câu hỏi | Ví dụ ứng dụng workshop |
| --- | --- | --- |
| **Vấn đề** | Người dùng hoặc hệ thống đang gặp khó khăn gì? | Hai học viên có thể cùng được xác nhận suất cuối |
| **Mục tiêu** | Kết quả và thuộc tính cần bảo đảm là gì? | Không vượt sức chứa, trả trạng thái nhất quán |
| **Ràng buộc** | Điều gì bắt buộc phải tuân thủ? | Bảo vệ dữ liệu cá nhân; không ghi xác nhận sai |
| **Giả định (assumption)** | Chúng ta đang tin điều gì nhưng chưa đủ bằng chứng? | Một database quan hệ và giao dịch hiện có sẽ đủ đáp ứng tải ban đầu |
| **Giả thuyết kiểm chứng** | Có thể dự đoán quan sát nào nếu giả định đúng? | Với số yêu cầu đồng thời xác định, tổng xác nhận không vượt sức chứa |
| **Phương án** | Có những lựa chọn nào? | Cập nhật có điều kiện trong transaction; lock; queue |
| **Quyết định** | Chọn phương án nào trong bối cảnh hiện tại? | Dùng cập nhật nguyên tử ở database hiện có |
| **Bằng chứng** | Test, đo đạc, nghiên cứu hay dữ liệu nào hỗ trợ hoặc bác bỏ? | Integration test với giao dịch đồng thời và dữ liệu cuối cùng |
| **Hệ quả** | Chọn phương án mang lại lợi ích và chi phí gì? | Đơn giản hơn queue riêng nhưng phụ thuộc năng lực DB và cơ chế retry |

Một **giả định** không trở thành **sự thật** chỉ vì đã được ghi trong ADR. Một **quyết định** cũng không trở nên tối ưu cho mọi tương lai chỉ vì được chấp nhận ngày hôm nay.

### 3.1. Sự kiện, giả định, suy luận và cam kết

Ví dụ:

- **Sự kiện quan sát:** trong đợt thử, 18/20 yêu cầu nhận trạng thái đúng theo kiểm tra đã thực hiện.
- **Giả định:** phương án hiện tại sẽ xử lý an toàn khi 100 yêu cầu tranh suất cuối.
- **Suy luận:** cần test đồng thời và theo dõi việc retry trước khi mở rộng dùng thật.
- **Quyết định:** chọn phương án A cho bản đầu, kèm điều kiện kiểm chứng bắt buộc.

Nếu không phân biệt, nhóm có thể ghi “database chắc chắn đủ 100 yêu cầu/giây” mà chưa hề đo trong môi trường phù hợp.

### 3.2. Giả định quan trọng thường ẩn trong lời nói

Những câu sau đều chứa giả định:
- “Lúc phát hành chắc chỉ có vài người dùng đồng thời.”
- “Nhà cung cấp sẽ gửi sự kiện đúng một lần.”
- “Không ai sửa trạng thái đăng ký trực tiếp trong database.”
- “Chúng ta luôn rollback được schema.”
- “Service B sẽ phản hồi trong 100 ms.”
- “Cứ thêm cache là hiệu năng ổn.”
- “Nhóm vận hành sẽ tự theo dõi lỗi gửi thông báo.”

Một buổi phân tích ngắn có thể hỏi: **“Nếu câu nói này sai thì điều gì hỏng, ai chịu ảnh hưởng, và có cách thử trước khi cam kết lớn không?”**

## 4. Architecture Decision Record (ADR): lưu điều gì và để làm gì?

### 4.1. ADR là hồ sơ lý do ra quyết định

**ADR** là một bản ghi ngắn mô tả **quyết định kiến trúc có ý nghĩa trong bối cảnh cụ thể**, các lựa chọn và hệ quả. Nó trả lời cho người đến sau:

1. Vấn đề nào buộc phải quyết?
2. Khi đó nhóm biết gì và chưa biết gì?
3. Những phương án nào đã được cân nhắc?
4. Đã chọn gì, vì sao?
5. Đã chấp nhận những đánh đổi nào?
6. Điều gì phải kiểm chứng và điều gì có thể khiến cần xem lại?
7. Quyết định hiện còn áp dụng hay đã được thay thế?

Đừng hiểu ADR là bản thiết kế hệ thống dài hàng chục trang. Nó cũng **không tự thay thế code, test, sơ đồ, chính sách vận hành hoặc tài liệu hợp đồng**.

### 4.2. Quyết định nào đáng ghi ADR?

Nên cân nhắc ADR khi quyết định có một hoặc nhiều đặc điểm:
- Khó đảo ngược, chi phí di chuyển lớn.
- Ảnh hưởng tính đúng, bảo mật, quyền dữ liệu hoặc tuân thủ.
- Thiết lập ranh giới module/ownership hay mô hình giao tiếp giữa thành phần.
- Chọn cách quản lý transaction, tính nhất quán, retry hoặc event.
- Đặt một ràng buộc cần nhiều nhóm tuân thủ.
- Đổi nền tảng, công nghệ hoặc nhà cung cấp gây phụ thuộc đáng kể.
- Có **nhiều phương án hợp lý và đánh đổi khó nhớ**.
- Có khả năng xuất hiện câu hỏi “tại sao chúng ta làm như vậy?” sau vài tháng.

Không cần ADR cho **mọi đổi tên biến, tối ưu CSS, thêm unit test hoặc refactoring nhỏ** không làm thay đổi kiến trúc. Những việc này có thể được giải thích bằng code review và test phù hợp.

### 4.3. Các phần chính của ADR

| Trường | Nội dung mong đợi | Sai lầm cần tránh |
| --- | --- | --- |
| **ID và tiêu đề** | Tên duy nhất, nói rõ quyết định | “Thiết kế mới” không có ý nghĩa |
| **Trạng thái (status)** | Proposed, Accepted, Superseded… theo quy ước | Không biết quyết định đã áp dụng chưa |
| **Bối cảnh (context)** | Vấn đề, Product Goal, ràng buộc và tình trạng hiện tại | Chỉ chép tên công nghệ |
| **Decision drivers** | Tiêu chí và ưu tiên lựa chọn | Đưa tiêu chí sau khi đã chọn để hợp thức hóa |
| **Các phương án** | Ít nhất phương án thật sự đã cân nhắc, gồm chưa làm khi phù hợp | Lập danh sách giả chỉ có một phương án |
| **Quyết định** | Chọn gì, phạm vi nào và từ khi nào | Dùng câu mơ hồ như “sử dụng kiến trúc hiện đại” |
| **Lý do và đánh đổi** | Lợi ích, chi phí, rủi ro, điều hy sinh | Chỉ liệt kê ưu điểm |
| **Giả định** | Những điều chưa chứng minh mà lựa chọn dựa vào | Biến niềm tin thành dữ kiện |
| **Kiểm chứng** | Phép thử, fitness function, nguồn kết quả, điều kiện đạt | “Sẽ test sau” không có người và thời điểm |
| **Điều kiện xem lại** | Mốc thời gian hoặc dữ liệu kích hoạt | Coi quyết định là bất biến mãi mãi |
| **Liên kết** | User story, spike, issue, test, ADR thay thế | Hồ sơ tách khỏi mã và công việc |

Không có **một mẫu ADR bắt buộc cho mọi tổ chức**. Mẫu tốt nhất là mẫu đội có thể viết, đọc và duy trì đủ thường xuyên.

### 4.4. Ví dụ ADR hoàn chỉnh ở mức thực hành

Dưới đây là tài liệu **minh họa cho một sản phẩm giả định**, không phải kết quả triển khai thật:

~~~markdown
# ADR-007: Dùng cập nhật có điều kiện trong DB để giữ sức chứa workshop

Status: Accepted (có điều kiện kiểm chứng)
Date: 2026-11-23
Decision owner: Nhóm kỹ thuật cùng Product Owner xác nhận rủi ro nghiệp vụ

## Context
Một workshop có số chỗ giới hạn. Hai yêu cầu hợp lệ có thể đến gần
đồng thời; không được tạo hai xác nhận cho một suất cuối.
Bản đầu dùng cơ sở dữ liệu quan hệ hiện có.

## Decision drivers
- Không vượt sức chứa trong mọi thao tác xác nhận được hỗ trợ.
- Xử lý retry cùng định danh yêu cầu mà không tạo bản ghi trùng.
- Đủ đơn giản để vận hành và kiểm tra trong giai đoạn đầu.
- Có thể đo và tăng khả năng xử lý khi nhu cầu thực tăng.

## Options
A. UPDATE có điều kiện trong transaction + unique request key.
B. Dùng hàng đợi và một worker tuần tự hóa toàn bộ xác nhận.
C. Khóa logic chỉ trong bộ nhớ của từng instance.

## Decision
Chọn A cho bản đầu. Kết quả cập nhật và tạo bản ghi xác nhận
phải ở cùng giao dịch. Request key phải duy nhất theo chính sách.
Không dựa vào khóa trong bộ nhớ khi chạy nhiều instance.

## Consequences
+ Không cần vận hành queue riêng ngay.
+ Bất biến sức chứa được kiểm tra tại ranh giới dữ liệu.
- Có thể tạo tranh chấp trên row khi lượng request cao.
- Cần thiết kế retry, timeout, idempotency và quan sát lỗi.

## Assumptions to validate
H1: Một suất còn lại, 100 request khác nhau cùng tranh suất
    chỉ có tối đa một xác nhận mới hợp lệ trong dữ liệu cuối.
H2: Retry cùng request key không làm tăng số xác nhận.
H3: Độ trễ dưới tải thử phù hợp mục tiêu đã thống nhất.

## Evidence and checks
- Integration test với DB loại/cấu hình gần môi trường thật.
- Concurrency test lặp nhiều lượt, kiểm dữ liệu cuối.
- Load test ghi latency p95, lỗi, số transaction retry.
- Guardrail: không phát hành nếu phát hiện vượt sức chứa.

## Review triggers
Bằng chứng sai H1/H2; tải và độ trễ vượt ngưỡng đã thống nhất;
thay đổi ranh giới dữ liệu hay yêu cầu mở rộng dịch vụ.

## Links
Story WS-13; test integration WS-13-IT;
experiment EXP-04; ADR mới nếu thay đổi lựa chọn.
~~~

Một số tổ chức viết ADR dưới dạng Markdown nằm cạnh code và dùng pull request để thảo luận; nơi khác dùng wiki có lịch sử sửa đổi. **Quan trọng là bản ghi có thể tìm, có liên kết với thay đổi và còn truy vết khi người quyết định ban đầu không có mặt.**

### 4.5. ADR không chứng minh giải pháp đã đúng

Status **Accepted** nghĩa là phương án đã được **chấp nhận trong bối cảnh đã nêu**, không có nghĩa các giả định H1–H3 đã qua kiểm chứng. Bằng chứng có thể đến sau bước quyết định. Nếu một kiểm tra bắt buộc thất bại, nhóm cần ngăn phát hành phần rủi ro, xem lại quyết định hoặc sửa triển khai; không chỉ sửa chữ “passed” trong ADR.

## 5. Vòng đời ADR và quản lý quyết định bị thay thế

### 5.1. Một mô hình trạng thái minh họa

~~~mermaid
flowchart LR
    A[Proposed: đang thảo luận] --> B[Accepted: đã chọn]
    A --> R[Rejected: không chọn]
    B --> C[Implemented: đã áp dụng]
    B --> D[Superseded: quyết định mới thay thế]
    C --> D
    C --> E[Retired: không còn áp dụng]
~~~

Đây là một **quy ước nhóm có thể chọn**. Nhiều nhóm chỉ dùng **Proposed – Accepted – Superseded** và quản lý trạng thái triển khai trong issue riêng. Không cần sinh nhiều trạng thái nếu chúng không tạo giá trị.

### 5.2. Phân biệt Accepted và Implemented

Một ADR được chấp nhận hôm nay nhưng code chưa triển khai là **quyết định dự kiến**. Nếu báo “hệ thống đang dùng transaction mới” khi chưa có migration, team có thể đánh giá sai rủi ro.

Có thể lưu:
- **Decision status:** Accepted.
- **Implementation status:** chưa bắt đầu / đang làm / đã xác minh.
- **Evidence status:** thử nghiệm chưa chạy / đạt trong phạm vi X / cần xem lại.
- **Next review:** khi tải vượt mức hoặc khi thay đổi cách ghi dữ liệu.

Không cần thêm bốn field vào mọi ADR nếu một bảng liên kết issue/test đã giải quyết đủ. Điều quan trọng là **không đồng nhất quyết định giấy tờ với phần mềm đã hoạt động**.

### 5.3. Không xóa lịch sử khi quyết định đổi

Giả sử từ một database đơn, nhóm chuyển sang kiến trúc có hàng đợi vì nhu cầu giao xử lý nền tăng. Cách lưu hợp lý:

1. Viết **ADR mới** nêu bối cảnh mới và bằng chứng thay đổi.
2. Liên kết ADR mới **supersedes** ADR cũ.
3. Cập nhật ADR cũ thành **Superseded** và chỉ rõ ADR thay thế.
4. Giữ lại **lý do và giả định trước đây** để người khác hiểu tiến trình.
5. Liên kết kế hoạch migration, test và thời điểm thực sự chuyển đổi.

Không nên âm thầm sửa ADR cũ để nó trông như nhóm **đã dự đoán đúng từ đầu**. Lịch sử quyết định là nguồn học quan trọng; nếu viết đè lập luận cũ, đội không còn thấy giả định nào đã thay đổi.

### 5.4. ADR nên lưu cùng code hay công cụ riêng?

| Lựa chọn | Ưu điểm | Giới hạn |
| --- | --- | --- |
| **Markdown versioned cùng repository** | Review cùng code, xem diff, truy vết theo commit | Cần quy tắc đặt tên, liên kết và tìm kiếm |
| **Wiki/tài liệu sản phẩm** | Dễ tiếp cận với bên ngoài kỹ thuật | Có thể rời khỏi thay đổi code; cần lịch sử và trách nhiệm cập nhật |
| **Decision log trên hệ thống công việc** | Liên kết ưu tiên, issue và thử nghiệm | Có thể mất ngữ cảnh khi ticket đóng hoặc đổi công cụ |
| **Kết hợp** | ADR chính ở một nơi, liên kết từ backlog, code và wiki | Cần tránh nhiều bản sao mâu thuẫn |

Nên chọn **một nguồn có thẩm quyền cho mỗi quyết định**, còn nơi khác chỉ liên kết hoặc tóm tắt. Không tạo ba bản ADR độc lập rồi để chúng lệch trạng thái.

## 6. Sổ giả định: ghi điều chưa biết để không khóa thiết kế bởi niềm tin

**Assumption register** là một danh sách có chủ đích về những giả định ảnh hưởng quyết định quan trọng. Nó có thể ở bảng ngắn, issue tracker hoặc trong/đi kèm ADR.

### 6.1. Những trường tối thiểu hữu ích

| Trường | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **ID** | Định danh liên kết được | ASM-04 |
| **Phát biểu giả định** | Một câu có khả năng đúng/sai trong phạm vi rõ | Cập nhật có điều kiện không xác nhận vượt sức chứa |
| **Nếu sai thì sao?** | Tác động đến người dùng, dữ liệu, vận hành | Có thể bán/giữ chỗ vượt giới hạn |
| **Mức bất định** | Bằng chứng hiện tại tin cậy đến đâu | Chưa test đồng thời thật |
| **Cách kiểm chứng** | Test, spike, đo đạc hay nghiên cứu | Integration/concurrency test |
| **Owner** | Ai theo dõi để có kết quả | Developers phụ trách transaction |
| **Hạn kiểm chứng** | Trước sự kiện nào phải biết | Trước khi mở dùng thật |
| **Trạng thái** | Chưa kiểm tra, có bằng chứng hỗ trợ, bị bác bỏ… | In validation |
| **Nguồn kết quả** | Link test/report, ngày và phạm vi | EXP-04, cấu hình DB X |

Đừng ghi “DB luôn đủ nhanh” như một phát biểu có thể kiểm chứng. Cần xác định **đủ nhanh cho thao tác gì, tải nào, môi trường nào và ngưỡng nào**.

### 6.2. Ví dụ sổ giả định của ứng dụng workshop

| ID | Giả định cần xem xét | Nếu sai | Mức ưu tiên xác minh | Cách học |
| --- | --- | --- | --- | --- |
| **A-01** | Cập nhật đồng thời không thể xác nhận quá sức chứa | Sai dữ liệu và mất niềm tin nghiêm trọng | **Rất cao** | Test cạnh tranh trên kho dữ liệu thật |
| **A-02** | Retry cùng request key không tạo xác nhận trùng | Dữ liệu trùng, gây hỗ trợ thủ công | **Rất cao** | Test idempotency và lỗi mạng |
| **A-03** | Bản đầu có thể dùng database hiện tại với tải dự kiến | Độ trễ, timeout hoặc nghẽn | Cao khi gần phát hành | Đo tải thực tế với kịch bản đại diện |
| **A-04** | Người dùng hiểu đúng trạng thái chờ/xác nhận | Hỏi lại hoặc hiểu sai đã có chỗ | Cao đối với Product Goal | Quan sát thử nghiệm người dùng |
| **A-05** | Có thể đổi nhà cung cấp gửi email với chi phí nhỏ | Khóa nhà cung cấp | Trung bình, tùy hợp đồng | Spike đổi adapter/contract |
| **A-06** | Giao diện trang chủ cần hoạt ảnh phức tạp | Có thể xây thứ ít giá trị | Thường thấp hơn rủi ro dữ liệu | Thử nhanh với người dùng, theo ưu tiên |

Các mức ưu tiên là **đề xuất trong tình huống giả định**. Nếu có yêu cầu pháp lý mới, loại sản phẩm khác hoặc thời hạn dịch vụ, thứ tự có thể thay đổi.

### 6.3. Độ tin cậy bằng chứng không chỉ có hai trạng thái

Có thể dùng ngôn ngữ:
- **Unknown:** chưa có dữ liệu đủ liên quan.
- **Evidence supporting:** có bằng chứng trong phạm vi đã kiểm tra.
- **Evidence contradicting:** có quan sát bác bỏ giả định.
- **Not currently relevant:** bối cảnh khiến giả định không còn là điều cần quyết.
- **Needs revalidation:** điều kiện đã thay đổi nên cần kiểm tra lại.

**“Có bằng chứng hỗ trợ” không phải “chứng minh đúng mãi mãi”.** Một load test đạt trong môi trường nhỏ không tự chứng minh production sẽ đạt khi lượng người dùng tăng mười lần.

### 6.4. Giả định cần có thời hạn sử dụng

Một số giả định về logic nghiệp vụ được bảo vệ lâu dài bằng test và bất biến dữ liệu. Những giả định khác như tải, giá hạ tầng, hành vi người dùng và khả năng nhà cung cấp **thay đổi theo thời gian**.

Ghi lại **ngày, phạm vi và dấu hiệu cần đo lại**. Không nên dùng kết quả thử tải của một cấu hình cũ làm bằng chứng duy nhất cho kiến trúc hiện tại.

## 7. Ưu tiên giả định theo rủi ro, không theo thứ tự xuất hiện

Nhóm hiếm khi có năng lực kiểm tra mọi giả định. Cần chọn những điều **có thể làm quyết định sai gây thiệt hại lớn**, đặc biệt nếu có phép thử chi phí hợp lý trước khi cam kết.

### 7.1. Ba câu hỏi sàng lọc

1. **Hậu quả nếu giả định sai lớn đến đâu?** Mất dữ liệu, lộ thông tin, ngừng dịch vụ, chi phí di chuyển hay giảm giá trị?
2. **Bằng chứng hiện tại yếu đến mức nào?** Chỉ có ý kiến, demo một lần hay test thực tế đại diện?
3. **Khi nào phải biết?** Nếu chờ đến sau phát hành, hậu quả có còn chấp nhận được không?

Có thể bổ sung **chi phí kiểm chứng** và **khả năng thay đổi quyết định**, nhưng không nên dùng một bảng điểm tự tạo để bỏ qua ràng buộc an toàn nghiêm trọng.

### 7.2. Ma trận rủi ro minh họa

| Hậu quả nếu sai | Bằng chứng tương đối mạnh | Bằng chứng yếu hoặc chưa có |
| --- | --- | --- |
| **Rất lớn** | Giữ kiểm tra tự động, theo dõi thay đổi, xác minh khi ranh giới đổi | Ưu tiên kiểm chứng và/hoặc biện pháp bảo vệ ngay |
| **Trung bình** | Theo dõi tín hiệu, kiểm tra ở mốc phù hợp | Thử nghiệm nhỏ trước cam kết |
| **Thấp, dễ đảo ngược** | Không cần tăng thủ tục nếu đã đủ rõ | Có thể quyết nhỏ, quan sát sau, tránh phân tích quá mức |

Ma trận là **khung phân loại thực hành**, không phải mô hình xác suất được hiệu chuẩn. Không thể kết luận “rủi ro chỉ bằng 2” nếu chưa có dữ liệu tin cậy.

### 7.3. Ưu tiên theo thời điểm quyết định

Giả định A-01 về xác nhận trùng phải được kiểm tra **trước khi hệ thống nhận xác nhận thực**, vì hậu quả có thể khó đảo ngược. Giả định A-05 về thay nhà cung cấp email có thể chờ trong một giai đoạn nếu chi phí đổi thấp và hợp đồng không khóa dài hạn.

**Lean và thiết kế tiến hóa gặp nhau ở đây:** chủ động học sớm những điều nguy hiểm, nhưng chưa cam kết giải pháp phức tạp cho tương lai chưa có bằng chứng.

## 8. Biến giả định thành giả thuyết kiểm chứng

### 8.1. Giả định mơ hồ khiến thử nghiệm vô nghĩa

Những phát biểu yếu:
- “Hệ thống sẽ nhanh.”
- “Queue sẽ an toàn.”
- “Microservices dễ mở rộng.”
- “Người dùng thích nhận email.”
- “Cơ sở dữ liệu sẽ chịu được tải lớn.”

Chúng thiếu **tác vụ, điều kiện, ngưỡng, phương pháp đo và phạm vi**.

### 8.2. Mẫu giả thuyết hữu ích

Một mẫu có thể là:

> **Trong điều kiện** [bối cảnh và tải], **nếu dùng** [phương án], **chúng ta kỳ vọng** [hành vi đo được] **trong giới hạn** [ngưỡng và guardrail]. **Chúng ta sẽ kiểm chứng bằng** [phương pháp, dữ liệu, môi trường], **trước** [mốc quyết định].

Ví dụ:

> Với workshop còn một suất, khi **100 request khác nhau** cố xác nhận gần đồng thời qua hai instance ứng dụng và cùng database, số xác nhận mới thành công **không vượt một**, dữ liệu cuối cùng không vượt sức chứa và retry cùng request key không tạo bản ghi trùng. Nhóm kiểm tra qua integration test có thực hiện giao dịch và kiểm chứng trạng thái lưu trữ sau khi tất cả request kết thúc.

Đây là **giả thuyết kiểm tra tính đúng**, không phải thước đo đủ cho hiệu năng hay khả năng phục hồi toàn hệ thống.

### 8.3. Phải tách tiêu chí đúng nghiệp vụ và tiêu chí hiệu năng

| Khía cạnh | Giả thuyết ví dụ | Cách kiểm |
| --- | --- | --- |
| **Tính đúng** | Không xác nhận vượt số chỗ | Kiểm dữ liệu cuối dưới cạnh tranh |
| **Idempotency** | Retry với cùng key không tạo tác dụng phụ gấp đôi | Test retry, timeout, gửi lặp |
| **Hiệu năng** | p95 độ trễ dưới ngưỡng giả định khi tải cụ thể | Load test có cấu hình và số liệu |
| **Độ tin cậy** | Khi gateway email lỗi, xác nhận đã lưu không biến mất | Kiểm fault injection/contract |
| **Quyền truy cập** | Người dùng không xem được đăng ký không thuộc quyền | Security/authorization tests |
| **Giá trị người dùng** | Phần lớn người dùng thử hiểu rõ “đang chờ” | Quan sát hành vi trong dùng thử |

Một phép thử đạt ở một hàng **không tự chứng minh** các hàng còn lại.

### 8.4. Giới hạn bằng chứng phải được ghi lại

Nếu test chạy trên một database trong bộ nhớ, không được nói đã chứng minh hành vi locking của PostgreSQL hoặc một hệ quản trị khác. Nếu test tải chạy từ một laptop, phải ghi rõ máy, mạng, dữ liệu và số request. Nếu khảo sát chỉ gồm đồng nghiệp nội bộ, không suy rộng như mẫu đại diện toàn bộ học viên.

**Bằng chứng tốt không chỉ là số “PASS”; nó còn nói rõ cái gì đã được kiểm và trong điều kiện nào.**

## 9. Các phương pháp kiểm chứng giả định kiến trúc

### 9.1. Chọn phép thử khớp loại câu hỏi

| Phương pháp | Trả lời tốt câu hỏi nào? | Hạn chế |
| --- | --- | --- |
| **Spike kỹ thuật có timebox** | Công nghệ có làm được tác vụ mới, khó hiểu không? | Code khám phá thường chưa đủ chất lượng production |
| **Prototype / proof of concept** | Phương án có khả thi về kỹ thuật hoặc trải nghiệm không? | Demo chạy một lần không chứng minh vận hành ổn |
| **Unit tests / TDD** | Quy tắc nhỏ có đúng và dễ thay đổi không? | Không xác minh giao dịch, network hoặc tải thật |
| **Integration/contract tests** | Các thành phần và ranh giới có hành xử đúng hợp đồng? | Phụ thuộc mức độ sát môi trường thật |
| **Concurrency/fault tests** | Dữ liệu và hệ thống còn đúng khi có tranh chấp/lỗi? | Không thể bao phủ toàn bộ lịch xen kẽ và mọi loại lỗi |
| **Load/performance tests** | Độ trễ, throughput, tài nguyên ở tải xác định ra sao? | Kết quả phụ thuộc cấu hình, dữ liệu và điều kiện thử |
| **Security review / kiểm tra quyền** | Điều kiện truy cập và rủi ro thông tin có được bảo vệ? | Cần chuyên môn và đánh giá theo bề mặt tấn công thực |
| **Migration rehearsal** | Dữ liệu cũ có chuyển đổi/rollback hoặc phục hồi được? | Cần dữ liệu đại diện, môi trường an toàn |
| **Canary / triển khai tăng dần** | Thay đổi vận hành ra sao với phạm vi nhỏ? | Cần quan sát, cách cô lập và phương án quay lui |
| **Quan sát người dùng** | Giải pháp có giải quyết vấn đề người dùng? | Khác với chứng minh tính đúng ở tầng dữ liệu |
| **Architectural fitness function** | Đặc tính kiến trúc có còn đáp ứng tiêu chí đã chọn? | Chỉ kiểm điều được đặc tả và đo phù hợp |

### 9.2. Spike phải có câu hỏi và điều kiện dừng

Một spike không phải giấy phép “nghiên cứu tới khi thích thì thôi”. Ví dụ:

~~~text
Spike: Kiểm tra cơ chế cập nhật có điều kiện của DB

Câu hỏi:
Một request xác nhận workshop có thể bảo vệ sức chứa
bằng cập nhật nguyên tử trên database hiện tại không?

Phạm vi:
Một bảng workshop tối giản, một giao dịch xác nhận,
nhiều request đồng thời từ hai instance thử nghiệm.

Timebox:
Hai ngày làm việc (ví dụ minh họa).

Dữ liệu cần:
Số xác nhận thành công, dữ liệu cuối, retry, deadlock,
thời gian phản hồi và lỗi.

Tiêu chí dừng:
Có bằng chứng về tính đúng và giới hạn đã thử;
hoặc biết rõ rủi ro nào chưa thể kiểm chứng trong timebox.

Đầu ra:
Mã thử nghiệm, cách tái lập, kết quả, hạn chế,
đề xuất tiếp tục hoặc đổi phương án.
~~~

Nếu spike không cho câu trả lời đủ tin cậy, kết quả vẫn hữu ích: **ghi rõ chưa biết gì, hậu quả và mốc cần quyết**. Không biến một prototype đang chạy thành code production mặc nhiên.

### 9.3. Đặt guardrail trước khi thử

Đặc biệt với dữ liệu và an toàn:
- Không thử tải phá hoại trực tiếp trên production nếu không có quy trình và phạm vi an toàn thích hợp.
- Dùng dữ liệu giả hoặc dữ liệu được xử lý quyền riêng tư.
- Thiết lập giới hạn tài nguyên, quyền truy cập và cách dừng.
- Xác định điều kiện thất bại nghiêm trọng buộc dừng phát hành.
- Có người chịu trách nhiệm đánh giá kết quả.

Một bài test **không được phép gây rủi ro thật chỉ để thu bằng chứng nhanh**.

## 10. Ví dụ kỹ thuật: kiểm chứng giả định không xác nhận vượt sức chứa

### 10.1. Phân biệt quy tắc tính toán và bảo vệ dữ liệu

Một hàm thuần có thể trả lời:

~~~java
public boolean canConfirm(int confirmed, int capacity) {
    return confirmed >= 0
        && capacity >= 0
        && confirmed < capacity;
}
~~~

Nó có thể đúng khi dùng với dữ liệu đầu vào nhất quán, nhưng **không ngăn hai request cùng đọc confirmed = 9 ở một workshop sức chứa 10, rồi đều cập nhật**.

Bất biến “không xác nhận vượt sức chứa” phải được bảo vệ tại **ranh giới cập nhật dữ liệu** và phải kiểm chứng qua cơ chế thực sự được sử dụng.

### 10.2. Một ý tưởng cập nhật nguyên tử

Với **PostgreSQL** (cú pháp và hành vi cụ thể phụ thuộc hệ quản trị và thiết lập transaction), có thể nghiên cứu hướng tiếp cận cập nhật có điều kiện:

~~~sql
-- Minh họa ý tưởng cập nhật điều kiện, không phải
-- toàn bộ transaction xử lý registration production.
UPDATE workshop
SET confirmed_count = confirmed_count + 1
WHERE id = :workshop_id
  AND confirmed_count < capacity
RETURNING confirmed_count;
~~~

Nếu không còn chỗ, thao tác cập nhật không trả hàng nào. Khi nhiều giao dịch cùng sửa một hàng, database quản lý locking và đánh giá điều kiện theo cơ chế phù hợp; nhưng **cần test với isolation level, cấu hình, dữ liệu và luồng triển khai thực tế**.

Để một yêu cầu đăng ký được xử lý đúng, có thể còn cần:
- Ghi nhận registration trong **cùng transaction** với việc tăng số chỗ.
- Một **request key duy nhất** theo quy tắc idempotency.
- Quy tắc khi retry do timeout hoặc client gửi lại.
- Bảo đảm transaction rollback nếu bước ghi liên quan thất bại.
- Chính sách phân biệt đã tiếp nhận, đang chờ, đã xác nhận và bị từ chối.
- Không gửi thông báo xác nhận thành công trước khi kết quả giao dịch được xác định tin cậy.

Đoạn SQL trên **không phải công thức production đầy đủ**. Nếu nhóm triển khai chỉ một UPDATE mà không có giao dịch ghi registration và idempotency phù hợp, hệ thống vẫn có thể gặp lỗi dữ liệu hoặc phát thông báo sai.

### 10.3. Kế hoạch integration test quan trọng

~~~text
Experiment EXP-04: Xác nhận suất cuối dưới cạnh tranh

Setup:
- Workshop capacity = 10, confirmed_count = 9.
- 100 request khác nhau cùng cố xác nhận.
- Chạy qua hai instance nếu production dùng nhiều instance.
- Database và isolation level tương ứng cấu hình cần kiểm.

Execution:
1. Khởi tạo dữ liệu sạch và request keys khác nhau.
2. Cho 100 request bắt đầu gần đồng thời, có đồng bộ thời điểm thử.
3. Đợi request kết thúc hoặc timeout và phân loại kết quả.
4. Đọc dữ liệu cuối từ database.
5. Kiểm tra số xác nhận mới, số bản ghi và trạng thái trả về.
6. Lặp lại với các lịch thực thi và tốc độ khác nhau.
7. Gửi lại một số request keys để kiểm tra idempotency.
8. Tiêm lỗi phù hợp và quan sát rollback/retry.

Assertions:
- confirmed_count không vượt capacity.
- Chỉ tối đa một xác nhận mới thành công cho suất cuối.
- Dữ liệu registration nhất quán với count theo quy tắc.
- Retry cùng key không tạo thêm xác nhận hoặc thông báo sai.
- Tất cả kết quả đều có ý nghĩa nghiệp vụ và khả năng quan sát.

Evidence:
- Phiên bản app, DB, cấu hình, số vòng, logs,
  trạng thái cuối và những trường hợp chưa được kiểm.
~~~

Nếu test đạt, nhóm có bằng chứng **trong các điều kiện đã thử**. Không thể suy ra mọi lịch xen kẽ, phân vùng mạng, thay đổi schema hoặc hạ tầng tương lai đều an toàn. Vì vậy kiểm tra hồi quy quan trọng cần được duy trì khi code và kiến trúc tiến hóa.

### 10.4. Bảo vệ kết quả khi phát thông báo bất đồng bộ

Nếu nhóm sử dụng sự kiện thông báo sau xác nhận, giả định thường gặp là **sự kiện có thể được xử lý lặp hoặc chậm**. Cần làm rõ:
- Việc gửi lặp có thể gây hậu quả gì?
- Cách xử lý idempotent tại consumer thế nào?
- Khi ghi DB thành công nhưng phát event thất bại, dữ liệu và thông báo được phục hồi ra sao?
- Có cần mô hình **transactional outbox** hay phương án nhất quán phù hợp không?
- Trạng thái nào người dùng nhìn thấy khi thông báo bị chậm?

Không nên tự tuyên bố có **exactly-once delivery end-to-end** chỉ vì đã thêm queue. Cơ chế bảo đảm thực tế cần được phát biểu cụ thể theo broker, consumer, database và tác dụng phụ bên ngoài.

## 11. Architectural fitness functions: biến chất lượng kiến trúc thành kiểm tra lặp lại

### 11.1. Fitness function là gì?

**Architectural fitness function** là một phép đánh giá khách quan hoặc đủ rõ giúp kiểm tra liệu kiến trúc có còn đáp ứng **một đặc tính quan trọng đã chọn** khi hệ thống thay đổi hay không. Nó có thể được tự động hóa hoàn toàn, một phần hoặc thực hiện định kỳ theo quy trình có tiêu chí.

Ví dụ:
- Module nghiệp vụ không phụ thuộc trực tiếp vào controller/web framework.
- Không có xác nhận vượt sức chứa trong các tình huống cạnh tranh đã định nghĩa.
- Contract giữa các service còn tương thích theo chính sách.
- Latency p95 ở một tải có ý nghĩa nằm trong ngưỡng đã xác định.
- Chuyển đổi schema chạy thử được với dữ liệu đại diện.
- Không có truy cập dữ liệu sai quyền trong kiểm thử quan trọng.
- Có thể khôi phục hoạt động sau một lớp lỗi đã xác định.

**Không có một bộ fitness functions áp dụng cho mọi hệ thống.** Nhóm chọn thuộc tính liên quan Product Goal, ràng buộc và rủi ro thực.

### 11.2. Ví dụ bộ kiểm tra liên kết với ADR

| Quyết định/giả định | Thuộc tính cần bảo vệ | Fitness function hoặc phép kiểm | Tần suất |
| --- | --- | --- | --- |
| ADR-007: xác nhận qua transaction | Tính nhất quán sức chứa | Integration test đồng thời, dữ liệu cuối không vượt capacity | Mỗi thay đổi liên quan và trước release |
| Ranh giới domain không biết HTTP | Kiến trúc module | Kiểm phụ thuộc package/module theo danh sách cấm | Trong CI |
| Gateway thông báo qua adapter | Khả năng thay provider | Contract test trên adapter và fake/real phù hợp | Khi đổi adapter |
| Kỳ vọng thời gian phản hồi | Hiệu năng ở tải đã nêu | Load test có kết quả p95 và lỗi | Trước mốc mở rộng, khi đổi hạ tầng |
| Dữ liệu đăng ký có phân quyền | Bảo vệ thông tin | Authorization tests và review quyền truy cập | Mỗi thay đổi liên quan |
| Kế hoạch schema migration | Khả năng nâng cấp an toàn | Rehearsal chuyển đổi và xác minh dữ liệu | Trước đợt migration |

Một test đỏ cần tạo hành động: xác định **đang phá cam kết kiến trúc**, test sai hay bối cảnh đã đổi. Không nên bỏ test chỉ vì nó làm pipeline khó xanh.

### 11.3. Tự động hóa kiểm tra cấu trúc

Ví dụ một **quy tắc phụ thuộc**:

~~~text
Rule ARCH-01:
Gói domain không được import các gói controller,
HTTP transport hoặc implementation của persistence.

Reason:
Quy tắc nghiệp vụ phải kiểm tra và thay đổi độc lập
với cơ chế truyền nhận và lưu trữ.

Check:
Phân tích dependency của mã nguồn trong CI.

Failure:
Build fail hoặc cảnh báo có owner và hạn sửa theo
mức nghiêm trọng đã thống nhất.
~~~

Không nên dùng cấu trúc này để tạo một kiến trúc nhiều tầng phức tạp bất kể nhu cầu. Quy tắc hữu ích khi nó bảo vệ **ranh giới đáng giá** và không gây chi phí bất hợp lý.

### 11.4. Hiệu năng phải có tiêu chí và điều kiện đo

Ví dụ một yêu cầu **giả định**:

> “Trong môi trường staging gần cấu hình vận hành và kịch bản 200 yêu cầu xác nhận mỗi phút, latency p95 của API xác nhận phải không vượt 400 ms, tỷ lệ lỗi ngoài trường hợp hết chỗ không vượt ngưỡng đã thống nhất và count không vượt capacity.”

Ngưỡng 400 ms, 200/phút chỉ để minh họa. Nếu một nhóm đo p95 từ 10 request đơn lẻ trên laptop rồi nói đã chứng minh đạt mục tiêu production, kết luận không đáng tin.

Cần ghi:
- Cấu hình máy và database, số replica.
- Kích thước dữ liệu và đặc điểm truy cập.
- Thời lượng warm-up, thời lượng thử, phân bố tải.
- Cách tính latency và phân loại lỗi.
- Tác động của caching, network, phụ thuộc.
- Số lần chạy và độ biến thiên quan sát.

### 11.5. Fitness function không thay thế suy nghĩ về giá trị

Một hệ thống có module boundaries đẹp, test xanh và latency thấp vẫn có thể cung cấp chức năng **không ai cần**. Tách:
- **Fitness về kiến trúc:** kiến trúc giữ thuộc tính quan trọng?
- **Quality of delivery:** Increment có đạt tiêu chuẩn chất lượng?
- **Product outcome:** người dùng có nhận được giá trị?

Cần đo cả ba ở mức phù hợp, không biến số lượng fitness functions thành KPI của từng Developers.

## 12. Thực nghiệm lựa chọn kiến trúc: giữ tùy chọn rồi hội tụ có bằng chứng

### 12.1. So sánh lựa chọn bằng điều kiện thực

Một nhóm cân nhắc cách gửi thông báo sau khi xác nhận đăng ký:

| Phương án | Điều có lợi | Chi phí/rủi ro | Giả định cần kiểm |
| --- | --- | --- | --- |
| **A. Gọi trực tiếp gateway trong luồng request** | Đơn giản ở bản đầu | Chậm khi gateway chậm; lỗi thông báo có thể ảnh hưởng API | Gateway có độ trễ, độ tin cậy và chính sách retry phù hợp |
| **B. Ghi yêu cầu gửi vào bảng/outbox, xử lý nền** | Tách xác nhận khỏi gửi, hỗ trợ retry khi thiết kế đúng | Có độ trễ bất đồng bộ, phải vận hành worker và trạng thái gửi | Chấp nhận nhất quán cuối và có vận hành đáng tin |
| **C. Dùng broker/event bus riêng** | Hỗ trợ tích hợp nhiều consumer, phân phối event | Tăng hạ tầng, hợp đồng event, retry, quan sát | Có nhu cầu thực nhiều consumer và năng lực vận hành |
| **D. Chưa gửi chủ động, hiển thị trạng thái rõ** | Ít phụ thuộc, học nhanh từ người dùng | Người dùng rời trang có thể không nhận thông tin kịp | Nhu cầu chủ động thông báo chưa quan trọng ở giai đoạn đầu |

Bảng không nói rằng lựa chọn B/C luôn tốt hơn. Quyết định phụ thuộc **giá trị người dùng, ràng buộc kịp thời, tính đúng và năng lực đội**.

### 12.2. Giữ lựa chọn mở có giới hạn

Một thiết kế có thể giữ quy tắc **xác nhận chỗ** tách khỏi **kênh thông báo**, để sau này thay provider không đổi nghiệp vụ. Nhưng không cần triển khai trọn vẹn ba nhà cung cấp email, SMS, push khi chưa có bằng chứng.

**Thiết kế giữ khả năng thay đổi ≠ xây mọi phương án.** Giữ những ranh giới có giá trị và thử những giả định có thể làm thay đổi quyết định.

### 12.3. Một spike so sánh A và B

Mục tiêu:
> “Khi gateway email trả lỗi hoặc timeout, yêu cầu đăng ký đã được xác nhận có thể còn chính xác và hệ thống có thể khôi phục việc thông báo không?”

Thử:
1. Thiết lập phiên bản đơn giản của cả hai hướng trong môi trường an toàn.
2. Tạo lỗi timeout và gửi lặp.
3. Ghi trạng thái đăng ký, trạng thái phát thông báo và số lần gửi.
4. Xem log/metrics để biết người vận hành có chẩn đoán được lỗi không.
5. Đo độ trễ API và thời gian người dùng nhận thông báo trong điều kiện thử.
6. So sánh chi phí triển khai/vận hành với nhu cầu giai đoạn đầu.
7. Ghi bằng chứng và giới hạn, rồi đề xuất quyết định trước mốc cần phát hành.

Không nên chọn B chỉ vì demo trông “kiến trúc hơn”. Nếu gửi thông báo ngay chưa có giá trị người dùng, lựa chọn D có thể là phần tối thiểu phù hợp trong một giai đoạn.

## 13. Di chuyển kiến trúc tăng dần và có khả năng quay lui

### 13.1. Một quyết định mới cần kế hoạch thay đổi hệ thống đang chạy

ADR mới **không tự biến hệ thống cũ thành hệ thống mới**. Nếu thay đổi ranh giới dữ liệu, cơ chế giao tiếp hoặc nhà cung cấp, nhóm cần:

- Xác định **trạng thái hiện tại** và **trạng thái mục tiêu**.
- Tách thành những bước nhỏ có thể kiểm chứng.
- Làm rõ phụ thuộc và chủ sở hữu dữ liệu.
- Có kiểm thử hồi quy, contract, bảo mật, dữ liệu.
- Thiết kế giám sát và điều kiện dừng/rollback.
- Ghi thời điểm áp dụng thực tế; không chỉ ngày duyệt ADR.
- Xác định **khi nào loại bỏ đường cũ** để không giữ hai hệ thống song song mãi.

### 13.2. Ví dụ mở rộng cơ chế thông báo

Giả sử bản đầu đồng bộ gửi email; sau khi đo thực tế, nhóm quyết định tách xử lý nền. Một tiến trình minh họa:

~~~mermaid
flowchart TD
    A[Đo hiện trạng: latency, lỗi, nhu cầu] --> B[ADR mới: đề xuất xử lý nền]
    B --> C[Viết contract và test idempotency]
    C --> D[Thêm outbox/worker trong phạm vi nhỏ]
    D --> E[Chạy thử với dữ liệu và người dùng giới hạn]
    E --> F{Guardrail và mục tiêu đạt?}
    F -->|Chưa| G[Dừng mở rộng, phân tích, sửa hoặc quay lui]
    F -->|Có| H[Mở rộng dần và theo dõi]
    H --> I[Loại bỏ đường cũ sau khi xác minh]
    G --> C
~~~

Việc dùng **outbox** chỉ là một lựa chọn minh họa. Cần xét cơ chế giao dịch, schema, retry, idempotency và vận hành của sản phẩm thật.

### 13.3. Expand – Migrate – Contract cho dữ liệu

Khi thay đổi schema, một mẫu thường được cân nhắc:

1. **Expand:** thêm khả năng đọc/ghi tương thích mà không phá khách hàng hiện tại.
2. **Migrate:** chuyển dữ liệu và hành vi theo từng bước, kiểm tra tính nhất quán.
3. **Contract:** gỡ bỏ đường dữ liệu/field cũ khi mọi thành phần đã chuyển và có bằng chứng an toàn.

Không nên xóa cột dữ liệu cũ trước khi tất cả ứng dụng liên quan đã được triển khai tương thích. Một rollback mã ứng dụng **không tự đồng nghĩa rollback dữ liệu an toàn** khi schema đã biến đổi không thể đảo ngược; cần có kế hoạch phục hồi riêng và thử nghiệm.

### 13.4. Thời điểm đảo quyết định

Có thể cần ADR mới khi:
- Giả định gốc bị bác bỏ.
- Product Goal hoặc phạm vi dịch vụ thay đổi căn bản.
- Chi phí vận hành trở nên không phù hợp.
- Rủi ro bảo mật hoặc dữ liệu phát sinh.
- Một phụ thuộc nhà cung cấp thay đổi hợp đồng/khả năng.
- Quy mô và độ phức tạp vượt giới hạn mà giải pháp được thiết kế.

Không cần thay kiến trúc mỗi khi xuất hiện một công nghệ mới. **Chi phí đổi hướng phải được so với giá trị và rủi ro nếu giữ nguyên**.

## 14. Liên kết ADR, giả định, code, test và quan sát

### 14.1. Tạo “đường truy vết” đơn giản

Một liên kết hữu ích có thể đi từ vấn đề người dùng đến mã:

~~~text
Product Goal
  -> Product Backlog item WS-13
     -> Architectural risk A-01
        -> ADR-007 (Accepted)
           -> EXP-04 (concurrency test)
           -> integration tests
           -> database migration / implementation PR
           -> logs & metrics
           -> trigger to review ADR-007
~~~

Không nhất thiết tạo công cụ chuyên dụng để lưu mọi liên kết. Có thể ghi mã ID và URL phù hợp ở ADR, issue và pull request; điều quan trọng là người tiếp quản có thể **đi từ lý do đến bằng chứng và triển khai**.

### 14.2. Lưu ngữ cảnh, không chỉ tên công nghệ

Một ADR kiểu:

> “Decision: dùng Kafka vì Kafka tốt và có khả năng mở rộng.”

không trả lời:
- Những yêu cầu nào buộc dùng broker?
- Có bao nhiêu consumer hiện tại và dự kiến?
- Cần ordering, delivery semantics, replay, idempotency ra sao?
- Vận hành và chi phí có chấp nhận được không?
- Phương án đơn giản hơn đã bị loại vì bằng chứng nào?
- Có thể kiểm tra lại quyết định khi bối cảnh đổi không?

Một hồ sơ tốt cần **lý do có thể đánh giá được**, không cần một bài quảng cáo công nghệ.

### 14.3. Sơ đồ bối cảnh hỗ trợ nhưng không thay ADR

Sơ đồ hệ thống, C4 context/container/component hoặc bản vẽ luồng dữ liệu có thể giúp người mới hiểu kiến trúc hiện tại. Tuy nhiên:
- **Sơ đồ** mô tả cấu trúc hoặc tương tác.
- **ADR** giải thích vì sao cấu trúc được chọn.
- **Tests/fitness functions** bảo vệ các thuộc tính quan trọng.
- **Observability** cho biết hệ thống thực tế đang diễn ra thế nào.
- **Runbook** hướng dẫn thao tác khi gặp sự cố.

Các tài liệu bổ trợ nhau. Một sơ đồ chính xác nhưng không có ngày cập nhật hoặc liên kết với code cũng có thể nhanh chóng lỗi thời.

### 14.4. Đồng bộ hóa với thay đổi code

Nhóm có thể thêm một câu hỏi trong review:

> “Thay đổi này có làm khác đi một quyết định kiến trúc đã chấp nhận hoặc giả định quan trọng không?”

Nếu **có**, cần xem:
- Test hoặc guardrail nào phải thay?
- ADR cũ có cần thay trạng thái/viết ADR mới?
- Người vận hành và stakeholder nào cần biết?
- Có cần migration và điều kiện rollback?

Nếu **không**, không cần viết ADR mới cho mọi pull request. Mục tiêu là giữ **hồ sơ đủ đáng tin**, không tạo nghẽn tài liệu.

## 15. Kết hợp quyết định kiến trúc với Lean, XP, Scrum và Kanban

### 15.1. Lean: trì hoãn cam kết khó đảo ngược tới lúc đủ thông tin

Trong Lean, giữ tùy chọn hợp lý giúp tránh xây dư khi chưa biết nhu cầu. Tuy nhiên **không trì hoãn việc kiểm chứng rủi ro an toàn** chỉ vì muốn “quyết muộn”.

Ví dụ:
- Kiểm chứng giao dịch chống xác nhận trùng **sớm**, vì nếu sai sẽ ảnh hưởng người dùng.
- Chưa mua nền tảng thông báo đắt tiền khi người dùng chưa chứng minh nhu cầu.
- Đặt mốc quyết định nhà cung cấp đủ sớm cho hợp đồng, tích hợp, kiểm thử và phát hành.

ADR lưu quyết định; sổ giả định và thử nghiệm cung cấp bằng chứng để biết **khi nào đủ thông tin để cam kết**.

### 15.2. XP: TDD, CI, refactoring và thiết kế đơn giản

- **TDD** giúp diễn đạt quy tắc và kiểm tra thường xuyên.
- **Continuous integration** đưa kiểm tra kiến trúc/contract và regression tests vào dòng phát triển.
- **Refactoring** cải thiện cấu trúc khi behavior còn được bảo vệ.
- **Simple design** tránh kiến trúc quá lớn so với nhu cầu.
- **Pair programming** và collective ownership giúp nhiều người cùng hiểu ranh giới quan trọng.
- **Small releases** tạo cơ hội kiểm tra giả định thực tế trước khi mở rộng.

Không nên coi ADR là cách thay thế TDD hoặc coi unit test đủ để xác minh mọi quyết định kiến trúc liên quan dữ liệu, phân quyền và hiệu năng.

### 15.3. Scrum: dùng sự kiện để kiểm tra và thích ứng

| Điểm trong Scrum | Cách dùng ADR và giả định |
| --- | --- |
| **Product Backlog refinement** | Nhận diện rủi ro kiến trúc trong PBIs, đề xuất spike/kiểm tra cần thiết |
| **Sprint Planning** | Chọn lát cắt giá trị và giả định cần giảm trước, cân nhắc năng lực và DoD |
| **Trong Sprint** | Developers thực hiện test, điều chỉnh kế hoạch và bảo vệ Sprint Goal |
| **Sprint Review** | Kiểm tra Increment và kết quả sản phẩm; cập nhật Product Backlog khi phù hợp |
| **Sprint Retrospective** | Xem cách thảo luận quyết định, review, test, migration có tạo bottleneck không |

**Product Owner** chịu trách nhiệm tối đa hóa giá trị và quản lý Product Backlog; **Developers** sở hữu lựa chọn và thực thi kỹ thuật phù hợp trong Scrum Team; **Scrum Master** giúp Scrum hiệu quả. Những quyết định có tác động bảo mật, pháp lý hoặc vận hành cần chuyên gia và người có quyền quyết định ở phạm vi tương ứng tham gia.

Không phải mọi ADR phải chờ Sprint Review để được chấp nhận. Quyết định cần được đưa ra khi có đủ dữ liệu và đúng thời điểm, tránh trì hoãn công việc hoặc ứng phó sự cố.

### 15.4. Kanban: để việc kiểm chứng chảy qua hệ thống

Một nhóm dùng Kanban có thể theo dõi công việc kiến trúc như:
- Spike cần trả lời câu hỏi và bàn giao bằng chứng.
- Thử nghiệm hiệu năng.
- Tạo integration test và fitness function.
- Migration chia từng lát cắt.
- Refactoring giảm rủi ro theo phạm vi rõ.

Cần xác định **Definition of Workflow**, giới hạn WIP, started/finished và điều kiện hoàn tất. Ví dụ một spike **finished** khi có kết quả tái lập được và quyết định tiếp theo rõ, **không phải** khi đã có code production. Migration lại cần tiêu chuẩn hoàn tất khác.

Quan sát **work item age, cycle time, throughput, blocked** giúp biết giả định nào đang chờ lâu, nhưng không thể quy đổi throughput của một spike thành giá trị người dùng hoặc so trực tiếp với story chức năng.

### 15.5. Cải tiến liên tục theo bằng chứng

Trong Retro hoặc buổi xem xét dòng công việc, nhóm có thể hỏi:
- ADR nào không được tìm thấy khi cần?
- Giả định nào đã sai và sao không được kiểm chứng sớm?
- Test nào phát hiện rủi ro trước release?
- Có quyết định nào bị giữ lại quá lâu dù bằng chứng đã đổi?
- Việc viết ADR có bị biến thành thủ tục khiến quyết định nhỏ bị chậm không?
- Phần nào của Product Goal vẫn chưa được đáp ứng dù kiến trúc “đẹp”?

Những câu hỏi này giúp giữ **kiến trúc phục vụ sản phẩm**, không ngược lại.

## 16. Tình huống xuyên suốt: từ giả định đến ADR và thay đổi có kiểm soát

### 16.1. Bối cảnh

Một nhóm xây ứng dụng workshop. Product Goal là:

> Học viên có thể tự chọn buổi còn chỗ, gửi đăng ký và hiểu rõ kết quả; điều phối viên bảo đảm không xác nhận vượt sức chứa.

Nhóm hiện dùng một ứng dụng và database quan hệ duy nhất. Có hai vấn đề:
1. Hai yêu cầu có thể đến gần đồng thời để tranh một suất cuối.
2. Người dùng thường hỏi lại trạng thái vì không phân biệt “đã gửi yêu cầu” và “đã được xác nhận”.

Một thành viên đề xuất **đưa toàn bộ đăng ký qua một message queue** để “giải quyết cả hai”.

### 16.2. Đặt câu hỏi trước khi chọn công nghệ

Nhóm tách các vấn đề:

| Câu hỏi | Loại | Có queue chắc chắn giải quyết không? |
| --- | --- | --- |
| Dữ liệu không vượt sức chứa? | Tính đúng nghiệp vụ | Chưa chắc; còn transaction, consumer, retry |
| Người dùng hiểu trạng thái? | Outcome và giao diện | Không; cần nghiên cứu/thiết kế thông báo |
| Khi dịch vụ gửi email chậm, xác nhận có bị ảnh hưởng? | Coupling và độ tin cậy | Có thể cải thiện bằng bất đồng bộ, phải thử |
| Có cần nhiều consumer độc lập? | Nhu cầu tích hợp | Chưa có bằng chứng |
| Có thể vận hành broker an toàn? | Năng lực vận hành | Chưa được kiểm chứng |

Nhóm phát hiện đề xuất queue có thể giải quyết **một số cơ chế giao tiếp**, nhưng không thay thế điều kiện đúng nghiệp vụ hay nghiên cứu người dùng.

### 16.3. Hai ADR thay vì một quyết định khổng lồ

**ADR-007:** giữ sức chứa bằng cập nhật có điều kiện và transaction của database hiện tại, với test đồng thời và idempotency.

**ADR-008 (Proposed):** quyết định cách phát thông báo sau xác nhận; so sánh gửi đồng bộ, outbox/worker và broker riêng khi có bằng chứng về nhu cầu.

Việc tách ADR cho phép một quyết định **cần kiểm chứng ngay để bảo vệ dữ liệu**, trong khi quyết định thông báo có thể **đợi thêm thông tin người dùng** nhưng vẫn tiếp tục thử nghiệm.

### 16.4. Sổ giả định gắn với quyết định

| ID | Quyết định liên quan | Điều cần biết | Cách kiểm | Hạn |
| --- | --- | --- | --- | --- |
| A-01 | ADR-007 | Không vượt sức chứa dưới cạnh tranh | Integration/concurrency test | Trước mở đăng ký |
| A-02 | ADR-007 | Retry không tạo tác dụng phụ trùng | Idempotency tests | Trước mở đăng ký |
| A-03 | ADR-007 | Latency đủ tốt dưới tải ban đầu | Load test theo kịch bản | Trước mở rộng |
| A-04 | ADR-008 | Người dùng cần thông báo chủ động hay chỉ trạng thái rõ | Dùng thử có quan sát | Trước chọn nhà cung cấp |
| A-05 | ADR-008 | Gateway lỗi có ảnh hưởng xác nhận | Fault spike | Trước chọn tích hợp |

Nhóm không cần chứng minh toàn bộ những giả định về một tương lai nhiều năm sau. Họ ưu tiên **điều gây thiệt hại nếu sai tại thời điểm sắp giao**.

### 16.5. Ví dụ kết quả thử nghiệm giả định

Giả sử:
- **EXP-04:** chạy 30 lượt thử cạnh tranh, mỗi lượt 100 request và một suất còn lại; trong điều kiện thử, không có lượt nào vượt sức chứa. Các request lặp key không tạo bản ghi mới khi chạy trường hợp đã được thử.
- **EXP-05:** 25 lần thử fault injection khiến gateway email timeout; một số thao tác đồng bộ bị kéo dài hoặc trả lỗi không cần thiết.
- **User test:** 20 người thử giao diện trạng thái rõ; 15 người hiểu đúng “đang chờ xác nhận”, 5 người vẫn không chắc nên làm gì tiếp theo.

**Đây là dữ liệu giả định minh họa**, không phải kết quả chạy kiểm thử hoặc nghiên cứu thật. Từ đó có thể nói:
- Có bằng chứng **hỗ trợ** lựa chọn transaction trong phạm vi đã thử.
- Có dấu hiệu cơ chế gửi email đồng bộ **ảnh hưởng trải nghiệm và độ tin cậy** khi gateway lỗi.
- Chưa có cơ sở để tuyên bố Product Goal về trạng thái đã đạt hoàn toàn.
- Chưa đủ dữ liệu để kết luận queue riêng tốt hơn outbox/worker hoặc cải thiện giao diện.
- Các test bảo vệ dữ liệu cần tiếp tục chạy khi thay đổi code, DB và cấu hình.

Không được suy “30 lượt test đạt” thành bảo đảm **không bao giờ** có race condition.

### 16.6. Quyết định tiếp theo

Nhóm có thể:
1. Đưa các test tính đúng quan trọng vào CI.
2. Phát hành lát cắt đăng ký trong phạm vi đáp ứng DoD và điều kiện vận hành.
3. Thử cải thiện trạng thái hiển thị, theo dõi câu hỏi người dùng.
4. Tiếp tục đánh giá phương án gửi thông báo với fault spike và chi phí vận hành.
5. Khi có bằng chứng phù hợp, **Accepted** ADR-008 với phạm vi rõ.
6. Nếu thay đổi kiến trúc gửi thông báo, dùng migration tăng dần và kiểm tra khả năng phục hồi.
7. Ghi nguồn kết quả, phiên bản và điều kiện xem lại vào các ADR.

### 16.7. Giả định bị bác bỏ sau khi sản phẩm mở rộng

Sau vài tháng, giả sử tải thực tế tăng và latency của thao tác xác nhận vượt ngưỡng đã chấp nhận. Điều này **không có nghĩa ADR-007 là một quyết định tồi trong bối cảnh ban đầu**. Nó cho thấy điều kiện đã đổi và cần nhìn lại.

Nhóm nên:
- Thu dữ liệu thực và phân tích điểm nghẽn.
- Kiểm tra phương án tối ưu transaction/index/cấu trúc truy cập trước.
- Nếu cần một hướng khác, đề xuất ADR mới với phương án và đánh đổi.
- Kiểm chứng khả năng giữ bất biến và xử lý retry của phương án mới.
- Lập kế hoạch chuyển đổi cùng quan sát và cách dừng.
- Đánh dấu ADR cũ **Superseded** khi quyết định mới thay thế thực sự.

Thiết kế tiến hóa là **lựa chọn phù hợp nhất theo bối cảnh và bằng chứng đang có**, rồi thay đổi có trách nhiệm khi bối cảnh khác đi.

## 17. Đo hiệu quả: quyết định được sử dụng và rủi ro được giảm hay chưa?

Không nên đánh giá thành công bằng **số ADR đã viết** hoặc **số thử nghiệm đã chạy**. Những chỉ số đó có thể tăng ngay cả khi nhóm không giao giá trị.

### 17.1. Bốn nhóm tín hiệu

| Nhóm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Truy vết quyết định** | Khi cần thay đổi, người mới có tìm được lý do và trạng thái không? | ADR có link đến code/test và bản thay thế |
| **Giảm bất định** | Giả định rủi ro lớn đã có bằng chứng phù hợp chưa? | A-01 có integration test thực, A-03 có đo tải |
| **Chất lượng kiến trúc và delivery** | Ranh giới, dữ liệu, vận hành còn đúng khi thay đổi không? | CI fitness tests, lỗi dữ liệu, migration rehearsal |
| **Giá trị sản phẩm** | Người dùng có nhận ích lợi được mong muốn không? | Ít xác nhận nhầm, ít phải hỏi lại trạng thái |

### 17.2. Đo cả thời gian chờ quyết định

Có thể quan sát:
- Thời gian từ **phát hiện rủi ro** đến khi có quyết định có đủ căn cứ.
- Thời gian một spike bị blocked trước khi có kết quả.
- Số lần phải thảo luận lại do **không biết lý do quyết định cũ**.
- Chi phí thay đổi do giả định đã sai nhưng không được cập nhật.
- Sự ổn định của fitness functions và tình trạng false positives/flaky checks.
- Sự cố và rework liên quan ranh giới dữ liệu/contract.

Cần hiểu **loại quyết định và mức hậu quả** trước khi so sánh thời gian. Không nên đặt KPI kiểu “mọi ADR phải được duyệt trong một ngày” nếu một quyết định liên quan tính an toàn cần đánh giá nghiêm túc.

### 17.3. Một ADR tốt không cần dài

Nếu người mới đọc trong vài phút và hiểu:
- Điều gì đã được chọn.
- Vì sao.
- Dựa trên giả định nào.
- Những test hoặc dữ liệu nào hỗ trợ.
- Chi phí và rủi ro.
- Khi nào cần xem lại.

thì ADR đang phục vụ mục đích. Không nhất thiết đo số chữ hoặc yêu cầu sơ đồ phức tạp cho mọi quyết định.

### 17.4. Phân biệt cải thiện kiến trúc và cải thiện sản phẩm

Giả sử nhóm chuyển gửi thông báo từ đồng bộ sang nền và giảm p95 API trong điều kiện đo. Đây là **bằng chứng về thay đổi kỹ thuật**. Để biết **giá trị sản phẩm**, vẫn cần theo dõi người dùng có nhận trạng thái chính xác, kịp thời và hiểu kết quả không.

Ngược lại, một cải tiến giao diện làm giảm số lần hỏi lại có thể mang giá trị mà **không cần đổi kiến trúc**. Hãy giữ Product Goal làm mốc, không nhầm xây thêm hạ tầng với tiến bộ sản phẩm.

## 18. Những sai lầm phổ biến khi dùng ADR và kiểm chứng giả định

| Sai lầm | Hậu quả | Cách điều chỉnh |
| --- | --- | --- |
| ADR chỉ ghi “chọn công nghệ X” | Không hiểu vấn đề và đánh đổi | Ghi context, alternatives, drivers, consequences |
| Ghi Accepted và hiểu là mọi giả định đã chứng minh | Tạo niềm tin giả | Tách decision status, implementation và evidence |
| Không ghi giải pháp bị loại | Người mới lặp lại thảo luận cũ | Lưu 2–3 phương án thực sự đã cân nhắc và lý do |
| Chỉ ghi ưu điểm | Không lộ chi phí hay điều kiện thất bại | Ghi nhược điểm, rủi ro và giới hạn |
| Viết lại ADR cũ khi đổi hướng | Mất lịch sử học hỏi | Viết ADR mới và liên kết supersedes |
| Một ADR bao trùm mọi thứ | Không biết giả định nào tác động quyết định nào | Tách theo quyết định có thể đánh giá độc lập |
| Lưu ADR ở nhiều nơi khác nhau | Phiên bản mâu thuẫn | Chọn nguồn chính, nơi khác chỉ liên kết |
| Giả định “DB sẽ nhanh” | Không thể kiểm chứng | Gắn tải, thao tác, ngưỡng và môi trường |
| Chỉ test với mock rồi tuyên bố transaction an toàn | Race condition/lỗi thật bị bỏ sót | Integration test phù hợp kho dữ liệu thật |
| Test chạy một lần được coi là bảo đảm vĩnh viễn | Không thấy rủi ro khi tải và cấu hình đổi | Ghi phạm vi, phiên bản và điều kiện tái kiểm |
| Chỉ dùng test hiệu năng làm bằng chứng về đúng dữ liệu | Lẫn hai loại thuộc tính | Tách invariant, concurrency, performance và security |
| Dùng spike không có câu hỏi/timebox | Nghiên cứu kéo dài, không có quyết định | Ghi mục tiêu, điều kiện dừng và bằng chứng |
| Đưa prototype trực tiếp lên production | Thiếu kiểm thử, bảo mật, vận hành | Củng cố DoD, integration, quality và migration |
| Fitness functions chỉ viết rồi không chạy | Không bảo vệ được ranh giới | Liên kết CI hoặc nhịp kiểm tra rõ |
| Quá nhiều kiểm tra hình thức/flaky | Pipeline thiếu tin cậy | Giữ các tiêu chí có giá trị, sửa false positives |
| Tạo abstraction trước mọi công nghệ giả định | Phức tạp hóa thiết kế | Giữ tùy chọn cần thiết, tránh xây dư |
| Tối ưu kiến trúc nhưng không đo giá trị người dùng | Giao nhiều hạ tầng ít ích lợi | Kết nối Product Goal, outcome và guardrails |
| Không thử migration và rollback dữ liệu | Đổi kiến trúc có thể gây mất dữ liệu | Rehearsal, backup, expand–migrate–contract phù hợp |
| Không làm rõ owner/hạn kiểm chứng | Giả định quan trọng trôi qua thời hạn | Gắn người theo dõi, mốc và điều kiện chặn |
| Coi ADR như cửa phê duyệt cho mọi refactor | Tăng hàng chờ và thủ tục | Chỉ ghi các quyết định kiến trúc đáng nhớ, có tác động |
| Chỉ báo “test xanh” mà không nói phạm vi | Stakeholder hiểu sai mức chắc chắn | Công bố dữ liệu, môi trường, giới hạn và rủi ro còn lại |

## 19. Bài thực hành: ghi quyết định và kiểm chứng giả định

### 19.1. Bối cảnh

Một nhóm xây ứng dụng workshop có:
- 10 chỗ trong mỗi buổi.
- Có thể có nhiều yêu cầu đồng thời tranh suất cuối.
- Người dùng cần biết trạng thái “đã tiếp nhận”, “đang chờ” hay “đã xác nhận”.
- Một dịch vụ email bên ngoài có thể chậm hoặc gửi lặp.
- Database quan hệ hiện có, ứng dụng có thể chạy trên hai instance.
- Một bên liên quan đề xuất chuyển sang microservices và message queue ngay lập tức.

Đây là tình huống **giả định**, không có hệ thống production được truy cập hoặc kiểm thử trong bài.

### 19.2. Nhiệm vụ A – Tách dữ kiện, giả định và quyết định (15 phút)

Phân loại các câu sau:

1. “Sản phẩm đang chạy trên một database quan hệ.”
2. “Database này đủ xử lý 100 yêu cầu gần đồng thời.”
3. “Không được xác nhận vượt sức chứa.”
4. “Nên dùng hàng đợi vì hệ thống sẽ tăng trưởng.”
5. “Thử 100 request trên môi trường có transaction để kiểm bất biến.”
6. “Chọn cập nhật có điều kiện trước khi xem xét hàng đợi riêng.”

**Gợi ý:** (1) là bối cảnh theo đề; (2) là giả định cần đo; (3) là ràng buộc nghiệp vụ; (4) là đề xuất dựa trên suy đoán tăng trưởng; (5) là phương pháp kiểm chứng; (6) là quyết định có thể được chấp nhận **có điều kiện** sau khi cân nhắc các phương án.

### 19.3. Nhiệm vụ B – Viết một ADR trong 20 phút

Hãy ghi một ADR cho quyết định “bảo vệ sức chứa bằng database transaction ở bản đầu” gồm:
- ID, tiêu đề, ngày, trạng thái.
- Bối cảnh và Product Goal liên quan.
- Ít nhất ba decision drivers.
- Ít nhất hai phương án thật và lý do chọn.
- Lợi ích, chi phí, rủi ro.
- Hai giả định phải kiểm.
- Một thử nghiệm có điều kiện PASS/FAIL rõ.
- Điều kiện xem lại và liên kết công việc.

Một ADR đạt yêu cầu **không nhất thiết dài**, nhưng người khác đọc phải hiểu vì sao nhóm **không chọn queue ngay từ đầu**.

### 19.4. Nhiệm vụ C – Ưu tiên giả định (10 phút)

Chọn thứ tự kiểm chứng:
- **A:** không xác nhận trùng chỗ dưới tải đồng thời.
- **B:** người dùng hiểu đúng trạng thái.
- **C:** hiệu năng đủ ở mức tải ban đầu.
- **D:** nhà cung cấp email có thể thay thế dễ dàng.
- **E:** hoạt ảnh trang chủ sẽ tăng đăng ký.

Giải thích bằng **hậu quả nếu sai, bằng chứng hiện tại, mốc cần biết và giá trị của việc kiểm chứng**. Không có một thứ tự cố định cho mọi sản phẩm, nhưng A là rủi ro dữ liệu quan trọng cần xử lý trước khi chấp nhận xác nhận thật.

### 19.5. Nhiệm vụ D – Thiết kế experiment cho bất biến (20 phút)

Viết EXP-04 có:
1. Giả thuyết và điều kiện kiểm.
2. Một workshop capacity = 10, confirmed_count = 9.
3. 100 request **khác nhau** gần đồng thời qua hai instance.
4. Đọc số xác nhận thành công và dữ liệu cuối.
5. Test retry **cùng request key**.
6. Phương án kiểm tra khi transaction lỗi/timeout.
7. Điều kiện PASS, FAIL và trường hợp **inconclusive**.
8. Cấu hình DB, isolation level, phiên bản mã và số lượt lặp.
9. Rủi ro còn lại sau khi test đạt.
10. Hành động nếu test thất bại.

**Gợi ý:** điều kiện cơ bản là dữ liệu không vượt 10, chỉ tối đa một xác nhận mới hợp lệ, không tạo thêm bản ghi bởi retry cùng key. Test đạt trong môi trường giả định **không chứng minh mọi loại lỗi sẽ không bao giờ xảy ra**.

### 19.6. Nhiệm vụ E – Lập fitness functions (15 phút)

Thiết kế ít nhất:
- **Một kiểm tra tính đúng:** bất biến sức chứa.
- **Một kiểm tra cấu trúc:** domain không phụ thuộc trực tiếp framework HTTP.
- **Một kiểm tra khả năng thay đổi:** contract của cổng thông báo.
- **Một kiểm tra hiệu năng có ngưỡng:** giả định tải cụ thể.
- **Một kiểm tra bảo mật:** không cho người dùng đọc đăng ký của người khác.

Với mỗi kiểm tra, ghi **cách chạy, điều kiện thất bại, người nhận kết quả và tần suất kiểm**.

### 19.7. Nhiệm vụ F – Ra quyết định khi bằng chứng thay đổi (15 phút)

Giả sử sau hai tháng:
- Hệ thống vẫn đúng về sức chứa.
- p95 của xác nhận tăng cao dưới tải thật.
- Nhiều yêu cầu chờ vì cạnh tranh trên một hàng dữ liệu.
- Bộ phận kỹ thuật đề xuất bổ sung queue.

Bạn sẽ:
1. Điều tra và đo thêm điều gì để phân biệt nguyên nhân?
2. Xem phương án nào trước khi thêm hạ tầng mới?
3. Viết ADR mới hay sửa đè ADR cũ?
4. Định nghĩa điều kiện an toàn khi migration như thế nào?
5. Test nào phải tiếp tục giữ để không đánh đổi tính đúng lấy tốc độ?
6. Khi nào có thể xóa cấu trúc cũ?

**Gợi ý:** ghi ADR mới có bằng chứng, liên kết thay thế, đo và thử phương án mới. Hệ thống chỉ chuyển toàn bộ khi dữ liệu, vận hành và guardrails được kiểm chứng phù hợp. Không tự suy queue giải quyết mọi điểm nghẽn.

### 19.8. Nhiệm vụ G – Tính và diễn giải tỷ lệ thử nghiệm (10 phút)

Trong một thử nghiệm **giả định**, có 40 lượt kiểm tra tự động một cấu hình, trong đó 39 lượt đạt và một lượt phát hiện trạng thái vượt sức chứa.

1. Tính tỷ lệ đạt: **39/40 = 97,5%**.
2. Có nên nói “97,5% yêu cầu an toàn nên có thể phát hành” không?
3. Quyết định nào cần đưa ra khi một lượt đã vi phạm bất biến quan trọng?
4. Dữ liệu cần giữ để tái lập lỗi là gì?
5. Khi sửa xong, cần thay đổi kiểm tra hồi quy thế nào?

**Gợi ý:** một lỗi phá bất biến nghiêm trọng có thể là **điều kiện chặn phát hành** bất kể tỷ lệ test đạt cao; cần điều tra nguyên nhân và xác minh sửa lỗi. Đây không phải bài toán chấp nhận một phần trăm lỗi dữ liệu.

### 19.9. Nhiệm vụ H – Thảo luận cùng Scrum Team hoặc nhóm Kanban (15 phút)

Trong Scrum, thử trình bày ở refinement/Sprint Planning:
- PBI người dùng đang cần giá trị gì?
- Quyết định nào cần chốt trước khi chọn lát cắt?
- Giả định nào cần spike ngắn?
- DoD và fitness tests nào bảo vệ kết quả?
- Bằng chứng nào sẽ mang vào Sprint Review?
- Điều gì cần cải thiện trong Retrospective?

Trong Kanban, mô tả work item “kiểm chứng phương án transaction” với **started/finished**, WIP, điều kiện hoàn tất và cách tránh bị blocked vô thời hạn. Phân biệt hoàn thành **spike nghiên cứu** với hoàn thành **Increment sản phẩm**.

### 19.10. Thang tự đánh giá

| Tiêu chí | Chưa đạt | Đạt | Vững |
| --- | --- | --- | --- |
| **Phân loại thông tin** | Coi đề xuất kỹ thuật là sự thật | Tách bối cảnh, giả định, quyết định, bằng chứng | Nêu mức chắc chắn, hạn dùng và điều kiện đổi quyết |
| **ADR** | Chỉ ghi “chọn X” | Có context, options, decision, consequences | Có assumption, evidence, trigger, lịch sử supersedes |
| **Thử nghiệm** | Demo chạy một lần rồi kết luận tuyệt đối | Có hypothesis, điều kiện và phạm vi test | Có guardrail, inconclusive, khả năng tái lập và revalidation |
| **Fitness functions** | Chỉ nói “cần test nhiều” | Đề xuất kiểm tra phù hợp thuộc tính | Liên kết CI, vận hành và chủ sở hữu kiểm tra |
| **Thay đổi an toàn** | Viết đè lịch sử, chuyển toàn bộ một lần | Có ADR mới và migration có kiểm chứng | Xem rollback dữ liệu, observability, xóa đường cũ có điều kiện |
| **Agile** | Kiến trúc tách rời nhu cầu người dùng | Liên kết Product Goal và Increment | Đọc flow, quality, outcome và cải tiến dựa trên bằng chứng |

## 20. Biểu mẫu áp dụng ngay

### 20.1. ADR tối giản

~~~text
ADR ID và tiêu đề:
Ngày:
Status: Proposed / Accepted / Superseded / ...
Decision owner và người tham vấn:

Context / Product Goal liên quan:
Quyết định cần đưa ra:
Ràng buộc không được đánh đổi:
Tiêu chí lựa chọn (decision drivers):

Các phương án:
A:
B:
C (nếu có):

Phương án đã chọn và phạm vi:
Lý do:
Hệ quả tích cực:
Chi phí, đánh đổi, rủi ro:

Giả định trọng yếu và ID liên kết:
Bằng chứng hiện có (nguồn, phạm vi, ngày):
Điều cần thử và hạn kiểm:
Fitness function / guardrail:
Điều kiện xem lại:
Issue / PR / tests / migration / ADR liên quan:
Nếu bị thay thế, link ADR mới:
~~~

### 20.2. Phiếu giả định

~~~text
Assumption ID:
Phát biểu có thể kiểm chứng:
Quyết định kiến trúc liên quan:
Điều gì xảy ra nếu giả định sai:
Bằng chứng hiện tại:
Mức độ bất định và hậu quả:
Điều kiện cần quan sát:
Phương pháp thử:
Owner:
Mốc phải biết:
Kết quả và giới hạn:
Status: Unknown / Supporting / Contradicted / Revalidate:
Ngày, phiên bản, cấu hình:
Điều kiện cần kiểm tra lại:
~~~

### 20.3. Phiếu thử nghiệm kỹ thuật

~~~text
Experiment ID:
ADR/Assumption được hỗ trợ:
Câu hỏi cần trả lời:
Hypothesis:
Environment và phiên bản:
Tải/dữ liệu/setup:
Các bước tái lập:
Metric và điều kiện PASS:
Điều kiện FAIL:
Điều kiện INCONCLUSIVE:
Guardrail và cách dừng an toàn:
Thời lượng/timebox:
Log, biểu đồ, kết quả:
Giới hạn và biến gây nhiễu:
Quyết định tiếp theo:
Ai phê duyệt/tiếp nhận kết quả:
~~~

### 20.4. Phiếu fitness function

~~~text
Tên fitness function:
Thuộc tính kiến trúc cần bảo vệ:
ADR / rủi ro liên quan:
Đầu vào và môi trường:
Phép kiểm:
Ngưỡng/điều kiện lỗi:
Tần suất chạy:
Ai nhận cảnh báo:
Cách xử lý khi đỏ:
Trường hợp ngoại lệ và điều kiện cho phép:
Khi nào ngưỡng hoặc cách đo phải xem lại:
~~~

### 20.5. Phiếu thay thế quyết định và migration

~~~text
ADR hiện tại:
Bằng chứng khiến phải xem lại:
ADR thay thế đề xuất:
Phạm vi code, dữ liệu, dịch vụ bị ảnh hưởng:
Các bước thay đổi nhỏ:
Kiểm thử hồi quy / contract / security:
Kế hoạch migration và xác minh dữ liệu:
Quan sát production / SLO hoặc guardrail:
Điều kiện dừng hoặc rollback:
Hạn chế rollback dữ liệu:
Thời điểm áp dụng thực tế:
Khi nào loại bỏ đường cũ:
Người chịu trách nhiệm:
Liên kết PR, test, báo cáo và ADR superseded:
~~~

Biểu mẫu là **gợi ý thực hành**, không phải thủ tục bắt buộc của Scrum hoặc một tiêu chuẩn ADR duy nhất. Dùng mức chi tiết **tương xứng hậu quả và chi phí thay đổi**. Quyết định nhỏ, dễ đảo ngược có thể chỉ cần một đoạn giải thích trong code review.

## 21. Checklist: lưu quyết định và kiểm chứng giả định trước khi mở rộng

**Bối cảnh và quyết định:**

- [ ] Quyết định kiến trúc gắn với Product Goal, yêu cầu hoặc rủi ro cụ thể.
- [ ] Phân biệt sự kiện, giả định, giả thuyết, quyết định và bằng chứng.
- [ ] ADR có ID, tiêu đề, trạng thái, bối cảnh và người chịu trách nhiệm.
- [ ] Có các phương án thật sự đã cân nhắc và lý do chọn hoặc loại.
- [ ] Ghi cả lợi ích, chi phí, hệ quả không mong muốn và giới hạn.
- [ ] Không viết ADR cho mọi thay đổi nhỏ không có tác động kiến trúc.
- [ ] Khi đổi hướng, giữ lịch sử và liên kết ADR mới thay thế ADR cũ.

**Giả định và thực nghiệm:**

- [ ] Các giả định hậu quả lớn được ghi rõ và có người theo dõi.
- [ ] Mỗi giả định quan trọng có một câu hỏi kiểm chứng quan sát được.
- [ ] Phép thử phù hợp đúng loại thuộc tính: correctness, concurrency, load, security, contract hoặc user outcome.
- [ ] Có cách ghi môi trường, dữ liệu, phiên bản, số lần chạy và giới hạn kết luận.
- [ ] Thử nghiệm/spike có timebox và điều kiện dừng.
- [ ] Biết phân biệt PASS, FAIL và INCONCLUSIVE.
- [ ] Không coi demo, mock test hoặc một lần chạy xanh là bảo đảm production.
- [ ] Rủi ro an toàn, dữ liệu và quyền riêng tư được bảo vệ trước khi thử hoặc phát hành.
- [ ] Có mốc tái kiểm khi tải, cấu hình, sản phẩm hoặc nhà cung cấp thay đổi.

**Bảo vệ kiến trúc và thay đổi:**

- [ ] Những ranh giới quan trọng có fitness functions hoặc cách kiểm tra lặp lại.
- [ ] Kiểm tra phù hợp được tích hợp trong CI hoặc nhịp vận hành có trách nhiệm.
- [ ] Code/test/issue/ADR có liên kết để người khác truy vết được.
- [ ] Status Accepted không bị hiểu nhầm là implementation/test đã hoàn tất.
- [ ] Migration chia bước, có xác minh dữ liệu và phương án dừng/quay lui phù hợp.
- [ ] Không xóa cấu trúc cũ trước khi khách hàng và dữ liệu đã chuyển an toàn.
- [ ] Lưu kết quả quan sát thật sau khi thay đổi, không chỉ kế hoạch trên giấy.
- [ ] Hệ quả kiến trúc được xem cùng chất lượng và giá trị người dùng.

**Học hỏi Agile:**

- [ ] Product Backlog phản ánh công việc giảm rủi ro và kiểm chứng khi cần.
- [ ] Scrum Team hoặc nhóm Kanban biết giả định nào đang blocked và phải quyết khi nào.
- [ ] XP/TDD/refactoring/CI được sử dụng để giảm chi phí thay đổi khi phù hợp.
- [ ] Có cơ chế kiểm tra lại kiến trúc khi bằng chứng mới trái giả định cũ.
- [ ] Số ADR và số test không thay thế đo chất lượng, flow và outcome.
- [ ] Nhóm chọn **kiến trúc đủ tốt với bằng chứng hiện tại**, không chạy theo công nghệ mới hoặc bảo vệ lựa chọn cũ bằng mọi giá.

**Kết luận:** **Lưu quyết định kiến trúc** giúp nhóm không quên **vì sao** một cấu trúc được chọn. **Kiểm chứng các giả định quan trọng** giúp biết **quyết định đó còn phù hợp đến đâu**, trong điều kiện nào và khi nào phải đổi. Hai thực hành kết hợp với thiết kế đơn giản, test tự động, migration tăng dần, quan sát vận hành và phản hồi người dùng tạo ra **thiết kế tiến hóa có trách nhiệm**: nhóm có thể thay đổi cấu trúc theo hiểu biết mới mà vẫn giữ tính đúng, chất lượng và khả năng giao giá trị lâu dài.
