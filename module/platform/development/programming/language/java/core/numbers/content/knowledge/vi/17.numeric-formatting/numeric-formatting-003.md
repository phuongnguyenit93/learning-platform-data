# Float.toString, Double.toString và tính chất round-trip trong Java

> **Java core – numbers · Biểu diễn và định dạng**  
> **Mục tiêu:** Hiểu vì sao một giá trị `float`/`double` được in thành chuỗi thập phân ngắn nhưng vẫn đọc lại chính xác cùng giá trị nhị phân; phân biệt *round-trip* với biểu diễn thập phân toán học chính xác; xử lý số 0 có dấu, subnormal, Infinity, NaN và lựa chọn định dạng phù hợp khi lưu, trao đổi hoặc hiển thị dữ liệu.

## 1. Câu hỏi trung tâm: vì sao Java in 0.1 thay vì một dãy chữ số dài?

Hãy chạy:

```java
double value = 0.1;
System.out.println(Double.toString(value)); // 0.1
System.out.println(Double.toHexString(value));
// 0x1.999999999999ap-4
```

Giá trị `double` ở đây **không phải chính xác phân số toán học 1/10**. Nó là một trong các số nhị phân có thể biểu diễn được bằng IEEE 754 *binary64* và nằm rất gần 0.1.

Vậy tại sao `Double.toString(value)` chỉ trả `"0.1"` thay vì in ra toàn bộ phần thập phân của số nhị phân đã lưu? Vì mục tiêu của `toString` là tạo một **chuỗi thập phân gọn, đủ nhận diện giá trị floating-point ban đầu khi parse trở lại**, không phải xuất mọi chữ số của giá trị hữu tỉ nhị phân chính xác.

Chính xác hơn, với một giá trị hữu hạn `double`:

```java
double original = 0.1;
String text = Double.toString(original);
double recovered = Double.parseDouble(text);

System.out.println(text);                 // 0.1
System.out.println(recovered == original); // true
```

Chuỗi `"0.1"` mô tả số thực toán học 0.1. Khi `Double.parseDouble` làm tròn số thực ấy về `double` gần nhất, nó thu được **đúng giá trị binary64 đã lưu**.

**Phân biệt hai phát biểu:**

- “In ra rồi parse lại giữ được *giá trị `double` ban đầu*” — đây là tính chất *round-trip*.
- “Chuỗi in ra mô tả *chính xác mọi chữ số thập phân của giá trị nhị phân*” — **không phải** điều `Double.toString` hứa.

## 2. toString và parse tạo thành một cặp round-trip

Hai cặp API điển hình là:

```java
String floatText = Float.toString(floatValue);
float restoredFloat = Float.parseFloat(floatText);

String doubleText = Double.toString(doubleValue);
double restoredDouble = Double.parseDouble(doubleText);
```

*Round-trip* là hành trình:

```text
float bits (32 bit)
    └── Float.toString(float)
             └── văn bản decimal
                      └── Float.parseFloat(text)
                               └── giá trị float ban đầu

double bits (64 bit)
    └── Double.toString(double)
             └── văn bản decimal
                      └── Double.parseDouble(text)
                               └── giá trị double ban đầu
```

Với các giá trị **hữu hạn không phải NaN**, việc parse đúng chuỗi do `toString` tạo ra bằng **parser cùng kiểu** khôi phục giá trị dấu phẩy động ban đầu; điều này bao gồm các số normal, subnormal và cả hai số 0 có dấu.

Với `+Infinity` và `-Infinity`, chuỗi đặc biệt được parse lại thành đúng vô cực tương ứng.

Với **NaN**, `toString` trả `"NaN"` và parser tạo một NaN, nhưng **không được hứa bảo toàn dấu hay các bit payload của từng NaN**. Có nhiều mẫu bit IEEE 754 biểu diễn NaN và chúng bị gom lại thành một chuỗi chung.

### Kiểm tra round-trip theo raw bits

Với số hữu hạn, nên dùng các phép quan sát bit để kiểm tra chính xác:

```java
double before = -0.0;
String text = Double.toString(before); // "-0.0"
double after = Double.parseDouble(text);

boolean sameBits = Double.doubleToRawLongBits(before)
        == Double.doubleToRawLongBits(after);
System.out.println(sameBits); // true
```

`before == after` không đủ mạnh để xác nhận dấu zero, vì `+0.0 == -0.0` là `true` trong so sánh số học Java. Với `float`, dùng `Float.floatToRawIntBits` và `Float.intBitsToFloat` khi cần quan sát/mã hóa bit.

## 3. Quy tắc chữ số của toString trong Java 17

Tài liệu Java 17 mô tả việc in các chữ số thập phân sao cho **đủ để phân biệt giá trị đang in với các giá trị floating-point kề bên**, với số chữ số thêm vào được giữ ở mức cần thiết.

