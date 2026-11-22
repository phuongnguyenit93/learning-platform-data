# Khai báo, kế thừa và ghi đè default method trong Java Interface

## 1. Mục tiêu và bối cảnh hiện hành

**Default method** là phương thức instance có phần triển khai ngay trong một interface, được khai báo bằng từ khóa `default`. Cơ chế này ra đời từ Java 8, **vẫn được Java hiện đại hỗ trợ và sử dụng rộng rãi** trong các thư viện chuẩn, giúp bổ sung hành vi mặc định cho một interface mà không buộc tất cả implementation cũ phải viết lại code ngay.

Bài học này trả lời ba câu hỏi trọng tâm:

1. **Khai báo:** Cú pháp và điều kiện để định nghĩa một default method; khác gì với abstract, static và private interface methods.
2. **Kế thừa:** Khi class triển khai hoặc subinterface mở rộng interface, method mặc định nào được thừa hưởng? Khi nào có xung đột?
3. **Ghi đè:** Cách class/subinterface override, cách chọn implementation khi có hai default cùng chữ ký, và cách gọi lại implementation của superinterface qua `InterfaceName.super.method()`.

Mọi kiến thức cốt lõi dưới đây vẫn áp dụng trên JDK được duy trì hiện nay. Ví dụ chính dùng cú pháp Java 8 để có thể biên dịch với `javac --release 8` trên JDK hỗ trợ tùy chọn này, thay vì yêu cầu chạy một JDK 8 cũ không được cập nhật.

## 2. Cú pháp khai báo và ý nghĩa

Một interface có thể khai báo cả abstract method (không có body) và default method (có body):

~~~java
interface Notifier {
    void send(String recipient, String message); // abstract

    default boolean canSend(String recipient) {
        return recipient != null && !recipient.trim().isEmpty();
    }
}

class ConsoleNotifier implements Notifier {
    @Override
    public void send(String recipient, String message) {
        if (!canSend(recipient)) {
            throw new IllegalArgumentException("Invalid recipient");
        }
        System.out.println(recipient + ": " + message);
    }
}
~~~

Ở đây `ConsoleNotifier` **bắt buộc** thực hiện `send` vì đó là abstract method chưa có implementation. Nhưng class **không bắt buộc** viết `canSend`; nó thừa hưởng default method từ `Notifier`. Khi gọi `notifier.canSend("Lan")`, method mặc định chạy trên instance `ConsoleNotifier`.

Đặc điểm cần ghi nhớ:

- Default method là **instance method** của interface: cần một object triển khai interface để gọi.
- Trong interface, viết `default ReturnType method(Parameters) { ... }`; phần body là bắt buộc.
- Method dạng này là **public** theo quy tắc của interface; có thể viết `public default` nhưng không bắt buộc.
- Không khai báo default method là `static` hoặc `abstract` cùng lúc; hai loại đó có hợp đồng khác.
- Không dùng `default` cho field. Từ khóa này chỉ dùng để khai báo method có implementation trong interface.
- Một default method có thể gọi abstract method của cùng interface, nhờ đó đưa ra **thuật toán chung** và để implementation cung cấp một phần dữ liệu/hành vi cụ thể.
- `@Override` nên được đặt trên method ghi đè trong class hoặc subinterface để compiler phát hiện lỗi chữ ký.

Một default method không biến interface thành class thông thường: **interface không có instance field riêng** để lưu trạng thái của object. Logic mặc định nên dựa vào abstract methods/arguments hoặc trạng thái do implementation cung cấp.

### Default method dùng abstract method làm điểm mở rộng

~~~java
interface Identified {
    String id();

    default String displayName() {
        return "Item-" + id();
    }
}

class Product implements Identified {
    private final String productId;

    Product(String productId) {
        this.productId = productId;
    }

    @Override
    public String id() {
        return productId;
    }
}
~~~

`new Product("42").displayName()` trả `"Item-42"`. Default method không cần biết implementation lưu `id` bằng field, database hay một hàm tính toán; nó chỉ dựa vào abstract contract `id()`.

Đây là dạng thiết kế phù hợp cho **hành vi chung nhỏ, ổn định**; nếu quy trình quá phức tạp và chứa nhiều trạng thái, cân nhắc tách service/class thay vì nhồi nhiều logic vào interface.

## 3. Kế thừa default method không cần ghi đè

