# Kiểm thử phiên bản giao thức, tham số không hợp lệ và cờ khả năng

## Vì sao cần kiểm thử hợp đồng OSB API?

Một service broker có thể chạy ổn trong happy path nhưng vẫn không tương thích với platform nếu xử lý sai phiên bản giao thức, chấp nhận tham số không hợp lệ hoặc công bố capability không khớp với hành vi thực tế. Những lỗi này thường chỉ xuất hiện khi broker được đăng ký với Cloud Foundry hoặc một platform OSB khác, nơi client dựa vào catalog và response để quyết định endpoint nào sẽ được gọi.

Module `SPRING_CLOUD_SERVICE_BROKER` sử dụng Spring Cloud Open Service Broker để công bố catalog và xử lý provision, update, deprovision, bind, unbind cùng operation bất đồng bộ. Kiểm thử cần xác nhận ba lớp hợp đồng:

1. **Phiên bản giao thức:** broker nhận đúng header `X-Broker-API-Version`, chấp nhận phiên bản được hỗ trợ và phản hồi rõ ràng với phiên bản không tương thích.
2. **Tham số:** catalog mô tả schema đúng, broker validate request độc lập và trả HTTP status/error code phù hợp.
3. **Capability flags:** các cờ trong catalog phản ánh chính xác endpoint và hành vi broker thực sự hỗ trợ.

Kiểm thử các lớp này giúp tránh trường hợp platform thấy một capability rồi gọi endpoint mà broker chưa triển khai, hoặc người dùng gửi tham số sai nhưng broker vẫn tạo tài nguyên một phần.

## Phiên bản OSB API và header bắt buộc

Mỗi request từ platform đến broker phải có header:

```http
X-Broker-API-Version: 2.17
```

Giá trị dùng định dạng `MAJOR.MINOR`. Platform MUST gửi header này trên mọi request OSB API. Theo đặc tả, nếu header bị thiếu, broker MAY trả `400 Bad Request` kèm thông điệp cho biết header là bắt buộc. Nếu broker cần một tính năng chỉ có trong phiên bản mới hơn phiên bản platform gửi, broker MAY trả `412 Precondition Failed` và giải thích phiên bản cần thiết.

Các thay đổi minor của OSB API được thiết kế theo hướng cộng thêm: endpoint/field hiện có không bị xóa hoặc đổi tên; field mới phải là optional và client/server không hiểu field mới nên bỏ qua field đó. Do đó, broker cần kiểm tra khả năng tương thích thay vì giả định mọi request có thêm field đều là request lỗi.

### Ma trận kiểm thử version header

Giả sử ứng dụng đang cấu hình yêu cầu phiên bản `2.17`:

| Request header | Kỳ vọng | Mục đích |
|---|---|---|
| `2.17` | Request được xử lý. | Phiên bản đã cấu hình. |
| Thiếu header | `400 Bad Request` nếu broker chọn từ chối theo đặc tả. | Bảo vệ yêu cầu header của OSB API. |
| `2.16` | `412 Precondition Failed` khi framework đang kiểm tra exact version `2.17`. | Phát hiện platform chưa hỗ trợ phiên bản broker yêu cầu. |
| `3.0` | Bị từ chối nếu broker không hỗ trợ major version đó. | Tránh diễn giải nhầm giao thức khác major. |
| Giá trị sai định dạng | Bị từ chối theo validation/version policy của broker. | Không cho version parser nhận dữ liệu không hợp lệ. |

Phân biệt hai trường hợp: OSB API cho phép broker từ chối một phiên bản mà broker không thể hỗ trợ; còn Spring Cloud Open Service Broker khi cấu hình `BrokerApiVersion` sẽ so sánh với phiên bản được cấu hình và trả `412` nếu platform gửi một giá trị khác. Vì vậy cấu hình exact version không đồng nghĩa với một bộ đàm phán tự động hỗ trợ cả dải minor version.

## Cấu hình kiểm tra version trong Spring Cloud Open Service Broker

Theo tài liệu Spring Cloud Open Service Broker 4.4.1, mặc định framework cho phép mọi API version. Có thể bật kiểm tra bằng property:

```yaml
spring:
  cloud:
    openservicebroker:
      apiVersion: "2.17"
```

