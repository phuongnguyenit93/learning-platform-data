# Tổng hợp BigDecimal bằng reduce với quy tắc làm tròn rõ ràng

Trong chương **Độ chính xác khi tổng hợp số** của **Java Stream API**, việc cộng tiền, thuế, phí hoặc các số thập phân cần độ chính xác cao đòi hỏi nhiều hơn một lời gọi `sum()`. Với dữ liệu kiểu `BigDecimal`, ta thường dùng `map` để tạo các khoản cần cộng và `reduce` để tổng hợp. Quyết định quan trọng nhất là **làm tròn ở bước nào, đến bao nhiêu chữ số và theo chế độ nào**.

Bài học này xây dựng một pipeline khai báo có kết quả kiểm chứng được: cộng các `BigDecimal` **chính xác trong suốt quá trình tổng hợp**, sau đó làm tròn tại **ranh giới nghiệp vụ** đã xác định. Bài cũng giải thích vì sao làm tròn trong accumulator có thể làm mất tính kết hợp (*associativity*) và làm kết quả khác nhau khi đổi cách gom nhóm hoặc chuyển sang parallel stream.

## 1. Vì sao không cộng tiền bằng double?

`double` biểu diễn số theo định dạng dấu phẩy động nhị phân IEEE 754. Nhiều số thập phân như `0.1` không có biểu diễn nhị phân hữu hạn, vì vậy một số phép cộng sinh ra sai số biểu diễn:

~~~java
double a = 0.1;
double b = 0.2;

System.out.println(a + b); // 0.30000000000000004
~~~

`BigDecimal` biểu diễn một số bằng **giá trị nguyên không chia tỷ lệ (*unscaled value*)** và **scale**. Khi khởi tạo từ chuỗi thập phân, giá trị là đúng theo các chữ số được cung cấp:

~~~java
import java.math.BigDecimal;

BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");

System.out.println(a.add(b)); // 0.3
~~~

Khởi tạo dữ liệu tài chính nên ưu tiên:

- `new BigDecimal("19.995")` nếu giá trị đến từ văn bản, JSON hoặc dữ liệu nguồn có chữ số thập phân xác định.
- `BigDecimal.valueOf(42L)` nếu giá trị nguyên được dùng làm số lượng hoặc thành tiền.
- `BigDecimal.valueOf(0.1)` khi buộc phải chuyển một `double` đã có: phương thức dựa trên biểu diễn chuỗi thập phân chuẩn của `double`, nhưng **không khôi phục được thông tin đã mất** từ các phép tính dấu phẩy động trước đó.

Tránh `new BigDecimal(0.1)` khi mục tiêu là giá trị thập phân chính xác `0.1`, bởi constructor nhận nguyên giá trị xấp xỉ nhị phân của `double`:

~~~java
System.out.println(new BigDecimal(0.1));
// 0.1000000000000000055511151231257827021181583404541015625

System.out.println(new BigDecimal("0.1")); // 0.1
~~~

`BigDecimal` tránh sai số biểu diễn **nếu đầu vào đã chính xác**. Nó không tự chọn chính sách làm tròn, loại bỏ mọi lỗi nhập liệu hay tự xác định đơn vị tiền tệ phù hợp.

## 2. Pipeline cơ bản: map rồi reduce

Giả sử mỗi dòng hóa đơn có số lượng và đơn giá. Thành tiền chính xác của một dòng bằng:

\[
\text{thành tiền dòng} = \text{đơn giá} \times \text{số lượng}
\]

Tổng trước làm tròn bằng:

\[
S = \sum_{i=1}^{n} p_i q_i
\]

Trong Stream API, đó là pipeline:

~~~java
import java.math.BigDecimal;
import java.util.List;

record Line(long quantity, BigDecimal unitPrice) {}

List<Line> lines = List.of(
        new Line(2, new BigDecimal("12.345")),
        new Line(1, new BigDecimal("3.210"))
);

BigDecimal exactTotal = lines.stream()
        .map(line -> line.unitPrice()
                .multiply(BigDecimal.valueOf(line.quantity())))
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(exactTotal); // 27.900
~~~

Giải thích:

1. `lines.stream()` tạo nguồn từ collection.
2. `map` biến mỗi `Line` thành một `BigDecimal` biểu diễn thành tiền của dòng.
3. `reduce(BigDecimal.ZERO, BigDecimal::add)` dùng **0 làm identity** và phép `add` làm phép kết hợp các khoản.
4. `exactTotal` chứa kết quả chính xác theo các giá trị đầu vào, **chưa có chính sách làm tròn**.

