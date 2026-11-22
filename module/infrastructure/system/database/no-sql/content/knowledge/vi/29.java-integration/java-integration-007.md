# Serialization, schema version và xử lý trường thiếu hoặc không nhận biết

Một ứng dụng Java kết nối tới cơ sở dữ liệu NoSQL thường trao đổi dữ liệu bằng JSON, BSON, cấu trúc key–value hoặc một định dạng nhị phân như Avro/Protocol Buffers. Khi mới triển khai, mọi document có thể cùng cấu trúc với DTO hiện tại. Sau vài lần nâng cấp, thực tế thay đổi:

- Document được ghi từ phiên bản ứng dụng cũ vẫn còn trong database.
- Trong lúc rolling deployment, instance Java cũ và mới cùng đọc/ghi một tập dữ liệu.
- Một service khác bổ sung field mà ứng dụng hiện tại chưa biết.
- Thiết bị offline đồng bộ bản ghi cũ sau nhiều tuần.
- Một số field không có, một số có giá trị `null`, một số bị thay đổi kiểu dữ liệu.
- SDK/serializer có thể bỏ qua field lạ, gán giá trị mặc định hoặc báo lỗi khi deserialize.

Ví dụ, phiên bản 1 của hồ sơ:

~~~json
{
  "tenantId": "tenant-A",
  "profileId": "P-100",
  "displayName": "An",
  "schemaVersion": 1
}
~~~

Phiên bản 2 bổ sung timezone và thông tin liên hệ:

~~~json
{
  "tenantId": "tenant-A",
  "profileId": "P-100",
  "displayName": "An",
  "timeZone": "Asia/Ho_Chi_Minh",
  "contactPreferences": {
    "email": true,
    "push": false
  },
  "schemaVersion": 2
}
~~~

Nếu một ứng dụng Java phiên bản cũ deserialize document v2 vào DTO chỉ có `tenantId`, `profileId`, `displayName`, rồi **serialize lại cả document** để đổi tên hiển thị, các trường `timeZone` và `contactPreferences` có thể biến mất. Chương trình không báo lỗi, database ghi thành công, nhưng dữ liệu mới đã bị làm mất. Đây là một dạng **mất dữ liệu do schema evolution** thường khó phát hiện hơn lỗi parse.

Bài học thuộc chương **Kết nối Java** của module **Database No SQL** giải thích serialization/deserialization, phiên bản schema, các trạng thái field thiếu/null/unknown, khả năng tương thích khi deploy, mapping Java, migration và cách kiểm thử. Trọng tâm không chỉ là “Jackson đọc JSON được hay không”, mà còn là **giữ đúng ý nghĩa dữ liệu khi nhiều phiên bản ứng dụng cùng tồn tại**.

> **Nguyên tắc:** Đọc được một document chưa chắc có quyền ghi nó lại nguyên vẹn; bỏ qua trường không nhận biết có thể phù hợp ở ranh giới request, nhưng nguy hiểm tại ranh giới lưu trữ nếu ứng dụng thực hiện full replacement.

## 1. Serialization và deserialization là gì?

**Serialization** chuyển dữ liệu trong bộ nhớ Java thành representation để lưu hoặc truyền đi. **Deserialization** đọc representation ấy thành cấu trúc mà chương trình có thể xử lý.

~~~mermaid
flowchart LR
    D["Domain object"] --> M["Persistence mapper"]
    M --> DTO["Persistence DTO / document"]
    DTO --> SER["Serializer / Codec"]
    SER --> DB["JSON / BSON / NoSQL storage"]
    DB --> DES["Deserializer / Codec"]
    DES --> VER["Schema version reader / upcaster"]
    VER --> DOM["Domain object"]
~~~

Ví dụ:

~~~java
public record Profile(
    String tenantId,
    String profileId,
    String displayName
) {}
~~~

Serializer có thể chuyển thành:

~~~json
{
  "tenantId": "tenant-A",
  "profileId": "P-100",
  "displayName": "An"
}
~~~

Nhưng conversion không nhất thiết đối xứng hoàn toàn: database còn có metadata như `_id`, ETag, TTL, khóa phân vùng, schema version hoặc các field do ứng dụng mới thêm.

### 1.1. Các ranh giới khác nhau

| Ranh giới | Bên gửi/bên nhận | Mục tiêu |
|---|---|---|
| HTTP request DTO | Client → Java API | Validate đầu vào không đáng tin |
| HTTP response DTO | Java API → Client | Hợp đồng công khai và bảo mật |
| Persistence DTO | Java service ↔ NoSQL | Mapping schema/version của storage |
| Event DTO | Producer ↔ consumer | Compatibility qua queue/CDC |
| Cache value | Java ↔ Redis/cache | Serialization, TTL và invalidation |
| Backup/export | Storage ↔ công cụ migration | Giữ dữ liệu và metadata chính xác |

Một model không nhất thiết phù hợp cho tất cả ranh giới. Đặc biệt, **request DTO không nên được ghi thẳng thành database document** chỉ vì JSON có các field giống nhau.

### 1.2. Codec khác domain mapper

Codec biết cách chuyển Java/BSON/JSON/native types. Domain mapper biết `Money`, `OrderStatus`, invariant và schema migration có nghĩa gì. Cho codec tự suy luận domain từ `null` hoặc field không tồn tại thường tạo lỗi âm thầm.

### 1.3. “Schema-less” không phải “schema-free”

NoSQL document store có thể không bắt mọi record theo một DDL cố định, nhưng ứng dụng luôn có **kỳ vọng về field, kiểu dữ liệu, quan hệ và ý nghĩa**. Schema có thể nằm trong code, validation rules, event contract hoặc registry. Không có constraint tại DB không làm schema biến mất.

### 1.4. Serialization là một phần của data contract

Đổi Java `int` thành `long`, tên field hay timezone representation có thể làm records cũ không đọc được hoặc giá trị bị sai, dù class mới compile thành công.

## 2. Ba trạng thái quan trọng: thiếu, null và có giá trị

Đối với một key JSON, tối thiểu có ba trạng thái:

~~~json
{"profileId": "P-100"}
~~~

Field `nickname` **không tồn tại**.

~~~json
{"profileId": "P-100", "nickname": null}
~~~

Field `nickname` **có mặt và mang giá trị JSON null**.

~~~json
{"profileId": "P-100", "nickname": "Bé An"}
~~~

Field `nickname` **có giá trị string**.

### 2.1. Bảng ngữ nghĩa

| Trạng thái | JSON | Có thể mang nghĩa |
|---|---|---|
| Missing/absent | Không có key | Chưa được gửi, chưa từng biết, áp default hợp lệ |
| Explicit null | `"nickname": null` | Chủ ý xóa giá trị hoặc “không có” theo domain |
| Non-null value | `"nickname": "An"` | Giá trị cụ thể |
| Unknown field | `"newFeature": ...` | Có key nhưng reader hiện tại chưa biết schema |
| Invalid type | `"age": "nhiều"` | Field biết tên nhưng sai kiểu/format |

**Unknown** là một trục khác với missing/null: một field có thể hiện diện với kiểu đúng nhưng **không nằm trong model cũ**.

### 2.2. Vì sao Java DTO dễ làm mất phân biệt?

~~~java
public record ProfilePatch(String nickname) {}
~~~

Khi deserialize hai payload `{}` và `{"nickname":null}`, field `nickname` có thể cùng thành Java `null` tùy mapper/config. Nếu logic cập nhật chỉ nhìn `patch.nickname() == null`, nó không biết caller **không yêu cầu thay đổi** hay **muốn xóa nickname**.

### 2.3. Với primitive còn nguy hiểm hơn

~~~java
public record SubscriptionDto(boolean emailEnabled, int retryLimit) {}
~~~

Một mapper có thể gán `false`/`0` khi field thiếu theo cách khởi tạo/config cụ thể. Khi lưu lại, hệ có thể ghi đè `emailEnabled=true` thành `false`. Với giá trị quan trọng, dùng boxed types và validation/field-presence semantics rõ; không suy “mặc định Java” là business default.

### 2.4. Null không nhất thiết nghĩa delete

Một API PUT có thể coi null là giá trị hợp lệ; JSON Merge Patch (RFC 7396) dùng null để **xóa member** của object đích theo semantics chuẩn; JSON Patch (RFC 6902) có operation `"remove"` riêng. Không áp lẫn ba hợp đồng này.

## 3. Unknown fields: reader không biết nhưng dữ liệu vẫn có giá trị

Giả sử service cũ biết:

~~~java
public record ProfileV1(
    String tenantId,
    String profileId,
    String displayName
) {}
~~~

Trong khi database đã có:

~~~json
{
  "tenantId": "tenant-A",
  "profileId": "P-100",
  "displayName": "An",
  "timeZone": "Asia/Ho_Chi_Minh",
  "schemaVersion": 2
}
~~~

Reader V1 có ba lựa chọn:

1. **Strict reject:** từ chối unknown fields hoặc schema version vượt khả năng.
2. **Ignore on read:** bỏ qua `timeZone` và tiếp tục xử lý các fields biết.
3. **Preserve as extensions:** giữ field lạ trong representation riêng để không làm mất khi phải ghi qua.

### 3.1. Không có chính sách duy nhất cho mọi ranh giới

| Trường hợp | Chính sách thường phù hợp | Lý do |
|---|---|---|
| Public create/update API | Strict allowlist hoặc reject unknown | Chống mass assignment/typo |
| Read-only consumer cần subset | Ignore unknown có chủ đích | Forward compatibility khi field mới thêm |
| Persistence reader có full replace | Preserve unknown hoặc từ chối write | Không làm mất field mới |
| Event consumer | Ignore hoặc preserve unknown tùy contract | Hỗ trợ producer mới nhưng cần validation |
| Payment/permission/security DTO | Strict hoặc version-aware | Field mới có thể đổi nghĩa quyết định |
| Export/import round trip | Preserve raw fields có kiểm soát | Không cắt mất dữ liệu |

### 3.2. Tolerant reader không có nghĩa tolerant writer

Một service cũ có thể **đọc** document v3 để hiển thị tên nhưng không được **ghi đè toàn bộ** nếu nó không hiểu semantics của field v3. Có thể chỉ cho phép patch field do service sở hữu qua CAS.

### 3.3. Bỏ qua unknown field không phải validation

Nếu client viết nhầm `"emial"` thay vì `"email"`, ignore unknown silently có thể trả 200 nhưng không làm gì. Với input API, reject unknown có thể giúp phát hiện lỗi client sớm.

