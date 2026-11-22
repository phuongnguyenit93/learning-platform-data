# Kiểm tra kiểu, trường và toán tử được phép từ đầu vào

Một API Java cung cấp chức năng tìm kiếm đơn đặt chỗ trong MongoDB. Người dùng được phép yêu cầu những đơn có trạng thái CONFIRMED:

~~~~json
{"status":"CONFIRMED"}
~~~~

Nhưng client cũng có thể gửi:

~~~~json
{"status":{"$ne":"CANCELLED"}}
~~~~

Nếu backend chuyển nguyên JSON body thành bộ lọc MongoDB, status có thể bị hiểu thành một **toán tử truy vấn**, thay vì một giá trị trạng thái. Hệ thống có thể trả nhiều bản ghi hơn ý định ban đầu, dù database chỉ đang thực hiện đúng câu truy vấn được đưa đến.

Vấn đề tương tự xảy ra khi client được chọn tên field sort, projection, update operator hoặc aggregation stage. Một request vẫn có thể đúng cú pháp JSON, thậm chí được tạo bằng builder chính thức của driver, nhưng lại đọc thông tin nhạy cảm, sửa trường không được cấp phép hoặc tạo query quá tốn tài nguyên.

Bài thuộc **Database No SQL → Bảo mật dữ liệu**, giải thích cách **kiểm tra kiểu, trường và toán tử được phép từ đầu vào** trong ứng dụng Java dùng NoSQL. Trọng tâm gồm strict JSON parsing, DTO có kiểu, allowlist field/operator, domain-specific query AST, tenant authorization, query-cost limits, input validation cho reads/writes, và các ví dụ MongoDB, DynamoDB, Cassandra, Redis, OpenSearch. Cuối bài có bộ test, runbook và bài tập.

> **Nguyên tắc:** Dữ liệu từ client chỉ được coi là **giá trị đầu vào**, không được tùy ý trở thành **cấu trúc ngôn ngữ truy vấn**. Server phải quyết định field, operator, đường dẫn, projection, sort và mutation nào được phép. Parameter binding có thể bảo vệ literal values; nó **không tự kiểm tra tên field và toán tử có phù hợp quyền của người gọi hay không**.

> **Phạm vi:** Ví dụ sử dụng Java 21, Jackson và các NoSQL drivers. Những con số như max limit 100 hay max range 90 ngày chỉ minh họa policy. Kiểm tra phiên bản driver/framework và security contract thực tế trước khi triển khai.

## 1. NoSQL injection không giống hệt SQL injection

Các rủi ro thường gặp:

| Kiểu rủi ro | Đầu vào điều khiển gì? | Tác động |
| --- | --- | --- |
| Query selector injection | Object/query operator thay vì literal | Trả kết quả rộng hơn |
| Operator injection | NE, OR, range, regex, expression | Thay đổi ngữ nghĩa query |
| Field/path injection | Tên trường và nested path | Truy cập dữ liệu nhạy cảm |
| Mass assignment | Field update ngoài DTO | Sửa tenant, role, status |
| Aggregation injection | Group, lookup, script, output stage | Lộ dữ liệu, CPU/IO cao |
| Search DSL abuse | Wildcard, query_string, regex, script | Query đắt, bypass policy |
| Sort/projection abuse | Field sort hoặc field trả về | Suy ra hoặc lộ trường nội bộ |
| Query complexity abuse | IN/OR quá lớn, deep nesting | Exhaustion/DoS |
| Tenant bypass | Scope do client chọn | Đọc hoặc sửa tenant khác |
| Dynamic command abuse | Redis command, table/collection, CQL identifier | Vượt ranh giới API |

Ba khía cạnh phải xử lý riêng:

1. **Cú pháp/grammar:** input nào là biểu thức hợp lệ của API?
2. **Authorization:** ai được chạy biểu thức đó trên tài nguyên nào?
3. **Chi phí:** biểu thức ấy có bị giới hạn tải, độ sâu và thời gian không?

Một query an toàn về injection vẫn có thể thiếu quyền hoặc quá đắt.

### 1.1. Database thực thi đúng không chứng minh API an toàn

Nếu API cho người dùng gửi raw filter document, database có thể thực hiện filter đó đúng theo spec. Lỗi nằm ở chỗ API **trao quyền quyết định truy vấn lớn hơn hợp đồng sản phẩm**.

### 1.2. Không coi ứng dụng nội bộ là nguồn tin tuyệt đối

HTTP, queue, webhook, batch import, GraphQL variables và dữ liệu từ service khác đều có thể mang input không đúng schema hoặc bị thao túng. Mỗi boundary cần kiểm tra contract của chính mình.

## 2. Các lớp phòng vệ

~~~~mermaid
flowchart TD
    C["Untrusted input"] --> L["Body size, content type, depth"]
    L --> P["Strict JSON parser"]
    P --> T["Typed DTO / schema"]
    T --> V["Field, operator, value validation"]
    V --> A["Trusted principal + tenant authorization"]
    A --> Q["Allowlisted query compiler"]
    Q --> B["Query budget, timeout, rate limits"]
    B --> D[("NoSQL")]
    D --> R["Approved response projection"]
~~~~

- **Transport/parser:** dữ liệu đúng encoding, không vượt kích thước hoặc depth, không có duplicate fields trái policy.
- **DTO/domain:** đúng kiểu, enum, số, thời gian và quan hệ giữa fields.
- **Policy:** trường/toán tử/đường dẫn được phép.
- **Authorization:** người dùng có quyền trên resource và field hay không.
- **Compiler:** tạo cú pháp database từ các nhánh đã duyệt.
- **Resource protection:** giới hạn scan, batch, timeout, pagination, concurrency.
- **Storage:** schema constraints, ACL, least privilege.
- **Response:** không lộ dữ liệu ngoài phép.

Không một bước nào thay được toàn bộ các bước khác.

## 3. Định nghĩa ngôn ngữ truy vấn nhỏ theo nghiệp vụ

Một API booking search có thể công bố:

~~~~json
{
  "status":"CONFIRMED",
  "createdFrom":"2026-11-01T00:00:00Z",
  "createdBefore":"2026-12-01T00:00:00Z",
  "sortBy":"CREATED_AT",
  "sortDirection":"DESC",
  "limit":50
}
~~~~

Hợp đồng:
- status là enum hoặc optional theo endpoint.
- createdFrom/createdBefore là Instant.
- sortBy có hai lựa chọn được định nghĩa.
- sortDirection ASC hoặc DESC.
- limit integer từ 1 đến 100.
- Không có filter raw.
- Không có tenantId từ client.
- Không có tên field/tên operator database do client đặt.

### 3.1. Bảng chính sách

| Field | Kiểu | Toán tử | Giới hạn | Quyền |
| --- | --- | --- | --- | --- |
| status | Enum | EQ hoặc IN có giới hạn | PENDING/CONFIRMED/CANCELLED | User được xem bookings |
| createdAt | Instant | GTE, LT | Range tối đa 90 ngày | User được xem bookings |
| bookingId | String ID | EQ | Canonical ID | Resource authorization |
| amountMinor | Long | GTE/LTE | Numeric bounded | FINANCE |
| sortBy | Enum | Static sort mapping | CREATED_AT, BOOKING_ID | User được xem |
| limit | Integer | Page size | 1–100 | User được xem |
| tenantId | Không nhận từ body | EQ do server thêm | Authenticated context | Server only |
| internalRiskScore | Không công khai | Không | — | Nội bộ |
| passwordHash | Không công khai | Không | — | Nội bộ |
| role | Không thuộc search DTO | Không | — | Nội bộ |

