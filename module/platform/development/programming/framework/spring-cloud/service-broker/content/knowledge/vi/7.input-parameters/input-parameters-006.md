# Chuẩn hóa tham số và từ chối trường không được hỗ trợ

Trong Open Service Broker API (OSB API), trường `parameters` cho phép consumer truyền thêm dữ liệu để tùy biến một service instance hoặc một service binding. Các tham số này có thể quyết định tên database, dung lượng, phiên bản engine, chính sách backup hoặc cấu hình kết nối. Vì dữ liệu đến từ bên ngoài và có thể ảnh hưởng trực tiếp đến tài nguyên hạ tầng, broker phải xác định rõ tham số nào được hỗ trợ, chuẩn hóa chúng về dạng nhất quán và từ chối những trường không hợp lệ hoặc không được phép.

Trong module `SPRING_CLOUD_SERVICE_BROKER`, việc chuẩn hóa tham số là một phần của ranh giới giữa hợp đồng OSB API và logic cấp phát tài nguyên. Broker cần áp dụng cùng quy tắc khi chạy đồng bộ, bất đồng bộ, retry hoặc update để một request không tạo ra kết quả khác nhau chỉ vì cách viết giá trị đầu vào.

## 1. Vai trò của parameters trong OSB API

`parameters` là một JSON object chứa các tùy chọn mà broker hiểu theo service, plan và thao tác đang được gọi. Nó không thay thế các định danh chuẩn của OSB API như `service_id`, `plan_id`, `instance_id` hoặc `binding_id`.

Ví dụ request provision:

~~~json
{
  "service_id": "svc-postgresql",
  "plan_id": "plan-postgresql-standard",
  "parameters": {
    "database_name": "orders",
    "storage_gb": 150,
    "engine_version": "16",
    "backup": {
      "enabled": true,
      "retention_days": 14
    }
  }
}
~~~

Trong ví dụ này:

- `service_id` chọn loại dịch vụ PostgreSQL.
- `plan_id` chọn gói cấu hình `standard`.
- `parameters` tùy biến instance trong giới hạn của plan.
- Broker chịu trách nhiệm kiểm tra từng field, áp dụng mặc định và chuyển giá trị hợp lệ thành cấu hình backend.

Tham số có thể xuất hiện trong các thao tác khác nhau. Provision parameters thường mô tả cấu hình ban đầu của instance; update parameters mô tả thay đổi được yêu cầu; binding parameters có thể tùy biến cách tạo quyền truy cập hoặc cấu hình consumer. Không nên mặc định một field hợp lệ trong provision cũng hợp lệ trong update hoặc bind.

## 2. Vì sao phải chuẩn hóa tham số?

Hai request có thể mang cùng ý nghĩa nghiệp vụ nhưng khác cách biểu diễn:

~~~json
{ "storage_gb": 150 }
~~~

~~~json
{ "storage_gb": 150.0 }
~~~

Nếu schema yêu cầu số nguyên, broker nên chấp nhận hoặc từ chối theo một quy tắc rõ ràng. Không nên để backend tự diễn giải tùy tiện. Tương tự, các giá trị chuỗi có thể có khoảng trắng thừa, chữ hoa/thường, Unicode khác dạng chuẩn hoặc định dạng không nhất quán.

Chuẩn hóa (normalization/canonicalization) giúp:

1. Chuyển đầu vào về một biểu diễn nội bộ thống nhất.
2. Làm cho validation và so sánh giá trị có thể dự đoán.
3. Tính fingerprint/idempotency ổn định khi request được gửi lại.
4. Tránh backend nhận các cấu hình khác nhau do khác biệt định dạng.
5. Tạo log và audit dễ đọc mà không lưu dữ liệu nhạy cảm.
6. Tách logic nghiệp vụ khỏi kiểu dữ liệu thô của JSON parser.

Chuẩn hóa không có nghĩa là tự sửa mọi dữ liệu người dùng. Chỉ thực hiện các phép biến đổi đã được định nghĩa trong hợp đồng. Ví dụ, có thể loại bỏ khoảng trắng đầu/cuối của một field tên nếu điều đó được cho phép; không nên tự đổi tên database hoặc viết thường mật khẩu vì có thể làm thay đổi ý nghĩa.

