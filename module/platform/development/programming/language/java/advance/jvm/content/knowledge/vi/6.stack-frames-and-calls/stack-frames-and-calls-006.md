# `<init>` và `<clinit>`: hai phương thức đặc biệt có vai trò khác nhau trong JVM

Trong ClassFile của Java, **`<init>`** và **`<clinit>`** là tên nội bộ của hai loại *method đặc biệt*, nhưng chúng phục vụ hai công việc khác nhau:

- **`<init>` — instance initialization method:** tương ứng với constructor của một class. Nó được gọi trong quy trình khởi tạo **mỗi đối tượng** bằng cơ chế gọi đặc biệt, điển hình là bytecode `invokespecial`. Một class có thể có nhiều `<init>` khác descriptor vì constructor có thể overload.
- **`<clinit>` — class/interface initialization method:** nếu có, chứa công việc khởi tạo tĩnh mà compiler tạo ra từ static field initializers và static initializer blocks. Nó được JVM **tự thực hiện khi class hoặc interface được khởi tạo theo quy tắc JVM**, thường chỉ một lần cho mỗi định nghĩa class/interface thành công, không phải một lần cho mỗi `new`.

Khi đọc kết quả `javap`, cần nhớ `<init>` không đồng nghĩa **toàn bộ khởi tạo object**, còn `<clinit>` không đồng nghĩa **nạp class file**. Class loading, linking, initialization và gọi constructor là những bước có liên quan nhưng khác nhau.

## 1. So sánh nhanh `<init>` và `<clinit>`

| Tiêu chí | `<init>` | `<clinit>` |
| --- | --- | --- |
| Mục đích | Khởi tạo một **instance** thông qua constructor | Khởi tạo trạng thái **static** của class/interface |
| Xuất hiện từ đâu? | Constructor viết trong source hoặc constructor mặc định do compiler tạo | Phần khởi tạo static cần thực thi do compiler tổng hợp |
| Bao nhiêu method? | Có thể nhiều, phân biệt bằng descriptor tham số | Tối đa một method mang tên `<clinit>` trong một ClassFile hợp lệ |
| Descriptor | Dạng `(tham_so)V`, trả `void` ở mức JVM | **`()V`**: không tham số, không trả giá trị |
| Cách khởi chạy | Thường dùng `invokespecial` với tham chiếu instance chưa được khởi tạo hoặc đang trong constructor chain | JVM kích hoạt theo quy trình class/interface initialization; không gọi trực tiếp như method Java |
| Liên quan tới `new` | Lời gọi constructor diễn ra khi tạo object qua biểu thức `new` trong chương trình Java thông thường | Nếu class chưa initialized, hoạt động `new` có thể làm class cần initialization trước khi tiếp tục |
| Tần suất | Mỗi lần có lời gọi constructor tương ứng trong quá trình tạo object | Một lần cho mỗi định nghĩa class/interface được initialize thành công, trừ trường hợp định nghĩa khác do class loader khác |
| Có kế thừa/override không? | Constructor không được kế thừa hay override; constructor chain có thể gọi `super(...)` hoặc `this(...)` | Static initialization của class cha xảy ra theo quy tắc trước class con; không có override `<clinit>` |
| Có thể gọi từ source Java theo tên `<init>`/`<clinit>`? | Không; dùng `new`, constructor chaining hoặc reflection API thích hợp | Không; chỉ viết static field initializer/static block hoặc để JVM kích hoạt |
| Có thể gây lỗi? | Exception từ constructor và quá trình khởi tạo instance | Exception/Error lúc khởi tạo class, có thể ảnh hưởng mọi lần sử dụng về sau |

**Cách nhớ:** `<init>` gắn với **một object** và constructor; `<clinit>` gắn với **trạng thái class**. Dù tên chứa cặp ngoặc nhọn góc, đây là những tên đặc biệt trong ClassFile/JVM, **không phải cú pháp khai báo method của Java source**.

## 2. Đặt đúng hai method trong vòng đời JVM

Một mô hình khái quát:

```text
      JVM cần sử dụng một class
                 │
                 ▼
       Loading: nạp định nghĩa class
                 │
                 ▼
       Linking: verify, prepare, resolve
                 │
                 ▼
     Initialization khi có yêu cầu
       ┌──────────────────────────┐
       │ Thực thi <clinit> nếu có │
       │ (khi đúng điều kiện)     │
       └──────────────────────────┘
                 │
                 ▼
          new một instance
                 │
                 ▼
     Constructor chain / <init>
                 │
                 ▼
        Dùng object đã tạo
```

