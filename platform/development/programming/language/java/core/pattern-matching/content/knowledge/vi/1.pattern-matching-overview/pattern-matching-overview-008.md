# Giới hạn của pattern matching trong Java 21

Pattern matching giúp Java kiểm tra một giá trị có khớp với **mẫu** (pattern) hay không, đồng thời lấy ra dữ liệu đã được kiểm tra kiểu. Trong Java 21, hai trường hợp chính là **type pattern** (thường dùng với `instanceof` hoặc `switch`) và **record pattern** (tách các thành phần của `record`, kể cả mẫu lồng nhau). Cú pháp gọn hơn ép kiểu thủ công, nhưng pattern matching **không phải** công cụ kiểm tra mọi điều kiện, thay thế hệ kiểu, hoặc tự động xác thực dữ liệu nghiệp vụ.

## 1. Chỉ khớp những dạng pattern mà ngôn ngữ hỗ trợ

- **Type pattern** kiểm tra kiểu đối tượng tại runtime rồi khai báo biến, chẳng hạn `value instanceof String text`. Biến `text` chỉ dùng được tại những vị trí mà trình biên dịch chứng minh phép khớp đã thành công.
- **Record pattern** tách dữ liệu theo các *component* đã khai báo của một `record`, ví dụ `case Point(var x, var y)`. Nó không tự tách trường của mọi class thông thường, không truy cập tùy ý vào private field và không tạo cơ chế deconstruction tùy biến cho class.
- Trong Java 21, không có pattern cú pháp sẵn để tách từng phần tử của array/`List`, so khớp regex, hay ràng buộc số học. Có thể dùng `when` trong `switch` hoặc điều kiện `&&` với `instanceof` để kiểm tra thêm, nhưng đó là **điều kiện bổ sung**, không phải kiểu pattern mới.
- Type pattern trong các tính năng ổn định của Java 21 chủ yếu dành cho **kiểu tham chiếu**. Không viết `case int n` như một primitive type pattern trong Java 21; `switch` trên `int` vẫn dùng nhãn hằng `case 1`, `case 2`, v.v.

Ví dụ `Point` phải là `record` thì cú pháp tách thành phần sau mới dùng trực tiếp được:

```java
record Point(int x, int y) {}

static String show(Object value) {
    return switch (value) {
        case Point(var x, var y) -> "(" + x + ", " + y + ")";
        default -> "not a point";
    };
}
```

Đây là đoạn mã minh họa cần đặt trong một class hoặc một ngữ cảnh Java hợp lệ; riêng nó không phải tệp chạy độc lập.

## 2. Khớp cấu trúc không đồng nghĩa dữ liệu hợp lệ

`record User(String name, int age) {}` vẫn cho phép tạo `new User(null, -2)` nếu constructor không kiểm tra. Mẫu `User(var name, var age)` chỉ tách hai component; nó **không chứng minh** `name` có nội dung hay `age` hợp lệ.

Trong `switch`, dùng `when` để kiểm tra thêm những điều kiện nghiệp vụ cần thiết:

```java
record User(String name, int age) {}

static String describe(User user) {
    return switch (user) {
        case null -> "missing user";
        case User(var name, var age)
                when name != null && !name.isBlank() && age >= 0
                -> name + " (" + age + ")";
        case User(var name, var age) -> "invalid user";
    };
}
```

Đoạn này là minh họa cần đặt trong một class. Nhánh `User(var name, var age)` cuối cùng xử lý những bản ghi đã đúng kiểu nhưng không qua điều kiện `when`. Với dữ liệu quan trọng, xác thực ở constructor, domain service hoặc validation layer vẫn cần thiết; pattern matching chỉ giúp *đọc và phân nhánh* theo dữ liệu.

## 3. Không vượt qua được type erasure của generics

Java xóa phần lớn thông tin đối số kiểu generic lúc runtime (*type erasure*). Vì vậy, nếu biến đầu vào có kiểu `Object`, không thể khẳng định mọi phần tử đều là `String` bằng cách khớp `List<String>`:

```java
// KHÔNG BIÊN DỊCH khi value có kiểu Object:
if (value instanceof java.util.List<String> strings) {
    // ...
}
```

Hãy khớp kiểu có thể kiểm tra ở runtime, rồi kiểm tra từng phần tử nếu nghiệp vụ cần:

```java
if (value instanceof java.util.List<?> items) {
    for (Object item : items) {
        if (item instanceof String text) {
            System.out.println(text);
        }
    }
}
```

Hai đoạn trên là minh họa bên trong một method có biến `value`. `List<?>` chỉ chứng minh đó là một `List`; nó **không** bảo đảm mọi phần tử là `String`. Ép kiểu không kiểm tra như `(List<String>) value` cũng không khôi phục được bằng chứng kiểu đã bị xóa.

## 4. `null` cần được xử lý riêng

- `null instanceof String` trả về `false`; type pattern của `instanceof` không khớp với `null`.
- `switch` dùng pattern trên giá trị tham chiếu thường ném `NullPointerException` khi selector là `null`, trừ khi có nhánh xử lý `null` thích hợp như `case null`. **`default` đơn lẻ không phải nhánh bắt `null`.**
- Một record có thể chứa component tham chiếu bằng `null`. Tách component bằng `var` không tự xác thực rằng thành phần đó khác `null`; phải kiểm tra trước khi gọi method trên nó.

Ví dụ, `case null -> "missing"` là cách chỉ rõ cách xử lý selector rỗng. Khi dùng `when text != null && ...`, phép kiểm tra `null` dành cho **component** được tách khỏi record chứ không chỉ cho chính selector.

## 5. Phạm vi của pattern variable phụ thuộc luồng điều khiển

Trình biên dịch dùng *flow scoping*: một pattern variable chỉ xuất hiện ở nơi có thể chứng minh mẫu đã khớp.

```java
static void printIfText(Object value) {
    if (value instanceof String text && !text.isBlank()) {
        System.out.println(text.trim()); // hợp lệ: text đã được gán
    }

    // System.out.println(text); // LỖI: ngoài phạm vi của text
}
```

Với phép `&&`, vế phải chỉ chạy nếu vế trái đúng, nên có thể dùng `text` ở vế phải. Ngược lại, đừng dựa vào `text` sau phép `||`, vì một nhánh có thể đúng mà `instanceof` vẫn sai:

```java
// KHÔNG BIÊN DỊCH: text không chắc chắn đã được gán khi nhánh || còn lại đúng.
if (value instanceof String text || value == null) {
    System.out.println(text);
}
```

Các ví dụ là những đoạn bên trong class/method thích hợp, không phải chương trình độc lập. Khi biểu thức điều kiện phức tạp, tách điều kiện hoặc dùng `if`/early return sẽ dễ đọc và dễ kiểm chứng hơn.

## 6. `switch` có quy tắc về thứ tự, tính bao phủ và `when`

**Dominance (nhánh bao phủ nhánh khác).** Một nhánh kiểu rộng đặt trước có thể làm nhánh kiểu hẹp phía sau không bao giờ được chọn. Java báo lỗi biên dịch thay vì âm thầm để nhánh đó vô dụng:

```java
// KHÔNG BIÊN DỊCH trong một pattern switch có selector kiểu Object:
case CharSequence chars -> "character sequence";
case String text -> "string"; // bị nhánh CharSequence phía trước bao phủ
```

Đặt nhánh cụ thể trước nhánh tổng quát. Các nhánh có `when` cũng phải xét độ bao phủ; điều kiện bảo vệ có thể khiến một kiểu được khớp ở nhánh đầu nhưng vẫn cần nhánh dự phòng cùng kiểu phía sau.

**Exhaustiveness (bao phủ mọi khả năng).** `switch` expression phải đầy đủ; `switch` statement dùng pattern cũng thuộc nhóm enhanced switch và phải đầy đủ. Khi selector có kiểu mở như `Object`, thường cần `default`. Với một sealed interface, compiler có thể xác nhận đủ nhánh cho tất cả các subtype được phép; nếu thay đổi hierarchy sealed, phải rà soát `switch` liên quan.

**Guard `when` không thay thế nhánh dự phòng.** Nếu chỉ có `case Circle(var r) when r > 0`, trường hợp `Circle` có bán kính không dương vẫn chưa được xử lý. Hãy bổ sung `case Circle(var r)` không có guard, hoặc nhánh tổng quát phù hợp.

**Không đánh đồng cú pháp.** `when` được dùng với pattern label trong `switch` Java 21; với `instanceof`, dùng `&&` để nối kiểm tra bổ sung. Các rule của `switch` bảo vệ tính toàn vẹn của phân nhánh, nhưng không thể quyết định thay bạn điều kiện nghiệp vụ nào là đúng.

