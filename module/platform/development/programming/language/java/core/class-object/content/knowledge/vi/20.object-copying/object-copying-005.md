# So sánh sao chép tường minh với `Object.clone()` trong Java

## 1. Mục tiêu và kết luận chính

Trong Java, **sao chép đối tượng (*object copying*)** là tạo ra một đối tượng mới từ thông tin của đối tượng đang có. Nhưng “tạo một object mới” chưa nói rõ **mức độ độc lập của trạng thái**: hai object có thể vẫn chia sẻ cùng mảng, danh sách hoặc thành phần mutable.

Hai cách thường gặp:

- **Sao chép tường minh (*explicit copying*)**: tự định nghĩa copy constructor, static copy factory hoặc method `copy()`; dùng `new` và chủ động chọn fields, validations, shallow/deep copy và contract kết quả.
- **`Object.clone()`**: cơ chế có sẵn trong `java.lang.Object`. Nếu runtime object hỗ trợ `Cloneable` theo hợp đồng, implementation cơ sở của `clone()` tạo một object mới bằng **sao chép các fields**, mặc định là **shallow copy**. Constructor không chạy theo lối tạo object bằng `new` thông thường.

Hai cách đều có thể tạo **object identity mới**; nhưng chúng khác nhau ở API, quyền truy cập, exception, constructor/invariant, kế thừa và cách xử lý mutable components.

> **Khuyến nghị cơ bản:** Với class do bạn tự thiết kế, đặc biệt có invariants, fields `final` hoặc mutable nested objects, **copy constructor/static factory tường minh thường dễ đọc, dễ kiểm tra và dễ duy trì hơn**. `clone()` vẫn cần hiểu và dùng đúng khi một API hoặc hierarchy đã quy định clone contract.

Bài này tập trung vào **so sánh sao chép tường minh với `Object.clone()`**, không đánh đồng copy với phép gán reference, serialization, conversion hay Java garbage collection.

## 2. Phép gán tham chiếu không phải sao chép object

Trước hết, xác định đúng thứ đang được sao chép.

```java
Box first = new Box(10);
Box alias = first;
```

`alias = first` chỉ sao chép **giá trị tham chiếu**. Không có `new`, không gọi constructor và không sinh một Box object thứ hai.

Sơ đồ:

```text
first ─────┐
           ├────> Box object X { value: 10 }
alias ─────┘
```

Nếu `alias` thay đổi mutable state của object X, `first` nhìn thấy thay đổi ấy.

Với phép copy tạo object mới:

```java
Box copy = new Box(first.value());
```

sơ đồ là:

```text
first ─────────> Box object X { value: 10 }
copy  ─────────> Box object Y { value: 10 }
```

`first == copy` false nếu có hai objects riêng; nhưng `first.value()==copy.value()` true.

**Phân biệt:** “cùng dữ liệu” không đồng nghĩa “cùng object”; “khác object” cũng **không bảo đảm mọi objects con đều khác nhau** nếu có shallow copy.

## 3. Ví dụ đầu tiên: tạo bản sao tường minh bằng constructor

Tạo tệp **`ExplicitCopyBasicsDemo.java`**:

```java
final class Box {
    private int value;

    Box(int value) {
        this.value = value;
    }

    Box(Box source) {
        this.value = source.value;
    }

    int value() {
        return value;
    }

    void change(int value) {
        this.value = value;
    }
}

public class ExplicitCopyBasicsDemo {
    public static void main(String[] args) {
        Box original = new Box(10);
        Box copy = new Box(original);

        System.out.println(original == copy);
        System.out.println(original.value() == copy.value());

        copy.change(20);

        System.out.println("original=" + original.value());
        System.out.println("copy=" + copy.value());
    }
}
```

Chạy bằng JDK 17+:

```bash
javac ExplicitCopyBasicsDemo.java
java ExplicitCopyBasicsDemo
```

**Standard output:**

```text
false
true
original=10
copy=20
```

Constructor `Box(Box source)` là **copy constructor**: nó nhận source object và dùng `new Box(original)` để tạo object mới.

Vì `value` là primitive `int`, phép gán field value vào field khác là đủ. Sau đó `copy.change(20)` không đổi `original.value`.

**Điểm đáng giá:** Body của copy constructor hiển thị rõ **đang sao chép field nào**, theo chiến lược nào. Với các fields mutable reference types, phải chủ động quyết định có chia sẻ hay copy sâu.

## 4. `Object.clone()` là gì?

Class gốc `java.lang.Object` định nghĩa một method với chữ ký khái niệm:

```java
protected native Object clone() throws CloneNotSupportedException;
```

Đây là **chữ ký API để học**, không phải class source độc lập.

Những đặc điểm quan trọng:

1. `clone()` trong Object có quyền truy cập **`protected`**, không phải public.
2. Method trả về `Object` theo declaration ở Object; class con có thể **override với kiểu trả về covariant** như `Ticket`.
3. `Object.clone()` có khả năng ném checked exception `CloneNotSupportedException`.
4. Object runtime phải đáp ứng marker contract `Cloneable` để implementation cơ sở của Object cho phép clone thông thường; nếu không, ném exception.
5. Bản sao do implementation của Object tạo ra có **field values được sao chép**; đó là **shallow copy** đối với reference fields.
6. Constructor của object được clone **không được gọi** theo quy trình `new ClassName(...)`.
7. Class con có thể override `clone()` để xử lý additional fields hoặc mutable references, nhưng phải quản lý contract cẩn thận.

**Không tự suy rằng** mọi object trong Java đều có public `clone()`. Method tồn tại ở Object nhưng protected và không phải mọi runtime class được phép clone bằng implementation cơ sở.

## 5. `Cloneable` là marker interface, không phải interface có `clone()`

`java.lang.Cloneable` là **marker interface**: nó đánh dấu cho `Object.clone()` biết class instance cho phép field-for-field cloning.

Điểm dễ nhầm:

```java
class Ticket implements Cloneable {
}
```

`Ticket` đã đánh dấu Cloneable, nhưng dòng này **không tự sinh public `Ticket.clone()` method**. Interface `Cloneable` **không khai báo** một method `clone()` để caller gọi qua biến kiểu Cloneable.

Do đó:

```java
// Cloneable marker = new Ticket();
// marker.clone(); // Không hợp lệ: Cloneable không có public clone().
```

Khi class muốn cho code bên ngoài copy, thường phải **override `clone()` và mở quyền `public`**, hoặc cung cấp một phương thức copy khác.

**Phân biệt hai việc:**

- `implements Cloneable`: cho phép đường `Object.clone()` hoạt động khi được gọi đúng cách.
- `public clone()`: API do class tự cung cấp để caller được gọi phương thức clone.

Không có cú pháp đặc biệt `implements Cloneable` nào tự gọi constructor hoặc deep-copy nested objects cho bạn.

## 6. Một `clone()` công khai hoạt động đúng

Tạo **`BasicCloneDemo.java`**:

```java
final class Ticket implements Cloneable {
    private int number;

    Ticket(int number) {
        this.number = number;
    }

    int number() {
        return number;
    }

    void renumber(int next) {
        number = next;
    }

    @Override
    public Ticket clone() {
        try {
            return (Ticket) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

public class BasicCloneDemo {
    public static void main(String[] args) {
        Ticket original = new Ticket(10);
        Ticket copied = original.clone();

        System.out.println(original == copied);
        System.out.println(original.number() == copied.number());

        copied.renumber(20);

        System.out.println("original=" + original.number());
        System.out.println("copied=" + copied.number());
    }
}
```

```bash
javac BasicCloneDemo.java
java BasicCloneDemo
```

```text
false
true
original=10
copied=20
```

### Diễn giải

