# Lập ma trận kiểm thử từ khả năng công bố trong catalog

Catalog của Open Service Broker API (OSB API) không chỉ là danh sách service và plan để platform hiển thị cho người dùng. Các thuộc tính trong catalog còn công bố những khả năng mà broker hỗ trợ, chẳng hạn có cho phép bind hay không, có hỗ trợ đổi plan, truy xuất instance hoặc truy xuất binding hay không. Mỗi khả năng được công bố tạo ra một hợp đồng có thể kiểm thử giữa platform và broker.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, Spring Cloud Open Service Broker (SCOSB) cung cấp model catalog, request/response và service abstraction cho các thao tác vòng đời. Ứng dụng broker cần bảo đảm catalog phản ánh đúng implementation, đồng thời các endpoint thực hiện đúng hành vi mà catalog đã công bố. Nếu catalog nói một tính năng được hỗ trợ nhưng endpoint tương ứng trả lỗi hoặc trả dữ liệu sai, platform và consumer sẽ gặp lỗi trong quá trình sử dụng.

Bài học này trình bày cách chuyển catalog thành ma trận kiểm thử có thể truy vết. Nội dung bao gồm service-level capability, plan và schema, endpoint OSB tương ứng, ca kiểm thử thành công/thất bại, kiểm thử trạng thái và bất đồng bộ, bảo mật, tích hợp platform và cách tổ chức dữ liệu kiểm thử trong Spring.

## 1. Catalog là hợp đồng kiểm thử

Catalog được trả qua endpoint:

~~~http
GET /v2/catalog
~~~

Một service definition có thể khai báo service ID, tên, mô tả, các thuộc tính như **bindable**, **plan_updateable**, **instances_retrievable**, **bindings_retrievable**, **allow_context_updates**, các yêu cầu như **syslog_drain**, **route_forwarding**, **volume_mount**, cùng danh sách plans và schemas.

Ví dụ rút gọn:

~~~json
{
  "services": [
    {
      "id": "svc-postgresql",
      "name": "postgresql",
      "description": "Managed PostgreSQL service",
      "bindable": true,
      "plan_updateable": true,
      "instances_retrievable": true,
      "bindings_retrievable": true,
      "allow_context_updates": true,
      "requires": [],
      "plans": [
        {
          "id": "plan-small",
          "name": "small",
          "description": "Small PostgreSQL instance"
        },
        {
          "id": "plan-standard",
          "name": "standard",
          "description": "Standard PostgreSQL instance"
        }
      ]
    }
  ]
}
~~~

Đây là catalog minh họa. Trong hệ thống thực tế, chỉ công bố capability mà broker và provider adapter đã triển khai đầy đủ. Các field tùy chọn phải tuân theo phiên bản OSB API mà broker khai báo và platform đang sử dụng.

Từ catalog, người kiểm thử cần trả lời:

- Service có cho phép tạo binding không?
- Có cho phép chuyển service instance sang plan khác không?
- Platform có thể GET service instance hoặc GET service binding không?
- Broker có chấp nhận cập nhật context của instance không?
- Service yêu cầu platform hỗ trợ các tính năng như syslog drain, route forwarding hoặc volume mount không?
- Plan có schema parameters nào cho provision, update và binding?
- Với mỗi khả năng được bật, endpoint nào phải hoạt động và response nào phải được trả về?

Một catalog hợp lệ về JSON chưa đủ. Phải kiểm thử tính nhất quán giữa metadata được công bố và hành vi của broker.

## 2. Phân biệt capability, plan và schema

Khi lập ma trận, không gom tất cả thông tin catalog thành một cột features. Cần phân biệt ba lớp:

| Lớp | Nội dung | Câu hỏi kiểm thử |
|---|---|---|
| Service capability | bindable, plan_updateable, retrieval và context update | Service có hỗ trợ nghiệp vụ nào? |
| Plan | Plan ID, tên, mô tả, metadata, maintenance information | Platform có nhận đúng danh sách plan và thuộc tính không? |
| Parameter schema | Schema cho create, update hoặc binding | Request hợp lệ được chấp nhận và request sai bị từ chối như thế nào? |

Một service có thể bindable nhưng một plan cụ thể vẫn có schema parameters riêng. Ngược lại, việc một plan có schema binding không có nghĩa service đã công bố khả năng bind. Phải kiểm tra cả service-level capability lẫn dữ liệu plan.

