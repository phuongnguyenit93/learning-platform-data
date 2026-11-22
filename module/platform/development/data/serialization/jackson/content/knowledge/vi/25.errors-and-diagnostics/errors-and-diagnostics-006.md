# Xử lý số vượt giới hạn và kiểu dữ liệu không tương thích

JSON chỉ có một dạng giá trị number, nhưng Java có nhiều kiểu số với miền giá trị và độ chính xác khác nhau: byte, short, int, long, float, double, BigInteger và BigDecimal. Khi Jackson đọc JSON, ứng dụng phải chuyển số trong payload sang kiểu Java được khai báo. Nếu số vượt miền, mất độ chính xác hoặc input có hình dạng không phù hợp, quá trình binding có thể thất bại hoặc tạo ra giá trị khác ý nghĩa mà producer gửi.

Vấn đề không chỉ là bắt exception. Một hợp đồng dữ liệu cần quy định rõ field nhận số nguyên hay số thập phân, giới hạn nhỏ nhất/lớn nhất, có chấp nhận chuỗi chứa số hay không, có cho phép làm tròn hay không và cần giữ độ chính xác đến mức nào.

Nguyên tắc quan trọng: **chọn kiểu Java đủ rộng cho miền dữ liệu, quy định coercion tường minh và kiểm tra range/precision trước khi đưa giá trị vào nghiệp vụ.** Không dựa vào ép kiểu Java hoặc default của Jackson để quyết định ý nghĩa dữ liệu.

## 1. JSON number và các kiểu số của Java

JSON có một kiểu dữ liệu number. Trong cú pháp JSON, số có thể được viết dưới dạng nguyên, thập phân hoặc exponent:

~~~json
12
-12
12.50
1.25e3
-4E-2
~~~

Jackson phân biệt các token số theo cách biểu diễn trong input:

- VALUE_NUMBER_INT: dạng số nguyên như 12 hoặc -12.
- VALUE_NUMBER_FLOAT: dạng có phần thập phân hoặc exponent như 12.0, 1.25e3.

Về mặt toán học, 12, 12.0 và 1.2e1 có thể biểu diễn cùng một giá trị. Nhưng ở cấp parser, chúng không nhất thiết có cùng token type. Sự khác biệt này quan trọng nếu hợp đồng yêu cầu field integer phải được gửi bằng cú pháp số nguyên.

Java có các kiểu số cơ bản:

| Kiểu | Miền giá trị / đặc điểm | Khi phù hợp |
|---|---|---|
| byte | -128 đến 127 | Dữ liệu nguyên rất nhỏ |
| short | -32,768 đến 32,767 | Dữ liệu nguyên giới hạn nhỏ |
| int | -2,147,483,648 đến 2,147,483,647 | Số lượng hoặc chỉ số có miền vừa |
| long | -9,223,372,036,854,775,808 đến 9,223,372,036,854,775,807 | ID số hoặc bộ đếm lớn |
| float | Số dấu phẩy động 32-bit, độ chính xác hữu hạn | Tính toán gần đúng khi cần ít bộ nhớ |
| double | Số dấu phẩy động 64-bit, độ chính xác hữu hạn | Tính toán khoa học hoặc gần đúng |
| BigInteger | Số nguyên có độ dài tùy theo bộ nhớ và giới hạn xử lý | Số nguyên vượt long |
| BigDecimal | Số thập phân chính xác theo biểu diễn decimal | Tiền, tỷ lệ và dữ liệu cần kiểm soát scale |

Không có một kiểu số tốt nhất cho mọi field. Kiểu đích phải phản ánh miền giá trị và semantics của dữ liệu.

## 2. Tràn số xảy ra khi nào?

Tràn số (overflow) xảy ra khi giá trị cần biểu diễn nằm ngoài miền của kiểu đích.

~~~java
int max = Integer.MAX_VALUE; // 2147483647
long maxLong = Long.MAX_VALUE;
~~~

JSON:

~~~json
{
  "quantity": 3000000000
}
~~~

Giá trị 3,000,000,000 lớn hơn Integer.MAX_VALUE. Nếu DTO khai báo:

~~~java
public record Request(int quantity) {}
~~~

Jackson không thể biểu diễn chính xác giá trị đó bằng int. Quá trình deserialize thường ném lỗi mapping/coercion thay vì tự động quay vòng thành một số âm như phép ép kiểu primitive Java.

Nếu field thực sự có thể vượt miền int, hãy dùng long hoặc BigInteger:

~~~java
public record Request(long quantity) {}
~~~

Hoặc:

~~~java
public record Request(BigInteger quantity) {}
~~~

Chọn kiểu lớn hơn chỉ giải quyết giới hạn biểu diễn. Ứng dụng vẫn cần kiểm tra giới hạn nghiệp vụ, ví dụ quantity không được âm hoặc không được vượt hạn mức cho phép.

### 2.1. Tràn số không giống giá trị sai nghiệp vụ

Một số có thể nằm trong miền int nhưng vẫn không hợp lệ:

~~~json
{
  "quantity": -5
}
~~~

-5 biểu diễn được bằng int, nên binding có thể thành công. Nếu quantity phải từ 1 đến 100, lỗi này thuộc validation nghiệp vụ.

Ngược lại, 3,000,000,000 không biểu diễn được bằng int. Đây là lỗi range khi chuyển đổi sang kiểu Java.

| Tình huống | Ví dụ | Lớp xử lý |
|---|---|---|
| Không biểu diễn được bằng kiểu đích | 3000000000 vào int | Databinding / numeric range |
| Biểu diễn được nhưng ngoài giới hạn API | -5 vào quantity | Validation |
| Kiểu JSON không được chấp nhận | "five" vào int | Coercion / format |
| Đúng kiểu và đúng range nhưng sai quan hệ nghiệp vụ | endDate trước startDate | Business validation |

