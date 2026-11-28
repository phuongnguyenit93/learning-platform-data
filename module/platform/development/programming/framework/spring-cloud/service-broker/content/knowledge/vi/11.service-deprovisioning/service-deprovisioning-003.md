# Xác minh service_id, plan_id và quyền sở hữu trước khi xóa

## Mục tiêu và bối cảnh

Khi platform gửi yêu cầu deprovision, service broker nhận lệnh thu hồi một service instance đã được tạo trước đó. Đây là thao tác có tác động lớn: broker có thể xóa database, bucket, queue, volume, tài khoản truy cập hoặc các tài nguyên backend khác. Nếu broker chỉ nhận instance ID rồi xóa ngay, một request sai hoặc bị giả mạo có thể làm mất dữ liệu của instance khác.

Trong Open Service Broker API (OSB API), request deprovision mang service_id và plan_id qua query string. Broker phải đối chiếu hai giá trị này với thông tin đã lưu khi provision. Đồng thời, broker phải xác minh instance thuộc platform và tenant được phép thực hiện thao tác. Việc xác minh cần diễn ra trước khi gọi backend xóa tài nguyên.

Bài học này thuộc chương Thu hồi dịch vụ của module Spring Cloud Service Broker. Nội dung tập trung vào ba lớp kiểm tra:

- **Định danh dịch vụ:** service_id trong request phải khớp service definition đã dùng để tạo instance.
- **Định danh plan:** plan_id trong request phải khớp plan đã được chọn khi provision hoặc plan hiện tại theo chính sách update.
- **Quyền sở hữu:** instance phải thuộc platform, tenant hoặc phạm vi quản trị đã được xác thực và được phép thu hồi.

Sau bài học, bạn có thể đọc request DELETE theo OSB API, thiết kế truy vấn instance an toàn, kiểm tra service và plan, xác minh quyền sở hữu, xử lý request lặp, chống race condition và ánh xạ lỗi phù hợp trước khi thực hiện deprovision.

## 1. Hợp đồng deprovision của OSB API

Nền tảng yêu cầu thu hồi service instance qua endpoint:

~~~http
DELETE /v2/service_instances/{instance_id}?service_id={service_id}&plan_id={plan_id}
Authorization: Basic <broker-credentials>
X-Broker-API-Version: <supported-version>
~~~

Nếu thao tác có thể chạy bất đồng bộ và platform hỗ trợ, request có thể thêm:

~~~http
DELETE /v2/service_instances/{instance_id}?service_id={service_id}&plan_id={plan_id}&accepts_incomplete=true
~~~

Request deprovision chuẩn không mang một JSON body chứa cấu hình instance. Broker nhận instance_id từ path và service_id, plan_id từ query string. Các thông tin cần thiết để xác định tenant và tài nguyên backend phải được lưu từ quá trình provision hoặc lấy từ context xác thực đáng tin cậy theo thiết kế tích hợp.

Ví dụ request:

~~~http
DELETE /v2/service_instances/instance-7f82?service_id=service-postgresql&plan_id=plan-standard&accepts_incomplete=true
Authorization: Basic <broker-credentials>
X-Broker-API-Version: <supported-version>
~~~

Các thành phần:

| Thành phần | Nguồn | Vai trò |
|---|---|---|
| instance_id | Path | Định danh instance mà platform yêu cầu thu hồi |
| service_id | Query | Xác nhận loại service gắn với instance |
| plan_id | Query | Xác nhận plan mà platform đang tham chiếu |
| accepts_incomplete | Query, tùy chọn | Cho biết platform chấp nhận thao tác bất đồng bộ |
| Authorization | Header | Xác thực platform hoặc broker client |
| X-Broker-API-Version | Header | Phiên bản OSB API mà client yêu cầu |

Broker cần xác thực phiên bản API và thông tin xác thực trước khi xử lý nghiệp vụ. Tuy nhiên, xác thực platform thành công chưa đủ để chứng minh platform có quyền xóa mọi instance trong broker. Quyền truy cập phải được kiểm tra ở cấp instance và tenant.

### 1.1. Vì sao phải kiểm tra service_id và plan_id?

Instance ID xác định một bản ghi, nhưng service_id và plan_id xác nhận request đang tham chiếu đúng loại dịch vụ và gói dịch vụ. Broker lưu các ID này từ lần provision đầu tiên và cập nhật thông tin plan theo quy trình update đã hỗ trợ.

Ví dụ:

