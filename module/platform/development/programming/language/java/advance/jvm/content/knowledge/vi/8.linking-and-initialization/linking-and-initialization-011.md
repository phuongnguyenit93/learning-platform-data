# Lỗi khởi tạo: `ExceptionInInitializerError` và trạng thái lớp lỗi trong JVM

Một class Java có thể **nạp thành công**, **liên kết hợp lệ**, nhưng **thất bại khi khởi tạo tĩnh**. Khi công việc khởi tạo một class hoặc interface kết thúc bất thường, JVM ghi nhận định nghĩa runtime đó ở **trạng thái lỗi (erroneous state)**. Từ đây, những lần yêu cầu khởi tạo tiếp theo **không tự chạy lại static initializer**. Kết quả thường gây ngạc nhiên: lần đầu có thể thấy `ExceptionInInitializerError`, còn lần sử dụng sau nhận `NoClassDefFoundError`.

Đây không phải hai tên gọi thay thế cho cùng một lỗi. Chúng phản ánh **hai thời điểm và hai trạng thái runtime khác nhau**:

- **Lần đầu:** mã trong hoặc gắn với class initialization phát sinh exception; nếu throwable ban đầu **không phải `Error`**, JVM thường bọc nó trong **`ExceptionInInitializerError`** và đánh dấu class ở trạng thái lỗi.
- **Lần sau:** JVM thấy class đã ở **erroneous state** nên không khởi tạo lại và ném **`NoClassDefFoundError`** theo quy tắc initialization.
- Nếu công việc khởi tạo ban đầu ném một đối tượng **`Error`**, JVM có thể truyền tiếp chính `Error` đó thay vì bọc trong `ExceptionInInitializerError`; class vẫn thất bại khởi tạo và bị đánh dấu lỗi.
- Thông báo lỗi, chuỗi `cause` và stack trace cụ thể có thể khác theo JVM/version; khi phân tích phải giữ **toàn bộ chuỗi lỗi từ lần đầu**, không chỉ nhìn lỗi cuối cùng.

Bài học này giải thích vòng đời khởi tạo, cơ chế lỗi, các trường hợp kích hoạt, cách tái hiện bằng Java 17+, nguyên nhân thường gặp và hướng xử lý an toàn.

## 1. Loading, linking và initialization là những việc khác nhau

Trong JVM, một class/interface đi qua các giai đoạn logic:

```text
Định nghĩa class được JVM yêu cầu
             │
             ▼
        Loading
             │
             ▼
        Linking
   ┌─────────┼─────────┐
 Verification Preparation Resolution
             │
             ▼
    Initialization khi cần
      (chạy <clinit>
       theo quy tắc)
             │
     ┌───────┴────────┐
     ▼                ▼
 Thành công          Thất bại
     │                │
 initialized        erroneous
     │                │
 dùng tiếp        không tự retry
```

Sơ đồ có mục đích **phân biệt trách nhiệm**, không khẳng định JVM phải resolve toàn bộ constant pool trước khi chạy `<clinit>`. Một số reference có thể được giải quyết muộn theo yêu cầu. Việc nạp một class không đồng nghĩa nó đã được initialized.

| Giai đoạn | Ý nghĩa | Có tự động chạy static initializer của class không? |
| --- | --- | --- |
| Loading | Tạo biểu diễn runtime từ định nghĩa do loader cung cấp | Không đồng nghĩa |
| Verification | Xác minh class file/bytecode thỏa các luật JVM | Không |
| Preparation | Chuẩn bị static fields, thiết lập giá trị mặc định và các `ConstantValue` theo luật | Không phải chạy toàn bộ static initializer |
| Resolution | Chuyển symbolic references thành liên kết runtime phù hợp | Không mặc nhiên |
| Initialization | Thực hiện công việc khởi tạo class/interface cần thiết | **Có**, nếu có code `<clinit>` và các bước bắt buộc khác |

Trong Java source:

```java
class Config {
    static int port = parsePort();

    static int parsePort() {
        return Integer.parseInt("not-a-number");
    }
}
```

Đây là **class minh họa** có thể biên dịch nhưng khởi tạo tĩnh sẽ lỗi khi một active use yêu cầu `Config` initialization. Điều đó không có nghĩa ClassFile sai cấu trúc hay verifier không chấp nhận bytecode.

## 2. `<clinit>` được sinh từ đâu?

Tên **`<clinit>`** là phương thức khởi tạo class/interface đặc biệt trong mô hình JVM. Với class có công việc static cần chạy, `javac` thường tổng hợp `<clinit>:()V` từ **static field initializers** và **static initializer blocks**, thực hiện theo thứ tự phù hợp với khai báo nguồn.

Ví dụ:

```java
class ServerSettings {
    static int base = loadBase();

    static {
        base += 2;
    }

    static int loadBase() {
        return 8000;
    }
}
```

Nội dung tương ứng `<clinit>` có thể làm:

```text
base = loadBase();
base = base + 2;
return;
```

Đây là **pseudocode mô tả hoạt động**, không phải bytecode đầy đủ. Khi initialization thành công, `ServerSettings.base == 8002`.

Nếu thay `loadBase()` bằng phương thức ném exception, `<clinit>` có thể dừng giữa chừng: những field được khởi tạo trước đó có thể đã bị ghi giá trị, trong khi những static initializer sau **chưa chạy**. Nhưng sau thất bại, class không tự trở về trạng thái “chưa initialized” để thực hiện lại từ đầu.

### `<init>` không phải `<clinit>`