Tổng ở ví dụ là `2 × 12.345 + 3.210 = 27.900`. Phép `multiply` và `add` **không truyền `MathContext`** thực hiện phép toán thập phân chính xác; thông thường scale của kết quả được giữ theo quy tắc của `BigDecimal`.

Lựa chọn `BigDecimal.ZERO` làm identity giúp Stream rỗng trả về `0` thay vì phải xử lý `Optional.empty()`. Một số hệ thống sau đó chuẩn hóa về đúng hai chữ số:

~~~java
import java.math.RoundingMode;

BigDecimal payable = exactTotal.setScale(2, RoundingMode.HALF_UP);
System.out.println(payable); // 27.90
~~~

Đây là cách làm rõ hai bước: **tính tổng chính xác** và **làm tròn cho mục đích thanh toán/hiển thị**.

## 3. Xác định chính sách làm tròn trước khi viết reduce

Không tồn tại một quy tắc làm tròn duy nhất đúng cho mọi quốc gia, loại tiền hoặc nghiệp vụ. Trước khi viết mã, cần xác định đầy đủ:

| Câu hỏi | Ví dụ quyết định | Vì sao quan trọng? |
| --- | --- | --- |
| **Đơn vị và scale đích** | Hai chữ số thập phân cho một khoản tiền minh họa | Scale xác định đơn vị nhỏ nhất mà kết quả sẽ biểu diễn. |
| **Rounding mode** | `RoundingMode.HALF_UP` hoặc `HALF_EVEN` | Hai quy tắc có thể cho kết quả khác nhau ở điểm đúng giữa. |
| **Điểm làm tròn** | Mỗi dòng, mỗi khoản thuế, mỗi hóa đơn hay sau khi nhóm | Cộng rồi làm tròn không phải lúc nào cũng bằng làm tròn từng phần rồi cộng. |
| **Dữ liệu đầu vào** | Đơn giá có thể có 3–4 chữ số thập phân | Không được âm thầm cắt mất độ chính xác trước khi tính. |
| **Nhóm dữ liệu** | Tổng theo khách hàng, hóa đơn, ngày giao dịch | Cần biết khi nào mỗi nhóm được phép làm tròn. |
| **Số âm và hoàn tiền** | Hoàn tiền, điều chỉnh giảm | Quy tắc làm tròn phải áp dụng nhất quán cho cả số âm. |

Ví dụ quy tắc minh họa:

> Cộng chính xác mọi khoản phát sinh trong **một hóa đơn**, sau đó làm tròn tổng hóa đơn đến **2 chữ số thập phân** bằng `RoundingMode.HALF_UP`. Các khoản tiền âm được cộng như số âm. Không làm tròn từng dòng trước khi cộng.

Quy tắc này là **giả định của bài tập**, không phải chuẩn pháp lý áp dụng cho mọi đơn vị tiền tệ hoặc mọi hóa đơn. Trong ứng dụng thật, chính sách phải đến từ nghiệp vụ, hợp đồng, quy định kế toán/thuế hoặc đặc tả tích hợp đang sử dụng.

## 4. Ví dụ hoàn chỉnh: làm tròn sau khi reduce

Ba dòng hàng có thành tiền đúng bằng `0.005` mỗi dòng giúp thấy rõ sự khác biệt giữa các thời điểm làm tròn.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

public class InvoiceReductionDemo {
    record Line(String sku, long quantity, BigDecimal unitPrice) {}

    private static final int MONEY_SCALE = 2;
    private static final RoundingMode MONEY_ROUNDING = RoundingMode.HALF_UP;

