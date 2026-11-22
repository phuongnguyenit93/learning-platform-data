# Thành viên mặc định và giới hạn tùy ngôn ngữ của giao diện

Trong OOP, **giao diện (interface)** mô tả một khả năng hoặc hợp đồng mà những lớp khác nhau có thể thực hiện. Tuy nhiên, không phải ngôn ngữ nào cũng cho phép interface chứa cùng loại thành viên. Ngay trong Java, tập tính năng của interface cũng đã phát triển: ngoài phương thức trừu tượng, Java hiện đại còn hỗ trợ **phương thức mặc định (`default`)**, phương thức `static`, và phương thức hỗ trợ `private`.

Để hiểu đúng chủ đề, cần phân biệt hai nghĩa của từ *mặc định*:

- **Thành viên được ngầm gán modifier:** ví dụ, một phương thức thông thường chỉ có chữ ký trong Java interface được hiểu là `public abstract`; field của interface ngầm là `public static final`.
- **Phương thức `default`:** phương thức có **thân cài đặt sẵn** ngay trong interface, dùng từ khóa `default`. Lớp triển khai có thể kế thừa hoặc override cách cài đặt này theo quy tắc Java.

Không được nhầm **`default` trên interface method** với **quyền truy cập package-private** thường được gọi là “default access” ở Java. Hai khái niệm hoàn toàn khác nhau.

Bài sử dụng Java 17 để giải thích các quy tắc, ví dụ biên dịch được, những lỗi dễ mắc và điểm khác nhau khi chuyển ý tưởng sang các ngôn ngữ khác.

## 1. Thành viên nào được phép xuất hiện trong Java interface?

| Loại thành viên | Java 17 hỗ trợ? | Ý nghĩa, giới hạn |
|---|---|---|
| Phương thức `public abstract` | Có | Khai báo hành vi mà implementation phải đáp ứng |
| Phương thức `default` | Có (từ Java 8) | Có thân hàm; implementation có thể sử dụng hoặc override |
| Phương thức `public static` | Có (từ Java 8) | Tiện ích gắn với chính interface; gọi bằng `TenInterface.method()` |
| Phương thức `private`, `private static` | Có (từ Java 9) | Helper nội bộ cho các phương thức có thân của interface |
| Field/hằng số | Có | Mọi field đều ngầm là `public static final` và phải có initializer |
| Field instance có thể thay đổi | Không | Interface Java không lưu trạng thái instance trực tiếp |
| Constructor | Không | Không thể tạo trực tiếp instance của interface |
| Khối khởi tạo instance | Không | Không có đối tượng interface để khởi tạo |
| Phương thức `protected` / package-private | Không | Phương thức interface chỉ có các mức truy cập hợp lệ theo quy tắc `public` hoặc `private` |
| Interface lồng nhau | Có | Có thể định nghĩa kiểu lồng trong interface, với các quy tắc modifier tương ứng |
| Kế thừa nhiều interface | Có | Một interface có thể `extends` nhiều interface |
| Một class implements nhiều interface | Có | Nhưng phải giải quyết xung đột phương thức theo quy tắc Java |

Một vài quy tắc cú pháp cần nhớ:

~~~java
interface Auditable {
    String auditId();               // Ngầm là public abstract.
    int MAX_EVENTS = 100;           // Ngầm là public static final.

    default boolean canAudit() {    // Public default method.
        return !auditId().isBlank();
    }

    static boolean validId(String id) {
        return id != null && !id.isBlank();
    }

    private String normalizedId() {
        return auditId().strip();
    }
}
~~~

`normalizedId()` ở đây là private helper hợp lệ, dù ví dụ nhỏ chưa gọi đến nó. Các phương thức không có `private` trong interface thường là public; field không thể biến thành biến riêng theo từng đối tượng.

### Vì sao `default` quan trọng?

Trước Java 8, khi thêm một phương thức trừu tượng vào một interface đang có nhiều implementation, các lớp triển khai thường phải cập nhật mã. Phương thức `default` giúp interface đưa ra **một cách cài đặt chung hợp lệ**, để những lớp triển khai hiện có có thể dùng hành vi mới trong nhiều trường hợp.

