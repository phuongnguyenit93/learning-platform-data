# Lập bảng tính năng tương thích giữa broker, đặc tả và nền tảng

Một service broker có thể chạy ổn định trong môi trường phát triển nhưng vẫn gặp lỗi khi nâng phiên bản Spring, thay đổi Open Service Broker API (OSB API) hoặc kết nối với một phiên bản platform khác. Nguyên nhân thường không nằm ở một thành phần riêng lẻ mà ở quan hệ giữa nhiều phiên bản: broker implementation, thư viện Spring Cloud Open Service Broker, Java runtime, OSB API contract, Cloud Foundry hoặc Kubernetes adapter, provider API và cấu hình triển khai.

Ma trận tương thích giúp nhóm phát triển biết tổ hợp nào đã được kiểm thử, tính năng nào được hỗ trợ, giới hạn nào đang tồn tại và bằng chứng nào xác nhận kết luận đó. Thay vì chỉ ghi “broker hỗ trợ Cloud Foundry” hoặc “tương thích OSB 2.x”, ma trận cần chỉ rõ release broker nào, dải OSB API nào, platform version nào, capability nào và kết quả kiểm thử tương ứng.

Trong module `SPRING_CLOUD_SERVICE_BROKER`, broker cung cấp catalog, service plan, provision, update, deprovision, binding và các thao tác bất đồng bộ theo OSB API. Broker có thể được gọi từ Cloud Foundry hoặc thông qua một controller/adapter tương thích trên Kubernetes. Bài học này trình bày cách lập ma trận theo từng lớp, xác định mức hỗ trợ, kiểm thử tổ hợp phiên bản, quản lý thay đổi và công bố giới hạn tương thích.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao tương thích là quan hệ giữa nhiều phiên bản, không phải một nhãn duy nhất.
- Phân biệt phiên bản broker, OSB API, Spring framework, Java runtime và platform API.
- Lập ma trận tương thích theo release và theo tính năng.
- Phân biệt Supported, Partial, Unsupported, Unverified và Deprecated bằng tiêu chí rõ ràng.
- Đánh giá khác biệt giữa tích hợp Cloud Foundry và Kubernetes OSB adapter.
- Thiết kế kiểm thử contract, integration và end-to-end cho từng tổ hợp quan trọng.
- Lập kế hoạch nâng cấp broker, dependency, platform và database schema.
- Ghi nhận bằng chứng, giới hạn, deprecation và chính sách hỗ trợ.

## 1. Tương thích là quan hệ giữa nhiều thành phần

Một tổ hợp triển khai service broker có thể được mô tả bằng các chiều:

| Thành phần | Ví dụ thông tin cần ghi | Vì sao ảnh hưởng tương thích? |
|---|---|---|
| Broker release | Version ứng dụng, build ID, Git commit | Xác định code và hành vi thực tế đang chạy. |
| OSB API contract | Version header và revision đặc tả được hỗ trợ | Quy định request, response, status, capability và semantics. |
| Spring Cloud Open Service Broker | Artifact version/BOM | Quy định service interface, model, builder và framework integration. |
| Spring Boot / Spring Framework | Release train và dependency versions | Ảnh hưởng auto-configuration, web stack, validation và security. |
| Java runtime | JDK vendor và major version | Ảnh hưởng bytecode, TLS, runtime API và thư viện. |
| Platform | Cloud Foundry foundation/release hoặc Kubernetes adapter/controller | Quyết định cách gọi broker, polling, binding và phân phối credentials. |
| Provider adapter | API version, region hoặc operator version | Quyết định khả năng tạo, update, bind và thu hồi tài nguyên. |
| Database/schema | Schema version và migration level | Ảnh hưởng operation store, binding records và khả năng rollback. |
| Deployment environment | TLS, proxy, ingress, DNS, secrets, network policy | Có thể làm thay đổi hành vi dù code không đổi. |

Một broker release có thể tương thích với một OSB API version nhưng không tương thích với một Spring Boot/JDK combination khác. Tương tự, cùng một broker có thể hoạt động với Cloud Foundry nhưng chưa được xác minh với Kubernetes adapter vì cách adapter truyền context hoặc xử lý binding khác nhau.

### 1.1. Không gộp các loại phiên bản thành một số version

Các phiên bản sau có mục đích độc lập:

- **Broker version:** version sản phẩm do nhóm phát triển phát hành.
- **OSB API version:** version contract mà platform gửi qua header `X-Broker-API-Version`.
- **Spring Cloud Open Service Broker version:** version thư viện cung cấp model và service interfaces.
- **Spring Boot/Spring Framework version:** nền tảng ứng dụng mà broker được xây dựng trên đó.
- **Platform version:** version Cloud Foundry foundation hoặc controller/adapter kết nối tới broker.
- **Provider API version:** version API của database/cloud/Kubernetes operator mà adapter sử dụng.

Không suy ra OSB API version từ broker version. Ví dụ broker release 2.4 không có nghĩa nó tự động triển khai OSB API 2.4. Hai con số có thể dùng quy ước versioning khác nhau.

### 1.2. Tương thích cần có phạm vi

Một tuyên bố tương thích phải nói rõ:

1. Thành phần và version cụ thể.
2. Tính năng hoặc endpoint được xác nhận.
3. Điều kiện cấu hình cần thiết.
4. Giới hạn đã biết.
5. Môi trường và bằng chứng kiểm thử.
6. Ngày xác minh và người/nhóm chịu trách nhiệm.

