# Kiểm thử hợp đồng JSON, HTTP status và header OSB

Service broker giao tiếp với nền tảng bằng Open Service Broker API (OSB API). Hai bên không chỉ trao đổi dữ liệu nghiệp vụ mà còn phải tuân thủ chính xác hợp đồng HTTP: endpoint, method, query parameter, header, JSON request, JSON response và status code. Một broker có thể tạo database thành công ở provider nhưng vẫn bị nền tảng coi là thất bại nếu trả sai status, thiếu operation ID hoặc dùng sai cấu trúc JSON.

Contract test (kiểm thử hợp đồng) xác minh rằng request và response của broker phù hợp với giao thức mà nền tảng mong đợi. Với `SPRING_CLOUD_SERVICE_BROKER`, cần kiểm tra cả luồng đồng bộ và bất đồng bộ của catalog, provision, update, deprovision, bind, unbind và `last_operation`; đồng thời xác minh các header như `X-Broker-API-Version`, `Content-Type`, `Accept` và header nhận diện nền tảng nếu được sử dụng.

Mục tiêu là phát hiện lỗi tương thích ngay trong quá trình phát triển và CI, trước khi broker được đăng ký vào Cloud Foundry hoặc một nền tảng hỗ trợ OSB khác.

## 1. Contract test kiểm tra điều gì?

Một endpoint có thể trả HTTP `200 OK` nhưng body không đúng schema; hoặc trả JSON đúng nhưng status không phù hợp với trạng thái thao tác. Vì vậy, contract test phải kiểm tra nhiều lớp cùng lúc.

| Lớp hợp đồng | Nội dung cần kiểm tra | Ví dụ lỗi |
|---|---|---|
| HTTP routing | Method, path, query parameter | Dùng `POST` thay `PUT` cho provision |
| Request headers | API version, content type, authentication | Thiếu `X-Broker-API-Version` |
| Request JSON | Tên field, kiểu dữ liệu, cấu trúc lồng nhau | `plan_id` bị gửi thành `planId` |
| Response status | Status được OSB quy định cho endpoint và kết quả | Trả `204` cho DELETE thay `200` |
| Response headers | Content type, header hỗ trợ polling nếu có | JSON response nhưng thiếu Content-Type phù hợp |
| Response JSON | Field bắt buộc, field tùy chọn và kiểu dữ liệu | `operation` bị trả thành số thay vì string |
| Error response | Error code và description | Trả HTML stack trace thay vì error JSON |
| Lifecycle semantics | Retry, async polling, idempotency | Retry provision tạo thêm database |

Contract test không chỉ kiểm tra controller đã nhận request. Nó kiểm tra hành vi quan sát được từ phía nền tảng, vì đó là thứ quyết định broker có tương thích hay không.

## 2. Phân biệt unit test, integration test và contract test

Ba loại test có mục đích khác nhau và bổ sung cho nhau.

| Loại test | Phạm vi | Câu hỏi chính |
|---|---|---|
| Unit test | Một mapper, validator hoặc use case | Logic nội bộ có đúng không? |
| Integration test | Spring application, database, security filter, provider adapter giả lập | Các thành phần có phối hợp đúng không? |
| Contract test | HTTP request/response quan sát từ client OSB | Broker có tuân thủ giao thức không? |
| End-to-end test | Broker với Cloud Foundry hoặc nền tảng thử nghiệm | Nền tảng thực tế có thể provision, bind và thu hồi không? |

Ví dụ, unit test có thể chứng minh `ProvisionResult` được ánh xạ thành response model đúng. Contract test cần xác minh HTTP endpoint thực sự trả `201 Created` hoặc `202 Accepted`, body đúng và header đúng. Một test gọi trực tiếp method Java không thể thay thế kiểm tra HTTP contract.

## 3. Phiên bản OSB API và header `X-Broker-API-Version`

Nền tảng gửi header `X-Broker-API-Version` để cho broker biết phiên bản OSB API mà request tuân theo. Ví dụ:

```http
X-Broker-API-Version: 2.17
```

Contract test nên xác minh:

- Request hợp lệ có phiên bản được broker hỗ trợ được chấp nhận.
- Broker không diễn giải request theo một phiên bản khác với header.
- Phiên bản không được hỗ trợ được xử lý theo hợp đồng OSB, thường là `412 Precondition Failed`.
- Thay đổi API version không âm thầm làm thay đổi semantics của status, body hoặc field.
- Các phiên bản mà broker công bố hỗ trợ được kiểm tra bằng test matrix riêng.

