# Làm tròn hai lần và khác biệt với làm tròn ở bước cuối

## 1. Vấn đề: cùng một dữ liệu, hai cách làm tròn có thể cho hai kết quả

Trong tính toán thập phân, **làm tròn hai lần** (*double rounding*) là tình huống một giá trị bị làm tròn ở một mức trung gian rồi lại làm tròn về mức cuối cùng. Kết quả **có thể khác** việc giữ nguyên các chữ số cần thiết và chỉ làm tròn một lần ở bước cuối.

Xét số thập phân chính xác `1.245`, cùng quy tắc `RoundingMode.HALF_UP`:

| Quy trình | Giá trị trung gian | Giá trị cuối |
| --- | --- | --- |
| Làm tròn hai lần: 3 → 2 → 1 chữ số sau dấu phẩy | `1.245 → 1.25` | `1.3` |
| Làm tròn trực tiếp: 3 → 1 chữ số sau dấu phẩy | Không có | `1.2` |

Lần làm tròn đầu tiên đã đổi `1.245` thành `1.25`, khiến lần làm tròn thứ hai nhìn thấy **một trường hợp đúng giữa** (`1.25` nằm giữa `1.2` và `1.3`). Trong khi đó, `1.245` thực sự gần `1.2` hơn `1.3`. Sai khác này đến từ thông tin bị mất ở bước trung gian, **không phải lỗi của `BigDecimal`**.

```java
BigDecimal value = new BigDecimal("1.245");
BigDecimal twice = value
        .setScale(2, RoundingMode.HALF_UP)
        .setScale(1, RoundingMode.HALF_UP);
BigDecimal once = value.setScale(1, RoundingMode.HALF_UP);

System.out.println(twice); // 1.3
System.out.println(once);  // 1.2
```

Các đoạn mã rời trong bài giả định đã import `java.math.BigDecimal` và `java.math.RoundingMode`. Phần chương trình hoàn chỉnh bên dưới có thể biên dịch và chạy độc lập với Java 17+.

## 2. Cơ chế toán học: sai khác xuất hiện ở đâu?

Ký hiệu `R_s(x)` là kết quả làm tròn `x` về **scale `s`**, với một `RoundingMode` nhất định. Hai phép xử lý cần so sánh là:

```text
Làm tròn trung gian: R_1(R_2(x))
Làm tròn một lần:   R_1(x)
```

Với `x = 1.245`, `HALF_UP`:

1. `R_2(1.245) = 1.25` vì bỏ chữ số 5 đúng giữa hai mức ở hàng phần trăm và `HALF_UP` làm tròn lên với số dương.
2. `R_1(1.25) = 1.3` vì `1.25` là điểm giữa `1.2` và `1.3`.
3. `R_1(1.245) = 1.2` vì giá trị ban đầu **nhỏ hơn** điểm giữa `1.25`; nó chưa đủ gần `1.3` để làm tròn lên.

Như vậy:

```text
R_1(R_2(1.245)) = 1.3
R_1(1.245)      = 1.2
```

Sai khác bằng `0.1` — một đơn vị ở độ chính xác đích, dù việc làm tròn trung gian chỉ thay đổi `1.245` một lượng `0.005`.

Điều cần ghi nhớ là **một giá trị vốn nằm sát ngưỡng làm tròn ở độ chính xác cuối** có thể bị đẩy tới hoặc vượt ngưỡng vì một bước làm tròn trước đó. Không phải mọi giá trị đều gặp tình huống này, nhưng không thể bảo đảm hai quy trình luôn tương đương chỉ vì dùng cùng `RoundingMode`.

### Vì sao “đúng giữa” quan trọng?

Với `HALF_UP` và kết quả một chữ số sau dấu phẩy, ngưỡng giữa `1.2` và `1.3` là `1.25`. Số `1.245` nằm **dưới ngưỡng** này. Làm tròn đến hai chữ số trước đã đẩy nó thành đúng `1.25`, khiến quyết định ở bước cuối thay đổi.

