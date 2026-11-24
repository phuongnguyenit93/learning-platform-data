# Feature-Driven Development và vai trò của mô hình miền

> **Chương:** Các cách tiếp cận khác  
> **Học phần:** **AGILE_DEVELOPMENT** — hiểu giá trị và nguyên tắc Agile để phát triển phần mềm thích ứng qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc nhằm chọn cách phối hợp phù hợp.

Một nhóm được yêu cầu xây hệ thống đặt lịch tư vấn. Nếu chia việc ngay thành “tạo bảng SQL”, “làm API”, “viết giao diện” và “gửi email”, từng nhóm chuyên môn có thể hoàn thành phần của mình nhưng khách hàng vẫn chưa đặt được một lịch hợp lệ. Tệ hơn, giao diện có thể hiểu “giữ chỗ” khác backend, còn dịch vụ thông báo lại coi lịch vừa tạo là đã xác nhận. Mỗi phần có vẻ đúng, **toàn hệ thống vẫn sai về nghiệp vụ**.

**Feature-Driven Development (FDD)** là một cách tiếp cận phát triển phần mềm theo tính năng nhỏ có giá trị cho khách hàng, lấy **mô hình miền (domain model)** làm nền tảng để hiểu thế giới nghiệp vụ, tạo danh sách feature và tổ chức thiết kế–xây dựng theo từng feature. Điểm đáng học của FDD không chỉ là “chia nhỏ công việc”, mà là **kết nối hiểu biết nghiệp vụ với cấu trúc phần mềm và các phần chức năng có thể kiểm chứng, hoàn tất thường xuyên**.

Trong bài này, *miền* là lĩnh vực vấn đề mà phần mềm phục vụ, chẳng hạn đặt lịch, quản lý kho hoặc thanh toán. **Mô hình miền** là cách nhóm diễn đạt các khái niệm, quan hệ, quy tắc và hành vi quan trọng của lĩnh vực ấy. Mô hình có thể biểu diễn bằng lời, ví dụ, sơ đồ hoặc mã; không đồng nghĩa với một sơ đồ bảng cơ sở dữ liệu. FDD thường gắn với mô hình đối tượng, nhưng giá trị cốt lõi của bài học là **hiểu đúng miền để xây đúng feature**.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Mô tả FDD là gì, mục tiêu của cách tiếp cận này và **năm quy trình** thường dùng trong FDD.
2. Giải thích vì sao **mô hình miền tổng thể** giúp nhóm có ngôn ngữ chung, tìm ranh giới nghiệp vụ, phát hiện bất biến và chia feature có ý nghĩa.
3. Phân biệt **feature theo FDD**, user story, tác vụ kỹ thuật, epic và một module kiến trúc.
4. Xây ví dụ danh sách feature theo **miền chủ đề → nhóm feature → feature nhỏ**, đồng thời liên hệ feature với quy tắc nghiệp vụ và tiêu chí kiểm chứng.
5. Mô tả công việc **Design by Feature** và **Build by Feature**, cơ chế phối hợp nhóm feature, quyền sở hữu lớp và vấn đề tích hợp/chất lượng.
6. Đánh giá khi nào FDD phù hợp, những rủi ro của mô hình hóa quá mức và cách phối hợp với Scrum, Kanban, XP để phản hồi sớm.

## 2. FDD giải quyết vấn đề nào?

**FDD (Feature-Driven Development)** được phát triển từ thực hành xây dựng các hệ thống phần mềm lớn, thường gắn với công trình của **Jeff De Luca và Peter Coad**. FDD đặt trọng tâm vào:

- **Hiểu miền nghiệp vụ đủ sâu:** Có mô hình tổng thể giúp người phát triển và chuyên gia nghiệp vụ nói cùng một ngôn ngữ.
- **Chia công việc theo feature nhỏ có giá trị:** Mỗi phần việc diễn đạt kết quả mà người dùng hoặc bên liên quan nhận được, thay vì chỉ là công việc công nghệ.
- **Tổ chức thiết kế và xây dựng theo feature:** Một nhóm feature phối hợp trên các phần mô hình liên quan, hoàn tất và tích hợp thường xuyên.
- **Theo dõi tiến độ bằng phần đã hoàn tất:** Minh bạch những feature đã qua các bước thiết kế, xây dựng, kiểm tra và tích hợp, thay vì chỉ báo “đã viết 80% code”.

FDD nổi bật trong các bối cảnh có **miền nghiệp vụ tương đối phức tạp**, nhiều quy tắc và nhiều thành viên cần cộng tác. Tuy nhiên, việc dùng FDD không đảm bảo thành công nếu đội ngũ ít tiếp xúc với người hiểu nghiệp vụ, hiểu sai mô hình hoặc coi danh sách feature ban đầu là hợp đồng bất biến.

### 2.1. Khác với việc quản lý dự án bằng danh sách công nghệ

| Cách chia theo bộ phận/kiến trúc | Cách nhìn hướng feature theo giá trị |
| --- | --- |
| “Tạo bảng Appointment và Slot.” | “Ngăn hai khách giữ cùng một khung giờ.” |
| “Viết REST endpoint POST /appointments.” | “Tạo lịch hẹn hợp lệ cho khách.” |
| “Thiết kế màn hình chọn ngày.” | “Hiển thị những giờ có thể đặt của chuyên gia.” |
| “Tích hợp SMTP.” | “Thông báo xác nhận lịch sau khi đặt thành công.” |
| “Refactor lớp ReservationService.” | “Giảm lỗi tạo lịch trùng để khách có kết quả đáng tin.” |

Không có nghĩa tác vụ kỹ thuật là vô ích. Chúng **vẫn cần tồn tại trong kế hoạch thiết kế và xây dựng**, nhưng nên phục vụ một kết quả chức năng, chất lượng hoặc năng lực đã được hiểu rõ. Nếu mọi “feature” trong danh sách chỉ là đặt tên bảng và API, FDD dễ biến thành một mô hình quản lý nhiệm vụ truyền thống được đổi nhãn.

### 2.2. FDD không phải một cách viết user story khác tên

**User story** thường viết từ góc nhìn người dùng và giá trị mong muốn, ví dụ:

> “Là khách cần tư vấn, tôi muốn chọn một giờ còn trống để biết có thể đặt lịch mà không phải gọi tổng đài.”

Trong FDD, **feature** là một **chức năng nhỏ có giá trị cho khách hàng**, thường được diễn đạt bằng cấu trúc *hành động – kết quả – đối tượng* (*action – result – object*). Ví dụ:

> “Xác định các khung giờ có thể đặt của một chuyên gia.”

Hai cách mô tả có thể bổ sung nhau: user story giúp thảo luận **người dùng, nhu cầu và bối cảnh**, còn feature FDD giúp diễn đạt **hành vi chức năng cụ thể** dựa trên mô hình miền. Không nên tự động ép quan hệ một-một: một story có thể đòi nhiều feature nhỏ; một feature có thể hỗ trợ nhiều user story.

### 2.3. FDD có phải là Scrum, Kanban hay XP?

FDD là **một cách tiếp cận phát triển phần mềm riêng**, thường được xếp trong họ các phương pháp Agile. Nó không định nghĩa Sprint Goal, Sprint Review và các trách nhiệm Scrum như Scrum; cũng không đồng nghĩa phương pháp quản lý dòng theo WIP như Kanban, hay một bộ thực hành kỹ thuật giống XP.

Điểm giao nhau là việc **giao kết quả nhỏ, theo dõi tiến độ thực tế, phối hợp và học từ phản hồi**. Một nhóm có thể kết hợp các thực hành phù hợp, nhưng phải rõ cái gì thuộc quy trình FDD, cái gì là bổ sung do nhóm lựa chọn.

## 3. Năm quy trình của Feature-Driven Development

FDD truyền thống thường được mô tả bằng **năm quy trình liên kết với nhau**:

1. **Develop an Overall Model** — Phát triển mô hình tổng thể.
2. **Build a Features List** — Xây dựng danh sách feature.
3. **Plan by Feature** — Lập kế hoạch theo feature.
4. **Design by Feature** — Thiết kế theo feature.
5. **Build by Feature** — Xây dựng theo feature.

Ba quy trình đầu tạo bức tranh chung và khả năng lựa chọn thứ tự; hai quy trình sau được **lặp theo những nhóm feature nhỏ** để tạo phần mềm hoạt động được.

~~~mermaid
flowchart TD
    A["Hiểu bài toán và chuyên gia nghiệp vụ"] --> B["1. Develop an Overall Model"]
    B --> C["2. Build a Features List"]
    C --> D["3. Plan by Feature"]
    D --> E["4. Design by Feature"]
    E --> F["5. Build by Feature"]
    F --> G["Tích hợp, kiểm tra và giao kết quả"]
    G --> H["Phản hồi và hiểu biết miền mới"]
    H -. "Cập nhật mô hình, feature và ưu tiên" .-> B
    H -. "Điều chỉnh kế hoạch tiếp" .-> D
    F -. "Feature tiếp theo" .-> E
~~~

Sơ đồ nhấn mạnh khả năng **lặp lại và cập nhật**. Không nên hiểu “Develop an Overall Model” là phải mô hình hóa hoàn hảo mọi chức năng của hệ thống trong nhiều tháng rồi mới được viết dòng mã đầu tiên. Mô hình tổng thể cần **đủ tốt để định hướng**, sau đó được chỉnh khi học thêm.

### 3.1. Năm quy trình tạo những quyết định khác nhau

| Quy trình | Câu hỏi chính | Đầu ra điển hình | Điều cần tránh |
| --- | --- | --- | --- |
| **Develop an Overall Model** | Miền này có những khái niệm và quy tắc cốt lõi nào? | Hiểu biết nghiệp vụ, mô hình miền tổng thể, các giả định quan trọng. | Biến sơ đồ ban đầu thành “chân lý không được đổi”. |
| **Build a Features List** | Người dùng nhận được những chức năng nhỏ nào từ mô hình? | Danh sách feature có cấu trúc theo miền chủ đề và nhóm feature. | Liệt kê class, API hoặc task thuần kỹ thuật như feature khách hàng. |
| **Plan by Feature** | Chọn feature nào trước, phụ thuộc và ai phối hợp? | Thứ tự/nhóm triển khai, người chịu trách nhiệm, dự báo và rủi ro. | Cam kết cứng toàn bộ dự báo bất chấp thông tin mới. |
| **Design by Feature** | Các đối tượng, hành vi và tương tác nào phải thay đổi? | Thiết kế chi tiết đủ dùng, walkthrough và kiểm tra thiết kế. | Thiết kế tất cả feature tương lai trước khi học từ bản chạy. |
| **Build by Feature** | Làm thế nào hiện thực, kiểm tra, tích hợp feature này? | Code, kiểm thử, kiểm tra chất lượng và feature tích hợp. | Gọi Done khi mới viết xong code nhưng chưa đạt điều kiện kiểm chứng. |

Một feature trong FDD truyền thống thường được **chia đủ nhỏ để có thể hoàn tất trong khoảng hai tuần hoặc ngắn hơn**; đây là hướng dẫn kích thước hay gặp, không phải lời hứa mọi feature đều mất đúng hai tuần. Nếu lớn hơn, cần phân rã; nếu nhỏ nhưng không tạo kết quả có ích, cần viết lại theo nghiệp vụ.

## 4. Mô hình miền là gì và vì sao FDD bắt đầu từ đó?

### 4.1. Mô hình miền là sự hiểu biết có cấu trúc

Một **domain model** diễn đạt các khái niệm, quan hệ, hành vi, quy tắc và bất biến quan trọng của miền mà phần mềm phục vụ. Với đặt lịch tư vấn, các khái niệm có thể gồm:

