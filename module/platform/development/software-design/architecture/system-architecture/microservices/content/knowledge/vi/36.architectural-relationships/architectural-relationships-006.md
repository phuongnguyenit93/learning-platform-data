# Khối đơn thể mô-đun và vi dịch vụ trong kiến trúc kết hợp

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt modular monolith (khối đơn thể mô-đun) và microservices ở cấp độ mã nguồn, dữ liệu, tiến trình, triển khai và quyền sở hữu.
2. Giải thích vì sao một hệ thống có thể kết hợp hai mô hình thay vì buộc mọi capability phải nằm trong cùng một ứng dụng hoặc tách thành service riêng.
3. Thiết kế module boundary theo bounded context, business capability, ownership và vòng đời thay đổi.
4. Nhận diện module nào nên giữ trong cùng tiến trình và module nào có lý do đủ mạnh để tách thành microservice.
5. Thiết kế giao tiếp giữa module nội bộ và service từ xa, đồng thời tránh biến lời gọi trong tiến trình thành dependency mạng không cần thiết.
6. Quản lý transaction, database ownership, event, API contract, read model và consistency trong kiến trúc kết hợp.
7. Áp dụng strangler pattern, branch by abstraction và expand–migrate–contract để chuyển đổi từng phần có kiểm soát.
8. Tổ chức build, test, deploy, observability, security và on-call cho cả ứng dụng mô-đun lẫn service độc lập.
9. Đánh giá chi phí, rủi ro, khả năng mở rộng và lợi ích tổ chức trước khi tách hoặc gộp một capability.
10. Xây dựng lộ trình tiến hóa kiến trúc dựa trên bằng chứng thay vì đặt mục tiêu số lượng microservice.

Một kiến trúc kết hợp có thể giữ phần lớn domain trong một **modular monolith**, đồng thời triển khai riêng một số capability có nhu cầu độc lập rõ ràng dưới dạng microservices. Cách tiếp cận này cho phép chọn ranh giới triển khai theo nhu cầu thực tế của từng phần hệ thống.

## 1. Hai mô hình và điểm khác biệt

**Modular monolith** là một ứng dụng được triển khai như một đơn vị, nhưng mã nguồn được chia thành các module có trách nhiệm, interface và quy tắc phụ thuộc rõ. Các module thường chạy trong cùng tiến trình và có thể dùng chung transaction hoặc một database được quản lý theo module.

**Microservices** là các service có ranh giới runtime riêng, thường sở hữu dữ liệu và được triển khai độc lập. Chúng giao tiếp qua API, RPC, event hoặc message broker; mỗi service cần xử lý network failure, version compatibility và dữ liệu phân tán.

~~~text
MODULAR MONOLITH

             One application process
  +-------------------------------------------+
  |  Catalog Module  | Order Module            |
  |  - API           | - Use cases             |
  |  - Domain        | - Domain                |
  |  - Persistence   | - Persistence            |
  |------------------+-------------------------|
  |  Billing Module  | Customer Module         |
  |  - API           | - API                   |
  |  - Domain        | - Domain                |
  +-------------------------------------------+
             One deployable artifact


HYBRID ARCHITECTURE

  +-----------------------------+
  | Commerce Modular Monolith    |
  |                              |
  | Order Module                 |
  | Customer Module              |
  | Support Module               |
  +---------------+--------------+
                  |
             API / Events
                  |
       +----------+-----------+
       |                      |
       v                      v
  Catalog Service        Payment Service
  own deployment         own deployment
  own data boundary      own data boundary
~~~

Khác biệt cốt lõi không phải cách đặt tên thư mục. Đó là ranh giới tiến trình, dữ liệu, giao tiếp, triển khai và trách nhiệm vận hành.

| Khía cạnh | Modular monolith | Microservices |
| --- | --- | --- |
| Runtime | Nhiều module trong cùng process | Nhiều process/service |
| Deployment | Thường một artifact | Artifact riêng theo service |
| Giao tiếp nội bộ | Function/interface call | HTTP, gRPC, event hoặc message |
| Transaction | Có thể dùng transaction cục bộ | Thường cần workflow phân tán |
| Data ownership | Có thể dùng chung DB nhưng cần module ownership | Service sở hữu dữ liệu riêng |
| Failure mode | Lỗi process có thể ảnh hưởng nhiều module | Có partial failure và network failure |
| Scaling | Thường scale application; có thể tách worker | Có thể scale từng service |
| Testing | Module/component tests trong cùng ứng dụng | Contract/integration tests giữa service |
| Vận hành | Ít runtime unit hơn | Nhiều deployable unit và dependency |
| Autonomy | Module boundary ở code | Có thể độc lập cả code, data và deploy |

Một modular monolith có thể có cấu trúc rất tốt và dễ thay đổi. Một hệ thống microservices có thể vẫn coupling chặt nếu mọi thay đổi phải phát hành cùng lúc hoặc truy cập database của nhau.

## 2. Kiến trúc kết hợp là gì?

Kiến trúc kết hợp (hybrid architecture) dùng các kiểu triển khai khác nhau cho những capability khác nhau. Ví dụ:
- Order, Customer và Support nằm trong một modular monolith vì thường thay đổi cùng nhau và cần transaction cục bộ.
- Catalog tách thành service riêng vì traffic đọc cao, cache/search và scaling khác biệt.
- Payment tích hợp nhà cung cấp ngoài, có security boundary, quota và vận hành riêng.
- Notification chạy worker/service riêng vì workload bất đồng bộ và có thể scale theo queue.
- Data Platform xử lý pipeline và analytics với vòng đời khác ứng dụng giao dịch.

~~~text
                         Clients
                            |
                       API Gateway
                            |
             +--------------+---------------+
             |                              |
             v                              v
     Commerce Application              Catalog Service
     (Modular Monolith)                (Independent)
       |       |       |                       |
       |       |       +--> Support            +--> Catalog DB
       |       +----------> Customer
       +------------------> Order
               |
               +---- API/Event ----> Payment Service
               |
               +---- Event -------> Notification Worker
               |
               +---- Event -------> Data Platform
~~~

