# Service key và ứng dụng của binding ngoài quy trình gắn ứng dụng

Cloud Foundry cho phép ứng dụng sử dụng service thông qua service binding, nhưng không phải mọi consumer đều là một ứng dụng đang chạy trên Cloud Foundry. Một pipeline CI/CD, công cụ quản trị, máy phát triển, hệ thống giám sát hoặc workload chạy ở nền tảng khác cũng có thể cần credentials để truy cập service instance. Với các trường hợp đó, Cloud Foundry cung cấp **service key**: một bộ thông tin truy cập được tạo từ service instance nhưng không gắn với vòng đời của một ứng dụng Cloud Foundry cụ thể.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, service key vẫn đi qua vòng đời binding của Open Service Broker API (OSB API). Cloud Controller quản lý tên key và liên kết key với service instance; broker nhận yêu cầu tạo binding, cấp credentials và xử lý thu hồi khi key bị xóa. Spring Cloud Open Service Broker (SCOSB) cung cấp service abstraction cho thao tác bind/unbind, còn ứng dụng broker cần phân biệt binding dành cho app với binding được tạo để dùng như service key.

Bài học này giải thích service key là gì, cách tạo và quản lý bằng Cloud Foundry CLI, luồng xử lý qua OSB API, khác biệt với app binding, cách triển khai trong Spring Cloud Service Broker, quản lý credentials và kiểm thử vòng đời.

## 1. Service key là gì?

**Service key** là một bộ credentials được tạo cho một service instance để một consumer bên ngoài quy trình bind ứng dụng có thể truy cập service. Key không yêu cầu một app GUID làm consumer và không tự động được đưa vào môi trường của một ứng dụng Cloud Foundry.

Ví dụ, một service instance PostgreSQL tên **orders-db** đang được một ứng dụng Cloud Foundry sử dụng. Đội vận hành muốn một pipeline migration chạy từ hệ thống CI bên ngoài Cloud Foundry kết nối tới database đó. Họ có thể tạo service key riêng cho pipeline thay vì bind database vào một app giả chỉ để lấy credentials.

Service key có các đặc điểm:

- Thuộc về một service instance cụ thể.
- Có tên do người vận hành hoặc automation chọn trong Cloud Foundry.
- Được broker hiện thực hóa thành một service binding với binding ID riêng.
- Chứa credentials hoặc thông tin kết nối dành cho consumer ngoài app lifecycle.
- Có thể được liệt kê, đọc và xóa qua Cloud Foundry CLI/API.
- Có vòng đời độc lập với việc start, stop, restage hoặc xóa một ứng dụng.
- Khi bị xóa, broker cần thu hồi đúng quyền truy cập được cấp cho key đó.

Service key không phải một service instance mới. Nó không provision thêm database, queue hay bucket; nó tạo một cách truy cập vào service instance đã tồn tại.

## 2. Phân biệt app binding và service key

Cả app binding và service key đều dựa trên thao tác bind của OSB API. Điểm khác nhau nằm ở consumer và cách platform quản lý credentials.

| Tiêu chí | App binding | Service key |
|---|---|---|
| Consumer | Ứng dụng Cloud Foundry | Pipeline, developer, công cụ hoặc workload bên ngoài |
| Liên kết app | Có app association | Không gắn với app cụ thể |
| Mục tiêu | Cung cấp credentials cho app runtime | Cung cấp credentials cho consumer độc lập |
| Nơi app nhận credentials | Thường qua **VCAP_SERVICES** | Không tự xuất hiện trong VCAP_SERVICES của một app |
| Vòng đời | Gắn với thao tác bind/unbind và lifecycle app/platform | Được quản lý tường minh bằng create/delete service key |
| Cách sử dụng | App đọc credentials trong runtime | Consumer lấy key và cấu hình vào hệ thống của mình |
| Ví dụ | orders-api kết nối PostgreSQL | Pipeline chạy migration kết nối PostgreSQL |

### App binding

Khi bind service instance vào app, Cloud Foundry quản lý liên kết giữa app và service. Credentials được cung cấp cho ứng dụng qua cơ chế môi trường của platform, thường là biến **VCAP_SERVICES**. Ứng dụng có thể đọc thông tin kết nối khi chạy mà không cần người vận hành sao chép credentials thủ công vào cấu hình riêng.

Ví dụ:

~~~bash
cf bind-service orders-api orders-db
cf restage orders-api
~~~

