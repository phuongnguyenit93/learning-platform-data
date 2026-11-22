# @FunctionalInterface: kiểm tra hợp đồng giao diện hàm trong Java

`@FunctionalInterface` là annotation chuẩn trong `java.lang`, dùng để **yêu cầu trình biên dịch kiểm tra rằng một interface đáp ứng hợp đồng của functional interface** (giao diện hàm). Một functional interface có **một phương thức trừu tượng chức năng** (single abstract method, thường gọi SAM) sau khi áp dụng các quy tắc của ngôn ngữ về kế thừa, phương thức `Object` và các phương thức có chữ ký tương đương.

Hợp đồng này rất hữu ích vì Java có thể dùng **lambda expression** hoặc **method reference** để cung cấp cách triển khai phương thức chức năng đó, thay vì phải tạo một lớp triển khai có tên.

```java
@FunctionalInterface
interface Converter {
    String convert(String input);
}

// Một đối tượng thực hiện hợp đồng Converter.
Converter converter = text -> text.trim();
```

Đoạn trên minh họa cú pháp và giả định đặt trong một phương thức/khối lệnh. `@FunctionalInterface` bảo vệ khai báo `Converter` ở thời điểm biên dịch; Java chỉ chấp nhận lambda vì **kiểu đích là functional interface**, không phải vì annotation tự tạo ra lambda.

## 1. Bài toán mà @FunctionalInterface giải quyết

Giả sử bạn thiết kế một interface để truyền một hành vi xử lý chuỗi:

```java
interface TextProcessor {
    String process(String text);
}
```

Đây là một functional interface hợp lệ, dù **không hề có `@FunctionalInterface`**:

```java
TextProcessor processor = text -> text.toUpperCase();
```

Sau một thời gian, có người thêm phương thức trừu tượng thứ hai:

```java
interface TextProcessor {
    String process(String text);
    boolean isValid(String text);
}
```

Lúc này interface không còn là functional interface. Những nơi dùng lambda làm đối tượng `TextProcessor` sẽ không biên dịch được. Nếu ngay từ đầu viết:

```java
@FunctionalInterface
interface TextProcessor {
    String process(String text);
}
```

thì **ngay tại khai báo interface**, `javac` kiểm tra hợp đồng. Khi ai đó thêm một phương thức trừu tượng độc lập như `isValid`, compiler báo lỗi tại interface đã gắn annotation. Lỗi xuất hiện sớm, gần nơi gây ra thay đổi, và người bảo trì biết đây là một cam kết thiết kế.

**Phân biệt rõ hai ý:**

- **Functional interface** là một đặc tính ngữ nghĩa của kiểu interface theo luật Java. Một interface vẫn có thể là functional interface dù không gắn annotation.
- **`@FunctionalInterface`** là cách khai báo ý định và yêu cầu compiler báo lỗi nếu interface không thỏa luật đó. Nó **không làm interface trở nên functional**, không sinh implementation và không đổi cách chạy của lambda.

## 2. Chính xác điều gì được tính là một phương thức trừu tượng?

Không thể đơn giản đếm số dòng kết thúc bằng dấu `;`. Java xét toàn bộ các phương thức mà interface khai báo hoặc kế thừa, phân biệt phương thức trừu tượng đóng góp vào hợp đồng chức năng với các phương thức khác.

### 2.1. Trường hợp cơ bản: một abstract method

```java
@FunctionalInterface
interface Action {
    void execute();
}
```

Hợp lệ. Phương thức `execute()` trong interface mặc định là `public abstract` khi khai báo như trên. Ví dụ:

```java
Action action = () -> System.out.println("executed");
action.execute();
```

Lúc chạy, dòng `executed` được in do mã gọi `action.execute()`. Bản thân annotation không gọi phương thức.

### 2.2. Default, static và private method không làm tăng số SAM

Interface có thể chứa nhiều phương thức, miễn phần hợp đồng chức năng vẫn chỉ là một phương thức trừu tượng hợp lệ:

- **`default`** có thân triển khai: cho phép cung cấp hành vi chung cho mọi implementation.
- **`static`** thuộc interface: gọi qua tên interface.
- **`private`** có thân triển khai trong interface (Java 9+): giúp chia sẻ logic nội bộ giữa các phương thức có thân.

Các phương thức trên không trở thành SAM. Ví dụ đầy đủ ở mục 3 có cả ba loại.

**Cần nhớ:** thêm default method có thể tạo xung đột với các kiểu liên quan trong một hệ kế thừa cụ thể; “không làm tăng số SAM” không có nghĩa mọi thay đổi default method đều an toàn về tương thích.

### 2.3. Khai báo khớp với public method của Object không được tính thêm

Ví dụ:

```java
@FunctionalInterface
interface NamedTask extends Runnable {
    boolean equals(Object other);
}
```

`Runnable` cung cấp `void run()`. Dù `NamedTask` khai báo `boolean equals(Object)` (một phương thức giống `public Object.equals(Object)`), `equals` không được tính thành một phương thức chức năng bổ sung theo luật Java. Hợp đồng chức năng vẫn là `run()`.

Tương tự, việc khai báo lại chữ ký phù hợp của `toString()` hoặc `hashCode()` từ `Object` không tự tạo thêm SAM. **Không áp dụng ngoại lệ này một cách mù quáng cho mọi phương thức mang tên giống `Object`**: phải xét đúng chữ ký và quy tắc ghi đè đối với public method của `Object`.

### 2.4. Kế thừa nhiều khai báo abstract chưa chắc thành nhiều SAM

Các phương thức kế thừa có thể mô tả **cùng một hợp đồng có chữ ký tương thích**. Ví dụ:

```java
interface First {
    Number value();
}

interface Second {
    Integer value();
}

@FunctionalInterface
interface Combined extends First, Second {
}
```

`Combined` vẫn hợp lệ: hai khai báo `value()` có cùng danh sách tham số, và `Integer` là kiểu trả về con của `Number`, nên Java có thể xác định một phương thức chức năng phù hợp.

Ngược lại, nếu hai phương thức abstract có **tên/tham số độc lập**, chúng tạo thành hai hợp đồng khác nhau và không thể dùng một lambda để triển khai cả hai.

Quy tắc tổng quát khi có generics, overload, kế thừa và kiểu trả về phức tạp liên quan đến **override-equivalent signatures**, khả năng một phương thức ghi đè các khai báo còn lại và kiểu trả về tương thích. Đừng chỉ so sánh chuỗi tên phương thức bằng mắt; để compiler xác thực định nghĩa cụ thể.

## 3. Ví dụ chạy được: SAM cùng default, static, private và lambda

Tạo một file tên **`FunctionalInterfaceDemo.java`**:

```java
import java.util.Locale;

@FunctionalInterface
interface Labeler {
    String label(String input); // Phương thức chức năng duy nhất

    default String decorate(String input) {
        return surround(label(input));
    }

    private String surround(String value) {
        return "[" + value + "]";
    }

    static Labeler upperCase() {
        return value -> value.toUpperCase(Locale.ROOT);
    }
}

public class FunctionalInterfaceDemo {
    public static void main(String[] args) {
        Labeler upper = text -> text.trim().toUpperCase(Locale.ROOT);
        System.out.println(upper.label("  java  "));
        System.out.println(upper.decorate("  java  "));

        Labeler trim = String::trim;
        System.out.println(trim.decorate(" api "));

        System.out.println(Labeler.upperCase().label("lambda"));
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac --release 17 FunctionalInterfaceDemo.java
java FunctionalInterfaceDemo
```

Stdout:

```text
JAVA
[JAVA]
[api]
LAMBDA
```

Giải thích từng phần:

1. `Labeler` chỉ có một phương thức abstract: `String label(String input)`.
2. `upper` là một lambda tương thích với chữ ký `String -> String`. Nội dung lambda cắt khoảng trắng rồi chuyển thành chữ in hoa.
3. `decorate` là default method, gọi phương thức chức năng `label` rồi đặt kết quả trong ngoặc vuông. Nó hoạt động cho mọi implementation của `Labeler`.
4. `surround` là helper private, có thân, và không tạo thêm yêu cầu triển khai cho lambda.
5. `upperCase` là static factory trả về một đối tượng `Labeler` tạo từ lambda.
6. `String::trim` là method reference tới phương thức thể hiện trên `String`: Java liên kết tham số `String` nhận vào với đối tượng được gọi `trim()` và sử dụng kết quả làm giá trị trả về.

Không có đoạn mã nào ở đây đọc annotation bằng Reflection. Công việc kiểm tra hợp đồng thuộc về compiler; lambda và method reference được kiểm tra tương thích với functional descriptor theo các quy tắc kiểu của Java.

Nếu cần tách output .class khỏi source:

```bash
javac --release 17 -d out FunctionalInterfaceDemo.java
java -cp out FunctionalInterfaceDemo
```

Thư mục `out` phải tồn tại hoặc được compiler tạo theo cách phù hợp với môi trường. Kết quả stdout không thay đổi.

## 4. Các khai báo làm compiler từ chối @FunctionalInterface

Mỗi ví dụ trong mục này là một **trường hợp lỗi độc lập**, không ghép cùng file ví dụ chạy thành công ở mục 3.

### 4.1. Hai phương thức abstract độc lập

```java
@FunctionalInterface
interface WrongService {
    void start();
    void stop();
}
```

Lỗi: `start()` và `stop()` tạo hai phương thức trừu tượng riêng. Không có một method descriptor duy nhất cho lambda triển khai.

Để có một functional interface, cần quyết định hành vi nào là cốt lõi; hành vi khác có thể được chuyển thành default method nếu có implementation hợp lý, hoặc tách thành interface khác. **Không nên biến một phương thức thành default giả chỉ để vượt kiểm tra**, vì nó dễ tạo ra hành vi sai nghiệp vụ.

### 4.2. Không có phương thức abstract

```java
@FunctionalInterface
interface EmptyTask {
    default void execute() {
        System.out.println("default");
    }
}
```

Lỗi: không có phương thức abstract để lambda cung cấp cách triển khai. Một interface chỉ có default/static/private method không phải functional interface.

### 4.3. Gắn annotation lên class

```java
@FunctionalInterface
abstract class TaskBase {
    abstract void execute();
}
```

Lỗi: `@FunctionalInterface` áp dụng cho **interface**, kể cả interface kế thừa, không áp dụng cho class hoặc abstract class. Một abstract class có đúng một abstract method vẫn không trở thành functional interface.

### 4.4. Thêm phương thức abstract vào interface đang được dùng bởi lambda

**Trước thay đổi:**

```java
@FunctionalInterface
interface Rule {
    boolean test(String value);
}
```

**Sau thay đổi:**

```java
@FunctionalInterface
interface Rule {
    boolean test(String value);
    String reason(String value);
}
```

Lỗi ở khai báo `Rule` vì phương thức `reason` khiến hợp đồng không còn là SAM. Các call site sử dụng lambda cũng có thể lỗi nếu bỏ annotation đi; bỏ `@FunctionalInterface` chỉ che mất cảnh báo bảo vệ hợp đồng chứ không giải quyết nguyên nhân.

### 4.5. Kế thừa hai hợp đồng thực sự khác nhau

```java
interface Load {
    void load();
}

interface Save {
    void save();
}

@FunctionalInterface
interface LoadAndSave extends Load, Save {
}
```

Lỗi vì `load()` và `save()` khác nhau. Kế thừa nhiều interface **không bị cấm tự thân**, như `Combined` ở mục 2.4 cho thấy; điều quyết định là tập hợp phương thức abstract có gom được thành một hợp đồng chức năng hay không.

