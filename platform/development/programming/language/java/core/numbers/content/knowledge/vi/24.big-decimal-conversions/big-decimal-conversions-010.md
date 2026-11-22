# Thiết kế dạng trao đổi giữ số chính xác, không qua `double` trung gian

## 1. Bài toán và tiêu chí thành công

Khi chuyển một giá trị `BigDecimal` qua JSON, HTTP, hàng đợi, tập tin hoặc giữa Java và JavaScript, lỗi phổ biến là đưa số qua `double`/`Double` ở một mắt xích bất kỳ. `double` là số dấu phẩy động nhị phân hữu hạn (IEEE 754 binary64), nên không thể biểu diễn chính xác mọi số thập phân, kể cả `0.1`, và không thể giữ riêng rẽ mọi số nguyên lớn.

Ví dụ trong Java:

~~~java
BigDecimal exact = new BigDecimal("9007199254740993.01");
BigDecimal altered = BigDecimal.valueOf(exact.doubleValue());

System.out.println(exact.toPlainString());   // 9007199254740993.01
System.out.println(altered.toPlainString()); // 9007199254740994
~~~

Việc chuyển sang `double` đã làm mất dữ liệu; chuyển ngược bằng `BigDecimal.valueOf(...)` **không thể khôi phục** những chữ số vốn đã bị làm tròn.

Một dạng trao đổi tốt cần định nghĩa rõ:

1. **Giữ nguyên giá trị số học**: phía nhận đọc được đúng số thập phân phía gửi định truyền.
2. **Có cần giữ nguyên `scale` không?** `1.0` và `1.00` có cùng giá trị theo `compareTo`, nhưng không bằng nhau theo `BigDecimal.equals`.
3. **Giữ nguyên mọi chữ số trên đường truyền**, không chuyển ngầm qua `double`, `float`, `Number` của JavaScript hoặc ép kiểu tương tự.
4. **Hợp đồng có thể kiểm thử**: thống nhất kiểu dữ liệu, cú pháp, giới hạn, quy tắc làm tròn và cách báo lỗi.
5. **Bảo vệ tài nguyên**: kiểm soát độ dài, `precision`, `scale` và số mũ trước các phép chuyển đổi tốn bộ nhớ.

Bài học này tập trung vào thiết kế và thực hiện trao đổi `BigDecimal` giữa các thành phần. Khi cần phép tính có làm tròn, chính sách làm tròn phải được xác định riêng, không lén thực hiện trong bước mã hóa hoặc giải mã.

## 2. Vì sao `double` là bước trung gian không an toàn?

`BigDecimal` biểu diễn một số bằng `unscaledValue × 10^(-scale)`. Với chuỗi thập phân, `new BigDecimal(String)` đọc các chữ số chính xác theo biểu diễn thập phân.

Ngược lại, `double` lưu một lượng hữu hạn bit cho số có nghĩa và số mũ nhị phân. Có hai nhóm lỗi chính:

- **Phân số thập phân**: nhiều số như `0.1` không biểu diễn chính xác bằng nhị phân hữu hạn. `new BigDecimal(0.1)` cho giá trị chính xác của *số double đang lưu*, có thể dài hơn nhiều so với chuỗi `"0.1"`.
- **Số nguyên vượt miền an toàn của JavaScript**: `Number` là binary64, nên mọi số nguyên trong khoảng `[-(2^53-1), 2^53-1]` mới được bảo đảm biểu diễn chính xác từng đơn vị. `9007199254740993` không thuộc miền đó.

Minh họa:

~~~java
BigDecimal text = new BigDecimal("0.1");
BigDecimal viaDoubleConstructor = new BigDecimal(0.1);

System.out.println(text.equals(viaDoubleConstructor)); // false

BigDecimal huge = new BigDecimal("9007199254740993");
System.out.println(
        BigDecimal.valueOf(huge.doubleValue()).toPlainString()
); // 9007199254740992
~~~

Đừng hiểu nhầm rằng `BigDecimal.valueOf(double)` vô dụng: nó thường thích hợp hơn `new BigDecimal(double)` khi **đầu vào đã thực sự là một `double`** và bạn cần biểu diễn thập phân theo `Double.toString`. Tuy nhiên, không cách nào trong hai cách đó lấy lại chữ số từng tồn tại trước khi dữ liệu bị chuyển sang `double`.

