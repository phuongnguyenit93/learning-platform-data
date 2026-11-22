# Điều kiện suy ra danh sách lớp con khi bỏ `permits` trong Java `sealed`

## 1. Câu hỏi trung tâm

Java 17 cho phép khai báo lớp hoặc interface **`sealed`** để giới hạn những kiểu nào được trực tiếp kế thừa hay triển khai nó. Ta có thể ghi rõ danh sách con trong `permits`:

```java
sealed interface Message permits TextMessage, ImageMessage {
}

record TextMessage(String text) implements Message {
}

record ImageMessage(String path) implements Message {
}
```

Nhưng khi những kiểu con trực tiếp được khai báo **trong cùng một compilation unit**, ta có thể bỏ mệnh đề `permits`:

```java
sealed interface Message {
}

record TextMessage(String text) implements Message {
}

record ImageMessage(String path) implements Message {
}
```

Hai đoạn trên là **các phương án khai báo minh họa độc lập**, không đặt cả hai vào cùng một file.

**Điều kiện suy ra cốt lõi:** Khi `sealed` type **không ghi `permits`**, Java suy ra danh sách được phép từ những **kiểu con trực tiếp**, **có canonical name**, **được khai báo trong cùng compilation unit** với kiểu sealed. Nếu không tìm được kiểu con trực tiếp phù hợp, khai báo sealed thiếu `permits` sẽ là **lỗi biên dịch** (trừ cơ chế đặc biệt dành cho enum, không phải sealed class/interface thông thường mà bài này khảo sát).

Nói ngắn gọn:

- **Cùng file nguồn/compilation unit:** cần cho suy ra.
- **Quan hệ kế thừa hoặc triển khai trực tiếp:** cần cho suy ra.
- **Kiểu con có canonical name:** cần cho suy ra.
- **Kiểu con khai báo `final`, `sealed` hoặc `non-sealed` phù hợp:** vẫn bắt buộc theo luật sealed hierarchy.
- **Cùng package hay cùng module nhưng khác file:** chưa đủ để tự suy ra.
- **Lớp con gián tiếp, local class và anonymous class:** không tự được suy ra.

Bài này giải thích điều kiện từng bước, ví dụ Java 17+ biên dịch được, các trường hợp cố tình sai, đối chiếu explicit/inferred `permits`, phạm vi package/module và cách kiểm tra ở runtime.

## 2. Phân biệt sealed class, sealed interface và `permits`

Ví dụ sealed class:

```java
sealed abstract class Shape permits Circle, Rectangle {
}

final class Circle extends Shape {
}

final class Rectangle extends Shape {
}
```

Ví dụ sealed interface:

```java
sealed interface Command permits Start, Stop {
}

record Start() implements Command {
}

record Stop() implements Command {
}
```

Cả hai là **mảnh khai báo minh họa**.

- `sealed class` giới hạn các **direct subclasses** có thể `extends` class.
- `sealed interface` giới hạn các **direct subclasses/direct subinterfaces** có thể trực tiếp `implements` hoặc `extends` interface.
- `permits` là danh sách **kiểu con trực tiếp được phép**, không phải danh sách mọi loại hậu duệ.
- Khi **không có `permits`**, compiler suy ra danh sách nếu đủ điều kiện.
- Khi **đã có `permits`**, compiler lấy danh sách **được liệt kê tường minh**, không tự gộp thêm mọi kiểu cùng file.

**Điểm quan trọng:** Bỏ `permits` không đồng nghĩa sealed trở thành một class hoặc interface tự do cho mọi kiểu con kế thừa. Kiểu sealed **vẫn bị đóng về danh sách các con trực tiếp**.

## 3. Ví dụ đầy đủ: compiler suy ra hai lớp con trực tiếp

Tạo tệp **`InferredPermitsClassDemo.java`**:

```java
sealed abstract class Shape {
    abstract int area();
}

final class Square extends Shape {
    private final int side;

    Square(int side) {
        this.side = side;
    }

    @Override
    int area() {
        return side * side;
    }
}

final class Rectangle extends Shape {
    private final int width;
    private final int height;

    Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }

    @Override
    int area() {
        return width * height;
    }
}

public class InferredPermitsClassDemo {
    public static void main(String[] args) {
        Shape first = new Square(3);
        Shape second = new Rectangle(2, 5);

        System.out.println(first.area());
        System.out.println(second.area());
    }
}
```

```bash
javac InferredPermitsClassDemo.java
java InferredPermitsClassDemo
```

```text
9
10
```

Ở đây compiler suy ra `Square` và `Rectangle` vì:

1. `Shape` được khai báo là `sealed`.
2. Khai báo Shape không viết `permits`.
3. `Square` và `Rectangle` được khai báo **trong cùng tệp Java** với Shape.
4. Cả hai có canonical names vì là top-level classes.
5. Cả hai đều `extends Shape` **trực tiếp**.
6. Cả hai là `final`, thỏa một lựa chọn hợp lệ về modifier của direct subclass.

**Không phải nhờ cùng package ngầm định:** Dù cùng tệp đương nhiên cùng package, chính **cùng compilation unit** là điều kiện then chốt của suy ra.

## 4. Ví dụ đầy đủ: sealed interface không có `permits`

Tạo tệp **`InferredPermitsInterfaceDemo.java`**:

```java
sealed interface PaymentResult {
    String description();
}

record Paid(String reference) implements PaymentResult {
    @Override
    public String description() {
        return "paid:" + reference;
    }
}

record Declined(String reason) implements PaymentResult {
    @Override
    public String description() {
        return "declined:" + reason;
    }
}

public class InferredPermitsInterfaceDemo {
    public static void main(String[] args) {
        PaymentResult a = new Paid("TX-7");
        PaymentResult b = new Declined("limit");

        System.out.println(a.description());
        System.out.println(b.description());
    }
}
```

```bash
javac InferredPermitsInterfaceDemo.java
java InferredPermitsInterfaceDemo
```

```text
paid:TX-7
declined:limit
```

Compiler nhận diện `Paid` và `Declined` là **hai lớp trực tiếp implement `PaymentResult`**, có canonical names và khai báo cùng compilation unit.

**Vì sao `record` dùng được?** Record class mặc định là `final` nên có thể làm một direct permitted implementation của sealed interface. Record chỉ cần khai báo `implements PaymentResult` và cung cấp method interface yêu cầu.

Sealed **interface** có thể có cả direct implementing classes và direct extending interfaces. Điều kiện suy ra xét cả hai loại đó, không chỉ `record`.

## 5. “Compilation unit” là gì trong tình huống thông thường?

Một **ordinary compilation unit** tương ứng một tệp nguồn Java chứa các khai báo top-level và có thể chứa nested types. Ví dụ tệp `Workflow.java` có:

```java
sealed interface Workflow {
}

final class Manual implements Workflow {
}

final class Automated implements Workflow {
}
```

Ba kiểu khai báo trong cùng file nguồn nên phù hợp điều kiện **cùng compilation unit**.

### Điều không đủ

Hai files trong **cùng thư mục/package**:

```text
src/example/Workflow.java
src/example/Manual.java
```

