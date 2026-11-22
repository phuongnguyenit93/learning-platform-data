# Nested generic record pattern trong Java 21

## 1. Nested generic record pattern là gì?

**Nested generic record pattern** là record pattern lồng trong record pattern khác, trong đó một hoặc nhiều record mang tham số kiểu generic (`T`, `L`, `R`...). Java có thể **giải cấu trúc nhiều tầng** và **suy luận kiểu của pattern variable** từ kiểu được khai báo ở từng tầng.

Xét một record đơn giản:

```java
record Box<T>(T value) {}
```

`Box<String>` có component `value` kiểu `String`; `Box<Box<String>>` có component là một `Box<String>`. Với biến tĩnh kiểu `Box<Box<String>>`, ta có thể viết:

```java
Box<Box<String>> nested = new Box<>(new Box<>("Java 21"));

if (nested instanceof Box(Box(var text))) {
    // Compiler suy luận: text có kiểu String.
    System.out.println(text.toUpperCase());
}
```

Đây là **hai record pattern** lồng nhau: `Box(...)` bên ngoài giải cấu trúc một `Box<Box<String>>`; `Box(var text)` bên trong giải cấu trúc component `Box<String>` để lấy chuỗi. Cú pháp không phải một constructor call, cũng không phải kiểu `Box<Box<...>>` mới. Nó mô tả việc matching dữ liệu hiện có.

Điều đặc biệt là **không cần viết type arguments tường minh** ở cả hai record pattern: trình biên dịch dùng thông tin kiểu của biểu thức được so khớp để suy luận. Record patterns trở thành tính năng chính thức ở **Java 21** theo JEP 440; mã dùng cú pháp này biên dịch với JDK 21 trở lên mà không cần `--enable-preview`.

## 2. Tách ba khái niệm: generic, nesting và pattern matching

Một nested generic record pattern kết hợp ba cơ chế có vai trò khác nhau:

| Cơ chế | Câu hỏi mà nó giải quyết | Ví dụ |
| --- | --- | --- |
| Generic record | Component chứa kiểu gì theo khai báo? | `record Box<T>(T value) {}` |
| Nested record | Bên trong một record có một record khác không? | `Box<Box<String>>` |
| Record pattern | Giá trị có khớp cấu trúc record và các pattern con không? | `Box(Box(var text))` |

Với:

```java
record Box<T>(T value) {}

Box<Box<String>> outer = new Box<>(new Box<>("hello"));
```

kiểu tĩnh của `outer` là `Box<Box<String>>`. Khi xét `outer instanceof Box(Box(var text))`:

1. **Tầng ngoài:** kiểu đối tượng được so khớp là `Box<Box<String>>`. Pattern `Box(...)` suy luận đối số kiểu tương ứng là `Box<String>`.
2. **Lấy component:** Java gọi accessor `value()` của `Box` bên ngoài. Giá trị component có kiểu tĩnh `Box<String>`.
3. **Tầng trong:** pattern `Box(...)` thứ hai suy luận đối số kiểu là `String`, rồi lấy component của record bên trong.
4. **Biến lá:** `var text` được suy luận là `String`. Nếu cả hai tầng đều khớp, `text` được ràng buộc và dùng trong nhánh thành công.

Vì `text` được suy luận là `String`, biểu thức `text.toUpperCase()` hợp lệ **ngay khi biên dịch**. Với một component kiểu `Integer`, compiler suy luận tương tự thành `Integer`; không cần ép kiểu thủ công tại mỗi tầng.

Không có “ép kiểu generic đầy đủ bằng reflection” xảy ra ở runtime. **Thông tin type arguments phục vụ phân tích kiểu tĩnh**, còn matching runtime kiểm tra các kiểu record có thể kiểm tra được và áp dụng pattern ở từng component.

## 3. Ví dụ hoàn chỉnh: `Box<Box<String>>`

Lưu vào `NestedBoxDemo.java`:

```java
import java.util.Locale;

public class NestedBoxDemo {
    record Box<T>(T value) {}

    public static void main(String[] args) {
        Box<Box<String>> nested =
                new Box<>(new Box<>("Java 21"));

        if (nested instanceof Box(Box(var text))) {
            String typed = text; // Biên dịch được: text là String.
            System.out.println("nested=" + typed.toUpperCase(Locale.ROOT));
        }
    }
}
```

Chạy với JDK 21 trở lên:

```bash
javac --release 21 NestedBoxDemo.java
java NestedBoxDemo
```

Kết quả:

```text
nested=JAVA 21
```

Từ trái sang phải, hai `Box` trong `Box(Box(var text))` tương ứng với hai tầng record. Nếu viết:

```java
if (nested instanceof Box(var inner)) {
    // inner có kiểu Box<String>; đây mới giải cấu trúc một tầng.
}
```

thì `inner` là **cả record bên trong**, chưa phải chuỗi. Ngược lại, `Box(Box(var text))` đi sâu thêm một tầng và đưa ra component kiểu `String`.

Có thể nêu rõ type arguments của mỗi pattern khi chúng an toàn trong ngữ cảnh tĩnh:

```java
if (nested instanceof Box<Box<String>>(Box<String>(var text))) {
    System.out.println(text);
}
```

Với biến `nested` khai báo đúng kiểu `Box<Box<String>>`, đây là cách biểu đạt tường minh. Tuy nhiên, cú pháp `Box(Box(var text))` thường gọn hơn, dễ tái cấu trúc hơn và cho compiler thực hiện suy luận.

## 4. Ví dụ nhiều tham số kiểu: `Envelope<Pair<String, Integer>>`

Generic record có thể mang **nhiều type parameter** và được lồng ở vị trí component của record khác. Ta khai báo:

```java
record Pair<L, R>(L left, R right) {}
record Envelope<T>(String id, T payload) {}
```

Với `Envelope<Pair<String, Integer>>`, pattern `Envelope(var id, Pair(var state, var retries))` suy luận `id` và `state` là `String`, còn `retries` là `Integer`.

Chương trình độc lập `NestedPairDemo.java`:

```java
public class NestedPairDemo {
    record Pair<L, R>(L left, R right) {}
    record Envelope<T>(String id, T payload) {}

    public static void main(String[] args) {
        Envelope<Pair<String, Integer>> message =
                new Envelope<>("msg-7", new Pair<>("READY", 3));

        if (message instanceof Envelope(
                var id,
                Pair(var state, var retries))) {

            String eventId = id;
            String status = state;
            int nextRetry = retries + 1; // Unboxing Integer -> int.

            System.out.println(eventId + " | " + status
                    + " | next=" + nextRetry);
        }
    }
}
```

```bash
javac --release 21 NestedPairDemo.java
java NestedPairDemo
```

Kết quả:

```text
msg-7 | READY | next=4
```

**Suy luận theo từng tầng:**

- `message` có kiểu `Envelope<Pair<String, Integer>>`.
- `Envelope(...)` nhận hai component theo khai báo: `id` kiểu `String`, `payload` kiểu `Pair<String, Integer>`.
- `Pair(...)` mở `payload` ra hai component: `left` kiểu `String`, `right` kiểu `Integer`.
- `var` chỉ khai báo pattern variable và suy luận kiểu tương ứng; nó **không chuyển** giá trị từ kiểu này sang kiểu khác. Riêng phép `retries + 1` dùng cơ chế unboxing thông thường của Java.

Nếu có thêm một tầng generic, ta lồng tiếp record pattern:

```java
record Box<T>(T value) {}
record Pair<L, R>(L left, R right) {}
record Envelope<T>(String id, T payload) {}

Envelope<Pair<Box<String>, Integer>> job =
        new Envelope<>("job-9", new Pair<>(new Box<>("ok"), 4));

if (job instanceof Envelope(
        var id,
        Pair(Box(var token), var retries))) {
    // token: String; retries: Integer; id: String.
    System.out.println(id + " | " + token
            + " | retries=" + retries);
}
```

Đoạn trên là minh họa **trong một phạm vi Java nơi các record đã được khai báo**. Kết quả khi nhánh khớp là:

```text
job-9 | ok | retries=4
```

Tầng lồng có thể sâu hơn khi mô hình dữ liệu yêu cầu, nhưng nên dùng tên component/biến dễ hiểu để tránh pattern trở thành một dòng khó đọc.

## 5. Suy luận kiểu phụ thuộc vào kiểu tĩnh của đầu vào

Compiler **không đọc giá trị runtime** để đoán rằng một object đang chứa `String`. Nó lấy thông tin từ kiểu được khai báo tại chỗ dùng pattern.

### Có thông tin kiểu tĩnh

```java
Box<Box<String>> known = new Box<>(new Box<>("safe"));

if (known instanceof Box(Box(var value))) {
    String text = value; // Hợp lệ.
}
```

Compiler có đủ dữ kiện để suy luận `value` là `String`.

### Chỉ biết `Object`

```java
Object unknown = new Box<>("hello");

if (unknown instanceof Box(var data)) {
    // data có kiểu Object, chưa thể gọi data.toUpperCase().
    System.out.println(data.getClass().getSimpleName());
}
```