Không hard-code một phiên bản trong toàn bộ test nếu broker có chủ đích hỗ trợ nhiều phiên bản. Có thể khai báo constant hoặc test parameter để mỗi phiên bản được kiểm tra tường minh.

Ví dụ khai báo:

```java
final class OsbContract {
    static final String API_VERSION_HEADER = "X-Broker-API-Version";
    static final String API_VERSION = "2.17";
    static final String CATALOG_PATH = "/v2/catalog";
}
```

Tên header HTTP không phân biệt chữ hoa/chữ thường theo chuẩn HTTP, nhưng test nên dùng cách viết chuẩn để tài liệu và log nhất quán.

## 4. Các header cần kiểm tra

Không phải mọi header đều có cùng vai trò. Một số là thành phần giao thức, một số phụ thuộc cấu hình triển khai.

| Header | Chiều | Mục đích | Cách kiểm thử |
|---|---|---|---|
| `X-Broker-API-Version` | Request | Phiên bản OSB API | Có mặt, đúng định dạng và được hỗ trợ |
| `Content-Type` | Request | Kiểu body gửi đến broker | `application/json` khi gửi JSON body |
| `Accept` | Request | Kiểu response client chấp nhận | Broker trả định dạng phù hợp |
| `Authorization` | Request | Xác thực nền tảng với broker | Thiếu/sai credential bị từ chối |
| `X-Broker-API-Originating-Identity` | Request, nếu nền tảng gửi | Thông tin actor/platform theo extension OSB | Parse đúng, không dùng thay authentication |
| `Content-Type` | Response | Kiểu response body | JSON response dùng `application/json` |
| `Retry-After` | Response, khi áp dụng | Gợi ý thời gian trước lần polling tiếp theo | Giá trị hợp lệ và nhất quán với async policy |

### `X-Broker-API-Originating-Identity`

Cloud Foundry có thể gửi header `X-Broker-API-Originating-Identity` để cung cấp danh tính nguồn khởi tạo thao tác. Header này thường mang thông tin platform và value đã được encode theo quy ước của nền tảng. Nếu broker sử dụng nó để audit hoặc policy, cần kiểm tra đúng định dạng, decode an toàn và giới hạn kích thước.

Header originating identity không thay thế `Authorization`. Không được cấp quyền chỉ vì body/header tự khai báo một organization, space hoặc user. Danh tính có thẩm quyền phải đến từ trust boundary đã xác minh của nền tảng.

### Correlation ID và header riêng

Một số môi trường thêm `X-Correlation-ID`, trace header hoặc header riêng của gateway. Chúng hữu ích cho observability nhưng không tự động là header chuẩn của OSB API. Contract test nên phân loại header bắt buộc theo OSB và header mở rộng theo cấu hình nền tảng, tránh vô tình làm broker phụ thuộc vào một header chỉ có ở môi trường phát triển.

## 5. Quy tắc kiểm tra JSON request

JSON là định dạng truyền dữ liệu nhưng tên field và kiểu dữ liệu vẫn thuộc hợp đồng. Ví dụ request provision:

```json
{
  "service_id": "postgres-service",
  "plan_id": "standard",
  "context": {
    "platform": "cloud-foundry",
    "organization_guid": "org-7",
    "space_guid": "space-3"
  },
  "organization_guid": "org-7",
  "space_guid": "space-3",
  "parameters": {
    "storage_gb": 100,
    "backup_enabled": true
  }
}
```

Contract test cần xác minh:

- `service_id` và `plan_id` là string theo định dạng giao thức.
- `context` là object nếu được gửi.
- `parameters` là object và được validate theo schema riêng của service/plan.
- Boolean không bị deserialize thành string như `"true"`.
- Số không bị gửi thành chuỗi nếu schema yêu cầu number/integer.
- Field tùy chọn vắng mặt được xử lý đúng; không tự biến `null`, `""` và field không tồn tại thành cùng một trạng thái nếu nghiệp vụ phân biệt chúng.
- Tên field theo snake_case của OSB không bị thay bằng camelCase của Java model.

Không nên kiểm tra JSON bằng so sánh chuỗi nguyên văn vì thứ tự property không có ý nghĩa trong JSON object. Dùng JSONPath, Jackson tree hoặc JSON Schema để kiểm tra cấu trúc và giá trị.

## 6. Kiểm tra JSON response và schema

Response phải có field và kiểu dữ liệu đúng theo endpoint. Ví dụ catalog:

