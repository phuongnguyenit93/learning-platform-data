# So sánh kết quả và phát hiện khác biệt được cho phép

Trong quá trình nâng Java, một dự án có thể biên dịch thành công, chạy toàn bộ unit test cũ và vẫn làm thay đổi hành vi mà người dùng hoặc hệ thống tích hợp quan sát được. Hai bản triển khai cùng trả HTTP 200 nhưng có thể khác số tiền, thứ tự dữ liệu, mã lỗi, timestamp, định dạng JSON, số lần publish event hoặc khả năng kết nối TLS. Ngược lại, hai JSON responses có thể khác thứ tự thuộc tính hay ID truy vết nhưng vẫn tương đương theo hợp đồng.

Điều quan trọng không phải là làm mọi kết quả trước và sau migration giống nhau từng ký tự. Điều quan trọng là **phát hiện đầy đủ những khác biệt có ý nghĩa, phân biệt lỗi hồi quy với thay đổi hợp lệ, và không cho phép các quy tắc bỏ qua che khuất lỗi thực sự**.

Bài học thuộc **Java Advance Compatibility Migration**, chương **Kiểm thử hồi quy**, với chủ đề **So sánh kết quả và phát hiện khác biệt được cho phép**. Nội dung tập trung vào so sánh hành vi giữa các phiên bản JDK, xây test oracle, xử lý dữ liệu không xác định, thiết kế phép so sánh ngữ nghĩa, quản lý ngoại lệ có phê duyệt và xác minh kết quả trên môi trường Java thực tế.

## 1. Khác biệt không đồng nghĩa hồi quy

Giả sử phiên bản cũ trả:

~~~json
{
  "orderId": "O-42",
  "total": "240000.00",
  "currency": "VND",
  "items": [
    {"sku": "BOOK", "quantity": 2}
  ],
  "traceId": "a1",
  "processedAt": "2026-11-12T03:00:00Z"
}
~~~

Phiên bản mới trả:

~~~json
{
  "processedAt": "2026-11-12T03:00:01Z",
  "items": [
    {"quantity": 2, "sku": "BOOK"}
  ],
  "currency": "VND",
  "traceId": "b2",
  "total": "240000.00",
  "orderId": "O-42"
}
~~~

Hai chuỗi JSON không giống nhau. Tuy nhiên:

- Thứ tự thuộc tính trong JSON object thường không mang ngữ nghĩa thứ tự.
- traceId có thể là metadata vận hành không cam kết giá trị cụ thể.
- processedAt có thể thay đổi vì hai lượt chạy không dùng cùng đồng hồ.
- total, currency, orderId và quantity là dữ liệu nghiệp vụ phải được kiểm tra nghiêm ngặt.
- Thứ tự phần tử trong JSON array thường có ý nghĩa, không được bỏ qua tùy tiện.

Nếu một comparator chỉ so chuỗi, nó có thể tạo false positive. Nếu comparator xóa mọi field có tên chứa id hoặc time, nó có thể tạo false negative nguy hiểm.

**Nguyên tắc:** phân loại khác biệt theo hợp đồng và mức ảnh hưởng, không theo việc có thấy dấu cộng/dấu trừ trong diff hay không.

## 2. Bốn loại kết quả so sánh

| Loại | Ý nghĩa | Xử lý |
|---|---|---|
| Exact match | Kết quả giống theo biểu diễn được yêu cầu | Pass |
| Semantic equivalent | Biểu diễn khác nhưng ngữ nghĩa và hợp đồng không đổi | Pass với rule cụ thể |
| Approved behavior change | Ngữ nghĩa đã đổi có chủ đích, được đánh giá và phê duyệt | Pass có điều kiện/versioning |
| Unexpected difference | Khác biệt chưa được cho phép hoặc vi phạm invariant | Fail và điều tra |
| Inconclusive | Không đủ dữ liệu hoặc test harness lỗi | Không coi là pass |

Thêm trạng thái inconclusive là cần thiết. Nếu không thu được event hoặc snapshot database, ta không có cơ sở kết luận hai bản ứng dụng tương đương.

### 2.1. “Allowed difference” phải có phạm vi

Một quy tắc hợp lệ có thể là:

~~~text
Chỉ cho phép giá trị /traceId khác nhau.
Cả hai giá trị phải là chuỗi không rỗng đúng định dạng.
Các vị trí khác của payload vẫn phải tương đương.
Mối liên kết traceId trong mỗi execution vẫn phải nhất quán.
~~~

Một quy tắc quá rộng như “ignore all identifiers” có thể bỏ qua orderId, customerId hoặc tenantId, dẫn tới mất bằng chứng về lỗi dữ liệu.

### 2.2. Thay đổi có chủ đích không tự động là backward-compatible

Ví dụ JDK mới từ chối TLS yếu theo policy bảo mật. Đây có thể là thay đổi đúng về an toàn nhưng vẫn làm một consumer cũ không kết nối được. Nó đòi hỏi migration decision, thông báo và phương án xử lý compatibility, không phải chỉ thêm một rule “bỏ qua lỗi handshake”.

## 3. Test oracle: lấy đâu làm chuẩn?

**Test oracle** là căn cứ để kết luận một output là đúng.

Các phương pháp chính:

1. **Expected values:** kết quả được tính từ yêu cầu nghiệp vụ hoặc thông số kỹ thuật độc lập.
2. **Differential testing:** chạy cùng input trên bản cũ và bản mới, so outputs.
3. **Invariant/property testing:** kiểm tra quy luật luôn phải đúng dù giá trị cụ thể thay đổi.
4. **Consumer contract testing:** kiểm tra những điều mà bên gọi phụ thuộc.
5. **Historical replay:** đảm bảo dữ liệu cũ và luồng cũ vẫn xử lý được.

Đừng coi phiên bản cũ là chân lý tuyệt đối. Nó có thể có bug mà bản mới vô tình sửa. Khi V1 và V2 khác nhau, cần phân tích behavior nào phù hợp với nghiệp vụ và hợp đồng đã công bố.

### 3.1. Ví dụ độc lập khỏi baseline cũ

~~~text
Input:
  quantity = 3
  unitPrice = 120.00
  discount = 10.00

Business invariant:
  subtotal = 360.00
  total = 350.00
  total >= 0
  currency không đổi
~~~

Nếu cả V1 và V2 đều trả total=349.00, differential test có thể pass nhưng invariant độc lập vẫn fail. Kết hợp hai loại oracle giúp tránh hợp thức hóa lỗi lịch sử.

## 4. Kiểm kê toàn bộ đầu ra có thể quan sát

Một request có thể để lại nhiều hiệu ứng ngoài HTTP response:

| Ranh giới | Các dữ liệu cần so |
|---|---|
| REST/gRPC | Status, headers, body, errors |
| Serialization | JSON, XML, Avro, Protobuf schema/value |
| Database | Rows, constraints, transaction outcome |
| Messaging | Topic, key, payload, event order |
| Batch | Input/output files, record count, report |
| Tính toán | Decimal precision, rounding, overflow |
| Security | Authentication, authorization, signature, TLS |
| Thời gian | Timestamps, expiration, scheduling |
| Concurrency | Duplicates, races, consistency |
| Vận hành | Startup, shutdown, GC, resource usage |
| Hiệu năng | Latency distribution, throughput, error rate |

