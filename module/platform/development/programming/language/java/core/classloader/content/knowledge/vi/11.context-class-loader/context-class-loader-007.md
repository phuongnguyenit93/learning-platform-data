# Đổi context class loader trong phạm vi hẹp và khôi phục bằng finally

## 1. Vì sao cần đổi Thread Context ClassLoader?

Trong Java, mỗi thread có thể giữ một tham chiếu tới **Thread Context ClassLoader (TCCL)**. Ta lấy nó bằng:

~~~java
ClassLoader current =
        Thread.currentThread().getContextClassLoader();
~~~

Đây là **loader gắn với ngữ cảnh của thread**, không nhất thiết là loader định nghĩa class đang chạy. Một thư viện có thể được nạp bởi loader của host nhưng vẫn cần tìm provider, class hoặc resource thuộc plugin. Thay vì buộc thư viện biết một loader plugin cụ thể, framework có thể đặt **TCCL của thread** thành loader plugin trong thời gian gọi thư viện.

Ví dụ thực tế: overload một tham số của `ServiceLoader.load(MyService.class)` sử dụng **TCCL của thread hiện tại** để tìm provider trong ngữ cảnh caller. Một số framework và API khám phá plugin/resource khác cũng đọc TCCL để chọn loader phù hợp.

Tuy nhiên, TCCL là **trạng thái có thể thay đổi của thread**, vì vậy việc đổi nó phải có phạm vi và cơ chế phục hồi rõ ràng:

> **Quy tắc cốt lõi:** Lưu loader cũ, đặt loader tạm thời, thực hiện công việc trong `try` và **luôn khôi phục loader cũ trong `finally`**.

Nếu quên khôi phục, một thao tác sau trên **cùng thread** có thể dùng nhầm loader plugin, tìm nhầm resource/provider hoặc giữ loader cũ còn sống sau khi plugin đã bị gỡ.

## 2. Phân biệt ba loại “ClassLoader hiện tại”

Ba cách lấy loader sau giải quyết các câu hỏi khác nhau:

~~~java
ClassLoader defining =
        MyClass.class.getClassLoader();

ClassLoader system =
        ClassLoader.getSystemClassLoader();

ClassLoader context =
        Thread.currentThread().getContextClassLoader();
~~~

| Tham chiếu | Câu hỏi nó trả lời | Có đổi khi `setContextClassLoader` không? |
|---|---|---|
| `MyClass.class.getClassLoader()` | Ai **định nghĩa runtime class** `MyClass`? | **Không** |
| `ClassLoader.getSystemClassLoader()` | System/application loader được JVM chọn là gì? | **Không** |
| `Thread.currentThread().getContextClassLoader()` | Loader nào đang được thread dùng làm ngữ cảnh tra cứu? | **Có**, với thread đó |

Việc gọi `thread.setContextClassLoader(pluginLoader)` **không di chuyển class** từ parent sang child, không thay đổi loader định nghĩa các class đã nạp và không sửa quan hệ ủy quyền parent–child. Nó chỉ thay giá trị của **một trường ngữ cảnh trên đối tượng `Thread`**.

Nếu một API tự gọi `SomeClass.class.getClassLoader()` thay vì lấy TCCL, việc đổi TCCL có thể **không ảnh hưởng** tới API đó. TCCL là một **quy ước tra cứu được một số API/framework sử dụng**, không phải công tắc thay toàn bộ class loading của JVM.

## 3. Mẫu an toàn tối thiểu: `try/finally`

Mẫu nên thuộc nằm lòng:

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    // Gọi thư viện hoặc framework cần tìm tài nguyên từ pluginLoader.
} finally {
    thread.setContextClassLoader(previous);
}
~~~

Đây là **đoạn mã minh họa**: `pluginLoader` phải được tạo hoặc truyền từ bên ngoài. Những điểm không được bỏ qua:

1. **Lấy đúng thread hiện tại.** Một lệnh gọi `setContextClassLoader` thay TCCL của thread mà nó được gọi trên; trong ví dụ là `Thread.currentThread()`.
2. **Giữ nguyên tham chiếu loader cũ**, kể cả khi nó là `null`. Đừng suy luận “loader cũ chắc chắn là system loader”.
3. **Giới hạn vùng `try`** vừa đủ cho lời gọi cần plugin loader. Không giữ TCCL của plugin cho toàn bộ request nếu chỉ một bước discovery cần dùng.
4. **Dùng `finally` chứ không đặt restore sau `try`**. `finally` vẫn được chạy trên luồng điều khiển thông thường khi code trong `try` thành công, return hoặc ném exception.
5. **Không nuốt exception chính.** `finally` dùng để khôi phục trạng thái; exception từ thao tác chính thường cần truyền lên caller hoặc được xử lý theo chính sách rõ ràng.

Mã sau **không an toàn**:

~~~java
// Mã minh họa sai.
Thread.currentThread().setContextClassLoader(pluginLoader);
service.perform();
Thread.currentThread().setContextClassLoader(previous);
~~~

Nếu `service.perform()` ném exception, dòng restore cuối **không chạy**. Trên thread pool, một task sau có thể vô tình nhìn thấy loader plugin của task trước.

Lưu ý kỹ thuật: `setContextClassLoader` có thể bị từ chối theo cơ chế kiểm soát quyền trong các runtime có cấu hình kiểm soát phù hợp, chẳng hạn `SecurityManager` của các JDK hỗ trợ tính năng này. `finally` bảo đảm **thử khôi phục**, không bảo đảm một lệnh khôi phục bị chặn luôn thành công. Đừng âm thầm bỏ qua lỗi restore.

## 4. Vì sao mẫu này quan trọng với nested calls và exception?

Giả sử một thao tác A cần loader A, nhưng trong khi chạy A lại gọi thao tác B cần loader B.

~~~text
Ban đầu:               TCCL = system
│
├─ Vào phạm vi A:       TCCL = loader A
│  │
│  ├─ Vào phạm vi B:    TCCL = loader B
│  └─ finally của B:    TCCL = loader A
│
└─ finally của A:       TCCL = system
~~~

Mỗi phạm vi lưu **loader mà nó thấy khi bắt đầu** và khôi phục **chính giá trị đó**. Vì thế nested scopes hoạt động theo cấu trúc *stack* tự nhiên.

Nếu B ném exception, `finally` của B vẫn khôi phục A; sau đó nếu exception tiếp tục đi ra phạm vi A, `finally` của A khôi phục system. Không cần giả định loader cũ luôn là system loader.

Nếu đổi TCCL nhiều lần trong cùng một vùng `try` mà không thiết kế rõ các mức lồng nhau, dễ khôi phục sai loader. Tốt nhất mỗi lần thay tạm thời nên được bọc trong **một vùng `try/finally` độc lập**.

## 5. Ví dụ Java 17+ hoàn chỉnh: hai plugin resource và khôi phục TCCL

Ví dụ sau minh họa bằng **resource lookup qua TCCL**. Đây là cách thấy rõ thay đổi ngữ cảnh mà không cần phụ thuộc framework.

Ta tạo hai JAR chỉ chứa cùng tên resource:

~~~text
tccl-demo/
├── src/
│   └── ContextScopeDemo.java
└── resources/
    ├── alpha/
    │   └── demo/context/marker.txt
    └── beta/
        └── demo/context/marker.txt
~~~

Nội dung chính xác của hai file UTF-8:

- `resources/alpha/demo/context/marker.txt`: `ALPHA`
- `resources/beta/demo/context/marker.txt`: `BETA`

Các resource này **không** được thêm vào application classpath. Host chỉ chứa class `ContextScopeDemo`. Chúng được nạp qua hai `URLClassLoader` khác nhau.

### 5.1. File nguồn Java độc lập

Tạo **`src/ContextScopeDemo.java`**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.Callable;

public final class ContextScopeDemo {
    private static final String RESOURCE = "demo/context/marker.txt";

    private ContextScopeDemo() {
    }

    private static String readMarker() throws IOException {
        ClassLoader loader =
                Thread.currentThread().getContextClassLoader();

        if (loader == null) {
            return "(no context loader)";
        }

        try (InputStream in = loader.getResourceAsStream(RESOURCE)) {
            if (in == null) {
                return "(missing)";
            }
            return new String(
                    in.readAllBytes(),
                    StandardCharsets.UTF_8).strip();
        }
    }

