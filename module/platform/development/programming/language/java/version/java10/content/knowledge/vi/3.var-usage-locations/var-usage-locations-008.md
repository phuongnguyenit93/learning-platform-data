# Yêu cầu có biểu thức khởi tạo khi dùng `var` (Java 10+)

## 1. Mục tiêu và quy tắc chính

Khi khai báo **biến cục bộ** với `var` trong Java, bạn phải cung cấp **biểu thức khởi tạo ngay tại câu lệnh khai báo** để trình biên dịch có thông tin xác định kiểu của biến.

```java
var count = 10;       // Hợp lệ: suy luận kiểu int từ 10
var title = "Java";   // Hợp lệ: suy luận kiểu String
// var total;         // Lỗi biên dịch: thiếu biểu thức khởi tạo
```

Dù `var` được đưa vào Java từ phiên bản 10, quy tắc này **vẫn áp dụng trong Java hiện đại**. `var` không có nghĩa “khai báo trước, gán giá trị sau” hoặc “kiểu sẽ được biết ở lần gán đầu tiên”.

Sau bài học, bạn có thể:

- Nhận biết khai báo `var` nào có biểu thức khởi tạo hợp lệ và khai báo nào bị từ chối.
- Giải thích vì sao việc có dấu `=` chưa đủ: vế phải phải là biểu thức mà trình biên dịch xác định được kiểu phù hợp.
- Phân biệt `null` trực tiếp với một **biểu thức có kiểu** nhưng giá trị có thể là `null`.
- Sửa các trường hợp `var` sai với lambda, method reference, array initializer và generic.
- Biết vì sao enhanced `for` và tham số lambda (Java 11+) không cần viết `= biểu thức` ngay sau tên biến.
- Chọn cách khai báo phù hợp khi chương trình cần gán biến theo các nhánh điều kiện.

**Phạm vi:** `var` dùng cho biến cục bộ, biến trong `for` và tài nguyên `try-with-resources`; các phân biệt về lambda theo đúng phiên bản Java. Ví dụ chương trình hoàn chỉnh được viết để biên dịch bằng JDK 17 trở lên.

## 2. Tại sao phải khởi tạo ngay?

Khai báo với kiểu tường minh đã cho trình biên dịch biết loại dữ liệu ngay cả khi chưa có giá trị:

```java
String message;   // Hợp lệ với biến cục bộ, chưa có giá trị
message = "ready"; // Gán sau; phải bảo đảm definite assignment trước khi đọc
```

Khi dùng `var`, tên kiểu đã bị lược bỏ. Trình biên dịch cần **biểu thức khởi tạo ngay bên phải** để suy luận kiểu:

```java
var message = "ready"; // Trình biên dịch suy luận String
```

Cách viết dưới đây **không hợp lệ**:

```java
var message;       // LỖI ngay tại câu lệnh khai báo
message = "ready"; // Dòng này không thể sửa lỗi của dòng trên
```

Sự khác biệt không liên quan đến việc Java “tự gán giá trị mặc định” cho `var`. **Biến cục bộ** trong Java nói chung cũng không tự nhận giá trị mặc định để đọc tùy ý. Với kiểu tường minh, bạn có thể để việc gán đến sau nhưng vẫn phải tuân thủ quy tắc **definite assignment** trước khi sử dụng.

### Suy luận kiểu được thực hiện tại thời điểm biên dịch

Với cú pháp:

```java
var variableName = initializerExpression;
```

trình biên dịch xác định kiểu của `initializerExpression` rồi dùng kiểu đó làm **kiểu tĩnh** của `variableName`. Việc suy luận không bị trì hoãn đến lúc chạy chương trình, cũng không lặp lại khi gán biến về sau.

```java
var number = 1;  // int
number = 2;      // Hợp lệ, number vẫn là int
// number = "3"; // Lỗi: không thể gán String cho int
```

## 3. Thế nào là một biểu thức khởi tạo hợp lệ?

