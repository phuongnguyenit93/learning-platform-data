# Lộ trình học và mối liên hệ giữa các chủ đề Microservices

## Mục tiêu của bài học

Microservices là cách tổ chức một hệ thống thành các dịch vụ có ranh giới nghiệp vụ rõ ràng, triển khai và tiến hóa tương đối độc lập. Muốn hiểu kiến trúc này, người học cần kết nối nhiều chủ đề: phân rã miền nghiệp vụ, giao tiếp giữa dịch vụ, sở hữu dữ liệu, nhất quán phân tán, khả năng chịu lỗi, quan sát hệ thống, bảo mật, triển khai và vận hành.

Sau bài học, bạn cần có thể:

1. Sắp xếp các chủ đề Microservices theo quan hệ **tiền đề → kiến thức kế tiếp → năng lực áp dụng**, thay vì học rời rạc theo tên công nghệ.
2. Giải thích vì sao một quyết định về ranh giới dịch vụ ảnh hưởng đến API, dữ liệu, giao dịch, độ trễ và tổ chức nhóm phát triển.
3. Nhận diện các mối liên hệ xuyên suốt như **giao tiếp đồng bộ ↔ chịu lỗi**, **sở hữu dữ liệu ↔ nhất quán cuối cùng**, **triển khai độc lập ↔ tự động hóa và khả năng quan sát**.
4. Tự xây dựng một lộ trình thực hành theo mức độ phức tạp tăng dần, có sản phẩm kiểm chứng ở từng giai đoạn.
5. Biết khi nào nên cân nhắc một modular monolith thay vì tách Microservices quá sớm.

**Phạm vi:** Đây là bản đồ học tập và kết nối kiến thức, không phải hướng dẫn triển khai một framework cụ thể. REST, gRPC, message broker, Docker hay Kubernetes là những lựa chọn công nghệ có thể dùng để thực hành; chúng không tự động tạo ra một kiến trúc Microservices tốt.

## 1. Nguyên tắc chọn thứ tự học

Hãy đi từ **vấn đề cần giải quyết** đến **ranh giới nghiệp vụ**, sau đó mới đến **tương tác, dữ liệu và cách vận hành**. Một dịch vụ không trở nên đúng ranh giới chỉ vì có repository riêng, container riêng hay endpoint HTTP riêng.

Bốn câu hỏi định hướng:

- **Vì sao cần tách?** Hệ thống đang gặp khó khăn gì về quy mô nhóm, tốc độ phát hành, giới hạn mở rộng, độ tin cậy hoặc tính độc lập của miền nghiệp vụ?
- **Tách theo đâu?** Năng lực nghiệp vụ nào có dữ liệu, quy tắc và nhịp thay đổi đủ rõ để sở hữu một ranh giới?
- **Các phần phối hợp thế nào?** Hoạt động nào cần phản hồi ngay, hoạt động nào chấp nhận xử lý bất đồng bộ, trạng thái được đồng bộ ra sao?
- **Làm sao biết hệ thống còn hoạt động đúng?** Khi mạng chậm, một dịch vụ lỗi, sự kiện bị gửi lặp hoặc triển khai phiên bản mới, ta quan sát, kiểm thử và phục hồi bằng cách nào?

Một lộ trình tốt phải quay lại các câu hỏi này ở mỗi giai đoạn. Học công cụ trước khi hiểu quyết định kiến trúc thường tạo ra hệ thống phân tán nhưng vẫn phụ thuộc chặt chẽ như một khối.

## 2. Bản đồ phụ thuộc kiến thức

~~~mermaid
flowchart TD
    A["Bối cảnh, mục tiêu chất lượng và modular monolith"] --> B["Mô hình miền nghiệp vụ, bounded context, ranh giới dịch vụ"]
    B --> C["Hợp đồng API, đồng bộ / bất đồng bộ"]
    B --> D["Sở hữu dữ liệu và bất biến nghiệp vụ"]
    C --> E["Quy trình nhiều dịch vụ, saga, event và nhất quán"]
    D --> E
    C --> F["Timeout, retry, idempotency và chịu lỗi"]
    E --> F
    C --> G["Log, metric, trace và kiểm thử hợp đồng"]
    E --> G
    F --> G
    B --> H["Đóng gói, cấu hình, triển khai và phân phối"]
    F --> H
    G --> H
    H --> I["Bảo mật, vận hành, SLO, tiến hóa kiến trúc"]
    G --> I
    I -. "Phản hồi từ sản xuất" .-> B
