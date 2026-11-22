# RoundingMode của bộ định dạng trong Java

Khi hiển thị một số thành chuỗi, ứng dụng thường cần giới hạn số chữ số thập phân: giá tiền có hai chữ số sau dấu thập phân, tỷ lệ có ba chữ số hoặc giá trị trong báo cáo cần cùng độ chính xác. Nếu giá trị có nhiều chữ số hơn giới hạn hiển thị, **bộ định dạng phải quyết định làm tròn theo hướng nào**. Trong Java, `java.math.RoundingMode` mô tả quy tắc đó; `java.text.DecimalFormat` cho phép cấu hình bằng `setRoundingMode(...)`.

Bài này giải thích cách `RoundingMode` chi phối **kết quả định dạng** của `DecimalFormat`, đặc biệt khi gặp số đúng giữa hai mức làm tròn (*tie*) và số âm. Phép làm tròn trong tính toán bằng `BigDecimal` được đối chiếu để tránh nhầm mục đích.

## 1. Làm tròn xảy ra ở bước nào?

Có ba khái niệm khác nhau:

1. **Giá trị gốc:** ví dụ `BigDecimal("12.345")` vẫn biểu diễn giá trị `12.345`.
2. **Độ chính xác cần hiển thị:** mẫu `0.00` hoặc `setMaximumFractionDigits(2)` yêu cầu không hiển thị quá hai chữ số thập phân.
3. **Quy tắc chọn giá trị gần đúng:** `RoundingMode.HALF_UP`, `HALF_EVEN`, `FLOOR`... cho biết phải xử lý phần bị loại bỏ ra sao.

Ví dụ, cùng giá trị `12.345` với hai chữ số sau dấu thập phân:

| Bộ định dạng | Quy tắc | Chuỗi kết quả |
|---|---|---|
| `0.00` | `HALF_UP` | `12.35` |
| `0.00` | `HALF_EVEN` | `12.34` |
| `0.00` | `DOWN` | `12.34` |

`DecimalFormat.format(...)` trả về **`String`**; nó không sửa đối tượng `BigDecimal` và không cập nhật biến số đầu vào. Nếu cần làm tròn giá trị để tiếp tục tính toán, hãy dùng API số học phù hợp như `BigDecimal.setScale(...)` với quy tắc đã chọn.

### Cách thiết lập

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

DecimalFormat formatter = new DecimalFormat(
        "#,##0.00", DecimalFormatSymbols.getInstance(Locale.US));
formatter.setRoundingMode(RoundingMode.HALF_UP);

String text = formatter.format(new BigDecimal("1234.565"));
// text = "1,234.57"
```

Đây là **đoạn mã minh họa** để đặt trong phương thức hoặc JShell (không phải một tệp Java độc lập). Mẫu `#,##0.00` bật phân nhóm hàng nghìn và luôn in đúng hai chữ số thập phân; bộ ký hiệu `Locale.US` dùng dấu `.` cho phần thập phân và dấu `,` cho hàng nghìn. `HALF_UP` chọn phía xa số 0 khi giá trị nằm đúng giữa hai mức làm tròn.

`DecimalFormat` mặc định dùng `RoundingMode.HALF_EVEN`, nhưng nên đặt tường minh để người đọc mã nhận ra quy tắc nghiệp vụ và để tránh phụ thuộc vào mặc định.

## 2. Tám chế độ của `RoundingMode`

Giả sử định dạng bắt buộc **hai chữ số thập phân**, và giá trị đầu vào là `2.345` hoặc `-2.345`. Cả hai đều nằm đúng giữa hai mức gần nhất vì chữ số thứ ba là `5` và không có phần còn lại.

