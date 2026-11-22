# Pattern component chứa sealed type trong nested record patterns (Java 21+)

## 1. Vấn đề: thành phần của record có kiểu sealed

Trong Java, một `record` có thể có **component** được khai báo bằng một `sealed interface` hoặc `sealed class`. Kiểu sealed giới hạn những kiểu được phép kế thừa/triển khai nó. Nếu các kiểu được phép có những `record` cụ thể, ta có thể dùng **nested record pattern** để đồng thời:

1. Khớp record bên ngoài.
2. Xem component sealed bên trong đang mang đối tượng thuộc biến thể nào.
3. Nếu biến thể đó là record, tiếp tục tách các component của record con.
4. Ràng buộc các giá trị nhận được vào biến pattern.

Ví dụ cấu trúc dữ liệu:

```java
sealed interface Payload permits Text, Metric {}

record Text(String value) implements Payload {}
record Metric(int count) implements Payload {}

record Envelope(String id, Payload payload) {}
```

`payload` có **kiểu khai báo** là `Payload` (sealed interface), nhưng ở thời điểm chạy có thể chứa `new Text("OK")`, `new Metric(7)` hoặc `null`.

Thay vì lấy `envelope.payload()` rồi kiểm tra kiểu và ép kiểu thủ công, có thể viết:

```java
if (object instanceof Envelope(var id, Text(var text))) {
    System.out.println(id + " -> " + text);
}
```

Đây là một **record pattern lồng nhau**: `Envelope(...)` khớp record bên ngoài; `Text(var text)` khớp **một kiểu record được sealed interface cho phép** và lấy thành phần `value` của nó. Biến `id` được suy luận là `String`; `text` cũng là `String`.

**Điểm mấu chốt:** bản thân `Payload` chỉ là interface, nên **`Payload(...)` không phải record pattern hợp lệ**. Ta đặt record pattern `Text(...)` / `Metric(...)` vào vị trí component có kiểu `Payload` vì kiểu thực tế của component có thể là những record ấy.

## 2. Cơ chế khớp và vai trò của sealed

Giả sử đối tượng đang xét là:

```java
new Envelope("M-2", new Metric(7))
```

Khi gặp `Envelope(var id, Metric(int n))`, Java lần lượt:

1. Kiểm tra đối tượng bên ngoài có phải `Envelope` không và không phải `null`.
2. Lấy các component thông qua accessor của `Envelope`: `id()` và `payload()`.
3. Ràng buộc `id`; khớp `payload` với record `Metric`.
4. Lấy `Metric.count()`, ràng buộc `n = 7`; nếu mọi pattern con thành công, nhánh được chọn.

Pattern `Envelope(var id, Text(var text))` không khớp đối tượng này vì `payload` đang là `Metric`, không phải `Text`.

Lợi thế quan trọng của `sealed` trong `switch` là **phân tích tính bao phủ (exhaustiveness)**. Nếu `Payload` chỉ cho phép `Text` và `Metric`, hai nhánh sau có thể bao phủ mọi **giá trị non-null** thuộc các biến thể được phép của component:

```java
return switch (envelope) {
    case Envelope(var id, Text(var text)) -> "Text: " + text;
    case Envelope(var id, Metric(int n)) -> "Metric: " + n;
};
```

Trình biên dịch Java 21 hiểu mối quan hệ giữa record bên ngoài, kiểu sealed của component và các kiểu con được phép. Vì vậy, với tập biến thể đã khép kín, `switch` có thể được coi là exhaustive **mà không cần `default`**.

Tuy nhiên, **exhaustive tại thời điểm biên dịch không đồng nghĩa xử lý an toàn mọi trường hợp `null`**: `new Envelope("X", null)` không khớp `Text(...)` hay `Metric(...)`. Một `switch` được compiler chấp nhận vẫn có thể ném `MatchException` khi gặp component null như vậy. Cần có chiến lược xử lý null phù hợp.

## 3. Ví dụ đầy đủ: record con, class con và null

Lưu đoạn sau thành file **`SealedPayloadPatternDemo.java`**. Ví dụ dùng Java 21 trở lên, không cần bật preview.

