# Cú pháp lambda, target type và biến effectively final trong Java 27

Trong **Java 27**, một biểu thức lambda (*lambda expression*) là cách ngắn gọn để cung cấp hành vi cho nơi đang cần một **functional interface**. Chẳng hạn, thay vì tạo một lớp riêng chỉ để định nghĩa quy tắc kiểm tra chuỗi, ta có thể viết:

```java
import java.util.function.Predicate;

Predicate<String> nonBlank = text -> !text.isBlank();

System.out.println(nonBlank.test("Java")); // true
System.out.println(nonBlank.test("  "));   // false
```

Ba câu hỏi quan trọng khi đọc đoạn mã này là:

1. **Cú pháp:** `text -> !text.isBlank()` biểu diễn đầu vào và phần thân thực thi như thế nào?
2. **Target type:** Tại sao compiler biết `text` là `String` và lambda có thể dùng với `Predicate<String>`?
3. **Effectively final:** Khi lambda dùng biến cục bộ bên ngoài, vì sao có biến được phép tham chiếu và có biến gây lỗi biên dịch?

Bài học thuộc chương **Lambda và interface hàm**, trình bày các quy tắc ổn định trong Java SE 27, không phụ thuộc vào API đã lỗi thời hay cơ chế preview.

## 1. Lambda là một biểu thức có kiểu phụ thuộc ngữ cảnh

Hình thức tổng quát:

```java
(parameters) -> body
```

Trong đó:

- `parameters` là danh sách tham số, có thể rỗng; kiểu tham số có thể viết rõ hoặc được suy luận.
- `->` ngăn cách tham số với thân lambda.
- `body` là một biểu thức đơn hoặc một khối lệnh đặt trong `{ ... }`.

Ví dụ, khi đã có một functional interface nhận hai số và trả tổng:

```java
import java.util.function.BinaryOperator;

BinaryOperator<Integer> add = (a, b) -> a + b;

System.out.println(add.apply(3, 4)); // 7
```

Lambda **không tự định nghĩa một kiểu hàm độc lập** theo cách có thể gán trực tiếp cho bất cứ `Object` nào. Trong Java, lambda là *poly expression*: kiểu của nó được xác định từ **ngữ cảnh kiểu đích** (*target typing*). Ở ví dụ trên, `BinaryOperator<Integer>` chính là target type.

Đối tượng dùng để thực thi một lambda có thể được JVM tạo hoặc tái sử dụng theo cách triển khai riêng; không nên dựa vào tên lớp sinh ra, identity hay chi tiết bytecode để diễn giải ngữ nghĩa chương trình.

## 2. Các dạng cú pháp lambda cần nắm vững

| Hình thức | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Không tham số | `() -> "READY"` | Trả giá trị khi được gọi |
| Một tham số, suy luận kiểu | `name -> name.length()` | Có thể bỏ ngoặc khi chỉ một tham số dạng tên đơn |
| Một tham số, có ngoặc | `(name) -> name.length()` | Tương đương cách viết ngay trên |
| Một tham số, kiểu tường minh | `(String name) -> name.length()` | Bắt buộc có ngoặc |
| Hai tham số, suy luận kiểu | `(a, b) -> a + b` | Bắt buộc có ngoặc với nhiều tham số |
| Hai tham số, kiểu tường minh | `(int a, int b) -> a + b` | Phù hợp khi target method nhận hai `int` |
| Thân dạng biểu thức | `x -> x * 2` | Giá trị biểu thức có thể dùng làm kết quả |
| Thân dạng khối | `x -> { return x * 2; }` | Có thể chứa nhiều câu lệnh |

Ví dụ đầy đủ cho các dạng thường gặp:

```java
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.IntBinaryOperator;
import java.util.function.Supplier;

Supplier<String> status = () -> "READY";

Function<String, Integer> length = text -> text.length();

Consumer<String> print = (String text) -> System.out.println(text);

IntBinaryOperator sum = (int a, int b) -> a + b;

Function<Integer, Integer> doubleValue = x -> {
    int result = x * 2;
    return result;
};
```

Đây là các **functional interface khác nhau**, nên dù cú pháp lambda tương tự nhau, số tham số, kiểu tham số và kiểu kết quả cũng khác nhau.

### 2.1. Kiểu tham số suy luận hay khai báo tường minh?

Khi ngữ cảnh đã rõ, thường nên để compiler suy luận:

```java
Predicate<String> longText = text -> text.length() >= 5;
```

Kiểu `text` là `String` vì phương thức trừu tượng `Predicate<String>.test` nhận `String`.

Nếu muốn viết tường minh:

```java
Predicate<String> longText = (String text) -> text.length() >= 5;
```

Hai đoạn có cùng ý nghĩa trong trường hợp này. Tuy nhiên, khi ghi kiểu tường minh, **kiểu đó phải tương thích chính xác theo quy tắc lambda với kiểu tham số của functional method**. Không thể tùy tiện thay `String` bằng `Object` chỉ vì `String` là một `Object`.

### 2.2. Dùng `var` cho tham số lambda

Java 27 cho phép khai báo tham số lambda bằng `var` khi có ngữ cảnh suy luận kiểu:

```java
import java.util.function.BinaryOperator;

BinaryOperator<Integer> sum = (var left, var right) -> left + right;
```

Ở đây `var` **không làm lambda trở thành kiểu tùy ý**: kiểu thực của `left` và `right` vẫn đến từ `BinaryOperator<Integer>`. Dạng `var` hữu ích khi cần áp dụng annotation cho tham số hoặc muốn giữ cách viết nhất quán.