    private static <T> T withContext(
            ClassLoader temporary, Callable<T> action) throws Exception {
        Thread thread = Thread.currentThread();
        ClassLoader previous = thread.getContextClassLoader();

        try {
            thread.setContextClassLoader(temporary);
            return action.call();
        } finally {
            thread.setContextClassLoader(previous);
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: ContextScopeDemo <alpha.jar> <beta.jar>");
        }

        Path alphaJar = Path.of(args[0]).toAbsolutePath().normalize();
        Path betaJar = Path.of(args[1]).toAbsolutePath().normalize();

        if (!Files.isRegularFile(alphaJar)
                || !Files.isRegularFile(betaJar)) {
            throw new IllegalArgumentException("Both JARs must exist");
        }

        URL alphaUrl = alphaJar.toUri().toURL();
        URL betaUrl = betaJar.toUri().toURL();

        Thread thread = Thread.currentThread();
        ClassLoader original = thread.getContextClassLoader();

        try (URLClassLoader alpha =
                     new URLClassLoader(new URL[] {alphaUrl}, original);
             URLClassLoader beta =
                     new URLClassLoader(new URL[] {betaUrl}, original)) {

            System.out.println("Before: " + readMarker());

            withContext(alpha, () -> {
                System.out.println("Inside alpha: " + readMarker());

                String nestedValue =
                        withContext(beta, ContextScopeDemo::readMarker);
                System.out.println("Inside beta: " + nestedValue);

                System.out.println("Back in alpha: " + readMarker());
                return null;
            });

            System.out.println("After alpha: " + readMarker());

            try {
                withContext(beta, () -> {
                    throw new IllegalStateException("boom");
                });
            } catch (IllegalStateException expected) {
                System.out.println("Caught: " + expected.getMessage());
            }

            System.out.println("After exception: " + readMarker());
            System.out.println("Original restored: "
                    + (thread.getContextClassLoader() == original));
        }
    }
}
~~~

**Mẫu trọng tâm** là phương thức `withContext`. Nó cho phép truyền một đoạn công việc dưới dạng `Callable<T>`, lưu loader cũ, đặt loader mới, chạy `action.call()`, rồi khôi phục trong `finally`.

Cách này đơn giản hóa nested calls vì mỗi lần gọi `withContext` quản lý chính phạm vi của mình. Đây không phải cách duy nhất để xây một context scope; với thao tác đơn lẻ, đoạn `try/finally` trực tiếp ở phần 3 thường dễ đọc hơn.

### 5.2. Biên dịch, đóng JAR và chạy

Yêu cầu **JDK 17 trở lên**. Đứng tại thư mục `tccl-demo/` có cấu trúc đã mô tả.

**Bash (Linux/macOS hoặc Git Bash):**

~~~bash
mkdir -p build/classes dist

javac -encoding UTF-8 \
  -d build/classes src/ContextScopeDemo.java

jar --create --file dist/alpha.jar -C resources/alpha .
jar --create --file dist/beta.jar -C resources/beta .

java -cp build/classes \
  ContextScopeDemo dist/alpha.jar dist/beta.jar
~~~

**Windows PowerShell:**

~~~powershell
New-Item -ItemType Directory -Force build/classes,dist | Out-Null

javac -encoding UTF-8 -d build/classes src/ContextScopeDemo.java

jar --create --file dist/alpha.jar -C resources/alpha .
jar --create --file dist/beta.jar -C resources/beta .

java -cp build/classes ContextScopeDemo dist/alpha.jar dist/beta.jar
~~~

Lệnh `jar` đóng resource vào JAR ở đường dẫn `demo/context/marker.txt`. Có thể xác minh:

~~~bash
jar --list --file dist/alpha.jar
jar --list --file dist/beta.jar
~~~

Cả hai JAR đều phải có `demo/context/marker.txt`. Chương trình chạy trên classpath `build/classes` và **không** thêm hai JAR vào `-cp`: như vậy loader mặc định của host không tìm thấy resource plugin, còn TCCL `alpha` hoặc `beta` có thể tìm thấy.

### 5.3. Stdout trong môi trường Java 17 tiêu chuẩn