~~~

Đọc sơ đồ theo hai chiều:

- **Chiều phụ thuộc:** Không thể thiết kế saga có ý nghĩa nếu chưa xác định dịch vụ nào sở hữu dữ liệu và quy tắc nghiệp vụ; không thể chọn chiến lược retry an toàn nếu chưa hiểu lệnh có thể chạy lặp hay không.
- **Chiều phản hồi:** Sau khi vận hành, trace, chỉ số độ trễ, lỗi giao tiếp và tần suất triển khai có thể cho thấy ranh giới dịch vụ ban đầu chưa phù hợp. Kiến trúc cần được điều chỉnh theo bằng chứng.

**Các trục xuyên suốt** bắt đầu từ sớm và tăng dần độ sâu: kiểm thử, bảo mật, quan sát, quản lý thay đổi hợp đồng, tự động hóa triển khai, quản lý chi phí và vận hành. Chúng không phải “môn học cuối cùng” chỉ được thêm sau khi hệ thống hoàn thiện.

## 3. Lộ trình học theo bảy chặng

### Chặng 1 — Hiểu bài toán kiến trúc và phương án thay thế

**Học gì**

- Kiến trúc hệ thống, yêu cầu chức năng và yêu cầu chất lượng: khả năng sẵn sàng, độ trễ, thông lượng, mức độc lập triển khai, khả năng bảo trì, chi phí.
- Sự khác nhau giữa monolith, **modular monolith** và microservices: ranh giới trong mã nguồn, ranh giới tiến trình, ranh giới dữ liệu và chi phí vận hành.
- Coupling/cohesion: hai thành phần càng cần thay đổi cùng nhau, việc tách thành hai dịch vụ càng có nguy cơ tạo ra giao tiếp và phối hợp phức tạp.
- Trade-off: tách dịch vụ mang lại quyền tự chủ nhưng tạo thêm mạng, quan sát, triển khai, dữ liệu phân tán và xử lý lỗi.

**Bài thực hành:** Chọn hệ thống bán hàng gồm Catalog, Order, Inventory, Payment. Viết một trang mô tả bối cảnh, số nhóm phát triển, tần suất phát hành, tình huống cần mở rộng độc lập và các yêu cầu chất lượng. Đề xuất giữ modular monolith hay tách dịch vụ, kèm lý do có thể kiểm chứng.

**Điều kiện chuyển chặng:** Bạn giải thích được *tại sao* cần hoặc chưa cần Microservices mà không viện dẫn việc “muốn dùng Kubernetes”.

**Liên hệ:** Quyết định kiến trúc ở chặng này là tiêu chí để đánh giá mọi ranh giới và công cụ ở các chặng sau.

### Chặng 2 — Xác định ranh giới dịch vụ từ miền nghiệp vụ

**Học gì**

- Domain-driven design (DDD) ở mức thiết kế chiến lược: domain, subdomain, **bounded context**, ubiquitous language và context map.
- Business capability: nhóm công việc nghiệp vụ có mục tiêu và quy tắc tương đối ổn định, khác với việc chia đơn thuần theo bảng cơ sở dữ liệu hoặc tầng controller/service/repository.
- Aggregate và bất biến nghiệp vụ: quy tắc nào phải đúng trong một giao dịch cục bộ, ai chịu trách nhiệm thực thi quy tắc đó.
- Service ownership: một nhóm sở hữu hợp đồng, dữ liệu, triển khai và chất lượng hoạt động của dịch vụ; tránh nhiều nhóm cùng thay đổi một miền mà không có ranh giới rõ.

**Bài thực hành:** Vẽ context map cho Catalog, Order, Inventory, Payment. Với mỗi context, ghi rõ trách nhiệm, dữ liệu chủ, quy tắc nghiệp vụ, các sự kiện hoặc API cần cung cấp và các phụ thuộc bắt buộc. Kiểm tra xem việc thay đổi chính sách thanh toán có buộc sửa mã tồn kho hay không.

**Điều kiện chuyển chặng:** Mỗi dịch vụ có nhiệm vụ rõ, có dữ liệu thuộc quyền quản lý và có thể mô tả các tình huống nghiệp vụ mà không cần viện đến cấu trúc bảng kỹ thuật.

**Liên hệ:** **Ranh giới nghiệp vụ quyết định hợp đồng giao tiếp và sở hữu dữ liệu.** Nếu ranh giới cắt ngang một bất biến cần giao dịch tức thời, các chặng sau sẽ phải “vá” bằng các cơ chế phân tán rất đắt.