Với giá trị hữu hạn, khác 0, một biểu diễn thập phân phù hợp phải tròn về giá trị gốc khi parse theo quy tắc *round to nearest, ties to even*. Định dạng cũng bắt buộc có **ít nhất một chữ số phía sau dấu chấm thập phân**, kể cả khi giá trị là một số nguyên biểu diễn được.

Ví dụ:

```java
System.out.println(Float.toString(1.0f));  // 1.0
System.out.println(Double.toString(1.0)); // 1.0
```

`"1"` có thể được parse thành cùng giá trị số, nhưng định dạng `toString` của Java chọn `"1.0"`. Vì thế, gọi nó là “chuỗi ngắn nhất” nên hiểu là **biểu diễn thập phân ngắn theo quy tắc định dạng đã quy định, đủ để phân biệt giá trị**, không nhất thiết là chuỗi có ít ký tự nhất trong mọi ngữ pháp văn bản tùy ý.

**Không có số chữ số thập phân cố định** cho mọi `float` hay `double`. Mỗi giá trị có thể cần số chữ số khác nhau để phân biệt với giá trị có thể biểu diễn ngay bên cạnh. Đó là lý do đôi khi Java in `0.1`, đôi khi in một số dài hơn như `0.30000000000000004`.

**Cảnh báo phiên bản:** thuật toán chọn/định dạng chữ số của `toString` đã được cải tiến qua các phiên bản JDK. Khi kiểm thử đòi **đúng từng ký tự**, hãy dùng đúng phiên bản Java mục tiêu và tuân thủ hợp đồng API của phiên bản đó. Thuộc tính cần bảo vệ trong bài này là khả năng parse về **cùng giá trị nhị phân**, không phải coi mọi chuỗi của mọi JDK là bất biến theo thời gian.

## 4. Khi nào Java dùng dạng thập phân thông thường, khi nào dùng E?

Theo cách định dạng trong Java 17, với **độ lớn dương hữu hạn khác 0**:

- Từ `10^-3` (bao gồm) đến dưới `10^7`: hiển thị theo dạng decimal thông thường.
- Nhỏ hơn `10^-3` hoặc từ `10^7` trở lên: hiển thị bằng *computerized scientific notation*, có ký tự `E` viết hoa và số mũ thập phân.

Ví dụ:

| Giá trị đầu vào `double` | `Double.toString` |
| --- | --- |
| `0.0` | `"0.0"` |
| `-0.0` | `"-0.0"` |
| `1.0` | `"1.0"` |
| `0.001` | `"0.001"` |
| `0.0001` | `"1.0E-4"` |
| `1_000_000.0` | `"1000000.0"` |
| `10_000_000.0` | `"1.0E7"` |

Lưu ý:

- Chuỗi `"1.0E7"` và `"10000000.0"` mô tả cùng số thực toán học; đây là **lựa chọn định dạng**.
- Chuỗi `E7` có nghĩa **nhân 10^7**, không phải mũ nhị phân.
- `toString` không dùng dấu phân nhóm hàng nghìn, ký hiệu tiền tệ hay dấu phẩy thập phân phụ thuộc vùng.
- Dấu chấm thập phân của định dạng mặc định là dấu `.`, giúp chuỗi dễ dùng để trao đổi trong các hệ thống có cùng quy ước.

**Không dùng** `Float.toString` hoặc `Double.toString` như định dạng dành cho người dùng ở mọi quốc gia: giao diện bản địa hóa cần `NumberFormat` hoặc API định dạng với `Locale` được chỉ định.

## 5. Float và Double: cùng giá trị chữ viết nhưng khác bit

`float` và `double` có độ chính xác khác nhau:

| Kiểu | Định dạng IEEE 754 | Bit phần trị chính xác hiệu dụng (normal) |
| --- | --- | --- |
| `float` | binary32, 32 bit | 24 |
| `double` | binary64, 64 bit | 53 |

Xem:

```java
float f = 0.1f;
double d = 0.1;
double widened = f; // widening float -> double

System.out.println(Float.toString(f));    // 0.1
System.out.println(Double.toString(d));   // 0.1
System.out.println(Double.toString(widened));
// 0.10000000149011612
```

Tại sao `f` và `d` đều in `"0.1"`, nhưng `widened` khác?

1. `0.1f` được làm tròn đến một giá trị **binary32** gần 0.1.
2. `0.1` được làm tròn trực tiếp đến một giá trị **binary64** gần 0.1, chính xác hơn.
3. Khi chuyển `float f` lên `double`, giá trị binary32 được giữ chính xác trong binary64, **không tự trở thành giá trị của literal `double 0.1`**.
4. Chuỗi `"0.10000000149011612"` đủ để phân biệt giá trị double đã mở rộng ấy.

