# CreateServiceInstanceAppBindingResponse và cấu trúc credentials

Khi một ứng dụng cần sử dụng database, cache hoặc một dịch vụ khác do service broker quản lý, nền tảng gửi yêu cầu tạo service binding. Broker xác định tài nguyên mà ứng dụng được phép sử dụng, tạo hoặc cấp quyền truy cập tương ứng rồi trả thông tin kết nối trong response. Với Spring Cloud Open Service Broker, kiểu response dành cho app binding là CreateServiceInstanceAppBindingResponse.

Phần quan trọng nhất của response thường là credentials: một JSON object chứa thông tin mà ứng dụng cần để kết nối tới service. Cấu trúc này do broker và dịch vụ cung cấp định nghĩa; OSB quy định vị trí và hình dạng tổng thể của object, còn ý nghĩa từng key phải được thống nhất với ứng dụng tiêu thụ. Vì credentials thường chứa password, token hoặc khóa truy cập, broker cần quản lý chúng như dữ liệu bí mật trong toàn bộ vòng đời binding.

## 1. App binding trong vòng đời OSB

Service instance đại diện cho một dịch vụ đã được provision, ví dụ một database PostgreSQL. Binding đại diện cho quyền sử dụng instance đó của một consumer cụ thể, thường là một ứng dụng. Một instance có thể có nhiều binding, mỗi binding có thể có credential hoặc quyền hạn riêng.

Nền tảng gửi request tạo binding đến broker:

~~~http
PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id}?service_id={service_id}&plan_id={plan_id}
X-Broker-API-Version: 2.17
Content-Type: application/json
Authorization: Basic ...

{
  "app_guid": "app-7f31",
  "bind_resource": {
    "app_guid": "app-7f31"
  },
  "parameters": {
    "database": "orders"
  }
}
~~~

Các thành phần định danh có ý nghĩa riêng:

| Thành phần | Ý nghĩa |
|---|---|
| instance_id | Service instance mà ứng dụng muốn sử dụng |
| binding_id | Định danh binding trong phạm vi broker |
| service_id, plan_id | Service và plan của instance, cần đối chiếu với state đã lưu |
| app_guid | Định danh ứng dụng trong nền tảng nếu được gửi |
| parameters | Tùy chọn cấu hình binding, cần được kiểm tra theo policy |

Binding không đồng nghĩa với provision một instance mới. Nhiều ứng dụng có thể cùng bind vào một instance, hoặc một ứng dụng có thể có nhiều binding theo chính sách của broker. Mỗi binding cần có định danh và vòng đời riêng để có thể thu hồi quyền của một consumer mà không ảnh hưởng các consumer khác.

## 2. Vai trò của CreateServiceInstanceAppBindingResponse

CreateServiceInstanceAppBindingResponse biểu diễn kết quả tạo binding cho ứng dụng. Trong Spring Cloud Open Service Broker, kiểu này thuộc nhóm model binding và thường được trả về từ extension point ServiceInstanceBindingService.

Các trường thường liên quan đến app binding:

| Trường response | Vai trò |
|---|---|
| credentials | JSON object chứa thông tin xác thực/kết nối mà ứng dụng cần |
| syslogDrainUrl | Endpoint nhận log nếu service cung cấp chức năng log drain |
| routeServiceUrl | URL của route service nếu broker cung cấp loại tích hợp này |
| volumeMounts | Mô tả volume mount nếu service và nền tảng hỗ trợ capability tương ứng |

Trong đó, credentials là nội dung chính của hầu hết database/cache binding. Các trường như syslogDrainUrl, routeServiceUrl và volumeMounts là tùy chọn theo loại service và khả năng nền tảng; không thêm chúng chỉ để làm response phong phú hơn.

OSB có kiểu response khác cho route binding. Nếu request là app binding, dùng response model dành cho ứng dụng; nếu tích hợp route service, dùng kiểu response và capability tương ứng của framework. Không đặt URL route service hoặc thông tin mount vào credentials nếu chúng thuộc các trường chuyên biệt của hợp đồng.

