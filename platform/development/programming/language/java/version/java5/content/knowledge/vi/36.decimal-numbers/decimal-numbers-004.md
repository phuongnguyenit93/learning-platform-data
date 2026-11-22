# Ý nghĩa của UP, DOWN, CEILING và FLOOR

## 1. Đừng dịch UP thành “tăng giá trị” một cách máy móc

Khi làm tròn số thập phân, chương trình phải quyết định giữ kết quả nào trong các giá trị có thể biểu diễn ở độ chia đã chọn. Bốn chế độ `RoundingMode.UP`, `DOWN`, `CEILING` và `FLOOR` quyết định theo **hướng**, không dựa vào quy tắc “chữ số từ 5 trở lên”.

Điểm dễ nhầm nhất xuất hiện với số âm. Nếu bỏ phần lẻ của `-7.201` để giữ hai vị trí thập phân:

- Đi **xa số 0** hơn sẽ đến `-7.21`: đó là `UP`.
- Đi **về số 0** sẽ đến `-7.20`: đó là `DOWN`.
- Đi về phía giá trị **lớn hơn** sẽ đến `-7.20`: đó là `CEILING`.
- Đi về phía giá trị **nhỏ hơn** sẽ đến `-7.21`: đó là `FLOOR`.

Vì vậy, `UP` không có nghĩa là cộng thêm vào giá trị; `DOWN` cũng không có nghĩa là giá trị luôn giảm. Hai chế độ này lấy **số 0** làm mốc.

## 2. Nhìn trên trục số

Giả sử kết quả chỉ được có hai vị trí thập phân:

```text
Số dương:
7.20 < 7.201 < 7.21
  ^               ^
DOWN/FLOOR     UP/CEILING

Số âm:
-7.21 < -7.201 < -7.20
  ^                 ^
UP/FLOOR        DOWN/CEILING
```

Ở cả hai dòng, `CEILING` chọn đầu bên phải, `FLOOR` chọn đầu bên trái. Với `UP`/`DOWN`, cần xác định đầu nào xa/gần số 0 hơn.

Nếu số đầu vào đã biểu diễn chính xác ở scale yêu cầu, cả bốn chế độ đều giữ nguyên giá trị số. Không có chuyện `UP` luôn tăng một đơn vị ở chữ số cuối: `7.200` đưa về scale 2 là `7.20`, không phải `7.21`.

## 3. Quy tắc của từng chế độ

| Chế độ | Hướng khi thực sự phải bỏ phần khác 0 | Với số dương | Với số âm |
| --- | --- | --- | --- |
| `UP` | Ra xa số 0 | Chọn phía lớn hơn | Chọn phía nhỏ hơn |
| `DOWN` | Tiến về số 0 | Chọn phía nhỏ hơn | Chọn phía lớn hơn |
| `CEILING` | Hướng về dương vô cực | Giống `UP` | Giống `DOWN` |
| `FLOOR` | Hướng về âm vô cực | Giống `DOWN` | Giống `UP` |

Có thể kiểm tra kết quả bằng các bất đẳng thức theo giá trị số:

- `CEILING(x) >= x`.
- `FLOOR(x) <= x`.
- `|UP(x)| >= |x|`.
- `|DOWN(x)| <= |x|`.

Các so sánh này giả sử đang làm tròn cùng một giá trị về cùng độ chia và phép tính thực hiện thành công. Dấu bằng xảy ra khi không cần thay đổi giá trị số. Đối với mã `BigDecimal`, so sánh giá trị số bằng `compareTo`, không dùng toán tử `>=` trực tiếp trên đối tượng.

### UP: phần bị bỏ chỉ cần khác 0

Với scale 2, cả `3.001` và `3.009` đều cho `3.01` khi dùng `UP`. Phần bị bỏ nhỏ hơn `0.005` vẫn đủ làm kết quả đi xa số 0.

Điều này phân biệt `UP` với `HALF_UP`: `3.001` dùng `HALF_UP` sẽ là `3.00`. `HALF_UP` chọn giá trị gần nhất và có quy tắc khi đúng giữa; `UP` luôn chọn hướng xa số 0 khi cần thay đổi giá trị.

### DOWN: cắt về số 0

`-3.999` về scale 2 với `DOWN` là `-3.99`. Đừng gọi thao tác này là “lấy sàn”: sàn theo nghĩa toán học tương ứng hướng `FLOOR`, và ở đây sẽ cho `-4.00`.