Nếu class triển khai interface có default method và không có implementation khác ưu tiên cao hơn, class thừa hưởng default đó:

~~~java
interface Greeting {
    default String greet(String name) {
        return "Hi " + name;
    }
}

class BasicGreeter implements Greeting {
    // Không cần khai báo greet().
}

// new BasicGreeter().greet("Lan") -> "Hi Lan"
~~~

Một **subinterface** có thể kế thừa default method mà không cần viết gì:

~~~java
interface FriendlyGreeting extends Greeting {
    // Kế thừa Greeting.greet(String).
}

class FriendlyService implements FriendlyGreeting {
}

// new FriendlyService().greet("Lan") -> "Hi Lan"
~~~

Trong trường hợp này, cả `BasicGreeter` và `FriendlyService` đều có thể gọi `greet`, dù code class không viết method đó. Đây là **lợi ích tương thích khi mở rộng API**: một default mới có thể cung cấp hành vi cho các implementation hiện có mà không bắt buộc bổ sung cùng method.

Tuy nhiên, **không cam kết rằng mọi thay đổi thêm default method luôn tương thích tuyệt đối**. Nếu interface khác hoặc superclass đã có method cùng chữ ký, có thể xảy ra ưu tiên/xung đột hoặc thay đổi cách phân giải; cần kiểm thử implementation và mã khách hàng khi phát hành API mới.

## 4. Ghi đè default method trong class

Một class có thể override default method như override một instance method thông thường, miễn tuân thủ quy tắc signature, visibility, return type và checked exception:

~~~java
interface Greeting {
    default String greet(String name) {
        return "Hi " + name;
    }
}

class FormalGreeter implements Greeting {
    @Override
    public String greet(String name) {
        return "Xin chào " + name;
    }
}
~~~

Trong `FormalGreeter`, `greet("Lan")` trả `"Xin chào Lan"`. Phương thức ghi đè phải **public** vì method của interface là public; không được hạ visibility thành `protected` hoặc package-private.

### Những thay đổi bị ràng buộc khi override

- **Return type** phải tương thích; với kiểu reference có thể sử dụng *covariant return type* khi hợp lệ.
- **Checked exception** trong method overriding không được mở rộng tùy ý ngoài hợp đồng của method bị override. Unchecked exceptions không bị compiler ràng buộc theo cùng cách.
- **Không giảm quyền truy cập** từ public xuống private/protected.
- **Tên và kiểu tham số** phải đúng với chữ ký override. Đổi tham số có thể trở thành overload, khiến default cũ vẫn tồn tại và code hoạt động không như dự định.
- **`@Override`** không bắt buộc về ngôn ngữ nhưng là thói quen hữu ích giúp phát hiện việc viết sai tên hoặc chữ ký.

~~~java
interface LabelProvider {
    default CharSequence label() {
        return "default";
    }
}

class StringLabelProvider implements LabelProvider {
    @Override
    public String label() { // String là kiểu con của CharSequence.
        return "custom";
    }
}
~~~

Ví dụ `StringLabelProvider` hợp lệ do covariant return type. Tuy nhiên, không thể override bằng một kiểu trả về hoàn toàn không tương thích.

## 5. Subinterface có ba lựa chọn với default method

Với một default method được kế thừa, subinterface có thể:

1. **Giữ nguyên** bằng cách không khai báo lại.
2. **Override bằng một default mới** để thay đổi hành vi.
3. **Khai báo lại thành abstract** để bắt buộc các concrete implementation cung cấp phiên bản riêng.

~~~java
interface Mode {
    default String mode() {
        return "basic";
    }
}

// 1. Giữ nguyên.
interface InheritedMode extends Mode {
}

// 2. Ghi đè bằng default mới.
interface AdvancedMode extends Mode {
    @Override
    default String mode() {
        return "advanced";
    }
}

// 3. Tái khai báo abstract, bỏ implementation mặc định.
interface RequiredMode extends Mode {
    @Override
    String mode();
}

class RequiredService implements RequiredMode {
    @Override
    public String mode() {
        return "service";
    }
}
~~~

`InheritedMode` giữ `Mode.mode()`. `AdvancedMode` cung cấp default `"advanced"` cho các class triển khai. `RequiredMode` không còn cung cấp default đó cho concrete class, nên `RequiredService` phải tự định nghĩa `mode()`.

