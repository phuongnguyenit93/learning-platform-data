# Kiểm tra biểu diễn số khoa học và quy tắc ghi số

JSON cho phép biểu diễn số bằng ký pháp thông thường hoặc ký pháp khoa học (scientific notation). Ví dụ, `1000000`, `1e6` và `1E+6` biểu diễn cùng một giá trị số. Jackson có thể đọc các dạng này và ghi số từ kiểu Java ra JSON, nhưng kết quả văn bản phụ thuộc kiểu Java, cách tạo giá trị và cấu hình generator.

Khi làm việc với dữ liệu số, cần tách ba vấn đề:

- **Giá trị số:** giá trị toán học mà ứng dụng muốn biểu diễn.
- **Kiểu Java:** `int`, `long`, `double`, `BigInteger`, `BigDecimal` hoặc kiểu khác dùng để lưu giá trị.
- **Cách ghi JSON:** dạng số nguyên, thập phân hay ký pháp khoa học; đây là biểu diễn văn bản của giá trị.

Sự khác biệt đặc biệt quan trọng với số thập phân chính xác như giá tiền, tỷ lệ và số đo. `double` dùng biểu diễn dấu phẩy động nhị phân nên có thể làm tròn; `BigDecimal` biểu diễn thập phân với độ chính xác tùy ý và cho phép kiểm soát rõ hơn cách ghi số. Jackson cũng có tùy chọn để ghi `BigDecimal` ở dạng plain notation thay vì scientific notation.

## 1. JSON cho phép ký pháp khoa học

Trong JSON, một number có thể có dấu âm, phần nguyên, phần thập phân và phần số mũ. Phần số mũ bắt đầu bằng `e` hoặc `E`, có thể kèm dấu `+` hoặc `-`.

Ví dụ hợp lệ:

```json
{
  "whole": 1200,
  "decimal": 12.50,
  "small": 1e-8,
  "large": 6.02E+23,
  "negative": -3.5e2
}
```

Các ví dụ trên tương ứng với những giá trị số; chữ `e` không làm cho giá trị trở thành chuỗi. Ký pháp khoa học được hiểu như phép nhân với lũy thừa của 10:

| Biểu diễn JSON | Giá trị toán học |
| --- | ---: |
| `1e3` | 1000 |
| `1.25e2` | 125 |
| `1e-3` | 0.001 |
| `-2.5E+4` | -25000 |

JSON cũng có các quy tắc cú pháp chặt chẽ. Một số ví dụ không hợp lệ:

```text
.5       // Không được có dấu + ở đầu số và thiếu phần nguyên
01       // Không được có số 0 đứng trước một phần nguyên nhiều chữ số
1.       // Phần thập phân phải có ít nhất một chữ số
1e       // Phần số mũ phải có ít nhất một chữ số
NaN      // Không phải number hợp lệ trong JSON
Infinity // Không phải number hợp lệ trong JSON
```

JSON number dùng dấu chấm `.` làm dấu phân cách thập phân và không có dấu phân nhóm hàng nghìn. Ví dụ `1234.56` hợp lệ; `1,234.56` và `1234,56` không phải JSON number hợp lệ.

### 1.1. Number khác với chuỗi chứa số

Hai JSON sau có kiểu dữ liệu khác nhau:

```json
{ "amount": 1e3 }
```

```json
{ "amount": "1e3" }
```

Trong trường hợp đầu, `amount` là JSON number. Trong trường hợp thứ hai, `amount` là JSON string chứa các ký tự `1e3`. Nếu Java property có kiểu số, Jackson có thể thực hiện coercion từ chuỗi sang số tùy cấu hình, nhưng đó là một quy tắc chuyển kiểu khác. Nếu hợp đồng API quy định trường là số, nên gửi JSON number thay vì dựa vào coercion từ string.

## 2. Jackson đọc số khoa học như thế nào?

Jackson parser nhận diện number token theo cú pháp JSON. Khi Databind ánh xạ token đó vào kiểu Java, kiểu đích quyết định cách lưu giá trị.

