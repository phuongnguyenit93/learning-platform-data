# Biểu thức khởi tạo `null` và yêu cầu kiểu xác định trong Java 10+

*Chủ đề: `var` và biểu thức. Bài học dùng các quy tắc suy luận kiểu cục bộ có từ Java 10 và vẫn áp dụng trong Java hiện đại; ví dụ hoàn chỉnh tương thích JDK 17 trở lên.*

## 1. Mục tiêu của bài học

Sau khi học xong, bạn có thể:

1. Giải thích vì sao `var value = null;` là **lỗi biên dịch**, dù Java cho phép nhiều biến tham chiếu mang giá trị `null`.
2. Phân biệt **kiểu tĩnh của biểu thức khởi tạo** với **giá trị thực tế** của biểu thức khi chạy.
3. Khai báo đúng biến dự kiến ban đầu là `null`, hoặc xử lý giá trị có thể vắng mặt mà vẫn giữ kiểu xác định.
4. Phân tích `null` trong toán tử điều kiện, biểu thức `switch`, phương thức generic, `Optional` và cấu trúc dữ liệu.
5. Nhận diện các trường hợp initializer không cung cấp đủ ngữ cảnh kiểu cho `var`, đọc lỗi `javac` và kiểm tra kiểu bằng IDE.

Một nguyên tắc xuyên suốt: **`var` suy luận kiểu tại thời điểm biên dịch; `null` chỉ là một giá trị đặc biệt có thể được gán cho các kiểu tham chiếu.** Khai báo bằng `var` không làm Java trở thành ngôn ngữ kiểu động và không tự đảm bảo biến không bao giờ là `null`.

## 2. Vì sao `var x = null;` không hợp lệ?

### 2.1. `null` không cho trình biên dịch một kiểu biến cụ thể

Khi gặp:

```java
var age = 20;               // age: int
var name = "Java";          // name: String
var scores = new int[3];    // scores: int[]
```

Trình biên dịch suy ra kiểu từ **biểu thức khởi tạo**. Với `var age = 20;`, literal `20` có kiểu `int`; với `var name = "Java";`, literal chuỗi có kiểu `String`.

Hãy so sánh với chương trình **cố ý không biên dịch được**:

```java
// InvalidVarNull.java — ví dụ lỗi, không chạy được
public class InvalidVarNull {
    public static void main(String[] args) {
        var value = null; // Lỗi: không thể suy luận kiểu biến từ null
    }
}
```

Ở cấp độ ngôn ngữ, `null` literal có **null type** đặc biệt, không phải một kiểu tham chiếu cụ thể có thể dùng làm kiểu khai báo biến. Quy tắc suy luận kiểu biến cục bộ không chấp nhận kết quả suy luận chỉ là null type; do đó `var value = null;` không tạo ra biến kiểu `Object`, `String` hay một “kiểu null” dùng được trong Java.

Thử:

```bash
javac --release 17 InvalidVarNull.java
```

`javac` trả mã thoát lỗi (nonzero). Phần chẩn đoán thường nêu `cannot infer type for local variable value` và `variable initializer is 'null'`; định dạng và vị trí dấu mũ có thể khác giữa các JDK. Không có file lớp hợp lệ để chạy `java InvalidVarNull`, cũng không có stdout chương trình. Đây là **lỗi tại thời điểm biên dịch**, chưa phải `NullPointerException`.

### 2.2. Vì sao `String value = null;` lại được?

```java
String value = null;       // Hợp lệ
Integer count = null;      // Hợp lệ: Integer là kiểu tham chiếu
int number = 0;            // Hợp lệ
// int bad = null;         // Lỗi: primitive int không nhận null
```

Trong khai báo tường minh, `String` và `Integer` đã là **kiểu đích** của phép gán. Trình biên dịch biết `null` có thể chuyển đổi sang kiểu tham chiếu đó. Với `var`, bạn không cung cấp kiểu đích; trình biên dịch phải suy ra kiểu từ initializer, và `null` đơn lẻ không đủ.

Bảng phân biệt:

| Khai báo | Biên dịch? | Kiểu tĩnh của biến | Ý nghĩa |
| --- | --- | --- | --- |
| `String x = null;` | Có | `String` | Kiểu đích được viết rõ |
| `Object x = null;` | Có | `Object` | Kiểu đích được viết rõ |
| `Integer x = null;` | Có | `Integer` | Wrapper là kiểu tham chiếu |
| `var x = null;` | Không | Không tạo được kiểu | Initializer chỉ mang null type |
| `var x = (String) null;` | Có | `String` | Phép ép kiểu tạo biểu thức có kiểu `String` |
| `var x = (Object) null;` | Có | `Object` | Phép ép kiểu tạo biểu thức có kiểu `Object` |
| `var x = (null);` | Không | Không tạo được kiểu | Ngoặc không bổ sung kiểu |
| `int x = null;` | Không | — | Primitive không nhận `null` |

**Không hiểu nhầm rằng `null` là một đối tượng thuộc lớp `Object`.** `null` là giá trị đặc biệt của kiểu tham chiếu; gọi `getClass()` qua một tham chiếu đang là `null` sẽ phát sinh `NullPointerException`, không cho ra “lớp của null”.

## 3. Những cách viết đúng khi giá trị ban đầu là `null`

### 3.1. Dùng kiểu tường minh nếu cần biểu diễn trạng thái “chưa có”

Khi ý định là tạo một biến kiểu `String` chưa nhận được dữ liệu:

```java
String token = null;
if (token == null) {
    token = "generated";
}
System.out.println(token); // generated
```

Đây là trường hợp **không cần cố dùng `var`**. Kiểu tường minh mô tả hợp đồng ngay tại nơi khai báo; `null` biểu thị trạng thái tạm vắng mặt. Trong ứng dụng thực tế, cân nhắc liệu có thể khởi tạo ngay bằng giá trị hợp lệ hoặc thiết kế API biểu diễn việc vắng mặt rõ ràng hơn hay không.

### 3.2. Biểu thức đã được gán kiểu: ép kiểu `null`

```java
var text = (String) null;             // String
var sequence = (CharSequence) null;  // CharSequence
var anything = (Object) null;        // Object
```

Các phép ép kiểu trên hợp lệ; giá trị của cả ba biến **vẫn là `null`**. Chúng chỉ cung cấp thông tin kiểu lúc biên dịch. Không có đối tượng `String`, `CharSequence` hoặc `Object` nào được tạo ra.

Không dùng `(String) null` như cách “chữa cháy” mặc định: `String text = null;` rõ ý định hơn khi cần biến ban đầu là `null`. Đừng ép sang `Object` khi bạn thật sự cần `String`, vì sẽ mất khả năng gọi các thao tác dành riêng cho `String` mà không ép kiểu lại.

### 3.3. Dùng phương thức hoặc biến đã có kiểu xác định

Một phương thức có thể được khai báo trả về `String` nhưng khi chạy vẫn trả `null`:

```java
static String findName(boolean found) {
    return found ? "Lan" : null;
}

// Trong một phương thức khác:
var name = findName(false); // Kiểu tĩnh String, giá trị runtime null
```

`var` được phép ở đây, vì trình biên dịch suy luận từ **kiểu trả về đã khai báo** là `String`, không cần biết nhánh runtime nào sẽ chạy.

Tương tự:

```java
String possiblyMissing = null;
var copy = possiblyMissing; // Kiểu String, giá trị null
```

Lỗi `var x = null;` và nguy cơ `NullPointerException` là **hai vấn đề khác nhau**: một là initializer không cung cấp kiểu; vấn đề kia là dùng một giá trị tham chiếu đang bằng `null` tại runtime.

## 4. `null` trong toán tử điều kiện và biểu thức `switch`

### 4.1. Biểu thức có nhánh `null` vẫn có thể suy ra kiểu

Ví dụ:

```java
boolean missing = true;
var label = missing ? null : "ready"; // Kiểu String
System.out.println(label == null);   // true
```

Toán tử điều kiện `?:` xét kiểu của các nhánh theo quy tắc Java. Nhánh còn lại là biểu thức `String` nên biểu thức điều kiện có thể có kiểu `String` dù giá trị khi chạy là `null`.

Nhưng hai nhánh đều là `null` sẽ không cung cấp kiểu thích hợp cho `var`:

```java
// Ví dụ lỗi biên dịch:
boolean condition = true;
// var unknown = condition ? null : null;
```

Nếu phải biểu diễn một kiểu cụ thể, ghi rõ kiểu hoặc cung cấp kiểu cho nhánh tương ứng:

```java
String chosen = condition ? null : null; // Hợp lệ: có kiểu đích String
var typed = condition ? (String) null : null; // Kiểu String
```

**Đừng cho rằng một nhánh không `null` sẽ đảm bảo giá trị kết quả không `null`.** Kiểu tĩnh và nhánh được chọn lúc chạy là hai khía cạnh độc lập.

### 4.2. `switch` expression cũng phụ thuộc kiểu của các nhánh

Với Java 17 trở lên, có thể viết:

```java
int code = 1;
var status = switch (code) {
    case 0 -> "OK";
    case 1 -> null;
    default -> "UNKNOWN";
};
System.out.println(status == null); // true
```

`status` có kiểu `String`: các nhánh cho giá trị `String` định hướng kiểu của biểu thức, trong khi nhánh được chọn trả về `null`. Khi xử lý `status` về sau vẫn phải kiểm tra khả năng `null`.

Không sử dụng biểu thức `switch` chỉ để tạo ra một biến `null` chưa biết kiểu. Nếu ý định là giữ trạng thái chưa có giá trị, khai báo kiểu tường minh sẽ rõ ràng và dễ bảo trì hơn.

## 5. Chương trình hoàn chỉnh: kiểu đã biết vẫn có thể chứa `null`

Tạo tệp **`NullInitializationDemo.java`**:

```java
import java.util.Objects;
import java.util.Optional;

public class NullInitializationDemo {
    static String findName(boolean exists) {
        return exists ? "Lan" : null;
    }

    public static void main(String[] args) {
        String pending = null;
        System.out.println("pending-null=" + (pending == null));

        pending = "ready";
        System.out.println("pending=" + pending);

        var typedNull = (String) null;
        System.out.println("typed-null=" + (typedNull == null));

        var fromMethod = findName(false);
        System.out.println("method-null=" + (fromMethod == null));

        var branch = true ? null : "default";
        System.out.println("branch-null=" + (branch == null));

        var safeName = Objects.requireNonNullElse(fromMethod, "Guest");
        System.out.println("name=" + safeName);

        var maybeName = Optional.ofNullable(fromMethod);
        System.out.println("present=" + maybeName.isPresent());

        var emptyText = Optional.<String>ofNullable(null);
        System.out.println("optional-empty=" + emptyText.isEmpty());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 NullInitializationDemo.java
java NullInitializationDemo
```

Stdout chính xác:

```text
pending-null=true
pending=ready
typed-null=true
method-null=true
branch-null=true
name=Guest
present=false
optional-empty=true
```

Giải thích:

- `pending` được khai báo rõ là `String`, cho phép khởi tạo bằng `null` rồi gán lại bằng chuỗi.
- `typedNull` được suy ra là `String` từ phép ép kiểu; kiểm tra `== null` vẫn cho `true`.
- `fromMethod` là `String` vì chữ ký `findName` trả `String`, dù lời gọi này nhận `null`.
- `branch` suy ra `String` từ toán tử điều kiện, giá trị runtime theo nhánh là `null`.
- `Objects.requireNonNullElse` chọn `"Guest"` khi giá trị nguồn là `null`; kết quả không phải `null` nếu giá trị mặc định hợp lệ.
- `Optional.ofNullable` biến giá trị `null` thành `Optional.empty()`. Phần `<String>` tường minh ở lời gọi cuối cho biết kiểu phần tử ngay cả khi đối số chỉ là `null`.

Không có dòng nào cố gọi phương thức trên tham chiếu `null`, nên chương trình không phát sinh `NullPointerException`.

## 6. Yêu cầu kiểu xác định còn liên quan đến generics

### 6.1. Khi `var` không có kiểu đích, generic factory có thể suy ra `Object`

So sánh:

```java
// Đoạn minh họa trong một phương thức:
java.util.List<String> names = new java.util.ArrayList<>();
var otherNames = new java.util.ArrayList<String>();
var mixedValues = new java.util.ArrayList<>();
```

Kiểu tĩnh:

| Biến | Kiểu | Nguồn suy luận |
| --- | --- | --- |
| `names` | `List<String>` | Khai báo tường minh tạo ngữ cảnh kiểu cho `<>` |
| `otherNames` | `ArrayList<String>` | Constructor ghi rõ tham số `String` |
| `mixedValues` | `ArrayList<Object>` | `new ArrayList<>()` không có kiểu phần tử đích hẹp hơn trong ngữ cảnh `var` |

Do vậy, `mixedValues.add("Java")` và `mixedValues.add(10)` có thể đều hợp lệ, nhưng `String x = mixedValues.get(0);` lỗi biên dịch vì `get` trả `Object`. Đây là lỗi thiết kế kiểu trong initializer, **không phải lỗi do `null`**. Hai tình huống có cùng bài học: biểu thức khởi tạo phải mang đủ thông tin kiểu bạn thực sự muốn dùng.

### 6.2. `Optional.ofNullable(null)` và kiểu generic suy luận

`Optional.ofNullable` có tham số kiểu generic `T`. Xét:

```java
// Đoạn minh họa trong một phương thức:
var unknown = java.util.Optional.ofNullable(null);
var typed = java.util.Optional.<String>ofNullable(null);
java.util.Optional<String> declared =
        java.util.Optional.ofNullable(null);
```

- `unknown` suy ra kiểu **`Optional<Object>`** trong ngữ cảnh này, vì không có tham số kiểu hoặc kiểu đích hẹp hơn.
- `typed` có kiểu **`Optional<String>`** nhờ `<String>` truyền tường minh cho phương thức generic.
- `declared` có kiểu **`Optional<String>`** do kiểu ở vế trái cung cấp ngữ cảnh đích.

Ba `Optional` đều rỗng ở runtime; chúng không giống nhau về **thông tin kiểu trong mã nguồn**. Việc chọn kiểu `String` cho Optional không tự tạo ra một đối tượng `String` và cũng không thêm giá trị vào Optional.

Nếu không có giá trị ban đầu, bạn có thể dùng `Optional.<String>empty()` để diễn đạt rõ kiểu phần tử và trạng thái rỗng. Không lạm dụng `Optional` cho mọi biến cục bộ: API nên dùng nó ở nơi việc không có kết quả là một phần hợp đồng; với một biến cục bộ đơn giản, kiểm tra `null` hoặc chọn default có thể gọn và phù hợp hơn.

### 6.3. Ví dụ generic độc lập chạy được

Tạo tệp **`GenericInitializerDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public class GenericInitializerDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Java");

        var typedNames = new ArrayList<String>();
        typedNames.add("JVM");

        var mixedValues = new ArrayList<>();
        mixedValues.add("data");
        mixedValues.add(10);

        var emptyName = Optional.<String>ofNullable(null);

        System.out.println(names);
        System.out.println(typedNames);
        System.out.println(mixedValues);
        System.out.println(emptyName.isEmpty());
    }
}
```

Chạy:

```bash
javac --release 17 GenericInitializerDemo.java
java GenericInitializerDemo
```

Stdout:

```text
[Java]
[JVM]
[data, 10]
true
```

Thử thay `mixedValues` bằng `new ArrayList<String>()` rồi thêm `10`: dòng thêm số sẽ bị `javac` từ chối, vì kiểu phần tử nay được xác định là `String`. Đây là mục đích của kiểm tra kiểu tĩnh.

## 7. Các initializer khác cũng cần ngữ cảnh kiểu

Không phải chỉ có `null` literal mới khiến `var` không suy luận được kiểu. Một số biểu thức phụ thuộc vào kiểu đích hoặc không có kiểu giá trị phù hợp:

```java
// Các dòng cố ý sai nếu bỏ chú thích; không phải chương trình chạy:
// var x;                         // Không có initializer
// var y = null;                  // Initializer chỉ có null type
// var z = {1, 2, 3};             // Array initializer trần cần ngữ cảnh kiểu
// var f = s -> s.trim();         // Lambda cần target functional interface
// var trim = String::trim;       // Method reference cần target type
// var done = System.out.println("done"); // println trả void
```

Những cách viết đúng, khi đặt trong một phương thức:

```java
String x = null;
var array = new int[] {1, 2, 3};
java.util.function.Function<String, String> f = s -> s.trim();
java.util.function.Function<String, String> trim = String::trim;
System.out.println("done"); // Chỉ gọi phương thức, không gán vào biến
```

Với lambda và method reference, kiểu functional interface cung cấp chữ ký tham số/giá trị trả về cần thiết. Với mảng, `new int[] {...}` tạo biểu thức có kiểu `int[]` thay vì chỉ có array initializer trần. Với lời gọi `void`, không có giá trị để khởi tạo biến.

Trong Java hiện đại, `var` được dùng cho biến cục bộ có initializer (bao gồm các vị trí phù hợp trong `for` và `for-each`), **không** thay kiểu trường (field), kiểu trả về của phương thức hay tham số phương thức thông thường. Một số cú pháp hiện đại khác cho phép `var` trong những vị trí đặc biệt (ví dụ tham số lambda có kiểu suy ra với ngoặc), nhưng không làm thay đổi quy tắc `var x = null;`.

## 8. Khi đã xác định kiểu, vẫn cần xử lý khả năng `null`

### 8.1. Kiểm tra trước khi truy cập đối tượng

Ví dụ:

```java
// Đoạn minh họa trong một phương thức:
String input = null;
var current = input;  // current có kiểu String

if (current != null) {
    System.out.println(current.length());
} else {
    System.out.println("Không có chuỗi");
}
```

Hệ kiểu Java thông thường không tự động xem mọi biến tham chiếu khai báo bằng `var` là **non-null**. Một biến có kiểu `String` vẫn có thể mang `null` tùy hợp đồng và đường đi dữ liệu. Nếu bỏ phép kiểm tra và gọi `current.length()` khi `current == null`, chương trình có nguy cơ phát sinh `NullPointerException` ở runtime.

Một IDE có phân tích nullability có thể cảnh báo nhưng mức độ chắc chắn phụ thuộc dữ liệu phân tích, chú thích và cấu hình. **Đừng coi lời gợi ý của IDE như bảo đảm của kiểu `String` trong Java.**

### 8.2. Các API xử lý `null` vẫn nên biết

| Tình huống | Cách dùng | Hành vi |
| --- | --- | --- |
| `null` là đầu vào không hợp lệ | `Objects.requireNonNull(value)` | Trả lại giá trị nếu khác `null`; ném `NullPointerException` nếu `null` |
| Có giá trị thay thế không `null` | `Objects.requireNonNullElse(value, fallback)` | Trả `fallback` khi `value` bằng `null`; không cho kết quả `null` |
| Có fallback tạo tốn công | `Objects.requireNonNullElseGet(value, supplier)` | Chỉ gọi supplier khi `value` bằng `null`; kết quả supplier phải không `null` |
| API biểu diễn kết quả có thể vắng mặt | `Optional.ofNullable(value)` | `null` thành `Optional.empty()` |
| Chắc chắn đã có giá trị | `Optional.of(value)` | Ném `NullPointerException` nếu `value` là `null` |

Không dùng `Optional.of(value)` nếu đầu vào có khả năng `null`. `Optional` là cách thể hiện rõ tình huống vắng mặt, **không** phải cơ chế “làm cho mọi tham chiếu không thể null”. Cũng tránh thay mọi `null` bằng chuỗi rỗng hoặc danh sách rỗng nếu hai trạng thái có ý nghĩa nghiệp vụ khác nhau.

### 8.3. Collection và wrapper có các bẫy `null` riêng

- `var texts = new String[] {null, "A"};` hợp lệ, suy ra `String[]` và phần tử đầu là `null`.
- `List.of(null)` hoặc `List.of("A", null)` không chấp nhận phần tử `null`; chúng ném `NullPointerException` ở runtime. Đây không phải cách kiểm tra kiểu `var`.
- `Integer count = null;` hợp lệ, nhưng `int n = count;` sẽ phát sinh `NullPointerException` khi unboxing. `var` không xóa được rủi ro này.
- Với `Map` hoặc các API khác, có cho phép khóa/giá trị `null` hay không là **hợp đồng riêng của implementation/API**; không suy từ kiểu generic.

## 9. Kiểu tĩnh còn ảnh hưởng chọn overload

