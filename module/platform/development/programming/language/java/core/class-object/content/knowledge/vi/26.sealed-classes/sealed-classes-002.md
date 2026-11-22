# Khai báo sealed và danh sách permits trong Java 17+

**Sealed class** và **sealed interface** cho phép người thiết kế API **kiểm soát trực tiếp những lớp hoặc interface nào được quyền kế thừa/hiện thực một kiểu**. Java 17 hỗ trợ tính năng này ở dạng chính thức, không cần bật preview.

Ví dụ cơ bản:

~~~java
sealed interface Result permits Success, Failure {}

record Success(String value) implements Result {}

record Failure(String message) implements Result {}
~~~

`Result` là một **sealed interface**; chỉ `Success` và `Failure` được chỉ định là **permitted direct implementations**. Một class bên ngoài danh sách không thể trực tiếp `implements Result`, kể cả khi nó nằm cùng package.

Với class:

~~~java
sealed abstract class Shape permits Circle, Rectangle {}

final class Circle extends Shape {}

non-sealed class Rectangle extends Shape {}
~~~

Ở đây `Circle` đóng đường kế thừa bằng `final`, còn `Rectangle` mở lại việc tạo subclasses vì khai báo `non-sealed`. Danh sách `permits` chỉ kiểm soát **bước kế thừa trực tiếp**, không tự cấm mọi hậu duệ gián tiếp.

Bài thuộc **Java Core — Class & Object / Lớp sealed**, tập trung đúng đề **“Khai báo sealed và danh sách permits”**. Mọi chương trình hoàn chỉnh sử dụng Java 17+ với tên file, lệnh biên dịch/chạy và stdout dự kiến. Các đoạn cố ý sai được chú thích riêng để không nhầm với code runnable.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Khai báo `sealed class` và `sealed interface` theo cú pháp Java 17.
2. Viết danh sách `permits` với đúng các **direct subclasses/direct subinterfaces/direct implementing classes**.
3. Phân biệt `extends`, `implements` và `permits`; hiểu chúng không thay thế nhau.
4. Biết khi nào phải viết `permits` tường minh và khi nào Java suy luận danh sách.
5. Nắm giới hạn **cùng named module** hoặc **cùng package trong unnamed module**.
6. Giải thích nghĩa vụ của permitted subtype: `final`, `sealed` hoặc `non-sealed` khi cần.
7. Phân biệt `final` kết thúc hierarchy, `sealed` tiếp tục giới hạn và `non-sealed` mở hierarchy.
8. Hiểu sự khác nhau giữa **trực tiếp được phép** và **gián tiếp kế thừa hợp lệ**.
9. Dùng records, enums và ordinary classes phù hợp với sealed interfaces.
10. Khai báo hierarchy nhiều tầng, nhiều branches và thiết kế leaf types.
11. Hiểu `abstract sealed class` và phương thức trừu tượng của hierarchy.
12. Tránh nhầm `sealed` có nghĩa kiểu dữ liệu bất biến, thread-safe hoặc không thể tạo instance.
13. Hiểu modifiers hợp lệ cho permitted interfaces khác với permitted classes.
14. Phân biệt generic sealed types và generic permitted subtypes.
15. Hiểu accessibility/package/module ràng buộc danh sách permits.
16. Đọc lỗi trình biên dịch khi listed type không trực tiếp extends/implements type gốc.
17. Biết sealed class vẫn có constructors, fields và methods thông thường.
18. Phân biệt thiết kế với sealed hierarchy và enum hữu hạn.
19. Hiểu Java 17 `instanceof` pattern matching nhưng không mặc định sử dụng switch pattern matching ổn định.
20. Sử dụng Reflection `Class.isSealed()` và `getPermittedSubclasses()`.
21. Đánh giá versioning khi thêm/bớt loại được permits.
22. Test cả constraints ở compile time và behavior ở runtime.

## 2. Vì sao cần giới hạn hệ thống kiểu con?

Giả sử API mô hình hóa outcome của xử lý:

~~~java
interface Outcome {}

class Success implements Outcome {}
class Failure implements Outcome {}
~~~

Nếu interface thông thường là accessible, một module khác có thể định nghĩa thêm:

~~~java
class UnknownOutcome implements Outcome {}
~~~

Việc mở rộng như vậy đôi khi hữu ích cho plugins. Nhưng đôi khi domain muốn bảo đảm rằng **chỉ có một số biến thể được biết trước**, để:

- kiểm soát tính hợp lệ của những trạng thái/biến thể;
- làm rõ kiến trúc phân cấp;
- tránh implementation bên ngoài phá invariant của API;
- tập trung logic xử lý từng variant;
- giúp compiler và công cụ phân tích biết những nhánh trực tiếp có thể tồn tại.

Sealed type đáp ứng mục tiêu đó bằng **quy tắc ngôn ngữ và kiểm tra của compiler/runtime**, không phải chỉ bằng comment hay convention.

## 3. Cú pháp sealed class

Mẫu:

~~~java
public sealed class Parent
        permits ChildA, ChildB {
    // Constructors, methods, fields...
}
~~~

Các class `ChildA`, `ChildB` phải thực sự **extends Parent trực tiếp** và tuân thủ location/modifier rules.

Ví dụ:

~~~java
sealed class Vehicle permits Car, Truck {}

final class Car extends Vehicle {}

final class Truck extends Vehicle {}
~~~

Trong một source file với các top-level types package-private như trên, Java compiler xác định danh sách permitted direct subclasses.

**Ghi nhớ ba câu:**

- `extends` viết ở **subclass** để khai báo quan hệ kế thừa.
- `permits` viết ở **sealed parent** để giới hạn direct subtypes.
- Một type trong `permits` **không tự trở thành subclass** chỉ vì được liệt kê; nó còn phải khai báo quan hệ kế thừa phù hợp.

## 4. Chương trình chạy: sealed class có hai leaf types

Tạo file **`SealedClassBasicsDemo.java`**:

~~~java
public class SealedClassBasicsDemo {
    static abstract sealed class Vehicle permits Car, Truck {
        abstract String label();
    }

    static final class Car extends Vehicle {
        @Override
        String label() {
            return "car";
        }
    }

    static final class Truck extends Vehicle {
        @Override
        String label() {
            return "truck";
        }
    }

    static String describe(Vehicle vehicle) {
        return vehicle.label();
    }