Không được trộn các phong cách khai báo trong **cùng danh sách tham số**:

```java
// LỖI BIÊN DỊCH:
// BinaryOperator<Integer> wrong1 = (var a, b) -> a + b;
// BinaryOperator<Integer> wrong2 = (int a, var b) -> a + b;
// BinaryOperator<Integer> wrong3 = (a, Integer b) -> a + b;
```

Các tham số phải cùng được suy luận theo cách viết không khai báo kiểu, hoặc cùng được khai báo bằng kiểu tường minh, hoặc cùng dùng `var`. Với một tham số dùng `var`, phải viết ngoặc: `(var text) -> ...`, không viết `var text -> ...`.

### 2.3. Tham số không dùng đến

Trong Java 27 có cú pháp **unnamed variable** bằng ký hiệu `_`. Khi không cần đọc một tham số lambda, có thể viết rõ việc bỏ qua nó:

```java
import java.util.function.BiConsumer;

BiConsumer<String, Integer> reportCount =
        (_, count) -> System.out.println("Số lượng: " + count);
```

Ký hiệu `_` không phải một tên biến có thể tham chiếu trong thân lambda. Đừng nhầm cách viết này với việc đặt tên biến thông thường bằng dấu gạch dưới: cú pháp unnamed variables là một tính năng chuẩn hiện hành của Java.

## 3. Thân dạng biểu thức và thân dạng khối

Thân lambda dạng biểu thức không cần `return`:

```java
import java.util.function.Function;

Function<Integer, Integer> square = x -> x * x;
```

Thân dạng khối cần quy tắc trả về tương ứng:

```java
Function<Integer, Integer> square = x -> {
    int result = x * x;
    return result;
};
```

Lưu ý dấu chấm phẩy:

- Với **thân biểu thức**, không thêm `;` ngay bên trong thân: `x -> x * x`.
- Với **thân khối**, các câu lệnh bên trong dùng `;` bình thường.
- Dấu `;` sau toàn bộ lambda trong ví dụ là dấu kết thúc câu lệnh **gán biến**, không thuộc thân lambda.

### 3.1. Functional method trả `void`

`Consumer<T>` và `Runnable` có functional method trả `void`:

```java
import java.util.function.Consumer;

Consumer<String> print = text -> System.out.println(text);

Runnable task = () -> {
    System.out.println("Bắt đầu");
    System.out.println("Hoàn tất");
};
```

Một lambda có thân khối trả `void` có thể dùng `return;` không kèm giá trị để kết thúc sớm:

```java
Consumer<String> printNonBlank = text -> {
    if (text.isBlank()) {
        return;
    }
    System.out.println(text);
};
```

### 3.2. Functional method có kết quả

Với kiểu trả về khác `void`, một thân khối có khả năng hoàn thành bình thường phải trả về giá trị theo các đường đi phù hợp:

```java
Function<String, String> category = text -> {
    if (text.isBlank()) {
        return "EMPTY";
    }
    return "FILLED";
};
```

Không hợp lệ khi thiếu giá trị trả về trên một nhánh:

```java
// LỖI BIÊN DỊCH: không trả kết quả trên mọi đường đi cần thiết.
// Function<String, String> wrong = text -> {
//     if (text.isBlank()) {
//         return "EMPTY";
//     }
// };
```

Thân lambda phải **tương thích với kiểu kết quả** của functional method. Không phải bất cứ khối lệnh hợp lệ nào cũng có thể gán cho mọi functional interface.

### 3.3. `return` trong lambda không trả về từ phương thức bao quanh

```java
static void runExample() {
    Runnable task = () -> {
        System.out.println("Trong lambda");
        return; // Chỉ kết thúc lời gọi của lambda
    };

    task.run();
    System.out.println("Sau lambda");
}
```

Lệnh `return;` bên trong lambda kết thúc **thân lambda**, không kết thúc `runExample()`. Nếu lambda không được gọi, thân lambda cũng không tự thực thi khi khai báo.

## 4. Functional interface là điều kiện để có target type

Một **functional interface** là interface có một functional method trừu tượng theo quy tắc của Java Language Specification. Cách khai báo điển hình:

```java
@FunctionalInterface
interface TextFormatter {
    String format(String text);
}
```

Dùng làm target type:

```java
TextFormatter normalize = text -> text.strip().toLowerCase();
System.out.println(normalize.format("  JAVA  ")); // java
```

Annotation `@FunctionalInterface` **không bắt buộc** để interface hợp lệ làm target type, nhưng rất nên dùng khi tự thiết kế interface: compiler sẽ kiểm tra nó còn thỏa điều kiện functional interface sau mỗi lần chỉnh sửa.

Một functional interface có thể có các phương thức `default` và `static`; chúng không làm tăng số functional method trừu tượng:

```java
@FunctionalInterface
interface TextFormatter {
    String format(String text);

    default String formatTrimmed(String text) {
        return format(text.strip());
    }

    static TextFormatter identity() {
        return text -> text;
    }
}
```

Các phương thức tương đương với một số public method của `Object` theo quy tắc của JLS cũng không được tính như những functional method độc lập. Vì vậy, diễn giải chính xác hơn “interface chỉ được có đúng một phương thức” là: **interface phải có một functional method trừu tượng thích hợp sau khi xét quy tắc kế thừa/ghi đè**.

Nếu thêm một abstract method không liên quan như `int measure(String text);` vào interface trên thì nó không còn là functional interface; đoạn gán lambda sẽ bị lỗi biên dịch.

## 5. Target typing: compiler tìm kiểu của lambda ở đâu?