## 3. Jackson xử lý số vượt miền như thế nào?

Khi deserialize một JSON number vào kiểu Java cụ thể, Jackson dùng deserializer tương ứng. Nếu giá trị không thể biểu diễn bằng kiểu đích, quá trình thường thất bại với lỗi mapping hoặc coercion.

~~~java
public record SmallCounter(int value) {}

String json = """
    {"value": 3000000000}
    """;

SmallCounter counter =
    mapper.readValue(json, SmallCounter.class);
~~~

Giá trị không vừa int nên Jackson không nên âm thầm wrap về một số khác. Exception cụ thể có thể khác theo đường đọc, phiên bản Jackson và target type; thường gặp các loại exception thuộc nhóm JsonMappingException hoặc InputCoercionException.

Không nên bắt mọi lỗi rồi thay bằng 0. Số 0 có thể là giá trị hợp lệ và việc thay thế sẽ che giấu dữ liệu bị lỗi.

### 3.1. Dùng long khi miền dữ liệu lớn hơn int

~~~java
public record CounterRequest(long value) {}
~~~

JSON 3,000,000,000 có thể binding vào long vì nằm trong miền long.

Nhưng nếu input lớn hơn Long.MAX_VALUE, long vẫn không đủ. Khi miền số không có giới hạn cố định phù hợp với kiểu primitive, dùng BigInteger.

### 3.2. Dùng BigInteger cho số nguyên rất lớn

~~~java
public record LedgerSequence(BigInteger sequence) {}
~~~

JSON:

~~~json
{
  "sequence": 1234567890123456789012345678901234567890
}
~~~

BigInteger có thể giữ chính xác số nguyên lớn mà không bị giới hạn 32/64-bit. Kích thước thực tế vẫn bị giới hạn bởi bộ nhớ, giới hạn độ dài token của Jackson và giới hạn tài nguyên ứng dụng.

Không nên dùng BigInteger cho mọi field. Kiểu này có chi phí và semantics khác int/long; chỉ dùng khi hợp đồng thực sự cho phép miền số lớn.

### 3.3. Dùng BigDecimal cho số thập phân chính xác

Với tiền hoặc tỷ lệ cần giữ decimal chính xác, dùng BigDecimal:

~~~java
public record PaymentRequest(BigDecimal amount) {}
~~~

JSON:

~~~json
{
  "amount": 12345678901234567890.1250
}
~~~

BigDecimal có thể giữ giá trị decimal và scale từ biểu diễn số được đọc. Điều này phù hợp hơn double khi cần so sánh, tính toán và làm tròn theo quy tắc tài chính.

## 4. Phân biệt precision và scale của BigDecimal

BigDecimal biểu diễn số thập phân với hai khái niệm:

- Precision: tổng số chữ số có nghĩa.
- Scale: số chữ số nằm bên phải dấu thập phân.

| Giá trị | Precision | Scale |
|---|---:|---:|
| 12 | 2 | 0 |
| 12.5 | 3 | 1 |
| 12.50 | 4 | 2 |
| 0.0125 | 3 | 4 |
| 123456.789 | 9 | 3 |

12.5 và 12.50 có cùng giá trị số nhưng scale khác nhau. Nếu scale là một phần của hợp đồng, không nên tự ý chuẩn hóa hoặc làm tròn mà không có quy tắc.

### 4.1. Không dùng double cho tiền chỉ vì JSON có number

double dùng biểu diễn dấu phẩy động nhị phân. Nhiều số thập phân không thể được biểu diễn chính xác bằng binary floating point.

~~~java
double value = 0.1 + 0.2;
System.out.println(value); // thường hiển thị 0.30000000000000004
~~~

Với BigDecimal:

~~~java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");

BigDecimal result = a.add(b);
// 0.3
~~~

Hãy tạo BigDecimal từ chuỗi decimal hoặc để Jackson đọc trực tiếp JSON number vào BigDecimal. Tránh:

~~~java
new BigDecimal(0.1)
~~~

vì giá trị double đã mang sai số nhị phân trước khi được chuyển sang BigDecimal.

### 4.2. Làm tròn khác với kiểm tra scale

Nếu hợp đồng cho phép tối đa hai chữ số thập phân, có hai chính sách khác nhau.

Làm tròn:

~~~java
BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_UP);
~~~

Từ chối nếu cần làm tròn:

~~~java
BigDecimal exact = amount.setScale(2, RoundingMode.UNNECESSARY);
~~~

UNNECESSARY ném ArithmeticException nếu không thể biểu diễn ở scale yêu cầu mà không làm tròn.

Không dùng setScale(2, HALF_UP) như một cách validation nếu hợp đồng phải từ chối input có quá nhiều chữ số thập phân. Nó thay đổi dữ liệu người gửi đã cung cấp.

### 4.3. Kiểm tra precision và scale

Có thể kiểm tra tường minh:

~~~java
if (amount.precision() > 12 || amount.scale() > 2) {
    throw new IllegalArgumentException("Amount precision/scale is invalid");
}
~~~

Cần xem xét số âm và scale âm do exponent. Nếu hợp đồng cho phép exponent, BigDecimal có thể có scale âm. Định nghĩa rõ quy tắc thay vì chỉ dựa vào một phép so sánh scale đơn giản.

Bean Validation có @Digits:

~~~java
public record PaymentRequest(
    @Digits(integer = 10, fraction = 2)
    BigDecimal amount
) {}
~~~

@Digits kiểm tra số chữ số phần nguyên và phần thập phân theo semantics của BigDecimal. Nó không tự làm tròn giá trị.

## 5. Số thập phân bị chuyển thành số nguyên

Một trường hợp không tương thích phổ biến là JSON gửi số có phần thập phân nhưng DTO khai báo int hoặc long.