### 3.2. Field tồn tại không đồng nghĩa field được phép

Một trường có thể được:
- Hiển thị.
- Filter.
- Sort.
- Group/aggregate.
- Update.
- Export.

Đó là các **quyền khác nhau**. Một user được xem amountMinor không mặc định được sort/range-filter theo một trường tài chính khác.

### 3.3. Allowlist ưu tiên blocklist

Blocklist chặn một vài ký tự/toán tử dễ bỏ sót:
- Biến thể operator.
- Nested paths.
- Field hợp lệ nhưng nhạy cảm.
- Encoding khác.
- Chức năng query mới trong phiên bản engine.

Allowlist chỉ biên dịch các **cấu trúc đã được review**, nên unknown input mặc định bị reject.

## 4. Anti-pattern: Map thành MongoDB filter

~~~~java
@PostMapping("/bookings/search")
public List<Document> search(@RequestBody Map<String, Object> body) {
    return collection.find(new Document(body))
            .into(new ArrayList<>());
}
~~~~

Đây là một thiết kế thiếu boundary:
- Client được chọn field.
- Có thể chọn operator-like objects.
- Query không tự có tenant scope.
- Không có typed domain validation.
- Có thể tạo query rất đắt.
- Không có field-level authorization.

### 4.1. Một lỗi khác: ghi đè tenant

~~~~java
Document filter = new Document("tenantId", authenticatedTenant);
filter.putAll(untrustedBody);
~~~~

Nếu body có tenantId, nó có thể ghi đè điều kiện từ principal.

### 4.2. Chỉ thêm AND tenant chưa đủ

~~~~java
Bson filter = Filters.and(
        Filters.eq("tenantId", authenticatedTenant),
        arbitraryClientFilter
);
~~~~

Dù cấu trúc này giúp bảo vệ một số trường hợp tenant overwrite, arbitraryClientFilter vẫn có thể dùng forbidden fields, regex/scripts, query cost rất lớn hoặc semantics ngoài API. **Tenant scope không thay field/operator allowlist.**

### 4.3. Escape string không thay type check

Nếu status phải là enum string, một object JSON không thể được coi là status literal chỉ bằng cách escape ký tự. Phải reject wrong type trước query compilation.

## 5. Kiểm tra JSON type thực sự

Nếu status có kiểu **enum string**, thì:

~~~~json
{"status":"CONFIRMED"}
~~~~

là hợp lệ, còn:

~~~~json
{"status":{"$ne":"CANCELLED"}}
~~~~

~~~~json
{"status":["CONFIRMED","PENDING"]}
~~~~

~~~~json
{"status":true}
~~~~

~~~~json
{"status":1}
~~~~

~~~~json
{"status":null}
~~~~

phải được xử lý theo hợp đồng type/nullable cụ thể, không tự hiểu như các truy vấn khác.

### 5.1. JSON type khác BSON type

JSON có string, number, boolean, object, array, null. BSON và Java phân biệt thêm:
- Int32/Int64/Decimal128/Double.
- Date/Instant.
- ObjectId/UUID.
- Binary.
- BigDecimal/long/enum.

Không đưa Map<String,Object> raw qua nhiều lớp rồi hy vọng mọi hệ giữ đúng semantics.

### 5.2. String số khác number

~~~~json
{"limit":50}
~~~~

và:

~~~~json
{"limit":"50"}
~~~~

khác kiểu. Nếu contract strict, phải tắt những coercion không mong muốn.

### 5.3. Null, missing và default

- Missing limit có thể default=50.
- Null limit có thể reject.
- limit=0 reject.
- limit=50 hợp lệ.

Java primitive int có thể nhận giá trị mặc định 0 khi thiếu field; Integer giúp phân biệt null/missing ở một số workflows, nhưng cần validator riêng nếu phải phân biệt **null đã gửi** với **field không có**.

### 5.4. Enum unknown

Nếu status="SUPERUSER" không hợp lệ, không map thành null rồi bỏ filter. Bỏ điều kiện status có thể làm query trả quá nhiều dữ liệu.

## 6. Parser phải có giới hạn

Kiểm tra:
- Content-Type được hỗ trợ.
- Max body bytes tại ingress/server.
- Max JSON nesting depth.
- Max string/number lengths.
- Max array/object members theo schema.
- Duplicate key policy.
- Unknown property policy.
- Scalar coercion.
- UTF-8/Unicode.
- Rate limit.

### 6.1. Duplicate JSON keys

~~~~json
{
  "status":"CONFIRMED",
  "status":{"$ne":"CANCELLED"}
}
~~~~

Parser/gateway khác nhau có thể lấy field đầu hoặc field cuối, hoặc reject. Điều này tạo **validation/parser differential**. Cách bảo vệ đơn giản là reject duplicate keys ở boundary tin cậy.

### 6.2. Unknown properties

~~~~json
{"status":"CONFIRMED","role":"ADMIN"}
~~~~

Nếu role không thuộc DTO, reject thay vì âm thầm bỏ qua ở các API nhạy cảm. Unknown fields có thể là dấu hiệu client sai version, overposting hoặc probing.

### 6.3. Deep objects và huge arrays

Body size limit không thay được max depth, max nodes và array cardinality. Một JSON cú pháp hợp lệ vẫn có thể làm parser/query compiler tiêu CPU/memory quá mức.

## 7. Java 21 DTO: types cố định

~~~~java
import java.time.Instant;

public enum BookingStatus {
    PENDING, CONFIRMED, CANCELLED
}

public enum SortField {
    CREATED_AT, BOOKING_ID
}

public enum SortDirection {
    ASC, DESC
}

public record BookingSearchRequest(
        BookingStatus status,
        Instant createdFrom,
        Instant createdBefore,
        SortField sortBy,
        SortDirection sortDirection,
        Integer limit
) {}
~~~~

DTO không có:
- tenantId từ user.
- raw MongoDB filter.
- arbitrary field/operator.
- pipeline.
- index/table names.
- role/internalRiskScore.

Nhưng một typed DTO vẫn cần validate giá trị và quyền.

### 7.1. Domain validator

~~~~java
import java.time.Duration;
import java.time.Instant;

public final class BookingSearchValidator {
    public record Validated(
            BookingStatus status,
            Instant from,
            Instant before,
            SortField sort,
            SortDirection direction,
            int limit
    ) {}

    public static Validated check(BookingSearchRequest input) {
        if (input == null) {
            throw new IllegalArgumentException("body required");
        }

        int limit = input.limit() == null ? 50 : input.limit();
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit out of range");
        }

        Instant from = input.createdFrom();
        Instant before = input.createdBefore();

        if (from != null && before != null) {
            if (!from.isBefore(before)) {
                throw new IllegalArgumentException("range order");
            }
            if (Duration.between(from, before)
                    .compareTo(Duration.ofDays(90)) > 0) {
                throw new IllegalArgumentException("range too wide");
            }
        }

