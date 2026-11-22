# So sánh phương án đơn thể mô-đun với vi dịch vụ cho cùng một yêu cầu

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân tích một yêu cầu nghiệp vụ duy nhất và xây dựng hai phương án kiến trúc: modular monolith và microservices.
2. Giữ nguyên phạm vi, quy tắc nghiệp vụ, tải, SLO, bảo mật và tiêu chí nghiệm thu khi so sánh hai phương án.
3. Phân biệt ranh giới module trong mã nguồn với ranh giới service ở runtime, dữ liệu và triển khai.
4. Thiết kế luồng xử lý, transaction, API/event contract và ownership cho từng phương án.
5. So sánh latency, failure modes, consistency, khả năng mở rộng, release autonomy và trải nghiệm phát triển.
6. Ước lượng TCO bao gồm migration, hạ tầng, nền tảng, observability, kiểm thử, bảo mật, on-call và phối hợp nhóm.
7. Dùng số liệu, giả định và sensitivity analysis để tránh kết luận dựa trên sở thích công nghệ.
8. Chọn phương án phù hợp với bối cảnh, chỉ rõ điều kiện khiến quyết định cần thay đổi trong tương lai.
9. Trình bày quyết định bằng sơ đồ, bảng trade-off, kế hoạch triển khai và tiêu chí kiểm chứng.

Bài tập đặt ra một yêu cầu nghiệp vụ và yêu cầu người học thiết kế **hai cách triển khai khác nhau nhưng giải quyết cùng một vấn đề**. Một phương án dùng modular monolith: một ứng dụng triển khai chung nhưng có module boundary rõ. Phương án còn lại dùng microservices: nhiều service có runtime, data ownership và pipeline riêng.

Không được so sánh hai phương án với phạm vi chức năng hoặc SLO khác nhau. Nếu một phương án bỏ bớt yêu cầu để có vẻ đơn giản hơn, kết quả không còn là phép so sánh công bằng.

## 1. Tình huống nghiệp vụ dùng chung

Một doanh nghiệp bán lẻ trực tuyến cần xây dựng chức năng **đặt hàng và xác nhận đơn**. Người mua có thể xem sản phẩm, thêm sản phẩm vào giỏ, đặt hàng, thanh toán và nhận thông báo kết quả.

Phạm vi yêu cầu:
- Khách hàng đã xác thực có thể xem sản phẩm đang kinh doanh và giá hiện hành.
- Khách hàng gửi một yêu cầu checkout có danh sách sản phẩm, số lượng, địa chỉ giao hàng và idempotency key.
- Hệ thống xác minh sản phẩm còn được bán, giá hợp lệ và tồn kho có thể giữ.
- Hệ thống tạo đơn với mã duy nhất và lưu snapshot tên sản phẩm, đơn giá, currency tại thời điểm đặt.
- Hệ thống yêu cầu nhà cung cấp thanh toán thực hiện authorization.
- Nếu thanh toán được chấp nhận, đơn chuyển sang trạng thái CONFIRMED và tồn kho được giữ theo quy tắc nghiệp vụ.
- Nếu thanh toán thất bại, đơn không được xác nhận; reservation phải được giải phóng hoặc hết hạn theo chính sách.
- Khách hàng có thể xem trạng thái đơn.
- Notification gửi email hoặc push sau khi trạng thái phù hợp được ghi nhận.
- Request trùng do retry không được tạo hai đơn hoặc charge hai lần.
- Hệ thống phải ghi nhận audit/event cần thiết để đối soát.

Giả định ban đầu để làm bài:
- Peak checkout: 80 request/giây trong 15 phút.
- Traffic đọc sản phẩm: 1.000 request/giây ở peak.
- 5.000 người dùng có thể hoạt động đồng thời.
- SLO checkout: 99,9% request hợp lệ được xử lý đúng; p95 phản hồi nhận đơn dưới 500 ms, chưa tính thời gian hoàn tất thanh toán bất đồng bộ nếu provider xử lý lâu.
- SLO product read: p95 dưới 200 ms.
- Payment provider có quota 100 authorization/giây và có thể trả kết quả chậm hoặc timeout.
- Hệ thống cần triển khai trong một region, có khả năng phục hồi khi một node hỏng.
- Đơn hàng và payment record cần lưu theo chính sách nghiệp vụ; dữ liệu hồ sơ khách hàng có retention riêng.
- Nhóm phát triển ban đầu có 6 kỹ sư backend, 2 kỹ sư frontend, 1 QA và 1 SRE dùng chung.
- Sản phẩm dự kiến tăng trưởng, nhưng domain và quy trình nghiệp vụ vẫn có thể thay đổi trong năm đầu.

Các con số là giả định minh họa. Khi áp dụng vào dự án thật, phải thay bằng forecast, benchmark, quota, chính sách dữ liệu và SLO đã được owner xác nhận.

### Tiêu chí nghiệm thu chung

Hai phương án phải đáp ứng cùng các điều kiện:
1. Không tạo đơn trùng khi client retry cùng idempotency key.
2. Không charge hai lần cho cùng một payment intent.
3. Snapshot đơn hàng không thay đổi khi Catalog cập nhật tên/giá sau đó.
4. Không xác nhận đơn nếu payment authorization thất bại.
5. Không giữ tồn kho vô thời hạn khi workflow bị lỗi.
6. Trạng thái đơn có thể được truy vấn và giải thích.
7. Event/notification có thể được retry mà không tạo side effect sai.
8. Có audit trail và reconciliation cho các trạng thái không rõ.
9. Đạt SLO và security requirements.
10. Có thể build, test, deploy, monitor và khôi phục theo quy trình đã thiết kế.

