# Quản lý thông tin xác thực và quyền tối thiểu của tài khoản nhà cung cấp

Service broker cần xác thực khi gọi API của hạ tầng bên ngoài để tạo, cập nhật, tra cứu và thu hồi tài nguyên. Tài khoản dùng cho các lệnh này thường có quyền rộng hơn một ứng dụng consumer. Nếu broker lưu khóa truy cập lâu dài hoặc được cấp quyền quản trị toàn bộ cloud account, một lỗi cấu hình có thể ảnh hưởng đến nhiều service instance và tenant.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, tích hợp provider cần được thiết kế quanh danh tính riêng cho broker, thông tin xác thực có thời hạn và quyền tối thiểu theo đúng vòng đời tài nguyên. Spring Cloud Open Service Broker (SCOSB) xử lý hợp đồng Open Service Broker API (OSB API); phần tích hợp hạ tầng cần lớp quản lý credential và provider adapter để gọi API cloud hoặc Kubernetes an toàn.

Bài học này trình bày cách phân biệt các loại credential, chọn cơ chế xác thực workload, giới hạn quyền theo thao tác và phạm vi tài nguyên, quản lý secret và rotation, cấu hình Spring, tách tài khoản theo tenant, kiểm thử quyền và vận hành audit.

## 1. Phân biệt ba ranh giới xác thực

Một broker thường làm việc với ít nhất ba nhóm danh tính khác nhau. Không nên dùng chung credential giữa chúng.

| Danh tính | Bên sử dụng | Mục đích | Ví dụ |
|---|---|---|---|
| Platform-to-broker | Cloud Foundry, Kubernetes platform hoặc marketplace gọi broker | Xác thực request OSB API đến broker | HTTP Basic, mTLS hoặc gateway |
| Broker-to-provider | Tiến trình broker gọi API của nhà cung cấp | Quản lý database, bucket, queue, volume hoặc tài nguyên khác | Workload identity, IAM role, service account |
| Binding-to-service | Ứng dụng consumer kết nối dịch vụ đã bind | Truy cập database, cache hoặc service instance | Username/password riêng cho binding, certificate hoặc token |

**Platform-to-broker credential** bảo vệ endpoint broker. Nó chứng minh request đến từ platform hoặc client được cấp quyền gọi broker. Credential này không tự động cho broker quyền tạo tài nguyên ở provider.

**Broker-to-provider credential** là danh tính của workload broker trong hạ tầng. Nó cho phép broker thực hiện tập thao tác quản trị đã được cấp. Không gửi credential này cho platform hoặc consumer.

**Binding credential** được cấp riêng cho consumer sau thao tác bind. Nó chỉ nên cho phép consumer sử dụng đúng tài nguyên và quyền đã yêu cầu. Không dùng access key của broker làm credentials trong response binding.

~~~mermaid
flowchart LR
    P["Platform"] -->|"Platform credential"| B["Service broker"]
    B -->|"Broker workload identity"| I["IAM / Identity provider"]
    I -->|"Short-lived token"| B
    B -->|"Scoped provider API calls"| C["Cloud / Kubernetes provider"]
    B -->|"Binding-specific credential"| A["Consumer application"]
    A -->|"Use service instance"| R["Database / Cache / Service"]
~~~

Tách ba ranh giới này giúp giới hạn thiệt hại khi một credential bị lộ. Nếu password của một binding bị lộ, quyền của consumer đó có thể được thu hồi mà không cần xoay khóa quản trị provider. Nếu credential broker bị lộ, phạm vi tác động được giới hạn bởi IAM policy của broker.

## 2. Nguyên tắc least privilege cho broker

Least privilege nghĩa là danh tính broker chỉ có những quyền cần thiết để thực hiện nhiệm vụ được giao, trong đúng phạm vi tài nguyên và thời gian cần thiết.

Khi thiết kế quyền, cần trả lời bốn câu hỏi:

1. **Ai?** Workload hoặc thành phần nào thực hiện thao tác?
2. **Làm gì?** Tạo, đọc, cập nhật, xóa, gắn tag hay quản lý credential?
3. **Trên tài nguyên nào?** Account, project, namespace, region, resource type hoặc resource cụ thể nào?
4. **Trong bao lâu?** Credential tồn tại bao lâu, quyền có thể được cấp tạm thời hay không?