## 3. Hợp đồng tham số theo service, plan và thao tác

Một broker nên xác định schema và chính sách tham số theo ít nhất ba chiều:

- **Service:** nhóm dịch vụ và các field có ý nghĩa.
- **Plan:** giới hạn hoặc khả năng khác nhau giữa các gói.
- **Operation:** provision, update, bind hoặc thao tác khác.

Ví dụ:

| Tham số | Provision | Update | Bind | Ghi chú |
|---|---|---|---|---|
| `database_name` | Có | Không | Không | Xác định database khi tạo |
| `storage_gb` | Có | Có | Không | Phải nằm trong giới hạn plan và quota |
| `backup.retention_days` | Có | Có | Không | Plan phải hỗ trợ backup |
| `engine_version` | Có | Có điều kiện | Không | Chỉ cho phép nâng cấp theo ma trận tương thích |
| `username_prefix` | Không | Không | Có thể có | Tùy chính sách tạo credential |
| `read_only` | Không | Không | Có thể có | Quyền riêng của binding |

Bảng chỉ là ví dụ cho một broker PostgreSQL. Schema thực tế cần phản ánh hợp đồng sản phẩm và khả năng backend.

### Công bố schema trong catalog

OSB API cho phép broker công bố schema cho parameters của plan thông qua phần `schemas` trong catalog, khi broker hỗ trợ khả năng đó. Schema giúp platform hoặc giao diện người dùng biết field nào được chấp nhận và kiểu dữ liệu mong đợi.

Ví dụ rút gọn:

~~~json
{
  "id": "plan-postgresql-standard",
  "name": "standard",
  "schemas": {
    "service_instance": {
      "create": {
        "parameters": {
          "$schema": "http://json-schema.org/draft-04/schema#",
          "type": "object",
          "additionalProperties": false,
          "properties": {
            "database_name": {
              "type": "string",
              "minLength": 1,
              "maxLength": 40
            },
            "storage_gb": {
              "type": "integer",
              "minimum": 50,
              "maximum": 250
            },
            "backup": {
              "type": "object",
              "additionalProperties": false,
              "properties": {
                "enabled": { "type": "boolean" },
                "retention_days": {
                  "type": "integer",
                  "minimum": 1,
                  "maximum": 30
                }
              }
            }
          },
          "required": ["database_name"]
        }
      }
    }
  }
}
~~~

Giá trị `maxLength` trong ví dụ là 40 ký tự để minh họa giới hạn tên database. Schema công bố là tài liệu hợp đồng, không phải cơ chế thực thi thay cho validation phía broker. Client có thể không kiểm tra schema hoặc có thể gửi request trực tiếp.

Nếu broker không công bố schema, nó vẫn phải có schema nội bộ hoặc validator tương đương. Cả catalog và server-side validator nên được tạo từ cùng một định nghĩa để tránh tình trạng tài liệu cho phép một field nhưng handler lại từ chối, hoặc ngược lại.

## 4. Phân biệt field thiếu, null và giá trị mặc định

JSON có thể biểu diễn ba tình huống khác nhau:

~~~json
{}
~~~

~~~json
{ "storage_gb": null }
~~~

~~~json
{ "storage_gb": 100 }
~~~

- **Thiếu field:** consumer không gửi giá trị. Broker có thể áp dụng default nếu hợp đồng định nghĩa.
- **Null:** consumer gửi giá trị null một cách tường minh. Broker cần quy định null có nghĩa là xóa cấu hình, không chỉ định, hay không hợp lệ.
- **Có giá trị:** broker validate kiểu, miền giá trị và quyền sử dụng.

Không nên tự động coi null giống như field thiếu. Đối với một tham số bắt buộc, cả hai có thể bị từ chối nhưng lý do cần rõ ràng. Đối với update, null đôi khi có thể được dùng để yêu cầu xóa một cấu hình tùy chọn; chỉ hỗ trợ khi schema và semantics đã định nghĩa.

