# Phân biệt kiểu số khi đọc dữ liệu không định kiểu

JSON chỉ có một loại giá trị số là `number`. Nó không khai báo riêng `int`, `long`, `float`, `double`, `BigInteger` hay `BigDecimal` như Java. Khi Jackson đọc một số vào thuộc tính Java có kiểu cụ thể, kiểu đích đã cho biết cách chuyển đổi. Nhưng khi đọc dữ liệu **không định kiểu** như `Object`, `Map<String, Object>` hoặc `List<Object>`, Jackson phải tự chọn một kiểu Java để biểu diễn mỗi số.

Lựa chọn đó có thể ảnh hưởng đến độ chính xác, miền giá trị, phép tính tiếp theo và cách code xử lý dữ liệu. Ví dụ, một giá trị thập phân được đọc thành `Double` có thể không giữ chính xác biểu diễn thập phân ban đầu; một số nguyên rất lớn có thể vượt giới hạn `long`; còn một số nguyên nhỏ thường được biểu diễn bằng `Integer`.

Jackson cung cấp các cấu hình như `USE_BIG_DECIMAL_FOR_FLOATS`, `USE_BIG_INTEGER_FOR_INTS` và `USE_LONG_FOR_INTS` để điều chỉnh cách ánh xạ số trong dữ liệu không định kiểu. Khi cần kiểm soát chi tiết hơn, có thể đọc bằng `JsonNode`, kiểm tra loại token hoặc ánh xạ vào DTO có kiểu rõ ràng.

## 1. JSON không phân biệt int, long, float và double

JSON có sáu loại giá trị cơ bản: object, array, string, number, boolean và null. Trong đó, `number` có thể được viết theo dạng số nguyên hoặc dạng có phần thập phân/số mũ.

```json
{
  "quantity": 12,
  "unitPrice": 19.95,
  "largeId": 9223372036854775808,
  "scientificValue": 1.25e6
}
```

Các giá trị trên đều là JSON number. Cú pháp JSON không ghi rằng `quantity` là Java `int`, `unitPrice` là `double` hay `largeId` là `BigInteger`. Hệ thống nhận phải chọn kiểu biểu diễn phù hợp.

Một số cách viết số có ý nghĩa cú pháp khác nhau:

| JSON number | Hình thức | Nhận xét |
|---|---|---|
| `12` | Số nguyên | Không có phần thập phân hoặc số mũ |
| `12.0` | Số có phần thập phân | Giá trị toán học bằng 12 nhưng token có phần thập phân |
| `1e3` | Số có số mũ | Giá trị toán học bằng 1000 nhưng token dùng ký pháp số mũ |
| `-0` | Số nguyên âm không | Cú pháp có dấu âm |
| `-0.0` | Số có phần thập phân âm không | Có thể khác `-0` ở cách biểu diễn dấu của số dấu phẩy động |
| `123456789012345678901234567890` | Số nguyên rất lớn | Vượt giới hạn của `long` |

JSON không quy định miền giá trị hay độ chính xác tối đa mà mọi triển khai phải hỗ trợ giống nhau. Một hệ thống có thể giới hạn độ dài token hoặc phạm vi số. Vì vậy, hợp đồng API cần quy định rõ miền giá trị nếu dữ liệu có yêu cầu chính xác hoặc giới hạn nghiệp vụ.

## 2. Kiểu Java thường dùng để biểu diễn số

Các kiểu Java có miền giá trị và đặc tính khác nhau:

| Kiểu Java | Đặc điểm | Trường hợp thường gặp |
|---|---|---|
| `Integer` / `int` | Số nguyên 32 bit có dấu | Số lượng nhỏ, trạng thái đếm có giới hạn |
| `Long` / `long` | Số nguyên 64 bit có dấu | ID số, timestamp dạng số, bộ đếm lớn |
| `BigInteger` | Số nguyên độ dài tùy ý, giới hạn bởi tài nguyên | Số nguyên vượt miền `long` hoặc cần giữ chính xác |
| `Float` / `float` | Số dấu phẩy động 32 bit | Dữ liệu khoa học/đồ họa khi chấp nhận sai số |
| `Double` / `double` | Số dấu phẩy động 64 bit | Tính toán số gần đúng, đo lường |
| `BigDecimal` | Số thập phân độ chính xác tùy ý với scale | Tiền tệ, tỷ lệ, dữ liệu thập phân cần chính xác |

