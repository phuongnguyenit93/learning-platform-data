# BigDecimal: tính nhiều bước và lựa chọn thời điểm làm tròn

## 1. Vấn đề: cùng phép toán, kết quả cuối có thể khác nhau

Trong quy trình nhân đơn giá với số lượng, giảm giá, tính thuế, quy đổi, chia tiền hay tính lãi nhiều kỳ, **thời điểm làm tròn là quy tắc nghiệp vụ**. Làm tròn mọi kết quả trung gian và chỉ làm tròn tổng cuối là hai chính sách khác nhau, kể cả khi cùng dùng `BigDecimal`, cùng scale và cùng `RoundingMode`.

Ví dụ có ba khoản, mỗi khoản có giá trị gốc `0.335`, kết quả cần hai chữ số sau dấu thập phân và dùng `HALF_UP`:

- **Chốt từng khoản rồi cộng:** `0.335 → 0.34`; tổng `0.34 × 3 = 1.02`.
- **Cộng số gốc rồi chốt:** `0.335 × 3 = 1.005`; tổng `1.005 → 1.01`.

Chênh lệch `0.01` không phải lỗi của Java. Cần xác định tiền được ghi nhận theo từng dòng, theo tổng hóa đơn hay theo cơ sở tính thuế/lãi được quy định. Mục tiêu bài này là biết **giữ độ chính xác khi cần**, **làm tròn đúng ranh giới**, **chọn precision/scale/mode phù hợp** và **đối soát tổng sau khi phân bổ**.

## 2. Scale, precision, MathContext và tính chính xác

`BigDecimal` biểu diễn một số bằng `unscaledValue × 10^(-scale)`. Với `new BigDecimal("123.450")`, `scale() == 3` và `precision() == 6`.

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| `scale` | Số chữ số bên phải dấu thập phân; có thể âm | `123.450` có scale 3 |
| `precision` | Tổng số chữ số có nghĩa của giá trị | `123.450` có precision 6 |
| `setScale(2, mode)` | Chốt còn hai chữ số thập phân; có thể làm tròn | `123.456 → 123.46` với `HALF_UP` |
| `round(new MathContext(5, mode))` | Chốt còn tối đa năm chữ số có nghĩa | `1234.56789 → 1234.6` với `HALF_EVEN` |

`new MathContext(5)` **không có nghĩa là năm chữ số sau dấu thập phân**. MathContext kiểm soát precision kết quả; `setScale` kiểm soát scale kết quả.

Các overload `add`, `subtract`, `multiply` **không truyền MathContext** thường giữ kết quả toán học chính xác trong biểu diễn thập phân, trong giới hạn tài nguyên và phạm vi scale được hỗ trợ. Với `multiply`, scale kết quả thường bằng tổng scale hai toán hạng; với `add`/`subtract`, scale thường bằng scale lớn hơn của hai toán hạng. Điều này không có nghĩa kết quả đã được chốt theo đơn vị tiền tệ.

**Khởi tạo dữ liệu thập phân đúng:**

~~~java
BigDecimal unitPrice = new BigDecimal("19.995");
BigDecimal discountRate = new BigDecimal("0.075");
BigDecimal quantity = BigDecimal.valueOf(3L);
~~~

Tránh `new BigDecimal(0.1)` nếu ý định là giá trị thập phân chính xác `0.1`: `double` đã chứa gần đúng nhị phân. `BigDecimal.valueOf(0.1)` lấy biểu diễn thập phân từ `Double.toString` và thường dễ dùng hơn constructor nhận `double`, nhưng **không khôi phục sai số do phép tính double xảy ra trước khi chuyển đổi**. Với tiền và tỷ lệ cố định, ưu tiên `String`, số nguyên đơn vị nhỏ hoặc dữ liệu thập phân được parse đúng định dạng.

`BigDecimal` là immutable: `a.add(b)`, `a.setScale(...)` và `a.round(...)` trả kết quả mới, không thay đổi `a`. Phải gán và sử dụng giá trị trả về.

## 3. Ví dụ nhiều bước: làm tròn cuối và làm tròn mỗi khoản

Giả sử đơn giá `19.995`, số lượng `3`, giảm giá `7.5%`, thuế `8%` trên giá trị sau giảm. Số tiền thanh toán cuối cùng được chốt tới hai chữ số thập phân theo `HALF_UP`. Đây là **mô hình minh họa**, không xác lập chính sách thuế hay định giá của bất kỳ quốc gia nào.

