# Che khuất tên và định danh bằng `Outer.this` trong Java

## 1. Vấn đề: một tên xuất hiện ở nhiều phạm vi

Trong Java, **lớp trong không static (*inner class*)** có thể truy cập các thành viên của một **đối tượng thuộc lớp bao ngoài (*enclosing instance*)**. Nhưng lớp trong cũng có thể khai báo field, tham số hoặc biến cục bộ **trùng tên** với thành viên bên ngoài.

Ví dụ:

```java
class Outer {
    String name = "outer";

    class Inner {
        String name = "inner";

        void print(String name) {
            System.out.println(name);
            System.out.println(this.name);
            System.out.println(Outer.this.name);
        }
    }
}
```

Ba biểu thức trong method `print` mang ba ý nghĩa khác nhau:

- `name`: **tham số** của method, vì tên tham số che khuất những khai báo cùng tên ở phạm vi ngoài.
- `this.name`: field `name` của **Inner object đang thực thi method**.
- `Outer.this.name`: field `name` của **Outer object bao ngoài gắn với Inner object đó**.

Cú pháp **`Outer.this`** là *qualified this expression*. Nó chỉ rõ một đối tượng đang bao quanh về mặt từ vựng và có **enclosing instance** phù hợp. Nó không tạo đối tượng mới, không lấy một đối tượng Outer bất kỳ và không phải cơ chế truy cập trường static.

> **Quy tắc nhớ nhanh:** `name` tra cứu tên theo phạm vi; `this.name` bắt đầu từ receiver hiện tại; `Outer.this.name` bắt đầu từ enclosing instance có type `Outer`.

Bài học thuộc nhóm **Lớp lồng nhau**, tập trung vào cách **che khuất tên (*shadowing*)**, phân biệt các receiver và sử dụng `Outer.this` đúng chỗ trong Java 17+.

## 2. Ví dụ hoàn chỉnh đầu tiên: ba giá trị của cùng một tên

Tạo tệp **`OuterThisBasicsDemo.java`**:

```java
class Outer {
    private final String name = "OUTER";

    class Inner {
        private final String name = "INNER";

        void show(String name) {
            System.out.println("parameter=" + name);
            System.out.println("inner=" + this.name);
            System.out.println("outer=" + Outer.this.name);
        }
    }
}

public class OuterThisBasicsDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        Outer.Inner inner = outer.new Inner();

        inner.show("LOCAL");
    }
}
```

Biên dịch và chạy:

```bash
javac OuterThisBasicsDemo.java
java OuterThisBasicsDemo
```

**Standard output:**

```text
parameter=LOCAL
inner=INNER
outer=OUTER
```

Diễn giải từ trên xuống:

1. `new Outer()` tạo một Outer object.
2. `outer.new Inner()` tạo Inner object **gắn với outer**.
3. Khi `show("LOCAL")` chạy, tham số `name` có giá trị LOCAL.
4. `this` trong `Inner.show` là receiver Inner, nên `this.name` là INNER.
5. `Outer.this` chỉ enclosing Outer instance, nên `Outer.this.name` là OUTER.

**Lưu ý quan trọng:** Outer field khai báo `private` nhưng Inner vẫn được truy cập hợp lệ. Trong Java, các nested classes và enclosing classes có quyền truy cập private members của nhau theo quy tắc nested class access; `private` không tự chặn `Outer.this.name` trong ví dụ.

## 3. “Che khuất tên” nghĩa là gì?

*Shadowing* xảy ra khi một khai báo ở phạm vi gần hơn khiến cách sử dụng **tên đơn giản không định danh** chọn khai báo ấy thay vì khai báo cùng tên ở phạm vi xa hơn.

Ví dụ:

```java
int score = 10;
{
    // int score = 20; // Không hợp lệ nếu trùng tên local
    // trong phạm vi local còn chồng lấp như ví dụ này.
}
```

Đây là **mảnh code** minh họa một quy tắc local-variable khác với field shadowing: Java **không cho phép tùy ý khai báo lại local variable trong các khối phạm vi lồng nhau chồng lấp**. Nhưng field của class và parameter/local variable **có thể trùng tên** theo những quy tắc khác.

Trong nested class:

```java
class Outer {
    int number = 1;

    class Inner {
        int number = 2;

        void show(int number) {
            System.out.println(number);
            System.out.println(this.number);
            System.out.println(Outer.this.number);
        }
    }
}
```

Ở đây:

- `number` trong method trỏ đến parameter.
- `this.number` trỏ đến Inner field.
- `Outer.this.number` trỏ đến Outer field.

**Không phải** compiler “quên” Outer field. Nó vẫn tồn tại, nhưng khi một tên ngắn bị che, bạn phải dùng **receiver định danh** để nói chính xác mình muốn field nào.

## 4. Phân biệt shadowing field với gán lại giá trị

Che khuất tên là vấn đề **name resolution tại compile time**; nó không đồng nghĩa với việc thay object reference hoặc mutate field.

Tạo **`ShadowingAssignmentsDemo.java`**:

```java
class Outer {
    private int count = 1;

    class Inner {
        private int count = 2;

        void modify(int count) {
            count += 10;                 // Chỉ sửa parameter.
            this.count += 20;            // Sửa Inner field.
            Outer.this.count += 30;      // Sửa Outer field.

            System.out.println("parameter=" + count);
            System.out.println("inner=" + this.count);
            System.out.println("outer=" + Outer.this.count);
        }
    }

    int count() {
        return count;
    }
}

public class ShadowingAssignmentsDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        Outer.Inner inner = outer.new Inner();

        inner.modify(5);
        System.out.println("outside outer=" + outer.count());
    }
}
```

```bash
javac ShadowingAssignmentsDemo.java
java ShadowingAssignmentsDemo
```

```text
parameter=15
inner=22
outer=31
outside outer=31
```

Đây là ba vùng state khác nhau:

- Parameter `count` là local value của lần gọi method, lúc đầu bằng 5.
- `this.count` là instance field thuộc Inner object, lúc đầu bằng 2.
- `Outer.this.count` là instance field thuộc associated Outer object, lúc đầu bằng 1.

Khi sửa Outer field từ Inner, method `outer.count()` ở bên ngoài cũng thấy 31 vì đây là **cùng Outer instance**, không phải một copy dữ liệu.

## 5. `Outer.this` là biểu thức chỉ *đối tượng*, không chỉ một field

Cần hiểu đầy đủ cú pháp:

```java
Outer.this
```

Đây là một **expression có giá trị là reference đến enclosing Outer instance**. Bạn có thể:

- Đọc field: `Outer.this.name`.
- Gọi instance method: `Outer.this.describe()`.
- Truyền làm argument: `register(Outer.this)`.
- So sánh identity: `Outer.this == expectedOuter`.
- Tạo method reference: `Outer.this::describe` khi functional interface phù hợp.

**Không thể gán lại bản thân `Outer.this`** như một field mutable:

```java
// Outer.this = anotherOuter; // Sai: qualified this không phải lvalue.
```

Liên kết enclosing instance được xác lập khi inner object được tạo; bình thường không thể “đổi Inner này sang Outer khác” bằng assignment tới `Outer.this`.

### Ví dụ dùng method, object identity

Tạo **`OuterInstanceReferenceDemo.java`**:

```java
final class Outer {
    private final String id;

    Outer(String id) {
        this.id = id;
    }

    String describe() {
        return "Outer(" + id + ")";
    }

    class Inner {
        String summary() {
            return Outer.this.describe();
        }

        boolean belongsTo(Outer candidate) {
            return Outer.this == candidate;
        }
    }
}

public class OuterInstanceReferenceDemo {
    public static void main(String[] args) {
        Outer first = new Outer("A");
        Outer second = new Outer("B");

        Outer.Inner inner = first.new Inner();

        System.out.println(inner.summary());
        System.out.println(inner.belongsTo(first));
        System.out.println(inner.belongsTo(second));
    }
}
```

```bash
javac OuterInstanceReferenceDemo.java
java OuterInstanceReferenceDemo
```

```text
Outer(A)
true
false
```

`Outer.this` trong `inner.summary` là **first**, không phải second, vì Inner được tạo bằng `first.new Inner()`.

## 6. Vì sao inner object biết enclosing Outer instance?

Một **non-static member inner class** được khai báo ở trong một class và khi được tạo trong ngữ cảnh thông thường, instance của nó gắn với một enclosing instance.

Ví dụ:

```java
Outer a = new Outer();
Outer b = new Outer();

Outer.Inner ia = a.new Inner();
Outer.Inner ib = b.new Inner();
```

Đây là **mảnh code minh họa**, giả định Outer có constructor không tham số và Inner có constructor phù hợp. `ia` gắn với a, `ib` gắn với b.

Sơ đồ:

```text
a ──> Outer A <──── enclosing instance ── Inner ia

b ──> Outer B <──── enclosing instance ── Inner ib
```

Khi method của `ia` dùng `Outer.this`, nó nhận Outer A. Khi method của `ib` dùng `Outer.this`, nó nhận Outer B.

JVM/compiler có thể dùng các trường tổng hợp hay cách biểu diễn tương đương để cài đặt liên kết này. **Không nên phụ thuộc vào tên field compiler-generated** như `this$0` hoặc layout thực thi để viết application code. Hãy dựa trên semantic `Outer.this` được Java quy định.

## 7. Hai Outer khác nhau, cùng kiểu Inner nhưng không chung state

Tạo **`TwoOuterInstancesDemo.java`**:

```java
class Outer {
    private final String label;
    private int counter;

    Outer(String label) {
        this.label = label;
    }

    class Inner {
        void incrementOuter() {
            Outer.this.counter++;
        }

        String snapshot() {
            return label + "=" + Outer.this.counter;
        }
    }
}

public class TwoOuterInstancesDemo {
    public static void main(String[] args) {
        Outer first = new Outer("first");
        Outer second = new Outer("second");

        Outer.Inner left = first.new Inner();
        Outer.Inner right = second.new Inner();

        left.incrementOuter();
        left.incrementOuter();
        right.incrementOuter();

        System.out.println(left.snapshot());
        System.out.println(right.snapshot());
    }
}
```

```bash
javac TwoOuterInstancesDemo.java
java TwoOuterInstancesDemo
```

```text
first=2
second=1
```

Mỗi Inner instance dùng enclosing object của **chính nó**. `Outer.this` không phải một static variable dùng chung cho mọi Inner instances.

Điều này quan trọng trong event handlers, callbacks, UI components hoặc các helpers chứa trong một owner object: inner instance có thể thao tác đúng trạng thái của owner.

## 8. `this` và `Outer.this` khi không bị trùng tên

Ngay cả khi không shadowing, bạn vẫn có thể chọn cách viết có định danh:

```java
class Outer {
    private int capacity = 10;

    class Inner {
        int capacity() {
            return capacity;            // Có thể tra tới outer.
        }

        int explicitCapacity() {
            return Outer.this.capacity; // Rõ owner.
        }
    }
}
```

Trong ví dụ, Inner **không khai báo** field `capacity`, nên lookup tên đơn giản có thể tìm outer field. `Outer.this.capacity` nói rõ nơi field thuộc về và giảm rủi ro khi Inner sau này thêm field trùng tên.

**Cân bằng khả năng đọc:** Không nhất thiết viết `Outer.this` cho mọi lần dùng outer field. Dùng nó khi tên bị shadow, khi code dễ mơ hồ, hoặc khi muốn làm rõ receiver trong logic nhiều tầng.

## 9. Nhiều tầng nested class: `Outer.this`, `Middle.this`, `this`

Một inner class có thể được khai báo trong một inner class khác. Khi đó có **nhiều enclosing instances về mặt từ vựng**.

Tạo **`ThreeLevelShadowingDemo.java`**:

```java
class Outer {
    private final String id = "OUTER";

    class Middle {
        private final String id = "MIDDLE";

        class Inner {
            private final String id = "INNER";

            void show(String id) {
                System.out.println("parameter=" + id);
                System.out.println("inner=" + this.id);
                System.out.println("middle=" + Middle.this.id);
                System.out.println("outer=" + Outer.this.id);
            }
        }
    }
}

public class ThreeLevelShadowingDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        Outer.Middle middle = outer.new Middle();
        Outer.Middle.Inner inner = middle.new Inner();

        inner.show("LOCAL");
    }
}
```

```bash
javac ThreeLevelShadowingDemo.java
java ThreeLevelShadowingDemo
```

```text
parameter=LOCAL
inner=INNER
middle=MIDDLE
outer=OUTER
```

Tra cứu của từng expression:

| Biểu thức | Receiver / phạm vi |
| --- | --- |
| `id` | Tham số method `show` |
| `this.id` | Inner object |
| `Middle.this.id` | Middle instance bao quanh Inner |
| `Outer.this.id` | Outer instance bao quanh Middle và Inner |

**Sai lầm hay gặp:** Cứ có nhiều tầng thì `Outer.this` trỏ đến “Outer gần nhất được tạo”. Không đúng: nó trỏ đến **enclosing instance của Outer tương ứng với inner object đang chạy**.