`Integer` và `Long` có giới hạn. `BigInteger` có thể giữ số nguyên lớn mà không tràn trong phạm vi tài nguyên cho phép. `Double` và `Float` dùng biểu diễn nhị phân IEEE 754 nên nhiều phân số thập phân không thể biểu diễn chính xác. `BigDecimal` phù hợp khi cần thao tác với giá trị thập phân theo quy tắc chính xác và scale rõ ràng.

Ví dụ, `0.1` không có biểu diễn nhị phân hữu hạn trong `double`. Phép tính:

```java
double total = 0.1 + 0.2;
System.out.println(total);
```

có thể in ra giá trị gần `0.30000000000000004`, thay vì đúng bằng `0.3`. Nếu cần tính toán tiền, nên dùng `BigDecimal`:

```java
BigDecimal total = new BigDecimal("0.1")
    .add(new BigDecimal("0.2"));

System.out.println(total); // 0.3
```

Nên tạo `BigDecimal` từ chuỗi thập phân hoặc từ dữ liệu đã được parse chính xác. Tránh `new BigDecimal(0.1)` vì lúc đó giá trị `double` đã có sai số trước khi được đưa vào `BigDecimal`.

## 3. Jackson ánh xạ số không định kiểu như thế nào?

Khi đọc JSON vào `Object`, `Map<String, Object>` hoặc `List<Object>`, Jackson phải chọn kiểu Java tự nhiên cho từng giá trị.

Với cấu hình mặc định phổ biến của Jackson Databind:

- Số nguyên được ánh xạ thành `Integer` nếu giá trị nằm trong miền `int`.
- Nếu vượt miền `int` nhưng vẫn nằm trong miền `long`, giá trị được ánh xạ thành `Long`.
- Nếu vượt miền `long`, Jackson có thể dùng `BigInteger`.
- Số có phần thập phân hoặc số mũ thường được ánh xạ thành `Double`.
- Chuỗi vẫn là `String`; JSON boolean thành `Boolean`; object thành `Map`; array thành `List`; null thành null Java.

Ví dụ:

```java
ObjectMapper mapper = new ObjectMapper();

String json = """
    {
      "small": 12,
      "medium": 3000000000,
      "large": 9223372036854775808,
      "ratio": 0.25,
      "scientific": 1.2e4
    }
    """;

Map<String, Object> values = mapper.readValue(
    json,
    new TypeReference<Map<String, Object>>() {}
);

values.forEach((key, value) ->
    System.out.println(key + " -> " + value.getClass().getName())
);
```

Với dữ liệu minh họa và cấu hình mặc định, các giá trị số nguyên sẽ được chọn theo miền biểu diễn; các giá trị có phần thập phân/số mũ thường là `Double`. Kết quả cụ thể cần được xác nhận theo phiên bản Jackson và cấu hình đang dùng.

Điều cần nhớ là kiểu khai báo ở vế trái không quyết định kiểu phần tử bên trong nếu Jackson không nhận được thông tin generic. Ví dụ:

```java
Map<String, Object> values = mapper.readValue(json, Map.class);
```

Các giá trị trong map vẫn là kiểu tự nhiên của quá trình untyped deserialization. Nếu cần kiểu số khác, phải cấu hình mapper/reader hoặc chuyển đổi có kiểm soát sau khi parse.

## 4. Điều chỉnh kiểu số bằng DeserializationFeature

Jackson có các feature dành cho số khi deserialize dữ liệu không định kiểu.

| Feature | Hành vi |
|---|---|
| `USE_LONG_FOR_INTS` | Dùng `Long` thay cho `Integer` đối với các số nguyên không định kiểu nằm trong phạm vi phù hợp |
| `USE_BIG_INTEGER_FOR_INTS` | Dùng `BigInteger` cho các số nguyên không định kiểu |
| `USE_BIG_DECIMAL_FOR_FLOATS` | Dùng `BigDecimal` thay cho `Double` cho các số có phần thập phân/số mũ không định kiểu |

