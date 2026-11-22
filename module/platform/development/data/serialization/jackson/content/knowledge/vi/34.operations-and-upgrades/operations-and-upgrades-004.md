# Bảo vệ thông tin nhạy cảm trong dữ liệu lỗi được lưu mẫu

Khi một request JSON không thể deserialize hoặc xử lý nghiệp vụ thất bại, đội phát triển thường muốn lưu một mẫu dữ liệu để tái hiện lỗi. Mẫu này có thể giúp tìm ra field sai định dạng, payload gây lỗi hoặc khác biệt giữa các phiên bản client. Tuy nhiên, request thực tế thường chứa thông tin cá nhân, thông tin tài khoản, token truy cập, cookie, dữ liệu thanh toán hoặc bí mật tích hợp. Nếu lưu nguyên payload vào log, file lỗi, dead-letter queue hay hệ thống theo dõi lỗi, ứng dụng có thể vô tình tạo thêm một nơi lưu trữ dữ liệu nhạy cảm với quyền truy cập và thời hạn lưu giữ kém chặt chẽ hơn hệ thống chính.

Với Jackson, có thể đọc JSON thành `JsonNode`, tạo một bản sao đã che dữ liệu nhạy cảm rồi mới lưu mẫu phục vụ chẩn đoán. Nhưng việc che theo tên field chỉ là một lớp bảo vệ: secret có thể nằm trong field tên lạ, chuỗi tự do, URL, message hoặc dữ liệu lồng sâu. Vì vậy, thiết kế an toàn nên ưu tiên **allowlist các field thực sự cần cho chẩn đoán**, giới hạn kích thước mẫu, bỏ qua payload không parse được thay vì lưu raw fragment, và chỉ lưu metadata lỗi đã được kiểm soát.

## 1. Vì sao mẫu lỗi có thể trở thành nơi rò rỉ dữ liệu?

Một ứng dụng có thể lưu request thất bại ở nhiều vị trí:

- Log ứng dụng khi bắt `JsonProcessingException`.
- File tạm hoặc thư mục quarantine để kỹ sư tái hiện lỗi.
- Dead-letter queue (DLQ) của message broker.
- Bảng database lưu request thất bại.
- Hệ thống APM, error tracking hoặc tracing.
- Báo cáo lỗi tự động và attachment trong ticket.
- Bộ fixture/test data được copy từ production.

Nếu tất cả các vị trí trên đều nhận raw JSON, dữ liệu nhạy cảm sẽ bị nhân bản. Một access token xuất hiện trong request có thể tiếp tục tồn tại trong log nhiều tháng, được sao lưu, lập chỉ mục và hiển thị cho nhiều nhóm người dùng hơn quyền truy cập dữ liệu nghiệp vụ ban đầu.

Ví dụ payload:

```json
{
  "requestId": "REQ-1001",
  "customer": {
    "name": "Nguyen Van An",
    "email": "an@example.com",
    "phone": "+84900000000"
  },
  "authorization": "Bearer eyJhbGciOi...",
  "payment": {
    "cardNumber": "4111111111111111",
    "cvv": "123",
    "amount": 1250000
  }
}
```

Đối với chẩn đoán lỗi mapping, kỹ sư có thể chỉ cần biết:

- Request có field `customer`, `authorization` và `payment`.
- `payment.amount` là number.
- `payment.cardNumber` có mặt nhưng đã được che.
- Parser lỗi ở một vị trí cụ thể hoặc `payment.amount` không chuyển được sang kiểu đích.

Họ thường không cần biết tên thật, email, số điện thoại, token hay số thẻ. Mẫu lỗi nên giữ đủ cấu trúc để tái hiện loại lỗi, đồng thời loại bỏ giá trị không cần thiết.

## 2. Nguyên tắc: giảm dữ liệu trước khi lưu

Một chính sách lưu mẫu lỗi an toàn nên theo thứ tự ưu tiên:

1. **Không lưu raw payload theo mặc định.** Chỉ lưu mã lỗi, loại exception, request correlation id và vị trí lỗi nếu các metadata đó đủ để điều tra.
2. **Chỉ lưu phần dữ liệu cần thiết.** Nếu cần một mẫu JSON, chỉ giữ các field nằm trong allowlist phục vụ tái hiện lỗi.
3. **Che trước khi ghi.** Redaction phải hoàn tất trước khi gọi logger, database, queue hoặc file writer.
4. **Giới hạn kích thước và độ sâu.** Mẫu lỗi không được trở thành một bản sao vô hạn của request lớn.
5. **Giới hạn quyền và thời gian lưu.** Mẫu lỗi cần quyền truy cập hẹp, audit và retention ngắn.
6. **Dùng dữ liệu tổng hợp khi có thể.** Một fixture synthetic thường tái hiện lỗi mà không cần dữ liệu production.

Redaction là một biện pháp giảm rủi ro, không phải giấy phép để lưu mọi dữ liệu. Nếu không thể xác định chắc chắn giá trị nào an toàn, hãy bỏ giá trị đó hoặc bỏ toàn bộ mẫu.

## 3. Phân biệt dữ liệu nhạy cảm và dữ liệu cần chẩn đoán

Những trường thường cần che hoặc loại khỏi mẫu gồm:

| Nhóm | Ví dụ tên field hoặc dữ liệu | Cách xử lý mặc định |
| --- | --- | --- |
| Xác thực | `password`, `accessToken`, `refreshToken`, `authorization`, `cookie` | Loại bỏ hoặc thay bằng marker |
| Bí mật tích hợp | `apiKey`, `clientSecret`, `privateKey`, `credential` | Loại bỏ hoàn toàn |
| Thanh toán | `cardNumber`, `cvv`, `cvc`, `iban`, `bankAccount` | Loại bỏ; chỉ giữ trạng thái/loại nếu cần |
| Định danh cá nhân | `ssn`, `passport`, `taxId`, số giấy tờ | Loại bỏ hoặc token hóa theo chính sách |
| Thông tin liên hệ | `email`, `phone`, `address`, ngày sinh | Che hoặc thay bằng dữ liệu tổng hợp |
| Dữ liệu sức khỏe | Mã hồ sơ, chẩn đoán, kết quả xét nghiệm | Loại bỏ khỏi log chẩn đoán thông thường |
| Nội dung tự do | `message`, `description`, `notes`, comment | Không mặc định coi là an toàn; có thể chứa secret/PII |
| Định danh nội bộ | user id, tenant id, order id | Cân nhắc pseudonymization hoặc chỉ giữ khi cần |

Không chỉ dựa vào tên field. Ví dụ `metadata`, `payload`, `value`, `data` hoặc `extra` có thể chứa một JSON object khác hoặc chuỗi tự do chứa token. Một trường tên `note` có thể vô tình chứa thông tin thẻ hoặc mật khẩu do người dùng dán vào.

Vì vậy, denylist tên field là lớp bảo vệ hữu ích nhưng không đủ cho dữ liệu có mức nhạy cảm cao. Allowlist có nghĩa là chỉ ghi những field đã được xác nhận an toàn; các field còn lại bị loại hoặc che.

## 4. Chọn chiến lược redaction phù hợp

Có một số chiến lược thường dùng:

| Chiến lược | Cách làm | Ưu điểm | Hạn chế |
| --- | --- | --- | --- |
| Drop field | Bỏ hẳn property nhạy cảm | Không lưu lại giá trị gốc hoặc độ dài của nó | Có thể khó biết field có tồn tại hay không |
| Replace marker | Thay bằng `"[REDACTED]"` | Giữ cấu trúc và cho biết field có mặt | Marker làm thay đổi kiểu JSON ban đầu |
| Mask một phần | Ví dụ chỉ giữ bốn ký tự cuối | Hữu ích khi cần đối chiếu định danh | Vẫn có thể nhận diện; không phù hợp cho mọi loại secret |
| Tokenization | Thay giá trị bằng token giả ổn định | Có thể liên kết nhiều mẫu mà không lộ giá trị gốc | Cần quản lý token mapping và chống tái nhận diện |
| Synthetic replacement | Thay bằng dữ liệu giả cùng kiểu/định dạng | Tốt cho tái hiện mapping và test | Phải tránh tạo giá trị giả vô tình trùng dữ liệu thật |
| Allowlist | Chỉ giữ field đã được phê duyệt | Giảm rủi ro từ field lạ | Cần duy trì schema và danh sách field |

Với access token, password, CVV và private key, nên drop hoặc thay marker toàn bộ; không nên giữ vài ký tự cuối vì giá trị vẫn là bí mật xác thực. Với email hoặc số điện thoại, có thể dùng dữ liệu synthetic hoặc pseudonymization nếu cần liên kết các mẫu, nhưng phải đánh giá nguy cơ nhận diện lại.

## 5. Che dữ liệu JSON hợp lệ bằng JsonNode

Nếu request là JSON hợp lệ, Tree Model giúp duyệt object/array và tạo một cây đã redaction trước khi serialize thành mẫu lỗi.

Ví dụ hàm che theo tên field:

```java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.JsonNodeFactory;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.util.Iterator;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

public final class JsonRedactor {
    private static final Set<String> SENSITIVE_PARTS = Set.of(
            "password", "passwd", "secret", "token", "apikey",
            "authorization", "cookie", "privatekey", "credential",
            "cvv", "cvc", "cardnumber", "bankaccount", "iban",
            "ssn", "passport", "taxid", "email", "phone",
            "address", "dateofbirth", "birthdate", "otp"
    );

    private JsonRedactor() {
    }

    private static String canonicalName(String name) {
        return name.replaceAll("[^A-Za-z0-9]", "")
                .toLowerCase(Locale.ROOT);
    }

    private static boolean isSensitiveName(String name) {
        String canonical = canonicalName(name);
        return SENSITIVE_PARTS.stream().anyMatch(canonical::contains);
    }

    public static JsonNode redact(JsonNode input) {
        if (input == null || input.isValueNode()) {
            return input == null ? JsonNodeFactory.instance.nullNode() : input.deepCopy();
        }

        if (input.isObject()) {
            ObjectNode output = JsonNodeFactory.instance.objectNode();
            Iterator<Map.Entry<String, JsonNode>> fields = input.fields();

            while (fields.hasNext()) {
                Map.Entry<String, JsonNode> field = fields.next();
                if (isSensitiveName(field.getKey())) {
                    output.put(field.getKey(), "[REDACTED]");
                } else {
                    output.set(field.getKey(), redact(field.getValue()));
                }
            }
            return output;
        }

        if (input.isArray()) {
            ArrayNode output = JsonNodeFactory.instance.arrayNode();
            for (JsonNode element : input) {
                output.add(redact(element));
            }
            return output;
        }

        return input.deepCopy();
    }
}
```

