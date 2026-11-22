# ExceptionInInitializerError và trạng thái khởi tạo thất bại trong Java

Khi Java Virtual Machine (JVM) **khởi tạo một lớp hoặc interface**, nó thực hiện các bộ khởi tạo `static` và khởi tạo các trường `static` theo quy tắc của Java. Nếu quá trình này kết thúc bất thường, lớp có thể chuyển sang trạng thái **khởi tạo thất bại (erroneous)**. Lần sử dụng đầu tiên có thể thấy `ExceptionInInitializerError`; những lần chủ động khởi tạo lại chính lớp đó thường nhận `NoClassDefFoundError`.

Đây là tình huống quan trọng khi dùng **class loader**, framework, thư viện cấu hình, singleton `static` hoặc code sinh lúc chạy. Nó giải thích vì sao sau khi sửa biến cấu hình trong bộ nhớ, lời gọi thứ hai vẫn báo lỗi dù đoạn khởi tạo không chạy lần nữa.

## 1. Khởi tạo lớp thực hiện công việc gì?

Quá trình chuẩn của một lớp thông thường:

```text
Loading               Tìm/đọc class file; tạo biểu diễn runtime của lớp
   ↓
Linking
  ├─ Verification      Xác minh class file/bytecode
  ├─ Preparation       Cấp phát và đặt giá trị mặc định cho trường static
  └─ Resolution        Giải quyết symbolic references (có thể diễn ra muộn)
   ↓
Initialization         Chạy logic khởi tạo lớp, nếu có, qua <clinit>
   ↓
Sử dụng bình thường   new, gọi phương thức, truy cập trường...
```

Phần **initialization** không đồng nghĩa với **loading** hoặc **preparation**. Trong preparation, các trường `static` đã có giá trị mặc định (`0`, `false`, `null`, ...); trong initialization, các giá trị theo biểu thức khởi tạo và các khối `static { ... }` được thực thi theo thứ tự xuất hiện trong nguồn (với các quy tắc biên dịch/JVM tương ứng).

Ví dụ:

```java
class Settings {
    static int retries = loadRetries();

    static {
        System.out.println("Settings initialized");
    }

    static int loadRetries() {
        return 3;
    }
}
```

Lớp `Settings` được tạo và liên kết trước khi code khởi tạo `static` bắt đầu. Khi khởi tạo, nó gọi `loadRetries()` để thiết lập `retries`, rồi in thông báo từ khối `static`. Nếu `loadRetries()` ném một exception không được xử lý, khối `static` phía sau **không được chạy**.

**Điểm học tập:** Việc tham chiếu đến `Settings.class` hay sử dụng `Class.forName("Settings", false, loader)` không tự nó buộc `Settings` thực hiện khối khởi tạo. Ngược lại, `Class.forName("Settings")` thông thường yêu cầu khởi tạo, nên có thể làm lộ lỗi này.

## 2. Khi nào JVM bắt đầu initialization?

Theo ngữ nghĩa Java, các ví dụ sử dụng chủ động điển hình là:

- `new MyClass()`: tạo instance của lớp, nên lớp cần được khởi tạo trước khi tạo instance hoàn tất.
- `MyClass.staticMethod()`: gọi phương thức `static` được khai báo bởi lớp.
- `MyClass.staticField = value`: gán trường `static` không phải hằng số inline ở lớp khai báo.
- `int x = MyClass.nonConstantStaticField`: đọc trường `static` không phải *constant variable*.
- `Class.forName("pkg.MyClass")`: phương thức này mặc định yêu cầu khởi tạo lớp được tìm thấy.

Đọc *compile-time constant* khác với đọc biến `static` thông thường:

```java
class Example {
    static final int LIMIT = 10;              // constant variable
    static final int DYNAMIC = computeLimit(); // không phải constant variable

    static int computeLimit() {
        System.out.println("initializing");
        return 20;
    }
}
```

