# Thực hành tổng hợp: Xây dựng backlog rồi điều chỉnh ưu tiên sau phản hồi

Một nhóm sản phẩm được giao xây cổng đăng ký workshop. Ban đầu, stakeholder cho rằng “người học cần email xác nhận thật đẹp”, còn nhóm kỹ thuật muốn làm trang quản trị để người tổ chức nhìn thấy danh sách đăng ký. Sau Increment đầu tiên, một số học viên lại hiểu nhầm trạng thái **PENDING** là “đã được giữ chỗ”; Support nhận nhiều câu hỏi, còn một lỗi timeout có nguy cơ khiến giao diện trình bày trạng thái cũ như kết quả mới. Nếu nhóm vẫn triển khai các ticket theo thứ tự ban đầu chỉ vì “Sprint/roadmap đã chốt”, họ có thể làm đúng kế hoạch mà **không cải thiện vấn đề quan trọng nhất của người dùng**.

Bài thực hành này mô phỏng **toàn bộ chu trình từ mục tiêu sản phẩm đến Product Backlog được sắp thứ tự, giao một lát cắt phần mềm, thu phản hồi, kiểm tra bằng chứng và điều chỉnh ưu tiên**. Người học sẽ tạo những đầu ra cụ thể: Product Goal, user stories, acceptance criteria, bảng backlog có lý do sắp thứ tự, giả thuyết cần kiểm, feedback log, backlog sau điều chỉnh, quyết định có trade-off, kế hoạch Increment tiếp theo và cách đo hiệu quả.

Bài thuộc chương **Thực hành tổng hợp** của mô-đun **AGILE_DEVELOPMENT**. Phạm vi kết hợp giá trị và nguyên tắc Agile – phản hồi sớm, bàn giao tăng dần, thích ứng và cải tiến liên tục – với **user story, Product Backlog, Scrum, Kanban, XP và flow metrics**. Trọng tâm không phải thuộc một công thức chấm điểm ưu tiên, mà là **xây backlog đủ minh bạch để có thể đổi quyết định khi bằng chứng thay đổi**.

**Lưu ý về bối cảnh:** mọi nhân vật, số liệu, chi phí, giá trị, giả thuyết và phản hồi trong bài là ví dụ giả định. Các phép tính minh họa cách ra quyết định, không phải dự báo chính xác cho dự án thật. Với sản phẩm có dữ liệu cá nhân, thanh toán hoặc an toàn, không được bỏ các yêu cầu kiểm soát chỉ vì một PBI được chấm điểm thấp.

## 1. Kết quả học tập và sản phẩm đầu ra

Sau khi hoàn thành bài, bạn có thể:

1. Xác định **ranh giới sản phẩm, người dùng, Product Goal** và tiêu chí đánh giá kết quả.
2. Phỏng vấn hoặc tổng hợp nhu cầu theo **vấn đề, ngữ cảnh, bằng chứng và giả định**, thay vì sao chép mọi yêu cầu thành solution ticket.
3. Viết user story có **người dùng – nhu cầu – lợi ích**, acceptance criteria và liên kết mục tiêu.
4. Chia story lớn thành **lát cắt dọc (vertical slice)** có thể kiểm chứng, tránh tách thuần frontend/backend/test rồi coi từng phần là giá trị hoàn tất.
5. Tạo một Product Backlog có ID, tiêu đề, mô tả, giá trị/rủi ro, điều kiện Done, phụ thuộc, kích thước tương đối và **thứ tự duy nhất**.
6. Phân biệt **sắp thứ tự Product Backlog** với Sprint Backlog, cam kết Sprint Goal và lịch giao hàng chắc chắn.
7. Chọn một Increment nhỏ đạt Definition of Done và thiết kế **kênh phản hồi trước khi xây**.
8. Phân loại dữ liệu sau giao thành quan sát, giả thuyết, sự cố, ý kiến và đề xuất giải pháp.
9. **Thay đổi thứ tự backlog có lý do**: thêm, làm rõ, chia nhỏ, nâng/hạ ưu tiên, gộp hoặc bỏ PBI.
10. Trình bày minh bạch **PBI nào dịch chuyển, vì sao và công việc nào phải chờ**.
11. Xử lý ưu tiên mới khi đang trong Sprint theo trách nhiệm của Product Owner, Developers và Sprint Goal; vận dụng Kanban nếu không dùng Sprint.
12. Đánh giá kết quả đổi ưu tiên bằng outcome, chất lượng, flow, độ bất định và khả năng học tiếp.

**Bộ đầu ra cuối bài** gồm:
- Phiếu Product Goal và giả thuyết giá trị.
- Bản đồ hành trình đăng ký và khoảng cần học.
- Bảng Product Backlog phiên bản V0.
- Một PBI mẫu có user story, AC và kiểm thử.
- Bản tóm tắt Increment đầu tiên cùng cách thu dữ liệu.
- Feedback log F01–F04.
- Bảng Product Backlog phiên bản V1 có thay đổi thứ tự.
- Decision log, kế hoạch Sprint/luồng tiếp theo và bộ chỉ số kiểm chứng.

## 2. Sơ đồ toàn bộ bài thực hành

~~~mermaid
flowchart TD
    A[1. Product Goal và hành trình người dùng] --> B[2. Thu nhu cầu và viết user stories]
    B --> C[3. Chia vertical slices và đặt acceptance criteria]
    C --> D[4. Product Backlog V0 có thứ tự và lý do]
    D --> E[5. Chọn Increment nhỏ đạt DoD]
    E --> F[6. Giao/thử có kiểm soát và thu feedback]
    F --> G{7. Bằng chứng nói gì?}
    G -->|Lỗi nghiêm trọng| H[Mitigation/incident theo policy]
    G -->|Giả thuyết cần thử| I[Experiment/PBI nhỏ]
    G -->|Giá trị hoặc nhu cầu đổi| J[Đổi thứ tự, gộp, tách, dừng PBI]
    G -->|Chưa đủ dữ liệu| K[Đặt câu hỏi và tiếp tục quan sát]
    H --> L[8. Product Backlog V1 và quyết định minh bạch]
    I --> L
    J --> L
    K --> L
    L --> M[9. Thương lượng scope/capacity, triển khai]
    M --> N[10. Kiểm chứng outcome/quality/flow]
    N --> A
~~~

**Mỗi mũi tên phải tạo một đầu ra có thể quan sát**, không chỉ là một cuộc họp đã diễn ra. Vòng lặp không nhất thiết tuần tự cứng: lỗi bảo mật nghiêm trọng cần xử lý ngay; Product Backlog có thể được refined bất cứ khi nào có thông tin mới; nhóm có thể đo flow liên tục mà không đợi kết thúc Sprint.

## 3. Dự án mẫu: cổng đăng ký workshop

### 3.1. Bối cảnh kinh doanh

Một đơn vị tổ chức workshop trực tuyến và trực tiếp. Hiện nay học viên gửi thông tin qua biểu mẫu; nhân viên dùng bảng tính để kiểm tra sức chứa và gửi xác nhận thủ công. Hệ quả được nhóm **giả định cần kiểm chứng**:
- Học viên không biết mình đã có chỗ hay chưa.
- Người tổ chức mất thời gian tìm trạng thái mới nhất.
- Có nguy cơ hai đăng ký tranh suất cuối.
- Support phải giải thích trạng thái nhiều lần.
- Bước xác nhận chậm có thể khiến người học bỏ cuộc.

Nhóm được phép xây cổng đăng ký và kiểm tra một bộ học viên/nhà tổ chức nhỏ. Họ không được tự ý thu nhiều dữ liệu cá nhân hơn mức cần thiết; phải có chính sách quyền truy cập và xử lý sự cố phù hợp.

### 3.2. Các vai trò và nhu cầu

| Vai trò | Việc muốn hoàn thành | Nỗi lo/rủi ro | Bằng chứng cần tìm |
| --- | --- | --- | --- |
| **Học viên** | Gửi đăng ký và hiểu trạng thái | Tưởng PENDING là có chỗ, không nhận thông tin kịp | Quan sát tác vụ, câu hỏi Support, tỷ lệ hiểu đúng |
| **Người tổ chức** | Quản lý sức chứa và quyết định xác nhận | Xác nhận vượt số chỗ, dữ liệu lệch | Log nghiệp vụ, test đồng thời, dữ liệu kiểm toán |
| **Support** | Giải thích và hỗ trợ đăng ký | Không biết nguồn trạng thái đáng tin | Loại ticket, thời gian xử lý, câu hỏi lặp |
| **Product Owner** | Tối đa hóa giá trị và định thứ tự backlog | Tập trung tính năng hấp dẫn nhưng không giải vấn đề | Product Goal, phản hồi, trade-off |
| **Developers** | Tạo Increment Done, an toàn và thay đổi được | Hợp đồng trạng thái, timeout, test tích hợp | AC, DoD, CI, telemetry, incident |
| **Stakeholders/leadership** | Đầu tư hợp lý, giảm rủi ro, đạt mục tiêu | Phát hành chậm hoặc dữ liệu không tin cậy | Outcome/flow/quality và báo cáo quyết định |

### 3.3. Ngôn ngữ nghiệp vụ thống nhất

Trong bài này, trạng thái có nghĩa:
- **PENDING:** hệ thống đã nhận **yêu cầu đăng ký**, nhưng **chưa giữ chỗ**; không được truyền đạt là đã xác nhận.
- **CONFIRMED:** yêu cầu đã được chấp nhận, chỗ đã được giữ theo giao dịch có thẩm quyền; sức chứa được kiểm tra và cập nhật nhất quán.
- **CANCELLED:** đăng ký bị hủy theo quy tắc và quyền hợp lệ; tác động tới chỗ trống phải đúng.
- **UNKNOWN/ERROR trên client:** chưa xác minh được trạng thái mới; **không phải CONFIRMED**. Đây là trạng thái hiển thị lỗi, không nhất thiết là trạng thái nghiệp vụ được lưu.

Định nghĩa này phải được dùng chung bởi người tổ chức, Product Owner, Developers, test và Support. Nếu mỗi nhóm hiểu PENDING khác nhau, backlog dù sắp thứ tự tốt vẫn dẫn tới sản phẩm sai.

### 3.4. Product Goal mẫu

> **Trong giai đoạn đầu, học viên có thể gửi đăng ký workshop, tự xem trạng thái đúng và không bị hiểu nhầm rằng yêu cầu PENDING đã giữ chỗ; người tổ chức không xác nhận vượt sức chứa.**

Đây là **mục tiêu định hướng**, chưa phải một metric hoàn chỉnh. Nhóm có thể kiểm:
- Tỷ lệ học viên hiểu đúng trạng thái trong một tác vụ có ngữ cảnh.
- Tỷ lệ đăng ký hợp lệ/hoàn tất theo định nghĩa.
- Số câu hỏi Support về trạng thái trên một đơn vị đăng ký.
- Không có vi phạm quy tắc sức chứa trong các test và giám sát cần thiết.
- Khả năng phục hồi/không phát thông điệp xác nhận giả khi lỗi mạng.

Một Product Goal tốt tạo cơ sở **chọn và bỏ** tính năng. Email đẹp hoặc biểu đồ quản trị chỉ có giá trị tương đối khi xét mục tiêu này.

## 4. Khám phá nhu cầu trước khi viết backlog

### 4.1. Thu tín hiệu từ nhiều nguồn

Nhóm giả định thực hiện:
1. Phỏng vấn một số học viên vừa gửi đăng ký.
2. Quan sát nhân viên Support trả lời câu hỏi phổ biến.
3. Cùng người tổ chức vẽ quy trình xác nhận và sức chứa.
4. Đọc một mẫu dữ liệu sự cố và sai lệch bảng tính.
5. Phân tích sự khác nhau giữa đăng ký “đã gửi” và “đã được chấp nhận”.
6. Xác định điều kiện dữ liệu cá nhân cần bảo vệ.
7. Liệt kê các câu chưa biết có thể ảnh hưởng thứ tự công việc.

Các cuộc phỏng vấn nhỏ **không tạo chân lý đại diện cho mọi người dùng**. Chúng giúp nhận diện câu hỏi cần kiểm bằng các nguồn khác.

### 4.2. Tách nhu cầu khỏi giải pháp đề xuất

| Phát biểu nghe được | Nhu cầu có thể ở phía sau | Câu hỏi kiểm chứng |
| --- | --- | --- |
| “Hãy gửi SMS ngay.” | Muốn biết trạng thái kịp thời | Người dùng cần biết lúc nào, kênh nào thực sự hữu ích? |
| “Làm dashboard trước.” | Người tổ chức muốn quyết định nhanh | Thông tin nào thiếu, hiện mất bao lâu tìm? |
| “Nút Xác nhận phải xanh.” | Muốn tránh nhập nhằng kết quả | Học viên hiểu ý nghĩa trạng thái không? |
| “Cho phép đăng ký dù hết chỗ.” | Không muốn mất người quan tâm | Có quy trình waitlist và kỳ vọng rõ không? |
| “Xuất Excel là đủ.” | Cần báo cáo và đối chiếu | Ai dùng, dữ liệu nào, có chứa thông tin nhạy cảm không? |

**Không copy câu “Hãy gửi SMS” thành user story ngay** nếu chưa biết lợi ích và trạng thái nghiệp vụ. Giải pháp có thể là trang trạng thái, email có điều kiện, hoặc thông báo khi CONFIRMED – tất cả đều cần so rủi ro, chi phí và giá trị.

### 4.3. Bản đồ hành trình người dùng

~~~text
Xem workshop -> Chọn phiên -> Gửi yêu cầu
    -> Nhận mã tra cứu an toàn -> Xem PENDING
    -> Chờ người tổ chức xử lý
    -> Xem CONFIRMED hoặc trạng thái khác
    -> Tham dự / hủy theo chính sách
~~~

