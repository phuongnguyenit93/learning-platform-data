# UP và DOWN trong Java: làm tròn ra xa hoặc về phía 0

## 1. Mục tiêu và ý nghĩa

Khi phải giảm số chữ số thập phân hoặc số chữ số có nghĩa, Java cần biết phải xử lý phần bị loại bỏ như thế nào. Hai giá trị `RoundingMode.UP` và `RoundingMode.DOWN` của `java.math.RoundingMode` mô tả **hướng làm tròn so với số 0**, không mô tả hướng tăng hay giảm theo trục số.

- **UP — ra xa 0:** nếu phần bị bỏ có bất kỳ chữ số khác 0, tăng **độ lớn tuyệt đối** của kết quả lên một đơn vị ở vị trí giữ lại cuối cùng.
- **DOWN — về phía 0:** bỏ phần vượt quá độ chính xác đã chọn, **không tăng** chữ số cuối cùng còn giữ; nói cách khác, cắt bớt phần lẻ theo hướng 0.

Ví dụ, giữ **hai chữ số sau dấu thập phân**:

| Số ban đầu | UP | DOWN | Vì sao? |
| --- | ---: | ---: | --- |
| 1.231 | 1.24 | 1.23 | Phần bỏ đi là 1; UP tăng độ lớn, DOWN giữ nguyên phần đã giữ |
| -1.231 | -1.24 | -1.23 | UP đi về phía âm hơn; DOWN đi gần 0 hơn |
| 1.239 | 1.24 | 1.23 | UP không đợi chữ số bỏ đi đạt 5 |
| -1.239 | -1.24 | -1.23 | Quy tắc dựa vào trị tuyệt đối, áp dụng đối xứng với số âm |
| 1.230 | 1.23 | 1.23 | Chỉ bỏ số 0 nên không cần thay đổi giá trị |
| 0.001 | 0.01 | 0.00 | Với số rất nhỏ khác 0, UP vẫn đi xa 0 |
| -0.001 | -0.01 | 0.00 | DOWN có thể cho kết quả bằng 0 |

Điểm cốt lõi: **UP không đồng nghĩa với số lớn hơn; DOWN không đồng nghĩa với số nhỏ hơn**. Với số âm, UP thường cho số nhỏ hơn về mặt thứ tự số học, trong khi DOWN cho số lớn hơn.

## 2. Cơ chế theo vị trí giữ lại

Giả sử chỉ giữ hai chữ số sau dấu thập phân. Với `3.141`, phần được giữ trước khi làm tròn là `3.14`, còn phần bỏ là `0.001`.

- Dùng UP: phần bỏ khác 0, tăng một bước `0.01` theo hướng **ra xa 0** → `3.15`.
- Dùng DOWN: loại bỏ `0.001` theo hướng **về 0** → `3.14`.
- Với `-3.141`: UP → `-3.15`, DOWN → `-3.14`.

Một bước ở đây được xác định bởi **độ phân giải của kết quả**: giữ hai chữ số thập phân thì bước bằng `0.01`; giữ một chữ số thập phân thì bước bằng `0.1`; giữ phần nguyên thì bước bằng `1`. UP **chỉ** tăng một bước ở mức kết quả khi có phần khác 0 phải bỏ, bất kể chữ số đầu tiên bị bỏ là `1` hay `9`.

Đối với một số khác 0 cần rút ngắn, có thể hình dung:

- `DOWN`: lấy trị tuyệt đối → cắt tới độ phân giải đích → đặt lại dấu.
- `UP`: lấy trị tuyệt đối → nếu có phần khác 0 bị cắt, tăng một bước ở độ phân giải đích → đặt lại dấu.

Đây là cách hiểu khái niệm. Trong chương trình, hãy dùng `BigDecimal` cùng `RoundingMode` thay vì tự xử lý dấu hoặc nhân chia thủ công, đặc biệt ở biên độ lớn, giá trị âm và số có nhiều chữ số.

## 3. Thực hành với BigDecimal trên Java 17+

`BigDecimal` biểu diễn số thập phân chính xác theo hệ cơ số 10 và có các phương thức nhận `RoundingMode`. Dùng chuỗi như `new BigDecimal("1.231")` để bảo toàn đúng giá trị thập phân được viết ra; tránh lấy một giá trị `double` không chính xác rồi mới chuyển thành `BigDecimal`.

