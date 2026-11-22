# Lỗi khởi tạo lớp và bài thực nghiệm dự đoán thứ tự in trong Java

**Thứ tự khởi tạo** là một chủ đề dễ nhầm khi học Java Core: lúc nào `static` block chạy, field initializer thực thi trước hay sau constructor, lớp cha có khởi tạo trước lớp con hay không, và vì sao lần sử dụng một class thất bại có thể ném `ExceptionInInitializerError` nhưng lần tiếp theo lại ném `NoClassDefFoundError`?

Muốn dự đoán **stdout** chính xác, cần phân biệt **khởi tạo class** và **khởi tạo object**, rồi theo dõi các điểm mà Java bắt buộc thực thi static initializers. Khi static initialization thất bại, cần hiểu trạng thái class sau lỗi: JVM không đơn giản thử chạy lại cùng một static block mỗi lần có người truy cập.

Bài học này thuộc **Java core - class-object**, phần **Thứ tự khởi tạo**. Mỗi bài thực nghiệm chạy độc lập bằng **Java 17+**, có tên file, lệnh `javac`/`java`, kết quả chuẩn và lời giải. Các trường hợp cố ý không biên dịch hoặc chỉ là đoạn minh họa đều được phân biệt rõ.

## 1. Kết quả cần đạt

Sau khi học, bạn cần tự trả lời được:

1. Khi nào JVM chạy các biểu thức gán `static` field và `static { ... }`?
2. Vì sao một `static final` compile-time constant có thể được đọc mà **không** kích hoạt khởi tạo class?
3. Lớp cha, lớp con, instance fields, instance initializer blocks và constructor xuất hiện theo thứ tự nào?
4. Vì sao field được đọc sớm qua method có thể vẫn bằng `0`, `false` hoặc `null`?
5. Tại sao class initialization thất bại thường gây `ExceptionInInitializerError`, còn lần dùng tiếp có thể gây `NoClassDefFoundError`?
6. Exception trong **constructor instance** khác gì exception khi **khởi tạo class**?
7. Làm sao dự đoán output bằng một bảng trạng thái, thay vì đoán theo thứ tự dòng `println` trong source?

Khái niệm cốt lõi: **một class runtime được initialized theo quy tắc JVM**, còn **mỗi object** có quy trình khởi tạo instance riêng.

## 2. Ba giai đoạn của class và giai đoạn tạo object

Trước hết hãy tách hai cấp độ.

Ở cấp class/interface, JVM thực hiện những hoạt động phù hợp:

~~~text
Loading
  -> Linking (verification, preparation, resolution theo quy tắc JVM)
  -> Initialization khi có lý do phải khởi tạo class/interface

Class initialization:
  thực thi static field initializers và static initializer blocks
  theo thứ tự quy định
~~~

Ở cấp instance, khi gọi `new SomeClass()`:

~~~text
Yêu cầu class sẵn sàng/initialized
  -> cấp phát object và thiết lập mặc định cho instance fields
  -> đi qua chuỗi constructor superclass/subclass
  -> chạy instance field initializers và instance initializer blocks
  -> chạy thân constructor thích hợp
  -> trả object nếu tạo thành công
~~~

**Loading không đồng nghĩa initialization.** Một class có thể đã được nạp hoặc liên kết nhưng chưa chạy static block. Ngược lại, một static block in ra console chỉ chứng minh giai đoạn initialization của class ấy đã bắt đầu thực thi, không chứng minh thời điểm class file lần đầu được nạp.

**Preparation không gọi** các phương thức trong biểu thức `static int x = compute();`: nó chuẩn bị storage/giá trị ban đầu cho static fields. Lời gọi `compute()` thuộc static initialization. Tham chiếu được phân giải (*resolution*) có thể được JVM xử lý sớm hoặc trì hoãn theo đặc tả; không nên coi toàn bộ resolution là một dòng sự kiện dễ quan sát bằng `println`.

## 3. Những hành động kích hoạt class initialization

Theo [JLS 17 §12.4.1](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1), các tình huống chủ chốt bao gồm:

| Hành động | Ảnh hưởng tới initialization |
| --- | --- |
| `new Target()` | Target phải được initialized trước khi tạo instance thích hợp |
| Gọi static method được Target **khai báo** | Target được initialized nếu chưa |
| Đọc static field Target khai báo và **không phải constant variable** | Target được initialized |
| Gán static field | Class/interface khai báo field phải được initialized |
| Một số lời gọi reflection yêu cầu initialization | Phụ thuộc API và tham số |
| JVM bắt đầu chạy `Main.main` | Main class được initialized trước khi chạy `main` |
| Truy cập field inherited bằng tên subclass | Xét **class thực sự khai báo field**, không chỉ tên đứng trước dấu chấm |

Những việc **không tự buộc Target initialized** chỉ vì chúng xuất hiện trong source:

- Viết `Target.class` để lấy class literal.
- Viết `new Target[3]` để tạo mảng tham chiếu.
- Khai báo `Target reference;`.
- Đọc một `static final` trường nguyên thủy/`String` là **constant variable** được tính bằng *constant expression*.
- `Class.forName(name, false, loader)`: yêu cầu tìm/nhận `Class` mà **không yêu cầu initialization** của class đó.

Không thể dự đoán static output nếu chưa chỉ ra **hành động nào là active use đầu tiên** của class cần xét.

## 4. Thực nghiệm 1: `main` class, constant, static block và constructor

Tạo tệp **`FirstUseOrderDemo.java`**:

~~~java
class Warmup {
    static final int CONSTANT = 7;
    static int value = announce("Warmup.value", 3);

    static {
        System.out.println("Warmup.block value=" + value);
    }

    static int announce(String label, int result) {
        System.out.println(label);
        return result;
    }

    Warmup() {
        System.out.println("Warmup.constructor");
    }
}

public class FirstUseOrderDemo {
    static {
        System.out.println("Main.initialized");
    }

