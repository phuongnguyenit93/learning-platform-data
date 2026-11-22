# Dự đoán kết quả bằng dấu vết nạp lớp và thứ tự chạy static initializer

## 1. Mục tiêu: nhìn code Java và dự đoán chính xác dòng nào xuất hiện trước

Khi đọc một chương trình có nhiều lớp, kế thừa, interface, static field và static block, thứ tự in log thường bị đoán sai vì người đọc gộp ba việc khác nhau:

1. **Loading:** JVM có biểu diễn runtime của class/interface từ một nguồn class bytes thích hợp.
2. **Linking:** class được kiểm chứng (*verification*), chuẩn bị (*preparation*) và resolve các symbolic references theo quy tắc VM.
3. **Initialization:** JVM thực thi các static field initializers và static blocks thuộc class/interface được yêu cầu khởi tạo (thường qua phương thức đặc biệt `<clinit>`).

**Dấu vết nạp lớp (class-load trace)** và **dấu vết in từ static initializer** đo những sự kiện khác nhau. Một dòng log báo class đã loaded **không có nghĩa** static block của nó đã chạy. Ngược lại, khi một static initializer đã thực thi thành công, lớp đó phải được load, verify/prepare trước, nhưng việc tải lớp có thể diễn ra từ trước mốc in rất lâu.

Mục tiêu của bài là xây dựng **quy trình dự đoán kết quả có thể lặp lại**, không dựa vào thứ tự nạp chủ quan của một phiên bản HotSpot.

### Một ví dụ tư duy

~~~text
Trong JAR có: Main.class, Parent.class, Child.class, Helper.class.

Log class+load:
  Parent loaded
  Child loaded

Stdout từ Java:
  PARENT_INIT
  CHILD_INIT

Không thể từ hai dòng "loaded" suy ra:
- mỗi lớp được initialized ngay khi loaded;
- JVM đã load mọi class trong JAR;
- Helper chắc chắn chưa được load;
- Parent và Child in ngay sau nhau, không có sự kiện runtime khác.
~~~

**Quy tắc vàng khi làm bài dự đoán stdout:** chỉ liệt kê dòng do **mã Java được yêu cầu thực thi** tạo ra theo quan hệ thứ tự được Java/JVM bảo đảm. Nếu bật VM logging, giữ một cột/dòng phân tích riêng cho log của runtime; không trộn log JVM phụ thuộc cấu hình với stdout cố định của chương trình.

## 2. Mô hình class initialization cần thuộc

Class initialization có hai câu hỏi:

- **Ai kích hoạt?** Những hành động được xem là *active use* theo JLS/JVMS.
- **Ai phải chạy trước?** Superclass, một số superinterface, rồi static initialization logic của class được yêu cầu.

Sơ đồ khái quát cho **lần active use đầu tiên của một class C**:

~~~text
Code thực hiện active use C
         |
         v
C đã initialized thành công chưa?
  +------+- Có ----> dùng ngay, không chạy <clinit> lần nữa
  |
  Không
  |
  v
Đảm bảo loading, verification, preparation phù hợp
         |
         v
Phối hợp initialization giữa các thread
         |
         v
Initialize superclass và các superinterface có
default method theo thứ tự mà đặc tả quy định
         |
         v
Thực thi static field initializers / static blocks
của chính C theo thứ tự văn bản
         |
         v
Đánh dấu initialized thành công, tiếp tục active use
~~~

**Đây là mô hình ngữ nghĩa**, không cam kết tất cả substep của linking chỉ diễn ra sau khi active use bắt đầu: JVM có thể tải/resolve sớm trong phạm vi đặc tả. Nếu class đang được initialization bởi **chính thread hiện tại** và đụng lại nó theo đường khởi tạo vòng, VM có quy tắc xử lý riêng; phần giá trị mặc định ở mục 9 là điểm dễ gây bất ngờ.

## 3. Khi nào một class/interface được initialized?

Các tình huống điển hình với Java 17:

| Hành động nguồn hoặc runtime | Kích hoạt initialization của kiểu được chỉ định? | Cần chú ý |
| --- | --- | --- |
| `new Widget()` | **Có** với `Widget` khi chưa initialized | Initialization hoàn tất theo quy tắc trước khi constructor body thực thi |
| `Widget.staticMethod()` | **Có** đối với class/interface thực sự khai báo static method | Static method không cần instance |
| Đọc `Widget.nonConstantStatic` | **Có** đối với class/interface thực sự khai báo field | Tên kiểu trong cú pháp chưa chắc là nơi **khai báo field** |
| Gán `Widget.staticField = value` | **Có** theo quy tắc active use | Trước lần ghi đầu tiên cần trạng thái class phù hợp |
| `Widget.class` | **Không chỉ do class literal** | Có thể cần load/resolve kiểu nhưng không bắt buộc initialize |
| `Class.forName(name)` | **Có** theo overload một tham số khi class tìm thấy | Yêu cầu initialization |
| `Class.forName(name, false, loader)` | **Không yêu cầu initialization** | Có thể tải/liên kết class; `false` không cấm loading |
| `loader.loadClass(name)` | Thông thường **không** tự yêu cầu initialization | Custom loader có thể có side effects riêng |
| `new Widget[3]` | **Không** initialize component class chỉ vì tạo array | Tạo **mảng**, không tạo ba instance `Widget` |
| Đọc `static final int X = 7` là compile-time constant variable | **Không chỉ vì lần đọc này** | Compiler có thể inline literal sang caller |
| Đọc `static final Integer X = 7` | **Có** (không phải primitive/String constant variable theo JLS) | `Integer` là reference; không phải compile-time constant expression của kiểu cho phép |
| Chạy `main` class khởi đầu | **Có** đối với class khởi đầu | Các class JDK cần cho startup cũng đã/đang được init |