Dù tại runtime `unknown` tình cờ chứa `Box<String>`, biến `data` trong pattern trên được suy luận với kiểu tĩnh `Object`. Dòng `String name = data;` sẽ gây **lỗi biên dịch** vì không thể tự động gán `Object` cho `String`.

Nếu mục tiêu thực sự là kiểm tra *giá trị component* là chuỗi, hãy dùng **type pattern** ở vị trí component:

```java
if (unknown instanceof Box(String text)) {
    System.out.println(text.toUpperCase());
}
```

Pattern `Box(String text)` áp dụng kiểm tra kiểu `String` cho **component hiện tại**. Nó không khẳng định rằng runtime xác nhận đầy đủ type argument của mọi `Box<T>` trong hệ thống; điều được kiểm tra là **giá trị component** có phù hợp với type pattern đó hay không.

Điều này giúp phân biệt hai tuyên bố:

- **“Compiler biết `T` là `String` từ khai báo `Box<String>`.”** Đây là thông tin kiểu tĩnh.
- **“Runtime phân biệt được `Box<String>` với `Box<Integer>` chỉ bằng type argument.”** Điều này không đúng nói chung, vì **type erasure**.

## 6. Type erasure và giới hạn `instanceof` với generic record

Java generic dùng cơ chế **xóa kiểu** (*type erasure*). Thông thường, `Box<String>` và `Box<Integer>` đều có cùng lớp runtime `Box`; không thể dựa vào runtime class của `Box` để xác nhận mọi type argument.

Đoạn minh họa **không biên dịch**, cố ý nêu lỗi:

```java
record Box<T>(T value) {}

static void invalid(Object unknown) {
    if (unknown instanceof Box<String>(var text)) {
        System.out.println(text);
    }
}
```

Với `unknown` có kiểu `Object`, compiler không thể thực hiện phép chuyển kiểu được kiểm tra an toàn sang `Box<String>` mà pattern trên yêu cầu. Tương tự, nếu đối số là raw type `Box`, mã `raw instanceof Box<String>(var text)` cũng có thể bị từ chối vì cần unchecked conversion. Đây là giới hạn có chủ đích của generic record pattern, không phải lỗi của `var`.

Thay vào đó, khi thực sự cần xác định giá trị component là `String` từ một `Object`, có thể viết:

```java
static void inspect(Object unknown) {
    if (unknown instanceof Box(String text)) {
        System.out.println("String component: " + text);
    }
}
```

`Box(String text)` kiểm tra record `Box` và **tiếp tục kiểm tra component là `String`**. Với dữ liệu nhiều tầng nhưng thiếu thông tin generic tĩnh, cần mô tả và kiểm tra component ở những tầng thích hợp, thay vì cố ép kiểu tham số hóa không thể kiểm chứng.

**Không dùng raw type hoặc unchecked cast chỉ để “ép” compiler chấp nhận pattern.** Nếu một cấu trúc generic thực tế chứa dữ liệu không đúng cam kết kiểu, chương trình có thể gặp lỗi khi tiêu thụ giá trị sau matching. Hãy ưu tiên lưu giữ kiểu generic chính xác ở API và model, hoặc dùng type pattern kiểm tra component khi nhận dữ liệu từ biên `Object`.

## 7. Wildcard và generic ở record lồng nhau

Generic record pattern còn có thể làm việc khi đầu vào khai báo wildcard mà ràng buộc trên vẫn cung cấp thông tin cần thiết:

```java
record Box<T>(T value) {}

static void printNested(Box<? extends Box<String>> input) {
    if (input instanceof Box(Box(var text))) {
        String value = text; // Kiểu suy luận vẫn là String.
        System.out.println(value);
    }
}
```

`? extends Box<String>` nói rằng component bên ngoài thuộc một kiểu con phù hợp với `Box<String>`. Do `Box` là record và record vốn `final`, ví dụ này vẫn là một kiểu khai báo generic hợp lệ giúp compiler truyền ràng buộc vào tầng bên trong. Khi wildcard không còn thông tin về component cụ thể, `var` sẽ suy luận kiểu tổng quát hơn; không thể tùy tiện giả định `String`.

Đây là lý do nên đọc **khai báo kiểu hoàn chỉnh**, bao gồm các wildcard và bound, trước khi kết luận pattern variable có kiểu nào.

## 8. `null` ở tầng ngoài, tầng trong và biến `var`

Một record pattern không khớp `null`, kể cả khi record pattern đó được lồng bên trong. Nhưng component của record có thể bằng `null`; một type pattern dạng `var` đặt trực tiếp tại vị trí component có thể là **null-matching**.