Ví dụ, “Broker 1.8 hỗ trợ Cloud Foundry” là quá rộng. Một tuyên bố hữu ích hơn là “Broker 1.8 đã qua E2E với foundation thuộc release line X, OSB API version header Y, provision async và binding credentials; route service và context update chưa được xác minh”.

## 2. Phân biệt tương thích giao thức, hành vi và vận hành

Một tổ hợp có thể đúng schema nhưng vẫn sai hành vi hoặc không vận hành được trong môi trường thật.

| Lớp tương thích | Nội dung cần xác minh | Ví dụ lỗi |
|---|---|---|
| Protocol compatibility | URL, HTTP method, header, request/response schema, status code | Broker trả sai body cho `last_operation`. |
| Semantic compatibility | Ý nghĩa của idempotency, async, binding, update, deprovision | Platform retry provision nhưng broker tạo hai tài nguyên. |
| Capability compatibility | Catalog công bố capability đúng với endpoint thực tế | Catalog bật `bindings_retrievable` nhưng fetch binding không hoạt động. |
| Runtime compatibility | JDK, Spring Boot, Spring Cloud, TLS, serialization | Broker không khởi động sau nâng dependency hoặc lỗi handshake. |
| Platform compatibility | Platform gọi API, truyền context và phân phối credentials đúng | Ứng dụng không nhận binding sau restage. |
| Provider compatibility | Provider API/operator thực hiện đúng lifecycle | Broker báo provision thành công nhưng provider chưa sẵn sàng. |
| Operational compatibility | Upgrade, rollback, migration, monitoring và recovery | Nâng broker làm worker cũ không đọc được operation record. |
| Security compatibility | Authentication, authorization, TLS, secret handling | Platform đổi cơ chế xác thực khiến request bị từ chối. |

Kết luận “tương thích” chỉ nên được đưa ra khi những lớp bắt buộc cho phạm vi hỗ trợ đã được kiểm tra. Một contract test thành công không thay thế E2E test về phân phối credentials hoặc provider state.

## 3. Xác định ma trận phiên bản nền

Trước khi lập ma trận tính năng, nhóm cần có một bảng phiên bản nền. Bảng này ghi nhận các tổ hợp dependency và platform được phép đưa vào kiểm thử.

### 3.1. Ma trận thành phần

| Chiều | Giá trị cần quản lý | Nguồn xác minh |
|---|---|---|
| Broker | Release tag, build number, commit | Artifact metadata và release record. |
| OSB API | Version header được broker chấp nhận | Contract test và request log đã làm sạch. |
| Spring Cloud Open Service Broker | Artifact version và BOM | Dependency lock/report của build. |
| Spring Boot | Version chính xác | Dependency management và startup test. |
| Spring Framework | Version được resolve | Dependency tree. |
| Java | JDK vendor, major/minor/build khi cần | Runtime image và CI toolchain. |
| Cloud Foundry | Foundation release/API behavior | Environment metadata và E2E test. |
| Kubernetes integration | Adapter/controller version, Kubernetes version | Deployment manifest và integration test. |
| Provider | Provider API/engine/operator version | Sandbox metadata và provider test. |
| Database | Engine version và schema migration | Migration history và compatibility test. |

Không tự điền một version chỉ vì nó có vẻ phổ biến. Lấy giá trị từ artifact thực tế, platform environment và kết quả kiểm thử. Nếu chưa có bằng chứng, đánh dấu `Unverified`.

### 3.2. Ví dụ bảng phiên bản minh họa

Bảng dưới đây chỉ minh họa cách trình bày; các nhãn `Broker-A`, `Framework-B`, `CF-line-C` và `Adapter-D` không phải chứng nhận cho một release sản phẩm cụ thể. Khi dùng trong dự án, thay bằng version thật và link bằng chứng tương ứng.

| Profile | Broker | OSB API header | Spring stack | Java | Platform | Kết quả |
|---|---|---|---|---|---|---|
| Profile A | Broker-A | Dải version đã khai báo | Framework-B + Boot-C | JDK-LTS-1 | CF-line-C | Chờ E2E chứng nhận |
| Profile B | Broker-A | Dải version đã khai báo | Framework-B + Boot-C | JDK-LTS-1 | OSB Adapter-D trên Kubernetes-E | Chưa xác minh |
| Profile C | Broker-next | Dải version mới | Framework-next + Boot-next | JDK-LTS-2 | CF-line-C | Đang kiểm thử nâng cấp |
| Profile D | Broker-next | Dải version mới | Framework-next + Boot-next | JDK-LTS-2 | OSB Adapter-D trên Kubernetes-E | Chưa xác minh |

Không kết luận Profile B hoặc D tương thích chỉ vì cùng broker artifact đã chạy trên Cloud Foundry. Platform adapter và cách tích hợp Kubernetes cần được xác minh riêng.

## 4. Ma trận tương thích theo tính năng OSB API

Ma trận tính năng cho biết mỗi broker release và platform combination hỗ trợ endpoint/capability nào. Đây là phần quan trọng nhất khi platform dùng catalog để quyết định thao tác nào có thể gọi.

### 4.1. Các tính năng lifecycle chính