Điều này cũng giải thích một cạm bẫy:

```java
float f = 0.1f;
double fromFloatBits = (double) f;
double parsedAsDouble = Double.parseDouble(Float.toString(f));

System.out.println(fromFloatBits == parsedAsDouble); // false
```

`Float.toString(f)` bảo đảm round-trip **khi dùng `Float.parseFloat`**. Nếu bạn đọc chuỗi đó bằng `Double.parseDouble`, bạn đang parse một giá trị thập phân thành một **định dạng khác**, không phải giải mã lại trực tiếp mọi bit của `float`.

**Quy tắc:** Khi cần giữ giá trị `float`, lưu và parse với đúng kiểu `float`; khi cần giữ giá trị `double`, dùng cặp API `double`. Đừng âm thầm thay parser đích bằng kiểu khác rồi suy rằng mọi chuyển đổi vẫn giống nhau.

## 6. Phân biệt chuỗi round-trip và giá trị thập phân chính xác

Giá trị `double 0.1` thực ra là một số hữu tỉ nhị phân hữu hạn, có biểu diễn thập phân đầy đủ dài hơn `"0.1"`:

```java
import java.math.BigDecimal;

double d = 0.1;
System.out.println(Double.toString(d));
// 0.1

System.out.println(new BigDecimal(d));
// 0.1000000000000000055511151231257827021181583404541015625
```

Hai chuỗi khác nhau vì:

- `Double.toString(d)` chọn văn bản **gọn đủ để parse lại `d`**.
- `new BigDecimal(d)` xây dựng giá trị thập phân mô tả **chính xác giá trị binary64 hiện có**, có thể cần rất nhiều chữ số.

Tương tự:

```java
System.out.println(BigDecimal.valueOf(0.1)); // 0.1
```

`BigDecimal.valueOf(double)` sử dụng biểu diễn thập phân canonical của `double` (theo `Double.toString`) để tạo `BigDecimal`. Đây là lựa chọn chuyển đổi hợp lý trong nhiều tình huống, **nhưng không thể khôi phục ý định số học hay bit đã mất** ở các phép tính trước đó.

Nếu nguồn nghiệp vụ gốc là chuỗi decimal cần chính xác (như tiền), nên cân nhắc tạo:

```java
BigDecimal exact = new BigDecimal("0.1");
```

Không lấy một kết quả `double` đã tính xong rồi mặc định `BigDecimal.valueOf(result)` biến toàn bộ lịch sử phép tính thành chính xác vô hạn.

## 7. Subnormal và các biên: chuỗi có thể rất ngắn dù số rất nhỏ

Ví dụ:

```java
System.out.println(Float.toString(Float.MIN_VALUE));
// 1.4E-45
System.out.println(Double.toString(Double.MIN_VALUE));
// 4.9E-324
```

`Float.MIN_VALUE` và `Double.MIN_VALUE` là **số dương khác 0 nhỏ nhất** biểu diễn được bởi kiểu tương ứng, thuộc miền *subnormal*. Giá trị nhị phân chính xác của chúng:

\[
\mathrm{Float.MIN\_VALUE} = 2^{-149}
\]
\[
\mathrm{Double.MIN\_VALUE} = 2^{-1074}
\]

Chuỗi `"1.4E-45"` và `"4.9E-324"` không hiển thị đủ mọi chữ số của hai giá trị này dưới hệ thập phân. Chúng đủ để parser làm tròn về **đúng bit subnormal nhỏ nhất** của kiểu đích.

Các giá trị biên lớn nhất:

```java
System.out.println(Float.toString(Float.MAX_VALUE));
// 3.4028235E38
System.out.println(Double.toString(Double.MAX_VALUE));
// 1.7976931348623157E308
```

Điều quan trọng khi serialize:

- Không đặt một giới hạn cố định như “số thực phải có tối đa 6 chữ số sau dấu chấm” rồi kỳ vọng round-trip cho mọi `double`.
- Giá trị rất lớn/rất nhỏ cần **số mũ E**, parser nhận lại đúng chuỗi chuẩn nếu dùng API tương ứng.
- Các giá trị thuộc miền subnormal thường nhạy với việc làm tròn thêm; đừng định dạng ngắn hơn một cách tùy ý.

## 8. Số 0 có dấu: +0.0 và -0.0 phải được phân biệt nếu xét bit

IEEE 754 có hai biểu diễn số 0:

```java
double positiveZero = +0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero); // true
System.out.println(Double.toString(positiveZero)); // 0.0
System.out.println(Double.toString(negativeZero)); // -0.0
```