Ví dụ hai phiên bản cùng trả:

~~~json
{"status":"COMPLETED"}
~~~

nhưng V1 publish một OrderCompleted event còn V2 publish hai events. Đây có thể là regression nghiêm trọng dù body giống hệt.

**So sánh kết quả phải bao gồm những side effects được hợp đồng yêu cầu.**

## 5. Chuẩn bị môi trường so sánh tương đương

Hai executions chỉ có ý nghĩa khi những yếu tố quan trọng được kiểm soát hoặc ghi nhận rõ:

- Commit/build của phiên bản cũ và mới.
- JDK vendor, version và update.
- Container image digest, OS, CPU architecture.
- Java locale, default charset, timezone.
- Database snapshot, schema và seed.
- Feature flags và application configuration.
- Network stubs hoặc external services.
- Clock, randomness và ID generator.
- Heap, GC, CPU/memory limits.
- Thread pool và concurrency level.
- Cache warm-up, connection pools.
- Observability agents.
- Dependency versions.

### 5.1. Mẫu baseline

~~~text
OLD:
  appVersion:
  sourceCommit:
  javaVersion:
  javaVendor:
  imageDigest:

NEW:
  appVersion:
  sourceCommit:
  javaVersion:
  javaVendor:
  imageDigest:

SHARED:
  fixtureVersion:
  databaseSeed:
  timezone:
  locale:
  featureFlags:
  upstreamStubs:
  requestSequence:
  testConcurrency:
  measurementWindow:
~~~

Nếu nâng Java đồng thời nâng database driver, framework hoặc serializer, cần ghi nhận tất cả thay đổi. Một khác biệt không thể mặc nhiên quy cho JDK.

### 5.2. Mô hình differential testing

~~~text
Controlled fixture/input
           |
       +---+---+
       |       |
       v       v
    Old JDK  New JDK
       |       |
       v       v
    Output A Output B
       |       |
       +---+---+
           |
           v
   Contract validation
           |
           v
    Semantic comparison
           |
           v
   Allowed-difference policy
           |
           v
   Classification and report
~~~

Nếu dùng traffic được ghi từ production, cần bảo vệ PII/secrets và cô lập side effects để tránh ghi dữ liệu, gửi email hoặc thanh toán hai lần.

## 6. Ba cấp độ phép so sánh

### 6.1. Byte-for-byte equality

So sánh trực tiếp bytes.

Phù hợp với:

- Artifact yêu cầu reproducible binary output.
- Chữ ký/hash khi canonical representation được cam kết.
- Fixed-width records và binary protocols chính xác.
- File checksum contract.
- Dữ liệu phải giữ nguyên từng byte.

Không phù hợp nếu hai JSON object chỉ khác thứ tự property mà contract không quy định thứ tự.

### 6.2. Structural equality

Parse dữ liệu thành cấu trúc rồi so sánh:

~~~text
JSON string -> JSON tree -> compare fields and values
XML document -> XML model -> namespace-aware compare
Database -> keyed rows -> compare columns
~~~

Phép so sánh này bỏ qua một số khác biệt biểu diễn không mang ý nghĩa, nhưng không được bỏ qua required fields, type changes hay array order nếu contract yêu cầu.

### 6.3. Semantic equality

Trích xuất những sự kiện nghiệp vụ:

~~~text
Result -> parse -> validate schema
       -> map domain facts
       -> compare business invariants
~~~

Ví dụ hai CSV có cùng bản ghi nhưng khác thứ tự có thể tương đương nếu hợp đồng là tập bản ghi không thứ tự. Ngược lại, một danh sách transaction có thứ tự thời gian hoặc số thứ tự phải giữ order.

### 6.4. So sánh theo miền dữ liệu

| Dữ liệu | So sánh thông thường |
|---|---|
| Số tiền | Decimal chính xác và rounding rule |
| UUID động | Format, uniqueness, correlation |
| Danh sách có thứ tự | Exact sequence |
| Tập giá trị | Set equality |
| Danh sách có phần tử trùng | Multiset equality |
| Instant | Cùng thời điểm hoặc bounded tolerance theo contract |
| Security decision | Exact allow/deny semantics |
| Performance | Statistics và SLO |
| Chữ ký số | Verification và protocol-specific invariants |

Không dùng một comparator chung cho mọi loại output.

## 7. JSON: những khác biệt cần phân biệt

Hai JSON objects:

~~~json
{"id":"A1","status":"PAID"}
~~~

~~~json
{"status":"PAID","id":"A1"}
~~~

thường tương đương về object members. Nhưng:

~~~json
{"items":["A","B"]}
~~~

~~~json
{"items":["B","A"]}
~~~

có thể khác về ngữ nghĩa nếu items là ordered sequence.

### 7.1. Missing khác null khác zero

~~~json
{}
~~~

~~~json
{"discount":null}
~~~

~~~json
{"discount":0}
~~~

không được coi là tương đương mặc định. Đối với PATCH, missing có thể nghĩa là giữ nguyên; null có thể nghĩa là xóa; zero có thể là giá trị số xác định.

### 7.2. Number khác string

~~~json
{"total":125000}
~~~

~~~json
{"total":"125000"}
~~~

khác wire type, dù một parser lenient có thể chuyển đổi. Nếu API contract yêu cầu number, thay number bằng string là breaking change với nhiều consumers.

### 7.3. Rename trường

~~~json
{"customerId":"C-1"}
~~~

không giống:

~~~json
{"clientId":"C-1"}
~~~

Một semantic comparator có thể nhận ra hai tên có chung ý nghĩa, nhưng điều đó **không chứng minh backward compatibility**. Nếu consumer cũ chỉ hiểu customerId thì việc đổi wire name vẫn có thể phá hệ thống.

### 7.4. Property order và canonical serialization

Một số hệ thống ký canonical JSON hoặc hash payload. Khi hợp đồng yêu cầu exact canonical bytes, thứ tự property/escaping có thể bị điều khiển bởi quy tắc canonicalization. Không được dựa vào quy tắc “JSON object order không quan trọng” để bỏ qua signature mismatch.

## 8. Ví dụ so JSON bằng Jackson và JUnit

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class JsonCompatibilityTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void objectMemberOrderDoesNotMatter() throws Exception {
        String oldJson =
            "{\"id\":\"A1\",\"amount\":2,\"status\":\"PAID\"}";
        String newJson =
            "{\"status\":\"PAID\",\"id\":\"A1\",\"amount\":2}";

        JsonNode before = mapper.readTree(oldJson);
        JsonNode after = mapper.readTree(newJson);

        assertEquals(before, after);
    }
}
~~~

Trong ví dụ, Jackson JsonNode equality cho JSON object không yêu cầu thứ tự các properties như chuỗi ban đầu. JSON arrays vẫn so sánh theo thứ tự.