| Dữ liệu đã lưu | Giá trị request | Kết quả |
|---|---|---|
| service_id = service-postgresql | service-postgresql | Khớp |
| service_id = service-postgresql | service-redis | Không khớp |
| plan_id = plan-standard | plan-standard | Khớp |
| plan_id = plan-premium | plan-standard | Không khớp |

Nếu ID không khớp, broker phải dừng trước khi gọi backend. Không được dùng service_id hoặc plan_id từ request để ghi đè dữ liệu đã lưu rồi tiếp tục xóa. Làm như vậy sẽ khiến request có thể đổi danh tính của tài nguyên mà broker đang quản lý.

### 1.2. Plan cần được đối chiếu với trạng thái nào?

Service instance có thể được update plan sau khi provision. Vì vậy, broker cần định nghĩa rõ dữ liệu plan nào là nguồn tham chiếu cho deprovision.

Thông thường, broker nên lưu plan hiện tại của instance sau khi một thao tác update plan hoàn tất. Request deprovision phải khớp với plan hiện tại mà platform đang tham chiếu theo hợp đồng OSB API. Nếu update đang chạy hoặc trạng thái plan chưa được xác định, broker cần xử lý trạng thái operation trước khi cho phép xóa.

Không nên chỉ lưu plan_id ban đầu rồi dùng mãi mãi nếu broker hỗ trợ update plan. Cũng không nên chấp nhận bất kỳ plan_id nào chỉ vì service_id đúng. Cần duy trì lịch sử plan hoặc operation nếu phục vụ audit, nhưng bản ghi instance phải thể hiện plan hiện tại một cách nhất quán.

## 2. Lưu thông tin sở hữu ngay từ provision

Deprovision cần xác định ai sở hữu instance. Request chuẩn không gửi lại đầy đủ organization, space hoặc namespace như lúc provision. Vì vậy, broker phải lưu thông tin tenant và platform khi tiếp nhận yêu cầu tạo instance.

Một bản ghi service instance có thể chứa:

| Trường | Mục đích |
|---|---|
| instance_id | ID do platform cung cấp |
| service_id | Service definition đã chọn |
| plan_id | Plan hiện tại |
| platform_id | Nền tảng đã đăng ký broker |
| tenant_id | Định danh tenant nội bộ |
| organization_id | Organization của Cloud Foundry nếu có |
| space_id | Space của Cloud Foundry nếu có |
| namespace_id | Namespace của Kubernetes nếu tích hợp qua controller |
| owner_subject | Chủ thể hoặc tài khoản sở hữu theo mô hình sản phẩm |
| backend_resource_id | Định danh tài nguyên thực tế |
| state | Trạng thái vòng đời instance |
| version | Phiên bản bản ghi để kiểm soát cập nhật đồng thời |

Không phải mọi platform đều có organization và space. Một số tích hợp Kubernetes dùng namespace, cluster hoặc một định danh tenant riêng. Broker nên chuẩn hóa thông tin đó thành TenantContext nội bộ và lưu cùng instance.

Ví dụ mô hình Java:

~~~java
public record TenantContext(
        String platformId,
        String tenantId,
        String organizationId,
        String spaceId,
        String namespaceId
) {}

public record ServiceInstanceRecord(
        String instanceId,
        String serviceId,
        String currentPlanId,
        TenantContext tenant,
        String backendResourceId,
        InstanceState state,
        long version
) {}
~~~

Đây là mô hình minh họa cho domain layer. Tên trường và cấu trúc thực tế phụ thuộc cách tích hợp platform. Điều quan trọng là dữ liệu sở hữu phải được lưu từ request provision đã xác thực, không được suy ra từ một giá trị tùy ý trong request DELETE.

### 2.1. Context không phải bằng chứng xác thực độc lập

OSB API có thể truyền thông tin nguồn gốc người dùng hoặc platform qua header như X-Broker-API-Originating-Identity. Header này hữu ích cho audit và có thể bổ sung thông tin actor, nhưng broker không nên tin một header do client bất kỳ gửi đến nếu request chưa được xác thực và nguồn gửi chưa được xác minh.

Một số nguyên tắc:

- Xác thực platform bằng credentials hoặc cơ chế bảo mật đã cấu hình.
- Gắn instance với platform_id và tenant_id khi provision.
- Chỉ dùng originating identity sau khi đã xác thực nguồn request và kiểm tra định dạng.
- Không lấy tenant_id từ parameters hoặc header không đáng tin cậy để quyết định xóa.
- Ghi actor và nguồn request vào audit để có thể truy vết.