        return new Validated(
                input.status(),
                from,
                before,
                input.sortBy() == null
                        ? SortField.CREATED_AT : input.sortBy(),
                input.sortDirection() == null
                        ? SortDirection.DESC : input.sortDirection(),
                limit
        );
    }
}
~~~~

Nếu endpoint yêu cầu status bắt buộc, reject null. Các mức max là policy minh họa.

### 7.2. Bean Validation

Trong Spring có thể bổ sung:
- @NotNull.
- @Min/@Max.
- @Size.
- @Valid.
- Custom validator cho from < before.

Annotation không thay strict parser, authz, query allowlist và cost controls.

## 8. Jackson strict parsing

Ví dụ cấu hình với Jackson 2.15+:

~~~~java
import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadConstraints;
import com.fasterxml.jackson.core.StreamReadFeature;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

public final class StrictJson {
    public static ObjectMapper create() {
        JsonFactory factory = JsonFactory.builder()
                .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
                .streamReadConstraints(
                        StreamReadConstraints.builder()
                                .maxNestingDepth(16)
                                .maxStringLength(4096)
                                .maxNumberLength(64)
                                .build())
                .build();

        return JsonMapper.builder(factory)
                .addModule(new JavaTimeModule())
                .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
                .disable(MapperFeature.ALLOW_COERCION_OF_SCALARS)
                .build();
    }
}
~~~~

### 8.1. Những lưu ý khi dùng thật

- Kiểm tra Jackson version và methods.
- Đảm bảo framework dùng đúng mapper/decoder.
- Custom deserializer có thể làm coercion khác.
- Null/missing cần validate riêng.
- Max body bytes nằm ở ingress/HTTP server.
- Đừng bật polymorphic default typing tùy tiện trên dữ liệu untrusted.
- Nếu có clients legacy, migration theo version hoặc endpoint phù hợp.

### 8.2. Unknown enum không được biến thành null

Nếu tính năng cho unknown enum thành null/default được bật mà service bỏ null filter, user có thể nhận tập kết quả rộng hơn. Không để biến lỗi parse thành broad query.

## 9. Biên dịch DTO thành query cố định

~~~~java
import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Sorts.*;

import java.util.ArrayList;
import java.util.Date;
import java.util.List;

import com.mongodb.client.FindIterable;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import org.bson.conversions.Bson;

public final class BookingMongoQuery {
    public static FindIterable<Document> search(
            MongoCollection<Document> collection,
            String authenticatedTenant,
            BookingSearchValidator.Validated input
    ) {
        if (authenticatedTenant == null ||
                authenticatedTenant.isBlank()) {
            throw new SecurityException("missing tenant");
        }

        List<Bson> filters = new ArrayList<>();
        filters.add(eq("tenantId", authenticatedTenant));

        if (input.status() != null) {
            filters.add(eq("status", input.status().name()));
        }
        if (input.from() != null) {
            filters.add(gte("createdAt", Date.from(input.from())));
        }
        if (input.before() != null) {
            filters.add(lt("createdAt", Date.from(input.before())));
        }

        Bson sort = switch (input.sort()) {
            case CREATED_AT -> input.direction() ==
                    SortDirection.ASC
                    ? orderBy(ascending("createdAt"),
                              ascending("bookingId"))
                    : orderBy(descending("createdAt"),
                              descending("bookingId"));
            case BOOKING_ID -> input.direction() ==
                    SortDirection.ASC
                    ? ascending("bookingId")
                    : descending("bookingId");
        };

        return collection.find(and(filters))
                .sort(sort)
                .limit(input.limit());
    }
}
~~~~

Ở đây:
- Tenant từ auth context.
- Field names cố định.
- Operator từ code.
- Status literal enum.
- Date chuyển thành Date/BSON kiểu rõ.
- Sort chỉ hai lựa chọn.
- Limit bounded.

### 9.1. Vẫn cần gì?

- Resource-level authorization.
- Response DTO không trả fields nội bộ.
- Query timeout/quotas.
- Index phù hợp.
- Cursor/page policy.
- Read consistency theo contract.
- Error/trace redaction.
- Schema constraints.

### 9.2. Builder chưa bảo vệ dynamic field

~~~~java
Filters.eq(untrustedFieldName, validatedValue)
~~~~

vẫn có thể vi phạm field authorization. Builder giúp tạo BSON hợp lệ, không biết user được phép filter field nào.

## 10. Tên field, nested paths và normalization

Tùy DSL, các ký tự/path có semantics đặc biệt:
- Dấu chấm cho nested path.
- Dollar-prefixed keys cho MongoDB operators.
- Reserved identifiers.
- Wildcards/scripts trong search.
- Unicode và encoding khác biệt.

Một field hợp lệ trong database vẫn có thể là internal-only.

### 10.1. Map alias sang constant

~~~~java
public static String toDbSortField(SortField sort) {
    return switch (sort) {
        case CREATED_AT -> "createdAt";
        case BOOKING_ID -> "bookingId";
    };
}
~~~~

Không dùng direct request:

~~~~text
sortBy = "security.internalRiskScore"
~~~~

hoặc tạo database path bằng cách ghép raw metadata key của client.

### 10.2. Custom fields phải có schema registry

Nếu tenant tạo custom fields:
- Alias được đăng ký và kiểm tra collisions.
- Server map alias sang internal path.
- Kiểu và operators được xác định.
- Role/tenant được kiểm tra.
- Cost/size được giới hạn.
- Schema versioning.
- Canonicalization thống nhất.

### 10.3. Không tự lowercase mọi identifier

Identifier có thể case-sensitive hoặc định danh dựa trên bytes. Normalization phải theo hợp đồng, áp dụng nhất quán ở validation, authorization và query.

## 11. Per-field/operator allowlist

| Field | EQ | IN | GTE/LT | REGEX | SORT |
| --- | :---: | :---: | :---: | :---: | :---: |
| status | Có | Có, max 3 | Không | Không | Không |
| createdAt | Có thể | Không | Có | Không | Có |
| amountMinor | Theo role | Không | Theo role | Không | Theo role |
| bookingId | Có | Không | Không | Không | Có |
| tenantId | Server-only | Không | Không | Không | Không |
| customerName | Theo API | Không | Không | Không mặc định | Không |
| internalRiskScore | Không | Không | Không | Không | Không |

### 11.1. Không dùng tên toán tử raw

~~~~json
{
  "field":"status",
  "operator":"NOT_EQUALS",
  "value":"CANCELLED"
}
~~~~

Nếu status chỉ hỗ trợ EQ, reject. Không đổi tên operator rồi đưa vào driver bằng string lookup tự động.

### 11.2. Nếu cho flexible filters

Sử dụng tên operator ở mức business:
- EQUALS.
- AFTER_OR_EQUAL.
- BEFORE.
- ONE_OF.

Sau đó:
1. Parse field enum.
2. Parse operator enum.
3. Check tuple được cho phép.
4. Parse value theo field.
5. Apply role/tenant.
6. Bound list/range/depth.
7. Compile thành driver operation tĩnh.

### 11.3. Avoid broad expression fallbacks

Không có nhánh “unknown operator → parse raw JSON” vì nhánh đó làm allowlist vô nghĩa.