Ví dụ đọc trực tiếp vào `BigDecimal`:

```java
import com.fasterxml.jackson.databind.ObjectMapper;

import java.math.BigDecimal;

ObjectMapper mapper = new ObjectMapper();

BigDecimal value = mapper.readValue("1.25e3", BigDecimal.class);
System.out.println(value);
```

`BigDecimal` có thể biểu diễn chính xác giá trị thập phân của token `1.25e3`, tương ứng 1250. Ký pháp đầu vào có thể là scientific notation; kiểu đích không bắt buộc phải là `double`.

Nếu đọc vào `double`:

```java
double value = mapper.readValue("1.25e3", Double.class);
```

Jackson tạo giá trị dấu phẩy động nhị phân. Kiểu này phù hợp với nhiều phép tính khoa học và kỹ thuật, nhưng không bảo đảm biểu diễn chính xác mọi số thập phân.

## 3. Chọn kiểu Java phù hợp với dữ liệu số

| Kiểu Java | Đặc điểm | Tình huống thường gặp |
| --- | --- | --- |
| `int`, `long` | Số nguyên có giới hạn phạm vi | Bộ đếm, số lượng, mã số dạng số nếu không cần giữ số 0 đầu |
| `BigInteger` | Số nguyên độ lớn tùy ý | Số nguyên vượt phạm vi `long` |
| `float`, `double` | Dấu phẩy động nhị phân, độ chính xác hữu hạn | Tính toán khoa học, đo lường, mô phỏng |
| `BigDecimal` | Số thập phân độ chính xác tùy ý, có scale | Tiền, tỷ lệ, số thập phân cần kiểm soát độ chính xác |

### 3.1. Vì sao không nên dùng double cho tiền?

Nhiều số thập phân không có biểu diễn nhị phân hữu hạn. Vì vậy, giá trị `0.1` được lưu trong `double` dưới dạng số gần đúng. Khi thực hiện nhiều phép tính, sai số biểu diễn có thể tích lũy.

Ví dụ:

```java
double a = 0.1;
double b = 0.2;
System.out.println(a + b); // Thường in 0.30000000000000004
```

Với tiền hoặc dữ liệu cần quy tắc làm tròn xác định, nên dùng `BigDecimal`:

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");

BigDecimal total = a.add(b);
System.out.println(total); // 0.3
```

Hãy tạo `BigDecimal` từ chuỗi thập phân hoặc từ nguồn dữ liệu chính xác. `new BigDecimal(0.1)` nhận một `double` đã xấp xỉ trước đó, vì vậy nó sẽ giữ lại biểu diễn chính xác của giá trị nhị phân gần đúng ấy, không phải số thập phân `0.1` mà người viết thường mong muốn. `BigDecimal.valueOf(0.1)` thường dễ dùng hơn constructor nhận `double`, nhưng với dữ liệu JSON hoặc dữ liệu tiền, tạo trực tiếp từ chuỗi là cách rõ ràng nhất.

## 4. Jackson ghi BigDecimal ở dạng nào?

`BigDecimal` có thể lưu một giá trị theo dạng plain hoặc scientific notation. Cách `BigDecimal.toString()` chọn biểu diễn có thể dùng ký pháp khoa học khi scale hoặc exponent phù hợp. Ví dụ:

```java
BigDecimal small = new BigDecimal("0.0000000123");
BigDecimal large = new BigDecimal("1E+9");

System.out.println(small.toString());
System.out.println(small.toPlainString());