## 2. Phương án A: Modular Monolith

Modular monolith dùng một ứng dụng Spring Boot có module boundary rõ. Các module chạy trong cùng process và có thể dùng chung một database transaction cho những phần nghiệp vụ phù hợp.

~~~text
                    Web / Mobile
                         |
                         v
                    API Gateway
                         |
                         v
              Commerce Spring Boot App
  +------------------------------------------------+
  |                                                |
  |  Catalog Module                                |
  |  - Product query                               |
  |  - Price read                                  |
  |                                                |
  |  Cart / Checkout Module                        |
  |  - Validate checkout                           |
  |  - Idempotency                                 |
  |                                                |
  |  Order Module                                  |
  |  - Order aggregate                             |
  |  - Order state                                 |
  |                                                |
  |  Inventory Module                              |
  |  - Reservation                                 |
  |  - Release/expiry                              |
  |                                                |
  |  Payment Module                                |
  |  - Provider adapter                            |
  |  - Payment intent                              |
  |                                                |
  |  Notification Module                           |
  |  - Outbox consumer / delivery                  |
  +------------------------+-----------------------+
                           |
                           v
                    Commerce Database
                           |
                           v
                     Outbox / Queue
                           |
                           v
                  External Email / Push
~~~

Một số module có thể được chạy dưới dạng worker process riêng từ cùng codebase nếu cần tách tải nền, nhưng trong phương án cơ sở vẫn giữ một deployable application cho phần giao dịch chính. Payment provider và email/push vẫn là hệ thống ngoài, không phải module nội bộ.

### Ranh giới module

- Catalog sở hữu Product và quy tắc sản phẩm.
- Checkout điều phối use case tạo đơn nhưng không tự sở hữu mọi entity.
- Order sở hữu Order aggregate, trạng thái và snapshot giao dịch.
- Inventory sở hữu reservation và số lượng có thể giữ.
- Payment sở hữu payment intent, provider reference và kết quả authorization.
- Notification sở hữu lịch gửi, trạng thái delivery và retry.

Dù dùng chung một database, module không được tùy ý đọc/ghi bảng của nhau. Mỗi module công bố interface hoặc application service được phép gọi; persistence implementation và entity nội bộ không được dùng làm contract.

### Luồng checkout trong modular monolith

1. Controller nhận request, xác thực user và kiểm tra idempotency key.
2. Checkout use case gọi Catalog interface để lấy snapshot sản phẩm/giá.
3. Inventory module kiểm tra và tạo reservation.
4. Order module tạo order ở trạng thái PENDING_PAYMENT.
5. Payment module tạo payment intent và gọi provider qua adapter với timeout/idempotency.
6. Khi provider xác nhận thành công, Order chuyển CONFIRMED; reservation được giữ theo trạng thái đã định nghĩa.
7. Transactional outbox ghi event OrderConfirmed cùng transaction cập nhật trạng thái.
8. Notification worker đọc event và gửi email/push.
9. Nếu payment thất bại, Order chuyển PAYMENT_FAILED và Inventory release reservation.
10. Nếu provider timeout không rõ kết quả, payment intent ở trạng thái PENDING/UNKNOWN; hệ thống query/reconcile provider thay vì tạo authorization mới mù quáng.

Một điểm cần quyết định: không nên giữ database transaction mở trong lúc chờ một HTTP call chậm tới provider. Có thể chia workflow thành trạng thái bền vững và tiếp tục bất đồng bộ. Modular monolith không buộc mọi thao tác phải nằm trong một transaction dài.

### Cấu trúc package minh họa

~~~text
commerce-app/
  src/main/java/com/example/commerce/
    CommerceApplication.java
    catalog/
      api/
      application/
      domain/
      infrastructure/
    checkout/
      api/
      application/
    order/
      api/
      application/
      domain/
      infrastructure/
    inventory/
      api/
      application/
      domain/
      infrastructure/
    payment/
      api/
      application/
      domain/
      infrastructure/
    notification/
      api/
      application/
      infrastructure/
    platform/
      security/
      observability/
      messaging/
~~~

Có thể dùng Spring Modulith, ArchUnit hoặc dependency rules tự xây để kiểm tra module boundaries. Package structure một mình không bảo đảm module isolation; phải có test ngăn import internal package hoặc truy cập persistence trái phép.

## 3. Phương án B: Microservices

Microservices tách các capability thành runtime unit độc lập. Mỗi service sở hữu data store hoặc schema được quản lý theo ownership, API/event contract và pipeline riêng.

~~~text
                         Web / Mobile
                              |
                              v
                         API Gateway
                              |
              +---------------+----------------+
              |               |                |
              v               v                v
        Catalog Service   Checkout API     Order Service
              |               |                |
          Catalog DB          |             Order DB
                              |
                 +------------+-----------+
                 |            |           |
                 v            v           v
          Inventory Svc   Payment Svc  Customer Svc
              |              |             |
          Inventory DB   Payment DB    Customer DB
                             |           /
                             |          /
                   +----------+---------+
                              |
                         Event Broker
                              |
                    +---------+----------+
                    |                    |
                    v                    v
              Notification Svc     Data Platform
                    |
               Email / Push
~~~

Trong phương án này, Checkout API có thể là một service điều phối riêng hoặc một module của Order Service tùy domain boundary. Bài tập yêu cầu nêu rõ lựa chọn, không tạo service chỉ để có thêm một ô trong sơ đồ.

### Ownership và contract

