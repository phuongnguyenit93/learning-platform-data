# Vai trò kiểm tra của @FunctionalInterface trong Java

## Mục tiêu

`@FunctionalInterface` là annotation tiêu chuẩn của `java.lang`, được giới thiệu từ Java 8 và vẫn có vai trò rõ ràng trong Java hiện đại: **ghi nhận chủ ý thiết kế một interface là functional interface và yêu cầu trình biên dịch kiểm tra chủ ý ấy**. Đây là một ràng buộc có thể kiểm chứng ngay khi biên dịch, đặc biệt hữu ích khi interface được sửa đổi qua nhiều lần refactor.

Sau bài này, bạn có thể:

- Giải thích chính xác functional interface và **single abstract method (SAM)** là gì.
- Phân biệt việc interface **thực sự là functional interface** với việc **có annotation `@FunctionalInterface`**.
- Dự đoán các khai báo nào bị compiler từ chối, kể cả trường hợp không có SAM, có hai SAM khác nhau hoặc kế thừa phương thức.
- Hiểu vì sao phương thức `default`, `static`, `private` và khai báo lại phương thức `public` từ `Object` không làm tăng số SAM theo cách thông thường.
- Áp dụng annotation khi thiết kế API nhận lambda/method reference và phòng ngừa lỗi thay đổi hợp đồng trong tương lai.
- Biên dịch, chạy và tự kiểm tra ví dụ trên JDK 17+; nhận biết phần cú pháp có từ Java 8 và phần bổ sung về sau.

## 1. Functional interface là một **khái niệm của ngôn ngữ**, không do annotation tạo ra