không phải cùng compilation unit. Khi Workflow bỏ `permits`, compiler không tự tìm Manual từ file khác rồi bổ sung vào danh sách, kể cả build system compile cả hai files cùng lúc.

**Cẩn thận từ ngữ:** “Cùng một lần chạy `javac`” không đồng nghĩa “cùng compilation unit”. Lệnh `javac A.java B.java` nạp hai compilation units khác nhau, không gộp chúng thành một.

## 6. Cùng package nhưng khác file vẫn cần `permits` tường minh

Giả sử thiết kế đặt sealed interface và implementations vào ba file trong package `demo`:

```text
demo/
  Operation.java
  Add.java
  Subtract.java
```

Tệp **`demo/Operation.java`**:

```java
package demo;

public sealed interface Operation permits Add, Subtract {
    int apply(int a, int b);
}
```

Tệp **`demo/Add.java`**:

```java
package demo;

public final class Add implements Operation {
    @Override
    public int apply(int a, int b) {
        return a + b;
    }
}
```

Tệp **`demo/Subtract.java`**:

```java
package demo;

public final class Subtract implements Operation {
    @Override
    public int apply(int a, int b) {
        return a - b;
    }
}
```

Đặt trong thư mục gốc chứa folder `demo`, biên dịch:

```bash
javac demo/Operation.java demo/Add.java demo/Subtract.java
```

Bộ ba files này **biên dịch hợp lệ** trên Java 17+. Tên `Add` và `Subtract` có thể được liệt kê trong `permits` vì là direct implementations, accessible, cùng package trong unnamed module.

Nếu xóa `permits Add, Subtract` khỏi `Operation.java` mà không chuyển declarations con vào **cùng compilation unit**, code không còn thỏa điều kiện suy ra. Compiler không dùng “hai classes đã có sẵn trong package” để suy ra.

**Phân biệt:** Quy tắc co-location theo package/module dành cho quan hệ permitted nói chung **không thay thế** quy tắc co-location theo compilation unit dành riêng cho **bỏ `permits`**.

## 7. Một compilation unit có thể chứa nhiều top-level types

Java cho phép một file chứa nhiều top-level declarations, miễn tuân thủ quy tắc tên file cho top-level `public` type.

Tạo **`ManyTopLevelTypesDemo.java`**:

```java
sealed interface Message {
}

final class Text implements Message {
}

final class Image implements Message {
}

final class Video implements Message {
}

public class ManyTopLevelTypesDemo {
    public static void main(String[] args) {
        Message message = new Video();

        System.out.println(message instanceof Video);
        System.out.println(Message.class.isSealed());
    }
}
```

```bash
javac ManyTopLevelTypesDemo.java
java ManyTopLevelTypesDemo
```

```text
true
true
```

Ba classes `Text`, `Image`, `Video` đều được suy ra là permitted. Chúng là top-level non-public types cùng compilation unit với Message. Không cần viết `permits Text, Image, Video`.

**Lưu ý tổ chức code:** Việc nhiều top-level classes chung file là hợp lệ, không có nghĩa luôn tốt cho bảo trì. Nếu mỗi implementation lớn và cần file riêng, dùng explicit `permits` là rõ ràng và có thể cần thiết.

## 8. Kiểu lồng (*member nested type*) cũng có thể được suy ra

Một nested class có **canonical name**, ví dụ `Envelope.Letter`, nếu là member class được khai báo hợp lệ. Nó có thể nằm trong cùng compilation unit và trực tiếp implement sealed interface.

Tạo **`NestedPermittedTypesDemo.java`**:

```java
sealed interface Message {
}

public class NestedPermittedTypesDemo {
    static final class Text implements Message {
    }

    static final class Binary implements Message {
    }

    public static void main(String[] args) {
        Message a = new Text();
        Message b = new Binary();

        System.out.println(a instanceof Text);
        System.out.println(b instanceof Binary);
    }
}
```

```bash
javac NestedPermittedTypesDemo.java
java NestedPermittedTypesDemo
```

```text
true
true
```

Mặc dù `Text`, `Binary` không phải top-level classes, chúng là **member nested classes** có canonical names, trong cùng compilation unit và trực tiếp implement Message. Do đó chúng được suy ra.

**Không rút gọn quy tắc thành “chỉ lớp top-level cùng file”.** Đúng hơn: các kiểu có canonical name, thuộc cùng compilation unit và có quan hệ direct subclass/subinterface tương ứng.

## 9. Kiểu con có thể được khai báo ngay bên trong sealed type

Tạo **`NestedInsideSealedDemo.java`**:

```java
sealed interface Event {
    record Started(String id) implements Event {
    }

    record Finished(String id) implements Event {
    }
}

public class NestedInsideSealedDemo {
    public static void main(String[] args) {
        Event first = new Event.Started("A");
        Event second = new Event.Finished("A");

        System.out.println(first);
        System.out.println(second);
    }
}
```

```bash
javac NestedInsideSealedDemo.java
java NestedInsideSealedDemo
```

```text
Started[id=A]
Finished[id=A]
```

Hai record `Event.Started` và `Event.Finished` được khai báo trong body của sealed interface, nằm trong cùng compilation unit, có canonical names và implement trực tiếp Event.

**Tại sao ví dụ này có lợi?** Người đọc thấy trọn tập variants ở gần khai báo parent. Đây là trường hợp bỏ `permits` thường làm file rất dễ hiểu.

Nested record là implicitly static theo Java, không capture một Event object; nó là một type declaration riêng implement interface Event.

## 10. Sealed class có thể có nested final classes

Tạo **`SealedClassNestedChildrenDemo.java`**:

```java
sealed abstract class Result {
    abstract String text();

    static final class Success extends Result {
        @Override
        String text() {
            return "SUCCESS";
        }
    }

    static final class Failure extends Result {
        @Override
        String text() {
            return "FAILURE";
        }
    }
}

public class SealedClassNestedChildrenDemo {
    public static void main(String[] args) {
        Result a = new Result.Success();
        Result b = new Result.Failure();

        System.out.println(a.text());
        System.out.println(b.text());
    }
}
```

```bash
javac SealedClassNestedChildrenDemo.java
java SealedClassNestedChildrenDemo
```

```text
SUCCESS
FAILURE
```

Hai nested classes có canonical names `Result.Success` và `Result.Failure`, cùng compilation unit, `extends Result` trực tiếp, nên được suy ra.

**Đừng lẫn access modifier với suy ra:** Dù một member class có thể private/package-private/public tùy ngữ cảnh, điều kiện quan trọng ở đây là type khai báo hợp lệ và có canonical name, không phải mọi child đều phải là public top-level class.

## 11. “Con trực tiếp” của class có nghĩa chính xác gì?

Với:

```java
sealed class Base {
}

non-sealed class Middle extends Base {
}

final class End extends Middle {
}
```

Ba declarations này hợp lệ nếu ở cùng compilation unit và Base không có `permits`.

**Danh sách được suy ra của Base chỉ chứa `Middle`.**

- `Middle extends Base` → direct subclass.
- `End extends Middle` → indirect subclass of Base.
- `End` không phải direct child của Base, nên không được thêm vào inferred permitted set.

Điều này vẫn đúng dù cả ba nằm cùng file.