- **Khách hàng (Customer)** — người yêu cầu đặt lịch.
- **Chuyên gia tư vấn (Consultant)** — người cung cấp phiên tư vấn.
- **Khung khả dụng (Availability Window)** — khoảng thời gian chuyên gia có thể nhận lịch.
- **Lịch hẹn (Appointment)** — một thỏa thuận cụ thể về người, thời điểm và trạng thái.
- **Chính sách đặt lịch (Booking Policy)** — quy tắc về xung đột, thời gian tối thiểu hoặc quyền hủy/đổi.
- **Yêu cầu đặt lịch (Booking Request)** — hành động gửi thông tin từ khách, có thể cần xử lý trùng lặp.

Đây là **mô hình minh họa**, không phải chuẩn dữ liệu bắt buộc. Trong một miền khác, “khung khả dụng” có thể được tính động thay vì lưu thành thực thể, “lịch hẹn” có thể gồm nhiều người hoặc trạng thái chờ phê duyệt. Nhóm phải hỏi chuyên gia miền trước khi chọn cách biểu diễn.

### 4.2. Mô hình miền khác sơ đồ cơ sở dữ liệu

| Góc nhìn | Câu hỏi nó trả lời | Ví dụ |
| --- | --- | --- |
| **Mô hình miền** | Khái niệm nghiệp vụ là gì, hành vi và quy tắc nào phải đúng? | “Một chuyên gia không thể có hai lịch đã xác nhận giao nhau nếu chính sách cấm.” |
| **Mô hình dữ liệu lưu trữ** | Lưu và truy vấn trạng thái bằng bảng, khóa và chỉ mục nào? | Bảng appointments có khóa chuyên gia, thời gian UTC và trạng thái. |
| **Thiết kế API** | Hệ thống bên ngoài yêu cầu hoặc nhận kết quả bằng hợp đồng nào? | POST để tạo lịch, trả ID/trạng thái và cách xử lý retry. |
| **Thiết kế giao diện** | Người dùng nhìn và thao tác như thế nào? | Danh sách giờ trống và trạng thái đang chờ/xác nhận. |

Những mô hình này **liên quan nhưng không đồng nhất**. Nếu xem mô hình miền chỉ là ảnh chụp các bảng SQL, nhóm có thể bỏ sót các quy tắc xử lý xung đột và trạng thái nghiệp vụ. Ngược lại, một sơ đồ class đầy đủ không tự đảm bảo dữ liệu an toàn khi nhiều request đến đồng thời; thiết kế triển khai vẫn cần ràng buộc và giao dịch thích hợp.

### 4.3. Khái niệm, quan hệ, hành vi và bất biến

Một mô hình hữu ích nên giúp trả lời ít nhất bốn câu:

1. **Khái niệm:** “Lịch hẹn” khác “Yêu cầu đặt lịch” ở đâu?
2. **Quan hệ:** Một Customer có thể có nhiều Appointment không? Một Appointment có thể có nhiều Consultant không?
3. **Hành vi:** Khi khách đặt lịch, chuyển trạng thái nào và phát sinh sự kiện gì?
4. **Bất biến:** Điều gì phải luôn đúng để hệ thống không làm sai nghiệp vụ?

**Bất biến (invariant)** là một điều kiện mà hệ thống phải duy trì ở những thời điểm có liên quan, chẳng hạn “một khung giờ không bị bán hai lần khi chỉ có một chỗ”. Để giữ bất biến trong thực tế, chỉ kiểm tra trên giao diện hoặc chỉ dựa vào một truy vấn trước khi lưu có thể chưa đủ vì **race condition**. Mô hình miền phải dẫn tới một cơ chế bảo đảm ở điểm cập nhật có thẩm quyền, chẳng hạn giao dịch, ràng buộc dữ liệu hoặc điều phối nhất quán phù hợp.

### 4.4. Mô hình hóa không phải đoán trước mọi thứ

FDD khuyến khích xây **overall model** để định hướng công việc, nhưng điều đó không đồng nghĩa mọi giả định ban đầu đều đúng. Mô hình cần được xem là **bản giải thích hiện tại có thể sửa**, dựa trên quan sát và đối thoại với người hiểu miền.

Ví dụ, ban đầu nhóm nghĩ trạng thái Appointment chỉ có **Confirmed** và **Cancelled**. Sau khi hỏi bộ phận hỗ trợ, họ phát hiện thời gian đối tác phản hồi khiến cần trạng thái **Pending**, và có trường hợp **Expired** khi khách không xác nhận kịp. Phát hiện này ảnh hưởng:

- Feature tạo lịch và xác nhận.
- Quy tắc giữ chỗ, tránh trùng.
- Giao diện hiển thị trạng thái.
- Thông báo và chính sách retry.
- Kiểm thử và việc tính tỷ lệ đặt lịch thành công.

Thay vì cố “vá” từng nơi bằng cờ boolean riêng, nhóm cập nhật **ngôn ngữ và quy tắc miền**, rồi xem lại danh sách feature và thiết kế liên quan.

## 5. Tạo mô hình miền tổng thể bằng đối thoại và ví dụ

### 5.1. Mở đầu từ một kịch bản nghiệp vụ thực

**Kịch bản:** Khách xem giờ trống, chọn một giờ, gửi yêu cầu. Hệ thống xác nhận rằng giờ chưa bị người khác đặt, tạo lịch và thông báo kết quả. Nếu hai khách chọn cùng giờ, chỉ một yêu cầu được xác nhận khi quy tắc cho phép một người tham gia.

Thay vì hỏi “cần bảng nào?”, bắt đầu bằng:

- Ai là người dùng và họ muốn hoàn tất tác vụ nào?
- “Giờ trống” được tính như thế nào: lịch làm việc, ngày nghỉ, lịch đã đặt, múi giờ?
- Khi nào một yêu cầu được coi là **đã xác nhận**?
- Nếu khách gửi lại do mạng timeout, có được tạo thêm lịch không?
- Nếu đối tác không phản hồi, trạng thái nào được hiển thị?
- Điều gì xảy ra khi khách đổi/hủy? Có thời hạn hay phí không?
- Ai có quyền thay đổi trạng thái và ai chịu trách nhiệm về nguồn dữ liệu chính?

Những câu hỏi này giúp tìm ra **bất biến, trạng thái và ranh giới** cần mô hình hóa trước khi đi sâu vào code.

### 5.2. Sơ đồ khái niệm mẫu

~~~mermaid
classDiagram
    class Customer {
        +CustomerId id
        +requestBooking()
    }
    class Consultant {
        +ConsultantId id
        +workingCalendar
    }
    class Appointment {
        +AppointmentId id
        +timeRange
        +status
        +confirm()
        +cancel()
    }
    class BookingPolicy {
        +canBook(timeRange)
        +canCancel(appointment)
    }
    class BookingRequest {
        +requestId
        +idempotencyKey
        +requestedTime
    }
    Customer "1" --> "0..*" Appointment : books
    Consultant "1" --> "0..*" Appointment : hosts
    BookingRequest --> Appointment : may-create
    BookingPolicy ..> Appointment : validates
~~~

Sơ đồ chỉ là **một giả thuyết mô hình miền**, không phải thiết kế triển khai cuối cùng. Nó chưa thể hiện nhiều yếu tố như quyền truy cập, hủy hết hạn, nhiều chuyên gia trong một phiên, múi giờ, cạnh tranh đồng thời hoặc dữ liệu từ đối tác. Chính việc xem và phản biện sơ đồ với chuyên gia miền mới tạo giá trị.

### 5.3. Bảng thuật ngữ chung để giảm sai lệch

| Thuật ngữ | Định nghĩa nhóm cần thống nhất | Câu hỏi còn mở |
| --- | --- | --- |
| **Khung giờ trống** | Khoảng thời gian theo chính sách hiện tại có thể nhận yêu cầu đặt lịch. | “Trống” có tính những yêu cầu Pending không? |
| **Yêu cầu đặt lịch** | Hành động do khách gửi; chưa nhất thiết tạo lịch đã xác nhận. | Retry cùng yêu cầu được nhận diện bằng gì? |
| **Lịch đã xác nhận** | Kết quả đáp ứng đủ điều kiện nghiệp vụ và được hệ thống có thẩm quyền chấp nhận. | Nếu thông báo gửi thất bại, lịch còn hợp lệ không? |
| **Hủy lịch** | Chuyển lịch sang trạng thái không còn hiệu lực theo chính sách. | Hủy sát giờ có hoàn phí không? |
| **Đổi lịch** | Yêu cầu thay thời điểm của một cuộc hẹn. | Là thay trực tiếp hay hủy và tạo mới để giữ nhất quán? |

**Ngôn ngữ chung** quan trọng vì “đã đặt” có thể bị hiểu là “đã gửi yêu cầu” ở giao diện nhưng “đã lưu giao dịch thành công” ở backend. FDD cần mô hình giúp các bên nói cùng một nghĩa trước khi xây feature.

### 5.4. Từ mô hình tổng thể sang ranh giới thiết kế

Mô hình tổng thể không bắt buộc có một đối tượng khổng lồ “BookingSystem” biết tất cả nghiệp vụ. Nhóm có thể tách các vùng khái niệm:

- **Availability:** lịch làm việc, ngày nghỉ, giờ có thể đặt.
- **Booking:** tạo yêu cầu, xác nhận, chống đặt trùng, chuyển trạng thái.
- **Notification:** gửi kết quả và trạng thái tới khách.
- **Billing:** thanh toán/phí hủy nếu tồn tại trong phạm vi sản phẩm.

Sự phân tách này là **lựa chọn thiết kế cần kiểm chứng**, không tự động yêu cầu triển khai thành bốn microservice. Các ranh giới giúp tìm chủ đề feature và người hiểu miền, nhưng quyết định kiến trúc phải dựa trên nhu cầu vận hành, dữ liệu, sự nhất quán và chi phí phối hợp.

## 6. Từ mô hình miền tới danh sách feature

**Build a Features List** chuyển hiểu biết miền thành những chức năng **nhỏ, có giá trị và có thể kiểm chứng**. Một cấu trúc thường dùng là:

1. **Subject Area** — Miền chủ đề rộng.
2. **Feature Set** — Nhóm feature liên quan tới một hoạt động nghiệp vụ.
3. **Feature** — Một hành vi nhỏ có kết quả xác định.

### 6.1. Ví dụ phân rã cho hệ thống đặt lịch

~~~text
Miền chủ đề: QUẢN LÝ LỊCH TƯ VẤN
|
+-- Nhóm feature: Khả dụng của chuyên gia
|   +-- Xác định các khung giờ có thể đặt của chuyên gia.
|   +-- Loại trừ các khung giờ đã bị chiếm theo chính sách.
|   +-- Hiển thị giờ khả dụng trong múi giờ của khách.
|
+-- Nhóm feature: Đặt lịch
|   +-- Kiểm tra điều kiện hợp lệ của yêu cầu đặt lịch.
|   +-- Tạo lịch hẹn đã xác nhận cho khách.
|   +-- Trả kết quả nhất quán khi khách gửi lại cùng yêu cầu.
|
+-- Nhóm feature: Quản lý lịch
|   +-- Kiểm tra quyền hủy lịch theo chính sách.
|   +-- Hủy một lịch hẹn còn hiệu lực.
|   +-- Xác định phương án đổi giờ hợp lệ cho lịch đã đặt.
|
+-- Nhóm feature: Thông báo
    +-- Gửi xác nhận sau khi lịch được chấp nhận.
    +-- Thông báo kết quả hủy lịch cho khách.
~~~