### Bảng ánh xạ capability sang endpoint

| Catalog field/capability | Hành vi cần kiểm thử |
|---|---|
| bindable=true | Tạo binding được hỗ trợ; kiểm thử bind và unbind |
| bindable=false | Platform không nên cung cấp luồng bind; broker từ chối request bind theo hợp đồng |
| plan_updateable=true | Hỗ trợ update plan theo quy tắc OSB API |
| plan_updateable=false hoặc không công bố | Không nhận yêu cầu đổi plan như một capability được hỗ trợ |
| instances_retrievable=true | GET service instance trả thông tin theo contract |
| instances_retrievable=false hoặc không công bố | Không giả định endpoint retrieval được hỗ trợ |
| bindings_retrievable=true | GET binding trả dữ liệu hiện hành của binding |
| bindings_retrievable=false hoặc không công bố | Không công bố khả năng đọc lại binding |
| allow_context_updates=true | Kiểm thử cập nhật context theo API version hỗ trợ |
| allow_context_updates=false hoặc không công bố | Không áp dụng thay đổi context ngoài hợp đồng |
| requires có syslog_drain | Kiểm thử service cung cấp syslog drain URL khi bind |
| requires có route_forwarding | Kiểm thử route service URL và tích hợp platform tương ứng |
| requires có volume_mount | Kiểm thử volume mount response và platform support |

Không suy diễn rằng một field không có trong catalog tương đương với true. Với capability tùy chọn, ma trận phải ghi rõ giá trị thực tế được serialize và hành vi tương ứng.

## 3. Xây dựng test inventory từ catalog

Trước khi viết test case, hãy chuyển catalog thành một inventory có cấu trúc. Mỗi service và plan cần có định danh ổn định để kết quả test có thể truy vết khi catalog thay đổi.

Ví dụ inventory:

| Service ID | Plan ID | bindable | plan_updateable | instances_retrievable | bindings_retrievable |
|---|---|---:|---:|---:|---:|
| svc-postgresql | plan-small | true | true | true | true |
| svc-postgresql | plan-standard | true | true | true | true |
| svc-redis-cache | plan-cache | false | false | false | false |

Bảng chỉ minh họa dữ liệu test. Trong test tự động, nên đọc catalog từ endpoint hoặc từ cùng bean cấu hình được dùng để phục vụ catalog, tránh duy trì một bản copy thủ công không đồng bộ.

Có thể dùng một record test:

~~~java
public record CatalogCapabilityCase(
        String serviceId,
        String planId,
        boolean bindable,
        boolean planUpdateable,
        boolean instancesRetrievable,
        boolean bindingsRetrievable,
        boolean allowContextUpdates
) {
}
~~~

Với mỗi dòng inventory, sinh hoặc lựa chọn test case theo capability. Nếu catalog có hàng chục service và nhiều plan, có thể dùng parameterized test để tránh lặp code, nhưng tên test report vẫn phải chứa service ID, plan ID và capability đang kiểm tra.

## 4. Ma trận kiểm thử capability ở cấp service

Ma trận đầu tiên kiểm tra mỗi capability được công bố có hành vi tương ứng.

| ID | Điều kiện catalog | Request/endpoint | Kết quả mong đợi |
|---|---|---|---|
| CAT-001 | Service tồn tại | GET /v2/catalog | Service xuất hiện đúng một lần theo ID |
| CAT-002 | bindable=true | Bind instance hợp lệ | Binding được tạo theo contract |
| CAT-003 | bindable=false | Bind instance | Broker từ chối theo contract, không tạo provider principal |
| CAT-004 | plan_updateable=true | Update sang plan hợp lệ | Plan được cập nhật hoặc operation async được tạo |
| CAT-005 | Không hỗ trợ plan update | Update sang plan khác | Request bị từ chối đúng contract |
| CAT-006 | instances_retrievable=true | GET instance | Trả dữ liệu instance được phép công bố |
| CAT-007 | Không hỗ trợ instance retrieval | GET instance | Không giả lập response thành công ngoài capability |
| CAT-008 | bindings_retrievable=true | GET binding | Trả dữ liệu binding hiện hành |
| CAT-009 | Không hỗ trợ binding retrieval | GET binding | Không trả credentials ngoài contract |
| CAT-010 | allow_context_updates=true | PATCH có context update | Chỉ các field context được hỗ trợ được cập nhật |
| CAT-011 | allow_context_updates=false | PATCH thay đổi context | Không áp dụng thay đổi không được công bố |
| CAT-012 | requires khai báo capability | Bind tương ứng | Response và tích hợp đáp ứng yêu cầu đã khai báo |