**Lưu ý:** việc **load hoặc link** một class có thể chủ động đến sớm hơn trong implementation; bảng trên chỉ phân loại **yêu cầu initialization** của hành động đang xét. Nếu một class đã initialized do thao tác trước, lần dùng mới **không in lại static block**.

### 3.1. Phân biệt compile-time constant và giá trị final thông thường

~~~java
class Config {
    static {
        System.out.println("CONFIG_INIT");
    }

    static final int LIMIT = 7;
    static final String NAME = "JAVA";
    static final Integer BOXED = Integer.valueOf(7);
    static final int COMPUTED = Integer.parseInt("7");
}
~~~

- `Config.LIMIT` và `Config.NAME` có thể được inline vào caller như compile-time constants, nên một lần đọc chúng **không** tự khởi tạo Config.
- `Config.BOXED` và `Config.COMPUTED` không phải *constant variables* theo định nghĩa JLS dù khai báo `static final`. Đọc chúng đòi hỏi truy cập static field tại runtime, nên có thể kích hoạt Config initialization nếu chưa xảy ra.
- **Final không đồng nghĩa constant variable.** Điều kiện quan trọng là kiểu primitive hoặc String, `final`, và initializer là **constant expression** hợp lệ.
- Nếu một caller đã được biên dịch với `LIMIT = 7`, thay binary Config thành `LIMIT = 9` mà không rebuild caller có thể làm caller vẫn sử dụng literal cũ do constant inlining.

Ví dụ Config phía trên chỉ là đoạn minh họa, không có `main`; hãy xem chương trình đầy đủ ở mục 7 để có kết quả in chính xác.

## 4. Dự đoán thứ tự static fields và static blocks trong một class

Các **static variable initializers** và **static initializer blocks** được thực thi theo thứ tự văn bản ở cấp khai báo khi class được initialized. JVM thực hiện preparation trước, khiến một số static fields bắt đầu ở **giá trị mặc định** (ví dụ `int` là 0; reference là null), rồi initialization logic gán giá trị theo source semantics.

~~~java
class Order {
    static int first = print("FIRST_FIELD", 10);

    static {
        System.out.println("FIRST_BLOCK");
    }

    static int second = print("SECOND_FIELD", first + 1);

    static {
        System.out.println("SECOND_BLOCK");
    }

    static int print(String label, int value) {
        System.out.println(label + "=" + value);
        return value;
    }
}
~~~

Đây là đoạn minh họa **không có main**. Lần đầu thực sự initialize `Order`, thứ tự dòng do code Order phát sinh là:

~~~text
FIRST_FIELD=10
FIRST_BLOCK
SECOND_FIELD=11
SECOND_BLOCK
~~~

Không phải static initializer nào cũng có println, nên một lớp có thể initialized mà không xuất hiện dòng nào trên stdout. Khi dự đoán, đừng dùng “không in” làm bằng chứng chưa initialized.

### Static initialization khác constructor

- Static field initializer và static block chạy theo lifecycle **class**.
- **Constructor** và instance field initializer chạy khi một **object** được tạo; chúng có thể chạy nhiều lần cho nhiều instance.
- Khi tạo object của class con, superclass phải initialized theo quy tắc trước class con, nhưng **constructor của superclass** là một giai đoạn khác xảy ra khi instance construction được thực thi.
- Nếu class đã initialized trước, tạo instance thứ hai **không chạy lại `<clinit>`**; các constructor liên quan vẫn thực hiện cho instance mới.

Cách dự đoán: viết hai bảng tách biệt, một bảng **class initialization**, một bảng **object construction**. Sau đó ghép theo các active-use points.

## 5. Thừa kế: superclass được initialized trước subclass

Với:

~~~java
class Parent {
    static { System.out.println("PARENT_INIT"); }
    Parent() { System.out.println("PARENT_CTOR"); }
}
class Child extends Parent {
    static { System.out.println("CHILD_INIT"); }
    Child() { System.out.println("CHILD_CTOR"); }
}
~~~

Khi mã thực hiện lần đầu `new Child()`, trình tự ngữ nghĩa do chương trình tạo ra sẽ là:

~~~text
PARENT_INIT
CHILD_INIT
PARENT_CTOR
CHILD_CTOR
~~~

Giải thích:

1. Khởi tạo **class** Parent trước Child.
2. Khởi tạo **class** Child sau Parent.
3. Bắt đầu **instance initialization/constructor** cho Child, trước hết các phần của superclass object/constructor Parent theo quy tắc.
4. Sau Parent constructor, Child constructor hoàn tất.

**Đừng đánh đồng** `PARENT_INIT` với `PARENT_CTOR`. Một là static initializer có vòng đời class; một là constructor có vòng đời instance. Nếu bạn tạo Child lần thứ hai sau khi cả class đã initialized, lần thứ hai thông thường chỉ in:

~~~text
PARENT_CTOR
CHILD_CTOR
~~~

Hai đoạn trên là mô hình theo source minh họa; chương trình ở mục 6 có đủ code runnable và kết quả đã kiểm chứng.

### Field khai báo ở superclass dù được viết qua Subclass

~~~java
class Base {
    static int value = trace("BASE", 123);
}
class Sub extends Base {
    static { System.out.println("SUB"); }
}
~~~

