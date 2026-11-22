# Không suy ra quy tắc làm tròn nghiệp vụ chỉ từ kiểu dữ liệu

Một trường được khai báo là `int`, `double`, `BigDecimal`, `DECIMAL(18, 2)` hay “kiểu tiền tệ” **không tự trả lời được** câu hỏi nghiệp vụ: *làm tròn lúc nào, đến mức nào, theo hướng nào và trên đơn vị tính nào?*

Kiểu dữ liệu mô tả **cách một giá trị được biểu diễn và giới hạn xử lý của nền tảng**. Quy tắc làm tròn thuộc **hợp đồng nghiệp vụ**, cần được xác định độc lập, diễn đạt rõ ràng, kiểm thử và duy trì nhất quán trong toàn bộ luồng xử lý.

Ví dụ, cùng giá trị thập phân chính xác `1.005`:

```java
BigDecimal amount = new BigDecimal("1.005");

System.out.println(amount.setScale(2, RoundingMode.HALF_UP));   // 1.01
System.out.println(amount.setScale(2, RoundingMode.HALF_EVEN)); // 1.00
```

Cả hai kết quả đều được tạo từ cùng **một kiểu `BigDecimal`**, cùng **scale đích bằng 2**, nhưng khác **chế độ làm tròn**. Muốn biết kết quả nào đúng phải xem yêu cầu của nghiệp vụ cụ thể; Java không thể suy ra điều đó từ tên kiểu.

## 1. Tách ba lớp quyết định: biểu diễn, phép tính và nghiệp vụ

| Lớp quyết định | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| **Biểu diễn dữ liệu** | Lưu giá trị nào, chính xác đến đâu, giới hạn ra sao? | `BigDecimal`, `long` số đơn vị nhỏ nhất, `DECIMAL(18, 4)` |
| **Phép tính số học** | Thực hiện phép cộng/nhân/chia thế nào, có cần giới hạn precision không? | `multiply` chính xác; `divide` cần scale/mode nếu thương không kết thúc |
| **Quy tắc nghiệp vụ** | Khi nào làm tròn, làm tròn gì, bao nhiêu chữ số, hướng nào, xử lý phần dư ra sao? | Làm tròn thuế trên từng dòng hay toàn hóa đơn; giảm giá trước hay sau thuế |

Một quyết định ở lớp biểu diễn **không thay thế** quyết định ở lớp nghiệp vụ:

- Chọn `BigDecimal` giúp biểu diễn số thập phân và tính toán theo cơ chế decimal, nhưng **không chỉ định** `HALF_UP`, `HALF_EVEN` hoặc scale đích.
- Chọn `double` không hàm ý được làm tròn theo quy tắc ngân hàng. Nó dùng số dấu phẩy động nhị phân có sai số biểu diễn đối với nhiều phân số thập phân.
- Chọn `long` lưu “đơn vị nhỏ nhất” có thể tránh một số vấn đề số thập phân ở bước lưu trữ, nhưng **việc đổi từ giá trị chia nhỏ sang đơn vị nguyên vẫn cần chính sách làm tròn**.
- Khai báo `DECIMAL(p, s)` trong cơ sở dữ liệu mô tả precision và scale giới hạn của cột. Hành vi tự chuyển đổi, làm tròn hoặc từ chối dữ liệu vượt scale/phạm vi tùy hệ quản trị và cấu hình; cột `DECIMAL(18, 2)` **không xác định được** liệu một khoản phí phải làm tròn trên từng dòng hay cuối kỳ.

Nếu quy tắc nghiệp vụ không được nêu, **không được tự lấy số chữ số sau dấu trong kiểu lưu trữ làm chính sách**.

## 2. Precision, scale và RoundingMode là công cụ chứ không phải chính sách

`BigDecimal` có `unscaledValue`, `scale()` và `precision()`; giá trị bằng `unscaledValue × 10^(-scale)`. `setScale(2, mode)` chọn hai chữ số thập phân, còn `MathContext(4, mode)` giới hạn bốn chữ số có nghĩa của toàn bộ số. Cả hai đều là lựa chọn của người lập trình, chưa nói hệ thống **nên** làm tròn ở đâu.