- `<init>` là constructor/instance initialization method, gắn với **quá trình tạo từng object**.
- `<clinit>` gắn với **class/interface initialization**, thường chỉ một lần cho từng định nghĩa runtime nếu thành công.
- `new Example()` có thể **kích hoạt khởi tạo class trước**, rồi mới có thể chạy constructor body. Nếu class initialization thất bại, constructor body **không đạt tới**.
- Exception ném **trong constructor body `<init>`** không tự động biến class thành erroneous. Có thể tạo instance khác bằng constructor đó sau khi bắt exception, nếu logic cho phép.

Phân biệt này đặc biệt quan trọng khi nhìn stack trace: `ExceptionInInitializerError` phản ánh lỗi ở **class initialization**, không phải cứ có exception khi `new` thì đều là lỗi `<clinit>`.

## 3. Khi nào JVM yêu cầu initialization?

Class initialization thường được kích hoạt trước các **active uses**, trong đó có:

1. `new T()` khi `T` chưa initialized.
2. Lần thực thi `getstatic`/`putstatic` liên quan static field **được khai báo trong class/interface phải khởi tạo**, theo quy tắc tương ứng.
3. `invokestatic` tới static method của kiểu cần khởi tạo.
4. Một số thao tác reflection, method handles hoặc cơ chế bootstrap có yêu cầu initialization.
5. Trước khi class chính khởi chạy theo quy tắc JVM; và những trường hợp khác được JVMS quy định.

Ví dụ:

```java
class LazyStore {
    static int value = init();

    static int init() {
        System.out.println("LazyStore initialized");
        return 5;
    }
}
```

Một lệnh `System.out.println(LazyStore.value)` thông thường yêu cầu initialization trước khi đọc kết quả. Nhưng **không phải mọi lần nhắc tên class đều là active use**.

### 3.1. Những thao tác không tự buộc `<clinit>` chạy

```java
Class<?> clazz = LazyStore.class;
```

Class literal cho phép lấy `Class` object mà không tự yêu cầu `LazyStore` initialization. Tương tự, tạo **mảng tham chiếu** `new LazyStore[3]` không tự tạo ba `LazyStore` instances và không tự gọi constructor hay static initializer của component class.

Một overload hữu ích của reflection:

```java
Class.forName("LazyStore", false, someClassLoader);
```

Với `initialize=false`, API yêu cầu không initialize target class chỉ vì lookup này. Đoạn trên **chỉ minh họa cú pháp** và cần có biến `someClassLoader` phù hợp, code xử lý `ClassNotFoundException`, và binary name chính xác.

### 3.2. Compile-time constant khác static value tính lúc chạy

```java
class Constants {
    static final int LIMIT = 100;
    static int runtimeValue = compute();

    static int compute() {
        System.out.println("Constants initializing");
        return 3;
    }
}
```

`Constants.LIMIT` là constant variable có thể được compiler **inline** vào caller, vì vậy việc chỉ dùng hằng số này không tự làm class initialized. `Constants.runtimeValue` cần công việc static initialization, nên truy cập thông thường kích hoạt nó.

Không đánh đồng mọi `static final` với compile-time constant. Ví dụ `static final Object HOLDER = new Object();` không phải hằng compile-time; cần thực thi khởi tạo object.

**Hệ quả thực tế:** ứng dụng có thể dùng một số constants hoặc Class literals bình thường dù sau đó active-use class lại dẫn đến lỗi initialization.

## 4. Bốn trạng thái JVM dùng khi khởi tạo một class/interface

*JVMS §5.5* mô tả cơ chế initialization bằng bốn trạng thái logic:

| Trạng thái | Diễn giải | Khi có yêu cầu initialization |
| --- | --- | --- |
| Verified/prepared, chưa initialized | Chưa bắt đầu công việc initialization | JVM bắt đầu quy trình |
| Initializing bởi một thread cụ thể | Một thread đã nhận trách nhiệm initialization | Thread khác chờ; chính thread đó yêu cầu đệ quy được xử lý đặc biệt |
| Fully initialized | Initialization đã thành công | Không chạy lại `<clinit>`; tiếp tục |
| **Erroneous** | Initialization trước đó thất bại | **Không retry**; JVM ném `NoClassDefFoundError` |

JVM có **initialization lock** riêng theo runtime class/interface để phối hợp concurrency. Khi một thread bắt đầu initialization, thread khác yêu cầu initialization cùng class sẽ không tự thực thi `<clinit>` song song. JVM cho phép một trường hợp **yêu cầu khởi tạo đệ quy trong chính thread đang initializing** hoàn thành phần yêu cầu lặp mà không đợi chính nó.

Không có Java API public tiêu chuẩn để đặt Class object từ `erroneous` trở về `uninitialized`. Trạng thái này gắn với **một runtime class definition**, không đơn thuần với chuỗi tên hay một object instance riêng.

### 4.1. Class được định danh theo defining loader

Hai runtime classes cùng binary name nhưng do hai **defining class loaders** khác nhau định nghĩa là hai loại runtime khác nhau. Mỗi định nghĩa có **trạng thái initialization riêng**, static fields riêng và lỗi riêng.

Do đó phát biểu chính xác là:

> Nếu initialization của **một runtime class/interface** thất bại, các yêu cầu initialization tiếp theo với **chính runtime type đó** không tự thử lại.

Tạo một class loader mới và nạp **một định nghĩa class mới** có thể có trạng thái initialization mới; đó không phải “reset” định nghĩa cũ. Trong ứng dụng thông thường, quá trình sửa lỗi thường cần deploy binary phù hợp hoặc khởi động lại quy trình/ứng dụng theo kiến trúc đang dùng, thay vì cố thao tác trạng thái JVM bằng reflection.