### 3.4. Preserve unknown phải có giới hạn

Lưu mọi field lạ vô hạn có thể tăng document size, làm lộ dữ liệu hoặc tạo key trùng với reserved fields. Cần giới hạn kích thước, độ sâu, key naming, schema owner và nguồn đáng tin trước khi round-trip.

## 4. Schema version dùng để làm gì?

Một document versioned:

~~~json
{
  "_id": "tenant-A/P-100",
  "schemaVersion": 3,
  "profileId": "P-100",
  "displayName": "An",
  "preferredLocale": "vi-VN"
}
~~~

`schemaVersion` chỉ ra **cấu trúc và ngữ nghĩa serialization** mà writer sử dụng, để reader biết phải decode hoặc chuyển đổi như thế nào.

### 4.1. Không trộn schemaVersion với entityVersion

~~~json
{
  "schemaVersion": 3,
  "entityVersion": 42,
  "eventSequence": 87,
  "lastModifiedAt": "2026-11-14T08:00:00Z"
}
~~~

| Field | Mục đích |
|---|---|
| `schemaVersion` | Phiên bản cấu trúc/encoding của document |
| `entityVersion` | Kiểm soát cạnh tranh khi update một entity |
| `eventSequence` | Thứ tự sự kiện trong một aggregate/stream |
| `lastModifiedAt` | Thời điểm nghiệp vụ/kỹ thuật theo clock policy |
| `_etag` hoặc revision token | Conditional update theo API sản phẩm |
| `routingEpoch` | Thế hệ owner/tenant placement trong một giao thức |

Số 3 của schema không nói một document được cập nhật lần thứ ba. EntityVersion 42 không chứng minh cấu trúc đã là schema v42.

### 4.2. Khi nào tăng schemaVersion?

Khi thay representation hoặc semantics khiến reader phải có logic mới: đổi tên có migration, đổi kiểu tiền, tách nested object, đổi đơn vị, encode enum mới không tương thích, thay bất biến.

Thêm một field optional với default rõ có thể có hoặc không cần tăng version tùy chiến lược schema evolution; quan trọng là **quy tắc của đội phải nhất quán và kiểm thử compatibility**.

### 4.3. Unknown schema version là vấn đề riêng với unknown field

V1 reader có thể bỏ qua field mới của V2; nhưng nếu V2 đổi nghĩa `"amount"` từ đồng sang cents, ignore unknown không cứu được. Một reader không hiểu `schemaVersion` mới có thể cần **từ chối những thao tác quan trọng**, không tự deserialize rồi viết lại.

### 4.4. Version metadata phải đáng tin

Client không nên tự chọn schemaVersion cao để bypass validation. Persistence writer do service quản lý phải tạo version theo code; dữ liệu được nhập phải validate và upcast theo policy.

## 5. Backward, forward và full compatibility

Với writer V1/V2 và reader V1/V2:

| Khả năng | Nghĩa |
|---|---|
| **Backward compatibility** | Reader mới V2 có thể đọc dữ liệu writer cũ V1 |
| **Forward compatibility** | Reader cũ V1 có thể đọc dữ liệu writer mới V2 |
| **Full compatibility** | Cả hai chiều đều được giữ trong phạm vi đã cam kết |
| **Breaking change** | Một chiều đọc hoặc interpretation không còn đúng |

Không được nhầm backward compatibility với “deploy mới rồi tất cả dữ liệu cũ tự đúng” nếu default không có nguồn xác định.

### 5.1. Thêm optional field

~~~text
V1: {name}
V2: {name, timeZone?}
~~~

V2 reader có thể đọc V1 nếu xử lý thiếu `timeZone` hợp lệ. V1 reader có thể đọc V2 nếu ignore unknown, **nhưng full replacement bởi V1 writer có thể mất timeZone**. Read compatibility **không** đồng nghĩa write round-trip compatibility.

### 5.2. Đổi tên field

~~~text
V1: "fullName"
V2: "displayName"
~~~

Reader V2 chỉ đọc `displayName` sẽ làm tên của records V1 thành missing. Cần alias/upcaster/dual-read, migration và cutover; không chỉ rename member trong Java class.

### 5.3. Đổi kiểu dữ liệu

~~~text
V1: amount = 120.50 as floating-point.
V2: amountMinor = 12050 as integer cents.
~~~

Không tự suy đơn vị và độ chính xác khi convert. Nếu dữ liệu cũ từng lưu float, có thể đã mất precision; migration phải định nghĩa rounding, currency, audit và test.

### 5.4. Đổi enum

~~~text
V1: status = PENDING | ACTIVE
V2: status = PENDING | ACTIVE | SUSPENDED
~~~

Reader V1 strict có thể fail khi gặp `SUSPENDED`. Reader V1 map mọi enum lạ thành `ACTIVE` có thể cấp quyền nhầm. Unknown enum cần xử lý **theo mức độ nguy hiểm của domain**, không chỉ cấu hình Jackson.

### 5.5. Xóa field

Một writer V2 ngừng ghi `legacyEmail`, nhưng consumer V1 vẫn dựa vào field này thì không forward-compatible. Cần deprecate, dual-read/dual-write khi có chứng cứ hợp lý, hoặc nâng readers trước khi writer ngừng cung cấp.

## 6. Rolling deployment tạo ra “đa phiên bản cùng thời”

Một rollout không xảy ra tức thì:

~~~text
T0: 100% services V1
T1: 20% V2, 80% V1
T2: 70% V2, 30% V1
T3: 100% V2
~~~

Trong T1/T2, V1 và V2 có thể đọc cùng records. Nếu V2 ghi schema mới không tương thích, V1 không parse được. Nếu V1 đọc được nhưng full replace, có thể làm mất field V2.

### 6.1. Mô hình reader/writer compatibility

| Reader | Writer data V1 | Writer data V2 |
|---|---|---|
| V1 | Thường được bảo đảm bởi release V1 | Phải kiểm forward compatibility |
| V2 | Phải kiểm backward compatibility | Mục tiêu release V2 |

Một test chuyển JSON qua DTO rồi serialize lại cần kiểm thêm **unknown field preservation**, không chỉ check read không throw exception.

### 6.2. Đổi order triển khai

Thông thường nên:

1. Deploy reader đọc được cả v1/v2.
2. Chuyển writers sang v2 sau khi readers sẵn sàng.
3. Backfill/upgrade dữ liệu cũ nếu cần.
4. Chỉ sau đó bỏ đường đọc v1 khi có bằng chứng không còn v1, bao gồm backup/offline/queue.

Với rollback, phải nhớ binary V1 có thể quay lại sau khi V2 đã ghi dữ liệu. Nếu V1 không forward-compatible, rollback code thuần túy có thể không an toàn.

### 6.3. Compatibility window cần định nghĩa

Không thể hứa hỗ trợ vô hạn mọi version từ năm năm trước. Hãy định nghĩa reader compatibility horizon, mobile offline window, queue retention và restore policy. Điều này quyết định thời gian giữ upcasters và schema migration metadata.

## 7. Jackson trong Java: strict hoặc ignore unknown

Jackson `ObjectMapper` thường được dùng để đọc JSON vào Java DTO:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.DeserializationFeature;

ObjectMapper mapper = new ObjectMapper();
mapper.configure(
    DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
    true
);
~~~

Một DTO:

~~~java
public record ProfileInput(
    String profileId,
    String displayName
) {}
~~~

Khi JSON có `"timeZone"` nhưng DTO không có property tương ứng, cấu hình strict có thể ném `UnrecognizedPropertyException`.

### 7.1. Ignore unknown fields có chủ đích

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record ProfileReadView(
    String profileId,
    String displayName
) {}
~~~

Annotation giúp deserializer bỏ qua các field chưa biết cho type này. Nó **không bảo đảm bảo toàn** field bị bỏ qua khi serialize DTO trở lại; thông tin ấy đã mất khỏi object.

### 7.2. Global lenient vs local strict

~~~java
mapper.configure(
    DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
    false
);
~~~

Cấu hình global thay đổi hành vi nhiều loại DTO. Một Spring Boot application có thể có default/custom ObjectMapper khác Jackson thuần. Không đoán mode từ tên framework; kiểm thử mapper configuration thực tế.

### 7.3. Trường biết nhưng sai kiểu không phải unknown

~~~json
{"profileId":"P-100","age":"không rõ"}
~~~

`age` có thể là field được biết nhưng value sai kiểu. `ignoreUnknown=true` **không phải** quy tắc tự chữa mọi lỗi conversion. Coercion từ string sang số/boolean phải được xem xét, giới hạn hoặc tắt khi correctness yêu cầu.

### 7.4. DTO cho public API có thể nên strict

Client gửi `"isAdmn":true` do typo hoặc `"role":"ADMIN"` ngoài allowlist. Lenient bind trực tiếp vào persistence entity dễ gây mass assignment và silent errors. Dùng input DTO có explicit allowed fields, authorization và validation.

## 8. Jackson: kiểm tra presence bằng JsonNode

Đối với patch hoặc schema migration, `JsonNode` giúp phân biệt missing và JSON null rõ hơn record thuần:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

public final class PresenceExample {
    private static final ObjectMapper MAPPER = new ObjectMapper();

    public static String classify(String json) throws Exception {
        JsonNode root = MAPPER.readTree(json);
        if (root == null || !root.isObject()) {
            throw new IllegalArgumentException("expected object");
        }

        JsonNode nickname = root.get("nickname");
        if (nickname == null) {
            return "MISSING";
        }
        if (nickname.isNull()) {
            return "EXPLICIT_NULL";
        }
        if (!nickname.isTextual()) {
            return "INVALID_TYPE";
        }
        return "VALUE:" + nickname.textValue();
    }
}
~~~

### 8.1. `get` và `path` khác nhau

`get("field")` trả Java null khi field không tồn tại trên object; nếu field có JSON null thì trả `NullNode`. `path("field")` thường cho `MissingNode` khi không có. Đừng viết `root.path("age").asInt()` rồi mặc định 0 là giá trị đã được người dùng gửi.

### 8.2. Kiểu dữ liệu phải được validate

`asText()` và các coercion convenience methods có thể chuyển kiểu hoặc trả giá trị default. Với money, permissions, quantity và timestamp, thường nên kiểm `isTextual/isIntegralNumber` và range rõ trước khi chuyển.

### 8.3. Empty, whitespace và null là các trạng thái khác