## 3. Cấu trúc credentials là JSON object

OSB định nghĩa credentials như một object trong response binding. Broker có thể chọn các key phù hợp với dịch vụ, ví dụ:

~~~json
{
  "credentials": {
    "hostname": "postgres.service.internal",
    "port": 5432,
    "database": "orders",
    "username": "svc_orders_app",
    "password": "<secret>",
    "sslmode": "require"
  }
}
~~~

Đây là ví dụ minh họa, không phải schema bắt buộc chung cho mọi broker. Với Redis, credentials có thể chứa host, port, username, password và TLS setting. Với object storage, chúng có thể chứa bucket, endpoint, access key và secret key. Ứng dụng tiêu thụ phải biết hợp đồng cụ thể của service.

Một số quy tắc thiết kế:

- Dùng tên key ổn định, dễ hiểu và có tài liệu cho consumer.
- Dùng kiểu JSON đơn giản, có thể serialize an toàn; nhiều nền tảng và thư viện client mong đợi các giá trị credential dạng chuỗi.
- Chỉ trả các giá trị mà ứng dụng cần để sử dụng service.
- Không đưa credential quản trị dùng chung của toàn hệ thống vào binding nếu có thể tạo user/token riêng cho từng binding.
- Không đưa password hoặc token vào URL nếu có thể tách thành trường riêng; URL có thể bị ghi vào log hoặc lịch sử lỗi.
- Tránh trả cùng một thông tin dưới nhiều key có thể lệch nhau, ví dụ vừa có URI chứa password vừa có password riêng nhưng hai giá trị không được cập nhật đồng bộ.

Nếu cần cung cấp cả URI tiện dụng và các thành phần rời, hãy quy định rõ URI là giá trị chuẩn và bảo đảm các trường host, port, username, database tương thích với URI đó. Không để consumer phải đoán trường nào mới nhất.

## 4. Xây dựng credentials bằng Java

Có thể xây dựng credentials như một Map<String, Object> rồi truyền vào builder của CreateServiceInstanceAppBindingResponse.

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.cloud.servicebroker.model.binding.CreateServiceInstanceAppBindingResponse;

public final class PostgresBindingResponseFactory {

    private PostgresBindingResponseFactory() {
    }

    public static CreateServiceInstanceAppBindingResponse create(
            DatabaseBindingSecret secret) {

        Map<String, Object> credentials = new LinkedHashMap<>();
        credentials.put("hostname", secret.hostname());
        credentials.put("port", secret.port());
        credentials.put("database", secret.database());
        credentials.put("username", secret.username());
        credentials.put("password", secret.password());
        credentials.put("sslmode", "require");

        return CreateServiceInstanceAppBindingResponse.builder()
                .credentials(credentials)
                .build();
    }
}
~~~

DatabaseBindingSecret là mô hình nội bộ minh họa, không phải class do framework cung cấp. Builder trả về app binding response để framework chuyển thành JSON theo hợp đồng OSB. Chữ ký method của ServiceInstanceBindingService và các builder có thể khác theo phiên bản Spring Cloud Open Service Broker; cần dùng đúng dependency version của ứng dụng.

Trong handler, response có thể được trả qua kiểu cha mà extension point yêu cầu:

~~~java
public Mono<CreateServiceInstanceBindingResponse>
createServiceInstanceBinding(CreateServiceInstanceBindingRequest request) {

    return bindingApplicationService.createBinding(toCommand(request))
            .map(PostgresBindingResponseFactory::create);
}
~~~

Đây là ví dụ cấu trúc luồng reactive. toCommand cần lấy các định danh và context phù hợp từ request model, còn bindingApplicationService chịu trách nhiệm xác minh quyền, tạo binding và lấy secret. Không thực hiện trực tiếp lệnh SQL hoặc gọi cloud SDK trong lớp response factory.

## 5. Tách dữ liệu binding, credentials và response