### Chặng 3 — Giao tiếp giữa các dịch vụ và thiết kế hợp đồng

**Học gì**

- Giao tiếp **đồng bộ** (HTTP/REST, gRPC): phù hợp khi bên gọi cần kết quả tức thời; phải tính timeout, lỗi mạng, chain độ trễ và phụ thuộc thời gian chạy.
- Giao tiếp **bất đồng bộ** (message/command/event): phù hợp với tác vụ có thể xử lý sau, tích hợp qua sự kiện, giảm nhu cầu các dịch vụ cùng sẵn sàng tại một thời điểm; phát sinh trễ, lặp, sai thứ tự và vận hành broker.
- Phân biệt **command** (yêu cầu thực hiện một hành động) và **event** (sự kiện đã xảy ra). Event không được xem như lời hứa rằng mọi bên nhận đã xử lý xong.
- API contract, schema, tương thích tiến/lùi, versioning, xử lý lỗi, pagination và định danh tài nguyên.
- API Gateway/BFF và service discovery: điểm vào, định tuyến, cấu hình vị trí dịch vụ; không gom toàn bộ nghiệp vụ vào gateway.

**Bài thực hành:** Thiết kế một REST API tạo đơn hàng và một event khi đơn đã được tạo. Ghi rõ payload, ý nghĩa trạng thái, mã lỗi, cách tránh tạo trùng yêu cầu, timeout và consumer nhận event. Lập sơ đồ xem mỗi request đi qua bao nhiêu dịch vụ đồng bộ.

**Điều kiện chuyển chặng:** Bạn giải thích được vì sao một thao tác cần đồng bộ hoặc bất đồng bộ, bên nào chịu trách nhiệm khi giao tiếp thất bại và hợp đồng thay đổi thế nào để consumer cũ còn chạy.

**Liên hệ:** Cách giao tiếp tác động trực tiếp đến nhất quán dữ liệu ở chặng 4 và cơ chế chịu lỗi ở chặng 5. Việc chuyển từ REST sang broker **không tự giải quyết** vấn đề nhất quán hay trùng lặp.

### Chặng 4 — Sở hữu dữ liệu và tính nhất quán xuyên dịch vụ

**Học gì**

- Nguyên tắc **database per service** theo nghĩa sở hữu: một dịch vụ là chủ thể duy nhất thực hiện thay đổi theo quy tắc của dữ liệu đó; công nghệ lưu trữ có thể khác nhau. Không cho dịch vụ khác ghi thẳng bảng nội bộ của nó.
- Transaction cục bộ, bất biến trong một aggregate và giới hạn của giao dịch ACID khi yêu cầu trải qua nhiều dịch vụ.
- **Eventual consistency**: các bản sao hoặc view có thể lệch tạm thời; cần xác định độ trễ chấp nhận được, trạng thái trung gian và cách giải thích cho người dùng.
- **Saga**: một quy trình nhiều giao dịch cục bộ với các bước điều phối và hành động bù trừ khi thất bại; phân biệt choreography và orchestration.
- **Transactional outbox**: ghi thay đổi nghiệp vụ và thông điệp chờ phát trong cùng transaction cục bộ để giảm nguy cơ “đã commit nhưng mất event”; relay có thể phát lặp nên consumer phải xử lý idempotent.
- CQRS, event sourcing, read model, CDC: những kỹ thuật bổ sung có điều kiện; **không bắt buộc** cho mọi hệ thống Microservices.

**Bài thực hành:** Mô hình hóa quy trình đặt hàng: tạo Order ở trạng thái PENDING, giữ hàng ở Inventory, xác nhận thanh toán ở Payment rồi chuyển Order sang CONFIRMED. Vẽ cả nhánh thanh toán thất bại và thao tác hoàn trả giữ hàng. Xác định nơi phải chống xử lý lặp và cách xác minh trạng thái cuối.

**Điều kiện chuyển chặng:** Bạn nêu được hệ quả khi một bước saga thành công và bước tiếp theo thất bại, cách bù trừ phù hợp, và lý do không thể dùng transaction cơ sở dữ liệu cục bộ để bao trùm ba dịch vụ độc lập.

**Liên hệ:** **Tách dữ liệu → nhất quán phân tán → saga/outbox/idempotency.** Nếu nhiều dịch vụ liên tục cần join bảng của nhau hay transaction chéo, cần xem lại ranh giới ở chặng 2.

