# Catalog không xuất hiện hoặc gói không hiển thị trên marketplace

Trong một Spring Cloud service broker tuân thủ Open Service Broker API (OSB API), catalog là danh sách service và plan mà platform có thể khám phá. Platform đọc catalog từ endpoint của broker rồi quyết định service nào và plan nào có thể hiển thị trong marketplace. Vì vậy, một service có thể tồn tại trong code và broker vẫn chạy bình thường nhưng không xuất hiện trong marketplace; hoặc service hiển thị nhưng một số plan không thấy được.

Sự cố thường nằm ở một trong các ranh giới: broker trả catalog sai hoặc không đầy đủ; platform không gọi được endpoint; broker registration hoặc authentication không đúng; catalog bị cache; service/plan chưa được cấp quyền truy cập; hoặc lớp marketplace áp dụng thêm quy tắc hiển thị riêng. Cần kiểm tra theo từng lớp để xác định dữ liệu biến mất ở đâu.

Bài học này hướng dẫn chẩn đoán từ HTTP endpoint GET /v2/catalog, cấu trúc JSON của service và plan, metadata hiển thị, cấu hình Spring Cloud Open Service Broker, đăng ký broker trên Cloud Foundry và tích hợp catalog với Kubernetes. Nội dung cũng trình bày cách kiểm tra quyền truy cập, cache, version, lỗi serialization và kiểm thử để ngăn catalog bị thiếu sau mỗi lần triển khai.

## 1. Hiểu đường đi của catalog

OSB API định nghĩa endpoint catalog để platform lấy danh sách service offerings mà broker cung cấp. Broker trả về danh sách service cùng các plan của từng service. Platform có thể lưu catalog, đồng bộ vào registry nội bộ và dùng dữ liệu đó để dựng marketplace.

Luồng tổng quát:

~~~mermaid
sequenceDiagram
    participant U as Operator
    participant M as Marketplace
    participant P as Platform service manager
    participant B as Spring Cloud broker
    participant C as Catalog configuration
    U->>P: Register/update broker
    M->>P: Request available services
    P->>B: GET /v2/catalog
    B->>C: Build service and plan list
    C-->>B: Catalog model
    B-->>P: 200 + JSON catalog
    P->>P: Validate, cache and apply access policy
    P-->>M: Visible services and plans
~~~

Catalog có thể bị mất ở nhiều bước:

- Platform không kết nối được broker hoặc xác thực thất bại.
- Broker trả JSON không đúng schema OSB.
- Service hoặc plan bị loại khỏi catalog do cấu hình.
- Platform nhận catalog nhưng không đồng bộ hoặc cache bản cũ.
- Service được đồng bộ nhưng chưa được enable cho organization/tenant.
- Marketplace áp dụng filter theo quyền, tag, visibility hoặc policy.
- Người dùng đang xem sai marketplace, organization, region hoặc cluster.

Không nên bắt đầu bằng việc sửa giao diện marketplace. Trước hết phải xác định platform có nhận được service và plan từ endpoint catalog hay không.

## 2. Kiểm tra trực tiếp endpoint GET /v2/catalog

Bước đầu tiên là gọi endpoint catalog bằng đúng URL mà platform đã đăng ký. OSB API thường dùng path /v2/catalog; broker có thể được triển khai phía sau reverse proxy hoặc context path, vì vậy cần kiểm tra URL thực tế.

Ví dụ dùng curl:

~~~bash
curl --fail-with-body \
  --user "$BROKER_USERNAME:$BROKER_PASSWORD" \
  --header "X-Broker-API-Version: 2.14" \
  --header "Accept: application/json" \
  "https://broker.example.com/v2/catalog"
~~~

Đây là ví dụ minh họa. Hãy dùng API version mà platform hỗ trợ và thông tin xác thực được cấp cho môi trường đang kiểm tra. Không ghi password thật trực tiếp vào shell history hoặc ticket. Trên môi trường Windows, có thể dùng PowerShell Invoke-RestMethod hoặc công cụ HTTP client được tổ chức cho phép.

Kết quả cơ bản cần kiểm tra:

| Hạng mục | Kết quả mong đợi |
|---|---|
| DNS/TLS | Hostname phân giải được và certificate hợp lệ |
| HTTP status | 200 OK |
| Content-Type | application/json |
| Authentication | Broker chấp nhận credentials của platform |
| JSON syntax | Parse được hoàn toàn |
| Catalog schema | Có trường services với cấu trúc hợp lệ |
| Service count | Có service dự kiến |
| Plan count | Mỗi service có các plan dự kiến |
| API version | Tương thích với platform |

