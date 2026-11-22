# NumericDate, kiểu dữ liệu JSON và chuyển đổi sang kiểu Java

Trong **JWT (JSON Web Token)**, các thông tin như người dùng, bên phát hành, quyền truy cập và thời điểm hết hạn được biểu diễn thành các **claim** trong một đối tượng JSON. JWT là một định dạng thuộc hệ sinh thái **JOSE (JSON Object Signing and Encryption)**; JWT có thể được bảo vệ bằng chữ ký JWS hoặc mã hóa JWE. Dù token được vận chuyển dưới dạng chuỗi ký tự, **giá trị của từng claim vẫn phải được hiểu theo kiểu JSON và quy tắc của chuẩn JWT/OIDC**.

Một chi tiết rất dễ gây lỗi khi làm việc với **Spring Security OAuth 2.0 Resource Server** là ba claim thời gian `exp`, `iat`, `nbf` dùng kiểu **NumericDate**: số giây tính từ Unix epoch, **không phải số mili giây**. Khi ứng dụng Java dùng `Instant`, `Date`, `Long`, `BigDecimal` hoặc một thư viện giải mã JWT, cần phân biệt rõ biểu diễn ban đầu và kiểu đã được thư viện chuyển đổi.

Bài này giải thích ý nghĩa NumericDate, cách các kiểu JSON được ánh xạ sang Java, những lỗi chuyển đổi thường gặp và cách đọc claims trong Resource Server mà vẫn tuân thủ ranh giới xác thực token.

## 1. Vị trí của claim JSON trong JWT và JOSE

Một JWT dạng **JWS Compact Serialization** thường có ba phần ngăn bằng dấu chấm:

~~~text
BASE64URL(Protected Header).BASE64URL(Claims Payload).BASE64URL(Signature)
~~~

Ví dụ cấu trúc bên trong:

**JOSE protected header:**

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "signing-key-01"
}
~~~

**JWT Claims Set (payload):**

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "iat": 1704067200,
  "nbf": 1704067200,
  "exp": 1704070800,
  "scope": "orders.read",
  "email_verified": true,
  "permissions": ["orders:view", "orders:export"],
  "profile": {
    "tenant_id": "tenant-7"
  }
}
~~~

Trong ví dụ, `iat` là **2024-01-01T00:00:00Z**, `exp` là **2024-01-01T01:00:00Z**: token có khoảng hiệu lực theo thiết kế là một giờ. Các giá trị thời gian đang là **JSON number**, không có dấu ngoặc kép.

JOSE header chứa thông tin cần thiết để xử lý bảo vệ mật mã như `alg` và `kid`. JWT Claims Set chứa các claim như `iss`, `sub`, `aud` và `exp`. Các kiểu dữ liệu JSON ở hai phần đều quan trọng, nhưng **không được tin một claim chỉ vì có thể Base64URL-decode và đọc được nó**. Resource Server phải xác minh chữ ký/điều kiện token theo cấu hình trước khi dùng dữ liệu claim để phân quyền.

> Lưu ý: JWT có thể được mã hóa dưới dạng JWE thay vì dạng JWS ba phần; nội dung claims chỉ đọc được khi giải mã hợp lệ. Không suy luận rằng mọi chuỗi JWT đều có thể tách đúng ba phần rồi đọc trực tiếp JSON.

## 2. NumericDate là gì?

Theo định nghĩa của JWT (RFC 7519), **NumericDate** là một giá trị **JSON number** biểu thị số giây tính từ thời điểm:

~~~text
1970-01-01T00:00:00Z
~~~

Đây là mốc **Unix epoch**. Cách đếm giây của NumericDate tương ứng mô hình thời gian POSIX: bỏ qua leap seconds khi quy đổi. NumericDate **có thể chứa phần thập phân**, không bắt buộc là số nguyên.

Ví dụ:

| NumericDate trong JSON | Ý nghĩa theo UTC |
| --- | --- |
| `0` | `1970-01-01T00:00:00Z` |
| `1` | `1970-01-01T00:00:01Z` |
| `-1` | `1969-12-31T23:59:59Z` |
| `1704067200` | `2024-01-01T00:00:00Z` |
| `1704067200.5` | `2024-01-01T00:00:00.500Z` |
| `1704067200.125` | `2024-01-01T00:00:00.125Z` |