```java
BigDecimal value = new BigDecimal("123.456");
System.out.println(value.setScale(2, RoundingMode.HALF_UP)); // 123.46
System.out.println(value.round(new MathContext(4, RoundingMode.HALF_UP))); // 123.5
```

Bài `Đưa precision, scale và rounding vào hợp đồng` trình bày định nghĩa, kiểm soát scale, precision và quy tắc chia. Ở đây ta xét **quyết định chính sách nghiệp vụ** cần áp những phép ấy tại bước nào.

## 3. RoundingMode không tự chọn thời điểm làm tròn

Các mode thông dụng gồm `HALF_UP` (hòa ra xa 0), `HALF_EVEN` (hòa về chữ số chẵn), `DOWN` (về 0), `UP` (xa 0), `FLOOR` (về âm vô cực), `CEILING` (về dương vô cực); `HALF_DOWN` và `UNNECESSARY` xử lý hòa/cấm làm tròn theo hợp đồng riêng.

```java
System.out.println(new BigDecimal("-1.235").setScale(2, RoundingMode.FLOOR)); // -1.24
System.out.println(new BigDecimal("-1.235").setScale(2, RoundingMode.DOWN));  // -1.23
```

Sự khác nhau của hai dòng trên phản ánh hướng làm tròn với số âm. Song ngay cả khi cùng mode và cùng scale, làm tròn ở **từng dòng**, **từng phép tính** hay **cuối tổng** có thể cho kết quả khác nhau. Bài này đặt trọng tâm ở quy tắc kết toán và thứ tự thao tác, không suy chúng ra từ Java type.

## 4. Cùng mode, cùng scale nhưng khác thời điểm làm tròn sẽ khác kết quả

Đây là một trong những lý do mạnh nhất khiến ta không thể suy quy tắc làm tròn từ kiểu dữ liệu.

Giả sử ba dòng độc lập, mỗi dòng có giá trị chính xác là `0.335`. Theo quy tắc `HALF_UP` và kết quả ở scale 2, có ít nhất hai lựa chọn:

**Lựa chọn A: làm tròn từng dòng, sau đó cộng**

```text
0.335 → 0.34
0.335 → 0.34
0.335 → 0.34
Tổng = 1.02
```

**Lựa chọn B: cộng giá trị chưa làm tròn, sau đó làm tròn tổng**

```text
0.335 + 0.335 + 0.335 = 1.005
1.005 → 1.01
```

Chênh lệch ở đây là **0.01** dù:

- Cùng dùng `BigDecimal`.
- Cùng đích scale 2.
- Cùng mode `RoundingMode.HALF_UP`.
- Không có lỗi biểu diễn nhị phân như `double`.

Vì vậy một quy tắc đầy đủ phải nêu **đơn vị làm tròn**: từng đơn giá, từng lượng nhân đơn giá, từng khoản thuế dòng, tổng hóa đơn, từng giao dịch, cuối tháng hay một mốc khác. Số liệu lưu trữ cũng cần phân biệt **giá trị chưa làm tròn** với **giá trị đã kết toán** nếu nghiệp vụ cần đối soát.

Tương tự, thứ tự của chiết khấu, thuế, phân bổ và các khoản điều chỉnh có thể thay đổi cơ sở tính. Không nên tự quyết định thứ tự hoặc mặc định rằng cách thực hiện đầu tiên trong mã là yêu cầu chuẩn.

## 5. Ví dụ Java 17+ chạy độc lập

Lưu tệp `BusinessRoundingDemo.java`:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.util.List;
import java.util.Objects;

public class BusinessRoundingDemo {
    record RoundingPolicy(int scale, RoundingMode mode) {
        RoundingPolicy {
            if (scale < 0) {
                throw new IllegalArgumentException("scale must be nonnegative");
            }
            Objects.requireNonNull(mode, "mode");
        }