## 5. `ExceptionInInitializerError`: lỗi lần khởi tạo đầu tiên

Khi JVM thực thi class initialization, công việc này có thể thất bại do:

- Static field initializer đọc cấu hình không hợp lệ.
- Static block thao tác với tệp, môi trường hoặc tài nguyên thiếu.
- `Integer.parseInt`, chuyển kiểu, `null` dereference hay index sai trong đoạn code static.
- Một dependency được active-use trong lúc khởi tạo class lại thất bại initialization.
- Có lỗi nạp/liên kết/phân quyền hoặc lỗi runtime xảy ra trong chuỗi khởi tạo.
- Vòng phụ thuộc hoặc logic static quá phức tạp dẫn đến exception.

Ví dụ:

```java
class Broken {
    static int threshold = parse();

    static int parse() {
        return Integer.parseInt("invalid");
    }
}
```

Đây là **class minh họa**. Source biên dịch được, nhưng `new Broken()` lần đầu có thể gây:

```text
ExceptionInInitializerError
  caused by NumberFormatException
```

**Tại sao bọc?** Khi initialization thất bại do throwable **không phải `Error`**, quy trình JVM nỗ lực tạo `ExceptionInInitializerError` với nguyên nhân ban đầu, đánh dấu class erroneous và ném lỗi thích hợp. Mục tiêu là biểu thị rằng một **quá trình khởi tạo class** đã thất bại, không chỉ đơn thuần method `parse()` trả exception.

### 5.1. `ExceptionInInitializerError` thuộc nhóm nào?

```text
Throwable
└── Error
    └── LinkageError
        └── ExceptionInInitializerError
```

Nó là **`Error`**, không phải `Exception`. Vì vậy:

```java
try {
    new Broken();
} catch (Exception e) {
    // Không bắt được ExceptionInInitializerError
}
```

Đây là **mã minh họa**, không phải lớp chạy hoàn chỉnh. `catch (Exception)` không bắt được `Error` nói chung. Khi cần thể hiện bài lab, có thể bắt chính xác `ExceptionInInitializerError` hoặc `LinkageError` đã biết để đọc cause. Trong code production, **không nên nuốt lỗi initialization để tiếp tục sử dụng class lỗi**.

### 5.2. Xem cause gốc

`ExceptionInInitializerError` hỗ trợ:

```java
Throwable original = error.getCause();
Throwable legacy = error.getException();
```

Trong đó `error` là biến có kiểu `ExceptionInInitializerError` và có giá trị phù hợp. `getException()` là API lịch sử; `getCause()` thường quen thuộc hơn trong phân tích chuỗi lỗi. Cần lưu cả **thông báo gốc, stack trace gốc và frame đầu tiên thuộc source của mình**.

Lưu ý constructor/overload của `ExceptionInInitializerError` có các trường hợp không gắn cause; đừng giả định `getCause()` luôn khác `null` nếu chính ứng dụng hoặc thư viện **tự tạo** một instance lỗi. Trong tình huống VM tự bọc throwable thích hợp, cause thường rất hữu ích.

### 5.3. Nếu `<clinit>` ném `Error` thì sao?

Quy tắc JVM phân biệt throwable là subtype `Error` với throwable không phải `Error`. Nếu code initialization ném một `AssertionError` hoặc một `Error` khác, JVM **không bắt buộc bọc lại thành `ExceptionInInitializerError`**; lỗi gốc có thể được ném trực tiếp. **Runtime class vẫn vào erroneous state** sau kết thúc bất thường.

Vì vậy định nghĩa “mọi lỗi static init đều là `ExceptionInInitializerError`” là **sai**. Phần lab sẽ kiểm chứng cả nhánh exception bị bọc và nhánh `Error` được giữ nguyên.

## 6. `NoClassDefFoundError` ở lần dùng sau: class đã lỗi, không phải luôn mất tệp

Khi một runtime class đã ở erroneous state, một yêu cầu initialization tiếp theo không chạy lại toàn bộ static initializer mà gây **`NoClassDefFoundError`**.

```text
Lần đầu active use
  → bắt đầu <clinit>
  → IllegalStateException
  → JVM bọc ExceptionInInitializerError
  → class bị đánh dấu erroneous

Lần thứ hai active use cùng runtime class
  → kiểm tra trạng thái
  → erroneous
  → NoClassDefFoundError
  → KHÔNG chạy lại <clinit>
```

Không nên đọc mỗi chữ “NoClassDefFound” rồi lập tức kết luận thiếu JAR/file. `NoClassDefFoundError` có thể xuất hiện bởi nhiều nguyên nhân khác nhau, trong đó có:

1. JVM cần định nghĩa một class nhưng không lấy được nó trong quá trình loading/linking.
2. Một runtime class đã **khởi tạo thất bại** trước đó.
3. Một lỗi linkage/initialization trong dependency khiến một class liên quan không thể được dùng như kỳ vọng.

Trong trường hợp class erroneous, thông báo thường có dạng liên quan **“Could not initialize class ...”**; thông báo chi tiết **không ổn định giữa JVM/version**. Tìm lỗi **đầu tiên** trong logs, nhất là `ExceptionInInitializerError` và cause của nó.

### 6.1. Vì sao bắt lỗi đầu tiên rồi retry không sửa được?

Một đoạn như:

```java
for (int i = 0; i < 3; i++) {
    try {
        useBrokenClass();
    } catch (LinkageError e) {
        // Ghi nhận lỗi, nhưng không "reset" class
    }
}
```