Trong thuật toán tính toán, một quy tắc làm tròn áp dụng hai lần không nhất thiết có tính chất:

```text
R_final(R_intermediate(x)) == R_final(x)
```

Nhất là với các chế độ làm tròn gần nhất như `HALF_UP`, `HALF_EVEN` và `HALF_DOWN`.

## 3. Với HALF_EVEN cũng có thể xảy ra khác biệt

`HALF_EVEN` chọn kết quả có chữ số cuối chẵn khi hai giá trị ứng viên cách điểm đầu vào đúng bằng nhau. Cách này thường được gọi là *banker's rounding*, nhưng **không miễn nhiễm với làm tròn hai lần**.

Xét `1.251`:

```java
BigDecimal x = new BigDecimal("1.251");
BigDecimal intermediate = x.setScale(2, RoundingMode.HALF_EVEN);
BigDecimal twice = intermediate.setScale(1, RoundingMode.HALF_EVEN);
BigDecimal once = x.setScale(1, RoundingMode.HALF_EVEN);

System.out.println(intermediate); // 1.25
System.out.println(twice);        // 1.2
System.out.println(once);         // 1.3
```

Giải thích:

- `1.251` về hai chữ số sau dấu phẩy là `1.25` vì gần `1.25` hơn `1.26`.
- `1.25` về một chữ số sau dấu phẩy tạo thế hòa giữa `1.2` và `1.3`; `HALF_EVEN` chọn `1.2` vì chữ số ở hàng phần mười là 2 (chẵn).
- `1.251` về trực tiếp một chữ số là `1.3` vì giá trị gốc lớn hơn điểm giữa `1.25`; trường hợp này **không hòa**, nên quy tắc chẵn không được sử dụng.

Vì thế việc chọn `HALF_EVEN` nhằm hạn chế thiên lệch trong nhiều phép làm tròn không đồng nghĩa với việc có thể làm tròn trung gian tùy ý.

## 4. Không phải hai lần làm tròn nào cũng cho kết quả khác

Ví dụ `1.234` với `HALF_UP`:

```text
1.234 → 1.23 → 1.2
1.234 ─────────→ 1.2
```

Hai đường cùng trả `1.2`. Sai khác phụ thuộc vào chữ số bị bỏ, vị trí ngưỡng, scale trung gian, scale cuối và chế độ làm tròn.

Khi chỉ liên tiếp **giảm scale trên cùng một số** bằng một chế độ làm tròn có hướng cố định (`DOWN` hướng về 0, `UP` xa 0, `FLOOR` hướng về âm vô cực, `CEILING` hướng về dương vô cực), kết quả hai lần khớp kết quả trực tiếp ở scale đích: các phép làm tròn theo hướng này không tạo tình huống “đúng giữa” mới làm đổi lựa chọn. Nhưng khi chèn **phép tính khác** giữa các lần làm tròn, hoặc thay đổi rounding mode, không được tự suy rộng kết luận đó.

Ngược lại, với các chế độ gần nhất như `HALF_UP` và `HALF_EVEN`, phải tính đến nguy cơ làm tròn hai lần ngay cả khi scale trung gian mịn hơn scale cuối.

Một cách nhìn hữu ích: nếu quy trình đưa từ `1.245` đến `1.25`, phần `0.005` đã mất không còn có thể được suy ra từ `1.25`. Lần làm tròn sau chỉ thấy số đã bị biến đổi.

## 5. Phân biệt làm tròn hai lần với làm tròn từng phần trước khi tổng hợp

Một nguồn sai khác thường gặp khác là **thứ tự làm tròn so với phép cộng hoặc nhân**. Dù không nhất thiết là cùng một số bị gọi `setScale()` hai lần, đó vẫn là cùng vấn đề thiết kế: **đặt phép làm tròn ở bước nào của phép tính**.

### 5.1. Cộng hai khoản nhỏ

Hai khoản chính xác là `0.006` và `0.006`. Nếu làm tròn từng khoản về hai chữ số bằng `HALF_UP` trước khi cộng:

```text
round(0.006, 2) + round(0.006, 2)
= 0.01 + 0.01
= 0.02
```

Nếu cộng ở độ chính xác gốc rồi làm tròn tổng một lần:

```text
round(0.006 + 0.006, 2)
= round(0.012, 2)
= 0.01
```

Kết quả chênh `0.01`. Nếu hợp đồng yêu cầu từng khoản đã là một đơn vị hạch toán phải làm tròn độc lập, quy trình đầu có thể là đúng. Nếu quy định chỉ làm tròn tổng cuối, quy trình sau mới đúng. **Không có công thức duy nhất đúng cho mọi trường hợp tài chính.**

### 5.2. Làm tròn đơn giá trước khi nhân số lượng

Giá đơn vị giả định là `0.335`, số lượng là 3.

```text
Làm tròn đơn giá trước:
round(0.335, 2) × 3
= 0.34 × 3
= 1.02

Nhân chính xác rồi làm tròn tổng dòng:
round(0.335 × 3, 2)
= round(1.005, 2)
= 1.01
```

Với `HALF_UP`, hai quy trình chênh `0.01`. Đây không phải sai số nhị phân vì toàn bộ giá trị có thể được lưu chính xác trong `BigDecimal`; sai khác hoàn toàn do **quy tắc làm tròn được áp dụng ở thời điểm khác nhau**.

### 5.3. Chia số và độ chính xác trung gian

Một phép chia như `1 / 3` có biểu diễn thập phân vô hạn; `BigDecimal.ONE.divide(new BigDecimal("3"))` không thể có kết quả thập phân hữu hạn chính xác và sẽ ném `ArithmeticException`. Khi buộc phải làm tròn ở bước chia, cần đặt scale/`MathContext` trung gian đủ phù hợp và định nghĩa rõ ranh giới làm tròn nghiệp vụ, ví dụ `divide(divisor, 8, RoundingMode.HALF_EVEN)`. Không nên gọi `divide()` thiếu quy tắc và hy vọng `setScale()` sau đó sẽ xử lý được exception đã xảy ra.

Dù chọn thêm các chữ số “guard digits” ở trung gian thường giúp giảm rủi ro, không có số chữ số dư cố định nhỏ nào tự động bảo đảm mọi phép tính và mọi đầu vào cho ra đúng kết quả như phép tính chính xác vô hạn. Cần hiểu độ chính xác của dữ liệu, chuỗi phép tính và tiêu chuẩn làm tròn cần chứng minh.

## 6. Precision và MathContext: dạng làm tròn hai lần khác

`BigDecimal.setScale(n, mode)` giữ `n` chữ số **sau dấu thập phân**. `MathContext(p, mode)` giới hạn `p` **chữ số có nghĩa** (*precision*) trong một số phép toán hoặc khi gọi `round(MathContext)`. Hai tham số này khác nhau, nhưng nguy cơ làm tròn trung gian tồn tại ở cả hai.

Ví dụ với `9.949`:

```java
BigDecimal x = new BigDecimal("9.949");
MathContext p3 = new MathContext(3, RoundingMode.HALF_UP);
MathContext p2 = new MathContext(2, RoundingMode.HALF_UP);

BigDecimal twice = x.round(p3).round(p2);
BigDecimal once = x.round(p2);

System.out.println(x.round(p3).toPlainString()); // 9.95
System.out.println(twice.toPlainString());       // 10
System.out.println(once.toPlainString());        // 9.9
```

`9.949` được làm tròn từ bốn xuống ba chữ số có nghĩa thành `9.95`. Sau đó, từ ba xuống hai chữ số có nghĩa thành `10`. Nhưng nếu đi thẳng từ `9.949` xuống hai chữ số có nghĩa, kết quả là `9.9`.

Khi tính toán nhiều bước, ví dụ nhân rồi cộng với `MathContext` giới hạn, mỗi phép toán sử dụng context có thể làm tròn ngay ở kết quả của phép đó. Điều này ảnh hưởng tới kết quả cuối, kể cả khi sau đó còn một lời gọi `setScale()` để hiển thị. Hãy phân biệt rõ:

- **Precision tính toán**: độ chính xác của kết quả các bước số học.
- **Scale lưu trữ/trao đổi**: mức thập phân theo hợp đồng dữ liệu.
- **Scale hiển thị**: số chữ số dùng cho giao diện, hóa đơn hoặc báo cáo.

Không nên hoán đổi ba khái niệm trên.

## 7. Ví dụ Java 17+ hoàn chỉnh, chạy được

Lưu chương trình sau vào tệp `DoubleRoundingDemo.java`. Mỗi phép tính dùng chuỗi thập phân để tránh nhiễu do biểu diễn `double`.

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class DoubleRoundingDemo {
    public static void main(String[] args) {
        RoundingMode halfUp = RoundingMode.HALF_UP;

        BigDecimal value = new BigDecimal("1.245");
        BigDecimal intermediate = value.setScale(2, halfUp);
        BigDecimal twice = intermediate.setScale(1, halfUp);
        BigDecimal once = value.setScale(1, halfUp);

        System.out.println("original = " + value);
        System.out.println("intermediate = " + intermediate);
        System.out.println("twice = " + twice);
        System.out.println("once = " + once);

        BigDecimal halfEvenValue = new BigDecimal("1.251");
        BigDecimal halfEvenTwice = halfEvenValue
                .setScale(2, RoundingMode.HALF_EVEN)
                .setScale(1, RoundingMode.HALF_EVEN);
        BigDecimal halfEvenOnce =
                halfEvenValue.setScale(1, RoundingMode.HALF_EVEN);
        System.out.println("HALF_EVEN twice = " + halfEvenTwice);
        System.out.println("HALF_EVEN once = " + halfEvenOnce);

        BigDecimal itemA = new BigDecimal("0.006");
        BigDecimal itemB = new BigDecimal("0.006");
        BigDecimal sumOfRoundedItems =
                itemA.setScale(2, halfUp).add(itemB.setScale(2, halfUp));
        BigDecimal roundedTotal = itemA.add(itemB).setScale(2, halfUp);
        System.out.println("sum rounded items = " + sumOfRoundedItems);
        System.out.println("round sum = " + roundedTotal);

        BigDecimal unitPrice = new BigDecimal("0.335");
        BigDecimal quantity = new BigDecimal("3");
        BigDecimal roundedUnitFirst =
                unitPrice.setScale(2, halfUp).multiply(quantity);
        BigDecimal roundedLineTotal =
                unitPrice.multiply(quantity).setScale(2, halfUp);
        System.out.println("round unit first = " + roundedUnitFirst);
        System.out.println("round line total = " + roundedLineTotal);

        BigDecimal precisionInput = new BigDecimal("9.949");
        MathContext p3 = new MathContext(3, halfUp);
        MathContext p2 = new MathContext(2, halfUp);
        System.out.println("precision twice = "
                + precisionInput.round(p3).round(p2).toPlainString());
        System.out.println("precision once = "
                + precisionInput.round(p2).toPlainString());
    }
}
```

Chạy từ thư mục chứa tệp:

```bash
javac DoubleRoundingDemo.java
java DoubleRoundingDemo
```

Đầu ra kỳ vọng:

```text
original = 1.245
intermediate = 1.25
twice = 1.3
once = 1.2
HALF_EVEN twice = 1.2
HALF_EVEN once = 1.3
sum rounded items = 0.02
round sum = 0.01
round unit first = 1.02
round line total = 1.01
precision twice = 10
precision once = 9.9
```

Điểm cần quan sát: cùng số ban đầu và cùng rounding mode nhưng đường đi khác có thể tạo kết quả khác. Chương trình giữ kết quả `BigDecimal` gốc không đổi vì `BigDecimal` là immutable. `setScale()` và `round(MathContext)` **trả về kết quả**; các lời gọi không làm biến đổi instance nguồn.

## 8. Cách thiết kế quy trình tính toán tránh mất độ chính xác không cần thiết

**Bước 1 — Xác định kết quả cuối và đơn vị làm tròn.** Ghi rõ “số tiền của từng dòng hóa đơn làm tròn về 0.01”, “tổng lãi làm tròn sau mỗi kỳ”, hoặc “chỉ định dạng hiển thị hai chữ số sau dấu phẩy”. Những câu này mô tả ba quy trình khác nhau.

**Bước 2 — Giữ dữ liệu thập phân chính xác ở đầu vào.** Nếu số gốc là decimal do người dùng/DB cung cấp, khởi tạo `BigDecimal` từ chuỗi hoặc dữ liệu decimal chính xác. Tránh `new BigDecimal(0.1)` nếu định dùng số thập phân chính xác 0.1; constructor này giữ chính xác giá trị nhị phân xấp xỉ của literal `double`. Thường dùng `new BigDecimal("0.1")` hoặc `BigDecimal.valueOf(0.1)`.

**Bước 3 — Dùng độ chính xác tính toán phù hợp.** `BigDecimal.add()` và `multiply()` không truyền `MathContext` thực hiện số học chính xác theo khả năng số học thập phân (với scale của toán hạng). `divide()` có thể đòi chính sách rounding khi thương không hữu hạn. Nếu dùng `MathContext` trong chuỗi tính toán, hiểu rằng kết quả trung gian có thể đã bị làm tròn.

**Bước 4 — Làm tròn ở ranh giới được định nghĩa.** Nếu hợp đồng đòi làm tròn từng line item, làm vậy chủ ý; nếu hợp đồng đòi làm tròn một lần sau khi cộng tổng, trì hoãn `setScale()` đến cuối tổng. Tránh làm tròn “cho đẹp dữ liệu” ở những bước vẫn còn phép toán phía sau.

**Bước 5 — Chọn rounding mode theo nghiệp vụ.** `HALF_EVEN`, `HALF_UP`, `FLOOR` và `CEILING` phục vụ nhu cầu khác nhau. Đặc biệt lưu ý số âm, hoàn tiền, đảo giao dịch và các điểm đúng giữa.

**Bước 6 — Thử ở các ranh giới.** Ngoài số bình thường, kiểm tra các giá trị vừa dưới/trên midpoint, số âm, số 0 và trường hợp rất nhỏ. Kiểm tra cả tổng nhiều khoản và thứ tự toán tử. Sự khác biệt nhỏ trên một giao dịch có thể tích lũy khi xử lý lượng lớn giao dịch.

Một hàm có ranh giới rõ ràng có thể viết như sau:

```java
static BigDecimal totalRoundedAtEnd(
        BigDecimal first,
        BigDecimal second,
        int resultScale,
        RoundingMode mode) {
    return first.add(second).setScale(resultScale, mode);
}
```

Đây là một **đoạn phương thức minh họa** đặt trong lớp Java; nó thực thi chính sách làm tròn sau phép cộng. Nếu yêu cầu là hai dòng phải được làm tròn độc lập, hàm này không đáp ứng chính sách đó và phải được thay bằng quy trình tương ứng.

## 9. Những giả định sai và cách kiểm tra

| Nhầm lẫn | Điều đúng cần nhớ |
| --- | --- |
| “Cùng `RoundingMode` thì làm tròn bao nhiêu lần cũng giống nhau.” | Sai đối với nhiều kiểu làm tròn gần nhất; `1.245` với `HALF_UP` là phản ví dụ. |
| “`HALF_EVEN` loại bỏ hoàn toàn sai số làm tròn hai lần.” | Sai; `1.251` với `HALF_EVEN` là phản ví dụ. |
| “`BigDecimal` luôn bảo đảm kết quả đúng dù làm tròn ở đâu.” | Nó biểu diễn decimal chính xác và tuân thủ chính sách rounding được chỉ định; chính sách đặt sai thời điểm vẫn cho kết quả khác. |
| “Làm tròn từng hạng mục luôn sai.” | Đúng hay sai phụ thuộc quy tắc hạch toán/thuế/hóa đơn được yêu cầu. |
| “Chỉ cần lưu hai chữ số thập phân cho mọi phép tính tiền.” | Trung gian có thể cần thêm chữ số; nên phân biệt precision tính toán với scale kết quả cuối. |
| “Cứ tính với `double` rồi dùng `setScale()` là hết sai số.” | Chuyển một giá trị nhị phân đã xấp xỉ sang decimal không tự tái tạo được số thập phân gốc mong muốn. |
| “Sau phép tính nào cũng gọi `setScale(2)` để thống nhất.” | Có thể làm mất thông tin và làm đổi giá trị của những phép tính phía sau. |

Về mặt kỹ thuật, cũng phải nhớ rằng `BigDecimal.equals()` xét cả scale: `new BigDecimal("1.2").equals(new BigDecimal("1.20"))` là `false` mặc dù `compareTo()` trả 0. Khi so sánh kết quả tính toán theo **giá trị số học**, dùng `compareTo() == 0` hoặc chuẩn hóa theo một quy tắc nhất quán; khi kiểm thử chuỗi định dạng, so sánh nội dung chuỗi như một kiểm tra riêng.

## 10. Bài tập tự kiểm tra

**Câu 1.** `new BigDecimal("1.245").setScale(2, HALF_UP).setScale(1, HALF_UP)` so với `new BigDecimal("1.245").setScale(1, HALF_UP)`?

**Đáp án:** `1.3` và `1.2`. Bước đầu đã biến `1.245` thành midpoint `1.25` cho lần làm tròn thứ hai.

**Câu 2.** Vì sao `HALF_EVEN` không ngăn hoàn toàn sai khác do double rounding?

**Đáp án:** `1.251` → `1.25` → `1.2`, nhưng làm tròn trực tiếp một chữ số được `1.3`. Bước trung gian tạo ra trường hợp tie giả.

**Câu 3.** Hai khoản `0.006` và `0.006`, `HALF_UP` về 2 chữ số thập phân: tổng sau khi làm tròn từng khoản là bao nhiêu, và làm tròn tổng cuối là bao nhiêu?

**Đáp án:** `0.02` và `0.01`. Chọn kết quả nào phụ thuộc ranh giới làm tròn do nghiệp vụ quy định.

**Câu 4.** Với đơn giá `0.335`, số lượng 3, `HALF_UP` về 2 chữ số: làm tròn giá đơn vị trước khi nhân và làm tròn tổng dòng sau khi nhân khác nhau không?

**Đáp án:** `0.34 × 3 = 1.02`, còn `round(0.335 × 3, 2) = 1.01`.

**Câu 5.** `setScale(2)` và `round(new MathContext(2, mode))` có giống nhau?

**Đáp án:** Không. `setScale(2)` chỉ định 2 chữ số sau dấu phẩy (và sẽ lỗi nếu phải làm tròn mà không có mode), trong khi `MathContext(2, mode)` dùng 2 chữ số có nghĩa.

**Câu 6.** Muốn giảm nguy cơ sai khác do làm tròn hai lần trong một pipeline, nguyên tắc thực tế là gì?

**Đáp án:** Duy trì đủ độ chính xác trung gian; chỉ làm tròn tại ranh giới được quy định; tránh hai bước làm tròn gần nhất liên tiếp nếu có thể tính và làm tròn trực tiếp từ giá trị đầy đủ; thử nghiệm các giá trị sát ngưỡng. Nếu nghiệp vụ yêu cầu làm tròn từng hạng mục, phải thực hiện theo đúng yêu cầu đó.

**Ghi nhớ:** Làm tròn là một phép biến đổi có thể làm mất thông tin. **`R_final(R_intermediate(x))` không nhất thiết bằng `R_final(x)`**; tương tự, làm tròn từng thành phần trước khi cộng/nhân có thể khác làm tròn kết quả cuối. Tính toán bằng `BigDecimal` giúp tránh sai số biểu diễn thập phân của `double`, nhưng không thay thế việc chọn đúng **độ chính xác, quy tắc và thời điểm làm tròn**.