Khi broker không hỗ trợ một endpoint retrieval, hãy kiểm tra status code và error body theo đúng phiên bản OSB API. Không chỉ kiểm tra rằng request thất bại; cần xác minh broker không đọc secret hoặc gọi provider như một side effect ngoài ý muốn.

## 5. Ma trận kiểm thử catalog và plan

Catalog cần ổn định về ID, quan hệ service-plan và các metadata mà platform dùng để tạo request.

| ID | Nội dung | Ca kiểm thử | Kết quả mong đợi |
|---|---|---|---|
| PLAN-001 | Service ID | ID bị thiếu hoặc trùng | Catalog không được trả cấu trúc mơ hồ |
| PLAN-002 | Plan ID | Plan ID trong cùng service bị trùng | Test phát hiện lỗi cấu hình |
| PLAN-003 | Plan membership | Request provision dùng plan không thuộc service | Bị từ chối |
| PLAN-004 | Plan visibility | Plan không public hoặc không khả dụng | Không xuất hiện sai trong catalog |
| PLAN-005 | Plan metadata | Metadata có giá trị hợp lệ | Serialize đúng schema |
| PLAN-006 | Parameter schema | Catalog khai báo create schema | Platform đọc được schema đúng |
| PLAN-007 | Update schema | Catalog khai báo update schema | Chỉ nhận parameters hợp lệ theo schema |
| PLAN-008 | Binding schema | Catalog khai báo binding schema | Bind parameters được validate |
| PLAN-009 | Maintenance info | Plan công bố maintenance metadata | Serialize đúng format và version |
| PLAN-010 | Catalog repeatability | Gọi catalog nhiều lần | ID và capability ổn định nếu cấu hình không đổi |

Một plan không được tham chiếu bởi service khác chỉ vì hai service có cùng tên. Mọi request phải được validate bằng cặp service ID và plan ID.

### Kiểm thử schema parameters

Giả sử plan có schema create parameters:

~~~json
{
  "schemas": {
    "service_instance": {
      "create": {
        "parameters": {
          "type": "object",
          "properties": {
            "storage_gb": {
              "type": "integer",
              "minimum": 10,
              "maximum": 500
            },
            "region": {
              "type": "string",
              "enum": ["ap-southeast-1", "ap-southeast-2"]
            }
          },
          "required": ["storage_gb"]
        }
      }
    }
  }
}
~~~

Các ca kiểm thử tương ứng:

- storage_gb nằm trong giới hạn và region hợp lệ: chấp nhận.
- Thiếu storage_gb: từ chối validation.
- storage_gb nhỏ hơn 10 hoặc lớn hơn 500: từ chối.
- Truyền số dưới dạng string khi schema yêu cầu integer: xử lý theo validator/schema contract.
- Region không nằm trong enum: từ chối.
- Truyền field không được hỗ trợ: áp dụng chính sách additional properties đã công bố.
- Payload chứa secret: không ghi raw value vào log hoặc error response.

Cần kiểm tra schema được công bố và validator thực thi cùng một quy tắc. Không để catalog nói maximum=500 nhưng backend vẫn cho tạo resource 1.000 GB.

## 6. Ma trận provision và deprovision