~~~json
{
  "quantity": 5.8
}
~~~

Jackson có feature DeserializationFeature.ACCEPT_FLOAT_AS_INT. Trong nhiều cấu hình Jackson 2, feature này mặc định được bật; khi được phép, floating-point input có thể được chuyển sang kiểu integral theo quy tắc chuyển đổi của deserializer, thường loại bỏ phần thập phân.

Điều đó có thể tạo ra kết quả quantity = 5 dù producer gửi 5.8.

Nếu quantity phải là số nguyên JSON, hãy từ chối float:

~~~java
ObjectMapper strictMapper = JsonMapper.builder()
    .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
    .build();
~~~

Từ Jackson 2.12, có thể dùng CoercionConfig để thể hiện chính sách theo logical type:

~~~java
strictMapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(
        CoercionInputShape.Float,
        CoercionAction.Fail
    );
~~~

Nếu hợp đồng muốn chấp nhận 5.0 nhưng không chấp nhận 5.8, đó là quy tắc khác với việc chỉ tắt float-to-int. Cần parse bằng BigDecimal, kiểm tra phần thập phân bằng 0 rồi kiểm tra range trước khi chuyển thành int/long. Không dựa vào phép ép kiểu để tự quyết định.

### 5.1. Số nguyên viết dưới dạng decimal token

Các input sau có giá trị toán học tương đương:

~~~json
5
5.0
5e0
~~~

Nhưng parser có thể phát ra VALUE_NUMBER_INT cho 5 và VALUE_NUMBER_FLOAT cho hai dạng còn lại.

Nếu hợp đồng chỉ chấp nhận cú pháp integer token, hãy từ chối float token. Nếu hợp đồng chỉ quan tâm giá trị toán học nguyên, hãy chấp nhận decimal khi phần thập phân bằng 0 và vẫn kiểm tra range.

Đây là quyết định schema, không nên để default coercion ngầm quyết định.

## 6. String chứa số và coercion

Một số client gửi số dưới dạng JSON string:

~~~json
{
  "quantity": "25"
}
~~~

Jackson có thể chuyển chuỗi số thành kiểu số trong một số cấu hình mặc định. Nhưng string và number là hai JSON type khác nhau. Nếu schema yêu cầu quantity là number, chấp nhận "25" có thể che giấu lỗi producer.

Cần quyết định:

- Chấp nhận chuỗi chỉ chứa chữ số hay cả dấu âm?
- Có trim whitespace không?
- Có cho phép dấu thập phân/exponent không?
- Chuỗi rỗng có được coi là null không?
- Có cho phép dấu phân cách hàng nghìn không?
- Có giới hạn độ dài chuỗi số không?

### 6.1. Từ chối string-to-integer bằng CoercionConfig

~~~java
ObjectMapper strictMapper = JsonMapper.builder().build();

strictMapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(CoercionInputShape.String, CoercionAction.Fail)
    .setCoercion(CoercionInputShape.EmptyString, CoercionAction.Fail);
~~~

Có thể cấu hình tương tự cho LogicalType.Float nếu string number cũng phải bị từ chối:

~~~java
strictMapper.coercionConfigFor(LogicalType.Float)
    .setCoercion(CoercionInputShape.String, CoercionAction.Fail)
    .setCoercion(CoercionInputShape.EmptyString, CoercionAction.Fail);
~~~

CoercionConfig có các hành động như:

| CoercionAction | Ý nghĩa |
|---|---|
| Fail | Từ chối input shape |
| TryConvert | Thử chuyển đổi theo deserializer |
| AsNull | Xem input như null |
| AsEmpty | Dùng empty value của kiểu đích |

AsNull hoặc AsEmpty có thể làm mất dữ liệu nếu client gửi chuỗi sai nhưng ứng dụng vẫn tiếp tục với null/empty. Chỉ sử dụng khi hợp đồng định nghĩa rõ semantics đó.

### 6.2. Khi chuỗi số là hợp đồng hợp lệ

Nếu API thật sự quy định số dưới dạng string, hãy khai báo DTO là String hoặc dùng custom deserializer/value object để kiểm tra grammar:

~~~java
public record AccountNumber(String value) {
    public AccountNumber {
        if (value == null || !value.matches("[0-9]{1,20}")) {
            throw new IllegalArgumentException("Invalid account number");
        }
    }
}
~~~

Không nên khai báo long cho một mã định danh chỉ có chữ số nếu phép cộng/trừ không có ý nghĩa. Mã tài khoản, mã bưu chính hoặc số điện thoại thường là identifier dạng string, vì có thể có số 0 ở đầu và không phải đại lượng để tính toán.

## 7. Dùng feature cho số trong untyped Object và Map

Khi DTO khai báo kiểu cụ thể như int, long hoặc BigDecimal, Jackson dùng target type đó. Nhưng khi đọc JSON vào Object hoặc Map<String, Object>, Jackson phải tự chọn kiểu Java cho number.

Các feature liên quan:

| Feature | Ảnh hưởng |
|---|---|
| USE_LONG_FOR_INTS | Với integer trong untyped context, ưu tiên Long thay vì Integer khi phù hợp |
| USE_BIG_INTEGER_FOR_INTS | Với integer trong untyped context, dùng BigInteger |
| USE_BIG_DECIMAL_FOR_FLOATS | Với floating-point trong untyped context, dùng BigDecimal thay vì Double |

Ví dụ:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.USE_BIG_INTEGER_FOR_INTS)
    .enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS)
    .build();

Map<String, Object> values = mapper.readValue(
    """
    {
      "sequence": 123456789012345678901234567890,
      "amount": 0.10
    }
    """,
    new TypeReference<Map<String, Object>>() {}
);
~~~

Integer lớn có thể trở thành BigInteger và số thập phân thành BigDecimal.

