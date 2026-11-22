# HALF_UP và HALF_DOWN khi giá trị nằm đúng giữa

## Vấn đề cần hiểu

Trong Java, `RoundingMode.HALF_UP` và `RoundingMode.HALF_DOWN` đều làm tròn về **giá trị gần nhất**. Chúng chỉ khác nhau khi giá trị ban đầu **cách đều hai mức đích**, gọi là *đúng giữa* (*tie* hay *halfway case*).

Ví dụ, giữ hai chữ số sau dấu thập phân: `2.34` và `2.35` cách nhau `0.01`, còn `2.345` cách mỗi số `0.005`. Khi đó:

- `HALF_UP` chọn `2.35` (xa số 0 hơn).
- `HALF_DOWN` chọn `2.34` (gần số 0 hơn).
- `2.344` không đúng giữa: cả hai chọn `2.34`.
- `2.346` không đúng giữa: cả hai chọn `2.35`.

Với mục tiêu giữ `s` chữ số thập phân, hai mức liền kề cách nhau `10^-s` và điểm giữa cách mỗi mức `(10^-s)/2`. Ở `scale = 2`, nửa bước chính xác là `0.005`.

```text
2.34           2.345           2.35
 |---------------|---------------|
       0.005           0.005
           đúng giữa
```

**Cần xét toàn bộ phần chữ số bị loại.** `2.345000` vẫn đúng giữa vì chỉ thêm số 0 cuối; `2.345001` không còn đúng giữa vì nằm gần `2.35` hơn. Việc “chữ số đầu bị loại là 5” chưa đủ để kết luận có tie.

## Quy tắc khi số dương và số âm

| Số ban đầu, giữ 2 chữ số | HALF_UP | HALF_DOWN | Giải thích |
|---|---|---|---|
| `2.344` | `2.34` | `2.34` | Gần mức thấp hơn |
| `2.345` | `2.35` | `2.34` | Tie dương |
| `2.346` | `2.35` | `2.35` | Gần mức cao hơn |
| `-2.344` | `-2.34` | `-2.34` | Gần `-2.34` |
| `-2.345` | `-2.35` | `-2.34` | Tie âm |
| `-2.346` | `-2.35` | `-2.35` | Gần `-2.35` |
| `0.005` | `0.01` | `0.00` | Tie sát 0 |
| `-0.005` | `-0.01` | `0.00` | Tie âm sát 0 |
| `2.34501` | `2.35` | `2.35` | Trên điểm giữa |

Điểm quan trọng nhất: **“UP” không có nghĩa kết quả số học tăng**. Với `-2.345`, `HALF_UP` cho `-2.35`, tức là số nhỏ hơn trên trục số nhưng **xa 0 hơn**; `HALF_DOWN` cho `-2.34`, tức là **gần 0 hơn**. Với `-0.005` và `HALF_DOWN`, `BigDecimal` trả `0.00` (số 0 có scale 2), không cần một kết quả “-0.00”.

Khi giá trị **không** đúng giữa, cả hai chế độ đều chọn số gần nhất bất kể dấu; ví dụ `-2.346` thành `-2.35` ở cả hai chế độ.

## Java 17+ — chương trình chạy độc lập

Tạo file `HalfTieDemo.java`:

```java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class HalfTieDemo {
    private static void show(String raw) {
        BigDecimal value = new BigDecimal(raw);
        BigDecimal up = value.setScale(2, RoundingMode.HALF_UP);
        BigDecimal down = value.setScale(2, RoundingMode.HALF_DOWN);

        System.out.println(raw + " | " + up.toPlainString()
                + " | " + down.toPlainString());
    }

    public static void main(String[] args) {
        System.out.println("value | HALF_UP | HALF_DOWN");
        for (String raw : new String[] {
                "2.344", "2.345", "2.346",
                "-2.344", "-2.345", "-2.346",
                "0.005", "-0.005", "2.34501"
        }) {
            show(raw);
        }

        BigDecimal one = BigDecimal.ONE;
        BigDecimal eight = new BigDecimal("8");
        System.out.println("1 / 8 | "
                + one.divide(eight, 2, RoundingMode.HALF_UP)
                + " | "
                + one.divide(eight, 2, RoundingMode.HALF_DOWN));

        BigDecimal p = new BigDecimal("12.35");
        System.out.println("precision 3 | "
                + p.round(new MathContext(3, RoundingMode.HALF_UP))
                        .toPlainString()
                + " | "
                + p.round(new MathContext(3, RoundingMode.HALF_DOWN))
                        .toPlainString());
    }
}
```