Không nên lưu nguyên response JSON làm bản ghi binding. Cần phân biệt:

| Mô hình | Nội dung | Nơi sử dụng |
|---|---|---|
| Binding record | Binding ID, instance ID, consumer/app ID, tenant, trạng thái, thời điểm tạo | State store của broker |
| Credential reference | ID hoặc đường dẫn tham chiếu đến secret trong secret manager | Application service và infrastructure adapter |
| Credential material | Username/password/token thực tế | Secret manager hoặc vùng lưu trữ mã hóa có kiểm soát |
| App binding response | Credentials được phép trả và các trường OSB tùy chọn | OSB adapter trả về nền tảng |

Ví dụ binding record:

~~~java
public record ServiceBindingRecord(
        String bindingId,
        String instanceId,
        String tenantId,
        String appId,
        String credentialReference,
        String status,
        long version) {
}
~~~

State store chỉ cần giữ credentialReference nếu secret manager có thể cung cấp lại credential theo chính sách. Điều này tránh lưu password dạng rõ trong database nghiệp vụ. Nếu hệ thống bắt buộc lưu credential material, cần mã hóa khi lưu, giới hạn quyền đọc và có quy trình xoay vòng khóa.

Không lưu password trong binding.parameters, metadata catalog, log hoặc exception. Parameters là dữ liệu đầu vào do caller gửi; credentials là bí mật broker cấp cho consumer. Hai loại dữ liệu có nguồn gốc và vòng đời khác nhau.

## 6. Sinh credential riêng cho từng binding

Một thiết kế an toàn thường tạo principal, user hoặc token riêng cho mỗi binding. Ví dụ, hai ứng dụng bind vào cùng PostgreSQL instance sẽ nhận hai database user khác nhau:

| Binding | Consumer | Principal | Quyền |
|---|---|---|---|
| binding-a | Orders API | svc_orders_app | Quyền trên database orders |
| binding-b | Reporting worker | svc_reporting | Chỉ đọc dữ liệu được cấp phép |

Khi một ứng dụng unbind, broker có thể thu hồi principal của binding đó mà không làm gián đoạn ứng dụng còn lại. Nếu tất cả binding dùng chung một admin password, việc thu hồi một binding sẽ khó thực hiện an toàn và việc lộ một credential có thể ảnh hưởng toàn bộ instance.

Credential nên có quyền tối thiểu:

- Chỉ truy cập database, schema, bucket hoặc resource được cấp cho binding.
- Chỉ có thao tác cần thiết, ví dụ read-only nếu consumer chỉ đọc.
- Không có quyền tạo user, sửa cấu hình instance hoặc truy cập tài nguyên tenant khác.
- Có thể thu hồi độc lập khi unbind hoặc khi phát hiện credential bị lộ.

Nếu backend không hỗ trợ principal riêng, broker cần đánh giá tác động của credential dùng chung và có cơ chế thay thế phù hợp, chẳng hạn proxy credential hoặc token giới hạn theo consumer.

## 7. Kiểm tra quyền trước khi trả credentials

Credentials là dữ liệu nhạy cảm. Trước khi tạo binding, broker cần xác minh:

1. Caller được phép gọi endpoint OSB.
2. Service instance tồn tại và đang ở trạng thái cho phép bind.
3. Instance thuộc tenant hoặc phạm vi mà caller được phép quản lý.
4. Service definition có bindable=true.
5. Service plan và chính sách tenant cho phép tính năng binding được yêu cầu.
6. Binding ID chưa thuộc một binding khác với nội dung không tương thích.
7. App/consumer context hợp lệ theo chính sách tích hợp của nền tảng.
8. Parameters của binding hợp lệ và không vượt quyền của instance.

Không tin app_guid, tenant ID hoặc role chỉ vì chúng xuất hiện trong body. Broker cần xác minh originating identity hoặc context nền tảng theo ranh giới tin cậy đã cấu hình. Nếu không thể xác định consumer hoặc tenant một cách đáng tin cậy, không cấp credentials có quyền truy cập tài nguyên.