**Target type** là kiểu functional interface mà ngữ cảnh yêu cầu lambda phải tương thích. Compiler dùng target type để quyết định:

1. Lambda cần nhận bao nhiêu tham số.
2. Kiểu của từng tham số khi người viết không ghi tường minh.
3. Thân lambda có hợp lệ và có trả về giá trị tương thích hay không.
4. Các checked exception nào được phép phát sinh qua functional method.
5. Lambda nào phù hợp với một lời gọi overloaded/generic.

Ví dụ:

```java
import java.util.function.Function;
import java.util.function.Predicate;

Function<String, Integer> countChars = text -> text.length();
Predicate<String> hasContent = text -> !text.isBlank();
```

Hai lambda đều nhận một `String`, nhưng một lambda trả `Integer`, một lambda trả `boolean`. Tên tham số `text` **không mang sẵn kiểu**; target type quyết định.

### 5.1. Target type từ phép gán

```java
import java.util.function.Supplier;

Supplier<String> greeting = () -> "Xin chào Java 27";
```

Dùng kiểu tường minh phía trái là cách đọc code rất rõ. Với lambda có tham số suy luận, đây cũng là nguồn cung cấp kiểu tham số.

### 5.2. Target type từ tham số phương thức

```java
import java.util.List;
import java.util.function.Predicate;

static long countMatching(
        List<String> values, Predicate<String> condition) {

    return values.stream().filter(condition).count();
}

long result = countMatching(
        List.of("java", "", "lambda"),
        value -> !value.isEmpty()
);

System.out.println(result); // 2
```

Trong `countMatching(..., value -> !value.isEmpty())`, tham số thứ hai của phương thức yêu cầu `Predicate<String>`. Vì thế `value` được suy luận là `String` và thân lambda phải tạo một giá trị `boolean`.

Cách này không yêu cầu khai báo một biến `Predicate<String>` trung gian, nhưng nếu điều kiện dài hoặc dùng nhiều nơi, đặt tên predicate sẽ dễ đọc hơn.

### 5.3. Target type từ giá trị trả về của phương thức

```java
import java.util.function.Supplier;

static Supplier<String> createMessageSupplier() {
    String version = "Java 27";
    return () -> "Học " + version;
}
```

Khai báo `Supplier<String>` là kiểu trả về của phương thức, cũng chính là target type cho lambda sau `return`. Biến `version` được capture và phải tuân thủ quy tắc effectively final (xem phần sau).

### 5.4. Target type từ phép ép kiểu (*cast*)

```java
import java.util.function.Supplier;

Object action = (Supplier<String>) () -> "READY";
```

Phép cast cung cấp target type `Supplier<String>` cho lambda. Sau phép ép kiểu, toàn biểu thức có thể được gán vào `Object`.

Trái lại, các biểu thức sau không hợp lệ:

```java
// LỖI: Object không phải functional interface.
// Object action = () -> "READY";

// LỖI: var không tự suy ra functional interface cho lambda.
// var action = () -> "READY";
```

**Lambda cần ngữ cảnh kiểu đích.** Nó không có một kiểu tự thân duy nhất mà `var` có thể suy luận chỉ từ `() -> ...`.

## 6. Kiểu generic và suy luận kiểu từ target type

Java có thể kết hợp type inference của generic method với target typing của lambda:

```java
import java.util.function.Function;

static <T, R> R convert(T input, Function<T, R> mapper) {
    return mapper.apply(input);
}

int length = convert("lambda", text -> text.length());
System.out.println(length); // 6
```

Ở lời gọi trên, compiler có đủ thông tin để suy luận:

- `T` phù hợp với `String`.
- `R` phù hợp với kết quả của `text.length()` (khi gán vào `int` có thể unbox).
- Tham số `text` của lambda được xác định theo `Function<T, R>`.

Không nên ghi kiểu tường minh khắp nơi chỉ để buộc compiler suy luận; hãy để kiểu của phương thức và đối số biểu thị rõ hợp đồng. Tuy nhiên, nếu compiler báo không thể suy luận type parameter, có thể tách một biến lambda có kiểu tường minh, chỉ định type witness cho generic method, hoặc làm rõ overload đang được dùng.

### 6.1. Boxing và primitive-specialized functional interface

`Function<Integer, Integer>` dùng kiểu wrapper `Integer`, còn `IntUnaryOperator` làm việc trực tiếp với `int`:

```java
import java.util.function.Function;
import java.util.function.IntUnaryOperator;

Function<Integer, Integer> boxed = x -> x + 1;
IntUnaryOperator primitive = x -> x + 1;

System.out.println(boxed.apply(5));     // 6
System.out.println(primitive.applyAsInt(5)); // 6
```

Hai lambda nhìn giống nhau nhưng target type và chữ ký functional method khác nhau. Trong logic xử lý lượng lớn số nguyên, các interface chuyên biệt có thể tránh boxing không cần thiết. Không nên tối ưu chỉ dựa vào suy đoán; cân nhắc workload thực tế.

## 7. Overload resolution: cùng một lambda có thể gây nhập nhằng

Nếu hai overload đều chấp nhận các functional interface khác nhau nhưng lambda đều phù hợp, Java có thể không tự chọn được phương thức đích.

```java
import java.util.concurrent.Callable;
import java.util.function.Supplier;

static void register(Supplier<String> supplier) {
    System.out.println("Supplier");
}

static void register(Callable<String> callable) {
    System.out.println("Callable");
}

// LỖI BIÊN DỊCH: lời gọi nhập nhằng.
// register(() -> "READY");
```

