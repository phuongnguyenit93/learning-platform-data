# So sánh các chức năng được hỗ trợ theo từng client

## Mục tiêu bài học

Ứng dụng Spring chạy trong Kubernetes có thể tương tác với Kubernetes API bằng nhiều client hoặc thông qua một lớp tích hợp của Spring Cloud Kubernetes. Mỗi lựa chọn hỗ trợ một tập chức năng, mô hình lập trình và mức độ kiểm soát khác nhau. Chọn client theo tên thư viện hoặc theo ví dụ trên mạng dễ dẫn đến dependency thừa, quyền RBAC rộng và hành vi khác với điều ứng dụng cần.

Bài thuộc chương **Kubernetes client** của module **SPRING_CLOUD_KUBERNETES**. Module học tích hợp ứng dụng Spring với Kubernetes qua DiscoveryClient, ConfigMap, Secret, Spring Cloud LoadBalancer và Configuration Watcher; đồng thời thực hành phân quyền RBAC, cập nhật cấu hình, theo dõi sức khỏe Pod và lựa chọn tính năng Spring Cloud Kubernetes thực sự cần cho triển khai.

Sau bài này, bạn có thể:

- Phân biệt Kubernetes Java client, Fabric8 và lớp abstraction của Spring Cloud Kubernetes.
- So sánh khả năng đọc, ghi, watch, informer, discovery và cấu hình.
- Đánh giá dependency, API model, async, testability và yêu cầu RBAC.
- Chọn client theo nhu cầu thay vì bật mọi tính năng.
- Lập bảng capability và kiểm chứng lại theo release đang dùng.

## 1. “Client” có thể chỉ nhiều lớp khác nhau

Trong một hệ thống Spring Cloud Kubernetes, từ client thường được dùng cho ít nhất ba lớp:

    ứng dụng Spring
        → abstraction Spring Cloud Kubernetes
            → implementation client
                → Kubernetes API Server

Ba lớp này không có cùng trách nhiệm:

| Lớp | Trách nhiệm | Ví dụ câu hỏi |
| --- | --- | --- |
| Spring Cloud Kubernetes | Cung cấp integration ở cấp ứng dụng Spring | Có DiscoveryClient, config integration hoặc watcher không? |
| Kubernetes client library | Tạo request, model resource, watch và xử lý response | Có typed API, async, informer hoặc DSL không? |
| Kubernetes API Server | Xác thực, RBAC, lưu object và phát sự kiện | Danh tính có được get, list, watch resource không? |

Spring Cloud Kubernetes có thể đóng gói hoặc chọn implementation khác nhau tùy module và dòng phiên bản. Vì vậy, “dùng Spring Cloud Kubernetes” chưa đủ để xác định code đang dùng Fabric8 hay Kubernetes Java client. Dependency và module thực tế phải được kiểm tra theo release của dự án.

## 2. Ba lựa chọn cần phân biệt

### 2.1. Kubernetes Java client

Kubernetes Java client là client Java hướng tới Kubernetes API với các model và nhóm API tương ứng. Nó phù hợp khi ứng dụng cần kiểm soát gần với API Server:

- gọi API resource trực tiếp;
- dùng model Kubernetes typed;
- thực hiện CRUD;
- theo dõi thay đổi bằng watch;
- dùng async hoặc cơ chế callback tùy API;
- xử lý request, response và lỗi ở cấp thấp hơn.

Đổi lại, ứng dụng phải tự thiết kế nhiều phần: cache, retry, mapping domain, lifecycle, xử lý reconnect và giới hạn quyền.

### 2.2. Fabric8 Kubernetes client

Fabric8 cung cấp Java client với DSL và mô hình lập trình fluent. Nó thường được chọn khi đội Java muốn thao tác resource bằng API giàu tính biểu đạt, hỗ trợ watch, informer, CRUD và các utility liên quan.

Điểm mạnh thường được cân nhắc:

- DSL dễ đọc cho nhiều loại resource;
- typed resource model;
- watch và informer;
- hỗ trợ mock server hoặc test utility tùy module;
- cơ chế xử lý client ở mức thư viện.

Đội phát triển vẫn cần kiểm tra resource nào, verb nào và phiên bản API nào được client hỗ trợ. DSL tiện dụng không làm thay đổi yêu cầu RBAC.

### 2.3. Spring Cloud Kubernetes integration

Lớp Spring Cloud Kubernetes hướng đến nhu cầu ứng dụng Spring hơn là cung cấp toàn bộ API Kubernetes. Nó có thể nối Kubernetes với các abstraction quen thuộc:

- DiscoveryClient;
- ServiceInstance;
- Spring Cloud LoadBalancer;
- nguồn cấu hình từ ConfigMap hoặc Secret;
- Configuration Watcher;
- health hoặc thông tin liên quan tùy module.

Lớp này phù hợp khi ứng dụng cần hành vi Spring Cloud và muốn giảm code gọi API trực tiếp. Nó không phải lúc nào cũng phù hợp cho controller nghiệp vụ cần thao tác sâu trên nhiều resource Kubernetes.

## 3. Capability matrix khái quát

Bảng sau dùng để định hướng. Dấu “có thể” nghĩa là capability phụ thuộc module, phiên bản, implementation và cấu hình; không phải cam kết mọi release đều có cùng API.

| Capability | Kubernetes Java client | Fabric8 | Spring Cloud Kubernetes |
| --- | --- | --- | --- |
| CRUD resource cơ bản | Có | Có | Thường giới hạn theo integration |
| Typed Kubernetes model | Có | Có | Dùng gián tiếp qua integration |
| DSL fluent | Hạn chế hơn, tùy API | Điểm mạnh | Không phải mục tiêu chính |
| Watch resource | Có | Có | Dùng bên trong cho discovery, config hoặc watcher tùy tính năng |
| Informer và local cache | Có thể tự xây hoặc dùng hỗ trợ của client | Có utility tương ứng tùy phiên bản | Thường được quản lý nội bộ, không phải API nghiệp vụ chung |
| DiscoveryClient Spring Cloud | Không tự cung cấp | Không tự cung cấp | Là mục tiêu của module discovery |
| Spring Cloud LoadBalancer | Không tự cung cấp | Không tự cung cấp | Có thể tích hợp khi module và cấu hình phù hợp |
| ConfigMap, Secret thành property Spring | Tự viết | Tự viết hoặc dùng integration | Là mục tiêu của module config |
| Configuration Watcher | Tự thiết kế | Có primitive watch | Có integration watcher theo release |
| Controller framework | Tự xây | Có thể xây trên client | Không phải mục tiêu chính |
| API control | Cao | Cao | Trừu tượng hóa ở mức cao hơn |
| Code Spring cần viết | Nhiều hơn | Nhiều hơn | Ít hơn cho capability đã được hỗ trợ |

Không chọn client chỉ vì một dòng “Có”. Cần hỏi capability đó có đúng implementation, namespace, resource, verb, lifecycle và failure behavior mà ứng dụng cần không.

## 4. So sánh theo nhóm chức năng

### 4.1. Đọc resource

Cả Kubernetes Java client và Fabric8 đều có thể đọc resource Kubernetes nếu dependency và API group phù hợp. Các câu hỏi cần kiểm tra:

- Resource có typed model trong client không?
- API version có được hỗ trợ không?
- Có đọc theo tên, namespace, label selector không?
- Có xử lý resource không tồn tại và Forbidden không?
- Response có được map sang domain object riêng không?

Spring Cloud Kubernetes thường che phần request bằng integration. Ví dụ, application có thể nhận property từ ConfigMap mà không tự gọi ConfigMap API. Lợi ích là ít code; giới hạn là ứng dụng phụ thuộc cách integration chọn resource, key, namespace và precedence.

