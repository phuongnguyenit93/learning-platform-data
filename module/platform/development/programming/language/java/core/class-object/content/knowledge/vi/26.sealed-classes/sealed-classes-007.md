# So sánh hệ phân cấp đóng với lớp tự do mở rộng trong Java

## 1. Bài toán thiết kế: ai được quyền tạo kiểu con mới?

Khi thiết kế một thư viện hoặc ứng dụng hướng đối tượng Java, ta thường phải chọn giữa hai chính sách:

- **Hệ phân cấp mở** (*open hierarchy*): những class khác có thể kế thừa/triển khai một type và cung cấp implementation mới, miễn tuân thủ các quy tắc thông thường của Java.
- **Hệ phân cấp đóng có kiểm soát** (*sealed hierarchy*): tác giả của một class/interface xác định **những direct subtypes nào được phép**. Các nhánh con có thể đóng tiếp, kết thúc bằng `final`, hoặc được chủ ý mở trở lại bằng `non-sealed`.

Ví dụ một giao thức trả kết quả chỉ có hai biến thể:

```java
sealed interface Result permits Success, Failure {}

record Success(String value) implements Result {}

record Failure(String message) implements Result {}
```

Đây là một đoạn khai báo hợp lệ của Java 17 nếu ba types trong cùng compilation unit; chưa có `main`. Vì `Result` là `sealed`, một class bất kỳ bên ngoài **không được tự ý** thêm direct implementation thứ ba.

Ngược lại:

```java
interface Result {}

record Success(String value) implements Result {}

record Failure(String message) implements Result {}
```

Ở phiên bản này, `Result` là interface thông thường: class khác có thể viết `implements Result` nếu type được truy cập và những ràng buộc Java bình thường cho phép.

**Câu hỏi trung tâm không phải “cú pháp nào ngắn hơn”, mà là:** Tập implementations có phải một phần **đóng và do chủ sở hữu type kiểm soát**, hay là một **điểm mở rộng** dành cho modules, plugins và người dùng thư viện?

Bài này so sánh hành vi Java 17+, mô hình quyền mở rộng, lỗi compiler, thiết kế API, khả năng nâng cấp phần mềm và các phương án phối hợp hai hướng. Các chương trình đầy đủ có tệp, lệnh `javac`/`java` và kết quả xác định; những đoạn sai được gắn nhãn minh họa lỗi.

## 2. Một hệ phân cấp mở trông thế nào?

Xét abstract class thông thường:

```java
abstract class Message {
    abstract String text();
}
```

Một subclass ở nơi khác có thể định nghĩa:

```java
final class Greeting extends Message {
    @Override
    String text() {
        return "hello";
    }
}
```

Đây là hai khai báo minh họa có thể thuộc một chương trình hợp lệ. `Message` không phải `sealed` hay `final`, nên Java không có **danh sách `permits` đóng** áp dụng cho các direct subclasses.

Cần phân biệt:

- **Mở về inheritance:** Type không cấm subclasses theo sealed/final rules.
- **Có thể truy cập từ nơi muốn kế thừa:** Access modifiers, package, module exports, constructor visibility vẫn quan trọng.
- **Có điểm mở rộng hữu dụng:** Để subclass thực tế, superclass phải có contract, methods và constructor phù hợp.
- **Không tự an toàn:** Bên thứ ba có thể implement khác dự kiến; tác giả API cần viết đúng hợp đồng và tránh giả định danh sách hữu hạn.

Một abstract class **không tự đóng** tập subclasses. Nó chỉ không thể được tạo instance trực tiếp, và có thể buộc các subclasses thực hiện abstract methods.

## 3. Chương trình chạy: hệ phân cấp mở cho phép thêm behavior

Tạo tệp **`OpenHierarchyDemo.java`**:

```java
abstract class Notification {
    abstract String send(String target);
}

final class EmailNotification extends Notification {
    @Override
    String send(String target) {
        return "email:" + target;
    }
}

final class SmsNotification extends Notification {
    @Override
    String send(String target) {
        return "sms:" + target;
    }
}

public class OpenHierarchyDemo {
    static void deliver(Notification notification) {
        System.out.println(notification.send("An"));
    }

    public static void main(String[] args) {
        deliver(new EmailNotification());
        deliver(new SmsNotification());
    }
}
```

```bash
javac OpenHierarchyDemo.java
java OpenHierarchyDemo
```

```text
email:An
sms:An
```

Method `deliver` chỉ biết abstract superclass `Notification`. Khi thêm implementation mới theo quy tắc thường, caller vẫn có thể truyền instance cho `deliver` nếu subclass đáp ứng contract.

**Lợi ích:** Polymorphism tạo extension point rõ, nhất là khi một hệ sinh thái có nhiều implementation do các tổ chức khác nhau phát triển.

**Chi phí:** Người thiết kế `Notification` không được phép giả định chỉ có EmailNotification và SmsNotification. Nếu method trong thư viện dùng `if (notification instanceof EmailNotification) ... else ...` thì future subclasses có nguy cơ không được xử lý.

## 4. Hệ phân cấp đóng bằng `sealed` hoạt động ra sao?

Với Java 17:

```java
sealed abstract class Notification
        permits EmailNotification, SmsNotification {
    abstract String send(String target);
}

final class EmailNotification extends Notification {
    @Override
    String send(String target) {
        return "email:" + target;
    }
}

final class SmsNotification extends Notification {
    @Override
    String send(String target) {
        return "sms:" + target;
    }
}
```

Đây là một khai báo minh họa độc lập, **không đặt đồng thời với ví dụ `Notification` mở** trong cùng scope.

Trong sealed version:

1. `Notification` vẫn là một abstract class, không khởi tạo trực tiếp.
2. Nó chỉ cho phép **direct subclasses đã được cấp phép**.
3. `EmailNotification` và `SmsNotification` là `final`, nên không thể subclass chúng tiếp.
4. Một direct subclass `PushNotification extends Notification` sẽ bị compiler từ chối nếu không được phép.
5. Polymorphic calls qua `Notification` vẫn hoạt động bình thường: `sealed` không vô hiệu dynamic dispatch.

**Đóng không có nghĩa “không dùng kế thừa”.** Sealed kiểm soát **những nhánh kế thừa trực tiếp** được phép.

## 5. Chương trình chạy: sealed và dynamic dispatch vẫn cùng tồn tại

Tạo **`SealedHierarchyDemo.java`**:

```java
sealed abstract class Notification
        permits EmailNotification, SmsNotification {
    abstract String send(String target);
}

final class EmailNotification extends Notification {
    @Override
    String send(String target) {
        return "email:" + target;
    }
}

final class SmsNotification extends Notification {
    @Override
    String send(String target) {
        return "sms:" + target;
    }
}

public class SealedHierarchyDemo {
    static void deliver(Notification notification) {
        System.out.println(notification.send("An"));
    }

    public static void main(String[] args) {
        deliver(new EmailNotification());
        deliver(new SmsNotification());
        System.out.println(Notification.class.isSealed());
    }
}
```

```bash
javac SealedHierarchyDemo.java
java SealedHierarchyDemo
```

```text
email:An
sms:An
true
```

So với bản mở, **mã sử dụng đa hình ở `deliver` không đổi**. Chỉ khác là compiler/runtime ràng buộc direct subclass set.

**Hệ quả thiết kế:** Có thể chọn sealed mà vẫn hưởng abstraction, override, method dispatch và constructor chaining của OOP. Sealed không biến toàn bộ class hierarchy thành `switch` hoặc enumeration.

## 6. Ba từ khóa cần đặt cạnh nhau: `final`, `sealed`, `non-sealed`

| Modifier | Cho phép direct subclasses mới? | Ý nghĩa thiết kế |
| --- | --- | --- |
| `final class` | Không | Chặn kế thừa hoàn toàn ở node đó |
| `sealed class/interface` | Chỉ các direct types được permit | Cho kế thừa có kiểm soát |
| `non-sealed class/interface` | Mở lại theo rules thông thường | Cố ý mở một nhánh bên dưới sealed parent |
| Class/interface thường | Có thể mở, tùy access và rules khác | Không khóa bằng danh sách permits |
| `abstract class` | Tùy sealed/final policy; abstract riêng không khóa | Không khởi tạo trực tiếp; có thể chứa abstract methods |

