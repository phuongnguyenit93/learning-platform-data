# Kiểm chứng thứ tự static initializer và lỗi khởi tạo

## 1. Mục tiêu

Khi học Java ClassLoader, cần phân biệt **nạp lớp** với **khởi tạo lớp**. Một ClassLoader có thể tìm được bytecode và trả `Class<?>` trong khi các `static` blocks của lớp chưa chạy. Ngược lại, khi JVM bắt đầu class initialization, các static field initializers, static blocks và quan hệ superclass phải tuân thủ thứ tự chặt chẽ.

Bài này cung cấp một chương trình Java 17+ biên dịch được để kiểm chứng:

- Class literal và `ClassLoader.loadClass` không mặc nhiên kích hoạt static initialization.
- `Class.forName(name, false, loader)` khác `Class.forName(name, true, loader)`.
- Khi `new Derived()`, static initializers của superclass chạy trước subclass, và trong từng class chúng chạy theo **thứ tự xuất hiện trong source**.
- `static final` compile-time constants có thể được inline mà không initialize class; static field được tính ở runtime thì có thể kích hoạt.
- Static initialization ném exception có thể dẫn tới `ExceptionInInitializerError` ở lần đầu và `NoClassDefFoundError` ở lần dùng sau.
- Một class khởi tạo hỏng không làm tất cả các classes trong JVM tự động hỏng; trạng thái initialization gắn với **runtime class**, kể cả defining loader.

## 2. Phân biệt thời điểm nạp, liên kết và chạy initializer

**Loading** tạo/tra cứu định nghĩa `Class<?>`, **linking** gồm verification, preparation (các static fields nhận giá trị mặc định) và resolution có thể xảy ra muộn. **Initialization** mới thực hiện các static field initializers và static blocks cần chạy. `ConstantValue` (nếu có) được gán trong initialization trước `<clinit>`, không phải bởi mã `static {}` trong source. Bài này đo **thứ tự observable output** và trạng thái erroneous bằng một chương trình, thay vì chỉ nhìn log tải class.

## 3. Quy tắc thứ tự static initialization

Ví dụ:

~~~java
// Mã minh họa; mark(...) là helper in nhãn rồi trả số.
class Sample {
    static int a = mark("a", 1);

    static {
        System.out.println("block");
    }

    static int b = mark("b", 2);
}
~~~

Khi `Sample` được initialize, output sẽ theo thứ tự:

~~~text
a
block
b
~~~

Static fields và blocks được thực thi **theo thứ tự văn bản** trong class. Không có quy tắc “mọi field trước mọi block”.

Với kế thừa:

~~~text
class Base
  static Base.field
  static Base.block

class Derived extends Base
  static Derived.field
  static Derived.block

new Derived():
  Base.field
  Base.block
  Derived.field
  Derived.block
  Base constructor
  Derived constructor
~~~

Superclass chưa initialized được initialize trước subclass. Khi các static initializers xong, object construction mới thực hiện constructor superclass và subclass.

**Ngoại lệ cần hiểu riêng:** Interfaces có quy tắc đặc thù; initialization của class còn liên quan một số superinterfaces khai báo default methods. Không dùng câu “mọi interface mà class implements đều được initialize trước class” như một quy tắc tuyệt đối.

## 4. Điều kiện để dự đoán output

`Derived.class`, `loader.loadClass(...)` và `Class.forName(name,false,loader)` không tự khởi tạo lớp đích. Nhưng `new Derived()`, truy cập static field không phải hằng, gọi static method và `Class.forName(name,true,loader)` yêu cầu initialization nếu chưa hoàn tất. Đọc một primitive/`String` `final` được gán constant expression có thể được compiler inline, nên không chạy marker. Bài trước kiểm chứng từng overload sâu hơn; ở đây sẽ cùng lúc theo dõi cả **thứ tự field/block, superclass, success và failure**.

## 5. Chương trình Java 17+ tự kiểm chứng