## 12. Domain AST là cách mở rộng an toàn

~~~~java
import java.time.Instant;

public sealed interface BookingCriterion
        permits StatusEquals, CreatedAfter, CreatedBefore {}

public record StatusEquals(BookingStatus value)
        implements BookingCriterion {}

public record CreatedAfter(Instant value)
        implements BookingCriterion {}

public record CreatedBefore(Instant value)
        implements BookingCriterion {}
~~~~

Compiler:

~~~~java
import static com.mongodb.client.model.Filters.*;
import java.util.Date;
import org.bson.conversions.Bson;

public final class BookingCriterionCompiler {
    public static Bson compile(BookingCriterion criterion) {
        return switch (criterion) {
            case StatusEquals s ->
                    eq("status", s.value().name());
            case CreatedAfter d ->
                    gte("createdAt", Date.from(d.value()));
            case CreatedBefore d ->
                    lt("createdAt", Date.from(d.value()));
        };
    }
}
~~~~

### 12.1. Ưu điểm

Không có variant:
- ArbitraryMongoOperator.
- RawAggregation.
- ScriptExpression.
- DynamicCollection.

Muốn hỗ trợ loại filter mới phải review domain policy, authorization, cost/index và viết test.

### 12.2. Cây lồng vẫn phải bounded

Nếu AST hỗ trợ AND/OR, giới hạn:
- Max tree depth.
- Max nodes.
- Max OR branches.
- Max IN list.
- Max time range.
- Max query cost.

Một cây hợp lệ nhưng quá lớn vẫn có thể làm server quá tải.

## 13. Toán tử cần đặc biệt thận trọng

Các nhóm có thể rủi ro tùy engine:
- NE/NIN/EXISTS mở rộng tập kết quả.
- OR/NOR/NOT làm thay đổi scope logic.
- Regex/wildcard có thể quét lớn hoặc có ReDoS.
- Script/expression/function chạy logic ngoài domain.
- Aggregation lookup/union/group fan-out.
- Output/write stages trong pipeline.
- Geo/vector searches với bán kính/candidate count lớn.
- Graph traversal không giới hạn.

### 13.1. Regex không phải lựa chọn mặc định cho text search

Nếu chỉ cần tìm chuỗi:
- Dùng full-text/search index phù hợp.
- Treat user query as literal text.
- Limit length.
- Không chấp nhận raw regex.
- Giới hạn query execution time và index scan cost.

Escaping metacharacters không đảm bảo query sẽ chạy nhanh.

### 13.2. IN và range

Ngay cả khi status IN được cho phép, max list size vẫn cần thiết. Một array gồm 100.000 IDs có thể làm query cost/size vượt dự kiến.

## 14. Ghép tenant filter đúng nhóm logic

Muốn:

~~~~text
tenant = T42 AND (status = PENDING OR status = CONFIRMED)
~~~~

Không được tạo:

~~~~text
(tenant = T42 AND status = PENDING) OR status = CONFIRMED
~~~~

vì nhánh thứ hai có thể đọc dữ liệu tenant khác.

~~~~java
Bson scoped = Filters.and(
        Filters.eq("tenantId", authenticatedTenant),
        Filters.or(
                Filters.eq("status", "PENDING"),
                Filters.eq("status", "CONFIRMED")
        )
);
~~~~

Server phải kiểm soát grouping. Không nhận raw OR expression của user rồi ghép thiếu chặt chẽ.

### 14.1. Tenant từ đâu?

Trusted principal/token/session đã xác thực, không phải body. Nếu admin có quyền chọn tenant khác, cần explicit authorization, audit và API contract riêng.

### 14.2. Authorization theo tài nguyên

Tenant scope có thể chưa đủ:
- Project ownership.
- Booking owner.
- Field visibility.
- Deleted records.
- Financial role.
- Organization hierarchy.

Kiểm tra quyền theo operation và record khi cần.

## 15. Update validation và mass assignment

Một endpoint đổi tên booking có thể nhận:

~~~~json
{"displayName":"Kỳ nghỉ","expectedVersion":17}
~~~~

Không cho một body có thêm tenantId, role, status hoặc other internal fields được chuyển thẳng sang entity.

### 15.1. DTO riêng

~~~~java
public record RenameBookingRequest(
        String displayName,
        Long expectedVersion
) {}
~~~~

### 15.2. Cố định update operator

~~~~java
import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

public final class RenameBooking {
    public static boolean execute(
            MongoCollection<Document> collection,
            String authenticatedTenant,
            String bookingId,
            RenameBookingRequest request
    ) {
        if (request == null || request.expectedVersion() == null
                || request.expectedVersion() < 0) {
            throw new IllegalArgumentException("expectedVersion");
        }

        String name = request.displayName();
        if (name == null || name.isBlank()
                || name.codePointCount(0, name.length()) > 120) {
            throw new IllegalArgumentException("displayName");
        }

        // Also enforce record-level authorization.
        UpdateResult result = collection.updateOne(
                and(
                        eq("tenantId", authenticatedTenant),
                        eq("bookingId", bookingId),
                        eq("version", request.expectedVersion())
                ),
                combine(
                        set("displayName", name),
                        inc("version", 1L)
                )
        );

        return result.getMatchedCount() == 1L;
    }
}
~~~~

### 15.3. Các ranh giới còn lại

- Route bookingId phải canonical.
- Resource authorization cần làm rõ.
- MatchedCount=0 có thể là not found hoặc conflict.
- Retry after timeout có thể có UNKNOWN commit outcome.
- OperationId/idempotency hữu ích với mutations có side effects.
- Audit/versioned event theo chính sách.

### 15.4. Raw update document bị cấm

Không chấp nhận update operators từ body chỉ để dễ triển khai generic PATCH. Được phép đổi displayName không có nghĩa được quyền thay tenantId, accountStatus hoặc push vào auditEvents.

## 16. Business state machine nghiêm hơn type validation

Một status enum là giá trị đúng kiểu nhưng chưa chắc transition hợp lệ:
- PENDING → CONFIRMED có thể yêu cầu reserve tồn kho.
- CONFIRMED → CANCELLED có điều kiện.
- CANCELLED → CONFIRMED có thể bị cấm.
- Một booking slot không được double-confirm.

Cần:
- Current authoritative state.
- Expected version.
- Actor permissions.
- Conditional update/transaction.
- Idempotency.
- Audit.

Một API generic set status chỉ kiểm tra enum sẽ không bảo vệ invariant nghiệp vụ.

## 17. Sort, projection và pagination là attack surfaces

### 17.1. Sort

Sort theo internalRiskScore có thể tiết lộ thông tin qua thứ tự ngay cả khi field bị ẩn khỏi response. Chỉ map enum sort công khai sang paths đã duyệt.

### 17.2. Projection

~~~~json
{"fields":["bookingId","status","passwordHash"]}
~~~~

Không nên được phục vụ bởi API public. Dùng response DTO theo endpoint/role thay vì trả Document đầy đủ.

### 17.3. Pagination

- Limit bounded.
- Offset/deep pagination bị giới hạn.
- Cursor có tenant/query scope.
- Stable tie-breaker.
- Không cho client chọn arbitrary sort key.
- Query deadline.
- Export API riêng nếu cần xuất nhiều dữ liệu.