| Chế độ | Ý nghĩa | `2.345` | `-2.345` |
|---|---|---:|---:|
| `UP` | Ra xa 0 nếu phải bỏ phần khác 0 | `2.35` | `-2.35` |
| `DOWN` | Về phía 0; bỏ phần vượt quá độ chính xác | `2.34` | `-2.34` |
| `CEILING` | Về phía dương vô cực (`+∞`) | `2.35` | `-2.34` |
| `FLOOR` | Về phía âm vô cực (`-∞`) | `2.34` | `-2.35` |
| `HALF_UP` | Chọn gần nhất; nếu hòa, ra xa 0 | `2.35` | `-2.35` |
| `HALF_DOWN` | Chọn gần nhất; nếu hòa, về phía 0 | `2.34` | `-2.34` |
| `HALF_EVEN` | Chọn gần nhất; nếu hòa, chữ số giữ lại cuối cùng phải chẵn | `2.34` | `-2.34` |
| `UNNECESSARY` | Không cho phép làm tròn làm thay đổi giá trị | Ném `ArithmeticException` | Ném `ArithmeticException` |

**Hai nhóm quy tắc cần phân biệt:**

- `UP`, `DOWN`, `CEILING` và `FLOOR` quyết định **hướng** khi có phần khác 0 bị loại, không cần xét liệu phần đó lớn hay nhỏ hơn `0.5` đơn vị ở chữ số cuối.
- `HALF_UP`, `HALF_DOWN` và `HALF_EVEN` chọn **giá trị gần nhất** trước; chỉ khi khoảng cách tới hai giá trị kề nhau bằng nhau, quy tắc xử lý *tie* mới khác nhau.

Ví dụ `2.346` khi in hai chữ số thập phân sẽ thành `2.35` với cả `HALF_UP`, `HALF_DOWN` và `HALF_EVEN`: đây không phải trường hợp hòa, vì `2.35` gần hơn `2.34`.

### Vì sao `HALF_EVEN` không có nghĩa là “luôn làm tròn xuống”?

Khi gặp hòa, `HALF_EVEN` chọn kết quả có **chữ số cuối được giữ lại là số chẵn**:

- `2.345` → `2.34`, vì chữ số hàng phần trăm là `4` (chẵn).
- `2.355` → `2.36`, vì chữ số hàng phần trăm là `6` (chẵn).
- `-2.345` → `-2.34`, cũng theo quy tắc chữ số chẵn.

Cơ chế này còn được gọi là *round half to even* hoặc *banker's rounding*. Trong nhiều chuỗi làm tròn với dữ liệu phân bố phù hợp, nó giúp giảm xu hướng lệch cộng dồn do luôn xử lý hòa về một phía. Điều đó không biến nó thành quy tắc bắt buộc cho mọi hệ thống tiền tệ: hệ thống cần áp dụng chính sách làm tròn được quy định cho từng nghiệp vụ.

### Đặc biệt với số âm

`CEILING` và `FLOOR` không đồng nghĩa với “tăng” và “giảm” phần trị tuyệt đối:

- `CEILING(-2.345)` ở hai chữ số → `-2.34`, vì `-2.34` **lớn hơn** `-2.35`.
- `FLOOR(-2.345)` → `-2.35`, vì `-2.35` **nhỏ hơn** `-2.34`.
- `UP` luôn hướng **ra xa 0**; `DOWN` luôn hướng **về 0**, với cả dấu dương lẫn dấu âm.

Đây là nguyên nhân phổ biến khiến việc kiểm thử chỉ với số dương bỏ sót lỗi.

## 3. Chương trình Java 17+ chạy độc lập

Lưu tệp dưới tên `RoundingModeFormatterDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class RoundingModeFormatterDemo {
    private static String display(String value, RoundingMode mode) {
        DecimalFormat formatter = new DecimalFormat("0.00",
                DecimalFormatSymbols.getInstance(Locale.US));
        formatter.setRoundingMode(mode);
        return formatter.format(new BigDecimal(value));
    }

    public static void main(String[] args) {
        for (RoundingMode mode : new RoundingMode[] {
                RoundingMode.UP, RoundingMode.DOWN, RoundingMode.CEILING,
                RoundingMode.FLOOR, RoundingMode.HALF_UP, RoundingMode.HALF_DOWN,
                RoundingMode.HALF_EVEN
        }) {
            System.out.println(mode + ": " + display("2.345", mode)
                    + " | " + display("-2.345", mode));
        }
        System.out.println("HALF_EVEN 2.355: "
                + display("2.355", RoundingMode.HALF_EVEN));
        try {
            System.out.println(display("2.345", RoundingMode.UNNECESSARY));
        } catch (ArithmeticException ex) {
            System.out.println("UNNECESSARY: ArithmeticException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 RoundingModeFormatterDemo.java
java RoundingModeFormatterDemo
```

