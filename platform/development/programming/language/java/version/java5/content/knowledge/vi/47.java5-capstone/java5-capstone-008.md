# Tính toán số thập phân với chính sách làm tròn rõ ràng

## 1. BigDecimal không tự quyết định chính sách của bài toán

Khi cần tính toán số thập phân theo quy tắc rõ ràng, `BigDecimal` cung cấp biểu diễn thập phân và phép toán với mức kiểm soát cao. Nhưng chọn đúng kiểu dữ liệu chưa đủ: vẫn phải quyết định đầu vào đến từ đâu, giữ bao nhiêu chữ số, làm tròn bằng cách nào và tại bước nào.

Một chính sách cần trả lời ít nhất:

| Câu hỏi | Ví dụ quyết định cần ghi rõ |
| --- | --- |
| Nguồn đầu vào | Chuỗi số thập phân từ dữ liệu đã kiểm tra |
| Đơn vị | Giá trị đang biểu diễn đơn vị nào, tỷ lệ hay số lượng? |
| Kết quả cần giữ | Hai chữ số sau dấu thập phân hay một số chữ số có nghĩa? |
| Quy tắc điểm giữa | `HALF_UP`, `HALF_EVEN` hoặc quy tắc khác do bài toán yêu cầu |
| Thời điểm làm tròn | Mỗi thành phần, sau phép chia hay tại kết quả cuối? |
| Giá trị không thể biểu diễn đúng | Từ chối hay cho phép xấp xỉ có kiểm soát? |

Bài thực hành sử dụng các giá trị số minh họa. Không có quy tắc “mọi số nghiệp vụ đều phải hai chữ số” hoặc “một chế độ làm tròn phù hợp mọi trường hợp”. API không thay thế yêu cầu của mô hình.

## 2. Giữ ý nghĩa thập phân từ đầu vào

Với dữ liệu thập phân được biểu diễn bằng chuỗi, có thể tạo trực tiếp:

```java
BigDecimal first = new BigDecimal("0.1");
BigDecimal second = new BigDecimal("0.2");
BigDecimal sum = first.add(second); // Giá trị thập phân 0.3
```

Đoạn này cần import `java.math.BigDecimal`. Nó chưa phải chương trình độc lập.

Tránh đi vòng qua `double` nếu mục tiêu là giữ đúng số thập phân của đầu vào. `new BigDecimal(0.1)` biểu diễn chính xác giá trị nhị phân của `double` được truyền vào, nên không có nghĩa giống `new BigDecimal("0.1")`. [API BigDecimal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html).

`BigDecimal.valueOf(double)` dùng biểu diễn chuỗi chuẩn của `double`, thường phù hợp hơn constructor nhận `double` khi bắt buộc nhận đầu vào kiểu ấy. Tuy nhiên, nó không phục hồi được thông tin đã mất hoặc sai lệch đã sinh ở các phép tính nhị phân trước đó. Nếu đầu vào đã là kết quả của `0.1 + 0.2` bằng `double`, đổi kiểu về sau không tự tạo lại phép cộng thập phân gốc.

Định nghĩa hợp đồng chuỗi đầu vào rõ ràng: dấu phân cách thập phân, có cho phép dạng số mũ không, độ dài và miền giá trị. Đừng tự thay mọi dấu phẩy bằng dấu chấm nếu chưa biết dấu phẩy là dấu thập phân hay phân cách hàng nghìn.

## 3. Scale khác precision

`BigDecimal` có thể được hình dung là một số nguyên không dấu thập phân kết hợp một `scale`:

```text
giá trị = unscaledValue × 10^(-scale)
```

Với `123.450`, `scale` là 3 và `precision` là 6. Hai khái niệm khác nhau:

| Khái niệm | Ý nghĩa trong ví dụ thông thường |
| --- | --- |
| `scale` | Số vị trí sau dấu thập phân khi scale không âm |
| `precision` | Số chữ số trong phần số nguyên không chia tỷ lệ của biểu diễn |

