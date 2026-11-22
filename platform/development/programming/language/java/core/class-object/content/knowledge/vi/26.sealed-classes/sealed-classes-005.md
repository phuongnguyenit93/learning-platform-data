# Ràng buộc cùng module hoặc cùng package của lớp sealed trong Java 17

## Mục tiêu bài học

Sau khi hoàn thành, bạn có thể:

- Hiểu `sealed` giới hạn **direct subclasses** của sealed class và **direct implementations/subinterfaces** của sealed interface thông qua `permits`.
- Áp dụng chính xác quy tắc Java 17: khi sealed type thuộc **named module**, mọi permitted direct subtype phải thuộc **cùng named module**; khi sealed type thuộc **unnamed module**, chúng phải thuộc **cùng package**.
- Phân biệt khái niệm **named module**, **unnamed module**, **package**, **compilation unit**, **classpath**, **module path**, cùng Maven/Gradle project và cùng physical directory.
- Tổ chức code và biên dịch một dự án sealed class **classpath cùng package**, dù mỗi class nằm một source file riêng.
- Tổ chức code và biên dịch một dự án JPMS có sealed interface trong package API và các permitted implementations thuộc **hai package khác nhau nhưng cùng named module**.
- Chẩn đoán lỗi khi declared permitted subtype khác package trong unnamed module, khác named module, không accessible hoặc không trực tiếp extends/implements parent.
- Giải thích `permits` **chỉ liệt kê trực tiếp**, không liệt kê grandchildren; cách một `non-sealed` child có thể làm extension point vượt package/module.
- Hiểu direct child phải tự khai `final`, `sealed` hoặc `non-sealed` theo rules; records là implicitly final và có thể implements sealed interfaces.
- Nắm suy luận `permits` khi omitted: chỉ xét direct types trong **cùng compilation unit**, không rà mọi source file của package hoặc module.
- Biết dùng `Class.isSealed()`, `Class.getPermittedSubclasses()`, `Class.getModule()`, `Module.isNamed()` để quan sát chương trình đang chạy, không nhầm reflection với quyền phá luật compiler.
- Giải thích ảnh hưởng riêng của `exports`, `requires`, accessibility, package-private visibility và JPMS, đồng thời chọn kiến trúc hierarchy dễ bảo trì.
- Tự chạy các chương trình Java 17+ có source đầy đủ và kết quả chính xác; biết những đoạn được đánh dấu cố tình sai chỉ dùng để đọc lỗi, **không** paste vào một demo hợp lệ.

> **Phạm vi:** Bài thuộc chủ đề **Lớp sealed** trong Java core. Sealed classes/interfaces là tính năng chính thức từ Java 17 (JEP 409), không cần `--enable-preview`. Trọng tâm là **ràng buộc cùng module/cùng package đối với permitted direct types**, kèm những quy tắc kề cận để giải thích các trường hợp compiler chấp nhận/từ chối.

## 1. Quy tắc cần nhớ đầu tiên

| Vị trí của sealed parent | Yêu cầu vị trí của mỗi permitted **direct** subtype | Khác package? |
| --- | --- | --- |
| **Named module** (JPMS) | **Cùng một named module** | **Có thể**, nếu access và các rules khác hợp lệ |
| **Unnamed module** (điển hình là classpath) | **Cùng package** | **Không**, ngay cả nếu nằm cùng JAR/project |
| Hai **named modules khác nhau** | Không được trở thành parent/direct child được permit của nhau | Không hợp lệ |
| Chỉ “cùng project/cùng folder/cùng JAR” | Không đủ để xác nhận module association | Phải xác định named/unnamed thực tế |

Với một sealed class, các direct subtypes trong `permits` là **classes trực tiếp `extends` parent**. Với sealed interface, chúng có thể là **classes trực tiếp `implements`** hoặc **interfaces trực tiếp `extends` parent**.

**Nhớ ngắn gọn:**

- **Named → cùng module.**
- **Unnamed → cùng package.**
- **Chỉ kiểm tra permitted trực tiếp, không áp một cách máy móc lên mọi đời con.**

Quy tắc nằm trong JLS 17 [`8.1.6](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6) (sealed class) và [`9.1.4](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4) (sealed interface).

## 2. Tại sao Java có ràng buộc này?

Một sealed parent giới hạn **những kiểu nào được trực tiếp kế thừa** để tập immediate variants được quản lý bởi cùng nhóm duy trì mã. Ví dụ:

~~~java
sealed interface PaymentResult permits Success, Failure {
}

record Success(String receipt) implements PaymentResult {
}

record Failure(String reason) implements PaymentResult {
}
~~~

Đây là một **snippet**: các declarations có thể đặt trong cùng Java source file/package hoặc cùng module hợp lệ. `Success` và `Failure` là direct implementations, record đã implicitly final.

Nếu bất kỳ thư viện ở module độc lập nào cũng có thể direct implements `PaymentResult`, danh sách được permit sẽ không còn là ranh giới quản lý một tập domain variants nhất quán. JPMS named module tạo **đơn vị duy trì**, vì thế Java yêu cầu sealed parent và direct children cùng module. Với code classpath/unnamed module không có boundary có tên, Java dùng **package boundary** thay thế.

Đây là **quy tắc của ngôn ngữ** chứ không phải style convention; compiler từ chối chương trình vi phạm.

### 2.1. Vì sao không cho cross-module direct subtype?

Một direct child cần biết parent qua `extends`/`implements`; parent lại khai tên child trong `permits`. Nếu hai types nằm hai named modules độc lập, quan hệ này tạo nhu cầu tham chiếu **hai chiều**, không phù hợp JPMS module dependency graph và mục tiêu bảo trì. JLS cấm trước cả khi tìm cách “sửa” bằng `requires transitive` hoặc `opens`.

### 2.2. Có phải mọi descendant đều cùng module không?

**Không.** Parent sealed giới hạn **direct** children. Nếu một direct child là `non-sealed`, nhánh đó mở rộng theo rules bình thường, có thể có grandchildren ở package/module khác nếu accessibility và module readability phù hợp.