Nếu request không thành công, lưu lại status, response headers, correlation ID và phần body đã được redaction. Nếu request thành công, lưu một bản catalog đã loại bỏ dữ liệu nhạy cảm để so sánh với catalog mà platform hiển thị.

## 3. Phân biệt lỗi endpoint với lỗi hiển thị

Các dấu hiệu sau giúp khoanh vùng nhanh:

| Quan sát | Vùng cần kiểm tra |
|---|---|
| DNS không phân giải | DNS, service discovery hoặc hostname |
| TLS handshake thất bại | Certificate, trust store, ingress hoặc proxy |
| Connection refused/timeout | Service, port, network policy, load balancer |
| 401 Unauthorized | Broker credentials hoặc authentication configuration |
| 403 Forbidden | Authorization, ingress policy hoặc account scope |
| 404 Not Found | Base URL, context path, route hoặc endpoint mapping |
| 406/415 | Accept hoặc Content-Type và cấu hình HTTP |
| 5xx | Broker startup, catalog builder, dependency hoặc exception handler |
| 200 nhưng services rỗng | Catalog configuration hoặc filter trong broker |
| 200 có service nhưng thiếu plan | Plan registration, filtering hoặc serialization |
| Endpoint đầy đủ nhưng marketplace thiếu | Platform sync, cache, access policy hoặc marketplace filter |

Một HTTP 200 chỉ chứng minh endpoint trả response thành công. Nó không chứng minh platform đã chấp nhận schema, đồng bộ catalog hoặc cấp quyền hiển thị service.

## 4. Kiểm tra cấu trúc JSON của catalog

Catalog response có trường services chứa danh sách service offerings. Mỗi service cần có các định danh và mô tả cần thiết theo OSB API.

Ví dụ tối giản:

~~~json
{
  "services": [
    {
      "id": "8f8d9c3a-6f8a-4d9d-a24d-2f30a1f71d10",
      "name": "managed-postgresql",
      "description": "Managed PostgreSQL database",
      "bindable": true,
      "plans": [
        {
          "id": "f4c9c64a-1e2d-4f2a-bd45-3e9b2a1c8a10",
          "name": "small",
          "description": "Small PostgreSQL instance",
          "free": false
        }
      ]
    }
  ]
}
~~~

Đây là ví dụ minh họa, không phải catalog hoàn chỉnh cho mọi broker. Các trường tùy chọn có thể xuất hiện theo capability và phiên bản OSB. Cần kiểm tra schema mà platform hỗ trợ.

Các trường quan trọng:

| Trường | Ý nghĩa | Điều cần xác minh |
|---|---|---|
| services | Danh sách service offerings | Có đúng service cần công bố không |
| service.id | Định danh ổn định của service | Không bị đổi giữa các lần deploy |
| service.name | Tên service trong catalog | Không trùng với service khác trong phạm vi platform |
| service.description | Mô tả chức năng | Có giá trị và dễ hiểu |
| service.bindable | Service có hỗ trợ binding không | Phù hợp với implementation |
| service.plans | Danh sách plan | Không null hoặc bị lọc nhầm |
| plan.id | Định danh ổn định của plan | Không đổi khi chỉ sửa tên hiển thị |
| plan.name | Tên plan | Duy nhất trong phạm vi service theo policy |
| plan.description | Mô tả plan | Phản ánh đúng giới hạn và tính năng |
| plan.free | Plan có miễn phí hay không nếu được khai báo | Không gán sai chi phí |

Không nên chỉ kiểm tra tên service. Platform thường định danh service và plan bằng ID. Nếu ID thay đổi sau một lần release, platform có thể coi đó là service hoặc plan mới, làm ảnh hưởng tới instance đã được tạo trước đó.

## 5. Kiểm tra service ID và plan ID

ID cần ổn định qua các lần restart và deployment. Không sinh UUID ngẫu nhiên mỗi lần tạo catalog trong runtime.

Ví dụ cấu hình không tốt:

~~~java
ServiceDefinition.builder()
        .id(UUID.randomUUID().toString())
        .name("managed-postgresql")
        .description("Managed PostgreSQL")
        .build();
~~~

Mỗi lần broker khởi động, service có ID khác. Platform có thể thấy offering mới, mất liên kết với dữ liệu cũ hoặc từ chối catalog do định danh thay đổi.

Nên dùng ID cấu hình cố định:

~~~java
ServiceDefinition.builder()
        .id("8f8d9c3a-6f8a-4d9d-a24d-2f30a1f71d10")
        .name("managed-postgresql")
        .description("Managed PostgreSQL")
        .bindable(true)
        .plan(postgresSmallPlan())
        .plan(postgresProductionPlan())
        .build();