Ở đây, ký hiệu `Z` là UTC, **không phải múi giờ địa phương của máy chủ**. Số `1704067200` giữ nguyên ý nghĩa bất kể API chạy ở Việt Nam, châu Âu hay Mỹ. Múi giờ chỉ ảnh hưởng cách **hiển thị** thời gian, không thay đổi timestamp trong token.

### Ba registered claims dùng NumericDate

| Claim | Tên đầy đủ | Ý nghĩa | Điều kiện xử lý thường gặp |
| --- | --- | --- | --- |
| `exp` | Expiration Time | Thời điểm token **hết hiệu lực** | Thời gian hiện tại phải **trước** thời điểm `exp` (có thể áp dụng leeway/clock skew được cấu hình) |
| `nbf` | Not Before | Thời điểm token **bắt đầu được phép sử dụng** | Không chấp nhận token trước `nbf`, ngoài leeway được phép |
| `iat` | Issued At | Thời điểm token **được phát hành** | Dùng để biết tuổi token; các quy tắc bổ sung cần được xác định theo chính sách |

Theo đặc tả JWT chung, các registered claims này không mặc nhiên là bắt buộc với **mọi** JWT: từng hệ thống hoặc hồ sơ giao thức có thể quy định claim nào phải xuất hiện. Chẳng hạn, **OIDC ID Token** yêu cầu một số claim thời gian như `exp` và `iat`; một Resource Server cũng nên xác định rõ yêu cầu của nó đối với access token do issuer phát hành.

**Không đánh đồng `iat` với thời điểm token bắt đầu hợp lệ.** Claim biểu thị mốc “không dùng trước” là `nbf`. Cũng không suy luận token hợp lệ chỉ từ một timestamp: chữ ký/issuer, audience, scope và các điều kiện khác vẫn phải được kiểm tra.

### Vì sao NumericDate không có đơn vị “mili giây”?

Hệ sinh thái có nhiều cách biểu diễn thời gian:

| Nguồn/kiểu | Đơn vị của giá trị số | Ví dụ cùng một thời điểm |
| --- | --- | --- |
| JWT `NumericDate` | **Giây** từ Unix epoch | `1704067200` |
| Java `Instant.getEpochSecond()` | **Giây** | `1704067200L` |
| Java `Instant.toEpochMilli()` | **Mili giây** | `1704067200000L` |
| Java `Date.getTime()` | **Mili giây** | `1704067200000L` |
| JavaScript `Date.now()` | **Mili giây** | `1704067200000` |

Nếu đưa trực tiếp kết quả `System.currentTimeMillis()` hoặc `Date.getTime()` vào claim `exp`, sẽ tạo ra một timestamp **lớn gấp 1.000 lần về đơn vị** so với giá trị NumericDate mong muốn. Ngược lại, nếu lấy NumericDate rồi đưa trực tiếp vào constructor `new Date(long)` của Java, Java sẽ hiểu là **mili giây**, dẫn đến ngày trong năm 1970 thay vì thời điểm thực.

## 3. NumericDate là kiểu number của JSON, không phải kiểu long của Java

JSON chỉ có một loại dữ liệu **number**, không phân biệt `int`, `long`, `float` và `double` trong cú pháp. Những ví dụ sau đều là JSON number về mặt cú pháp:

~~~json
{
  "wholeSeconds": 1704067200,
  "fractionalSeconds": 1704067200.125,
  "scientificNotation": 1.7040672e9
}
~~~

Trong ứng dụng Java, thư viện đọc JSON có thể ánh xạ chúng thành `Integer`, `Long`, `Double`, `BigInteger` hoặc `BigDecimal` tùy cấu hình và độ lớn. **Không thể suy luận từ cú pháp JSON rằng đối tượng Java nhất định là `Long`**.

Các cách viết sau có ý nghĩa khác nhau:

~~~json
{
  "exp_number": 1704067200,
  "exp_string": "1704067200",
  "exp_milliseconds": 1704067200000,
  "exp_iso_string": "2024-01-01T00:00:00Z"
}
~~~