Default cũng cần có nguồn rõ ràng. Có thể lấy default từ service, plan hoặc policy tenant. Nên áp dụng theo thứ tự đã thống nhất, ví dụ:

~~~text
effective_value =
    explicit_validated_parameter
    ?? plan_default
    ?? service_default
~~~

Không dùng giá trị mặc định để âm thầm che giấu một giá trị null hoặc sai kiểu đã được gửi tường minh. Nếu field có mặt nhưng không hợp lệ, hãy trả lỗi validation.

## 5. Từ chối field không được hỗ trợ

Một lỗi thường gặp là nhận mọi field trong JSON rồi bỏ qua field mà broker không biết. Điều này khiến lỗi đánh máy trở thành cấu hình thành công giả.

Ví dụ người dùng gửi:

~~~json
{
  "database_name": "orders",
  "storage_gb": 150,
  "backkup_retention_days": 14
}
~~~

Field đúng có thể là `backup_retention_days`, nhưng request lại gửi `backkup_retention_days`. Nếu broker bỏ qua field lạ và provision thành công, người dùng có thể nghĩ backup retention đã được thiết lập trong khi thực tế không có.

Một chính sách chặt chẽ nên:

1. Xác định allowlist field ở đúng service/plan/operation.
2. Từ chối field không được hỗ trợ ở cấp cao nhất.
3. Kiểm tra field lạ lồng bên trong object con.
4. Trả lỗi có tên field để consumer sửa request.
5. Không đưa giá trị nhạy cảm của field vào error message hoặc log.
6. Không âm thầm chuyển field lạ thành một tham số khác bằng fuzzy matching.

Có trường hợp broker cần mở rộng tương thích với client cũ hoặc cho phép metadata tùy chỉnh. Khi đó, hãy thiết kế một namespace riêng hoặc allowlist extension có version, thay vì mở `additionalProperties` vô hạn. Chính sách ignore field chỉ nên dùng khi hợp đồng của broker chủ động định nghĩa hành vi đó và người dùng không thể hiểu nhầm rằng field đã được áp dụng.

### Từ chối field lạ ở object lồng nhau

Kiểm tra chỉ ở cấp ngoài là chưa đủ. Ví dụ:

~~~json
{
  "backup": {
    "enabled": true,
    "retention_days": 14,
    "send_credentials_to": "external.example"
  }
}
~~~

Nếu `backup` là object có schema đóng, field `send_credentials_to` cũng phải bị từ chối. Validation đệ quy phải áp dụng cho từng object và array, không chỉ kiểm tra danh sách key đầu tiên.

## 6. Kiểu dữ liệu và miền giá trị

Không nên dựa vào ép kiểu tự động của JSON parser hoặc database để chấp nhận đầu vào. Mỗi field cần có kiểu và miền giá trị rõ ràng.

| Kiểu | Ví dụ hợp lệ | Kiểm tra cần có |
|---|---|---|
| String | `"orders"` | Độ dài, charset, pattern, Unicode, reserved names |
| Integer | `150` | Phải là số nguyên, giới hạn min/max, overflow |
| Decimal | `0.75` | Precision/scale, miền giá trị |
| Boolean | `true` | Không nhận chuỗi `"true"` nếu schema yêu cầu boolean |
| Enum | `"daily"` | Chỉ nhận một giá trị trong danh sách công bố |
| Array | `["read", "write"]` | Số phần tử, kiểu phần tử, trùng lặp |
| Object | `{"enabled": true}` | Field được phép, required, nesting depth |

Ví dụ, nếu `storage_gb` yêu cầu integer thì `"150"` là string và `150.5` là decimal; không tự động ép cả hai thành 150. Việc ép kiểu có thể làm mất dữ liệu hoặc tạo ra hành vi không thống nhất giữa các backend.

Với enum, so sánh theo quy tắc đã công bố. Không tự chuyển `"Daily"` thành `"daily"` nếu hợp đồng phân biệt chữ hoa/thường. Với tên tài nguyên, cần kiểm tra độ dài, ký tự hợp lệ, tên dành riêng và quy tắc duy nhất của backend.

## 7. Chuẩn hóa từng loại dữ liệu

Chuẩn hóa phải được xác định theo semantics của từng field:

- **String:** loại bỏ khoảng trắng đầu/cuối nếu cho phép; giữ nguyên field có ý nghĩa phân biệt khoảng trắng; giới hạn Unicode và ký tự.
- **Identifier:** có thể chuẩn hóa theo quy tắc cụ thể như lowercase ASCII nếu backend không phân biệt hoa/thường; kiểm tra collision sau chuẩn hóa.
- **Integer/decimal:** parse thành kiểu số có giới hạn; không dùng floating point cho giá trị cần độ chính xác như tiền hoặc quota thập phân.
- **Boolean:** chỉ nhận JSON boolean.
- **Enum:** ánh xạ sang giá trị nội bộ chuẩn bằng danh sách cho phép.
- **Array:** giữ hoặc sắp xếp thứ tự tùy semantics; chỉ loại bỏ phần tử trùng nếu hợp đồng định nghĩa array như tập hợp.
- **Object:** chuẩn hóa đệ quy theo schema, không giữ field lạ.
- **Timestamp/date:** yêu cầu định dạng rõ ràng, múi giờ và độ chính xác thống nhất.

Không nên dùng một hàm `trimAndLowercaseAllStrings` cho toàn bộ JSON. Hàm đó có thể làm hỏng mật khẩu, token, giá trị phân biệt hoa/thường hoặc dữ liệu người dùng. Chuẩn hóa phải dựa trên metadata của từng field, không dựa trên phỏng đoán về kiểu nội dung.

### Unicode và tên tài nguyên

Hai chuỗi nhìn giống nhau có thể có cách mã hóa Unicode khác nhau. Nếu backend yêu cầu canonical form, broker có thể chuẩn hóa Unicode theo dạng được quy định (chẳng hạn NFC) trước khi kiểm tra uniqueness. Tuy nhiên, không được tự ý biến đổi dữ liệu mà backend xem là opaque hoặc case-sensitive.

Đối với tên database, queue hoặc bucket, nên có validator chuyên biệt cho từng loại tài nguyên. Regex tổng quát có thể bỏ sót reserved word, giới hạn độ dài theo byte, hoặc quy tắc tên theo engine. Cần kiểm tra cả giá trị trước và sau chuẩn hóa để phát hiện collision.

## 8. Validation nhiều lớp

Validation nên diễn ra trước khi tạo hoặc thay đổi tài nguyên:

1. **JSON parsing:** body hợp lệ, object có cấu trúc đúng, không có key trùng nếu parser hỗ trợ kiểm tra.
2. **Shape validation:** `parameters` phải là object khi được gửi; kiểm tra nesting depth, số phần tử và kích thước.
3. **Schema validation:** field được phép, required, kiểu dữ liệu, enum, pattern, min/max.
4. **Canonicalization:** chuẩn hóa field theo quy tắc đã định nghĩa.
5. **Cross-field validation:** kiểm tra quan hệ giữa các field.
6. **Plan validation:** kiểm tra giá trị có phù hợp với service plan được chọn.
7. **Tenant policy/quota:** xác nhận caller có quyền và còn hạn mức.
8. **Backend capability:** xác nhận target có hỗ trợ tính năng yêu cầu.
9. **Persist normalized command:** lưu bản đã chuẩn hóa trước khi chạy tác vụ dài.

Ví dụ cross-field validation:

- `backup.enabled=true` thì plan phải hỗ trợ backup.
- `backup.retention_days` phải có mặt nếu bật backup và nằm trong giới hạn.
- `read_replicas > 0` thì plan phải hỗ trợ replication.
- `storage_gb` không được thấp hơn dung lượng đã sử dụng khi update.
- `engine_version` đích phải nằm trong ma trận nâng cấp từ phiên bản hiện tại.

Không để backend quyết định ngầm các quy tắc nghiệp vụ này. Backend adapter có thể kiểm tra thêm constraint kỹ thuật, nhưng broker cần trả lỗi nhất quán và dễ hiểu trước khi gửi request nếu có thể.

## 9. Ví dụ validator trong Java

