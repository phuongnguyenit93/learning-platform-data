# Phân biệt broker toàn nền tảng và broker giới hạn trong một space

Cloud Foundry cho phép đăng ký service broker ở phạm vi toàn nền tảng (global) hoặc giới hạn trong một space (space-scoped), tùy phiên bản và cấu hình của nền tảng. Phạm vi đăng ký quyết định broker được công bố và được gọi trong phạm vi nào. Đây là một quyết định về ranh giới quản trị, khả năng nhìn thấy catalog và quyền tạo service instance; nó không làm thay đổi bản chất của các thao tác Open Service Broker API (OSB API).

Với `SPRING_CLOUD_SERVICE_BROKER`, hiểu đúng hai phạm vi này giúp chọn cách triển khai broker, ánh xạ `organization_guid`/`space_guid`, giới hạn quyền truy cập và cô lập tài nguyên provider. Một broker global có thể phục vụ nhiều organization và space, nhưng từng service instance vẫn thuộc một space cụ thể. Một broker space-scoped chỉ được sử dụng trong space đã đăng ký; điều đó không có nghĩa tài nguyên hạ tầng phía sau tự động được cô lập nếu broker dùng chung provider account hoặc database.

## 1. Broker registration scope là gì?

Service broker là một ứng dụng cung cấp catalog và thực hiện các thao tác vòng đời service instance/binding thông qua OSB API. Cloud Foundry lưu thông tin đăng ký broker, bao gồm endpoint và thông tin xác thực mà platform dùng khi gọi broker.

Hai phạm vi đăng ký thường gặp:

- **Global service broker:** được đăng ký ở phạm vi toàn Cloud Foundry foundation. Catalog của broker có thể được cung cấp cho nhiều organization/space, tùy chính sách service access và cấu hình của platform.
- **Space-scoped service broker:** được gắn với một space cụ thể. Broker/catalog của đăng ký đó chỉ phục vụ phạm vi space được chỉ định; việc tạo service instance thông qua đăng ký này bị giới hạn trong space tương ứng theo khả năng của phiên bản platform.

Phạm vi này nói về đăng ký broker trong Cloud Foundry. Nó không đồng nghĩa với phạm vi của tài nguyên provider. Ví dụ, một broker space-scoped vẫn có thể gọi một AWS account dùng chung; nếu không có policy riêng, tài nguyên của nhiều space vẫn có thể nằm trong cùng account/project.

## 2. Global broker

Global broker phù hợp khi một nhóm platform hoặc đội vận hành trung tâm cung cấp dịch vụ cho nhiều organization và space. Broker được đăng ký một lần ở cấp foundation, sau đó platform có thể công bố service/plan theo chính sách truy cập.

Ví dụ:

```text
Cloud Foundry Foundation
|
+-- Organization: retail
|   +-- Space: dev
|   +-- Space: staging
|   +-- Space: prod
|
+-- Organization: analytics
|   +-- Space: notebooks
|   +-- Space: batch
|
+-- Global Service Broker: managed-postgresql
    +-- Catalog: postgres / small, standard, high-availability
```

Một global broker có thể cung cấp cùng một service cho nhiều space, nhưng phải xác định tenant và quota theo từng instance. Broker không được dùng một cấu hình mặc định toàn cục để cho phép mọi instance truy cập cùng một database hoặc credential.

### Ưu điểm

- Một lần đăng ký và một endpoint broker có thể phục vụ nhiều space.
- Quản lý catalog, plan, version và vận hành tập trung.
- Dễ áp dụng chuẩn logging, monitoring, audit, backup và policy ở cấp platform.
- Có thể chia sẻ năng lực provider và tối ưu chi phí vận hành nếu có quota/tenant isolation phù hợp.

### Trách nhiệm tăng thêm

- Mọi request phải được ràng buộc với organization/space sở hữu instance.
- Quota, billing, rate limit và giới hạn provider phải được tính theo tenant khi cần.
- Một lỗi cấu hình hoặc sự cố broker có thể ảnh hưởng nhiều organization.
- Catalog visibility cần phối hợp với service access của Cloud Foundry.
- Không được để một tenant đọc, bind, update hoặc xóa tài nguyên của tenant khác.

## 3. Space-scoped broker