Scale còn có thể âm, chẳng hạn biểu diễn `1E+3`; vì vậy, không coi `scale()` luôn là một số không âm. [API BigDecimal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html).

Hai công cụ phổ biến:

```java
value.setScale(2, RoundingMode.HALF_UP);
value.round(new MathContext(3, RoundingMode.HALF_UP));
```

Đây là hai thao tác khác nhau. Với `value = new BigDecimal("123.456")`, thao tác đầu cho `123.46`; thao tác sau giữ ba chữ số có nghĩa, cho `123`. `MathContext(3, ...)` không có nghĩa giữ ba chữ số sau dấu thập phân. [API MathContext](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/MathContext.html).

`BigDecimal` bất biến: `setScale`, `add`, `multiply` và các phép toán trả kết quả mới. Nếu gọi `value.setScale(...)` rồi bỏ kết quả, biến `value` vẫn giữ đối tượng cũ.

## 4. Chọn RoundingMode bằng hành vi, đặc biệt với số âm

Bảng sau dùng hai đầu vào nằm đúng điểm giữa và yêu cầu scale 2:

| Chế độ | Ý nghĩa định hướng | `1.005` | `-1.005` |
| --- | --- | --- | --- |
| `UP` | Ra xa 0 khi cần bỏ phần khác 0 | `1.01` | `-1.01` |
| `DOWN` | Về phía 0 | `1.00` | `-1.00` |
| `CEILING` | Về phía dương vô cùng | `1.01` | `-1.00` |
| `FLOOR` | Về phía âm vô cùng | `1.00` | `-1.01` |
| `HALF_UP` | Gần nhất; điểm giữa chọn phía xa 0 | `1.01` | `-1.01` |
| `HALF_DOWN` | Gần nhất; điểm giữa chọn phía gần 0 | `1.00` | `-1.00` |
| `HALF_EVEN` | Gần nhất; điểm giữa chọn chữ số cuối giữ lại chẵn | `1.00` | `-1.00` |
| `UNNECESSARY` | Yêu cầu không cần làm tròn | Ném lỗi | Ném lỗi |

Điểm dễ nhầm: “làm tròn xuống” có thể được hiểu là `DOWN` hoặc `FLOOR`, nhưng chúng khác nhau với số âm. Hãy đặt tên chế độ cụ thể trong chính sách. [API RoundingMode](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/RoundingMode.html).

`HALF_EVEN` không phải luôn làm tròn xuống: `1.015` về hai chữ số là `1.02`, vì chữ số cuối được giữ là 2 chẵn. Việc chọn một chế độ dựa trên yêu cầu của bài toán, không dựa vào tên nghe quen thuộc.

Dùng enum `RoundingMode` trong mã hiện đại để quy tắc có ý nghĩa rõ ràng ở nơi gọi.

## 5. Phép chia cần chính sách biểu diễn kết quả

Các đầu vào thập phân hữu hạn vẫn có thể tạo thương thập phân vô hạn tuần hoàn. Ví dụ `1 / 3` không có biểu diễn thập phân hữu hạn chính xác.

```java
BigDecimal.ONE.divide(new BigDecimal("3"));
```

Phép chia chính xác này ném `ArithmeticException`. Nếu bài toán cho phép thương xấp xỉ với bốn chữ số sau dấu thập phân:

```java
BigDecimal third = BigDecimal.ONE.divide(
        new BigDecimal("3"), 4, RoundingMode.HALF_EVEN);
// third biểu diễn 0.3333
```

Chọn rõ overload của `divide`. Overload chỉ nhận chế độ làm tròn có cách xác định scale khác overload nhận cả scale; đừng giả định mọi lời gọi đều cho cùng số chữ số. [API BigDecimal.divide](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html).

`MathContext.UNLIMITED` không biến `1/3` thành một số thập phân hữu hạn chính xác. Nó yêu cầu tính chính xác trong bối cảnh ấy, nên phép chia không kết thúc vẫn có thể báo lỗi. Tăng precision hữu hạn là chọn một mức xấp xỉ, không phải loại bỏ bản chất vô hạn của thương.