Sau khi app được restage/restart theo quy trình của platform, ứng dụng có thể đọc service credentials từ VCAP_SERVICES.

### Service key

Với service key, không có app đích để Cloud Foundry đưa credentials vào môi trường runtime. Người dùng hoặc automation tạo key, sau đó đọc thông tin bằng CLI và cấu hình cho consumer bên ngoài theo chính sách bảo mật.

~~~bash
cf create-service-key orders-db ci-migration
cf service-key orders-db ci-migration
~~~

Kết quả **cf service-key** chứa thông tin truy cập do broker trả về. Không đưa output này vào log CI công khai, ticket không kiểm soát hoặc shell transcript được chia sẻ.

## 3. Tạo và quản lý service key bằng Cloud Foundry CLI

Các lệnh phổ biến:

| Lệnh | Mục đích |
|---|---|
| **cf create-service-key SERVICE_INSTANCE KEY_NAME** | Tạo key cho service instance |
| **cf create-service-key SERVICE_INSTANCE KEY_NAME -c PARAMETERS** | Tạo key với tham số bổ sung nếu offering hỗ trợ |
| **cf service-keys SERVICE_INSTANCE** | Liệt kê các key của instance |
| **cf service-key SERVICE_INSTANCE KEY_NAME** | Đọc credentials của một key |
| **cf delete-service-key SERVICE_INSTANCE KEY_NAME** | Xóa key và yêu cầu broker thu hồi binding |

Ví dụ tạo key cho pipeline:

~~~bash
cf create-service-key orders-db ci-migration
~~~

Nếu broker hỗ trợ tham số binding, có thể truyền parameters:

~~~bash
cf create-service-key orders-db reporting-tool -c '{"role":"read-only"}'
~~~

**role** trong ví dụ là tham số riêng của offering minh họa. Broker phải validate nó theo schema và policy; không được mặc định rằng mọi service hỗ trợ cùng một bộ tham số.

Liệt kê key:

~~~bash
cf service-keys orders-db
~~~

Đọc một key:

~~~bash
cf service-key orders-db ci-migration
~~~

Xóa key:

~~~bash
cf delete-service-key orders-db ci-migration
~~~

Một số lệnh có thể có tùy chọn xác nhận hoặc force tùy phiên bản CLI. Hãy kiểm tra **cf help create-service-key** và **cf help delete-service-key** trên môi trường đang dùng.

### Bảo vệ output credentials

Lệnh đọc service key có thể in password, token hoặc endpoint riêng tư ra terminal. Trong pipeline:

- Chỉ cấp quyền đọc key cho job và người cần sử dụng.
- Mask output trong CI logs; tốt nhất không in toàn bộ JSON ra log.
- Truyền credentials qua secret store của CI hoặc biến môi trường được bảo vệ.
- Không commit file credentials vào repository.
- Không gửi output qua chat hoặc ticket công khai.
- Thu hồi key ngay khi pipeline hoặc integration không còn cần truy cập.

Service key là credential thực sự có thể truy cập tài nguyên. Tên key không phải secret, nhưng nội dung response cần được bảo vệ như password.

## 4. Luồng service key từ Cloud Foundry tới broker

Cloud Foundry quản lý service key như một loại binding không gắn với app. Khi người dùng chạy **cf create-service-key**, Cloud Controller xác thực quyền trên service instance, ghi nhận yêu cầu và gọi broker theo hợp đồng OSB API.

Luồng khái quát:

~~~mermaid
sequenceDiagram
    participant U as Operator / CI
    participant CLI as Cloud Foundry CLI
    participant CC as Cloud Controller
    participant B as Service broker
    participant DB as Broker database
    participant P as Service provider

    U->>CLI: create-service-key instance key-name
    CLI->>CC: Request create service key
    CC->>CC: Authorize access to instance
    CC->>B: OSB bind request
    B->>DB: Create binding record
    B->>P: Create key-specific principal/credential
    P-->>B: Credentials
    B->>DB: Store secret reference and binding state
    B-->>CC: Bind response with credentials
    CC-->>CLI: Key creation result
    U->>CLI: service-key instance key-name
    CLI->>CC: Read service key
    CC-->>CLI: Stored credentials
~~~

Cloud Controller quản lý tên service key và ánh xạ nó tới binding do broker tạo. Broker cần dùng **binding ID** mà platform gửi làm định danh binding trong kho dữ liệu. Không nên giả định tên **KEY_NAME** của CLI chính là **binding_id**; hai định danh thuộc hai lớp khác nhau.

