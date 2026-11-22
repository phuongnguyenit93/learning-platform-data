# Ảnh hưởng của guard khi kiểm tra dominance và type coverage

Trong Java 21, pattern matching for `switch` cho phép thêm guard bằng từ khóa `when` để chỉ chọn một nhánh khi pattern khớp và điều kiện bổ sung đúng. Guard ảnh hưởng đến hai kiểm tra tĩnh quan trọng của compiler: **dominance** (một nhãn có che khuất nhãn phía sau hay không) và **type coverage** (các nhãn đã bao phủ hết kiểu đầu vào hay chưa).

Điểm cốt lõi là compiler không thể giả định một guard thông thường sẽ trả về `true`. Vì guard có thể trả về `false` khi chạy, pattern có guard như vậy không được xem là bao phủ toàn bộ kiểu mà pattern nhận diện. Ngoại lệ là guard có giá trị là biểu thức hằng `true` theo quy tắc của Java.

## 1. Guard được kiểm tra sau khi pattern khớp

Cấu trúc một case có guard trong Java 21:

```java
case String text when text.isBlank() -> "blank";
```

Java kiểm tra giá trị có phải `String` trước. Chỉ khi pattern khớp, guard `text.isBlank()` mới được đánh giá. Nếu guard trả về `true`, nhánh được chọn; nếu trả về `false`, switch tiếp tục xét các nhãn sau.

```java
static String classify(Object value) {
    return switch (value) {
        case String text when text.isBlank() -> "blank";
        case String text -> "non-blank text";
        default -> "other";
    };
}
```

Với chuỗi trắng, nhánh đầu được chọn. Với chuỗi không trắng, pattern đầu khớp nhưng guard sai; nhãn `String` thứ hai tiếp tục xử lý giá trị. Đây là lý do nhãn guarded đứng trước nhãn không guard cùng kiểu có thể hợp lệ.

## 2. Guard và quy tắc dominance

Dominance là kiểm tra lúc biên dịch để phát hiện một nhãn `case` phía sau chắc chắn không thể được chọn vì nhãn trước đã bao phủ mọi giá trị mà nó có thể nhận.

Với các pattern tương thích, một nhãn pattern phía trước có thể dominate nhãn phía sau khi pattern phía trước bao phủ pattern phía sau và nhãn trước không có guard, hoặc guard của nó là biểu thức hằng có giá trị `true`.

Ví dụ, pattern không guard `String` bao phủ mọi giá trị `String`, nên nhãn guarded cùng kiểu phía sau bị dominate:

```java
// Không hợp lệ: nhãn String đầu tiên dominate nhãn thứ hai.
static String invalidOrder(Object value) {
    return switch (value) {
        case String text -> "text";
        // case String text when text.isBlank() -> "blank";
        default -> "other";
    };
}
```

Đảo thứ tự sẽ hợp lệ vì guard đầu tiên có thể sai. Khi đó nhãn `String` không guard phía sau nhận phần giá trị còn lại:

```java
static String validOrder(Object value) {
    return switch (value) {
        case String text when text.isBlank() -> "blank";
        case String text -> "text";
        default -> "other";
    };
}
```

Guard không phải biểu thức hằng `true` không làm nhãn trước dominate pattern rộng hơn tương thích phía sau. Compiler không chạy guard để chứng minh điều kiện đúng hay sai; nó dựa trên quy tắc tĩnh của ngôn ngữ.

## 3. Guard hằng `true` được xử lý như pattern không bị giới hạn

Java có thể xác định giá trị của biểu thức hằng ngay khi biên dịch. Nếu guard là biểu thức hằng có giá trị `true`, guard không loại trừ giá trị nào mà pattern có thể nhận. Vì vậy, trong các kiểm tra dominance và type coverage, nhãn đó được xem như pattern không có guard.

```java
// Không hợp lệ: guard true không giới hạn pattern String.
static String constantTrueGuard(Object value) {
    return switch (value) {
        case String text when true -> "text";
        // case String text -> "another text"; // bị dominate
        default -> "other";
    };
}
```

Ngược lại, một lời gọi phương thức dù trong thực tế luôn trả về `true` cũng không phải biểu thức hằng theo định nghĩa của Java:

```java
static boolean alwaysTrue() {
    return true;
}

static String methodGuard(Object value) {
    return switch (value) {
        case String text when alwaysTrue() -> "text";
        case String text -> "remaining text";
        default -> "other";
    };
}
```