System.out.println(large.toString());
System.out.println(large.toPlainString());
```

`toString()` có thể trả về dạng scientific notation; `toPlainString()` tạo biểu diễn thập phân không dùng số mũ. Mặc định, Jackson có thể ghi `BigDecimal` dựa trên biểu diễn `toString()`, vì vậy JSON output đôi khi có `E` hoặc `e`.

Ví dụ về hai dạng JSON có thể biểu diễn cùng giá trị:

```json
{ "amount": 1.23E-8 }
```

```json
{ "amount": 0.0000000123 }
```

Cả hai đều là JSON number. Dạng plain thường dễ đọc hơn với người dùng hoặc một số hệ thống tích hợp; dạng scientific notation có thể ngắn hơn đáng kể với số rất lớn hoặc rất nhỏ.

### 4.1. Ghi BigDecimal bằng plain notation

Jackson Core cung cấp `JsonGenerator.Feature.WRITE_BIGDECIMAL_AS_PLAIN`. Bật feature này trên `JsonFactory` để các generator do factory tạo ra ghi `BigDecimal` bằng plain notation:

```java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();
mapper.getFactory().configure(
        JsonGenerator.Feature.WRITE_BIGDECIMAL_AS_PLAIN,
        true
);
```

Sau cấu hình, khi serialize một `BigDecimal` như `new BigDecimal("1E+9")`, generator ghi số theo dạng plain thay vì dùng exponent notation. Cấu hình trên thuộc factory của mapper, nên cần thiết lập trong giai đoạn khởi tạo trước khi mapper được chia sẻ và sử dụng.

Một ví dụ đầy đủ:

```java
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.math.BigDecimal;

public class NumberOutputExample {
    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = new ObjectMapper();
        mapper.getFactory().configure(
                JsonGenerator.Feature.WRITE_BIGDECIMAL_AS_PLAIN,
                true
        );

        BigDecimal amount = new BigDecimal("1E+9");
        String json = mapper.writeValueAsString(amount);

        System.out.println(json); // 1000000000
    }
}
```

Feature này dành cho `BigDecimal`. Không nên kỳ vọng nó buộc mọi `double` hoặc `float` phải được ghi ở dạng plain notation. Cách ghi của các kiểu dấu phẩy động còn phụ thuộc biểu diễn số của Java và generator.

### 4.2. Ghi số mũ hay plain notation là lựa chọn hợp đồng

JSON cho phép cả hai cách biểu diễn, vì vậy không có một dạng duy nhất đúng cho mọi hệ thống. Hãy chọn dựa trên yêu cầu của bên nhận:

- Nếu consumer hỗ trợ JSON number theo chuẩn và không yêu cầu dạng văn bản cụ thể, scientific notation là hợp lệ.
- Nếu hệ thống tích hợp yêu cầu số thập phân plain, cấu hình `WRITE_BIGDECIMAL_AS_PLAIN` cho `BigDecimal`.
- Nếu cần giữ nguyên chính xác cách người dùng nhập số, cần lưu thêm chuỗi gốc; parse rồi serialize không bảo đảm giữ nguyên lexical form.
- Nếu consumer yêu cầu số có dấu phân nhóm hoặc định dạng theo locale, đó không còn là JSON number chuẩn. Cần dùng chuỗi theo hợp đồng riêng, không chèn dấu phẩy vào JSON numeric token.

## 5. Độ chính xác khi deserialize số không định kiểu

Khi JSON được đọc vào một property có kiểu rõ ràng như `BigDecimal`, Jackson biết kiểu đích cần tạo. Nhưng nếu đọc vào `Object`, `Number` hoặc một cấu trúc không định kiểu, Jackson phải chọn một kiểu Java mặc định cho số.

Với JSON floating-point number, hành vi mặc định thường dùng `Double`. Nếu số có nhiều chữ số thập phân, việc chuyển qua `double` có thể làm mất độ chính xác. Có thể bật `DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS` để các floating-point number trong ngữ cảnh untyped được đọc thành `BigDecimal`:

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();
mapper.enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS);

Object payload = mapper.readValue("1.234567890123456789", Object.class);
System.out.println(payload.getClass()); // BigDecimal
```

Feature này chủ yếu tác động khi kiểu đích là untyped `Object`/`Number` hoặc cấu trúc tương tự. Nếu DTO khai báo field là `BigDecimal`, hãy dùng kiểu đó trực tiếp; không cần bật feature chỉ để đọc field đã có kiểu rõ ràng.

### 5.1. Số nguyên lớn trong ngữ cảnh untyped