Space-scoped broker phù hợp khi một đội phát triển hoặc đơn vị trong tổ chức cần cung cấp dịch vụ riêng cho một space, ví dụ một service nội bộ thử nghiệm, một integration chuyên biệt hoặc một broker do đội ứng dụng tự vận hành.

```text
Cloud Foundry Foundation
|
+-- Organization: product
    +-- Space: checkout
    |   +-- Space-scoped Broker: checkout-private-services
    |       +-- Catalog: checkout-cache, checkout-events
    |
    +-- Space: fulfillment
        +-- Space-scoped Broker: fulfillment-services
            +-- Catalog: fulfillment-queue
```

Space-scoped broker giúp thu hẹp phạm vi hiển thị và quản trị. Người dùng ở space khác không nên nhìn thấy catalog từ đăng ký này hoặc tạo instance qua đăng ký đó. Tuy vậy, broker vẫn cần xác thực platform, kiểm tra scope của đăng ký và quản lý tài nguyên provider đúng tenant.

### Ưu điểm

- Phạm vi sử dụng và blast radius nhỏ hơn một đăng ký global.
- Có thể phục vụ cấu hình, catalog hoặc provider integration riêng cho một space.
- Dễ giao trách nhiệm vận hành cho đội sở hữu space khi quy trình quản trị cho phép.
- Có thể áp dụng hạn mức, endpoint hoặc credential provider riêng cho space.

### Đánh đổi

- Có thể phát sinh nhiều đăng ký broker, endpoint, credential và quy trình rotation.
- Cập nhật catalog hoặc broker version có thể cần phối hợp nhiều space.
- Nếu mỗi space có một broker deployment riêng, chi phí vận hành và giám sát tăng.
- Space-scoped không tự tạo ranh giới mạng hoặc IAM ở provider; broker phải cấu hình các ranh giới đó.

## 4. So sánh global và space-scoped

| Tiêu chí | Global broker | Space-scoped broker |
|---|---|---|
| Phạm vi đăng ký | Toàn foundation | Một space được chỉ định |
| Catalog visibility | Có thể được nhiều organization/space sử dụng theo service access | Giới hạn trong space đăng ký theo khả năng platform |
| Quản trị | Thường tập trung ở platform team | Có thể giao cho đội sở hữu space theo quyền platform |
| Phân quyền tenant | Broker phải kiểm tra ranh giới giữa nhiều organization/space | Broker vẫn kiểm tra scope và quyền trong space đó |
| Blast radius | Rộng hơn | Hẹp hơn về phạm vi đăng ký |
| Vận hành | Ít đăng ký hơn, cần kiểm soát đa tenant tốt | Có thể nhiều đăng ký/credential hơn |
| Provider account | Có thể dùng chung hoặc tách theo tenant | Có thể dùng riêng cho space, nhưng không tự động được bảo đảm |
| Phù hợp | Dịch vụ nền tảng dùng chung, managed services tập trung | Dịch vụ riêng của space/đội hoặc integration giới hạn |

Không có lựa chọn nào an toàn mặc định. Global broker với tenant isolation tốt có thể an toàn hơn nhiều broker space-scoped dùng chung một provider credential quản trị rộng. Hãy đánh giá cả registration scope, identity, provider account, network boundary và quy trình vận hành.

## 5. Registration scope khác service access

Một điểm dễ nhầm là phạm vi đăng ký broker và quyền nhìn thấy service/plan là hai khái niệm khác nhau.

- **Broker registration scope** xác định broker được đăng ký ở cấp foundation hay gắn với một space.
- **Service access** kiểm soát organization nào được phép sử dụng service/plan do platform công bố, đặc biệt với global broker.
- **Service instance scope** xác định instance được tạo trong organization/space cụ thể.
- **Provider resource scope** xác định tài nguyên thật được tạo trong account, project, subscription, cluster hoặc namespace nào.

Ví dụ, global broker có thể đăng ký ở cấp foundation nhưng một plan chỉ được enable cho một số organization. Ngược lại, việc service/plan xuất hiện trong catalog không có nghĩa mọi user đều có quyền provision; quyền tạo instance còn phụ thuộc role và policy Cloud Foundry.

Với space-scoped broker, phạm vi catalog bị giới hạn theo space registration; không nên dùng service access của global broker như một cơ chế thay thế cho ranh giới space-scoped. Cách áp dụng service access và khả năng quản trị catalog có thể khác giữa các release Cloud Foundry, vì vậy cần xác nhận trên foundation mục tiêu.