```java
public class SealedPayloadPatternDemo {

    sealed interface Payload permits Text, Count, Reject {}

    record Text(String value) implements Payload {}
    record Count(int value) implements Payload {}

    // Một nhánh được phép của sealed interface không nhất thiết là record.
    static final class Reject implements Payload {}

    record Envelope(String id, Payload payload) {}
    record Batch(Envelope envelope) {}

    static String explain(Envelope envelope) {
        return switch (envelope) {
            case null ->
                    "Envelope null";

            // var payload là pattern component bao phủ cả null.
            case Envelope(var id, var payload) when payload == null ->
                    id + ": payload null";

            // Component có kiểu Payload, nhưng giá trị thực tế là Text.
            case Envelope(var id, Text(var body)) ->
                    id + ": text=" + body;

            case Envelope(var id, Count(int count)) ->
                    id + ": count=" + count;

            // Reject là class thông thường: dùng type pattern, không có (...).
            case Envelope(var id, Reject rejected) ->
                    id + ": reject";
        };
    }

    public static void main(String[] args) {
        System.out.println(
                explain(new Envelope("T-1", new Text("OK"))));

        System.out.println(
                explain(new Envelope("M-2", new Count(7))));

        System.out.println(
                explain(new Envelope("R-3", new Reject())));

        System.out.println(explain(new Envelope("E-4", null)));
        System.out.println(explain(null));

        // String value trong Text có thể null; var body nhận được null.
        System.out.println(
                explain(new Envelope("T-5", new Text(null))));

        // Hai lớp record lồng nhau: Batch -> Envelope -> Count.
        Object candidate =
                new Batch(new Envelope("B-6", new Count(9)));

        if (candidate instanceof Batch(
                Envelope(var id, Count(int count)))) {
            System.out.println("Batch " + id + ": " + count);
        }
    }
}
```

Biên dịch và chạy bằng JDK 21+:

```bash
javac --release 21 SealedPayloadPatternDemo.java
java SealedPayloadPatternDemo
```

Stdout:

```text
T-1: text=OK
M-2: count=7
R-3: reject
E-4: payload null
Envelope null
T-5: text=null
Batch B-6: 9
```

Giải thích:

- `Payload permits Text, Count, Reject` khóa danh sách kiểu con trực tiếp. `Text` và `Count` là record (mặc định `final`); `Reject` là class `final` thông thường.
- `Envelope(var id, Text(var body))` và `Envelope(var id, Count(int count))` vừa xét kiểu biến thể vừa tách dữ liệu bên trong.
- `Envelope(var id, Reject rejected)` chỉ kiểm tra kiểu và lấy đối tượng `Reject`; cú pháp `Reject(...)` sẽ sai vì `Reject` không phải record.
- `case null` xử lý chính **selector** `envelope` là null. Nó khác với việc **component** `envelope.payload()` là null.
- `case Envelope(var id, var payload) when payload == null` bắt component null mà không che khuất các nhánh cụ thể khác. `when` là guard của nhánh `switch`.
- `Text(var body)` chấp nhận giá trị `null` của thành phần `String value` vì kiểu suy luận của `var body` bao phủ đúng kiểu thành phần đó. Lưu ý: `Text(...)` vẫn yêu cầu chính đối tượng `Text` không null.
- `Batch(Envelope(var id, Count(int count)))` minh họa nhiều tầng lồng nhau. Nếu `Batch.envelope()` là null, pattern `Envelope(...)` bên trong sẽ không khớp.

## 4. Null: phân biệt ba cấp độ

Khi nested record patterns làm việc với sealed component, có ít nhất ba vị trí có thể chứa `null`:

| Vị trí | Ví dụ | Ý nghĩa với pattern |
| --- | --- | --- |
| Đối tượng bên ngoài | `explain(null)` | Không khớp bất kỳ record pattern `Envelope(...)` nào; có thể dùng `case null` trong `switch`. |
| Component sealed | `new Envelope("X", null)` | Không khớp `Text(...)`, `Count(...)` hay `Reject rejected`; cần kiểm tra null hoặc một pattern bao phủ null. |
| Component bên trong record con | `new Envelope("X", new Text(null))` | `Text(var body)` vẫn khớp; biến `body` nhận `null`. |

Quy tắc Java 21 tinh tế hơn câu “mọi type pattern đều không khớp null”: **type pattern nằm trực tiếp trong danh sách component của record pattern là *null-matching* khi nó bao phủ toàn bộ kiểu khai báo của component đó**. Ví dụ, tại vị trí `Payload payload`, `var payload` hoặc `Payload payload` khớp được null. Trái lại, `Text t` ở cùng vị trí không bao phủ mọi `Payload`, nên không khớp null. Đây là lý do guard kiểm tra `payload == null` trong ví dụ chạy được.

Với record pattern lồng thêm một mức, `Text(var body)` chỉ yêu cầu **đối tượng Text không null**; bản thân `body` có thể null. Không nên nhầm `Text(null)` với `null` thay cho cả đối tượng `Text`.

## 5. Exhaustiveness, thứ tự nhánh và thay đổi phân cấp sealed

### Bao phủ mọi kiểu được permits cho phép

Để một `switch` không có `default` được coi là exhaustive, compiler phải suy ra các pattern bao phủ mọi biến thể thích hợp của kiểu sealed. Nếu thêm một kiểu con:

```java
record Empty() implements Payload {}
```

thì đồng thời phải sửa `permits` thành danh sách có `Empty`, rồi cập nhật những `switch` cần nhánh mới, ví dụ:

```java
case Envelope(var id, Empty()) -> id + ": empty";
```

Nếu một biến thể mới chưa được xử lý, `switch` không có nhánh bao phủ phù hợp có thể bị báo **không exhaustive** khi biên dịch lại. Đây là lợi ích khi mô hình hóa trạng thái hữu hạn bằng sealed types: thay đổi mô hình khiến các vị trí xử lý thiếu nhánh dễ được phát hiện.

Một kiểu con `non-sealed` cho phép các lớp con của nó mở rộng tiếp; khi đó có thể dùng type pattern khớp kiểu `non-sealed` ấy để bao phủ cả nhánh phân cấp liên quan. Các kiểu con không nhất thiết đều là record.

### Thứ tự nhánh phải tránh domination

Nhánh quá rộng có thể làm các nhánh cụ thể phía sau không thể tới được. Ví dụ:

```java
// Sai: nhánh đầu quá rộng, bao phủ cả Text và Count.
// switch (envelope) {
//     case Envelope(var id, var payload) -> "Có Envelope";
//     case Envelope(var id, Text(var body)) -> body; // dominated
// };
```

Nên đặt các nhánh cụ thể trước. Nếu cần một nhánh rộng chỉ dùng cho trường hợp nhất định, thêm guard như `when payload == null`; nhánh đã guard không tự động bao phủ mọi giá trị của `payload`.

Tương tự, `case Envelope(var id, Count(int n)) when n > 0` chỉ xử lý `Count` có `n > 0`. Một nhánh duy nhất có guard như vậy không bao phủ `Count(0)` hay `Count(-1)`; cần thêm nhánh xử lý các giá trị còn lại nếu muốn `switch` exhaustive.

### Exhaustive không đồng nghĩa miễn mọi lỗi lúc chạy

Khi một component sealed mang `null`, các nhánh subtype không thể khớp; nếu không có nhánh xử lý phù hợp, `switch` exhaustive có thể ném `MatchException`. `MatchException` cũng có thể xuất hiện do sự khác biệt giữa các phiên bản class đã biên dịch (ví dụ phân cấp sealed thay đổi mà nơi dùng `switch` chưa được biên dịch lại). Những trường hợp này khác với lỗi compile-time vì thiếu nhánh.

## 6. Lỗi phổ biến và cách dùng thực tế

1. **Dùng sealed interface như một record pattern:** `Envelope(Payload(var x))` không hợp lệ vì `Payload` không phải record. Dùng `Envelope(var p)` để lấy component tổng quát, `Envelope(Text(var x))` để tách biến thể record, hoặc `Envelope(Payload p)` nếu muốn ràng buộc theo kiểu interface.
2. **Quên một kiểu con được phép:** Nếu `permits` có class thường, không thể chỉ viết các nhánh record rồi mặc định đã xử lý mọi biến thể. Cần thêm type pattern tương ứng hoặc một nhánh phù hợp.
3. **Nhầm null ở nhiều lớp:** `case null` xử lý selector; nó không tự xử lý `new Envelope("X", null)`. Cũng cần phân biệt null của record con với null trong component của record con.
4. **Dùng pattern rộng trước pattern hẹp:** `Envelope(var id, var payload)` không có guard sẽ bao phủ cả các trường hợp cần xử lý riêng, gây dominated case khi khai báo nhánh cụ thể sau đó.
5. **Hiểu sai `var`:** `var` trong record pattern là suy luận **kiểu tĩnh** từ khai báo component, không phải kiểu động tự thay đổi. Trong `Envelope(var id, var payload)`, compiler biết `id` có kiểu `String` và `payload` có kiểu `Payload`.
6. **Cho rằng sealed luôn thay thế kiểm tra dữ liệu:** `sealed` giới hạn cấu trúc phân cấp kiểu, nhưng không đảm bảo giá trị component khác null, hợp lệ về nghiệp vụ hay không gây ngoại lệ khi gọi accessor.

Nested record patterns đặc biệt hữu ích với mô hình dữ liệu phân nhánh như kết quả thành công/thất bại, thông điệp sự kiện, cây cú pháp hoặc các trạng thái của một workflow. Đặt `sealed` ở component giúp compiler biết các biến thể có thể xuất hiện, còn record patterns giúp diễn đạt chính xác cấu trúc dữ liệu muốn tách.

**Ghi nhớ:** Khi một record có component kiểu sealed, hãy đặt **pattern của từng kiểu con thực tế** vào vị trí component. Với kiểu con là record, có thể deconstruct sâu bằng `TypeCon(... )`; với class thường, dùng type pattern. Kiểm tra tính bao phủ, null và thứ tự nhánh để code đúng cả lúc biên dịch lẫn lúc chạy.

### Tài liệu tham khảo

- Oracle Java 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- Java SE 21 API — MatchException: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/MatchException.html