Một `non-sealed` declaration chỉ có ý nghĩa ở vị trí **direct subtype của sealed type**; không thể đặt `non-sealed` tùy ý lên mọi class thông thường.

**Không nhầm hai trục:** `abstract` nói về instantiation và abstract methods; `sealed` nói về quyền tạo **direct subtype**. Chẳng hạn `abstract sealed class` hợp lệ: vừa không tạo instance trực tiếp, vừa khóa danh sách con.

## 7. Cơ chế cấp phép chỉ xét các nhánh trực tiếp

Giả sử:

```java
sealed class Base permits Middle {}

non-sealed class Middle extends Base {}

final class Leaf extends Middle {}
```

Mã minh họa này hợp lệ trong cùng package phù hợp.

- `Middle` là **direct subclass** được permit bởi Base.
- `Leaf` là **indirect subclass** của Base.
- `Leaf` không cần xuất hiện trong `Base permits ...` vì nó không trực tiếp `extends Base`.
- Vì Middle là `non-sealed`, nó cho phép subclasses như Leaf theo quy tắc class thông thường.

Sealed **không đảm bảo danh sách tất cả descendants trên mọi cấp là hữu hạn** nếu tồn tại một nhánh `non-sealed`. Nó chỉ đảm bảo tập **direct permitted subtypes** được kiểm soát cho từng sealed node.

## 8. Chương trình chạy: một nhánh sealed, một nhánh non-sealed

Tạo **`SelectiveOpenHierarchyDemo.java`**:

```java
sealed abstract class Document
        permits OfficialDocument, CustomDocument {
    abstract String label();
}

final class OfficialDocument extends Document {
    @Override
    String label() {
        return "official";
    }
}

non-sealed class CustomDocument extends Document {
    @Override
    String label() {
        return "custom";
    }
}

final class UserDocument extends CustomDocument {
    @Override
    String label() {
        return "user";
    }
}

public class SelectiveOpenHierarchyDemo {
    public static void main(String[] args) {
        Document[] documents = {
                new OfficialDocument(),
                new CustomDocument(),
                new UserDocument()
        };

        for (Document document : documents) {
            System.out.println(document.label());
        }
    }
}
```

```bash
javac SelectiveOpenHierarchyDemo.java
java SelectiveOpenHierarchyDemo
```

```text
official
custom
user
```

`Document` chỉ permit OfficialDocument và CustomDocument trực tiếp. UserDocument được tạo qua nhánh CustomDocument `non-sealed`. Đây là mô hình **đóng ở lõi, mở có chọn lọc tại nhánh extension**.

**Điểm thiết kế:** Không cần chọn “mọi thứ đóng” hoặc “mọi thứ mở”. Java cho phép kết hợp hai chính sách ở các tầng phù hợp.

## 9. Một bảng quyền mở rộng theo tình huống

| Trường hợp | Lớp mở | Hệ sealed |
| --- | --- | --- |
| Developer khác viết direct subclass | Có thể, nếu Java access/rules cho phép | Chỉ khi child được permit |
| Plugin ngoài thư viện mở rộng qua inheritance | Thuận tiện hơn | Không ở sealed node, trừ nhánh non-sealed |
| Tác giả biết tất cả direct variants | Không được compiler bảo đảm chỉ có chúng | Có danh sách được kiểm soát |
| Thêm implementation ở module khác | Có thể nếu API/module cho phép | Không thể thành direct permitted child khi named-module co-location cấm |
| Dynamic polymorphism | Có | Có |
| Cấm kế thừa một nhánh cụ thể | Đặt final trên child | Đặt final trên permitted child |
| Cho phép mở rộng một nhánh cụ thể | Thường đã mở | Dùng non-sealed child |
| Đổi tập direct subtypes | Consumers bên ngoài có thể thêm không cần sửa parent | Chủ sở hữu hierarchy cập nhật permits/source |
| Static reasoning về direct hierarchy | Hạn chế | Tốt hơn khi tất cả branches đủ đóng |
| Rủi ro future subtype bất ngờ | Cao hơn | Giảm ở sealed nodes |
| Compatibility khi thay đổi parent | Phải giữ contract cho subclasses bên ngoài | Vẫn phải cân nhắc permitted clients và binary/serialization |

**Lưu ý:** “Open” không có nghĩa bất kỳ nơi nào cũng dễ extends. Một constructor private hoặc class package-private không accessible vẫn hạn chế code bên ngoài. Sealed mới là ràng buộc **type hierarchy** có ngữ nghĩa riêng.

## 10. Sealed interface thường phù hợp với tập biến thể dữ liệu

Khi nghiệp vụ có một số loại kết quả với hình thức dữ liệu khác nhau, sealed interface và records là cách diễn đạt mạnh.

Tạo **`ResultVariantsDemo.java`**:

```java
sealed interface Result
        permits Success, Failure, Pending {
    String describe();
}

record Success(String value) implements Result {
    @Override
    public String describe() {
        return "success:" + value;
    }
}

record Failure(int code) implements Result {
    @Override
    public String describe() {
        return "failure:" + code;
    }
}

record Pending() implements Result {
    @Override
    public String describe() {
        return "pending";
    }
}

public class ResultVariantsDemo {
    public static void main(String[] args) {
        Result[] results = {
                new Success("A"),
                new Failure(404),
                new Pending()
        };

        for (Result result : results) {
            System.out.println(result.describe());
        }
    }
}
```

```bash
javac ResultVariantsDemo.java
java ResultVariantsDemo
```

```text
success:A
failure:404
pending
```

Ba record classes là final theo đặc tính record, nên không mở rộng thêm ở mỗi variant. `Result` mô tả một **tập khả năng domain** có tên chính xác.

**Khi nào phù hợp:** protocol states, AST nodes, outcome types, messages có schema cố định theo phiên bản. Tuy nhiên, mô hình không tự cấm `null` làm giá trị reference, không tự validate fields, và không tự sinh logic xử lý tất cả variants.

## 11. Hệ interface mở phù hợp với extension point thực thụ

Nếu mục tiêu là cho các nhà phát triển khác thêm cách xử lý mới, một interface **không sealed** thường phù hợp.

Tạo **`OpenStrategyDemo.java`**:

```java
interface Compression {
    String name();
    String compress(String input);
}

final class NoCompression implements Compression {
    @Override
    public String name() {
        return "none";
    }

    @Override
    public String compress(String input) {
        return input;
    }
}

final class UppercaseDemoCompression implements Compression {
    @Override
    public String name() {
        return "uppercase";
    }

    @Override
    public String compress(String input) {
        return input.toUpperCase(java.util.Locale.ROOT);
    }
}

public class OpenStrategyDemo {
    static void run(Compression compression) {
        System.out.println(compression.name() + ":"
                + compression.compress("java"));
    }

    public static void main(String[] args) {
        run(new NoCompression());
        run(new UppercaseDemoCompression());
    }
}
```

```bash
javac OpenStrategyDemo.java
java OpenStrategyDemo
```

```text
none:java
uppercase:JAVA
```

Ở đây `UppercaseDemoCompression` chỉ là thuật toán minh họa, **không phải nén dữ liệu thật**. Mục đích là cho thấy framework có thể nhận implementation theo interface contract; thêm class mới không cần sửa danh sách `permits`.

Trong một plugin architecture, khả năng đăng ký implementation và cách tải plugin là việc riêng của registry, ServiceLoader hoặc dependency injection; interface mở chỉ cung cấp **khả năng triển khai type**.

## 12. Không chỉ phụ thuộc `sealed`: mức truy cập và constructor cũng giới hạn thực tế

Một class không sealed nhưng không public có thể chỉ accessible trong package. Một constructor private cũng có thể cấm caller subclass vì không thể gọi constructor hợp lệ.

Ví dụ:

```java
public abstract class ServiceBase {
    protected ServiceBase() {
    }

    public abstract void run();
}
```

Đây là một **tệp minh họa `ServiceBase.java`**, không có main. Một protected constructor giúp subclasses hợp lệ ở package khác có thể gọi `super()` theo Java rules.