Provision và deprovision là các nghiệp vụ nền tảng của broker, cần kiểm thử cả response đồng bộ/bất đồng bộ, persistence và side effect provider.

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| PROV-001 | Provision với service/plan hợp lệ | Tạo đúng instance |
| PROV-002 | Service ID không tồn tại | Trả lỗi validation phù hợp |
| PROV-003 | Plan ID không thuộc service | Từ chối trước provider call |
| PROV-004 | Parameters hợp lệ theo schema | Provider nhận cấu hình đã chuẩn hóa |
| PROV-005 | Parameters sai schema | Không tạo provider resource |
| PROV-006 | Provider hoàn tất đồng bộ | Trả response success đúng contract |
| PROV-007 | Provider xử lý bất đồng bộ và platform chấp nhận | Trả 202 cùng operation ID |
| PROV-008 | Platform không chấp nhận async nhưng provider chưa hoàn tất | Không giả vờ thành công |
| PROV-009 | Retry cùng provision request | Không tạo resource trùng |
| PROV-010 | Provider timeout sau khi có thể đã tạo resource | Reconcile trước khi gửi create lại |
| DEPROV-001 | Deprovision instance hợp lệ | Xóa đúng tài nguyên được quản lý |
| DEPROV-002 | Deprovision lặp lại | Xử lý idempotent theo contract |
| DEPROV-003 | Instance ID không tồn tại | Trả kết quả theo quy tắc OSB API |
| DEPROV-004 | Provider từ chối xóa | Lưu lỗi và trạng thái operation chính xác |
| DEPROV-005 | Có binding còn hoạt động | Áp dụng điều kiện lifecycle và platform contract |

Với mỗi test, kiểm tra đồng thời:

- HTTP status và response body.
- Instance state trong database.
- Operation record nếu bất đồng bộ.
- Provider adapter được gọi đúng số lần.
- External resource mapping.
- Log không chứa credentials hoặc raw secret parameters.

## 7. Ma trận bind, unbind và binding retrieval

Chỉ tạo test bind nếu catalog công bố bindable=true. Nếu bindable false, test âm phải chứng minh broker từ chối request và không tạo principal ở provider.

| ID | Điều kiện | Hành động | Kết quả mong đợi |
|---|---|---|---|
| BIND-001 | bindable=true | Bind request hợp lệ | Tạo binding riêng |
| BIND-002 | bindable=false | Bind request | Từ chối, không có provider side effect |
| BIND-003 | Binding schema hợp lệ | Bind với parameters | Tạo credentials theo schema |
| BIND-004 | Binding schema sai | Bind với parameters lỗi | Từ chối validation |
| BIND-005 | Instance không tồn tại | Bind | Not found theo contract |
| BIND-006 | Binding ID đã tồn tại với cùng request | Retry bind | Trả kết quả idempotent |
| BIND-007 | Binding ID tồn tại với request khác | Bind lại | Từ chối conflict theo contract |
| UNBIND-001 | Binding ACTIVE | Unbind | Thu hồi đúng credential/principal |
| UNBIND-002 | Binding đã REVOKED | Unbind lặp lại | Xử lý idempotent |
| UNBIND-003 | Provider revoke timeout | Unbind | Giữ trạng thái chưa kết luận và hỗ trợ retry |
| GETBIND-001 | bindings_retrievable=true | GET binding hợp lệ | Trả đúng credentials hiện hành |
| GETBIND-002 | bindings_retrievable=false | GET binding | Không công bố khả năng retrieval |
| GETBIND-003 | Binding thuộc instance khác | GET binding | Không trả dữ liệu binding đó |
| GETBIND-004 | Binding đã revoke | GET binding | Không trả secret đã thu hồi |

Với GET binding, test cần kiểm tra response allowlist. Không trả secret reference, provider admin token, dữ liệu tenant khác hoặc field nội bộ chỉ vì chúng có trong database entity.

## 8. Ma trận update và context update

Nếu service công bố plan_updateable=true, phải kiểm tra khả năng update theo những điều kiện OSB API cho phép. Các trường hợp phổ biến gồm update parameters, chuyển plan khi được hỗ trợ và xử lý bất đồng bộ.

| ID | Điều kiện | Hành động | Kết quả mong đợi |
|---|---|---|---|
| UPDATE-001 | Plan updateable | Update với parameters hợp lệ | Provider nhận thay đổi được hỗ trợ |
| UPDATE-002 | Plan updateable | Chuyển sang plan hợp lệ | Plan đích được áp dụng |
| UPDATE-003 | Plan updateable | Chuyển sang plan không tồn tại | Từ chối |
| UPDATE-004 | Plan không updateable | Yêu cầu đổi plan | Từ chối theo contract |
| UPDATE-005 | Update schema có giới hạn | Vượt quota | Từ chối trước provider side effect |
| UPDATE-006 | Provider update async | Poll last_operation | Trạng thái tiến triển và kết thúc chính xác |
| UPDATE-007 | Retry update cùng operation | Gửi lại request | Không áp dụng thay đổi hai lần |
| CONTEXT-001 | allow_context_updates=true | Context update hợp lệ | Lưu context đã validate |
| CONTEXT-002 | allow_context_updates=false | Thử thay đổi context | Không cập nhật |
| CONTEXT-003 | Context có field ngoài allowlist | Update context | Không nhận field không được hỗ trợ |
| CONTEXT-004 | Context update lặp | Gửi lại cùng nội dung | Kết quả ổn định, không tạo side effect thừa |