## 3. Phân biệt module, package và source file

| Thuật ngữ | Định nghĩa thực dụng | Điều **không** suy ra được |
| --- | --- | --- |
| Package | Namespace theo `package x.y;` | Chưa biết named module nào |
| Compilation unit | Một source file theo JLS `7.3` | Không đồng nghĩa toàn package |
| Named module | Module JPMS có name, ví dụ `com.example.domain` | Có thể chứa nhiều packages |
| Unnamed module | Module do runtime/classloader gán cho code ngoài named modules, thường qua classpath | Cùng unnamed module **không bỏ** same-package rule |
| Module path | `--module-path` dùng để tìm modules | Không phải cứ directory có chữ “module” |
| Classpath | `-cp`/`--class-path` kiểu truyền thống | Một JAR classpath không tự là named module |
| JAR | File đóng gói classes/resources | Cùng JAR chưa đủ kết luận location rule |
| Maven/Gradle project | Đơn vị build/dependency | Chưa chắc tương ứng một JPMS named module |

**Một package có thể có nhiều Java files**; một **named module có thể có nhiều packages**. Hai sự thật này lý giải vì sao “same module” và “same package” là hai cấp ranh giới khác nhau.

### 3.1. Cấu trúc named module minh họa

~~~text
com.example.geometry       ← named module
├── geometry.api           ← package 1
├── geometry.circle        ← package 2
├── geometry.rect          ← package 3
└── geometry.app           ← package 4
~~~

Một sealed interface `geometry.api.Shape` có thể permit `geometry.circle.Circle` và `geometry.rect.Rectangle` nếu các declarations thuộc cùng **com.example.geometry** và legal theo Java access rules.

Ngược lại, khi tất cả classes được chạy như classpath code (unnamed module), hai implementations ở `geometry.circle`/`geometry.rect` **không thể** là direct permitted children của parent `geometry.api.Shape`.

## 4. Cú pháp sealed superclass và children trực tiếp

~~~java
sealed abstract class Animal permits Dog, Cat {
    abstract String sound();
}

final class Dog extends Animal {
    @Override
    String sound() {
        return "woof";
    }
}

non-sealed class Cat extends Animal {
    @Override
    String sound() {
        return "meow";
    }
}
~~~

Cả ba declarations cùng compilation unit/package ở ví dụ này, nên legal về location. `Animal` sealed; `Dog` final, `Cat` non-sealed.

- `Dog` trực tiếp `extends Animal`.
- `Cat` trực tiếp `extends Animal`.
- `Animal.permits` **không** được liệt kê một unrelated class.
- `abstract` dùng vì `sound()` là abstract; sealed **không tự làm class abstract**.
- `final` cấm subclass Dog.
- `non-sealed` cho phép subclasses tương lai kế thừa Cat theo access rules.

## 5. Ví dụ đa file classpath — **cùng package** dù khác file

Tạo project mới:

~~~text
classpath-animals/
└── src/
    └── animals/
        ├── Animal.java
        ├── Dog.java
        ├── Cat.java
        └── Main.java
~~~

Các file dưới đây đều dùng `package animals;`.

**`src/animals/Animal.java`**

~~~java
package animals;

public abstract sealed class Animal permits Dog, Cat {
    public abstract String sound();
}
~~~

**`src/animals/Dog.java`**

~~~java
package animals;

public final class Dog extends Animal {
    @Override
    public String sound() {
        return "woof";
    }
}
~~~

**`src/animals/Cat.java`**

~~~java
package animals;

public non-sealed class Cat extends Animal {
    @Override
    public String sound() {
        return "meow";
    }
}
~~~

**`src/animals/Main.java`**

~~~java
package animals;

public class Main {
    public static void main(String[] args) {
        Animal dog = new Dog();
        Animal cat = new Cat();

        System.out.println("named module=" +
                Animal.class.getModule().isNamed());
        System.out.println("dog=" + dog.sound());
        System.out.println("cat=" + cat.sound());
        System.out.println("sealed=" + Animal.class.isSealed());
        System.out.println("permitted=" +
                Animal.class.getPermittedSubclasses().length);
    }
}
~~~

### 5.1. Biên dịch và chạy Java 17

Đứng trong thư mục `classpath-animals` vừa tạo:

~~~bash
mkdir out
javac --release 17 -d out src/animals/Animal.java src/animals/Dog.java src/animals/Cat.java src/animals/Main.java
java -cp out animals.Main
~~~

**Stdout:**

~~~text
named module=false
dog=woof
cat=meow
sealed=true
permitted=2
~~~

### 5.2. Giải thích

- `-cp out` chạy trên classpath; `Animal.class.getModule().isNamed()` trả false trong dự án này.
- Animal, Dog, Cat đều **cùng package animals**, nên hợp lệ theo unnamed-module rule.
- Chúng không cùng source file: `permits Dog, Cat` **explicit** khai danh sách khi direct children nằm các compilation units khác nhau.
- Dog/Cat là direct children, thỏa rule final/non-sealed.
- Reflection `getPermittedSubclasses()` đếm **hai children trực tiếp**, không phải mọi subtype về sau.

Đừng xóa `permits` khi vẫn giữ mỗi type ở file khác và mong Java tự tìm chúng: inferred permits chỉ áp dụng cùng compilation unit (mục 12).

## 6. Cố tình sai: unnamed module nhưng **khác package**

Tạo hai file ở một project **riêng** (mã ở mục này cố tình không compile).

**`src/p/core/Base.java`**

~~~java
package p.core;

public sealed interface Base permits p.ext.Child {
}
~~~

**`src/p/ext/Child.java`**

~~~java
package p.ext;

public final class Child implements p.core.Base {
}
~~~

Thử biên dịch qua classpath-style:

~~~bash
mkdir out
javac --release 17 -d out src/p/core/Base.java src/p/ext/Child.java
~~~

**Kết quả:** `javac` từ chối ở compile time: direct permitted Child thuộc `p.ext`, trong khi sealed Base thuộc `p.core` của unnamed module. Không có stdout của một ứng dụng chạy thành công; cách viết stderr tùy bản JDK.

