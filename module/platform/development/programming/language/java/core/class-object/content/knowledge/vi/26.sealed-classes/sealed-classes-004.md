# Lớp con `final`, `sealed` và `non-sealed` trong hệ phân cấp sealed — Java 17

## 1. Mục tiêu của bài học

Java 17 đưa **sealed classes** và **sealed interfaces** vào ngôn ngữ dưới dạng tính năng chính thức. Với một lớp hoặc giao diện khai báo `sealed`, người thiết kế có thể chỉ định **những kiểu nào được trực tiếp kế thừa hoặc triển khai** nó. Đây là cách kiểm soát *tập nhánh trực tiếp* của một hệ phân cấp kiểu, thay vì để mọi class có quyền truy cập tùy ý `extends`/`implements`.

Điểm phải học kỹ nhất không chỉ là cú pháp `permits` ở lớp cha, mà là **nghĩa vụ của lớp con trực tiếp được cấp phép**:

> Trong Java 17, một class trực tiếp kế thừa một sealed superclass hoặc trực tiếp implements một sealed interface phải xác định rõ chính sách kế thừa tiếp theo: `final`, `sealed` hoặc `non-sealed`. Với record, tính `final` được áp dụng ngầm định.

Ba lựa chọn không tương đương:

- **`final`**: kết thúc nhánh ở chính class ấy; không cho class khác `extends` nó.
- **`sealed`**: cho phép tiếp tục phân nhánh nhưng giới hạn **những direct subclasses/subinterfaces được phép**; tầng tiếp theo lại chịu những quy tắc tương ứng.
- **`non-sealed`**: mở nhánh đó cho những kiểu kế thừa/triển khai tiếp theo theo Java access và inheritance rules thông thường, dù tổ tiên của nó vẫn là `sealed`.

Bài hướng dẫn từ cơ bản đến triển khai: các quy tắc JLS Java SE 17, nhiều tầng kế thừa, records, interfaces, giới hạn module/package và visibility, sự khác nhau giữa trực tiếp/gián tiếp, lỗi biên dịch thường gặp, khả năng mở rộng API, pattern matching Java 17, kiểm thử, thiết kế domain, các ví dụ chạy độc lập cùng stdout, bài tập có đáp án và checklist code review.

**Phiên bản:** Các ví dụ dùng Java 17 (`javac --release 17`). Không dựa vào `switch` pattern matching dạng preview hoặc ngữ pháp Java mới hơn.

## 2. Bắt đầu bằng một hệ phân cấp đơn giản

```java
sealed interface PaymentResult
        permits PaymentSuccess, PaymentFailure {
}

final class PaymentSuccess implements PaymentResult {
}

final class PaymentFailure implements PaymentResult {
}
```

Ba declarations này hợp lệ nếu ở phạm vi module/package phù hợp và chúng được biên dịch cùng nhau.

Đọc theo thứ tự:

1. `PaymentResult` là một sealed interface.
2. `permits PaymentSuccess, PaymentFailure` chỉ định **hai direct permitted subtypes**.
3. `PaymentSuccess` và `PaymentFailure` trực tiếp `implements PaymentResult`.
4. Mỗi class con đều ghi `final`, nên không class nào được tiếp tục `extends PaymentSuccess` hoặc `extends PaymentFailure`.
5. Class khác không nằm trong danh sách permits không được tự trực tiếp `implements PaymentResult`.

**Nhầm lẫn phổ biến:** danh sách `permits` không phải một danh sách object instances, cũng không phải list hằng enum. Nó liệt kê **các kiểu (classes/interfaces)** được phép làm **direct subtypes**.

### Minh họa trực quan

```text
sealed PaymentResult
├── final PaymentSuccess       (dừng nhánh)
└── final PaymentFailure       (dừng nhánh)
```

Nếu ý định domain là tập kết quả đóng, không cần mở rộng ở bất kỳ tầng nào, dùng final direct implementations như vậy rất tự nhiên.

## 3. Runnable: hai lớp con final

Lưu file **`FinalBranchesDemo.java`**:

```java
sealed interface Result permits Success, Failure {
    String description();
}

final class Success implements Result {
    private final int value;

    Success(int value) {
        this.value = value;
    }

    @Override
    public String description() {
        return "success:" + value;
    }
}

final class Failure implements Result {
    private final String reason;

    Failure(String reason) {
        this.reason = reason;
    }

    @Override
    public String description() {
        return "failure:" + reason;
    }
}

public class FinalBranchesDemo {
    public static void main(String[] args) {
        Result first = new Success(42);
        Result second = new Failure("invalid");

        System.out.println(first.description());
        System.out.println(second.description());
        System.out.println(first instanceof Success);
        System.out.println(second instanceof Failure);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 FinalBranchesDemo.java
java FinalBranchesDemo
```

**Stdout chính xác:**

```text
success:42
failure:invalid
true
true
```

`Result` là interface; hai implementations là final classes. Các references có static type `Result` vẫn gọi đúng method overrides nhờ dynamic dispatch.

## 4. Ba modifier phải được hiểu ở cấp nào?

Đặt một sealed parent:

```java
sealed class Parent permits Closed, Restricted, Open {
}

final class Closed extends Parent {
}

sealed class Restricted extends Parent permits RestrictedChild {
}

final class RestrictedChild extends Restricted {
}

non-sealed class Open extends Parent {
}
```

Các modifiers `final`/`sealed`/`non-sealed` áp dụng cho **declaration của những direct subclasses** (`Closed`, `Restricted`, `Open`), không phải cho references đến chúng.

| Modifier | Cho class khác extends nó? | Ai quyết định lớp con tiếp theo? | Lựa chọn thích hợp |
| --- | --- | --- | --- |
| `final` | Không | Không có lớp con nữa | Biến thể cuối cùng, đóng nhánh |
| `sealed` | Có, nhưng giới hạn | Chính class sealed thông qua `permits`/inference | Cho một số biến thể cấp dưới đã biết |
| `non-sealed` | Có nếu các quy tắc thông thường cho phép | Không còn whitelist sealed tại nhánh ấy | Điểm mở rộng cho bên thứ ba |
| Không ghi một trong ba trên direct class child | **Lỗi trong Java 17** | Không được để mơ hồ | Phải chọn một chính sách |

**Không nhầm `non-sealed` với `non-final`.** `non-final` không phải một keyword modifier của Java. `non-sealed` là từ khóa modifier thực sự trong ngữ cảnh sealed hierarchy.

## 5. Vì sao Java buộc lớp con phải chọn chính sách?

Nếu một sealed parent chỉ giới hạn direct children mà không buộc children nói rõ chính sách, người đọc khó biết liệu hệ thống thực sự đóng ở tầng con hay vô tình để một nhánh mở.

Java 17 yêu cầu lựa chọn minh bạch:
- Chọn `final` nếu direct child là **lá** của cây kế thừa.
- Chọn `sealed` nếu direct child còn có các nhánh hợp lệ nhưng được kiểm soát.
- Chọn `non-sealed` nếu direct child là **điểm mở rộng có chủ đích**.

Quy tắc giúp reviewer đánh giá *ở mỗi nút* xem hệ phân cấp còn có thể mở rộng tiếp hay không.

**Điều compiler bảo vệ:** kiểu nào được **trực tiếp** kế thừa/triển khai sealed parent và chính sách của direct subclasses/direct subinterfaces. Compiler không chứng minh mọi business rule hay object invariant mà ứng dụng mong muốn.

## 6. `final`: dừng nhánh kế thừa

`final class Leaf extends SealedParent` vừa thực hiện nghĩa vụ của direct child vừa chặn những classes khác `extends Leaf`.

```java
sealed class Vehicle permits Car, Truck {
}

final class Car extends Vehicle {
}

final class Truck extends Vehicle {
}
```

Nếu thử:

```java
// Compile-negative:
class SportsCar extends Car {
}
```

Java từ chối vì `Car` final. Tất nhiên, nếu `SportsCar` đồng thời cố trực tiếp `extends Vehicle` mà không được permits, nó cũng vi phạm sealed-parent restriction.

### `final` có làm object bất biến không?

Không. `final` trên **class** ngăn subclassing, không tự khiến mọi fields final hoặc thread-safe.

```java
final class Counter {
    int value;

    void increment() {
        value++;
    }
}
```

`Counter` không thể bị extends, nhưng `value` vẫn thay đổi. Đây là lỗi hiểu lầm phổ biến khi đọc một nhánh sealed có final leaf.

### `final` có dùng trên interface không?

Không. Java interface không được khai báo `final`. Nếu direct subtype của sealed interface **cũng là interface**, dùng `sealed` hoặc `non-sealed`; nếu direct subtype là một **class** implements interface, class có thể là `final`, `sealed` hoặc `non-sealed`.

## 7. Runnable: final leaf vẫn có state mutable

Lưu **`FinalLeafStateDemo.java`**:

```java
sealed interface Task permits MutableTask {
    int done();
}

final class MutableTask implements Task {
    private int completed;

    void completeOne() {
        completed++;
    }

    @Override
    public int done() {
        return completed;
    }
}

public class FinalLeafStateDemo {
    public static void main(String[] args) {
        MutableTask task = new MutableTask();

        task.completeOne();
        task.completeOne();

        System.out.println(task.done());
        System.out.println(task instanceof Task);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 FinalLeafStateDemo.java
java FinalLeafStateDemo
```

Stdout:

```text
2
true
```

Class `MutableTask` là final **về kế thừa**. State `completed` vẫn mutable. Nếu dùng đồng thời nhiều threads, `completed++` còn cần synchronization thích hợp.