Một biểu thức khởi tạo có thể là literal, biểu thức tính toán, lời gọi phương thức có kiểu trả về, lời gọi constructor, phép ép kiểu, biểu thức điều kiện hoặc một biểu thức có kiểu khác phù hợp.

| Khai báo | Kiểu suy luận | Giải thích |
| --- | --- | --- |
| `var age = 18;` | `int` | Literal số nguyên là `int`. |
| `var length = 18L;` | `long` | Hậu tố `L` cho biết kiểu `long`. |
| `var ratio = 0.75;` | `double` | Literal số thực mặc định là `double`. |
| `var enabled = true;` | `boolean` | Literal boolean có kiểu xác định. |
| `var text = "Java";` | `String` | Literal chuỗi có kiểu `String`. |
| `var size = text.length();` | `int` | Phương thức `length()` trả về `int`. |
| `var doubled = age * 2;` | `int` | Biểu thức số có kiểu xác định. |
| `var names = java.util.List.of("An", "Lan");` | `List<String>` | Generic được suy luận từ các đối số. |
| `var points = new int[] {2, 4};` | `int[]` | Biểu thức tạo mảng có kiểu `int[]`. |
| `var state = enabled ? "on" : "off";` | `String` | Biểu thức điều kiện có kiểu `String`. |
| `var list = new java.util.ArrayList<String>();` | `ArrayList<String>` | Constructor và tham số kiểu rõ ràng. |

Các dòng trong bảng là **minh họa trong cùng một khối lệnh**, được sắp xếp theo thứ tự để các biến `age`, `text` và `enabled` đã được khai báo trước khi sử dụng.

**Phân biệt cú pháp và kiểu:** Có `= biểu thức` là điều kiện cần đối với khai báo cục bộ thông thường bằng `var`. Tuy nhiên, không phải mọi thứ có thể đặt bên phải dấu `=` đều tạo ra được kiểu suy luận cho `var`.

## 4. Trường hợp thiếu biểu thức: khai báo trước rồi gán sau

### 4.1. `var` không thể khai báo trống

```java
// Sai:
var status;
status = "READY";
```

Cách sửa khi bạn có thể xác định giá trị ngay:

```java
var status = "READY";
```

Nếu giá trị cần được xác định bằng các nhánh mà không thể hoặc không nên hợp thành một biểu thức, hãy dùng kiểu tường minh:

```java
String status;
if (isReady) {
    status = "READY";
} else {
    status = "PENDING";
}
System.out.println(status);
```

Đây là **đoạn mã minh họa nằm trong phương thức**, giả sử `isReady` là biến `boolean` đã có. Trình biên dịch chấp nhận vì cả hai nhánh đều gán `status` trước khi nó được đọc.

Bạn cũng có thể dùng một biểu thức điều kiện khi đơn giản và dễ đọc:

```java
var status = isReady ? "READY" : "PENDING"; // String
```

Chọn cách diễn đạt rõ ý định; không thêm giá trị giả chỉ để “lách” yêu cầu có initializer.

### 4.2. `final var` cũng phải có biểu thức khởi tạo

```java
final var threshold = 10; // Hợp lệ, kiểu int
// final var threshold2;   // Không hợp lệ với var
```

`final` cấm gán lại sau khởi tạo. Nó không thay thế việc suy luận kiểu và không loại bỏ yêu cầu initializer của `var`.

## 5. Có `=` nhưng vẫn sai: các trường hợp cần nhận diện

### 5.1. Khởi tạo trực tiếp bằng literal `null`

```java
// var name = null; // Lỗi: literal null không cho var một kiểu có thể suy luận
```

Quy tắc là **không thể suy luận kiểu từ biểu thức chỉ có kiểu null**. Điều này không có nghĩa biến khai báo bằng `var` không bao giờ chứa `null`.

Hai ví dụ hợp lệ:

```java
var name = (String) null; // Hợp lệ: biểu thức ép kiểu có kiểu String
var maybeName = java.util.Optional.of("Lan").orElse(null); // Kiểu String
```

Cả hai có thể chứa giá trị `null`, nhưng trình biên dịch xác định được **kiểu tĩnh String** từ biểu thức.

Cách đơn giản, rõ ràng hơn nếu bạn định khởi tạo trực tiếp bằng `null`:

```java
String name = null;
```

Trong ứng dụng thực tế, nếu một API có thể trả về `null`, vẫn cần xử lý khả năng đó; `var` không giúp tránh `NullPointerException`.

### 5.2. Biểu thức trả về `void`

```java
// var result = System.out.println("Hello"); // Lỗi: println trả về void
```

Lệnh `println` là một lời gọi hợp lệ khi dùng như một **statement**, nhưng nó không tạo ra giá trị có kiểu để gán vào một biến:

```java
System.out.println("Hello"); // Hợp lệ
```

Nếu bạn cần nhận giá trị trả về, hãy dùng phương thức có kiểu kết quả khác `void`.

### 5.3. Lambda không có kiểu đích

```java
// var action = () -> System.out.println("Running"); // Lỗi
```

Lambda không tự có một kiểu độc lập để `var` suy luận trong ngữ cảnh này; nó cần **functional interface làm kiểu đích (target type)**. Cách sửa rõ ràng:

```java
Runnable action = () -> System.out.println("Running");
action.run();
```

Nếu muốn, có thể ép kiểu lambda để tạo một biểu thức mang kiểu:

```java
var action = (Runnable) () -> System.out.println("Running");
```

Cách viết này hợp lệ, nhưng khai báo tường minh `Runnable action = ...` thường thể hiện hợp đồng tốt hơn.

### 5.4. Method reference cũng cần kiểu đích

```java
// var lengthOf = String::length; // Lỗi: không có target type
```

Thay bằng:

```java
java.util.function.ToIntFunction<String> lengthOf = String::length;
System.out.println(lengthOf.applyAsInt("Java")); // In 4
```

Một lần nữa, vấn đề là **kiểu của biểu thức khởi tạo**, không phải `var` không cho phép khởi tạo bằng phương thức.

### 5.5. Array initializer trực tiếp không hợp lệ

```java
// var numbers = {1, 2, 3}; // Lỗi: array initializer trực tiếp
```

Cách sửa:

```java
int[] numbers = {1, 2, 3};            // Có kiểu mảng tường minh
var otherNumbers = new int[] {1, 2, 3}; // Biểu thức tạo mảng có kiểu int[]
```

`{1, 2, 3}` là dạng **array initializer** cần ngữ cảnh kiểu mảng; `new int[] {1, 2, 3}` là một **biểu thức tạo mảng** có kiểu xác định.

### 5.6. Không được tự tham chiếu trong chính initializer

```java
// var next = next + 1; // Lỗi: tham chiếu tới chính biến đang khai báo
```

Sửa bằng cách khởi tạo độc lập rồi cập nhật:

```java
var next = 1;
next = next + 1; // next vẫn là int, giá trị thành 2
```

Đây không đơn thuần là lỗi “chưa gán” trong một lần chạy cụ thể: Java cấm initializer của khai báo `var` tham chiếu chính biến đó.

### 5.7. Không khai báo nhiều biến hoặc thêm `[]` sau tên trong một khai báo `var`

```java
// var a = 1, b = 2;      // Lỗi: var không hỗ trợ nhiều declarator cùng lúc
// var numbers[] = new int[2]; // Lỗi: dấu [] đặt sau tên biến
```

Cách đúng:

```java
var a = 1;
var b = 2;
var numbers = new int[2];
```

Quy tắc này ngăn cách viết thiếu rõ ràng về kiểu suy luận. Nó không có nghĩa Java cấm khai báo mảng hoặc nhiều biến khi dùng **kiểu tường minh**.

## 6. Khởi tạo bằng generic: có biểu thức nhưng cần kiểm tra kiểu thực tế