### Chặng 5 — Chịu lỗi và quan sát hệ thống phân tán

**Học gì**

- Lỗi phân tán: một dịch vụ có thể vẫn chạy nhưng phản hồi chậm, gói tin thất lạc hoặc client không biết request đã được xử lý chưa.
- Timeout, deadline và **retry có giới hạn**; exponential backoff + jitter để tránh tạo bão tải khi hệ thống đang lỗi. Chỉ retry khi hiểu tính an toàn của thao tác và idempotency.
- Circuit breaker, bulkhead, rate limiting, backpressure, queue buffering, load shedding, graceful degradation.
- Kiểm soát consumer: acknowledgment, retry queue, dead-letter queue, phát lại có kiểm soát và xử lý poison message.
- Observability với **logs có cấu trúc, metrics và distributed tracing**; sử dụng request ID, correlation ID, trace context; xác định SLI/SLO và alert có hành động.
- Phân biệt health check với độ tin cậy thực tế: tiến trình trả 200 OK chưa đủ chứng minh quy trình đặt hàng hoàn tất.

**Bài thực hành:** Giả lập Payment phản hồi chậm, Inventory mất kết nối và broker phát lại cùng một event. Đo độ trễ theo từng đoạn, vẽ trace cho một đơn hàng và chứng minh rằng retry không tạo hai lần thanh toán hoặc trừ hai lần tồn kho.

**Điều kiện chuyển chặng:** Bạn có thể trả lời “đơn hàng này mắc ở đâu, vì sao, trong bao lâu và khôi phục thế nào?” dựa trên tín hiệu quan sát thay vì chỉ xem một log riêng lẻ.

**Liên hệ:** **Giao tiếp đồng bộ → timeout/circuit breaker**; **giao tiếp bất đồng bộ → retry/idempotency/DLQ**; **nhiều dịch vụ → trace xuyên biên giới**. Cơ chế chịu lỗi phải phù hợp hợp đồng và ngữ nghĩa dữ liệu từ các chặng trước.

### Chặng 6 — Đóng gói, triển khai, cấu hình và bảo mật

**Học gì**

- Tính độc lập của artifact và vòng đời phát hành: build, test, container image, cấu hình theo môi trường, migration, rollback và tương thích phiên bản.
- CI/CD, triển khai từng dịch vụ, rolling/canary/blue-green tùy nhu cầu; khác biệt giữa triển khai độc lập thật sự và triển khai phải đồng bộ toàn hệ thống.
- Container, scheduling/orchestration, autoscaling, service discovery, ingress và quản lý secrets. Kubernetes có thể là một nền tảng triển khai, không phải tiền đề bắt buộc để hiểu Microservices.
- Authentication và authorization giữa client–gateway–service; service identity, nguyên tắc quyền tối thiểu, truyền danh tính đáng tin cậy, quản lý token/chứng thư và mã hóa kết nối phù hợp.
- Sở hữu vận hành: ai nhận cảnh báo, ai quyết định rollback, ai phục hồi event và ai chịu trách nhiệm với SLO của một luồng nghiệp vụ.

**Bài thực hành:** Đóng gói hai hoặc ba dịch vụ và chạy bằng một cấu hình nhiều tiến trình/container. Thử phát hành phiên bản mới của Order trong khi Inventory vẫn chạy phiên bản cũ; xác minh hợp đồng còn tương thích, secrets không nằm trong mã nguồn và log/trace vẫn nối được.

**Điều kiện chuyển chặng:** Có quy trình build–test–deploy lặp lại được, biết tìm cấu hình đang áp dụng, và có thể cập nhật một dịch vụ mà không phải đồng thời sửa tất cả các dịch vụ phụ thuộc.

**Liên hệ:** **Triển khai độc lập cần hợp đồng ổn định, quan sát tốt và rollback**; việc chỉ có nhiều container không chứng minh dịch vụ độc lập về nghiệp vụ.

### Chặng 7 — Kiểm thử, quản trị và tiến hóa kiến trúc

**Học gì**

