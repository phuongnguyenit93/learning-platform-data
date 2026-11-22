# Khởi tạo lớp trước khi thực thi các thao tác yêu cầu trong Java

Một lớp có thể đã được **nạp (loaded)** và **liên kết (linked)** nhưng khối `static` của nó vẫn chưa chạy. JVM chỉ **khởi tạo (initialize)** lớp hoặc interface khi một thao tác cụ thể đòi hỏi điều đó. Trước khi cho phép thao tác tiếp tục, JVM bảo đảm quá trình khởi tạo cần thiết đã hoàn tất, hoặc báo lỗi nếu khởi tạo thất bại. Cơ chế này giải thích vì sao `SomeType.class` thường không in log `static`, nhưng `new SomeType()` hoặc `SomeType.run()` lại có thể in log ngay lần đầu sử dụng.

Bài này tập trung vào **khi nào và theo thứ tự nào JVM khởi tạo lớp trước các thao tác yêu cầu**, thuộc nhóm **Vòng đời lớp** của Java core – classloader. Mục tiêu là dự đoán được thời điểm chạy `<clinit>`, nhận diện thao tác kích hoạt và không kích hoạt khởi tạo, hiểu bảo đảm trong môi trường nhiều luồng và phân tích được lỗi khi static initializer thất bại.

## 1. Phân biệt loading, linking và initialization

| Giai đoạn | Công việc chính | Có chạy các lệnh trong `static { ... }` không? |
| --- | --- | --- |
| **Loading** | Tìm/đọc định nghĩa nhị phân, tạo đối tượng `Class` tương ứng với tên và defining class loader | Không phải bước chạy static initializer |
| **Linking – verification** | Kiểm chứng tính hợp lệ và an toàn cấu trúc của bytecode | Không |
| **Linking – preparation** | Cấp phát/trang bị trạng thái cho các static field và đặt giá trị mặc định như `0`, `false`, `null` | Không chạy mã Java của static initializer |
| **Linking – resolution** | Giải quyết các symbolic reference tới kiểu, field, method theo quy tắc JVM; có thể sớm hoặc theo nhu cầu | Bản thân một thao tác resolution thông thường không đồng nghĩa khởi tạo lớp được tham chiếu |
| **Initialization** | Thiết lập các giá trị hằng qua metadata `ConstantValue` khi áp dụng, khởi tạo superclass/default-method superinterfaces cần thiết, thực thi logic khởi tạo lớp/interface | Có, khi class/interface có mã cần thực thi |

Trong JVM Java 17, phần **initialization** là lúc các `final static` có `ConstantValue` được gán giá trị đặc tả và phương thức khởi tạo `<clinit>` được thực thi. Trước đó, các static field đã được chuẩn bị với giá trị mặc định. Do vậy không nên đồng nhất việc “static field đã tồn tại” với việc “static field đã hoàn tất gán giá trị khởi tạo”.

Ví dụ:

```java
class Settings {
    static int port = loadPort();

    static int loadPort() {
        System.out.println("Loading port");
        return 8080;
    }
}
```

Mã `loadPort()` chạy **khi khởi tạo `Settings`**, không phải chỉ vì một công cụ đã load `Settings.class` vào JVM. Phân biệt này còn quan trọng khi dùng classpath scanning, reflection, plugin loader và công cụ kiểm tra metadata.

Một class đã hoàn thành initialization được xem là đã khởi tạo trong phạm vi **định nghĩa class đó**. Cùng một tên lớp nếu được hai defining loader khác nhau định nghĩa sẽ có hai thực thể `Class` và trạng thái khởi tạo riêng; không có quy tắc “một lần cho mọi lớp cùng tên trong toàn bộ ứng dụng”.

## 2. Những thao tác nào buộc khởi tạo?

Theo quy tắc Java/JVM, thời điểm kích hoạt phụ thuộc **thao tác được thực thi** và **lớp/interface thực sự khai báo thành viên đã được resolve**, chứ không chỉ chuỗi ký tự dùng để viết tên lớp trong mã nguồn.