Sự có mặt của initializer bảo đảm trình biên dịch **có thể thử suy luận kiểu**; không bảo đảm kiểu suy luận **đúng với ý định của bạn**.

```java
var names = new java.util.ArrayList<>(); // ArrayList<Object>
names.add("Lan");
names.add(42);                           // Hợp lệ vì phần tử là Object
```

Với `var`, không có kiểu đích `List<String>` ở vế trái để hướng dẫn suy luận tham số của diamond operator `<>`. Hãy viết:

```java
var names = new java.util.ArrayList<String>(); // ArrayList<String>
```

hoặc khai báo interface:

```java
java.util.List<String> names = new java.util.ArrayList<>();
```

Tương tự:

```java
var empty = java.util.List.of();       // List<Object>
var emptyStrings = java.util.List.<String>of(); // List<String>
```

Đây là ví dụ điển hình của một **initializer hợp lệ nhưng kiểu có thể khác kỳ vọng**. Khi review, cần kiểm tra cả **tính hợp lệ** và **ý nghĩa kiểu**.

## 7. Phân biệt vị trí dùng `var`: có và không có `= initializer`

Quy tắc “phải có initializer” áp dụng cho **khai báo biến cục bộ dùng `var`** ở dạng `var name = expression`, bao gồm vị trí khai báo được phép trong thân khối và trong phần khởi tạo của vòng `for` cơ bản.

Các cấu trúc khác dùng ký pháp `var` nhưng **giá trị/kiểu được cung cấp bởi cú pháp bao quanh**, nên không bắt người viết thêm dấu `=`.

| Vị trí | Ví dụ | Nguồn dữ liệu để xác định kiểu |
| --- | --- | --- |
| Biến cục bộ trong khối | `var count = 0;` | Biểu thức `0`, suy luận `int`. |
| Phần khởi tạo `for` cơ bản | `for (var i = 0; i < 3; i++)` | Biểu thức `0`, suy luận `int`. |
| Tài nguyên khai báo trong `try-with-resources` | `try (var reader = new StringReader("Hi")) { ... }` | Biểu thức `new StringReader(...)`; tài nguyên có kiểu phù hợp với `AutoCloseable`. |
| Biến duyệt `enhanced for` | `for (var word : words)` | Kiểu phần tử của mảng hoặc `Iterable` được duyệt; không viết `=` cho biến duyệt. |
| Tham số lambda từ Java 11 | `Function<String,Integer> f = (var s) -> s.length();` | Kiểu đích của functional interface xác định kiểu tham số `s`. |

### 7.1. Basic `for` vẫn cần initializer

```java
for (var i = 0; i < 3; i++) {
    System.out.println(i);
}
```

`var i = 0` là khai báo biến trong phần khởi tạo `for`. Việc không đặt initializer tại khai báo (ví dụ `for (var i; i < 3; i++)`) là lỗi biên dịch.

### 7.2. Enhanced `for` là một cú pháp khác

```java
java.util.List<String> words = java.util.List.of("Java", "VM");
for (var word : words) {
    System.out.println(word);
}
```

`word` được cấp một phần tử của `words` cho mỗi lần lặp và có kiểu `String`. Không được thêm `= ...` sau `word` trong cú pháp này. Vì vậy, câu “mọi nơi thấy `var` đều phải có `=`” **không chính xác**.

### 7.3. Tham số lambda dùng `var` là tính năng Java 11+

```java
java.util.function.Function<String, Integer> length =
        (var text) -> text.length();
```

`text` là **tham số lambda**, không phải khai báo cục bộ với initializer ở vế phải. Kiểu của nó được xác định từ kiểu đích `Function<String, Integer>`. Cách viết này được hỗ trợ từ **Java 11**, không phải Java 10 gốc.

Với lambda có nhiều tham số, khi chọn `var` phải dùng thống nhất cho danh sách tham số, ví dụ:

```java
java.util.function.BiFunction<Integer, Integer, Integer> sum =
        (var left, var right) -> left + right;
```

Không nhầm `var` trong **tham số lambda** với việc viết `var lambda = (x) -> x;`: trường hợp sau vẫn thiếu target type ở khai báo biến và không hợp lệ.

### 7.4. `var` không thay thế kiểu ở mọi vị trí

`var` không dùng làm kiểu khai báo **field, tham số phương thức thông thường hoặc kiểu trả về của phương thức**. Những vị trí này có quy tắc khai báo riêng và không chuyển sang suy luận kiểu chỉ bằng cách thêm initializer.

```java
// class Person { var age = 18; } // Lỗi: var không dùng cho field
// void setAge(var age) { }        // Lỗi: var không dùng làm kiểu tham số method
// var getAge() { return 18; }    // Lỗi: var không dùng làm return type
```

Các dòng trên là **minh họa lỗi cú pháp**, không phải chương trình có thể chạy.

## 8. Ví dụ Java 17+ chạy độc lập

Tạo tệp **`VarInitializerDemo.java`**:

```java
import java.io.StringReader;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

public class VarInitializerDemo {
    static String findName(boolean found) {
        return found ? "Lan" : null;
    }

    public static void main(String[] args) throws Exception {
        var age = 20;                       // int
        var language = "Java";              // String
        var names = List.of("Lan", "An");    // List<String>
        var mutable = new ArrayList<String>(names);
        var maybeName = findName(false);    // String, dù nhận null
        var typedNull = (String) null;      // String
        var numbers = new int[] {2, 4};     // int[]
        var status = age >= 18 ? "adult" : "minor"; // String

        var sum = 0;                        // int
        for (var i = 0; i < numbers.length; i++) {
            sum += numbers[i];
        }

        for (var name : names) {
            System.out.println("name=" + name);
        }

        try (var reader = new StringReader("OK")) {
            System.out.println("firstChar=" + (char) reader.read());
        }

        // Cú pháp tham số lambda có var được hỗ trợ từ Java 11.
        Function<String, Integer> length = (var text) -> text.length();

        System.out.println("age=" + age);
        System.out.println("language=" + language);
        System.out.println("mutable=" + mutable);
        System.out.println("maybeNull=" + (maybeName == null));
        System.out.println("typedNull=" + (typedNull == null));
        System.out.println("status=" + status);
        System.out.println("sum=" + sum);
        System.out.println("length=" + length.apply("Java"));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 VarInitializerDemo.java
java VarInitializerDemo
```

**Kết quả stdout:**

```text
name=Lan
name=An
firstChar=O
age=20
language=Java
mutable=[Lan, An]
maybeNull=true
typedNull=true
status=adult
sum=6
length=4
```

**Điểm cần quan sát:**

1. `age`, `language`, `names`, `mutable`, `numbers`, `status` và `sum` đều có biểu thức khởi tạo ngay tại khai báo.
2. `findName(false)` có kiểu trả về `String`, nên khai báo `maybeName` hợp lệ ngay cả khi kết quả chạy là `null`.
3. `(String) null` là một biểu thức **có kiểu String**, khác với literal `null` đứng một mình.
4. Biến `i` trong basic `for` được khởi tạo bằng `0`, còn `name` trong enhanced `for` lấy kiểu phần tử từ `names`.
5. `reader` được khởi tạo bằng biểu thức tạo `StringReader` rồi tự đóng theo `try-with-resources`.
6. `text` trong lambda lấy kiểu từ functional interface `Function<String, Integer>`, không cần khai báo `= initializer`.
7. Thứ tự phần tử của `List.of("Lan", "An")` ổn định theo thứ tự đối số, vì vậy stdout ở ví dụ này xác định.

## 9. Khi cần khởi tạo muộn, nên xử lý thế nào?

Không nên cố giữ `var` bằng một giá trị ban đầu không có ý nghĩa, đặc biệt với dữ liệu có trạng thái chưa sẵn sàng.