Cả `Supplier<String>.get()` lẫn `Callable<String>.call()` đều không nhận tham số và trả `String`. Với `register(() -> "READY")`, không có target type duy nhất đủ rõ.

Cách giải quyết thứ nhất: **gán lambda vào biến có kiểu**.

```java
Supplier<String> supplier = () -> "READY";
register(supplier);
```

Cách giải quyết thứ hai: **cast** để chỉ định target type.

```java
register((Callable<String>) () -> "READY");
```

Trong thiết kế API, tránh cung cấp nhiều overload nhận các functional interface không có sự phân biệt rõ về hành vi. Nếu nghiệp vụ cần hai ý nghĩa khác nhau, đặt tên phương thức rõ ràng có thể tốt hơn bắt người dùng cast thường xuyên.

### 7.1. Lambda không phải phương thức overload độc lập

```java
// Không hợp lệ theo ý định “tự chọn bằng kiểu giá trị trả về”:
// execute(() -> 42);
```

Nếu `execute` có nhiều overload, compiler vẫn phải áp dụng quy tắc overload resolution và target typing. Giá trị `42` trong thân lambda không đồng nghĩa với việc luôn ưu tiên một interface trả số. Không nên suy đoán overload được chọn từ cú pháp ngắn gọn của lambda khi tồn tại nhiều target type có thể áp dụng.

## 8. Biến effectively final là gì?

Một biến cục bộ được coi là **effectively final** khi nó đáp ứng quy tắc trong Java Language Specification để có thể được xem như biến `final`, dù **không viết từ khóa `final`**. Trong trường hợp thông thường, đó là biến **được gán đúng một lần và không bị gán lại**, kể cả qua `++`/`--`.

```java
import java.util.function.Supplier;

String prefix = "[INFO] ";
Supplier<String> label = () -> prefix + "Đã xử lý";

System.out.println(label.get()); // [INFO] Đã xử lý
```

Biến `prefix` không được khai báo `final`, nhưng sau khi có giá trị nó không bị gán lại: đây là trường hợp effectively final.

Viết `final` tường minh cũng hợp lệ:

```java
final String prefix = "[INFO] ";
Supplier<String> label = () -> prefix + "Đã xử lý";
```

Điểm chính: **không cần thêm `final` cho tất cả biến được lambda capture**, nhưng compiler vẫn yêu cầu chúng giữ tính effectively final.

### 8.1. Capturing local variables

Khi lambda tham chiếu một biến cục bộ hoặc tham số phương thức được khai báo ngoài thân lambda, nó **capture** biến đó.

```java
static Runnable createPrinter(String message) {
    return () -> System.out.println(message);
}
```

Tham số `message` không bị gán lại trong phương thức nên có thể capture. Lambda vẫn sử dụng được giá trị đó khi được thực thi **sau khi `createPrinter` đã trả về**.

Không cần hiểu capture như việc lambda lấy một biến cục bộ có thể thay đổi và giữ một con trỏ tới ô nhớ trên stack của lời gọi cũ. Theo mô hình ngôn ngữ, chỉ các giá trị cục bộ thỏa điều kiện capture mới được dùng; không phụ thuộc vào chi tiết quản lý bộ nhớ do JVM triển khai.

### 8.2. Gán lại trước hoặc sau dòng khai báo lambda đều vi phạm

```java
int threshold = 10;
threshold = 20;

// LỖI BIÊN DỊCH: threshold không effectively final.
// java.util.function.IntPredicate high = n -> n > threshold;
```

Ngay cả khi việc gán lại nằm **sau** khi tạo lambda, biến vẫn không đạt điều kiện effectively final:

```java
int threshold = 10;

// LỖI BIÊN DỊCH nếu sau đó gán lại threshold:
// java.util.function.IntPredicate high = n -> n > threshold;

threshold++;
```

Compiler phân tích các thao tác gán của biến trong phạm vi liên quan; không chỉ nhìn số lần thay đổi đã xảy ra **trước** biểu thức lambda.

Nếu cần cả cấu hình ban đầu lẫn trạng thái thay đổi, tách thành các biến với ý nghĩa khác nhau:

```java
int threshold = 10;
java.util.function.IntPredicate high = n -> n > threshold;

int nextThreshold = threshold + 1; // Biến mới, không gán lại threshold.
```

### 8.3. Có thể gán giá trị theo các nhánh loại trừ nhau

Một biến không có initializer có thể vẫn là effectively final nếu Java có thể chứng minh mỗi đường thực thi gán cho nó đúng một lần trước khi dùng:

```java
boolean debug = true;
String mode;

if (debug) {
    mode = "DEBUG";
} else {
    mode = "NORMAL";
}

java.util.function.Supplier<String> getMode = () -> mode;
System.out.println(getMode.get()); // DEBUG
```

Dù xuất hiện hai câu lệnh gán trong source code, chỉ một nhánh chạy, và `mode` được gán đúng một lần trên mỗi đường đi. Compiler còn yêu cầu biến phải **definitely assigned** trước chỗ lambda sử dụng nó.

Không được dùng một biến chưa chắc có giá trị:

```java
// LỖI BIÊN DỊCH: value chưa definitely assigned.
// int value;
// Runnable print = () -> System.out.println(value);
```

### 8.4. Tham số phương thức cũng chịu quy tắc effectively final

```java
static Runnable makeTask(int retries) {
    return () -> System.out.println("Retries: " + retries);
}
```

Hợp lệ vì `retries` không bị gán lại.