Hàm này:

- Duyệt đệ quy object và array.
- Chuẩn hóa tên field để nhận ra một số biến thể như `access_token`, `accessToken` hoặc `ACCESS-TOKEN`.
- Thay value của field nhạy cảm bằng marker.
- Giữ các scalar khác bằng bản sao node.

Đây là ví dụ denylist để minh họa kỹ thuật, không phải bộ nhận diện bí mật hoàn chỉnh. Nó không phát hiện token nằm trong field `comment`, URL, chuỗi tự do, nội dung Base64 hoặc một field có tên không dự đoán được. Với hệ thống lưu mẫu lỗi production, nên bổ sung allowlist theo schema và quy tắc kiểm tra nội dung.

## 6. Allowlist an toàn hơn denylist

Denylist cố gắng liệt kê mọi tên nguy hiểm. Khi schema mở hoặc client có thể gửi field tùy ý, danh sách này sẽ luôn có khả năng bỏ sót.

Allowlist bắt đầu từ giả định ngược lại: không ghi field nào nếu chưa được phê duyệt. Ví dụ, mẫu lỗi cho một endpoint tạo đơn hàng có thể chỉ giữ:

```text
request.version
order.currency
order.itemCount
order.items[*].productType
order.total
```

Các field như `customer.name`, `customer.email`, `payment.cardNumber`, `authorization` và mọi field không nằm trong danh sách sẽ bị drop hoặc thay marker.

Một thiết kế allowlist nên xác định theo **đường dẫn**, không chỉ theo tên field. Ví dụ `id` có thể an toàn ở `order.items[*].id` nhưng nhạy cảm ở `customer.id` hoặc `session.id`. Tương tự, `value` ở một property có thể là số lượng, nhưng ở property khác có thể là token.

Có thể tổ chức policy theo endpoint/schema version:

```java
record SamplePolicy(
        Set<String> allowedPaths,
        Set<String> maskedPaths,
        int maxBytes,
        int maxDepth
) {
}
```

Khi duyệt cây, xây dựng path như `order.items[*].productType`, chỉ giữ giá trị nếu path được allowlist; các path còn lại được drop hoặc marker. Policy nên được version hóa cùng API schema để khi thêm field mới, field đó mặc định không xuất hiện trong mẫu lỗi cho đến khi được đánh giá.

## 7. Chỉ serialize bản đã che, không serialize cây gốc

Một lỗi triển khai thường gặp là tạo bản redacted nhưng sau đó vẫn log raw request hoặc exception chứa raw value:

```java
JsonNode safeTree = JsonRedactor.redact(mapper.readTree(rawJson));
logger.warn("Invalid request: {}", rawJson); // Sai: log dữ liệu gốc.
```

Hãy chỉ truyền bản đã che tới sink:

```java
JsonNode safeTree = JsonRedactor.redact(mapper.readTree(rawJson));
String safeSample = mapper.writeValueAsString(safeTree);

logger.warn("Request rejected; sample={}", safeSample);
```

Trong code thực tế, cần giới hạn kích thước trước khi ghi, và chỉ lưu những field nằm trong policy đã phê duyệt. Không giữ raw JSON trong biến log context, MDC, tracing baggage hoặc attachment vô tình được ghi ở một nhánh khác.

Một nguyên tắc quan trọng: redaction phải nằm trước mọi điểm lưu trữ. Không ghi raw vào log rồi mới chạy job xóa/che sau đó; bản raw đã có thể được chuyển tới collector, replica, backup hoặc hệ thống alert.

## 8. Tạo mẫu an toàn có giới hạn kích thước

Ngay cả bản đã redaction cũng có thể rất lớn. Một request chứa hàng trăm nghìn item vẫn tạo ra một mẫu khổng lồ nếu giữ toàn bộ cấu trúc.

Ví dụ helper đơn giản cho JSON hợp lệ:

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.nio.charset.StandardCharsets;

public final class SafeSampleFactory {
    private static final int MAX_SAMPLE_BYTES = 16 * 1024;

    private SafeSampleFactory() {
    }