### Vì sao cần phân biệt?

`sealed` giới hạn **điểm rẽ trực tiếp** từ parent. Nếu một child là `non-sealed`, nhánh con phía dưới có thể mở rộng bình thường. Nếu child là `sealed`, nó tiếp tục giới hạn các direct subclasses của chính nó.

## 12. Runnable: trực tiếp được suy ra, gián tiếp không được suy ra

Tạo **`DirectVersusIndirectDemo.java`**:

```java
sealed abstract class Base {
}

non-sealed class Middle extends Base {
}

final class Leaf extends Middle {
}

public class DirectVersusIndirectDemo {
    public static void main(String[] args) {
        Base value = new Leaf();

        System.out.println(value instanceof Middle);
        System.out.println(value instanceof Leaf);
    }
}
```

```bash
javac DirectVersusIndirectDemo.java
java DirectVersusIndirectDemo
```

```text
true
true
```

Cả Middle và Leaf là instances/subtypes liên quan tới Base theo inheritance chain. Nhưng **permitted direct subclasses** của Base chỉ là Middle. Leaf không cần được cấp phép trực tiếp bởi Base vì nó `extends Middle`, và Middle là non-sealed.

**Lưu ý:** Một subtype gián tiếp không tự động vi phạm sealed contract. Điều phải kiểm là **mỗi direct inheritance edge** đi qua một sealed parent có được phép hay không.

## 13. Với sealed interface, cả class và interface có thể là con trực tiếp

Tạo **`SealedInterfaceMixedChildrenDemo.java`**:

```java
sealed interface Resource {
}

final class LocalResource implements Resource {
}

non-sealed interface RemoteResource extends Resource {
}

final class HttpResource implements RemoteResource {
}

public class SealedInterfaceMixedChildrenDemo {
    public static void main(String[] args) {
        Resource local = new LocalResource();
        Resource remote = new HttpResource();

        System.out.println(local instanceof LocalResource);
        System.out.println(remote instanceof RemoteResource);
    }
}
```

```bash
javac SealedInterfaceMixedChildrenDemo.java
java SealedInterfaceMixedChildrenDemo
```

```text
true
true
```

Compiler suy ra `LocalResource` (class implements Resource trực tiếp) và `RemoteResource` (interface extends Resource trực tiếp). `HttpResource` chỉ implements RemoteResource trực tiếp, nên không cần xuất hiện trong inferred permitted set của Resource.

**Phân biệt:** `non-sealed interface` có thể mở lại nhánh cho implementations tiếp theo. Nó vẫn phải là một direct permitted subinterface hợp lệ của Resource.

## 14. Direct implementation không phụ thuộc việc class còn extends class khác

Một class có thể vừa `extends` một superclass thường vừa `implements` sealed interface trực tiếp. Khi đó nó vẫn là **direct subclass theo quan hệ interface**.

Ví dụ:

```java
sealed interface Tag {
}

class BaseObject {
}

final class TaggedObject extends BaseObject implements Tag {
}
```

Đây là **khai báo hợp lệ**, nếu cùng compilation unit.

`TaggedObject` không extends Tag (Tag là interface), nhưng `implements Tag` **trực tiếp**, nên nó được suy ra khi Tag bỏ permits. Việc nó còn extends BaseObject không làm Tag trở thành quan hệ gián tiếp.

Với sealed **class**, compiler xét direct superclass đúng tên sealed class; một interface implementer không phải direct subclass của sealed class.

## 15. “Canonical name” là gì và vì sao cần?

Một named top-level class có canonical name như `package.Type`. Một member nested type có canonical name như `package.Outer.Nested`.

Ngược lại:

- **Local class** khai báo trong method/block không có canonical name.
- **Anonymous class** tạo bằng `new SomeType() { ... }` không có canonical name.
- Local interface (trong những ngữ cảnh Java hiện đại cho phép) cũng không có canonical name.

Khi không có permits, các types không có canonical name **không thể thuộc inferred permitted set**.

### Điều này không chỉ là giới hạn nhìn thấy tên

Local class có thể có một tên đơn giản trong block, ví dụ `Local`. Nhưng **simple name không phải canonical name**. Điều kiện của JLS là canonical name, không phải “có chữ để gõ trong method”.

## 16. Tại sao local class không được tự suy ra?

Đây là **mã cố tình sai**, không biên dịch:

```java
sealed interface Task {
}

class Factory {
    static Task create() {
        final class LocalTask implements Task {
        }

        return new LocalTask();
    }
}
```

`LocalTask` được khai báo trong method, không có canonical name. Nó không thể trở thành permitted direct implementation chỉ nhờ xuất hiện trong cùng file.

Ngoài ra `Task` không có bất kỳ permitted direct implementation hợp lệ nào khác, nên bản thân sealed declaration thiếu permits cũng lỗi.

**Cách sửa:** Dùng top-level hoặc member nested type có canonical name, hoặc chọn design interface không sealed nếu cần implementation cục bộ linh hoạt.

## 17. Anonymous class cũng không được phép lách điều kiện

Mã sau **cố ý sai**:

```java
sealed interface Task {
    void run();
}

class Factory {
    static Task create() {
        return new Task() {
            @Override
            public void run() {
                System.out.println("RUN");
            }
        };
    }
}
```

Anonymous class không có canonical name, không thể được suy ra từ cùng compilation unit và không được ghi tên hợp lệ vào `permits`.

**Không nên suy rằng:** “Nếu bỏ `permits` thì mọi anonymous implementation cùng file được phép.” Ngược lại, sealed là giới hạn chủ đích, và anonymous implementation không đáp ứng permitted direct type rules.

Nếu muốn callback implementation một lần, có thể dùng một class/record có tên được permitted, rồi khởi tạo class ấy; nếu domain cần vô số anonymous implementations, reconsider sealed interface.

## 18. Nếu không có con trực tiếp phù hợp thì compiler báo lỗi

Đoạn này **cố ý sai**:

```java
sealed interface EmptyHierarchy {
}
```

Không có `permits` và không có subtype phù hợp trong cùng compilation unit. Compiler từ chối vì không thể suy ra nonempty permitted direct set.

Tương tự với:

```java
sealed class Lonely {
}
```

Lớp sealed thông thường (không phải trường hợp enum đặc biệt) thiếu permits và không có direct subclasses hợp lệ là **lỗi compile-time**.

### Đúng cách nếu muốn cấm hoàn toàn subclass

Nếu bạn chỉ cần một class **không có bất kỳ subclass nào**, hãy dùng `final class` thay vì sealed class không có permitted child:

```java
final class NoSubclasses {
}
```

Nếu cần một sealed hierarchy thực sự, khai báo ít nhất một direct permitted type tương ứng.

## 19. Modifier của direct permitted child vẫn bắt buộc

Bỏ `permits` chỉ bỏ phần **liệt kê tên**. Nó không bỏ yêu cầu direct permitted subclass/subinterface thể hiện rõ chính sách tiếp tục kế thừa.

Một direct permitted **class** thường phải là một trong:

- `final`: cấm subclass thêm.
- `sealed`: tiếp tục đóng danh sách direct children.
- `non-sealed`: mở lại quyền subclass theo các quy tắc thường.