Nếu viết `retries++` trong phương thức đó, rồi tiếp tục capture `retries`, chương trình không còn biên dịch được. Điều kiện này áp dụng cho biến cục bộ và tham số được khai báo bên ngoài lambda, không chỉ cho biến có kiểu nguyên thủy.

## 9. Mutability của đối tượng khác với tính final của biến tham chiếu

Đây là chỗ dễ nhầm nhất.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

List<String> messages = new ArrayList<>();

Consumer<String> collect = text -> messages.add(text);

collect.accept("Java");
collect.accept("Lambda");

System.out.println(messages); // [Java, Lambda]
```

Biến cục bộ `messages` **không bị gán lại** nên effectively final. Nhưng đối tượng `ArrayList` mà nó tham chiếu vẫn **mutable**; gọi `add` làm thay đổi trạng thái đối tượng.

Do đó:

- Effectively final ràng buộc **phép gán lại biến cục bộ**, không bảo đảm bất biến sâu cho đối tượng.
- `messages = new ArrayList<>()` sau khi lambda capture sẽ làm biến mất tính effectively final.
- `messages.add(...)` không gán lại biến `messages`, vì vậy hợp lệ về mặt cú pháp.
- Hợp lệ cú pháp không có nghĩa là thiết kế tốt trong mọi ngữ cảnh, đặc biệt khi có concurrency.

### 9.1. Vì sao không dùng mảng một phần tử chỉ để “lách” effectively final?

```java
int[] counter = {0};
Runnable increment = () -> counter[0]++;

increment.run();
System.out.println(counter[0]); // 1
```

Đoạn trên biên dịch được vì biến `counter` không được gán lại. Tuy vậy, dùng mảng một phần tử như một **hộp chứa mutable** chỉ để tăng biến ngoài lambda thường che giấu tác dụng phụ và làm logic khó kiểm tra.

Các lựa chọn sáng rõ hơn:

- Nếu đang tính tổng trong stream, dùng `sum()`, `reduce(...)` hoặc collector phù hợp.
- Nếu xử lý tuần tự, dùng vòng `for` thông thường với biến đếm rõ ràng.
- Nếu chia sẻ trạng thái giữa nhiều luồng là yêu cầu thật, chọn cấu trúc concurrent hoặc cơ chế đồng bộ hóa phù hợp. `AtomicInteger` có thể giải quyết một số thao tác đếm nguyên tử, nhưng không biến toàn bộ quy trình thành thread-safe.

**Không nên chọn công cụ đồng thời chỉ để vượt qua lỗi effectively final.** Trước hết nên xem thuật toán có thể chuyển thành phép biến đổi không tác dụng phụ hay không.

## 10. Lambda trong vòng lặp: lưu ý biến `i` và biến mỗi lượt

Trong vòng `for` truyền thống, biến điều khiển thường bị tăng hoặc giảm:

```java
import java.util.ArrayList;
import java.util.List;

List<Runnable> tasks = new ArrayList<>();

// LỖI BIÊN DỊCH vì i thay đổi sau mỗi vòng:
// for (int i = 0; i < 3; i++) {
//     tasks.add(() -> System.out.println(i));
// }
```

Nếu muốn tạo ba tác vụ giữ riêng chỉ số của mỗi lượt, hãy tạo một biến cục bộ mới:

```java
for (int i = 0; i < 3; i++) {
    int index = i; // Mỗi lượt có một index mới, không gán lại.
    tasks.add(() -> System.out.println(index));
}

tasks.forEach(Runnable::run);
```

Kết quả:

```text
0
1
2
```

Với *enhanced for*, biến phần tử là một biến riêng cho từng lượt:

```java
for (String name : List.of("Lan", "Minh")) {
    tasks.add(() -> System.out.println(name));
}
```

Việc lambda capture `name` hợp lệ nếu `name` không bị gán lại trong lượt tương ứng. Tuy vậy, nếu đã có `tasks` chứa các tác vụ từ vòng trước, ví dụ tiếp theo sẽ bổ sung tác vụ mới vào cùng danh sách; khi chạy chúng sẽ in toàn bộ giá trị đã capture. Khi viết ví dụ độc lập, khởi tạo danh sách mới để tránh nhầm.

**Bài học:** Không giả định lambda lấy “giá trị mới nhất của biến `i`” như một ô nhớ có thể cập nhật. Java không cho capture biến cục bộ đang thay đổi như vậy. Hãy tạo một giá trị ổn định cho từng tác vụ.

## 11. `this` và phạm vi tên trong thân lambda

Trong lambda, `this` có ý nghĩa là **instance bao quanh** (nếu đang ở ngữ cảnh instance), không phải một đối tượng “lambda” sở hữu `this` như lớp anonymous riêng biệt.

```java
import java.util.function.Supplier;

class MessageFactory {
    private final String prefix = "[APP] ";

    Supplier<String> create(String text) {
        return () -> this.prefix + text;
    }
}
```

`this.prefix` chỉ trường của `MessageFactory`, không chỉ tới một đối tượng triển khai `Supplier`. Đồng thời, `text` là tham số phương thức và cần effectively final nếu được capture.

Điều này khác với `this` bên trong **anonymous class**, nơi `this` là instance của chính anonymous class.

### 11.1. Trường instance được phép thay đổi mà vẫn được đọc trong lambda

```java
class CounterView {
    private int count;

    Runnable printer() {
        return () -> System.out.println(count);
    }