`""`, `"   "`, `null` và missing có thể khác nhau về nghiệp vụ. Ví dụ nickname rỗng có thể là yêu cầu clear, nhưng email rỗng không hợp lệ. Không áp chung `trim().isEmpty() -> null` cho mọi field.

### 8.4. Presence phải đi theo application command

Sau deserialize, đừng nén patch thành DTO mà mọi field là nullable nếu cần phân biệt KEEP/SET/CLEAR. Hãy chuyển thành một kiểu command có trạng thái rõ.

## 9. Thiết kế kiểu patch ba trạng thái bằng Java

Một kiểu minh họa:

~~~java
public sealed interface FieldPatch<T>
    permits FieldPatch.Keep,
            FieldPatch.SetValue,
            FieldPatch.Clear {

    record Keep<T>() implements FieldPatch<T> {}
    record SetValue<T>(T value) implements FieldPatch<T> {}
    record Clear<T>() implements FieldPatch<T> {}
}
~~~

Ví dụ:

~~~java
public record UpdateProfileCommand(
    String tenantId,
    String profileId,
    long expectedEntityVersion,
    FieldPatch<String> nickname
) {}
~~~

Mapping từ JSON:

~~~java
import com.fasterxml.jackson.databind.JsonNode;

public final class PatchMapper {
    public static FieldPatch<String> nickname(JsonNode root) {
        JsonNode n = root.get("nickname");
        if (n == null) {
            return new FieldPatch.Keep<>();
        }
        if (n.isNull()) {
            return new FieldPatch.Clear<>();
        }
        if (!n.isTextual()) {
            throw new IllegalArgumentException("nickname must be string");
        }
        return new FieldPatch.SetValue<>(n.textValue());
    }
}
~~~

### 9.1. Không để Java null quyết định cả ba ý nghĩa

Ở tầng service, một `Keep` làm không đổi field, `SetValue` gán giá trị, `Clear` áp semantics xóa/nil do domain định nghĩa. Adapter map chúng sang `$set/$unset`, expression update hoặc CQL operations tương ứng.

### 9.2. Nullable field trong domain có thể khác patch null

Một domain object `Profile.nickname == null` có nghĩa trạng thái hiện tại không có nickname. Một patch `nickname: null` là **hành động muốn xóa field** nếu API định nghĩa vậy. Hai điều này cùng chữ null nhưng khác loại thông tin.

### 9.3. JSON Merge Patch và JSON Patch

Ví dụ Merge Patch:

~~~json
{"nickname":null,"timeZone":"UTC"}
~~~

Theo RFC 7396, null biểu thị remove member. JSON Patch dùng operations:

~~~json
[
  {"op":"remove","path":"/nickname"},
  {"op":"replace","path":"/timeZone","value":"UTC"}
]
~~~

Phải chọn và ghi rõ chuẩn/semantics API. JSON Patch cũng có `test` để kiểm điều kiện trên representation, nhưng không được nhầm với CAS commit-level nếu server không enforce nguyên tử.

### 9.4. Patch cũng cần expectedVersion

Hai requests đồng thời có thể cùng sửa nickname hoặc các fields liên quan. Dùng entityVersion/ETag/conditional predicate khi nghiệp vụ cần chống lost update; việc chỉ dùng patch không bảo vệ mọi invariant.

## 10. Unknown fields: bỏ qua, từ chối hay bảo toàn?

Đây là một quyết định theo **ownership và trust boundary**.

### 10.1. Strict public input

~~~text
POST /profiles
Known fields: displayName, nickname, locale
Input contains: isAdmin=true
=> reject, do not silently mass-assign
~~~

Caller không được chọn persistence metadata, permission roles, routing keys hoặc version fields nếu API không cấp quyền ấy.

### 10.2. Tolerant read-only projection

Một service chỉ cần `profileId` và `displayName` có thể ignore `timeZone`, `contactPreferences`. Nếu nó không ghi trở lại document gốc, việc ignore thường giảm coupling hữu ích.

### 10.3. Preserve unknown cho round-trip

Nếu cần đọc một representation tương lai rồi ghi lại toàn bộ, có thể giữ raw tree/extension map, **nhưng phải xác minh source đáng tin và kiểm soát reserved keys**.

### 10.4. Fail closed khi không hiểu ngữ nghĩa quan trọng

Một service V1 không hiểu `accountState="SUSPENDED"` không nên coi trạng thái đó là `ACTIVE` chỉ để tiếp tục. Có thể từ chối command với `UNSUPPORTED_SCHEMA_OR_STATE` và chuyển sang service mới.

### 10.5. Unknown data không thuộc quyền sở hữu của service

Một microservice không nên sửa/normalize field do service khác sở hữu. Ngay cả khi bảo toàn raw fields, việc viết lại toàn document từ snapshot cũ vẫn có thể đè dữ liệu mới. Ownership và concurrency guard quan trọng hơn việc “giữ tất cả field lạ”.

## 11. Jackson: giữ unknown properties trong extension map

Một DTO có thể dùng `@JsonAnySetter` và `@JsonAnyGetter` để giữ các properties chưa map:

~~~java
import com.fasterxml.jackson.annotation.JsonAnyGetter;
import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.LinkedHashMap;
import java.util.Map;

public final class ProfileEnvelope {
    private String profileId;
    private String displayName;
    private final Map<String, JsonNode> extensions =
        new LinkedHashMap<>();

    public String getProfileId() { return profileId; }
    public void setProfileId(String value) { profileId = value; }

    public String getDisplayName() { return displayName; }
    public void setDisplayName(String value) { displayName = value; }

    @JsonAnySetter
    public void acceptUnknown(String name, JsonNode value) {
        if ("profileId".equals(name) || "displayName".equals(name)) {
            throw new IllegalArgumentException("reserved property");
        }
        if (name.startsWith("$") || name.contains(".")) {
            throw new IllegalArgumentException("invalid extension key");
        }
        extensions.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, JsonNode> unknownFields() {
        return Map.copyOf(extensions);
    }
}
~~~

### 11.1. Đây không phải schema migration tự động

Extension map giúp round-trip một số fields mà class chưa biết. Nó **không** xác minh rằng unknown field an toàn, thuộc owner này hay không, hoặc có tương thích business rule mới.

### 11.2. Map bất biến và null

`Map.copyOf` không chấp nhận Java null key/value; Jackson `NullNode` là một object không-null nếu được sử dụng đúng. Production cần xử lý limits, reserved names, duplicate keys, size/depth và null policy.

### 11.3. Nested unknown fields

Nếu DTO có nested `Address` class chỉ nhận `city` nhưng bản mới có `geocode`, unknown nested field vẫn có thể mất nếu nested object không bảo toàn. Phải quyết định preservation **tới độ sâu nào**, không chỉ ở top-level.

### 11.4. Không dùng extension map cho dữ liệu từ public request một cách tùy tiện

Nếu caller đưa `"role":"ADMIN"` qua unknown map rồi service round-trip xuống database, có thể tạo mass assignment. Có thể chỉ bật preservation cho data đọc từ trusted persistence source, còn public input dùng strict DTO.

### 11.5. Full replace vẫn có race

Dù DTO giữ unknown fields, nếu service đọc document ở version 8 rồi ghi nguyên object sau khi writer khác commit version 9, nó vẫn có thể gây lost update. Phải dùng CAS, atomic patch hoặc transaction thích hợp.

## 12. Cách an toàn hơn: patch trường do service sở hữu

Thay vì:

~~~text
read full document
deserialize into old DTO
change displayName
serialize full DTO
replace entire document
~~~

hãy ưu tiên khi phù hợp:

~~~text
atomic conditional PATCH:
    entity identity + tenant scope + expectedVersion
    SET displayName = newValue
    INCREMENT entityVersion
    preserve every unrelated persisted field
~~~

### 12.1. MongoDB ví dụ

~~~javascript
db.profiles.updateOne(
  {
    _id: "tenant-A/P-100",
    tenantId: "tenant-A",
    entityVersion: 8
  },
  {
    $set: { displayName: "An Nguyễn" },
    $inc: { entityVersion: 1 }
  }
);
~~~

Một `$set` chỉ tác động field chọn, không tự xóa các fields mới khác. Condition giúp ngăn ghi theo version cũ nếu operation cần guard. Cần kiểm tra matched count và contract để phân biệt conflict/not-found/tenant scope.

### 12.2. Khi full replacement vẫn cần thiết

Có tình huống muốn thay cả aggregate theo snapshot và validate invariant toàn bộ. Khi đó reader phải hiểu/preserve schema trong phạm vi hỗ trợ, writer dùng CAS và chính sách unknown fields rõ. Không dùng nguyên DTO response HTTP làm replacement document.

### 12.3. Không phải mọi NoSQL đều patch như nhau

DynamoDB có UpdateExpression nhưng `PutItem` có thể thay toàn item; Cosmos DB có patch operations/replace với ETag; CQL UPDATE/UNSET/NULL có semantics riêng. Adapter phải map từ **ý định** sang primitive đúng sản phẩm.

## 13. SchemaVersion reader: áp default đúng ngữ nghĩa

Một reader tốt thường:

1. Decode representation thô và validate structure cơ bản.
2. Xác định schema version theo policy.
3. Chạy migration/upcaster từ version cũ nếu được hỗ trợ.
4. Validate các trường bắt buộc sau chuẩn hóa.
5. Chuyển sang domain type.
6. Giữ đủ metadata để update an toàn.

### 13.1. Legacy records không có schemaVersion

Có thể quy ước:

~~~text
missing schemaVersion -> legacy v1
~~~

**Chỉ làm vậy** nếu biết chắc tất cả records không có field này thuộc đúng format v1. Nếu có nhiều legacy formats, cần phân biệt bằng marker khác hoặc dữ liệu nền; gán 1 tùy tiện có thể làm lệch dữ liệu.

### 13.2. Explicit null cho schemaVersion

`"schemaVersion":null` không nên tự coi như missing nếu contract không cho phép. Có thể là dữ liệu lỗi cần repair/quarantine. Nên phân biệt null, missing, non-integer và version vượt khả năng.

### 13.3. Unknown future schema

Reader hỗ trợ tới v3 gặp v7:

~~~text
If operation is read-only and fields stable:
    may expose a supported limited projection.

If operation is a critical write:
    reject as UNSUPPORTED_SCHEMA_VERSION
    unless a documented compatibility path exists.
~~~

### 13.4. Không tự downgrade schema khi ghi

Nếu service v2 đọc document v3 và serialize lại với `schemaVersion=2`, đó không chỉ là thay marker: các field v3 có thể bị cắt, làm hậu quả khó sửa. Một reader cũ không nên vô ý downgrade dữ liệu.

## 14. Upcaster: chuyển document cũ sang model hiện tại

**Upcaster** chuyển representation cũ thành representation logic mới khi đọc, không nhất thiết sửa dữ liệu lưu ngay lập tức.

Ví dụ v1 dùng `fullName`, v2 dùng `displayName`:

~~~json
{"schemaVersion":1,"profileId":"P-100","fullName":"An"}
~~~

Reader v2 muốn:

~~~json
{"schemaVersion":2,"profileId":"P-100","displayName":"An"}
~~~

Một upcaster minh họa:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

public interface DocumentUpcaster {
    int sourceVersion();
    ObjectNode upcast(ObjectNode source);
}

public final class ProfileV1ToV2 implements DocumentUpcaster {
    @Override
    public int sourceVersion() { return 1; }