Không cấp quyền quản trị toàn bộ cloud account chỉ vì broker cần tạo một database. Hãy phân tích các thao tác thật sự cần trong từng vòng đời.

| Nghiệp vụ broker | Quyền provider có thể cần | Phạm vi nên giới hạn |
|---|---|---|
| Provision | Tạo resource, đọc trạng thái tạo, gắn metadata/tag | Resource type và account/project được broker quản lý |
| Fetch / kiểm tra trạng thái | Đọc metadata và trạng thái resource | Resource thuộc instance đã lưu |
| Update | Thay đổi các thuộc tính được hỗ trợ | Resource và field được phép cập nhật |
| Deprovision | Xóa resource hoặc giải phóng allocation | Resource do broker sở hữu |
| Bind | Tạo principal, role hoặc credential dành cho consumer | Một service instance hoặc database cụ thể |
| Unbind | Thu hồi principal hoặc credential của binding | Đúng principal do binding tạo |
| Reconciliation | Đọc trạng thái, tìm resource có marker của broker | Account/project và tag/namespace được broker quản lý |
| Secret management | Tạo, đọc, rotate hoặc xóa secret | Đường dẫn secret theo provider và binding |

Một quyền chỉ cần cho reconciliation không nhất thiết phải cho phép xóa resource. Tách quyền đọc và quyền thay đổi giúp broker có thể chạy tác vụ kiểm tra với danh tính hạn chế hơn.

### Không dùng quyền wildcard theo thói quen

Các quyền như wildcard, Administrator, Owner, cluster-admin hoặc quyền đọc mọi secret thường vượt xa nhu cầu. Chỉ dùng quyền rộng khi provider không có cơ chế giới hạn chi tiết và đã đánh giá rõ lý do, phạm vi cùng biện pháp bù trừ.

Nếu provider API yêu cầu quyền đọc danh sách ở phạm vi account để tìm tài nguyên, hãy giới hạn quyền đó trong account/project chuyên dụng và lọc kết quả bằng metadata do broker quản lý. Không mở rộng quyền xóa hoặc ghi chỉ để giải quyết một truy vấn đọc.

## 3. Lập ma trận quyền trước khi cấu hình IAM

Trước khi tạo IAM policy hoặc Kubernetes Role, hãy liệt kê thao tác mà provider adapter thực hiện. Ma trận giúp phát hiện quyền thừa và hỗ trợ review bảo mật.

Ví dụ cho broker quản lý PostgreSQL:

| Tác vụ adapter | Cần thực hiện | Không cần mặc định |
|---|---|---|
| Tạo database instance | Tạo database resource và gắn tag broker | Sửa IAM policy của account |
| Kiểm tra provision | Đọc trạng thái operation/resource | Đọc dữ liệu ứng dụng trong database |
| Tăng storage | Sửa thông số storage của resource được quản lý | Thay đổi network của mọi resource |
| Tạo binding | Tạo database role/user có quyền theo binding | Tạo user quản trị cloud |
| Thu hồi binding | Disable/drop đúng role/user | Xóa database instance |
| Deprovision | Xóa resource thuộc instance đã xác minh | Xóa resource không có marker của broker |
| Reconciliation | Đọc resource và đối chiếu tag/ID | Liệt kê secret của tenant khác |

Từ ma trận này, tạo policy theo nguyên tắc:

- Tách quyền control plane của cloud khỏi quyền data plane của database.
- Tách thao tác instance khỏi thao tác binding nếu có thể.
- Chỉ cho phép region, project, namespace và resource type đã được phê duyệt.
- Dùng tag/label có nguồn gốc từ broker để xác định resource do broker sở hữu.
- Không cho request parameters quyết định policy, role hoặc account mà broker sẽ sử dụng.
- Review lại policy khi thêm tính năng provider mới hoặc thay đổi vòng đời service.

## 4. Ưu tiên workload identity và credential ngắn hạn

Cách an toàn thường là để broker chứng minh danh tính bằng môi trường runtime, sau đó nhận token ngắn hạn từ identity provider. Nhờ vậy, ứng dụng không cần mang theo access key dài hạn trong file cấu hình.