**Quy tắc kiến trúc:** nếu nguồn là chuỗi thập phân, dữ liệu `DECIMAL/NUMERIC` hoặc `BigDecimal`, giữ nó dưới dạng **chuỗi thập phân chính xác hoặc kiểu decimal chính xác** cho đến khi đến đích.

## 3. Đầu tiên phải phân biệt hai mức “giữ nguyên”

### A. Giữ giá trị số học

Hai biểu diễn có giá trị bằng nhau nếu:

~~~java
BigDecimal a = new BigDecimal("1000");
BigDecimal b = new BigDecimal("1E+3");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
~~~

Mức bảo toàn này phù hợp khi chỉ quan tâm kết quả tính toán, chẳng hạn tổng đo lường được chuẩn hóa và quy tắc nghiệp vụ không dùng `scale`.

### B. Giữ cả giá trị lẫn `scale`

`BigDecimal.equals` xét cả giá trị và `scale`. Ví dụ:

| Giá trị nhập | `unscaledValue()` | `scale()` |
| --- | ---: | ---: |
| `"1.0"` | `10` | `1` |
| `"1.00"` | `100` | `2` |
| `"1000"` | `1000` | `0` |
| `"1E+3"` | `1` | `-3` |

Nếu `scale` là phần của hợp đồng (ví dụ để giữ số chữ số thập phân đã khai báo), cần round-trip mà `BigDecimal.equals` cũng trả `true`.

Không nên quy kết số chữ số 0 cuối là “không quan trọng” trong mọi hệ thống. Đối với tính toán số học có thể không quan trọng, nhưng trong nhập liệu, xuất chứng từ hoặc trao đổi dựa trên biểu diễn, thông tin đó có thể cần được giữ lại.

## 4. Các phương án wire format và đánh đổi

### Phương án 1 — JSON string chứa decimal chính xác (khuyến nghị mặc định)

~~~json
{
  "currency": "USD",
  "amount": "9007199254740993.01"
}
~~~

Hợp đồng: `amount` là **JSON string**, không phải JSON number. Nội dung chuỗi biểu diễn số thập phân theo cú pháp đã thỏa thuận; phía Java giải mã trực tiếp bằng `new BigDecimal(amount)`.

Ưu điểm:

- JavaScript `JSON.parse` trả về **string**, không tự làm tròn qua `Number`.
- Java, Python, .NET hoặc các ngôn ngữ khác có thể parse bằng kiểu decimal có độ chính xác cần thiết.
- Dễ duy trì tính toàn vẹn của số nguyên rất lớn, nhiều chữ số thập phân và ký pháp số mũ.
- Có thể quy định rằng chuỗi là đầu ra của `BigDecimal.toString()` để giữ cả `scale`.

Cần thống nhất schema: tên trường, loại JSON **string**, định dạng dấu chấm thập phân, dấu âm, hỗ trợ số mũ, độ dài tối đa và ràng buộc miền giá trị. Đừng để client tùy tiện gọi `Number(amount)` hoặc `parseFloat(amount)` trước khi tính toán.

### Phương án 2 — JSON number với pipeline decimal chính xác từ đầu đến cuối

~~~json
{
  "amount": 9007199254740993.01
}
~~~

Cú pháp JSON **cho phép** literal số có nhiều chữ số, nhưng JSON không bảo đảm mọi parser giữ nguyên độ chính xác. Nếu một bên làm `JSON.parse` trong JavaScript thông thường, `amount` sẽ trở thành `Number`; số đã mất chính xác ngay tại bước parse.

Phương án này chỉ đáp ứng yêu cầu khi **mọi mắt xích** đều đọc token số trực tiếp thành decimal tùy ý và không có bước trung gian qua binary64. Ví dụ một parser Java được cấu hình bind trường sang `BigDecimal` có thể đọc token decimal chính xác, trong khi một parser khác bind sang `Double` có thể làm tròn.

Việc Java tự serialize `BigDecimal` thành JSON numeric token không đủ chứng minh rằng toàn tuyến an toàn. Hãy kiểm thử cả các consumer, message broker, proxy và bước chuyển đổi dữ liệu.