Tạo file duy nhất **`InitializationLab.java`**:

~~~java
public final class InitializationLab {
    private InitializationLab() {
    }

    private static void log(String text) {
        System.out.println(text);
    }

    private static int mark(String label, int value) {
        log(label);
        return value;
    }

    private static int fail() {
        log("Broken.fail");
        throw new IllegalStateException("boom");
    }

    static class Base {
        static int first = mark("Base.field", 1);

        static {
            log("Base.block");
        }

        static int last = mark("Base.last", 2);

        Base() {
            log("Base.ctor");
        }
    }

    static final class Derived extends Base {
        static int first = mark("Derived.field", 3);

        static {
            log("Derived.block");
        }

        Derived() {
            log("Derived.ctor");
        }
    }

    static final class Probe {
        static {
            log("Probe.<clinit>");
        }
    }

    static final class OnlyLoaded {
        static {
            log("OnlyLoaded.<clinit>");
        }

        static String value() {
            return "LOADED";
        }
    }

    static final class Constants {
        static final int NUMBER = 42;
        static final String TEXT = "CONST";
        static final Integer BOXED = mark("Constants.<clinit>", 99);
    }

    static final class Broken {
        static int VALUE = fail();
    }

    static final class Healthy {
        static {
            log("Healthy.<clinit>");
        }

        static int VALUE = 7;
    }

    public static void main(String[] args) throws Exception {
        log("01 main");

        // Class literal không khởi tạo Derived.
        Class<?> literal = Derived.class;
        log("02 class literal: " + literal.getSimpleName());

        log("03 construct");
        new Derived();

        log("04 static again: " + Derived.first);

        Class<?> passive = Class.forName(
                InitializationLab.class.getName() + "$Probe",
                false,
                InitializationLab.class.getClassLoader());
        log("05 forName(false): " + passive.getSimpleName());

        Class.forName(
                InitializationLab.class.getName() + "$Probe",
                true,
                InitializationLab.class.getClassLoader());
        log("06 forName(true)");

        Class<?> loaded =
                InitializationLab.class.getClassLoader().loadClass(
                        InitializationLab.class.getName()
                                + "$OnlyLoaded");
        log("07 loadClass: " + loaded.getSimpleName());

        log("08 invoke: " + OnlyLoaded.value());

        log("09 int constant: " + Constants.NUMBER);
        log("10 String constant: " + Constants.TEXT);
        log("11 boxed: " + Constants.BOXED);

        Class<?> brokenType = Broken.class;
        log("12 Broken.class: " + brokenType.getSimpleName());

        try {
            log("13 Broken first: " + Broken.VALUE);
        } catch (ExceptionInInitializerError first) {
            log("13 first: " + first.getClass().getSimpleName());
            log("13 cause: "
                    + first.getCause().getClass().getSimpleName());
        }

        try {
            log("14 Broken second: " + Broken.VALUE);
        } catch (NoClassDefFoundError second) {
            log("14 second: " + second.getClass().getSimpleName());
        }

        log("15 Healthy: " + Healthy.VALUE);
    }
}
~~~

### 5.1. Biên dịch và chạy

Yêu cầu JDK **17 trở lên**. Mở terminal tại thư mục chứa file:

~~~bash
javac -encoding UTF-8 InitializationLab.java
java InitializationLab
~~~

Lệnh sử dụng được trên Bash, PowerShell và Command Prompt nếu `javac`/`java` nằm trong `PATH`; chương trình không cần thư viện ngoài JDK.

### 5.2. Stdout chính xác với source trên

~~~text
01 main
02 class literal: Derived
03 construct
Base.field
Base.block
Base.last
Derived.field
Derived.block
Base.ctor
Derived.ctor
04 static again: 3
05 forName(false): Probe
Probe.<clinit>
06 forName(true)
07 loadClass: OnlyLoaded
OnlyLoaded.<clinit>
08 invoke: LOADED
09 int constant: 42
10 String constant: CONST
Constants.<clinit>
11 boxed: 99
12 Broken.class: Broken
Broken.fail
13 first: ExceptionInInitializerError
13 cause: IllegalStateException
14 second: NoClassDefFoundError
Healthy.<clinit>
15 Healthy: 7
~~~