Các feature này chủ yếu ảnh hưởng cách Jackson chọn kiểu khi target là Object/Number hoặc cấu trúc untyped. Chúng không tự thay đổi field đã khai báo là int thành BigInteger. Nếu DTO có int quantity, target vẫn là int và range vẫn phải được đáp ứng.

### 7.1. Không dựa vào kiểu suy luận trong Map cho hợp đồng ổn định

Một Map<String, Object> làm giảm type safety. Cùng một field có thể trở thành Integer, Long, BigInteger hoặc Double tùy giá trị và cấu hình.

Nếu schema ổn định, dùng DTO có kiểu cụ thể:

~~~java
public record LedgerEntry(
    BigInteger sequence,
    BigDecimal amount
) {}
~~~

Map untyped phù hợp với metadata động hoặc payload linh hoạt, nhưng tầng nghiệp vụ nên chuyển về kiểu rõ ràng và validate.

## 8. Tràn số trong Streaming API

Khi dùng JsonParser trực tiếp, các phương thức đọc số có kiểm tra khả năng chuyển đổi sang kiểu được yêu cầu.

~~~java
JsonParser parser = factory.createParser(input);

if (parser.nextToken() != JsonToken.VALUE_NUMBER_INT) {
    throw new IOException("Expected an integer token");
}

int value = parser.getIntValue();
~~~

Nếu token có giá trị vượt Integer.MAX_VALUE hoặc nhỏ hơn Integer.MIN_VALUE, getIntValue() có thể ném InputCoercionException thay vì wrap.

| Phương thức | Kiểu kết quả |
|---|---|
| getIntValue() | int |
| getLongValue() | long |
| getBigIntegerValue() | BigInteger |
| getFloatValue() | float |
| getDoubleValue() | double |
| getDecimalValue() | BigDecimal |
| getNumberValue() | Number được parser chọn |
| getNumberType() | Phân loại kiểu số của token |

Ví dụ đọc số nguyên lớn:

~~~java
if (parser.currentToken() != JsonToken.VALUE_NUMBER_INT) {
    throw new IOException("Expected an integer");
}

BigInteger value = parser.getBigIntegerValue();
~~~

Ví dụ đọc decimal chính xác:

~~~java
if (parser.currentToken() != JsonToken.VALUE_NUMBER_INT
        && parser.currentToken() != JsonToken.VALUE_NUMBER_FLOAT) {
    throw new IOException("Expected a JSON number");
}

BigDecimal amount = parser.getDecimalValue();
~~~

Sau đó kiểm tra range nghiệp vụ:

~~~java
if (amount.compareTo(BigDecimal.ZERO) < 0
        || amount.compareTo(new BigDecimal("1000000.00")) > 0) {
    throw new IOException("Amount is outside the allowed range");
}
~~~

Đọc bằng BigInteger/BigDecimal giúp tránh ép sang kiểu hẹp quá sớm. Nhưng vẫn cần giới hạn độ dài token và giá trị tối đa theo nghiệp vụ.

## 9. Kiểm tra range trước khi chuyển kiểu

Không nên dùng phép ép kiểu narrowing để kiểm tra range:

~~~java
long raw = 3_000_000_000L;
int quantity = (int) raw;
~~~

Phép ép kiểu này có thể làm mất các bit cao và tạo ra một số khác. Nó không ném exception khi vượt miền.

Dùng kiểm tra tường minh:

~~~java
static int toIntExact(BigInteger value) {
    if (value.compareTo(BigInteger.valueOf(Integer.MIN_VALUE)) < 0
            || value.compareTo(BigInteger.valueOf(Integer.MAX_VALUE)) > 0) {
        throw new IllegalArgumentException("Value does not fit in int");
    }

    return value.intValue();
}
~~~

Hoặc với BigDecimal:

~~~java
int quantity = decimal.intValueExact();
~~~

intValueExact() từ chối nếu có phần thập phân khác 0 hoặc giá trị vượt miền int.

Tương tự:

- longValueExact() kiểm tra số nguyên có vừa long.
- shortValueExact() và byteValueExact() kiểm tra miền hẹp hơn.
- toBigIntegerExact() từ chối phần thập phân khác 0.

Các phương thức exact diễn đạt đúng ý định hơn intValue() hoặc longValue() khi cần bảo toàn dữ liệu.

## 10. Precision của float và double

float và double có miền biểu diễn rộng nhưng độ chính xác hữu hạn. Một số JSON number rất lớn có thể vượt miền hữu hạn; số rất nhỏ có thể bị underflow khi chuyển sang kiểu dấu phẩy động.

Ví dụ:

- Float có khoảng 7 chữ số thập phân có nghĩa.
- Double có khoảng 15–16 chữ số thập phân có nghĩa.
- Các giá trị thập phân như 0.1 thường không biểu diễn chính xác trong binary floating point.

Nếu dữ liệu cần giữ số chữ số chính xác, dùng BigDecimal. Nếu dữ liệu dùng cho đo lường hoặc tính toán gần đúng, float/double có thể phù hợp nhưng cần quy định sai số chấp nhận được.

### 10.1. Không so sánh double bằng == cho kết quả tính toán

~~~java
double total = 0.1 + 0.2;

if (total == 0.3) {
    // Không nên dựa vào nhánh này.
}
~~~

Có thể dùng epsilon:

~~~java
double epsilon = 1e-9;

if (Math.abs(total - 0.3) < epsilon) {
    // Hai giá trị đủ gần theo tolerance đã chọn.
}
~~~

Tolerance phải theo đơn vị và quy mô dữ liệu. Với tiền, dùng BigDecimal và quy tắc rounding cụ thể thay vì epsilon.

### 10.2. NaN và Infinity không phải JSON number hợp lệ