### Phương án 3 — đơn vị nhỏ nhất dưới dạng chuỗi số nguyên

Ví dụ, nếu hợp đồng quy định hai chữ số thập phân:

~~~json
{
  "currency": "USD",
  "minorUnits": "123456",
  "scale": 2
}
~~~

Giá trị được hiểu là `123456 × 10^(-2) = 1234.56`. `minorUnits` là **string số nguyên** để phía JavaScript không vô tình mất chính xác; phía Java có thể dùng `BigInteger`.

Phương án này hữu ích trong thanh toán hoặc hệ thống đòi hỏi số nguyên theo một đơn vị đã định trước. Nhưng `scale` không nên tự suy từ mã tiền tệ một cách tùy tiện; cần áp dụng đúng chính sách và phiên bản quy định nghiệp vụ. Nếu giá trị gốc có nhiều chữ số hơn `scale` cho phép, phải xác định **từ chối** hay **làm tròn với chế độ nào** trước khi mã hóa.

### Phương án 4 — truyền tách `unscaled` và `scale`

~~~json
{
  "unscaled": "100000",
  "scale": 2
}
~~~

Phía nhận dựng lại:

~~~java
BigDecimal number = new BigDecimal(
        new BigInteger("100000"), 2
); // 1000.00
~~~

Biểu diễn này giữ cả giá trị và `scale` mà không cần dựa trên quy tắc chuỗi chuẩn. `unscaled` phải được coi là string số nguyên lớn; `scale` là số nguyên có ràng buộc miền và độ lớn hợp lý (ở Java, `BigDecimal.scale()` trả `int`).

Ưu điểm là contract tường minh và dễ tái dựng. Nhược điểm là schema dài hơn và mọi bên phải triển khai đúng công thức `unscaled × 10^(-scale)`, đặc biệt với `scale` âm.

### Chọn phương án nào?

| Mục tiêu | Khuyến nghị |
| --- | --- |
| API JSON có web client hoặc nhiều ngôn ngữ | Decimal **string** |
| Chỉ có các service dùng parser decimal đã được xác minh | JSON number có thể dùng, kèm kiểm thử toàn tuyến |
| Dữ liệu gắn với đơn vị nhỏ nhất cố định | Integer minor units **string** cùng scale/đơn vị |
| Phải lưu đúng biểu diễn `BigDecimal` gồm scale | Decimal `toString()` hoặc cặp `unscaled/scale` |

## 5. Hợp đồng chuỗi decimal: `toString()` khác `toPlainString()`

Hai phương thức đều tạo chuỗi chứa giá trị số mà không chuyển qua `double`, nhưng **khả năng giữ scale khi parse lại khác nhau**.

| Giá trị ban đầu | `toString()` | `toPlainString()` | Parse lại có giữ scale? |
| --- | --- | --- | --- |
| `new BigDecimal("12.3400")` | `12.3400` | `12.3400` | Cả hai |
| `new BigDecimal("1E+3")` | `1E+3` | `1000` | Chỉ `toString()` |
| `new BigDecimal("1000")` | `1000` | `1000` | Cả hai |
| `new BigDecimal("0.000")` | `0.000` | `0.000` | Cả hai |

Điểm then chốt:

~~~java
BigDecimal original = new BigDecimal("1E+3");

BigDecimal canonicalRoundTrip =
        new BigDecimal(original.toString());

BigDecimal plainRoundTrip =
        new BigDecimal(original.toPlainString());

System.out.println(original.equals(canonicalRoundTrip)); // true
System.out.println(original.equals(plainRoundTrip));     // false
System.out.println(original.compareTo(plainRoundTrip));  // 0
~~~

`BigDecimal.toString()` có thể dùng ký pháp mũ (`1E+3`), nhưng biểu diễn chuẩn này chứa đủ thông tin để `new BigDecimal(original.toString()).equals(original)` trả về `true`.

`toPlainString()` loại bỏ ký pháp mũ, phù hợp để hiển thị hoặc trao đổi khi chỉ cần giữ **giá trị số học**. Với scale âm, việc đọc lại chuỗi plain thường tạo scale khác. Nếu một hệ thống chỉ cho chuỗi thập phân không có số mũ nhưng vẫn phải giữ scale, truyền kèm trường `scale` theo schema riêng.

