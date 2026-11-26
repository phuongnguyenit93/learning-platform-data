# Phân biệt tầng logic với tier vật lý khi triển khai

Kiến trúc phân tầng mô tả cách tổ chức trách nhiệm trong mã nguồn; kiến trúc nhiều tier mô tả cách các phần mềm được triển khai và giao tiếp khi chạy. Hai khái niệm liên quan nhưng không đồng nhất. Một ứng dụng Java có thể chia thành tầng trình bày, ứng dụng, nghiệp vụ và truy cập dữ liệu nhưng vẫn được đóng gói thành một ứng dụng Spring Boot chạy trong một tiến trình. Ngược lại, một hệ thống có thể triển khai giao diện, backend và cơ sở dữ liệu trên các môi trường riêng, trong khi backend vẫn chứa nhiều tầng logic bên trong.

Trong module SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED — học tổ chức phần mềm theo kiến trúc phân tầng — việc phân biệt hai khái niệm giúp lựa chọn cấu trúc mã nguồn và cách triển khai phù hợp. Tách tầng logic nhằm quản lý phụ thuộc và trách nhiệm. Tách tier triển khai nhằm đáp ứng nhu cầu vận hành như mở rộng tải, cô lập lỗi, bảo mật, quản lý tài nguyên và triển khai độc lập. Không nên suy ra rằng mỗi tầng logic phải chạy trên một máy chủ hoặc container riêng.

## 1. Tầng logic là gì?

Tầng logic (logical layer) là cách nhóm các thành phần theo trách nhiệm và quy tắc phụ thuộc trong thiết kế phần mềm. Trong một ứng dụng phân tầng, có thể gặp các nhóm sau:

| Tầng logic | Trách nhiệm | Ví dụ trong ứng dụng Java |
|---|---|---|
| Trình bày (presentation) | Nhận yêu cầu từ kênh giao tiếp, kiểm tra cấu trúc, chuyển đổi dữ liệu và tạo phản hồi. | Spring MVC controller, REST endpoint, view adapter. |
| Ứng dụng (application) | Điều phối ca sử dụng, gọi nghiệp vụ và các cổng cần thiết, quản lý đơn vị công việc. | PlaceOrderService, TransferUseCase. |
| Nghiệp vụ (domain/business) | Biểu diễn khái niệm, trạng thái, bất biến và chính sách nghiệp vụ. | Order, Account, Money, domain policy. |
| Truy cập dữ liệu/hạ tầng (data access/infrastructure) | Làm việc với database, message broker, tệp hoặc dịch vụ ngoài. | JPA adapter, Spring Data repository, HTTP client. |

Các tầng này là ranh giới trong mã nguồn và trong cách tư duy về trách nhiệm. Chúng có thể được biểu diễn bằng package, module Gradle/Maven, interface, adapter hoặc quy ước phụ thuộc. Chúng không tự động tạo ra một ranh giới mạng hay một tiến trình độc lập.

Ví dụ, trong cùng một ứng dụng Spring Boot, controller gọi dịch vụ ứng dụng, dịch vụ gọi domain và repository, còn repository adapter dùng JPA để truy cập PostgreSQL. Tất cả lớp này có thể được đóng gói vào một file JAR và chạy trong cùng một JVM. Dù cùng tiến trình, việc phân tầng vẫn có ích vì controller không cần biết chi tiết JPA và domain không cần phụ thuộc Spring Web.

## 2. Tier triển khai là gì?

Tier triển khai (deployment tier) là một phần của hệ thống được triển khai và vận hành như một đơn vị runtime. Tùy kiến trúc, tier có thể là một tiến trình, một nhóm máy chủ, một dịch vụ được triển khai độc lập hoặc một môi trường runtime có ranh giới mạng và vận hành riêng.

Một hệ thống web ba tier thường được mô tả như sau:

1. **Client/presentation tier:** trình duyệt hoặc ứng dụng di động hiển thị giao diện và gửi yêu cầu.
2. **Application tier:** backend xử lý request, điều phối ca sử dụng và thực thi quy tắc nghiệp vụ.
3. **Data tier:** database lưu trữ dữ liệu và thực hiện truy vấn.

Mỗi tier có thể có nhiều bản sao để tăng khả năng phục vụ. Ví dụ, application tier có bốn instance Spring Boot chạy sau load balancer. Chúng vẫn thuộc cùng một vai trò triển khai, dù có nhiều tiến trình hoặc container.