Một **functional interface** là interface có **một hợp đồng phương thức trừu tượng duy nhất** để lambda hoặc method reference có thể triển khai. Nói “một phương thức abstract” là cách nói gọn; quy tắc chính xác của Java Language Specification (JLS `9.8) còn xét việc gộp các phương thức kế thừa có chữ ký tương đương và bỏ qua khai báo tương ứng các phương thức instance `public` của `Object`.

Ví dụ:

~~~java
interface Greeting {
    String makeMessage(String name);
}
~~~

Đây **đã là một functional interface** dù không có annotation. Nó có đúng một SAM `String makeMessage(String)`, nên dùng được:

~~~java
Greeting greeting = name -> "Xin chào, " + name;
System.out.println(greeting.makeMessage("Lan"));
~~~

Kết quả:

~~~text
Xin chào, Lan
~~~

Bây giờ thêm annotation:

~~~java
@FunctionalInterface
interface Greeting {
    String makeMessage(String name);
}
~~~

**Hành vi lambda không thay đổi**. Ý nghĩa bổ sung là compiler sẽ từ chối khai báo nếu interface không còn thỏa mãn quy tắc functional interface.

Một cách phân biệt hữu ích:

| Câu hỏi | Kết luận |
| --- | --- |
| Không có `@FunctionalInterface`, nhưng interface có đúng SAM hợp lệ, dùng lambda được không? | **Có.** Compiler vẫn nhận ra target type là functional interface. |
| Có `@FunctionalInterface` thì tự động trở thành functional interface dù có hai phương thức abstract độc lập không? | **Không.** Compiler báo lỗi. |
| Annotation có tự sinh SAM, tạo đối tượng hoặc thực thi lambda không? | **Không.** Chỉ biểu đạt chủ ý và kích hoạt kiểm tra khai báo. |
| Annotation có bắt buộc trên mọi interface dùng lambda không? | **Không.** Đây là công cụ bảo vệ hợp đồng khi chủ ý thiết kế là functional interface. |

`@FunctionalInterface` là một **annotation interface** trong `java.lang`, nên không cần import riêng.

## 2. Compiler kiểm tra chính xác điều gì?

Nếu gắn `@FunctionalInterface` lên một kiểu, Java yêu cầu:

1. Kiểu được đánh dấu phải là **interface thường**, không phải class, enum hay annotation interface.
2. Interface phải thỏa mãn **định nghĩa functional interface** ở JLS `9.8 sau khi xét các phương thức abstract của nó và các phương thức kế thừa.

Nếu không thỏa mãn, compiler báo **compile-time error tại khai báo interface được đánh dấu**. Việc bạn có thực sự tạo lambda cho interface ấy hay chưa **không ảnh hưởng** tới yêu cầu kiểm tra.

### Trường hợp hợp lệ: đúng một SAM

~~~java
@FunctionalInterface
interface Formatter {
    String format(String input);
}
~~~

Phương thức `format` mặc nhiên là `public abstract` dù bạn không viết từ khóa. Có thể triển khai bằng class hoặc lambda:

~~~java
Formatter formatter = value -> "[" + value + "]";
~~~

### Trường hợp lỗi: có hai phương thức abstract độc lập

~~~java
// Cố ý không hợp lệ: compiler phải báo lỗi.
@FunctionalInterface
interface BadProcessor {
    void start();
    void stop();
}
~~~

`start()` và `stop()` là **hai hợp đồng độc lập**. Một biểu thức lambda không thể làm triển khai cho cả hai. Việc bỏ annotation có thể khiến khai báo interface thông thường hợp lệ, nhưng interface đó vẫn **không thể** làm target type của một lambda.

### Trường hợp lỗi: không có phương thức abstract hợp lệ

~~~java
// Cố ý không hợp lệ: chỉ có default method, không có SAM.
@FunctionalInterface
interface BadOnlyDefault {
    default void run() {
        System.out.println("running");
    }
}
~~~

Phương thức `default` đã có body, không tạo ra SAM. Interface này không đáp ứng ý nghĩa của annotation.

### Trường hợp lỗi: đánh dấu sai loại kiểu

~~~java
// Cố ý không hợp lệ: class không thể là functional interface.
@FunctionalInterface
abstract class BadType {
    abstract void execute();
}
~~~

Mặc dù abstract class có thể khai báo đúng một abstract method, nó **không phải interface**. Annotation không biến class thành functional interface.

Các đoạn mã trong mục này là **ví dụ lỗi biên dịch có chủ đích**, không nên chép chung vào tệp ví dụ chạy thành công.

## 3. Đếm SAM đúng cách: các phương thức có body

### `default` không làm tăng số SAM

`default` method được hỗ trợ từ Java 8, có body và cung cấp hành vi mặc định:

~~~java
@FunctionalInterface
interface StringRule {
    boolean matches(String text);

    default StringRule negate() {
        return text -> !matches(text);
    }
}
~~~

Chỉ `matches(String)` là SAM. `negate()` là phương thức đã có triển khai; nó tạo một rule mới bằng lambda. Annotation **vẫn hợp lệ** khi interface có nhiều phương thức `default`.

### `static` không làm tăng số SAM

Phương thức `static` thuộc interface thay vì đối tượng, nên có thể dùng làm factory/helper:

~~~java
@FunctionalInterface
interface PositiveRule {
    boolean matches(int value);

    static PositiveRule greaterThan(int threshold) {
        return value -> value > threshold;
    }
}
~~~

`greaterThan` không phải SAM; `matches` vẫn là hợp đồng duy nhất. Cách dùng:

~~~java
PositiveRule rule = PositiveRule.greaterThan(10);
System.out.println(rule.matches(11));
~~~

Kết quả:

~~~text
true
~~~

### `private` cũng không làm tăng số SAM (Java 9+)

Từ Java 9, interface có thể khai báo `private` method để tái sử dụng logic bên trong các phương thức có body:

~~~java
@FunctionalInterface
interface Normalizer {
    String normalize(String input);

    default String normalizeOrEmpty(String input) {
        return normalize(safe(input));
    }

    private String safe(String input) {
        return input == null ? "" : input;
    }
}
~~~

Đây là **đoạn minh họa Java 9+**. `normalize` là SAM; `normalizeOrEmpty` là `default`; `safe` là `private` có body. Khi biên dịch với `--release 8`, cú pháp private method trong interface chưa tồn tại nên không hợp lệ. Trên JDK 17+ hoặc JDK hiện đại, mã này vẫn hợp lệ.

### Quy tắc thực hành

Khi kiểm tra một interface có thể dùng làm target type cho lambda, hãy xác định **những phương thức abstract cần một triển khai**, không đếm tất cả dòng trông giống khai báo phương thức. Phương thức `default`, `static` và `private` không phải SAM.

## 4. Ngoại lệ quan trọng: các phương thức `public` của `Object`

Theo JLS, khi xác định functional interface, một khai báo phương thức abstract có chữ ký tương ứng với **phương thức instance `public` của `java.lang.Object`** không được tính như một SAM mới.

Ví dụ này **hợp lệ**:

~~~java
@FunctionalInterface
interface NamedAction {
    void execute();

    boolean equals(Object other);
    int hashCode();
    String toString();
}
~~~

Dù có bốn khai báo không body, functional interface vẫn có **một hợp đồng chức năng** là `execute()`. Các khai báo `equals(Object)`, `hashCode()`, `toString()` khớp với những phương thức instance `public` của `Object`; implementation object đã có các phương thức tương ứng.

Do đó:

~~~java
NamedAction action = () -> System.out.println("execute");
action.execute();
~~~

Kết quả:

~~~text
execute
~~~

**Không khái quát thành “mọi phương thức của Object đều bị bỏ qua”.** Quy tắc áp dụng tới các phương thức instance **public** của `Object` với chữ ký phù hợp. Ví dụ `clone()` của `Object` là `protected`, nên nếu interface khai báo một phương thức `public clone()` thì không thể tự động coi nó như khai báo `toString()`.

Một interface chỉ khai báo lại `equals(Object)`, không có SAM khác, cũng **không** trở thành functional interface:

~~~java
// Cố ý không hợp lệ: equals(Object) không tạo SAM độc lập.
@FunctionalInterface
interface BadObjectOnly {
    boolean equals(Object other);
}
~~~

Khi thấy `Comparator<T>` có `compare(T,T)` và `equals(Object)`, hãy nhớ vì sao `Comparator<T>` vẫn có thể là functional interface: `compare` là SAM, còn `equals` theo ngoại lệ `Object`.

## 5. Kế thừa interface: không đơn giản đếm tổng số khai báo

Một functional interface có thể **kế thừa** SAM, không nhất thiết khai báo trực tiếp trong body của nó.

~~~java
interface BaseAction {
    void execute();
}

@FunctionalInterface
interface ExtendedAction extends BaseAction {
    default String description() {
        return "extended";
    }
}
~~~

`ExtendedAction` có SAM `execute()` được kế thừa và một `default` method. Vì vậy:

~~~java
ExtendedAction action = () -> System.out.println("done");
action.execute();
System.out.println(action.description());
~~~

Kết quả:

~~~text
done
extended
~~~

Kế thừa hai phương thức abstract có **chữ ký tương đương** cũng có thể vẫn tạo thành **một hợp đồng chức năng duy nhất**:

~~~java
interface FirstTask {
    void perform();
}

interface SecondTask {
    void perform();
}

@FunctionalInterface
interface CombinedTask extends FirstTask, SecondTask {
}
~~~

`CombinedTask` hợp lệ vì hai khai báo `perform()` tương đương nhau. Ngược lại, nếu kế thừa `void perform()` và `void cancel()` thì có hai phương thức khác nhau và `@FunctionalInterface` báo lỗi.

Với trường hợp tổng quát hơn, JLS xét **override-equivalent signatures**, **subsignature** và **return-type-substitutability**; không chỉ kiểm tra số dòng khai báo. Khi có generic hoặc kiểu trả về đồng biến, nên dùng compiler và JLS để xác định thay vì đếm bằng mắt.

## 6. Ví dụ hoàn chỉnh trên JDK 17+: annotation bảo vệ hợp đồng, lambda vẫn ngắn gọn

Tạo tệp **`FunctionalInterfaceCheckDemo.java`**. Mọi interface trong ví dụ là member interface của lớp, giúp chương trình gói trong một tệp độc lập.

~~~java
public class FunctionalInterfaceCheckDemo {

    @FunctionalInterface
    interface TextRule {
        boolean test(String text);

        // Khai báo này tương ứng Object.equals, không tăng SAM.
        boolean equals(Object other);

        default TextRule negate() {
            return text -> !test(text);
        }

        static TextRule nonBlank() {
            return text -> text != null && !text.isBlank();
        }
    }

    // Không có annotation nhưng vẫn là functional interface.
    interface UnmarkedTask {
        void run();
    }

    interface ParentTask {
        void perform();
    }

    @FunctionalInterface
    interface ChildTask extends ParentTask {
        default String name() {
            return "child";
        }
    }

    public static void main(String[] args) {
        TextRule rule = TextRule.nonBlank();
        System.out.println(rule.test("Java"));
        System.out.println(rule.test("   "));
        System.out.println(rule.negate().test("   "));

        TextRule startsWithJ =
                (String value) ->
                        value != null && value.startsWith("J");
        System.out.println(startsWithJ.test("Java"));

        UnmarkedTask task =
                () -> System.out.println("task");
        task.run();

        ChildTask child =
                () -> System.out.println("child-run");
        child.perform();
        System.out.println(child.name());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc bản mới hơn:

~~~bash
javac --release 17 FunctionalInterfaceCheckDemo.java
java FunctionalInterfaceCheckDemo
~~~

Kết quả chính xác:

~~~text
true
false
true
true
task
child-run
child
~~~

Giải thích:

1. `TextRule` có SAM `test(String)`; khai báo `equals(Object)` không tăng số hợp đồng trừu tượng theo quy tắc `Object`.
2. `default negate()` và `static nonBlank()` đều có body, không tăng số SAM.
3. `String.isBlank()` có từ Java 11, vì vậy ví dụ dùng `--release 17`. Annotation `@FunctionalInterface` và lambda tự chúng có từ Java 8.
4. `startsWithJ` dùng lambda với kiểu tham số **tường minh**; `rule.negate()` trả về lambda với kiểu tham số **được suy luận**. Cả hai cùng triển khai `TextRule` hợp lệ.
5. `UnmarkedTask` **không có annotation** nhưng vẫn nhận lambda; compiler nhận ra một SAM.
6. `ChildTask` **có annotation** và nhận lambda triển khai phương thức `perform()` được kế thừa.
7. Khi một refactor vô tình thêm abstract method thứ hai vào `TextRule` hoặc `ChildTask`, compiler sẽ phát hiện interface không còn đúng chủ ý từ chính khai báo được annotation, thay vì chỉ chờ những nơi truyền lambda xuất hiện lỗi.

Nếu dự án cần dùng `--release 8`, giữ nguyên quy tắc annotation và lambda, nhưng dùng API chuỗi có sẵn từ Java 8 (ví dụ kiểm tra `text != null && !text.trim().isEmpty()` khi yêu cầu xử lý khoảng trắng phù hợp). Không được coi `isBlank()` là API Java 8.

## 7. Vai trò trong refactor và bảo vệ API

Giả sử một ứng dụng hiện có:

~~~java
@FunctionalInterface
interface EventHandler {
    void onEvent(String event);
}
~~~

Nhiều caller đang viết:

~~~java
EventHandler handler = event -> System.out.println(event);
~~~

Sau đó một developer muốn thêm chức năng `reset`. Có ba hướng và hậu quả khác nhau:

**A. Thêm abstract method mới — phá hợp đồng SAM**

~~~java
// Cố ý không hợp lệ:
@FunctionalInterface
interface EventHandler {
    void onEvent(String event);
    void reset();
}
~~~

Compiler báo lỗi ngay tại interface vì giờ có hai abstract methods độc lập. Các lambda cũ cũng không còn đáp ứng interface này.

**B. Thêm default method — vẫn giữ SAM**

~~~java
@FunctionalInterface
interface EventHandler {
    void onEvent(String event);

    default void reset() {
        // Hành vi mặc định có chủ đích.
    }
}
~~~

Interface còn một SAM `onEvent` nên lambda cũ vẫn dùng được, với điều kiện logic mặc định thực sự phù hợp nghiệp vụ. Không nên thêm default method rỗng chỉ để né lỗi compiler nếu mọi implementation cần một hành vi `reset` riêng: điều đó có thể giấu một thay đổi hợp đồng thực sự.

**C. Tách chức năng mới thành interface khác**

~~~java
interface Resettable {
    void reset();
}

@FunctionalInterface
interface EventHandler {
    void onEvent(String event);
}
~~~

Đây là một lựa chọn thiết kế khi `reset` không thuộc trách nhiệm tối thiểu của `EventHandler`. Việc tạo interface mới không tự động làm đối tượng handler hỗ trợ `Resettable`; người viết API cần xác định rõ ai triển khai và sử dụng nó.

**Giá trị lớn nhất của `@FunctionalInterface` là giữ chủ ý “interface này phải tiếp tục nhận được lambda” ngay tại nơi khai báo.** Nó bắt được một loại regression khi cấu trúc abstract method bị thay đổi. Tuy vậy, annotation **không kiểm tra toàn bộ compatibility**: đổi tên/phạm vi/kiểu của SAM, đổi hành vi default method hoặc thay ngoại lệ có thể vẫn làm caller bị lỗi hoặc thay đổi nghĩa của chương trình. Cần chạy kiểm tra API và test phù hợp ngoài compiler.

## 8. @FunctionalInterface hoạt động ở lúc nào?

Bản chất của annotation cần phân biệt:

- **Lúc biên dịch:** Compiler kiểm tra kiểu được đánh dấu có phải một functional interface theo JLS hay không. Nếu không, báo compile-time error, kể cả interface chưa được sử dụng.
- **Khi xác định lambda target type:** Compiler xét **cấu trúc functional interface**; annotation **không bắt buộc**. Lambda được type-check dựa trên SAM.
- **Lúc chạy:** JVM không yêu cầu annotation để nhận biết hay gọi đối tượng lambda. Annotation không tự tạo một hàm, không sinh phương thức abstract và không gọi lambda.
- **Metadata:** `@FunctionalInterface` được định nghĩa với `@Retention(RUNTIME)`, `@Target(TYPE)` và `@Documented`. Nghĩa là metadata annotation có thể truy vấn qua reflection và xuất hiện trong Javadoc, nhưng **ý nghĩa kiểm tra SAM vẫn là ràng buộc biên dịch**, không phải cơ chế runtime tự động.

Ví dụ `@FunctionalInterface` khác với annotation được framework xử lý để đăng ký handler hay tạo dependency. Nó thuộc hợp đồng ngôn ngữ Java, không cần Spring, CDI hay thư viện riêng.

## 9. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
| --- | --- |
| “Phải thêm `@FunctionalInterface` thì mới dùng lambda được.” | Sai: interface đáp ứng SAM hợp lệ được dùng làm target type dù không đánh dấu. |
| “Annotation biến interface có hai abstract methods thành functional interface.” | Sai: compiler báo lỗi. |
| “Một interface có thêm `default` method sẽ hết functional.” | Sai: default method có body và không tính vào SAM. |
| “Mọi method khai báo trong interface đều tính một SAM.” | Sai: cần xét `default`, `static`, `private`, public `Object` và kế thừa. |
| “Cứ có một dòng khai báo abstract là chắc chắn functional.” | Sai: một dòng có thể chỉ khai báo lại `Object.equals`; hoặc còn abstract members kế thừa. |
| “Kế thừa hai interface có method cùng tên thì luôn có hai SAM.” | Sai: nếu chữ ký tương đương và hợp lệ, có thể là cùng một function contract. |
| “Annotation phải được JVM dùng để tạo lambda.” | Sai: việc kiểm tra và type-check là ở compiler. |
| “Thêm annotation bảo đảm mọi thay đổi API sau này đều tương thích.” | Sai: chỉ kiểm tra điều kiện structural functional-interface, không đảm bảo toàn bộ hành vi hay binary compatibility. |
| “`@FunctionalInterface` đã cũ vì xuất hiện từ Java 8.” | Sai: vẫn là phần của Java hiện đại; phù hợp với các API được thiết kế để dùng lambda/method reference. |

Một lỗi đặc biệt phổ biến là **xóa annotation để làm interface có hai abstract methods biên dịch được**, sau đó coi như đã sửa vấn đề. Nếu public API vốn được dự kiến dùng qua lambda, thao tác đó chỉ bỏ đi kiểm tra bảo vệ thiết kế, không giữ được tính tương thích của caller.

## 10. Khi nào nên đặt annotation?

**Nên dùng** `@FunctionalInterface` cho interface bạn chủ động thiết kế để biểu diễn một hành vi duy nhất như `Rule<T>`, `Handler<E>`, `Mapper<T,R>` hay `Factory<T>`, đặc biệt khi người dùng API thường truyền lambda/method reference.

Không cần **ép** mọi interface tình cờ chỉ có một abstract method phải mang annotation. Có interface được thiết kế để mở rộng thành hợp đồng có nhiều phương thức theo thời gian; khi đó việc đánh dấu “phải mãi là SAM” có thể diễn đạt sai ý định thiết kế.

Ví dụ generic hợp lệ, áp dụng trong Java hiện đại:

~~~java
@FunctionalInterface
interface Mapper<T, R> {
    R map(T source);
}
~~~

Nó có một SAM `map(T)`; target type như `Mapper<String, Integer>` cho phép compiler suy luận tham số `String` và kết quả `Integer`:

~~~java
Mapper<String, Integer> length = text -> text.length();
System.out.println(length.map("lambda"));
~~~

Kết quả:

~~~text
6
~~~

Chọn annotation dựa trên **cam kết API về số hợp đồng abstract**; chọn lambda hay class implementation dựa trên độ phức tạp của hành vi. Một functional interface vẫn có thể được triển khai bằng class bình thường hoặc anonymous class — annotation không ép mọi người dùng phải viết lambda.

## 11. Cách tự kiểm tra với javac

Nếu muốn thấy compiler giữ hợp đồng ngay tại nơi khai báo, lưu riêng tệp **`InvalidFunctionalInterface.java`** sau:

~~~java
@FunctionalInterface
interface InvalidFunctionalInterface {
    void handle(String text);
    void reset();
}
~~~

Chạy:

~~~bash
javac InvalidFunctionalInterface.java
~~~

**Kết quả mong đợi:** Biên dịch không thành công. Compiler thông báo interface không phải functional interface vì có nhiều abstract methods. Nội dung tiếng Anh và dòng lỗi cụ thể có thể khác theo bản `javac`; đừng so khớp từng ký tự của chẩn đoán.

Để sửa đúng bản chất, chỉ giữ một abstract method trong interface được annotation, hoặc chuyển phương thức bổ sung thành `default` nếu thực sự có một hành vi mặc định phù hợp. Không nên chỉ xóa annotation khi hợp đồng ban đầu chủ đích dành cho lambda.

Một thử nghiệm bổ sung: bỏ annotation ở ví dụ `Greeting` có đúng một SAM. Biên dịch lambda vẫn thành công; đây là bằng chứng annotation **không quyết định khả năng dùng lambda**, mà bổ sung **kiểm tra chủ đích thiết kế**.

## 12. Bài tập áp dụng

**Bài 1.** Dự đoán hợp lệ hay không:

~~~java
@FunctionalInterface
interface A {
    void run();
    default void retry() { run(); }
    static A noop() { return () -> {}; }
}

@FunctionalInterface
interface B {
    void onOpen();
    void onClose();
}

@FunctionalInterface
interface C {
    boolean equals(Object value);
}
~~~

Tự giải thích theo SAM:

- `A` **hợp lệ**, chỉ `run()` abstract; `retry` và `noop` đã có body.
- `B` **không hợp lệ**, có hai abstract methods độc lập.
- `C` **không hợp lệ**, chỉ khai báo lại `Object.equals` nên không có SAM.

Đoạn trên nhằm **phân tích điều kiện compiler**; không biên dịch nguyên khối vì chứa hai khai báo không hợp lệ.

**Bài 2.** Dựa trên mục kế thừa, giải thích vì sao `CombinedTask extends FirstTask, SecondTask` vẫn là functional interface khi hai interface cha cùng khai báo `void perform()`. Điều gì thay đổi nếu một interface cha thêm `void cancel()`?

**Bài 3.** Một developer thêm `void audit()` vào `EventHandler` dùng bởi hàng trăm lambda. Khi có `@FunctionalInterface`, lỗi bị phát hiện ở đâu? Nếu xóa annotation, các caller lambda có tiếp tục hợp lệ không? Vì sao?

**Bài 4.** Với API `Mapper<T,R>`, tạo `Mapper<String,String>` đổi chữ thường thành chữ hoa bằng lambda và viết bản method reference khi có một phương thức phù hợp. Annotation tác động đến hai cách khởi tạo này như thế nào?

**Bài 5.** Tại sao không nên tùy tiện thêm `default void reset() {}` chỉ để tránh lỗi annotation khi nghiệp vụ thực sự đòi hỏi mọi implementation reset trạng thái?

## Tổng kết kiến thức cần giữ

- **Functional interface** được xác định theo hợp đồng abstract của interface và quy tắc JLS, không do annotation sinh ra.
- **`@FunctionalInterface` là khai báo chủ đích và phép kiểm tra tại compile time**: interface được đánh dấu mà không còn là functional interface sẽ gây lỗi ngay khi biên dịch.
- **Lambda/method reference vẫn hoạt động khi annotation vắng mặt**, miễn target type là functional interface hợp lệ.
- **`default`, `static`, `private` không tăng SAM**; public methods tương ứng `Object` được xử lý theo ngoại lệ; các phương thức kế thừa có chữ ký tương đương có thể vẫn đại diện cho một SAM.
- **Dùng annotation để bảo vệ ý định thiết kế API**, đồng thời tiếp tục dùng compiler, test và đánh giá compatibility khi refactor.

## Tài liệu chính thức

1. Java SE 17 API Specification, `java.lang.FunctionalInterface` (mô tả annotation, yêu cầu compiler, `@Retention(RUNTIME)` và `Since 1.8`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/FunctionalInterface.html
2. Java Language Specification, `9.8 Functional Interfaces`: https://docs.oracle.com/javase/specs/jls/se24/html/jls-9.html#jls-9.8
3. Java Language Specification, `9.6.4.9 @FunctionalInterface`: https://docs.oracle.com/javase/specs/jls/se24/html/jls-9.html#jls-9.6.4.9
4. Java Language Specification, `15.27 Lambda Expressions`: https://docs.oracle.com/javase/specs/jls/se24/html/jls-15.html#jls-15.27
5. Oracle API, `java.util.function` — các functional interface chuẩn vẫn được dùng trong Java hiện đại: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html

Các quy tắc trên vẫn áp dụng cho Java hiện hành. Khi sử dụng một JDK mới, hãy đối chiếu thêm bản JLS và Javadoc tương ứng với JDK đang xây dựng hoặc triển khai; phần ví dụ `private` interface method thuộc Java 9+, `String.isBlank()` thuộc Java 11+, trong khi `@FunctionalInterface`, `default`, `static` và lambda là các tính năng có từ Java 8.