Những câu trên **chưa đủ thành đặc tả triển khai**; chúng là danh sách hành vi dựa trên mô hình để nhóm làm rõ dần. Khi một feature chứa nhiều trường hợp lớn, nên chia theo biến thể nghiệp vụ hoặc kết quả nhỏ hơn, nhưng vẫn giữ mỗi phần có ích.

### 6.2. Cú pháp đặt tên giúp tập trung hành vi

Một quy ước phổ biến của FDD là diễn đạt feature dưới dạng:

~~~text
<hành động> <kết quả> <đối tượng>

Xác định + khung giờ khả dụng + của một chuyên gia.
Tính     + tổng tiền hoàn trả + của một lịch đã hủy.
Hiển thị + trạng thái xác nhận + của một lịch hẹn.
~~~

Công thức là **công cụ tư duy**, không phải parser bắt buộc; tiếng Việt có thể cần thêm từ nối cho tự nhiên. Điều cốt lõi là câu feature diễn đạt **một hành vi và kết quả nghiệp vụ có thể xác minh**, không chỉ một động từ kỹ thuật như “lập trình”, “tạo class”, “viết unit test”.

### 6.3. Phân biệt feature, epic, user story, task

| Khái niệm | Câu hỏi chính | Ví dụ | Đơn vị hoàn tất |
| --- | --- | --- | --- |
| **Mục tiêu sản phẩm / initiative** | Kết quả rộng nào cần đạt? | Giảm nhu cầu gọi tổng đài để đặt lịch. | Outcome và bằng chứng sản phẩm. |
| **Epic** | Nhóm nhu cầu lớn nào cần chia tiếp? | Tự phục vụ đặt và quản lý lịch. | Được phân rã thành lát cắt nhỏ. |
| **User story** | Ai cần gì và vì sao? | Là khách, tôi muốn biết giờ trống để chọn lịch phù hợp. | Hành vi chấp nhận được, có phản hồi người dùng. |
| **FDD feature** | Chức năng nhỏ nào có giá trị, dựa trên miền? | Xác định khung giờ khả dụng của chuyên gia. | Hành vi được hiện thực, kiểm tra và tích hợp. |
| **Task kỹ thuật** | Cần làm bước nào để tạo hành vi? | Viết transaction chống xung đột, thêm kiểm thử concurrent booking. | Công việc kỹ thuật đạt tiêu chí riêng, chưa tự chứng minh giá trị đầu cuối. |

**Không ép quan hệ một–một.** Một user story đặt lịch có thể được hỗ trợ bởi nhiều feature (xem khả dụng, tạo lịch, xác nhận, retry); một feature tính khung giờ khả dụng cũng có thể phục vụ nhiều story. Các khái niệm có thể cùng tồn tại nếu nhóm thống nhất nguồn sự thật và tránh quản lý trùng lặp.

### 6.4. Một feature đủ nhỏ nhưng có giá trị nghĩa là gì?

**Phản mẫu 1 — Quá lớn:** “Xây toàn bộ hệ thống đặt lịch, thanh toán, đổi hủy và thông báo.” Nhóm khó dự báo, kiểm tra hoặc giao tăng dần.

**Phản mẫu 2 — Quá kỹ thuật:** “Tạo bảng booking_status.” Người dùng không nhận kết quả nghiệp vụ chỉ từ bảng này.

**Ví dụ tốt hơn:** “Trả về trạng thái xác nhận hiện tại của một lịch hẹn.” Nó có hành vi rõ, có thể kiểm chứng với các trạng thái hợp lệ, và giúp giao diện tránh thông báo sai khi có timeout.

**Hướng dẫn kích thước:** Chia feature đủ nhỏ để nhóm thiết kế, xây và kiểm chứng trong thời gian ngắn (FDD truyền thống thường nhắm khoảng hai tuần hoặc ít hơn). Nhưng **kích thước ngắn không có nghĩa được tách thành nhiều ticket vô nghĩa**. Nếu chỉ có “API mới” mà chưa tạo một hành vi có ích, cần giải thích nó nằm trong feature nào và khi nào tính năng có thể được kiểm chứng.

## 7. Lập kế hoạch theo feature: chọn giá trị, rủi ro và phụ thuộc

Sau khi có danh sách feature, **Plan by Feature** giúp nhóm quyết định **thứ tự, nhóm triển khai, trách nhiệm kỹ thuật và dự báo**. FDD truyền thống có vai trò Chief Programmer, kế hoạch theo từng feature hoặc nhóm feature và cơ chế class ownership; khi ứng dụng hiện đại, tổ chức có thể điều chỉnh cách phối hợp mà không đánh mất mục đích.

### 7.1. Ưu tiên không chỉ theo thứ tự trên sơ đồ

Những tiêu chí cần xem:

- **Giá trị người dùng:** Feature nào cho phép khách hoàn tất tác vụ hoặc giải quyết vấn đề thật?
- **Rủi ro miền:** Bất biến hay quy tắc nào nếu hiểu sai sẽ gây lỗi nghiêm trọng?
- **Chi phí trì hoãn:** Có ngày bắt buộc hoặc hậu quả nếu để sau không?
- **Phụ thuộc:** Feature nào cần hành vi nền, API đối tác, dữ liệu hoặc quyết định chuyên môn?
- **Bằng chứng:** Điều gì đã kiểm chứng, điều gì là giả định?
- **Khả năng chia nhỏ:** Có thể giao lát cắt trước để học mà không làm giảm chất lượng?
- **Năng lực thực tế:** Ai hiểu những lớp/miền liên quan và có khả năng phối hợp?

Một feature rủi ro cao như “trả kết quả nhất quán khi retry” có thể nên thực hiện sớm trước khi mở rộng quy mô. Một feature trang trí dễ làm không tự động có ưu tiên cao chỉ vì có thể đóng nhanh.

### 7.2. Bảng lập kế hoạch minh họa

| ID | Feature | Giá trị/rủi ro | Phụ thuộc | Quyết định ban đầu |
| --- | --- | --- | --- | --- |
| **F01** | Xác định giờ khả dụng của chuyên gia | Cốt lõi của tác vụ đặt lịch | Quy tắc lịch làm việc và múi giờ | Làm sớm; kiểm chứng với ví dụ miền. |
| **F02** | Tạo lịch hẹn hợp lệ | Tạo giá trị trực tiếp | F01 và cơ chế nhất quán khi lưu | Làm lát cắt nhỏ sau khi hiểu bất biến. |
| **F03** | Trả kết quả nhất quán khi retry | Ngăn trùng dữ liệu | Hợp đồng API/đối tác, thiết kế giao dịch | Khảo sát rủi ro sớm, thực hiện cùng luồng đặt lịch. |
| **F04** | Hiển thị trạng thái xác nhận | Giảm nhầm lẫn khi mạng chậm | F02/F03 và trạng thái miền | Giao sớm cùng thử nghiệm người dùng. |
| **F05** | Gửi SMS xác nhận | Tiện ích bổ sung | F02, nhà cung cấp thông báo | Cân nhắc sau khi luồng lõi ổn định. |
| **F06** | Đổi lịch đã xác nhận | Giá trị lớn nhưng quy tắc phức tạp | Chính sách đổi/hủy, khả năng API | Spike/timebox trước khi cam kết thiết kế lớn. |

Đây là **dự báo giả định**, không phải backlog thực. Kế hoạch cần được xem lại khi người dùng, chuyên gia miền hoặc kết quả tích hợp cho thấy giả định sai. Không biến “Plan by Feature” thành lệnh cấm thay đổi thứ tự sau khi đã phân công.

### 7.3. Kế hoạch feature khác danh sách nhiệm vụ cá nhân

Một feature có thể chạm UI, ứng dụng, domain, lưu trữ và kiểm thử. Lập kế hoạch theo feature giúp mọi người thấy **kết quả chung cần hoàn tất**, thay vì giao riêng từng tầng mà không ai chịu trách nhiệm kết quả end-to-end.

Tuy nhiên, người điều phối phải nhận biết điểm nghẽn: nếu ba feature cùng cần thay đổi một class có một chủ sở hữu, tổng thời gian không chỉ bằng tổng giờ code độc lập. Nên xem **lịch phối hợp, review, tích hợp và năng lực class owner** trước khi lập dự báo.

### 7.4. Không dùng “phần trăm thiết kế xong” như bằng chứng giá trị đã giao

Tiến độ theo FDD có thể được theo dõi qua các mốc thiết kế, kiểm tra thiết kế, code, kiểm tra code và đưa vào build; đây là **tín hiệu quy trình**, không tự động là outcome. Một feature mới chỉ thiết kế xong chưa cho người dùng khả năng mới. Nên tách:

- **Trạng thái tiến độ kỹ thuật** — bước nào đã thực hiện và kiểm tra?
- **Tình trạng feature hoàn tất** — đã kiểm chứng hành vi và tích hợp tới mức nào?
- **Kết quả người dùng** — đã giao và có bằng chứng đem lại giá trị chưa?

Nếu tổ chức dùng phần trăm hoặc milestone để lập báo cáo, cần ghi **định nghĩa rõ ràng**, không kết luận “90% Done” nghĩa là chắc chắn chỉ còn 10% thời gian khi rủi ro tích hợp chưa giải quyết.

## 8. Design by Feature: thiết kế một lát cắt từ mô hình miền

**Design by Feature** tập trung vào một nhóm feature đủ nhỏ. Những người hiểu các lớp và quy tắc liên quan cùng làm rõ tương tác, trách nhiệm và cách bảo vệ bất biến. Trong FDD truyền thống, **Chief Programmer** tổ chức nhóm feature (*feature team*) thường gồm các **class owners** của những lớp liên quan; nhóm có thể thực hiện walkthrough, mô hình tương tác và **design inspection** trước khi xây dựng.

Mục tiêu không phải biến mọi thay đổi thành cuộc duyệt sơ đồ dài. Thiết kế cần **đủ rõ để tránh hiểu sai nghiệp vụ và giảm rủi ro tích hợp**, nhất là khi một feature đi qua nhiều phần hệ thống.

### 8.1. Từ feature sang hành vi và các lớp cộng tác

Ví dụ feature **F02 — Tạo lịch hẹn hợp lệ cho khách**.

**Điều kiện đầu vào cần hỏi:**

- Customer là ai? Có được đặt lịch cho người khác không?
- Consultant và khung giờ được xác định thế nào?
- Có trạng thái **Pending** hay chỉ tạo **Confirmed**?
- Nếu hai người chọn cùng giờ đồng thời, ai được nhận?
- Nếu request bị gửi lại, có tạo lịch thứ hai không?
- Nếu thông báo lỗi sau khi lịch đã tạo, lịch còn hiệu lực không?

| Thành phần | Trách nhiệm nghiệp vụ | Điều cần tránh |
| --- | --- | --- |
| **BookingCommand / BookingRequest** | Biểu diễn ý định của khách và khóa nhận diện lần gửi. | Trộn lẫn yêu cầu đặt lịch với kết quả đã xác nhận. |
| **BookingPolicy** | Kiểm tra điều kiện đặt/hủy, thời gian và quyền liên quan. | Chỉ kiểm tra ở UI mà bỏ cơ chế bảo vệ ở server. |
| **Appointment** | Biểu diễn lịch hẹn, trạng thái và các chuyển trạng thái hợp lệ. | Dùng các cờ boolean rời rạc dễ tạo trạng thái mâu thuẫn. |
| **BookingApplication Service** | Điều phối yêu cầu qua những thành phần cần thiết. | Chứa mọi quy tắc miền trong một hàm khổng lồ. |
| **Appointment Repository/Storage** | Lưu và truy vấn trạng thái nhất quán. | Dùng “đọc xem còn trống rồi lưu” mà không bảo vệ cạnh tranh. |
| **Notification adapter** | Thông báo dựa trên kết quả đã xác nhận. | Coi email đã gửi là điều kiện duy nhất xác định lịch hợp lệ. |