Các nhãn số chỉ là mốc do chương trình in, không phải timestamp. Lời gọi `Class.forName` dùng chính defining loader của `InitializationLab` để tránh phụ thuộc vào context loader của thread hoặc môi trường bên ngoài.

## 6. Phân tích phần class literal và kế thừa

Trước lệnh `new Derived()`, output:

~~~text
01 main
02 class literal: Derived
03 construct
~~~

`Derived.class` và `getSimpleName()` không gây static initialization trong ví dụ. Nếu đã chạy `<clinit>`, bạn sẽ nhìn thấy `Base.field` hoặc `Derived.field` xuất hiện **trước** dòng `02`; thực tế không có.

Sau mốc `03`:

~~~text
Base.field
Base.block
Base.last
Derived.field
Derived.block
Base.ctor
Derived.ctor
~~~

Quan sát được cả **thứ tự giữa các class** và **thứ tự bên trong mỗi class**. `Base` phải initialize trước `Derived`; trong `Base`, initializer của `first`, block rồi initializer của `last`; sau đó tới `Derived.first` và block. Chỉ khi mọi static initializer hoàn tất, constructor `Base` và `Derived` mới chạy.

Nếu gọi `new Derived()` lần thứ hai trong cùng JVM, hai constructor sẽ chạy lại, nhưng các static initializers của runtime classes đã initialize không tự chạy thêm lần nữa.

## 7. Class.forName và loadClass có cùng hành vi không?

Không. Phần tiếp của stdout:

~~~text
05 forName(false): Probe
Probe.<clinit>
06 forName(true)
07 loadClass: OnlyLoaded
OnlyLoaded.<clinit>
08 invoke: LOADED
~~~

- `Class.forName(..., false, loader)` tìm/chuẩn bị class phù hợp nhưng **không yêu cầu chạy `Probe.<clinit>`**.
- `Class.forName(..., true, loader)` yêu cầu initialization, nên log `Probe.<clinit>` xuất hiện **trước** khi in mốc `06`.
- `ClassLoader.loadClass` tìm class `OnlyLoaded` nhưng không tự initialize nó; sau mốc `07` mới có `OnlyLoaded.<clinit>`.
- Static method `OnlyLoaded.value()` là active use, kích hoạt initialization trước khi kết quả `LOADED` được in.

**Không đồng nhất “chưa initialize” với “không thể lỗi”.** Loading và linking vẫn có thể gặp `ClassNotFoundException`, `ClassFormatError` hay `LinkageError`. Sự khác biệt ở đây chỉ về bước chạy class initialization method `<clinit>`.

## 8. Vì sao hằng static final không làm Constants khởi tạo?

Đầu ra:

~~~text
09 int constant: 42
10 String constant: CONST
Constants.<clinit>
11 boxed: 99
~~~

Hai trường:

~~~java
static final int NUMBER = 42;
static final String TEXT = "CONST";
~~~

là **constant variables**: kiểu primitive/String và có constant expression. Java compiler có thể inline giá trị vào bytecode của `InitializationLab.main`. Đọc chúng trong ví dụ không làm initialize `Constants`.

Trong khi đó:

~~~java
static final Integer BOXED = mark("Constants.<clinit>", 99);
~~~

không phải constant variable: `Integer` là reference type và giá trị được tính khi class initialization. Khi đọc `BOXED`, JVM initialize `Constants` và gọi `mark`.

Điều này liên quan versioning JAR: nếu một library đổi giá trị của `public static final int` compile-time constant, caller **đã biên dịch từ trước** có thể vẫn dùng literal cũ. Không thể suy từ giá trị ấy rằng ClassLoader “đã nạp phiên bản mới”.