- Catalog Service sở hữu product catalog, giá công bố và query API.
- Checkout/Order Service sở hữu yêu cầu checkout, order lifecycle và snapshot.
- Inventory Service sở hữu reservation và tồn kho.
- Payment Service sở hữu payment intent, provider integration và reconciliation.
- Notification Service sở hữu delivery status và retry.
- Event Broker vận chuyển integration events; nó không thay thế owner dữ liệu.

Giao tiếp đồng bộ phù hợp với những bước cần câu trả lời ngay, nhưng phải có timeout, bounded concurrency, retry có giới hạn và error contract. Event phù hợp cho việc cập nhật trạng thái hoặc tác vụ có thể xử lý sau.

### Luồng checkout trong microservices

1. API Gateway xác thực request và chuyển đến Checkout/Order API.
2. Order Service kiểm tra idempotency và lưu checkout intent ở trạng thái RECEIVED.
3. Order Service lấy giá/snapshot qua Catalog API hoặc dữ liệu đã được cache theo freshness policy.
4. Order Service gửi ReserveInventory command tới Inventory Service.
5. Inventory Service tạo reservation idempotent và trả kết quả hoặc phát ReservationCreated.
6. Order Service tạo order PENDING_PAYMENT và payment intent.
7. Payment Service gọi provider bằng idempotency key ổn định.
8. PaymentAuthorized/PaymentFailed event được phát qua outbox.
9. Order Service cập nhật trạng thái; khi payment thành công, đơn CONFIRMED.
10. Inventory giữ reservation hoặc commit deduction theo business policy.
11. OrderConfirmed event kích hoạt Notification Service.
12. Các service retry và reconciliation những bước chưa rõ kết quả.

Luồng này là một distributed workflow. Không có một ACID transaction tự động bao trùm Order DB, Inventory DB, Payment DB và provider ngoài. Cần saga hoặc state machine, outbox/inbox, idempotency và xử lý compensation.

### Sơ đồ trạng thái đơn giản

~~~text
RECEIVED
   |
   v
VALIDATING
   |
   v
RESERVATION_PENDING
   |
   v
PAYMENT_PENDING
   |                |               timeout/unknown
   v               v
CONFIRMED        PAYMENT_UNKNOWN
   |               |
   v               +--> reconcile provider
FULFILLMENT        |
                   +--> CONFIRMED / PAYMENT_FAILED
~~~

Nếu payment thất bại, workflow chuyển sang PAYMENT_FAILED và phát lệnh release reservation. Nếu reservation đã hết hạn, consumer phải xử lý kết quả release một cách idempotent. Các trạng thái chính xác phải dựa trên domain, không chỉ dựa vào lỗi HTTP.

## 4. Giữ nguyên yêu cầu khi so sánh

Một phép so sánh công bằng dùng cùng một bảng traceability:

| Yêu cầu | Modular monolith | Microservices |
| --- | --- | --- |
| Xác thực khách hàng | Security module / gateway | Gateway + identity/customer contract |
| Xem sản phẩm | Catalog module | Catalog Service |
| Tạo đơn idempotent | Order DB unique key | Order Service DB unique key |
| Giữ tồn kho | Inventory module transaction/workflow | Inventory API/command + reservation |
| Thanh toán | Payment adapter + payment state | Payment Service + provider adapter |
| Snapshot giá/tên | Order snapshot | Order snapshot nhận qua contract |
| Trạng thái đơn | Order module query | Order API/read model |
| Notification | Outbox + worker/module | Event broker + Notification Service |
| Retry/reconciliation | Job/worker trong app hoặc process | Consumer/worker theo service |
| Audit | Audit table/outbox | Event/audit ownership xuyên service |
| SLO | App-level + module metrics | Journey SLO + per-service SLO |
| Security | App identity/roles + external provider | Service identity, scopes, network policy |
| Backup/restore | DB/app recovery | Nhiều store và event recovery |

Không được giả định microservices có thể bỏ idempotency hoặc modular monolith có thể bỏ observability. Hai phương án đều cần bảo vệ cùng business invariant.

## 5. So sánh ranh giới transaction và consistency

### Modular monolith

Lợi thế:
- Có thể cập nhật Order và OrderLine trong một database transaction.
- Có thể giữ reservation record và order state trong cùng DB nếu cùng ownership.
- Query nội bộ không cần network.
- Có thể dùng foreign key và constraint trong phạm vi DB.
- Dễ đối soát dữ liệu liên quan khi tất cả thuộc cùng application/database.

Chi phí/rủi ro:
- Một database/schema có thể trở thành điểm contention.
- Module boundary có thể bị phá nếu team truy cập bảng của nhau.
- Transaction dài có thể giữ lock và làm tăng latency.
- Một lỗi process hoặc thread pool có thể ảnh hưởng nhiều module.
- Scale database và application có thể khó tối ưu riêng.

### Microservices

Lợi thế:
- Mỗi service có thể giữ invariant cục bộ trong DB của mình.
- Data owner và quyền truy cập rõ.
- Service có thể tối ưu storage và scaling riêng.
- Một số lỗi có thể được cô lập ở runtime boundary.

Chi phí/rủi ro:
- Không có transaction nguyên tử xuyên nhiều DB mặc định.
- Eventual consistency và trạng thái trung gian phải được chấp nhận/thiết kế.
- Retry, duplicate, out-of-order và timeout là bình thường.
- Reconciliation và saga làm tăng code/operations.
- Shared dependency như broker, gateway hoặc cloud database vẫn có thể tạo blast radius chung.

**Không so sánh “transaction đơn giản” với “eventual consistency” như hai lựa chọn miễn phí.** Phải xác định business invariant nào cần strong consistency và invariant nào cho phép xử lý bất đồng bộ.

## 6. So sánh latency và network hops

