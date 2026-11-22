# @FunctionalInterface: annotation tùy chọn để diễn đạt và kiểm tra ý định

Trong Java, một **functional interface** là interface có đúng **một phương thức trừu tượng cần triển khai** theo quy tắc của ngôn ngữ Java. Nó có thể làm **kiểu đích (target type)** cho lambda expression và method reference. Annotation **`@FunctionalInterface` là tùy chọn**: nó diễn đạt rõ ý định thiết kế interface để dùng như một functional interface và yêu cầu compiler kiểm tra tính hợp lệ của ý định đó.

Điểm quan trọng nhất: **một interface trở thành functional interface nhờ cấu trúc phương thức, không phải nhờ gắn annotation**. Ngược lại, thêm `@FunctionalInterface` vào interface có cấu trúc không hợp lệ sẽ gây lỗi biên dịch; annotation không biến nó thành functional interface.

Bài học này tập trung vào ý nghĩa của annotation, cách compiler kiểm tra, các ngoại lệ trong phép đếm phương thức trừu tượng và lựa chọn sử dụng trong thiết kế API Java 17+.

## 1. Functional interface và SAM là gì?

SAM viết tắt của **Single Abstract Method** (một phương thức trừu tượng). Ví dụ:

```java
@FunctionalInterface
interface TextRule {
    boolean test(String text);
}
```

Phương thức `test(String)` không có phần thân; một lambda có thể cung cấp phần triển khai:

```java
TextRule nonBlank = text -> text != null && !text.isBlank();
boolean valid = nonBlank.test("Java"); // true
```

Hai đoạn là ví dụ minh họa có thể đặt trong cùng một chương trình Java; đoạn thứ hai cần nằm trong phương thức hoặc khối khởi tạo. Compiler kiểm tra chữ ký hàm, kiểu tham số, kiểu trả về và các ràng buộc ngoại lệ khi chuyển lambda thành đối tượng của `TextRule`.

**Functional interface là một hợp đồng kiểu.** Lambda không thể tồn tại như một giá trị có kiểu độc lập tùy ý: nó cần một functional interface làm kiểu đích thông qua phép gán, đối số phương thức, ép kiểu hoặc ngữ cảnh được suy luận hợp lệ.

## 2. Vai trò chính xác của @FunctionalInterface

Annotation thuộc `java.lang` nên không cần khai báo `import`:

```java
@FunctionalInterface
interface Formatter {
    String format(String value);
}
```

Khi gặp annotation, compiler xác minh khai báo `Formatter` thực sự đáp ứng các quy tắc của functional interface. Nếu ai đó vô tình thêm một phương thức trừu tượng không tương thích, mã nguồn sẽ không biên dịch được, giúp phát hiện thay đổi làm hỏng hợp đồng từ sớm.

Không có annotation, interface vẫn có thể là functional interface:

```java
interface PlainFormatter {
    String format(String value);
}

// Trong phương thức:
PlainFormatter trim = String::trim;
String result = trim.format("  Hello  "); // "Hello"
```

Vì vậy:

- **Có annotation và hợp lệ**: compiler chấp nhận; lambda/method reference có thể dùng interface đó làm target type.
- **Không có annotation nhưng hợp lệ**: lambda/method reference **vẫn** dùng được.
- **Có annotation nhưng không hợp lệ**: compiler báo lỗi **ngay tại khai báo interface**.
- **Không có annotation và không hợp lệ**: interface có thể vẫn là interface thông thường; nhưng không thể dùng nó như kiểu đích của lambda.

Annotation không sinh thêm phương thức, không tự cung cấp implementation, không thay đổi quy tắc gọi phương thức, không làm lambda chạy nhanh hơn và không bắt buộc phải dùng lambda thay vì anonymous class. Nó cũng không chứng nhận hàm là *pure*, không có side effect, thread-safe hay luôn chạy đúng một lần.

## 3. Quy tắc đếm phương thức trừu tượng: những gì được tính?

Đối với các ví dụ thông thường, hãy xét tập phương thức trừu tượng của interface, kể cả phương thức được **kế thừa**, rồi áp dụng các quy tắc Java để xác định một hợp đồng hàm duy nhất. Những phương thức có chữ ký tương đương và kiểu trả về tương thích có thể cùng biểu diễn một functional method; chỉ đếm số dòng chứa chữ khóa `abstract` sẽ cho kết luận sai.

### 3.1. Một phương thức abstract duy nhất: hợp lệ

```java
@FunctionalInterface
interface StringTransform {
    String apply(String source);
}
```

`apply` là functional method. Phương thức trong interface thông thường mặc định là `public abstract` nếu không có phần thân và không thuộc nhóm ngoại lệ như `default`, `static` hoặc `private`. Vì vậy không cần ghi tường minh `public abstract`.