### 17.4. Cursor

Cursor có thể chứa last sort key, query fingerprint và tenant. Nếu do client giữ:
- Bảo vệ integrity (chữ ký/token policy).
- Bind với principal/tenant.
- Có expiry.
- Không tin JSON decoded raw.
- Không dùng cursor của tenant khác.

## 18. Aggregation: template thay vì raw pipeline

Nếu public API nhận arbitrary pipeline:

~~~~json
{
  "pipeline": [
    {"$match":{"status":"CONFIRMED"}},
    {"$group":{"_id":"$tenantId","count":{"$sum":1}}}
  ]
}
~~~~

client có thể điều khiển group keys, joins, expressions, output hoặc data scope. Điều này không phù hợp search/report endpoint thông thường.

### 18.1. Report template

~~~~json
{
  "report":"BOOKING_COUNT_BY_DAY",
  "createdFrom":"2026-11-01T00:00:00Z",
  "createdBefore":"2026-12-01T00:00:00Z"
}
~~~~

Server:
- Chọn pipeline tĩnh.
- Chèn tenant filter đúng vị trí.
- Validate time range.
- Giới hạn group cardinality.
- Rate/cost limit.
- Kiểm tra role được phép xem report.

### 18.2. Admin console

Nếu cần raw querying cho quản trị, phải là một security boundary riêng: elevated role, audit, read-only credentials khi phù hợp, sandbox, approval, timeout và data masking.

## 19. DynamoDB: placeholders không tự cấp quyền

DynamoDB sử dụng expressions và aliases:
- KeyConditionExpression.
- FilterExpression.
- UpdateExpression.
- ExpressionAttributeNames.
- ExpressionAttributeValues.

Ví dụ:

~~~~text
UpdateExpression = "SET #f = :v"
ExpressionAttributeNames = {"#f": userChosenField}
~~~~

Nếu userChosenField là một thuộc tính bí mật, alias không ngăn unauthorized write. **Parameterization/escaping không phải field authorization.**

### 19.1. KeyCondition khác FilterExpression

FilterExpression không thay thiết kế partition key và không tự làm truy vấn rẻ. API phải enforce tenant/partition scope, không cho arbitrary Scan hoặc filter rộng qua public endpoint.

### 19.2. AttributeValue types

S, N, BOOL, NULL, L, M và sets phải được validate đúng kiểu domain. Không để client tự chọn type tag trái contract.

### 19.3. IAM

App role chỉ nên có permissions tối thiểu theo table/action/conditions được hỗ trợ. Một lỗi validation sẽ ít nghiêm trọng hơn nếu DB credentials không có quyền toàn hệ.

## 20. Cassandra CQL: bind values, allowlist identifiers

Prepared statement:

~~~~sql
SELECT booking_id, status
FROM booking_by_tenant
WHERE tenant_id = ?
  AND bucket_day = ?;
~~~~

Bind values ngăn việc ghép literal vào syntax CQL. Nhưng tên table, column và một số identifiers không được bind như value.

Sai:

~~~~java
String cql = "SELECT * FROM " + untrustedTable
        + " WHERE " + untrustedColumn
        + " = '" + untrustedValue + "'";
~~~~

Đúng về nguyên tắc:
- Table/columns map từ constants/enum.
- Values bind qua prepared statements.
- Query shape cố định theo partition key.
- Page size/consistency/timeout bounded.
- Không cho arbitrary ALLOW FILTERING.
- RBAC phù hợp.

Query hợp lệ về cú pháp chưa chắc hợp lý về performance nếu nó đòi scan sai access path.

## 21. Redis: key namespace, command và script

Một Redis endpoint có dạng:

~~~~json
{"command":"ARBITRARY_COMMAND","args":["..."]}
~~~~

trao quyền quá rộng cho người gọi. Thay bằng domain commands như GetCart, SetPreference, InvalidateCatalog.

### 21.1. Key scope

Không ghép:

~~~~text
"tenant:" + tenantFromBody + ":cart:" + cartId
~~~~

mà không xác thực quyền. Tenant nên đến từ trusted context; cartId validated/canonical, key encoding đúng quy tắc.

### 21.2. Lua

Không nhận raw Lua script từ client. Dùng scripts được review và args/keys có validation, hiểu scope atomicity và Redis Cluster limitations.

### 21.3. Redis ACL

Key patterns/command permissions tối thiểu là defense in depth. ACL không thay application authorization.

## 22. OpenSearch/Elasticsearch: raw DSL không phải text search API

Search DSL có bool, regex, wildcard, query-string, script, aggregation, sort và runtime fields. Public API thường không nên nhận toàn bộ raw DSL.

### 22.1. Literal text

User gõ:

~~~~text
căn hộ gần biển
~~~~

đây là **text data**, không phải syntax query_string hoặc regex. Server có thể build static match/multi_match query trên allowed fields với:
- Max string length.
- Tenant filter.
- Result size limit.
- Analyzer/index phù hợp.
- No raw script.
- No arbitrary index alias.

### 22.2. Expensive query controls

Cần giới hạn:
- Regex/wildcard.
- Deep pagination.
- Aggregation buckets.
- Script/runtime fields.
- Nested joins.
- Vector kNN candidate count.
- Timeout/rate.

Một input không chứa ký tự nguy hiểm vẫn có thể tạo full scan.

### 22.3. Search index không phải authority

Một GSI/search index có eventual consistency; query miss không tự chứng minh source không có item. Input validation và read-consistency contract là hai vấn đề khác nhau.

## 23. Graph NoSQL: labels và traversal depth

Với Cypher/Gremlin:
- Bind values.
- Map label/edge types/property names từ allowlist.
- Bound traversal depth và fan-out.
- Giữ tenant/resource authorization.
- Không nhận arbitrary query fragments.

Một truy vấn graph có cú pháp hợp lệ vẫn có thể duyệt data ngoài quyền hoặc bùng nổ CPU.

## 24. Storage schema validation là lớp bổ sung

Database validators/constraints có thể:
- Chặn write sai type/thiếu field.
- Giảm schema drift.
- Bảo vệ nhiều writers.
- Hỗ trợ mandatory field/role policies.

Nhưng không thay:
- Read authorization.
- Filter/operator allowlist.
- Sort/projection permissions.
- Aggregation cost.
- API response redaction.
- Tenant isolation.
- Timeouts và rate limits.

### 24.1. Legacy data

Nếu records schema v1 có amountMinor string còn v3 là Long:
- Có migration strategy.
- Versioned codecs.
- Test read compatibility.
- Ghi tỷ lệ records chưa migrate.
- Không nới public input thành arbitrary Map chỉ vì dữ liệu cũ không đồng nhất.

## 25. Bảo vệ chi phí truy vấn

Một policy minh họa:

~~~~yaml
bookingSearch:
  maxBodyBytes: 16384
  maxJsonDepth: 16
  maxFilterNodes: 12
  maxOrBranches: 3
  maxInValues: 50
  maxTimeRangeDays: 90
  maxPageSize: 100
  maxQueryDurationMs: 1000
  maxConcurrentQueriesPerTenant: 20
  allowRawRegex: false
  allowScripts: false
  allowRawAggregation: false
  allowDynamicFieldNames: false
