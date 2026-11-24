# Thiết kế mô đun để giảm phụ thuộc và giới hạn tác động thay đổi

> **Chương:** Thiết kế tiến hóa  
> **Học phần:** **AGILE_DEVELOPMENT** — vận dụng giá trị và nguyên tắc Agile để phát triển phần mềm thích ứng nhờ phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc để lựa chọn cách phối hợp phù hợp.

Một hệ thống đặt lịch tư vấn đang chạy ổn định. Product Owner nhận phản hồi rằng khi mạng yếu, khách gửi lại yêu cầu đặt lịch và đôi khi nhận hai cuộc hẹn. Developers dự định sửa logic chống trùng. Nhưng thay vì thay đổi một khu vực rõ ràng, họ phải sửa màn hình, bộ điều khiển HTTP, nhiều dịch vụ nghiệp vụ, lớp lưu trữ, bộ gửi thông báo và hàng loạt bài kiểm thử phụ thuộc cấu trúc nội bộ. Mỗi thay đổi tạo thêm lỗi ngoài dự kiến.

Đây là vấn đề của **phụ thuộc khó kiểm soát** và **phạm vi ảnh hưởng của thay đổi** (*change impact* hoặc *blast radius*). Trong Agile, yêu cầu mới, kết quả thử nghiệm và phản hồi người dùng sẽ liên tục làm kế hoạch thay đổi. Nếu cấu trúc phần mềm khiến một chỉnh sửa nhỏ lan qua nhiều nơi, nhóm khó giao Increment nhỏ, khó dự báo và có thể sợ thay đổi.

**Thiết kế mô đun (modular design)** nhằm chia hệ thống thành những phần có **trách nhiệm rõ, tính gắn kết bên trong cao, phụ thuộc bên ngoài hợp lý và hợp đồng tương tác đủ ổn định**. Nhờ vậy, khi một quy tắc thay đổi, nhóm biết **nơi cần sửa**, **những điều không được phá** và **cách kiểm chứng tác động**. Đây là nền tảng của **thiết kế tiến hóa (evolutionary design)**: kiến trúc được điều chỉnh từng bước theo bằng chứng, không đóng băng quá sớm cũng không chấp nhận cấu trúc hỗn loạn.

Mô đun hóa không đồng nghĩa “chia thành thật nhiều microservice” hoặc “mỗi class đều phải có interface”. Thiết kế tốt là **tạo ranh giới đúng cho những lý do thay đổi quan trọng**, đồng thời tránh chi phí trừu tượng và vận hành không cần thiết.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích **cohesion**, **coupling**, **information hiding**, **encapsulation** và **change impact** bằng ví dụ phần mềm.
2. Phân biệt mô đun nghiệp vụ với package, class, thư viện, dịch vụ triển khai và mô đun của công cụ build; nhận ra vì sao chia thư mục chưa đủ tạo ranh giới thật.
3. Xác định ranh giới theo **trách nhiệm và lý do thay đổi**, vẽ sơ đồ phụ thuộc và phát hiện vòng phụ thuộc hoặc truy cập xuyên ranh giới.
4. Thiết kế **hợp đồng giao tiếp** che giấu chi tiết triển khai, dùng **Dependency Inversion** khi có lợi, đồng thời kiểm soát phụ thuộc dữ liệu và thời gian.
5. Đề xuất cách tách một hệ thống đặt lịch thành các mô đun có trách nhiệm rõ, xử lý quy tắc chống trùng và tích hợp API đối tác mà không lan thay đổi bất hợp lý.
6. Thực hiện refactoring từng bước với kiểm thử bảo vệ hành vi, kiểm thử hợp đồng và cơ chế đo tác động, thay vì viết lại toàn bộ.
7. Đánh giá đánh đổi giữa **modular monolith**, thư viện chung và microservices; kết nối kỹ thuật mô đun hóa với Scrum, Kanban, XP và phản hồi sớm.

## 2. Tối ưu cho thay đổi, không chỉ cho sơ đồ đẹp

### 2.1. Tại sao giới hạn tác động thay đổi lại quan trọng?

Giả sử hệ thống có ba khu vực:

- **Booking:** tạo, giữ, xác nhận, đổi và hủy lịch.
- **Notification:** gửi email/SMS và theo dõi thông báo.
- **Availability:** tính giờ có thể đặt.

Khách hàng yêu cầu thay mẫu email. Nếu thiết kế rõ ràng, việc sửa chủ yếu ở Notification; Booking chỉ cung cấp dữ kiện hoặc một sự kiện có ý nghĩa. Nếu Booking trực tiếp ghép HTML, biết cấu hình SMTP và truy vấn bảng mẫu email, một yêu cầu trình bày đơn giản có thể đụng cả nghiệp vụ đặt lịch.

Ngược lại, nếu Product Owner thay quy tắc **“một chuyên gia không được có hai lịch đã xác nhận giao nhau”**, đó là thay đổi thuộc Booking và có thể ảnh hưởng Availability ở **hợp đồng nghiệp vụ đã xác định**. Không nên che giấu tác động cần thiết: thay đổi quy tắc quan trọng phải được kiểm tra tại mọi nơi nó thực sự áp dụng. Mô đun hóa giúp phân biệt **tác động bắt buộc vì thay đổi ý nghĩa** với **tác động tình cờ vì cấu trúc phụ thuộc kém**.

### 2.2. Ba kiểu thay đổi cần phân biệt

| Loại thay đổi | Ví dụ | Thiết kế mô đun tốt giúp gì? |
| --- | --- | --- |
| **Thay đổi chính sách nghiệp vụ** | Không cho đổi lịch trong vòng hai giờ trước phiên. | Đặt quy tắc ở mô đun có trách nhiệm, cập nhật kiểm thử hành vi và hợp đồng liên quan. |
| **Thay đổi hạ tầng/kỹ thuật** | Chuyển nhà cung cấp SMS, đổi thư viện HTTP. | Giữ logic nghiệp vụ không phụ thuộc trực tiếp SDK, cấu hình hay payload riêng của nhà cung cấp. |
| **Thay đổi cách người dùng tương tác** | Thêm ứng dụng di động bên cạnh giao diện web. | Tái sử dụng hành vi nghiệp vụ qua API/use case rõ mà không sao chép quy tắc vào từng UI. |

Mục tiêu không phải thay đổi một dòng mã trong mọi trường hợp. Một quy tắc mới ảnh hưởng nhiều hành vi có thể cần sửa nhiều nơi hợp lệ. Mục tiêu là **tác động có thể dự đoán, có lý do và được kiểm chứng**, không phát tán ngẫu nhiên.

### 2.3. Phạm vi ảnh hưởng là gì?

**Change impact** có thể hiểu theo nhiều chiều:

1. **Mã nguồn:** Bao nhiêu lớp, package và mô đun phải chỉnh sửa?
2. **Kiểm thử:** Bao nhiêu bài kiểm thử hỏng vì đổi hành vi, bao nhiêu bài hỏng vì phụ thuộc chi tiết nội bộ?
3. **Triển khai:** Cần xây, phát hành hoặc đồng bộ bao nhiêu thành phần?
4. **Dữ liệu và hợp đồng:** Có cần di chuyển dữ liệu, thay API, cập nhật người tiêu dùng không?
5. **Con người:** Bao nhiêu nhóm phải phối hợp, chờ review hoặc phê duyệt?
6. **Vận hành:** Có ảnh hưởng giám sát, rollback, quyền truy cập và khả năng khôi phục không?

**Số file thay đổi thấp** không tự động chứng minh thiết kế tốt: một file khổng lồ xử lý cả hệ thống có thể chỉ cần sửa một nơi nhưng rất khó hiểu và dễ gây lỗi. Đánh giá phải xem **phạm vi trách nhiệm, mức lan truyền thực tế, chất lượng và chi phí phối hợp**.

## 3. Các nguyên tắc nền tảng của thiết kế mô đun

### 3.1. Cohesion — gắn kết cao bên trong mô đun

**Cohesion** trả lời: *Những trách nhiệm trong mô đun có thực sự thuộc về cùng một mục đích không?*

Mô đun **Booking** có thể bao gồm yêu cầu đặt lịch, chính sách xác nhận, xử lý chống trùng và vòng đời Appointment vì các khái niệm này phối hợp để bảo đảm một lịch hợp lệ. Nếu Booking cũng quản lý bản tin marketing, hóa đơn lương và cấu hình giao diện, ranh giới đang quá rộng.

**Ví dụ không tốt:**

~~~text
utils/
  BookingUtil
  PriceUtil
  EmailUtil
  SecurityUtil
  CalendarUtil
~~~

Tên **utils** nói rất ít về người chịu trách nhiệm hay lý do thay đổi. Một số hàm nhỏ không có trạng thái có thể nằm ở thư viện chung khi thực sự ổn định, nhưng việc gom mọi quy tắc nghiệp vụ vào “utils” sẽ làm mờ ranh giới.

**Ví dụ có chủ đích hơn:**

~~~text
booking/
  BookingPolicy
  Appointment
  BookingApplicationService

availability/
  AvailabilityService
  WorkingCalendar

notification/
  NotificationService
  MessageTemplate
~~~

Đây vẫn chỉ là sơ đồ minh họa: chất lượng của mô đun phụ thuộc vào **ai được phép gọi gì và quy tắc nằm ở đâu**, không phải tên folder.

### 3.2. Coupling — phụ thuộc giữa các mô đun

**Coupling** là mức một phần của hệ thống cần biết hoặc dựa vào chi tiết của phần khác. Không thể có hệ thống hữu ích với **không phụ thuộc nào cả**; mô đun phải cộng tác để tạo tính năng. Điều cần giảm là **phụ thuộc không cần thiết, phụ thuộc vào chi tiết dễ đổi và phụ thuộc vòng**.

| Cấu trúc | Đánh giá |
| --- | --- |
| Booking gọi một hợp đồng Availability trả về khả năng đặt giờ. | Phụ thuộc có mục đích, có thể kiểm soát. |
| Booking import kiểu dữ liệu nội bộ của SDK SMS. | Phụ thuộc sai lý do: thay nhà cung cấp làm Booking phải sửa. |
| Notification đọc/ghi trực tiếp bảng Appointment để quyết định trạng thái. | Rò rỉ quyền sở hữu dữ liệu và quy tắc nghiệp vụ. |
| Booking gọi Notification; Notification lại gọi Booking để kết thúc transaction. | Nguy cơ phụ thuộc vòng và khó hiểu thứ tự thực hiện. |
| Một thư viện chung chứa mọi entity và business rule của cả công ty. | Có thể khiến thay đổi nhỏ kéo theo build/release hàng loạt. |

### 3.3. Encapsulation và information hiding

**Encapsulation** gom trạng thái và hành vi liên quan cùng nơi, cung cấp những thao tác hợp lệ. **Information hiding** là chủ đích **che giấu quyết định triển khai có khả năng thay đổi** để mô đun bên ngoài không phụ thuộc chúng.

Ví dụ, mô đun Booking có thể cung cấp thao tác **requestBooking(...)** với kết quả rõ, còn việc dùng bảng SQL, khóa idempotency và transaction nội bộ là chi tiết không nên để controller hay Notification trực tiếp thao tác. Khi thay cấu trúc lưu trữ, hợp đồng nghiệp vụ có cơ hội được giữ.

**Giới hạn:** Che giấu chi tiết không có nghĩa giấu **ý nghĩa nghiệp vụ**. Nếu khách có thể nhận trạng thái Pending, hợp đồng trả kết quả phải công khai điều này; không thể đặt tên thao tác là Confirmed rồi âm thầm che việc còn chờ.

### 3.4. Separation of concerns — tách các mối quan tâm

Các quy tắc về xác nhận lịch, hiển thị giao diện, gửi thông báo, lưu trữ và quan sát lỗi có lý do thay đổi khác nhau. Tách chúng theo **concern** giúp mô đun chuyên trách không phải hiểu mọi chi tiết.

Nhưng phân tầng thuần kỹ thuật kiểu **controllers/services/repositories** trải rộng toàn bộ sản phẩm không tự bảo đảm tách tốt nghiệp vụ. Nếu mọi use case phải đi qua một **CommonService** biết tất cả domain entity, phụ thuộc vẫn dày đặc.

### 3.5. Single Responsibility ở cấp mô đun

Một cách áp dụng **Single Responsibility Principle** là hỏi: *Mô đun này có bao nhiêu nhóm lý do độc lập có thể buộc nó thay đổi?*

Ví dụ:

- Chính sách “được hủy trước bao lâu” do nghiệp vụ đặt lịch thay đổi.
- Nội dung email do đội truyền thông thay đổi.
- Thư viện gửi email do nhà cung cấp thay đổi.