Dùng JDK 17 hoặc mới hơn:

```bash
javac HalfTieDemo.java
java HalfTieDemo
```

Kết quả chính xác:

```text
value | HALF_UP | HALF_DOWN
2.344 | 2.34 | 2.34
2.345 | 2.35 | 2.34
2.346 | 2.35 | 2.35
-2.344 | -2.34 | -2.34
-2.345 | -2.35 | -2.34
-2.346 | -2.35 | -2.35
0.005 | 0.01 | 0.00
-0.005 | -0.01 | 0.00
2.34501 | 2.35 | 2.35
1 / 8 | 0.13 | 0.12
precision 3 | 12.4 | 12.3
```

Giải thích mã:

1. `new BigDecimal(raw)` nhận biểu diễn **thập phân chính xác** từ chuỗi, giúp các trường hợp tie đúng như mô tả.
2. `setScale(2, mode)` yêu cầu chính xác 2 chữ số sau dấu thập phân và áp dụng chế độ nếu phải loại chữ số.
3. `1 / 8 = 0.125` nằm giữa `0.12` và `0.13`; `divide(eight, 2, mode)` trả về `0.13` theo `HALF_UP`, `0.12` theo `HALF_DOWN`.
4. `new MathContext(3, mode)` yêu cầu **3 chữ số có nghĩa**, nên `12.35` thành `12.4` hoặc `12.3`.
5. `BigDecimal` là kiểu **bất biến**. `setScale`, `divide` và `round` trả về kết quả mới; không thay đổi đối tượng cũ. Muốn lưu thì gán lại, chẳng hạn `value = value.setScale(2, mode)`.

## Scale, precision và độ lớn một bước làm tròn

**Scale** là số chữ số bên phải dấu thập phân. `setScale(2, mode)` làm tròn theo phần trăm đơn vị; `setScale(0, mode)` làm tròn tới đơn vị; `setScale(-1, mode)` làm tròn tới hàng chục.

**Precision** trong `MathContext` là **tổng số chữ số có nghĩa**, không phải riêng phần thập phân. Ví dụ `12.35` có 4 chữ số có nghĩa; làm tròn về precision 3 tạo tie giữa `12.3` và `12.4`.

| Mục tiêu | Đầu vào | HALF_UP | HALF_DOWN |
|---|---|---|---|
| `setScale(2)` | `7.125` | `7.13` | `7.12` |
| `setScale(0)` | `-2.5` | `-3` | `-2` |
| `setScale(-1)` | `145` | `150` | `140` |
| `MathContext(3)` | `12.35` | `12.4` | `12.3` |

Làm tròn ở scale âm có thể cho biểu diễn ký pháp khoa học trong `BigDecimal`; `toPlainString()` hiển thị theo dạng thông thường. Nếu `setScale` cần loại chữ số nhưng không cung cấp `RoundingMode`, phép gọi có thể ném `ArithmeticException`. `RoundingMode.UNNECESSARY` cũng ném lỗi khi cần làm tròn, hữu ích nếu hợp đồng dữ liệu yêu cầu kết quả chính xác tuyệt đối ở scale đích.

## Những lỗi hiểu và áp dụng thường gặp

### 1. Thấy chữ số 5 rồi tự cho là đúng giữa