| Thao tác / tình huống | Có yêu cầu khởi tạo? | Giải thích |
| --- | --- | --- |
| `new Worker()` | **Có** đối với `Worker` trước khi tạo instance | Bytecode `new` yêu cầu class được khởi tạo; superclass và một số superinterface cũng được khởi tạo theo quy tắc |
| `Worker.work()` với `static void work()` do `Worker` khai báo | **Có** | Lệnh `invokestatic` yêu cầu khởi tạo kiểu khai báo method được resolve |
| Đọc `Worker.count` với `static int count` không phải constant variable | **Có** | `getstatic` yêu cầu kiểu khai báo field đã được khởi tạo |
| Ghi `Worker.count = 5` | **Có** | `putstatic` yêu cầu kiểu khai báo field đã được khởi tạo |
| `Worker.COMPILE_TIME_CONST` với `static final int` gán constant expression | **Không chỉ vì việc đọc hằng này** | Compiler có thể thay giá trị trực tiếp vào bytecode; không cần thực hiện `getstatic` tới field |
| `Worker.class` | **Không do riêng class literal** | Có thể lấy đối tượng `Class` mà chưa khởi tạo `Worker` |
| `new Worker[10]` | **Không do riêng việc tạo mảng** | Tạo mảng đối tượng khác với tạo instance `Worker`; component class không bị buộc khởi tạo |
| `ClassLoader.loadClass("pkg.Worker")` | **Không do riêng lệnh loadClass** | Thường đưa class vào trạng thái đã load; chính việc load không đồng nghĩa initialization |
| `Class.forName("pkg.Worker")` | **Có** theo overload một tham số | Overload này yêu cầu initialization của kiểu tìm được |
| `Class.forName(name, false, loader)` | **Không yêu cầu initialization** | Tham số `initialize=false` chủ ý tránh kích hoạt |
| Lấy metadata qua nhiều API như `getName()`, `getDeclaredMethods()` | **Không do riêng thao tác tra cứu metadata thông thường** | Reflection tra cứu và reflection gọi thực thi là hai việc khác nhau |
| Gọi static method qua `Method.invoke` hoặc đọc static field qua `Field.get` | **Có khi việc truy cập thực sự cần** | Một số phương thức reflection kích hoạt initialization của declaring class |
| JVM chọn class khởi đầu chương trình | **Có** | Initial class/interface được khởi tạo theo quy tắc khởi động JVM |
| Khởi tạo một subclass | **Có** với các superclass chưa được khởi tạo | Bảo đảm các lớp cha cần thiết được khởi tạo trước lớp con |

Ở tầng bytecode, bốn lệnh quan trọng là **`new`, `getstatic`, `putstatic`, `invokestatic`**. Với `getstatic`, `putstatic` và `invokestatic`, kiểu cần khởi tạo là **declaring class/interface** của field hoặc method sau khi symbolic reference được resolve.

Các trường hợp đặc biệt hơn gồm lần gọi đầu tiên một `MethodHandle` đã được resolve thuộc dạng `REF_getStatic`, `REF_putStatic`, `REF_invokeStatic`, `REF_newInvokeSpecial`; bootstrap method của một số call site `invokedynamic` cũng có thể kích hoạt khởi tạo. Đây là mở rộng cùng nguyên tắc: phải hoàn tất trạng thái của kiểu trước khi thực thi thao tác tĩnh/tạo instance mà lời gọi thực sự yêu cầu.

**Cần phân biệt hai phát biểu:**

- “Java source nhắc tới tên `Worker`” **không đủ** để kết luận `Worker` khởi tạo.
- “JVM thực thi `getstatic` hoặc `invokestatic` tới thành viên khai báo bởi `Worker`” là một **điều kiện yêu cầu khởi tạo** của `Worker` nếu nó chưa khởi tạo.

## 3. Ví dụ chạy được: điều gì kích hoạt và không kích hoạt?

Tạo duy nhất file `InitializationDemo.java`:

```java
public class InitializationDemo {
    static class Parent {
        static final int LIMIT = 42; // constant variable: có thể được inline

        static int first = announce("Parent.first", 7);

        static {
            System.out.println("Parent.block");
        }

        static final Integer BOXED = createBoxed(); // không là constant variable

        static int announce(String label, int value) {
            System.out.println(label);
            return value;
        }

        static Integer createBoxed() {
            System.out.println("Parent.BOXED");
            return 99;
        }
    }

    static class Child extends Parent {
        static {
            System.out.println("Child.block");
        }

        static void ping() {
            System.out.println("Child.ping");
        }
    }

    static class Unused {
        static {
            System.out.println("Unused.block");
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("1 LIMIT=" + Child.LIMIT);
        System.out.println("2 literal=" + Unused.class.getSimpleName());
        System.out.println("3 array=" + new Unused[0].length);

        Class<?> type = Class.forName(
            "InitializationDemo$Unused",
            false,
            InitializationDemo.class.getClassLoader()
        );
        System.out.println("4 loaded=" + type.getSimpleName());

        System.out.println("5 call Child.ping()");
        Child.ping();

        System.out.println("6 BOXED=" + Child.BOXED);
        System.out.println("7 forName true");
        Class.forName("InitializationDemo$Unused");

        System.out.println("8 again");
        Child.ping();
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 InitializationDemo.java
java InitializationDemo
```

Stdout:

```text
1 LIMIT=42
2 literal=Unused
3 array=0
4 loaded=Unused
5 call Child.ping()
Parent.first
Parent.block
Parent.BOXED
Child.block
Child.ping
6 BOXED=99
7 forName true
Unused.block
8 again
Child.ping
```

Đọc theo thứ tự:

1. `Child.LIMIT` là cách truy cập hằng compile time được **khai báo ở `Parent`**. Giá trị `42` có thể được nhúng vào mã client; trong ví dụ không có `Parent.first` hay `Child.block` ở bước 1.
2. `Unused.class` chỉ lấy `Class<?>`; `new Unused[0]` chỉ tạo mảng. Không bước nào buộc chạy `Unused.block`.
3. `Class.forName(name, false, loader)` chỉ yêu cầu tìm/nạp và liên kết theo nhu cầu, **không yêu cầu** chạy static block; vì vậy dòng `4 loaded=Unused` vẫn xuất hiện trước `Unused.block`.
4. Lần đầu gọi `Child.ping()`, JVM phải khởi tạo `Child` trước khi chạy method body. `Parent` là superclass chưa được khởi tạo, nên `Parent` chạy trước: gán `first`, chạy static block, tính `BOXED`; sau đó `Child.block` mới chạy, cuối cùng method in `Child.ping`.
5. `Child.BOXED` thực tế là static field do `Parent` khai báo. `Parent` đã khởi tạo, nên chỉ in giá trị `99`; đọc field qua tên subclass **không tự tạo thêm lần chạy `<clinit>`**.
6. `Class.forName("InitializationDemo$Unused")` với overload một đối số yêu cầu khởi tạo `Unused`, vì vậy `Unused.block` lúc này mới xuất hiện.
7. Gọi `Child.ping()` lần nữa chỉ chạy **method body**. Khởi tạo `Parent` và `Child` đã hoàn tất và không lặp lại.

Chú ý: code trên là **một chương trình chạy độc lập**. Nếu chỉ chạy `javap` mà không chạy `java InitializationDemo`, việc phân tích class file bằng công cụ không chứng minh rằng static initializer của chính ứng dụng đã chạy.

## 4. `<clinit>` được tạo và thực thi như thế nào?

`javac` thường tổng hợp static field initializer và các khối `static { ... }` của **cùng một class** thành phương thức khởi tạo class tên **`<clinit>`** trong bytecode. Chương trình Java không gọi trực tiếp phương thức này.

Với ví dụ `Parent`, thứ tự logic là:

```text
Giá trị static ban đầu sau preparation: first=0, BOXED=null
          |
JVM quyết định phải initialize Parent
          |
Áp dụng ConstantValue của LIMIT (=42) nếu cần
          |
first = announce("Parent.first", 7)  -> in "Parent.first"
          |
static { println("Parent.block"); } -> in "Parent.block"
          |
BOXED = createBoxed()               -> in "Parent.BOXED"
          |
Parent hoàn tất initialization
          |
JVM tiếp tục initialize Child
```

**Thứ tự trong cùng class:** các initializer của static field và static block chạy theo **thứ tự xuất hiện trong source**. Sau khi superclass và các superinterface thuộc diện bắt buộc được khởi tạo, JVM mới thực thi phần khởi tạo của class hiện tại.

Dùng:

```bash
javap -c -p 'InitializationDemo$Parent'
javap -c -p 'InitializationDemo$Child'
```

Trong PowerShell và các shell hỗ trợ dấu nháy đơn, cú pháp trên giữ nguyên ký tự `$` trong tên nested class. Trong Windows Command Prompt có thể dùng `javap -c -p "InitializationDemo$Parent"`. Tìm khối `static {};` do `javap` hiển thị: đó là phần biểu diễn bytecode của `<clinit>`, với những lệnh như `putstatic`, `invokestatic` và lệnh in output.

**Không nhất thiết class nào cũng có `<clinit>`.** Class không cần công việc khởi tạo tại runtime có thể không có phương thức ấy. Tuy vậy JVM vẫn theo dõi trạng thái “đã initialized” để đáp ứng quy tắc vòng đời.

### Trạng thái mặc định và đọc giá trị trước khi gán

Trong quá trình khởi tạo, một static field có thể đã tồn tại với giá trị mặc định trong khi initializer của nó chưa chạy đến. Để nhìn thấy điều này, tạo `InitializationOrder.java`:

```java
public class InitializationOrder {
    static int first = readSecond();
    static int second = 9;

    static int readSecond() {
        return second;
    }

    public static void main(String[] args) {
        System.out.println(first + "," + second);
    }
}
```

```bash
javac --release 17 InitializationOrder.java
java InitializationOrder
```

Stdout chính xác:

```text
0,9
```

Tại lúc gán `first`, `readSecond()` thấy `second` còn bằng giá trị mặc định `0`; lệnh `second = 9` chỉ xảy ra sau đó. Đọc trực tiếp một field được khai báo *sau* trong initializer có thể vướng quy tắc **illegal forward reference** của ngôn ngữ; qua một method như ví dụ thì hợp lệ. Không nên dựa vào thứ tự phức tạp như vậy để thiết kế trạng thái chia sẻ.

## 5. Superclass và superinterface: cái nào được khởi tạo trước?

Khi khởi tạo một **class**, JVM cần khởi tạo các superclass chưa được khởi tạo. Ngoài ra, những **superinterface trực tiếp hoặc gián tiếp khai báo default method** cũng thuộc diện khởi tạo bắt buộc theo quy tắc JVMS/JLS. Điều này tinh tế hơn câu “interface luôn khởi tạo sau class” hoặc “mọi interface đều khởi tạo trước class”: cả hai câu đều sai.

Trong ví dụ trước, `Child` buộc khởi tạo `Parent` trước, nên `Parent.first`, `Parent.block`, `Parent.BOXED` luôn đứng trước `Child.block`.

### Static field kế thừa: kiểu khai báo mới là điều quyết định

Tạo file `FieldOwnerDemo.java`:

```java
public class FieldOwnerDemo {
    static class Base {
        static int count = init();

        static int init() {
            System.out.println("Base.init");
            return 10;
        }
    }

    static class Derived extends Base {
        static {
            System.out.println("Derived.init");
        }
    }

    public static void main(String[] args) {
        System.out.println(Derived.count);
    }
}
```

```bash
javac --release 17 FieldOwnerDemo.java
java FieldOwnerDemo
```

Stdout:

```text
Base.init
10
```

`Derived.count` trong source chỉ ra field **được khai báo bởi `Base`**, do đó JVM yêu cầu khởi tạo `Base`, **không tự khởi tạo `Derived`**. Khác với `new Derived()` hoặc gọi static method thực sự được khai báo bởi `Derived`.