Toán tử `==` coi hai số 0 bằng nhau về **giá trị số học**, nhưng chuỗi `Double.toString` vẫn giữ dấu âm.

```java
double recovered = Double.parseDouble("-0.0");
System.out.println(Double.doubleToRawLongBits(recovered)
        == Double.doubleToRawLongBits(-0.0)); // true
```

Khi ký số dữ liệu, phân biệt biểu diễn bit hoặc kiểm thử exact, dấu `-0.0` có thể mang thông tin hữu ích. Nhưng trong nhiều phép so sánh toán học, hai số 0 tương đương về giá trị.

Tương tự với `float`:

```java
float negativeZero = -0.0f;
String text = Float.toString(negativeZero); // "-0.0"
float restored = Float.parseFloat(text);
```

Nếu cần bảo toàn **toàn bộ mẫu bit của các số không phải NaN**, dùng round-trip đúng kiểu và kiểm tra qua `floatToRawIntBits`/`doubleToRawLongBits`.

## 9. NaN và Infinity: trường hợp đặc biệt của round-trip

Ba chuỗi quan trọng:

| Giá trị | Chuỗi từ `Double.toString` / `Float.toString` |
| --- | --- |
| `Double.POSITIVE_INFINITY` | `"Infinity"` |
| `Double.NEGATIVE_INFINITY` | `"-Infinity"` |
| `Double.NaN` | `"NaN"` |

Ví dụ:

```java
double pos = Double.parseDouble("Infinity");
double neg = Double.parseDouble("-Infinity");
double nan = Double.parseDouble("NaN");

System.out.println(Double.isInfinite(pos)); // true
System.out.println(neg < 0.0);              // true
System.out.println(Double.isNaN(nan));      // true
```

### Vì sao NaN không có round-trip raw bits như số hữu hạn?

IEEE 754 có nhiều bit pattern NaN, với sign và payload khác nhau. Nhưng `Double.toString` trả cùng chữ `"NaN"` cho NaN, nên **văn bản này không mang thông tin về payload và bit dấu**. Khi parse lại, kết quả là một NaN, không phải một cam kết tái tạo đúng mọi raw bit của NaN ban đầu.

Ví dụ khái niệm:

```java
long raw = 0x7ff8000000000001L; // NaN có payload khác giá trị canonical
double customNan = Double.longBitsToDouble(raw);

String text = Double.toString(customNan); // "NaN"
double parsed = Double.parseDouble(text);

System.out.println(Double.isNaN(parsed)); // true
// Không suy ra Double.doubleToRawLongBits(parsed) == raw.
```

Nếu cần truyền tải hoặc ghi lại **mọi raw bit IEEE 754**, kể cả NaN payload, sử dụng mã hóa bit rõ ràng (ví dụ `Double.doubleToRawLongBits` và một dạng hex có chiều rộng cố định) cùng API ngược `Double.longBitsToDouble`. Cũng cần thống nhất thứ tự byte, signedness và quy tắc JSON/transport nếu trao đổi qua mạng.

**Lưu ý:** Chuẩn JSON thông thường **không có literal NaN hoặc Infinity**. Chuỗi `"NaN"` của Java phù hợp cho parser Java, nhưng việc nhét trực tiếp token `NaN` không có dấu ngoặc kép vào JSON chuẩn sẽ làm dữ liệu không hợp lệ.

## 10. toString, String.valueOf và println liên quan với nhau thế nào?

Các cách in phổ biến:

```java
double x = 12.5;
String a = Double.toString(x);
String b = String.valueOf(x);
System.out.println(x);
```

Với `double` primitive thông thường, `String.valueOf(double)` dùng cách chuyển tương ứng với `Double.toString` và `println(double)` cũng cung cấp chuỗi hiển thị theo ngữ nghĩa chuyển đổi của Java. Với wrapper `Double`, lời gọi `wrapper.toString()` trả chuỗi của giá trị bên trong.

```java
Double wrapper = Double.valueOf(12.5);
String text = wrapper.toString(); // "12.5"
```

Nhưng:

```java
Double maybe = null;
// String text = maybe.toString(); // NullPointerException
String text = String.valueOf(maybe); // "null"
```

Hai phương thức trên khác nhau khi tham chiếu đối tượng là `null`: `String.valueOf(Object)` có thể trả `"null"`. Chuỗi `"null"` **không** phải một số hợp lệ để `Double.parseDouble` đọc thành numeric value; thiết kế API phải biểu diễn null riêng.

Tương tự, khi `Float wrapper = null` thì `wrapper.toString()` cũng ném NPE, còn `String.valueOf(wrapper)` có thể trả `"null"`.

## 11. Round-trip không giống định dạng hiển thị có số chữ số cố định