### 8.1. Bỏ qua đúng một metadata field

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class NarrowNormalizationTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void ignoresOnlyRootTraceId() throws Exception {
        JsonNode a = mapper.readTree(
            "{\"orderId\":\"O1\",\"total\":\"10.00\",\"traceId\":\"x\"}"
        ).deepCopy();

        JsonNode b = mapper.readTree(
            "{\"traceId\":\"y\",\"total\":\"10.00\",\"orderId\":\"O1\"}"
        ).deepCopy();

        ((ObjectNode) a).remove("traceId");
        ((ObjectNode) b).remove("traceId");

        assertEquals(a, b);
    }
}
~~~

Đoạn này giả định root là object và contract cho phép /traceId khác giá trị. Đối với dữ liệu không tin cậy, cần validate loại node và schema trước khi cast hoặc chuẩn hóa.

**Cảnh báo:** nếu contract bắt buộc traceId hiện diện và đúng format, việc chỉ xóa trường rồi so sánh là chưa đủ. Nên kiểm tra presence/type/format của trường đó trước, sau đó mới bỏ qua phần giá trị động.

### 8.2. Không normalize trước schema validation

Một thứ tự an toàn:

~~~text
Raw JSON
  |
  v
Schema/type checks
  |
  v
Validate allowed dynamic fields
  |
  v
Normalize only approved paths
  |
  v
Compare business facts
  |
  v
Report raw and normalized diff
~~~

Cách này tránh vô tình che việc mất field bắt buộc hoặc thay JSON type.

## 9. Thứ tự của list, set, multiset và pagination

Một comparator cần biết ý nghĩa collection.

| Contract | Ví dụ | Quy tắc so |
|---|---|---|
| Sequence | Transaction history, event order | So cùng thứ tự |
| Set | Permissions đã chuẩn hóa | So tập phần tử |
| Multiset | Cart lines có thể trùng | So cả giá trị và số lần xuất hiện |
| Map | Key/value data | So theo key |
| Ordered page | Search results có sort | So thứ tự và boundaries |

Nếu chỉ chuyển list sang HashSet rồi so sánh, duplicates bị mất. Nếu một API phân trang có sort không ổn định, cần xác định tie-breaker, ví dụ ORDER BY created_at, id.

### 9.1. Ví dụ đếm số lần xuất hiện

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class Multisets {
    public static <T> Map<T, Long> count(List<T> values) {
        Map<T, Long> result = new HashMap<>();

        for (T value : values) {
            result.merge(value, 1L, Long::sum);
        }

        return result;
    }
}
~~~

Phép so sánh multiset:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

assertEquals(
    Multisets.count(beforeItems),
    Multisets.count(afterItems)
);
~~~

Chỉ dùng khi contract không cam kết thứ tự nhưng vẫn yêu cầu giữ số lần lặp.

### 9.2. HashMap iteration order sau nâng JDK

HashMap không cam kết thứ tự iteration như một List đã sort. JDK hoặc dependency changes có thể làm output vô tình dựa vào HashMap iteration thay đổi. Tuy nhiên, dù behavior cũ không được Java specification bảo đảm, consumer thực tế có thể đã phụ thuộc vào output đó. Phải điều tra de facto contract trước khi tuyên bố an toàn.

## 10. Thời gian, timezone và đồng hồ

Một test chạy V1 lúc 10:00:00 và V2 lúc 10:00:01 có thể thấy timestamp khác dù logic giống nhau.

### 10.1. Tốt nhất là inject Clock

~~~java
import java.time.Clock;
import java.time.Instant;

public final class PaymentService {
    private final Clock clock;

    public PaymentService(Clock clock) {
        this.clock = clock;
    }

    public Instant createdAt() {
        return Instant.now(clock);
    }
}
~~~

Test:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PaymentServiceTest {
    @Test
    void fixedClockMakesOutputDeterministic() {
        Instant instant =
            Instant.parse("2026-11-12T03:00:00Z");

        Clock fixed = Clock.fixed(
            instant,
            ZoneOffset.UTC
        );

        PaymentService service = new PaymentService(fixed);

        assertEquals(instant, service.createdAt());
    }
}
~~~

Nếu kiểm soát Clock trong application layer, hai bản có thể tạo timestamp cùng giá trị. Đây thường là cách tốt hơn việc xóa mọi timestamp khỏi comparison.

### 10.2. Khi không thể cố định đồng hồ

Một policy có thể cho phép bounded difference ở một trường cụ thể, ví dụ processing timestamp được tạo trong khoảng bắt đầu/kết thúc request. Nhưng cần định nghĩa:

- Tên trường/JSON path.
- Phạm vi thời gian.
- Đơn vị và precision.
- Offset/timezone.
- Trường hợp vượt giới hạn phải fail.
- Loại timestamp có bắt buộc chính xác hay không.

Đừng dùng một tolerance thời gian rộng cho expiration, security token hoặc ledger timestamp nếu hợp đồng cần chính xác.

### 10.3. JDK timezone data có thể khác

JDK update có thể mang timezone/locale data mới; container base image cũng có timezone default khác. Cần test với ZoneId tường minh, nhất là quanh DST và các khu vực có thay đổi chính sách giờ. Nếu bản mới phản ánh một rule timezone chính thức mới, đó có thể là intentional change; phải ghi phạm vi và consumer impact.

## 11. Randomness, UUID và correlation

Những giá trị thường khác giữa hai lần chạy:

- UUID.
- Session ID.
- Trace ID.
- Security token.
- Generated database ID.
- Random sample ID.
- Retry/backoff jitter.

### 11.1. Không cố định SecureRandom trong production

Để test deterministic, có thể inject một IdGenerator hoặc TokenGenerator. Bản test dùng generator có seed/fixture, bản production dùng generator phù hợp yêu cầu bảo mật.

Không sửa code production bằng cách thay SecureRandom bằng java.util.Random để snapshot test pass.

### 11.2. So quan hệ thay vì raw IDs

~~~text
POST /orders -> returns orderId
GET /orders/{orderId} -> returns same order
OrderCreated event -> references same orderId
Database order -> same business entity
~~~

ID giữa V1 và V2 có thể khác, nhưng trong mỗi run, các thành phần phải liên kết chính xác. Comparator nên mapping theo business key và kiểm tra referential consistency, không xóa mọi identifier.

### 11.3. ID format cũng có contract

Nếu public API cam kết UUID string, V2 trả null hoặc một chuỗi không hợp lệ không được xem là allowed difference. Rule chỉ nên bỏ qua raw value sau khi validate format, uniqueness và relationship.

## 12. Floating point, BigDecimal và độ chính xác

Không dùng cùng tolerance cho mọi giá trị số.

| Miền | So sánh phù hợp |
|---|---|
| Tiền, số dư | Exact decimal và rounding policy |
| Số lượng | Exact integer |
| Tham số đo sensor | Absolute/relative tolerance theo độ chính xác |
| Kết quả khoa học | Error bounds + special cases |
| Percentage report | Scale, precision, rounding được chỉ định |
| Signature/hash | Exact/protocol verification |