Đoạn này là minh họa ý tưởng. Nếu biểu thức Java dùng `Sub.value`, **field thực sự được khai báo trong Base**, nên quy tắc active use kích hoạt initialization **Base**, không nhất thiết initialize Sub. Compiler có thể sinh `getstatic` tham chiếu field đã resolve tới Base. Muốn Sub chắc chắn initialized, cần một active use thực sự của Sub như `new Sub()` hoặc gọi static method do Sub khai báo.

Điều này giải thích những bài trắc nghiệm mà tên `Sub` xuất hiện rõ trong source nhưng stdout lại không có `"SUB"`.

## 6. Bài thực hành Java 17: một lần chạy có superclass, interface, hằng và constructor

Tạo tệp **`InitOrderDemo.java`** với toàn bộ mã sau:

~~~java
public final class InitOrderDemo {
    static int mark(String label, int result) {
        System.out.println(label);
        return result;
    }

    static class Parent {
        static int number = mark("PARENT_FIELD", 10);
        static { System.out.println("PARENT_BLOCK"); }

        Parent() {
            System.out.println("PARENT_CONSTRUCTOR");
        }
    }

    interface WithDefault {
        int TOKEN = InitOrderDemo.mark("DEFAULT_INTERFACE_FIELD", 11);
        default void unused() { }
    }

    interface Plain {
        int TOKEN = InitOrderDemo.mark("PLAIN_INTERFACE_FIELD", 22);
    }

    static class Child extends Parent implements WithDefault, Plain {
        static int number = mark("CHILD_FIELD", 20);
        static { System.out.println("CHILD_BLOCK"); }

        Child() {
            System.out.println("CHILD_CONSTRUCTOR");
        }

        static void ping() {
            System.out.println("CHILD_STATIC_METHOD");
        }
    }

    static class Constants {
        static { System.out.println("CONSTANTS_BLOCK"); }

        static final int MAGIC = 7;
        static final int NON_CONSTANT =
                mark("CONSTANTS_COMPUTED", 8);
    }

    public static void main(String[] args) {
        System.out.println("START");

        System.out.println("CLASS=" + Child.class.getSimpleName());
        System.out.println("CONST=" + Constants.MAGIC);
        System.out.println("BEFORE_NEW");

        Child child = new Child();

        System.out.println("AFTER_NEW");
        System.out.println("PLAIN=" + Plain.TOKEN);
        Child.ping();
        System.out.println("NON_CONST=" + Constants.NON_CONSTANT);
    }
}
~~~

Biên dịch và chạy với **JDK 17 trở lên**:

~~~bash
javac --release 17 InitOrderDemo.java
java InitOrderDemo
~~~

### Kết quả stdout đã kiểm chứng

~~~text
START
CLASS=Child
CONST=7
BEFORE_NEW
PARENT_FIELD
PARENT_BLOCK
DEFAULT_INTERFACE_FIELD
CHILD_FIELD
CHILD_BLOCK
PARENT_CONSTRUCTOR
CHILD_CONSTRUCTOR
AFTER_NEW
PLAIN_INTERFACE_FIELD
PLAIN=22
CHILD_STATIC_METHOD
CONSTANTS_BLOCK
CONSTANTS_COMPUTED
NON_CONST=8
~~~

Các dòng trên là **kết quả dự đoán theo Java 17**; hãy biên dịch bằng `javac --release 17` và chạy bằng JDK 17 để tự kiểm chứng thứ tự. Không cần đoán vị trí class load của JVM để có kết quả stdout này.

### 6.1. Giải từng mốc như một bài thi trace

**Mốc 1 — `START`:** `main` đã bắt đầu. Class `InitOrderDemo` cần được initialized để chạy `main`, nhưng chương trình không định nghĩa static initializer nào trong outer class nên không in thêm dấu vết ở đây.

**Mốc 2 — `Child.class.getSimpleName()`:** class literal tạo/lấy một `Class<?>` object cho Child và `getSimpleName()` trả `"Child"`. Thao tác này **không yêu cầu Child initialization** nên chưa có `CHILD_FIELD` hoặc `CHILD_BLOCK`. Nó có thể đi kèm class loading/linking, nhưng việc đó không hiện qua static initializer.

**Mốc 3 — `Constants.MAGIC`:** trường `MAGIC` là compile-time constant kiểu `int`, nên caller in `7` mà chưa kích hoạt Constants `<clinit>`. Sau `CONST=7` vẫn **không có `CONSTANTS_BLOCK`**.

**Mốc 4 — `new Child()`:** đây là lần active use đầu tiên yêu cầu Child initialized. JVM initialize superclass Parent trước; do đó `PARENT_FIELD` rồi `PARENT_BLOCK`. Sau đó **superinterface trực tiếp `WithDefault` khai báo default method** và thuộc tập cần initialized trong quy trình class initialization của Child, nên `DEFAULT_INTERFACE_FIELD` in trước các dòng static của Child.

**Mốc 5 — interface Plain:** Plain không khai báo default method, nên **không bị initialize chỉ vì Child implements Plain** trong tình huống này. `PLAIN_INTERFACE_FIELD` chưa in ở thời điểm Child initialization. Điều này khác với suy nghĩ “initialize class thì phải initialize tất cả interfaces của nó”.

**Mốc 6 — chính Child:** hai static declarations của Child theo thứ tự nguồn, in `CHILD_FIELD`, `CHILD_BLOCK`.

**Mốc 7 — tạo instance:** sau khi phần class initialization đã hoàn tất, phần object construction chạy constructor Parent rồi Child; in `PARENT_CONSTRUCTOR`, `CHILD_CONSTRUCTOR`.