    void increase() {
        count++;
    }
}
```

Quy tắc effectively final chỉ ràng buộc capture **biến cục bộ/tham số**, không cấm lambda đọc hoặc sửa trường instance. Nhưng giá trị của `count` có thể thay đổi sau khi tạo lambda, vì nó là trạng thái của đối tượng bao quanh.

Nếu nhiều luồng cùng đọc/ghi `count`, phải xét quy tắc Java Memory Model và đồng bộ hóa. **Effectively final không bảo đảm thread safety.**

### 11.2. Biến tham số lambda không được trùng với tên local đang ở phạm vi bao quanh

```java
String name = "Lan";

// LỖI BIÊN DỊCH: trùng tên name ở local scope bao quanh.
// java.util.function.Function<String, String> f = name -> name.strip();
```

Đổi tên tham số:

```java
java.util.function.Function<String, String> f =
        value -> name + ": " + value.strip();
```

Lambda có cách xét phạm vi tên gần với khối code bao quanh, chứ không mở ra một lexical scope tách biệt như một lớp mới. Dùng tên biến rõ nghĩa để tránh trùng và tránh che khuất dữ liệu quan trọng.

## 12. Checked exceptions trong lambda

Kiểu `throws` của functional method ảnh hưởng trực tiếp đến checked exception mà thân lambda được phép phát sinh.

`Runnable.run()` **không khai báo** checked exception:

```java
import java.io.IOException;

// LỖI BIÊN DỊCH: IOException là checked exception.
// Runnable task = () -> {
//     throw new IOException("Lỗi đọc");
// };
```

Trong khi đó `Callable<V>.call()` khai báo `throws Exception`:

```java
import java.io.IOException;
import java.util.concurrent.Callable;

Callable<String> task = () -> {
    throw new IOException("Lỗi đọc");
};
```

Đoạn khai báo `task` trên hợp lệ; **khi gọi `task.call()`**, bên gọi phải xử lý hoặc khai báo ngoại lệ theo quy tắc thông thường.

Không nên bắt mọi checked exception chỉ để chuyển chúng thành `RuntimeException` mà không có quy tắc thiết kế rõ ràng. Nếu API tự xây dựng cần thể hiện khả năng lỗi, có thể định nghĩa functional interface với `throws` phù hợp:

```java
@FunctionalInterface
interface IOAction {
    void run() throws java.io.IOException;
}
```

Việc chọn `Runnable`, `Callable` hay interface riêng phải bắt nguồn từ **hợp đồng lỗi** của thao tác, không chỉ từ độ ngắn của biểu thức lambda.

## 13. Các functional interface chuẩn thường dùng

Phần lớn trường hợp không cần tự định nghĩa interface chỉ để truyền một hành vi đơn giản.

| Interface | Functional method | Ý nghĩa | Ví dụ lambda |
| --- | --- | --- | --- |
| `Predicate<T>` | `boolean test(T value)` | Kiểm tra điều kiện | `s -> !s.isBlank()` |
| `Function<T,R>` | `R apply(T value)` | Biến đổi dữ liệu | `s -> s.length()` |
| `Consumer<T>` | `void accept(T value)` | Thực hiện hành động | `s -> System.out.println(s)` |
| `Supplier<T>` | `T get()` | Tạo/cung cấp giá trị | `() -> "READY"` |
| `BiFunction<T,U,R>` | `R apply(T a, U b)` | Biến đổi hai đầu vào | `(a, b) -> a + b` |
| `UnaryOperator<T>` | `T apply(T value)` | Biến đổi và giữ cùng kiểu | `s -> s.strip()` |
| `BinaryOperator<T>` | `T apply(T a, T b)` | Kết hợp hai giá trị cùng kiểu | `(a, b) -> a + b` |
| `Runnable` | `void run()` | Tác vụ không nhận và không trả giá trị | `() -> System.out.println("OK")` |
| `Callable<V>` | `V call() throws Exception` | Tác vụ trả giá trị, có thể ném checked exception | `() -> "OK"` |

Ví dụ:

```java
import java.util.function.Function;
import java.util.function.Predicate;

Predicate<String> isUseful = s -> !s.isBlank();
Function<String, Integer> size = String::length;

if (isUseful.test("Java")) {
    System.out.println(size.apply("Java")); // 4
}
```

Khi ý định là một hành vi nghiệp vụ cụ thể và cần tên có ý nghĩa như `PriceCalculator` hoặc `PermissionRule`, functional interface tự định nghĩa có thể diễn đạt hợp đồng rõ hơn một `Function<..., ...>` khó đọc.

## 14. Lambda và method reference: chọn cách nào?

Method reference là cú pháp biểu thị việc gọi **một phương thức đã có**, khi chữ ký phù hợp với target type.

```java
import java.util.function.Function;

Function<String, Integer> length1 = text -> text.length();
Function<String, Integer> length2 = String::length;
```

Trong trường hợp này, hai biểu thức có cùng hành vi: nhận `String` và trả độ dài. Chọn `String::length` khi ngắn gọn, rõ ràng.

Nhưng khi cần thêm logic, lambda dễ hiểu hơn:

```java
Function<String, String> normalize =
        text -> text.strip().toUpperCase(java.util.Locale.ROOT);
```

Các dạng method reference phổ biến:

- `String::length`: gọi instance method trên đối tượng đầu vào.
- `Integer::parseInt`: gọi static method.
- `System.out::println`: gọi instance method trên một receiver đã xác định.
- `StringBuilder::new`: tham chiếu constructor phù hợp với functional interface.

Cả method reference và lambda đều cần một **target functional interface**. Method reference không xóa bỏ quy tắc target typing hay hợp đồng checked exception.

## 15. Lazy execution: tạo lambda khác với chạy lambda

Một lambda được gán hoặc truyền làm đối số **không đồng nghĩa thân lambda đã được thực thi**.

```java
import java.util.function.Supplier;