Nhưng `default` không tự động bảo đảm mọi thay đổi đều tương thích: xung đột tên phương thức, kế thừa, ý nghĩa nghiệp vụ, hoặc mã đã biên dịch trước đó vẫn có thể gây vấn đề. Chỉ nên thêm default method khi có hành vi chung thực sự đúng cho mọi implementation mà nó áp dụng.

## 2. Ví dụ Java hoàn chỉnh: abstract, default, static và private

Hãy tưởng tượng ứng dụng có nhiều thực thể cần được hiển thị tên, chẳng hạn người dùng và hóa đơn. Interface `Named` quy định khả năng cung cấp tên, đồng thời có quy tắc chung để tạo nhãn hiển thị.

Một hóa đơn ngoài vai trò `Named` còn có vai trò `Loggable`; cả hai interface đều cung cấp `default label()`. Lớp hóa đơn phải giải quyết sự trùng lặp này.

Lưu toàn bộ thành **`Demo.java`**, dùng Java 17 trở lên:

~~~java
public class Demo {
    public static void main(String[] args) {
        User user = new User("  Lan  ");
        Invoice invoice = new Invoice("INV-07");

        System.out.println(user.label());
        System.out.println(user.shortLabel());
        System.out.println(invoice.label());
        System.out.println(Named.isValidName("  Mai  "));
        System.out.println(Named.MAX_NAME_LENGTH);
    }
}

// Hợp đồng: mọi đối tượng Named có thể trả về tên của nó.
interface Named {
    // Field của interface ngầm là public static final.
    int MAX_NAME_LENGTH = 40;

    // Phương thức trừu tượng ngầm là public abstract.
    String name();

    // Phương thức mặc định: có implementation chung.
    default String label() {
        return "Tên: " + normalize(name());
    }

    // Một default method có thể gọi abstract method và helper private.
    default String shortLabel() {
        String text = normalize(name());
        return text.length() <= 12
                ? text
                : text.substring(0, 12) + "...";
    }

    // Public static method: thuộc interface, không gắn với instance.
    static boolean isValidName(String candidate) {
        return candidate != null
                && !candidate.isBlank()
                && withinLimit(candidate.strip());
    }

    // Private instance method: helper cho default methods.
    private String normalize(String raw) {
        return raw.strip();
    }

    // Private static method: helper cho static method.
    private static boolean withinLimit(String text) {
        return text.length() <= MAX_NAME_LENGTH;
    }
}

// Một vai trò độc lập, tình cờ cũng có method label().
interface Loggable {
    default String label() {
        return "[log]";
    }
}

// Chỉ cần hiện thực abstract method name().
final class User implements Named {
    private final String displayName;

    User(String displayName) {
        if (!Named.isValidName(displayName)) {
            throw new IllegalArgumentException("Tên không hợp lệ");
        }
        this.displayName = displayName.strip();
    }

    @Override
    public String name() {
        return displayName;
    }
}

// Triển khai hai interface cùng có default label().
final class Invoice implements Named, Loggable {
    private final String number;

    Invoice(String number) {
        if (!Named.isValidName(number)) {
            throw new IllegalArgumentException("Mã không hợp lệ");
        }
        this.number = number;
    }

    @Override
    public String name() {
        return number;
    }

    // Bắt buộc giải quyết xung đột default label().
    @Override
    public String label() {
        return Named.super.label() + " | " + Loggable.super.label();
    }
}
~~~

Chạy:

~~~bash
javac Demo.java
java Demo
~~~

Kết quả:

~~~text
Tên: Lan
Lan
Tên: INV-07 | [log]
true
40
~~~

**Giải thích các vị trí đáng chú ý:**

1. `Named.name()` không có thân: `User` và `Invoice` phải hiện thực phương thức này.
2. `Named.label()` và `Named.shortLabel()` có thân: `User` sử dụng implementation mặc định mà không phải viết lại.
3. `Named.isValidName(...)` được gọi từ constructor của hai class. Nó là static method nên được gọi bằng **tên interface**.
4. `normalize()` và `withinLimit()` là private helper bên trong `Named`. Chúng không xuất hiện trong API mà client/implementation được phép gọi.
5. `MAX_NAME_LENGTH` là hằng số chung; không có bản sao field riêng cho từng `User` hoặc `Invoice`.
6. `Invoice` không thể kế thừa một cách mơ hồ cả hai default `label()`. Nó override và quyết định kết quả, có thể gọi `Named.super.label()` hoặc `Loggable.super.label()` để tận dụng hai implementation sẵn có.