Khi xóa service key, Cloud Controller gọi thao tác unbind tương ứng. Broker cần thu hồi đúng principal/credential của binding đó và cập nhật trạng thái trước khi xác nhận hoàn tất theo hợp đồng platform.

## 5. Request bind khác nhau ở đâu?

Trong OSB API, thao tác bind dùng endpoint dạng:

~~~http
PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id}
~~~

Request có thể mang **bind_resource**, context và parameters tùy platform cùng offering. Với app binding, bind_resource có thể chứa thông tin ứng dụng, chẳng hạn **app_guid**. Với service key, không có ứng dụng Cloud Foundry làm consumer, vì vậy broker không nên yêu cầu app_guid phải hiện diện để cho phép bind.

Ví dụ request app binding minh họa:

~~~json
{
  "service_id": "svc-postgresql",
  "plan_id": "plan-standard",
  "bind_resource": {
    "app_guid": "app-guid-orders-api"
  }
}
~~~

Ví dụ request cho service key minh họa, không có app association:

~~~json
{
  "service_id": "svc-postgresql",
  "plan_id": "plan-standard",
  "parameters": {
    "role": "read-only"
  }
}
~~~

Hình dạng request thực tế phụ thuộc phiên bản OSB API và cách Cloud Foundry triển khai. Broker nên xử lý **bind_resource** theo tính tùy chọn của hợp đồng, không suy luận rằng request thiếu app GUID là request sai. Đồng thời, broker không nên tự tạo app GUID giả để lấp chỗ trống.

### Không nhầm service key với binding parameters

**parameters** là dữ liệu cấu hình do consumer/platform truyền theo offering. **bind_resource** mô tả tài nguyên liên quan tới binding, ví dụ app association. Tên service key do Cloud Foundry quản lý không nhất thiết được truyền như một field OSB chuẩn trong request bind.

Vì vậy:

- Dùng **binding_id** làm khóa ổn định của binding trong broker.
- Lưu consumer type như APP hoặc KEY khi có thể xác định từ request/context đã được platform xác thực.
- Chỉ lưu app GUID khi request thực sự có app association.
- Không lấy tên key từ parameters tùy ý rồi coi đó là định danh đã xác thực.
- Nếu platform cung cấp metadata riêng trong context, chỉ sử dụng theo contract và policy đã biết.

## 6. Thiết kế dữ liệu để phân biệt binding loại APP và KEY

Một service instance có thể có nhiều app binding và nhiều service key. Broker nên lưu mỗi binding như một bản ghi riêng, cùng loại consumer và secret reference.

Ví dụ cấu trúc nội bộ:

| Trường | Ý nghĩa |
|---|---|
| **binding_id** | ID binding do platform gửi |
| **instance_id** | Service instance được bind |
| **binding_type** | APP hoặc KEY nếu xác định được |
| **app_guid** | App GUID, nullable với service key |
| **consumer_reference** | Tham chiếu consumer nếu platform cung cấp |
| **parameters** | Parameters đã validate, không chứa secret |
| **credentials_secret_ref** | Secret reference riêng của binding |
| **state** | CREATING, ACTIVE, REVOKING, REVOKED hoặc FAILED |
| **created_at, revoked_at** | Mốc thời gian |

Ví dụ record:

~~~json
{
  "binding_id": "binding-8f31",
  "instance_id": "instance-orders-db",
  "binding_type": "KEY",
  "app_guid": null,
  "consumer_reference": "ci-migration",
  "credentials_secret_ref": "secret://broker/bindings/binding-8f31",
  "state": "ACTIVE"
}
~~~

**consumer_reference** trong ví dụ là metadata nội bộ minh họa. Không được giả định Cloud Foundry luôn gửi tên key **ci-migration** trong OSB request. Nếu platform không cung cấp tên đó qua contract được hỗ trợ, broker chỉ lưu binding ID và các context field thực sự nhận được.

Không dùng một credential chung cho mọi binding của instance. Khi **ci-migration** bị xóa, broker phải thu hồi credential của **binding-8f31** mà không ảnh hưởng app binding **orders-api** hoặc service key khác.

## 7. Triển khai bind trong Spring Cloud Service Broker