    public static void main(String[] args) {
        System.out.println(describe(new Car()));
        System.out.println(describe(new Truck()));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedClassBasicsDemo.java
java SealedClassBasicsDemo
~~~

Stdout:

~~~text
car
truck
~~~

`Vehicle` là abstract sealed class. Chỉ `Car` và `Truck` trực tiếp extends Vehicle. Compiler bảo đảm hierarchy contract; runtime dispatch chọn phương thức `label()` tương ứng.

## 5. Cú pháp sealed interface

Mẫu:

~~~java
sealed interface Message
        permits TextMessage, BinaryMessage {
}
~~~

Các direct implementors hoặc extending subinterfaces được phép phải khai báo quan hệ với Message:

~~~java
record TextMessage(String text) implements Message {}

final class BinaryMessage implements Message {}
~~~

Một interface có thể được:
- trực tiếp **implements** bởi class/record/enum phù hợp;
- trực tiếp **extends** bởi một interface con.

Giống sealed class, `permits` kiểm soát **những direct subtypes**, không phải danh sách object instances.

### Class và interface có gì khác?

Sealed class kiểm soát direct classes dùng `extends`. Sealed interface kiểm soát **classes implement trực tiếp** và **interfaces extends trực tiếp**. Vì vậy sealed interface thường rất tiện để mô hình hóa một tập variants vừa có dữ liệu vừa có behavior.

## 6. Chương trình chạy: sealed interface với records

Tạo **`SealedInterfaceBasicsDemo.java`**:

~~~java
public class SealedInterfaceBasicsDemo {
    sealed interface Result permits Ok, Error {}

    record Ok(String value) implements Result {}

    record Error(String reason) implements Result {}

    static String describe(Result result) {
        if (result instanceof Ok ok) {
            return "ok:" + ok.value();
        }
        if (result instanceof Error error) {
            return "error:" + error.reason();
        }
        throw new IllegalStateException("unexpected result");
    }

    public static void main(String[] args) {
        System.out.println(describe(new Ok("data")));
        System.out.println(describe(new Error("missing")));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedInterfaceBasicsDemo.java
java SealedInterfaceBasicsDemo
~~~

Stdout:

~~~text
ok:data
error:missing
~~~

Records là final types theo ngôn ngữ, nên phù hợp làm leaves của sealed interface. `instanceof` type patterns đã được Java 16 hoàn thiện và chạy bình thường trên Java 17.

## 7. Ý nghĩa chính xác của `permits`

Danh sách:

~~~java
sealed class Base permits A, B {}
~~~

nói: **Các direct subclasses của Base chỉ có thể thuộc những class A và B được liệt kê, với điều kiện A/B đáp ứng đầy đủ những quy tắc khác.**

Nó **không** nói:
- A hoặc B được tạo object tự động;
- A/B chỉ được chứa một instance;
- A/B phải là final trong mọi trường hợp;
- những subclasses của A/B đều phải liệt kê tại Base;
- A/B được miễn Java access control;
- Base không được có methods hoặc constructors;
- Base tự trở thành immutable;
- mọi object type trong hệ thống được đóng toàn bộ nếu có một nhánh non-sealed.

Ví dụ:

~~~java
sealed class Base permits Branch {}
non-sealed class Branch extends Base {}
class Grandchild extends Branch {}
~~~

`Grandchild` **không trực tiếp extends Base**, nên nó không thuộc danh sách permits của Base và vẫn hợp lệ. `Branch` đã chủ động mở nhánh con.

## 8. Chương trình chạy: subtype gián tiếp không cần xuất hiện trong root permits

Tạo **`IndirectSubtypeDemo.java`**:

~~~java
public class IndirectSubtypeDemo {
    static sealed class Base permits Branch {}

    static non-sealed class Branch extends Base {}

    static final class Leaf extends Branch {}

    public static void main(String[] args) {
        Base value = new Leaf();

        System.out.println("Base=" + (value instanceof Base));
        System.out.println("Branch=" + (value instanceof Branch));
        System.out.println("Leaf=" + (value instanceof Leaf));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 IndirectSubtypeDemo.java
java IndirectSubtypeDemo
~~~

Stdout:

~~~text
Base=true
Branch=true
Leaf=true
~~~

`Leaf` kế thừa Base gián tiếp thông qua Branch. Vì Branch là non-sealed, nó được phép có thêm subclasses không bị Base liệt kê từng cái.

## 9. Ba kết cục của permitted class: final, sealed, non-sealed

Một **class được permitted trực tiếp** trong một sealed hierarchy phải dùng một trong những hướng khai báo phù hợp:

| Modifier | Nghĩa | Có descendants? |
| --- | --- | --- |
| `final` | Không cho class khác subclass class này | Không |
| `sealed` | Cho phép một tập direct subclasses được kiểm soát tiếp | Có, nhưng giới hạn |
| `non-sealed` | Mở trở lại subclassing theo access rules thông thường | Có, không giới hạn bằng permits ở chính nhánh này |

Ví dụ:

~~~java
sealed class Root permits FinalLeaf, RestrictedBranch, OpenBranch {}

final class FinalLeaf extends Root {}

sealed class RestrictedBranch extends Root permits InnerLeaf {}

final class InnerLeaf extends RestrictedBranch {}

non-sealed class OpenBranch extends Root {}
~~~

Không viết một direct child thông thường thiếu modifier:

~~~java
// class InvalidChild extends Root {} // Không hợp lệ khi direct permitted subtype.
~~~

Ngoại lệ về cú pháp modifier: records vốn implicitly final, nên record implements sealed interface không cần gõ `final`; enum có special rules riêng.

## 10. Chương trình chạy: final, sealed và non-sealed trong cùng cây

Tạo **`ThreeBranchesDemo.java`**:

~~~java
public class ThreeBranchesDemo {
    static sealed class Root
            permits FinalLeaf, RestrictedBranch, OpenBranch {}

    static final class FinalLeaf extends Root {}

    static sealed class RestrictedBranch extends Root
            permits InnerLeaf {}

    static final class InnerLeaf extends RestrictedBranch {}

    static non-sealed class OpenBranch extends Root {}

    static final class FurtherChild extends OpenBranch {}

    public static void main(String[] args) {
        Root a = new FinalLeaf();
        Root b = new InnerLeaf();
        Root c = new FurtherChild();

        System.out.println(a.getClass().getSimpleName());
        System.out.println(b.getClass().getSimpleName());
        System.out.println(c.getClass().getSimpleName());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ThreeBranchesDemo.java
java ThreeBranchesDemo
~~~

Stdout:

~~~text
FinalLeaf
InnerLeaf
FurtherChild
~~~

`Root` chỉ permits **FinalLeaf, RestrictedBranch, OpenBranch**. `InnerLeaf` được RestrictedBranch cho phép, còn `FurtherChild` nằm bên dưới nhánh non-sealed.

## 11. Permitted interface con chọn sealed hoặc non-sealed

Một **interface** không thể là `final interface`, bởi interface vẫn là contract để được implementations/extension.

Nếu sealed interface trực tiếp cho phép một subinterface, subinterface này phải tự khai báo **sealed** hoặc **non-sealed**.

~~~java
sealed interface Event permits InternalEvent, ExtensionEvent {}

sealed interface InternalEvent extends Event permits Started {}

non-sealed interface ExtensionEvent extends Event {}

record Started(long id) implements InternalEvent {}
~~~

`Started` là record implicitly final. `ExtensionEvent` mở extension: các classes mới có thể implements ExtensionEvent (trong phạm vi accessibility thông thường), và do đó là indirect implementations của Event.

### Khác biệt với permitted class

Đối với class direct child, ba lựa chọn final/sealed/non-sealed. Đối với interface direct child, chỉ sealed/non-sealed vì `final` không phải interface modifier hợp lệ.

## 12. Chương trình chạy: sealed interface nối tiếp với non-sealed interface

Tạo **`InterfaceBranchDemo.java`**:

~~~java
public class InterfaceBranchDemo {
    sealed interface Event permits Internal, External {}

    sealed interface Internal extends Event permits Started {}

    non-sealed interface External extends Event {}

    record Started(int id) implements Internal {}

    static final class ExternalNotice implements External {
        @Override
        public String toString() {
            return "external";
        }
    }

    public static void main(String[] args) {
        Event internal = new Started(7);
        Event external = new ExternalNotice();

        System.out.println(internal);
        System.out.println(external);
        System.out.println(external instanceof Event);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 InterfaceBranchDemo.java
java InterfaceBranchDemo
~~~

Stdout:

~~~text
Started[id=7]
external
true
~~~

Sealed Event không trực tiếp permits ExternalNotice. ExternalNotice implements non-sealed External, rồi gián tiếp là Event. Phân biệt hai cấp là cốt lõi.

## 13. `sealed` không đồng nghĩa `abstract`

Một sealed **class** có thể là abstract hoặc concrete. Modifier sealed chỉ hạn chế **ai được quyền extends**, không tự bắt class thành abstract.

Ví dụ concrete:

~~~java
sealed class Base permits Child {
    String name() {
        return "base";
    }
}

final class Child extends Base {}
~~~

Nếu constructor/accessibility cho phép, code có thể `new Base()`; sealed không cấm tạo instance của chính Base. Ngược lại, nếu dùng `abstract sealed class Base`, không thể tạo Base trực tiếp vì abstract.

### Khi nào chọn abstract sealed?

Khi root đại diện cho một contract chung nhưng không có ý nghĩa tạo instance trực tiếp, ví dụ `Shape` với `area()` abstract hoặc `Expression` với semantics riêng từng variant.

## 14. Chương trình chạy: concrete sealed class vẫn instantiate được

Tạo **`ConcreteSealedDemo.java`**:

~~~java
public class ConcreteSealedDemo {
    static sealed class Base permits Child {
        String label() {
            return "base";
        }
    }

    static final class Child extends Base {}

    public static void main(String[] args) {
        Base direct = new Base();
        Base child = new Child();

        System.out.println(direct.label());
        System.out.println(child.label());
        System.out.println("same type=" +
                (direct.getClass() == child.getClass()));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ConcreteSealedDemo.java
java ConcreteSealedDemo
~~~

Stdout:

~~~text
base
base
same type=false
~~~

`Base` là concrete sealed class nên có thể instantiate. `Child` là subtype hợp lệ và kế thừa method `label`.

## 15. `permits` với tên class đầy đủ

`permits` thường liệt kê simple names khi các types nằm cùng phạm vi tìm tên:

~~~java
sealed class Document permits TextDocument, PdfDocument {}
~~~

Nếu types ở các packages khác nhau trong **cùng named module**, có thể cần fully qualified names hoặc imports hợp lệ, chẳng hạn:

~~~java
public sealed interface Document
        permits example.impl.TextDocument, example.impl.PdfDocument {
}
~~~

**Đoạn này là skeleton minh họa**, chỉ biên dịch khi các packages/module/types tồn tại và Java visibility rules cho phép. Nó không phải một file runnable độc lập.

`permits` dùng type names, không dùng object expressions hoặc enum constants:

~~~java
// permits new TextDocument() // Sai cú pháp.
// permits SomeEnum.CONSTANT // Sai: danh sách type names, không là values.
~~~

Đồng thời, được liệt kê không thay thế yêu cầu actual direct inheritance.

## 16. Nhầm lẫn thường gặp: `permits` không phải `implements`

Sai tư duy:

~~~java
sealed interface Role permits Admin {}
class Admin {}
~~~

Type `Admin` được listed nhưng không `implements Role`. Compiler sẽ không xem Admin là permitted implementation hợp lệ chỉ nhờ tên.

Đúng:

~~~java
sealed interface Role permits Admin {}

final class Admin implements Role {}
~~~

Hướng ngược lại cũng sai:

~~~java
sealed interface Role permits Admin {}
final class Guest implements Role {} // Guest không nằm trong permits.
~~~

Ở hierarchy sealed có explicit permits list, direct implementing class Guest sẽ bị từ chối.

## 17. Nếu bỏ danh sách permits: khi nào Java suy luận?

Khi không có `permits` explicit, compiler chỉ có thể suy ra **direct children được khai báo phù hợp trong cùng compilation unit**:

~~~java
sealed interface Value {}
record TextValue(String text) implements Value {}
record NumberValue(int number) implements Value {}
~~~

Trong cùng một source file, hai records là inferred permitted implementations. Compiler **không tìm mọi files trong package/module** để cập nhật whitelist. Khi tách các types ra compilation units khác, dùng `permits` tường minh và kiểm direct inheritance. Trường hợp canonical name, nested/local declarations, lớp không trực tiếp thuộc hierarchy và lỗi khi tách file được phân tích có hệ thống tại bài **Điều kiện suy ra danh sách lớp con khi bỏ permits**.

## 18. Chương trình chạy: suy luận permits từ cùng file

Tạo **`InferredPermitsDemo.java`**:

~~~java
sealed interface Transport {}

final class Bus implements Transport {
    @Override
    public String toString() {
        return "bus";
    }
}

final class Train implements Transport {
    @Override
    public String toString() {
        return "train";
    }
}

public class InferredPermitsDemo {
    public static void main(String[] args) {
        Transport first = new Bus();
        Transport second = new Train();

        System.out.println(first);
        System.out.println(second);
        System.out.println("sealed=" + Transport.class.isSealed());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 InferredPermitsDemo.java
java InferredPermitsDemo
~~~

Stdout:

~~~text
bus
train
sealed=true
~~~

Parent `Transport` không có explicit permits; `Bus` và `Train` là direct implementors trong cùng source file nên danh sách được suy luận.

## 19. Explicit permits dù các types cùng file

Không bắt buộc bỏ permits khi tất cả types nằm cùng compilation unit:

~~~java
sealed interface Payment permits Cash, Card {}

record Cash(int cents) implements Payment {}

record Card(String lastFour) implements Payment {}
~~~

Viết explicit `permits Cash, Card` có lợi khi:
- muốn API reader nhìn ngay danh sách allowed variants;
- muốn giới hạn rõ types khi file có nhiều declarations;
- review versioning/kiến trúc dễ hơn;
- định chuyển các types sang source files khác về sau.

### Không lặp cho vui

Nếu types và hierarchy nhỏ, inferred permits làm ví dụ gọn. Nhưng với public API lớn, explicit list thường giúp biểu đạt intentional restriction.

## 20. Chương trình chạy: explicit permits cùng compilation unit

Tạo **`ExplicitPermitsDemo.java`**:

~~~java
public class ExplicitPermitsDemo {
    sealed interface Payment permits Cash, Card {}

    record Cash(int cents) implements Payment {}

    record Card(String number) implements Payment {}

    static String text(Payment payment) {
        if (payment instanceof Cash cash) {
            return "cash:" + cash.cents();
        }
        if (payment instanceof Card card) {
            return "card:" + card.number();
        }
        throw new IllegalStateException();
    }

    public static void main(String[] args) {
        System.out.println(text(new Cash(100)));
        System.out.println(text(new Card("****")));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ExplicitPermitsDemo.java
java ExplicitPermitsDemo
~~~

Stdout:

~~~text
cash:100
card:****
~~~

Explicit `permits` và inferred `permits` cùng thực hiện language-level restrictions; khác nhau ở cách declared permitted types được xác định.

## 21. Quy tắc vị trí: named module và unnamed module

Ngoài `permits` và modifier của children, vị trí khai báo phải hợp lệ:

- Parent thuộc **named module**: permitted direct subtypes phải ở **cùng named module** (có thể khác package nếu access phù hợp).
- Parent thuộc **unnamed module**: permitted direct subtypes phải ở **cùng package**.

`exports` và `requires` không nới điều kiện `permits`. Các ví dụ source layout đa package/classpath và cách kiểm lỗi `javac` là trọng tâm của bài **Ràng buộc cùng module hoặc cùng package**.

## 22. Nhiều packages trong cùng named module: cấu trúc minh họa

Ví dụ này **không phải một-file runnable**; nó minh họa layout project hợp lệ:

~~~text
src/
  edu.demo.sealed/
    module-info.java
    demo/api/Result.java
    demo/impl/Ok.java
    demo/impl/Error.java
~~~

`module-info.java`:

~~~java
module edu.demo.sealed {
    exports demo.api;
    exports demo.impl;
}
~~~

`demo/api/Result.java`:

~~~java
package demo.api;

public sealed interface Result
        permits demo.impl.Ok, demo.impl.Error {
}
~~~

`demo/impl/Ok.java`:

~~~java
package demo.impl;

public record Ok(String value)
        implements demo.api.Result {
}
~~~

`demo/impl/Error.java`:

~~~java
package demo.impl;

public record Error(String reason)
        implements demo.api.Result {
}
~~~

Các permitted implementations ở package khác nhưng **trong cùng named module**. Trong dự án thực, điều chỉnh `exports` theo public API/visibility mong muốn; đây là ví dụ minh họa để đơn giản hóa việc đọc.

## 23. Quy tắc cùng package trong unnamed module

Giả sử không dùng `module-info.java`:

~~~text
src/
  demo/
    Result.java
    Ok.java
    Error.java
~~~

`demo/Result.java`:

~~~java
package demo;

public sealed interface Result permits Ok, Error {}
~~~

`demo/Ok.java`:

~~~java
package demo;

public record Ok(String value) implements Result {}
~~~

`demo/Error.java`:

~~~java
package demo;

public record Error(String reason) implements Result {}
~~~

Đây là **bộ file minh họa**, không chạy như một-file demo. Vì cùng package demo, explicit permits works trong unnamed module. Nếu chuyển Error sang package khác mà không chuyển toàn hierarchy vào cùng named module phù hợp, sẽ vi phạm quy tắc location.

## 24. Compile-time errors từ module/package mismatch

Với **unnamed module**, không được:

~~~java
// package a;
// public sealed interface Result permits b.Ok {}
~~~

và định nghĩa `b.Ok` ở package khác rồi tin compiler chấp nhận. Dù một class public và import được, nó vẫn vi phạm same-package rule.

Với **named modules khác nhau**, việc cả hai modules `requires` nhau không làm permitted subclass thuộc cùng named module. Java cũng không cho phép “chỉ cần một danh sách permits thôi” để vượt module boundary.

### Thiết kế module phù hợp

Nếu cần mở rộng implementation ở plugins/modules độc lập, cân nhắc:
- public **non-sealed interface** extension point;
- sealed core hierarchy với **non-sealed permitted branch**;
- composition và registration;
- ServiceLoader qua một interface không sealed thích hợp.

Sealed root nên đại diện cho phạm vi kiểm soát mà module thực sự sở hữu.

## 25. Access modifiers vẫn áp dụng

`permits` **không nới lỏng accessibility**. Một direct subtype phải được phép extends/implements supertype theo Java access rules.

Ví dụ, nếu sealed class có constructor `private` không accessible với class con được phép, subclassing có thể thất bại dù tên subtype nằm trong permits list.

Tương tự, package-private types chỉ accessible trong package phù hợp; private nested types có lexical access rules riêng.

Đặc biệt với sealed class, thiết kế constructor accessibility phù hợp cho allowed subclasses:

~~~java
sealed abstract class Command permits Start, Stop {
    protected Command() {}
}

final class Start extends Command {}

final class Stop extends Command {}
~~~

Constructor `protected` giúp permitted subclass gọi `super()` hợp lệ, nhưng không biến mọi class thành permitted subtype.

## 26. Chương trình chạy: constructor của sealed superclass

Tạo **`SealedConstructorDemo.java`**:

~~~java
public class SealedConstructorDemo {
    static abstract sealed class Message permits Notice, Alert {
        private final String text;

        protected Message(String text) {
            this.text = java.util.Objects.requireNonNull(
                    text, "text");
        }

        String text() {
            return text;
        }
    }

    static final class Notice extends Message {
        Notice(String text) {
            super(text);
        }
    }

    static final class Alert extends Message {
        Alert(String text) {
            super(text);
        }
    }

    public static void main(String[] args) {
        Message first = new Notice("Hello");
        Message second = new Alert("Danger");

        System.out.println(first.text());
        System.out.println(second.text());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedConstructorDemo.java
java SealedConstructorDemo
~~~

Stdout:

~~~text
Hello
Danger
~~~

Sealed superclass vẫn có instance fields và constructors bình thường; permits kiểm soát type hierarchy, không thay constructor chaining rules.

## 27. Sealed và `final` khác nhau

`final class`: không cho bất kỳ subclass nào.

`sealed class`: có thể cho **một danh sách direct subclasses** cụ thể.

`non-sealed class`: khôi phục khả năng subclassing ở một nhánh vốn trực tiếp kế thừa/hiện thực sealed supertype.

Ví dụ:

~~~java
final class Closed {}
// class SubClosed extends Closed {} // Sai.

sealed class Limited permits Allowed {}
final class Allowed extends Limited {}
~~~

Ở Limited, subclass Allowed hợp lệ; ở Closed, không có permitted subtype nào vì `final` đóng hoàn toàn.

**Đừng viết `final sealed class`**: hai modifiers mâu thuẫn ý nghĩa về subclassing và Java không cho tổ hợp đó.

## 28. `non-sealed` chỉ hợp lệ đúng chỗ

`non-sealed` có ý nghĩa khi declaration là một **direct subtype của sealed class/interface**. Một class hoàn toàn không liên quan tới sealed parent không thể tự viết non-sealed tùy ý:

~~~java
// non-sealed class Ordinary {} // Không hợp lệ: không direct extends sealed type.
~~~

Đúng:

~~~java
sealed class Base permits Open {}

non-sealed class Open extends Base {}
~~~

`Open` ở nhánh đó cho phép subclasses theo usual Java rules. Các hậu duệ trực tiếp của Open **không phải** tiếp tục thêm `non-sealed` hoặc `final` vì chính Open đã mở lại nhánh.

## 29. Chương trình chạy: mở nhánh rồi subclass thường

Tạo **`NonSealedContinuationDemo.java`**:

~~~java
public class NonSealedContinuationDemo {
    static sealed class Entry permits Extension {}

    static non-sealed class Extension extends Entry {
        String describe() {
            return "extension";
        }
    }

    static class Plugin extends Extension {
        @Override
        String describe() {
            return "plugin";
        }
    }

    public static void main(String[] args) {
        Entry value = new Plugin();

        System.out.println(value instanceof Entry);
        System.out.println(((Extension) value).describe());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 NonSealedContinuationDemo.java
java NonSealedContinuationDemo
~~~

Stdout:

~~~text
true
plugin
~~~

`Plugin` chỉ `extends Extension`. Nó không trực tiếp extends sealed Entry và không cần được Entry liệt kê trong permits.

## 30. Hierarchy tiếp tục sealed ở tầng dưới

Một permitted class dùng `sealed` nghĩa là **nó tự trở thành sealed parent của tầng kế tiếp**:

~~~java
sealed class Parent permits Intermediate {}

sealed class Intermediate extends Parent permits Leaf {}

final class Leaf extends Intermediate {}
~~~

`Parent` không cần liệt kê Leaf vì Leaf không phải direct subclass của Parent.

Có thể có nhiều nhánh:

~~~text
Parent [sealed]
  |
  +-- Intermediate [sealed]
  |       |
  |       +-- Leaf [final]
  |
  +-- Open [non-sealed]
          |
          +-- arbitrary descendants
~~~

Tính đóng của toàn bộ cây phụ thuộc vào **từng nhánh**, không chỉ declaration của root.

## 31. Chương trình chạy: hierarchy nhiều tầng

Tạo **`MultiLevelSealedDemo.java`**:

~~~java
public class MultiLevelSealedDemo {
    static sealed interface Expression
            permits Literal, Compound {}

    static record Literal(int value) implements Expression {}

    static sealed interface Compound extends Expression
            permits Add, Multiply {}

    static record Add(Expression left, Expression right)
            implements Compound {}

    static record Multiply(Expression left, Expression right)
            implements Compound {}

    static int evaluate(Expression expression) {
        if (expression instanceof Literal literal) {
            return literal.value();
        }
        if (expression instanceof Add add) {
            return evaluate(add.left()) + evaluate(add.right());
        }
        if (expression instanceof Multiply multiply) {
            return evaluate(multiply.left()) *
                    evaluate(multiply.right());
        }
        throw new IllegalStateException("unknown expression");
    }

    public static void main(String[] args) {
        Expression expression =
                new Add(new Literal(2),
                        new Multiply(new Literal(3),
                                new Literal(4)));

        System.out.println(evaluate(expression));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 MultiLevelSealedDemo.java
java MultiLevelSealedDemo
~~~

Stdout:

~~~text
14
~~~

`Expression` permits Literal và Compound; Compound tiếp tục permits Add và Multiply. Tất cả leaf records implement trực tiếp một trong các permitted interfaces phù hợp, đồng thời là Expression gián tiếp.

## 32. Vì sao một class trong permits phải là **direct** child?

Sai:

~~~java
sealed class Parent permits Child, Grandchild {}
non-sealed class Child extends Parent {}
final class Grandchild extends Child {}
~~~

`Grandchild` **không trực tiếp extends Parent**, nên không được listed như một direct permitted subclass của Parent.

Đúng:

~~~java
sealed class Parent permits Child {}
non-sealed class Child extends Parent {}
final class Grandchild extends Child {}
~~~

Hoặc nếu muốn Grandchild trực tiếp extends Parent, nó phải sửa superclass declaration để thực sự `extends Parent` (và tuân thủ những dependencies/constructors liên quan).

### Quy tắc kiểm tra nhanh

Với từng tên trong `permits` của `Parent`, đi tới declaration đó và đọc `extends Parent` hoặc `implements Parent`/`extends Parent` với interface theo đúng trường hợp. Không thấy quan hệ **trực tiếp** thì không đúng.

## 33. Chương trình chạy: compiler kiểm soát root direct children

Tạo **`DirectChildDemo.java`**:

~~~java
public class DirectChildDemo {
    sealed interface Root permits Alpha, Beta {}

    record Alpha(int value) implements Root {}

    final static class Beta implements Root {}

    static String type(Root root) {
        if (root instanceof Alpha) {
            return "alpha";
        }
        if (root instanceof Beta) {
            return "beta";
        }
        throw new IllegalStateException();
    }

    public static void main(String[] args) {
        System.out.println(type(new Alpha(1)));
        System.out.println(type(new Beta()));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 DirectChildDemo.java
java DirectChildDemo
~~~

Stdout:

~~~text
alpha
beta
~~~

Cả Alpha và Beta trực tiếp implements Root và nằm trong permits list. Nếu thêm `class Gamma implements Root` không có trong permits, javac sẽ từ chối.

## 34. Trong sealed interface: class được permits phải thực sự implements trực tiếp

Một trường hợp dễ nhầm:

~~~java
sealed interface Root permits A {}

non-sealed interface A extends Root {}

final class C implements A {}
~~~

`C` là Root **gián tiếp**, và hợp lệ dù không nằm trong Root.permits.

Ngược lại:

~~~java
// final class C implements Root {} // Không hợp lệ nếu C không permitted.
~~~

Giới hạn áp dụng cho direct extension/implementation edge của sealed type, không áp dụng từng subclass đến vô tận sau non-sealed branch.

## 35. Chương trình chạy: interface con làm cổng mở rộng

Tạo **`ExtensionPointDemo.java`**:

~~~java
public class ExtensionPointDemo {
    sealed interface Command permits BuiltinCommand, PluginCommand {}

    record BuiltinCommand(String name) implements Command {}

    non-sealed interface PluginCommand extends Command {
        String execute();
    }

    static final class EchoPlugin implements PluginCommand {
        @Override
        public String execute() {
            return "echo";
        }
    }

    public static void main(String[] args) {
        Command builtin = new BuiltinCommand("help");
        Command plugin = new EchoPlugin();

        System.out.println(builtin instanceof Command);
        System.out.println(((PluginCommand) plugin).execute());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ExtensionPointDemo.java
java ExtensionPointDemo
~~~

Stdout:

~~~text
true
echo
~~~

Cấu trúc này cho phép một sealed root đại diện cho **vài loại lớn được kiểm soát**, trong đó một loại là extension interface non-sealed.

## 36. Records là permitted leaves tự nhiên

`record` là class **implicitly final**, nên rất phù hợp làm leaf của sealed interface:

~~~java
sealed interface Payment permits Cash, Card {}
record Cash(int cents) implements Payment {}
record Card(String lastFour) implements Payment {}
~~~

Permits kiểm soát **kiểu con trực tiếp**; record components mô tả payload của từng variant. Record không tự bảo đảm deep immutability nếu chứa mutable components. Các tổ hợp thực tế abstract/record/enum và các giới hạn kế thừa ở bài **Kết hợp sealed với lớp abstract, record và enum**; ví dụ runnable ngay sau mục này vẫn minh họa record variants.

## 37. Chương trình chạy: records được permits

Tạo **`SealedRecordsDemo.java`**:

~~~java
public class SealedRecordsDemo {
    sealed interface Payment permits Cash, Card {}

    record Cash(int cents) implements Payment {
        Cash {
            if (cents < 0) {
                throw new IllegalArgumentException("cents");
            }
        }
    }

    record Card(String lastFour) implements Payment {
        Card {
            if (lastFour == null || lastFour.length() != 4) {
                throw new IllegalArgumentException("lastFour");
            }
        }
    }

    public static void main(String[] args) {
        Payment a = new Cash(100);
        Payment b = new Card("1234");

        System.out.println(a);
        System.out.println(b);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedRecordsDemo.java
java SealedRecordsDemo
~~~

Stdout:

~~~text
Cash[cents=100]
Card[lastFour=1234]
~~~

`Cash` và `Card` đều final vì là records; permitted list của Payment là hoàn chỉnh với hai direct implementations này.

## 38. Sealed interfaces và enum

`enum` có thể là một **direct permitted implementation** của sealed interface. Danh sách `permits` liệt kê **enum type**, không liệt kê từng enum constant:

~~~java
sealed interface Action permits FixedAction, CustomAction {}
enum FixedAction implements Action { START, STOP }
record CustomAction(String name) implements Action {}
~~~

Enum dùng quy tắc đặc biệt: một enum declaration được coi implicitly final hoặc sealed tùy việc có constant-specific class bodies, không cần tác giả viết `final enum`. Mọi constants vẫn thuộc cùng enum type; chúng không thành nhiều direct permitted types. Trường hợp enum constant bodies có giải thích sâu tại bài **Kết hợp sealed với lớp abstract, record và enum**.

## 39. Chương trình chạy: enum permitted trực tiếp

Tạo **`SealedEnumDemo.java`**:

~~~java
public class SealedEnumDemo {
    sealed interface Command permits Fixed, Custom {}

    enum Fixed implements Command {
        START, STOP
    }

    record Custom(String name) implements Command {}

    public static void main(String[] args) {
        Command a = Fixed.START;
        Command b = new Custom("build");

        System.out.println(a);
        System.out.println(b);
        System.out.println(Fixed.START instanceof Command);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedEnumDemo.java
java SealedEnumDemo
~~~

Stdout:

~~~text
START
Custom[name=build]
true
~~~

`Command.permits` liệt kê Fixed và Custom, không liệt kê START/STOP; những enum constants là instances, không phải direct subtypes của interface Command.

## 40. Generic sealed classes và interfaces

Sealed types có thể generic:

~~~java
sealed interface Box<T> permits ValueBox, EmptyBox {}

record ValueBox<T>(T value) implements Box<T> {}

record EmptyBox<T>() implements Box<T> {}
~~~

Ngôn ngữ kiểm tra generic supertype signatures và trực tiếp permission. `permits` chỉ liệt kê **tên của kiểu được phép**, không liệt kê từng generic instantiation:

~~~java
// permits ValueBox<String>, ValueBox<Integer> // Sai ý tưởng.
~~~

Java generics chủ yếu dùng type erasure; một generic class declaration vẫn là một permitted type, không phải một subtype mới cho mỗi type argument.

## 41. Chương trình chạy: generic sealed hierarchy

Tạo **`GenericSealedDemo.java`**:

~~~java
public class GenericSealedDemo {
    sealed interface Maybe<T> permits Present, Absent {}

    record Present<T>(T value) implements Maybe<T> {}

    record Absent<T>() implements Maybe<T> {}

    static <T> String show(Maybe<T> maybe) {
        if (maybe instanceof Present<?> present) {
            return "present:" + present.value();
        }
        if (maybe instanceof Absent<?>) {
            return "absent";
        }
        throw new IllegalStateException();
    }

    public static void main(String[] args) {
        Maybe<String> first = new Present<>("Java");
        Maybe<Integer> second = new Absent<>();

        System.out.println(show(first));
        System.out.println(show(second));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 GenericSealedDemo.java
java GenericSealedDemo
~~~

Stdout:

~~~text
present:Java
absent
~~~

Present và Absent là generic records, được phép implements Maybe<T> trực tiếp. `Maybe.permits` không cần nêu String/Integer.

## 42. Multiple interfaces: phải thỏa tất cả sealed parents

Một class có thể implements nhiều interfaces. Nếu nó trực tiếp implements hai sealed interfaces, cả hai direct permission lists phải cho phép class đó:

~~~java
sealed interface A permits C {}
sealed interface B permits C {}

final class C implements A, B {}
~~~

Nếu B không permits C, C không thể implements B trực tiếp dù A đã permits nó.

Trong thực tế, types có nhiều contracts cần review kỹ hierarchy boundaries; sealed permission là **theo từng parent edge**, không có “quyền chung” khi một interface đã chấp thuận.

## 43. Chương trình chạy: implements hai sealed interfaces

Tạo **`MultipleSealedParentsDemo.java`**:

~~~java
public class MultipleSealedParentsDemo {
    sealed interface Readable permits Combined {
        String read();
    }

    sealed interface Writable permits Combined {
        void write(String value);
    }

    static final class Combined implements Readable, Writable {
        private String value = "";

        @Override
        public String read() {
            return value;
        }

        @Override
        public void write(String value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        Combined object = new Combined();
        Readable readable = object;
        Writable writable = object;

        writable.write("Java");
        System.out.println(readable.read());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 MultipleSealedParentsDemo.java
java MultipleSealedParentsDemo
~~~

Stdout:

~~~text
Java
~~~

Cả Readable và Writable đều permits Combined. Sealed không đồng nghĩa object bất biến; Combined ở ví dụ này có mutable state.

## 44. Modifier `non-sealed` không tự biến class thành public

Một `non-sealed class` vẫn tuân thủ access modifiers như package-private, public, protected/private nested classes theo vị trí.

Ví dụ:

~~~java
sealed class Root permits Branch {}
non-sealed class Branch extends Root {}
~~~

Nếu Branch package-private, code từ package khác không thể tự `extends Branch` bằng cách chỉ dựa vào modifier non-sealed. Khả năng mở rộng thực tế phụ thuộc **tập hợp**: accessibility, constructors, package/module boundaries và những restrictions khác.

Đọc `non-sealed` là “loại bỏ sealing restriction của nhánh này”, không phải “bỏ mọi Java access rule”.

## 45. Sealed type kiểm soát direct inheritance, không kiểm soát method overrides

Một sealed class vẫn có:
- `final` methods không được override;
- `abstract` methods cần implementation;
- concrete virtual methods có thể override;
- private fields và methods;
- constructors với access restrictions.

`permits` không thay thế method visibility/override rules.

Nếu mục tiêu là cấm override một method nhưng vẫn cho phép subclassing một số types, dùng `final method` đúng chỗ. Nếu mục tiêu giới hạn **ai được subclass**, dùng sealed type.

Ví dụ:

~~~java
abstract sealed class Task permits LocalTask {
    final String category() {
        return "task";
    }

    abstract void run();
}

final class LocalTask extends Task {
    @Override
    void run() {
    }
}
~~~

LocalTask không thể override `category()` vì method final, độc lập với permits.

## 46. Chương trình chạy: final method bên trong sealed hierarchy

Tạo **`FinalMethodSealedDemo.java`**:

~~~java
public class FinalMethodSealedDemo {
    static abstract sealed class Task permits PrintTask {
        final String category() {
            return "task";
        }

        abstract String execute();
    }

    static final class PrintTask extends Task {
        @Override
        String execute() {
            return "printed";
        }
    }

    public static void main(String[] args) {
        Task task = new PrintTask();

        System.out.println(task.category());
        System.out.println(task.execute());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 FinalMethodSealedDemo.java
java FinalMethodSealedDemo
~~~

Stdout:

~~~text
task
printed
~~~

Hai tầng kiểm soát khác nhau: root sealed hạn chế subclass list; method final hạn chế override hành vi category.

## 47. Reflection: `isSealed()` và `getPermittedSubclasses()`

Java 17 cung cấp Reflection trên `Class`:

- `Class.isSealed()` → true nếu class/interface là sealed.
- `Class.getPermittedSubclasses()` → mảng `Class<?>` đại diện cho **direct permitted subclasses/implementations** của type sealed.
- Với type không sealed, `getPermittedSubclasses()` trả `null` theo API contract.
- Thứ tự duyệt/hiển thị nên được kiểm soát nếu output/logging cần ổn định.

Đừng nhầm `getPermittedSubclasses()` với “liệt kê mọi transitive descendant trong toàn chương trình”. Reflection trả danh sách direct permissions, không tự duyệt sâu qua non-sealed branches.

### Lưu ý

Reflection không thay khả năng compiler kiểm tra source code. Nó giúp inspection/debug/framework tooling; đừng thiết kế plugin loader dựa trên giả định có thể tự bổ sung direct permitted type sau runtime.

## 48. Chương trình chạy: metadata của sealed hierarchy

Tạo **`SealedReflectionDemo.java`**:

~~~java
import java.util.Arrays;

public class SealedReflectionDemo {
    sealed interface Root permits Alpha, Beta {}

    record Alpha(int value) implements Root {}

    record Beta(String value) implements Root {}

    public static void main(String[] args) {
        System.out.println("sealed=" + Root.class.isSealed());
        System.out.println("alpha sealed=" + Alpha.class.isSealed());

        String[] names = Arrays.stream(
                Root.class.getPermittedSubclasses())
                .map(Class::getSimpleName)
                .sorted()
                .toArray(String[]::new);

        System.out.println(Arrays.toString(names));
        System.out.println("alpha permits=null=" +
                (Alpha.class.getPermittedSubclasses() == null));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedReflectionDemo.java
java SealedReflectionDemo
~~~

Stdout:

~~~text
sealed=true
alpha sealed=false
[Alpha, Beta]
alpha permits=null=true
~~~

Code sort names để tránh phụ thuộc thứ tự Reflection trả mảng. `Alpha` là record final, không phải sealed.

## 49. Không cần tạo một instance để truy vấn permissions

`Root.class.getPermittedSubclasses()` là metadata query. Nó không tạo `new Alpha()` hoặc `new Beta()`.

Danh sách permits là **compile-time class hierarchy contract**, không là service registry của object instances. Nếu cần runtime registry/factory, hãy thiết kế API riêng để tạo variant objects hoặc đọc configuration.

Có thể có class permitted abstract hoặc non-sealed, không có constructor tạo instance trực tiếp phù hợp. Do đó phép liệt kê Class metadata không tương đương liệt kê những “object values” hợp lệ ngay lập tức.

## 50. Java 17: xử lý variants bằng `instanceof`

Java 17 đã chuẩn hóa pattern variable với `instanceof`:

~~~java
if (value instanceof Success success) {
    return success.message();
}
~~~

Đây là snippet giả định `value`, `Success` và method trả String đã được khai báo. Với `javac --release 17` không bật preview, **pattern switch trên sealed types chưa phải tính năng chuẩn**; dùng polymorphic methods, `if/else instanceof` có fallback hoặc `switch` trên enum thích hợp. Không copy record patterns hoặc switch syntax từ Java release mới vào demo Java 17 rồi coi là code biên dịch mặc định.

## 51. Chương trình chạy: exhaustiveness bằng cấu trúc đơn giản

Tạo **`SealedDispatchDemo.java`**:

~~~java
public class SealedDispatchDemo {
    sealed interface Event permits Created, Deleted {}

    record Created(long id) implements Event {}

    record Deleted(long id) implements Event {}

    static String describe(Event event) {
        if (event instanceof Created created) {
            return "created:" + created.id();
        }
        if (event instanceof Deleted deleted) {
            return "deleted:" + deleted.id();
        }
        throw new IllegalStateException("unhandled event");
    }

    public static void main(String[] args) {
        System.out.println(describe(new Created(7)));
        System.out.println(describe(new Deleted(7)));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedDispatchDemo.java
java SealedDispatchDemo
~~~

Stdout:

~~~text
created:7
deleted:7
~~~

`throw` cuối là defensive fallback trong cách viết if-chains trên Java 17; không nên tuyên bố compiler đã compile-time exhaustiveness-check kiểu chain này như một exhaustive pattern switch từ các Java versions khác.

## 52. Sealed interface + polymorphic method, không cần type tests

Một alternative là cho sealed interface khai báo method:

~~~java
sealed interface Event permits Created, Deleted {
    String describe();
}

record Created(long id) implements Event {
    @Override
    public String describe() {
        return "created:" + id;
    }
}

record Deleted(long id) implements Event {
    @Override
    public String describe() {
        return "deleted:" + id;
    }
}
~~~

Caller gọi `event.describe()` mà không cần if/instanceof.

### Khi nào chọn?

- Nếu behavior **thực sự thuộc từng variant**, polymorphism phù hợp.
- Nếu operation chỉ là một client-specific visualization/serialization concern, có thể đặt function ngoài hierarchy.
- Nếu thêm nhiều operations vào base interface làm các variants phụ thuộc services không cần thiết, tách service/controller.

Sealed kiểm soát hierarchy; cách tổ chức behavior là quyết định thiết kế riêng.

## 53. Chương trình chạy: sealed polymorphism

Tạo **`SealedPolymorphismDemo.java`**:

~~~java
public class SealedPolymorphismDemo {
    sealed interface Operation permits Add, Multiply {
        int compute(int a, int b);
    }

    record Add() implements Operation {
        @Override
        public int compute(int a, int b) {
            return a + b;
        }
    }

    record Multiply() implements Operation {
        @Override
        public int compute(int a, int b) {
            return a * b;
        }
    }

    public static void main(String[] args) {
        Operation add = new Add();
        Operation multiply = new Multiply();

        System.out.println(add.compute(3, 4));
        System.out.println(multiply.compute(3, 4));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedPolymorphismDemo.java
java SealedPolymorphismDemo
~~~

Stdout:

~~~text
7
12
~~~

Permits quyết định direct variants, còn `compute` cung cấp interface behavior mà caller dùng chung.

## 54. Sealed hierarchy không phải enum

Enum:

~~~java
enum Status {
    NEW, ACTIVE, DONE
}
~~~

phù hợp khi có **các constant instances cố định** thuộc một type. Sealed interface:

~~~java
sealed interface Status permits New, Active, Done {}

record New() implements Status {}
record Active(long sinceMillis) implements Status {}
record Done(String result) implements Status {}
~~~

cho phép **các variants khác data shape**, và có thể tạo nhiều record instances cho Active/Done theo constructor arguments.

### Khác biệt chủ chốt

- Enum đóng tập **constant objects**.
- Sealed type đóng tập **direct subtype declarations** (hoặc mở có kiểm soát qua non-sealed).
- Một permitted class có thể tạo nhiều objects.
- Enum `values()` cho constants; sealed interface không tự có `values()` để tạo mọi variant instances.

Chọn dựa vào domain model, không chỉ mong muốn “finite”.

## 55. Chương trình chạy: enum và sealed model khác nhau

Tạo **`EnumVsSealedDemo.java`**:

~~~java
public class EnumVsSealedDemo {
    enum SimpleState {
        READY, DONE
    }

    sealed interface DetailedState permits Ready, Done {}

    record Ready() implements DetailedState {}

    record Done(String message) implements DetailedState {}

    public static void main(String[] args) {
        System.out.println(SimpleState.READY);
        System.out.println(SimpleState.values().length);

        DetailedState first = new Done("A");
        DetailedState second = new Done("B");

        System.out.println(first);
        System.out.println(second);
        System.out.println(first.equals(second));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 EnumVsSealedDemo.java
java EnumVsSealedDemo
~~~

Stdout:

~~~text
READY
2
Done[message=A]
Done[message=B]
false
~~~

Sealed permits Done class, không giới hạn chỉ một Done object. Enum constant Done (nếu có) sẽ là một instance cố định thuộc declaring enum.

## 56. Thêm một variant: cần cập nhật gì?

Ví dụ đang công bố `Result permits Ok, Error`. Thêm `Cancelled` nghĩa là phải:

1. Khai direct implementation hợp lệ và sửa `permits` nếu explicit.
2. Đáp ứng final/sealed/non-sealed cùng module/package và accessibility.
3. Cập nhật business dispatch, serialization/UI/schema và regression tests.
4. Kiểm các giả định về tập variants của consumers và chính sách versioning.

Việc mở rộng một **sealed intermediate type** chỉ yêu cầu cập nhật danh sách permitted children của tầng đó, không nhất thiết sửa root; một `non-sealed` branch cho phép thêm descendants mà không sửa whitelist root. Mẫu migration và đánh đổi closed/open API được dạy chính ở bài **So sánh hệ phân cấp đóng với lớp tự do mở rộng**.

## 57. API evolution với `non-sealed` extension point

Một sealed root có thể chứa một nhánh extension hợp lệ:

~~~java
sealed interface Message permits KnownMessage, PluginMessage {}
record KnownMessage(String text) implements Message {}
non-sealed interface PluginMessage extends Message {
    String pluginId();
}
~~~

Plugins implement `PluginMessage`, chứ không tự direct implement root `Message`. Root chỉ có hai **permitted direct branches**, nhưng toàn bộ hậu duệ của nhánh `non-sealed` không hữu hạn. Cách này cần public visibility, module exports, compatibility policy và fallback theo contract. Bài **So sánh hệ phân cấp đóng với lớp tự do mở rộng** phân tích sâu hybrid extension vs open strategy.

## 58. Nested sealed types có thể dễ tổ chức hơn nhiều files

Một outer class có thể chứa sealed interface và permitted nested records:

~~~java
final class Results {
    sealed interface Result permits Success, Failure {}

    record Success(String data) implements Result {}

    record Failure(String error) implements Result {}
}
~~~

Các members có canonical names và visibility theo outer/nested modifiers. Cùng compilation unit nên có thể dùng inferred permits nếu không cần explicit list.

Lợi ích:
- giữ variants gần nhau để dễ review;
- giảm nguy cơ declaration lệch nhau ở source files;
- scopes có thể private/package-private tùy API;
- một-file examples đơn giản.

Nhưng nếu mỗi subtype lớn, tách files trong cùng package/module và explicit permits có thể dễ bảo trì hơn.

## 59. Chương trình chạy: nested sealed hierarchy

Tạo **`NestedSealedDemo.java`**:

~~~java
public class NestedSealedDemo {
    static final class Results {
        sealed interface Result permits Success, Failure {}

        record Success(String data) implements Result {}

        record Failure(String reason) implements Result {}
    }

    public static void main(String[] args) {
        Results.Result first = new Results.Success("ok");
        Results.Result second = new Results.Failure("bad");

        System.out.println(first);
        System.out.println(second);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 NestedSealedDemo.java
java NestedSealedDemo
~~~

Stdout:

~~~text
Success[data=ok]
Failure[reason=bad]
~~~

Các permitted nested records ở cùng source file với parent sealed interface. `Results.Result` là nested interface implicitly static theo Java rules.

## 60. Sealed và interfaces có default methods

Một sealed interface vẫn có thể khai báo default methods:

~~~java
sealed interface Coded permits A, B {
    String code();

    default String display() {
        return "[" + code() + "]";
    }
}

record A() implements Coded {
    @Override
    public String code() {
        return "A";
    }
}

record B() implements Coded {
    @Override
    public String code() {
        return "B";
    }
}
~~~

`permits` không thay method inheritance behavior. Default methods có body được kế thừa nếu không có conflict/override.

Khi dùng multiple interfaces với defaults cùng signature, subtypes phải giải quyết xung đột theo quy tắc Java bình thường. Sealed permission **không** tự chọn default implementation.

## 61. Chương trình chạy: default method trong sealed interface

Tạo **`SealedDefaultMethodDemo.java`**:

~~~java
public class SealedDefaultMethodDemo {
    sealed interface Coded permits A, B {
        String code();

        default String display() {
            return "[" + code() + "]";
        }
    }

    record A() implements Coded {
        @Override
        public String code() {
            return "A";
        }
    }

    record B() implements Coded {
        @Override
        public String code() {
            return "B";
        }
    }

    public static void main(String[] args) {
        Coded first = new A();
        Coded second = new B();

        System.out.println(first.display());
        System.out.println(second.display());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedDefaultMethodDemo.java
java SealedDefaultMethodDemo
~~~

Stdout:

~~~text
[A]
[B]
~~~

Records provide required `code()`; shared formatting lives in default method.

## 62. Sealed không ngăn tạo anonymous subclass khi không permitted

Cú pháp anonymous subclass:

~~~java
Base value = new Base() {
    // ...
};
~~~

sẽ tạo một **anonymous subclass** của Base. Nếu Base là sealed và anonymous class không nằm trong permitted direct subtype declarations, expression này sẽ bị từ chối theo sealing rules.

Với sealed interface:

~~~java
sealed interface Action permits KnownAction {}

final class KnownAction implements Action {}

// Action a = new Action() {}; // Không hợp lệ: anonymous direct implementation.
~~~

Anonymous classes không có canonical names để khai báo tùy ý trong permits list theo cách ordinary named permitted types làm; không dùng chúng để bypass restrictions.

### Dùng permitted branch

Nếu cần one-off implementations, thiết kế non-sealed extension interface/class bên dưới sealed root và implement/extend branch đó theo ngữ cảnh phù hợp.

## 63. Sealed và lambda: cần phân biệt SAM target

Một sealed interface có một abstract method, về bề mặt trông giống functional interface:

~~~java
sealed interface Task permits BuiltinTask {
    void run();
}
~~~

Tuy nhiên Java sealed interfaces **không phải functional interfaces hợp lệ** theo functional interface semantics cần cho lambda target. Một lambda implementation không có cách được liệt kê như permitted direct subtype của sealed interface.

Do đó:

~~~java
// Task task = () -> System.out.println("run"); // Không hợp lệ.
~~~

Nếu cần lambda callback, dùng **một functional non-sealed interface**, chẳng hạn `Runnable` hoặc interface riêng `@FunctionalInterface`, ở contract phù hợp.

**Quy tắc thiết kế:** Sealed roots dùng để giới hạn **implementing types**; functional interfaces dùng để cho phép clients cung cấp lambdas linh hoạt. Hai mục đích có thể xung đột ở một interface duy nhất.

## 64. Chương trình chạy: sealed type nhận Runnable thành component

Thay vì dùng lambda trực tiếp làm instance của sealed interface, có thể gói một Runnable vào permitted record:

Tạo **`SealedWithLambdaDemo.java`**:

~~~java
public class SealedWithLambdaDemo {
    sealed interface Command permits NamedCommand, CallbackCommand {
        void execute();
    }

    record NamedCommand(String name) implements Command {
        @Override
        public void execute() {
            System.out.println("named:" + name);
        }
    }

    record CallbackCommand(Runnable action) implements Command {
        CallbackCommand {
            java.util.Objects.requireNonNull(action);
        }

        @Override
        public void execute() {
            action.run();
        }
    }

    public static void main(String[] args) {
        Command first = new NamedCommand("A");
        Command second = new CallbackCommand(
                () -> System.out.println("callback"));

        first.execute();
        second.execute();
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedWithLambdaDemo.java
java SealedWithLambdaDemo
~~~

Stdout:

~~~text
named:A
callback
~~~

Sealed interface vẫn chỉ có hai permitted variants. Lambda implements Runnable, còn permitted CallbackCommand record gói Runnable và implements Command.

## 65. Lỗi: thiếu modifier ở direct permitted class

Ví dụ sai:

~~~java
sealed class Parent permits Child {}

// class Child extends Parent {} // Sai: thiếu final/sealed/non-sealed.
~~~

Đúng:

~~~java
sealed class Parent permits Child {}

final class Child extends Parent {}
~~~

Hoặc nếu cần mở:

~~~java
sealed class Parent permits Child {}

non-sealed class Child extends Parent {}
~~~

Hoặc tiếp tục giới hạn:

~~~java
sealed class Parent permits Child {}

sealed class Child extends Parent permits Grandchild {}

final class Grandchild extends Child {}
~~~

Không sửa bằng cách xóa `sealed` của Parent trừ khi bạn thực sự muốn **mở API**; modifier ở permitted type thể hiện architectural decision quan trọng.

## 66. Lỗi: subtype không nằm trong permits

Ví dụ conceptual:

~~~java
sealed interface Shape permits Circle {}

record Circle(int radius) implements Shape {}

// record Square(int side) implements Shape {} // Compile error.
~~~

`Square` trực tiếp implements Shape nhưng không được Shape cho phép.

Muốn thêm Square:
- sửa `permits Circle, Square`;
- khai báo Square đúng source/module/package boundary;
- đảm bảo subtype phù hợp modifier semantics (record implicitly final);
- cập nhật tests/API behavior.

Không có annotation hoặc reflection API nào thay thế việc sửa trực tiếp sealed hierarchy declaration.

## 67. Lỗi: `permits` một type không phải direct subtype

Sai:

~~~java
sealed interface Root permits A, B {}

non-sealed interface A extends Root {}

// class B implements A {} // B không trực tiếp implements Root.
~~~

Tên B nằm trong permits nhưng declaration chỉ implements A; như vậy B **không phải một direct permitted child của Root**.

Đúng:

~~~java
sealed interface Root permits A {}

non-sealed interface A extends Root {}

class B implements A {}
~~~

Nếu muốn B là direct implementor, đổi declaration quan hệ cho phù hợp và kiểm tra conflict giữa các interface edges.

## 68. Lỗi: dùng `non-sealed` không có sealed supertype trực tiếp

Sai:

~~~java
// non-sealed class Helper {} // Không direct extends sealed type.
~~~

Đúng:

~~~java
sealed class Parent permits Helper {}

non-sealed class Helper extends Parent {}
~~~

Tương tự, non-sealed interface phải trực tiếp extends một sealed interface thích hợp. `non-sealed` không phải synonym của “public/extensible”.

## 69. Lỗi: sealed type với no permitted direct subtype

Sealed type được thiết kế để cho phép một tập direct subtypes. Nếu declaration không có permits và compiler không thể suy luận allowed direct subtypes ở cùng compilation unit, source có thể bị từ chối vì không có permitted subclasses hợp lệ.

Trong thực tế:
- khai báo types được phép;
- hoặc nếu muốn tuyệt đối không subclass, hãy dùng `final class` cho concrete class;
- với interface cần contract nhưng không có implementations hiện tại, cân nhắc liệu nó thật sự cần sealed ngay thời điểm này.

Không được dùng `sealed` như một cách viết khác của `final`. Đó là hai ý định khác nhau.

## 70. Compile-time tests cho hierarchy

Nhiều restrictions của sealed/permits kiểm tra được ngay lúc compile. Hãy chủ động thử:
- một child có trong permits và modifier đúng → compile.
- một direct child không có trong permits → compile error.
- một child listed nhưng không extends/implements parent trực tiếp → compile error.
- child dùng plain class modifier thiếu final/sealed/non-sealed → compile error.
- non-sealed không có sealed direct supertype → compile error.
- wrong package/module boundary → compile error.
- child cố extends final leaf → compile error.
- child tiếp tục extends sealed branch nhưng không được branch permits → compile error.

Các negative tests phải chạy trong môi trường riêng và **kỳ vọng javac exit nonzero**; không trộn những đoạn sai vào chương trình cần chạy để minh họa stdout.

## 71. Chương trình chạy: unit-like assertions cho variants

Tạo **`SealedContractTestDemo.java`**:

~~~java
public class SealedContractTestDemo {
    sealed interface Expr permits IntValue, Negate {
        int evaluate();
    }

    record IntValue(int value) implements Expr {
        @Override
        public int evaluate() {
            return value;
        }
    }

    record Negate(Expr value) implements Expr {
        @Override
        public int evaluate() {
            return -value.evaluate();
        }
    }

    static void check(int actual, int expected) {
        if (actual != expected) {
            throw new AssertionError(
                    actual + " != " + expected);
        }
    }

    public static void main(String[] args) {
        Expr one = new IntValue(5);
        Expr two = new Negate(one);

        check(one.evaluate(), 5);
        check(two.evaluate(), -5);
        check(new Negate(two).evaluate(), 5);

        System.out.println("all behavior tests PASS");
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedContractTestDemo.java
java SealedContractTestDemo
~~~

Stdout:

~~~text
all behavior tests PASS
~~~

Compiler xác nhận direct permitted types; tests xác nhận business method behavior, điều compiler không tự chứng minh.

## 72. Sealed có làm code thread-safe hay immutable không?

Không. Sealed chỉ giới hạn type hierarchy. Một permitted non-sealed class có mutable state; một final permitted class cũng có mutable fields nếu được định nghĩa như vậy.

Ví dụ:

~~~java
sealed interface Counter permits MutableCounter {}

final class MutableCounter implements Counter {
    int value;

    void increment() {
        value++;
    }
}
~~~

Đây là mutable class dù Counter sealed và MutableCounter final. `value++` không atomic trong concurrent access.

Tách ba khái niệm:
- **Sealing:** ai được kế thừa/implement trực tiếp?
- **Final field/immutability:** state có thể mutate?
- **Thread safety:** concurrency operations được bảo đảm như thế nào?

Không dùng một keyword để kết luận cho hai vấn đề còn lại.

## 73. API design: sealed hierarchy hay ordinary extensible interface?

Chọn sealed nếu team/module thực sự sở hữu **một tập direct variants có giới hạn** và muốn consumers nhận ra mọi nhánh chính. Chọn ordinary open interface nếu mục tiêu là nhiều plugins do bên ngoài implement và không thể liệt kê trước. Cần vừa có built-in variants được kiểm soát vừa cho plugin? Dùng permitted `non-sealed` extension point phù hợp, như ở mục trước. Bài **So sánh hệ phân cấp đóng với lớp tự do mở rộng** đưa ra cây quyết định, OCP, composition và kế hoạch versioning; ở bài cú pháp này chỉ cần hiểu cách các declarations thực hiện lựa chọn ấy.

## 74. Versioning: thêm nhánh có thể ảnh hưởng consumers

Thêm `Pending` vào permitted direct variants có thể khiến consumers chưa xử lý nhánh mới, thay đổi serialization schema, metadata reflection hoặc assumptions về exhaustiveness. Vì vậy cần release notes, tests và chiến lược compatibility; compiler không tự làm cho mọi business method hiểu variant mới. Bài **So sánh hệ phân cấp đóng với lớp tự do mở rộng** và bài **Khi nào sealed phù hợp để mô hình hóa các loại giá trị** phân tích sâu API evolution từ góc nhìn người dùng và thiết kế miền.

## 75. Cẩn trọng với public sealed classes có constructor quá rộng

Một `public sealed class` nếu **concrete** và constructor accessible vẫn có thể được instantiate trực tiếp; `sealed` **không đồng nghĩa** `abstract`. Nếu domain chỉ cho phép các variants chuyên biệt, cân nhắc `abstract sealed class` và constructor có visibility phù hợp.

Trong mọi trường hợp, constructor cần bảo vệ invariants, kể cả khi only permitted children được phép extend root. `permits` không cấp quyền gọi private constructor, không thay validation và không bảo đảm immutability. Chi tiết về state/constructor chung thuộc bài **Kết hợp sealed với lớp abstract, record và enum**.

## 76. Reflection và danh sách transitive descendants

`getPermittedSubclasses()` trả direct permissions. Nếu muốn xây một báo cáo cây, bạn có thể đệ quy qua **những child vẫn sealed**; khi gặp:
- final leaf: không có subclasses;
- non-sealed branch: không thể suy luận toàn bộ future descendant types chỉ từ root permits;
- sealed child: có danh sách direct permitted subtypes riêng.

Vì vậy một công cụ code generation có thể trình bày **controlled branches**, nhưng không nên tuyên bố “liệt kê toàn bộ runtime subclasses” nếu tồn tại non-sealed extension point.

## 77. Chương trình chạy: kiểm tra từng nhánh bằng metadata

Tạo **`SealedHierarchyMetadataDemo.java`**:

~~~java
public class SealedHierarchyMetadataDemo {
    sealed interface Root permits Leaf, Branch {}

    record Leaf(int n) implements Root {}

    non-sealed interface Branch extends Root {}

    public static void main(String[] args) {
        System.out.println("root sealed=" +
                Root.class.isSealed());
        System.out.println("leaf sealed=" +
                Leaf.class.isSealed());
        System.out.println("branch sealed=" +
                Branch.class.isSealed());

        System.out.println("root direct allowed=" +
                Root.class.getPermittedSubclasses().length);
        System.out.println("branch permits=null=" +
                (Branch.class.getPermittedSubclasses() == null));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SealedHierarchyMetadataDemo.java
java SealedHierarchyMetadataDemo
~~~

Stdout:

~~~text
root sealed=true
leaf sealed=false
branch sealed=false
root direct allowed=2
branch permits=null=true
~~~

Root là sealed, Leaf là final record, Branch là non-sealed interface. Chỉ Root có direct permits list trong Reflection metadata.

## 78. Những hiểu nhầm phổ biến

| Hiểu nhầm | Điều đúng trong Java 17 |
| --- | --- |
| `sealed` cấm mọi subclasses | Nó cho phép direct subtypes trong permits list |
| `sealed` giống `final` | Final đóng hoàn toàn, sealed mở có kiểm soát |
| `permits` tự làm class kia extends parent | Child phải khai báo relation trực tiếp |
| Child liệt kê có thể thiếu modifier | Ordinary direct child phải final/sealed/non-sealed |
| `non-sealed` có nghĩa mọi class đều public | Accessibility vẫn áp dụng |
| `non-sealed` dùng được trên bất kỳ class | Cần sealed direct supertype |
| `final interface` hợp lệ | Interface không dùng final modifier |
| Parent cần liệt kê mọi hậu duệ gián tiếp | Chỉ direct subtypes |
| Java suy luận permits bằng cách quét package | Inference giới hạn same compilation unit |
| Subclass khác package trong unnamed module vẫn được phép | Phải same package |
| Subclass khác named module vẫn được phép | Phải same named module |
| `permits` bỏ qua constructor access rules | Không |
| Sealed class mặc định abstract | Không; class có thể concrete |
| Sealed interface tự có `values()` | Không, enum mới có values() API |
| Permits enum constants thay enum type | Phải liệt kê type |
| Record cần khai báo `final` khi được permits | Record implicitly final |
| Sealed interface một SAM dùng lambda trực tiếp như functional interface | Sealed interface không là lambda functional target hợp lệ |
| Sealed type tự deep immutable | Không |
| Sealed type tự thread-safe | Không |
| `getPermittedSubclasses` trả mọi transitive subclasses | Chỉ direct permissions |
| `instanceof` type pattern là preview trên Java 17 | Đã chuẩn, dùng được |
| Pattern switch là chuẩn không-preview trên Java 17 | Không; tránh trong ví dụ Java 17 tiêu chuẩn |
| Thêm variant không ảnh hưởng API | Có thể ảnh hưởng consumers và behavior |
| Sealed là lựa chọn tốt cho mọi plugin API | Plugins thường cần open extension point |

## 79. Bài tập 1 — Khai báo sealed class

Yêu cầu: Vehicle chỉ cho phép Car và Truck trực tiếp kế thừa, cả hai đều là leaf classes.

**Đáp án:**

~~~java
sealed class Vehicle permits Car, Truck {}

final class Car extends Vehicle {}

final class Truck extends Vehicle {}
~~~

Hãy chỉ rõ vì sao `Vehicle` không nhất thiết abstract: sealed giới hạn subclasses, không giới hạn instantiation nếu class concrete và constructor accessible.

## 80. Bài tập 2 — Sealed interface với records

Yêu cầu: Response có variants Success(String) và Failure(String).

**Đáp án:**

~~~java
sealed interface Response permits Success, Failure {}

record Success(String value) implements Response {}

record Failure(String error) implements Response {}
~~~

Hai records tự là final theo language rules. Thêm validation nếu null hoặc blank input bị cấm.

## 81. Bài tập 3 — Child thiếu modifier

~~~java
sealed class A permits B {}

// class B extends A {}
~~~

**Đáp án:** Nếu uncomment, B thiếu một trong `final`, `sealed`, `non-sealed`. Nếu không muốn subclasses của B, viết `final class B extends A {}`.

## 82. Bài tập 4 — Hậu duệ gián tiếp

~~~java
sealed class A permits B {}
non-sealed class B extends A {}
class C extends B {}
~~~

C có hợp lệ dù không ở A.permits không?

**Đáp án:** Có. C không trực tiếp extends A, mà extends B là nhánh non-sealed.

## 83. Bài tập 5 — Liệt kê sai tầng

~~~java
sealed class A permits B, C {}
non-sealed class B extends A {}
class C extends B {}
~~~

**Đáp án:** Sai vì C không phải direct subclass A. Sửa A permits B, bỏ C khỏi root list.

## 84. Bài tập 6 — Inferred permits

~~~java
sealed interface Event {}
record Started(int id) implements Event {}
record Stopped(int id) implements Event {}
~~~

Cả ba được khai báo trong một compilation unit, không explicit permits.

**Đáp án:** Compiler có thể suy luận Started và Stopped là direct permitted implementations, miễn các rules còn lại đúng.

## 85. Bài tập 7 — Khác package trong unnamed module

Result được khai báo package a; record Ok ở package b; cả hai nằm trong unnamed module. Parent ghi `permits b.Ok`.

**Đáp án:** Không hợp lệ: direct permitted subclass/implementation phải cùng package khi sealed type thuộc unnamed module. Chuyển cùng package hoặc thiết kế named module phù hợp nếu thực sự cần packages khác nhau.

## 86. Bài tập 8 — Named module

Sealed interface thuộc named module M, permitted record ở package khác nhưng cũng trong module M; accessible hợp lệ.

**Đáp án:** Có thể hợp lệ. Named-module rule yêu cầu cùng module, không bắt buộc cùng package. Vẫn cần direct inheritance/visibility/modifier đúng.

## 87. Bài tập 9 — Interface con

~~~java
sealed interface Root permits Child {}
// final interface Child extends Root {} // Sai.
~~~

**Đáp án:** Interface không được final. Dùng `sealed interface Child extends Root permits Leaf {}` hoặc `non-sealed interface Child extends Root {}`, tùy chính sách mở rộng.

## 88. Bài tập 10 — Sealed có immutable không?

Một `final class Counter implements SealedCounter` giữ `int count` và method `increment()`.

**Đáp án:** Không tự immutable hay thread-safe. final chỉ chặn subclassing, sealed chỉ kiểm soát permitted hierarchy. Concurrent increments phải xét synchronization riêng.

## 89. Bài tập 11 — Reflection

`Root.class.isSealed()` true, `Root.class.getPermittedSubclasses()` có length 2. Điều này chứng minh có đúng hai object instances của Root không?

**Đáp án:** Không. Metadata nói có hai direct permitted subtype declarations, không giới hạn số objects tạo bởi mỗi subtype. Nếu non-sealed branch tồn tại, descendants gián tiếp cũng có thể mở rộng.

## 90. Bài tập 12 — Sealed interface và lambda

Có sealed interface Task với method `void run()` và permitted record wrapper. Viết trực tiếp `Task t = () -> ...;` được không?

**Đáp án:** Không. Sealed interface không là functional interface target hợp lệ cho lambda. Có thể dùng `Runnable` làm callback và gói vào permitted record `CallbackTask(Runnable action) implements Task`.

## 91. Bài tập 13 — Tạo class ngoài permits

~~~java
sealed interface Expression permits Literal {}
record Literal(int value) implements Expression {}
// record Add(Expression a, Expression b) implements Expression {}
~~~

**Đáp án:** Nếu uncomment Add, compiler từ chối vì Add không nằm trong permits. Muốn thêm variant, khai báo `permits Literal, Add` và review logic xử lý expression.

## 92. Bài tập 14 — Final leaf

~~~java
sealed class Base permits Leaf {}
final class Leaf extends Base {}
// class More extends Leaf {} // Sai.
~~~

**Đáp án:** More không thể extends Leaf vì Leaf final, dù mọi type ở cùng compilation unit và Base đã permits Leaf.

## 93. Bài tập 15 — Mở một nhánh extension

Thiết kế Command có hai branches: Builtin (đóng) và Plugin (cho third-party implement).

**Đáp án gợi ý:**

~~~java
sealed interface Command permits Builtin, Plugin {}

record Builtin(String name) implements Command {}

non-sealed interface Plugin extends Command {
    String pluginId();
}
~~~

Third-party classes sẽ `implements Plugin` theo accessibility contract, không implements Command trực tiếp.

## 94. Bài tập 16 — Tác động API

Ban đầu sealed Result permits Success, Failure; sau đó thêm Cancelled.

**Đáp án:** Cập nhật permits list và declaration, xét business handlers, schema, tests và compatibility. Sealed constraint không làm client tự hiểu behavior của Cancelled.

## 95. Bài tập 17 — Sealed hay enum?

Chỉ có các states NEW, ACTIVE, DONE; không mang data khác nhau.

**Đáp án:** Enum thường đơn giản. Nếu mỗi state variant chứa data shape khác nhau như Active(startTime), Done(result), sealed interface + records có thể phù hợp hơn.

## 96. Bài tập 18 — Methods chung của sealed superclass

Một abstract sealed class có protected constructor và final method category(), permitted subclasses override abstract execute().

**Đáp án:** Hợp lệ. Sealed kiểm soát direct subclass list; final method ngăn override; abstract method vẫn buộc concrete subclasses implement.

## 97. Quy trình thiết kế permits list

**Bước 1 — Đặt tên kiểu gốc.** Nó đại diện cho category/abstraction nào?

**Bước 2 — Quyết định đóng hay mở.** Nếu cần arbitrary extensions, thường không dùng sealed root, hoặc thiết kế một nhánh non-sealed.

**Bước 3 — Xác định direct variants.** Liệt kê đúng những class/interface types trực tiếp extends/implements root.

**Bước 4 — Chọn abstract/concrete root.** Sealed không tự abstract; quyết định constructor/base behavior.

**Bước 5 — Chọn modifier từng permitted child.** Final để kết thúc; sealed để giới hạn tiếp; non-sealed để mở branch. Với record/enum áp dụng special rules.

**Bước 6 — Chọn explicit hoặc inferred permits.** Suy luận chỉ khi direct types ở cùng compilation unit; nhiều files dùng explicit.

**Bước 7 — Kiểm tra package/module.** Same named module; unnamed module → same package.

**Bước 8 — Kiểm tra accessibility/constructors.** Listed name không miễn inheritance access rules.

**Bước 9 — Kiểm tra nested hierarchy.** Nhánh sealed con có permits list riêng; non-sealed mở descendants.

**Bước 10 — Test compiler và runtime.** Negative compile tests và behavior tests cho từng variant.

**Bước 11 — Xem xét versioning.** Thêm direct subtype là contract change cần review.

**Bước 12 — Xem xét mô hình thay thế.** Enum, ordinary interface, named class, composition hoặc sealed+records.

## 98. Checklist cuối bài

- [ ] Tôi biết Java 17 hỗ trợ sealed class/interface không cần preview.
- [ ] Tôi viết được `sealed class Parent permits ChildA, ChildB`.
- [ ] Tôi viết được `sealed interface Parent permits A, B`.
- [ ] Tôi phân biệt `permits` với `extends` và `implements`.
- [ ] Tôi biết permits chỉ áp dụng cho direct subtypes.
- [ ] Tôi không đưa grandchildren vào root permits list.
- [ ] Tôi biết direct child phải xuất hiện trong explicit permits nếu parent có list.
- [ ] Tôi biết class direct child chọn final/sealed/non-sealed.
- [ ] Tôi biết interface direct child chọn sealed/non-sealed, không final.
- [ ] Tôi biết record implicitly final nên là permitted leaf tự nhiên.
- [ ] Tôi biết enum permitted list liệt kê enum type, không enum constants.
- [ ] Tôi hiểu non-sealed mở branch chứ không mở root direct permits.
- [ ] Tôi biết sealed child có permits list riêng.
- [ ] Tôi biết root sealed có thể concrete hoặc abstract.
- [ ] Tôi không nhầm final class với sealed class.
- [ ] Tôi biết non-sealed không dùng tùy ý nếu không có direct sealed supertype.
- [ ] Tôi biết Java suy luận permits khi direct types cùng compilation unit.
- [ ] Tôi biết inference không tự dò toàn bộ package.
- [ ] Tôi biết named module yêu cầu permitted direct types ở cùng module.
- [ ] Tôi biết unnamed module yêu cầu same package.
- [ ] Tôi không cho rằng permits loại bỏ visibility/constructor rules.
- [ ] Tôi hiểu sealed không tự bất biến, thread-safe hay singleton.
- [ ] Tôi biết generic sealed interface có permitted generic records.
- [ ] Tôi biết `Class.isSealed()`.
- [ ] Tôi biết `Class.getPermittedSubclasses()` trả direct types, không instances.
- [ ] Tôi biết `instanceof` patterns chuẩn trên Java 17.
- [ ] Tôi không dùng pattern switch/record patterns như Java 17 non-preview syntax.
- [ ] Tôi biết sealed interface không dùng trực tiếp làm lambda target.
- [ ] Tôi biết thiết kế wrapper record với Runnable nếu cần callback.
- [ ] Tôi biết khi nào sealed hierarchy tốt hơn enum.
- [ ] Tôi biết khi nào ordinary extensible interface tốt hơn sealed.
- [ ] Tôi đánh giá API evolution khi sửa permits list.
- [ ] Tôi có thể giải thích compiler errors trong các bài tập.
- [ ] Tôi kiểm tra toàn bộ hierarchy và contracts bằng tests.

**Kết luận:** `sealed` và `permits` trong Java 17 định nghĩa **ranh giới mở rộng trực tiếp của kiểu dữ liệu**. Parent có quyền công bố những direct classes/interfaces được phép, còn mỗi permitted type phải chủ động chọn chính sách tiếp tục mở rộng (`final`, `sealed`, `non-sealed` hoặc special implicit semantics của record/enum). Danh sách có thể viết tường minh hoặc được suy luận khi direct types ở cùng compilation unit; các restrictions same-module/same-package và accessibility vẫn luôn áp dụng. Hãy dùng sealed để mô hình hóa **controlled hierarchies**, không nhầm nó với immutability, singleton hoặc runtime registry.