Trong modular monolith, lời gọi giữa module thường là method/interface call trong cùng process. Trong microservices, các boundary có thể thêm network hop, serialization, connection management và timeout.

Ví dụ một checkout đồng bộ:
- Gateway → Checkout/Order.
- Order → Catalog.
- Order → Inventory.
- Order → Payment.

Nếu mỗi hop thêm 10–30 ms, tổng latency có thể tăng đáng kể, đặc biệt khi các lời gọi nối tiếp. Nếu gọi song song, latency có thể giảm nhưng failure handling và concurrency phức tạp hơn.

| Yếu tố | Modular monolith | Microservices |
| --- | --- | --- |
| Module call | In-process | Network/API nếu khác service |
| Serialization | Có thể không cần | Thường có |
| Timeout | Chủ yếu DB/provider | Mỗi remote dependency |
| Partial failure | Ít boundary nội bộ hơn | Phải xử lý ở từng hop |
| Trace | Có thể trace trong process | Cần distributed tracing |
| Retry | Thường cho DB/job/provider | Phải tránh retry amplification |
| Latency budget | Ít hop nội bộ | Chia ngân sách theo service/dependency |

Không giả định microservices luôn chậm. Cache, scaling riêng, tối ưu query và giảm tải shared process có thể cải thiện latency. Cần benchmark với workload mix thực tế và cùng SLO.

## 7. So sánh khả năng mở rộng và capacity

Với giả định 1.000 product reads/s và 80 checkout/s, Catalog có tỷ lệ đọc cao hơn đáng kể so với giao dịch checkout.

### Modular monolith

Nếu tất cả module chạy cùng một deployment:
- Scale app replicas có thể nhân bản cả Order, Payment adapter và Notification code dù chỉ Catalog cần thêm CPU.
- Có thể tách read worker/cache hoặc dùng process profile khác từ cùng codebase.
- Database chung có thể chịu tải đọc lớn; cần index, read replica/cache và connection management.
- Cần đo xem scale toàn app có làm tăng connection pool và memory baseline.

### Microservices

- Catalog có thể scale từ 3 lên 15 replica.
- Order có thể giữ 4 replica.
- Payment adapter có thể scale theo concurrency nhưng phải tôn trọng quota provider.
- Notification worker scale theo queue lag.
- Inventory scale theo reservation throughput và DB capacity.

Tuy nhiên, tăng replica không tự tăng capacity nếu DB, broker hoặc provider là bottleneck. HPA/KEDA cần metric phù hợp và max replicas gắn với downstream capacity.

### Chi phí process baseline minh họa

Giả sử modular monolith chạy 5 replica, mỗi process có baseline 700 MiB:

~~~text
5 × 700 MiB = 3.500 MiB
~~~

Nếu microservices có 5 service, mỗi service 3 replica, mỗi process baseline 300 MiB:

~~~text
5 × 3 × 300 MiB = 4.500 MiB
~~~

Đây là giả định minh họa. Thực tế phụ thuộc JVM, heap, sidecar, cache, runtime, số replica, workload và cấu hình. Không thể kết luận microservices luôn tốn RAM hơn chỉ từ ví dụ; cần đo baseline của artifact thực tế.

## 8. So sánh failure isolation

### Modular monolith

- Một module có thể ném exception và được xử lý trong boundary use case.
- Một memory leak hoặc CPU loop có thể làm ảnh hưởng toàn process.
- Thread pool hoặc connection pool chung có thể bị một module chiếm hết.
- Một deploy lỗi có thể tác động toàn ứng dụng.
- Có thể dùng bulkhead executor, bounded queue và process riêng cho batch để cô lập một phần.

### Microservices

- Catalog lỗi không nhất thiết làm Payment process dừng.
- Nhưng Order gọi Catalog đồng bộ có thể timeout và làm Checkout thất bại.
- Retry không giới hạn có thể lan lỗi sang downstream.
- Broker/database/gateway dùng chung vẫn là điểm lỗi chung.
- Version mismatch giữa producer và consumer có thể gây lỗi sau deploy.
- SRE phải quan sát và xử lý nhiều failure domain.

Cần đánh giá **blast radius của hành trình nghiệp vụ**, không chỉ đếm số process còn sống. Một microservice Payment vẫn healthy nhưng provider down thì Checkout không hoàn tất. Một modular monolith có thể tiếp tục hiển thị Catalog dù Payment provider lỗi nếu workflow được thiết kế phù hợp.

## 9. So sánh ownership và tốc độ phát hành

### Modular monolith

Một nhóm hoặc nhiều nhóm có thể sở hữu module riêng nhưng cùng deploy một artifact. Khi release chung gây chờ đợi, module autonomy ở code không chuyển thành deploy autonomy.

Có thể giảm coupling bằng:
- Module API rõ.
- Build/test theo module.
- Architecture tests.
- Code ownership và review rules.
- Feature flags.
- Backward-compatible schema changes.

Nhưng nếu production artifact chung, một thay đổi vẫn đi qua cùng release pipeline và có thể chịu regression scope rộng.

### Microservices

Mỗi team có thể:
- Build artifact riêng.
- Chọn thời điểm release.
- Rollback/forward-fix riêng.
- Scale riêng.
- Có SLO và on-call riêng.

Đổi lại, team phải quản lý contract với consumer. Một breaking change có thể buộc nhiều nhóm phối hợp và làm mất lợi ích autonomy.

| Chỉ số | Cách so sánh |
| --- | --- |
| Lead time | Từ merge đến production theo cùng định nghĩa |
| Deployment frequency | Theo deployable unit và outcome |
| Coordinated release ratio | Tỷ lệ thay đổi phải chờ service khác |
| Consumer migration time | Thời gian để các consumer nâng cấp |
| Change failure rate | Deploy gây lỗi/rollback theo quy tắc thống nhất |
| MTTR | Thời gian khôi phục khi thay đổi lỗi |
| On-call effort | Giờ xử lý vận hành theo team/service |
| Contract incidents | Lỗi do mismatch producer/consumer |