| Tính năng | Contract/endpoint cần kiểm tra | Broker implementation cần có | Bằng chứng E2E |
|---|---|---|---|
| Catalog | `GET /v2/catalog` | Service/plan IDs ổn định, metadata và capability đúng | Platform đọc và hiển thị đúng offering/plan. |
| Provision | `PUT /v2/service_instances/{instance_id}` | Validate, idempotency, provider create, state persistence | Instance tồn tại ở platform, broker và provider. |
| Async provision | `accepts_incomplete=true`, `202`, `last_operation` | Operation store, worker, retry/reconciliation | Platform poll tới terminal state đúng. |
| Fetch instance | `GET /v2/service_instances/{instance_id}` khi capability bật | Truy xuất dữ liệu instance theo contract | Response đúng instance và tenant. |
| Update | `PATCH /v2/service_instances/{instance_id}` | Validate plan/parameters, revision, provider update | Provider config và operation state khớp. |
| Deprovision | `DELETE /v2/service_instances/{instance_id}` | Provider delete, idempotency, cleanup | Tài nguyên thật bị thu hồi. |
| Bind | `PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id}` | Tạo credentials/quyền riêng cho consumer | App nhận credentials và kết nối thành công. |
| Fetch binding | `GET .../service_bindings/{binding_id}` khi capability bật | Truy xuất binding đúng và bảo mật | Platform lấy lại binding response đúng. |
| Unbind | `DELETE .../service_bindings/{binding_id}` | Revoke credentials/permission theo binding | Consumer không còn truy cập bằng secret cũ. |
| Async update/deprovision | `accepts_incomplete=true`, `last_operation` | Operation lifecycle và status mapping | Polling phản ánh đúng tiến trình và kết quả. |

### 4.2. Capability trong catalog

Catalog không chỉ là danh sách service. Các capability/field công bố cho platform phải khớp implementation:

| Field/capability | Ý nghĩa cần xác minh |
|---|---|
| `bindable` | Offering có hỗ trợ tạo binding hay không. |
| `requires` | Các capability binding cần từ platform, ví dụ route forwarding hoặc syslog drain nếu có. |
| `instances_retrievable` | Broker hỗ trợ fetch service instance. |
| `bindings_retrievable` | Broker hỗ trợ fetch service binding. |
| `plan_updateable` | Plan có thể được thay đổi qua update theo contract. |
| `allow_context_updates` | Broker cho phép xử lý thay đổi context theo semantics OSB. |
| `maintenance_info` | Broker công bố metadata maintenance khi cần. |
| `dashboard_client` | Có dashboard URL/metadata phù hợp khi offering hỗ trợ. |

Không bật capability chỉ vì framework có model tương ứng. Phải có handler, persistence, security và E2E test xác nhận. Nếu platform nhìn thấy capability nhưng endpoint thực tế chưa triển khai, người dùng có thể khởi tạo một workflow không thể hoàn tất.

### 4.3. Phân biệt capability không hỗ trợ và chưa xác minh

`Unsupported` nghĩa là release không cung cấp tính năng theo thiết kế hoặc contract đã công bố. `Unverified` nghĩa là chưa có đủ bằng chứng để kết luận. Không đánh dấu `Unsupported` chỉ vì nhóm chưa chạy test; cũng không đánh dấu `Supported` chỉ vì code có một handler.

## 5. Ma trận tương thích giữa broker và Cloud Foundry

Cloud Foundry Cloud Controller là consumer OSB API. Platform đăng ký broker, đọc catalog, gọi lifecycle endpoints và phân phối binding credentials cho ứng dụng.

Các điểm cần xác minh theo từng foundation release:

| Khu vực | Kiểm tra |
|---|---|
| Broker registration | URL, TLS trust, authentication credentials và network reachability. |
| Catalog | Service/plan ID, bindable, requires và các capability. |
| API version | Header `X-Broker-API-Version` mà foundation gửi và dải broker chấp nhận. |
| Provision | Sync/async behavior, `accepts_incomplete`, response và operation polling. |
| Update | Plan/parameters update, capability và lỗi không hỗ trợ. |
| Binding | `bind_resource`, app context, credentials response và binding ID. |
| Environment delivery | `VCAP_SERVICES`, restage/restart và schema credentials. |
| Unbind/deprovision | Thứ tự cleanup, retry, async và provider resource deletion. |
| Authentication | Basic/mTLS hoặc cơ chế platform cấu hình; credential rotation. |
| Operations | Timeout, polling interval, Retry-After, logs và audit. |

### 5.1. Kiểm thử Cloud Foundry bằng CLI

Trong môi trường test, quy trình có thể gồm:

    cf create-service-broker broker-e2e USER PASSWORD https://broker.example.test
    cf service-brokers
    cf marketplace
    cf create-service postgresql standard orders-db-e2e
    cf bind-service orders-api-e2e orders-db-e2e
    cf restage orders-api-e2e
    cf env orders-api-e2e

Các lệnh là ví dụ và cần thay credentials/offerings theo môi trường. `cf env` có thể hiển thị secret, vì vậy không lưu output nguyên bản vào CI artifact hoặc ticket. Test cần xác minh ứng dụng kết nối được backing service, không chỉ xác minh biến môi trường tồn tại.

### 5.2. Những khác biệt cần ghi nhận

Hai foundation có thể khác về cách cấu hình timeout, TLS, broker registration, quyền enable service access hoặc cách operator thực hiện restage. Không nên gắn mọi khác biệt vào một nhãn “Cloud Foundry supported”. Ghi foundation release và kết quả của từng kịch bản cụ thể.

## 6. Ma trận tương thích giữa broker và Kubernetes OSB adapter

Kubernetes API bản thân không tự động là một OSB API consumer. Để dùng broker theo OSB API, cần một controller, service catalog component hoặc adapter có trách nhiệm gọi broker và ánh xạ vòng đời OSB sang resource/workload Kubernetes.