Ví dụ một lớp có hai phương thức:

```java
// Các đoạn minh họa nằm trong cùng một lớp:
static void handle(String value) {
    System.out.println("String");
}

static void handle(Integer value) {
    System.out.println("Integer");
}

static void test() {
    // handle(null);  // Mơ hồ: String và Integer đều nhận null
    handle((String) null); // Chọn overload handle(String)

    String knownType = null;
    handle(knownType);     // Chọn overload handle(String)

    var alsoString = (String) null;
    handle(alsoString);    // Chọn overload handle(String)
}
```

Khi các overload nhận hai kiểu tham chiếu không có quan hệ kế thừa hẹp hơn theo cách phù hợp, `null` đơn lẻ có thể làm lời gọi mơ hồ. Khai báo kiểu tường minh hoặc ép kiểu có chủ đích cung cấp thông tin cho **overload resolution khi biên dịch**. Không có chuyện JVM chọn overload khác chỉ vì giá trị runtime đang bằng `null`.

Đừng ép kiểu một cách máy móc để làm hết lỗi overload: cần xác định overload nào phản ánh đúng ý định của API.

## 10. Quy trình kiểm tra với `javac` và IDE

Khi gặp lỗi quanh `var`:

1. **Đọc chính xác initializer.** Là `null` literal, một phương thức trả về kiểu cụ thể, biểu thức `?:`, `switch`, constructor generic hay lambda?
2. **Xác định kiểu của initializer trước khi quan tâm đến giá trị runtime.** Ví dụ `findName()` có kiểu `String` dù kết quả có thể `null`; `null` literal đứng một mình lại không có kiểu biến dùng được.
3. **Hover tên biến và biểu thức trong IDE** để xem kiểu suy luận; đặc biệt kiểm tra tham số kiểu generic, chẳng hạn `Optional<Object>` so với `Optional<String>`.
4. **Biên dịch bằng `javac` của phiên bản dự án.** Khi cần xem lỗi chi tiết, dùng `javac --release 17 -Xdiags:verbose FileName.java`; diễn đạt lỗi có thể thay đổi theo JDK.
5. **Sửa tại nguồn kiểu**: chọn khai báo tường minh, thêm kiểu generic ở constructor/method call, hoặc cung cấp một biểu thức typed phù hợp. Chỉ chọn cast khi thật sự biết kiểu mong muốn.
6. **Kiểm tra đường đi có thể trả `null`** và xử lý theo hợp đồng. Code biên dịch được không chứng minh mọi lần chạy đều tránh được `NullPointerException`.

Có thể thử nhanh bằng **JShell**:

```text
jshell
```

Sau khi vào JShell, nhập:

```java
var bad = null;
var good = (String) null;
var nullable = true ? null : "ok";
```

Dòng `bad` bị từ chối. Hai dòng còn lại hợp lệ, và lệnh JShell `/vars` cho biết `good` và `nullable` đều có kiểu `String` với giá trị `null`. Chữ ký hiển thị có thể được rút gọn tùy cấu hình JShell. Nhập `/exit` để thoát. JShell thuận tiện để thử một biểu thức; khi kiểm tra dự án, hãy ưu tiên compiler và cấu hình JDK chính thức của dự án.

## 11. Lỗi phổ biến và cách chỉnh sửa

| Viết chưa đúng / suy luận sai | Cách hiểu và hướng sửa |
| --- | --- |
| `var value = null;` | Không biên dịch; viết `String value = null;` nếu cần trạng thái nullable có kiểu rõ |
| “`var` luôn tạo biến không `null`” | Sai: initializer từ lời gọi method/biểu thức có kiểu vẫn có thể trả `null` |
| “`var x = (Object) null;` sẽ tiện hơn mọi lúc” | Kiểu `Object` quá rộng nếu cần thao tác như `String`; chọn đúng kiểu ý định |
| `var names = new ArrayList<>();` rồi mong `names.get(0)` là `String` | Kiểu phần tử thường suy ra `Object`; viết `new ArrayList<String>()` hoặc khai báo `List<String>` |
| `var maybe = Optional.ofNullable(null);` rồi nghĩ đó là `Optional<String>` | Không có ngữ cảnh String, thường suy ra `Optional<Object>`; dùng `Optional.<String>ofNullable(null)` hoặc kiểu đích tường minh |
| `var choice = flag ? null : null;` | Không có nhánh typed; ghi kiểu rõ hoặc tạo biểu thức đã có kiểu |
| `List.of(null)` để tạo danh sách có phần tử trống | API từ chối `null` ở runtime; chọn cấu trúc và hợp đồng phù hợp |
| Gọi `nullable.length()` chỉ vì IDE hiển thị `String` | Kiểu `String` không loại trừ giá trị `null`; kiểm tra hoặc bảo đảm giá trị theo API |