    @Override
    public ObjectNode upcast(ObjectNode source) {
        ObjectNode result = source.deepCopy();
        JsonNode oldName = result.get("fullName");

        if (!result.has("displayName")) {
            if (oldName == null || !oldName.isTextual()) {
                throw new IllegalArgumentException(
                    "legacy fullName is required"
                );
            }
            result.set("displayName", oldName.deepCopy());
        }

        result.remove("fullName");
        result.put("schemaVersion", 2);
        return result;
    }
}
~~~

### 14.1. Idempotence và version preconditions

Upcaster v1→v2 chỉ nên áp cho document được xác minh là v1. Gọi lại trên v2 không được vô tình mất dữ liệu. Pipeline phải enforce version precondition và kiểm thử từng bước.

### 14.2. Đừng áp default đoán mò

Nếu v1 lưu `total` mà không có currency, upcaster không được lấy default `USD` chỉ vì application mới chạy ở Mỹ. Cần biết currency lịch sử từ schema contract, tenant settings ở mốc hợp lệ hoặc một migration dữ liệu có phân loại.

### 14.3. Upcast on read khác backfill

Upcaster có thể chuyển in-memory mỗi khi đọc. Backfill sửa records lưu thật để giảm chi phí và loại legacy formats. Nếu upcaster tự write-back trong mỗi read, hãy coi đó là một mutation có CAS, retry, durability và tải vận hành.

### 14.4. Không làm side effect ngoài trong upcaster

Upcaster nên deterministic cho cùng input và policy. Không gọi payment gateway hoặc gửi email khi deserialize; đọc một record không được kích hoạt side effect nghiệp vụ.

### 14.5. Chuyển nhiều bước

~~~text
v1 --upcast--> v2 --upcast--> v3 --map--> CurrentDomain
~~~

Mỗi bước có test fixtures riêng, có thể ghi phiên bản của converter/migration. Reader phải từ chối version không có đường đi thay vì âm thầm ép.

## 15. Java: đọc schemaVersion nghiêm ngặt

Một hàm chỉ xử lý **phần version detection**:

~~~java
import com.fasterxml.jackson.databind.JsonNode;

public final class SchemaVersionReader {
    private static final int CURRENT = 3;

    public static int version(JsonNode root) {
        if (root == null || !root.isObject()) {
            throw new IllegalArgumentException("document must be object");
        }

        JsonNode value = root.get("schemaVersion");
        if (value == null) {
            // Explicitly documented: legacy documents without marker are v1.
            return 1;
        }

        if (!value.isIntegralNumber() || !value.canConvertToInt()) {
            throw new IllegalArgumentException("invalid schemaVersion");
        }

        int result = value.intValue();
        if (result < 1) {
            throw new IllegalArgumentException("unsupported legacy version");
        }
        if (result > CURRENT) {
            throw new UnsupportedOperationException(
                "future schema version: " + result
            );
        }
        return result;
    }
}
~~~

`schemaVersion:null` bị từ chối, không được coi như missing. Việc map missing thành 1 ở đây là một **giả định đã được nêu rõ trong ví dụ**; trong hệ thật chỉ áp dụng khi chứng minh đúng với dữ liệu lịch sử.

### 15.1. Range và kiểu

`"schemaVersion":"3"` là string, không tự coercion thành integer trong ví dụ. `schemaVersion=3.0` có thể được Jackson biểu diễn floating, cũng không tự được chấp nhận. Quy tắc nên thống nhất, không để mỗi service đoán khác nhau.

### 15.2. Không chuyển lỗi version thành not-found

Nếu bản ghi tồn tại nhưng không parse được, trả 404 có thể làm caller tạo record trùng hoặc xóa sai. Nên trả lỗi có category như `UNSUPPORTED_SCHEMA` và log safe diagnostic.

### 15.3. Không để client tùy ý gửi schemaVersion storage

Request DTO có thể mang API version khác. Storage schemaVersion nên được writer application định nghĩa; nếu import dữ liệu ngoài, cần validation và conversion trước lưu.

## 16. Enum mở rộng: tránh default sai quyền hoặc trạng thái

Giả sử:

~~~java
public enum AccountState {
    ACTIVE,
    SUSPENDED,
    CLOSED
}
~~~

Phiên bản mới bổ sung `REVIEW_REQUIRED`. Reader cũ không biết giá trị ấy.

### 16.1. Strict reject có thể an toàn hơn

Đối với authorization, payment, fraud hoặc lifecycle state, không nhận biết state có thể phải **fail closed**. Map unknown thành `ACTIVE` có thể cấp quyền sai.

### 16.2. Jackson enum fallback có giới hạn

Một số cấu hình Jackson hỗ trợ:

~~~java
import com.fasterxml.jackson.annotation.JsonEnumDefaultValue;

public enum DisplayTheme {
    LIGHT,
    DARK,