Các feature này chủ yếu ảnh hưởng tới quá trình ánh xạ giá trị số không định kiểu, chẳng hạn thuộc tính khai báo là `Object`, phần tử trong `List<Object>` hoặc giá trị trong `Map<String, Object>`. Nếu DTO khai báo rõ một field là `int`, `long`, `double` hay `BigDecimal`, Jackson vẫn ánh xạ theo kiểu đích và quy tắc chuyển đổi tương ứng; không nên kỳ vọng các feature untyped sẽ thay đổi kiểu đã khai báo của DTO.

### 4.1. Dùng Long cho số nguyên không định kiểu

```java
ObjectMapper mapper = new ObjectMapper();
mapper.enable(DeserializationFeature.USE_LONG_FOR_INTS);

Map<String, Object> data = mapper.readValue(
    json,
    new TypeReference<Map<String, Object>>() {}
);
```

Feature này hữu ích khi ứng dụng muốn các số nguyên thông thường trong dữ liệu động có kiểu nhất quán là `Long`, chẳng hạn khi chuyển dữ liệu từ một nguồn JSON vào mô hình map dùng chung.

### 4.2. Dùng BigInteger cho số nguyên không định kiểu

```java
ObjectMapper mapper = new ObjectMapper();
mapper.enable(DeserializationFeature.USE_BIG_INTEGER_FOR_INTS);

Map<String, Object> data = mapper.readValue(
    json,
    new TypeReference<Map<String, Object>>() {}
);

BigInteger id = (BigInteger) data.get("largeId");
```

Với feature này, các số nguyên không định kiểu được biểu diễn bằng `BigInteger`, kể cả khi giá trị nhỏ. Điều này tránh phải suy đoán xem một số cụ thể có rơi vào `Integer` hay `Long`, nhưng làm thay đổi kiểu runtime mà code downstream nhận được.

### 4.3. Dùng BigDecimal cho số thập phân không định kiểu

```java
ObjectMapper mapper = new ObjectMapper();
mapper.enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS);

Map<String, Object> data = mapper.readValue(
    json,
    new TypeReference<Map<String, Object>>() {}
);

BigDecimal ratio = (BigDecimal) data.get("ratio");
```

Feature này đặc biệt hữu ích khi dữ liệu thập phân được đọc vào `Object`, map hoặc collection không có kiểu phần tử cố định. Nó giúp tránh việc chuyển token thập phân sang `double` trước khi ứng dụng xử lý.

### 4.4. Kết hợp các feature

Nếu dữ liệu động cần giữ số nguyên lớn và số thập phân chính xác, có thể cấu hình:

```java
ObjectMapper mapper = new ObjectMapper();
mapper.enable(DeserializationFeature.USE_BIG_INTEGER_FOR_INTS);
mapper.enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS);
```

Không cần bật `USE_LONG_FOR_INTS` đồng thời với `USE_BIG_INTEGER_FOR_INTS` nếu mục tiêu là buộc mọi số nguyên không định kiểu thành `BigInteger`; feature BigInteger đã quy định kiểu đó. Hãy chọn chính sách có chủ đích để code xử lý map không phải kiểm tra quá nhiều kiểu số khác nhau.

## 5. Đặt feature trên ObjectReader thay vì thay đổi mapper dùng chung

Nếu chỉ một luồng tích hợp cần số thập phân chính xác, không nhất thiết phải thay đổi chính sách của toàn ứng dụng. Có thể tạo reader riêng:

```java
ObjectReader exactNumberReader = mapper.reader()
    .with(DeserializationFeature.USE_BIG_INTEGER_FOR_INTS)
    .with(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS);

Map<String, Object> payload = exactNumberReader.readValue(json);
```

Reader giữ chính sách đọc riêng mà không làm thay đổi mapper gốc. Có thể tạo reader chuyên biệt trong constructor của adapter và tái sử dụng:

```java
public final class DynamicPayloadReader {
    private final ObjectReader reader;

    public DynamicPayloadReader(ObjectMapper mapper) {
        this.reader = mapper.reader()
            .with(DeserializationFeature.USE_BIG_INTEGER_FOR_INTS)
            .with(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS);
    }

    public Map<String, Object> read(String json) throws IOException {
        return reader.readValue(json);
    }
}
```

Đây là cách hữu ích khi một hệ thống có nhiều loại dữ liệu: một API nghiệp vụ dùng DTO với kiểu cụ thể, trong khi một bộ xử lý event động cần bảo toàn số trong map.