Supplier<String> message = () -> {
    System.out.println("Đang tạo nội dung");
    return "READY";
};

System.out.println("Đã khai báo");
System.out.println(message.get());
```

Kết quả:

```text
Đã khai báo
Đang tạo nội dung
READY
```

Cơ chế này giải thích tác dụng của `Supplier<T>` trong API fallback hoặc deferred computation. Tuy nhiên, không phải tất cả API nhận lambda đều chạy nó vào cùng thời điểm:

- `list.forEach(action)` gọi action trong lúc thực thi `forEach`.
- `stream.map(mapper)` thiết lập bước biến đổi của pipeline; mapper thường chạy khi terminal operation yêu cầu dữ liệu.
- `optional.map(mapper)` gọi mapper khi `Optional` có giá trị ngay tại lời gọi `map`.
- `supplier.get()` chủ động yêu cầu thực thi tính toán.

Do đó, **thời điểm chạy phụ thuộc vào API nhận lambda**, không phải chỉ riêng cú pháp `->`. Khi lambda capture biến và thay đổi trạng thái đối tượng, phải tính đến thời điểm thực thi thực tế.

### 15.1. Capture và concurrency

```java
java.util.List<String> buffer = new java.util.ArrayList<>();
Runnable write = () -> buffer.add("x");
```

Biến `buffer` effectively final, nhưng đối tượng `ArrayList` mutable **không thread-safe cho cập nhật đồng thời**. Nếu nhiều luồng chạy `write.run()` đồng thời, cần thiết kế đồng bộ hóa thích hợp.

Tính effectively final cũng không biến `Supplier` thành cache: nếu supplier đọc trường mutable, mỗi lần gọi `get()` có thể nhận dữ liệu khác nhau; nếu thân lambda có tác dụng phụ, tác dụng phụ có thể xảy ra mỗi lần thực thi.

## 16. Ví dụ hoàn chỉnh: target type, capture và suy luận kiểu

Chương trình sau dùng một functional interface tự khai báo, một số interface chuẩn, lambda có nhiều kiểu thân, method reference và biến cục bộ effectively final. Mọi thao tác sử dụng API chuẩn Java 27.

Tạo file `LambdaTargetTypeDemo.java`:

```java
import java.util.List;
import java.util.Locale;
import java.util.function.Function;
import java.util.function.Predicate;
import java.util.function.Supplier;

public class LambdaTargetTypeDemo {

    @FunctionalInterface
    interface TextFormatter {
        String format(String value);
    }

    static String applyFormatter(String value, TextFormatter formatter) {
        return formatter.format(value);
    }

    static <T, R> R convert(T value, Function<T, R> mapper) {
        return mapper.apply(value);
    }

    static Runnable printer(String prefix, String message) {
        return () -> System.out.println(prefix + message);
    }