**Dễ nhầm:** khai báo lại thành abstract trong subinterface là một tính năng chủ động để nâng yêu cầu hợp đồng, **không phải "gọi ngầm" implementation của superinterface**. Khi một concrete class triển khai `RequiredMode`, nó phải có implementation phù hợp từ chính class hoặc superclass; không thể bỏ qua vì `Mode` vốn đã từng có default.

## 6. Thứ tự ưu tiên khi kế thừa nhiều nguồn

Quy tắc thực dụng khi phân giải một instance method có cùng chữ ký:

1. **Method phù hợp trong class/superclass được ưu tiên trước default của interface** (*class wins*). Nếu superclass cung cấp method concrete tương thích, nó được dùng.
2. **Một khai báo override chuyên biệt hơn có thể che khai báo ở superinterface**, ví dụ một subinterface đã override default của interface cha.
3. **Hai default độc lập cùng chữ ký và không có ứng viên ưu tiên** gây lỗi compile-time cho class/interface cụ thể; phải giải quyết bằng override tường minh.
4. Nhiều đường kế thừa dẫn đến **cùng một khai báo default duy nhất** không tự tạo xung đột.

Các quy tắc này là một phần đặc tả Java, không phụ thuộc vào thứ tự interface trong `implements A, B`. Đổi thành `implements B, A` không tự chọn default khác.

### 6.1. Class wins

~~~java
class BaseStatus {
    public String status() {
        return "class";
    }
}

interface Status {
    default String status() {
        return "interface";
    }
}

class StatusService extends BaseStatus implements Status {
    // Không override; BaseStatus.status() được chọn.
}

// new StatusService().status() -> "class"
~~~

Đây không phải lựa chọn ngẫu nhiên: Java ưu tiên method instance thừa hưởng từ class hierarchy so với default method tương ứng của interface.

**Giới hạn quan trọng:** Nếu superclass có abstract method cùng chữ ký, concrete subclass vẫn phải có implementation hợp lệ theo quy tắc của class; đừng giả định default interface tự "lấp chỗ trống" của abstract method trong class hierarchy.

### 6.2. Subinterface chuyên biệt hơn thắng interface cha

~~~java
interface BaseGreeting {
    default String text() {
        return "base";
    }
}

interface SpecialGreeting extends BaseGreeting {
    @Override
    default String text() {
        return "special";
    }
}

class SpecialService implements BaseGreeting, SpecialGreeting {
}

// new SpecialService().text() -> "special"
~~~

`SpecialGreeting` override chính method `BaseGreeting.text`. Nó không phải hai default độc lập cạnh tranh. Khi tham chiếu qua `BaseGreeting`, virtual invocation vẫn chạy implementation được chọn trên instance thực tế.

### 6.3. Hai default độc lập xung đột

~~~java
interface Printable {
    default String render() {
        return "Printable";
    }
}

interface Exportable {
    default String render() {
        return "Exportable";
    }
}

// LỖI nếu mở comment: không biết chọn render() nào.
// class BrokenDocument implements Printable, Exportable { }

// CÁCH SỬA: class tự override.
class Document implements Printable, Exportable {
    @Override
    public String render() {
        return Printable.super.render()
            + " + " + Exportable.super.render();
    }
}
~~~

Lệnh `Printable.super.render()` và `Exportable.super.render()` chỉ rõ default implementation từ **superinterface thích hợp**. Class có thể chọn một bên, kết hợp cả hai hoặc cung cấp logic riêng; miễn nó giải quyết được xung đột theo hợp đồng nghiệp vụ.

**Lưu ý:** Đoạn ở trên là ví dụ class/interface ở mức top-level; khi đặt nhiều ví dụ cùng file sẽ có thể trùng tên, vì vậy **chỉ chương trình hoàn chỉnh tại mục 8 mới là file độc lập để chạy trực tiếp**.

### 6.4. Diamond có cùng nguồn không tự gây lỗi

~~~java
interface Root {
    default String identity() {
        return "root";
    }
}

interface Left extends Root { }
interface Right extends Root { }

class Combined implements Left, Right { }

// new Combined().identity() -> "root"
~~~

Cả hai đường kế thừa đều dẫn tới **cùng một declaration của `Root.identity`**, nên không có hai implementation cạnh tranh. Nếu `Left` ghi đè `identity` còn `Right` chỉ kế thừa từ `Root`, implementation của `Left` có ưu tiên vì nó override declaration ở `Root`. Đừng nhầm mọi hình thoi đa kế thừa với conflict.