| Hạ tầng | Cơ chế nên xem xét | Cách hoạt động |
|---|---|---|
| AWS | IAM role cho workload, EKS Pod Identity hoặc IRSA | Pod/compute workload nhận temporary credentials gắn với IAM role |
| Google Cloud | Workload Identity Federation hoặc service account impersonation | Workload chứng minh danh tính bên ngoài để nhận token của service account |
| Azure | Managed Identity / workload identity | Workload lấy token từ Microsoft Entra ID mà không lưu client secret dài hạn |
| Kubernetes | ServiceAccount token ngắn hạn và RBAC | Pod dùng danh tính Kubernetes để gọi API server trong namespace/phạm vi được cấp |
| Hệ thống on-premises | Vault hoặc identity broker | Workload xác thực với hệ thống cấp credential để nhận secret/token theo policy |

Credential ngắn hạn giảm thời gian sử dụng được nếu bị lộ. Broker nên yêu cầu token có audience và scope phù hợp, không nhận token có quyền rộng hơn nhu cầu của provider adapter.

### Luồng cấp token

~~~mermaid
sequenceDiagram
    participant W as Broker workload
    participant ID as Identity provider
    participant IAM as IAM policy
    participant API as Provider API

    W->>ID: Chứng minh workload identity
    ID->>IAM: Kiểm tra role và policy
    IAM-->>ID: Quyền được cấp
    ID-->>W: Short-lived access token
    W->>API: Gọi API với token
    API->>IAM: Đánh giá action/resource
    IAM-->>API: Allow hoặc deny
    API-->>W: Kết quả thao tác
~~~

Token có thời hạn hết hiệu lực. Provider client hoặc credential provider cần làm mới trước thời điểm hết hạn với một khoảng đệm, có jitter để nhiều replica không refresh cùng lúc. Không cache token vô thời hạn hoặc giả định token vẫn hợp lệ sau khi workload identity bị thu hồi.

## 5. Khi nào phải dùng static credential?

Một số provider hoặc môi trường cũ chưa hỗ trợ workload identity. Khi đó, broker có thể phải dùng client secret, API key hoặc access key. Đây nên là phương án có kiểm soát:

- Lưu secret trong Vault, cloud secret manager hoặc hệ thống quản lý secret chuyên dụng.
- Chỉ cấp quyền đọc secret cho service identity của broker.
- Tách secret theo môi trường và provider account.
- Đặt thời hạn, rotation schedule và quy trình thu hồi.
- Không commit secret vào Git, Docker image, Helm values hoặc file cấu hình chia sẻ.
- Không truyền secret qua query string, log, tracing hoặc thông báo lỗi.
- Có thể cấp credential riêng cho từng provider account hoặc nhóm tenant.
- Theo dõi lần sử dụng cuối, ngày tạo và ngày hết hạn.

Không nên đặt giá trị secret trực tiếp trong application.yml. File cấu hình chỉ nên chứa chế độ xác thực và tham chiếu tới secret:

~~~yaml
broker:
  providers:
    primary:
      type: aws
      region: ap-southeast-1
      credential-mode: workload-identity
    legacy:
      type: external-api
      credential-mode: secret-manager
      secret-reference: secret://broker/providers/legacy-api
~~~

Đoạn cấu hình trên chỉ chứa metadata và secret reference. Không đặt access key, client secret hoặc password thật vào YAML. Giá trị secret được lấy ở runtime từ hệ thống được phân quyền.

## 6. Tổ chức lớp credential trong Spring

Không nên để mỗi provider adapter tự đọc environment variable hoặc tự giải mã secret. Hãy định nghĩa abstraction để các adapter nhận credential theo provider/account đã được broker lựa chọn.

Ví dụ mô hình:

~~~java
import java.time.Instant;
import reactor.core.publisher.Mono;

public record ProviderTarget(
        String providerId,
        String accountReference,
        String region
) {
}

public record ProviderSession(
        String accessToken,
        Instant expiresAt
) {
}

public interface ProviderCredentialProvider {

    Mono<ProviderSession> acquire(ProviderTarget target);
}
~~~

**ProviderTarget** chứa tham chiếu account đã được broker xác thực. **ProviderSession** đại diện cho token và thời điểm hết hạn. Implementation có thể lấy token qua workload identity, SDK credential chain hoặc secret manager.

Ví dụ service dùng credential provider:

~~~java
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ProviderProvisioningGateway {

    private final ProviderCredentialProvider credentialProvider;
    private final ProviderApiClient providerApiClient;

    public ProviderProvisioningGateway(
            ProviderCredentialProvider credentialProvider,
            ProviderApiClient providerApiClient) {
        this.credentialProvider = credentialProvider;
        this.providerApiClient = providerApiClient;
    }

    public Mono<ProviderResult> provision(
            ProviderTarget target,
            ProvisionCommand command) {

        return credentialProvider.acquire(target)
                .flatMap(session -> providerApiClient.createResource(
                        target,
                        session.accessToken(),
                        command));
    }
}
~~~