    static BigDecimal exactSubtotal(List<Line> lines) {
        return lines.stream()
                .map(line -> line.unitPrice()
                        .multiply(BigDecimal.valueOf(line.quantity())))
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    static BigDecimal payable(List<Line> lines) {
        return exactSubtotal(lines).setScale(
                MONEY_SCALE, MONEY_ROUNDING);
    }

    public static void main(String[] args) {
        List<Line> lines = List.of(
                new Line("A", 1, new BigDecimal("0.005")),
                new Line("B", 1, new BigDecimal("0.005")),
                new Line("C", 1, new BigDecimal("0.005"))
        );

        System.out.println(exactSubtotal(lines)); // 0.015
        System.out.println(payable(lines));        // 0.02

        BigDecimal roundedPerLine = lines.stream()
                .map(line -> line.unitPrice()
                        .multiply(BigDecimal.valueOf(line.quantity()))
                        .setScale(MONEY_SCALE, MONEY_ROUNDING))
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        System.out.println(roundedPerLine); // 0.03
    }
}
~~~

Điểm khác nhau:

~~~text
Cộng chính xác rồi làm tròn:
  0.005 + 0.005 + 0.005 = 0.015
  0.015 -> 0.02 (HALF_UP, 2 chữ số)

Làm tròn từng dòng rồi cộng:
  0.005 -> 0.01
  0.005 -> 0.01
  0.005 -> 0.01
  Tổng = 0.03
~~~

**Cả hai phép tính đều có thể hợp lệ dưới những chính sách nghiệp vụ khác nhau.** Chúng không tương đương và phải được lựa chọn có chủ đích. Nếu tài liệu nghiệp vụ quy định làm tròn mỗi dòng trước khi tính tổng, hãy diễn đạt điều đó trong `map` và kiểm thử đúng quy tắc. Nếu quy định làm tròn ở cấp hóa đơn, giữ các dòng chính xác cho tới sau `reduce`.

Lưu ý: `setScale(2, ...)` không làm cho phép tính trước đó chính xác hơn. Nó quyết định **cách chuyển** giá trị chính xác sang kết quả có hai chữ số thập phân.

## 5. So sánh các RoundingMode thường gặp

Với `setScale(2, mode)`, hai chữ số thập phân được giữ lại, còn phần dư xác định có phải thay đổi chữ số cuối hay không.

| Giá trị gốc | `HALF_UP` | `HALF_EVEN` | `DOWN` | `UP` |
| --- | ---: | ---: | ---: | ---: |
| `2.344` | 2.34 | 2.34 | 2.34 | 2.35 |
| `2.345` | 2.35 | 2.34 | 2.34 | 2.35 |
| `2.355` | 2.36 | 2.36 | 2.35 | 2.36 |
| `-2.345` | -2.35 | -2.34 | -2.34 | -2.35 |

Ý nghĩa:

- `HALF_UP`: làm tròn về số gần nhất; nếu đúng giữa hai lựa chọn thì làm tròn **ra xa 0**.
- `HALF_EVEN`: làm tròn về số gần nhất; nếu đúng giữa thì chọn kết quả có **chữ số cuối được giữ lại là chẵn** (*banker's rounding*).
- `DOWN`: làm tròn về **0**; không đồng nghĩa luôn làm tròn xuống theo trục số.
- `UP`: làm tròn **ra xa 0**.
- `CEILING`: hướng về dương vô cực; `FLOOR`: hướng về âm vô cực. Cần đặc biệt phân biệt với `UP`/`DOWN` khi xử lý số âm.
- `UNNECESSARY`: từ chối phép toán cần làm tròn bằng cách ném `ArithmeticException`.

`HALF_EVEN` thường được chọn để giảm thiên lệch làm tròn khi có nhiều lần làm tròn, nhưng điều đó **không thay thế yêu cầu chọn đúng điểm làm tròn**. Nếu hợp đồng ghi `HALF_UP`, không được tự đổi sang `HALF_EVEN` chỉ vì thấy lựa chọn kia phổ biến trong một hệ thống khác.

## 6. Vì sao không nên làm tròn bên trong accumulator?

Một đoạn mã có vẻ ngắn nhưng dễ sai là:

~~~java
BigDecimal total = values.stream()
        .reduce(BigDecimal.ZERO,
                (sum, value) -> sum.add(value)
                        .setScale(2, RoundingMode.HALF_UP));
~~~

Mỗi lần thêm một phần tử, accumulator đã làm mất các chữ số dư trước khi đọc phần tử tiếp theo. Kết quả có thể phụ thuộc vào **cách các phần tử được gom nhóm**. Điều này đặc biệt nguy hiểm khi gọi `parallel()`, vì phép toán dùng trong reduction cần có tính kết hợp thích hợp để có thể chia nhỏ và ghép kết quả.

Ta xét một toán tử làm tròn đến số nguyên:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.function.BinaryOperator;

BinaryOperator<BigDecimal> roundedAdd =
        (x, y) -> x.add(y).setScale(0, RoundingMode.HALF_UP);

BigDecimal a = new BigDecimal("0.4");
BigDecimal b = new BigDecimal("0.4");
BigDecimal c = new BigDecimal("0.7");

BigDecimal left = roundedAdd.apply(roundedAdd.apply(a, b), c);
BigDecimal right = roundedAdd.apply(a, roundedAdd.apply(b, c));

System.out.println(left);  // 2
System.out.println(right); // 1
~~~

Ta có:

~~~text
(a ⊕ b) ⊕ c = round(round(0.4 + 0.4) + 0.7)
              = round(1 + 0.7) = 2

a ⊕ (b ⊕ c) = round(0.4 + round(0.4 + 0.7))
              = round(0.4 + 1) = 1
~~~

Vì `left != right`, phép `roundedAdd` **không có tính kết hợp**. Hơn nữa, nếu `identity` là `BigDecimal.ZERO`, phép thêm rồi làm tròn cũng không còn giữ nguyên mọi giá trị đầu vào: `roundedAdd.apply(BigDecimal.ZERO, new BigDecimal("0.4"))` trả `0` thay vì `0.4`. Như vậy nó không đáp ứng đầy đủ hợp đồng của một reduction dùng identity cho các giá trị chưa làm tròn.

Trong khi đó, phép cộng `BigDecimal::add` **không truyền `MathContext`** là phép cộng thập phân chính xác và phù hợp để tổng hợp theo các nhóm khác nhau, miễn dữ liệu nguồn có thể xử lý hợp lệ:

~~~java
BigDecimal exact = values.parallelStream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

BigDecimal rounded = exact.setScale(2, RoundingMode.HALF_UP);
~~~

Cách này tạo ra kết quả số học không phụ thuộc vào việc các phần tử được chia thành nhóm nào. Việc parallel stream có nhanh hơn hay không vẫn cần đo riêng; đối với tập dữ liệu nhỏ, overhead có thể lớn hơn lợi ích.

### Trường hợp nghiệp vụ bắt buộc làm tròn từng bước

Đôi khi nghiệp vụ quy định mỗi bút toán được làm tròn khi ghi nhận và các bước tiếp theo phải tính trên **bút toán đã chốt**. Khi đó, hãy biến đổi mỗi phần tử theo quy tắc đã chốt trước khi giảm:

~~~java
BigDecimal sumOfBookedAmounts = values.stream()
        .map(value -> value.setScale(2, RoundingMode.HALF_UP))
        .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

Bây giờ mỗi phần tử đã có giá trị nghiệp vụ riêng. `reduce` vẫn dùng phép cộng chính xác trên các giá trị đã làm tròn; cách này có thể chạy song song theo đúng tính chất của phép cộng. Nó khác với việc làm tròn **tổng chạy tích lũy** sau mỗi phép cộng.

## 7. MathContext không phải chính sách số chữ số thập phân

`MathContext` kiểm soát **precision** (số chữ số có nghĩa), cùng `RoundingMode`. Nó khác với `setScale`, vốn kiểm soát số chữ số **sau dấu thập phân**.

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

BigDecimal value = new BigDecimal("123.456");

System.out.println(
        value.round(new MathContext(4, RoundingMode.HALF_UP))
); // 123.5: bốn chữ số có nghĩa

System.out.println(
        value.setScale(4, RoundingMode.HALF_UP)
); // 123.4560: bốn chữ số sau dấu thập phân
~~~

Với phép tính tiền cần hai chữ số sau dấu thập phân ở kết quả, `setScale(2, roundingMode)` thường mô tả đúng yêu cầu hơn `new MathContext(2, ...)`.

Cũng cần phân biệt:

~~~java
BigDecimal a = new BigDecimal("1234.56");
BigDecimal b = new BigDecimal("0.78");

// Cộng chính xác:
BigDecimal exact = a.add(b); // 1235.34

// Cộng có precision giới hạn: có thể làm tròn ngay trong phép cộng.
BigDecimal approximate = a.add(
        b, new MathContext(5, RoundingMode.HALF_UP)
); // 1235.3
~~~

Khi gọi `add(b, mathContext)` trong mỗi lượt `reduce`, sai số làm tròn trung gian xuất hiện ngay trong phép cộng. Nó có thể phá tính kết hợp và tạo khác biệt giữa các cách thực thi. Đối với quy tắc **cộng chính xác rồi làm tròn một lần**, không truyền `MathContext` vào accumulator.

Nếu một thuật toán chuyên biệt buộc phải tính với precision hữu hạn, phải thiết kế rõ điều kiện sai số, phép kết hợp và thứ tự thực thi; không suy rằng `reduce` song song vẫn luôn cho cùng kết quả.

## 8. Chia và tính tỷ lệ: chọn điểm làm tròn riêng

Phép `add` và `multiply` không dùng `MathContext` hoạt động chính xác trên các giá trị thập phân hữu hạn. Ngược lại, phép chia có thể cho khai triển thập phân vô hạn, ví dụ `1 / 3`.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

// one.divide(three); // ArithmeticException vì kết quả không hữu hạn.
BigDecimal ratio = one.divide(three, 4, RoundingMode.HALF_EVEN);

System.out.println(ratio); // 0.3333
~~~

Khi cần tỷ lệ, hãy phân biệt **độ chính xác nội bộ** với **scale cuối cùng của tiền**. Ví dụ khoản thuế được tính bằng 7,5% của tổng trước thuế:

~~~java
BigDecimal subtotal = new BigDecimal("19.99");
BigDecimal taxRate = new BigDecimal("0.075");

BigDecimal exactTax = subtotal.multiply(taxRate); // 1.49925
BigDecimal tax = exactTax.setScale(2, RoundingMode.HALF_UP);

System.out.println(tax); // 1.50
~~~

Ở đây phép nhân giữ đầy đủ phần thập phân, còn quy định làm tròn thuế ở cấp hóa đơn được áp dụng sau đó. Một hệ thống khác có thể quy định thuế làm tròn theo từng dòng hoặc tại một bước khác. Chính sách đó phải được mô tả và kiểm thử riêng.

Khi tính bình quân, nên cộng chính xác trước, rồi chia với scale/rounding đã thống nhất:

~~~java
import java.util.List;

List<BigDecimal> prices = List.of(
        new BigDecimal("10.00"),
        new BigDecimal("10.01"),
        new BigDecimal("10.02")
);

BigDecimal total = prices.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

BigDecimal average = total.divide(
        BigDecimal.valueOf(prices.size()), 2, RoundingMode.HALF_UP);

System.out.println(average); // 10.01
~~~

Cần xử lý danh sách rỗng trước khi chia để tránh chia cho 0. `Collectors.averagingDouble` không phải lựa chọn thích hợp nếu nghiệp vụ yêu cầu giữ kết quả dựa trên `BigDecimal` chính xác.

## 9. reduce hai đối số, một đối số và ba đối số

### 9.1. Có identity: `reduce(BigDecimal.ZERO, BigDecimal::add)`

~~~java
BigDecimal total = prices.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

- Trả trực tiếp `BigDecimal`.
- Với Stream rỗng, trả `BigDecimal.ZERO`.
- Dùng đúng identity của phép cộng và phép cộng chính xác để hỗ trợ chia nhỏ/ghép các phần tử.

### 9.2. Không có identity: `reduce(BigDecimal::add)`

~~~java
import java.util.Optional;

Optional<BigDecimal> maybeTotal = prices.stream()
        .reduce(BigDecimal::add);

BigDecimal totalOrZero = maybeTotal.orElse(BigDecimal.ZERO);
~~~

Overload này trả `Optional<BigDecimal>` vì Stream có thể rỗng. Nó phù hợp nếu **“không có dữ liệu”** phải được phân biệt với **“tổng bằng 0”**. Việc chọn một trong hai tùy theo hợp đồng của ứng dụng.

### 9.3. Ba đối số: identity, accumulator, combiner

Overload dạng:

~~~java
<U> U reduce(
        U identity,
        java.util.function.BiFunction<U, ? super T, U> accumulator,
        java.util.function.BinaryOperator<U> combiner)
~~~

Chẳng hạn nguồn Stream là các `Line`, còn kết quả giảm là `BigDecimal`:

~~~java
BigDecimal total = lines.parallelStream()
        .reduce(
                BigDecimal.ZERO,
                (sum, line) -> sum.add(
                        line.unitPrice().multiply(
                                BigDecimal.valueOf(line.quantity()))),
                BigDecimal::add
        );

BigDecimal payable = total.setScale(2, RoundingMode.HALF_UP);
~~~

Accumulator cộng thành tiền của một dòng vào kết quả trung gian; combiner cộng chính xác hai tổng trung gian. Cả hai tuân thủ việc giữ identity và tính kết hợp cần thiết. Tuy nhiên, ví dụ này thường dễ đọc hơn khi tách `map` và `reduce`:

~~~java
BigDecimal total = lines.parallelStream()
        .map(line -> line.unitPrice()
                .multiply(BigDecimal.valueOf(line.quantity())))
        .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

**Tránh dùng một `BigDecimal[]`, `AtomicReference<BigDecimal>` hoặc một accumulator mutable dùng chung** để cộng trong `forEach` của parallel stream. `BigDecimal` là immutable; dùng `reduce` với phép cộng chính xác phù hợp hơn với cách kết hợp các kết quả từ nhiều tác vụ.

## 10. Tổng hợp theo nhóm trước khi làm tròn

Với báo cáo theo hóa đơn, tài khoản hoặc khách hàng, cần phân biệt tổng **từng nhóm** và tổng **tất cả dữ liệu**. Nếu quy tắc nghiệp vụ nói “làm tròn trên mỗi hóa đơn”, ta phải nhóm theo hóa đơn, cộng chính xác trong từng nhóm, sau đó làm tròn từng tổng.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Charge(String invoiceId, BigDecimal amount) {}

List<Charge> charges = List.of(
        new Charge("INV-1", new BigDecimal("0.005")),
        new Charge("INV-1", new BigDecimal("0.005")),
        new Charge("INV-2", new BigDecimal("0.005"))
);

Map<String, BigDecimal> exactByInvoice = charges.stream()
        .collect(Collectors.groupingBy(
                Charge::invoiceId,
                Collectors.reducing(
                        BigDecimal.ZERO,
                        Charge::amount,
                        BigDecimal::add
                )
        ));

Map<String, BigDecimal> roundedByInvoice = exactByInvoice.entrySet()
        .stream()
        .collect(Collectors.toMap(
                entry -> entry.getKey(),
                entry -> entry.getValue()
                        .setScale(2, RoundingMode.HALF_UP)
        ));

System.out.println(roundedByInvoice.get("INV-1")); // 0.01
System.out.println(roundedByInvoice.get("INV-2")); // 0.01
~~~

Tổng các khoản **sau khi chốt từng hóa đơn** là `0.01 + 0.01 = 0.02`. Nếu đem **mọi khoản trước khi làm tròn** cộng lại rồi làm tròn một lần, `0.015` trở thành `0.02` trong ví dụ này. Hai con số tình cờ bằng nhau, nhưng phương pháp không tương đương tổng quát. Để thấy sự khác biệt, xét ba hóa đơn, mỗi hóa đơn có một khoản `0.005`:

~~~text
Làm tròn mỗi hóa đơn:  0.01 + 0.01 + 0.01 = 0.03
Cộng toàn bộ rồi tròn: round(0.005 + 0.005 + 0.005) = 0.02
~~~

**Ranh giới nhóm là một phần của chính sách làm tròn.** Không được “tối ưu” bằng cách gộp nhiều nhóm thành một tổng rồi làm tròn nếu hợp đồng đòi chốt từng nhóm riêng.

Nếu một hóa đơn không có khoản nào, `groupingBy` trên Stream các `Charge` sẽ không tự sinh khóa cho hóa đơn đó. Cần lấy danh sách hóa đơn gốc để bổ sung giá trị `0.00` theo yêu cầu, hoặc tổng hợp trực tiếp trên từng đối tượng hóa đơn.

## 11. BigDecimal bất biến, scale và phép so sánh

### 11.1. add không thay đổi đối tượng gốc

~~~java
BigDecimal total = BigDecimal.ZERO;
total.add(new BigDecimal("10.50"));

System.out.println(total); // 0
~~~

`BigDecimal` là immutable. `add` trả về một đối tượng kết quả; lời gọi không làm thay đổi `total`. Cách đúng:

~~~java
total = total.add(new BigDecimal("10.50"));
System.out.println(total); // 10.50
~~~

Đó cũng là lý do `reduce(BigDecimal.ZERO, BigDecimal::add)` không cần biến tổng mutable dùng chung.

### 11.2. equals xét cả giá trị và scale

~~~java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.equals(b));           // false
System.out.println(a.compareTo(b) == 0);   // true
~~~

`equals` yêu cầu cả giá trị lẫn scale khớp nhau. `compareTo` dùng thứ tự theo giá trị số học nên hai số trên được xem là bằng nhau. Trong kiểm thử tổng số tiền, nếu hợp đồng yêu cầu đúng scale hai chữ số, hãy kiểm tra cả scale hoặc chuẩn hóa trước:

~~~java
BigDecimal actual = new BigDecimal("2.0")
        .setScale(2, RoundingMode.UNNECESSARY);

System.out.println(actual.equals(new BigDecimal("2.00"))); // true
~~~

`RoundingMode.UNNECESSARY` từ chối dữ liệu phải bỏ chữ số có nghĩa để đạt scale mới:

~~~java
new BigDecimal("2.001")
        .setScale(2, RoundingMode.UNNECESSARY);
// ArithmeticException: rounding necessary
~~~

Chế độ này hữu ích để **xác nhận** một khoản đã được lưu đúng đơn vị nhỏ nhất mà nghiệp vụ cho phép, thay vì âm thầm làm tròn khoản đó.

### 11.3. Scale của đầu vào không phải lúc nào cũng giống scale của tổng

~~~java
BigDecimal total = new BigDecimal("1.2")
        .add(new BigDecimal("2.345"));

System.out.println(total);         // 3.545
System.out.println(total.scale()); // 3
~~~

Khi định dạng cho thanh toán, dùng `setScale` ở bước nghiệp vụ thích hợp. Không nên dựa vào số chữ số hiển thị sẵn của dữ liệu đầu vào để suy ra tổng đã đáp ứng chính sách làm tròn.

## 12. Kiểm tra dữ liệu và những rủi ro khi xử lý thực tế

| Rủi ro | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Khởi tạo tiền từ `new BigDecimal(double)` | Mang theo xấp xỉ nhị phân của `double` | Nhận chuỗi thập phân chính xác; dùng `BigDecimal.valueOf` nếu phải chuyển từ `double` đã có. |
| Dùng `doubleValue()` trước khi `reduce` | Mất tính chính xác thập phân | Duy trì dữ liệu dạng `BigDecimal` qua mọi phép tính tiền. |
| Làm tròn sau từng `add` | Kết quả phụ thuộc thứ tự nhóm, sai khi parallel | Cộng chính xác trước; làm tròn một lần tại ranh giới nghiệp vụ. |
| Dùng `MathContext(2, ...)` để biểu diễn hai chữ số thập phân | Nhầm precision với scale | Dùng `setScale(2, mode)` ở điểm phù hợp. |
| Không có rounding mode khi chia số thập phân vô hạn | `ArithmeticException` | Chỉ rõ scale, mode hoặc precision theo quy tắc nghiệp vụ. |
| Giả định `BigDecimal.equals` kiểm tra bằng nhau về số học | Hai khoản `2.0` và `2.00` bị xem là khác | Dùng `compareTo` khi chỉ cần so giá trị, hoặc chuẩn hóa scale khi hợp đồng yêu cầu. |
| Có giá trị `null` trong nguồn | `NullPointerException` ở `add` hoặc `multiply` | Kiểm tra dữ liệu đầu vào; quyết định từ chối, thay bằng 0 hoặc loại bỏ theo chính sách rõ ràng. |
| Dùng chung một biến mutable trong parallel stream | Race condition, kết quả không ổn định | Dùng reduction không chia sẻ trạng thái, với accumulator/combiner đúng hợp đồng. |
| Làm tròn cấp hóa đơn nhưng cộng nhiều hóa đơn rồi mới tròn | Tổng sai theo ranh giới chốt sổ | Nhóm và làm tròn riêng từng hóa đơn trước khi cộng kết quả đã chốt. |
| Dữ liệu hoặc số lượng quá lớn | Chi phí CPU, bộ nhớ và thời gian tăng | Đánh giá độ lớn, chọn phân lô/nhóm phù hợp, kiểm soát tài nguyên và đo hiệu năng. |

Với pipeline lấy dữ liệu từ cơ sở dữ liệu, file hoặc API, không nên giả định dữ liệu đầu vào lúc nào cũng đầy đủ, đúng thứ tự và đã được chuẩn hóa. `Stream` duyệt dữ liệu theo nguồn; các lambda nên tránh sửa dữ liệu nguồn trong khi duyệt. Nếu cần snapshot kế toán, hãy bảo đảm đầu vào ổn định trong suốt lượt tổng hợp.

## 13. Kiểm thử chính sách làm tròn có thể tái lập

Nên đặt các tình huống biên thành ca kiểm thử độc lập. Dưới đây là bảng kỳ vọng khi chính sách là **tổng chính xác, làm tròn cuối bằng `setScale(2, HALF_UP)`**:

| Dữ liệu đầu vào | Tổng chính xác | Kết quả đã làm tròn |
| --- | ---: | ---: |
| `0.005`, `0.005`, `0.005` | 0.015 | 0.02 |
| `2.345` | 2.345 | 2.35 |
| `-2.345` | -2.345 | -2.35 |
| `10.001`, `-10.001` | 0.000 | 0.00 |
| Không có phần tử | 0 | 0.00 |
| `1.20`, `2.30` | 3.50 | 3.50 |

Một phương thức thuần nhỏ dễ kiểm thử:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Collection;

static BigDecimal sumAsMoney(Collection<BigDecimal> amounts) {
    BigDecimal exact = amounts.stream()
            .reduce(BigDecimal.ZERO, BigDecimal::add);

    return exact.setScale(2, RoundingMode.HALF_UP);
}
~~~

Các kiểm thử có thể so sánh `BigDecimal` bằng `equals` khi **scale cũng là một phần của hợp đồng**:

~~~java
import java.util.List;

BigDecimal result = sumAsMoney(List.of(
        new BigDecimal("0.005"),
        new BigDecimal("0.005"),
        new BigDecimal("0.005")
));

if (!result.equals(new BigDecimal("0.02"))) {
    throw new AssertionError("Expected 0.02 but got " + result);
}
~~~

Đừng chỉ kiểm thử giá trị “đẹp” như `10.00 + 20.00`; những trường hợp đúng điểm giữa, dữ liệu âm, danh sách rỗng và nhiều nhóm mới dễ bộc lộ khác biệt về chính sách làm tròn.

## 14. Bài tập tự kiểm tra

**Bài 1.** Dự đoán hai kết quả khi sử dụng `HALF_UP` với scale 2:

~~~java
List<BigDecimal> amounts = List.of(
        new BigDecimal("0.005"),
        new BigDecimal("0.005"),
        new BigDecimal("0.005")
);

BigDecimal a = amounts.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add)
        .setScale(2, RoundingMode.HALF_UP);