### 12.1. BigDecimal scale và value

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("10.0");
BigDecimal b = new BigDecimal("10.00");

System.out.println(a.equals(b));    // false
System.out.println(a.compareTo(b)); // 0
~~~

Nếu business contract chỉ yêu cầu cùng giá trị thập phân, compareTo có thể được dùng. Nếu API yêu cầu hai chữ số sau dấu thập phân khi serialize thành string, scale vẫn là một phần hợp đồng.

### 12.2. Numeric tolerance trong JUnit

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SensorTest {
    @Test
    void boundedMeasurementNoise() {
        double expected = 12.345678;
        double actual = 12.345680;

        assertEquals(expected, actual, 0.00001);
    }
}
~~~

Ngưỡng 0.00001 chỉ minh họa. Trong dự án thực tế phải được lựa chọn theo độ chính xác thiết bị/thuật toán, không tăng dần cho tới khi test xanh.

### 12.3. Absolute và relative tolerance

Một quy tắc có thể mô tả:

~~~text
abs(actual - expected) <= absoluteTolerance
OR
abs(actual - expected)
    <= relativeTolerance * max(abs(expected), abs(actual))
~~~

Cần xét số gần zero, số cực lớn, NaN, infinity và signed zero. Tolerance phụ thuộc miền giá trị và yêu cầu correctness.

### 12.4. Rounding mode là policy nghiệp vụ

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("12.345");
BigDecimal rounded = amount.setScale(
    2,
    RoundingMode.HALF_EVEN
);
~~~

Nếu V1 và V2 khác nhau vì HALF_EVEN/HALF_UP, đây là policy change cần phê duyệt, không phải floating-point noise tự nhiên.

### 12.5. Nâng JDK/hardware không giải thích được mọi sai số

Một số khác biệt số học có thể đến từ algorithm, vectorization, dependencies hoặc CPU architecture. Nhưng phải đối chiếu numeric contract trước khi hợp thức hóa bất kỳ sự chênh lệch nào.

## 13. Serialization và schema compatibility

Nâng JDK thường đi cùng nâng Jackson, JAXB, Hibernate, Spring, Avro/Protobuf libraries hoặc configuration.

Khác biệt có thể xuất hiện ở:

- Wire field names.
- Null/missing/default.
- String vs number.
- Enum representations.
- Date/time format.
- JSON property order.
- XML namespace/whitespace.
- Array/list order.
- Object serialization.
- Binary schema resolution.
- Unknown-field handling.

### 13.1. Một semantic match không thay thế wire compatibility

V1:

~~~json
{"amount":125000}
~~~

V2:

~~~json
{"amountText":"125000"}
~~~

Một comparator biết map amountText sang amount có thể tính ra cùng giá trị nghiệp vụ, nhưng client đang đọc amount có thể bị hỏng.

Do đó cần **hai kết luận riêng**:

1. Business fact có tương đương không?
2. Wire/API contract có tương thích với consumer cũ không?

### 13.2. XML

Whitespace và thứ tự attributes có thể không mang ý nghĩa theo một XML data model, nhưng element order, namespace URI và text content có thể quan trọng. Với XML signatures, dùng chuẩn canonicalization của signature protocol thay vì tự strip hoặc sort XML tùy tiện.

### 13.3. Avro/Protobuf

Schema registry có thể kiểm tra các quy tắc compatibility, nhưng không biết default value có đúng nghiệp vụ hay không. Test consumer–writer matrix và replay historical events vẫn cần thiết.

### 13.4. Java object serialization

ObjectOutputStream có serialVersionUID, class descriptors và schema evolution riêng. Khi migration, cần test deserialization dữ liệu lịch sử và round-trip semantics; không chỉ so raw serialized bytes nếu byte-level format không được cam kết.

## 14. Database: so cả trạng thái sau transaction

Hai responses giống nhau nhưng database state khác nhau vẫn có thể là regression.

~~~text
Input: completeOrder("O-42")

V1:
  orders.status = COMPLETED
  payments.captured = 1
  outbox OrderCompleted = 1 event

V2:
  orders.status = COMPLETED
  payments.captured = 1
  outbox OrderCompleted = 2 events
~~~

Response có thể giống, nhưng V2 vi phạm duplicate event invariant.

### 14.1. Snapshot theo business keys

Dùng database được seed cùng dữ liệu và lấy snapshot các bảng/record liên quan. Với auto-generated primary keys, có thể mapping theo business key rồi kiểm tra foreign-key relationships.

Đừng xóa toàn bộ IDs khỏi comparison nếu chúng đóng vai trò integrity.

### 14.2. Dữ liệu không có ORDER BY

SQL không cam kết thứ tự rows khi query không có ORDER BY. Nếu API contract cần thứ tự, phải xác định ORDER BY với tie-breaker; nếu output là set, so multiset hợp lệ hơn.

### 14.3. Transaction semantics

Cần kiểm tra:

- Commit và rollback.
- Atomicity.
- Isolation.
- Optimistic locking/version.
- Constraint enforcement.
- Retries và idempotency.
- Number of records affected.
- Outbox consistency.
- Duplicate prevention.

### 14.4. Database schema migration là thay đổi riêng

Nếu nâng JDK cùng lúc đổi schema, phải tách nguyên nhân lỗi. Dữ liệu cũ có default/field thiếu và driver mới có thể deserialize khác, nên cần fixtures cho historical rows.

## 15. Events, queues và eventual consistency

Đối với Kafka/RabbitMQ hoặc event systems, so sánh cần kiểm tra:

- Topic/queue.
- Partition/key.
- Event type/schema version.
- Headers và payload.
- Event count.
- Ordering theo phạm vi được cam kết.
- Retries, duplicates và dead-letter behavior.
- Consumer-visible final state.

### 15.1. Không áp đặt global order ngoài contract

Một broker có thể chỉ bảo đảm thứ tự trong partition hoặc aggregate. Không nên so tất cả events theo global sequence khi contract không cam kết; nhưng phải giữ thứ tự trong phạm vi nó có ý nghĩa.

### 15.2. Eventual consistency cần wait-until

~~~text
Start operation
       |
       v
Poll expected invariant
       |
       +--> reached before deadline: pass
       +--> deadline exceeded: fail
~~~

Đừng chỉ sleep cứng một khoảng rồi so output nếu hệ thống có độ trễ bất đồng bộ biến thiên.

### 15.3. Shadow traffic phải cô lập side effects

Một request payment gửi song song vào V1/V2 có thể charge hai lần nếu không cô lập. Shadow run nên dùng môi trường riêng hoặc stub providers, kiểm soát idempotency và quyền sử dụng dữ liệu.

## 16. Exception và error response cũng là hợp đồng

V1:

~~~json
{"code":"INVALID_AMOUNT","message":"Amount must be positive"}
~~~

V2:

~~~json
{"status":400,"error":"Bad Request"}
~~~

Cả hai có thể HTTP 400 nhưng khác machine-readable error code. Nếu client dựa vào INVALID_AMOUNT, đây là breaking change.