## 8. `sealed`: giữ quyền kiểm soát ở tầng kế tiếp

Một direct subclass có thể tự là `sealed` và liệt kê direct subtypes của mình:

```java
sealed interface Expression permits Literal, Binary {
}

final class Literal implements Expression {
}

sealed abstract class Binary implements Expression
        permits Addition, Multiplication {
}

final class Addition extends Binary {
}

final class Multiplication extends Binary {
}
```

Cây:

```text
sealed Expression
├── final Literal
└── sealed abstract Binary
    ├── final Addition
    └── final Multiplication
```

- `Expression` kiểm soát direct children: `Literal` và `Binary`.
- `Binary` kiểm soát direct subclasses: `Addition` và `Multiplication`.
- `Addition`/`Multiplication` là **indirect descendants** của Expression.
- Không cần liệt kê Addition/Multiplication trong `Expression.permits`, vì chúng **không trực tiếp** implements/extends Expression.

### `sealed` và `abstract`

Một class có thể vừa `sealed` vừa `abstract`:
- `sealed` quyết định **những subclasses được cấp phép**.
- `abstract` quyết định khả năng trực tiếp khởi tạo và các abstract methods.

Chúng không mâu thuẫn. Ngược lại, `final abstract class` là tổ hợp mâu thuẫn.

## 9. Runnable: nhiều tầng sealed và tính toán expression

Lưu **`SealedExpressionTreeDemo.java`**:

```java
sealed interface Expr permits Num, BinaryExpr {
    int evaluate();
}

record Num(int value) implements Expr {
    @Override
    public int evaluate() {
        return value;
    }
}

sealed abstract class BinaryExpr implements Expr
        permits AddExpr, MultiplyExpr {
    protected final Expr left;
    protected final Expr right;

    BinaryExpr(Expr left, Expr right) {
        this.left = left;
        this.right = right;
    }
}

final class AddExpr extends BinaryExpr {
    AddExpr(Expr left, Expr right) {
        super(left, right);
    }

    @Override
    public int evaluate() {
        return left.evaluate() + right.evaluate();
    }
}

final class MultiplyExpr extends BinaryExpr {
    MultiplyExpr(Expr left, Expr right) {
        super(left, right);
    }

    @Override
    public int evaluate() {
        return left.evaluate() * right.evaluate();
    }
}

public class SealedExpressionTreeDemo {
    public static void main(String[] args) {
        Expr expression = new MultiplyExpr(
                new AddExpr(new Num(2), new Num(3)),
                new Num(4));

        System.out.println(expression.evaluate());
        System.out.println(expression instanceof BinaryExpr);
        System.out.println(expression instanceof MultiplyExpr);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SealedExpressionTreeDemo.java
java SealedExpressionTreeDemo
```

Stdout:

```text
20
true
true
```

`Num` là record và **ngầm final**, nên có thể làm permitted direct implementation của sealed interface `Expr` mà không phải ghi `final` trong record declaration. `BinaryExpr` là một permitted direct class dùng `sealed`, rồi chặn số lớp phép toán nhị phân có thể extends trực tiếp.

## 10. `non-sealed`: chủ động mở nhánh

`non-sealed` có nghĩa rằng type **không tiếp tục áp danh sách direct permitted subtypes** của chính mình; subclasses tiếp theo chịu quy tắc extends/implements/accessibility bình thường.

```java
sealed class Notification permits EmailNotification,
        ExtensibleNotification {
}

final class EmailNotification extends Notification {
}

non-sealed class ExtensibleNotification
        extends Notification {
}

class SmsNotification extends ExtensibleNotification {
}

class PushNotification extends ExtensibleNotification {
}
```

`Notification` **chỉ permits trực tiếp** EmailNotification và ExtensibleNotification. Nó không cần liệt kê SmsNotification hoặc PushNotification vì hai classes này kế thừa **gián tiếp** qua ExtensibleNotification.

### Điều `non-sealed` *không* làm

- Không tự biến constructor private thành accessible.
- Không bỏ Java module/package access rules.
- Không bảo đảm mọi bên thứ ba đều có thể tạo subclass trong mọi hoàn cảnh.
- Không làm class abstract trở thành concrete.
- Không làm public API tự động hỗ trợ mọi extension.
- Không thể dùng `non-sealed` một cách tùy tiện trên class không có direct sealed superclass/superinterface.

Nó chỉ **bỏ cơ chế sealed restriction ở nhánh này**, không bỏ mọi hạn chế khác.

## 11. Runnable: non-sealed và các cháu không cần permits của ông

Lưu **`NonSealedExtensionDemo.java`**:

```java
sealed interface Message permits SystemMessage, CustomMessage {
    String text();
}

final class SystemMessage implements Message {
    @Override
    public String text() {
        return "system";
    }
}

non-sealed abstract class CustomMessage implements Message {
}

final class EmailMessage extends CustomMessage {
    @Override
    public String text() {
        return "email";
    }
}

class SmsMessage extends CustomMessage {
    @Override
    public String text() {
        return "sms";
    }
}

public class NonSealedExtensionDemo {
    public static void main(String[] args) {
        Message one = new SystemMessage();
        Message two = new EmailMessage();
        Message three = new SmsMessage();

        System.out.println(one.text());
        System.out.println(two.text());
        System.out.println(three.text());
        System.out.println(two instanceof CustomMessage);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 NonSealedExtensionDemo.java
java NonSealedExtensionDemo
```

Stdout:

```text
system
email
sms
true
```

`EmailMessage` và `SmsMessage` là descendants của `Message` nhưng **không trực tiếp implements sealed Message**. Chúng không cần xuất hiện trong `Message.permits`.

`CustomMessage` là `non-sealed abstract class` — một tổ hợp hợp lệ: abstract buộc subclasses hiện thực hóa methods, non-sealed cho phép mở rộng tập subclasses.

## 12. Phân biệt lớp con trực tiếp và gián tiếp

Với:

```java
sealed class Root permits Branch {
}

non-sealed class Branch extends Root {
}

class Leaf extends Branch {
}
```

- `Branch` là **direct subclass** của `Root`.
- `Leaf` là **direct subclass** của `Branch`, nhưng chỉ là **indirect subclass** của `Root`.
- `Root.permits Branch` đủ để cho phép mối quan hệ trên.
- `Leaf` không được đưa vào `Root.permits` nếu Leaf không extends Root trực tiếp.
- `Leaf` **không phải khai báo final/sealed/non-sealed** chỉ vì Root sealed, bởi **direct superclass** của Leaf là non-sealed Branch.

### Tại sao điều này quan trọng với API?

Nếu người thiết kế chọn `non-sealed Branch`, họ đã chủ động nhường quyền mở rộng ở nhánh Branch. Không được mô tả Root như “đóng tuyệt đối ở mọi tầng” trong trường hợp ấy. Chỉ phần direct children được Root kiểm soát; nhánh non-sealed có thể phát triển tùy thiết kế.

## 13. Non-sealed không lan truyền modifier tới lớp cháu

```java
sealed class A permits B {
}

non-sealed class B extends A {
}

class C extends B {
}

final class D extends C {
}
```

Code hợp lệ: `C` là ordinary class và không cần tự ghi non-sealed. `D` là final theo thiết kế của chính D.

**Không có quy tắc mọi descendants đều phải gắn một trong ba modifiers.** Yêu cầu cụ thể áp dụng khi declaration là **direct subtype của một sealed type**. Một lớp C kế thừa non-sealed B không trực tiếp kế thừa sealed A.

### Re-seal một nhánh được không?

Có thể đặt một ranh giới sealed mới ở phía dưới nhánh đã mở:

```java
sealed class Root permits Open {
}

non-sealed class Open extends Root {
}

sealed class Controlled extends Open permits End {
}

final class End extends Controlled {
}
```

`Controlled` không phải direct permitted subclass của Root; nó tự chọn `sealed` để kiểm soát descendants trực tiếp của chính nó. `non-sealed` ở Open cho phép subclass như Controlled được khai báo mà không phải nằm trong Root.permits.

## 14. Runnable: mở nhánh rồi niêm phong lại

Lưu **`ResealBranchDemo.java`**:

```java
sealed interface Event permits ExtensionPoint {
    String kind();
}

non-sealed abstract class ExtensionPoint implements Event {
}

sealed class ControlledEvent extends ExtensionPoint
        permits SuccessEvent, FailureEvent {
    @Override
    public String kind() {
        return "controlled";
    }
}

final class SuccessEvent extends ControlledEvent {
}

final class FailureEvent extends ControlledEvent {
}

public class ResealBranchDemo {
    public static void main(String[] args) {
        Event first = new SuccessEvent();
        Event second = new FailureEvent();

        System.out.println(first.kind());
        System.out.println(second instanceof ControlledEvent);
        System.out.println(first instanceof ExtensionPoint);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ResealBranchDemo.java
java ResealBranchDemo
```

Stdout:

```text
controlled
true
true
```

Một số lập trình viên nhầm rằng “đã non-sealed thì không được sealed trở lại”. Đó là sai: type thấp hơn có thể tự sealed **nhánh trực tiếp của nó** bằng declaration mới, miễn tuân đúng quy tắc Java.

## 15. `non-sealed` chỉ hợp lệ khi có direct sealed parent phù hợp

Sai:

```java
// Compile-negative:
non-sealed class Plain {
}
```

Nếu `Plain` không trực tiếp extends một sealed class hoặc trực tiếp implements một sealed interface, modifier `non-sealed` không có ngữ cảnh phù hợp và bị Java từ chối.

Sai tương tự:

```java
class Ordinary {
}

// Compile-negative:
non-sealed class Child extends Ordinary {
}
```

`Ordinary` không phải sealed class và Child không có direct sealed superinterface nào; vì vậy không dùng `non-sealed`.

### Lưu ý khi có cả superclass và interfaces

Một class có thể extends một non-sealed superclass nhưng **trực tiếp implements một sealed interface**. Khi ấy nó vẫn là direct subtype của sealed interface, và `non-sealed` có thể hợp lệ nếu được interface permits:

```java
sealed interface Role permits CustomRole {
}

class BaseRole {
}

non-sealed class CustomRole extends BaseRole
        implements Role {
}
```

Vị trí `sealed` trong các **direct supertypes** mới quyết định yêu cầu/khả năng khai báo `non-sealed`.

## 16. Sealed interface: không có `final interface`

Một sealed interface có thể cho phép:
- **Một class** implement trực tiếp, và class chọn `final`/`sealed`/`non-sealed` (record ngầm final).
- **Một interface** extends trực tiếp, và interface chọn **`sealed` hoặc `non-sealed`**.

Ví dụ:

```java
sealed interface Protocol permits InternalProtocol, OpenProtocol {
}

sealed interface InternalProtocol extends Protocol
        permits InternalProtocolImpl {
}

final class InternalProtocolImpl
        implements InternalProtocol {
}

non-sealed interface OpenProtocol extends Protocol {
}

class PluginProtocolImpl implements OpenProtocol {
}
```

`InternalProtocol` là sealed direct subinterface. `OpenProtocol` là non-sealed direct subinterface. `PluginProtocolImpl` không trực tiếp implements sealed Protocol; nó implements interface đã được mở.

**Không viết `final interface InternalProtocol`**. Java không cho interface `final`; một interface luôn có khả năng được triển khai bởi classes, còn sealed interface kiểm soát *các direct subtypes* bằng cách giới hạn danh sách.

## 17. Runnable: phân nhánh interface đóng/mở

Lưu **`SealedInterfacesDemo.java`**:

```java
sealed interface Service permits CoreService, PluginService {
    String id();
}

sealed interface CoreService extends Service
        permits BuiltInService {
}

final class BuiltInService implements CoreService {
    @Override
    public String id() {
        return "core";
    }
}

non-sealed interface PluginService extends Service {
}

final class ThirdPartyService implements PluginService {
    @Override
    public String id() {
        return "third-party";
    }
}

public class SealedInterfacesDemo {
    public static void main(String[] args) {
        Service first = new BuiltInService();
        Service second = new ThirdPartyService();

        System.out.println(first.id());
        System.out.println(second.id());
        System.out.println(second instanceof PluginService);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SealedInterfacesDemo.java
java SealedInterfacesDemo
```

Stdout:

```text
core
third-party
true
```

Giao diện `PluginService` mở đường cho các implementation ở bên dưới, trong khi `CoreService` vẫn yêu cầu whitelist riêng.

## 18. Bảng so sánh đầy đủ class/interface

| Direct subtype của sealed parent | Modifier hợp lệ | Điều cần bổ sung |
| --- | --- | --- |
| Concrete class leaf | `final` | Implement mọi abstract methods cần thiết |
| Abstract class muốn giữ nhánh có kiểm soát | `abstract sealed` | Có direct permitted children |
| Concrete class muốn giới hạn nhánh | `sealed` | Liệt kê/infer direct permitted children |
| Concrete class muốn cho extend tự do | `non-sealed` | Tuân các quy tắc access/constructor thông thường |
| Abstract class muốn extension point | `abstract non-sealed` | Caller có thể viết subclasses hợp lệ |
| Direct subinterface có whitelist riêng | `sealed interface` | Có permitted direct subtypes |
| Direct subinterface muốn extension | `non-sealed interface` | Không có permits whitelist của nó |
| Direct subinterface viết `final` | **Không hợp lệ** | `final` không áp cho interface |
| Direct class child không ghi modifier | **Không hợp lệ** | Chọn final/sealed/non-sealed |
| Direct record implements sealed interface | **Hợp lệ, ngầm final** | Record phải nằm trong permits hoặc được suy ra |
| Indirect class descendant của non-sealed parent | Không bắt buộc modifier thuộc bộ ba | Chỉ cần quy tắc class thường nếu direct supertypes không sealed |

**Bẫy trộn modifiers:** `final sealed class`, `final non-sealed class`, `sealed non-sealed class` không biểu diễn những chính sách đồng thời hợp lệ. Class phải chọn một chính sách kế thừa nhất quán.

## 19. Record: direct permitted class mặc nhiên final

Java record được ngôn ngữ xem là final; không có subclasses của record. Vì vậy record là lựa chọn tiện lợi cho những **leaf variants mang dữ liệu** của sealed interface:

```java
sealed interface ApiResult permits Ok, ErrorResult {
}

record Ok(String value) implements ApiResult {
}

record ErrorResult(String message) implements ApiResult {
}
```

Không cần `final record Ok(...)` để chứng tỏ thỏa nghĩa vụ direct permitted child; `record` đã cung cấp final semantics. Record vẫn là một class, nên `implements ApiResult` là mối quan hệ trực tiếp.

### Điều record *không* làm

- Record không được extends một class tự chọn ngoài `java.lang.Record`.
- Record không thể là sealed class làm parent cho subclasses khác.
- Record không tự deep immutable nếu component giữ mutable objects/arrays.
- Record không tự làm API exhaustiveness của Java 17 `switch` theo sealed interface mà không dùng các cơ chế phù hợp.

## 20. Runnable: sealed interface và record leaves

Lưu **`SealedRecordVariantsDemo.java`**:

```java
sealed interface SearchResult permits Found, Missing {
}

record Found(String value) implements SearchResult {
}

record Missing(String reason) implements SearchResult {
}

public class SealedRecordVariantsDemo {
    static String describe(SearchResult result) {
        if (result instanceof Found found) {
            return "found:" + found.value();
        }
        if (result instanceof Missing missing) {
            return "missing:" + missing.reason();
        }
        throw new IllegalStateException("unhandled");
    }

    public static void main(String[] args) {
        System.out.println(describe(new Found("Java")));
        System.out.println(describe(new Missing("not indexed")));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SealedRecordVariantsDemo.java
java SealedRecordVariantsDemo
```

Stdout:

```text
found:Java
missing:not indexed
```

`instanceof` pattern matching cho variable `found`/`missing` là **tính năng chuẩn trong Java 17**, không cần preview. Phần xử lý `throw` cuối vẫn được viết tường minh; sealed metadata không tự biến một chuỗi `if/instanceof` thành một `switch` exhaustiveness proof.

## 21. `permits` chỉ tác động direct subtypes

Giả sử:

```java
sealed interface Animal permits Mammal, Bird {
}

non-sealed abstract class Mammal implements Animal {
}

final class Bird implements Animal {
}

class Dog extends Mammal {
}

class Cat extends Mammal {
}
```

Trong hình:

```text
sealed Animal
├── non-sealed Mammal
│   ├── Dog
│   └── Cat
└── final Bird
```

`Animal.permits Mammal, Bird` đủ. `Dog` và `Cat` là indirect implementations của Animal qua Mammal.

Nếu đổi Dog thành:

```java
// Compile-negative nếu Dog không được permits:
class Dog implements Animal {
    // ...
}
```

thì Dog bây giờ **trực tiếp** implements Animal, khác hoàn toàn quan hệ trước. Java từ chối nếu Dog không nằm trong permitted set.

### Vấn đề thiết kế

Khi thêm một subtype, hãy xác định **nó extends/implements trực tiếp kiểu nào**. Không chỉ kiểm tra `instanceof Animal` hoặc câu “nó cũng là Animal” vì `instanceof` nhận cả descendants gián tiếp.

## 22. Điều kiện về `permits` và module/package

`final`/`sealed`/`non-sealed` quyết định **chính sách mở rộng của nhánh**; vị trí các permitted direct children vẫn chịu giới hạn riêng:

- **Named module:** phải cùng named module, có thể khác package nếu type visibility hợp lệ.
- **Unnamed module:** phải cùng package.
- Mọi child vẫn cần trực tiếp extends/implements parent và constructor/access hợp lệ.

Ví dụ trong một file `Payment.java` thuộc package `demo`:

~~~java
package demo;
public sealed interface Payment permits Cash, Card {}
final class Cash implements Payment {}
final class Card implements Payment {}
~~~

Những class khác package không được tự thêm trực tiếp vào một root ở unnamed module. Muốn plugin ngoài boundary, cho phép nhánh `non-sealed` thích hợp. Bài **Ràng buộc cùng module hoặc cùng package** trình bày ví dụ nhiều files, named modules và source layout; mục này chỉ kiểm ràng buộc kết hợp với branch modifiers.

## 23. Permits có thể được suy luận khi các direct children cùng compilation unit

Khi sealed parent và direct children cùng **compilation unit**, có thể bỏ `permits` explicit:

~~~java
sealed interface Shape {}
record Circle(double radius) implements Shape {}
record Square(double side) implements Shape {}
~~~

Compiler suy ra permitted direct children từ khai báo cùng source file, **không** tự tìm tất cả class trong package khi tách files. Điều này không thay yêu cầu mỗi child phải chọn đúng extension policy. Bài **Điều kiện suy ra danh sách lớp con khi bỏ permits** giải thích sâu canonical names, local/anonymous types và điều kiện compilation-unit; nội dung chính ở đây là lựa chọn `final`/`sealed`/`non-sealed` sau khi đã xác định direct children.

## 24. Runnable: permits inference trong một file