Lưu ý: `stripTrailingZeros()` **thay đổi scale** dù giá trị giữ nguyên; không gọi nó một cách vô thức trước khi xuất dữ liệu cần round-trip chính xác theo `equals()`. Tương tự, `setScale(...)` có thể thêm số 0 hoặc làm tròn, vì vậy là một quy tắc nghiệp vụ riêng, không phải bước bắt buộc của serialization.

## 6. Thiết kế hợp đồng trao đổi cụ thể

Ví dụ thống nhất hợp đồng cho `PaymentWire`:

~~~json
{
  "currency": "USD",
  "amount": "9007199254740993.01"
}
~~~

- `currency`: mã đơn vị theo danh sách hệ thống hỗ trợ, được kiểm tra độc lập.
- `amount`: JSON **string**, chứa chuỗi canonical do `BigDecimal.toString()` tạo ra.
- Sử dụng dấu `.` làm dấu thập phân, dấu `-` cho số âm, có thể có số mũ `E` cùng dấu số mũ `+` hoặc `-`.
- Không chứa dấu phân nhóm (`,`), ký hiệu tiền tệ, khoảng trắng hoặc định dạng phụ thuộc locale.
- Giới hạn tổng ký tự, `precision`, `scale` và miền giá trị được xác định theo nghiệp vụ.
- Người nhận parse trực tiếp `String → BigDecimal`, không sử dụng `Double`, `Float`, `BigDecimal(double)` hoặc `Number` làm trung gian.
- Nếu dữ liệu không hợp lệ, người nhận trả lỗi validation rõ ràng; không âm thầm thay thế bằng `0` hoặc làm tròn.

Vì hợp đồng lựa chọn chuỗi canonical, các dạng như `"01.20"`, `"1e3"` hay `"1E+03"` có thể là chuỗi mà một parser decimal đọc được, nhưng **bị từ chối theo tính canonical** nếu đầu ra `BigDecimal.toString()` khác nguyên văn đầu vào. Nếu cần tương thích nhiều producer có quy tắc khác nhau, có thể nới canonical check nhưng vẫn giữ kiểm tra decimal chính xác và thống nhất yêu cầu bảo toàn scale.

## 7. Java 17+ — ví dụ hoàn chỉnh chạy độc lập

Tệp: `LosslessDecimalWireDemo.java`.

Đây là mô hình dữ liệu wire độc lập với thư viện JSON. Một thư viện JSON có thể ánh xạ record `PaymentWire` thành object JSON, trong đó trường `amount` mang kiểu string. Chương trình dưới đây tập trung kiểm chứng tính toàn vẹn của decimal tại điểm mã hóa/giải mã.

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public class LosslessDecimalWireDemo {
    record PaymentWire(String currency, String amount) {}

    private static final int MAX_TEXT_LENGTH = 120;
    private static final int MAX_PRECISION = 50;
    private static final int MAX_ABS_SCALE = 50;

    static PaymentWire encode(String currency, BigDecimal amount) {
        Objects.requireNonNull(currency, "currency");
        Objects.requireNonNull(amount, "amount");
        return new PaymentWire(currency, amount.toString());
    }

    static BigDecimal decode(PaymentWire wire) {
        Objects.requireNonNull(wire, "wire");
        String decimal = wire.amount();

        if (decimal == null || decimal.isEmpty()
                || decimal.length() > MAX_TEXT_LENGTH
                || !decimal.matches(
                        "-?(0|[1-9][0-9]*)(\\.[0-9]+)?([eE][+-]?[0-9]+)?"
                )) {
            throw new IllegalArgumentException("Invalid decimal string");
        }

        final BigDecimal parsed;
        try {
            parsed = new BigDecimal(decimal);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Invalid decimal number", ex);
        }

        if (parsed.precision() > MAX_PRECISION
                || Math.abs((long) parsed.scale()) > MAX_ABS_SCALE) {
            throw new IllegalArgumentException("Decimal outside contract");
        }

        // Bảo đảm một cách viết canonical tương ứng một biểu diễn.
        if (!parsed.toString().equals(decimal)) {
            throw new IllegalArgumentException("Non-canonical decimal");
        }

        return parsed;
    }

    public static void main(String[] args) {
        BigDecimal original = new BigDecimal("9007199254740993.01");
        PaymentWire wire = encode("USD", original);
        BigDecimal decoded = decode(wire);

        System.out.println("wire amount: " + wire.amount());
        System.out.println(
                "same numeric value: " + (original.compareTo(decoded) == 0)
        );
        System.out.println("same value and scale: " + original.equals(decoded));

        BigDecimal passedThroughDouble =
                BigDecimal.valueOf(original.doubleValue());
        System.out.println(
                "through double: " + passedThroughDouble.toPlainString()
        );

        BigDecimal exponent = new BigDecimal("1E+3");
        BigDecimal restored = decode(encode("USD", exponent));
        System.out.println("exponent wire: " + exponent.toString());
        System.out.println("restored scale: " + restored.scale());
        System.out.println("exponent round-trip equals: "
                + exponent.equals(restored));
        System.out.println("plain reparsed equals: "
                + exponent.equals(new BigDecimal(exponent.toPlainString())));
    }
}
~~~