**A — chỉ chốt tổng cuối:**

1. Gốc: `19.995 × 3 = 59.985`.
2. Chiết khấu: `59.985 × 0.075 = 4.498875`.
3. Giá trị chịu thuế: `59.985 - 4.498875 = 55.486125`.
4. Thuế: `55.486125 × 0.08 = 4.43889000`.
5. Tổng gốc `55.486125 + 4.43889000 = 59.92501500`, làm tròn thành **59.93**.

**B — chốt đơn giá và các khoản khi ghi nhận:**

1. Đơn giá `19.995 → 20.00`; giá trị gốc `20.00 × 3 = 60.00`.
2. Chiết khấu `60.00 × 0.075 = 4.50000 → 4.50`.
3. Giá trị chịu thuế `60.00 - 4.50 = 55.50`.
4. Thuế `55.50 × 0.08 = 4.4400 → 4.44`.
5. Tổng đã chốt **59.94**.

Hai cách lệch `0.01`. Nếu đầu vào đơn giá bắt buộc hai chữ số thì đó là chính sách xác thực/chốt đơn giá, không được lẫn với việc làm tròn tùy ý tại tầng xử lý.

### Chương trình Java 17+ hoàn chỉnh

Lưu thành `RoundingPipelineDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class RoundingPipelineDemo {
    private static final RoundingMode MODE = RoundingMode.HALF_UP;

    private static BigDecimal money(BigDecimal value) {
        return value.setScale(2, MODE);
    }

    public static void main(String[] args) {
        BigDecimal unitPrice = new BigDecimal("19.995");
        BigDecimal quantity = new BigDecimal("3");
        BigDecimal discountRate = new BigDecimal("0.075");
        BigDecimal taxRate = new BigDecimal("0.08");

        // A: Dùng giá trị trung gian chính xác, chốt tổng cuối.
        BigDecimal gross = unitPrice.multiply(quantity);
        BigDecimal discount = gross.multiply(discountRate);
        BigDecimal taxable = gross.subtract(discount);
        BigDecimal tax = taxable.multiply(taxRate);
        BigDecimal finalOnly = money(taxable.add(tax));

        // B: Chốt đơn giá, chiết khấu và thuế ở từng bước.
        BigDecimal grossEarly = money(unitPrice).multiply(quantity);
        BigDecimal discountEarly = money(grossEarly.multiply(discountRate));
        BigDecimal taxableEarly = grossEarly.subtract(discountEarly);
        BigDecimal taxEarly = money(taxableEarly.multiply(taxRate));
        BigDecimal eachStep = money(taxableEarly.add(taxEarly));

        System.out.println("final only = " + finalOnly);
        System.out.println("each step  = " + eachStep);
        System.out.println("difference = " + eachStep.subtract(finalOnly));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac RoundingPipelineDemo.java
java RoundingPipelineDemo
~~~

Stdout:

~~~text
final only = 59.93
each step  = 59.94
difference = 0.01
~~~

Hàm `money` thể hiện thao tác **chốt số tiền**. Đừng thêm `setScale(2, ...)` ở một bước chỉ vì kết quả sau cùng là tiền. Mọi điểm chốt phải được chỉ rõ trong đặc tả nghiệp vụ.

## 4. Quyết định thời điểm làm tròn theo ranh giới nghiệp vụ

| Bước thực tế | Câu hỏi phải trả lời | Ảnh hưởng |
|---|---|---|
| Nhân đơn giá với số lượng | Đơn giá được phép có bao nhiêu chữ số? Chốt trước hay sau khi nhân? | Làm tròn đơn giá có thể khuếch đại chênh lệch theo số lượng |
| Tính nhiều dòng hóa đơn | Tổng dòng đã chốt hay tổng giá trị gốc mới là cơ sở tính? | Tổng các dòng đã hiển thị có thể khác tổng tính toán |
| Chiết khấu/thuế | Chốt riêng theo dòng, theo loại thuế hay toàn hóa đơn? | Ảnh hưởng cơ sở tính và kết quả cuối |
| Tiền lãi nhiều kỳ | Lãi kỳ trước nhập vào gốc ngay hay giữ chưa chốt? | Ảnh hưởng lãi kép và đối soát |
| Quy đổi ngoại tệ | Độ chính xác tỷ giá và thời điểm chốt theo loại tiền đích? | Sai lệch khi tỷ giá được làm tròn sớm |
| Phân bổ tiền | Đơn vị nhỏ nhất có thể chuyển/ghi sổ là bao nhiêu? | Cần phân bổ phần dư để tổng các khoản bằng tổng cần chia |
| Hiển thị báo cáo | Làm tròn chỉ để xem, hay số đó đã được ghi sổ? | Không được để hiển thị tự ý thay đổi dữ liệu giao dịch |

Một thiết kế rõ nghĩa phân biệt **input → phép tính chưa chốt → điểm chốt/giao dịch → hiển thị**. Một số tiền đã ghi sổ thường phải tiếp tục tham gia quy trình bằng **giá trị đã chốt** nếu hợp đồng/ledger yêu cầu; giữ số thô để phục vụ kiểm toán không có nghĩa được dùng số thô thay số đã ghi sổ. Ngược lại, báo cáo chỉ định dạng số để đọc không nên âm thầm làm tròn và ghi ngược lại nguồn.

Cần mô tả riêng scale của đơn giá, scale của tỷ lệ, scale nội bộ của phép chia, scale khi chốt và scale hiển thị. Chúng không nhất thiết giống nhau. Với pháp luật thuế/lãi, phải tuân thủ quy định áp dụng; không có một mode duy nhất đúng cho mọi lĩnh vực.

## 5. Double rounding: làm tròn hai lần có thể sai khác một lần

~~~java
BigDecimal x = new BigDecimal("2.345");
BigDecimal twice = x.setScale(2, RoundingMode.HALF_UP)
                    .setScale(1, RoundingMode.HALF_UP);
BigDecimal once = x.setScale(1, RoundingMode.HALF_UP);

System.out.println(twice); // 2.4
System.out.println(once);  // 2.3
~~~

Làm tròn hai lần: `2.345 → 2.35 → 2.4`. Làm tròn trực tiếp tới một chữ số: `2.345 → 2.3`. Không có định luật nói `round(round(x))` luôn bằng `round(x)` khi chính sách/scale hai lần khác nhau. Làm tròn trước phép nhân cũng gây mất mát: `19.995` thành `20.00`, nhân `3` thành `60.00`, không thể suy lại thành `59.985`.

**Giải pháp:** giữ số trung gian đủ chính xác, chỉ chốt ở ranh giới được quy định; nếu buộc phải chốt hai lần thì coi đó là hai giao dịch đã chốt, không cố “làm tròn bù” để giả vờ kết quả như tính một lần.

## 6. Phép chia: bắt buộc quản lý trường hợp vô hạn

`BigDecimal.divide(divisor)` không có chế độ làm tròn chỉ thành công khi thương có biểu diễn thập phân hữu hạn. Ví dụ `1 / 8 = 0.125` thành công, nhưng `1 / 3` có biểu diễn vô hạn và ném `ArithmeticException`. Chia cho 0 cũng ném `ArithmeticException`.

~~~java
BigDecimal one = new BigDecimal("1");
BigDecimal three = new BigDecimal("3");

// one.divide(three); // ArithmeticException vì thương vô hạn.

BigDecimal byScale = one.divide(three, 6, RoundingMode.HALF_EVEN);
BigDecimal byPrecision = one.divide(
        three, new MathContext(6, RoundingMode.HALF_EVEN));

System.out.println(byScale);     // 0.333333
System.out.println(byPrecision); // 0.333333
~~~

Hai kết quả này giống nhau **riêng với 1/3**. Scale 6 nghĩa là sáu chữ số sau dấu thập phân; precision 6 là sáu chữ số có nghĩa. Thí dụ thương của `12345/7` sẽ có cách biểu diễn khác nhau dưới hai quy tắc.

Cẩn thận với overload `divide(BigDecimal divisor, RoundingMode mode)`: nó lấy **scale kết quả từ scale của số bị chia**. Đây là lỗi dễ bị bỏ qua:

~~~java
System.out.println(new BigDecimal("1")
        .divide(new BigDecimal("3"), RoundingMode.HALF_UP)); // 0
System.out.println(new BigDecimal("1.00")
        .divide(new BigDecimal("3"), RoundingMode.HALF_UP)); // 0.33
~~~

Khi cần scale cố định, dùng `divide(divisor, scale, mode)`; khi cần số chữ số có nghĩa, dùng `divide(divisor, mc)`. `MathContext.UNLIMITED` có precision 0, yêu cầu phép toán chính xác và **không thể biến thương 1/3 thành hữu hạn**. Không được tùy tiện dùng một precision rồi khẳng định có kết quả toán học chính xác tuyệt đối.

## 7. MathContext trên từng bước khác chốt tổng cuối

Một `MathContext` có precision hữu hạn sẽ làm tròn **kết quả của mỗi phương thức được truyền context**. Ví dụ:

~~~java
BigDecimal x = new BigDecimal("1234.56789");
System.out.println(x.round(new MathContext(5, RoundingMode.HALF_EVEN)));
System.out.println(x.setScale(2, RoundingMode.HALF_EVEN));
~~~

Stdout:

~~~text
1234.6
1234.57
~~~

Do đó `a.multiply(b, mc).divide(c, mc).add(d, mc)` có thể làm tròn ở ba bước. Nó không có nghĩa là tính chính xác ba bước rồi làm tròn một lần. Khi làm tròn ở mỗi bước, đổi thứ tự cộng/gom nhóm cũng có thể đổi kết quả.

Gợi ý lựa chọn:

1. Với `add`, `subtract`, `multiply` thập phân hữu hạn, giữ kết quả chính xác nếu nghiệp vụ và tài nguyên cho phép.
2. Với phép chia vô hạn, căn bậc hai hoặc thuật toán lặp, chọn working precision theo độ chính xác đầu ra cần đạt và mức độ tích lũy sai số.
3. Giữ chữ số dự phòng (guard digits) nếu còn nhiều bước. **Không có số guard digits cố định đảm bảo mọi công thức chính xác**.
4. Chỉ chốt bằng `setScale` ở ranh giới đã xác định. Nếu nghiệp vụ yêu cầu chốt từng kỳ, từng khoản, làm đúng các lần chốt đó.
5. Muốn cam kết sai số tối đa, phải phân tích công thức và thứ tự tính, không chỉ đặt precision lớn một cách cảm tính.

Một lần làm tròn theo mode gần nhất tới scale 2 có sai số tuyệt đối tối đa `0.005` đơn vị so với **giá trị ngay trước lần làm tròn đó**. Nếu làm tròn `n` dòng rồi cộng, sai lệch có thể tích lũy; nhân/chia sau đó có thể làm sai số biến đổi thêm. Không áp dụng ngưỡng một bước cho toàn quy trình khi chưa phân tích các bước sau.

## 8. Chọn RoundingMode kể cả với số âm

| Mode | Hướng làm tròn | Ví dụ scale 2 |
|---|---|---|
| `HALF_UP` | Gần nhất, điểm giữa ra xa 0 | `2.345 → 2.35`; `-2.345 → -2.35` |
| `HALF_EVEN` | Gần nhất, điểm giữa giữ chữ số cuối chẵn | `2.345 → 2.34`; `2.355 → 2.36` |
| `DOWN` | Về 0 (không đồng nghĩa luôn nhỏ hơn) | `-2.349 → -2.34` |
| `UP` | Ra xa 0 nếu có chữ số bị bỏ | `-2.341 → -2.35` |
| `FLOOR` | Về âm vô cực | `-2.341 → -2.35` |
| `CEILING` | Về dương vô cực | `-2.341 → -2.34` |
| `UNNECESSARY` | Cấm làm tròn làm mất thông tin; ném lỗi nếu cần | `2.340 → 2.34`, `2.345 → lỗi` |

`HALF_EVEN` có thể giảm thiên lệch khi làm tròn nhiều giá trị rơi đúng điểm giữa; `HALF_UP` quen thuộc trong nhiều quy tắc tiền tệ. Nhưng cả hai đều **phải theo chính sách đã được xác định**, không tự suy ra từ một ví dụ. Đặc biệt kiểm tra số âm và chứng từ hoàn trả vì `DOWN` và `FLOOR` khác nhau.

`UNNECESSARY` là cách kiểm tra số đã hợp lệ tại scale yêu cầu:

~~~java
new BigDecimal("12.340").setScale(2, RoundingMode.UNNECESSARY); // 12.34
// new BigDecimal("12.345").setScale(2, RoundingMode.UNNECESSARY);
// ArithmeticException vì không thể giảm scale mà giữ nguyên giá trị.
~~~

## 9. Phân bổ phần dư khi chia số tiền đã chốt

Nếu phải chia `1.00` cho ba người, `1.00 / 3` chốt thành `0.33`; nhân ngược ba chỉ được `0.99`. Để **tổng các khoản bằng tổng phải chi**, cần có quy tắc phân bổ phần dư, thí dụ lấy phần cơ sở theo `DOWN` và phát các cent còn thừa theo thứ tự xác định.

Chương trình Java 17+ dưới đây áp dụng cho **số tiền không âm có tối đa hai chữ số sau dấu thập phân**, số người chia dương; lưu thành `AllocationDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;