Tạo tệp `RoundingUpDownDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class RoundingUpDownDemo {
    private static void show(String input) {
        BigDecimal value = new BigDecimal(input);
        BigDecimal up = value.setScale(2, RoundingMode.UP);
        BigDecimal down = value.setScale(2, RoundingMode.DOWN);

        System.out.println(input
                + " -> UP=" + up.toPlainString()
                + ", DOWN=" + down.toPlainString());
    }

    public static void main(String[] args) {
        for (String input : new String[]{
                "1.231", "-1.231", "1.239",
                "1.230", "0.001", "-0.001"}) {
            show(input);
        }

        BigDecimal seven = new BigDecimal("7");
        BigDecimal three = new BigDecimal("3");
        System.out.println("7 / 3 UP="
                + seven.divide(three, 2, RoundingMode.UP));
        System.out.println("7 / 3 DOWN="
                + seven.divide(three, 2, RoundingMode.DOWN));

        BigDecimal number = new BigDecimal("17.89");
        System.out.println("Precision 3 UP="
                + number.round(new MathContext(3, RoundingMode.UP)));
        System.out.println("Precision 3 DOWN="
                + number.round(new MathContext(3, RoundingMode.DOWN)));
    }
}
~~~

Chạy:

~~~bash
javac RoundingUpDownDemo.java
java RoundingUpDownDemo
~~~

Kết quả:

~~~text
1.231 -> UP=1.24, DOWN=1.23
-1.231 -> UP=-1.24, DOWN=-1.23
1.239 -> UP=1.24, DOWN=1.23
1.230 -> UP=1.23, DOWN=1.23
0.001 -> UP=0.01, DOWN=0.00
-0.001 -> UP=-0.01, DOWN=0.00
7 / 3 UP=2.34
7 / 3 DOWN=2.33
Precision 3 UP=17.9
Precision 3 DOWN=17.8
~~~

Các điểm quan sát:

1. `setScale(2, mode)` giữ **hai chữ số sau dấu thập phân**, không phải hai chữ số có nghĩa.
2. `1.230` thành `1.23` ở cả hai mode: số 0 cuối chỉ ảnh hưởng cách biểu diễn ban đầu, không làm thay đổi giá trị.
3. `-0.001` với DOWN thành `0.00`; `BigDecimal` không duy trì một giá trị số âm riêng biệt cho zero.
4. `7 / 3` có phần dư khác 0: tại scale 2, UP là `2.34`, DOWN là `2.33`.
5. `MathContext(3, ...)` làm tròn theo **ba chữ số có nghĩa**. Với `17.89`, UP thành `17.9`, DOWN thành `17.8`.

## 4. Scale và precision là hai yêu cầu khác nhau

### Scale: số chữ số sau dấu thập phân

`BigDecimal.setScale(int newScale, RoundingMode mode)` thay đổi scale. Với `newScale = 2`:

- `new BigDecimal("123.456").setScale(2, UP)` → `123.46`.
- `new BigDecimal("123.456").setScale(2, DOWN)` → `123.45`.
- `new BigDecimal("-123.456").setScale(2, UP)` → `-123.46`.
- `new BigDecimal("-123.456").setScale(2, DOWN)` → `-123.45`.

Nếu **tăng scale**, ví dụ `1.2` thành scale 3, kết quả `1.200` chỉ được thêm số 0; không cần chọn lên hay xuống vì không mất chữ số khác 0. Nếu giảm scale nhưng phần bỏ toàn là 0, UP và DOWN cũng cho cùng giá trị.

Scale có thể âm: `new BigDecimal("124").setScale(-1, RoundingMode.DOWN)` đại diện cho `1.2E+2`, tức **120**; dùng UP cho **130**. Để hiển thị dạng thập phân thông thường, có thể gọi `toPlainString()`.

### Precision: tổng số chữ số có nghĩa

`MathContext(precision, mode)` ràng buộc **tổng chữ số có nghĩa của kết quả**, được dùng với `round(context)` hoặc một phép toán nhận `MathContext`:

| Giá trị gốc | Đích | UP | DOWN |
| --- | --- | ---: | ---: |
| 17.89 | 3 chữ số có nghĩa | 17.9 | 17.8 |
| 0.01234 | 3 chữ số có nghĩa | 0.0124 | 0.0123 |
| -987.65 | 3 chữ số có nghĩa | -988 | -987 |

Không nhầm `setScale(3, ...)` với `MathContext(3, ...)`: scale 3 giữ **ba chữ số sau dấu thập phân**, còn precision 3 giữ **ba chữ số có nghĩa** tùy độ lớn của số. `MathContext` có precision bằng 0 nghĩa là **không giới hạn precision**; khi đó quy tắc làm tròn không được dùng để cắt chữ số.

## 5. UP/DOWN và CEILING/FLOOR khác nhau thế nào?

Các tên gần giống nhau dễ gây lỗi. `RoundingMode.CEILING` hướng về **dương vô cực**, `RoundingMode.FLOOR` hướng về **âm vô cực**; chúng được xác định theo trục số. UP và DOWN được xác định theo khoảng cách đến 0.

Ví dụ làm tròn về phần nguyên (scale 0):

| Giá trị | UP (xa 0) | DOWN (gần 0) | CEILING (+∞) | FLOOR (-∞) |
| --- | ---: | ---: | ---: | ---: |
| 2.1 | 3 | 2 | 3 | 2 |
| -2.1 | -3 | -2 | -2 | -3 |
| 2.0 | 2 | 2 | 2 | 2 |
| -2.0 | -2 | -2 | -2 | -2 |

Với số dương, UP giống CEILING và DOWN giống FLOOR **trong tình huống làm tròn cùng độ phân giải**. Với số âm, sự ghép cặp đảo lại. Vì vậy yêu cầu “luôn làm tròn lên trên trục số” phải dùng CEILING, trong khi yêu cầu “luôn đẩy độ lớn ra xa 0” mới dùng UP.

`RoundingMode.HALF_UP` lại là quy tắc làm tròn **đến giá trị gần nhất**, với trường hợp đúng nửa bước thì đi ra xa 0. Ví dụ `1.231` giữ hai chữ số: UP → `1.24`, nhưng HALF_UP → `1.23`. Chữ UP trong HALF_UP **không** làm quy tắc này giống `RoundingMode.UP`.

## 6. Áp dụng đúng vào phép chia và phép tính nhiều bước

Một phép chia thập phân có thể không kết thúc: `1 / 3` không thể được biểu diễn bằng hữu hạn chữ số thập phân. Với `BigDecimal`, có thể chỉ định scale và rounding mode:

~~~java
BigDecimal result = new BigDecimal("1")
        .divide(new BigDecimal("3"), 2, RoundingMode.UP);
// result = 0.34
~~~

Nếu dùng `divide(BigDecimal divisor)` mà kết quả thập phân không kết thúc, `BigDecimal` có thể ném `ArithmeticException`. Việc chọn mode là một quyết định của nghiệp vụ: UP đảm bảo độ lớn không bị cắt giảm ở mức biểu diễn đích, còn DOWN cắt phần vượt quá.

Với giá trị âm, quy tắc vẫn như cũ: `-7 / 3` về scale 2 sẽ thành `-2.34` với UP và `-2.33` với DOWN. Không viết logic “cộng một phần nhỏ để làm tròn lên” áp dụng cho mọi dấu, vì với số âm hướng ra xa 0 chính là hướng âm hơn.

Hạn chế làm tròn sau **mọi bước trung gian** nếu bài toán yêu cầu kết quả chính xác ở cuối. Chẳng hạn:

- Trước tiên lấy `1.234 + 1.234 = 2.468`, sau đó dùng DOWN ở scale 2 → `2.46`.
- Nếu cắt mỗi số xuống `1.23` trước khi cộng, tổng thành `2.46`; cùng kết quả trong ví dụ này nhưng không phải luôn như vậy.
- Với `1.239 + 1.239 = 2.478`, dùng UP **một lần ở cuối** được `2.48`, còn làm UP từng số thành `1.24 + 1.24 = 2.48`; cũng trùng nhau trong trường hợp này.
- Trường hợp cho thấy khác biệt rõ: `1.231 + 1.231 = 2.462`; UP ở cuối cho `2.47`, còn UP mỗi số thành `1.24 + 1.24 = 2.48`.

Do đó cần quy định **thời điểm làm tròn**, **độ phân giải** và **mode**. Các phép tính cộng, trừ, nhân giữa `BigDecimal` có thể giữ độ chính xác thập phân mà không bắt buộc làm tròn; chỉ làm tròn tại ranh giới được yêu cầu. Nếu truyền `MathContext` ngay vào phép toán, kết quả của chính phép toán đó sẽ bị làm tròn theo context.

## 7. Cách chọn UP hay DOWN trong thực tế

Chọn mode từ đặc tả thay vì từ cảm giác tên gọi:

- **UP** khi yêu cầu rõ rằng giá trị khác 0, sau khi rút gọn, phải có **độ lớn không nhỏ hơn** độ lớn ban đầu ở độ phân giải đích; ví dụ quy ước làm tròn số lượng tài nguyên để đủ chỗ. Kiểm tra cả dấu âm và ý nghĩa nghiệp vụ.
- **DOWN** khi yêu cầu **cắt bớt** phần vượt quá để kết quả tiến về 0; hữu ích cho thuật toán cần loại bỏ các chữ số ngoài độ chính xác đích.
- Nếu yêu cầu là **gần nhất**, hãy đánh giá các mode `HALF_UP`, `HALF_EVEN`, v.v. UP/DOWN đều có sai lệch một hướng về độ lớn nếu phải làm tròn nhiều lần.
- Trong tài chính, tính phí và thuế, tuyệt đối không tự suy diễn rằng UP hoặc DOWN là chuẩn mặc định. Quy tắc làm tròn phải theo hợp đồng, chính sách hoặc quy định tương ứng; phép toán với giá trị âm (điều chỉnh, hoàn trả, ghi âm) đặc biệt dễ làm sai ý nghĩa.

Một câu hỏi kiểm tra trước khi lập trình: **“Khi số bị loại bỏ có chữ số khác 0, muốn trị tuyệt đối của kết quả tăng hay giảm (hoặc giữ ở phía gần 0)?”** Nếu muốn tăng độ lớn chọn UP; muốn cắt về 0 chọn DOWN.

## 8. Những lỗi thường gặp

**Lỗi 1 — Hiểu UP là luôn tăng giá trị số.** `-1.231` với UP scale 2 thành `-1.24`, là số **nhỏ hơn** `-1.231` trên trục số. Với yêu cầu tăng theo trục số, cân nhắc CEILING.

**Lỗi 2 — Tưởng UP chỉ làm tròn khi chữ số bỏ đi từ 5 trở lên.** UP áp dụng khi **bất kỳ** phần khác 0 nào bị loại. `2.001` scale 2 với UP vẫn là `2.01`. Quy tắc ngưỡng 5 thuộc các mode làm tròn gần nhất.

**Lỗi 3 — Dùng `double` để lưu giá trị thập phân rồi giả định nó chính xác.** Nhiều số cơ số 10 không thể biểu diễn đúng dưới dạng nhị phân dấu phẩy động. Với giá trị thập phân nghiệp vụ, xây dựng `BigDecimal` từ chuỗi hoặc từ `BigDecimal.valueOf(double)` khi dữ liệu đã là `double`, rồi xác nhận yêu cầu về nguồn dữ liệu và độ chính xác.

**Lỗi 4 — Quên `BigDecimal` bất biến.** Phương thức `setScale` trả về **đối tượng kết quả**, không sửa đối tượng gốc:

~~~java
BigDecimal original = new BigDecimal("1.231");
original.setScale(2, RoundingMode.UP); // Bỏ kết quả trả về.
System.out.println(original);          // 1.231

BigDecimal rounded = original.setScale(2, RoundingMode.UP);
System.out.println(rounded);           // 1.24
~~~

**Lỗi 5 — Nhầm số chữ số thập phân với chữ số có nghĩa.** `setScale(2, ...)` và `round(new MathContext(2, ...))` có thể cho kết quả rất khác nhau. Chọn đúng API theo yêu cầu.

**Lỗi 6 — Không tính tới kết quả bằng 0.** DOWN có thể biến `-0.001` thành `0.00` khi giữ hai chữ số thập phân; nếu cần biết dấu của dữ liệu đầu vào, lưu thông tin đó **trước khi làm tròn**.

**Lỗi 7 — Làm tròn quá sớm hoặc lặp lại không nhất quán.** Áp dụng UP từng phần rồi cộng có thể lệch so với cộng chính xác rồi UP tổng. Hãy ghi rõ ranh giới tính toán nào được phép làm tròn.

## 9. Tự kiểm tra

Thử tự tính trước khi chạy Java; mọi dòng đều đưa về scale 2:

| Đầu vào | UP | DOWN |
| --- | ---: | ---: |
| 12.000 | 12.00 | 12.00 |
| 12.001 | 12.01 | 12.00 |
| -12.001 | -12.01 | -12.00 |
| 0.0001 | 0.01 | 0.00 |
| -9.999 | -10.00 | -9.99 |

Nếu còn phân vân với số âm, hãy so sánh **khoảng cách từ mỗi kết quả tới 0**: UP chọn kết quả xa 0 hơn, DOWN chọn kết quả gần 0 hơn. Nếu không loại bỏ chữ số khác 0 nào, hai mode cho cùng giá trị số.

**Ghi nhớ:** Trong Java, `RoundingMode.UP` = **ra xa 0** và `RoundingMode.DOWN` = **về phía 0**. Quyết định độc lập với dấu, nhưng vị trí kết quả trên trục số phụ thuộc dấu. Luôn kết hợp mode với scale hoặc precision phù hợp và thời điểm làm tròn được xác định rõ.