- `exp_number` có định dạng đơn vị phù hợp với NumericDate.
- `exp_string` là **JSON string**, không phải NumericDate hợp lệ cho claim `exp` chuẩn.
- `exp_milliseconds` tuy là JSON number, nhưng sai **đơn vị** nếu định dùng làm thời điểm năm 2024.
- `exp_iso_string` là một chuỗi ISO-8601, hữu ích cho hiển thị nhưng không đúng kiểu NumericDate chuẩn khi gán vào `exp`.

Vì vậy, API nên từ chối hoặc xử lý lỗi claim sai kiểu theo chính sách và thư viện xác minh, **không tự động “đoán” rằng chuỗi thời gian hay số mili giây là NumericDate đúng**. Chuyển đổi tùy tiện có thể khiến các issuer phát hành token lỗi nhưng vẫn được chấp nhận một cách không nhất quán.

### Lưu ý với số thập phân

NumericDate cho phép giá trị không nguyên. Ví dụ `1704067200.125` mang thêm **125 mili giây**. Nếu code dùng `longValue()`, phần lẻ có thể bị mất.

~~~java
double numericDate = 1704067200.125;
long seconds = (long) numericDate;  // 1704067200, mất 0.125 giây
~~~

Đối với việc xác thực token thực tế, nên để thư viện JWT đáng tin cậy xử lý và kiểm tra claim thời gian. Nếu phải chuyển đổi trực tiếp ở tầng dữ liệu, cần quy định **độ chính xác** (giây, mili giây, nano giây) và cách xử lý phần thập phân; `BigDecimal` thường phù hợp hơn `double` khi muốn tránh sai số do dấu phẩy động.

## 4. Các kiểu JSON khác trong JWT và cách hiểu trong Java

JWT Claims Set là một **JSON object**, có thể chứa các loại JSON tiêu chuẩn:

| Kiểu JSON | Ví dụ payload | Biểu diễn Java thường gặp |
| --- | --- | --- |
| **string** | `"sub": "user-42"` | `String` |
| **number** | `"exp": 1704070800` | `Integer`, `Long`, `BigDecimal`... hoặc `Instant` sau khi thư viện xử lý |
| **boolean** | `"email_verified": true` | `Boolean` |
| **array** | `"roles": ["USER", "ADMIN"]` | `List<String>` hoặc `List<?>` |
| **object** | `"profile": {"tenant_id": "tenant-7"}` | `Map<String, Object>` hoặc DTO tùy cách parse |
| **null** | `"nickname": null` | `null` hoặc cách biểu diễn null tùy thư viện |

Trong ví dụ:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api", "reports-api"],
  "exp": 1704070800,
  "iat": 1704067200,
  "jti": "token-abc-123",
  "scope": "orders.read orders.write",
  "roles": ["USER", "REPORT_VIEWER"],
  "email_verified": true,
  "account": {
    "id": 42,
    "tier": "standard"
  }
}
~~~

Ý nghĩa kiểu dữ liệu cần được đọc **theo hợp đồng của từng claim**, không chỉ theo khả năng parse JSON:

- `iss` (issuer), `sub` (subject), `jti` (JWT ID) là các claim dạng **string** theo định nghĩa tương ứng.
- `aud` (audience) theo JWT có thể là **một string** hoặc **array các string**. Thư viện JWT có thể chuẩn hóa thành một danh sách cho phía ứng dụng.
- `exp`, `nbf`, `iat` là **NumericDate**.
- `scope` trong nhiều access token OAuth 2.0 được biểu diễn thành **một string các scope cách nhau bằng dấu cách**. Một số nhà cung cấp dùng claim `scp` kiểu array; không được mặc định hai cách này luôn tồn tại hoặc có cùng schema.
- `roles` và `account` ở đây là **custom claims**. Kiểu và ý nghĩa của chúng phụ thuộc vào issuer/thiết kế API; JWT không quy định mọi token phải có các claim này.
- `email_verified` là ví dụ claim dạng boolean trong ngữ cảnh OIDC; không được hiểu chuỗi `"true"` tương đương boolean `true` khi hợp đồng yêu cầu kiểu boolean.

**Một claim bắt đầu bằng chữ số cũng có thể là string.** Ví dụ `"sub": "123456"` vẫn là string: `sub` là định danh, không phải phép toán. Việc chuyển `sub` thành số có thể làm mất số 0 ở đầu hoặc làm sai ý nghĩa định danh.

## 5. Chuyển NumericDate sang kiểu Java