Ngược lại, nếu tất cả constructors của superclass đều private và không có cơ chế Java phù hợp cho subclass, việc kế thừa từ code ngoài class có thể không thực hiện được, dù superclass không sealed.

**Phân biệt 3 lớp hạn chế:**

1. `public`/package-private/protected/private: **quyền truy cập**.
2. `final`/`sealed`/`non-sealed`: **chính sách kế thừa**.
3. Module exports/reads: **khả năng truy cập giữa modules**.

Không nên kết luận “class không ghi sealed thì chắc chắn mọi plugin ở nơi khác kế thừa được”.

## 13. Điều kiện module và package của `sealed`

Java 17 giới hạn vị trí của permitted direct subtypes:

- Nếu sealed type nằm trong **named module**, permitted direct subtypes phải nằm trong **cùng named module**.
- Nếu sealed type nằm trong **unnamed module**, permitted direct subtypes phải nằm trong **cùng package**.

Điều này khiến `sealed` thích hợp cho **closed family do cùng một module/namespace kiểm soát**. Nó thường **không** thích hợp làm direct extension point cho code trong named module của nhà cung cấp plugin khác.

### Minh họa thiết kế nhiều module

```text
module app.core
  app.core.model.Event
  app.core.model.Started
  app.core.model.Finished

module app.plugin
  app.plugin.CustomEvent
```

Đây là **sơ đồ kiến trúc**, không phải project Java hoàn chỉnh. Nếu Event là sealed interface trong `app.core`, type `CustomEvent` ở module `app.plugin` không thể trở thành direct permitted implementation của Event theo rule same named module. Điều đó không đổi chỉ vì app.plugin khai báo `requires app.core`.

Muốn plugins mở rộng ở module khác, dùng interface không sealed hoặc expose một permitted `non-sealed` branch theo thiết kế, cùng các ràng buộc truy cập thích hợp.

## 14. Khi không ghi `permits`: compiler chỉ suy ra trong cùng compilation unit

Một sealed type không nhất thiết phải liệt kê children tường minh nếu các direct subtypes có **canonical name** và được khai báo trong **cùng compilation unit**.

Tạo **`ImplicitPermitsDemo.java`**:

```java
sealed interface Action {
    String label();
}

record Start() implements Action {
    @Override
    public String label() {
        return "start";
    }
}

record Stop() implements Action {
    @Override
    public String label() {
        return "stop";
    }
}

public class ImplicitPermitsDemo {
    public static void main(String[] args) {
        Action a = new Start();
        Action b = new Stop();

        System.out.println(a.label());
        System.out.println(b.label());
    }
}
```

```bash
javac ImplicitPermitsDemo.java
java ImplicitPermitsDemo
```

```text
start
stop
```

Compiler suy ra Start/Stop vì chúng ở cùng source file, có canonical names và implement trực tiếp Action.

**Điều không đủ:** Cùng package hay module nhưng **khác source file** không khiến compiler tự tìm children nếu không có permits. Nếu muốn để implementations ở các tệp riêng, thông thường dùng `permits` tường minh.

## 15. Một sealed hierarchy hoàn toàn đóng và một nhánh mở

Hai ví dụ khái niệm:

```java
sealed interface CompletelyClosed
        permits A, B {}

record A() implements CompletelyClosed {}

record B() implements CompletelyClosed {}
```

Các children đều final (record), nên xét inheritance **không còn đường tạo subtype mới**.

```java
sealed interface SelectivelyOpen
        permits Standard, Extension {}

record Standard() implements SelectivelyOpen {}

non-sealed interface Extension extends SelectivelyOpen {}
```

Ở đây `Extension` mở cho những implementations khác đi vào hệ thông qua nhánh ấy. Bất kỳ implementation mới nào **trực tiếp extends Extension** không cần xuất hiện trong permits của SelectivelyOpen.

**Khi nói “đóng” phải chỉ rõ mức nào:** Đóng ở **direct permitted set** là mặc định của sealed; đóng **toàn bộ descendants** chỉ đúng khi mọi nhánh được đóng đến leaves và không có `non-sealed` branch.

## 16. Ví dụ chạy: giao diện đóng một nhánh và mở nhánh plugin

Tạo **`HybridExtensionDemo.java`**:

```java
sealed interface Rule
        permits BuiltinRule, PluginRule {
    String apply(String value);
}

record BuiltinRule() implements Rule {
    @Override
    public String apply(String value) {
        return "builtin:" + value;
    }
}

non-sealed interface PluginRule extends Rule {
}

final class ExternalRule implements PluginRule {
    @Override
    public String apply(String value) {
        return "plugin:" + value;
    }
}

public class HybridExtensionDemo {
    public static void main(String[] args) {
        Rule a = new BuiltinRule();
        Rule b = new ExternalRule();

        System.out.println(a.apply("A"));
        System.out.println(b.apply("A"));
    }
}
```

```bash
javac HybridExtensionDemo.java
java HybridExtensionDemo
```

```text
builtin:A
plugin:A
```

`Rule` chỉ permit BuiltinRule và PluginRule trực tiếp. `ExternalRule` implements PluginRule, không trực tiếp implements Rule, nên không vi phạm danh sách direct permitted types.

**Đây là một cấu trúc thực tế khi muốn phân biệt** những variants built-in đã đóng với một nhánh extension rõ ràng có interface riêng. Không bắt buộc dùng sealed cho mọi plugin system; nó đáng dùng khi chủ đích boundary này mang giá trị mô hình hóa.

## 17. Vì sao `final` khác `sealed`?

`final class` cấm subclasses hoàn toàn:

```java
final class ImmutableToken {
}
```

`sealed class` cho phép **một số** direct subclasses:

```java
sealed abstract class Token
        permits IdentifierToken, NumberToken {
}

final class IdentifierToken extends Token {
}

final class NumberToken extends Token {
}
```

Hai snippets là các khai báo minh họa.

| Câu hỏi | `final` | `sealed` |
| --- | --- | --- |
| Có direct subtype mới không? | Không | Có, nếu được permit |
| Có thể mô hình nhiều variants dưới một parent? | Không qua subclasses | Có |
| Cần `permits`? | Không | Tường minh hoặc suy ra |
| Có thể khai báo abstract? | Không đồng thời abstract và final trên class | Có thể abstract sealed |
| Phù hợp với value object riêng lẻ | Thường phù hợp | Chỉ khi có family variants |
| Phù hợp với AST/result variants | Một leaf có thể final | Sealed parent thường phù hợp |

Chọn `final` khi hoàn toàn không định mở subclass tại node đó. Chọn `sealed` khi cần **một hierarchy đóng có nhiều biến thể**.

## 18. Abstract không có nghĩa sealed

Ví dụ:

```java
abstract class OpenProcessor {
    abstract void process();
}
```

Tác giả có thể buộc subclasses implement `process` nhưng không giới hạn số subclasses. Còn:

```java
abstract sealed class ClosedProcessor
        permits BatchProcessor, LiveProcessor {
    abstract void process();
}

final class BatchProcessor extends ClosedProcessor {
    @Override
    void process() {
    }
}

final class LiveProcessor extends ClosedProcessor {
    @Override
    void process() {
    }
}
```

cũng có abstract contract nhưng **giới hạn direct subtypes**.

**Định nghĩa tách bạch:** Abstract là chính sách **đối tượng và implementation**; sealed là chính sách **kế thừa và tập subtype**. Hai khái niệm có thể kết hợp.

## 19. Nếu một direct child bị quên modifier, compiler báo lỗi

Trong một sealed hierarchy, direct permitted subclass phải khai báo chính sách kế thừa phù hợp.

**Mã cố tình sai:**

```java
sealed class Parent {
}

class Child extends Parent {
}
```

Dù Child nằm cùng compilation unit và được suy ra, nó không có `final`, `sealed` hay `non-sealed`. Compiler báo lỗi.

Bản sửa nếu Child là leaf:

```java
sealed class Parent {
}

final class Child extends Parent {
}
```

Bản sửa nếu muốn extension branch:

```java
sealed class Parent {
}

non-sealed class Child extends Parent {
}
```