Với mỗi bước, gắn:
- **Mục tiêu người dùng.**
- **Rủi ro nếu hiểu sai.**
- **Nguồn dữ liệu có thẩm quyền.**
- **Khả năng kiểm thử/giao lát cắt nhỏ.**
- **Giả định cần đo.**

### 4.4. Example mapping cho một điểm quan trọng

**Câu hỏi nghiệp vụ:** “Đăng ký PENDING đã giữ chỗ chưa?”

| Thành phần | Nội dung |
| --- | --- |
| **Rule** | PENDING chỉ xác nhận đã nhận yêu cầu, chưa giữ chỗ |
| **Ví dụ bình thường** | Người học gửi form, nhận mã, trang hiển thị PENDING |
| **Ví dụ đối lập** | Hai học viên đăng ký suất cuối; chỉ người được CONFIRMED theo giao dịch hợp lệ mới chiếm suất |
| **Trường hợp lỗi** | API timeout; giao diện không hiển thị CONFIRMED từ suy đoán |
| **Câu hỏi chưa rõ** | Khi hết chỗ thì CANCELLED, REJECTED hay WAITLISTED? Có cần kênh thông báo? |
| **Đầu ra** | Acceptance criteria/test và PBI cần làm rõ |

Khi câu hỏi chưa được giải, ghi là **open question với owner**; không tạo AC chắc chắn dựa trên giả định chưa được thống nhất.

## 5. Viết user stories có giá trị và có thể kiểm chứng

### 5.1. Mẫu user story

> Là **[đối tượng]**, tôi muốn **[khả năng hoặc nhu cầu]**, để **[lợi ích/kết quả]**.

Đây là **một công cụ diễn đạt**, không phải định dạng bắt buộc của Scrum hay thay thế hội thoại và test. Một PBI có thể là lỗi, thử nghiệm, nợ kỹ thuật hoặc công việc rủi ro nếu phục vụ Product Goal.

### 5.2. Bốn user stories ban đầu

**US-01 – Gửi yêu cầu đăng ký**

> Là học viên, tôi muốn gửi yêu cầu đăng ký workshop và nhận mã tra cứu, để biết yêu cầu đã đến hệ thống và có thể xem tiến triển mà không gửi lặp.

**US-02 – Xác nhận chỗ đúng sức chứa**

> Là người tổ chức, tôi muốn xác nhận đăng ký theo số chỗ còn lại, để không giữ vượt sức chứa khi có các yêu cầu đồng thời.

**US-03 – Xem trạng thái đáng tin**

> Là học viên, tôi muốn xem yêu cầu đang PENDING hay đã CONFIRMED, để quyết định có thể tham dự và không hiểu nhầm chỗ đã được giữ.

**US-04 – Nhận thông báo xác nhận**

> Là học viên đã được xác nhận, tôi muốn nhận thông báo kết quả trên kênh thích hợp, để không cần liên tục kiểm tra trang trạng thái.

### 5.3. Stories chưa đủ tốt thường có triệu chứng nào?

| Story chưa tốt | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| “Làm database đăng ký” | Là task kỹ thuật, không nói giá trị trực tiếp | Gắn với quy tắc xác nhận chỗ và test nghiệp vụ |
| “Là admin tôi muốn dashboard thật đẹp” | Kết quả mơ hồ, AC không rõ | Hỏi quyết định cần hỗ trợ, thông tin nào bắt buộc |
| “Là học viên tôi muốn mọi tính năng” | Quá lớn, không hoàn tất tăng dần | Chia theo hành trình và rủi ro |
| “Gửi SMS mỗi lần PENDING” | Chọn giải pháp trước khi hiểu nhu cầu | Kiểm nhu cầu về thời điểm và ý nghĩa trạng thái |
| “Hiển thị trạng thái đúng” | Chưa rõ đúng nghĩa gì | Đặt rule PENDING/CONFIRMED, timeout, quyền |
| “Đã merge API là Done” | Phần kỹ thuật chưa phải Increment | Đo theo DoD và hành vi người dùng |

### 5.4. Kiểm tra INVEST một cách thực dụng

INVEST thường gợi ý story nên **Independent, Negotiable, Valuable, Estimable, Small, Testable**. Đây là heuristic, không phải điều kiện cưỡng ép mọi PBI độc lập tuyệt đối. Ví dụ US-03 vẫn phụ thuộc nguồn dữ liệu trạng thái; mục tiêu là **làm rõ và giảm sự phụ thuộc gây chờ**, không giả định mỗi story sống tách hệ thống.

Khi chưa ước lượng được vì vấn đề quá mơ hồ, giải pháp tốt có thể là **một hoạt động khám phá có timebox** và đầu ra cần quyết, không tùy tiện gán point cao để che rủi ro.

## 6. Acceptance criteria, Definition of Done và bằng chứng sản phẩm

### 6.1. Acceptance criteria của US-03

1. Nếu trạng thái nghiệp vụ là PENDING, giao diện hiển thị PENDING theo nội dung nhất quán; ở bản đầu có thể hiển thị “Đang chờ xác nhận”.
2. Nếu CONFIRMED có thẩm quyền, giao diện hiển thị “Đã xác nhận” và thông tin phù hợp.
3. Nếu API timeout hoặc lỗi, giao diện **không tự suy đoán** trạng thái mới là CONFIRMED.
4. Học viên không xem được dữ liệu đăng ký của người khác.
5. Các thông điệp không tiết lộ thông tin nhạy cảm.
6. Test trạng thái, xử lý lỗi, quyền truy cập và tích hợp phù hợp phải đạt.

Các AC ban đầu bảo vệ nghiệp vụ cơ bản nhưng **chưa kiểm trực tiếp mức hiểu của người học**. Khoảng trống này sẽ được phát hiện sau feedback và dẫn tới điều chỉnh backlog.

### 6.2. Ví dụ kịch bản kiểm chứng

~~~gherkin
Tính năng: Học viên xem trạng thái đăng ký

  Tình huống: Đăng ký đang PENDING
    Cho trước một đăng ký thuộc học viên hiện tại có trạng thái PENDING
    Khi học viên mở trang trạng thái
    Thì trang hiển thị "Đang chờ xác nhận"
    Và không hiển thị nhãn "Đã xác nhận"

  Tình huống: Đăng ký đã được xác nhận
    Cho trước một đăng ký thuộc học viên hiện tại có trạng thái CONFIRMED
    Khi học viên mở trang trạng thái
    Thì trang hiển thị "Đã xác nhận"

  Tình huống: API trả lỗi tạm thời
    Cho trước yêu cầu lấy trạng thái mới gặp lỗi
    Khi giao diện cập nhật
    Thì giao diện thông báo chưa thể xác minh trạng thái mới
    Và không tự xác nhận chỗ cho học viên

  Tình huống: Không có quyền truy cập
    Cho trước học viên B không sở hữu đăng ký của học viên A
    Khi B yêu cầu xem trạng thái của A
    Thì hệ thống không tiết lộ dữ liệu đăng ký của A
~~~

Đây là **đặc tả minh họa**, chưa chứng minh hệ thống được triển khai an toàn. Test đồng thời, transaction, tích hợp, môi trường và chính sách dữ liệu vẫn cần được thiết kế.

### 6.3. Acceptance criteria khác Definition of Done

- **Acceptance criteria:** điều kiện chấp nhận cụ thể của một PBI/user story.
- **Definition of Done:** cam kết chất lượng chung để Increment được coi là Done, thường gồm tích hợp, kiểm thử thích hợp, review, an toàn và các yêu cầu khác của sản phẩm/tổ chức.

Một PBI đáp ứng AC về câu chữ nhưng còn lỗi quyền dữ liệu **chưa đạt Done**. Một PBI đã merge và có unit tests cũng **chưa tự đạt Done** nếu Definition of Done yêu cầu integration kiểm chứng.

### 6.4. Bằng chứng outcome còn khác cả hai

AC và DoD trả lời “đã xây đúng điều đã thỏa thuận chưa?”. Outcome trả lời “**người dùng có nhận được giá trị như kỳ vọng không?**”.

Ví dụ AC ban đầu của trạng thái có thể đúng trong test, nhưng học viên vẫn nghĩ PENDING là đã giữ chỗ. Đó là **bằng chứng cần cập nhật hiểu biết về sản phẩm**, không phải lý do đổ lỗi cho người đã triển khai AC.

## 7. Chia nhỏ backlog để giao và học sớm

### 7.1. Tránh chỉ chia theo tầng kỹ thuật

Cách chia có rủi ro:
- Ticket A: tạo database.
- Ticket B: tạo REST API.
- Ticket C: tạo màn hình.
- Ticket D: viết test.
- Ticket E: tích hợp.

Nếu mỗi ticket “Done” riêng mà người dùng chưa làm được gì, **feedback sản phẩm đến muộn**.

Cách chia theo lát cắt:
1. Gửi yêu cầu đăng ký và nhận mã tra cứu an toàn, trạng thái PENDING rõ theo định nghĩa.
2. Người tổ chức xác nhận chỗ theo quy tắc sức chứa, có kiểm thử đồng thời.
3. Học viên xem trạng thái từ nguồn đúng với quyền truy cập được bảo vệ.
4. Làm rõ thông điệp khi chờ/timeout theo kết quả dùng thử.
5. Thông báo CONFIRMED theo kênh phù hợp sau khi học được nhu cầu.

Một vertical slice có thể vẫn cần code ở nhiều tầng; khác biệt là **đầu ra có thể kiểm tra end-to-end**.

### 7.2. Giao tăng dần không có nghĩa phát hành sai nghiệp vụ

Có thể dùng:
- Môi trường demo với dữ liệu giả.
- Feature flags/limited cohort có kiểm soát.
- Mock API rõ tính chất để lấy phản hồi giao diện, nhưng không dùng kết quả mock làm bằng chứng nghiệp vụ production đã đúng.
- Chế độ thử nội bộ trước khi chấp nhận đăng ký thật.
- Bản release chỉ cho workshop giới hạn khi rủi ro đã được bảo vệ.

**Không giao một luồng nhận đăng ký thật khi transaction sức chứa chưa an toàn**. Nếu chưa đủ guardrails, Increment có thể được kiểm nghiệm nội bộ thay vì công khai rộng.

### 7.3. Dependency cần rõ nhưng không biến thành lời bào chữa

US-03 cần nguồn trạng thái hợp lệ. Nhóm có thể:
- Thống nhất API contract sớm.
- Dùng contract tests.
- Pairing giữa người làm UI/API.
- Tích hợp thường xuyên bằng CI.
- Ghi blocker thay vì khởi động nhiều PBI khác.
- Chọn một Sprint Goal tương ứng với lát cắt hoàn chỉnh.

Điều chỉnh backlog phải tính **khả năng hoàn tất** và risk; một item có giá trị cao nhưng hoàn toàn chưa rõ có thể cần một thí nghiệm khám phá trước.

## 8. Tạo Product Backlog V0: bảng có thứ tự, không phải danh sách tùy ý

### 8.1. Những trường tối thiểu đủ để quyết định

Một PBI có thể ghi:
- **ID** và tên ngắn.
- **Ai/giá trị hoặc rủi ro cần giải**.
- **Kết quả/AC và liên kết Product Goal**.
- **Trạng thái**: chưa bắt đầu, đang làm, Done; phân biệt khỏi thứ tự.
- **Mức độ hiểu rõ/phụ thuộc chính**.
- **Kích thước hoặc nỗ lực tương đối** (nếu cần để forecast).
- **Thứ tự trong Product Backlog** và **rationale**.
- **Nguồn bằng chứng, ngày xem lại** khi cần.

Scrum Guide không yêu cầu mọi Product Backlog phải có đúng các cột này; các trường là **mẫu thực hành để tăng minh bạch**.

### 8.2. Product Backlog V0 (trước feedback)

Product Goal: học viên gửi đăng ký, hiểu trạng thái và không xác nhận vượt chỗ.

| Thứ tự V0 | ID | PBI / mục tiêu | Giá trị hoặc rủi ro | Phụ thuộc chính | Trạng thái ban đầu |
| ---: | --- | --- | --- | --- | --- |
| **1** | PB-01 | Gửi yêu cầu, nhận mã tra cứu, lưu PENDING | Có đầu vào cho hành trình | Quyền, định danh request | Ready |
| **2** | PB-02 | Xác nhận chỗ với kiểm tra sức chứa nhất quán | Tránh giữ vượt chỗ | Transaction và rule nghiệp vụ | Ready |
| **3** | PB-03 | Trang xem PENDING/CONFIRMED theo quyền | Học viên biết kết quả từ nguồn đúng | PB-01, PB-02, status API | Ready |
| **4** | PB-04 | Email sau khi CONFIRMED | Giảm nhu cầu phải kiểm thủ công | PB-02, notification service | Refinement |
| **5** | PB-05 | Trang nhà tổ chức xem danh sách và sức chứa | Hỗ trợ quản lý phiên | Quyền admin, dữ liệu đăng ký | Refinement |
| **6** | PB-06 | Lọc và tìm workshop | Giúp chọn phiên phù hợp | Dữ liệu workshop | Candidate |
| **7** | PB-07 | Học viên gửi yêu cầu hủy đăng ký | Hỗ trợ thay đổi kế hoạch | PB-01/02, rule giải phóng chỗ | Candidate |
| **8** | PB-08 | Xuất danh sách đăng ký | Hỗ trợ báo cáo có kiểm soát | PB-05, quyền dữ liệu | Candidate |
| **9** | PB-09 | Theo dõi lỗi trạng thái và thời gian phản hồi | Độ tin cậy, có bằng chứng lỗi | Logging/observability | Candidate |
| **10** | PB-10 | Xử lý lỗi tải trạng thái và timeout đầy đủ | Tránh thông báo sai khi lỗi | PB-03, test lỗi mạng | Candidate |