public class AllocationDemo {
    static List<BigDecimal> allocate(BigDecimal amount, int recipients) {
        if (recipients <= 0 || amount.signum() < 0) {
            throw new IllegalArgumentException("recipients > 0, amount >= 0");
        }
        BigDecimal total = amount.setScale(2, RoundingMode.UNNECESSARY);
        BigDecimal divisor = BigDecimal.valueOf(recipients);
        BigDecimal base = total.divide(divisor, 2, RoundingMode.DOWN);
        int extraCents = total.subtract(base.multiply(divisor))
                .movePointRight(2).intValueExact();

        List<BigDecimal> shares = new ArrayList<>();
        for (int i = 0; i < recipients; i++) {
            shares.add(i < extraCents
                    ? base.add(new BigDecimal("0.01"))
                    : base);
        }
        return shares;
    }

    public static void main(String[] args) {
        List<BigDecimal> shares = allocate(new BigDecimal("1.00"), 3);
        BigDecimal sum = shares.stream()
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        System.out.println(shares);
        System.out.println(sum);
    }
}
~~~

Biên dịch bằng `javac AllocationDemo.java`, chạy `java AllocationDemo`:

~~~text
[0.34, 0.33, 0.33]
1.00
~~~

Quy tắc trên cho người đầu tiên nhận cent thừa. Trong nghiệp vụ thật, chọn thứ tự có thể cần công bằng theo thời gian, chia theo trọng số, lưu phương án phân bổ, xử lý số âm/hoàn tiền và scale khác 2 theo đơn vị tiền tệ. Bất biến cần giữ là **tổng phần đã phân bổ bằng chính xác tổng đã chốt**.