Sơ đồ là luồng khái quát của việc **lần đầu tạo một object**; không phải mọi thao tác load class đều lập tức gây initialization, và trong quá trình thực thi có thể nạp thêm nhiều class. Khi class đã khởi tạo thành công, việc tạo object tiếp theo **không chạy `<clinit>` lần nữa**, nhưng vẫn chạy quá trình constructor thích hợp.

### Phân biệt ba ý niệm “khởi tạo”

1. **Preparation:** JVM chuẩn bị các static fields với giá trị mặc định hoặc giá trị `ConstantValue` theo quy tắc ClassFile, trước khi thực thi code static initializer.
2. **Class/interface initialization:** JVM thực hiện công việc khởi tạo class/interface, trong đó có `<clinit>` nếu compiler đã tạo.
3. **Instance initialization:** Sau khi đối tượng được cấp phát và các instance fields có giá trị mặc định, quy trình constructor chain và instance field initializers/instance initializer blocks tạo nên trạng thái ban đầu của từng object.

`static int total = compute();` thường cần code thực thi trong `<clinit>`; `int value = compute();` là instance field initializer và thường được compiler chèn vào constructor `<init>` ở vị trí phù hợp. Không có opcode chung tên “execute every initializer” trong bytecode mà mọi trường hợp đều đi qua.

## 3. `<init>`: instance initialization method

### 3.1. Constructor Java trở thành gì trong class file?

Cho source:

```java
class Point {
    int x;

    Point() {
        this(0);
    }

    Point(int value) {
        x = value;
    }
}
```

Đây là **class minh họa**; nó có thể biên dịch khi đặt trong `Point.java` mà không cần `public`. Trong ClassFile, hai constructor tương ứng hai `<init>` có descriptor khác nhau:

```text
Point.<init>:()V
Point.<init>:(I)V
```

- `()V` nghĩa là không nhận tham số và kết thúc bình thường không trả giá trị.
- `(I)V` nghĩa là nhận một `int` và trả `void` ở mức method descriptor.
- Cả hai được JVM nhìn dưới tên đặc biệt `<init>`, **không phải hai method Java thường tên `Point` để có thể override**.

Ở Java source, constructor **không khai báo return type**, kể cả `void`; ký hiệu `V` trong descriptor là quy ước JVM về cách method này kết thúc, không cho phép viết `void Point()` để khai báo constructor.

### 3.2. `new` không tự gọi tất cả constructor

Khi biên dịch biểu thức:

```java
Point point = new Point(5);
```

bytecode thường có mẫu:

```text
new           Point
dup
iconst_5
invokespecial Point."<init>":(I)V
astore_1
```

Đây là **đoạn bytecode minh họa**, trong đó offset, cách nạp số `5` và chỉ số local variable có thể khác tùy ngữ cảnh/compiler. Diễn giải:

1. `new` yêu cầu tạo instance; reference trên stack đang ở trạng thái **uninitialized** theo các quy tắc kiểm tra của JVM.
2. `dup` sao chép **giá trị reference**, không tạo object thứ hai.
3. `iconst_5` đưa tham số `5` lên operand stack.
4. `invokespecial` gọi đúng instance initialization method `Point.<init>(int)`.
5. Reference sau khi khởi tạo thành công có thể được lưu và sử dụng.

**Đừng sử dụng object trước khi hoàn thành khởi tạo một cách không hợp lệ.** Bytecode verifier theo dõi các dạng *uninitialized reference* và điều kiện gọi constructor. `<init>` là loại invocation đặc biệt, không phải method có thể gọi tùy ý bằng `invokevirtual`.

### 3.3. `this(...)`, `super(...)` và constructor chaining

Ở Java 17, constructor thông thường phải bắt đầu bằng constructor invocation phù hợp:

- `this(...)` chuyển sang một constructor **khác của cùng class**.
- `super(...)` chuyển sang constructor của **class cha**.
- Nếu không viết tường minh, `javac` thêm lời gọi `super()` khi hợp lệ.

Ví dụ `Point()` gọi `this(0)`, nên khi `new Point()`, constructor no-arg **không** tự chạy toàn bộ instance field initializers rồi mới chạy constructor `Point(int)` thêm lần nữa. Các initializer của object được bố trí vào luồng constructor sao cho chúng chạy đúng số lần và đúng thứ tự theo ngữ nghĩa Java.

Với object thuộc class con:

```text
new Child(...)
  → gọi constructor thích hợp của Child
    → constructor chain đến super(...)
      → constructor chain của các ancestor
      → phần instance initialization của superclass
    → phần instance initialization của Child
    → body của Child constructor
  → object sẵn sàng được trả về nếu không có exception
```