**V0 là bản đồ thứ tự giả định, không phải thứ tự tối ưu đã được chứng minh.** Lý do đặt PB-04 khá cao ban đầu là một giả định rằng email sẽ giảm Support; sau feedback giả định đó có thể không còn là ưu tiên tốt nhất.

### 8.3. Phân biệt trạng thái với thứ tự

- **Thứ tự 1** không có nghĩa PBI đã bắt đầu.
- **Ready** không có nghĩa Product Owner đã cam kết ngày phát hành.
- **Candidate** không có nghĩa kém quan trọng mãi mãi.
- **Done** là kết quả đáp ứng DoD, không bị “xếp lại” như việc chưa làm.
- Có thể giữ lịch sử PBI Done trong công cụ, còn **active backlog** chỉ hiển thị việc còn có thể lựa chọn.
- Một PBI có thể **được chia, gộp, bỏ hoặc viết lại** khi học được điều mới.

### 8.4. Vì sao đây là Product Backlog chứ không phải Sprint Backlog?

Trong Scrum:
- **Product Backlog** là danh sách có thứ tự nổi lên từ những điều cần làm để cải thiện sản phẩm; Product Owner chịu trách nhiệm hiệu quả quản lý và thứ tự.
- **Sprint Backlog** gồm Sprint Goal, những PBI được chọn và kế hoạch của Developers để giao Increment trong Sprint.
- Thay đổi thứ tự **Product Backlog** không cho phép một người ngoài nhóm tự động xóa/chèn task trong **Sprint Backlog** mà không xét Sprint Goal, trách nhiệm và thương lượng phạm vi.

Điểm này đặc biệt quan trọng khi một feedback cấp thiết đến **giữa Sprint**.

## 9. Sắp thứ tự V0 bằng giá trị, rủi ro, phụ thuộc và khả năng học

### 9.1. Không có một công thức chấm điểm bắt buộc

Các yếu tố cần xét:
1. **Liên kết Product Goal:** giúp mục tiêu ra sao?
2. **Giá trị cho người dùng:** tác vụ hoặc vấn đề thật nào được giải?
3. **Mức nguy hại/rủi ro:** sai dữ liệu, bảo mật, nghĩa vụ bắt buộc?
4. **Độ khẩn/cost of delay:** bỏ lỡ thời điểm nào khi chậm?
5. **Cơ hội học:** PBI nào kiểm giả định ảnh hưởng lớn?
6. **Kích thước/công sức:** có thể giao lát cắt nhỏ hơn không?
7. **Phụ thuộc:** điều gì phải có trước và làm thế nào giảm chờ?
8. **Độ tin cậy của bằng chứng:** quan sát thật hay yêu cầu của một người?
9. **Chi phí dài hạn:** vận hành, CI, dữ liệu, quản lý thay đổi.
10. **Guardrails:** có yêu cầu không được đánh đổi bằng điểm số?

### 9.2. Ví dụ chấm điểm chỉ để trao đổi

Giả sử nhóm tạm dùng thang 1–5 để **so mức giá trị theo Product Goal, độ khẩn và giảm rủi ro**, và dùng t-shirt size S/M/L để gợi ý độ lớn. Đây là thang **cục bộ minh họa**, không phải dự báo định lượng.

| ID | Giá trị 1–5 | Khẩn 1–5 | Giảm rủi ro 1–5 | Size | Nhận định |
| --- | ---: | ---: | ---: | --- | --- |
| PB-01 | 5 | 5 | 3 | M | Cần có để học viên gửi yêu cầu |
| PB-02 | 5 | 5 | 5 | M/L | Guardrail sức chứa, không được bỏ |
| PB-03 | 5 | 4 | 4 | M | Tạo trạng thái tự phục vụ |
| PB-04 | 4 | 3 | 1 | M | Giả định email giảm câu hỏi, chưa kiểm |
| PB-05 | 3 | 2 | 2 | L | Quản trị cần rõ tác vụ trước |
| PB-09 | 2 | 2 | 4 | S/M | Có thể tăng khi phát hiện lỗi thực |
| PB-10 | 3 | 2 | 4 | S | Rủi ro timeout chưa được kiểm đủ |

**Không cộng bừa các số để ra “điểm ưu tiên tuyệt đối”**. Ví dụ PB-02 phải đáp ứng bất biến an toàn, không thể bị đẩy xuống chỉ vì size lớn. Nếu dùng một công thức tỷ số (ví dụ weighted score/size), phải nêu rõ cách chuẩn hóa, độ bất định và trường hợp bắt buộc vượt xếp hạng.

### 9.3. Phân biệt rủi ro và giá trị

Một PBI kỹ thuật như “test xử lý đồng thời suất cuối” có thể không trực tiếp tạo màn hình mới nhưng **bảo vệ giá trị và quyền lợi người dùng**. Hãy liên kết nó tới risk, DoD và Product Goal, không gán “giá trị bằng 0” chỉ vì người dùng không nhìn thấy một nút mới.

### 9.4. Lý do thứ tự V0 phải truy vết được

| Quyết định V0 | Lý do | Giả định cần kiểm |
| --- | --- | --- |
| PB-01/02/03 lên đầu | Tạo hành trình đăng ký và trạng thái đáng tin | Người dùng hiểu trạng thái nếu có trang tự xem |
| PB-04 thứ 4 | Stakeholder tin email sẽ giảm câu hỏi | Học viên thực cần email hay lời giải thích ngay tại trang? |
| PB-05 thứ 5 | Người tổ chức muốn thấy dữ liệu | Dashboard có giảm lỗi/quá tải đáng kể hơn cải tiến UI? |
| PB-09/10 phía dưới | Chưa có dữ kiện đủ về tần suất lỗi | Hệ thống có vấn đề khi mất mạng/timeouts không? |

Thứ tự tốt ban đầu là **phán đoán minh bạch có khả năng đổi**, không phải lời khẳng định “chúng ta đã dự báo tương lai đúng”.

## 10. Thiết kế một Increment nhỏ và kế hoạch lấy phản hồi

### 10.1. Increment đầu tiên nên kiểm gì?

Trong một Sprint hoặc chu kỳ delivery giả định, nhóm chọn lát cắt đầu tiên từ PB-01, PB-02, PB-03 trong phạm vi **có khả năng hoàn tất**, thay vì nhận cả 10 PBI để giữ người bận.

**Sprint Goal mẫu:**

> “Học viên có thể gửi yêu cầu đăng ký và xem trạng thái đúng từ nguồn đáng tin, còn người tổ chức có thể xác nhận chỗ mà không vượt sức chứa trong phạm vi thử nghiệm.”

Developers cùng Product Owner làm rõ scope; Developers lập kế hoạch. Nếu các PBI quá lớn hoặc rủi ro cao, nhóm nên giảm phạm vi hoặc kéo dài quan sát thích hợp, **không hạ DoD**.

### 10.2. Công việc kỹ thuật giúp Increment Done

- Thiết kế transaction xác nhận chỗ nhất quán.
- Test các trạng thái PENDING/CONFIRMED.
- Test hai request tranh suất cuối.
- Xác thực và phân quyền đọc đăng ký.
- Handling timeout không tự khẳng định có chỗ.
- CI tự động chạy test phù hợp.
- Logging không lưu dữ liệu nhạy cảm không cần thiết.
- Khả năng rollback hoặc tắt tính năng theo rủi ro.
- Giao diện hiển thị rõ ràng trong phạm vi AC V0.

### 10.3. Chuẩn bị feedback trước khi giao

Trước khi triển khai cho cohort nhỏ, nhóm ghi:

| Câu hỏi muốn học | Phương pháp | Thước đo hoặc bằng chứng | Guardrail |
| --- | --- | --- | --- |
| Học viên có hiểu PENDING chưa giữ chỗ? | Quan sát 30 người giả định làm tác vụ, hỏi lại ý nghĩa | Tỷ lệ hiểu đúng theo kịch bản | Không hiển thị xác nhận sai |
| Học viên cần email hay chỉ cần trang trạng thái? | Phỏng vấn và quan sát lựa chọn kênh | Nhu cầu theo tình huống, không chỉ bình chọn | Quyền riêng tư, chống spam |
| Có sai chỗ khi xác nhận đồng thời? | Test concurrency + telemetry phù hợp | Không vi phạm bất biến trong test/giám sát | Dừng rollout nếu có dấu hiệu vượt sức chứa |
| Trạng thái có vấn đề khi timeout? | Thử mạng lỗi trên môi trường an toàn | UI không suy đoán CONFIRMED | Không thông báo sai |
| Các PBI có bị nghẽn ở đâu? | Work item age, cycle time, blocked reasons | Queue và thời gian chờ | Không chạy KPI bằng bỏ test |

Không thu số điện thoại thật nếu chỉ cần kiểm cách hiểu trạng thái. Nếu thử với người dùng thật, tuân thủ chính sách đồng ý, bảo vệ dữ liệu và giới hạn rollout phù hợp.

### 10.4. Thực hành kỹ thuật XP để phản hồi sớm

- **Test-driven development (TDD):** viết test về các quy tắc quan trọng khi phù hợp.
- **Pair programming:** phối hợp ở giao dịch xác nhận chỗ/contract khó.
- **Continuous integration:** tích hợp nhỏ thường xuyên, tránh cuối Sprint mới ghép.
- **Refactoring:** giữ mã dễ sửa khi feedback đổi yêu cầu.
- **Small releases:** rút ngắn thời gian tới bằng chứng.
- **Collective ownership phù hợp:** giảm một người duy nhất nắm kiến thức trọng yếu.

Những thực hành này không bảo đảm sản phẩm đúng nhu cầu, nhưng giúp **đổi backlog rồi đổi mã an toàn và nhanh hơn**.

## 11. Kết thúc Increment đầu: đã giao gì, chưa biết gì?

Giả sử PB-01, PB-02, PB-03 **thật sự đạt DoD** và được thử trong phạm vi an toàn. Chúng được lưu thành các PBI **Done**, không còn nằm trong danh sách active backlog cần ưu tiên tiếp.

Nhóm đã có:
- Một yêu cầu đăng ký được lưu ở PENDING, không khẳng định giữ chỗ.
- Xác nhận chỗ theo điều kiện sức chứa được kiểm.
- Trang trạng thái dựa trên API có quyền truy cập đúng.
- CI/test kỹ thuật cho các kịch bản đã mô tả.
- Khả năng quan sát hành vi người dùng trong một luồng nhỏ.

Nhóm **chưa được biết chắc**:
- Người học có thực sự phân biệt PENDING và CONFIRMED?
- Email có phải cách tốt nhất để giảm Support?
- Giao diện giải thích được tình huống timeout chưa?
- Nhu cầu dashboard quản trị có đáng ưu tiên hơn sửa cách hiểu trạng thái?
- Những số liệu từ cohort đầu có đại diện đủ không?

**Done của Increment và đúng của Product Goal là hai phép kiểm khác nhau.** Phần tiếp theo sử dụng phản hồi để thay thứ tự các PBI còn mở, không tô lại lịch sử PBI đã Done.

## 12. Thu phản hồi có thể dẫn tới quyết định

### 12.1. Những kênh phù hợp với Increment đầu

Trong phiên thử mẫu giả định, nhóm dùng:
- **Quan sát tác vụ:** cho học viên gửi đăng ký và nói rõ họ nghĩ đã được giữ chỗ chưa, trước khi người nghiên cứu giải thích.
- **Support feedback:** ghi số câu hỏi liên quan trạng thái so với lượng đăng ký, phân biệt liên hệ lặp.
- **Fault-injection test:** mô phỏng timeout/lỗi mạng để xem UI phản hồi an toàn và có thể thao tác tiếp không.
- **Nhật ký hệ thống:** kiểm trạng thái được xác định từ nguồn có thẩm quyền; không đưa dữ liệu cá nhân không cần thiết vào dashboard.
- **Phỏng vấn người tổ chức:** tìm một quyết định cụ thể mà họ chưa có thông tin để thực hiện.
- **Sprint Review:** cùng stakeholder kiểm Increment thật và xem các quan sát, không chỉ chiếu phần giao diện đẹp.
- **Flow metrics:** xem các PBI hoàn tất tốn bao lâu, review có bị chặn không; không dùng để xếp hạng người.

Mỗi kênh trả lời một câu hỏi khác nhau. Không thay thử nghiệm nghiệp vụ bằng biểu đồ số người mở trang; không thay quan sát hành vi bằng lời khen “demo trông ổn”.

### 12.2. Feedback log F01–F05 (tất cả dữ liệu giả định)

| ID | Nguồn và quan sát | Loại | Tác động có thể có | Mức tin cậy hiện tại |
| --- | --- | --- | --- | --- |
| **F01** | Trong 30 lượt thử, 20 người hiểu đúng PENDING chưa giữ chỗ; 10 người hiểu sai | Outcome/trải nghiệm | Người học dễ có kỳ vọng sai | Mẫu nhỏ; đủ tín hiệu để điều tra |
| **F02** | 100 lượt đăng ký tạo 18 liên hệ Support liên quan câu hỏi trạng thái | Nhu cầu/Support | Tăng công sức hỗ trợ và bối rối | Chưa biết các liên hệ có trùng người |
| **F03** | Trong 20 lần mô phỏng lỗi mạng, 3 lần trang đứng ở spinner lâu, không có hướng dẫn thử lại | Chất lượng/khả dụng | Học viên không biết kết quả mới | Mô phỏng có thể khác production |
| **F04** | Một người tổ chức yêu cầu dashboard nhiều biểu đồ màu | Ý kiến stakeholder | Có thể hỗ trợ quản trị, chưa rõ quyết định nào | Chỉ một quan điểm, thiếu tác vụ |
| **F05** | Một số học viên nói muốn email hoặc SMS ngay sau gửi yêu cầu | Nhu cầu và đề xuất giải pháp | Cần giảm bất định trạng thái | Chưa rõ muốn receipt, PENDING hay CONFIRMED |