```json
{
  "services": [
    {
      "id": "postgres-service",
      "name": "postgresql",
      "description": "Managed PostgreSQL database",
      "bindable": true,
      "plans": [
        {
          "id": "standard",
          "name": "standard",
          "description": "Production database plan",
          "free": false
        }
      ]
    }
  ]
}
```

Một test chỉ xác nhận `services` tồn tại là chưa đủ. Nên kiểm tra:

- `services` là array.
- Mỗi service có `id`, `name`, `description` theo schema.
- `id` duy nhất trong catalog.
- `bindable` là boolean.
- `plans` là array và mỗi plan có `id`, `name`, `description`.
- Plan ID duy nhất trong phạm vi service theo quy tắc catalog.
- Các capability như `instances_retrievable`, `bindings_retrievable`, `plan_updateable` hoặc schema chỉ xuất hiện khi có ý nghĩa và đúng kiểu.
- JSON không vô tình chứa password, token hoặc provider credential.

Có thể validate response bằng JSON Schema. Schema test nên theo đúng phiên bản OSB mà broker công bố; không tự tạo schema hẹp hơn đặc tả đến mức từ chối field extension hợp lệ.

## 7. Kiểm tra status code theo endpoint

Status code là một phần quan trọng của contract. Không nên chỉ assert rằng response nằm trong dải `2xx`.

| Endpoint | Kết quả đồng bộ | Kết quả bất đồng bộ | Các tình huống lỗi đáng kiểm tra |
|---|---|---|---|
| `GET /v2/catalog` | `200` | Không áp dụng | `401`, `412`, `5xx` |
| `PUT /v2/service_instances/{id}` provision | `201` khi tạo mới; `200` cho request lặp phù hợp | `202` | `400`, `409`, `422`, `5xx` |
| `PATCH /v2/service_instances/{id}` update | `200` | `202` | `400`, `404`, `409`, `422`, `5xx` |
| `DELETE /v2/service_instances/{id}` deprovision | `200` | `202` | `410` nếu instance không tồn tại, lỗi provider |
| `PUT .../service_bindings/{binding_id}` bind | `201` khi tạo mới; `200` khi request lặp phù hợp | `202` | `400`, `404`, `409`, `422`, `5xx` |
| `DELETE .../service_bindings/{binding_id}` unbind | `200` | `202` | `410` nếu binding không tồn tại |
| `GET .../last_operation` | `200` với state | Không áp dụng | `404`; `410` trong polling async delete theo điều kiện đặc tả |
| `GET instance/binding` | `200` nếu capability được công bố và resource tồn tại | Không áp dụng | `404` nếu không tìm thấy |

Không dùng `204 No Content` thay cho status được OSB quy định chỉ vì response body rỗng. Contract test cần assert chính xác `200`, `201`, `202` hoặc `410` theo endpoint và trạng thái, không dùng `is2xxSuccessful()` làm assertion duy nhất.

## 8. Phân biệt HTTP status với trạng thái nghiệp vụ

HTTP `200 OK` trên endpoint `last_operation` chỉ có nghĩa broker đã đọc và trả trạng thái thành công. Operation bên trong có thể đang `in progress`, `succeeded` hoặc `failed`.

Ví dụ response:

```json
{
  "state": "in progress",
  "description": "Đang tạo database"
}
```

```json
{
  "state": "succeeded",
  "description": "Database đã sẵn sàng"
}
```

```json
{
  "state": "failed",
  "description": "Provider từ chối do hết quota"
}
```

Contract test phải kiểm tra cả status `200` và giá trị `state`. Nếu test chỉ kiểm tra status, broker có thể trả `200` cùng `state=failed` mà test vẫn xanh dù nghiệp vụ thất bại.

Ngược lại, một response `202 Accepted` ở provision có nghĩa thao tác được chấp nhận nhưng chưa hoàn tất. Test phải xác minh operation ID có mặt, có kiểu string và có thể dùng để truy vấn `last_operation`.

## 9. Kiểm thử response đồng bộ và bất đồng bộ

Với thao tác hỗ trợ async, cần có ít nhất hai nhóm test.

### Đồng bộ

- Request không yêu cầu async.
- Provider giả lập hoàn tất trong thời gian xử lý.
- Broker trả status đồng bộ theo endpoint.
- Response body đúng schema; với thao tác không cần body, test xác minh body rỗng theo hợp đồng.
- Không tạo operation record thừa nếu implementation không cần operation cho luồng sync.

### Bất đồng bộ