## 6. Ánh xạ số vào DTO có kiểu rõ ràng

Nếu hợp đồng dữ liệu ổn định, cách tốt nhất thường là khai báo kiểu đích rõ ràng thay vì nhận mọi giá trị dưới dạng `Object`.

Ví dụ dữ liệu thanh toán:

```json
{
  "transactionId": 1024,
  "quantity": 3,
  "unitPrice": 125000.50
}
```

DTO:

```java
public class PaymentLine {
    private long transactionId;
    private int quantity;
    private BigDecimal unitPrice;

    public long getTransactionId() {
        return transactionId;
    }

    public void setTransactionId(long transactionId) {
        this.transactionId = transactionId;
    }

    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public void setUnitPrice(BigDecimal unitPrice) {
        this.unitPrice = unitPrice;
    }
}
```

Jackson sẽ ánh xạ theo kiểu đã khai báo:

- `transactionId` vào `long`.
- `quantity` vào `int`.
- `unitPrice` vào `BigDecimal`.

Việc dùng `BigDecimal` cho giá tiền giúp tránh sai số nhị phân của `double`. Ứng dụng vẫn cần xác định scale, quy tắc làm tròn, đơn vị tiền tệ và giới hạn giá trị hợp lệ.

Ví dụ tính tổng:

```java
BigDecimal total = line.getUnitPrice()
    .multiply(BigDecimal.valueOf(line.getQuantity()));
```

Không nên dùng `double` cho tiền chỉ vì JSON gửi số có dấu thập phân. Kiểu Java nên được chọn theo ý nghĩa dữ liệu và yêu cầu chính xác của nghiệp vụ.

## 7. Đọc dữ liệu không định kiểu bằng JsonNode

Tree Model là lựa chọn hữu ích khi cấu trúc JSON chưa biết trước hoặc một số trường có thể mang kiểu số khác nhau. `JsonNode` cung cấp các phương thức để kiểm tra loại node trước khi lấy giá trị.

```java
JsonNode root = mapper.readTree(json);
JsonNode amountNode = root.path("amount");

if (!amountNode.isNumber()) {
    throw new IllegalArgumentException("amount must be a number");
}

BigDecimal amount = amountNode.decimalValue();
```

Các phương thức kiểm tra thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| `isNumber()` | Node là giá trị số |
| `isIntegralNumber()` | Node là số nguyên |
| `isFloatingPointNumber()` | Node là số có phần thập phân hoặc số mũ |
| `numberType()` | Cho biết kiểu số nội bộ của node |
| `canConvertToInt()` | Kiểm tra khả năng chuyển về miền `int` |
| `canConvertToLong()` | Kiểm tra khả năng chuyển về miền `long` |
| `bigIntegerValue()` | Lấy giá trị dưới dạng `BigInteger` |
| `decimalValue()` | Lấy giá trị dưới dạng `BigDecimal` |

Trước khi chuyển sang `int` hoặc `long`, cần kiểm tra node là số nguyên và nằm trong miền giá trị đích. Tránh gọi `asInt()` một cách mù quáng vì các phương thức `asXxx()` có thể thực hiện coercion hoặc trả giá trị mặc định trong một số tình huống, làm mất dấu hiệu dữ liệu sai.

Ví dụ kiểm tra số nguyên trong miền `long`:

```java
JsonNode idNode = root.path("id");

if (!idNode.isIntegralNumber() || !idNode.canConvertToLong()) {
    throw new IllegalArgumentException("id must be a valid long integer");
}

long id = idNode.longValue();
```

Nếu cần số nguyên lớn hơn `long`, hãy lấy `bigIntegerValue()` và kiểm tra miền nghiệp vụ sau đó.

### 7.1. Giữ số thập phân chính xác trong Tree Model

Khi đọc JSON vào cây, số dấu phẩy động mặc định có thể được biểu diễn bằng `DoubleNode`. Nếu cần `BigDecimal`, cấu hình `USE_BIG_DECIMAL_FOR_FLOATS` trước khi đọc:

```java
ObjectReader exactTreeReader = mapper.reader()
    .with(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS);

JsonNode root = exactTreeReader.readTree(json);
BigDecimal amount = root.path("amount").decimalValue();
```