Đây là ví dụ về **tái sử dụng hành vi mặc định mà không cần chia sẻ một lớp cha có trạng thái**.

## 3. Cơ chế giải quyết xung đột default method

Java cho phép một class implements nhiều interface, nhưng không cho chọn tùy tiện một implementation khi xảy ra xung đột cùng chữ ký.

Ba quy tắc thực dụng:

| Trường hợp | Quy tắc |
|---|---|
| Superclass có instance method phù hợp | Phương thức từ class thường được ưu tiên trước default method từ interface (*class wins*) |
| Một interface con cụ thể hơn override default của interface cha | Phương thức từ interface chuyên biệt hơn được chọn |
| Hai default method độc lập cùng chữ ký | Class triển khai phải override để giải quyết xung đột |

### Trường hợp 1: class thắng interface

~~~java
interface HasLabel {
    default String label() {
        return "interface";
    }
}

class Base {
    public String label() {
        return "class";
    }
}

class Derived extends Base implements HasLabel {}

class Test {
    public static void main(String[] args) {
        System.out.println(new Derived().label()); // class
    }
}
~~~

`Derived` thừa hưởng `label()` từ `Base`. Java không dùng default `HasLabel.label()` để ghi đè phương thức của superclass.

### Trường hợp 2: interface chuyên biệt hơn

~~~java
interface ParentRole {
    default String role() { return "parent"; }
}

interface ChildRole extends ParentRole {
    @Override
    default String role() { return "child"; }
}

class Agent implements ParentRole, ChildRole {}

class Test {
    public static void main(String[] args) {
        System.out.println(new Agent().role()); // child
    }
}
~~~

Trong trường hợp này `ChildRole` mở rộng `ParentRole` và định nghĩa hành vi chuyên biệt hơn; đó là implementation được kế thừa.

### Trường hợp 3: hai default độc lập

~~~java
interface A {
    default String message() { return "A"; }
}

interface B {
    default String message() { return "B"; }
}

// class C implements A, B {} // Lỗi biên dịch: xung đột default.
class C implements A, B {
    @Override
    public String message() {
        return A.super.message() + B.super.message();
    }
}
~~~

Khi override, class có thể viết logic hoàn toàn mới hoặc dùng cú pháp `InterfaceName.super.method()` để gọi một default method hợp lệ từ interface. Cú pháp này có các điều kiện về interface kế thừa trực tiếp/phương thức được phép gọi; không phải cách tùy ý gọi default của mọi tổ tiên trong hệ phân cấp.

Sơ đồ cách lựa chọn ở mức khái quát:

~~~mermaid
flowchart TD
    A["Lời gọi instance method"] --> B{"Superclass có method phù hợp?"}
    B -->|Có| C["Ưu tiên implementation từ class"]
    B -->|Không| D{"Có default từ interface chuyên biệt hơn?"}
    D -->|Có| E["Chọn implementation chuyên biệt"]
    D -->|Không| F{"Có hai default độc lập xung đột?"}
    F -->|Có| G["Class phải override và giải quyết"]
    F -->|Không| H["Dùng default method hợp lệ"]
~~~

Sơ đồ phục vụ nhận diện các tình huống thường gặp, không thay thế đầy đủ quy tắc phân giải phương thức trong Java Language Specification.

## 4. Các quy tắc modifier dễ hiểu sai

### 4.1. Phương thức chỉ có chữ ký là `public abstract`

Hai cách khai báo sau có ý nghĩa tương đương:

~~~java
interface Vehicle {
    void move();
    public abstract int speed();
}
~~~

Khi lớp không abstract triển khai, method phải được khai báo `public`:

~~~java
class Bicycle implements Vehicle {
    @Override
    public void move() {
        System.out.println("Đang di chuyển");
    }

    @Override
    public int speed() {
        return 12;
    }
}
~~~