Đây là ví dụ kiến trúc rút gọn; các kiểu ProviderApiClient, ProvisionCommand và ProviderResult thuộc domain của ứng dụng. Trong hệ thống thật, token nên được giữ trong memory trong thời gian cần thiết, không đưa vào log hoặc exception. Nếu SDK provider đã hỗ trợ credential refresh, ưu tiên sử dụng credential chain chính thức của SDK thay vì tự viết cơ chế ký request.

### Tách cấu hình không bí mật khỏi credential

Có thể dùng **@ConfigurationProperties** để bind provider ID, region, account reference và credential mode. Credential provider sẽ chịu trách nhiệm lấy token khi cần.

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "broker.providers.primary")
public record ProviderProperties(
        String type,
        String region,
        String accountReference,
        String credentialMode,
        String secretReference
) {
}
~~~

Không thêm trường accessKey, secretKey hoặc password vào properties object dùng chung nếu không có yêu cầu cụ thể. Nếu bắt buộc bind secret từ secret manager, hãy dùng type và lifecycle có kiểm soát, hạn chế log object và tránh đưa giá trị bí mật vào actuator endpoint.

## 7. Phân quyền theo tài nguyên và theo tenant

Một broker có thể quản lý tài nguyên cho nhiều organization hoặc tenant. Không nên cho caller tự gửi account ID, role ARN, project ID hoặc Kubernetes namespace rồi broker sử dụng trực tiếp.

Thay vào đó, broker duy trì mapping đã được quản trị:

~~~mermaid
flowchart TD
    A["Authenticated tenant"] --> B["Tenant-to-provider mapping"]
    B --> C["Provider account reference"]
    B --> D["Allowed regions and plans"]
    B --> E["Namespace and resource policy"]
    C --> F["Credential provider"]
    D --> F
    E --> F
    F --> G["Short-lived provider session"]
~~~

Ví dụ mapping nội bộ:

| Tenant đã xác thực | Provider account reference | Region | Namespace |
|---|---|---|---|
| org-001 | cloud-account-a | ap-southeast-1 | broker-org-001 |
| org-002 | cloud-account-b | ap-southeast-2 | broker-org-002 |

Giá trị tenant phải đến từ danh tính hoặc context đã được broker xác minh. Không tin một field organization trong parameters nếu chưa ràng buộc với caller. Việc chọn account và namespace phải qua policy phía server.

Các mô hình cách ly có thể gồm:

- **Một account riêng cho mỗi tenant:** cách ly tốt, nhưng tăng chi phí vận hành.
- **Một account cho một nhóm tenant:** cân bằng giữa cách ly và quản lý.
- **Một account chung với resource boundary:** cần policy chặt, tag/label bắt buộc và kiểm tra ownership trước mọi thao tác.
- **Một role được assume theo tenant:** broker dùng workload identity gốc để nhận role giới hạn cho account hoặc tenant đã được ánh xạ.

Dù chọn mô hình nào, không cho phép tenant tự chọn credential của provider hoặc chỉ định một role bất kỳ trong request OSB API.

## 8. Ví dụ least privilege trên Kubernetes

Nếu provider là Kubernetes API, broker thường cần tạo và quản lý một số resource trong namespace được chỉ định. Hãy dùng **Role** và **RoleBinding** theo namespace thay vì cấp **cluster-admin** cho ServiceAccount của broker.

Ví dụ Role giới hạn trong namespace chuyên dụng:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: service-broker-resource-manager
  namespace: broker-org-001
rules:
  - apiGroups: [""]
    resources: ["services", "configmaps", "persistentvolumeclaims"]
    verbs: ["get", "list", "watch", "create", "patch", "delete"]
  - apiGroups: ["apps"]
    resources: ["deployments", "statefulsets"]
    verbs: ["get", "list", "watch", "create", "patch", "delete"]
~~~

Gắn Role với ServiceAccount của broker trong cùng namespace:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: service-broker-resource-manager
  namespace: broker-org-001
subjects:
  - kind: ServiceAccount
    name: service-broker
    namespace: broker-system
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: service-broker-resource-manager
~~~