Với direct permitted **interface**, dùng `sealed` hoặc `non-sealed` (interface không được là `final`).

Nếu direct child là record, record là final nên đáp ứng chính sách đóng nhánh.

**Chú ý:** `abstract` không thay thế `sealed`/`non-sealed` trong direct permitted subtype khi quy tắc yêu cầu modifier chính sách; có thể kết hợp abstract với sealed hoặc non-sealed ở class nếu hợp lệ.

## 20. Lỗi khi quên `final`/`sealed`/`non-sealed`

Đây là **mã sai có chủ đích**:

```java
sealed class Parent {
}

class Child extends Parent {
}
```

Dù Child nằm trong cùng compilation unit và được suy ra về mặt tên, nó **không công bố chính sách mở rộng** mà Java yêu cầu cho direct permitted class.

Sửa:

```java
sealed class Parent {
}

final class Child extends Parent {
}
```

Đây là **hai phương án riêng**, không khai báo trùng trong cùng source.

Hoặc dùng `non-sealed class Child extends Parent` nếu thực sự muốn cho các descendants khác mở rộng dưới Child, hay `sealed class Child` nếu Child tiếp tục đóng nhánh với direct subclasses hợp lệ riêng.

## 21. Inference và chuỗi `sealed -> sealed -> final`

Tạo **`MultiLevelSealedDemo.java`**:

```java
sealed abstract class Root {
    abstract String label();
}

sealed abstract class Branch extends Root {
}

final class LeafA extends Branch {
    @Override
    String label() {
        return "A";
    }
}

final class LeafB extends Branch {
    @Override
    String label() {
        return "B";
    }
}

public class MultiLevelSealedDemo {
    public static void main(String[] args) {
        Root a = new LeafA();
        Root b = new LeafB();

        System.out.println(a.label());
        System.out.println(b.label());
    }
}
```

```bash
javac MultiLevelSealedDemo.java
java MultiLevelSealedDemo
```

```text
A
B
```

Có **hai quá trình suy ra khác nhau**:

- `Root` không có permits, suy ra **Branch** vì Branch trực tiếp extends Root.
- `Branch` không có permits, suy ra **LeafA, LeafB** vì chúng trực tiếp extends Branch.

Root **không trực tiếp permit LeafA và LeafB**. Nhưng Root references vẫn có thể trỏ LeafA/LeafB objects vì chúng là indirect descendants qua Branch được phép.

**Một hierarchy có nhiều tầng sealed cần xem từng cạnh trực tiếp**, không lập một danh sách phẳng tất cả classes cuối cùng.

## 22. Nếu direct child là `non-sealed` thì nhánh đó mở ra

Tạo **`NonSealedBranchDemo.java`**:

```java
sealed interface Device {
}

non-sealed class Computer implements Device {
}

final class Laptop extends Computer {
}

public class NonSealedBranchDemo {
    public static void main(String[] args) {
        Device device = new Laptop();

        System.out.println(device instanceof Computer);
        System.out.println(device instanceof Laptop);
    }
}
```

```bash
javac NonSealedBranchDemo.java
java NonSealedBranchDemo
```

```text
true
true
```

Compiler suy ra `Computer` là direct permitted implementation của Device. `Laptop` không direct implements Device; nó inherits Device through Computer. Vì Computer là `non-sealed`, nó cho phép mở rộng theo quy tắc ordinary inheritance.

**Không có mâu thuẫn:** Device vẫn sealed dù gián tiếp có nhiều implementations đi qua non-sealed branch. Sealed chỉ kiểm các direct children của từng sealed type.

## 23. Một direct implementation trong cùng file là đủ, không cần cùng block

Điều kiện là cùng **compilation unit**, không nhất thiết declarations phải sát nhau hoặc cùng lexical block.

Ví dụ:

```java
sealed interface Signal {
}

class Holder {
    static final class On implements Signal {
    }
}

final class Off implements Signal {
}
```

Ở đây `Holder.On` và `Off` đều là named types có canonical name, cùng compilation unit, direct implements Signal. Cả hai được suy ra dù một cái lồng trong Holder, một cái là top-level.

**Điểm cần nhớ:** Không phải “gần khai báo sealed trong source” mới được phép; compiler xét tập declarations trong cùng compilation unit đáp ứng chính xác điều kiện.

## 24. Không phải mọi class cùng file đều nằm trong danh sách inferred

Giả sử có:

```java
sealed interface Command {
}

final class Start implements Command {
}

final class Other {
}

final class ExtendedStart {
}
```

Chỉ `Start` là direct implementation của Command. `Other` và `ExtendedStart` không extends/implements Command, nên không được suy ra.

Compiler không lập danh sách mọi named class cùng file. Nó lọc theo **quan hệ kế thừa/triển khai trực tiếp**.

## 25. Có `permits` rõ thì inferred set không được cộng thêm

Đây là **mã sai có chủ đích**:

```java
sealed interface Choice permits A {
}

final class A implements Choice {
}

final class B implements Choice {
}
```

B mặc dù cùng compilation unit, có canonical name và trực tiếp implements Choice, nhưng **không được ghi trong explicit permits**. Compiler từ chối B.

Nếu muốn B được phép, sửa declaration thành:

```java
sealed interface Choice permits A, B {
}
```

Hoặc **bỏ toàn bộ permits clause** khi A, B đều ở cùng compilation unit; compiler khi ấy suy ra cả hai.

**Không nhầm hai chế độ:** Không ghi permits thì infer từ cùng unit. Có permits thì dùng explicit list, không tự mở rộng.

## 26. `permits` không được liệt kê một subtype gián tiếp

Mã sau **sai**:

```java
sealed class Root permits Leaf {
}

non-sealed class Branch extends Root {
}

final class Leaf extends Branch {
}
```

`Leaf` là indirect subclass của Root, nên không thể được liệt kê như **direct permitted subclass** của Root. Nếu Root muốn đóng nhánh Branch, khai báo:

```java
sealed class Root permits Branch {
}

non-sealed class Branch extends Root {
}

final class Leaf extends Branch {
}
```

Nếu ba declarations trong cùng compilation unit, còn có thể bỏ `permits Branch` để compiler suy ra Branch. `Leaf` vẫn không nằm trong direct permitted set.

**Tại sao cần chính xác?** `permits` không phải danh sách “mọi lớp có thể tồn tại dưới root”. Nó mô tả **các đường đi trực tiếp** được mở từ một sealed node.

## 27. Khác biệt sealed class và sealed interface khi suy ra

| Nội dung | Sealed class | Sealed interface |
| --- | --- | --- |
| Cú pháp khai báo | `sealed class C` | `sealed interface I` |
| Quan hệ trực tiếp được xét | `extends C` | `implements I` hoặc `extends I` trực tiếp |
| Kiểu con có thể có | Classes | Classes và subinterfaces |
| Không có permits | Suy ra direct classes trong cùng compilation unit có canonical name | Suy ra direct classes/interfaces trong cùng compilation unit có canonical name |
| Không có direct subtype phù hợp | Lỗi compile-time (normal sealed class) | Lỗi compile-time |
| Local/anonymous types | Không được suy ra | Không được suy ra |
| Con gián tiếp | Không được suy ra vào set trực tiếp | Không được suy ra vào set trực tiếp |
| Modifier của direct child | `final` / `sealed` / `non-sealed` | Classes: tương tự; interfaces: `sealed` / `non-sealed` |
| Thêm subtype từ khác compilation unit mà vẫn bỏ permits | Không | Không |

