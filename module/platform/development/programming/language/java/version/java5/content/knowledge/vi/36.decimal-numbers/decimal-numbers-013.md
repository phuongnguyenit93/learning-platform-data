# Ảnh hưởng của làm tròn trung gian đến kết quả cuối

## 1. Làm tròn là một bước tính toán có thể làm mất thông tin

`BigDecimal` tránh các xấp xỉ nhị phân không mong muốn khi dữ liệu thập phân được tạo đúng cách, nhưng không loại bỏ sai lệch do **chính sách làm tròn**.

Khi đưa `0.335` về hai vị trí thập phân bằng `HALF_UP`, ta nhận `0.34`. Phần chênh `0.005` không biến mất khỏi ý nghĩa toán học; nó đã được đưa vào dữ liệu dùng ở các bước sau.

Vì vậy, hai cách viết một công thức có vẻ tương đương có thể cho kết quả khác nếu vị trí làm tròn khác nhau:

```text
Làm tròn từng giá trị -> cộng các giá trị đã làm tròn
Cộng các giá trị chính xác -> làm tròn tổng
```

Muốn xác định chương trình đúng hay sai, cần biết yêu cầu chọn quy trình nào. Không có quy tắc chung rằng mọi bài toán đều phải làm tròn ở cùng một vị trí.

## 2. Làm tròn từng dòng và làm tròn tổng

Giả sử có ba dòng, mỗi dòng có giá trị chính xác `0.335`, và đầu ra cần hai vị trí thập phân với `HALF_UP`:

| Quy trình | Các bước | Kết quả |
| --- | --- | --- |
| Làm tròn từng dòng trước | `0.34 + 0.34 + 0.34` | `1.02` |
| Cộng chính xác rồi làm tròn | `0.335 × 3 = 1.005`, sau đó làm tròn | `1.01` |

Chênh lệch `0.01` xuất hiện dù mọi toán hạng đều là `BigDecimal` tạo từ chuỗi chính xác. Nguyên nhân là vị trí làm tròn, không phải lỗi kiểu dữ liệu.

Nếu quy tắc yêu cầu tổng bằng tổng các dòng đã chốt ở hai vị trí thập phân, quy trình đầu có thể là yêu cầu đúng. Nếu quy tắc yêu cầu cộng giá trị đầy đủ rồi mới làm tròn tổng, phải dùng quy trình sau. Cần ghi rõ hợp đồng này trong mã và ví dụ kiểm chứng.

## 3. Sai lệch có thể được khuếch đại khi nhân

Một giá trị trung gian làm tròn chỉ lệch một ít vẫn có thể tạo chênh lệch lớn hơn sau phép nhân.

Giả sử hệ số chính xác là `0.335`, số lượng là 100:

```text
Làm tròn hệ số trước: 0.335 -> 0.34; 0.34 × 100 = 34.00
Nhân trước:          0.335 × 100 = 33.500 -> 33.50
```

Chênh lệch cuối là `0.50`. Nếu một giá trị `x` bị thay bằng `x + e`, nhân với một số chính xác `m` làm phần sai lệch trở thành `m × e`. Dấu và độ lớn của `m` quyết định hướng và mức khuếch đại.

Phép trừ cũng cần chú ý: nếu hai số lớn gần nhau đã bị làm tròn, các chữ số nhỏ bị mất có thể chính là thông tin quyết định phần chênh lệch cần tính.

## 4. Làm tròn hai lần có thể khác làm tròn một lần

Thêm một bước làm tròn “để chuẩn hóa trước” không bảo đảm kết quả cuối giữ nguyên.

Ví dụ cùng dùng `HALF_EVEN` với số `2.3451`:

```text
Qua hai bước:
2.3451 -> scale 3: 2.345
2.345  -> scale 2: 2.34

Đi thẳng:
2.3451 -> scale 2: 2.35
```

Ở bước thứ hai của quy trình đầu, `2.345` nằm đúng giữa `2.34` và `2.35`; `HALF_EVEN` chọn `2.34`. Nhưng số gốc `2.3451` nằm hơi cao hơn điểm giữa, nên làm tròn trực tiếp chọn `2.35`.

Đó là hiện tượng làm tròn kép (`double rounding`). Không phải lần nào cũng xuất hiện, nên chỉ thử vài giá trị thông thường có thể không phát hiện được.

Một bước `setScale` chỉ thêm số 0 hoặc bỏ các số 0 không cần thiết mà giữ nguyên giá trị thì không tạo sai lệch giá trị. Vấn đề phát sinh khi thực sự bỏ thông tin khác 0.

## 5. Tăng scale về sau không phục hồi dữ liệu đã mất

Nếu tính `1 / 3` và làm tròn ngay về scale 2, ta có `0.33`. Nhân lại với 3 cho `0.99`, không phải 1.

Gọi `setScale(6)` lên `0.33` chỉ cho `0.330000`; nó không thể đoán rằng nguồn gốc từng là `1 / 3`. Muốn tính lại ở mức chính xác cao hơn, phải giữ toán hạng gốc hoặc giá trị trung gian đủ chính xác trước bước làm tròn.