### 6.5. Default kết hợp với abstract từ hai nhánh

Một subinterface hoặc class có thể gặp hai superinterface có method **cùng chữ ký tương ứng**, một default và một abstract không override nhau. Đây cũng có thể tạo **xung đột compile-time**, không phải quy tắc "default luôn thắng abstract":

~~~java
interface Cached {
    default String get() {
        return "cached";
    }
}

interface Required {
    String get();
}

// KHÔNG HỢP LỆ nếu bỏ comment; phải khai báo rõ:
// interface Mixed extends Cached, Required { }

// HỢP LỆ: giải quyết bằng khai báo mới.
interface Resolved extends Cached, Required {
    @Override
    default String get() {
        return Cached.super.get();
    }
}
~~~

Cần chú ý luật chọn default có những ràng buộc khác nhau giữa **class hierarchy** và **interface inheritance**. Cách an toàn nhất là override tường minh để làm rõ hành vi, thay vì đoán rằng compiler tự chọn default.

## 7. Cách dùng `InterfaceName.super.method()` đúng chỗ

Trong một class đã `implements` trực tiếp một superinterface phù hợp, cú pháp `InterfaceName.super.method(args)` cho phép **gọi phần thân default** của superinterface đó khi override:

~~~java
interface Traceable {
    default String trace() {
        return "trace";
    }
}

class AuditTrace implements Traceable {
    @Override
    public String trace() {
        return Traceable.super.trace() + "+audit";
    }
}
~~~

`new AuditTrace().trace()` trả `"trace+audit"`. Đây là cách mở rộng hành vi trước/sau một default được chọn mà không sao chép logic.

Những điều **không** nên giả định:

- `InterfaceName.super.method()` không gọi tùy tiện mọi interface trong hệ thống; qualifier phải phù hợp với quan hệ superinterface trực tiếp/được phép tại nơi dùng theo JLS.
- Không thể gọi `InterfaceName.super.method()` từ một class **không có quan hệ** với interface đó.
- Nếu interface cha đã bị subinterface trực tiếp override theo cách làm lời gọi bypass không hợp lệ, bạn không thể dùng qualifier để tùy tiện bỏ qua override chuyên biệt.
- `super.method()` thông thường thuộc class hierarchy; nó không thay cho `InterfaceName.super.method()` để chọn giữa hai default từ interface.
- Default method có thể dùng `this`: đó là **instance của class thực tế đang triển khai**, không phải một "interface object" riêng biệt.

Ví dụ diễn giải `this`:

~~~java
interface Named {
    String id();

    default String describe() {
        return this.getClass().getSimpleName() + ":" + id();
    }
}

class NamedTask implements Named {
    @Override
    public String id() {
        return "T-1";
    }
}

// new NamedTask().describe() -> "NamedTask:T-1"
~~~

Khi gọi default method qua instance `NamedTask`, `this` trỏ đến instance `NamedTask`. Tuy vậy, đừng dùng tên runtime của class làm định danh nghiệp vụ ổn định; ví dụ chỉ giúp hình dung receiver.

## 8. Chương trình hoàn chỉnh: minh họa sáu quy tắc

Tạo file **`DefaultMethodsDemo.java`** với encoding UTF-8. Tất cả interface/class là các kiểu lồng bên trong một public class, do đó chỉ cần một file.

~~~java
public class DefaultMethodsDemo {
    interface Printable {
        default String render() {
            return "Printable";
        }
    }

    interface Exportable {
        default String render() {
            return "Exportable";
        }
    }

    static final class Document implements Printable, Exportable {
        @Override
        public String render() {
            return Printable.super.render()
                + " + " + Exportable.super.render();
        }
    }

    interface Greeting {
        default String greet(String name) {
            return "Hi " + name;
        }
    }

    interface FriendlyGreeting extends Greeting {
        @Override
        default String greet(String name) {
            return "Hello " + name;
        }
    }

    static final class Person implements FriendlyGreeting {
    }

    static class Base {
        public String status() {
            return "from class";
        }
    }

    interface Status {
        default String status() {
            return "from interface";
        }
    }

    static final class Child extends Base implements Status {
    }

    interface Trace {
        default String trace() {
            return "trace";
        }
    }

    static final class Audit implements Trace {
        @Override
        public String trace() {
            return Trace.super.trace() + " + audit";
        }
    }