là **pseudocode dạng Java**: cần có method `useBrokenClass()` trong ngữ cảnh phù hợp mới biên dịch. Nếu lần đầu class đã erroneous, những lần lặp không trở lại `<clinit>`. Việc dùng `Thread.sleep(...)`, thử lại ngay, hoặc gọi `System.gc()` không làm JVM xóa trạng thái erroneous.

Cách sửa phải hướng tới **nguyên nhân ban đầu và vòng đời deployment/runtime class**.

## 7. Lab Java 17+ chạy được: quan sát hai kiểu thất bại

Tạo file duy nhất **`InitializerFailureDemo.java`**:

```java
public class InitializerFailureDemo {
    static class Broken {
        static int configuration = load();

        static int load() {
            System.out.println("Broken initializing");
            throw new IllegalStateException("bad configuration");
        }

        Broken() {
            System.out.println("Broken constructor");
        }
    }

    static class Fatal {
        static int flag = fail();

        static int fail() {
            System.out.println("Fatal initializing");
            throw new AssertionError("fatal problem");
        }

        Fatal() {
            System.out.println("Fatal constructor");
        }
    }

    static class Healthy {
        static int count = init();

        static int init() {
            System.out.println("Healthy initializing");
            return 12;
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("start");

        Class<?> mirror = Broken.class;
        System.out.println("literal: " + mirror.getSimpleName());
        Class.forName(mirror.getName(), false, mirror.getClassLoader());
        System.out.println("lookup without initialization");

        try {
            new Broken();
        } catch (ExceptionInInitializerError e) {
            System.out.println("broken first: "
                    + e.getClass().getSimpleName());
            System.out.println("broken cause: "
                    + e.getCause().getClass().getSimpleName());
        }

        try {
            new Broken();
        } catch (NoClassDefFoundError e) {
            System.out.println("broken second: "
                    + e.getClass().getSimpleName());
        }

        try {
            new Fatal();
        } catch (AssertionError e) {
            System.out.println("fatal first: "
                    + e.getClass().getSimpleName());
        }

        try {
            new Fatal();
        } catch (NoClassDefFoundError e) {
            System.out.println("fatal second: "
                    + e.getClass().getSimpleName());
        }

        System.out.println("healthy first: " + Healthy.count);
        System.out.println("healthy second: " + Healthy.count);
        System.out.println("end");
    }
}
```

Chạy với JDK 17 hoặc mới hơn trong thư mục chứa file:

```bash
javac -encoding UTF-8 InitializerFailureDemo.java
java InitializerFailureDemo
```

**Standard output chính xác:**

```text
start
literal: Broken
lookup without initialization
Broken initializing
broken first: ExceptionInInitializerError
broken cause: IllegalStateException
broken second: NoClassDefFoundError
Fatal initializing
fatal first: AssertionError
fatal second: NoClassDefFoundError
Healthy initializing
healthy first: 12
healthy second: 12
end
```

### 7.1. Vì sao output có thứ tự như vậy?

1. `Broken.class` tạo/lấy Class mirror mà **không bắt buộc initialize `Broken`**; vì vậy chưa có dòng `Broken initializing`.
2. `Class.forName(name, false, loader)` cũng không yêu cầu initialization; in `lookup without initialization` như thường.
3. `new Broken()` lần đầu yêu cầu class initialization, gọi `Broken.load()` từ code static. Method in `Broken initializing` rồi ném `IllegalStateException`.
4. Throwable ban đầu **không phải `Error`**, nên JVM bọc bằng `ExceptionInInitializerError`; cause được in là `IllegalStateException`. Constructor body chưa được thực thi, vì vậy **không có** `Broken constructor`.
5. `new Broken()` lần thứ hai gặp cùng runtime class **erroneous**, ném `NoClassDefFoundError` và **không in** `Broken initializing` lần nữa.
6. `new Fatal()` lần đầu đi qua static initialization và `Fatal.fail()` ném **`AssertionError`**. JVM chuyển tiếp `Error` này theo nhánh tương ứng, nên dòng đầu ghi `AssertionError` thay vì `ExceptionInInitializerError`.
7. `Fatal` vẫn erroneous. Lần thứ hai ném `NoClassDefFoundError`, và constructor body cũng chưa thực thi.
8. `Healthy.count` được dùng lần đầu khiến initialization thành công, in một lần `Healthy initializing`; lần đọc thứ hai không chạy lại initializer.

Chương trình cố ý bắt đúng loại `Error` cần quan sát và in tên lớp của lỗi thay vì `getMessage()`; điều này giữ stdout ổn định trước khác biệt về stack trace/message giữa các JVM. **Trong production, tránh bắt lỗi liên kết/initialization rồi coi hệ thống đã hồi phục.**

### 7.2. Tự xem ClassFile bằng `javap`

```bash
javap -c -p 'InitializerFailureDemo$Broken'
javap -c -p 'InitializerFailureDemo$Fatal'
javap -c -p 'InitializerFailureDemo$Healthy'
javap -c -p InitializerFailureDemo
```

Nháy đơn bảo vệ ký tự `$` của nested class trong Bash hoặc PowerShell; với Windows `cmd.exe` có thể dùng nháy kép.

Trong output lớp `Broken`, tìm phần **`static {}`** mà `javap` hiển thị cho `<clinit>`:

```text
invokestatic ... load:()I
putstatic    ... configuration:I
return
```

Đây là **mô tả mẫu instruction**, không phải listing gồm offset/constant-pool indexes cố định. Vì `load()` ném exception, `putstatic` và `return` theo luồng bình thường không đạt tới trong lần chạy lỗi. JVM đánh dấu class erroneous.