Chia cho 0 cũng là lỗi cần xử lý theo hợp đồng đầu vào. Không bắt mọi `ArithmeticException` rồi trả `0`, vì như vậy sẽ biến một phép tính không hợp lệ thành một kết quả nghiệp vụ có vẻ hợp lệ.

## 6. Thời điểm làm tròn có thể thay đổi tổng

Giả sử có ba thành phần, mỗi thành phần bằng `0.335`, và chính sách làm tròn minh họa là scale 2 với `HALF_UP`.

```text
Làm tròn từng thành phần:
0.34 + 0.34 + 0.34 = 1.02

Cộng chính xác rồi làm tròn tổng:
0.335 + 0.335 + 0.335 = 1.005 -> 1.01
```

Hai kết quả khác nhau dù đều dùng `BigDecimal` và cùng `RoundingMode`. Không thể kết luận một bên là lỗi Java. Chúng thực hiện hai chính sách khác nhau về thời điểm làm tròn.

Nếu hợp đồng yêu cầu từng thành phần đã làm tròn là giá trị chính thức, tổng phải nhất quán với các thành phần ấy. Nếu hợp đồng yêu cầu cộng giá trị chính xác rồi làm tròn tổng, không tự thay bằng tổng các thành phần đã làm tròn để hiển thị.

Một lỗi khác là làm tròn hai lần:

```text
1.2449 -> scale 3, HALF_UP -> 1.245
1.245  -> scale 2, HALF_UP -> 1.25

Làm tròn trực tiếp 1.2449 về scale 2, HALF_UP -> 1.24
```

Giữ dữ liệu trung gian phù hợp và chỉ làm tròn tại các điểm chính sách quy định. Với phép chia cần xấp xỉ, phải chọn precision/scale trung gian có căn cứ; không hứa rằng thêm tùy ý vài chữ số luôn bảo đảm đúng kết quả cuối của mọi thuật toán.

## 7. Chương trình Java 17+ với chính sách làm tròn tường minh

Chương trình dưới đây đóng gói chính sách đầu ra thành một record. Chính sách minh họa chỉ chấp nhận scale không âm, dù API `BigDecimal` nói chung hỗ trợ cả scale âm. Nó không ấn định thời điểm làm tròn cho mọi phép toán; `main` chủ động cho thấy hai cách đặt điểm làm tròn.

Lưu thành `DecimalPolicyDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Objects;

public class DecimalPolicyDemo {
    record RoundingPolicy(int scale, RoundingMode mode) {
        RoundingPolicy {
            if (scale < 0) throw new IllegalArgumentException("Negative output scale");
            Objects.requireNonNull(mode, "mode");
        }
        BigDecimal apply(BigDecimal value) {
            return Objects.requireNonNull(value, "value").setScale(scale, mode);
        }
    }

    public static void main(String[] args) {
        RoundingPolicy output = new RoundingPolicy(2, RoundingMode.HALF_UP);
        BigDecimal tie = new BigDecimal("1.005");
        System.out.println("halfUp=" + output.apply(tie).toPlainString());
        System.out.println("halfEven="
                + tie.setScale(2, RoundingMode.HALF_EVEN).toPlainString());

        List<BigDecimal> lines = List.of(
                new BigDecimal("0.335"), new BigDecimal("0.335"),
                new BigDecimal("0.335"));
        BigDecimal rawTotal = lines.stream().reduce(BigDecimal.ZERO, BigDecimal::add);
        BigDecimal roundedLines = lines.stream().map(output::apply)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        System.out.println("roundTotal=" + output.apply(rawTotal).toPlainString());
        System.out.println("sumRoundedLines=" + roundedLines.toPlainString());

        BigDecimal negative = new BigDecimal("-1.005");
        System.out.println("negativeDown="
                + negative.setScale(2, RoundingMode.DOWN).toPlainString());
        System.out.println("negativeFloor="
                + negative.setScale(2, RoundingMode.FLOOR).toPlainString());

        try {
            BigDecimal.ONE.divide(new BigDecimal("3"));
        } catch (ArithmeticException expected) {
            System.out.println("exactThird=rejected");
        }
        System.out.println("third=" + BigDecimal.ONE
                .divide(new BigDecimal("3"), 4, RoundingMode.HALF_EVEN).toPlainString());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 DecimalPolicyDemo.java
java DecimalPolicyDemo
```