Sai nếu viết:

~~~java
// class BrokenBicycle implements Vehicle {
//     void move() {}   // Lỗi: đang giảm quyền truy cập public.
//     public int speed() { return 12; }
// }
~~~

Không thể biến một phương thức của interface thành `protected` hay package-private chỉ vì class triển khai không muốn public.

### 4.2. `default` là một loại phương thức có thân

~~~java
interface Greeting {
    default String greet() {
        return "Xin chào";
    }
}
~~~

`default` ở đây **không** có nghĩa package-private. Phương thức có thể được client gọi công khai qua tham chiếu interface. Không thể kết hợp `default` với `abstract`, `static` hoặc `private` cho cùng một phương thức theo cách tùy ý: mỗi modifier có quy tắc hợp lệ riêng.

Một implementation có thể override:

~~~java
class FormalGreeting implements Greeting {
    @Override
    public String greet() {
        return "Kính chào quý khách";
    }
}
~~~

Khi override, vẫn phải giữ phạm vi truy cập phù hợp và tôn trọng hợp đồng hành vi.

### 4.3. Phương thức `static` phải gọi qua tên interface

~~~java
interface TextTools {
    static boolean isBlank(String text) {
        return text == null || text.isBlank();
    }
}

System.out.println(TextTools.isBlank("  ")); // true
~~~

Đoạn gọi `System.out.println` nằm trong phương thức Java thích hợp. Không dùng `new TextTools()` vì interface không có constructor. Static method của interface **không được kế thừa như instance method** vào class triển khai:

~~~java
class TextService implements TextTools {}

// TextService.isBlank("x"); // Không hợp lệ với static interface method.
// new TextService().isBlank("x"); // Cũng không hợp lệ.
~~~

Khác với instance default method, `static` method không tham gia đa hình override theo kiểu đối tượng. Nếu class khai báo phương thức static trùng tên/chữ ký, đó là một khai báo riêng, không phải override static method của interface.

### 4.4. Phương thức `private` là chi tiết nội bộ

~~~java
interface GreetingFactory {
    default String greetUser(String name) {
        return wrap("Xin chào " + normalize(name));
    }

    static String greetGuest() {
        return wrapStatic("Xin chào khách");
    }

    private String normalize(String name) {
        return name == null ? "bạn" : name.strip();
    }

    private String wrap(String value) {
        return "[" + value + "]";
    }

    private static String wrapStatic(String value) {
        return "[" + value + "]";
    }
}
~~~

Private method trong interface có thân và chỉ được dùng từ mã thích hợp **bên trong chính interface**, không thể được client gọi, không thể bị override như một phần của hợp đồng và không thể là abstract. Cả private instance method và private static method đều được Java 17 hỗ trợ.

Có thể dùng helper `private static` từ những method khác trong interface, trong khi private instance method cần ngữ cảnh instance của interface. Hai dạng có phạm vi mục đích khác nhau.

## 5. Field trong interface luôn là public static final

Đây là điểm đặc biệt quan trọng:

~~~java
interface Limits {
    int MAX_ITEMS = 100;
}
~~~

Trong Java, câu trên được hiểu tương đương:

~~~java
interface Limits {
    public static final int MAX_ITEMS = 100;
}
~~~

`MAX_ITEMS` là **một hằng số gắn với interface**, không phải số lượng mặt hàng của từng instance.

Bạn không thể viết:

~~~java
// interface Wrong {
//     private int count = 0;  // Lỗi: field không thể private.
//     int count;              // Lỗi: field cần initializer.
// }
~~~

Dù `final`, hằng tham chiếu vẫn có thể trỏ tới một đối tượng **mutable**:

~~~java
import java.util.ArrayList;
import java.util.List;

interface Settings {
    List<String> CODES = new ArrayList<>();
}

// Settings.CODES = new ArrayList<>(); // Lỗi: không gán lại field final.
// Settings.CODES.add("A1");          // Vẫn có thể sửa nội dung List!
~~~

Field này ngầm là `public static final`, **không có nghĩa danh sách bất biến**. Công khai mutable object dưới dạng hằng số là thiết kế nhiều rủi ro: người gọi có thể sửa trạng thái chung mà không qua kiểm soát.