Trong môi trường hiện đại, một tier có thể chạy trên nhiều container hoặc pod, nhiều pod có thể chạy trên cùng một node hoặc trên nhiều node. Vì vậy, “tier vật lý” không nhất thiết có nghĩa là một máy chủ vật lý riêng. Điều quan trọng là ranh giới triển khai, giao tiếp, cấu hình, quyền truy cập và vận hành.

## 3. Tầng logic và tier triển khai không ánh xạ một-một

Có thể hình dung cùng một backend được chia thành nhiều tầng logic nhưng nằm trong một deployment unit:

~~~mermaid
flowchart TB
    subgraph Runtime["Một deployment unit: Spring Boot application"]
        P["Presentation layer<br/>Controller"]
        A["Application layer<br/>Use case service"]
        D["Domain layer<br/>Entity, value object, policy"]
        I["Infrastructure layer<br/>Repository adapter"]
        P --> A
        A --> D
        A --> I
    end
    I --> DB[(PostgreSQL tier)]
~~~

Trong sơ đồ này, bốn tầng logic nằm trong một ứng dụng Spring Boot. Database là một tier runtime riêng. Không có nghĩa tầng trình bày, ứng dụng, domain và infrastructure đều cần máy chủ riêng.

Một cách triển khai khác có thể tách frontend và backend thành các deployment unit riêng, nhưng vẫn giữ nhiều tầng logic bên trong backend:

~~~mermaid
flowchart LR
    Browser["Browser / Mobile<br/>Presentation client"]
    Web["Web frontend<br/>Static hosting / CDN"]
    API["Backend deployment<br/>Spring Boot"]
    DB[("Database deployment")]
    Browser --> Web
    Browser --> API
    API --> DB
~~~

Ở đây frontend và backend có thể được build, triển khai và mở rộng độc lập. Backend vẫn có thể chứa presentation adapter cho REST, application service, domain model và persistence adapter. Tầng trình bày trong backend (REST controller) không nhất thiết là cùng một runtime với phần giao diện chạy trên trình duyệt.

Có thể tóm tắt các khả năng ánh xạ:

| Tổ chức logic | Cách triển khai | Ví dụ |
|---|---|---|
| Nhiều tầng logic | Một deployment unit | Ứng dụng Spring Boot dạng layered monolith; các package controller, application, domain, infrastructure nằm trong cùng JAR. |
| Nhiều tầng logic | Một số deployment unit | Frontend riêng, backend có nhiều tầng logic, database riêng. |
| Một số module logic được tách | Nhiều deployment unit | Các dịch vụ độc lập theo năng lực nghiệp vụ, mỗi dịch vụ vẫn có tầng trình bày, ứng dụng, domain và hạ tầng riêng. |
| Một runtime có nhiều bản sao | Một tier được mở rộng theo chiều ngang | Nhiều instance backend sau load balancer; mỗi instance chứa cùng cấu trúc tầng logic. |

Điểm cốt lõi: số tầng logic không quyết định số tier triển khai. Một backend có bốn tầng logic không có nghĩa cần bốn tier. Một hệ thống ba tier cũng không có nghĩa mỗi tier chỉ có một lớp hoặc một trách nhiệm.

## 4. Ví dụ Java/Spring: layered monolith chạy trong một tier ứng dụng

Giả sử hệ thống bán hàng có chức năng tạo đơn. Mã nguồn có thể tổ chức như sau:

~~~text
com.example.shop
├── presentation
│   ├── OrderController.java
│   └── CreateOrderRequest.java
├── application
│   ├── PlaceOrderUseCase.java
│   └── PlaceOrderService.java
├── domain
│   ├── Order.java
│   ├── OrderLine.java
│   └── Money.java
└── infrastructure
    └── persistence
        ├── JpaOrderRepositoryAdapter.java
        └── OrderJpaEntity.java
~~~

Khi ứng dụng khởi động, Spring tạo các bean trong cùng ApplicationContext. Controller nhận HTTP request và gọi PlaceOrderUseCase. PlaceOrderService điều phối ca sử dụng. Domain Order kiểm tra bất biến và tính toán. JpaOrderRepositoryAdapter dùng Spring Data/JPA để lưu dữ liệu.

Một cách triển khai phổ biến:

~~~text
Internet / Internal network
          |
     Load balancer
          |
   +------+------+
   |             |
Spring Boot   Spring Boot       <- application tier
instance A    instance B
   |             |
   +------+------+
          |
      PostgreSQL                 <- data tier
~~~

Hai instance Spring Boot đều chứa các tầng logic giống nhau. Chúng có thể được triển khai trên hai VM hoặc hai container. Việc thêm instance là mở rộng deployment tier theo chiều ngang, không phải tạo thêm một tầng logic mới.