~~~

Ví dụ dùng builder để minh họa. Tên method và API builder cần đối chiếu phiên bản Spring Cloud Open Service Broker đang dùng.

Khi thay đổi catalog:

- Giữ service ID nếu vẫn là cùng offering.
- Giữ plan ID nếu vẫn là cùng plan về mặt nghiệp vụ.
- Chỉ đổi name hoặc description khi cần thay đổi nhãn hiển thị.
- Không tái sử dụng ID của plan đã bị loại bỏ cho một plan khác.
- Kiểm tra ảnh hưởng tới service instance hiện có trước khi ngừng công bố plan.

## 6. Kiểm tra service và plan có được đăng ký vào catalog builder

Trong Spring Cloud Open Service Broker, catalog thường được tạo từ các service definition được cấu hình bằng builder hoặc bean theo API của phiên bản thư viện. Một service có thể không xuất hiện nếu bean không được tạo, profile không được bật hoặc cấu hình conditional không thỏa mãn.

Ví dụ cấu trúc khai báo khái niệm:

~~~java
@Configuration
public class BrokerCatalogConfiguration {

    @Bean
    public ServiceDefinition postgresService() {
        return ServiceDefinition.builder()
                .id("8f8d9c3a-6f8a-4d9d-a24d-2f30a1f71d10")
                .name("managed-postgresql")
                .description("Managed PostgreSQL database")
                .bindable(true)
                .plan(postgresSmallPlan())
                .plan(postgresProductionPlan())
                .build();
    }

    private Plan postgresSmallPlan() {
        return Plan.builder()
                .id("f4c9c64a-1e2d-4f2a-bd45-3e9b2a1c8a10")
                .name("small")
                .description("Small database")
                .free(false)
                .build();
    }

    private Plan postgresProductionPlan() {
        return Plan.builder()
                .id("c1b2d3e4-5f60-4789-8123-456789abcdef")
                .name("production")
                .description("Production database")
                .free(false)
                .build();
    }
}
~~~

Đây là ví dụ về cách tổ chức cấu hình, không bảo đảm chữ ký builder giống mọi release. Hãy kiểm tra đúng dependency và API của phiên bản dự án.

Các nguyên nhân phổ biến:

- Class cấu hình không nằm trong component scan.
- Bean bị giới hạn bởi profile như dev hoặc local.
- Conditional property đang false.
- Bean bị loại bởi cấu hình auto-configuration.
- Plan được tạo nhưng không được thêm vào ServiceDefinition.
- Có exception trong quá trình dựng catalog.
- Nhiều bean hoặc catalog source cạnh tranh nhau.

Hãy kiểm tra startup log và application context test để xác nhận catalog builder nhận đúng số service và plan.

## 7. Kiểm tra profile và cấu hình môi trường

Catalog có thể khác nhau giữa local, staging và production nếu dùng profile hoặc property để bật/tắt offering.

Ví dụ:

~~~yaml
broker:
  catalog:
    services:
      postgresql:
        enabled: true
      redis:
        enabled: false
~~~

Cấu hình minh họa này là property của ứng dụng, không phải cấu hình chuẩn OSB. Nếu service bị ẩn trong production do enabled=false, endpoint có thể vẫn trả 200 nhưng danh sách services thiếu offering đó.

Kiểm tra:

- Profile thực tế đang active.
- ConfigMap/Secret hoặc environment variables đã được mount đúng.
- Property source nào ghi đè property khác.
- Giá trị boolean có được parse đúng không.
- Deployment mới có dùng image/tag mong muốn không.
- Replica có cùng cấu hình catalog không.
- Có replica cũ vẫn trả catalog khác sau rollout không.

Nếu catalog được dựng khác nhau trên từng replica, platform có thể nhận response không nhất quán tùy load balancer. Nên log catalog version hoặc hash an toàn ở startup và kiểm tra cùng một request qua từng replica.

## 8. Kiểm tra capability và tính nhất quán giữa service với implementation

Một service có thể bị platform từ chối hoặc hiển thị sai nếu capability trong catalog không phù hợp với hành vi broker.

Các trường và capability cần xem xét:

- bindable: service có hỗ trợ binding không.
- instances_retrievable: broker có hỗ trợ lấy thông tin instance theo OSB contract không.
- bindings_retrievable: broker có hỗ trợ lấy thông tin binding không.
- plan_updateable: service có hỗ trợ update plan không.
- requires: service yêu cầu capability hoặc tính năng platform nào.
- plans: danh sách plan mà broker công bố.