### 4.2. Tạo, sửa và xóa resource

Client cấp thấp thường có thể tạo, cập nhật, patch hoặc xóa resource. Đây là nhóm chức năng có rủi ro cao hơn đọc:

| Thao tác | Câu hỏi cần trả lời |
| --- | --- |
| Create | Nếu object đã tồn tại thì làm gì? |
| Update | Có cần resourceVersion hoặc optimistic concurrency không? |
| Patch | Patch type nào và field nào bị thay đổi? |
| Delete | Xóa object có kích hoạt controller tạo thay thế không? |
| Apply | Ai là field manager và có conflict không? |

Spring Cloud Kubernetes integration thường không nhằm biến ứng dụng nghiệp vụ thành Kubernetes controller. Nếu ứng dụng cần tạo Deployment, sửa Service hoặc quản lý CRD, nên đánh giá trực tiếp client cấp thấp hoặc một operator framework thay vì ép abstraction discovery/config làm nhiệm vụ đó.

### 4.3. Watch

Watch cho phép nhận thay đổi resource thay vì polling liên tục. Một watch có thể kết thúc vì:

- kết nối bị đóng;
- timeout;
- resource version quá cũ;
- lỗi xác thực hoặc phân quyền;
- API Server trả lỗi;
- client cần reconnect.

Kubernetes Java client và Fabric8 cung cấp primitive watch theo cách riêng. Ứng dụng tự dùng watch phải xử lý reconnect, duplicate event, delete event, ordering tương đối và trạng thái ban đầu.

Trong integration Spring Cloud Kubernetes, watch có thể được dùng nội bộ cho discovery hoặc configuration. Người dùng cần biết integration có tự quản lý reconnect và cache hay chỉ phát tín hiệu một lần. Không suy ra behavior từ việc dependency có class tên Watch.

### 4.4. Informer và cache

Informer thường kết hợp initial list, watch và local cache. Mô hình này giảm request lặp lại và giúp subscriber nhận event đã chuẩn hóa. Tuy nhiên, cache có thể stale trong một khoảng thời gian và cần resync.

| Cách tiếp cận | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Đọc trực tiếp mỗi request | Dữ liệu gần API tại thời điểm đọc | Tăng latency và tải API Server |
| Watch thuần | Nhận thay đổi nhanh | Phải tự xử lý reconnect và initial state |
| Informer/cache | Giảm tải, có event handler | Có độ trễ, cần quản lý lifecycle và memory |
| Integration Spring | Ít code ứng dụng | Behavior phụ thuộc module và cấu hình |

Nếu application dùng discovery cache, cần quyết định behavior khi cache rỗng hoặc stale. Không gửi request đến instance đã bị xóa chỉ vì cache chưa nhận delete event.

## 5. So sánh model và API lập trình

### 5.1. Typed model

Typed model giúp compiler kiểm tra nhiều field và làm code dễ đọc hơn. Nhưng Kubernetes API có nhiều version, resource mở rộng và field optional. Code vẫn phải xử lý:

- field vắng mặt;
- resource mới hơn client model;
- unknown field;
- conversion giữa API version;
- CRD không có model compile-time.

### 5.2. DSL fluent

DSL của Fabric8 có thể làm manifest thao tác bằng Java rõ hơn, nhưng DSL dài vẫn cần được review như code điều khiển hạ tầng. Không nên tạo resource bằng một chuỗi fluent call mà không có test cho name, namespace, selector và owner reference.

### 5.3. HTTP hoặc API cấp thấp

Kubernetes Java client cấp quyền kiểm soát trực tiếp hơn trên request và response. Phù hợp khi cần:

- API endpoint đặc biệt;
- field hoặc query parameter cụ thể;
- xử lý status code chính xác;
- tích hợp vào framework nội bộ.

Đổi lại, code có nhiều chi tiết transport và dễ gắn chặt vào API client.

### 5.4. Spring abstraction