## 6. Context organization và space trong OSB request

Khi Cloud Foundry gửi request vòng đời, broker cần biết service instance thuộc organization và space nào. Context có thể chứa thông tin như:

```json
{
  "platform": "cloudfoundry",
  "organization_guid": "org-123",
  "space_guid": "space-456"
}
```

Tùy phiên bản OSB API và platform, một số request có thể còn chứa các trường legacy như `organization_guid` hoặc `space_guid` ở vị trí riêng. Broker nên chuẩn hóa chúng vào một mô hình nội bộ, đồng thời xử lý trường hợp thiếu hoặc mâu thuẫn theo contract đã hỗ trợ.

Ví dụ model nội bộ:

```java
public record CloudFoundryScope(
        String foundationId,
        String organizationGuid,
        String spaceGuid,
        BrokerRegistrationScope registrationScope
) {}

public enum BrokerRegistrationScope {
    GLOBAL,
    SPACE
}
```

`foundationId` và `registrationScope` là metadata nội bộ của broker; không phải field OSB chuẩn bắt buộc. Nếu cùng một broker phục vụ nhiều Cloud Foundry foundation, cần thêm định danh foundation để tránh va chạm ID hoặc áp dụng nhầm policy giữa các môi trường.

### Kiểm tra scope cho global broker

Global broker phải chấp nhận nhiều space hợp lệ, nhưng mọi thao tác trên instance phải kiểm tra ownership:

1. Xác thực platform/broker registration gọi request.
2. Đọc instance record bằng `instance_id`.
3. So sánh organization/space context trong request với scope đã lưu khi provision.
4. Kiểm tra service ID, plan ID và tenant policy.
5. Chỉ thao tác trên external resource mapping thuộc instance đó.

Không dùng một `space_guid` duy nhất trong cấu hình toàn cục cho tất cả request. Context của từng instance phải được lưu riêng.

### Kiểm tra scope cho space-scoped broker

Space-scoped broker có thể biết space được gắn với đăng ký thông qua cấu hình/metadata đã được provision cho broker. Khi xử lý request:

- Xác minh `space_guid` của request khớp space đã đăng ký.
- Nếu có organization GUID, xác minh organization đó là parent hợp lệ của space.
- Từ chối request tham chiếu instance thuộc space khác.
- Không tin body context đơn lẻ nếu chưa xác thực caller và registration scope.
- Không cho phép caller sửa scope bằng cách gửi một GUID khác trong request.

Nếu platform không cung cấp đủ context để broker xác minh scope theo contract đang dùng, cần cấu hình adapter hoặc ranh giới đăng ký phù hợp; không tự suy đoán tenant từ tên service instance.

## 7. Catalog và service access trong thực tế

Catalog là danh sách service/plan mà broker công bố. Với global broker, catalog có thể chứa các service dùng chung cho toàn foundation, nhưng platform có thể bật/tắt service access theo organization để kiểm soát ai được sử dụng plan nào.

Ví dụ chính sách:

| Service/plan | Organization được phép | Mục đích |
|---|---|---|
| PostgreSQL small | `product`, `analytics` | Môi trường dev/test |
| PostgreSQL HA | `product` | Production workloads |
| Redis standard | `product`, `fulfillment` | Cache dùng chung theo quota |
| Internal event stream | `analytics` | Dịch vụ chuyên biệt |

Service access không nên được xem là authorization duy nhất ở broker. Broker vẫn cần kiểm tra context và policy khi provision/bind/update. Một user có thể nhìn thấy service trong catalog nhưng request vẫn phải tuân theo role, quota và policy của organization/space.

Đối với space-scoped broker, catalog nên chỉ chứa service thực sự phục vụ space đó. Không công bố một plan đòi hỏi provider account hoặc network scope mà broker không thể sử dụng trong space tương ứng.

## 8. Tác động tới vòng đời service instance

Dù broker global hay space-scoped, service instance trên Cloud Foundry vẫn được tạo trong một organization/space. Registration scope không biến service instance thành tài nguyên toàn cục.

Một vòng đời điển hình:

1. Platform đọc catalog và xác định service/plan có thể sử dụng.
2. User có quyền trong space gửi yêu cầu tạo service instance.
3. Cloud Foundry gọi broker provision với instance ID và context tương ứng.
4. Broker lưu organization/space scope cùng service/plan và external resource ID.
5. Platform gọi bind/unbind cho consumer thuộc phạm vi phù hợp.
6. Khi xóa service instance, platform gửi deprovision; broker kiểm tra scope đã lưu trước khi thu hồi provider resource.

Nếu instance được chuyển giữa space hoặc organization, không nên tự động cập nhật scope chỉ vì tên hiển thị thay đổi. Việc move service instance phụ thuộc khả năng của Cloud Foundry và loại service; nhiều trường hợp cần tạo instance mới, migrate dữ liệu/binding rồi deprovision instance cũ theo quy trình riêng.

## 9. Lưu scope và mapping trong broker database

Broker cần lưu registration scope và tenant context như một phần dữ liệu vòng đời:

| Trường nội bộ | Ý nghĩa |
|---|---|
| `foundation_id` | Cloud Foundry foundation đã gọi broker. |
| `registration_id` | Định danh đăng ký broker hoặc credential principal nội bộ. |
| `registration_scope` | `GLOBAL` hoặc `SPACE`. |
| `registered_space_guid` | Space được gắn với đăng ký nếu là space-scoped. |
| `organization_guid` | Organization sở hữu instance. |
| `space_guid` | Space sở hữu instance. |
| `service_instance_id` | Instance ID từ OSB API. |
| `provider_account_ref` | Reference tới provider account/project được chọn. |
| `external_resource_id` | ID tài nguyên provider. |

Không lưu broker password hoặc provider secret trực tiếp trong bảng này. Dùng secret manager và chỉ lưu credential reference hoặc principal ID cần thiết.

Nếu broker có nhiều registration trỏ về cùng endpoint, cần xác định request thuộc registration nào. Có thể dùng credential principal, endpoint riêng hoặc metadata được platform cung cấp theo thiết kế tích hợp. Không suy ra registration từ `space_guid` trong body mà bỏ qua authentication.

## 10. Thiết kế Spring Cloud Service Broker cho hai phạm vi

Nên giữ domain service dùng chung và đưa khác biệt global/space-scoped vào policy/resolver. Ví dụ:

```java
public interface RegistrationScopeResolver {
    Mono<ResolvedBrokerScope> resolve(AuthenticatedBrokerClient client,
                                      ProvisionCommand command);
}

public record ResolvedBrokerScope(
        String foundationId,
        String registrationId,
        BrokerRegistrationScope scope,
        String registeredSpaceGuid,
        String organizationGuid,
        String spaceGuid
) {}
```

Resolver có thể:

- Xác định broker registration dựa trên authenticated client/endpoint.
- Với global scope, chấp nhận space hợp lệ và kiểm tra tenant policy.
- Với space scope, yêu cầu `spaceGuid` trùng registered space.
- Xác minh organization parent và các giới hạn service/plan.
- Trả một scope object đã chuẩn hóa để provision service layer dùng.

Ví dụ kiểm tra scope:

```java
public void validateRegistrationScope(
        ResolvedBrokerScope scope,
        String requestSpaceGuid
) {
    if (scope.scope() == BrokerRegistrationScope.SPACE
            && !scope.registeredSpaceGuid().equals(requestSpaceGuid)) {
        throw new BrokerScopeViolationException();
    }
}
```

Đây là ví dụ đơn giản. Trong production cần xử lý null, xác minh organization/space relation, foundation identity và authentication principal. Không lấy `requestSpaceGuid` từ dữ liệu không được xác thực rồi coi nó là bằng chứng quyền truy cập.

### Một endpoint hay nhiều endpoint?

Có thể triển khai một ứng dụng broker dùng chung cho nhiều registration, hoặc nhiều deployment/endpoint theo space. Lựa chọn phụ thuộc cách Cloud Foundry quản lý registration, khả năng phân biệt credential principal và yêu cầu cô lập.

- **Một endpoint dùng chung:** giảm số deployment, nhưng cần resolver xác định registration và scope chính xác cho từng request.
- **Endpoint riêng theo space:** ranh giới mạng/configuration rõ hơn, nhưng tăng số deployment, certificate, credential và công việc nâng cấp.
- **Một deployment với nhiều broker registrations:** cần mapping credential/registration tới scope và catalog tương ứng, tránh trả catalog của space A cho registration của space B.

Không nên giả định chỉ vì URL giống nhau thì mọi registration có cùng catalog hoặc quyền. Registration identity vẫn phải được phân biệt.