SCOSB cung cấp **ServiceInstanceBindingService** để triển khai nghiệp vụ tạo, đọc và xóa binding. Với service key, broker vẫn thực hiện thao tác create binding; điểm khác biệt là không có app association bắt buộc.

Ví dụ component xử lý nghiệp vụ:

~~~java
import org.springframework.stereotype.Service;

import org.springframework.cloud.servicebroker.model.binding.CreateServiceInstanceBindingRequest;
import org.springframework.cloud.servicebroker.model.binding.CreateServiceInstanceBindingResponse;

import reactor.core.publisher.Mono;

@Service
public class BrokerBindingService {

    private final BindingRepository bindingRepository;
    private final ProviderBindingClient providerBindingClient;
    private final BindingSecretStore secretStore;

    public BrokerBindingService(
            BindingRepository bindingRepository,
            ProviderBindingClient providerBindingClient,
            BindingSecretStore secretStore) {
        this.bindingRepository = bindingRepository;
        this.providerBindingClient = providerBindingClient;
        this.secretStore = secretStore;
    }

    public Mono<CreateServiceInstanceBindingResponse> create(
            CreateServiceInstanceBindingRequest request) {

        String instanceId = request.getServiceInstanceId();
        String bindingId = request.getBindingId();

        boolean hasAppAssociation =
                request.getBindResource() != null
                && request.getBindResource().getAppGuid() != null;

        BindingType type = hasAppAssociation
                ? BindingType.APP
                : BindingType.KEY;

        return bindingRepository.createPending(
                        instanceId, bindingId, type,
                        hasAppAssociation
                                ? request.getBindResource().getAppGuid()
                                : null)
                .then(providerBindingClient.createCredentials(
                        instanceId, bindingId, request.getParameters()))
                .flatMap(credentials -> secretStore
                        .write(bindingId, credentials)
                        .flatMap(secretRef -> bindingRepository.activate(
                                bindingId, secretRef)
                                .thenReturn(credentials)))
                .map(credentials -> CreateServiceInstanceBindingResponse.builder()
                        .credentials(credentials)
                        .build());
    }
}

enum BindingType {
    APP,
    KEY
}
~~~

Đây là ví dụ kiến trúc rút gọn. Tên accessor, package và builder cần được đối chiếu với phiên bản SCOSB đang dùng. Việc phân loại KEY bằng cách không có app GUID chỉ phù hợp khi platform contract xác định rõ kiểu request này; nếu một platform có dạng binding khác cũng không có app GUID, cần dùng context/metadata đáng tin cậy để phân biệt thay vì suy đoán.

Trong triển khai đầy đủ, adapter triển khai **ServiceInstanceBindingService** sẽ ủy quyền cho application service và đồng thời xử lý các phương thức lifecycle còn lại của interface. Không đặt toàn bộ logic provider, secret storage và persistence vào controller.

### Tại sao phải lưu binding trước khi trả credentials?

Nếu provider đã tạo user nhưng broker chưa lưu secret reference, platform có thể nhận credentials mà broker không thể truy xuất lại. Luồng cần quản lý các bước tạo principal, ghi secret, commit binding và xử lý lỗi một cách nhất quán.

Nếu provider tạo credential thành công nhưng secret manager hoặc database gặp lỗi:

- Giữ binding ở trạng thái chưa ACTIVE.
- Retry bước có thể retry an toàn.
- Nếu không thể hoàn tất, thu hồi principal đã tạo hoặc đưa vào reconciliation.
- Không trả success response với credentials chưa được lưu theo thiết kế.
- Không log credentials trong quá trình xử lý lỗi.

## 8. Đọc service key và hỗ trợ bindings_retrievable

Cloud Foundry CLI có lệnh đọc key đã tạo:

~~~bash
cf service-key orders-db ci-migration
~~~

Cloud Controller lấy credentials đã lưu cho service key. Broker có thể được gọi qua GET binding nếu offering và platform sử dụng capability retrieval tương ứng.

Trong catalog OSB API, **bindings_retrievable** cho biết broker hỗ trợ đọc lại service binding. Nếu công bố capability này, broker cần triển khai **getServiceInstanceBinding()** để trả đúng credentials hiện hành của binding.

Các nguyên tắc:

- Tra cứu theo cả instance ID và binding ID.
- Xác minh binding thuộc đúng tenant và service instance.
- Kiểm tra trạng thái binding trước khi đọc secret.
- Đọc đúng secret version đã lưu.
- Không tạo credentials mới khi GET.
- Không trả provider credential hoặc secret của binding khác.
- Không yêu cầu app GUID đối với service key.
- Nếu không thể khôi phục credentials an toàn, không công bố capability retrieval cho offering đó.

