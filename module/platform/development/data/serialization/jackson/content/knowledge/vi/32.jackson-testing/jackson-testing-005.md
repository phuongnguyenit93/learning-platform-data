# Kiểm thử số lớn, số thập phân và giá trị biên

## 1. Vì sao dữ liệu số cần được kiểm thử riêng?

JSON có một dạng cú pháp number chung. Một giá trị như 42, 3.14 hoặc 1.2e10 đều được viết dưới dạng số trong JSON. Nhưng khi Jackson ánh xạ chúng sang Java, kiểu đích có thể là byte, short, int, long, BigInteger, float, double hoặc BigDecimal. Mỗi kiểu có miền giá trị và độ chính xác khác nhau.

Những lỗi số thường không xuất hiện với dữ liệu mẫu nhỏ:

- Một số nguyên hợp lệ với int nhưng vượt giới hạn long.
- Một giá trị decimal bị làm tròn khi đi qua double.
- Một số JSON có phần thập phân bị ép thành int ngoài ý muốn.
- Một số dạng chuỗi được coercion thành number dù hợp đồng chỉ cho phép token số.
- Một giá trị đúng về mặt số học nhưng vượt giới hạn nghiệp vụ.
- Số lớn bị mất độ chính xác ở consumer JavaScript hoặc hệ thống khác.
- BigDecimal có cùng giá trị số nhưng khác scale, khiến equals() trả false.

Kiểm thử số phải bao gồm cả cú pháp JSON, kiểu Java, miền giá trị, độ chính xác và quy tắc nghiệp vụ. Không chỉ kiểm tra một ví dụ “bình thường”.

## 2. Các kiểu số Java và miền giá trị

Các kiểu số nguyên primitive và wrapper có miền cố định:

| Kiểu | Giá trị nhỏ nhất | Giá trị lớn nhất |
|---|---:|---:|
| byte / Byte | -128 | 127 |
| short / Short | -32,768 | 32,767 |
| int / Integer | -2,147,483,648 | 2,147,483,647 |
| long / Long | -9,223,372,036,854,775,808 | 9,223,372,036,854,775,807 |

BigInteger không có giới hạn miền số học cố định như long; giới hạn thực tế đến từ bộ nhớ, thời gian xử lý và giới hạn parser.

Với số thập phân:

- float dùng biểu diễn dấu phẩy động nhị phân 32-bit.
- double dùng biểu diễn dấu phẩy động nhị phân 64-bit.
- BigDecimal biểu diễn số thập phân với precision và scale, phù hợp khi cần phép tính decimal chính xác theo hợp đồng.

Không nên chọn kiểu chỉ dựa vào kích thước JSON text. Một số nguyên có 30 chữ số vẫn là một token JSON hợp lệ về cú pháp, nhưng không thể chứa trong long. Jackson có thể đọc nó vào BigInteger nếu kiểu đích và giới hạn parser cho phép.

## 3. Kiểm thử đúng tại biên của Integer

Với int, cần kiểm tra ít nhất:

1. Giá trị nhỏ hơn minimum một đơn vị.
2. Giá trị đúng bằng minimum.
3. Giá trị bên trong miền.
4. Giá trị đúng bằng maximum.
5. Giá trị lớn hơn maximum một đơn vị.

Ví dụ:

~~~java
ObjectMapper mapper = new ObjectMapper();

assertEquals(
        Integer.MIN_VALUE,
        mapper.readValue("-2147483648", Integer.class)
);

assertEquals(
        Integer.MAX_VALUE,
        mapper.readValue("2147483647", Integer.class)
);

assertThrows(
        JsonProcessingException.class,
        () -> mapper.readValue("-2147483649", Integer.class)
);

assertThrows(
        JsonProcessingException.class,
        () -> mapper.readValue("2147483648", Integer.class)
);
~~~

Ví dụ kiểm tra trên kiểu wrapper Integer. Khi giá trị JSON vượt miền int, Jackson không nên âm thầm cuộn vòng về một số khác. Quá trình chuyển đổi số ngoài miền phải thất bại.

Không nên dùng cast hoặc intValue() để kiểm tra dữ liệu không đáng tin cậy trước khi xác nhận miền. Các phép chuyển đổi kiểu số Java có thể làm mất phần cao hoặc phần thập phân mà không ném lỗi.

## 4. Kiểm thử biên của Long và số nguyên rất lớn

Long có miền rộng hơn int nhưng vẫn hữu hạn:

~~~java
assertEquals(
        Long.MIN_VALUE,
        mapper.readValue("-9223372036854775808", Long.class)
);