Chạy:

~~~bash
javac LosslessDecimalWireDemo.java
java LosslessDecimalWireDemo
~~~

Stdout mong đợi:

~~~text
wire amount: 9007199254740993.01
same numeric value: true
same value and scale: true
through double: 9007199254740994
exponent wire: 1E+3
restored scale: -3
exponent round-trip equals: true
plain reparsed equals: false
~~~

Phần `MAX_TEXT_LENGTH`, `MAX_PRECISION` và `MAX_ABS_SCALE` là **giới hạn minh họa**, cần thiết kế lại theo miền số cho từng API. Trường `currency` trong demo chỉ được mang theo; triển khai thực tế cần xác minh enum/danh sách tiền tệ, quyền truy cập, và các quy tắc giá trị (ví dụ có cho phép số âm không). Giới hạn scale được kiểm tra **trước khi** có thao tác `toPlainString()` có thể mở rộng một số mũ khổng lồ thành chuỗi quá dài.

### Dùng với thư viện JSON

Trên Java, một thư viện JSON như Jackson có thể deserialize chuỗi JSON `"amount"` trực tiếp vào thuộc tính `String` của DTO hoặc record, sau đó gọi `decode`. Ví dụ payload:

~~~json
{"currency":"USD","amount":"9007199254740993.01"}
~~~

Trường `amount` bắt buộc giữ là **string** trong JSON schema. Khi serialize, lấy `BigDecimal.toString()` để tạo string. Khi deserialize, đọc string và gọi `new BigDecimal(String)` như ví dụ. **Không bind sang `double` hay `Double` rồi mới gọi `BigDecimal.valueOf`**.

Nếu chọn JSON number, có thể bind trực tiếp token sang `BigDecimal` bằng cấu hình parser thích hợp, nhưng phải xác nhận tất cả các mắt xích khác cũng xử lý decimal chính xác. Nhiều parser mặc định chuyển token JSON number sang kiểu binary64 hoặc một kiểu có giới hạn khác; không đủ an toàn để suy đoán từ phía gửi.

## 8. Client JavaScript: đọc chuỗi như chuỗi

Trong JavaScript thông thường:

~~~javascript
const payload = JSON.parse(
  '{"currency":"USD","amount":"9007199254740993.01"}'
);

console.log(typeof payload.amount); // string
console.log(payload.amount);        // 9007199254740993.01
~~~

Chuỗi `amount` vẫn giữ nguyên ký tự thập phân. **Không** làm thế này nếu cần tính toán chính xác:

~~~javascript
const unsafe = Number(payload.amount);
console.log(unsafe); // giá trị đã bị làm tròn
~~~

JavaScript `BigInt` phù hợp với số nguyên tùy ý, **không hỗ trợ trực tiếp phần thập phân**. Với decimal tổng quát, hãy dùng thư viện decimal tùy ý hoặc truyền chuỗi về service có `BigDecimal`. Với hợp đồng minor units, chỉ chuyển chuỗi đơn vị nhỏ nhất thành `BigInt` sau validation và giữ scale riêng.