## 8. Idempotency khi tạo app binding

Nền tảng có thể gửi lại request bind sau timeout. Nếu lần đầu broker đã tạo user và secret nhưng response bị mất, lần thứ hai không nên tạo một user khác hoặc thay password âm thầm.

Broker nên dùng binding_id cùng instance_id làm định danh nghiệp vụ và áp dụng các quy tắc:

- Nếu binding chưa tồn tại, tạo operation và binding record theo transaction hoặc cơ chế idempotency.
- Nếu binding đã tồn tại và cùng consumer/cùng cấu hình, trả lại cùng logical binding và credentials tương ứng theo khả năng lưu trữ secret.
- Nếu binding ID tồn tại nhưng thuộc consumer hoặc instance khác, từ chối xung đột.
- Nếu lần tạo trước đang chạy, tiếp tục hoặc trả operation đang hoạt động theo hợp đồng.
- Không xoay vòng secret chỉ vì request bị gửi lại; rotation là một thao tác riêng có kiểm soát.

Ví dụ, khi broker tạo database user thành công nhưng bị timeout trước khi ghi credential reference, lần retry phải reconcile bằng binding ID hoặc ownership metadata. Nếu chỉ tạo user mới, backend sẽ có user dư thừa và broker có thể trả credentials không khớp với state đã lưu.

Nếu secret manager chỉ cho phép đọc secret một lần, broker cần cân nhắc cách khôi phục response khi request lặp. Có thể lưu secret được mã hóa trong một khoảng thời gian phù hợp, hoặc thiết kế thao tác phục hồi/rotation riêng. Không giả định broker có thể tái tạo cùng password bằng cách sinh ngẫu nhiên lại.

## 9. Các trường app binding bổ sung

Ngoài credentials, app binding response có thể mang các trường chuyên biệt khi service cung cấp chức năng tương ứng:

| Trường | Ví dụ mục đích | Khi nào sử dụng |
|---|---|---|
| syslog_drain_url | URL để nền tảng chuyển log của ứng dụng đến dịch vụ | Service thực sự cung cấp log drain |
| route_service_url | URL endpoint của route service | Broker triển khai route service binding và nền tảng hỗ trợ |
| volume_mounts | Danh sách volume mount và cấu hình mount cho ứng dụng | Service cung cấp volume service theo capability được hỗ trợ |

Không nhầm route_service_url với URL kết nối database. Không đưa volume mount vào credentials nếu OSB/framework có trường cấu trúc riêng. Chỉ khai báo capability trong catalog khi broker có thể thực hiện binding tương ứng.

## 10. Bảo vệ credentials trong response và vận hành

Response binding có thể được nền tảng lưu trữ và chuyển đến ứng dụng. Vì vậy, cần bảo vệ cả đường truyền lẫn các bản sao dữ liệu:

- Dùng TLS giữa platform và broker; xác thực caller theo cấu hình broker.
- Không ghi response body, password, token hoặc private key vào log.
- Không đưa credentials vào exception message, tracing tag, metric label hoặc audit event.
- Chỉ log binding ID, instance ID, operation ID và mã kết quả đã chuẩn hóa.
- Hạn chế quyền đọc secret manager theo service account và phạm vi tài nguyên.
- Mã hóa secret khi lưu và có quy trình xoay vòng/thu hồi.
- Đặt thời hạn hoặc chính sách rotation cho token nếu backend hỗ trợ.
- Khi trả lỗi, không echo parameters hoặc secret do caller gửi.

Không thể thu hồi một secret chỉ bằng cách xóa binding record nếu credential vẫn còn hoạt động ở backend. Unbind phải thực hiện revoke principal/token hoặc thay đổi quyền tương ứng trước khi đánh dấu binding đã thu hồi.

## 11. Unbind và vòng đời credentials

