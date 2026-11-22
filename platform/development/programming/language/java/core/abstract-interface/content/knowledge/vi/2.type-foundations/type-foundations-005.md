# Phân biệt `extends` và `implements` trong Java

`extends` dùng để kế thừa một class hoặc mở rộng một interface. `implements` dùng trong khai báo class để công bố rằng class đáp ứng hợp đồng của một hay nhiều interface. Điểm cần nhớ là **interface cũng dùng `extends`**; `implements` không phải từ khóa cho interface kế thừa interface.

## 1. Đọc khai báo trước khi đọc code

| Khai báo | Ý nghĩa | Giới hạn chính |
|---|---|---|
| `class Child extends Parent` | Kế thừa một class. | Một class chỉ có một superclass trực tiếp; `Parent` không được `final`. |
| `abstract class Child extends Parent` | Abstract class kế thừa class. | Vẫn chỉ có một superclass trực tiếp. |
| `interface B extends A` | Interface B kế thừa hợp đồng A. | A phải là interface. |
| `interface C extends A, B` | Interface C kết hợp nhiều hợp đồng. | Các khai báo kế thừa phải tương thích. |
| `class Child implements A, B` | Class đáp ứng các interface A và B. | A và B phải là interface; class cụ thể phải đáp ứng các abstract method còn thiếu. |
| `class Child extends Parent implements A, B` | Kết hợp kế thừa class và thực hiện nhiều interface. | `extends` phải đứng trước `implements`. |

Ví dụ khai báo:

```java
class Child extends Base implements Readable, Writable {
    // Cần đáp ứng các abstract method còn thiếu.
}

interface AdvancedReadable extends Readable, AutoCloseable {
    // Kế thừa hợp đồng của cả hai interface.
}
```

Không có cú pháp `class Child extends Base1, Base2`. Một interface có thể `extends` nhiều interface, nhưng không thể `extends` class. Một class không khai báo `extends` sẽ mặc nhiên kế thừa trực tiếp `Object` (ngoại trừ chính `Object`).

## 2. `extends` giữa hai class

Với `class Dog extends Animal`, `Dog` là subtype của `Animal` và có thể dùng các thành viên được kế thừa theo quy tắc Java.

- Concrete method phù hợp có thể được dùng lại hoặc override.
- Field instance thuộc state của object; field `private` của superclass không thể được subclass truy cập trực tiếp.
- Constructor **không được kế thừa**. Constructor subclass gọi `super(...)` để khởi tạo phần superclass; nếu không có constructor cha không tham số phù hợp, phải gọi rõ constructor cần dùng.
- Class `final` không thể có subclass; method `final` không thể bị override. Method `static` cùng tên bị hide chứ không dispatch như method instance.
- Abstract class có thể chứa field, constructor, concrete method và abstract method. Concrete subclass phải cài đặt các abstract method còn thiếu.

Chỉ dùng `extends` khi quan hệ “là một” đúng cả về hành vi: code dùng `Animal` phải có thể làm việc với `Dog` mà không bị phá các cam kết của `Animal`. Nếu chỉ muốn mượn một helper, composition thường ít ràng buộc hơn.

## 3. `implements`: class đáp ứng hợp đồng interface

Interface công bố các khả năng mà caller có thể yêu cầu, chẳng hạn `Runnable`, `Comparable` hoặc hợp đồng nghiệp vụ `Payable`. Một object của class triển khai có thể được tham chiếu qua interface; interface không cung cấp constructor hoặc state instance.

- Method abstract thông thường của interface là `public abstract`; implementation phải là `public`, không được giảm quyền truy cập.
- `default` method có body và có thể được thừa hưởng nếu không bị override hoặc quy tắc xung đột thay thế.
- `static` method được gọi qua tên interface; nó không trở thành instance method của class triển khai.
- Từ Java 9, interface có thể khai báo `private` method để dùng nội bộ các implementation khác trong chính interface.
- Field trong interface mặc định là `public static final`, tức hằng dùng chung, không phải state riêng của object.

Abstract class có thể `implements` interface nhưng để lại một số abstract method cho subclass. Class cụ thể phải đáp ứng toàn bộ hợp đồng abstract còn thiếu, trực tiếp hoặc qua implementation public hợp lệ được kế thừa.

## 4. Ví dụ chạy được: vừa `extends` vừa `implements`

Lưu toàn bộ chương trình sau thành `Main.java`:

```java
interface Named {
    String name();
}

interface Payable extends Named {
    double monthlyPay();

    default String label() {
        return name() + " / " + monthlyPay();
    }
}

abstract class Worker {
    private final String workerName;

    protected Worker(String name) {
        this.workerName = name;
    }

    public String name() {
        return workerName;
    }

    public abstract String role();
}

final class Developer extends Worker implements Payable {
    private final double salary;

    Developer(String name, double salary) {
        super(name);
        this.salary = salary;
    }

    @Override
    public String role() {
        return "Developer";
    }

    @Override
    public double monthlyPay() {
        return salary;
    }
}

public class Main {
    public static void main(String[] args) {
        Developer developer = new Developer("Lan", 1200.0);

        Worker bySuperclass = developer;
        Payable byContract = developer;
        Named byParentInterface = developer;

        System.out.println(bySuperclass.role());
        System.out.println(byContract.label());
        System.out.println(byParentInterface.name());
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac Main.java
java Main
```