Nếu nhiều platform dùng chung một tài khoản broker, broker cần một cơ chế phân biệt platform đáng tin cậy, chẳng hạn credentials riêng, client identity hoặc cấu hình đăng ký. Nếu không thể xác định request đến từ platform nào, không nên giả định mọi platform đều có quyền xóa mọi instance.

## 3. Quy trình xác minh trước khi xóa

Một deprovision an toàn có thể được tổ chức thành các bước:

~~~mermaid
flowchart TD
    A[Nhận DELETE service instance] --> B[Xác thực platform và API version]
    B --> C[Đọc instance theo ID và platform scope]
    C --> D{Instance tồn tại?}
    D -->|Không| E[Trả kết quả not found theo OSB]
    D -->|Có| F[So sánh service_id]
    F --> G{Khớp?}
    G -->|Không| X[Từ chối request]
    G -->|Có| H[So sánh plan_id hiện tại]
    H --> I{Khớp?}
    I -->|Không| X
    I -->|Có| J[Kiểm tra tenant và quyền sở hữu]
    J --> K{Được phép?}
    K -->|Không| X
    K -->|Có| L[Kiểm tra trạng thái và operation đang chạy]
    L --> M{Có thể deprovision?}
    M -->|Không| N[Trả conflict hoặc lỗi trạng thái]
    M -->|Có| O[Khóa/chuyển trạng thái DEPROVISIONING]
    O --> P[Thu hồi tài nguyên backend]
    P --> Q[Cập nhật operation và instance]
~~~

Một trình tự thực tế:

1. Xác thực platform và kiểm tra X-Broker-API-Version.
2. Kiểm tra instance_id có đúng định dạng và giới hạn kích thước.
3. Tìm instance trong phạm vi platform hoặc tenant đã xác thực.
4. Kiểm tra service_id trong request khớp bản ghi.
5. Kiểm tra plan_id khớp plan hiện tại theo chính sách update.
6. Xác minh tenant, owner và quyền thực hiện deprovision.
7. Kiểm tra instance có đang provision, update hoặc deprovision hay không.
8. Thực hiện chuyển trạng thái có kiểm soát và tạo operation nếu cần.
9. Chỉ sau khi tất cả kiểm tra thành công mới gọi backend adapter.

Thứ tự có thể thay đổi một phần tùy cách truy vấn và bảo vệ thông tin. Ví dụ, truy vấn theo instance_id và platform_id trong cùng một câu query giúp không tiết lộ sự tồn tại của instance thuộc platform khác. Nhưng mọi kiểm tra phải hoàn tất trước khi có tác động xóa.

### 3.1. Truy vấn trong phạm vi platform

Thay vì tìm instance toàn cục rồi mới kiểm tra owner, có thể giới hạn ngay truy vấn:

~~~sql
SELECT instance_id,
       service_id,
       current_plan_id,
       tenant_id,
       state,
       backend_resource_id,
       version
FROM service_instance
WHERE instance_id = :instanceId
  AND platform_id = :authenticatedPlatformId;
~~~

Cách truy vấn này giúp tránh để platform A dò được instance thuộc platform B. Nếu hệ thống cho phép nhiều platform cùng quản lý một instance, phạm vi truy vấn phải phản ánh quan hệ ownership đã được thiết kế, không được tự mở rộng bằng cách bỏ điều kiện platform_id.

Có thể dùng repository method tương ứng:

~~~java
Optional<ServiceInstanceEntity> findByInstanceIdAndPlatformId(
        String instanceId,
        String platformId
);
~~~

Không nên tạo repository method chỉ nhận instanceId rồi gọi delete trực tiếp mà không qua lớp authorization nghiệp vụ.

### 3.2. So sánh service_id và plan_id

Sau khi tìm được bản ghi trong phạm vi phù hợp:

~~~java
private void validateServiceAndPlan(
        DeprovisionRequest request,
        ServiceInstanceRecord instance) {

    if (!instance.serviceId().equals(request.getServiceId())) {
        throw new ServiceIdentityMismatchException();
    }

    if (!instance.currentPlanId().equals(request.getPlanId())) {
        throw new PlanIdentityMismatchException();
    }
}
~~~

Đây là pseudocode minh họa. Request model và exception mapping cần theo phiên bản Spring Cloud Open Service Broker trong project.