Lưu **`InferredPermitsDemo.java`**:

```java
sealed interface Shape {
    int area();
}

record Square(int side) implements Shape {
    @Override
    public int area() {
        return side * side;
    }
}

record Rectangle(int width, int height) implements Shape {
    @Override
    public int area() {
        return width * height;
    }
}

public class InferredPermitsDemo {
    public static void main(String[] args) {
        Shape first = new Square(3);
        Shape second = new Rectangle(3, 4);

        System.out.println(first.area());
        System.out.println(second.area());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 InferredPermitsDemo.java
java InferredPermitsDemo
```

Stdout:

```text
9
12
```

`Shape` vẫn sealed dù không ghi explicit `permits`. Compiler suy direct permitted types từ các declarations trong cùng compilation unit. `Square` và `Rectangle` là records, implicit final.

## 25. Trường hợp con trực tiếp bị quên modifier

Code **cố ý không biên dịch**:

```java
sealed class Base permits Child {
}

class Child extends Base {
}
```

Lỗi là `Child` không khai báo chính sách `final`, `sealed` hoặc `non-sealed` như một direct permitted subclass của sealed Base.

Các hướng sửa khác nhau:

```java
// Đóng nhánh:
final class Child extends Base { }
```

```java
// Mở nhánh:
non-sealed class Child extends Base { }
```

```java
// Kiểm soát thêm một tầng:
sealed class Child extends Base permits Grandchild { }
final class Grandchild extends Child { }
```

Mỗi snippet là **một phương án riêng**, không đặt cả ba declarations trùng tên vào cùng source file.

## 26. Vì sao `abstract class Child` chưa đủ?

`abstract` giải quyết câu hỏi “class này có thể được instantiate trực tiếp không?”, không giải quyết câu hỏi “ai được extends class này?”.

Code sai:

```java
sealed class Root permits AbstractChild {
}

abstract class AbstractChild extends Root {
}
```

`AbstractChild` vẫn thiếu final/sealed/non-sealed. Hai cách hợp lệ:

```java
abstract non-sealed class AbstractChild extends Root {
}
```

hoặc:

```java
abstract sealed class AbstractChild extends Root
        permits ConcreteChild {
}

final class ConcreteChild extends AbstractChild {
}
```

**Không viết `abstract final class`**, bởi abstract cần một subclass concrete để instantiate trong khi final ngăn subclass.

## 27. Direct subinterface bắt buộc sealed hay non-sealed

Sai:

```java
sealed interface Root permits Branch {
}

interface Branch extends Root {
}
```

`Branch` trực tiếp extends sealed Root nhưng không có modifier.

Sửa thành:

```java
non-sealed interface Branch extends Root {
}
```

Hoặc:

```java
sealed interface Branch extends Root permits Leaf {
}

final class Leaf implements Branch {
}
```

Không thể sửa bằng `final interface Branch` — Java cấm final interface.

### Còn ordinary interface con của non-sealed interface?

Hợp lệ:

```java
sealed interface Root permits Open {
}

non-sealed interface Open extends Root {
}

interface Further extends Open {
}

class Impl implements Further {
}
```

`Further` không phải direct subinterface của sealed Root; direct superinterface của Further là Open (non-sealed), nên Further không buộc ghi sealed/non-sealed.

## 28. Cấm `permits` cho non-sealed type

Một `non-sealed` type không thể đồng thời khai báo permits whitelist của chính nó:

```java
// Compile-negative:
sealed interface Root permits Open {
}

non-sealed interface Open extends Root permits Only {
}
```

`permits` áp dụng khi declaration là sealed type, không phải non-sealed extension point.

Nếu muốn giới hạn, khai báo `sealed interface Open extends Root permits Only`; nếu muốn mở, `non-sealed interface Open extends Root` mà không có permits.

**Một nhánh không thể vừa khẳng định “mở” vừa đặt danh sách direct children đóng trong cùng declaration.**

## 29. Một class implements hai sealed interfaces

Một class có thể trực tiếp implements nhiều interfaces, kể cả nhiều sealed interfaces, nhưng khi ấy **mỗi sealed interface phải permits class đó**, và class cần thỏa modifier requirement:

```java
sealed interface Readable permits SharedResource {
}

sealed interface Writable permits SharedResource {
}

final class SharedResource implements Readable, Writable {
}
```

Hợp lệ nếu các package/module/access conditions khác đều thỏa.

Nếu `Writable` chỉ permits một class khác, SharedResource không được trực tiếp implements Writable, dù Readable có permits nó.

### Bài học thiết kế

Permission không tự truyền từ một interface qua interface khác. Mỗi **direct sealed parent** độc lập kiểm soát danh sách permitted direct subtypes.

## 30. Runnable: thực thi hai sealed contracts cùng lúc

Lưu **`MultipleSealedParentsDemo.java`**:

```java
sealed interface Left permits Dual {
    String left();
}

sealed interface Right permits Dual {
    String right();
}

final class Dual implements Left, Right {
    @Override
    public String left() {
        return "L";
    }

    @Override
    public String right() {
        return "R";
    }
}

public class MultipleSealedParentsDemo {
    public static void main(String[] args) {
        Dual value = new Dual();

        System.out.println(value.left() + value.right());
        System.out.println(value instanceof Left);
        System.out.println(value instanceof Right);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 MultipleSealedParentsDemo.java
java MultipleSealedParentsDemo
```

Stdout:

```text
LR
true
true
```

Lớp `Dual` trực tiếp implements cả `Left` và `Right`; cả hai đều có tên Dual trong permits. `final` trên Dual giải quyết nhánh con cho cả hai contracts.

## 31. Lớp con là record: điều kiện cần nhớ

Đối với một sealed **interface**, record có thể implements trực tiếp:

```java
sealed interface Outcome permits Ok, Err {
}

record Ok(int value) implements Outcome {
}

record Err(String message) implements Outcome {
}
```

Tại sao không viết record extends sealed **class**?

`record` không thể extends class tùy ý: Java record đã implicitly extends `java.lang.Record` và là final. Vì thế:

```java
// Compile-negative:
sealed class Base permits SomeRecord {
}
record SomeRecord(int n) extends Base {
}
```

là sai cả vì record declaration không thể ghi `extends Base` như class bình thường. Muốn record làm leaf variant, ưu tiên sealed interface.

### Enum cũng có cơ chế riêng

Enum classes có quy tắc final/sealed ngầm định phụ thuộc constant-specific bodies, và không thể extends một class ngoài `java.lang.Enum`. Chúng có thể tham gia hierarchy qua interfaces khi declarations đáp ứng yêu cầu permits và các quy tắc JLS; không nên lấy quy tắc ordinary class `final class Child` áp máy móc cho cú pháp enum.

## 32. `non-sealed` vẫn chịu giới hạn constructor và visibility

Một ví dụ nhìn có vẻ “mở”:

```java
sealed class Root permits Open {
}

non-sealed class Open extends Root {
    private Open() {
    }
}
```

Nếu một class bên ngoài phạm vi private/nest access thử `extends Open`, compiler có thể không có đường gọi superclass constructor accessible, nên subclass ấy không hợp lệ dù Open non-sealed.

Muốn một extension point thực sự usable:
- Cung cấp accessible constructor phù hợp, thường protected/public tùy contract.
- Thiết kế invariant ổn định cho subclasses.
- Bảo đảm supertype/constructor accessible qua module/package boundaries.
- Công bố methods mà extension cần override.
- Kiểm tra security, thread-safety và lifecycle nếu bên thứ ba viết subclass.

**Chữ `non-sealed` không cấp thêm quyền truy cập.** Nó chỉ loại bỏ *sealed direct-subtype whitelist* tại type ấy.

## 33. Runnable: điểm mở rộng có constructor protected

Lưu **`OpenExtensionConstructorDemo.java`**:

```java
sealed abstract class Renderer permits RendererExtension {
    abstract String render();
}

abstract non-sealed class RendererExtension extends Renderer {
    protected final String prefix;

    protected RendererExtension(String prefix) {
        this.prefix = prefix;
    }
}

final class HtmlRenderer extends RendererExtension {
    HtmlRenderer() {
        super("<html>");
    }

    @Override
    String render() {
        return prefix + "content</html>";
    }
}

public class OpenExtensionConstructorDemo {
    public static void main(String[] args) {
        Renderer renderer = new HtmlRenderer();

        System.out.println(renderer.render());
        System.out.println(renderer instanceof RendererExtension);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 OpenExtensionConstructorDemo.java
java OpenExtensionConstructorDemo
```

Stdout:

```text
<html>content</html>
true
```

`Renderer` vẫn sealed, nhưng `RendererExtension` là non-sealed extension point. `HtmlRenderer` không nằm trong Renderer.permits; nó trực tiếp extends RendererExtension và kế thừa gián tiếp Renderer.

## 34. Mục đích của `final` trong domain modeling

Một hệ phân cấp sealed thường đại diện một **tập biến thể của cùng một ý nghĩa**:

```java
sealed interface PaymentMethod
        permits CardPayment, BankTransfer, CustomPayment {
}

record CardPayment(String lastFour)
        implements PaymentMethod {
}

record BankTransfer(String iban)
        implements PaymentMethod {
}

non-sealed interface CustomPayment
        extends PaymentMethod {
}
```

Hai record leaves biểu diễn **những biến thể do core system kiểm soát**. `CustomPayment` là extension point chủ đích.

Nếu loại payment Card không được phép có arbitrary subclasses ngoài `CardPayment`, record/final class giúp khóa representation của nhánh. Nếu CustomPayment được dùng cho plugins, API phải xác định trách nhiệm validation và security của custom implementations.