Đây là sơ đồ ngữ nghĩa; trong bytecode thực, **các lời gọi `<init>` được lồng nhau** và Java source có các quy tắc về đánh giá đối số, instance initializers và thứ tự constructor body. Hãy xem ví dụ chạy ở mục 6 để thấy output chính xác.

### 3.4. Default values, instance field initializer và constructor body

Khi object được cấp phát, các instance field bắt đầu với **default values** như `0`, `false`, `null`. Sau đó các constructor và instance initializers có thể ghi đè chúng. Với class con, constructor cha chạy trước phần khởi tạo instance của con theo quy tắc Java.

Ví dụ:

```java
class Example {
    int count = 3;

    {
        count += 2;
    }

    Example() {
        count += 4;
    }
}
```

Nếu tạo `new Example()`, field `count` cuối cùng là **9**: mặc định `0`, initializer thành `3`, instance initializer block cộng `2`, constructor body cộng `4`. Đây là class minh họa hợp lệ; không cần khai báo `main` nếu chỉ dùng để quan sát cấu trúc khi biên dịch.

### 3.5. `<init>` không được kế thừa hay gọi như phương thức thường

Class con không “thừa hưởng” các constructor của class cha. Lời gọi `super(...)` khởi tạo phần thuộc class cha thông qua một constructor được chọn, nhưng đó **không phải override hoặc dynamic dispatch của constructor**. Bạn không thể gọi constructor như `obj.Point()` sau khi object đã được tạo.

Reflection có API `Constructor.newInstance(...)` để tạo object theo constructor thích hợp; nó không biến `<init>` thành Java method công khai tên `<init>`. Việc dùng reflection vẫn phải tuân thủ quy tắc về access và khởi tạo class.

## 4. `<clinit>`: class/interface initialization method

### 4.1. Compiler tổng hợp static initializers

Ví dụ:

```java
class Settings {
    static int port = readDefaultPort();

    static {
        port += 10;
    }

    static int readDefaultPort() {
        return 8000;
    }
}
```

Trong ClassFile, compiler có thể tạo:

```text
Settings.<clinit>:()V
  // port = readDefaultPort();
  // port += 10;
  // return
```

Đây là **pseudocode** về các hoạt động do `<clinit>` thực hiện, không phải cú pháp để tạo một method trong Java source. Nếu class initialization thành công, `Settings.port` trở thành **8010**. Các thao tác static field initializer và static block thông thường được thực hiện **theo thứ tự xuất hiện trong source**, có các quy tắc đặc biệt cho constant variables và forward reference.

Nếu class **không có công việc static cần code khởi tạo**, compiler **không bắt buộc** tạo `<clinit>`. Chẳng hạn một class chỉ có các method thường hoặc `static final int MAX = 10;` có thể không cần body `<clinit>` riêng; hằng số loại này có thể được biểu diễn thông qua `ConstantValue`.

### 4.2. `<clinit>` có một descriptor cố định

Khác với overload của constructor:

```text
<init>:()V           // no-arg constructor
<init>:(I)V          // constructor nhận int
<init>:(Ljava/lang/String;)V
<clinit>:()V         // class/interface initialization, không tham số
```

Các method trong bảng dùng **tên đặc biệt và method descriptors**. `<clinit>` không có tham số và không được khai báo như một Java source method. Trong class file hiện đại, nó mang tính `static` theo quy tắc phiên bản ClassFile; bạn không thể chọn gọi nó bằng `someClass.<clinit>()` hay bằng cách đưa tên `<clinit>` vào một câu lệnh Java.

### 4.3. Khi nào JVM kích hoạt class initialization?

Theo mô hình JVM/JLS, class thường được khởi tạo ngay trước một số **active uses**, ví dụ:

- Tạo instance của class bằng `new` (nếu chưa initialized).
- Gọi static method được khai báo trong class, ví dụ `Service.run()`.
- Đọc static field không thuộc trường hợp constant variable được phép truy cập mà không initialization.
- Ghi static field theo quy tắc truy cập static.
- Một số thao tác reflection/MethodHandle hoặc yêu cầu cụ thể của runtime.

Ví dụ:

```java
class Counter {
    static int value = init();

    static int init() {
        System.out.println("Counter static init");
        return 7;
    }

    static void show() {
        System.out.println(value);
    }
}
```