## 10. Dùng reference identity để chứng minh chuỗi enclosing instances

Có thể kiểm bằng `==`:

Tạo **`EnclosingIdentityDemo.java`**:

```java
class Outer {
    class Middle {
        class Inner {
            boolean linkedTo(Outer expectedOuter,
                             Middle expectedMiddle) {
                return Outer.this == expectedOuter
                        && Middle.this == expectedMiddle;
            }
        }
    }
}

public class EnclosingIdentityDemo {
    public static void main(String[] args) {
        Outer first = new Outer();
        Outer other = new Outer();

        Outer.Middle middle = first.new Middle();
        Outer.Middle.Inner inner = middle.new Inner();

        System.out.println(inner.linkedTo(first, middle));
        System.out.println(inner.linkedTo(other, middle));
    }
}
```

```bash
javac EnclosingIdentityDemo.java
java EnclosingIdentityDemo
```

```text
true
false
```

Đây là kiểm identity, **không gọi `equals()`**. Nếu Outer override equals theo value, hai Outer objects có thể equals nhau mà vẫn không phải cùng enclosing instance.

Dùng `==` trong phép thử này là có chủ đích vì câu hỏi là **có phải chính object bao quanh đó không?**

## 11. `Outer.this` không giống `Outer.class`

Hai expression này phục vụ mục tiêu hoàn toàn khác:

- `Outer.this`: một **Outer instance reference** đang liên kết về mặt lexical/enclosing trong instance context phù hợp.
- `Outer.class`: một `Class<Outer>` object mô tả **kiểu Outer**.
- `Outer.staticField`: tham chiếu đến **static field** của class, không cần enclosing instance.

Ví dụ minh họa:

```java
class Outer {
    static int sharedCount = 1;
    int instanceCount = 2;

    class Inner {
        int total() {
            return Outer.sharedCount + Outer.this.instanceCount;
        }
    }
}
```

`Outer.class` không có ý nghĩa “lấy outer object đang chứa inner”; class metadata không thể thay thế instance reference.

**Cú pháp nên tránh khi đọc code:** `Outer.this.instanceCount` là instance-qualified access; còn `Outer.sharedCount` là static-qualified access. Nếu mục đích là truy cập static field, viết qua tên lớp rõ ràng.

## 12. Static nested class không có implicit enclosing Outer instance

Đây là giới hạn quan trọng nhất của `Outer.this`.

Một **static nested class** được khai báo:

```java
class Outer {
    private int value = 10;

    static class Nested {
        void show() {
            // System.out.println(Outer.this.value); // Không hợp lệ.
        }
    }
}
```

`Nested` ở ví dụ này **không có enclosing Outer instance tự động**. Dù được khai báo trong source Outer, lexical nesting không làm static nested object gắn với một Outer object cụ thể.

Vì vậy `Outer.this` **không hợp lệ** từ static nested class nếu không có một lexical enclosing Outer instance trong context ấy.

### Cách sửa: truyền Outer instance tường minh

Tạo **`StaticNestedExplicitOwnerDemo.java`**:

```java
class Outer {
    private final int value;

    Outer(int value) {
        this.value = value;
    }

    static class Nested {
        private final Outer owner;

        Nested(Outer owner) {
            this.owner = owner;
        }

        int readValue() {
            return owner.value;
        }
    }
}

public class StaticNestedExplicitOwnerDemo {
    public static void main(String[] args) {
        Outer owner = new Outer(10);
        Outer.Nested nested = new Outer.Nested(owner);

        System.out.println(nested.readValue());
    }
}
```

```bash
javac StaticNestedExplicitOwnerDemo.java
java StaticNestedExplicitOwnerDemo
```

```text
10
```

`owner.value` được phép trong mã nested class vì quy tắc truy cập private members giữa nested/enclosing classes; nhưng **reference owner được truyền vào**, không đến từ `Outer.this`.

**Không nhầm:** `Outer.Nested` vẫn là *nested class*, nhưng không phải *inner class* theo nghĩa non-static member inner class.

## 13. `Outer.this` cũng không dùng được trong static method của Outer

Static method không có implicit receiver `this`.

```java
class Outer {
    private int value = 10;

    static void wrong() {
        // System.out.println(this.value);       // Không hợp lệ.
        // System.out.println(Outer.this.value); // Không hợp lệ.
    }
}
```

Nếu static method cần một Outer object, hãy nhận hoặc tạo reference tường minh:

```java
static int read(Outer candidate) {
    return candidate.value;
}
```

Đây là mảnh method minh họa đặt trong Outer. Một static method biết **type** Outer, nhưng không biết **instance nào** nên được chọn làm enclosing instance.

### Quy tắc hỏi nhanh

“Trong đoạn mã hiện tại có một implicit/lexically enclosing **Outer instance** hợp lệ không?” Nếu **không**, `Outer.this` không giúp tạo ra instance ấy.

Trong static nested class, dù có biến `Outer owner`, `owner.value` hợp lệ còn `Outer.this.value` không trở nên hợp lệ chỉ vì biến owner tồn tại.

## 14. Local class bên trong instance method có thể dùng enclosing instance

Nested classes không chỉ gồm member classes. Một **local class** cũng có thể được khai báo trong block của method.

Tạo **`LocalClassOuterThisDemo.java`**:

```java
class Outer {
    private final String label;

    Outer(String label) {
        this.label = label;
    }

    void execute() {
        class LocalTask {
            private final String label = "LOCAL";

            void run(String label) {
                System.out.println("argument=" + label);
                System.out.println("local class=" + this.label);
                System.out.println("outer=" + Outer.this.label);
            }
        }

        new LocalTask().run("PARAM");
    }
}

public class LocalClassOuterThisDemo {
    public static void main(String[] args) {
        new Outer("OWNER").execute();
    }
}
```

```bash
javac LocalClassOuterThisDemo.java
java LocalClassOuterThisDemo
```

```text
argument=PARAM
local class=LOCAL
outer=OWNER
```

`LocalTask` được khai báo bên trong **instance method** của Outer. Khi thực thi, nó có enclosing Outer context, nên `Outer.this.label` được phép.

**Ngược lại:** Local class được khai báo trong **static method** của Outer không tự có Outer enclosing instance. Khi cần một Outer cụ thể, truyền reference qua constructor/parameter như với static nested class.

## 15. Local variable và captured variable không phải Outer field

Local class và lambda có thể tham chiếu local variables từ enclosing method nếu chúng **final hoặc effectively final** theo rules của Java.

Ví dụ minh họa:

```java
void perform() {
    String prefix = "HELLO";

    class Task {
        void run() {
            System.out.println(prefix);
        }
    }

    new Task().run();
}
```

Đây là **mảnh instance method** đặt trong class hợp lệ.

`prefix` là **local variable captured từ method**, không phải field `Outer.this.prefix`. Nếu Outer không có field prefix thì `Outer.this.prefix` hoàn toàn không liên quan.

Sửa lại biến local `prefix` sau khi tạo Task (trong vùng code còn ảnh hưởng điều kiện capture) có thể làm mất trạng thái effectively final và khiến chương trình không biên dịch.

**Phân biệt phạm vi:**

- Local/parameter captured variable → tên biến trực tiếp, tuân thủ effectively-final.
- Inner field → `this.field`.
- Outer field → `Outer.this.field`.
- Static field → `Outer.field`.

`Outer.this` không dùng để bypass quy tắc effectively-final của captured local variables.

## 16. Anonymous class: `this` là anonymous object, `Outer.this` là Outer

Anonymous class tạo một class không có tên source-level riêng và một object từ class đó. Trong thân anonymous class, `this` trỏ tới chính anonymous object.

Tạo **`AnonymousClassOuterThisDemo.java`**:

```java
class Outer {
    private final String name;

    Outer(String name) {
        this.name = name;
    }

    Runnable task() {
        return new Runnable() {
            private final String name = "ANONYMOUS";

            @Override
            public void run() {
                System.out.println("this=" + this.name);
                System.out.println("outer=" + Outer.this.name);
                System.out.println("anonymous=" +
                        this.getClass().isAnonymousClass());
            }
        };
    }
}

public class AnonymousClassOuterThisDemo {
    public static void main(String[] args) {
        Runnable task = new Outer("OWNER").task();
        task.run();
    }
}
```

```bash
javac AnonymousClassOuterThisDemo.java
java AnonymousClassOuterThisDemo
```

```text
this=ANONYMOUS
outer=OWNER
anonymous=true
```

- `this` bên trong `run` là anonymous Runnable object.
- `Outer.this` là Outer instance nơi anonymous class được tạo.
- `getClass().isAnonymousClass()` kiểm runtime class là anonymous.
- Hai objects khác nhau dù code nested về mặt source.

**Lưu ý:** Anonymous class khai báo trong static context không tự gắn với Outer instance; ví dụ này chạy trong **Outer.task() instance method**.

## 17. Lambda khác anonymous class về ngữ nghĩa `this`

Lambda **không tạo một `this` receiver mới có thể tham chiếu bằng từ khóa `this`** trong thân lambda. `this` trong lambda có nghĩa như tại **lexical context** bao quanh nó.

Tạo **`LambdaThisDemo.java`**:

```java
class Outer {
    private final String name = "OUTER";

    Runnable createTask() {
        return () -> {
            System.out.println("this=" + this.name);
            System.out.println("qualified=" + Outer.this.name);
        };
    }
}

public class LambdaThisDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        Runnable task = outer.createTask();

        task.run();
    }
}
```

```bash
javac LambdaThisDemo.java
java LambdaThisDemo
```

```text
this=OUTER
qualified=OUTER
```

Trong `Outer.createTask()`, enclosing lexical `this` là Outer object. Lambda sử dụng cùng `this`, không đổi sang một anonymous implementation object's `this` như anonymous class.

### Lambda khai báo bên trong Inner

Nếu lambda được viết trong **instance method của Inner**, `this` trong lambda là Inner instance; `Outer.this` vẫn chỉ Outer instance nếu lexically enclosing Outer context hợp lệ.

**Tóm tắt:** Không được suy từ việc lambda được gán cho biến kiểu `Runnable` rằng `this` trong lambda là Runnable object. Với anonymous class, `this` chỉ anonymous object; với lambda, nó theo lexical context.

## 18. Ví dụ tổng hợp lambda bên trong Inner và hai field cùng tên

Tạo **`InnerLambdaShadowDemo.java`**:

```java
class Outer {
    private final String value = "OUTER";

    class Inner {
        private final String value = "INNER";

        Runnable task() {
            return () -> {
                System.out.println("inner=" + this.value);
                System.out.println("outer=" +
                        Outer.this.value);
            };
        }
    }
}

public class InnerLambdaShadowDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        Outer.Inner inner = outer.new Inner();

        inner.task().run();
    }
}
```

```bash
javac InnerLambdaShadowDemo.java
java InnerLambdaShadowDemo
```

```text
inner=INNER
outer=OUTER
```

`this` trong lambda được khai báo bởi `Inner.task()` là Inner receiver; `Outer.this` vẫn là Outer receiver. Vì hai lớp đều khai báo field `value`, qualification làm rõ nguồn dữ liệu.

Nếu thay lambda bằng anonymous Runnable, `this` bên trong `run()` sẽ là anonymous object, nên muốn nói Inner bạn có thể dùng **`Inner.this.value`** từ anonymous class đó; `Outer.this.value` vẫn trỏ Outer.

## 19. Anonymous class nằm bên trong Inner: ba receiver riêng

Tạo **`AnonymousInsideInnerDemo.java`**:

```java
class Outer {
    private final String label = "OUTER";

    class Inner {
        private final String label = "INNER";

        Runnable create() {
            return new Runnable() {
                private final String label = "ANONYMOUS";

                @Override
                public void run() {
                    System.out.println(this.label);
                    System.out.println(Inner.this.label);
                    System.out.println(Outer.this.label);
                }
            };
        }
    }
}

public class AnonymousInsideInnerDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        Outer.Inner inner = outer.new Inner();
        inner.create().run();
    }
}
```

```bash
javac AnonymousInsideInnerDemo.java
java AnonymousInsideInnerDemo
```

```text
ANONYMOUS
INNER
OUTER
```

Receiver trong method `run()`:

| Expression | Object |
| --- | --- |
| `this` | Anonymous Runnable instance |
| `Inner.this` | Enclosing Inner instance |
| `Outer.this` | Enclosing Outer instance |

Đây là pattern hữu ích khi callback cần dùng trạng thái của component bao ngoài nhưng cũng có state riêng bên trong callback.

## 20. Field kế thừa, inner field và outer field: đừng nhầm `super` với `Outer.this`

`super.field` liên quan đến **kế thừa**, còn `Outer.this.field` liên quan đến **enclosing instance**.

Tạo **`InheritanceVersusEnclosingDemo.java`**:

```java
class Base {
    protected String tag = "BASE";
}

class Outer {
    private final String tag = "OUTER";

    class Inner extends Base {
        private final String tag = "INNER";

        void show() {
            System.out.println("this=" + this.tag);
            System.out.println("super=" + super.tag);
            System.out.println("outer=" + Outer.this.tag);
        }
    }
}

public class InheritanceVersusEnclosingDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        outer.new Inner().show();
    }
}
```