Nên dùng bất biến phù hợp, ví dụ:

~~~java
interface SupportedCodes {
    List<String> VALUES = List.of("A1", "B2");
}
~~~

Trong dự án thực tế, nếu hằng số chỉ liên quan đến một nhóm chức năng, có thể dùng một lớp `final` hoặc cấu hình có tên rõ ràng thay vì biến một interface thành “kho hằng số” (*constant interface anti-pattern*).

Ngoài ra, **field của interface phải được khởi tạo**, nhưng không nhất thiết mọi initializer là compile-time constant theo nghĩa JLS. Ví dụ có thể là `new Object()`, dù làm vậy cần thận trọng về vòng đời và trạng thái dùng chung.

## 6. Interface không có trạng thái instance, constructor hoặc vòng đời riêng

Không thể khai báo một field thay đổi độc lập cho từng đối tượng triển khai ngay trong interface:

~~~java
// interface Session {
//     int requestCount = 0; // Đây vẫn là static final, không phải instance.
//     Session() {}          // Không có constructor interface.
// }
~~~

Nếu mỗi session phải có số lần request riêng, class cài đặt lưu field:

~~~java
interface SessionCounter {
    int getRequestCount();
    void recordRequest();
}

final class UserSession implements SessionCounter {
    private int requestCount;

    @Override
    public int getRequestCount() {
        return requestCount;
    }

    @Override
    public void recordRequest() {
        requestCount++;
    }
}
~~~

Interface quy định những việc có thể làm với một session; class giữ trạng thái và cài đặt hành vi. Các default method có thể gọi getter/abstract method để sử dụng trạng thái của đối tượng triển khai, nhưng bản thân interface **không cấp phát instance field riêng**.

Interface cũng không thể được tạo bằng `new SessionCounter()`. Bạn có thể tạo một instance của class implements interface, hoặc dùng anonymous class/lambda khi quy tắc loại interface cho phép.

## 7. Giới hạn đặc biệt: phương thức của `Object`

Mọi object Java có các phương thức công khai như `toString()`, `equals(Object)`, `hashCode()` từ `Object`. Interface được phép khai báo chữ ký trừu tượng tương ứng để nêu hợp đồng, nhưng không được cung cấp default implementation trực tiếp cho các phương thức khớp với các phương thức public non-static của `Object`.

Ví dụ không hợp lệ:

~~~java
// interface Described {
//     default String toString() { // Lỗi biên dịch.
//         return "Đối tượng";
//     }
// }
~~~

Muốn tùy chỉnh `toString()`, hãy override trong **class** cụ thể:

~~~java
interface Described {
    String description();
}

final class Note implements Described {
    private final String text;

    Note(String text) {
        this.text = text;
    }

    @Override
    public String description() {
        return text;
    }

    @Override
    public String toString() {
        return "Note[" + text + "]";
    }
}
~~~

Lý do là các quy tắc tương tác giữa `Object` và phương thức interface khác với việc cung cấp default của một phương thức nghiệp vụ thông thường. Đây là một giới hạn Java cụ thể; không nên suy ra mọi ngôn ngữ có interface đều áp dụng chính xác cùng quy tắc.

## 8. Interface có thể kế thừa interface, nhưng không kế thừa class

Một interface Java có thể mở rộng nhiều interface:

~~~java
interface Readable {
    String read();
}

interface Writable {
    void write(String text);
}

interface ReadWrite extends Readable, Writable {
    default boolean canEdit() {
        return true;
    }
}
~~~

Một class implements `ReadWrite` phải đáp ứng `read()` và `write()` trừ khi nó là abstract, hoặc các phương thức đó đã có implementation hợp lệ từ class cha.

`interface` không được `extends` một class:

~~~java
// class Base {}
// interface Wrong extends Base {} // Lỗi.
~~~

Một **class** chỉ được trực tiếp `extends` một class nhưng có thể `implements` nhiều interface:

~~~java
class BasicDocument {}

class EditableDocument extends BasicDocument
        implements Readable, Writable {
    @Override
    public String read() {
        return "Nội dung";
    }

    @Override
    public void write(String text) {
        // Implementation minh họa.
    }
}
~~~