Kết quả chuẩn trong môi trường Java đã hỗ trợ các API này (ví dụ Java 17):

```text
UP: 2.35 | -2.35
DOWN: 2.34 | -2.34
CEILING: 2.35 | -2.34
FLOOR: 2.34 | -2.35
HALF_UP: 2.35 | -2.35
HALF_DOWN: 2.34 | -2.34
HALF_EVEN: 2.34 | -2.34
HALF_EVEN 2.355: 2.36
UNNECESSARY: ArithmeticException
```

**Giải thích chương trình:**

1. `new BigDecimal(value)` nhận chuỗi thập phân để tạo đầu vào đúng theo số viết ra, giúp thử các giá trị hòa một cách chính xác.
2. `new DecimalFormat("0.00", ...)` giới hạn kết quả về hai chữ số thập phân và cố định ký hiệu hiển thị.
3. `setRoundingMode(mode)` thay đổi cách chọn kết quả khi cần loại bớt chữ số.
4. Vòng lặp thử các chế độ theo cùng dữ liệu dương và âm. `UNNECESSARY` được thử riêng, vì đây là chế độ xác thực việc **không phải làm tròn**, và nó có thể ném ngoại lệ.

## 4. Quan hệ giữa mẫu định dạng, số chữ số và `RoundingMode`

`RoundingMode` **không tự quy định** làm tròn tới hàng đơn vị, một chữ số hay hai chữ số thập phân. Vị trí làm tròn được quyết định bởi cấu hình chữ số của bộ định dạng.

```java
DecimalFormat f = new DecimalFormat("0.##",
        DecimalFormatSymbols.getInstance(Locale.US));
f.setRoundingMode(RoundingMode.HALF_UP);

f.format(new BigDecimal("2.345")); // "2.35"
f.format(new BigDecimal("2.3"));   // "2.3"
f.format(new BigDecimal("2"));     // "2"
```

Mẫu `0.##` cho phép **tối đa** hai chữ số sau dấu thập phân; dấu `#` không buộc in các số 0 ở cuối. Nếu muốn luôn in đủ hai chữ số, dùng `0.00`. Đây là sự khác biệt về **trình bày**, không phải hai chế độ làm tròn khác nhau.

Có thể cấu hình bằng phương thức thay cho mẫu:

```java
DecimalFormat f = new DecimalFormat("#,##0.###",
        DecimalFormatSymbols.getInstance(Locale.US));
f.setMinimumFractionDigits(2);
f.setMaximumFractionDigits(2);
f.setRoundingMode(RoundingMode.HALF_UP);

f.format(new BigDecimal("1234.565")); // "1,234.57"
f.format(new BigDecimal("1234.5"));   // "1,234.50"
```

- `setMaximumFractionDigits(2)`: giới hạn số chữ số thập phân hiển thị ở mức tối đa hai; đây là cấu hình khiến phép làm tròn có thể phát sinh.
- `setMinimumFractionDigits(2)`: yêu cầu in ít nhất hai chữ số, kể cả khi phải bổ sung số 0.
- `getRoundingMode()`: đọc quy tắc hiện tại của bộ định dạng.
- `setRoundingMode(...)`: đặt quy tắc khi có chữ số phải loại bỏ.

Với một giá trị đã biểu diễn đúng ở độ chính xác cần hiển thị (ví dụ `2.34` in hai chữ số), các chế độ sẽ cho cùng giá trị kết quả; việc bổ sung số 0 (`2.3` → `2.30`) không phải là làm tròn thay đổi giá trị.