    @JsonEnumDefaultValue
    UNKNOWN
}
~~~

Khi bật `READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE` theo version/cấu hình hỗ trợ, reader có thể đưa literal lạ vào `UNKNOWN`. Điều này hữu ích cho UI theme, nhưng **không nên** dùng một `UNKNOWN` chung để giả vờ `AccountState` đủ an toàn cho quyết định quyền.

### 16.3. Bảo toàn literal chưa hiểu

Nếu đọc rồi ghi lại dữ liệu, chỉ giữ enum `UNKNOWN` sẽ mất string gốc `"SOLARIZED"`. Có thể giữ `rawValue` song song hoặc giữ raw document, tùy contract.

### 16.4. `toString()` không là wire contract mặc định

Nếu thay `enum.toString()` để hiển thị tiếng Việt, rồi serializer ghi giá trị đó thay tên enum, data format có thể đổi. Dùng explicit wire values/annotations và tests.

## 17. Số, tiền, timestamp và Unicode khi deserialize

### 17.1. Số nguyên lớn

Java `int` giới hạn 32-bit; document NoSQL có thể lưu số 64-bit hoặc arbitrary precision theo type. `asInt()` trên số lớn không phải phép chuyển an toàn. Kiểm tra range và dùng `long`, `BigInteger` khi phù hợp.

### 17.2. Decimal và tiền

~~~java
import java.math.BigDecimal;

BigDecimal amount = new BigDecimal("120.50");
~~~

Tránh `new BigDecimal(0.1)` nếu muốn chính xác giá trị thập phân từ chuỗi. Với tiền, một mô hình dùng integer minor units kèm currency có thể ổn định hơn qua JSON; cần xác định rounding/scale.

### 17.3. BSON Decimal128 khác Java double

Đổi Decimal128 sang `double` có thể làm mất precision. Mapper nên convert đúng domain Money type và test qua nhiều giá trị biên. Đừng cho rằng JSON number/BSON numeric types đều tương đương.

### 17.4. Timestamp và timezone

~~~json
{"createdAt":"2026-11-14T08:00:00Z"}
~~~

Phân biệt một `Instant` tuyệt đối với `LocalDateTime` không timezone. Nếu lưu lịch họp “9:00 sáng mỗi thứ Hai ở Hà Nội”, cần timezone ID và recurrence semantics, không chỉ một epoch timestamp.

### 17.5. Jackson Java Time

Jackson có module hỗ trợ Java Time types như `Instant`, `OffsetDateTime`. Khi dùng `JavaTimeModule`, phải thống nhất serialization format (ISO string hay epoch), precision và configuration. Không phỏng đoán default giống nhau giữa mọi Spring/Jackson version.

### 17.6. Unicode

Hai chuỗi trông giống nhau có thể khác Unicode normalization; username và unique-key strategy cần chuẩn hóa theo policy. Tránh biến đổi Unicode trên read rồi full replace một document không sở hữu, gây đổi ID/tên ngoài ý định.

### 17.7. Binary

BSON binary, base64 JSON và Java `byte[]` có các convention khác nhau. Cần validate size/content type và không lưu raw secrets qua API DTO không kiểm soát.

## 18. MongoDB Java: BSON, POJO codecs và sự khác biệt kiểu

MongoDB lưu BSON, không chỉ JSON. BSON có các types như ObjectId, Date, Binary, Decimal128 và numeric widths. MongoDB Java driver có cơ chế codec/POJO mapping, còn Jackson thường dùng cho JSON HTTP hoặc mapping tùy chọn.

### 18.1. Không assume Jackson mapping = BSON codec

Một field Jackson đã annotate `@JsonProperty("display_name")` không đương nhiên được MongoDB POJO codec mapping cùng cách nếu adapter chưa cấu hình tương ứng. Chọn mapper rõ ràng và test cả HTTP serialization lẫn persistence serialization.

### 18.2. Null và missing

Một BSON document có field bị thiếu khác document có explicit BSON null. Query operators và indexes có thể xử lý hai tình huống theo semantics sản phẩm. Adapter không được làm phẳng hai loại nếu domain phân biệt chúng.

### 18.3. `_id` và ObjectId

Java có thể dùng string public ID nhưng database dùng ObjectId/compound tenant key. Mapper phải xác định conversion an toàn; không để driver tự tạo ID mới khi reserializing một entity cũ mà key bị thiếu.

### 18.4. Unknown fields + replacement

Nếu đọc document bằng POJO codec chỉ map các fields đã biết rồi `replaceOne` toàn document, fields mới có thể bị cắt. Dùng targeted `$set/$unset`, raw Document preservation hoặc schema-aware mapping kèm CAS khi cần.

### 18.5. Schema validation ở database

Nếu MongoDB collection có JSON Schema validation, Java DTO validation và database validation có thể lệch trong rolling deployment. Expand constraints trước, chuẩn bị readers/writers, rồi tighten khi dữ liệu cũ đã migration.

### 18.6. `_etag`/entityVersion không phải schemaVersion

Không dùng `schemaVersion` làm expectedVersion cho every update, vì schemaVersion có thể không đổi qua hàng trăm mutations. Cần business/data revision token riêng.

## 19. DynamoDB Java: AttributeValue và field preservation

Với AWS SDK for Java v2, DynamoDB có native attribute-value types (`S`, `N`, `BOOL`, `L`, `M`, `NULL`, v.v.). SDK Enhanced Client có mapping Java bean/immutable classes với annotations và conversion.

### 19.1. Phân biệt absent attribute và NULL attribute

Một item không chứa `nickname` khác item có `"nickname": {"NULL": true}` theo native representation. Conversion sang Java `null` có thể làm mất phân biệt khi dùng một DTO đơn giản.

### 19.2. `PutItem` khác `UpdateItem`

`PutItem` thường biểu diễn viết item đầy đủ theo API; nếu Java mapper làm mất các attributes reader không biết, full put/replace có thể xóa fields mới. `UpdateItem` với expression cụ thể thường cho phép chỉ sửa fields đã chọn.

### 19.3. Enhanced Client và nulls

Behavior của null/empty/ignoreNulls trong update cần xác minh theo API/overload và SDK version; đừng mặc định một null Java nghĩa “không đụng”, “xóa attribute” hay “ghi NULL”. Hãy định nghĩa explicit patch operations và test wire requests.

### 19.4. Number representation

DynamoDB `N` được truyền bằng string representation, không phải JSON number nguyên trạng. Adapter phải parse với `BigDecimal`/`BigInteger` hoặc `long` theo domain và enforce precision/range. Không chuyển tiền thành floating-point một cách âm thầm.

### 19.5. Conditional update

Để tránh old writer ghi đè new fields, dùng condition theo entityVersion và update expression chỉ chạm fields mà writer sở hữu. Cross-item atomicity/idempotency phải nằm trong transaction scope hỗ trợ.

### 19.6. GSI và schema evolution

Thêm một indexed attribute có thể làm records cũ không xuất hiện trong access pattern mới cho tới khi được backfill. Mapping Java đọc đúng object không bảo đảm query qua GSI tìm được dữ liệu cũ.

## 20. Cosmos DB, Couchbase, Cassandra và Redis

### 20.1. Cosmos DB for NoSQL

JSON document, partition key và ETag cùng tồn tại. Replace toàn item từ DTO cũ có thể làm mất field mới; patch operations và `If-Match` khi API hỗ trợ phù hợp hơn cho một số updates. ETag là token optimistic concurrency, **không phải schemaVersion**.

### 20.2. Couchbase

JSON documents cùng SDK transcoder/serializer configuration. Sub-document mutations có thể thay một path mà không thay toàn document; CAS token bảo vệ lost update. Khi full document round-trip, unknown fields vẫn có nguy cơ bị mất nếu POJO không giữ chúng.

### 20.3. Cassandra/ScyllaDB

CQL columns/schema và Java driver codecs có rules riêng. `NULL` có thể gắn với deletion/tombstone semantics; `UNSET` là khái niệm riêng trong prepared statement/bindings để không ghi giá trị vào column tương ứng theo contract. Không dùng một nullable Java bean để tự đoán ý định `SET`, `NULL`, `UNSET`.

### 20.4. Redis

Redis keys có thể lưu string, binary, hash hoặc RedisJSON nếu deployment có module tương ứng. Nếu tự serialize object thành JSON string, server không tự hiểu schemaVersion/unknown fields; adapter chịu trách nhiệm migration, TTL và atomic update. Một `GET`-deserialize-`SET` vòng lại có thể làm mất fields và lost update, cần CAS/Lua/transaction/version policy phù hợp.

### 20.5. Đa backend không nghĩa đa semantics

Nếu một service migrate từ MongoDB sang DynamoDB, dù hai adapter cùng trả `Profile` Java object, chúng có thể khác ở numeric type, absent/null, update operation, consistency, token và index behavior. Kiểm thử **data equivalence cùng semantics**, không chỉ compile interface.

## 21. JSON, BSON, Protobuf, Avro: khác nhau ở schema evolution

| Định dạng | Cách biểu diễn | Lưu ý khi thay schema |
|---|---|---|
| JSON | Key–value text theo field name | Unknown properties, missing/null, coercion |
| BSON | Typed binary document | Native numeric/date/ObjectId/binary types |
| Protobuf | Numbered fields, wire types | Không tái sử dụng field numbers; default/presence/unknown fields |
| Avro | Writer/reader schema resolution | Defaults, type promotions, unions, aliases, registry policy |
| CQL row | Column schema/typed bindings | Nullable/missing, prepared statements, migrations |
| Redis bytes | App-defined encoding | Version header, serializer, migration tự quản |

### 21.1. Protocol Buffers

Ví dụ:

~~~proto
syntax = "proto3";

message ProfileEvent {
  string profile_id = 1;
  string display_name = 2;
  optional string nickname = 3;
}
~~~

Field numbers là một phần của wire contract. **Không tái sử dụng số field đã xóa cho nghĩa khác**, và sử dụng `reserved` cho numbers/names bị bỏ khi phù hợp. Proto3 scalar presence phụ thuộc khai báo `optional`, message fields, oneof và compiler/runtime version; không mặc định giá trị `""` cho biết field có được gửi hay không.

### 21.2. Unknown fields trong Protobuf

Nhiều Protobuf runtimes có khả năng giữ unknown fields qua binary parsing/serialization, nhưng điều này còn phụ thuộc ngôn ngữ/runtime, transforms và việc chuyển qua JSON. Không dựa vào round-trip preservation mà không kiểm thử đường serialization thực.

### 21.3. Avro schema resolution

Reader mới đọc writer cũ thông qua resolution rules. Field mới trong reader cần default phù hợp nếu writer cũ không cung cấp, theo schema compatibility rule. Đổi tên field có thể dùng aliases trong điều kiện được hỗ trợ. Không nhầm Avro default với việc dữ liệu được rewrite vật lý.

### 21.4. Schema registry

Registry có thể kiểm backward/forward/full compatibility cho event schemas. Nhưng registry không kiểm hộ **business invariants**, timezone conversions, precision hay side effect của consumer. Vẫn cần domain tests.

### 21.5. JSON envelope và event version

~~~json
{
  "eventId": "evt-100",
  "eventType": "ProfileUpdated",
  "eventSchemaVersion": 2,
  "aggregateId": "P-100",
  "payload": {
    "displayName": "An",
    "nickname": null
  }
}
~~~

`eventSchemaVersion` không phải database document `schemaVersion`; chúng có thể tiến hóa độc lập. Event được lưu trong queue lâu ngày có thể được replay bởi consumer mới, cần event upcaster hoặc version-aware handler.

## 22. Tolerant readers và “robustness principle” có giới hạn

Một consumer chịu lỗi field lạ có thể giúp rolling deployments. Tuy nhiên, “chấp nhận mọi input” gây nguy hiểm:

- Typo field biến thành silent no-op.
- JSON với field quyền mới bị bỏ qua dù nó phải làm thay đổi quyết định.
- Kiểu string `"true"` bị tự ép thành boolean `true` không theo API contract.
- Duplicate JSON keys có thể được các parsers xử lý khác nhau.
- Unknown field cực lớn gây memory pressure hoặc DoS.

### 22.1. Validate trước khi domain sử dụng

Một luồng an toàn:

~~~text
trusted/authorized source?
    -> parse with bounded size/depth
    -> check schemaVersion
    -> upcast known versions
    -> validate type/range/invariants
    -> map to domain
~~~

### 22.2. Strict public ingress, tolerant trusted persistence có kiểm soát

Không có cấu hình Jackson duy nhất phải dùng cho cả REST requests và database read. Có thể dùng ObjectMapper/reader policies riêng cho từng boundary, để tránh “sửa lỗi compatibility” bằng cách nới lỏng cả security input.

### 22.3. Không dùng unknown field để vượt ownership

Một DTO có extension map chỉ nên bảo toàn fields từ persistence source đáng tin, không serialize nguyên các extras do client gửi vào document privileged. Cần allowlist và authentication.

## 23. Semantic defaults: chỉ đặt khi chắc chắn

Giả sử V2 thêm:

~~~json
{
  "newsletterOptIn": false
}
~~~

Nếu V1 không có field, việc gán `false` là một quyết định hợp lý **chỉ khi chính sách cũ là không opt-in**. Nếu hệ trước đây không ghi nhận consent, có thể cần trạng thái `UNKNOWN` chứ không thể tự suy `false`/`true`.

### 23.1. Ba cách đặt default

1. **Read-time default:** reader hiển thị giá trị logic mà không sửa stored record.
2. **Write-time default:** writer mới luôn ghi field rõ cho new entities.
3. **Backfill:** migration cập nhật records cũ với evidence/policy đủ chắc.

Ba cách có chi phí và rủi ro khác nhau; không tự thay thế cho nhau.

### 23.2. Null không mặc định là missing

Một user có thể chủ ý đặt `nickname:null`; nếu reader tự áp default `"Anonymous"` cho cả missing và null, sẽ mất khả năng biểu diễn trạng thái clear.

### 23.3. Default thay đổi theo thời gian

Nếu default locale của tổ chức chuyển từ `vi-VN` sang `en-US`, document cũ không có locale có thể bị hiển thị khác giữa các releases nếu mỗi lần đọc dùng default hiện tại. Có thể cần lưu versioned default theo thời điểm tạo hoặc backfill trước khi đổi behavior.

### 23.4. Default là một phần của contract

Giá trị mặc định phải được tài liệu hóa, test và migration như các field khác. Một silent Jackson default không phải business decision đáng tin.

## 24. Presence và cập nhật dữ liệu qua API

Xét `PATCH /profiles/P-100`:

~~~json
{"nickname":null}
~~~

Nếu API chọn JSON Merge Patch, đây là lệnh xóa nickname. Nếu API dùng custom PATCH DTO mà `null` nghĩa “không thay đổi”, payload có nghĩa khác. Hợp đồng API phải ghi rõ.

### 24.1. PUT và PATCH

**PUT full replacement** thường mang representation đầy đủ theo contract; việc thiếu field có thể dẫn đến mất field nếu server thực hiện full replace. **PATCH** mô tả các thay đổi, nhưng vẫn cần định nghĩa partial document/merge/remove semantics, validation và atomicity.

### 24.2. `@JsonInclude(Include.NON_NULL)` không sửa được semantics

Omit null khi serialize có thể làm mất ý định xóa field nếu endpoint dựa vào explicit null. Annotation là quy tắc biểu diễn, không thay business specification.

### 24.3. Nullability annotations không tự tạo validation

`@NotNull`, `@JsonProperty(required=true)`, Jackson constructor validation và Bean Validation hoạt động theo thư viện/config/validation invocation cụ thể. Không giả định chỉ thêm annotation là mọi missing/null đều bị từ chối đúng trong mọi mapper.

### 24.4. Test presence ở cả request và persistence

Ứng dụng có thể nhận PATCH đúng nhưng adapter lại map `Clear` thành Java null và Enhanced Client bỏ qua null, khiến field không xóa; hoặc map `Keep` thành null rồi vô tình xóa. Phải test end-to-end operation semantics.

## 25. Khi document schema mới hơn code đang chạy

Một document có `schemaVersion=5`, nhưng service chỉ biết tới v3. Ba chiến lược:

| Chiến lược | Khi có thể dùng | Rủi ro |
|---|---|---|
| Fail closed | Critical writes, state machine, authorization | Có thể giảm availability |
| Limited read-only projection | UI cần một số fields ổn định | Hiển thị thiếu ý nghĩa mới |
| Opaque preserve + safe patch | Schema owner cho phép sửa field độc lập | Vẫn cần CAS và trust boundary |

### 25.1. Không tự viết ngược về schema v3

Nếu service ghi full replace từ V3 DTO, nó có thể xóa những fields V5. Khi không hiểu future schema, mặc định tốt cho critical write là `UNSUPPORTED_SCHEMA_VERSION` hoặc route tới compatible writer.

### 25.2. Version gắn với tenant hoặc document

Trong migration dần, có thể một tenant còn v1, tenant khác v3, thậm chí documents cùng tenant khác versions. Không chỉ dựa vào application deployment version để suy format từng record.

### 25.3. Feature flags không đủ nếu writer cũ chạy song song

Bật flag V3 trên một node không ngăn V1 nodes ghi full replacement. Cần read/write compatibility và rollout ordering cụ thể.

### 25.4. Ghi nhận unsupported schema

Không lặp retry 100 lần với cùng reader không hỗ trợ v5; đây là terminal compatibility issue cho binary hiện tại. Báo dashboard/alert và canary rollback plan phù hợp.

## 26. Schema migration: expand–migrate–contract

Một lộ trình thay `fullName` thành `displayName`:

~~~mermaid
flowchart TD
    A["V1: fullName"] --> B["Expand readers: accept fullName/displayName"]
    B --> C["Deploy writers V2 with safe compatibility"]
    C --> D["Backfill old records in batches"]
    D --> E["Check coverage, lag, old writers"]
    E --> F["Contract: stop accepting fullName when safe"]
~~~

### 26.1. Expand readers trước

Reader mới hiểu cả hai fields và quyết định precedence rõ nếu cả hai cùng tồn tại. Không lấy giá trị ngẫu nhiên nếu `fullName` và `displayName` mâu thuẫn; cần migration policy.

### 26.2. Writer phase

Nếu V1 vẫn còn cần đọc, một số migration dùng **dual-write có kiểm soát vào hai fields trên cùng record**, kèm version/ETag và rõ nguồn chính. Không nhầm dual-write hai fields trong một atomic document update với dual-write hai databases độc lập.

### 26.3. Backfill có checkpoint

Quét theo index/range phù hợp, giới hạn throughput, retry idempotently, ghi progress và metrics. Mỗi update cần CAS hoặc guarded patch để không ghi đè user edit vừa xảy ra.

### 26.4. Validate dữ liệu thực

Không chỉ đếm documents. Cần xác định missing vs null, kiểu không hợp lệ, timezone/currency edge cases và những tenant chưa migrate.

### 26.5. Contract sau bằng chứng

Chỉ xóa field cũ/upcaster khi chứng minh không còn readers/writers/queues/backup/offline clients cần format ấy trong policy window. Retiring code quá sớm có thể làm restore hoặc replay thất bại.

### 26.6. Rollback

Nếu code V2 rollback nhưng dữ liệu đã được V2 ghi, V1 có thể không hiểu. Kế hoạch rollout phải có fallback version tương thích hoặc cơ chế roll forward; không coi “deploy bản cũ” luôn an toàn.

## 27. Backfill và optimistic concurrency

Một migration worker đọc document:

~~~json
{
  "profileId": "P-100",
  "schemaVersion": 1,
  "fullName": "An",
  "entityVersion": 8
}
~~~

Trước khi worker viết, user đổi tên thành "An Nguyễn" làm entityVersion thành 9. Nếu worker thay toàn document từ snapshot version 8, user change có thể mất.

### 27.1. Chỉ cập nhật khi precondition còn đúng

~~~text
IF schemaVersion=1
   AND entityVersion=8
THEN migrate fields and advance entityVersion
ELSE re-read and re-evaluate
~~~

Không chỉ so schemaVersion; business fields có thể đã thay đổi trong cùng version schema.

### 27.2. Chunked migration

Đừng giữ một transaction/lock khổng lồ cho toàn bộ collection. Batch theo partition/tenant, có throttling, checkpoint, reconciliation và rollback plan; đảm bảo không vượt giới hạn request size/quota.

### 27.3. Idempotent migration

Mỗi bước nên nhận biết record đã migrate để không apply conversion tiền/timestamp hai lần. Một lỗi nhân 100 ở v1→v2 lặp hai lần có thể biến 12.5 thành 125000.

### 27.4. Không dùng read path làm batch migrator vô hạn

Upcast on read có thể hợp lý, nhưng write-back tự động mọi read có thể tạo tải và conflicts. Backfill riêng giúp quota/visibility và kiểm soát blast radius.

## 28. Event/schema evolution và outbox

Một document V3 có thể tạo event payload schema V1:

~~~json
{
  "eventType": "ProfileUpdated",
  "eventSchemaVersion": 1,
  "aggregateId": "P-100",
  "payload": {
    "displayName": "An"
  }
}
~~~

Không bắt buộc event schema version trùng document schema version. Consumers tiến hóa theo tốc độ khác nhau.

### 28.1. Producer và consumer hỗ trợ version nào?

Một consumer mới có thể đọc events cũ từ queue/replay, nên cần backward compatibility/upcasters. Một producer mới có thể thêm field trong lúc consumer cũ chưa deploy, nên cần forward compatibility hoặc rollout gates.

### 28.2. Unknown enum event

Nếu `OrderStatusChanged` thêm `ON_HOLD`, consumer v1 không được tự coi `ON_HOLD` như `PAID` chỉ vì unknown enum fallback. Có thể route vào DLQ/unsupported-event monitor hoặc dùng generic projection phù hợp.

### 28.3. Schema registry không thay domain review

Một registry có thể kiểm field type/compatibility rules của Avro/Protobuf, nhưng không chứng minh thêm `authorizationDecision` field là an toàn khi consumer cũ bỏ qua.

### 28.4. Event version và idempotency

`eventId` phải ổn định qua redelivery; `eventSchemaVersion` mô tả payload; `aggregateVersion` mô tả thứ tự business event. Không dùng một field `version` duy nhất cho tất cả.

### 28.5. CDC raw payload có thể chứa schema khác nhau

Change stream từ DB có thể phát documents v1 và v3. Integration layer nên deserialize version-aware và phát typed domain event có contract, không yêu cầu mọi consumer hiểu toàn bộ lịch sử storage representation.

## 29. Validation, bảo mật và dữ liệu không đáng tin

### 29.1. Mass assignment

API nhận:

~~~json
{
  "displayName": "An",
  "role": "ADMIN",
  "tenantId": "tenant-B"
}
~~~

Nếu bind thẳng vào persistence document và save, caller có thể thay fields không được phép. Input DTO và allowlist fields phải độc lập với storage serializer; authorization phải kiểm resource/tenant.

### 29.2. Duplicate JSON keys

~~~json
{"role":"USER","role":"ADMIN"}
~~~

Đây là payload có keys trùng; một số parsers có thể chọn giá trị đầu/cuối hoặc cho phép tùy cấu hình. Với security-sensitive APIs, nên cấu hình duplicate field detection/validation và kiểm soát parser behavior để không có parser differential giữa gateway/app/DB.

### 29.3. Oversized/deep documents

Unknown field chứa một array khổng lồ hoặc nested object rất sâu có thể gây memory pressure. Đặt max body size, depth, field count và tenant quota ở boundary.

### 29.4. Polymorphic deserialization

Không bật unrestricted polymorphic typing cho JSON từ nguồn không đáng tin. Nếu dùng subtype discriminator, giới hạn allowed subtypes và validate type names theo schema, tránh nguy cơ deserialize type không mong muốn.

### 29.5. Sensitive history

Giữ raw unknown fields/old schema versions có thể giữ PII đã bị xóa khỏi current model. Retention, access control, backup và erasure workflow phải áp lên history/extension storage.

### 29.6. Encryption và schema evolution

Thay encrypted field format/key identifier cần migration-aware decoder và key rotation plan. Không log plaintext khi deserialize lỗi; security metadata không nên được client tự chọn.

## 30. Test compatibility: fixtures theo phiên bản

Một bộ test cần chứa **raw serialized fixtures** đại diện dữ liệu thật, không chỉ tạo object Java rồi serialize bằng mapper hiện tại.

~~~text
fixtures/
    profile-v1-minimal.json
    profile-v1-null-nickname.json
    profile-v2-new-field.json
    profile-v3-unknown-enum.json
    profile-invalid-version.json
    profile-invalid-type.json
~~~

### 30.1. Những trường hợp tối thiểu

| Test | Mục tiêu |
|---|---|
V1 không có schemaVersion | Legacy default chỉ áp khi hợp đồng cho phép |
Field missing | Reader dùng default đúng/giữ presence |
Field explicit null | Không nhầm với missing |
Unknown field V3 | Ignore/reject/preserve đúng boundary |
Unknown nested field | Không mất dữ liệu lúc round-trip |
Invalid type | Không coercion nguy hiểm |
Unknown enum | Fail closed hoặc fallback có chủ đích |
Decimal lớn | Không mất precision/overflow |
Timestamp timezone | Đúng offset/instant semantics |
Duplicate keys | Parser policy nhất quán |
Full replace của reader cũ | Không xóa fields mới ngoài ý định |
Concurrent write/migration | CAS chống lost update |
Version v999 | Không downgrade/mutate |
Schema rollout mixed versions | Old/new reader–writer matrix |
CDC/event replay | Consumer đọc event cũ đúng |
Tenant auth + unknown field | Không mass-assign/chiếm quyền |

### 30.2. Mẫu JUnit với Jackson `JsonNode`

~~~java
import static org.junit.jupiter.api.Assertions.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.Test;

class SchemaCompatibilityTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void missingAndNullAreDifferent() throws Exception {
        JsonNode missing = mapper.readTree("{}");
        JsonNode explicit = mapper.readTree("{\"nickname\":null}");