Đó là cơ chế cho phép **nhiều vai trò** mà không đưa toàn bộ lớp vào một cây kế thừa implementation phức tạp.

### Default method không phải một cách kế thừa trạng thái

Việc nhiều interface có default implementation không biến Java thành ngôn ngữ cho phép một class kế thừa nhiều superclass có instance fields, constructors và initialization logic. Java vẫn giữ phân biệt **kế thừa implementation từ một class** với **triển khai nhiều hợp đồng giao diện**.

## 9. Interface và abstract class: phương thức mặc định khác gì phương thức thường?

Một default method trong interface và một concrete method trong abstract class đều có thân, nhưng vai trò thiết kế khác nhau.

| Tiêu chí | Interface có default method | Abstract class có concrete method |
|---|---|---|
| Có field instance | Không | Có |
| Có constructor | Không | Có |
| Một class kế thừa bao nhiêu | Implements nhiều interface | Extends trực tiếp tối đa một class |
| Thích hợp cho | Hành vi chung từ một khả năng/contract | Hành vi và trạng thái dùng chung của họ class |
| Xử lý trùng method | Có quy tắc default conflict, có thể phải override | Class method có thứ tự kế thừa class |
| Có thể dùng `protected` cho instance method | Không | Có |
| Có thể có `private` helper | Có | Có |

Ví dụ abstract class cho phép lưu trạng thái chung:

~~~java
abstract class BaseWorker {
    protected int completedJobs;

    protected BaseWorker() {
        completedJobs = 0;
    }

    public void markCompleted() {
        completedJobs++;
    }

    public abstract void perform();
}
~~~

Interface thuần túy có thể chỉ quy định:

~~~java
interface Worker {
    void perform();
    default boolean isAvailable() {
        return true;
    }
}
~~~

Nếu một nhóm class cần chung constructor, field và invariant, abstract class hoặc **composition** có thể hợp lý hơn. Nếu nhiều loại class khác nhau chỉ cần cùng một hành vi/khả năng, interface phù hợp hơn. Không có quy tắc “default method luôn tốt hơn abstract class”.

## 10. Java khác những ngôn ngữ khác ở đâu?

Ý tưởng “giao diện là một hợp đồng” có tính phổ quát, nhưng các hạn chế cú pháp và khả năng cung cấp implementation **phụ thuộc ngôn ngữ và phiên bản**.

| Ngôn ngữ | Có thể đặt implementation sẵn trong cấu trúc interface? | Trạng thái/khả năng đặc trưng |
|---|---|---|
| **Java 17** | Có, qua `default`; có `static` và `private` method | Không có instance field/constructor trong interface; field ngầm `public static final` |
| **C# hiện đại** | Có thể có default interface implementation | Hệ thống member, property và quy tắc triển khai khác Java; không bê nguyên quy tắc Java sang |
| **Kotlin** | Interface method có thể có thân | Interface có thể khai báo property với accessor nhưng không có backing field riêng |
| **TypeScript** | Interface là hợp đồng kiểu tĩnh, không mang phần cài đặt runtime của phương thức | Interface theo cơ chế structural typing và bị loại bỏ sau biên dịch sang JavaScript |

Ví dụ gần nghĩa trong TypeScript:

~~~typescript
interface Greeter {
  greet(name: string): string;
}

class FriendlyGreeter implements Greeter {
  greet(name: string): string {
    return "Hello " + name;
  }
}
~~~

Interface TypeScript không trực tiếp chứa mã chạy như Java `default method`. Muốn tái sử dụng implementation, TypeScript thường dùng class, function, mixin hoặc composition tùy trường hợp.

Trong Kotlin, một interface có thể có property khai báo bằng accessor, nhưng không thể lưu một backing field của property ấy bên trong interface như class thông thường. Trong C#, các tính năng interface và khả năng gắn implementation phụ thuộc phiên bản ngôn ngữ/runtime. Không nên giả định việc C# có một tính năng tương tự Java `default` thì mọi quy tắc xung đột, kế thừa và dispatch đều giống nhau.