    public static void main(String[] args) {
        System.out.println("main.begin");
        System.out.println("constant=" + Warmup.CONSTANT);
        System.out.println("after.constant");
        System.out.println("value=" + Warmup.value);
        new Warmup();
        new Warmup();
        System.out.println("main.end");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 FirstUseOrderDemo.java
java FirstUseOrderDemo
~~~

**Stdout chính xác:**

~~~text
Main.initialized
main.begin
constant=7
after.constant
Warmup.value
Warmup.block value=3
value=3
Warmup.constructor
Warmup.constructor
main.end
~~~

**Phân tích:** JVM initialized `FirstUseOrderDemo` trước khi chạy `main`, nên dòng `Main.initialized` xuất hiện trước `main.begin`. `Warmup.CONSTANT` là một compile-time constant, vì vậy câu lệnh đọc nó không tự kích hoạt `Warmup` initialization.

Đến `Warmup.value` (static field không phải constant variable), Java mới cần initialized `Warmup`. Initializer gọi `announce` trước, static block chạy sau. Khi class initialized thành công, hai lần `new Warmup()` chỉ gọi constructor **hai lần**; static block không lặp lại.

**Đừng suy luận sai:** việc `Warmup.value` chạy sau `constant=7` không khẳng định chính xác JVM đã load file `Warmup.class` vào thời điểm nào. Thứ ta dự đoán ở đây là **initialization output**.

## 5. Quy tắc ưu tiên khi cùng class có nhiều static initializers

Trong một class, **static field initializers** và **static initializer blocks** thực thi theo thứ tự xuất hiện trong source, sau khi các điều kiện khởi tạo lớp đã thỏa mãn.

Ví dụ minh họa:

~~~java
class StaticPlan {
    static int a = print("a", 1);
    static {
        System.out.println("block 1");
    }
    static int b = print("b", 2);
    static {
        System.out.println("block 2");
    }

    private static int print(String label, int result) {
        System.out.println(label);
        return result;
    }
}
~~~

Đây là **class minh họa hợp lệ**, không có `main`. Khi initialized, output của riêng static code lần lượt là:

~~~text
a
block 1
b
block 2
~~~

Một lỗi thường gặp là tưởng tất cả static field initializers chạy trước toàn bộ static blocks. **Không đúng**: field initializers và blocks **xen kẽ theo thứ tự textual**.

Riêng những trường là *constant variables* có xử lý hằng số đặc biệt, không nên dùng chúng để suy ra thời điểm chạy biểu thức initializer như đối với `static int x = method();`.

## 6. Thực nghiệm 2: static trước, constructor lớp cha và con theo từng object

Tạo tệp **`ParentChildTraceDemo.java`**:

~~~java
class ParentTrace {
    static {
        System.out.println("Parent.static");
    }

    int baseValue = mark("Parent.field", 10);

    {
        System.out.println("Parent.instance block");
    }

    ParentTrace() {
        System.out.println("Parent.constructor");
    }

    static int mark(String name, int value) {
        System.out.println(name);
        return value;
    }
}

class ChildTrace extends ParentTrace {
    static {
        System.out.println("Child.static");
    }

    int childValue = mark("Child.field", 20);

    {
        System.out.println("Child.instance block");
    }

    ChildTrace() {
        System.out.println("Child.constructor");
    }
}

public class ParentChildTraceDemo {
    public static void main(String[] args) {
        System.out.println("begin");
        new ChildTrace();
        System.out.println("again");
        new ChildTrace();
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ParentChildTraceDemo.java
java ParentChildTraceDemo
~~~

**Stdout chính xác:**

~~~text
begin
Parent.static
Child.static
Parent.field
Parent.instance block
Parent.constructor
Child.field
Child.instance block
Child.constructor
again
Parent.field
Parent.instance block
Parent.constructor
Child.field
Child.instance block
Child.constructor
~~~

Lần đầu tạo `ChildTrace`, JVM bảo đảm **ParentTrace initialized trước ChildTrace**. Sau đó là giai đoạn khởi tạo object: instance field initializer và instance block của `ParentTrace`, thân constructor cha, rồi initializer/block và constructor của `ChildTrace`.

Lần tạo thứ hai không lặp static initialization, nhưng **mỗi object mới** lại chạy các initializer/constructor instance.

**Cần phân biệt:** “lớp cha initialized trước lớp con” là một quan hệ ở **cấp class**. “constructor cha chạy trước constructor con” là quan hệ ở **cấp object**. Hai điều xảy ra ở hai tầng khác nhau, dù cùng có thể được kích hoạt bởi một câu `new ChildTrace()`.

## 7. Thực nghiệm 3: đọc static field quá sớm sẽ thấy giá trị mặc định

Tại **preparation**, static fields thông thường nhận giá trị mặc định thích hợp trước khi static initializers chạy. Khi một static initializer gọi helper method mà helper đọc field chưa đến lượt gán, nó có thể quan sát giá trị mặc định.

Tạo tệp **`StaticForwardReadDemo.java`**:

~~~java
class ForwardState {
    static int early = computeEarly();
    static int later = 10;

    static {
        System.out.println("block later=" + later);
    }

    private static int computeEarly() {
        System.out.println("during later=" + later);
        return later + 1;
    }
}

public class StaticForwardReadDemo {
    public static void main(String[] args) {
        System.out.println("begin");
        System.out.println("early=" + ForwardState.early);
        System.out.println("later=" + ForwardState.later);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 StaticForwardReadDemo.java
java StaticForwardReadDemo
~~~

**Stdout:**

~~~text
begin
during later=0
block later=10
early=1
later=10
~~~

Khi `computeEarly()` chạy, `later` chưa tới lượt initializer `= 10`, nên nó là `0`. Sau khi `early` đã nhận `1`, lệnh gán `later=10` **không tính lại `early`**.

**Không khuyến nghị phụ thuộc vào giá trị mặc định do đọc quá sớm.** Nếu `early` thật sự cần `later=10`, đặt initializer của `later` trước hoặc dùng thiết kế khởi tạo rõ ràng.

Java còn có quy tắc **illegal forward reference** (JLS §8.3.3): `static int x = y; static int y = 10;` có thể không biên dịch do đọc tên đơn giản quá sớm. Ví dụ hoàn chỉnh ở trên **hợp lệ** vì phép đọc `later` nằm trong **thân method**, nơi quy tắc hạn chế trực tiếp ấy không ngăn. “Compiler cho phép” không đồng nghĩa “giá trị lúc đọc đã như mong muốn”.

## 8. `static final` không phải lúc nào cũng kích hoạt initialization

Phân biệt:

~~~java
static final int FIXED = 12;
static final String LABEL = "OK";
static final int COMPUTED = Integer.parseInt("13");
~~~

Hai field đầu là **constant variables** (kiểu nguyên thủy hoặc `String`, `final`, initializer là constant expression). Field `COMPUTED` không phải constant variable vì initializer gọi method.

Tạo tệp **`ConstantTriggerDemo.java`**:

~~~java
class ConfigTokens {
    static final int FIXED = 12;
    static final String LABEL = "OK";
    static final int COMPUTED = compute();

    static {
        System.out.println("ConfigTokens.static");
    }

    private static int compute() {
        System.out.println("ConfigTokens.compute");
        return 13;
    }
}

public class ConstantTriggerDemo {
    public static void main(String[] args) {
        System.out.println("start");
        System.out.println("fixed=" + ConfigTokens.FIXED);
        System.out.println("label=" + ConfigTokens.LABEL);
        System.out.println("computed=" + ConfigTokens.COMPUTED);
        System.out.println("end");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ConstantTriggerDemo.java
java ConstantTriggerDemo
~~~

**Stdout:**

~~~text
start
fixed=12
label=OK
ConfigTokens.compute
ConfigTokens.static
computed=13
end
~~~

Đọc `FIXED` và `LABEL` **không tự initialized `ConfigTokens`**. Lần đầu đọc `COMPUTED` mới yêu cầu initialization; JVM thực hiện initializer gọi `compute()`, rồi static block.

**Cảnh báo:** đừng coi mọi field có `static final` là compile-time constant. `static final Integer n = 12` không phải constant variable theo định nghĩa JLS, vì `Integer` không phải kiểu primitive hoặc `String`.

## 9. Class literal, mảng và reflection có thể trì hoãn initialization

Tạo tệp **`DeferredInitializationDemo.java`**:

~~~java
class Deferred {
    static {
        System.out.println("Deferred.static");
    }

    static int count = 5;

    Deferred() {
        System.out.println("Deferred.constructor");
    }
}

public class DeferredInitializationDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("begin");

        Class<?> type = Deferred.class;
        System.out.println("literal=" + type.getSimpleName());

        Deferred[] array = new Deferred[2];
        System.out.println("array=" + array.length);

        ClassLoader loader =
                DeferredInitializationDemo.class.getClassLoader();
        Class<?> metadata =
                Class.forName("Deferred", false, loader);
        System.out.println("loaded=" + metadata.getSimpleName());

        System.out.println("before forName");
        Class.forName("Deferred");
        System.out.println("after forName");

        new Deferred();
        System.out.println("count=" + Deferred.count);
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 DeferredInitializationDemo.java
java DeferredInitializationDemo
~~~

**Stdout:**

~~~text
begin
literal=Deferred
array=2
loaded=Deferred
before forName
Deferred.static
after forName
Deferred.constructor
count=5
~~~

Phân tích:

- `Deferred.class` lấy `Class` object mà không tự yêu cầu initialized `Deferred`.
- `new Deferred[2]` chỉ tạo **array object** có hai slot reference ban đầu là `null`, chưa tạo hai đối tượng `Deferred`.
- `Class.forName("Deferred", false, loader)` có thể yêu cầu loading/linking để có metadata nhưng **không yêu cầu initialization**.
- `Class.forName("Deferred")` một tham số **yêu cầu initialization**, nên static block in trước `after forName`.
- `new Deferred()` sau đó chỉ chạy constructor instance; `Deferred.static` không in lần nữa.

Chú ý `Class.forName(name)` chỉ yêu cầu khởi tạo class chứ **không tạo một instance Deferred**. `ClassNotFoundException` xuất hiện nếu không tìm được class theo tên; đó là lỗi khác với exception xảy ra **trong static initializer** của class đã tìm được.

## 10. Static initialization thất bại: khái niệm class ở trạng thái lỗi

Một static field initializer hoặc static initializer block có thể thực hiện tính toán, đọc cấu hình hoặc gọi phương thức. Nếu một bước ném exception không được xử lý và class initialization không thể hoàn tất bình thường, JVM đánh dấu class đó **initialization failed/erroneous** theo thủ tục đặc tả.

Sơ đồ khái niệm:

~~~text
Class chưa được initialized
          |
          v
Một active use yêu cầu initialization
          |
          v
Chạy static initializers và static blocks
          |
          +---- thành công ---> Initialized
          |                     lần dùng sau không chạy lại static code
          |
          +---- ném lỗi ------> Erroneous
                                lần dùng sau không đơn giản thử lại
                                có thể gặp NoClassDefFoundError
~~~

**Điểm then chốt:** lỗi ở giai đoạn khởi tạo class không giống việc một lời gọi method bình thường ném exception. Class initialization là một thủ tục có trạng thái trong JVM, được chia sẻ bởi những code dùng **cùng runtime class**.

Nếu static initializer thất bại vì cấu hình sai, không thể giả định rằng sửa một biến môi trường rồi gọi lại class ấy trong cùng class loader sẽ khiến JVM tự chạy lại static initialization như lần đầu.

## 11. Thực nghiệm 4: lần đầu `ExceptionInInitializerError`, lần sau `NoClassDefFoundError`

Tạo tệp **`FailedClassInitializationDemo.java`**:

~~~java
class FaultySettings {
    static int port = loadPort();

    private static int loadPort() {
        System.out.println("FaultySettings.init");
        throw new IllegalStateException("invalid port");
    }
}

public class FailedClassInitializationDemo {
    private static void use() {
        System.out.println(FaultySettings.port);
    }

    public static void main(String[] args) {
        try {
            use();
        } catch (ExceptionInInitializerError ex) {
            System.out.println("first="
                    + ex.getClass().getSimpleName());
            System.out.println("cause="
                    + ex.getCause().getClass().getSimpleName());
        }

        try {
            use();
        } catch (NoClassDefFoundError ex) {
            System.out.println("second="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("main.end");
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 FailedClassInitializationDemo.java
java FailedClassInitializationDemo
~~~

**Stdout chính xác:**

~~~text
FaultySettings.init
first=ExceptionInInitializerError
cause=IllegalStateException
second=NoClassDefFoundError
main.end
~~~

### Lý giải từng dòng

1. `use()` lần đầu đọc `FaultySettings.port`: static field không constant, nên phải initialized `FaultySettings`.
2. `loadPort()` in `FaultySettings.init`, rồi ném `IllegalStateException`.
3. Theo quy tắc class initialization, khi nguyên nhân không phải một `Error`, JVM bọc exception thành **`ExceptionInInitializerError`**; `getCause()` trong ví dụ là `IllegalStateException`.
4. `FaultySettings` bị đánh dấu khởi tạo lỗi.
5. Lần `use()` thứ hai không khởi tạo lại class ấy; JVM ném **`NoClassDefFoundError`** trong tình huống này. Vì vậy không có dòng `FaultySettings.init` thứ hai.

**`NoClassDefFoundError` không luôn có nghĩa class file bị xóa.** Nó có thể là hậu quả trực tiếp của **class đã được tìm thấy nhưng không khởi tạo thành công trước đó**. Cần xem exception chain và lỗi đầu tiên trong log.

## 12. `Error` ném trong static initializer không nhất thiết bị bọc thêm

JLS §12.4.2 quy định cách xử lý nguyên nhân khởi tạo lỗi. Nếu exception/throwable gây thất bại **đã là một `Error`**, JVM không cần bọc nó thành `ExceptionInInitializerError` mới theo cùng trường hợp.

Tạo tệp **`ErrorDuringInitializationDemo.java`**:

~~~java
class BrokenContract {
    static int value = check();

    private static int check() {
        System.out.println("BrokenContract.init");
        throw new AssertionError("contract broken");
    }
}

public class ErrorDuringInitializationDemo {
    public static void main(String[] args) {
        try {
            System.out.println(BrokenContract.value);
        } catch (AssertionError ex) {
            System.out.println("first="
                    + ex.getClass().getSimpleName());
        }

        try {
            System.out.println(BrokenContract.value);
        } catch (NoClassDefFoundError ex) {
            System.out.println("second="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ErrorDuringInitializationDemo.java
java ErrorDuringInitializationDemo
~~~

**Stdout:**

~~~text
BrokenContract.init
first=AssertionError
second=NoClassDefFoundError
~~~

Khác với ví dụ trước, nguyên nhân là `AssertionError`, bản thân đã thuộc nhóm `Error`; do đó lần đầu caller bắt **`AssertionError`**, không phải một `ExceptionInInitializerError` được tạo để bọc `IllegalStateException`.

Lần yêu cầu sử dụng sau vẫn gặp `NoClassDefFoundError` vì class đã ở trạng thái initialization lỗi.

### Vì sao không viết `static { throw new RuntimeException(); }` trực tiếp?

Java có quy tắc **static initializer block phải có khả năng hoàn thành bình thường** theo phân tích compile-time. Một block chứa lệnh `throw` vô điều kiện như vậy bị compiler từ chối. Các ví dụ runnable ở đây dùng **static field initializer gọi method**, và method ném exception khi chạy. Đây là cách minh họa lỗi khởi tạo mà vẫn hợp lệ về cú pháp.

## 13. Thực nghiệm 5: exception trong constructor không làm class trở thành erroneous

Cùng là một exception, nhưng vị trí phát sinh thay đổi ý nghĩa.

Tạo tệp **`ConstructorExceptionDemo.java`**:

~~~java
class RetryableObject {
    static {
        System.out.println("RetryableObject.static");
    }

    RetryableObject(int amount) {
        System.out.println("constructor amount=" + amount);
        if (amount < 0) {
            throw new IllegalArgumentException("negative");
        }
    }
}

public class ConstructorExceptionDemo {
    public static void main(String[] args) {
        try {
            new RetryableObject(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }

        new RetryableObject(1);
        new RetryableObject(2);
        System.out.println("done");
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ConstructorExceptionDemo.java
java ConstructorExceptionDemo
~~~

**Stdout:**

~~~text
RetryableObject.static
constructor amount=-1
rejected=negative
constructor amount=1
constructor amount=2
done
~~~

Tại lời gọi `new RetryableObject(-1)` đầu tiên, **class initialization đã hoàn thành thành công** trước khi constructor chạy. Constructor ném `IllegalArgumentException`, nên chỉ việc tạo **instance đó** thất bại. Class vẫn initialized bình thường, vì vậy hai lời gọi tiếp theo có thể tạo object hợp lệ.

Đừng gộp tất cả lỗi xảy ra “gần từ khóa `new`” vào lỗi class initialization. Cần xác định exception ném **trong `<clinit>`** hay **trong chuỗi constructor/instance initializer**. Một lỗi trong instance field initializer cũng thuộc quá trình tạo instance, không tự làm class trở thành erroneous nếu class đã initialized.

## 14. Thực nghiệm 6: class con không chạy static block khi superclass initialization thất bại

Khi cần initialized subclass, JVM bảo đảm superclass cần thiết được initialized trước. Nếu superclass initialization thất bại, class con chưa thể chạy static initializers theo đường bình thường.

Tạo tệp **`FailedSuperclassDemo.java`**:

~~~java
class BadParent {
    static int value = read();

    private static int read() {
        System.out.println("BadParent.init");
        throw new IllegalStateException("bad parent config");
    }
}

class BlockedChild extends BadParent {
    static {
        System.out.println("BlockedChild.static");
    }

    BlockedChild() {
        System.out.println("BlockedChild.constructor");
    }
}

public class FailedSuperclassDemo {
    public static void main(String[] args) {
        try {
            new BlockedChild();
        } catch (ExceptionInInitializerError ex) {
            System.out.println("first="
                    + ex.getClass().getSimpleName());
        }

        try {
            new BlockedChild();
        } catch (NoClassDefFoundError ex) {
            System.out.println("second="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 FailedSuperclassDemo.java
java FailedSuperclassDemo
~~~

**Stdout:**

~~~text
BadParent.init
first=ExceptionInInitializerError
second=NoClassDefFoundError
~~~

`BadParent` ném lỗi trước khi hoàn tất static initialization. Vì vậy **`BlockedChild.static` không được in**, và cũng không có `BlockedChild.constructor`. Class con không thể tiếp tục khởi tạo bình thường khi dependency superclass bắt buộc đã thất bại.

Điểm rút ra khi chẩn đoán: nếu stack trace báo lỗi ở một class con, **nguyên nhân gốc có thể nằm ở static initialization của lớp cha**. Đừng chỉ tìm `static { ... }` của class con rồi bỏ qua chuỗi kế thừa.

## 15. Class initialization thành công chỉ chạy một lần theo danh tính class runtime

Trong một ứng dụng thông thường, class được initialized thành công **một lần cho mỗi định nghĩa runtime** của class đó. Sau này tạo thêm object, đọc static field hoặc gọi static method không chạy lại các initializer.

Tuy nhiên, cần phân biệt **danh tính runtime class** với tên source. Định danh class tại JVM bao gồm binary name và **defining class loader**. Hai class được định nghĩa bởi hai loader khác nhau có thể có cùng binary name mà vẫn là hai runtime classes với static state và trạng thái initialization riêng.

Điều đó hữu ích khi hiểu cơ chế plugin, application server và hot-reload. Nó **không** có nghĩa một class loader có thể tự nhiên “khởi tạo lại class erroneous” bằng cách gọi lại method. Nếu cần nạp một **định nghĩa runtime khác**, đó là câu chuyện kiến trúc class loader riêng, không phải một lệnh reset static đơn giản.

**Không nên dùng `System.gc()` hoặc tạo object mới như cách thử chạy lại static block.** Garbage collection không phải cơ chế khởi tạo lại class đã initialized.

## 16. Đa luồng: JVM phối hợp initialization nhưng không biến mọi static state thành thread-safe

Theo [JLS §12.4.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2), class initialization có trạng thái và phối hợp giữa các thread. Nếu nhiều thread cùng cần initialized **một class runtime** lần đầu, JVM không để mỗi thread độc lập chạy một bản sao của cùng static initializer.

Tuy nhiên, điều đó **không** khiến những field mutable trở nên thread-safe về sau.

~~~java
class SharedCounter {
    static int count;

    static void increment() {
        count++;
    }
}
~~~

Đây là một lớp minh họa hợp lệ. Sau initialization, nhiều thread cùng gọi `increment()` có thể gây mất cập nhật, vì `count++` là thao tác đọc–tính–ghi không nguyên tử.

Tương tự, không nên dùng static initializer để thực hiện tác vụ blocking phức tạp phụ thuộc các luồng khác đang chờ cùng class initialized. Có thể gặp vấn đề liveness hoặc vòng phụ thuộc giữa initializers.

**Tách hai câu hỏi:** JVM initialized class an toàn theo quy tắc riêng; còn các **thao tác nghiệp vụ sau initialization** phải tự thiết kế synchronization, ownership hoặc cấu trúc bất biến.

## 17. Thực nghiệm 7: initialization-on-demand holder

Một ứng dụng của cơ chế class initialization là **holder idiom**: trì hoãn tạo một instance cho tới lần đầu cần nó.

Tạo tệp **`HolderOrderDemo.java`**:

~~~java
final class SettingsService {
    private SettingsService() {
        System.out.println("SettingsService.constructor");
    }

    static SettingsService get() {
        System.out.println("SettingsService.get");
        return Holder.INSTANCE;
    }

    private static class Holder {
        static final SettingsService INSTANCE =
                new SettingsService();

        static {
            System.out.println("Holder.static");
        }
    }
}

public class HolderOrderDemo {
    public static void main(String[] args) {
        System.out.println("main.start");
        SettingsService a = SettingsService.get();
        SettingsService b = SettingsService.get();
        System.out.println("same=" + (a == b));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 HolderOrderDemo.java
java HolderOrderDemo
~~~

**Stdout:**

~~~text
main.start
SettingsService.get
SettingsService.constructor
Holder.static
SettingsService.get
same=true
~~~

Class ngoài `SettingsService` được initialized khi cần thực hiện static method `get`, nhưng nested class `Holder` **không bắt buộc initialized chỉ vì nằm trong lớp ngoài**. Lần đầu code truy cập `Holder.INSTANCE`, JVM initialized `Holder`: initializer tạo đối tượng (constructor in ra trước), rồi static block mới in `Holder.static`.

Lần `get()` thứ hai đọc cùng field đã gán; không tạo object thứ hai. `a == b` là `true` vì hai biến nhận cùng tham chiếu.

**Giới hạn:** singleton có một instance không đồng nghĩa các method trên instance ấy thread-safe nếu chứa mutable state; holder idiom chủ yếu dùng bảo đảm initialization của JVM cho việc tạo và công bố tham chiếu theo thiết kế phù hợp.

## 18. Bốn nhóm lỗi cần phân biệt khi chẩn đoán

| Lỗi/nhóm lỗi | Điểm phát sinh điển hình | Ý nghĩa |
| --- | --- | --- |
| `ClassNotFoundException` | Gọi API theo tên như `Class.forName` nhưng không tìm được class | Checked exception do yêu cầu tìm class thất bại |
| `NoClassDefFoundError` | Runtime không thể dùng định nghĩa class cần thiết; hoặc class trước đó đã initialization failed | Không đồng nghĩa bắt buộc “file class chưa từng tồn tại” |
| `ExceptionInInitializerError` | Static initialization ném một throwable không thuộc `Error` và JVM phải bọc nó | Quan sát lỗi tại class initialization |
| `IllegalArgumentException` trong constructor | Đối số tạo instance không hợp lệ | Thường chỉ lời tạo instance thất bại |
| `NoSuchMethodError`, `NoSuchFieldError` | Không tương thích binary/linkage ở runtime | Khác với logic sai trong static initializer |
| `StackOverflowError` hoặc `AssertionError` trong initialization | Có thể phát sinh là `Error` trực tiếp từ initializer | Có thể truyền ra mà không bị bọc bởi `ExceptionInInitializerError` |

Hai câu hỏi chẩn đoán hiệu quả:

1. Lỗi xảy ra khi **liên kết/phân giải** một class, khi **chạy static initializers**, hay khi **gọi constructor/method bình thường**?
2. Đây là **lần đầu class đó thất bại**, hay chỉ là **lần dùng tiếp sau khi initialization đã failed**?

Nếu chỉ xem dòng exception cuối cùng mà không theo chuỗi `Caused by` hoặc log trước đó, bạn rất dễ chẩn đoán sai. Trong ví dụ `FailedClassInitializationDemo`, lỗi có thông tin hữu ích nhất là **`IllegalStateException("invalid port")` ban đầu**, không phải `NoClassDefFoundError` của lần dùng thứ hai.

## 19. Những nguyên tắc dự đoán stdout

Hãy coi bài output prediction như mô phỏng một máy trạng thái, thay vì đọc từng câu `println` từ trên xuống.

**Bước 1 — Liệt kê các class:** class chứa `main`, class cha/con, nested class, helper class có static initializers.

**Bước 2 — Ghi trạng thái class:** chưa initialized, đang initializing, initialized, hoặc erroneous. Một class đã initialized sẽ không chạy lại static code trên lần dùng tiếp.

**Bước 3 — Tìm active use đầu tiên:** `new`, lời gọi static method, đọc nonconstant static field, `Class.forName` yêu cầu initialize. Tránh coi class literal/mảng/compile-time constants là trigger.

**Bước 4 — Xét inheritance:** superclass cần thiết initialized trước subclass; với interface/default methods, dùng đúng JLS chứ không áp quy tắc class một cách máy móc cho mọi interface.

**Bước 5 — Chạy static code theo textual order:** ghi giá trị mặc định từ preparation cho nonconstant static fields và cập nhật khi initializer thực sự chạy. Không tính lại field cũ khi field khác được gán sau.

**Bước 6 — Nếu `new` thành công để tiến vào giai đoạn instance:** đi qua superclass constructor chain và mỗi lớp có instance initializer/constructor theo thứ tự quy định.

**Bước 7 — Nếu có exception:** dừng đường thực thi bình thường, chuyển đúng sang `catch` thích hợp; nếu class initialization thất bại, đánh dấu class erroneous và không giả định chạy lại initializer.

**Bước 8 — Chỉ sau đó mới liệt kê stdout:** thông điệp lỗi hoặc thông điệp có thể phụ thuộc JVM nên tránh đoán toàn bộ stack trace; ưu tiên in tên kiểu lỗi/giá trị cụ thể để có output xác định.

## 20. Bài thực nghiệm A: constructor gọi override quá sớm

Dự đoán trước khi chạy chương trình sau. Tạo tệp **`OverrideDuringConstructionDemo.java`**:

~~~java
class BaseReader {
    BaseReader() {
        System.out.println("base.ctor");
        read();
    }

    void read() {
        System.out.println("base.read");
    }
}

class DetailReader extends BaseReader {
    private String name = "READY";

    {
        System.out.println("detail.block " + name);
    }

    DetailReader() {
        System.out.println("detail.ctor " + name);
    }

    @Override
    void read() {
        System.out.println("detail.read " + name);
    }
}

public class OverrideDuringConstructionDemo {
    public static void main(String[] args) {
        new DetailReader();
    }
}
~~~

Lệnh:

~~~bash
javac -encoding UTF-8 OverrideDuringConstructionDemo.java
java OverrideDuringConstructionDemo
~~~

**Đáp án stdout:**

~~~text
base.ctor
detail.read null
detail.block READY
detail.ctor READY
~~~

**Lời giải:** object `DetailReader` đã được cấp phát với các instance fields mặc định, trong đó `name=null`. Constructor superclass `BaseReader()` chạy trước initializer `name="READY"` của subclass. Lời gọi `read()` thực hiện **dynamic dispatch** đến override `DetailReader.read()`, nên nó quan sát `null`. Sau khi constructor cha xong, subclass mới thực thi initializer và block, rồi phần thân constructor con.

**Bài học thiết kế:** tránh gọi method có thể override từ constructor lớp cha và tránh để `this` thoát ra ngoài khi object chưa khởi tạo đầy đủ. Đây là hiện tượng **khởi tạo object**, không phải lỗi class initialization.

## 21. Bài thực nghiệm B: static initializer và `try/catch`

Tạo tệp **`CaughtDuringStaticDemo.java`**:

~~~java
class RecoveringClass {
    static int port = getPort();

    private static int getPort() {
        System.out.println("try port");
        try {
            return Integer.parseInt("bad");
        } catch (NumberFormatException ex) {
            System.out.println("fallback");
            return 8080;
        }
    }

    static {
        System.out.println("port initialized=" + port);
    }
}

public class CaughtDuringStaticDemo {
    public static void main(String[] args) {
        System.out.println("main");
        System.out.println("port=" + RecoveringClass.port);
        System.out.println("again=" + RecoveringClass.port);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 CaughtDuringStaticDemo.java
java CaughtDuringStaticDemo
~~~

**Stdout:**

~~~text
main
try port
fallback
port initialized=8080
port=8080
again=8080
~~~

Ở đây exception `NumberFormatException` được **bắt và xử lý hoàn toàn** trong initializer, nên class initialization **thành công**, không có `ExceptionInInitializerError`. Lần truy cập thứ hai chỉ đọc field đã nhận 8080.

**Điểm mấu chốt:** không phải cứ một phương thức được gọi từ static initializer **từng ném exception** thì class sẽ erroneous. Điều quyết định là toàn bộ quá trình class initialization **có hoàn thành bình thường hay không**.

Trong ứng dụng thật, nếu dùng fallback phải có chính sách rõ: cấu hình sai có thể chấp nhận giá trị dự phòng hoặc cần dừng startup. Đừng nuốt lỗi âm thầm nếu giá trị mặc định làm sai nghiệp vụ.

## 22. Bài tự luyện dự đoán output

Hãy tự viết stdout trước khi xem lời giải. Các đoạn dưới là những class minh họa độc lập hoặc được giả định đặt trong tệp hợp lệ theo tên class tương ứng.

**Câu 1 — Static một lần.**

~~~java
class A {
    static {
        System.out.print("S");
    }

    A() {
        System.out.print("C");
    }
}
~~~

Nếu một phương thức `main` thuộc lớp khác gọi `new A(); new A();` lần đầu và không có code in khác, kết quả là gì?

**Câu 2 — Hằng số.**

~~~java
class B {
    static final int N = 5;
    static {
        System.out.print("I");
    }
}
~~~

Trong một `main` của class khác, chỉ gọi `System.out.print(B.N);`. Có in `I` không?

**Câu 3 — Static method.**

~~~java
class C {
    static {
        System.out.print("I");
    }

    static void work() {
        System.out.print("W");
    }
}
~~~

Trong `main` của class khác gọi `C.work(); C.work();`, chuỗi nào được in?

**Câu 4 — Trường bị đọc sớm.**

~~~java
class D {
    static int x = init();
    static int y = 4;

    static int init() {
        System.out.print(y);
        return y + 1;
    }
}
~~~

Khi một `main` khác lần đầu dùng `D.x`, method `init()` in ký tự gì và `D.x` có giá trị mấy?

**Câu 5 — Kế thừa.** Class `P` in `P` trong static block, `Q extends P` in `Q` trong static block. Nếu chưa class nào initialized và gọi `new Q()`, thứ tự hai chữ in ra là gì?

**Câu 6 — Failure.** Static initializer của `Broken` lần đầu gọi method ném `IllegalStateException` không được bắt. Caller bắt `ExceptionInInitializerError` rồi **tiếp tục truy cập static field của cùng Broken**. Lần sau thường gặp kiểu lỗi gì?

**Câu 7 — Constructor.** Một class có static block hợp lệ, constructor ném `IllegalArgumentException` với một tham số sai. Sau khi bắt lỗi, caller tạo object khác bằng tham số đúng. Có mặc nhiên nhận `NoClassDefFoundError` không?

**Câu 8 — Class literal.** `T.class` và `new T[2]` có yêu cầu static block của `T` chạy không nếu chưa có thao tác khác kích hoạt?

**Câu 9 — Error trực tiếp.** Method được gọi trong static initializer ném `AssertionError`, và không có catch. Lần đầu lỗi có bắt buộc bị bọc bởi một `ExceptionInInitializerError` mới không?

**Câu 10 — Holder.** Vì sao lần thứ hai đọc `Holder.INSTANCE` không in lại static block của Holder, dù code dùng cùng tên class lần nữa?

**Câu 11 — Catch trong initializer.** Một static field initializer gọi `parse()`; `parse()` bắt `NumberFormatException` rồi trả một giá trị hợp lệ. Class có buộc trở thành erroneous không?

**Câu 12 — Inherited static field.** `Parent` khai báo `static int count`, `Child extends Parent` có static block riêng. Chỉ đọc `Child.count` có nhất thiết initialized `Child` không?

### Đáp án chi tiết

1. **`SCC`**: static code một lần, constructor chạy cho hai object.
2. **`5`**, không in `I`: `N` là compile-time constant variable.
3. **`IWW`**: `C` initialized trước static method lần đầu, rồi hai lần chạy `work`.
4. In **`0`**, và sau đó `D.x=1`; `y` còn mặc định 0 khi `init` chạy.
5. **`PQ`**: superclass initialized trước subclass.
6. Thường **`NoClassDefFoundError`** trong cùng runtime class/class loader vì lần đầu initialization đã thất bại.
7. **Không**. Lỗi constructor không tự làm class erroneous; lần tạo khác có thể thành công.
8. **Không tự yêu cầu** initialization của component class `T`; array được tạo riêng.
9. **Không**. Vì nguyên nhân đã là `Error`, nó có thể được truyền trực tiếp theo quy tắc initialization.
10. Class holder đã initialized thành công; JVM không thực thi lại static initializer cho mỗi lần đọc.
11. **Không**; initializer hoàn thành bình thường, class có thể initialized thành công.
12. **Không**, vì field được khai báo bởi `Parent`. Xét class khai báo field chứ không chỉ tên `Child` đứng trước dấu chấm.

## 23. Ma trận quan sát khi chạy các ví dụ

Để tự kiểm chứng, có thể thực hiện trong thư mục học tập của riêng bạn (mỗi chương trình độc lập mang tên đã nêu):

| Tệp chương trình | Điều cần quan sát | Dấu hiệu chính |
| --- | --- | --- |
| `FirstUseOrderDemo.java` | Main static, constant, static field, constructors | `Main.initialized` đầu tiên; `Warmup` chờ đến nonconstant field |
| `ParentChildTraceDemo.java` | Parent/child và hai object | Static cha/con một lần; instance chain hai lần |
| `StaticForwardReadDemo.java` | Field bị đọc trước initializer | `during later=0`, sau đó `later=10` |
| `ConstantTriggerDemo.java` | Constant vs nonconstant | `compute` xuất hiện chỉ trước dòng đọc `COMPUTED` |
| `DeferredInitializationDemo.java` | Class literal/mảng/`forName(false)` | `Deferred.static` chỉ khi `forName(name)` yêu cầu init |
| `FailedClassInitializationDemo.java` | First failure vs subsequent use | `ExceptionInInitializerError` rồi `NoClassDefFoundError` |
| `ErrorDuringInitializationDemo.java` | Nguyên nhân thuộc `Error` | `AssertionError` trước, NCDFE sau |
| `ConstructorExceptionDemo.java` | Instance failure | Một static print, có thể thử constructor mới |
| `FailedSuperclassDemo.java` | Parent failure blocks child | Không có dòng `BlockedChild.static` |
| `HolderOrderDemo.java` | Lazy holder | Constructor một lần và `same=true` |
| `OverrideDuringConstructionDemo.java` | Dynamic dispatch quá sớm | `detail.read null` |
| `CaughtDuringStaticDemo.java` | Exception được xử lý | Fallback thành công, không có EIIE |

Khi kết quả khác kỳ vọng, trước tiên kiểm tra bạn có thực sự chạy **đúng tệp/class đã biên dịch** hay không. Với chương trình dùng package mặc định, lệnh `java ClassName` phải chạy từ nơi class files phù hợp có mặt; với package có tên, classpath và tên đủ package phải chính xác.

Mỗi ví dụ có top-level public class riêng để tránh xung đột giữa những đoạn học; nếu chép nhiều ví dụ cùng một dự án, hãy giữ tên class và package không trùng theo khả năng của dự án.

## 24. Tình huống lỗi thực tế và cách chẩn đoán

**Tình huống A — Cấu hình static thất bại.** Một class đọc biến môi trường trong static initializer và ném `IllegalStateException`. Nếu ứng dụng dùng class đó lần đầu, lỗi có thể bị bọc thành `ExceptionInInitializerError`. Hướng xử lý: tìm nguyên nhân ban đầu; cân nhắc validate cấu hình ở startup theo một cơ chế có báo lỗi rõ thay vì đợi class được dùng bất ngờ.

**Tình huống B — Log chỉ còn `NoClassDefFoundError`.** Một request sau báo không thể initialized class. Có thể request trước đã khiến class initialization thất bại. Hướng xử lý: tìm log của **lần dùng đầu tiên** và chuỗi nguyên nhân; kiểm tra class loader, cấu hình, static code và dependency.

**Tình huống C — Test đầu pass, test sau khác.** Test dùng cùng JVM/class loader có thể gặp class đã initialized từ test trước. Không được giả định static initializer chạy lại khi tạo instance mới. Thiết kế test nên tránh phụ thuộc thứ tự toàn suite; reset state mutable có kiểm soát, dùng dependency injection hoặc tách tiến trình khi thật sự cần isolation cấp JVM.

**Tình huống D — Thread deadlock quanh khởi tạo.** Hai static initializers phức tạp có thể yêu cầu nhau hoặc chờ các thread khác trong thời điểm class initialization đang được đồng bộ hóa. Hướng xử lý: giảm side effects trong static blocks, tránh I/O/chờ khóa phức tạp và kiểm tra thread dump khi cần.

**Tình huống E — Cấu hình của subclass chưa có.** Constructor superclass gọi method overridable; subclass field chưa chạy initializer và đang `null`. Đây là lỗi **khởi tạo object/thiết kế kế thừa**, không nhất thiết là class initialization failure.

**Tình huống F — Lỗi binary sau nâng cấp thư viện.** `NoSuchMethodError` hay `NoSuchFieldError` có thể liên quan linking/resolution, không cần có static initializer sai. Hãy kiểm tra binary compatibility và dependency versions.

## 25. Checklist thiết kế static initialization an toàn

- Có thật sự cần tính dữ liệu ngay trong `static` field initializer hay static block không?
- Có thể dùng **constant expression** cho hằng số bất biến đơn giản không?
- Biểu thức initializer có I/O, chờ lock, khởi chạy thread hoặc gọi external code khó đoán không?
- Nếu đọc configuration thất bại, chương trình nên dừng startup hay có fallback được xác định rõ?
- Có phụ thuộc vòng giữa static fields/classes khiến đọc giá trị mặc định quá sớm không?
- Thứ tự source giữa các static initializers có được giữ rõ ràng không?
- Có superclass/interface cần initialized trước theo JLS không?
- Nếu static initializer ném lỗi, log đầu tiên có đủ bối cảnh để tìm nguyên nhân không?
- Có giả định sai rằng class erroneous sẽ tự được initialized lại trong cùng loader không?
- Có vô tình gọi method overridable từ constructor khiến subclass field chưa sẵn sàng không?
- Nếu state static mutable dùng nhiều thread, có cơ chế synchronization/atomic update riêng không?
- Bài test có tránh phụ thuộc vào thứ tự chạy hoặc trạng thái static từ bài test trước không?

**Thiết kế tốt không tìm cách “bắt hết mọi `Error`” rồi tiếp tục.** Nên giảm khả năng lỗi trong class initialization, báo nguyên nhân rõ và chọn một lifecycle quản lý cấu hình/phụ thuộc phù hợp.

## 26. Tài liệu chuẩn để đối chiếu

- [Java Language Specification 17, §12.2 — Loading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2): tải kiểu và class loader.
- [JLS 17, §12.3 — Linking of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.3): verification, preparation và resolution.
- [JLS 17, §12.4.1 — When Initialization Occurs](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.1): active use, hằng số, static field và subclass.
- [JLS 17, §12.4.2 — Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): trạng thái class, đồng bộ hóa khởi tạo và xử lý thất bại.
- [JLS 17, §12.5 — Creation of New Class Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.5): khởi tạo instance và thứ tự constructor.
- [JLS 17, §8.3.3 — Restrictions on Field References in Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3.3): illegal forward references.
- [JLS 17, §8.7 — Static Initializers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.7): yêu cầu đối với static initializer.
- [JLS 17, §4.12.4 — final Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4): constant variables và cách xác định.
- [Java Virtual Machine Specification 17, §5.5 — Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5): cơ chế class initialization ở JVM.
- [Java SE 17 API — Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): lựa chọn initialization qua reflection.
- [Java SE 17 API — ExceptionInInitializerError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html): lỗi khi static initializer/field initializer ném exception.
- [Java SE 17 API — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html): lỗi runtime khi không thể dùng class definition.

**Ghi nhớ:** Khởi tạo class diễn ra theo các **trigger và trạng thái của JVM**, không theo số lần class xuất hiện trong source. Static code chạy theo **thứ tự initializer** khi class cần initialized; constructor instance chạy **cho từng object**. Nếu class initialization ném một exception không thuộc `Error`, caller thường thấy **`ExceptionInInitializerError` ở lần đầu**; class trở thành **erroneous**, và **lần dùng tiếp có thể thấy `NoClassDefFoundError`**. Hãy lần lại **nguyên nhân đầu tiên**, phân biệt lỗi constructor với lỗi class, và dùng bảng trạng thái để dự đoán stdout chính xác.