Nếu dữ liệu cần giữ cả scale hoặc cách viết nguyên văn của token như `1.00` so với `1.0`, cần kiểm tra thêm cấu hình node factory và yêu cầu lưu trữ. `BigDecimal` có cả giá trị và scale, nhưng việc parse/ghi JSON có thể chuẩn hóa cách biểu diễn theo cấu hình. Nếu cần bảo toàn chính xác văn bản gốc, hãy lưu token/string gốc thay vì chỉ lưu giá trị số đã parse.

## 8. Kiểm tra kiểu số ở mức Streaming API

Khi đọc một luồng JSON lớn, có thể kiểm tra kiểu token và lấy số theo kiểu phù hợp mà không cần tạo toàn bộ object graph.

```java
try (JsonParser parser = mapper.getFactory().createParser(input)) {
    while (parser.nextToken() != null) {
        JsonToken token = parser.currentToken();

        if (token == JsonToken.VALUE_NUMBER_INT
                || token == JsonToken.VALUE_NUMBER_FLOAT) {

            JsonParser.NumberType numberType = parser.getNumberType();
            Number value = parser.getNumberValue();

            System.out.println(numberType + " -> " + value);
        }
    }
}
```

`getNumberType()` có thể cho biết Jackson đang biểu diễn token bằng `INT`, `LONG`, `BIG_INTEGER`, `FLOAT`, `DOUBLE` hoặc `BIG_DECIMAL`. Chỉ gọi các phương thức lấy số sau khi xác nhận token hiện tại là token số.

Nếu cần độ chính xác cụ thể, có thể yêu cầu parser lấy giá trị tương ứng:

```java
BigInteger integer = parser.getBigIntegerValue();
BigDecimal decimal = parser.getDecimalValue();
```

Các phương thức này giúp tránh việc ép một số lớn vào kiểu nhỏ. Tuy nhiên, parser vẫn chịu giới hạn tài nguyên và giới hạn token được cấu hình trong `JsonFactory`; dữ liệu quá dài hoặc quá lớn cần được từ chối theo chính sách đầu vào.

## 9. Phân biệt số nguyên và số thập phân theo cú pháp

Một JSON number không có kiểu Java được chỉ định, nhưng cách viết token vẫn giúp parser phân biệt dạng số nguyên và dạng dấu phẩy động.

Ví dụ:

```json
{
  "a": 1,
  "b": 1.0,
  "c": 1e0
}
```

Ba giá trị có cùng giá trị toán học, nhưng `a` là token số nguyên, còn `b` và `c` là token dấu phẩy động theo cú pháp JSON. Với dữ liệu không định kiểu, điều này có thể dẫn đến kiểu Java khác nhau.

Nếu ứng dụng muốn chấp nhận cả `1`, `1.0` và `1e0` cho một trường số nguyên, cần quy định rõ cách chuyển đổi. Không nên tự động cắt phần thập phân bằng `intValue()` nếu phần thập phân khác 0. Ví dụ `3.9` chuyển thành `3` có thể làm sai dữ liệu mà không báo lỗi.

Đối với trường bắt buộc là số nguyên, hãy xác nhận token hoặc node là integral. Đối với trường chấp nhận số thập phân, dùng kiểu phù hợp như `BigDecimal` và kiểm tra scale/range theo yêu cầu.

## 10. Giới hạn chính xác của số và hệ thống JavaScript

Một số nguyên có thể nằm trong miền `long` của Java nhưng vẫn vượt phạm vi số nguyên an toàn của JavaScript. JavaScript `Number` sử dụng số dấu phẩy động IEEE 754 double; các số nguyên chỉ được biểu diễn chính xác liên tục trong khoảng:

\[
-(2^{53}-1) \le n \le 2^{53}-1
\]

Nếu API gửi ID lớn hơn giới hạn này dưới dạng JSON number, client JavaScript có thể làm tròn giá trị khi parse. Ví dụ một ID 64-bit có thể không còn nguyên vẹn dù server Java dùng `long` chính xác.

Với ID lớn hoặc số nguyên cần giữ chính xác qua nhiều nền tảng, cân nhắc biểu diễn bằng chuỗi:

```json
{
  "accountId": "9223372036854775808"
}
```

DTO:

```java
public class AccountReference {
    private String accountId;

    public String getAccountId() {
        return accountId;
    }

    public void setAccountId(String accountId) {
        this.accountId = accountId;
    }
}
```

Nếu cần tính toán số học, có thể chuyển chuỗi sang `BigInteger` ở tầng ứng dụng sau khi xác thực định dạng. Nếu giá trị chỉ là định danh, giữ dưới dạng chuỗi thường đơn giản và an toàn hơn.

## 11. Không để kiểu số không định kiểu lan vào toàn bộ ứng dụng

`Map<String, Object>` hữu ích cho dữ liệu động, nhưng downstream phải xử lý nhiều kiểu runtime khác nhau. Một giá trị có thể là `Integer`, `Long`, `BigInteger`, `Double` hoặc `BigDecimal`, tùy giá trị JSON và cấu hình mapper.

Ví dụ code dễ phát sinh lỗi:

```java
Object value = data.get("amount");
Double amount = (Double) value;
```

Nếu JSON chứa `100` thay vì `100.0`, giá trị có thể được ánh xạ thành `Integer` hoặc `Long`, dẫn đến `ClassCastException`.

Nếu cần làm việc với một giá trị số tổng quát, có thể kiểm tra `Number`:

```java
Object value = data.get("amount");

if (!(value instanceof Number number)) {
    throw new IllegalArgumentException("amount must be numeric");
}

BigDecimal amount;
if (number instanceof BigDecimal decimal) {
    amount = decimal;
} else if (number instanceof BigInteger integer) {
    amount = new BigDecimal(integer);
} else {
    amount = new BigDecimal(number.toString());
}
```

Đoạn code trên xử lý các kiểu số thường gặp. Nếu `number` là `Double`, `number.toString()` tạo biểu diễn thập phân ngắn nhất của giá trị double hiện có; nó không khôi phục được độ chính xác của token JSON ban đầu nếu trước đó đã mất. Muốn bảo toàn độ chính xác, hãy bật `USE_BIG_DECIMAL_FOR_FLOATS` ngay từ lúc deserialize hoặc ánh xạ trường thành `BigDecimal`.

Với schema ổn định, DTO có kiểu cụ thể thường tốt hơn map động:

```java
public record InvoiceLine(
    long productId,
    int quantity,
    BigDecimal unitPrice
) {
}
```

Kiểu cụ thể giúp compiler hỗ trợ kiểm tra, làm rõ hợp đồng và giảm các phép ép kiểu ở code nghiệp vụ.

## 12. Coercion và validation khi đọc số

Jackson có thể hỗ trợ một số chuyển đổi giữa dạng chuỗi và dạng số tùy cấu hình coercion. Ví dụ, một API có thể nhận:

```json
{"quantity": "12"}
```

trong khi DTO khai báo `int quantity`. Việc chấp nhận chuỗi số hay từ chối phải là quyết định của hợp đồng API. Không nên phụ thuộc vào coercion ngầm nếu client cần gửi đúng kiểu JSON.

Khi cần chính sách nghiêm ngặt, có thể cấu hình coercion theo kiểu logic hoặc kiểm tra JSON đầu vào trước khi ánh xạ. Dù cách nào, validation nghiệp vụ vẫn cần kiểm tra:

- Giá trị có nằm trong miền hợp lệ không.
- Số lượng có âm hoặc vượt giới hạn không.
- Số thập phân có quá nhiều chữ số sau dấu thập phân không.
- Số tiền có đúng đơn vị và quy tắc làm tròn không.
- Trường bắt buộc có bị thiếu hoặc null không.
- Số nguyên có thể chuyển an toàn sang kiểu đích không.

Parse thành công chỉ có nghĩa Jackson có thể tạo giá trị Java theo quy tắc chuyển đổi; không đồng nghĩa giá trị đó hợp lệ về nghiệp vụ.

## 13. Kiểm thử kiểu số

Khi sử dụng dữ liệu không định kiểu, nên kiểm tra cả giá trị lẫn class runtime:

```java
class UntypedNumberTest {
    @Test
    void usesBigDecimalForUntypedFloatingPointNumbers() throws Exception {
        ObjectMapper mapper = new ObjectMapper()
            .enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS);

        Map<String, Object> values = mapper.readValue(
            "{\"amount\": 0.10}",
            new TypeReference<Map<String, Object>>() {}
        );

        assertInstanceOf(BigDecimal.class, values.get("amount"));
        assertEquals(new BigDecimal("0.10"), values.get("amount"));
    }
}
```