Khi nền tảng gửi DELETE binding, broker cần thu hồi quyền của consumer và dọn dữ liệu liên quan. Luồng thường gồm:

1. Tra cứu binding theo binding ID và instance ID.
2. Xác minh caller và quyền trên binding.
3. Nếu binding đã unbound, trả kết quả phù hợp theo semantics idempotent.
4. Đánh dấu binding đang thu hồi để chặn thao tác cạnh tranh.
5. Revoke database user, token hoặc quyền truy cập do binding sở hữu.
6. Xóa secret hoặc đánh dấu secret reference đã thu hồi.
7. Cập nhật binding state và audit.

Nếu backend cleanup bất đồng bộ, lưu operation và dùng cơ chế last operation theo hỗ trợ của API. Không xóa secret reference khỏi state trước khi worker có đủ dữ liệu để revoke credential. Nếu worker retry, bước revoke cần idempotent; principal không còn tồn tại có thể được xem là đã đạt mục tiêu sau khi xác minh đúng principal của binding.

## 12. Kiểm thử response và credentials

Nên kiểm tra cả cấu trúc JSON lẫn vòng đời secret:

| Ca kiểm thử | Kết quả mong đợi |
|---|---|
| App binding thành công | Response có credentials object theo schema đã công bố |
| Thiếu trường bắt buộc khi tạo credential | Broker không trả response thiếu dữ liệu kết nối |
| Binding cho plan không bindable | Request bị từ chối trước khi cấp credential |
| Hai binding trên cùng instance | Credential và quyền được phân tách theo binding |
| Request bind lặp cùng binding ID | Không tạo user/token trùng hoặc xoay secret ngoài ý muốn |
| Binding ID xung đột instance/consumer | Trả lỗi xung đột theo hợp đồng |
| Secret filtering | Password/token không xuất hiện trong log, metric hoặc error body |
| Unbind thành công | Credential bị revoke và binding state được cập nhật |
| Unbind retry | Không lỗi giả khi principal đã bị thu hồi |
| Secret manager tạm thời không truy cập được | Không cấp response credentials không đầy đủ hoặc không xác minh được |
| Optional response fields | Chỉ có syslog drain, route URL hoặc volume mounts khi được hỗ trợ |

Contract test nên xác nhận JSON response có credentials ở đúng vị trí và các trường tùy chọn dùng đúng tên theo OSB. Unit test cho mapper cần kiểm tra key, kiểu dữ liệu, giá trị thiếu và việc không vô tình thêm trường nội bộ. Integration test cần mô phỏng timeout giữa bước tạo principal, lưu secret và trả response.

## 13. Những sai lầm thường gặp

- Trả toàn bộ cấu hình backend hoặc object persistence trong credentials.
- Dùng chung admin credential cho tất cả binding.
- Lưu password dạng rõ trong binding table hoặc log.
- Coi binding ID là bằng chứng caller được phép bind.
- Tạo credential mới mỗi khi nhận lại cùng request bind.
- Xóa binding record mà không revoke credential thực tế.
- Đưa route service URL hoặc volume mount vào map credentials dù response có trường chuyên biệt.
- Công bố bindable=true nhưng chưa triển khai bind/unbind đầy đủ.
- Trả credentials không nhất quán với secret đã lưu khi request bị retry.

## Kết luận

CreateServiceInstanceAppBindingResponse là response model của Spring Cloud Open Service Broker dành cho app binding. credentials bên trong response là JSON object do broker định nghĩa để cung cấp đúng thông tin kết nối mà ứng dụng cần. Thiết kế tốt cần tách binding record khỏi credential material, tạo quyền riêng cho từng binding, kiểm tra caller và tenant trước khi cấp secret, đồng thời giữ idempotency để request lặp không sinh credential mới ngoài ý muốn. Kết hợp allowlist cho credentials, secret manager, unbind có revoke thực sự và contract test giúp broker công bố một hợp đồng kết nối rõ ràng mà vẫn bảo vệ tài nguyên của khách hàng.