Ví dụ một giao diện muốn in đúng 2 chữ số sau dấu chấm:

```java
import java.util.Locale;

double pi = Math.PI;

String display = String.format(Locale.ROOT, "%.2f", pi);
System.out.println(display); // 3.14

double parsed = Double.parseDouble(display);
System.out.println(parsed == pi); // false
```

Định dạng cố định hai chữ số đã **làm tròn thông tin** về độ chính xác, nên không thể khôi phục đúng `Math.PI` ban đầu.

So sánh với cách round-trip:

```java
String canonical = Double.toString(Math.PI);
System.out.println(canonical); // 3.141592653589793
System.out.println(Double.parseDouble(canonical) == Math.PI); // true
```

**Dùng đúng mục đích:**

| Mục tiêu | API thường phù hợp |
| --- | --- |
| Chuỗi Java có thể parse trở lại cùng `float` | `Float.toString` ↔ `Float.parseFloat` |
| Chuỗi Java có thể parse trở lại cùng `double` | `Double.toString` ↔ `Double.parseDouble` |
| In số cho con người, nhóm hàng nghìn, dấu thập phân theo vùng | `NumberFormat` với `Locale` đã chọn |
| Cố định 2 chữ số để hiển thị báo cáo | `String.format(Locale.ROOT, "%.2f", x)` hoặc format theo nghiệp vụ |
| Cần chính xác thập phân theo scale/rounding | `BigDecimal` và quy tắc tạo/round được định nghĩa |
| Bảo toàn bit IEEE 754 kể cả payload NaN | Raw bits + mã hóa nhị phân/hex được đặc tả rõ |

Tránh dùng `String.format("%.2f", x)` để serialize số thực cần exact round-trip. Ngược lại, `Double.toString` không tự đáp ứng yêu cầu xuất hóa đơn “luôn có đúng 2 số lẻ”.

## 12. Làm sao kiểm thử round-trip cho đúng?

### 12.1. Dùng bits cho số hữu hạn và signed zero

```java
static boolean doubleRoundTrips(double x) {
    if (Double.isNaN(x)) {
        return Double.isNaN(
                Double.parseDouble(Double.toString(x)));
    }
    double y = Double.parseDouble(Double.toString(x));
    return Double.doubleToRawLongBits(x)
            == Double.doubleToRawLongBits(y);
}
```

Đây là phương thức minh họa cần đặt trong một lớp. Nó kiểm tra bit cho mọi giá trị **không phải NaN**, kể cả hai số 0 và Infinity; đối với NaN, nó kiểm tra **giữ được trạng thái NaN**, không yêu cầu payload giống nhau.

Với `float`, mẫu kiểm tra tương tự:

```java
static boolean floatRoundTrips(float x) {
    if (Float.isNaN(x)) {
        return Float.isNaN(
                Float.parseFloat(Float.toString(x)));
    }
    float y = Float.parseFloat(Float.toString(x));
    return Float.floatToRawIntBits(x)
            == Float.floatToRawIntBits(y);
}
```

Nếu dùng `Double.doubleToLongBits` thay vì `Double.doubleToRawLongBits`, các mẫu NaN sẽ được **canonicalize**. Điều đó hữu ích trong một số phép so sánh giá trị nhưng **không phản ánh raw payload** ban đầu. Hãy xác định rõ bạn muốn kiểm tra “cùng giá trị floating-point” hay “cùng mẫu bit”.

### 12.2. Bộ dữ liệu test nên có gì?

- `+0.0`, `-0.0`;
- số normal như `1.0`, `0.1`, `Math.PI`;
- số subnormal như `Double.MIN_VALUE`, `Float.MIN_VALUE`;
- biên normal như `Float.MIN_NORMAL`, `Double.MIN_NORMAL`;
- biên hữu hạn lớn nhất như `Float.MAX_VALUE`, `Double.MAX_VALUE`;
- `Infinity` dương/âm và NaN;
- số lớn có ULP > 1 để kiểm tra mất thông tin khi chuyển qua loại dữ liệu khác.

Một kiểm thử tốt không chỉ nhìn chuỗi bằng mắt; nó **parse bằng đúng kiểu** và kiểm tra kết quả theo tiêu chí cần giữ.

## 13. Tránh nhầm giữa định dạng decimal và biểu diễn hex floating-point

Ngoài `toString` thập phân, Java còn có:

```java
System.out.println(Double.toHexString(0.1));
// 0x1.999999999999ap-4
System.out.println(Float.toHexString(0.1f));
// 0x1.99999ap-4
```

Đây là cách mô tả **giá trị nhị phân** bằng phần trị hệ 16 và số mũ **của 2** (ký tự `p`/`P`).

Ví dụ `0x1.8p1` biểu diễn `1.5 × 2^1 = 3.0`, không phải `1.8 × 10^1`.