Tên lớp chỉ để minh họa; nhóm có thể chọn tổ chức khác nếu mô hình và yêu cầu khác. FDD quan tâm **feature có kết quả, thiết kế phản ánh miền** chứ không buộc mọi dự án dùng những tên lớp mẫu.

### 8.2. Biểu đồ tương tác một feature

~~~mermaid
sequenceDiagram
    actor K as Khách
    participant UI as Giao diện
    participant A as Booking Application
    participant P as Booking Policy
    participant R as Kho lưu lịch
    participant N as Notification

    K->>UI: Chọn giờ và xác nhận đặt lịch
    UI->>A: Gửi yêu cầu kèm mã idempotency
    A->>P: Kiểm tra quy tắc đặt lịch
    P-->>A: Điều kiện nghiệp vụ
    A->>R: Thử giữ chỗ/lưu lịch nhất quán
    alt Được chấp nhận
        R-->>A: ID lịch và trạng thái đã lưu
        A-->>UI: Kết quả xác nhận
        A-->>N: Yêu cầu thông báo sau commit
    else Trùng hoặc không hợp lệ
        R-->>A: Lý do từ chối
        A-->>UI: Kết quả từ chối rõ ràng
    end
    UI-->>K: Hiển thị trạng thái thực tế
~~~

**Giới hạn của sơ đồ:** “Thử giữ chỗ/lưu lịch nhất quán” là hành vi **phải được hiện thực** bằng cơ chế phù hợp (ràng buộc dữ liệu, transaction hoặc điều phối nhất quán). Mũi tên không giải quyết race condition. Nếu dùng API đối tác cần xác minh hợp đồng, retry và đối soát timeout. Việc gửi notification sau commit có thể cần **outbox hoặc cơ chế giao tin đáng tin**, chứ không thể giả định một transaction cơ sở dữ liệu bao trùm email bên ngoài.

### 8.3. Quy tắc nghiệp vụ chuyển thành kiểm thử chấp nhận

~~~gherkin
Feature: Đặt lịch tư vấn hợp lệ

  Scenario: Khách chọn giờ còn trống
    Given chuyên gia có một khung giờ cho phép đặt
    And chưa có lịch đã xác nhận xung đột với khung giờ đó
    When khách gửi một yêu cầu đặt lịch hợp lệ
    Then hệ thống trả kết quả đã xác nhận
    And tồn tại đúng một lịch có hiệu lực tương ứng

  Scenario: Hai khách cùng chọn một khung giờ chỉ đủ một chỗ
    Given một khung giờ chỉ chấp nhận một lịch đã xác nhận
    When hai khách gửi yêu cầu cạnh tranh đồng thời
    Then tối đa một yêu cầu được xác nhận
    And hệ thống không lưu hai lịch đã xác nhận xung đột

  Scenario: Khách gửi lại cùng một yêu cầu sau timeout
    Given hệ thống đã chấp nhận yêu cầu với mã nhận diện R1
    When khách gửi lại yêu cầu tương đương với mã R1
    Then hệ thống trả kết quả nhất quán với lần đã xử lý
    And không tạo thêm một lịch hẹn thứ hai
~~~

Đây là **đặc tả hành vi minh họa**, chưa phải test tự động của một dự án thật. Nó giúp chuyên gia nghiệp vụ và Developers cùng xác định điều phải đúng. Khi áp dụng, còn phải xem quyền truy cập, hết hạn, múi giờ, trạng thái chưa xác định, mất kết nối và quy tắc đối tác.

### 8.4. Review thiết kế theo rủi ro

Một **design inspection** nên tập trung vào:

1. Các thuật ngữ/feature có cùng nghĩa trong nhóm không?
2. Ai chịu trách nhiệm duy trì bất biến quan trọng?
3. Tương tác giữa lớp/dịch vụ có tạo phụ thuộc vòng hoặc chỗ khó kiểm thử không?
4. Điều gì xảy ra khi lỗi mạng, retry, timeout, dữ liệu cũ hoặc truy cập đồng thời?
5. Có thể tích hợp và kiểm chứng lát cắt độc lập, an toàn không?
6. Có cần cập nhật mô hình tổng thể vì phát hiện quy tắc mới không?

Không cần một sơ đồ UML dài cho mọi feature. Đôi khi ba ví dụ nghiệp vụ, một phác thảo tương tác và vài test là đủ; feature giao dịch phức tạp có thể cần phân tích sâu hơn.

## 9. Build by Feature: hiện thực, kiểm tra và tích hợp thường xuyên

Sau thiết kế đủ dùng, **Build by Feature** biến một feature thành phần mềm hoạt động được. FDD truyền thống có các bước **code, code inspection, unit testing và promote to build**; đội hiện đại có thể bổ sung CI, kiểm thử tự động, triển khai an toàn và quan sát sản phẩm.

### 9.1. Dấu hiệu feature thực sự hoàn tất

- [ ] Hành vi và các trường hợp chấp nhận đã được thống nhất với người hiểu miền.
- [ ] Code cần thiết trong các lớp liên quan đã được tích hợp.
- [ ] Kiểm tra thiết kế và code ở mức phù hợp rủi ro đã được thực hiện.
- [ ] Kiểm thử đơn vị, tích hợp và các bất biến trọng yếu đạt.
- [ ] Không có thay đổi mới phá các feature đang hoạt động.
- [ ] Có thể trình diễn hoặc kiểm chứng trong môi trường phù hợp.
- [ ] Trạng thái công việc và rủi ro còn lại được trình bày trung thực.

Nếu nhóm dùng Scrum, các mục đóng góp vào Increment còn phải đáp ứng **Definition of Done**. **DoD là commitment của Increment trong Scrum**, không phải một thành phần được FDD tự định nghĩa với cùng tên và cấu trúc. Nhóm thuần FDD vẫn cần chuẩn chất lượng rõ cho feature và build.

### 9.2. Ví dụ pseudocode bảo vệ bất biến

~~~java
// Mã minh họa ý tưởng, không phải chương trình chạy độc lập.
BookingResult book(BookingCommand command) {
    validateIdentityAndPermission(command);
    BookingPolicy policy = policyFor(command.consultantId());
    policy.validateRequestedTime(command.timeRange());

    // Cần cơ chế nhất quán tại nơi lưu dữ liệu có thẩm quyền:
    // transaction, constraint hoặc giao thức điều phối phù hợp.
    BookingResult saved = bookingRepository.reserveAtomically(
        command.idempotencyKey(),
        command.customerId(),
        command.consultantId(),
        command.timeRange()
    );

    // Gửi thông báo sau commit có retry/đối soát nếu cần.
    notificationDispatcher.enqueueAfterCommit(saved);
    return saved;
}
~~~

Điểm dạy học không nằm ở tên phương thức **reserveAtomically**. Nó nằm ở việc **bất biến “không tạo trùng” phải được bảo vệ tại ranh giới xử lý thực sự có thẩm quyền**, không chỉ qua một kiểm tra giao diện. Trong hệ phân tán, một hàm có tên “atomically” không đủ chứng minh tính nguyên tử giữa các dịch vụ; triển khai phải có cơ chế và kiểm thử tương ứng.

### 9.3. Tích hợp thường xuyên và phản hồi nhanh

**Đường đi mong muốn:** Một feature nhỏ được thiết kế, code, review, kiểm thử và đưa vào build đủ sớm để những feature khác có thể dựa trên hành vi đã được chứng minh.

Nếu nhóm tạo mười nhánh lớn, mỗi nhánh sửa cùng mô hình miền trong nhiều tuần rồi mới merge, lợi ích của chia feature nhỏ sẽ biến mất. **Continuous integration (CI)**, kiểm thử hồi quy, hợp đồng API và các thay đổi nhỏ giúp phát hiện xung đột sớm.

Nhưng **integration** khác **release**. Feature đạt chuẩn và được tích hợp không tự động có nghĩa đã mở cho người dùng production. Với sản phẩm có ràng buộc bảo mật và vận hành, phải tuân thủ điều kiện phát hành và theo dõi sau giao.

### 9.4. Feature hoàn tất nhưng người dùng chưa nhận giá trị

Một nhóm xây xong feature “gửi xác nhận lịch” nhưng khách không nhận email vì hệ thống thông báo chưa cấu hình production. Kết quả nội bộ có giá trị hạn chế. Nên theo dõi:

| Tầng | Câu hỏi |
| --- | --- |
| **Hoàn tất feature** | Chức năng hoạt động, đã kiểm tra và tích hợp theo chuẩn chưa? |
| **Cung cấp dịch vụ** | Đã được phát hành, giám sát và hỗ trợ an toàn chưa? |
| **Outcome** | Người dùng hiểu xác nhận, ít cần hỗ trợ và ít gặp lỗi hơn không? |

FDD mạnh về tổ chức **các kết quả chức năng nhỏ và tiến độ xây dựng**. Nhóm nên bổ sung **đo outcome người dùng** để tránh danh sách feature Done nhưng ít giá trị thực.

## 10. Feature team, Chief Programmer và class ownership

Đặc điểm của FDD truyền thống là tổ chức **feature team linh hoạt** dưới sự phối hợp của **Chief Programmer**, với vai trò **class owner** đối với những lớp trong mô hình. Mục đích là duy trì hiểu biết sâu về lớp và phối hợp nhiều người để hoàn tất feature.

### 10.1. Những vai trò thường gặp

| Vai trò | Trách nhiệm điển hình | Lưu ý |
| --- | --- | --- |
| **Domain Expert** | Giải thích khái niệm và quy tắc thực tế của nghiệp vụ. | Không thay việc kiểm chứng người dùng cuối khi nhu cầu chưa rõ. |
| **Chief Architect** | Giữ mô hình tổng thể và hướng kiến trúc nhất quán. | Không cần thiết kế mọi chi tiết tương lai trước. |
| **Development Manager** | Điều phối năng lực, tiến độ và trở ngại quá trình phát triển. | Không tối ưu mức bận rộn cá nhân bất chấp dòng giá trị. |
| **Chief Programmer** | Điều phối thiết kế/xây dựng theo feature và lập feature team. | Không tự thay người quyết định giá trị sản phẩm. |
| **Class Owner** | Hiểu sâu, chịu trách nhiệm chất lượng/thay đổi những class được giao. | Có thể thành điểm nghẽn nếu quyền sở hữu quá cứng. |
| **Feature Team** | Người liên quan phối hợp thiết kế, code, kiểm tra một nhóm feature. | Cấu hình thay đổi theo feature và các lớp bị ảnh hưởng. |
| **Tester, Build/Release Engineer và các chuyên môn hỗ trợ** | Bảo vệ kiểm thử, tích hợp và khả năng đưa sản phẩm vào sử dụng. | Cách phân nhiệm có thể khác theo tổ chức. |

FDD cổ điển mô tả thêm nhiều vai trò cụ thể. Bảng này không phải sơ đồ nhân sự bắt buộc; điều quan trọng là **ai bảo đảm tính đúng của mô hình, ai phối hợp feature, ai hiểu nghiệp vụ và ai chịu trách nhiệm với build**.

### 10.2. Feature team hình thành theo nhu cầu feature

Với **“Xác định giờ có thể đặt của chuyên gia”**, nhóm cần người hiểu Consultant, Appointment, BookingPolicy và kiểm thử phù hợp. Với **“Gửi thông báo xác nhận”**, nhóm cần người hiểu Appointment, Notification và cơ chế giao tin.

~~~text
Feature F01: Xác định giờ có thể đặt
  |-- Người hiểu Consultant và lịch làm việc
  |-- Người hiểu Appointment và quy tắc xung đột
  |-- Người thiết kế API/UI và kiểm thử liên quan
  +-- Chief Programmer phối hợp kết quả, design/build inspection