### Interface có default method

Tạo file `DefaultInterfaceDemo.java`:

```java
public class DefaultInterfaceDemo {
    interface Feature {
        Object MARKER = report();

        static Object report() {
            System.out.println("Feature.init");
            return new Object();
        }

        default void execute() { }
    }

    static class Service implements Feature {
        static {
            System.out.println("Service.init");
        }
    }

    public static void main(String[] args) {
        new Service();
    }
}
```

```bash
javac --release 17 DefaultInterfaceDemo.java
java DefaultInterfaceDemo
```

Stdout:

```text
Feature.init
Service.init
```

`Service` là class implement `Feature`; `Feature` khai báo một `default` method, nên initialization của `Service` dẫn đến khởi tạo `Feature` trước. `MARKER` được tính trong quá trình initialization của interface, dù code ở `main` không trực tiếp truy cập `MARKER`.

**Chiều ngược lại không đối xứng:** tự khởi tạo một interface không mặc nhiên khởi tạo mọi superinterface của nó. Một truy cập static field qua tên interface con cũng phải xét nơi field **thực sự được khai báo**. Nếu interface có field hằng compile time được inline, truy cập giá trị ấy cũng không nhất thiết khởi tạo interface khai báo.

## 6. Reflection và việc nạp class không giống initialization

Có hai overload dễ nhầm:

```java
Class<?> a = Class.forName("com.example.Plugin");
Class<?> b = Class.forName(
    "com.example.Plugin",
    false,
    Thread.currentThread().getContextClassLoader()
);
```

Đoạn trên là **minh họa API**, chỉ chạy nếu `com.example.Plugin` tồn tại và class loader phù hợp. Với overload một tham số, việc tìm class đi kèm yêu cầu khởi tạo; với overload ba tham số, `false` có nghĩa **không yêu cầu initialize lúc tra cứu**. Đến khi client thật sự `new`, gọi static method, truy cập non-constant static field hoặc reflection thực thi một thao tác cần initialization, quá trình đó vẫn có thể bắt đầu.

Các thao tác thường **không tự yêu cầu** khởi tạo class đích: lấy `T.class`, tạo `T[]`, xem tên từ `Class<?>`, tìm danh sách method/field, kiểm tra kiểu bằng `instanceof` hay `checkcast`. Một API metadata vẫn có thể cần load/resolve các kiểu liên quan hoặc sinh lỗi khác; “không khởi tạo class đích” không có nghĩa “không làm bất kỳ việc gì”.

Ngược lại, các thao tác thực sự **gọi** static method (`Method.invoke`), **đọc/ghi** static field (`Field.get`/`Field.set`) sẽ tuân thủ điều kiện khởi tạo của declaring class. Phân biệt tra cứu descriptor với sử dụng thành viên giúp tránh gây tác dụng phụ khi plugin scanner chỉ muốn đọc metadata.

## 7. JVM bảo đảm khởi tạo đúng một lần như thế nào khi có nhiều luồng?

Đối với một **định nghĩa class/interface**, quy trình initialization phối hợp các thread để tránh chạy hai lần static initializer. Có thể hình dung trạng thái:

```text
VERIFIED + PREPARED, CHƯA INITIALIZED
        |
        | thread đầu tiên thực hiện thao tác yêu cầu
        v
INITIALIZATION IN PROGRESS (một thread sở hữu)
        |               |
        |               +-- thread khác chờ kết quả
        |               +-- chính thread đó yêu cầu đệ quy: JVM xử lý riêng
        |
        +-- hoàn tất thành công --> INITIALIZED
        |
        +-- thất bại ------------> ERRONEOUS
                                    |
                                    +-- lần yêu cầu sau: NoClassDefFoundError
```

Quy tắc quan trọng:

- Nếu thread A đang khởi tạo `T`, thread B đồng thời thực hiện thao tác yêu cầu `T` phải chờ kết quả theo cơ chế JVM. Các thread sử dụng thành công sau đó nhìn thấy kết quả initialization theo bảo đảm của mô hình bộ nhớ Java.
- Nếu chính thread A vô tình yêu cầu khởi tạo lại `T` trong lúc đang thực hiện `T.<clinit>`, JVM nhận biết yêu cầu đệ quy từ cùng thread; không chạy lại toàn bộ initializer.
- Điều này **không loại bỏ deadlock** nếu hai thread đồng thời khởi tạo hai class khác nhau rồi mỗi class lại yêu cầu chờ class kia. Không thực hiện khóa chéo, I/O vô hạn hoặc thread join trong static initializer.
- Sau khi khởi tạo thành công, JVM **không chạy lại** `<clinit>` chỉ vì nhiều instance của class được tạo sau đó. Constructor (`<init>`) của từng instance là một cơ chế khác.

### Ứng dụng: Initialization-on-demand holder

Mẫu phổ biến dùng trạng thái initialization để lazy-create một singleton:

```java
public final class LazyService {
    private LazyService() { }

    private static final class Holder {
        static final LazyService INSTANCE = new LazyService();
    }

    public static LazyService getInstance() {
        return Holder.INSTANCE;
    }
}
```

Đây là **class hoàn chỉnh có thể biên dịch**; đoạn này không có `main`. Lần gọi `LazyService.getInstance()` phải khởi tạo lớp `LazyService` trước khi gọi method, nhưng **chưa bắt buộc khởi tạo nested `Holder` trước khi tới dòng truy cập `Holder.INSTANCE`**. Việc thực hiện `getstatic` cho `Holder.INSTANCE` kích hoạt khởi tạo `Holder` và tạo một `LazyService` duy nhất cho defining loader của `Holder`. Mẫu này dựa vào cơ chế đồng bộ initialization của JVM, không cần tự thêm `synchronized` vào getter.

Một static field được khai báo là `final` **không tự động** trở thành constant variable; `Holder.INSTANCE` là reference được tính bằng `new`, nên đọc nó phải tuân theo `getstatic`, khác với hằng nguyên `static final int LIMIT = 42`.

## 8. Điều gì xảy ra nếu static initializer thất bại?

Tạo file `FailedInitialization.java`:

```java
public class FailedInitialization {
    static class Broken {
        static int value = fail();

        static int fail() {
            throw new IllegalStateException("boom");
        }
    }

    public static void main(String[] args) {
        for (int attempt = 1; attempt <= 2; attempt++) {
            try {
                System.out.println(Broken.value);
            } catch (LinkageError error) {
                System.out.println(
                    attempt + ": " + error.getClass().getSimpleName()
                );
            }
        }
    }
}
```

```bash
javac --release 17 FailedInitialization.java
java FailedInitialization
```

Stdout:

```text
1: ExceptionInInitializerError
2: NoClassDefFoundError
```

Lần đầu truy cập `Broken.value`, JVM bắt đầu initialization và gọi `fail()`. `IllegalStateException` là exception không thuộc `Error`, vì thế JVM bọc nó trong `ExceptionInInitializerError`, một subclass của `LinkageError`. Định nghĩa `Broken` chuyển sang trạng thái **erroneous**. Lần truy cập thứ hai không khởi tạo lại; JVM phát `NoClassDefFoundError` vì class đã thất bại trong quá trình initialization.

Nếu lỗi gốc trong `<clinit>` đã là một subclass của `Error`, JVM thường chuyển tiếp `Error` ấy trong lượt thất bại ban đầu, thay vì bọc bằng `ExceptionInInitializerError`. Nếu superclass thất bại khi đang khởi tạo subclass, subclass cũng có thể bị đánh dấu erroneous. Khi phân tích, hãy xem **exception đầu tiên và cause**; chỉ nhìn dòng `NoClassDefFoundError` sau đó dễ kết luận nhầm rằng file class “biến mất”.