### Có phải cứ sealed là tốt hơn enum?

Không phải. Enum phù hợp khi biến thể là **tập hằng singleton đã biết**, ít hoặc không có payload per instance. Sealed interface + record final leaves phù hợp khi mỗi biến thể có **nhiều instances mang payload khác nhau**.

Ví dụ `Success("A")` và `Success("B")` là hai record objects khác state; điều ấy khác `enum Status.SUCCESS` chỉ là một enum constant.

## 35. Khi nào nên chọn `sealed` ở tầng giữa?

Chọn `sealed` cho một intermediate class/interface khi:
- Domain đã biết danh sách nhóm con ở tầng ấy.
- Không muốn plugin tạo arbitrary subtype trong nhóm nhạy cảm.
- Cần invariant hoặc behavior chung ở tầng giữa.
- Muốn future additions vào nhóm đó phải được review bằng cách sửa permits.
- Có một số leaf variants final/records ở tầng cuối.

Ví dụ cấu trúc:

```text
sealed Request
├── final Ping
├── sealed AuthRequest
│   ├── final PasswordRequest
│   └── final TokenRequest
└── non-sealed ExtensionRequest
    └── [plugin-defined classes...]
```

Nhánh `AuthRequest` được khóa chặt vì liên quan bảo mật. Nhánh `ExtensionRequest` được mở theo contract plugin. Đây là biểu đạt ý định rõ hơn một lớp cha thường cho phép mọi subclass.

### Không tăng độ sâu vô ích

Quá nhiều tầng sealed (A permits B; B permits C; C permits D) có thể khiến hierarchy khó đọc. Chỉ dùng intermediate sealed khi nó thể hiện một nhóm nghiệp vụ hoặc policy cần thiết.

## 36. Switch và sealed hierarchy ở Java 17

Trong Java 17:
- `instanceof` pattern matching là tính năng ổn định, có thể dùng để phân biệt variants.
- `switch` expression với enum là tính năng ổn định.
- **Pattern matching for switch trên sealed types chưa phải tính năng chính thức không cần preview trong Java 17**. Không viết một `switch (shape) { case Circle c -> ... }` như ví dụ `javac --release 17` thông thường.
- Không giả định compiler Java 17 chứng minh exhaustiveness của một chuỗi `if/else` chỉ nhờ sealed permits.

Một cách xử lý không cần preview:

```java
static String describe(Shape shape) {
    if (shape instanceof Circle circle) {
        return "circle:" + circle.radius();
    }
    if (shape instanceof Square square) {
        return "square:" + square.side();
    }
    throw new IllegalStateException("unsupported");
}
```

Đây là **snippet** giả định `Shape` sealed interface và `Circle`/`Square` là records. Cần thiết kế lỗi cuối phù hợp API. Nếu sau này thêm một permitted subtype, phải cập nhật xử lý thủ công.

### Có thể tăng độ an toàn bằng visitor?

Một visitor hoặc polymorphic method khai báo trong sealed parent có thể khiến compiler yêu cầu mỗi concrete leaf cung cấp behavior, giảm thiếu sót khi có variant mới. Nhưng API nào tốt hơn phụ thuộc mục tiêu: transformation, extensibility hay separation of concerns.

## 37. Runnable: polymorphism thay vì switch preview

Lưu **`SealedPolymorphismDemo.java`**:

```java
sealed interface Shape permits Circle, Rect {
    int area();
}

record Circle(int radius) implements Shape {
    @Override
    public int area() {
        return 3 * radius * radius;
    }
}

record Rect(int width, int height) implements Shape {
    @Override
    public int area() {
        return width * height;
    }
}

public class SealedPolymorphismDemo {
    public static void main(String[] args) {
        Shape a = new Circle(2);
        Shape b = new Rect(4, 5);

        System.out.println(a.area());
        System.out.println(b.area());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SealedPolymorphismDemo.java
java SealedPolymorphismDemo
```

Stdout:

```text
12
20
```

`Circle` và `Rect` là record leaves. Sealed interface kiểm soát direct variants; polymorphic method giúp mỗi variant tự cung cấp implementation mà không cần switch theo runtime type.

**Lưu ý:** công thức ví dụ dùng 3 thay vì π để có int output xác định; nếu tính diện tích hình tròn thực, dùng double/Math.PI và làm tròn theo contract thích hợp.

## 38. Có được tạo subclass vô danh của sealed class không?

Cú pháp:

```java
// Compile-negative nếu Base là sealed và chỉ permits các
// kiểu có tên được liệt kê:
Base obj = new Base() {
};
```

Anonymous subclass cũng là **direct subclass** của Base. Nhưng sealed parent chỉ chấp nhận các permitted direct subclasses đã xác định theo source/module rules; anonymous subclass tại call site không thể tùy ý vượt whitelist.

Ngược lại, nếu đối tượng được tạo từ **non-sealed branch** accessible:

```java
sealed class Base permits Open {
}

non-sealed class Open extends Base {
}

Open instance = new Open() {
    @Override
    public String toString() {
        return "anonymous extension";
    }
};
```

có thể hợp lệ vì anonymous class trực tiếp extends **Open**, chứ không trực tiếp extends sealed Base. Constructor/access rules vẫn được xét như bình thường.

### Kết luận

`sealed` kiểm soát **các direct subclass declarations**, bất kể có tên hay vô danh. `non-sealed` mở một điểm xuống cấp dưới cho phép khả năng subclassing bình thường trở lại.

## 39. Binary/class loading và ý nghĩa của sealed

Trong Java 17, sealed relationships không chỉ là một quy ước comment:
- Compiler kiểm tra permits và direct subtype modifiers ở source level.
- Class-file metadata `PermittedSubclasses` biểu diễn quyền kế thừa trực tiếp theo JVM/class-file rules.
- Khi class loading/linking gặp direct subtype không được phép, JVM có thể từ chối class với linkage error phù hợp.
- `Class.isSealed()` và `Class.getPermittedSubclasses()` cung cấp Reflection API để khảo sát sealed types.

Không coi Reflection metadata là một danh sách tất cả runtime instances hay toàn bộ *transitive closure* của descendants. API permitted subclasses nói về **direct permitted types**.

**Chú ý:** quy tắc này không tự chứng minh mọi nơi tạo object là an toàn; methods, state và business logic vẫn cần validation.

## 40. Runnable: Reflection với các direct permitted types

Lưu **`SealedReflectionDemo.java`**:

```java
import java.util.Arrays;

sealed interface Root permits Alpha, Beta {
}

final class Alpha implements Root {
}

non-sealed class Beta implements Root {
}

public class SealedReflectionDemo {
    public static void main(String[] args) {
        System.out.println(Root.class.isSealed());
        System.out.println(Alpha.class.isSealed());
        System.out.println(Beta.class.isSealed());

        Class<?>[] permitted =
                Root.class.getPermittedSubclasses();

        String[] names = Arrays.stream(permitted)
                .map(Class::getSimpleName)
                .sorted()
                .toArray(String[]::new);

        System.out.println(Arrays.toString(names));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SealedReflectionDemo.java
java SealedReflectionDemo
```

Stdout:

```text
true
false
false
[Alpha, Beta]
```

`Alpha` final và `Beta` non-sealed đều **không tự là sealed**. Root isSealed true. Sắp xếp tên trước khi in để không phụ thuộc giả định về thứ tự mảng Reflection.

## 41. Sai lầm: sealed parent cho phép indirect descendant trực tiếp?

Giả sử:

```java
sealed class Root permits Intermediate {
}

non-sealed class Intermediate extends Root {
}

class Leaf extends Intermediate {
}
```

`Leaf` là **indirect descendant** của Root, nhưng **không là direct permitted subtype** của Root.

Không thể hợp thức hóa code sau chỉ bằng việc Root “có Leaf ở trong cây”:

```java
// Compile-negative vì Leaf không trực tiếp kế thừa Root:
sealed class Root permits Intermediate, Leaf {
}
```

**Danh sách permits chỉ gồm trực tiếp**. Nếu Leaf trực tiếp extends Intermediate, nó không nên nằm trong Root.permits. Nếu mục tiêu là Root trực tiếp permits Leaf, phải thay cấu trúc subtype quan hệ sao cho Leaf trực tiếp extends/implements Root và thỏa tất cả ràng buộc.

## 42. Sai lầm: `sealed class X` nhưng không có permitted child

Khai báo `sealed` không có ý nghĩa để biểu diễn một nhánh **không có lớp con nào**.

```java
// Compile-negative nếu không có direct permitted
// subclass hợp lệ để được suy ra:
sealed class Lonely {
}
```

Nếu thật sự không muốn subtype nào, hãy cân nhắc `final class Lonely`. Nếu muốn mô hình sealed, cần những direct subtypes được phép và hợp lệ.

**Không dùng `sealed` như từ đồng nghĩa `final`**:
- `final`: cấm mọi subclasses.
- `sealed`: cho **một tập** subclasses được khai báo phù hợp.

## 43. Sai lầm: modifier ở direct child không khớp

**Sai — direct class child bỏ trống modifier:**

```java
sealed class Root permits Child {
}

class Child extends Root {
}
```

**Sai — direct interface child cố dùng final:**

```java
sealed interface Root permits Branch {
}

final interface Branch extends Root {
}
```

**Sai — direct child `non-sealed` và `sealed` cùng lúc:**

```java
sealed class Root permits Branch {
}

sealed non-sealed class Branch extends Root {
}
```

**Sai — direct subclass không được permits:**