### 3.2. Default method không làm tăng số abstract method

```java
@FunctionalInterface
interface Validator {
    boolean isValid(String input);

    default boolean isInvalid(String input) {
        return !isValid(input);
    }
}
```

`isInvalid` đã có thân và có thể gọi functional method `isValid`. Interface vẫn hợp lệ; lambda chỉ cần triển khai `isValid`.

### 3.3. Static và private method không phải SAM bổ sung

```java
@FunctionalInterface
interface Labeler {
    String label(String text);

    static Labeler withPrefix(String prefix) {
        String safePrefix = sanitize(prefix);
        return value -> safePrefix + value;
    }

    private static String sanitize(String value) {
        return value == null ? "" : value;
    }
}
```

`withPrefix` là phương thức tiện ích thuộc interface, có thân và được gọi như `Labeler.withPrefix("Hi ")`. `sanitize` là helper riêng của interface; private method trong interface được hỗ trợ từ Java 9. Cả hai không bổ sung nghĩa vụ trừu tượng cho lambda.

### 3.4. Những phương thức tương ứng với public method của Object không được tính

```java
@FunctionalInterface
interface Reporter {
    void report(String message);

    boolean equals(Object other);
    String toString();
}
```

Dù `equals` và `toString` được khai báo không có thân, chúng tương ứng với các phương thức **public** của `java.lang.Object`, nên không được tính là abstract method bổ sung khi xác định functional interface. `report` vẫn là functional method duy nhất.

**Không suy rộng quy tắc này cho mọi phương thức của `Object`.** Ví dụ, `clone()` là `protected` trong `Object`, nên không thuộc ngoại lệ dành cho các phương thức public tương ứng.

### 3.5. Phương thức abstract kế thừa cũng được tính

```java
interface Work {
    void execute();
}

@FunctionalInterface
interface LoggedWork extends Work {
    default void printLabel() {
        System.out.println("work");
    }
}
```

`LoggedWork` không tự khai báo `execute`, nhưng kế thừa nó từ `Work`. Vì thế functional method vẫn là `execute()`, và có thể dùng `LoggedWork action = () -> System.out.println("run");`.

Nếu interface kế thừa nhiều khai báo abstract có chữ ký tương đương, compiler áp dụng quy tắc override-equivalence và return-type substitutability để xác định có một functional method hợp lệ hay không. Trong các trường hợp khó với generic/covariant return, hãy để compiler xác nhận thay vì đếm thủ công.

## 4. Ví dụ Java 17 hoàn chỉnh: có và không có annotation

Lưu thành **`FunctionalInterfaceAnnotationDemo.java`**:

```java
@FunctionalInterface
interface TextFormatter {
    String format(String text);

    // Tương ứng với phương thức public của Object: không tính là SAM thứ hai.
    boolean equals(Object other);

    // Có thân: không tính là abstract method.
    default String twice(String text) {
        return format(text) + " | " + format(text);
    }

    static TextFormatter withPrefix(String prefix) {
        String safe = safePrefix(prefix);
        return text -> safe + text;
    }

    private static String safePrefix(String prefix) {
        return prefix == null ? "" : prefix;
    }
}

// Không gắn annotation, nhưng vẫn là functional interface.
interface PlainFormatter {
    String format(String text);
}

public class FunctionalInterfaceAnnotationDemo {
    public static void main(String[] args) {
        // Lambda: triển khai TextFormatter.format(String).
        TextFormatter tagged = text -> "[Java] " + text;
        System.out.println(tagged.format("Lambda"));
        System.out.println(tagged.twice("SAM"));

        // Static factory tạo lambda có giữ giá trị tiền tố.
        TextFormatter prefixed = TextFormatter.withPrefix("Hi ");
        System.out.println(prefixed.format("Lan"));

        // Method reference dùng được dù PlainFormatter không có annotation.
        PlainFormatter plain = String::trim;
        System.out.println(plain.format("  Hello  "));

        // Functional interface có sẵn trong JDK.
        Runnable task = () -> System.out.println("Runnable chạy");
        task.run();
    }
}
```