Một cách triển khai là giữ request thô dưới dạng JSON tree, kiểm tra schema, sau đó map sang command có kiểu dữ liệu rõ ràng. Ví dụ dưới đây mô tả cấu trúc tổng quát; tên lớp không phải API cố định của Spring Cloud Service Broker.

~~~java
public record ProvisionParameters(
    String databaseName,
    Integer storageGb,
    BackupParameters backup
) {}

public record BackupParameters(
    Boolean enabled,
    Integer retentionDays
) {}
~~~

Một validator theo allowlist có thể thực hiện:

~~~java
public final class ParameterValidator {

    private static final Set<String> ALLOWED_FIELDS =
        Set.of("database_name", "storage_gb", "backup");

    public ProvisionParameters validate(JsonNode input) {
        if (input == null || !input.isObject()) {
            throw new InvalidParametersException(
                "parameters must be a JSON object");
        }

        input.fieldNames().forEachRemaining(name -> {
            if (!ALLOWED_FIELDS.contains(name)) {
                throw new UnsupportedParameterException(name);
            }
        });

        JsonNode nameNode = input.get("database_name");
        if (nameNode == null || !nameNode.isTextual()) {
            throw new InvalidParametersException(
                "database_name must be a string");
        }

        String databaseName = normalizeDatabaseName(nameNode.textValue());

        Integer storageGb = readOptionalInteger(input, "storage_gb");
        if (storageGb != null && (storageGb < 50 || storageGb > 250)) {
            throw new InvalidParametersException(
                "storage_gb must be between 50 and 250");
        }

        BackupParameters backup = validateBackup(input.get("backup"));

        return new ProvisionParameters(databaseName, storageGb, backup);
    }
}
~~~

Trong triển khai thực tế, cần xử lý đầy đủ object lồng nhau, field bắt buộc, null, overflow, giới hạn chuỗi và các quy tắc plan/tenant. Đặc biệt, `validateBackup` phải kiểm tra field lạ bên trong `backup`, không chỉ parse các field đã biết.

Nếu dùng JSON Schema validator, nên cấu hình schema với `additionalProperties: false` ở những object cần đóng và chạy validation đệ quy. Có thể tạo schema runtime từ service/plan/operation hoặc quản lý phiên bản schema trong cấu hình. Cần chọn phiên bản JSON Schema tương thích với thư viện validator và cách công bố schema của broker.

### Strict parsing

Với Jackson, broker có thể cấu hình parser để phát hiện key trùng trong JSON. Nếu JSON chứa cùng một key hai lần, các parser khác nhau có thể giữ giá trị đầu hoặc cuối; chấp nhận điều này có thể dẫn đến khác biệt giữa gateway và broker.

~~~java
JsonFactory factory = JsonFactory.builder()
    .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
~~~

API cấu hình cụ thể có thể khác theo phiên bản Jackson. Ngoài duplicate detection, cần giới hạn độ dài body, nesting depth và số token để giảm nguy cơ payload quá lớn hoặc gây tiêu thụ tài nguyên bất thường.

## 10. Error response khi tham số không hợp lệ

Khi từ chối request, broker nên trả lỗi có cấu trúc theo hợp đồng OSB API và HTTP status phù hợp với loại lỗi. Không nên trả stack trace, SQL, endpoint backend hoặc secret.

Ví dụ response minh họa:

~~~json
{
  "error": "UnsupportedParameter",
  "description": "Parameter 'backkup_retention_days' is not supported for plan 'standard'."
}
~~~

Một lỗi validation khác:

~~~json
{
  "error": "InvalidParameters",
  "description": "Parameter 'storage_gb' must be an integer between 50 and 250."
}
~~~

Thông báo nên có đủ thông tin để sửa request:

- Tên field sai hoặc không hỗ trợ.
- Lý do từ chối ở mức an toàn.
- Plan hoặc operation liên quan nếu cần.
- Không trả giá trị nhạy cảm do caller gửi.
- Không tiết lộ cấu hình nội bộ hoặc tài nguyên của tenant khác.

Dùng mã lỗi ổn định và HTTP status đúng theo OSB API version, thay vì để mỗi handler tự chọn response khác nhau. Validation error cần được phân biệt với lỗi backend tạm thời để platform không retry vô hạn một request vốn không thể thành công nếu không sửa input.