assertEquals(
        Long.MAX_VALUE,
        mapper.readValue("9223372036854775807", Long.class)
);

assertThrows(
        JsonProcessingException.class,
        () -> mapper.readValue("9223372036854775808", Long.class)
);
~~~

Nếu hợp đồng cho phép số nguyên lớn hơn long, dùng BigInteger:

~~~java
BigInteger value = mapper.readValue(
        "1234567890123456789012345678901234567890",
        BigInteger.class
);

assertEquals(
        new BigInteger("1234567890123456789012345678901234567890"),
        value
);
~~~

Khi cần chuyển BigInteger về kiểu primitive, dùng phương thức exact để phát hiện overflow:

~~~java
BigInteger value = new BigInteger("2147483648");

assertThrows(
        ArithmeticException.class,
        value::intValueExact
);
~~~

intValue() có thể cắt bớt phần cao của số nguyên. intValueExact() ném ArithmeticException nếu không thể biểu diễn chính xác trong int.

## 5. Kiểm thử BigDecimal thay vì dùng double cho decimal chính xác

Các số thập phân như 0.1 không có biểu diễn nhị phân hữu hạn chính xác trong float hoặc double. Vì vậy:

~~~java
double amount = 0.1 + 0.2;
System.out.println(amount); // thường hiển thị 0.30000000000000004
~~~

Với dữ liệu tiền tệ, thuế, tỷ lệ hoặc phép tính cần quy tắc decimal rõ ràng, nên dùng BigDecimal:

~~~java
BigDecimal amount = new BigDecimal("0.10");
BigDecimal tax = new BigDecimal("0.20");

BigDecimal total = amount.add(tax);
assertEquals(new BigDecimal("0.30"), total);
~~~

Tạo BigDecimal từ String giữ đúng giá trị decimal được mô tả. Không nên dùng:

~~~java
new BigDecimal(0.1)
~~~

Constructor nhận double sẽ chuyển giá trị nhị phân gần đúng đang có trong double thành BigDecimal, nên kết quả có thể chứa nhiều chữ số bất ngờ.

BigDecimal.valueOf(0.1) dùng biểu diễn thập phân chuẩn hóa từ Double.toString và thường cho kết quả dễ dự đoán hơn constructor double. Tuy nhiên, nếu nguồn gốc là JSON, cách tốt nhất để giữ decimal gốc là để Jackson parse trực tiếp vào BigDecimal thay vì đi qua double.

## 6. Đọc JSON number trực tiếp vào BigDecimal

Khai báo DTO:

~~~java
public class Invoice {
    private BigDecimal amount;
    private BigDecimal taxRate;

    public BigDecimal getAmount() {
        return amount;
    }

    public void setAmount(BigDecimal amount) {
        this.amount = amount;
    }

    public BigDecimal getTaxRate() {
        return taxRate;
    }

    public void setTaxRate(BigDecimal taxRate) {
        this.taxRate = taxRate;
    }
}
~~~

JSON:

~~~json
{
  "amount": 12345678901234567890.123400,
  "taxRate": 0.075
}
~~~

Deserialize:

~~~java
Invoice invoice = mapper.readValue(json, Invoice.class);

assertEquals(
        new BigDecimal("12345678901234567890.123400"),
        invoice.getAmount()
);

assertEquals(new BigDecimal("0.075"), invoice.getTaxRate());
~~~

Khi property đích là BigDecimal, Jackson có thể lấy giá trị decimal từ parser mà không phải chuyển qua double. Điều này giữ được độ chính xác và scale của token decimal theo cách parser biểu diễn.

Đừng khai báo field là double rồi chuyển sang BigDecimal sau đó nếu hợp đồng yêu cầu decimal chính xác. Phần sai số có thể đã xuất hiện trước khi tạo BigDecimal.

## 7. Phân biệt precision và scale của BigDecimal

BigDecimal có hai thuộc tính quan trọng:

- **Precision:** tổng số chữ số có nghĩa.
- **Scale:** số chữ số nằm bên phải dấu thập phân.

Ví dụ:

~~~java
BigDecimal value = new BigDecimal("123.4500");

assertEquals(7, value.precision());
assertEquals(4, value.scale());
~~~

Hai giá trị sau bằng nhau về giá trị số học:

~~~java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

assertEquals(0, a.compareTo(b));
assertNotEquals(a, b);
~~~

compareTo() so sánh giá trị số học và bỏ qua khác biệt scale. equals() yêu cầu cả giá trị và scale giống nhau.

Khi kiểm thử decimal, hãy quyết định điều cần xác nhận:

- Nếu scale là một phần hợp đồng, dùng equals/assertEquals với BigDecimal có scale mong đợi.
- Nếu chỉ quan tâm giá trị số học, dùng compareTo() hoặc assertion so sánh theo comparator.
- Nếu API yêu cầu đúng hai chữ số thập phân, kiểm tra scale hoặc validate scale riêng.

Không nên dùng assertEquals(new BigDecimal("1.0"), new BigDecimal("1.00")) rồi kết luận Jackson làm sai. Hai object có scale khác nhau theo đúng semantics của BigDecimal.

## 8. Kiểm thử số thập phân có exponent

JSON number có thể dùng exponent notation:

~~~json
{
  "small": 1.25e-7,
  "large": 6.02E23
}
~~~

BigDecimal hỗ trợ cả dạng decimal và exponent:

~~~java
BigDecimal small = mapper.readValue("1.25e-7", BigDecimal.class);
BigDecimal large = mapper.readValue("6.02E23", BigDecimal.class);

assertEquals(new BigDecimal("1.25e-7"), small);
assertEquals(new BigDecimal("6.02E23"), large);
~~~

Khi so sánh giá trị số học, có thể dùng compareTo() vì biểu diễn có thể khác scale hoặc exponent. Khi cần giữ định dạng hiển thị cụ thể, phải định nghĩa quy tắc serialization riêng; JSON number không bắt buộc consumer giữ nguyên cách viết ban đầu.

Một round-trip số học không đồng nghĩa byte-for-byte round-trip. Ví dụ, 1000, 1e3 và 1000.0 có thể đại diện cùng giá trị số nhưng có cách viết khác nhau.

## 9. Phép chia và quy tắc làm tròn

BigDecimal cộng, trừ và nhân có thể giữ kết quả decimal chính xác trong giới hạn precision của phép toán. Phép chia có thể tạo decimal vô hạn tuần hoàn:

~~~java
BigDecimal one = new BigDecimal("1");
BigDecimal three = new BigDecimal("3");

one.divide(three); // ArithmeticException nếu không có quy tắc làm tròn
~~~

Phải chọn scale và RoundingMode theo hợp đồng nghiệp vụ:

~~~java
BigDecimal result = one.divide(
        three,
        2,
        RoundingMode.HALF_UP
);

assertEquals(new BigDecimal("0.33"), result);
~~~

Các chế độ thường gặp:

| RoundingMode | Ý nghĩa khái quát |
|---|---|
| UP | Làm tròn ra xa 0 |
| DOWN | Cắt về phía 0 |
| CEILING | Làm tròn về phía dương vô cùng |
| FLOOR | Làm tròn về phía âm vô cùng |
| HALF_UP | Gần nhất, trường hợp giữa thì ra xa 0 |
| HALF_DOWN | Gần nhất, trường hợp giữa thì về phía 0 |
| HALF_EVEN | Gần nhất, trường hợp giữa về chữ số chẵn gần nhất |
| UNNECESSARY | Ném lỗi nếu cần làm tròn |

Đừng chọn HALF_UP hoặc HALF_EVEN chỉ vì thói quen. Quy tắc phải phù hợp với hợp đồng, chuẩn kế toán và luật áp dụng cho nghiệp vụ.

## 10. Kiểm tra scale và precision theo nghiệp vụ

BigDecimal có thể chứa giá trị chính xác nhưng vẫn vượt giới hạn nghiệp vụ. Ví dụ một tỷ lệ thuế chỉ được phép có tối đa 4 chữ số thập phân hoặc số tiền chỉ có precision nhất định.

Ví dụ validator:

~~~java
static void validateAmount(BigDecimal amount) {
    if (amount == null) {
        throw new IllegalArgumentException("amount is required");
    }

    if (amount.signum() < 0) {
        throw new IllegalArgumentException("amount must not be negative");
    }

    if (amount.precision() > 18) {
        throw new IllegalArgumentException("amount precision is too large");
    }

    if (amount.scale() > 2) {
        throw new IllegalArgumentException(
                "amount supports at most two fractional digits"
        );
    }
}
~~~

Đây chỉ là ví dụ chính sách cho một loại amount cụ thể. Không áp dụng scale = 2 cho mọi currency; có loại tiền không dùng chữ số thập phân, có loại dùng ba chữ số. Scale phải dựa trên currency và hợp đồng domain.

Nếu muốn chấp nhận nhiều chữ số rồi làm tròn, phải định nghĩa chế độ làm tròn rõ ràng. Nếu muốn từ chối dữ liệu có phần lẻ vượt scale, có thể dùng setScale với RoundingMode.UNNECESSARY:

~~~java
BigDecimal normalized = amount.setScale(
        2,
        RoundingMode.UNNECESSARY
);
~~~

Nếu cần làm tròn theo chính sách:

~~~java
BigDecimal rounded = amount.setScale(
        2,
        RoundingMode.HALF_EVEN
);
~~~

Hãy kiểm thử cả hai trường hợp: giá trị có thể chuẩn hóa chính xác và giá trị buộc phải làm tròn.

## 11. Kiểm thử ACCEPT_FLOAT_AS_INT

Jackson có feature ACCEPT_FLOAT_AS_INT. Trong cấu hình thông thường, feature này được bật mặc định và có thể cho phép giá trị JSON floating-point được chuyển sang kiểu số nguyên bằng cách loại bỏ phần thập phân.

Ví dụ:

~~~java
ObjectMapper defaultMapper = new ObjectMapper();
Integer value = defaultMapper.readValue("12.9", Integer.class);
~~~

Nếu hợp đồng yêu cầu chỉ nhận JSON integer token, hãy tắt coercion này:

~~~java
ObjectMapper strictMapper = JsonMapper.builder()
        .disable(DeserializationFeature.ACCEPT_FLOAT_AS_INT)
        .build();

assertThrows(
        JsonProcessingException.class,
        () -> strictMapper.readValue("12.9", Integer.class)
);
~~~

Kiểm thử thêm:

- 12 phải được chấp nhận.
- 12.0 phải bị từ chối nếu hợp đồng yêu cầu integer token.
- 12.9 phải bị từ chối.
- Chuỗi "12" phải được xử lý theo chính sách string coercion.
- null phải được xử lý theo null policy riêng.

Không nên dựa vào việc một số decimal có phần lẻ bằng 0 để xem nó là integer token. JSON 12 và 12.0 có cùng giá trị số học nhưng khác loại token.

## 12. Kiểm soát coercion từ String sang number

Jackson có thể chuyển một số chuỗi số thành kiểu số tùy mapper feature, coercion configuration và kiểu đích. Nếu hợp đồng yêu cầu JSON number, không nên mặc định chấp nhận:

~~~json
{"quantity": "12"}
~~~

thay cho:

~~~json
{"quantity": 12}
~~~

Từ Jackson Databind 2.12, có thể cấu hình coercion theo logical type:

~~~java
ObjectMapper mapper = JsonMapper.builder().build();

mapper.coercionConfigFor(LogicalType.Integer)
        .setCoercion(
                CoercionInputShape.String,
                CoercionAction.Fail
        );

mapper.coercionConfigFor(LogicalType.Float)
        .setCoercion(
                CoercionInputShape.String,
                CoercionAction.Fail
        );
~~~

Với cấu hình trên, string input được từ chối cho logical integer/float theo coercion policy. Cần kiểm tra các kiểu property thực tế và phiên bản Jackson của dự án vì coercion có thể được override ở cấp property hoặc custom deserializer.

Nếu API chủ động cho phép chuỗi số, hãy định nghĩa format, locale, dấu thập phân và quy tắc khoảng trắng. Không dùng một chính sách coercion ngầm cho mọi endpoint.

## 13. Untyped number trong Object và Map

Khi đọc JSON vào kiểu cụ thể:

~~~java
BigDecimal amount = mapper.readValue("123.45", BigDecimal.class);
~~~

kiểu đích đã yêu cầu BigDecimal. Nhưng khi đọc vào Object hoặc Map<String, Object>, Jackson phải chọn kiểu Java cho number mà không có thông tin kiểu đích.

Theo cấu hình mặc định, số nguyên untyped thường được chọn giữa Integer, Long và BigInteger tùy kích thước; floating-point thường được ánh xạ thành Double.

Có thể yêu cầu dùng BigInteger cho số nguyên untyped:

~~~java
ObjectMapper mapper = JsonMapper.builder()
        .enable(DeserializationFeature.USE_BIG_INTEGER_FOR_INTS)
        .enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS)
        .build();

Map<String, Object> values = mapper.readValue(
        """
        {
          "largeInteger": 123456789012345678901234567890,
          "decimal": 0.1234567890123456789012345
        }
        """,
        new TypeReference<Map<String, Object>>() {}
);

assertInstanceOf(BigInteger.class, values.get("largeInteger"));
assertInstanceOf(BigDecimal.class, values.get("decimal"));
~~~

USE_BIG_INTEGER_FOR_INTS và USE_BIG_DECIMAL_FOR_FLOATS đặc biệt quan trọng với dữ liệu untyped. Chúng không thay thế việc khai báo kiểu đích rõ ràng trong DTO.