## 11. Chọn provider account và ranh giới tài nguyên

Global broker có thể dùng một provider account chung hoặc chọn account/project theo organization, space, environment và plan. Space-scoped broker có thể dùng account riêng cho space, nhưng đó là quyết định kiến trúc của broker chứ không phải hệ quả tự động của Cloud Foundry scope.

| Mô hình provider | Khi phù hợp | Yêu cầu kiểm soát |
|---|---|---|
| Một account chung | Provider hỗ trợ quota, IAM và tag isolation tốt | Phân quyền theo resource, ownership tags, quota tenant và audit. |
| Account/project theo organization | Organization cần ranh giới chi phí hoặc IAM | Mapping org → account phải được quản lý và kiểm tra quyền. |
| Account/project theo space | Yêu cầu cô lập mạnh hoặc môi trường riêng | Quản lý nhiều credential/account và vòng đời mapping. |
| Credential theo service/plan | Plan có quyền provider khác nhau | Secret rotation, least privilege và không trộn credential giữa plan. |

Không dùng provider credential quản trị toàn quyền chỉ vì broker global cần phục vụ nhiều tenant. Ưu tiên workload identity hoặc credential giới hạn theo account/project/resource. Với space-scoped broker, cũng không nên dùng credential của space khác do copy nhầm cấu hình.

## 12. Bảo mật broker global và space-scoped

### Global broker

- Xác thực platform registration và nhận diện foundation/registration.
- Lưu organization/space context riêng cho từng instance.
- Kiểm tra ownership ở mọi thao tác retrieval, update, bind, unbind và deprovision.
- Áp dụng quota/rate limit theo organization/space để một tenant không chiếm hết capacity.
- Tách provider credentials hoặc role theo tenant khi cần.
- Ghi audit có instance ID, organization/space, operation ID nhưng không ghi secret.
- Kiểm tra catalog/service access không bị nhầm với quyền gọi API.

### Space-scoped broker

- Gắn registration với đúng space đã được platform xác nhận.
- Từ chối request có context thuộc space khác.
- Giới hạn provider account/project và network theo chính sách của space.
- Không cho broker dùng chung credential quản trị rộng hơn mức cần thiết.
- Theo dõi owner/role quản trị registration và quy trình thu hồi khi space bị xóa.
- Bảo đảm service instance/binding không tồn tại ngoài phạm vi registration.

Trong cả hai mô hình, `organization_guid` và `space_guid` là context để kiểm tra phạm vi; chúng không phải secret và cũng không phải credential xác thực. Caller phải được xác thực trước, sau đó broker mới dùng context để authorization.

## 13. Vận hành và quản trị vòng đời registration

Registration broker có vòng đời riêng với service instance:

- Tạo registration và cấu hình endpoint/credential.
- Kiểm tra kết nối và catalog.
- Bật service/plan access theo chính sách.
- Rotate broker credentials và chứng chỉ TLS.
- Cập nhật endpoint/catalog khi phát hành phiên bản mới.
- Ngừng service access hoặc gỡ registration theo quy trình migration.

Trước khi xóa global broker, cần xác định mọi organization/space đang sử dụng service instance và binding do broker quản lý. Trước khi xóa space-scoped broker, cần xử lý các instance/binding trong space đó. Xóa registration không nhất thiết đồng nghĩa provider resource đã được deprovision; broker và platform cần có quy trình chuyển giao hoặc cleanup rõ ràng.

Không xóa broker endpoint hoặc thu hồi credential trước khi platform đã hoàn tất các thao tác vòng đời cần thiết, trừ khi đang xử lý sự cố bảo mật khẩn cấp. Nếu cần ngừng dịch vụ, có thể dừng cấp mới trước, thông báo người dùng, migrate hoặc deprovision instance, rồi mới gỡ registration.

## 14. Tích hợp Cloud Foundry và kiểm tra phiên bản

Các khả năng space-scoped broker, API quản trị registration và lệnh CLI phụ thuộc phiên bản Cloud Foundry foundation và CLI được cài đặt. Vì vậy, khi triển khai cần xác minh:

1. Foundation đang chạy release nào và có hỗ trợ space-scoped broker không.
2. API/CLI version hiện tại cho phép tạo registration global hay space-scoped bằng cách nào.
3. Role nào được phép đăng ký, cập nhật hoặc xóa broker trong phạm vi đó.
4. Catalog visibility và service access được áp dụng ra sao cho loại registration.
5. Context nào được gửi trong provision/bind/update và cách platform biểu diễn organization/space.
6. Platform retry và polling async theo phiên bản OSB API nào.

Không sao chép cú pháp CLI/API từ một release khác mà chưa kiểm tra. Tên lệnh, flag và endpoint quản trị có thể thay đổi theo phiên bản; bài học này tập trung vào semantics của phạm vi đăng ký và ranh giới bảo mật.

## 15. Kiểm thử global và space-scoped

Nên có test riêng cho từng phạm vi:

| Ca kiểm thử | Global broker | Space-scoped broker |
|---|---|---|
| Request trong space hợp lệ | Chấp nhận nếu service access và authorization cho phép | Chấp nhận nếu đúng registered space |
| Request từ space khác | Chỉ chấp nhận nếu registration/service access/tenant policy cho phép | Từ chối |
| Organization không khớp parent space | Từ chối | Từ chối |
| Cùng instance ID ở foundation khác | Phân biệt theo foundation/registration nếu broker phục vụ nhiều foundation | Phân biệt theo foundation/registration |
| Catalog visibility | Kiểm tra service access theo organization | Chỉ hiển thị trong space được gắn |
| Provider account mapping | Chọn đúng account theo tenant/plan | Không dùng account của space khác |
| Deprovision | Chỉ xóa resource thuộc instance/tenant | Chỉ xóa resource thuộc registered space |
| Credential rotation | Không làm ảnh hưởng tenant ngoài phạm vi thay đổi | Chỉ rotate credential của registration/space tương ứng |

Các kiểm thử quan trọng khác:

- Caller không xác thực không thể gọi `/v2/**`.
- Request có `space_guid` giả mạo không vượt qua scope validation.
- Binding ID của instance khác không thể được sử dụng để truy cập credential.
- Global broker không trả dữ liệu instance của organization khác.
- Space-scoped broker không provision hoặc bind cho space khác.
- Retry provision không tạo resource provider trùng.
- Catalog của registration này không bị lẫn với registration khác dùng chung endpoint.
- Log/audit có scope và operation ID nhưng không chứa broker/provider secret.

## 16. Checklist lựa chọn mô hình

Chọn **global broker** khi:

- Dịch vụ được platform team vận hành tập trung cho nhiều organization/space.
- Có khả năng xác thực và authorization tenant rõ ràng.
- Có quota, rate limit, audit và provider resource mapping đa tenant.
- Muốn quản lý catalog và release tập trung.

Chọn **space-scoped broker** khi:

- Dịch vụ chỉ phục vụ một space hoặc một nhóm workload giới hạn.
- Cần catalog hoặc integration riêng cho space.
- Quy trình quản trị cho phép đội sở hữu space quản lý broker registration.
- Có thể vận hành credential, endpoint và provider account trong phạm vi riêng.

Trước khi quyết định, hãy trả lời:

- Ai sở hữu broker và chịu trách nhiệm vận hành?
- Ai được nhìn thấy catalog và plan?
- Broker được gọi từ những space nào?
- Provider account/project có dùng chung không?
- Scope được xác minh từ authentication principal và registration metadata ra sao?
- Khi space/org bị xóa, ai cleanup instance, binding và provider resource?
- Cần bao nhiêu endpoint/registration/credential để đáp ứng yêu cầu cô lập?

## 17. Kết luận

Global và space-scoped mô tả hai phạm vi đăng ký service broker trong Cloud Foundry. Global broker tập trung cung cấp catalog và quản lý dịch vụ cho nhiều organization/space; space-scoped broker giới hạn đăng ký và khả năng sử dụng vào một space. Service access, quyền người dùng, ownership của service instance và provider resource scope là các lớp riêng cần được thiết kế đồng bộ.

Với Spring Cloud Service Broker, hãy chuẩn hóa foundation/registration identity cùng organization/space context, xác thực caller trước khi kiểm tra scope, lưu ownership vào từng instance và binding, rồi chọn provider account theo policy. Khi làm rõ các ranh giới này, broker có thể phục vụ đúng phạm vi, tránh truy cập chéo tenant và quản lý vòng đời tài nguyên nhất quán dù được đăng ký global hay space-scoped.