Nếu cả ba đòi sửa một mô đun chung, ranh giới cần xem lại. Tuy nhiên, không nên tách **mỗi phương thức** thành một mô đun: quá nhiều ranh giới mỏng có thể tạo chi phí điều phối và debug không cần thiết.

### 3.6. Nguyên tắc thiết kế tiến hóa

Thiết kế tiến hóa không đòi phải dự báo mọi thay đổi trong mười năm. Nhóm:

1. Bắt đầu với **thiết kế đơn giản đáp ứng yêu cầu đã biết**.
2. Đặt ranh giới rõ ở những khu vực **có lý do thay đổi khác nhau hoặc có rủi ro cao**.
3. Dùng **kiểm thử và tích hợp liên tục** để có khả năng sửa cấu trúc an toàn.
4. Thu thập phản hồi, phát hiện điểm đau thực.
5. **Refactor** khi bằng chứng cho thấy cấu trúc hiện tại cản trở thay đổi.

Một mô đun có thể cần tách sau vài vòng phát triển; một mô đun khác có thể nên được gộp lại vì ranh giới cũ gây giao tiếp quá mức. **Khả năng sửa thiết kế** là phẩm chất quan trọng không kém sơ đồ thiết kế ban đầu.

## 4. Chọn ranh giới mô đun theo lý do thay đổi

### 4.1. Bắt đầu từ ngôn ngữ nghiệp vụ

Với hệ thống đặt lịch, hãy hỏi chuyên gia miền và người chịu trách nhiệm sản phẩm:

- “Khung giờ khả dụng” khác “giữ chỗ” và “lịch đã xác nhận” như thế nào?
- Ai quyết định một Appointment có hợp lệ không?
- Nếu đổi nhà cung cấp thông báo, quy tắc đặt lịch có cần thay không?
- Nếu thay chính sách hủy, hệ thống thanh toán và thông báo cần nhận thông tin gì?
- Những bất biến nào phải được bảo vệ trong cùng giao dịch?

Các câu trả lời giúp vẽ **ranh giới trách nhiệm**, sau đó mới quyết định cách tổ chức package, module của build hoặc service triển khai.

### 4.2. Mẫu ranh giới cho hệ thống đặt lịch

| Mô đun | Trách nhiệm chính | Điều nó nên che giấu | Hợp đồng mô đun khác cần biết |
| --- | --- | --- | --- |
| **Booking** | Nhận yêu cầu, kiểm tra và tạo/hủy/đổi lịch, bảo vệ bất biến chống trùng. | Cơ chế transaction, schema lưu lịch, thuật toán xử lý retry. | Kết quả tạo lịch, trạng thái và những sự kiện nghiệp vụ công khai. |
| **Availability** | Tính giờ có thể đặt từ lịch làm việc và các điều kiện liên quan. | Cách tổng hợp lịch làm việc, ngày nghỉ và dữ liệu đầu vào. | Truy vấn thời gian khả dụng với ý nghĩa rõ. |
| **Notification** | Biên soạn và gửi thông báo theo kết quả nghiệp vụ. | SDK SMTP/SMS, retry thông báo, template rendering. | Yêu cầu thông báo với loại và dữ liệu cần thiết. |
| **Identity/Authorization** | Xác thực và xác định quyền cho các thao tác. | Nhà cung cấp danh tính, token/cấu hình cụ thể. | Nhận diện chủ thể và quyết định quyền có căn cứ. |
| **Partner Integration** | Chuyển đổi hợp đồng giữa ứng dụng và hệ thống đối tác. | Payload, mã lỗi, SDK, retry/timeout đặc thù đối tác. | Cổng giao tiếp và kiểu kết quả theo ngữ nghĩa nội bộ. |

Đây là **cách phân rã gợi ý**, không phải kiến trúc chuẩn bắt buộc. Với hệ thống nhỏ, Availability và Booking có thể nằm trong cùng mô đun nếu chúng phải thay đổi cùng nhau và tách ra tạo giao tiếp phức tạp. Trong các miền đặc biệt, Notification có thể chịu những nghĩa vụ nghiệp vụ riêng, không chỉ là adapter kỹ thuật.

### 4.3. Đừng nhầm bounded context với microservice

**Bounded context** trong Domain-Driven Design (DDD) là một ranh giới mà mô hình/thuật ngữ có nghĩa nhất quán. Nó có thể giúp tìm ứng viên mô đun, nhưng **không đồng nghĩa mỗi bounded context phải là một microservice**. Một hệ thống đơn khối được tổ chức thành mô đun rõ ràng (*modular monolith*) vẫn có thể có nhiều vùng ngôn ngữ nghiệp vụ.

Ví dụ, “Khách hàng” trong Booking có thể là danh tính và quyền đặt lịch, còn trong Billing có thể là chủ thể thanh toán. Không nên bắt hai vùng dùng cùng một object chứa hàng chục thuộc tính chỉ vì tên giống nhau. Hợp đồng giữa các vùng cần dữ liệu tối thiểu với **ngữ nghĩa rõ**, không chia sẻ toàn bộ mô hình nội bộ.

### 4.4. Phân tích lý do thay đổi bằng ma trận

Giả sử các thay đổi dự kiến gồm:

| Thay đổi | Booking | Availability | Notification | Partner Integration |
| --- | --- | --- | --- | --- |
| Đổi mẫu email | Không cần sửa | Không cần sửa | **Sửa** | Không cần sửa |
| Đổi thuật toán tính ngày nghỉ | Có thể ảnh hưởng hợp đồng nếu nghĩa đổi | **Sửa** | Không cần sửa | Không cần sửa |
| Đổi SDK nhà cung cấp lịch đối tác | Không cần sửa nếu hợp đồng ổn | Không cần sửa nếu hợp đồng ổn | Không cần sửa | **Sửa** |
| Thêm trạng thái Pending vào quy trình đặt lịch | **Sửa** | Có thể đổi quy tắc giữ chỗ | Có thể thêm thông báo phù hợp | Có thể cập nhật mapping |
| Thêm bảo vệ tạo trùng khi retry | **Sửa và kiểm chứng bất biến** | Có thể cần kiểm thử tích hợp | Không nên đổi logic email | Có thể cần hỗ trợ idempotency |

Những ô “có thể” là **tác động có chủ đích cần đánh giá**, không phải minh chứng thiết kế lỗi. Nếu một thay đổi **chỉ về giao diện email** buộc sửa Booking và database Appointment, đó mới là dấu hiệu phụ thuộc bất hợp lý.

## 5. Nhìn phụ thuộc như một mạng, không chỉ import code

### 5.1. Các loại coupling cần nhận biết

| Kiểu phụ thuộc | Ví dụ | Nguy cơ | Cách giảm có chủ đích |
| --- | --- | --- | --- |
| **Compile-time/code** | Booking import class SDK của SMS. | Thay thư viện buộc rebuild/sửa nhiều mô đun. | Dùng hợp đồng miền hoặc adapter tại ranh giới. |
| **Data/schema** | Notification cập nhật trực tiếp bảng Appointment. | Thay schema phá mô đun khác và vi phạm quyền sở hữu dữ liệu. | Dùng API/query projection/event đúng nhu cầu. |
| **Temporal** | Booking chỉ hoạt động nếu SMS trả lời tức thì. | Lỗi thông báo làm chặn đặt lịch. | Xem thông báo bất đồng bộ nếu nghiệp vụ cho phép; dùng retry/outbox khi cần. |
| **Behavioral/semantic** | Hai mô đun hiểu Pending với nghĩa khác nhau. | Hợp đồng có thể compile nhưng xử lý sai. | Ví dụ nghiệp vụ, contract tests, phiên bản và ngôn ngữ chung. |
| **Deployment** | Thay template email buộc triển khai đồng thời nhiều dịch vụ. | Khó phát hành độc lập và rollback. | Giảm shared libraries dễ đổi; giữ hợp đồng tương thích. |
| **Organizational** | Chỉ một người được sửa mọi lớp Booking. | Chờ review và phụ thuộc tri thức. | Pairing, người dự phòng, chính sách review hợp lý. |
| **Operational** | Mỗi yêu cầu UI gọi đồng bộ qua năm dịch vụ. | Độ trễ, nhiều điểm lỗi và khó quan sát. | Giảm chuỗi đồng bộ; thiết kế ranh giới theo luồng thực tế. |

**Không có kỹ thuật duy nhất giải quyết tất cả coupling.** Interface có thể giảm phụ thuộc vào một SDK, nhưng không sửa được nghĩa Pending bị hiểu khác hoặc một shared database mà mọi đội đều sửa.

### 5.2. Sơ đồ hướng phụ thuộc

~~~mermaid
flowchart LR
    UI["Web/Mobile UI"] --> APP["Booking Application"]
    APP --> CORE["Booking Domain"]
    APP --> AVAIL["Availability Contract"]
    APP --> OUT["Notification Port"]
    APP --> PARTNER["Partner Gateway Port"]
    AVIMPL["Availability Module"] -. "implements" .-> AVAIL
    NOTIF["Notification Adapter"] -. "implements" .-> OUT
    EXTERNAL["Partner Adapter"] -. "implements" .-> PARTNER
    EXTERNAL --> API["External Partner API"]
    APP --> REPO["Booking Repository Port"]
    STORE["Booking Persistence Adapter"] -. "implements" .-> REPO
~~~

Sơ đồ tách **cách Booking mô tả nhu cầu** khỏi **cách một adapter đáp ứng nhu cầu**. Các interface/port được đặt ở ranh giới phù hợp để phần nghiệp vụ không phải import SDK đối tác. Sơ đồ không có nghĩa phải tạo một class interface cho mọi phương thức hoặc chia mỗi ô thành microservice.

### 5.3. Vòng phụ thuộc làm thay đổi lan xa

**Ví dụ xấu:**

~~~text
booking -> notification -> customer -> booking
~~~

Booking muốn sửa khái niệm Customer có thể gặp vòng import hoặc vòng trách nhiệm; việc build/test/tái sử dụng khó tách. Một module dependency graph nên được hướng theo **lớp trừu tượng và trách nhiệm** có chủ đích.

**Một hướng tách:**

~~~text
booking -> notification-contract
notification -> notification-contract

booking -> customer-identity-contract
customer-identity-adapter -> customer-identity-contract
~~~

Tuy nhiên, việc tạo thư viện contract chung cũng có chi phí: phiên bản, nghĩa nghiệp vụ và ownership. **Đừng tạo một common-contract khổng lồ** làm thay đổi một enum phải rebuild mọi ứng dụng. Hợp đồng nên **hẹp, ổn định theo người tiêu dùng và được quản lý phiên bản**.

### 5.4. Sơ đồ không thể thay thế kiểm chứng

Một sơ đồ không có mũi tên vòng **không chứng minh** hệ thống không phụ thuộc vòng ở runtime. Ví dụ Booking phát sự kiện, Notification xử lý rồi đồng bộ gọi lại Booking để “xác nhận tiếp” vẫn tạo vòng hành vi. Nhóm cần xem:

- Quan hệ import/build (tĩnh).
- Luồng gọi đồng bộ hoặc bất đồng bộ (thời gian chạy).
- Ai sở hữu schema/trạng thái.
- Các sự kiện và chuỗi xử lý khi lỗi.
- Các phụ thuộc triển khai, cấu hình và vận hành.

## 6. Hợp đồng mô đun: ổn định ở điều có ý nghĩa, linh hoạt ở triển khai

### 6.1. Hợp đồng phải nói rõ hành vi chứ không chỉ chữ ký

Một interface như **book(request): AppointmentId** chưa nói:

- Nếu không còn giờ, kết quả ra sao?
- Nếu client gửi lại cùng yêu cầu sau timeout, có tạo trùng không?
- Nếu lịch đang Pending, có trả một AppointmentId chưa Confirmed không?
- Ai có quyền đặt cho người khác?
- Thông báo thất bại có ảnh hưởng sự hợp lệ của lịch không?

Hợp đồng tốt phải mô tả **đầu vào, ý nghĩa kết quả, lỗi, bất biến và điều kiện thời gian**. Java interface giúp kiểm tra chữ ký, nhưng **không tự chứng minh tương thích về nghiệp vụ**.

### 6.2. Một mô hình cổng giao tiếp hẹp

Giả sử Booking cần kiểm tra lịch làm việc của chuyên gia. Cổng giao tiếp có thể diễn đạt theo thuật ngữ nghiệp vụ:

~~~java
// Pseudocode Java minh họa, bỏ qua phần định nghĩa kiểu cụ thể.
public interface AvailabilityReader {
    AvailabilityDecision checkBookable(
        ConsultantId consultantId,
        TimeRange desiredRange
    );
}

public record AvailabilityDecision(
    boolean bookable,
    String reasonCode
) {}
~~~

Đây là hợp đồng ở **mức thảo luận**; trong sản phẩm thật cần xem chính sách thời gian, múi giờ, lỗi hệ thống và việc hai yêu cầu đồng thời có thể vượt qua kiểm tra trước khi lưu. **checkBookable** chỉ cung cấp một thông tin; Booking vẫn phải bảo vệ bất biến khi ghi lịch ở nơi có thẩm quyền.

Thiết kế không tốt là để Booking nhận **VendorCalendarSdkResponse** chứa mã lỗi đặc thù, metadata HTTP, kiểu ngày riêng và token của đối tác. Khi nhà cung cấp đổi, cả nghiệp vụ phải sửa.

### 6.3. Dependency Inversion Principle (DIP)

**DIP** gợi ý rằng các phần chính sách cấp cao không nên phụ thuộc trực tiếp vào chi tiết triển khai cấp thấp; cả hai hướng tới một trừu tượng phù hợp. Trừu tượng phải phản ánh **nhu cầu của bên sử dụng** hơn là chỉ bọc nguyên giao diện nhà cung cấp.

**Trước khi đảo hướng phụ thuộc:**

~~~java
public final class BookingService {
    private final VendorCalendarClient client =
        new VendorCalendarClient("provider-specific-config");

    public void book(BookingCommand command) {
        VendorSlotResponse result =
            client.reserveSlot(command.toVendorPayload());
        // Logic miền phụ thuộc SDK, payload và mã lỗi cụ thể.
    }
}
~~~

**Sau khi làm rõ ranh giới:**

~~~java
public interface PartnerReservationPort {
    PartnerReservationResult reserve(ReservationRequest request);
}

public final class BookingService {
    private final PartnerReservationPort reservationPort;

    public BookingService(PartnerReservationPort reservationPort) {
        this.reservationPort = reservationPort;
    }

    public BookingOutcome book(BookingCommand command) {
        // Kiểm tra quyền và bất biến nghiệp vụ ở vị trí phù hợp.
        PartnerReservationResult result =
            reservationPort.reserve(command.toReservationRequest());
        return mapBusinessOutcome(result);
    }
}

// Adapter ở mép hệ thống: chuyển đổi payload/lỗi của nhà cung cấp.
public final class VendorReservationAdapter
        implements PartnerReservationPort {
    private final VendorCalendarClient vendor;

    public VendorReservationAdapter(VendorCalendarClient vendor) {
        this.vendor = vendor;
    }

    @Override
    public PartnerReservationResult reserve(ReservationRequest request) {
        // Mapping có kiểm thử: timeout, retry, từ chối, trạng thái chưa rõ.
        return mapVendorResponse(vendor.reserve(request));
    }
}
~~~

Đây là **mã minh họa ý tưởng, chưa đủ để biên dịch hoặc dùng production**: các kiểu, quyền truy cập, xử lý lỗi và cơ chế nhất quán chưa được định nghĩa. Điểm cần học là Booking **không tự tạo SDK cụ thể và không dùng payload đối tác làm ngôn ngữ miền**.

### 6.4. Dependency Injection khác Dependency Inversion

**Dependency Injection (DI)** là kỹ thuật cung cấp đối tượng phụ thuộc từ bên ngoài, chẳng hạn truyền adapter vào constructor. **Dependency Inversion (DIP)** là nguyên tắc về **hướng phụ thuộc và mức độ trừu tượng**.

Một lớp được DI trực tiếp một **VendorCalendarClient** vẫn có thể phụ thuộc chặt vào SDK nếu logic miền sử dụng mã lỗi và kiểu dữ liệu của nhà cung cấp. DI giúp thay thế lúc chạy và kiểm thử; nó không tự tạo hợp đồng đúng.

### 6.5. Trừu tượng hợp lý khác overengineering

Nếu hệ thống chỉ có một thuật toán tính giá đơn giản, ổn định và không có lý do thay đổi độc lập, tạo **PricingStrategyFactoryProviderRegistry** cùng bảy interface có thể làm thiết kế khó hiểu hơn. Hãy hỏi:

- Có **ít nhất một lý do thay đổi hoặc nhu cầu kiểm thử** cần ranh giới này không?
- Hợp đồng có che một chi tiết dễ đổi **thực sự** không?
- Người dùng hợp đồng có ít cần hiểu hơn trước không?
- Khi thêm một biến thể, cần sửa bao nhiêu nơi?
- Chi phí đọc, điều tra lỗi và cấu hình có tăng quá lợi ích không?

**Thiết kế tiến hóa ưu tiên ranh giới cần thiết hôm nay và khả năng thêm ranh giới ngày mai**, không tạo mọi trừu tượng giả định từ đầu.

## 7. Tách phụ thuộc dữ liệu: ai sở hữu thông tin và quy tắc?

Rất nhiều hệ thống có các package đẹp nhưng vẫn phụ thuộc chặt vì **mọi mô đun cùng đọc và sửa một tập bảng**. Đổi một cột khiến báo cáo, thông báo, lịch hẹn và tích hợp đối tác cùng bị ảnh hưởng. Như vậy, ranh giới ở code chưa phải ranh giới dữ liệu thực.

### 7.1. Ownership dữ liệu không nhất thiết là database riêng

**Data ownership** nghĩa là một mô đun có **trách nhiệm giải thích và bảo vệ ý nghĩa/trạng thái** của dữ liệu trong phạm vi của nó. Mô đun khác tương tác qua hợp đồng được thỏa thuận.

Trong một **modular monolith**, các mô đun có thể dùng **cùng database server** và thậm chí cùng một database vật lý nhưng:

- Booking sở hữu việc tạo, xác nhận, hủy Appointment và bất biến chống trùng.
- Notification không trực tiếp cập nhật trạng thái Appointment.
- Reporting được cung cấp projection/query có ngữ nghĩa rõ hoặc bản sao đọc phù hợp.
- Migration schema được kiểm tra với các consumer trước khi đổi.

Không cần tạo nhiều database độc lập chỉ để thể hiện tính mô đun. Ngược lại, với microservices, việc chia database vật lý cũng **không tự bảo đảm** tính độc lập nếu các dịch vụ vẫn gọi chéo đồng bộ để đọc mọi trường nội bộ.

### 7.2. Tác hại của truy cập xuyên ranh giới

**Trước cải tiến:**

~~~sql
-- Ví dụ mô đun Notification truy vấn trực tiếp bảng nội bộ của Booking:
SELECT customer_email, start_time, status
FROM appointments
WHERE appointment_id = :id;
~~~

Giả sử Booking đổi cấu trúc bảng, tách customer_email sang nơi khác hoặc thêm trạng thái **Pending**. Notification có thể xử lý sai mà compiler không phát hiện.

**Hướng thay thế:** Booking công bố một **BookingConfirmed** event hoặc cung cấp **AppointmentSummary** với các trường và ngữ nghĩa đủ dùng:

~~~json
{
  "eventType": "BookingConfirmed",
  "eventId": "evt-123",
  "appointmentId": "apt-456",
  "customerId": "customer-789",
  "confirmedAt": "2026-05-12T09:00:00Z",
  "schemaVersion": 1
}
~~~

Payload chỉ minh họa. Không nên phát cả hồ sơ khách hàng hoặc token vào sự kiện để “tránh phải gọi API”. Notification cần có cách lấy/biên soạn địa chỉ nhận hợp lệ với chính sách quyền riêng tư và quyền truy cập. **Event mô tả sự thật nghiệp vụ đã xảy ra**, không phải lệnh bí mật cho Notification tự sửa Appointment.

### 7.3. Event-driven có thể giảm coupling nhưng tăng độ phức tạp

Nếu Booking gọi đồng bộ SMS để hoàn tất transaction, lỗi mạng của dịch vụ SMS có thể chặn việc đặt lịch. Phát một sự kiện sau khi lịch được xác nhận và gửi thông báo bất đồng bộ có thể giảm **temporal coupling** nếu nghiệp vụ cho phép.

Nhưng cách này tạo các câu hỏi mới:

- Sự kiện có thể bị giao **ít nhất một lần**; consumer có xử lý trùng an toàn không?
- Hệ thống có đảm bảo không mất sự kiện khi database commit thành công nhưng process chết trước khi gửi không?
- Khi nào trạng thái ở consumer mới được cập nhật, và độ trễ nào chấp nhận được?
- Nếu message đến sai thứ tự hoặc có schema mới, consumer xử lý thế nào?
- Nếu notification thất bại, lịch có cần bị hủy không?

**Transactional outbox** là một cách thường dùng để ghi thay đổi nghiệp vụ và ý định phát sự kiện trong cùng transaction dữ liệu, sau đó chuyển sự kiện đi bằng cơ chế đáng tin. Nó không đem lại “exactly once end-to-end” miễn phí: cần định danh sự kiện, idempotent consumer, monitoring và retry phù hợp.

### 7.4. Chọn nhất quán mạnh cho bất biến thực sự

Một **bất biến không được tạo hai lịch cho một chỗ** có thể cần kiểm soát nhất quán tại nơi sở hữu trạng thái đặt lịch. Không nên vô tình tách bước “kiểm tra còn chỗ” và “ghi lịch” qua hai dịch vụ chỉ giao tiếp bất đồng bộ mà không có cơ chế giữ chỗ/điều phối thích hợp.

Có thể dùng transaction và constraint trong một mô đun, hoặc một giao thức giữ chỗ, idempotency và đối soát rõ ràng khi hệ thống phân tán. **Không có nguyên tắc mô đun hóa nào cho phép bỏ qua tính đúng đắn chỉ để giảm phụ thuộc code.**

### 7.5. Cơ chế tránh lan thay đổi schema

Nếu cần chuyển từ trường **status** dạng chuỗi sang mô hình trạng thái có phiên bản, có thể dùng chiến lược **expand–migrate–contract**:

1. **Expand:** thêm cấu trúc mới theo cách vẫn hỗ trợ consumer cũ.
2. **Migrate:** chuyển dữ liệu và chuyển các consumer sang cách dùng mới; đo lỗi và độ phủ.
3. **Contract:** chỉ bỏ cấu trúc cũ sau khi chắc chắn không còn consumer phụ thuộc.

Trong hệ thống nhiều dịch vụ, cần tính cả consumer không triển khai đồng thời. Nếu có bảng dùng chung bất đắc dĩ, phải xác định rõ ai chịu trách nhiệm tương thích và lịch loại bỏ phụ thuộc, không giả định chỉ cần đổi tên cột là an toàn.

## 8. Mô đun và ranh giới chạy: modular monolith hay microservices?

**Mô đun** là ranh giới trách nhiệm và phụ thuộc. **Microservice** là một kiểu ranh giới triển khai và vận hành riêng. Hai khái niệm không đồng nghĩa.

### 8.1. Modular monolith

Một **modular monolith** là ứng dụng được triển khai như một đơn vị chính nhưng tổ chức thành các mô đun với API và ranh giới dữ liệu/nội bộ rõ. Nó có thể tận dụng transaction nội bộ, IDE refactoring, kiểm thử tích hợp đơn giản hơn và ít thành phần vận hành hơn.

**Điểm mạnh:**

- Dễ thay đổi cấu trúc code và mô hình trong cùng repository/process.
- Tránh overhead network cho các lời gọi nội bộ.
- Có thể bảo vệ một số bất biến bằng transaction cục bộ rõ.
- Dễ bắt đầu nhỏ và tách dần khi có lý do thực tế.

**Giới hạn:** Triển khai chung có thể kéo theo nhiều mô đun cùng lúc; code có thể bị gọi trực tiếp xuyên ranh giới nếu không kiểm soát bằng kiến trúc, package visibility, module tests hoặc quy tắc build. Một “monolith” với phụ thuộc vòng dày đặc **không tự thành modular monolith** chỉ vì đổi tên thư mục.

### 8.2. Microservices

Các dịch vụ độc lập về triển khai có thể hữu ích khi có:

- Nhu cầu triển khai/thay đổi từng phần thực sự khác nhau.
- Năng lực tổ chức, vận hành và giám sát phân tán đủ mạnh.
- Ranh giới nghiệp vụ/dữ liệu tương đối ổn định.
- Nhu cầu mở rộng tải, bảo mật hoặc vòng đời riêng đáng kể.

