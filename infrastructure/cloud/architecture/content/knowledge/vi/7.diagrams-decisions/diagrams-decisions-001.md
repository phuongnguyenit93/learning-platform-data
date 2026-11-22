# Mô hình C4: bối cảnh, container và thành phần

Khi thiết kế một hệ thống trên đám mây, kiến trúc sư phải trao đổi với nhiều nhóm: người phụ trách sản phẩm muốn hiểu hệ thống hỗ trợ nghiệp vụ nào; kỹ sư backend cần biết các thành phần phụ thuộc nhau ra sao; đội platform cần biết phải triển khai những tài nguyên gì; đội bảo mật cần nhận diện những ranh giới tin cậy và luồng dữ liệu quan trọng. Một sơ đồ có quá nhiều biểu tượng dịch vụ cloud thường không đáp ứng đồng thời mọi nhu cầu đó.

**Mô hình C4 (C4 model)** là cách mô tả kiến trúc phần mềm ở các mức phóng đại khác nhau: **Context** (bối cảnh), **Container** (đơn vị chạy hoặc lưu trữ) và **Component** (thành phần bên trong container), cùng mức **Code** (cấu trúc mã) khi cần. Ba mức đầu thường đủ để làm rõ một thiết kế cloud ở giai đoạn kiến trúc. Thay vì vẽ tất cả máy chủ, cơ sở dữ liệu, API và lớp xử lý trong một hình, người thiết kế đi từ cái nhìn tổng quan đến chi tiết có chủ đích.

Trong module **CLOUD_ARCHITECTURE**, C4 hỗ trợ đi từ **yêu cầu nghiệp vụ** đến **cấu trúc ứng dụng**, rồi mới lựa chọn mạng, compute, dữ liệu và mô hình triển khai. C4 giúp các bên thảo luận đánh đổi về **độ tin cậy, bảo mật, mở rộng, chi phí và vận hành**; riêng các thuộc tính đó vẫn phải được kiểm chứng bằng thiết kế triển khai, phép đo và đánh giá Well-Architected.

## 1. C4 trả lời những câu hỏi nào?

Tên **C4** bắt nguồn từ bốn chữ C: *Context, Container, Component, Code*. Các cấp thể hiện cùng một hệ thống dưới các phạm vi quan sát khác nhau.

| Mức | Câu hỏi trọng tâm | Đối tượng chính trong sơ đồ | Người thường sử dụng |
|---|---|---|---|
| **1. System Context** | Hệ thống phục vụ ai và tương tác với hệ thống bên ngoài nào? | Người dùng, hệ thống đang thiết kế, các hệ thống khác và quan hệ giữa chúng | Product owner, business analyst, architect, security |
| **2. Container** | Bên trong hệ thống có những ứng dụng hoặc kho dữ liệu nào, và chúng liên lạc thế nào? | Web app, API, worker, database, queue, các đơn vị ứng dụng hoặc lưu trữ | Architect, developer, platform, operations |
| **3. Component** | Một container cụ thể được chia thành những khối chức năng nào và chúng phụ thuộc nhau ra sao? | Controller, application service, domain service, adapter, repository và khối chức năng tương tự | Developer, tech lead, người review thiết kế |
| **4. Code (tùy chọn)** | Các thành phần quan trọng được triển khai bằng lớp, interface, package hoặc module mã nào? | Các cấu trúc mã có chọn lọc | Developer, người bảo trì mã |

Các cấp **không phải bốn giai đoạn bắt buộc phải vẽ hết**. Mục đích của việc phóng đại là chỉ đưa vào chi tiết mà người đọc cần để đưa ra quyết định. Hệ thống nhỏ có thể cần Context và Container; một API phức tạp có thể cần thêm Component; sơ đồ Code thường chỉ có ích với một phần cụ thể khó hiểu.

### Ví dụ về mức độ chi tiết

Giả sử xây dựng **Booking System** cho phép khách hàng tìm chỗ, đặt chỗ và nhận xác nhận:

- **Context:** Khách hàng dùng Booking System; hệ thống trao đổi với cổng thanh toán và nhà cung cấp email.
- **Container:** Booking System có Web App, Booking API, cơ sở dữ liệu giao dịch, hàng đợi và worker thông báo.
- **Component:** Bên trong Booking API có HTTP Controller, Booking Service, kiểm tra quy tắc đặt chỗ, Repository, Payment Adapter và Outbox Writer.
- **Code:** Chỉ khi cần mới vẽ interface của Booking Service, các kiểu dữ liệu giao dịch và cách Repository thực hiện thao tác nguyên tử.

Từng mức phải **phù hợp về ý nghĩa**: một hệ thống ngoài được nhắc ở Context vẫn là hệ thống ngoài ở Container; không được vô tình biến cổng thanh toán của đối tác thành thành phần nội bộ chỉ vì vẽ ở mức chi tiết hơn.

## 2. Các khái niệm và quy tắc ký hiệu của C4

C4 tập trung vào một tập phần tử đơn giản:

| Phần tử | Ý nghĩa | Ví dụ |
|---|---|---|
| **Person** | Người hoặc vai trò trực tiếp tương tác với hệ thống | Khách hàng, nhân viên vận hành |
| **Software System** | Hệ thống phần mềm cung cấp chức năng có ý nghĩa cho người dùng hoặc hệ thống khác | Booking System, Payment Gateway |
| **Container** | Ứng dụng hoặc kho dữ liệu chạy/lưu trữ như một đơn vị có vai trò riêng trong một software system | Web App, Booking API, database, message broker |
| **Component** | Tập hợp chức năng được nhóm lại sau interface hoặc trách nhiệm rõ ràng trong một container | Booking Service, Reservation Repository |
| **Relationship** | Quan hệ sử dụng hoặc trao đổi dữ liệu giữa các phần tử | “Gọi API HTTPS”, “Đọc/ghi đặt chỗ”, “Nhận thông điệp” |
| **Boundary** | Ranh giới hệ thống hoặc phạm vi nhóm phần tử đang được mô tả | Booking System chứa các container của nó |