Không nên lấy service definition hoặc plan từ catalog hiện tại rồi chỉ kiểm tra ID có còn tồn tại. Một plan có thể đã bị ngừng công bố trong catalog nhưng instance cũ vẫn cần được deprovision. Đối chiếu quan trọng nhất là ID được lưu cùng instance và trạng thái vòng đời của nó. Catalog hiện tại hỗ trợ kiểm tra metadata, nhưng không thay thế dữ liệu lịch sử của instance.

### 3.3. Xác minh quyền sở hữu

Một policy service có thể kiểm tra tenant context của request với tenant đã lưu:

~~~java
public void authorizeDeprovision(
        AuthenticatedPlatform platform,
        TenantContext owner) {

    if (!platform.platformId().equals(owner.platformId())) {
        throw new InstanceOwnershipException();
    }

    if (!platform.canManageTenant(owner.tenantId())) {
        throw new TenantAccessDeniedException();
    }
}
~~~

Đoạn code là minh họa. Trong một hệ thống thực tế, quyền có thể được biểu diễn bằng platform registration, credential scope, service account, tenant mapping hoặc policy engine. Không nên dùng một phép so sánh chuỗi đơn giản nếu danh tính platform và tenant có quy tắc liên kết phức tạp.

## 4. Phân biệt xác thực, quyền sở hữu và tính hợp lệ nghiệp vụ

Ba kiểm tra này trả lời ba câu hỏi khác nhau:

| Kiểm tra | Câu hỏi | Ví dụ thất bại |
|---|---|---|
| Authentication | Ai đang gọi broker? | Credentials sai hoặc token hết hạn |
| Authorization / Ownership | Caller có quyền quản lý instance này không? | Platform khác hoặc tenant không có quyền |
| Business validation | Request có tham chiếu đúng service, plan và trạng thái không? | service_id/plan_id không khớp hoặc instance đang update |

Không được gộp ba lớp này thành một kiểm tra "instance tồn tại". Một caller có thể xác thực hợp lệ nhưng không có quyền trên tenant. Một tenant có quyền vẫn có thể gửi nhầm plan_id. Một request khớp service và plan vẫn không thể xóa an toàn nếu instance đang có một operation không tương thích.

Cũng cần quyết định cách phản hồi khi instance không thuộc caller. Có hệ thống trả not found để không tiết lộ sự tồn tại của tài nguyên; hệ thống khác có thể trả forbidden nếu chính sách cho phép. Cách ánh xạ phải nhất quán với OSB API, threat model và thông tin mà platform được phép biết.

## 5. Kiểm tra trạng thái trước khi deprovision

Service instance có thể ở nhiều trạng thái khác nhau:

| Trạng thái | Xử lý deprovision |
|---|---|
| READY | Có thể bắt đầu thu hồi |
| PROVISIONING | Chờ provision hoàn tất hoặc phối hợp hủy workflow |
| UPDATING | Chờ update kết thúc hoặc áp dụng quy tắc hủy có kiểm soát |
| DEPROVISIONING | Trả lại operation hiện tại nếu request là retry hợp lệ |
| DELETED | Xử lý idempotent theo chính sách |
| FAILED | Kiểm tra tài nguyên backend còn tồn tại hay không trước khi thu hồi |
| CLEANUP_PENDING | Tiếp tục hoặc trả trạng thái cleanup hiện tại, không tạo workflow xóa song song |

Không nên cho phép hai operation provision/update và deprovision cùng điều khiển một instance mà không có cơ chế đồng bộ. Nếu update đang thay đổi backend resource, lệnh delete có thể chạy đồng thời và tạo ra trạng thái không xác định.

Một số cách kiểm soát:

- Optimistic locking bằng cột version.
- Pessimistic row lock trong transaction ngắn.
- Distributed lock hoặc lease theo instance_id.
- Unique constraint để chỉ có một deprovision operation đang hoạt động.
- State transition có điều kiện, ví dụ chỉ đổi READY thành DEPROVISIONING nếu version vẫn bằng giá trị đã đọc.

Ví dụ cập nhật có điều kiện:

~~~sql
UPDATE service_instance
SET state = 'DEPROVISIONING',
    version = version + 1
WHERE instance_id = :instanceId
  AND platform_id = :platformId
  AND service_id = :serviceId
  AND current_plan_id = :planId
  AND state = 'READY'
  AND version = :expectedVersion;
~~~