Trong ví dụ, các module nội bộ vẫn có boundary rõ. Khi một module có nhu cầu độc lập đủ lớn, nó có thể được tách ra thành service mà không phải tách tất cả module khác cùng lúc.

**Hybrid không phải trạng thái nửa vời.** Đây là một lựa chọn có chủ đích: dùng boundary trong tiến trình khi nó đủ tốt, và tạo boundary phân tán khi lợi ích của triển khai riêng lớn hơn chi phí.

## 3. Vì sao không cần tách mọi module thành microservice?

Mỗi service mới tạo thêm một đơn vị cần build, deploy, monitor, bảo mật và hỗ trợ. Nếu hai capability:
- Thường xuyên thay đổi cùng nhau.
- Cần transaction đồng bộ trên cùng một thao tác nghiệp vụ.
- Có cùng owner và cùng SLO.
- Có tải và nhu cầu tài nguyên tương tự.
- Chưa có lý do rõ ràng về failure isolation.
- Chưa có contract ổn định giữa chúng.

thì giữ chúng trong cùng modular monolith có thể đơn giản và kinh tế hơn.

Ví dụ Order và OrderLine thường thuộc cùng một aggregate hoặc transaction. Nếu tách thành hai service chỉ vì chúng là hai entity, mỗi lần tạo đơn có thể cần network call, saga và reconciliation mà không tạo lợi ích tổ chức tương ứng.

Ngược lại, Catalog có thể có lượng đọc rất lớn và thay đổi độc lập với Order; tách Catalog có thể cho phép cache, search và scaling riêng mà không cần nhân bản toàn bộ ứng dụng.

**Chọn ranh giới theo business capability và lý do vận hành**, không theo số class, bảng hay controller.

## 4. Bounded context và module boundary

Một module nên đại diện cho một phần domain có ngôn ngữ, quy tắc và trách nhiệm rõ. Domain-driven design gọi ranh giới ngữ nghĩa đó là bounded context.

Ví dụ trong thương mại điện tử:
- Catalog quản lý mô tả, danh mục và thuộc tính sản phẩm.
- Pricing quản lý giá và chính sách khuyến mãi.
- Order quản lý vòng đời đơn hàng.
- Payment quản lý giao dịch thanh toán.
- Inventory quản lý khả năng giữ và xuất kho.
- Customer quản lý hồ sơ khách hàng.
- Notification quản lý kênh gửi thông báo.

Không phải tất cả bounded context đều cần một microservice. Chúng có thể bắt đầu là module trong một ứng dụng, sau đó chỉ tách những context cần runtime independence.

### Dấu hiệu một module boundary tốt

- Có tên và mục đích nghiệp vụ dễ hiểu.
- Có owner chịu trách nhiệm.
- Dữ liệu được truy cập qua interface do module sở hữu.
- Module khác không sửa trực tiếp bảng hoặc entity nội bộ.
- Business rule được thực thi trong module sở hữu.
- Dependency direction rõ và ít vòng lặp.
- Có thể kiểm thử module mà không khởi chạy mọi module khác.
- Có thể thay implementation mà không buộc caller thay đổi.

### Dấu hiệu boundary yếu

- Các module import entity/repository nội bộ của nhau.
- Một bảng có nhiều nhóm ghi trực tiếp.
- Thay đổi một field làm hàng loạt module compile lại.
- Business logic bị chia giữa controller của module A và repository của module B.
- Một use case cần gọi vòng qua nhiều module để hoàn tất.
- Tên module theo tầng kỹ thuật (common, utils, shared) nhưng không có domain ownership.
- Mọi module đều phụ thuộc vào một shared model khổng lồ.

## 5. Cấu trúc modular monolith trong Spring Boot

Một ứng dụng Spring Boot có thể chia package theo module:

~~~text
commerce-app/
  src/main/java/com/example/commerce/
    CommerceApplication.java
    order/
      api/
      application/
      domain/
      infrastructure/
    customer/
      api/
      application/
      domain/
      infrastructure/
    support/
      api/
      application/
      domain/
      infrastructure/
    integration/
      catalog/
      payment/
    shared/
      observability/
      security/
  src/test/java/
    order/
    customer/
    support/
~~~

Cấu trúc package là bước đầu. Cần quy định package nào public, package nào internal và module nào được phụ thuộc vào module nào.

Một interface của Order module có thể là:

~~~java
package com.example.commerce.order.api;

public interface OrderQueries {
    OrderSummary findSummary(String orderId);
}
~~~

Implementation nằm trong module Order:

~~~java
package com.example.commerce.order.application;

import com.example.commerce.order.api.OrderQueries;

public class OrderQueryService implements OrderQueries {
    // Inject repository thuộc sở hữu Order.
}
~~~

Customer hoặc Support có thể gọi interface được công bố thay vì truy cập OrderRepository hoặc OrderEntity trực tiếp.

Mã ví dụ chỉ minh họa boundary; trong ứng dụng thật cần định nghĩa DTO, validation, exception và cách đăng ký bean phù hợp.

### Dùng Spring Modulith khi phù hợp

Spring Modulith cung cấp cơ chế hỗ trợ tổ chức và kiểm tra module trong ứng dụng Spring Boot. Có thể dùng để:
- Xác định module theo package.
- Kiểm tra dependency giữa module.
- Phát hiện truy cập package nội bộ.
- Viết integration test theo module.
- Ghi nhận quan hệ module bằng tài liệu/diagram.
- Hỗ trợ event publication trong ứng dụng.

Không bắt buộc mọi modular monolith dùng Spring Modulith. Có thể bắt đầu bằng package convention, ArchUnit hoặc các test kiến trúc riêng. Điều quan trọng là boundary được kiểm tra tự động và không phụ thuộc hoàn toàn vào quy ước miệng.

## 6. Kiểm soát dependency giữa các module

Ví dụ dependency mong muốn:

~~~text
Web/API Layer
      |
      v
Application Use Cases
      |
      v
Domain Model
      ^
      |
Infrastructure implements ports

Order Module ---> Customer Public API
Order Module ---> Pricing Public API
Order Module ---> Internal Order Repository
~~~