## 5. `UNNECESSARY`: phát hiện thay vì tự động làm tròn

`RoundingMode.UNNECESSARY` phù hợp khi hợp đồng dữ liệu yêu cầu đầu vào **đã đúng độ chính xác**, và bất kỳ việc loại phần khác 0 nào cũng phải được báo lỗi.

```java
DecimalFormat strict = new DecimalFormat("0.00",
        DecimalFormatSymbols.getInstance(Locale.US));
strict.setRoundingMode(RoundingMode.UNNECESSARY);

strict.format(new BigDecimal("2.34"));  // "2.34"
strict.format(new BigDecimal("2.340")); // "2.34": bỏ số 0 không đổi giá trị
strict.format(new BigDecimal("2.345")); // ArithmeticException
```

Đoạn này minh họa các lệnh gọi riêng lẻ; nếu chạy tuần tự và không bắt ngoại lệ, lệnh cuối sẽ dừng luồng thực thi. Quan trọng là `UNNECESSARY` **không cấm mọi thao tác thay đổi chuỗi ký tự**: nó cấm làm tròn làm thay đổi **giá trị số**. Vì vậy việc loại các số 0 thập phân dư thừa vẫn hợp lệ.

Nếu giá trị đến từ nhập liệu hoặc API, hãy kiểm tra yêu cầu về scale/độ chính xác ngay tại ranh giới nhập dữ liệu, trả lỗi nghiệp vụ rõ ràng; không nên dùng `UNNECESSARY` như cách thay thế cho toàn bộ quy trình xác thực đầu vào.

## 6. Định dạng khác với làm tròn phục vụ phép tính

Có hai luồng xử lý hợp lý, tùy mục đích.

**Chỉ hiển thị số**:

```java
BigDecimal original = new BigDecimal("19.995");
DecimalFormat view = new DecimalFormat("0.00",
        DecimalFormatSymbols.getInstance(Locale.US));
view.setRoundingMode(RoundingMode.HALF_UP);

String label = view.format(original); // "20.00"
// original vẫn là 19.995
```

**Tính tiếp với giá trị đã làm tròn**:

```java
BigDecimal original = new BigDecimal("19.995");
BigDecimal rounded = original.setScale(2, RoundingMode.HALF_UP);
// rounded = 20.00 (BigDecimal, scale = 2)
```

Cả `format(...)` và `setScale(...)` đều có thể dùng `RoundingMode`, nhưng kết quả khác loại: một bên là `String` phục vụ biểu diễn, bên kia là `BigDecimal` phục vụ số học. `BigDecimal` bất biến: `setScale(...)` trả đối tượng mới thay vì sửa `original`.

Nếu tính tiền, thuế, chiết khấu hoặc đối soát, phải xác định **thời điểm làm tròn** theo quy tắc nghiệp vụ (từng dòng, từng giao dịch hay ở tổng cuối). Cộng các chuỗi đã định dạng hoặc định dạng trước mỗi bước rồi chuyển ngược lại thành số có thể làm mất thông tin và tạo sai lệch. `RoundingMode` chỉ quyết định **cách** làm tròn khi đã đến bước cần làm tròn; nó không tự quyết định **khi nào** làm tròn.

## 7. Đầu vào `double`, `BigDecimal` và lỗi do biểu diễn nhị phân

Phần lớn phân số thập phân không được biểu diễn chính xác bằng `double`. Khi kiểm thử những trường hợp nhạy cảm như đúng điểm giữa, dùng giá trị `double` có thể khiến kết quả khó suy luận chỉ bằng cách nhìn ký tự thập phân trong mã nguồn.

```java
BigDecimal exact = new BigDecimal("2.345"); // Chính xác là 2.345
BigDecimal fromDouble = new BigDecimal(2.345); // Lấy đúng giá trị nhị phân của double
```