Nếu số dòng cập nhật là 0, một điều kiện đã thay đổi hoặc request không còn hợp lệ. Broker cần đọc lại trạng thái và phân loại nguyên nhân thay vì tiếp tục xóa backend.

## 6. Xử lý deprovision đồng bộ và bất đồng bộ

Một thao tác thu hồi đơn giản có thể hoàn tất nhanh. Nhưng nếu backend cần xóa database server, snapshot, volume, network policy và credentials, thời gian xử lý có thể vượt giới hạn HTTP.

OSB API cho phép broker hỗ trợ thao tác bất đồng bộ khi platform gửi accepts_incomplete=true. Khi đó, broker có thể trả HTTP 202 Accepted cùng operation token và platform theo dõi qua endpoint last operation.

Ví dụ response:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
~~~

~~~json
{
  "operation": "deprovision-op-456"
}
~~~

Trong lúc đang thu hồi:

~~~json
{
  "state": "in progress",
  "description": "Dang thu hoi tai nguyen cua service instance"
}
~~~

Khi hoàn tất:

~~~json
{
  "state": "succeeded",
  "description": "Service instance da duoc thu hoi"
}
~~~

Nếu thao tác deprovision thất bại, operation cần phản ánh failed theo hợp đồng. Broker nên lưu lỗi đã chuẩn hóa và tài nguyên còn sót lại để worker có thể retry hoặc reconciliation xử lý tiếp.

Nếu platform không chấp nhận incomplete operation, broker không được trả 202 cho một thao tác chưa hoàn tất. Broker phải xử lý đồng bộ trong giới hạn phù hợp hoặc trả lỗi theo hợp đồng OSB API khi không thể thực hiện ở chế độ đồng bộ.

### 6.1. Tách transaction xác minh khỏi lời gọi backend

Không giữ database transaction hoặc row lock trong suốt thời gian gọi API cloud. Một workflow tốt:

1. Mở transaction ngắn.
2. Tìm instance trong phạm vi caller.
3. Kiểm tra service_id, plan_id, owner và state.
4. Chuyển instance sang DEPROVISIONING bằng cập nhật có điều kiện.
5. Tạo operation và outbox event trong cùng transaction.
6. Commit.
7. Worker nhận event và gọi backend.
8. Worker cập nhật operation và instance trong transaction riêng.

Cách này giữ tính nguyên tử giữa state change và việc ghi nhận công việc, nhưng không giữ transaction mở trong nhiều phút.

### 6.2. Outbox và worker

Khi ghi state DEPROVISIONING, broker cần bảo đảm công việc xóa tài nguyên không bị mất nếu tiến trình restart. Transactional outbox giúp ghi operation và event yêu cầu deprovision trong cùng transaction.

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant API as Broker API
    participant DB as Broker Database
    participant Q as Queue
    participant W as Deprovision Worker
    participant B as Backend

    P->>API: DELETE service instance
    API->>DB: Validate + mark DEPROVISIONING
    API->>DB: Save operation + outbox
    API-->>P: 202 Accepted + operation
    DB->>Q: Publish outbox event
    Q->>W: Deprovision command
    W->>B: Delete backend resources
    B-->>W: Result
    W->>DB: Update operation and instance
    P->>API: GET last_operation
    API->>DB: Read operation state
    API-->>P: in progress / succeeded / failed
~~~

## 7. Idempotency và request lặp

Platform có thể gửi lại DELETE khi response bị mất. Broker cần coi request lặp là tình huống bình thường và xử lý theo trạng thái đã lưu.

Các trường hợp:

- Instance READY và request hợp lệ: bắt đầu deprovision.
- Instance DEPROVISIONING và request khớp operation hiện tại: trả lại trạng thái hoặc operation hiện tại theo OSB API.
- Instance đã DELETED: xử lý như yêu cầu lặp đã hoàn tất theo chính sách và hợp đồng.
- Instance không tồn tại: trả kết quả not found/gone theo quy tắc OSB API.
- service_id hoặc plan_id không khớp: từ chối, không chạy cleanup.
- Instance tồn tại nhưng thuộc platform/tenant khác: không tiết lộ hoặc không cho phép thao tác theo chính sách bảo mật.

Idempotency không có nghĩa mọi request DELETE đều được chấp nhận bất kể dữ liệu. Nó có nghĩa cùng một yêu cầu hợp lệ được gửi nhiều lần không gây ra tác động xóa lặp nguy hiểm hoặc tạo operation xung đột.

Một operation record có thể lưu:

- operation_id.
- instance_id.
- platform_id và tenant_id.
- service_id và plan_id đã xác minh.
- trạng thái và bước cleanup hiện tại.
- idempotency key hoặc request fingerprint.
- thời điểm bắt đầu, cập nhật và hoàn tất.
- mã lỗi và thông tin retry đã chuẩn hóa.

Không tạo một operation mới mỗi khi platform retry cùng một DELETE nếu operation cũ vẫn đang chạy. Hãy tra operation hiện tại theo instance và loại thao tác, rồi trả kết quả tương ứng.

## 8. Mapping lỗi và phản hồi OSB API

Broker cần phân loại lỗi xác thực, quyền sở hữu, ID không khớp và trạng thái instance để trả response phù hợp. Các mã HTTP cụ thể phải theo phiên bản OSB API được hỗ trợ và hành vi của platform tích hợp.

| Tình huống | Hướng phản hồi |
|---|---|
| Thiếu hoặc sai credentials | 401 Unauthorized |
| Caller đã xác thực nhưng không được phép | 403 Forbidden hoặc 404 theo chính sách không tiết lộ tài nguyên |
| Instance không tồn tại | 410 Gone hoặc response phù hợp theo OSB API version |
| service_id hoặc plan_id không khớp instance | Từ chối request theo lỗi client phù hợp của OSB API |
| Instance đang có operation xung đột | 409 Conflict hoặc trạng thái operation theo hợp đồng |
| Request thiếu query bắt buộc hoặc sai định dạng | 400 Bad Request |
| Backend tạm thời không sẵn sàng | Lỗi tạm thời hoặc async operation nếu được chấp nhận |
| Deprovision hoàn tất | 200 OK |
| Deprovision được chấp nhận bất đồng bộ | 202 Accepted |

Không trả stack trace, SQL, credentials hoặc thông tin backend nhạy cảm trong response. Description nên giải thích ngắn gọn vấn đề có thể xử lý, ví dụ "service_id không khớp instance đã lưu" hoặc "instance đang có operation update".

Đối với lỗi không được phép truy cập, cân nhắc việc trả 404 để không tiết lộ instance tồn tại ở tenant khác. Tuy nhiên, broker phải giữ audit nội bộ để phân biệt không tồn tại với không có quyền.

## 9. Ví dụ tổ chức logic trong Spring Cloud Service Broker

Spring Cloud Open Service Broker cung cấp abstraction cho service instance lifecycle. Ứng dụng triển khai handler deprovision và ủy quyền xác minh cho application service.

Luồng tổng quát:

~~~mermaid
flowchart TD
    HTTP[OSB Deprovision Endpoint] --> AUTH[Authentication]
    AUTH --> HANDLER[ServiceInstanceService]
    HANDLER --> APP[DeprovisionApplicationService]
    APP --> REPO[(Instance Repository)]
    APP --> POLICY[Ownership and Identity Policy]
    APP --> VALIDATE[Service/Plan Validator]
    APP --> OP[(Operation + Outbox)]
    OP --> WORKER[Deprovision Worker]
    WORKER --> ADAPTER[Backend Adapter]
~~~

Một service layer minh họa:

~~~java
public DeprovisionDecision requestDeprovision(
        DeprovisionCommand command) {

    ServiceInstanceRecord instance =
            repository.findByInstanceIdAndPlatformId(
                    command.instanceId(),
                    command.platformId()
            ).orElseThrow(InstanceNotFoundException::new);

    identityValidator.validateServiceAndPlan(
            command.serviceId(),
            command.planId(),
            instance
    );

    ownershipPolicy.authorize(
            command.authenticatedPlatform(),
            instance.tenant()
    );

    return transactionTemplate.execute(status -> {
        ServiceInstanceRecord current =
                repository.lockById(instance.instanceId());

        statePolicy.assertCanDeprovision(current.state());

        BrokerOperation operation =
                operationRepository.findActiveDeprovision(
                        current.instanceId()
                ).orElseGet(() ->
                        operationRepository.createDeprovision(current)
                );

        repository.markDeprovisioning(
                current.instanceId(),
                current.version()
        );

        outboxRepository.save(
                OutboxEvent.deprovisionRequested(operation.id())
        );

        return DeprovisionDecision.accepted(operation.id());
    });
}
~~~

Đây là pseudocode mô tả ranh giới trách nhiệm. Chữ ký thật của ServiceInstanceService, request model, reactive type và response object phụ thuộc phiên bản Spring Cloud Open Service Broker đang dùng. Không sao chép trực tiếp đoạn code vào project nếu chưa ánh xạ nó với API thư viện hiện tại.