Không lấy số deployment cao hơn làm bằng chứng tự động rằng microservices tốt hơn. Cần kết hợp lỗi, SLO và giá trị sản phẩm.

## 10. So sánh testing strategy

### Modular monolith

- Unit test domain/application từng module.
- Spring slice/component test.
- Architecture test kiểm tra module boundary.
- Integration test với DB và broker.
- E2E test trong một application process cho use case quan trọng.
- Test transaction và migration tương đối trực tiếp.

### Microservices

- Unit/component test từng service.
- Consumer-driven contract tests.
- Provider verification.
- Schema compatibility test.
- Integration test với DB/broker riêng.
- E2E test xuyên service.
- Failure injection: timeout, duplicate event, out-of-order, provider unavailable.
- Replay/DLQ test và reconciliation test.

| Rủi ro | Modular monolith | Microservices |
| --- | --- | --- |
| Module import sai | Architecture test | API/contract + dependency policy |
| Schema DB sai | Migration integration test | Migration per owner + compatibility |
| API mismatch | Module API/component test | Contract/provider verification |
| Event decode lỗi | Integration test | Schema registry + consumer test |
| Network timeout | External adapter test | Timeout/failure injection từng hop |
| Duplicate side effect | Idempotency test | Idempotency + outbox/inbox |
| Rollback version | App/schema compatibility | Producer-consumer compatibility matrix |

Microservices không thể chỉ có unit tests; modular monolith cũng không nên chỉ dựa vào một E2E test lớn. Chọn test theo boundary và failure mode.

## 11. So sánh observability và incident response

Cả hai phương án cần logs, metrics, traces, dashboards và alert. Khác biệt nằm ở phạm vi correlation và ownership.

Modular monolith:
- Trace có thể hiển thị module/use case trong một process.
- Metrics theo module cần naming/tag convention.
- Một process và một artifact giúp xác định version đơn giản.
- Incident có thể tập trung vào một runtime, nhưng lỗi module có thể ảnh hưởng toàn app.

Microservices:
- Trace phải đi qua gateway, Order, Catalog, Inventory, Payment và broker.
- Cần correlation ID, trace context và event causation ID.
- Dashboard theo service và journey.
- Mỗi service cần owner/on-call.
- Incident có thể cần nhiều team điều tra.
- Log/trace volume và retention cost có thể tăng.

Đừng ghi toàn bộ payload nhạy cảm để tiện debug. Cần structured logs, error code, correlation ID và data minimization. Observability là chi phí sở hữu của cả hai phương án, đặc biệt trong hệ phân tán.

## 12. So sánh security và data governance

Modular monolith:
- Có thể dùng một application identity và authorization layer.
- Module vẫn cần kiểm soát quyền truy cập dữ liệu và business action.
- Một lỗ hổng trong process có thể có phạm vi lớn.
- Secret/config tập trung dễ quản lý hơn nhưng cần phân quyền nội bộ.

Microservices:
- Mỗi service cần service identity, authentication và authorization.
- Tenant/user context phải truyền an toàn.
- Network policy và secret/certificate lifecycle phức tạp hơn.
- Data classification và retention phải theo từng store.
- API/event payload có thể tạo thêm bản sao dữ liệu nhạy cảm.
- Audit và access review trải trên nhiều owner.

Tách service có thể cải thiện security isolation nếu service identity và quyền được thiết kế đúng. Nếu mọi service dùng chung admin credential và có thể đọc mọi database, lợi ích isolation chỉ tồn tại trên sơ đồ.

## 13. So sánh chi phí phát triển và vận hành

Các khoản chi phí phải tính cho cả hai:
- Phân tích domain và thiết kế module/service boundary.
- Build/test/CI/CD.
- Runtime CPU/RAM/storage/network.
- Database, cache, broker và backup.
- Observability và alert.
- Security, patching, secrets và audit.
- QA, integration tests và test data.
- On-call, incident response và runbook.
- Migration, training và onboarding.
- Coordination, API/event governance và release support.

Microservices thường có thêm:
- Nhiều runtime baseline.
- Nhiều deployable artifact.
- Service discovery/gateway/network policy.
- Data consistency, outbox, saga, reconciliation.
- Distributed tracing và contract compatibility.
- Nhiều database/store hoặc logical owner.
- Nhiều on-call boundary.

Modular monolith thường có thêm áp lực:
- Release train chung.
- Regression scope rộng.
- Scale toàn ứng dụng khi workload không đồng đều.
- Ownership module có thể bị phá bởi shared code/database.
- Một process failure ảnh hưởng nhiều capability.

Không được coi chi phí modular monolith bằng 0 hoặc chi phí microservices luôn cao hơn một tỷ lệ cố định. Hãy dùng dữ liệu dự án và cùng phạm vi tính toán.

## 14. Ví dụ TCO ba năm với giả định minh họa

Giả sử so sánh hai phương án trong 36 tháng, đơn vị triệu đồng:

| Khoản mục | Modular monolith | Microservices |
| --- | ---: | ---: |
| Build/migration ban đầu | 1.500 | 3.200 |
| Runtime/database/network mỗi tháng | 180 | 260 |
| Platform/observability mỗi tháng | 35 | 85 |
| Maintenance/on-call allocation mỗi tháng | 220 | 290 |
| Testing/security/coordination mỗi tháng | 70 | 110 |