JSON chuẩn không có token NaN, Infinity hoặc -Infinity. Nếu Java object chứa Double.NaN hoặc Double.POSITIVE_INFINITY, Jackson có thể xử lý theo cấu hình generator, thường ghi dưới dạng chuỗi được quote để tránh phát ra JSON number không hợp lệ.

Đừng để những giá trị này lọt vào hợp đồng như một con số bình thường. Kiểm tra:

~~~java
if (!Double.isFinite(value)) {
    throw new IllegalArgumentException("Value must be finite");
}
~~~

Nếu domain cần biểu diễn trạng thái không xác định, hãy dùng null, một enum hoặc object có trạng thái rõ ràng theo hợp đồng.

## 11. Numeric identifier và giới hạn của JavaScript

Một long Java có thể giữ chính xác số đến Long.MAX_VALUE. Nhưng nhiều client JavaScript dùng Number theo IEEE-754 double và chỉ biểu diễn chính xác mọi số nguyên đến:

~~~text
2^53 - 1 = 9007199254740991
~~~

Nếu API gửi một ID lớn hơn giới hạn đó dưới dạng JSON number, client JavaScript có thể làm tròn và gửi lại một ID khác.

Ví dụ:

~~~json
{
  "id": 9007199254740993
}
~~~

Jackson phía Java có thể đọc chính xác vào long hoặc BigInteger, nhưng client JavaScript có thể không giữ được giá trị nguyên ban đầu.

Với ID lớn, account number hoặc mã định danh không dùng để tính toán, nên cân nhắc JSON string:

~~~json
{
  "id": "9007199254740993"
}
~~~

Đây là quyết định hợp đồng API. Nếu đổi number thành string, client cũ cần được migration; không tự ý đổi representation mà không quản lý version.

## 12. Kiểu JSON không tương thích với kiểu Java

Ngoài range, input có thể sai JSON shape hoặc sai scalar type.

DTO:

~~~java
public record Request(int quantity, boolean active) {}
~~~

Payload có thể gặp:

| JSON input | Target | Vấn đề |
|---|---|---|
| "5" | int | String-to-number coercion |
| 5.5 | int | Float-to-integer coercion |
| true | int | Sai scalar type |
| {"value":5} | int | Object thay vì number |
| [5] | int | Array thay vì scalar |
| "yes" | boolean | String không theo boolean grammar |
| 1 | boolean | Number thay vì boolean |
| null | int | Null cho primitive |
| field bị thiếu | int | Default primitive hoặc creator policy |

Không nên giả định Jackson luôn từ chối mọi trường hợp sai kiểu. Một số scalar coercion được hỗ trợ tùy target type và cấu hình. Hãy cấu hình rõ các chuyển đổi mà API cho phép.

### 12.1. Object hoặc array vào scalar

~~~json
{
  "quantity": {
    "value": 5
  }
}
~~~

Nếu target là int, Jackson không thể coi object này như số nguyên nếu không có custom deserializer quy định cách làm. Lỗi thường thuộc nhóm MismatchedInputException/JsonMappingException.

Không tự lấy field value từ object lạ chỉ vì nó có tên value. Nếu API muốn object, khai báo DTO:

~~~java
public record QuantityValue(int value) {}
~~~

Nếu API muốn scalar, producer phải gửi number theo schema.

### 12.2. Boolean và number không nên thay thế nhau

Không coi true là 1 hoặc false là 0 trừ khi hợp đồng legacy quy định rõ. Boolean thể hiện trạng thái hai giá trị; number thể hiện đại lượng. Coercion giữa hai loại có thể làm mất ý nghĩa và gây lỗi nghiệp vụ.

## 13. Primitive, wrapper và null

Primitive không thể giữ Java null. Wrapper như Integer, Long và BigDecimal có thể.

~~~java
public record PrimitiveRequest(int quantity) {}
public record WrapperRequest(Integer quantity) {}
~~~

Nếu JSON gửi:

~~~json
{
  "quantity": null
}
~~~

Với primitive, Jackson có thể gán giá trị mặc định 0 nếu không bật feature từ chối null cho primitive. Có thể bật:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .enable(DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES)
    .build();
~~~

Wrapper Integer có thể nhận null. Nhưng null có hợp lệ hay không là vấn đề validation.

Cần phân biệt:

- Field missing.
- Field explicit null.
- Field có giá trị 0.
- Field có giá trị vượt range.

Không dùng primitive nếu API cần phân biệt null với 0. Với request DTO, wrapper thường giúp validation và presence semantics rõ hơn; tuy nhiên missing và explicit null vẫn có thể cùng thành null nếu không có cơ chế presence riêng.

## 14. Coercion policy cho số bằng CoercionConfig

Từ Jackson 2.12, CoercionConfig cho phép quy định hành vi theo LogicalType hoặc kiểu Java cụ thể.

Ví dụ strict policy cho integer:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
    .build();

mapper.coercionConfigFor(LogicalType.Integer)
    .setCoercion(CoercionInputShape.String, CoercionAction.Fail)
    .setCoercion(CoercionInputShape.EmptyString, CoercionAction.Fail)
    .setCoercion(CoercionInputShape.Float, CoercionAction.Fail);
~~~

Với kiểu số thập phân:

~~~java
mapper.coercionConfigFor(LogicalType.Float)
    .setCoercion(CoercionInputShape.String, CoercionAction.Fail)
    .setCoercion(CoercionInputShape.EmptyString, CoercionAction.Fail);
~~~

Chính sách này nói rằng field số phải nhận JSON number đúng shape; chuỗi số và chuỗi rỗng bị từ chối.

Có thể cấu hình class cụ thể nếu chỉ một target type cần policy riêng:

~~~java
mapper.coercionConfigFor(Integer.class)
    .setCoercion(CoercionInputShape.String, CoercionAction.Fail);
~~~