## 9. Lần đầu lỗi initialization và lần dùng sau

Một đoạn quan trọng:

~~~java
static final class Broken {
    static int VALUE = fail();
}

private static int fail() {
    log("Broken.fail");
    throw new IllegalStateException("boom");
}
~~~

`Broken.class` không thực thi `fail()`. Khi lần đầu đọc `Broken.VALUE`, JVM bắt đầu initialize class và gọi `fail()`. Code ném `IllegalStateException` (không phải subclass của `Error`), nên JVM bọc lỗi vào `ExceptionInInitializerError`.

Trong stdout:

~~~text
12 Broken.class: Broken
Broken.fail
13 first: ExceptionInInitializerError
13 cause: IllegalStateException
14 second: NoClassDefFoundError
~~~

`Broken.fail` **chỉ xuất hiện một lần**. Sau lần khởi tạo thất bại, runtime class `Broken` ở trạng thái **erroneous**; JVM không tự retry `<clinit>` khi cùng runtime class được active use lần nữa. Lần dùng sau có thể nhận `NoClassDefFoundError`.

`NoClassDefFoundError` còn có thể do thiếu dependency hoặc sai tên class file, nên khi thấy thông báo `Could not initialize class` cần **truy tìm exception khởi tạo đầu tiên**, không mặc định là thiếu JAR.

### Một lưu ý về Error trực tiếp

Nếu static initializer ném `AssertionError` hoặc một `Error` khác, JVM có thể truyền chính `Error` ban đầu ra ngoài thay vì bọc vào `ExceptionInInitializerError`. Lần dùng sau của class erroneous vẫn có thể báo `NoClassDefFoundError`.

Không nên viết code production bắt `ExceptionInInitializerError` hoặc `NoClassDefFoundError` rồi tiếp tục vô điều kiện. Cần ghi nhận nguyên nhân gốc và sửa initialization code/config; một runtime class erroneous không được “sửa” bằng cách gọi constructor lần nữa.

## 10. Superclass initialization thất bại sẽ ngăn subclass

Ví dụ minh họa, **không phải file chạy độc lập**:

~~~java
class FailingBase {
    static int value = failure();

    static int failure() {
        throw new IllegalStateException("base init failed");
    }
}

class Child extends FailingBase {
    static {
        System.out.println("Child initializer");
    }

    static void go() {
    }
}
~~~

Khi `Child.go()` kích hoạt initialization của `Child`, JVM cần initialize `FailingBase` trước. Nếu `FailingBase` khởi tạo thất bại, `Child` không hoàn thành initialization và dòng `Child initializer` không được in.

Các side effects của những static initializers đã chạy **không được JVM rollback theo giao dịch**. Nếu chúng đã ghi file, đăng ký listener hoặc thay đổi global state trước khi ném exception, application phải tự thiết kế cleanup/khôi phục nếu cần.

## 11. Static field đọc giá trị mặc định trong khởi tạo vòng

Static fields được cấp giá trị mặc định trong preparation trước khi chạy initializer Java. Ví dụ minh họa:

~~~java
class Defaults {
    static int observed = readLater();
    static int later = 10;

    static int readLater() {
        return later;
    }
}
~~~

Nếu `Defaults` được initialize bình thường, `observed` có thể nhận `0` do `later` chưa được gán `10` ở thời điểm `readLater()` chạy. Sau khi toàn bộ initialization xong, `later == 10`.

Vì vậy:

- Đừng tự cho rằng một static field luôn nhìn thấy các giá trị final dự kiến của những fields khác trong lúc `<clinit>` đang chạy.
- Tránh dependency cycle giữa static initializers của nhiều classes.
- Hạn chế I/O, mutable shared state và đăng ký callback trong static initialization.
- Khi cần quản lý thứ tự dependency phức tạp, dùng explicit initialization/factory lifecycle với xử lý lỗi rõ ràng.