Mô hình này có một số lợi ích:

- Ranh giới logic rõ ràng nhưng việc gọi giữa các tầng trong cùng JVM không cần qua mạng.
- Có thể triển khai và rollback backend như một đơn vị.
- Giao dịch cục bộ có thể bao trọn nhiều repository nếu cùng transaction manager và resource phù hợp.
- Dễ bắt đầu với một đội ngũ nhỏ và một hệ thống chưa cần chia nhỏ thành nhiều dịch vụ.

Đổi lại, các phần trong cùng deployment unit thường được phát hành cùng nhau và dùng chung tài nguyên runtime. Nếu một tác vụ nền tiêu thụ CPU hoặc bộ nhớ quá lớn, nó có thể ảnh hưởng API trên cùng instance. Có thể xử lý bằng giới hạn tài nguyên, pool riêng, tách worker deployment hoặc sau này tách dịch vụ nếu nhu cầu vận hành đủ rõ.

## 5. Ví dụ hệ thống nhiều tier triển khai

Một hệ thống lớn hơn có thể tách các phần có nhu cầu vận hành khác nhau:

~~~mermaid
flowchart TB
    User["Browser / Mobile"]
    CDN["CDN / Web frontend"]
    Gateway["API gateway"]
    Order["Order service<br/>Presentation + Application + Domain + Infrastructure"]
    Catalog["Catalog service<br/>Presentation + Application + Domain + Infrastructure"]
    Payment["Payment service<br/>Presentation + Application + Domain + Infrastructure"]
    OrderDB[("Order database")]
    CatalogDB[("Catalog database")]
    PaymentDB[("Payment database")]
    User --> CDN
    User --> Gateway
    Gateway --> Order
    Gateway --> Catalog
    Order --> Payment
    Order --> OrderDB
    Catalog --> CatalogDB
    Payment --> PaymentDB
~~~

Ở đây mỗi service có thể tự tổ chức thành nhiều tầng logic. Các service là những đơn vị triển khai riêng, có cấu hình, scaling và vòng đời phát hành riêng. Việc chia service thường dựa trên ranh giới nghiệp vụ, quyền sở hữu dữ liệu, nhu cầu mở rộng và khả năng vận hành độc lập; không nên tách service chỉ để mỗi tầng logic có một process.

Tách deployment unit tạo ra một số hệ quả:

- Gọi qua mạng có độ trễ, timeout và khả năng thất bại riêng.
- Mỗi service cần cấu hình, giám sát, logging, tracing và quản lý phiên bản.
- Giao dịch cục bộ không tự bao trùm database của service khác.
- Cần xử lý retry, idempotency, eventual consistency hoặc saga khi một quy trình đi qua nhiều service.
- Ranh giới mạng có thể giúp giới hạn quyền truy cập, nhưng cần xác thực service-to-service và quản lý secrets phù hợp.

Một hệ thống nhiều tier không tự động có hiệu năng tốt hơn hoặc độ tin cậy cao hơn. Tách một lời gọi nội bộ vốn rất nhanh thành HTTP call giữa hai service có thể tăng độ trễ và tạo thêm điểm lỗi. Chỉ nên tách khi lợi ích về triển khai độc lập, bảo mật, khả năng mở rộng, quyền sở hữu hoặc cô lập lỗi lớn hơn chi phí phân tán.

## 6. Phân biệt các loại ranh giới khi thiết kế

Một thiết kế cần phân biệt ít nhất ba loại ranh giới:

| Ranh giới | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Logic/code boundary | Thành phần nào sở hữu trách nhiệm và được phép phụ thuộc vào thành phần nào? | Controller chỉ gọi use case; domain không import JPA. |
| Module/build boundary | Phần nào được build, kiểm tra hoặc đóng gói độc lập ở mức mã nguồn? | Gradle module domain, application, infrastructure; module có dependency khai báo rõ. |
| Deployment/runtime boundary | Phần nào được phát hành, cấu hình, mở rộng và vận hành như một đơn vị riêng? | Spring Boot service, frontend hosting, PostgreSQL cluster, message broker. |

Một module Gradle riêng không nhất thiết là một deployment tier. Nhiều module có thể được đóng gói vào cùng JAR. Ngược lại, một deployment unit có thể chứa nhiều module build. Package riêng cũng không tự tạo ra ranh giới bảo mật hoặc mạng.