## 11. Chuẩn hóa parameters trong update và bind

### Update

Update thường là thay đổi một phần cấu hình instance. Broker cần phân biệt:

- Field không xuất hiện: giữ giá trị hiện tại.
- Field xuất hiện với giá trị mới: validate và yêu cầu thay đổi.
- Field xuất hiện với null: chỉ chấp nhận nếu semantics cho phép xóa hoặc reset.
- Field không hỗ trợ trong update schema: từ chối.

Không lấy default provision áp dụng lại toàn bộ khi update, vì có thể vô tình reset cấu hình hiện tại. Update command nên chứa cả giá trị hiện tại và thay đổi đã chuẩn hóa để kiểm tra tương thích.

Ví dụ:

~~~json
{
  "storage_gb": 200,
  "backup": {
    "retention_days": 21
  }
}
~~~

Broker cần xác nhận plan cho phép storage 200 GB, backup retention 21 ngày hợp lệ, quota còn đủ và backend hỗ trợ thay đổi này. Nếu thao tác bất đồng bộ, lưu normalized update command và profile version để worker sử dụng cùng dữ liệu đã được chấp nhận.

### Bind

Binding parameters có thể mô tả quyền hoặc cấu hình riêng cho consumer. Ví dụ:

~~~json
{
  "access_mode": "read_only",
  "schema": "reporting"
}
~~~

Broker cần có schema riêng cho bind, kiểm tra service instance đã sẵn sàng, service có bindable và consumer được phép sử dụng các giá trị đó. Không cho phép binding parameters ghi đè tenant ID, instance ownership, backend credential hoặc quyền quản trị.

## 12. Chuẩn hóa và idempotency

Broker thường nhận request retry khi platform timeout hoặc mất kết nối. Nếu fingerprint được tính từ JSON thô, hai request tương đương có thể tạo fingerprint khác nhau do thứ tự key hoặc cách biểu diễn giá trị.

Ví dụ hai object có cùng nội dung nhưng thứ tự field khác nhau:

~~~json
{ "database_name": "orders", "storage_gb": 150 }
~~~

~~~json
{ "storage_gb": 150, "database_name": "orders" }
~~~

Sau khi validate và chuẩn hóa, broker có thể serialize command theo thứ tự field ổn định và tính fingerprint. Chỉ các field có ảnh hưởng đến kết quả nghiệp vụ mới nên tham gia fingerprint.

~~~text
normalized_command = validate_and_normalize(raw_parameters)

request_fingerprint = hash(
    service_id,
    plan_id,
    operation_type,
    canonical_json(normalized_command)
)
~~~

Không đưa các giá trị bí mật vào fingerprint có thể bị log hoặc quan sát. Nếu cần phân biệt credential, dùng HMAC với key quản lý an toàn hoặc một digest được thiết kế riêng, và không tiết lộ digest trong response.

Khi cùng ID được gửi lại với fingerprint giống nhau, broker có thể trả operation/kết quả đã lưu. Nếu fingerprint khác, broker cần trả xung đột theo quy tắc API. Không được bỏ qua field lạ ở lần đầu rồi âm thầm nhận field đó ở lần retry nếu điều đó làm thay đổi ý nghĩa request.

## 13. An toàn khi xử lý dữ liệu đầu vào

Parameters có thể chứa tên tài nguyên, chuỗi truy vấn, đường dẫn hoặc giá trị được chuyển tiếp tới API backend. Cần phòng tránh các lỗi sau:

- **Injection:** không nối chuỗi parameters trực tiếp vào SQL, shell command hoặc manifest không được kiểm soát. Dùng prepared statement, API typed và escaping đúng ngữ cảnh.
- **Mass assignment:** không map JSON trực tiếp vào entity persistence hoặc object cấu hình có field quản trị. Dùng DTO/command allowlist.
- **Prototype/property abuse:** trong hệ Java, tránh bind dữ liệu ngoài vào object tùy ý; chỉ map vào kiểu dữ liệu được kiểm soát.
- **Resource exhaustion:** giới hạn body size, độ sâu JSON, số phần tử array, độ dài chuỗi và thời gian validation.
- **Secret leakage:** không log password, token, private key hoặc parameters nhạy cảm.
- **Path/URL abuse:** nếu field được dùng để chọn file, endpoint hoặc resource path, áp dụng allowlist và kiểm tra đích đến.
- **Cross-tenant reference:** không tin ID network, storage class, secret hoặc project do caller gửi nếu chúng chưa được xác minh thuộc tenant.