Hai cách tạo `BigDecimal` này không bảo đảm cùng giá trị số. Để mô tả một giá trị thập phân nghiệp vụ, ưu tiên nhận `BigDecimal` từ chuỗi thập phân, từ dữ liệu decimal có kiểm soát, hoặc dùng `BigDecimal.valueOf(double)` khi buộc chuyển từ `double` (hiểu rõ rằng quá trình tính toán bằng `double` trước đó có thể đã mất độ chính xác).

Khi gọi `DecimalFormat.format(double)`, hãy nhớ đang định dạng **giá trị `double` thực tế**, không phải một “số thập phân lý tưởng” mà người đọc hình dung từ literal. Với bài kiểm thử quy tắc tie và các con số tiền tệ, đầu vào `BigDecimal` từ chuỗi sẽ giúp thể hiện ý định chính xác hơn.

## 8. Chọn chế độ theo yêu cầu sử dụng

Không có một chế độ tốt nhất cho mọi bài toán. Hãy chọn theo quy tắc của dữ liệu và người tiêu thụ kết quả.

| Tình huống | Lựa chọn cần cân nhắc | Vì sao |
|---|---|---|
| Báo cáo thống kê nhiều phép làm tròn | `HALF_EVEN` | Có thể giảm xu hướng sai lệch khi nhiều giá trị ở điểm hòa |
| Quy định nghiệp vụ yêu cầu hòa thì ra xa 0 | `HALF_UP` | Quy tắc dễ giải thích cho cả số dương lẫn âm |
| Cắt bớt chữ số, luôn hướng về 0 | `DOWN` | Thể hiện rõ ý định cắt bỏ phần vượt quá độ chính xác |
| Tìm giới hạn làm tròn theo hướng lên/xuống trục số | `CEILING` / `FLOOR` | Hướng được định nghĩa theo `+∞` / `-∞` |
| Dữ liệu bắt buộc đã đúng độ chính xác | `UNNECESSARY` | Lỗi rõ ràng nếu phải làm tròn làm đổi giá trị |

Các tình huống về tiền tệ cần đặc biệt thận trọng: quy tắc làm tròn, đơn vị tiền, số chữ số và vị trí áp dụng phải theo đặc tả sản phẩm, quy định pháp lý hoặc hợp đồng. Không suy ra rằng cứ dùng `NumberFormat.getCurrencyInstance(...)` là tự động đáp ứng mọi luật làm tròn tiền.

Một bộ định dạng tiền tệ theo locale vẫn có thể cấu hình `RoundingMode`:

```java
import java.text.NumberFormat;

NumberFormat usd = NumberFormat.getCurrencyInstance(Locale.US);
usd.setRoundingMode(RoundingMode.HALF_UP);

String amount = usd.format(new BigDecimal("1234.565"));
// Với ký hiệu tiền tệ và quy tắc của Locale.US: "$1,234.57"
```

`NumberFormat` là lớp cơ sở. Các bộ định dạng số thập phân thông dụng hỗ trợ `setRoundingMode(...)`, nhưng API của lớp cơ sở cho phép một số triển khai ném `UnsupportedOperationException`. Nếu cần dựa vào hành vi hoặc cấu hình riêng của `DecimalFormat`, hãy làm việc với đối tượng `DecimalFormat` cụ thể.

## 9. Lỗi thường gặp và cách tránh

**Lỗi 1 — Chỉ đặt `RoundingMode` mà không giới hạn chữ số.** Nếu bộ định dạng vẫn hiển thị đủ độ chính xác đầu vào, quy tắc làm tròn có thể không phát huy tác dụng. Hãy kiểm tra mẫu định dạng, `getMinimumFractionDigits()` và `getMaximumFractionDigits()`.

**Lỗi 2 — Nhầm `DOWN` với `FLOOR`, hoặc `UP` với `CEILING`.** Với số âm, cặp chế độ này cho kết quả khác nhau. Hãy có test cho cả `2.345` và `-2.345`.

**Lỗi 3 — Cho rằng `HALF_UP` luôn làm tròn lên.** `HALF_UP` chọn kết quả gần nhất và chỉ ra xa số 0 khi đúng điểm hòa. Với `2.341` và hai chữ số, `HALF_UP` cho `2.34`, không phải `2.35`.