Ví dụ response minh họa:

~~~json
{
  "credentials": {
    "username": "ci_migration",
    "password": "<service-key-secret>",
    "host": "pg.internal.example",
    "port": 5432,
    "database": "orders"
  }
}
~~~

Service key không tự động xuất hiện trong **VCAP_SERVICES** của app. Consumer ngoài Cloud Foundry nhận credentials qua quy trình đọc key được phân quyền, sau đó lưu vào secret store riêng của mình.

## 9. Xóa service key và thu hồi quyền

Khi không còn cần key, người vận hành xóa nó:

~~~bash
cf delete-service-key orders-db ci-migration
~~~

Cloud Foundry sẽ yêu cầu broker unbind binding tương ứng. Broker cần:

1. Xác định đúng instance ID và binding ID.
2. Chuyển binding sang REVOKING hoặc trạng thái tương đương.
3. Thu hồi user, role, token hoặc quyền provider đã tạo cho binding.
4. Xác nhận credentials không còn truy cập được.
5. Xóa hoặc đánh dấu secret hết hiệu lực theo retention policy.
6. Đánh dấu binding REVOKED và trả response theo hợp đồng OSB API.

Xóa service key không đồng nghĩa deprovision service instance. Database hoặc queue vẫn tồn tại cho các app binding và key khác. Broker không được xóa tài nguyên chính chỉ vì một key bị xóa.

Nếu provider revoke thành công nhưng database update thất bại, cần reconciliation để hoàn tất trạng thái. Nếu provider timeout và chưa rõ quyền đã bị thu hồi hay chưa, không được đánh dấu thành công giả; hãy truy vấn trạng thái provider hoặc retry theo idempotency policy.

## 10. Bảo mật service key

Service key thường được dùng ngoài app runtime nên credentials có thể xuất hiện trong pipeline, máy phát triển hoặc hệ thống quản trị. Cần bảo vệ từ lúc tạo tới lúc thu hồi.

- Tạo key riêng cho từng consumer hoặc mục đích sử dụng.
- Cấp quyền tối thiểu, ví dụ read-only cho pipeline chỉ cần đọc dữ liệu.
- Không chia sẻ một key giữa nhiều hệ thống không liên quan.
- Lưu credentials trong secret manager của CI hoặc workload.
- Hạn chế quyền chạy **cf service-key** và **cf delete-service-key**.
- Không ghi output lệnh đọc key vào log.
- Xoay key khi thay đổi người sở hữu, nghi ngờ bị lộ hoặc theo lịch.
- Xóa key khi integration ngừng hoạt động.
- Audit người tạo, đọc và xóa key nếu platform cung cấp sự kiện phù hợp.
- Không lưu key name hoặc binding ID như thể chúng là password.

Service key không gắn với app lifecycle, vì vậy platform không thể dựa vào việc xóa app để thu hồi key của một công cụ bên ngoài. Đội vận hành cần quản lý danh sách key và vòng đời của chúng một cách tường minh.

## 11. Các lỗi thường gặp

**Dùng app binding giả chỉ để lấy credentials.** Điều này tạo app association không cần thiết và có thể làm phức tạp lifecycle. Dùng service key cho consumer ngoài app.

**Giả định service key là service instance mới.** Key chỉ tạo một binding vào instance đã có; không gọi provision hoặc tạo resource chính lần nữa.

**Bắt buộc app GUID trong mọi bind request.** Service key không gắn với app. Hãy xử lý app association theo tính tùy chọn của request và contract platform.

**Dùng chung credentials giữa app binding và service key.** Khi xóa key, broker có thể vô tình thu hồi quyền của app. Mỗi binding cần principal/credential và secret reference riêng.

**Nhầm tên service key với binding ID.** Cloud Foundry quản lý tên key, còn OSB request có binding ID. Lưu đúng từng định danh và không tự ánh xạ bằng giả định.

**Cho rằng key credentials xuất hiện trong VCAP_SERVICES.** Service key không được inject vào app như app binding. Consumer phải đọc key qua lệnh/API được cấp quyền.

**Xóa service key rồi deprovision cả instance.** Unbind chỉ thu hồi một binding. Chỉ deprovision instance khi platform yêu cầu xóa service instance và các điều kiện vòng đời đã được thỏa mãn.