`Double.parseDouble` và `Float.parseFloat` chấp nhận cú pháp hex floating-point hợp lệ, nên dạng `toHexString` cũng hữu ích khi cần ghi số học nhị phân chính xác ở dạng văn bản.

Nhưng `toHexString` vẫn in `"NaN"` đối với NaN; do đó nó **không phải** cách serializing payload NaN qua một chuỗi biểu diễn giá trị. Dùng API raw bits khi cần điều ấy.

**So sánh:**

- `Double.toString(0.1)` → `"0.1"`: dễ đọc dạng decimal, đủ cho round-trip.
- `Double.toHexString(0.1)` → `"0x1.999999999999ap-4"`: thể hiện giá trị nhị phân một cách tường minh.
- `Long.toHexString(Double.doubleToRawLongBits(0.1))` → chuỗi hex của **64 bit lưu trữ**, phản ánh bit dấu, exponent và fraction chứ không phải công thức trị số `0x...p...`.

Ba dạng có mục đích khác nhau. Không trộn chúng khi định nghĩa giao thức dữ liệu hoặc so sánh output.

## 14. Chương trình Java 17+ hoàn chỉnh

Tạo tệp **`FloatingPointRoundTripDemo.java`**:

```java
import java.util.Locale;

public class FloatingPointRoundTripDemo {
    private static boolean sameDoubleBits(double a, double b) {
        return Double.doubleToRawLongBits(a)
                == Double.doubleToRawLongBits(b);
    }

    private static boolean sameFloatBits(float a, float b) {
        return Float.floatToRawIntBits(a)
                == Float.floatToRawIntBits(b);
    }

    public static void main(String[] args) {
        float f = 0.1f;
        double d = 0.1;
        double widenedFloat = f;

        System.out.println("float text = " + Float.toString(f));
        System.out.println("double text = " + Double.toString(d));
        System.out.println("widened float = "
                + Double.toString(widenedFloat));
        System.out.println("double hex = " + Double.toHexString(d));

        float parsedF = Float.parseFloat(Float.toString(f));
        double parsedD = Double.parseDouble(Double.toString(d));
        System.out.println("float round-trip = "
                + sameFloatBits(f, parsedF));
        System.out.println("double round-trip = "
                + sameDoubleBits(d, parsedD));

        double parsedFloatTextAsDouble =
                Double.parseDouble(Float.toString(f));
        System.out.println("wrong target type = "
                + (widenedFloat == parsedFloatTextAsDouble));

        System.out.println("float minimum = "
                + Float.toString(Float.MIN_VALUE));
        System.out.println("double minimum = "
                + Double.toString(Double.MIN_VALUE));
        System.out.println("double maximum = "
                + Double.toString(Double.MAX_VALUE));

        System.out.println("plain lower = "
                + Double.toString(0.001));
        System.out.println("scientific lower = "
                + Double.toString(0.0001));
        System.out.println("plain upper = "
                + Double.toString(1_000_000.0));
        System.out.println("scientific upper = "
                + Double.toString(10_000_000.0));

        double negativeZero = -0.0;
        double restoredZero =
                Double.parseDouble(Double.toString(negativeZero));
        System.out.println("negative zero = "
                + Double.toString(negativeZero));
        System.out.println("negative zero round-trip = "
                + sameDoubleBits(negativeZero, restoredZero));
        System.out.println("signed zeros == = "
                + (+0.0 == -0.0));

        System.out.println("infinity = "
                + Double.toString(Double.POSITIVE_INFINITY));
        System.out.println("NaN parsed = "
                + Double.isNaN(
                        Double.parseDouble(Double.toString(Double.NaN))));

        String display = String.format(Locale.ROOT, "%.2f", Math.PI);
        System.out.println("display Pi = " + display);
        System.out.println("display round-trip = "
                + sameDoubleBits(Math.PI,
                        Double.parseDouble(display)));
    }
}
```

Chạy từ thư mục chứa tệp:

```bash
javac FloatingPointRoundTripDemo.java
java FloatingPointRoundTripDemo
```

**Kết quả dự kiến trên Java 17:**

```text
float text = 0.1
double text = 0.1
widened float = 0.10000000149011612
double hex = 0x1.999999999999ap-4
float round-trip = true
double round-trip = true
wrong target type = false
float minimum = 1.4E-45
double minimum = 4.9E-324
double maximum = 1.7976931348623157E308
plain lower = 0.001
scientific lower = 1.0E-4
plain upper = 1000000.0
scientific upper = 1.0E7
negative zero = -0.0
negative zero round-trip = true
signed zeros == = true
infinity = Infinity
NaN parsed = true
display Pi = 3.14
display round-trip = false
```