Tính chi phí vận hành định kỳ:

~~~text
Modular monthly = 180 + 35 + 220 + 70
                = 505 triệu VND

Microservices monthly = 260 + 85 + 290 + 110
                      = 745 triệu VND
~~~

TCO ba năm, chưa chiết khấu và chưa tính incident/benefits:

~~~text
TCO_modular = 1.500 + 36 × 505
            = 19.680 triệu VND

TCO_microservices = 3.200 + 36 × 745
                  = 30.020 triệu VND
~~~

Chênh lệch giả định là 10.340 triệu đồng trong ba năm. Đây không phải kết luận microservices không đáng dùng. Phương án microservices cần tạo thêm giá trị kinh doanh hoặc giảm rủi ro tương ứng, ví dụ:
- Catalog scale riêng giảm chi phí không phải nhân bản toàn bộ ứng dụng.
- Team phát hành độc lập giúp tính năng quan trọng ra sớm.
- Payment isolation cải thiện khả năng bảo vệ checkout khi provider gặp sự cố.
- Giảm blast radius hoặc đáp ứng yêu cầu bảo mật/availability riêng.

Các số chỉ là bài tập tính toán. Dự án thật cần tính chi phí nhân sự đầy đủ, chiết khấu, traffic growth, incident, chi phí cơ hội và độ bất định.

## 15. Tính lợi ích kinh tế của autonomy

Giả sử mỗi tháng có 30 thay đổi nhỏ. Trong modular monolith, 40% thay đổi bị chờ release chung trung bình 4 ngày. Nếu microservices giúp giảm thời gian chờ xuống 1 ngày, số ngày elapsed time được rút ngắn là:

~~~text
Affected changes = 30 × 40% = 12
Saved elapsed days = 12 × (4 - 1) = 36 change-days/month
~~~

36 change-days không phải 36 ngày công tiết kiệm. Để quy đổi thành tiền, cần biết thay đổi sớm hơn tạo giá trị gì:
- Giảm thời gian khách hàng chịu lỗi.
- Đưa tính năng ra trước một mốc business.
- Tăng conversion hoặc doanh thu có thể quy kết.
- Giảm chi phí phối hợp/handoff thực tế.
- Giảm incident do batch release lớn.

Nếu không có bằng chứng về business value, ghi đây là lợi ích thời gian/flow, không cộng tùy tiện vào doanh thu.

### Lợi ích giảm blast radius

Có thể dùng số service/khách hàng/giao dịch bị ảnh hưởng mỗi incident, thời gian phát hiện và khôi phục. Nhưng không giả định microservices luôn giảm blast radius: shared broker/database hoặc retry storm có thể làm sự cố lan rộng hơn.

## 16. Ma trận trade-off cho cùng yêu cầu

| Tiêu chí | Modular monolith | Microservices |
| --- | --- | --- |
| Tốc độ triển khai ban đầu | Thường nhanh hơn | Tốn setup platform/contract hơn |
| Build độc lập | Có thể theo module | Theo service |
| Deploy độc lập | Hạn chế nếu cùng artifact | Có thể cao |
| Transaction checkout | Dễ giữ trong DB boundary | Cần saga/state machine nếu phân tán |
| Consistency | Có thể strong trong DB | Có thể eventual giữa service |
| Latency nội bộ | Ít network hop | Có serialization/network |
| Scaling Catalog | Có thể scale toàn app hoặc tách worker | Scale Catalog riêng |
| Failure isolation | Process chung có blast radius rộng | Boundary riêng nhưng dependency vẫn lan lỗi |
| Contract governance | Module API nội bộ | API/event contract liên nhóm |
| Observability | Ít runtime unit hơn | Distributed trace và nhiều dashboard |
| Security | Identity tập trung hơn | Service identity và policy phân tán |
| On-call | Ít service owner boundary | Nhiều service/rotation hơn |
| Testing | Dễ test transaction cục bộ | Nhiều compatibility/failure tests |
| TCO ban đầu | Thường thấp hơn | Thường cao hơn |
| Autonomy dài hạn | Phụ thuộc module/release discipline | Có thể cao nếu contract tốt |

Từ bảng không thể chấm một phương án thắng tuyệt đối. Cần gắn trọng số theo ưu tiên thực tế của tổ chức.

## 17. Quy trình đưa ra quyết định

### Bước 1: Chốt yêu cầu và ràng buộc

Ghi:
- Use case và business invariant.
- Traffic mix, peak và growth.
- SLO, RTO/RPO và failure scenarios.
- Security, privacy và data retention.
- Nhóm, ownership và lịch release.
- Hệ thống ngoài, quota và dependency.

### Bước 2: Thiết kế hai phương án

Với mỗi phương án, vẽ:
- Component/module/service boundaries.
- Data ownership.
- Request/event flow.
- Transaction/workflow.
- Build/deploy units.
- Failure domains.
- Observability và security.

Giữ cùng phạm vi chức năng và cùng SLO.

### Bước 3: Kiểm tra các use case khó

Không chỉ vẽ happy path. Kiểm tra:
- Payment timeout nhưng provider đã charge.
- Inventory reservation thành công nhưng event bị mất.
- Client gửi retry.
- Catalog đổi giá sau khi order được tạo.
- Notification provider down.
- Database hoặc node hỏng.
- Một service deploy version mới trong khi consumer còn cũ.

### Bước 4: Ước lượng TCO và lợi ích

Tính migration, runtime, platform, labor, testing, security, data, on-call và coordination. Tính lợi ích từ release wait, scaling, failure isolation và business outcome có bằng chứng.

### Bước 5: Sensitivity analysis