Trong method `main`, quan sát các instruction `new` và các nhánh catch trong exception table. **Không có opcode tên `retry_clinit`** mà `javac` tự thêm sau khi bắt lỗi.

## 8. Đối chiếu: constructor exception không làm class erroneous

Một class có thể initialize thành công nhưng **constructor body của instance** ném exception. Chẳng hạn:

```java
class ConstructorFails {
    static {
        System.out.println("Class initialized");
    }

    ConstructorFails() {
        throw new IllegalArgumentException("bad instance");
    }
}
```

Đây là **class minh họa**, không phải chương trình có `main`. Nếu caller bắt `IllegalArgumentException` khi thực hiện `new ConstructorFails()`, rồi sau đó gọi `new ConstructorFails()` lần nữa, class vẫn initialized thành công; constructor có thể lại ném exception. Không có quy tắc class-erroneous chỉ vì constructor của một instance thất bại.

Tương tự, một **static method bình thường**, được gọi **sau khi class initialized thành công**, có thể ném `IllegalStateException` mà không làm class bị đánh dấu erroneous. Class initialization được coi là một **giai đoạn riêng**, không phải mọi code chạy “trong một class”.

### Bảng đối chiếu ba tình huống

| Nơi xảy ra exception | Class initialization đã thành công? | Hệ quả điển hình |
| --- | --- | --- |
| Trong `<clinit>` hoặc chuỗi công việc initialization | **Chưa** | Throwable/error ban đầu theo quy tắc JVM, class có thể vào erroneous state |
| Trong constructor `<init>` sau class initialization | **Rồi** | Object creation thất bại; class vẫn usable, constructor sau vẫn có thể được thử |
| Trong static method thông thường sau initialization | **Rồi** | Method invocation thất bại; class không bị erroneous chỉ vì exception này |

**Cẩn trọng:** nếu static method được **gọi bởi `<clinit>`**, exception thoát khỏi method đó sẽ làm công việc class initialization thất bại. Cùng một method có thể không làm class erroneous khi được gọi ở thời điểm khác, nhưng khi nó là một mắt xích trong `<clinit>` chưa hoàn thành thì hậu quả khác.

## 9. Lỗi khi khởi tạo superclass hoặc dependency

Khi JVM khởi tạo một subclass, superclass liên quan phải được initialized theo thứ tự quy định. Nếu **superclass initialization** thất bại, subclass không thể tiếp tục initialization bình thường.

```text
Active use of Child
       │
       ▼
Initialize Parent
       │
       ▼
Parent <clinit> fails
       │
       ├── Parent becomes erroneous
       │
       ▼
Child initialization cannot proceed
       │
       └── Child also cannot be used normally
```

Trong trường hợp phụ thuộc kiểu này, error thấy ở lời gọi tạo **Child** có thể có nguyên nhân nằm trong static initializer của **Parent** hoặc interface được yêu cầu khởi tạo theo quy tắc JVM. Xem **cause chain** và các frame khởi tạo thực tế, không chỉ tên class được nêu ở dòng đầu của lệnh `new Child()`.

### Các static dependencies có thể kéo lỗi lan truyền

```java
class DatabaseConfig {
    static final String URL = loadUrl();

    static String loadUrl() {
        throw new IllegalStateException("missing URL");
    }
}

class Repository {
    static String connectionUrl = DatabaseConfig.URL;
}
```

Đây là hai class minh họa. Khi `Repository` initialization cần đọc `DatabaseConfig.URL`, JVM có thể phải initialize `DatabaseConfig`. Nếu lớp phụ thuộc lỗi, đường khởi tạo của `Repository` cũng không hoàn thành bình thường.

**Đừng dùng suy đoán rằng exception gốc luôn được bọc thêm một lớp `ExceptionInInitializerError` cho mỗi dependency.** JVM có luật cụ thể với `Error` và trạng thái runtime; hình dạng cause chain phải quan sát từ lỗi thực tế.

### Static initialization và class loader

Nếu ứng dụng có nhiều class loaders, lỗi trong định nghĩa `Repository` thuộc loader A không mặc nhiên khiến một class cùng binary name nhưng **được định nghĩa độc lập bởi loader B** trở thành erroneous. Dù cùng source bytes, đây là hai runtime classes khác nhau. Tuy nhiên tính độc lập này **không phải giải pháp hồi phục tùy tiện**: thực tế còn có resource leaks, class loader constraints và những phụ thuộc chung.

## 10. Concurrency: tại sao JVM không cho hai thread “sửa lỗi bằng cách thử song song”?

JVM cung cấp cơ chế **initialization lock** cho mỗi runtime class/interface:

1. Thread đầu tiên cần initialize class nhận trách nhiệm và bắt đầu quy trình.
2. Nếu thread khác cần initialization của cùng class khi việc này đang diễn ra, nó chờ trạng thái có kết quả theo quy tắc JVM.
3. Nếu initialization hoàn thành thành công, các thread tiếp tục sử dụng class đã initialized.
4. Nếu initialization thất bại, class chuyển erroneous; các yêu cầu sau **không được chạy lại `<clinit>` đồng thời hoặc tuần tự**.
5. Nếu chính thread đang initializing yêu cầu recursive initialization của class đó, JVM có quy tắc xử lý đặc biệt để không tự chặn chính nó.

Từ đó suy ra: **chạy thêm 10 thread khởi tạo cùng một class không tạo 10 lần retry hợp lệ**. Một vài thread có thể nhìn thấy các kiểu lỗi khác nhau vì thời điểm chúng chạm tới trạng thái class khác nhau; không dự đoán thứ tự console output trong ví dụ đa luồng nếu chưa đồng bộ cụ thể.