    interface Resettable {
        default String reset() {
            return "default";
        }
    }

    interface StrictReset extends Resettable {
        @Override
        String reset();
    }

    static final class ResetJob implements StrictReset {
        @Override
        public String reset() {
            return "required";
        }
    }

    @FunctionalInterface
    interface Transformer {
        String apply(String input);

        default String label() {
            return "transformer";
        }
    }

    public static void main(String[] args) {
        System.out.println("conflict: " + new Document().render());
        System.out.println("inherit: " + new Person().greet("Lan"));
        System.out.println("class wins: " + new Child().status());
        System.out.println("override: " + new Audit().trace());
        System.out.println("reabstract: " + new ResetJob().reset());

        Transformer upper = text -> text.toUpperCase(java.util.Locale.ROOT);
        System.out.println("functional: " + upper.apply("java"));
        System.out.println("default helper: " + upper.label());
    }
}
~~~

Với JDK còn được duy trì và compiler hỗ trợ mục tiêu 8:

~~~text
javac --release 8 -encoding UTF-8 DefaultMethodsDemo.java
java DefaultMethodsDemo
~~~

Nếu ứng dụng không cần output bytecode Java 8, có thể biên dịch bằng phiên bản toolchain được cấu hình cho dự án. `--release 8` giúp compiler kiểm tra mức tương thích API/source/bytecode, nhưng **không thay thế** kiểm thử dependency hoặc quyết định về runtime được hỗ trợ.

**Stdout kỳ vọng, đúng 7 dòng:**

~~~text
conflict: Printable + Exportable
inherit: Hello Lan
class wins: from class
override: trace + audit
reabstract: required
functional: JAVA
default helper: transformer
~~~

**Giải thích chính xác từng dòng:**

1. `Document` nhận hai default độc lập từ `Printable` và `Exportable` nên **tự override** và gọi rõ `Printable.super.render()` cùng `Exportable.super.render()`; kết quả `Printable + Exportable`.
2. `FriendlyGreeting` override default của `Greeting` nên `Person` kế thừa `"Hello Lan"` thay vì `"Hi Lan"`.
3. `Child` kế thừa method cụ thể `Base.status()`; method class ưu tiên hơn default `Status.status()`.
4. `Audit` override `Trace.trace()` và gọi lại default qua `Trace.super.trace()` rồi nối ` + audit`.
5. `StrictReset` khai báo `reset()` thành abstract, nên `ResetJob` cung cấp implementation riêng `"required"`.
6. `Transformer` chỉ có **một abstract method** `apply`. Lambda chuyển `"java"` thành `"JAVA"` bằng locale trung lập.
7. `Transformer.label()` là default method, **không** phá điều kiện functional interface, trả `"transformer"`.

Bài này không dựa vào truy cập mạng/file, đồng hồ hoặc thứ tự lặp ngẫu nhiên nên đầu ra được xác định hoàn toàn bởi mã.

## 9. Default method và functional interface

Default methods **không được đếm** khi xác định số phương thức trừu tượng của một functional interface. Vì vậy interface có một SAM cộng nhiều default/helper methods vẫn có thể được đánh dấu `@FunctionalInterface`:

~~~java
@FunctionalInterface
interface StringRule {
    boolean accept(String value); // SAM

    default boolean reject(String value) {
        return !accept(value);
    }

    default String description() {
        return "StringRule";
    }
}

// Trong một phương thức:
StringRule nonBlank = text -> text != null && !text.trim().isEmpty();
System.out.println(nonBlank.accept("Java")); // true
System.out.println(nonBlank.reject(" "));    // true
~~~

Nếu thêm một **abstract method độc lập** `int priority();` vào interface này, `@FunctionalInterface` sẽ khiến compiler báo lỗi; còn `reject`/`description` vẫn là default nên không vi phạm.

**Điểm nâng cao:** Một số method trong interface có chữ ký tương ứng với public instance methods của `Object` không được tính như SAM riêng; tuy nhiên không được dùng `default` để triển khai lại tùy tiện `equals(Object)`, `hashCode()` hay `toString()` bằng default method trong interface. Java đặt ràng buộc đặc biệt nhằm giữ semantics cơ bản của `Object`.

## 10. Default method khác static và private interface method