Đặc biệt, **“interface” không đồng nghĩa với “một thứ bắt buộc chỉ có các chữ ký trống”** trong mọi ngôn ngữ và phiên bản. Khi chuyển dự án giữa Java, Kotlin, C# và TypeScript, cần đối chiếu tài liệu cú pháp, khả năng biểu diễn trạng thái và quy tắc thực thi cụ thể của công nghệ đang dùng.

## 11. Những thay đổi của Java qua phiên bản

| Giai đoạn | Năng lực đáng chú ý |
|---|---|
| Java trước 8 | Interface chủ yếu dùng abstract methods và các hằng số; chưa có default/static interface methods như cách hiện đại |
| Java 8 | Thêm `default` và `static` methods trong interface |
| Java 9 | Thêm private instance/static helper methods trong interface |
| Java 17 | Có đầy đủ các dạng trên; Java cũng hỗ trợ sealed classes/interfaces để kiểm soát những kiểu được phép mở rộng |

Một ví dụ sealed interface (Java 17):

~~~java
sealed interface PaymentResult permits Approved, Declined {}

record Approved(String transactionId) implements PaymentResult {}
record Declined(String reason) implements PaymentResult {}
~~~

Đây là một **giới hạn về tập lớp có thể triển khai interface**, không phải một dạng default method. `permits` xác định các lớp con trực tiếp được cho phép; các lớp đó tuân thủ những quy định tương ứng như `final`, `sealed` hoặc `non-sealed` theo ngữ cảnh.

Vì bài tập dựa trên Java 17, những ví dụ về `private` method trong interface hoặc sealed interface sẽ không biên dịch nếu đem nguyên xi sang phiên bản Java quá cũ.

## 12. Sử dụng default method có trách nhiệm

Default method không nên trở thành nơi giấu logic nghiệp vụ phức tạp hoặc trạng thái toàn cục. Một default method tốt thường:

- **Được diễn đạt dựa trên các phương thức đã có của hợp đồng**, giống `label()` gọi `name()`.
- Có cách thực hiện hợp lý cho **mọi implementation** chấp nhận hành vi mặc định ấy.
- Không giả định class triển khai có field, constructor hoặc cấu trúc nội bộ cụ thể.
- Giữ đúng ý nghĩa nghiệp vụ và rõ ràng về exception/side effect.
- Được kiểm tra khi có nhiều interface kế thừa hoặc triển khai giao nhau.

Ví dụ `label()` dựa trên `name()` khá tự nhiên. Nhưng đặt một default `saveToDatabase()` giả định tất cả lớp đều có connection, transaction và table sẽ là abstraction không đáng tin, trừ khi hợp đồng thực sự cung cấp đủ khả năng và quy tắc cần thiết.

### Interface evolution có rủi ro gì?

Giả sử interface công khai đã được nhiều plugin triển khai. Khi thêm một default method mới:

1. Các implementation cũ **có thể** dùng được mà không phải bổ sung phương thức.
2. Nếu class đã khai báo method cùng tên/chữ ký với quyền truy cập không phù hợp, mã nguồn có thể phát sinh lỗi tương thích.
3. Nếu plugin đồng thời triển khai interface khác có default method trùng chữ ký, có thể phát sinh xung đột.
4. Nếu default method giả định precondition mới hoặc thay đổi side effect, các client có thể gặp hành vi ngoài mong đợi.
5. Tương thích mã nguồn, nhị phân và hành vi là ba khái niệm khác nhau; cần kiểm tra theo phiên bản phân phối của thư viện.

Do đó `default` **giảm bớt một loại thay đổi bắt buộc** khi mở rộng interface; nó không phải tấm vé cho phép sửa public API mà không kiểm thử.