Bảng này dành cho **ordinary sealed class/interface của Java 17+**. Enum có quy tắc riêng về constant-specific classes và ngữ nghĩa final/sealed ngầm, không phải trường hợp điển hình của `sealed class ...` trong bài này.

## 28. Package và module: hai lớp điều kiện khác nhau

Java còn ràng buộc location của direct permitted types:

- Nếu sealed type thuộc **named module**, permitted direct types phải ở **cùng module**.
- Nếu sealed type thuộc **unnamed module**, permitted direct types phải ở **cùng package**.

Nhưng đối với việc **bỏ permits**, cần mạnh hơn: **cùng compilation unit**. Cùng module/package không thể tự thay thế.

### Ví dụ khái niệm

```text
module app.core
  package app.core.model
    Result.java
    Success.java
    Failure.java
```

Giả sử cả ba classes thuộc named module `app.core`. Việc cùng module chỉ làm chúng **có khả năng** thỏa điều kiện module-level của explicit permits. Khi Result, Success, Failure ở **ba compilation units**, Result không thể bỏ permits rồi hy vọng compiler tự suy ra qua toàn module.

**Cách tốt:** Giữ `sealed interface Result permits Success, Failure` trong file của Result hoặc chuyển direct descendants vào cùng compilation unit nếu muốn infer.

## 29. “Compile cùng lúc” không làm nhiều source files thành một compilation unit

Một hiểu nhầm thường gặp:

> Tôi đã chạy `javac Root.java Child.java`, vậy compiler có thể suy ra Child cho Root không?

**Không.** Javac nhận nhiều source files trong cùng invocation không thay đổi ranh giới **compilation unit** của từng tệp.

Ví dụ:

```text
Root.java
Child.java
```

`Root.java`:

```java
sealed interface Root {
}
```

`Child.java`:

```java
final class Child implements Root {
}
```

Đây là **hai tệp của một ví dụ cố tình sai**, vì Root thiếu direct subtypes **trong chính Root.java**.

Sửa `Root.java`:

```java
sealed interface Root permits Child {
}
```

Giữ `Child.java` như trước; cùng package (unnamed module) và explicit permits cho Child thì compile được.

**Không được đồng nhất** các khái niệm “cùng compilation”, “cùng thư mục”, “cùng module” và “cùng compilation unit”.

## 30. Điều kiện `canonical name` loại local/anonymous types ngay cả khi cùng source

Một local class có thể có một **simple name**, ví dụ `Worker` trong method:

```java
void create() {
    class Worker {
    }
}
```

Nhưng nó không có canonical name theo Java. Anonymous class còn không có simple source-level class name.

Vì vậy:

- Same file: **có**.
- Direct `implements SealedInterface`: có thể viết cố gắng.
- Có canonical name: **không**.
- Kết quả: **không đủ điều kiện suy ra** và việc trực tiếp kế thừa sealed type không được cho phép.

Đây là điểm phân biệt **lexical name** với **canonical name**; không chỉ đơn giản là “compiler chưa nhìn thấy kiểu”.

## 31. Khi muốn local implementation, có những cách thiết kế nào?

Nếu logic chỉ sử dụng trong một method, nhưng parent sealed interface yêu cầu permitted named type, cân nhắc:

1. Khai báo **private static nested class** (có canonical name) trong một class cùng compilation unit với sealed parent, nếu phù hợp visibility và architecture.
2. Khai báo **nested record** trong sealed interface/class tương ứng nếu đó là một data variant có trạng thái bất biến phù hợp.
3. Khai báo **top-level final class** trong same source file để inference hợp lệ.
4. Giữ implementation trong file riêng và dùng explicit `permits`.
5. Nếu thực sự phải tạo arbitrary anonymous implementations ở nhiều nơi, xét lại việc dùng `sealed`: có thể một interface thông thường hoặc strategy registry phù hợp hơn.

**Không cố dùng reflection hay cast** để qua mặt compiler. Sealed hierarchy còn có các ràng buộc runtime/linkage phù hợp; đường mở rộng phải là API thiết kế đúng.

## 32. Kiểm runtime bằng `Class.isSealed()`

Java 17 có API reflection giúp biết một class/interface có sealed hay không.

Tạo **`SealedReflectionDemo.java`**:

```java
sealed interface Event {
}

record Started(String id) implements Event {
}

record Finished(String id) implements Event {
}

public class SealedReflectionDemo {
    public static void main(String[] args) {
        System.out.println(Event.class.isSealed());
        System.out.println(Started.class.isSealed());
        System.out.println(Finished.class.isSealed());
    }
}
```

```bash
javac SealedReflectionDemo.java
java SealedReflectionDemo
```

```text
true
false
false
```

Event là sealed; hai records là final, không phải sealed, nên isSealed false.

**Reflection hỗ trợ kiểm cấu trúc type, không thay thế compile-time validation**. Nó không thêm types vào danh sách allowed và không làm một class ở file khác được infer.

## 33. Quan sát permitted direct types bằng `getPermittedSubclasses()`

Trong Java 17, `Class.getPermittedSubclasses()` cho biết các types **trực tiếp được phép** bởi một sealed type.

Tạo **`InferredPermitsReflectionDemo.java`**:

```java
import java.util.Arrays;

sealed interface Event {
}

record Started(int id) implements Event {
}

record Finished(int id) implements Event {
}

public class InferredPermitsReflectionDemo {
    public static void main(String[] args) {
        String[] names = Arrays.stream(
                        Event.class.getPermittedSubclasses())
                .map(Class::getSimpleName)
                .sorted()
                .toArray(String[]::new);

        System.out.println(Arrays.toString(names));
        System.out.println(
                Event.class.getPermittedSubclasses().length);
    }
}
```

```bash
javac InferredPermitsReflectionDemo.java
java InferredPermitsReflectionDemo
```

```text
[Finished, Started]
2
```

Chương trình **sắp xếp tên trước khi in**, không dựa vào một thứ tự reflection không cần thiết cho kiến thức bài này. Danh sách gồm direct permitted classes, không phải tất cả descendants.

Với `Class` không sealed, `getPermittedSubclasses()` trả `null` theo API; khi viết generic reflection code, cần xét null trước khi duyệt.

## 34. Reflection: direct vs indirect trong chuỗi inheritance

Tạo **`SealedHierarchyReflectionDemo.java`**:

```java
import java.util.Arrays;

sealed abstract class Root {
}

sealed class Branch extends Root {
}

final class Leaf extends Branch {
}

public class SealedHierarchyReflectionDemo {
    static String permitted(Class<?> type) {
        return Arrays.toString(
                Arrays.stream(type.getPermittedSubclasses())
                        .map(Class::getSimpleName)
                        .sorted()
                        .toArray(String[]::new));
    }

    public static void main(String[] args) {
        System.out.println(permitted(Root.class));
        System.out.println(permitted(Branch.class));
    }
}
```