Không khai báo capability chỉ để marketplace trông đầy đủ. Nếu service công bố bindable nhưng handler bind chưa được triển khai, platform có thể cho phép người dùng tạo binding rồi gặp lỗi ở runtime.

Một số field tùy chọn và capability phụ thuộc phiên bản OSB. Hãy xác minh schema và semantics của phiên bản platform hỗ trợ. Catalog phải phản ánh đúng khả năng thật của broker, provider adapter và platform đích.

## 9. Kiểm tra metadata hiển thị trên marketplace

Catalog metadata có thể ảnh hưởng tới tên hiển thị, mô tả, icon, tài liệu, thông tin hỗ trợ và cách marketplace trình bày plan. Tuy nhiên, metadata không thay thế các field bắt buộc của OSB.

Ví dụ minh họa:

~~~json
{
  "metadata": {
    "displayName": "Managed PostgreSQL",
    "imageUrl": "https://assets.example.com/postgresql.png",
    "longDescription": "Managed relational database service",
    "providerDisplayName": "Platform Database Team",
    "documentationUrl": "https://docs.example.com/postgresql",
    "supportUrl": "https://support.example.com"
  }
}
~~~

Các key và cách platform sử dụng metadata có thể khác nhau. Marketplace có thể bỏ qua key không nhận diện, giới hạn URL hoặc chỉ hiển thị một tập field nhất định.

Cần kiểm tra:

- Metadata nằm đúng cấp service hay plan.
- Key được platform hỗ trợ và đúng chính tả.
- URL dùng HTTPS và truy cập được từ browser của người dùng.
- Image không bị chặn bởi authentication hoặc content policy.
- Mô tả không rỗng hoặc chứa dữ liệu nhạy cảm.
- Metadata JSON có kiểu dữ liệu phù hợp.
- Platform có cần sync lại catalog sau khi metadata thay đổi không.

Nếu service xuất hiện nhưng icon hoặc mô tả không đúng, đây thường là vấn đề metadata/rendering. Nếu service hoàn toàn không xuất hiện, hãy kiểm tra service ID, catalog sync và access policy trước.

## 10. Phân biệt catalog có plan với plan được phép hiển thị

Một plan có trong response GET /v2/catalog chưa chắc được hiển thị cho mọi organization hoặc tenant. Platform có thể áp dụng service access policy sau khi đồng bộ catalog.

Cần phân biệt:

1. Catalog publication: broker công bố service và plan.
2. Broker registration: platform biết URL và credentials của broker.
3. Service access: administrator cho phép organization/tenant dùng service hoặc plan.
4. Marketplace visibility: giao diện chỉ hiển thị offering mà caller có quyền nhìn thấy.

Nếu endpoint catalog có plan production nhưng người dùng không thấy plan đó trong marketplace, hãy kiểm tra access policy ở platform. Không sửa broker catalog để giải quyết một vấn đề quyền truy cập.

## 11. Chẩn đoán trên Cloud Foundry

Với Cloud Foundry, broker cần được đăng ký vào platform. Sau khi đăng ký, platform đọc catalog và có thể áp dụng service access theo organization hoặc plan.

Các bước kiểm tra thường gồm:

~~~bash
cf service-brokers
cf service-access
cf marketplace
cf marketplace -s managed-postgresql
~~~

Cú pháp cụ thể có thể thay đổi theo phiên bản cf CLI và platform distribution. Dùng help của CLI đang cài đặt để xác minh options.

Các thao tác quản trị thường gặp:

- Đăng ký broker bằng URL và credentials phù hợp.
- Cập nhật broker sau khi URL hoặc credentials thay đổi.
- Kiểm tra broker đã được đăng ký và trạng thái đồng bộ.
- Kiểm tra service access theo organization.
- Enable service hoặc plan cho phạm vi cần thiết.
- Xem marketplace ở đúng foundation và organization.

Ví dụ một số lệnh thường dùng:

~~~bash
cf create-service-broker my-broker BROKER_USERNAME BROKER_PASSWORD https://broker.example.com
cf update-service-broker my-broker BROKER_USERNAME BROKER_PASSWORD https://broker.example.com
cf enable-service-access managed-postgresql
cf enable-service-access managed-postgresql -o engineering
cf enable-service-access managed-postgresql -p production -o engineering
~~~

Các lệnh có thể yêu cầu quyền administrator hoặc quyền quản trị service access. Không chạy lệnh thay đổi access trong production khi chưa xác định organization và plan mục tiêu. Ở bước chẩn đoán, ưu tiên lệnh đọc như service-brokers, service-access và marketplace.