**Chi phí phải tính:** mạng và timeout, quan sát xuyên dịch vụ, dữ liệu phân tán, hợp đồng phiên bản, triển khai nhiều đơn vị, bảo mật giao tiếp, retry, xử lý lỗi và tính nhất quán. **Chia sai ranh giới thành microservices** có thể làm một thay đổi nhỏ phải phối hợp nhiều đội và phát hành nhiều nơi — đúng điều mô đun hóa muốn tránh.

### 8.3. So sánh theo mục đích

| Câu hỏi | Modular monolith | Microservices |
| --- | --- | --- |
| Có thể tổ chức mô đun nghiệp vụ rõ không? | **Có.** | **Có**, nhưng không tự động. |
| Triển khai độc lập từng mô đun? | Thường không: chủ yếu một đơn vị deploy. | Có thể, nếu hợp đồng và dữ liệu thật sự đủ độc lập. |
| Transaction xuyên ranh giới? | Dễ quản lý hơn nếu cùng process/database và luật ownership phù hợp. | Cần thiết kế nhất quán phân tán hoặc chuyển luồng nghiệp vụ. |
| Chi phí vận hành? | Thường thấp hơn ở quy mô nhỏ/vừa. | Cao hơn do mạng, quan sát và nhiều thành phần. |
| Nguy cơ phụ thuộc sai? | Import trực tiếp, shared tables, common classes. | Đồng bộ nhiều cuộc gọi, shared schema, phiên bản API và triển khai dây chuyền. |
| Khi nào đáng chọn? | Cần tốc độ học, tính nhất quán, ít overhead. | Có nhu cầu độc lập rõ và năng lực quản lý hệ phân tán. |

**Lựa chọn tối ưu không được suy ra từ quy mô repository hoặc số Developer một cách máy móc.** Một sản phẩm nhỏ nhưng nhiều quy tắc nhất quán có thể nên giữ monolith; một tổ chức lớn có thể cần nhiều dịch vụ — nhưng cả hai vẫn cần thiết kế mô đun tốt.

### 8.4. Đừng tối ưu độc lập triển khai bằng mọi giá

Nếu mỗi user story “đặt lịch” đòi thay API Booking, Availability, Notification và Customer rồi triển khai bốn service cùng ngày, hệ thống có nhiều microservices nhưng **khả năng thay đổi độc lập thấp**. Khi đo chất lượng kiến trúc, hãy hỏi **tần suất một thay đổi thông thường yêu cầu đồng bộ nhiều thành phần**, không chỉ đếm số service.

## 9. Tình huống xuyên suốt: đổi nhà cung cấp lịch mà không sửa nghiệp vụ

Giả sử Booking hiện tích hợp một API bên ngoài để giữ giờ tư vấn. Nhà cung cấp hiện tại thay đổi chính sách giá và Product Owner muốn thử một nhà cung cấp khác. Đồng thời, khách hàng đang báo lỗi xác nhận sau timeout.

### 9.1. Kiến trúc trước: phụ thuộc SDK lan khắp hệ thống

~~~mermaid
flowchart LR
    UI["Booking UI"] --> CTRL["Booking Controller"]
    CTRL --> SVC["BookingService"]
    SVC --> VENDOR["VendorCalendarSDK"]
    CTRL --> VENDOR
    NOTIF["NotificationService"] --> VENDOR
    TEST["Integration Tests"] --> VENDOR
    VENDOR --> API["Vendor API"]
~~~

Các vấn đề:

- Controller và Notification đều dùng kiểu phản hồi SDK.
- Mã lỗi riêng của nhà cung cấp được giải thích ở nhiều lớp.
- Logic timeout/retry có nhiều bản sao.
- Muốn thử nhà cung cấp mới phải sửa cả UI, service và test.
- Một yêu cầu nghiệp vụ “không đặt trùng” chưa có nơi chịu trách nhiệm rõ.

**Khi thay nhà cung cấp, phạm vi sửa lớn không phải vì nghiệp vụ thay đổi, mà vì quyết định kỹ thuật đã rò rỉ qua nhiều nơi.**

### 9.2. Bước một: viết test bảo vệ hành vi

Trước khi chuyển cấu trúc, nhóm ghi lại hành vi hiện tại bằng **characterization tests** (kiểm thử đặc tả hành vi đang có) và xác định đâu là hành vi **mong muốn**:

- Gửi một yêu cầu hợp lệ tạo một kết quả đặt lịch đúng.
- Hai request cạnh tranh không tạo hai lịch được xác nhận cho cùng chỗ.
- Gửi lại cùng mã nhận diện không tạo thêm lịch.
- Timeout sau khi đã xử lý phải trả **trạng thái chưa xác định hoặc đối soát**, không tự khẳng định thất bại.
- Nhà cung cấp từ chối giờ đã chiếm phải được ánh xạ sang kết quả nghiệp vụ rõ.
- Notification không được phát thông báo Confirmed khi lịch còn Pending.

**Phân biệt:** Characterization test giúp thấy hệ thống **đang hành xử thế nào**, không chứng nhận hành vi đó đúng. Khi phát hiện lỗi hiện tại, đội cần có test mới mô tả **hành vi đúng** trước hoặc trong quá trình sửa.

### 9.3. Bước hai: tạo cổng có ngữ nghĩa nội bộ

~~~java
// Giao diện minh họa, kiểu dữ liệu chỉ nêu ý nghĩa.
public interface ReservationGateway {
    ReservationResult submit(ReservationAttempt attempt);
    ReservationStatus query(ReservationReference reference);
}

public sealed interface ReservationResult
        permits Accepted, Rejected, Pending, Unknown {
}

public record Accepted(ReservationReference reference)
        implements ReservationResult {}
public record Rejected(String businessReason)
        implements ReservationResult {}
public record Pending(ReservationReference reference)
        implements ReservationResult {}
public record Unknown(String correlationId)
        implements ReservationResult {}
~~~

Đoạn code chỉ minh họa trên các phiên bản Java hỗ trợ sealed interface/record; chưa phải mã hoàn chỉnh. Nó thể hiện **các kết quả có ý nghĩa với Booking**, thay vì ép Booking xử lý hàng chục mã lỗi HTTP và payload của từng vendor.

**Điểm quan trọng:** Nếu vendor không thể truy vấn lại kết quả khi timeout, interface không được giả vờ cung cấp khả năng chắc chắn. Cần biểu diễn tình trạng **Unknown** và chính sách đối soát/phục hồi phù hợp.

### 9.4. Bước ba: chuyển đổi bằng adapter

Adapter của nhà cung cấp hiện tại ánh xạ những trạng thái, lỗi và payload đặc thù thành hợp đồng nội bộ. Nhóm viết **contract tests** để kiểm tra:

| Tình huống | Kết quả cổng nội bộ kỳ vọng |
| --- | --- |
| Vendor xác nhận thành công | **Accepted(reference)**. |
| Vendor trả kết quả cần chờ | **Pending(reference)**. |
| Vendor từ chối theo quy tắc | **Rejected(reason)**. |
| Timeout nhưng không biết yêu cầu đã xử lý chưa | **Unknown(correlationId)**, không mặc định Rejected. |
| Gửi lại cùng mã idempotency, vendor cam kết xử lý idempotent | Một kết quả tương thích với lần trước; không tạo thêm lịch ở phía đối tác. |

Kiểm thử với mock chỉ chứng minh adapter tuân thủ dữ kiện giả lập. Muốn biết vendor **thực sự** xử lý như vậy, cần kiểm thử sandbox/hợp đồng thật, dữ liệu phù hợp và đánh giá giới hạn môi trường.

### 9.5. Bước bốn: chuyển caller, đo và tháo phụ thuộc cũ

Nhóm chuyển BookingService qua ReservationGateway, rồi sửa controller và Notification để không nhập kiểu SDK. Việc này có thể thực hiện **theo lát cắt**, không cần viết lại đồng thời tất cả phần mềm.

~~~text
Trước:
UI -> Controller -> BookingService -> Vendor SDK
       \---------------------------> Vendor SDK
Notification ----------------------> Vendor SDK

Sau:
UI -> Booking API -> Booking Application -> ReservationGateway
                                                  ^
                                                  |
                                          Vendor Adapter -> Vendor API
Booking (Confirmed event) -> Notification
~~~

Sau khi consumer đã chuyển và test phù hợp, nhóm loại bỏ import/thư viện cũ không còn dùng. Có thể thử adapter mới sau feature flag và rollout có kiểm soát **nếu hệ thống cho phép**; không được dùng feature flag để âm thầm thực hiện hai giao dịch đặt lịch thực trên hai nhà cung cấp mà không có cơ chế ngăn đặt trùng.

### 9.6. Kiểm chứng lợi ích

Để biết việc tách mô đun hữu ích, nhóm xem:

- Thay đổi SDK có còn buộc sửa Booking domain và UI không?
- Số khu vực chỉnh sửa và nhóm cần phối hợp cho một yêu cầu tích hợp điển hình có giảm không?
- Contract test của cả hai adapter có cùng ý nghĩa nghiệp vụ không?
- Thời gian từ yêu cầu sửa một trường hợp retry đến khi giao an toàn có giảm không?
- Lỗi dữ liệu trùng, timeout chưa giải quyết hoặc notification sai có tăng không?

Không kết luận từ việc “số class tăng 12 nên kiến trúc tốt hơn”. Một số class mới giúp cô lập trách nhiệm; quá nhiều lớp ủy quyền vô nghĩa có thể làm chi phí đọc và điều tra lỗi tăng.

## 10. Kiểm thử tại ranh giới: kiểm tra điều đúng nhưng không khóa chi tiết nội bộ

Mô đun hóa làm tăng hiệu quả khi **test mô tả hợp đồng và bất biến**, thay vì sao chép cấu trúc triển khai. Nếu thay tên private helper khiến hàng trăm test hỏng dù hành vi không đổi, bộ test đang làm tăng coupling.

### 10.1. Một chiến lược kiểm thử cân bằng

| Tầng kiểm tra | Điều cần chứng minh | Ví dụ |
| --- | --- | --- |
| **Unit tests của domain** | Quy tắc, trạng thái, tính toán cốt lõi đúng. | Không cho hủy ngoài thời hạn, quy tắc không đặt trùng trong các trường hợp logic. |
| **Module/service tests** | API công khai của Booking đúng ở nhiều tình huống. | **requestBooking** trả Accepted/Pending/Rejected đúng và không làm rò SDK. |
| **Contract tests** | Bên cung cấp và bên tiêu thụ thống nhất hình dạng và **ngữ nghĩa** giao tiếp. | Adapter mapping timeout, retry, lỗi nghiệp vụ. |
| **Integration tests** | DB, queue, API và transaction thực phối hợp đúng. | Hai yêu cầu đồng thời không lưu hai lịch xung đột. |
| **End-to-end tests chọn lọc** | Lát cắt quan trọng từ UI tới trạng thái dùng được. | Khách đặt lịch và nhận trạng thái đúng qua các bước thực tế. |
| **Quan sát production** | Hành vi vận hành thật không lệch ngoài giả định. | Mức lỗi trùng, độ trễ, tỷ lệ Unknown, số sự kiện retry. |

Không cần viết hàng nghìn E2E test cho mọi nhánh nhỏ. Các điều kiện nghiệp vụ có thể được chứng minh ở **tầng thấp nhất có đủ thông tin**, rồi dùng một số test tích hợp/đầu-cuối để kiểm chứng ranh giới thực.

### 10.2. Kiểm thử hợp đồng khác kiểm thử giả lập

Giả sử unit test của Booking dùng một **fake ReservationGateway** trả Accepted. Nó chứng minh Booking xử lý Accepted theo cách mong muốn. Nó **không chứng minh** VendorReservationAdapter luôn trả đúng kết quả khi vendor timeout.

Cần kiểm tra ít nhất:

1. Contract của ReservationGateway định nghĩa các kết quả gì?
2. Adapter thực tế có ánh xạ đúng những tình huống nhận được không?
3. Vendor có đáp ứng những giả định mà adapter dựa vào không?
4. Nếu hợp đồng thay phiên bản, consumer cũ có còn dùng được không?

**Contract tests không thay thế** kiểm thử an toàn thông tin, bảo vệ bất biến giữa các giao dịch hoặc đo kết quả người dùng.

### 10.3. Bảo vệ ranh giới bằng kiểm tra tự động

Ở hệ thống Java, nhóm có thể chọn:

- **Package visibility / Java modules** khi có ích để giới hạn API lộ ra.
- **Quy tắc phụ thuộc trong build**, chỉ cho module được phép nhập module tương ứng.
- **Architecture tests** (ví dụ ArchUnit) để kiểm tra package/module không có vòng hoặc domain không phụ thuộc adapter.
- **CI** để kiểm tra refactoring không phá hợp đồng và hồi quy.
- **Code review** tập trung vào rò rỉ dữ liệu/kiểu SDK, vòng phụ thuộc và thay đổi nghĩa nghiệp vụ.

**Quy tắc kiến trúc không nên quá cứng.** Nếu exception là cần thiết do quyết định thiết kế có căn cứ, ghi lý do, người chịu trách nhiệm và kế hoạch xem lại; không dùng việc tắt tất cả test như cách mặc định để “chạy cho xong”.

### 10.4. Ví dụ quy tắc kiến trúc ở mức khái niệm

~~~text
Rule A: booking.domain KHÔNG import notification.*, vendor.sdk.*, web.*
Rule B: booking.application CHỈ truy cập booking.domain và các port rõ.
Rule C: adapter có thể phụ thuộc port, nhưng port không phụ thuộc adapter.
Rule D: Không có chu trình phụ thuộc giữa các module cấp cao.
Rule E: Chỉ module sở hữu dữ liệu mới trực tiếp sửa bảng/trạng thái của nó.
~~~

Chúng là quy tắc minh họa cần điều chỉnh theo kiến trúc thật. Ví dụ nếu một thư viện kiểu giá trị cơ bản được dùng nhiều nơi, nhóm có thể chấp nhận phụ thuộc chung. Quan trọng là **lý do được hiểu và kiểm chứng được**, thay vì chỉ là sơ đồ mong muốn.

## 11. Refactor mô đun từng bước mà vẫn giao giá trị

**Refactoring** là thay đổi cấu trúc code mà **giữ hành vi quan sát được** trong phạm vi đã định. Thay quy tắc đặt lịch từ “Confirmed ngay” thành “Pending” là **thay đổi hành vi**, có thể đi kèm refactoring nhưng phải có yêu cầu và kiểm thử rõ; không nên gọi tất cả thay đổi là refactor để tránh thảo luận nghiệp vụ.

### 11.1. Trình tự tách một mô đun đang bị coupling cao

1. **Chọn lát cắt có lý do rõ:** Một yêu cầu gần đây lan sang nhiều nơi, một lỗi thường tái diễn hoặc một vùng đang chặn việc giao.
2. **Vẽ dependency map thực tế:** Import, gọi runtime, shared schema, điểm triển khai chung, người phải review.
3. **Nêu hành vi cần giữ:** Lập test đặc tả hành vi đang có, bổ sung test yêu cầu đúng nếu phát hiện bug.
4. **Tạo hợp đồng hẹp:** API/port theo nhu cầu consumer, gồm lỗi và bất biến quan trọng.
5. **Tách adapter hoặc logic theo trách nhiệm:** Di chuyển từng phần qua ranh giới mới.
6. **Chuyển consumer tăng dần:** Một đường gọi hoặc một use case trước; giữ backward compatibility khi cần.
7. **Kiểm tra CI, contract, integration và dữ liệu:** Không chỉ nhìn unit test.
8. **Loại phụ thuộc cũ:** Sau khi tất cả đường dùng đã chuyển và được xác minh.
9. **Đo kết quả:** Thời gian thay đổi, test bị ảnh hưởng, lỗi, work item age và phản hồi Developers.

### 11.2. Strangler pattern và anti-corruption layer

Khi một hệ thống lớn không thể thay đồng loạt, nhóm có thể dùng **strangler pattern**: đặt đường chuyển tiếp, phát triển phần mới ở ranh giới rõ rồi chuyển dần từng chức năng, cuối cùng rút bỏ phần cũ.

Một **anti-corruption layer (ACL)** giúp dịch nghĩa giữa mô hình mới và mô hình cũ/đối tác, để những thuật ngữ hoặc hạn chế kỹ thuật từ phía ngoài không lây vào domain. ACL có thể là một adapter/mapping hẹp, không nhất thiết là một service độc lập.

~~~text
Booking Domain (ngôn ngữ nội bộ)
       |
       v
Reservation Port
       |
       v
Anti-Corruption / Vendor Adapter
       |
       v
Legacy / Partner API (ngôn ngữ riêng)
~~~

**Cảnh báo:** Nếu lớp chuyển đổi bắt đầu chứa mọi logic nghiệp vụ của Booking và các quyết định ưu tiên sản phẩm, ta chỉ chuyển “god module” sang chỗ khác. Giữ ACL phục vụ **dịch hợp đồng, giới hạn ảnh hưởng và giao tiếp**, không biến nó thành nơi duy nhất biết tất cả.

### 11.3. Giữ thay đổi nhỏ và có khả năng quay lại

Một kế hoạch tách mô đun mười hai tuần chỉ merge vào ngày cuối có rủi ro cao. Nên ưu tiên:

- Tạo một port và adapter cho một use case quan trọng trước.
- Đưa các test bảo vệ vào CI rồi mới chuyển dependency.
- Tránh thay schema và thay hợp đồng công khai đồng thời nếu không bắt buộc.
- Dùng **expand–migrate–contract** khi có consumer cũ.
- Dùng feature flag/canary nếu phù hợp với an toàn giao dịch; có kế hoạch rollback.
- Xem lại mô hình theo phản hồi thay vì chờ toàn bộ chương trình refactor xong.

**Không mọi thay đổi đều đảo ngược dễ dàng**: migration dữ liệu, giao dịch đã phát hành, thông báo đã gửi và API công khai có thể để lại hậu quả. Phải đánh giá khả năng rollback trước, không chỉ bật một cờ là xong.

### 11.4. Khi nào không nên tách mô đun ngay?

Không phải một lớp dài hoặc một import xuyên package đều phải được sửa trong Sprint hiện tại. Nên hoãn hoặc chỉ thử nhỏ nếu:

- Chưa có bằng chứng ranh giới hiện tại gây lỗi/chi phí đáng kể.
- Phần mềm còn ở giai đoạn rất sớm và mô hình chưa ổn định.
- Một thay đổi dự kiến không thể được kiểm chứng an toàn trong năng lực hiện tại.
- Tách ranh giới sẽ tạo chuỗi gọi mạng, transaction phân tán và chi phí mới lớn hơn lợi ích.

**Không hành động chỉ để theo đuổi “kiến trúc sạch” trên sơ đồ.** Nhưng cũng không chờ tới khi thay đổi trở nên bất khả thi mới đầu tư. Xem lại **tần suất thay đổi, mức lan truyền và rủi ro** định kỳ.

## 12. Phân tích ảnh hưởng thay đổi bằng một bài tập cụ thể

Giả sử Product Owner đề xuất yêu cầu:

> “Khách có thể đổi lịch trước giờ tư vấn ít nhất hai giờ; việc đổi phải bảo đảm không phát sinh hai lịch đã xác nhận cùng lúc.”

### 12.1. Xác định hành vi và điều kiện

**Đầu tiên, hỏi về nghiệp vụ:**

- “Ít nhất hai giờ” tính theo thời gian server, múi giờ khách hay giờ của Consultant?
- Có bao gồm đúng mốc **120 phút** không?
- Trạng thái **Pending** có được đổi không?
- Việc đổi có giữ lịch cũ nếu không giữ được lịch mới không?
- Có phí hoặc thông báo cần gửi sau đổi không?
- Nếu hai lần đổi được gửi đồng thời, trạng thái cuối cùng là gì?

Những câu hỏi có thể **mở rộng hợp đồng nghiệp vụ**. Mô đun hóa không thể thay thế quyết định chính sách chưa được làm rõ.

### 12.2. Bản đồ tác động theo mô đun

| Mô đun | Có thể cần thay gì? | Không nên tự nhiên phải thay gì? |
| --- | --- | --- |
| **Booking** | Chính sách đổi lịch, kiểm soát cạnh tranh, giao dịch và trạng thái kết quả. | Cấu hình SMTP và cách render email. |
| **Availability** | Tra cứu giờ thay thế; nếu quy tắc giữ chỗ đổi thì cập nhật hợp đồng. | Nhà cung cấp SMS. |
| **Notification** | Thêm mẫu thông báo đổi lịch sau khi thành công. | Bất biến chống trùng và ghi trực tiếp Appointment. |
| **Partner Integration** | Mapping thao tác đổi/giữ chỗ, timeout và đối soát nếu API yêu cầu. | Quy tắc hiển thị màu của giao diện. |
| **UI / API** | Hành vi chọn giờ mới, hiển thị trạng thái và thông báo lỗi phù hợp. | Nội bộ transaction, truy vấn schema của Booking. |
| **Tests/observability** | Boundary tests, contract tests, integration concurrency và đo lỗi. | Chi tiết private helper không ảnh hưởng hợp đồng. |

Không nên dùng bảng để nói “chỉ Booking được thay”. Một thay đổi **end-to-end** có những điểm tác động hợp lý. Mục tiêu là **giới hạn nơi phải sửa vì trách nhiệm thực**, không phải phủ nhận nhu cầu thay đổi ở nơi nhận kết quả.

### 12.3. Ma trận kiểm thử các trường hợp biên

| Dữ kiện | Kỳ vọng cần thống nhất |
| --- | --- |
| Đổi còn 121 phút | Hợp lệ nếu các điều kiện khác cho phép. |
| Đổi đúng 120 phút | Hợp lệ khi chính sách là “ít nhất hai giờ”; cần quy ước thời gian chính xác. |
| Đổi còn 119 phút | Từ chối với lý do rõ. |
| Giờ mới vừa bị khách khác chiếm | Không tạo lịch mới xung đột; lịch cũ được giữ hay hủy theo hợp đồng đã chọn. |
| Retry sau timeout | Không đổi hai lần ngoài ý muốn; có trạng thái đối soát. |
| Gửi thông báo thất bại | Không làm sai kết quả đổi lịch đã commit; có cơ chế retry phù hợp. |
| Người khác muốn đổi lịch không thuộc quyền | Từ chối và không lộ thông tin nhạy cảm. |

**Lưu ý:** Việc thử đúng mốc thời gian cần kiểm soát đồng hồ trong test và dùng kiểu thời gian phù hợp; chỉ so chuỗi ngày giờ có thể sai vì múi giờ hoặc DST. Quy tắc quyền truy cập và tính nhất quán phải được bảo vệ ở server, không chỉ UI.

### 12.4. Thế nào là kết quả tốt?

Sau một Sprint hoặc một vòng giao hàng nhỏ, nhóm có thể chứng minh:

- Quy tắc đổi trước hai giờ được kiểm tra nhất quán qua các entry point.
- Cơ chế chống trùng và đối soát có test đồng thời/timeout.
- Notification không trực tiếp sửa Booking, SDK vendor không rò vào domain.
- Không cần sửa các mô đun không liên quan.
- Increment hoặc feature đạt tiêu chí chất lượng và có phản hồi sử dụng thực.

Nếu phần mềm chạy đúng nhưng phải sửa toàn bộ hệ thống mỗi lần thay một chính sách giờ, đó là tín hiệu cần điều chỉnh cấu trúc. Nếu cấu trúc đẹp nhưng **không đảm bảo bất biến**, đó cũng chưa phải thiết kế tốt.

## 13. Đo khả năng thay đổi và thiết lập architecture fitness functions

Một sơ đồ module đẹp không chứng minh cấu trúc sẽ giúp nhóm phát triển trong sáu tháng tới. Cần quan sát **thay đổi thực tế** và, nơi có thể, tự động kiểm tra ranh giới bằng **architecture fitness functions** — các phép kiểm tra/quan sát giúp biết kiến trúc còn đáp ứng thuộc tính mong muốn không.

### 13.1. Nhóm chỉ số cần cân bằng

| Góc nhìn | Tín hiệu gợi ý | Điều nó giúp phát hiện | Giới hạn |
| --- | --- | --- | --- |
| **Change impact** | Số mô đun phải sửa cho một thay đổi thuộc một trách nhiệm rõ. | Mức lan truyền bất thường và phụ thuộc sai. | Một tính năng end-to-end có thể cần nhiều mô đun hợp lý. |
| **Dependency health** | Vòng phụ thuộc, import vào internals, độ phụ thuộc build. | Ranh giới bị xuyên hoặc hướng phụ thuộc bất hợp lý. | Không đo đủ coupling dữ liệu/runtime. |
| **Contract stability** | Số consumer phải đổi đồng thời khi một API thay. | Hợp đồng công khai dễ vỡ hoặc thiếu tương thích. | Hợp đồng ổn định có thể vẫn sai về nghiệp vụ. |
| **Delivery flow** | Cycle time, WIP, throughput, work item age, chờ review/owner. | Kiến trúc có làm chậm giao thay đổi không? | Bị ảnh hưởng bởi loại việc, đội ngũ và ưu tiên. |
| **Quality** | Lỗi hồi quy, lỗi dữ liệu, sự cố, mức kiểm chứng bất biến. | Tách mô đun có bảo vệ tính đúng đắn không? | Cần xem mức độ nghiêm trọng và cách phát hiện. |
| **Outcome** | Tỷ lệ hoàn tất tác vụ, phản hồi người dùng, thời gian nhận giá trị. | Cải tiến có giúp sản phẩm hữu ích hơn không? | Thay đổi outcome không tự chứng minh nguyên nhân kiến trúc. |
| **Developer experience** | Thời gian hiểu nơi sửa, số bước phối hợp, thời gian onboarding. | Chi phí nhận thức, phụ thuộc con người. | Tín hiệu định tính cần lấy từ nhiều người. |