Stdout:

```text
halfUp=1.01
halfEven=1.00
roundTotal=1.01
sumRoundedLines=1.02
negativeDown=-1.00
negativeFloor=-1.01
exactThird=rejected
third=0.3333
```

`RoundingPolicy.apply()` trả một kết quả mới; nó không sửa đầu vào. `roundTotal` và `sumRoundedLines` là hai kết quả để so sánh, không phải hai giá trị cần ghi đồng thời làm cùng một tổng chính thức. Chọn đường tính theo yêu cầu rồi dùng nhất quán.

Không có giá trị `double` trong luồng dữ liệu của ví dụ. Các đầu vào thập phân được tạo trực tiếp từ chuỗi.

## 8. UNNECESSARY dùng để kiểm tra điều kiện chính xác

Khi đầu vào không được phép mất phần thập phân vượt quá scale đầu ra, có thể kiểm tra:

```java
BigDecimal accepted = new BigDecimal("1.2300")
        .setScale(2, RoundingMode.UNNECESSARY);
```

Kết quả là `1.23` vì bỏ các số 0 dư không làm mất giá trị. Còn `1.234` không thể đưa về scale 2 chính xác và sẽ ném `ArithmeticException`.

Điều này khác kiểm tra chuỗi đầu vào phải có đúng hai chữ số sau dấu phân cách. `UNNECESSARY` kiểm tra giá trị có biểu diễn chính xác ở scale yêu cầu hay không, không kiểm tra hình thức văn bản ban đầu. Nếu bài toán quy định định dạng đầu vào, cần một bước kiểm tra định dạng riêng.

Cũng phân biệt làm tròn với thay đổi đơn vị. `setScale` thường giữ nguyên hoặc xấp xỉ cùng giá trị; `movePointLeft`/`movePointRight` thay vị trí dấu thập phân và do đó thay giá trị. Không dùng thao tác đổi scale để thay cho quy đổi giữa các đơn vị.

## 9. So sánh giá trị và so sánh biểu diễn