Hoặc khai báo bean:

```java
@Configuration
public class BrokerApiVersionConfiguration {

    @Bean
    BrokerApiVersion brokerApiVersion() {
        return new BrokerApiVersion("2.17");
    }
}
```

Nếu cả property và bean cùng được khai báo, bean có độ ưu tiên cao hơn. Khi cấu hình một version cụ thể, framework trả `412 Precondition Failed` nếu header platform gửi khác giá trị đã cấu hình. Khi không cấu hình `BrokerApiVersion`, mặc định version verification được để mở theo tài liệu framework.

Trước khi chọn `2.17` hoặc một phiên bản khác, hãy xác định platform thực tế đang gửi version nào và broker có sử dụng tính năng mới nào hay không. Nếu broker chỉ cần tính năng của một phiên bản cũ hơn, đừng pin một version mới hơn mà không có lý do tương thích rõ ràng.

## Kiểm thử version header ở tầng HTTP

Không chỉ unit test lớp version configuration. Cần gửi request HTTP đến endpoint OSB thật trong Spring application context để kiểm tra filter/controller chain xử lý header đúng.

Ví dụ với WebTestClient:

```java
@SpringBootTest(properties = {
    "spring.cloud.openservicebroker.apiVersion=2.17"
})
@AutoConfigureWebTestClient
class ApiVersionContractTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void acceptsConfiguredApiVersion() {
        webTestClient.get()
                .uri("/v2/catalog")
                .header("X-Broker-API-Version", "2.17")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.services").isArray();
    }

    @Test
    void rejectsDifferentApiVersion() {
        webTestClient.get()
                .uri("/v2/catalog")
                .header("X-Broker-API-Version", "2.16")
                .exchange()
                .expectStatus().isEqualTo(412);
    }
}
```

Đây là khung kiểm thử cho ứng dụng WebFlux. Nếu broker dùng Spring MVC, dùng MockMvc theo acceptance test stack tương ứng. Cần cấu hình authentication test nếu endpoint broker được bảo vệ; nếu không, test có thể dừng ở `401` trước khi chạm đến version verifier.

Với header bị thiếu, có thể viết test riêng theo chính sách broker đã chọn. Nếu framework version verifier không tự xử lý trường hợp thiếu như mong muốn, hãy kiểm tra hành vi thực tế và bổ sung lớp validation phù hợp mà không làm thay đổi các request hợp lệ.

## Kiểm thử schema tham số trong catalog

OSB API cho phép service plan công bố JSON Schema cho parameters của service instance và service binding. Các vị trí quan trọng:

- `schemas.service_instance.create.parameters`: tham số provision.
- `schemas.service_instance.update.parameters`: tham số update.
- `schemas.service_binding.create.parameters`: tham số bind.

Ví dụ catalog schema cho plan PostgreSQL:

```json
{
  "schemas": {
    "service_instance": {
      "create": {
        "parameters": {
          "type": "object",
          "required": ["storage_gb"],
          "properties": {
            "storage_gb": {
              "type": "integer",
              "minimum": 10,
              "maximum": 500
            },
            "backup_enabled": {
              "type": "boolean"
            },
            "region": {
              "type": "string",
              "enum": ["ap-southeast-1", "ap-southeast-2"]
            }
          }
        }
      }
    }
  }
}
```

Schema giúp platform biết những field và giá trị nào hợp lệ để hiển thị form hoặc validate sớm. Tuy nhiên broker vẫn phải validate parameters ở server. Client có thể cũ, bỏ qua schema, gửi request trực tiếp hoặc bị lỗi khi chuyển đổi dữ liệu; không được dựa vào platform để bảo đảm mọi request đều hợp lệ.

Schema nên phản ánh chính xác hành vi thực tế của broker. Nếu broker yêu cầu `storage_gb` nhưng catalog không đánh dấu required, platform có thể cho người dùng gửi request thiếu field. Nếu catalog cho phép `region` không được provider hỗ trợ, broker sẽ nhận request mà không thể thực hiện.

## Ma trận tham số hợp lệ và không hợp lệ

Với schema ví dụ ở trên, cần kiểm tra ít nhất các trường hợp:

| Trường hợp | Request mẫu | Kỳ vọng nghiệp vụ |
|---|---|---|
| Giá trị hợp lệ tối thiểu | `{"storage_gb": 10}` | Được chấp nhận. |
| Giá trị hợp lệ tối đa | `{"storage_gb": 500}` | Được chấp nhận. |
| Thiếu field required | `{}` | Bị từ chối trước provider call. |
| Nhỏ hơn minimum | `{"storage_gb": 5}` | Bị từ chối. |
| Lớn hơn maximum | `{"storage_gb": 1000}` | Bị từ chối. |
| Sai kiểu dữ liệu | `{"storage_gb": "50"}` | Bị từ chối nếu schema yêu cầu integer. |
| Enum không hợp lệ | `{"storage_gb": 50, "region": "eu-west-1"}` | Bị từ chối. |
| Sai kiểu boolean | `{"storage_gb": 50, "backup_enabled": "yes"}` | Bị từ chối. |
| JSON malformed | `{"storage_gb":` | `400 Bad Request`. |
| Field không biết | `{"storage_gb": 50, "unknown": true}` | Theo chính sách schema/broker; phải nhất quán với catalog và tài liệu service. |

Ngoài các trường trong bảng, cần kiểm tra `null`, chuỗi rỗng, số thập phân, giá trị biên, ký tự Unicode, payload quá lớn và các tổ hợp tham số có ràng buộc chéo. Ví dụ `backup_enabled=true` có thể yêu cầu plan hỗ trợ backup hoặc storage tối thiểu cao hơn.

## Phân biệt lỗi cú pháp, dữ liệu sai và thay đổi không được hỗ trợ

Không phải mọi lỗi tham số đều dùng cùng HTTP status. Hãy phân loại theo hợp đồng endpoint:

| Tình huống | HTTP status thường dùng theo OSB API | Lưu ý |
|---|---|---|
| JSON malformed, thiếu field bắt buộc hoặc request body không đọc được | `400 Bad Request` | Với invalid data, đặc tả cho phép broker trả 400 cùng `description` hữu ích. |
| Tham số sai schema ở provision/bind | `400 Bad Request` có thể dùng | Validate trước khi tạo tài nguyên/credential; không trả thành công rồi mới phát hiện lỗi. |
| Thay đổi update không được hỗ trợ hoặc trạng thái instance hiện tại không cho phép update | `422 Unprocessable Entity` | Đây là trường hợp được nêu rõ trong update contract. |
| Plan có `maintenance_info.version` mới nhưng request gửi version cũ | `422 Unprocessable Entity` với `MaintenanceInfoConflict` | Platform SHOULD fetch lại catalog. |
| Chỉ hỗ trợ async nhưng request không có `accepts_incomplete=true` | `422 Unprocessable Entity` với `AsyncRequired` | Không bắt đầu side effect bất đồng bộ. |
| Request thay đổi resource đang có operation xung đột | `422 Unprocessable Entity` với `ConcurrencyError` | Platform MUST NOT orphan mitigation cho lỗi concurrency này. |
| Binding cần app nhưng request thiếu `app_guid` theo yêu cầu broker | `422 Unprocessable Entity` với `RequiresApp` | Chỉ dùng khi điều kiện app thực sự bắt buộc. |
| Provision/bind ID đã tồn tại nhưng thuộc tính khác request hiện tại | `409 Conflict` trong các tình huống được endpoint quy định | Phân biệt retry cùng ý định với ID bị tái sử dụng cho request khác. |

`InvalidParameters` không phải error code chuẩn bắt buộc được liệt kê trong phần Service Broker Errors của OSB API. Nếu broker dùng mã này, hãy xem đó là mã riêng do broker định nghĩa. Với lỗi cụ thể mà đặc tả đã quy định error code, phải trả đúng mã chuẩn tương ứng.