**Mốc 8 — đọc `Plain.TOKEN`:** `TOKEN` là `int` nhưng được tạo bởi **method invocation**, nên nó không phải compile-time constant variable. `getstatic` cho field đã được khai báo trong Plain yêu cầu Plain initialization; in `PLAIN_INTERFACE_FIELD` trước khi `println` in `PLAIN=22`.

**Mốc 9 — `Child.ping()`:** Child đã initialized từ lần `new Child`, vì vậy không chạy lại `CHILD_BLOCK`; chỉ in `CHILD_STATIC_METHOD`.

**Mốc 10 — `Constants.NON_CONSTANT`:** đây là lần active use thực sự của Constants nên `CONSTANTS_BLOCK`, sau đó lời gọi `mark` của field initializer in `CONSTANTS_COMPUTED`; cuối cùng `println` in `NON_CONST=8`.

### Câu hỏi cải biến

- Nếu đảo hai declaration `static int number` và `static { ... }` trong Parent thì hai dòng Parent có đổi không? **Có**, theo thứ tự văn bản.
- Nếu bỏ `default void unused() {}` khỏi WithDefault, có còn được **bảo đảm** in `DEFAULT_INTERFACE_FIELD` khi `new Child()` không? **Không**, vì superinterface không có default method theo quy tắc thường không bắt buộc initialized cùng subclass.
- Nếu thêm `new Child()` lần nữa, static initializer nào chắc chắn chạy lại? **Không có**, nếu tất cả lần khởi tạo trước đã thành công; constructor của Parent và Child vẫn chạy cho object mới.
- Nếu thay `Plain.TOKEN` bằng `Plain.class`, có bảo đảm chạy `PLAIN_INTERFACE_FIELD` không? **Không**.
- Nếu `Constants.MAGIC` đổi từ `int` literal thành `Integer.valueOf(7)`, nó còn là compile-time constant variable không? **Không**.

## 7. Bài thực hành Java 17 thứ hai: loaded/linked nhưng chưa initialized

Tạo file **`TriggerMatrixDemo.java`**:

~~~java
public final class TriggerMatrixDemo {
    static class Target {
        static { System.out.println("TARGET_INIT"); }

        static final int MAGIC = 40;
        static final Integer BOXED = Integer.valueOf(40);

        static void ping() {
            System.out.println("PING");
        }
    }

