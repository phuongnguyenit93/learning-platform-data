# Thứ tự thực thi bộ khởi tạo trường, khối khởi tạo và chuỗi hàm khởi tạo

## 1. Mục tiêu và bối cảnh Java 25

Khi tạo một đối tượng Java, nhiều thành phần có thể tham gia vào quá trình khởi tạo: giá trị mặc định của trường, bộ khởi tạo trường (*instance field initializer*), khối khởi tạo instance (*instance initializer block*), constructor của lớp cha, constructor của lớp con và lời gọi ủy quyền `this(...)`. Chỉ cần hiểu sai một mắt xích, chương trình có thể đọc trạng thái chưa sẵn sàng, ghi đè giá trị hoặc gọi nhầm logic trong constructor.

**Java 25 hoàn thiện Flexible Constructor Bodies (JEP 513)**, cho phép đặt một số câu lệnh trước lời gọi constructor tường minh `super(...)` hay `this(...)`. Điều này mở thêm khả năng kiểm tra đối số, chuẩn bị giá trị và, trong điều kiện ngôn ngữ cho phép, **gán trực tiếp trường của đối tượng đang được tạo trước khi gọi constructor cha**. Nhưng tính năng mới **không** đảo ngược trình tự khởi tạo cơ bản của Java. <https://openjdk.org/jeps/513>

Bài học thuộc chương **Hàm khởi tạo linh hoạt** của `JAVA_VERSION_JAVA25` và tập trung đúng đề bài: **“Thứ tự thực thi bộ khởi tạo trường, khối khởi tạo và chuỗi hàm khởi tạo”**. Chỉ xét cơ chế hiện vẫn áp dụng trong Java hiện đại; không dùng kỹ thuật legacy như `finalize()` hay các workaround truy cập internals để điều khiển vòng đời đối tượng.

### Sau bài học, bạn có thể

1. Mô tả thứ tự tạo object theo Java Language Specification (JLS) mục 12.5.
2. Dự đoán chính xác output khi có lớp cha/lớp con, field initializers, instance blocks và constructor prologue/epilogue.
3. Phân biệt luồng `super(...)` với `this(...)`, tránh hiểu nhầm khối khởi tạo chạy nhiều lần.
4. Giải thích vì sao gán trường trong prologue có thể được constructor cha quan sát, và vì sao field initializer có thể ghi đè giá trị đã gán sớm.
5. Xác định những thao tác bị cấm trong *early construction context*.
6. Thiết kế kiểm thử bảo vệ thứ tự thực thi và các bất biến của đối tượng khi nâng JDK.

## 2. Trạng thái chính thức: JEP 513 đã final ở Java 25

| Mốc | Ý nghĩa |
| --- | --- |
| Java 22–24 | Các phiên bản preview của ý tưởng constructor body linh hoạt |
| **Java 25 / JEP 513** | **Final**, cú pháp và quy tắc được đưa vào ngôn ngữ chính thức |
| JDK mới hơn | Phải kiểm tra tài liệu đúng JDK đang sử dụng, nhưng không coi JEP 513 của Java 25 là tính năng preview |

Ví dụ Java 25 hợp lệ:

~~~java
class Base {
    Base(int value) {
        System.out.println("Base: " + value);
    }
}

class Child extends Base {
    Child(String text) {
        String value = text.strip();              // prologue
        if (value.isEmpty()) {
            throw new IllegalArgumentException("empty");
        }
        super(Integer.parseInt(value));           // constructor cha
        System.out.println("Child constructed"); // epilogue
    }
}
~~~

Phần nằm trước `super(...)` là **prologue**; phần nằm sau nó là **epilogue**. Đối số `text` được xử lý bằng biến cục bộ, không đọc trạng thái `this` khi superclass chưa được khởi tạo.

Biên dịch ví dụ với compiler JDK 25 và mức release tương ứng:

~~~bash
javac --release 25 Child.java
~~~

Đoạn code ở trên mô tả class minh họa nhưng lệnh giả định nội dung đã được lưu vào `Child.java` cùng lớp `Base` không public. Với JEP 513 **không cần `--enable-preview`** trên Java 25. Nếu dự án vẫn dùng `--release 21` thì không thể viết dạng prologue trước `super(...)` trong source mức 21.

## 3. Phân biệt các cơ chế “khởi tạo” thường bị trộn lẫn

| Thành phần | Khi nào chạy | Tần suất điển hình |
| --- | --- | --- |
| Giá trị mặc định của instance field | Ngay sau khi cấp bộ nhớ cho object, trước khi chạy constructor | Một lần cho lần tạo đối tượng |
| `static` field initializer / static block | Khi **class** được JVM khởi tạo, theo quy tắc `12.4` | Thường một lần trong mỗi class loader tương ứng |
| Constructor prologue của `C` | Trước lời gọi `super(...)` hoặc `this(...)` tường minh trong constructor `C` | Khi constructor đó được thực thi |
| Constructor cha | Theo chuỗi superclass, sau prologue của constructor gọi nó | Một chuỗi đi tới `Object` |
| Instance field initializer của `C` | Sau khi constructor cha trả về thành công, theo thứ tự khai báo trong source | Một lần cho một đối tượng `C` trên đường `super` |
| Instance initializer block của `C` | Xen kẽ field initializers theo thứ tự xuất hiện trong source | Một lần trên đường khởi tạo `C` |
| Constructor epilogue của `C` | Sau instance initializers của `C` (nếu đi qua `super`), hoặc sau delegated constructor (nếu đi qua `this`) | Khi constructor đó hoàn tất chặng gọi trước |

**Lưu ý:** *khởi tạo class* (`static`) khác *khởi tạo instance*. Một field có `static` không trở thành instance initializer. Một field không gắn initializer nguồn (ví dụ `int count;`) vẫn nhận giá trị mặc định trước mọi constructor.

### Giá trị mặc định trước mọi code khởi tạo instance