- Runtime class Ticket implements Cloneable, nên `super.clone()` được phép tạo bản sao field-for-field của Ticket.
- `super.clone()` có compile-time return type `Object`, do đó cast `(Ticket)` hợp lệ theo hợp đồng của clone trong trường hợp này.
- Override dùng covariant return type `Ticket` giúp caller không phải cast.
- Override không khai báo checked exception; nó xử lý `CloneNotSupportedException` bằng `AssertionError` vì class final Ticket tự bảo đảm marker contract.
- `number` là primitive, nên original và copied có các giá trị `int` riêng.
- Vì class không có mutable reference field, shallow copy đủ cho trạng thái ví dụ.

**Không áp dụng máy móc cách bắt `CloneNotSupportedException` vào mọi hierarchy.** Nếu một superclass có chính sách clone đặc biệt hoặc code có khả năng không đáp ứng marker contract, error handling cần dựa vào contract đó.

## 7. Nếu không implements `Cloneable` thì sao?

Một class có thể override `clone()` và làm nó public, nhưng nếu dùng `super.clone()` trên instance **không implements Cloneable**, `Object.clone()` sẽ ném `CloneNotSupportedException`.

Tạo **`CloneWithoutMarkerDemo.java`**:

```java
class Plain {
    @Override
    public Plain clone() throws CloneNotSupportedException {
        return (Plain) super.clone();
    }
}

public class CloneWithoutMarkerDemo {
    public static void main(String[] args) {
        Plain source = new Plain();

        try {
            source.clone();
        } catch (CloneNotSupportedException ex) {
            System.out.println("clone rejected");
        }
    }
}
```

```bash
javac CloneWithoutMarkerDemo.java
java CloneWithoutMarkerDemo
```

```text
clone rejected
```

Ở đây method `Plain.clone()` **được phép gọi từ caller** vì public, nhưng internal call `super.clone()` bị từ chối do Plain không implements Cloneable.

**Không nhầm compile-time với runtime:** Với `Object obj = new Object()`, `obj.clone()` không được phép từ caller bất kỳ vì method Object protected; đó là vấn đề **accessibility**. Trong ví dụ Plain, caller gọi được public override nhưng thất bại lúc runtime vì **Cloneable marker**.

Có thể viết method copy tường minh cho `Plain` mà không cần Cloneable:

```java
Plain copy() {
    return new Plain();
}
```

Đây là mảnh method minh họa, không nói rằng copy data đã đầy đủ khi Plain có thêm fields; mục đích là cho thấy constructor-copy approach không dựa vào marker contract.

## 8. Constructor có chạy khi gọi `Object.clone()`?

Đây là khác biệt lớn giữa `new` và `Object.clone()`.

Sao chép tường minh bằng:

```java
new Ticket(source.number())
```

là một constructor invocation bình thường, nên constructors/initializers cần thiết cho object mới được thực thi.

Đường `super.clone()` dựa trên `Object.clone()` tạo object bằng cơ chế clone mà **không thực thi constructor của class đang được clone**.

Tạo **`CloneConstructorDemo.java`**:

```java
final class Stamp implements Cloneable {
    static int constructorCalls;

    private final int value;

    Stamp(int value) {
        constructorCalls++;
        this.value = value;
    }

    Stamp copy() {
        return new Stamp(value);
    }

    @Override
    public Stamp clone() {
        try {
            return (Stamp) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

public class CloneConstructorDemo {
    public static void main(String[] args) {
        Stamp source = new Stamp(5);
        System.out.println("after source=" + Stamp.constructorCalls);

        Stamp cloned = source.clone();
        System.out.println("after clone=" + Stamp.constructorCalls);

        Stamp copied = source.copy();
        System.out.println("after copy=" + Stamp.constructorCalls);

        System.out.println(source == cloned);
        System.out.println(source == copied);
    }
}
```

```bash
javac CloneConstructorDemo.java
java CloneConstructorDemo
```

```text
after source=1
after clone=1
after copy=2
false
false
```

**Quan sát quan trọng:**

- `new Stamp(5)` gọi constructor một lần.
- `source.clone()` gọi đường Object.clone nhưng **không** gọi `Stamp(int)`, nên counter không tăng.
- `source.copy()` gọi `new Stamp(value)`; counter tăng.
- Cả hai trả object khác identity source.
- Final primitive `value` trong cloned Stamp có giá trị được copy như một phần field-copy operation, không do constructor gán lại.

### Hệ quả thiết kế

Nếu constructor tạo ID mới, tăng counter, validate, đăng ký listener, cấp phát resource hoặc ghi audit, clone có thể **bỏ qua** những side effects ấy. Điều này có thể hợp hoặc không hợp với định nghĩa “copy” của domain.

Ví dụ, ID của hai bản sao nên giữ nguyên hay tạo mới? Không có đáp án chung: đó là business policy mà **explicit copying làm rõ hơn**.

## 9. `Object.clone()` sao chép nông (*shallow*) là gì?

Một object có các fields:

```java
class Report {
    int version;
    String title;
    int[] counts;
}
```

Giả sử `Report` implements Cloneable và override clone hợp lệ gọi `super.clone()`.

Field-for-field copy có nghĩa:

- `version` là primitive: copy giá trị số.
- `title` là reference tới String immutable: copy reference; chia sẻ String thường an toàn.
- `counts` là reference tới **mảng mutable**: copy reference, nên clone và source cùng trỏ một mảng.

Sơ đồ:

```text
source Report S --counts--+
                          +----> int[] X [1, 2]
clone  Report C --counts--+

source != clone
source.counts == clone.counts
```

Đây chính là **shallow copy**. Bản sao có identity mới, nhưng **đồ thị object phía sau fields chưa được tách**.

**Không nên diễn giải shallow copy là “copy nửa đối tượng”**. Tất cả field values được copy; đối với reference values, copy reference có nghĩa vẫn dùng chung object được tham chiếu.

## 10. Chứng minh shallow copy bằng mảng

Tạo **`ShallowCloneArrayDemo.java`**:

```java
import java.util.Arrays;

final class Scores implements Cloneable {
    private final int[] values;

    Scores(int[] values) {
        this.values = values.clone();
    }

    int[] snapshot() {
        return values.clone();
    }

    void setAt(int index, int value) {
        values[index] = value;
    }

    @Override
    public Scores clone() {
        try {
            return (Scores) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }

    @Override
    public String toString() {
        return Arrays.toString(values);
    }
}

public class ShallowCloneArrayDemo {
    public static void main(String[] args) {
        Scores original = new Scores(new int[] {1, 2});
        Scores cloned = original.clone();

        System.out.println(original == cloned);
        System.out.println(original);

        cloned.setAt(0, 99);

        System.out.println("original=" + original);
        System.out.println("cloned=" + cloned);
    }
}
```

```bash
javac ShallowCloneArrayDemo.java
java ShallowCloneArrayDemo
```

```text
false
[1, 2]
original=[99, 2]
cloned=[99, 2]
```

Dù constructor đã clone mảng đầu vào, **`Object.clone()` tiếp tục sao chép reference `values` theo kiểu shallow**. Hai Scores objects trỏ cùng internal array sau clone.

- Final field `values` không cho **gán sang mảng mới** bằng assignment thông thường sau initialization.
- Nó không làm array slots immutable.
- Vì `clone()` hiện chỉ gọi super.clone, việc sửa internal array qua method `setAt` ở một bản sao cũng ảnh hưởng bản còn lại.

Đây là lý do không thể kết luận “đã dùng copy trong constructor nên Object.clone chắc chắn deep copy”.

## 11. Mảng trong Java có `clone()` riêng

Array objects là một trường hợp đặc biệt hữu ích.

Java arrays hỗ trợ `clone()` công khai và implement `Cloneable`. Khi gọi:

```java
int[] source = {1, 2, 3};
int[] copy = source.clone();
```

`copy` là **một array object mới** cùng loại/chiều dài với source và các phần tử được copy. Với primitive array một chiều, đây là **sao chép đủ nội dung** vì các phần tử là primitive values.

Tệp **`ArrayCloneDemo.java`**:

```java
import java.util.Arrays;

public class ArrayCloneDemo {
    public static void main(String[] args) {
        int[] source = {1, 2, 3};
        int[] copy = source.clone();

        System.out.println(source == copy);
        System.out.println(Arrays.equals(source, copy));

        copy[0] = 99;

        System.out.println(Arrays.toString(source));
        System.out.println(Arrays.toString(copy));
    }
}
```

```bash
javac ArrayCloneDemo.java
java ArrayCloneDemo
```

```text
false
true
[1, 2, 3]
[99, 2, 3]
```

**Chú ý:** `array.clone()` là ngôn ngữ/JVM hỗ trợ đối với arrays; không có nghĩa method `clone()` trên mọi instance class đều public. `int[]` clone cũng không yêu cầu bạn viết `implements Cloneable` trong mã Java.

Các phương thức `Arrays.copyOf(...)` và `System.arraycopy(...)` cũng có thể copy phần tử của array, với các contracts/range rules riêng. Chúng là những lựa chọn tường minh khác cho array copy.

## 12. Array of references và mảng nhiều chiều vẫn copy nông

Với `StringBuilder[]`, clone array mới nhưng **các phần tử là references tới cùng StringBuilder objects**.

Tạo **`ObjectArrayCloneDemo.java`**:

```java
public class ObjectArrayCloneDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("A");
        StringBuilder[] source = {builder};
        StringBuilder[] copy = source.clone();

        System.out.println(source == copy);
        System.out.println(source[0] == copy[0]);

        copy[0].append("B");

        System.out.println(source[0]);
        System.out.println(copy[0]);
    }
}
```

```bash
javac ObjectArrayCloneDemo.java
java ObjectArrayCloneDemo
```

```text
false
true
AB
AB
```

Tương tự, `int[][]` là mảng chứa **references tới `int[]` rows**. `source.clone()` chỉ tạo outer array mới; các inner arrays vẫn chia sẻ.

Tệp **`MatrixShallowCloneDemo.java`**:

```java
import java.util.Arrays;

public class MatrixShallowCloneDemo {
    public static void main(String[] args) {
        int[][] source = {{1, 2}, {3}};
        int[][] copy = source.clone();

        System.out.println(source != copy);
        System.out.println(source[0] == copy[0]);

        copy[0][0] = 99;

        System.out.println(Arrays.deepToString(source));
        System.out.println(Arrays.deepToString(copy));
    }
}
```

```bash
javac MatrixShallowCloneDemo.java
java MatrixShallowCloneDemo
```

```text
true
true
[[99, 2], [3]]
[[99, 2], [3]]
```

Để copy data graph sâu hơn, phải copy từng mutable component hoặc chuyển sang immutable representation thích hợp.

## 13. Sao chép tường minh cho object có mutable array

Trong copy constructor, có thể viết rõ:

```java
this.values = source.values.clone();
```

trong khi Object.clone mặc định chỉ copy `values` reference.

Tạo **`DeepCopyConstructorDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class Scores {
    private final int[] values;

    Scores(int[] input) {
        values = Objects.requireNonNull(input).clone();
    }

    Scores(Scores source) {
        this.values = source.values.clone();
    }

    void setAt(int index, int value) {
        values[index] = value;
    }

    int at(int index) {
        return values[index];
    }

    @Override
    public String toString() {
        return Arrays.toString(values);
    }
}

public class DeepCopyConstructorDemo {
    public static void main(String[] args) {
        Scores original = new Scores(new int[] {1, 2});
        Scores copied = new Scores(original);

        copied.setAt(0, 99);

        System.out.println("original=" + original);
        System.out.println("copied=" + copied);
        System.out.println(original == copied);
    }
}
```

```bash
javac DeepCopyConstructorDemo.java
java DeepCopyConstructorDemo
```

```text
original=[1, 2]
copied=[99, 2]
false
```

**Ưu điểm của cách tường minh:**

- Có thể giữ `private final int[] values` và vẫn tạo **mỗi instance một mảng riêng**.
- Validation/normalization được đặt tại các constructors theo contract.
- Reviewer nhìn thấy ngay nested array được copy.
- Không phải dùng `Cloneable`/`CloneNotSupportedException` hoặc override method đặc biệt.
- Constructor thực sự chạy, nên quy tắc khởi tạo fields được compiler kiểm.

Trong class phức tạp, copy constructor có thể **delegates qua constructor chuẩn** để tái sử dụng validation:

```java
Scores(Scores source) {
    this(source.values);
}
```

Đoạn này là phương án thay thế constructor copy trước: constructor `Scores(int[])` đã clone input, nên call `this(source.values)` thực hiện copy và validation của constructor đó. Không đặt **cả hai** constructors copy cùng chữ ký trong cùng class.

## 14. Sao chép bằng static factory: API có tên rõ

Một lựa chọn khác là cung cấp:

```java
static Order copyOf(Order source) {
    return new Order(source.id(), source.items());
}
```

Đây là **mảnh minh họa** giả định `Order` có constructor và accessors tương ứng; constructor cần tự quản lý mutable collection sao cho copy đúng.

Static factory có thể mang tên truyền đạt chính sách:

- `copyOf(source)`: tạo value tương đương theo quy ước API.
- `deepCopyOf(source)`: nhấn mạnh các mutable components được tách.
- `from(source)`: biểu thị conversion/snapshot nếu khác domain type.
- `withName(newName)` trên immutable value class: tạo value khác thay vì mutate original.
- `snapshotOf(source)`: nhấn mạnh capture một trạng thái ổn định.

**Đừng đặt tên “deepCopy” nếu chỉ sao chép outer container và giữ aliases tới nested mutable elements.** Tên chỉ có ích khi nội dung code thật sự đáp ứng contract.

### Chương trình factory copy

Tệp **`CopyFactoryDemo.java`**:

```java
import java.util.List;

final class Basket {
    private final List<String> items;

    private Basket(List<String> items) {
        this.items = List.copyOf(items);
    }

    static Basket of(List<String> items) {
        return new Basket(items);
    }

    static Basket copyOf(Basket source) {
        return new Basket(source.items);
    }

    List<String> items() {
        return items;
    }
}

public class CopyFactoryDemo {
    public static void main(String[] args) {
        Basket original = Basket.of(List.of("A", "B"));
        Basket copy = Basket.copyOf(original);

        System.out.println(original == copy);
        System.out.println(original.items().equals(copy.items()));
        System.out.println(copy.items());
    }
}
```

```bash
javac CopyFactoryDemo.java
java CopyFactoryDemo
```

```text
false
true
[A, B]
```

Factory gọi `new Basket(...)` nên chắc chắn tạo Basket instance mới. `List.copyOf` bảo vệ list structure và String elements vốn immutable; nó có thể chia sẻ **immutable list object reference** an toàn. Không bắt buộc mọi nested references đều khác nhau để hai Basket objects có state độc lập.

**Lưu ý về cách đặt tên:** Một số JDK factory methods tên `copyOf` có thể **trả lại chính input** nếu type/contract cho phép. Trong class Basket cụ thể này, code dùng `new` nên **source và result khác identity**. Không suy ra quy tắc identity từ mỗi cái tên `copyOf` trong mọi API.

## 15. So sánh tổng quát: copy tường minh vs `Object.clone()`