Spring Cloud Kubernetes giúp code ứng dụng dùng ServiceInstance, property source hoặc Spring event thay vì model Kubernetes ở mọi nơi. Đây là lựa chọn tốt khi mục tiêu là hành vi ứng dụng:

    service ID
        → DiscoveryClient
        → ServiceInstance
        → LoadBalancer
        → HTTP client

Nếu mục tiêu là cập nhật một Deployment hoặc đọc owner reference của CRD, abstraction này có thể không đủ.

## 6. Discovery và client nào phù hợp?

Discovery trong Spring Cloud Kubernetes có hai câu hỏi tách biệt:

1. Client bên dưới có thể đọc dữ liệu Kubernetes nào?
2. Integration có chuyển dữ liệu đó thành DiscoveryClient và ServiceInstance không?

Kubernetes Java client hoặc Fabric8 tự chúng không biến thành Spring Cloud DiscoveryClient. Cần module adapter hoặc code tích hợp.

Khi đánh giá discovery, cần kiểm tra:

- service ID được lấy từ tên Service, label hay metadata nào;
- có hỗ trợ namespace hiện tại hay cross-namespace không;
- instance URI dùng cluster IP, endpoint hay port nào;
- có lọc Pod Ready không;
- metadata instance có được giữ không;
- cache refresh khi scale hoặc rollout ra sao;
- behavior khi danh sách rỗng.

Ví dụ logic:

    inventory
        → discovery provider
        → danh sách ServiceInstance
        → Spring Cloud LoadBalancer
        → request đến inventory

Tên class của client không trả lời được toàn bộ câu hỏi trên. Phải kiểm tra module discovery và cấu hình thực tế.

## 7. ConfigMap, Secret và cấu hình Spring

### 7.1. Đọc trực tiếp hay qua integration

Nếu dùng Kubernetes Java client hoặc Fabric8 trực tiếp, ứng dụng có thể:

- get ConfigMap;
- get Secret;
- đọc key trong data;
- tự map sang property;
- tự quyết định precedence;
- tự xử lý refresh.

Nếu dùng Spring Cloud Kubernetes config integration, ứng dụng có thể để Spring Environment nhận property từ nguồn Kubernetes theo cơ chế module hỗ trợ. Cách này giảm code nhưng cần hiểu:

- tên resource được suy ra hoặc cấu hình thế nào;
- namespace nào được đọc;
- key nào được map;
- property source có priority nào;
- lỗi API được xử lý ra sao;
- Secret có được log hoặc expose an toàn không.

### 7.2. Secret không phải ConfigMap đổi tên

Client có thể đọc cả ConfigMap và Secret, nhưng hai loại resource có mục đích bảo mật khác nhau. Capability “get resource” không làm Secret an toàn. Cần kiểm tra:

- ServiceAccount có quyền đọc Secret không;
- quyền có bị mở rộng sang mọi Secret không;
- log có in data không;
- endpoint chẩn đoán có lộ property không;
- quy trình rotation có tạo Pod mới hoặc refresh bean không.

### 7.3. Cập nhật cấu hình

Một client hỗ trợ watch ConfigMap chưa có nghĩa mọi bean Spring tự đổi giá trị. Cần phân biệt:

    resource changed
        → client nhận event
        → Environment hoặc source được cập nhật
        → bean nhận refresh
        → request mới dùng giá trị mới

Nếu một bước không có, ứng dụng vẫn giữ giá trị cũ. Spring Cloud Kubernetes có thể cung cấp integration cho một số bước, còn application phải thiết kế bean lifecycle.

## 8. RBAC theo capability

Mỗi client hoặc integration cần quyền theo cách nó truy vấn API. Bảng định hướng:

| Capability | Resource có thể cần | Verb có thể cần |
| --- | --- | --- |
| Đọc ConfigMap theo tên | configmaps | get |
| Đọc Secret theo tên | secrets | get |
| Discovery Service | services | get, list, watch tùy cách |
| Discovery endpoint | endpoints hoặc EndpointSlice | get, list, watch tùy cách |
| Watch cấu hình | configmaps, secrets | get, list, watch tùy cách |
| Controller | resource quản lý | get, list, watch, create, update, patch, delete tùy thiết kế |

Đây là capability matrix khái quát, không phải manifest RBAC hoàn chỉnh. Client dùng informer thường cần list và watch. Code chỉ get một resource theo tên có thể cần ít quyền hơn.

Quy trình cấp quyền:

1. Chọn capability ứng dụng thực sự cần.
2. Xác định API resource và namespace.
3. Quan sát request hoặc đối chiếu tài liệu release.
4. Cấp verb nhỏ nhất.
5. Kiểm tra bằng đúng ServiceAccount.
6. Xác nhận behavior khi bị từ chối.

Không cấp cluster-admin vì một client trả 403. Lỗi 403 là bằng chứng để sửa mapping quyền, không phải lý do mở toàn cluster.

## 9. Async, reactive và blocking

Client có thể cung cấp API blocking, async callback, CompletableFuture hoặc integration reactive tùy thư viện và module. Không nên chọn chỉ dựa trên tên “async”.

Các câu hỏi cần kiểm tra:

- request có chiếm thread ứng dụng trong lúc chờ không;
- callback chạy trên executor nào;
- watch event được xử lý trên thread nào;
- reconnect có chặn startup không;
- timeout có được đặt ở client, HTTP layer hay cả hai;
- khi API Server chậm, thread pool có bị đầy không.

Một ứng dụng Spring MVC dùng client blocking có thể phù hợp nếu request tới Kubernetes không nằm trên đường request nghiệp vụ nóng. Một watcher chạy nền cần lifecycle và executor riêng. Ứng dụng reactive cần kiểm tra client có tích hợp đúng mô hình backpressure hay không, thay vì bọc API blocking trong scheduler rồi gọi đó là reactive.

## 10. Retry, reconnect và lỗi API Server

Mọi client Kubernetes phải đối mặt với lỗi mạng, timeout, 401, 403, 404, 409 và resource version cũ. Mỗi lỗi có ý nghĩa khác nhau:

| Lỗi | Diễn giải có thể xảy ra | Hướng xử lý |
| --- | --- | --- |
| 401 | Credential hoặc token không hợp lệ | Kiểm tra danh tính và vòng đời token |
| 403 | Có danh tính nhưng thiếu quyền | Sửa RBAC theo resource và verb |
| 404 | Resource không tồn tại hoặc sai namespace | Kiểm tra tên, namespace và thời điểm tạo |
| 409 | Conflict hoặc resourceVersion thay đổi | Đọc lại, merge hoặc retry có điều kiện |
| Timeout | Mạng hoặc API Server chậm | Timeout hữu hạn, backoff và metric |
| Watch closed | Kết nối watch kết thúc | Reconnect và resync theo cơ chế client |

Retry không nên áp dụng giống nhau cho mọi lỗi. Retry Forbidden vô hạn chỉ tạo tải và che lỗi cấu hình. Retry một watch bị đóng thường cần bắt đầu lại từ resource state phù hợp.

## 11. Testing và mock

### 11.1. Unit test ở lớp mapping

Logic chuyển ConfigMap hoặc ServiceInstance sang domain object nên được test mà không cần cluster:

- key tồn tại;
- key thiếu;
- giá trị rỗng;
- namespace khác;
- instance không có port;
- metadata không đầy đủ;
- lỗi được map thành exception phù hợp.

### 11.2. Mock server hoặc fake client

Fabric8 và Kubernetes Java client có thể cung cấp cơ chế test khác nhau tùy phiên bản. Mock server hữu ích để kiểm tra HTTP request, status code và resource response. Fake client hoặc in-memory server hữu ích để test flow CRUD và watch ở mức thư viện.

Không giả định fake client mô phỏng đầy đủ:

- RBAC thật;
- NetworkPolicy;
- latency API Server;
- admission webhook;
- scheduler;
- controller reconciliation;
- eventual consistency của cluster.

### 11.3. Integration test

Test integration với cluster thật hoặc môi trường Kubernetes test cần kiểm tra:

- ServiceAccount;
- Role và RoleBinding;
- namespace;
- ConfigMap, Secret;
- Service selector;
- watch reconnect;
- rollout và readiness;
- cleanup resource.

Một unit test pass không chứng minh Pod production có quyền hoặc DNS đúng. Một integration test pass cũng cần ghi phiên bản cluster và client để tái lập.

## 12. Quan sát client trong production

Client nên tạo các tín hiệu giúp phân biệt lỗi API với lỗi ứng dụng:

- số request Kubernetes API theo resource và verb;
- latency request;
- mã lỗi 401, 403, 404, 409 và 5xx;
- số lần reconnect watch;
- độ tuổi dữ liệu cache;
- thời điểm discovery/config update gần nhất;
- số instance được nhìn thấy;
- thời gian refresh property;
- tên namespace và application, không ghi Secret value.

Log cần có:

    application=order-service
    capability=config
    resource=configmaps/order-service-config
    namespace=team-a
    result=success

Không log token, payload Secret hoặc toàn bộ response API. Với lỗi, ghi status code, reason và correlation ID đủ để truy vết.

## 13. Khi nào dùng client trực tiếp?

Client trực tiếp phù hợp hơn lớp Spring abstraction khi:

- cần quản lý resource Kubernetes ngoài phạm vi discovery/config;
- cần xây controller hoặc operator;
- cần thao tác CRD;
- cần patch field cụ thể;
- cần xử lý watch và cache theo domain riêng;
- ứng dụng là công cụ quản trị Kubernetes thay vì service nghiệp vụ.

Khi dùng client trực tiếp, application phải chịu trách nhiệm về:

- lifecycle client;
- authentication;
- RBAC;
- timeout;
- retry;
- reconnect;
- thread hoặc executor;
- cache;
- mapping lỗi;
- test và observability.

Một service nghiệp vụ chỉ cần gọi Service nội bộ không nên thêm client trực tiếp chỉ để phân giải tên. Kubernetes Service và DNS có thể đã đủ.

## 14. Khi nào dùng Spring Cloud Kubernetes?

Lớp Spring Cloud Kubernetes phù hợp hơn khi:

- ứng dụng đã dùng DiscoveryClient;
- cần ServiceInstance cho LoadBalancer;
- muốn đưa ConfigMap hoặc Secret vào Environment;
- muốn dùng cơ chế watcher đã được module hỗ trợ;
- muốn giảm code Kubernetes API trong business service;
- cần tích hợp với lifecycle và abstraction Spring.

Trước khi chọn, kiểm tra:

1. Module nào cung cấp capability?
2. Implementation client nào được kéo vào?
3. Resource và verb nào cần cho capability?
4. Namespace và tên resource được xác định thế nào?
5. Behavior khi API Server không truy cập được?
6. Cache, watch và refresh có được quản lý tự động không?
7. Có thể tắt capability không dùng để giảm quyền không?

## 15. Quy trình lập capability matrix cho dự án

Đừng bắt đầu bằng danh sách tất cả class trong dependency. Bắt đầu từ use case:

| Use case | Kết quả cần | Client hoặc integration cần | Quyền dự kiến | Cách kiểm chứng |
| --- | --- | --- | --- | --- |
| Gọi inventory bằng DNS | HTTP request thành công | Không nhất thiết cần Kubernetes client | Không cần API read nếu dùng DNS | Service, endpoint, smoke test |
| Lấy danh sách instance | ServiceInstance | Discovery integration | Service, endpoint hoặc EndpointSlice | Discovery count và request |
| Đọc feature flag | Property Spring | Config integration hoặc volume | ConfigMap get/list/watch tùy cách | Property version an toàn |
| Đọc token | Credential | Secret reference hoặc config integration | Secret get tối thiểu | Không log giá trị |
| Refresh feature flag | Bean dùng giá trị mới | Watcher và refresh lifecycle | watch cùng resource | Kiểm tra trên mọi replica |
| Tạo resource | Object mới | Client trực tiếp hoặc controller | create, get, update | Integration test và audit |