Biên dịch và chạy với JDK 17 trở lên trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 FunctionalInterfaceAnnotationDemo.java
java FunctionalInterfaceAnnotationDemo
```

**Stdout chính xác:**

```text
[Java] Lambda
[Java] SAM | [Java] SAM
Hi Lan
Hello
Runnable chạy
```

Giải thích:

1. `TextFormatter` có functional method là `format(String)`. Khai báo `equals(Object)` không làm nó mất tính functional.
2. `tagged` là một lambda thực hiện `format`; lời gọi `twice` dùng default method đã có sẵn và gọi `format` hai lần.
3. `withPrefix` là factory static trả về một `TextFormatter`. Phương thức private static chỉ giúp xử lý đầu vào của factory.
4. `PlainFormatter` không được annotation nhưng `String::trim` vẫn phù hợp chữ ký `String -> String`.
5. `Runnable` minh họa một functional interface chuẩn của JDK. Lambda cung cấp implementation cho `run()`.

Ví dụ còn cho thấy `@FunctionalInterface` **không gắn annotation vào lambda**. Nó gắn vào **khai báo interface**, là nơi định nghĩa hợp đồng nhận lambda.

## 5. Khi compiler phải báo lỗi

### 5.1. Thêm abstract method thứ hai không tương thích

**Đoạn sau cố ý không biên dịch được:**

```java
@FunctionalInterface
interface BrokenRule {
    boolean test(String value);
    String explain(String value);
}
```

Ở đây `test` và `explain` là hai phương thức abstract khác nhau cần triển khai. Annotation bắt compiler báo lỗi vì `BrokenRule` không phải functional interface. Tùy mục tiêu API, có thể:
- Chuyển `explain` thành default method có implementation phù hợp và không phá nghĩa.
- Tách `explain` sang một interface khác.
- Giữ interface có nhiều abstract methods nhưng bỏ annotation, đồng thời chấp nhận rằng interface đó **không** là target type cho lambda.

Không nên sửa chỉ bằng việc xóa annotation nếu ý định ban đầu của API là nhận lambda; khi đó hợp đồng thiết kế vẫn đã bị phá.

### 5.2. Không có abstract method nào

**Đoạn sau cố ý không biên dịch được:**

```java
@FunctionalInterface
interface MarkerOnly {
}
```

Một marker interface rỗng không có functional method để lambda triển khai. Nếu cần kiểu đánh dấu, bỏ `@FunctionalInterface`. Nếu muốn nhận lambda, phải định nghĩa một functional method thực sự có ý nghĩa.

### 5.3. Interface nhiều abstract methods không có annotation

```java
interface TwoOperations {
    void start();
    void stop();
}
```

Bản thân khai báo `TwoOperations` là hợp lệ nếu không annotation. Nhưng **đoạn gán sau cố ý không biên dịch được**:

```java
TwoOperations operations = () -> System.out.println("start");
```

Lambda không thể tự triển khai hai phương thức abstract độc lập. Việc bỏ annotation chỉ loại bỏ bước kiểm tra tại chỗ khai báo; nó không làm cho kiểu đó hỗ trợ lambda.

### 5.4. Annotation phải dùng trên interface phù hợp

`@FunctionalInterface` không dùng để đánh dấu một class hoặc phương thức bình thường. Annotation cũng không chữa được lỗi chữ ký, lỗi generic hoặc các xung đột kế thừa vốn đã khiến khai báo interface không hợp lệ.

## 6. Tác động khi thiết kế và bảo trì API

Giả sử ban đầu API công khai:

```java
@FunctionalInterface
public interface EventHandler {
    void handle(String event);
}
```

Client có thể dùng `event -> System.out.println(event)`. Nếu phiên bản sau thêm `void onError(Throwable error);` dưới dạng abstract method, interface mất tính functional: lambda của client không còn có target type hợp lệ, và compiler phát hiện thay đổi ngay trong module định nghĩa interface nhờ annotation.

Nếu việc thêm hành vi là cần thiết, cân nhắc một `default` method có ngữ nghĩa mặc định đúng, hoặc thiết kế interface mới phù hợp. **Đừng thêm default method chỉ để vượt qua compiler** nếu không tồn tại implementation mặc định hợp lý; điều đó dễ tạo hợp đồng API gây hiểu nhầm.

Gắn `@FunctionalInterface` giúp người đọc hiểu ngay chủ đích sử dụng của interface. Đồng thời, nó đóng vai trò một phép kiểm tra biên dịch lâu dài khi nhiều người cùng bảo trì code. Với interface được thiết kế để truyền callback, predicate, mapper, factory hoặc action, annotation thường là lựa chọn tốt.

Có những interface tình cờ có một abstract method nhưng được thiết kế cho mục đích khác hoặc dự kiến mở rộng theo cách làm mất tính functional. Java cho phép không gắn annotation; quyết định phụ thuộc vào ý định có muốn cam kết giữ hợp đồng SAM qua các thay đổi tiếp theo hay không.

## 7. Liên hệ với các functional interface chuẩn

Trước khi tạo interface riêng, xem các kiểu có sẵn trong JDK:

| Interface | Functional method | Mục đích điển hình |
| --- | --- | --- |
| `Runnable` | `void run()` | Chạy hành động không nhận đối số, không trả kết quả. |
| `Supplier<T>` | `T get()` | Cung cấp hoặc trì hoãn việc tạo giá trị. |
| `Consumer<T>` | `void accept(T value)` | Nhận giá trị để thực hiện hành động. |
| `Predicate<T>` | `boolean test(T value)` | Kiểm tra điều kiện. |
| `Function<T, R>` | `R apply(T value)` | Chuyển đổi đầu vào sang kết quả. |
| `UnaryOperator<T>` | `T apply(T value)` | Biến đổi giá trị và giữ cùng kiểu. |
| `BiFunction<T, U, R>` | `R apply(T left, U right)` | Biến đổi hai đầu vào. |
| `Comparator<T>` | `int compare(T a, T b)` | So sánh hai giá trị để sắp xếp. |
| `Callable<V>` | `V call() throws Exception` | Tính kết quả có thể ném checked exception. |

Các interface generic ở `java.util.function` thường đủ cho những trường hợp đơn giản. Tạo interface riêng khi tên miền nghiệp vụ, ràng buộc kiểu, ngoại lệ, default methods hay khả năng đọc code khiến hợp đồng riêng có ý nghĩa rõ ràng.

Ví dụ:

```java
java.util.function.Predicate<String> valid =
        text -> text != null && !text.isBlank();