## 10. Tổ chức pipeline rõ ràng, kiểm toán được

Cần đặc tả trước khi viết công thức:

- **Đầu vào:** đơn vị tiền, precision đơn giá, scale tỷ giá/thuế suất, dạng lưu trữ thập phân, ràng buộc làm tròn sẵn.
- **Thứ tự tính:** áp giảm giá/thuế/phí vào cơ sở nào, tính theo dòng hay tổng, kỳ tính lãi, phép nhân/chia cần độ chính xác bao nhiêu.
- **Ranh giới chốt:** điểm nào bắt buộc chốt, scale và mode cụ thể cho từng loại khoản; giá trị chốt có trở thành đầu vào bước tiếp theo không.
- **Đối soát:** tổng dòng đã hiển thị có phải bằng tổng chứng từ không, phần dư hay điều chỉnh được ghi ở dòng nào.
- **Lưu vết:** giữ đầu vào, tỷ lệ, chính sách làm tròn và phiên bản quy tắc; không dùng `double` vô tình làm trung gian.
- **Hiển thị:** định dạng để xem không được tự ý ghi đè giá trị đã chốt.

Tên biến nên thể hiện ngữ nghĩa: `rawSubtotal`, `postedDiscount`, `taxableAmount`, `postedTax`, `settlementTotal`. Hàm `roundTaxLine(...)` hay `roundSettlement(...)` diễn đạt ý nghĩa rõ hơn một `setScale(2, HALF_UP)` đặt tùy ý. Quy tắc chưa rõ thì cần thống nhất với người quyết định nghiệp vụ; không chọn cách cho kết quả “trông đẹp hơn”.