### 16.1. Phân lớp độ ổn định

| Thành phần | Thường cần giữ? |
|---|---|
| HTTP status | Theo API contract |
| Machine-readable error code | Theo API contract |
| Error body schema | Theo API contract |
| User-facing message | Có thể được localization theo policy |
| Internal stack trace/line number | Thường không là contract |
| Java exception type trong public library | Có thể là source/binary API contract |
| Audit event | Thường phải giữ ngữ nghĩa |

Không được ignore toàn bộ error response chỉ vì wording thay đổi.

### 16.2. Security errors

Một thay đổi làm thông báo lỗi ít tiết lộ hơn có thể là cải tiến. Nhưng phải kiểm tra mã lỗi, authorization outcome và không làm lộ dữ liệu. Đặc biệt, một request trước đây bị từ chối nhưng nay được phép truy cập cần được coi là security regression cho tới khi có bằng chứng ngược lại.

## 17. Locale, charset, timezone và Unicode

JDK, locale provider và container image có thể làm output thay đổi ở:

- Ngày/tháng và lịch.
- Decimal separator.
- Currency format.
- Collation và sorting.
- Default charset.
- Line endings.
- Unicode normalization/case mapping.
- Timezone data.

Từ Java 18, default charset được chuẩn hóa thành UTF-8 theo JEP 400 trong phạm vi quy định. Nếu code cũ dựa vào charset mặc định của OS, migration có thể tạo khác biệt file/network output.

### 17.1. Dùng Locale rõ ràng

~~~java
import java.text.NumberFormat;
import java.util.Locale;

NumberFormat format = NumberFormat.getNumberInstance(
    Locale.forLanguageTag("vi-VN")
);

String result = format.format(12345.67);
~~~

Nếu cần contract định dạng cố định, test nên chọn Locale/timezone/charset rõ, không phụ thuộc các defaults không được tài liệu hóa.

### 17.2. Line endings

LF và CRLF có thể tương đương đối với một file text nếu contract chỉ quy định nội dung dòng. Nhưng với file đã ký, hash hoặc fixed-width protocol, từng byte có thể quan trọng. Không normalize line endings toàn cục.

### 17.3. Unicode normalization

Hai chuỗi hiển thị giống nhau có thể chứa các code-point sequences khác. Unicode normalization có thể là yêu cầu hợp lệ ở search/input, nhưng có thể làm thay đổi IDs, signatures hoặc payload cần round-trip nguyên văn. Chọn theo domain.

### 17.4. Sorting với locale

Nếu API yêu cầu stable pagination, phải có comparator/collation policy và tie-breaker. Một thay đổi thứ tự khi nâng locale data cần được kiểm tra với dữ liệu tiếng Việt có dấu, không chỉ ASCII.

## 18. Security: nhóm khác biệt phải xét riêng

Nâng JDK có thể đổi TLS policy, certificate validation, cryptographic defaults, module access hoặc reflection behavior.

### 18.1. TLS legacy bị từ chối

V1 kết nối được một endpoint chỉ hỗ trợ thuật toán yếu, V2 từ chối. Đây có thể là thay đổi đúng theo security policy, nhưng cần migration plan:

1. Xác nhận protocol/cipher/certificate gây lỗi.
2. Đánh giá mức yêu cầu bảo mật.
3. Nâng server hoặc dùng gateway được kiểm soát khi cần.
4. Phê duyệt ngoại lệ có thời hạn nếu có.
5. Test downgrade resistance và certificate validation.
6. Không tắt hostname verification hoặc trust-all để test xanh.

### 18.2. Authorization invariant

Ví dụ:

~~~text
Tenant A không được xem dữ liệu Tenant B.
Token hết hạn phải bị từ chối.
User không có quyền không được cập nhật role.
Input invalid không được gây side effect.
~~~

Những bất biến này quan trọng hơn tỉ lệ pass tổng thể. Một regression ở authorization không thể được che bằng normalization rule dù chỉ ảnh hưởng một test case.

### 18.3. Cryptographic output

Một số chữ ký có randomness nên raw signature bytes khác giữa hai lần ký dù cả hai hợp lệ. Trong trường hợp đó test có thể kiểm tra verify success, key identity, algorithm policy và integrity. Nhưng với digest/canonical hashing contract, byte equality vẫn cần được giữ.

Không dùng khả năng ký “thành công” để bỏ qua việc thuật toán bị downgrade.

## 19. Performance regression khác functional regression

Thời gian xử lý của Java chịu ảnh hưởng JIT, GC, CPU, heap, warm-up, container quotas, native libraries và network. Một lời gọi 4 ms ở V1 và 5 ms ở V2 chưa đủ kết luận regression.

### 19.1. Functional comparison

~~~text
Input -> expected business output/side effects
~~~

### 19.2. Non-functional comparison

~~~text
Comparable workload
      |
      v
Distributions of latency, throughput, CPU, memory, errors
      |
      v
SLO/guardrails with sufficient evidence
~~~

Hai loại phải dùng tiêu chí riêng. Không áp tolerance 10% của latency cho số tiền hoặc transaction counts.

### 19.3. Cần kiểm soát khi đo

- JDK vendor/update.
- CPU architecture.
- JVM heap/GC.
- Thread counts.
- Request mix.
- Database/cache state.
- Network conditions.
- Warm-up duration.
- Sample size và number of runs.
- Monitoring/agent overhead.

### 19.4. Những metrics hữu ích

- p50/p95/p99 latency.
- Throughput.
- Error rate.
- CPU utilization.
- GC pause distribution.
- Allocation rate.
- RSS/native memory.
- Queue lag.
- Startup time.

Một bản có throughput cao hơn vì trả nhiều lỗi hơn không phải là cải tiến.

### 19.5. Microbenchmark và end-to-end

Nếu đo Java method rất nhỏ, JMH hoặc công cụ benchmark phù hợp hữu ích hơn System.nanoTime của một lần gọi. Nhưng đánh giá production migration vẫn cần integration/load tests trên deployment topology thực tế.

## 20. Những thay đổi JDK có thể hợp lệ nhưng vẫn cần bằng chứng

| Khác biệt | Có thể chấp nhận khi | Cần kiểm tra thêm |
|---|---|---|
| Thứ tự property JSON | Object structure tương đương | Signed/canonical payload? |
| Thứ tự HashMap iteration | Thứ tự không thuộc contract | Consumer thực tế có phụ thuộc? |
| UUID/traceId | Giá trị động, đúng format | Correlation/uniqueness |
| Processing timestamp | Có time-bound policy | Expiration/audit semantics |
| Error wording | Machine-readable contract ổn định | Consumer/client parsing |
| Charset output | Intentional UTF-8 contract | Dữ liệu lịch sử |
| Locale format | Đã cập nhật policy | Internationalization tests |
| TLS handshake bị từ chối | Bảo mật mới yêu cầu | Kế hoạch hỗ trợ endpoint cũ |
| GC log format | Chuyển Unified Logging | Parser/metrics vẫn hoạt động |
| Latency chênh lệch nhỏ | Trong SLO/guardrails | Statistical reliability |