**Lỗi 4 — Cho rằng `HALF_EVEN` luôn làm tròn xuống.** `2.345` → `2.34`, nhưng `2.355` → `2.36`.

**Lỗi 5 — Không xác định locale khi so sánh chuỗi.** Dấu phân cách thập phân và hàng nghìn tùy `DecimalFormatSymbols`/`Locale`. Với test cần so sánh stdout cố định, hãy truyền `Locale.US`; với giao diện thực tế, dùng locale được yêu cầu.

**Lỗi 6 — Tưởng rằng chuỗi đã định dạng thay đổi số gốc.** `format()` chỉ tạo chuỗi hiển thị. Nếu nghiệp vụ thực sự cần giá trị đã làm tròn, phải lưu rõ kết quả số học (`BigDecimal.setScale(...)`) tại bước phù hợp.

**Lỗi 7 — Dùng một `DecimalFormat` dùng chung cho nhiều luồng.** `DecimalFormat` là đối tượng có trạng thái thay đổi được và không được bảo đảm an toàn khi nhiều luồng truy cập đồng thời mà không đồng bộ. Thông thường hãy tạo bộ định dạng theo phạm vi lời gọi/tác vụ, hoặc thiết kế chiến lược sử dụng và đồng bộ phù hợp.

**Lỗi 8 — Tin rằng hiển thị hai chữ số đảm bảo mọi phép tính chính xác hai chữ số.** Bước định dạng cuối không thay thế chính sách độ chính xác của toàn bộ chuỗi tính toán. Hãy kiểm tra scale, vị trí làm tròn và cách cộng tổng theo yêu cầu nghiệp vụ.

## 10. Bài tập tự kiểm tra

Giả sử dùng `new DecimalFormat("0.00", DecimalFormatSymbols.getInstance(Locale.US))`, định dạng các giá trị `BigDecimal` tạo từ **chuỗi**. Hãy đoán kết quả trước khi chạy:

1. `1.225` với `HALF_EVEN`.
2. `1.235` với `HALF_EVEN`.
3. `-1.225` với `CEILING`.
4. `-1.225` với `FLOOR`.
5. `2.300` với `UNNECESSARY`.
6. `2.301` với `UNNECESSARY`.

**Đáp án và lý do:**

1. `1.22`: giữa `1.22` và `1.23`, chọn chữ số cuối chẵn (`2`).
2. `1.24`: giữa `1.23` và `1.24`, chọn chữ số cuối chẵn (`4`).
3. `-1.22`: hướng về dương vô cực.
4. `-1.23`: hướng về âm vô cực.
5. `2.30`: chỉ bỏ số 0 thừa, không thay đổi giá trị.
6. Ném `ArithmeticException`: muốn về hai chữ số phải làm tròn bỏ phần khác 0.

Khi kiểm thử chức năng định dạng số, tối thiểu nên có trường hợp số dương, số âm, ở đúng điểm hòa, gần nhưng không ở điểm hòa, giá trị đã đúng độ chính xác và giá trị không được phép làm tròn.

## Ghi nhớ

- **Độ chính xác hiển thị** được quyết định bởi mẫu `DecimalFormat` hoặc các phương thức điều chỉnh số chữ số; **hướng làm tròn** do `RoundingMode` quyết định.
- `HALF_UP`, `HALF_DOWN`, `HALF_EVEN` khác nhau **chỉ ở trường hợp hòa**; với các giá trị khác, chúng cùng chọn giá trị gần nhất.
- `UP`/`DOWN` xét hướng so với **0**; `CEILING`/`FLOOR` xét hướng theo **trục số**.
- `DecimalFormat.format(...)` tạo `String` và giữ nguyên giá trị đầu vào; `BigDecimal.setScale(...)` trả về một giá trị số mới.
- Với kết quả cần chính xác về dấu và quy tắc làm tròn, dùng giá trị thập phân có kiểm soát và test cả trường hợp âm lẫn điểm hòa.