RoleBinding trong ví dụ có thể tham chiếu ServiceAccount ở namespace khác. Role vẫn giới hạn quyền được cấp trong namespace **broker-org-001**. Cần kiểm tra chính xác namespace và resource type mà adapter thực sự sử dụng.

Nếu broker cần quản lý Kubernetes Secret, hãy bổ sung quyền tối thiểu cho đúng use case. Quyền **list** hoặc **watch** trên secrets có thể cho phép đọc nhiều secret trong namespace; không thêm các verb đó chỉ để tiện debug. Kubernetes RBAC cũng không thể giới hạn quyền create bằng resourceNames theo cách mà nhiều người thường kỳ vọng. Có thể cần namespace riêng, admission policy hoặc external secret controller để giới hạn phạm vi.

ServiceAccount của broker nên có automountServiceAccountToken và projected token được cấu hình theo yêu cầu của cluster. Nếu broker không cần gọi Kubernetes API từ một pod cụ thể, không cần mount token vào container đó. Không cấp ClusterRoleBinding rộng chỉ vì broker cần tạo tài nguyên trong một namespace.

## 9. Ví dụ quyền trên cloud provider

Với AWS, Google Cloud hoặc Azure, nên dùng IAM role, service account hoặc managed identity gắn với workload. Policy cần giới hạn theo resource type, account/project, region, tag hoặc resource group mà provider hỗ trợ.

Một policy review cho broker quản lý database nên xem xét riêng:

| Nhóm quyền | Câu hỏi review |
|---|---|
| Create | Có chỉ tạo được database resource thuộc service broker không? |
| Read | Có cần đọc mọi database trong account hay chỉ resource được quản lý? |
| Modify | Có giới hạn thuộc tính update và phạm vi resource không? |
| Delete | Có yêu cầu tag/ownership trước khi xóa không? |
| Identity | Broker có cần tạo IAM user/role hay chỉ database principal? |
| Pass/impersonate role | Có thể giới hạn role được ủy quyền cụ thể không? |
| Secret access | Có chỉ đọc secret prefix hoặc secret ID của broker không? |
| Network | Có cần sửa security group/firewall không, và phạm vi nào? |

Không cấp quyền sửa IAM, network hoặc secret chỉ vì chúng có thể hữu ích trong tương lai. Khi tính năng mới cần quyền mới, cập nhật policy cùng thay đổi code và review như một phần của release.

## 10. Quản lý secret và rotation

Credential dài hạn cần được thay trước khi hết hạn hoặc ngay khi có dấu hiệu bị lộ. Rotation phải phối hợp giữa identity provider, broker runtime và provider adapter để tránh gián đoạn thao tác.

### Rotation cho credential ngắn hạn

Với workload identity và token ngắn hạn:

1. Theo dõi thời điểm hết hạn của token.
2. Làm mới trước hạn với một khoảng đệm.
3. Thêm jitter để các replica không refresh đồng thời.
4. Nếu refresh thất bại, retry có giới hạn và phân loại lỗi.
5. Không tiếp tục dùng token đã hết hạn.
6. Theo dõi tỷ lệ refresh lỗi và thời gian còn lại của token.

### Rotation cho API key hoặc client secret dài hạn

Với provider chỉ hỗ trợ static secret, dùng quy trình thay thế có overlap nếu provider cho phép:

1. Tạo credential mới với cùng phạm vi quyền tối thiểu.
2. Lưu phiên bản mới vào secret manager.
3. Cập nhật broker để đọc phiên bản mới hoặc refresh secret reference.
4. Kiểm tra một thao tác provider không gây side effect để xác nhận credential mới hoạt động.
5. Chuyển toàn bộ replica sang credential mới.
6. Theo dõi lỗi xác thực và xác nhận không còn request dùng credential cũ.
7. Thu hồi credential cũ.
8. Ghi audit record về người thực hiện, thời điểm và phiên bản.

Nếu provider không hỗ trợ hai credential đồng thời, cần kế hoạch rotation có cửa sổ bảo trì và khả năng rollback. Không xóa credential cũ trước khi xác nhận broker đã chuyển sang credential mới.

### Cache và refresh

Không cache secret vô thời hạn. Cache nên có TTL ngắn, gắn với expiry của token và có cơ chế invalidation khi secret version thay đổi. Với nhiều replica, tránh để tất cả replica cùng refresh bằng một nhịp; dùng jitter hoặc refresh coordination nếu cần.