Nếu một class khác gọi `Counter.show()` lần đầu, JVM phải bảo đảm `Counter` đã được initialized theo quy tắc trước khi phần code `show()` thực thi. Tuy vậy, chỉ **load** class hoặc lấy một class literal như `Counter.class` thường **chưa** tự kích hoạt initialization.

### 4.4. Static initializer không nhất thiết có mặt dù dùng class

`static final` **compile-time constant** là trường hợp cần phân biệt:

```java
class Constants {
    static final int LIMIT = 100;
    static int runtimeValue = compute();

    static int compute() {
        System.out.println("Constants initialized");
        return 2;
    }
}
```

Khi Java compiler có thể thay `Constants.LIMIT` bằng literal `100` theo quy tắc constant variables, lời đọc `Constants.LIMIT` **không tự yêu cầu khởi tạo `Constants`**. Nhưng truy cập `Constants.runtimeValue` thông thường kích hoạt initialization.

Không được khái quát thành “mọi `static final` đều không kích hoạt `<clinit>`”: `static final Object VALUE = new Object();` không phải compile-time constant variable, nên công việc khởi tạo object thuộc class initialization. Hãy phân biệt **hằng số lúc biên dịch** với **biến static final cần thực thi biểu thức lúc chạy**.

### 4.5. Interface và class có khác nhau không?

Interface cũng có thể cần initialization, đặc biệt khi có các static field với initializer tạo tác dụng phụ theo những ngữ nghĩa hợp lệ. Compiler có thể tạo `<clinit>` cho interface nếu cần.

Không suy luận “một class implement interface thì mọi interface cha đều được initialize như toàn bộ chuỗi superclass”. **Quy tắc khởi tạo superclass và superinterface có default method** khác với giả định khởi tạo toàn bộ đồ thị interface cùng lúc. Trong thực hành, đọc *JLS §12.4* và *JVMS §5.5* khi phải dự đoán thứ tự phức tạp.

## 5. Thứ tự và tính duy nhất của class initialization

### 5.1. Một lần trên mỗi định nghĩa class, không phải một lần trên toàn ứng dụng

Trong một JVM, danh tính lớp phụ thuộc vào **binary name** và **defining class loader**. Hai class loaders khác nhau có thể định nghĩa hai class cùng binary name nhưng là **hai runtime classes khác nhau**, với static state riêng và quy trình initialization riêng.

Vì vậy câu “`<clinit>` chỉ chạy một lần” cần nói chính xác: **mỗi runtime class/interface definition được initialization thành công chỉ thực hiện quy trình khởi tạo của nó một lần**. Nếu tải định nghĩa độc lập qua loader khác, đó là trường hợp khác. Không có cam kết chỉ một lần trên mọi tiến trình Java trong mọi hệ thống.

### 5.2. Khởi tạo superclass trước subclass

Khi initialization của subclass được yêu cầu, JVM bảo đảm superclass liên quan được initialized trước theo các quy tắc áp dụng. Vì vậy:

```text
First active use of Child
  → Parent class initialization (<clinit> nếu có)
  → Child class initialization (<clinit> nếu có)
  → constructor chain của object:
      Parent.<init> ...
      Child.<init> ...
```

**Class initialization** là công việc ở mức static, còn **constructor chain** là công việc trên từng instance. Hai chuỗi này liên quan nhau vì `new Child()` cần class initialized trước khi object được tạo/khởi tạo đầy đủ, nhưng không nên gộp chúng thành một `<init>`.

### 5.3. Thread safety và trạng thái lỗi

JVM có cơ chế phối hợp initialization của một class để những luồng đồng thời không cùng chạy nội dung `<clinit>` như hai tác vụ độc lập trên cùng một runtime class. Các thread khác có thể cần chờ kết quả initialization; JVM có các quy tắc về trạng thái đang khởi tạo, đã khởi tạo và **erroneous**.

Nếu `<clinit>` kết thúc bất thường, việc dùng class có thể thất bại với `ExceptionInInitializerError` (khi một exception phù hợp được bao bọc) hoặc lỗi tương ứng; những lần active use về sau thường nhận `NoClassDefFoundError` cho class ở trạng thái initialization thất bại. Trường hợp lỗi `Error` có các quy tắc riêng; không phải mọi lỗi luôn được bọc cùng một cách.

Việc bắt lỗi rồi “gọi lại `<clinit>`” theo tên là **không có** trong ngữ nghĩa Java. Cách khắc phục thường là sửa nguyên nhân initialization, thay đổi cấu trúc thiết kế hoặc trong môi trường ứng dụng phù hợp nạp định nghĩa mới qua loader/tiến trình mới; không tìm cách gọi trực tiếp `<clinit>`.