**Lưu ý so sánh:** `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` trả `false` vì scale khác, trong khi `compareTo(...) == 0` là `true` vì giá trị số bằng nhau. Khi kiểm tra số tiền tính toán, cân nhắc `compareTo`; khi kiểm tra đúng chuẩn biểu diễn/scale, kiểm tra scale riêng hoặc sử dụng `equals` theo contract.

## 11. Kiểm thử các ranh giới và bất biến

1. **Điểm giữa và dấu:** kiểm thử `2.345`, `2.355`, `-2.345`, `0.005`, `0.0049`, với mode/scale nghiệp vụ.
2. **Điểm chốt:** ba khoản `0.335` dẫn tới `1.02` theo từng khoản hoặc `1.01` theo tổng. Ví dụ giảm giá/thuế trên phải cho `59.93` hoặc `59.94` đúng chính sách.
3. **Double rounding:** `2.345 → 2.35 → 2.4` khác `2.345 → 2.3`; phát hiện refactor đặt nhầm `setScale`.
4. **Chia:** `1/3` chính xác phải báo lỗi; chia theo scale/context ra kết quả đã định; chia cho 0 phải báo lỗi.
5. **Phân bổ:** thử `1.00 / 3`, `0.01 / 3`, `0.00 / 3` và tổng lớn; mỗi phần có scale hợp lệ, tổng phần bằng tổng trước chia.
6. **Dữ liệu biên:** giá trị âm, hoàn tiền, thuế suất 0, chiết khấu 100%, phép toán lặp dài, ngoại tệ với số chữ số nhỏ khác 2.
7. **Bất biến lưu trữ:** kiểm tra số đã chốt có được dùng làm đầu vào đúng ranh giới, phân biệt so sánh giá trị và so sánh scale.

