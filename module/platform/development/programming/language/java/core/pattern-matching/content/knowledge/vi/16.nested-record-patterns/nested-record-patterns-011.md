# Kiểm thử các cấu trúc lồng không hợp lệ trong Nested Record Patterns (Java 21+)

## 1. Mục tiêu và phạm vi

**Nested record pattern** cho phép kiểm tra một giá trị và tách nhiều tầng `record` trong cùng một pattern. Khi kiểm thử, cần phân biệt rõ **pattern viết sai nên không biên dịch được** và **pattern hợp lệ nhưng dữ liệu thực tế không khớp khi chạy**. Hai trường hợp có cơ chế phát hiện và cách viết test khác nhau.

Record patterns trở thành tính năng chính thức từ **Java 21** (JEP 440). Các ví dụ sử dụng `instanceof` và chạy với JDK 21 trở lên, không cần `--enable-preview`. Java 17 hỗ trợ khai báo `record` nhưng chưa hỗ trợ record pattern trong `instanceof`.

Ví dụ mô hình gồm ba tầng:

```java
record Leaf(int id) {}
record Envelope(Leaf leaf, Object payload) {}
record Root(Envelope envelope) {}
```

Pattern hợp lệ:

```java
Object input = new Root(new Envelope(new Leaf(7), "data"));

if (input instanceof Root(Envelope(Leaf(var id), String text))) {
    System.out.println(id + " - " + text); // 7 - data
}
```

Cấu trúc khớp từ ngoài vào trong: `Root` có đúng **một** thành phần `Envelope`; `Envelope` có đúng **hai** thành phần (`Leaf` và `Object`); `Leaf` có đúng **một** thành phần `int`. Pattern `String text` thu hẹp thành phần `payload` có kiểu khai báo `Object`. Biến `id` và `text` chỉ dùng được ở đường đi đã khớp.

## 2. Phân loại trường hợp cần kiểm thử

| Nhóm | Ví dụ | Kết quả cần xác nhận |
| --- | --- | --- |
| **Pattern sai cấu trúc ở mã nguồn** | Sai số component, tách class không phải record, pattern con không tương thích kiểu, trùng tên biến | `javac` từ chối và báo lỗi biên dịch |
| **Pattern hợp lệ nhưng dữ liệu không khớp** | Sai kiểu đối tượng gốc, record con bằng `null`, giá trị động sai kiểu | `instanceof` trả về `false`, nhánh xử lý không chạy |
| **Pattern hợp lệ và dữ liệu khớp** | Đúng kiểu, đúng các tầng record, mọi pattern con khớp | `instanceof` trả về `true`, biến pattern được gán |
| **Lỗi khi thực thi accessor** | Accessor record được tự định nghĩa và ném ngoại lệ | Khớp pattern có thể ném `MatchException`; không được coi như `false` |

Một `record` được tạo đúng kiểu Java luôn có số component theo khai báo. Vì thế “dữ liệu thiếu/thừa component” **không phải** tình huống có thể đưa vào một record Java bình thường lúc runtime. Thiếu/thừa **pattern con trong mã nguồn** là lỗi do trình biên dịch bắt; `null` hoặc dữ liệu kiểu rộng không khớp là tình huống runtime riêng.

## 3. Kiểm thử runtime bằng chương trình Java tự chạy

Tạo file **`InvalidNestedPatternTests.java`**:

```java
public class InvalidNestedPatternTests {
    record Leaf(int id) {}
    record Envelope(Leaf leaf, Object payload) {}
    record Root(Envelope envelope) {}

    static void assertMatch(String name, boolean actual, boolean expected) {
        if (actual != expected) {
            throw new AssertionError(
                name + ": expected " + expected + ", got " + actual
            );
        }
        System.out.println(name + " => " + actual + " (OK)");
    }

    public static void main(String[] args) {
        Object valid = new Root(new Envelope(new Leaf(7), "data"));
        Object nullLeaf = new Root(new Envelope(null, "data"));
        Object nullEnvelope = new Root(null);
        Object wrongRoot = "not a Root";
        Object wrongPayload = new Root(new Envelope(new Leaf(7), 99));
        Object nullRoot = null;

        // Đúng mọi tầng, đúng kiểu payload, điều kiện id == 7.
        assertMatch("valid",
            valid instanceof Root(Envelope(Leaf(var id), String text))
                && id == 7,
            true);

        // Leaf là null nên Leaf(var id) không khớp.
        assertMatch("null-leaf",
            nullLeaf instanceof Root(Envelope(Leaf(var id), var payload)),
            false);

        // Envelope là null nên Envelope(...) không khớp.
        assertMatch("null-envelope",
            nullEnvelope instanceof Root(Envelope(var leaf, var payload)),
            false);

        // Giá trị ngoài cùng không phải Root.
        assertMatch("wrong-root",
            wrongRoot instanceof Root(Envelope(var leaf, var payload)),
            false);

        // payload được khai báo Object, thực tế là Integer, không phải String.
        assertMatch("wrong-payload",
            wrongPayload instanceof Root(Envelope(Leaf(var id), String text)),
            false);

        // Toàn bộ giá trị đem kiểm tra là null.
        assertMatch("null-root",
            nullRoot instanceof Root(Envelope(var leaf, var payload)),
            false);

        // var leaf nhận được null: không hề yêu cầu khớp Leaf(...).
        assertMatch("var-null-leaf",
            nullLeaf instanceof Root(Envelope(var leaf, var payload)),
            true);

        System.out.println("7/7 tests passed");
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 InvalidNestedPatternTests.java
java InvalidNestedPatternTests
```

**Stdout chính xác** nếu cả 7 phép thử đạt:

```text
valid => true (OK)
null-leaf => false (OK)
null-envelope => false (OK)
wrong-root => false (OK)
wrong-payload => false (OK)
null-root => false (OK)
var-null-leaf => true (OK)
7/7 tests passed
```

Nếu giá trị thực tế khác kỳ vọng, `assertMatch` ném `AssertionError`, nên quá trình chạy thất bại thay vì âm thầm in kết quả sai. Có thể chạy chương trình này trực tiếp trong CI bằng JDK 21+ mà không phụ thuộc thư viện test bên ngoài.

### Vì sao ca `var-null-leaf` lại khớp?

Cần phân biệt **record pattern con** `Leaf(var id)` với **pattern thành phần** `var leaf`:

- `Leaf(var id)` đòi hỏi thành phần thực sự là một `Leaf` khác `null`; `null` không khớp record pattern.
- `var leaf` lấy giá trị của component `leaf` theo kiểu tĩnh mà compiler suy luận; trong danh sách thành phần record, pattern này có thể nhận cả `null`.
- `Root(Envelope(var leaf, var payload))` vẫn thất bại nếu **toàn bộ `Envelope`** là `null`, vì ở tầng đó ta đang dùng record pattern `Envelope(...)`.

Vì thế không nên viết test với giả định “cứ có một component `null` thì mọi record pattern đều thất bại”. Hãy xem component ấy được kiểm tra bởi loại pattern nào.

### Vì sao ca `wrong-payload` hợp lệ để kiểm thử?

`Envelope.payload` được khai báo `Object`, nên nó có thể chứa `String`, `Integer` hoặc `null`. Pattern `String text` kiểm tra kiểu thực tế lúc chạy; với `Integer`, toàn bộ nested pattern trả về `false`.

Ngược lại, nếu component được khai báo là `String`, Java không cho truyền trực tiếp một `Integer` khi khởi tạo record chỉ để tạo “dữ liệu sai kiểu”. Muốn kiểm thử dữ liệu đa dạng, hãy mô hình hóa component kiểu rộng ở vị trí nghiệp vụ thực sự cho phép nhiều kiểu.

## 4. Kiểm thử pattern sai bằng negative compilation test

Các trường hợp sau **phải không biên dịch được**. Đây là các **negative tests**, nên một lần chạy `javac` có mã thoát khác 0 là kết quả mong đợi. Không nên đưa các đoạn sai vào chương trình runtime ở mục 3 vì chương trình sẽ không thể biên dịch.

Tạo file riêng **`BadNestedPatterns.java`** với một lỗi chủ đích:

```java
public class BadNestedPatterns {
    record Leaf(int id) {}
    record Envelope(Leaf leaf, String tag) {}

    static boolean test(Object input) {
        // Sai: Leaf chỉ có một component, nhưng pattern yêu cầu hai.
        return input instanceof Envelope(Leaf(var id, var extra), var tag);
    }
}
```

Kiểm tra:

```bash
javac --release 21 BadNestedPatterns.java
```

**Kỳ vọng:** biên dịch thất bại vì `Leaf` khai báo một component `id` nhưng `Leaf(var id, var extra)` có hai pattern con. Thông báo cụ thể phụ thuộc bản JDK; điều kiện test đáng tin cậy là **`javac` từ chối mã** và chỉ ra lỗi số lượng pattern.

Để kiểm thử ba lỗi tiếp theo, **thay duy nhất biểu thức bên phải `instanceof`** trong phương thức `test` của file trên, rồi chạy lại lệnh biên dịch. Mỗi biến thể phải được kiểm tra **riêng**, một lỗi tại một thời điểm:

| Biểu thức pattern sai | Lý do compiler phải từ chối |
| --- | --- |
| `Envelope(Leaf(var id, var extra), var tag)` | `Leaf` chỉ có 1 component, nhưng pattern có 2. |
| `Envelope(Leaf(var id), Leaf(var other))` | Component `tag` có kiểu `String`, không tương thích với pattern record `Leaf(...)`. |
| `Envelope(Leaf(var id), String(var text))` | `String` là class thường, không phải `record` nên không được tách bằng `String(...)`. |
| `Envelope(Leaf(var same), var same)` | Biến pattern `same` bị khai báo trùng trong cùng record pattern lồng. |

Cú pháp `Envelope(...)` phải có đúng hai pattern con theo thứ tự component. Tương tự, với mỗi record bên trong, cần kiểm tra tiếp số lượng và kiểu các component tại tầng đó.

Phiên bản **đã sửa**, dùng cùng hai record `Leaf` và `Envelope`, có thể viết:

```java
static boolean test(Object input) {
    return input instanceof Envelope(Leaf(var id), var tag) && id >= 0;
}
```

Đoạn này là **phương thức minh họa thay thế** bên trong class `BadNestedPatterns` ở trên. `id` khả dụng ở vế phải `&&` vì vế phải chỉ chạy khi pattern bên trái khớp.

### Cách tổ chức negative tests trong dự án

1. Mỗi mẫu mã sai được để trong một file kiểm thử biên dịch **riêng**, tách khỏi thư mục source của ứng dụng chạy được.
2. Gọi `javac --release 21` cho từng mẫu và xác nhận **exit code khác 0**.
3. Đối chiếu nhóm lỗi compiler (arity, non-record, incompatible type, duplicate binding) thay vì so khớp nguyên văn lỗi, vì định dạng chẩn đoán có thể thay đổi theo JDK.
4. Có ít nhất một **positive control** biên dịch thành công để chắc chắn môi trường JDK và lệnh biên dịch thực sự hoạt động; chương trình ở mục 3 là positive control.
5. Nếu một negative test bỗng biên dịch thành công, test đó **FAIL** và cần xem lại kỳ vọng về ngôn ngữ; đừng diễn giải “javac không báo lỗi” thành PASS.

Có thể bổ sung trường hợp ngoặc lồng sai, chẳng hạn thiếu `)`, để kiểm tra lỗi cú pháp thuần túy. Tuy nhiên, nên phân biệt lỗi cú pháp với bốn lỗi ngữ nghĩa pattern ở bảng trên.

## 5. Những trường hợp không nên đánh đồng với “pattern không hợp lệ”

### 5.1. `null` là dữ liệu không khớp, không phải lỗi biên dịch

`input instanceof Root(Envelope(Leaf(var id), var payload))` là biểu thức hợp lệ. Nếu `input`, `envelope` hoặc `leaf` bằng `null` tại tầng đang cần record pattern thì phép khớp trả về `false`. Không nên mong đợi `NullPointerException` chỉ vì `instanceof` gặp `null`.

### 5.2. Biến pattern chỉ tồn tại trên nhánh đã khớp

Đoạn sau hợp lệ:

```java
if (input instanceof Root(Envelope(Leaf(var id), var payload))
        && id > 0) {
    System.out.println(id);
}
```

Nhưng sử dụng `id` ở vế phải `||` theo mẫu dưới đây **không hợp lệ** vì nhánh phải có thể được đánh giá khi pattern trái không khớp:

```java
// Ví dụ sai, chỉ dùng cho negative compilation test.
if (input instanceof Root(Envelope(Leaf(var id), var payload))
        || id > 0) {
    System.out.println("checking");
}
```

Đây là lỗi **flow scoping** (phạm vi biến theo luồng điều khiển), không phải do cấu trúc record bị thiếu component.

### 5.3. Ngoại lệ từ accessor không phải kết quả `false`

Record pattern truy cập các component thông qua **accessor** của record. Nếu accessor được tự định nghĩa và ném ngoại lệ, phép khớp có thể ném `MatchException` với nguyên nhân là ngoại lệ của accessor, thay vì đơn giản trả về `false`. Vì vậy, trong hệ thống có custom accessor, cần kiểm thử riêng đường đi lỗi của accessor và không nuốt ngoại lệ thành “dữ liệu không khớp”.

### 5.4. Không dùng cú pháp preview khi kiểm thử cú pháp Java 21 chuẩn

Để test hành vi chính thức của record pattern trong Java 21, dùng `javac --release 21` và tránh các cú pháp từ tính năng preview khác. Một test bất ngờ biên dịch trên JDK mới hơn có thể đến từ thay đổi ngôn ngữ hoặc cờ preview; nên cố định Java release và phiên bản công cụ trong CI.

## 6. Checklist thiết kế test case

| Câu hỏi | Cách xác minh |
| --- | --- |
| Đúng số component mỗi tầng? | Negative compilation test cho thiếu/thừa pattern con. |
| Mọi tầng đều là `record` khi dùng `Type(...)`? | Negative compilation test cho class thường như `String(...)`. |
| Kiểu pattern con tương thích component? | Negative compilation test cho kiểu không thể chuyển đổi. |
| Biến pattern có trùng tên hay bị dùng sai scope? | Negative compilation test. |
| Record con hoặc root bằng `null`? | Runtime test, kỳ vọng `false` nếu vị trí đó dùng record pattern. |
| Component kiểu rộng chứa subtype không mong muốn? | Runtime test, kỳ vọng `false` với type pattern không khớp. |
| Một component `null` được lấy bằng `var`? | Runtime test xác nhận vẫn có thể khớp. |
| Nhánh thành công lấy đúng giá trị và điều kiện `&&`? | Positive runtime test kiểm tra biến và kết quả xử lý. |
| Accessor có thể ném ngoại lệ? | Test ngoại lệ `MatchException` riêng khi hệ thống dùng accessor tự định nghĩa. |

## 7. Bài tập tự luyện

Cho:

```java
record Coordinate(int x, int y) {}
record Segment(Coordinate start, Coordinate end) {}
```

1. Hãy viết pattern hợp lệ lấy `start.x` và `end.y` từ một `Object` chứa `Segment`.
2. Tạo negative test với `Segment(Coordinate(var x), var end)`. Nó sai ở tầng nào?
3. Với `new Segment(null, new Coordinate(3, 4))`, dự đoán kết quả khi match cả `start` bằng `Coordinate(...)`; sau đó đổi pattern của `start` sang `var start` và giải thích sự khác biệt.

Đáp án tham khảo:

```java
Object candidate = new Segment(
    new Coordinate(1, 2),
    new Coordinate(3, 4)
);
if (candidate instanceof Segment(
        Coordinate(var startX, var startY),
        Coordinate(var endX, var endY))) {
    System.out.println(startX + " -> " + endY); // 1 -> 4
}
```

Ở câu 2, `Coordinate` có hai component nên `Coordinate(var x)` sai số lượng pattern con ngay khi **biên dịch**. Ở câu 3, record pattern cho `start` không khớp `null` nên toàn bộ pattern thất bại; `var start` có thể nhận `null` và cho phép phần `end` khớp tiếp.

**Tài liệu chuẩn:** [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html) và [JEP 440 — Record Patterns](https://openjdk.org/jeps/440).