Ví dụ response lỗi tham số:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json
```

```json
{
  "error": "InvalidStorageSize",
  "description": "storage_gb phải là số nguyên từ 10 đến 500."
}
```

`InvalidStorageSize` là mã do broker tự định nghĩa. Thông điệp nên giúp người dùng sửa request và không được tiết lộ thông tin nội bộ hoặc secret.

## Kiểm thử capability flags trong catalog

Catalog không chỉ mô tả tên service và plan. Các capability flag cho platform biết những thao tác nào được hỗ trợ. Mỗi flag cần được kiểm tra ở hai phía: giá trị trong response catalog và hành vi endpoint tương ứng.

### Các cờ ở Service Offering

| Field | Ý nghĩa | Kiểm thử cần có |
|---|---|---|
| `bindable` | Giá trị mặc định cho biết instance của service có thể bind hay không; plan có thể override. | Catalog trả đúng giá trị; bind bị từ chối hoặc được hỗ trợ đúng theo effective value. |
| `instances_retrievable` | Broker hỗ trợ fetch service instance cho tất cả plan của service. | Nếu `true`, `GET /v2/service_instances/{instance_id}` hoạt động sau provision thành công. |
| `bindings_retrievable` | Broker hỗ trợ fetch service binding cho các plan bindable. | Nếu `true`, endpoint fetch binding phải hoạt động theo hợp đồng. |
| `allow_context_updates` | Instance hỗ trợ update khi contextual data của platform thay đổi. | Kiểm tra platform context update được xử lý đúng khi flag bật. |
| `plan_updateable` | Giá trị mặc định cho biết service có hỗ trợ nâng cấp/hạ cấp/sidegrade plan. | Nếu bật, handler update phải kiểm tra transition và plan; plan có thể override. |
| `requires` | Các quyền/tài nguyên nền tảng cần cấp khi provision, ví dụ `syslog_drain`, `route_forwarding`, `volume_mount`. | Catalog chỉ liệt kê yêu cầu thực sự được hỗ trợ; test giá trị hợp lệ và trường hợp không hỗ trợ. |

Lưu ý spelling `plan_updateable` là spelling được giữ lại trong OSB API vì lý do tương thích ngược. Không tự đổi thành `plan_updatable` trong JSON response.

### Các cờ ở Service Plan

| Field | Ý nghĩa | Kiểm thử cần có |
|---|---|---|
| `bindable` | Override khả năng bind mặc định của service. | Plan không bindable không được provision binding thành công. |
| `binding_rotatable` | Plan hỗ trợ rotation của service binding. Mặc định `false`. | Chỉ công bố `true` nếu endpoint/flow rotation được hỗ trợ. |
| `plan_updateable` | Override khả năng đổi plan của service. | Kiểm thử ma trận chuyển đổi giữa plan, cả chiều được phép và bị cấm. |
| `schemas` | Schema cho create/update instance và create binding. | Schema response phải khớp với validator và behavior thật. |
| `maximum_polling_duration` | Thời lượng polling tối đa platform SHOULD dùng cho plan. | Giá trị hợp lý, dương và phù hợp thời gian operation. |
| `maintenance_info` | Metadata maintenance, bao gồm version. | Request version cũ phải bị từ chối bằng `MaintenanceInfoConflict` khi điều kiện áp dụng. |

Plan-level `bindable` và `plan_updateable` có thể override service-level default. Vì vậy không chỉ test service object; phải kiểm tra effective capability của từng plan.

## Ma trận kiểm thử capability theo endpoint

| Capability | Bật (`true`) | Tắt (`false` hoặc không khai báo) |
|---|---|---|
| `bindable` | Platform có thể gọi bind cho plan được phép. | Platform không nên gọi bind; broker không cấp binding trái capability. |
| `instances_retrievable` | GET instance phải trả thông tin theo retrieve contract. | Platform SHOULD NOT gọi retrieve endpoint. |
| `bindings_retrievable` | GET binding phải trả binding resource theo contract. | Platform SHOULD NOT gọi retrieve binding endpoint. |
| `allow_context_updates` | Context change có thể dẫn tới update request theo platform behavior. | Broker không được giả định platform sẽ gửi context update. |
| `plan_updateable` | Platform có thể đề xuất đổi plan; broker validate transition cụ thể. | Không quảng cáo khả năng đổi plan. |
| `binding_rotatable` | Rotation flow được công bố và phải thực hiện đúng. | Không công bố rotation; request rotation không được chấp nhận như tính năng đã hỗ trợ. |

Capability là lời hứa của broker với platform. Công bố `true` rồi trả 404/501 hoặc không có handler tương ứng là lỗi hợp đồng. Ngược lại, capability tắt nhưng endpoint vẫn bị platform gọi không nên được dùng để suy ra platform làm sai; cần kiểm tra catalog cache, version và plan override.

## Kiểm thử `plan_updateable` và ma trận đổi plan

Một service có thể hỗ trợ update parameters nhưng không hỗ trợ đổi plan. Vì vậy test cần tách:

- Update parameters trên cùng plan.
- Upgrade từ plan nhỏ lên plan lớn.
- Downgrade từ plan lớn xuống plan nhỏ.
- Sidegrade giữa hai plan cùng tier.
- Chuyển đổi bị cấm do khác loại tài nguyên.
- Plan-level override khác service-level default.

Ví dụ ma trận:

| Plan hiện tại | Plan đích | Chính sách | Kỳ vọng |
|---|---|---|---|
| `small` | `standard` | Cho phép upgrade | Update được chấp nhận. |
| `standard` | `ha` | Cho phép chuyển sang HA | Update được chấp nhận nếu quota đủ. |
| `ha` | `small` | Không cho downgrade | `422 Unprocessable Entity`. |
| `standard` | `archive` | Khác loại storage, không hỗ trợ | `422 Unprocessable Entity` với mô tả rõ. |

Khi `plan_updateable` là `true`, broker vẫn có quyền từ chối một cặp plan cụ thể không hỗ trợ. Flag thể hiện service/plan có khả năng update plan nói chung, không có nghĩa mọi phép chuyển đổi đều hợp lệ.

## Kiểm thử `requires` và bindability

Service field `requires` liệt kê các quyền mà người dùng cần cấp khi provision. Các giá trị OSB API định nghĩa gồm:

- `syslog_drain`
- `route_forwarding`
- `volume_mount`

Test catalog phải xác nhận broker chỉ công bố các yêu cầu mà platform và service thực sự hỗ trợ. Ví dụ service cần route forwarding không được âm thầm bỏ `route_forwarding` khỏi catalog nếu workflow phụ thuộc vào quyền đó.

Với bindability:

1. Test service `bindable=true`, plan không override: binding được phép.
2. Test service `bindable=false`: plan mặc định không bindable.
3. Test service `bindable=true`, plan `bindable=false`: plan đó không bindable.
4. Test service `bindable=false`, plan `bindable=true`: plan override được hỗ trợ theo schema và platform compatibility mà broker công bố.
5. Test plan không bindable nhưng request bind trực tiếp: broker từ chối và không tạo credential/role.

## Kiểm thử API version và capability bằng Spring Test

Có thể gom kiểm tra catalog contract thành integration test. Ví dụ dùng WebTestClient:

```java
@SpringBootTest
@AutoConfigureWebTestClient
class CatalogCapabilityContractTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void catalogAdvertisesOnlySupportedCapabilities() {
        webTestClient.get()
                .uri("/v2/catalog")
                .header("X-Broker-API-Version", "2.17")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.services[0].bindable").isEqualTo(true)
                .jsonPath("$.services[0].instances_retrievable").isEqualTo(true)
                .jsonPath("$.services[0].plans[0].bindable").isEqualTo(false);
    }
}
```

Các giá trị trong assertion là fixture minh họa. Trong test thực tế, chọn catalog fixture của ứng dụng và assert đầy đủ service/plan ID, schema, flags cùng `requires`. Nếu catalog có nhiều service/plan, không phụ thuộc thứ tự mảng; tìm object theo ID hoặc name trước khi assert.

Kiểm thử endpoint tương ứng cần đi xa hơn response catalog. Ví dụ nếu `instances_retrievable=true`, sau khi provision thành công phải gọi được GET instance; nếu `bindings_retrievable=true`, sau bind thành công phải fetch được binding. Nếu `binding_rotatable=true`, test cả predecessor binding, binding mới và trạng thái rotation.

## Kiểm thử invalid parameters trước provider call

Một test quan trọng là xác nhận request không hợp lệ không gây side effect:

```java
@Test
void rejectsStorageBelowMinimumWithoutCallingProvider() {
    webTestClient.put()
            .uri("/v2/service_instances/instance-101")
            .header("X-Broker-API-Version", "2.17")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("""
                {
                  "service_id": "postgres-service",
                  "plan_id": "standard",
                  "parameters": {"storage_gb": 5}
                }
                """)
            .exchange()
            .expectStatus().isBadRequest();

    verifyNoInteractions(providerClient);
}
```

Đây là ví dụ kiểm thử cho policy trả 400 với invalid provision parameters. Tùy endpoint và loại validation, status cụ thể phải theo OSB contract: malformed/missing mandatory data là 400; update không được hỗ trợ hoặc state không cho phép có thể là 422; lỗi `AsyncRequired`, `ConcurrencyError`, `RequiresApp` và `MaintenanceInfoConflict` phải dùng đúng error code chuẩn. `verifyNoInteractions` cần áp dụng cho provider mock tương ứng và chỉ phù hợp khi validation được kỳ vọng diễn ra trước side effect.

Với Spring MVC dùng MockMvc, assertion tương đương có thể kiểm tra status, response JSON `error`/`description` và verify provider service không được gọi.

## Kiểm thử update parameters và giá trị bị bỏ qua

OSB API có quy tắc quan trọng: nếu field `parameters` không xuất hiện trong update request, broker MUST NOT thay đổi parameters của instance do request đó. Nếu field có mặt, platform có thể gửi toàn bộ tập tham số hoặc chỉ một subset; cách diễn giải subset thuộc chính sách service/broker và cần được tài liệu hóa.

Do đó cần test:

- `parameters` bị thiếu: cấu hình hiện tại giữ nguyên.
- `parameters: {}`: xử lý theo semantics broker đã công bố; không tự coi giống field bị thiếu nếu domain model phân biệt hai trường hợp.
- Chỉ gửi một field: các field còn lại được giữ hay reset theo contract của service đã tài liệu hóa.
- Field có giá trị `null`: được chấp nhận, xóa giá trị hay từ chối phải rõ ràng.
- Plan đích không cho phép tham số mới: trả lỗi trước khi gọi provider.
- `previous_values` không khớp state broker: xử lý xung đột theo concurrency policy.

Không dựa vào Java `Map` rỗng để phân biệt field không xuất hiện với object rỗng nếu framework/deserializer đã làm mất thông tin presence. Khi semantics yêu cầu phân biệt, cần kiểm tra request model và cơ chế deserialize của phiên bản thư viện đang dùng.

## Test contract cho error response

Mọi response lỗi cần có status và body đúng:

```json
{
  "error": "InvalidStorageSize",
  "description": "storage_gb phải nằm trong khoảng 10 đến 500."
}
```

Checklist cho error response:

- `error` là chuỗi không rỗng theo camel case.
- `description`, nếu có, là thông điệp không rỗng và có thể hiển thị cho người dùng.
- Các error code chuẩn được dùng đúng tình huống.
- Không đưa stack trace, SQL, password hoặc provider token vào response.
- Với 4xx, tài nguyên broker phải không thay đổi về mặt ngữ nghĩa do request gây ra.
- Với 5xx, broker SHOULD giữ tài nguyên không thay đổi về mặt ngữ nghĩa; nếu có side effect một phần, phải có compensation/reconciliation.
- Không trả 4xx cho lỗi phát sinh sau side effect mà không phục hồi trạng thái về ngữ nghĩa ban đầu.

## Kiểm thử catalog ổn định và tương thích ngược

Platform dùng `id` của service offering và service plan làm định danh bất biến để nhận diện tài nguyên qua các lần fetch catalog. Vì vậy test catalog cần:

1. ID service/plan không thay đổi giữa các lần gọi nếu vẫn là cùng resource.
2. Tên hoặc metadata có thể thay đổi theo chính sách, nhưng không dùng tên để thay thế ID khi so sánh identity.
3. Catalog có ít nhất một plan cho mỗi service offering.
4. Field capability optional được bỏ qua khi không hỗ trợ thay vì khai báo `true` sai sự thật.
5. Field extension mới có prefix riêng và không làm client cũ dừng xử lý.
6. Schema của plan không thay đổi bất ngờ khiến request đang hợp lệ trở thành invalid mà không có chiến lược migration.

Khi hỗ trợ nhiều API version, tạo fixture request/response theo từng phiên bản được platform sử dụng. Kiểm tra minor version cũ không bị phá bởi field mới; field optional mà broker không hiểu phải được xử lý tương thích theo change policy. Nếu broker cần tính năng mới, hãy kiểm tra điều kiện version và trả 412 rõ ràng thay vì âm thầm xử lý sai.

## Bộ test tối thiểu cho bài học

| Nhóm | Ca kiểm thử tối thiểu |
|---|---|
| Version header | Header hợp lệ, thiếu, khác minor, khác major, malformed. |
| Catalog schema | Service/plan IDs ổn định, schema create/update/bind chính xác. |
| Invalid parameters | Required missing, wrong type, boundary, enum invalid, malformed JSON. |
| Capability `bindable` | Service default, plan override, bind bị cấm. |
| Capability retrieve | `instances_retrievable` và `bindings_retrievable` khớp endpoint thật. |
| Capability update | `plan_updateable`, `allow_context_updates`, ma trận chuyển đổi plan. |
| Capability binding | `binding_rotatable`, `requires`, volume/route/system permission. |
| Error mapping | 400, 409, 412, 422 và error code chuẩn. |
| No side effect | Invalid request không gọi provider hoặc tạo record tài nguyên. |
| Async contract | `accepts_incomplete`, `AsyncRequired`, 202 và last_operation. |
| Compatibility | Platform version cũ, field optional mới và catalog refresh. |

## Checklist trước khi phát hành broker

1. Platform request luôn được kiểm tra `X-Broker-API-Version` theo chính sách hỗ trợ.
2. Thiếu version header được xử lý rõ ràng; version không tương thích trả response phù hợp.
3. Cấu hình Spring `BrokerApiVersion` không vô tình pin version khác với platform production.
4. Catalog schema mô tả đúng parameters create, update và binding.
5. Broker validate lại parameters ở server trước provider call.
6. Invalid request không tạo side effect và trả status/error code đúng endpoint.
7. Capability service-level và plan-level được kiểm tra cùng cơ chế override.
8. `plan_updateable` được viết đúng spelling của OSB API.
9. Endpoint retrieve/rotation chỉ được công bố khi thực sự hỗ trợ.
10. `requires` chỉ chứa capability platform/service hỗ trợ.
11. Service/plan ID ổn định qua các lần catalog fetch.
12. Test version, schema, capability và error mapping chạy ở tầng HTTP/application context.
13. Test invalid parameters xác minh provider adapter không được gọi.
14. Response lỗi không làm lộ secret và không che giấu side effect một phần.

## Kết luận

Kiểm thử phiên bản giao thức bảo đảm broker và platform hiểu cùng một hợp đồng OSB API. Kiểm thử parameters xác nhận catalog schema và server-side validation đồng nhất, đồng thời request sai bị từ chối trước khi tạo tài nguyên. Kiểm thử capability flags bảo đảm những gì broker quảng cáo trong catalog khớp với endpoint và behavior thật. Với Spring Cloud Open Service Broker, hãy kiểm tra version header ở tầng HTTP, cấu hình `BrokerApiVersion` có chủ đích, test từng service/plan override và xác minh provider không bị gọi khi request không hợp lệ. Đây là nền tảng để broker tương thích nhiều platform và tránh lỗi chỉ xuất hiện khi chạy production.

## Tài liệu tham khảo

- [Open Service Broker API Specification – API Version Header](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md#api-version-header): yêu cầu `X-Broker-API-Version`, format MAJOR.MINOR và phản hồi khi version không tương thích.
- [Open Service Broker API Specification – Service Offering and Service Plan Objects](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md#service-offering-object): capability flags, plan overrides và catalog schema.
- [Open Service Broker API Specification – Provisioning](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md#provisioning): parameters, response status và validation của provision.
- [Open Service Broker API Specification – Updating a Service Instance](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md#updating-a-service-instance): parameters, `previous_values`, plan update và lỗi 422.
- [Spring Cloud Open Service Broker 4.4.1 – API version verification](https://docs.spring.io/spring-cloud-open-service-broker/docs/4.4.1/reference/#api-version-verification): cấu hình property/bean và hành vi 412.
- [Spring Cloud Open Service Broker 4.4.1 Reference](https://docs.spring.io/spring-cloud-open-service-broker/docs/4.4.1/reference/): catalog, service instance, binding và các service interface của framework.
