# Định dạng ít chữ số không sửa sai số của giá trị đang lưu trong Java

Trong Java, một giá trị `double` có thể **hiển thị** thành `0.30` trong khi giá trị thực sự đang giữ là số dấu phẩy động gần `0.30000000000000004`. Việc yêu cầu `printf`, `String.format` hay `DecimalFormat` in hai chữ số sau dấu thập phân chỉ thay đổi **chuỗi trình bày**. Nó không cập nhật biến, không thay đổi các bit của `double` và không chữa sai số đã xuất hiện trong phép tính.

Bài học thuộc chủ đề **Sai số và ổn định**. Mục tiêu là phân biệt rõ (1) biểu diễn nhị phân được lưu, (2) chuỗi văn bản nhìn thấy, (3) phép làm tròn có chủ đích và (4) tính toán thập phân chính xác bằng `BigDecimal` khi miền nghiệp vụ yêu cầu. Sự khác biệt quyết định cách kiểm thử số thực, cộng dồn, xuất dữ liệu và tính toán tiền tệ.

## 1. Ba tầng thường bị đánh đồng

| Tầng | Ví dụ | Điều gì thực sự xảy ra? |
| --- | --- | --- |
| Giá trị đang lưu trong `double` | `double sum = 0.1 + 0.2;` | Máy lưu mẫu bit của một giá trị `double` gần tổng toán học |
| Chuỗi dùng để hiển thị | `String.format(Locale.ROOT, "%.2f", sum)` | Tạo chuỗi `"0.30"`; **không sửa `sum`** |
| Giá trị đã được làm tròn/định lượng lại | `Math.round(sum * 100.0) / 100.0` | Tính và gán một **giá trị `double` mới** (nhưng vẫn là binary floating point) |
| Số thập phân theo chính sách | `new BigDecimal("0.30")` | Lưu số thập phân bằng `BigDecimal`, có thể làm tròn theo `RoundingMode` |

Hai khái niệm quan trọng:

- **Formatting**: biến đổi *cách thể hiện một giá trị* thành ký tự. Số chữ số in ra không đồng nghĩa số chữ số được lưu.
- **Rounding**: tạo kết quả số học hoặc thập phân mới theo một quy tắc làm tròn. Nó có thể thay đổi kết quả được giữ nếu bạn thực sự gán lại, nhưng không đảm bảo một `double` trở thành thập phân chính xác.

Ngay cả khi màn hình, log, bảng hay JSON được yêu cầu “hiển thị ngắn”, bản thân những phép tính trước đó vẫn đã được thực thi trên giá trị đang lưu.

## 2. Vì sao `0.1 + 0.2` không bằng chính xác `0.3`?

`float` và `double` dùng dạng dấu phẩy động nhị phân IEEE 754. Phần lớn phân số thập phân như 0.1, 0.2 và 0.3 có biểu diễn nhị phân **vô hạn tuần hoàn**, nên cần làm tròn về mẫu bit gần nhất khi lưu ở độ rộng hữu hạn. Khi cộng hai toán hạng đã được làm tròn, kết quả tiếp tục được làm tròn theo quy tắc dấu phẩy động.

~~~java
double sum = 0.1 + 0.2;
System.out.println(sum);             // 0.30000000000000004
System.out.println(sum == 0.3);      // false
System.out.println(sum - 0.3);       // 5.551115123125783E-17
~~~

`0.3` dưới dạng literal `double` cũng là số nhị phân xấp xỉ, nhưng biểu diễn đó **khác một khoảng rất nhỏ** so với kết quả `0.1 + 0.2`. Toán tử `==` so sánh hai giá trị dấu phẩy động đang lưu theo quy tắc Java, không tự áp dụng dung sai thập phân.

Đầu ra mặc định của `Double.toString` và `System.out.println(double)` thường là dạng thập phân ngắn đủ để đọc lại đúng mẫu bit (`shortest round-trip representation`), **không phải bản khai triển thập phân đầy đủ của bit lưu trữ**. Để thấy giá trị thập phân chính xác tương ứng với `double`, có thể dùng `new BigDecimal(sum)` cho mục đích phân tích. Phương pháp đó khác với cách khởi tạo `BigDecimal` được khuyến nghị cho dữ liệu thập phân chính xác.

## 3. `String.format` và `printf` chỉ thay đổi những gì được nhìn thấy

~~~java
double sum = 0.1 + 0.2;
String display = String.format(java.util.Locale.ROOT, "%.2f", sum);
System.out.println(display); // 0.30
System.out.println(sum);     // 0.30000000000000004
~~~