**Những điều chương trình xác minh:**

1. `0.1f` và `0.1` đều có biểu diễn decimal ngắn `0.1` nhưng là các giá trị nhị phân khác nhau; mở rộng `float` thành `double` làm sự khác biệt hiện rõ.
2. `toString` → `parseXxx` cùng kiểu giữ nguyên raw bits của `0.1f`/`0.1`.
3. Parse văn bản `Float.toString(f)` bằng `Double.parseDouble` có thể thu được một `double` khác với giá trị `double` chuyển từ `f`.
4. Các giá trị cực nhỏ/cực lớn có biểu diễn khoa học gọn và có thể parse ngược bằng parser tương ứng.
5. Chuỗi `"-0.0"` giữ bit dấu qua round-trip; so sánh số học `+0.0 == -0.0` vẫn true.
6. NaN được khôi phục theo **loại giá trị**, không cam kết payload; định dạng cố định hai chữ số mất độ chính xác của `Math.PI`.

## 15. Lỗi phổ biến cần tránh

| Hiểu lầm | Giải thích đúng |
| --- | --- |
| “`Double.toString(0.1)` ra 0.1 nghĩa là double lưu chính xác 1/10” | Chuỗi được chọn để parse lại cùng giá trị nhị phân; giá trị lưu vẫn là số gần 1/10 |
| “Float và Double cùng in 0.1 thì raw bits có cùng giá trị số” | Hai kiểu có độ chính xác khác nhau; widen `0.1f` cho `0.10000000149011612` |
| “Chuỗi round-trip có thể chứa số chữ số tùy ý và vẫn giữ nguyên” | Rút ngắn/làm tròn thêm có thể biến thành giá trị khác khi parse |
| “Round-trip nghĩa là giữ toàn bộ bit của mọi NaN” | Chuỗi `NaN` không bảo toàn payload/dấu NaN |
| “Dùng `==` kiểm tra round-trip là đủ cả với -0.0” | `+0.0 == -0.0`; cần so raw bits nếu quan tâm signed zero |
| “Double.toString luôn in số thập phân không có E” | Java dùng `E` khi độ lớn nằm ngoài khoảng hiển thị decimal thường |
| “String.format("%.2f") cho phép round-trip nguyên vẹn” | Format này giới hạn chữ số nên có thể mất độ chính xác |
| “Double.toHexString là raw 64-bit hex” | `0x...p...` biểu diễn giá trị nhị phân; raw bits cần `doubleToRawLongBits` |
| “String.valueOf(null Double) luôn giống gọi wrapper.toString” | `String.valueOf(Object)` trả `"null"`; gọi phương thức trên null gây NPE |
| “Tăng số chữ số in ra có thể sửa lỗi số học đã xảy ra” | Format không khôi phục thông tin mất do phép tính/làm tròn trước đó |
| “Locale không ảnh hưởng định dạng hiển thị” | `NumberFormat`/`String.format` có thể chịu locale; `Double.toString` là định dạng Java độc lập locale |
| “Chuỗi Infinity và NaN hợp lệ như số trong JSON chuẩn” | JSON chuẩn không có các literal này; giao thức phải định nghĩa cách xử lý |
| “Mọi JDK phải in giống từng ký tự từ mọi thuật toán chuyển số” | Khi cần so sánh literal output, phải biết hợp đồng/phiên bản JDK; mục tiêu chính là round-trip đúng giá trị |

## 16. Bài tập có lời giải

**Bài 1.** Tại sao `Double.toString(0.1)` trả `"0.1"` dù `new BigDecimal(0.1)` in nhiều chữ số hơn?  
**Lời giải:** `toString` tìm văn bản thập phân ngắn đủ để parse về cùng `double`; `new BigDecimal(double)` mô tả chính xác giá trị nhị phân đã lưu trong thập phân.

**Bài 2.** Với `float f = 0.1f;`, `Float.parseFloat(Float.toString(f))` có lấy lại giá trị `float` ban đầu không?  
**Lời giải:** Có. Đây là đúng cặp API bảo đảm round-trip cho `float`, bao gồm mẫu bit của các giá trị không phải NaN.

**Bài 3.** Vì sao `Double.parseDouble(Float.toString(0.1f))` không nhất thiết bằng `(double)0.1f`?  
**Lời giải:** Chuỗi `"0.1"` được chọn để parse **về `float`**. Khi parse trực tiếp thành `double`, nó thành giá trị binary64 gần 0.1 chứ không phải binary64 biểu diễn chính xác giá trị binary32 đã widen.

**Bài 4.** `Double.toString(-0.0)` in gì? `Double.parseDouble` có giữ dấu zero không?  
**Lời giải:** In `"-0.0"` và parse lại thành zero âm. Kiểm tra raw bits bằng `Double.doubleToRawLongBits`; phép `==` không phân biệt được ±0.