## 6. Ví dụ chạy Java 17+: thứ tự `<clinit>`, `<init>` và constructor chaining

Tạo file **`InitLifecycleDemo.java`**:

```java
public class InitLifecycleDemo {
    static int log(String text) {
        System.out.println(text);
        return 1;
    }

    static class Parent {
        static int staticValue = log("Parent static initializer");

        int parentValue = log("Parent instance initializer");

        Parent() {
            System.out.println("Parent constructor");
        }
    }

    static class Child extends Parent {
        static int staticValue = log("Child static field initializer");

        static {
            System.out.println("Child static block");
        }

        int childValue = log("Child instance initializer");

        Child() {
            System.out.println("Child constructor");
        }

        Child(int number) {
            this();
            System.out.println("Child constructor(int): " + number);
        }
    }

    public static void main(String[] args) {
        System.out.println("start");

        System.out.println("first new");
        Child first = new Child(7);

        System.out.println("second new");
        Child second = new Child();

        System.out.println("different objects: " + (first != second));
    }
}
```

Từ thư mục chứa source, sử dụng JDK 17 trở lên:

```bash
javac -encoding UTF-8 InitLifecycleDemo.java
java InitLifecycleDemo
```

**Standard output chính xác:**

```text
start
first new
Parent static initializer
Child static field initializer
Child static block
Parent instance initializer
Parent constructor
Child instance initializer
Child constructor
Child constructor(int): 7
second new
Parent instance initializer
Parent constructor
Child instance initializer
Child constructor
different objects: true
```

### Giải thích theo từng giai đoạn

**Lần tạo object đầu tiên:**

1. `main` in `start`, rồi `first new`.
2. Active use `new Child(7)` cần initialization của `Child`; `Parent` được initialized trước → `Parent static initializer`.
3. `Child` được initialized → field static initializer in `Child static field initializer`, static block in `Child static block`. Hai thành phần tĩnh của **Child** thực hiện theo thứ tự source.
4. `Child(int)` gọi `this()`, và `Child()` có lời gọi `super()` ngầm định. Luồng constructor đến **Parent** trước.
5. Instance field initializer của `Parent` in `Parent instance initializer`, rồi body của `Parent()` in `Parent constructor`.
6. Instance field initializer của `Child` in `Child instance initializer`, rồi body `Child()` in `Child constructor`.
7. Trở về body của `Child(int)` → in `Child constructor(int): 7`.

**Lần tạo object thứ hai:**

- `Parent` và `Child` đã initialized thành công, nên **không in** ba dòng static initializer nữa.
- Object mới vẫn thực hiện instance initializers của cha/con và constructor bodies như bình thường.
- `first != second` là `true` vì `new` tạo các object riêng; việc `<clinit>` chạy một lần không có nghĩa chương trình chỉ tạo được một instance.

**Lưu ý chính xác:** `Parent static initializer` và `Child static field initializer` trong ví dụ là *chuỗi log*, không phải tên bytecode instruction. Lệnh thực hiện việc in được compiler đưa vào `<clinit>` theo cấu trúc source, còn constructor/instance initializers được chuyển thành bytecode trong các `<init>` tương ứng.

## 7. Thử nghiệm riêng: `static final`, `T.class` và active use

Để phân biệt load/reference class với initialization, tạo file **`ActiveUseDemo.java`**:

```java
public class ActiveUseDemo {
    static class Lazy {
        static final int LIMIT = 100;

        static int result = init();

        static int init() {
            System.out.println("Lazy initialized");
            return 25;
        }

        static void work() {
            System.out.println("Lazy.work()");
        }

        Lazy() {
            System.out.println("Lazy constructor");
        }
    }

    public static void main(String[] args) {
        System.out.println("begin");
        System.out.println("constant: " + Lazy.LIMIT);
        System.out.println("class literal: " + (Lazy.class != null));
        System.out.println("before active use");
        System.out.println("runtime field: " + Lazy.result);
        Lazy.work();
        new Lazy();
        System.out.println("end");
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 ActiveUseDemo.java
java ActiveUseDemo
```

**Standard output:**

```text
begin
constant: 100
class literal: true
before active use
Lazy initialized
runtime field: 25
Lazy.work()
Lazy constructor
end
```

Ý nghĩa:

- `Lazy.LIMIT` là **compile-time constant variable**; compiler có thể inline `100`, nên thao tác này không gây initialization của `Lazy`.
- `Lazy.class != null` dùng class literal; hoạt động này không phải active use đòi `<clinit>`. Nó có thể khiến hệ thống lấy đối tượng `Class` của type nhưng **không** đồng nghĩa khởi tạo static state.
- Lần đọc **`Lazy.result`** kích hoạt `Lazy` initialization, in một lần `Lazy initialized`.
- Gọi `Lazy.work()` và `new Lazy()` sau đó không khởi tạo lại static fields. Tuy nhiên **`new Lazy()` vẫn gọi constructor** nên có `Lazy constructor`.
- Nếu đảo thứ tự để `new Lazy()` diễn ra đầu tiên, class initialization sẽ diễn ra trước khi constructor body chạy.

Chương trình không dùng reflection hay class loader tùy biến nên thứ tự stdout trên có thể kiểm tra nhất quán.

## 8. Đọc bytecode bằng `javap`

Các lệnh sau dùng output `.class` của ví dụ mục 6:

```bash
javap -c -p InitLifecycleDemo
javap -c -p 'InitLifecycleDemo$Parent'
javap -c -p 'InitLifecycleDemo$Child'
javap -v -p 'InitLifecycleDemo$Child'
```

Trong Bash/PowerShell, nháy đơn bảo vệ ký tự `$` trong tên binary của nested class. Với Windows `cmd.exe`, dùng dấu nháy kép xung quanh `InitLifecycleDemo$Child`.

### 8.1. Tìm constructor `<init>`

Ở output `javap -c -p 'InitLifecycleDemo$Child'`, các constructor có thể được hiển thị bằng **tên class**:

```text
InitLifecycleDemo$Child();
InitLifecycleDemo$Child(int);
```

Đừng suy ra trong class file constructor thật mang tên `Child`; **constant pool và các method references** sẽ thể hiện special name `<init>`. Một đoạn điển hình trong constructor no-arg:

```text
aload_0
invokespecial InitLifecycleDemo$Parent."<init>":()V
aload_0
invokestatic InitLifecycleDemo.log:(Ljava/lang/String;)I
putfield ... childValue:I
...
return
```

Đây là mẫu được rút gọn để giải thích, **không phải listing `javap` cần khớp từng offset**. Constructor `Child(int)` sẽ gọi `Child.<init>:()V` bằng `invokespecial` trước khi in dòng nhận tham số.

### 8.2. Tìm `<clinit>`

Ở output của class **Child**, `javap` thường trình bày class initialization method bằng nhãn:

```text
static {};
```

Phần body chứa bytecode cho:

```java
static int staticValue = log("Child static field initializer");
static {
    System.out.println("Child static block");
}
```

Đó là body `<clinit>:()V` do compiler tạo. Các lệnh thường liên quan tới gọi `log`, `putstatic`, in ra console rồi `return`.

Tại `javap -v -p`, quan sát **method descriptor `()V`** và những mục constant pool hoặc tên `<clinit>`, `<init>` khi chúng xuất hiện. `javap` có thể hiển thị constructor bằng tên class và static initializer là `static {}`, vì vậy đừng tìm một dòng hiển thị giống hệt `void <clinit>()` trong phần Java-like signatures.

### 8.3. So sánh code khởi tạo instance với code static

| Java source | Thông tin bytecode thường thấy |
| --- | --- |
| `static int staticValue = log(...);` | Trong `<clinit>`: gọi `log`, rồi `putstatic` |
| `static { System.out.println(...); }` | Trong `<clinit>`: các instruction từ static block |
| `int childValue = log(...);` | Trong constructor `<init>`, sau lời gọi constructor cha thích hợp |
| `Child()` | Một `<init>:()V` |
| `Child(int)` | Một `<init>:(I)V` gọi `this()` |
| `new Child(7)` | `new`, nạp tham số, `invokespecial <init>` tại code gọi |
| `Child.staticValue` | `getstatic`, có thể kích hoạt class initialization khi class chưa initialized |

Chi tiết instruction có thể thay đổi khi đổi compiler, nhưng ranh giới **static state khởi tạo một lần** và **instance state khởi tạo cho từng object** vẫn tuân theo ngữ nghĩa Java.

## 9. Các câu hỏi dễ nhầm khi debug chương trình

### 9.1. “Có constructor nhưng tại sao chưa thấy dòng static log?”

Nếu chỉ viết class mà chưa active-use class, **class initialization có thể chưa xảy ra**. Những thao tác như biên dịch, kiểm tra class file bằng `javap`, lấy tên lớp từ metadata hoặc dùng class literal không đồng nghĩa đã chạy static initializer. Ngược lại, lần đầu thực sự gọi static method hoặc tạo instance có thể kích hoạt initialization.