```bash
javac InheritanceVersusEnclosingDemo.java
java InheritanceVersusEnclosingDemo
```

```text
this=INNER
super=BASE
outer=OUTER
```

- `this.tag`: Inner field.
- `super.tag`: field thuộc superclass Base, được tham chiếu qua inheritance.
- `Outer.this.tag`: field thuộc **Outer instance bao ngoài**, không phải superclass của Inner.

**Quan hệ cây cú pháp không phải cây kế thừa:** Inner được khai báo bên trong Outer **không có nghĩa Inner extends Outer**. Trong ví dụ, Inner extends Base; Outer là enclosing class.

## 21. `Outer.this.method()` khi Inner cũng có method cùng tên

Che khuất không chỉ làm xuất hiện ở fields; khi Inner và Outer có methods cùng tên, cần hiểu receiver nào gọi method.

Tạo **`MethodReceiverDemo.java`**:

```java
class Outer {
    String label() {
        return "OUTER";
    }

    class Inner {
        String label() {
            return "INNER";
        }

        void show() {
            System.out.println(label());
            System.out.println(this.label());
            System.out.println(Outer.this.label());
        }
    }
}

public class MethodReceiverDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        outer.new Inner().show();
    }
}
```

```bash
javac MethodReceiverDemo.java
java MethodReceiverDemo
```

```text
INNER
INNER
OUTER
```

`label()` không định danh trong method Inner chọn method phù hợp ở Inner. `this.label()` nói rõ receiver Inner. `Outer.this.label()` buộc lời gọi instance method trên enclosing Outer object.

**Cần thận trọng về thuật ngữ:** Hiding/shadowing của fields và **method lookup/overloading/overriding** có các quy tắc riêng. Ví dụ này minh họa cách **chọn receiver một cách tường minh**, không khẳng định mọi method cùng tên bị “shadow” giống field trong mọi overload/signature.

## 22. Sửa nhầm receiver có thể tạo lỗi rất khó nhận diện

Giả sử Inner là một editor điều khiển Outer model:

```java
class Document {
    private String title = "Untitled";

    class Editor {
        private String title = "Editor panel";

        void renameDocument(String title) {
            OuterLogic:
            {
                // Không cần label trong code thật;
                // chọn đúng receiver mới là trọng tâm.
                Document.this.title = title;
            }
        }

        String panelTitle() {
            return this.title;
        }
    }
}
```

Đây là **khai báo hợp lệ nhưng chỉ minh họa**, không có `main`. Label `OuterLogic` không mang tác dụng gì với name lookup; cách viết đơn giản hơn và nên dùng là:

```java
void renameDocument(String title) {
    Document.this.title = title;
}
```

Trong method `renameDocument`:

- `title`: parameter chứa tên mới.
- `this.title`: field của Editor panel.
- `Document.this.title`: field của Document model.

Nếu vô tình viết `this.title = title`, code có thể compile nhưng lại **đổi tiêu đề của panel thay vì tài liệu**. Vì vậy qualified this vừa giải quyết compiler ambiguity vừa có ý nghĩa **đúng đối tượng nghiệp vụ**.

## 23. Runnable ví dụ sửa đúng Outer mà không sửa Inner

Tạo **`EditorOuterThisDemo.java`**:

```java
class Document {
    private String title = "Untitled";

    String title() {
        return title;
    }

    class Editor {
        private String title = "Editor panel";

        void renameDocument(String title) {
            Document.this.title = title;
        }

        String panelTitle() {
            return this.title;
        }
    }
}

public class EditorOuterThisDemo {
    public static void main(String[] args) {
        Document doc = new Document();
        Document.Editor editor = doc.new Editor();

        editor.renameDocument("Java Guide");

        System.out.println("document=" + doc.title());
        System.out.println("panel=" + editor.panelTitle());
    }
}
```

```bash
javac EditorOuterThisDemo.java
java EditorOuterThisDemo
```

```text
document=Java Guide
panel=Editor panel
```

Ở đây cả parameter và Inner field và Outer field đều tên `title`. `Document.this.title` là expression cần thiết để chắc chắn thay state của Document owner.

**Không nhầm:** `Document.title` không phải cú pháp đúng để truy cập instance field (không static) từ chỗ này; `Document.this.title` dùng chính enclosing Document instance.

## 24. `Outer.this` và method reference

`Outer.this` có thể làm receiver của method reference khi functional interface phù hợp.

Tạo **`OuterMethodReferenceDemo.java`**:

```java
class Outer {
    private final String label;

    Outer(String label) {
        this.label = label;
    }

    String getLabel() {
        return label;
    }

    class Inner {
        java.util.function.Supplier<String> supplier() {
            return Outer.this::getLabel;
        }
    }
}

public class OuterMethodReferenceDemo {
    public static void main(String[] args) {
        Outer outer = new Outer("OWNER");
        Outer.Inner inner = outer.new Inner();

        java.util.function.Supplier<String> supplier =
                inner.supplier();

        System.out.println(supplier.get());
    }
}
```

```bash
javac OuterMethodReferenceDemo.java
java OuterMethodReferenceDemo
```

```text
OWNER
```

`Outer.this::getLabel` gắn receiver Outer đang bao ngoài. Khi `supplier.get()` được gọi, nó gọi `getLabel()` trên Outer ấy.

Nếu bạn thay thành `this::getLabel` trong Inner nhưng Inner không có method phù hợp, compiler sẽ không tìm được instance method của Inner tương ứng. Cách chọn receiver trong method reference cũng phải rõ như method invocation bình thường.

## 25. `Outer.this` không phải cú pháp để tạo inner class

Cú pháp tạo non-static member inner class từ bên ngoài:

```java
Outer outer = new Outer();
Outer.Inner inner = outer.new Inner();
```

Còn:

```java
Outer.this
```

là một **expression trỏ tới enclosing instance trong lexical context hợp lệ**.

Ở trong Outer instance method, ta có thể dùng:

```java
Inner inner = new Inner();
```

vì enclosing instance hiện tại là receiver Outer của method.

**Không viết trong static main của class độc lập:**

```java
// Outer.Inner x = Outer.this.new Inner(); // Không có Outer.this ở đây.
```

Bạn cần một Outer object cụ thể, như biến `outer`, để gọi `outer.new Inner()`. Đừng nhầm dấu chấm của `outer.new Inner()` với qualified-this expression.