        assertNull(missing.get("nickname"));
        assertTrue(explicit.has("nickname"));
        assertTrue(explicit.get("nickname").isNull());
    }

    @Test
    void acceptsDocumentedLegacyVersion() throws Exception {
        JsonNode legacy = mapper.readTree(
            "{\"profileId\":\"P-100\",\"fullName\":\"An\"}"
        );
        assertEquals(1, SchemaVersionReader.version(legacy));
    }

    @Test
    void rejectsExplicitNullSchemaVersion() throws Exception {
        JsonNode bad = mapper.readTree("{\"schemaVersion\":null}");
        assertThrows(
            IllegalArgumentException.class,
            () -> SchemaVersionReader.version(bad)
        );
    }

    @Test
    void rejectsUnknownFutureSchemaForCriticalReader()
        throws Exception {
        JsonNode future = mapper.readTree("{\"schemaVersion\":99}");
        assertThrows(
            UnsupportedOperationException.class,
            () -> SchemaVersionReader.version(future)
        );
    }
}
~~~

`SchemaVersionReader` là class ví dụ ở mục 15; test skeleton minh họa ý định, không thay thế kiểm thử trên adapter/SDK thực. Theo quy trình viết bài này, **không chạy JUnit hoặc Content QA**.

### 30.3. Test không nên chỉ round-trip qua cùng writer