Không ghi giá trị token vào metric label, log, trace attribute hoặc exception message. Chỉ ghi provider ID, account reference đã được mask, credential version, expiry bucket và kết quả refresh.

## 11. Xử lý credential bị từ chối hoặc provider không khả dụng

Provider call có thể thất bại vì token hết hạn, policy bị thu hồi, account bị khóa, quota hoặc provider API tạm lỗi. Không nên gom tất cả thành một lỗi provision chung.

| Nhóm lỗi | Cách xử lý |
|---|---|
| Token hết hạn | Refresh token/credential rồi retry một lần nếu thao tác an toàn |
| Permission denied | Không retry liên tục; ghi nhận action/resource bị từ chối và báo vận hành |
| Account hoặc role bị vô hiệu hóa | Dừng thao tác, cảnh báo cấu hình identity |
| Secret manager timeout | Retry có giới hạn, giữ operation ở trạng thái chưa kết luận |
| Provider throttling | Backoff có jitter và tôn trọng retry-after nếu có |
| Provider 5xx hoặc network timeout | Kiểm tra idempotency/provider operation trước khi retry |
| Resource không thuộc broker | Không xóa hoặc sửa; yêu cầu reconciliation/manual review |
| Policy thay đổi giữa operation | Xác minh quyền hiện tại trước side effect tiếp theo |

Khi provider trả permission denied, không tự động xin quyền rộng hơn. Hãy xác định action và resource cụ thể bị từ chối, sau đó cập nhật IAM policy qua quy trình quản trị có review.

Nếu timeout xảy ra sau khi provider có thể đã thực hiện thao tác, hãy tra cứu provider operation ID hoặc resource marker trước khi gửi lại. Retry một lệnh tạo tài nguyên mà không có idempotency có thể tạo resource trùng.

## 12. Audit và quan sát việc sử dụng quyền

Mọi provider call quan trọng nên có audit context để trả lời được workload nào đã thực hiện thao tác, trên account nào và vì sao.

Một audit event có thể ghi:

| Trường | Ví dụ |
|---|---|
| actor | broker-service-account |
| tenant reference | org-001 đã được xác minh |
| provider | aws / gcp / azure / kubernetes |
| account reference | cloud-account-a |
| operation ID | op-123 |
| service instance ID | instance-100 |
| action | CreateDatabase |
| resource reference | resource-9a8f |
| credential mode | workload-identity |
| credential version | version-12 |
| result | allowed / denied / success / failure |
| timestamp | Thời điểm thực hiện |
| correlation ID | ID liên kết log giữa các thành phần |

Không ghi access token, client secret, private key, password hoặc toàn bộ HTTP Authorization header. Nếu cần liên kết với một credential, chỉ ghi secret version hoặc fingerprint không thể dùng để khôi phục secret.

Các metric hữu ích:

- Số provider request theo action và kết quả.
- Số lỗi permission denied theo provider/account.
- Tỷ lệ token refresh thành công.
- Số credential sắp hết hạn.
- Số provider call dùng static credential.
- Số resource bị từ chối do không xác minh được ownership.
- Số thao tác bị dừng do policy hoặc account mapping.

Cảnh báo nên hướng tới sự kiện có thể hành động, ví dụ token refresh thất bại liên tục, credential sắp hết hạn hoặc một action mới bị IAM từ chối sau khi deploy.

## 13. Kiểm thử credential provider và least privilege

Kiểm thử không chỉ xác minh provider call thành công. Cần chứng minh broker không thể thực hiện những thao tác ngoài quyền đã cấp.

| Kiểm thử | Kết quả mong đợi |
|---|---|
| Broker lấy token từ workload identity | Không cần static secret trong cấu hình |
| Token gần hết hạn | Credential provider refresh trước khi hết hạn |
| Token hết hạn | Không gửi request bằng token cũ |
| Policy cho phép create trong account A | Tạo resource trong account A thành công |
| Request chọn account không nằm trong mapping | Bị từ chối trước provider call |
| Action không có trong IAM policy | Provider trả permission denied, broker không mở rộng quyền |
| Resource không có tag/label ownership | Không cho update/delete |
| Tenant A yêu cầu resource tenant B | Authorization thất bại |
| Secret reference không tồn tại | Operation báo lỗi có kiểm soát, không log secret |
| Rotation sang secret version mới | Broker dùng version mới trước khi revoke version cũ |
| Kubernetes Role chỉ ở một namespace | Không truy cập resource namespace khác |
| Kubernetes broker không cần đọc Secret | Không có quyền list/watch secrets |
| Log và trace | Không xuất hiện token hoặc secret plaintext |
| Provider timeout sau create | Reconciliation tránh tạo resource trùng |