Trong biểu thức này, `1 / 3` không có biểu diễn thập phân hữu hạn. Bỏ rounding mode và yêu cầu chia chính xác không phải giải pháp; `BigDecimal.divide` sẽ ném `ArithmeticException`. Cần chọn chính sách cho phép chia hoặc biến đổi biểu thức một cách đúng với điều kiện của bài toán.

Ví dụ, về mặt số học chính xác, biểu thức `(a / b) × b` bằng `a` nếu `b != 0`. Tuy nhiên, không được tự thay quy trình nghiệp vụ có yêu cầu chốt thương trung gian bằng một biểu thức rút gọn chỉ để kết quả trông đẹp hơn.

## 6. Precision hữu hạn làm thứ tự nhóm phép toán trở nên quan trọng

Khi truyền `MathContext` có precision hữu hạn ở từng bước, mỗi kết quả trung gian có thể bị làm tròn.

Với precision 3 và `HALF_UP`:

```text
(2000 + (-2000)) + 3:
0 + 3 = 3

2000 + ((-2000) + 3):
-1997 được làm tròn thành -2000
2000 + (-2000) = 0
```

Đẳng thức kết hợp của phép cộng chính xác không tự được bảo toàn trong quy trình làm tròn từng bước. Đổi thứ tự gom nhóm, chia dữ liệu thành các lô hoặc tổng hợp song song có thể thay đổi kết quả nếu phép cộng trung gian áp dụng context như vậy.

Nếu hợp đồng yêu cầu tổng chính xác rồi mới làm tròn, hãy cộng các giá trị hữu hạn chính xác trước. Nếu hợp đồng quy định làm tròn từng bước, cần cố định và kiểm chứng thứ tự bước tương ứng.

## 7. Chương trình chạy đầy đủ