### 5.1. Dùng `Instant` cho thời điểm tuyệt đối

Trong Java hiện đại, `java.time.Instant` biểu diễn một thời điểm trên trục thời gian UTC và là lựa chọn phù hợp để lưu/so sánh thời gian token.

~~~java
import java.time.Instant;

long numericDate = 1704067200L;
Instant instant = Instant.ofEpochSecond(numericDate);

System.out.println(instant);
// 2024-01-01T00:00:00Z

long secondsBack = instant.getEpochSecond();
// 1704067200
~~~

Phần quan trọng là dùng **`Instant.ofEpochSecond(...)`** khi dữ liệu đầu vào là NumericDate, **không dùng `Instant.ofEpochMilli(...)`** với cùng giá trị số.

Khi cần tạo NumericDate từ thời gian hiện tại:

~~~java
Instant now = Instant.now();
long issuedAt = now.getEpochSecond();
long expiresAt = now.plusSeconds(900).getEpochSecond();

// issuedAt và expiresAt là số giây, ví dụ dùng làm iat/exp
~~~

`Instant.getEpochSecond()` trả về `long`. Điều này tránh giới hạn kiểu `int` 32 bit quanh tháng 1 năm 2038. Tuy nhiên, khi dữ liệu từ JSON có phần thập phân, `getEpochSecond()` chỉ biểu diễn phần giây nguyên; nếu cần độ chính xác cao hơn, phải kết hợp với `getNano()`.

### 5.2. Phân biệt `Date` với `Instant`

`java.util.Date` vẫn được nhiều thư viện JOSE/JWT sử dụng. Constructor `Date(long)` và phương thức `Date.getTime()` sử dụng **mili giây** từ epoch.

~~~java
import java.time.Instant;
import java.util.Date;

long numericDate = 1704067200L;       // GIÂY

Date correct = Date.from(Instant.ofEpochSecond(numericDate));
Date alsoCorrect = new Date(numericDate * 1000L);

Date incorrect = new Date(numericDate); // SAI: Java hiểu là mili giây

long seconds = correct.toInstant().getEpochSecond();
long milliseconds = correct.getTime();
~~~

Với thời gian hiện tại, các giá trị mili giây thường lớn hơn giá trị giây **1.000 lần**. Nhưng **không dùng một heuristic dựa trên số chữ số để tự đổi đơn vị trong cơ chế xác thực**: điều đó có thể gây lỗi với dữ liệu cũ, ngày âm hoặc timestamp bất thường. Quy ước rõ kiểu và đơn vị ngay tại ranh giới nhận/ghi dữ liệu.

### 5.3. Giữ phần thập phân bằng `BigDecimal`

Nếu đang xử lý **JSON thô** hoặc tự xây bộ chuyển đổi dữ liệu, `BigDecimal` giúp bảo toàn phần thập phân đến giới hạn bạn quy định. Ví dụ dưới đây chuyển số JSON NumericDate thành `Instant`, yêu cầu độ chính xác không vượt quá **nano giây** (9 chữ số có nghĩa sau dấu thập phân).

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;

public final class NumericDateConverter {

    private NumericDateConverter() {}

    public static Instant fromNumericDate(BigDecimal numericDate) {
        if (numericDate == null) {
            throw new IllegalArgumentException("NumericDate must not be null");
        }

        // FLOOR để xử lý cả thời điểm trước 1970.
        BigDecimal wholeSeconds = numericDate.setScale(0, RoundingMode.FLOOR);
        long epochSeconds = wholeSeconds.longValueExact();

        BigDecimal fractionalNanos = numericDate
            .subtract(wholeSeconds)
            .movePointRight(9);

        // intValueExact() từ chối phần nhỏ hơn 1 nanosecond.
        int nanos = fractionalNanos.intValueExact();

        return Instant.ofEpochSecond(epochSeconds, nanos);
    }

    public static BigDecimal toNumericDate(Instant instant) {
        BigDecimal seconds = BigDecimal.valueOf(instant.getEpochSecond());
        if (instant.getNano() == 0) {
            return seconds;
        }
        return seconds.add(BigDecimal.valueOf(instant.getNano(), 9));
    }
}
~~~

Ví dụ sử dụng:

~~~java
Instant t1 = NumericDateConverter.fromNumericDate(
    new BigDecimal("1704067200.125")
);
// 2024-01-01T00:00:00.125Z

Instant t2 = NumericDateConverter.fromNumericDate(
    new BigDecimal("-0.5")
);
// 1969-12-31T23:59:59.500Z

BigDecimal value = NumericDateConverter.toNumericDate(t1);
// 1704067200.125000000 (giá trị số tương đương 1704067200.125)
~~~

Vì `Instant` lưu độ chính xác nano giây, phương thức trên **từ chối** NumericDate có phần nhỏ hơn 1 nano giây mà không thể biểu diễn chính xác. Ứng dụng cũng có thể đặt chính sách làm tròn khác nếu có yêu cầu nghiệp vụ, nhưng không nên âm thầm làm tròn trong khâu xác thực token.

Điểm tinh tế: với số âm `-0.5`, phần giây của `Instant` là `-1` và phần nano là `500000000`. Dùng cách tách số nguyên bằng phép cắt về 0 mà không hiệu chỉnh phần thập phân có thể làm sai thời điểm trước epoch.

### 5.4. Đọc JSON thô bằng Jackson

Khi code Java nhận JSON chưa qua bộ chuyển đổi JWT, có thể đọc loại nút JSON trước khi ép kiểu:

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.json.JsonMapper;
import java.time.Instant;

JsonMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS)
    .build();

JsonNode claims = mapper.readTree(
    "{\"exp\":1704067200.125,\"sub\":\"user-42\"}"
);

JsonNode exp = claims.get("exp");
if (exp == null || !exp.isNumber()) {
    throw new IllegalArgumentException("exp must be a JSON number");
}

Instant expiresAt = NumericDateConverter.fromNumericDate(
    exp.decimalValue()
);

String subject = claims.path("sub").asText();
~~~

Ví dụ này minh họa **kiểu dữ liệu và chuyển đổi**, không phải cách xây bộ xác minh JWT riêng. Thực tế, Resource Server phải sử dụng `JwtDecoder` được cấu hình đúng để xác thực token trước khi tin các claim. Việc tự tách payload rồi dùng `ObjectMapper` để đọc không đủ bảo vệ API.

Khi xử lý một `Map<String, Object>`, tránh giả định `(Long) claims.get("exp")` luôn thành công: kết quả parse có thể là `Integer`, `Long`, `BigDecimal` hoặc kiểu khác, tùy parser và giai đoạn chuyển đổi.

## 6. Chuyển đổi claim trong Spring Security Resource Server

Spring Security thường thực hiện thêm bước **chuẩn hóa kiểu claim** sau khi xác minh và giải mã JWT, để lập trình viên làm việc thuận tiện bằng Java API.

Ví dụ cấu hình Resource Server dùng JWT:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

Với token có issuer tin cậy, Spring Security có thể dùng bộ giải mã JWT tương ứng (chẳng hạn `NimbusJwtDecoder`) rồi xây dựng đối tượng `org.springframework.security.oauth2.jwt.Jwt`.

### 6.1. Nên đọc thời gian bằng các getter có kiểu

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.security.oauth2.jwt.Jwt;

public final class ClaimExamples {

    public static void inspect(Jwt jwt) {
        String subject = jwt.getSubject();
        String issuer = jwt.getIssuer() == null
            ? null : jwt.getIssuer().toString();

        Instant issuedAt = jwt.getIssuedAt();   // iat
        Instant notBefore = jwt.getNotBefore();  // nbf
        Instant expiresAt = jwt.getExpiresAt();  // exp

        List<String> audiences = jwt.getAudience();
        String scope = jwt.getClaimAsString("scope");
        List<String> roles = jwt.getClaimAsStringList("roles");

        // Dùng các giá trị trên theo chính sách của ứng dụng.
    }
}
~~~

`Jwt.getIssuedAt()`, `getNotBefore()` và `getExpiresAt()` trả kiểu **`Instant`** (hoặc `null` nếu claim tương ứng không hiện diện, tùy API và dữ liệu). Các API này tránh việc người viết controller phải tự chia cho 1.000 hoặc ép kiểu `Long` từ `getClaims()`.