Compiler không thực thi `alwaysTrue()` để phân tích dominance. Vì guard là lời gọi phương thức, nó có thể trả về `false` hoặc ném exception trong một lần chạy; do đó nhãn `String` thứ hai vẫn có thể được chọn và không bị dominate.

## 4. Guard và type coverage

Type coverage là cách compiler xác định những kiểu nào đã được các nhãn trong switch bao phủ. Nó được dùng để kiểm tra tính đầy đủ (exhaustiveness), đặc biệt với switch expression và switch statement sử dụng pattern labels.

Một pattern có guard chỉ đóng góp vào type coverage khi guard không có hoặc là biểu thức hằng có giá trị `true`. Guard thông thường không đóng góp type coverage vì nó có thể trả về `false`, khiến một phần giá trị thuộc kiểu đó chưa được xử lý.

Ví dụ với sealed hierarchy:

```java
sealed interface Shape permits Circle, Rectangle {}
record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}

static String describe(Shape shape) {
    return switch (shape) {
        case Circle circle when circle.radius() > 0 -> "positive circle";
        case Rectangle rectangle -> "rectangle";
    };
}
```

Switch expression trên chưa exhaustive. `Circle` có thể có bán kính không lớn hơn 0, làm guard trả về `false`; không có nhãn nào khác xử lý các giá trị `Circle` đó. Nhãn guarded `Circle` không đóng góp type coverage cho toàn bộ kiểu `Circle`.

Thêm một nhãn `Circle` không guard để xử lý phần còn lại:

```java
static String describeCompletely(Shape shape) {
    return switch (shape) {
        case Circle circle when circle.radius() > 0 -> "positive circle";
        case Circle circle -> "circle with non-positive radius";
        case Rectangle rectangle -> "rectangle";
    };
}
```

Giờ đây mọi `Circle` đều được xử lý: nếu guard đúng thì nhánh đầu chạy, nếu guard sai thì nhánh `Circle` không guard phía sau nhận giá trị. `Rectangle` được xử lý ở nhánh cuối, nên switch có đủ type coverage cho sealed hierarchy `Shape`.

## 5. Guard hằng `true` có thể đóng góp type coverage

Vì guard hằng `true` không loại trừ giá trị nào, pattern đó có thể đóng góp type coverage như pattern không guard. Ví dụ, `case Circle c when true` bao phủ toàn bộ kiểu `Circle` theo kiểm tra tĩnh.

```java
static String describeWithConstantGuard(Shape shape) {
    return switch (shape) {
        case Circle circle when true -> "circle";
        case Rectangle rectangle -> "rectangle";
    };
}
```

Ví dụ này exhaustive đối với các kiểu con được khai báo trong `Shape`. Tuy nhiên, guard `when true` không đem lại điều kiện lọc hữu ích; trong mã ứng dụng, nên bỏ guard nếu không có lý do rõ ràng để giữ nó.

## 6. Record pattern cũng phải bao phủ toàn bộ component

Type coverage không chỉ phụ thuộc guard. Một record pattern chỉ bao phủ toàn bộ kiểu record khi các component pattern của nó đều là total pattern đối với kiểu component tương ứng.

Ví dụ `Pair` có hai component kiểu `Object`. Pattern `Pair(String left, String right)` chỉ khớp khi cả hai component đều là chuỗi, vì vậy nó không bao phủ mọi instance của `Pair`:

```java
sealed interface Payload permits Pair, Text {}
record Pair(Object left, Object right) implements Payload {}
record Text(String value) implements Payload {}

static String read(Payload payload) {
    return switch (payload) {
        case Pair(String left, String right) -> "pair of strings";
        case Text(var value) -> value;
    };
}
```

Switch này chưa exhaustive: một `Pair` có component là `Integer`, `null` hoặc kiểu khác vẫn không khớp nhánh đầu. Nhánh `Text(var value)` là total cho `Text` vì `var` nhận mọi giá trị component thuộc kiểu đã khai báo.

Đổi thành record pattern total để bao phủ mọi `Pair`:

```java
static String readCompletely(Payload payload) {
    return switch (payload) {
        case Pair(var left, var right) -> "pair";
        case Text(var value) -> value;
    };
}
```