Thay đổi các giả định:
- Số nhóm và tần suất release.
- Traffic Catalog so với checkout.
- Số transaction cross-domain.
- Cost per service runtime.
- Mức độ trưởng thành của platform.
- Số consumer và độ dài compatibility window.
- Growth và chi phí sự cố.

### Bước 6: Chọn phương án và ghi điều kiện xem xét lại

Quyết định cần nêu:
- Lý do chọn.
- Trade-off được chấp nhận.
- Rủi ro còn lại.
- Metric theo dõi.
- Ngưỡng khiến kiến trúc cần được xem lại.
- Lộ trình chuyển đổi nếu giả định thay đổi.

## 18. Scorecard hỗ trợ quyết định

Có thể chấm mỗi phương án từ 1 đến 5 theo trọng số. Ví dụ trọng số minh họa:

| Tiêu chí | Trọng số |
| --- | ---: |
| Đáp ứng yêu cầu nghiệp vụ và invariant | 20% |
| SLO, latency và reliability | 15% |
| Khả năng thay đổi/release autonomy | 15% |
| Scaling/capacity efficiency | 10% |
| Data ownership và consistency | 10% |
| Security và compliance | 10% |
| TCO ba năm | 15% |
| Năng lực team/platform | 5% |

Điểm tổng:

~~~text
Weighted score = SUM(score_i × weight_i)
~~~

Scorecard chỉ là công cụ thảo luận. Nếu modular monolith đạt điểm cao nhưng vi phạm một yêu cầu bắt buộc về security isolation, không thể dùng tổng điểm để bỏ qua ràng buộc đó. Hãy phân biệt:
- **Hard constraints:** phải đáp ứng.
- **Weighted preferences:** có thể trade-off.
- **Unknowns:** cần benchmark/pilot trước khi kết luận.

## 19. Ví dụ kết luận có điều kiện

Với giả định đã nêu, một modular monolith có thể là lựa chọn ban đầu hợp lý nếu:
- Team còn nhỏ và có thể phối hợp release.
- Domain Order/Inventory/Payment còn thay đổi thường xuyên.
- Transaction và consistency là ưu tiên cao.
- Chưa có platform/on-call maturity cho nhiều service.
- Có thể tối ưu Catalog bằng cache, read replica hoặc worker riêng trước.

Microservices có thể hợp lý nếu:
- Catalog thực sự cần scaling riêng lớn và có data ownership rõ.
- Payment cần security/availability boundary và team owner riêng.
- Notification workload bất đồng bộ có nhu cầu vận hành riêng.
- Các nhóm cần release độc lập thường xuyên và có số liệu chứng minh release coupling.
- Tổ chức có contract testing, observability, CI/CD và SRE đủ năng lực.

Một phương án thứ ba là **hybrid**: giữ Order/Checkout/Inventory trong modular monolith ban đầu, tách Catalog hoặc Notification khi có bằng chứng, sau đó đánh giá Payment theo nhu cầu compliance/provider isolation. Hybrid không phải yêu cầu bắt buộc của bài, nhưng là một phương án nên cân nhắc nếu hai lựa chọn cực đoan đều có trade-off lớn.

## 20. Cách viết Architecture Decision Record (ADR)

Một ADR tốt nên ghi:

~~~text
Title:
  Choose modular monolith or microservices for checkout

Context:
  Business scope, traffic, SLO, team, constraints.

Options:
  A. Modular monolith
  B. Microservices
  C. Hybrid (if considered)

Decision:
  Selected option and reasons.

Consequences:
  Benefits, costs, risks and accepted trade-offs.

Evidence:
  Benchmarks, forecasts, cost model, dependency map.

Operational plan:
  Build, deploy, monitoring, on-call, backup, rollback.

Revisit triggers:
  Measurable conditions that would change the decision.
~~~

Ví dụ trigger xem xét tách Catalog:
- Tỷ lệ thời gian release Catalog bị chặn bởi release chung vượt ngưỡng đã thống nhất trong nhiều chu kỳ.
- Chi phí scale toàn ứng dụng cao hơn đáng kể so với phương án Catalog riêng.
- Catalog có team owner và data boundary đủ rõ.
- Contract với consumer ổn định, có tests và migration plan.
- Platform có khả năng vận hành service mới.

Không dùng một con số ngưỡng tùy ý cho mọi dự án. Chốt ngưỡng sau khi đo baseline và phân tích chi phí.

## 21. Kế hoạch kiểm chứng bằng prototype/pilot

Khi chưa đủ dữ liệu, xây một prototype nhỏ cho cùng use case hoặc một capability có ranh giới rõ:
1. Tạo một vertical slice trong modular monolith.
2. Đo build/test time, latency, resource baseline và effort.
3. Tạo một service boundary tương đương cho capability đó.
4. Chạy cùng workload và cùng data shape.
5. Đo network latency, failure handling, scaling và observability overhead.
6. Ước lượng effort contract, deployment và on-call.
7. So sánh kết quả, ghi sai lệch giữa prototype và production.
8. Quyết định có tiếp tục tách hay giữ module.

Prototype phải đủ đại diện. Một benchmark chỉ gọi endpoint rỗng không chứng minh khả năng xử lý checkout có payment, DB và retry.

### Success criteria

- Cả hai phương án đáp ứng cùng business tests.
- Đạt SLO dưới cùng workload.
- Có chi phí runtime và platform được ghi.
- Có failure test cho payment timeout/duplicate.
- Có đo build/test/deploy effort.
- Có mô hình on-call và incident ownership.
- Có TCO theo cùng horizon.
- Có kết luận và điều kiện xem xét lại.

## 22. Các lỗi lập luận thường gặp