Không hàng nào ở bảng tự động pass. Chúng là **ứng viên** cho một quyết định dựa trên hợp đồng, policy và bằng chứng.

## 21. Flaky tests và tính không xác định

Các nguồn nondeterminism thường gặp:

- Clock realtime.
- Random IDs.
- Thread scheduling.
- Concurrent races.
- HashMap/HashSet iteration.
- File listing order.
- External API changes.
- Retries/backoff.
- Cache warm-up.
- Background jobs.
- Tests dùng chung database/queue.

### 21.1. Re-run thành công không chứng minh test sai

Nếu test fail 10% số lần, đó có thể là concurrency regression thực. Không nên auto retry và bỏ qua thất bại đầu tiên mà không điều tra.

### 21.2. Làm test deterministic

Ưu tiên:

- Clock injection.
- Deterministic ID generator trong test.
- Isolated database seeds.
- Upstream stubs.
- Bounded wait-until.
- Explicit sort order.
- Unique test namespaces.
- Controlled concurrency.
- Fixed fixture versions.
- Ghi execution metadata khi fail.

### 21.3. Không dùng sleep dài vô hạn

Với asynchronous operations, dùng condition-based waiting và deadline phù hợp hơn Thread.sleep một khoảng thời gian cố định. Nếu timeout vượt ngưỡng nghiệp vụ, test phải fail.

## 22. Property-based và metamorphic testing

Khi exact output không xác định, có thể kiểm tra các quan hệ.

Ví dụ:

- Serialize rồi deserialize giữ dữ liệu nghiệp vụ.
- Với đơn giá không âm, tăng quantity không làm subtotal giảm.
- Hai request cùng idempotency key không tạo hai payment charges.
- Pages nối lại không làm mất/trùng record trong snapshot cố định.
- Tổng tiền dòng phải bằng tổng tiền order theo rounding policy.
- Một user không có quyền không thể đọc dữ liệu khác tenant.

### 22.1. Metamorphic relation

~~~text
Input A -> Output A

Transform Input A -> Input B -> Output B

Required relation:
  Relation(Output A, Output B) == true
~~~

Phương pháp này không đòi biết output chính xác của mọi input. Nó bổ sung cho differential test, đặc biệt nếu V1 và V2 có cùng một bug.

### 22.2. Boundary inputs

Cần bao gồm:

- Min/max integers và overflow.
- BigDecimal scale/rounding.
- NaN/infinity/signed zero.
- Unicode, combining marks và surrogate pairs.
- Null/missing/empty.
- DST/leap day/timezone.
- Duplicate records.
- Deep JSON/XML nesting.
- Malformed certificates.
- Concurrent retries.
- Historical schema versions.

Các trường hợp biên dễ phát hiện thay đổi parser/serializer/JDK hơn một bộ dữ liệu chỉ có happy path.

## 23. Quy tắc chuẩn hóa phải hẹp và có kiểm chứng

Normalization là một công cụ, không phải giấy phép bỏ qua kết quả không mong muốn.

Một quy tắc tốt có thể là:

~~~yaml
ruleId: DIFF-TRACE-001
scope:
  endpoint: GET /orders/{id}
  jsonPath: /traceId
operation: compare-format-only
constraints:
  required: true
  type: string
  nonEmpty: true
reason: Diagnostic identifier is generated independently
owner: api-platform
reviewDate: 2027-03-01
~~~

Đây là schema minh họa, không phải định dạng của một thư viện cụ thể.

### 23.1. Điều nên có trong rule

- ID ổn định.
- Phạm vi API/event/module.
- JSON path hoặc database column chính xác.
- Điều kiện trước/sau normalization.
- Độ lệch tối đa khi là tolerance.
- Lý do nghiệp vụ/kỹ thuật.
- Owner và reviewer.
- Thời hạn/review date.
- Negative tests chứng minh không che lỗi khác.

### 23.2. Điều không nên làm

~~~yaml
ignoreFieldsMatching: "*Id"
ignoreAllTimestamps: true
ignoreAllUnknownProperties: true
~~~

Các rule này có thể làm mất bằng chứng sai tenantId/orderId, expired token, audit timestamp hoặc schema drift.

### 23.3. Giữ raw và normalized diff

Ví dụ report:

~~~text
Raw:
  /traceId: abc -> def

Rule:
  DIFF-TRACE-001

Checks:
  field exists: yes
  type is string: yes
  format valid: yes
  correlation within run: yes

Normalized:
  no remaining differences

Decision:
  approved non-semantic difference
~~~

Không chỉ lưu normalized data, vì reviewer cần biết những gì đã bị bỏ qua.

## 24. Danh mục approved differences khác known defects

Cần phân biệt:

**Approved difference:** khác biệt không vi phạm hợp đồng hoặc thay đổi contract được duyệt.

**Known defect:** regression đã được xác định nhưng chưa sửa.

Ví dụ:

~~~text
DIFF-090
Status: KNOWN_DEFECT
Impact: Export loses one optional customer attribute
Owner: reporting-team
Mitigation: Disable affected export variant
Fix milestone: next release
~~~

Một known defect có thể được release manager xử lý theo một quyết định rủi ro riêng, nhưng không được đổi nhãn thành semantic equivalent để làm báo cáo đẹp.

### 24.1. Thay đổi có chủ đích

Một intentional behavior change cần:

1. Business/technical requirement cụ thể.
2. Consumer impact assessment.
3. Versioning/deprecation nếu breaking.
4. Positive tests cho behavior mới.
5. Negative tests cho behavior không được phép.
6. Approval và release notes phù hợp.
7. Rollback/contingency nếu cần.

**Allowed không đồng nghĩa “đã hết rủi ro”.**

## 25. Không dùng tổng số diff làm guardrail duy nhất

Ví dụ:

~~~text
Total: 10,000 cases
Exact match: 8,000
Semantic equivalent: 1,700
Approved changes: 250
Unexpected: 50
Inconclusive: 0
~~~

Đây là số minh họa. Tỷ lệ pass 99.5% không đủ đánh giá nếu 50 cases còn lại là lỗi payment/authorization.

### 25.1. Phân loại theo severity

- Critical: security, money, irreversible data loss.
- High: breaking API, duplicate side effect, transaction violation.
- Medium: consumer-visible output/behavior difference có mitigation.
- Low: cosmetic/diagnostic non-contract change.

Severity thực tế phải dựa trên risk policy của tổ chức. Một trường hợp critical có thể chặn release ngay cả khi hàng nghìn cases khác pass.

### 25.2. Gắn diff với vị trí cụ thể

Báo cáo nên nhóm theo:

- Endpoint/operation.
- Business domain.
- JSON path/database field.
- Exception/error code.
- Dependency/JDK version.
- Platform.
- Approved rule ID.
- Owner.
- Test fixture.

Không chỉ đếm 18 diff; nếu 18 diff cũ biến mất nhưng 18 diff mới xuất hiện, số tổng không thay đổi vẫn là vấn đề.