```bash
javac SealedHierarchyReflectionDemo.java
java SealedHierarchyReflectionDemo
```

```text
[Branch]
[Leaf]
```

Hai danh sách không giống nhau:

- Root trực tiếp permit Branch.
- Branch trực tiếp permit Leaf.
- Leaf là **indirect subclass của Root**, không thuộc Root.getPermittedSubclasses().

**Lưu ý:** Hàm `permitted` trong demo chỉ được gọi với sealed types, nên không xử lý kết quả null. Với thư viện reusable, cần kiểm `type.isSealed()` hoặc null trước.

## 35. `permits` không phải công cụ áp dụng cho mọi class/interface

Một class thông thường không sealed không được dùng permits để liệt kê subclasses:

```java
// class Open permits A, B { } // Không hợp lệ.
```

Một type `final` không cho kế thừa và không thể đồng thời sealed theo cú pháp Java class thông thường:

```java
// final sealed class Invalid { } // Không hợp lệ.
```

Với class hierarchy thông thường, `sealed` bảo vệ **direct subtype set**; `permits` là mệnh đề bổ trợ có thể tường minh hoặc suy ra khi điều kiện cùng compilation unit đủ.

## 36. Compiler suy ra từ khai báo, không cần tạo objects

Một sealed hierarchy là **thông tin về types**, không phụ thuộc số instances đã được tạo.

Ví dụ:

```java
sealed interface Marker {
}

final class One implements Marker {
}

final class Two implements Marker {
}
```

Dù chương trình **chưa bao giờ gọi `new One()` hay `new Two()`**, compiler vẫn suy ra hai types nếu chúng ở cùng compilation unit.

**Không nhầm:** “Kiểu con được phép” là luật compile/link-time cho type hierarchy; không phải tập objects đã xuất hiện trong heap.

## 37. Thứ tự khai báo kiểu con trong file không phải điều kiện bản chất

Các top-level declarations trong một compilation unit có thể tham chiếu nhau phù hợp Java name resolution. Không phải bắt buộc đặt sealed parent trước tất cả children mới được suy ra.

Ví dụ:

```java
final class Done implements State {
}

sealed interface State {
}
```

Đây là **hai top-level declarations minh họa** trong cùng compilation unit, hợp lệ theo điều kiện inference. `Done` direct implements State và có canonical name.

**Điều kiện là quan hệ khai báo và unit, không phải vị trí dòng đầu/cuối file**. Tuy nhiên, sắp xếp parent trước children thường dễ đọc hơn cho người học.

## 38. Nested types sâu hơn một tầng vẫn có canonical name

Ví dụ:

```java
sealed interface Message {
}

class Outer {
    static class Inner {
        static final class Email implements Message {
        }
    }
}
```

`Outer.Inner.Email` là member nested class có canonical name và cùng compilation unit. Vì `Email implements Message` trực tiếp, nó có thể thuộc inferred permitted set dù nested nhiều tầng.

**Không khái quát thành mọi nested type:** Local/anonymous class không có canonical name. Chỉ các nested named types có canonical name theo Java mới thỏa điều kiện.

## 39. Sealed interface vẫn có thể có abstract method và polymorphism

Tập direct implementations đã được suy ra không làm interface mất khả năng dispatch qua shared API.

Tạo **`SealedPolymorphismDemo.java`**:

```java
sealed interface Calculation {
    int apply(int a, int b);
}

record Add() implements Calculation {
    @Override
    public int apply(int a, int b) {
        return a + b;
    }
}

record Multiply() implements Calculation {
    @Override
    public int apply(int a, int b) {
        return a * b;
    }
}

public class SealedPolymorphismDemo {
    public static void main(String[] args) {
        Calculation[] operations = {
                new Add(), new Multiply()
        };

        for (Calculation operation : operations) {
            System.out.println(operation.apply(3, 4));
        }
    }
}
```

```bash
javac SealedPolymorphismDemo.java
java SealedPolymorphismDemo
```

```text
7
12
```

Compiler biết các direct types Add/Multiply được phép nhờ same compilation unit. Nhưng runtime vẫn gọi `apply` theo implementation object. `sealed` giới hạn quan hệ kế thừa; nó **không biến mọi lời gọi thành static dispatch**.

## 40. Tránh nhầm exhaustive switch với suy ra `permits`

Việc Java suy ra permitted classes khi bỏ `permits` là quy tắc khai báo sealed hierarchy. Nó không tự có nghĩa mọi dạng `switch` trên sealed interface là exhaustive ở **mọi phiên bản Java** hay trong mọi cú pháp.

Đặc biệt với **Java 17**:

- Pattern matching for `instanceof` đã có.
- Pattern matching for `switch` là tính năng preview ở Java 17, không nên đưa làm ví dụ mặc định nếu mục tiêu biên dịch bằng `javac` bình thường không bật preview.
- `switch` truyền thống chỉ dùng types/labels phù hợp với ngôn ngữ; không thể đặt tùy ý `case SomeSubtype` như cú pháp hoàn chỉnh Java 17 mặc định.

Nếu xây ví dụ sealed hierarchy Java 17 chạy ngay, dùng polymorphism, `instanceof` type patterns hoặc methods chung. Với Java 21+ có các pattern switch final/record patterns thì là chủ đề phiên bản khác, cần ghi version rõ.

## 41. Vì sao Java không suy ra từ cả package hay module?

Nếu compiler tự tìm tất cả classes trong package/module để tạo permitted set khi bỏ permits, kết quả sẽ phụ thuộc nhiều hơn vào build inputs và những files nào hiện diện khi biên dịch. Điều này không phù hợp một hierarchy cần **danh sách đóng, dễ kiểm soát và ổn định**.

Giới hạn inference theo compilation unit cho phép:

- Thấy trực tiếp những child declarations ngay trong đơn vị mã nguồn tương ứng.
- Kiểm quan hệ parent/children nhất quán.
- Tránh việc chỉ thêm một file cùng package mà vô tình biến nó thành permitted subtype của sealed parent.
- Khuyến khích explicit permits khi members tách file để ý đồ kiến trúc rõ ràng.

Đây là **lý do thiết kế có tính diễn giải**, còn điều kiện ràng buộc chính thức là **same compilation unit + canonical name + direct relation**.

## 42. So sánh `permits` tường minh và suy ra

| Tình huống | Có thể bỏ permits? | Giải thích |
| --- | --- | --- |
| Sealed class và hai direct final subclasses trong cùng file | Có | Cùng compilation unit, canonical names |
| Sealed interface và hai direct records trong cùng file | Có | Direct implementations cùng unit |
| Direct child là member nested class cùng unit | Có | Member type có canonical name |
| Direct child là local class trong method | Không | Local class không có canonical name |
| Direct child là anonymous class | Không | Anonymous class không có canonical name |
| Child ở file khác nhưng cùng package | Không cho inference | Cần explicit permits |
| Child ở file khác nhưng cùng named module | Không cho inference | Cần explicit permits |
| Indirect grandchild cùng file | Không suy ra vào parent set | Không trực tiếp extends/implements parent |
| Cùng file có unrelated class | Không suy ra class unrelated | Thiếu direct relation |
| Sealed không có subtype nào và không permits | Không | Lỗi compile-time |
| Sealed đã ghi permits A, cùng file thêm B | B không tự được cộng vào | Explicit list quyết định |
| Child `non-sealed` cùng file | Có thể | Nếu direct relation đúng và hợp lệ |
| Child `sealed` cùng file | Có thể | Bản thân child phải có permitted descendants hợp lệ |
| Child record implements sealed interface | Có thể | Record final, direct implementation hợp lệ |