Từ bảng này, chọn implementation có ít capability thừa nhất. Capability thừa thường kéo theo dependency, RBAC và đường lỗi thừa.

## 16. Cách xác định client thực tế trong project

Khi được phép kiểm tra project theo quy trình của đội, cần xác định:

- dependency trực tiếp;
- dependency transitive;
- module Spring Cloud Kubernetes được chọn;
- implementation bean được tạo;
- configuration property bật client nào;
- image runtime có cùng dependency với môi trường build không.

Không suy ra client từ tên starter hoặc một bài hướng dẫn cũ. Một release có thể đổi module, tách starter hoặc thay implementation mặc định.

Trong bài này không chạy công cụ build. Khi dự án được kiểm tra ở bước phù hợp, kết quả cần được ghi thành capability record gồm:

    Spring Boot version
    Spring Cloud release
    Spring Cloud Kubernetes modules
    Kubernetes client implementation
    enabled capabilities
    required RBAC
    verified behavior

## 17. So sánh một số kịch bản

### Kịch bản A: gọi Service bằng DNS

order-service gọi inventory qua Service name. Không cần list Pod hoặc Endpoint từ trong ứng dụng. Chọn client trực tiếp sẽ tăng bề mặt vận hành mà chưa tạo giá trị.

Khả năng cần:

- DNS;
- Service;
- readiness;
- timeout HTTP;
- retry có kiểm soát.

### Kịch bản B: mã nguồn dùng DiscoveryClient

Ứng dụng cần service ID và danh sách ServiceInstance. Spring Cloud Kubernetes discovery integration phù hợp hơn tự viết adapter nếu module đã hỗ trợ yêu cầu.

Cần kiểm tra:

- discovery provider;
- namespace;
- resource đọc;
- cache;
- instance port;
- behavior khi danh sách rỗng.

### Kịch bản C: controller quản lý CRD

Ứng dụng cần watch, reconcile, update status và xử lý resourceVersion. Lớp Spring Cloud Kubernetes discovery/config không phải công cụ chính cho use case này. Client trực tiếp hoặc framework controller phù hợp hơn.

### Kịch bản D: cập nhật ConfigMap động

Nếu chỉ cần rollout, dùng volume hoặc env theo chính sách triển khai có thể đơn giản hơn watcher. Nếu cần refresh động, phải kiểm tra client watch, RBAC, event routing và lifecycle bean.

## 18. Những hiểu nhầm thường gặp

**“Kubernetes Java client và Fabric8 là hai tên cho cùng một API.”** Chúng là các thư viện khác nhau, có model, DSL, lifecycle và API programming khác nhau.

**“Có Fabric8 thì tự có DiscoveryClient.”** Client Kubernetes cung cấp thao tác API. DiscoveryClient là abstraction Spring cần integration hoặc adapter.

**“Spring Cloud Kubernetes hỗ trợ mọi resource Kubernetes.”** Integration thường tập trung vào discovery, config, load balancing, watcher và health theo module. CRUD hoặc controller sâu có thể nằm ngoài phạm vi.

**“Client hỗ trợ watch thì ứng dụng đã có reload.”** Watch chỉ là nhận thay đổi. Cần nối event đến source configuration và bean lifecycle.

**“Quyền get là đủ cho informer.”** Informer thường cần initial list và watch. Quyền thực tế phụ thuộc cách implementation hoạt động.

**“Retry 403 sẽ hết lỗi.”** 403 là lỗi quyền, cần sửa RBAC. Retry chỉ làm tăng request.