| Kiểu field | Giá trị mặc định |
| --- | --- |
| `boolean` | `false` |
| `byte`, `short`, `int`, `long` | `0` tương ứng kiểu |
| `float`, `double` | `0.0` tương ứng kiểu |
| `char` | `'\u0000'` |
| Mọi kiểu tham chiếu | `null` |

Các giá trị này đã tồn tại **trước khi prologue đầu tiên thực thi**. Nhưng chúng không phải giá trị cuối cùng nếu constructor, instance block hoặc field initializer sẽ gán lại.

## 4. Thuật toán khởi tạo instance theo JLS Java SE 25, mục 12.5

JLS mục 12.5 xác định trình tự xử lý constructor. Có thể ghi nhớ theo các bước logic dưới đây, với điều kiện mọi bước hoàn tất bình thường:

1. JVM cấp bộ nhớ cho object và các trường của **toàn bộ lớp trong cây kế thừa** nhận giá trị mặc định. Nếu class chưa được khởi tạo tĩnh, JVM thực hiện class initialization theo quy tắc riêng.
2. Tạo các biến tham số của constructor được gọi.
3. Nếu constructor có lời gọi `super(...)` hoặc `this(...)` tường minh, thực thi **prologue** trước.
4. Đánh giá đối số và thực hiện lời gọi constructor tường minh.
5. Nếu constructor gọi `this(...)`, xử lý constructor đích trước, rồi **chuyển thẳng tới epilogue của constructor ủy quyền**; không chạy lại field initializers/instance blocks của cùng lớp.
6. Nếu constructor gọi `super(...)` (hoặc không viết lời gọi và được chèn `super()` ngầm định), khởi tạo constructor cha trước; sau khi nó trả về, chạy **instance field initializers và instance blocks** của lớp hiện tại theo **thứ tự xuất hiện trong source**.
7. Thực thi **epilogue** của constructor hiện tại.

Các bước 3–7 lặp đệ quy qua chuỗi constructor. Điều quan trọng là **prologue lớp con có thể chạy trước constructor cha**, nhưng các **instance initializers của lớp con chỉ chạy sau khi superclass constructor hoàn tất**. Đây là khác biệt cần nắm để không đọc sai output.

~~~mermaid
flowchart TD
    A["Cấp object và đặt default values"] --> P["Constructor hiện tại: prologue nếu có"]
    P --> Q{"Lời gọi constructor?"}
    Q -->|super hoặc ngầm định super| S["Chạy constructor superclass"]
    S --> I["Field initializers + instance blocks của class hiện tại theo thứ tự source"]
    I --> E["Epilogue constructor hiện tại"]
    Q -->|this| T["Chạy constructor khác trong cùng class"]
    T --> E
    E --> D["Constructor hiện tại hoàn tất"]
~~~

Sơ đồ rút gọn bỏ qua nhánh exception; nếu một bước ném exception, các bước còn lại của đường đó không được chạy.

Nguồn đặc tả: [JLS Java SE 25 — mục 12.5 Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.5).

## 5. Ví dụ chuẩn: lớp cha, field initializer và instance block

Lưu toàn bộ ví dụ vào `ConstructorOrderDemo.java`:

~~~java
public class ConstructorOrderDemo {

    static void mark(String event) {
        System.out.println(event);
    }

    static int mark(String event, int value) {
        mark(event);
        return value;
    }

    static class Parent {
        int parentValue = mark("P1 field", 10);

        {
            mark("P2 instance block");
        }

        Parent(String name) {
            mark("P3 constructor: " + name);
        }
    }

    static class Child extends Parent {
        int childValue1 = mark("C1 field #1", 20);

        {
            mark("C2 instance block");
        }

        int childValue2 = mark("C3 field #2", 30);

        Child(String raw) {
            String normalized = raw.strip();
            mark("C0 prologue");
            super(normalized);
            mark("C4 epilogue");
        }
    }

    public static void main(String[] args) {
        new Child(" demo ");
    }
}
~~~

Chạy bằng JDK 25:

~~~bash
javac --release 25 ConstructorOrderDemo.java
java ConstructorOrderDemo
~~~

**Output có thứ tự xác định:**

~~~text
C0 prologue
P1 field
P2 instance block
P3 constructor: demo
C1 field #1
C2 instance block
C3 field #2
C4 epilogue
~~~

### Đọc output từng bước

1. `Child` có constructor prologue, nên `C0` in **trước** lời gọi `super(normalized)`.
2. `Parent` không có lời gọi `super(...)` tường minh; JVM xử lý `Object()` ngầm định, rồi khởi tạo `parentValue`, chạy instance block và phần thân constructor `Parent`.
3. Khi `Parent` hoàn tất, các instance initializers của `Child` được chạy **theo đúng thứ tự xuất hiện trong mã nguồn**: `childValue1` → block → `childValue2`.
4. Cuối cùng constructor epilogue `Child` mới in `C4`.

**Không có quy tắc “tất cả field initializers trước, tất cả instance blocks sau”.** Field initializer và instance block được **xen kẽ** theo thứ tự khai báo.

### Nếu đổi vị trí trong source thì sao?

Nếu chuyển block `C2` lên trước khai báo `childValue1`, thì trong output `C2` sẽ chạy trước `C1`, dù cả hai vẫn xảy ra sau khi `Parent` hoàn thành. Ngược lại, di chuyển vị trí khai báo constructor trong class nhưng giữ nguyên thứ tự fields/blocks không làm thay đổi thứ tự của chúng.

## 6. Field initializer và instance block: giống và khác nhau

Một field initializer là biểu thức trực tiếp gắn vào khai báo:

~~~java
int retryLimit = computeDefault();
~~~

Một instance initializer block là khối câu lệnh độc lập trong thân class:

~~~java
{
    auditInitialization();
    retryLimit = Math.max(retryLimit, 1);
}
~~~

Hai loại initializer có các thuộc tính chung:

- Chạy trong phần **instance initialization** của class, sau superclass constructor.
- Chạy theo **thứ tự văn bản** khi xen kẽ trong class body.
- Có thể gây side effect hoặc exception; tránh phụ thuộc external I/O không cần thiết.
- Không được thực thi thêm lần thứ hai chỉ vì có constructor `this(...)` ủy quyền.
- Không phải nơi an toàn để xuất bản `this` sang thread/registry bên ngoài khi object chưa hoàn tất.

Nhưng chúng khác về cách thể hiện. Field initializer thường phù hợp với giá trị mặc định đơn giản; instance block có thể làm nhiều câu lệnh. Trong code doanh nghiệp hiện đại, nếu logic khởi tạo phức tạp phụ thuộc vào tham số, **constructor hoặc factory** thường rõ ràng hơn instance block vì block không nhận trực tiếp tham số của constructor.

### Thí nghiệm thay đổi thứ tự khai báo

~~~java
class Interleaved {
    int a = log("field a", 1);

    {
        log("block 1");
    }

    int b = log("field b", 2);

    {
        log("block 2");
    }

    Interleaved() {
        System.out.println("constructor epilogue");
    }

    static int log(String event, int value) {
        System.out.println(event);
        return value;
    }

    static void log(String event) {
        System.out.println(event);
    }
}
~~~

Với `new Interleaved()`, output là:

~~~text
field a
block 1
field b
block 2
constructor epilogue
~~~

Không có prologue tường minh ở đây; lời gọi `super()` ngầm định của `Object` xảy ra trước `field a` và không in gì.

## 7. Chuỗi kế thừa nhiều cấp: prologue có thể đi trước cha và ông

Khi `Leaf extends Middle extends Root`, logic **constructor prologue** khác với **instance initialization**. Ví dụ:

~~~java
class Root {
    int rootField = log("R1 Root field", 1);

    Root() {
        log("R2 Root constructor");
    }

    static int log(String s, int v) {
        System.out.println(s);
        return v;
    }

    static void log(String s) {
        System.out.println(s);
    }
}

class Middle extends Root {
    int middleField = log("M1 Middle field", 2);

    Middle() {
        log("M0 Middle prologue");
        super();
        log("M2 Middle epilogue");
    }
}

class Leaf extends Middle {
    int leafField = log("L1 Leaf field", 3);

    Leaf() {
        log("L0 Leaf prologue");
        super();
        log("L2 Leaf epilogue");
    }
}

class ThreeLevelsDemo {
    public static void main(String[] args) {
        new Leaf();
    }
}
~~~

Output:

~~~text
L0 Leaf prologue
M0 Middle prologue
R1 Root field
R2 Root constructor
M1 Middle field
M2 Middle epilogue
L1 Leaf field
L2 Leaf epilogue
~~~

Suy ra:

- **Prologue** đi theo chiều tiến sâu vào constructor cha: Leaf → Middle → Root.
- **Field/block initializers và epilogue** hoàn tất theo chiều quay về: Root → Middle → Leaf.
- Không có “bước khởi tạo tất cả field của Leaf” trước Root, trừ các **phép gán trực tiếp hợp lệ** mà chính Leaf cố ý làm trong prologue; trường hợp đặc biệt này được học ở phần sau.

Mỗi constructor trong chuỗi cũng có thể ném exception. Khi một constructor cha thất bại, các instance initializers và epilogue của lớp con chưa thực thi sẽ không được chạy.

## 8. `this(...)`: ủy quyền constructor không nhân đôi instance initializers

Một class có nhiều constructor thường dùng `this(...)` để tập trung việc khởi tạo về một constructor chính. Trong Java 25, constructor ủy quyền cũng có thể có **prologue trước `this(...)`**.

Lưu `ConstructorDelegationDemo.java`:

~~~java
public class ConstructorDelegationDemo {

    String label = note("F field initializer", "default");

    {
        System.out.println("I instance block");
    }

    ConstructorDelegationDemo() {
        System.out.println("A prologue before this");
        this("chosen");
        System.out.println("A epilogue after this");
    }

    ConstructorDelegationDemo(String value) {
        System.out.println("B prologue before super");
        super();
        System.out.println("B epilogue after super: " + value);
    }

    static String note(String event, String value) {
        System.out.println(event);
        return value;
    }

    public static void main(String[] args) {
        new ConstructorDelegationDemo();
    }
}
~~~

Output:

~~~text
A prologue before this
B prologue before super
F field initializer
I instance block
B epilogue after super: chosen
A epilogue after this
~~~

Tại sao `F` và `I` chỉ in một lần?

1. Constructor không tham số chạy prologue `A`.
2. `this("chosen")` gọi constructor nhận `String`, chạy prologue `B`.
3. Constructor nhận `String` gọi `super()`, sau khi superclass hoàn thành mới chạy field initializer `F` và instance block `I` của class hiện tại.
4. Constructor nhận `String` hoàn thành epilogue `B`.
5. Quay lại constructor không tham số, chỉ chạy epilogue `A`. **Nó không chạy lại `F` hoặc `I`**.

Điểm dễ nhầm: quy tắc “một lần mỗi object” áp dụng cho instance initializers **của class** trong một constructor chain thành công, không có nghĩa mỗi constructor được gọi sẽ tự chạy cùng các initializers đó.

## 9. Chuỗi `this(...)` sâu hơn và điều kiện kết thúc

Một chuỗi constructor trong cùng class có thể kéo dài:

~~~java
class Chained {
    int version = log("initializer", 1);

    Chained() {
        System.out.println("A prologue");
        this(5);
        System.out.println("A epilogue");
    }

    Chained(int input) {
        int prepared = Math.max(input, 1);
        System.out.println("B prologue");
        this(prepared, "source");
        System.out.println("B epilogue");
    }

    Chained(int value, String origin) {
        System.out.println("C prologue");
        super();
        System.out.println("C epilogue: " + value + ", " + origin);
    }

    static int log(String name, int value) {
        System.out.println(name);
        return value;
    }
}
~~~

Đối với `new Chained()`, trình tự là:

~~~text
A prologue
B prologue
C prologue
initializer
C epilogue: 5, source
B epilogue
A epilogue
~~~

Một chuỗi `this(...)` **cuối cùng phải tới constructor khởi tạo superclass**, tường minh hoặc ngầm định. Java cấm vòng lặp constructor ủy quyền trực tiếp hoặc gián tiếp:

~~~java
// SAI, không biên dịch: chuỗi this(...) quay lại chính nó.
class Loop {
    Loop() {
        this(1);
    }

    Loop(int number) {
        this();
    }
}
~~~

Cũng không được viết hai lời gọi constructor trong cùng một constructor body (chẳng hạn vừa `this(...)` vừa `super(...)`). Cú pháp Java 25 vẫn cho phép **tối đa một** lời gọi constructor tường minh, nằm trong cấu trúc của constructor body, không phải tùy ý đặt vào hai nhánh `if`.

## 10. Gán trường trong prologue trước `super(...)`: lợi ích và giới hạn

Java 25 cho phép **gán trực tiếp một trường instance của lớp đang xây dựng** trước lời gọi `super(...)` theo quy tắc early construction. Đây không chỉ là khả năng kiểm tra tham số; nó còn cho phép một số trạng thái của subclass sẵn sàng trước khi superclass constructor chạy.

~~~java
class Parent {
    Parent() {
        show(); // Không phải thiết kế tốt: gọi method có thể override.
    }

    void show() {
        System.out.println("Parent");
    }
}

class PreparedChild extends Parent {
    private final int number;

    PreparedChild(int number) {
        this.number = number; // Gán blank final field của lớp hiện tại.
        super();
    }

    @Override
    void show() {
        System.out.println("number = " + number);
    }
}

class EarlyWriteDemo {
    public static void main(String[] args) {
        PreparedChild result = new PreparedChild(42);
        result.show();
    }
}
~~~

Output:

~~~text
number = 42
number = 42
~~~

**Giải thích:** trước khi gọi `Parent()`, prologue `PreparedChild(int)` gán field `number`. Constructor Parent gọi `show()`; Java dùng dynamic dispatch nên chạy `PreparedChild.show()` và quan sát 42.

Cần phân biệt phép **gán đơn giản** `this.number = number;` với đọc `this.number` hoặc `this.number++`, vốn bị hạn chế trong early construction context.

**Cảnh báo thiết kế:** superclass gọi phương thức có thể bị override từ constructor vẫn tiềm ẩn lỗi, bởi những trường khác của lớp con chưa chắc được khởi tạo. Không lạm dụng tính năng gán sớm để hợp thức hóa việc gửi `this` sang thread, callback hay registry trong lúc tạo object. Cách an toàn hơn là không gọi overridable methods trong constructor cha, trừ khi kiến trúc đã được kiểm soát kỹ.

Nguồn: [JLS Java SE 25 — mục 12.5 Example 12.5-3](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.5).

## 11. Cạm bẫy: field initializer có thể ghi đè giá trị prologue

Câu hỏi: nếu prologue gán `counter=7` trước `super()`, nhưng class còn có `int counter=100;` thì giá trị cuối là bao nhiêu?

~~~java
class BaseCounter {
    BaseCounter() {
        System.out.println("Base sees: " + readCounter());
    }

    int readCounter() {
        return -1;
    }
}

class CounterChild extends BaseCounter {
    int counter = 100;

    CounterChild() {
        counter = 7; // Prologue, trước BaseCounter().
        super();
        System.out.println("Child sees: " + counter);
    }

    @Override
    int readCounter() {
        return counter;
    }
}

class OverwriteDemo {
    public static void main(String[] args) {
        new CounterChild();
    }
}
~~~

Output:

~~~text
Base sees: 7
Child sees: 100
~~~

Trình tự: default `counter=0` → prologue gán 7 → Base đọc 7 → Base hoàn tất → **field initializer của Child gán 100** → Child epilogue đọc 100.

Đây là ví dụ cốt lõi: **lệnh gán trong prologue không xóa hoặc làm chạy sớm field initializer theo source**. Nếu muốn field giữ đúng giá trị gán sớm, đừng đặt một initializer khác sẽ ghi đè nó. Với blank `final` field, không khai báo initializer nguồn khác nếu constructor dự định gán trong prologue.

## 12. Early construction context: thao tác được phép và bị cấm

Early construction context gồm prologue và biểu thức đối số trong `super(...)` / `this(...)`. Java 25 cho phép:

- Đọc tham số constructor và biến cục bộ đã được khởi tạo.
- Gọi static methods, sử dụng static constants theo quy tắc truy cập thông thường.
- Tính toán, chuẩn hóa dữ liệu và kiểm tra/throw exception trước superclass constructor.
- Gán **đơn giản** cho instance fields được khai báo trong lớp hiện tại, tuân thủ definite assignment.
- Gọi constructor tường minh đúng một lần ngoài các nhánh điều kiện, theo cấu trúc constructor body.

Ví dụ:

~~~java
class CheckedParent {
    CheckedParent(int capacity) {
        System.out.println("capacity = " + capacity);
    }
}

class CheckedChild extends CheckedParent {
    final int capacity;

    CheckedChild(String raw) {
        int value = Integer.parseInt(raw.strip());
        if (value <= 0) {
            throw new IllegalArgumentException("capacity must be positive");
        }

        this.capacity = value;
        super(value);
    }
}
~~~

Với `new CheckedChild(" 16 ")`, constructor cha thấy 16. Nếu input không hợp lệ, exception xảy ra trước khi gọi cha.

Các thao tác **không hợp lệ** khi tham chiếu instance chưa hoàn thành giai đoạn bắt buộc:

~~~java
// ĐOẠN CỐ TÌNH SAI: không dùng để biên dịch.
class InvalidChild extends CheckedParent {
    int points;