**So sánh hai phạm vi khác nhau:** microservices được đánh giá với cache/scale tốt hơn nhưng monolith không có cache hoặc index tương đương. Phải giữ cùng yêu cầu và điều kiện.

**Cho rằng modular monolith đồng nghĩa code rối:** module boundary có thể được kiểm tra bằng architecture tests và có ownership rõ.

**Cho rằng microservices luôn deploy độc lập:** breaking contract, shared DB hoặc coordinated migration có thể buộc release đồng bộ.

**Bỏ qua distributed transaction:** tách Order/Inventory/Payment nhưng không thiết kế reservation, saga, idempotency và reconciliation.

**Chỉ tính cloud bill:** quên labor, on-call, testing, security, incident và coordination.

**Coi mọi service cần database vật lý riêng:** logical ownership có thể được triển khai trên cluster dùng chung nếu đáp ứng isolation và capacity.

**Dùng số lượng service làm thước đo thành công:** số deployable unit tăng nhưng lead time/SLO/TCO có thể xấu đi.

**Lấy deployment frequency làm lợi ích duy nhất:** deploy nhiều hơn không có ý nghĩa nếu lỗi tăng hoặc business outcome không đổi.

**Bỏ qua platform maturity:** microservices cần pipeline, observability, security, catalog, runbook và on-call.

**Không tính migration/dual-run:** chi phí chuyển đổi và giai đoạn vận hành song song có thể chiếm phần lớn business case.

**Không ghi điều kiện đổi quyết định:** kiến trúc trở thành niềm tin cố định thay vì giả thuyết có thể kiểm chứng.

## 23. Checklist hoàn thành bài so sánh

- [ ] Cả hai phương án giải quyết cùng yêu cầu nghiệp vụ.
- [ ] Cùng traffic, SLO, security và retention assumptions.
- [ ] Có sơ đồ component/module/service và luồng request/event.
- [ ] Có data ownership và transaction boundary.
- [ ] Có xử lý idempotency, timeout, retry và duplicate.
- [ ] Có mô tả consistency và trạng thái trung gian.
- [ ] Có so sánh latency/network hops và failure modes.
- [ ] Có scaling/capacity analysis với dependency bottleneck.
- [ ] Có build, test, deployment và release coordination.
- [ ] Có observability, on-call, backup và recovery.
- [ ] Có TCO với cùng horizon và giả định.
- [ ] Có lợi ích autonomy/scale/failure isolation được đo.
- [ ] Có sensitivity analysis.
- [ ] Có hard constraints và weighted preferences.
- [ ] Có lựa chọn cuối cùng, trade-off và risk register.
- [ ] Có trigger xem xét lại và kế hoạch pilot nếu còn uncertainty.

## 24. Bài tập thực hành

Một nhóm cần xây dựng cùng chức năng checkout cho nền tảng bán lẻ với các yêu cầu ở phần 1. Hãy nộp một báo cáo thiết kế gồm:

1. Sơ đồ modular monolith với các module và public interfaces.
2. Sơ đồ microservices với service boundaries, databases và broker.
3. Sequence diagram cho checkout success, payment failure và payment timeout/unknown.
4. Data model và transaction boundaries của mỗi phương án.
5. API/event contract tối thiểu giữa các boundary.
6. Cách bảo vệ idempotency và tránh double charge.
7. Cách giữ reservation và giải phóng khi workflow thất bại.
8. Test strategy: unit, architecture, contract, integration, E2E và failure tests.
9. Capacity estimate cho 1.000 product reads/s và 80 checkout/s.
10. TCO ba năm với giả định được công bố.
11. Bảng trade-off về autonomy, consistency, latency, scaling, security và operations.
12. Quyết định cuối cùng, lý do, rủi ro chấp nhận và điều kiện xem xét lại.

Báo cáo phải trả lời rõ:
- Hai phương án khác nhau ở đâu nhưng vẫn đáp ứng cùng yêu cầu?
- Phần nào của microservices tạo giá trị thật?
- Phần nào chỉ chuyển chi phí từ code sang vận hành/phối hợp?
- Nếu chọn modular monolith hôm nay, dữ liệu và module boundary nào giúp tách sau này?
- Nếu chọn microservices hôm nay, team/platform nào chịu trách nhiệm và làm sao bảo đảm release compatibility?

### Tiêu chí tự đánh giá bài tập

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| Yêu cầu tương đương | Traceability từ từng requirement tới thiết kế |
| Boundary rõ | Owner, interface và data ownership |
| Business correctness | Sequence/state diagrams và invariant |
| Distributed failure | Timeout, retry, duplicate, compensation |
| SLO/capacity | Workload, benchmark assumptions và bottleneck |
| TCO | Cost model, horizon và sensitivity |
| Team autonomy | Release dependency và ownership model |
| Quyết định | ADR có trade-off và revisit trigger |

## Kết luận

So sánh modular monolith với microservices chỉ có ý nghĩa khi hai phương án giải quyết cùng một yêu cầu, cùng SLO và cùng ràng buộc. Modular monolith thường đơn giản hơn về transaction, network và vận hành; microservices có thể tạo lợi ích về deployment autonomy, scaling và failure/data ownership khi các boundary thực sự độc lập. Cả hai đều cần modularity, test, observability, security và trách nhiệm production rõ ràng.

Quyết định tốt không dựa trên xu hướng hay số lượng service. Nó dựa trên business invariant, tải, ranh giới domain, năng lực nhóm, TCO và bằng chứng thử nghiệm. Khi chưa đủ dữ liệu, hãy chọn phương án ít rủi ro hơn, giữ module boundary sạch và ghi rõ điều kiện khiến kiến trúc cần tiến hóa.