~~~~

Chọn limits thực dựa trên SLO, indexes, tenant workload và capacity.

### 25.1. Query cost classes

- Partition-key equality: tương đối rẻ.
- Indexed bounded range: vừa.
- Cross-partition scan: đắt.
- Unindexed sort: đắt.
- Regex/script rộng: deny với public API.
- Export: route đặc quyền có quotas riêng.

### 25.2. Admission và resource limits

Thêm:
- Driver/server query timeout.
- Connection pool budgets.
- Per-tenant concurrency.
- Rate limit.
- Circuit breaker.
- Backpressure.
- Slow query metrics.

Một query nhỏ nhưng lặp 100.000 lần/giây vẫn có thể quá tải database.

## 26. Các kiểm tra biên về kiểu

### 26.1. Long overflow

~~~~json
{"amountMinor":9223372036854775808}
~~~~

Vượt signed 64-bit long. Parser phải reject hoặc áp kiểu số rộng theo contract, không wrap/truncate.

### 26.2. Decimal

Với tiền, kiểm tra BigDecimal precision/scale, rounding, nonnegative bounds; không chuyển qua double gây mất chính xác.

### 26.3. Date/time

- ISO timestamp có offset rõ.
- Start < end.
- Max range.
- Calendar timezone policy.
- Không lấy client clock làm source commit version.

### 26.4. UUID/ObjectId/string identifiers

- Đúng định dạng/độ dài.
- Không chấp nhận object thay ID string.
- Canonical hóa khi contract cho phép.
- Không tự bỏ filter nếu ID invalid.

### 26.5. Unicode

Java String.length đếm UTF-16 code units, không phải grapheme clusters. Chọn length policy theo bytes/code points theo ứng dụng. Canonicalization phải nhất quán với authorization/query/cache keys.

## 27. Error response an toàn

~~~~json
{
  "code":"INVALID_FILTER",
  "message":"Trường status phải là trạng thái được hỗ trợ.",
  "requestId":"R-486"
}
~~~~

Không trả raw database command, stack trace, connection string, secret hoặc full payload PII.

| Tình huống | Hướng phản hồi |
| --- | --- |
| Invalid JSON | 400 |
| Wrong type/unknown field/operator | 400/422 |
| Missing authentication | 401 |
| Không đủ quyền | 403 hoặc concealment policy |
| Version conflict | 409 |
| Rate/resource limit | 429 theo contract |
| Database unavailable | 5xx, không chuyển thành input error |

### 27.1. Không xử lý input lỗi bằng cách bỏ filter

Một invalid status mà app tự bỏ qua status condition sẽ làm query rộng hơn. Reject rõ ràng thường an toàn hơn.

### 27.2. Không xem timeout như NOT_FOUND

Một database failure không phải bằng chứng record không tồn tại. Không negative-cache lỗi như NOT_FOUND.

## 28. Observability và incident signals

Metrics:
- wrong_type_reject_total.
- unknown_field_reject_total.
- forbidden_operator_reject_total.
- query_cost_reject_total.
- authz_denied_total.
- normalized_query_shape_counts.
- scanned-to-returned ratio.
- p95/p99.
- request throttles/errors.

Log redacted:

~~~~json
{
  "event":"QUERY_INPUT_REJECTED",
  "requestId":"R-486",
  "endpoint":"booking-search",
  "reason":"WRONG_TYPE",
  "fieldAlias":"status",
  "expectedType":"enum-string",
  "receivedType":"object",
  "rawValueCaptured":false
}
~~~~

Không gắn raw JSON, userId, token hoặc arbitrary field values vào metric labels; sẽ gây high cardinality và data leakage.

### 28.1. Phân biệt bug client và probing

Một đợt invalid filters có thể do client version lỗi hoặc probing. Cần điều tra nguồn, release timeline, tần suất, scopes và hậu quả; không suy ý định chỉ từ một payload.

## 29. Unit test matrix

| Input | Kết quả kỳ vọng |
| --- | --- |
| status CONFIRMED | Hợp lệ |
| status UNKNOWN | Reject |
| status empty string | Reject |
| status object | Reject wrong type |
| status array | Reject nếu scalar contract |
| status boolean | Reject |
| status number | Reject |
| limit 0 | Reject |
| limit 100 | Hợp lệ |
| limit 101 | Reject |
| limit string 50 | Reject nếu strict type |
| Unknown property | Reject |
| Duplicate JSON key | Reject |
| createdFrom ≥ createdBefore | Reject |
| time range vượt limit | Reject |
| raw update operator | Reject |
| raw aggregation pipeline | Reject |
| forbidden sort field | Reject |

### 29.1. Assert query compilation

Với valid request:
- Tenant filter luôn có.
- Field names cố định.
- Operator đúng allowlist.
- Limit/sort bounded.
- Không raw operator/user field.
- Response DTO không có secret.

### 29.2. Cross-tenant integration

Tạo booking A tại T1 và B tại T2 với cùng status. Assert T1 không:
- Read B.
- Update B.
- Sort/count dựa trên B.
- Reuse cursor T2.
- Read fields restricted by role.

### 29.3. Mutation concurrency

Hai writers cùng expectedVersion:
- Chỉ một transition hợp lệ.
- Version conflict được trả đúng.
- Không đổi tenant/role.
- Retry timeout dùng operationId nếu có side effects.

## 30. Property-based testing và fuzzing

Sinh có kiểm soát:
- Scalars, arrays, objects.
- Nested operator-like keys.
- Duplicate fields.
- Unknown paths.
- Unicode unusual inputs.
- Oversized strings.
- Overflow numbers.
- Huge IN/OR.
- Null/missing combinations.
- Invalid dates.
- Wrong enum case.

Properties:
1. Input ngoài grammar không tạo DB query ngoài allowlist.
2. Tenant scope không bị mất.
3. Không dynamic DB field từ client.
4. Query complexity trong budget.
5. Invalid payload reject trước database.
6. Error không chứa secrets/PII.
7. Response không có internal fields.
8. No cross-tenant read/update.

Chạy trong isolated test cluster với synthetic data, rate limits và no real payment/notification side effects.

## 31. Dynamic custom fields

Một SaaS có thể cho tenant tạo custom fields. Vẫn có thể kiểm soát:

~~~~json
{
  "fieldAlias":"customPriority",
  "storagePathId":"tenant-field-17",
  "type":"INTEGER",
  "allowedOperations":["EQ","GTE","LTE"],
  "minValue":0,
  "maxValue":100,
  "allowSort":false,
  "visibility":"TENANT_ADMIN"
}
~~~~

Server:
- Tra registry đúng tenant.
- Kiểm tra role.
- Map fieldAlias sang internal approved storage path.
- Parse value theo type.
- Bound cost.
- Version schema policy.
- Bảo vệ cache query results theo tenant/role/policy version.

Một custom field tồn tại không tự cấp quyền cho mọi users.

## 32. Validation khác authorization

Một input hoàn toàn hợp lệ vẫn có thể gây:
- Broken Object-Level Authorization khi user chọn booking ID tenant khác.
- Broken Function-Level Authorization khi user gọi admin endpoint.
- Field-level leakage qua projection/sort.
- DoS qua query quá đắt.