| Khía cạnh | Copy constructor / factory tường minh | Override gọi `Object.clone()` |
| --- | --- | --- |
| Cú pháp thường gặp | `new Person(other)` / `Person.copyOf(other)` | `other.clone()` nếu method exposed |
| Dựa vào `Cloneable` | Không | Có khi dùng implementation Object.clone |
| Constructor chạy cho object mới | **Có**, nếu dùng `new` | **Không** theo Object.clone mechanism |
| Kiểm fields và invariant | Code copy tự điều khiển rõ | Field-for-field copy ban đầu; override phải khắc phục |
| Copy primitive fields | Bằng giá trị | Bằng giá trị |
| Copy immutable references | Có thể share an toàn | Copy reference |
| Copy mutable references | Có thể clone/copy chủ động | Mặc định chia sẻ references |
| Checked exception | Tùy constructor/factory contract | Base method khai `CloneNotSupportedException` |
| Quyền truy cập | API do class quyết định | Object.clone là `protected`; thường phải public override |
| Return type | Type được thiết kế rõ | Object base; override covariant được |
| Kế thừa / subtype | Copy constructor trên base cần chú ý runtime type | Object.clone tạo cùng runtime class trong field-copy path |
| Field `final` mutable reference | Constructor có thể gán defensive copy mới | Clone copy field final reference; không gán lại sau clone thông thường |
| Thay đổi schema fields | Phải cập nhật manual copy đúng | Field-for-field tự thêm field value nhưng có thể share mutable field mới |
| Debug/tracing | Thấy rõ validations và constructor side effects | Clone có thể bỏ qua constructors và side effects |
| Phụ thuộc hierarchy | Có thể thấp hơn nếu class final | Phải xét inherited clone contracts |
| Khuyến nghị cho API mới | Thường dễ bảo trì | Dùng khi contract/legacy/API đòi hoặc trường hợp được kiểm soát |

**Cẩn thận chữ “deep”:** Không phải copy constructor tự động deep copy. Nó chỉ deep theo những phần bạn **thật sự sao chép**. Không phải clone lúc nào cũng chỉ shallow nếu subclass **đã override để deep-copy**; mặc định `Object.clone` mới là shallow.

## 16. `final` field tạo ra một quyết định quan trọng khi deep-clone

Giả sử:

```java
final class Data implements Cloneable {
    private final int[] values;

    // ...
}
```

`super.clone()` tạo một Data object mới có `values` field trỏ **cùng mảng** với source.

Để deep-clone, ta muốn:

```java
Data copied = (Data) super.clone();
copied.values = values.clone(); // Không hợp lệ: values là final.
```

Đây là **mảnh minh họa lỗi compile-time**, không phải code để copy vào chương trình. Field `final` không thể được gán lại ở đây.

Có các cách thiết kế:

1. **Ưu tiên copy constructor**: `new Data(source.values)`; constructor có thể gán final field bằng mảng clone.
2. Nếu phải dùng `clone()`, có thể triển khai override **bằng cách gọi constructor mới** thay vì `super.clone()`, nhưng lúc đó contract, inheritance và constructor side effects khác với field-for-field clone. Tên clone phải được giải thích.
3. Chỉ với class không có ràng buộc final tương ứng, override gọi super.clone rồi thay reference mutable field mới trong cloned object có thể phù hợp.
4. Nếu component thực chất immutable, chia sẻ reference là an toàn; không cần deep-copy chỉ để đổi identity.

**Kết luận:** `final` fields rất hữu ích cho immutable design; copy tường minh thường hòa hợp với final-fields initialization hơn clone-and-patch.

## 17. Override `clone` để copy mutable array khi field không final

Một pattern clone cổ điển là gọi `super.clone()`, sau đó thay các mutable references. Nó cần field có khả năng được gán lại trong cloned instance.

Tạo **`DeepCloneOverrideDemo.java`**:

```java
import java.util.Arrays;

final class Scores implements Cloneable {
    private int[] values;

    Scores(int[] input) {
        values = input.clone();
    }

    void setAt(int index, int value) {
        values[index] = value;
    }

    @Override
    public Scores clone() {
        try {
            Scores copy = (Scores) super.clone();
            copy.values = values.clone();
            return copy;
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }

    @Override
    public String toString() {
        return Arrays.toString(values);
    }
}

public class DeepCloneOverrideDemo {
    public static void main(String[] args) {
        Scores original = new Scores(new int[] {1, 2});
        Scores clone = original.clone();

        clone.setAt(0, 99);

        System.out.println("original=" + original);
        System.out.println("clone=" + clone);
    }
}
```

```bash
javac DeepCloneOverrideDemo.java
java DeepCloneOverrideDemo
```

```text
original=[1, 2]
clone=[99, 2]
```

Trong override:

1. `super.clone()` tạo shallow copy ban đầu.
2. `copy.values = values.clone()` thay mảng tham chiếu ở cloned instance thành mảng mới.
3. Trả bản sao có state độc lập ở tầng mutable array.

**Nhưng đây chưa phải giải pháp tổng quát cho mọi object graph**. Nếu fields chứa mảng các mutable objects, nested collection, cycles hoặc shared aliases, phải sao chép các tầng tương ứng. Ngoài ra, clone-and-patch tạo object trung gian có field reference chia sẻ trong quá trình method thực thi; không publish cloned object trước khi hoàn tất patch.

## 18. Có thể override `clone()` không dùng `super.clone()`?

Về mặt Java, một class có thể định nghĩa public method tên `clone()` tự tạo object bằng constructor mà không gọi Object.clone. Ví dụ:

```java
@Override
public Scores clone() {
    return new Scores(values);
}
```

Đây là **phương án khác** dành cho một class có constructor `Scores(int[])` và field `values`; không kết hợp vào class ví dụ ở mục 17 nếu chưa điều chỉnh và chọn một implementation duy nhất.

Với class `final` biết rõ state, method đó có thể bảo đảm deep copy và giữ `final` fields nếu constructor được thiết kế đúng.

Nhưng cần phân biệt:

- Đây là **method override mang tên clone** có implementation tường minh bằng `new`.
- Nó **không có hành vi constructor-bypass** của `Object.clone()`.
- Với subclassing mở, tạo cố định một superclass instance trong `clone()` có thể gây vấn đề subtype preservation.
- Không nên nói “mọi lần gọi method tên clone đều chắc chắn không chạy constructor”; điều ấy đúng với **Object.clone implementation**, không đúng với arbitrary overrides dùng `new`.

Đây là lý do khi API chưa bị ràng buộc bởi tên clone, một tên `copy()` hoặc copy constructor có contract rõ thường ít gây ngộ nhận hơn.

## 19. Trường hợp sao chép shallow hoàn toàn hợp lý

Shallow copy không tự là bug. Nó có thể đúng khi references được chia sẻ trỏ tới **immutable values** hoặc collaborator có chủ ý shared.

Ví dụ:

```java
final class Label implements Cloneable {
    private final String text;

    Label(String text) {
        this.text = text;
    }

    @Override
    public Label clone() {
        try {
            return (Label) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }

    String text() {
        return text;
    }
}
```

Đây là class declaration hợp lệ, chưa có `main`. `String` immutable nên việc source và clone cùng trỏ một String object không làm observable state thay đổi.

Tương tự, một copy constructor có thể viết:

```java
Label(Label source) {
    this.text = source.text;
}
```

nếu muốn copy tường minh.

**Bài kiểm:** hỏi “references được chia sẻ có thể mutate theo con đường nào?” chứ không chỉ hỏi “có chia sẻ reference hay không?”. Chia sẻ immutable components thường an toàn và tiết kiệm memory.

## 20. Kế thừa: sao chép lớp cha có thể làm mất subtype

Copy constructor truyền thống có một hạn chế: `new Base(source)` **luôn tạo Base**, không tự giữ runtime subtype khi source là Derived.

Tạo **`CopyConstructorSlicingDemo.java`**:

```java
class Animal {
    private final String name;

    Animal(String name) {
        this.name = name;
    }

    Animal(Animal other) {
        this.name = other.name;
    }

    String name() {
        return name;
    }
}

final class Dog extends Animal {
    private final String breed;

    Dog(String name, String breed) {
        super(name);
        this.breed = breed;
    }

    String breed() {
        return breed;
    }
}

public class CopyConstructorSlicingDemo {
    public static void main(String[] args) {
        Animal original = new Dog("Milo", "Collie");
        Animal copy = new Animal(original);

        System.out.println(original.getClass().getSimpleName());
        System.out.println(copy.getClass().getSimpleName());
        System.out.println(original.name().equals(copy.name()));
    }
}
```

