# Bảo toàn số nguyên lớn và kiểm tra miền giá trị

JSON có một kiểu dữ liệu number, nhưng Java có nhiều kiểu số với giới hạn và độ chính xác khác nhau. Khi Jackson đọc JSON, lựa chọn kiểu Java đích quyết định một giá trị được lưu chính xác đến đâu và có thể biểu diễn được trong miền nào. Khi ghi JSON, kiểu Java và cấu hình generator lại quyết định cách giá trị được phát ra.

Vấn đề dễ thấy nhất xuất hiện với số nguyên lớn như ID, số thứ tự, số đếm tích lũy hoặc giá trị từ hệ thống tài chính. Nếu đọc chúng qua `double`, `Object` hoặc một kiểu nguyên quá nhỏ, giá trị có thể mất độ chính xác hoặc gây lỗi tràn miền. Ngoài ra, một số client JSON như JavaScript dùng số IEEE 754 double, nên dù Jackson giữ nguyên số nguyên lớn, client vẫn có thể làm tròn khi nhận dữ liệu.

Để bảo toàn dữ liệu, cần chọn kiểu Java đúng, truyền đầy đủ generic type khi cần, cấu hình cách xử lý số không định kiểu và kiểm tra miền giá trị theo quy tắc nghiệp vụ.

## 1. JSON number và vấn đề độ chính xác

JSON định nghĩa một kiểu dữ liệu number. Nó không phân biệt riêng `int`, `long`, `BigInteger`, `float` hay `BigDecimal`. Một token như:

```json
{
  "accountId": 9007199254740993,
  "balance": 12345678901234567890.123456789
}
```

chỉ là các số theo cú pháp JSON. Khi Jackson đọc token, mapper phải chuyển chúng thành một kiểu Java cụ thể.

Độ chính xác phụ thuộc vào kiểu đó:

- `int` chỉ chứa số nguyên trong miền 32-bit có dấu.
- `long` chứa số nguyên trong miền 64-bit có dấu.
- `BigInteger` chứa số nguyên có độ dài tùy ý, giới hạn thực tế phụ thuộc bộ nhớ và giới hạn parser.
- `float` và `double` dùng biểu diễn dấu phẩy động nhị phân, không thể biểu diễn chính xác mọi số thập phân.
- `BigDecimal` biểu diễn số thập phân với độ chính xác và scale được kiểm soát.

Với số nguyên vượt quá miền kiểu đích, Jackson không thể lưu nó chính xác vào kiểu nhỏ hơn. Với số thập phân, nếu chuyển sang `double`, một số chữ số có thể bị làm tròn.

### 1.1. Giới hạn an toàn khi trao đổi với JavaScript

JavaScript thông thường biểu diễn number bằng IEEE 754 double. Các số nguyên chỉ được biểu diễn chính xác liên tiếp đến:

```text
Number.MAX_SAFE_INTEGER = 9007199254740991 = 2^53 - 1
```

Vì vậy, các số nguyên lớn hơn giới hạn này có thể bị làm tròn khi đi qua client JavaScript:

```javascript
const id = 9007199254740993;
console.log(id); // Có thể hiển thị 9007199254740992
```

Đây là vấn đề ở phía client, không phải lỗi riêng của Jackson. Jackson có thể đọc và ghi `BigInteger` chính xác, nhưng client vẫn có thể mất dữ liệu nếu diễn giải token đó thành JavaScript `Number`.

Nếu một ID lớn hơn miền safe integer cần đi qua browser, cân nhắc biểu diễn ID dưới dạng chuỗi trong hợp đồng JSON:

```json
{
  "accountId": "9007199254740993"
}
```

Dùng chuỗi cho ID không có ý nghĩa tính toán giúp giữ nguyên từng chữ số trên nhiều nền tảng. Nếu trường là một đại lượng cần tính toán, hãy chọn kiểu số và quy ước truyền nhận phù hợp ở cả hai phía.

## 2. Chọn kiểu Java theo miền giá trị

Các kiểu số nguyên có miền khác nhau:

| Kiểu Java | Miền giá trị |
|---|---|
| `byte` | -128 đến 127 |
| `short` | -32.768 đến 32.767 |
| `int` | -2.147.483.648 đến 2.147.483.647 |
| `long` | -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 |
| `BigInteger` | Số nguyên có độ dài tùy ý, giới hạn bởi tài nguyên và cấu hình parser |

Các kiểu thập phân:

| Kiểu Java | Đặc điểm |
|---|---|
| `float` | 32-bit floating point; độ chính xác hữu hạn |
| `double` | 64-bit floating point; độ chính xác hữu hạn, thường khoảng 15–17 chữ số thập phân có nghĩa |
| `BigDecimal` | Số thập phân chính xác theo giá trị được parse và scale; phù hợp với tiền và số thập phân cần kiểm soát |

Không nên chọn kiểu chỉ vì giá trị mẫu hiện tại vừa miền. Hãy dựa trên miền hợp lệ của domain và khả năng tăng trưởng của dữ liệu.

Ví dụ:

- Số lượng sản phẩm trong một đơn hàng thường dùng `int` nếu domain giới hạn rõ.
- Timestamp hoặc ID số có thể dùng `long` nếu hợp đồng đảm bảo không vượt miền 64-bit.
- ID từ hệ thống phân tán, số thứ tự toàn cục hoặc số nguyên lớn có thể cần `BigInteger`.
- Tiền, tỷ lệ hoặc đại lượng cần giữ chính xác chữ số thập phân nên dùng `BigDecimal`, không dùng `double`.

## 3. Đọc số nguyên lớn bằng BigInteger

Khi kiểu đích đã biết là `BigInteger`, Jackson có thể chuyển token JSON integer trực tiếp thành `BigInteger`:

```java
import java.math.BigInteger;

public class AccountRequest {
    private BigInteger accountId;

    public BigInteger getAccountId() {
        return accountId;
    }

    public void setAccountId(BigInteger accountId) {
        this.accountId = accountId;
    }
}
```

Deserialize:

```java
ObjectMapper mapper = new ObjectMapper();

AccountRequest request = mapper.readValue(
        """
        {
          "accountId": 9007199254740993
        }
        """,
        AccountRequest.class
);

System.out.println(request.getAccountId());
// 9007199254740993
```

Jackson không cần chuyển số qua `double` trước khi gán vào `BigInteger`. Giá trị nguyên trong token được giữ nguyên nếu parser và kiểu đích sử dụng đường xử lý số nguyên chính xác.

Có thể đọc root number trực tiếp:

```java
BigInteger sequence = mapper.readValue(
        "123456789012345678901234567890",
        BigInteger.class
);
```

### 3.1. Đọc danh sách số nguyên lớn

Khi JSON chứa mảng số nguyên lớn, khai báo kiểu phần tử là `BigInteger`:

```java
List<BigInteger> identifiers = mapper.readValue(
        """
        [
          9007199254740993,
          123456789012345678901234567890,
          -98765432109876543210987654321
        ]
        """,
        new TypeReference<List<BigInteger>>() {}
);
```

`TypeReference` giữ kiểu phần tử của collection. Nếu chỉ truyền `List.class`, Jackson không nhận được yêu cầu rõ ràng rằng từng phần tử phải là `BigInteger`.

### 3.2. Đọc map có value là BigInteger

```java
Map<String, BigInteger> counters = mapper.readValue(
        json,
        new TypeReference<Map<String, BigInteger>>() {}
);
```

Cách này hữu ích với payload có các key động, ví dụ thống kê theo mã khách hàng hoặc bộ đếm theo tên sự kiện.

## 4. Đọc số thập phân chính xác bằng BigDecimal

Không dùng `double` cho số thập phân cần bảo toàn giá trị. Ví dụ, biểu thức dấu phẩy động nhị phân:

```java
System.out.println(0.1 + 0.2);
// 0.30000000000000004
```

không cho kết quả thập phân chính xác như phép cộng số học thập phân mà người dùng thường mong đợi.