## 5. Thử nghiệm thứ hai: kế thừa, Object và lambda vẫn hợp lệ

Tạo file **`SamInheritanceDemo.java`**:

```java
interface First {
    Number value();
}

interface Second {
    Integer value();
}

@FunctionalInterface
interface Combined extends First, Second {
}

@FunctionalInterface
interface NamedTask extends Runnable {
    boolean equals(Object other);
}

public class SamInheritanceDemo {
    public static void main(String[] args) {
        Combined c = () -> 42;
        NamedTask task = () -> System.out.println("done");

        System.out.println(c.value());
        task.run();
    }
}
```

Chạy:

```bash
javac --release 17 SamInheritanceDemo.java
java SamInheritanceDemo
```

Stdout chính xác:

```text
42
done
```

Vì sao chạy được?

- `Combined` thừa kế hai khai báo `value()` tương thích nhau: phương thức do lambda cung cấp trả về `Integer` cho biểu thức `42`, phù hợp cả yêu cầu `Integer` và `Number`.
- `NamedTask` kế thừa `Runnable.run()`. Khai báo `equals(Object)` tương ứng một public instance method của `Object` nên không tạo thêm phương thức chức năng.
- Lambda `() -> System.out.println("done")` cung cấp triển khai cho `run()`; hành vi chỉ xảy ra khi mã gọi `task.run()`.

Các ví dụ đều không yêu cầu thư viện ngoài JDK.

## 6. Vai trò chính xác của annotation trong compiler

`@FunctionalInterface` là annotation chuẩn mà Java compiler nhận biết. Các khai báo annotation kiểu này phải được dùng đúng nơi và thỏa quy tắc functional interface. Nếu không thỏa, compiler phát lỗi biên dịch.

Một số thuộc tính cần phân biệt:

| Khía cạnh | Ý nghĩa |
| --- | --- |
| `@Target(ElementType.TYPE)` | Annotation được khai báo để gắn trên kiểu, nhưng quy tắc đặc biệt của `@FunctionalInterface` còn yêu cầu kiểu đó phải là interface hợp lệ |
| `@Retention(RetentionPolicy.RUNTIME)` | Metadata của annotation này được giữ để có thể truy vấn tại runtime; **không có nghĩa runtime là nơi xác nhận hợp đồng** |
| `@Documented` | Annotation có thể xuất hiện trong tài liệu API do công cụ như Javadoc sinh |
| Compiler enforcement | `javac` kiểm tra hợp đồng functional interface tại compile time |
| Lambda target typing | Compiler xác định kiểu đích có phải functional interface và lambda/method reference có tương thích với descriptor hay không |

Chú ý: việc **gắn** `@FunctionalInterface` không bắt buộc khi sử dụng lambda. Ví dụ interface chuẩn `Runnable` là functional interface và được Java coi là kiểu đích hợp lệ nhờ hợp đồng của nó; việc một interface không gắn annotation **không đủ để kết luận** lambda không thể dùng.

Tương tự, `@FunctionalInterface` không tương đương `@Override`. Cả hai giúp compiler kiểm tra ý định thiết kế, nhưng `@Override` kiểm tra một phương thức có ghi đè/triển khai phương thức từ supertype đúng luật hay không, còn `@FunctionalInterface` kiểm tra hình dạng hợp đồng abstract của **cả interface**.

## 7. Lambda cần kiểu đích: annotation không tự định nghĩa thuật toán

Xét:

```java
@FunctionalInterface
interface Check<T> {
    boolean test(T input);
}
```

Vì chỉ có một phương thức `boolean test(T)`, bạn có thể dùng:

```java
Check<String> nonBlank = value -> !value.isBlank();
boolean result = nonBlank.test("Java"); // true
```

Compiler dựa trên **kiểu đích `Check<String>`** để suy luận kiểu tham số `value` là `String`, kiểm tra biểu thức lambda trả về `boolean` và tạo cách thực thi tương ứng khi chương trình chạy.