Vì vậy, ma trận Kubernetes phải ghi rõ adapter/controller nào được kiểm thử, không chỉ ghi Kubernetes version.

| Khu vực | Kiểm tra |
|---|---|
| OSB client | Adapter có gọi đúng catalog/provision/update/bind/unbind/deprovision endpoints không? |
| Version header | Adapter gửi `X-Broker-API-Version` phù hợp không? |
| Context mapping | Tenant, cluster, namespace và consumer identity được ánh xạ/kiểm tra ra sao? |
| Async | Adapter theo dõi `last_operation`, retry và timeout như thế nào? |
| Resource model | Service instance/binding được biểu diễn bằng CRD, Secret hoặc object nào? |
| RBAC | Broker/adapter có quyền đúng namespace và đúng resource không? |
| Credentials | Binding credentials được đưa vào Secret/volume/env và cập nhật thế nào? |
| Unbind | Secret và provider permission được thu hồi đúng không? |
| Deprovision | Operator/controller xóa đúng tài nguyên, không xóa nhầm namespace/tenant khác? |
| Recovery | Controller restart, queue redelivery và resource drift được reconcile ra sao? |

### 6.1. Không suy ra Kubernetes compatibility từ Cloud Foundry compatibility

Cloud Foundry thường cung cấp `VCAP_SERVICES` cho application. Kubernetes adapter có thể tạo Secret, custom resource hoặc cập nhật workload theo cơ chế khác. Broker response có thể giống nhau ở OSB layer nhưng cách phân phối credentials và consumer context không giống nhau.

Một broker có thể được OSB contract test thành công trên cả hai platform nhưng chỉ có E2E binding delivery trên Cloud Foundry. Khi đó ma trận phải ghi Kubernetes binding delivery là `Unverified` hoặc `Partial`, tùy phần đã được kiểm chứng.

### 6.2. Kubernetes version và adapter version là hai chiều riêng

Ghi riêng:

- Kubernetes server version.
- Adapter/controller release.
- CRD schema version.
- Operator/provider version.
- CNI/network policy behavior nếu có ảnh hưởng.
- RBAC policy bundle và namespace model.

Một adapter version có thể hoạt động trên hai Kubernetes releases nhưng CRD upgrade hoặc API deprecation có thể làm thay đổi kết quả. Cần kiểm tra cả API resource và hành vi controller.

## 7. Ma trận tương thích Spring và Java

Spring Cloud Open Service Broker là thư viện trong ứng dụng Spring. Nâng thư viện có thể thay đổi model, builder, service interface, auto-configuration hoặc dependency constraints. Vì vậy cần có ma trận riêng cho build/runtime.

| Thành phần | Nội dung cần ghi |
|---|---|
| Java | JDK major version và vendor/build đã kiểm thử. |
| Spring Boot | Version chính xác và release line. |
| Spring Framework | Version được dependency management resolve. |
| Spring Cloud Open Service Broker | Artifact version và API dùng trong code. |
| Reactor/Web stack | Version và execution model nếu broker dùng reactive service. |
| Spring Security | Version, filter chain và auth configuration. |
| Jackson/serialization | Version, naming strategy, date/time và JSON compatibility. |
| Database driver | Version và TLS/auth compatibility. |
| Build tool | Maven/Gradle wrapper và plugin version. |

### 7.1. Quản lý dependency bằng BOM

Ưu tiên dependency management/BOM tương thích được dự án lựa chọn thay vì tự nâng riêng lẻ một dependency nền tảng. Khi thay Spring Boot hoặc Spring Cloud Open Service Broker, kiểm tra dependency tree để phát hiện phiên bản bị override hoặc thư viện kéo theo không tương thích.

Không suy luận rằng hai artifact cùng major version chắc chắn tương thích. Dùng release notes, dependency metadata và build/test thực tế của đúng tổ hợp.

### 7.2. Kiểm tra API framework sau nâng cấp

Sau khi nâng thư viện, kiểm tra:

- Service interface và method signature cho provision/update/deprovision/bind/unbind.
- Request/response model và builder.
- Last operation response/state mapping.
- Reactive return types và subscription/error propagation.
- Auto-configuration và endpoint mapping.
- Validation, exception mapping và serialization.
- Spring Security filter chains, CSRF policy và authentication.
- Actuator/metrics/tracing endpoint và tag conventions.

Một thay đổi source-compatible vẫn có thể làm thay đổi behavior runtime, default configuration hoặc serialization. Do đó compile thành công chỉ là bước đầu.

## 8. Định nghĩa trạng thái trong ma trận

Một taxonomy rõ ràng giúp tránh hiểu nhầm giữa “đã chạy thử”, “được hỗ trợ” và “chưa biết”.

| Trạng thái | Định nghĩa | Điều kiện dùng |
|---|---|---|
| `Supported` | Tổ hợp và tính năng nằm trong phạm vi hỗ trợ đã công bố. | Contract + integration/E2E test phù hợp đã PASS; giới hạn được ghi rõ. |
| `Partial` | Chỉ một phần tính năng hoặc một số điều kiện được hỗ trợ. | Có danh sách phần được hỗ trợ và phần bị giới hạn. |
| `Unsupported` | Tổ hợp/tính năng không được release hỗ trợ theo thiết kế hoặc chính sách. | Có quyết định kỹ thuật/sản phẩm rõ ràng. |
| `Unverified` | Chưa có đủ bằng chứng để kết luận. | Chưa chạy test hoặc môi trường/bằng chứng chưa đầy đủ. |
| `Deprecated` | Vẫn có thể hoạt động nhưng đã thông báo sẽ ngừng hỗ trợ. | Có ngày thông báo, thời hạn và đường nâng cấp. |
| `Blocked` | Không thể xác minh do phụ thuộc/môi trường/lỗi ngoài phạm vi. | Ghi blocker, owner và điều kiện gỡ chặn. |