- Request gửi `accepts_incomplete=true`.
- Broker ghi operation bền vững trước khi trả response.
- Response là `202 Accepted` với operation ID.
- Nền tảng polling đúng endpoint `last_operation`.
- Trạng thái chuyển từ `in progress` sang `succeeded` hoặc `failed`.
- Operation ID không thay đổi khi request được retry cho cùng operation.
- Broker không trả credentials hoặc thông tin tài nguyên chưa sẵn sàng trong response async ban đầu nếu hợp đồng yêu cầu đợi hoàn tất.

Nếu broker chỉ hỗ trợ async cho một thao tác nhưng request không gửi `accepts_incomplete=true`, test cần xác minh lỗi `422` với `error=AsyncRequired`. Nếu request yêu cầu async nhưng broker không hỗ trợ, kiểm tra `AsyncNotSupported` theo capability và semantics OSB.

## 10. Kiểm thử error response

Error response cũng là JSON contract. Ví dụ:

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json
```

```json
{
  "error": "AsyncRequired",
  "description": "Operation requires asynchronous support"
}
```

Các assertion cần có:

- Status code phù hợp với loại lỗi.
- `Content-Type` là JSON khi có JSON error body.
- `error` là mã lỗi ổn định, không phải tên exception Java tùy ý.
- `description` là string có thể hiển thị cho người dùng hoặc vận hành.
- Không có stack trace, SQL, provider token, password hoặc secret.
- Không trả HTTP `200` cùng body báo lỗi nghiệp vụ.
- Lỗi authentication/authorization không tiết lộ resource của tenant khác.

Ví dụ một error body tối thiểu:

```json
{
  "error": "Conflict",
  "description": "Service instance already exists with different parameters"
}
```

Không nên assert toàn bộ câu description nếu câu chữ có thể được cải thiện mà không đổi semantics. Hãy assert error code và một phần thông điệp quan trọng; dùng snapshot test cho nội dung chỉ khi sản phẩm cần giữ nguyên văn bản.

## 11. Kiểm thử idempotency và conflict

Nền tảng có thể retry request khi timeout hoặc mất response. Contract test cần kiểm tra hành vi quan sát được:

| Tình huống | Kết quả cần xác minh |
|---|---|
| Provision lần đầu | `201` và một instance được tạo |
| Provision lặp cùng ID, cùng parameters sau khi hoàn tất | `200` theo semantics idempotent của OSB; không tạo provider resource thứ hai |
| Provision lặp khi operation đang chạy | `202` và cùng operation ID |
| Provision cùng ID nhưng parameters khác | `409 Conflict` |
| Bind lần đầu | `201` và một binding/credential được tạo |
| Bind lặp cùng binding ID và parameters | `200` theo điều kiện đặc tả; không tạo principal thứ hai |
| Bind cùng ID nhưng parameters khác | `409 Conflict` |
| DELETE được gửi lại sau khi xóa | Xử lý `410 Gone` khi resource không còn tồn tại |
| Hai request đồng thời cùng ID | Chỉ một side effect; response nhất quán |

Không chỉ kiểm tra HTTP response. Dùng mock provider verify số lần gọi hoặc đọc repository để xác minh không có resource, principal hay operation trùng.

## 12. Kiểm thử catalog contract

Catalog là endpoint đầu tiên nền tảng thường đọc khi đăng ký broker. Test catalog nên xác minh:

- HTTP `GET /v2/catalog` trả `200`.
- Response có `Content-Type: application/json`.
- Root object có `services` là array.
- Service ID và plan ID ổn định, không trùng.
- `bindable` phản ánh khả năng thực tế.
- Plan metadata, cost, schemas và capabilities có cấu trúc hợp lệ nếu được công bố.
- Catalog không lộ provider account, internal hostname, credential hoặc dữ liệu tenant.
- Catalog response có thể được đọc lặp mà không làm thay đổi trạng thái.
- Header API version được xử lý đúng.

Ví dụ test bằng WebTestClient:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CatalogContractTest {

    @Autowired
    WebTestClient client;

    @Test
    void catalogMatchesOsbContract() {
        client.get()
                .uri("/v2/catalog")
                .header("X-Broker-API-Version", "2.17")
                .accept(MediaType.APPLICATION_JSON)
                .headers(headers -> headers.setBasicAuth("broker", "test-secret"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.services").isArray()
                .jsonPath("$.services[0].id").isNotEmpty()
                .jsonPath("$.services[0].name").isNotEmpty()
                .jsonPath("$.services[0].bindable").isBoolean()
                .jsonPath("$.services[0].plans").isArray()
                .jsonPath("$.services[0].plans[0].id").isNotEmpty();
    }
}
```

