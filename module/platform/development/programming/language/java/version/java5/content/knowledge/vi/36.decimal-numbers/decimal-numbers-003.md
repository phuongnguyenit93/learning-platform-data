# Các chế độ làm tròn bằng RoundingMode

## 1. Làm tròn là chọn kết quả theo một quy tắc rõ ràng

Khi cần biểu diễn `2.675` với hai chữ số sau dấu thập phân, hai giá trị kề nhau có thể chọn là `2.67` và `2.68`. Phải quyết định giữ giá trị nào. `java.math.RoundingMode` mô tả quyết định đó; bản thân nó không phải phép tính và không xác định cần giữ bao nhiêu chữ số.

Để làm tròn đúng, phải trả lời hai câu hỏi độc lập:

1. **Giữ đến đâu?** Ví dụ hai chữ số sau dấu thập phân, hoặc ba chữ số có nghĩa.
2. **Chọn theo quy tắc nào?** Ví dụ tiến về 0, tiến về âm vô cùng, hoặc chọn giá trị gần nhất.

Trong Java, `BigDecimal` thực hiện phép tính và trả về kết quả; `RoundingMode` cung cấp chính sách. Với `setScale(2, mode)`, vị trí cần giữ do `2` quyết định. Với `new MathContext(3, mode)`, giới hạn là ba chữ số có nghĩa.

Ví dụ ngắn, dùng trong một phương thức sau khi import `BigDecimal` và `RoundingMode`:

```java
BigDecimal input = new BigDecimal("2.675");
BigDecimal result = input.setScale(2, RoundingMode.HALF_UP);
System.out.println(result.toPlainString()); // 2.68
```

Chuỗi `"2.675"` giúp ví dụ xuất phát từ đúng số thập phân cần xét. Tất cả ví dụ trong bài dùng API đang được sử dụng trong Java hiện đại và có thể chạy với JDK 17 trở lên.

## 2. Tám chế độ và ý nghĩa với số âm

Có thể chia tám giá trị enum thành ba nhóm:

| Nhóm | Chế độ | Quy tắc lựa chọn |
|---|---|---|
| Theo hướng | `UP` | Ra xa 0 khi cần loại bỏ phần khác 0 |
| Theo hướng | `DOWN` | Về phía 0 |
| Theo hướng | `CEILING` | Về phía dương vô cùng |
| Theo hướng | `FLOOR` | Về phía âm vô cùng |
| Gần nhất | `HALF_UP` | Gần nhất; đúng giữa thì ra xa 0 |
| Gần nhất | `HALF_DOWN` | Gần nhất; đúng giữa thì về phía 0 |
| Gần nhất | `HALF_EVEN` | Gần nhất; đúng giữa thì chọn chữ số cuối được giữ là chẵn |
| Yêu cầu chính xác | `UNNECESSARY` | Báo lỗi nếu phép toán cần làm tròn |

Đây là các chính sách được định nghĩa trong [Java API: RoundingMode](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/RoundingMode.html).

### 2.1. UP và DOWN nói về khoảng cách đến 0

`UP` không đồng nghĩa với “kết quả lớn hơn”, còn `DOWN` không đồng nghĩa với “kết quả nhỏ hơn”.

Khi làm tròn về số nguyên:

- `2.1` với `UP` thành `3`; `-2.1` với `UP` thành `-3`.
- `2.9` với `DOWN` thành `2`; `-2.9` với `DOWN` thành `-2`.

Với số âm, ra xa 0 khiến giá trị nhỏ đi trên trục số. Vì vậy, đọc `UP` theo nghĩa “tăng giá trị” sẽ dẫn đến lựa chọn sai.

`UP` phản ứng với **bất kỳ phần khác 0 nào bị loại bỏ**, không chỉ khi gặp chữ số 5. Chẳng hạn:

```java
new BigDecimal("4.0001").setScale(2, RoundingMode.UP);   // 4.01
new BigDecimal("-4.0001").setScale(2, RoundingMode.UP);  // -4.01
new BigDecimal("4.0000").setScale(2, RoundingMode.UP);   // 4.00
```

Các dòng trên là biểu thức minh họa, không phải một chương trình độc lập.

### 2.2. CEILING và FLOOR nói về thứ tự trên trục số