Ba đoạn được hiểu là **ba phương án riêng**, không khai báo trùng `Parent` trong một source file. `non-sealed` chỉ được sử dụng đúng khi Child trực tiếp extends một sealed superclass hoặc implements một sealed interface theo quy tắc.

## 20. Hệ mở tăng khả năng mở rộng, nhưng giảm khả năng liệt kê toàn bộ

Một API open class/interface không thể giả định rằng đã biết toàn bộ implementations ở compile time.

Chẳng hạn:

```java
interface PaymentGateway {
    boolean charge(int amount);
}
```

Thư viện có thể tích hợp một gateway khác trong tương lai; callers thường phải phụ thuộc vào **contract `charge`**, không viết code dựa trên một list subclasses do tình cờ thấy ở repository hôm nay.

Ngược lại, với sealed interface:

```java
sealed interface PaymentEvent
        permits Authorized, Declined {}

record Authorized(String id) implements PaymentEvent {}

record Declined(String reason) implements PaymentEvent {}
```

tác giả chủ động định nghĩa **hai event variants**. Đây là mô hình của dữ liệu/sự kiện **đã biết trước theo phiên bản schema**, khác mục tiêu của API gateway dành cho nhà cung cấp.

**Đừng chọn sealed chỉ để “làm code nghiêm ngặt hơn”.** Nó có giá trị khi tập variants đóng là một sự thật của domain hoặc của contract kiến trúc.

## 21. Sealed không đồng nghĩa một “enum nhiều dữ liệu” trong mọi tình huống

`enum` cũng là cách mô tả một tập named constants đóng:

```java
enum Status {
    NEW, PAID, CANCELLED
}
```

Nhưng nếu mỗi variant có **payload shape khác nhau**:

```java
sealed interface PaymentResult
        permits PaymentSuccess, PaymentFailure {}

record PaymentSuccess(String receipt)
        implements PaymentResult {}

record PaymentFailure(int code, String reason)
        implements PaymentResult {}
```

sealed interface + records có thể diễn đạt tốt hơn vì từng variant mang **components khác nhau**.

| Yêu cầu | Enum | Sealed hierarchy |
| --- | --- | --- |
| Một tập named constant instances | Rất phù hợp | Có thể quá nhiều boilerplate |
| Mỗi biến thể có payload riêng | Có thể nhưng không tự nhiên với nhiều payload tùy request | Record/class variants tự nhiên |
| Tự sinh data accessors theo variant | Không | Record variant có |
| Tập type variants đóng | Có theo constant set | Có theo direct permitted set nếu các nhánh đều đóng |
| Có branch `non-sealed` | Không kiểu extension này | Có |
| Đa hình behavior | Có thể qua constant-specific bodies | Có qua classes/records/interfaces |

**Không bắt buộc sealed cho mọi state enum.** Chọn theo việc domain cần **các giá trị constant** hay **các loại object có payload riêng**.

## 22. Một interface mở nhưng không có quy tắc exhaustive variants

Ví dụ ứng dụng xử lý event theo method contract:

```java
interface Event {
    void dispatch();
}
```

Một open interface có thể có vô hạn implementations về mặt thiết kế. Do đó method:

```java
void inspect(Event event) {
    if (event instanceof AuditEvent) {
        // ...
    } else if (event instanceof UserEvent) {
        // ...
    }
}
```

là **mảnh code minh họa**, `AuditEvent` và `UserEvent` giả định được khai báo. Không có gì trong interface open bảo đảm chỉ có hai kiểu đó; nhánh else có thể bỏ sót future implementations.

**Hướng xử lý ở open hierarchy:** Ưu tiên gọi virtual method chung hoặc dùng visitor/registry/dispatch strategy có fallback rõ ràng. Nếu code business đòi thực sự **liệt kê tất cả variants**, có thể domain đã phù hợp sealed hơn.

## 23. Java 17: cẩn thận với pattern matching và `switch`

Sealed hierarchy giúp reasoning về finite variants. Tuy nhiên **cú pháp xử lý exhaustive** phụ thuộc phiên bản Java.

Ở **Java 17**:

- `instanceof` với type pattern là tính năng ổn định.
- Pattern matching for `switch` vẫn ở dạng preview của Java 17.
- Không nên đưa `case SomeRecord(...)` hoặc record pattern `switch` làm code Java 17 biên dịch thông thường.
- Java 21+ mới có pattern switch và record patterns ở dạng final; cần ghi rõ version riêng nếu sử dụng.

Tạo **`SealedInstanceofDemo.java`** chạy Java 17:

```java
sealed interface Event permits Started, Finished {
}

record Started(String id) implements Event {
}

record Finished(String id) implements Event {
}

public class SealedInstanceofDemo {
    static String describe(Event event) {
        if (event instanceof Started started) {
            return "start:" + started.id();
        }
        if (event instanceof Finished finished) {
            return "finish:" + finished.id();
        }
        throw new IllegalStateException("unexpected type");
    }

    public static void main(String[] args) {
        System.out.println(describe(new Started("A")));
        System.out.println(describe(new Finished("B")));
    }
}
```

```bash
javac SealedInstanceofDemo.java
java SealedInstanceofDemo
```

```text
start:A
finish:B
```

Đây là `instanceof` patterns, không phải pattern `switch`. Vì đã biết direct variants hiện tại, exception fallback có thể biểu thị vi phạm dự kiến, nhưng **compiler không tự chứng minh chuỗi `if` này exhaustive**. Nếu thêm variant, tác giả phải cập nhật/tests accordingly.

## 24. Lợi ích của sealed khi xử lý hệ phân cấp

Một sealed hierarchy được đóng qua các branches mang lại:

1. **Giới hạn đường kế thừa:** Types ngoài danh sách direct permits không thể mở nhánh bất ngờ.
2. **Rõ ownership:** Tác giả parent công bố những biến thể được phép.
3. **Dễ kiểm bất biến:** Có thể xem/đánh giá một tập direct implementations đã biết.
4. **Hỗ trợ phân tích exhaustiveness** trong các tính năng ngôn ngữ/phân tích tĩnh phù hợp, nhất là Java versions có pattern switch ổn định.
5. **Tổ chức domain tốt:** Khi business chỉ có một số variants, type system phản ánh điều đó.
6. **Phân nhánh có kiểm soát:** Child chọn final, sealed hoặc non-sealed.
7. **Dễ audit:** Thêm direct subtype phải sửa declaration/list hoặc source scope phù hợp.

**Nhưng compiler không tự chứng minh toàn bộ logic nghiệp vụ:** Nó xác nhận các ràng buộc type/subtype, không xác nhận mọi implementation trả data đúng, mọi transition hợp lệ, hay tất cả serialized inputs an toàn.

## 25. Chi phí của sealed: thay đổi bộ biến thể cần phối hợp

Giả sử một library công bố:

```java
public sealed interface Outcome
        permits Success, Failure {}
```

với các classes `Success` và `Failure` hợp lệ. Sau này library muốn thêm `Retry`. Việc này có thể kéo theo:

- Cập nhật `permits` (hoặc declarations cùng compilation unit nếu infer).
- Thêm một direct permitted implementation tuân thủ modifier.
- Xem lại `switch`/pattern handling trong các consumer Java versions phù hợp.
- Cập nhật tests, serializers, schemas và deserializers.
- Xác định legacy clients có gặp subtype mới không, nên xử lý thế nào.
- Xem xét binary/source compatibility và deployment order của libraries.

**Tránh tuyên bố “thêm một subtype luôn binary-compatible và hoàn toàn an toàn”.** Tính tương thích phụ thuộc APIs, cách build, linked artifacts, patterns, dữ liệu và contracts; cần test cụ thể theo deployment.

Sealed làm thay đổi danh sách variants thành **thay đổi có chủ đích của schema**, nên là lợi thế với mô hình đóng nhưng có thể là gánh nặng với ecosystem cần extension liên tục.

## 26. Chi phí của hệ mở: phải giữ hợp đồng lâu dài cho subclasses ngoài

Một superclass/interface mở thường xuất hiện trong các extension libraries. Khi công bố nó, người phát triển có thể:

- Override methods hợp lệ.
- Gọi accessible constructors.
- Dựa vào protected hooks.
- Bổ sung fields và behavior.
- Subclass các classes trung gian.

Do đó thay đổi như **finalize method**, **đóng constructors**, **đổi abstract contract**, hoặc **biến một class mở thành sealed/final** có thể phá source/binary compatibility của code đã mở rộng nó.

**Đổi open class thành sealed không chỉ là refactor nội bộ** nếu đã cho third parties subclass. Những subclasses không được permit sẽ không còn hợp lệ. Với API public, nên có migration strategy thay vì khóa hierarchy đột ngột.

## 27. Vì sao sealed không mặc nhiên an toàn về bảo mật?

Sealed kiểm soát **type inheritance**, không tự:

- Kiểm role/permissions của người dùng.
- Xác thực input từ mạng.
- Mã hóa data.
- Bảo đảm thread safety.
- Chặn reflection đối với mọi dữ liệu.
- Cấm logic sai bên trong permitted subclasses.
- Bảo vệ services khỏi injection/serialization issues.
- Bảo đảm một list of variants tương ứng với mọi state nghiệp vụ.

Ví dụ `Success(String token)` là record hợp lệ trong sealed hierarchy vẫn có thể chứa `null` hoặc lộ token qua `toString()` nếu không có validation/display policy.

**Đừng dùng `sealed` như nhãn “secure”.** Nó là công cụ biểu đạt **ownership và đóng/mở của direct subtype set**.

## 28. Vì sao `non-sealed` cần được dùng có chủ đích?

Nếu một sealed parent permit `CustomExtension` mà CustomExtension là `non-sealed`, các lớp khác có thể mở rộng tiếp qua nhánh ấy theo rules Java thường.

Điều này giúp:

- Giữ variants chuẩn nằm dưới sự kiểm soát.
- Cung cấp plugin extension interface riêng.
- Phân biệt các nhánh nội bộ ổn định và nhánh do third parties làm chủ.
- Tránh việc phải sửa parent permits cho mọi plugin mới.

Nhưng nó cũng có nghĩa những đoạn logic dựa vào **“đã biết mọi instance types”** ở root sẽ không chắc chắn nữa. Các consumers nên xử lý một dạng generic `CustomExtension` theo interface contract, thay vì giả định mọi descendant đều có tên được công bố.

## 29. Khi nào nên chọn sealed? Các dấu hiệu mạnh

Sealed thường hợp khi:

- Miền giá trị có **một số dạng dữ liệu/behavior đã biết trước**.
- Tác giả thư viện **sở hữu toàn bộ direct variants** và muốn chặn implementer bên ngoài.
- Muốn phân tách payloads bằng records/classes thay vì enum constant không đủ biểu đạt.
- Tập biến thể cần được review/kiểm thử đầy đủ.
- Changes of variants xảy ra theo **release/schema migration**, không phải plugin runtime.
- Cần thiết kế **sum-type-like** bằng sealed interface/abstract class và các variant classes.
- Tác giả sẵn sàng quản lý API compatibility khi thêm/xóa direct type.

Ví dụ: cú pháp AST cho compiler, kết quả parser, các loại event từ domain bounded context, một bộ request/response variants cố định, workflow state types có payload khác nhau.

**Cẩn thận:** Một bộ “hiện giờ chỉ có ba implementation” chưa chứng minh nó phải sealed. Hãy hỏi liệu business **cho phép** người ngoài bổ sung implementation thứ tư trong tương lai không.

## 30. Khi nào chọn hierarchy mở? Các dấu hiệu mạnh

Hệ mở thường phù hợp khi:

- Framework/library cung cấp **extension point** cho ứng dụng khác.
- Plugin authors được thêm implementation mà không sửa code core.
- Behavior variations được xác định bởi configuration/modules/dependency injection.
- Không thể biết hết các implementations tại thời điểm compile.
- Các implementations có thể được cung cấp bởi thư viện khác/module khác.
- Contract ổn định dựa trên methods/semantics, không trên danh sách concrete types.
- API cố ý tuân theo Open/Closed Principle theo nghĩa mở cho extension nhưng tránh sửa consumer.

Ví dụ: `Comparator<T>`, `Runnable`, một `StorageProvider`, `AuthenticationStrategy`, `MessageTransport` dành cho plugins.

**Mở không có nghĩa mọi thứ thành public API.** Thiết kế một interface nhỏ, rõ contract, và hạn chế bằng access/module/lifecycle khi phù hợp.

## 31. Thay vì mở trực tiếp toàn bộ, có thể dùng composition

Không phải mọi variation đều cần subclass. Một class final có thể nhận một strategy interface mở:

```java
interface PricingRule {
    int calculate(int amount);
}

final class Checkout {
    private final PricingRule rule;

    Checkout(PricingRule rule) {
        this.rule = java.util.Objects.requireNonNull(rule);
    }

    int total(int amount) {
        return rule.calculate(amount);
    }
}
```

Đây là **khai báo hợp lệ minh họa**, chưa có main.

`Checkout` là final, không cho subclass; nhưng behavior `PricingRule` có thể thay qua composition. Điều này giải quyết nhu cầu extension mà không cần để khách hàng kế thừa trực tiếp một class mang invariants nhạy cảm.

**Tư duy thiết kế:** Đôi khi bạn muốn **đóng hierarchy của model**, nhưng **mở behavior injection** bằng interfaces. Không bắt buộc mở toàn bộ inheritance của aggregate/entity.

## 32. Ví dụ chạy: final core, open strategy

Tạo **`CompositionInsteadOfInheritanceDemo.java`**:

```java
import java.util.Objects;

interface Discount {
    int apply(int total);
}

final class Basket {
    private final Discount discount;

    Basket(Discount discount) {
        this.discount = Objects.requireNonNull(discount);
    }

    int payable(int total) {
        return discount.apply(total);
    }
}

final class NoDiscount implements Discount {
    @Override
    public int apply(int total) {
        return total;
    }
}

final class FixedDiscount implements Discount {
    @Override
    public int apply(int total) {
        return Math.max(0, total - 10);
    }
}

public class CompositionInsteadOfInheritanceDemo {
    public static void main(String[] args) {
        Basket normal = new Basket(new NoDiscount());
        Basket special = new Basket(new FixedDiscount());

        System.out.println(normal.payable(40));
        System.out.println(special.payable(40));
    }
}
```

```bash
javac CompositionInsteadOfInheritanceDemo.java
java CompositionInsteadOfInheritanceDemo
```

```text
40
30
```

`Basket` không có subclasses, nhưng có thể đổi logic qua `Discount`. Đây là minh họa cụ thể rằng “muốn extension” **không đồng nghĩa phải làm mọi class không final**.

Nếu pricing rules chỉ có vài lựa chọn đóng theo domain, `Discount` có thể sealed; nếu plugins được thêm tùy ý, giữ nó open. Chọn theo đúng boundary.

## 33. Không nhầm “đóng biến thể” với “bất biến dữ liệu”

Một class con final hoặc record final không mặc nhiên khiến mọi object state bất biến:

```java
sealed interface Container
        permits MutableContainer {}

final class MutableContainer implements Container {
    private int count;

    void increment() {
        count++;
    }

    int count() {
        return count;
    }
}
```

Đây là khai báo hợp lệ trong cùng compilation unit. Hierarchy **đóng**, nhưng instances của MutableContainer có **state mutable**.

Sealed/final kiểm **subtyping**, không kiểm **mutability**. Nếu cần thread safety, dùng immutable state, synchronization hoặc các concurrency primitives theo logic riêng.

## 34. Sealed interface cũng có thể được implement bởi một enum

Một enum là một class final hoặc implicitly sealed trong một số trường hợp constant-specific bodies; nó có thể implement sealed interface với đúng permission tương ứng.

Tạo **`SealedInterfaceEnumDemo.java`**:

```java
sealed interface ColorSignal permits Signal {
    String label();
}

enum Signal implements ColorSignal {
    RED, GREEN;

    @Override
    public String label() {
        return name().toLowerCase(java.util.Locale.ROOT);
    }
}

public class SealedInterfaceEnumDemo {
    public static void main(String[] args) {
        ColorSignal a = Signal.RED;
        ColorSignal b = Signal.GREEN;

        System.out.println(a.label());
        System.out.println(b.label());
    }
}
```