Feature F04: Hiển thị trạng thái xác nhận
  |-- Người hiểu Appointment: Pending, Confirmed
  |-- Người hiểu API và xử lý retry
  |-- Người thiết kế giao diện/trải nghiệm
  +-- Người kiểm thử, tích hợp và phát hành liên quan
~~~

Thay vì team UI làm toàn bộ màn hình rồi đẩy cho backend cuối kỳ, feature team phối hợp **phục vụ một hành vi**. Đừng tan nhóm ngay khi viết xong code nếu feature còn chưa kiểm thử và tích hợp.

### 10.3. Lợi ích và rủi ro của class ownership

**Individual class ownership** trong FDD truyền thống có thể:

- Giữ người hiểu sâu về một lớp và bất biến liên quan.
- Giảm thay đổi mâu thuẫn khi nhiều feature cùng tác động một lớp.
- Có đầu mối chịu trách nhiệm về tính nhất quán và kiểm tra thay đổi.
- Giúp Chief Programmer tập hợp những người cần tham gia feature team.

Nhưng nó cũng có đánh đổi:

- Một class owner có thể thành nút thắt review/chỉnh sửa.
- Nếu người đó vắng, các feature phụ thuộc bị chặn.
- Kiến thức bị tập trung, khó chia sẻ.
- Những feature sửa cùng class tạo lịch phối hợp phức tạp.

Quyền sở hữu lớp nên bảo vệ **chất lượng và trách nhiệm**, không biến thành độc quyền cứng làm tắc dòng giá trị. Một nhóm hiện đại có thể có người chịu trách nhiệm chính nhưng dùng pairing, reviewer dự phòng và tri thức chung. Nếu điều chỉnh cách làm khác FDD truyền thống, nên nói rõ để mọi người hiểu cơ chế trách nhiệm.

### 10.4. FDD và XP khác nhau ở sở hữu mã

| Khía cạnh | FDD truyền thống | XP phổ biến |
| --- | --- | --- |
| **Sở hữu code** | Thường gắn class owner với class cụ thể. | **Collective code ownership**: nhiều người có thể cải tiến code chung với trách nhiệm chất lượng. |
| **Phối hợp** | Feature team tạm thời, tập hợp người liên quan theo feature. | Pair programming và cộng tác kỹ thuật thường xuyên. |
| **Giữ nhất quán** | Người hiểu sâu lớp, walkthrough, inspection và build. | TDD, CI, refactoring, coding standards và phản hồi nhanh. |
| **Rủi ro** | Nút thắt owner, phụ thuộc cá nhân nếu không dự phòng. | Thay đổi thiếu hiểu biết nếu thiếu test, trao đổi và kỷ luật. |

Không cần tuyên bố một cách **luôn tốt hơn**. Miền phức tạp cần người hiểu sâu, nhưng quyền sửa quá tập trung dễ hạn chế việc giao; chọn cơ chế **giữ tri thức mà không khóa dòng giá trị**.

### 10.5. Nhóm nhỏ có cần đủ mọi vai trò?

Không nhất thiết. Một nhóm ít người có thể để một người đảm nhiệm nhiều trách nhiệm, miễn là có cách làm rõ nghiệp vụ, giữ mô hình nhất quán, kiểm tra chất lượng và tích hợp. **FDD không nên tạo bộ máy vai trò phức tạp hơn vấn đề cần giải quyết.**

## 11. Tình huống xuyên suốt: mô hình miền thay đổi khi có bằng chứng mới

Tình huống sau minh họa vì sao **mô hình miền** không chỉ phục vụ bước thiết kế đầu tiên mà còn giúp nhóm phản ứng khi giả định bị bác bỏ. Đây là **ví dụ giáo dục**, không phải dữ liệu dự án thật.

### 11.1. Hiểu biết ban đầu

Nhóm hình dung hành vi đặt lịch:

~~~text
Khách chọn giờ
    -> Hệ thống thấy giờ trống
    -> Tạo lịch ở trạng thái Confirmed
    -> Gửi email thông báo
~~~

Danh sách feature ban đầu có “Hiển thị giờ trống”, “Tạo lịch” và “Gửi xác nhận”. Đội đã dựng được luồng đơn giản trên sandbox.

### 11.2. Bằng chứng mới xuất hiện

Trong thử nghiệm tích hợp:

1. API đối tác đôi khi trả timeout **sau khi đã tiếp nhận yêu cầu**.
2. Một số phiên phải được đối tác phê duyệt, nên không thể lập tức coi là **Confirmed**.
3. Người dùng thường nhấn gửi lại khi trạng thái chưa rõ.
4. Việc gửi lặp có thể tạo hai lịch nếu thiết kế không bảo vệ đúng.

Chỉ thêm spinner vào UI **không** bảo đảm hệ thống không lưu hai lịch. Giả định miền “mọi request thành công đều Confirmed ngay” đã sai.

### 11.3. Cập nhật mô hình trạng thái

~~~mermaid
stateDiagram-v2
    [*] --> Pending : Nhận yêu cầu
    Pending --> Confirmed : Xác nhận thành công
    Pending --> Rejected : Không đáp ứng điều kiện
    Pending --> Expired : Hết thời gian chờ
    Confirmed --> Cancelled : Hủy hợp lệ
    Rejected --> [*]
    Expired --> [*]
    Cancelled --> [*]
~~~

Sơ đồ là **giả thuyết mô hình**. Thực tế có thể có hoàn tiền, chấp nhận thủ công hoặc tái thử. Chuyển trạng thái cần được chuyên gia miền xác nhận và đối chiếu hợp đồng API. **Expired ở hệ thống nội bộ không tự bảo đảm đối tác chưa tạo lịch**; phải có quy tắc đối soát khi kết quả chưa xác định.

**Các bất biến cần xem lại:** Pending có giữ chỗ không? Một yêu cầu đang chờ được tính vào khả dụng như thế nào? Có thể hoàn tất phê duyệt sau timeout không? Mã idempotency được giữ bao lâu và ai quản lý? Nếu hủy để đổi lịch, làm sao tránh giải phóng chỗ trước khi phương án mới được xác nhận?

### 11.4. Danh sách feature được cập nhật theo mô hình

| Feature trước | Điều mới hiểu | Feature/tiêu chí cập nhật |
| --- | --- | --- |
| Tạo lịch hẹn | Có bước chờ phê duyệt. | “Tạo yêu cầu đặt lịch ở trạng thái Pending” và “Xác nhận yêu cầu khi đối tác chấp nhận”. |
| Trả kết quả xác nhận | Timeout có thể tạo kết quả chưa rõ. | “Hiển thị trạng thái đang xử lý” và “Đối soát kết quả của yêu cầu”. |
| Chống đặt trùng | Retry có thể tạo thêm lịch. | “Trả kết quả nhất quán khi gửi lại cùng yêu cầu”, với bảo vệ khi lưu. |
| Gửi email | Không nên báo Confirmed khi mới Pending. | “Thông báo xác nhận chỉ sau khi lịch thật sự được chấp nhận”. |

Nhóm không chỉ **thêm ticket sửa lỗi**. Họ sửa cách hiểu miền, các tính năng phụ thuộc, tiêu chí kiểm chứng và kế hoạch.

### 11.5. Thiết kế và xây lại theo feature nhỏ

Một lựa chọn có thể là:

1. **Spike một ngày:** Thử API đối tác với timeout, gửi lặp và truy vấn trạng thái.
2. **Feature F02a:** Ghi nhận yêu cầu ở trạng thái Pending với mã nhận diện nhất quán.
3. **Feature F03a:** Xử lý gửi lại cùng yêu cầu không tạo trùng.
4. **Feature F04a:** Hiển thị Pending/Confirmed/Rejected rõ cho người dùng.
5. **Feature F04b:** Đối soát kết quả sau timeout có kiểm thử.
6. **Feature thông báo:** Chỉ gửi thông điệp “đã xác nhận” khi trạng thái phù hợp.

Không bắt buộc làm theo đúng thứ tự nếu rủi ro hoặc phụ thuộc khiến phương án khác tốt hơn. Điều quan trọng là **mỗi lát cắt có hành vi đúng, được kiểm chứng**, thay vì sửa một gói rất lớn mà không có phản hồi.

### 11.6. Có được sửa mô hình sau khi đã viết code không?

**Có, khi bằng chứng cho thấy hiểu biết miền cần đổi.** Đóng băng mô hình ban đầu sẽ làm FDD mất tính thích ứng. Tuy nhiên, sửa mô hình cần đánh giá:

- Những feature đã xây nào bị ảnh hưởng?
- Bất biến nào phải kiểm thử hồi quy?
- Có dữ liệu cũ phải chuyển đổi không?
- API và người dùng nào phụ thuộc vào nghĩa cũ?
- Ai thông báo cách hiểu mới và cập nhật feature list?

Khi đó, mô hình miền trở thành **cơ chế phối hợp thay đổi**, không chỉ là sơ đồ để ký duyệt.

## 12. Đo tiến độ FDD mà không tối ưu cục bộ

FDD có truyền thống theo dõi tiến độ theo feature và các mốc thiết kế/xây dựng. Điều này hữu ích cho việc phối hợp nhiều nhóm, nhưng **tiến độ kỹ thuật không tự đồng nghĩa giá trị đã đến tay người dùng**.

### 12.1. Ba lớp đo lường

| Góc nhìn | Chỉ số/tín hiệu | Câu hỏi |
| --- | --- | --- |
| **Hoàn tất feature** | Số feature đạt chuẩn, trạng thái thiết kế/xây/kiểm tra, việc bị chặn. | Hạng mục nào thật sự hoàn tất, hạng mục nào còn rủi ro? |
| **Dòng công việc** | Lead time, cycle time, throughput, WIP, work item age, chờ owner/review. | Giá trị đang mắc ở đâu và dự báo có đáng tin không? |
| **Outcome/chất lượng** | Tỷ lệ đặt lịch thành công, lỗi trùng, thời gian khôi phục, phản hồi khách. | Feature có giải quyết đúng nhu cầu và ổn định không? |

Nếu nhóm báo “40/50 feature đã hoàn tất”, cần hỏi **các feature có kích thước tương tự không, mười feature còn lại có phức tạp hơn không, có đang chờ tích hợp hay kiểm thử không, và mục tiêu người dùng đã đạt đến đâu?**

### 12.2. Bảng tiến độ ví dụ

| ID | Feature | Trạng thái | Bằng chứng còn thiếu hoặc cần theo dõi |
| --- | --- | --- | --- |
| **F01** | Xác định giờ khả dụng | **Done** | Test múi giờ đã đạt; tiếp tục theo dõi dữ liệu sau phát hành. |
| **F02** | Tạo lịch hợp lệ | **Build/Integration** | Chưa đạt kiểm thử hai yêu cầu đồng thời. |
| **F03** | Trả kết quả nhất quán khi retry | **Design** | Cần kết quả spike API đối tác. |
| **F04** | Hiển thị xác nhận rõ | **Ready** | Cần trạng thái miền thống nhất với F02/F03. |
| **F05** | Gửi SMS | **Backlog** | Chưa có bằng chứng ưu tiên hơn độ tin cậy luồng đặt lịch. |

Bảng chỉ là ví dụ; trạng thái phải phản ánh workflow thực tế. Một feature chưa đạt chuẩn **không phải Done** vì đã viết code hoặc demo giao diện. Không có quy định FDD bắt buộc đúng năm trạng thái như trên.

### 12.3. Công việc đang mở cần được đo