**Phân biệt số liệu:** F02 là **18 lượt liên hệ/100 lượt đăng ký**, không được trình bày thành “18% học viên phàn nàn” nếu một người có thể gửi nhiều câu hỏi. F03 xảy ra trong **fault-injection test**, chưa khẳng định lỗi production phổ biến.

### 12.3. Tách quan sát khỏi giải pháp

Với F01:
- **Quan sát:** 10/30 người trả lời sai câu hỏi liệu PENDING có giữ chỗ.
- **Giả thuyết A:** nhãn “Đang chờ xác nhận” không đủ cụ thể.
- **Giả thuyết B:** màn hình trước đã dùng chữ “Đăng ký thành công” gây hiểu sai.
- **Giả thuyết C:** học viên không đọc đoạn giải thích vì vị trí hiển thị.
- **Giải pháp đề xuất:** thêm “Chưa được giữ chỗ”, đổi nhãn nút, đặt trạng thái và next steps rõ hơn.
- **Việc cần làm:** kiểm cách hiểu và điểm gây hiểu nhầm trước khi chọn một phương án lớn.

Với F05, giải pháp “SMS ngay” có thể gây sai kỳ vọng nếu gửi văn bản xác nhận trước khi nghiệp vụ CONFIRMED. Trước hết cần phân biệt **thông báo đã nhận yêu cầu (PENDING)** với **thông báo đã được giữ chỗ (CONFIRMED)**.

### 12.4. Phát hiện rủi ro nghiêm trọng phải có đường xử lý riêng

Giả sử thay vì spinner, nhóm phát hiện UI đang hiển thị “Đã xác nhận” khi API timeout dù nguồn dữ liệu chưa CONFIRMED. Đây là một **nguy cơ nghiệp vụ nghiêm trọng**; nếu xảy ra với người dùng thật, phải kích hoạt phân loại sự cố, mitigation và xác minh theo chính sách. Không nên đợi đủ một buổi refinement hoặc chấm điểm ưu tiên để hành động.

Bài thực hành chính dùng **F03 là vấn đề spinner và thiếu hướng dẫn**, trong khi ví dụ “xác nhận giả” được tách như **tình huống giả định cần escalation**. Không trộn chúng để thổi phồng dữ liệu.

## 13. Tính và diễn giải tín hiệu ban đầu đúng cách

### 13.1. Tỷ lệ hiểu đúng PENDING

~~~text
Số người hiểu đúng: 20
Số người được thử: 30

Tỷ lệ hiểu đúng = 20 / 30 × 100% ≈ 66,7%
Tỷ lệ hiểu sai = 10 / 30 × 100% ≈ 33,3%
~~~

Trong mẫu nhỏ này, khoảng một phần ba hiểu sai. Đó là **tín hiệu liên quan trực tiếp Product Goal**, đủ để nâng mức chú ý và kiểm chứng thêm, nhưng **không tự chứng minh** tỷ lệ hiểu sai của toàn bộ học viên cũng là 33,3%.

### 13.2. Tần suất câu hỏi Support

~~~text
Lượt liên hệ về trạng thái: 18
Lượt đăng ký trong kỳ: 100

Tỷ số = 18 / 100 = 0,18 lượt liên hệ / lượt đăng ký
      = 18 lượt liên hệ / 100 lượt đăng ký
~~~

Đây là **tỷ số lượt liên hệ trên lượt đăng ký**, không phải xác suất một học viên gặp vấn đề. Nếu 5 người mỗi người liên hệ nhiều lần, số 18 có ý nghĩa khác với 18 người liên hệ một lần.

### 13.3. Kết quả mô phỏng lỗi mạng

~~~text
3 / 20 lần mô phỏng có spinner quá lâu = 15% trong mẫu mô phỏng
~~~

Kết quả này giúp nhóm xem lại xử lý trạng thái lỗi và thông điệp thử lại. Không dùng 15% như tỷ lệ lỗi thực của production; phương pháp fault-injection có chủ đích làm xuất hiện lỗi mạng.

### 13.4. Một phép tính không thể thay thế quyết định

Nếu chỉ lấy số người bầu chọn tính năng, email hoặc dashboard có thể nhận nhiều phiếu hơn. Nhưng F01 nói trực tiếp về **khả năng hiểu trạng thái**, còn PB-02 liên quan **bất biến sức chứa**. Quyết định tốt phải xét **mục tiêu, độ rủi ro, độ tin cậy và cơ hội học**, không chỉ đếm số phiếu.

## 14. Triage feedback: bước trung gian trước khi sửa backlog

### 14.1. Một luồng triage minh bạch

~~~mermaid
flowchart TD
    A[Feedback F01-F05] --> B[Phân loại: incident, bug, outcome, nhu cầu, đề xuất]
    B --> C{Có gây hại nghiêm trọng đang diễn ra?}
    C -->|Có| D[Incident/mitigation theo policy]
    C -->|Không| E[Đối chiếu Product Goal và bằng chứng]
    E --> F{Cần quyết định nào?}
    F -->|Thử nhỏ| G[Tạo experiment PBI với giả thuyết]
    F -->|Điều chỉnh sản phẩm| H[Thêm/chỉnh/tách PBI và AC]
    F -->|Làm rõ chất lượng| I[Nâng/thay PBI technical và test]
    F -->|Chưa phù hợp| J[Giữ nguồn, ghi lý do/tín hiệu kiểm lại]
    D --> K[Backlog/incident record minh bạch]
    G --> K
    H --> K
    I --> K
    J --> K
    K --> L[Product Owner cân nhắc thứ tự việc còn mở]
~~~

**Triage không tự động đưa tất cả ý kiến vào Top 1.** Một feedback có thể được:
- Chuyển thành bug cần xử lý.
- Chuyển thành PBI cải tiến.
- Dùng để làm rõ acceptance criteria PBI đã có.
- Tách thành experiment nhỏ nếu thiếu bằng chứng.
- Gộp với yêu cầu trùng.
- Để lại với lý do và mốc xem lại.
- Chuyển sang chính sách incident nếu đang gây hại.

### 14.2. Quyết định triage cụ thể

| Feedback | Quyết định được đề xuất | Tác động lên backlog | Người chịu trách nhiệm |
| --- | --- | --- | --- |
| **F01** hiểu sai PENDING | Kiểm và sửa cách diễn đạt cho rõ “chưa giữ chỗ” | **Tạo PB-11** có test/experiment | Product Owner quyết thứ tự; Developers triển khai |
| **F02** câu hỏi Support cao | Kết hợp F01, tìm nguyên nhân trong hành trình | Tăng lý do ưu tiên PB-11; không tạo PBI trùng | Product Owner + Support + Developers |
| **F03** spinner khi lỗi mạng | Làm rõ cách thoát lỗi, retry và trạng thái cũ | **Nâng PB-10** và bổ sung AC | Developers đề xuất kỹ thuật; PO cân nhắc backlog |
| **F04** yêu cầu dashboard màu | Hỏi tác vụ và quyết định cần hỗ trợ | **PB-05 chưa được nâng**, cần discovery | Product Owner với người tổ chức |
| **F05** muốn email/SMS | Kiểm nhu cầu kênh và thời điểm thông báo | **Tạo PB-12** discovery; chưa xây SMS ngay | Product Owner với người dùng/Developers |

### 14.3. Tại sao không tạo năm ticket tương ứng năm feedback?

F01 và F02 có thể chung nguyên nhân; tách thành hai task giống nhau làm backlog phình to mà không tăng giá trị. F04 chỉ là một ý kiến về giải pháp; chưa đủ để chiếm capacity lớn. F05 cần phân biệt thông báo receipt với xác nhận. **Backlog mô tả những lựa chọn cải thiện sản phẩm**, không phải kho sao chép từng tin nhắn.

### 14.4. Ai có quyền chốt?

Trong Scrum, **Product Owner chịu trách nhiệm về việc quản lý hiệu quả Product Backlog, gồm thứ tự và tính minh bạch**. Họ có thể ủy quyền hoạt động refinement hay thu dữ liệu nhưng vẫn chịu trách nhiệm cuối. Developers cung cấp ước lượng, phân tích phụ thuộc và rủi ro kỹ thuật, giữ DoD; stakeholder cung cấp nhu cầu và ràng buộc. **Không yêu cầu Product Owner tự giải quyết các chi tiết kỹ thuật không thuộc chuyên môn** và không để ai tự tạo “Top Priority” song song mà nhóm không biết.

## 15. Làm rõ các PBI mới và PBI được điều chỉnh

### 15.1. PB-11 – giải thích PENDING để tránh hiểu nhầm

**User story PB-11:**

> Là học viên đã gửi yêu cầu đăng ký, tôi muốn biết rõ rằng trạng thái PENDING **chưa có nghĩa được giữ chỗ** và việc gì sẽ xảy ra tiếp theo, để không sắp lịch dựa trên một xác nhận chưa có.

**Acceptance criteria V1 đề xuất:**
1. Với PENDING, giao diện hiển thị ngôn ngữ tương đương **“Đang chờ xác nhận – chưa được giữ chỗ”**.
2. Với CONFIRMED, chỉ hiển thị xác nhận khi dữ liệu nghiệp vụ có thẩm quyền cho biết chỗ đã được giữ hợp lệ.
3. Nội dung phân biệt **“Đã nhận yêu cầu”** với **“Đã xác nhận chỗ”**, kể cả ở bước gửi form thành công.
4. Thông báo có khả năng truy cập phù hợp, không chỉ phân biệt bằng màu.
5. Trong một buổi thử có kịch bản nhất quán, đo tỷ lệ người dùng trả lời đúng “Tôi đã có chỗ chưa?”.
6. Không làm suy giảm test quyền truy cập, tính nhất quán dữ liệu, timeout và DoD.

Nếu chưa rõ lời giải thích nào tốt nhất, PB-11 có thể được **chia thành một thử nghiệm copy/flow nhỏ** và một PBI triển khai sau khi có bằng chứng.

### 15.2. PB-10 – xử lý lỗi trạng thái/timeout

PB-10 vốn nằm thứ 10 ở V0, chưa được ưu tiên đủ vì chưa có dữ liệu.

Sau F03, bổ sung AC:
1. Khi lấy trạng thái thất bại, hiển thị **“Chưa thể cập nhật trạng thái – hãy thử lại”** hoặc thông điệp rõ tương đương.
2. Không hiển thị trạng thái mới như thể vừa được xác nhận nếu request lỗi.
3. Nếu hiển thị dữ liệu cache, phải nói rõ **đó là kết quả cũ/chưa được xác minh mới**, phù hợp chính sách nghiệp vụ.
4. Có thao tác thử lại an toàn, không gửi lại yêu cầu đăng ký khi chỉ refresh trạng thái.
5. Có test lỗi mạng, timeout và xử lý retry/idempotency phù hợp.
6. Không log/tiết lộ dữ liệu cá nhân quá cần thiết.

**Lý do nâng thứ tự:** nhóm đã có bằng chứng fault-injection về trải nghiệm lỗi, liên quan trực tiếp mục tiêu trạng thái đáng tin. Nếu phát hiện xác nhận giả thực trên production, phải phân loại incident và can thiệp ngay, không chỉ sửa điểm trong backlog.

### 15.3. PB-09 – quan sát độ tin cậy ở nơi có ý nghĩa

PB-09 được làm rõ:
- Ghi event thao tác lấy trạng thái thành công/thất bại với trường dữ liệu an toàn.
- Phân biệt timeout, lỗi quyền, lỗi server và kết quả nghiệp vụ.
- Có chỉ số với mẫu số (ví dụ request lỗi trên request hợp lệ).
- Thiết lập tín hiệu cảnh báo phù hợp với mức rủi ro.
- Có cách xác minh sau rollout mà không thu dữ liệu cá nhân không cần thiết.

**Không đặt telemetry chỉ để “có thêm dashboard”**. Phải giúp nhóm phát hiện sai trạng thái, đo quality hoặc biết người dùng bị ảnh hưởng bao nhiêu.

### 15.4. PB-12 – tìm kênh thông báo phù hợp trước khi xây SMS

**Experiment PBI:**

> Kiểm nhu cầu thông báo ở các trạng thái PENDING/CONFIRMED, thời điểm cần tin và khả năng tự tra cứu; so lựa chọn trang trạng thái, email hoặc kênh khác dưới ràng buộc chi phí và quyền riêng tư.

**Đầu ra** là bằng chứng và quyết định:
- Câu hỏi nghiên cứu, nhóm người dùng, kịch bản.
- Điều kiện cần gửi email sau CONFIRMED.
- Rủi ro khi gửi receipt PENDING bị hiểu là giữ chỗ.
- Ước chi phí/kênh, khả năng tiếp cận, cách cho phép tắt nếu cần.
- Product Owner quyết giữ, tách hoặc hạ PB-04; không làm một SMS service vội.

### 15.5. Lịch sử PB-01/02/03 không bị xóa

PB-01/02/03 đã đạt DoD trong Increment đầu. Chúng nằm trong **lịch sử Done**. PB-11 và PB-10 là **cải tiến/khắc phục mới dựa trên feedback**, không được giả vờ PB-03 “chưa từng Done” chỉ vì sản phẩm cần học thêm. Nếu phát hiện PB-03 thực tế **không đáp ứng DoD tại thời điểm báo**, cần sửa tình trạng và xử lý chất lượng trung thực – đó là trường hợp khác với cải tiến theo bằng chứng mới.

## 16. Product Backlog V1: bảng thứ tự sau khi kiểm feedback

### 16.1. Active backlog trước và sau

Ngay sau Increment đầu, PB-01/02/03 đã Done. Các thứ tự V0 còn mở là **4 đến 10**. Khi cập nhật V1, Product Owner đưa các PBI mới vào thứ tự theo mục tiêu, rủi ro và mức độ hiểu rõ:

| Thứ tự V1 trong active backlog | ID | Thứ tự V0 ban đầu | Điều thay đổi | Lý do sau feedback |
| ---: | --- | ---: | --- | --- |
| **1** | **PB-11** | Mới | Bổ sung thông điệp PENDING và thử khả năng hiểu | F01 + F02 đánh trực tiếp Product Goal |
| **2** | **PB-10** | 10 | Nâng lên, bổ sung handling lỗi và retry | F03 cho thấy hành vi lỗi khó hiểu |
| **3** | **PB-09** | 9 | Nâng lên, làm rõ telemetry rủi ro | Cần phát hiện và kiểm tác động trạng thái |
| **4** | **PB-12** | Mới | Thử nghiệm nhu cầu kênh thông báo | F05 chưa đủ bằng chứng để xây SMS |
| **5** | **PB-04** | 4 | Hạ sau các cải tiến trạng thái | Email hữu ích nhưng chưa giải nhầm PENDING |
| **6** | **PB-07** | 7 | Giữ tương đối, bổ sung rule hủy | Nhu cầu có thể thực nhưng chưa phải điểm nghẽn đầu |
| **7** | **PB-05** | 5 | Hạ, cần xác định tác vụ dashboard | F04 là mong muốn giải pháp, chưa có bằng chứng mạnh |
| **8** | **PB-06** | 6 | Hạ theo trade-off | Tìm workshop chưa là vấn đề lớn nhất của giai đoạn |
| **9** | **PB-08** | 8 | Hạ và chờ làm rõ quyền dữ liệu | Xuất dữ liệu cần kiểm rủi ro và người dùng thực |

**Đọc bảng cẩn thận:**
- PB-01/02/03 không xuất hiện vì đã **Done**, không phải bị xóa khỏi lịch sử.
- Số 10 ở PB-10 là **thứ tự trong V0 đầy đủ**, số 2 là thứ tự trong **active V1**; không nên trừ các thứ tự này để suy “giá trị tăng tám bậc” theo số học.
- PB-09 có thể được làm **một phần trong chính PB-10 hoặc DoD** nếu đó là điều bắt buộc cho chất lượng; việc để thành PBI riêng chỉ là một mô hình minh họa cần refinement.
- Thứ tự là **lựa chọn có bối cảnh**, không phải lời hứa giao đủ chín item trong chu kỳ tới.

### 16.2. V0 vs V1: những quyết định có thể giải thích

~~~text
V0 sau khi loại PBI Done:
PB-04 -> PB-05 -> PB-06 -> PB-07 -> PB-08 -> PB-09 -> PB-10

V1 active:
PB-11 -> PB-10 -> PB-09 -> PB-12 -> PB-04 -> PB-07 -> PB-05 -> PB-06 -> PB-08
~~~

Đây là **thay đổi có chủ đích**:
- Thêm **PB-11** vì hiểu nhầm trạng thái đã được quan sát.
- Nâng **PB-10** vì xử lý timeout là phần trải nghiệm và độ tin cậy.
- Nâng **PB-09** vì cần phát hiện tác dụng phụ/đo kiểm an toàn.
- Thêm **PB-12** để học trước khi xây thông báo mới.
- Hạ **PB-04** chứ không xóa, vì email sau xác nhận có thể vẫn có giá trị.
- Hạ **PB-05** vì đề xuất biểu đồ chưa gắn tác vụ rõ.
- Trì hoãn lọc, xuất danh sách và hủy khi rủi ro/giá trị hiện tại chưa đủ ưu tiên; **nếu có nghĩa vụ pháp lý hoặc vận hành bắt buộc đối với hủy, thứ tự cần đánh giá lại ngay**.

### 16.3. Không nên “điểm số hóa” một nghĩa vụ bắt buộc

Giả sử PB-08 xuất dữ liệu có rủi ro quyền riêng tư. Một tập con công việc về quyền xóa/truy cập dữ liệu có thể là **nghĩa vụ bắt buộc**, không được hạ vì “không tạo doanh thu”. Khi phân loại, tách:
- Hạng mục **bắt buộc để hoạt động hợp lệ/an toàn**.
- Hạng mục **đầu tư để tăng giá trị người dùng**.
- Hạng mục **thử nghiệm học trước khi mở rộng**.
- Hạng mục **chưa phù hợp cần giữ rationale**.

Điều chỉnh ưu tiên có trách nhiệm **không bỏ tuân thủ, bảo mật, tính đúng hoặc DoD**.

## 17. Một cách so sánh lựa chọn có cân nhắc độ tin cậy

### 17.1. Ma trận thảo luận quyết định V1

| Tiêu chí | PB-11 rõ PENDING | PB-10 lỗi timeout | PB-04 email | PB-05 dashboard |
| --- | --- | --- | --- | --- |
| **Liên kết Product Goal** | Rất trực tiếp | Rất trực tiếp | Có thể hỗ trợ | Phụ thuộc nhu cầu tổ chức |
| **Bằng chứng hiện có** | F01/F02 | F03 mô phỏng | F05 còn mơ hồ | F04 một ý kiến |
| **Rủi ro bỏ qua** | Kỳ vọng sai của học viên | Không biết trạng thái khi lỗi | Ít tiện hơn | Quản trị chưa tối ưu |
| **Có thể thử nhỏ?** | Có, nội dung/trình bày | Có, trạng thái lỗi + retry | Có, khám phá nhu cầu | Có, quan sát tác vụ nhà tổ chức |
| **Phụ thuộc** | UI/API, test hiểu đúng | UI/network và handling lỗi | Notification service, PB-02 | Quyền, dữ liệu, UI |
| **Quyết định** | Làm/kiểm sớm | Làm/kiểm sớm | Chờ PB-12 hoặc discovery | Chưa cấp capacity lớn |

Không có số “100 điểm” thần kỳ. Ma trận làm hiện **lý do và điều chưa biết**, đặc biệt khi stakeholder bất đồng.

### 17.2. Cost of delay là giá trị bị mất, không chỉ số ngày chờ

Với PB-11, chậm thêm có thể kéo dài hiểu nhầm, ảnh hưởng trải nghiệm và Support. Với PB-10, chậm làm tăng rủi ro khi mạng lỗi. Với PB-04, việc chờ có thể ít tác động nếu người dùng vẫn xem trạng thái được. Nhưng **không tự quy mọi ngày chờ thành tiền** khi chưa có dữ liệu về hành vi và giá trị.

### 17.3. Quy tắc quyết định gần với thông tin

- Product Owner chịu trách nhiệm **thứ tự Product Backlog** và minh bạch quyết định.
- Developers cung cấp phân tích phụ thuộc, nỗ lực, khả năng giao, chất lượng.
- Support đem câu hỏi thật thay vì yêu cầu một giải pháp cố định.
- Người tổ chức cho biết quyết định vận hành bị ảnh hưởng.
- Những người chịu trách nhiệm an toàn/dữ liệu xác định ràng buộc bắt buộc.
- Nếu có xung đột vượt quyền nhóm hoặc sản phẩm, dùng đường escalation rõ, tránh “ai cũng được sửa thứ tự backlog”.

### 17.4. Decision log minh họa

~~~text
Decision ID: D-2026-01 (mã giả định)
Product Goal: Đăng ký đúng và trạng thái đáng tin
Evidence: F01 20/30 hiểu đúng; F02 18 lượt hỏi/100 đăng ký;
          F03 3/20 lần fault-injection UI spinner không rõ cách thử lại
Assumptions: Nội dung trang và phản hồi lỗi có thể gây hiểu nhầm
Options:
  A. Tiếp tục PB-04 email và PB-05 dashboard như V0
  B. Ưu tiên PB-11/PB-10, sau đó PB-09; thử PB-12 trước khi xây kênh mới
Decision: Chọn B trong phạm vi và guardrails đã thảo luận
Rationale: Liên kết trực tiếp hơn tới Product Goal và có bằng chứng mới
Trade-off: Email/dashboard được dời; cần thông báo stakeholder
Owner quyết thứ tự: Product Owner
Owner triển khai: Developers theo Sprint/flow plan
Guardrails: Không xác nhận vượt chỗ, không lộ dữ liệu, giữ DoD
Review trigger: Kết quả dùng thử tiếp, lỗi mới, thay đổi nghĩa vụ kinh doanh
Next checkpoint: Sprint Review tiếp theo / flow review theo cadence phù hợp
~~~

Đây là **mẫu ghi quyết định**, không phải bắt buộc mọi PBI phải có một tài liệu dài.

## 18. Nếu phản hồi đến giữa Sprint thì sao?

### 18.1. Product Backlog có thể đổi, nhưng Sprint Goal không phải danh sách tùy ý

Theo Scrum Guide 2020:
- Product Owner tiếp tục quản lý và sắp thứ tự Product Backlog.
- Developers quản lý Sprint Backlog và điều chỉnh kế hoạch mỗi ngày hướng Sprint Goal.
- Khi có điều mới, phạm vi có thể được **làm rõ/thương lượng với Product Owner** khi học thêm, nhưng **không được thay đổi làm nguy hại Sprint Goal**.
- Nếu Sprint Goal trở nên lỗi thời vì hoàn cảnh thay đổi, **Product Owner có quyền hủy Sprint**; đó là trường hợp có điều kiện, không phải phản xạ sau mọi feedback.

Giả sử giữa Sprint nhóm đang làm PB-04 email và PB-05 dashboard, còn F01 đến:
1. Product Owner phân loại F01 và cập nhật thứ tự Product Backlog ngay khi có căn cứ.
2. Developers kiểm phần hiện có, Sprint Goal và khả năng hoàn tất.
3. Nếu một phần PB-11 phù hợp Sprint Goal, nhóm có thể thương lượng phạm vi/cách thực hiện.
4. Nếu không phù hợp và không khẩn, đưa PB-11 lên đầu **cho lựa chọn tiếp theo** mà không âm thầm xóa kế hoạch của Developers.
5. Nếu phát hiện nguy cơ dữ liệu/confirmation giả đang gây hại, kích hoạt incident response theo policy trước, rồi cập nhật Sprint impact minh bạch.

### 18.2. Ví dụ quyết định trong Sprint

**Sprint Goal hiện tại:** “Học viên nhận biết trạng thái đăng ký đáng tin trong phạm vi thử nghiệm.”

- PB-11 rõ PENDING có thể **hỗ trợ Sprint Goal**, nếu phù hợp capacity và thỏa thuận của nhóm.
- PB-05 biểu đồ quản trị có thể **lùi sau** khi chưa bắt đầu để dành năng lực.
- PB-04 email nếu đang làm dở: cần xem effort đã có, khả năng hoàn tất, WIP và tác động bỏ dở; không mặc định “feedback mới thì dừng mọi việc”.
- PB-10 nếu tìm thấy bug nghiệp vụ nghiêm trọng: xử lý theo chính sách rủi ro, không chỉ bàn điểm ưu tiên.

**Sprint Backlog không bị đổi bởi một câu nhắn của stakeholder tới cá nhân Developers.** Việc điều chỉnh phải có bối cảnh, quyền và truyền thông.

### 18.3. Nếu một PBI đang làm dở thì đổi ưu tiên thế nào?

Một PBI đang thực hiện có:
- WIP đang tiêu tốn capacity.
- Context đã hình thành.
- Có thể liên quan test/integration khác.
- Có rủi ro nếu dừng giữa một migration.
- Có giá trị còn lại nếu hoàn tất nhỏ gọn.

Cần quyết:
- Hoàn tất lát cắt nhỏ hiện tại hay dừng an toàn?
- Có thể chia phần chưa làm vào backlog sau?
- Nếu dừng, code/feature flag có ở trạng thái an toàn không?
- Có làm giảm khả năng đạt Sprint Goal không?
- Ai chịu trách nhiệm thông báo ảnh hưởng forecast?

**Reprioritize không có nghĩa tạo thêm WIP vô hạn.**

## 19. Nếu nhóm dùng Kanban thay vì Sprint

### 19.1. Sắp lại hàng Ready và giữ ranh giới workflow

Một Definition of Workflow minh họa:

~~~text
Intake -> Ready -> Doing -> Review -> Verify -> Done
                   ^ STARTED                 ^ FINISHED
~~~

Với một hệ thống pull:
- Product Owner/người có trách nhiệm sản phẩm giữ thứ tự work items còn **chưa Started** theo chính sách.
- Nhóm chỉ kéo item mới khi WIP cho phép.
- Item đã Started không tự biến mất khỏi WIP vì bị hạ ưu tiên.
- Nếu phát hiện rủi ro khẩn, chính sách expedite ghi ai được kích hoạt, item nào tạm ngừng và guardrails.
- Cần nhìn **work item age**, throughput, cycle time distribution và blocked reasons để nhận biết tác động thay đổi.

### 19.2. Ví dụ giới hạn WIP

Giả sử:
- Doing: 3 item.
- Review: 2 item.
- Verify: 1 item.
- Tổng WIP từ Started đến Finished: **6 item**.

Nếu chính sách WIP tối đa là **6**, nhóm không nên kéo PB-11 vào Doing ngay chỉ vì được đặt Top 1 khi sáu item khác đang Started, trừ khi có cơ chế ngoại lệ hợp lý và trade-off rõ. Có thể **hỗ trợ hoàn tất** một item hoặc dừng một item ở trạng thái an toàn theo chính sách. Feedback làm đổi **thứ tự sắp tới**, không tự tạo thêm capacity.

### 19.3. Khác Scrum ở nhịp lựa chọn, giống ở vòng học

- Scrum dùng Sprint Goal và các sự kiện kiểm tra/thích ứng trong Sprint.
- Kanban tập trung trực quan hóa/định nghĩa dòng công việc, quản lý WIP và đo flow liên tục.
- Cả hai đều có thể đưa phản hồi khách hàng vào ưu tiên tiếp theo, bảo vệ chất lượng, và dùng thử nghiệm cải tiến.
- Không cần bắt một nhóm Kanban tạo Sprint giả chỉ để “đủ Agile”; không được gọi một bảng thẻ có cột là Kanban trưởng thành nếu không có chính sách dòng công việc.