| Kiểu method trong interface | Có body? | Gọi qua instance? | Được class triển khai thừa hưởng? | Mốc khả dụng |
| --- | --- | --- | --- | --- |
| Abstract | Không | Qua implementation cụ thể | Có nghĩa vụ implement nếu chưa có implementation | Cơ bản của Java interface |
| Default | Có | Có | Có, theo quy tắc phân giải | Java 8 trở đi |
| Static | Có | Không, gọi qua tên interface | **Không** được thừa hưởng như instance method | Java 8 trở đi |
| Private helper | Có | Chỉ bên trong chính interface | Không | Java 9 trở đi |

Ví dụ static method:

~~~java
interface TextRules {
    static boolean isBlankAfterTrim(String value) {
        return value == null || value.trim().isEmpty();
    }

    default boolean isValid(String value) {
        return !TextRules.isBlankAfterTrim(value);
    }
}

// Gọi: TextRules.isBlankAfterTrim("  ")
// Không gọi: new Implementation().isBlankAfterTrim("  ")
~~~

Ví dụ trên dùng `String.trim` vì chương trình nhắm tới API Java 8. `String.isBlank()` được thêm ở Java 11 và **không dùng được với `--release 8`**. Nếu dự án nhắm Java 11+, `isBlank()` có thể phù hợp hơn vì xét whitespace theo semantics Unicode; hai cách không hoàn toàn tương đương. Hãy chọn theo yêu cầu và mục tiêu runtime.

**Private interface methods** hỗ trợ từ Java 9, hữu ích để chia sẻ helper code bên trong các default/static methods của chính interface. Nếu phải biên dịch `--release 8`, không dùng `private` trong interface. Khi triển khai Java hiện đại, nó là tính năng hợp lệ và không phải legacy; khác biệt chỉ nằm ở mức phiên bản nguồn cần hỗ trợ.

## 11. Vấn đề thiết kế và tương thích khi phát triển thư viện

### Vì sao default method được bổ sung?

Giả sử v1 một thư viện định nghĩa:

~~~java
interface Store<T> {
    void save(T entity);
}
~~~

Nếu v2 cần thêm chức năng kiểm tra dựa trên `save`, có thể khai báo default:

~~~java
interface Store<T> {
    void save(T entity);

    default void saveIfPresent(T entity) {
        if (entity != null) {
            save(entity);
        }
    }
}
~~~

Implementation cũ chỉ triển khai `save` vẫn có thể hưởng `saveIfPresent` mà không viết lại code. Đây là động cơ quan trọng khiến default method hữu ích cho API evolution.

Tuy nhiên, khả năng tương thích **có điều kiện**:
- Một implementation có thể đã định nghĩa method cùng chữ ký với behavior khác; việc thêm default không đơn giản là "tính năng mới mà không đụng đến gì".
- Hai interface độc lập sau khi cập nhật đều có default cùng chữ ký có thể tạo conflict cho class đang `implements` cả hai.
- Default mới có thể làm rõ hơn hoặc làm lộ vấn đề về contract, null handling, state và exception.
- Không áp dụng quy tắc "class wins" để kết luận mọi xung đột đều không cần review. Kiểm tra cả **source compatibility** và hành vi runtime của các client.

### Khi nên đặt default method trong interface?

Nên khi:
- Hành vi ngắn, có thể diễn đạt bằng các abstract methods đã được interface định nghĩa.
- Có một mặc định hợp lý cho hầu hết implementation; các implementation đặc biệt vẫn có thể override.
- Tăng khả năng sử dụng API mà không ép mọi class lặp cùng boilerplate.
- Default có ngữ nghĩa ổn định, document rõ input/output và trạng thái lỗi.

Cân nhắc tách helper/service khi:
- Logic cần nhiều field/state độc lập và vòng đời riêng.
- Hành vi dựa vào database, network, transaction hoặc chính sách nghiệp vụ phức tạp.
- Việc thêm default gây nguy cơ collision với ecosystem interface rộng.
- Class con cần điều phối nhiều bước với trạng thái mutable, khiến contract của interface quá mơ hồ.

**Lưu ý về concurrency:** Default method không tự động thread-safe chỉ vì nằm trong interface. Ví dụ `Map.computeIfAbsent` là API phổ biến, nhưng semantics atomicity/concurrency phụ thuộc **implementation cụ thể**, đặc biệt cần phân biệt `Map` thông thường với `ConcurrentMap` hoặc `ConcurrentHashMap`. Tra hợp đồng của kiểu collection dùng trong ứng dụng trước khi suy luận.