Nên có unit test cho credential provider, integration test với IAM sandbox hoặc cluster test và policy test để xác minh cả quyền được phép lẫn quyền bị từ chối. Mock một provider client luôn trả success không chứng minh least privilege đang hoạt động.

## 14. Quy trình triển khai cho một provider mới

Khi thêm AWS, Google Cloud, Azure, Kubernetes hoặc provider nội bộ, hãy thực hiện theo trình tự:

1. Liệt kê resource mà offering sẽ tạo, update, đọc và xóa.
2. Viết ma trận action/resource cho từng operation.
3. Chọn workload identity hoặc cơ chế credential ngắn hạn nếu provider hỗ trợ.
4. Tạo account/project/namespace hoặc role chuyên dụng cho broker.
5. Viết policy giới hạn action, resource, region và tenant scope.
6. Thiết kế mapping tenant đã xác thực sang provider account reference.
7. Tạo ProviderCredentialProvider và provider adapter riêng.
8. Đưa secret vào secret manager; cấu hình Spring chỉ giữ metadata và reference.
9. Thiết lập refresh, rotation, audit và alert.
10. Kiểm thử permission allow/deny, tenant isolation, token expiry và resource ownership.
11. Triển khai theo môi trường dev/staging trước production.
12. Review policy định kỳ và thu hồi quyền không còn được code sử dụng.

Khi thay đổi provider adapter, hãy cập nhật ma trận quyền và policy cùng thay đổi chức năng. Không đợi tới lúc production báo permission denied mới cấp một role quản trị rộng để khắc phục nhanh.

## 15. Checklist review bảo mật

Trước khi đưa broker kết nối provider vào production, kiểm tra:

- Platform credential, provider credential và binding credential được tách biệt.
- Broker chạy bằng workload identity hoặc credential ngắn hạn khi có thể.
- Không có secret plaintext trong Git, image, log, trace hoặc application YAML.
- IAM policy chỉ cấp action cần thiết cho đúng resource/account/region.
- Quyền tạo, sửa, xóa và đọc được review riêng.
- Tenant-to-account mapping do broker quản lý và được xác minh.
- Provider resource có tag/label để xác định ownership.
- Kubernetes dùng Role/RoleBinding theo namespace, không cấp cluster-admin tùy tiện.
- Token và secret có expiry, rotation, invalidation và audit.
- Permission denied không dẫn tới tự động mở rộng quyền.
- Retry provider call có idempotency và reconciliation.
- Test chứng minh cả allow và deny path.
- Có alert cho credential expiry, refresh failure và permission drift.

## Kết luận

Broker cần một danh tính riêng để quản lý tài nguyên ở provider, với quyền vừa đủ cho provision, update, bind, unbind, deprovision và reconciliation. Hãy tách credential của platform, broker và consumer; ưu tiên workload identity cùng token ngắn hạn; lưu static secret trong secret manager; giới hạn IAM theo action, resource, account, region và tenant; đồng thời thiết kế rotation, audit và kiểm thử deny path. Trong Spring Cloud Service Broker, một **ProviderCredentialProvider** và provider adapter tách biệt giúp các thao tác hạ tầng sử dụng đúng danh tính, giảm quyền thừa và giữ credential ngoài luồng dữ liệu OSB API.

## Tài liệu tham khảo

- [Spring Boot Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — quản lý cấu hình ứng dụng và nguồn cấu hình bên ngoài.
- [AWS IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html) — least privilege, temporary credentials và workload roles.
- [Google Cloud Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation) — xác thực workload mà không cần service account key dài hạn.
- [Microsoft Entra Workload ID](https://learn.microsoft.com/en-us/entra/workload-id/workload-identity-federation) — federation và danh tính workload.
- [Kubernetes RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/) — Role, ClusterRole, RoleBinding và quyền API.
- [Kubernetes Service Accounts](https://kubernetes.io/docs/concepts/security/service-accounts/) — danh tính workload và token ServiceAccount.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) — lưu trữ, rotation, truy cập và audit secret.