Với vị trí làm tròn đã chọn:

- `CEILING` chọn giá trị biểu diễn được nhỏ nhất nhưng không nhỏ hơn số ban đầu.
- `FLOOR` chọn giá trị biểu diễn được lớn nhất nhưng không lớn hơn số ban đầu.

Khi giữ hai chữ số sau dấu thập phân:

| Giá trị ban đầu | `UP` | `DOWN` | `CEILING` | `FLOOR` |
|---|---:|---:|---:|---:|
| `1.231` | `1.24` | `1.23` | `1.24` | `1.23` |
| `-1.231` | `-1.24` | `-1.23` | `-1.23` | `-1.24` |
| `1.230` | `1.23` | `1.23` | `1.23` | `1.23` |
| `-1.230` | `-1.23` | `-1.23` | `-1.23` | `-1.23` |

Hàng có phần bị loại bỏ chỉ gồm số 0 không đòi hỏi thay đổi giá trị số học. Không được tăng hoặc giảm thêm một đơn vị chỉ vì tên chế độ là `UP` hay `FLOOR`.

## 3. Ba chế độ HALF: chỉ khác nhau tại điểm chính giữa

Trước hết, cả ba chế độ `HALF_*` đều chọn giá trị gần số ban đầu nhất. Chỉ khi hai giá trị ứng viên có khoảng cách bằng nhau mới cần quy tắc phân xử.

Giả sử giữ hai chữ số sau dấu thập phân:

| Giá trị | `HALF_UP` | `HALF_DOWN` | `HALF_EVEN` | Giải thích |
|---|---:|---:|---:|---|
| `2.344` | `2.34` | `2.34` | `2.34` | Gần `2.34` hơn |
| `2.345` | `2.35` | `2.34` | `2.34` | Đúng giữa; chữ số 4 là chẵn |
| `2.3451` | `2.35` | `2.35` | `2.35` | Đã vượt điểm giữa |
| `2.355` | `2.36` | `2.35` | `2.36` | Đúng giữa; chữ số 6 là chẵn |
| `-2.345` | `-2.35` | `-2.34` | `-2.34` | Đúng giữa ở phía âm |

### 3.1. Phải xét toàn bộ phần bị loại bỏ

Không chỉ nhìn thấy chữ số đầu bị bỏ là 5 rồi kết luận “đúng giữa”.

Với `2.3451`, khoảng cách đến `2.35` là `0.0049`, còn đến `2.34` là `0.0051`. Vì thế `HALF_DOWN` vẫn cho `2.35`. Phần `51` bị loại bỏ đã lớn hơn nửa một đơn vị ở vị trí giữ cuối cùng.

Ngược lại, `2.3450` và `2.345` có cùng giá trị số học: cả hai đều nằm đúng giữa `2.34` và `2.35`.

### 3.2. HALF_EVEN xét chữ số cuối được giữ

Trong `2.345` làm tròn về hai chữ số sau dấu thập phân, hai kết quả ứng viên là `2.34` và `2.35`. Chọn `2.34` vì chữ số cuối 4 là chẵn.

Trong `2.355`, hai ứng viên là `2.35` và `2.36`. Chọn `2.36` vì chữ số cuối 6 là chẵn.

Không xét tổng chữ số và cũng không xét phần nguyên có chẵn hay không. Kết quả có thể là số thập phân như `2.34`; “chẵn” ở đây nói về **chữ số cuối cùng được giữ**, không yêu cầu toàn bộ kết quả là số nguyên chẵn.

### 3.3. Số âm cũng tuân theo cùng quy tắc

Khi làm tròn `-2.5` về số nguyên:

- `HALF_UP` cho `-3`: phân xử bằng hướng ra xa 0.
- `HALF_DOWN` cho `-2`: phân xử bằng hướng về 0.
- `HALF_EVEN` cho `-2`: chữ số cuối được giữ là 2.

Trong khi đó `-3.5` với `HALF_EVEN` thành `-4`. Không có quy tắc chung “số âm luôn giảm” hoặc “HALF_EVEN luôn cắt phần lẻ”.

## 4. UNNECESSARY: xác nhận không được mất độ chính xác