Ví dụ kiểm tra kết quả của đoạn chương trình đầu, sau khi biến `finalOnly` được tính:

~~~java
if (finalOnly.compareTo(new BigDecimal("59.93")) != 0) {
    throw new AssertionError("Incorrect final rounding policy");
}
~~~

Chỉ kiểm thử một đầu ra tình cờ giống nhau không đủ chứng minh ranh giới làm tròn đúng. Nên chủ động chọn dữ liệu khiến hai cách làm tròn khác nhau, để kiểm thử bắt được việc di chuyển một phép `setScale`.

## 12. Lỗi phổ biến và bài tập

**Các lỗi cần tránh:** chốt mọi phép nhân vì “tiền có hai số lẻ”; nhầm `MathContext(2)` với `setScale(2)`; quên `divide` có thể ném lỗi vì thương vô hạn; gọi `divide(divisor, mode)` mà bỏ qua scale của số bị chia; làm tròn hai lần qua các tầng service/DTO; dùng `double` cho tỷ lệ mà không kiểm soát; giả định tổng từng phần đã làm tròn luôn bằng tổng làm tròn một lần; nhầm `DOWN` với `FLOOR` cho số âm; dùng `equals` khi chỉ cần bằng nhau về số học.

**Tự luyện:**

1. Bốn khoản `0.125`, `HALF_UP`, scale 2: chốt từng khoản rồi cộng bao nhiêu? Cộng số thô rồi chốt bao nhiêu?
2. Vì sao `new BigDecimal("1").divide(new BigDecimal("8"))` có kết quả còn `1/3` có thể ném lỗi?
3. Với `5.55`, `round(new MathContext(2, HALF_EVEN))` và `setScale(2, HALF_EVEN)` có giống nhau không?
4. Phân bổ `0.02` cho ba người như thế nào để tổng vẫn chính xác hai cent?

**Đáp án:** (1) `0.13 × 4 = 0.52`; cộng trước `0.125 × 4 = 0.500 → 0.50`. (2) `1/8 = 0.125` hữu hạn, `1/3` vô hạn. (3) Không: kết quả lần lượt `5.6` và `5.55`. (4) Với thứ tự cố định có thể là `[0.01, 0.01, 0.00]`.

### Checklist trước khi đưa pipeline vào sử dụng

Giá trị nào phải chính xác tuyệt đối? Bước nào cần xấp xỉ, scale hay precision nào là đủ? Điểm chốt nghiệp vụ ở đâu, mode nào áp dụng và cách xử lý số âm ra sao? Giá trị sau chốt có được dùng cho bước tiếp theo? Tổng sau phân bổ có khớp tổng cần ghi nhận? Có kiểm thử phân biệt chốt từng phần với chốt tổng không?

### Tài liệu chuẩn

- Java SE 17, `BigDecimal`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
- Java SE 17, `MathContext`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/MathContext.html
- Java SE 17, `RoundingMode`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html

**Nguyên tắc:** làm rõ số nào còn là giá trị trung gian, số nào đã được chốt và *chốt vì điều gì*; sau đó mới áp dụng `setScale`, `MathContext` và `RoundingMode` đúng với ranh giới đó.