    InvalidChild(int value) {
        System.out.println(this);        // Không được sử dụng this.
        System.out.println(this.points); // Không được đọc field.
        this.points++;                   // ++ phải đọc giá trị cũ.
        inspect();                       // Không được gọi instance method.
        super(value);
    }

    void inspect() { }
}
~~~

Cấm này cũng áp dụng cho những cú pháp đọc instance field **không viết tường minh `this`**. Ngược lại, nếu tên đó chỉ một biến cục bộ hoặc tham số, việc đọc hợp lệ.

| Biểu thức trong prologue | Trạng thái | Vì sao |
| --- | --- | --- |
| `int n = Math.max(input, 1);` | Hợp lệ | Chỉ dùng tham số và static method |
| `this.points = input;` | Hợp lệ khi đúng quy tắc | Gán đơn giản field của lớp hiện tại |
| `System.out.println(this.points);` | Không hợp lệ | Đọc field chưa được phép |
| `this.points += 1;` | Không hợp lệ | Compound assignment cần đọc giá trị cũ |
| `this.points++;` | Không hợp lệ | Increment cần đọc giá trị cũ |
| `this.inspect();` | Không hợp lệ | Gọi instance method |
| `System.out.println(this);` | Không hợp lệ | Tham chiếu object đang tạo |
| `super.toString();` | Không hợp lệ | Truy cập superclass instance trước constructor |

Các trường hợp nested classes hoặc field hiding có quy tắc bổ sung; khi nghi ngờ, biên dịch riêng một ví dụ tối thiểu trên `javac --release 25`.

## 13. Blank `final` field và definite assignment

Một blank `final` instance field không có biểu thức khởi tạo tại khai báo:

~~~java
final int capacity;
~~~

Java yêu cầu field cuối cùng được gán đúng theo quy tắc *definite assignment*, và phép gán chỉ hợp lệ khi field còn *definitely unassigned* ở vị trí đó.

Một trường hợp hợp lệ:

~~~java
class ValidFinalChild extends CheckedParent {
    final int capacity;

    ValidFinalChild(int value) {
        if (value <= 0) {
            throw new IllegalArgumentException("invalid capacity");
        }

        this.capacity = value;
        super(value);
    }
}
~~~

Một trường hợp **sai**:

~~~java
// KHÔNG BIÊN DỊCH: final field được gán hai lần.
class InvalidFinalChild extends CheckedParent {
    final int capacity = 10;

    InvalidFinalChild(int value) {
        this.capacity = value;
        super(value);
    }
}
~~~

Đối với chuỗi `this(...)`, nên tập trung logic gán các blank final fields ở constructor đích kết thúc chuỗi và gọi `super(...)`, thay vì rải các phép gán sớm trong nhiều constructor ủy quyền. Compiler kiểm tra definite assignment qua tất cả đường đi, kể cả khi có nhánh exception.

Ví dụ có trách nhiệm rõ:

~~~java
class ConfigValue {
    final String key;

    ConfigValue() {
        this("default");
    }

    ConfigValue(String raw) {
        String normalized = raw.strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("blank key");
        }

        this.key = normalized;
        super();
    }
}
~~~

## 14. Không viết `super(...)` vẫn có lời gọi ngầm định

Nếu một constructor thông thường **không chứa** `super(...)` hay `this(...)` tường minh, Java chèn `super()` ngầm định **trước phần thân constructor**. Lúc này, các statements trong body là epilogue, không phải prologue.

~~~java
class DefaultBase {
    DefaultBase() {
        System.out.println("Base constructor");
    }
}

class DefaultChild extends DefaultBase {
    int x = log("Child field", 10);

    DefaultChild() {
        System.out.println("Child constructor body");
    }

    static int log(String label, int value) {
        System.out.println(label);
        return value;
    }
}
~~~

Với `new DefaultChild()`:

~~~text
Base constructor
Child field
Child constructor body
~~~

**Không kết luận:** vì Java 25 cho phép câu lệnh trước `super()`, nên mọi câu lệnh ở đầu constructor tự động chạy trước constructor cha. Nếu không có lời gọi tường minh, constructor body chạy **sau** lời gọi `super()` ngầm định và instance initializers.

Việc chuyển logic validation từ epilogue sang prologue bằng cách thêm `super()` tường minh có thể **thay đổi thời điểm side effects và exceptions**. Đây là thay đổi hành vi, không phải điều chỉnh phong cách code thuần túy.

## 15. Khi có exception, thứ tự dừng ở đâu?

JLS yêu cầu dừng quá trình khởi tạo khi một bước kết thúc bất thường:

| Lỗi xảy ra tại | Bước tiếp theo bị bỏ qua |
| --- | --- |
| Prologue của constructor con | Lời gọi `super(...)`/`this(...)` và phần còn lại |
| Biểu thức đối số của `super(...)` | Constructor cha chưa chạy nếu đánh giá đối số đã lỗi |
| Constructor cha | Field/block initializers và epilogue chưa tới của lớp con |
| Một field initializer | Các initializers sau nó và epilogue không chạy |
| Một instance initializer block | Các initializers sau nó và epilogue không chạy |
| Constructor đích của `this(...)` | Epilogue của constructor ủy quyền không chạy |
| Constructor epilogue | Việc tạo object không trả về bình thường |

Ví dụ:

~~~java
class ValidatingParent {
    ValidatingParent() {
        System.out.println("parent");
    }
}

class ValidatingChild extends ValidatingParent {
    int field = trace("child field", 1);

    ValidatingChild(int input) {
        if (input < 0) {
            throw new IllegalArgumentException("negative");
        }

        System.out.println("child prologue");
        super();
        System.out.println("child epilogue");
    }

    static int trace(String message, int value) {
        System.out.println(message);
        return value;
    }
}
~~~

Với `new ValidatingChild(-1)`, exception ở prologue có nghĩa `ValidatingParent()` chưa in gì, field initializer và epilogue của Child chưa chạy. Với input hợp lệ, output là: `child prologue` → `parent` → `child field` → `child epilogue`.