Mã `System.out.println(Example.LIMIT)` có thể được biên dịch thành sử dụng trực tiếp giá trị `10`, **không kích hoạt khởi tạo** `Example`. Trong khi đó, đọc `Example.DYNAMIC` là một hành vi có thể kích hoạt initialization. Do vậy, “đọc một trường static” chưa đủ để kết luận khối `static` sẽ chạy.

Khi khởi tạo một lớp, JVM còn phải khởi tạo superclass chưa khởi tạo và những superinterface có default methods theo quy tắc hiện hành. Nếu một superclass thất bại, lớp con đang được khởi tạo cũng có thể bị đánh dấu erroneous mà không chạy bộ khởi tạo riêng của nó. Khởi tạo một interface thì không mặc nhiên khởi tạo tất cả superinterface của nó.

## 3. Phân biệt exception gốc, ExceptionInInitializerError và NoClassDefFoundError

Giả sử một lớp có:

```java
static final String CONFIG = loadRequiredConfig();
```

Nếu `loadRequiredConfig()` ném `IllegalStateException` hoặc `NullPointerException` và không có đoạn xử lý phù hợp, JVM đánh dấu lớp khởi tạo lỗi. Điều gì được ném ra cho người gọi phụ thuộc loại `Throwable` làm kết thúc bộ khởi tạo:

| Lần thử và nguyên nhân | Throwable nhìn thấy thường gặp | Ý nghĩa |
|---|---|---|
| Lần đầu: `<clinit>` kết thúc bởi `RuntimeException`, ví dụ `IllegalStateException` | `ExceptionInInitializerError` chứa exception gốc | JVM bọc lỗi không thuộc nhánh `Error` khi khởi tạo |
| Lần đầu: `<clinit>` trực tiếp kết thúc bởi `Error`, ví dụ `AssertionError` | Chính `Error` đó | JVM không tự bọc `Error` thành một `ExceptionInInitializerError` mới |
| Lần kế tiếp: cùng lớp đã ở trạng thái erroneous | `NoClassDefFoundError` | JVM từ chối cố khởi tạo lại lớp đã thất bại |
| Bất kỳ lúc nào: class file không thể tải hoặc dependency thiếu | Có thể là `ClassNotFoundException` hoặc `NoClassDefFoundError`, tùy API/ngữ cảnh | Cần phân biệt với erroneous state; không phải mọi `NoClassDefFoundError` đến từ `<clinit>` |

`ExceptionInInitializerError` kế thừa `LinkageError`, còn `LinkageError` kế thừa `Error`. `NoClassDefFoundError` cũng kế thừa `LinkageError`, nhưng **không** phải subclass của `ExceptionInInitializerError`.

Đừng mặc định rằng lần đầu **luôn** xuất hiện `ExceptionInInitializerError`: nếu code khởi tạo ném `Error`, JVM có thể chuyển tiếp chính lỗi đó. Ngoài ra, khi việc tạo đối tượng `ExceptionInInitializerError` thất bại vì thiếu bộ nhớ, JVM có thể dùng `OutOfMemoryError` theo đặc tả.

### Exception gốc nằm ở đâu?

Trong lần đầu thất bại do exception không phải `Error`, xem chuỗi nguyên nhân:

```text
java.lang.ExceptionInInitializerError
Caused by: java.lang.IllegalStateException: missing configuration
    at ... loadRequiredConfig(...)
    at ... <clinit>(...)
```

Đoạn trên là **mẫu stack trace minh họa**, không phải stdout cố định của chương trình. `Throwable.getCause()` trả về cause khi có. `ExceptionInInitializerError.getException()` là API cũ cũng có thể trả về exception ban đầu. Phân tích nguyên nhân phải bắt đầu từ lỗi trong `<clinit>`, không chỉ từ kiểu lỗi bọc phía ngoài.

Lần kế tiếp có thể thấy:

```text
java.lang.NoClassDefFoundError: Could not initialize class pkg.Settings
```