boolean ok = valid.test("Java"); // true
```

Đoạn minh họa này có thể đặt trong một phương thức. `Predicate<String>` chính là target type; `@FunctionalInterface` đã được khai báo trên interface `Predicate` của JDK chứ không xuất hiện ở vị trí biến `valid`.

## 8. Những ngộ nhận dễ gặp

- **“Không gắn annotation thì không dùng lambda được.”** Sai. Interface có cấu trúc SAM hợp lệ vẫn làm target type.
- **“Gắn annotation sẽ tự biến interface thành SAM.”** Sai. Compiler từ chối nếu hợp đồng không có đúng một functional method hợp lệ.
- **“Chỉ cần đếm số khai báo phương thức trong file.”** Sai. Cần xét phương thức kế thừa, các khai báo tương đương, phương thức public của `Object`, `default`, `static` và `private`.
- **“Interface có default method thứ hai là không functional.”** Sai. Default method đã có implementation nên không tạo nghĩa vụ triển khai thứ hai.
- **“Interface không khai báo phương thức nào nhưng kế thừa một SAM thì không functional.”** Sai. Abstract method kế thừa vẫn được xét.
- **“Annotation đảm bảo lambda không có side effect.”** Sai. Annotation chỉ kiểm tra hợp đồng cấu trúc interface.
- **“Chỉ dùng lambda, không thể dùng anonymous class.”** Sai. Một functional interface vẫn có thể được triển khai bằng class thường hoặc anonymous class.
- **“Xóa annotation là sửa xong lỗi phát sinh khi thêm SAM thứ hai.”** Sai với API đã cam kết hỗ trợ lambda: cấu trúc không còn tương thích dù annotation biến mất.

## 9. Tự kiểm tra

**Câu 1.** Interface dưới đây có hợp lệ với annotation không?

```java
@FunctionalInterface
interface Task {
    void run();
    default void log() { System.out.println("log"); }
    static Task noOp() { return () -> {}; }
}
```

**Có.** Chỉ `run()` là abstract method cần triển khai.

**Câu 2.** Khi bỏ `@FunctionalInterface` khỏi `Task`, phép gán `Task t = () -> {};` còn hợp lệ không?

**Có.** Interface vẫn có một functional method.

**Câu 3.** `@FunctionalInterface interface Empty {}` có hợp lệ không?

**Không.** Không có abstract method cần triển khai.

**Câu 4.** Nếu thêm `void cancel();` abstract vào `Task`, điều gì xảy ra?

**Không hợp lệ với annotation;** compiler phát hiện hai abstract methods khác nhau. Bỏ annotation vẫn không giúp lambda `() -> {}` triển khai được cả `run` lẫn `cancel`.

**Câu 5.** Vì sao nên gắn annotation vào một interface callback do nhóm phát triển tự định nghĩa?

Vì annotation **nêu rõ ý định** và **đề nghị compiler giữ ràng buộc functional interface qua những lần sửa code**, làm lỗi thay đổi hợp đồng dễ phát hiện ngay khi biên dịch.

Ghi nhớ: **Quy tắc SAM quyết định interface có dùng làm kiểu đích cho lambda được hay không; `@FunctionalInterface` giúp compiler kiểm tra và người đọc nhận ra ý định đó.**