Nếu schema đã biết, ưu tiên field BigInteger/BigDecimal cụ thể thay vì Map<String, Object> vì kiểu rõ ràng giúp validation và kiểm thử dễ hơn.

## 14. Kiểm tra kiểu token bằng JsonParser

Khi cần strict policy ở cấp token, có thể kiểm tra JsonToken trước khi lấy giá trị:

~~~java
JsonToken token = parser.currentToken();

if (token == JsonToken.VALUE_NUMBER_INT) {
    BigInteger value = parser.getBigIntegerValue();
} else if (token == JsonToken.VALUE_NUMBER_FLOAT) {
    BigDecimal value = parser.getDecimalValue();
} else {
    throw JsonMappingException.from(
            parser,
            "Expected a JSON number token"
    );
}
~~~

Cách này phân biệt:

- Integer token như 12.
- Floating-point token như 12.0 hoặc 1.2e1.
- String token như "12".

Nếu field yêu cầu integer, chỉ chấp nhận VALUE_NUMBER_INT. Nếu field yêu cầu decimal, có thể chấp nhận cả integer và floating-point token nhưng đọc cả hai vào BigDecimal.

Không dùng getValueAsInt() như một validator strict. Các phương thức tiện ích chuyển đổi có thể trả giá trị fallback hoặc coercion; hãy kiểm tra token và miền giá trị trước.

## 15. Kiểm thử JsonNode với số lớn

JsonNode cung cấp các phương thức kiểm tra kiểu số:

- isIntegralNumber(): node là số nguyên.
- isFloatingPointNumber(): node là số dấu phẩy động.
- bigIntegerValue(): lấy giá trị BigInteger của node số.
- decimalValue(): lấy giá trị BigDecimal của node số.
- canConvertToInt() và canConvertToLong(): kiểm tra khả năng chuyển vào miền int/long theo quy tắc của node.

Ví dụ:

~~~java
JsonNode node = mapper.readTree(
        """
        {
          "count": 2147483648,
          "ratio": 0.1234567890123456789
        }
        """
);

JsonNode countNode = node.path("count");
assertTrue(countNode.isIntegralNumber());
assertFalse(countNode.canConvertToInt());
assertTrue(countNode.canConvertToLong());

JsonNode ratioNode = node.path("ratio");
assertTrue(ratioNode.isNumber());
~~~

Với floating-point node, không nên chỉ dựa vào canConvertToInt() để quyết định có được phép chuyển sang int theo nghiệp vụ hay không. Hãy kiểm tra token kind, phần lẻ, range và rounding policy rõ ràng.

Nếu cần giữ decimal chính xác trong Tree Model, cấu hình USE_BIG_DECIMAL_FOR_FLOATS khi đọc untyped numeric node và kiểm thử chính xác với phiên bản Jackson đang dùng. Với DTO có kiểu BigDecimal, đọc trực tiếp vào BigDecimal thường rõ ràng hơn.

## 16. Kiểm tra overflow trong custom deserializer

Một custom deserializer có thể đọc BigInteger trước, sau đó xác nhận miền int:

~~~java
public class StrictIntDeserializer extends StdDeserializer<Integer> {
    public StrictIntDeserializer() {
        super(Integer.class);
    }

    @Override
    public Integer deserialize(
            JsonParser parser,
            DeserializationContext context
    ) throws IOException {
        if (parser.currentToken() != JsonToken.VALUE_NUMBER_INT) {
            throw JsonMappingException.from(
                    parser,
                    "Expected an integer JSON token"
            );
        }

        BigInteger value = parser.getBigIntegerValue();
        if (value.compareTo(BigInteger.valueOf(Integer.MIN_VALUE)) < 0
                || value.compareTo(BigInteger.valueOf(Integer.MAX_VALUE)) > 0) {
            throw JsonMappingException.from(
                    parser,
                    "Integer value is outside the 32-bit range"
            );
        }

        return value.intValue();
    }
}
~~~

Đọc BigInteger trước giúp logic range rõ ràng và tránh chuyển đổi có mất mát. Với field có kiểu int, Jackson đã có kiểm tra miền; custom deserializer hữu ích khi hợp đồng còn cần strict token type hoặc thông báo lỗi riêng.

Đừng bắt ArithmeticException rồi trả về 0. Giá trị fallback như 0 có thể là dữ liệu hợp lệ và che giấu overflow.

## 17. Kiểm tra giới hạn số chữ số trong parser

BigInteger và BigDecimal có độ chính xác tùy kích thước input nhưng không phải không giới hạn về tài nguyên. Một token number chứa hàng triệu chữ số có thể tiêu thụ CPU và memory lớn.