Hai đối tượng có thể cùng giá trị số nhưng khác scale:

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");
boolean sameRepresentation = a.equals(b); // false
boolean sameNumericValue = a.compareTo(b) == 0; // true
```

`equals()` của `BigDecimal` xét cả giá trị và scale; `compareTo()` so sánh giá trị số. Chọn phép so sánh theo ý nghĩa cần kiểm tra. [API BigDecimal về equals và thứ tự tự nhiên](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html).

Nếu `BigDecimal` làm khóa của map hoặc phần tử trong set, khác biệt này ảnh hưởng cách nhận diện trùng. Đừng đổi tùy tiện giữa một cấu trúc dùng `equals` và một cấu trúc dựa trên so sánh tự nhiên mà không kiểm tra ý nghĩa dữ liệu.

`stripTrailingZeros()` có thể hữu ích khi cần dạng chuẩn hóa số, nhưng có thể thay scale và tạo biểu diễn số mũ. Không gọi nó tự động lên kết quả mà hợp đồng yêu cầu giữ scale 2 để lưu/hiển thị. Chuẩn hóa giá trị và giữ số chữ số theo hợp đồng là hai mục tiêu cần quyết định rõ.

## 10. Phân bổ phần dư cần quy tắc riêng

Nếu chia `10.00` thành ba phần và làm tròn mỗi phần về scale 2, ba phần `3.33` có tổng `9.99`. Chênh lệch `0.01` không được giải quyết bằng việc tăng độ chính xác biểu diễn đầu vào; nó đến từ việc các phần cuối bị ràng buộc số chữ số.

Một bài toán yêu cầu bảo toàn tổng phải xác định cách phân bổ phần dư: ai nhận thêm phần đơn vị nhỏ nhất, thứ tự ưu tiên có ổn định không và áp dụng cho số âm thế nào. Chẳng hạn, một chính sách có thể chọn hai phần `3.33`, một phần `3.34` theo thứ tự định danh đã xác định. Đây là một chính sách phân bổ minh họa, không phải quy tắc mặc định của `BigDecimal`.

Ghi nhận cả tổng gốc và các phần cuối cần thiết cho kiểm chứng. Không cố làm mọi phần bằng nhau tuyệt đối khi miền số biểu diễn không cho phép, rồi âm thầm bỏ chênh lệch.

## 11. Lưu trữ và hiển thị phải giữ hợp đồng tính toán

`toPlainString()` hữu ích khi muốn chuỗi không dùng dạng số mũ. Nó không tự áp một chế độ làm tròn mới; hãy tạo giá trị đúng chính sách trước rồi mới biểu diễn.

Đừng chuyển kết quả qua `doubleValue()` chỉ để xuất dữ liệu nếu hợp đồng yêu cầu giữ số thập phân chính xác. Một hệ thống nhận/gửi JSON, cơ sở dữ liệu hoặc tệp phải thống nhất kiểu, scale/precision và cách biểu diễn; nếu một lớp khác tự làm tròn lần nữa, kết quả đầu cuối có thể khác phép tính đã kiểm chứng.

Nếu cần hiển thị dấu phân cách theo ngôn ngữ, giữ tách biệt bước định dạng cho người dùng với dữ liệu dùng để tính hoặc trao đổi giữa hệ thống. Không lấy chuỗi đã định dạng có dấu phân cách hàng nghìn đưa ngược vào constructor thập phân như thể nó là dữ liệu chuẩn.

`BigDecimal` không tự mang đơn vị hoặc loại đại lượng. Hai số có cùng kiểu Java vẫn có thể không được cộng nếu khác đơn vị/ngữ nghĩa. Mô hình miền cần bảo đảm điều ấy khi bài toán yêu cầu.

## 12. Ca tự kiểm tra cho một chính sách rõ ràng

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Giá trị nằm đúng điểm giữa dương và âm | Đúng `RoundingMode` đã chọn |
| Giá trị đã đủ scale, ví dụ `1.20` | Không thay đổi giá trị ngoài yêu cầu |
| Phép chia `1/3` | Chính sách cho phép xấp xỉ hoặc chủ động từ chối |
| Tổng nhiều thành phần lẻ | Đúng điểm làm tròn, tổng khớp hợp đồng |
| Làm tròn lặp ở nhiều tầng | Không tạo sai khác ngoài chính sách |
| `1.2300` và `1.234` với `UNNECESSARY` scale 2 | Trường hợp chính xác được nhận, trường hợp mất giá trị bị từ chối |
| `2.0` so với `2.00` | Phân biệt so sánh số với so sánh biểu diễn |
| Số lớn hoặc chuỗi rất dài | Có giới hạn đầu vào/tài nguyên phù hợp trước khi tính |

Bài tập: đổi chính sách của chương trình sang `HALF_EVEN`. Dự đoán trước kết quả của `roundTotal` cho tổng `1.005`, sau đó chạy và đối chiếu. Tiếp theo, giải thích vì sao tổng các thành phần `0.335` đã làm tròn vẫn có thể khác kết quả làm tròn tổng.

Một chính sách có thể kiểm tra được cần gồm kiểu/nguồn đầu vào, đơn vị, precision hoặc scale, chế độ, điểm làm tròn và cách xử lý sai lệch. `BigDecimal` giúp thực hiện các quyết định ấy; nó không chọn quyết định thay cho ứng dụng.