Đây là ví dụ cho Spring WebFlux. Nếu ứng dụng dùng Spring MVC, có thể dùng MockMvc với các assertion tương đương. Credential trong test phải là giá trị giả lập, không dùng thông tin production.

## 13. Kiểm thử provision và header/body

Ví dụ kiểm tra provision đồng bộ:

```java
@Test
void provisionCreatesNewInstance() {
    client.put()
            .uri("/v2/service_instances/instance-42?service_id=postgres-service&plan_id=standard")
            .header("X-Broker-API-Version", "2.17")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .headers(headers -> headers.setBasicAuth("broker", "test-secret"))
            .bodyValue(Map.of(
                    "service_id", "postgres-service",
                    "plan_id", "standard",
                    "parameters", Map.of("storage_gb", 100)))
            .exchange()
            .expectStatus().isCreated();

    verify(providerClient).createDatabase(any());
}
```

Ví dụ kiểm tra async:

```java
@Test
void provisionCanBeAcceptedAsynchronously() {
    client.put()
            .uri("/v2/service_instances/instance-43?service_id=postgres-service&plan_id=standard&accepts_incomplete=true")
            .header("X-Broker-API-Version", "2.17")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of(
                    "service_id", "postgres-service",
                    "plan_id", "standard",
                    "parameters", Map.of("storage_gb", 500)))
            .exchange()
            .expectStatus().isAccepted()
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.operation").isNotEmpty();
}
```

Test async nên lấy operation ID từ response, sau đó gọi `last_operation` bằng ID thực tế để kiểm tra vòng đời thay vì chỉ kiểm tra `202`.

## 14. Kiểm thử `last_operation`

Một test có thể mô phỏng provider job tiến triển qua các trạng thái:

1. Khi operation mới được tiếp nhận, `last_operation` trả `200` và `state=in progress`.
2. Sau khi provider hoàn tất, endpoint trả `200` và `state=succeeded`.
3. Nếu provider thất bại cuối cùng, endpoint trả `200` và `state=failed` cùng description an toàn.
4. Với async delete, kiểm tra semantics `410 Gone` khi resource đã bị xóa và nền tảng cần quên instance/binding theo đặc tả.
5. Với instance/binding ID không tồn tại, kiểm tra `404` ở endpoint polling thông thường.

Ví dụ:

```java
client.get()
        .uri("/v2/service_instances/instance-43/last_operation?operation=op-43")
        .header("X-Broker-API-Version", "2.17")
        .headers(headers -> headers.setBasicAuth("broker", "test-secret"))
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.state").isEqualTo("in progress");
```

Endpoint polling nên đọc operation store đã lưu. Test có thể tắt provider mock sau khi operation được tạo để chứng minh `last_operation` không gọi provider đồng bộ mỗi lần nền tảng polling.

## 15. Kiểm thử bind và unbind

Bind contract test nên xác minh:

- `PUT` đúng path và có `service_id`, `plan_id` theo query.
- Request body hỗ trợ `context`, `bind_resource` và `parameters` theo schema.
- Binding mới trả `201 Created` với response credentials hợp lệ.
- Binding lặp phù hợp trả `200` và không tạo credential mới.
- Binding bất đồng bộ trả `202` cùng operation ID khi request chấp nhận async.
- Credentials có field đúng kiểu và không chứa thông tin ngoài phạm vi consumer.

Unbind contract test nên xác minh:

- `DELETE` đúng path binding.
- Unbind đồng bộ trả `200` theo hợp đồng và body theo response schema (thường không có payload nghiệp vụ).
- Unbind async trả `202` khi được yêu cầu và hỗ trợ.
- Binding không tồn tại trả `410 Gone` theo semantics DELETE.
- Provider principal được thu hồi đúng binding, không thu hồi binding khác.
- Request lặp không gây lỗi side effect hoặc xóa nhầm instance.

Không giả định `bind_resource` luôn có mặt. Test cả binding có `app_guid`, binding có route và consumer không gắn application nếu service cho phép.

## 16. Kiểm thử deprovision và response xóa

Deprovision contract test nên bao gồm:

- DELETE đồng bộ hoàn tất và trả `200`.
- DELETE async trả `202` với operation ID nếu `accepts_incomplete=true`.
- Instance không tồn tại trả `410 Gone`.
- Provider timeout không bị giả mạo thành thành công.
- Request lặp trong lúc đang deprovision giữ cùng operation ID.
- Sau khi xóa, GET instance không còn trả dữ liệu hoạt động.
- Không xóa resource thuộc instance khác do nhầm provider mapping.

Đối với `200` response body rỗng, test phải phản ánh đúng hợp đồng của endpoint. Không ép mọi response thành JSON object nếu OSB cho phép body rỗng; cũng không đổi status thành `204` để làm test dễ hơn.

## 17. Kiểm tra JSON Schema

JSON Schema giúp kiểm tra cấu trúc lồng nhau và kiểu dữ liệu. Có thể dùng thư viện validator trong test để validate fixture response hoặc body nhận được.

Một schema rút gọn minh họa cho `last_operation`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["state"],
  "properties": {
    "state": {
      "type": "string",
      "enum": ["in progress", "succeeded", "failed"]
    },
    "description": {
      "type": "string"
    }
  },
  "additionalProperties": true
}
```

Đây là schema rút gọn để minh họa, không thay thế schema đầy đủ của OSB API. Với catalog hoặc binding response, cần dùng schema tương ứng và xử lý field extension theo quy tắc đặc tả.

### Không overfit schema test

- Chỉ yêu cầu field bắt buộc theo phiên bản OSB đang kiểm tra.
- Cho phép field tùy chọn vắng mặt khi hợp đồng cho phép.
- Không khóa thứ tự property trong JSON.
- Không giả định provider metadata phải xuất hiện trong response công khai.
- Không cấm extension hợp lệ nếu OSB cho phép broker mở rộng response.
- Kiểm tra type và semantics thay vì chỉ kiểm tra tên field.

## 18. Kiểm tra header âm tính và bảo mật

Contract test cũng cần xác minh broker từ chối request không hợp lệ:

| Request | Kết quả cần xác minh |
|---|---|
| Thiếu `X-Broker-API-Version` | Xử lý theo yêu cầu phiên bản giao thức và policy broker |
| API version không hỗ trợ | `412 Precondition Failed` theo OSB |
| Thiếu Authorization | `401 Unauthorized` hoặc response auth được cấu hình |
| Credential sai | Bị từ chối, không gọi provider |
| JSON body malformed | `400 Bad Request` |
| Content-Type không phù hợp khi gửi JSON | Từ chối theo HTTP/framework contract |
| Originating identity sai định dạng | Không crash; xử lý theo policy và không cấp quyền từ dữ liệu chưa xác minh |
| Tenant/space không thuộc instance | Từ chối, không trả dữ liệu tenant khác |
| Header quá lớn hoặc chứa ký tự không hợp lệ | Bị giới hạn và xử lý an toàn |

Test authentication cần xác minh request bị chặn trước khi provider adapter được gọi. Điều này giúp tránh lỗi chỉ được phát hiện sau khi đã tạo tài nguyên hoặc credentials.

## 19. Contract test với Spring WebTestClient và MockMvc

`WebTestClient` phù hợp với ứng dụng WebFlux và có thể kiểm tra HTTP end-to-end trong Spring test context. `MockMvc` phù hợp với Spring MVC. Cả hai cho phép kiểm tra status, header, JSONPath và body.

Ví dụ kiểm tra error response:

```java
@Test
void unsupportedApiVersionReturnsPreconditionFailed() {
    client.get()
            .uri("/v2/catalog")
            .header("X-Broker-API-Version", "99.0")
            .headers(headers -> headers.setBasicAuth("broker", "test-secret"))
            .exchange()
            .expectStatus().isEqualTo(HttpStatus.PRECONDITION_FAILED)
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.error").isNotEmpty()
            .jsonPath("$.description").isNotEmpty();
}
```

Ví dụ kiểm tra request thiếu authentication:

```java
@Test
void catalogRequiresBrokerAuthentication() {
    client.get()
            .uri("/v2/catalog")
            .header("X-Broker-API-Version", "2.17")
            .exchange()
            .expectStatus().isUnauthorized();

    verifyNoInteractions(providerClient);
}
```

Các ví dụ cần được điều chỉnh theo security configuration, base path và phiên bản Spring Cloud Open Service Broker thực tế. Không tạo controller test-only để bỏ qua filter hoặc endpoint routing mà production đang sử dụng.

## 20. Kiểm tra response không làm lộ dữ liệu nhạy cảm

Contract test nên kiểm tra những field tuyệt đối không được xuất hiện trong response không liên quan:

- Provider API token hoặc access key.
- Database administrator password.
- Private key hoặc secret encryption key.
- Internal provider account credential.
- Stack trace, SQL statement chứa dữ liệu nhạy cảm.
- Secret của binding khác hoặc tenant khác.

Ví dụ kiểm tra body không chứa tên field nhạy cảm:

```java
String response = result.getResponse().getContentAsString();
assertThat(response).doesNotContain("provider_admin_password");
assertThat(response).doesNotContain("access_token");
assertThat(response).doesNotContain("-----BEGIN PRIVATE KEY-----");
```

Không chỉ kiểm tra tên field. Secret có thể bị lồng trong `description`, nested object hoặc debug property. Với test có secret giả lập, có thể kiểm tra giá trị canary không xuất hiện trong bất kỳ response/log nào ngoài nơi được phép.

## 21. Test fixture và quản lý dữ liệu kiểm thử

Fixture giúp giữ request/response mẫu ổn định và dễ review. Có thể tổ chức theo endpoint và phiên bản OSB:

```text
src/test/resources/osb/v2.17/
  catalog-response.json
  provision-request.json
  provision-created-response.json
  provision-accepted-response.json
  update-request.json
  bind-request.json
  bind-created-response.json
  last-operation-in-progress.json
  last-operation-succeeded.json
  error-async-required.json