Với tiền hoặc dữ liệu cần giữ chính xác chữ số, dùng `BigDecimal`:

```java
public class PaymentRequest {
    private BigDecimal amount;

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }
}
```

Deserialize:

```java
PaymentRequest request = mapper.readValue(
        """
        {
          "amount": 12345678901234567890.123456789
        }
        """,
        PaymentRequest.class
);

System.out.println(request.getAmount());
// 12345678901234567890.123456789
```

Khi property được khai báo rõ là `BigDecimal`, Jackson đọc số thập phân vào kiểu này mà không phải đi qua `double`.

### 4.1. Không tạo BigDecimal từ double nếu cần chính xác

Cách sau có thể giữ lại sai số vốn đã xuất hiện trong `double`:

```java
BigDecimal amount = new BigDecimal(0.1);
```

Nên tạo từ chuỗi thập phân hoặc để Jackson đọc trực tiếp token JSON vào `BigDecimal`:

```java
BigDecimal amount = new BigDecimal("0.1");
```

Hoặc:

```java
BigDecimal amount = mapper.readValue("0.1", BigDecimal.class);
```

### 4.2. Scale và so sánh BigDecimal

`BigDecimal` giữ scale, tức số chữ số sau dấu thập phân. Vì vậy:

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));        // false
```

Hai giá trị bằng nhau về số học nhưng khác scale. Khi kiểm tra miền hoặc so sánh giá trị tiền, cần chọn `compareTo()` nếu chỉ quan tâm giá trị số. Nếu scale là một phần của hợp đồng (ví dụ luôn có hai chữ số thập phân), hãy kiểm tra scale riêng.

## 5. Khi kiểu đích là Object hoặc Number

Một số ứng dụng đọc JSON động thành `Map<String, Object>` hoặc `Object` thay vì DTO có kiểu trường cố định. Khi đó, Jackson phải tự chọn kiểu số cho token vì ứng dụng không cung cấp kiểu cụ thể.

Ví dụ:

```java
Map<String, Object> values = mapper.readValue(
        json,
        new TypeReference<Map<String, Object>>() {}
);
```

Với cấu hình mặc định, số nguyên không định kiểu thường được chọn theo kích thước token, chẳng hạn `Integer`, `Long` hoặc `BigInteger`; số thập phân thường được biểu diễn bằng `Double`. Nếu ứng dụng cần tất cả integer untyped thành `BigInteger` hoặc tất cả floating point untyped thành `BigDecimal`, hãy cấu hình các feature tương ứng.

### 5.1. USE_BIG_INTEGER_FOR_INTS

`DeserializationFeature.USE_BIG_INTEGER_FOR_INTS` yêu cầu Jackson dùng `BigInteger` cho số nguyên khi kiểu đích là untyped `Object` hoặc `Number`:

```java
ObjectMapper mapper = JsonMapper.builder()
        .enable(DeserializationFeature.USE_BIG_INTEGER_FOR_INTS)
        .build();

Map<String, Object> values = mapper.readValue(
        """
        {
          "small": 10,
          "large": 9007199254740993
        }
        """,
        new TypeReference<Map<String, Object>>() {}
);
```

Khi bật feature này, cả giá trị nhỏ như 10 trong ngữ cảnh untyped cũng được biểu diễn bằng `BigInteger`, không chỉ các số vượt `long`.

Feature này phù hợp khi cấu trúc JSON động chứa các số nguyên có miền chưa biết trước và ứng dụng muốn tránh phụ thuộc vào việc Jackson chọn `Integer` hay `Long`.

### 5.2. USE_LONG_FOR_INTS

`DeserializationFeature.USE_LONG_FOR_INTS` yêu cầu số nguyên untyped được biểu diễn bằng `Long` thay vì `Integer` khi có thể. Feature này không mở rộng miền vượt quá 64-bit; số nguyên quá lớn vẫn cần `BigInteger` để giữ chính xác.

Nếu bật cả `USE_BIG_INTEGER_FOR_INTS` và `USE_LONG_FOR_INTS`, `USE_BIG_INTEGER_FOR_INTS` có độ ưu tiên cao hơn. Nếu mục tiêu là bảo toàn số nguyên không giới hạn trong map/object động, chọn `USE_BIG_INTEGER_FOR_INTS`.

### 5.3. USE_BIG_DECIMAL_FOR_FLOATS

Với số thập phân untyped, `DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS` yêu cầu Jackson dùng `BigDecimal` thay cho `Double`:

```java
ObjectMapper mapper = JsonMapper.builder()
        .enable(DeserializationFeature.USE_BIG_INTEGER_FOR_INTS)
        .enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS)
        .build();