Nếu mapper hiện tại bỏ qua một field, test serialize rồi deserialize object do chính mapper tạo sẽ không bao giờ thấy field lạ. Cần fixtures được lưu từ writer cũ/mới hoặc tạo payload với unknowns chủ đích.

### 30.4. Golden data và migration checks

Giữ fixtures cho mỗi format đã deploy. Khi đổi serializer version, chạy compatibility matrix tự động và so domain meaning, không chỉ equality của JSON whitespace hoặc field order.

## 31. Java: bảo toàn unknown fields khi làm việc với JsonNode

Nếu ứng dụng phải giữ raw document nhưng chỉ thay một field, cách trực quan là copy tree:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

public final class ProfileTreeEditor {
    private final ObjectMapper mapper = new ObjectMapper();

    public String updateDisplayName(String json, String newName)
        throws Exception {

        JsonNode parsed = mapper.readTree(json);
        if (!(parsed instanceof ObjectNode original)) {
            throw new IllegalArgumentException("object expected");
        }

        int version = SchemaVersionReader.version(original);
        if (version > 3) {
            throw new IllegalArgumentException("schema not supported");
        }
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("invalid displayName");
        }

        ObjectNode result = original.deepCopy();
        result.put("displayName", newName);

        // This only transforms an in-memory representation.
        // Do not save via full replace without a correct CAS contract.
        return mapper.writeValueAsString(result);
    }
}
~~~

### 31.1. Cách này bảo toàn raw fields có điều kiện

Nếu JSON có `contactPreferences` chưa biết, copy tree giữ nó trong representation. Nhưng việc **cho phép ghi cả tree** còn cần ownership, trusted source, size/depth validation và conditional update tại database.

### 31.2. Không tự nâng schemaVersion chỉ vì đổi displayName

Nếu document v1 chưa được upcast thành v2, viết một trường v2 mà vẫn gắn schemaVersion=1 có thể tạo hybrid format. Writer cần either route qua migration pipeline hoặc patch một field có ngữ nghĩa tương thích theo contract.

### 31.3. Không ghi đè sau stale read

Hai writers có thể cùng copy tree v3 rồi sửa fields khác nhau. Nếu cả hai full replace mà không CAS, writer sau làm mất thay đổi của writer trước. Targeted patch hoặc guarded update là an toàn hơn khi đủ.

### 31.4. Bảo toàn bytes không phải bảo toàn mọi semantics

Serializer có thể reorder fields, normalize number representations hoặc thay timestamp encoding dù `JsonNode` giữ keys. Nếu yêu cầu cryptographic signature hay canonical hash, phải có canonical serialization rule riêng.

## 32. Observability và vận hành schema evolution

| Metric/trace | Câu hỏi |
|---|---|
| Documents theo schemaVersion | Còn bao nhiêu v1/v2/v3? |
| Deserialization failures | Version/type nào gây lỗi? |
| Unknown field count | Producer nào đang ghi fields mới? |
| Unknown enum count | Có state chưa được reader hiểu? |
| Missing required field rate | Dữ liệu cũ hay writer lỗi? |
| Upcaster latency | Read path có bị chậm? |
| Backfill progress | Đã migrate tới checkpoint nào? |
| CAS conflict trong migration | Có writer đồng thời không? |
| Old-version writer rate | Rolling deployment đã kết thúc chưa? |
| Projection/index lag | Query có bỏ sót dữ liệu do chưa backfill? |
| Schema validation rejects | Deploy mới có làm đứt writes không? |
| Full-replace operations | Có nguy cơ xóa fields mới? |
| Event schema versions | Consumer đã sẵn sàng chưa? |
| Quarantined records | Bao nhiêu dữ liệu không đọc an toàn? |

### 32.1. Đừng biến unknown field thành silent metric-only

Nếu unknown field liên quan quyền/tiền/state, metric có ích nhưng service cần **dừng operation nguy hiểm**. Monitoring không bù được correctness.

### 32.2. Alert theo tỷ lệ và tenant

Một tenant có nhiều legacy records có thể gây hot upcaster path; theo dõi tỷ lệ lỗi và p99, không chỉ tổng count. Tuy nhiên tránh dùng từng entityId làm metric label cardinality vô hạn.

### 32.3. Diagnostics phải bảo vệ PII

Log field names, version và safe IDs là đủ trong nhiều trường hợp. Không log full customer profile hoặc secrets khi parser báo lỗi.

### 32.4. Kết nối deployment health và schema health

`serviceUp=true` không bảo đảm service hiểu tất cả document versions. Canary có thể pass HTTP health nhưng fail khi gặp một legacy subtype; cần sample/fixture tests và real error metrics.

## 33. Quy trình vận hành một thay đổi schema

1. **Xác định boundary:** API request, persistence document, event, cache hay backup?
2. **Viết schema contract hiện tại:** Kiểu, nullability, optional, defaults, ownership, version.
3. **Lập reader–writer compatibility matrix** cho tất cả versions còn hỗ trợ.
4. **Đánh giá unknown fields:** Ignore, preserve hay reject cho từng boundary.
5. **Đánh giá business semantics:** Enum mới, currency, consent, permissions, state transitions.
6. **Định nghĩa version marker:** Phân biệt schemaVersion, entityVersion, ETag, eventVersion.
7. **Tạo upcasters/defaults có bằng chứng**, không dựa vào coercion vô thức.
8. **Viết fixtures cũ/mới**, gồm missing, null, unknown, malformed và nested fields.
9. **Tách public DTO khỏi persistence DTO** nếu có nguy cơ mass assignment.
10. **Ưu tiên targeted conditional writes**, tránh old-reader full replacement.
11. **Deploy backward-compatible readers trước** khi writers dùng schema mới.
12. **Thực hiện backfill có CAS và checkpoint** nếu migration lưu trữ cần thiết.
13. **Kiểm soát writers cũ**, nhất là instances có thể rollback/offline workers.
14. **Theo dõi lỗi version/unknown field**, phát hiện model còn không tương thích.
15. **Chỉ contract/drop old fields sau bằng chứng** về backlog/backup/offline windows.
16. **Lập rollback/roll-forward plan** không làm dữ liệu mới không đọc được.
17. **Đánh giá privacy/retention** cho old fields và snapshots.
18. **Kiểm thử trên SDK/backend thật** nếu absent/null/patch/replace semantics phụ thuộc sản phẩm.

### 33.1. Mẫu chính sách schema

~~~yaml
entity: Profile
storageFormat: JSON-or-BSON
currentSchemaVersion: 3

versionPolicy:
  missingSchemaMarker: "legacy-v1-only-if-verified"
  explicitNullSchemaMarker: "reject"
  futureVersion: "no-critical-writes"
  entityVersion: "separate CAS counter"

fields:
  nickname:
    missing: "use documented legacy meaning"
    null: "represents no nickname"
    patchNull: "clear under the selected PATCH contract"
  timeZone:
    missing: "no assumption unless policy defines one"
    unknownToOldReader: "preserve or forbid full replacement"

readers:
  supportedVersions: [1, 2, 3]
  upcast: "v1 -> v2 -> v3"
  publicInputUnknown: "reject"
  readOnlyProjectionUnknown: "ignore-with-telemetry"

writers:
  schemaVersion: 3
  updateMode: "targeted conditional patch"
  fullReplace: "only with compatible schema and CAS"

testing:
  historicalFixtures: "required"
  mixedVersionDeployment: "required"
  nullMissingUnknown: "required"
  concurrencyMigration: "required"
~~~

Đây chỉ là mẫu review. Các policies phải được xác nhận từ nghiệp vụ, SDK version và dữ liệu thực, không copy máy móc.

## 34. Những hiểu nhầm thường gặp

### “NoSQL không có schema nên không cần version”

Sai. Reader Java vẫn kỳ vọng tên field, type, enum và meaning. Schema có thể không được DB enforce nhưng vẫn tồn tại.

### “Missing và null là một”

Sai với PATCH, defaulting, validation, audit và business meaning.

### “Unknown field cứ ignore là forward-compatible”

Chưa đủ. Read có thể pass nhưng full replacement có thể xóa field ấy, hoặc field mới thay nghĩa nghiệp vụ.

### “Jackson ignoreUnknown giúp giữ fields mới”

Không. Nó chỉ bỏ qua khi deserialize, không tự giữ thông tin để serialize lại.

### “Đổi Java field name không ảnh hưởng data”

Có thể là breaking change nếu wire/storage name cũng thay mà không có alias/upcaster.

### “Thêm optional field luôn an toàn”

Chỉ khi defaults, validation, reader–writer compatibility và ownership phù hợp; old writer vẫn có thể xóa field.