**Container trong C4 không đồng nghĩa với Docker container.** Một container C4 có thể là ứng dụng JVM chạy trên máy ảo, web app trong trình duyệt, một database được quản lý hoặc một worker serverless. Nó biểu đạt **ranh giới ứng dụng hoặc kho dữ liệu**, không quy định dùng Docker, Kubernetes hay số lượng instance.

**Component trong C4 không đồng nghĩa với microservice.** Component là cấu trúc chức năng **bên trong một container**; nó có thể là một module Java, nhóm package hoặc tập lớp. Microservice thường có ranh giới triển khai và vận hành riêng nên có thể xuất hiện như một **container ở mức C4**, tùy cách xác định software system.

**Boundary của C4 không tự là trust boundary của bảo mật.** Việc hai thành phần cùng nằm trong một khung hệ thống không bảo đảm chúng có cùng quyền, cùng mạng hoặc cùng phân loại dữ liệu. Khi đánh giá bảo mật, cần chú thích thêm ranh giới tin cậy, dữ liệu nhạy cảm và luồng truy cập thực tế.

### Quy tắc giúp người đọc hiểu sơ đồ

1. **Đặt tên theo vai trò nghiệp vụ hoặc trách nhiệm:** “Booking API” rõ hơn “Service A”; “Reservation Database” rõ hơn “DB-01”.
2. **Viết mô tả ngắn:** Mỗi phần tử trả lời “nó làm gì?”; với container có thể ghi thêm công nghệ hoặc loại lưu trữ như “Java/Spring Boot” và “PostgreSQL”.
3. **Gắn nhãn lên quan hệ:** Nên mô tả hành động và giao thức quan trọng, ví dụ “Gửi yêu cầu đặt chỗ qua HTTPS/JSON”, thay cho mũi tên trống.
4. **Phân biệt nội bộ và bên ngoài:** Giữ boundary rõ ràng; không để nhà cung cấp thanh toán nằm trong khung phần mềm mình quản lý.
5. **Giữ một phạm vi quan sát:** Đừng trộn các lớp Java, máy chủ, Region và SaaS bên ngoài thành những phần tử ngang cấp không giải thích.
6. **Có chú giải khi dùng màu/kiểu nét:** Người xem không nên phải đoán màu xanh nghĩa là “managed” hay “an toàn”.
7. **Dễ đọc hơn đầy đủ:** Chọn các quan hệ có ý nghĩa; nếu quá nhiều cạnh chéo, chia sơ đồ hoặc dùng góc nhìn bổ sung.

## 3. Level 1 — System Context: bối cảnh của hệ thống

**Sơ đồ bối cảnh hệ thống** đặt *một software system đang nghiên cứu* ở trung tâm, sau đó xác định những **vai trò người dùng** và **hệ thống khác** trực tiếp liên quan. Đây là điểm nối giữa yêu cầu nghiệp vụ và kiến trúc kỹ thuật.

Ví dụ Booking System có ba tương tác chính:

- **Khách hàng:** Tìm và đặt chỗ, theo dõi trạng thái.
- **Nhân viên vận hành:** Theo dõi đặt chỗ, xử lý các trường hợp cần hỗ trợ.
- **Payment Gateway:** Xử lý giao dịch thanh toán được hệ thống yêu cầu.
- **Email Provider:** Nhận yêu cầu gửi xác nhận hoặc thông báo.

~~~mermaid
flowchart LR
    CUSTOMER["Person: Khách hàng"]
    OPS["Person: Nhân viên vận hành"]
    BOOK["Software System: Booking System<br/>Tìm, đặt chỗ, quản lý trạng thái"]
    PAYMENT["External Software System:<br/>Payment Gateway"]
    EMAIL["External Software System:<br/>Email Provider"]

    CUSTOMER -->|"Tìm chỗ, đặt chỗ và xem trạng thái"| BOOK
    OPS -->|"Theo dõi và xử lý đặt chỗ"| BOOK
    BOOK -->|"Yêu cầu thanh toán qua API"| PAYMENT
    BOOK -->|"Gửi yêu cầu email xác nhận"| EMAIL
~~~

*Sơ đồ minh họa bằng Mermaid theo ý nghĩa của C4 System Context; đây không phải bộ ký pháp C4 chính thức hay sơ đồ triển khai cloud.*

### Những gì nên và không nên xuất hiện ở Level 1

Ở Level 1, **Booking System là một hộp duy nhất**. Không cần biết nó chạy Spring Boot, Node.js, Kubernetes hay database nào. Context cũng không cho biết có bao nhiêu API instance, đặt máy ở Region nào hoặc dùng subnet ra sao.

Từ sơ đồ, các bên có thể rà soát các yêu cầu:

- Khách hàng có được đặt chỗ khi cổng thanh toán tạm thời lỗi không? Nếu có, trạng thái nghiệp vụ là gì?
- Thông tin cá nhân hoặc thanh toán nào đi qua hệ thống ngoài? Dữ liệu có được phép chuyển tới bên thứ ba không?
- Email gửi chậm có được chấp nhận không, và khách hàng xem kết quả xác nhận ở đâu?
- Có nhóm vận hành cần quyền khác người dùng thông thường không?

Nếu bỏ sót một hệ thống thanh toán hoặc nguồn danh tính tại Level 1, các quyết định bảo mật, bảo vệ dữ liệu, tích hợp và xử lý sự cố ở các cấp sau dễ thiếu cơ sở. Ngược lại, Level 1 không nên trở thành danh mục toàn bộ dịch vụ hạ tầng.

### Cách xác định ranh giới “hệ thống”

Ranh giới software system nên phản ánh phạm vi chức năng và trách nhiệm mà một nhóm hoặc tổ chức quản lý. Ví dụ, một nền tảng có thể tách “Booking System” và “Payment System” thành hai hệ thống nội bộ có vòng đời riêng; lúc đó Payment System xuất hiện là **hệ thống liên quan** trong Context của Booking. Không có quy tắc rằng một tổ chức phải đặt toàn bộ sản phẩm vào đúng một software system.