```

Nguyên tắc quản lý fixture:

- Chỉ dùng ID, hostname và secret giả lập.
- Ghi chú endpoint và tình huống tương ứng.
- Không copy response production có dữ liệu tenant.
- Khi cập nhật OSB API version, review thay đổi fixture và schema cùng lúc.
- Không dùng một fixture chung cho response sync và async nếu body/status khác nhau.
- Giữ test data đủ nhỏ để người review hiểu được contract.

## 22. Kiểm thử tích hợp với provider giả lập

Contract test của OSB không nên phụ thuộc dịch vụ cloud thật trong mỗi lần chạy. Dùng provider stub hoặc WireMock/MockWebServer để kiểm soát response:

- Provider create trả resource ID và trạng thái hoàn tất.
- Provider create trả job ID đang chạy.
- Provider trả `429`, `5xx`, timeout hoặc JSON lỗi.
- Provider trả trạng thái không biết.
- Provider trả response malformed.
- Provider job hoàn tất nhưng resource chưa sẵn sàng.
- Provider đã tạo resource nhưng broker mất kết nối trước khi lưu mapping.

Sau đó kiểm tra broker phản ánh đúng OSB contract. Ví dụ provider timeout không nên khiến broker trả `201 Created` nếu resource chưa được xác minh. Nếu broker đã chấp nhận async, response `202` phải đi cùng operation record bền vững và `last_operation` phải phản ánh tiến trình.

## 23. Kiểm thử concurrency và retry

Một broker có nhiều replica và nền tảng có thể gửi request đồng thời. Contract test hoặc integration test nên mô phỏng:

- Hai PUT provision cùng `instance_id` và parameters đến đồng thời.
- Hai PUT binding cùng `binding_id` đến đồng thời.
- DELETE binding chạy đồng thời với một request bind mới.
- Update chạy trong khi deprovision được gửi đến.
- Hai poller cùng đọc/cập nhật một provider job.
- Request retry đến một replica khác sau khi replica đầu đã commit operation.

Kết quả cần bảo đảm:

- Database unique constraint và locking ngăn tạo record trùng.
- Provider side effect không bị lặp nếu idempotency key được hỗ trợ.
- Operation ID ổn định cho cùng một request.
- Response của các request cạnh tranh nhất quán với trạng thái cuối.
- Không có response thành công khi dữ liệu mapping chưa được lưu bền vững.

## 24. Contract test trong CI

Một pipeline CI có thể chạy các nhóm kiểm tra theo thứ tự:

1. Compile và unit tests cho mapper/validator.
2. JSON Schema validation cho fixture.
3. Spring HTTP contract tests cho status, header và body.
4. Integration tests với database test và provider stub.
5. Security tests cho authentication, tenant isolation và secret leakage.
6. Concurrency/retry tests cho idempotency và operation store.
7. Optional sandbox tests với Cloud Foundry hoặc provider staging trước release.

Không cần chạy test với provider production trong mỗi commit. Sandbox tests có thể chạy theo lịch hoặc trước release lớn, còn contract test nhanh phải chạy thường xuyên.

Khi contract test thất bại, báo rõ endpoint, request fixture, API version, expected status/header/body và actual result. Tránh log bearer token hoặc secret trong CI output.

## 25. Ma trận contract test tổng hợp

| Nhóm | Ca kiểm thử tối thiểu | Assertion chính |
|---|---|---|
| Catalog | GET catalog hợp lệ, version sai, auth sai | `200`, JSON schema, `412`, `401` |
| Provision | Sync create, async accept, retry, conflict | `201`, `202`, `200`, `409` và body phù hợp |
| Update | Sync update, async update, invalid parameters | `200`, `202`, `422` |
| Deprovision | Sync delete, async delete, missing instance | `200`, `202`, `410` |
| Binding | Create, retry, async, conflict | `201`, `200`, `202`, `409` và credentials |
| Unbinding | Sync, async, missing binding | `200`, `202`, `410` |
| Last operation | In progress, succeeded, failed, delete complete | `200` cùng state; `410` đúng ngữ cảnh delete |
| Fetch | Instance/binding retrievable | `200`, `404`, capability đúng |
| Headers | Version, content type, auth, originating identity | Header được parse và xác thực đúng |
| Errors | Malformed JSON, unsupported version, provider failure | Status và error JSON đúng, không lộ secret |
| Reliability | Retry, concurrency, restart | Idempotency, mapping bền vững, không tạo resource trùng |

## 26. Những lỗi contract test thường gặp

**Chỉ kiểm tra status thuộc 2xx:** `204` có thể lọt qua dù không đúng hợp đồng OSB. Assert chính xác status theo endpoint.

**Chỉ kiểm tra status mà bỏ qua body:** `last_operation` có thể trả `200` cùng `state=failed`. Assert cả JSON state.

**So sánh JSON bằng chuỗi:** test thất bại vì thứ tự key thay đổi dù JSON tương đương. Dùng JSONPath hoặc JSON Schema.

**Không test API version:** broker có thể chấp nhận request không hỗ trợ hoặc diễn giải sai contract. Test version header và `412`.

**Bỏ qua auth trong test:** endpoint hoạt động trong test nhưng bị chặn hoặc mở sai trong production. Test security filter thực tế.

**Test chỉ gọi service method:** không phát hiện lỗi path, query, serialization, content type hoặc HTTP mapping. Dùng WebTestClient/MockMvc.

**Dùng provider thật cho mọi test:** test chậm và phụ thuộc mạng, quota, trạng thái cloud. Dùng stub có kiểm soát và thêm sandbox test riêng.

**Fixture chứa secret thật:** có nguy cơ lộ qua repository và CI. Chỉ dùng dữ liệu giả lập.

**Không test retry/concurrency:** broker có thể tạo nhiều resource khi nền tảng gửi lại request. Kiểm tra idempotency ở cả response và provider side effect.

## 27. Trình tự xây dựng contract test cho service broker

Khi xây dựng test suite cho `SPRING_CLOUD_SERVICE_BROKER`, có thể thực hiện theo trình tự:

1. Chốt phiên bản OSB API và lập danh sách endpoint broker hỗ trợ.
2. Ghi rõ request method/path/query/header và JSON schema của từng endpoint.
3. Lập bảng status đồng bộ, bất đồng bộ, idempotent và lỗi cho từng thao tác.
4. Tạo fixture JSON chỉ dùng dữ liệu giả lập.
5. Viết HTTP contract tests bằng WebTestClient hoặc MockMvc trên Spring application context.
6. Validate catalog, provision, update, deprovision, bind, unbind và `last_operation`.
7. Test header version, authentication, content type và originating identity theo nền tảng.
8. Test error response, JSON schema, secret leakage và tenant isolation.
9. Dùng provider stub để kiểm tra timeout, retry, async job và partial failure.
10. Mô phỏng request lặp/concurrent và xác minh không có side effect trùng.
11. Chạy test trong CI và lưu kết quả theo endpoint/API version.
12. Bổ sung sandbox integration trước release khi cần xác minh tương tác với foundation thực tế.

Contract test có giá trị khi nó mô phỏng đúng cách nền tảng nhìn thấy broker. Kiểm tra đồng thời JSON, HTTP status và header giúp phát hiện lỗi giao thức trước khi chúng gây ra provision thất bại, binding sai, operation bị polling vô hạn hoặc tài nguyên mồ côi. Khi kết hợp với integration test, idempotency test và sandbox test, đội phát triển có thể thay đổi implementation Spring mà vẫn giữ hợp đồng OSB ổn định.