## 20. Đo xem việc đổi thứ tự có thật tạo giá trị hay không

### 20.1. Outcome, quality, flow và learning cùng có mặt

| Góc nhìn | Tín hiệu | Câu hỏi cần hỏi |
| --- | --- | --- |
| **Outcome** | Tỷ lệ hiểu đúng PENDING, câu hỏi Support theo lượt đăng ký | Người học bớt hiểu nhầm chưa? |
| **Quality** | Lỗi xác nhận chỗ, bảo mật, timeout, incidents | Có an toàn và đúng nghiệp vụ không? |
| **Flow** | WIP, work item age, throughput, cycle time | Lựa chọn mới có làm nghẽn hệ thống không? |
| **Learning** | Giả thuyết được kiểm, quyết định thay từ feedback | Có giảm được điều chưa biết quan trọng? |
| **Cost/capacity** | Nỗ lực phát triển/duy trì, opportunity cost | Có hợp lý khi dời email/dashboard? |
| **Sustainability** | Bị ngắt việc, phụ thuộc một chuyên gia, làm quá giờ | Nhóm có thể duy trì thay đổi không? |

Không dùng chỉ số số lần thay thứ tự backlog như thước đo thành công. **Thay đổi nhiều không nhất thiết tốt; thay đổi đúng theo bằng chứng mới là mục tiêu.**

### 20.2. Mô phỏng một lần kiểm lại sau PB-11/PB-10

Giả sử sau khi triển khai có kiểm soát, nhóm thử **một mẫu khác gồm 30 học viên** và quan sát trong kỳ:

| Tín hiệu | Trước thay | Sau thay giả định |
| --- | ---: | ---: |
| Hiểu đúng PENDING trong bài thử | 20/30 | 26/30 |
| Tỷ lệ hiểu đúng | 66,7% | 86,7% |
| Lượt hỏi Support về trạng thái /100 lượt đăng ký | 18 | 10 |
| Fault-injection còn spinner khó thoát /20 lượt thử | 3 | 0 |
| Vi phạm sức chứa được quan sát trong kiểm thử/giám sát | 0 | 0 |

Phép tính:

~~~text
Hiểu đúng trước = 20/30 × 100% ≈ 66,7%
Hiểu đúng sau  = 26/30 × 100% ≈ 86,7%
Tăng tuyệt đối = 86,7 − 66,7 = 20,0 điểm phần trăm
Tăng tương đối = (26/20) − 1 = 30%

Tỷ số lượt hỏi Support:
Trước = 18 lượt /100 lượt đăng ký
Sau   = 10 lượt /100 lượt đăng ký
Giảm = 8 lượt /100 lượt đăng ký
Giảm tương đối = (18−10)/18 ≈ 44,4% trong hai kỳ minh họa
~~~

**Không kết luận PB-11/PB-10 gây ra đúng 20 điểm phần trăm cải thiện hoặc giảm Support 44,4%.** Có thể hai mẫu học viên khác nhau, người tham gia đã từng xem giao diện cũ, hỗ trợ được cải thiện, số workshop khác hoặc cách ghi ticket thay đổi. Số 0 lỗi được quan sát **không chứng minh rủi ro bằng 0**.

### 20.3. Khi kết quả không như kỳ vọng

Giả sử sau PB-11, tỷ lệ hiểu đúng chỉ lên 21/30, hoặc support questions không giảm. Quyết định hợp lý có thể là:
- Phỏng vấn người trả lời sai, xem thứ tự các màn hình.
- Kiểm lại điều kiện và cách hỏi.
- Thử thay đổi nhỏ hơn ở trang trước khi gửi.
- Kiểm một cohort khác.
- Tạm dừng mở rộng nếu có tác dụng phụ.
- Đánh giá lại giả thuyết, không cố “chứng minh PB-11 đã thành công”.

**Một thí nghiệm không đạt giả thuyết vẫn có giá trị nếu giúp tránh đầu tư sai và làm rõ nhu cầu.**

### 20.4. Đánh giá flow mà không che công việc bị bỏ dở

Nếu thay thứ tự khiến PB-04 email đang làm dở nằm chờ nhiều tuần, dashboard của các item Done có thể trông nhanh nhưng **aging WIP vẫn xấu**. Cần:
- Theo dõi item đã Started chưa Finished.
- Ghi quyết định dừng/tách theo trạng thái an toàn.
- Không đổi ranh giới Started/Finished để làm đẹp biểu đồ.
- Xem throughput, cycle time distribution và blocked reasons.
- Ghi chất lượng và lỗi tích hợp của các thay đổi ưu tiên mới.

### 20.5. Khi nào xem lại thứ tự?

Các trigger có thể là:
- Người dùng không hiểu đúng hoặc tác vụ không hoàn tất.
- Incident/bảo mật/tuân thủ có rủi ro cao.
- Một PBI/chủ đề cần thiết đã hoàn thành và có dữ liệu mới.
- Nhu cầu kinh doanh hoặc điều kiện thị trường đổi.
- Một experiment đã cho kết quả đủ để chọn hướng.
- Phụ thuộc/kỹ thuật khiến forecast không còn hợp lý.
- Product Goal hoàn thành hoặc không còn phù hợp.

Không nhất thiết đổi backlog theo giờ hoặc đợi cuối quý. **Cadence và trigger phải phục vụ việc học và ra quyết định**, không phải tạo thêm một nghi thức cứng.

## 21. Thương lượng với stakeholder khi ưu tiên thay đổi

### 21.1. Vì sao thay backlog dễ gây xung đột?

Khi PB-04 email từ vị trí cao ở V0 xuống thứ 5 của active V1, stakeholder đã đề xuất email có thể lo:
- “Chúng tôi đã hứa với người tổ chức.”
- “Nhóm làm trái roadmap.”
- “Chúng ta cứ thay đổi mãi, bao giờ mới xong?”
- “Tại sao trang giải thích lại được ưu tiên hơn dashboard?”
- “Các Developers có đang tự chọn việc dễ?”

Một Product Owner có trách nhiệm không nên chỉ trả lời “Agile thì phải linh hoạt”. Cần **cho thấy bằng chứng, rủi ro, cơ hội mất đi, lý do và mốc quyết định tiếp**.

### 21.2. Mẫu trao đổi ngắn, có thể kiểm

> “Ở phiên thử đầu, 10 trong 30 học viên hiểu sai PENDING là đã có chỗ, và trong 100 đăng ký có 18 lượt hỏi Support về trạng thái. Chúng ta vẫn chưa đủ dữ liệu để nói email sẽ giải vấn đề trước xác nhận. Vì vậy thứ tự backlog mới đặt PB-11 giải thích PENDING, PB-10 xử lý lỗi mạng và PB-09 quan sát chất lượng lên trước PB-04. Email không bị hủy; chúng ta sẽ kiểm nhu cầu kênh qua PB-12, rồi quyết định tiếp tại Sprint Review sau. Quy tắc không vượt sức chứa, quyền dữ liệu và Definition of Done giữ nguyên.”

Thông điệp nêu rõ:
- **Quan sát** với mẫu số.
- **Giả thuyết** cần kiểm.
- **Phương án được ưu tiên** và trade-off.
- **Điều không bị đánh đổi**.
- **Ngày/điều kiện xem lại**.
- **Trách nhiệm Product Owner và Developers**.

### 21.3. Khi có sự bất đồng thật

| Ý kiến | Câu hỏi giúp ra quyết định |
| --- | --- |
| Sales cần email ngay để ký hợp đồng | Có nghĩa vụ/điều kiện hợp đồng cụ thể? Loại email nào và hạn chót nào? |
| Support muốn trạng thái rõ ngay | Có bao nhiêu câu hỏi, người dùng bị ảnh hưởng thế nào? |
| Engineering muốn sửa timeout trước | Nguy cơ gây xác nhận giả, không thể retry hay chỉ là spinner? |
| Operations cần thêm observability | Không thấy lỗi nào, ảnh hưởng tới mức rủi ro nào? |
| Người tổ chức cần dashboard | Quyết định vận hành nào chưa thể đưa ra, có giải pháp tạm an toàn? |
| Lãnh đạo muốn giữ ngày release cố định | Có thể giảm scope hoặc chia Increment mà vẫn giữ DoD không? |

Khi nhiều mục tiêu cạnh tranh, cần nói **cái gì bị lùi** nếu ưu tiên một việc. Không thể “tất cả đều Top 1” mà không đổi capacity, phạm vi hoặc thời hạn.

### 21.4. Product Goal là bộ lọc, không phải lá chắn chống mọi nghĩa vụ

Có những việc phải xử lý dù không trực tiếp tăng tỷ lệ hiểu đúng:
- Khắc phục lỗi bảo mật.
- Đáp ứng nghĩa vụ dữ liệu hoặc tiếp cận.
- Vá lỗi gây hại đang xảy ra.
- Chăm sóc hệ thống vận hành và phục hồi.
- Sửa quy tắc thanh toán/sức chứa sai.

Không nên dùng “không liên quan Product Goal hiện tại” để từ chối nghĩa vụ bắt buộc. **Tách bắt buộc khỏi tối ưu tùy chọn**, rồi quản lý capacity và kỳ vọng minh bạch.

## 22. Thực hành mô phỏng hai vòng phản hồi

### 22.1. Vòng 0: tạo backlog ban đầu

Nhóm học chia vai:
- Product Owner.
- Developers: frontend, backend, test/operations (là kỹ năng, không mặc định ba team riêng).
- Học viên.
- Người tổ chức.
- Support.
- Observer ghi bằng chứng, assumption và quyết định.

**Đầu bài:**
- Workshop có sức chứa giới hạn.
- Học viên gửi yêu cầu trước khi được người tổ chức xác nhận.
- API có thể timeout.
- Trạng thái đúng quan trọng hơn thông báo đẹp.
- Nhu cầu email và dashboard còn bất định.

**Các bước:**
1. Viết một Product Goal và tối đa ba outcome quan trọng.
2. Vẽ một hành trình người dùng có điểm PENDING/CONFIRMED.
3. Tạo ít nhất sáu PBI, gồm công việc chất lượng có liên kết mục tiêu.
4. Viết AC cho ba PBI trên cùng.
5. Sắp thứ tự V0 với lý do, phụ thuộc và mức tin cậy.
6. Chọn một lát cắt có thể Done, nêu guardrails.
7. Đặt hai câu hỏi feedback và phương pháp quan sát trước khi xây.

**Đầu ra nộp:** Product Goal + bảng V0 + một PBI chi tiết + kế hoạch feedback.

### 22.2. Vòng 1: nhóm nhận feedback bất lợi

Giảng viên/observer đưa dữ kiện F01–F05:
- F01: chỉ 20/30 người hiểu đúng PENDING.
- F02: 18 lượt liên hệ trạng thái trên 100 đăng ký.
- F03: 3/20 lần mô phỏng lỗi mạng có spinner khó thoát.
- F04: một stakeholder đề xuất dashboard.
- F05: một số người muốn thông báo nhưng chưa rõ lúc nào.

Người học cần:
1. Phân loại **quan sát, ý kiến, giả thuyết và rủi ro**.
2. Xác định phản hồi nào liên quan trực tiếp Product Goal.
3. Gộp feedback trùng và ghi điều còn chưa biết.
4. Tạo/chỉnh PBIs với AC.
5. Sắp lại active backlog có thứ tự duy nhất.
6. Nêu rõ ba PBI được nâng, hai PBI bị dời, một PBI cần thử trước khi xây.
7. Viết một decision log có trade-off và quyền quyết.
8. Gửi một thông điệp giải thích tới stakeholder.

**Đầu ra nộp:** feedback log + V1 + decision log + thông điệp.

### 22.3. Vòng 2: kiểm chứng kết quả và chọn hướng tiếp

Giảng viên đưa dữ kiện sau sửa giả định:
- 26/30 người hiểu đúng PENDING.
- 10 lượt hỏi Support trên 100 đăng ký.
- 0/20 lượt fault-injection có spinner không thoát được.
- Không quan sát vi phạm sức chứa trong mẫu, nhưng chưa chứng minh rủi ro bằng 0.
- PB-04 vẫn chưa được triển khai.

Nhóm phải:
1. Tính chênh lệch theo **điểm phần trăm** và tỷ số.
2. Nêu **ít nhất ba biến gây nhiễu**.
3. Giữ guardrails nào và cần monitor điều gì tiếp?
4. Quyết định tiếp tục PB-12 khám phá kênh hay chuyển PB-04 lên cao hơn?
5. Nêu điều kiện nếu kết quả sau sửa lại xấu.
6. Ghi thêm một learning item giúp giảm bất định tiếp theo.

**Đầu ra nộp:** báo cáo V1 result + một quyết định V2 có lý do.

### 22.4. Phân vai để luyện xung đột ưu tiên

- **Product Owner:** ưu tiên theo giá trị, bảo vệ một Product Backlog.
- **Developers:** xem việc nào khả thi, AC/DoD, dependencies, test, WIP.
- **Support:** nêu dữ liệu thật, không tự ra lệnh làm tính năng.
- **Stakeholder:** bảo vệ nhu cầu kinh doanh, chỉ rõ ràng buộc.
- **Observer:** kiểm xem những quyết định nào dựa trên dữ liệu/giả định, item nào bị lùi.
- **Facilitator/Scrum Master nếu nhóm dùng Scrum:** giúp trao đổi hiệu quả, không quyết backlog thay Product Owner.

**Tiêu chí đạt:** không cần mọi bên đồng ý tuyệt đối, nhưng có **quyền quyết rõ, lý do và bước kiểm tiếp**.

## 23. Các sai lầm khi tạo rồi đổi backlog