`%.2f` yêu cầu định dạng cố định với hai chữ số sau dấu thập phân. Formatter tạo chuỗi, **không gán ngược vào biến `sum`**. Tương tự:

~~~java
System.out.printf(java.util.Locale.ROOT, "Kết quả: %.2f%n", sum);
// In: Kết quả: 0.30
// Không sửa giá trị của sum
~~~

Với `DecimalFormat`, một mẫu như `"0.00"` cũng quy định **cách trình bày**. `DecimalFormat` có các quy tắc riêng về locale, pattern và rounding mode; không nên suy đoán rằng mọi formatter có chính sách làm tròn giống nhau trong trường hợp ở đúng điểm giữa.

Dấu phân cách thập phân có thể phụ thuộc locale: mặc định của máy tại một quốc gia có thể dùng dấu phẩy. Khi cần xuất văn bản máy đọc hoặc một ví dụ có output xác định, chỉ định `Locale.ROOT` hoặc một locale cố định phù hợp. Khi hiển thị cho người dùng, chọn locale theo yêu cầu giao diện.

**Lỗi tư duy phổ biến:** thấy `0.30` trong log và kết luận phép tính đã chính xác tới hai chữ số. Log chỉ thể hiện một bản rút gọn, có thể giấu chênh lệch đủ lớn để ảnh hưởng so sánh, ngưỡng quyết định hoặc phép tính tiếp theo.

## 4. Ví dụ Java 17+ chạy độc lập