## 12. Bài tập tự kiểm tra

**Bài 1.** Với các dòng sau (giả sử đặt trong method), dòng nào biên dịch?

```java
// A
var a = null;
// B
String b = null;
// C
var c = (String) null;
// D
var d = true ? null : "done";
// E
var e = true ? null : null;
```

**Đáp án:** B, C, D biên dịch; A và E không. B/C/D đều có kiểu tĩnh `String`; giá trị của cả B, C, D trong ví dụ này đều bằng `null`. Bốn chữ cái trong tên biến chỉ là ký hiệu bài tập, không mang ý nghĩa kiểu.

**Bài 2.** Đoán kiểu suy luận và khả năng `null`:

```java
String name = null;
var x = name;
var y = java.util.Optional.ofNullable(name);
var z = java.util.Optional.<String>ofNullable(null);
```

**Đáp án:** `x` là `String` và bằng `null`; `y`, `z` đều là `Optional<String>` rỗng. Vì đối số `name` đã có kiểu tĩnh `String`, phương thức generic suy luận phần tử `String` cho `y`. `z` truyền kiểu `String` tường minh.

**Bài 3.** Đoán kết quả:

```java
String token = null;
var output = java.util.Objects.requireNonNullElse(token, "fallback");
System.out.println(output);
```

**Đáp án:** in ra `fallback`. `output` có kiểu `String`. Nếu `fallback` cũng là `null`, `Objects.requireNonNullElse` không trả về `null` bình thường mà sẽ ném `NullPointerException`.

**Bài 4.** Vì sao `var data = new java.util.ArrayList<>();` không có cùng kiểu phần tử với `java.util.List<String> data = new java.util.ArrayList<>();`?

**Đáp án:** khai báo `List<String>` cung cấp ngữ cảnh kiểu cho diamond `<>`. Khi dùng `var` mà constructor không chỉ rõ tham số và không có ràng buộc nào khác cho kiểu phần tử, compiler thường suy ra `Object`; biến có kiểu `ArrayList<Object>`. Nếu cần `String`, hãy viết `var data = new ArrayList<String>();` hoặc `List<String> data = new ArrayList<>();`.

## 13. Ghi nhớ khi sử dụng trong dự án thực tế

- `var` cần một **biểu thức khởi tạo có kiểu xác định và dùng được**; literal `null` đứng một mình không đáp ứng yêu cầu đó.
- **Khai báo kiểu tường minh** là lựa chọn rõ ràng khi giá trị khởi tạo chủ ý là `null`, hoặc khi muốn quy định interface/generic type làm hợp đồng.
- **Biểu thức typed vẫn có thể trả `null`.** Suy luận kiểu và kiểm soát nullability là hai việc khác nhau.
- **Generic inference cần ngữ cảnh**: `new ArrayList<>()` hay `Optional.ofNullable(null)` kết hợp với `var` có thể cho `Object` ngoài dự định.
- Khi `null` được chấp nhận theo nghiệp vụ, hãy xử lý rõ qua guard, giá trị mặc định hoặc `Optional` tùy API; khi `null` bị cấm, kiểm tra sớm bằng hợp đồng phù hợp.
- Ưu tiên kiểm chứng bằng `javac`, IDE, chương trình mẫu chạy được và phân tích kiểu tĩnh. Đừng phán đoán kiểu chỉ từ giá trị được in ra tại runtime.

Nắm vững những nguyên tắc trên giúp đọc đúng `var` trong Java 10 trở đi, viết initializer an toàn và phân biệt chính xác **lỗi suy luận kiểu lúc biên dịch** với **lỗi truy cập tham chiếu `null` lúc chạy**.