Map<String, Object> values = mapper.readValue(
        """
        {
          "count": 9007199254740993,
          "amount": 12345678901234567890.123456789
        }
        """,
        new TypeReference<Map<String, Object>>() {}
);
```

Các feature trên có ý nghĩa với dữ liệu untyped. Nếu DTO đã khai báo trường là `BigInteger` hoặc `BigDecimal`, hãy dùng kiểu đích rõ ràng; không cần bật feature chỉ để xử lý những trường đã có kiểu cụ thể.

## 6. Đọc JSON động bằng JsonNode hoặc streaming parser

Khi không muốn ánh xạ ngay thành DTO, có thể dùng tree model:

```java
JsonNode root = mapper.readTree(json);
JsonNode idNode = root.get("accountId");
```

Nếu node đại diện số nguyên, dùng phương thức lấy giá trị phù hợp:

```java
BigInteger accountId = idNode.bigIntegerValue();
```

Với số thập phân:

```java
BigDecimal amount = root.get("amount").decimalValue();
```

Tree model có thể chọn kiểu node số theo token và cấu hình mapper. Khi yêu cầu độ chính xác là bắt buộc, hãy kiểm tra kiểu node/feature trong phiên bản Jackson đang dùng hoặc chuyển trực tiếp sang kiểu đích `BigInteger`/`BigDecimal`. Tránh gọi `asLong()` cho một số có thể vượt miền long, hoặc `doubleValue()` cho số thập phân cần giữ chính xác.

Nếu chỉ cần đọc một giá trị số ở vị trí cụ thể và muốn kiểm soát trực tiếp token, streaming API cho phép lấy giá trị chính xác:

```java
try (JsonParser parser = mapper.getFactory().createParser(json)) {
    while (parser.nextToken() != null) {
        if ("accountId".equals(parser.currentName())) {
            parser.nextToken();
            BigInteger accountId = parser.getBigIntegerValue();
            // Xử lý accountId
        }
    }
}
```

Parser cung cấp `getBigIntegerValue()` cho integer và `getDecimalValue()` cho decimal. Cách này hữu ích với file lớn hoặc khi không muốn tạo toàn bộ object tree, nhưng cần quản lý trạng thái parser và cấu trúc token cẩn thận.

## 7. Kiểm tra miền giá trị sau khi deserialize

Giữ được chính xác một con số chưa đồng nghĩa với việc con số đó hợp lệ theo nghiệp vụ. Ví dụ, `BigInteger` có thể chứa giá trị lớn tùy ý, nhưng ID của một hệ thống có thể bị giới hạn trong một miền cụ thể.

Có hai lớp kiểm tra:

1. **Miền biểu diễn của kiểu Java:** giá trị có thể lưu trong `int`, `long`, `BigInteger` hoặc `BigDecimal` hay không.
2. **Miền nghiệp vụ:** giá trị có hợp lệ với domain hay không, ví dụ số lượng phải dương, tỷ lệ nằm trong 0–1 hoặc tiền không vượt hạn mức.

### 7.1. Kiểm tra giới hạn của int và long

`Integer.MIN_VALUE`, `Integer.MAX_VALUE`, `Long.MIN_VALUE` và `Long.MAX_VALUE` thể hiện giới hạn kiểu:

```java
long maxId = Long.MAX_VALUE;
long minId = Long.MIN_VALUE;
```

Nếu JSON chứa số nguyên vượt miền của kiểu đích, Jackson sẽ báo lỗi chuyển đổi thay vì có thể lưu giá trị chính xác vào `long`. Không nên dựa vào ép kiểu thu hẹp như:

```java
long id = bigInteger.longValue(); // Có thể mất phần cao nếu vượt miền long
```

Hãy kiểm tra trước:

```java
if (bigInteger.compareTo(BigInteger.valueOf(Long.MIN_VALUE)) < 0
        || bigInteger.compareTo(BigInteger.valueOf(Long.MAX_VALUE)) > 0) {
    throw new IllegalArgumentException("ID nằm ngoài miền long");
}