BigDecimal b = amounts.stream()
        .map(x -> x.setScale(2, RoundingMode.HALF_UP))
        .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

**Đáp án:** `a = 0.02` và `b = 0.03`. Mỗi dòng làm tròn độc lập rồi cộng không tương đương với cộng chính xác toàn bộ rồi làm tròn một lần.

**Bài 2.** Vì sao không nên dùng accumulator bên dưới với `parallelStream()`?

~~~java
BigDecimal result = amounts.parallelStream()
        .reduce(BigDecimal.ZERO, (sum, x) ->
                sum.add(x).setScale(2, RoundingMode.HALF_UP));
~~~

**Đáp án:** Hàm kết hợp làm tròn mỗi bước nên không còn bảo đảm tính kết hợp và identity cho các giá trị chưa chốt. Parallel reduction có thể nhóm các phần tử khác với duyệt tuần tự, làm thay đổi kết quả. Thay bằng `reduce(BigDecimal.ZERO, BigDecimal::add)` rồi `setScale(...)` trên tổng cuối.

**Bài 3.** Kết quả của hai biểu thức sau có giống nhau không?

~~~java
BigDecimal x = new BigDecimal("123.456");

BigDecimal a = x.setScale(2, RoundingMode.HALF_UP);
BigDecimal b = x.round(new MathContext(2, RoundingMode.HALF_UP));
~~~