## 13. Các lỗi biên dịch và hiểu lầm thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| Cho rằng mọi interface method đều abstract | Java 8+ cho phép `default`/`static`, Java 9+ cho phép `private` | Phân biệt các dạng method theo modifier |
| Dùng `default` như quyền truy cập package-private | `default` trên interface method là implementation công khai mặc định | Phân biệt từ khóa `default` với việc bỏ access modifier ở class |
| Gọi static method qua đối tượng triển khai | Static interface method không được kế thừa như instance method | Dùng `InterfaceName.method()` |
| Viết `private int count` trong interface | Field luôn ngầm `public static final` | Đặt trạng thái instance trong class triển khai |
| Cho rằng field `final List` có nội dung bất biến | Final chỉ ngăn gán lại tham chiếu | Dùng dữ liệu/collection bất biến và quản lý state |
| Implements hai interface có default trùng chữ ký mà không override | Không có quy tắc chọn tự động giữa hai default độc lập | Override để giải quyết |
| Cài method interface với quyền truy cập package-private | Abstract interface method ngầm public | Override bằng `public` |
| Định nghĩa `default toString()` trong interface | Không được cung cấp default ghi đè phương thức public non-static của `Object` | Override `toString()` trong class |
| Coi private interface helper là API cho implementation | Private helper không thuộc hợp đồng được kế thừa | Công khai khả năng phù hợp hoặc giữ helper nội bộ |
| Dùng interface chỉ để thay mọi class | Tăng abstraction không cần thiết, thiếu trạng thái chung | Chọn interface, class, abstract class hoặc composition theo nhu cầu |
| Sao chép cách viết từ ngôn ngữ khác | Quy tắc interface khác nhau | Kiểm tra tính năng theo ngôn ngữ và phiên bản |

## 14. Tự kiểm tra kiến thức

**Câu 1.** Interface sau khai báo `int LIMIT = 10;`. `LIMIT` có phải là field riêng của mỗi instance không?

**Đáp án:** Không. Trong Java interface, field ngầm `public static final`; nó gắn với interface và được khởi tạo theo quy tắc của lớp/interface.

**Câu 2.** Một class implements interface có `default greet()` nhưng không override phương thức ấy. Code có thể gọi `greet()` trên instance class không?

**Đáp án:** Có, nếu không có xung đột và không có quy tắc khác ghi đè hành vi. Class có thể kế thừa default implementation hợp lệ.

**Câu 3.** Hai interface không liên quan đều có `default String message()`. Class implements cả hai có thể để trống phần thân không?

**Đáp án:** Không. Class phải override `message()` và chọn hoặc kết hợp hành vi phù hợp.

**Câu 4.** Viết `User.isValidName("Lan")` có thay được `Named.isValidName("Lan")` khi `User implements Named` không?

**Đáp án:** Không. Static method trong interface không được kế thừa sang class `User`; phải gọi qua tên interface khai báo.

**Câu 5.** Có thể khai báo `private String normalize(...)` có thân bên trong interface Java 17 không?

**Đáp án:** Có. Đây là private helper của interface, không phải một phương thức mà class implements được phép override hoặc client được phép gọi.

**Câu 6.** Có nên dùng `default` để triển khai một thao tác cần trực tiếp thay đổi field `balance` mà chỉ vài implementation có?

**Đáp án:** Không nên nếu interface không có hợp đồng và khả năng chung để làm việc đó. Đặt hành vi trong class phù hợp, hoặc thiết kế interface hẹp hơn cho những class thực sự có khả năng ấy.

**Câu 7.** Interface Java và TypeScript có nhất thiết giống nhau về hành vi runtime không?

**Đáp án:** Không. Java interface có thể cung cấp default method chạy được; TypeScript interface chủ yếu phục vụ kiểm tra kiểu tại thời điểm biên dịch và không tự sinh implementation runtime tương ứng.

## Nguyên tắc áp dụng

Khi thiết kế hoặc đọc một Java interface, hãy xác định rõ **phương thức nào là nghĩa vụ phải hiện thực**, **phương thức nào đã có implementation chung**, **thành viên nào thuộc chính interface**, và **trạng thái nào phải thuộc về class triển khai**.

Dùng `default` cho hành vi chung thực sự có ý nghĩa; dùng `static` cho tiện ích gắn với hợp đồng; dùng `private` để chia sẻ logic nội bộ mà không mở rộng public API. Khi kết hợp nhiều interface, kiểm tra xung đột default method và quy tắc kế thừa. Quan trọng hơn, khi làm việc với ngôn ngữ hoặc phiên bản khác, hãy đối chiếu giới hạn thực tế của nó thay vì coi “interface” ở mọi nơi đều có cùng quy tắc với Java.