## 26. Thiết kế comparison engine

Một mô hình:

~~~text
Input fixtures or sanitized replay
             |
             v
 Old execution / New execution
             |
             v
 Collect responses, database, events,
 files, metrics and diagnostics
             |
             v
 Validate schema and required fields
             |
             v
 Domain-specific comparison
   - exact
   - structural
   - multiset/sequence
   - numeric/time bounds
   - relational invariants
             |
             v
 Approved-difference rules
             |
             v
 Classify:
   equal
   semantic match
   approved change
   regression
   inconclusive
             |
             v
 Evidence report and review
~~~

### 26.1. Comparator không được sửa production output

Normalization chỉ dùng trên bản sao trong test harness/compare layer. Không được sửa database hoặc API responses thật để giúp comparison xanh.

### 26.2. Phải kiểm tra schema trước

Nếu total thành totalAmount, semantic mapping có thể thấy cùng giá trị nhưng client schema cũ vẫn có thể bị phá. Báo cáo phải thể hiện riêng wire contract status và semantic business status.

### 26.3. Thu thập side effects

Một comparison result có thể chia:

~~~text
response:
  status
  headers
  body

sideEffects:
  databaseChanges
  events
  outboundCalls
  generatedFiles

nonFunctional:
  latency
  cpu
  memory
  logs
~~~

Không nhất thiết mọi test capture mọi thành phần, nhưng phải biết cái gì chưa được kiểm chứng.

### 26.4. Inconclusive không phải success

Nếu dependency ngoài timeout, database snapshot không thu được hoặc test harness parser crash, phải ghi inconclusive/infra failure. Kết luận tương thích đòi đủ evidence theo phạm vi đã định.

## 27. Báo cáo diff có thể hành động

Ví dụ:

~~~text
Case:
  ORDER-QUOTE-017

Baseline:
  Java 11, app 4.2.0

Candidate:
  Java 21, app 5.0.0

Request:
  quote-two-items.json

Difference:
  JSON path: /total
  Before: "240000.00"
  After:  "240000.01"

Classification:
  UNEXPECTED_SEMANTIC_DIFFERENCE

Severity:
  HIGH

Environment:
  Locale: vi-VN
  Timezone: UTC
  Database seed: fixture-2026-11

Rule:
  none

Next action:
  Investigate rounding/dependency behavior
~~~

Ví dụ allowed difference:

~~~text
Case:
  ORDER-QUOTE-017

Difference:
  JSON path: /traceId
  Before: "e4..."
  After:  "a1..."

Classification:
  APPROVED_NON_SEMANTIC_DIFFERENCE

Rule:
  DIFF-TRACE-001

Validation:
  Both are valid identifiers
  Correlation within each run verified

Owner:
  api-platform

Review:
  2027-03-01
~~~

Không để báo cáo tự động đính kèm secrets/PII; có thể lưu sanitized fixtures, redacted values và secure internal links.

## 28. Những khác biệt thường có thể cho phép

### 28.1. Metadata chẩn đoán

Trace ID hoặc diagnostic timestamp nếu nằm ngoài contract và có rule kiểm tra presence/format/correlation.

### 28.2. JSON object member order

Thông thường không mang ý nghĩa trong semantic JSON. Trường hợp signed canonical JSON phải theo quy tắc chữ ký.

### 28.3. Whitespace không mang ngữ nghĩa

Ví dụ JSON pretty-print hoặc line endings của text file có contract cho phép. Không đúng với XML text content, fixed-width protocol hoặc signed payload.

### 28.4. Log format

JDK mới có thể dùng Unified Logging cho GC thay vì PrintGCDetails. Raw log text khác nhau là bình thường, nhưng vẫn cần xác nhận parser, metrics và khả năng điều tra.

### 28.5. Thông báo lỗi nội bộ

Stack trace line number và wording có thể đổi. Tuy nhiên, public error code/HTTP status và security behavior vẫn cần giữ hoặc được version hóa.

### 28.6. Khác biệt số học có bound

Chỉ với miền floating-point hoặc đo lường có tolerance được thiết kế; không áp dụng mặc định cho currency ledger.

### 28.7. Thay đổi bảo mật được duyệt

Một TLS endpoint legacy có thể bị từ chối theo policy mới. Đây là migration exception/intentional change cần kiểm tra consumer impact và mitigation, không phải một lỗi được bỏ qua im lặng.

## 29. Những khác biệt phải được coi là vấn đề cho đến khi chứng minh khác

- Sai số tiền, currency hoặc tax policy.
- Mất required API field.
- Thay JSON type không được consumer hỗ trợ.
- Mất dữ liệu hoặc ghi sai tenant.
- Authorization thay đổi ngoài policy.
- Audit event bị thiếu.
- Transaction mất atomicity.
- Event bị publish trùng gây side effect.
- Ordering quan trọng bị thay.
- Uniqueness hoặc foreign key hỏng.
- Serialization dữ liệu lịch sử thất bại.
- Cryptographic verification sai.
- Expiration/security timestamp không đúng.
- Native crash/JVM crash.
- Error rate tăng vượt guardrail.
- p99 latency vượt SLO trên workload tương đương.

Nếu sản phẩm cố ý thay đổi một trong những behavior này, cần breaking-change process riêng với owner và consumer migration, không thể giải quyết bằng ignore rule không có điều kiện.

## 30. Regression test suite theo tầng

### 30.1. Unit tests

Kiểm tra domain calculations, parser, formatter, validation. Sử dụng fixed Clock và input deterministic.

### 30.2. Contract tests

Kiểm tra API/event schema, error codes, consumer compatibility, fields và enum behavior.

### 30.3. Integration tests

Chạy database, broker, serializer, framework trên JDK target. Kiểm tra transaction và side effects.

### 30.4. Differential replay

Chạy cùng fixtures trên V1/V2, capture outputs, so ngữ nghĩa và phân loại rules.

### 30.5. Shadow/canary

Thu traffic đại diện với side effects cô lập hoặc được kiểm soát, theo dõi lỗi vận hành và SLO. Không gửi duplicate payment operations thật chỉ để so sánh.

### 30.6. Production rollout

Sau khi CI pass, cần đo behavior trên runtime/image mới và có rollback plan. Regression testing không kết thúc ở biên compiler.

## 31. Quy trình phân loại và phê duyệt khác biệt

### Bước 1 — Chốt hợp đồng

Xác định strict invariants, wire API, những field động, error codes, data side effects và performance guardrails.

### Bước 2 — Tạo baseline

Lưu outputs của JDK cũ, input fixtures, database seed, Java/dependency versions và environment metadata.

### Bước 3 — Kiểm soát non-determinism

Inject Clock/ID generator, stub external systems, reset database, chọn explicit ordering và cố định feature flags.

### Bước 4 — Chạy candidate

Sử dụng JDK, framework, container, OS/architecture đúng target. Thu responses, database, events và metrics.

### Bước 5 — Validate schema

Bắt các thay đổi field name/type, missing/null, enum và required/optional trước normalization.