**Không xem việc “cùng file” là điều kiện duy nhất.** Tất cả điều kiện phải đồng thời đáp ứng.

## 43. Các lỗi biên dịch thường gặp và cách sửa

| Lỗi/hiểu nhầm | Nguyên nhân | Sửa đúng |
| --- | --- | --- |
| Sealed parent không có permits và không con cùng file | Không có tập để infer | Khai báo direct child hoặc đổi thiết kế final |
| Child ở file khác cùng package nhưng bỏ permits | Không cùng compilation unit | Dùng explicit permits |
| Child ở cùng module nhưng file khác | Module scope không thay thế unit scope | Dùng explicit permits |
| Local class implements sealed interface trực tiếp | Không có canonical name | Dùng top-level/member permitted type |
| Anonymous class extends sealed parent | Không có canonical name/permitted declaration | Dùng named child |
| Grandchild được kỳ vọng xuất hiện trong parent permits | Quan hệ gián tiếp | Chỉ direct child được permit |
| Quên `final`/`sealed`/`non-sealed` ở direct child | Chưa chọn inheritance policy | Chọn modifier phù hợp |
| Sealed class không nhận direct interface như “subclass” | Interface không extends class | Kiểm extends/implements đúng loại |
| Explicit permits chỉ liệt kê A nhưng B cũng extends parent | B không được permit | Thêm B vào permits hoặc bỏ permits khi same unit |
| Explicit permits tên một class không direct extends parent | Permits chỉ cho direct types | Liệt kê direct child thật |
| Tưởng `javac A.java B.java` là một unit | Mỗi source file là unit riêng | Xem ranh giới file nguồn |
| Muốn class sealed mà không cho con nào | Sealed yêu cầu permitted set | Dùng `final class` |
| Dùng preview pattern switch Java 17 không bật flags | Sai phiên bản/cờ compile | Dùng Java 17 ổn định hoặc nêu version |
| Cố đoán generated class names từ compiler | Không phải API ổn định | Dùng reflection `getPermittedSubclasses` |
| Cho subclass thuộc module/package không phù hợp | Vi phạm co-location rules | Cùng module hoặc cùng package (unnamed) |
| Tưởng có inferred permits thì mọi descendant bị final | `non-sealed` có thể mở nhánh | Xem từng direct child modifier |

## 44. Test tự động về danh sách được suy ra

Tạo **`InferredPermitsSelfTest.java`**:

```java
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

sealed interface Transport {
}

record Walk() implements Transport {
}

record Bike() implements Transport {
}

record Car() implements Transport {
}

public class InferredPermitsSelfTest {
    static void check(boolean value, String label) {
        if (!value) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        check(Transport.class.isSealed(), "sealed");

        Class<?>[] permitted =
                Transport.class.getPermittedSubclasses();

        check(permitted.length == 3, "three children");

        Set<String> names = Arrays.stream(permitted)
                .map(Class::getSimpleName)
                .collect(Collectors.toSet());

        check(names.equals(Set.of("Walk", "Bike", "Car")),
                "permitted names");

        check(!Walk.class.isSealed(), "record is final");

        System.out.println("inferred permits PASS");
    }
}
```

```bash
javac InferredPermitsSelfTest.java
java InferredPermitsSelfTest
```

```text
inferred permits PASS
```

`check` ném `AssertionError` tường minh khi sai, nên không cần bật JVM `-ea`. Test không giả định thứ tự kết quả reflection: chuyển thành Set và so toàn bộ tên.

**Mục tiêu test:** Xác nhận `Transport` sealed và danh sách direct permitted implementations chính xác sau khi compiler suy ra. Nếu vô tình thêm `Scooter implements Transport` vào cùng unit, test count/names bắt được thay đổi đó.

## 45. Bài tập 1: xét một compilation unit

Giả sử tất cả ở **cùng một tệp Java**:

```java
sealed interface Vehicle {
}

final class Car implements Vehicle {
}

non-sealed class Bike implements Vehicle {
}

final class RacingBike extends Bike {
}

final class Boat {
}
```

**Câu hỏi:** Khi bỏ permits của Vehicle, những kiểu nào được compiler suy ra?

**Đáp án:** `Car` và `Bike`.

- Car và Bike **direct implements Vehicle**.
- RacingBike chỉ extends Bike, **gián tiếp** thuộc Vehicle.
- Boat không implements Vehicle.
- Car và Bike có canonical names và cùng compilation unit.

Nếu muốn Bike không cho subclass nữa, đổi thành `final class Bike implements Vehicle`, nhưng khi ấy RacingBike sẽ không thể extends Bike.

## 46. Bài tập 2: loại những ứng viên không có canonical name

Xem mã **cố ý sai**:

```java
sealed interface Listener {
}

class Factory {
    static Listener make() {
        class LocalListener implements Listener {
        }

        return new LocalListener();
    }
}
```

**Vấn đề:** LocalListener không có canonical name và không thuộc inferred permitted set. Listener còn không có permitted direct subtype hợp lệ nào khác. Compiler từ chối.

### Một cách sửa runnable

Tạo **`NamedListenerDemo.java`**:

```java
sealed interface Listener {
    void onEvent();
}

public class NamedListenerDemo {
    private static final class LocalNamedListener
            implements Listener {
        @Override
        public void onEvent() {
            System.out.println("EVENT");
        }
    }

    static Listener make() {
        return new LocalNamedListener();
    }

    public static void main(String[] args) {
        make().onEvent();
    }
}
```

```bash
javac NamedListenerDemo.java
java NamedListenerDemo
```

```text
EVENT
```

`LocalNamedListener` là **member nested class có canonical name**, không phải local class dù tên của nó có chữ “Local”. Nó là direct implementation của Listener, cùng compilation unit và final, nên inference hợp lệ.

**Tên kiểu không quyết định category của declaration.** Vị trí khai báo và rules của Java mới quyết định local vs member.

## 47. Bài tập 3: phân biệt class/interface trực tiếp

Tệp **`InterfaceHierarchyExercise.java`**:

```java
sealed interface Service {
}

non-sealed interface Online extends Service {
}

final class Web implements Online {
}

final class LocalService implements Service {
}

public class InterfaceHierarchyExercise {
    public static void main(String[] args) {
        Service a = new Web();
        Service b = new LocalService();

        System.out.println(a instanceof Online);
        System.out.println(b instanceof Online);
    }
}
```

```bash
javac InterfaceHierarchyExercise.java
java InterfaceHierarchyExercise
```

```text
true
false
```

**Hỏi:** Direct permitted types của Service là gì?