Nếu muốn hiển thị theo locale, xử lý định dạng tại tầng UI bằng công cụ hỗ trợ decimal phù hợp. `Intl.NumberFormat` làm việc với `Number` theo các cách gọi quen thuộc; việc gọi `Number(decimalString)` trước khi format có thể đã mất chính xác. Không thay dấu chấm bằng dấu phẩy trong dữ liệu wire vì locale của người dùng.

## 9. Những đường đi khác cũng phải giữ chính xác

### HTTP/REST

- Request/response schema xác định `amount` là string và tài liệu hóa giới hạn, ví dụ `"12.3400"`.
- Bên Java nhận trực tiếp chuỗi, xác thực, parse thành `BigDecimal`.
- Bên server serialize lại từ `BigDecimal` bằng `toString()` nếu cần giữ scale.
- Kiểm thử HTTP thực tế qua serializer, gateway và client thay vì chỉ unit test hàm `decode`.

### Cơ sở dữ liệu quan hệ

Với cột `DECIMAL(p,s)` hoặc `NUMERIC(p,s)` theo đặc tả hệ quản trị, dùng `PreparedStatement.setBigDecimal(...)` và `ResultSet.getBigDecimal(...)`. Tránh đưa dữ liệu qua `setDouble/getDouble`.

~~~java
// Minh họa trong ngữ cảnh đã có PreparedStatement ps và ResultSet rs:
ps.setBigDecimal(1, new BigDecimal("1234.56"));
BigDecimal amount = rs.getBigDecimal("amount");
~~~

Đây là **đoạn minh họa JDBC**, không phải chương trình chạy độc lập. Schema database vẫn có thể áp đặt precision/scale, làm tròn hoặc từ chối dữ liệu tùy engine/cấu hình. Hãy kiểm tra chính sách cột và round-trip của chính driver/database được dùng.

### Message broker, CSV, spreadsheet và tập tin

- Payload thông qua queue vẫn dùng hợp đồng chuỗi decimal; không dùng bước mapper trung gian chuyển thành `Double`.
- CSV là text nhưng công cụ import có thể tự đoán cột thành floating point. Khai báo cột decimal là text hoặc nhập bằng parser decimal chính xác.
- Nếu truyền `unscaled/scale`, tránh đưa `unscaled` vào JSON number ở consumer JavaScript.
- Khi giao tiếp với hệ thống chưa hỗ trợ decimal chính xác, yêu cầu tiêu chuẩn đầu ra dạng **string** và kiểm tra round-trip thay vì trông chờ “JSON number lúc nào cũng chính xác”.

## 10. Validation, chuẩn hóa và bảo mật tài nguyên

Một parser decimal chính xác không đồng nghĩa mọi đầu vào đều hợp lệ:

1. **Cú pháp**: chặn `NaN`, `Infinity`, chuỗi rỗng, whitespace không quy định, dấu phân nhóm và số có format ngoài hợp đồng. `BigDecimal` không đại diện các giá trị `NaN/Infinity`.
2. **Độ dài và precision**: hạn chế số lượng chữ số để tránh payload rất dài.
3. **Scale và exponent**: giới hạn miền `scale`; không gọi `toPlainString()` trên `1E+100000000` khi chưa kiểm soát vì có thể tạo chuỗi khổng lồ.
4. **Miền giá trị**: kiểm tra số âm/dương, `min/max`, đơn vị, loại tiền và ý nghĩa trường.
5. **Canonical representation**: nếu muốn ký số, hash, cache hoặc tránh nhiều cách viết của cùng biểu diễn, xác định thuật toán canonical rồi áp dụng nhất quán. `BigDecimal.toString()` duy trì scale, nhưng nó không ép hai giá trị numerically equal có scale khác nhau thành một chuỗi.
6. **Tính nguyên tử của xử lý**: xác thực trước khi ghi database hoặc gửi tiếp, không âm thầm làm tròn tại lớp hạ tầng.