### Bước 6 — So sánh theo domain

Áp exact, structural, sequence/multiset, numerical/time tolerance hoặc relational invariants phù hợp.

### Bước 7 — Áp approved rules

Chỉ áp rule hiện hành, đúng scope và constraints. Ghi raw diff, rule ID và kết quả validation.

### Bước 8 — Triage bất thường

Phân loại regression, intentional change, known defect, flaky test, infrastructure failure hoặc unresolved. Không tự gộp unresolved thành allowed.

### Bước 9 — Review và cập nhật golden fixtures

Chỉ cập nhật baseline sau khi reviewer hiểu diff và quyết định. Thêm negative tests chứng minh comparator không trở nên quá lỏng.

### Bước 10 — Canary và rollback readiness

Theo dõi error rates, SLO, data integrity, security và native/runtime failures. Nếu phát hiện sai khác nghiêm trọng, rollback theo quy trình đã thiết kế.

## 32. Ví dụ tổng hợp: nâng Java 11 lên Java 21

Một order service có các khác biệt:

| Output | V1 | V2 | Đánh giá |
|---|---|---|---|
| JSON field order | id trước status | status trước id | Có thể semantic-equivalent |
| traceId | UUID A | UUID B | Có thể allowed nếu đúng format/correlation |
| total | 100.00 | 100.01 | Fail, kiểm tra rounding |
| processedAt | T0 | T0+1s | Dùng Clock hoặc bounded policy |
| items array | A, B | B, A | Fail nếu ordered contract |
| Error code | INVALID_AMOUNT | BAD_REQUEST | Xem client contract |
| TLS legacy | Success | Rejected | Security policy review |
| GC log | Legacy syntax | Unified Logging | Parser/observability validation |
| p99 latency | 180 ms | 185 ms | Đánh giá phân phối/SLO |
| Outbox events | 1 | 2 | Regression nếu duplicate side effects |

Một báo cáo tốt không chỉ ghi “có 10 diffs”. Nó phải phân loại từng diff theo semantic, contract, risk và quyết định.

### 32.1. Ví dụ quyết định

~~~text
Approved:
  JSON object property order
  Diagnostic traceId values

Requires investigation:
  Monetary rounding
  Array ordering
  Duplicate event

Requires product/security decision:
  Legacy TLS endpoint rejection

Requires performance analysis:
  p99 latency trend under comparable workload

Requires tooling migration:
  GC log parser for Unified Logging
~~~

## 33. Checklist thiết kế phép so sánh

- [ ] Đã xác định contract độc lập, không chỉ snapshot của bản cũ.
- [ ] Đã phân biệt raw bytes, structure và semantic facts.
- [ ] Đã kiểm tra response và side effects.
- [ ] Đã validate schema trước normalization.
- [ ] Đã phân biệt JSON object và array ordering.
- [ ] Đã phân biệt sequence, set và multiset.
- [ ] Đã phân biệt missing/null/empty/zero.
- [ ] Đã xác định rounding/precision cho mỗi miền số.
- [ ] Đã kiểm soát Clock/timezone.
- [ ] Đã kiểm soát random IDs và correlation.
- [ ] Đã có fixture dữ liệu lịch sử.
- [ ] Đã kiểm tra locale/charset/Unicode.
- [ ] Đã kiểm tra idempotency và concurrency.
- [ ] Đã giữ security invariants nghiêm ngặt.
- [ ] Đã phân biệt allowed difference với known defect.
- [ ] Đã gắn rule ID, scope, owner, expiry.
- [ ] Đã có negative tests cho normalization.
- [ ] Đã bảo vệ dữ liệu production/PII trong fixtures.
- [ ] Đã lưu raw diff và normalized diff.
- [ ] Đã có trạng thái inconclusive.
- [ ] Đã test trên runtime/container target.
- [ ] Đã thiết kế canary và rollback guardrails.

## 34. Mẫu hồ sơ một khác biệt được cho phép

~~~text
RULE
  Rule ID:
  Status: PROPOSED / APPROVED / EXPIRED
  Owner:
  Reviewer:
  Created:
  Review date:

SCOPE
  Service:
  Endpoint/event:
  Schema/contract version:
  Input fixtures:
  JSON path / DB column:
  Old JDK:
  New JDK:
  Framework/library versions:

DIFFERENCE
  Previous behavior:
  New behavior:
  Kind: structural / semantic / performance
  Allowed transformation:
  Allowed bound:
  Preconditions:
  Cases that must fail:

JUSTIFICATION
  Business requirement:
  Technical cause:
  Consumer impact:
  Security impact:
  Evidence/ticket:

VALIDATION
  Raw output:
  Normalized output:
  Positive tests:
  Negative tests:
  Old/new integration tests:
  Replay tests:
  Performance evidence:

DECISION
  Approved:
  Release impact:
  Rollback condition:
  Expiration/removal milestone:
~~~

Mẫu này giúp một rule không biến thành ngoại lệ vĩnh viễn không ai biết lý do.

## 35. Tổng kết

So sánh kết quả khi nâng Java không chỉ là thực hiện text diff. Đó là quá trình thiết lập **hợp đồng hành vi**, xây **test oracle**, kiểm soát input và môi trường, so sánh theo **ngữ nghĩa nghiệp vụ**, rồi quản lý những khác biệt có chủ đích bằng bằng chứng và phê duyệt.

Các nguyên tắc quan trọng:

1. **So theo contract, không chỉ theo text.** Những khác biệt biểu diễn vô hại có thể được chuẩn hóa, nhưng field names, types và business facts vẫn phải đúng.
2. **Không normalization quá rộng.** Mọi rule phải có scope, constraints, owner, review date và negative tests.
3. **Giảm diff giả từ Clock, randomness và môi trường** trước khi nới tolerance.
4. **Giữ strict cho tiền, dữ liệu và bảo mật.** Không bỏ qua lỗi vì tỉ lệ pass tổng thể cao.
5. **Kiểm tra cả side effects.** Database, events, transactions và idempotency có thể hỏng dù HTTP body giống nhau.
6. **Kết hợp differential tests với independent invariants.** Phiên bản cũ có thể có bug; không coi nó là chân lý duy nhất.
7. **Phân biệt intentional change và known defect.** Một lỗi đã biết không tự trở thành output hợp lệ.
8. **Đánh giá performance bằng phân phối và workload tương đương.** Một lần đo riêng lẻ không đủ.
9. **Lưu raw diff, normalized diff và quyết định.** Có thể kiểm toán lại những gì comparator đã bỏ qua.
10. **Kiểm chứng đến runtime production.** CI, integration, canary, metrics và rollback là các phần của cùng một migration.

Một migration được kiểm thử tốt không đòi mọi byte đầu ra trước và sau khi nâng JDK đều giống nhau. Nó đòi mọi **khác biệt có ý nghĩa** đều được nhìn thấy, giải thích bằng hợp đồng và bằng chứng, được phê duyệt có điều kiện rõ ràng hoặc bị chặn để sửa trước khi gây hỏng dữ liệu và hành vi của hệ thống.