**Để credentials trong CI log.** Output của **cf service-key** có thể chứa password. Cần mask hoặc chuyển thẳng vào secret store được bảo vệ.

## 12. Kiểm thử service key trong broker

Bộ kiểm thử nên chứng minh broker xử lý được binding không có app association và thu hồi đúng một key.

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| Bind request có app GUID | Tạo APP binding |
| Bind request không có app GUID theo service-key flow | Tạo KEY binding |
| Service key có parameters hợp lệ | Provider tạo credentials theo policy |
| Parameters không hợp lệ | Từ chối trước provider side effect |
| Hai service key trên cùng instance | Có binding ID và credentials riêng |
| GET binding cho KEY | Trả credentials đúng key nếu retrieval được hỗ trợ |
| GET binding với instance ID sai | Không trả credentials |
| Delete một KEY binding | Chỉ revoke principal của key đó |
| Xóa key không có app association | Không yêu cầu app GUID |
| Delete key lặp lại | Xử lý idempotent theo contract |
| Provider revoke timeout | Giữ trạng thái chưa kết luận và reconcile |
| Secret store lỗi sau provider create | Không đánh dấu binding ACTIVE; cleanup/reconcile |
| App binding vẫn hoạt động sau khi xóa key khác | Credentials app không bị ảnh hưởng |
| Service instance có nhiều key | Xóa một key không ảnh hưởng key còn lại |
| Log/trace | Không chứa password hoặc token |

Nên có unit test cho application service, repository và provider adapter; integration test cho endpoint OSB bind/unbind; và kiểm thử trên Cloud Foundry sandbox để xác nhận CLI, Cloud Controller và broker phối hợp đúng.

## 13. Quy trình vận hành đề xuất

Một quy trình sử dụng service key cho pipeline có thể gồm:

1. Người quản trị xác nhận pipeline cần truy cập service instance nào.
2. Chọn quyền tối thiểu và parameters được offering hỗ trợ.
3. Tạo key riêng, ví dụ **ci-migration**.
4. Đọc credentials bằng **cf service-key** qua phiên chạy được bảo vệ.
5. Lưu credentials vào secret store của CI.
6. Cấu hình pipeline lấy secret tại runtime.
7. Theo dõi lần sử dụng và lỗi xác thực.
8. Rotate key khi cần hoặc khi credential có dấu hiệu bị lộ.
9. Xóa key khi pipeline ngừng hoạt động.
10. Xác nhận broker đã revoke principal và secret không còn hiệu lực.

Với mỗi môi trường dev, staging và production, nên dùng service key riêng. Không sao chép key production sang máy phát triển hoặc môi trường thử nghiệm.

## Kết luận

Service key của Cloud Foundry cung cấp credentials cho consumer không gắn với một ứng dụng Cloud Foundry cụ thể. Platform vẫn sử dụng vòng đời service binding của OSB API, nhưng broker không được yêu cầu app GUID cho service-key flow và phải cấp một bộ credentials riêng cho binding đó. Các lệnh **cf create-service-key**, **cf service-key**, **cf service-keys** và **cf delete-service-key** giúp người vận hành tạo, đọc, liệt kê và thu hồi key. Trong Spring Cloud Service Broker, cần lưu binding ID, phân biệt loại consumer khi contract cho phép, quản lý secret riêng, triển khai GET binding nếu công bố **bindings_retrievable**, và bảo đảm xóa key chỉ thu hồi đúng quyền truy cập của key mà không deprovision service instance.

## Tài liệu tham khảo

- [Cloud Foundry Documentation — Managing Service Instances](https://docs.cloudfoundry.org/devguide/services/managing-services.html) — tạo, bind và quản lý service instance.
- [Cloud Foundry CLI Reference](https://cli.cloudfoundry.org/en-US/v8/) — lệnh create-service-key, service-key, service-keys và delete-service-key.
- [Cloud Foundry Cloud Controller API](https://v3-apidocs.cloudfoundry.org/) — service instances, service credential bindings và API platform.
- [Open Service Broker API Specification](https://github.com/openservicebrokerapi/servicebroker/blob/master/spec.md) — bind/unbind, bind_resource và binding retrieval.
- [Spring Cloud Open Service Broker Reference Documentation](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/reference/) — ServiceInstanceBindingService và request/response model.