Dòng `nonBlank.test("Java")` mới là chỗ gọi hành vi. Annotation không tự làm phép kiểm tra chuỗi.

Một functional interface dùng generics vẫn có thể hợp lệ; số lượng tham số kiểu (`<T>`) không tương đương số lượng phương thức abstract. Tính hợp lệ phụ thuộc tập hợp các phương thức cần được triển khai.

Lỗi lambda không nhất thiết có nghĩa interface không phải functional interface. Chẳng hạn `Check<String> invalid = value -> value.length();` không hợp lệ vì lambda trả `int` trong khi phương thức chức năng phải trả `boolean`. `@FunctionalInterface` trên `Check` vẫn đúng; **chính implementation lambda không khớp kiểu**.

Method reference (`String::trim`, `System.out::println` khi phù hợp kiểu đích) chịu nguyên tắc tương tự: kiểm tra chữ ký phù hợp functional descriptor, không cần một annotation xử lý runtime.

## 8. Khi bảo trì thư viện: thay đổi nào giữ, thay đổi nào phá hợp đồng?

Giả sử bạn công bố:

```java
@FunctionalInterface
public interface MessageHandler {
    void handle(String message);
}
```

Người dùng thư viện có thể viết:

```java
MessageHandler handler = message -> System.out.println(message);
```

Đánh giá một số thay đổi:

| Thay đổi đối với `MessageHandler` | Có giữ SAM không? | Lưu ý |
| --- | --- | --- |
| Thêm một phương thức `default` có thân | Thường có | Số phương thức abstract không tăng; vẫn cần xem xung đột kế thừa |
| Thêm `static` utility method | Có | Không phải phương thức chức năng của instance |
| Thêm `private` helper có thân | Có | Chỉ phục vụ nội bộ interface |
| Thêm một abstract method khác chữ ký, khác hợp đồng | Không | Annotation bắt lỗi sớm, lambda cũ không còn tương thích |
| Thêm khai báo phù hợp public method của `Object` | Có thể có | Chỉ khi đáp ứng chính xác quy tắc chữ ký hợp lệ |
| Đổi tham số/kiểu trả về của SAM | Có thể vẫn là SAM | Nhưng lambdas, method references và code đang dùng API có thể phải sửa |

Khi thiết kế API cho callback, event handler hoặc strategy một hành vi, hãy gắn `@FunctionalInterface` để khẳng định rằng **khả năng truyền implementation bằng lambda là một phần của hợp đồng mong muốn**. Đừng dùng nó nếu interface chủ ý yêu cầu nhiều hành vi abstract độc lập.

Một default method có thể mở rộng hành vi mà không yêu cầu mọi lambda cũ cài thêm phương thức. Tuy nhiên tương thích nguồn, tương thích nhị phân và hành vi là những vấn đề riêng; bảng trên **chỉ kiểm tra hợp đồng functional interface**.

## 9. Nhầm lẫn phổ biến

**“Không gắn `@FunctionalInterface` thì không dùng được lambda.”** Sai. Compiler nhìn vào đặc tính của kiểu đích. Annotation làm rõ ý định và bật kiểm tra trực tiếp tại khai báo interface.

**“Functional interface chỉ được khai báo đúng một method.”** Sai. Nó có thể có default, static, private và phương thức tương ứng với public method của `Object`; còn phải xét phương thức kế thừa và tương đương chữ ký.

**“Một method abstract trong chính file interface là đủ.”** Chưa chắc. Interface có thể kế thừa thêm abstract methods từ các interface cha. Phải xét toàn bộ hợp đồng thực tế.

**“Kế thừa hai interface chắc chắn không dùng lambda.”** Sai. Nếu các abstract methods tương thích và tổng hợp được thành một chức năng, ví dụ `Combined` vẫn là functional interface.

**“Gắn annotation sẽ tự sinh code/lambda implementation.”** Sai. Compiler xác minh hình dạng interface. Lambda hoặc class triển khai vẫn phải được cung cấp từ phía mã ứng dụng.