Không suy luận rằng plan_updateable=true cho phép thay đổi mọi thuộc tính của instance. Chỉ các thay đổi được OSB API, plan schema và implementation hỗ trợ mới được chấp nhận.

## 9. Kiểm thử requires và các tính năng platform

Trường **requires** trong service definition có thể công bố các tính năng platform mà service cần, chẳng hạn **syslog_drain**, **route_forwarding** hoặc **volume_mount**. Nếu khai báo một yêu cầu, cần kiểm tra cả catalog serialization và response binding tương ứng.

| Capability yêu cầu | Kiểm thử response | Kiểm thử tích hợp |
|---|---|---|
| syslog_drain | Có syslog_drain_url hợp lệ khi bind theo offering | Platform cấu hình log drain và gửi log |
| route_forwarding | Có route_service_url hợp lệ nếu service hỗ trợ | Platform thiết lập route forwarding |
| volume_mount | volume_mounts đúng cấu trúc và quyền | Platform mount volume theo contract |

Không công bố requires chỉ vì broker có thể tạo một URL hoặc trả một object. Phải có provider capability, response model và platform integration tương ứng. Nếu platform test environment không hỗ trợ một capability, ghi rõ phần kiểm thử contract đã chạy và phần end-to-end còn thiếu.

## 10. Ma trận asynchronous operation và last_operation

Các operation dài thường trả 202 và yêu cầu platform polling. Catalog không thay thế việc kiểm thử operation store; capability và endpoint phải được kiểm tra cùng nhau.

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| ASYNC-001 | Platform gửi accepts_incomplete=true và provider chưa xong | Trả 202 và operation ID |
| ASYNC-002 | Operation đang chạy | last_operation trả in progress |
| ASYNC-003 | Operation hoàn tất thành công | last_operation trả succeeded |
| ASYNC-004 | Operation thất bại cuối cùng | last_operation trả failed |
| ASYNC-005 | Operation ID không thuộc instance | Không tiết lộ operation khác |
| ASYNC-006 | Poll cùng operation nhiều lần | Không tạo thêm provider side effect |
| ASYNC-007 | Broker restart khi operation đang chạy | Worker phục hồi từ trạng thái bền vững |
| ASYNC-008 | Queue giao message lặp | Worker idempotent |
| ASYNC-009 | Provider trả operation ID riêng | Broker lưu và theo dõi đúng operation |
| ASYNC-010 | Provider timeout, kết quả chưa rõ | Reconciliation trước retry |

Kiểm tra rằng operation ID ổn định, instance state nhất quán với operation result và description không chứa secret. Không trả các trạng thái nội bộ tùy ý nếu OSB API quy định tập giá trị khác.

## 11. Ma trận bảo mật và phân quyền

Catalog có thể công bố khả năng hợp lệ nhưng endpoint vẫn có thể bị khai thác nếu authorization và tenant isolation sai. Mỗi capability nên có test âm về caller, resource ownership và dữ liệu trả về.

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| SEC-001 | Request không có broker authentication hợp lệ | 401/403 theo cấu hình |
| SEC-002 | Caller tenant A truy cập instance tenant B | Từ chối |
| SEC-003 | Binding ID thuộc instance khác | Không trả credentials |
| SEC-004 | GET binding hợp lệ | Chỉ trả credentials của binding đó |
| SEC-005 | Catalog public metadata | Không chứa provider credential hoặc secret |
| SEC-006 | Parameters chứa secret | Log và trace đã redacted |
| SEC-007 | Provider permission denied | Không tự mở rộng quyền |
| SEC-008 | Request parameters chọn provider account tùy ý | Bị từ chối hoặc bỏ qua theo policy |
| SEC-009 | Unbind một binding | Không thu hồi credential binding khác |
| SEC-010 | Deprovision một instance | Không xóa resource ngoài ownership |