Với Java launcher thông thường (TCCL ban đầu của luồng `main` là application/system loader), không có resource trùng tên trong application/JDK classpath:

~~~text
Before: (missing)
Inside alpha: ALPHA
Inside beta: BETA
Back in alpha: ALPHA
After alpha: (missing)
Caught: boom
After exception: (missing)
Original restored: true
~~~

**Giải thích:**

1. **Before:** System/context loader ban đầu không nhìn thấy `marker.txt` chỉ nằm trong plugin JAR → `(missing)`.
2. **Inside alpha:** `withContext(alpha, ...)` tạm đặt TCCL thành loader alpha; đọc resource từ `alpha.jar` → `ALPHA`.
3. **Inside beta:** Nested `withContext(beta, ...)` đặt loader beta → `BETA`. Khi lời gọi lồng nhau kết thúc, `finally` của beta khôi phục TCCL về **alpha**, không phải system.
4. **Back in alpha:** Resource lại trả `ALPHA`, chứng minh nested scope đã khôi phục chính xác.
5. **After alpha:** `finally` của alpha khôi phục TCCL về original → không còn thấy plugin resource từ ngữ cảnh host.
6. **Caught:** Một action dùng beta cố ý ném `IllegalStateException("boom")`. `finally` vẫn khôi phục TCCL, sau đó caller bắt exception.
7. **After exception** và **Original restored:** TCCL không bị rò khỏi vùng tạm và chính là **cùng object loader ban đầu**; phép so sánh dùng `==`, không dựa trên tên hoặc `toString()`.

Kết quả sẽ khác nếu môi trường chạy chủ động thiết lập TCCL ban đầu đặc biệt hoặc thêm các resource tương tự vào parent classpath. Chương trình vẫn thể hiện nguyên tắc khôi phục, nhưng các phép lookup có thể chịu ảnh hưởng của parent-first resource delegation.

## 6. Vì sao phải lưu loader cũ thay vì ép về system?

Cách sai thường thấy:

~~~java
// Mã minh họa sai về ngữ nghĩa scope.
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    usePlugin();
} finally {
    Thread.currentThread().setContextClassLoader(
            ClassLoader.getSystemClassLoader());
}
~~~

Nếu caller ban đầu chạy trong application server, loader của request, loader của plugin A hoặc một custom context loader, đoạn này **thay ngữ cảnh ban đầu bằng system loader**, không phải khôi phục. Nó có thể làm hỏng lời gọi bên ngoài trong nested scope.

Cách đúng:

~~~java
// Mã minh họa; pluginLoader/usePlugin do ứng dụng cung cấp.
Thread current = Thread.currentThread();
ClassLoader old = current.getContextClassLoader();

try {
    current.setContextClassLoader(pluginLoader);
    usePlugin();
} finally {
    current.setContextClassLoader(old);
}
~~~

TCCL cũ có thể là `null`; nếu thật sự là `null` thì `finally` cũng cần trả về `null`, chứ không tự thay bằng system loader.

Không nên xác định loader cũ bằng `getClass().getClassLoader()` trong thư viện vì loader định nghĩa class thư viện thường **khác** context loader mà caller đã lựa chọn.

## 7. Khi nào dùng TCCL với ServiceLoader?

Giả sử host có interface `com.example.api.Plugin` do loader cha định nghĩa và plugin JAR có service descriptor `META-INF/services/com.example.api.Plugin`.

Trong thư viện sử dụng overload:

~~~java
// Mã minh họa; Plugin đã được định nghĩa bởi API dùng chung.
ServiceLoader<Plugin> providers = ServiceLoader.load(Plugin.class);
~~~

`ServiceLoader.load(Plugin.class)` chọn loader qua **TCCL của thread**. Vì vậy host có thể gọi nó trong một phạm vi tạm:

~~~java
// Mã minh họa; Plugin và pluginLoader được cung cấp bên ngoài.
Thread thread = Thread.currentThread();
ClassLoader old = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    for (Plugin provider : ServiceLoader.load(Plugin.class)) {
        // Sử dụng provider trong phạm vi plugin loader thích hợp.
    }
} finally {
    thread.setContextClassLoader(old);
}
~~~