Đối với số 0, `BigDecimal` không giữ dấu âm tách biệt: `new BigDecimal("-0.00").toString()` là `"0.00"`. Nếu hợp đồng bắt buộc bảo toàn từng ký tự đầu vào (bao gồm dấu `-` của “âm 0”, số 0 đứng trước, chữ `e` thường hoặc khoảng trắng), phải lưu **raw input string** riêng. Bảo toàn `BigDecimal` theo `equals` không phải là bảo toàn byte-for-byte nguyên văn dữ liệu gốc.

Nếu phía gửi có thể cung cấp `1.00`, còn phía nhận lưu cột database scale cố định bằng `2`, có thể giữ được scale này; nhưng không nên mặc nhiên tin rằng bất kỳ cột `DECIMAL/NUMERIC` nào cũng bảo tồn đúng scale từng payload. Phải kiểm thử driver, schema và cách truy vấn.

## 11. Quy tắc kiểm thử một giao thức decimal

Một vòng kiểm thử tối thiểu:

- **Giá trị lớn**: `9007199254740993`, `9007199254740993.01`; khẳng định không qua `double` và không sai chữ số.
- **Giá trị rất nhỏ**: `0.0000000000000000000001`; khẳng định không mất phần thập phân.
- **Scale khác nhau**: `1.0` và `1.00`; kiểm tra cả `compareTo` và `equals`.
- **Scale âm**: `1E+3` và `1E-7`; xác nhận `toString` và parse lại giữ scale.
- **Số âm và số 0**: `-12.3400`, `0`, `0.00`; kiểm tra quy tắc canonical.
- **Biên validation**: payload rỗng, quá dài, có dấu phân nhóm, exponent vượt giới hạn, giá trị ngoài miền.
- **Liên thông**: Java → JSON → JavaScript → JSON → Java; các consumer phải giữ trường `amount` dưới dạng string từ đầu đến cuối.

Với hợp đồng cần giữ scale, bất biến kiểm thử có thể viết:

~~~java
BigDecimal before = new BigDecimal("1E+3");
String wireValue = before.toString();
BigDecimal after = new BigDecimal(wireValue);

assert before.equals(after);
assert before.scale() == after.scale();
~~~

Khi không bật assertions (`-ea`), Java bỏ qua `assert`; trong test JUnit nên dùng assertion framework của bộ kiểm thử để tránh phụ thuộc cờ JVM. Đây là đoạn minh họa điều kiện round-trip, không phải một ứng dụng chạy độc lập.

### Bài tập ngắn

1. Một web client nhận `{"amount":9007199254740993}` bằng `JSON.parse`. Chỗ nào có nguy cơ mất thông tin?
2. Với `new BigDecimal("1E+3")`, bạn chọn `toString()` hay `toPlainString()` để sau khi parse vẫn có `scale = -3`?
3. Một service ghi `BigDecimal("123.4500")` thành JSON string `"123.4500"`, service khác parse qua `Double` trước khi tạo `BigDecimal`. Đường truyền đó có còn bảo đảm cả giá trị và scale không?
4. Nếu hợp đồng chỉ truyền minor units là `"12345"` và quy định `scale = 2`, giá trị tiền là bao nhiêu?
5. Nếu cần giữ nguyên nguyên văn `"-0.00"`, chỉ giữ đối tượng `BigDecimal` đã parse có đủ không?

**Đáp án:** (1) `JSON.parse` tạo `Number` từ token JSON number, có thể làm tròn số nguyên vượt giới hạn an toàn. (2) `toString()`; `toPlainString()` tạo `"1000"` và mất scale âm khi đọc lại. (3) Không: bước `Double` có thể đổi giá trị hoặc làm mất scale, dù kết quả tình cờ đúng ở một số đầu vào. (4) `123.45`. (5) Không: `BigDecimal` không lưu dấu âm của số 0 dưới dạng dấu độc lập; phải lưu chuỗi đầu vào khi cần bảo toàn nguyên văn.

**Kết luận kỹ thuật:** chọn wire format decimal chính xác ngay từ schema, sử dụng `String ↔ BigDecimal` (hoặc `unscaled + scale`), xác định rõ mức bảo toàn và tuyệt đối kiểm thử toàn tuyến có JavaScript/JSON parser. Một lần chuyển qua binary64 có thể biến lỗi mất chính xác thành vĩnh viễn.