Schema validation là cần thiết nhưng chưa đủ. Một giá trị có thể đúng kiểu và đúng pattern nhưng vẫn không được phép dùng trong tenant hoặc target hiện tại. Phải kiểm tra authorization, entitlement, quota và backend capability sau validation cấu trúc.

## 14. Phiên bản schema và tương thích ngược

Hợp đồng parameters có thể thay đổi theo thời gian. Nếu broker thay đổi field, kiểu hoặc semantics mà không quản lý version, các client cũ có thể gửi request không còn hợp lệ.

Một số nguyên tắc:

1. Giữ tên field và semantics ổn định khi có thể.
2. Khi thêm field mới, quyết định rõ client cũ không gửi field đó sẽ nhận default nào.
3. Khi bỏ field, có thời gian deprecation và telemetry để biết còn client sử dụng hay không.
4. Không tái sử dụng tên field cũ cho ý nghĩa khác.
5. Version hóa schema hoặc profile nếu thay đổi ảnh hưởng đến instance đã tồn tại.
6. Giữ validator tương thích với request cũ trong phạm vi đã cam kết.
7. Từ chối field lạ theo policy đã công bố; không thay đổi hành vi một cách bất ngờ giữa các lần triển khai.

Nếu broker có nhiều plan, mỗi plan có thể có schema khác nhau. Cần bảo đảm catalog trả schema tương ứng với plan và server validator dùng cùng phiên bản. Với update, schema cần phản ánh chính xác các field được phép thay đổi, không chỉ sao chép schema create.

## 15. Theo dõi và audit validation

Validation nên tạo được thông tin vận hành hữu ích mà không làm lộ dữ liệu đầu vào.

Các metric có thể theo dõi:

- Số request bị từ chối theo loại lỗi.
- Số field không được hỗ trợ theo tên field đã được allowlist để thống kê.
- Tỷ lệ validation failure theo service, plan và operation.
- Thời gian validation và kích thước payload.
- Tỷ lệ lỗi sau validation tại backend.
- Số request retry với fingerprint giống hoặc khác.

Audit có thể ghi platform/tenant ID đã chuẩn hóa, instance ID, operation ID, plan ID, schema version, loại lỗi và timestamp. Không lưu toàn bộ parameters thô nếu chúng có thể chứa thông tin nhạy cảm. Nếu cần điều tra, lưu một bản đã lọc hoặc tham chiếu an toàn theo chính sách retention.

Dữ liệu metric cần tránh cardinality quá cao. Không dùng giá trị tùy ý do người dùng gửi làm nhãn metric. Tên field không được hỗ trợ có thể được phân loại thành nhóm hoặc giới hạn số lượng giá trị lưu trữ.

## 16. Kiểm thử chuẩn hóa và từ chối field lạ

Bộ kiểm thử cần xác minh cả giá trị được chấp nhận và dữ liệu phải bị từ chối.