Lưu vào `NestedNullDemo.java`:

```java
public class NestedNullDemo {
    record Box<T>(T value) {}

    public static void main(String[] args) {
        Box<Box<String>> missingInner = new Box<>(null);
        Object missingOuter = null;

        System.out.println("nested="
                + (missingInner instanceof Box(Box(var text))));

        System.out.println("direct="
                + (missingInner instanceof Box(var inner)));

        System.out.println("outer="
                + (missingOuter instanceof Box(var inner)));

        if (missingInner instanceof Box(var child)) {
            System.out.println("childIsNull=" + (child == null));
        }
    }
}
```

```bash
javac --release 21 NestedNullDemo.java
java NestedNullDemo
```

Kết quả:

```text
nested=false
direct=true
outer=false
childIsNull=true
```

Giải thích:

- `missingInner` là một `Box` hợp lệ, nhưng component của nó là `null`. `Box(Box(var text))` thất bại tại **pattern `Box(...)` bên trong** vì record pattern không nhận `null`.
- `Box(var inner)` khớp `Box` bên ngoài; `var inner` ràng buộc component `null` trong trường hợp này.
- `missingOuter` là `null`, nên pattern `Box(...)` bên ngoài thất bại ngay từ đầu.

Vì vậy, khi một cấu trúc nested generic có component tùy chọn, hãy lựa chọn rõ: muốn pattern lồng nhau **yêu cầu có record con**, hay muốn ràng buộc record con vào biến để tự xử lý `null`.

## 9. Nested generic record pattern trong `switch`

`switch` trong Java 21 cho phép dùng record patterns ở các nhánh `case`. Tương tự `instanceof`, các type argument của generic record pattern có thể được suy luận từ ngữ cảnh.

Lưu vào `NestedSwitchDemo.java`:

```java
public class NestedSwitchDemo {
    record Pair<L, R>(L left, R right) {}
    record Envelope<T>(String id, T payload) {}

    static String describe(Envelope<Pair<String, Integer>> input) {
        return switch (input) {
            case null -> "empty";

            case Envelope(var id, Pair(var label, var count))
                    -> id + ":" + label + "/" + count;

            default -> "missing payload";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(
                new Envelope<>("r1", new Pair<>("ok", 2))));
        System.out.println(describe(new Envelope<>("r2", null)));
        System.out.println(describe(null));
    }
}
```

```bash
javac --release 21 NestedSwitchDemo.java
java NestedSwitchDemo
```

Kết quả:

```text
r1:ok/2
missing payload
empty
```

`case Envelope(var id, Pair(var label, var count))` chỉ khớp khi selector là `Envelope` và component `payload` khớp record pattern `Pair(...)`. Với payload `null`, Java xét `default`; với selector `null`, Java xét `case null`.

Lưu ý: nếu `switch` có thể nhận `null` nhưng không có nhánh `case null` thích hợp, Java có thể ném `NullPointerException`. Và không được cho rằng nhánh lồng nhau luôn khớp chỉ vì kiểu tĩnh đúng: một component `null` vẫn khiến record pattern tương ứng thất bại.

## 10. Tại runtime, nested pattern thực hiện những gì?

Với `Envelope(var id, Pair(var state, var retries))` trên một `Envelope<Pair<String, Integer>>`, có thể hình dung các bước:

1. Kiểm tra giá trị đầu vào không phải `null` và thuộc record `Envelope` phù hợp.
2. Lấy từng component của record bằng **accessor** tương ứng (`id()` và `payload()`).
3. Ràng buộc `id`; tiếp tục kiểm tra giá trị `payload` với record pattern `Pair(...)`.
4. Nếu `payload` khác `null` và khớp `Pair`, lấy `left()` và `right()` rồi ràng buộc `state`, `retries`.
5. Khi các pattern con đều khớp, chương trình được dùng các pattern variable trong nhánh thành công.

Đây là **một phép matching đệ quy**, không phải lời gọi constructor `Envelope(...)` hoặc `Pair(...)`. Nó cũng không tạo bản sao của các record trong lúc matching.

Accessor được viết tường minh trong record vẫn được Java gọi khi matching. Bởi vậy, nên thiết kế accessor ổn định, tránh tác dụng phụ khó đoán. Nếu accessor ném ngoại lệ trong lúc record pattern lấy component, matching kết thúc bất thường (theo đặc tả Java 21, thông qua `MatchException` với nguyên nhân gốc), thay vì đơn giản trả `false`.