Nếu service có trong catalog nhưng marketplace không hiển thị:

1. Kiểm tra service broker đã đăng ký đúng URL chưa.
2. Kiểm tra platform gọi GET /v2/catalog thành công chưa.
3. Kiểm tra service name và ID trong catalog.
4. Kiểm tra service access có bị disable không.
5. Kiểm tra organization đang đăng nhập có quyền không.
6. Kiểm tra plan cụ thể đã được enable chưa.
7. Xem log platform hoặc service manager để tìm lỗi đồng bộ.

## 12. Chẩn đoán trên Kubernetes

Kubernetes không có một marketplace OSB thống nhất được mọi cluster cung cấp mặc định. Một số nền tảng dùng Service Catalog API hoặc controller tích hợp OSB; nền tảng khác có portal/operator riêng để đồng bộ service offerings.

Do đó, cần xác định thành phần nào đọc catalog:

- Operator hoặc controller gọi OSB broker.
- Service catalog component đồng bộ service class/plan.
- Platform portal đọc CRD hoặc API nội bộ.
- Một integration service chuyển catalog OSB sang resource Kubernetes.

Các bước chẩn đoán:

1. Xác định controller/adapter đang chịu trách nhiệm đồng bộ catalog.
2. Kiểm tra broker URL và secret reference mà controller sử dụng.
3. Kiểm tra log của controller khi gọi GET /v2/catalog.
4. Kiểm tra condition/status của resource đăng ký broker nếu integration có định nghĩa.
5. Kiểm tra service class/plan object đã được tạo hoặc cập nhật.
6. Kiểm tra namespace, cluster scope và policy hiển thị của portal.
7. Kiểm tra RBAC để controller có thể đọc catalog và ghi resource đồng bộ.
8. Kiểm tra resync interval và cache của controller.

Có thể dùng các lệnh đọc trạng thái:

~~~bash
kubectl get pods -A
kubectl get events -A --sort-by=.metadata.creationTimestamp
kubectl logs -n service-catalog deployment/catalog-controller
kubectl get crd
~~~

Tên namespace, Deployment và CRD chỉ là ví dụ. Thay bằng resource thực tế của integration đang cài đặt. Không giả định mọi Kubernetes cluster đều có deployment hoặc API ServiceCatalog giống nhau.

Nếu controller không thể gọi broker do TLS hoặc authentication, việc sửa Service/Plan object ở Kubernetes sẽ không giải quyết được nguyên nhân. Hãy xác minh request tới broker trước, sau đó mới kiểm tra bước chuyển đổi catalog.

## 13. Kiểm tra API version và header

Platform có thể gửi header X-Broker-API-Version để chỉ rõ phiên bản OSB API mà nó hỗ trợ. Broker cần xử lý tương thích theo phiên bản được cấu hình và thư viện đang dùng.

Các vấn đề có thể xảy ra:

- Platform gửi version thấp hơn hoặc cao hơn phạm vi broker hỗ trợ.
- Broker hoặc reverse proxy loại bỏ header.
- Custom filter xử lý header sai.
- Catalog có field chỉ được hỗ trợ ở phiên bản khác.
- Broker dùng dependency version không tương thích với platform.
- Response có field hoặc enum serialization không đúng schema.

Khi điều tra, ghi nhận giá trị header thực tế tại broker và platform. Không chỉ dựa vào cấu hình client hoặc tài liệu deployment.

Không tự sửa header thành một version mới hơn chỉ để request qua được. Hãy kiểm tra compatibility matrix và xác nhận broker thực sự hỗ trợ semantics của version đó.

## 14. Kiểm tra authentication, authorization và reverse proxy

Catalog endpoint thường được platform gọi bằng broker credentials đã đăng ký. Nếu credentials bị rotate ở broker nhưng platform vẫn giữ giá trị cũ, request có thể trả 401.

Kiểm tra:

- Username/password hoặc token của broker registration.
- Secret version mà platform đang sử dụng.
- Security filter chain của Spring Security.
- Basic Auth hoặc cơ chế xác thực được cấu hình.
- Reverse proxy có loại bỏ Authorization header không.
- TLS termination và forwarded headers.
- Network policy giữa platform và broker.
- Có allowlist IP hoặc mTLS policy nào chặn platform không.

Một số proxy không chuyển tiếp Authorization header nếu cấu hình chưa đúng. Cũng có thể proxy rewrite path khiến /v2/catalog thành một path khác.

Không bật log raw Authorization header để debug. Có thể log kết quả authentication, principal đã xác minh, request ID và source component mà không ghi credential.

## 15. Kiểm tra cache và quá trình đồng bộ catalog