Không nên đặt mục tiêu “mọi pull request chỉ sửa một mô đun”. Một thay đổi bổ sung trạng thái **Pending** có lý do để sửa Booking, API và giao diện. Quan trọng là **mức độ lan truyền có thể giải thích và không phá các mô đun không liên quan**.

### 13.2. Fitness functions minh họa

~~~text
FF-01: Không có chu trình phụ thuộc trực tiếp giữa các business modules.
FF-02: booking.domain không import vendor.sdk, notification.adapter, web.
FF-03: Chỉ booking.persistence được trực tiếp ghi trạng thái Appointment.
FF-04: Mọi adapter ReservationGateway phải thỏa bộ contract tests chung.
FF-05: Trường hợp hai yêu cầu đồng thời không tạo hai lịch đã xác nhận trùng.
FF-06: Thêm một template email không đòi sửa hoặc redeploy Booking domain.
FF-07: Khi đổi vendor, mã lỗi riêng không xuất hiện trong API/domain công khai.
~~~

Những phép kiểm tra có thể thuộc nhiều dạng:

- **Tĩnh:** kiểm tra import, dependency graph, package visibility và API công khai.
- **Động:** chạy contract tests, concurrency tests, fault injection ở môi trường an toàn.
- **Vận hành:** kiểm tra cách rollout, tỷ lệ lỗi, độ trễ và hành vi sau khi thay đổi.
- **Thực nghiệm định kỳ:** lấy một thay đổi điển hình, ghi nơi phải sửa và thời gian từ hiểu yêu cầu tới giao.

Không nên chọn fitness function chỉ vì dễ tự động hóa. Một quy tắc **không có import vòng** hữu ích, nhưng chưa bảo đảm không có vòng workflow do event/call runtime. Cần kết hợp nhiều bằng chứng.

### 13.3. Ví dụ thử “đổi nhà cung cấp SMS”

Nhóm chọn một thay đổi mô phỏng:

> “Chuyển từ nhà cung cấp SMS A sang B nhưng giữ nguyên quy tắc đặt lịch và nội dung thông báo.”

**Kỳ vọng kiến trúc:** Chủ yếu sửa adapter/cấu hình/kiểm thử của Notification; Booking không biết payload và SDK của nhà cung cấp. Nếu phải sửa Appointment, BookingPolicy và các trang UI dù **ý nghĩa nghiệp vụ không đổi**, đó là dấu hiệu rò rỉ chi tiết.

**Lưu ý:** Một nhà cung cấp SMS mới có khả năng, giới hạn hoặc nghĩa vụ khác, vì vậy hợp đồng nội bộ có thể **thực sự cần đổi**. Mục tiêu không phải giấu sự khác biệt quan trọng, mà tránh để thông tin kỹ thuật không cần thiết lan tràn.

### 13.4. Không biến chỉ số kiến trúc thành mục tiêu dễ bị thao túng

Nếu khen thưởng theo **số interface tạo ra**, Developers có thể dựng nhiều lớp vô nghĩa. Nếu phạt theo **số module sửa trên một PR**, nhóm có thể gom mọi thứ vào một module khổng lồ. Nếu đo **số test xanh** mà bỏ qua kiểm thử tích hợp, hệ thống có thể vẫn sai khi nhiều request đến đồng thời.

Sử dụng số liệu như **công cụ chẩn đoán và học**, không như bảng xếp hạng cá nhân hay bộ định nghĩa “kiến trúc sạch” duy nhất.

## 14. Vòng thiết kế tiến hóa trong một nhịp phát triển Agile

Thiết kế mô đun phát huy tác dụng khi là một phần của **vòng lặp sản phẩm và kỹ thuật**, thay vì một dự án kiến trúc tách khỏi mọi phản hồi thực.

~~~mermaid
flowchart TD
    A["Nhu cầu mới / lỗi / phản hồi"] --> B["Làm rõ hành vi và bất biến"]
    B --> C["Vẽ impact và phụ thuộc hiện tại"]
    C --> D{"Cấu trúc đủ để thay đổi an toàn?"}
    D -->|Có| E["Thực hiện lát cắt nhỏ"]
    D -->|Chưa| F["Test bảo vệ rồi refactor ranh giới"]
    F --> E
    E --> G["Unit + contract + integration tests"]
    G --> H["Giao có kiểm soát và quan sát"]
    H --> I["Đo outcome, flow, lỗi và chi phí thay đổi"]
    I --> J["Cập nhật backlog và hiểu biết kiến trúc"]
    J -. "Vòng tiếp theo" .-> A
~~~

### 14.1. Thay đổi do phản hồi người dùng

Giả sử khách muốn **đổi lịch** và nhóm nhận ra logic Appointment đang nằm rải rác ở controller, notification handler và database trigger. Thay vì viết thêm bản sao quy tắc ở giao diện mới, nhóm:

1. Xác định chính sách đổi lịch cùng Product Owner và người hiểu nghiệp vụ.
2. Đánh dấu những nơi đang áp dụng quy tắc.
3. Viết test có thể chứng minh trạng thái đúng.
4. Tập trung quy tắc ở Booking phù hợp.
5. Tạo API/use case rõ cho giao diện cũ và mới.
6. Giao lát cắt nhỏ, xem lỗi và phản hồi người dùng.

Nhóm có thể cần một phần **refactor đi kèm feature**. Không nên ghi toàn bộ công việc chất lượng là “không tạo giá trị” chỉ vì người dùng không nhìn thấy class mới; giảm lỗi và tăng khả năng đổi hướng là một phần của giá trị.

### 14.2. Thay đổi chỉ ở kiến trúc khi nào hợp lý?

Không phải mọi cải tiến kỹ thuật đều phải đi kèm một feature ngay hôm nay. Nếu một nút thắt build, schema hoặc code coupling thường xuyên làm chậm các Sprint, một hạng mục kiến trúc độc lập có thể hợp lý. Cần diễn đạt:

- **Vấn đề hiện tại:** Ví dụ mọi thay đổi SMS làm Booking phải rebuild.
- **Chi phí có bằng chứng:** Số lần sửa dây chuyền, lỗi hoặc thời gian chờ.
- **Phương án nhỏ nhất:** Tách một adapter/hợp đồng trước.
- **Lợi ích kỳ vọng:** Chuyển vendor không sửa nghiệp vụ, test adapter độc lập.
- **Cách kiểm chứng:** Thử thay provider hoặc kiểm tra dependency graph/contract tests.

Điều cần tránh là “viết lại toàn bộ để sạch hơn” mà không có ranh giới, tiêu chí thành công hoặc kế hoạch rollback.

### 14.3. Scrum: giới hạn tác động thay đổi để giữ Sprint Goal

Trong Scrum:

- **Product Owner** chịu trách nhiệm tối đa hóa giá trị và quản lý hiệu quả Product Backlog.
- **Developers** lựa chọn công việc cho Sprint, tạo Sprint Backlog, giữ chất lượng và tạo Increment.
- **Scrum Master** giúp nhóm vận dụng Scrum và cải tiến hiệu quả.

Một thay đổi về yêu cầu có thể làm Developers xem lại cấu trúc mô đun, thương lượng phạm vi với Product Owner khi học thêm và **không giảm Definition of Done**. Các kỹ thuật refactoring và test giúp tạo Increment có ích mà không phải sửa cả hệ thống mỗi lần thay Sprint Backlog.

**Sprint Goal** cung cấp trọng tâm; nó không biến mọi item ban đầu thành danh sách bất biến. Đổi cấu trúc có giới hạn để bảo vệ tính đúng đắn có thể hỗ trợ mục tiêu tốt hơn việc đánh dấu Done nhiều ticket nhưng vẫn có bug.

### 14.4. Kanban: nhìn thấy chi phí phối hợp của phụ thuộc

Kanban có thể trực quan hóa việc đang chờ **review class owner**, **kiểm thử liên mô đun**, **đổi schema** hoặc **phê duyệt đối tác**. Thực hành giới hạn WIP và kéo việc theo khả năng hoàn tất giúp tránh mở thêm feature khi những thay đổi cũ đang bị chặn.

Nếu work item age tăng mạnh tại bước review của một mô đun dùng chung, đó có thể là **dấu hiệu coupling tổ chức/kiến trúc**. Đội cần kiểm tra cả quyền sở hữu, kiến thức và ranh giới module, không chỉ tăng số cuộc họp.

### 14.5. XP: khả năng sửa kiến trúc an toàn

**TDD, CI, refactoring và pair programming** của Extreme Programming bổ trợ thiết kế tiến hóa:

- TDD cho những quy tắc đã rõ tạo lưới bảo vệ khi sửa cấu trúc.
- CI phát hiện lỗi tích hợp sớm giữa các mô đun.
- Refactoring liên tục tránh dồn nợ cấu trúc tới cuối dự án.
- Pairing và chia sẻ tri thức giảm phụ thuộc một người hiểu một module.
- Các lát cắt nhỏ giúp nhận phản hồi trước khi hướng thiết kế trở nên quá khó sửa.

**TDD không tự chứng minh kiến trúc đúng**, nhưng kiểm thử chất lượng là một điều kiện quan trọng để cải tiến ranh giới mà không phải đánh cược với dữ liệu người dùng.

## 15. Những phản mẫu thường khiến mô đun hóa thất bại

| Phản mẫu | Dấu hiệu | Hệ quả | Điều chỉnh |
| --- | --- | --- | --- |
| **God module / God service** | Một nơi chứa booking, email, thanh toán, báo cáo. | Mọi thay đổi đều ảnh hưởng cùng nơi; khó hiểu và kiểm thử. | Tìm trách nhiệm và lý do thay đổi khác nhau, tách lát cắt có test. |
| **Shared kernel quá rộng** | Mọi module cùng sửa mô hình Customer/Appointment chung. | Thay một field gây rebuild/deploy hàng loạt. | Chia shared contract nhỏ, ổn định hoặc mapping theo consumer. |
| **Anemic domain bị dàn trải** | Quy tắc nghiệp vụ bị viết lặp ở controller, UI, trigger, adapter. | Bất biến không nhất quán khi một đường gọi thay đổi. | Quy định nơi sở hữu nghiệp vụ; API phục vụ hành vi. |
| **Interface cho mọi class** | Nhiều lớp chỉ ủy quyền một dòng, không có biến thể hoặc boundary. | Khó đọc và debug, chi phí thiết kế tăng. | Chỉ trừu tượng hóa phụ thuộc có lý do rõ. |
| **Microservices quá sớm** | Một tính năng cần gọi/triển khai đồng thời nhiều service nhỏ. | Network coupling, transaction phân tán, phí vận hành cao. | Cân nhắc modular monolith và ranh giới dữ liệu trước. |
| **Truy cập bảng xuyên module** | Notification sửa trực tiếp Appointment. | Lộ schema, phá bất biến và migration khó. | API/event/projection có hợp đồng rõ, ownership dữ liệu. |
| **Event không có ngữ nghĩa ổn định** | Tên EventChanged chung, payload nguyên object nội bộ. | Consumer lệ thuộc cấu trúc và thứ tự xử lý. | Event nói sự thật nghiệp vụ, phiên bản và schema tối thiểu. |
| **Bỏ qua trạng thái chưa xác định** | Timeout được xem là thất bại chắc chắn. | Retry tạo trùng giao dịch hoặc sai dữ liệu. | Mô hình Unknown/Pending, idempotency, đối soát. |
| **Test khóa private details** | Đổi tên helper làm hàng trăm test thất bại. | Cản refactor ngay cả khi hành vi giữ nguyên. | Test hợp đồng/hành vi; internal test đúng mức cần thiết. |
| **Phụ thuộc vòng tĩnh** | Booking → Notification → Booking. | Khó build độc lập, khó định trách nhiệm. | Đổi hướng dependency, port/adapter hoặc tách trách nhiệm. |
| **Phụ thuộc vòng runtime** | Event handler gọi ngược để hoàn tất transaction ban đầu. | Khó truy vết, timeout và lỗi lan rộng. | Xác định owner của workflow, rút chuỗi đồng bộ nếu phù hợp. |
| **Module được định nghĩa bằng tổ chức** | Team A/Team B là tên package, không theo miền/lý do đổi. | Tái tổ chức nhân sự gây đổi cấu trúc phần mềm. | Thiết kế quanh trách nhiệm bền vững và giao tiếp có nghĩa. |
| **Tách mọi mô đun giống nhau** | Mỗi module đúng ba file và một interface. | Ranh giới hình thức không phản ánh độ phức tạp. | Điều chỉnh kích thước theo cohesive responsibility. |
| **Big-bang rewrite** | Viết lại hàng tháng, ít giao Increment, rollback khó. | Rủi ro cao và mất phản hồi. | Refactor/strangler theo lát cắt, CI và phép đo rõ. |
| **Chỉ đo số file thay đổi** | Tăng điểm kiến trúc khi gom mọi thứ vào một file. | Che rủi ro tích hợp/độ phức tạp. | Đo change impact cùng hành vi, flow và chất lượng. |