Stdout:

```text
Developer
Lan / 1200.0
Lan
```

Trong ví dụ, `Developer extends Worker` để nhận phần triển khai chung; `Developer implements Payable` để đáp ứng hợp đồng thanh toán; `Payable extends Named` nên `Developer` cũng là subtype của `Named`. `Worker.name()` là public và tương thích với `Named.name()`, vì vậy không cần viết lại method này trong `Developer`. Default method `Payable.label()` gọi `name()` trên object thực tế.

## 5. Interface `extends` interface

Một interface con có thể kết hợp hợp đồng từ nhiều interface:

```java
interface Identified {
    long id();
}

interface Described {
    String description();
}

interface CatalogItem extends Identified, Described {
    // Kế thừa cả id() và description().
}
```

Class cụ thể `implements CatalogItem` phải đáp ứng cả hai method, trừ khi đã kế thừa implementation tương thích từ superclass. Hai interface có cùng abstract method và signature/return type tương thích có thể dùng chung một implementation; chữ ký hoặc kiểu trả về không tương thích có thể khiến khai báo không hợp lệ.

## 6. Khi cú pháp đúng nhưng hợp đồng chưa đủ

Một class dùng đúng `extends` và `implements` vẫn có thể không biên dịch nếu thiếu method abstract, sai signature, giảm quyền truy cập hoặc gặp các default method xung đột. Trong ví dụ mục 4, `Worker.name()` là `public` nên đã đáp ứng `Named.name()` cho `Developer` mà không cần viết lại. Overload `name(String)` hoặc method package-private không thay thế được `public String name()`.

Khi compiler báo lỗi, hãy kiểm tra method còn thiếu, kiểu trả về, `throws` và mức truy cập; sau đó xét nguồn default implementation. Thứ tự viết `implements A, B` không giải quyết xung đột. Các trường hợp hai default method cạnh tranh, ưu tiên class và `InterfaceName.super.method()` đã có ví dụ chạy được trong bài **Đơn kế thừa lớp và đa kế thừa interface**.

## 7. Các khai báo sai thường gặp

Các dòng sau là ví dụ lỗi biên dịch; chúng được comment để không làm hỏng các khai báo hợp lệ xung quanh:

```java
class Animal {}
interface Flyable { void fly(); }

// class Bird extends Flyable {}       // Sai: class không extends interface.
// class Bird implements Animal {}     // Sai: implements phải nhận interface.
// interface FastFlyer implements Flyable {} // Sai: interface dùng extends.
// class Bird extends Animal, Object {} // Sai: chỉ một superclass trực tiếp.
// class Bird implements Flyable {}    // Sai nếu Bird concrete và chưa có fly().

abstract class AbstractBird implements Flyable {}

class Eagle extends AbstractBird {
    @Override
    public void fly() {
        System.out.println("Flying");
    }
}
```

Những điểm cần rà soát:

- `class X implements A extends B` sai thứ tự; nếu `B` là class và `A` là interface, viết `class X extends B implements A`.
- Implementation của method interface phải `public`.
- `implements` không tự cung cấp body cho abstract method.
- `private` field của superclass không thể được truy cập trực tiếp từ subclass.
- Hai default method trùng signature chỉ gây xung đột khi quy tắc kế thừa không chọn được một implementation hợp lệ.

## 8. Một cách dùng `extends` khác: generic bound

Trong khai báo type parameter, `extends` đặt **upper bound**, không phải quan hệ superclass của class bao ngoài:

```java
class NumberBox<T extends Number> {
    private final T value;

    NumberBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

`T extends Number` giới hạn kiểu đối số generic vào `Number` hoặc subtype phù hợp. Bound cũng có thể là interface, ví dụ `<T extends Comparable<T>>`; nếu có nhiều bound, dùng `&`, và class bound (nếu có) phải đứng đầu. `? extends Number` là upper-bounded wildcard, một cú pháp liên quan nhưng có vai trò khác.

Từ Java 17, `sealed` class/interface có thể giới hạn các subtype được phép qua `permits`. Điều này bổ sung ràng buộc về kiểu con, không thay đổi ý nghĩa của `extends` hay `implements`.

## 9. Tự kiểm tra

1. `interface B extends A` và `class C implements B`: C có đáp ứng A không? **Có**, các hợp đồng được kế thừa bắc cầu.
2. `class C extends Base implements X, Y` có hợp lệ không? **Có**, nếu Base có thể kế thừa, X/Y là interface và mọi abstract method/xung đột được xử lý.
3. `class C implements Runnable` đã đủ để chạy trên thread mới chưa? **Chưa**; class concrete phải đáp ứng `public void run()`, còn thực thi cần `Thread` hoặc executor phù hợp.
4. Hai interface có default method trùng nhau thì đổi thứ tự trong `implements` có giải quyết được không? **Không**; hãy áp dụng quy tắc kế thừa và override rõ ràng khi cần.

**Ghi nhớ:** `class Child extends Parent`, `class Child implements Contract`, `interface MoreSpecific extends Contract`. Với class dùng cả hai, thứ tự là `extends` rồi `implements`. Hãy chọn class inheritance cho quan hệ “là một” bền vững và interface cho hợp đồng có thể được nhiều loại class thực hiện.