long id = bigInteger.longValueExact();
```

`longValueExact()` ném `ArithmeticException` nếu giá trị không thể biểu diễn chính xác bằng long.

### 7.2. Dùng Bean Validation cho miền nghiệp vụ

Với DTO, có thể khai báo giới hạn bằng Bean Validation:

```java
public class TransferRequest {
    @NotNull
    @Min(1)
    @Max(1000000)
    private BigInteger quantity;

    @NotNull
    @DecimalMin("0.01")
    @DecimalMax("999999999999.99")
    @Digits(integer = 12, fraction = 2)
    private BigDecimal amount;

    // Getter/setter
}
```

Ý nghĩa:

- `@Min` và `@Max` xác định cận nguyên.
- `@DecimalMin` và `@DecimalMax` xác định cận số thập phân; giá trị biên mặc định được tính inclusive nếu không đặt khác.
- `@Digits` giới hạn số chữ số phần nguyên và phần thập phân.
- `@NotNull` từ chối giá trị null.

Validation không tự chạy chỉ vì DTO có annotation. Ứng dụng phải gọi validator hoặc tích hợp Bean Validation qua framework (ví dụ `@Valid` trong Spring MVC). Việc deserialize và validation là hai bước khác nhau.

### 7.3. Kiểm tra bằng code khi không dùng Bean Validation

Với domain object hoặc service, có thể kiểm tra trực tiếp:

```java
public static BigDecimal requirePositiveAmount(BigDecimal amount) {
    if (amount == null || amount.signum() <= 0) {
        throw new IllegalArgumentException("amount phải lớn hơn 0");
    }

    if (amount.scale() > 2) {
        throw new IllegalArgumentException("amount chỉ được có tối đa 2 chữ số thập phân");
    }

    return amount;
}
```

`signum()` trả về -1, 0 hoặc 1. Cách này tránh chuyển đổi qua `double` chỉ để kiểm tra số dương.

Nếu cần kiểm tra miền decimal, dùng `compareTo()`:

```java
BigDecimal min = new BigDecimal("0.01");
BigDecimal max = new BigDecimal("999999.99");

if (amount.compareTo(min) < 0 || amount.compareTo(max) > 0) {
    throw new IllegalArgumentException("amount nằm ngoài miền cho phép");
}
```

## 8. Kiểm soát coercion khi đọc số

Jackson có các quy tắc coercion để chuyển một dạng token sang kiểu Java đích. Một số trường hợp có thể được chấp nhận theo cấu hình mặc định, ví dụ chuỗi số vào trường số hoặc số thập phân vào kiểu nguyên.

### 8.1. Tránh âm thầm cắt phần thập phân

Trong Jackson 2.x, `DeserializationFeature.ACCEPT_FLOAT_AS_INT` mặc định được bật. Điều đó cho phép một số giá trị floating-point được chuyển vào kiểu nguyên bằng cách cắt phần thập phân theo quy tắc chuyển đổi.

Ví dụ, nếu DTO có:

```java
public class CounterRequest {
    private long count;

    public void setCount(long count) {
        this.count = count;
    }
}
```

Input `{"count": 12.9}` có thể được chuyển thành 12 khi feature này bật. Nếu domain yêu cầu token nguyên, hãy tắt feature:

```java
ObjectMapper mapper = JsonMapper.builder()
        .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
        .build();