### 9.2. “Constructor nào chạy khi `this(...)` xuất hiện?”

Constructor được gọi qua `this(...)` chạy trên **cùng object**. Đây không phải tạo object thứ hai. Quá trình đi tới một constructor có lời gọi `super(...)`, rồi quay lại lần lượt các constructor trong chain. Instance initialization blocks của class không chạy lặp một lần cho mỗi constructor cùng class nằm trong chain.

### 9.3. “Static field có giá trị mặc định trước `<clinit>` không?”

Có. JVM thực hiện **preparation** và áp dụng các quy tắc cho static fields/constant values. Khi `<clinit>` chạy, code có thể đọc các giá trị mặc định hoặc giá trị đã được khởi tạo trước theo quy tắc, rồi ghi tiếp. Đừng đồng nhất việc field ban đầu có `0` với chuyện `<clinit>` đã chạy.

### 9.4. “Gọi `super()` có khởi tạo static field của class cha không?”

Class initialization của superclass được JVM bảo đảm theo quy trình class initialization phù hợp khi cần khởi tạo subclass. Nhưng **`super()` là constructor invocation**, dùng để khởi tạo phần instance của cha. Đây là hai khái niệm khác; không dùng tên `super()` thay cho `<clinit>`.

### 9.5. “`<clinit>` có được JVM thực thi lại khi tạo object thứ hai không?”

Không, nếu runtime class đã initialized thành công. Mỗi object mới vẫn có quá trình constructor riêng. Nếu định nghĩa class khác được nạp qua loader khác hoặc JVM mới, đó lại là runtime class khác.

### 9.6. “Tại sao một static initializer lỗi làm cả class khó dùng?”

Lỗi phát sinh trong quá trình class initialization có thể đưa runtime class vào trạng thái **erroneous**. Những lần active-use về sau không đơn giản thử lại initializer như một function gọi thông thường. Thiết kế static initializer nên tránh công việc bất ổn khó phục hồi như truy cập mạng, đọc cấu hình không kiểm soát và thao tác phụ thuộc tài nguyên chưa sẵn sàng.

### 9.7. “Có `<clinit>` trong mọi class chứa `static` không?”

Không. Class có `static` methods hoặc compile-time constants chưa chắc cần `<clinit>`; compiler chỉ tạo khi cần các công việc khởi tạo class/interface phải thực thi thành bytecode. Ngược lại, class không có static block tường minh **vẫn** có thể có `<clinit>` vì static field initializer có biểu thức cần chạy.

### 9.8. “`<init>` có thể trả một object khác thay thế `this` không?”

Constructor Java không có return value và `<init>` có descriptor trả `V`. Factory method có thể trả object do nó chọn, nhưng đó là **method bình thường** chứ không phải constructor `<init>`. Kết quả của biểu thức `new` là tham chiếu tới object vừa được tạo/khởi tạo thành công.

## 10. Bài tập vận dụng

### Bài tập 1 — Đếm số lần

Xét:

```java
class Service {
    static {
        System.out.println("S");
    }

    {
        System.out.println("I");
    }

    Service() {
        System.out.println("C");
    }
}
```

Nếu một `main` khác lần lượt gọi `new Service(); new Service();` và không có active use trước đó, output gồm:

```text
S
I
C
I
C
```

Giải thích: static initialization chỉ diễn ra lần đầu; instance initializer và constructor body chạy cho **mỗi object**.

### Bài tập 2 — Constructor chaining

Xét:

```java
class Sample {
    {
        System.out.println("I");
    }

    Sample() {
        this(1);
        System.out.println("A");
    }

    Sample(int n) {
        System.out.println("B");
    }
}
```

Nếu `new Sample()`, output là:

```text
I
B
A
```

Instance initializer **chỉ chạy một lần** trên object. `Sample()` chuyển sang `Sample(int)`, khởi tạo instance và chạy body constructor nhận `int`, rồi mới trở lại in `A`.

### Bài tập 3 — Hằng số compile-time

Xét:

```java
class Marks {
    static final int LIMIT = 50;
    static {
        System.out.println("initialized");
    }
}
```

Nếu `main` chỉ in `Marks.LIMIT` từ một class được biên dịch cùng code, JVM có thể chỉ thực thi code đã inline `50`; không bắt buộc in `initialized`. Nếu thêm một active use chắc chắn như gọi một static method thực thi của `Marks` hoặc tạo `new Marks()`, initialization sẽ xảy ra trước thao tác tương ứng.

### Bài tập 4 — Dự đoán `javap`