### Cảnh báo về circular initialization

Các vòng phụ thuộc static là vùng có rủi ro:

- **Cùng thread:** recursive initialization request của một class đang khởi tạo có thể được JVM cho qua theo quy tắc, khiến code đọc **default values** hoặc giá trị static mới được gán một phần; không nhất thiết ném exception.
- **Khác thread:** các class initialization lock và phụ thuộc chéo có thể tạo tình huống chờ lẫn nhau, thậm chí deadlock nếu thiết kế bất cẩn.
- **Trạng thái không hoàn chỉnh:** các static fields đã gán trước lỗi không biến class lỗi thành một API an toàn; tránh cố khai thác trạng thái trung gian.

Thiết kế static initialization tối giản và ít tác dụng phụ thường an toàn hơn so với init gọi mạng, khóa ngoài, tác vụ bất đồng bộ chờ nhau hoặc registry phụ thuộc vòng.

## 11. Static field có thể được đọc khi còn ở giá trị mặc định

Một vòng tham chiếu nội bộ **không nhất thiết gây lỗi initialization**; nó có thể tạo kết quả bất ngờ:

Tạo file **`PartialInitializationDemo.java`**:

```java
public class PartialInitializationDemo {
    static class Order {
        static int early = readLater();
        static int later = 7;

        static int readLater() {
            return later;
        }
    }

    public static void main(String[] args) {
        System.out.println("early: " + Order.early);
        System.out.println("later: " + Order.later);
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 PartialInitializationDemo.java
java PartialInitializationDemo
```

**Standard output:**

```text
early: 0
later: 7
```

Giải thích:

- **Preparation** cung cấp giá trị mặc định `0` cho static `int` fields theo mô hình JVM.
- Khi `Order.<clinit>` xử lý `early = readLater()`, trường `later` chưa được gán `7` từ initializer nằm **sau**.
- `readLater()` vì vậy đọc giá trị hiện tại `0`.
- Sau đó `later = 7` chạy, nhưng `early` không được tự tính lại.
- Class initialization hoàn thành thành công: **không có `ExceptionInInitializerError`**.

**Đừng hiểu mọi static field có thể đọc bất kỳ đâu trước khai báo:** Java source có những quy tắc về **illegal forward reference**; trong ví dụ, phép đọc thông qua method `readLater()` hợp lệ. Vòng khởi tạo không chỉ có hai kết quả “thành công đúng” hoặc “ném lỗi”: **thành công với state không như mong đợi** cũng đáng chú ý.

## 12. Chẩn đoán `ExceptionInInitializerError` và `NoClassDefFoundError`

Khi nhận báo lỗi, thực hiện tuần tự:

### Bước 1 — Tìm lần lỗi đầu tiên

Ưu tiên log đầu tiên chứa tên class trong chuỗi initialization, có thể là:

```text
ExceptionInInitializerError
Caused by: IllegalStateException: bad configuration
...
```

Đây là **trích cấu trúc minh họa**, không phải stack trace đầy đủ từ một JVM cụ thể. Nếu chỉ thấy `NoClassDefFoundError: Could not initialize class ...`, tìm về log **sớm hơn trong cùng tiến trình và class loader**.

### Bước 2 — Xem cause và static initializer nào chạy

Tìm method `<clinit>` hoặc method được static initializer gọi: `loadConfig`, `registerDriver`, `connect`, `parse`, `initializeCache`, v.v. Những method này là ví dụ chức năng có thể gây lỗi, không phải danh sách những method JVM tự gọi.

### Bước 3 — Phân biệt đường dẫn lỗi

| Triệu chứng | Câu hỏi chẩn đoán |
| --- | --- |
| `ClassNotFoundException` từ `Class.forName` | Tên, loader, module path, classpath đã đúng chưa? |
| `NoClassDefFoundError` khi tải dependency | Class file/dependency có thiếu, phiên bản binary có không tương thích không? |
| `NoClassDefFoundError` sau lỗi static init | Có `ExceptionInInitializerError` hoặc `Error` ban đầu trước đó không? |
| `ExceptionInInitializerError` | Throwable **gốc** trong cause là gì, xuất phát ở initializer nào? |
| `NoSuchMethodError` hoặc `IllegalAccessError` | Đây có phải lỗi linkage của dependency trong đường initialization? |
| `OutOfMemoryError` hoặc `StackOverflowError` | Lỗi tài nguyên/đệ quy xảy ra khi khởi tạo hay ở code sau? |

**Không phải mọi `NoClassDefFoundError` đều do initialization thất bại**. Dùng toàn bộ bối cảnh thay vì suy từ riêng tên exception.

### Bước 4 — Kiểm tra file/class thật sự đang chạy

```bash
java --version
javac --version
javap -c -p 'InitializerFailureDemo$Broken'
```

Với dự án lớn, xác minh phiên bản runtime của JAR/dependency, classpath/module path, class loader, environment variables và cấu hình được đọc trong static initializer. `javap` giúp xem có `static {}` tương ứng `<clinit>` và thứ tự bytecode nào; nó không tự chạy class initialization.

### Bước 5 — Sửa nguyên nhân và restart/khởi tạo lại theo thiết kế

Khi runtime class đã erroneous, chỉ sửa một biến cấu hình bên ngoài rồi tiếp tục truy cập cùng class **không khiến JVM tự chạy lại `<clinit>`**. Thường cần khởi động lại tiến trình/ứng dụng hoặc cơ chế reload có kiểm soát tạo một **runtime class definition mới** sau khi nguyên nhân đã sửa.