Cấu hình class cụ thể giúp giới hạn phạm vi hơn LogicalType. Khi có nhiều cấp cấu hình, hãy test trên đúng phiên bản Jackson để xác nhận rule áp dụng như mong muốn.

### 14.1. Không dùng một mapper strict cho mọi hợp đồng một cách máy móc

Một hệ thống có thể nhận payload từ đối tác cũ vẫn gửi string number. Có thể cần mapper compatible ở adapter đó, trong khi API mới dùng strict mapper.

Nên:

- Chia policy theo ranh giới tích hợp.
- Không thay đổi cấu hình mapper dùng chung sau khi đã sử dụng.
- Tạo mapper/ObjectReader riêng nếu hợp đồng thực sự khác nhau.
- Ghi nhận và theo dõi payload legacy.
- Có kế hoạch loại bỏ coercion cũ khi producer đã nâng cấp.

Mapper thường được cấu hình xong rồi tái sử dụng. Không sửa CoercionConfig dùng chung theo từng request vì có thể gây hành vi khác nhau giữa các luồng xử lý.

## 15. Chọn kiểu số cho untyped input

Nếu đọc vào JsonNode, có thể kiểm tra kiểu node trước khi lấy giá trị:

~~~java
JsonNode node = root.path("amount");

if (!node.isNumber()) {
    throw new IllegalArgumentException("amount must be a JSON number");
}

BigDecimal amount = node.decimalValue();
~~~

Nếu đọc vào Object hoặc Map<String, Object>, kiểu Java của số phụ thuộc feature và giá trị. Khi cần kiểm soát, dùng JsonNode hoặc DTO có kiểu rõ.

~~~java
JsonNode root = mapper.readTree(json);
JsonNode sequence = root.path("sequence");

if (!sequence.isIntegralNumber()) {
    throw new IllegalArgumentException("sequence must be an integer token");
}

BigInteger exact = sequence.bigIntegerValue();
~~~

bigIntegerValue() diễn đạt rằng ứng dụng muốn giữ số nguyên lớn. Nếu node là floating-point, hãy từ chối trước thay vì tự cắt phần thập phân.

## 16. Giới hạn độ dài số và chống payload gây cạn tài nguyên

BigInteger và BigDecimal có thể biểu diễn số rất lớn, nhưng điều đó không có nghĩa ứng dụng nên chấp nhận token dài tùy ý.

Một JSON number có thể chứa hàng triệu chữ số hoặc exponent cực lớn. Parse số đó tiêu tốn CPU và bộ nhớ.

Jackson 2.15+ có StreamReadConstraints để giới hạn độ sâu và độ dài token, bao gồm number length:

~~~java
StreamReadConstraints constraints =
    StreamReadConstraints.builder()
        .maxNumberLength(1_000)
        .maxStringLength(1_000_000)
        .maxNestingDepth(100)
        .build();

JsonFactory factory = JsonFactory.builder()
    .streamReadConstraints(constraints)
    .build();

ObjectMapper mapper = new ObjectMapper(factory);
~~~

Các giới hạn trên chỉ là ví dụ. Chọn theo schema và payload thực tế.

Ngoài giới hạn parser, cần giới hạn:

- Kích thước HTTP request/file.
- Số field và số record.
- Thời gian xử lý.
- Số chữ số precision/scale được phép.
- Range nghiệp vụ.
- Tần suất request và kích thước batch.

Giới hạn độ dài token không thay thế validation giá trị. Một số có 20 chữ số vẫn có thể vượt hạn mức nghiệp vụ dù parser chấp nhận.

## 17. Các loại exception khi số hoặc kiểu dữ liệu không tương thích

Tên exception phụ thuộc đường đọc, phiên bản và loại lỗi. Một số loại thường gặp:

| Exception | Trường hợp thường gặp |
|---|---|
| JsonParseException | JSON sai cú pháp hoặc token không hợp lệ |
| InputCoercionException | Parser không thể chuyển token sang kiểu được yêu cầu hoặc giá trị vượt miền |
| InvalidFormatException | Giá trị không thể chuyển sang target format, ví dụ chuỗi không phải số |
| MismatchedInputException | Hình dạng input không phù hợp target, ví dụ object vào int |
| JsonMappingException | Lỗi databinding tổng quát, thường có path đến property |
| StreamConstraintsException | Vượt giới hạn đọc như độ dài number/token hoặc nesting |

Không nên phụ thuộc vào exact exception class nếu cùng một hợp đồng được đọc qua nhiều API. Hãy xác định lỗi ở cấp ứng dụng: malformed JSON, wrong JSON type, numeric overflow, precision/scale violation hay business range violation.

### 17.1. Đọc path của lỗi

JsonMappingException thường mang thông tin đường dẫn đến property gây lỗi. Có thể lấy:

~~~java
catch (JsonMappingException ex) {
    String path = ex.getPathReference();
    throw new InvalidPayloadException(
        "Invalid value at " + path,
        ex
    );
}
~~~

Không nên trả stack trace hoặc toàn bộ payload cho client. API response nên có mã lỗi và đường dẫn field có thể hiểu được, ví dụ:

~~~json
{
  "code": "INVALID_NUMBER",
  "field": "items[2].quantity",
  "message": "quantity must be an integer within the supported range"
}
~~~

Thông báo nên mô tả yêu cầu schema, không cần tiết lộ chi tiết nội bộ của Jackson.

## 18. Tách binding, range validation và business validation

Một pipeline rõ ràng:

~~~text
JSON parsing
     |
     v
Type binding / coercion
     |
     v
Numeric representability
     |
     v
Bean Validation
     |
     v
Business validation
     |
     v
Domain operation
~~~

Ví dụ DTO:

~~~java
public record TransferRequest(
    @NotNull
    @Digits(integer = 15, fraction = 2)
    @DecimalMin("0.01")
    @DecimalMax("1000000000.00")
    BigDecimal amount,

    @NotNull
    @Min(1)
    @Max(100000)
    Integer installmentCount
) {}
~~~

Sau khi Jackson binding thành công, Bean Validation kiểm tra null, precision/scale và range theo annotation.

Lưu ý:

- @Digits không thay thế parser range; giá trị phải được binding thành BigDecimal trước.
- @Min/@Max kiểm tra giá trị sau binding.
- Bean Validation không quyết định có chấp nhận string number hay float-to-int hay không.
- Business validation có thể kiểm tra quan hệ giữa nhiều field hoặc giới hạn theo tài khoản.
- Nếu DTO dùng primitive, @NotNull không thể phát hiện JSON null đã trở thành 0; chọn wrapper khi cần semantics null.

## 19. Thiết kế DTO theo miền giá trị

| Field | Kiểu thường phù hợp | Lý do |
|---|---|---|
| Số lượng sản phẩm nhỏ | int hoặc Integer | Miền nhỏ, dùng phép tính nguyên |
| Tổng số bản ghi rất lớn | long | Bộ đếm 64-bit |
| Sequence vượt 64-bit | BigInteger | Không giới hạn 64-bit |
| Giá tiền | BigDecimal | Decimal chính xác và scale rõ |
| Tỷ lệ phần trăm | BigDecimal | Cần precision/scale theo hợp đồng |
| Điểm đo gần đúng | double | Sai số floating-point chấp nhận được |
| Mã tài khoản có số 0 đầu | String | Identifier, không phải đại lượng |
| ID lớn gửi cho JavaScript | String có thể phù hợp | Tránh mất integer precision ở client |
| Boolean trạng thái | boolean/Boolean | Không nên thay bằng 0/1 nếu không có contract |

Đừng chọn Long chỉ vì nó lớn hơn Integer. Nếu giá trị là mã định danh, dùng String có thể đúng semantics hơn. Đừng chọn BigDecimal cho số đếm nếu domain yêu cầu số nguyên; dùng BigInteger khi cần số nguyên rất lớn.

## 20. Kiểm thử overflow và kiểu không tương thích

Test nên bao phủ boundary và các dạng input bị từ chối. Đừng chỉ test một số bình thường.

### 20.1. Boundary của int

~~~java
@Test
void acceptsIntegerBoundaries() throws Exception {
    IntRequest min = mapper.readValue(
        "{\"value\":-2147483648}",
        IntRequest.class
    );

    IntRequest max = mapper.readValue(
        "{\"value\":2147483647}",
        IntRequest.class
    );

    assertEquals(Integer.MIN_VALUE, min.value());
    assertEquals(Integer.MAX_VALUE, max.value());
}
~~~

### 20.2. Từ chối overflow

~~~java
@Test
void rejectsIntegerOverflow() {
    assertThrows(JsonProcessingException.class, () ->
        mapper.readValue(
            "{\"value\":2147483648}",
            IntRequest.class
        )
    );
}
~~~

Test này xác nhận input vượt miền int không được âm thầm wrap. Tùy phiên bản và đường binding, exception cụ thể có thể là subclass khác của JsonProcessingException; chọn assertion theo hợp đồng lỗi của ứng dụng nếu cần ổn định giữa các phiên bản.

### 20.3. Từ chối float cho integer

~~~java
@Test
void rejectsFloatingPointForIntegerWhenStrict() {
    ObjectMapper strict = JsonMapper.builder()
        .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
        .build();

    assertThrows(JsonProcessingException.class, () ->
        strict.readValue("{\"value\":5.8}", IntRequest.class)
    );
}
~~~

### 20.4. Từ chối string number khi strict

~~~java
@Test
void rejectsStringNumberWhenStrict() {
    ObjectMapper strict = JsonMapper.builder().build();

    strict.coercionConfigFor(LogicalType.Integer)
        .setCoercion(
            CoercionInputShape.String,
            CoercionAction.Fail
        );

    assertThrows(JsonProcessingException.class, () ->
        strict.readValue("{\"value\":\"5\"}", IntRequest.class)
    );
}
~~~

### 20.5. Giữ precision với BigDecimal

~~~java
@Test
void readsDecimalWithoutDoubleConversion() throws Exception {
    PaymentRequest request = mapper.readValue(
        "{\"amount\":0.10}",
        PaymentRequest.class
    );

    assertEquals(new BigDecimal("0.10"), request.amount());
}
~~~

Test này giả định DTO khai báo BigDecimal và mapper đọc trực tiếp JSON number vào target đó.

### 20.6. Kiểm tra exact integer conversion

~~~java
@Test
void rejectsFractionalBigDecimalAsInteger() {
    BigDecimal value = new BigDecimal("5.8");

    assertThrows(ArithmeticException.class, value::intValueExact);
}
~~~

### 20.7. Ma trận test đề xuất

| Target | JSON input | Kết quả mong muốn theo strict contract |
|---|---|---|
| int | 2147483647 | Chấp nhận |
| int | 2147483648 | Từ chối overflow |
| int | -2147483648 | Chấp nhận |
| int | -2147483649 | Từ chối overflow |
| int | 5.0 | Từ chối nếu chỉ nhận integer token |
| int | "5" | Từ chối nếu không cho string coercion |
| int | true | Từ chối |
| int | null | Theo null/primitive policy |
| long | 9223372036854775807 | Chấp nhận |
| long | 9223372036854775808 | Từ chối |
| BigInteger | Số nguyên rất lớn | Chấp nhận trong giới hạn token/tài nguyên |
| BigDecimal | 0.10 | Giữ decimal theo target BigDecimal |
| BigDecimal | Số vượt precision/scale contract | Binding có thể thành công, validation từ chối |
| double | 0.1 | Chấp nhận gần đúng theo floating-point semantics |
| double | Số vượt miền hữu hạn | Từ chối hoặc xử lý theo policy rõ |
| String ID | "000123" | Giữ số 0 đầu |