### 15.1. Một dấu hiệu nhanh: sửa một thứ nhưng test nơi khác cùng hỏng

Giả sử thay cách gửi SMS nhưng unit tests của BookingPolicy hỏng vì import một DTO của SDK. Đây là tín hiệu module Booking đã phụ thuộc vào chi tiết Notification. Hãy tìm **đường truyền phụ thuộc thực**, không chỉ đổi package của DTO sang tên **common**.

Ngược lại, nếu thay chính sách hủy và kiểm thử Booking lẫn phần thông báo về hủy cùng thay, đó có thể là **tác động có ý nghĩa nghiệp vụ**. Phân loại đúng mới tránh “sửa cấu trúc” nhằm che mối liên hệ cần thiết.

### 15.2. Hệ quả của “đưa mọi thứ vào common”

Thư viện dùng chung giúp giảm lặp **khi thật sự là khái niệm chung ổn định** như một kiểu giá trị số học hoặc công cụ serialization đã chuẩn hóa. Nhưng nếu đặt toàn bộ Customer, Appointment, NotificationMessage, VendorResponse, BusinessRule và các enum vào một common module, mọi nhóm phải theo phiên bản mới cùng nhau.

**Lặp một lượng nhỏ cấu trúc đơn giản qua ranh giới** đôi khi rẻ hơn tạo shared semantic model dễ vỡ. Chọn dựa trên **chi phí thay đổi và khả năng tương thích**, không chỉ đếm dòng code trùng nhau.

### 15.3. Đừng đổi hướng phụ thuộc chỉ để giấu vòng

Nếu Booking và Notification đang gọi nhau vì quy trình nghiệp vụ chưa xác định ai chịu trách nhiệm, tạo thêm hai interface có thể làm **vòng import biến mất** nhưng **vòng runtime vẫn còn**. Cần trả lời:

- Ai là chủ sở hữu trạng thái cuối cùng?
- Đâu là hành động nghiệp vụ chủ đạo?
- Thành phần nào chỉ phản ứng sau kết quả?
- Điều gì được phép eventual, điều gì phải có nhất quán mạnh?
- Khi một bước thất bại, ai quyết định retry, hủy bù hoặc đối soát?

Chỉ sau khi rõ luồng mới chọn interface, event hay transaction.

## 16. Ra quyết định về ranh giới bằng ma trận đánh đổi

Không có thiết kế “ít phụ thuộc nhất” đúng cho mọi tình huống. Một số phụ thuộc trực tiếp là hợp lý nếu hai phần luôn đổi cùng nhau và cần transaction đơn giản. Một số ranh giới phải chịu chi phí phối hợp vì cần bảo mật hoặc tổ chức độc lập.

| Phương án | Lợi ích | Chi phí/rủi ro | Khi nào đáng thử |
| --- | --- | --- | --- |
| **Giữ hai logic trong một mô đun cohesive** | Ít overhead, dễ giữ transaction, debug đơn giản. | Ranh giới có thể rộng nếu lý do đổi bắt đầu tách. | Khái niệm gắn chặt, thường thay cùng nhau. |
| **Tách hai mô đun trong cùng ứng dụng** | API rõ, kiểm soát import, dễ refactor/tích hợp. | Cần quản lý giao tiếp và visibility. | Hai trách nhiệm có lý do đổi khác nhau. |
| **Dùng port + adapter** | Che nhà cung cấp/chi tiết hạ tầng, test linh hoạt. | Tăng số type, mapping và trừu tượng. | Chi tiết biến động cao hoặc là boundary quan trọng. |
| **Dùng event bất đồng bộ** | Giảm chờ đồng bộ, phân tách một số thời điểm xử lý. | Eventual consistency, retry, idempotency, quan sát khó hơn. | Consumer phản ứng sau sự thật nghiệp vụ, độ trễ chấp nhận được. |
| **Tách thành service triển khai riêng** | Deploy/scale/vòng đời độc lập nếu thiết kế đúng. | Network, ops, dữ liệu và contract complexity. | Nhu cầu độc lập rõ, tổ chức đủ năng lực vận hành. |
| **Gộp những mô đun bị gọi chéo liên tục** | Giảm chuỗi gọi, đơn giản hóa bất biến và ownership. | Có thể mất độc lập phát hành ở một số nơi. | Ranh giới hiện tại cắt ngang một trách nhiệm chung. |

### 16.1. Sáu câu hỏi trước khi tách

1. Hai phần có **thay đổi vì cùng một lý do** không?
2. Có **bất biến nào buộc chúng phải nhất quán** tại một thời điểm không?
3. Bên sử dụng có thực sự cần biết **chi tiết nội bộ** của bên cung cấp không?
4. Mô đun sẽ có **hợp đồng đủ nhỏ và đủ rõ** sau khi tách chứ?
5. Nếu tách, **số lần gọi, mapping, retry, vận hành và số nhóm phối hợp** tăng tới đâu?
6. Có thể **thử một lát cắt** với test rồi đánh giá thực tế thay vì cam kết viết lại không?

### 16.2. Quy tắc thực dụng: hoãn trừu tượng nhưng không hoãn tính đúng

Với một phần hệ thống chưa có nhu cầu tách rõ, giữ thiết kế đơn giản có thể hợp lý. Nhưng **không trì hoãn kiểm soát quyền truy cập, bất biến dữ liệu hoặc chuẩn chất lượng** chỉ vì “sau này mới cần kiến trúc”.

Một chiến lược là **chừa đường thay đổi** ở boundary có rủi ro (ví dụ SDK đối tác) bằng adapter nhỏ, nhưng không dựng framework plugin tổng quát cho mười provider chưa từng tồn tại.

## 17. Bài tập tình huống và đáp án định hướng

### Tình huống A — Thay email buộc sửa Booking

Một nhóm muốn thêm ngôn ngữ tiếng Việt và tiếng Anh cho email xác nhận. Họ phải sửa BookingService vì BookingService đang tự ghép nội dung HTML, lưu SMTP settings và gọi API đặt lịch.

**Câu hỏi:**

1. Những trách nhiệm nào đang trộn trong BookingService?
2. Có thể tách hợp đồng giữa Booking và Notification ra sao?
3. Cần kiểm thử gì để bảo đảm không gửi email “đã xác nhận” khi lịch Pending?

**Hướng giải:** Booking sở hữu trạng thái lịch, Notification sở hữu rendering và gửi tin. Booking có thể công bố **BookingConfirmed** sau khi trạng thái đã commit; Notification xử lý template/ngôn ngữ và retry. Kiểm thử phải xác minh chỉ có thông báo đúng trạng thái, không dựa vào việc controller tự gắn email ngay khi người dùng nhấn nút.

### Tình huống B — Vòng phụ thuộc giữa ba mô đun

Dependency graph có đường:

~~~text
booking -> notification
notification -> customer
customer -> booking
~~~

**Câu hỏi:**

1. Vì sao vòng phụ thuộc gây khó khăn khi thay đổi?
2. Nếu chỉ chuyển những lời gọi vào interface chung mà nghiệp vụ vẫn gọi vòng, đã giải quyết chưa?
3. Mô đun nào nên sở hữu kết quả đặt lịch và Notification cần dữ kiện gì?

**Hướng giải:** Vòng tĩnh và runtime cần được phân tích riêng. Booking phải sở hữu trạng thái lịch; Notification nhận kết quả đã xác nhận qua hợp đồng/sự kiện. Customer/Identity cung cấp thông tin nhận diện theo nhu cầu, tránh trả toàn bộ đối tượng nội bộ. Interface chỉ có ích khi thay **hướng phụ thuộc và trách nhiệm thật**, không che vòng nghiệp vụ.

### Tình huống C — Tách microservice để “đỡ phụ thuộc”

Một ứng dụng đơn khối có hai mô đun Booking và Availability. Người quản lý muốn tách ngay thành hai microservices. Nhưng mỗi lần tạo lịch phải kiểm tra và giữ chỗ nhất quán, cùng một bảng và cần transaction. Đội chưa có distributed tracing hoặc quy trình rollout hợp đồng.

**Câu hỏi:**

1. Tách dịch vụ lúc này sẽ thêm các loại coupling/rủi ro nào?
2. Có thể cải tiến mô đun trong cùng ứng dụng trước không?
3. Bằng chứng nào khiến việc tách triển khai độc lập trở nên đáng cân nhắc?

**Hướng giải:** Tách quá sớm có thể tạo phân tán transaction, lỗi mạng, chia quyền sở hữu dữ liệu khó và deploy phối hợp. Nên xác định nghiệp vụ/ownership và có test bảo vệ bất biến trong modular monolith trước. Khi có nhu cầu scale/vòng đời/phân quyền độc lập rõ và năng lực quan sát/contract, mới cân nhắc service riêng.

### Tình huống D — Test hỏng hàng loạt sau refactor không đổi hành vi

Developers đổi tên private method trong BookingService để làm rõ trách nhiệm. Hai trăm unit tests hỏng vì mock trực tiếp private implementation và assert trình tự gọi các helper. Không có hành vi người dùng nào đổi.

**Câu hỏi:**

1. Bộ test đang phụ thuộc vào điều gì?
2. Nên giữ test nào và viết lại test nào?
3. Làm sao vẫn chứng minh việc đặt lịch chống trùng và kiểm thử cạnh tranh đúng?

**Hướng giải:** Test đã khóa vào chi tiết triển khai. Chuyển trọng tâm sang API/use case, quy tắc domain và hợp đồng observable, giữ unit test nội bộ cho thuật toán phức tạp khi có ích. Thêm integration tests cho transaction và concurrent booking; không đơn giản xóa hết test để build xanh.

### Tình huống E — Mã nhà cung cấp rò vào domain

Nhà cung cấp lịch trả các mã **E17, E23, E99**, và BookingPolicy dùng trực tiếp những mã này để quyết định trạng thái. Nhà cung cấp mới có mã lỗi khác, nhưng ý nghĩa nghiệp vụ giống nhau.

**Câu hỏi:**

1. Vì sao đây là coupling theo hợp đồng/semantics?
2. Tạo abstraction thế nào để không làm mất thông tin quan trọng?
3. Những trường hợp nào cần kiểm thử với adapter thật?

**Hướng giải:** Chuyển mã lỗi vendor sang kết quả miền có nghĩa như Accepted, Rejected, Pending, Unknown qua adapter; giữ thông tin cần đối soát/log an toàn. Viết contract tests cho mapping, thử timeout/retry/idempotency với sandbox phù hợp và đo các tình huống chưa xác định. Đừng ánh xạ mọi lỗi thành “Rejected” vì như vậy có thể gây gửi lặp và tạo trùng.

### Tình huống F — Thêm chính sách hủy trước hai giờ

Yêu cầu mới: Khách được hủy lịch trước khi phiên bắt đầu ít nhất hai giờ; lịch chưa xác nhận có quy tắc khác. Hiện code kiểm tra điều kiện hủy ở UI và một cron job, còn Booking chỉ lưu trạng thái.

**Câu hỏi:**

1. Nơi nào nên sở hữu quy tắc nghiệp vụ?
2. Những mốc thời gian biên cần kiểm thử?
3. Nếu UI mobile và web dùng chung API, thiết kế nào giảm nguy cơ hai nơi xử lý khác nhau?