- Test pyramid trong hệ thống phân tán: unit/component test, integration test, contract test giữa producer–consumer; số lượng vừa đủ các end-to-end test theo kịch bản quan trọng.
- Kiểm thử thất bại: timeout, duplicate event, xử lý sai thứ tự, consumer chậm, thay đổi schema, triển khai khác phiên bản và khôi phục sau sự cố.
- Architecture Decision Record (ADR), sơ đồ dependency, vòng đời API, ownership, tiêu chuẩn logging/tracing, và chính sách loại bỏ hợp đồng cũ.
- Quan sát thực tế về chu kỳ phát hành, thay đổi chéo nhóm, chi phí giao tiếp, độ trễ ở đường đi quan trọng và rủi ro vận hành; dùng dữ liệu đó để gộp, tách hoặc điều chỉnh ranh giới.
- Đánh giá kinh tế kỹ thuật: Microservices có thể giúp nhóm mở rộng độc lập nhưng làm tăng chi phí hạ tầng, phát triển, bảo mật và vận hành.

**Bài thực hành:** Viết ADR cho một quyết định “giữ modular monolith”, “tách Inventory” hoặc “chuyển cập nhật trạng thái sang event”. Đính kèm tiêu chí thành công, rủi ro, kết quả thử nghiệm và điều kiện đảo quyết định.

**Điều kiện hoàn thành:** Bạn có thể bảo vệ một quyết định kiến trúc bằng nhu cầu nghiệp vụ, mức phụ thuộc, số đo vận hành và phương án thay thế; không chỉ vẽ được sơ đồ nhiều hộp dịch vụ.

## 4. Mối liên hệ giữa các chủ đề trọng tâm

| Chủ đề đang học | Kiến thức cần có trước | Chủ đề kết nối trực tiếp | Câu hỏi kiểm tra mối liên hệ |
|---|---|---|---|
| Ranh giới dịch vụ | Miền nghiệp vụ, cohesion/coupling | API, dữ liệu, quyền sở hữu, đội nhóm | Nếu một quy tắc nghiệp vụ đổi, bao nhiêu dịch vụ phải sửa? |
| Bounded context | Ngôn ngữ nghiệp vụ, quy tắc cục bộ | Aggregate, hợp đồng tích hợp | Hai context có đang dùng cùng một từ với hai nghĩa khác nhau? |
| REST/gRPC đồng bộ | Consumer và hợp đồng | Timeout, chain độ trễ, circuit breaker | Nếu một dependency chậm, request của người dùng bị ảnh hưởng thế nào? |
| Event/message | Command/event, schema | Outbox, xử lý lặp, eventual consistency, trace | Sự kiện có thể đến hai lần hoặc đến muộn không, và consumer xử lý thế nào? |
| Data ownership | Ranh giới và bất biến | Saga, read model, CQRS | Bên nào là nguồn sự thật cho trạng thái và ai được quyền sửa? |
| Saga | Transaction cục bộ, nghiệp vụ bù trừ | Orchestration, outbox, idempotency | Nếu bước thứ ba thất bại, những bước nào có thể đảo ngược hợp lệ? |
| Resilience | Mô hình lỗi, kiểu giao tiếp | Retry budget, backpressure, SLO | Retry có làm trạng thái sai hoặc tăng tải lúc sự cố không? |
| Observability | Luồng nghiệp vụ qua nhiều service | Metrics, tracing, alerts, incident response | Làm sao truy vết một đơn hàng qua toàn bộ luồng xử lý? |
| Triển khai độc lập | Hợp đồng tương thích, tự động kiểm thử | CI/CD, rollout, rollback, security | Có thể phát hành một service mà consumer cũ vẫn hoạt động không? |
| Security | Ranh giới tin cậy, danh tính | Gateway, service identity, least privilege | Ai xác thực lời gọi và ai quyết định quyền trên tài nguyên? |
| Kiểm thử hợp đồng | API/event contract, versioning | CI/CD, tương thích schema | Một phiên bản producer mới có phá consumer cũ không? |

**Cách sử dụng bảng:** Khi đọc một chủ đề mới, trước tiên chọn một câu hỏi ở cột cuối. Nếu chưa trả lời được, quay lại kiến thức tiền đề tương ứng. Sau đó dựng một minh chứng nhỏ thay vì cố học hết danh sách công cụ.

## 5. Ví dụ xuyên suốt: đặt hàng, giữ hàng và thanh toán

Giả sử hệ thống có ba bounded context:

- **Order** sở hữu đơn hàng và các trạng thái PENDING, CONFIRMED, CANCELLED.
- **Inventory** sở hữu số lượng có thể bán và bản ghi giữ hàng.
- **Payment** sở hữu yêu cầu thanh toán, kết quả ủy quyền và bản ghi giao dịch.