```bash
javac SealedInterfaceEnumDemo.java
java SealedInterfaceEnumDemo
```

```text
red
green
```

`Signal` là direct permitted implementation type của ColorSignal, còn RED/GREEN là constants thuộc Signal. `permits` liệt kê **types**, không liệt kê enum constant values.

**Không khai báo `non-sealed enum`**: Enum types có các quy tắc riêng về inheritance/finality. Chúng có thể implement interface, nhưng không mở cho user subclasses như class thường.

## 35. Điều gì xảy ra nếu bên ngoài cố tạo direct subtype không được permit?

Mã **cố tình sai**, không phải ví dụ runnable:

```java
sealed interface Result permits Success {}

record Success(String value) implements Result {}

final class UnknownResult implements Result {}
```

`UnknownResult` không được liệt kê trong `permits` nên bị compiler từ chối. Cùng source file không giải cứu được khi parent đã có **explicit permits**.

**Muốn cho phép thêm variant:** Chủ sở hữu của Result cập nhật `permits Success, UnknownResult` và bảo đảm UnknownResult hợp lệ, hoặc bỏ permits nếu all direct children có canonical names trong cùng compilation unit.

**Muốn third party tùy ý thêm:** Có thể chọn interface open hoặc permitted non-sealed branch. Không sửa type system bằng cast/reflection để “lách” sealed contract.

## 36. Một direct subtype có thể sealed tiếp và tự quản lý tập con

Tạo **`MultiLevelSealedHierarchyDemo.java`**:

```java
sealed abstract class Expression permits NumberExpr, OperationExpr {
    abstract int eval();
}

final class NumberExpr extends Expression {
    private final int number;

    NumberExpr(int number) {
        this.number = number;
    }

    @Override
    int eval() {
        return number;
    }
}

sealed abstract class OperationExpr
        extends Expression permits SumExpr {
}

final class SumExpr extends OperationExpr {
    private final Expression left;
    private final Expression right;

    SumExpr(Expression left, Expression right) {
        this.left = left;
        this.right = right;
    }

    @Override
    int eval() {
        return left.eval() + right.eval();
    }
}

public class MultiLevelSealedHierarchyDemo {
    public static void main(String[] args) {
        Expression value = new SumExpr(
                new NumberExpr(2), new NumberExpr(5));

        System.out.println(value.eval());
    }
}
```

```bash
javac MultiLevelSealedHierarchyDemo.java
java MultiLevelSealedHierarchyDemo
```

```text
7
```

- Expression permits NumberExpr và OperationExpr **trực tiếp**.
- OperationExpr permits SumExpr **trực tiếp**.
- SumExpr là descendant của Expression **gián tiếp**, không cần trong Expression's permits.
- NumberExpr và SumExpr final, nên những nhánh ấy kết thúc.

**Hệ quả:** Có thể tạo cây phân cấp nhiều tầng đóng đầy đủ để diễn đạt một domain AST, nhưng mỗi cấp sealed phải có permits hợp lệ và mỗi direct child phải công bố final/sealed/non-sealed policy phù hợp.

## 37. Runtime có thể nhận biết một type sealed

Java 17 cung cấp reflection:

- `Class.isSealed()`: type có sealed hay không.
- `Class.getPermittedSubclasses()`: mảng các **permitted direct classes/interfaces** đối với sealed type; trả null cho type không sealed.

Tạo **`SealedReflectionComparisonDemo.java`**:

```java
import java.util.Arrays;

sealed interface ClosedMessage permits Letter, Notice {
}

record Letter(String text) implements ClosedMessage {
}

record Notice(int code) implements ClosedMessage {
}

interface OpenMessage {
}

public class SealedReflectionComparisonDemo {
    static String[] names(Class<?> type) {
        Class<?>[] permitted = type.getPermittedSubclasses();
        if (permitted == null) {
            return new String[0];
        }

        String[] result = Arrays.stream(permitted)
                .map(Class::getSimpleName)
                .sorted()
                .toArray(String[]::new);
        return result;
    }

    public static void main(String[] args) {
        System.out.println(ClosedMessage.class.isSealed());
        System.out.println(OpenMessage.class.isSealed());

        System.out.println(Arrays.toString(
                names(ClosedMessage.class)));
        System.out.println(Arrays.toString(
                names(OpenMessage.class)));
    }
}
```

```bash
javac SealedReflectionComparisonDemo.java
java SealedReflectionComparisonDemo
```

```text
true
false
[Letter, Notice]
[]
```

Output được sắp xếp để không dựa vào thứ tự reflection. `OpenMessage` không sealed, nên helper chuyển null thành mảng rỗng. **Mảng rỗng ở đây không chứng minh open interface không có implementations**; chỉ nói nó không có sealed permits metadata.

Không dùng `Class.getPermittedSubclasses()` như một “registry mọi subtype đã được load” của interface mở. Nó không phải công cụ đó.

## 38. Những phương án bổ sung: enum, sealed, open interface, final + strategy

| Vấn đề domain | Lựa chọn nên cân nhắc | Lý do |
| --- | --- | --- |
| Ba tên trạng thái không có payload riêng | `enum Status` | Tập constant values đóng, gọn |
| Nhiều kết quả có payload khác nhau, tập đóng | Sealed interface + records | Variants có cấu trúc dữ liệu khác |
| Một số behavior strategies được cài từ plugins | Open interface | Tập implementation mở |
| Một lớp domain có invariants, không muốn subclass | Final class | Khóa inheritance của core |
| Muốn hành vi thay được trên final class | Composition + open interface | Mở behavior, không mở entity |
| Có variants chuẩn, thêm nhánh custom | Sealed root + non-sealed branch | Giữ lõi đóng, nhánh extension rõ |
| Hệ thống cần test exhaustiveness của direct variants | Sealed fully-closed hierarchy | Type constraints phản ánh tập |
| User cấu hình trực tiếp tên loại trong DB | Entity/registry/config | Tập thay đổi runtime, không compile-time |
| Base class cần các protected hook cho app tùy biến | Open abstract class | Inheritance là extension contract |
| Base type không được mở rộng vì security/invariant | Final hoặc sealed, tùy cần children | Chặn những subclasses không cho phép |

Không chọn chỉ dựa vào “ít dòng nhất”. Mức đóng/mở là quyết định về **quyền mở rộng và chi phí bảo trì**.

## 39. Một lưu ý về Open/Closed Principle

Trong SOLID, “open for extension, closed for modification” thường được nhắc đến. Nhưng không có nghĩa **mọi class phải non-final hoặc mọi interface phải không sealed**.

Hai khái niệm khác nhau:

- **Open/Closed Principle**: định hướng tổ chức mã để thêm behavior mà không sửa các phần đã ổn định, khi phù hợp.
- **Java `sealed`**: một cơ chế ngôn ngữ quản lý danh sách direct subtypes được phép.

Một ứng dụng có thể **đóng domain hierarchy** để bảo vệ invariant và đồng thời **mở extension qua composition/services**. Ngược lại, một interface open nhưng consumers liên tục `instanceof` từng implementation vẫn có thể vi phạm tinh thần extension design.

**Câu hỏi thực tế:** Extension nên xảy ra **ở type hierarchy**, **qua một injected behavior object**, hay **qua data/config**? Sealed chỉ là một trong những công cụ trả lời.

## 40. Những trường hợp không nên vội biến class mở thành sealed

- Library đã công bố superclass được hàng trăm packages khác subclass.
- Bạn không kiểm soát hoặc không thể liệt kê direct client subclasses.
- Plugins ở các named modules khác nhau phải trực tiếp implement interface.
- Mỗi tenant có implementation riêng trong runtime.
- Tests hiện dùng subclass test doubles của parent; sau khi seal có thể cần chuyển sang mock interface/composition/điểm mở rộng permitted.
- Parent không đại diện tập variants đóng mà chỉ là behavior contract.

**Trước migration**, phân loại usages: internal subclasses, external subclasses, mocks, generated proxies, runtime code generators và serialization frameworks. Sealing thay đổi khả năng tạo subclasses, nên có thể ảnh hưởng cả tooling.

