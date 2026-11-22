# Cú pháp tạo `Outer.Nested` và `outer.new Inner` trong Java

## Mục tiêu học tập

Sau khi học xong, bạn có thể:

- Phân biệt **static nested class** và **non-static member inner class**, hai dạng lớp thành viên thường được khai báo bên trong một lớp bao ngoài.
- Đọc đúng cú pháp `new Outer.Nested(...)` và `outer.new Inner(...)`; hiểu khi nào cần một object `Outer` có sẵn.
- Khai báo kiểu biến bằng `Outer.Nested` hoặc `Outer.Inner`, trong khi hiểu rằng **cách gọi tên kiểu** không nhất thiết giống **cách tạo instance**.
- Dự đoán việc mỗi inner object được gắn với **một enclosing instance** cụ thể; dùng `Outer.this` để tham chiếu đúng outer object khi cần.
- Tạo inner instance trong instance method/constructor của Outer bằng `new Inner(...)` hoặc `this.new Inner(...)`, và trong static context qua một outer reference.
- Biết vì sao `new Outer.Inner()` không hợp lệ cho một non-static inner class từ bên ngoài khi thiếu enclosing instance; phân biệt các lỗi biên dịch với `NullPointerException` khi qualifier là null.
- Viết constructors có parameters cho Nested và Inner, chọn đúng cú pháp truyền đối số và hiểu rằng outer qualifier **không phải constructor argument do người dùng khai báo**.
- Dùng nested classes với private members, static/instance members, access modifiers, generic outer types và nested generic classes đúng Java 17.
- Hiểu mức khác biệt với local classes, anonymous classes, member records và nested interfaces; không đánh đồng mọi thứ “khai báo bên trong” với inner class.
- Nhận diện ảnh hưởng tới lifetime/aliasing, giữ outer object qua inner reference, lưu các inner instances từ những outers khác nhau trong collections.
- Tự sửa các lỗi thường gặp, chạy ví dụ Java 17+ độc lập và kiểm tra đầu ra đáng tin.

## 1. Hai cú pháp trọng tâm

Một lớp có thể chứa hai loại **member classes**:

~~~java
class Outer {
    static class Nested {
    }

    class Inner {
    }
}
~~~

Từ một lớp khác trong cùng phạm vi được phép truy cập:

~~~java
Outer.Nested nested = new Outer.Nested();

Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();
~~~

**Sự khác biệt quan trọng:**

- `Nested` được khai báo `static` trong `Outer`; để tạo instance, dùng `new Outer.Nested()`. Không cần tạo object Outer trước.
- `Inner` **không** khai báo `static`; để tạo instance từ bên ngoài, trước hết phải có một **Outer object** như `outer`. Dùng `outer.new Inner()`.
- `Outer.Inner` **vẫn là một tên kiểu hợp lệ** khi khai báo biến, dù cú pháp tạo instance là `outer.new Inner()`.
- Một `Inner` object gắn với một enclosing `Outer` object cụ thể. `Nested` object không có **enclosing Outer instance tự động** như Inner.

Hãy tách hai câu hỏi:

1. **Kiểu dữ liệu là gì?** → `Outer.Nested` hay `Outer.Inner`.
2. **Tạo đối tượng như thế nào?** → `new Outer.Nested(...)` hay `outer.new Inner(...)`.

Không được xem việc xuất hiện dấu chấm `Outer.Inner` trong **tên kiểu** là bằng chứng rằng có thể viết `new Outer.Inner()`.

## 2. Sơ đồ quan hệ instance

Với static nested:

~~~text
Lớp Outer
    |
    +--- member class: static Nested

new Outer.Nested()
        |
        v
  [Nested object]

Không cần [Outer object] đi kèm.
~~~

Với member inner:

~~~text
Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();

outer -----------------------> [Outer object]
                                    ^
                                    |
                          enclosing instance
                                    |
inner -----------------------> [Inner object]
~~~

Sơ đồ thứ hai mô tả **liên kết enclosing instance**: Inner được tạo qua `outer` nên có thể dùng `Outer.this` để truy cập outer ấy. Đây không phải là việc Java clone/copy outer mỗi khi tạo Inner.

Một Outer object có thể tạo nhiều Inner objects. Một biến kiểu `Outer.Inner` cũng có thể giữ inner được tạo từ một Outer khác, miễn là reference/type/access hợp lệ. Kiểu `Outer.Inner` không mã hóa danh tính **cụ thể** của enclosing outer trong tên kiểu.

## 3. Chương trình chạy đầu tiên: cả hai kiểu trong một file

Lưu **`NestedCreationDemo.java`**:

~~~java
public class NestedCreationDemo {
    static class Outer {
        private final String name;
        private static final String FAMILY = "Java";

        Outer(String name) {
            this.name = name;
        }

        static class Nested {
            String describe() {
                return "Nested@" + FAMILY;
            }
        }

        class Inner {
            String describe() {
                return "Inner@" + name;
            }
        }
    }