Hãy ghi rõ **hệ thống nào đang được phóng đại**, vì thuật ngữ “container” ở Level 2 chỉ có ý nghĩa trong phạm vi của hệ thống đã chọn.

## 4. Level 2 — Container: cấu trúc ứng dụng và dữ liệu

Sau khi các bên thống nhất bối cảnh, **sơ đồ Container** phóng đại vào Booking System để thấy những **đơn vị ứng dụng, lưu trữ và xử lý có trách nhiệm khác nhau**.

Trong ví dụ này:

| Container | Trách nhiệm | Công nghệ minh họa | Yêu cầu kiến trúc |
|---|---|---|---|
| **Web App** | Hiển thị chức năng tìm kiếm/đặt chỗ và gọi API | Web SPA | Trải nghiệm người dùng, bảo vệ phiên và dữ liệu |
| **Booking API** | Xác thực, kiểm tra quy tắc và thực hiện nghiệp vụ đặt chỗ | Java / Spring Boot | Stateless compute, transaction, kiểm soát đồng thời |
| **Reservation Database** | Lưu trạng thái đặt chỗ và bản ghi outbox bền vững | Relational database | Nhất quán, backup, phục hồi |
| **Outbox Publisher** | Phát sự kiện đã ghi thành công sang queue | Worker/background process | Retry, chống bỏ sót sự kiện |
| **Message Queue** | Giữ thông điệp gửi thông báo chờ xử lý | Managed queue | Độ bền, giới hạn lưu giữ, giao nhận lại |
| **Notification Worker** | Nhận sự kiện và gọi Email Provider | Worker | Idempotency, retry, giám sát thất bại |

~~~mermaid
flowchart LR
    CUSTOMER["Person:<br/>Khách hàng"]
    PAYMENT["External System:<br/>Payment Gateway"]
    EMAIL["External System:<br/>Email Provider"]

    subgraph BOOK["Software System: Booking System"]
        WEB["Container: Web App<br/>SPA"]
        API["Container: Booking API<br/>Java / Spring Boot"]
        DB[("Container: Reservation Database<br/>Relational DB")]
        PUBLISHER["Container: Outbox Publisher<br/>Background worker"]
        QUEUE[("Container: Message Queue<br/>Managed service")]
        NOTIFY["Container: Notification Worker<br/>Background worker"]

        WEB -->|"HTTPS / JSON"| API
        API -->|"Transaction: đọc/ghi đặt chỗ và outbox"| DB
        PUBLISHER -->|"Đọc outbox, đánh dấu kết quả"| DB
        PUBLISHER -->|"Phát sự kiện"| QUEUE
        QUEUE -->|"Giao thông điệp"| NOTIFY
    end

    CUSTOMER -->|"Sử dụng qua trình duyệt"| WEB
    API -->|"Yêu cầu thanh toán qua HTTPS"| PAYMENT
    NOTIFY -->|"Gọi API gửi email"| EMAIL
~~~

Sơ đồ làm rõ **đường xử lý nghiệp vụ**: Web App gọi Booking API; API ghi dữ liệu bằng transaction. Sự kiện thông báo được ghi cùng giao dịch vào **outbox**, sau đó Outbox Publisher đọc và phát ra queue; Notification Worker xử lý bất đồng bộ. Đây là một phương án thiết kế để tránh tình huống database commit thành công nhưng việc gửi sự kiện thất bại làm mất thông báo.

Giải pháp vẫn cần quy tắc **idempotency** vì publisher có thể gửi lại cùng sự kiện và queue có thể giao lại thông điệp; worker không nên gửi cùng một email nhiều lần không kiểm soát. Chi tiết “chống trùng như thế nào” có thể được giải thích ở Component hoặc tài liệu luồng xử lý, không nhất thiết nhồi lên sơ đồ Container.

### Tại sao database và queue được xem là container?

Trong C4, database và message queue là các **kho dữ liệu hoặc thành phần hạ tầng có vai trò độc lập trong hệ thống phần mềm**, nên thường thể hiện như container. Điều này giúp thấy **quyền sở hữu trạng thái** và luồng truy cập. Tuy nhiên, C4 không yêu cầu một container tương ứng duy nhất với một dịch vụ cloud hoặc instance vật lý:

- Một Booking API container có thể chạy **nhiều bản sao** trên máy ảo, Kubernetes hoặc nền tảng ứng dụng được quản lý.
- Một database container có thể triển khai bằng dịch vụ cơ sở dữ liệu được quản lý có replication và failover.
- Một Message Queue container có thể được hiện thực hóa bởi dịch vụ được quản lý, với hạn mức và semantics giao nhận khác nhau.

Mô hình container mô tả **cấu trúc và trách nhiệm**; sơ đồ triển khai bổ sung **vị trí, số lượng, kết nối mạng và khả năng dự phòng**.

### Container không đồng nghĩa microservice

Booking API có thể là một **modular monolith** chứa nhiều module nghiệp vụ rõ ràng. Chia mỗi chức năng thành một microservice riêng sẽ tăng số API, luồng gọi mạng, giao dịch phân tán, tài nguyên giám sát và công vận hành. Chỉ nên tách thêm container khi có nhu cầu rõ về vòng đời triển khai, sở hữu dữ liệu, khả năng mở rộng, cách ly lỗi hoặc trách nhiệm nhóm.

## 5. Level 3 — Component: trách nhiệm bên trong một container

Ở Level 3, ta chọn **một container duy nhất để phóng đại**, chẳng hạn Booking API. Những container khác như database hoặc web app chỉ còn xuất hiện dưới dạng **phụ thuộc bên ngoài phạm vi container đang xét**, dù chúng vẫn có thể thuộc cùng Booking System.

Ví dụ tách Booking API thành các component sau:

| Component trong Booking API | Trách nhiệm | Quan hệ quan trọng |
|---|---|---|
| **Booking Controller** | Nhận request, kiểm tra định dạng và trả response | Gọi Booking Application Service |
| **Authentication & Authorization** | Xác minh người gọi và kiểm tra quyền thực hiện hành động | Được controller/application service sử dụng phù hợp |
| **Booking Application Service** | Điều phối use case đặt chỗ và transaction | Gọi Availability Policy, Repository, Outbox Writer |
| **Availability Policy** | Đánh giá quy tắc nghiệp vụ về tình trạng chỗ | Không quyết định tính nhất quán cuối cùng bằng cache đơn thuần |
| **Reservation Repository** | Truy xuất và cập nhật đặt chỗ | Sử dụng database và ràng buộc dữ liệu |
| **Outbox Writer** | Ghi sự kiện nghiệp vụ trong cùng transaction với đặt chỗ | Ghi vào database; publisher phát sau commit |
| **Payment Gateway Adapter** | Chuẩn hóa lời gọi sang hệ thống thanh toán bên ngoài | Che giấu giao thức và chi tiết SDK của nhà cung cấp |

~~~mermaid
flowchart LR
    WEB["External Container:<br/>Web App"]
    DB[("External Container:<br/>Reservation Database")]
    PAYMENT["External Software System:<br/>Payment Gateway"]

    subgraph API["Container: Booking API (Java / Spring Boot)"]
        CTRL["Component:<br/>Booking Controller"]
        AUTH["Component:<br/>Authentication & Authorization"]
        SERVICE["Component:<br/>Booking Application Service"]
        RULES["Component:<br/>Availability Policy"]
        REPO["Component:<br/>Reservation Repository"]
        OUTBOX["Component:<br/>Outbox Writer"]
        PAY["Component:<br/>Payment Gateway Adapter"]

        CTRL -->|"Kiểm tra quyền"| AUTH
        CTRL -->|"Thực hiện use case"| SERVICE
        SERVICE -->|"Đánh giá quy tắc"| RULES
        SERVICE -->|"Đọc/ghi đặt chỗ"| REPO
        SERVICE -->|"Ghi sự kiện cùng transaction"| OUTBOX
        SERVICE -->|"Yêu cầu thanh toán khi cần"| PAY
    end

    WEB -->|"HTTPS / JSON"| CTRL
    REPO -->|"SQL / transaction"| DB
    OUTBOX -->|"SQL / transaction"| DB
    PAY -->|"HTTPS API"| PAYMENT
~~~

*Các component là ranh giới logic. Chúng có thể được triển khai bằng package, module, interface hoặc lớp Java theo cách thiết kế mã thực tế. Sơ đồ không yêu cầu mỗi component là một process hay pod riêng.*

### Biểu đạt ranh giới transaction rõ ràng

Ở ví dụ này, **Booking Application Service** điều phối một transaction trong phạm vi database, bao gồm ghi đặt chỗ và ghi outbox. **Reservation Repository** phải sử dụng thao tác kiểm soát đồng thời phù hợp: ràng buộc duy nhất, cập nhật có điều kiện, khóa hoặc mức isolation thích hợp. Chỉ kiểm tra “còn chỗ” bằng SELECT rồi INSERT tách rời mà không có bảo vệ ở database có thể gây đặt trùng khi nhiều request đồng thời.

Lời gọi đến Payment Gateway diễn ra qua một hệ thống ngoài, nên **không thuộc cùng transaction ACID cục bộ**. Nếu có bước thanh toán, use case cần mô hình trạng thái rõ như *pending payment*, *confirmed*, *expired*, *failed*, cùng xử lý retry, webhook và trường hợp thanh toán thành công nhưng phản hồi bị mất. Có thể phải dùng quy trình điều phối hoặc bù trừ thay vì giả định một transaction bao phủ cả hai hệ thống.

Sơ đồ Component cho phép kỹ sư phát hiện những điểm cần mô tả kỹ hơn:

- Ai chịu trách nhiệm giới hạn thời gian giữ chỗ và quyết định đặt trùng?
- Thành phần nào thực hiện phân quyền trước khi đọc dữ liệu người khác?
- Sự kiện outbox được ghi trước hay sau commit?
- Lỗi thanh toán được biến thành trạng thái nghiệp vụ nào?
- Có đang để controller chứa toàn bộ quy tắc nghiệp vụ, khiến logic khó kiểm thử và bảo trì không?

## 6. Mức Code, Dynamic và Deployment: bổ sung khi cần

C4 thường giới thiệu **mức Code** là tầng chi tiết thứ tư, nhưng hệ thống thực tế còn có những **góc nhìn bổ sung** rất hữu ích:

| Góc nhìn | Khi dùng | Câu hỏi được giải đáp |
|---|---|---|
| **Code (Level 4, tùy chọn)** | Một component có cấu trúc mã phức tạp cần người triển khai thống nhất | Các interface, class và module phối hợp thế nào? |
| **Dynamic diagram** | Luồng đặt chỗ, thanh toán, retry hoặc khôi phục có thứ tự tương tác quan trọng | Khi nào ai gọi ai, thứ tự và nhánh lỗi ra sao? |
| **Deployment diagram** | Cần đánh giá Region, AZ, subnet, runtime, replica, cloud service và failover | Các container logic được triển khai ở đâu và nhân bản thế nào? |
| **System landscape** | Một tổ chức có nhiều software system cùng quan hệ | Những hệ thống cấp tổ chức liên hệ nhau thế nào? |

### Dynamic diagram: minh họa một lần đặt chỗ

~~~mermaid
sequenceDiagram
    actor U as Khách hàng
    participant W as Web App
    participant A as Booking API
    participant D as Reservation Database
    participant P as Outbox Publisher
    participant Q as Message Queue
    participant N as Notification Worker
    participant E as Email Provider

    U->>W: Xác nhận đặt chỗ
    W->>A: POST /bookings (Idempotency-Key)
    A->>D: Transaction: kiểm soát đặt trùng, ghi booking + outbox
    D-->>A: Commit thành công
    A-->>W: Booking ID và trạng thái
    W-->>U: Hiển thị xác nhận
    P->>D: Đọc outbox chưa phát
    D-->>P: Sự kiện đặt chỗ
    P->>Q: Publish sự kiện (có thể retry)
    Q->>N: Giao thông điệp
    N->>E: Yêu cầu gửi email (có chống trùng)
    N-->>Q: Ack sau khi hoàn tất
~~~