Không dịch vụ nào ghi trực tiếp bảng nội bộ của dịch vụ khác. Một lựa chọn thiết kế là **saga có điều phối** bởi Order: tạo đơn, yêu cầu giữ hàng, yêu cầu thanh toán, xác nhận hoặc bù trừ. Ví dụ dưới đây biểu diễn ý tưởng bằng thông điệp; trong triển khai thật cần outbox, định danh thông điệp và cơ chế xử lý lặp.

~~~mermaid
sequenceDiagram
    participant U as Client
    participant O as Order
    participant B as Message Broker
    participant I as Inventory
    participant P as Payment
    U->>O: Tạo đơn + idempotency key
    O->>O: Lưu PENDING và outbox
    O-->>U: Mã đơn và trạng thái PENDING
    O->>B: ReserveInventory(orderId)
    B->>I: ReserveInventory
    I->>I: Ghi reservation một lần
    I->>B: InventoryReserved(orderId)
    B->>O: InventoryReserved
    O->>B: AuthorizePayment(orderId)
    B->>P: AuthorizePayment
    P->>P: Ghi kết quả theo khóa duy nhất
    P->>B: PaymentAuthorized(orderId)
    B->>O: PaymentAuthorized
    O->>O: Chuyển CONFIRMED
~~~

Điều gì xảy ra khi hệ thống không đi theo đường thành công?

1. **Inventory hết hàng:** Phát kết quả giữ hàng thất bại; Order chuyển CANCELLED, không yêu cầu thanh toán.
2. **Payment từ chối:** Order phát lệnh giải phóng phần hàng đã giữ; Inventory thực hiện bù trừ idempotent; Order chuyển CANCELLED khi quy tắc hủy được đáp ứng.
3. **Broker gửi trùng:** Inventory và Payment dùng orderId hoặc mã thao tác duy nhất để không giữ hàng/thu tiền hai lần; handler phải an toàn khi thực thi lại.
4. **Không nhận được phản hồi:** Order chưa thể biết bước bên kia đã xử lý hay chưa; theo dõi trạng thái và đối soát trước khi retry hoặc can thiệp, tránh giả định rằng timeout đồng nghĩa thất bại nghiệp vụ.
5. **Consumer tạm ngừng:** Thông điệp có thể nằm trong hàng đợi; cần chỉ số tuổi thông điệp, chính sách retry, DLQ và thao tác phát lại có kiểm soát.
6. **Người dùng truy vấn quá sớm:** API trả trạng thái PENDING, thay vì tuyên bố đơn đã xác nhận khi saga chưa hoàn thành.

Ví dụ này liên kết đồng thời **bounded context → data ownership → event contract → outbox → saga → idempotency → resilience → observability**. Nếu bỏ một mắt xích, hệ thống có thể chạy tốt trong demo nhưng khó giải thích trạng thái khi có sự cố.

**Nhiệm vụ nối các chặng:** Ghi lại một orderId, traceId, eventId và business state trong bảng theo dõi. Chạy kịch bản thành công, thanh toán thất bại và sự kiện lặp; đối chiếu trạng thái cuối của ba dịch vụ. Đây là bằng chứng học tập có giá trị hơn việc chỉ chứng minh các API trả về HTTP 200.

## 6. Các vòng học song song cần duy trì

Lộ trình theo chặng hữu ích để xác định kiến thức tiền đề, nhưng trong dự án thực tế phải lặp các hoạt động sau ngay từ lúc có tương tác giữa hai dịch vụ.

**Vòng kiểm thử:** Mỗi khi thêm hợp đồng, bổ sung test cho đầu vào, đầu ra, lỗi, tính tương thích và xử lý lặp. Khi thêm saga, kiểm thử cả bù trừ; khi thêm triển khai độc lập, kiểm thử chéo phiên bản.

**Vòng quan sát:** Từ lần gọi đầu tiên giữa hai dịch vụ, ghi correlation ID, thời lượng, mã lỗi và trạng thái nghiệp vụ. Khi số service tăng, bổ sung distributed trace, SLI và cảnh báo theo tác động người dùng.

**Vòng bảo mật:** Mỗi ranh giới dịch vụ là một ranh giới tin cậy phải xem xét: danh tính người gọi, quyền trên dữ liệu, dữ liệu nhạy cảm trong log/event, secrets, mã hóa giao tiếp và audit cần thiết.

**Vòng kiến trúc:** Sau mỗi tính năng, hỏi: “Tính năng này đòi hỏi bao nhiêu nhóm và service thay đổi cùng lúc?” Nếu thường xuyên phải sửa nhiều dịch vụ cho một thay đổi nhỏ, xem lại bounded context hoặc thiết kế hợp đồng.