Cách trực tiếp hơn, khi API cho phép truyền loader rõ ràng:

~~~java
// Mã minh họa; không cần đổi TCCL.
ServiceLoader<Plugin> providers =
        ServiceLoader.load(Plugin.class, pluginLoader);
~~~

**Ưu tiên truyền loader tường minh** nếu API hỗ trợ, vì tránh một thay đổi trạng thái trên thread. Chỉ đổi TCCL khi library/framework bên trong chủ động phụ thuộc vào nó và không có cách truyền loader phù hợp khác.

Dù dùng cách nào, provider class cần liên kết tới **cùng runtime interface** mà host đưa vào `ServiceLoader`. TCCL không chữa được lỗi `ClassCastException` do host/plugin tự định nghĩa hai bản interface cùng tên.

Với **named modules**, `ServiceLoader` và module layers còn có cơ chế `uses`, `provides ... with ...`, readability và các cách nạp provider khác; ví dụ trên chỉ mô tả trường hợp classpath/plugin thông dụng.

## 8. Scope TCCL không tự lan sang công việc bất đồng bộ
`try/finally` chỉ quản lý **thread đang chạy scope**. Nếu một method trong scope gọi `executor.submit(...)` rồi trả về, `finally` của thread gửi sẽ chạy trước khi task hoàn tất, và worker không mặc nhiên nhận TCCL tạm. Với `CompletableFuture`, callback có thể chạy trên một thread khác hoặc tại thread hoàn thành stage, tùy API.

Muốn tác vụ dùng TCCL plugin, chuyển desired loader như dependency, đặt/khôi phục trên chính worker trong wrapper. Khi một thread mới được **tạo** trong scope tạm, nó có thể thừa hưởng plugin loader và giữ reference sau khi scope cha đã phục hồi; giới hạn vòng đời thread con hoặc đặt context rõ ràng qua factory. Không đóng `URLClassLoader` khi tác vụ async vẫn cần tải resource/class từ nó. Bài về thread creation/pool trình bày ví dụ chi tiết.
## 9. Phạm vi hẹp và quan hệ với vòng đời URLClassLoader

Đổi TCCL **không tự đóng** resource loader và **không tự unload** class. Nếu plugin loader là `URLClassLoader`:

~~~java
// Mã minh họa (không phải chương trình độc lập):
try (URLClassLoader pluginLoader =
             new URLClassLoader(urls, parentLoader)) {
    Thread thread = Thread.currentThread();
    ClassLoader previous = thread.getContextClassLoader();
    try {
        thread.setContextClassLoader(pluginLoader);
        usePlugin();
    } finally {
        thread.setContextClassLoader(previous);
    }
}
~~~

Thứ tự có chủ đích:

1. Tạo/open loader.
2. Chuyển TCCL tạm thời.
3. Gọi code cần dùng loader.
4. **Restore TCCL trong `finally`**.
5. Đóng `URLClassLoader` khi công việc dùng loader đã kết thúc.

`URLClassLoader.close()` đóng nguồn JAR/file mà loader quản lý, nhưng không bảo đảm các class đã nạp được giải phóng ngay. Một thread pool, thread sống lâu, object plugin, callback hoặc cache còn giữ loader có thể chặn class unloading.

Nếu công việc đã gửi sang thread khác chưa hoàn thành thì **không đóng plugin loader quá sớm**. Scope cho TCCL và vòng đời plugin phải được đồng bộ: đóng loader chỉ khi không còn task cần dùng nguồn class/resource của nó.

## 10. Mẫu helper và chi phí của abstraction

Có thể đóng gói mã lặp lại như trong ví dụ:

~~~java
// Phương thức minh họa — cần import java.util.concurrent.Callable.
static <T> T withContext(
        ClassLoader temporary, Callable<T> action) throws Exception {
    Thread thread = Thread.currentThread();
    ClassLoader original = thread.getContextClassLoader();
    try {
        thread.setContextClassLoader(temporary);
        return action.call();
    } finally {
        thread.setContextClassLoader(original);
    }
}
~~~

Ưu điểm: nơi gọi ít khả năng quên restore, nested scope được quản lý đúng, và helper dùng được với task trả giá trị.

Nhưng helper không loại bỏ mọi trách nhiệm:

- `Callable.call()` cho phép ném `Exception`; caller cần chính sách xử lý phù hợp.
- Với lỗi restore (ví dụ bị từ chối bởi cấu hình security), exception ở `finally` có thể làm che exception ban đầu. Nếu hệ thống cần đảm bảo cả hai lỗi được báo đầy đủ, cần thiết kế cleanup/error reporting riêng.
- Nếu action trả về `CompletableFuture` rồi kết thúc ngay, `finally` khôi phục TCCL **trước khi** công việc bất đồng bộ chạy xong. Không coi helper đồng bộ này là phạm vi bao trùm tương lai bất đồng bộ.
- Helper chỉ thay TCCL trên **thread gọi nó**, không lan sang các executor thread khác.
- Khi không cần trả kết quả, có thể dùng `Runnable` và vẫn cần xử lý exception theo contract, nhưng đừng phát triển nhiều helper làm che khuất loader được chọn.

Một `AutoCloseable` context scope cũng có thể được thiết kế, nhưng phải bảo đảm capture đúng thread ban đầu, khôi phục đúng thứ tự lồng nhau và tránh close scope từ thread khác. Đối với bài học cơ bản và Java 17, `try/finally` trực tiếp thường minh bạch nhất.

## 11. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách giải quyết |
|---|---|---|
| Sau khi gọi plugin, lời gọi kế tiếp thấy provider của plugin | Quên restore TCCL | Bao lời gọi trong `try/finally` |
| Scoped call lồng nhau trả về system thay vì loader A | Trong scope B restore về system, không restore `previous` | Lưu TCCL tại lúc bắt đầu **mỗi** scope |
| Sau exception, thread pool tiếp tục dùng loader plugin | Đặt restore sau dòng có thể ném exception | Chuyển restore vào `finally` |
| Parent thread đã restore nhưng worker vẫn thấy plugin | Thread mới kế thừa TCCL hoặc worker có trạng thái riêng | Quản lý TCCL trong worker/thread factory |
| `executor.submit` không thấy resource plugin dù caller đã đổi TCCL | Task chạy trên thread khác | Đặt scope trong task thực thi |
| `Class.forName(...)` vẫn không tìm class plugin | API đang dùng loader của caller, không lấy TCCL | Dùng overload có `ClassLoader` tường minh hoặc API hỗ trợ TCCL |
| `ServiceLoader` không thấy provider | TCCL sai hoặc metadata `META-INF/services` thiếu | Truyền loader rõ ràng, kiểm tra provider descriptor |
| Sau plugin reload, loader cũ chưa unload | Thread/callback/cache giữ tham chiếu loader | Restore TCCL, gỡ task/thread/cache, quản lý lifecycle |
| `ClassCastException` giữa host và plugin | Shared interface/DTO bị nhiều loader tự định nghĩa | Dùng một bản API định nghĩa bởi loader chung |
| Đổi TCCL không thay loader của class hiện tại | TCCL không phải defining loader | Kiểm tra `SomeClass.class.getClassLoader()` |
| Resource lookup đổi kết quả giữa môi trường | Parent delegation/classpath/module visibility khác nhau | Kiểm tra đúng loader, URL, module và quyền truy cập |
| `finally` cũng ném exception | Restore thất bại hoặc cleanup không an toàn | Đừng nuốt lỗi; phân tích lỗi chính và lỗi cleanup |

## 12. TCCL và module/security: phạm vi thật sự của cơ chế

**TCCL không tạo sandbox.** Đặt plugin loader làm ngữ cảnh cho thread không giới hạn quyền hệ điều hành của code plugin và không phân lập tiến trình. Với plugin không tin cậy, cần mô hình cách ly thực sự như tiến trình/container và chính sách kiểm soát phù hợp.

**JPMS không biến mất.** ClassLoader có thể tìm thấy bytecode, nhưng named modules vẫn chịu các quy tắc readability, `exports`, `opens` và `ModuleLayer`. Thay TCCL không mặc nhiên cho phép truy cập package đã bị đóng.

**Bootstrap loader và giá trị `null`.** `Thread.getContextClassLoader()` có thể trả `null`. Trường hợp này không nhất thiết là lỗi; cách một thư viện diễn giải TCCL null phụ thuộc API đó. Không tự thay null bằng system loader trong logic restore.