Đây là **happy path** giản lược, chưa biểu diễn tất cả trạng thái lỗi. Khi review cần bổ sung tình huống database từ chối đặt trùng, HTTP timeout sau commit, publisher/queue gián đoạn hoặc Email Provider trả lỗi. Những nhánh đó có thể thể hiện bằng sequence diagram riêng hoặc mô tả use case; không phải đưa toàn bộ lên sơ đồ Context.

### Deployment diagram: nối C4 với cloud

Một bản triển khai minh họa trên một nền tảng cloud:

~~~mermaid
flowchart TB
    USER["Người dùng / Internet"] --> EDGE["CDN, DNS, bảo vệ biên"]
    EDGE --> LB["Public load balancer"]
    subgraph VNET["Mạng cloud riêng của ứng dụng"]
        subgraph AZ1["Availability Zone A"]
            APIA["Booking API replica A"]
            WA["Notification Worker A"]
        end
        subgraph AZ2["Availability Zone B"]
            APIB["Booking API replica B"]
            WB["Notification Worker B"]
        end
        DB[("Managed relational database<br/>Cấu hình HA theo lựa chọn")]
        QUEUE[("Managed message queue")]
        PUBLISH["Outbox Publisher<br/>Có cơ chế thay thế/tiếp tục"]
        LB --> APIA
        LB --> APIB
        APIA --> DB
        APIB --> DB
        PUBLISH --> DB
        PUBLISH --> QUEUE
        QUEUE --> WA
        QUEUE --> WB
    end
~~~

*Sơ đồ triển khai này chỉ minh họa hai AZ cho compute. Vị trí thực, khả năng dự phòng và phạm vi lỗi của database, queue, publisher cùng các dịch vụ ngoài phải kiểm tra theo sản phẩm cloud và cấu hình cụ thể. Không thể suy ra đạt HA chỉ từ biểu tượng “managed”.*

Ở đây có thể chọn chạy Booking API bằng VM, container orchestration, serverless function hoặc dịch vụ ứng dụng được quản lý; đó là **quyết định triển khai**, không nhất thiết thay đổi tên “Booking API” trên C4 Level 2. Nếu đổi kiến trúc từ một Booking API thành nhiều dịch vụ độc lập, khi ấy sơ đồ Container cũng cần cập nhật.

## 7. Nối các mức C4 với quyết định cloud

Một phương pháp thiết kế rõ ràng là gắn **mỗi câu hỏi kiến trúc vào đúng góc nhìn**, sau đó lưu quyết định bằng tài liệu hoặc bản ghi ADR.

| Câu hỏi kiến trúc | Góc nhìn hữu ích | Quyết định hoặc bằng chứng |
|---|---|---|
| Ai sử dụng hệ thống, ai xử lý thanh toán, dữ liệu nào đi ra đối tác? | Context | Danh sách actor, hệ thống ngoài, luồng dữ liệu và trách nhiệm tích hợp |
| Có cần tách xử lý thông báo ra khỏi request đặt chỗ? | Container và Dynamic | API, queue, worker, outbox; retry và trạng thái nghiệp vụ |
| Ai đảm bảo không đặt trùng chỗ? | Component và thiết kế dữ liệu | Transaction, constraint, concurrency control |
| Chạy API trên máy ảo, nền tảng container hay serverless? | Deployment, yêu cầu phi chức năng và ADR | Độ trễ, tải, kỹ năng vận hành, chi phí, khả năng scale |
| Hệ thống lỗi một AZ có phục hồi không? | Deployment và fault analysis | Phụ thuộc, failover, thử mất AZ, RTO/RPO |
| API chỉ được truy cập database nào? | Container, Deployment và security view | Network policy, IAM, secret và audit log |
| Sự kiện đặt chỗ có mất khi queue lỗi không? | Dynamic, Component và ADR | Outbox, cơ chế phát lại, giám sát backlog |
| Chi phí phát sinh ở đâu? | Deployment, cost view và báo cáo cloud | Compute, database, queue, log, mạng, backup, cost allocation |

**Các cấp C4 không thay thế cho thiết kế phi chức năng.** Một đường “Booking API → Database” cho biết có phụ thuộc, nhưng không cho biết kết nối đã mã hóa hay chưa, database có replica hay không, query p95 là bao nhiêu, connection pool có quá tải không hoặc chi phí truyền dữ liệu giữa các Region.

### Khả năng mở rộng và sự khác biệt logic – vật lý

Trên C4 Container, Booking API có thể xuất hiện **một ô duy nhất** dù thực tế chạy nhiều replica không lưu trạng thái. Nếu API giữ session trong RAM của một replica và yêu cầu người dùng luôn đến đúng replica đó, khả năng scale-out/failover sẽ hạn chế. Đây là chi tiết cần đưa vào quyết định “stateless compute và externalized state”, không phải thay tên container theo số replica.

Tương tự, khi tăng số API replica, giới hạn của database, payment gateway và queue vẫn có thể trở thành nút thắt. Cần kiểm thử tải đồng thời, quản lý connection pool, quota, rate limit, backpressure và quan sát p95/p99 latency. Sơ đồ C4 tạo nền cho danh sách phụ thuộc cần đo.

### Bảo mật và ranh giới tin cậy

Sau khi có Context và Container, hãy đánh dấu các điểm dữ liệu vượt ranh giới:

1. Từ Internet/trình duyệt vào Web App và Booking API: xác thực, chống lạm dụng, bảo vệ session/token.
2. Từ Booking API sang database: định danh workload, quyền tối thiểu, kiểm soát mạng và mã hóa kết nối.
3. Từ Booking API sang Payment Gateway: xác minh đối tác, chứng thực webhook/callback, tránh log bí mật và dữ liệu thanh toán nhạy cảm.
4. Từ Notification Worker sang Email Provider: giới hạn dữ liệu chia sẻ, secret, retry và chống gửi trùng.
5. Từ các thành phần về hệ thống quan sát: bảo vệ log khỏi chứa token, bí mật hoặc thông tin cá nhân vượt mức cần thiết.