### Lựa chọn A: Dùng kiểu tường minh khi nhiều nhánh sẽ gán sau

```java
String result;
if (score >= 50) {
    result = "PASS";
} else {
    result = "RETRY";
}
```

Đoạn này giả sử `score` đã được khai báo. Nếu thiếu nhánh gán mà sau đó đọc `result`, trình biên dịch sẽ báo lỗi **definite assignment**. Quy tắc vẫn bảo vệ bạn trước việc đọc biến chưa khởi tạo.

### Lựa chọn B: Dùng một biểu thức khởi tạo rõ ràng

```java
var result = score >= 50 ? "PASS" : "RETRY";
```

Cách này phù hợp khi chỉ có hai nhánh đơn giản và kết quả cùng kiểu, giúp biến được khởi tạo ngay.

### Lựa chọn C: Đưa logic vào phương thức có kiểu trả về rõ ràng

```java
String result = computeResult(score);
// hoặc, khi phương thức được đặt tên rõ và kiểu dễ hiểu:
var result = computeResult(score);
```

`computeResult` ở đây là **phương thức minh họa, chưa được định nghĩa**; đây là đoạn code về cách tổ chức phương thức, không phải một chương trình chạy độc lập. Phương thức thực tế phải có kiểu trả về khác `void` và được định nghĩa hoặc import phù hợp.

**Đừng dùng giá trị giả chỉ để khai báo bằng `var`**, ví dụ khởi tạo `0` rồi đặt lại giá trị ở mọi nhánh khi `0` không mang ý nghĩa. Giá trị giả có thể che giấu lỗi logic nếu một nhánh bị quên.

## 10. Những hiểu nhầm phổ biến và cách kiểm tra nhanh

| Hiểu nhầm | Thực tế | Cách sửa hoặc kiểm tra |
| --- | --- | --- |
| “Có thể viết `var x;` rồi gán sau.” | Không hợp lệ với khai báo biến cục bộ dùng `var`. | Gán tại khai báo hoặc viết kiểu tường minh. |
| “Có dấu `=` là đủ.” | Biểu thức phải cho ra kiểu có thể suy luận; `null` trực tiếp, `void` và lambda không target type đều không phù hợp. | Xác định kiểu của vế phải trước khi dùng `var`. |
| “`var x = null;` tạo biến nullable.” | Literal `null` đơn độc không cung cấp kiểu. | `String x = null;` hoặc biểu thức đã có kiểu. |
| “`var arr = {1, 2};` là một array hợp lệ.” | Array initializer trực tiếp cần kiểu mảng. | `var arr = new int[] {1, 2};`. |
| “`var xs = new ArrayList<>();` có phần tử kiểu String vì về sau thêm String.” | Kiểu generic suy luận tại khai báo có thể là `Object`. | Ghi `new ArrayList<String>()` hoặc kiểu vế trái tường minh. |
| “`var` trong enhanced `for` cũng cần dấu `=`.” | Cú pháp `for (var x : values)` lấy kiểu phần tử từ nguồn. | Phân biệt cấu trúc enhanced `for` với khai báo cục bộ. |
| “Có thể dùng `var` cho field có initializer.” | `var` không hợp lệ ở field. | Viết kiểu field tường minh. |
| “Java 10 đã có `(var x) -> ...`.” | Dùng `var` cho tham số lambda là tính năng Java 11+. | Ghi rõ phiên bản của ví dụ. |

**Checklist review một dòng khai báo `var`:**

1. Đây có đúng là vị trí được phép dùng `var` không?
2. Nếu là khai báo cục bộ thông thường, có **biểu thức khởi tạo tại dòng khai báo** không?
3. Biểu thức đó có **kiểu suy luận hợp lệ** (khác kiểu `null` và `void`; không phải lambda/method reference thiếu target type) không?
4. Biểu thức có tự tham chiếu biến đang được khai báo không?
5. Có vô tình viết nhiều declarator, đặt `[]` sau tên biến hoặc dùng array initializer trần không?
6. Kiểu suy luận thực sự (đặc biệt generic, primitive) có đúng với mục đích chương trình không?
7. Người đọc có hiểu kiểu và ý nghĩa từ initializer không, hay kiểu tường minh sẽ rõ hơn?