Không dùng `System.gc()`, `Thread.sleep()`, thay đổi quyền file giữa chừng hoặc lặp `Class.forName(name, true, sameLoader)` như cách “xóa erroneous state”.

## 13. Giảm rủi ro bằng thiết kế và xử lý lỗi hợp lý

### 13.1. Giữ static initialization tối giản

Ưu tiên static initialization của dữ liệu thuần túy, bất biến, tính được chắc chắn; hạn chế thực hiện tác vụ có thể thất bại vì môi trường:

```java
class SafeConstants {
    static final int MAX_RETRIES = 3;
    static final String PREFIX = "app";
}
```

Với những công việc có thể thất bại (đọc file cấu hình, truy cập mạng, tạo connection), cân nhắc **khởi tạo tường minh trong lifecycle ứng dụng**, trả lỗi rõ ràng cho caller, cho phép retry có kiểm soát và không gắn retry vào `<clinit>` của một class đã hỏng.

### 13.2. Tách tài nguyên khởi tạo động khỏi static initializer

Đoạn **minh họa thiết kế**, chưa là chương trình chạy độc lập:

```java
final class ConnectionManager {
    private ConnectionManager() {}

    static Connection open(String endpoint) {
        return connectWithTimeout(endpoint);
    }
}
```

Ở đây `Connection` và `connectWithTimeout` là **ký hiệu phụ thuộc ứng dụng** chưa được định nghĩa trong ví dụ, chỉ diễn tả việc chuyển thao tác có thể lỗi khỏi `<clinit>`. Trong ứng dụng thực tế, cần cung cấp kiểu/API cụ thể, close resource đúng cách và quyết định retry/backoff dựa trên yêu cầu nghiệp vụ.

### 13.3. Initialization-on-demand holder vẫn có thể thất bại

Mẫu holder:

```java
class ServiceHolder {
    static class Holder {
        static final Service INSTANCE = createService();
    }

    static Service get() {
        return Holder.INSTANCE;
    }
}
```

Đây là **pseudocode Java yêu cầu khai báo thêm `Service` và `createService()`**. Holder giúp trì hoãn initialization cho đến lúc active use, nhưng **không tự mang khả năng retry nếu `Holder.<clinit>` thất bại**. Sau lỗi, `Holder` cũng có thể erroneous. Do đó holder thích hợp cho singleton khởi tạo chắc chắn, không phải cơ chế phục hồi phép kết nối thiếu ổn định.

### 13.4. Không nuốt `Error` một cách mù quáng

`LinkageError`, `ExceptionInInitializerError`, `OutOfMemoryError` có ý nghĩa nghiêm trọng. Một số bài lab bắt chúng để kiểm tra hành vi, nhưng trong production, dùng `catch (Throwable)` chỉ nhằm “giữ ứng dụng sống” có thể che giấu trạng thái runtime không còn đáng tin.

Nếu cần ranh giới xử lý ở container/test runner, log đầy đủ, đánh dấu ứng dụng unhealthy và quyết định isolate/restart phù hợp thay vì tiếp tục gọi vào class erroneous.

### 13.5. Tránh khởi tạo tĩnh theo vòng phụ thuộc

Một thiết kế có:

```text
ServiceA.<clinit>
    ↳ ServiceB.staticMethod()
         ↳ ServiceC.INSTANCE
              ↳ ServiceA.otherStaticField
```

có thể dẫn tới đọc partial state, exception hoặc chờ chéo. Đây là **sơ đồ phụ thuộc**, không phải một thứ tự luôn gây lỗi. Tách dependency graph, dùng dependency injection lúc runtime, đặt initialization order rõ ràng và tránh khóa/chờ I/O kéo dài bên trong static initializer.

## 14. Kiểm tra nhanh các nhận định dễ nhầm

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| “Đọc `SomeClass.class` luôn thực thi `<clinit>`.” | **Sai** | Class literal không tự kích hoạt class initialization |
| “Static initializer lỗi lần đầu thì `NoClassDefFoundError` chắc chắn xuất hiện ngay.” | **Sai** | Lần đầu thường là `ExceptionInInitializerError` hoặc `Error` gốc; lần sau mới gặp erroneous state |
| “`ExceptionInInitializerError` là một `Exception`.” | **Sai** | Nó là `Error`, thuộc `LinkageError` |
| “Mọi Throwable từ `<clinit>` đều bị bọc một lớp `ExceptionInInitializerError`.” | **Sai** | Throwable thuộc `Error` có thể được giữ nguyên |
| “Lần sau chỉ việc `new` lại class là JVM chạy lại static block.” | **Sai** | Erroneous state không tự reset |
| “Mọi `NoClassDefFoundError` đều do thiếu JAR.” | **Sai** | Có thể do class initialization thất bại trước đó |
| “Constructor `<init>` ném exception sẽ làm class erroneous.” | **Sai**, nếu `<clinit>` đã thành công | Lỗi constructor của instance khác lỗi khởi tạo runtime class |
| “Dùng class loader mới có thể tạo một runtime type khác dù tên trùng.” | **Đúng** | Class identity gắn với defining loader |
| “Một thread thất bại trong `<clinit>` thì thread khác tự khởi tạo lại cùng class.” | **Sai** | JVM dùng initialization lock/state; class lỗi không được retry |
| “Static initialization có thể đọc các field còn ở default value.” | **Đúng** | Khi code dùng thứ tự init/đệ quy nhất định, partial state có thể được quan sát |

## 15. Bài tập thực hành và câu hỏi tự kiểm tra

**1. Lần dùng đầu ném `IllegalArgumentException` trong static initializer, caller thấy gì?**  
**Đáp án:** JVM thường bọc thành **`ExceptionInInitializerError`** vì `IllegalArgumentException` không phải `Error`. Runtime class trở thành erroneous khi initialization thất bại.