Lưu thành `IntermediateRoundingDemo.java`; ví dụ dùng API có trên Java 17 trở lên.

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class IntermediateRoundingDemo {
    private static final RoundingMode MODE = RoundingMode.HALF_UP;

    public static void main(String[] args) {
        BigDecimal line = new BigDecimal("0.335");
        BigDecimal count = new BigDecimal("3");
        BigDecimal sumRoundedLines = line.setScale(2, MODE).multiply(count);
        BigDecimal roundedExactSum = line.multiply(count).setScale(2, MODE);
        System.out.println("round lines then sum = " + sumRoundedLines);
        System.out.println("sum then round = " + roundedExactSum);

        BigDecimal rate = new BigDecimal("0.335");
        BigDecimal quantity = new BigDecimal("100");
        System.out.println("rounded rate product = "
                + rate.setScale(2, MODE).multiply(quantity).setScale(2, MODE));
        System.out.println("exact rate product = "
                + rate.multiply(quantity).setScale(2, MODE));

        BigDecimal source = new BigDecimal("2.3451");
        BigDecimal roundedTwice = source.setScale(3, RoundingMode.HALF_EVEN)
                .setScale(2, RoundingMode.HALF_EVEN);
        BigDecimal roundedOnce = source.setScale(2, RoundingMode.HALF_EVEN);
        System.out.println("half even twice = " + roundedTwice);
        System.out.println("half even once = " + roundedOnce);

        BigDecimal third = BigDecimal.ONE.divide(new BigDecimal("3"), 2, MODE);
        System.out.println("rounded third times three = "
                + third.multiply(new BigDecimal("3")));
        System.out.println("third later padded = " + third.setScale(6));

        MathContext mc = new MathContext(3, MODE);
        BigDecimal x = new BigDecimal("2000");
        BigDecimal y = new BigDecimal("-2000");
        BigDecimal z = new BigDecimal("3");
        System.out.println("left group = "
                + x.add(y, mc).add(z, mc).toPlainString());
        System.out.println("right group = "
                + x.add(y.add(z, mc), mc).toPlainString());

        BigDecimal total = new BigDecimal("10.00");
        BigDecimal share = total.divide(new BigDecimal("3"), 2, RoundingMode.DOWN);
        BigDecimal assigned = share.multiply(new BigDecimal("3"));
        System.out.println("three equal rounded shares = " + assigned);
        System.out.println("unassigned remainder = " + total.subtract(assigned));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 IntermediateRoundingDemo.java
java IntermediateRoundingDemo
```

Stdout:

```text
round lines then sum = 1.02
sum then round = 1.01
rounded rate product = 34.00
exact rate product = 33.50
half even twice = 2.34
half even once = 2.35
rounded third times three = 0.99
third later padded = 0.330000
left group = 3
right group = 0
three equal rounded shares = 9.99
unassigned remainder = 0.01
```

Các cặp kết quả được tạo có chủ đích từ những quy trình khác nhau. Mỗi quy trình đều tuân theo API; việc chọn quy trình nào cần dựa trên yêu cầu của bài toán.

Hai dòng cuối minh họa việc chia tổng `10.00` thành ba phần bằng nhau ở scale 2: mỗi phần `3.33` chỉ cộng thành `9.99`. Phần dư `0.01` cần một quy tắc phân bổ riêng nếu tổng các phần phải đúng bằng `10.00`. Một quy tắc có thể tạo các phần `3.34`, `3.33`, `3.33`, nhưng phải nêu rõ phần nào nhận dư và cách xử lý các trường hợp khác. Không sửa ngẫu nhiên một phần chỉ để tổng khớp.

## 8. Thiết kế chính sách làm tròn rõ ràng

Một chính sách đầy đủ cần xác định ít nhất:

| Câu hỏi | Ví dụ câu trả lời cụ thể |
| --- | --- |
| Giá trị nào được làm tròn? | Từng dòng, hệ số trung gian, thương hay tổng cuối |
| Giới hạn theo cách nào? | Scale 2 hoặc precision 16 |
| Dùng quy tắc nào? | `HALF_UP`, `HALF_EVEN` hoặc hướng khác đã được thống nhất |
| Thời điểm nào? | Trước nhân số lượng, sau từng dòng hoặc tại điểm chốt đầu ra |
| Cần bảo toàn quan hệ nào? | Tổng các phần bằng tổng gốc, tổng hóa đơn bằng tổng dòng đã chốt |
| Khi có phần dư thì xử lý ra sao? | Thuật toán phân bổ xác định và có thể kiểm tra lại |

Một vài nguyên tắc triển khai:

- Giữ dữ liệu thập phân gốc bằng chuỗi hoặc `BigDecimal`, tránh đi vòng qua `double`.
- Tách giá trị dùng tính toán khỏi chuỗi định dạng hiển thị; không định dạng rồi phân tích ngược chuỗi để dùng như dữ liệu tính tiếp.
- Với các bước cộng, trừ, nhân hữu hạn, giữ chính xác nếu quy tắc chưa yêu cầu làm tròn.
- Với phép chia không hữu hạn, chọn precision/scale trung gian theo yêu cầu sai số. Có thể giữ thêm chữ số dự phòng, nhưng một số chữ số dự phòng cố định không bảo đảm đúng cho mọi thuật toán và mọi đầu vào.
- Chỉ đổi precision, rounding mode hoặc vị trí làm tròn khi chủ động thay đổi hợp đồng tính toán.

`HALF_EVEN` có thể giảm một số dạng thiên lệch trong tập dữ liệu phù hợp, nhưng không loại bỏ mọi sai lệch tích lũy hoặc hiện tượng làm tròn kép.

## 9. Ước lượng và kiểm chứng sai lệch

Khi làm tròn về **scale s cố định** theo một chế độ chọn giá trị gần nhất như `HALF_UP` hoặc `HALF_EVEN`, độ lệch tuyệt đối của một lần làm tròn không vượt quá:

```text
0.5 × 10^(-s)
```

Ví dụ scale 2 có mức lệch tối đa `0.005` cho một giá trị. Với n giá trị được làm tròn độc lập rồi cộng chính xác, tổng độ lệch so với tổng các giá trị gốc không vượt quá `n × 0.005`. Đây là giới hạn theo trường hợp xấu nhất cho phép cộng đó; nếu còn nhân, chia hoặc làm tròn tổng, phải xét thêm các bước tương ứng. Các chế độ có hướng như `UP`/`DOWN` không dùng cùng giới hạn nửa đơn vị này.

Nên kiểm chứng bằng những trường hợp có khả năng phân biệt chính sách:

- Giá trị đúng giữa và ngay hai phía của điểm giữa.
- Nhiều giá trị nhỏ có phần bị bỏ cùng chiều.
- Hệ số có nhiều chữ số nhân với số lượng lớn.
- Số âm và tổng có các khoản triệt tiêu nhau.
- Phép chia lặp vô hạn và bài toán cần phân bổ phần dư.

So sánh giá trị số của `BigDecimal` bằng `compareTo` khi scale không phải nội dung cần kiểm tra. Nếu hợp đồng yêu cầu scale cố định, kiểm tra scale riêng hoặc dùng so sánh biểu diễn có chủ đích.

## 10. Tự kiểm tra

Với hai giá trị `0.145`, scale 2 và `HALF_UP`:

1. Làm tròn từng giá trị rồi cộng được bao nhiêu?
2. Cộng trước rồi làm tròn được bao nhiêu?
3. Nếu đã lưu riêng từng giá trị thành `0.15`, tăng scale lên 5 có khôi phục được `0.145` không?

Đáp án:

1. `0.15 + 0.15 = 0.30`.
2. `0.145 + 0.145 = 0.290`, làm tròn thành `0.29`.
3. Không; chỉ nhận `0.15000`. Cần dữ liệu gốc để tính lại.

Tham khảo hợp đồng API hiện hành: [BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html) và [RoundingMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html) trong Java SE 21.