Trong một class loader đang dùng, lỗi initialization thường không khắc phục bằng việc gọi lại cùng class. Cần sửa nguyên nhân gốc (cấu hình, dependency, exception trong static code), rồi tái khởi động hoặc sử dụng một định nghĩa mới qua class loader phù hợp khi kiến trúc thực sự hỗ trợ.

**Quy tắc thiết kế thực tế:** tránh network call, truy vấn DB, thao tác file dễ thất bại và phụ thuộc lẫn nhau giữa nhiều class trong static initializer. Khi cần retry một tài nguyên, dùng API khởi tạo có quản lý trạng thái và lỗi rõ ràng thay vì biến lỗi tạm thời thành class erroneous.

## 9. Dùng `javap` để nhận diện trigger trước khi chạy

Sau khi biên dịch `InitializationDemo.java`, thực hiện:

```bash
javap -c -p InitializationDemo
javap -c -p 'InitializationDemo$Parent'
javap -c -p 'InitializationDemo$Child'
javap -v -p InitializationDemo
```

Mục tiêu quan sát:

1. Tìm `invokestatic` tại call site `Child.ping()`. Lệnh này khiến JVM phải bảo đảm declaring class đã được initialize trước khi method chạy.
2. Tìm `getstatic` cho `Parent.BOXED` (có thể được tham chiếu qua tên `Child` ở source nhưng owner sau biên dịch là nơi field khai báo).
3. Với `Child.LIMIT`, compiler có thể tạo chuỗi literal `"1 LIMIT=42"` để in hoặc dùng một hằng trực tiếp, **không** cần lệnh đọc static field `LIMIT` từ `Parent`. Java có thể gộp constant expression ngay khi biên dịch; hãy kiểm tra bytecode thực tế.
4. Trong output `javap -c -p 'InitializationDemo$Parent'`, khối `static {};` mô tả trình tự của logic khởi tạo class, kể cả việc ghi các static field không phải constant variable.
5. Dùng `javap -v` để xem mục constant pool, lệnh tham chiếu trường/phương thức và metadata `ConstantValue` khi có. **Sự tồn tại của tên kiểu trong constant pool chưa chứng minh class đã được initialize.**

Thông điệp quan trọng là: **symbolic reference được ghi khi biên dịch, resolution xác định thực thể runtime, còn initialization bắt đầu khi điều kiện JVM yêu cầu**. Vì vậy chỉ nhìn mã source có dấu chấm `SomeClass.member` không đủ; phải xét member là static/instance, có phải compile-time constant, ai thực sự khai báo, và lệnh bytecode được phát.

Nếu cần logging lớp được nạp, có thể thử `java -Xlog:class+load=info InitializationDemo` trên JVM HotSpot hỗ trợ unified logging. Tuy nhiên **log load không phải log khởi tạo**. Để kiểm chứng initialization của ví dụ, quan sát các dòng do `static` in và thứ tự lệnh thực sự.

## 10. Các hiểu lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Chỉ cần import hoặc nhắc tới tên class là chạy static block.” | `import` là cú pháp compile time; class literal, metadata lookup và việc tạo mảng không tự gây initialization. |
| “Loading một class đồng nghĩa khởi tạo class đó.” | Loading/linking và initialization là các pha khác nhau; `Class.forName(name, false, loader)` minh họa sự tách biệt. |
| “Mọi static field access luôn chạy static block.” | Field hằng compile time có thể được inline; static field kế thừa chỉ yêu cầu initialize nơi khai báo field thực sự. |
| “Class con có thể chạy static initializer trước superclass.” | Khi bắt đầu initialization của subclass, superclass cần thiết phải hoàn thành initialization trước. |
| “Mọi interface cha luôn được khởi tạo trước interface con.” | Tự khởi tạo một interface không mặc nhiên khởi tạo các superinterface; default-method superinterfaces quan trọng khi khởi tạo một class. |
| “Mỗi `new` sẽ chạy lại static block.” | Static initialization cho một định nghĩa class chỉ chạy một lần thành công; constructor chạy cho từng instance. |
| “Một initializer lỗi sẽ được tự động thử lại ở lần truy cập tiếp.” | Định nghĩa class rơi vào trạng thái erroneous; các lần tiếp theo thường ném `NoClassDefFoundError`. |
| “`static final` nào cũng được inline.” | Chỉ **constant variable** với kiểu primitive/String và constant expression đáp ứng điều kiện; object được tạo bằng `new` không thuộc nhóm này. |
| “Hai loader nạp cùng tên class dùng chung static state.” | Danh tính class gắn với defining loader; mỗi định nghĩa có static state và trạng thái initialization riêng. |