**2. Sau khi bắt lỗi trên, gọi `new` lần nữa với cùng runtime class sẽ khởi tạo lại?**  
**Đáp án:** Không. JVM nhận thấy erroneous state và ném **`NoClassDefFoundError`** theo quy tắc initialization.

**3. Nếu `<clinit>` ném `AssertionError` trực tiếp?**  
**Đáp án:** JVM không cần bọc Error đó thành `ExceptionInInitializerError`; lần đầu có thể thấy `AssertionError`, và những lần dùng sau của class erroneous gặp `NoClassDefFoundError`.

**4. Vì sao `new Demo[5]` không chạy static block của `Demo`?**  
**Đáp án:** Nó tạo **một array object của kiểu `Demo[]`** với năm reference mặc định `null`, không tạo năm Demo instances và không tự kích hoạt class initialization của component.

**5. `static final int MAX = 8;` có buộc static block chạy khi caller đọc MAX?**  
**Đáp án:** Không, khi đây là compile-time constant variable được inline theo quy tắc Java. Truy cập một non-constant static field là trường hợp khác.

**6. `Class.forName(name, false, loader)` và `Class.forName(name, true, loader)` có điểm khác gì liên quan tới initialization?**  
**Đáp án:** Overload với `false` không yêu cầu initialization; với `true` yêu cầu initialize class nếu phù hợp và chưa initialized. Nếu class erroneous, yêu cầu initialization với cùng runtime definition không thành công.

**7. `new Demo()` ném `IllegalStateException` từ constructor body sau khi static initializer thành công; Demo có erroneous không?**  
**Đáp án:** Không chỉ vì lỗi constructor. Runtime class có thể đã initialized; lần tạo object tiếp theo vẫn có thể gọi constructor đó.

**8. Có thể sửa cấu hình rồi gọi `Class.forName(name, true, sameLoader)` để thử lại `<clinit>` của class đã lỗi?**  
**Đáp án:** Không. JVM không reset erroneous state cho cùng runtime class chỉ bằng một lời gọi reflection tiếp theo.

**9. Vì sao lần đầu `new Child()` báo lỗi từ `Parent`?**  
**Đáp án:** JVM khởi tạo các superclass cần thiết trước subclass. Nếu `Parent` static initialization thất bại, Child không thể hoàn thành initialization bình thường.

**10. Nếu hai class loaders định nghĩa cùng binary name độc lập thì lỗi init bên loader A có khiến class loader B erroneous không?**  
**Đáp án:** Không mặc nhiên. Hai defining loaders tạo hai runtime classes khác nhau, với trạng thái initialization riêng; nhưng các tài nguyên/dependencies chung có thể vẫn gây lỗi khi loader B tự khởi tạo.

**11. Vì sao chỉ `NoClassDefFoundError` ở cuối log chưa đủ để kết luận nguyên nhân?**  
**Đáp án:** Nó có thể phát sinh do thiếu class khi loading/linking hoặc do runtime class đã erroneous. Cần lỗi **đầu tiên**, cause chain, tên class và loader.

**12. JVM có thể cho static initializer chạy cùng lúc ở hai thread trên cùng một runtime class để tăng tốc?**  
**Đáp án:** Không theo nghĩa thực thi hai initialization riêng của cùng runtime class. JVM phối hợp initialization bằng lock/state; thread khác phải tuân theo trạng thái của class đang initializing.

## 16. Tổng kết và tài liệu gốc

Hãy xem lỗi khởi tạo như **một chuyển trạng thái**, không chỉ là exception bị bắt:

```text
not initialized
       │ active use
       ▼
  initializing
       │
       ├── thành công ──► initialized ──► dùng tiếp
       │
       └── lỗi ────────► erroneous
                            │
                       active use sau
                            │
                            ▼
                    NoClassDefFoundError
```

- **`ExceptionInInitializerError`** thường là bề mặt của **lần khởi tạo thất bại ban đầu** do exception không thuộc `Error`.
- **`NoClassDefFoundError`** ở lần sau có thể là **hệ quả của class erroneous**, không phải bằng chứng thiếu file.
- **`Error` gốc** trong `<clinit>` có thể được JVM truyền tiếp thay vì bọc.
- **Constructor lỗi ≠ class initialization lỗi**.
- **Runtime class identity** gồm tên và defining class loader; cùng định nghĩa đã erroneous **không thể tự retry**.
- Cần xử lý **root cause ban đầu** và thiết kế static initialization an toàn, thay vì cố làm JVM gọi lại `<clinit>`.

Tài liệu chuẩn để kiểm chứng:

- *The Java Virtual Machine Specification*, chương **§5.5 Initialization**, đặc biệt phần thuật toán trạng thái initialization, lỗi và chuyển sang erroneous: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- *The Java Language Specification*, **§12.4 Initialization of Classes and Interfaces**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4
- Java API **`ExceptionInInitializerError`** và **`NoClassDefFoundError`** trong `java.lang`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html và https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html

**Kết luận thực hành:** khi chương trình gặp `NoClassDefFoundError: Could not initialize class ...`, hãy tìm **lần đầu class thất bại khởi tạo**. Cause của `ExceptionInInitializerError` hoặc `Error` gốc thường chỉ tới lỗi thật. Sau khi đã erroneous, retry trong cùng runtime class không chữa được nguyên nhân — phải sửa dữ liệu/phụ thuộc/thiết kế và khởi tạo một định nghĩa runtime phù hợp qua vòng đời ứng dụng hợp lệ.