```java
sealed class Root permits Allowed {
}

final class Allowed extends Root {
}

final class Unlisted extends Root {
}
```

Các snippets này **cố ý không biên dịch**. Không đưa chung chúng vào một runnable file với những declarations trùng tên.

## 44. Khi nào `non-sealed` có nguy cơ thiết kế?

`non-sealed` rất hữu ích cho extension points, nhưng mở rộng cũng tạo trách nhiệm:

- Có thể xuất hiện subclasses mà core team chưa biết khi phát hành.
- Các subclasses có thể override non-final methods và đổi behavior.
- Một thuật toán `instanceof` xét vài lớp known có thể bỏ sót descendants mới.
- Serialization/integration frameworks có thể cần subtype registration.
- Invariant chỉ được duy trì nếu constructor/method design đúng.
- Security-sensitive domain cần kiểm soát inputs và extension boundaries.
- Public method contracts phải document rõ (thread safety, exceptions, lifecycle).

Nếu muốn một domain **exhaustive closed union**, không nên có non-sealed branch dễ dàng mở rộng. Dùng final leaves hoặc sealed intermediate groups với final leaves ở cuối.

## 45. Closed hierarchy và open extension point

Hai kiến trúc minh họa:

**Closed tree:**

```text
sealed Token
├── final Identifier
├── final NumberToken
└── final EndOfInput
```

Ưu điểm: tập variants được kiểm soát hoàn toàn. Phù hợp parser/compiler AST, protocol message cố định hoặc states được định nghĩa chặt.

**Hybrid tree:**

```text
sealed Handler
├── final BuiltInHandler
└── non-sealed PluginHandler
    ├── SomePluginHandler
    └── OtherPluginHandler
```

Ưu điểm: kiểm soát core categories nhưng vẫn công bố extension mechanism.

**Đặt non-sealed ở đâu là một quyết định API lớn**, không chỉ biện pháp để “làm hết lỗi compiler”.

## 46. Nested permitted types

Một sealed type có thể chứa nested permitted classes/interfaces và danh sách permits có thể dùng simple names trong phạm vi hợp lệ:

```java
public sealed interface QueryResult
        permits QueryResult.Success, QueryResult.Failure {

    record Success(String data) implements QueryResult {
    }

    record Failure(String message) implements QueryResult {
    }
}
```

Hai nested records là implicitly static và final; chúng trực tiếp implements QueryResult.

Cách tổ chức này giúp:
- Gom các variants vào một namespace.
- Giữ contract trực quan.
- Tránh đặt quá nhiều top-level types khi API nhỏ.
- Cho compiler kiểm tra subtype policy rõ.

### Chú ý visibility

Nested types trong interface được xử lý theo quy tắc modifier của interface members; không giả định nested type tự private. Nếu cần giấu details, chọn class-based container, factory và visibility phù hợp.

## 47. Runnable: nested record leaves

Lưu **`NestedSealedVariantsDemo.java`**:

```java
sealed interface Reply permits Reply.Ok, Reply.Error {
    record Ok(int value) implements Reply {
    }

    record Error(String message) implements Reply {
    }
}

public class NestedSealedVariantsDemo {
    public static void main(String[] args) {
        Reply first = new Reply.Ok(7);
        Reply second = new Reply.Error("bad");

        System.out.println(first);
        System.out.println(second);

        if (first instanceof Reply.Ok ok) {
            System.out.println(ok.value());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 NestedSealedVariantsDemo.java
java NestedSealedVariantsDemo
```

Stdout:

```text
Ok[value=7]
Error[message=bad]
7
```

`Reply.Ok`/`Reply.Error` là direct permitted record classes của sealed interface Reply, được final ngầm định. Không dùng `final interface`.

## 48. Kết hợp `sealed`, `final` và `non-sealed` theo từng tầng

Một mô hình hỗn hợp:

```text
sealed Root
├── final LeafA
├── sealed GroupB
│   ├── final LeafB1
│   └── non-sealed ExtensibleB2
│       ├── PluginB2a
│       └── PluginB2b
└── non-sealed ExtensionC
    └── ThirdPartyC
```

Root có ba direct permitted children. GroupB có hai direct permitted children. ExtensibleB2 và ExtensionC mở hai subtrees.

### Quan hệ cần nhớ

- `PluginB2a` không cần được Root.permits hoặc GroupB.permits liệt kê vì nó không trực tiếp extends hai sealed types đó.
- `LeafA` chặn subclassing.
- `GroupB` không cho arbitrary direct subclasses.
- `ExtensibleB2` cho phép ordinary descendants.
- `ExtensionC` tương tự.

Để đánh giá một type D mới có được thêm hay không, hãy đi từng **cạnh trực tiếp** trên class/interface hierarchy thay vì hỏi mơ hồ “Root có sealed không?”.

## 49. Hệ quả khi thiết kế public library API

Sealed hierarchy của một thư viện là một phần **public API contract**, không chỉ tài liệu: client modules không được tạo direct children ngoài permits; một nhánh `non-sealed` phải có access/constructor phù hợp nếu muốn làm extension point.

Các thay đổi như thêm direct variant, bỏ một leaf, đổi non-sealed thành sealed/final hoặc đổi constructor visibility có thể ảnh hưởng source/binary compatibility và consumer behavior. Trong code review, xác định **ai sở hữu thay đổi cây types** và **những nhánh được quyền mở**. Bài **So sánh hệ phân cấp đóng với lớp tự do mở rộng** phân tích chi tiết versioning, OCP, compatibility và migration cho public APIs.

## 50. Một lỗi API: chặn plugin ngoài module

Thư viện:

```java
public sealed interface Plugin permits BuiltInPlugin {
}

final class BuiltInPlugin implements Plugin {
}
```

Ứng dụng tiêu thụ muốn:

```java
// Compile-negative nếu không được permits:
public final class MyPlugin implements Plugin {
}
```

Không thể chỉ sửa `MyPlugin` thành `non-sealed` rồi xong; **Plugin không permits MyPlugin**, và package/module constraints vẫn còn.

Thiết kế mở rộng hợp lý hơn:

```java
public sealed interface Plugin
        permits BuiltInPlugin, ExternalPlugin {
}

final class BuiltInPlugin implements Plugin {
}

public non-sealed interface ExternalPlugin extends Plugin {
}
```

Đây là **snippet API design**; trong Java mỗi public top-level type cần source file riêng, và named-module visibility/accessibility phải được khai báo đúng. Client khác module có thể implement `ExternalPlugin` nếu type được export và accessible, không phải trực tiếp implements sealed Plugin.

## 51. Chọn `final` hay `sealed` hay `non-sealed`: cây quyết định

Với một **direct subtype của sealed parent**:

1. **Có cần bất kỳ subclass/implementation nào bên dưới type này không?**
   - Không → nếu là class, chọn **`final`** (hoặc record implicitly final).
   - Có → tiếp tục.
2. **Có thể liệt kê và duy trì được tập direct subtypes hợp lệ của type này không?**
   - Có → chọn **`sealed`**, xác định `permits`/inference.
   - Không, muốn một extension point → chọn **`non-sealed`**.
3. **Type này có phải interface không?**
   - Nếu là interface, **không có lựa chọn final**.
   - Chọn sealed hoặc non-sealed.
4. **Type này cần abstract behavior không?**
   - Có thể kết hợp `abstract sealed` hoặc `abstract non-sealed` đối với class.
5. **Public API có cho phép third-party extensions không?**
   - Nếu có, xem visibility/constructors/modules; non-sealed là cần nhưng chưa đủ.

Đừng chọn non-sealed chỉ vì ngại viết danh sách permits, nếu thật ra domain đòi hỏi một cây đóng hoàn toàn.

## 52. Điều gì xảy ra khi thêm subtype mới?

Thêm một direct child vào `State permits Active, Failed` nghĩa là khai child (chẳng hạn `Paused`) rồi cập nhật root `permits` nếu explicit; child phải mang extension policy hợp lệ. Ngoài source declaration còn phải xem business dispatch, serialization, tests và versioning.

Nếu `Paused` là child của một **non-sealed intermediate** đã được root permits, không cần thêm nó vào root whitelist. Nếu nó là child của một **sealed intermediate**, cập nhật `permits` của chính tầng giữa ấy. Quy tắc này là hệ quả trực tiếp của **direct vs indirect inheritance**, không phải một cơ chế tìm kiếm descendants tự động.

## 53. Rủi ro `instanceof` khi có non-sealed branch

Ví dụ:

```java
sealed interface Action permits BuiltIn, Custom {
}

record BuiltIn() implements Action {
}

non-sealed interface Custom extends Action {
}
```

Consumer xử lý:

```java
if (action instanceof BuiltIn) {
    // ...
} else if (action instanceof Custom) {
    // ...
}
```

Hai branches đại diện direct categories hiện tại, nhưng những Custom implementations có thể phát sinh thêm. Consumer không được giả định duy nhất một class `CustomImpl` đã biết. Hãy viết behavior dựa vào interface contract của `Custom` thay vì check tất cả concrete classes.

### Nếu code cần exhaustive cases thật sự

Tránh non-sealed ở đường này hoặc định nghĩa fallback/extension contract rõ. Pattern matching Java 17 với instanceof giúp cú pháp gọn nhưng **không chứng minh một nhánh non-sealed chỉ có hữu hạn concrete classes**.

## 54. Kết hợp sealed và visibility

Các vấn đề độc lập:
- **Sealed restriction**: kiểu nào được direct extends/implements?
- **Access control**: code tại nơi sử dụng có nhìn thấy class/constructor/member không?
- **Final restriction**: class cho phép subclass nào không?
- **Abstract restriction**: có instantiate trực tiếp được không?
- **Module encapsulation**: package/type có được exported/accessible không?