### 6.1. Tại sao `public` không cứu được?

`public` giải quyết một lớp **accessibility**. Nhưng cùng lúc Java kiểm tra sealed location: **unnamed module đòi cùng package**. Public child khác package vẫn không đủ.

### 6.2. Tại sao chuyển file vào cùng folder không cứu được?

Package thuộc về `package p.ext;` trong source, không được quyết định chỉ từ nơi đặt file. Đổi folder mà không đổi package declaration không làm p.ext trở thành p.core.

### 6.3. Sửa hợp lệ có những cách nào?

- Đặt direct child và parent ở **cùng package** (cập nhật declarations/imports phù hợp).
- Hoặc đưa chúng vào **cùng named module** được cấu hình đúng nếu chủ đích tách packages.
- Hoặc dùng extension point `non-sealed` trong cùng package cho những descendants gián tiếp khác package.
- Không dùng reflection, `exports`, `opens` hay thêm modifier public như mẹo bỏ qua language rule.

## 7. Named module: **khác package** mà vẫn hợp lệ

Một named module có thể có nhiều packages. Ta xây một project có sealed interface `geometry.api.Shape` và hai direct implementing classes thuộc `geometry.circle` và `geometry.rect` nhưng **cùng module**.

Cấu trúc:

~~~text
modular-shapes/
└── src/
    └── com.example.geometry/
        ├── module-info.java
        └── geometry/
            ├── api/
            │   └── Shape.java
            ├── circle/
            │   └── Circle.java
            ├── rect/
            │   └── Rectangle.java
            └── app/
                └── Main.java
~~~

**`src/com.example.geometry/module-info.java`**

~~~java
module com.example.geometry {
    exports geometry.api;
}
~~~

**`src/com.example.geometry/geometry/api/Shape.java`**

~~~java
package geometry.api;

public sealed interface Shape
        permits geometry.circle.Circle, geometry.rect.Rectangle {
    String describe();
}
~~~

**`src/com.example.geometry/geometry/circle/Circle.java`**

~~~java
package geometry.circle;

import geometry.api.Shape;

public final class Circle implements Shape {
    private final int radius;

    public Circle(int radius) {
        this.radius = radius;
    }

    @Override
    public String describe() {
        return "circle(r=" + radius + ")";
    }
}
~~~

**`src/com.example.geometry/geometry/rect/Rectangle.java`**

~~~java
package geometry.rect;

import geometry.api.Shape;

public final class Rectangle implements Shape {
    private final int width;
    private final int height;

    public Rectangle(int width, int height) {
        this.width = width;
        this.height = height;
    }

    @Override
    public String describe() {
        return "rect(" + width + "x" + height + ")";
    }
}
~~~

**`src/com.example.geometry/geometry/app/Main.java`**

~~~java
package geometry.app;

import geometry.api.Shape;
import geometry.circle.Circle;
import geometry.rect.Rectangle;

public class Main {
    public static void main(String[] args) {
        Shape a = new Circle(2);
        Shape b = new Rectangle(3, 4);

        System.out.println("module=" +
                Shape.class.getModule().getName());
        System.out.println(a.describe());
        System.out.println(b.describe());
        System.out.println("permitted=" +
                Shape.class.getPermittedSubclasses().length);
    }
}
~~~

### 7.1. Biên dịch và chạy theo module mode

Đứng trong `modular-shapes`:

~~~bash
mkdir out
javac --release 17 --module-source-path src -d out -m com.example.geometry
java --module-path out -m com.example.geometry/geometry.app.Main
~~~

**Stdout:**

~~~text
module=com.example.geometry
circle(r=2)
rect(3x4)
permitted=2
~~~

### 7.2. Vì sao project này hợp lệ?

1. Module descriptor khai **com.example.geometry**.
2. Shape, Circle và Rectangle đều thuộc **named module com.example.geometry**.
3. `Shape` trực tiếp được triển khai bởi Circle/Rectangle.
4. Circle và Rectangle public nên accessible khi Shape ở package khác.
5. Cả hai là final classes, hợp lệ làm direct children của sealed interface.
6. `permits` dùng full qualified names nêu rõ hai package khác nhau.
7. Main cùng module nên có thể dùng public classes từ các packages của module; `exports geometry.api` dùng cho external module consumers chứ không cấp quyền permit cross-module.
8. `getPermittedSubclasses().length` trả 2.

### 7.3. Có cần `exports geometry.circle` và `exports geometry.rect` không?

**Không để phép permit hợp lệ.** Exports điều khiển public accessibility **từ module khác**. Trong chính module com.example.geometry, Main dùng Circle/Rectangle bình thường vì class public, dù các packages này chưa exports.

Một external module có thể dùng `Shape` nếu đọc com.example.geometry và shape API được export, nhưng không thể direct `implements Shape` ở module external do sealed location rule.

## 8. So sánh module mode và classpath mode

| Câu hỏi | Classpath/unnamed | JPMS named |
| --- | --- | --- |
| Parent, child cùng package? | Được nếu các rules khác đúng | Được nếu cùng module |
| Parent, child khác package? | **Không được** direct permit | **Có thể được** nếu cùng module/access đúng |
| Parent, child khác named module? | Không phải kiểu tổ chức này | **Không được** direct permit |
| Có thể dùng multi-file `permits` explicit? | Có | Có |
| Bỏ permits, tự suy từ các file khác? | Không | Không |
| `exports` có thay sealed restriction? | Không | Không |
| `final/sealed/non-sealed` vẫn cần? | Có | Có |
| `getPermittedSubclasses()` chỉ direct? | Có | Có |

**Không được suy:** “Hai files thuộc cùng Gradle subproject” → cùng named module. Tên công cụ build không định nghĩa module association; `module-info.java`, compiler mode, module path/classpath và module graph thực tế mới quan trọng.

## 9. Sealed class và sealed interface: location rule giống nhau

Với sealed **class**:

~~~java
sealed class Parent permits First, Second {
}

final class First extends Parent {
}

non-sealed class Second extends Parent {
}
~~~

`First` và `Second` là classes có direct superclass Parent.

Với sealed **interface**:

~~~java
sealed interface Result permits Success, Failure, Extensible {
}

record Success(String value) implements Result {
}

final class Failure implements Result {
}

non-sealed interface Extensible extends Result {
}
~~~

`Success`/`Failure` là direct implementing classes; `Extensible` là direct subinterface. Tất cả phải thỏa same named module hoặc same package (nếu unnamed).

Các ví dụ này là standalone **source snippets** có thể đặt trong compilation unit phù hợp; không có main riêng. Record ngầm final, vì thế permitted implementation Success không cần ghi `final` trước `record`.

## 10. Chương trình: sealed interface nhận record implementations

Lưu **`SealedRecordsDemo.java`**:

~~~java
public class SealedRecordsDemo {
    sealed interface Answer permits Yes, No {
        String text();
    }

    record Yes(String reason) implements Answer {
        @Override
        public String text() {
            return "yes:" + reason;
        }
    }

    record No(String reason) implements Answer {
        @Override
        public String text() {
            return "no:" + reason;
        }
    }

    public static void main(String[] args) {
        Answer a = new Yes("valid");
        Answer b = new No("missing");

        System.out.println(a.text());
        System.out.println(b.text());
        System.out.println("sealed=" + Answer.class.isSealed());
        System.out.println("direct=" +
                Answer.class.getPermittedSubclasses().length);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 SealedRecordsDemo.java
java SealedRecordsDemo
~~~

Output:

~~~text
yes:valid
no:missing
sealed=true
direct=2
~~~

Member records nằm cùng compilation unit với sealed interface. Chúng là final types, không thể bị subclass và không cần ghi `final` explicitly.

## 11. Mỗi direct child phải chọn tình trạng mở rộng

Nếu một **normal class** trực tiếp extends sealed class hoặc directly implements sealed interface, cần tuyên bố:

- `final`: không còn subclass.
- `sealed`: giới hạn direct subclasses của child qua own `permits`.
- `non-sealed`: chủ động mở nhánh cho ordinary inheritance rules.

Với một interface trực tiếp extends sealed interface, trạng thái thích hợp là `sealed` hoặc `non-sealed`, không phải final. Với records: `final` ngầm định; enums có quy tắc ngầm final/sealed tùy constant-specific bodies.

### 11.1. Ví dụ thiếu modifier (sai)

~~~java
sealed interface Task permits Worker {
}

// class Worker implements Task {} // Sai: thiếu final/sealed/non-sealed.

final class Worker implements Task {
}
~~~

Nếu bỏ final ở Worker và không thay bằng sealed hoặc non-sealed, compiler từ chối, dù cùng package/module.

### 11.2. `non-sealed` không phải modifier cho mọi class

~~~java
// non-sealed class Independent {} // Sai nếu không có
// sealed direct superclass hoặc sealed direct superinterface.
~~~

`non-sealed` hợp lệ khi nó **trả lời một sealed boundary trực tiếp**. Một class chỉ extends một non-sealed parent không tự cần và thường không được ghi `non-sealed` nếu không có sealed direct parent/interface.

## 12. `permits` chỉ cho phép **direct** types

Giả sử:

~~~text
Base (sealed)
 ├── Closed (final)
 └── Gateway (non-sealed)
       └── Plugin (ordinary subclass)
~~~

`Base.permits` chứa Closed/Gateway, **không chứa Plugin**. Plugin là descendant gián tiếp qua Gateway.

~~~java
sealed class Base permits Closed, Gateway {
}

final class Closed extends Base {
}

non-sealed class Gateway extends Base {
}

class Plugin extends Gateway {
}
~~~

Các declarations có thể cùng file/package. `Plugin` không direct extends Base và không phải phần tử của `Base.permits`.

### 12.1. Nếu Gateway lại sealed?

Nếu Gateway là `sealed class Gateway extends Base permits Plugin`, thì Plugin phải đáp ứng **own permits location rule của Gateway**. Mỗi sealed node kiểm soát **một lớp children trực tiếp**.

### 12.2. Sai khi liệt kê grandchild

~~~java
// sealed class Base permits Plugin {} // Sai nếu Plugin chỉ extends Gateway.
~~~

Một tên cùng module/package vẫn **không đủ** nếu không phải direct subtype.

## 13. Chương trình: direct subtype và indirect subtype

Lưu **`SealedDirectDemo.java`**:

~~~java
public class SealedDirectDemo {
    static abstract sealed class Base permits Closed, Open {
        abstract String label();
    }

    static final class Closed extends Base {
        @Override
        String label() {
            return "closed";
        }
    }

    static non-sealed class Open extends Base {
        @Override
        String label() {
            return "open";
        }
    }

    static class Extension extends Open {
        @Override
        String label() {
            return "extension";
        }
    }

    public static void main(String[] args) {
        Base value = new Extension();

        System.out.println("label=" + value.label());
        System.out.println("base sealed=" + Base.class.isSealed());
        System.out.println("permits=" +
                Base.class.getPermittedSubclasses().length);
        System.out.println("open sealed=" + Open.class.isSealed());
        System.out.println("extension instance=" +
                (value instanceof Base));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 SealedDirectDemo.java
java SealedDirectDemo
~~~

Output:

~~~text
label=extension
base sealed=true
permits=2
open sealed=false
extension instance=true
~~~

`Extension` vẫn là Base instance qua subtype chain, nhưng không được liệt kê vào Base permits, và `getPermittedSubclasses()` trả số **trực tiếp**, tức 2.

## 14. Đặc biệt: `non-sealed` mở sang package khác trong unnamed module

Nếu parent sealed thuộc unnamed module:

- Parent và **direct Gateway** phải cùng package.
- Nhưng descendant `Plugin extends Gateway` có thể nằm package khác nếu Gateway **non-sealed**, public/access hợp lệ.

Tạo project:

~~~text
extension-demo/
└── src/
    ├── p/
    │   ├── Root.java
    │   └── Gateway.java
    └── q/
        ├── Plugin.java
        └── Main.java
~~~

**`src/p/Root.java`:**

~~~java
package p;

public abstract sealed class Root permits Gateway {
    public abstract String kind();
}
~~~

**`src/p/Gateway.java`:**

~~~java
package p;

public non-sealed class Gateway extends Root {
    @Override
    public String kind() {
        return "gateway";
    }
}
~~~

**`src/q/Plugin.java`:**

~~~java
package q;

public final class Plugin extends p.Gateway {
    @Override
    public String kind() {
        return "plugin";
    }
}
~~~

**`src/q/Main.java`:**

~~~java
package q;

public class Main {
    public static void main(String[] args) {
        p.Root value = new Plugin();

        System.out.println(value.kind());
        System.out.println("root permits=" +
                p.Root.class.getPermittedSubclasses().length);
    }
}
~~~

Chạy từ project root:

~~~bash
mkdir out
javac --release 17 -d out src/p/Root.java src/p/Gateway.java src/q/Plugin.java src/q/Main.java
java -cp out q.Main
~~~

**Stdout:**

~~~text
plugin
root permits=1
~~~

Giải thích: Root và Gateway đều `package p` (cùng package); Plugin `package q` chỉ extends Gateway (non-sealed). Plugin **không** direct extends Root, nên parent sealed package restriction không áp trực tiếp cho Plugin.

**Cấm hiểu sai:** không được viết `Root permits q.Plugin`. Plugin chỉ là grandchild và ở package khác.

## 15. `non-sealed interface` làm extension point cho plugin

Một sealed interface có thể trực tiếp permit một `non-sealed interface`, rồi plugins ở package/module khác implement interface đó.

~~~java
sealed interface Event permits BuiltIn, PluginEvent {
}

record BuiltIn(String name) implements Event {
}

non-sealed interface PluginEvent extends Event {
}

final class CustomEvent implements PluginEvent {
}
~~~

PluginEvent là **direct subinterface** của Event; CustomEvent là một **indirect implementation** qua PluginEvent. Vì branch PluginEvent non-sealed, subclasses được mở lại theo normal Java access rules.

### 15.1. Chương trình runnable

Lưu **`SealedPluginGatewayDemo.java`**:

~~~java
public class SealedPluginGatewayDemo {
    sealed interface Event permits BuiltIn, PluginEvent {
        String kind();
    }

    record BuiltIn(String kind) implements Event {
    }

    non-sealed interface PluginEvent extends Event {
    }

    static final class CustomEvent implements PluginEvent {
        @Override
        public String kind() {
            return "custom";
        }
    }

    public static void main(String[] args) {
        Event a = new BuiltIn("builtin");
        Event b = new CustomEvent();

        System.out.println(a.kind());
        System.out.println(b.kind());
        System.out.println("permits=" +
                Event.class.getPermittedSubclasses().length);
        System.out.println("gateway sealed=" +
                PluginEvent.class.isSealed());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 SealedPluginGatewayDemo.java
java SealedPluginGatewayDemo
~~~

Output:

~~~text
builtin
custom
permits=2
gateway sealed=false
~~~

Nếu PluginEvent public và được export từ provider named module, consumer module có thể direct implements PluginEvent (đủ accessibility), mà vẫn chỉ **gián tiếp** là Event. Đó là kiến trúc extension point hợp lệ; không lách direct sealed restriction.

## 16. `permits` explicit và suy luận permits là hai cơ chế riêng

Java cho phép sealed class/interface **không ghi `permits`** trong một số trường hợp. Compiler có thể suy các permitted direct subclasses/subinterfaces từ declarations trong **cùng compilation unit**.

**Cùng compilation unit ≈ cùng file Java source**, không phải mọi files cùng package hoặc mọi files đưa vào một lệnh `javac`.

Nếu direct child nằm **file riêng**, ngay cả cùng named module hoặc cùng package, đừng kỳ vọng compiler scan các files để infer. Dùng `permits` explicit.

### 16.1. Chương trình inference khi cùng source file

Lưu **`InferredPermitsDemo.java`**:

~~~java
public class InferredPermitsDemo {
    sealed interface Action {
        String execute();
    }

    record Start() implements Action {
        @Override
        public String execute() {
            return "start";
        }
    }

    record Stop() implements Action {
        @Override
        public String execute() {
            return "stop";
        }
    }

    public static void main(String[] args) {
        Action a = new Start();
        Action b = new Stop();

        System.out.println(a.execute());
        System.out.println(b.execute());
        System.out.println("inferred=" +
                Action.class.getPermittedSubclasses().length);
    }
}
~~~

Chạy:

~~~bash
javac --release 17 InferredPermitsDemo.java
java InferredPermitsDemo
~~~

Output:

~~~text
start
stop
inferred=2
~~~

Cả Start/Stop nằm cùng source file với Action và direct implements Action, nên compiler suy inferred permits list dù Action không ghi permits clause.

### 16.2. Tách file thì phải nêu permits

~~~text
Action.java: sealed interface Action permits Start, Stop { ... }
Start.java:  final class Start implements Action { ... }
Stop.java:   final class Stop implements Action { ... }
~~~

Đây là sơ đồ chứ không phải một file Java hợp lệ. Nếu Action.java chỉ có `sealed interface Action {}` trong khi direct types ở file khác, compiler không suy ra chúng chỉ vì chúng cùng package.

### 16.3. Local/anonymous classes có được suy luận không?

Không. Suy luận yêu cầu direct subtypes có canonical name trong cùng compilation unit. Local classes và anonymous classes không được infer vào list để mở sealed hierarchy.

## 17. `permits` không phải danh sách bất kỳ

Một permits clause phải dùng tên type có thể truy cập được, không liệt kê trùng và mỗi type phải **direct subtype** của parent.

### 17.1. Tên trong permits nhưng không extends

~~~java
sealed class Root permits Child {
}

// final class Child { } // Sai nếu không extends Root.
final class Child extends Root {
}
~~~

Location đã đúng vẫn cần **inheritance relation**.

### 17.2. Không liệt kê một type hai lần

~~~java
// package p;
// sealed class Root permits Child, p.Child { } // Sai: trùng type.
// final class Child extends Root { }
~~~

Simple name và fully qualified name cùng trỏ tới Child không tạo hai loại permission riêng.

### 17.3. Package-private type qua package boundary

Trong unnamed module, parent và child cùng package có thể dùng package-private declarations. Trong named module, nếu child ở **package khác**, parent thường cần child là public/accessible để gọi tên nó trong `permits`. Same-module **không loại bỏ** Java access restrictions.

## 18. `exports` và `requires` khác `permits` thế nào?

Trong JPMS:

- `requires other.module;` tạo dependency/readability theo module descriptor.
- `exports api.package;` mở quyền truy cập public types trong package này tới readers hợp lệ.
- `opens some.package;` liên quan reflective access; không tạo quyền extends sealed type.
- `permits MyChild` thuộc Java sealed declaration, xác định direct subtypes được phép.

Ví dụ module provider:

~~~java
module com.example.geometry {
    exports geometry.api;
}
~~~

Consumer có thể:

~~~java
module consumer.module {
    requires com.example.geometry;
}
~~~

Rồi dùng `geometry.api.Shape` làm parameter/return type theo public API. Nhưng một `consumer.impl.CustomShape` trong **consumer.module** không được direct `implements Shape`, ngay cả khi Shape public/exported. Điều kiện **cùng named module** vẫn tồn tại.

### 18.1. Vì sao không dùng `requires transitive` để giải quyết?

`requires transitive` thay đổi readability giữa modules; không thay đổi nơi class được declared. Cross-module direct sealed subclass vẫn là compile-time error.

### 18.2. Một package được export không bắt buộc để permit nội bộ

Ở project modular-shapes, `geometry.circle` không export. Shape vẫn permits Circle do **cùng named module**, và compiler thấy Circle public/accessible. Exports chỉ cần khi module khác phải truy cập package ấy.

## 19. Named module khác nhau nhưng package name giống nhau có được không?

**Không.** Quy tắc của named module xét **same named module association**, không chỉ package string. Nếu Root thuộc named module A và direct child thuộc named module B, dù package names trùng hoặc build cố tổ chức split package, direct permit vẫn không hợp lệ.

JPMS cũng có constraints riêng quanh split packages/readability. Đừng thiết kế cross-module hierarchy bằng cách đặt cả hai tên package `api` rồi nghĩ Java sẽ coi chúng như một namespace chung.

**Nguyên tắc:** named-module branch phải thật sự nằm trong **một** named module, không phải hai modules có vẻ liên quan tên.

## 20. Cùng JAR, automatic module và runtime mode

Một JAR đặt trên **classpath** thuộc classpath loading, thường là **unnamed module**. Nhiều packages trong cùng JAR **không tự** được phép làm cross-package direct sealed hierarchy.

JAR đặt trên **module path** có thể trở thành explicit named module (nếu có descriptor), hoặc automatic module theo module-system rules nếu phù hợp. Một automatic module là **named module** về module association, nhưng code/build layout và constraints thực tế vẫn phải xem đúng. Không nên phụ thuộc vào “cùng artifact” mà bỏ qua module configuration.

Quan sát loại runtime module:

~~~java
System.out.println(SomeType.class.getModule().isNamed());
System.out.println(SomeType.class.getModule().getName());
~~~

Trong classpath demo, isNamed false; trong modular-shapes demo, tên là `com.example.geometry`. Đây là chẩn đoán runtime, không thay compiler source checks.

## 21. Reflection: xem sealed metadata trong Java 17

Các APIs hữu ích:

- `Class.isSealed()`: sealed class/interface runtime status.
- `Class.getPermittedSubclasses()`: trả các **permitted direct types**. Với non-sealed class/interface nó có thể trả null, nên không gọi `.length` bất cẩn.
- `Class.getModule()` và `Module.isNamed()`: module association.
- `Class.getPackageName()`: Java package name, hữu ích khi kiểm tra unnamed-module same-package case.
- `Class.getSuperclass()`/`getInterfaces()`: quan sát relations; phân biệt direct với indirect.

**Không lẫn lộn:** reflection cho phép **đọc metadata**. Nó không cấp quyền tạo direct subclass ngoài permitted list/module/package.

### 21.1. Chương trình runnable không có named package

Lưu **`SealedReflectionDemo.java`**:

~~~java
public class SealedReflectionDemo {
    sealed interface Node permits Leaf, Branch {
    }

    record Leaf(int value) implements Node {
    }

    non-sealed interface Branch extends Node {
    }

    public static void main(String[] args) {
        Class<?> type = Node.class;

        System.out.println("sealed=" + type.isSealed());
        System.out.println("named=" +
                type.getModule().isNamed());
        System.out.println("package=" + type.getPackageName());
        System.out.println("direct=" +
                type.getPermittedSubclasses().length);
        System.out.println("branch sealed=" +
                Branch.class.isSealed());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 SealedReflectionDemo.java
java SealedReflectionDemo
~~~

Output:

~~~text
sealed=true
named=false
package=
direct=2
branch sealed=false
~~~

`package=` không có chữ sau dấu bằng vì chương trình demo không khai package và `getPackageName()` trả chuỗi rỗng. Production code nên dùng named packages, nhưng default package hợp lệ để chứng minh unnamed-module behavior.

## 22. Chương trình contract test chủ động

Lưu **`SealedLocationTest.java`**:

~~~java
public class SealedLocationTest {
    sealed interface Animal permits Dog, Cat {
        String sound();
    }

    record Dog() implements Animal {
        @Override
        public String sound() {
            return "woof";
        }
    }

    record Cat() implements Animal {
        @Override
        public String sound() {
            return "meow";
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        check(Animal.class.isSealed(), "sealed");
        check(!Animal.class.getModule().isNamed(), "unnamed");
        check(Animal.class.getPermittedSubclasses().length == 2,
                "direct permits");
        check(Dog.class.getModule() == Animal.class.getModule(),
                "same runtime module");
        check(Dog.class.getPackageName().equals(
                Animal.class.getPackageName()), "same package");

        Animal dog = new Dog();
        Animal cat = new Cat();
        check("woof".equals(dog.sound()), "dog");
        check("meow".equals(cat.sound()), "cat");

        System.out.println("sealed location tests passed");
    }
}
~~~

Chạy trong thư mục mới ở classpath:

~~~bash
javac --release 17 SealedLocationTest.java
java SealedLocationTest
~~~

Output:

~~~text
sealed location tests passed
~~~

Method `check` chủ động kiểm tra thay vì dùng `assert` (mặc định không hoạt động nếu không dùng `-ea`). Test chỉ xác nhận **một chương trình hợp lệ**. Đối với những tình huống **bị Java compiler cấm**, bạn cần phân tích JLS/biên dịch riêng các examples sai; không có runtime test hợp lệ để “chứng minh” một class được compiler từ chối.

## 23. Những lỗi phổ biến về cùng module/package

| Quan niệm sai | Quy tắc đúng |
| --- | --- |
| “Cùng Gradle module thì cứ khác package vẫn permit.” | Phải xác minh **JPMS named module**, không dựa build-tool naming. |
| “Cùng JAR classpath là đủ.” | Unnamed module → direct children phải cùng package. |
| “Trong JPMS mọi permitted child phải cùng package.” | Named module → có thể khác package nếu cùng module và accessible. |
| “Cùng package trong hai named modules là đủ.” | Phải cùng named module; package name không thay module boundary. |
| “`public` bỏ giới hạn khác package trên classpath.” | Public chỉ giải quyết access, không bỏ sealed location rule. |
| “`exports` cho phép downstream direct implementations.” | Exports không cấp quyền cross-module direct sealed subtype. |
| “`opens` hoặc reflection có thể bổ sung permitted class.” | Không làm thay JLS sealed declaration. |
| “`permits` chứa mọi descendant.” | Chỉ direct children. |
| “Grandchild phải cùng package với ancestor sealed.” | Không nhất thiết nếu đi qua non-sealed branch. |
| “Một non-sealed branch có nghĩa Root không còn sealed.” | Root vẫn sealed và có fixed direct permits. |
| “`final` child có thể mở rộng qua `extends` ở package khác.” | Final cấm subclass. |
| “`sealed` child không cần own permits.” | Nếu child sealed, nó phải khai/infer direct permits hợp lệ. |
| “Class được ghi trong `permits` không cần extends parent.” | Phải direct subtype. |
| “Viết cùng type hai lần trong permits là hợp lệ.” | Duplicate type bị cấm. |
| “`sealed interface` không thể permit record.” | Record implicitly final, có thể implements. |
| “Quên final/sealed/non-sealed không sao nếu cùng package.” | Direct normal child phải có suitable status modifier. |
| “Cùng package ở file khác là đủ để compiler tự suy permits.” | Inferred permits chỉ từ cùng compilation unit. |
| “Một anonymous/local class có thể inferred vào permits.” | Cần canonical named declarations; local/anonymous không được infer. |
| “Package name lấy từ folder bất kỳ.” | Source `package` declaration xác định namespace; layout build cần tương thích. |
| “Tất cả modules trên module path là cùng một module.” | Mỗi named module có identity riêng. |

## 24. Checklist thiết kế và kiểm tra build

1. Sealed parent nằm **named module** hay **unnamed module**?
2. Parent là **sealed class** hay **sealed interface**?
3. Mọi direct permitted subtype đã được xác định bằng actual `extends`/`implements`/`extends interface` arrows chưa?
4. Named → toàn bộ direct children thuộc **chính xác cùng named module**?
5. Unnamed → toàn bộ direct children có **cùng `package` declaration**?
6. Nếu named và child ở package khác, accessibility của child có phù hợp?
7. Các public/protected constructors khi extending cross-package class có accessible?
8. Tên trong `permits` có trùng/không accessible/unrelated không?
9. Direct normal classes có final/sealed/non-sealed đúng không?
10. Direct interfaces có sealed/non-sealed phù hợp không?
11. Record/enum implicit status được hiểu đúng không?
12. Child sealed tiếp có own permits hierarchy?
13. Nếu bỏ permits, children có cùng compilation unit và canonical names?
14. Nếu children khác file, đã khai explicit permits?
15. Có nhầm grandchildren với permitted direct subclasses?
16. `non-sealed` extension point đã được lựa chọn có chủ đích?
17. Có nhầm code classpath với module path khi chạy test?
18. `module-info.java` đúng module name và exports/access?
19. Có dependency cycle/split packages/JPMS readability issues?
20. Tests có được chạy đúng mode giống application thực tế?
21. Có cần consumer extension qua non-sealed interface thay vì cho trực tiếp implement sealed root?
22. Đã dùng Java 17+ mà không bật preview không cần thiết?
23. Thông báo lỗi `javac` được hiểu theo nguyên nhân, không ép phải trùng từng dòng stderr?
24. Có kiểm tra `Class.getPermittedSubclasses()` chỉ nói về direct permitted types?

## 25. Bài tập ôn luyện và đáp án

**Câu 1.** Sealed parent ở named module M, child ở package khác nhưng vẫn M, có được không?  
**Đáp án:** Có thể được, nếu child accessible/direct permitted và thỏa tất cả các quy tắc khác.

**Câu 2.** Parent ở unnamed module package p, child ở package q cùng classpath, được không?  
**Đáp án:** Không cho direct child. Unnamed module yêu cầu cùng package.

**Câu 3.** Hai source files ở package p trong unnamed module nhưng khác file được permit không?  
**Đáp án:** Có nếu `permits` explicit và direct relation/modifier rules hợp lệ.

**Câu 4.** Cùng package p nhưng hai named modules khác nhau, được không?  
**Đáp án:** Không, location rule của named module yêu cầu cùng module.

**Câu 5.** Vì sao không chỉ dùng `public` để fix cross-package unnamed-module error?  
**Đáp án:** Public access và same-package sealed restriction là hai phép kiểm tra khác nhau.

**Câu 6.** `module-info.java` cho phép dùng `exports` để consumer tự implement sealed root không?  
**Đáp án:** Không; exports chỉ quyết định public API access.

**Câu 7.** Sealed class có thể permits một interface không?  
**Đáp án:** Không; direct subclass của một class phải là class extends nó.

**Câu 8.** Sealed interface có thể permits một interface khác không?  
**Đáp án:** Có, interface đó direct extends parent.

**Câu 9.** Sealed interface có thể permits một record không?  
**Đáp án:** Có, record trực tiếp implements sealed interface và record implicitly final.

**Câu 10.** Tại sao direct normal class phải `final`/`sealed`/`non-sealed`?  
**Đáp án:** Để quyết định có mở rộng tiếp hay không; Java yêu cầu explicit posture tại sealed boundary.

**Câu 11.** `sealed Root permits Grandchild` nếu Grandchild chỉ extends Middle extends Root có đúng không?  
**Đáp án:** Sai; Grandchild không direct subtype.

**Câu 12.** Parent sealed class permits một non-sealed class cùng package, grandchild ở package khác có được không?  
**Đáp án:** Có thể, vì grandchild chỉ extends non-sealed child và tuân bình thường visibility rules.

**Câu 13.** Nếu child lại sealed thì grandchildren bị kiểm soát thế nào?  
**Đáp án:** Theo own permits list và location rules của sealed child.

**Câu 14.** Inferred permits có quét tất cả source files cùng module không?  
**Đáp án:** Không. Chỉ cùng compilation unit.

**Câu 15.** Tại sao đặt cùng file Java mà vẫn cần trực tiếp implements/extends?  
**Đáp án:** Same compilation unit giúp inferred list, không bỏ direct subtype requirement.

**Câu 16.** `Class.isSealed()` trả gì cho `non-sealed` branch?  
**Đáp án:** False; parent vẫn sealed.

**Câu 17.** `getPermittedSubclasses()` đếm grandchildren không?  
**Đáp án:** Không, chỉ permitted direct types.

**Câu 18.** Mọi direct subtype ở named module có thể package-private khác package không?  
**Đáp án:** Không phải mặc định; type phải accessible từ sealed parent. Cross-package top-level type thường cần public.

**Câu 19.** Một public module API ở package exported có cho downstream direct extends sealed parent không?  
**Đáp án:** Không, vì parent vẫn yêu cầu direct subtypes cùng named module.

**Câu 20.** `non-sealed interface Gateway extends SealedRoot` có ích gì?  
**Đáp án:** Cho phép open extension branch mà không mở direct variants của SealedRoot.

**Câu 21.** Có thể sửa JLS violation bằng `requires transitive` không?  
**Đáp án:** Không; đó là module readability, không thay sealed direct location rule.

**Câu 22.** Cùng JAR có đồng nghĩa cùng named module không?  
**Đáp án:** Không; xem JAR đang ở classpath hay module path và descriptor/automatic module handling.

**Câu 23.** Java 17 cần `--enable-preview` cho sealed không?  
**Đáp án:** Không, đã chính thức từ Java 17.

**Câu 24.** Bước đầu tiên khi compiler báo sealed location error là gì?  
**Đáp án:** Xác định named/unnamed module thực tế và package declaration của parent/direct child.

## 26. Tài liệu tham khảo chính thức

- [JLS Java SE 17 `8.1.6 — Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6): điều kiện cùng named module hoặc cùng package của sealed classes, và inferred permits.
- [JLS Java SE 17 `9.1.4 — Permitted Direct Subclasses and Subinterfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4): quy tắc tương ứng cho sealed interfaces.
- [JLS Java SE 17 `8.1.1.2 — sealed, non-sealed, final Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2): hành vi các direct classes.
- [JLS Java SE 17 `9.1.1.4 — sealed and non-sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4): hành vi các direct subinterfaces.
- [JLS Java SE 17 `7.3 — Compilation Units](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.3): đơn vị suy luận permits.
- [JLS Java SE 17 `7.7 — Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7) và [`7.7.5 — Unnamed Modules](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7.5): module associations.
- [JLS Java SE 17 `6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): accessible types và package boundaries.
- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): mục tiêu thiết kế và chuẩn hóa sealed trong Java 17.
- [Java 17 API Class.isSealed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isSealed()): introspection metadata.
- [Java 17 API Class.getPermittedSubclasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()): direct permitted classes/interfaces.
- [Java 17 API Class.getModule](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getModule()) và [Module.isNamed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html#isNamed()): runtime module identity.
- [Java 17 javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) và [java launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `--release`, `--module-source-path`, `-cp`, `--module-path` và `-m`.

## Tổng kết

**Sealed class/interface giới hạn tập direct permitted subtypes.** Trong Java 17, vị trí hợp lệ phụ thuộc module association:

- **Named module:** sealed parent và từng direct permitted subtype **cùng named module**, có thể khác packages khi accessibility và inheritance rules thỏa.
- **Unnamed module:** sealed parent và direct permitted subtypes **cùng package**, kể cả khi chúng nằm cùng classpath, JAR hoặc project.
- **Chỉ direct subtype:** grandchild qua một `non-sealed` gateway không cần nằm trong `permits` của sealed ancestor; nó tuân rules của nhánh và access/module bình thường.
- **Không suy từ mọi file:** compiler chỉ infer permits khi direct types được declared trong **cùng compilation unit**; nếu source files khác nhau hãy ghi `permits` explicit.

Khi gặp lỗi, hãy lần lượt kiểm tra **named/unnamed module → package → direct extends/implements → permits list → final/sealed/non-sealed → accessibility/readability**. Đây là cách vừa bảo đảm code biên dịch, vừa giữ chủ ý thiết kế để các sealed hierarchies nằm trong một maintenance boundary rõ ràng.