### CEILING và FLOOR: giữ quan hệ lớn hơn hoặc nhỏ hơn

Với `-3.001` về scale 2, `CEILING` cho `-3.00`, vì `-3.00` lớn hơn `-3.001`. `FLOOR` cho `-3.01`, vì giá trị đó nhỏ hơn.

`CEILING`/`FLOOR` không chỉ áp dụng cho số nguyên. Chúng chọn hướng theo độ chia do phép toán quy định: phần trăm, phần nghìn hoặc hàng trăm đều có thể dùng được.

## 4. Chọn độ chia trước, chọn hướng sau

Chỉ đưa ra `RoundingMode` chưa đủ để biết kết quả; còn phải biết giữ bao nhiêu vị trí hoặc chữ số.

Trong `setScale(2, mode)`, kết quả có hai vị trí thập phân. Trong `setScale(0, mode)`, kết quả là số nguyên theo giá trị. Scale âm cũng hợp lệ: `setScale(-2, mode)` đưa kết quả về bội số của 100.

Ví dụ minh họa trong một phương thức:

```java
BigDecimal value = new BigDecimal("1234");

BigDecimal atHundreds =
        value.setScale(-2, RoundingMode.CEILING); // Gia tri so: 1300

BigDecimal atUnits =
        value.setScale(0, RoundingMode.CEILING);  // Gia tri so: 1234
```

Đối với `round(new MathContext(2, mode))`, số 2 lại là tổng số chữ số có nghĩa được giữ tối đa. Nó không có nghĩa là hai chữ số sau dấu thập phân. Ví dụ `0.01234`:

- `round(new MathContext(2, UP))` → `0.013`.
- `setScale(2, UP)` → `0.02`.

Với phép chia, có thể dùng `divide(divisor, scale, mode)` để nêu rõ scale của thương. Ví dụ `new BigDecimal("10").divide(new BigDecimal("3"), 2, RoundingMode.DOWN)` cho `3.33`. Luôn đọc chữ ký phương thức để biết tham số đang điều khiển scale hay precision.

## 5. Chương trình chạy đầy đủ