Nếu chỉ tính cycle time của feature **đã Done**, những feature phức tạp đang chờ class owner có thể bị che. Nên xem **work item age** và điểm blocked, đặc biệt những feature chạm nhiều lớp hoặc phụ thuộc đối tác.

Không nên yêu cầu class owner bỏ kiểm tra bất biến để tăng số lượng feature hoàn tất. Hãy xem **phân bổ tri thức, phụ thuộc, WIP và khả năng giúp nhau hoàn tất**.

### 12.4. Milestone không phải phép nội suy phần trăm chính xác

Một feature đã qua design inspection nhưng chưa thử với dữ liệu thật có thể vẫn mang rủi ro cao. Thay vì khẳng định “đã xong 80%”, hãy báo:

> “Thiết kế và unit test đã hoàn tất. Còn chặn ở kiểm thử cạnh tranh đồng thời và hợp đồng API; cần kết quả hai việc này trước khi xác nhận feature đủ điều kiện giao.”

**Trạng thái có bằng chứng** thường hữu ích hơn phần trăm thiếu cơ sở. Nếu tổ chức dùng hệ milestone/điểm trọng số truyền thống của FDD, phải giải thích rằng chúng biểu thị **tiến độ quy trình**, không thay thế kết quả dùng được.

## 13. Khi nào FDD phù hợp và khi nào cần điều chỉnh?

### 13.1. Tình huống có thể phát huy điểm mạnh

- **Miền có nhiều quy tắc và khái niệm liên quan:** bảo hiểm, ngân hàng, hậu cần hoặc đặt lịch phức tạp.
- **Nhiều người cần hiểu chung nghiệp vụ:** mô hình làm giảm sai lệch giữa các bộ phận.
- **Cần cấu trúc feature và dự báo rõ:** có thể phân rã chức năng, lập kế hoạch và theo dõi phần hoàn tất.
- **Thiết kế đối tượng phù hợp:** có thể tổ chức trách nhiệm theo lớp, phối hợp feature teams.
- **Có chuyên gia miền để kiểm chứng:** không chỉ để nhóm kỹ thuật tự suy đoán yêu cầu.

### 13.2. Bối cảnh cần thận trọng

| Bối cảnh | Rủi ro khi áp dụng FDD máy móc | Điều chỉnh có thể hữu ích |
| --- | --- | --- |
| **Sản phẩm mới, nhu cầu còn bất định** | Mô hình quá chi tiết cho nhu cầu có thể đổi sau vài ngày. | Discovery, prototype, lát cắt học sớm; chỉ mô hình phần cần thiết. |
| **Nhóm nhỏ và thay đổi rất nhanh** | Vai trò và inspection cứng tăng chi phí phối hợp. | Giữ mô hình chung đơn giản, review theo mức rủi ro. |
| **Đội vận hành nhận công việc ngẫu nhiên** | Feature list không xử lý tốt dòng sự cố. | Bổ sung Kanban pull/WIP và chính sách sự cố; dùng FDD cho feature phù hợp. |
| **Hệ thống nhiều dịch vụ và API ngoài** | Class model nội bộ không phản ánh thất bại phân tán. | Mô hình hợp đồng, trạng thái, kiểm thử tích hợp và đối soát. |
| **Class ownership quá tập trung** | Nghẽn review và phụ thuộc cá nhân. | Pairing, tri thức chung, owner dự phòng và WIP hợp lý. |
| **Tổ chức dùng Scrum đầy đủ** | Hai hệ thống cam kết và trạng thái chồng chéo. | Dùng mô hình miền/feature list trong refinement, giữ Sprint Goal/DoD. |

Không có quy tắc “dự án lớn bắt buộc dùng FDD” hoặc “FDD không thể dùng cho nhóm nhỏ”. Cần xem **bài toán, mức bất định, năng lực thực và lợi ích của mô hình**.

### 13.3. Câu hỏi trước khi chọn

1. Các thành viên có đang hiểu khác nhau về quy tắc miền quan trọng?
2. Yêu cầu có thể chia thành hành vi nhỏ có giá trị và kiểm chứng được?
3. Có chuyên gia miền để xem mô hình thường xuyên không?
4. Có thể giữ thiết kế, kiểm thử và tích hợp theo từng feature?
5. Class ownership giúp nhất quán hay tạo nút thắt?
6. Mô hình tổng thể cần nhẹ đến mức nào để phản hồi không bị chậm?
7. Phản hồi từ sản phẩm và vận hành sẽ quay về mô hình và feature list bằng cách nào?

**Có thể chọn một số thực hành FDD mà không áp dụng nguyên cả bộ quy trình.** Quan trọng là công khai lựa chọn, trách nhiệm và tiêu chuẩn hoàn tất.

## 14. FDD so với Scrum, Kanban, XP và Domain-Driven Design

Những tên gọi này có thể được nhắc chung trong Agile nhưng **không ở cùng tầng khái niệm**.

| Cách tiếp cận | Trọng tâm | Khái niệm/thực hành nổi bật | Không nên đồng nhất với |
| --- | --- | --- | --- |
| **FDD** | Mô hình miền và phát triển theo feature nhỏ. | Năm quy trình, overall model, feature list, design/build by feature, feature team, class owner. | Bắt buộc Sprint hoặc quản lý WIP theo Kanban. |
| **Scrum** | Framework thực nghiệm để tạo và thích ứng sản phẩm phức tạp. | Product Goal, Sprint Goal, Increment/DoD, ba accountabilities và các sự kiện. | Một phương pháp thiết kế class hoặc feature list cố định. |
| **Kanban** | Định nghĩa và tối ưu dòng công việc. | Workflow, WIP, pull, cycle time, throughput, work item age, SLE. | Mọi đội phải có Sprint hoặc class ownership. |
| **XP** | Phản hồi kỹ thuật và chất lượng khi thay đổi. | TDD, CI, refactoring, pairing, small releases. | Mô hình đối tượng tổng thể bắt buộc. |
| **Domain-Driven Design (DDD)** | Hiểu miền phức tạp để dẫn dắt thiết kế phần mềm. | Ubiquitous Language, bounded context, entity, value object, aggregate khi phù hợp. | FDD: DDD không phải tên khác của năm quy trình FDD. |

### 14.1. Mô hình miền trong FDD khác DDD ra sao?

FDD khuyến khích tạo **overall object model** để phát triển feature list và thiết kế. DDD cũng đặt hiểu biết miền và trao đổi với chuyên gia ở vị trí quan trọng, nhưng có **hệ khái niệm thiết kế chiến lược và chiến thuật riêng**. **Bounded context** là khái niệm nổi bật của DDD, không phải tên bước bắt buộc trong FDD.

Nhóm có thể học ngôn ngữ chung và cách phân định vùng miền của DDD khi áp dụng FDD. Nhưng không thể suy ra “dùng FDD bắt buộc phải thiết kế microservice theo bounded context”; đó là lựa chọn kiến trúc riêng, cần cân nhắc dữ liệu và vận hành.

### 14.2. Dùng mô hình và feature list FDD trong Scrum

Một Scrum Team có thể:

1. Dùng **mô hình miền** để làm rõ các Product Backlog Item.
2. Dùng **feature list** để nhận diện chức năng nhỏ và phụ thuộc.
3. Tạo **Sprint Goal** có giá trị trong Sprint Planning.
4. Dùng **Design by Feature** để cùng làm rõ cách triển khai các lát cắt quan trọng.
5. **Build by Feature** với kiểm thử/tích hợp để tạo Increment đạt DoD.
6. Dùng **Sprint Review** lấy phản hồi, cập nhật Product Backlog và mô hình khi cần.

Trong cách phối hợp đó, **Product Owner** vẫn chịu trách nhiệm tối đa hóa giá trị và quản lý hiệu quả Product Backlog; **Developers** tạo Sprint Backlog và giữ chất lượng. Không lập một feature list riêng để âm thầm ghi đè Product Backlog hoặc để Chief Programmer tự thay đổi Sprint Goal khi chưa rõ quyền quyết định.

### 14.3. Dùng Kanban để nhìn dòng của các feature

Một workflow có thể là **Ready → Design → Build → Review/Test → Done**, với WIP limit, chính sách kéo và đo **cycle time/work item age**. Nó giúp thấy feature nào chờ owner, review hoặc đối tác.

Nhưng đừng đồng nhất một feature đã merge với giá trị người dùng đã nhận. Nếu điểm Done chỉ là code đã tích hợp, hãy đo thêm thời gian tới phát hành và outcome.

### 14.4. XP giúp mô hình đúng nhưng vẫn thay đổi an toàn

Mô hình miền và feature list làm rõ **điều gì phải đúng**; XP giúp bảo vệ khả năng thay đổi:

- **TDD:** chuyển ví dụ miền thành kiểm thử để bảo vệ hành vi.
- **CI:** phát hiện xung đột khi nhiều feature tác động cùng lớp.
- **Refactoring:** điều chỉnh cấu trúc khi hiểu biết miền tiến triển.
- **Pair programming:** giảm phụ thuộc vào một class owner.
- **Small releases:** lấy phản hồi sớm khi thỏa điều kiện an toàn.

Không nên lấy “đã vẽ model” làm lý do trì hoãn test, cũng không nên lấy “đã có TDD” làm lý do khỏi cần hỏi chuyên gia miền.

## 15. Những ngộ nhận và phản mẫu khi áp dụng FDD

| Ngộ nhận hoặc phản mẫu | Hệ quả | Hành động nên thử |
| --- | --- | --- |
| **“Mô hình tổng thể phải đầy đủ 100% trước khi viết code.”** | Học từ phần mềm chạy thật quá muộn; mô hình được xây trên giả định. | Mô hình đủ định hướng, ưu tiên quy tắc rủi ro cao, cập nhật khi có bằng chứng. |
| **“Domain model chính là ERD/database schema.”** | Quy tắc nghiệp vụ, trạng thái và bất biến bị ẩn trong service/UI. | Thảo luận khái niệm và hành vi trước, đối chiếu rồi mới thiết kế lưu trữ. |
| **“Một feature là một class, API hoặc bảng.”** | Theo dõi công việc kỹ thuật chứ không theo dõi kết quả có giá trị. | Đặt tên feature bằng hành vi nghiệp vụ, liên kết task kỹ thuật dưới feature. |
| **“Feature list đã duyệt nên không bao giờ được đổi.”** | Xây sản phẩm theo hiểu biết cũ dù nhu cầu đã khác. | Nhận phản hồi, cập nhật mô hình, feature list và thứ tự với trách nhiệm rõ. |
| **“Feature càng nhỏ càng tốt, dù không có kết quả riêng.”** | Quá nhiều ticket vụn, người dùng chưa nhận được giá trị. | Chia đủ nhỏ nhưng giữ khả năng kiểm chứng hành vi và kết quả. |
| **“Chief Programmer quyết định mọi ưu tiên sản phẩm.”** | Quyền giá trị/kinh doanh và quyền kỹ thuật bị lẫn. | Tách trách nhiệm quyết định giá trị, thiết kế, chất lượng và phát hành. |
| **“Class owner là người duy nhất được phép sửa mãi mãi.”** | Nghẽn review, thiếu dự phòng và học hỏi. | Giữ người chịu trách nhiệm, nhưng pairing, mentoring, quyền dự phòng khi phù hợp. |
| **“Design inspection là ký duyệt mọi sơ đồ chi tiết.”** | Chi phí nghi thức cao hơn giá trị kiểm tra. | Tập trung bất biến, rủi ro và tương tác khó; nhẹ hóa khi tính năng đơn giản. |
| **“Build by Feature xong khi code compile.”** | Lỗi tích hợp hoặc nghiệp vụ lọt sang người dùng. | Kiểm chứng tiêu chí, test hồi quy, tích hợp và chuẩn chất lượng rõ. |
| **“100 feature Done chắc chắn tốt hơn 60 feature Done.”** | Đội chia ticket vụn và bỏ qua outcome. | Đo giá trị, loại/độ phức tạp feature, lỗi, flow và việc đang bị chặn. |
| **“Mọi việc kỹ thuật phải ngụy trang thành feature.”** | Nợ kỹ thuật, bảo mật và discovery bị diễn đạt khó hiểu. | Quản lý công việc hỗ trợ chất lượng/rủi ro minh bạch và gắn với mục tiêu. |
| **“FDD là DDD hoặc microservice.”** | Áp dụng thuật ngữ/kiến trúc không cần thiết. | Phân biệt phương pháp phát triển, kỹ thuật mô hình hóa và kiến trúc triển khai. |
| **“FDD loại trừ Scrum, Kanban và XP.”** | Tranh luận nhãn thay vì giải quyết điểm nghẽn. | Kết hợp thực hành có chủ đích, không tạo trách nhiệm hoặc backlog mâu thuẫn. |
| **“Đã có domain model thì không cần gặp người dùng.”** | Có thể hiểu đúng quy tắc cũ nhưng xây sai nhu cầu mới. | Liên tục kiểm tra outcome và học từ phản hồi khách hàng. |