Các lớp phải tách:
- DTO/type validation.
- Field/operator allowlist.
- Resource/field authorization.
- Query cost and rate limits.
- Output redaction.

Frontend chỉ có hai filter không phải lý do tin API body; attacker/client lỗi có thể tự gửi request.

## 33. Rollout khi siết validation

Một ứng dụng cũ cho string "50" ở limit rồi tự coercion. Khi chuyển sang integer strict:
- Clients cũ có thể nhận 400.
- Cần API contract/version plan.
- Có thể canary strict mode.
- Quan sát reject reasons.
- Thông báo SDK integrators.
- Không giữ một raw-filter bypass mãi chỉ vì compatibility.

Quy trình:
1. Liệt kê query shapes đang dùng bằng metrics có redaction.
2. Thiết kế DTO/allowlist.
3. Xây query compiler.
4. Viết tests.
5. Chạy canary.
6. Migrate clients.
7. Disable legacy raw mode.
8. Audit những paths còn lại.

Nếu có admin query console, tách thành security boundary riêng với auth/audit/quotas.

## 34. Runbook khi nghi NoSQL operator injection

### Bước 1 — Nhận diện

- Có cross-tenant records trong response?
- Có unauthorized updates?
- DB QPS/p99 tăng bất thường?
- Input objects được đưa vào scalar fields?
- Unknown operators/fields nhiều?
- Có sort/internal projection đáng ngờ?

### Bước 2 — Contain

- Rate limit/disable affected endpoint theo incident policy.
- Hạn chế DB role có quyền quá rộng.
- Giữ evidence và audit trail.
- Thu hồi credentials nếu có lộ.
- Không paste raw PII vào ticket.

### Bước 3 — Thu metadata

- App build.
- Driver/Jackson/framework versions.
- Effective parser config.
- Controller/DTO.
- Query compiler.
- Database schema/roles.
- Feature flags.

### Bước 4 — Reproduce

Synthetic:
- Valid request baseline.
- Object thay scalar.
- Duplicate keys.
- Unknown field.
- Forbidden operator/sort.
- Raw update/aggregation.
- Cross-tenant body.
- Huge IN/range.

Xác minh invalid input không tới DB.

### Bước 5 — Fix

- Typed DTO.
- Strict parser.
- Per-field/operator whitelist.
- Trusted identity/tenant.
- Static driver builder.
- Domain mutation.
- Least privilege.
- Query budgets.
- Sanitized errors.

### Bước 6 — Verify

- Unit, integration, fuzz tests.
- Cross-tenant tests.
- Performance/cost tests.
- Client compatibility.
- Audit impacted data.
- Monitor rejects/source load sau deploy.

## 35. Những hiểu nhầm thường gặp

1. **“NoSQL không có injection.”** Có selector, operator và DSL injection.
2. **“JSON là data nên không ảnh hưởng query.”** JSON object có thể thành biểu thức.
3. **“Escape string là đủ.”** Không ngăn object/operator injection.
4. **“Driver builder tự whitelist fields.”** Không.
5. **“Parameter binding bảo vệ dynamic identifier.”** Không.
6. **“Chặn dollar là đủ.”** Không ngăn forbidden fields/cost.
7. **“Blacklisting một operator đủ.”** Có operators và paths khác.
8. **“Unknown field cứ bỏ qua.”** Có thể che client bug/mass assignment.
9. **“Unknown enum thành null an toàn.”** Có thể bỏ filter.
10. **“String số và number giống nhau.”** Strict contract phân biệt.
11. **“Boolean và 1 giống nhau.”** Không.
12. **“Null và missing luôn giống.”** Không.
13. **“Duplicate JSON keys vô hại.”** Parser divergence.
14. **“Body bytes limit thay depth limit.”** Không.
15. **“Typed DTO không cần domain validation.”** Vẫn cần bounds/state.
16. **“TenantId client gửi là tin cậy.”** Không.
17. **“putAll sau tenant predicate an toàn.”** Có thể ghi đè.
18. **“AND tenant cho phép mọi operator còn lại.”** Không.
19. **“Field tồn tại nghĩa được filter/sort.”** Không.
20. **“Field đọc được nghĩa được update.”** Không.
21. **“Entity là PATCH DTO.”** Mass assignment.
22. **“Raw update operators hợp lệ cho mọi endpoint.”** Không.
23. **“Status enum hợp lệ nghĩa transition hợp lệ.”** Không.
24. **“DB schema validator bảo vệ reads.”** Không đủ.
25. **“Ẩn field ở response là bảo vệ sort/filter.”** Có thể suy thông tin.
26. **“Sort risk score không lộ giá trị.”** Thứ tự có thể leak.
27. **“Limit lớn vẫn an toàn vì là int.”** Cost cần cap.
28. **“IN có thể vô hạn.”** Resource exhaustion.
29. **“Regex được escape luôn nhanh.”** Có thể full scan.
30. **“Raw search DSL cần thiết cho advanced search.”** Có thể typed AST.
31. **“DynamoDB placeholders là authorization.”** Không.
32. **“CQL có thể bind mọi table/column name.”** Không.
33. **“Redis key prefix từ body là tenant boundary.”** Không.
34. **“Redis ACL không cần khi app validate.”** Defense in depth.
35. **“Graph traversal không cần depth limit.”** Fan-out risk.
36. **“Custom fields không thể có allowlist.”** Có thể schema registry.
37. **“Frontend form đủ chặn query abuse.”** Backend cần validate.
38. **“Invalid input nên trả empty list.”** Che violations.
39. **“Log full invalid payload giúp điều tra.”** PII/secret risks.
40. **“Raw input làm metric label là tốt.”** High cardinality.
41. **“Một happy-path test đủ chứng minh.”** Cần negative/integration tests.
42. **“Không cần duplicate-key tests.”** Có parser differential.
43. **“Bỏ validation tăng hiệu năng.”** Mở security/cost risks.
44. **“App DB role full access vô hại.”** Blast radius cao.
45. **“Query đúng kiểu không thể DoS.”** Có thể rất đắt.
46. **“Timeout nghĩa NOT_FOUND.”** Không.
47. **“Retry mutation không cần operationId.”** Có duplicate effects.
48. **“Validation tương đương authorization.”** Khác mục tiêu.
49. **“Dùng production dump để fuzz bình thường.”** Privacy/safety.
50. **“Xong fix không cần theo dõi rejects.”** Cần post-deploy monitoring.

## 36. Bài tập: thiết kế API search/update NoSQL an toàn

Hệ thống SaaS có:
- Java 21, Spring Boot.
- MongoDB cho Bookings.
- DynamoDB cho read model.
- Redis cache.
- OpenSearch cho search.
- Roles USER, SUPPORT, FINANCE, ADMIN.
- Fields bookingId, tenantId, status, createdAt, amountMinor, displayName, customerNotes, internalRiskScore.
- Endpoint search theo status/time/sort/page.
- Endpoint rename với expectedVersion.
- Custom fields theo tenant.

### A. Object/operator injection

So sánh:

~~~~json
{"status":"CONFIRMED"}
~~~~

và:

~~~~json
{"status":{"$ne":"CANCELLED"}}
~~~~