**Exception không rollback các side effects đã xảy ra.** Nếu một prologue ghi file, gọi network hoặc cập nhật biến static rồi throw, tác động đó có thể còn tồn tại dù object creation thất bại. Vì vậy, prologue thường nên ưu tiên validation và tính toán không có side effect.

## 16. Static initialization không phải instance initialization

Static field initializers và static blocks thuộc **class initialization** (JLS mục 12.4), thường chạy một lần cho class identity của một class loader. Instance initializers và constructors chạy mỗi lần tạo một object.

~~~java
public class StaticAndInstanceDemo {
    static class Parent {
        static { System.out.println("Parent static"); }

        { System.out.println("Parent instance block"); }

        Parent() { System.out.println("Parent constructor"); }
    }

    static class Child extends Parent {
        static { System.out.println("Child static"); }

        { System.out.println("Child instance block"); }

        Child() { System.out.println("Child constructor"); }
    }

    public static void main(String[] args) {
        new Child();
        System.out.println("--- another object ---");
        new Child();
    }
}
~~~

Output khi các class chưa được chủ động khởi tạo trước đó:

~~~text
Parent static
Child static
Parent instance block
Parent constructor
Child instance block
Child constructor
--- another object ---
Parent instance block
Parent constructor
Child instance block
Child constructor
~~~

Static blocks chạy một lần; instance blocks/constructors chạy cho từng lần `new`. Đừng suy ra rằng một class trong ứng dụng thực tế chỉ được khởi tạo tĩnh đúng một lần trên mọi class loader/reload scenario. Không nên dùng static initializer để thay logic construction của từng entity.

## 17. Những trường hợp đặc biệt: record và constructor ủy quyền

### 17.1. Record không có `super(...)` do lập trình viên khai báo

Record kế thừa trực tiếp từ `java.lang.Record`. Với record, Java áp dụng các quy tắc constructor riêng:

- **Canonical constructor** (hoặc compact canonical constructor) chịu trách nhiệm khởi tạo record components. Không viết lời gọi `super(...)` tường minh trong constructor của record.
- **Noncanonical constructor** phải ủy quyền đến constructor khác của cùng record bằng `this(...)` theo quy tắc record, và Java 25 cho phép một số câu lệnh prologue trước lời gọi này.
- Record components là dữ liệu bất biến theo mô hình record; không dùng mẹo gán instance field trước `super(...)` của normal class để sửa contract của record.

Ví dụ Java 25:

~~~java
record Size(int width, int height) {
    Size(int side) {
        if (side <= 0) {
            throw new IllegalArgumentException("side must be positive");
        }

        this(side, side);
    }
}

class SizeDemo {
    public static void main(String[] args) {
        System.out.println(new Size(4));
    }
}
~~~

Output:

~~~text
Size[width=4, height=4]
~~~

`Size(int side)` chạy validation trước `this(side, side)`, rồi **canonical constructor** hoàn tất việc gán components. Record là cơ chế hiện đại đang được hỗ trợ; ví dụ không dùng cú pháp preview.

### 17.2. Không lẫn constructor chain với vòng đời framework

Một số thư viện dùng reflection, dependency injection, proxies hoặc serialization khi tạo đối tượng. Thứ tự field initializers, blocks và Java constructors nêu ở đây áp dụng cho **quá trình gọi constructor theo ngôn ngữ Java**; đừng tự suy ra mọi framework đều gọi constructor/đường instantiation giống nhau.

Ví dụ với Spring, bước chạy constructor không đồng nghĩa bean đã hoàn thành dependency injection, `@PostConstruct` hoặc lifecycle callbacks. Với JPA, proxy và loading entity có thể chịu quy tắc framework. Khi chẩn đoán framework, xem vòng đời chính thức của framework thay vì kỳ vọng mọi bước cấu hình đều nằm trong Java constructor.

## 18. Kiểm thử tự động thứ tự khởi tạo bằng event log

Dùng một chương trình duy nhất với JDK 25; nó không phụ thuộc framework bên ngoài. Thay vì chỉ nhìn `System.out` rồi suy đoán, lưu **chuỗi sự kiện** và so sánh với giá trị kỳ vọng.