## 41. Những trường hợp không nên vội bỏ sealed

- Có protocol enum-like variants cần rõ giới hạn.
- Có AST families cần kiểm toán.
- Các record variants có tính chất đóng theo schema version.
- Phát hiện subtype ngoài ý muốn có thể làm nghiệp vụ bị xử lý sai hoặc phá assumptions.
- Toàn bộ types thuộc cùng nhóm/ module và tác giả quản lý.
- Muốn compiler nhắc xử lý subtype mới ở những nơi có exhaustive constructs phù hợp phiên bản Java.

Bỏ sealed để xử lý một edge case có thể làm mất **thông tin domain quan trọng**. Có thể giải quyết bằng một `non-sealed` branch đã được cân nhắc hoặc bằng strategy composition bên ngoài mà vẫn giữ root đóng.

## 42. Kế hoạch thiết kế cho một API mới

Khi tạo API có nhiều implementations, tự trả lời lần lượt:

1. **Type này là một contract mở hay một tổng các variants đóng?**
2. Có những implementations được **app/third parties thêm sau deployment** không?
3. Ai là **owner** của inheritance hierarchy?
4. Các implementations nằm cùng named module/package không?
5. Có cần dữ liệu/fields khác nhau ở từng variant không?
6. Có cần đóng inheritance ở leaf bằng `final`?
7. Có branch nào cần mở lại bằng `non-sealed` không?
8. Nếu thêm subtype mới, những consumers nào cần cập nhật?
9. Data serialization/API compatibility có chịu thay đổi không?
10. Có thể tách behavior extension ra một interface chiến lược và giữ domain class final không?
11. Tests có bảo vệ expected direct subtype set không?
12. Target Java version có hỗ trợ patterns/switch mà bạn định dùng không?

Sau đó mới chọn `sealed`/`non-sealed`/`final`/ordinary interface/class. Việc định nghĩa contract rõ sẽ giảm nguy cơ refactor gây breaking changes sau này.

## 43. Test một hệ phân cấp đóng

Tạo **`SealedHierarchySelfTest.java`**:

```java
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

sealed interface Response permits Accepted, Rejected {
}

record Accepted(int id) implements Response {
}

record Rejected(String message) implements Response {
}

public class SealedHierarchySelfTest {
    static void check(boolean passed, String label) {
        if (!passed) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        check(Response.class.isSealed(), "root sealed");
        check(!Accepted.class.isSealed(), "record leaf");

        Class<?>[] permitted =
                Response.class.getPermittedSubclasses();

        check(permitted.length == 2, "two direct variants");

        Set<String> names = Arrays.stream(permitted)
                .map(Class::getSimpleName)
                .collect(Collectors.toSet());

        check(names.equals(Set.of("Accepted", "Rejected")),
                "permitted types");

        Response result = new Accepted(7);
        check(result instanceof Accepted, "runtime variant");

        System.out.println("sealed hierarchy PASS");
    }
}
```

```bash
javac SealedHierarchySelfTest.java
java SealedHierarchySelfTest
```

```text
sealed hierarchy PASS
```

Self-test kiểm trực tiếp runtime reflection type set và một lần polymorphic assignment. Nó không phụ thuộc thứ tự reflection. `check` ném AssertionError chủ động; không cần bật `-ea`.

**Giới hạn:** Test không chứng minh logic business của Accepted/Rejected đúng trong mọi trường hợp; các constructors, payload invariants và consumers vẫn cần tests riêng.

## 44. Test một extension point mở

Một open interface không có reflection metadata liệt kê tất cả implementations. Test đúng là **contract tests** chạy trên các implementations đã đăng ký/được cung cấp.

Tạo **`OpenContractSelfTest.java`**:

```java
interface Formatter {
    String format(String input);
}

final class PlainFormatter implements Formatter {
    @Override
    public String format(String input) {
        return input;
    }
}

final class BracketFormatter implements Formatter {
    @Override
    public String format(String input) {
        return "[" + input + "]";
    }
}

public class OpenContractSelfTest {
    static void check(boolean passed, String label) {
        if (!passed) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Formatter[] examples = {
                new PlainFormatter(),
                new BracketFormatter()
        };

        for (Formatter formatter : examples) {
            String output = formatter.format("A");
            check(output != null, "non-null output");
            check(output.contains("A"), "preserves input");
        }

        System.out.println("open contract PASS");
    }
}
```

```bash
javac OpenContractSelfTest.java
java OpenContractSelfTest
```

```text
open contract PASS
```

Hai formatters là những implementations hiện được test, **không phải bằng chứng rằng chỉ có hai implementations hợp lệ**. Ở hệ mở, cần công bố invariant/contract cho mọi extension mới và cung cấp bộ conformance tests khi cần.

## 45. Bài tập dự đoán: hệ nào đóng hoàn toàn?

Xét:

```java
sealed interface Node permits Leaf, Branch {}

record Leaf(String value) implements Node {}

sealed interface Branch extends Node permits BranchEnd {}

record BranchEnd(int number) implements Branch {}
```

Đây là khai báo minh họa hợp lệ trong cùng compilation unit.

**Câu hỏi:** Có thể tự thêm một class `NewLeaf implements Node` từ tệp khác mà không đổi Node không? Có thể tự thêm `NewBranchEnd implements Branch` không?

**Đáp án:** Không. Node và Branch đều sealed và các direct permitted sets của chúng đã xác định. `Leaf` và `BranchEnd` là records final. Toàn bộ inheritance hierarchy ở ví dụ **đóng qua các nhánh**.

Nếu muốn mở riêng Branch, cần một direct permitted subtype non-sealed của Branch hoặc đổi thiết kế. Không thể “đi tắt” với cast hoặc annotation.

## 46. Bài tập dự đoán: điều gì mở lại?

Xét:

```java
sealed interface Process permits Internal, External {}

record Internal(String id) implements Process {}

non-sealed interface External extends Process {}

final class VendorProcess implements External {}
```

**Hỏi:** Tập direct permitted types của Process? Có thể bổ sung một `OtherVendor implements External` không?

**Đáp án:** Direct permitted types là Internal và External. Có thể bổ sung implementations của `External` nếu thỏa normal Java access/module rules, vì External là `non-sealed`. Đây là hệ có root sealed nhưng **một nhánh mở**; không được diễn giải rằng chỉ Internal và VendorProcess là mọi subtype cuối cùng.

## 47. Bài tập lựa chọn mô hình

| Yêu cầu | Lựa chọn tham khảo | Giải thích |
| --- | --- | --- |
| Loại kết quả parse: Ok(payload), Error(message) | Sealed interface + records | Bộ biến thể có payload đóng |
| Trình chỉnh sửa cần plugins render mới | Open interface | Third-party implementations |
| Data class không được subclass | Final class/record | Đóng inheritance một node |
| AST operator variants cố định trong compiler | Sealed hierarchy | Chủ sở hữu kiểm soát variants |
| Nhiều công cụ thanh toán tùy provider | Open PaymentProvider interface | Bộ providers có thể mở rộng |
| Built-in parsers đóng, extension parser do bên ngoài | Sealed root + non-sealed extension branch | Phân tách quyền mở rộng |
| Một boolean isActive | Boolean | Không cần hierarchy |
| Ba mức LOW/MEDIUM/HIGH | Enum | Tập named constant values |
| Domain object bất biến nhưng cách validate thay đổi | Final domain class + Strategy | Đóng entity inheritance, mở behavior |
| Người dùng tạo tên trạng thái động trên admin UI | Data-driven model | Không phải compile-time type family đóng |

**Bài tập tư duy:** Chọn mô hình cho dự án của bạn và giải thích bằng **quyền tạo subtype** và **vòng đời thay đổi tập variants**, chứ không chỉ nói “sealed nhìn chuyên nghiệp”.

## 48. Sai lầm phổ biến