`UNNECESSARY` không có nghĩa là “bỏ qua việc làm tròn và chấp nhận mất dữ liệu”. Nó đặt điều kiện: kết quả phải biểu diễn chính xác được ở giới hạn đã yêu cầu.

Các biểu thức sau minh họa điều kiện đó:

```java
new BigDecimal("7.1200").setScale(2, RoundingMode.UNNECESSARY); // 7.12
new BigDecimal("7.12").setScale(4, RoundingMode.UNNECESSARY);   // 7.1200
new BigDecimal("7.1201").setScale(2, RoundingMode.UNNECESSARY); // ArithmeticException
```

Ở dòng đầu, bỏ các số 0 cuối không làm thay đổi giá trị. Ở dòng thứ hai, thêm số 0 chỉ thay đổi cách biểu diễn. Dòng cuối phải bỏ phần khác 0, nên điều kiện chính xác bị vi phạm.

Chế độ này hữu ích khi đầu vào chỉ được phép có giá trị biểu diễn chính xác với một số vị trí thập phân đã định. Nó kiểm tra **giá trị có biểu diễn được hay không**, chứ không kiểm tra số lượng ký tự người dùng đã nhập. Ví dụ `"7.1200"` có bốn chữ số sau dấu chấm nhưng vẫn chuyển chính xác về scale 2 được.

Không bắt ngoại lệ rồi tự đổi sang một chế độ khác nếu yêu cầu nghiệp vụ chưa cho phép. Hành động đó biến điều kiện “không được mất dữ liệu” thành “cho phép thay đổi giá trị”.

## 5. Dùng với BigDecimal: scale, precision và phép chia

### 5.1. setScale: vị trí sau dấu thập phân

`setScale(2, mode)` đặt scale bằng 2. Trong trường hợp này, kết quả có hai chữ số sau dấu thập phân. Nếu cần giảm scale và có phần khác 0 bị loại bỏ, `mode` quyết định kết quả.

`BigDecimal` bất biến: phải giữ lại đối tượng được trả về.

```java
BigDecimal value = new BigDecimal("8.765");
value.setScale(2, RoundingMode.HALF_UP); // Giá trị trả về bị bỏ đi.
System.out.println(value.toPlainString()); // 8.765

BigDecimal rounded = value.setScale(2, RoundingMode.HALF_UP);
System.out.println(rounded.toPlainString()); // 8.77
```

Đây là đoạn mã dùng bên trong một phương thức. Không có đối tượng `value` nào bị sửa tại chỗ.

Scale âm cũng hợp lệ. Chẳng hạn, `new BigDecimal("145").setScale(-1, RoundingMode.HALF_UP)` có giá trị `150`: vị trí làm tròn lúc này là hàng chục. Dùng `toPlainString()` để xem dạng `150` thay vì có thể thấy dạng số mũ khi in bằng `toString()`.

### 5.2. MathContext: tổng số chữ số có nghĩa

`new MathContext(3, mode)` yêu cầu tối đa ba chữ số có nghĩa cho phép toán có nhận context đó. Nó không yêu cầu ba chữ số sau dấu thập phân.

Ví dụ:

```java
BigDecimal value = new BigDecimal("1234.567");

BigDecimal byScale = value.setScale(2, RoundingMode.HALF_UP);
BigDecimal byPrecision = value.round(new MathContext(3, RoundingMode.HALF_UP));

System.out.println(byScale.toPlainString());     // 1234.57
System.out.println(byPrecision.toPlainString()); // 1230
```

Cần import thêm `java.math.MathContext` cho đoạn mã này. Chữ số 0 cuối trong chuỗi `1230` không có nghĩa rằng context đã yêu cầu bốn chữ số có nghĩa; kết quả ở đây được biểu diễn bằng một `BigDecimal` có scale âm.

Context chỉ có tác dụng trên lần gọi nhận nó, không trở thành cấu hình toàn cục cho tất cả `BigDecimal`. Precision bằng 0 biểu thị tính toán chính xác không giới hạn precision; không dùng nó như cách buộc phép chia tuần hoàn kết thúc. Các quan hệ giữa scale, precision, tính bất biến và làm tròn được mô tả trong [Java API: BigDecimal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html).

### 5.3. Phép chia cần chỉ rõ hợp đồng kết quả