Một module nên phụ thuộc vào public interface của module khác. Tránh để Order import CustomerEntity rồi dùng entity đó làm dữ liệu nghiệp vụ nội bộ.

Có thể áp dụng:
- Java package visibility và module boundaries.
- Gradle subprojects hoặc Maven modules khi cần build isolation.
- ArchUnit tests kiểm tra dependency rule.
- Spring Modulith module verification.
- API/DTO riêng cho từng module.
- Code review rule không import internal package.

### Có nên tạo một Gradle subproject cho mỗi module?

Không nhất thiết. Package/module boundary có thể đủ khi build vẫn nhanh và các module dùng chung artifact. Tạo subproject có ích nếu cần:
- Compile/test riêng.
- Dependency graph rõ hơn.
- Tách API artifact khỏi implementation.
- Build cache và task isolation tốt hơn.

Nhưng mỗi subproject thêm cấu hình và có thể làm build phức tạp. Không tạo module build chỉ để mỗi folder có một build.gradle.

## 7. Quy tắc sở hữu dữ liệu trong kiến trúc kết hợp

Một vấn đề thường gặp là modular monolith dùng chung database, trong khi microservices sở hữu database riêng. Hai cách này có thể cùng tồn tại nếu quy tắc truy cập rõ.

~~~text
Commerce DB
  +-- order tables       (Order module owns)
  +-- customer tables    (Customer module owns)
  +-- support tables     (Support module owns)

Catalog Service
  +-- Catalog DB         (Catalog owns)

Payment Service
  +-- Payment DB         (Payment owns)
~~~

Trong Commerce DB, các module có thể cùng dùng một database engine/schema hoặc schema riêng. Nhưng **mỗi module cần quyền sở hữu logic đối với bảng của mình**:
- Chỉ Order module thay đổi order tables.
- Customer module công bố API để đọc/cập nhật hồ sơ.
- Support dùng API hoặc query interface được công bố.
- Migration của một module không được tự ý phá dữ liệu module khác.

Khi một module được tách ra, cần chuyển quyền sở hữu dữ liệu và đường truy cập. Việc tạo database mới nhưng vẫn cho monolith truy cập trực tiếp cả hai nơi có thể duy trì coupling lâu dài.

### Shared database có phải luôn sai?

Không. Một database cluster có thể phục vụ nhiều schema/module nếu:
- Có ownership rõ.
- Quyền DB tách theo role/schema khi phù hợp.
- Migration có kiểm soát.
- Không truy cập bảng nội bộ của module khác.
- Backup/restore và capacity được quản lý.
- Không tạo một transaction cross-service khó kiểm soát khi module được tách.

Logical data ownership có thể đi trước physical database separation. Đây thường là bước chuyển đổi thực tế hơn.

## 8. Giao tiếp nội bộ và giao tiếp giữa service

Trong modular monolith, module gọi public interface bằng function call trong cùng process. Khi capability được tách thành microservice, giao tiếp chuyển qua network hoặc message broker.

| Tình huống | Trong modular monolith | Trong hybrid |
| --- | --- | --- |
| Order cần thông tin Customer | Customer public API/interface | HTTP/gRPC hoặc snapshot/event |
| Order cần xác nhận Payment | Payment port/adapter | Payment API hoặc command/event |
| Catalog thay đổi sản phẩm | Module event nội bộ | Integration event từ Catalog Service |
| Notification gửi email | Application event/job | Queue và Notification Worker |
| Reporting đọc dữ liệu | Query module được công bố | Data product/read model |

Không nên giữ nguyên một interface đồng bộ rồi thay implementation bằng HTTP mà không xem xét timeout, retry, partial failure và latency. Một method call nội bộ có thể trả kết quả ngay; network call có thể timeout sau khi server đã thực hiện side effect.

### Ports and adapters

Có thể định nghĩa một port trong Order:

~~~java
public interface PaymentPort {
    PaymentResult authorize(AuthorizePayment command);
}
~~~

Trong modular monolith, implementation có thể là adapter gọi module Payment nội bộ. Khi tách Payment thành service, implementation thay bằng HTTP/gRPC client. Use case Order vẫn phụ thuộc vào abstraction, nhưng contract và semantics phải đủ rõ để hai cách triển khai tương đương.

Không dùng abstraction để che giấu distributed failure. Adapter từ xa phải thể hiện timeout, lỗi retryable, idempotency và trạng thái pending đúng trong application model.

## 9. Khi nào giao tiếp đồng bộ, khi nào dùng event?

**Synchronous API** phù hợp khi caller cần câu trả lời ngay và nghiệp vụ không thể tiếp tục nếu chưa có kết quả. Ví dụ lấy báo giá hiện tại hoặc kiểm tra quyền trước khi thực hiện một thao tác.

**Asynchronous event/command** phù hợp khi công việc có thể xử lý sau, cần tách thời gian sống của producer và consumer, hoặc có nhiều consumer phản ứng với một thay đổi. Ví dụ gửi email sau khi đơn được xác nhận hoặc cập nhật analytics.

Trong hybrid architecture:
- Giao tiếp giữa module nội bộ có thể là interface/event trong process.
- Giao tiếp qua boundary microservice cần contract rõ.
- Không đưa mọi lời gọi nội bộ lên broker chỉ để “đồng nhất kiến trúc”.
- Không dùng synchronous call xuyên nhiều service cho mọi bước nếu có thể xử lý bằng workflow bất đồng bộ.

### Ví dụ tạo đơn

~~~text
Client
  |
  v
Commerce App / Order Module
  |
  +--> Customer module: validate reference
  |
  +--> Pricing Service: quote / price snapshot
  |
  +--> Order DB: create order + outbox
                     |
                     v
                  Broker
                     |
            +--------+---------+
            |                  |
            v                  v
      Inventory Service   Notification
            |
            v
      reservation result
            |
            v
      Order state update
~~~

Thiết kế thực tế cần xác định bước nào đồng bộ, bước nào bất đồng bộ, khi nào đơn được coi là accepted/confirmed, cách retry và cách bù trừ khi giữ hàng hoặc thanh toán thất bại.