**Hướng giải:** Đưa chính sách vào domain/module có thẩm quyền, công bố hành vi kiểm tra/hủy rõ cho các entry point. Test 119/120/121 phút, quyền, múi giờ, trạng thái Pending và điều kiện cạnh tranh. UI có thể hiển thị thông tin hướng dẫn, nhưng server phải tự bảo vệ quy tắc.

### Tình huống G — Một shared library đổi kéo theo cả tổ chức

Tất cả sản phẩm cùng dùng module **shared-model**, chứa hàng trăm DTO và enum. Thêm một trạng thái Appointment khiến hơn mười nhóm phải cập nhật dependency, chạy build và đôi khi thay cách parse dù không dùng Booking.

**Câu hỏi:**

1. Những coupling nào đang xảy ra?
2. Có nên đưa tất cả DTO sang một service chung không?
3. Làm sao chia hợp đồng theo consumer và chuyển đổi tăng dần?

**Hướng giải:** Shared model quá rộng gây coupling build, semantics và phát hành. Phân tách hợp đồng có sở hữu rõ, chỉ công bố kiểu cần thiết; dùng version/adapter và hỗ trợ tương thích khi chuyển consumer. Đổi tất cả sang một shared service có thể chỉ chuyển coupling sang runtime, không giải quyết gốc rễ.

### Bài tập tính độ lan truyền và chi phí phối hợp

Một thay đổi **đổi nhà cung cấp SMS** trong hệ thống cũ buộc sửa **6 mô đun**, cần review của **4 đội** và mất **8 ngày làm việc** từ bắt đầu đến kiểm chứng. Sau khi tạo boundary Notification, một lần đổi provider tương đương yêu cầu sửa **2 mô đun**, có **2 đội** tham gia và mất **4 ngày**.

1. Số mô đun bị ảnh hưởng giảm bao nhiêu phần trăm?
2. Thời gian thay đổi giảm bao nhiêu phần trăm?
3. Vì sao không thể khẳng định chính boundary mới gây ra toàn bộ mức cải thiện?
4. Cần đối chiếu những tín hiệu chất lượng và kết quả nào?

**Đáp án tham khảo:** (1) \((6-2)/6\times100\%\approx66{,}7\%\); (2) \((8-4)/8\times100\%=50\%\); (3) loại thay đổi, năng lực, độ phức tạp, môi trường và đối tác có thể khác; (4) contract tests, lỗi thông báo, tỷ lệ giao đúng, dữ liệu riêng tư, thời gian phục hồi và kết quả người dùng.

## 18. Workshop: phân rã mô đun từ một user story

### 18.1. Đề bài

Một nhóm năm Developers và Product Owner đang xây hệ thống đặt lịch. Ban đầu:

- **BookingService** xử lý đặt lịch, hủy, tạo email và gọi SDK đối tác.
- **CalendarUtil** chứa cả tính giờ trống và chuyển đổi múi giờ.
- **NotificationService** đọc và ghi trực tiếp bảng Appointment.
- Controller gọi database để xem còn giờ, rồi gọi BookingService ghi lịch.
- Một class owner duy nhất được quyền sửa BookingService.

Yêu cầu mới:

> “Khách có thể đổi lịch trước giờ bắt đầu ít nhất hai giờ, trong khi yêu cầu gửi lặp và API đối tác timeout không được tạo lịch trùng.”

### 18.2. Các bước thực hành 60–75 phút

| Thời lượng gợi ý | Công việc nhóm | Đầu ra |
| --- | --- | --- |
| 0–10 phút | Viết kết quả người dùng, quy tắc và các tình huống chưa rõ. | Một mục tiêu và bảng giả định/bất biến. |
| 10–25 phút | Vẽ sơ đồ phụ thuộc code, runtime và dữ liệu hiện tại. | Dependency map, các vòng và chỗ rò chi tiết. |
| 25–40 phút | Đề xuất ranh giới dựa trên trách nhiệm và lý do thay đổi. | Bảng các mô đun, dữ liệu sở hữu, API công khai. |
| 40–50 phút | Chọn một port/adapter và diễn giải kết quả khi timeout. | Hợp đồng đầu vào/đầu ra, lỗi và trạng thái chưa xác định. |
| 50–60 phút | Thiết kế test bảo vệ hành vi, bản đồ impact và bước refactor đầu. | Test cases, một lát cắt có thể làm an toàn. |
| 60–75 phút (nếu có) | Thử thay đổi giả định và phản biện mô hình. | Quyết định giữ/sửa ranh giới và phép đo. |

### 18.3. Mẫu quyết định kỹ thuật

| Hạng mục | Ghi chép của nhóm |
| --- | --- |
| Người dùng cần kết quả nào? | ... |
| Bất biến nghiệp vụ phải bảo vệ? | ... |
| Những thay đổi dự kiến và lý do thay đổi? | ... |
| Các mô đun hiện tại và phụ thuộc sai? | ... |
| Các mô đun đề xuất và owner? | ... |
| API/port công khai, input/output và lỗi? | ... |
| Ai được đọc/ghi dữ liệu nào? | ... |
| Đồng bộ hay bất đồng bộ, vì sao? | ... |
| Những test behavior/contract/integration cần bổ sung? | ... |
| Chi phí/mối nguy mới do tách mô đun? | ... |
| Bước refactor có thể đảo ngược trước? | ... |
| Tín hiệu nào chứng minh impact giảm? | ... |

### 18.4. Một phương án tham khảo

1. **Booking** sở hữu Appointment, quyền và quy tắc đổi lịch, transaction chống trùng.
2. **Availability** cung cấp truy vấn giờ hợp lệ; ranh giới cần làm rõ khi nào việc kiểm tra khả dụng là thông tin tham khảo và khi nào phải giữ chỗ nguyên tử.
3. **Partner Integration** dịch SDK đối tác sang ReservationGateway, bao gồm Accepted/Pending/Rejected/Unknown.
4. **Notification** nhận yêu cầu gửi dựa trên kết quả đã commit, không sửa bảng Booking.
5. **UI** chỉ dùng API đặt/đổi lịch với lỗi có nghĩa, không tự quyết định tính hợp lệ cuối cùng.
6. **Tests** bảo vệ quyền, mốc giờ, retry, concurrent requests và timeout; architecture checks ngăn SDK lan ngược vào domain.

Trước khi triển khai tách service, nhóm có thể làm các ranh giới trên trong cùng một ứng dụng, kiểm tra độ phức tạp và chi phí. **Đáp án khác có thể đúng** nếu giải thích được bất biến, trách nhiệm, hợp đồng và đánh đổi.

## 19. Checklist cho một thay đổi có kiểm soát

### Khi xác định ranh giới

- [ ] Đã biết **người dùng/miền** cần kết quả gì và quy tắc nào phải luôn đúng.
- [ ] Các mô đun được nhóm theo trách nhiệm và lý do thay đổi, không chỉ theo tầng kỹ thuật.
- [ ] Có người chịu trách nhiệm làm rõ nghĩa của mỗi hợp đồng và dữ liệu.
- [ ] Phụ thuộc tĩnh, runtime, dữ liệu và triển khai quan trọng đã được xem xét.
- [ ] Không có vòng phụ thuộc không chủ đích; các trường hợp phải giữ vòng được hiểu và quản lý.
- [ ] Quyết định trừu tượng hóa có lý do cụ thể, không tạo interface chỉ để tăng số interface.
- [ ] Đã cân nhắc modular monolith trước khi chấp nhận chi phí phân tán.

### Khi thiết kế và thực hiện

- [ ] Hợp đồng ghi rõ hành vi, kết quả, trường hợp lỗi, quyền và trạng thái chưa xác định.
- [ ] Domain không nhập trực tiếp payload và kiểu của các SDK bên ngoài nếu không cần thiết.
- [ ] Các bất biến quan trọng được bảo vệ ở nơi có thẩm quyền, không chỉ ở UI.
- [ ] Dữ liệu nội bộ không bị mô đun khác sửa tùy tiện.
- [ ] Nếu dùng event, có chính sách giao lại, idempotency, đối soát, quyền và quan sát.
- [ ] Có test bảo vệ hành vi trước khi refactor, test hợp đồng và integration tại ranh giới.
- [ ] Thay đổi được chia nhỏ, có kế hoạch chuyển consumer/schema và rollback phù hợp.
- [ ] Không hạ chuẩn chất lượng để làm tiến độ hoặc sơ đồ trông đẹp hơn.

### Khi kiểm chứng giá trị

- [ ] Một thay đổi thường gặp có cần ít mô đun/đội phối hợp hơn không?
- [ ] Tác động còn lại có giải thích được bằng lý do nghiệp vụ không?
- [ ] Thời gian từ yêu cầu tới Increment/phát hành an toàn có được cải thiện?
- [ ] Lỗi hồi quy, lỗi dữ liệu, rủi ro bảo mật và chi phí vận hành có được theo dõi?
- [ ] Developers có dễ hiểu nơi cần thay đổi và khả năng kiểm thử hơn không?
- [ ] Những quy tắc kiến trúc cần thiết đã được kiểm tra tự động trong CI?
- [ ] Nhóm có thể thay đổi ranh giới khi học thêm, thay vì xem sơ đồ ban đầu là bất biến?

## 20. Ghi nhớ cốt lõi

**Thiết kế mô đun để giảm phụ thuộc** không có nghĩa chia phần mềm thành nhiều mảnh nhất có thể. Nó có nghĩa **đặt đúng trách nhiệm đúng chỗ, bảo vệ chi tiết dễ thay đổi sau hợp đồng rõ và kiểm soát những chỗ các phần cần phối hợp**.

Nhớ năm câu hỏi:

1. **Mô đun này chịu trách nhiệm về điều gì?** Các thành phần bên trong có cùng lý do thay đổi không?
2. **Nó phụ thuộc vào điều gì?** Phụ thuộc vào ngữ nghĩa cần thiết hay chi tiết công nghệ dễ đổi?
3. **Nó sở hữu trạng thái và bất biến nào?** Có mô đun khác được phép sửa trực tiếp không?
4. **Nếu thay một quy tắc, ảnh hưởng sẽ lan tới đâu?** Có cách nào tách tác động tình cờ mà vẫn giữ tương tác nghiệp vụ cần thiết?
5. **Làm sao chứng minh thiết kế mới tốt hơn?** Kiểm thử hành vi, contract, integration, dữ liệu flow, lỗi và outcome thay vì đếm package/interface.

**Thiết kế tiến hóa** là lặp lại vòng **hiểu nhu cầu → xác định ranh giới → giao lát cắt nhỏ → kiểm chứng → refactor khi có bằng chứng**. Các mô đun có tính gắn kết cao, hợp đồng có nghĩa, phụ thuộc đúng hướng và lưới kiểm thử vững sẽ giúp nhóm đón nhận yêu cầu mới **mà không phải sửa dây chuyền hoặc đánh cược chất lượng**.

Scrum giúp đặt **mục tiêu và nhịp kiểm tra–thích ứng**; Kanban giúp nhìn **điểm chặn, WIP và thời gian tới giá trị**; XP giúp **test, tích hợp và refactor an toàn**. Thiết kế mô đun tạo nền để cả ba cách tiếp cận ấy có thể giao phần mềm tăng dần, học từ người dùng và cải tiến liên tục.

### Tài liệu tham khảo để tìm hiểu sâu

- David L. Parnas (1972), *On the Criteria To Be Used in Decomposing Systems into Modules* — nguyên tắc mô đun hóa dựa trên việc che giấu những quyết định thiết kế có khả năng thay đổi.
- Robert C. Martin, *Clean Architecture* (2017) — hướng phụ thuộc, ranh giới và nguyên tắc phân tách chính sách với chi tiết.
- Martin Fowler, *Refactoring: Improving the Design of Existing Code*, 2nd edition (2018) — thay đổi cấu trúc theo các bước nhỏ với kiểm thử bảo vệ.
- Eric Evans, *Domain-Driven Design: Tackling Complexity in the Heart of Software* (2003) — mô hình miền, ngôn ngữ chung và ranh giới ngữ nghĩa.
- Neal Ford, Rebecca Parsons và Patrick Kua, *Building Evolutionary Architectures* — architecture fitness functions và phương pháp phát triển kiến trúc thích ứng.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — Increment, Definition of Done, Sprint Goal và kiểm tra–thích ứng trong Scrum.
- [The Kanban Guide](https://kanbanguides.org/) — Definition of Workflow, WIP, cycle time, throughput và work item age.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/) và [12 nguyên tắc](https://agilemanifesto.org/principles.html) — phần mềm hoạt động, chất lượng kỹ thuật, tính đơn giản và thay đổi dựa trên phản hồi.