Để nhận bốn chữ số sau dấu thập phân:

```java
BigDecimal result = BigDecimal.ONE.divide(
        new BigDecimal("3"), 4, RoundingMode.HALF_UP);
System.out.println(result.toPlainString()); // 0.3333
```

Đừng nhầm lời gọi trên với:

```java
BigDecimal result = BigDecimal.ONE.divide(
        new BigDecimal("3"), RoundingMode.HALF_UP);
System.out.println(result.toPlainString()); // 0
```

Overload chỉ nhận số chia và `RoundingMode` dùng scale của **số bị chia** làm scale kết quả. `BigDecimal.ONE` có scale 0, nên kết quả bị làm tròn về số nguyên. Truyền một `RoundingMode` không tự động giữ lại đủ chữ số mà người viết mong muốn.

Nếu cần giới hạn số chữ số có nghĩa, dùng overload nhận `MathContext`. Nếu cần số chữ số sau dấu thập phân cố định, thường dùng overload nhận cả `scale` và `RoundingMode`.

Không truyền chế độ làm tròn cho phép chia chính xác như `BigDecimal.ONE.divide(new BigDecimal("3"))` sẽ gây `ArithmeticException`, vì kết quả có khai triển thập phân vô hạn tuần hoàn.

## 6. Chương trình chạy đầy đủ để đối chiếu