Từ `InitLifecycleDemo.java`:

1. `Child()` có descriptor nào? **`()V`**.
2. `Child(int)` có descriptor nào? **`(I)V`**.
3. `Child static block` nằm trong method nào? **`<clinit>` của Child**.
4. `Child instance initializer` thuộc quá trình nào? **Constructor `<init>`**, không phải `<clinit>`.
5. Dòng `Child constructor(int): 7` in trước hay sau `Child constructor`? **Sau**, bởi `Child(int)` gọi `this()`.
6. Có bao nhiêu object `Child` được tạo trong `main`? **Hai**, mặc dù static initializer chỉ chạy một lần.

### Câu hỏi tự kiểm tra

**1.** `<init>` và `<clinit>` có chung mục đích “đặt giá trị mặc định cho mọi field” không?  
**Không.** Default values có quy trình riêng tại preparation/object allocation; `<init>` thực hiện constructor logic trên instance, `<clinit>` thực hiện static initialization logic nếu có.

**2.** Có thể overload `<clinit>` thành `<clinit>(int)` trong class file không?  
**Không.** Class/interface initialization method có descriptor quy định `()V`; không phải API do người dùng overload.

**3.** Tạo 100 instance cùng một class đã initialized thì `<init>` và `<clinit>` chạy bao nhiêu lần?  
Mỗi instance được khởi tạo qua constructor chain thích hợp; **`<clinit>` không chạy lại** vì class đã initialized thành công. Số lời gọi `<init>` thực tế có thể lớn hơn 100 do mỗi object có chuỗi constructor của cha/con.

**4.** Vì sao `javap` đôi khi chỉ in `static {}` mà không hiện đúng chuỗi `<clinit>` ở dòng method header?  
`javap` hiển thị biểu diễn dễ đọc gần cú pháp Java; tên method đặc biệt `<clinit>` được biểu diễn thành static initializer.

**5.** `<init>` được gọi bằng `invokevirtual` như override method không?  
**Không.** Constructor được gọi theo cơ chế `invokespecial`; nó không là method thường để override.

**6.** Khi class có `static final String CODE = "OK";`, việc đọc CODE chắc chắn kích hoạt static block?  
**Không.** Nếu `CODE` là compile-time constant variable và được inline theo quy tắc Java, chỉ đọc nó chưa phải active use khởi tạo class.

**7.** Class loading có đồng nghĩa với class initialization không?  
**Không.** Có thể load/link class mà chưa chạy `<clinit>`; initialization được kích hoạt tại thời điểm thích hợp theo các quy tắc JVM.

**8.** Nếu một static initializer thất bại, gọi `new` lần nữa có chắc initializer được chạy lại không?  
**Không.** Class có thể ở trạng thái erroneous trong class loader hiện tại, nên việc active-use tiếp tục thất bại.

## 11. Ghi nhớ và tài liệu chuẩn

- **`<init>`**: tên JVM của constructor; có thể overload theo descriptor; tham gia instance initialization, thường thấy qua `invokespecial`.
- **`<clinit>`**: method do compiler tổng hợp cho công việc class/interface initialization; descriptor `()V`; JVM quản lý khi nào thực thi.
- **Static initialization không phải instance initialization**: `<clinit>` xử lý trạng thái static, constructor chain/`<init>` xử lý state mỗi object.
- **Loading không phải initialization**: xem trình tự loading, linking, preparation, initialization thay vì mặc định tất cả xảy ra ngay sau khi đọc tệp class.
- **Kiểm chứng bằng `javap -c -p` và `javap -v`**: dự đoán output chương trình, sau đó đọc các method, descriptors và instruction liên quan.

Tài liệu chuẩn: *The Java Virtual Machine Specification*, chương 2 (*instance initialization methods* và *class/interface initialization methods*), chương 4 (*ClassFile*), chương 5.5 (*Initialization*) và chương 6.5 (`new`, `invokespecial`), bản Java 17: https://docs.oracle.com/javase/specs/jvms/se17/html/ . Quy tắc thứ tự initializer và constructor ở cấp ngôn ngữ được giải thích trong *Java Language Specification*, các mục **§8.8** và **§12.4**.

**Kết luận:** Hãy đặt câu hỏi đúng cấp độ: “JVM đã **initialize class** chưa?” để hiểu `<clinit>`; và “JVM đang **khởi tạo object nào, qua constructor chain nào**?” để hiểu `<init>`. Khi hai câu hỏi được tách rõ, thứ tự log static/instance, lỗi initialization và output của `javap` trở nên nhất quán, dễ dự đoán hơn.