Không dùng `Supported` chỉ vì tính năng tồn tại trong code. Cần có test evidence ở đúng platform/version combination. `Partial` cũng không được dùng như cách nói mơ hồ; phải ghi rõ giới hạn, ví dụ “provision và deprovision sync supported; async polling chưa verified”.

## 9. Cấu trúc một compatibility matrix có thể vận hành

Ma trận cần đủ thông tin để developer, operator và support team ra quyết định. Một cấu trúc gợi ý:

| Trường | Mô tả |
|---|---|
| `matrix_id` | ID phiên bản của ma trận. |
| `broker_release` | Release broker được đánh giá. |
| `osb_api_range` | Version header/contract được xác nhận. |
| `framework_stack` | Spring Cloud Open Service Broker, Boot, Framework và Java. |
| `platform` | Cloud Foundry hoặc tên adapter/controller Kubernetes. |
| `platform_version` | Release/foundation/server/adapter version chính xác. |
| `provider_profile` | Provider API/engine/operator và môi trường. |
| `feature` | Catalog, provision, async, update, bind, fetch, unbind, deprovision... |
| `status` | Supported/Partial/Unsupported/Unverified/Deprecated/Blocked. |
| `constraints` | Cấu hình hoặc giới hạn cần biết. |
| `evidence` | Link test report, CI run, trace đã làm sạch hoặc release note. |
| `verified_at` | Ngày xác minh. |
| `owner` | Nhóm chịu trách nhiệm. |

### 9.1. Ví dụ ma trận tính năng

Các version trong bảng sau là placeholder để minh họa cấu trúc; không phải khẳng định tương thích cho một bản phát hành thực tế.

| Broker profile | Platform profile | Feature | Status | Constraint/evidence |
|---|---|---|---|---|
| Broker-A | CF-line-C | Catalog | Supported | Contract test và marketplace discovery PASS. |
| Broker-A | CF-line-C | Sync provision | Supported | Provider sandbox và platform state đã đối chiếu. |
| Broker-A | CF-line-C | Async provision | Supported | `202`, operation polling và terminal state PASS. |
| Broker-A | CF-line-C | Binding + VCAP delivery | Supported | App restage và kết nối database PASS. |
| Broker-A | CF-line-C | Route forwarding | Unverified | Chưa có platform route service E2E. |
| Broker-A | Kubernetes adapter-D | Provision CR | Partial | CR được tạo; provider readiness reconciliation còn thiếu test. |
| Broker-A | Kubernetes adapter-D | Binding Secret delivery | Unverified | Chưa kiểm tra rollout consumer sau Secret update. |
| Broker-A | Kubernetes adapter-D | Deprovision | Partial | Resource CR bị xóa; provider cleanup cần xác minh. |

Ma trận này không thay thế release notes. Nó cho biết một tính năng trong một tổ hợp cụ thể đã được kiểm chứng tới đâu.

### 9.2. Lưu bằng chứng có thể tái kiểm tra

Evidence nên chứa:

- CI run/build URL hoặc test report ID.
- Platform và broker version.
- Test case ID.
- Kết quả assertion ở platform, broker và provider.
- Log/trace đã làm sạch với correlation ID.
- Known issue liên quan.
- Người xác nhận và thời điểm.

Không đưa password, bearer token, Secret YAML data hoặc response credentials vào evidence. Link test report phải có quyền truy cập phù hợp và retention đủ dài cho chu kỳ hỗ trợ.

## 10. Chọn tổ hợp kiểm thử: full matrix, pairwise và critical paths

Nếu có 4 broker releases, 3 OSB API versions, 3 Spring stacks, 2 JDK lines, 4 platform versions và 3 provider profiles, full Cartesian product có:

    4 × 3 × 3 × 2 × 4 × 3 = 864 tổ hợp

Chạy toàn bộ tổ hợp có thể tốn nhiều thời gian và chi phí. Có thể dùng chiến lược phân tầng:

1. **Full test cho tổ hợp release được hỗ trợ chính thức:** mọi lifecycle feature quan trọng trên platform/provider chính.
2. **Pairwise hoặc combinatorial test:** bao phủ tương tác giữa các chiều phiên bản mà không chạy toàn bộ Cartesian product.
3. **Critical path test:** tập trung provision async, binding, update, unbind, deprovision, security và recovery.
4. **Compatibility smoke test:** startup, health, catalog, authentication và một lifecycle tối thiểu trên các tổ hợp phụ.
5. **Negative test:** version header không hỗ trợ, capability sai, request không hợp lệ, permission thiếu và provider lỗi.

Pairwise không thay thế E2E cho những workflow có rủi ro cao. Một số lỗi chỉ xuất hiện khi nhiều yếu tố kết hợp, ví dụ async operation + platform polling + provider timeout + broker restart.

### 10.1. Ma trận kiểm thử tối thiểu theo release