| Trường hợp | Input | Kết quả mong đợi |
|---|---|---|
| Parameters hợp lệ | Object có các field đúng schema | Tạo normalized command |
| Field lạ cấp cao nhất | `backkup_retention_days` | Từ chối và chỉ rõ field |
| Field lạ lồng nhau | `backup.send_credentials_to` | Từ chối đệ quy |
| Sai kiểu | `storage_gb: "150"` | Từ chối nếu schema yêu cầu integer |
| Vượt miền | `storage_gb: 1000` | Từ chối theo giới hạn plan |
| Null không hợp lệ | `database_name: null` | Từ chối field bắt buộc |
| Field thiếu | Không có `database_name` | Từ chối hoặc áp dụng default nếu hợp đồng cho phép |
| Enum sai | `access_mode: "superuser"` | Từ chối giá trị không được công bố |
| Chuỗi quá dài | Tên database vượt max length | Từ chối trước khi gọi backend |
| Unicode tương đương | Hai dạng mã hóa cùng tên sau canonicalization | Có kết quả uniqueness nhất quán |
| JSON key trùng | Một key xuất hiện hai lần | Parser từ chối |
| Object quá sâu/lớn | Payload vượt giới hạn | Từ chối có kiểm soát |
| Update field không cho phép | Gửi `database_name` trong update | Từ chối theo update schema |
| Retry tương đương | Key order khác nhưng normalized command giống nhau | Fingerprint ổn định |
| Retry mâu thuẫn | Cùng ID nhưng normalized command khác | Phát hiện xung đột |
| Tenant không có quyền | Giá trị đúng schema nhưng vượt entitlement | Từ chối authorization/policy |

Ngoài unit test cho từng validator, cần integration test đảm bảo request không hợp lệ không gọi backend và không tạo operation cấp phát tài nguyên. Với request bất đồng bộ, chỉ enqueue sau khi validation và policy checks hoàn tất, đồng thời lưu normalized command để worker không phải diễn giải lại JSON thô.

## 17. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Bỏ qua mọi field không biết | Typo trở thành request thành công giả | Allowlist và từ chối field lạ |
| Chỉ kiểm tra field cấp cao nhất | Field lạ trong object con lọt qua | Validation đệ quy |
| Dùng ép kiểu tự động | Dữ liệu sai kiểu bị biến đổi âm thầm | Strict type validation |
| Gộp null với field thiếu | Update có thể xóa hoặc reset nhầm cấu hình | Định nghĩa semantics riêng |
| Trim/lowercase mọi chuỗi | Thay đổi password hoặc identifier case-sensitive | Chuẩn hóa theo từng field |
| Map JSON trực tiếp vào entity | Caller có thể ghi field nội bộ | DTO/command allowlist |
| Chỉ dựa vào schema công bố | Client gửi trực tiếp có thể bỏ qua schema | Server-side validation |
| Validate trước nhưng không kiểm tra quota | Request hợp lệ về cú pháp vẫn vượt quyền | Policy và quota checks |
| Fingerprint JSON thô | Request tương đương bị coi là khác nhau | Canonicalize trước khi hash |
| Worker parse lại request gốc | Kết quả khác với dữ liệu đã được chấp nhận | Persist normalized command |
| Ghi parameters vào log | Có thể lộ secret và dữ liệu khách hàng | Redaction và audit tối thiểu |

## 18. Nguyên tắc cần ghi nhớ

Chuẩn hóa tham số giúp broker hiểu một request theo cách nhất quán. Từ chối field không được hỗ trợ giúp consumer phát hiện lỗi sớm và ngăn những cấu hình không được broker cam kết lọt xuống hạ tầng.

Khi triển khai trong Spring Cloud Service Broker, hãy giữ các bước rõ ràng:

- Xác định schema theo service, plan và operation.
- Parse JSON nghiêm ngặt, giới hạn kích thước và cấu trúc.
- Từ chối field lạ ở mọi cấp object theo policy đã công bố.
- Phân biệt field thiếu, null và giá trị mặc định.
- Validate kiểu, miền giá trị, enum và quan hệ giữa các field.
- Chuẩn hóa từng field theo semantics riêng.
- Kiểm tra entitlement, quota và backend capability.
- Chuyển dữ liệu hợp lệ thành command có kiểu và lưu command đó cho operation bất đồng bộ.
- Tính fingerprint trên dữ liệu chuẩn hóa để hỗ trợ idempotency.
- Trả lỗi có cấu trúc, không tiết lộ bí mật hoặc chi tiết hạ tầng.

Với cách tiếp cận này, parameters trở thành một hợp đồng được kiểm soát giữa platform, broker và backend. Người dùng biết rõ field nào được hỗ trợ; broker có thể từ chối request sai trước khi tạo tài nguyên; các lần retry và worker bất đồng bộ tiếp tục xử lý cùng một cấu hình đã được xác thực.