Trả lời:
1. Khác nhau về JSON type như thế nào?
2. Vì sao pass Map tới Document nguy hiểm?
3. DTO enum xử lý payload thứ hai ra sao?
4. Vì sao escape một ký tự không giải quyết tận gốc?
5. Test nào chứng minh reject trước DB?

### B. Strict parser

Thiết kế:
- status enum.
- createdFrom/before Instant.
- sortBy/direction enum.
- limit integer 1–100.

Chỉ rõ unknown fields, duplicate keys, null/missing, wrong types và max body/depth.

### C. Tenant authorization

T1/T2 cùng có bookings CONFIRMED:
1. Tenant lấy từ đâu?
2. Viết đúng tenant AND status filter.
3. Mô tả sai grouping OR.
4. Làm sao bảo vệ count/sort?
5. Role nào được xem amountMinor?

### D. Field/operator matrix

Cho status EQ/IN, createdAt range, amountMinor range chỉ FINANCE, bookingId EQ, internalRiskScore deny. Thiết kế max IN=20, max range=90 ngày, allowed sort fields và 4xx reject errors.

### E. Java compiler

Viết DTO, validator, enum mapping, MongoDB Filters, stable sort, bounded limit và response DTO; thêm unit/integration tests cho query structure.

### F. Update/mass assignment

Endpoint rename có displayName và expectedVersion:
1. Vì sao không deserialize vào entity?
2. Vì sao không nhận raw update document?
3. Dùng conditional version thế nào?
4. Khi version conflict trả gì?
5. Khi write timeout sau commit, idempotency giúp gì?

### G. DynamoDB/CQL/Redis

Giải thích:
1. ExpressionAttributeNames khác field authorization.
2. KeyCondition khác FilterExpression.
3. CQL bound values khác identifiers.
4. Redis key namespace/ACL.
5. Dynamic scripts và cost limits.

### H. OpenSearch/Graph

User muốn raw regex, script query, sort internalRiskScore, deep pagination, arbitrary graph traversal. Xác định trường hợp reject, trường hợp privileged API riêng và query budget.

### I. Custom fields

Tenant admin đăng ký customPriority integer 0..100:
1. Registry chứa gì?
2. Mapping path?
3. Operator/role policy?
4. Index/cost constraints?
5. Policy version và cache?

### J. Fuzzing

Lập ít nhất 15 negative tests:
- Object thay enum.
- Array thay scalar.
- Number thay string.
- String thay number.
- Unknown enum.
- Duplicate keys.
- Unknown field.
- Null/missing.
- Deep nesting.
- Huge string.
- Long overflow.
- IN too large.
- OR too deep.
- Forbidden sort.
- TenantId từ body.
- Raw update operator.
- Raw aggregation.
- Invalid date range.
- Cursor tenant khác.
- Authorization-denied field.

Với mỗi test ghi expected error, có DB query emitted hay không, data exposure và metrics.

### K. Incident

Một tenant thấy booking của tenant khác sau release search filter. Lập runbook contain, thu evidence redacted, kiểm tra parser/compiler AND/OR, repro T1/T2, fix policy, tests, audit scope và monitor.

### L. Phản biện

Một đồng nghiệp đề xuất:

> “Frontend có hai filter nên backend cứ nhận Map. Chặn ký tự dollar là xong. DynamoDB placeholder làm mọi field an toàn. PATCH vào entity cho tiện. Bỏ validation sẽ nhanh hơn.”

Phản biện về trust boundary, typed DTO, field/operator whitelist, parameterization vs authorization, mass assignment, query cost, least privilege, security tests.

### Hướng giải

Một API được bảo vệ tốt:
1. Strict JSON parser với duplicate/unknown policy và size/depth limits.
2. Typed DTO/enum và domain validators.
3. Tenant/role lấy từ trusted identity.
4. Per-field/per-operator/per-action allowlist.
5. Query compiler dùng DB names/operators cố định.
6. Không raw JSON/update/pipeline từ client.
7. Domain commands với conditional updates.
8. Output DTO và authorization theo resource/field.
9. Database schema/ACL/least privilege.
10. Query budgets, timeouts, rate limits.
11. Unit/integration/fuzz/cross-tenant tests.
12. Redacted observability và rollout plan.

## 37. Checklist triển khai

1. **Đã liệt kê các untrusted input boundary?**
2. **Dùng typed DTO, không pass-through raw Map?**
3. **Unknown properties có policy?**
4. **Duplicate keys được reject/giải quyết nhất quán?**
5. **Body/depth/array limits có?**
6. **Coercion/Jackson version được kiểm tra?**
7. **Enums/numbers/dates/IDs đúng type?**
8. **Null/missing semantics rõ?**
9. **Object tại scalar field bị reject?**
10. **DB field names từ allowlist mapping?**
11. **Field/operator pairs có policy?**
12. **IN/OR/range/node limits có?**
13. **Raw scripts/regex/aggregation bị hạn chế?**
14. **Sort/projection/response fields có authorization?**
15. **Pagination size/cursor được kiểm tra?**
16. **Tenant từ principal đáng tin?**
17. **Resource-level permission đã kiểm tra?**
18. **AND/OR grouping có cross-tenant tests?**
19. **Mutation DTO ngăn mass assignment?**
20. **Domain state transitions có conditional authority?**
21. **Version conflict/timeout unknown có policy?**
22. **DynamoDB expression names được whitelist?**
23. **CQL identifiers constant, values bound?**
24. **Redis command/key namespace/ACL được khóa?**
25. **Search DSL và graph traversal có budget?**
26. **Database schema/least privilege được dùng?**
27. **Timeout/rate/concurrency limits có?**
28. **Allowed query shapes có indexes phù hợp?**
29. **Error messages không lộ raw payload/secret?**
30. **Metrics/logs redacted, low cardinality?**
31. **Type/operator/duplicate/overflow unit tests?**
32. **Compiled query integration tests?**
33. **Cross-tenant read/update tests?**
34. **Fuzz/property-based tests?**
35. **Response DTO không chứa private fields?**
36. **Security migration/rollout plan?**
37. **Privileged querying có audit/quota riêng?**
38. **Incident runbook có?**
39. **Theo dõi invalid input và source cost sau deploy?**
40. **Không coi validation thay authorization?**

**Kết luận:** Bảo mật NoSQL không chỉ là escape chuỗi hay dùng driver builder. Điểm quan trọng là **không cho dữ liệu đầu vào trở thành cú pháp truy vấn tùy ý**. Hãy tạo một grammar nhỏ theo nghiệp vụ, kiểm tra **kiểu, field, toán tử, nested path, sort, projection, update và query cost**, gắn với quyền của principal và tenant. Parse bằng typed DTO, reject wrong-type/unknown/duplicate input theo contract, biên dịch sang driver expression bằng fields/operators do server quyết định và bảo vệ database bằng least privilege, quota, timeout. Đừng truyền raw Map/JSON hoặc update/aggregation DSL vào NoSQL và đừng nhầm parameter binding với phân quyền. Kiểm chứng bằng tests cả điều kiện hợp lệ và invalid, cùng các tình huống cross-tenant, mass assignment, query-cost abuse, để một đầu vào sai không thể mở rộng quyền truy cập, thay đổi dữ liệu nhạy cảm hay gây quá tải nguồn.