| Nhóm test | Tần suất gợi ý | Mục tiêu |
|---|---|---|
| Compile/startup | Mỗi build | Phát hiện dependency/runtime incompatibility. |
| Contract suite | Mỗi pull request/release candidate | Xác minh OSB request/response và version header. |
| Database migration test | Mỗi schema change | Xác minh nâng cấp dữ liệu và rollback policy. |
| Provider integration | Mỗi adapter change | Xác minh API/provider semantics. |
| Platform E2E | Release candidate và trước production rollout | Xác minh lifecycle trên consumer thật. |
| Security suite | Mỗi release/security change | Authn/authz, tenant isolation, TLS, secret handling. |
| Upgrade/rollback rehearsal | Trước release lớn | Xác minh rolling upgrade, recovery và tương thích dữ liệu. |

## 11. Kiểm tra version negotiation của OSB API

Platform gửi version contract qua header `X-Broker-API-Version`. Broker cần xác định dải version được hỗ trợ và hành vi khi nhận version không tương thích.

Các test cần có:

- Header version được hỗ trợ: request được xử lý theo semantics đã công bố.
- Header version thấp hơn mức tối thiểu: broker từ chối hoặc xử lý theo compatibility policy được tài liệu hóa.
- Header version cao hơn mức tối đa: broker không giả định hiểu semantics mới.
- Header thiếu hoặc sai định dạng: hành vi phù hợp với contract và security policy.
- Version thay đổi giữa các request của cùng workflow: broker xử lý nhất quán theo policy.

Không nên âm thầm bỏ qua header rồi xử lý mọi request theo model mới nhất. Một platform có thể gửi field hoặc semantics khác nhau theo API version. Nếu broker hỗ trợ nhiều version, cần test từng dải và ghi rõ giới hạn.

### 11.1. Backward compatibility của request/response

Khi nâng broker:

- Thêm field response tùy chọn thường ít phá vỡ hơn đổi kiểu hoặc xóa field, nhưng vẫn phải theo contract.
- Không đổi ý nghĩa của field đã công bố mà không có migration/version plan.
- Không bắt buộc platform gửi field mới nếu version cũ không yêu cầu.
- Không trả state nội bộ ngoài tập state OSB cho phép.
- Giữ ID service/plan ổn định qua release nếu platform đã lưu chúng.
- Không thay đổi semantics idempotency hoặc async mà không đánh giá workflow hiện hữu.

## 12. Kiểm tra tương thích catalog và capability

Catalog là metadata mà platform dùng để quyết định thao tác. Thay đổi catalog có thể ảnh hưởng service instance đã tồn tại.

Trước mỗi release, so sánh catalog mới với catalog của release trước:

- Service ID/plan ID có bị đổi hoặc tái sử dụng sai không?
- Service name và plan name có thay đổi ảnh hưởng CLI/operator không?
- Offering/plan có bị xóa trong khi instance cũ vẫn tồn tại không?
- `bindable`, `requires` và các capability có thay đổi không?
- Có thay đổi schema parameters hoặc defaults không?
- Có plan updateability mới hoặc bị thu hồi không?
- Dashboard/metadata có thay đổi URL hoặc contract không?

### 12.1. Không xóa plan đang có instance

Một platform có thể còn lưu service instance được provision từ plan cũ. Nếu broker loại bỏ plan khỏi catalog, cần có chính sách cho instance hiện hữu: tiếp tục update/deprovision, giữ plan legacy, hoặc thông báo thời hạn kết thúc. Không để instance cũ không thể deprovision chỉ vì plan đã bị ẩn khỏi catalog.

### 12.2. Thay đổi capability cần kiểm tra cả platform behavior

Khi bật `bindings_retrievable`, platform có thể bắt đầu gọi fetch binding. Khi thay `bindable`, platform có thể thay đổi khả năng cho phép bind. Khi bật async, platform phải xử lý `202` và polling. Mỗi capability mới cần kiểm tra platform version thực tế, không chỉ unit test catalog serialization.

## 13. Tương thích dữ liệu và database migration

Broker thường lưu service instance, binding, operation, provider resource ID và idempotency key. Nâng application version mà không kiểm tra schema có thể làm worker cũ và mới đọc cùng dữ liệu theo hai cách khác nhau.

### 13.1. Expand-and-contract migration

Với thay đổi schema có ảnh hưởng, có thể chia thành:

1. **Expand:** thêm cột/bảng/index mới theo cách code cũ vẫn hoạt động.
2. **Deploy compatible code:** code mới đọc được dữ liệu cũ và mới; ghi dữ liệu theo transition policy.
3. **Backfill:** chuyển dữ liệu cũ sang cấu trúc mới, có kiểm tra và khả năng resume.
4. **Switch reads/writes:** chuyển hẳn sang schema mới sau khi xác minh.
5. **Contract:** chỉ xóa field cũ trong release sau khi không còn code/worker cần chúng.

Không thực hiện destructive migration trong cùng thời điểm rolling deploy nếu instance/worker cũ vẫn đang chạy.

### 13.2. Worker và message compatibility

Nếu broker dùng queue/outbox:

- Event mới cần schema version.
- Consumer mới nên xử lý event cũ trong khoảng rollout.
- Producer không gửi field mới bắt buộc trước khi consumer hỗ trợ.
- Event đã nằm trong queue cần còn đọc được sau deploy.
- Dead-letter replay phải dùng schema migration/compatibility handler phù hợp.
- Operation state cũ phải được mapping sang state mới mà không mất terminal meaning.

Một release có thể tương thích HTTP API nhưng không tương thích event schema hoặc operation database. Hãy ghi các lớp này riêng trong ma trận.

## 14. Kế hoạch nâng cấp theo từng thành phần