```bash
javac CopyConstructorSlicingDemo.java
java CopyConstructorSlicingDemo
```

```text
Dog
Animal
true
```

**Lưu ý:** Đây không phải “Java tự cắt bytes của object” theo cơ chế C++; đơn giản là biểu thức `new Animal(original)` **tạo một Animal instance mới**, vì constructor chỉ định type Animal. `Dog.breed` không có trong Animal copy.

Vì vậy copy constructor/factory của base class cần định nghĩa rõ:

- Có chủ ý tạo Base value?
- Hay cần giữ runtime subtype và mọi subclass state?
- Nếu giữ subtype, có cần **virtual copy/polymorphic factory** trên hierarchy?

Đừng tự tuyên bố mọi `Base copy = new Base(subclassInstance)` là bản sao đầy đủ của subclass.

## 21. `Object.clone()` có ưu điểm giữ runtime class

Khi thực thi bằng cơ chế field-copy của `Object.clone()`, clone được tạo **cùng runtime class** với source object. Đây là một khác biệt quan trọng với `new Base(source)`.

Tạo **`CloneSubclassDemo.java`**:

```java
class Animal implements Cloneable {
    private final String name;

    Animal(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    @Override
    public Animal clone() {
        try {
            return (Animal) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

final class Dog extends Animal {
    private final String breed;

    Dog(String name, String breed) {
        super(name);
        this.breed = breed;
    }

    String breed() {
        return breed;
    }
}

public class CloneSubclassDemo {
    public static void main(String[] args) {
        Animal original = new Dog("Milo", "Collie");
        Animal clone = original.clone();

        System.out.println(original == clone);
        System.out.println(clone.getClass().getSimpleName());
        System.out.println(clone.name());

        if (clone instanceof Dog dog) {
            System.out.println(dog.breed());
        }
    }
}
```

```bash
javac CloneSubclassDemo.java
java CloneSubclassDemo
```

```text
false
Dog
Milo
Collie
```

Vì `Dog` kế thừa Cloneable marker thông qua Animal, Object.clone có thể tạo clone **runtime class Dog** dù method public override được định nghĩa ở Animal.

Nhưng **đừng nhầm subtype preserved với deep copy guaranteed**:

- Nếu Dog sau này thêm `List` mutable, inherited shallow clone sẽ giữ reference chung trừ khi class/hierarchy cập nhật.
- Subclass có thể override clone với contract khác, gây nguy cơ nếu hierarchy không được thiết kế để clone mở rộng.
- Kiểu trả về của `Animal.clone()` vẫn là Animal, dù runtime clone object có thể Dog; caller cần kiểm type/abstraction khi dùng Dog-specific behavior.

## 22. Kế thừa và mutable fields: mỗi subclass phải xem xét clone contract

Giả sử:

```java
class Base implements Cloneable {
    private final String id;

    Base(String id) {
        this.id = id;
    }

    @Override
    public Base clone() {
        try {
            return (Base) super.clone();
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}
```

Hôm nay Base chỉ giữ immutable String, clone shallow là đủ. Ngày mai một subclass thêm:

```java
private final java.util.List<String> mutableNotes =
        new java.util.ArrayList<>();
```

thì inherited clone sẽ copy reference tới cùng mutable list object; hơn nữa field final cản việc “clone rồi gán mới” bình thường.

**Bài học cho code review:** “Superclass có method clone” không đồng nghĩa “mọi subclass trong tương lai tự deep-copy đúng”. Một hierarchy có mutable fields và clone contract cần quy định cách clone mở rộng, hoặc dùng composition/explicit copy per type.

### Vì sao `Cloneable` không phải một “mẫu đa hình copy” lý tưởng?

Marker interface không hứa public `clone()` signature hoặc return type. Caller có biến kiểu `Cloneable` **không thể gọi clone như gọi method của một interface copy**.

Nếu ứng dụng muốn polymorphic copying rõ ràng, có thể thiết kế một interface chứa **method riêng**:

```java
interface Copyable<T> {
    T copy();
}
```

Sau đó mỗi concrete class implement `copy` đúng semantics. Đây là API người lập trình tự thiết kế; Java không tự suy hợp đồng “deep” từ generic interface ấy.

## 23. Tạo một polymorphic copy method tường minh

Một giải pháp cho hierarchy muốn giữ runtime subtype là **mỗi class hiện thực `copy()` phù hợp**.

Tệp **`PolymorphicCopyDemo.java`**:

```java
abstract class Animal {
    private final String name;

    Animal(String name) {
        this.name = name;
    }

    String name() {
        return name;
    }

    abstract Animal copy();
}

final class Dog extends Animal {
    private final String breed;

    Dog(String name, String breed) {
        super(name);
        this.breed = breed;
    }

    @Override
    Dog copy() {
        return new Dog(name(), breed);
    }

    String breed() {
        return breed;
    }
}

public class PolymorphicCopyDemo {
    public static void main(String[] args) {
        Animal original = new Dog("Milo", "Collie");
        Animal copy = original.copy();

        System.out.println(original == copy);
        System.out.println(copy.getClass().getSimpleName());
        System.out.println(copy.name());

        if (copy instanceof Dog dog) {
            System.out.println(dog.breed());
        }
    }
}
```

```bash
javac PolymorphicCopyDemo.java
java PolymorphicCopyDemo
```

```text
false
Dog
Milo
Collie
```

- `Animal` định nghĩa abstract method `copy()`, không đòi Cloneable.
- `Dog.copy()` dùng constructor và trả Dog (covariant return type).
- Khi gọi qua `Animal` reference, runtime dispatch tới Dog, trả **đúng subtype**.
- Khi thêm một subclass mới, class đó phải cung cấp copy implementation tương ứng.

Điểm phải trả giá: người thiết kế hierarchy tự chịu trách nhiệm clone/copy toàn bộ fields và nested objects. Nhưng contract có thể đặt tên, kiểm thử và mở rộng một cách tường minh.

## 24. Sao chép mảng nhiều chiều theo cách tường minh

Một deep-enough copy cho `int[][]` cần copy **outer array và từng inner `int[]`**, không chỉ outer clone.

Tệp **`ExplicitMatrixCopyDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

final class Matrix {
    private final int[][] rows;

    Matrix(int[][] source) {
        Objects.requireNonNull(source);
        rows = copyRows(source);
    }

    Matrix(Matrix source) {
        rows = copyRows(source.rows);
    }

    private static int[][] copyRows(int[][] source) {
        int[][] copied = new int[source.length][];
        for (int i = 0; i < source.length; i++) {
            copied[i] = Objects.requireNonNull(source[i]).clone();
        }
        return copied;
    }

    void set(int row, int column, int value) {
        rows[row][column] = value;
    }

    @Override
    public String toString() {
        return Arrays.deepToString(rows);
    }
}

public class ExplicitMatrixCopyDemo {
    public static void main(String[] args) {
        Matrix source = new Matrix(new int[][] {
                {1, 2}, {3}
        });

        Matrix copy = new Matrix(source);
        copy.set(0, 0, 99);

        System.out.println(source);
        System.out.println(copy);
    }
}
```

```bash
javac ExplicitMatrixCopyDemo.java
java ExplicitMatrixCopyDemo
```

```text
[[1, 2], [3]]
[[99, 2], [3]]
```

`copyRows` tạo outer array mới và clone từng inner primitive array. Với jagged arrays, độ dài từng row vẫn được giữ.

**Không gọi đây là deep copy của mọi object graph**; chỉ là deep-enough copy cho shape `int[][]`. Với `MutableElement[][]`, clone các inner arrays còn chia sẻ MutableElement objects.

## 25. `ArrayList.clone()` và `List.copyOf`: cũng cần hiểu contract