**Bài 5.** `Double.toString(Double.MIN_VALUE)` trả chuỗi nào và có phải in toàn bộ thập phân chính xác của `2^-1074` không?  
**Lời giải:** `"4.9E-324"` trên Java 17. Đó là chuỗi đủ để parse trở lại `Double.MIN_VALUE`, không phải mọi chữ số thập phân của giá trị hữu tỉ nhị phân chính xác.

**Bài 6.** Khi `Double.toString(Double.NaN)` trả `"NaN"`, có thể tái tạo mọi payload NaN ban đầu bằng `parseDouble` không?  
**Lời giải:** Không. Ta chỉ bảo đảm parse ra một NaN. Nếu phải bảo toàn payload, cần serializing raw bits.

**Bài 7.** Giải thích tại sao `String.format(Locale.ROOT, "%.2f", Math.PI)` không bảo đảm round-trip.  
**Lời giải:** Nó tạo `"3.14"`, đã bỏ các chữ số cần thiết để phân biệt `Math.PI` với các `double` lân cận. Parse lại thành một `double` khác.

**Bài 8.** Giá trị `10_000_000.0` được `Double.toString` in dạng nào trong Java 17?  
**Lời giải:** `"1.0E7"`, vì miền dùng dạng thập phân thông thường chỉ bao gồm độ lớn nhỏ hơn `10^7`.

**Bài 9.** API nào thích hợp để ghi nguyên mẫu bit của NaN có payload khác nhau?  
**Lời giải:** `Double.doubleToRawLongBits` hoặc `Float.floatToRawIntBits`, sau đó tự mã hóa bit theo định dạng dữ liệu; khi đọc dùng `Double.longBitsToDouble` hoặc `Float.intBitsToFloat`.

**Bài 10.** Có thể dùng `Double.toString` thay cho định dạng hóa đơn luôn đúng hai chữ số phần lẻ không?  
**Lời giải:** Không. Nó được tối ưu cho chuỗi giá trị floating-point có thể parse lại, không bảo đảm độ dài phần thập phân hay quy tắc làm tròn tài chính. Chọn `BigDecimal` và định dạng theo hợp đồng.

## 17. Checklist khi xuất/nhập float và double

1. **Xác định mục tiêu:** xuất để con người đọc, để lưu/trao đổi có round-trip, hay để bảo toàn raw bits?
2. **Dùng đúng cặp kiểu:** `Float.toString` ↔ `Float.parseFloat`; `Double.toString` ↔ `Double.parseDouble`.
3. **Đừng suy ngược từ văn bản:** một chuỗi `0.1` không có nghĩa binary floating-point lưu chính xác thập phân 0.1.
4. **Đừng dùng định dạng ít chữ số** nếu cần bảo toàn giá trị bit; đặc biệt với số có ULP nhỏ hoặc chuỗi đã tính toán phức tạp.
5. **Kiểm tra signed zero:** `-0.0` có thể cần được giữ; raw bit comparison đáng dùng khi test serialization.
6. **Xử lý NaN riêng:** round-trip văn bản giữ trạng thái NaN nhưng không cam kết payload; Infinity cũng cần được giao thức cho phép.
7. **Nhận biết scientific notation:** `E` là lũy thừa của 10; `p` trong `toHexString` là lũy thừa của 2.
8. **Kiểm tra locale/giao thức:** `toString` ổn định theo quy tắc Java, còn UI và JSON/CSV có ràng buộc định dạng riêng.
9. **Nếu cần decimal exact**, lưu từ nguồn `String` hoặc dùng `BigDecimal` theo quy tắc nghiệp vụ, không đổi kiểu sau khi `double` đã làm tròn để mong “lấy lại dữ liệu”.
10. **Kiểm thử biên:** ±0, subnormal, max, infinity, NaN và sự khác nhau giữa widening `float → double` và parse decimal thành `double`.

### Tài liệu Java 17

- [Float – toString, parseFloat, toHexString, floatToRawIntBits](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html)
- [Double – toString, parseDouble, toHexString, doubleToRawLongBits](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html)
- [BigDecimal – constructor từ double và valueOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html)

**Ghi nhớ:** `Float.toString` và `Double.toString` chọn một văn bản thập phân **đủ để parse lại đúng giá trị floating-point**, không phải xuất đầy đủ thập phân toán học của bit pattern. Hãy dùng parser **cùng kiểu**, kiểm tra bit khi cần phân biệt số 0 có dấu, xử lý NaN riêng và chọn định dạng chuyên biệt nếu yêu cầu là giao diện, tiền hoặc bảo toàn raw bits.