**Đáp án:** `Online` và `LocalService`. `Web` chỉ directly implements Online nên là indirect descendant của Service.

## 48. Bài tập 4: sửa code tách file

Đang có:

```text
Shape.java
Square.java
Circle.java
```

Tệp Shape.java:

```java
sealed interface Shape {
}
```

Tệp Square.java:

```java
final class Square implements Shape {
}
```

Tệp Circle.java:

```java
final class Circle implements Shape {
}
```

Đây là **bộ ba file cố ý có lỗi** do Shape bỏ permits và không có con trực tiếp trong compilation unit Shape.java.

**Hai cách sửa:**

1. Giữ ba files và sửa Shape thành `sealed interface Shape permits Square, Circle`, đảm bảo package/module constraints.
2. Đưa các khai báo Square và Circle vào **cùng compilation unit** với Shape và giữ bỏ permits nếu cách tổ chức file phù hợp.

Chỉ biên dịch cả ba trong một lệnh `javac` không giải quyết lỗi inference.

## 49. Câu hỏi ôn tập có đáp án

**1.** Khi nào một sealed class không cần `permits`?

*Khi có ít nhất một direct subclass có canonical name, khai báo trong cùng compilation unit; compiler suy ra toàn bộ direct subclasses thỏa điều kiện.*

**2.** Nếu direct child ở file khác nhưng cùng package, có được suy ra không?

*Không; chỉ cùng package chưa đủ.*

**3.** Nếu direct child ở module khác?

*Không hợp lệ đối với permitted hierarchy theo rules module. Inference cũng không thể vượt qua compilation unit.*

**4.** Trong sealed interface, những loại direct types nào được suy ra?

*Direct implementing classes và direct extending interfaces, có canonical names trong cùng unit.*

**5.** Local class trong method có canonical name không?

*Không, nên không được suy ra.*

**6.** Anonymous class có thể trực tiếp implements sealed interface nhờ bỏ permits không?

*Không; không có canonical name và không thể trở thành permitted direct implementation theo cách đó.*

**7.** Nested member class có được suy ra không?

*Có thể, nếu có canonical name, cùng unit, và trực tiếp extends/implements parent.*

**8.** Tại sao một direct child phải `final`, `sealed` hoặc `non-sealed`?

*Để chỉ rõ nhánh tiếp tục đóng, tiếp tục sealed hoặc mở lại theo inheritance policy.*

**9.** Có thể khai báo sealed type không permits và không có direct children không?

*Không đối với ordinary sealed class/interface; lỗi compile-time.*

**10.** Nếu không muốn có bất kỳ subclass nào, nên dùng gì?

*Final class.*

**11.** `Grandchild extends Child` có tự nằm trong permits của Grandparent không?

*Không, nếu chỉ là quan hệ gián tiếp.*

**12.** Một direct `non-sealed` child có cho phép subclass phía dưới không?

*Có, theo ordinary inheritance rules.*

**13.** Nếu parent đã ghi `permits A` nhưng cùng file còn B extends parent, B được tự bổ sung không?

*Không, phải ghi B hoặc bỏ permits khi đủ điều kiện inference.*

**14.** `Class.getPermittedSubclasses()` liệt kê direct hay indirect descendants?

*Direct permitted types của sealed declaration.*

**15.** `Class.isSealed()` kiểm gì?

*Kiểm class/interface tương ứng có sealed hay không.*

**16.** Cùng một lần gọi `javac A.java B.java` có biến A.java/B.java thành cùng compilation unit không?

*Không.*

**17.** Inference dựa vào thứ tự declarations trong file không?

*Không; dựa vào loại, canonical name, quan hệ direct và compilation unit.*

**18.** Những classes unrelated cùng file có được suy ra không?

*Không; thiếu direct inheritance/implementation relation.*

**19.** Vì sao enum thường không phải ví dụ nên dùng để giải thích inference của ordinary sealed class?

*Enum có ngữ nghĩa đặc biệt về subclass ngầm do constant-specific bodies; chủ đề này nói về sealed class/interface thông thường.*

**20.** Khi nào explicit permits tốt hơn inference?

*Khi direct subtypes ở các source files riêng, hoặc muốn danh sách cho phép hiển thị rõ từ declaration để kiểm soát API.*

## 50. Checklist trước khi xóa `permits`

- [ ] Parent thật sự được khai báo `sealed`?
- [ ] Parent là ordinary sealed class hay sealed interface, không nhầm với enum special case?
- [ ] Có ít nhất một **direct** subtype hợp lệ?
- [ ] Tất cả direct subtypes muốn cho phép nằm trong **cùng compilation unit**?
- [ ] Không dựa vào việc chúng chỉ cùng package/thư mục/module?
- [ ] Không dựa vào việc chúng được biên dịch trong cùng invocation `javac`?
- [ ] Mỗi subtype được suy ra có **canonical name**?
- [ ] Không cố dùng local/anonymous class làm direct permitted child?
- [ ] Quan hệ `extends`/`implements` thực sự trực tiếp?
- [ ] Không nhầm descendants gián tiếp với direct permitted list?
- [ ] Với sealed interface, đã tính cả direct extending interfaces?
- [ ] Các direct children có modifiers final/sealed/non-sealed hợp lệ?
- [ ] Với child sealed tiếp theo, đã xét descendants của chính child đó?
- [ ] Nếu chọn `non-sealed`, đã hiểu nhánh phía dưới có thể mở?
- [ ] Không có file khác đang cố trực tiếp extends/implements parent sau khi xóa permits?
- [ ] Nếu có explicit permits, đã cập nhật đủ direct types thay vì tưởng compiler gộp?
- [ ] Constraints package/module phù hợp với toàn hierarchy?
- [ ] Không dựa vào generated binary names để suy ra canonical names?
- [ ] Có test `getPermittedSubclasses()` nếu muốn khóa danh sách API không?
- [ ] Nếu mục tiêu không có child, có nên dùng `final` thay vì `sealed`?
- [ ] Ví dụ Java 17 dùng cú pháp stable, không phụ thuộc preview pattern switch?
- [ ] Tên file/public class, lệnh `javac` và stdout đã khớp?
- [ ] Đã cân nhắc khả năng bảo trì khi nhét nhiều top-level classes vào cùng file?

---

**Ghi nhớ cuối bài:** Trong Java 17+, khi **`sealed class` hoặc `sealed interface` không ghi `permits`**, compiler suy ra danh sách permitted direct subtypes bằng cách chọn những **named types có canonical name được khai báo trong cùng compilation unit và trực tiếp extends/implements sealed parent**. Với class, đó là các **direct subclasses**; với interface, gồm direct implementing classes và direct extending interfaces. **Cùng package/module nhưng khác file không đủ**; **local/anonymous classes** và **descendants gián tiếp** không thuộc inferred set. Nếu không có direct subtype hợp lệ, sealed declaration thiếu permits bị lỗi. Bỏ permits **không bỏ** các ràng buộc `final`/`sealed`/`non-sealed` ở direct children hay điều kiện package/module. Khi direct implementations nằm ở nhiều files, dùng **explicit permits**; khi chúng gần nhau trong một file, inference có thể làm hierarchy gọn và rõ hơn.