**Class initialization độc lập.** Thay TCCL không chạy `static initializer` của mọi class trong plugin; nó chỉ thay loader được thư viện lựa chọn nếu thư viện chủ động đọc TCCL. Việc `loadClass`, `Class.forName` và initialization hoạt động theo những quy tắc riêng.

## 13. Checklist khi phải đổi context class loader

1. **API thực sự đọc TCCL không?** Nếu hỗ trợ tham số ClassLoader, ưu tiên truyền tham số tường minh.
2. **Loader ban đầu là gì?** Lấy `Thread.currentThread().getContextClassLoader()` và giữ nguyên object reference, kể cả `null`.
3. **Phạm vi đủ hẹp chưa?** Bao đúng lời gọi thư viện/plugin cần loader tạm.
4. **Restore nằm trong `finally` chưa?** Bao gồm cả khi return, exception và nested scopes.
5. **Có thread khác không?** Nếu dùng executor hoặc async, cần scope ở thread thực thi.
6. **Có tạo thread sống lâu không?** Cân nhắc TCCL kế thừa, ThreadFactory và classloader leak.
7. **Loader còn sống trong suốt công việc không?** Không đóng `URLClassLoader` trước khi task dùng nó kết thúc.
8. **Có shared API đúng identity không?** TCCL không giải quyết hai bản interface riêng biệt.
9. **Có test đường lỗi chưa?** Cố ý ném exception rồi xác minh context loader được restore bằng phép `==`.
10. **Có test nested calls chưa?** B khôi phục A, rồi A khôi phục caller.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao cần lưu TCCL cũ trước khi gọi `setContextClassLoader`?

**Đáp án:** Để khôi phục **đúng context ban đầu** của caller, có thể là loader riêng hoặc `null`; không mặc định là system loader.

**Câu 2.** Nếu một phương thức trong scope ném exception, đặt restore sau lời gọi có đủ không?

**Đáp án:** Không. Dòng restore sau lời gọi có thể bị bỏ qua. Phải đặt trong `finally`.

**Câu 3.** Với nested scope A → B, cuối scope B phải restore về loader nào?

**Đáp án:** Về **loader A**, tức TCCL được lưu khi scope B bắt đầu. Khi A kết thúc, restore về TCCL của caller ban đầu.

**Câu 4.** Một task trong thread pool có tự dùng TCCL mà thread gửi task vừa đặt không?

**Đáp án:** Không có đảm bảo tổng quát như vậy. Worker có TCCL riêng; đổi TCCL trong task nếu API bên trong cần context đó.

**Câu 5.** Tại sao `ServiceLoader.load(Service.class, pluginLoader)` thường phù hợp hơn việc đổi TCCL chỉ để nạp provider?

**Đáp án:** Nó chọn loader tường minh, không cần thay trạng thái thread và giảm nguy cơ rò TCCL. Chỉ dùng scope khi API bên dưới không hỗ trợ truyền loader.

**Câu 6.** Scope khôi phục đúng TCCL có đồng nghĩa loader plugin được unload ngay sau đó không?

**Đáp án:** Không. Thread khác, object, cache, listener hoặc tài nguyên còn giữ loader vẫn có thể ngăn unloading.

## 15. Nguồn tài liệu đối chiếu

- [Java SE 17: Thread.getContextClassLoader và setContextClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): hành vi context loader của thread và quyền thay đổi.
- [Java SE 17: ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): overload nạp service bằng TCCL hoặc loader tường minh.
- [Java SE 17: ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): class/resource lookup, delegation và class identity.
- [Java SE 17: URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): nạp resource từ JAR và đóng loader.
- [Java SE 17: Callable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Callable.html): cách truyền task có giá trị trả về và có thể ném checked exception.

**Ghi nhớ:** TCCL là **ngữ cảnh tạm của thread**, không phải defining loader của class. Khi cần chuyển sang plugin loader, hãy **lưu old → set temporary → chạy trong try → restore old trong finally**; scopes lồng nhau khôi phục từng tầng, và executor/async cần được xử lý ngay trên thread thực thi.