**“Fake client mô phỏng cluster thật.”** Fake client không thay thế kiểm tra RBAC, network, webhook, scheduler và eventual consistency.

**“Thêm tất cả module sẽ tránh phải chọn.”** Module thừa làm tăng dependency, quyền và behavior cần quan sát. Chọn theo capability matrix.

## 19. Checklist chọn client

### Nhu cầu

- [ ] Có thật sự cần gọi Kubernetes API từ ứng dụng không?
- [ ] Nhu cầu là DNS, discovery, config, watcher hay CRUD resource?
- [ ] Có cần CRD, controller hoặc reconcile không?

### Capability

- [ ] Client có resource và API version cần dùng không?
- [ ] Có typed model, watch, informer, async hoặc patch phù hợp không?
- [ ] Spring integration có cung cấp abstraction mong muốn không?
- [ ] Cache và reconnect có được quản lý theo cách chấp nhận được không?

### Bảo mật và vận hành

- [ ] ServiceAccount nào được dùng?
- [ ] Resource và verb RBAC là gì?
- [ ] Có thể giới hạn theo namespace hoặc resource name không?
- [ ] Log có tránh Secret và token không?
- [ ] Có metric cho API error, latency và reconnect không?

### Kiểm thử

- [ ] Có unit test cho mapping và lỗi không?
- [ ] Có mock hoặc integration test phù hợp không?
- [ ] Có kiểm tra behavior khi API chậm, 403, resource mất và watch reconnect không?
- [ ] Có ghi lại implementation và release đã kiểm chứng không?

## 20. Tự kiểm tra mức độ hiểu

**Câu 1: Kubernetes Java client hoặc Fabric8 có tự cung cấp DiscoveryClient của Spring Cloud không?**

Không. Chúng là client thao tác Kubernetes API. DiscoveryClient cần integration hoặc adapter ở cấp Spring Cloud.

**Câu 2: Khi nào lớp Spring Cloud Kubernetes phù hợp hơn client trực tiếp?**

Khi ứng dụng cần discovery, ServiceInstance, load balancing, ConfigMap hoặc Secret integration và muốn dùng abstraction Spring thay vì tự quản lý request API.

**Câu 3: Khi nào client trực tiếp phù hợp hơn?**

Khi cần CRUD hoặc patch resource sâu, thao tác CRD, xây controller, xử lý watch/cache theo domain hoặc quản trị tài nguyên Kubernetes.

**Câu 4: Vì sao cần kiểm tra implementation client thực tế theo release?**

Vì module, starter, default implementation và capability có thể thay đổi giữa phiên bản. Tên integration không đủ để kết luận dependency và behavior.

**Câu 5: Watch có bảo đảm bean Spring dùng giá trị mới không?**

Không. Watch chỉ nhận thay đổi. Cần source reload, event routing và bean lifecycle hỗ trợ refresh.

**Câu 6: Vì sao capability matrix giúp giảm rủi ro?**

Nó nối use case với resource, verb, dependency, behavior lỗi và cách kiểm chứng. Nhờ đó dự án tránh bật capability và quyền không cần thiết.

## Kết luận

Kubernetes Java client và Fabric8 cung cấp khả năng tương tác API ở mức thấp đến trung bình, trong khi Spring Cloud Kubernetes tập trung nối các capability Kubernetes vào abstraction của Spring. Không có client tốt nhất cho mọi use case. Lựa chọn đúng phụ thuộc vào việc ứng dụng cần DNS, discovery, config, watcher hay điều khiển resource trực tiếp.

Hãy lập capability matrix trước khi chọn dependency: ghi rõ resource, verb, namespace, cache, watch, retry, test và tín hiệu quan sát. Sau đó kiểm tra implementation thực tế của release đang dùng. Một client phù hợp là client đáp ứng đúng hợp đồng ứng dụng với quyền nhỏ nhất và behavior khi lỗi có thể giải thích được.