Thông báo và chuỗi cause có thể khác theo JDK/JVM. Đôi khi `NoClassDefFoundError` về sau có một cause liên quan đến lần thất bại ban đầu; **không dựa vào điều đó như điều kiện bắt buộc**. Luôn tìm lần initialization thất bại đầu tiên trong log.

## 4. Trạng thái khởi tạo của lớp là một state machine

JVMS `5.5` mô tả bốn trạng thái có ý nghĩa logic đối với class/interface đã được verify và prepare:

```text
VERIFIED + PREPARED, NOT INITIALIZED
                    |
                    | yêu cầu khởi tạo đầu tiên
                    v
BEING INITIALIZED BY THREAD T
         |                    |
         | thành công         | kết thúc bất thường
         v                    v
FULLY INITIALIZED         ERRONEOUS
         |                    |
         | dùng tiếp          | yêu cầu khởi tạo tiếp
         v                    v
     sử dụng được         NoClassDefFoundError
```

- **Not initialized:** chưa bắt đầu chạy logic khởi tạo.
- **Being initialized:** một thread đang làm việc đó. Nếu thread khác cùng cần khởi tạo lớp, nó phải chờ kết quả; sau khi được đánh thức, nó kiểm tra lại trạng thái.
- **Fully initialized:** khởi tạo thành công, các lần chủ động sử dụng tiếp không chạy lại `<clinit>`.
- **Erroneous:** quá trình khởi tạo đã thất bại. Yêu cầu khởi tạo tiếp theo với cùng runtime class ném `NoClassDefFoundError`, thay vì tự chạy lại initializer.

JVM có khóa khởi tạo riêng (`L_C`) cho từng class/interface về mặt ngữ nghĩa. Cách JVM biểu diễn khóa và tối ưu hóa việc lock là chi tiết triển khai, nhưng quy tắc đồng bộ và thứ tự quan sát phải được bảo toàn.

Nếu cùng **thread đang khởi tạo** lại yêu cầu khởi tạo chính lớp đó theo cách đệ quy, thuật toán của JVM cho phép yêu cầu lặp hoàn tất bình thường, không chạy một vòng `<clinit>` thứ hai. Tình huống này có thể làm code trong đường đệ quy quan sát một vài giá trị `static` đang ở mức mặc định/chưa hoàn tất; đó là một lý do tránh thiết kế static initialization quá phức tạp.

### Vì sao không tự thử lại?

Khởi tạo có thể đã tạo side effects trước khi gặp lỗi: in log, mở kết nối, chỉnh registry, đặt một số static fields, khởi chạy thread, v.v. JVM không có cơ chế “rollback rồi thử lại” chung cho các tác vụ đó. Đánh dấu erroneous và từ chối những lần khởi tạo lại tránh việc chạy lại một chuỗi tác vụ có trạng thái không chắc chắn. Trong một JVM đang chạy, trạng thái erroneous tồn tại đối với **chính runtime class đó**; không thể reset bằng cách gán lại một biến static thông thường.

## 5. Ví dụ Java 17+ có thể biên dịch và chạy

Ví dụ sau chứng minh ba điểm: `Class.forName(..., false, loader)` chưa chạy `<clinit>`; exception thường trong initializer dẫn tới `ExceptionInInitializerError`; khi class đã erroneous, truy cập sau nhận `NoClassDefFoundError`. Nó còn so sánh với việc initializer ném `AssertionError` trực tiếp.

Tạo tệp **`InitializerFailureDemo.java`**:

```java
public class InitializerFailureDemo {
    static class BadRuntime {
        static final int VALUE = initialize();

        private static int initialize() {
            System.out.println("BadRuntime: initializing");
            throw new IllegalStateException("missing configuration");
        }
    }

    static class BadError {
        static final int VALUE = initialize();

        private static int initialize() {
            System.out.println("BadError: initializing");
            throw new AssertionError("corrupt state");
        }
    }

    static void probe(String label, Runnable access) {
        try {
            access.run();
        } catch (LinkageError error) {
            System.out.println(label + ": "
                    + error.getClass().getSimpleName());

            if (error instanceof ExceptionInInitializerError wrapped) {
                System.out.println("cause: "
                        + wrapped.getCause().getClass().getSimpleName());
            }
        } catch (AssertionError error) {
            System.out.println(label + ": "
                    + error.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws Exception {
        Class.forName(
                "InitializerFailureDemo$BadRuntime",
                false,
                InitializerFailureDemo.class.getClassLoader()
        );
        System.out.println("load without initialization");

        probe("first Runtime", () -> System.out.println(BadRuntime.VALUE));
        probe("second Runtime", () -> System.out.println(BadRuntime.VALUE));

        probe("first Error", () -> System.out.println(BadError.VALUE));
        probe("second Error", () -> System.out.println(BadError.VALUE));
    }
}
```

Biên dịch/chạy từ thư mục chứa tệp:

```bash
javac --release 17 -d out InitializerFailureDemo.java
java -cp out InitializerFailureDemo
```

Đầu ra dự kiến với JDK 17+ tuân theo quy tắc trên:

```text
load without initialization
BadRuntime: initializing
first Runtime: ExceptionInInitializerError
cause: IllegalStateException
second Runtime: NoClassDefFoundError
BadError: initializing
first Error: AssertionError
second Error: NoClassDefFoundError
```

Giải thích theo thứ tự:

1. `Class.forName(..., false, ...)` tìm/chuẩn bị lớp `BadRuntime` nhưng không yêu cầu chạy initializer. Vì vậy câu đầu tiên in ra từ `main`.
2. `BadRuntime.VALUE` không phải *compile-time constant*, vì giá trị được trả từ một method. Lần đọc đầu kích hoạt `BadRuntime` initialization.
3. `initialize()` in một dòng rồi ném `IllegalStateException`. JVM bọc throwable này thành `ExceptionInInitializerError` và đánh dấu `BadRuntime` erroneous.
4. Lần đọc `BadRuntime.VALUE` kế tiếp không gọi `initialize()` lần nữa; JVM ném `NoClassDefFoundError`.
5. `BadError.initialize()` ném `AssertionError` (một subclass của `Error`), vì vậy lần đầu nhận chính `AssertionError`. Sau đó `BadError` cũng erroneous và lần tiếp theo nhận `NoClassDefFoundError`.

Hai khối `catch` trong `probe` **chỉ nhằm quan sát lỗi trong ví dụ**. Trong ứng dụng thật, đừng bắt chung lỗi khởi tạo rồi bỏ qua như thể component đã sẵn sàng. Nếu không có phương án fallback hợp lệ, để lỗi lan lên và dừng startup thường an toàn hơn việc tiếp tục với trạng thái thiếu nhất quán.

**Chi tiết dễ bỏ sót:** `static final int VALUE = initialize()` không phải constant variable. Nếu viết `static final int VALUE = 42` thì compiler có thể inline `42`, khiến ví dụ không kích hoạt initialization và dẫn tới kết luận sai.

## 6. Tại sao đôi khi chỉ thấy NoClassDefFoundError?

Những trường hợp thường gặp trong log:

**Tình huống A: class thật sự thiếu.**

```text
java.lang.NoClassDefFoundError: com/example/OptionalDependency
Caused by: java.lang.ClassNotFoundException: com.example.OptionalDependency
```

Một tham chiếu đến lớp phụ thuộc không được loader tìm thấy. Điều này khác với class có mặt nhưng đã từng thất bại trong `<clinit>`.

**Tình huống B: class có mặt nhưng initialization đã thất bại.**

```text
java.lang.ExceptionInInitializerError
Caused by: java.lang.IllegalArgumentException: bad setup
...
java.lang.NoClassDefFoundError: Could not initialize class com.example.ConfigHolder
```

Đoạn trên ghép các **mẫu log minh họa** từ những lượt gọi khác nhau, không phải một stack trace duy nhất. Nếu hệ thống chỉ lưu lượt gọi sau, người vận hành có thể thấy `NoClassDefFoundError` mà không còn log về exception ban đầu.