## 11. Câu hỏi tự kiểm tra

**1.** `Report.class.getName()` và `new Report()` khác nhau như thế nào về initialization?

**Đáp án:** class literal và đọc tên không tự yêu cầu `Report` initialization; tạo instance `Report` bằng `new` là thao tác yêu cầu class đã initialize trước khi instance được tạo.

**2.** Vì sao `Derived.count` chỉ in `Base.init` ở ví dụ `FieldOwnerDemo`?

**Đáp án:** `count` là static field được khai báo trong `Base`. `getstatic` sau resolution áp dụng cho declaring class `Base`, không buộc initialize `Derived` chỉ vì cú pháp source dùng tên `Derived`.

**3.** `static final Integer ANSWER = 42` và `static final int ANSWER = 42` có giống nhau khi đọc qua class không?

**Đáp án:** Không. `Integer` không phải loại constant variable theo JLS nên initializer và `getstatic` liên quan có thể yêu cầu initialization. `int` với constant expression `42` là constant variable, có thể được inline vào class sử dụng.

**4.** Tại sao trong `InitializationDemo` cả `Parent.first` và `Parent.BOXED` in ra trước `Child.block`?

**Đáp án:** `Child` là subclass nên quá trình initialization yêu cầu superclass `Parent` hoàn thành trước. Trong `Parent`, static field initializer và static block thực thi theo thứ tự source.

**5.** Nếu thread A đang chạy `<clinit>` của một class và thread B cần sử dụng static method của class đó, B có thể chạy method trước khi initialization hoàn tất không?

**Đáp án:** Không. JVM phối hợp initialization giữa các thread; B chờ trạng thái thành công hoặc nhận lỗi. Điều này không có nghĩa mọi trường hợp static initializer phụ thuộc khóa giữa các class đều không thể deadlock.

**6.** Vì sao log lỗi có `NoClassDefFoundError` dù file `.class` vẫn có mặt?

**Đáp án:** Một khả năng là initialization trước đó thất bại, class bị đánh dấu erroneous và lần yêu cầu sau ném `NoClassDefFoundError`. Cần xem exception gốc ban đầu cùng cause, đồng thời vẫn kiểm tra các khả năng khác như dependency/classpath thiếu.

## Tóm tắt quy trình suy luận

Khi muốn biết “dòng này đã làm chạy `static` chưa?”, hãy xác định:

1. Bytecode đang thực hiện **`new`**, **`getstatic`**, **`putstatic`**, **`invokestatic`**, hay thao tác tương đương qua reflection/MethodHandle?
2. Kiểu nào **thực sự được tham chiếu và khai báo member** sau resolution? Có phải compile-time constant đã được inline không?
3. Kiểu ấy đã initialize thành công chưa? Nếu chưa, JVM phải xử lý superclass và các superinterface có default method cần thiết, rồi mới chạy `<clinit>` của chính kiểu đó.
4. Nếu đồng thời có thread khác khởi tạo hoặc initializer thất bại, thao tác đang xét sẽ chờ hoặc nhận lỗi theo trạng thái class.

Hai nguồn chuẩn để đối chiếu các trường hợp ranh giới và điều kiện lỗi:

- [Java Language Specification 17 – 12.4 Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4).
- [Java Virtual Machine Specification 17 – 5.5 Initialization](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5).

Áp dụng đúng các quy tắc này giúp dự đoán side effect của class loader/reflection, tổ chức lazy singleton an toàn và tìm được nguyên nhân của lỗi static initialization khi ứng dụng chạy.