### 9.1. Không xóa trực tiếp trong controller

Controller hoặc handler giao thức nên làm nhiệm vụ chuyển request vào application service. Không đặt toàn bộ logic truy vấn owner, so sánh ID và gọi backend trong controller.

Lợi ích của cách tách lớp:

- Có thể unit test policy service độc lập.
- Có thể dùng cùng logic khi chạy cleanup từ worker hoặc công cụ quản trị.
- Có một nơi duy nhất để kiểm tra tenant và service identity.
- Có thể thay backend mà không thay đổi hợp đồng OSB API.
- Dễ audit và theo dõi operation.

### 9.2. Xác minh lại trong worker

Application service xác minh quyền khi tiếp nhận request. Nếu công việc được xử lý bất đồng bộ, worker cũng phải xác nhận operation vẫn thuộc instance và tenant đã ghi trong operation record trước khi gọi backend. Worker không nên nhận một resource ID tùy ý từ message mà không kiểm tra liên kết với instance.

Điều này giúp chống message giả, message cũ hoặc lỗi trong quá trình publish. Payload queue nên chứa operation ID hoặc instance ID; worker đọc dữ liệu có thẩm quyền từ database thay vì tin toàn bộ resource metadata được gửi trong message.

## 10. Bảo vệ khỏi IDOR và xóa nhầm tenant

Insecure Direct Object Reference (IDOR) xảy ra khi ứng dụng nhận một ID từ client và cho phép truy cập tài nguyên chỉ dựa vào ID đó mà không kiểm tra quyền sở hữu.

Trong broker, IDOR có thể xảy ra khi:

- Platform A gửi instance_id của platform B.
- Tenant A thay service_id hoặc plan_id để khớp một tài nguyên khác.
- Một người dùng có quyền tạo instance nhưng không có quyền xóa instance của tenant khác.
- Worker nhận resource ID trong message nhưng không xác minh owner.
- Endpoint quản trị bỏ qua tenant scope vì được coi là nội bộ.

Các biện pháp phòng vệ:

1. Xác thực platform trước khi xử lý.
2. Truy vấn instance trong phạm vi platform hoặc tenant.
3. So sánh service_id và plan_id với bản ghi đã lưu.
4. Kiểm tra quyền hành động riêng cho deprovision.
5. Không dùng client-supplied resource ID làm nguồn sự thật.
6. Dùng ownership metadata ở backend và kiểm tra trước khi xóa.
7. Audit mọi lần từ chối do owner hoặc ID mismatch.
8. Dùng least privilege cho tài khoản backend.

Nếu backend hỗ trợ tag hoặc label, gắn instance ID, platform ID và tenant ID đã chuẩn hóa khi tạo tài nguyên. Trước khi xóa, adapter có thể xác minh metadata này khớp với resource ledger. Đây là lớp bảo vệ bổ sung nếu database broker có dữ liệu cũ hoặc resource ID bị nhầm.

## 11. Kiểm thử xác minh trước khi xóa

Một bộ test cần xác nhận không chỉ trường hợp xóa thành công mà cả trường hợp request không hợp lệ phải dừng trước khi backend bị gọi.

| Kịch bản | Kết quả mong đợi | Backend delete được gọi? |
|---|---|---|
| service_id khớp, plan_id khớp, owner hợp lệ | Chấp nhận deprovision | Có |
| service_id không khớp | Từ chối request | Không |
| plan_id không khớp | Từ chối request | Không |
| Platform khác gửi instance ID | Không cho phép hoặc trả not found theo policy | Không |
| Tenant không có quyền xóa | Từ chối request | Không |
| Instance không tồn tại | Trả kết quả theo OSB API | Không |
| Instance đang update | Xử lý conflict hoặc điều phối an toàn | Không xóa đồng thời |
| Request DELETE lặp khi đang xóa | Trả operation hiện tại | Không tạo delete workflow thứ hai |
| Instance đã xóa | Idempotent theo chính sách | Không tạo tác động mới |
| Backend resource tag không khớp owner | Dừng cleanup và cảnh báo | Không |
| Query thiếu plan_id | Trả lỗi request | Không |

### 11.1. Unit test cho service và plan mismatch

Ví dụ kiểm tra request có plan_id sai:

~~~java
@Test
void rejectsDeprovisionWhenPlanDoesNotMatch() {
    ServiceInstanceRecord instance =
            fixture.instance(
                    "instance-1",
                    "service-postgresql",
                    "plan-standard"
            );

    DeprovisionCommand command =
            fixture.command(
                    "instance-1",
                    "service-postgresql",
                    "plan-premium"
            );

    assertThatThrownBy(() ->
            deprovisionService.requestDeprovision(command))
            .isInstanceOf(PlanIdentityMismatchException.class);

    verifyNoInteractions(backendProvisioner);
}
~~~

Test này xác nhận broker không gọi backend khi plan không khớp. Cần có test tương tự cho service ID, platform ID và tenant ownership.

### 11.2. Integration test cho request OSB

Gửi DELETE đến endpoint broker trong các tình huống:

- Credentials hợp lệ và ID khớp.
- Credentials sai.
- service_id sai.
- plan_id sai.
- Instance thuộc platform khác.
- Instance đang có update operation.
- Request được gửi lại sau khi response đầu tiên bị mất.

Kiểm tra status code, response body, operation record và số lần backend adapter nhận lệnh. Với trường hợp từ chối, phải xác nhận không có lệnh delete nào được gửi xuống backend.

## 12. Audit, log và vận hành

Deprovision là thao tác nhạy cảm nên cần audit đủ để trả lời ai đã yêu cầu xóa, tài nguyên nào bị tác động và vì sao broker chấp nhận hoặc từ chối.

Các trường audit hữu ích:

- instance_id.
- service_id và plan_id từ request.
- service_id và plan_id đã lưu.
- platform_id và tenant_id.
- actor hoặc originating identity đã xác thực.
- operation_id.
- quyết định authorization.
- trạng thái instance trước và sau.
- backend resource reference đã được che phù hợp.
- thời điểm và kết quả.

Không ghi Authorization header, password, token hoặc connection string vào log. Khi ghi mismatch, có thể ghi ID đã chuẩn hóa hoặc mã tham chiếu phục vụ điều tra theo chính sách bảo vệ dữ liệu.

Metric có thể gồm:

- Số request deprovision theo kết quả.
- Số request bị từ chối do service/plan mismatch.
- Số request bị từ chối do ownership.
- Thời gian deprovision đồng bộ và bất đồng bộ.
- Số operation đang DEPROVISIONING.
- Số lần retry backend delete.
- Số tài nguyên còn cleanup pending.

Không dùng instance ID hoặc tenant ID làm metric label có cardinality cao. Dùng nhãn giới hạn như provider, result và operation type.

## 13. Checklist trước khi gọi backend delete

Trước khi backend adapter thực hiện thao tác xóa, broker nên xác nhận:

- Request đã được xác thực và API version được hỗ trợ.
- instance_id được tìm trong phạm vi platform/tenant phù hợp.
- service_id khớp với service đã lưu.
- plan_id khớp với plan hiện tại theo trạng thái đã hoàn tất.
- Owner và tenant đã được xác minh.
- Caller có quyền deprovision instance.
- Không có operation xung đột hoặc đã xử lý theo chính sách.
- Instance được chuyển sang DEPROVISIONING bằng cập nhật có điều kiện.
- Backend resource reference lấy từ dữ liệu broker đã lưu.
- Ownership metadata của backend khớp nếu backend hỗ trợ kiểm tra.
- Operation và outbox event đã được ghi bền vững nếu chạy bất đồng bộ.
- Audit được ghi mà không lộ secret.

Nếu bất kỳ điều kiện định danh hoặc quyền sở hữu nào không đạt, dừng trước khi gọi backend. Việc từ chối request an toàn hơn một lần xóa nhầm không thể phục hồi.

## Kết luận

Deprovision cần xác minh đầy đủ định danh và quyền sở hữu trước khi xóa tài nguyên. service_id và plan_id trong request phải được đối chiếu với dữ liệu đã lưu của instance; quyền của platform và tenant phải được kiểm tra dựa trên thông tin đã xác thực và ownership được ghi nhận từ lúc provision.

Trong Spring Cloud Service Broker, hãy gom các kiểm tra vào application service hoặc policy service, truy vấn instance trong phạm vi caller, kiểm soát state transition và chỉ gọi backend sau khi xác minh hoàn tất. Kết hợp operation bền vững, idempotency, outbox, audit và test các trường hợp mismatch để ngăn IDOR, race condition và xóa nhầm tài nguyên giữa các tenant.