Một số Java collections có method clone riêng, nhưng contract có thể **chỉ clone structure shallow**.

Ví dụ `ArrayList.clone()` trả bản sao cấu trúc list, nhưng **không clone từng element**.

Tệp **`ArrayListCloneDemo.java`**:

```java
import java.util.ArrayList;

public class ArrayListCloneDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("A");
        ArrayList<StringBuilder> source = new ArrayList<>();
        source.add(builder);

        @SuppressWarnings("unchecked")
        ArrayList<StringBuilder> copied =
                (ArrayList<StringBuilder>) source.clone();

        System.out.println(source == copied);
        System.out.println(source.get(0) == copied.get(0));

        builder.append("B");
        System.out.println(source.get(0));
        System.out.println(copied.get(0));
    }
}
```

```bash
javac ArrayListCloneDemo.java
java ArrayListCloneDemo
```

```text
false
true
AB
AB
```

**Điểm QA:** `ArrayList.clone()` là public method cụ thể của ArrayList và trả `Object` theo API override ở lớp này, nên cần cast. Generic element type không được runtime-check đầy đủ vì type erasure; ví dụ dùng `@SuppressWarnings("unchecked")` tại local declaration có thể biên dịch, nhưng ứng dụng vẫn phải bảo đảm type.

Nếu mục đích là immutable snapshot của `List<String>`, thường `List.copyOf(source)` rõ hơn. Nếu mục đích là mutable structural copy, `new ArrayList<>(source)` dễ đọc. Cả hai vẫn **shallow đối với elements**.

## 26. Copy constructor cho collection chứa mutable elements

Đặt `List.copyOf` lên một `List<StringBuilder>` không deep-freeze StringBuilder objects. Nếu cần snapshot text, hãy convert sang Strings.

Tệp **`CopyMutableElementsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

final class Notes {
    private final List<String> lines;

    Notes(List<StringBuilder> input) {
        Objects.requireNonNull(input);
        List<String> copied = new ArrayList<>();

        for (StringBuilder builder : input) {
            copied.add(Objects.requireNonNull(builder).toString());
        }

        lines = List.copyOf(copied);
    }

    Notes(Notes source) {
        lines = List.copyOf(source.lines);
    }

    List<String> lines() {
        return lines;
    }
}

public class CopyMutableElementsDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("A");
        Notes original = new Notes(List.of(builder));
        Notes copy = new Notes(original);

        builder.append("B");

        System.out.println("original=" + original.lines());
        System.out.println("copy=" + copy.lines());
        System.out.println(original == copy);
    }
}
```

```bash
javac CopyMutableElementsDemo.java
java CopyMutableElementsDemo
```

```text
original=[A]
copy=[A]
false
```

Trong constructor đầu tiên, `StringBuilder.toString()` tạo immutable text snapshots; `List.copyOf` khóa list structure. Constructor copy của Notes có thể **chia sẻ các immutable elements** và thậm chí underlying immutable list object mà vẫn giữ observable state độc lập.

**Điều quan trọng là không còn mutable alias**, chứ không phải mọi reference trong graph đều phải khác nhau.

## 27. Constructors và invariants: copy có thể validate, clone có thể bỏ qua

Giả sử class có các ràng buộc:

- Số lượng không âm.
- Mã không được blank.
- Hai fields phải nhất quán, ví dụ `start <= end`.
- Mảng/list không có null hoặc giá trị ngoài phạm vi.

Với copy constructor, ta có thể:

```java
Range(Range source) {
    this(source.start, source.end);
}
```

và dùng constructor `Range(int start, int end)` kiểm invariant. Đây là mảnh minh họa, giả định class Range định nghĩa fields và constructor phù hợp.

Với `Object.clone()`, constructors không chạy, nên **validation code trong constructor không tự chạy lại**. Nếu runtime state được bảo vệ nhất quán và không mutable, field copy có thể vẫn hợp lệ. Nhưng nếu class cho phép state thay đổi hoặc phụ thuộc external resources, không được mặc định clone hợp lệ với mọi trường hợp.

### Ví dụ factory chủ động tạo identity mới

Một `Session` object có session ID, creation timestamp và connection handle. “Copy” có thể cần:

1. Giữ lại configuration.
2. Phát sinh session ID mới.
3. Không sao chép connection đang mở.
4. Có resource ownership rõ.
5. Báo lỗi nếu tạo session mới thất bại.

Một copy factory chuyên dụng như `Session.fromConfig(original.config())` làm chính sách này rõ hơn field-for-field clone. Đây là minh họa **thiết kế**, không phải source runnable; tùy hệ thống mà semantics khác nhau.

## 28. Vấn đề resource: clone handle không tạo resource độc lập

Các objects như `InputStream`, `Socket`, `Connection`, `Thread`, lock hoặc file handle có vòng đời đặc thù.

Nếu một class giữ:

```java
private final java.io.InputStream stream;
```

một shallow clone sẽ giữ **cùng stream reference**. Nó không mở stream khác và không bảo đảm hai objects có quyền đóng stream độc lập.

Thậm chí “deep-copy một open socket” không có nghĩa tổng quát: cần quy định liệu copy nên chia sẻ connection, mở connection mới hay cấm copy.

**Cách thiết kế tốt:** tách **immutable configuration/value state** khỏi **resource-bearing live object**, rồi cho phép copy configuration bằng factory nếu phù hợp. Không áp dụng field-for-field cloning với những resource wrappers chỉ vì method có sẵn.

### Ownership phải được xác định

Một getter/copy method trả object mới không nhất thiết có quyền gọi `close()` trên resource được giữ chung. Nếu hai wrappers cùng giữ một closable resource, việc đóng bởi một wrapper có thể khiến wrapper kia hỏng. Copy policy phải xác định ai sở hữu, ai đóng, khi nào và có thể chia sẻ hay không.

## 29. Copy và equality: giống về giá trị chưa chắc khác nhau về nghiệp vụ

Hai concepts độc lập:

- **Identity:** `source == copy` có thể false khi tạo instance mới.
- **Logical equality:** `source.equals(copy)` có thể true hoặc false tùy class.
- **State independence:** mutate copy có làm source thay không?
- **Subtype preservation:** copy có cùng runtime class với source không?
- **Resource independence:** copy có sở hữu độc lập external resources không?

Một copy constructor có thể tạo object khác identity nhưng dùng default Object.equals nên `equals` false. Một immutable value class có thể định nghĩa equals theo values nên copy equals source true. Một factory tên `copyOf` có thể trả reference cũ khi contract cho phép; không nên suy identity chỉ từ tên API.

### Bốn tiêu chí QA riêng

| Tiêu chí | Câu hỏi test |
| --- | --- |
| Identity | `source == copied`? Kết quả nào contract hứa? |
| Value equality | `source.equals(copied)`? Có cùng logical data không? |
| Mutation isolation | Sửa mutable component của copy có ảnh hưởng source không? |
| Runtime type | `source.getClass()==copied.getClass()`? Có cần bảo đảm không? |

Không được suy “`equals` true → đã deep copy” hoặc “`==` false → không còn alias”. Hai assertions đó không đủ.

## 30. `Object.clone()` và `CloneNotSupportedException`: thiết kế API public

`Object.clone()` khai báo checked `CloneNotSupportedException`. Một override public có thể:

**Giữ checked exception** nếu contract muốn caller xử lý:

```java
@Override
public MyType clone() throws CloneNotSupportedException {
    return (MyType) super.clone();
}
```

Đây là **mảnh phương thức minh họa** giả định class `MyType` implements Cloneable và kế thừa Object.clone phù hợp.

**Hoặc xử lý bên trong** như ở `BasicCloneDemo`, nếu class có đủ bảo đảm đường Object.clone không bị từ chối.

Quy tắc Java cho overriding methods:

- Override không được khai báo checked exceptions **rộng hơn** method superclass tương ứng.
- Có thể dùng return type covariant (ví dụ `MyType` thay vì Object).
- Không được giảm access dưới `protected` so với Object.clone; public override phù hợp khi muốn API công khai.
- `@Override` hỗ trợ compiler xác minh method thực sự override.
- Nếu return type sai hoặc class chưa tuân thủ clone contract, compile/runtime có thể thất bại.

**Đừng viết code giả định mọi subclass của Cloneable có public clone tự động.** Marker interface không khai báo clone method.

## 31. Những kiểu thường không cần `clone()`

Nếu class là **immutable value object**, việc trả object cũ đôi khi đủ: không có mutable state cần tách. Ví dụ `String` immutable nên không cần tạo String mới để tránh mutation của string nội dung.

Nếu class là **final value object** chứa primitives và immutable components, một static factory hoặc constructor có thể tái sử dụng object nếu API cho phép; hoặc trả bản sao mới nếu identity contract yêu cầu. Đừng ép clone chỉ để luôn đổi reference.

Nếu class có **mutable array/list**, hãy xác định shallow/deep policy cụ thể. Nếu class đại diện **resource/session**, thường cần factory tạo resource mới hoặc cấm copy.

Đây là các lựa chọn về semantics chứ không phải một luật “mọi immutable class không được clone”.

## 32. Copy sâu với đồ thị tham chiếu có chu trình

Deep copying một đồ thị có cycles và shared references khó hơn một chuỗi `new` đơn giản:

```text
Node A ----next----> Node B
   ^                   |
   +------next---------+
```

Nếu copy recursively bằng:

```java
new Node(copy(node.next))
```

mà không theo dõi objects đã copy, traversal có thể lặp vô hạn qua cycle.

Ngoài cycles, graph có thể có **sharing**:

```text
A.left  ──┐
          ├──> Shared Child X
A.right ──┘
```

Nếu copy child hai lần không theo chính sách, clone có thể thành hai children thay vì giữ alias structure cần thiết.

Một thuật toán deep-copy có chủ đích có thể dùng `IdentityHashMap<Original, Copy>` để ghi nhận objects đã xử lý theo **reference identity**, rồi:

1. Cấp đối tượng copy cho node hiện tại.
2. Ghi vào identity map **trước khi đệ quy vào children**.
3. Sao chép references/connections theo map.
4. Giữ cycles và shared topology theo contract.

Đó là **mô hình thuật toán**, không phải một implementation áp dụng cho mọi class. Cần xem constructor invariants, final fields và thứ tự wiring có cho phép xây graph theo hai pha hay không. Thường thiết kế immutable graph representation/serialization có schema rõ dễ kiểm chứng hơn “deep clone bất kỳ Object”.

## 33. Serialization không tự đồng nghĩa `clone()` hay copy constructor

Có thể serialize rồi deserialize để xây một object graph mới trong một số hoàn cảnh, nhưng đó là một cơ chế khác với hợp đồng và hạn chế riêng:

- Không phải mọi object implement Serializable.
- Dữ liệu transient, custom hooks, identity sharing và version compatibility cần được xử lý.
- Không nên dùng serialization round-trip làm giải pháp clone mặc định chỉ vì tránh viết code copy.
- Đặc biệt, deserialization dữ liệu không tin cậy có nguy cơ bảo mật và cần API/filter/policy thích hợp.

**Không nhầm:** Object.clone không dùng Java serialization; copy constructor không bắt buộc serialize; `Cloneable` và `Serializable` là hai interfaces khác nhau.

## 34. Performance: `clone` không mặc định nhanh hơn hoặc đúng hơn

Đánh giá performance cần dựa trên **workload và implementation cụ thể**, không gắn nhãn tuyệt đối.

- Shallow Object.clone có thể tránh chạy constructor, nhưng không thực hiện validations/deep-copy cần thiết.
- Copy constructor có thể tốn work hơn vì tạo nested copies hoặc normalize data theo domain; đó có thể là **yêu cầu correctness**, không phải “chậm vô ích”.
- Với primitive arrays, `clone()` và `Arrays.copyOf` đều là các lựa chọn hiệu quả tùy workload; benchmark đúng mới kết luận được.
- JIT, escape analysis, GC, heap size, object graph, reuse của immutable components đều ảnh hưởng số liệu.
- Một lựa chọn “nhanh” nhưng giữ mutable alias sai có thể gây bug nặng hơn chi phí cấp phát.

**Ưu tiên tính đúng:** xác định copy depth, identity, invariants và ownership trước. Sau đó mới benchmark nếu performance trở thành yêu cầu thực.

## 35. Self-test so sánh cùng input theo hai cơ chế

Tạo **`CopyComparisonSelfTest.java`**:

```java
import java.util.Arrays;

final class Payload implements Cloneable {
    private int[] bytes;

    Payload(int[] input) {
        bytes = input.clone();
    }

    Payload(Payload source) {
        bytes = source.bytes.clone();
    }

    void write(int index, int value) {
        bytes[index] = value;
    }

    int at(int index) {
        return bytes[index];
    }

    @Override
    public Payload clone() {
        try {
            return (Payload) super.clone(); // Shallow by default.
        } catch (CloneNotSupportedException ex) {
            throw new AssertionError(ex);
        }
    }
}

public class CopyComparisonSelfTest {
    static void check(boolean condition, String name) {
        if (!condition) {
            throw new AssertionError(name);
        }
    }

    public static void main(String[] args) {
        Payload original = new Payload(new int[] {1, 2});
        Payload shallow = original.clone();
        Payload deep = new Payload(original);

        check(original != shallow, "clone identity");
        check(original != deep, "copy identity");

        shallow.write(0, 99);
        check(original.at(0) == 99, "shallow shares array");
        check(deep.at(0) == 1, "deep isolates array");

        deep.write(1, 77);
        check(original.at(1) == 2, "deep independent");

        System.out.println("shallow original=" + original.at(0));
        System.out.println("deep first=" + deep.at(0));
        System.out.println("deep second=" + deep.at(1));
        System.out.println("copy checks passed");
    }
}
```

```bash
javac CopyComparisonSelfTest.java
java CopyComparisonSelfTest
```

```text
shallow original=99
deep first=1
deep second=77
copy checks passed
```

Đây là test **cố ý chứng minh shallow alias**. Nó không nói clone luôn sai: class Payload hứa những semantics gì mới quyết định có nên share array không. Tên `clone()` trong ví dụ được dùng với default Object.clone behavior để thấy sự khác biệt.

Không cần import `java.util.Arrays` trong code hoạt động này; Java cho phép import không dùng. Đây là self-test bằng main, không phải một bộ JUnit hoàn chỉnh.

## 36. Checklist kiểm tra bản sao đúng hợp đồng

Khi review method `copy()`, constructor copy hoặc `clone()`, hãy hỏi:

- [ ] Có **tạo object mới** hay chỉ gán reference?
- [ ] API có hứa source và copy phải khác identity?
- [ ] Giá trị logic nào phải giữ nguyên?
- [ ] Fields primitive nào được copy trực tiếp?
- [ ] References tới immutable objects nào được phép chia sẻ?
- [ ] Arrays và collections mutable có cần structural copy?
- [ ] Các elements mutable bên trong có cần deep copy/convert?
- [ ] Getter của source/copy có lộ internal mutable references?
- [ ] Mutate copy có làm source đổi không?
- [ ] Mutate source có làm copy đổi không?
- [ ] Có copy đúng final fields và constructor invariants không?
- [ ] Nếu dùng Object.clone, runtime type có implements Cloneable?
- [ ] Có public override nếu caller cần gọi clone từ bên ngoài?
- [ ] Có xử lý CloneNotSupportedException đúng contract?
- [ ] Có phân biệt marker Cloneable với API method clone?
- [ ] Có hiểu Object.clone không gọi constructor cho object cloned?
- [ ] Có cần tạo ID/timestamp/resource mới thay vì copy raw field?
- [ ] Runtime subtype có cần được giữ không?
- [ ] Với inheritance, subclasses mới có thêm mutable fields không?
- [ ] Có cần bảo toàn shared references/cycles trong object graph?
- [ ] Có external resources không thể copy bằng field-for-field?
- [ ] Thread khác có thể mutate source trong lúc đang copy?
- [ ] Nếu copy dùng làm key, equals/hashCode có ổn định theo contract?
- [ ] Tests không dựa vào raw object hash values hoặc allocation optimization?
- [ ] Các ví dụ runnable có tên tệp đúng public class, lệnh `javac`/`java` và stdout ổn định?