Trong cơ chế chuyển đổi claim chuẩn thường dùng của Spring Security (`MappedJwtClaimSetConverter`), các claim thời gian `exp`, `iat` và `nbf` được chuẩn hóa sang `Instant`; `aud` được biểu diễn phù hợp với danh sách audience. Vì vậy, **kiểu JSON trên wire và kiểu Java trong đối tượng `Jwt` không bắt buộc giống nhau**.

Ví dụ, JSON đầu vào:

~~~json
{
  "exp": 1704070800,
  "aud": "orders-api"
}
~~~

Sau khi xử lý bằng bộ chuyển đổi phù hợp, ứng dụng có thể dùng:

~~~java
Instant expiresAt = jwt.getExpiresAt();
List<String> audiences = jwt.getAudience();
~~~

Không nên viết:

~~~java
// Không an toàn về kiểu khi đang đọc đối tượng Jwt đã chuẩn hóa.
Long exp = (Long) jwt.getClaims().get("exp");
~~~

Các custom claims không nhất thiết tự được chuyển thành kiểu domain bạn mong muốn. Ví dụ `"account": {"id":42}` có thể vẫn là `Map`, và `"roles": ["USER"]` có thể là một danh sách dữ liệu thô. Nếu cần DTO hoặc mapping kiểu riêng, nên định nghĩa chính sách và bộ chuyển đổi phù hợp với issuer.

### 6.2. Spring Security kiểm tra thời gian như thế nào?

Resource Server JWT thường dùng các validator để kiểm tra hiệu lực của token, trong đó có **timestamp validation** cho `exp` và `nbf`, cùng validator issuer khi cấu hình issuer.

Ví dụ khái niệm:

~~~text
         Access token JWT
                |
                v
     Giải mã và kiểm tra chữ ký
                |
                v
    Chuẩn hóa JSON claims sang Java
                |
                v
      Kiểm tra thời gian/token
       exp, nbf, issuer...
                |
                v
    Xác thực & kiểm tra quyền API
                |
                v
       Controller / Service
~~~

Một số hệ thống cấu hình **clock skew/leeway** để chịu sai lệch đồng hồ nhỏ giữa Authorization Server và Resource Server. Ví dụ, validator có thể cho phép độ lệch vài chục giây ở mốc `exp` hoặc `nbf` theo chính sách. Đây là **biên dung sai khi kiểm tra**, không phải sửa `exp` trong token hoặc làm mới token.

`iat` thường được cung cấp để biểu thị thời điểm phát hành, nhưng không nên giả định mọi cấu hình mặc định sẽ từ chối một token chỉ vì `iat` nằm trong tương lai; nếu hệ thống cần quy tắc “không phát hành trong tương lai” hoặc “tuổi token tối đa”, hãy định nghĩa và cấu hình validator tương ứng.

JWT signature và các timestamps hợp lệ vẫn chưa đủ để cho phép gọi mọi API. Resource Server còn phải kiểm tra **issuer, audience, scope/quyền**, và quyền truy cập đối tượng cụ thể. Ví dụ, token `aud` dành cho Payments API không nên được Orders API chấp nhận chỉ vì cùng issuer và còn hạn.

### 6.3. Đừng tự chuyển NumericDate trong controller để thay validation

Mã như:

~~~java
// Ví dụ tư duy thiếu an toàn: không dùng làm cơ chế xác thực API.
String[] parts = bearerToken.split("\\.");
String payload = new String(
    java.util.Base64.getUrlDecoder().decode(parts[1])
);
// Sau đó đọc exp, sub từ JSON mà chưa xác minh chữ ký...
~~~

chỉ đọc được dữ liệu không đáng tin cậy. Nếu bỏ qua việc xác minh JOSE signature, issuer, audience và thời hạn, kẻ tấn công có thể tự tạo payload JSON tùy ý. Spring Security Resource Server đã cung cấp luồng xác thực để tránh phải tự triển khai việc đó.