Lưu tệp tên `DisplayVsValue.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Locale;

public class DisplayVsValue {
    public static void main(String[] args) {
        double result = 0.1 + 0.2;
        String displayed =
                String.format(Locale.ROOT, "%.2f", result);
        double parsed = Double.parseDouble(displayed);

        System.out.println("raw sum = " + result);
        System.out.println("formatted = " + displayed);
        System.out.println("raw sum after formatting = " + result);
        System.out.println("sum == 0.3 = " + (result == 0.3));
        System.out.println("parsed = " + parsed);
        System.out.println("parsed == sum = " + (parsed == result));
        System.out.println("sum - 0.3 = " + (result - 0.3));

        System.out.println("decimal from computed sum = "
                + BigDecimal.valueOf(result));
        System.out.println("exact decimal from stored double = "
                + new BigDecimal(result));
        System.out.println("scaled decimal = "
                + BigDecimal.valueOf(result)
                .setScale(2, RoundingMode.HALF_UP));

        BigDecimal exactMoney =
                new BigDecimal("0.10").add(new BigDecimal("0.20"));
        System.out.println("string decimal sum = " + exactMoney);

        double roundedDouble = Math.round(result * 100.0) / 100.0;
        System.out.println("rounded as double = " + roundedDouble);
        System.out.println("rounded double == 0.3 = "
                + (roundedDouble == 0.3));
        System.out.println("rounded double exact = "
                + new BigDecimal(roundedDouble));
    }
}
~~~

Biên dịch và chạy bằng Java 17 hoặc mới hơn:

~~~bash
javac DisplayVsValue.java
java DisplayVsValue
~~~

Stdout chính xác:

~~~text
raw sum = 0.30000000000000004
formatted = 0.30
raw sum after formatting = 0.30000000000000004
sum == 0.3 = false
parsed = 0.3
parsed == sum = false
sum - 0.3 = 5.551115123125783E-17
decimal from computed sum = 0.30000000000000004
exact decimal from stored double = 0.3000000000000000444089209850062616169452667236328125
scaled decimal = 0.30
string decimal sum = 0.30
rounded as double = 0.3
rounded double == 0.3 = true
rounded double exact = 0.299999999999999988897769753748434595763683319091796875
~~~

Đối chiếu:

- Ba dòng đầu cho thấy chuỗi `0.30` **không thay đổi biến gốc**.
- Sau khi parse chuỗi `"0.30"`, ta nhận `double` được biểu diễn ngắn là `0.3`; giá trị này **khác** kết quả ban đầu `0.1 + 0.2`. Đây là một lần chuyển đổi dữ liệu mới, không phải tác dụng phụ của `String.format`.
- `BigDecimal.valueOf(result)` thu được số thập phân `0.30000000000000004` dựa trên chuỗi dạng ngắn của `double`, trong khi `new BigDecimal(result)` biểu diễn **chính xác giá trị nhị phân đã lưu dưới dạng thập phân**. Hai cách chuyển đổi có mục đích khác nhau.
- `setScale(2, HALF_UP)` trả đối tượng `BigDecimal` mới với hai chữ số lẻ và chính sách làm tròn tường minh.
- `Math.round(...)/100.0` đã tạo một `double` mới bằng với literal `0.3` về bit, **nhưng bản thân `double` đó vẫn không lưu được 0.3 thập phân chính xác**; dòng cuối cho thấy biểu diễn thập phân đầy đủ.

## 5. Định dạng, parse và gán lại là ba hành động khác nhau

Giả sử:

~~~java
double x = 0.1 + 0.2;
String text = String.format(java.util.Locale.ROOT, "%.2f", x);
~~~

Sau hai dòng, `x` **vẫn bằng** `0.30000000000000004`. Nếu sau đó gọi `Double.parseDouble(text)`, một giá trị `double` **mới** được tính từ chuỗi định dạng. Chỉ khi bạn chủ động dùng giá trị mới, ví dụ `x = Double.parseDouble(text)`, biến `x` mới thay đổi.

Việc format rồi parse không phải phương pháp tổng quát để sửa tính chính xác:

1. Bạn đã **loại bỏ thông tin** theo độ dài hiển thị. Hai giá trị thực sự khác nhau có thể cùng thành chuỗi `"0.30"`.
2. Chuỗi có thể dùng dấu thập phân, dấu nhóm hàng nghìn hoặc chữ số theo locale; `Double.parseDouble` không phải bộ parse tùy locale.
3. Giá trị parse lại vẫn là `double` nhị phân. Nhiều phân số thập phân vẫn **không biểu diễn được chính xác**.
4. Việc format/parse trong mỗi bước tính thay đổi thuật toán theo cách khó kiểm soát và có thể tạo sai lệch do làm tròn lặp lại.

Nếu yêu cầu thực tế là lưu giá trị đã lượng tử hóa tới một số chữ số, hãy định nghĩa **quy tắc lượng tử hóa số học** cụ thể, rồi lưu kết quả theo kiểu phù hợp. Nếu chỉ cần hiển thị, chỉ định dạng ở bước xuất dữ liệu.

## 6. `Math.round` tạo một số khác nhưng không chuyển sang số thập phân chính xác

~~~java
double x = 0.1 + 0.2;
double rounded = Math.round(x * 100.0) / 100.0;
System.out.println(rounded); // 0.3
~~~

Trong ví dụ, `rounded` không còn cùng mẫu bit với `x`. Điều đó khác về bản chất với `String.format`, vì phép tính đã thực sự tạo một số mới. Tuy nhiên kết quả vẫn thuộc **kiểu `double`**, nên không thể biểu diễn chính xác phần lớn phân số thập phân như 0.3.

Biểu thức `Math.round(x * 100.0) / 100.0` cũng **không phải công thức làm tròn thập phân an toàn cho mọi giá trị**. Nó có thể gặp vấn đề với số rất lớn, overflow khi nhân trước, NaN/vô cực, và cách xử lý điểm giữa đối với số âm. `Math.round` làm tròn theo quy tắc riêng của nó; đừng mặc định quy tắc đó phù hợp hóa đơn hay chính sách tài chính.

Ví dụ sự khác biệt giữa chính sách làm tròn và hiển thị:

~~~java
BigDecimal amount = new BigDecimal("1.005");
BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_UP);
// rounded = 1.01 (số thập phân với scale 2)
~~~

`setScale` trả **một `BigDecimal` mới** (đối tượng gốc không thay đổi), và `RoundingMode.HALF_UP` mô tả rõ cách xử lý chữ số bị bỏ. Cùng một dữ liệu có thể dùng chính sách khác, ví dụ `HALF_EVEN`, nếu nghiệp vụ yêu cầu. Đừng chọn một chính sách chỉ vì giao diện in hai chữ số.

## 7. Khi nào nên dùng `BigDecimal`?

Nếu miền dữ liệu đòi hỏi phép cộng, trừ, nhân và lượng tử hóa **thập phân theo quy tắc chính xác**, chẳng hạn số tiền, giá niêm yết hay đơn vị đo quy đổi có bước thập phân cố định, `BigDecimal` thường phù hợp hơn `double`.

~~~java
BigDecimal first = new BigDecimal("0.10");
BigDecimal second = new BigDecimal("0.20");
BigDecimal sum = first.add(second);
System.out.println(sum); // 0.30
~~~

Ở đây chuỗi `"0.10"` và `"0.20"` xác định số thập phân chính xác. Điều quan trọng là **xây dựng dữ liệu đúng ngay từ nguồn**:

- `new BigDecimal("0.1")`: biểu diễn giá trị thập phân 0.1 chính xác.
- `BigDecimal.valueOf(0.1)`: sử dụng dạng chuỗi chuẩn `Double.toString(0.1)`, tạo `BigDecimal` bằng 0.1. Hữu ích khi nhận giá trị `double` đã tồn tại nhưng **không biết ý định thập phân ban đầu**.
- `new BigDecimal(0.1)`: nhận chính xác giá trị nhị phân đã lưu của literal `double`, không phải chính xác con số thập phân 0.1 được viết trong mã.
- `BigDecimal.valueOf(0.1 + 0.2)`: trở thành `0.30000000000000004`, **không tự phục hồi phép cộng thập phân 0.10 + 0.20**.

Vì vậy chuyển sang `BigDecimal` **sau** khi sai số đã xuất hiện trong các phép tính `double` không bảo đảm phục hồi giá trị mà người dùng dự định nhập. Khi có thể, parse trực tiếp chuỗi thập phân gốc hoặc nhận `BigDecimal` từ lớp dữ liệu có hợp đồng chính xác, rồi tính toán bằng `BigDecimal` ngay từ đầu.

`BigDecimal` cũng cần quy tắc chia: `BigDecimal.ONE.divide(new BigDecimal("3"))` không thể biểu diễn thương thập phân hữu hạn và sẽ ném `ArithmeticException` nếu không chỉ định scale hoặc `MathContext` phù hợp. Kiểu thập phân không loại bỏ nhu cầu thiết kế chính sách làm tròn.

## 8. Sai số có thể ảnh hưởng cả so sánh và thuật toán

### So sánh số thực

~~~java
double x = 0.1 + 0.2;
if (x == 0.3) {
    // Nhánh này không chạy trong ví dụ
}
~~~

In hai giá trị với `%.2f` có thể cho `0.30` ở cả hai phía, dù `x == 0.3` là `false`. Để **so sánh gần bằng**, cần định nghĩa tolerance theo đơn vị và miền giá trị. Ví dụ đơn giản cho số hữu hạn với trị tuyệt đối không quá lớn:

~~~java
static boolean nearlyEqual(double a, double b, double eps) {
    if (!Double.isFinite(a) || !Double.isFinite(b)
            || !Double.isFinite(eps) || eps < 0.0) {
        return false;
    }
    return Math.abs(a - b) <= eps;
}
~~~

Đây là **phương thức minh họa**, cần đặt bên trong một class. Với các số có độ lớn rất lớn hoặc rất nhỏ, phép trừ có thể mất thông tin, overflow; tolerance tương đối hoặc kiểm tra theo ULP có thể thích hợp hơn tùy bài toán. Không dùng comparator theo epsilon trong `TreeSet`/`TreeMap` vì tính “gần bằng” có thể không bắc cầu, vi phạm hợp đồng sắp thứ tự.

### Mất chính xác do triệt tiêu

Định dạng cũng không thể cứu thông tin đã mất khi cộng/trừ số chênh lệch lớn:

~~~java
double large = 1e16;
double difference = (large + 1.0) - large;
System.out.println(difference); // 0.0, không phải 1.0
~~~

Ở độ lớn `1e16`, một thay đổi bằng `1.0` quá nhỏ để biểu diễn thành một `double` khác ở bước cộng. Bước trừ phía sau không có cách nào phục hồi phần thông tin đã bị làm tròn. In `0.000000` thay vì `0.0` chỉ thay đổi chữ viết của kết quả.

Đây là lý do phân biệt **hiển thị số đẹp** với **thuật toán số học ổn định**: sai số và thứ tự phép toán cần được đánh giá ngay trong thiết kế tính toán.

## 9. Chọn cách xử lý theo mục đích

| Mục đích | Lựa chọn phù hợp | Điều phải kiểm tra |
| --- | --- | --- |
| Chỉ in số dễ đọc cho người dùng | `String.format`, `printf`, `DecimalFormat` | Locale, số chữ số, quy tắc định dạng |
| Gửi giá trị dùng cho round-trip mà không mất thông tin do rút ngắn tùy ý | `Double.toString` hoặc định dạng có round-trip được bảo đảm | Cách parse tương ứng, NaN/Infinity nếu có |
| So sánh kết quả số thực gần nhau | Tolerance có hợp đồng rõ | Miền giá trị, finite, lỗi số học, tuyệt đối/tương đối |
| Lưu số đã định lượng theo bước thập phân | `BigDecimal` và `setScale(..., RoundingMode)` | Scale, rounding policy, nguồn dữ liệu |
| Tính toán tiền tệ thập phân | `BigDecimal` từ chuỗi gốc hoặc dữ liệu decimal chuẩn | Không đi qua phép tính `double` gây sai số trước đó |
| Đo đạc/khoa học chấp nhận sai số | `double`/`float` + kiểm soát sai số | Tính ổn định, phạm vi, overflow/underflow |

**Xuất dữ liệu cũng cần chú ý:** Nếu một hệ thống xuất số `double` dưới dạng chuỗi hai chữ số rồi hệ thống khác parse lại, đó là **thay đổi độ chính xác dữ liệu trao đổi**. Có thể là một quyết định sản phẩm có chủ đích, nhưng không còn là truyền nguyên vẹn cùng giá trị ban đầu. Đặc biệt, độ phân giải nhỏ hơn `0.01` có thể bị mất.

## 10. Lỗi thường gặp

1. **Cho rằng chuỗi `"0.30"` chứng minh `sum == 0.3`.** Hai giá trị có thể được in giống nhau dù khác nhau ở các bit thấp.
2. **Ghi đè log bằng một chuỗi làm tròn rồi mất khả năng chẩn đoán.** Khi cần debug sai số, lưu thêm dạng đủ chính xác (`Double.toString`, bit nếu cần) hoặc nguồn đầu vào.
3. **Format rồi parse để “chữa” sai số.** Việc này chủ động loại bỏ thông tin và vẫn tạo một `double` xấp xỉ.
4. **Đồng nhất `Math.round` với định dạng.** `Math.round` thực sự tính giá trị mới, nhưng vẫn giữ loại số nhị phân nếu kết quả cuối là `double` và không phù hợp mọi quy tắc thập phân.
5. **Chuyển `new BigDecimal(double)` rồi cho rằng nhận được decimal người dùng đã nhập.** Constructor này giữ **chính xác biểu diễn nhị phân** của đối số; cần nguồn chuỗi thập phân ban đầu nếu muốn decimal chính xác.
6. **Chỉ sửa số chữ số hiển thị để xử lý tích lũy sai số.** Sai số có thể đã ảnh hưởng các nhánh `if`, giới hạn ngưỡng, tổng, trung bình trước thời điểm format.
7. **Dùng số chữ số in ra làm bằng chứng chính xác nghiệp vụ.** Hai chữ số thập phân trên hóa đơn cần chính sách tính tiền, làm tròn, cộng dồn và thuế được định nghĩa nhất quán.
8. **Không quy định locale và đầu ra máy đọc.** Dấu phân cách, nhóm chữ số và giá trị đặc biệt có thể khiến việc parse không đúng nếu hai hệ thống dùng quy ước khác nhau.

## 11. Câu hỏi tự kiểm tra

1. Nếu `double x = 0.1 + 0.2;` và `String.format(Locale.ROOT, "%.2f", x)` cho `"0.30"`, `x == 0.3` có trở thành `true` không?
2. `Double.parseDouble("0.30")` có nhất thiết lưu đúng giá trị nhị phân đang có trong `0.1 + 0.2` không?
3. Sau `double y = Math.round(x * 100) / 100.0;`, `y` đã trở thành số thập phân chính xác chưa?
4. `new BigDecimal(0.1)` và `new BigDecimal("0.1")` có biểu diễn cùng số thập phân chính xác không?
5. Khi nào phải dùng `BigDecimal` từ nguồn dữ liệu và khi nào `double` với kiểm soát sai số vẫn hợp lý?

**Đáp án:** (1) Không; formatting không thay đổi `x` nên so sánh vẫn `false`. (2) Không; parse chuỗi ngắn tạo mẫu bit cho literal `0.3`, khác bit của `0.1 + 0.2`. (3) Chưa: kết quả là `double` mới, có thể gần một số thập phân tròn nhưng vẫn là biểu diễn nhị phân xấp xỉ. (4) Không; constructor nhận `double` phản ánh chính xác giá trị nhị phân gần 0.1, constructor nhận chuỗi biểu diễn số thập phân 0.1. (5) Dùng `BigDecimal` khi cần số học thập phân và chính sách scale/rounding xác định; `double` thích hợp nhiều phép đo, tính khoa học và thuật toán biết cách kiểm soát sai số.

## Tài liệu tham khảo

- [Java Language Specification `4.2.3 — Floating-Point Types](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2.3).
- [Java SE 21 API — Double](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html): `toString`, `parseDouble` và giá trị dấu phẩy động.
- [Java SE 21 API — Formatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Formatter.html): các dạng format dấu phẩy động, độ chính xác và locale.
- [Java SE 21 API — BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html): constructor `String`/`double`, `valueOf`, `setScale`.
- [Java SE 21 API — RoundingMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html): quy tắc làm tròn.