Platform thường cache catalog để giảm số lần gọi broker. Thay đổi service hoặc plan trong broker có thể chưa xuất hiện ngay trên marketplace.

Cần xác định:

- Platform có cache catalog không.
- Cache được refresh theo thời gian hay chỉ khi operator trigger sync.
- Có endpoint hoặc command quản trị để refresh không.
- Broker có nhiều replica với catalog khác nhau không.
- Load balancer có route tới replica cũ không.
- Portal có cache riêng ngoài service manager không.
- Service access có được cập nhật sau khi catalog refresh không.

Một quy trình so sánh:

1. Gọi trực tiếp từng replica broker nếu có thể.
2. So sánh JSON catalog giữa các replica.
3. So sánh catalog từ broker với bản platform đã đồng bộ.
4. So sánh catalog platform với dữ liệu marketplace.
5. Xác định lớp đầu tiên làm mất service hoặc plan.
6. Chỉ refresh cache sau khi đã xác minh nguồn catalog đúng.

Không xóa cache một cách tùy tiện nếu platform đang có operation hoặc service instance phụ thuộc vào offering hiện tại. Cần dùng cơ chế refresh được platform hỗ trợ và kiểm tra ảnh hưởng.

## 16. Kiểm tra catalog consistency giữa các replica

Nếu catalog được tạo từ cấu hình động hoặc database, các replica có thể trả nội dung khác nhau trong lúc rollout.

Ví dụ:

- Replica A chạy image mới, có plan production.
- Replica B chạy image cũ, chỉ có plan small.
- Load balancer phân phối request luân phiên.
- Platform nhận catalog khác nhau theo từng lần sync.

Nên:

- Dùng immutable image/version và rollout có kiểm soát.
- Đảm bảo mọi replica dùng cùng catalog configuration.
- Không lưu catalog riêng trong memory nếu nguồn cấu hình có thể khác giữa replica.
- Log catalog version hoặc hash an toàn khi startup.
- Có readiness check xác minh catalog load thành công.
- Drain replica cũ sau khi rollout.
- Kiểm thử catalog consistency trước khi hoàn tất deployment.

Catalog hash nên được tạo từ JSON canonicalized hoặc cấu hình đã chuẩn hóa, không chứa secret. Không cần log toàn bộ catalog ở production nếu metadata có thể nhạy cảm.

## 17. Kiểm tra serialization và schema validation

Một object catalog có thể được tạo đúng trong Java nhưng serialize sai do Jackson configuration, custom serializer hoặc dependency mismatch.

Các lỗi thường gặp:

- Field bị null và bị bỏ khỏi JSON.
- Enum serialize thành tên không được platform chấp nhận.
- Boolean hoặc number serialize thành string.
- Plan list rỗng do builder không thêm plan.
- Metadata có kiểu dữ liệu không đúng.
- Duplicate service ID hoặc plan ID.
- JSON không hợp lệ do custom response wrapper.
- Response bị bọc thêm một cấp, ví dụ services nằm dưới data thay vì root.

Không chỉ kiểm tra object trong unit test. Cần gọi endpoint HTTP thực tế, lấy raw response và validate schema.

Ví dụ test ý tưởng:

~~~java
webTestClient.get()
        .uri("/v2/catalog")
        .headers(headers ->
                headers.setBasicAuth("broker-user", "test-password"))
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.services").isArray()
        .jsonPath("$.services[0].id").isNotEmpty()
        .jsonPath("$.services[0].plans").isArray();
~~~

Đây là cấu trúc test minh họa. Cần cấu hình API version, security và route theo broker thực tế. Nếu catalog có nhiều service, không nên dựa vào index 0; hãy tìm service theo ID hoặc name trong JSON đã parse.

## 18. Kiểm tra trùng ID và trùng tên

Catalog có thể bị platform từ chối hoặc hiển thị khó hiểu nếu ID trùng. Name cũng cần được quản lý để tránh người dùng không phân biệt được các offering.

Kiểm tra:

- Service ID duy nhất trong catalog.
- Plan ID duy nhất trong phạm vi service theo contract.
- Không tái sử dụng ID của service/plan đã bị xóa cho sản phẩm khác.
- Name không vô tình trùng với service khác trong marketplace.
- Display name có thể khác name kỹ thuật nhưng cần nhất quán.
- Không tạo ID dựa trên UUID random ở mỗi lần startup.
- Catalog migration giữ mapping với instance hiện có.

Có thể thêm test kiểm tra uniqueness:

~~~java
assertThat(serviceDefinitions)
        .extracting(ServiceDefinition::getId)
        .doesNotHaveDuplicates();