| Hiểu sai | Sự thật cần nhớ |
| --- | --- |
| “Sealed nghĩa là không subclass được” | Có thể subclass trực tiếp nếu được permit |
| “Sealed nghĩa là không có polymorphism” | Dynamic dispatch vẫn hoạt động |
| “Abstract tự khóa hierarchy” | Abstract không tự giới hạn subclasses |
| “Final và sealed giống nhau” | Final cấm con; sealed cho một danh sách trực tiếp |
| “Một non-sealed child khiến root không sealed” | Root vẫn sealed, chỉ nhánh child mở |
| “Permits liệt kê mọi hậu duệ” | Chỉ direct permitted subtypes |
| “Sealed luôn có toàn bộ descendants hữu hạn” | Non-sealed branch có thể mở vô hạn |
| “Mọi implementation phải nằm cùng source file” | Khi explicit permits, có thể khác file nhưng phải thỏa package/module rules |
| “Cùng file là đủ nếu xóa permits” | Cần direct relation và canonical names |
| “Interface mở nghĩa ai cũng triển khai được” | Access, modules và normal Java rules vẫn áp dụng |
| “Sealed đảm bảo thread safety/immutability” | Không liên quan trực tiếp |
| “Record luôn sealed” | Record là final class, có thể implement sealed interface |
| “Mỗi enum constant nằm trong permits” | Permits liệt kê types, không phải object constants |
| “Java 17 hỗ trợ pattern switch final” | Java 17 pattern switch vẫn preview |
| “Thêm variant không ảnh hưởng clients” | Cần xét consumers, serialization, source/binary compatibility |
| “Lớp open luôn tốt hơn vì extensible” | Extensibility cũng có chi phí và nguy cơ phá invariant |
| “Mọi class nên sealed để an toàn” | Domain và extension contract mới quyết định |
| “Có non-sealed là plugin tự được đăng ký” | Vẫn cần registry/loading/lifecycle |
| “getPermittedSubclasses liệt kê cả subclasses của open interface” | API reflection này dành cho sealed permits, không là registry |
| “Sealed interface có thể implements một class” | Interface extends interface; classes implements interfaces |
| “Chỉ cần compile ví dụ là chứng minh business logic đúng” | Cần tests/invariants ngoài type constraints |

## 49. Checklist code review

- [ ] Type đại diện tập variants **đóng** hay extension contract **mở**?
- [ ] Ai được phép thêm direct subtype và khi nào?
- [ ] Nếu sealed, đã xác định đúng danh sách permitted direct types?
- [ ] Tất cả direct permitted classes có final/sealed/non-sealed policy phù hợp?
- [ ] Direct permitted interfaces có sealed/non-sealed policy phù hợp?
- [ ] Các con gián tiếp không bị nhầm với direct permits?
- [ ] Có nhánh non-sealed khiến family mở lại không?
- [ ] Module/package location có hợp lệ?
- [ ] Nếu bỏ permits, tất cả direct children cần suy ra có canonical names trong same compilation unit?
- [ ] Nếu mở public API, access/constructor/module exports có cho phép inheritance đúng chủ đích?
- [ ] Có cần abstract methods hoặc default methods để xác định behavior contract?
- [ ] Nếu hierarchy mở, consumers có tránh giả định chỉ biết vài implementations?
- [ ] Nếu hierarchy đóng, thay đổi variant có review consumers/tests/serialization?
- [ ] Có dùng record variants khi payload shapes khác nhau?
- [ ] Có nên dùng enum thay vì một hierarchy quá phức tạp?
- [ ] Có thể tách behavior extension sang composition/strategy?
- [ ] Không hiểu sealed là thread safety, immutability hay security?
- [ ] Với Java 17, không dùng pattern `switch` preview mà thiếu cờ?
- [ ] Reflection test có chỉ kiểm **direct** permitted types?
- [ ] Không dựa thứ tự `getPermittedSubclasses()` nếu test không cần?
- [ ] Code samples có tên tệp/public class, lệnh `javac`/`java` và stdout hợp lệ?

## 50. Câu hỏi ôn tập có đáp án

**1.** Open hierarchy là gì?

*Là hệ class/interface cho phép thêm subclasses/implementations theo normal Java access/inheritance rules, không có danh sách sealed permits đóng.*

**2.** Sealed kiểm soát trực tiếp điều gì?

*Danh sách các direct subclasses hoặc direct subinterfaces được phép.*

**3.** Sealed có cấm virtual method dispatch không?

*Không.*

**4.** `final class` khác `sealed class` thế nào?

*Final không cho subclass; sealed cho một số direct subclasses được cấp phép.*

**5.** `abstract class` có tự đóng subclasses không?

*Không.*

**6.** `non-sealed` dùng ở đâu?

*Dùng cho direct subtype hợp lệ của sealed type để mở lại nhánh kế thừa.*

**7.** Nếu child non-sealed, root còn sealed không?

*Có. Root vẫn giới hạn direct children của chính nó.*

**8.** Một indirect grandchild có cần trong root permits không?

*Không; permits chỉ cho direct types.*

**9.** Khi nào bỏ được permits?

*Khi direct subtypes hợp lệ có canonical names trong cùng compilation unit để compiler suy ra.*

**10.** Cùng package nhưng khác file có tự được suy ra không?

*Không.*

**11.** Hai module khác nhau có thể chia sẻ direct permitted subtype khi parent trong named module không?

*Không; direct permitted subtypes phải nằm trong cùng named module.*

**12.** Một record có thể implements sealed interface không?

*Có, nếu nó là permitted direct implementation; record tự là final.*

**13.** Một enum có thể implements sealed interface không?

*Có, nếu permitted theo rules; enum constants không phải những names liệt kê trong permits.*

**14.** Sealed làm toàn bộ fields immutable không?

*Không.*

**15.** Hệ mở phù hợp tình huống nào?

*Plugin/strategy extension contracts nơi bên thứ ba được thêm implementations.*

**16.** Sealed phù hợp tình huống nào?

*Tập variants do owner xác định và được thay đổi qua release/schema có kiểm soát.*

**17.** Có thể kết hợp lõi đóng với plugin mở không?

*Có, ví dụ sealed root permits một non-sealed extension interface.*

**18.** Vì sao có thể chọn final class với injected interface?

*Để bảo vệ invariants của class, nhưng vẫn cho thay đổi behavior qua composition.*

**19.** `Class.getPermittedSubclasses()` trả loại nào?

*Direct permitted types của sealed class/interface, không phải mọi descendant hoặc mọi loaded plugin.*

**20.** Java 17 có pattern switch final chưa?

*Chưa; đó là preview, dùng Java 17 ổn định nên ưu tiên instanceof type patterns và polymorphism.*

**21.** Chuyển class public open thành sealed có thể gây gì?

*Phá contract của client subclasses chưa được permit; cần migration/compatibility review.*

**22.** Thêm variant mới vào sealed hierarchy có thể gây gì?

*Consumers/tests/serializers cần cập nhật, nhất là exhaustive logic.*

**23.** Nếu chỉ có vài constant values không payload, nên xem xét gì?

*Enum có thể ngắn và đúng domain hơn sealed hierarchy.*

**24.** Nếu mỗi variant có payload khác nhau, xem xét gì?

*Sealed interface + records/classes thường biểu đạt rõ.*

**25.** Vì sao không dùng sealed như công cụ bảo mật tổng quát?

*Vì nó giới hạn type inheritance, không tự xử lý validation, permissions, synchronization hoặc secrets.*

---

**Ghi nhớ cuối bài:** **Hệ phân cấp mở** cho phép thêm implementation theo hợp đồng kế thừa/triển khai thông thường; nó phù hợp framework và plugin extension nhưng đòi API vững trước những subclasses chưa biết. **Hệ phân cấp `sealed`** cho phép tác giả kiểm soát **direct permitted types**, giúp mô hình một tập biến thể domain đóng, rõ ràng và dễ review. Những direct children phải chọn `final` (đóng nhánh), `sealed` (đóng tiếp) hoặc `non-sealed` (mở lại nhánh) theo rules Java. Sealed **không bỏ đa hình**, **không tự bảo đảm mọi descendant đều hữu hạn** nếu có non-sealed branch, và **không thay thế validation, immutability hay security**. Chọn theo **ai sở hữu quyền tạo subtype và tập variants thay đổi qua quy trình nào**; cân nhắc enum, composition và strategy khi inheritance không phải điểm mở rộng thích hợp.