Nếu nhà cung cấp cloud có IAM, private endpoint, network segmentation và dịch vụ mã hóa, những năng lực đó hiện thực hóa **kiểm soát**; chúng không làm toàn bộ luồng tự động an toàn nếu quyền hoặc cách dùng sai.

## 8. Từ sơ đồ tới quyết định: Architecture Decision Record (ADR)

Sơ đồ giúp nhiều người nhìn thấy cấu trúc, nhưng hiếm khi tự trả lời **vì sao chọn phương án A thay vì B**. Với các quyết định có đánh đổi đáng kể, nên ghi một **Architecture Decision Record (ADR)** ngắn.

Ví dụ cho hệ thống đặt chỗ:

### ADR-001 — Xử lý email xác nhận bất đồng bộ

**Bối cảnh:** Email Provider có thể phản hồi chậm hoặc lỗi. Người dùng cần biết kết quả đặt chỗ ngay; trạng thái đã ghi thành công trong database không được bị đảo ngược chỉ vì email chậm.

**Các phương án:**

- **A. Gửi email đồng bộ trong Booking API:** Ít thành phần; nhưng request phụ thuộc độ trễ và độ sẵn sàng của nhà cung cấp email.
- **B. Ghi đặt chỗ, đưa sự kiện lên queue rồi xử lý bằng worker:** Tách đường xử lý email; tuy nhiên có nguy cơ ghi database thành công nhưng phát queue lỗi nếu thao tác không được phối hợp.
- **C. Ghi đặt chỗ và outbox trong cùng transaction, publisher chuyển sự kiện sang queue, worker xử lý:** Có thêm cơ chế outbox, replay, monitoring và idempotency, đổi lại giảm nguy cơ mất sự kiện sau commit.

**Quyết định:** Chọn **C** vì yêu cầu nghiệp vụ là xác nhận giao dịch đặt chỗ nhanh, trong khi email được phép đến sau. Dùng database làm nguồn dữ liệu chuẩn; worker phải xử lý lại thông điệp an toàn.

**Hệ quả:** Cần giám sát độ trễ phát outbox, độ sâu queue, số lần retry và thông báo lỗi. Người dùng xem trạng thái đặt chỗ trực tiếp từ hệ thống, không coi việc nhận email là nguồn xác thực duy nhất.

**Kiểm chứng:** Giả lập Email Provider lỗi, làm publisher dừng sau database commit, gửi lại message trùng; kiểm tra booking không bị mất, sự kiện có thể phát lại và số lần gửi ngoài mong muốn được kiểm soát.

**Sơ đồ liên quan:** Context nêu phụ thuộc Email Provider; Container hiển thị queue/worker/outbox publisher; Component hiển thị Outbox Writer; Dynamic giải thích thứ tự ghi và phát.

ADR này có thể dẫn tới các quyết định tiếp theo: chọn dịch vụ queue managed nào, thời hạn giữ thông điệp, chiến lược bảo vệ dữ liệu trong email và ngưỡng cảnh báo. Khi đổi quyết định, cần sửa cả ADR lẫn sơ đồ liên quan để chúng không mâu thuẫn.

## 9. C4 và đánh giá theo Well-Architected

Các khung Well-Architected giúp đặt câu hỏi có hệ thống. C4 hỗ trợ liệt kê đúng thành phần và phụ thuộc để đánh giá, nhưng không tự chứng minh hệ thống đáp ứng mục tiêu chất lượng.

| Khía cạnh | C4 giúp nhìn thấy | Câu hỏi phải kiểm chứng thêm |
|---|---|---|
| **Vận hành xuất sắc** | Container, người sở hữu, phụ thuộc và đường xử lý | Có log, metric, trace, runbook, quy trình deploy/rollback và quản lý sự cố không? |
| **Bảo mật** | Tác nhân, hệ thống ngoài, luồng dữ liệu và phạm vi xử lý | IAM/quyền tối thiểu, phân đoạn mạng, mã hóa, xác thực và xử lý dữ liệu nhạy cảm đã được thực thi chưa? |
| **Độ tin cậy** | Các điểm phụ thuộc có thể gây gián đoạn dây chuyền | Có điểm lỗi đơn không? Backup, failover và diễn tập có đáp ứng RTO/RPO không? |
| **Hiệu quả hiệu năng** | Đường gọi đồng bộ, bất đồng bộ, nơi truy cập database | Kết quả tải thực tế về throughput, p95/p99, connection pool và quota thế nào? |
| **Tối ưu chi phí** | Những dịch vụ ứng dụng và kho dữ liệu cần triển khai | Chi phí compute, storage, network, log và môi trường dự phòng có được dự toán và phân bổ không? |
| **Bền vững** | Workload chạy thường trực, tác vụ nền và kho dữ liệu | Có right-sizing, autoscaling, chính sách vòng đời dữ liệu và tránh tài nguyên nhàn rỗi không? |

Ví dụ, mục tiêu tham khảo cho một workload có thể được đặt là **99,9% availability**, **p95 đặt chỗ dưới 500 ms** ở tải dự kiến, **RTO tối đa 60 phút** và **RPO tối đa 15 phút**. Đây là **giả định minh họa**, không phải mục tiêu mặc định. Các thông số cần được thương lượng theo nghiệp vụ, sau đó đo lường bằng hệ thống thật, thử tải và diễn tập phục hồi.

Sơ đồ C4 có thể chỉ ra nơi hệ thống dễ gặp lỗi, nhưng câu trả lời về mức sẵn sàng phụ thuộc **cấu hình triển khai và kết quả kiểm chứng**. Một database được vẽ là “managed” không mặc nhiên đạt RPO bằng 0; hai API replica không bảo đảm hệ thống sống sót khi một AZ lỗi nếu chúng phụ thuộc chung vào một điểm lỗi đơn.

### Ma trận kiểm chứng từ yêu cầu đến kiến trúc