Jackson Core cung cấp StreamReadConstraints trong các phiên bản hỗ trợ:

~~~java
JsonFactory factory = JsonFactory.builder()
        .streamReadConstraints(
                StreamReadConstraints.builder()
                        .maxNumberLength(1_000)
                        .build()
        )
        .build();

ObjectMapper mapper = new ObjectMapper(factory);
~~~

Giới hạn 1.000 ký tự chỉ là ví dụ. Chọn theo precision tối đa mà schema cho phép. Nếu nghiệp vụ cần số lớn hơn, tăng giới hạn có kiểm soát thay vì tắt giới hạn.

Kiểm thử:

- Token có độ dài nhỏ hơn giới hạn.
- Token đúng bằng giới hạn.
- Token vượt giới hạn.
- Token exponent rất dài.
- Token có nhiều chữ số leading hoặc trailing theo cú pháp JSON.

Parser constraints là lớp bảo vệ tài nguyên; validation domain vẫn cần kiểm tra precision, scale và range.

## 18. Kiểm thử số âm, số 0 và dấu

Các trường hợp biên không chỉ là MIN_VALUE và MAX_VALUE:

- Số âm nhỏ nhất được phép theo nghiệp vụ.
- Số âm một đơn vị ngoài giới hạn.
- Số 0.
- -0 trong JSON number.
- Decimal âm rất nhỏ.
- Decimal bằng 0 nhưng có scale như 0.00.
- Số có exponent âm.

JSON number grammar cho phép dấu trừ ở đầu số, nhưng không có token riêng cho số âm. Khi parse thành số học, -0 có thể được chuẩn hóa tùy kiểu đích; đừng dựa vào dấu âm của zero để biểu diễn một trạng thái nghiệp vụ riêng.

Nếu cần phân biệt “chưa nhập” với số 0, dùng null/missing hoặc một trạng thái presence riêng. Không dùng -0 hoặc một số sentinel nếu sentinel đó có thể xuất hiện hợp lệ.

## 19. Số nguyên an toàn khi trao đổi với JavaScript

Java long có thể chứa số nguyên lớn hơn phạm vi integer chính xác của JavaScript Number. JavaScript Number dùng IEEE-754 double, có thể biểu diễn chính xác mọi số nguyên trong khoảng:

~~~text
-(2^53 - 1) đến +(2^53 - 1)
~~~

Tức là ±9,007,199,254,740,991.

Nếu API phát một long lớn hơn safe integer range, client JavaScript có thể làm tròn khi parse JSON bằng JSON.parse. Jackson phía Java có thể giữ đúng giá trị nhưng điều đó không bảo đảm client giữ được.

Các lựa chọn:

- Biểu diễn ID lớn dưới dạng JSON string.
- Dùng BigInt-aware protocol hoặc thư viện parser có hỗ trợ số nguyên lớn.
- Dùng chuỗi decimal cho giá trị cần giữ nguyên chính xác ở client.
- Dùng số nguyên minor unit chỉ khi miền giá trị vẫn nằm trong safe range và quy tắc currency được định nghĩa.

Không đổi mọi number thành string một cách tùy tiện; thay đổi kiểu là thay đổi hợp đồng. Chọn representation theo consumer và kiểm thử qua đúng runtime client.

## 20. Tiền tệ: precision, scale và currency

Tiền tệ cần quy tắc rõ về:

- Currency code.
- Precision tối đa.
- Scale theo currency hoặc nghiệp vụ.
- Rounding mode.
- Phạm vi giá trị âm/dương.
- Có cho phép giá trị fractional nhỏ hơn đơn vị tiền hay không.

Một mô hình:

~~~java
public record Money(
        String currency,
        BigDecimal amount
) {
}
~~~

JSON:

~~~json
{
  "currency": "USD",
  "amount": 1234.50
}
~~~

Không nên dùng double cho amount chỉ vì JSON number có thể đọc thành double. BigDecimal giữ phép tính decimal chính xác hơn.

Đừng mặc định mọi currency có scale 2. Currency và quy tắc nghiệp vụ quyết định scale. Nếu lưu minor units dạng integer, phải biết currency exponent và miền giá trị; một số currency không có hai chữ số lẻ, một số có ba.

## 21. Kiểm thử serialize và deserialize round-trip

Round-trip kiểm tra:

~~~text
Java numeric value
       |
       v
Jackson serialize
       |
       v
JSON number
       |
       v
Jackson deserialize
       |
       v
Java numeric value mới
~~~

Với BigInteger:

~~~java
BigInteger original =
        new BigInteger("987654321098765432109876543210");

String json = mapper.writeValueAsString(original);
BigInteger restored = mapper.readValue(json, BigInteger.class);

assertEquals(original, restored);
~~~

Với BigDecimal:

~~~java
BigDecimal original = new BigDecimal("1234567890.12000");

String json = mapper.writeValueAsString(original);
BigDecimal restored = mapper.readValue(json, BigDecimal.class);

assertEquals(original, restored);
~~~

Nếu hợp đồng chỉ quan tâm giá trị số học, dùng compareTo() để kiểm tra. Nếu scale là một phần dữ liệu, assertEquals() sẽ kiểm tra cả scale.

Round-trip cùng Jackson không chứng minh consumer khác ngôn ngữ giữ nguyên số. Cần test integration với client thực tế, đặc biệt khi có JavaScript, spreadsheet hoặc database numeric type.

## 22. Ma trận kiểm thử giá trị biên

Một bộ test có thể tổ chức như sau:

| Nhóm | Giá trị cần thử | Kết quả mong đợi |
|---|---|---|
| Integer | MIN_VALUE - 1 | Từ chối overflow |
| Integer | MIN_VALUE | Chấp nhận |
| Integer | 0 | Chấp nhận |
| Integer | MAX_VALUE | Chấp nhận |
| Integer | MAX_VALUE + 1 | Từ chối overflow |
| Long | MIN_VALUE và MAX_VALUE | Chấp nhận |
| Long | Ngoài miền long | Từ chối hoặc dùng BigInteger |
| BigInteger | Số nhiều chữ số | Giữ chính xác |
| BigDecimal | Nhiều chữ số thập phân | Giữ precision/scale theo hợp đồng |
| BigDecimal | 1.0 và 1.00 | Kiểm tra compareTo và equals đúng mục tiêu |
| Decimal | 1e-10 và 1e20 | Đọc đúng exponent |
| Integer target | JSON 12.9 | Từ chối nếu strict integer |
| Integer target | JSON "12" | Theo string coercion policy |
| Untyped number | Số lớn và decimal dài | Kiểm tra USE_BIG_INTEGER/USE_BIG_DECIMAL |
| Parser | Token vượt maxNumberLength | Từ chối theo constraint |
| Domain | Số âm, scale vượt giới hạn | Validation nghiệp vụ từ chối |
| Cross-language | Integer vượt 2^53-1 | Consumer JavaScript không được mất chính xác |

## 23. JUnit parameterized test cho biên Integer

Có thể dùng parameterized test để tránh lặp code:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.*;

class IntegerBoundaryTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @ParameterizedTest
    @CsvSource({
            "-2147483648, true",
            "-1, true",
            "0, true",
            "1, true",
            "2147483647, true",
            "-2147483649, false",
            "2147483648, false"
    })
    void checksIntegerRange(String json, boolean valid) {
        if (valid) {
            assertDoesNotThrow(
                    () -> mapper.readValue(json, Integer.class)
            );
        } else {
            assertThrows(
                    JsonProcessingException.class,
                    () -> mapper.readValue(json, Integer.class)
            );
        }
    }
}
~~~

Trong dự án, có thể bổ sung test cho byte, short, long và kiểu domain riêng. Nên giữ các giá trị biên dưới dạng literal string để tránh chính test vô tình làm tròn số trước khi gửi vào Jackson.

## 24. Property-based testing cho số lớn và decimal

Ngoài các giá trị biên cố định, property-based testing có thể sinh nhiều số ngẫu nhiên:

- BigInteger có độ dài khác nhau.
- BigDecimal với precision và scale khác nhau.
- Giá trị âm, dương và zero.
- Exponent dương/âm.
- Giá trị sát MIN/MAX.

Một property quan trọng:

~~~text
deserialize(serialize(value)) == value
~~~

Với BigDecimal, cần xác định equality là equals hay compareTo tùy scale có thuộc hợp đồng không.

Có thể dùng jqwik hoặc QuickTheories nếu dự án đã có dependency. Không cần thêm framework chỉ để kiểm tra vài biên cố định; JUnit parameterized test có thể đủ cho nhiều dự án.

Đối với dữ liệu không đáng tin cậy, thêm fuzz test cho token number dài, exponent cực lớn và chuỗi không phải JSON number. Kết quả cần là thành công đúng giá trị hoặc lỗi được kiểm soát, không phải treo hoặc tiêu thụ tài nguyên không giới hạn.

## 25. Kiểm thử custom deserializer và lỗi chuyển đổi

Nếu có custom deserializer, hãy test riêng:

- Integer token đúng miền.
- Integer token vượt miền.
- Floating-point token.
- String token.
- Boolean, object và array token.
- Null token qua getNullValue().
- Số dài vượt parser constraint.

Không chỉ kiểm tra exception được ném. Hãy xác nhận:

- Loại lỗi phù hợp (mapping, coercion, validation hoặc constraint).
- Đường dẫn property nếu lỗi nằm trong object.
- Không có giá trị fallback âm thầm.
- Không có side effect trước khi validation hoàn tất.
- Error message không làm lộ dữ liệu nhạy cảm.

Với số lớn, parser có thể ném StreamConstraintsException khi token vượt maxNumberLength. Đây là lỗi giới hạn tài nguyên, khác với lỗi overflow của Integer hoặc Long.

## 26. Quy trình kiểm thử số trong một API

Khi thiết kế test cho field numeric:

1. Chọn kiểu Java theo miền giá trị và độ chính xác cần thiết.
2. Ghi rõ JSON token nào được phép: integer, decimal, string hay nhiều dạng.
3. Xác định range, precision và scale của domain.
4. Cấu hình Jackson coercion để từ chối hoặc cho phép chuyển đổi có chủ đích.
5. Kiểm tra null/missing riêng với numeric zero.
6. Test MIN/MAX và giá trị ngoài biên một đơn vị.
7. Test decimal có nhiều chữ số, trailing zero và exponent.
8. Test serialize/deserialize round-trip.
9. Test giới hạn parser với token quá dài.
10. Test consumer khác ngôn ngữ nếu payload đi qua nhiều nền tảng.
11. Xác nhận lỗi không biến thành zero, null hoặc giá trị mặc định một cách âm thầm.

## 27. Những lỗi thường gặp

### Dùng double cho tiền

Double là floating-point nhị phân, không thể biểu diễn chính xác mọi decimal. Dùng BigDecimal khi cần decimal chính xác.

### Tạo BigDecimal từ double

new BigDecimal(0.1) giữ xấp xỉ nhị phân của double. Dùng String hoặc parse trực tiếp từ JSON vào BigDecimal.

### Chỉ test số nhỏ

Các lỗi overflow chỉ xuất hiện gần biên. Test cả giá trị tại biên và ngay ngoài biên.

### Dùng intValue() hoặc longValue() để ép kiểu

Các phương thức này có thể cắt phần cao. Dùng intValueExact()/longValueExact() hoặc so sánh range trước.

### Không phân biệt 12 và 12.0

Chúng là hai dạng token khác nhau. Nếu field yêu cầu integer token, tắt ACCEPT_FLOAT_AS_INT và test.

### Để String coercion xảy ra ngoài ý muốn

Một chuỗi "123" có thể được chuyển thành số theo cấu hình. Đặt coercion policy rõ ràng.

### Dùng Double cho untyped Map

Số decimal dài có thể mất độ chính xác. Cân nhắc USE_BIG_DECIMAL_FOR_FLOATS và USE_BIG_INTEGER_FOR_INTS.

### So sánh BigDecimal bằng equals khi không quan tâm scale

1.0 và 1.00 không equals. Dùng compareTo nếu chỉ so giá trị số học.

### Quên giới hạn token số

BigInteger/BigDecimal không giới hạn miền cố định nhưng parser vẫn cần giới hạn chiều dài để bảo vệ tài nguyên.

### Chỉ test Java-to-Java

Consumer JavaScript có thể mất chính xác với integer vượt safe range. Test qua đúng client thực tế.

## 28. Kết luận

Kiểm thử số trong Jackson phải bao phủ miền giá trị, kiểu token, precision, scale, coercion và giới hạn parser. Dùng Integer/Long khi miền giá trị đã biết, BigInteger cho số nguyên lớn và BigDecimal cho decimal cần độ chính xác. Kiểm tra MIN/MAX cùng giá trị ngay ngoài biên; không ép kiểu bằng intValue/longValue khi chưa xác nhận range. Với BigDecimal, phân biệt equals() và compareTo(), quy định scale và RoundingMode theo nghiệp vụ. Tắt ACCEPT_FLOAT_AS_INT hoặc cấu hình coercion khi cần strict numeric token; dùng USE_BIG_INTEGER_FOR_INTS và USE_BIG_DECIMAL_FOR_FLOATS cho dữ liệu untyped khi cần giữ độ chính xác. Cuối cùng, đặt maxNumberLength, test round-trip và kiểm tra consumer đa ngôn ngữ để bảo đảm số không bị tràn, làm tròn hoặc thay đổi âm thầm.