Các component pattern `var` đều total, vì vậy record pattern bao phủ mọi instance của `Pair`. Kết hợp với nhánh `Text`, switch có đủ type coverage cho `Payload`.

## 7. Phân biệt type coverage với xử lý null

`case null` xử lý giá trị null theo một nhãn riêng; nó không đóng góp type coverage cho một kiểu tham chiếu. `default` đóng vai trò nhánh bao phủ phần kiểu còn lại, nhưng theo quy tắc Java 21, `default` đơn lẻ không nhận selector `null`.

```java
static String describeNullable(Object value) {
    return switch (value) {
        case null -> "null";
        case String text when text.isBlank() -> "blank text";
        case String text -> "text";
        default -> "other";
    };
}
```

Trong ví dụ này, `case null` xử lý null. Hai nhãn `String` xử lý toàn bộ các giá trị chuỗi: guard đầu tiên lọc chuỗi trắng, nhãn thứ hai nhận phần còn lại. `default` xử lý các kiểu khác.

Khi selector có thể null và ứng dụng cần hành vi rõ ràng, hãy khai báo `case null` hoặc gộp với `default` bằng `case null, default`. Không suy luận rằng switch đã exhaustive về kiểu thì tự động có nghĩa là null cũng được xử lý.

## 8. Bảng tổng hợp quy tắc

| Case label | Có thể dominate pattern tương thích phía sau? | Đóng góp type coverage? |
|---|---|---|
| Pattern không có guard | Có, nếu pattern trước bao phủ pattern sau | Có, theo phần kiểu mà pattern bao phủ |
| Pattern có guard thông thường | Không dựa trên guard đó để dominate nhãn sau | Không |
| Pattern có guard là biểu thức hằng `true` | Có, như pattern không guard | Có, như pattern không guard |
| Pattern có guard là biểu thức hằng `false` | Không | Không |
| `case null` | Không dominate pattern theo kiểu | Không; xử lý null riêng |
| `default` | Là nhãn bao phủ phần còn lại theo quy tắc switch | Bao phủ phần type coverage còn lại |

Với record pattern, phần type coverage còn phụ thuộc các component pattern có total cho kiểu component hay không. Vì vậy, không thể chỉ nhìn tên record trong nhãn để kết luận toàn bộ kiểu record đã được bao phủ.

## 9. Cách thiết kế switch có guard

Khi viết switch expression hoặc switch statement dùng pattern labels, hãy thực hiện các bước sau:

1. Liệt kê các kiểu đầu vào có thể xuất hiện; với sealed hierarchy, xem đầy đủ các kiểu con được phép.
2. Đặt các pattern cụ thể trước pattern tổng quát để tránh dominance ngoài ý muốn.
3. Đặt guard cần lọc trước pattern không guard cùng kiểu; giữ nhánh không guard để nhận các giá trị guard từ chối nếu cần.
4. Kiểm tra type coverage: mọi kiểu con cần có nhánh không guard, guard hằng `true`, hoặc một pattern total bao phủ chúng.
5. Với record pattern, kiểm tra cả component pattern; một component pattern quá hẹp có thể làm record pattern không total.
6. Xử lý `null` riêng nếu selector có thể null.
7. Dùng compiler diagnostics để xác nhận dominance và exhaustiveness sau khi hoàn thiện các nhãn.

Không dùng một guard có vẻ luôn đúng trong dữ liệu hiện tại để thay thế nhánh bao phủ. Compiler chỉ xem guard là hằng `true` khi nó là biểu thức hằng theo quy tắc của Java; kết quả quan sát được khi chạy không làm thay đổi type coverage.

## 10. Biên dịch với Java 21

Pattern Matching for `switch` được hoàn thiện trong Java 21 qua JEP 441. Guard sử dụng từ khóa `when`; các ví dụ trong bài không cần bật Preview.

```bash
javac --release 21 -d out src/SwitchCoverageDemo.java
java -cp out SwitchCoverageDemo
```

Đặt compiler release hoặc toolchain về Java 21 để compiler kiểm tra đúng các quy tắc của phiên bản này. Không thêm `--enable-preview` cho pattern switch đã final trong Java 21.

## 11. Tài liệu tham khảo

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification, Java SE 21 — Switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java Language Specification, Java SE 21 — Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [Java Language Specification, Java SE 21 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Oracle — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