Không nhất thiết nâng broker, Spring, Java, platform và provider cùng một lần. Thay đổi một chiều tại mỗi giai đoạn giúp khoanh vùng lỗi.

Một quy trình nâng cấp có thể gồm:

1. Chọn target release và xác định lý do nâng cấp.
2. Đọc release notes/security advisories của framework, broker và platform.
3. Cập nhật ma trận target, đánh dấu các tổ hợp cần test.
4. Nâng dependency/build trên branch riêng.
5. Chạy compile, unit, contract và integration tests.
6. Chạy migration rehearsal trên bản sao dữ liệu.
7. Triển khai vào platform sandbox và chạy E2E.
8. Kiểm tra async operations đang chạy trước khi rollout production.
9. Canary/rolling deploy và quan sát error rate, latency, queue lag.
10. Hoàn tất rollout khi health và lifecycle assertions đạt ngưỡng.
11. Cập nhật compatibility matrix, release notes và support policy.

### 14.1. Nâng platform trước hay broker trước?

Thứ tự phụ thuộc backward compatibility:

- Nếu platform mới vẫn gửi OSB contract cũ mà broker đã hỗ trợ, có thể nâng platform trước sau khi test.
- Nếu broker mới yêu cầu capability/API version mới, cần xác minh platform hỗ trợ trước khi rollout broker.
- Nếu broker mới thay đổi catalog hoặc binding behavior, thử trên sandbox với instance test và app consumer.
- Nếu platform ngừng hỗ trợ một API/behavior, cần nâng broker trước hoặc đồng bộ rollout theo maintenance plan.

Không nâng production chỉ dựa trên việc cả hai release đều có nhãn “stable”. Ma trận phải chứng minh đúng tổ hợp.

### 14.2. Nâng cấp provider adapter

Provider API/engine version có thể thay đổi permission, async behavior, error mapping, quota hoặc deletion semantics. Kiểm thử adapter độc lập trước, sau đó chạy E2E lifecycle để xác minh broker vẫn ánh xạ đúng kết quả sang OSB.

## 15. Deprecation và chính sách hỗ trợ

Ma trận tương thích phải đi cùng support policy. Một tổ hợp có thể từng được hỗ trợ nhưng sẽ hết hỗ trợ khi platform hoặc dependency hết vòng đời.

Một policy nên ghi:

- Release broker đang được hỗ trợ.
- Dải OSB API được hỗ trợ.
- Spring/Java runtime được hỗ trợ.
- Platform/adapter release đã chứng nhận.
- Provider profiles được chứng nhận.
- Ngày bắt đầu deprecation.
- Ngày kết thúc hỗ trợ hoặc thời hạn nâng cấp.
- Đường chuyển đổi và giới hạn khi chạy phiên bản cũ.

### 15.1. Quy trình deprecation

1. Xác định tổ hợp/tính năng sắp ngừng hỗ trợ và lý do.
2. Kiểm tra usage thực tế để tìm tenant/platform còn dùng.
3. Công bố thời hạn và release thay thế.
4. Cung cấp migration guide và test checklist.
5. Giữ khả năng deprovision/cleanup cho tài nguyên đã tồn tại theo policy.
6. Theo dõi tiến độ chuyển đổi.
7. Chỉ loại bỏ sau khi hết thời hạn và có phương án cho instance còn lại.

Không nên loại bỏ một service plan khỏi catalog mà không có kế hoạch xử lý instance đang chạy trên plan đó.

## 16. Quản lý ma trận trong CI/CD và release process

Ma trận nên là artifact có version, được cập nhật cùng release. Có thể lưu dưới dạng Markdown, YAML hoặc dữ liệu trong hệ thống release management; điều quan trọng là có schema nhất quán và evidence truy xuất được.

Một bản ghi YAML minh họa:

    brokerRelease: 1.8.0
    osbApi:
      minimum: 2.x-supported-min
      maximum: 2.x-supported-max
    framework:
      springCloudOpenServiceBroker: framework-version-under-test
      springBoot: boot-version-under-test
      java: jdk-major-under-test
    platform:
      type: cloud-foundry
      version: foundation-release-under-test
    features:
      provision:
        status: Supported
        evidence: ci-run-1234
      asyncProvision:
        status: Supported
        evidence: ci-run-1235
      routeForwarding:
        status: Unverified
        evidence: null

Các giá trị version ở đây là placeholder, không phải giá trị release được khuyến nghị. Trong dữ liệu thực tế, nên dùng version string chính xác và URL/ID evidence có thể truy cập.

### 16.1. Gate phát hành

Một release candidate chỉ nên được công bố cho profile đã đáp ứng tiêu chí:

- Build/startup test PASS trên Java/Spring target.
- Contract test PASS cho dải OSB API công bố.
- Migration test PASS với dữ liệu đại diện.
- Lifecycle E2E PASS cho platform/provider profile bắt buộc.
- Security test PASS.
- Known issues và unsupported features đã được ghi.
- Upgrade/rollback rehearsal đạt yêu cầu.
- Compatibility matrix và release notes đã cập nhật.

Nếu một test bị bỏ qua vì môi trường không sẵn sàng, status cần là `Unverified` hoặc `Blocked`, không tự chuyển thành `Supported`.

## 17. Ví dụ đánh giá một thay đổi release

Giả sử broker cần nâng Spring Cloud Open Service Broker và Spring Boot, đồng thời bổ sung fetch binding. Một quy trình đánh giá:

1. Ghi release hiện tại và target release vào ma trận.
2. Kiểm tra dependency constraints giữa Java, Boot, Framework và thư viện broker.
3. Build và chạy test model/service interfaces.
4. Chạy contract test với OSB API version header cũ và mới trong dải hỗ trợ.
5. Chạy platform E2E trên Cloud Foundry để xác minh binding/fetch behavior.
6. Chạy adapter E2E trên Kubernetes để xác minh Secret/resource mapping riêng.
7. Kiểm tra operation/instance schema không bị thay đổi ngoài ý muốn.
8. Kiểm thử worker restart và event replay nếu event schema có thay đổi.
9. Kiểm tra `VCAP_SERVICES`/Secret delivery và ứng dụng consumer.
10. Cập nhật matrix: fetch binding chỉ thành `Supported` trên profile đã có evidence.

Nếu Cloud Foundry test PASS nhưng Kubernetes adapter chưa chạy, không gán trạng thái chung `Supported` cho mọi platform. Tách thành hai dòng platform profile.

## 18. Những lỗi thường gặp khi lập ma trận tương thích

- **Chỉ ghi “OSB 2.x”:** không chỉ rõ dải version header hoặc semantics đã kiểm tra.
- **Đồng nhất broker version với OSB API version:** hai version có vòng đời độc lập.
- **Chỉ kiểm tra compile:** bỏ qua behavior, serialization, async và platform semantics.
- **Chỉ test một platform:** suy diễn Cloud Foundry PASS thành Kubernetes PASS.
- **Ghi Supported khi chưa có evidence:** biến giả định thành cam kết hỗ trợ.
- **Không kiểm tra capability:** catalog công bố tính năng mà endpoint chưa triển khai.
- **Bỏ qua plan/instance cũ:** upgrade làm platform không thể update hoặc deprovision tài nguyên hiện hữu.
- **Nâng dependency và schema cùng lúc không có rehearsal:** khó rollback khi dữ liệu đã biến đổi.
- **Không kiểm tra worker/queue compatibility:** event cũ không được consumer mới đọc.
- **Không ghi platform/provider version:** không thể tái hiện lỗi.
- **Không có ngày xác minh/owner:** matrix nhanh chóng lỗi thời.
- **Không công bố deprecation:** operator tiếp tục chạy tổ hợp đã hết hỗ trợ.

## 19. Checklist xây dựng compatibility matrix

- [ ] Liệt kê broker release và build ID.
- [ ] Ghi dải OSB API version header được hỗ trợ.
- [ ] Ghi chính xác Spring Cloud Open Service Broker, Boot, Framework và Java.
- [ ] Ghi Cloud Foundry foundation hoặc Kubernetes adapter/controller version.
- [ ] Ghi provider API/engine/operator và database schema version.
- [ ] Tạo ma trận tính năng cho catalog, provision, async, update, bind, fetch, unbind và deprovision.
- [ ] Ghi capability catalog và xác minh behavior tương ứng.
- [ ] Dùng taxonomy Supported/Partial/Unsupported/Unverified/Deprecated/Blocked nhất quán.
- [ ] Gắn evidence test có thể truy xuất cho từng kết luận Supported.
- [ ] Kiểm thử contract và version negotiation.
- [ ] Kiểm thử platform-specific binding delivery.
- [ ] Kiểm thử migration, rolling upgrade, worker restart và rollback.
- [ ] Ghi known limitations, owner và ngày xác minh.
- [ ] Có support/deprecation policy và migration path.
- [ ] Cập nhật matrix như một artifact của mỗi release.

## 20. Bài tập tự luyện

### Bài tập 1: Xác định các chiều phiên bản

Một broker dùng Spring Cloud Open Service Broker, Spring Boot, Java, Cloud Foundry và PostgreSQL provider. Hãy liệt kê các version cần ghi để tái hiện một E2E test.

### Bài tập 2: Phân loại trạng thái hỗ trợ

Provision và bind đã PASS trên Cloud Foundry; provision đã PASS trên Kubernetes adapter nhưng binding Secret delivery chưa chạy. Hãy gán status riêng cho từng feature/platform và giải thích vì sao không thể kết luận tất cả đều Supported.

### Bài tập 3: Đánh giá capability

Release mới bật `bindings_retrievable` trong catalog. Hãy lập các test cần chạy ở broker, platform và provider trước khi công bố capability.

### Bài tập 4: Lập kế hoạch nâng cấp

Broker cần nâng Spring Boot và Java major version nhưng vẫn phải phục vụ operation đang chạy. Hãy đề xuất thứ tự nâng cấp, migration và kiểm tra rolling deployment.

### Bài tập 5: Thiết kế ma trận CI

Có ba broker releases, hai OSB API versions, hai platform profiles và hai provider profiles. Hãy chọn tổ hợp critical path và pairwise để giảm số lần chạy nhưng vẫn bao phủ async, binding và deprovision.

## Kết luận

Ma trận tương thích phải mô tả rõ quan hệ giữa broker release, OSB API contract, Spring/Java stack, platform, provider và database schema. Mỗi tính năng cần có trạng thái hỗ trợ, điều kiện, giới hạn và bằng chứng kiểm thử. Cloud Foundry và Kubernetes OSB adapter cần được đánh giá thành các platform profile riêng vì cách phân phối binding và quản lý tài nguyên khác nhau. Khi ma trận được cập nhật cùng CI/CD, migration rehearsal và support policy, nhóm có thể nâng cấp broker có kiểm soát, tránh công bố quá mức khả năng tương thích và giúp operator chọn đúng tổ hợp đã được xác minh.