### “schemaVersion và entityVersion là cùng một”

Không. Chúng phục vụ tiến hóa cấu trúc và optimistic concurrency khác nhau.

### “Một schemaVersion lớn nghĩa record mới nhất”

Không. Một record v2 có thể được sửa nhiều lần sau một record v3 khác.

### “Unknown enum cứ map ACTIVE”

Nguy hiểm với quyền truy cập, thanh toán hoặc state transitions.

### “Mọi numeric JSON đều chuyển được sang double”

Chuyển có thể mất precision, đặc biệt với tiền và số nguyên lớn.

### “`@NotNull` tự bảo đảm mọi parser reject missing”

Không mặc định. Cần Bean Validation invocation/mapping configuration phù hợp.

### “`@JsonInclude(NON_NULL)` sửa mọi lỗi PATCH”

Không. Nó có thể làm mất explicit-null intent.

### “Cứ dùng full document replacement là đơn giản nhất”

Có thể mất unknown fields hoặc concurrent writes. Targeted CAS patch thường phù hợp hơn cho partial edits.

### “Có JsonNode deepCopy là không còn data loss”

Vẫn có race condition, schema semantic mismatch, reserved fields và normalization differences.

### “ETag là schema version”

Không. ETag chủ yếu là version/revision token của resource theo API.

### “Upcaster có thể đoán currency của tài liệu cũ”

Không được nếu thiếu bằng chứng về đơn vị/loại tiền; phải fail hoặc tìm nguồn lịch sử.

### “Backfill có thể overwrite tất cả vì đây là migration”

Migration vẫn cạnh tranh với user writes; cần CAS/checkpoint và logic idempotent.

### “Old binary luôn rollback được”

Không nếu new writers đã ghi schema mà old binary không hiểu.

### “Avro/Protobuf registry bảo đảm business compatibility”

Registry kiểm một số quy tắc schema, không kiểm domain invariants hoặc security meaning.

### “Unknown properties từ API có thể giữ trong extension map an toàn”

Không nếu chưa có allowlist/authorization; có thể mass assignment.

### “MongoDB BSON và JSON có kiểu giống hệt”

Không. BSON có các native types và conversion rules riêng.

### “DynamoDB null Java chắc chắn nghĩa remove”

Không thể suy chung; tùy API/mapper/options và operation.

### “TTL xóa chính xác tại expiresAt”

Không nhất thiết. Business expiry và physical cleanup là hai cơ chế.

### “Chỉ test object Java serialize–deserialize là đủ”

Không, vì không thử historical raw fixtures, unknown fields hoặc vendor-specific wire behavior.

## 35. Bài tập thực hành

### Bài 1 — Missing so với null

Cho ba payload `{}`, `{"nickname":null}` và `{"nickname":"An"}`. Thiết kế result type KEEP/CLEAR/SET cho PATCH, chỉ rõ defaulting trong full-document read.

### Bài 2 — Unknown field bị mất

V1 Java DTO chỉ có name; V2 document thêm `timeZone`. Mô tả quy trình V1 read–replace khiến timeZone bị xóa và hai phương án phòng tránh (patch/CAS hoặc preserve-schema-aware).

### Bài 3 — Chọn strict hay lenient

Thiết kế chính sách unknown fields cho API tạo User, read-only search projection, database updater và event consumer. Nêu lý do bảo mật/correctness.

### Bài 4 — Schema vs entity version

Một document có `schemaVersion=3`, `entityVersion=42`, `eventSequence=100`. Giải thích mục đích từng field. Vì sao không dùng schemaVersion làm CAS token?

### Bài 5 — Matrix tương thích

V1 `{name}`, V2 `{name,timeZone?}`. Kiểm backward/forward read compatibility; sau đó phân tích vì sao full replacement V1 vẫn phá V2.

### Bài 6 — Rename field

Chuyển `fullName` sang `displayName` trong rolling deployment. Thiết kế dual reader, writer rollout, migration/backfill, conflict resolution và giai đoạn bỏ field cũ.

### Bài 7 — JSON null và Merge Patch

So sánh PUT, RFC 7396 Merge Patch và RFC 6902 JSON Patch trong trường hợp muốn xóa nickname; nêu cách biểu diễn thao tác và khi nào dùng CAS.

### Bài 8 — Java JsonNode

Viết hàm phân biệt field `age` missing, JSON null, integer hợp lệ, string sai kiểu. Không dùng `asInt()` mà không kiểm type/range.

### Bài 9 — Jackson ignoreUnknown

Một class dùng `@JsonIgnoreProperties(ignoreUnknown=true)`. Đọc JSON có unknown `loyaltyTier`. Giải thích state nào mất sau deserialize và tại sao round-trip có thể xóa field.

### Bài 10 — Extension map

Thiết kế `@JsonAnySetter` bảo toàn unknown properties từ trusted storage nhưng từ chối reserved keys, quá nhiều fields hoặc dữ liệu từ public input.

### Bài 11 — Enum mới

AccountState thêm `SUSPENDED`. Một reader cũ chỉ biết ACTIVE/CLOSED. So sánh strict reject, UNKNOWN fallback và default ACTIVE; chọn policy cho authorization.

### Bài 12 — Decimal conversion

Một document lưu tiền `120.50` và currency. Đề xuất Money type trong Java, mapping JSON/BSON và test precision/rounding khi chuyển sang minor units.

### Bài 13 — Timezone

V1 lưu `"createdAt":"2026-11-14 08:00"` không có offset, V2 dùng ISO `Instant`. Có thể convert chính xác không? Liệt kê context cần biết trước migration.

### Bài 14 — SchemaVersion validation

Reader hỗ trợ v1–v3. Phân loại missing marker, explicit null, `"schemaVersion":"3"`, value `0`, `3`, `99`; nêu những trường hợp phải reject.

### Bài 15 — Upcaster

Viết Java upcaster v1 `fullName` → v2 `displayName`, không mutate input, có version guard. Thiết kế tests cho missing fullName, cả hai fields cùng tồn tại và string rỗng.

### Bài 16 — Backfill race

Worker đọc entityVersion 8, user ghi lên 9 trước khi worker migrate. Viết conditional update/pseudocode retry để không mất user change.

### Bài 17 — Unknown nested

V1 DTO biết `address.city`, V2 thêm `address.geocode`. Giải thích vì sao top-level extension map chưa đủ khi nested DTO làm mất unknown child.

### Bài 18 — DynamoDB mapping

Giải thích khác biệt absent attribute, `NULL`, `PutItem` và `UpdateItem`. Thiết kế test khi Java nullable field đi qua Enhanced Client.

### Bài 19 — MongoDB codec

Một service dùng Jackson annotations nhưng lưu qua MongoDB POJO codec. Cần kiểm những gì để field names, ObjectId, Decimal128, Date và unknown fields không đổi ngoài ý định?

### Bài 20 — Cassandra CQL

Phân biệt “không bind/UNSET một column” với “ghi NULL/xóa một column” theo API. Vì sao một nullable DTO không thể tự biểu diễn cả hai ý định?

### Bài 21 — Redis JSON

Một service lưu cả object dưới dạng JSON string trong Redis và dùng GET–deserialize–SET để cập nhật nickname. Nêu lost update/unknown field risks, đề xuất atomic/version-aware operation.

### Bài 22 — Protobuf

Một message bỏ field number 3 rồi phiên bản sau dùng lại number 3 với nghĩa khác. Tại sao nguy hiểm? Đề xuất `reserved` và field presence policy.

### Bài 23 — Avro

Reader V2 thêm field có default để đọc writer V1. Giải thích backward compatibility theo schema resolution và những business defaults không nên tự suy.

### Bài 24 — Event version

Một event có `eventSchemaVersion=2`, `aggregateVersion=87`; database document có `schemaVersion=4`. Phân biệt, thiết kế replay consumer đọc event V1.

### Bài 25 — Rollback

Trong rolling deploy, V2 writer đã ghi schema mới. Phân tích vì sao rollback binary V1 có thể gây lỗi hoặc xóa fields mới. Đề xuất rollout có compatible readers/writers và feature gate.

### Bài 26 — Bảo mật

Một API cho phép unknown field `role=ADMIN` đi vào extension map rồi lưu nguyên xuống database. Chỉ ra mass-assignment attack và giải pháp input allowlist/ownership.

### Bài 27 — Test fixtures

Lập bộ raw JSON/BSON fixtures cho missing, null, unknown, invalid type, future schema, decimal precision, enum mới và nested unknown. Vì sao chỉ serialize object Java hiện tại rồi deserialize lại là không đủ?

### Bài 28 — Migration nhiều tenant

Tenant A có 5 triệu documents v1, tenant B đã ở v3. Lập kế hoạch backfill theo bucket, rate limiting, progress checkpoint, CAS conflicts, rollback và metrics.

### Bài 29 — Schema contract review

Viết một `schema-policy.yml` cho Profile nêu version markers, null/missing semantics, unknown policies theo input/storage/event, writer behavior, migration horizon và test evidence.

### Bài 30 — Tổng hợp tình huống

Một service Java V1 đọc document V3 có field `fraudHold=true`, map enum lạ thành ACTIVE, rồi replace toàn document khi đổi displayName. Xác định đồng thời các rủi ro: future-schema ignorance, security default, unknown field loss, concurrency và rollback. Thiết kế đường đọc/ghi an toàn hơn.

---

**Kết luận:** Serialization trong Java không chỉ là chuyển object thành JSON/BSON; nó là một **hợp đồng dữ liệu sống qua nhiều phiên bản code, nhiều replica và nhiều lần triển khai**. Cần phân biệt **field thiếu**, **field có null**, **field có giá trị** và **field reader chưa nhận biết**; không để mapper/coercion mặc định quyết định thay nghiệp vụ. `schemaVersion` phục vụ tiến hóa cấu trúc, còn `entityVersion`/ETag phục vụ concurrent writes, event sequence có mục đích khác. Để nâng cấp an toàn, hãy thiết kế **backward/forward compatibility**, version-aware readers/upcasters, strict public input, tolerant-but-controlled persistence reads, targeted conditional updates và migration có checkpoint. **Đọc được document mới không chứng minh old writer có thể ghi nó lại mà không mất dữ liệu**. Bộ fixtures lịch sử, tests trên adapter thực, monitoring schema versions và kế hoạch rollback là những công cụ cần thiết để tránh corruption âm thầm khi NoSQL và Java phát triển cùng nhau.