## 11. Câu hỏi luyện tập

Hãy đánh giá **hợp lệ / không hợp lệ**, giải thích ngắn gọn và nêu kiểu khi hợp lệ. Mỗi câu là một đoạn code độc lập trong khối lệnh:

1. `var x; x = 1;`
2. `var x = 1L;`
3. `var x = null;`
4. `var x = (String) null;`
5. `var x = new int[] {1, 2};`
6. `var x = {1, 2};`
7. `var x = java.util.List.of("An", "Lan");`
8. `var x = new java.util.ArrayList<>();`
9. `var r = () -> System.out.println("run");`
10. `Runnable r = () -> System.out.println("run");`
11. `for (var word : java.util.List.of("A", "B")) { System.out.println(word); }`
12. `var a = 1, b = 2;`

**Đáp án:**

1. **Không hợp lệ**: khai báo `var` thiếu initializer, dù sau đó có lệnh gán.
2. **Hợp lệ**, kiểu `long`.
3. **Không hợp lệ**: literal `null` không cung cấp kiểu suy luận.
4. **Hợp lệ**, kiểu `String`, giá trị hiện tại là `null`.
5. **Hợp lệ**, kiểu `int[]`.
6. **Không hợp lệ**: array initializer trần cần kiểu đích.
7. **Hợp lệ**, kiểu `List<String>`.
8. **Hợp lệ**, kiểu suy luận là `ArrayList<Object>` (cần cân nhắc kiểu phần tử mong muốn).
9. **Không hợp lệ**: lambda thiếu target type.
10. **Hợp lệ**, biến có kiểu `Runnable`; body chỉ in khi `r.run()` được gọi.
11. **Hợp lệ**, biến duyệt `word` có kiểu `String`; đây là enhanced `for`, không cần `=` trong tên biến.
12. **Không hợp lệ**: chỉ được một declarator cho một khai báo `var`; tách thành hai câu lệnh.

## 12. Ghi nhớ và tài liệu chính thức

- **Khai báo biến cục bộ bằng `var` phải có biểu thức khởi tạo ngay**, vì trình biên dịch cần lấy kiểu từ biểu thức đó.
- **Initializer có mặt chưa chắc suy luận kiểu được**: literal `null`, biểu thức `void`, lambda/method reference thiếu target type và array initializer trực tiếp là các bẫy thường gặp.
- **Enhanced `for` và tham số lambda có cú pháp khác:** chúng nhận kiểu/giá trị từ ngữ cảnh, không viết `= initializer` như một khai báo biến cục bộ bình thường.
- **Một kiểu đã được suy luận là kiểu tĩnh cố định**; các phép gán sau không khiến suy luận lại.
- **Kiểm tra tính rõ ràng của kiểu**, nhất là generic `<>` và literal số; đừng chọn `var` chỉ để rút ngắn mã.

Nguồn tham khảo hiện hành:
- [Java Language Specification (Java SE 26), `14.4 – Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se26/html/jls-14.html#jls-14.4): những giới hạn cú pháp của `var`, initializer và lỗi suy luận.
- [Java Language Specification (Java SE 26), `14.14.2 – Enhanced `for`](https://docs.oracle.com/javase/specs/jls/se26/html/jls-14.html#jls-14.14.2): biến duyệt trong vòng `for-each`.
- [JEP 286 – Local-Variable Type Inference](https://openjdk.org/jeps/286): thiết kế `var` từ Java 10.
- [JEP 323 – Local-Variable Syntax for Lambda Parameters](https://openjdk.org/jeps/323): mở rộng cú pháp tham số lambda từ Java 11.