Một permitted subclass có thể package-private. Một public sealed interface có thể liệt kê permitted types mà callers không thể dùng trực tiếp bằng tên từ package khác. Các điều này không mâu thuẫn.

**Thực tế khi thiết kế API:** nếu caller chỉ cần xử lý qua sealed parent, có thể giấu concrete implementations và cung cấp factories. Nếu caller cần tự tạo một số variants, phải công bố constructors/factories phù hợp.

## 55. Lỗi về kế thừa nhầm tầng

Bảng kiểm:

| Dự định | Điều cần xác minh |
| --- | --- |
| Thêm direct child D của sealed S | D có trong S.permits/inference; cùng module/package theo JLS; D có modifier phù hợp |
| Thêm child của sealed intermediate T | T.permits/inference được cập nhật; T trực tiếp extends/implements S đúng quy tắc |
| Thêm child của non-sealed branch U | Không cần root permits cho indirect descendant; kiểm tra access/constructors |
| Đóng một nhánh bằng final | Không còn legal subclasses |
| Giữ nhánh kiểm soát bằng sealed | Danh sách permitted direct children của nhánh mới hợp lệ |
| Cho third-party extends/implements | Non-sealed branch có visibility/module/API tương ứng |
| Direct subinterface của sealed interface | Không dùng final; sealed/non-sealed |
| Direct record implementation | Record implicitly final; không thể extends sealed class |
| Một class thực hiện hai sealed interfaces | Cả hai interfaces permits class ấy nếu direct |
| Dùng anonymous subclass | Không được trực tiếp vượt sealed permits |

## 56. Bài tập 1 — Direct child không có modifier

```java
sealed class A permits B {
}

class B extends A {
}
```

**Đáp án:** Không biên dịch Java 17. `B` là direct permitted subclass nhưng phải chọn `final`/`sealed`/`non-sealed`.

## 57. Bài tập 2 — Đổi thành final

```java
sealed class A permits B {
}

final class B extends A {
}
```

**Đáp án:** Hợp lệ nếu scope/module/package phù hợp. B chặn subclassing tiếp.

## 58. Bài tập 3 — Thêm cháu của final

```java
sealed class A permits B {
}

final class B extends A {
}

class C extends B {
}
```

**Đáp án:** Không hợp lệ vì B final, bất kể A có sealed hay không.

## 59. Bài tập 4 — Non-sealed branch

```java
sealed class A permits B {
}

non-sealed class B extends A {
}

class C extends B {
}
```

**Đáp án:** Hợp lệ nếu constructors/access rules thỏa; C không cần được liệt kê trong A.permits.

## 60. Bài tập 5 — Sealed intermediate

```java
sealed class A permits B {
}

sealed class B extends A permits C {
}

final class C extends B {
}
```

**Đáp án:** Hợp lệ. B direct child A và cũng là sealed parent của C. C là indirect descendant A.

## 61. Bài tập 6 — Sealed intermediate thiếu children

`sealed class B extends A` nhưng không có permits và không có child nào để suy ra.

**Đáp án:** Không hợp lệ về sealed declaration nếu không có permitted direct subtype phù hợp. Nếu không cần subclasses, chọn `final class B`.

## 62. Bài tập 7 — `abstract sealed`

Một abstract class B trực tiếp extends sealed A. Có thể viết `abstract sealed class B extends A permits C` không?

**Đáp án:** Có. Abstract không mâu thuẫn sealed. C phải được phép trực tiếp extends B và có modifier phù hợp.

## 63. Bài tập 8 — `abstract non-sealed`

`abstract non-sealed class B extends A` khi A sealed permits B có hợp lệ không?

**Đáp án:** Có. B vừa chưa concrete vừa mở cho subclasses.

## 64. Bài tập 9 — `abstract final`

`abstract final class B extends A` có hợp lệ để làm direct child không?

**Đáp án:** Không. Abstract và final mâu thuẫn về khả năng subclassing.

## 65. Bài tập 10 — `final interface`

Một sealed interface A permits B, B là interface. B có thể `final interface B extends A` không?

**Đáp án:** Không. Interface không final; dùng sealed/non-sealed.

## 66. Bài tập 11 — Non-sealed interface

`sealed interface A permits B`, `non-sealed interface B extends A`.

**Đáp án:** Hợp lệ; B là extension point. Class implements B gián tiếp implements A không cần được A permits.

## 67. Bài tập 12 — Direct record

`sealed interface S permits R`, `record R(int x) implements S`.

**Đáp án:** Hợp lệ với scope phù hợp. R implicitly final, nên không cần một modifier final explicit.

## 68. Bài tập 13 — Record extends sealed class

`sealed class Base permits R`, `record R(int x) extends Base`.

**Đáp án:** Không hợp lệ vì record không thể extends một superclass do ứng dụng chọn.

## 69. Bài tập 14 — Hai sealed parents

Sealed interfaces A và B, class C implements A,B trực tiếp. A permits C nhưng B không.

**Đáp án:** C không hợp lệ vì thiếu direct permission của B. Mỗi sealed direct superinterface phải permits C.

## 70. Bài tập 15 — Permits cháu gián tiếp

A permits B; B non-sealed; C extends B. Có thêm C vào A.permits cho “đầy đủ” không?

**Đáp án:** Không. C không direct subtype của A nên không thuộc danh sách direct permitted subtypes của A.

## 71. Bài tập 16 — Non-sealed ở một ordinary class

`non-sealed class Plain { }` hợp lệ không?

**Đáp án:** Không. Non-sealed chỉ có ngữ cảnh khi type trực tiếp kế thừa/triển khai một sealed type phù hợp.

## 72. Bài tập 17 — Re-seal

A sealed permits B; B non-sealed; C sealed extends B permits D; D final extends C.

**Đáp án:** Hợp lệ. C tự thiết lập ranh giới sealed mới trong nhánh mở.

## 73. Bài tập 18 — Không mở rộng mọi module

Public sealed interface ở module M chỉ permits types trong M; code ở module N có được tự direct implements không?

**Đáp án:** Không. Muốn extension, cần một permitted non-sealed branch có API exported/accessible và tuân module rules.

## 74. Bài tập 19 — Unnamed module

Trong classpath/unnamed module, direct permitted subclasses có thể nằm bất kỳ package nào không?

**Đáp án:** Không; trong unnamed module, chúng phải ở **cùng package** với sealed parent.

## 75. Bài tập 20 — Named module

Trong named module, direct permitted subclasses phải cùng package hay cùng module?

**Đáp án:** Phải trong **cùng named module**. Chúng có thể ở package khác nếu Java visibility/import/module access rules cho phép.

## 76. Bài tập 21 — Permits inference

Sealed parent và tất cả direct subclasses khai báo trong cùng compilation unit, không có explicit permits. Có thể hợp lệ không?

**Đáp án:** Có, nếu JLS inference requirements đáp ứng và child modifiers hợp lệ.

## 77. Bài tập 22 — Inference không mở hoàn toàn

Nếu permits được inferred trong một file, class mới trong file khác có tự extends sealed parent được không?

**Đáp án:** Không. Inference không xóa restriction; phải thuộc permitted set theo quy tắc Java.

## 78. Bài tập 23 — Final class mutable

`final class Counter extends SealedParent` có `int count` thay đổi được không?

**Đáp án:** Có nếu code cho phép. Final khóa subclassing, không biến tất cả fields thành final.

## 79. Bài tập 24 — Non-sealed nhưng constructor private

Một non-sealed class chỉ có private constructors; third-party class không có private access có thể extends nó ngay không?

**Đáp án:** Không nhất thiết. Cần accessible constructor hợp lệ dù non-sealed đã mở nhánh.

## 80. Bài tập 25 — `instanceof` Java 17

`if (value instanceof Ok ok) { ... }` trên sealed Result có phải cần preview không?

**Đáp án:** Không. Instanceof pattern matching đã chuẩn trong Java 17.

## 81. Bài tập 26 — Pattern switch Java 17

`switch (result) { case Ok ok -> ... }` có mặc định biên dịch bằng `javac --release 17` không?

**Đáp án:** Không trong chế độ Java 17 không preview; pattern matching switch khi ấy là preview. Dùng instanceof/polymorphism hoặc lựa chọn Java version/cờ preview có chủ đích.

## 82. Bài tập 27 — Reflection

`Root.class.isSealed()` trả true; `NonSealedChild.class.isSealed()` trả gì?

**Đáp án:** False, vì child non-sealed không phải sealed type. `getPermittedSubclasses()` của Root mô tả các direct permitted types.

## 83. Bài tập 28 — Anonymous subclass

Tạo `new Root(){...}` với Root sealed nhưng anonymous child không thể được liệt kê hợp lệ trong permits. Có được không?

**Đáp án:** Không thể tự vượt sealed direct subclass restriction bằng anonymous class syntax.

## 84. Bài tập 29 — Hybrid library extension

Một thư viện muốn ba built-in variants cố định nhưng hỗ trợ third-party extensions. Nên thiết kế thế nào?

**Đáp án:** Sealed root permits các built-in final classes/records và một `non-sealed` extension interface/abstract class được export/access đúng; plugins mở rộng thông qua extension point thay vì implement sealed root trực tiếp.

## 85. Bài tập 30 — Đọc cây nhiều tầng

```text
sealed Root
├── sealed BranchA
│   ├── final Leaf1
│   └── non-sealed ExtensionA
└── final BranchB
```