Lưu dưới tên `DirectionalRoundingDemo.java`. Chương trình sử dụng API có trên Java 17 trở lên, tạo dữ liệu từ chuỗi để các giá trị thập phân thử nghiệm được xác định rõ.

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class DirectionalRoundingDemo {
    public static void main(String[] args) {
        RoundingMode[] modes = {
                RoundingMode.UP, RoundingMode.DOWN,
                RoundingMode.CEILING, RoundingMode.FLOOR
        };
        System.out.println("input | UP | DOWN | CEILING | FLOOR");
        for (String text : new String[] {
                "7.201", "-7.201", "0.004", "-0.004", "7.200"
        }) {
            BigDecimal value = new BigDecimal(text);
            System.out.print(text);
            for (RoundingMode mode : modes) {
                System.out.print(" | " + value.setScale(2, mode).toPlainString());
            }
            System.out.println();
        }

        BigDecimal negative = new BigDecimal("-12.001");
        System.out.println("ceiling integer = "
                + negative.setScale(0, RoundingMode.CEILING));
        System.out.println("floor integer = "
                + negative.setScale(0, RoundingMode.FLOOR));

        BigDecimal large = new BigDecimal("1234");
        System.out.println("hundreds ceiling = "
                + large.setScale(-2, RoundingMode.CEILING).toPlainString());

        BigDecimal input = new BigDecimal("0.01234");
        System.out.println("precision 2, UP = "
                + input.round(new MathContext(2, RoundingMode.UP)));
        System.out.println("scale 2, UP = "
                + input.setScale(2, RoundingMode.UP));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 DirectionalRoundingDemo.java
java DirectionalRoundingDemo
```

Kết quả:

```text
input | UP | DOWN | CEILING | FLOOR
7.201 | 7.21 | 7.20 | 7.21 | 7.20
-7.201 | -7.21 | -7.20 | -7.20 | -7.21
0.004 | 0.01 | 0.00 | 0.01 | 0.00
-0.004 | -0.01 | 0.00 | 0.00 | -0.01
7.200 | 7.20 | 7.20 | 7.20 | 7.20
ceiling integer = -12
floor integer = -13
hundreds ceiling = 1300
precision 2, UP = 0.013
scale 2, UP = 0.02
```

Hàng `-0.004` là phép thử hữu ích: `DOWN` và `CEILING` đều cho giá trị 0 ở scale 2. `BigDecimal` không giữ một giá trị “âm 0” riêng biệt; vì vậy chương trình in `0.00`.

Hàng `7.200` cho thấy bỏ số 0 cuối không phải thay đổi giá trị số, nên không chế độ nào đẩy sang `7.21`.

## 6. Từ yêu cầu nghiệp vụ đến chế độ cụ thể

Trước khi chọn enum, hãy viết yêu cầu bằng quan hệ rõ ràng:

| Yêu cầu đã được xác nhận | Hướng thường phù hợp |
| --- | --- |
| Kết quả phải lớn hơn hoặc bằng giá trị chính xác ở độ chia này | `CEILING` |
| Kết quả phải nhỏ hơn hoặc bằng giá trị chính xác ở độ chia này | `FLOOR` |
| Độ lớn tuyệt đối không được thấp hơn giá trị chính xác | `UP` |
| Độ lớn tuyệt đối không được cao hơn giá trị chính xác | `DOWN` |

Ví dụ, nếu cần tính số hộp nguyên để chứa hết số lượng dương, lấy thương rồi làm tròn theo `CEILING` về scale 0 có thể phù hợp. Tuy nhiên, ví dụ này dựa trên điều kiện số lượng và sức chứa đều dương; không được suy diễn cùng cách diễn đạt cho dữ liệu âm.

Với số tiền có cả ghi nợ, hoàn tiền và điều chỉnh âm, các từ “làm tròn lên có lợi cho bên nhận” chưa xác định rõ hướng. Cần thống nhất dấu của khoản tiền và quan hệ giá trị mong muốn trước. Không chọn `UP` chỉ vì mô tả có từ “lên”.

Ngoài hướng, cần quyết định **thời điểm làm tròn**. Làm tròn từng dòng rồi cộng có thể khác cộng chính xác rồi làm tròn tổng. Bốn enum không tự quyết định quy trình đó.

## 7. Lỗi dễ mắc và cách kiểm tra

1. **Chỉ thử số dương.** Với số dương, `UP` giống `CEILING`, `DOWN` giống `FLOOR`; thiếu số âm sẽ che mất sự khác biệt.
2. **Nhìn riêng chữ số đầu tiên bị bỏ.** `UP` cần biết toàn bộ phần bị bỏ có khác 0 không. `1.23001` về scale 2 với `UP` là `1.24`, dù chữ số thứ ba là 0.
3. **Cho rằng mọi lần giảm scale đều đổi giá trị.** `8.000` về scale 2 vẫn là giá trị 8.
4. **Quên dùng kết quả trả về.** `BigDecimal` bất biến; hãy gán hoặc truyền tiếp kết quả của `setScale`/`round`.
5. **Dùng hằng số làm tròn kiểu số nguyên cũ trong mã mới.** Dùng `RoundingMode.UP`, `DOWN`, `CEILING`, `FLOOR` để biểu đạt yêu cầu rõ ràng bằng API hiện hành.

Một bộ kiểm tra có ý nghĩa nên chứa số dương, số âm, số gần 0, số đã đúng scale và số có phần bị bỏ rất nhỏ nhưng khác 0. Đồng thời kiểm tra đúng scale đầu ra theo hợp đồng.

## 8. Bài tập tự suy luận

Đưa mỗi số sau về scale 1 bằng cả bốn chế độ: `4.01`, `-4.01`, `4.00`, `-0.01`.

Đáp án theo thứ tự `UP, DOWN, CEILING, FLOOR`:

```text
4.01  -> 4.1, 4.0, 4.1, 4.0
-4.01 -> -4.1, -4.0, -4.0, -4.1
4.00  -> 4.0, 4.0, 4.0, 4.0
-0.01 -> -0.1, 0.0, 0.0, -0.1
```

Cách giải thích một đáp án phải chỉ ra mốc hướng: `UP`/`DOWN` theo khoảng cách đến 0; `CEILING`/`FLOOR` theo thứ tự trên trục số.

Tham khảo hợp đồng hiện hành: [RoundingMode trong Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html) và [BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html).