```

Khi đó, floating-point token cho kiểu nguyên sẽ bị từ chối thay vì bị cắt phần thập phân.

### 8.2. Kiểm soát chuỗi số

Một số API có thể nhận cả:

```json
{"quantity": 10}
```

và:

```json
{"quantity": "10"}
```

Jackson có các cơ chế coercion để chuyển chuỗi sang kiểu số. Nếu hợp đồng yêu cầu chỉ chấp nhận JSON number token, cần cấu hình coercion phù hợp theo phiên bản Jackson hoặc dùng custom deserializer kiểm tra token type.

Không nên cho rằng khai báo field là `long` tự động bảo đảm input chỉ có token integer. Kiểu Java đích và kiểu token JSON là hai khía cạnh riêng.

### 8.3. Tràn miền không phải là validation nghiệp vụ

Nếu một JSON integer quá lớn cho `int` hoặc `long`, Jackson thường phát sinh lỗi input coercion/mapping. Đây là kiểm tra khả năng biểu diễn. Ngược lại, giá trị `999999` vẫn có thể deserialize thành công vào `int` nhưng vi phạm giới hạn nghiệp vụ, ví dụ số lượng tối đa là 100.

Do đó, cần xử lý cả lỗi chuyển đổi kiểu và validation sau deserialize.

## 9. Ghi BigInteger và BigDecimal ra JSON

Jackson có thể serialize `BigInteger` và `BigDecimal` thành JSON number:

```java
Map<String, Object> payload = new LinkedHashMap<>();
payload.put("id", new BigInteger("9007199254740993"));
payload.put("amount", new BigDecimal("1234567890.123456789"));

String json = mapper.writeValueAsString(payload);
```

Giá trị số được ghi ra mà không cần chuyển thành `double`. Tuy nhiên, khi payload được tiêu thụ bởi JavaScript hoặc một hệ thống có giới hạn precision khác, vẫn cần cân nhắc biểu diễn chuỗi cho ID hoặc giá trị lớn.

### 9.1. Ghi BigDecimal ở dạng plain notation

`BigDecimal` có thể có biểu diễn scientific notation. Nếu hợp đồng yêu cầu dạng thập phân thông thường, có thể cấu hình generator feature `WRITE_BIGDECIMAL_AS_PLAIN` trong các phiên bản Jackson 2.x hỗ trợ:

```java
JsonFactory factory = JsonFactory.builder()
        .enable(JsonGenerator.Feature.WRITE_BIGDECIMAL_AS_PLAIN)
        .build();

ObjectMapper mapper = JsonMapper.builder(factory).build();
```

Ví dụ, giá trị có thể được ghi thành `0.0000001` thay vì `1E-7`. Đây là thay đổi cách biểu diễn văn bản, không thay đổi giá trị số học.

Không nên bật tính năng này một cách máy móc nếu consumer chấp nhận exponent notation và payload có thể chứa số với scale cực lớn. Hãy chọn theo schema và yêu cầu tích hợp.

### 9.2. Khi nào nên serialize ID thành chuỗi?

Nếu ID lớn hơn safe integer của JavaScript, một cách ổn định cho API public là dùng DTO có trường chuỗi:

```java
public class AccountResponse {
    private String accountId;

    public AccountResponse(BigInteger accountId) {
        this.accountId = accountId.toString();
    }

    public String getAccountId() {
        return accountId;
    }
}
```

JSON:

```json
{
  "accountId": "9007199254740993"
}
```

Cách này thể hiện rõ rằng ID là định danh, không phải đại lượng để client thực hiện phép tính. Nếu consumer là hệ thống Java hoặc hệ thống hỗ trợ số nguyên tùy ý, có thể giữ JSON number và khai báo hợp đồng tương ứng.

## 10. Giới hạn độ dài token số và dữ liệu không tin cậy

`BigInteger` và `BigDecimal` có thể biểu diễn giá trị rất lớn, nhưng không có nghĩa ứng dụng nên chấp nhận token số dài tùy ý. Payload không tin cậy có thể gửi hàng triệu chữ số, gây tiêu tốn CPU và bộ nhớ.

Từ Jackson Core 2.15, có thể cấu hình `StreamReadConstraints` để giới hạn độ dài token số:

```java
StreamReadConstraints constraints = StreamReadConstraints.builder()
        .maxNumberLength(1000)
        .build();