**Cách xử lý:** đối chiếu mốc thời gian từ khi JVM/class loader khởi động, tìm **lỗi đầu tiên** liên quan đến class name; kiểm tra exception cause, dòng trong `<clinit>` và trạng thái các dependency. Nếu hệ thống đa luồng, thread thứ hai có thể chờ thread thứ nhất khởi tạo rồi chỉ nhận thông tin erroneous.

Một `NoClassDefFoundError` tự nó **không đủ** để kết luận đường dẫn classpath sai hay initializer thất bại. Cần phân biệt theo thông điệp, cause và log đầy đủ.

## 7. Phạm vi “thất bại một lần” gắn với ClassLoader

JVM nhận diện runtime class bằng cặp:

```text
(binary name, defining class loader)
```

Vì vậy, hai lớp cùng tên nhị phân nhưng được **hai defining class loaders khác nhau** định nghĩa là hai runtime classes khác nhau, có initialization state riêng. Nếu loader A đã định nghĩa `pkg.Settings` và lớp này erroneous, **không có API Java thông thường để gọi lại `<clinit>` trên cùng lớp đó**.

Giải pháp thực tế tùy môi trường:

- **Ứng dụng Java thông thường:** sửa lỗi cấu hình, tài nguyên hoặc bytecode rồi khởi động lại tiến trình JVM để lớp được định nghĩa và khởi tạo trong runtime mới.
- **Plugin/container hỗ trợ reload:** tạo một defining class loader mới, nạp phiên bản lớp và dependency tương thích trong namespace mới, sau đó thay phần hệ thống sử dụng nó. Phải quản lý tham chiếu cũ, thread, tài nguyên và vòng đời loader cẩn thận.
- **Unit test:** tách logic tải cấu hình khỏi initializer `static` nếu cần dễ kiểm thử và thử lại; một test khác trong cùng JVM không mặc nhiên “làm mới” static state của lớp đã erroneous.

Chỉ tạo `new ClassLoader(parent)` **không đủ** nếu loader đó tiếp tục parent-first delegation để trả về chính lớp cũ từ parent. Điều quyết định là **defining loader của lớp được dùng thực tế**; load lại tên qua một child loader mà vẫn delegate lên lớp lỗi không khôi phục được trạng thái.

Cũng không nên dựa vào reflection để viết trường static hoặc cố gọi thủ công `<clinit>` nhằm “reset” một lớp: JVM quản lý trạng thái này theo quy tắc riêng.

## 8. Thực hành thiết kế tránh lỗi khởi tạo

Một initializer ngắn, ít side effects thường dễ duy trì hơn initializer mở kết nối mạng, tải file phức tạp hoặc tra cứu trạng thái phụ thuộc môi trường.

### 8.1. Tránh I/O và cấu hình có thể thất bại trong static initializer

Thiết kế dễ phát sinh lỗi:

```java
final class RemoteConfig {
    static final String TOKEN = readFromRemoteService();
    // Khi readFromRemoteService() thất bại, RemoteConfig có thể erroneous.
}
```

Đây chỉ là **đoạn minh họa**, chưa có định nghĩa `readFromRemoteService()`. Vấn đề không nằm ở `static final` tự thân, mà ở việc tải dữ liệu có thể thất bại đã được đặt vào initialization không có cơ chế retry cho cùng class.