**Java memory/concurrency:** JVM đồng bộ hóa class initialization. Hai thread cùng active use một runtime class chưa initialized không tự chạy `<clinit>` hai lần. Nhưng hai static initializers của **hai classes khác nhau** gọi chéo có thể tạo deadlock; synchronization tự động không giải quyết mọi vòng phụ thuộc.

## 12. Một test mới phải có runtime class chưa initialized

Trạng thái initialized/erroneous thuộc về cặp **(binary name, defining loader)**. Chạy lại cùng class trong cùng loader không làm initializer chạy lần nữa, kể cả sửa `.class` trên đĩa. Cần một defining loader mới hoặc tiến trình JVM mới khi muốn reset thí nghiệm; bài cuối chương có cách tách kịch bản và xác minh loader mới thật sự sở hữu class.

## 13. Quan sát bytecode

Để hiểu vì sao static fields chạy theo thứ tự, dùng `javap` sau khi biên dịch:

~~~bash
javap -c -p InitializationLab
javap -c -p 'InitializationLab$Base'
javap -c -p 'InitializationLab$Derived'
javap -c -p 'InitializationLab$Constants'
~~~

Lệnh Bash/PowerShell dùng dấu nháy đơn để shell không xử lý ký tự `$` trong binary name của nested class. Trên Command Prompt có thể dùng dấu nháy kép.

Hãy tìm:

- `<clinit>` trong bytecode của `Base`, `Derived`, `Constants`.
- Các lệnh khởi tạo `first`, gọi `log/mark` và thứ tự lệnh bytecode.
- Constant values được compiler nhúng vào caller và lệnh `getstatic` cho `Constants.BOXED`.
- Phần `main` gọi `Class.forName` với boolean `false`/`true`.

Diagnostic logs của JVM có thể hỗ trợ quan sát class loading. Hãy kiểm tra tùy chọn có sẵn bằng:

~~~bash
java -Xlog:help
~~~

Log kiểu Unified Logging không phải stdout cố định: tag support và cách trình bày có thể khác nhau giữa các triển khai JVM.

## 14. Các lỗi thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `loadClass` trả class nghĩa static block chạy rồi | Loading và initialization khác nhau |
| `SomeClass.class` luôn khởi tạo class | Class literal không mặc nhiên kích hoạt `<clinit>` |
| Static fields luôn chạy hết trước static blocks | Tất cả static initializers chạy theo thứ tự source |
| Constructor Base chạy trước static initializer Derived | Khi tạo Derived object, class initialization cần hoàn tất trước object construction |
| Đọc constant field luôn initialize class | Compile-time constants có thể được inline |
| Lần dùng thứ hai của Broken sẽ gọi `fail()` thêm lần nữa | Class erroneous không tự retry initialization |
| `NoClassDefFoundError` chỉ xuất hiện khi thiếu file/JAR | Có thể sau class initialization failure |
| Catch một exception nghĩa đã rollback static side effects | Không có tự động rollback |
| Tạo object mới khiến static block chạy lại | Constructor mới chạy lại; `<clinit>` không chạy lại cho class đã initialized |
| ClassLoader mới tự sửa lỗi initializer | Có runtime class mới nhưng cùng lỗi code/config vẫn tồn tại |
| Class loader thành công nghĩa đã resolve mọi dependency | Resolution có thể trì hoãn |
| Hai thread chạy một class initializer hai lần | JVM đồng bộ hóa class initialization, nhưng vẫn có nguy cơ deadlock đa class |

## 15. Kiểm chứng theo kịch bản

Để tự kiểm tra, chạy chương trình mẫu trong **JVM mới** mỗi lần và đối chiếu stdout ở mục 5.2. Các thay đổi sau là **bài tập tùy chọn**; nếu thực hiện thì output sẽ thay:

1. Thêm lệnh `new Derived();` lần thứ hai; dự đoán constructor logs nhưng không có static logs lần hai.
2. Đổi `Class.forName(..., false, ...)` thành `true`; `Probe.<clinit>` sẽ xuất hiện sớm hơn.
3. Thay `static final int NUMBER = 42` bằng một giá trị runtime được tính qua method; lúc đọc trường, class initialization sẽ có tác dụng.
4. Đổi `Broken.fail()` để ném `AssertionError`, điều chỉnh catch và so sánh lần thất bại đầu.
5. Thêm một static field initializer trước `Base.block` rồi quan sát thay đổi thứ tự log.
6. Tách code vào JAR, chạy với loaders riêng; so sánh class identity và vòng đời initializer thay vì chỉ so tên class.

Hãy giữ log của **lỗi đầu tiên**: lần thứ hai có thể chỉ còn `NoClassDefFoundError` và không nói rõ nguyên nhân static initializer ban đầu.

## 16. Câu hỏi tự kiểm tra

**1.** Vì sao `Derived.class` không in `Base.field`?

**Đáp án:** Class literal không mặc nhiên khởi tạo class; `Base` và `Derived` chưa bị active use bởi biểu thức đó.

**2.** Khi `new Derived()`, vì sao `Base.block` trước `Derived.field`?

**Đáp án:** Superclass initialize trước subclass; mỗi class thực thi static initializers theo thứ tự source.

**3.** `Class.forName(name, false, loader)` và `Class.forName(name, true, loader)` khác gì?

**Đáp án:** `false` không yêu cầu initialization; `true` yêu cầu initialization.

**4.** Vì sao hai constant fields của `Constants` không kích hoạt static block, còn `BOXED` có?

**Đáp án:** Primitive/String constant variables có thể inline; `BOXED` là reference field được tính ở runtime, truy cập sẽ trigger initialization.

**5.** Vì sao lần đầu dùng `Broken.VALUE` có `ExceptionInInitializerError`?

**Đáp án:** Static field initializer ném `IllegalStateException`, JVM bọc lỗi không phải `Error` vào `ExceptionInInitializerError`.

**6.** Vì sao lần thứ hai có `NoClassDefFoundError` mà không chạy lại `Broken.fail`?

**Đáp án:** Runtime class đã ở trạng thái erroneous, JVM không tự khởi tạo lại.

**7.** Cùng binary name nhưng một class do loader L2 định nghĩa thay vì L1 có bắt buộc giữ trạng thái erroneous của L1 không?

**Đáp án:** Không. Hai defining loaders có thể định nghĩa hai runtime classes với vòng đời initialization riêng; nhưng nguyên nhân lỗi vẫn có thể tái diễn.

**8.** Một lỗi static initializer có tự rollback side effects không?

**Đáp án:** Không. JVM không tự đảo các thao tác đã chạy như ghi file hay đăng ký callback.

## 17. Tài liệu tham khảo

- [JLS Java SE 17 — Class Initialization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): quy định khi nào và theo thứ tự nào initialization xảy ra.
- [JLS 17 — Detailed Initialization Procedure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4.2): đồng bộ hóa và trạng thái lỗi.
- [JVMS 17 — Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5): quy tắc JVM và lỗi trong `<clinit>`.
- [Java 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): loading và class loader identity.
- [Java 17 — Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): overload điều khiển initialization.
- [Java 17 — ExceptionInInitializerError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html): lỗi khởi tạo lớp.
- [Java 17 — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html): lỗi định nghĩa class.

**Ghi nhớ:** **Loading ≠ initialization.** Static field initializers và static blocks chạy theo source order, sau initialization cần thiết của superclass; `loadClass`, class literal và `Class.forName(..., false, ...)` không ép `<clinit>`. Nếu `<clinit>` thất bại, class có thể thành erroneous: lượt đầu báo `ExceptionInInitializerError`, lượt sau báo `NoClassDefFoundError`. Một defining loader mới có thể tạo runtime class mới, nhưng không tự sửa lỗi ứng dụng.