**Vòng vận hành:** Từ lúc cần triển khai, xác định ownership và thao tác phục hồi: nơi xem log/trace, cách rollback, cách chạy lại message, giới hạn retry và người quyết định khi trạng thái lệch.

## 7. Kế hoạch thực hành mẫu trong sáu tuần

Thời lượng dưới đây chỉ để tham khảo cho người đã biết lập trình backend và cơ sở dữ liệu; có thể tăng hoặc giảm theo kiến thức sẵn có. Mỗi tuần nên tạo một bằng chứng chạy được hoặc một tài liệu quyết định rõ ràng.

| Tuần | Trọng tâm | Sản phẩm có thể kiểm chứng |
|---|---|---|
| 1 | Bối cảnh kiến trúc, modular monolith, yêu cầu chất lượng | Bản mô tả bài toán + ADR chọn phương án ban đầu |
| 2 | DDD, bounded context, service ownership | Context map + trách nhiệm và dữ liệu thuộc quyền từng context |
| 3 | API, event, contract và thay đổi phiên bản | Hai service giao tiếp; hợp đồng có test, mô tả đồng bộ/bất đồng bộ |
| 4 | Data ownership, saga, outbox, idempotency | Luồng đặt hàng có trạng thái trung gian, bù trừ và xử lý event trùng |
| 5 | Timeout, retry, circuit breaker, trace, metrics | Báo cáo chạy thử lỗi Payment/broker với trace và trạng thái cuối |
| 6 | CI/CD, bảo mật, rollout, kiểm thử hợp đồng, quyết định kiến trúc | Pipeline lặp lại được + thử nâng một service + ADR đánh giá lại ranh giới |

**Tiêu chí đánh giá mỗi tuần:** (1) Tôi giải thích được vì sao có quyết định này; (2) tôi chứng minh được hành vi bình thường và ít nhất một lỗi quan trọng; (3) tôi biết dữ liệu và hợp đồng nào thuộc quyền ai; (4) tôi biết đo điều gì để phát hiện quyết định sai.

### Ba hướng mở rộng sau lộ trình nền tảng

- **Backend developer:** Đi sâu transaction cục bộ, outbox, consumer idempotency, API evolution, contract test, saga và thiết kế read model.
- **Platform/DevOps engineer:** Đi sâu release strategy, scheduler/orchestrator, discovery, secrets, autoscaling, SLO, observability, incident response và chi phí.
- **Software architect/tech lead:** Đi sâu domain decomposition, tổ chức ownership, trade-off modular monolith ↔ microservices, giới hạn kết nối, ranh giới tin cậy và ADR dựa trên dữ liệu vận hành.

Các hướng này **bổ sung** cho nhau; mọi vai trò vẫn cần hiểu các tiền đề chung ở chặng 1–4.

## 8. Các dấu hiệu học lệch thứ tự hoặc áp dụng quá sớm

1. **Học Kubernetes trước khi xác định dịch vụ:** Có hạ tầng phức tạp nhưng các service vẫn chia theo bảng hoặc tầng kỹ thuật. Quay lại phân tích miền nghiệp vụ.
2. **Tách mọi CRUD thành service:** Tạo nhiều request mạng cho một luồng đơn giản, khó bảo đảm bất biến. Đánh giá lại cohesion và quyền sở hữu dữ liệu.
3. **Dùng chung database để “tiện join”:** Làm giảm độc lập schema và triển khai. Xác định nguồn sự thật, chuyển truy vấn liên miền sang API hoặc read model có chủ đích.
4. **Gọi đồng bộ dây chuyền quá dài:** Một request phụ thuộc nhiều dịch vụ cùng sẵn sàng, làm tăng tail latency. Đo call graph, giới hạn độ sâu và cân nhắc xử lý bất đồng bộ.
5. **Cho rằng broker bảo đảm chính xác một lần end-to-end:** Consumer vẫn có thể nhận lại message hoặc thực thi lại thao tác. Thiết kế idempotency và quy trình đối soát.
6. **Nhầm eventual consistency với “dữ liệu sẽ tự đúng”:** Phải có trạng thái trung gian, ngưỡng trễ, phát hiện lệch và cách sửa.
7. **Retry mọi lỗi vô hạn:** Gây nhân tải và có thể thực thi lại side effect. Phân loại lỗi, dùng deadline/retry budget và thao tác có idempotency.
8. **Chỉ xem từng log service:** Không dựng được hành trình của request/đơn hàng. Chuẩn hóa correlation, trace và trạng thái nghiệp vụ.
9. **Mỗi service triển khai riêng nhưng release phải đồng thời:** Hợp đồng không tương thích hoặc coupling quá cao. Thiết kế thay đổi tiến/lùi tương thích và test consumer–producer.
10. **Đo thành công bằng số service:** Cần đo tốc độ thay đổi, tỷ lệ sự cố, độ trễ, chi phí, mức phối hợp nhóm và độ ổn định nghiệp vụ.