## 10. Transaction trong module và giữa microservice

Trong modular monolith, nhiều module có thể tham gia cùng một database transaction nếu domain và schema cho phép. Ví dụ Order và OrderLine cùng commit một giao dịch trong Order boundary.

Khi tách module thành service, transaction đó có thể trở thành distributed workflow. Cần dùng:
- Saga orchestration/choreography.
- Transactional outbox.
- Idempotent command/event consumer.
- Reservation và compensation.
- State machine cho trạng thái trung gian.
- Reconciliation khi một bước không có kết quả rõ.

Không nên tách một module có transaction xuyên suốt dày đặc nếu chưa có cách phân chia business invariant hợp lý.

### Transaction boundary là tín hiệu chọn service boundary

Hãy quan sát những dữ liệu luôn phải cập nhật nguyên tử. Nếu một thao tác thường xuyên ghi Order, Payment và Inventory trong cùng một transaction, việc tách ba phần có thể tăng chi phí đáng kể. Có thể giữ phần có invariant chặt trong cùng module hoặc thiết kế workflow bất đồng bộ nếu nghiệp vụ cho phép trạng thái trung gian.

Không phải mọi transaction cross-module đều cấm tách; câu hỏi là tần suất, độ nhạy của invariant và khả năng chấp nhận eventual consistency.

## 11. Consistency trong kiến trúc kết hợp

Modular monolith có thể đọc dữ liệu trong cùng transaction và thường có consistency mạnh hơn giữa module dùng chung DB. Microservice có data store riêng thường phải chấp nhận replication lag hoặc eventual consistency cho một số read model.

Ví dụ Catalog Service phát ProductUpdated; Commerce App nhận event và cập nhật một projection phục vụ màn hình hỗ trợ. Trong khoảng event chưa được xử lý, projection có thể cũ.

Cần xác định:
- Nguồn dữ liệu chuẩn cho từng field.
- Read-after-write requirement.
- Freshness SLA cho projection.
- Cách xử lý duplicate/out-of-order.
- Cơ chế rebuild/replay.
- Những quyết định nghiệp vụ nào bắt buộc đọc nguồn chuẩn.

Không dùng projection eventual-consistent để quyết định giao dịch nhạy cảm nếu nó có thể stale ngoài mức nghiệp vụ chấp nhận.

### Snapshot nghiệp vụ

Order có thể lưu product name và unit price tại thời điểm đặt hàng. Đây là snapshot có chủ đích để giữ lịch sử giao dịch, không phải bản sao cần luôn đồng bộ với Catalog. Hợp đồng phải phân biệt dữ liệu snapshot và dữ liệu tham chiếu hiện hành.

## 12. Chiến lược tách module thành microservice

Một module trong modular monolith không tự động trở thành microservice chỉ bằng cách chuyển package sang repository khác. Cần lần lượt xử lý:
1. Ownership và domain boundary.
2. Public interface và contract.
3. Database ownership.
4. Giao tiếp đồng bộ/bất đồng bộ.
5. Migration dữ liệu và cutover.
6. Build/test/deploy pipeline riêng.
7. Observability, security, capacity và on-call.
8. Rollback và loại bỏ đường cũ.

### Strangler pattern

Strangler pattern chuyển dần traffic hoặc capability từ monolith sang service mới:

~~~text
Before:
  Client ---> Monolith
                 |
                 +--> Catalog logic

Transition:
  Client ---> Monolith -----> Catalog Service
                 |
                 +--> Other modules

After:
  Client ---> Gateway ---> Catalog Service
                         -> Commerce App
~~~

Ban đầu monolith có thể đóng vai trò facade hoặc adapter, chuyển một số request tới service mới. Sau khi mọi caller đã chuyển, logic cũ được loại bỏ.

Lợi ích là có thể chuyển theo lát nhỏ và giữ hệ thống hoạt động. Chi phí là phải duy trì một thời gian bridge, dual-read/dual-write hoặc routing logic; cần deadline và điều kiện xóa đường cũ để tránh lớp chuyển tiếp tồn tại vĩnh viễn.

## 13. Branch by abstraction

Khi code hiện tại gọi trực tiếp implementation nội bộ, có thể tạo abstraction trước khi thay đổi vị trí triển khai.

~~~text
Before:
  OrderUseCase ---> CatalogRepository

Step 1:
  OrderUseCase ---> CatalogPort
                         ^
                         |
                  LocalCatalogAdapter

Step 2:
  OrderUseCase ---> CatalogPort
                         ^
                         |
                  RemoteCatalogAdapter

Step 3:
  Remove local implementation after cutover
~~~

Các bước:
1. Đặt interface tại boundary do caller sở hữu.
2. Chuyển caller sử dụng interface, giữ behavior cũ.
3. Viết implementation remote và kiểm tra contract.
4. Chuyển traffic bằng config/feature flag nếu cần.
5. Đối soát kết quả, quan sát latency/error.
6. Xóa implementation cũ khi không còn consumer.

Đây là cách giảm rủi ro vì phần lớn thay đổi cấu trúc được thực hiện trước khi chuyển network boundary.

## 14. Di chuyển dữ liệu từ monolith sang service mới

Giả sử Catalog data đang nằm trong Commerce DB và cần chuyển sang Catalog DB.

Một lộ trình minh họa:
1. Xác định bảng, owner, foreign key và mọi truy vấn direct access.
2. Tạo schema mới ở Catalog Service.
3. Backfill dữ liệu hiện tại với checkpoint và kiểm tra số lượng/hash nghiệp vụ.
4. Thiết lập CDC/outbox hoặc một cơ chế đồng bộ thay đổi phát sinh trong lúc backfill.
5. Chuyển một phần read traffic sang service mới.
6. So sánh kết quả cũ/mới và đo latency.
7. Chuyển write ownership sang Catalog.
8. Ngừng ghi vào bảng cũ sau khi các caller đã chuyển.
9. Xóa read/write path cũ khi điều kiện hoàn tất được đáp ứng.

### Dual-write có nguy cơ mất nhất quán