## 21. Test untyped numeric behavior

Nếu ứng dụng đọc vào Map<String, Object>, hãy test kiểu runtime được tạo:

~~~java
@Test
void usesBigNumberTypesForUntypedValues() throws Exception {
    ObjectMapper configured = JsonMapper.builder()
        .enable(DeserializationFeature.USE_BIG_INTEGER_FOR_INTS)
        .enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS)
        .build();

    Map<String, Object> values = configured.readValue(
        """
        {
          "sequence": 123456789012345678901234567890,
          "amount": 0.10
        }
        """,
        new TypeReference<Map<String, Object>>() {}
    );

    assertInstanceOf(BigInteger.class, values.get("sequence"));
    assertInstanceOf(BigDecimal.class, values.get("amount"));
}
~~~

Đây là test cho untyped numeric mapping. Nếu DTO khai báo BigInteger/BigDecimal rõ ràng, không cần feature này để có target type tương ứng.

## 22. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| int bị overflow | Chọn kiểu đích quá hẹp | Dùng long/BigInteger hoặc từ chối input |
| Phép cast long sang int tạo số khác | Narrowing conversion không kiểm tra range | Dùng exact conversion hoặc compare min/max |
| 5.8 thành 5 | Cho phép float-to-int coercion | Tắt ACCEPT_FLOAT_AS_INT hoặc cấu hình Fail |
| "5" được nhận như số | String-to-number coercion | Cấu hình CoercionConfig theo contract |
| Tiền bị sai số | Dùng double/float | Dùng BigDecimal |
| BigDecimal bị làm tròn âm thầm | Gọi setScale với rounding mode | Dùng UNNECESSARY hoặc validation |
| ID lớn bị client JavaScript đổi giá trị | Number vượt safe integer range | Gửi ID dưới dạng string |
| Số trong Map có kiểu runtime không ổn định | Đọc vào Object/Number | Dùng DTO hoặc cấu hình USE_BIG_INTEGER/USE_BIG_DECIMAL |
| null biến thành 0 | Primitive null policy | Dùng wrapper hoặc FAIL_ON_NULL_FOR_PRIMITIVES |
| Object vào field int | JSON shape không tương thích | Sửa schema hoặc custom deserializer có chủ đích |
| Payload số cực dài gây tốn tài nguyên | Không giới hạn number token | Dùng StreamReadConstraints và giới hạn request |
| Validation không chạy | Chỉ deserialize mà không gọi validator | Kích hoạt Bean Validation sau binding |
| Bắt mọi exception rồi trả 0 | Che giấu dữ liệu sai | Trả lỗi có field path và nguyên nhân rõ |

## 23. Quy trình xử lý số và kiểu dữ liệu không tương thích

1. Xác định semantics field: đại lượng, số đếm, tiền hay identifier.
2. Chọn kiểu Java có miền giá trị và precision phù hợp.
3. Quy định JSON shape: integer token, number, string hoặc object.
4. Quy định có cho phép string-to-number và float-to-int coercion không.
5. Cấu hình CoercionConfig và các DeserializationFeature cần thiết.
6. Với số lớn, dùng long/BigInteger; với decimal chính xác, dùng BigDecimal.
7. Kiểm tra range và precision/scale trước khi thực hiện nghiệp vụ.
8. Phân biệt binding error với validation error.
9. Giới hạn độ dài number token và kích thước request.
10. Chuẩn hóa lỗi thành mã/field path dễ hiểu cho client.
11. Test min/max, overflow, underflow, fractional, string, null và sai JSON shape.
12. Test cả DTO có kiểu rõ và untyped Map nếu ứng dụng sử dụng.
13. Khi nâng Jackson hoặc thay mapper configuration, chạy lại contract fixtures.

## 24. Nguyên tắc nên giữ

- Không dùng kiểu số hẹp hơn miền dữ liệu của hợp đồng.
- Jackson không nên âm thầm wrap giá trị vượt miền target.
- Dùng BigInteger cho integer vượt long và BigDecimal cho decimal cần chính xác.
- Không dùng double cho tiền hoặc dữ liệu cần so sánh decimal chính xác.
- Phân biệt 5, 5.0 và "5" theo contract dù chúng có thể biểu diễn giá trị gần nhau.
- Tắt ACCEPT_FLOAT_AS_INT nếu field integer không được nhận float.
- Dùng CoercionConfig để quy định rõ string, empty string và input shape khác.
- Dùng USE_BIG_INTEGER_FOR_INTS/USE_BIG_DECIMAL_FOR_FLOATS cho untyped numeric data khi cần.
- Kiểm tra range, precision và scale ở tầng phù hợp.
- Dùng String cho identifier nếu phép tính số không có ý nghĩa hoặc cần giữ số 0 đầu.
- Cân nhắc JavaScript safe integer limit khi phát hành ID lớn dưới dạng JSON number.
- Giới hạn độ dài number token và tổng payload.
- Phân biệt lỗi parse, coercion, overflow và validation.
- Kiểm thử boundary values và payload sai kiểu như một phần hợp đồng API.

Xử lý số vượt giới hạn và kiểu không tương thích cần phối hợp giữa kiểu Java, Jackson coercion policy và validation nghiệp vụ. Kiểu đích phải đủ rộng để biểu diễn dữ liệu hợp lệ; input sai shape hoặc vượt range phải bị từ chối theo quy tắc công bố; số thập phân cần chính xác phải dùng BigDecimal. Khi kiểm thử cả boundary, precision, string coercion và payload sai kiểu, ứng dụng sẽ tránh được việc âm thầm đổi ý nghĩa dữ liệu trong quá trình deserialize.