## 26. Có thể dùng `Outer.this` trong Inner constructor không?

Có: constructor body của member inner class chạy trong ngữ cảnh Inner instance có enclosing Outer instance.

Tạo **`InnerConstructorOuterThisDemo.java`**:

```java
class Outer {
    private final String id;

    Outer(String id) {
        this.id = id;
    }

    class Inner {
        private final String ownerId;

        Inner() {
            this.ownerId = Outer.this.id;
        }

        String ownerId() {
            return ownerId;
        }
    }
}

public class InnerConstructorOuterThisDemo {
    public static void main(String[] args) {
        Outer outer = new Outer("OUT-1");
        Outer.Inner inner = outer.new Inner();

        System.out.println(inner.ownerId());
    }
}
```

```bash
javac InnerConstructorOuterThisDemo.java
java InnerConstructorOuterThisDemo
```

```text
OUT-1
```

Constructor Inner đọc Outer field để gán một final field riêng. Đây là **snapshot String reference/value**. Nếu Outer field về sau thay đổi (khi không final) thì Inner.ownerId đã gán trước đó không tự đổi.

**Cảnh báo về lifecycle:** Đừng để `this`/enclosing owner leak từ constructor hoặc gọi overridable methods trên owner trước khi owner hoàn tất construction. Đặc biệt nguy hiểm nếu Outer constructor tự tạo Inner rồi gọi callbacks có thể quan sát Outer state còn dở dang.

## 27. Qualified this với generic Outer

Class bao ngoài có thể là generic class:

```java
class Container<T> {
    private final T item;

    Container(T item) {
        this.item = item;
    }

    class View {
        T get() {
            return Container.this.item;
        }
    }
}
```

`Container.this` được định danh theo **tên class**, không phải một type argument expression như `Container<String>.this`.

### Ví dụ chạy

Tệp **`GenericOuterThisDemo.java`**:

```java
class Container<T> {
    private final T value;

    Container(T value) {
        this.value = value;
    }

    class View {
        T get() {
            return Container.this.value;
        }
    }
}

public class GenericOuterThisDemo {
    public static void main(String[] args) {
        Container<String> container =
                new Container<>("Java");

        Container<String>.View view =
                container.new View();

        System.out.println(view.get());
    }
}
```

```bash
javac GenericOuterThisDemo.java
java GenericOuterThisDemo
```

```text
Java
```

`View.get()` trả `T` từ enclosing `Container<T>` instance. Type parameter `T` là type-level generic relationship; `Container.this` là object reference-level relationship. Không nhầm hai cơ chế.

## 28. Chỉ có lexical enclosing instance đúng kiểu mới dùng được `TypeName.this`

Một biến kiểu Outer **không** làm expression `Outer.this` hợp lệ nếu phạm vi không có enclosing instance.

Ví dụ:

```java
class Outer {
    int value = 10;

    static class Helper {
        private final Outer explicit;

        Helper(Outer explicit) {
            this.explicit = explicit;
        }

        int read() {
            return explicit.value;    // Hợp lệ.
            // return Outer.this.value; // Không hợp lệ.
        }
    }
}
```

Tương tự, object `Foreign` không thể viết `Outer.this` chỉ vì nó có field `Outer owner`. Nó phải dùng `owner` làm receiver.

**Một quy tắc nhận diện:** Đọc đường **lexically enclosing classes và static/non-static contexts** của vị trí code. Đừng chỉ nhìn toàn file có tên Outer hoặc có một reference tới Outer.

### Phân biệt với việc truyền `this` làm đối số

Một inner method có thể viết `use(Outer.this)` khi muốn truyền enclosing Outer object cho collaborator. Nhưng ở static nested class, bạn phải có biến `owner` và viết `use(owner)`.

## 29. Khi nào `Outer.this` không phải lựa chọn thiết kế tốt nhất?

Inner classes có khả năng truy cập instance bên ngoài rất tiện nhưng cũng tạo **coupling**:

- Inner có thể mutate private state của Outer theo đường ẩn.
- Inner instance có thể giữ Outer instance sống lâu hơn mong muốn nếu được lưu lâu dài.
- Callback lưu inner class instance có thể kéo dài vòng đời owner.
- Logic nhiều tầng `Outer.this / Middle.this` có thể khó bảo trì.
- Unit test một Inner instance có thể phải tạo Outer object và đủ state.

Nếu helper chỉ cần một vài giá trị, cân nhắc **static nested class nhận dữ liệu tường minh**, hoặc top-level class và dependency injection.

**Không có quy tắc “tránh mọi inner class”.** Chọn member inner class nếu logic thực sự thuộc từng Outer instance và quyền truy cập Outer state là cần thiết, rõ ràng. Nếu không, dùng một class có dependencies tường minh để giảm coupling.

## 30. Thiết kế lại thành static nested helper khi không cần enclosing instance

Tạo **`StaticHelperAlternativeDemo.java`**:

```java
class Report {
    private final String title;

    Report(String title) {
        this.title = title;
    }

    static class Formatter {
        private final String prefix;

        Formatter(String prefix) {
            this.prefix = prefix;
        }

        String format(Report report) {
            return prefix + report.title;
        }
    }
}

public class StaticHelperAlternativeDemo {
    public static void main(String[] args) {
        Report report = new Report("Java");
        Report.Formatter formatter =
                new Report.Formatter("Report:");

        System.out.println(formatter.format(report));
    }
}
```

```bash
javac StaticHelperAlternativeDemo.java
java StaticHelperAlternativeDemo
```

```text
Report:Java
```

`Formatter` không tự gắn với một Report instance. `format(report)` nhận owner một cách tường minh; quan hệ phụ thuộc thể hiện ở method signature. Nó vẫn truy cập được private field của Report theo nested-class access rules nhưng không có `Report.this`.

**So sánh:**

| Thiết kế | Owner instance đến từ đâu? |
| --- | --- |
| `class Inner` non-static | Enclosing instance khi Inner được tạo |
| `static class Helper` | Tham số, constructor field hoặc lookup tường minh |
| Local class trong instance method | Lexically enclosing instance hợp lệ |
| Anonymous class trong instance method | Enclosing instance hợp lệ |
| Lambda trong instance method | Lexical `this` của ngữ cảnh hiện tại |

## 31. Bài thực hành: dự đoán chính xác tên nào được chọn

Tạo **`ShadowingTraceDemo.java`**:

```java
class Outer {
    private String value = "O";

    class Middle {
        private String value = "M";

        class Inner {
            private String value = "I";

            void update(String value) {
                value = value + "1";
                this.value = this.value + "2";
                Middle.this.value =
                        Middle.this.value + "3";
                Outer.this.value =
                        Outer.this.value + "4";

                System.out.println(value);
                System.out.println(this.value);
                System.out.println(Middle.this.value);
                System.out.println(Outer.this.value);
            }
        }
    }
}

public class ShadowingTraceDemo {
    public static void main(String[] args) {
        Outer outer = new Outer();
        Outer.Middle middle = outer.new Middle();
        Outer.Middle.Inner inner = middle.new Inner();

        inner.update("P");
    }
}
```

```bash
javac ShadowingTraceDemo.java
java ShadowingTraceDemo
```

```text
P1
I2
M3
O4
```

**Lời giải theo từng phép gán:**

1. `value = value + "1"` dùng parameter `value` của method, kết quả P1.
2. `this.value = this.value + "2"` sửa field của Inner, I2.
3. `Middle.this.value = ...` sửa field của Middle, M3.
4. `Outer.this.value = ...` sửa field của Outer, O4.

Không có phép gán nào tự động sửa cả bốn. Đây là bốn storage locations khác nhau.

## 32. Một ví dụ lỗi thiết kế và bản sửa

Giả sử Outer lưu tổng số đơn hàng; Inner lưu số lần helper được sử dụng:

```java
class Store {
    private int orders;

    class Helper {
        private int orders;

        void registerOrder() {
            // orders++; // Sửa Helper.orders, KHÔNG phải Store.orders.
            Store.this.orders++;
        }
    }
}
```

Mảnh code không có `main` nhưng hợp lệ. Tên `orders` trong Helper che field Outer. Nếu viết `orders++`, compiler không báo lỗi vì Helper cũng có field hợp lệ, nhưng state **sai đối tượng** bị cập nhật.

**Cách bảo vệ bằng test:** Kiểm cả giá trị Outer và Inner sau call. Nếu business intent của `registerOrder` là tăng Store.orders, assert Store thay đổi mà Helper counter không bị tăng nhầm.

### Bài test runnable

Tệp **`ShadowingBugPreventionDemo.java`**:

```java
class Store {
    private int orders;

    int orders() {
        return orders;
    }

    class Helper {
        private int orders;

        void registerOrder() {
            Store.this.orders++;
        }

        int helperOrders() {
            return this.orders;
        }
    }
}

public class ShadowingBugPreventionDemo {
    public static void main(String[] args) {
        Store store = new Store();
        Store.Helper helper = store.new Helper();

        helper.registerOrder();
        helper.registerOrder();

        System.out.println("store=" + store.orders());
        System.out.println("helper=" + helper.helperOrders());
    }
}
```

```bash
javac ShadowingBugPreventionDemo.java
java ShadowingBugPreventionDemo
```

```text
store=2
helper=0
```

Code này không dựa vào warning của compiler. Test bảo đảm **đúng owner state** được sửa.

## 33. Những lỗi compile-time cần nhận diện

| Mảnh code / ý định | Có hợp lệ? | Lý do |
| --- | --- | --- |
| `this.x` trong Inner instance method | Có, nếu member lookup hợp lệ | Truy cập receiver Inner |
| `Outer.this.x` trong Inner instance method | Có, nếu có enclosing Outer instance và member hợp lệ | Truy cập Outer receiver |
| `Outer.x` với x là instance field | Không phải cách truy cập instance field thông thường | Cần object reference |
| `Outer.staticX` với static field | Có nếu access hợp lệ | Không dùng Outer instance |
| `Outer.this = other` | Không | Qualified this không phải biến có thể gán |
| `Outer.this` trong static nested class không có enclosing instance Outer | Không | Không có implicit enclosing Outer instance |
| `Outer.this` trong static method của Outer | Không | Không có receiver instance |
| `Outer.this` trong local class của Outer instance method | Có trong lexical context phù hợp | Gắn enclosing Outer instance |
| `Outer.this` trong local class của static method mà không có enclosing Outer instance | Không | Chỉ lexical nesting của source không tạo Outer instance |
| `Outer.this` trong anonymous class tạo ở Outer instance context | Có | Anonymous object gắn lexical Outer context |
| `this` trong lambda ở Outer instance method | Có | Dùng lexical receiver Outer |
| `Inner.this` trong anonymous class tạo từ Inner instance context | Có | Nhắm tới Inner enclosing instance |
| `Outer.this.someMethod()` | Có nếu method hợp lệ | Gọi trên Outer receiver |
| `Outer.this::someMethod` | Có nếu method reference tương thích | Bound instance method reference |
| `new Outer().new Inner()` | Có với constructors/access hợp lệ | Tạo Inner gắn Outer object mới |

**Không sao chép nguyên các dòng “Không” vào source runnable.** Chúng là ví dụ lỗi cú pháp/ngữ nghĩa để học.

## 34. Phân biệt `Outer.this` với những cú pháp gần giống

- `this.field`: receiver của current instance method/constructor.
- `Outer.this.field`: receiver enclosing Outer instance, khi hợp lệ.
- `super.field`: field ở superclass của current receiver, theo access rules.
- `Outer.super.method()`: một dạng **qualified-super invocation** trong ngữ cảnh thích hợp, có ngữ nghĩa gọi method ở superclass của enclosing instance; không đồng nghĩa `Outer.this`. Chỉ dùng khi hiểu đúng inheritance/access rules.
- `Outer.class`: object mô tả kiểu Outer, không phải Outer instance.
- `Outer.STATIC_FIELD`: static member access.
- `outer.field`: truy cập field trên biến reference tên `outer`, có thể trỏ một object khác với `Outer.this`.
- `outer.new Inner()`: tạo inner instance gắn outer object được chỉ định.
- `Outer.Inner`: tên kiểu nested class dùng trong declarations/types.

**Điểm phân biệt:** `Outer.this` yêu cầu mối liên hệ **lexical enclosing instance** tại vị trí code; biến `outer` là một reference thông thường được truyền hoặc gán và có thể trỏ bất cứ Outer object tương thích nào.

## 35. Checklist rà soát khi gặp che khuất tên