Một class X extends ExtensionA, một class Y extends Leaf1, một class Z extends Root mà không permits.

**Đáp án:** X có thể hợp lệ theo access/constructor rules; Y sai vì Leaf1 final; Z sai vì Root không permits Z trực tiếp.

## 86. Bài tập 31 — Modifier nào phù hợp?

Một direct class child cần cho phép **chính xác hai** subclasses được team kiểm soát.

**Đáp án:** Chọn `sealed` và permits hai direct children; không chọn non-sealed hoặc final.

## 87. Bài tập 32 — Modifier nào phù hợp?

Một direct class child đại diện một biến thể dữ liệu cuối, không được subclass.

**Đáp án:** `final class` hoặc `record` khi dữ liệu phù hợp record semantics. Với interface child không có final.

## 88. Bài tập 33 — Modifier nào phù hợp?

Một direct subinterface cần third parties implement không giới hạn whitelist tại nhánh ấy.

**Đáp án:** `non-sealed interface`, với public API/module exports và method contract phù hợp.

## 89. Bài tập 34 — Đổi từ non-sealed sang sealed

Đổi public `non-sealed class Extension` thành sealed với một số subclasses được permits. Có thể phá API không?

**Đáp án:** Có. Existing subclasses từ phía clients có thể không còn compile/load hợp lệ; cần versioning và migration plan.

## 90. Bài tập 35 — Một interface extends hai sealed parents

Interface C extends sealed interfaces A và B trực tiếp. Có cần cả A và B permits C không?

**Đáp án:** Có. C cũng phải khai báo `sealed` hoặc `non-sealed` (interface không final).

## 91. Bài tập 36 — Câu hỏi tổng hợp Đúng/Sai

Đánh giá các câu:

1. `final` cho phép class được extend nếu parent đã permits.
2. `sealed` dùng để liệt kê một tập direct permitted subtypes.
3. `non-sealed` mở nhánh, nhưng không tự mở private constructors.
4. Mọi indirect descendant của sealed parent phải có trong root permits.
5. Record có thể trực tiếp implements sealed interface nếu được phép.
6. Interface có thể dùng `final` để khóa nhánh.
7. Sealed intermediate có thể có final leaves.
8. Non-sealed branch có thể bị sealed trở lại ở một descendant.
9. Non-sealed child của sealed parent có thể là abstract.
10. Java 17 hỗ trợ instanceof pattern matching không cần preview.

**Đáp án:** 1 sai; 2 đúng; 3 đúng; 4 sai; 5 đúng; 6 sai; 7 đúng; 8 đúng; 9 đúng; 10 đúng.

## 92. Lỗi thường gặp và giải pháp nhanh

| Nhận định/mã sai | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Direct class child không ghi modifier | Sealed parent buộc child chọn kế thừa policy | `final`/`sealed`/`non-sealed` |
| Direct interface child ghi final | Interface không final | Chọn `sealed` hoặc `non-sealed` |
| `abstract` là đủ cho direct child | Abstract không quyết định subclass openness | Thêm sealed hoặc non-sealed |
| `final sealed class Child` | Hai chính sách mâu thuẫn | Chọn một |
| `sealed non-sealed class Child` | Hai chính sách mâu thuẫn | Chọn một |
| `non-sealed class Plain` không có direct sealed parent | Modifier không hợp lệ ở vị trí này | Dùng ordinary class hoặc thay hierarchy |
| Non-sealed child có `permits` | Permits dành cho sealed declaration | Dùng sealed hoặc xóa permits |
| Root permits gián tiếp Grandchild | Permits chỉ liệt kê direct subtypes | Chỉ permits direct child |
| Subclass không nằm trong permits | Vi phạm sealed direct subtype restriction | Bổ sung hợp lệ hoặc extends nhánh non-sealed |
| Đổi `final` thành `non-sealed` để “chữa” compile | Có thể mở API ngoài ý muốn | Chọn theo domain contract |
| Record dùng `extends SealedClass` | Record không extends class tùy ý | Thiết kế sealed interface |
| Không có permitted children | Sealed cần direct subtype hợp lệ | Dùng final nếu không muốn child |
| Sealed class parent ở unnamed module, child khác package | Vi phạm same-package restriction | Đưa child về đúng package hoặc module design |
| Named-module child ở module khác | Vi phạm same-module restriction | Đổi module ownership hoặc extension point |
| `public sealed` nghĩa là mọi client implements trực tiếp | Public visibility khác permitted list | Non-sealed extension point |
| Final class tự immutable/thread-safe | Final chỉ chặn subclassing | Quản lý state/thread safety riêng |
| Reflection trả “mọi cháu” | Permits API trả direct subtypes | Duyệt hierarchy có chủ đích |
| Java17 pattern switch chạy mặc định | Switch pattern chưa stable trong Java17 | Dùng instanceof/polymorphism |
| Non-sealed mở nhánh nên mọi subclass đều hợp lệ | Constructors/access/module còn ràng buộc | Thiết kế accessible extension contract |

## 93. Checklist code review sealed subclasses

- [ ] Parent có đúng `sealed class` hoặc `sealed interface`?
- [ ] Các direct subtypes thực sự extends/implements trực tiếp?
- [ ] Explicit `permits` hoặc inference phản ánh chính xác direct children?
- [ ] Mỗi direct **class** child có `final`, `sealed` hoặc `non-sealed`?
- [ ] Direct **interface** children có `sealed` hoặc `non-sealed`, không final?
- [ ] Record leaf được hiểu là implicitly final?
- [ ] Nếu root sealed class, không cố dùng record extends root?
- [ ] Nếu nhiều direct sealed parents, tất cả đều permits child?
- [ ] Không thêm indirect grandchildren vào root permits?
- [ ] Không bỏ sót direct permitted child khi di chuyển files?
- [ ] Named-module children ở cùng module?
- [ ] Unnamed-module children ở cùng package?
- [ ] Accessibility và imports của supertypes/constructors hợp lệ?
- [ ] Không kết hợp final/sealed/non-sealed mâu thuẫn?
- [ ] Abstract child chọn sealed/non-sealed phù hợp?
- [ ] Sealed intermediate có children hợp lệ và không có cycle?
- [ ] Non-sealed branch được mở có chủ đích?
- [ ] Third-party extension point có API, constructors và module exports phù hợp?
- [ ] Đã đánh giá hậu quả việc mở nhánh đối với input validation/security?
- [ ] Đã tránh class names/visibility vô tình làm API khó sử dụng?
- [ ] Có trường hợp cần sealed lại bên dưới non-sealed branch không?
- [ ] Có dùng final leaf khi subtype không nên mở rộng?
- [ ] Nếu muốn immutable value variant, record components được thiết kế và kiểm tra phù hợp?
- [ ] `final` không bị hiểu nhầm là immutable/thread-safe?
- [ ] Người dùng API có xử lý indirect variants của nhánh non-sealed không?
- [ ] Nếu có type-based dispatch, fallback và subclass openness đã được tính?
- [ ] Java17 code không phụ thuộc switch pattern preview?
- [ ] Bài chạy bằng đúng JDK/source release Java 17?
- [ ] Tên public class khớp tên file ở từng ví dụ?
- [ ] Mọi compile-negative snippets được tách khỏi runnable programs?
- [ ] Kiểm thử thêm/bỏ subtype phù hợp domain contract?
- [ ] Kiểm thử regression khi đổi non-sealed/final/sealed policy?
- [ ] Nếu là thư viện, đã rà soát source/binary compatibility và module boundaries?
- [ ] Có document chính sách “đóng hay mở” tại từng nhánh quan trọng?
- [ ] Có giữ đúng ý nghĩa direct vs indirect subtype trong code review?

## 94. Tổng kết: ba hướng đi của một lớp con trực tiếp

**`final`** trả lời: “Nhánh này dừng ở đây.”  
**`sealed`** trả lời: “Nhánh này còn mở rộng, nhưng chỉ theo danh sách con mà tôi kiểm soát.”  
**`non-sealed`** trả lời: “Từ nhánh này trở xuống, tôi không áp sealed whitelist; Java inheritance/access rules bình thường quyết định.”

Quy tắc này áp dụng tại **mỗi nút là direct subtype của một sealed parent**. Sealed parent chỉ quy định *direct* children, không tự đóng mọi descendants nếu một nhánh chọn non-sealed. Sealed interfaces có thể có direct subinterfaces sealed/non-sealed; class leaves có thể final; record leaves implicitly final.

Khi thiết kế domain:
- Dùng **final leaves** cho các biến thể cuối.
- Dùng **sealed intermediate** khi cần một nhóm con vẫn đóng.
- Dùng **non-sealed extension point** khi chủ động cho bên ngoài tiếp tục kế thừa.
- Kết hợp các lựa chọn này để vừa giữ invariant quan trọng vừa mở đúng vị trí cần mở.

**Cách nhớ:** Hãy nhìn *mỗi cạnh trực tiếp* trong cây kế thừa. Tổ tiên sealed không cấm con cháu gián tiếp của một nhánh non-sealed; nó chỉ kiểm soát những ai được bước qua cạnh đầu tiên.

## Tài liệu Java SE 17 chính thức

- **Java Language Specification `8.1.1.2 — `sealed`, `non-sealed`, `final` class modifiers**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2
- **JLS `8.1.4 — Superclasses and Subclasses**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.4
- **JLS `9.1.1.4 — Sealed Interfaces**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4
- **JLS `13.4 — Evolution of Classes and Interfaces**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html#jls-13.4
- **Java SE 17 `Class.isSealed()`/`getPermittedSubclasses()` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