    public static String create(String rawJson, ObjectMapper mapper) {
        if (rawJson == null || rawJson.isBlank()) {
            return null;
        }

        try {
            JsonNode input = mapper.reader()
                    .with(DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
                    .readTree(rawJson);

            JsonNode redacted = JsonRedactor.redact(input);
            byte[] safeBytes = mapper.writeValueAsBytes(redacted);

            if (safeBytes.length > MAX_SAMPLE_BYTES) {
                return "{\"sampleStatus\":\"OMITTED_TOO_LARGE\"}";
            }

            return new String(safeBytes, StandardCharsets.UTF_8);
        } catch (JsonProcessingException exception) {
            // Không lưu rawJson hoặc exception.getMessage() ở nhánh này.
            return "{\"sampleStatus\":\"OMITTED_INVALID_JSON\"}";
        }
    }
}
```

Ví dụ trả về một marker JSON hợp lệ thay vì cắt chuỗi JSON giữa chừng. Nếu mẫu quá lớn, không nên dùng `substring()` trên chuỗi JSON vì có thể tạo một fragment không hợp lệ và vô tình cắt đúng vào vùng chứa dữ liệu nhạy cảm.

Đoạn code minh họa có một số giới hạn cần xử lý thêm trong production:

- Giới hạn kích thước raw body trước khi parse, vì `rawJson` đã nằm trong bộ nhớ.
- Cấu hình `StreamReadConstraints` để giới hạn nesting depth, string và number.
- Thay denylist bằng policy allowlist phù hợp với endpoint.
- Giới hạn số phần tử/field khi cần, vì giới hạn byte đầu ra được kiểm tra sau khi cây đã được tạo.
- Cân nhắc không tạo mẫu nếu payload quá lớn hoặc không có giá trị chẩn đoán.

## 9. Không lưu raw fragment khi JSON không parse được

Đây là trường hợp cần chú ý nhất. Nếu JSON sai cú pháp hoặc bị cắt dở, `readTree()` có thể ném `JsonProcessingException` trước khi tạo được cây hoàn chỉnh. Không thể giả định rằng ta đã có một `JsonNode` an toàn để redaction.

Ví dụ:

```json
{
  "username": "an",
  "password": "secret-value",
  "profile": {
```

Nếu parser gặp EOF ở giữa object, nhánh catch có thể bị cám dỗ lưu `rawJson.substring(0, 500)` để xem phần đầu. Cách này nguy hiểm vì 500 ký tự đầu có thể chứa password hoặc token nguyên vẹn.

Đối với input không parse được, mặc định chỉ lưu metadata:

```json
{
  "sampleStatus": "OMITTED_INVALID_JSON",
  "errorCode": "JSON_PARSE_ERROR",
  "line": 4,
  "column": 18
}
```

Nếu cần tái hiện lỗi cú pháp, hãy tạo fixture synthetic từ schema và vị trí lỗi, ví dụ một object thiếu dấu ngoặc nhưng dùng dữ liệu giả. Chỉ lưu raw body trong một vùng quarantine đặc biệt nếu có lý do vận hành được phê duyệt, với encryption, quyền truy cập hạn chế, audit và thời hạn xóa ngắn.

## 10. Cẩn thận với exception message và JsonLocation

Không nên mặc định rằng `exception.getMessage()` hoặc `exception.toString()` là an toàn. Một số lỗi mapping có thể đưa giá trị đầu vào vào thông báo, ví dụ chuỗi không chuyển được sang số hoặc enum. Exception cũng có thể giữ source reference hoặc location gắn với nội dung parser.

Ví dụ log rủi ro:

```java
catch (JsonProcessingException exception) {
    logger.error("Cannot parse request: {}", exception.getMessage());
    logger.error("Full exception", exception);
}
```

Log toàn bộ exception có thể ghi cả message, cause và stack trace. Tùy loại exception và cấu hình Jackson, thông tin nguồn hoặc một phần dữ liệu đầu vào có thể xuất hiện.

Thay vào đó, log metadata đã chọn:

```java
catch (JsonProcessingException exception) {
    JsonLocation location = exception.getLocation();

    logger.warn(
            "Request JSON rejected; errorType={}, line={}, column={}, requestId={}",
            exception.getClass().getSimpleName(),
            location == null ? null : location.getLineNr(),
            location == null ? null : location.getColumnNr(),
            requestId
    );
}
```

Không gọi `location.toString()` nếu không cần, vì biểu diễn location có thể chứa mô tả nguồn. Chỉ lấy line/column/offset cần thiết.

Với `JsonMappingException`, `getPathReference()` có thể giúp xác định property gây lỗi. Tuy nhiên, path đôi khi có tên key do người dùng cung cấp trong map động; hãy xem xét che hoặc giới hạn path trước khi log. Không đưa invalid value vào log chỉ để giúp debug.

## 11. Tắt source inclusion trong parser location khi phù hợp

Các phiên bản Jackson Core hỗ trợ `StreamReadFeature.INCLUDE_SOURCE_IN_LOCATION` cho phép kiểm soát việc source reference có được đưa vào thông tin location hay không. Với dữ liệu đầu vào nhạy cảm, có thể tắt tính năng này trong `JsonFactory`:

```java
JsonFactory factory = JsonFactory.builder()
        .disable(StreamReadFeature.INCLUDE_SOURCE_IN_LOCATION)
        .build();

ObjectMapper mapper = new ObjectMapper(factory);
```

Khi tắt, location không giữ/hiển thị source reference theo cách mặc định của feature. Điều này giúp giảm nguy cơ một thông báo lỗi hoặc location vô tình chứa nội dung nguồn.

Hãy xác nhận feature có trong phiên bản `jackson-core` của dự án. Dù đã tắt source inclusion, ứng dụng vẫn phải tránh log raw request, exception message chứa invalid value hoặc dữ liệu được giữ riêng trong biến khác. Đây là một lớp bảo vệ bổ sung, không thay thế redaction và chính sách log.

## 12. Redaction theo đường dẫn thay vì chỉ tên field

Một field có thể an toàn ở ngữ cảnh này nhưng nhạy cảm ở ngữ cảnh khác. Ví dụ:

```json
{
  "order": {"id": "ORD-1001"},
  "customer": {"id": "CUST-9001"}
}
```

Có thể cần giữ `order.id` để đối chiếu lỗi nhưng che `customer.id`. Một policy dựa trên path có thể biểu diễn:

```text
Allowed:
  order.id
  order.currency
  order.itemCount

Masked:
  customer.id
  customer.email
  customer.phone
  payment.cardNumber
  payment.authorization
```

Với array, dùng wildcard path như `order.items[*].productCode`. Không nên dùng index cụ thể nếu muốn policy áp dụng cho mọi phần tử.

Nếu payload có dynamic key, ví dụ map chứa email làm key hoặc tên khách hàng làm key, chính key cũng có thể là dữ liệu nhạy cảm. Khi đó, cần redaction cả field name hoặc thay toàn bộ map bằng marker/summary; chỉ che value là chưa đủ.

## 13. Masking một phần có thể vẫn tiết lộ danh tính

Masking thường được dùng để giữ một phần dữ liệu giúp nhận diện bản ghi:

```text
email: a***@example.com
phone: ******0000
card: ************1111
```

Nhưng masking không đồng nghĩa với anonymization. Nếu người xem có thêm thông tin bên ngoài, vài ký tự còn lại có thể đủ để nhận diện người hoặc tài khoản. Một số giá trị có không gian tìm kiếm nhỏ, dễ bị dò bằng brute force.

Đối với secret xác thực như password, bearer token, refresh token, API key, CVV và private key, không nên giữ một phần. Hãy thay toàn bộ bằng marker hoặc loại bỏ.

Với định danh cần liên kết nhiều lỗi, cân nhắc pseudonymization bằng HMAC với khóa bí mật được quản lý riêng:

```text
customerId = HMAC-SHA-256(logKey, originalCustomerId)
```

Không dùng hash thuần cho giá trị có không gian nhỏ như số điện thoại hoặc mã ngắn; kẻ tấn công có thể thử toàn bộ khả năng. HMAC có khóa bí mật giúp giảm nguy cơ dò ngược, nhưng token ổn định vẫn là dữ liệu có thể liên kết và cần kiểm soát quyền truy cập.

## 14. Không chỉ JSON: dữ liệu nhạy cảm có thể nằm trong message, URL và header

Request lỗi không chỉ có body. Hệ thống logging thường ghi thêm:

- Request URL có query parameter chứa token hoặc email.
- HTTP header `Authorization`, `Cookie`, `Set-Cookie`.
- Query string như `?access_token=...`.
- Exception message do thư viện bên thứ ba tạo.
- Header hoặc metadata message broker.
- Trace span attributes và baggage.
- File name hoặc path có thông tin người dùng.

Redaction cho `JsonNode` chỉ bảo vệ phần JSON tree được xử lý. Nó không tự động che HTTP headers, URL, form data, multipart file name hoặc trace attributes.

Hãy áp dụng chính sách redaction riêng cho từng kênh log. Đối với header, dùng allowlist các header an toàn thay vì ghi tất cả header rồi cố gắng liệt kê header nhạy cảm. Đối với URL, loại query parameter hoặc chỉ giữ route template, không ghi raw query string nếu không cần.

## 15. Dead-letter queue và quarantine storage

DLQ thường được dùng để giữ message không xử lý được nhằm retry hoặc điều tra. Nếu message chứa dữ liệu nhạy cảm, DLQ là một kho dữ liệu production khác và phải được bảo vệ tương đương hoặc chặt hơn kho chính.

Một chính sách nên quy định:

- Có cần lưu raw message hay chỉ cần bản redacted?
- Nếu cần raw để replay, ai được phép đọc và trong trường hợp nào?
- Raw message có được mã hóa khi truyền và khi lưu không?
- Encryption key được quản lý và luân chuyển thế nào?
- Message được giữ bao lâu trước khi tự động xóa?
- Có audit cho thao tác đọc, export và replay không?
- Khi replay, secret có còn hiệu lực không; có cần revoke/rotate không?
- DLQ có được sao chép sang môi trường dev/test không?

Không nên dùng DLQ như một kho lưu trữ lâu dài không có retention. Nếu mục đích chỉ là chẩn đoán lỗi, bản redacted thường đủ. Nếu mục đích là replay chính xác, raw message cần quy trình truy cập đặc biệt và thời hạn lưu ngắn.

## 16. Mã hóa, quyền truy cập và retention

Redaction không phải lớp bảo vệ duy nhất. Mẫu lỗi sau khi che vẫn có thể chứa định danh, dữ liệu nghiệp vụ hoặc thông tin có thể liên kết với người dùng.

Các biện pháp vận hành:

1. **Encryption at rest:** mã hóa file, database, object storage và queue theo chính sách nền tảng.
2. **Encryption in transit:** dùng TLS cho đường truyền giữa ứng dụng, log collector, broker và storage.
3. **Least privilege:** chỉ cấp quyền đọc mẫu lỗi cho nhóm thực sự cần.
4. **Audit:** ghi lại ai xem, export, replay hoặc xóa mẫu.
5. **Retention:** đặt TTL tự động; xóa cả bản sao, index và backup theo chính sách phù hợp.
6. **Environment separation:** không copy raw production payload vào laptop, CI, sandbox hoặc môi trường dev.
7. **Key management:** không lưu encryption key hoặc HMAC key trong cùng nơi với dữ liệu.
8. **Incident response:** có quy trình xử lý khi phát hiện secret đã bị ghi vào log.

Nếu một access token đã xuất hiện trong log, xóa log không đảm bảo token chưa bị sao chép. Hãy xem xét revoke/rotate token và xử lý các bản sao theo quy trình bảo mật.

## 17. Thiết kế ErrorSample chỉ chứa metadata an toàn

Thay vì lưu một object tùy ý chứa toàn bộ request và exception, hãy tạo kiểu dữ liệu riêng cho mẫu lỗi:

```java
public record ErrorSample(
        String requestId,
        String errorCode,
        String exceptionType,
        Integer line,
        Integer column,
        String propertyPath,
        String sanitizedPayload,
        String sampleStatus
) {
}
```

Các field nên có ý nghĩa rõ:

- `requestId`: correlation id do server tạo hoặc đã được xác thực/chuẩn hóa.
- `errorCode`: mã lỗi nội bộ ổn định, không chứa input.
- `exceptionType`: chỉ tên lớp exception, không phải toàn bộ message.
- `line`, `column`: vị trí parser nếu có.
- `propertyPath`: path đã được kiểm tra/che.
- `sanitizedPayload`: chỉ bản JSON đã qua allowlist/redaction và giới hạn kích thước.
- `sampleStatus`: `STORED`, `OMITTED_INVALID_JSON`, `OMITTED_TOO_LARGE` hoặc trạng thái tương tự.

Không đưa `rawPayload`, `exceptionMessage` hoặc `stackTrace` vào record này nếu không có yêu cầu vận hành đặc biệt. Nếu cần stack trace, lưu trong hệ thống error tracking với chính sách scrub riêng.

## 18. Một luồng xử lý lỗi an toàn

Một pipeline mẫu:

```text
HTTP/message input
       │
       ▼
Enforce body/decompression limits
       │
       ▼
Jackson parse + deserialize
       │
       ├── Thành công ──> validation/domain processing
       │
       └── Thất bại
              │
              ▼
       Collect safe metadata
       (error code, type, line/column)
              │
              ▼
       Is input valid JSON?
          │             │
         Yes            No
          │             │
          ▼             ▼
   Apply allowlist/    Omit raw sample;
   redaction policy    keep metadata only
          │             │
          └──────┬──────┘
                 ▼
        Enforce sample size/TTL
                 │
                 ▼
       Store in restricted sink
```

Điểm quan trọng là mọi nhánh đều đi qua cùng chính sách trước khi lưu. Không để một nhánh catch riêng ghi raw body trong khi nhánh khác đã redaction.

## 19. Ví dụ xử lý exception mà không lưu dữ liệu gốc

```java
public ErrorSample handleJsonFailure(
        String requestId,
        String rawJson,
        JsonProcessingException exception,
        ObjectMapper mapper
) {
    JsonLocation location = exception.getLocation();

    String safeSample = SafeSampleFactory.create(rawJson, mapper);
    String status = safeSample == null
            ? "OMITTED_EMPTY"
            : safeSample.contains("OMITTED_")
                    ? "OMITTED"
                    : "STORED";

    String safePath = null;
    if (exception instanceof JsonMappingException mappingException) {
        // Trong hệ thống thực tế, cần scrub/allowlist path trước khi lưu.
        safePath = sanitizePropertyPath(mappingException.getPathReference());
    }

    return new ErrorSample(
            requestId,
            classifyError(exception),
            exception.getClass().getSimpleName(),
            location == null ? null : location.getLineNr(),
            location == null ? null : location.getColumnNr(),
            safePath,
            safeSample,
            status
    );
}
```

Các hàm `sanitizePropertyPath()` và `classifyError()` cần trả về giá trị đã kiểm soát, không copy message đầu vào. Ví dụ `classifyError()` có thể ánh xạ exception type thành `JSON_SYNTAX_ERROR`, `JSON_MAPPING_ERROR` hoặc `INVALID_FORMAT`, thay vì lưu `exception.getMessage()`.

Đây là khung minh họa; trong production, nên dùng một kiểu kết quả riêng cho `SafeSampleFactory` thay vì kiểm tra chuỗi marker bằng `contains()`. Mục tiêu là để trạng thái lưu mẫu tường minh và tránh việc một payload hợp lệ có nội dung chứa chữ `OMITTED_` bị hiểu sai.

## 20. Mẫu lỗi cho JSON không hợp lệ: chỉ giữ metadata hoặc synthetic fixture

Nếu parser thất bại trước khi tạo được cây, không có cách an toàn tổng quát để lấy một đoạn raw rồi che bằng tên field. Một đoạn text có thể cắt ngang giữa key/value hoặc chứa token bí mật mà không có cấu trúc đủ để nhận diện.

Hai hướng an toàn:

### 20.1. Metadata-only

Lưu:

```json
{
  "requestId": "REQ-1001",
  "errorCode": "JSON_UNEXPECTED_EOF",
  "exceptionType": "JsonEOFException",
  "line": 12,
  "column": 4,
  "sampleStatus": "OMITTED_INVALID_JSON"
}
```

### 20.2. Synthetic reproduction

Tạo một fixture mới với cấu trúc tương tự nhưng dữ liệu giả:

```json
{
  "customer": {
    "name": "Synthetic User",
    "email": "user@example.invalid"
  },
  "items": [
    {"quantity": "NOT_A_NUMBER"}
  ]
```

Fixture trên cố ý thiếu dấu đóng để tái hiện unexpected EOF; các giá trị là dữ liệu giả. Không copy prefix raw của request production vào fixture.

## 21. Tránh rò rỉ qua log framework và tracing

Ngay cả khi code xử lý lỗi không log raw payload, framework có thể ghi request body hoặc exception qua filter/interceptor/APM agent. Cần kiểm tra:

- HTTP request/response logging filter có ghi body không.
- Spring `CommonsRequestLoggingFilter` hoặc middleware tương tự có include payload không.
- APM agent có capture request body, headers hoặc exception local variables không.
- OpenTelemetry span có gắn `http.request.body` hoặc custom attributes không.
- Error tracker có gửi local variables, breadcrumbs hoặc attachment không.
- Message listener có log toàn bộ message khi retry thất bại không.

Đặt scrubber/allowlist ở nơi capture dữ liệu, không chỉ trong catch block của controller. Với tracing, chỉ ghi route template, method, status và correlation id; không đưa body hoặc credential vào span attributes trừ khi có chính sách rõ ràng.

## 22. Kiểm soát mẫu trong môi trường phát triển và CI

Mẫu lỗi production thường được copy vào issue, pull request, chat hoặc test fixture để tái hiện bug. Hãy coi mọi lần export là một lần chia sẻ dữ liệu mới:

- Dùng synthetic fixture trước.
- Kiểm tra fixture không còn email, số điện thoại, token, cookie hoặc định danh thật.
- Không lưu secret trong repository, kể cả file test private.
- Dùng secret scanner trong CI để phát hiện credential bị commit nhầm.
- Không đưa raw payload vào snapshot test nếu snapshot có thể được xem bởi người không có quyền production.
- Nếu cần test định dạng thật, tạo dữ liệu giả cùng shape và kiểu JSON.
- Xóa attachment/ticket export theo retention policy.

Một mẫu đã redaction vẫn cần được xem xét trước khi commit. Redaction theo field name có thể bỏ sót secret nằm trong text tự do hoặc field mới.

## 23. Quyền truy cập và audit cho mẫu lỗi

Không phải mọi kỹ sư đều cần quyền đọc mọi payload lỗi. Có thể chia lớp truy cập:

| Vai trò | Quyền phù hợp |
| --- | --- |
| On-call vận hành | Xem error code, timestamp, location và mẫu đã redaction |
| Developer của service | Xem mẫu đã redaction thuộc service được phân công |
| Security/privacy team | Điều tra yêu cầu đặc biệt theo quy trình có audit |
| Administrator storage | Quản lý hệ thống/backup; không mặc định có quyền đọc nội dung |
| Automated replay worker | Chỉ đọc queue/topic cần thiết và chỉ trong thời gian xử lý |

Audit nên ghi ai đọc/export/replay/xóa, thời điểm, mục đích và mã ticket nếu quy trình yêu cầu. Không log nội dung mẫu trong chính audit record.

## 24. Khi nào cần giữ raw payload để replay?

Đôi khi cần raw message để replay chính xác, ví dụ lỗi phụ thuộc vào byte encoding, signature, thứ tự field hoặc dữ liệu gây lỗi parser. Nhưng đây là ngoại lệ vận hành cần đánh giá riêng.

Nếu bắt buộc giữ raw:

1. Chỉ lưu trong quarantine storage chuyên biệt, không ghi vào log thường.
2. Mã hóa khi truyền và khi lưu; quản lý key riêng.
3. Giới hạn người được phép truy cập, yêu cầu phê duyệt hoặc break-glass nếu cần.
4. Audit mọi lần đọc/export/replay.
5. Đặt TTL ngắn và tự động xóa; kiểm tra cả backup/replica.
6. Không copy sang dev/test; nếu cần tái hiện, tạo bản synthetic hoặc redacted.
7. Revoke/rotate secret có nguy cơ đã bị lộ trong payload.

Nếu không có các biện pháp này, chỉ lưu metadata và bản redacted. Khả năng replay không nên tự động được ưu tiên hơn việc giảm rủi ro dữ liệu.

## 25. Những lỗi thiết kế thường gặp

| Cách làm | Rủi ro | Cách thay thế |
| --- | --- | --- |
| Log toàn bộ `rawJson` trong catch | Lộ PII/secret khi deserialize thất bại | Chỉ log metadata và safe sample |
| Log `exception.getMessage()` hoặc toàn bộ exception | Message có thể chứa invalid value/source | Log exception type, mã lỗi và location đã chọn |
| Lưu 500 ký tự đầu của body lỗi | Prefix có thể chứa token/password | Bỏ raw sample khi JSON không parse được |
| Chỉ redaction `password` và `token` | Bỏ sót field alias, nested value, free text | Allowlist theo path/schema, bổ sung denylist |
| Redact sau khi đã gửi log | Raw đã tới collector/backup | Redact trước mọi sink |
| Chỉ mã hóa file | Người có quyền đọc vẫn thấy raw | Kết hợp minimization, access control, audit và TTL |
| Lưu DLQ vô thời hạn | Tạo kho dữ liệu production lâu dài | TTL, encryption, access review |
| Mask token còn bốn ký tự cuối | Secret vẫn có thể bị sử dụng hoặc dò | Redact toàn bộ credential |
| Dùng `@JsonIgnore` như giải pháp cho raw request logging | Không ngăn logger ghi raw HTTP body | Scrub ở tầng logging/capture |
| Chỉ kiểm tra mẫu bằng mắt | Secret có thể nằm ở field lạ hoặc chuỗi tự do | Automated policy + review + secret scanning |

## 26. Kiểm thử chính sách redaction

Chính sách redaction cần test như code xử lý dữ liệu, không chỉ kiểm tra bằng một payload đơn giản.

Các tình huống nên có:

- Field nhạy cảm ở root object.
- Field nhạy cảm lồng nhiều cấp.
- Field nhạy cảm bên trong array.
- Biến thể tên như `access_token`, `accessToken`, `ACCESS-TOKEN`.
- Secret nằm trong field có tên chung như `message`, `metadata` hoặc `value`.
- Map có dynamic key chứa dữ liệu nhạy cảm.
- JSON null, scalar root, array root và object rỗng.
- JSON sai cú pháp hoặc bị cắt dở: không có raw fragment được lưu.
- JSON có nhiều root token: bị từ chối nếu policy yêu cầu một document.
- Payload vượt giới hạn: sample bị bỏ với status rõ ràng.
- Exception message chứa invalid value: log output không có giá trị đó.

Một test cơ bản cho redactor:

```java
@Test
void redactsSensitiveFieldsAtEveryNestedLevel() throws Exception {
    String json = """
            {
              "name": "Synthetic User",
              "access_token": "secret-token",
              "items": [
                {"cardNumber": "4111111111111111"}
              ]
            }
            """;

    JsonNode input = mapper.readTree(json);
    JsonNode safe = JsonRedactor.redact(input);
    String output = mapper.writeValueAsString(safe);

    assertFalse(output.contains("secret-token"));
    assertFalse(output.contains("4111111111111111"));
    assertTrue(output.contains("[REDACTED]"));
}
```

Test này chỉ kiểm tra denylist minh họa. Với allowlist, cần test rằng field không được phê duyệt bị loại mặc định, kể cả khi field đó chưa từng xuất hiện trong test trước đây.

## 27. Quy trình xử lý mẫu lỗi an toàn

Một quy trình triển khai có thể gồm:

1. Đọc request dưới giới hạn byte/decompression đã cấu hình.
2. Parse và bind bằng `ObjectMapper` có `StreamReadConstraints` phù hợp.
3. Khi lỗi, phân loại exception mà không log raw message.
4. Lấy metadata an toàn như request id, exception type, line và column.
5. Nếu JSON parse được đầy đủ, tạo cây riêng và áp dụng allowlist/redaction theo path.
6. Nếu JSON không parse được, không lưu raw prefix hoặc fragment; dùng metadata-only hoặc synthetic fixture.
7. Kiểm tra giới hạn kích thước mẫu đã redaction; nếu vượt, bỏ mẫu.
8. Ghi mẫu vào sink có access control, encryption, audit và TTL.
9. Scrub headers, URL, tracing attributes và error tracker độc lập với body.
10. Kiểm thử cả đường lỗi và đường framework tự động capture request.

## 28. Ghi nhớ

- Request lỗi có thể chứa PII, credential, payment data và secret; log/DLQ/error sample là các bản sao dữ liệu cần được bảo vệ.
- Không lưu raw JSON hoặc toàn bộ exception message theo mặc định.
- Ưu tiên metadata-only; nếu cần sample, dùng allowlist theo path và redaction trước khi ghi.
- Denylist theo tên field hữu ích nhưng không đủ để phát hiện secret trong field lạ, text tự do, URL hoặc dynamic key.
- `JsonNode` cho phép duyệt object/array và tạo bản sao redacted cho JSON hợp lệ.
- Không serialize/log cây gốc sau khi đã tạo bản redacted; mọi sink phải chỉ nhận dữ liệu đã được scrub.
- Nếu JSON sai cú pháp hoặc bị cắt, không lưu raw fragment/prefix vì không thể redaction an toàn tổng quát; giữ metadata hoặc tạo synthetic fixture.
- Không mặc định log `exception.getMessage()`, `exception.toString()`, `location.toString()` hoặc toàn bộ stack trace.
- `StreamReadFeature.INCLUDE_SOURCE_IN_LOCATION` có thể được tắt ở phiên bản Jackson hỗ trợ để giảm source data trong location; đây chỉ là lớp bảo vệ bổ sung.
- Giới hạn kích thước/depth của request và sample; không cắt chuỗi JSON tùy tiện giữa chừng.
- Masking không đồng nghĩa anonymization; không giữ một phần của credential có thể sử dụng được.
- DLQ/quarantine cần encryption, least privilege, audit, TTL và quy trình replay riêng.
- Scrub cả header, URL, trace, APM, message broker và error tracker; redactor cho JSON body không bảo vệ các kênh khác.
- Dùng dữ liệu synthetic cho fixture/test; kiểm tra secret trước khi commit hoặc chia sẻ mẫu.

Khi lưu mẫu lỗi, mục tiêu là giữ đủ thông tin để hiểu và tái hiện loại lỗi mà không nhân bản dữ liệu production không cần thiết. Hãy ưu tiên metadata và allowlist, redaction trước mọi điểm lưu, bỏ mẫu không thể parse an toàn, rồi bảo vệ phần dữ liệu còn lại bằng quyền truy cập hẹp, audit và thời hạn lưu rõ ràng.