## 12. Ví dụ default method trong thư viện chuẩn vẫn đang dùng

Một số method có từ Java 8 đến nay vẫn phổ biến:

- `Iterable.forEach(Consumer<? super T>)`: cho phép xử lý từng phần tử bằng callback; hành vi thứ tự theo đặc tính của nguồn dữ liệu.
- `Collection.removeIf(Predicate<? super E>)`: loại phần tử thỏa điều kiện khi collection hỗ trợ sửa; có thể ném `UnsupportedOperationException` nếu thao tác remove không được hỗ trợ.
- `List.replaceAll(UnaryOperator<E>)`: thay từng phần tử bằng kết quả transform, tuân theo đặc tính implementation.
- `Map.getOrDefault(Object,V)`: trả giá trị được map tới key hoặc mặc định trong trường hợp không có mapping; cần phân biệt giá trị `null` được map với việc không có mapping theo contract.
- `Map.forEach(BiConsumer)`: xử lý cặp key/value; không mặc nhiên bảo đảm thứ tự cho mọi Map.
- `Comparator.reversed()`: tạo Comparator theo thứ tự ngược; đây là **default method** trên `Comparator`.

Một ví dụ ngắn, runnable khi đặt trong method có import:

~~~java
java.util.List<String> values =
    new java.util.ArrayList<String>(
        java.util.Arrays.asList("A", "", "B", " ")
    );

values.removeIf(text -> text.trim().isEmpty());
values.replaceAll(String::toLowerCase);

System.out.println(values); // [a, b]
~~~

Đây là ví dụ minh họa việc dùng default methods của collection; nhớ rằng có collection bất biến hoặc không hỗ trợ thao tác xóa/thay, dù cùng interface `List`/`Collection`. Với Java hiện đại, Java 9+ còn cung cấp factory collections không sửa được; không nên giả định API default luôn có quyền mutate đối tượng.

## 13. Các lỗi phổ biến và cách khắc phục

### Lỗi 1 — Quên `default` dù có body

~~~java
// LỖI:
// interface Logger {
//     void log(String message) { System.out.println(message); }
// }

// ĐÚNG:
interface Logger {
    default void log(String message) {
        System.out.println(message);
    }
}
~~~

Một method instance có body trong interface cần dùng `default` (trừ một số hình thức khác với modifier thích hợp như `private` trên Java 9+). `abstract` không có body.

### Lỗi 2 — Override nhưng hạ visibility

~~~java
interface Check {
    default boolean enabled() {
        return true;
    }
}

// LỖI nếu bỏ comment:
// class CheckImpl implements Check {
//     @Override boolean enabled() { return false; }
// }

// ĐÚNG:
class CheckImpl implements Check {
    @Override
    public boolean enabled() {
        return false;
    }
}
~~~

### Lỗi 3 — Không giải quyết hai default độc lập

~~~java
interface A {
    default String key() { return "A"; }
}
interface B {
    default String key() { return "B"; }
}

// LỖI: class C implements A, B { }

// ĐÚNG:
class C implements A, B {
    @Override
    public String key() {
        return A.super.key();
    }
}
~~~

Không có nguyên tắc "interface viết trước trong implements sẽ thắng". Muốn kết hợp hai default, override tường minh và gọi cả hai nếu hợp đồng cho phép.

### Lỗi 4 — Dùng `super.method()` thay vì qualified interface super

Khi class muốn gọi **default cụ thể của interface**, dùng cú pháp `A.super.method()` hợp lệ tại vị trí triển khai. `super.method()` thường hướng đến superclass trong class hierarchy; nó không chọn được một default độc lập trong danh sách interface.

### Lỗi 5 — Cho rằng default method luôn thay được abstract method

Nếu subinterface **re-abstract** một default hoặc class hierarchy có abstract method tương ứng, concrete class có thể vẫn cần override. Compiler báo lỗi là tín hiệu phải đọc lại contract, không phải lý do để bỏ `@Override` hoặc dùng cast.

### Lỗi 6 — Phụ thuộc vào thứ tự thực thi ngầm

Default method là instance method bình thường: việc nó chạy hay không phụ thuộc lời gọi. Nó không tự động được gọi trước/sau override. Nếu class muốn dùng hành vi gốc, phải gọi `InterfaceName.super.method()` rõ ràng khi quy tắc cho phép.