        BigDecimal apply(BigDecimal value) {
            return Objects.requireNonNull(value, "value")
                    .setScale(scale, mode);
        }
    }

    static BigDecimal roundEachLine(
            List<BigDecimal> lines, RoundingPolicy policy) {
        BigDecimal total = BigDecimal.ZERO;
        for (BigDecimal line : lines) {
            total = total.add(policy.apply(line));
        }
        return total;
    }

    static BigDecimal roundOnlyTotal(
            List<BigDecimal> lines, RoundingPolicy policy) {
        BigDecimal rawTotal = BigDecimal.ZERO;
        for (BigDecimal line : lines) {
            rawTotal = rawTotal.add(line);
        }
        return policy.apply(rawTotal);
    }

    public static void main(String[] args) {
        BigDecimal midpoint = new BigDecimal("1.005");

        RoundingPolicy halfUp =
                new RoundingPolicy(2, RoundingMode.HALF_UP);
        RoundingPolicy halfEven =
                new RoundingPolicy(2, RoundingMode.HALF_EVEN);

        System.out.println("HALF_UP 1.005 = "
                + halfUp.apply(midpoint));
        System.out.println("HALF_EVEN 1.005 = "
                + halfEven.apply(midpoint));
        System.out.println("negative HALF_UP = "
                + halfUp.apply(new BigDecimal("-1.005")));

        List<BigDecimal> lines = List.of(
                new BigDecimal("0.335"),
                new BigDecimal("0.335"),
                new BigDecimal("0.335"));

        System.out.println("round each line = "
                + roundEachLine(lines, halfUp));
        System.out.println("round only total = "
                + roundOnlyTotal(lines, halfUp));

        BigDecimal base = new BigDecimal("19.99");
        BigDecimal rate = new BigDecimal("0.075");
        BigDecimal exactProduct = base.multiply(rate);
        System.out.println("unrounded product = " + exactProduct);
        System.out.println("product rounded = "
                + halfUp.apply(exactProduct));

        BigDecimal thirds = BigDecimal.ONE.divide(
                new BigDecimal("3"), 2, RoundingMode.HALF_UP);
        System.out.println("1 / 3 to scale 2 = " + thirds);

        BigDecimal value = new BigDecimal("1234.567");
        System.out.println("scale 2 = " + halfUp.apply(value));
        System.out.println("precision 3 = "
                + value.round(new MathContext(3, RoundingMode.HALF_UP)));

        try {
            new BigDecimal("3.1415")
                    .setScale(2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            System.out.println("UNNECESSARY rejected rounding");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac BusinessRoundingDemo.java
java BusinessRoundingDemo
```

**Stdout:**

```text
HALF_UP 1.005 = 1.01
HALF_EVEN 1.005 = 1.00
negative HALF_UP = -1.01
round each line = 1.02
round only total = 1.01
unrounded product = 1.49925
product rounded = 1.50
1 / 3 to scale 2 = 0.33
scale 2 = 1234.57
precision 3 = 1.23E+3
UNNECESSARY rejected rounding
```

Chương trình cố ý nhận `RoundingPolicy` như một **tham số nghiệp vụ tường minh**. `RoundingPolicy` mô tả scale và mode, trong khi hai hàm `roundEachLine` và `roundOnlyTotal` đại diện cho **hai thời điểm làm tròn khác nhau**. Một chính sách hoàn chỉnh trong ứng dụng thật còn phải mô tả đơn vị, giai đoạn tính toán, phiên bản và nguồn quy định.

Hàm `roundOnlyTotal` dùng phép cộng chính xác của `BigDecimal` trước khi đặt scale đích. Trong các phép chia mà kết quả thập phân vô hạn, ví dụ `1 / 3`, chương trình chỉ rõ scale và mode ngay tại phép chia. Không thể yêu cầu `BigDecimal` biểu diễn chính xác một dãy thập phân vô hạn trong một giá trị có số chữ số hữu hạn.

Phần `MathContext(3, ...)` cho thấy độ chính xác theo **chữ số có nghĩa** khác với làm tròn theo **số chữ số sau dấu**; việc chọn sai công cụ cũng có thể làm số liệu khác đáng kể.

## 6. Thiết kế chính sách làm tròn có thể kiểm soát và kiểm thử

Nếu hệ thống có nhiều nghiệp vụ, việc viết `setScale(2, RoundingMode.HALF_UP)` rải rác trong controller, service, mapper và đoạn xuất báo cáo rất khó bảo đảm nhất quán. Nên mô hình hóa một chính sách có thể được viện dẫn ở đúng **ranh giới nghiệp vụ**.

Một hợp đồng làm tròn rõ nghĩa thường trả lời các câu hỏi:

1. **Đại lượng là gì?** Tiền, khối lượng, số lượng, tỷ lệ, lãi suất, điểm thưởng, số đo hay chỉ số thống kê?
2. **Đơn vị và đơn vị nhỏ nhất là gì?** Ví dụ đơn vị tiền tệ, phần nghìn, gram, microsecond. Đừng mặc định “mọi đơn vị tiền đều có 2 chữ số thập phân”.
3. **Giữ bao nhiêu chữ số?** Chữ số sau dấu (scale), chữ số có nghĩa (precision), hoặc làm tròn đến bước cụ thể như 0,05.
4. **Mode làm tròn nào?** `HALF_UP`, `HALF_EVEN`, `FLOOR`, quy tắc riêng cho số âm, hay từ chối mọi giá trị cần làm tròn?
5. **Thực hiện ở bước nào?** Khi nhận dữ liệu, nhân đơn giá, tính thuế, chia phân bổ, kết toán từng dòng, tính tổng hay khi hiển thị?
6. **Có thể làm tròn nhiều lần không?** Làm tròn trước rồi dùng kết quả đó ở bước sau, hay giữ bản tính toán đầy đủ đến một ranh giới duy nhất?
7. **Dư số xử lý thế nào?** Phân bổ phần chênh lệch cho một dòng, tài khoản điều chỉnh, bên nhận đầu tiên, hay giữ thành khoản dư có truy vết?
8. **Ai/điều gì quyết định?** Hợp đồng với khách hàng, quy định pháp lý hiện hành, tài liệu nghiệp vụ đã được duyệt hay tiêu chuẩn nội bộ?
9. **Chính sách áp dụng theo phiên bản/thời gian nào?** Phải có cách giải thích lại số liệu lịch sử khi quy tắc về sau thay đổi.
10. **Kết quả nào cần được lưu?** Giá trị gốc, các thành phần đã lượng hóa, tổng đã làm tròn và dữ liệu để đối soát.

Không phải ứng dụng nào cũng cần mười trường trong một đối tượng Java. Nhưng các quyết định có ảnh hưởng đến kết quả **phải được xác định** thay vì ngầm dựa vào kiểu dữ liệu hoặc hành vi mặc định.

### Ví dụ mô tả bằng lời trước khi viết mã

> Giá thành của từng dòng được tính từ số lượng × đơn giá trong `BigDecimal`. Sau phép nhân, áp dụng scale 2 và `HALF_UP` cho **từng dòng**. Tổng tiền dòng bằng tổng các kết quả đã làm tròn. Thuế (nếu có) được tính và làm tròn theo chính sách riêng được hệ thống công bố. Kết quả cuối được lưu kèm đơn vị tiền, thời điểm áp dụng chính sách và mã phiên bản.

Đây chỉ là **một chính sách minh họa**, không phải quy tắc thuế/kế toán chung. Một hệ thống khác có thể yêu cầu cộng trước rồi mới làm tròn, giữ bốn chữ số nội bộ hoặc xử lý các bước chiết khấu khác nhau.

## 7. Phân biệt phép làm tròn trong tính toán và định dạng hiển thị

Định dạng như `DecimalFormat`, `NumberFormat` hay hiển thị “2 chữ số thập phân” phục vụ **giao diện người dùng**. Nó không tự tuyên bố cách kết toán chính thức.

Ví dụ, số gốc là `1.005`. Một UI có thể hiển thị `1.01` theo mode do UI đặt trong khi hệ thống kế toán giữ `1.005` chưa lượng hóa để tính một tổng sau đó. Nếu dùng chuỗi đã định dạng như **giá trị tính toán mới** mà không có quy tắc rõ ràng, bạn đã chuyển lựa chọn trình bày thành lựa chọn nghiệp vụ.

Cần tránh hai nhầm lẫn:

- **Hiển thị 2 chữ số** khác **lưu chính thức giá trị đã làm tròn đến 2 chữ số**.
- **Scale hiện tại là 2** khác **đã làm tròn đúng thời điểm và đúng mode được nghiệp vụ yêu cầu**.

Không nên tự động gọi `setScale(2, ...)` trong mọi mapper/serializer chỉ vì UI đang hiển thị hai chữ số. Khi dữ liệu đi qua API, cần nêu rõ trường nào là giá trị tính toán đầy đủ, trường nào là số đã được lượng hóa, trường nào chỉ phục vụ trình bày.

## 8. Lưu trữ và ranh giới giữa các hệ thống

### BigDecimal, double và dữ liệu đầu vào

Khi nghiệp vụ cần phép tính thập phân có thể kiểm soát, nên ưu tiên nguồn decimal rõ ràng:

```java
BigDecimal fromString = new BigDecimal("0.1");
BigDecimal fromDoubleValue = BigDecimal.valueOf(0.1);
BigDecimal binaryExact = new BigDecimal(0.1);
```

`new BigDecimal("0.1")` biểu diễn đúng giá trị thập phân 0,1. `BigDecimal.valueOf(0.1)` dùng biểu diễn thập phân từ `Double.toString(0.1)` nên thường phù hợp hơn constructor từ `double` khi đầu vào bắt buộc là `double`; còn `new BigDecimal(0.1)` biểu diễn chính xác giá trị nhị phân gần 0,1 đang nằm trong `double`, có thể tạo dãy chữ số dài ngoài mong đợi.

Dùng `BigDecimal` không tự giải quyết **nghiệp vụ**. Kể cả khi không có lỗi biểu diễn nhị phân, việc dùng sai mode hoặc làm tròn sai bước vẫn cho kết quả sai.

### Cơ sở dữ liệu và API

Một cột `DECIMAL(18, 2)` có thể bảo toàn hai vị trí thập phân trong phạm vi hỗ trợ, nhưng nó không ghi lại **lý do** dữ liệu có scale 2. Khi ghi một giá trị có nhiều chữ số hơn, các hệ CSDL/driver có thể có quy tắc làm tròn, chuyển đổi hoặc từ chối khác nhau. Phải kiểm tra hợp đồng của hệ thống đang dùng, đặc biệt tại ranh giới đọc/ghi và di trú dữ liệu.

Thiết kế nên tránh để việc ghi dữ liệu tình cờ trở thành “lần làm tròn nghiệp vụ” mà không có xác nhận. Hãy quyết định chính sách trước khi lưu, rồi kiểm thử việc ghi/đọc không vô tình thay đổi giá trị đã được chấp thuận.

Ví dụ các thông tin có thể hữu ích để lưu hay suy ra từ chứng từ: đơn vị, giá trị gốc, giá trị tính toán, giá trị đã lượng hóa, mã quy tắc và phiên bản áp dụng. Mức độ lưu trữ phụ thuộc yêu cầu audit/đối soát; không có một schema mặc định đúng cho mọi hệ thống.

### Quy tắc không nhất thiết “2 chữ số thập phân”

Có miền cần số nguyên, có miền dùng ba chữ số, có nơi phải làm tròn theo bước như 0,05 hay 5 đơn vị. Với yêu cầu “bội số gần nhất của một bước”, chỉ đặt `scale` là chưa đủ; còn phải làm phép lượng hóa theo **bước**.

Ví dụ công thức toán học cho giá trị `v`, bước dương `s` và mode `m`:

```text
rounded = round(v / s, mode) × s
```

Trong Java, với `BigDecimal`, cần sử dụng một phép chia có quy tắc làm tròn cụ thể, thường là thương nguyên được làm tròn về scale 0:

```java
static BigDecimal roundToStep(
        BigDecimal value, BigDecimal step, RoundingMode mode) {
    if (step.signum() <= 0) {
        throw new IllegalArgumentException("step must be positive");
    }
    BigDecimal count = value.divide(step, 0, mode);
    return count.multiply(step);
}
```

Hàm này là **đoạn minh họa** đặt trong một lớp cùng các import thích hợp. Với `value = 1.03`, `step = 0.05` và `HALF_UP`, kết quả là `1.05`; một yêu cầu “scale 2” thuần túy lại giữ `1.03`. Do đó ngay cả đơn vị làm tròn cũng là quy tắc nghiệp vụ cần nêu.

## 9. Kiểm thử quy tắc nghiệp vụ thay vì chỉ kiểm thử kiểu

Các bài test nên dựa vào **đầu ra được duyệt của chính sách** và có ví dụ ranh giới:

| Tình huống | Dữ liệu thử | Câu hỏi cần kiểm chứng |
|---|---|---|
| Điểm giữa | `1.005` với scale 2 | `HALF_UP` hay `HALF_EVEN`? |
| Điểm giữa âm | `-1.005` với scale 2 | Hướng xử lý giá trị âm đúng chưa? |
| Không ở điểm giữa | `1.004`, `1.006` | Làm tròn theo lân cận đúng chưa? |
| Tổng nhiều dòng | `0.335` lặp 3 lần | Làm tròn từng dòng hay toàn bộ? |
| Thuế và chiết khấu | Số tiền × tỷ lệ | Đúng thứ tự tính, cơ sở tính và điểm làm tròn? |
| Chia phân bổ | Chia 1 đơn vị cho 3 đối tượng | Phần dư có được xử lý/đối soát rõ không? |
| Không cho phép mất thông tin | `3.1415` → scale 2 | Có từ chối như yêu cầu không? |
| Ranh giới hệ thống | JSON/DB/UI | Giá trị chính thức có được bảo toàn? |
| Đổi phiên bản quy tắc | Giao dịch trước/sau mốc áp dụng | Có tái hiện đúng kết quả lịch sử không? |

Trong kiểm thử `BigDecimal`, cần chú ý mục tiêu so sánh:

- `assertEquals(new BigDecimal("1.00"), actual)` kiểm tra bằng nhau theo `BigDecimal.equals()`, gồm cả **scale**. Phù hợp khi hợp đồng đòi kết quả có scale 2.
- `expected.compareTo(actual) == 0` chỉ so sánh **giá trị số học**, bỏ qua khác biệt scale. Phù hợp khi hợp đồng không yêu cầu dạng biểu diễn.

Không thay mọi so sánh bằng `compareTo()==0` hoặc mọi so sánh bằng `equals()` mà không xét xem scale có phải một phần của hợp đồng kết quả hay không.

## 10. Những lỗi thiết kế dễ gặp

1. **“Là BigDecimal nên đã xử lý làm tròn đúng.”** `BigDecimal` chỉ cho công cụ; mode, scale, thời điểm làm tròn và thứ tự nghiệp vụ vẫn phải khai báo.
2. **“Cột database scale 2, vậy chính sách là HALF_UP hai chữ số.”** Kiểu cột không tự xác lập mode, đơn vị hay thời điểm nghiệp vụ.
3. **“Mọi số tiền luôn có hai chữ số.”** Không đúng với mọi tiền tệ, đơn vị và quy tắc tính; ngay trong cùng miền cũng có thể cần độ chính xác tính toán lớn hơn độ chính xác hiển thị.
4. **Làm tròn mỗi khi đi qua một tầng ứng dụng.** Điều này gây làm tròn lặp (double rounding), mất thông tin và lệch đối soát. Chỉ làm tròn tại ranh giới đã được xác định.
5. **Dùng `MathContext(2)` để yêu cầu “hai chữ số thập phân”.** `MathContext` giới hạn chữ số có nghĩa; `setScale(2, mode)` điều chỉnh scale.
6. **Dùng `RoundingMode.HALF_EVEN` vì nghe giống “quy tắc ngân hàng”.** Tên gọi không đủ để chọn chính sách. Cần yêu cầu chính thức.
7. **Không kiểm thử số âm, giá trị sát điểm giữa và phần dư phân bổ.** Những trường hợp này dễ làm lộ sai hướng làm tròn hoặc sai thứ tự tính.
8. **Tự chuyển sang `double` ở giữa phép tính decimal.** Có thể đưa vào sai số nhị phân mà không ai dự định.
9. **Đồng nhất định dạng UI với kết quả đã kết toán.** Chuỗi hiển thị có thể không phải giá trị cần đưa trở lại công thức.
10. **Không lưu căn cứ hoặc phiên bản quy tắc.** Khi chính sách thay đổi, khó giải thích vì sao hai giao dịch có số gốc giống nhau nhưng kết quả khác nhau.

## 11. Tự kiểm tra

**Câu 1.** Chỉ biết một trường có kiểu `BigDecimal`, có suy ra được nó phải dùng `HALF_UP` hay `HALF_EVEN` không?  
**Đáp án:** Không. Kiểu dữ liệu không quyết định quy tắc nghiệp vụ.

**Câu 2.** Hệ thống dùng `DECIMAL(18, 2)`. Có đủ thông tin để chọn làm tròn từng dòng hay làm tròn tổng không?  
**Đáp án:** Không. Scale lưu trữ không chỉ định thời điểm và phạm vi làm tròn.

**Câu 3.** Với ba giá trị `0.335` và `HALF_UP` scale 2, vì sao có thể ra `1.02` hoặc `1.01`?  
**Đáp án:** Làm tròn từng dòng rồi cộng cho `1.02`; cộng chính xác trước rồi làm tròn một lần cho `1.01`.

**Câu 4.** `new BigDecimal("1.005").setScale(2, HALF_EVEN)` trả gì?  
**Đáp án:** `1.00`, bởi tại điểm giữa lựa chọn chữ số giữ lại chẵn. Với `HALF_UP` kết quả là `1.01`.

**Câu 5.** Cần làm tròn về bội số của `0.05`. Chỉ `setScale(2)` có đủ không?  
**Đáp án:** Không. Scale 2 chỉ bảo đảm hai vị trí thập phân; cần quy tắc lượng hóa theo bước 0,05.

**Câu 6.** Nếu ứng dụng cho phép hiển thị hai chữ số nhưng giữ dữ liệu nội bộ chưa lượng hóa cho lần tính tiếp theo, nên dùng chuỗi UI làm dữ liệu tính tiếp không?  
**Đáp án:** Không, trừ khi hợp đồng nghiệp vụ có chủ ý chọn số đã lượng hóa. Phải tách giá trị tính toán, kết quả kết toán và định dạng trình bày.

**Câu 7.** Khi nào `RoundingMode.UNNECESSARY` hữu ích?  
**Đáp án:** Khi muốn **phát hiện và từ chối** trường hợp chuyển scale hoặc phép tính sẽ phải làm tròn mất thông tin.

**Ghi nhớ:** Kiểu dữ liệu trả lời *giá trị được biểu diễn ra sao*; quy tắc nghiệp vụ trả lời *làm tròn thứ gì, ở bước nào, theo mode nào và đến đơn vị nào*. Hai quyết định phải được thiết kế, công bố và kiểm thử **riêng nhưng nhất quán**.