## 37. Các lỗi thường gặp

| Ngộ nhận | Thực tế | Cách xử lý |
| --- | --- | --- |
| `b=a` sao chép object | Chỉ copy reference | Constructor/factory/clone có contract tạo object mới |
| `Object.clone` luôn public | Object.clone là protected | Public override nếu muốn expose |
| `implements Cloneable` tự tạo `clone()` method | Cloneable là marker rỗng | Khai báo method copy/clone công khai |
| `Object.clone` luôn chạy thành công | Có thể ném CloneNotSupportedException | Kiểm marker/hierarchy contract |
| `clone` luôn deep copy | Object.clone mặc định shallow | Copy mutable fields hoặc dùng constructor |
| Hai clones khác identity nghĩa mọi fields độc lập | Mutable refs vẫn có thể share | Test nested aliases |
| `array.clone()` clone mọi element object | Chỉ copy reference elements | Copy/convert mutable elements |
| `matrix.clone()` đủ cho 2D matrix | Inner arrays được share | Copy từng inner row |
| Copy constructor luôn deep | Chỉ deep theo logic viết | Audit fields/nested references |
| `final` reference làm array immutable | Array slots mutable | Defensive copy hoặc immutable representation |
| Có thể gán lại `final` field sau super.clone | Final không cho gán lại theo cách đó | Copy constructor hoặc đổi model |
| `clone()` luôn không gọi constructor | Chỉ cơ chế Object.clone như mô tả | Phân biệt arbitrary overrides |
| `new Base(subtype)` giữ runtime subtype | Tạo Base mới | Polymorphic copy nếu cần |
| Clone giữ subtype nghĩa clone nested mutable state | Chỉ giữ runtime class | Audit từng subclass fields |
| Mutable list dùng chung là deep copy | Cùng elements, có thể cùng container | Copy cấu trúc và mutable leaves |
| `ArrayList.clone` so elements sâu | Shallow structural copy | Explicit deep copy nếu cần |
| `Cloneable` dùng được như `Copyable.copy()` | Marker không có method clone | Tạo interface copy có method |
| Copy connection wrapper tạo socket mới | Shallow chỉ giữ handle reference | Resource-specific factory/ownership |
| Hash bằng nhau chứng minh copy cùng object | Hash collision hợp lệ | `==` hoặc class contract |
| “Copy nhanh nhất” luôn tối ưu | Không có benchmark/context | Correctness trước, đo sau |
| Serialize-deserialize luôn là deep clone an toàn | Không phải mọi type hỗ trợ, nhiều rủi ro | Copy API có schema/contract rõ |

## 38. Câu hỏi tự luyện có đáp án

**Câu 1.** `Box b=a;` có tạo Box object mới không?

*Đáp án:* Không; chỉ gán alias reference.

**Câu 2.** `Object.clone()` khai báo access modifier nào?

*Đáp án:* `protected`. Muốn caller ngoài phạm vi truy cập được, class thường cần public override.

**Câu 3.** Interface `Cloneable` có method `clone()` không?

*Đáp án:* Không. Nó là marker interface.

**Câu 4.** Điều gì xảy ra khi gọi `super.clone()` trên instance không implements Cloneable trong trường hợp class thông thường?

*Đáp án:* Implementation Object.clone từ chối bằng `CloneNotSupportedException`.

**Câu 5.** `Object.clone()` mặc định deep hay shallow?

*Đáp án:* Shallow field-for-field copy: primitive values copy, reference values copy tham chiếu.

**Câu 6.** Clone object có chạy constructor của object mới không?

*Đáp án:* Cơ chế `Object.clone()` không chạy constructor; override tự dùng `new` thì có.

**Câu 7.** `int[] a={1,2}; int[] b=a.clone();` sau `b[0]=9`, `a[0]` là gì?

*Đáp án:* Vẫn 1 vì primitive array clone tạo separate slots.

**Câu 8.** `StringBuilder[]` clone có clone các StringBuilder elements không?

*Đáp án:* Không, array clone copy references.

**Câu 9.** `int[][] matrix.clone()` có copy từng inner row không?

*Đáp án:* Không. Chỉ clone outer array.

**Câu 10.** Vì sao `private final int[] values` gây khó khi clone-and-patch sâu?

*Đáp án:* Field final không thể gán lại sang clone array trong ordinary clone method sau super.clone; copy constructor có thể khởi tạo final field ngay khi tạo instance.

**Câu 11.** Copy constructor có tự bảo đảm deep copy không?

*Đáp án:* Không. Nó chỉ thực hiện những phép copy code đã viết.

**Câu 12.** Nếu source là subclass Dog mà gọi `new Animal(source)`, result là type nào?

*Đáp án:* Animal instance, trừ khi constructor/factory rõ ràng tạo subtype bằng cách khác.

**Câu 13.** `Object.clone()` thường tạo runtime class gì?

*Đáp án:* Cùng runtime class với source trong cơ chế Object.clone field-for-field thông thường.

**Câu 14.** Có nên dùng `super.clone()` cho resource wrapper có Socket không?

*Đáp án:* Không mặc định; phải xác định resource ownership và semantics kết nối. Shallow clone có thể share cùng socket.

**Câu 15.** Một class immutable chỉ giữ Strings cần deep-copy Strings không?

*Đáp án:* Thường không; Strings immutable nên share reference an toàn theo content.

**Câu 16.** Có thể định nghĩa interface `Copyable<T>` với `T copy()` để hỗ trợ polymorphic copies không?

*Đáp án:* Có. Đó là contract ứng dụng tự thiết kế, không phải cơ chế tự động từ Cloneable.

**Câu 17.** `ArrayList.clone()` copy elements sâu không?

*Đáp án:* Không. Sao chép list structure shallow theo API.

**Câu 18.** Nếu copy constructor tạo object mới nhưng `equals` false, có phải sao chép sai không?

*Đáp án:* Chưa chắc. Có thể class dùng identity equality mặc định; kiểm copy contract và observable state riêng.

**Câu 19.** Hai objects có cùng hash codes có nhất thiết là same reference không?

*Đáp án:* Không. Hash collisions hợp lệ.

**Câu 20.** Nếu source graph có cycles hoặc shared child, deep copying cần thêm điều gì?

*Đáp án:* Một chính sách graph-copy và cơ chế ghi nhớ đã-copy nodes, thường theo reference identity, để xử lý cycles/sharing.

---

**Ghi nhớ cuối bài:** **Sao chép tường minh** bằng copy constructor, factory hoặc method `copy()` cho phép bạn tự quyết định constructor validation, fields, mức độ copy sâu, xử lý `final`, subtype và resource ownership. **`Object.clone()`** là protected method của Object với contract `Cloneable` và checked exception; implementation gốc tạo **shallow field copy** mà **không gọi constructor**. Mảng có `clone()` công khai nhưng cũng chỉ shallow khi elements là references; mảng nhiều chiều cần copy các inner arrays. Dù chọn cách nào, hãy kiểm **object identity, state equality, mutable alias isolation, runtime subtype và vòng đời tài nguyên** như các tiêu chí riêng. Với Java code mới cần maintainability và invariants rõ, **copy tường minh thường là lựa chọn dễ suy luận hơn**; dùng clone khi thực sự hiểu và cần hợp đồng của nó.