Với JSON integer, Jackson thường chọn kiểu số nguyên phù hợp theo kích thước giá trị. Nếu cần buộc các integer trong ngữ cảnh untyped thành `BigInteger`, có thể bật:

```java
mapper.enable(DeserializationFeature.USE_BIG_INTEGER_FOR_INTS);
```

Điều này hữu ích khi xử lý payload động có thể chứa số nguyên vượt giới hạn `long`, hoặc khi ứng dụng muốn giữ phạm vi số nguyên rộng. Cần cân nhắc kiểu Java mà code phía sau mong đợi vì kết quả untyped sẽ là `BigInteger` thay vì `Integer`/`Long`.

## 6. BigDecimal giữ scale và số 0 ở cuối

`BigDecimal` lưu giá trị bằng unscaled value và scale. Vì vậy, `1.0` và `1.00` có cùng giá trị toán học nhưng có scale khác nhau. Điều này có thể quan trọng trong miền nghiệp vụ như tiền tệ hoặc phép tính cần giữ số chữ số thập phân có ý nghĩa.

Ví dụ:

```java
BigDecimal oneDecimal = new BigDecimal("1.0");
BigDecimal twoDecimals = new BigDecimal("1.00");

System.out.println(oneDecimal.equals(twoDecimals));    // false
System.out.println(oneDecimal.compareTo(twoDecimals)); // 0
```

`equals()` xét cả giá trị và scale; `compareTo()` so sánh giá trị số. Khi serialize, scale có thể ảnh hưởng số chữ số thập phân được ghi. Không nên gọi `stripTrailingZeros()` một cách tự động nếu số chữ số thập phân mang ý nghĩa trong hợp đồng.

Ví dụ:

```java
BigDecimal amount = new BigDecimal("123.4500");
System.out.println(amount.toPlainString()); // 123.4500
System.out.println(amount.stripTrailingZeros().toPlainString()); // 123.45
```

Nếu API quy định số tiền luôn có hai chữ số thập phân, hãy áp dụng scale và rounding mode theo quy tắc nghiệp vụ trước khi serialize. Jackson ghi giá trị của `BigDecimal`; nó không tự quyết định quy tắc làm tròn tiền cho ứng dụng.

## 7. Không định dạng JSON number theo locale

Các API định dạng số cho giao diện người dùng có thể dùng dấu phẩy làm dấu thập phân hoặc dấu chấm làm dấu phân nhóm tùy locale. JSON number không sử dụng những quy tắc đó.

Ví dụ, một formatter theo locale có thể tạo chuỗi:

```text
1.234,56
```

Đây không phải JSON number hợp lệ. Nếu đưa vào JSON như một numeric token, parser sẽ từ chối. Nếu đặt trong dấu nháy kép, nó là string và bên nhận phải tự hiểu quy tắc locale.

Với JSON, hãy để Jackson ghi giá trị số từ kiểu Java. Nếu giao diện cần hiển thị `1.234,56`, hãy định dạng ở tầng presentation hoặc gửi một field string riêng theo hợp đồng, không thay đổi cách biểu diễn numeric token.

## 8. Ký pháp đầu vào và đầu ra không nhất thiết giống nhau

Một parser chuyển token JSON thành giá trị Java. Sau khi parse, ứng dụng thường giữ giá trị và kiểu Java, không giữ nguyên chính xác chuỗi ký tự đầu vào.

Ví dụ, JSON đầu vào có thể là:

```json
{ "amount": 1e3 }
```

Sau khi đọc vào `BigDecimal`, serialize lại có thể tạo ra `1000`, `1E+3` hoặc một dạng hợp lệ khác tùy kiểu giá trị, scale và cấu hình generator. Không nên kỳ vọng Jackson bảo toàn nguyên văn cách viết `1e3` ban đầu.

Nếu yêu cầu nghiệp vụ là lưu lại chính xác cách người dùng nhập, chẳng hạn giữ nguyên số mũ, số 0 ở cuối hoặc dấu cộng của exponent, hãy giữ raw JSON token/chuỗi gốc song song với giá trị đã parse. Một giá trị số và cách viết ban đầu của nó là hai thông tin khác nhau.