### 15.1. Mô hình được sở hữu bởi cả hiểu biết nghiệp vụ lẫn thiết kế

Nếu sơ đồ miền chỉ được làm bởi một kiến trúc sư mà không có chuyên gia nghiệp vụ, tính nhất quán trên giấy không bảo đảm tính đúng. Ngược lại, chỉ dựa vào cách người dùng mô tả một màn hình có thể thiếu trạng thái, quyền truy cập và trường hợp biên.

**Cách cân bằng:** Người hiểu nghiệp vụ cung cấp ví dụ và quy tắc; Developers mô tả mô hình, chỉ ra mâu thuẫn, thử nghiệm và kiểm chứng các bất biến; cả hai cập nhật ngôn ngữ chung. Mô hình là công cụ **cộng tác**, không phải sản phẩm phụ của phòng kiến trúc.

### 15.2. Chất lượng là điều kiện để feature có ý nghĩa

Ví dụ, feature “tạo lịch hẹn cho khách” chỉ có ích nếu không tạo lịch trùng, không lộ dữ liệu cá nhân và hiển thị trạng thái đúng. Nếu nhóm bỏ kiểm thử cạnh tranh để rút thời gian Build by Feature, kết quả có thể nhanh trên dashboard nhưng gây thiệt hại ngoài thực tế.

**Giao nhanh một feature không đủ chất lượng không phải cải tiến Agile.** Hãy giảm phạm vi ít cần thiết hoặc cải tiến kỹ thuật, không âm thầm hạ chuẩn an toàn.

## 16. Mô hình miền hỗ trợ yêu cầu thích ứng nhưng không thay thế discovery

FDD bắt đầu từ mô hình và danh sách feature, trong khi những nhu cầu sản phẩm mới thường chứa nhiều **giả định chưa được kiểm chứng**. Để không biến mô hình thành bản kế hoạch khóa cứng, nhóm cần đặt câu hỏi về giá trị ngay từ lúc phát hiện một khái niệm mới.

### 16.1. Ba loại điều chưa biết cần xử lý khác nhau

| Loại bất định | Ví dụ | Phương pháp giảm bất định |
| --- | --- | --- |
| **Nhu cầu** | Người dùng có muốn tự đổi lịch hay thường muốn gọi tổng đài? | Quan sát tác vụ, phỏng vấn, thử prototype, đo hành vi. |
| **Quy tắc miền** | Khách được hủy trong vòng bao lâu và khi nào phải hoàn phí? | Trao đổi chuyên gia miền, xem ví dụ thực tế, lập bảng quyết định. |
| **Kỹ thuật/tích hợp** | API có chấp nhận idempotency key và trả trạng thái sau timeout không? | Spike có timebox, thử sandbox, kiểm tra hợp đồng, quan sát giới hạn. |

Một domain model mô tả **cách nhóm hiện hiểu nghiệp vụ**; nó không chứng minh rằng người dùng muốn feature sắp xây, cũng không chứng minh API đối tác hoạt động như giả định. Vì thế phải kết hợp **discovery và kiểm thử** theo loại bất định.

### 16.2. Mẫu spike có giới hạn khi mô hình cần bằng chứng

~~~yaml
question: "API đối tác phân biệt yêu cầu gửi lại ra sao?"
decision_blocked: "Thiết kế trạng thái và cơ chế retry của Appointment"
assumption: "Cùng idempotency key không tạo hai lịch"
timebox: "Tối đa 2 ngày làm việc"
in_scope:
  - "Đọc hợp đồng API"
  - "Thử gửi lặp, timeout và truy vấn lại kết quả trên sandbox"
out_of_scope:
  - "Xây trọn chức năng đổi lịch production"
stop_when: "Đủ bằng chứng để chọn hướng hoặc hết timebox"
deliverable: "Kết quả thử, giới hạn, rủi ro còn lại, quyết định về mô hình và feature"
~~~

Kết quả timebox có thể là **“chưa đủ bằng chứng”**; nhóm phải ghi rõ điều chưa biết và xem có nên đầu tư khảo sát tiếp hay thay phương án. Không coi prototype dùng để khảo sát là feature sản phẩm đã hoàn tất khi chưa đạt tiêu chuẩn.

### 16.3. Quy trình thay đổi mô hình và feature list

~~~mermaid
flowchart TD
    A["Phản hồi người dùng hoặc bằng chứng mới"] --> B["Xác định giả định miền bị ảnh hưởng"]
    B --> C["Trao đổi với chuyên gia và người chịu trách nhiệm"]
    C --> D["Sửa thuật ngữ, quy tắc, mô hình nếu cần"]
    D --> E["Xem các feature và test liên quan"]
    E --> F["Chọn lát cắt tiếp theo theo giá trị/rủi ro"]
    F --> G["Design by Feature rồi Build by Feature"]
    G --> H["Tích hợp, kiểm chứng, giao và đo kết quả"]
    H -. "Học tiếp" .-> A
~~~

Sơ đồ là **vòng phối hợp**, không phải thủ tục phê duyệt bắt buộc cho mọi thay đổi tên biến. Khi sửa một khái niệm trọng yếu như “đã xác nhận”, cần trao đổi đủ rộng để tránh các nhóm dùng hai nghĩa khác nhau. Khi chỉ chỉnh một label giao diện nhỏ, có thể dùng cách làm nhẹ hơn.

### 16.4. Backlog còn chứa nhiều thứ ngoài feature

Sản phẩm thực tế cần sửa lỗi, giảm nợ kỹ thuật, bảo mật, quan sát vận hành, nâng cấp nền tảng và khám phá. Không nên ép mọi việc thành câu “hiển thị kết quả của đối tượng” chỉ để phù hợp danh pháp FDD.

Có thể:

- Giữ **feature list** để tổ chức chức năng có giá trị dựa trên mô hình.
- Giữ công việc chất lượng và kỹ thuật cần thiết **hiển thị minh bạch**, mô tả rủi ro hoặc giá trị mở khóa.
- Nếu dùng Scrum, quản lý công việc cải thiện sản phẩm theo Product Backlog có thứ tự.
- Nếu dùng Kanban, để các loại việc đi qua workflow và chính sách phù hợp, không giấu tải khẩn cấp.

Điều quan trọng là tất cả cùng tiêu thụ **năng lực hữu hạn**, vì vậy quyết định ưu tiên phải nêu chi phí cơ hội và các chuẩn bắt buộc.

## 17. Bài tập tình huống có hướng giải

### Tình huống A — Nhóm có database nhưng chưa có mô hình miền

Đội vừa tạo các bảng Customer, Booking, Slot, Payment. Khi được hỏi “lịch đã được xác nhận khi nào?”, backend nói “sau INSERT”, UI nói “sau khi nhấn Đặt” và QA nói “sau khi nhận email”.

**Câu hỏi:**

1. Vấn đề thực sự là thiếu bảng hay thiếu ngôn ngữ và quy tắc?
2. Cần mời ai để xây overall model?
3. Hãy viết một bất biến và hai ví dụ chấp nhận cần xác minh.

**Hướng giải:** Vấn đề là thiếu định nghĩa nghiệp vụ về trạng thái và điều kiện xác nhận. Cần người hiểu nghiệp vụ, Developers, QA và bên liên quan tới thanh toán/đối tác nếu có. Bất biến ví dụ: “Không có hai lịch đã xác nhận trùng giờ cho một chỗ nếu chính sách không cho phép”. Các kịch bản cần kiểm tra gồm gửi lặp sau timeout và trạng thái khi email lỗi. Bảng dữ liệu có thể phải thay đổi sau khi thống nhất mô hình.

### Tình huống B — Feature list toàn việc kỹ thuật

Nhóm có danh sách “Tạo bảng Booking”, “Code REST API”, “Tạo React component”, “Viết unit test”. Quản lý tuyên bố đã làm xong bốn feature FDD.

**Câu hỏi:**

1. Những mục này có phải feature khách hàng theo nghĩa FDD?
2. Có thể viết lại thành hai hoặc ba feature nghiệp vụ nào?
3. Những việc kỹ thuật ban đầu nằm ở đâu?

**Hướng giải:** Chúng chủ yếu là task kỹ thuật. Có thể viết “Xác định giờ khả dụng của chuyên gia”, “Tạo lịch hẹn hợp lệ cho khách”, “Hiển thị trạng thái xác nhận của lịch hẹn”. Database, API, UI và test trở thành các công việc cần để thực hiện feature. Chỉ coi Done khi hành vi liên quan được kiểm chứng và tích hợp.

### Tình huống C — Một class owner làm chậm bốn feature

F01, F02, F03, F04 đều cần sửa lớp Appointment, chỉ một người được phép sửa. Người đó bận sự cố ba ngày, mọi feature dừng ở trạng thái Review.

**Câu hỏi:**

1. Quyền sở hữu lớp đang mang lại giá trị và rủi ro gì?
2. Làm sao giảm điểm phụ thuộc mà không bỏ tính nhất quán?
3. Nên quan sát chỉ số nào để biết cải tiến thực sự có ích?

**Hướng giải:** Owner có thể giữ chất lượng miền nhưng trở thành nút thắt. Có thể lập pairing, reviewer dự phòng, kiểm thử hợp đồng và ghi rõ bất biến; ưu tiên hoàn tất feature quan trọng thay vì mở thêm nhiều feature. Đo work item age, thời gian chờ, throughput, lỗi hồi quy và khả năng hiểu code của thành viên khác. Không chỉ đánh giá qua số commit của owner.

### Tình huống D — Người dùng thay đổi quy tắc hủy lịch

Ban đầu mô hình cho phép hủy mọi lịch chưa diễn ra. Thử nghiệm người dùng và quy định nghiệp vụ mới cho thấy lịch sát giờ có thể bị tính phí, còn một số loại phiên cần chuyên gia phê duyệt hủy.

**Câu hỏi:**

1. Thành phần mô hình nào cần xem lại?
2. Danh sách feature nào bị ảnh hưởng?
3. Làm sao phát triển một phần nhỏ mà không báo sai phí hủy?

**Hướng giải:** Cần xem BookingPolicy, trạng thái Appointment, khái niệm phí/hủy, quyền phê duyệt và dữ liệu thời gian. Chia feature như “Xác định quyền hủy theo loại phiên và thời điểm”, “Tính khoản phí hủy”, “Ghi nhận yêu cầu hủy cần duyệt”, với ví dụ chấp nhận cho mốc giờ biên. Không mặc định mọi trường hợp sẽ có cùng luồng xác nhận hoặc hoàn tiền.