~~~

Tên accessor cần điều chỉnh theo model thực tế. Ngoài uniqueness, cần test ID ổn định qua hai lần khởi tạo catalog với cùng cấu hình.

## 19. Metadata có URL hoặc image không truy cập được

Một số marketplace hiển thị service dù icon hoặc tài liệu không tải được. Đây là lỗi presentation, không nhất thiết là lỗi catalog.

Kiểm tra:

- Image URL trả HTTP 200.
- Certificate HTTPS hợp lệ.
- URL không yêu cầu cookie hoặc authentication riêng.
- Content-Type của image phù hợp.
- Kích thước file hợp lý.
- Browser marketplace có thể truy cập domain.
- CSP hoặc proxy không chặn resource.
- Documentation/support URL không redirect tới địa chỉ nội bộ.

Nếu metadata chứa URL có signed token hoặc query credential, hãy loại bỏ vì catalog có thể được cache và hiển thị rộng. Chỉ công bố URL công khai hoặc endpoint được thiết kế để truy cập theo policy.

## 20. Catalog thay đổi nhưng marketplace vẫn hiển thị dữ liệu cũ

Khi thay đổi tên, mô tả hoặc plan, broker có thể đã trả catalog mới nhưng marketplace vẫn dùng bản cũ.

Quy trình kiểm tra:

1. Xác nhận commit/deployment chứa catalog mới.
2. Gọi GET /v2/catalog trực tiếp.
3. So sánh service ID, plan ID và metadata với bản mong muốn.
4. Xác định platform sync tự động hay cần trigger.
5. Kiểm tra sync job có thành công không.
6. Kiểm tra cache của service manager.
7. Kiểm tra cache riêng của portal/browser.
8. Xác minh user đang xem đúng foundation, organization, region hoặc cluster.

Nếu platform không hỗ trợ refresh ngay, có thể cần chờ chu kỳ sync. Không nên unregister rồi register lại broker như một cách refresh mặc định; thao tác đó có thể ảnh hưởng service instance và access configuration.

## 21. Quan sát catalog endpoint

Broker nên có log và metric đủ để xác định platform có gọi catalog hay không.

Các metric hữu ích:

- Số request GET /v2/catalog theo status.
- Latency p50/p95/p99.
- Số lần authentication failure.
- Số service và plan trong response.
- Catalog version/hash.
- Số lỗi serialization.
- Số request theo platform client hoặc broker registration, nếu được phép.
- Số lần catalog reload và thời điểm reload gần nhất.

Log nên có:

- Correlation ID.
- Request path và method.
- API version header.
- Principal hoặc client reference đã xác minh.
- HTTP status.
- Catalog version/hash.
- Thời gian xử lý.
- Error code đã chuẩn hóa.

Không log password, Authorization header hoặc toàn bộ response nếu không cần. Catalog thường không chứa secret nhưng có thể chứa metadata nội bộ, do đó vẫn cần đánh giá quyền truy cập.

## 22. Phân biệt lỗi catalog với lỗi provisioning

Một service có thể hiển thị trong marketplace nhưng tạo instance thất bại. Đây là lỗi sau giai đoạn catalog.

| Triệu chứng | Giai đoạn cần kiểm tra |
|---|---|
| Service không xuất hiện | Catalog, registration, sync, access |
| Service xuất hiện nhưng plan thiếu | Plan list, access policy, plan filtering |
| Service và plan đều xuất hiện nhưng provision lỗi | Provision handler, quota, provider adapter |
| Provision thành công nhưng bind lỗi | Bindability, binding handler, provider credentials |
| Binding thành công nhưng workload không kết nối | Credential mapping, network, Secret/configuration |
| Service biến mất sau update broker | Catalog ID, rollout, cache, registration |

Không sửa provision handler khi service chưa xuất hiện. Ngược lại, không tiếp tục điều chỉnh metadata catalog nếu service đã hiển thị nhưng provider create thất bại.

## 23. Quy trình chẩn đoán theo thứ tự

Có thể dùng quy trình sau để rút ngắn thời gian xử lý:

1. Xác định phạm vi: service biến mất hoàn toàn hay chỉ một plan? Ảnh hưởng mọi organization hay một người dùng?
2. Gọi endpoint: truy cập đúng URL broker và lấy response GET /v2/catalog.
3. Kiểm tra HTTP: DNS, TLS, status, authentication, content type và API version.
4. Kiểm tra JSON: services array, service ID/name, plans array và schema.
5. Kiểm tra broker config: bean, profile, property, catalog builder và replica version.
6. Kiểm tra platform registration: URL, credentials, trạng thái sync và API compatibility.
7. Kiểm tra access policy: organization, tenant, service và plan đã được enable chưa.
8. Kiểm tra cache: catalog cache, portal cache và resync interval.
9. Kiểm tra metadata: display name, icon, documentation URL và field platform hỗ trợ.
10. Kiểm tra audit/log: thời điểm platform gọi catalog và lớp đầu tiên làm mất offering.
11. Thực hiện sửa đổi nhỏ nhất: cập nhật đúng cấu hình hoặc access policy.
12. Xác minh lại: gọi catalog, refresh sync theo cơ chế platform và kiểm tra marketplace ở đúng scope.

## 24. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| GET /v2/catalog trả 404 | Sai base URL hoặc context path | Kiểm tra broker URL và proxy rewrite |
| GET /v2/catalog trả 401 | Credentials đã đổi hoặc proxy không chuyển Authorization | Đồng bộ secret và kiểm tra security chain |
| Catalog trả 200 nhưng services rỗng | Bean không được tạo hoặc profile loại service | Kiểm tra catalog configuration và active profile |
| Service có nhưng plans rỗng | Không thêm plan vào service definition | Kiểm tra builder và catalog serialization |
| Plan có trong JSON nhưng không thấy ở marketplace | Plan chưa được enable cho organization | Kiểm tra service access của platform |
| Service biến mất sau deployment | ID thay đổi hoặc replica có catalog khác | Giữ ID ổn định và đồng bộ rollout |
| Metadata không hiển thị | Key không được platform hỗ trợ hoặc URL không truy cập | Kiểm tra metadata schema và browser access |
| Platform sync thất bại | API version, JSON schema hoặc TLS không tương thích | Kiểm tra request thực tế và platform log |
| Chỉ một organization không thấy service | Access policy hoặc scope | Kiểm tra quyền của organization |
| Portal hiển thị dữ liệu cũ | Cache chưa refresh | Dùng cơ chế resync được hỗ trợ |
| Một số lần gọi thấy plan, một số lần không | Replica cấu hình không đồng nhất | So sánh catalog trên từng replica |
| Service hiển thị nhưng provision lỗi | Lỗi nằm ở lifecycle handler/provider | Chuyển sang chẩn đoán provision |

## 25. Checklist kiểm tra catalog trước release

**Broker endpoint và registration**

- [ ] Platform gọi đúng URL GET /v2/catalog.
- [ ] DNS, TLS và network path hoạt động.
- [ ] Broker credentials được đồng bộ với platform.
- [ ] X-Broker-API-Version được xử lý đúng.
- [ ] Response trả 200 và application/json.
- [ ] Không có lỗi serialization hoặc custom response wrapper.

**Catalog payload**

- [ ] Services array chứa offering dự kiến.
- [ ] Service ID ổn định và không trùng.
- [ ] Service name và description hợp lệ.
- [ ] Plans array chứa các plan dự kiến.
- [ ] Plan ID ổn định và không trùng trong phạm vi service.
- [ ] Capability khớp với handler đã triển khai.
- [ ] Metadata dùng key và kiểu dữ liệu được platform hỗ trợ.
- [ ] Không có secret hoặc URL nhạy cảm trong metadata.

**Platform và marketplace**

- [ ] Broker đã đăng ký trên đúng platform.
- [ ] Catalog sync hoàn tất.
- [ ] Service access được enable cho đúng organization/tenant.
- [ ] Plan access được cấp theo policy.
- [ ] User đang xem đúng organization, region hoặc cluster.
- [ ] Cache đã được refresh theo cơ chế hỗ trợ.
- [ ] Portal/browser có thể tải metadata URL nếu cần.

**Vận hành**

- [ ] Các replica trả catalog nhất quán.
- [ ] Có metric cho catalog request, latency và status.
- [ ] Có log correlation ID và catalog version/hash.
- [ ] Có test JSON schema và uniqueness của service/plan ID.
- [ ] Có integration test gọi endpoint bằng security configuration thực tế.
- [ ] Có quy trình rollback khi catalog release gây mất offering.

Catalog là điểm bắt đầu để platform khám phá những service mà broker cung cấp. Khi service hoặc plan không xuất hiện, cần lần theo dữ liệu từ endpoint GET /v2/catalog qua registration, schema validation, access policy, cache và lớp marketplace. Giữ ID ổn định, cấu hình catalog nhất quán giữa các replica, công bố capability chính xác và kiểm thử response HTTP thực tế sẽ giúp broker tránh tình trạng offering biến mất sau deployment hoặc chỉ hiển thị cho một phần người dùng.