## 7. Những lỗi chuyển đổi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `System.currentTimeMillis()` làm `exp` | Token có thời hạn sai đơn vị, có thể xa bất thường | Dùng thời gian theo **giây**, ví dụ `Instant.now().getEpochSecond()` |
| Dùng `new Date(numericDate)` | Java hiểu numericDate là mili giây, dẫn đến thời điểm gần 1970 | Dùng `Date.from(Instant.ofEpochSecond(numericDate))` |
| Dùng `Instant.ofEpochMilli(numericDate)` | Thời điểm sai vì NumericDate là giây | Dùng `Instant.ofEpochSecond(...)` |
| Ép thẳng `(Long) jwt.getClaim("exp")` | Có thể `ClassCastException` vì claim đã chuyển thành `Instant` | Dùng `jwt.getExpiresAt()` |
| Đọc `"exp": "1704067200"` như NumericDate | Che giấu việc token sai kiểu JSON | Yêu cầu JSON number đúng hợp đồng |
| Dùng `(int) epochSeconds` | Tràn số quanh giới hạn năm 2038 | Dùng `long` hoặc `Instant` |
| Dùng `longValue()` cho số có phần lẻ | Mất độ chính xác dưới một giây | Quy định độ chính xác; dùng `BigDecimal`/`Instant` khi cần |
| Chuyển `sub` thành số | Mất số 0 đầu, sai ID hoặc tràn số | Giữ định danh dạng `String` |
| Coi `aud` luôn là `String` | Không đọc đúng khi issuer gửi array audiences | Dùng `jwt.getAudience()` |
| Dùng `LocalDateTime.now()` để so UTC không có quy đổi | Dễ sai do múi giờ hệ thống | Dùng `Instant.now()` cho so sánh thời điểm tuyệt đối |
| Chỉ kiểm tra `exp` từ payload tự decode | Bỏ qua chữ ký và trust boundary | Dùng `JwtDecoder` và token validators của Resource Server |

### Ví dụ về lỗi giây và mili giây

~~~java
import java.time.Instant;

long expFromJwt = 1704070800L;

Instant correct = Instant.ofEpochSecond(expFromJwt);
// 2024-01-01T01:00:00Z

Instant wrong = Instant.ofEpochMilli(expFromJwt);
// 1970-01-20T17:07:50.800Z — sai đơn vị
~~~

### NumericDate không phải chuỗi ISO-8601

Ở phía Java, `Instant.toString()` thường trả ISO-8601, ví dụ `"2024-01-01T01:00:00Z"`. Đây là biểu diễn **chuỗi**, phù hợp khi gửi trong log/DTO hiển thị nhưng **không đúng kiểu JWT NumericDate** nếu đặt nguyên chuỗi đó vào claim `exp`.

Đặc biệt, nếu ứng dụng tự tạo JWT và dùng một thư viện serialize Java object sang JSON, không thể mặc định rằng `Instant` sẽ luôn được serialize thành **số giây**. Cách xuất JSON có thể phụ thuộc cấu hình Jackson và module thời gian; cần dùng API tạo JWT của thư viện JOSE hoặc bộ chuyển đổi NumericDate rõ ràng.

## 8. OIDC: những claim thời gian và kiểu dữ liệu cần lưu ý

OIDC ID Token cũng là JWT với các claim danh tính theo giao thức. Ngoài `exp` và `iat`, OIDC còn có thể dùng `auth_time` để cho biết **thời điểm người dùng được xác thực**.

Ví dụ ID Token Claims Set được rút gọn:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-42",
  "aud": "orders-web-app",
  "iat": 1704067200,
  "exp": 1704070800,
  "auth_time": 1704067000,
  "nonce": "random-nonce-value",
  "email_verified": true
}
~~~

Ở ví dụ này:

- `iat` và `exp` là NumericDate.
- `auth_time`, nếu xuất hiện, là NumericDate cho **thời điểm xác thực người dùng**, có thể khác `iat`.
- `nonce` là string dùng trong các luồng OIDC liên quan, không phải timestamp.
- `email_verified` là boolean, không phải string.
- `aud` của ID token thường hướng đến **OIDC client**, trong khi access token của API phải được xác minh theo audience dành cho **Resource Server**.

Không dùng **ID token thay cho access token** khi gọi API. OIDC client có trách nhiệm kiểm tra ID token theo quy tắc OIDC, còn Spring Security Resource Server xác thực **access token** theo hợp đồng của API. Hai loại token có thể đều chứa NumericDate, nhưng chúng phục vụ mục đích khác nhau.

## 9. Áp dụng khi thiết kế DTO, database và hợp đồng API

Trong hệ thống có nhiều service, nên thống nhất **kiểu dữ liệu, đơn vị và điểm chuyển đổi** tại mỗi ranh giới:

1. **Trong JWT/ID token theo chuẩn:** `exp`, `iat`, `nbf` (và `auth_time` khi OIDC dùng) là **JSON number theo giây**.
2. **Trong domain Java:** dùng `Instant` khi muốn lưu một thời điểm tuyệt đối; dùng `long` khi hợp đồng yêu cầu epoch seconds nguyên; dùng `BigDecimal` nếu phải xử lý phần giây lẻ chính xác.
3. **Trong Java legacy:** `Date`/epoch milliseconds phải được chuyển đơn vị rõ ràng ở ranh giới API.
4. **Trong DTO HTTP tự định nghĩa:** có thể chọn ISO-8601 string hoặc epoch seconds, nhưng phải **ghi rõ schema/đơn vị**. Không áp dụng ngầm quy tắc của DTO cho claim JWT tiêu chuẩn.
5. **Trong database:** lựa chọn kiểu timestamp và chính sách múi giờ/độ chính xác nhất quán; tránh trộn timestamp seconds và milliseconds vào cùng một cột không được định nghĩa rõ.

Ví dụ hai hợp đồng DTO khác nhau, cả hai đều có thể hợp lệ **nếu schema của chính DTO quy định**:

~~~json
{
  "expiresAt": "2024-01-01T01:00:00Z"
}
~~~

~~~json
{
  "expiresAtEpochSeconds": 1704070800
}
~~~

Nhưng đối với **JWT claim `exp`**, hợp đồng chuẩn là:

~~~json
{
  "exp": 1704070800
}
~~~

## 10. Minh họa một vòng đời token hoàn chỉnh

~~~mermaid
sequenceDiagram
    autonumber
    participant AS as Authorization Server
    participant C as OAuth2 Client
    participant RS as Spring Security Resource Server

    C->>AS: Yêu cầu token theo grant được phép
    AS-->>C: JWT access token (iat/exp là NumericDate)
    C->>RS: GET /api/orders + Bearer JWT
    RS->>RS: Xác minh chữ ký, issuer, audience
    RS->>RS: Ánh xạ NumericDate sang Instant
    RS->>RS: Kiểm tra exp/nbf, scope, quyền nghiệp vụ
    alt Token và quyền hợp lệ
        RS-->>C: 200 OK + dữ liệu
    else Token không hợp lệ hoặc hết hạn
        RS-->>C: 401 Unauthorized
    else Đã xác thực nhưng không đủ quyền
        RS-->>C: 403 Forbidden
    end
~~~

Nếu access token hết hạn, Resource Server từ chối request. Việc xin access token mới (qua refresh token grant, Client Credentials hoặc luồng cấp quyền tương ứng) do **Client và Authorization Server** xử lý. **Chuyển NumericDate sang `Instant` chỉ hỗ trợ kiểm tra thời gian**; nó không tự gia hạn token hay thay đổi quyền đã được cấp.

## 11. Ghi nhớ khi làm việc với Spring Security

- `exp`, `iat`, `nbf` theo JWT là **NumericDate — JSON number tính bằng giây từ Unix epoch**.
- JSON **number** và Java `Long` là hai khái niệm khác nhau; bộ parser và thư viện JWT có thể chuyển sang kiểu Java khác.
- Khi dùng Spring Security `Jwt`, ưu tiên `getExpiresAt()`, `getIssuedAt()`, `getNotBefore()` để lấy **`Instant`**; `getAudience()` cho danh sách audience.
- Đừng nhầm **giây** của JWT với **mili giây** của `Date.getTime()`, `System.currentTimeMillis()` hoặc `Instant.toEpochMilli()`.
- Dùng `BigDecimal` nếu phải xử lý NumericDate có phần thập phân một cách có kiểm soát; tránh phép ép kiểu làm mất độ chính xác.
- Claim trong JWT chỉ đáng tin sau khi **xác minh token** và áp dụng chính sách đúng issuer, audience, thời hạn và quyền. Không dùng dữ liệu lấy từ payload tự decode để cho phép truy cập.

Nắm chắc NumericDate và kiểu JSON giúp xử lý đúng cả ba lớp: **định dạng JWT trên đường truyền, kiểu dữ liệu của Java, và kiểm tra bảo mật trong Spring Security Resource Server**.