### Tình huống E — Demo đẹp nhưng feature chưa có giá trị thật

FDD team trình diễn “Tạo lịch” hoạt động trên dữ liệu giả. Khi tích hợp thật, API trả timeout sau khi đã tạo lịch và khách có thể gửi lặp. Nhóm muốn ghi Done vì phần giao diện đã hoàn tất.

**Câu hỏi:**

1. Tại sao code đã chạy trên mock chưa chứng minh feature hoàn tất?
2. Mô hình miền có thiếu trạng thái/bất biến nào?
3. Design by Feature và Build by Feature cần làm gì tiếp?

**Hướng giải:** Mock không chứng minh hợp đồng đối tác trong tình huống lỗi. Cần cập nhật khái niệm Pending/Confirmed/kết quả chưa xác định, idempotency, đối soát; thảo luận với chuyên gia miền, thiết kế tương tác đúng, bổ sung kiểm thử tích hợp và điều kiện hoàn tất. Nếu phát hành còn rủi ro mất dữ liệu, không gọi feature Done hoặc mở rộng người dùng khi chưa đủ điều kiện.

### Tình huống F — Chọn cách tiếp cận cho đội nhận việc liên tục

Một nhóm tám người làm sản phẩm đặt lịch và hỗ trợ sự cố hằng ngày. Miền có nhiều quy tắc, nhưng 30% năng lực bị yêu cầu khẩn chiếm dụng. Quản lý muốn áp dụng FDD bằng việc khóa feature list ba tháng và yêu cầu mọi người theo class owner.

**Câu hỏi:**

1. Phần nào của FDD có thể hữu ích ngay?
2. Có thể bổ sung Kanban và Scrum/XP ở đâu?
3. Vì sao khóa feature list và quyền sửa code cứng có rủi ro?

**Hướng giải:** Mô hình miền và các feature nhỏ giúp hiểu các hành vi phức tạp. Kanban giúp thấy WIP, lỗi khẩn, điểm chặn; XP giúp kiểm thử và tích hợp sớm. Nếu nhóm dùng Scrum cần tôn trọng Sprint Goal/DoD và trách nhiệm Scrum. Feature list phải cập nhật khi phản hồi mới tới, còn class ownership cần dự phòng để không tắc toàn dòng.

## 18. Bài thực hành: từ miền nghiệp vụ tới feature có thể kiểm chứng

### 18.1. Đề bài

Một nền tảng cho phép khách đặt **lịch tư vấn trực tuyến**. Một chuyên gia có lịch làm việc theo ngày; có giờ nghỉ, lịch đã được xác nhận, yêu cầu Pending và khả năng khách đổi/hủy. Người dùng có thể ở múi giờ khác. Nhóm chưa chắc API đối tác hỗ trợ retry an toàn.

Trong một buổi workshop 45–60 phút, hãy:

1. **Viết mục tiêu sản phẩm** bằng một câu nêu kết quả của khách.
2. **Lập bảng thuật ngữ** gồm ít nhất sáu khái niệm, quan hệ và các câu hỏi chưa rõ.
3. **Vẽ mô hình miền đơn giản**: các đối tượng/khái niệm, trạng thái, quy tắc.
4. **Chỉ ra ba bất biến**, gồm một liên quan dữ liệu khi concurrent requests.
5. **Tạo hai feature sets** và tối thiểu sáu feature nhỏ theo hướng hành động–kết quả–đối tượng.
6. **Đánh dấu một feature rủi ro cao** và thiết kế spike có timebox để kiểm chứng giả định trước khi xây lớn.
7. **Chọn một feature để Design by Feature**, vẽ tương tác và viết hai kịch bản chấp nhận.
8. **Nêu tiêu chí hoàn tất Build by Feature** gồm review, test, integration và các trường hợp lỗi trọng yếu.
9. **Lập kế hoạch thứ tự ban đầu** dựa trên giá trị, rủi ro, phụ thuộc và năng lực thực tế.
10. **Chọn hai chỉ số flow và hai tín hiệu outcome/chất lượng** để kiểm tra sau khi giao.

### 18.2. Mẫu ghi nhận

| Hạng mục | Câu trả lời của nhóm |
| --- | --- |
| **Product outcome** | ... |
| **Khái niệm miền và định nghĩa** | ... |
| **Quan hệ và bất biến** | ... |
| **Giả định chưa được kiểm chứng** | ... |
| **Subject areas / feature sets** | ... |
| **Danh sách feature theo hành vi** | ... |
| **Phụ thuộc và thứ tự dự kiến** | ... |
| **Feature team / người phối hợp** | ... |
| **Thiết kế một feature** | ... |
| **Tiêu chí chấp nhận và kiểm thử** | ... |
| **Điều kiện tích hợp/hoàn tất** | ... |
| **Tín hiệu flow, chất lượng, outcome** | ... |
| **Ngày/căn cứ xem lại mô hình** | ... |

### 18.3. Một đáp án mẫu ngắn

**Outcome:** “Khách tự đặt lịch tư vấn hợp lệ, biết trạng thái và không gặp lịch trùng”.

**Bất biến mẫu:** Không có hai lịch đã xác nhận trùng khoảng thời gian ở một chuyên gia nếu chính sách chỉ cho một lịch; chỉ chủ thể có quyền được hủy lịch; retry cùng yêu cầu không tạo lịch thứ hai.

**Feature set Khả dụng:** Xác định giờ còn trống; loại trừ lịch xung đột; hiển thị giờ theo múi giờ khách.

**Feature set Đặt lịch:** Kiểm tra điều kiện yêu cầu; tạo lịch hợp lệ; trả kết quả nhất quán khi retry.

**Điểm chưa biết:** Cách đối tác trả trạng thái sau timeout. Thực hiện spike sandbox có giới hạn với trường hợp gửi lặp/truy vấn kết quả, ghi độ tin cậy và quyết định tiếp.

**Tín hiệu:** Cycle time feature từ bắt đầu tới đủ điều kiện giao; tuổi hạng mục chờ API; tỷ lệ người dùng đặt thành công và số lỗi đặt trùng/khôi phục.

Đáp án chỉ là **một mô hình có thể hợp lý**. Nhóm cần trình bày giả định và cách kiểm chứng; không chấm điểm cao một sơ đồ chỉ vì có nhiều class hơn.

## 19. Checklist thực hành FDD hướng giá trị

### Hiểu miền và lập danh sách feature

- [ ] Có mô hình tổng thể đủ dùng và được người hiểu nghiệp vụ xem lại.
- [ ] Các thuật ngữ “đã yêu cầu”, “đã xác nhận”, “đã hủy” có định nghĩa nhất quán.
- [ ] Mô hình có hành vi, trạng thái và bất biến, không chỉ bảng lưu trữ.
- [ ] Những giả định quan trọng được ghi rõ mức tin cậy và cách kiểm tra.
- [ ] Feature list được nhóm theo miền chủ đề/feature set và diễn đạt bằng kết quả nghiệp vụ.
- [ ] Feature đủ nhỏ để thiết kế, hiện thực và kiểm chứng trong một vòng ngắn.
- [ ] Các công việc thuần kỹ thuật được gắn đúng vai trò, không giả vờ là giá trị người dùng đã hoàn tất.

### Thiết kế và xây dựng theo feature

- [ ] Người hiểu các lớp/quy tắc liên quan được tham gia feature team.
- [ ] Quyền quyết định sản phẩm và trách nhiệm thiết kế/kiểm tra được phân biệt.
- [ ] Design by Feature tập trung vào tình huống quan trọng, bất biến và tích hợp.
- [ ] Có test cho trường hợp biên, retry, quyền truy cập, lỗi mạng khi phù hợp.
- [ ] Feature không được coi Done trước khi đáp ứng chuẩn chất lượng và tích hợp.
- [ ] Class ownership không trở thành điểm phụ thuộc một người không có dự phòng.
- [ ] Các thay đổi mô hình được truyền đạt tới feature/test liên quan.

### Học và cải tiến liên tục

- [ ] Phản hồi của người dùng có thể làm đổi thứ tự feature hoặc điều chỉnh mô hình.
- [ ] Một quyết định chưa đủ thông tin có thể được hỗ trợ bằng spike timebox.
- [ ] Tiến độ theo feature được đối chiếu với WIP, cycle time, lỗi và outcome.
- [ ] Công việc chưa hoàn tất/bị chặn không bị giấu bằng báo cáo phần trăm.
- [ ] Nếu kết hợp Scrum/Kanban/XP, trách nhiệm và quy tắc thực thi không mâu thuẫn.
- [ ] Mọi cải tiến đều hướng tới giá trị và độ tin cậy của **toàn sản phẩm**, không chỉ số lượng class/code/ticket.

## 20. Ghi nhớ cốt lõi

**Feature-Driven Development (FDD)** là cách phát triển phần mềm dựa trên **mô hình miền tổng thể** và **những feature nhỏ có giá trị cho khách hàng**. Năm quy trình tạo một vòng làm việc có cấu trúc: **Develop an Overall Model → Build a Features List → Plan by Feature → Design by Feature → Build by Feature**. Mô hình giúp nhóm thống nhất khái niệm và bất biến; feature list chuyển hiểu biết thành hành vi có thể lập kế hoạch, kiểm chứng và tích hợp.

Ba điều quan trọng cần giữ:

1. **Mô hình miền không phải sơ đồ database bất biến.** Nó là sự hiểu biết đang tiến triển, cần được kiểm chứng với chuyên gia nghiệp vụ, thử nghiệm và phần mềm hoạt động.
2. **Feature không phải một task công nghệ.** Một feature cần mô tả kết quả chức năng có giá trị; class, API, UI, kiểm thử và tích hợp là các việc phục vụ kết quả đó.
3. **Phát triển theo feature phải đi tới giá trị được kiểm chứng.** Design inspection, code inspection, unit test, integration và phản hồi người dùng giúp tránh báo tiến độ đẹp khi sản phẩm chưa hữu ích hoặc không an toàn.

FDD có thể đặc biệt hữu ích khi miền phức tạp và nhiều người cần ngôn ngữ chung. Nhưng không nên áp dụng class ownership cứng, mô hình hóa quá mức hoặc khóa danh sách feature bất chấp thay đổi. Scrum có thể cung cấp mục tiêu Sprint và nhịp kiểm tra–thích ứng; Kanban giúp quản lý WIP và flow; XP giúp kiểm thử và tích hợp an toàn. **Chọn và kết hợp cách làm để hiểu đúng vấn đề, giao phần mềm tăng dần và học nhanh từ thực tế.**

### Tài liệu tham khảo nền tảng

- Stephen R. Palmer và John M. Felsing, *A Practical Guide to Feature-Driven Development* (2002) — mô tả các quy trình, feature list, vai trò và tổ chức triển khai FDD.
- Peter Coad, Eric Lefebvre và Jeff De Luca, *Java Modeling in Color with UML* (1999) — bối cảnh về mô hình đối tượng và mô hình hóa miền liên quan tới FDD.
- Eric Evans, *Domain-Driven Design: Tackling Complexity in the Heart of Software* (2003) — tham khảo thêm về tư duy mô hình miền, ngôn ngữ chung; **DDD không đồng nghĩa FDD**.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/) — các giá trị Agile và ưu tiên phần mềm hoạt động, phản hồi sớm, đáp ứng thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html) — giao giá trị sớm, chất lượng kỹ thuật, đơn giản và cải tiến liên tục.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — Sprint, Product Goal, Sprint Goal, Definition of Done và trách nhiệm Scrum Team.
- [The Kanban Guide](https://kanbanguides.org/) — Definition of Workflow, WIP, throughput, cycle time và work item age.