Nếu hợp đồng cần giữ scale, hãy kiểm tra cả `scale()` thay vì chỉ so sánh giá trị bằng `compareTo`, vì `BigDecimal("0.10")` và `BigDecimal("0.1")` có cùng giá trị số nhưng scale khác nhau.

Nên có test cho các biên quan trọng:

- Số nguyên nằm trong miền `int`.
- Số nguyên lớn hơn `Integer.MAX_VALUE` nhưng vẫn nằm trong miền `long`.
- Số nguyên vượt miền `long`.
- Số thập phân có nhiều chữ số sau dấu phẩy.
- Số ở dạng exponent như `1.25e6`.
- Giá trị âm, zero và `-0.0` nếu dấu âm của zero có ý nghĩa.
- Chuỗi số khi API có hoặc không cho phép coercion.
- Số vượt giới hạn nghiệp vụ hoặc giới hạn parser.

Không chỉ test với số nhỏ như `1` hoặc `2`; các lỗi về tràn số và mất chính xác thường chỉ xuất hiện ở biên miền giá trị.

## 14. Quy trình chọn kiểu số

Khi thiết kế DTO hoặc xử lý JSON động, hãy đi theo các bước:

1. Xác định ý nghĩa của trường: số đếm, định danh, tiền, tỷ lệ, phép đo hay giá trị kỹ thuật.
2. Xác định miền giá trị tối thiểu/tối đa và độ chính xác cần giữ.
3. Nếu schema ổn định, khai báo kiểu Java cụ thể trong DTO.
4. Nếu đọc dữ liệu không định kiểu, chọn feature phù hợp: `USE_LONG_FOR_INTS`, `USE_BIG_INTEGER_FOR_INTS` hoặc `USE_BIG_DECIMAL_FOR_FLOATS`.
5. Nếu chỉ một adapter cần chính sách riêng, dùng `ObjectReader` thay vì sửa mapper dùng chung.
6. Nếu dùng `JsonNode` hoặc Streaming API, kiểm tra token/type và range trước khi chuyển đổi.
7. Xác thực giá trị theo quy tắc nghiệp vụ sau khi parse.
8. Kiểm thử dữ liệu biên, số lớn, số thập phân và các dạng biểu diễn khác nhau.
9. Nếu JSON đi qua JavaScript hoặc hệ thống khác, kiểm tra khả năng giữ chính xác ở phía consumer.

## 15. Bảng ghi nhớ

| Nhu cầu | Kiểu hoặc cấu hình phù hợp |
|---|---|
| Số đếm có miền nhỏ, xác định | `int` / `Integer` |
| Số nguyên 64-bit | `long` / `Long` |
| Số nguyên rất lớn | `BigInteger` |
| Phép tính gần đúng | `double` / `Double` |
| Tiền và số thập phân cần chính xác | `BigDecimal` |
| Số nguyên không định kiểu muốn dùng Long | `USE_LONG_FOR_INTS` |
| Số nguyên không định kiểu muốn dùng BigInteger | `USE_BIG_INTEGER_FOR_INTS` |
| Số thập phân không định kiểu muốn dùng BigDecimal | `USE_BIG_DECIMAL_FOR_FLOATS` |
| Cần kiểm tra loại và miền số trong cây JSON | `JsonNode.isIntegralNumber()`, `numberType()`, `canConvertToLong()` |
| Cần đọc token số theo luồng | `JsonParser.getNumberType()`, `getBigIntegerValue()`, `getDecimalValue()` |

JSON không truyền theo nó thông tin `int`, `long`, `double` hay `BigDecimal`; ứng dụng phải lựa chọn cách biểu diễn. Với dữ liệu có schema rõ ràng, DTO khai báo kiểu cụ thể là lựa chọn dễ hiểu. Với `Object`, map hoặc collection không định kiểu, cần quyết định chính sách số của Jackson để tránh ép kiểu sai và mất chính xác. Đối với dữ liệu tiền hoặc số thập phân quan trọng, hãy dùng `BigDecimal` từ đầu và kiểm thử các giá trị biên thay vì chuyển đổi sau khi đã mất độ chính xác.