    public static void main(String[] args)
            throws ClassNotFoundException {
        System.out.println("BEGIN");
        System.out.println("CONST=" + Target.MAGIC);

        Class<?> token = Target.class;
        System.out.println("LITERAL=" + token.getSimpleName());

        Class.forName(token.getName(), false,
                TriggerMatrixDemo.class.getClassLoader());
        System.out.println("LOADED_NO_INIT");

        System.out.println("BOXED=" + Target.BOXED);
        Target.ping();
        System.out.println("FINISH");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 TriggerMatrixDemo.java
java TriggerMatrixDemo
~~~

**Stdout dự đoán theo Java 17 (hãy tự chạy để kiểm chứng):**

~~~text
BEGIN
CONST=40
LITERAL=Target
LOADED_NO_INIT
TARGET_INIT
BOXED=40
PING
FINISH
~~~

### Tại sao thứ tự này quan trọng?

1. `CONST=40`: `static final int MAGIC = 40` là constant variable; lần đọc không phải active use yêu cầu Target initialization.
2. `Target.class` và `getSimpleName()`: có thể khiến JVM biết class nhưng không bắt buộc chạy `<clinit>`.
3. `Class.forName(name, false, loader)`: **có thể load/link** Target nhưng tham số `false` **không yêu cầu initialization**, nên in `LOADED_NO_INIT` trước `TARGET_INIT`.
4. `Target.BOXED`: là static final **reference** `Integer`, không phải constant variable; lần đọc kích hoạt initialization của Target. JVM chạy static block, in `TARGET_INIT`, rồi xử lý giá trị BOXED để `println` in `BOXED=40`.
5. `Target.ping()`: Target đã initialized, nên không có dòng `TARGET_INIT` thứ hai.

Đổi biến thể `false` thành `true` trong lời gọi `Class.forName` để kiểm nghiệm: `TARGET_INIT` sẽ xuất hiện **trước** `LOADED_NO_INIT`, còn lần đọc BOXED sau đó không khởi tạo lại Target. Đây là **biến thể**, không phải kết quả stdout của source gốc.

**Phân biệt:** `Class.forName(name)` overload một tham số mặc định **yêu cầu initialization**. `ClassLoader.loadClass(name)` thông thường chỉ load, không tự động initialize. Với class loader tùy biến, code của loader có thể có side effect riêng nên không nên dự đoán những log tùy biến nếu không có source loader đó.

## 8. Trường hợp đặc biệt: interface có default method và interface không có

Đối với interface, quy tắc initialization khác cách nhiều người đoán:

- **Initialize một interface** không mặc nhiên initialize toàn bộ superinterfaces của nó chỉ vì quan hệ extends.
- **Initialize một class** có superclass phải initialize superclass trước. Theo JLS/JVMS hiện đại, một số **superinterface khai báo default method** cũng cần initialization trong quá trình initialize class ấy.
- Superinterface **không có default method** không nhất thiết initialized vào thời điểm class implementation được initialized; nó có thể chờ active use riêng như đọc static field không phải constant variable.
- “Interface field” là `public static final` theo ngôn ngữ, nhưng điều đó **không có nghĩa tất cả field đều là compile-time constants**. Một field được khởi tạo bằng lời gọi method không là compile-time constant.

Trong ví dụ mục 6, `WithDefault` chứa `int TOKEN = mark(...)` và default method `unused()`: việc Child initialization in `DEFAULT_INTERFACE_FIELD` là điều cần nhớ. `Plain` có `TOKEN = mark(...)` nhưng **không khai báo default method**; initialization của nó được trì hoãn tới lần đọc `Plain.TOKEN`.

Không suy ra Java source chỉ có cú pháp `interface` thì sẽ in initializer khi được nhắc tên. **Dấu vết phụ thuộc quy tắc active use và quá trình initialize class liên quan**, không phải mức độ gần nhau của khai báo trong file.

### Một caveat cấp compiler

Compiler có thể tạo **synthetic default methods** trong những trường hợp nhất định. JLS có ghi chú rằng default-method superinterface initialization có thể không hoàn toàn hiển nhiên từ source code. Khi làm bài yêu cầu kết quả **exact bytecode cụ thể**, cần biết compiler/version và class file thực. Với ví dụ Java 17 tự viết ở mục 6, cấu trúc `default void unused(){}` là rõ ràng.

## 9. Bài thực hành Java 17 thứ ba: circular class initialization

Điều khiến nhiều người ngạc nhiên là **preparation** đặt static fields về giá trị mặc định trước khi code `<clinit>` chạy. Nếu hai class lần lượt khởi tạo nhau trong cùng thread, một class đang initialization có thể bị đọc khi field chưa nhận initializer value.

Tạo file **`CircularInitDemo.java`**:

~~~java
public final class CircularInitDemo {
    static class A {
        static int value = B.value + 1;
        static { System.out.println("A_INIT=" + value); }
    }

    static class B {
        static int value = A.value + 1;
        static { System.out.println("B_INIT=" + value); }
    }

    public static void main(String[] args) {
        System.out.println("RESULT=" + A.value);
        System.out.println("AGAIN=" + B.value);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 CircularInitDemo.java
java CircularInitDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
B_INIT=1
A_INIT=2
RESULT=2
AGAIN=1
~~~

Giải:

1. Main đọc `A.value`. JVM chuẩn bị A với `A.value` mặc định bằng **0**, bắt đầu initialize A.
2. Initializer của A cần `B.value`, nên JVM bắt đầu initialize B; B cũng đã được chuẩn bị nên `B.value` mặc định **0**.
3. Initializer của B đọc `A.value` khi A đang được initialization bởi **chính thread này**. Quy tắc cho phép tiếp tục sử dụng trạng thái hiện có thay vì chạy A initializer lần thứ hai. `A.value` lúc ấy vẫn bằng **0**.
4. B gán `B.value = 0 + 1 = 1` rồi in `B_INIT=1`; B initialization hoàn tất.
5. A tiếp tục, gán `A.value = 1 + 1 = 2`, in `A_INIT=2`; A initialization hoàn tất.
6. Caller in `RESULT=2`; lần đọc B sau đó chỉ lấy `B.value = 1`, in `AGAIN=1`. Không có static initializer nào lặp lại.

**Không suy diễn:** circular initialization trên **nhiều thread** phức tạp hơn, có thể dẫn tới class initialization deadlock khi hai thread chờ nhau; chương trình này chỉ có một main thread truy cập A trước. Đừng nghĩ “mọi circular init luôn trả 0 rồi chạy bình thường” hoặc mọi trường hợp đều có thứ tự in như ví dụ.

### Nếu đổi mốc đầu tiên từ A sang B?

Nếu `main` đọc `B.value` trước, vòng khởi tạo bắt đầu ở B; với logic hai field đối xứng, các giá trị và thứ tự in có thể đổi. Muốn dự đoán, **vẽ đường truy cập chính xác**; không nhìn thứ tự class được khai báo trong source để quyết định class nào khởi tạo trước.

## 10. Cách đọc class-load và class-init traces của JVM

Ở HotSpot/OpenJDK/JDK 17+, Unified Logging có thể ghi riêng sự kiện nạp và khởi tạo:

~~~bash
java '-Xlog:class+load=info,class+init=info' InitOrderDemo
~~~

Hoặc chỉ xem class load:

~~~bash
java -Xlog:class+load=info InitOrderDemo
~~~

Hoặc class initialization:

~~~bash
java -Xlog:class+init=info InitOrderDemo
~~~

**Chú ý:** nhiều trăm sự kiện liên quan thư viện nền JVM có thể xuất hiện, đôi khi **trước khi main bắt đầu**. Thứ tự/số lượng và định dạng log phụ thuộc JVM, JDK build, class data sharing, collector, agents, classpath và cấu hình. Do đó **đầu ra logging không được xem là stdout cố định** của ví dụ.

Có thể ghi VM logging vào file và giữ stdout chương trình dễ đọc hơn:

~~~bash
java '-Xlog:class+load=info,class+init=info:file=class-trace.log:uptime,level,tags' InitOrderDemo
~~~

Phân biệt rõ ba loại thông tin:

| Thông tin | Cho biết gì? | Không cho biết gì? |
| --- | --- | --- |
| `[class,load]` event | VM ghi nhận một class được load, thường có tên/nguồn | Không chứng minh static block đã thực thi |
| `[class,init]` event | VM bắt đầu hoặc thực hiện thao tác initialization của kiểu theo cơ chế logging | Không phải câu lệnh `println` của initializer; có thể class không có `<clinit>` |
| Dòng `PARENT_FIELD`/`CHILD_BLOCK` từ Java | Một câu lệnh trong static initializer đã chạy tới vị trí in | Không mô tả tất cả class đã được load |

**Quan trọng khi lọc log:** nếu chỉ tìm tên `Child` trong file class-load log, bạn có thể thấy cả `InitOrderDemo$Child` lẫn những class JDK có chữ `Child`. Lọc tên đầy đủ và tag log, kiểm tra loader/source khi có. Dấu `$` trong binary name của nested class là ký tự thực, không phải biểu thị nested scope của shell.

### `javap -c -p` giúp gì?

~~~bash
javap -c -p InitOrderDemo
javap -c -p 'InitOrderDemo$Child'
javap -c -v -p 'InitOrderDemo$Constants'
~~~

Ở Bash, nháy đơn giữ ký tự `$` trong nested class name. PowerShell cũng có thể dùng nháy đơn. `javap` là **disassembly tĩnh**, không phải log lớp đã nạp trong JVM đang chạy.

Quan sát:

- Method `<clinit>` nếu class có logic static initialization cần thực thi.
- `getstatic`/`putstatic` trong các method/initializer.
- `invokestatic` cho static method calls.
- `new`, `dup`, `invokespecial <init>` khi tạo instance.
- `ConstantValue` attribute của compile-time constant field.
- Các method constructor `<init>` khác hoàn toàn `<clinit>`.

**Dùng `javap` để đối chiếu tại sao một dòng Java được biên dịch ra hành vi ấy**, không dùng constant-pool reference như chứng cứ tự động class đã initialized.

## 11. Quy trình chuẩn để giải bài dự đoán output

Khi gặp một đoạn code 10–100 dòng gồm nhiều lớp, hãy làm theo **từng sự kiện runtime**:

### Bước 1 — Liệt kê những lớp/interface liên quan và dòng in

Viết một bảng:

| Runtime type | Static fields/blocks in gì? | Constructor in gì? |
| --- | --- | --- |
| Parent | `PARENT_FIELD`, `PARENT_BLOCK` | `PARENT_CONSTRUCTOR` |
| WithDefault | `DEFAULT_INTERFACE_FIELD` | Interface không có constructor instance |
| Plain | `PLAIN_INTERFACE_FIELD` | Interface không có constructor |
| Child | `CHILD_FIELD`, `CHILD_BLOCK` | `CHILD_CONSTRUCTOR` |
| Constants | `CONSTANTS_BLOCK`, `CONSTANTS_COMPUTED` | Không có instance trong bài |

Không dùng thứ tự khai báo file làm thứ tự initialization toàn cục. Các kiểu được initialized theo **hành động thực thi**, với ngoại lệ về superclass/default method superinterfaces.

### Bước 2 — Đánh dấu active-use points

Ví dụ:

~~~text
Child.class.getSimpleName() → class literal, NO forced Child init
Constants.MAGIC            → compile-time constant, NO forced Constants init
new Child()                → initialize Parent / WithDefault / Child
Plain.TOKEN                → initialize Plain
Child.ping()               → Child already initialized
Constants.NON_CONSTANT     → initialize Constants
~~~

Với mỗi active use, kiểm tra loại đã initialized chưa.

### Bước 3 — Dùng trạng thái mỗi runtime class

Mô hình thực dụng:

~~~text
UNINITIALIZED
    |
    v
INITIALIZATION_IN_PROGRESS(thread X)
    |
    +--- success ---> INITIALIZED
    |
    +--- abrupt ---> ERRONEOUS
~~~

Nghĩa là **một lần initialization thành công**; các active uses sau không chạy lại initializer. Khi initialization lỗi, class có thể ở trạng thái erroneous và không thể tự retry initialization trong cùng runtime identity.

### Bước 4 — Triển khai dependency order

Trước khi chạy static logic của Child:

1. Khởi tạo superclass Parent nếu chưa initialized.
2. Theo quy tắc hiện đại, khởi tạo các superinterfaces cần thiết có default methods.
3. Thực thi static fields và static blocks của Child theo thứ tự source.
4. Khi `new Child()`, sau class initialization còn tới **constructor chain**.

Nếu superclass hoặc superinterface initialization thất bại, có thể không chạy được static logic của subclass, và stack trace/exception thay thế đường output bình thường.

### Bước 5 — Tính giá trị field cẩn thận

- Primitive fields có default 0/false; reference fields có default null **trong preparation**.
- Các compile-time constants có quy tắc `ConstantValue`/inline khác.
- Khi circular initialization, truy cập field chưa gán có thể thấy default.
- Static field initializer có side effect được thực thi theo thứ tự source.
- Một field mutable có thể bị thay đổi sau initialization; không mặc định giá trị mãi như ban đầu.

### Bước 6 — In kết quả theo đường thực thi, không đoán từ load log

Đối với mỗi `println`, điền chính xác giá trị biểu thức và các side effects xảy ra **trước khi println hoàn tất**. Ví dụ:

~~~java
System.out.println("RESULT=" + Feature.compute());
~~~

Java phải đánh giá biểu thức nối chuỗi, trong đó **gọi `Feature.compute()`** trước khi `println` in dòng kết quả. Nếu Feature initialization in thông báo, dòng ấy sẽ xuất hiện **trước** `RESULT=...`.

Đây là nguyên nhân của các dòng init log “chen vào” giữa hai dòng in của main.

### Bước 7 — Phân biệt stdout/stderr, threads và VM logging

Nếu static initializer chạy trên nhiều thread hoặc có `System.err.println`, thứ tự hiển thị khi gộp streams có thể phụ thuộc scheduling và logger. Trong các bài ví dụ trên, chỉ có main thread và tất cả log ứng dụng đều dùng `System.out.println`, nên thứ tự là cố định.

Class-load logging thường ghi rất nhiều dòng độc lập; muốn lấy “stdout chính xác của source” hãy chạy **không bật VM log** hoặc tách VM log vào file.

## 12. Một số bẫy thường gặp

### 12.1. “JVM load rồi nên static initializer đã chạy”

**Sai.** Loading và initialization là những pha khác nhau. `Feature.class` hoặc `Class.forName(name,false,loader)` minh họa rõ: JVM có thể biết class trước khi static block in.

### 12.2. “Thấy Sub.FIELD thì Sub chắc chắn initialized”

**Sai.** Field có thể được **khai báo trong superclass**, hoặc là compile-time constant được inline. Xác định declaring class/interface và cách field được sử dụng trước khi dự đoán.

### 12.3. “Mọi interface được initialized trước implementing class”

**Sai.** Có quy tắc đặc biệt dành cho superinterfaces khai báo **default methods**, không phải khẳng định mọi interface đều initialized như superclass.

### 12.4. “Cứ có `static final` là không in initializer”

**Sai.** Chỉ những *constant variables* theo định nghĩa Java mới có ngoại lệ đọc không kích hoạt initialization. `static final Integer` hoặc `static final int` gán từ lời gọi method không phải trường hợp đó.

### 12.5. “Static initializer luôn chạy đúng một lần trong cả hệ điều hành”

**Sai.** Trạng thái initialization gắn với **runtime class identity**, vốn chịu ảnh hưởng defining class loader. Hai loader độc lập có thể define cùng binary name và initialize mỗi lớp một lần. Khởi chạy process JVM khác cũng có lifecycle riêng.

### 12.6. “Một lần `<clinit>` lỗi, lần sau JVM tự retry”

**Sai.** Nếu initialization thất bại, class đi vào trạng thái erroneous theo quy tắc; lần active use sau có thể nhận `NoClassDefFoundError` (với cause liên quan) thay vì thử chạy static initializer mới.

### 12.7. “Class loader log hiển thị cùng thứ tự trên mọi máy”

**Sai.** Tải/resolve có thể sớm, phụ thuộc VM, shared class data, framework, agents và scheduling. Hãy ưu tiên quan hệ **active use/initialization theo đặc tả** để dự đoán những dòng code ứng dụng.

### 12.8. “Constructor chạy trước static block của subclass”

**Sai** với lần tạo instance đầu tiên thông thường: class cần initialized trước; constructor chain diễn ra trong quá trình tạo object sau đó.

## 13. Khi initialization thất bại thì log và lần sử dụng sau ra sao?

Xét code minh họa:

~~~java
class Unstable {
    static int port = Integer.parseInt("not-a-number");
    static {
        System.out.println("NEVER_REACHED");
    }
}
~~~

Đây là một lớp minh họa **không có main**. Nếu chương trình active-use Unstable và bước `parseInt` ném `NumberFormatException`, static block ở phía sau **không chạy**, nên `NEVER_REACHED` không được in. JVM hoàn tất class initialization một cách bất thường, thường bao bọc exception phù hợp vào `ExceptionInInitializerError` khi cần theo JVMS. Khi tiếp tục cố sử dụng **cùng runtime class** lần sau, có thể nhận `NoClassDefFoundError: Could not initialize class ...`.

Lưu ý:

- Lỗi ném từ static initializer không tự có nghĩa JVM kết thúc ngay; thread và caller có thể catch Throwable phù hợp, nhưng đây là lỗi nghiêm trọng không nên che giấu.
- Một `Error` phát sinh trong initializer có thể được xử lý theo quy tắc khác với exception thông thường; không khẳng định mọi Throwable luôn được bọc giống nhau.
- Không gọi thủ công `<clinit>` để “thử lại”. Không có API Java hợp lệ nhằm reset initialization state của cùng class.
- Để tái thử logic nghiệp vụ có thể lỗi, hãy chuyển nó thành **method initialization chủ động** có trạng thái/retry rõ ràng thay vì phụ thuộc static initializer tự chạy lại.
- Nếu tạo một class mới cùng binary name bằng **loader phiên khác**, đó là một runtime identity mới, nhưng lại kéo theo bài toán dependency/class-loader boundaries riêng.

Đối với môi trường production, hạn chế I/O không kiểm soát, network call blocking và dependency vòng ở static initialization. Dùng logging và chẩn đoán cause đầu tiên; thông báo cuối của `NoClassDefFoundError` đôi khi không chỉ ra nguyên nhân sâu nhất.

## 14. Class initialization và nhiều thread

JVMS quy định quá trình class/interface initialization được **đồng bộ** cho mỗi runtime class. Khi thread T1 đang initialize A và T2 cùng cần A, T2 có thể phải chờ A hoàn tất; không có hai thread cùng thực thi initializer của **chính cùng runtime class** một cách độc lập.

Tuy nhiên:

- Các initializer của **hai class khác nhau** có thể chạy trên các thread khác nhau và interleave dòng log.
- Nếu A initializer chờ B và B initializer chờ A qua các thread, **class initialization deadlock** có thể xảy ra.
- `System.out.println` trên nhiều thread không cung cấp quy tắc “theo thứ tự source toàn chương trình”; chỉ có thứ tự theo từng thread và các quan hệ đồng bộ cụ thể.
- Trong bài dự đoán stdout có threads, phải xem happens-before, locks, join, thread scheduling và mối quan hệ giữa các initializer; không gán một thứ tự tuyệt đối khi đặc tả không bảo đảm.

Ví dụ:

~~~text
Thread 1: cần initialize A → trong A.<clinit> chờ B
Thread 2: cần initialize B → trong B.<clinit> chờ A

Hai thread có thể bị mắc kẹt nếu giữ initialization locks
và mỗi bên cần class mà bên kia đang initialize.
~~~

Đây là sơ đồ điều kiện, **không phải một output Java cố định**. Dự đoán chính xác cần mã Java đầy đủ, cách đồng bộ và giả định scheduler.

## 15. Loading trace, class identity và “một lần” khi có nhiều loaders

Hai class có **cùng binary name** nhưng được **hai defining class loaders khác nhau** định nghĩa là hai runtime classes. Mỗi class có initialization state và static fields riêng. Vì vậy VM log có thể ghi cùng tên class xuất hiện hai lần với loader metadata khác nhau; hai static initializers có thể in cùng nhãn nhưng mỗi cái thuộc một runtime class.

Điều này thường xuất hiện ở:

- Plugin/hot-reload với child loader mỗi phiên.
- Application servers có deployment classloader riêng.
- Test runners hoặc framework cô lập dependencies.
- Runtime-generated classes/proxies.

Khi muốn dự đoán stdout của app có nhiều loader, thêm **cột defining loader** vào bảng theo dõi. “Tên class đã initialized” không đủ nếu có hai runtime identities.

Cũng đừng tưởng `Class.getClassLoader()` trả một object Java cho bootstrap loader trong mọi trường hợp: đối với class bootstrap, API thường trả `null` theo hợp đồng.

## 16. Luyện tập dự đoán nhanh

### Câu 1 — Class literal

~~~java
Class<?> c = Unused.class;
System.out.println("KNOWN");
~~~

Giả sử `Unused` có `static { System.out.println("INIT"); }`. Chỉ hai câu trên có đảm bảo in `INIT` không?

**Không.** Class literal không tự yêu cầu initialization; dòng có thể được đảm bảo từ code hiển thị là `KNOWN` (bỏ qua log JVM riêng và tác động ngoài ví dụ).

### Câu 2 — Static final

~~~java
static final int A = 3;
static final Integer B = 3;
~~~

Đọc trường nào có thể không initialize owner? **A** là constant variable nếu declaration phù hợp; B là reference và không phải compile-time constant variable.

### Câu 3 — Parent/Child

Gọi `new Child()` lần đầu với Parent static block in `P`, Child static block in `C`, constructor Parent in `p`, constructor Child in `c`. Thứ tự?

~~~text
P
C
p
c
~~~

Nếu gọi lần hai sau khi cả hai initialized thành công, chỉ thêm `p`, `c`.

### Câu 4 — Interface field

`interface I { int X = compute(); }`, trong đó compute in `I_INIT` và trả 5. Nếu chỉ tham chiếu `I.class`, có đảm bảo `I_INIT` không? **Không.** Nếu đọc `I.X` khi I chưa initialized, **có**.

### Câu 5 — Circular fields

Trong bài CircularInitDemo, vì sao `B_INIT=1` in trước `A_INIT=2`? Vì A initializer **đọc B.value** trước khi A field được gán, kéo B initialization; B đọc A default 0.

### Câu 6 — Logging

`[class,load] demo.Feature` có đủ chứng minh đã chạy Feature static block không? **Không**. Muốn chứng minh thực thi block, xem log/dấu vết bên trong initializer hoặc class-init event theo đúng ý nghĩa của nó.

### Câu 7 — Read before println

Vì sao trong `System.out.println("VALUE=" + Target.NON_CONSTANT)` dòng `TARGET_INIT` có thể xuất hiện **trước** dòng `VALUE=...`? Vì Java phải **đánh giá biểu thức đối số println** (gồm getstatic và class initialization nếu cần) trước khi gọi println để in chuỗi.

### Câu 8 — Hai class loaders

Một plugin class cùng binary name được defining loader A và B định nghĩa. Static initializer của chúng có bị giới hạn chỉ chạy một lần tổng cộng không? **Không**; mỗi runtime class có initialization state riêng.

### Câu 9 — Initialization lỗi

Một class bị lỗi trong `<clinit>`. Lần active use sau có bảo đảm chạy lại `<clinit>` không? **Không**; trạng thái erroneous thường khiến JVM phát lỗi khi dùng tiếp.

### Câu 10 — JVM log và stdout

Có thể khẳng định thứ tự **mọi** dòng `[class,load]` trên JDK 17 và 21 sẽ hoàn toàn giống nhau không? **Không**. Chỉ dự đoán những quan hệ đã được spec hoặc source bảo đảm.

## 17. Nguồn đọc sâu

- **Java Language Specification 17, §12.4.1 – When Initialization Occurs:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1
- **JLS 17, §12.4.2 – Detailed Initialization Procedure:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2
- **Java Virtual Machine Specification 17, §5.3 – Loading:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- **JVMS 17, §5.4 – Linking:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4
- **JVMS 17, §5.5 – Initialization:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- **JVMS 17, §4.7.2 – ConstantValue:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.2
- **JDK 17 java launcher tool:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **JDK 17 javap:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html

**Kết luận:** muốn dự đoán output trong bài JVM class initialization, hãy tách **class-load log** khỏi **initializer stdout**; đánh dấu chính xác **active use**, xét **superclass và superinterfaces khai báo default methods**, thực thi **static fields/blocks theo thứ tự văn bản**, phân biệt **constructor với `<clinit>`**, và nhớ mỗi runtime class chỉ initialized thành công một lần. Với **constant variables**, **class literal**, **`Class.forName(false)`** và **circular initialization**, không được áp dụng máy móc nguyên tắc “nhắc đến tên class là in static block”.