Nếu monolith ghi DB cũ rồi gọi Catalog API để ghi DB mới, một trong hai có thể thành công còn một bên thất bại. Không có transaction nguyên tử tự động giữa hai hệ thống.

Có thể dùng outbox, CDC hoặc một source of truth duy nhất trong giai đoạn chuyển. Nếu dual-write bắt buộc, cần idempotency, reconciliation và cơ chế xử lý conflict rõ. Tránh để hai nơi cùng là nguồn chuẩn lâu dài.

### Backfill và event ordering

Trong khi backfill, một ProductUpdated mới có thể tới trước hoặc sau snapshot cũ. Cần version/timestamp/sequence đáng tin để không để dữ liệu cũ ghi đè dữ liệu mới. Kiểm tra cả record bị xóa trong lúc backfill và tombstone.

## 15. Expand–migrate–contract cho schema và API

Một thay đổi breaking nên được chia pha:

**Expand**
- Thêm bảng/cột/API/event mới.
- Giữ cấu trúc cũ hoạt động.
- Deploy producer bridge và kiểm thử tương thích.

**Migrate**
- Backfill dữ liệu.
- Chuyển consumer sang interface mới.
- Dual-read hoặc adapter theo kế hoạch.
- Quan sát traffic, errors và reconciliation.

**Contract**
- Xác nhận không còn consumer hợp lệ dùng đường cũ.
- Ngừng ghi/đọc cũ.
- Xóa cột, endpoint, package hoặc adapter.
- Cập nhật catalog, tài liệu và runbook.

Đừng xóa database column trong cùng release đầu tiên thêm cột mới nếu pod cũ vẫn đang chạy. Đừng bỏ endpoint monolith trước khi mobile/partner/worker đã chuyển.

## 16. Hybrid architecture trong monorepo

Một monorepo có thể chứa modular monolith và một số microservice:

~~~text
platform/
  commerce-app/
    build.gradle
    src/main/java/
      order/
      customer/
      support/
  catalog-service/
    build.gradle
    src/main/java/
  payment-service/
    build.gradle
    src/main/java/
  notification-worker/
    build.gradle
    src/main/java/
  contracts/
    openapi/
    events/
  build-logic/
~~~

Có thể build riêng:

~~~bash
./gradlew :commerce-app:test
./gradlew :catalog-service:bootJar
./gradlew :payment-service:check
~~~

Nếu service phụ thuộc contract artifact trong cùng repository, task graph có thể build phần contract cần thiết. Nhưng không nên để build Catalog tự động compile toàn bộ Commerce App.

Monorepo giúp phối hợp thay đổi xuyên boundary trong một pull request, nhưng cần:
- Path/dependency-aware CI.
- Ownership theo thư mục/module.
- CODEOWNERS hoặc review policy phù hợp.
- Versioning artifact/contract rõ.
- Build convention được test.
- Quy tắc không import implementation module ngoài boundary.

## 17. Hybrid architecture trong multi-repo

Một lựa chọn khác:
- Commerce modular monolith trong một repo.
- Catalog Service trong repo riêng.
- Payment Service trong repo riêng.
- Notification Worker trong repo riêng.
- Contract/schema trong registry hoặc repository được version.

Ưu điểm là ownership và pipeline rõ, service có nhịp phát hành riêng. Chi phí là thay đổi xuyên repo cần pull request ở nhiều nơi, dependency artifact cần publish và consumer phải theo dõi compatibility.

Có thể dùng một repository contract riêng, hoặc publish OpenAPI/Protobuf/JSON Schema artifact từ producer. Không cần share implementation source giữa service chỉ để dùng chung DTO.

## 18. CI/CD và release trong kiến trúc kết hợp

Mỗi deployable unit nên có pipeline phù hợp:
- Modular monolith build/test/package một artifact.
- Catalog service build/deploy riêng.
- Payment service có release/security gates phù hợp.
- Worker có kiểm thử message và consumer contract riêng.
- Contract change kích hoạt kiểm tra các consumer liên quan.

Một pipeline mẫu:

~~~text
Change detected
      |
      v
Identify affected modules/services
      |
      v
Compile + unit tests for affected build
      |
      v
Architecture + contract checks
      |
      v
Integration tests for changed boundary
      |
      v
Package immutable artifact/image
      |
      v
Scan + publish
      |
      v
Deploy selected unit
      |
      v
Canary + SLO verification
~~~

Nếu một thay đổi chỉ tác động Catalog, không nhất thiết phải build/deploy Payment. Nhưng nếu contract Catalog thay đổi, consumer verification của Order/Commerce cần chạy theo impact graph.

### Build độc lập không đồng nghĩa bỏ kiểm thử hệ thống

Vẫn cần một số E2E cho checkout, payment, inventory và các hành trình quan trọng. Mục tiêu là không bắt mọi PR chạy mọi service trong mọi test; chọn phạm vi theo dependency và risk.

## 19. API gateway và routing trong giai đoạn chuyển đổi

Khi tách một capability, gateway có thể route một số endpoint sang service mới và giữ endpoint khác ở monolith.