**Đáp án:** Không. `a = 123.46` giữ hai chữ số sau dấu thập phân; `b = 1.2E+2` (giá trị số học 120) giữ hai chữ số có nghĩa. Precision và scale đo hai đặc tính khác nhau.

**Bài 4.** Chọn cách xử lý chính xác khi đầu vào có một khoản `1/3`.

**Đáp án:** Phải xác định quy tắc chia và làm tròn, chẳng hạn `BigDecimal.ONE.divide(new BigDecimal("3"), 4, RoundingMode.HALF_EVEN)` cho kết quả `0.3333`. Không gọi `divide` không tham số với một thương thập phân vô hạn, vì phép đó ném `ArithmeticException`.

**Bài 5.** Một công ty phải làm tròn **mỗi hóa đơn** trước khi cộng doanh thu. Có thể cộng toàn bộ dòng hàng của mọi hóa đơn rồi làm tròn một lần không?

**Đáp án:** Không. Cần gom theo mã hóa đơn, tính tổng chính xác trong từng nhóm, làm tròn tổng từng nhóm, rồi mới cộng các kết quả đã chốt. Quy tắc làm tròn ở **cấp hóa đơn** khác quy tắc làm tròn ở **cấp toàn công ty**.

## 15. Ghi nhớ

- Dùng `BigDecimal` từ dữ liệu thập phân chính xác, thường là chuỗi, khi cần tổng hợp tiền hoặc số liệu đòi hỏi kết quả thập phân rõ ràng.
- Mẫu mặc định cho phép cộng chính xác là `stream.map(...).reduce(BigDecimal.ZERO, BigDecimal::add)`.
- Chỉ áp dụng `setScale(scale, roundingMode)` tại **điểm chốt nghiệp vụ** đã được quy định. Cần tách bạch làm tròn từng dòng, từng hóa đơn và toàn bộ báo cáo.
- Không làm tròn trong accumulator hoặc combiner nếu muốn reduction bảo đảm tính kết hợp và an toàn khi chia nhóm/parallel.
- `MathContext` điều khiển chữ số **có nghĩa**; `setScale` điều khiển chữ số **sau dấu thập phân**.
- Dùng `compareTo` để so sánh giá trị số học; dùng `equals` khi cả scale lẫn giá trị phải khớp. Xử lý riêng trường hợp rỗng, số âm, `null` và phép chia vô hạn.

**Ý chính:** Với tổng hợp `BigDecimal` bằng `reduce`, hãy **xác định chính sách làm tròn trước, cộng chính xác trong pipeline, rồi làm tròn tại đúng ranh giới nghiệp vụ**. Cách này giúp kết quả dễ giải thích, dễ kiểm thử và giữ được các thuộc tính cần thiết khi xử lý dữ liệu khai báo hoặc chia công việc cho parallel stream.