Lưu nội dung sau vào `RoundingModeDemo.java`. Chương trình gồm ba phần: đối chiếu tám chế độ, kiểm tra ba tình huống đúng giữa/vượt điểm giữa, và phân biệt các API.

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class RoundingModeDemo {
    private static String rounded(String text, int scale, RoundingMode mode) {
        try {
            return new BigDecimal(text).setScale(scale, mode).toPlainString();
        } catch (ArithmeticException exception) {
            return "ArithmeticException";
        }
    }

    public static void main(String[] args) {
        System.out.println("mode | 2.5 | -2.5");
        for (RoundingMode mode : RoundingMode.values()) {
            System.out.println(mode + " | "
                    + rounded("2.5", 0, mode) + " | "
                    + rounded("-2.5", 0, mode));
        }

        System.out.println("HALF ties: 2.345 | 2.355 | 2.3451");
        for (RoundingMode mode : new RoundingMode[] {
                RoundingMode.HALF_UP,
                RoundingMode.HALF_DOWN,
                RoundingMode.HALF_EVEN
        }) {
            System.out.println(mode + " | "
                    + rounded("2.345", 2, mode) + " | "
                    + rounded("2.355", 2, mode) + " | "
                    + rounded("2.3451", 2, mode));
        }

        BigDecimal input = new BigDecimal("1234.567");
        System.out.println("scale(2) = "
                + input.setScale(2, RoundingMode.HALF_UP).toPlainString());
        System.out.println("precision(3) = "
                + input.round(new MathContext(3, RoundingMode.HALF_UP))
                        .toPlainString());
        System.out.println("1/3, scale 4 = "
                + BigDecimal.ONE.divide(new BigDecimal("3"), 4,
                        RoundingMode.HALF_UP).toPlainString());
        System.out.println("1/3, dividend scale = "
                + BigDecimal.ONE.divide(new BigDecimal("3"),
                        RoundingMode.HALF_UP).toPlainString());
        System.out.println("exact scale reduction = "
                + rounded("7.1200", 2, RoundingMode.UNNECESSARY));
        System.out.println("inexact scale reduction = "
                + rounded("7.1201", 2, RoundingMode.UNNECESSARY));

        BigDecimal original = new BigDecimal("1.2451");
        BigDecimal direct = original.setScale(2, RoundingMode.HALF_EVEN);
        BigDecimal twice = original.setScale(3, RoundingMode.HALF_EVEN)
                .setScale(2, RoundingMode.HALF_EVEN);
        System.out.println("direct = " + direct.toPlainString());
        System.out.println("twice = " + twice.toPlainString());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 RoundingModeDemo.java
java RoundingModeDemo
```

Stdout:

```text
mode | 2.5 | -2.5
UP | 3 | -3
DOWN | 2 | -2
CEILING | 3 | -2
FLOOR | 2 | -3
HALF_UP | 3 | -3
HALF_DOWN | 2 | -2
HALF_EVEN | 2 | -2
UNNECESSARY | ArithmeticException | ArithmeticException
HALF ties: 2.345 | 2.355 | 2.3451
HALF_UP | 2.35 | 2.36 | 2.35
HALF_DOWN | 2.34 | 2.35 | 2.35
HALF_EVEN | 2.34 | 2.36 | 2.35
scale(2) = 1234.57
precision(3) = 1230
1/3, scale 4 = 0.3333
1/3, dividend scale = 0
exact scale reduction = 7.12
inexact scale reduction = ArithmeticException
direct = 1.25
twice = 1.24
```

Phương thức trợ giúp bắt `ArithmeticException` để bảng kết quả tiếp tục in được khi đến `UNNECESSARY`. Trong mã ứng dụng, cách xử lý ngoại lệ cần phản ánh yêu cầu đầu vào và tính toán, không nhất thiết chuyển ngoại lệ thành chuỗi như chương trình trình diễn này.

## 7. Vì sao cùng chế độ vẫn có thể cho kết quả khác?

### 7.1. Làm tròn nhiều lần có thể thay đổi kết quả

Hai dòng cuối chương trình cho thấy:

- Làm tròn trực tiếp `1.2451` về scale 2 bằng `HALF_EVEN`: `1.25`.
- Làm tròn về scale 3 trước: `1.245`; sau đó về scale 2: `1.24`.

Lần đầu ở nhánh thứ hai đã xóa thông tin rằng số gốc vượt điểm giữa. Khi làm tròn tiếp, hệ thống chỉ thấy `1.245`, đúng điểm giữa, rồi chọn chữ số chẵn 4.

Do đó, cần xác định rõ những bước nào được phép làm tròn. Không làm tròn tạm ở mọi phép toán chỉ để chuỗi số nhìn ngắn hơn. Nếu bắt buộc giới hạn precision của phép tính trung gian, cần coi giới hạn đó là một phần thiết kế tính toán và kiểm chứng kết quả cuối.

### 7.2. Làm tròn từng phần khác làm tròn tổng

Giả sử có ba giá trị, mỗi giá trị bằng `0.335`, dùng scale 2 và `HALF_UP`:

- Làm tròn từng giá trị: `0.34 + 0.34 + 0.34 = 1.02`.
- Cộng chính xác trước: `0.335 × 3 = 1.005`; làm tròn tổng: `1.01`.

Cả hai phép tính đều thực hiện đúng chế độ. Khác biệt nằm ở **thời điểm làm tròn**. Nếu dữ liệu hiển thị từng dòng phải cộng khớp một tổng đã chốt, bài toán còn cần quy tắc phân bổ phần chênh lệch; chọn một enum không tự giải quyết quy tắc đó.

### 7.3. Giá trị đầu vào có thể đã không đúng số cần xét

`new BigDecimal(2.675)` nhận giá trị `double` nhị phân đã có trước, không nhận nguyên văn số thập phân `2.675`. Làm tròn đúng trên một đầu vào khác vẫn có thể cho kết quả khác kỳ vọng.

Khi đầu vào nghiệp vụ là văn bản thập phân, dùng `new BigDecimal("2.675")`. Nếu chỉ có sẵn một `double`, `BigDecimal.valueOf(value)` dùng biểu diễn chuỗi của `double`; nó không khôi phục được thông tin đã mất trong các phép tính nhị phân trước đó.

Một ví dụ: chuyển kết quả `0.1 + 0.2` thành `BigDecimal` không phải bằng chứng rằng phép cộng ban đầu đã được thực hiện trong hệ thập phân chính xác. Chọn kiểu dữ liệu phù hợp cần diễn ra trước phép tính.

## 8. Chọn chế độ bằng yêu cầu, không bằng thói quen

Một cách tự kiểm tra yêu cầu là viết thành câu trước khi chọn enum:

| Câu mô tả cần đáp ứng | Chế độ tương ứng |
|---|---|
| Bỏ phần dư theo hướng về 0 | `DOWN` |
| Khi có phần dư thì tiến ra xa 0 | `UP` |
| Kết quả không nhỏ hơn giá trị gốc | `CEILING` |
| Kết quả không lớn hơn giá trị gốc | `FLOOR` |
| Gần nhất, hòa thì ra xa 0 | `HALF_UP` |
| Gần nhất, hòa thì về 0 | `HALF_DOWN` |
| Gần nhất, hòa thì chọn chữ số chẵn | `HALF_EVEN` |
| Từ chối mọi thay đổi giá trị do làm tròn | `UNNECESSARY` |

Các câu trên giả định đã xác định vị trí làm tròn và kết quả nằm trong phạm vi biểu diễn được của phép toán.

Không mặc định `HALF_UP` phù hợp với mọi dữ liệu, hoặc `HALF_EVEN` tự bảo đảm mọi phép tổng hợp đều chính xác. Quy tắc làm tròn phải thống nhất với nơi tạo dữ liệu, nơi lưu dữ liệu, phép tính và nơi hiển thị. Nếu chưa có quy tắc cho trường hợp đúng giữa hoặc số âm, hãy làm rõ hợp đồng đó.

Trong mã mới, truyền trực tiếp enum như `RoundingMode.HALF_EVEN`; tránh mã số chế độ khó đọc. Cần phân biệt thao tác thay đổi giá trị của `BigDecimal` với định dạng chuỗi để hiển thị: hiển thị ít chữ số không tự thay đổi đối tượng số sẽ được dùng trong các phép tính tiếp theo.

## 9. Lỗi thường gặp và cách nhận diện

| Lỗi | Dấu hiệu | Cách sửa |
|---|---|---|
| Coi `UP` là tăng giá trị | Bất ngờ khi `-2.1` thành `-3` | Nhớ hướng ra xa 0 |
| Coi `DOWN` là `FLOOR` | Cắt `-2.9` thành `-2` nhưng kỳ vọng `-3` | Chọn theo hướng cần trên trục số |
| Coi mọi số có chữ số 5 là đúng giữa | `2.3451` bị xử lý như `2.345` | Xét toàn bộ phần bị loại bỏ |
| Nhầm precision với scale | Muốn `1234.57` nhưng nhận `1230` | Chọn đúng `setScale` hoặc `MathContext` |
| Bỏ quên kết quả trả về | Số gốc vẫn còn nhiều chữ số | Gán/lưu đối tượng mới |
| Chỉ truyền mode cho `divide` | `1/3` ra `0` | Truyền rõ scale hoặc precision |
| Dùng `UNNECESSARY` để “không làm gì” | Gặp `ArithmeticException` | Hiểu đây là điều kiện chính xác |
| Làm tròn ở nhiều tầng mà không có chủ đích | Hai luồng cùng input nhưng khác kết quả cuối | Kiểm tra vị trí và số lần làm tròn |

Khi viết kiểm thử cho quy tắc làm tròn, chọn các đầu vào ở ngay dưới, đúng và ngay trên điểm giữa; thêm số âm, số đã chính xác, giá trị bằng 0 và trường hợp gây nhớ sang hàng trước như `9.995 → 10.00` khi dùng scale 2 với `HALF_UP`.

## 10. Tự luyện tập

1. Với `-8.21` và scale 1, dự đoán kết quả của `UP`, `DOWN`, `CEILING`, `FLOOR`.
2. Với scale 2, so sánh `HALF_UP`, `HALF_DOWN`, `HALF_EVEN` cho `6.225`, `6.235`, `6.22501`.
3. Dự đoán `"4.1000"` và `"4.1001"` khi dùng scale 2 với `UNNECESSARY`.
4. Giải thích vì sao thay `HALF_EVEN` bằng cùng một `HALF_EVEN` ở mọi tầng không loại bỏ được vấn đề làm tròn nhiều lần.

Đáp án đối chiếu:

1. Lần lượt `-8.3`, `-8.2`, `-8.2`, `-8.3`.
2. `6.225`: `6.23 / 6.22 / 6.22`; `6.235`: `6.24 / 6.23 / 6.24`; `6.22501`: cả ba cùng cho `6.23`.
3. `4.1000` chuyển thành `4.10`; `4.1001` gây `ArithmeticException`.
4. Lần làm tròn trước có thể loại bỏ thông tin cần thiết cho quyết định gần nhất ở lần sau; chương trình với `1.2451` đã minh họa điều này.