Khi thiết kế, hãy nói rõ đang muốn tách loại ranh giới nào. Nếu mục tiêu là ngăn domain phụ thuộc Spring Data, có thể dùng package/module boundary và quy tắc build. Không cần đưa domain sang máy chủ riêng. Nếu mục tiêu là scale frontend tĩnh độc lập, có thể triển khai frontend lên CDN mà không thay đổi cấu trúc domain. Nếu mục tiêu là cô lập worker xử lý ảnh khỏi API, có thể tách worker thành deployment riêng nhưng vẫn dùng chung một số module logic phù hợp.

## 7. Tác động của việc tách tier đến hiệu năng

Khi các tầng logic chạy trong cùng JVM, lời gọi thường là lời gọi hàm trong bộ nhớ. Khi một phần được tách thành tier riêng, giao tiếp thường qua HTTP, gRPC, message broker hoặc giao thức khác. Chi phí mạng gồm serialization, truyền dữ liệu, xử lý giao thức, hàng đợi, timeout và retry.

| Khía cạnh | Cùng deployment/runtime | Tách tier qua mạng |
|---|---|---|
| Độ trễ gọi | Thường thấp hơn, ít chi phí giao thức. | Có thêm network latency và serialization. |
| Mở rộng | Có thể phải scale cả deployment unit. | Có thể scale từng tier theo tải riêng. |
| Cô lập tài nguyên | Thành phần có thể dùng chung CPU, heap, thread pool. | Có thể đặt giới hạn CPU/memory và lịch triển khai riêng. |
| Khả năng lỗi | Lỗi process có thể ảnh hưởng toàn bộ phần chạy chung. | Có thể cô lập một số lỗi, nhưng phát sinh lỗi mạng và phụ thuộc giữa tier. |
| Vận hành | Ít endpoint, cấu hình và pipeline hơn. | Cần service discovery, health check, tracing, secrets và pipeline cho từng đơn vị. |
| Giao dịch | Có thể dùng transaction cục bộ trên cùng resource manager. | Không có transaction cục bộ nào tự động bao trùm mọi tier. |

Tách tier có thể cải thiện khả năng scale khi tải của các phần khác nhau rõ rệt. Ví dụ, API đọc danh mục có tải cao có thể cần nhiều instance hơn worker tạo báo cáo. Nếu hai phần ở chung một deployment, scaling API cũng nhân bản worker hoặc làm worker cạnh tranh tài nguyên. Tách deployment cho phép điều chỉnh số lượng và tài nguyên độc lập.

Tuy nhiên, scale độc lập cần đo tải và xác định nút thắt. Nếu API bị chậm do truy vấn database, tăng số instance application có thể làm database quá tải hơn. Nếu độ trễ chủ yếu do dịch vụ ngoài, thêm tier không giải quyết nguyên nhân. Hãy dùng metrics, profiling và tracing để xác định điểm nghẽn trước khi thay đổi topology.

## 8. Tác động đến bảo mật và độ tin cậy

Ranh giới triển khai có thể được dùng để tạo vùng mạng và quyền truy cập riêng. Ví dụ, database chỉ cho phép kết nối từ application tier, không mở trực tiếp ra Internet. API gateway có thể kiểm tra token, giới hạn tốc độ và áp dụng chính sách truy cập ở biên. Worker xử lý nội bộ có thể chỉ nhận message từ broker và không mở HTTP endpoint công khai.

Nhưng tách tier không tự động tạo bảo mật. Một service nội bộ vẫn cần xác thực và phân quyền; secrets cần được quản lý; network policy cần được cấu hình; dữ liệu gửi qua mạng cần được bảo vệ. Trong một deployment unit, các tầng logic cũng vẫn cần kiểm soát quyền truy cập và xác thực ở đúng tầng.

Độ tin cậy cũng thay đổi. Nếu application tier được triển khai nhiều instance sau load balancer, một instance lỗi có thể được loại khỏi traffic. Tuy vậy, nếu tất cả instance phụ thuộc vào một database đơn lẻ đang hỏng, hệ thống vẫn không hoạt động. Mỗi tier cần health check và chiến lược phục hồi phù hợp. Với các lời gọi giữa tier, cần timeout, retry có giới hạn, circuit breaker khi phù hợp và xử lý kết quả không rõ ràng.

## 9. Cách quyết định có nên tách một phần thành tier riêng

Không nên tách chỉ vì sơ đồ có bốn tầng logic hoặc vì một lớp có nhiều trách nhiệm. Hãy xem xét các câu hỏi sau:

1. **Nhu cầu mở rộng có khác nhau không?** Một phần có tải, kiểu tài nguyên hoặc nhịp tăng trưởng khác đáng kể so với phần còn lại không?
2. **Có cần phát hành độc lập không?** Nhóm sở hữu phần đó có cần triển khai thường xuyên mà không phát hành toàn bộ ứng dụng không?
3. **Có cần cô lập lỗi hoặc tài nguyên không?** Một tác vụ nặng có làm ảnh hưởng API không? Tách process có giúp giới hạn tác động không?
4. **Có ranh giới bảo mật rõ ràng không?** Phần nào cần quyền truy cập mạng, dữ liệu hoặc secrets khác biệt?
5. **Dữ liệu và nghiệp vụ có quyền sở hữu độc lập không?** Nếu hai service cần sửa cùng một database hoặc transaction xuyên suốt, ranh giới service có thể chưa phù hợp.
6. **Chi phí phân tán có chấp nhận được không?** Đội ngũ có thể vận hành thêm endpoint, timeout, retry, tracing, deployment pipeline và xử lý eventual consistency không?
7. **Có bằng chứng đo đạc không?** Metrics, logs, traces hoặc profiling có cho thấy topology hiện tại là nút thắt thực sự không?

Nếu nhu cầu chủ yếu là giữ mã nguồn dễ hiểu, hãy bắt đầu bằng ranh giới logic trong cùng ứng dụng. Nếu cần scale một worker độc lập, có thể triển khai worker riêng mà không cần tách toàn bộ domain thành service mới. Nếu cần quyền sở hữu dữ liệu và vòng đời phát hành độc lập, khi đó mới cân nhắc service boundary lớn hơn.

## 10. Những nhầm lẫn thường gặp

- **Một tầng logic bằng một máy chủ:** không đúng. Nhiều tầng logic có thể chạy trong một JVM và một JAR.
- **Một tier chỉ có một tầng logic:** không đúng. Backend tier thường chứa controller, application service, domain và adapter hạ tầng.
- **Container luôn là một tier riêng:** container là đơn vị đóng gói/chạy; việc nó có tạo thành một tier độc lập hay không phụ thuộc cách triển khai, giao tiếp và vận hành.
- **Tách nhiều tier luôn tăng hiệu năng:** không đúng. Giao tiếp qua mạng tạo thêm độ trễ và điểm lỗi; lợi ích scale cần được đo và so sánh.
- **Tách package là đã cô lập triển khai:** không đúng. Package chỉ tổ chức mã nguồn; muốn phát hành riêng cần đơn vị build/deploy và hợp đồng giao tiếp phù hợp.
- **Tách service chỉ để phân tầng:** không đúng. Service boundary cần phản ánh quyền sở hữu và nhu cầu vận hành, không phải số lượng tầng trong sơ đồ.
- **Cùng tier nghĩa là dùng chung mọi thứ:** không nhất thiết. Một deployment có thể có nhiều process hoặc nhiều replica, mỗi process có pool và giới hạn tài nguyên riêng.

## 11. Quy trình thiết kế từ tầng logic đến topology triển khai

Khi bắt đầu một hệ thống hoặc xem xét thay đổi cách triển khai, hãy đi theo trình tự:

1. Xác định trách nhiệm logic: thành phần nào nhận request, điều phối ca sử dụng, giữ quy tắc nghiệp vụ và truy cập dữ liệu?
2. Xác định hướng phụ thuộc: tầng nào được gọi hoặc import tầng nào; hợp đồng nào cần ổn định?
3. Tổ chức package/module và kiểm thử ranh giới trong mã nguồn trước.
4. Xác định yêu cầu runtime: tải, độ trễ, tính sẵn sàng, bảo mật, tài nguyên, nhịp phát hành và quyền sở hữu dữ liệu.
5. Chọn deployment unit phù hợp: một ứng dụng, frontend và backend riêng, worker riêng hoặc các service độc lập khi có lý do rõ ràng.
6. Thiết kế giao tiếp giữa tier: HTTP/gRPC/message, timeout, retry, idempotency, authentication và quan sát vận hành.
7. Đo hiệu năng và kiểm tra khả năng phục hồi trên topology thực tế; điều chỉnh khi có bằng chứng.

Một kiến trúc phân tầng tốt có thể được triển khai theo nhiều topology khác nhau. Tầng logic giúp kiểm soát trách nhiệm và phụ thuộc trong mã nguồn; tier triển khai xác định cách các phần chạy, giao tiếp, mở rộng và được vận hành. Khi tách hai quyết định này, nhóm có thể giữ cấu trúc mã nguồn rõ ràng mà không phải phân tán ứng dụng quá sớm, đồng thời vẫn có đường tiến hóa sang các deployment unit độc lập khi nhu cầu thực tế xuất hiện.