## 9. Ví dụ DTO dùng BigDecimal

Một DTO nhận và trả giá tiền có thể khai báo:

```java
import java.math.BigDecimal;

public record PaymentRequest(
        String currency,
        BigDecimal amount
) {}
```

JSON request:

```json
{
  "currency": "VND",
  "amount": 125000.50
}
```

Jackson ánh xạ `amount` trực tiếp thành `BigDecimal`. Khi ghi lại, generator có thể dùng scientific notation nếu cách biểu diễn nội bộ của `BigDecimal` chọn dạng đó. Nếu hợp đồng yêu cầu plain notation, bật `WRITE_BIGDECIMAL_AS_PLAIN` trên factory.

Với dữ liệu tiền, ứng dụng nên kiểm tra thêm:

- Currency có hợp lệ không.
- Số tiền có âm hay vượt giới hạn nghiệp vụ không.
- Scale có phù hợp với currency hay không.
- Có cần rounding mode cụ thể không.
- Có cho phép exponent notation ở consumer hay không.

Jackson chỉ xử lý ánh xạ số; validation và quy tắc tiền tệ thuộc về domain/application layer.

## 10. Những điểm cần lưu ý khi cấu hình

1. `WRITE_BIGDECIMAL_AS_PLAIN` chỉ ảnh hưởng cách ghi `BigDecimal`; nó không thay đổi kiểu Java của giá trị và không ép `double` thành `BigDecimal`.
2. Cấu hình trên `JsonFactory` ảnh hưởng generator được tạo từ factory đó. Hãy cấu hình mapper/factory trong giai đoạn khởi tạo.
3. `USE_BIG_DECIMAL_FOR_FLOATS` chủ yếu ảnh hưởng số dấu phẩy động trong ngữ cảnh untyped; field có kiểu `BigDecimal` đã có kiểu đích rõ ràng.
4. `USE_BIG_INTEGER_FOR_INTS` có thể thay đổi kiểu Java của integer trong ngữ cảnh untyped.
5. Scientific notation là JSON number hợp lệ. Chỉ dùng string khi hợp đồng thật sự quy định trường là chuỗi.
6. `BigDecimal` giữ scale; việc bỏ số 0 ở cuối có thể làm thay đổi ý nghĩa trình bày hoặc quy tắc so sánh bằng `equals()`.
7. Plain notation với exponent cực lớn có thể tạo chuỗi rất dài. Cần giới hạn độ lớn và scale đầu vào để tránh payload khổng lồ hoặc tiêu tốn tài nguyên.

## 11. Ghi nhớ

- JSON hỗ trợ exponent notation như `1e3`, `1.25E-4` và `-2E+6`.
- `1e3` là number; `"1e3"` là string.
- Dùng `BigDecimal` cho số thập phân cần độ chính xác; tạo từ chuỗi để tránh mang sai số từ `double`.
- Jackson có thể ghi `BigDecimal` bằng scientific notation; `JsonGenerator.Feature.WRITE_BIGDECIMAL_AS_PLAIN` yêu cầu ghi dạng plain.
- `USE_BIG_DECIMAL_FOR_FLOATS` giúp giữ độ chính xác hơn khi đọc floating-point number vào kiểu untyped.
- `BigDecimal` giữ scale và có thể giữ số 0 ở cuối; đừng tự động strip nếu scale có ý nghĩa.
- JSON number không dùng định dạng locale; không chèn dấu phân nhóm hoặc dấu phẩy thập phân vào numeric token.
- Parse rồi serialize lại không bảo đảm giữ nguyên lexical form ban đầu. Nếu cần giữ nguyên văn, lưu chuỗi/token gốc.

Khi thiết kế hợp đồng số, hãy quyết định kiểu Java, độ chính xác, scale và dạng JSON mà consumer chấp nhận. Sau đó cấu hình Jackson đúng phạm vi và kiểm thử với số rất lớn, rất nhỏ, số mũ dương/âm, số thập phân nhiều chữ số và giá trị có số 0 ở cuối.