- [ ] Tôi đã xác định đúng class/method/block chứa expression?
- [ ] Tên đơn giản có bị tham số hoặc biến cục bộ che khuất?
- [ ] Inner có field trùng tên Outer field không?
- [ ] Có nhiều tầng Outer/Middle/Inner cùng khai báo member trùng tên?
- [ ] `this.field` đang nhắm Inner hay một anonymous object?
- [ ] Có cần `Outer.this.field` để chọn đúng Outer owner không?
- [ ] Nếu có Middle, đã dùng đúng `Middle.this` khi cần?
- [ ] Tôi phân biệt `super.member` (kế thừa) với `Outer.this.member` (enclosing instance)?
- [ ] Receiver của `method()` có rõ ràng khi nhiều classes có method cùng tên?
- [ ] Class hiện tại là non-static inner hay static nested class?
- [ ] Nếu ở static method/static nested context, đã tránh `Outer.this` khi không có enclosing Outer instance?
- [ ] Nếu cần Outer từ static nested helper, đã truyền owner reference tường minh?
- [ ] Nếu ở local/anonymous class, đã xác định enclosing instance và effectively-final local variables?
- [ ] Nếu là lambda, đã biết `this` theo lexical context chứ không phải lambda object?
- [ ] Tôi không gán lại `Outer.this` vì nó không phải assignable variable?
- [ ] Tôi không nhầm `Outer.class` với Outer object?
- [ ] Tôi không nhầm `outer.new Inner()` với `Outer.this`?
- [ ] Nếu có hai Outer instances, Inner có chắc đang gắn đúng owner không?
- [ ] Tôi dùng `==` khi kiểm **identity** của enclosing object?
- [ ] Có private fields không? Tôi đã hiểu nested access rules?
- [ ] Inner có giữ Outer sống lâu hơn dự kiến trong callbacks/collections không?
- [ ] Có nên đổi sang static nested helper để giảm coupling nếu không cần owner tự động?
- [ ] Tôi đã test đúng state của cả Inner và Outer sau mutation?
- [ ] Các ví dụ Java 17+ có đúng tên tệp/public class, lệnh `javac`/`java` và stdout?

## 36. Câu hỏi tự luyện và đáp án

**Câu 1.** Outer và Inner đều có field `name`; trong method Inner có parameter `name`. `name`, `this.name`, `Outer.this.name` khác nhau thế nào?

*Đáp án:* Lần lượt là parameter, field Inner, field Outer của enclosing instance.

**Câu 2.** `Outer.this` là kiểu/class metadata hay object reference?

*Đáp án:* Là expression trỏ enclosing Outer instance; metadata là `Outer.class`.

**Câu 3.** Trong static nested class, có thể dùng `Outer.this` để lấy một Outer object tự động không?

*Đáp án:* Không. Static nested class không có implicit Outer enclosing instance. Truyền Owner reference tường minh.

**Câu 4.** Trong static method Outer, có `this` không?

*Đáp án:* Không có implicit instance receiver. Do đó `Outer.this` cũng không hợp lệ trong static context ấy.

**Câu 5.** `Outer.Inner inner = outer.new Inner();` khiến `Outer.this` trong inner trỏ tới đâu?

*Đáp án:* Trỏ chính object được tham chiếu bởi `outer` tại lúc inner được tạo.

**Câu 6.** Hai Inner objects tạo từ hai Outer khác nhau có share Outer state không?

*Đáp án:* Không tự động. Mỗi Inner gắn với enclosing Outer instance của mình; static state có thể vẫn shared theo static rules.

**Câu 7.** Với Outer→Middle→Inner, làm sao đọc Middle field trùng tên Inner field?

*Đáp án:* `Middle.this.field`.

**Câu 8.** Có thể viết `Outer.this = anotherOuter` để đổi owner không?

*Đáp án:* Không. Qualified this không phải biến được gán.

**Câu 9.** `super.name` và `Outer.this.name` có phải cùng một field không?

*Đáp án:* Không tất yếu; `super` liên quan superclass của receiver hiện tại, `Outer.this` liên quan enclosing Outer object.

**Câu 10.** Vì sao private Outer field vẫn có thể được Inner truy cập?

*Đáp án:* Nested class access rules cho phép truy cập private members giữa classes trong nest phù hợp.

**Câu 11.** Trong anonymous class khai báo trong Outer instance method, `this` trỏ tới đâu?

*Đáp án:* Anonymous instance. `Outer.this` trỏ Outer enclosing instance.

**Câu 12.** Trong lambda ở Outer instance method, `this` trỏ đâu?

*Đáp án:* Lexical receiver Outer; lambda không tạo một `this` mới trong thân.

**Câu 13.** Trong lambda tạo từ Inner instance method, `this` trỏ đâu?

*Đáp án:* Inner instance của lexical context; `Outer.this` vẫn là Outer enclosing instance.

**Câu 14.** `Outer.this.method()` khác `this.method()` thế nào?

*Đáp án:* Đầu tiên gọi trên enclosing Outer receiver; thứ hai gọi trên receiver hiện tại.

**Câu 15.** Nếu Inner field và Outer field cùng tên, sửa `this.count++` có làm Outer.count tăng không?

*Đáp án:* Không, nếu đây là hai instance fields riêng. Phải dùng `Outer.this.count++` để sửa Outer.

**Câu 16.** Local class khai báo trong instance method Outer có thể dùng `Outer.this` không?

*Đáp án:* Có trong lexical context có enclosing Outer instance hợp lệ.

**Câu 17.** Local class khai báo trong static method Outer có tự có Outer instance không?

*Đáp án:* Không. Một Outer variable tồn tại không tự biến nó thành enclosing instance; dùng reference tường minh.

**Câu 18.** Nếu có hai Outer objects equal về giá trị, `Outer.this == other` có thể false không?

*Đáp án:* Có. `==` kiểm identity; equality theo value không làm hai objects thành một instance.

**Câu 19.** `Outer.this` có phù hợp để gọi static method không?

*Đáp án:* Với static method, nên gọi qua tên lớp `Outer.staticMethod()`; không cần enclosing instance.

**Câu 20.** Inner instance giữ liên kết Outer lâu dài có ảnh hưởng thiết kế gì?

*Đáp án:* Có thể tăng coupling và kéo dài vòng đời Outer khi Inner được giữ sống; cân nhắc static nested helper/explicit dependencies nếu không cần implicit owner.

---

**Ghi nhớ cuối bài:** Khi một tên xuất hiện ở nhiều cấp, đừng đoán compiler đang chọn biến nào. **`name`** chọn khai báo gần nhất theo phạm vi, **`this.name`** dùng receiver hiện tại, còn **`Outer.this.name`** dùng **đúng enclosing Outer instance** trong ngữ cảnh inner class hợp lệ. Với nhiều tầng, `Middle.this` và `Outer.this` phân biệt các owners; với anonymous class, `this` trỏ anonymous object; với lambda, `this` theo lexical context. **Static nested class và static method không tự có Outer instance**, nên không dùng `Outer.this` để lấy một owner tùy ý. Viết rõ receiver khi có shadowing sẽ tránh cập nhật nhầm state, giúp code dễ đọc và test đúng hành vi.