JsonFactory factory = JsonFactory.builder()
        .streamReadConstraints(constraints)
        .build();

ObjectMapper mapper = JsonMapper.builder(factory).build();
```

Giới hạn này bảo vệ parser trước token số quá dài. Nó không thay thế kiểm tra miền nghiệp vụ: một số 100 chữ số vẫn có thể nằm trong giới hạn parser nhưng không hợp lệ với domain. Ngược lại, một giá trị hợp lệ về nghiệp vụ có thể cần token dài hơn giới hạn tùy cấu hình.

Hãy chọn giới hạn dựa trên schema, kích thước số lớn nhất hợp lệ và yêu cầu tài nguyên của hệ thống.

## 11. Ví dụ tổng hợp: API nhận số nguyên lớn và số tiền

Một DTO có thể khai báo kiểu theo đúng bản chất dữ liệu:

```java
public class PaymentRequest {
    private BigInteger transactionId;
    private BigDecimal amount;
    private int installmentCount;

    public BigInteger getTransactionId() {
        return transactionId;
    }

    public void setTransactionId(BigInteger transactionId) {
        this.transactionId = transactionId;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }

    public int getInstallmentCount() {
        return installmentCount;
    }

    public void setInstallmentCount(int installmentCount) {
        this.installmentCount = installmentCount;
    }
}
```

JSON:

```json
{
  "transactionId": 123456789012345678901234567890,
  "amount": 123456789012345.67,
  "installmentCount": 12
}
```

Deserialize:

```java
PaymentRequest request = mapper.readValue(json, PaymentRequest.class);
```

Trong thiết kế này:

- `transactionId` dùng `BigInteger` để không bị giới hạn ở 64-bit.
- `amount` dùng `BigDecimal` để giữ giá trị thập phân chính xác.
- `installmentCount` dùng `int` vì domain có thể giới hạn rõ số kỳ; cần validation để xác định miền nghiệp vụ.

Ví dụ kiểm tra:

```java
if (request.getTransactionId() == null
        || request.getTransactionId().signum() <= 0) {
    throw new IllegalArgumentException("transactionId phải là số nguyên dương");
}

if (request.getAmount() == null
        || request.getAmount().compareTo(BigDecimal.ZERO) <= 0) {
    throw new IllegalArgumentException("amount phải lớn hơn 0");
}

if (request.getInstallmentCount() < 1
        || request.getInstallmentCount() > 60) {
    throw new IllegalArgumentException("installmentCount phải nằm trong 1..60");
}
```

Ví dụ minh họa kiểm tra domain ở tầng service. Trong ứng dụng thực tế, có thể chuyển các điều kiện này sang Bean Validation hoặc domain constructor để tái sử dụng và trả lỗi theo chuẩn API.

## 12. Kiểm thử bảo toàn số và miền giá trị

Test cần xác nhận không chỉ deserialize thành công mà còn giữ nguyên giá trị:

```java
@Test
void shouldPreserveLargeIntegerAndDecimal() throws Exception {
    ObjectMapper mapper = new ObjectMapper();

    PaymentRequest request = mapper.readValue(
            """
            {
              "transactionId": 9007199254740993,
              "amount": 12345678901234567890.123456789,
              "installmentCount": 12
            }
            """,
            PaymentRequest.class
    );

    assertEquals(
            new BigInteger("9007199254740993"),
            request.getTransactionId()
    );

    assertEquals(
            new BigDecimal("12345678901234567890.123456789"),
            request.getAmount()
    );
}
```

Có thể kiểm tra round-trip:

```java
String json = mapper.writeValueAsString(request);
PaymentRequest restored = mapper.readValue(json, PaymentRequest.class);