Với pattern lồng nhiều tầng, **đừng dựa vào thứ tự hoặc số lần accessor được gọi như một hợp đồng nghiệp vụ**. Hãy dùng pattern để mô tả cấu trúc và giữ logic có tác dụng phụ trong mã ứng dụng riêng.

## 11. Phạm vi biến và kết hợp điều kiện

Pattern variable tồn tại ở vị trí Java xác định matching đã thành công (*flow scoping*). Ví dụ trong một phương thức đã biết kiểu `Envelope<Pair<String, Integer>>`:

```java
if (message instanceof Envelope(var id, Pair(var state, var retries))
        && retries > 0) {
    System.out.println(id + ": " + state);
}
```

Ở vế sau toán tử `&&`, các biến đã được xác lập bởi pattern bên trái, nên có thể dùng `retries` ở đó. Điều này hoạt động nhờ **short-circuit evaluation**: nếu matching thất bại, Java không đánh giá điều kiện còn lại.

Không được đọc `id`, `state` hoặc `retries` ngoài phạm vi mà compiler bảo đảm các biến đã được gán. Với component `Integer` có khả năng `null`, phép so sánh `retries > 0` sẽ unbox `Integer` và có thể ném `NullPointerException`; cần thêm điều kiện phù hợp nếu model cho phép dữ liệu `null`.

## 12. Những lỗi phổ biến và cách sửa

| Lỗi hoặc hiểu nhầm | Giải thích và cách sửa |
| --- | --- |
| Nghĩ `Box(Box(var x))` là gọi constructor hai lần | Đây là hai record pattern, thực hiện matching trên giá trị đã có |
| Nghĩ `var` luôn suy luận đúng kiểu runtime | Kiểu của `var` dựa trên **kiểu tĩnh**; với đầu vào `Object`, generic type arguments có thể không còn cụ thể |
| Kiểm tra `Object` bằng `Box<String>(...)` | Type argument `String` không luôn kiểm chứng được qua type erasure; dùng pattern con như `Box(String text)` khi cần kiểm tra giá trị |
| Dùng raw `Box` rồi đòi suy luận nested generic chặt chẽ | Raw type làm mất cam kết kiểu; giữ `Box<T>` đầy đủ tại API |
| Đặt sai số component trong pattern | Số component pattern phải khớp đúng số component khai báo của record |
| Giả sử generic record pattern tự kiểm tra toàn bộ type argument ở runtime | Runtime chỉ kiểm tra được những phép thử kiểu hợp lệ của record và các pattern con |
| Dùng `Box(Box(var x))` khi inner component có thể `null` | Record pattern trong không khớp `null`; nếu muốn xử lý riêng, dùng `Box(var inner)` rồi kiểm tra |
| Dùng biến pattern ngoài nhánh thành công | Pattern variables tuân theo flow scoping của Java |
| Dùng tính năng này với `--release 17` | Nested record patterns chuẩn hóa từ Java 21; với JDK 21 trở lên dùng `--release 21` |
| Viết pattern cho một class thường có `value()` giống record | Record pattern yêu cầu kiểu là **record class**; tên accessor tương tự không đủ |

## 13. Cách chọn độ sâu phù hợp

Hãy dùng nested generic record pattern khi:

- Dữ liệu được mô hình hóa tự nhiên thành các record lồng nhau và kiểu generic đã được khai báo rõ.
- Cần truy cập các component ở nhiều tầng trong nhánh `if` hoặc `switch`.
- Muốn compiler kiểm tra kiểu tĩnh và giảm các phép cast thủ công.
- Các tầng `null` đã được xác định rõ trong thiết kế dữ liệu.

Nếu pattern có quá nhiều tầng, khó đặt tên hoặc chứa nhiều điều kiện nghiệp vụ, nên tách việc đọc record con thành những bước dễ hiểu. Ví dụ có thể matching `Envelope(var id, var payload)` rồi xử lý `payload` ở đoạn kế tiếp. Điều này vẫn tận dụng kiểu generic và dễ kiểm tra `null`.

**Quy tắc cần nhớ:** `Box(Box(var text))` giúp giải cấu trúc hai tầng, và Java suy luận `text` từ **kiểu generic tĩnh của từng tầng**. Pattern còn tuân theo kiểm tra record, pattern con, `null` và flow scoping; nó không phải phép kiểm tra tùy ý đối với type arguments đã bị xóa ở runtime.

## Tham khảo chính thức

- [Oracle Java SE 21 — Record Patterns: Generic Records, Type Inference và Nested Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Java Language Specification 21 — §14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Java Language Specification 21 — §18.5.5 Record Pattern Type Inference](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html#jls-18.5.5)