Test bảo mật phải kiểm tra cả status code, response body, database state và provider call count. Chỉ xác minh HTTP 403 là chưa đủ nếu broker đã gọi provider trước khi từ chối.

## 12. Từ ma trận sang traceability

Mỗi capability hoặc schema field cần có liên kết tới test ID. Có thể duy trì bảng traceability trong test management hoặc test source.

Ví dụ:

| Catalog source | Capability/field | Test ID | Endpoint | Nhóm test |
|---|---|---|---|---|
| svc-postgresql | bindable=true | BIND-001, BIND-003, UNBIND-001 | PUT/DELETE binding | Contract + integration |
| svc-postgresql | plan_updateable=true | UPDATE-001, UPDATE-002 | PATCH instance | Contract + provider |
| svc-postgresql | instances_retrievable=true | GETINST-001 | GET instance | Contract |
| svc-postgresql | bindings_retrievable=true | GETBIND-001, GETBIND-004 | GET binding | Contract + security |
| svc-postgresql | allow_context_updates=true | CONTEXT-001, CONTEXT-003 | PATCH instance | Contract + validation |
| svc-postgresql/plan-small | create schema | PROV-004, PROV-005 | PUT instance | Schema + provider |
| svc-postgresql/plan-small | binding schema | BIND-003, BIND-004 | PUT binding | Schema + provider |

Nếu catalog đổi từ bindings_retrievable=false sang true, pipeline nên báo thiếu test GET binding. Nếu capability bị tắt, test tích cực tương ứng cần được cập nhật thành test âm để xác nhận broker không tiếp tục quảng bá hành vi cũ.

## 13. Kiểm thử catalog endpoint với Spring

Trong ứng dụng SCOSB, catalog được xây dựng từ service definition và được framework phục vụ qua endpoint OSB. Có thể dùng **WebTestClient** để kiểm tra JSON được serialize thực tế.

Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class CatalogContractTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void catalogPublishesExpectedCapabilities() {
        webTestClient.get()
                .uri("/v2/catalog")
                .header("X-Broker-API-Version", "2.17")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.services[0].id")
                    .isEqualTo("svc-postgresql")
                .jsonPath("$.services[0].bindable")
                    .isEqualTo(true)
                .jsonPath("$.services[0].plan_updateable")
                    .isEqualTo(true)
                .jsonPath("$.services[0].bindings_retrievable")
                    .isEqualTo(true);
    }
}
~~~

Ví dụ cần điều chỉnh API version, authentication và test catalog fixture theo cấu hình dự án. Không cố định index [0] nếu catalog có nhiều service và thứ tự không được bảo đảm; nên tìm service theo ID bằng JSONPath phù hợp hoặc parse response thành model rồi assert theo ID.

### Kiểm tra capability và endpoint trong cùng test suite

Một test catalog riêng chỉ chứng minh metadata. Nên có test tương ứng cho endpoint được công bố. Có thể đặt tên theo cùng test ID:

~~~java
@Test
void bindingRetrievalCapabilityHasWorkingEndpoint() {
    // Arrange: create a READY instance and ACTIVE binding fixture.
    // Act: GET the binding endpoint.
    // Assert: response matches the OSB contract and contains only allowed fields.
}
~~~

Không cần gọi provider thật trong unit test. Dùng provider adapter giả để xác minh application service và repository; dùng sandbox/Testcontainers cho integration test khi cần kiểm tra persistence, HTTP và queue.

## 14. Kiểm thử endpoint theo hợp đồng OSB API

Với từng endpoint, xác minh:

- HTTP method và path.
- Header API version.
- Authentication và authorization.
- Request body hợp lệ/không hợp lệ.
- Status code và response JSON.
- Error response có cấu trúc đúng.
- Side effect provider có xảy ra đúng lúc và đúng số lần.
- Instance, binding và operation state sau request.
- Idempotency khi request lặp.
- Không tiết lộ secret hoặc dữ liệu tenant khác.

Các endpoint thường cần có trong test inventory:

| Nghiệp vụ | Endpoint |
|---|---|
| Catalog | GET /v2/catalog |
| Provision | PUT /v2/service_instances/{instance_id} |
| Fetch instance (nếu hỗ trợ) | GET /v2/service_instances/{instance_id} |
| Update | PATCH /v2/service_instances/{instance_id} |
| Deprovision | DELETE /v2/service_instances/{instance_id} |
| Last operation | GET /v2/service_instances/{instance_id}/last_operation |
| Bind | PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id} |
| Get binding (nếu hỗ trợ) | GET /v2/service_instances/{instance_id}/service_bindings/{binding_id} |
| Unbind | DELETE /v2/service_instances/{instance_id}/service_bindings/{binding_id} |

Các endpoint retrieval chỉ đưa vào nhóm test thành công khi catalog công bố capability tương ứng. Tuy nhiên, vẫn nên có test âm cho trường hợp capability không được hỗ trợ.

## 15. Phân tầng test để tránh phụ thuộc không cần thiết

Không phải mọi test case đều cần khởi chạy Cloud Foundry hoặc provider thật. Có thể chia test theo tầng:

| Tầng | Mục tiêu | Thành phần |
|---|---|---|
| Unit | Kiểm tra validation, state transition và mapping | Application service, validator, mapper |
| Catalog contract | Kiểm tra catalog JSON và capability | SCOSB endpoint, service definitions |
| HTTP integration | Kiểm tra path, header, status và response | Spring Boot, WebTestClient |
| Persistence integration | Kiểm tra transaction, constraint, locking | Database thật/Testcontainers |
| Provider contract | Kiểm tra adapter gọi đúng API | Mock server hoặc provider sandbox |
| Async integration | Kiểm tra outbox, queue, worker, retry | Database và message broker test |
| Platform end-to-end | Kiểm tra cách platform sử dụng catalog và lifecycle | Cloud Foundry/Kubernetes test environment |

Tầng thấp giúp phát hiện lỗi nhanh; tầng cao xác nhận các thành phần thực sự phối hợp. Không thay thế toàn bộ integration test bằng mock, vì mock không chứng minh serialization, transaction, RBAC hay provider API tương thích.

## 16. Dữ liệu test và cách đặt tên test

Dữ liệu test nên được tạo theo service ID, plan ID và capability. Tránh dùng một fixture chung khiến test vô tình kiểm tra service khác.

Ví dụ cấu trúc fixture:

~~~text
catalog-fixtures/
  postgresql-bindable.json
  postgresql-no-binding-retrieval.json
  redis-non-bindable.json

operation-fixtures/
  provision-in-progress.json
  provision-succeeded.json
  update-failed.json

binding-fixtures/
  app-binding-active.json
  service-key-active.json
  binding-revoked.json
~~~

Nếu repository không dùng thư mục fixture như ví dụ, có thể đặt fixture trong test resources hoặc factory. Không cần tạo file fixture cho mọi tổ hợp; dùng builder/parameterized data khi dữ liệu nhỏ và dễ đọc.

Tên test nên mô tả capability và kỳ vọng, ví dụ:

- catalog_shouldAdvertiseBindingRetrievalOnlyWhenImplemented
- nonBindableService_shouldRejectBindWithoutProviderSideEffect
- planUpdateableService_shouldAcceptSupportedPlanChange
- bindingRetrieval_shouldReturnCredentialsForRequestedBindingOnly
- contextUpdate_shouldRejectChangesWhenCapabilityIsDisabled

Tên rõ giúp báo cáo CI cho biết capability nào bị lỗi mà không cần đọc toàn bộ test source.

## 17. Quản lý thay đổi catalog và regression test

Catalog là API contract với platform. Khi thay đổi service definition, hãy kiểm tra tác động tới platform đã đăng ký broker và consumer hiện hữu.

Một quy trình regression:

1. Lấy catalog hiện tại và catalog mới.
2. So sánh service ID, plan ID, capability và schema.
3. Phát hiện capability mới bật hoặc capability cũ bị tắt.
4. Tạo test bắt buộc cho hành vi mới.
5. Chạy regression cho endpoint và state transition liên quan.
6. Kiểm tra plan cũ và instance đã provision vẫn được xử lý.
7. Xác minh response không làm lộ dữ liệu hoặc phá compatibility.
8. Lưu catalog snapshot hoặc contract test artifact theo release.