~~~text
/api/catalog/**  ---> Catalog Service
/api/orders/**   ---> Commerce App
/api/customers/** ---> Commerce App
~~~

Gateway cần quản lý:
- Authentication/authorization và tenant context.
- Rate limit và quota.
- Routing/version.
- Request/response headers.
- Correlation ID và trace propagation.
- Timeout và retry có giới hạn.
- Canary/traffic splitting nếu phù hợp.

Không đưa business logic phức tạp vào gateway chỉ để tránh sửa consumer. Gateway là lớp định tuyến/policy; logic domain nên thuộc service sở hữu.

Trong giai đoạn chuyển, tránh hai route cùng ghi một nguồn dữ liệu mà không có ownership rõ. Routing cần xác định một writer có thẩm quyền cho từng capability.

## 20. Security boundary trong mô hình kết hợp

Module cùng process thường có thể chia sẻ identity/context trong ứng dụng, nhưng microservice có network boundary riêng. Khi tách:
- Service-to-service authentication cần rõ.
- Authorization theo user/tenant phải được truyền an toàn.
- Không tin header do client tự gửi nếu gateway chưa xác thực/ghi đè.
- Secret/certificate có vòng đời và rotation.
- Network policy giới hạn caller.
- API/event payload được phân loại và tối thiểu hóa.
- Audit access và data retention.
- Không dùng database credential chung cho mọi service nếu cần isolation.

Một service tách riêng có thể tạo security boundary mạnh hơn, nhưng chỉ khi identity, authorization, network và secret được cấu hình đúng. Tách process mà tất cả service dùng cùng quyền database/admin không đem lại isolation đáng kể.

## 21. Observability và vận hành xuyên boundary

Một request có thể đi từ monolith sang Catalog, Payment và Notification. Cần correlation/trace context thống nhất để điều tra.

Theo dõi:
- Latency và error rate theo module/service.
- Request volume và fan-out.
- Dependency timeout/retry/circuit breaker.
- Queue lag và event processing age.
- DB connection, lock, query latency.
- Resource usage và autoscaling.
- Contract mismatch, schema decode failure.
- Business outcome như checkout success, payment completion.

Trong modular monolith, metrics theo module giúp biết module nào đang gây tải hoặc lỗi dù cùng process. Trong microservice, service-level metrics và distributed tracing giúp khoanh vùng network/dependency.

Không chỉ đo CPU và memory. Một Payment Service CPU thấp nhưng bị provider rate limit vẫn có thể là điểm nghẽn của checkout.

## 22. SLO và failure isolation

Hybrid architecture cần định nghĩa SLO ở cả service và journey:
- Catalog p95 dưới ngưỡng.
- Payment success/error rate theo provider behavior.
- Checkout completion rate.
- Notification delivery age.
- Data projection freshness.

Khi Catalog down, Order có thể dùng snapshot giá/metadata nếu nghiệp vụ cho phép; khi Payment down, checkout có thể ở trạng thái pending; khi Notification down, đơn vẫn có thể được tạo và thông báo gửi sau. Fallback phải theo domain semantics, không chỉ trả một response mặc định.

### Failure mode khác nhau

- Module trong cùng process có thể bị ảnh hưởng bởi JVM crash, memory pressure hoặc thread pool exhaustion.
- Microservice có thể lỗi riêng nhưng tạo timeout và retry storm ở caller.
- Shared database/cache/broker có thể là điểm lỗi chung.
- Gateway có thể trở thành bottleneck.
- Một lỗi trong module có thể chiếm thread pool chung và ảnh hưởng module khác.

Tách service chỉ cải thiện isolation khi có resource boundary, timeout, concurrency limit, fallback và dependency topology phù hợp.

## 23. Scaling theo nhu cầu

Một lợi ích của hybrid là chỉ scale capability cần thiết.

Ví dụ:
- Catalog Service scale từ 3 lên 15 replica trong flash sale.
- Commerce App giữ 5 replica vì Order/Customer có tải thấp hơn.
- Notification Worker scale theo queue lag.
- Payment Adapter bị giới hạn bởi quota provider, nên dùng rate limiter thay vì tăng pod vô hạn.

Nhưng nếu Commerce App vẫn chứa Catalog logic hoặc mọi request Order gọi Catalog đồng bộ nhiều lần, phần tải có thể vẫn bị coupling. Sau khi tách, phải loại bỏ logic cũ và tối ưu fan-out/cache.

### Scale độc lập cần capacity của dependency

Catalog scale lên 15 pod nhưng database Catalog chỉ chịu 500 connection hoặc Search cluster đã nghẽn thì service không tăng throughput tương ứng. Hãy tính connection pool tổng, DB IOPS, cache, broker và provider quota.

## 24. Chi phí và trade-off của kiến trúc kết hợp

| Hạng mục | Lợi ích | Chi phí/rủi ro |
| --- | --- | --- |
| Modular monolith core | Transaction và code flow đơn giản | Một artifact, blast radius process chung |
| Microservice chọn lọc | Scale/deploy/ownership riêng | Network, data consistency, on-call |
| Shared platform | Chuẩn hóa build, observability, security | Chi phí platform và dependency chung |
| API/event contracts | Ranh giới rõ và consumer tự chủ | Versioning, compatibility và migration |
| Data replication | Read model phù hợp từng workload | Lag, replay, reconciliation |
| Selective extraction | Giảm rủi ro big-bang | Giai đoạn bridge và dual-run |
| Monorepo | Dễ thay đổi xuyên boundary | CI/ownership cần quản lý |
| Multi-repo | Pipeline/release rõ | Coordination và dependency artifacts |

TCO phải tính cả:
- Runtime baseline của mỗi process.
- CI/CD, artifact registry và image scanning.
- Database, broker, cache và storage.
- Logs, metrics, traces và alert.
- Security, secret, certificate và audit.
- Testing nhiều phiên bản.
- Team coordination, on-call và incident.
- Migration, dual-run và cleanup đường cũ.

Kiến trúc kết hợp không mặc định rẻ hơn. Nó giúp chọn đúng nơi chấp nhận chi phí phân tán và nơi nên giữ đơn giản.

## 25. Khi nào nên giữ capability trong modular monolith?

Giữ module nội bộ thường hợp lý khi:
- Business rules thay đổi cùng nhau.
- Có nhiều transaction cần atomicity cục bộ.
- Tải và SLO tương tự các module khác.
- Không cần failure/security boundary riêng.
- Cùng một team sở hữu và vận hành.
- Giao tiếp giữa module rất thường xuyên và đồng bộ.
- Chi phí tách dữ liệu/API lớn hơn lợi ích.
- Domain chưa ổn định, boundary còn đang học hỏi.

Ví dụ Order và OrderLine có thể nên ở cùng module; Customer và Support có thể ở chung ứng dụng nhưng tách module nếu ownership/data boundary rõ. Quyết định phụ thuộc nghiệp vụ, không có danh sách module luôn phải tách.

## 26. Khi nào nên tách thành microservice?

Tách khi có bằng chứng về một hoặc nhiều nhu cầu:
- Một capability cần deploy theo nhịp riêng thường xuyên.
- Workload cần scaling khác biệt đáng kể.
- Cần failure isolation hoặc security boundary riêng.
- Data ownership đã rõ và có thể chuyển khỏi shared DB.
- Một team có thể sở hữu từ code tới production.
- Contract với consumer ổn định và kiểm thử được.
- Hạ tầng/observability/on-call đủ trưởng thành.
- Có thể chấp nhận consistency model và workflow mới.
- Lợi ích đo được lớn hơn migration và vận hành bổ sung.

Không tách chỉ vì module có nhiều class, nhiều bảng hoặc muốn dùng một công nghệ khác. Một module lớn có thể cần refactor nội bộ trước khi có lý do triển khai riêng.

## 27. Một ví dụ lựa chọn boundary: Commerce

Giả sử hệ thống có:
- Catalog: 70% traffic đọc, nhiều cache/search, cập nhật không quá thường xuyên.
- Order: nghiệp vụ giao dịch, nhiều invariant và cần transaction rõ.
- Payment: tích hợp provider ngoài, quota và security riêng.
- Notification: tác vụ bất đồng bộ, retry và queue.
- Support: giao diện nội bộ, thay đổi cùng Order/Customer.

Một phương án kết hợp:
- Tách Catalog thành microservice.
- Tách Payment khi có ownership và quota management rõ.
- Tách Notification Worker vì workload queue độc lập.
- Giữ Order, Customer và Support trong modular monolith nếu chúng cần thay đổi/transaction cùng nhau.
- Định nghĩa contract cho Catalog, Payment và Notification.
- Giữ module boundary nội bộ để sau này có thể tách thêm nếu bằng chứng xuất hiện.

Đây là lựa chọn minh họa. Nếu Order và Customer có nhịp thay đổi độc lập hoặc cần security isolation, ranh giới có thể khác. Nếu Catalog và Order luôn cần transaction mạnh cùng dữ liệu, tách Catalog có thể không phù hợp như ví dụ.

## 28. Roadmap tiến hóa từ monolith sang hybrid

Một roadmap thực tế có thể gồm:

**Giai đoạn 1 — Làm rõ cấu trúc**
- Lập domain map và dependency graph.
- Xác định module owner.
- Tách package theo capability.
- Ngăn truy cập package/database nội bộ.
- Thêm architecture tests.

**Giai đoạn 2 — Tăng chất lượng build và test**
- Build/test theo module.
- CI có dependency impact analysis.
- Contract và integration tests cho boundary.
- Observability theo module/use case.
- Chuẩn hóa config và release.

**Giai đoạn 3 — Chọn capability để tách**
- Dựa vào release wait, scaling, failure, data ownership.
- Định nghĩa API/event contract.
- Thiết kế migration, data ownership và rollback.
- Tạo service mới với pipeline và owner riêng.

**Giai đoạn 4 — Chuyển traffic và dữ liệu**
- Backfill, CDC/outbox nếu cần.
- Branch by abstraction/strangler routing.
- Canary và reconciliation.
- Chuyển write ownership.
- Loại bỏ đường cũ sau khi đạt gate.

**Giai đoạn 5 — Đo và điều chỉnh**
- So sánh SLO, lead time, deployment autonomy và TCO.
- Kiểm tra incident, on-call và dependency wait.
- Giữ, tách thêm hoặc gộp lại theo dữ liệu.

Không cần cam kết trước rằng cuối cùng mọi module sẽ thành microservice. Có thể dừng ở một kiến trúc kết hợp ổn định trong nhiều năm.

## 29. Rollback và trạng thái chuyển tiếp

Trong quá trình tách, có thể xảy ra:
- Service mới lỗi sau khi traffic đã chuyển.
- Backfill thiếu record.
- Event bị duplicate/out-of-order.
- Monolith và service mới ghi lệch nhau.
- Consumer cũ không tương thích.
- Database mới không đủ capacity.

Kế hoạch rollback cần trả lời:
1. Ai là nguồn dữ liệu chuẩn trong mỗi pha?
2. Có thể route traffic về monolith trong bao lâu?
3. Những write đã phát sinh ở service mới có cần đồng bộ ngược không?
4. Event đã publish có thể được replay như thế nào?
5. Khi nào không thể rollback vì schema/data đã thay đổi?
6. Cần forward-fix thay vì rollback trong tình huống nào?
7. Có reconciliation và idempotency để không nhân đôi giao dịch không?

Không thiết kế rollback chỉ bằng cách đổi URL gateway nếu dữ liệu đã có ở hai nơi và mỗi nơi có thể ghi độc lập.

## 30. Architecture fitness functions

Có thể kiểm tra một số thuộc tính kiến trúc tự động:
- Module không import package internal của module khác.
- Chỉ owner module truy cập repository/table thuộc module.
- Không có vòng phụ thuộc module.
- Mỗi microservice có build task/test riêng.
- API/event schema có compatibility checks.
- Không dùng shared entity cho persistence của nhiều service.
- Các service bắt buộc có health, metrics và trace context.
- Consumer contracts đang được hỗ trợ đều pass.
- Tỷ lệ coordinated deployment được theo dõi.
- Không còn direct DB dependency ngoài inventory.

Các kiểm tra này là **fitness functions**: quy tắc tự động giúp kiến trúc không suy giảm dần khi code thay đổi. Chúng không thay thế domain review; một module có thể pass package rules nhưng boundary nghiệp vụ vẫn sai.

### Ví dụ ArchUnit

~~~java
@AnalyzeClasses(packages = "com.example.commerce")
class ModuleBoundaryTest {

    @ArchTest
    static final ArchRule order_must_not_access_customer_internal =
        noClasses()
            .that().resideInAPackage("..order..")
            .should().dependOnClassesThat()
            .resideInAPackage("..customer.infrastructure..");
}
~~~

Mẫu minh họa một quy tắc kiến trúc; cần cấu hình ArchUnit dependency và package thực tế của ứng dụng. Có thể thêm rule cho module khác hoặc dùng Spring Modulith để xác định module dependencies.

## 31. Các anti-pattern trong kiến trúc kết hợp

**Modulith chỉ là package naming:** mọi module vẫn truy cập bảng/entity của nhau. Cần public API, dependency rules và architecture tests.

**Distributed monolith:** nhiều service nhưng phải deploy cùng nhau, dùng chung database và gọi đồng bộ chặt. Cần giảm coupling và xác lập ownership.

**Shared database không owner:** service nào cũng ghi cùng bảng, không ai kiểm soát migration. Cần module/service ownership và role/schema policy.

**Tách một transaction thành nhiều network call:** tăng latency và tạo trạng thái trung gian mà business không chấp nhận. Giữ boundary transaction phù hợp hoặc thiết kế saga có chủ đích.

**Giữ hai nguồn chuẩn lâu dài:** monolith và service cùng ghi một dữ liệu, không có reconciliation. Cần một writer owner và lộ trình cutover.

**Gateway chứa domain logic:** routing layer biến thành một monolith mới. Đưa business rules về service sở hữu.

**Common module khổng lồ:** mọi module phụ thuộc DTO/entity/domain model chung. Tách contract/library nhỏ và version hóa.

**Tách theo entity/table:** mỗi bảng thành service riêng, làm nghiệp vụ cần nhiều network call. Chọn theo business capability/aggregate.

**Tách nhưng không có on-call:** service có pipeline riêng nhưng không ai vận hành. Owner phải chịu trách nhiệm production.

**Không có compatibility window:** producer và consumer deploy khác thời điểm làm hỏng runtime. Dùng expand–migrate–contract.

**Dual-write không đối soát:** hai DB lệch nhau mà không biết. Có source of truth, outbox/CDC và reconciliation.

**Không dọn adapter chuyển tiếp:** strangler proxy/compatibility layer tồn tại mãi và tăng complexity. Đặt owner, metric và sunset criteria.

**Scale service nhưng quên dependency:** tăng replica làm DB/cache/provider quá tải. Capacity planning toàn tuyến.

**Đo thành công bằng số microservice:** tăng số deployable unit nhưng lead time/TCO không cải thiện. Đo outcome và autonomy thật.

## 32. Checklist thiết kế kiến trúc kết hợp

- [ ] Domain/bounded context được xác định và có owner.
- [ ] Module boundary trong modular monolith có public API và dependency rules.
- [ ] Các module không truy cập persistence nội bộ của nhau.
- [ ] Service được tách có lý do deployment/scaling/failure/security rõ.
- [ ] Mỗi microservice sở hữu dữ liệu và migration của mình.
- [ ] Shared DB có ownership, permission và migration policy.
- [ ] API/event contract có schema, semantics, version và consumer inventory.
- [ ] Giao tiếp sync/async được chọn theo yêu cầu nghiệp vụ.
- [ ] Transaction boundary và eventual consistency được định nghĩa.
- [ ] Outbox, idempotency, retry và reconciliation có nơi sở hữu.
- [ ] Migration có backfill, cutover, rollback và cleanup path.
- [ ] Build/test/deploy pipeline có thể chạy theo deployable unit.
- [ ] Contract tests bao phủ consumer được hỗ trợ.
- [ ] Observability xuyên boundary có correlation và owner.
- [ ] Security identity, secret, tenant và data retention được quản lý.
- [ ] Capacity và SLO của shared dependencies được tính.
- [ ] On-call/runbook cho mỗi service đã có.
- [ ] TCO bao gồm platform, network, data và coordination.
- [ ] Có metric trước/sau migration và tiêu chí dừng.
- [ ] Không đặt mục tiêu tách tất cả module nếu chưa có lợi ích chứng minh.

## 33. Bài tập thực hành

Một nền tảng thương mại điện tử hiện là một Spring Boot monolith. Trong ứng dụng có các module Catalog, Order, Customer, Payment, Notification và Support. Catalog chiếm phần lớn traffic đọc; Payment tích hợp nhà cung cấp ngoài; Notification xử lý email/SMS qua queue; Order và Customer thường xuyên tham gia cùng một giao dịch; Support chủ yếu đọc dữ liệu.

Hãy đề xuất một kiến trúc kết hợp và giải thích:

1. Module nào nên ở trong modular monolith, module nào có thể tách thành microservice? Nêu bằng chứng cần thu thập trước khi quyết định.
2. Sơ đồ runtime và data ownership sau khi tách.
3. Public interface và dependency rules giữa các module nội bộ.
4. API/event contract giữa Commerce App, Catalog, Payment và Notification.
5. Transaction boundary của Order và cách xử lý Payment/Inventory nếu có.
6. Lộ trình chuyển Catalog data từ database monolith sang Catalog DB.
7. Cách dùng outbox/CDC, backfill, dual-read và reconciliation.
8. CI/build/deploy riêng cho từng deployable unit trong monorepo hoặc multi-repo.
9. Observability, SLO, security và capacity cần có.
10. Rollback khi Catalog Service đã nhận write nhưng Commerce App còn chạy phiên bản cũ.
11. Các fitness functions bảo vệ module boundary.
12. Metric và TCO để quyết định có tách tiếp Payment hay giữ trong ứng dụng.

Hãy đưa ra hai phương án: một phương án ưu tiên modular monolith và một phương án tách nhiều service hơn. So sánh lợi ích, chi phí và rủi ro của từng phương án, sau đó chọn theo các giả định được nêu rõ.

## Kết luận

Modular monolith và microservices có thể cùng tồn tại trong một kiến trúc có chủ đích. Modular monolith giữ những capability cần transaction, thay đổi và ownership gần nhau trong một ứng dụng nhưng vẫn có module boundary rõ. Microservices được dùng cho những capability có nhu cầu triển khai, mở rộng, cách ly hoặc ownership độc lập đã được chứng minh.

Một lộ trình kết hợp bền vững bắt đầu bằng domain/module boundaries, sau đó tách có chọn lọc qua contract, data ownership, backfill, outbox, cutover và reconciliation. Build, test, deploy, security và observability phải theo đúng ranh giới mới; những module còn trong ứng dụng vẫn cần được bảo vệ bằng architecture tests. Thành công được đo bằng khả năng thay đổi, SLO, chi phí và quyền tự chủ thực tế của các nhóm, không phải số lượng microservice được tạo ra.