    public static void main(String[] args) {
        // Target type cho lambda có một tham số String.
        TextFormatter upper =
                text -> text.strip().toUpperCase(Locale.ROOT);

        System.out.println(applyFormatter(" java 27 ", upper));

        // minLength được capture nhưng không gán lại.
        int minLength = 4;
        Predicate<String> longEnough =
                text -> text.length() >= minLength;

        List<String> words = List.of("  java ", " ", "lambda", "jdk");

        List<String> labels = words.stream()
                .map(String::strip)
                .filter(longEnough)
                .map(upper::format)
                .toList();

        System.out.println(labels);

        // Method reference được đặt vào Function<String, Integer>.
        Function<String, Integer> length = String::length;
        System.out.println(convert("lambda", length));

        // Lambda không nhận đối số, trả về String.
        Supplier<String> status = () -> "READY";
        System.out.println(status.get());

        // printer trả một lambda capture cả prefix và message.
        Runnable log = printer("Trạng thái: ", status.get());
        log.run();
    }
}
```

Chạy bằng JDK 27:

```bash
javac -encoding UTF-8 LambdaTargetTypeDemo.java
java LambdaTargetTypeDemo
```

Kết quả:

```text
JAVA 27
[JAVA, LAMBDA]
6
READY
Trạng thái: READY
```

Phân tích:

1. `TextFormatter` là một functional interface có `format(String)`, vì vậy tham số `text` của lambda được suy luận thành `String`.
2. `upper` được truyền vào `applyFormatter` với target type đã khai báo rõ. Lời gọi `format` diễn ra khi phương thức gọi nó.
3. `minLength` là biến cục bộ được capture trong `Predicate<String>`, không bị gán lại nên effectively final.
4. `words.stream().map(String::strip)` biến đổi chuỗi trước khi lọc; `longEnough` được gọi với giá trị đã được `strip`.
5. `upper::format` là method reference tới instance method trên một formatter đã tạo.
6. `convert("lambda", length)` cho thấy generic method nhận một `Function<String,Integer>`; kết quả `Integer` có thể được in qua `println`.
7. `Supplier<String>` và `Runnable` có functional method không tham số nhưng **khác kiểu kết quả**, nên cần target type phù hợp.
8. `printer` capture hai tham số phương thức; sau khi `printer` trả về, lambda vẫn có thể sử dụng giá trị đã capture.

## 17. Lỗi biên dịch và hiểu nhầm thường gặp

| Cách viết/giả định | Vấn đề | Cách sửa |
| --- | --- | --- |
| `var action = () -> 42;` | Không có functional interface target type | Ghi `Supplier<Integer> action = () -> 42;` |
| `Object action = () -> 42;` | `Object` không phải functional interface | Dùng target type phù hợp hoặc cast tường minh |
| `(var x, y) -> ...` | Trộn tham số `var` và tham số suy luận không khai báo | Dùng `(var x, var y)` hoặc `(x, y)` |
| `(String x, y) -> ...` | Trộn kiểu khai báo và kiểu suy luận | Ghi rõ cả hai hoặc để cả hai suy luận |
| Lambda thân khối trả giá trị nhưng thiếu `return` | Không phù hợp kiểu kết quả functional method | `return` đầy đủ theo đường điều khiển |
| `() -> { return 1; }` gán vào `Runnable` | `Runnable.run` trả `void` | Dùng `Supplier<Integer>`/`Callable<Integer>` |
| Capture biến rồi gán lại bằng `=` hoặc `++` | Biến không effectively final | Dùng biến local không gán lại hoặc biến mới |
| Dùng biến chưa definitely assigned trong lambda | Không bảo đảm có giá trị để capture | Khởi tạo trên mọi đường đi trước khi capture |
| Capture `i` trong vòng `for (int i...)` | `i` bị tăng sau mỗi lượt | Tạo `int index = i;` ở trong thân vòng lặp |
| Nghĩ `final List` là immutable | `final` chỉ ràng buộc gán lại tham chiếu | Dùng collection bất biến khi cần và kiểm soát mutation |
| Dùng `ArrayList` chung từ nhiều lambda chạy song song | Có thể xảy ra race condition | Dùng thiết kế concurrent phù hợp, tránh mutable shared state |
| Lambda ném checked exception trái với functional method | Vi phạm hợp đồng `throws` của target type | Xử lý lỗi hoặc chọn functional interface thích hợp |
| Tin rằng khai báo lambda là thực thi luôn thân | Lambda chỉ thực thi khi được gọi qua API đích | Kiểm tra thời điểm chạy `get`, `run`, `apply` hoặc terminal operation |
| Overload nhận `Supplier` và `Callable` với lambda `() -> "x"` | Lời gọi có thể nhập nhằng | Gán vào biến có kiểu hoặc cast phù hợp |
| Dùng identity của lambda làm logic nghiệp vụ | Instance/cơ chế tạo lambda không phải hợp đồng identity bền vững | Định nghĩa key/value theo dữ liệu, không theo identity lambda |

## 18. Checklist khi thiết kế hoặc đọc lambda

1. **Kiểu đích ở đâu?** Xem phép gán, tham số phương thức, kiểu trả về, cast hoặc ngữ cảnh generic.
2. **Interface đích có đúng một functional method không?** Đếm theo quy tắc functional interface, không nhầm `default`/`static`.
3. **Số lượng tham số và kiểu kết quả khớp không?** Kiểm tra void-compatible/value-compatible body.
4. **Kiểu tham số có rõ không?** Giữ cùng phong cách suy luận, khai báo kiểu tường minh hoặc `var`.
5. **Lambda có capture local variable hay tham số phương thức không?** Biến đó phải effectively final và definitely assigned trước khi dùng.
6. **Có gán lại biến sau khi khai báo lambda không?** Việc gán lại có thể làm code không biên dịch dù nằm sau biểu thức lambda.
7. **Có dùng mutable object qua một tham chiếu capture không?** Đánh giá tác dụng phụ, vòng đời và an toàn đồng thời.
8. **Có tình huống vòng lặp với `i++` không?** Chụp giá trị riêng từng lượt bằng biến cục bộ mới nếu cần.
9. **Có overload nhận nhiều functional interface gần giống nhau không?** Làm rõ target type bằng tên hàm, biến có kiểu hoặc cast.
10. **Thân lambda có checked exception không?** Xác định hợp đồng `throws` của functional method.
11. **Lambda chạy lúc nào?** Tìm chính xác API gọi `run`/`get`/`apply`/`accept`/`test`, và xét eager/lazy.
12. **Có method reference đơn giản hơn không?** Dùng `Class::method` khi diễn đạt rõ ý định; giữ lambda nếu cần nhiều bước xử lý.

**Ghi nhớ:** Lambda là **biểu thức cần target type**; functional interface cung cấp chữ ký đầu vào/đầu ra; biến cục bộ mà lambda capture phải **effectively final**. Một tham chiếu effectively final vẫn có thể trỏ tới đối tượng mutable, nên tính đúng đắn và an toàn luồng vẫn phải được thiết kế riêng.

## 19. Tài liệu chính thức Java SE 27

- [Java Language Specification 27 — §15.27, Lambda Expressions](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.27): ngữ pháp, thân lambda, target typing và semantics lúc chạy.
- [JLS §15.27.1, Lambda Parameters](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.27.1): tham số suy luận, tường minh, `var` và unnamed parameters.
- [JLS §15.27.2, Lambda Body](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.27.2): biểu thức/khối lệnh, `return` và tương thích với functional method.
- [JLS §15.27.3, Type of a Lambda Expression](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.27.3): target type, type compatibility, assignment/invocation/cast context.
- [JLS §4.12.4, `final` Variables](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-4.html#jls-4.12.4): effectively final và quy tắc gán lại biến.
- [JLS §9.8, Functional Interfaces](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html#jls-9.8): định nghĩa functional interface và cách xác định functional method.
- [JLS §9.6.4.9, `@FunctionalInterface`](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-9.html#jls-9.6.4.9): ý nghĩa annotation và kiểm tra compiler.
- [`java.util.function` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/function/package-summary.html): `Function`, `Predicate`, `Consumer`, `Supplier` và các biến thể primitive.
- [`java.util.concurrent.Callable` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/Callable.html): functional method có giá trị trả về và checked exception.