Tạo `ConstructorOrderAssertions.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ConstructorOrderAssertions {
    private static final List<String> EVENTS = new ArrayList<>();

    static void mark(String value) {
        EVENTS.add(value);
    }

    static int mark(String label, int value) {
        mark(label);
        return value;
    }

    static class Parent {
        int value = mark("parent.field", 1);

        {
            mark("parent.block");
        }

        Parent(String name) {
            mark("parent.constructor");
        }
    }

    static class Child extends Parent {
        int left = mark("child.field.left", 2);

        {
            mark("child.block");
        }

        int right = mark("child.field.right", 3);

        Child(String input) {
            String normalized = input.strip();
            mark("child.prologue");
            super(normalized);
            mark("child.epilogue");
        }
    }

    public static void main(String[] args) {
        Child child = new Child(" example ");

        List<String> expected = List.of(
            "child.prologue",
            "parent.field",
            "parent.block",
            "parent.constructor",
            "child.field.left",
            "child.block",
            "child.field.right",
            "child.epilogue"
        );

        if (!EVENTS.equals(expected)) {
            throw new AssertionError(
                "Expected: " + expected + ", actual: " + EVENTS);
        }

        if (child.value != 1 || child.left != 2 || child.right != 3) {
            throw new AssertionError("Unexpected field values");
        }

        System.out.println("PASS: " + EVENTS);
    }
}
~~~

Chạy:

~~~bash
javac --release 25 ConstructorOrderAssertions.java
java ConstructorOrderAssertions
~~~

Đầu ra mong đợi:

~~~text
PASS: [child.prologue, parent.field, parent.block, parent.constructor, child.field.left, child.block, child.field.right, child.epilogue]
~~~

Điểm mạnh của phép kiểm tra là đối chiếu được **hai điều độc lập**: thứ tự side effects và giá trị field sau khi object tạo xong. Có thể đổi thứ tự khai báo field/block hoặc thay `Child` bằng chuỗi `this(...)` để thử các đường khởi tạo khác.

Không ghi chép side effects quan trọng bằng event log toàn cục trong ứng dụng production chỉ để “theo dõi constructor”. Trong ví dụ này, event log chỉ dùng cho test một luồng; nếu test chạy song song cần thiết kế recorder phù hợp.

### Thử nghiệm âm tính (compiler phải từ chối)

Tạo một tệp thử riêng, lần lượt thêm từng hành vi sai vào prologue:

- Đọc `this.field`.
- Gọi instance method không có receiver tường minh.
- Sử dụng `this` để tạo callback.
- Compound assignment `this.field += 1`.
- Gán lại blank final field hai lần.
- Tạo vòng lặp constructor `this(...)`.

Gọi `javac --release 25`, ghi lại thông báo lỗi. **Không đưa các đoạn code cố tình không biên dịch vào cùng file** với bài kiểm thử thành công, vì chúng sẽ làm toàn bộ bài lab thất bại.

## 19. Các lỗi tư duy phổ biến và cách sửa

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Java 25 cho phép chạy mọi thứ trước `super()`.” | Chỉ các câu lệnh hợp lệ trong early construction context, không tùy ý sử dụng instance |
| “`super()` luôn là câu lệnh đầu tiên chạy.” | Với lời gọi tường minh, **prologue có thể chạy trước** |
| “Field initializer lớp con chạy trước constructor lớp cha.” | Không, chúng chạy **sau superclass constructor**, dù prologue lớp con có thể chạy trước |
| “Mọi field initializer chạy trước mọi instance block.” | Không, field initializers và instance blocks **xen kẽ theo thứ tự source** |
| “Constructor dùng `this(...)` khởi tạo field thêm một lần.” | Không; delegated constructor thực hiện phần instance initialization tại đường đi xuống `super(...)` |
| “Gán sớm trong prologue luôn là giá trị cuối.” | Không; field initializer phía sau có thể ghi đè |
| “Gọi override trong constructor cha bây giờ an toàn.” | Vẫn rủi ro vì subclass chưa chắc đã có đủ invariant |
| “Không viết `super()` nghĩa là chẳng gọi constructor cha.” | Java chèn `super()` ngầm định khi hợp lệ |
| “Static initializer chạy với mỗi lần `new`.” | Static initialization theo class identity; instance initialization theo object |
| “Exception trong prologue sẽ rollback side effects.” | Exception ngăn bước sau chạy nhưng không tự rollback I/O trước đó |
| “JEP 513 vẫn preview trên Java 25.” | Đã final trong Java 25; không cần `--enable-preview` |

### Một lỗi cụ thể về refactor constructor

Giả sử trước đây code viết:

~~~java
class Service extends BaseService {
    Service(String name) {
        super();
        validate(name); // Gọi instance method sau super.
    }

    void validate(String name) { }
}
~~~

Nếu chuyển thành:

~~~java
// KHÔNG BIÊN DỊCH nếu validate là instance method.
Service(String name) {
    validate(name);
    super();
}
~~~

lỗi không phải do Java 25 chưa hỗ trợ flexible bodies, mà do `validate(name)` tham chiếu instance trong early construction context. Nếu muốn kiểm tra trước constructor cha, dùng phương thức static hoặc logic độc lập object, đồng thời xem xét thay đổi thứ tự side effects.

## 20. Quy tắc thiết kế thực tế cho Java 25

1. **Xác định invariants trước:** trường nào phải có giá trị khi superclass constructor chạy, trường nào phải sẵn sàng sau khi toàn bộ object được tạo.
2. **Giữ prologue ngắn:** validation, chuẩn hóa đối số, chuẩn bị biến cục bộ, và chỉ gán sớm những field thật sự có lý do.
3. **Không để initializer ghi đè âm thầm:** với một field được gán trước `super()`, rà soát initializer của field và instance block liên quan.
4. **Giữ trình tự source dễ đọc:** vì instance blocks xen kẽ field initializers, không rải side effects phức tạp giữa các trường.
5. **Tập trung constructor ủy quyền:** để một constructor chính chịu trách nhiệm gọi superclass và khởi tạo state, các overload chỉ chuẩn bị đối số.
6. **Tránh virtual dispatch từ constructor cha:** không phụ thuộc vào việc mọi subclass field đã sẵn sàng.
7. **Không công bố `this` sớm:** tránh đăng ký listener/callback hoặc khởi tạo thread từ constructor khi object còn chưa xong.
8. **Test đúng thứ tự và failure paths:** unit test hoặc integration test có thể xác nhận thứ tự events và invariants sau khi hoàn tất.
9. **Tách Java semantics khỏi framework lifecycle:** nếu dùng DI, persistence hay proxy, hãy kiểm tra contract của framework.
10. **Không áp dụng cú pháp mới chỉ để đổi format:** khi không có validation trước `super` hoặc không có vấn đề cần gán sớm, constructor kiểu cũ vẫn rõ ràng và hợp lệ trên Java 25.

Flexible constructor bodies **giúp điều khiển rõ thời điểm** validation/gán state, nhưng không tự động tối ưu hóa hiệu năng, giảm allocation hay thay đổi cơ chế class loading. Quyết định áp dụng dựa trên tính đúng đắn và khả năng bảo trì.

## 21. Bài thực hành tự đánh giá

### Bài 1 — Dự đoán output trước khi chạy

Dùng `ConstructorOrderDemo` ở mục 5. Trước khi biên dịch, hãy viết thứ tự từ `C0` đến `C4` và `P1` đến `P3`. Giải thích vì sao `C0` đứng trước `P1` nhưng `C1` đứng sau `P3`.

### Bài 2 — Đổi chỗ instance block

Chuyển block `C2` lên trên field `C1`. Giữ nguyên logic constructor và chạy lại. Chỉ ra thay đổi trong output. Vì sao `P1`, `P2`, `P3` không đổi?

### Bài 3 — Chuỗi `this(...)`

Dự đoán output `new Chained()` ở mục 9. Thử chuyển một câu lệnh `System.out.println` từ prologue vào epilogue của constructor nhận `int`; giải thích vì sao thứ tự thay đổi nhưng field initializer vẫn chạy một lần.

### Bài 4 — Gán field sớm

Chạy `PreparedChild` và `CounterChild`, so sánh:

- `PreparedChild.number` là blank `final`, không bị initializer ghi đè.
- `CounterChild.counter` là mutable field có initializer nguồn, bị gán lại sau constructor cha.

Đề xuất cách sửa tránh việc superclass gọi overridable methods từ constructor.

### Bài 5 — Exception và bất biến

Gọi `new ValidatingChild(-1)` và `new ValidatingChild(1)`. Dự đoán những dòng sẽ được in. Chỉ ra field initializer đã chạy hay chưa trong từng đường đi.

### Bài 6 — Giải thích không dùng feature khi không cần

Cho một class chỉ có constructor `MyConfig(String name) { this.name = name; }`, không cần kiểm tra trước superclass. Hãy lập luận vì sao không nhất thiết thêm prologue/`super()` tường minh.

### Câu hỏi tự kiểm tra

1. Giá trị mặc định của các instance fields xuất hiện trước hay sau prologue?
2. Khi `super()` được viết tường minh sau validation, constructor cha chạy ở bước nào?
3. Trình tự hai instance blocks và hai field initializers được quyết định theo điều gì?
4. Vì sao `new Chained()` không chạy field initializer ba lần?
5. Nếu gán `counter=7` trước `super()` và có `int counter=100;`, giá trị cuối là bao nhiêu?
6. Khi constructor cha gọi method override, nó có thể đọc trạng thái gì của subclass?
7. Trong early construction context, `this.field = value` khác `this.field++` thế nào?
8. Khi nào Java chèn `super()` ngầm định?
9. Có nên gán blank final field ở nhiều constructor ủy quyền không? Vì sao?
10. Nếu field initializer ném exception, epilogue có chạy không?
11. Static initialization và instance initialization khác nhau ở tần suất nào?
12. JEP 513 trong Java 25 còn cần `--enable-preview` không?

## 22. Checklist đọc và review constructor

- [ ] Xác định superclass và các constructor mà `super(...)`/`this(...)` trỏ đến.
- [ ] Tách rõ **prologue**, lời gọi constructor và **epilogue**.
- [ ] Đã nhớ các instance fields bắt đầu với default values.
- [ ] Đã xác định khi nào superclass constructor hoàn tất.
- [ ] Đã liệt kê field initializers + instance blocks theo **thứ tự source**.
- [ ] Với `this(...)`, không cộng thêm một lần instance initialization ngoài constructor đích.
- [ ] Không đọc `this`/instance fields hoặc gọi instance methods trong early context trái quy tắc.
- [ ] Mọi phép gán sớm tới field đều có lý do và không bị field initializer ghi đè ngoài ý muốn.
- [ ] Blank `final` fields đáp ứng definite assignment trên mọi đường constructor.
- [ ] Không có vòng lặp constructor `this(...)`.
- [ ] Không giả định các overridden methods gọi từ superclass constructor là an toàn.
- [ ] Đường exception không bỏ sót cleanup hoặc để lại side effects nguy hiểm.
- [ ] Đã phân biệt static block với instance block.
- [ ] Nếu code cần Java 25 syntax, compiler, `--release` và runtime mục tiêu phù hợp.
- [ ] Bài kiểm thử so sánh cả **thứ tự thực thi** và **state cuối cùng**.
- [ ] Không phụ thuộc vào cơ chế đã legacy như object finalization để hoàn tất khởi tạo.

**Kết luận:** Ở Java 25, constructor prologue có thể chạy **trước** constructor cha, nhưng instance field initializers và instance initializer blocks của lớp con vẫn chạy **sau** khi constructor cha hoàn tất và **theo đúng thứ tự xuất hiện trong source**. Khi `this(...)` ủy quyền, toàn bộ chuỗi cuối cùng đi đến constructor khởi tạo superclass; các instance initializers của cùng class **không chạy lại** ở mỗi constructor ủy quyền. Hiểu rõ ba quy tắc này giúp viết constructor linh hoạt mà vẫn bảo vệ tính nhất quán của đối tượng.

## 23. Tài liệu chuẩn để đối chiếu

- [JEP 513 — Flexible Constructor Bodies](https://openjdk.org/jeps/513): tính năng đã hoàn thiện trong Java 25 và động cơ thiết kế.
- [Java SE 25 Language Guide — Flexible Constructor Bodies](https://docs.oracle.com/en/java/javase/25/language/flexible-constructor-bodies.html): prologue/epilogue, early construction context, gán field trước `super(...)`.
- [JLS Java SE 25 — mục 12.5 Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.5): trình tự thực thi chính thức và ví dụ dynamic dispatch.
- [JLS Java SE 25 — mục 8.8.7 Constructor Body](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.8.7): cú pháp, prologue, epilogue và giới hạn một lời gọi constructor.
- [JLS Java SE 25 — mục 8.8.7.1 Constructor Invocations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.8.7.1): `this(...)`/`super(...)` và early construction context.
- [JLS Java SE 25 — mục 16.9 Definite Assignment, Constructors, and Instance Initializers](https://docs.oracle.com/javase/specs/jls/se25/html/jls-16.html#jls-16.9): gán blank final fields qua các đường constructor.
- [JLS Java SE 25 — mục 12.4 Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4): static initialization khác instance construction.
- [Java SE 25 javac](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): sử dụng `--release 25` khi biên dịch.

Các ví dụ dùng quy tắc **đã final trong Java 25**, không sao chép trạng thái preview cũ thành khuyến nghị triển khai. Đối với JDK khác Java 25, luôn kiểm tra đặc tả tương ứng với mức source đang được cấu hình.