**“Vì annotation tồn tại ở runtime nên JVM mới quyết định hợp đồng.”** Sai. Java compiler kiểm tra luật functional interface khi biên dịch. Việc metadata còn tồn tại ở runtime không làm thay đổi cơ chế kiểm tra này.

**“Nếu thêm abstract method làm lỗi, cứ xóa annotation là xong.”** Sai. Khi interface còn nhiều phương thức abstract độc lập, lambda vẫn không có một phương thức chức năng duy nhất để triển khai. Cần xem lại thiết kế interface.

## 10. Bài tập tự kiểm tra

**Bài 1.** Đoán khai báo nào được xem là functional interface:

```java
interface A {
    void run();
}

@FunctionalInterface
interface B {
    void run();
    default void reset() {}
}

@FunctionalInterface
interface C {
    void run();
    int count();
}

@FunctionalInterface
interface D extends Runnable {
    String toString();
}
```

**Bài 2.** Với `@FunctionalInterface interface Reader { String read(); }`, nếu muốn thêm khả năng `readOrDefault()` mà vẫn giữ tương thích lambda, bạn sẽ khai báo theo hướng nào?

**Bài 3.** Vì sao dòng `Labeler trim = String::trim;` trong ví dụ 3 hợp lệ nhưng `Labeler invalid = String::length;` không hợp lệ?

**Bài 4.** Giải thích khác biệt giữa lỗi ở định nghĩa một interface có hai abstract methods và lỗi ở lambda có kiểu trả về không khớp SAM.

**Bài 5.** Một interface không gắn `@FunctionalInterface` nhưng có một SAM. Nó có dùng được lambda không? Rủi ro gì nếu người khác thêm một abstract method thứ hai trong lúc bảo trì?

### Gợi ý lời giải

1. `A`, `B` và `D` là functional interface; `C` không hợp lệ với annotation vì có hai phương thức abstract độc lập. `D` chỉ có `Runnable.run()` là phương thức chức năng vì `toString()` phù hợp public method của `Object`.
2. Dùng một **default method có thân**, chẳng hạn `default String readOrDefault() { ... }` với logic dựa trên `read()`; đánh giá hành vi mặc định thích hợp trước khi đưa vào API.
3. `String::trim` tương thích kiểu `String -> String` của `Labeler.label`, còn `String::length` trả `int`, không khớp `String` yêu cầu.
4. Lỗi định nghĩa nghĩa là không tồn tại một hợp đồng chức năng hợp lệ; lỗi lambda có thể xảy ra ngay cả khi interface hợp lệ, do thân lambda không đáp ứng chữ ký/kiểu trả về.
5. Có. Annotation không bắt buộc; thiếu nó thì dự án mất một tín hiệu ý định và một lỗi kiểm tra trực tiếp tại khai báo nếu hợp đồng bị phá vỡ.

## 11. Checklist trước khi dùng @FunctionalInterface

1. Interface thực sự mô tả **một hành vi trừu tượng** sau khi xét cả phương thức kế thừa chưa?
2. Những phương thức bổ sung có phải default/static/private, hoặc thuộc ngoại lệ phù hợp với phương thức public của `Object` không?
3. Generic types, tham số và kiểu trả về của SAM có phù hợp với lambda hoặc method reference dự kiến không?
4. Một thay đổi mới có vô tình thêm abstract method thứ hai và phá API callback không?
5. Compiler đã kiểm tra thành công khi biên dịch toàn bộ interface và các call site liên quan chưa?

`@FunctionalInterface` là một **cam kết thiết kế được compiler kiểm chứng**: interface công bố đúng một hành vi abstract có thể cung cấp bằng lambda hoặc method reference. Hiểu quy tắc đếm abstract methods và vai trò của compiler sẽ giúp bạn thiết kế callback/strategy rõ ràng, đồng thời phát hiện sớm các thay đổi gây lỗi cho người dùng API.