    public static void main(String[] args) {
        Outer.Nested nested = new Outer.Nested();

        Outer outer = new Outer("Alpha");
        Outer.Inner inner = outer.new Inner();

        System.out.println(nested.describe());
        System.out.println(inner.describe());
        System.out.println("different types=" +
                !nested.getClass().equals(inner.getClass()));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac NestedCreationDemo.java
java NestedCreationDemo
~~~

**Stdout:**

~~~text
Nested@Java
Inner@Alpha
different types=true
~~~

Trong file này, `Outer` là **static member class của lớp demo** chỉ để chương trình có một `public` top-level class và dễ chạy; bên trong `Outer` lại khai báo `static class Nested` và `class Inner`. Cú pháp cần học vẫn chính xác: `new Outer.Nested()` và `outer.new Inner()`.

`Nested.describe()` dùng trực tiếp static field `FAMILY`. `Inner.describe()` dùng instance field `name` của enclosing Outer. Việc `Nested` có method instance `describe()` là hoàn toàn bình thường: **static nested class không có nghĩa tất cả methods/fields của chính Nested đều phải static**.

## 4. “Static” thuộc quan hệ lồng nhau, không phải trạng thái mỗi object

Xét:

~~~java
class Outer {
    static class Nested {
        private int counter;

        void increment() {
            counter++;
        }
    }
}
~~~

Mỗi lần `new Outer.Nested()` vẫn tạo một object Nested có field instance `counter` độc lập. Từ khóa `static` ở khai báo Nested chỉ nói **Nested không cần một enclosing Outer instance**.

Static nested class có thể:

- Có constructors, instance fields và instance methods như class bình thường.
- Có static members của chính nó.
- Kế thừa class, triển khai interfaces, có generic type parameters.
- Truy cập static members của Outer theo quy tắc access.
- Truy cập một Outer instance **nếu được cung cấp reference rõ ràng**, chứ không có một `Outer.this` tự động.

**Sai:** “`Outer.Nested` không có object instances vì nó static”.  
**Đúng:** “`Outer.Nested` có object instances bình thường, nhưng không gắn ngầm với một object Outer cụ thể”.

## 5. Chương trình: hai Nested objects có state riêng

Lưu **`StaticNestedStateDemo.java`**:

~~~java
public class StaticNestedStateDemo {
    static class Outer {
        private static final String PREFIX = "count";

        static class Nested {
            private int value;

            Nested(int initial) {
                value = initial;
            }

            void increase() {
                value++;
            }

            String report() {
                return PREFIX + "=" + value;
            }
        }
    }

    public static void main(String[] args) {
        Outer.Nested first = new Outer.Nested(2);
        Outer.Nested second = new Outer.Nested(10);

        first.increase();
        first.increase();
        second.increase();

        System.out.println("first " + first.report());
        System.out.println("second " + second.report());
    }
}
~~~

Chạy:

~~~bash
javac StaticNestedStateDemo.java
java StaticNestedStateDemo
~~~

Output:

~~~text
first count=4
second count=11
~~~

Hai Nested objects **không chia sẻ instance field `value`**. Chúng cùng có quyền đọc `PREFIX` static của Outer vì Java access/nesting rules, nhưng các `value` được khởi tạo riêng.

## 6. Enclosing instance của `Inner`

Một non-static member inner class có thể truy cập instance fields/methods của **đối tượng bao ngoài gắn với nó**, kể cả private members theo Java access rules.

~~~java
class Outer {
    private String name = "A";

    class Inner {
        String show() {
            return Outer.this.name;
        }
    }
}
~~~

`Outer.this` là **qualified this**: chỉ Outer instance bao ngoài của inner object hiện tại. Nó khác `this`, vốn chỉ **Inner object hiện tại** khi dùng bên trong Inner instance method.

Nếu bạn tạo hai Outer objects, rồi tạo Inner từ mỗi Outer, mỗi Inner giữ liên kết với Outer tương ứng. Thay đổi field mutable của một Outer có thể được Inner gắn với nó quan sát.

### 6.1. Chương trình minh họa nhiều enclosing instances

Lưu **`EnclosingInstanceDemo.java`**:

~~~java
public class EnclosingInstanceDemo {
    static class Outer {
        private String label;

        Outer(String label) {
            this.label = label;
        }

        void rename(String next) {
            label = next;
        }

        class Inner {
            private final int index;

            Inner(int index) {
                this.index = index;
            }

            boolean belongsTo(Outer candidate) {
                return Outer.this == candidate;
            }

            String describe() {
                return label + "#" + index;
            }
        }
    }

    public static void main(String[] args) {
        Outer left = new Outer("Left");
        Outer right = new Outer("Right");

        Outer.Inner a = left.new Inner(1);
        Outer.Inner b = right.new Inner(1);

        System.out.println("a owner left=" + a.belongsTo(left));
        System.out.println("a owner right=" + a.belongsTo(right));
        System.out.println("b owner right=" + b.belongsTo(right));
        System.out.println("a=" + a.describe());
        System.out.println("b=" + b.describe());

        left.rename("Changed");

        System.out.println("a after change=" + a.describe());
        System.out.println("b after change=" + b.describe());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac EnclosingInstanceDemo.java
java EnclosingInstanceDemo
~~~

Stdout:

~~~text
a owner left=true
a owner right=false
b owner right=true
a=Left#1
b=Right#1
a after change=Changed#1
b after change=Right#1
~~~

`a` liên kết với `left` và `b` liên kết với `right`. Hai Inner references đều có cùng **kiểu tĩnh `Outer.Inner`**, nhưng enclosing objects riêng.

`left.rename` là mutation của **Outer object**, không phải reassign enclosing instance của Inner. Liên kết của `a` với left giữ nguyên, nên `a.describe()` đọc state mới của chính left.

## 7. Khi tạo ở bên ngoài Outer: cú pháp bắt buộc của inner

Trong instance method của một class **khác Outer** và không có enclosing Outer instance ngầm, cú pháp hợp lệ:

~~~java
Outer outer = new Outer();
Outer.Inner item = outer.new Inner();
~~~

Ở đây giả định Outer/Inner có constructors không tham số phù hợp và đều accessible.

Có thể tạo Outer tạm rồi tạo Inner ngay:

~~~java
Outer.Inner item = new Outer().new Inner();
~~~

Đây không tạo ra “Inner không có outer”. Một Outer object vẫn được tạo, chỉ là bạn không lưu reference nó trong biến local riêng. Inner vẫn được liên kết với Outer đó.

Nếu constructor Outer nhận arguments:

~~~java
Outer.Inner item = new Outer("A").new Inner(7);
~~~

`"A"` truyền cho **Outer constructor**, `7` truyền cho **Inner constructor**. Các constructors và accessibility phải phù hợp.

### 7.1. Hai cú pháp dễ viết sai

~~~java
// Outer.Inner bad = new Outer.Inner();
// Sai khi Inner là non-static member class từ ngữ cảnh này:
// không cung cấp enclosing Outer instance.

// Outer.Inner bad = new Inner();
// Sai trong ngữ cảnh không có enclosing Outer phù hợp
// và không có Inner được import/resolve như một type phù hợp.
~~~

Những dòng sai đã comment **không phải ví dụ có thể chạy riêng**. Diagnostics thực tế tùy compiler và cách code được đặt trong scope.

**So sánh:**

~~~java
Outer.Nested nested = new Outer.Nested(); // static member class.
Outer.Inner inner = outer.new Inner();    // non-static member class.
~~~

Dù phần khai báo **type name** đều bắt đầu bằng `Outer.`, cụm sau từ khóa `new` khác nhau do có hay không có **enclosing instance**.

## 8. Constructor arguments: `outer` không phải một formal parameter

Ví dụ:

~~~java
class Outer {
    private final String prefix;

    Outer(String prefix) {
        this.prefix = prefix;
    }

    class Inner {
        private final int number;

        Inner(int number) {
            this.number = number;
        }

        String text() {
            return prefix + number;
        }
    }
}
~~~

Tạo:

~~~java
Outer outer = new Outer("ID-");
Outer.Inner inner = outer.new Inner(42);
~~~

Constructor `Inner(int number)` khai báo đúng **một** parameter: number. Phần `outer.` chỉ cung cấp enclosing instance theo quy tắc ngôn ngữ, **không phải một đối số int/String hoặc parameter `Outer` do lập trình viên khai báo trong constructor signature**.

Nếu muốn API inner nhận Outer khác như một parameter nghiệp vụ, có thể khai báo rõ thêm một `Outer someOther`, nhưng nó **không thay thế** enclosing instance được truyền bởi cú pháp qualified creation.

## 9. Chương trình: Outer constructor và Inner constructor riêng biệt

Lưu **`NestedConstructorDemo.java`**:

~~~java
public class NestedConstructorDemo {
    static class Outer {
        private final String prefix;

        Outer(String prefix) {
            this.prefix = prefix;
        }

        static class Nested {
            private final int id;

            Nested(int id) {
                this.id = id;
            }

            String display() {
                return "Nested-" + id;
            }
        }

        class Inner {
            private final int id;

            Inner(int id) {
                this.id = id;
            }

            String display() {
                return prefix + id;
            }
        }
    }

    public static void main(String[] args) {
        Outer.Nested staticMember = new Outer.Nested(7);

        Outer outer = new Outer("ORD-");
        Outer.Inner inner = outer.new Inner(42);
        Outer.Inner oneExpression =
                new Outer("TMP-").new Inner(9);

        System.out.println(staticMember.display());
        System.out.println(inner.display());
        System.out.println(oneExpression.display());
    }
}
~~~

Chạy:

~~~bash
javac NestedConstructorDemo.java
java NestedConstructorDemo
~~~

Output:

~~~text
Nested-7
ORD-42
TMP-9
~~~

`new Outer.Nested(7)` chỉ gọi constructor Nested. `outer.new Inner(42)` tạo Inner gắn với Outer hiện có. `new Outer("TMP-").new Inner(9)` tạo Outer mới rồi tạo Inner gắn với Outer đó, dù không có biến `outer` local giữ reference.

## 10. Trong instance method của Outer: dùng `new Inner()`

Khi code đang chạy trong instance context của chính Outer, Java đã có enclosing instance **ngầm**: `this` của Outer.

~~~java
class Outer {
    class Inner {
    }

    Inner create() {
        return new Inner();
    }
}
~~~

Trong `Outer.create()`, `new Inner()` tương đương về enclosing instance với `this.new Inner()`.

### 10.1. `this.new Inner()` có hợp lệ không?

Có, trong Outer instance context và khi Inner là member class phù hợp:

~~~java
Inner createAnother() {
    return this.new Inner();
}
~~~

Cách viết tường minh hữu ích để nhấn mạnh outer instance, nhưng `new Inner()` thường gọn, tự nhiên hơn khi không có nhầm lẫn về enclosing context.

### 10.2. Trong `static` method thì sao?

`static` method **không có Outer `this`**. Vì vậy không thể tự viết `new Inner()` trong một static method của Outer mà không cung cấp enclosing Outer.

Cần:

~~~java
static Inner createFor(Outer owner) {
    return owner.new Inner();
}
~~~

Hoặc nếu thực sự cần Outer mới:

~~~java
static Inner createWithNewOwner() {
    return new Outer().new Inner();
}
~~~

Tất cả snippets trong phần này giả định một Outer có constructors và member Inner tương ứng, với access hợp lệ.

## 11. Chương trình chạy: instance context và static context

Lưu **`CreationContextDemo.java`**:

~~~java
public class CreationContextDemo {
    static class Outer {
        private final String name;

        Outer(String name) {
            this.name = name;
        }

        class Inner {
            String say() {
                return name;
            }
        }

        Inner makeImplicit() {
            return new Inner();
        }

        Inner makeExplicit() {
            return this.new Inner();
        }

        static Inner makeFrom(Outer supplied) {
            return supplied.new Inner();
        }

        static Inner makeFresh() {
            return new Outer("Fresh").new Inner();
        }
    }

    public static void main(String[] args) {
        Outer current = new Outer("Current");

        Outer.Inner a = current.makeImplicit();
        Outer.Inner b = current.makeExplicit();
        Outer.Inner c = Outer.makeFrom(current);
        Outer.Inner d = Outer.makeFresh();

        System.out.println("implicit=" + a.say());
        System.out.println("explicit=" + b.say());
        System.out.println("supplied=" + c.say());
        System.out.println("fresh=" + d.say());
    }
}
~~~

Chạy:

~~~bash
javac CreationContextDemo.java
java CreationContextDemo
~~~

Output:

~~~text
implicit=Current
explicit=Current
supplied=Current
fresh=Fresh
~~~

Đường tạo inner khác nhau nhưng tất cả `a`, `b`, `c` đều gắn với Outer `current`; `d` gắn với một Outer object khác do static factory tạo.

## 12. Static nested class vẫn có thể dùng Outer instance nếu nhận reference

Không có enclosing Outer **ngầm** trong static nested class, nhưng Java không cấm Nested nhận Outer reference qua constructor, method hoặc field.

~~~java
class Outer {
    private String state = "ready";

    static class Nested {
        String from(Outer owner) {
            return owner.state;
        }
    }
}
~~~

Nested được phép đọc private `Outer.state` nếu có `owner` object phù hợp do quy tắc nested-class private access. Điều này **không** đồng nghĩa Nested có `Outer.this`.

### 12.1. Chương trình runnable

Lưu **`StaticNestedAccessDemo.java`**:

~~~java
public class StaticNestedAccessDemo {
    static class Outer {
        private static final String VERSION = "v1";
        private final String state;

        Outer(String state) {
            this.state = state;
        }

        static class Nested {
            String showVersion() {
                return VERSION;
            }

            String showStateOf(Outer owner) {
                return owner.state;
            }
        }

        class Inner {
            String showOwnState() {
                return state;
            }
        }
    }

    public static void main(String[] args) {
        Outer.Nested nested = new Outer.Nested();

        Outer first = new Outer("A");
        Outer second = new Outer("B");

        System.out.println("version=" + nested.showVersion());
        System.out.println("first=" + nested.showStateOf(first));
        System.out.println("second=" + nested.showStateOf(second));

        Outer.Inner inner = first.new Inner();
        System.out.println("inner=" + inner.showOwnState());
    }
}
~~~

Chạy:

~~~bash
javac StaticNestedAccessDemo.java
java StaticNestedAccessDemo
~~~

Output:

~~~text
version=v1
first=A
second=B
inner=A
~~~

`Nested.showStateOf(first)` đọc state của **Outer được truyền tường minh**. Trong khi đó `Inner.showOwnState()` dùng enclosing Outer được gắn **lúc tạo Inner**.

## 13. `this`, `Outer.this` và shadowing tên field

Bên trong Inner method:

- `this` là Inner object.
- `Outer.this` là enclosing Outer instance.
- Truy cập tên đơn `name` tuân quy tắc name resolution; nếu Inner khai báo field trùng tên Outer, field Inner có thể che khuất Outer field.
- `Outer.this.name` luôn nói rõ field của enclosing Outer phù hợp.

### 13.1. Chương trình phân biệt hai `this`

Lưu **`QualifiedThisDemo.java`**:

~~~java
public class QualifiedThisDemo {
    static class Outer {
        private final String name;

        Outer(String name) {
            this.name = name;
        }

        class Inner {
            private final String name;

            Inner(String name) {
                this.name = name;
            }

            String bothNames() {
                return this.name + "/" + Outer.this.name;
            }

            boolean isInner(Object candidate) {
                return this == candidate;
            }

            boolean isOwner(Outer candidate) {
                return Outer.this == candidate;
            }
        }
    }

    public static void main(String[] args) {
        Outer owner = new Outer("Outer");
        Outer.Inner child = owner.new Inner("Inner");

        System.out.println("names=" + child.bothNames());
        System.out.println("this is child=" + child.isInner(child));
        System.out.println("outer is owner=" + child.isOwner(owner));
    }
}
~~~

Chạy:

~~~bash
javac QualifiedThisDemo.java
java QualifiedThisDemo
~~~

Output:

~~~text
names=Inner/Outer
this is child=true
outer is owner=true
~~~

Không lẫn `this.name` với `Outer.this.name` khi Inner và Outer khai báo các fields cùng tên. Cũng không dùng `Outer.this` trong một static nested class: Nested không có enclosing instance ngầm để qualified-this tham chiếu.

## 14. Khi qualifier `outer` là `null`

Biểu thức:

~~~java
Outer outer = null;
Outer.Inner inner = outer.new Inner();
~~~

được compiler cho phép nếu loại Outer/Inner và quyền truy cập hợp lệ, nhưng **runtime sẽ ném `NullPointerException`** khi cố tạo inner qua enclosing reference null.

Đây **không phải** `ClassCastException` hoặc lỗi “không tạo được Outer” theo kiểu checked exception. Cũng không có Outer object tự động được tạo thay cho null.

### 14.1. Chương trình bắt lỗi có thể kiểm tra

Lưu **`NullOuterDemo.java`**:

~~~java
public class NullOuterDemo {
    static class Outer {
        class Inner {
            String text() {
                return "created";
            }
        }
    }

    public static void main(String[] args) {
        Outer owner = null;

        try {
            Outer.Inner value = owner.new Inner();
            System.out.println(value.text());
        } catch (NullPointerException expected) {
            System.out.println("null enclosing instance");
        }

        Outer valid = new Outer();
        Outer.Inner safe = valid.new Inner();
        System.out.println(safe.text());
    }
}
~~~

Chạy:

~~~bash
javac NullOuterDemo.java
java NullOuterDemo
~~~

Output:

~~~text
null enclosing instance
created
~~~

Không nên phụ thuộc nội dung nguyên văn của exception message hay stack trace vì có thể khác giữa JDKs. Ví dụ bắt theo **exception type** và in thông báo chủ động để stdout ổn định.

## 15. Outer biến đổi reference sau khi Inner được tạo

`outer.new Inner()` gắn Inner object với **Outer object hiện tại** mà `outer` đang tham chiếu ở thời điểm tạo, không gắn với chính **biến local outer**.

Nếu biến `outer` sau đó được gán reference tới một Outer khác, Inner đã tạo **không đổi owner**.

### 15.1. Chương trình kiểm tra ràng buộc

Lưu **`OwnerReassignmentDemo.java`**:

~~~java
public class OwnerReassignmentDemo {
    static class Outer {
        private final String id;

        Outer(String id) {
            this.id = id;
        }

        class Inner {
            String ownerId() {
                return Outer.this.id;
            }
        }
    }

    public static void main(String[] args) {
        Outer owner = new Outer("A");
        Outer.Inner oldInner = owner.new Inner();

        owner = new Outer("B");
        Outer.Inner newInner = owner.new Inner();

        System.out.println("old owner=" + oldInner.ownerId());
        System.out.println("new owner=" + newInner.ownerId());
    }
}
~~~

Chạy:

~~~bash
javac OwnerReassignmentDemo.java
java OwnerReassignmentDemo
~~~

Output:

~~~text
old owner=A
new owner=B
~~~

Dòng `owner = new Outer("B")` chỉ gán lại biến outer ở caller, không sửa liên kết enclosing instance của `oldInner`.

## 16. Inner gắn với Outer ảnh hưởng vòng đời và bộ nhớ

Khi một inner object còn được tham chiếu, enclosing outer object **có thể vẫn reachable** qua liên kết của inner. Nếu giữ các inner objects lâu dài trong static list/cache, ta có thể vô tình kéo dài lifetime của Outer objects lớn.

~~~text
Long-lived collection
       |
       v
   Inner object
       |
       v
 enclosing Outer
       |
       v
 outer's other data
~~~

**Đây không phải khẳng định “Inner luôn gây memory leak”.** Garbage collection dựa trên reachability; giữ reference tới Inner cũng có thể là ý định đúng. Vấn đề là khi chương trình mong Outer được giải phóng nhưng một cấu trúc sống lâu còn giữ Inner.

Với **static nested class**, không có enclosing Outer instance ngầm. Vì vậy static nested thường phù hợp cho helper không cần state của một Outer cụ thể.

### 16.1. Khi nào cần outer reference rõ ràng?

Nếu helper cần Outer đôi lúc, static nested class có thể nhận reference trong method:

~~~java
Outer.Nested helper = new Outer.Nested();
helper.process(outer);
~~~

Đây là minh họa cần `Nested.process(Outer)` khai báo phù hợp. Helper không nhất thiết giữ outer làm field sau khi method kết thúc.

Nếu helper phải thao tác với **một Outer cố định trong suốt lifetime**, Inner có thể biểu đạt quan hệ đó rõ ràng và thuận tiện, nhưng phải cân nhắc lifetime/ownership.

## 17. Quy tắc quyền truy cập và constructor visibility

Cú pháp tạo đúng **chưa đủ** để compile. Outer, Nested/Inner và constructors cần accessible từ vị trí gọi.

~~~java
public class Outer {
    public static class Nested {
        public Nested() {
        }
    }

    public class Inner {
        public Inner() {
        }
    }
}
~~~

Đây là một **top-level class độc lập** hợp lệ trong file `Outer.java`. Nếu nằm ngoài package của Outer:

~~~java
Outer.Nested a = new Outer.Nested();
Outer outer = new Outer();
Outer.Inner b = outer.new Inner();
~~~

có thể hợp lệ khi import `Outer` đúng và mọi type/constructor public như trên.

Nếu Inner là `private class Inner`, code bên ngoài Outer không thể dùng `Outer.Inner`/`outer.new Inner()` chỉ vì có Outer reference. Outer có thể tạo nó trong chính body và công bố behavior qua API khác.

### 17.1. `private` giữa Outer và member classes

Java cho phép member classes truy cập private members của lớp bao ngoài và outer truy cập private members của nested classes theo quy tắc access trong nested declarations. Từ Java 11, JVM có cơ chế *nestmates* hỗ trợ private access; đây không phải lý do để công khai fields bất cẩn.

### 17.2. Chương trình private member class chỉ được Outer tạo

Lưu **`PrivateNestedAccessDemo.java`**:

~~~java
public class PrivateNestedAccessDemo {
    static class Outer {
        private static class HiddenNested {
            String name() {
                return "hidden nested";
            }
        }

        private class HiddenInner {
            String name() {
                return "hidden inner";
            }
        }

        String useHiddenClasses() {
            HiddenNested a = new HiddenNested();
            HiddenInner b = new HiddenInner();
            return a.name() + " + " + b.name();
        }
    }

    public static void main(String[] args) {
        Outer outer = new Outer();
        System.out.println(outer.useHiddenClasses());

        // Outer.HiddenNested denied = new Outer.HiddenNested();
        // Outer.HiddenInner denied = outer.new HiddenInner();
        // Hai dòng bị comment vì private member types không
        // accessible từ NestedAccessDemo main này.
    }
}
~~~

Chạy:

~~~bash
javac PrivateNestedAccessDemo.java
java PrivateNestedAccessDemo
~~~

Output:

~~~text
hidden nested + hidden inner
~~~

**Quan trọng:** class file bên ngoài/khác scope chỉ nhìn thấy API được công khai. Cú pháp `new Outer.Nested` và `outer.new Inner` **không vượt qua Java access control**.

## 18. Generic Outer: kiểu biến Inner mang theo type argument của Outer

Nếu Outer generic:

~~~java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    class Inner {
        T read() {
            return value;
        }
    }
}
~~~

Từ bên ngoài:

~~~java
Box<String> box = new Box<>("hello");
Box<String>.Inner inner = box.new Inner();
String text = inner.read();
~~~

Type name chính xác của inner instance có thể mang `Box<String>.Inner`, vì Inner không static và có thể dùng type parameter `T` của enclosing Box.

### 18.1. Static nested class bên trong Generic Outer

Một static nested class **không có enclosing generic instance** và không thể dùng type parameter `T` của Outer như một instance member type variable trong chính class declaration. Nó có thể khai báo type parameter riêng:

~~~java
class Box<T> {
    static class Nested<U> {
        U value;
    }
}
~~~

Tạo:

~~~java
Box.Nested<Integer> x = new Box.Nested<>();
~~~

**Không dùng** `Box<String>.Nested<Integer>` như một cách ràng static nested class với một Box<String> instance. Static nested class được định danh qua raw enclosing type name `Box.Nested` và parameters riêng của nó (nếu có).

## 19. Chương trình generic hoàn chỉnh

Lưu **`GenericMemberCreationDemo.java`**:

~~~java
public class GenericMemberCreationDemo {
    static class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        class Inner {
            T read() {
                return value;
            }
        }

        static class Nested<U> {
            private final U data;

            Nested(U data) {
                this.data = data;
            }

            U read() {
                return data;
            }
        }
    }

    public static void main(String[] args) {
        Box<String> words = new Box<>("hello");
        Box<String>.Inner inner = words.new Inner();

        Box<Integer> numbers = new Box<>(7);
        Box<Integer>.Inner other = numbers.new Inner();

        Box.Nested<Double> nested = new Box.Nested<>(2.5);

        System.out.println("words=" + inner.read());
        System.out.println("number=" + other.read());
        System.out.println("nested=" + nested.read());
    }
}
~~~

Chạy:

~~~bash
javac GenericMemberCreationDemo.java
java GenericMemberCreationDemo
~~~

Output:

~~~text
words=hello
number=7
nested=2.5
~~~

Với `Box<T>.Inner`, `T` đến từ kiểu Box thực tế, giúp `inner.read()` có kiểu compile-time tương ứng. Với `Box.Nested<U>`, `U` thuộc Nested, không phụ thuộc vào một Box instance nào.

### 19.1. Cảnh báo raw types

Nếu dùng `Box raw = new Box(...); Box.Inner inner = raw.new Inner();`, code có thể gặp unchecked/raw-type warnings và mất thông tin type. Trong Java hiện đại, ưu tiên generic type an toàn như `Box<String>.Inner`.

## 20. Nhiều tầng inner: mỗi tầng có qualifier riêng

Có thể lồng tiếp:

~~~java
class Outer {
    class Middle {
        class Leaf {
        }
    }
}
~~~

Từ bên ngoài:

~~~java
Outer outer = new Outer();
Outer.Middle middle = outer.new Middle();
Outer.Middle.Leaf leaf = middle.new Leaf();
~~~

`Leaf` là inner của `Middle`, và `Middle` là inner của `Outer`. Ở mỗi qualified creation, qualifier là **object bao ngoài trực tiếp tương ứng**.

**Không viết** `outer.new Leaf()` nếu Leaf không phải member class trực tiếp hoặc inherited member class có thể resolve từ Outer; tên `Leaf` ở đây thuộc Middle.

### 20.1. Chương trình hoàn chỉnh với hai qualified-this

Lưu **`MultiLevelInnerDemo.java`**:

~~~java
public class MultiLevelInnerDemo {
    static class Outer {
        private final String name;

        Outer(String name) {
            this.name = name;
        }

        class Middle {
            private final String section;

            Middle(String section) {
                this.section = section;
            }

            class Leaf {
                private final int number;

                Leaf(int number) {
                    this.number = number;
                }

                String describe() {
                    return Outer.this.name + "/"
                            + Middle.this.section + "/"
                            + number;
                }
            }
        }
    }

    public static void main(String[] args) {
        Outer outer = new Outer("O");
        Outer.Middle middle = outer.new Middle("M");
        Outer.Middle.Leaf leaf = middle.new Leaf(3);

        System.out.println(leaf.describe());

        Outer.Middle.Leaf another =
                new Outer("X").new Middle("Y").new Leaf(5);
        System.out.println(another.describe());
    }
}
~~~

Chạy:

~~~bash
javac MultiLevelInnerDemo.java
java MultiLevelInnerDemo
~~~

Output:

~~~text
O/M/3
X/Y/5
~~~

`Outer.this` và `Middle.this` trong Leaf truy cập đúng hai enclosing instances trong chuỗi. Cách viết một biểu thức `new Outer("X").new Middle("Y").new Leaf(5)` tạo tuần tự từng instance bao ngoài.

## 21. Inner không có nghĩa “chỉ có thể tạo một đối tượng”

Mỗi lần:

~~~java
Outer.Inner one = outer.new Inner();
Outer.Inner two = outer.new Inner();
~~~

thông thường tạo hai Inner objects khác nhau, **cùng enclosing Outer**. Outer có thể có bao nhiêu Inner instances tùy chương trình; không có giới hạn singleton ngầm.

Một Outer class cũng có thể có cả `static Nested` và `Inner` với constructors/methods riêng. Việc Nested là static không tự quyết định identity/equality của Nested instances; nếu không override `equals`, Object equality thường dựa identity.

## 22. Chương trình: nhiều Inner objects cùng Outer

Lưu **`ManyInnerObjectsDemo.java`**:

~~~java
public class ManyInnerObjectsDemo {
    static class Outer {
        private final String ownerName;

        Outer(String ownerName) {
            this.ownerName = ownerName;
        }

        class Inner {
            private final int number;

            Inner(int number) {
                this.number = number;
            }

            String label() {
                return ownerName + ":" + number;
            }

            boolean sameOwner(Inner other) {
                return Outer.this == other.owner();
            }

            Outer owner() {
                return Outer.this;
            }
        }
    }

    public static void main(String[] args) {
        Outer a = new Outer("A");
        Outer b = new Outer("B");

        Outer.Inner first = a.new Inner(1);
        Outer.Inner second = a.new Inner(2);
        Outer.Inner third = b.new Inner(3);

        System.out.println("first==second=" + (first == second));
        System.out.println("first & second owner=" +
                first.sameOwner(second));
        System.out.println("first & third owner=" +
                first.sameOwner(third));

        System.out.println(first.label());
        System.out.println(second.label());
        System.out.println(third.label());
    }
}
~~~

Chạy:

~~~bash
javac ManyInnerObjectsDemo.java
java ManyInnerObjectsDemo
~~~

Output:

~~~text
first==second=false
first & second owner=true
first & third owner=false
A:1
A:2
B:3
~~~

Hai inner objects khác nhau có thể dùng chung một enclosing Outer object, và việc kiểm tra owner ở đây dùng `==` để so **reference identity** của Outer, không phải content equality của các tên.

## 23. Inner và Nested bên trong một static nested context khác

Một `static class Helper` nằm trong Outer không có `Outer.this` tự động. Nếu muốn tạo Outer.Inner từ Helper, Helper phải có một Outer reference rõ ràng:

~~~java
class Outer {
    class Inner {
    }

    static class Helper {
        Inner make(Outer owner) {
            return owner.new Inner();
        }
    }
}
~~~

Method `Helper.make` có thể là instance method của Helper, nhưng điều đó không biến Helper thành **enclosing Outer instance**. Cả static nested class lẫn top-level class khác đều cần `owner` rõ ràng để tạo Outer.Inner.

### 23.1. Chương trình runnable

Lưu **`NestedHelperCreationDemo.java`**:

~~~java
public class NestedHelperCreationDemo {
    static class Outer {
        private final String tag;

        Outer(String tag) {
            this.tag = tag;
        }

        class Inner {
            String tag() {
                return Outer.this.tag;
            }
        }

        static class Helper {
            Inner create(Outer owner) {
                return owner.new Inner();
            }
        }
    }

    public static void main(String[] args) {
        Outer owner = new Outer("Owner");
        Outer.Helper helper = new Outer.Helper();
        Outer.Inner inner = helper.create(owner);

        System.out.println("inner tag=" + inner.tag());
    }
}
~~~

Chạy:

~~~bash
javac NestedHelperCreationDemo.java
java NestedHelperCreationDemo
~~~

Output:

~~~text
inner tag=Owner
~~~

Điểm mấu chốt không phải Helper có method instance hay static, mà là Helper **không tự gắn với một Outer object** chỉ vì Helper được khai báo nested static.

## 24. Java 17 và static members bên trong Inner

Nhiều tài liệu Java cũ nói một inner class không được khai báo static members ngoại trừ constant variables. Hạn chế cú pháp này đã thay đổi: **Java 16 trở đi** cho phép inner classes khai báo static members, bao gồm static methods/static nested classes, theo quy tắc mới.

Điều này **không biến chính Inner thành static nested class**. Để tạo **Inner instance**, bạn vẫn cần enclosing Outer:

~~~java
Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();
~~~

Một static method của Inner không cần tạo Inner instance để gọi, nhưng đó là quy tắc của static method, **không chứng minh Inner là static member class**.

### 24.1. Chương trình Java 17 minh họa

Lưu **`InnerStaticMemberDemo.java`**:

~~~java
public class InnerStaticMemberDemo {
    static class Outer {
        private final String name;

        Outer(String name) {
            this.name = name;
        }

        class Inner {
            static int constructed;

            Inner() {
                constructed++;
            }

            static int total() {
                return constructed;
            }

            String ownerName() {
                return name;
            }
        }
    }

    public static void main(String[] args) {
        System.out.println("before=" + Outer.Inner.total());

        Outer outer = new Outer("A");
        Outer.Inner a = outer.new Inner();
        Outer.Inner b = outer.new Inner();

        System.out.println("after=" + Outer.Inner.total());
        System.out.println("a owner=" + a.ownerName());
        System.out.println("b owner=" + b.ownerName());
    }
}
~~~

Chạy với Java 17+:

~~~bash
javac InnerStaticMemberDemo.java
java InnerStaticMemberDemo
~~~

Output:

~~~text
before=0
after=2
a owner=A
b owner=A
~~~

Không mang giới hạn cũ của Java 8/11 sang Java 17 một cách máy móc. Nhưng cũng không nhầm `Outer.Inner.total()` là cú pháp tạo Inner instance.

## 25. Member record, member interface và enum không giống non-static inner

Bên trong một class có thể khai báo nested **record**, nested **interface** hoặc nested **enum**. Các khai báo member record/interface/enum có tính static ngầm theo quy tắc Java, không gắn với enclosing Outer instance như `class Inner` không static.

Ví dụ:

~~~java
class Outer {
    record Point(int x, int y) {
    }

    interface Converter {
        int apply(int n);
    }

    enum Mode {
        FAST, SAFE
    }
}
~~~

Cách dùng record member:

~~~java
Outer.Point point = new Outer.Point(1, 2);
~~~

Không dùng `outer.new Point(1,2)` vì Point không phải non-static member inner class.

### 25.1. Ví dụ chạy

Lưu **`NestedRecordDemo.java`**:

~~~java
public class NestedRecordDemo {
    static class Outer {
        record Point(int x, int y) {
            int sum() {
                return x + y;
            }
        }

        class Inner {
            private final int offset;

            Inner(int offset) {
                this.offset = offset;
            }

            int addTo(int value) {
                return value + offset;
            }
        }
    }

    public static void main(String[] args) {
        Outer.Point point = new Outer.Point(2, 3);

        Outer owner = new Outer();
        Outer.Inner inner = owner.new Inner(4);

        System.out.println("point sum=" + point.sum());
        System.out.println("inner sum=" +
                inner.addTo(point.sum()));
    }
}
~~~

Chạy:

~~~bash
javac NestedRecordDemo.java
java NestedRecordDemo
~~~

Output:

~~~text
point sum=5
inner sum=9
~~~

**Cần nhớ:** từ “nested” chỉ vị trí khai báo; muốn biết có cần enclosing instance hay không, kiểm tra **static/implicit-static status** của member type.

## 26. Local classes và anonymous classes: không dùng như member name

Một **local class** được khai báo trong block/method, không phải member class được gọi bằng `Outer.Local` từ code bên ngoài. Một **anonymous class** không có tên class do lập trình viên chọn, nên không thể tạo lại bằng `outer.new Anonymous()`.

~~~java
class Outer {
    Runnable create() {
        class LocalTask implements Runnable {
            public void run() {
                System.out.println("local");
            }
        }

        return new LocalTask();
    }
}
~~~

Đoạn code này là mảnh minh họa (chưa có main), dùng để phân biệt vị trí/class kind. Nó không phải câu trả lời cho hai cú pháp cụ thể `Outer.Nested` và `outer.new Inner`, vốn dành cho **named member types** phù hợp.

Một anonymous class expression có dạng `new Runnable() { ... }`, khác hoàn toàn với `outer.new Inner()`.

### 26.1. Cách quyết định nếu thấy lớp bên trong

- Khai báo **`static class Nested`** trực tiếp trong Outer → tạo bằng `new Outer.Nested(...)` nếu accessible.
- Khai báo **`class Inner`** không static trực tiếp trong Outer → tạo qua enclosing instance `outer.new Inner(...)` từ ngoài.
- Khai báo **`record Point`** thành viên trong Outer → là nested record implicitly static, `new Outer.Point(...)`.
- Khai báo local class trong method → chỉ dùng theo phạm vi local và enclosing rules.
- Anonymous class → không có simple class name để caller tạo lại bằng tên.

## 27. Chia sẻ inner objects trong collections

Một `List<Outer.Inner>` có thể chứa inner objects được tạo bởi **nhiều Outer instances khác nhau**. Static type của list element không buộc chúng cùng enclosing owner.

### 27.1. Chương trình runnable

Lưu **`InnerCollectionDemo.java`**:

~~~java
import java.util.List;

public class InnerCollectionDemo {
    static class Outer {
        private final String name;

        Outer(String name) {
            this.name = name;
        }

        class Inner {
            private final int number;

            Inner(int number) {
                this.number = number;
            }

            String label() {
                return name + "#" + number;
            }
        }
    }

    public static void main(String[] args) {
        Outer first = new Outer("A");
        Outer second = new Outer("B");

        List<Outer.Inner> items = List.of(
                first.new Inner(1),
                second.new Inner(2),
                first.new Inner(3));

        for (Outer.Inner item : items) {
            System.out.println(item.label());
        }
    }
}
~~~

Chạy:

~~~bash
javac InnerCollectionDemo.java
java InnerCollectionDemo
~~~

Output:

~~~text
A#1
B#2
A#3
~~~

`List.of` là unmodifiable list về cấu trúc, nhưng điều đó không quyết định Outer objects có mutable state hay không. Nếu Outer.name mutable, Inner.label có thể thay theo enclosing outer; ở ví dụ này name là final String.

## 28. Static nested helper so với inner để xây API

Một quy tắc thiết kế thực dụng:

**Ưu tiên static nested class nếu thành viên không cần một Outer instance tự động.**

Ví dụ:
- `Builder` chỉ tạo sản phẩm mới từ dữ liệu của chính builder, không cần chứa outer object có sẵn.
- `Node` là implementation detail của một data structure nhưng không cần truy cập trực tiếp một outer instance.
- `Result`/`Options` là kiểu phụ trợ có namespace gắn với Outer.

**Ưu tiên non-static inner class khi việc gắn với một Outer instance cụ thể là quan hệ cốt lõi và rõ hợp đồng.**

Ví dụ:
- Một view/iterator tương tác trực tiếp với state của chính Outer instance theo thiết kế.
- Một helper cần truy cập fields/methods instance của đúng enclosing Outer và giữ liên kết đó trong lifetime của helper.

Cân nhắc lifetime và memory retention, đặc biệt khi lưu một Inner trong static singleton/cache/listeners lâu dài.

### 28.1. Không lạm dụng inner để “tiết kiệm truyền parameter”

Nếu một helper chỉ cần một immutable value nhỏ như String ID, việc tạo non-static Inner chỉ để đọc ID có thể kéo theo reference tới cả Outer object lớn. Static nested helper nhận ID trực tiếp thường có ownership/lifetime rõ hơn.

Nếu cần hành vi gắn với instance thật, inner có thể là thiết kế phù hợp — không có luật cấm tuyệt đối.

## 29. Phân biệt method overload, tên lớp và constructor

Các biểu thức:

~~~java
new Outer.Nested(1)
outer.new Inner(1)
~~~

đều là **class instance creation expressions**, nhưng type resolution và enclosing instance requirements khác.

Nếu Outer có hai constructors `Outer()`/`Outer(String)`, điều đó **không** thay đổi constructor parameter list của Inner hay Nested. Constructor nào được gọi tùy theo đối số sau tên type tương ứng.

`outer.new Inner(7)` không phải cú pháp gọi một “method new” trên outer; dấu `.new` là **ngữ pháp tạo inner instance có qualifier** trong Java.

### 29.1. Ví dụ tránh nhầm lời gọi method

~~~java
Outer.Inner inner = outer.new Inner(7);
~~~

- `outer`: một expression kiểu Outer phù hợp, phải non-null tại runtime.
- `new Inner(7)`: tạo instance member Inner gắn với outer.
- `7`: explicit argument tới constructor Inner.
- `Outer.Inner` bên trái: tên kiểu của biến inner.
- `inner`: reference tới Inner instance mới tạo, không phải reference tới Outer.

## 30. Bảng lỗi compile-time và runtime thường gặp

| Code hoặc tình huống | Kết quả | Giải thích |
| --- | --- | --- |
| `new Outer.Nested()` với static member accessible | Hợp lệ | Không cần Outer object |
| `outer.new Inner()` với non-static Inner accessible | Hợp lệ nếu outer non-null runtime | Cần enclosing instance |
| `new Outer.Inner()` từ class ngoài không có enclosing context | Compile-time error | Không cung cấp Outer instance |
| `new Inner()` từ static method Outer (không qualifier) | Compile-time error | Static context không có Outer `this` |
| `new Inner()` từ instance method Outer | Hợp lệ | Dùng enclosing `this` ngầm |
| `this.new Inner()` từ instance method Outer | Hợp lệ | Tường minh cùng enclosing Outer |
| `new Outer().new Inner()` | Hợp lệ | Tạo Outer tạm rồi tạo Inner |
| `outer.new Inner()` với outer null | `NullPointerException` | Không có enclosing object thực tế |
| `outer.new Nested()` với Nested static | Không dùng cú pháp này | Tạo bằng `new Outer.Nested()` |
| `Outer.this` bên trong Inner instance | Hợp lệ | Truy cập enclosing Outer |
| `Outer.this` bên trong static Nested | Compile-time error | Không có enclosing Outer instance ngầm |
| `Outer.Inner` làm variable type | Hợp lệ nếu accessible | Tên kiểu không đồng nghĩa cú pháp khởi tạo |
| `Box<String>.Inner` với non-static member của Box<T> | Hợp lệ | Inner dùng T của enclosing Box |
| `Box.Nested<U>` với static nested generic | Hợp lệ | U là type parameter của Nested |
| `Outer.Point` là member record | Tạo với `new Outer.Point(...)` | Member record implicitly static |
| `Outer.PrivateInner` ngoài phạm vi cho phép | Compile-time access error | Cú pháp không vượt access modifiers |

Diagnostics compiler có thể được diễn đạt khác nhau theo JDK/IDE. Hãy xác định **lỗi do thiếu enclosing instance, tên type, constructor signature, null qualifier hay accessibility**, không dựa hoàn toàn vào một chuỗi error message.

## 31. Phân tích một lỗi điển hình theo từng bước

Giả sử:

~~~java
class School {
    class Student {
        Student(String name) {
        }
    }
}
~~~

Một nơi khác trong package gọi:

~~~java
// School.Student a = new School.Student("Lan"); // Sai.
~~~

Tại sao?

1. `Student` là **non-static member class**.
2. `School.Student` là **tên kiểu**, không bảo đảm có School instance.
3. `new School.Student("Lan")` thiếu **enclosing School object**.
4. Sửa:

~~~java
School school = new School();
School.Student a = school.new Student("Lan");
~~~

Nếu Student không cần truy cập School object, lựa chọn thiết kế khác là đổi declaration sang `static class Student` (nếu scope/domain cho phép), rồi dùng `new School.Student("Lan")`.

**Không tự đổi Inner thành static chỉ để sửa lỗi cú pháp** nếu việc gắn Student với School instance cụ thể là business relationship cần giữ.

## 32. Thực hành: chuyển từ static nested sang inner cần sửa những gì?

Ban đầu:

~~~java
class Container {
    static class Entry {
    }
}

Container.Entry entry = new Container.Entry();
~~~

Nếu bạn thay `static class Entry` thành `class Entry`, biểu thức `new Container.Entry()` ở code ngoài không còn là cú pháp tạo instance phù hợp.

Bạn cần:

~~~java
Container container = new Container();
Container.Entry entry = container.new Entry();
~~~

Ngoài cú pháp, đây là **thay đổi mô hình object**:

- Entry mới gắn với Container instance.
- Entry có thể truy cập state của Container trực tiếp.
- Entry có thể kéo dài reachability/lifetime của Container.
- Constructors/factories/callers có thể cần chỉnh.
- Các test phải xác nhận Entry thuộc đúng Container chứ không chỉ biên dịch.

Ngược lại, khi đổi non-static Inner sang static nested, phải xóa code dựa vào `Outer.this`/outer instance implicit và cung cấp Outer reference bằng API nếu còn cần.

## 33. Chương trình tổng hợp so sánh qua một interface chung

Lưu **`NestedVsInnerIntegrationDemo.java`**:

~~~java
public class NestedVsInnerIntegrationDemo {
    interface Descriptor {
        String describe();
    }

    static class Outer {
        private final String owner;
        private static final String KIND = "static";

        Outer(String owner) {
            this.owner = owner;
        }

        static class Nested implements Descriptor {
            private final String label;

            Nested(String label) {
                this.label = label;
            }

            @Override
            public String describe() {
                return KIND + ":" + label;
            }
        }

        class Inner implements Descriptor {
            private final String label;

            Inner(String label) {
                this.label = label;
            }

            @Override
            public String describe() {
                return owner + ":" + label;
            }
        }
    }

    static void show(Descriptor value) {
        System.out.println(value.describe());
    }

    public static void main(String[] args) {
        Outer.Nested nested = new Outer.Nested("N");

        Outer first = new Outer("A");
        Outer second = new Outer("B");
        Outer.Inner firstInner = first.new Inner("I1");
        Outer.Inner secondInner = second.new Inner("I2");

        show(nested);
        show(firstInner);
        show(secondInner);
    }
}
~~~

Chạy:

~~~bash
javac NestedVsInnerIntegrationDemo.java
java NestedVsInnerIntegrationDemo
~~~

Output:

~~~text
static:N
A:I1
B:I2
~~~

**Quan sát:**

- Nested và Inner có thể cùng implement một interface, cùng được truyền vào method polymorphic.
- `Nested` đọc static field `KIND`; `Inner` đọc owner instance field `owner`.
- Cách tạo từng object khác nhau nhưng cách sử dụng qua interface có thể thống nhất.
- Static nested và inner là **cơ chế gắn class với enclosing context**, không phải hai loại “object không tương thích” với polymorphism.

## 34. Test các cú pháp bằng điều kiện xác định

Khi viết unit tests hoặc một bài tự luyện, nên kiểm tra:

1. `new Outer.Nested()` tạo object Nested không cần Outer instance.
2. `outer.new Inner()` tạo inner object và có owner identity đúng.
3. Hai outers tạo inner objects với data khác nhau khi outer state khác.
4. Một outer tạo hai inner objects có identity riêng.
5. `Outer.this` trong Inner tham chiếu đúng outer object.
6. Thay reference local outer sau khi tạo inner **không đổi owner của inner cũ**.
7. Tạo inner qua null qualifier ném NPE theo contract.
8. Private member classes không accessible từ code ngoài.
9. Generic `Box<String>.Inner` có type parameter T phù hợp.
10. Static nested `Box.Nested<Integer>` không cần Box instance.
11. Member record tạo bằng `new Outer.RecordName(...)` nếu accessible.
12. Code dùng static context nhận được compiler error khi cố `new Inner()` trực tiếp.

### 34.1. Chương trình tự kiểm thử, không cần JUnit

Lưu **`NestedCreationContractTest.java`**:

~~~java
public class NestedCreationContractTest {
    static class Outer {
        private final String id;

        Outer(String id) {
            this.id = id;
        }

        static class Nested {
            int value() {
                return 7;
            }
        }

        class Inner {
            String owner() {
                return Outer.this.id;
            }

            boolean belongsTo(Outer expected) {
                return Outer.this == expected;
            }
        }
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        Outer.Nested nested = new Outer.Nested();
        check(nested.value() == 7, "nested construction");

        Outer outer = new Outer("A");
        Outer.Inner first = outer.new Inner();
        Outer.Inner second = outer.new Inner();

        check(first != second, "inner identity");
        check(first.belongsTo(outer), "enclosing owner");
        check(second.belongsTo(outer), "second owner");
        check("A".equals(first.owner()), "owner data");

        Outer.Inner fresh = new Outer("B").new Inner();
        check("B".equals(fresh.owner()), "fresh owner");

        System.out.println("all nested creation checks passed");
    }
}
~~~

Chạy:

~~~bash
javac NestedCreationContractTest.java
java NestedCreationContractTest
~~~

Output:

~~~text
all nested creation checks passed
~~~

Dùng method `check` thay vì Java `assert` mặc định có thể bị tắt khi không chạy với `-ea`. Ở đây mọi điều kiện được kiểm tra trong lệnh `java NestedCreationContractTest` thông thường.

## 35. Câu hỏi ôn tập và đáp án

**Câu 1.** `static class Nested` khai báo trong Outer có cần tạo một Outer object trước khi tạo Nested không?  
**Đáp án:** Không. Dùng `new Outer.Nested(...)` nếu type/constructor accessible.

**Câu 2.** `class Inner` không static có cần enclosing instance khi tạo từ code bên ngoài không?  
**Đáp án:** Có. Dùng `outer.new Inner(...)` với outer thích hợp.

**Câu 3.** `Outer.Inner` có được dùng làm tên kiểu của biến không?  
**Đáp án:** Có, nếu accessible; nhưng creation syntax vẫn khác với static nested.

**Câu 4.** Vì sao `new Outer.Inner()` thiếu outer thường sai?  
**Đáp án:** Non-static inner class cần một enclosing Outer instance.

**Câu 5.** `new Outer().new Inner()` có tạo Outer object không?  
**Đáp án:** Có. Inner được gắn với Outer tạm mới tạo.

**Câu 6.** `outer.new Inner(7)` truyền `outer` như một parameter constructor do lập trình viên khai báo không?  
**Đáp án:** Không. Qualifier cung cấp enclosing instance, còn `7` là explicit argument.

**Câu 7.** `new Inner()` trong instance method Outer có hợp lệ không?  
**Đáp án:** Có. Enclosing Outer instance ngầm là `this`.

**Câu 8.** `new Inner()` từ static method Outer, không có qualifier, có hợp lệ không?  
**Đáp án:** Không, thiếu enclosing instance.

**Câu 9.** `this.new Inner()` từ instance method Outer có hợp lệ không?  
**Đáp án:** Có, nếu Inner accessible và constructor phù hợp.

**Câu 10.** `outer.new Inner()` với `outer == null` xảy ra gì?  
**Đáp án:** `NullPointerException` khi tạo inner.

**Câu 11.** `Outer.this` trong Inner trỏ tới object nào?  
**Đáp án:** Enclosing Outer instance gắn với Inner đó.

**Câu 12.** `this` bên trong Inner instance method trỏ tới object nào?  
**Đáp án:** Chính Inner instance.

**Câu 13.** Nested có thể có instance fields riêng không?  
**Đáp án:** Có. `static` ở khai báo nested không làm các instance fields của Nested trở thành static.

**Câu 14.** Static Nested có thể đọc Outer instance field không?  
**Đáp án:** Có khi nhận một Outer reference tường minh và có quyền truy cập; không có Outer.this ngầm.

**Câu 15.** Hai Inner objects tạo từ hai Outer objects khác nhau có cùng tên kiểu không?  
**Đáp án:** Có thể cùng kiểu `Outer.Inner`, nhưng enclosing instances khác nhau.

**Câu 16.** Một Outer có thể tạo nhiều Inner objects không?  
**Đáp án:** Có, mỗi lần tạo tạo một Inner instance khác nhau thông thường.

**Câu 17.** Thay reference biến `outer` sau khi tạo inner có đổi enclosing instance của inner cũ không?  
**Đáp án:** Không. Inner giữ quan hệ với object được dùng tại lúc tạo.

**Câu 18.** Nếu Inner còn sống rất lâu, Outer có thể được giữ reachable không?  
**Đáp án:** Có, liên kết enclosing instance có thể kéo dài lifetime của Outer.

**Câu 19.** `Box<String>.Inner` với generic outer có hợp lệ không?  
**Đáp án:** Có khi Inner non-static và outer type/constructor hợp lệ.

**Câu 20.** `Box.Nested<Integer>` có cần một Box<Integer> object không?  
**Đáp án:** Không nếu Nested là static và type argument Integer thuộc Nested.

**Câu 21.** Static nested class dùng type parameter `T` của generic enclosing Box<T> trực tiếp được không?  
**Đáp án:** Không; static nested class không có enclosing Box<T> instance/type parameter context như non-static Inner.

**Câu 22.** Có thể tạo `Outer.Middle.Leaf` bằng `middle.new Leaf()` không?  
**Đáp án:** Có nếu Leaf là inner member của Middle, middle đúng kiểu và accessible.

**Câu 23.** `Outer.this` có dùng được trong static Nested không?  
**Đáp án:** Không có enclosing Outer instance ngầm.

**Câu 24.** Inner class Java 17 có thể khai báo static method không?  
**Đáp án:** Có theo quy tắc Java 16+; điều này không bỏ yêu cầu enclosing Outer khi tạo Inner instance.

**Câu 25.** Member record khai báo trong Outer được tạo bằng cú pháp nào?  
**Đáp án:** `new Outer.RecordName(...)` nếu accessible; member record implicitly static.

**Câu 26.** Private Inner có được tạo bằng `outer.new Inner()` từ class bên ngoài chỉ vì có reference outer không?  
**Đáp án:** Không, Java access control vẫn áp dụng.

**Câu 27.** Local class khai báo trong method có thể tạo từ ngoài bằng `new Outer.Local()` không?  
**Đáp án:** Không, local class không phải named member class accessible theo dạng đó.

**Câu 28.** Khi nào chọn static nested helper thay cho Inner?  
**Đáp án:** Khi helper không cần enclosing Outer instance tự động, muốn giảm coupling/lifetime retention.

**Câu 29.** Nếu method trong Nested nhận `Outer owner` để đọc state thì nó có biến Nested thành Inner không?  
**Đáp án:** Không. Reference explicit chỉ là dữ liệu được truyền, khác enclosing instance ngầm.

**Câu 30.** Cách nhớ hai cú pháp ngắn gọn nhất?  
**Đáp án:** **Static member: `new Outer.Nested(...)`. Non-static member: `outer.new Inner(...)`.**

## 36. Checklist trước khi biên dịch code tạo nested objects

- [ ] Member class có `static` hay non-static?
- [ ] Nếu non-static, đã có enclosing Outer instance chưa?
- [ ] Tên type có đúng scope `Outer.Inner`/`Outer.Nested` không?
- [ ] Constructor có phù hợp đối số được truyền không?
- [ ] Outer, member type, constructor có accessible từ caller không?
- [ ] Trong static context có vô tình viết `new Inner()` không?
- [ ] Có muốn outer mới bằng `new Outer().new Inner()` hay reuse outer hiện tại?
- [ ] Có bị null enclosing qualifier tại runtime không?
- [ ] Có shadowing cần dùng `Outer.this` không?
- [ ] Có static nested class đang cố truy cập instance field mà thiếu reference không?
- [ ] Nếu Outer generic, có dùng `Outer<T>.Inner` đúng không?
- [ ] Nếu static nested generic, có gọi qua `Outer.Nested<U>` đúng không?
- [ ] Có member record/interface/enum implicitly static bị nhầm là inner không?
- [ ] Enclosing instance relation có ảnh hưởng memory/lifetime/ownership không?
- [ ] Nếu chứa trong collection, các Inner instances có thể có owners khác nhau không?
- [ ] Đã thử compile trên Java 17 với đúng tên file/public class và test stdout chưa?

## 37. Tài liệu tham khảo

- Java Language Specification (Java SE 17), [`8.1.3 — Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): định nghĩa inner class/enclosing instance.
- Java Language Specification, [`8.5 — Member Type Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.5): nested member types và static declarations.
- Java Language Specification, [`15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): qualified class instance creation.
- Java Language Specification, [`15.9.2 — Determining Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.2): enclosing instance khi tạo inner.
- Java Language Specification, [`15.8.4 — Qualified `this`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.4): cú pháp `Outer.this`.
- Java Language Specification, [`8.8 — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): constructor parameters/creation.
- Java Language Specification, [`6.5 — Determining the Meaning of a Name](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.5): name resolution.
- Java Language Specification, [`6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): visibility và access modifiers.
- Java Language Specification, [`8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): member records và implicit static.
- Java Tutorials, [Nested Classes](https://docs.oracle.com/javase/tutorial/java/javaOO/nested.html): khái niệm static nested/inner. Tài liệu tutorial có thể phản ánh source level cũ; khi có khác biệt với cú pháp Java 17 (như static members trong inner), ưu tiên JLS 17.

## Tổng kết

**`Outer.Nested`** và **`Outer.Inner`** đều là tên kiểu của các lớp thành viên trong Outer, nhưng có **quy tắc tạo instance khác nhau**:

- Với `static class Nested`: `Outer.Nested value = new Outer.Nested(...)`. Không cần enclosing Outer object.
- Với `class Inner` không static: `Outer outer = new Outer(...); Outer.Inner value = outer.new Inner(...)`. Inner gắn với đúng Outer instance dùng làm qualifier.
- Bên trong instance context của Outer, có thể viết `new Inner(...)` hoặc `this.new Inner(...)`.
- Bên trong static context, phải có Outer reference tường minh để tạo Inner.
- `Outer.this` trong Inner truy cập enclosing instance, còn `this` chỉ Inner object.
- Nếu outer qualifier null, qualified inner creation ném `NullPointerException`.
- Nested classes vẫn tuân access modifiers, constructor signatures, generic typing và luật về enclosing context.

Chọn **static nested class khi không cần liên kết Outer instance tự động**; chọn **member inner class khi việc gắn với một Outer object cụ thể là một phần thiết kế**. Thực hành kiểm tra tên kiểu, cú pháp `new`, reference identity và lifetime sẽ giúp tránh phần lớn lỗi khi dùng lớp lồng nhau trong Java.