### Lỗi 7 — Mặc định mọi API Java mới đều tương thích Java 8

Default methods vẫn còn áp dụng; nhưng `private` trong interface là Java 9+, `String.isBlank` là Java 11+, `List.of` là Java 9+, và các API khác có mốc riêng. Dùng `--release 8` khi cần tương thích Java 8, kiểm tra dependency, rồi chạy trên runtime được cập nhật.

## 14. Bài tập thực hành có đáp án định hướng

**Bài 1 — Khai báo:** Viết `interface Validatable` có abstract `boolean valid()` và default `String status()` trả `"OK"` nếu `valid()` true, ngược lại `"INVALID"`. Tạo class cụ thể cho hai trường hợp và in ra kết quả.

**Bài 2 — Kế thừa:** Định nghĩa `interface Parent` có default `name() -> "P"`, `interface Child extends Parent` không override, `class User implements Child`. `new User().name()` trả **P**. Giải thích vì sao không cần implement method trong `User`.

**Bài 3 — Override ở subinterface:** Trong `Child`, thêm `@Override default String name() { return "C"; }`. Giải thích `User.name()` chuyển thành **C** mà không sửa class.

**Bài 4 — Re-abstract:** Tạo `interface StrictChild extends Parent { @Override String name(); }`. Thử `class StrictUser implements StrictChild { }` và quan sát lỗi. Sửa bằng `public String name() { return "S"; }`; kết quả **S**.

**Bài 5 — Class wins:** Viết superclass có `public String name()` trả `"class"` và interface có default cùng chữ ký trả `"interface"`. Tạo subclass `extends` superclass và `implements` interface. Dự đoán **class**.

**Bài 6 — Conflict:** Viết `interface Left`/`Right` đều có default `id()` riêng. Tạo class implement cả hai; sửa compile error bằng override chọn `Left.super.id()` rồi đổi sang kết hợp cả hai.

**Bài 7 — Diamond không xung đột:** Tạo `Root` có default `id()`, `Left extends Root` và `Right extends Root` không override, class implement cả hai. Giải thích tại sao **không** bị lỗi, dù có hai đường kế thừa.

**Bài 8 — Functional interface:** Tạo `@FunctionalInterface interface StringMapper` với abstract `String map(String)` và default `String help()`. Gán một lambda cho `map`, gọi `help` và kiểm tra chỉ có một SAM.

**Bài 9 — Thư viện chuẩn:** Tạo `ArrayList<String>` chứa `"a"`, `""`, `"b"`; gọi `removeIf(String::isEmpty)` rồi `replaceAll(String::toUpperCase)`. Dự kiến `[A, B]`. Giải thích vì sao không nhất thiết thao tác tương tự hợp lệ trên danh sách unmodifiable.

**Bài 10 — Review API:** Bạn chuẩn bị thêm một default method mới vào một interface public có nhiều implementation. Lập checklist: trùng chữ ký với class/superinterface, hợp đồng trả về/throws, null, concurrency, hành vi của implementation cũ, test source/binary compatibility.

**Tiêu chí đạt:** Bạn viết được default method, phân biệt method abstract/default/static/private theo phiên bản, dự đoán đúng thừa kế/override/conflict, gọi `InterfaceName.super` hợp lệ, và chạy `DefaultMethodsDemo.java` khớp 7 dòng stdout.

## 15. Tài liệu tham chiếu chính thức

- Java Language Specification, Chapter 9 — Interfaces, đặc biệt `9.4 Interface Method Declarations và `9.4.1.3 Inheriting Methods with Override-Equivalent Signatures: https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html
- Java Language Specification, `8.4.8.3 Requirements in Overriding and Hiding: https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.8.3
- Java SE API `Iterable`, `Collection`, `List`, `Map` và `Comparator`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/package-summary.html
- Oracle, hướng dẫn thừa kế và ghi đè interface method: https://docs.oracle.com/javase/tutorial/java/IandI/override.html

**Ghi nhớ:** Default method là **implementation mặc định có thể thừa kế và ghi đè**, không phải quyền "đa kế thừa code" không giới hạn. Khi nhiều nguồn có cùng chữ ký, hãy dùng quy tắc Java class-first/specificity/conflict và override tường minh để đảm bảo hành vi rõ ràng, hiện đại và dễ kiểm thử.