Một cách thiết kế khác cho service cần retry:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ConfigService {
    public String readToken(Path path) throws IOException {
        return Files.readString(path).trim();
    }
}
```

Tạo tệp `ConfigService.java`, biên dịch `javac ConfigService.java`. Đây là class biên dịch được nhưng **không có `main`**, nên chỉ là phần mô phỏng component. Người gọi có thể quyết định retry, fallback hoặc dừng startup khi `readToken` báo `IOException`; thất bại của lời gọi method **không tự làm lớp `ConfigService` erroneous**.

Lưu ý: ví dụ trên chỉ minh họa việc **dời phép đọc có thể lỗi ra khỏi khởi tạo lớp**. Trong hệ thống thật vẫn cần xác thực cấu hình, bảo mật token và xử lý tài nguyên phù hợp.

### 8.2. Nếu buộc cần dữ liệu lúc initialization

Dữ liệu bất biến, tự đủ và tính toán xác định thường thích hợp hơn. Khi bắt buộc kiểm tra cấu hình trong initializer:

- Đưa thông điệp lỗi rõ ràng vào exception gốc (`IllegalStateException("missing X")`) để log dễ tìm nguyên nhân.
- Không bắt `Throwable` rồi âm thầm trả về giá trị giả, vì có thể khiến class nhìn như đã khởi tạo thành công trong trạng thái sai.
- Không chạy tác vụ có thể gây side effects lớn mà không dự tính hành vi thất bại.
- Xác định failure là **fail-fast** hay có thể **retry**; nếu cần retry, nên đặt thao tác vào API/service với vòng đời riêng, thay vì dựa vào việc JVM chạy lại `<clinit>`.

### 8.3. Không lạm dụng catch đối với Error

Có thể xem root cause với `catch (ExceptionInInitializerError error)` tại điểm startup/logging thích hợp, sau đó phát tán lại hoặc chấm dứt thao tác. Tuy nhiên, `ExceptionInInitializerError` thuộc nhóm `Error` và không phải tình huống exception nghiệp vụ bình thường.

```java
try {
    Component.start();
} catch (ExceptionInInitializerError error) {
    log.error("Cannot initialize component", error);
    throw error;
}
```

Đây là **đoạn minh họa** cần có `Component` và `log` do ứng dụng cung cấp. Nó không phải chương trình Java độc lập, và không thay thế chính sách lifecycle/recovery của ứng dụng.

## 9. Đồng thời và tác động sang các lớp khác

**Nhiều thread:** Nếu thread A bắt đầu khởi tạo `Config`, thread B cần khởi tạo `Config` sẽ chờ kết quả. Nếu A thất bại và `Config` bị đánh dấu erroneous, B sau khi tiếp tục sẽ nhận `NoClassDefFoundError`. B không trở thành “thread thứ hai thử chạy lại static block”.

**Phụ thuộc superclass:** Khi lớp con cần khởi tạo và initializer của superclass thất bại, quá trình khởi tạo lớp con cũng thất bại, lớp con có thể erroneous. Lần đầu có thể thấy throwable bắt nguồn từ superclass; các lần sau dùng lớp con có thể nhận `NoClassDefFoundError` cho lớp con. Phân tích stack trace phải đi về lớp khởi tạo gốc.

**Side effects không tự quay lui:** Giả sử initializer A đã ghi một dòng log, thêm item vào registry hoặc thay đổi tệp, rồi bước kế tiếp thất bại. JVM đánh dấu A erroneous nhưng không tự xóa tác dụng bên ngoài của các bước đã chạy. Đây là một lý do ưu tiên initialization nhỏ và thuần túy.

**Vòng phụ thuộc static initialization:** Nếu A đang khởi tạo mà gọi B, B lại đọc A, cùng thread có thể quay lại A khi A chưa hoàn tất. Khi đó các trường của A chưa được gán có thể vẫn là giá trị mặc định, dẫn tới lỗi logic hoặc ngoại lệ khác. Không phải mọi vòng phụ thuộc đều bị verifier cấm; thiết kế thứ tự khởi tạo cần tránh trạng thái trung gian.

## 10. Checklist chẩn đoán ExceptionInInitializerError

1. **Tìm lần ném đầu tiên**, thường là `ExceptionInInitializerError`, `AssertionError` hoặc một `Error` khác phát sinh trong initialization; đừng chỉ nhìn `NoClassDefFoundError` ở những request sau.
2. **Tìm cause gốc** và vị trí `<clinit>` / phương thức được static initializer gọi. Ví dụ `IllegalStateException` do thiếu cấu hình, `NullPointerException` do phụ thuộc chưa sẵn sàng, `IOException` được bọc thành runtime exception.
3. **Xác nhận trigger thực sự**, ví dụ `new`, `invokestatic`, đọc non-constant static field hoặc `Class.forName(name)`; đọc constant có thể không khởi tạo lớp.
4. **Kiểm tra class loader và class identity**, đặc biệt với ứng dụng plugin, app server, test harness, agent hoặc nhiều phiên bản thư viện.
5. **Kiểm tra lớp cha/interface có default method** khi throwable của một lớp xuất hiện trong lúc lớp khác đang khởi tạo.
6. **Kiểm tra đồng thời**, thread nào chạy `<clinit>` trước, thread nào chỉ chờ rồi gặp erroneous state.
7. **Sửa nguyên nhân, khởi động lại hoặc tạo runtime class mới có kiểm soát**. Đừng mong một lần truy cập lại cùng class đã erroneous sẽ sửa trạng thái.
8. **Đưa retry vào tầng ứng dụng** nếu đó là yêu cầu nghiệp vụ. Đừng dùng static initialization làm vòng retry tự động.

## 11. Câu hỏi tự kiểm tra

**1. Tại sao lần đầu lỗi khác lần sau?** Lần đầu JVM đang thực hiện initializer, có thể phải bọc exception gốc vào `ExceptionInInitializerError`. Sau đó runtime class đã erroneous; yêu cầu khởi tạo tiếp theo bị từ chối bằng `NoClassDefFoundError`.

**2. `ExceptionInInitializerError` có phải một `Exception` thông thường?** Không. Nó là `Error` thông qua `LinkageError` và thường biểu thị lỗi nghiêm trọng khi initialization.

**3. Nếu `static` initializer ném `AssertionError`, JVM có luôn bọc nó bằng `ExceptionInInitializerError` không?** Không. `AssertionError` là `Error`, nên lần thất bại đầu có thể trực tiếp ném `AssertionError`.

**4. Gọi lại `new Config()` có chạy lại initializer đã thất bại không?** Không, nếu vẫn là cùng runtime class erroneous. JVM từ chối, thường bằng `NoClassDefFoundError`.

**5. Đổi giá trị biến môi trường trong JVM rồi gọi lại có đủ không?** Không. Phải sửa nguyên nhân và sử dụng vòng đời/runtime class mới, hoặc thiết kế lại để phần có thể thất bại nằm ngoài `<clinit>` và hỗ trợ retry.

**6. Có thể dùng `Class.forName(name, false, loader)` để tránh initialization ngay tại bước tra cứu không?** Có. Nhưng khi thực sự sử dụng lớp theo cách đòi initialization, lỗi vẫn có thể xuất hiện.

**7. Một `NoClassDefFoundError` có chắc nghĩa là class không nằm trong JAR?** Không. Nó cũng có thể xuất hiện vì một lớp đã bị đánh dấu erroneous sau lần initialization trước.

## 12. Tài liệu chuẩn để đối chiếu

- *Java Language Specification*, 12.4, “Initialization of Classes and Interfaces”: https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4
- *Java Virtual Machine Specification*, 5.5, “Initialization”: https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.5
- Java API, ExceptionInInitializerError: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ExceptionInInitializerError.html
- Java API, NoClassDefFoundError: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html

**Ghi nhớ:** `ExceptionInInitializerError` chỉ là một cách JVM báo rằng initializer thất bại lần đầu; nguyên nhân gốc nằm sâu hơn trong `<clinit>`. Khi class chuyển sang trạng thái **erroneous**, những lần cần khởi tạo lại *cùng runtime class* sẽ bị từ chối bằng `NoClassDefFoundError`. Đọc log theo thứ tự thời gian, hiểu danh tính class loader và đưa logic cần retry ra khỏi `static` initialization.