| Sai lầm | Hậu quả | Cách điều chỉnh |
| --- | --- | --- |
| Viết backlog từ danh sách feature một người đề xuất | Không thấy vấn đề người dùng | Discovery và Product Goal |
| Không có Product Goal | Mỗi stakeholder dùng tiêu chí khác | Mục tiêu sản phẩm có thể kiểm |
| User story chỉ là task kỹ thuật | Khó biết giá trị hoàn tất | Vertical slices và outcome |
| Story quá lớn | Feedback đến muộn | Chia theo hành trình/rủi ro |
| Chỉ viết user story, bỏ acceptance criteria | Hiểu khác nhau, rework | Rule, examples và test |
| Coi PENDING là đã được giữ chỗ | Hại người dùng | Thống nhất trạng thái nghiệp vụ |
| Coi Done là đã merge | Không có Increment an toàn | DoD và integration |
| Chỉ định thứ tự bằng ý kiến senior nhất | Bỏ phản hồi khách hàng | Minh bạch bằng chứng và trade-off |
| Chấm mọi PBI theo một điểm số máy móc | Đẩy rủi ro bắt buộc xuống thấp | Tách nghĩa vụ an toàn/tuân thủ |
| Chọn backlog order nhưng không ghi lý do | Sau feedback khó hiểu vì sao đổi | Rationale và assumption |
| Giữ cứng roadmap dù có bằng chứng mới | Xây sai nhu cầu lâu hơn | Product Backlog thích ứng |
| Đổi backlog theo mọi lời bình | WIP/phân tán tăng | Triage và kiểm độ tin cậy |
| Sao chép một feedback thành một ticket | Trùng lặp và backlog phình | Gộp theo vấn đề/giả thuyết |
| Xem mỗi đề xuất giải pháp là nhu cầu | Xây SMS không giải trạng thái | Tìm nhu cầu cơ bản |
| Chỉ thu phản hồi tích cực | Thiên lệch | Quan sát tác vụ và kịch bản lỗi |
| Chỉ đo completion của ticket | Không biết người dùng hiểu đúng | Outcome/quality/flow |
| Đếm Support contact thành số người gặp lỗi | Sai mẫu số và ý nghĩa | Định nghĩa contact/unique user |
| Bỏ AC test khi đổi PBI | Lỗi không được phòng ngừa | Cập nhật test và DoD |
| Đổi thứ tự không nói việc gì bị dời | Stakeholder mất lòng tin | Truyền thông trade-off |
| Người ngoài team sửa Sprint Backlog ngầm | Sprint Goal bị phá | Thương lượng theo trách nhiệm |
| Để PO tự ép Developers cam kết vô hạn | Mất khả thi và chất lượng | Dự báo theo capacity/flow |
| Giải feedback bằng cách kéo thêm WIP | Cycle time dài hơn | Pull, WIP policy |
| Đưa bug dữ liệu nghiêm trọng vào refinement thường | Kéo dài nguy cơ | Incident/mitigation đúng policy |
| Coi không thấy lỗi trong mẫu nhỏ là an toàn tuyệt đối | Rủi ro không được bảo vệ | Test, monitoring và guardrails |
| Dùng story points như tiền/giá trị | Ưu tiên sai | Giá trị thực, rủi ro và outcome |
| Bỏ dữ liệu nhạy cảm vào dashboard công khai | Nguy cơ riêng tư | Phân quyền và tối thiểu dữ liệu |
| Không theo dõi PBI Done lịch sử | Khó truy trace vì sao lại làm | Giữ lịch sử và PBI cải tiến mới |
| Giữ backlog chứa mọi ý tưởng vĩnh viễn | Mất trọng tâm | Gộp, đóng, hủy có lý do |
| Chỉ đo các item Done | Bỏ item đang già | Aging WIP và blocked time |
| Không đọc lại kết quả sau đổi thứ tự | Thiếu vòng học | Thử, đo, giữ/chỉnh/dừng |
| Khẳng định nhân quả từ hai mẫu 30 người | Quyết định quá tự tin | Công bố confounders, thử tiếp |
| Biến refinement thành cuộc họp bắt buộc dài | Tốn thời gian, chưa rõ quyết định | Refinement liên tục đúng nhu cầu |
| Giao dashboard đẹp trước tính đúng | Giá trị bị trì hoãn | Liên kết Product Goal và bất biến |

## 24. Bài thực hành có đáp án/hướng dẫn

### 24.1. Bài A – Tạo Product Goal và outcome (10 phút)

Một nhóm chỉ được giao yêu cầu: “Xây cổng đăng ký workshop có đăng nhập, email, dashboard, tìm kiếm, xuất dữ liệu”.

Hãy viết:
1. Một Product Goal tập trung người dùng.
2. Hai outcome cần đo.
3. Hai guardrails.
4. Một câu hỏi discovery trước khi chọn giải pháp.

**Đáp án định hướng:** mục tiêu có thể là đăng ký và hiểu trạng thái đúng, không vượt chỗ. Outcome là hiểu đúng PENDING và ít liên hệ Support về trạng thái. Guardrails: quyền dữ liệu và tính nhất quán sức chứa. Discovery: “Học viên cần biết lúc nào đã giữ chỗ?” thay vì “Muốn SMS hay email?”.

### 24.2. Bài B – Viết story có ích (15 phút)

Chuyển ba task:
- “Thêm cột status vào database”.
- “Làm trang trạng thái”.
- “Gửi email tự động”.

thành user stories hoặc PBIs liên kết Product Goal. Với mỗi item ghi:
- Ai cần?
- Việc hoặc vấn đề gì?
- Lợi ích là gì?
- Cách kiểm chứng?
- Có phụ thuộc nào?

**Đáp án định hướng:** không coi database column là giá trị hoàn chỉnh; đặt dưới khả năng xem trạng thái đúng, làm rõ PENDING/CONFIRMED và điều kiện gửi email.

### 24.3. Bài C – Viết acceptance criteria và guardrails (15 phút)

Với PB-03 trạng thái, bổ sung:
1. AC cho PENDING.
2. AC cho CONFIRMED.
3. AC khi timeout.
4. AC về phân quyền.
5. Một cách kiểm mức hiểu của người dùng sau giao.

**Đáp án:** PENDING chưa giữ chỗ, CONFIRMED chỉ từ nguồn có thẩm quyền; lỗi mạng không suy đoán xác nhận; không xem đăng ký người khác; thử người dùng trong tác vụ thật.

### 24.4. Bài D – Tạo backlog V0 sáu item (20 phút)

Chọn tối thiểu sáu hạng mục từ:
- Gửi đăng ký.
- Xác nhận chỗ.
- Xem trạng thái.
- Email.
- Dashboard.
- Tìm kiếm.
- Test sức chứa.
- Xử lý timeout.
- Quan sát lỗi.
- Hủy đăng ký.

Sắp thành thứ tự 1–6, có **Product Goal, lý do, phụ thuộc và điều chưa biết**. Không được dùng một score duy nhất để hạ test bất biến sức chứa.

**Gợi ý:** lát cắt đăng ký/trạng thái an toàn lên đầu; email/dashboard là lựa chọn cần chứng minh.

### 24.5. Bài E – Phân loại feedback (15 phút)

Phản hồi:
- 10/30 hiểu sai PENDING.
- 18 contact Support trên 100 đăng ký.
- 3/20 fault tests spinner không thoát.
- Một stakeholder muốn dashboard.
- Một số học viên muốn SMS.

Hãy phân thành **outcome, support, quality, opinion, proposal**; chỉ ra:
- Cái nào là quan sát?
- Cái nào cần thêm bằng chứng?
- Điều gì có thể cùng nguyên nhân?
- Có nguy cơ nào phải escalated ngay nếu xuất hiện production?

**Đáp án:** F01/F02 có thể cùng vấn đề hiểu trạng thái; F03 cần sửa handling lỗi; F04/F05 chưa tự chứng minh giải pháp. “CONFIRMED giả” gây hại phải xử lý theo incident policy nếu xảy ra.

### 24.6. Bài F – Tính kết quả trước feedback (10 phút)

Có 20/30 học viên hiểu đúng, 18 lượt hỏi trên 100 đăng ký, 3/20 lượt fault tests gặp spinner.

1. Tỷ lệ hiểu đúng?
2. Tỷ lệ hiểu sai trong mẫu?
3. Tỷ số contact Support được mô tả đúng thế nào?
4. Tỷ lệ spinner trong fault tests?
5. Điều **không thể** suy ra?

**Đáp án:**
- **20/30 ≈ 66,7%** hiểu đúng.
- **10/30 ≈ 33,3%** hiểu sai.
- **18 lượt liên hệ /100 lượt đăng ký**, không phải 18% học viên.
- **3/20 = 15%** trong fault tests.
- Không suy tỷ lệ lỗi production, xác suất trên toàn bộ người dùng hoặc nguyên nhân chắc chắn.

### 24.7. Bài G – Xây backlog V1 có trace (20 phút)

Sau khi PB-01/02/03 Done, những item còn lại là PB-04 đến PB-10. Bổ sung PB-11 và PB-12 theo feedback.

Yêu cầu:
1. Lập thứ tự V1 cho chín item đang mở.
2. Nêu ít nhất ba vị trí thay đổi.
3. Tạo AC cho PB-11.
4. Bổ sung AC xử lý timeout cho PB-10.
5. Ghi một PBI không thực hiện ngay và lý do.
6. Bảo vệ các nghĩa vụ bắt buộc.

**Đáp án tham khảo:** PB-11 → PB-10 → PB-09 → PB-12 → PB-04 → PB-07 → PB-05 → PB-06 → PB-08, có thể khác nếu giả định/ràng buộc khác; phải **giải thích bằng chứng, không chỉ chép bảng**.

### 24.8. Bài H – Đổi thứ tự giữa Sprint (15 phút)

Sprint Goal là “người học biết trạng thái đáng tin”, nhóm đang làm PB-04 và PB-05. F01 đến giữa Sprint.

Hãy:
- Chỉ ra Product Owner có thể đổi gì ngay.
- Developers phải xem điều gì trong Sprint Backlog.
- Khi nào điều chỉnh scope?
- Khi nào chờ Sprint kế tiếp?
- Khi nào kích hoạt incident?
- Làm sao thông báo trade-off?

**Đáp án:** PO có thể sắp Product Backlog, Developers điều chỉnh kế hoạch hướng Sprint Goal; phạm vi thương lượng, không làm suy giảm Sprint Goal. Rủi ro xác nhận sai production cần incident. Không để stakeholder giao riêng PB-11 cho một Developers và âm thầm giữ mọi cam kết.

### 24.9. Bài I – Kanban và WIP (10 phút)

Doing = 3, Review = 2, Verify = 1, total WIP limit = 6; PB-11 vừa lên Top 1 và chưa Started.

1. WIP hiện tại?
2. Có tự kéo thêm PB-11 không?
3. Nếu xuất hiện bug nghiêm trọng, thay chính sách thế nào?
4. Nếu một item bị blocked, có tính WIP không?
5. Nhóm xem metric nào để biết thay đổi tốt hơn?

**Đáp án:** WIP = **6**; chưa kéo thường lệ nếu limit = 6. Bug có đường expedite/incident theo rủi ro và trade-off rõ; blocked sau Started vẫn là WIP; xem age, throughput, cycle time, chất lượng.

### 24.10. Bài J – Kết quả sau thay đổi (10 phút)

Trước: 20/30 hiểu đúng, 18 contact/100 đăng ký. Sau: 26/30 hiểu đúng, 10 contact/100 đăng ký.

1. Tính tỷ lệ trước/sau.
2. Chênh lệch điểm phần trăm?
3. Mức tăng tương đối trong tỷ lệ hiểu đúng?
4. Mức giảm contact trên 100 đăng ký?
5. Nêu ba lý do không tuyên bố quan hệ nhân quả chắc chắn.

**Đáp án:** 66,7% → 86,7%, tăng **20 điểm phần trăm**, tăng tương đối **30%** theo 20 → 26; 18 → 10 contact/100, giảm **8 contact/100**, tương đương 44,4% so với 18. Hai mẫu nhỏ và khác bối cảnh, đo lường có thể thay, có can thiệp khác.

### 24.11. Bài K – Nêu một quyết định không làm (15 phút)

Stakeholder yêu cầu:
- Email cho PENDING có dòng “Bạn đã đăng ký thành công”.
- SMS cho mọi trạng thái mỗi năm phút.
- Dashboard với năm biểu đồ.
- Xuất đầy đủ email/số điện thoại mọi học viên.

Hãy chọn:
1. Một yêu cầu cần từ chối hoặc thay cách diễn đạt vì dễ gây sai.
2. Một yêu cầu nên kiểm nhu cầu trước.
3. Một yêu cầu có rủi ro dữ liệu phải xem quyền/chính sách.
4. Một cách thông báo từ chối có lý do, không đổ lỗi stakeholder.

**Gợi ý:** PENDING không có nghĩa chỗ đã được giữ; thông báo tần suất cao có chi phí và nguy cơ spam; xuất dữ liệu cá nhân cần kiểm soát; dashboard cần gắn quyết định vận hành.

### 24.12. Bài L – Lập quyết định V2 nếu dữ liệu xấu đi (20 phút)

Sau khi ưu tiên PB-11, tỷ lệ hiểu đúng không cải thiện, support contact tăng và PB-04 đang dở dang. Viết decision log:
- Điều biết chắc và chưa biết.
- Những dữ liệu cần kiểm lại.
- Việc đang Started xử lý an toàn ra sao.
- Phương án tiếp: giữ, đổi, thử, dừng.
- Đo outcome/quality/flow thế nào.
- Ai quyết và thời điểm review.

**Gợi ý:** không tăng lại email chỉ vì “cần làm gì đó”; kiểm giả định về điểm gây hiểu nhầm và rủi ro. Không xóa work in progress khỏi flow chỉ để báo cáo đẹp.