Ở scale 2, `2.34499` ở dưới nửa bước nên cả hai về `2.34`; `2.34500` là tie nên cho kết quả khác; `2.34501` ở trên nửa bước nên cả hai về `2.35`. Khi kiểm thử phải có các giá trị ngay trước, đúng tại và ngay sau điểm giữa.

### 2. Nhầm HALF_UP với UP, CEILING hoặc Math.round

`RoundingMode.UP` luôn đi xa số 0 khi phải loại chữ số; `DOWN` luôn đi về 0. `CEILING` về phía dương và `FLOOR` về phía âm. Chúng khác với `HALF_UP`/`HALF_DOWN` vì hai chế độ HALF ưu tiên **mức gần nhất**.

`Math.round(-2.5)` trả `-2`: tại tie, `Math.round` lựa chọn về phía dương trên trục số, khác `BigDecimal("-2.5").setScale(0, RoundingMode.HALF_UP)` cho `-3`. Vì vậy, không thay `RoundingMode` bằng `Math.round` theo trực giác tên gọi.

### 3. Dùng double làm mất tính chính xác của tie

`new BigDecimal(2.675)` nhận giá trị nhị phân xấp xỉ mà `double` đang lưu, có thể không đúng bằng `2.675`. Điểm giữa thập phân có thể bị lệch khiến kết quả bất ngờ. Để diễn đạt giá trị thập phân chính xác, dùng `new BigDecimal("2.675")`; tại scale 2 với `HALF_UP`, kết quả là `2.68`.

`BigDecimal.valueOf(2.675)` chuyển qua chuỗi biểu diễn của `double` và thường gần với giá trị con người mong đợi hơn constructor nhận `double`, nhưng **không khôi phục được độ chính xác đã mất** trong các phép toán `double` trước đó.

### 4. Làm tròn ở bước trung gian tùy ý

Hai khoản `1.245`: làm tròn từng khoản tại scale 2 với `HALF_UP` rồi cộng cho `1.25 + 1.25 = 2.50`. Nếu cộng trước rồi làm tròn một lần, `1.245 + 1.245 = 2.490` cho `2.49`. Cùng một chế độ nhưng khác kết quả vì **thời điểm làm tròn** khác nhau. Quy định nghiệp vụ phải nêu cả thời điểm, scale và chế độ.

### 5. Chọn chế độ vì “nghe hợp lý”

Không có quy tắc phổ quát rằng mọi khoản tiền phải dùng `HALF_UP` hoặc `HALF_DOWN`. Hãy theo yêu cầu của hệ thống, chuẩn hay hợp đồng. Còn `HALF_EVEN`, một chính sách phổ biến khác, chọn chữ số cuối được giữ là **số chẵn** tại tie: ở scale 2, `2.345` thành `2.34` nhưng `2.355` thành `2.36`. `HALF_EVEN` không đồng nghĩa với `HALF_DOWN`.

## Áp dụng và tự kiểm tra

Trước khi triển khai, trả lời được: đầu vào có giữ chính xác giá trị thập phân không; mục tiêu là scale hay precision; khi tie phải đi xa hay gần số 0; làm tròn ở bước nào; đã kiểm thử số âm và các số sát hai bên tie hay chưa. Dùng `RoundingMode` tường minh trong `setScale`, `divide` hoặc `round(MathContext)`.

**Bài tự kiểm tra:** Làm tròn `-7.1250` tới 2 chữ số. Đây là tie giữa `-7.12` và `-7.13`, nên `HALF_UP` cho **`-7.13`**, `HALF_DOWN` cho **`-7.12`**. Nếu đổi thành `-7.1251`, cả hai đều cho `-7.13` do gần `-7.13` hơn.

**Ghi nhớ:** Hai chế độ đều làm tròn về mức gần nhất; **chỉ tại điểm đúng giữa**, `HALF_UP` chọn xa số 0 và `HALF_DOWN` chọn gần số 0.