Không chỉ so sánh số lượng service. Một thay đổi từ bindable=false sang true có thể yêu cầu implementation bind, secret storage, unbind và security test. Một thay đổi plan_updateable=true có thể yêu cầu update workflow, async operation và provider capability.

## 18. Các lỗi thường gặp khi lập ma trận

**Chỉ kiểm tra catalog trả HTTP 200.** Điều này không chứng minh các capability đã khai báo hoạt động. Hãy liên kết từng field với endpoint và expected behavior.

**Chỉ viết test cho happy path.** Capability cần có negative test, ví dụ bindable false, plan không hợp lệ, tenant sai và secret đã revoke.

**Bỏ qua plan schema.** Catalog có thể khai báo giới hạn parameters nhưng backend không validate hoặc validate khác schema.

**Dùng một fixture cho mọi service.** Fixture chung có thể che lỗi capability hoặc plan ID bị nhầm.

**Không kiểm thử side effect.** Request bị từ chối vẫn có thể đã gọi provider. Kiểm tra provider call count và database state.

**Bỏ qua async operation.** 202 chỉ là chấp nhận xử lý; cần test operation ID, polling, retry và recovery.

**Coi capability không công bố là true.** Không tự bật test thành công cho endpoint retrieval hoặc update khi catalog không hỗ trợ.

**Chỉ dùng mock.** Mock không xác minh database constraint, queue durability, API serialization hoặc platform behavior.

**Không cập nhật regression khi catalog đổi.** Catalog và test inventory sẽ lệch nhau theo thời gian.

## 19. Quy trình lập và duy trì ma trận

Có thể áp dụng quy trình sau cho mỗi release broker:

1. Đọc catalog output thực tế của build hoặc môi trường test.
2. Lập inventory theo service ID và plan ID.
3. Ghi lại tất cả capability và requires được công bố.
4. Lấy schemas của provision, update và binding.
5. Ánh xạ từng field sang endpoint, state transition và provider action.
6. Viết test tích cực cho capability được bật.
7. Viết test âm cho capability bị tắt, request sai và caller không có quyền.
8. Thêm test async, idempotency, recovery và security khi có side effect.
9. Chạy unit, contract, integration và platform test phù hợp.
10. Lưu test report và catalog snapshot để truy vết regression.
11. Khi catalog đổi, cập nhật inventory và test ID cùng một thay đổi.

Ma trận cần được duy trì như một phần của hợp đồng phát hành. Nếu một capability không có test liên kết, hãy xem đó là khoảng trống kiểm chứng trước khi phát hành.

## Kết luận

Lập ma trận kiểm thử từ catalog giúp biến metadata của OSB API thành các kỳ vọng có thể xác minh. Mỗi service capability như **bindable**, **plan_updateable**, **instances_retrievable**, **bindings_retrievable** và **allow_context_updates** cần được liên kết với endpoint, trạng thái và side effect tương ứng. Plan và parameter schemas cần có test riêng cho dữ liệu hợp lệ, không hợp lệ và giới hạn. Trong Spring Cloud Service Broker, kết hợp catalog contract test với HTTP integration, persistence, provider, async và security test giúp bảo đảm broker chỉ công bố những khả năng thực sự hoạt động và giữ catalog đồng bộ với implementation qua từng release.

## Tài liệu tham khảo

- [Open Service Broker API Specification](https://github.com/openservicebrokerapi/servicebroker/blob/master/spec.md) — catalog, service capabilities, plans, schemas và endpoint lifecycle.
- [Open Service Broker API — API Versioning](https://github.com/openservicebrokerapi/servicebroker/blob/master/spec.md#api-versioning) — cách platform và broker thương lượng phiên bản API.
- [Spring Cloud Open Service Broker Reference Documentation](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/reference/) — catalog model, service abstraction và request/response.
- [Spring Boot Testing](https://docs.spring.io/spring-boot/reference/testing/index.html) — kiểm thử ứng dụng Spring Boot.
- [Spring Framework WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html) — kiểm thử HTTP endpoint reactive.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/) — parameterized test và test lifecycle.
- [Testcontainers Documentation](https://java.testcontainers.org/) — kiểm thử tích hợp với database và message broker thật.