### 24.13. Bài M – Diễn tập Product Owner và stakeholder (20 phút)

Một người đóng Product Owner, một người đóng Support, một người đóng lãnh đạo, hai người đóng Developers.

Nhiệm vụ:
- Support đưa F01/F02.
- Lãnh đạo yêu cầu email đúng kế hoạch.
- Developers mô tả PB-10 có rủi ro lỗi và PB-11 có thể giao nhỏ.
- Product Owner chọn thứ tự, điều kiện kiểm và trade-off.
- Observer ghi câu nào là evidence và câu nào là assumption.

**Tiêu chí đạt:** có quyết định rõ, lắng nghe ý kiến, bảo vệ DoD, không coi mọi đề xuất đều là mệnh lệnh.

### 24.14. Bài N – Tạo bộ artifact hoàn chỉnh (30–45 phút)

Từ một sản phẩm khác (đặt lịch khám, mượn thiết bị, đặt phòng học hoặc đăng ký khóa học), hãy nộp:
- Product Goal và hai outcome.
- Bản đồ người dùng/hành trình.
- 8–12 PBI ban đầu có thứ tự.
- Hai user stories có AC.
- Increment thử đầu và phương pháp feedback.
- Ba phản hồi khác nguồn.
- Backlog V1 sau đổi (gạch rõ PBI nào được nâng/hạ).
- Decision log.
- Một thử nghiệm đo tiếp và guardrails.
- Thông điệp stakeholder 150–250 từ.

Không bắt buộc backlog V1 phải khác hoàn toàn V0; **điểm chấm là lý do và bằng chứng**.

### 24.15. Thang tự đánh giá

| Tiêu chí | Chưa đạt | Đạt | Vững |
| --- | --- | --- | --- |
| **Product Goal** | Danh sách feature | Mục tiêu người dùng và ràng buộc | Outcome, bất định và guardrails |
| **Story/AC** | Task kỹ thuật, mơ hồ | Story có giá trị và AC kiểm được | Vertical slice, lỗi/ngoại lệ và DoD |
| **V0** | Danh sách không lý do | Có thứ tự và trade-off | Có nguồn/giả định, phụ thuộc và risk |
| **Feedback** | Chỉ nghe ý kiến | Quan sát có nguồn, mẫu số | Phân biệt nguyên nhân, đề xuất và độ tin cậy |
| **V1** | Đổi vì người yêu cầu lớn tiếng | Có PBI mới/chỉnh/đổi thứ tự | Trace F→PBI→Decision→Experiment |
| **Scrum/Kanban** | Thay kế hoạch vô tội vạ | Đúng quyền, Sprint Goal/WIP | Quản lý capacity, risk và flow |
| **Đo kết quả** | Chỉ nhìn số Done | Outcome + quality + flow | Hiểu điểm %, confounders và học tiếp |
| **Phối hợp** | Không giải thích việc bị dời | Thông báo trade-off | Có quyền quyết, mốc xem lại, tin cậy |

## 25. Các biểu mẫu dùng ngay trong dự án

### 25.1. Phiếu Product Goal và giả thuyết

~~~text
Product:
Người dùng chính:
Vấn đề quan sát:
Product Goal:
Bằng chứng hiện tại:
Giả định quan trọng:
Outcome cần đo (mẫu số, thời gian):
Quality/security/business guardrails:
Ranh giới MVP/Increment thử:
Điều chưa biết:
Thời điểm xem lại mục tiêu:
~~~

### 25.2. Phiếu user story và acceptance criteria

~~~text
PBI ID:
Tên:
Là [ai], tôi muốn [nhu cầu], để [lợi ích]:
Liên kết Product Goal:
Quy tắc nghiệp vụ và ví dụ:
Acceptance criteria:
- Given / When / Then:
- Trường hợp lỗi:
- Trường hợp quyền dữ liệu:
Definition of Done áp dụng:
Phụ thuộc/contract:
Giả định chưa rõ:
Kích thước tương đối nếu có:
Nguồn feedback và owner:
~~~

### 25.3. Product Backlog V0/V1 table

~~~text
Version:
Ngày/điều kiện tạo snapshot:
Product Goal:
Order | ID | PBI | Outcome/Risk | Evidence | Dependency | Size | Status | Rationale
...
Các PBI Done giữ lịch sử ở đâu:
Các item gộp/tách/xóa có trace thế nào:
Cơ chế quyền chỉnh thứ tự:
Review trigger:
~~~

### 25.4. Feedback log có phân loại

~~~text
Feedback ID:
Nguồn/kênh:
Ngày và phạm vi mẫu:
Quan sát nguyên văn (đã bảo vệ dữ liệu cá nhân):
Loại: outcome / technical / flow / opinion / proposal / incident
Mẫu số/định nghĩa:
Điều đã biết:
Giả thuyết/nguyên nhân có thể:
Mức rủi ro và độ khẩn:
Điều cần kiểm tiếp:
PBI/incident liên quan:
Decision owner:
Quyết định và mốc xem lại:
Kết quả phản hồi lại người gửi:
~~~

### 25.5. Decision log sau khi sắp lại thứ tự

~~~text
Decision ID:
Product Goal:
Version trước / Version sau:
Feedback/evidence liên quan:
Những điều còn bất định:
Các phương án:
Rủi ro và cost of delay:
PBI được thêm/chỉnh/gộp/bỏ:
PBI được nâng ưu tiên:
PBI được hạ và opportunity cost:
Quyết định:
Người có quyền quyết:
Ý kiến Developers/stakeholders:
Guardrails và nghĩa vụ bắt buộc:
Ảnh hưởng Sprint Goal hoặc WIP:
Người thực hiện:
Bằng chứng cần thu:
Điều kiện giữ/chỉnh/dừng:
Ngày kiểm lại:
~~~

### 25.6. Kế hoạch feedback/experiment nhỏ

~~~text
Experiment ID và PBI:
Product Goal/hypothesis:
Đối tượng và tác vụ:
Can thiệp nhỏ:
Cách chọn mẫu/cohort:
Metric chính, định nghĩa, mẫu số:
Baseline:
Thời gian/cỡ mẫu mong muốn:
Thước đo phụ:
Quality, privacy, security guardrails:
Owner đo và owner quyết:
Confounders và rủi ro diễn giải:
Tiêu chí giữ/chỉnh/dừng:
Cách thông báo kết quả:
~~~

### 25.7. Phiếu kế hoạch Sprint/flow sau reprioritization

~~~text
Product Backlog version:
Sprint Goal hoặc flow goal:
Những PBI Ready phù hợp mục tiêu:
Capacity/WIP/đơn vị đo:
Những item đang Started và nguy cơ:
Dependencies cần giải:
Definition of Done:
Incident/expedite policy:
Nếu feedback mới đến thì ai quyết:
Điều gì bị lùi và cần thông báo:
Checkpoints:
Cách đo throughput/cycle time/age/quality:
~~~

### 25.8. Báo cáo học và quyết định kế tiếp

~~~text
Product Goal:
Increment mới đã thật sự Done:
Feedback mới và nguồn:
Outcome trước/sau:
Quality và incidents:
WIP, throughput, cycle time, aging WIP:
Giả thuyết được hỗ trợ/bác bỏ/chưa rõ:
Confounders và giới hạn:
Chi phí/đánh đổi:
Product Backlog V2 đề xuất:
Quyết định: giữ / chỉnh / thử tiếp / dừng
Owner và mốc kiểm tiếp:
Stakeholders đã được thông báo:
~~~

**Không biến các biểu mẫu thành tám cổng phê duyệt bắt buộc.** Có thể lưu các thông tin quan trọng ngay trong công cụ backlog, issue hoặc decision log của nhóm. Điều cốt lõi là **truy vết được từ phản hồi đến lý do và hành động**, không phải có thêm tài liệu.

## 26. Checklist hoàn thành bài thực hành

**Mục tiêu và khám phá**

- [ ] Đã xác định ranh giới sản phẩm và đối tượng người dùng.
- [ ] Product Goal mô tả kết quả có ý nghĩa, không chỉ danh sách tính năng.
- [ ] Đã tách nhu cầu người dùng khỏi giải pháp stakeholder đề xuất.
- [ ] Có giả định và điều chưa biết quan trọng cần kiểm.
- [ ] Các guardrails bảo mật/dữ liệu/đúng nghiệp vụ được ghi.
- [ ] Đã chọn một lát cắt nhỏ để giao và học sớm.

**Backlog V0**

- [ ] Mỗi PBI quan trọng có ID, tên, mục tiêu và nguồn.
- [ ] Có ít nhất một user story đầy đủ người dùng–nhu cầu–lợi ích.
- [ ] Acceptance criteria có tình huống bình thường và lỗi.
- [ ] Definition of Done được phân biệt khỏi AC riêng của PBI.
- [ ] Có thứ tự Product Backlog duy nhất, không phải tất cả “cao”.
- [ ] Thứ tự có lý do theo giá trị, rủi ro, phụ thuộc và khả năng học.
- [ ] Story lớn được chia theo lát cắt có thể kiểm chứng.
- [ ] PBI kỹ thuật cần thiết có liên kết chất lượng và Product Goal.

**Increment và phản hồi**

- [ ] Một Increment đã thực sự đạt DoD trước khi gọi là Done.
- [ ] Phương thức thu feedback được thiết kế trước release/thử nghiệm.
- [ ] Quan sát người dùng có kịch bản và mẫu số phù hợp.
- [ ] Test an toàn nghiệp vụ, timeout và quyền dữ liệu không bị bỏ.
- [ ] Phân biệt outcome, technical feedback và flow feedback.
- [ ] Feedback quan trọng có nguồn, thời điểm, phạm vi và owner.
- [ ] Phân biệt sự kiện, giả thuyết, ý kiến và giải pháp.
- [ ] Không nói tỷ số contact là tỷ lệ người gặp lỗi khi mẫu không cho phép.

**Backlog V1 và trade-off**

- [ ] Đã phân loại, gộp hoặc tách feedback tránh trùng PBI.
- [ ] Có PBI mới hoặc AC được chỉnh dựa trên bằng chứng thật.
- [ ] Đã ghi rõ thứ tự active backlog sau feedback.
- [ ] PBI Done được giữ lịch sử, không xóa vì học được điều mới.
- [ ] Nêu PBI nào được nâng và vì sao.
- [ ] Nêu PBI nào bị dời và cơ hội/chi phí tương ứng.
- [ ] Các nghĩa vụ an toàn/tuân thủ không bị hạ bằng điểm số.
- [ ] Product Owner hoặc người được phân quyền phù hợp chịu trách nhiệm thứ tự.
- [ ] Stakeholders nhận được lý do và mốc kiểm tiếp.

**Thực thi theo phương pháp phù hợp**

- [ ] Nếu Scrum, việc đổi Product Backlog không âm thầm phá Sprint Goal.
- [ ] Developers được tham gia thương lượng phạm vi và kế hoạch.
- [ ] Nếu Kanban, WIP và chính sách pull được tôn trọng.
- [ ] Item đang Started/blocked không bị xóa để làm đẹp flow.
- [ ] Rủi ro nghiêm trọng có đường incident/mitigation riêng.
- [ ] CI, test và DoD tiếp tục bảo vệ chất lượng Increment.
- [ ] Có quyết định về việc nào không làm ngay và lý do.

**Đo lại, học và cải tiến**

- [ ] Có metric outcome với định nghĩa và mẫu số.
- [ ] Có quality guardrails và cách phát hiện tác dụng phụ.
- [ ] Có WIP/age/throughput/cycle time để xem tác động flow.
- [ ] Chênh lệch phần trăm và điểm phần trăm được dùng đúng.
- [ ] Kết luận không khẳng định nhân quả từ mẫu nhỏ trước/sau.
- [ ] Có mốc và điều kiện giữ, chỉnh, dừng hoặc thử tiếp.
- [ ] Bản quyết định V1/V2 có thể truy vết tới feedback.
- [ ] Nhóm giải thích được **điều đã học khiến thứ tự thay đổi**.

## 27. Tổng kết: backlog sống nhờ bằng chứng và quyết định

Bài thực hành đã đi qua một chu trình hoàn chỉnh:

1. **Khởi đầu từ Product Goal**, không từ danh sách tính năng ai đó muốn xây.
2. **Diễn đạt nhu cầu thành user stories và PBI có thể kiểm**, với acceptance criteria, DoD, risk và phụ thuộc.
3. **Sắp thứ tự Product Backlog V0** theo giá trị, an toàn và cơ hội học, đồng thời ghi giả định chưa chắc.
4. **Giao Increment nhỏ đạt Done** để có phản hồi sớm thay vì chỉ hoàn tất task cục bộ.
5. **Thu feedback có mẫu số và bối cảnh**, phân biệt việc người dùng hiểu sai, lỗi kỹ thuật, nhu cầu chưa rõ và ý kiến giải pháp.
6. **Triage và điều chỉnh backlog V1**: PB-11, PB-10 và PB-09 được ưu tiên vì dữ liệu mới; PB-04 và PB-05 được dời có lý do; PB-12 giúp học trước khi đầu tư vào kênh thông báo.
7. **Thương lượng cách thực hiện** theo Sprint Goal hoặc WIP, không chèn việc vô hạn và không bỏ guardrails.
8. **Đo lại outcome, chất lượng và flow**, rồi tiếp tục giữ, chỉnh, thử hoặc dừng theo bằng chứng.

**Product Backlog không phải hợp đồng đóng băng thứ tự công việc; nó là công cụ minh bạch những lựa chọn cải thiện sản phẩm.** Việc điều chỉnh ưu tiên có trách nhiệm không phải thay đổi cho thật nhiều, mà là giúp nhóm giao phần mềm có giá trị và chất lượng, **tìm ra giả định sai sớm, giảm rủi ro và thích ứng với phản hồi thật**.