assertEquals(request.getTransactionId(), restored.getTransactionId());
assertEquals(0, request.getAmount().compareTo(restored.getAmount()));
```

Dùng `compareTo()` nếu scale không phải một phần của yêu cầu; dùng `equals()` nếu cần xác nhận cả scale.

Nên bổ sung các trường hợp biên:

- Giá trị bằng `Long.MAX_VALUE` và `Long.MIN_VALUE`.
- Giá trị lớn hơn miền long nhưng hợp lệ với `BigInteger`.
- Giá trị lớn hơn (2^{53}-1) qua client JavaScript.
- Số thập phân có nhiều chữ số có nghĩa.
- Số âm, số 0 và giá trị đúng bằng cận min/max.
- Giá trị ngay dưới cận và ngay trên cận.
- Số thập phân gửi vào trường nguyên khi `ACCEPT_FLOAT_AS_INT` bị tắt.
- Token số quá dài vượt `StreamReadConstraints`.

## 13. Quy trình lựa chọn kiểu và kiểm tra

Khi thiết kế một property số trong DTO, có thể thực hiện theo trình tự:

1. **Xác định ý nghĩa dữ liệu.** ID, số đếm, tiền, tỷ lệ và số đo có yêu cầu khác nhau.
2. **Xác định miền hợp lệ.** Tìm giá trị nhỏ nhất/lớn nhất, số chữ số thập phân và khả năng tăng trưởng.
3. **Chọn kiểu Java.** Dùng kiểu nguyên có kích thước phù hợp, `BigInteger` cho integer lớn, `BigDecimal` cho decimal chính xác.
4. **Truyền kiểu đích đầy đủ.** Với collection/map generic, dùng `TypeReference` hoặc `JavaType`.
5. **Cấu hình untyped number khi cần.** Dùng `USE_BIG_INTEGER_FOR_INTS` và `USE_BIG_DECIMAL_FOR_FLOATS` nếu đọc vào `Object`/map động.
6. **Kiểm soát coercion.** Tắt `ACCEPT_FLOAT_AS_INT` nếu không cho phép cắt phần thập phân vào trường nguyên.
7. **Validate miền nghiệp vụ.** Dùng Bean Validation hoặc domain validation sau khi binding.
8. **Xem xét consumer.** Nếu đi qua JavaScript, cân nhắc gửi ID lớn dưới dạng string.
9. **Giới hạn kích thước input.** Cấu hình `StreamReadConstraints` cho payload không tin cậy.
10. **Kiểm thử biên và round-trip.** Xác nhận giá trị được giữ nguyên qua deserialize, serialize và các hệ thống liên quan.

## 14. Kết luận

Bảo toàn số nguyên lớn bắt đầu từ việc không đưa giá trị qua kiểu có miền hoặc độ chính xác nhỏ hơn cần thiết. Dùng `BigInteger` cho số nguyên vượt miền `long`, dùng `BigDecimal` cho số thập phân cần chính xác, và cấu hình feature untyped khi dữ liệu được đọc vào `Object` hoặc map động. Với collection generic, phải cung cấp đầy đủ kiểu phần tử để Jackson không chuyển chúng thành map hoặc kiểu số mặc định ngoài ý muốn.

Sau khi giữ được giá trị, ứng dụng vẫn cần kiểm tra miền nghiệp vụ, kiểm soát coercion và xem xét precision của consumer như JavaScript. Kết hợp kiểu dữ liệu phù hợp, validation và kiểm thử giá trị biên giúp JSON giữ đúng con số từ đầu vào đến đầu ra.

## Tài liệu tham khảo

- [RFC 8259 — JSON Number and Interoperability](https://www.rfc-editor.org/rfc/rfc8259)
- [Jackson Databind — DeserializationFeature API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/DeserializationFeature.html)
- [Jackson Core — StreamReadConstraints API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/latest/com/fasterxml/jackson/core/StreamReadConstraints.html)
- [Jackson Core — JsonGenerator Feature API](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-core/latest/com/fasterxml/jackson/core/JsonGenerator.Feature.html)
- [Java BigInteger API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html)
- [Java BigDecimal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)