## 9. Cách tự kiểm tra đã hiểu mối liên hệ

Dùng các câu hỏi này như một bài ôn tập. Mỗi câu nên trả lời bằng sơ đồ, lựa chọn có lý do và tình huống lỗi; không cần thuộc một bộ công nghệ cố định.

**Câu 1.** Vì sao đặt Order và Payment ở hai service nhưng dùng chung bảng có thể làm mất lợi ích triển khai độc lập?  
*Gợi ý:* schema coupling, quyền thay đổi dữ liệu và rủi ro release chéo nhóm.

**Câu 2.** Nếu từ Order đến Payment là lời gọi đồng bộ, những lỗi nào cần phân biệt trước khi retry?  
*Gợi ý:* timeout sau khi xử lý thành công, lỗi kết nối trước khi xử lý, idempotency key và deadline của người dùng.

**Câu 3.** Vì sao saga không tương đương một giao dịch ACID lớn?  
*Gợi ý:* các giao dịch cục bộ đã commit, trạng thái trung gian và bù trừ có ngữ nghĩa nghiệp vụ.

**Câu 4.** Outbox giải quyết vấn đề gì và vì sao vẫn cần consumer idempotent?  
*Gợi ý:* commit thay đổi với bản ghi chờ gửi, relay có thể gửi lặp và thông điệp có thể được xử lý lại.

**Câu 5.** Nếu một nhóm không thể cập nhật Inventory mà không sửa Order, bạn sẽ điều tra gì trước?  
*Gợi ý:* bounded context, hợp đồng API/event, việc dùng bảng chung, semantic coupling và test tương thích.

**Câu 6.** Làm sao biết nên tách thêm service hay quay lại modular monolith?  
*Gợi ý:* quyền tự chủ thực tế, mức phối hợp thay đổi, rủi ro giao tiếp phân tán và tổng chi phí vận hành.

**Câu 7.** Bạn cần xem những tín hiệu nào để điều tra một đơn hàng mắc ở PENDING?  
*Gợi ý:* trạng thái saga, event age, DLQ, trace, retry count, lần xử lý cuối và trạng thái Inventory/Payment.

## 10. Danh sách kiểm chứng cuối lộ trình

Bạn đã xây dựng được nền tảng Microservices khi có thể đưa ra **bằng chứng** cho các khả năng sau:

- [ ] Giải thích lợi ích, chi phí và điều kiện phù hợp của microservices so với modular monolith.
- [ ] Vẽ context map, phân biệt service boundary với project/container boundary.
- [ ] Nêu rõ chủ dữ liệu, bất biến và trách nhiệm của mỗi dịch vụ.
- [ ] Chọn giao tiếp đồng bộ/bất đồng bộ theo nhu cầu, mô tả contract và cách thay đổi tương thích.
- [ ] Thiết kế trạng thái trung gian, saga/bù trừ, outbox và xử lý trùng khi quy trình đi qua nhiều dịch vụ.
- [ ] Phân tích failure path, timeout, retry, circuit breaker/backpressure cho một luồng cụ thể.
- [ ] Truy dấu một giao dịch nghiệp vụ qua logs, metrics và traces, kèm tiêu chí phát hiện lỗi.
- [ ] Kiểm thử và triển khai một dịch vụ trong khi phiên bản phụ thuộc cũ vẫn hoạt động.
- [ ] Áp dụng ranh giới bảo mật, secrets, quyền tối thiểu và ownership vận hành.
- [ ] Viết ADR nêu quyết định, các phương án, trade-off và dữ liệu để đánh giá lại.

**Thông điệp cốt lõi:** Hãy học Microservices theo đường nối từ **nghiệp vụ → ranh giới → giao tiếp → dữ liệu → xử lý lỗi → quan sát → triển khai → vận hành**. Mỗi chủ đề chỉ thực sự được hiểu khi bạn giải thích được quyết định ở chủ đề đó tác động đến các chủ đề còn lại như thế nào.