| Yêu cầu | Mức sơ đồ cần thể hiện | Quyết định | Phép kiểm chứng |
|---|---|---|---|
| Không xác nhận hai đặt chỗ cùng tài nguyên/khung giờ | Component: Booking Service + Repository; Container: DB | Transaction và constraint theo mô hình dữ liệu | Hai request đồng thời chỉ một giao dịch hợp lệ được xác nhận |
| Nhà cung cấp email lỗi không làm mất đặt chỗ | Context, Container và Dynamic | Outbox + durable queue + worker | Ngắt Email Provider, phát lại và kiểm tra booking vẫn tồn tại |
| API tăng tải mà không mất phiên | Container và Deployment | Stateless API; session/token được xử lý phù hợp | Chuyển request qua các replica, scale in/out |
| Chỉ người có quyền xem dữ liệu đặt chỗ | Context, Component và security view | Phân quyền cấp đối tượng, IAM, bảo vệ token | Thử truy cập chéo người dùng bị từ chối, audit đúng |
| Dễ phân bổ chi phí ứng dụng | Deployment và cost view | Nhãn tài nguyên, ranh giới môi trường/sản phẩm | Đối chiếu báo cáo billing theo owner/workload |

## 10. Quy trình tạo và duy trì sơ đồ C4 có ích cho nhóm

Một quy trình thực hành hiệu quả:

1. **Xác định mục đích và người đọc:** Sơ đồ để giải thích nghiệp vụ, review bảo mật hay quyết định triển khai? Mỗi mục đích cần độ chi tiết khác nhau.
2. **Chọn phạm vi software system:** Xác định ranh giới và trách nhiệm của hệ thống đang mô tả; liệt kê người dùng và hệ thống bên ngoài.
3. **Vẽ Context trước:** Tập trung vào tương tác chính, dữ liệu quan trọng đi qua các ranh giới và các giả định tích hợp.
4. **Phóng đại Container:** Chỉ ra đơn vị chạy/lưu trữ, trách nhiệm, công nghệ quan trọng, hướng trao đổi dữ liệu, đồng bộ/bất đồng bộ và nơi sở hữu trạng thái.
5. **Chọn container cần vẽ Component:** Ưu tiên phần có nghiệp vụ quan trọng, độ phức tạp cao hoặc rủi ro bảo mật/nhất quán; không cần vẽ mọi container.
6. **Bổ sung góc nhìn Dynamic/Deployment:** Dùng khi luồng lỗi, trình tự xử lý hoặc ánh xạ lên hạ tầng cloud ảnh hưởng quyết định.
7. **Ghi ADR và giả định:** Lưu lý do, phương án thay thế, đánh đổi, điều kiện xem xét lại và phép kiểm chứng; liên kết với sơ đồ.
8. **Review với nhiều vai trò:** Sản phẩm xác nhận luồng nghiệp vụ; backend xác nhận trách nhiệm mã; platform xác nhận triển khai; security xác nhận luồng dữ liệu và quyền.
9. **Cập nhật cùng thay đổi hệ thống:** Khi thêm hoặc bỏ container, đổi phụ thuộc, tích hợp đối tác mới hoặc điều chỉnh ranh giới, cập nhật sơ đồ trong cùng nhịp review thay đổi kiến trúc.

### Lưu sơ đồ bằng mã

Sơ đồ dạng văn bản (Mermaid hoặc DSL chuyên biệt như Structurizr DSL) thuận tiện để lưu cùng tài liệu kiến trúc, xem diff và review qua pull request. Lợi ích chỉ có thật nếu **tên và ý nghĩa phần tử nhất quán**, sơ đồ có người chịu trách nhiệm cập nhật và quy trình review phát hiện thay đổi thực tế.

Ví dụ, có thể lưu liên kết giữa sơ đồ và ADR dưới một bảng trong tài liệu dự án:

| Đối tượng | Thuộc mức | Quyết định liên quan | Người xác nhận khi thay đổi |
|---|---|---|---|
| Payment Gateway | Context | Cách xử lý trạng thái thanh toán và webhook | Product + Backend + Security |
| Booking API | Container | Stateless compute, giới hạn scale, transaction | Backend + Platform |
| Notification Worker | Container | Retry, idempotency, SLA gửi thông báo | Backend + Operations |
| Booking Application Service | Component | Trách nhiệm đặt chỗ và quy tắc nhất quán | Backend |
| Reservation Database | Container + Deployment | HA, backup, schema và RTO/RPO | Backend + Platform |

Không bắt buộc tổ chức nào cũng cần bảng này. Giá trị nằm ở việc **mỗi sơ đồ có mục đích và người chịu trách nhiệm**, tránh tình trạng sơ đồ đẹp lúc bắt đầu nhưng nhanh chóng sai lệch với hệ thống.

## 11. Các lỗi thường gặp khi sử dụng C4

**Lỗi 1 — Vẽ mọi thứ trong một hình.** Một sơ đồ chứa người dùng, lớp Java, Kubernetes node, database, Region và firewall rất khó đọc. **Cách sửa:** Tách Context, Container, Component và Deployment theo đúng câu hỏi.

**Lỗi 2 — Nhầm container C4 với Docker.** Người xem nghĩ chuyển từ VM sang Kubernetes là phải thay toàn bộ cấu trúc logic. **Cách sửa:** Định nghĩa container theo đơn vị ứng dụng/kho dữ liệu; ghi cơ chế chạy ở Deployment.

**Lỗi 3 — Trộn component và microservice.** Biểu diễn mỗi lớp Java như một dịch vụ triển khai độc lập hoặc ngược lại coi một hệ thống ngoài là package nội bộ. **Cách sửa:** Giữ ranh giới container và chỉ phóng đại component của container được chọn.

**Lỗi 4 — Không ghi hướng hoặc ý nghĩa quan hệ.** Mũi tên trống “API ↔ Database” không cho biết ai chủ động truy cập, đọc hay ghi, giao thức nào. **Cách sửa:** Gắn nhãn quan hệ và chỉ ghi những chi tiết quan trọng cho mục tiêu sơ đồ.

**Lỗi 5 — Sơ đồ Context chỉ có danh sách microservice nội bộ.** Bức tranh mất người dùng, mục tiêu nghiệp vụ và hệ thống bên ngoài. **Cách sửa:** Đưa phần nội bộ xuống Container; Context ưu tiên phạm vi hệ thống và tương tác.