## 7. Pattern matching không tự thay thiết kế dữ liệu hoặc bảo đảm hiệu năng

- Pattern matching giảm lặp lại `instanceof` và ép kiểu, nhưng không bảo đảm chạy nhanh hơn `if`/cast viết đúng cách. Hiệu năng còn phụ thuộc dữ liệu, compiler/JIT, phân nhánh và logic bên trong.
- Một chuỗi dài `case` kiểm tra các subtype có thể báo hiệu mô hình đối tượng đang thiếu hành vi chung. Khi đối tượng thực sự sở hữu hành vi, polymorphism hoặc một method trong interface đôi khi rõ ràng hơn.
- Record pattern rất hợp với dữ liệu dạng cấu trúc bất biến ở cấp component; nó không biến record thành cơ chế kiểm tra schema hay sao chép sâu đối tượng. Component tham chiếu có thể trỏ tới một đối tượng mutable.
- Với hierarchy không `sealed`, không được giả định đã liệt kê hết subtype. Với hierarchy `sealed`, vẫn phải cập nhật logic nếu tập subtype thay đổi.

## 8. Ví dụ hoàn chỉnh chạy trên Java 21

Tạo file **`PatternMatchingLimitsDemo.java`**:

```java
public class PatternMatchingLimitsDemo {
    sealed interface Payload permits Text, Count {}

    record Text(String value) implements Payload {}
    record Count(int value) implements Payload {}

    static String explain(Payload payload) {
        return switch (payload) {
            case null -> "missing";
            case Text(var value) when value != null && !value.isBlank()
                    -> "text=" + value;
            case Text(var ignored) -> "text unavailable";
            case Count(var value) when value > 0 -> "positive=" + value;
            case Count(var value) -> "non-positive=" + value;
        };
    }

    public static void main(String[] args) {
        Object source = " Java ";
        if (source instanceof String text && !text.isBlank()) {
            System.out.println(text.trim());
        }

        System.out.println(explain(new Text("hello")));
        System.out.println(explain(new Text(null)));
        System.out.println(explain(new Count(0)));
        System.out.println(explain(null));
    }
}
```

Biên dịch và chạy bằng **JDK 21** (không cần `--enable-preview`):

```bash
javac --release 21 PatternMatchingLimitsDemo.java
java PatternMatchingLimitsDemo
```

Stdout:

```text
Java
text=hello
text unavailable
non-positive=0
missing
```

Điểm cần quan sát: `instanceof` xác nhận `source` là chuỗi trước khi gọi `trim()`; nhánh record pattern có `when` chỉ nhận text khác `null` và không rỗng; nhánh `Text` kế tiếp bắt trường hợp dữ liệu chưa hợp lệ; `Count(0)` được xử lý bởi nhánh dự phòng; `case null` xử lý selector rỗng. `Payload` là sealed interface, nên hai subtype `Text` và `Count` đủ cho tính bao phủ các giá trị không `null` của ví dụ.

## 9. Cách chọn khi áp dụng

1. Cần kiểm tra một giá trị có thuộc một kiểu hay record cụ thể không? Dùng type/record pattern; dữ liệu từ record vẫn phải được kiểm tra nếu có ràng buộc.
2. Cần kiểm tra generic element type, regex, phạm vi giá trị, hay quy tắc nghiệp vụ? Dùng kiểm tra bổ sung tương ứng; pattern không tự chứng minh các điều này.
3. Cần phân nhánh nhiều kiểu bằng `switch`? Sắp xếp nhánh hẹp trước nhánh rộng; xử lý `null`, guard không đạt và tính đầy đủ một cách tường minh.
4. Cần dùng pattern variable ngoài điều kiện? Kiểm tra flow scoping, đặc biệt khi có `&&`, `||`, phủ định hoặc early return.
5. Nếu logic dài hoặc thay đổi thường xuyên, xem xét tách method, validation hoặc polymorphism để code dễ kiểm thử và bảo trì.

Pattern matching là công cụ **diễn đạt phép kiểm tra và trích xuất dữ liệu an toàn kiểu** trong những hình thức được Java 21 hỗ trợ. Giới hạn quan trọng nhất là phép khớp thành công chỉ cung cấp điều mà pattern thật sự kiểm tra; những tính chất còn lại phải được mô hình hóa và xác thực riêng.