**Lỗi 6 — Sơ đồ Container không nêu nơi lưu trạng thái.** Nhóm bỏ qua transaction, session store, queue và điểm lỗi đơn. **Cách sửa:** Hiển thị các kho dữ liệu và luồng ghi/đọc quan trọng với công nghệ hoặc thuộc tính cần review.

**Lỗi 7 — Coi sơ đồ là bằng chứng bảo mật và HA.** Nhìn thấy hộp “Private Network” hoặc “Multi-AZ” rồi kết luận đã an toàn. **Cách sửa:** Bổ sung chính sách, hạ tầng và thử nghiệm thực tế; phân biệt giả định với điều đã được kiểm chứng.

**Lỗi 8 — Sơ đồ và mã thực tế lệch nhau.** Một dịch vụ đã tách nhưng sơ đồ vẫn gộp, hoặc tích hợp thanh toán mới không xuất hiện. **Cách sửa:** Gắn cập nhật sơ đồ vào review thay đổi kiến trúc và ADR.

**Lỗi 9 — Dùng quá nhiều màu hoặc tên vendor.** Sơ đồ khó đọc và bị khóa vào sản phẩm, dù logic còn có thể chuyển đổi. **Cách sửa:** Ưu tiên tên vai trò; chỉ ghi vendor/technology khi nó tác động tới quyết định.

## 12. Bài tập: vẽ C4 cho hệ thống bán vé

Một công ty muốn triển khai hệ thống bán vé trên cloud. Người dùng tìm sự kiện, giữ ghế trong thời gian ngắn, thanh toán và nhận email. Hệ thống dùng một nhà cung cấp thanh toán và một nhà cung cấp email bên ngoài. Nhóm hiện có một ứng dụng web, API Java và database quan hệ; việc gửi email chạy đồng bộ. Vào giờ mở bán, API tăng tải; nếu thanh toán hoặc email chậm thì nhiều request timeout.

**Yêu cầu thực hành:**

1. **Context:** Vẽ người mua vé, nhân viên hỗ trợ, Ticketing System, Payment Gateway và Email Provider. Ghi quan hệ nào chứa dữ liệu nhạy cảm hoặc phụ thuộc bên thứ ba.
2. **Container:** Đề xuất Web App, Ticketing API, Transactional Database, và nếu có lý do thì Queue + Notification Worker + Outbox Publisher. Giải thích vì sao chọn xử lý đồng bộ hoặc bất đồng bộ từng tác vụ.
3. **Component:** Phóng đại Ticketing API thành Ticket Controller, Ticket Purchase Service, Seat Allocation Policy, Reservation Repository, Payment Adapter và Outbox Writer. Định nghĩa ranh giới nhất quán và xử lý cạnh tranh đặt ghế.
4. **Deployment:** Chọn hướng chạy API trên cloud; làm rõ số replica, cân bằng tải, mạng, database HA và quan sát. Nếu dùng managed service, nêu trách nhiệm còn lại của đội ứng dụng.
5. **ADR:** Viết quyết định về email bất đồng bộ hoặc giữ ghế; liệt kê ít nhất hai phương án, đánh đổi và cách kiểm chứng.
6. **Well-Architected:** Chỉ ra một rủi ro quan trọng cho từng nhóm: độ tin cậy, bảo mật, hiệu năng, chi phí và vận hành.

### Gợi ý đánh giá lời giải

| Tiêu chí | Dấu hiệu lời giải hợp lý | Dấu hiệu cần sửa |
|---|---|---|
| Đúng phạm vi C4 | Context có người và hệ thống ngoài; Container có ứng dụng/kho dữ liệu; Component có logic của một container | Mọi loại phần tử bị trộn vào một mức |
| Nhất quán dữ liệu | Database bảo đảm không bán trùng ghế; mô tả rõ thời gian giữ và trạng thái thanh toán | Chỉ dựa vào kiểm tra trong cache hoặc RAM |
| Xử lý lỗi | Email lỗi không làm mất giao dịch; có retry và chống trùng khi cần | Gửi thông báo đồng bộ làm request quan trọng phụ thuộc email |
| Mở rộng và HA | API instance có thể thay thế; đo phụ thuộc database; failover và backup được kiểm thử | Chỉ thêm replica mà bỏ qua nút thắt và điểm lỗi đơn |
| An toàn | Luồng dữ liệu ngoài hệ thống có xác thực, phân quyền và bảo vệ dữ liệu | Sơ đồ không xác định ai truy cập dữ liệu nhạy cảm |
| Quyết định có chứng cứ | ADR nêu lý do, phương án thay thế, hệ quả và phép đo | Chọn dịch vụ cloud theo tên sản phẩm mà không liên hệ yêu cầu |

### Câu hỏi tự kiểm tra

- Tại sao Booking API chạy 12 Kubernetes pod vẫn có thể chỉ là **một container C4**?
- Nếu thêm một hệ thống quản lý danh tính bên ngoài, cần chỉnh sửa những sơ đồ nào và vì sao?
- Tại sao database xuất hiện ở Level 2, còn Reservation Repository xuất hiện ở Level 3?
- Vì sao một sơ đồ Context không đủ để chứng minh mục tiêu RTO/RPO?
- Nếu chuyển từ database tự quản lý sang managed database nhưng nghiệp vụ và ranh giới ứng dụng không đổi, mức sơ đồ nào cần cập nhật nhiều nhất?
- Khi sơ đồ Container và ADR mô tả hai cách phát sự kiện khác nhau, nhóm cần giải quyết sự không nhất quán đó ra sao?

**Điểm cần ghi nhớ:** C4 là **phương pháp giao tiếp kiến trúc theo mức phóng đại**. Context làm rõ mục đích và ranh giới, Container làm rõ đơn vị ứng dụng và dữ liệu, Component làm rõ trách nhiệm bên trong một đơn vị. Các quyết định về mạng, compute, HA, bảo mật, chi phí và vận hành phải được gắn với những sơ đồ đó và kiểm chứng bằng thiết kế triển khai, ADR và dữ liệu thực tế.
