# Tách từng kịch bản bằng loader hoặc tiến trình JVM mới

Khi kiểm chứng cơ chế **Java class loading**, việc chạy nhiều kịch bản liên tiếp trong cùng một `ClassLoader` hoặc cùng tiến trình JVM có thể tạo **kết quả sai lệch do trạng thái còn sót**. Một class đã nạp được cache bởi loader, các `static` fields đã được khởi tạo, singleton đã tồn tại, `ServiceLoader` có cache provider, JVM đã liên kết class hoặc khởi tạo class thất bại trước đó. Những lần chạy sau có thể không còn thật sự bắt đầu từ điểm xuất phát giống lần đầu.

Để so sánh công bằng và tái hiện lỗi, có hai mức cô lập chính:

1. **Tạo một class loader mới cho mỗi kịch bản:** tách namespace và trạng thái gắn với **những class thực sự do loader mới định nghĩa**. Nhanh, phù hợp thử parent-first/child-first, class identity, `ClassCastException`, khởi tạo `static` của plugin, SPI và hot redeploy.
2. **Tạo một tiến trình JVM mới cho mỗi kịch bản:** tạo một runtime Java độc lập, thường cô lập cả system class loader, heap, static state, JIT, JVM flags, loaded classes, thread pool nội bộ và nhiều trạng thái toàn cục cấp tiến trình. Tốn chi phí khởi động hơn, phù hợp kiểm thử cách JVM được khởi động, initialization failure, native libraries, `System` properties, classpath/module path, GC/Metaspace và những thí nghiệm có thể treo hoặc làm hỏng process.

**Không đồng nhất hai mức này.** Một loader mới **không tạo JVM mới**; hai JVM mới **không bảo đảm cô lập tài nguyên bên ngoài** như file, database, Redis, network service, port, hoặc user credentials. Mức cô lập phải được chọn theo **trạng thái thực sự cần reset**.

Bài Knowledge này trình bày cách thiết kế thí nghiệm độc lập, giải thích ranh giới kỹ thuật, cung cấp **ví dụ Java 17 đã biên dịch và chạy kiểm chứng** với hai `URLClassLoader` cùng hai JVM con, sau đó hướng dẫn tổ chức test matrix, vòng đời loader/tiến trình, kết quả dự kiến và các lỗi dễ gây “test pass giả”.

## 1. Vì sao cùng một JVM có thể làm méo kết quả?

Một JVM không nạp lại cùng một class trong **cùng defining class loader** mỗi lần code gọi `loadClass`. Nếu lần đầu đã tạo `Class<?>`, lần sau trả về cùng định nghĩa cho cùng binary name theo cơ chế cache/loading chuẩn.

~~~text
JVM hiện tại
   |
   +-- Loader A
   |     +-- plugin.Counter   → Class #A
   |     +-- static count = 2
   |
   +-- Loader B
   |     +-- plugin.Counter   → Class #B
   |     +-- static count = 1
   |
   +-- System/Application loader
         +-- HostRegistry    → global cache của host
         +-- các library class shared qua delegation
~~~

Trong sơ đồ:

- `Class #A` và `Class #B` là **hai class JVM khác nhau** vì defining loader khác nhau, dù binary name giống hệt.
- `static count` thuộc về **định nghĩa class**, vì thế có thể tách giữa A/B.
- `HostRegistry` do parent/system loader định nghĩa vẫn là **một bản chung** trong cùng process; A/B có thể cùng sửa static state của nó.
- JVM có thể tiếp tục giữ class/loader cũ nếu còn reference, dù đã gọi `URLClassLoader.close()`.

### Các trạng thái làm test nhiễu nhau

| Trạng thái | Loader mới có tự reset không? | JVM mới có tách không? |
| --- | --- | --- |
| `static` fields thuộc class do plugin loader định nghĩa | **Có**, nếu mỗi loader thực sự tự định nghĩa bản class riêng | **Có** giữa các process |
| Class identity của `pkg.Plugin` do plugin định nghĩa | **Có** giữa hai defining loader | **Có** giữa process; không thể so `Class<?>` trực tiếp xuyên process |
| `static` fields của class do system/parent loader định nghĩa | **Không**; dùng chung parent `Class<?>` | **Có**, trong process mới |
| `System.setProperty` / process-wide Java system properties | **Không**, cùng đối tượng properties ở JVM hiện tại | **Có** ở mức JVM instance; startup args có thể truyền cùng giá trị ban đầu |
| Host singleton, cache, `ThreadLocal` trên worker sống lâu | **Không mặc định** | **Có** trong process con riêng khi kết thúc, nếu không nối tới resource ngoài |
| `ServiceLoader` object/cache host giữ | **Không**; cần tạo object mới, dùng đúng loader, dọn reference | **Có** trong child process, trừ dữ liệu service ngoài JVM |
| Class initialization failure của cùng định nghĩa class | **Không** được reset bằng gọi lại trong loader cũ | **Có** với JVM mới; loader mới cũng có thể có class definition mới |
| `Thread.currentThread().getContextClassLoader()` | **Không** tự đổi theo loader đang được tạo | Worker/thread mới có context mới theo cách runtime khởi tạo |
| JVM flags, module path lúc launch, default charset/runtime image | **Không** | **Có thể thay đổi** qua lệnh launch mới |
| JIT code cache, GC state, Metaspace trong runtime | **Không** | **Có** khi chạy JVM process khác |
| File, database, network, OS service | **Không** | **Không tự động**; cần sandbox/fixtures/tên tài nguyên riêng |

Các ô “có” trong cột JVM mới là **cô lập theo tiến trình**, không có nghĩa JVM mới quên các file đã ghi, DB rows, network writes, logs hay shared kernel state.

## 2. Loader mới chỉ cô lập khi định nghĩa đúng lớp cần thử

JVM xác định runtime type bằng **(binary name, defining loader)**. Hai `URLClassLoader` độc lập có thể định nghĩa riêng `lab.Counter`, nhưng nếu parent-first trả về class đã có từ parent thì `new URLClassLoader(...)` chưa chứng minh có type mới. Mỗi kịch bản cần kiểm tra `type.getClassLoader()` và `typeA == typeB`. Fixture duplicate-JAR và bài delegation trước đó chỉ ra cách chọn đúng defining loader.

## 3. Phạm vi reset được của trạng thái static

Initialization thành công xảy ra một lần theo runtime class; class erroneous cũng không được JVM tự retry trong cùng defining loader. Khi loader mới **thực sự định nghĩa** một `lab.Counter` mới, các static fields có trạng thái riêng, còn các singleton/static state thuộc loader cha và tài nguyên cấp process vẫn có thể được chia sẻ. Vì vậy thử nghiệm dưới đây so **hai fresh plugin loaders** với **hai tiến trình JVM mới**, để phân biệt isolation theo type và theo process.

## 4. Ví dụ Java 17: hai class loader và hai JVM process độc lập

Ví dụ tách rất rõ **class của plugin** khỏi **host classpath**. `lab.Counter` chỉ được biên dịch vào `plugin-classes`, còn host `ScenarioIsolationDemo` chạy trong thư mục hiện tại. Hai `URLClassLoader` có cùng URL nguồn bytecode nhưng **định nghĩa riêng** `lab.Counter`, do parent là platform loader và không tìm `lab.Counter` trong phần runtime chuẩn.

Sau đó host dùng `ProcessBuilder` chạy `lab.Counter.main` trong **hai JVM mới**. Mỗi child JVM có một `Counter` mới và `static count` ban đầu bằng 0.

### Cấu trúc thư mục

~~~text
isolation-demo/
├── ScenarioIsolationDemo.java
├── src/
│   └── lab/
│       └── Counter.java
└── plugin-classes/          (thư mục output của javac)
    └── lab/
        └── Counter.class
~~~

### File 1: src/lab/Counter.java

~~~java
package lab;

public final class Counter {
    private static int count;

    public static int next() {
        return ++count;
    }

    public static void main(String[] args) {
        System.out.println(next());
    }
}
~~~

`count` là `static` field gắn với **định nghĩa class `lab.Counter`**. `main` cho phép chạy cùng class như entry point của một JVM con, còn `next` cho phép host gọi qua reflection từ những Class được child loaders định nghĩa.

### File 2: ScenarioIsolationDemo.java

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ScenarioIsolationDemo {
    private static int next(ClassLoader loader) throws Exception {
        Class<?> type = loader.loadClass("lab.Counter");
        return (int) type.getMethod("next").invoke(null);
    }

    private static String runFreshJvm(Path classes) throws Exception {
        String executable = System.getProperty("os.name").toLowerCase()
                .contains("win") ? "java.exe" : "java";

        String java = Path.of(System.getProperty("java.home"),
                "bin", executable).toString();

        Process process = new ProcessBuilder(java, "-cp",
                classes.toString(), "lab.Counter")
                .redirectErrorStream(true)
                .start();

        String output = new String(
                process.getInputStream().readAllBytes(),
                StandardCharsets.UTF_8).trim();

        int exit = process.waitFor();
        if (exit != 0) {
            throw new IllegalStateException(
                    "Child JVM exit=" + exit + ": " + output);
        }
        return output;
    }

    public static void main(String[] args) throws Exception {
        Path classes = Path.of("plugin-classes")
                .toAbsolutePath().normalize();

        if (!Files.isRegularFile(classes.resolve("lab/Counter.class"))) {
            throw new IllegalStateException("Compile Counter first");
        }

        URL[] urls = { classes.toUri().toURL() };
        ClassLoader parent = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader a = new URLClassLoader(urls, parent);
             URLClassLoader b = new URLClassLoader(urls, parent)) {

            Class<?> fromA = a.loadClass("lab.Counter");
            Class<?> fromB = b.loadClass("lab.Counter");

            System.out.println("Same Class in A: "
                    + (fromA == a.loadClass("lab.Counter")));
            System.out.println("A next: " + next(a));
            System.out.println("A next again: " + next(a));
            System.out.println("B next: " + next(b));
            System.out.println("Class A equals B: " + (fromA == fromB));
            System.out.println("A loader owns class: "
                    + (fromA.getClassLoader() == a));
            System.out.println("B loader owns class: "
                    + (fromB.getClassLoader() == b));
        }

        System.out.println("JVM run 1: " + runFreshJvm(classes));
        System.out.println("JVM run 2: " + runFreshJvm(classes));
    }
}
~~~

### Build và run trên JDK 17+

Dùng Bash/Linux/macOS từ thư mục `isolation-demo`:

~~~bash
mkdir -p plugin-classes
javac --release 17 -d plugin-classes src/lab/Counter.java
javac --release 17 ScenarioIsolationDemo.java
java ScenarioIsolationDemo
~~~

Với Windows PowerShell, thay lệnh tạo thư mục:

~~~powershell
New-Item -ItemType Directory -Force plugin-classes | Out-Null
javac --release 17 -d plugin-classes src/lab/Counter.java
javac --release 17 ScenarioIsolationDemo.java
java ScenarioIsolationDemo
~~~

**Stdout chính xác** với project/file được tạo đúng như trên:

~~~text
Same Class in A: true
A next: 1
A next again: 2
B next: 1
Class A equals B: false
A loader owns class: true
B loader owns class: true
JVM run 1: 1
JVM run 2: 1
~~~

Chương trình này đã được **biên dịch với `javac --release 17` và chạy trên OpenJDK**, thu được đúng toàn bộ output trên.

### Giải thích chi tiết

1. `a` và `b` đều có URL trỏ `plugin-classes`, nhưng chúng là **hai object URLClassLoader riêng** và parent `platform` không chứa `lab.Counter`.
2. `a.loadClass("lab.Counter")` gọi lại vẫn trả chính `fromA`, nên dòng đầu `true`.
3. `next(a)` thực thi static method của Class #A lần đầu và lần tiếp theo: kết quả **1**, rồi **2**.
4. `next(b)` dùng Class #B với static state riêng, cho kết quả **1**.
5. `fromA == fromB` là `false`; name giống nhau nhưng defining loader khác.
6. Hai phép kiểm tra `getClassLoader() == a/b` là `true`: bằng chứng class được định nghĩa đúng nơi yêu cầu, chứ không bị parent system loader chiếm.
7. `try-with-resources` gọi `URLClassLoader.close()`. Nó đóng tài nguyên loader; **không bảo đảm class unloading/GC ngay lập tức**. Với mục đích demo, việc đóng không ảnh hưởng kết quả đã in.
8. `ProcessBuilder` tìm executable Java bên trong `java.home/bin` của runtime hiện tại, dùng `java.exe` trên Windows hoặc `java` ở Linux/macOS.
9. Mỗi `ProcessBuilder.start()` tạo **một OS process/JVM riêng**, classpath chỉ tới `plugin-classes`, sau đó gọi `lab.Counter.main`. Static count của child process bắt đầu 0, nên mỗi lần in **1**.
10. Host đọc child output bằng UTF-8, chờ exit và kiểm tra exit code. `redirectErrorStream(true)` gom stderr vào stdout để tránh treo đọc một pipe khác không được tiêu thụ; trong ví dụ thành công, child chỉ in một số nguyên.

**Giới hạn thử nghiệm:** Class `Counter` không có dependency ngoài Java runtime nên `getPlatformClassLoader()` là parent phù hợp. Nếu plugin cần gọi API interface của host, không thể mặc định đưa platform loader làm parent: cần **shared API loader** và bảo đảm API identity đúng.

### Phép thử sẽ sai thế nào nếu sắp classpath không đúng?

Giả sử bạn biên dịch `Counter.java` vào chính thư mục host `.` hoặc đặt `plugin-classes` lên host classpath rồi dùng:

~~~java
new URLClassLoader(urls);
~~~

Đây là **fragment**, có parent mặc định là application/system loader. Parent-first có thể thấy `lab.Counter` và trả về cùng parent Class cho cả hai loaders. Khi đó:

~~~text
Class A equals B: true
B next: 3  (nếu A đã gọi next hai lần trên cùng parent Class)
~~~

Output ở đây là **minh họa kịch bản cấu hình sai có điều kiện**, không phải kết quả của demo chuẩn. Đừng sửa bằng cách ép child-first mọi package: với API chung, nhân bản class thường gây `ClassCastException`. Sửa **test packaging/classpath và delegation policy đúng mục tiêu**.

## 5. Khi nào loader mới là đủ?

Loader mới phù hợp khi đại lượng đang đo gắn trực tiếp với **class definition riêng của plugin**:

- Hai Class cùng binary name khác defining loader.
- Static field/initializer của class được loader mới định nghĩa.
- `ClassCastException` khi object của loader A bị cast sang Class tương ứng loader B.
- Parent-first/child-first lookup và `ClassNotFoundException`/`LinkageError` theo namespace.
- SPI/provider discovery trong một custom loader hoặc module layer cụ thể.
- Tải lại implementation plugin khi host/API contract vẫn ổn định.
- Kiểm tra lifecycle `URLClassLoader.close()`, weak references, class unloading sau khi thả reference.

### Nhưng loader mới không reset trạng thái parent

Một test ví dụ có class `HostMetrics` trong **application loader**:

~~~java
public final class HostMetrics {
    public static int count;
}
~~~

Đây là **fragment** (chưa có `package` và file riêng). Dù plugin A và B thuộc loader khác nhau, nếu cả hai ủy quyền class `HostMetrics` cho parent, chúng sẽ dùng **cùng field `HostMetrics.count`**. Loader mới không reset cache, singleton, logger registry hay `ThreadLocal` của class parent.

Cần xác định:

~~~text
State cần reset?
   |
   +-- ở class do child định nghĩa? → child loader mới có thể đủ
   |
   +-- ở class do parent/JDK định nghĩa? → reset tường minh hoặc fork JVM
   |
   +-- ngoài process (file/DB/network)? → fixtures riêng, cleanup ngoài JVM
~~~

Với **module layer động**, mỗi layer có thể tạo loader mới theo `defineModulesWithOneLoader`/`defineModulesWithManyLoaders`, nhưng các parent modules vẫn được chia sẻ; không đồng nhất “layer mới” với “JVM mới”. `ModuleLayer.boot()` là boot layer hiện hành, không được tạo lại khi thêm child layer.

## 6. Khi nào nên fork một JVM mới?

**JVM process mới** là lựa chọn mạnh hơn cho những bài kiểm chứng có thể để lại state khó reset hoặc làm JVM không còn ở trạng thái sạch:

| Mục tiêu kiểm thử | Vì sao fork JVM có giá trị |
| --- | --- |
| Static state trong **system/JDK classes** | Có runtime, system/application loader và heap riêng. |
| JVM/class initialization lỗi và không muốn retry cùng `Class<?>` | Process mới tạo lại class loading/initialization timeline. |
| `System.setProperty`, locale, default config và property initialization | Có bộ startup properties độc lập; cần truyền giá trị rõ bằng command-line arguments. |
| `-Xmx`, `-XX:*`, `--module-path`, `--add-opens`, `--add-exports` | Nhiều tùy chọn khởi động không thể thay giữa chừng trong cùng process. |
| GC/Metaspace/JFR hoặc class unloading benchmark | Mỗi lần chạy có JVM state và lịch sử allocation/GC riêng. |
| Deadlock hoặc một phép thử gây `System.exit`, crash, native code | Không làm chết/treo JVM đang chạy test khác; supervisor có thể hủy child. |
| Test ClassLoader+JNI native library conflicts | Native library load scope có quy tắc riêng; process mới tách native address space. |
| Bảo đảm thứ tự startup/classpath/module resolution | Mỗi child được launch với classpath và module graph từ đầu. |

**Nhược điểm:** Thời gian khởi động, CPU/RAM tăng; phải quản lý command-line flags, environment, stdin/stdout/stderr, timeout, exit code, dọn process tree và file artifacts. Một JVM con chạy cùng user/quyền OS với parent **không tự là security sandbox**. Muốn chạy plugin thật sự không tin cậy, kết hợp process isolation với OS account, sandbox/container, network policy, filesystem permissions và secrets boundaries.

### ProcessBuilder khác ClassLoader thế nào?

`new URLClassLoader(...)` tạo object **bên trong JVM hiện tại**. `new ProcessBuilder(...).start()` tạo process mới. Child process không chia sẻ địa chỉ object, `Class<?>`, singleton hay `static` field trực tiếp với parent; kết nối cần IPC/file/socket hoặc giao thức khác.

~~~text
Host JVM                               Child JVM
  heap / Class objects riêng              heap / Class objects riêng
  system loader / static state             system loader / static state
  URLClassLoader A                         plugin.Counter class
  URLClassLoader B                         static count = 1
      |                                          |
      +------------- ProcessBuilder ------------+
                             |
                        stdout / exit code
~~~

Giữa các JVM không thể viết `hostObject == childObject` theo nghĩa Java reference (hai object không nằm chung heap). Khi cần trao đổi kết quả, serial hóa dữ liệu hoặc truyền chuỗi/json/protobuf qua IPC và kiểm tra status.

## 7. Quản lý ProcessBuilder để test không bị treo

Ví dụ đầy đủ phần 4 dùng lối đơn giản vì child rất nhỏ và luôn thoát. Với test có thể deadlock, start server hoặc chạy lâu, cần **timeout và cleanup**.

Fragment mẫu (giả định `Process process` đã start):

~~~java
boolean finished = process.waitFor(
        10, java.util.concurrent.TimeUnit.SECONDS);

if (!finished) {
    process.destroyForcibly();
    process.waitFor();
    throw new IllegalStateException("Child JVM timeout");
}

int exitCode = process.exitValue();
if (exitCode != 0) {
    throw new IllegalStateException("Child JVM failed: " + exitCode);
}
~~~

Đây là **fragment**, không phải chương trình độc lập. Khi dùng trong ứng dụng thực:

- **Đọc/redirect stdout và stderr** để tránh child chặn vì pipe buffer đầy. Nếu child tạo output lớn, dùng thread đọc stream đồng thời hoặc redirect ra file; `readAllBytes()` giữ toàn bộ output trong memory, không nên áp dụng cho log vô hạn.
- **Timeout** phải đo trường hợp child treo do deadlock/chờ I/O. Nếu đọc `readAllBytes()` trước khi áp timeout thì chính việc đọc có thể **chờ tới EOF mãi**. Với child có khả năng treo, thiết kế đọc bất đồng bộ/redirect file và chờ có timeout một cách chủ động.
- **Dọn process descendants** khi child tự spawn grandchildren; `destroyForcibly()` của một Process không tự hứa hủy mọi process con/cháu trên mọi OS.
- **Chỉ truyền environment/working directory cần thiết**, tránh thừa kế bí mật/biến môi trường có thể thay hành vi runtime ngoài ý muốn. `ProcessBuilder.environment()` cho phép cấu hình environment của process con.
- **Bắt exit code và stderr**; không coi “stdout có dòng expected” là PASS nếu process cuối cùng thoát lỗi.
- **Không phụ thuộc absolute PID**: PID khác giữa lần chạy và có thể được tái sử dụng, không phải định danh logic cho scenario.

### Một kịch bản lỗi có thể phá các test tiếp theo

Nếu một test chạy:

~~~java
System.setProperty("demo.mode", "broken");
~~~

Đây là **fragment** chạy trong cùng JVM; property tồn tại cho những test khác trừ khi được restore/reset. Loader mới **không thay** `System.getProperties()` toàn process. Một forked JVM mới có properties riêng; tuy nhiên command-line `-Ddemo.mode=...` và environment có thể lại làm state giống nhau nếu runner truyền cùng cấu hình.

Nếu muốn test độc lập mà không fork, dùng `try/finally` giữ/restoring giá trị gốc cho property và các global hooks **chỉ khi đảm bảo không có thread khác cùng sửa state đó**. Với parallel test suite, reset toàn cục có thể cạnh tranh; fork JVM thường dễ tin cậy hơn.

## 8. Phân biệt “tạo ClassLoader mới” và “tạo ModuleLayer mới”

Từ Java 9, named modules có **module layer** và class loader mapping. Một module loader có thể được tạo khi:

~~~java
ModuleLayer layer = ModuleLayer.boot()
        .defineModulesWithOneLoader(configuration, parentLoader);
~~~

Đây là **fragment**; `configuration` phải là resolved `Configuration` hợp lệ và `parentLoader` phù hợp, chưa phải chương trình độc lập. `defineModulesWithOneLoader` tạo loader mới cho các modules của layer mới, dùng loader truyền vào làm parent theo API.

Nhưng:

- Parent layer/loader và các module runtime vẫn được chia sẻ theo cấu hình.
- `ModuleLayer.boot()` không khởi động một JVM mới và không bị tái tạo cho mỗi dynamic layer.
- Hai layer mới riêng biệt có thể định nghĩa cùng binary name bằng loaders khác nhau, nhưng điều đó **không biến object của chúng thành cùng type**.
- Module readability, `exports`, `opens`, `uses`, `provides` vẫn ảnh hưởng behavior. Cô lập loader chỉ là một phần của module isolation.
- Một layer không có `close()`; việc thu hồi phụ thuộc reachability của layer, Class, loader, threads và các references khác.

Trong test module/plugin, nếu đang đo **ModuleLayer resolution** cần bảo đảm parent configuration không vô tình chứa module target. Nếu muốn đo full **startup module graph**, hãy chạy child JVM mới với `--module-path`/`-m` tương ứng.

## 9. Không để trạng thái framework rò giữa hai scenario

`ServiceLoader` có cache provider riêng và các API `load(SPI)` có thể dùng **Thread Context ClassLoader**. Nếu scenario A thay TCCL hoặc giữ cache/listener của plugin cũ, loader mới ở scenario B vẫn có thể bị ảnh hưởng. Khi xong, khôi phục TCCL trong `finally`, bỏ registry/listener và bỏ cache tham chiếu plugin. Bài resource/SPI và bài lifecycle trong chương có các bài thử riêng về những reference paths này.

## 10. Đóng loader xong chưa đồng nghĩa đã unload class

`URLClassLoader.close()` đóng đường tìm class/resource do loader đó quản lý, nhưng không tự xóa các `Class<?>` đã load hay dọn mọi strong references. Khi test isolation pass, nó mới chứng minh state quan sát đúng theo kịch bản; chưa đủ khẳng định loader cũ đã được GC. Bài **Kiểm chứng vòng đời đóng loader, dừng plugin và giải phóng tham chiếu** đưa ra tiêu chí stop, TCCL cleanup và cách quan sát unload bằng weak references/heap tooling mà không giả định GC tất định.

## 11. Lập ma trận kiểm chứng và tiêu chí PASS

Một test suite tốt phải xác định **trạng thái cần reset, loader ownership và quan sát PASS** trước khi chạy.

| Scenario | Mức cô lập nên chọn | Assertion quan trọng |
| --- | --- | --- |
| Same-loader cache | Cùng loader trong một test | `a.loadClass(name) == a.loadClass(name)` |
| Static state của plugin | Hai loader mới, class chỉ child sở hữu | A: 1→2; B: 1; `ClassA != ClassB` |
| Duplicate API class | Hai defining loaders, hoặc shared-parent control | Compare `Class<?> ==`, `isInstance` và expected cast/error |
| Parent-first vs child-first | Loader cấu hình riêng, sources cố định | Class được định nghĩa ở loader được mong muốn |
| Initialization failure của plugin | New defining loader cho mỗi scenario | Lỗi xảy ra độc lập trên định nghĩa mới |
| Global `System` property / host singleton | JVM mới hoặc reset đồng bộ | Property/singleton baseline giống nhau mỗi run |
| Native library/`System.exit`/crash | Child JVM/process mới | Exit code, timeout, logs, không làm chết test runner |
| GC/Metaspace/class unloading | JVM mới cho các run đo độc lập | JVM flags, workload, GC logs, JFR, số lần GC/loader counts |
| Plugin hot redeploy | Loader/layer mới theo vòng deploy | Type identity mới, resources/old refs được dọn |
| Full startup module path | Fork với `--module-path`/`-m` | Named modules/resolution theo launch args |
| File/DB mutation | Process + test resource/fixture riêng | Không ghi lên dữ liệu dùng chung, cleanup sau test |

Nếu test cần **so sánh performance**, còn phải kiểm soát warm-up/JIT compilation, GC, CPU contention và môi trường. JVM mới giúp giảm nhiễu từ warm-up trước đó nhưng **không tự làm hai benchmark có điều kiện giống nhau**. Khi benchmark nghiêm túc nên dùng harness phù hợp như JMH, đo nhiều forks/iterations và báo sai số.

### Pseudocode tổ chức suite

~~~text
for each scenario:
    decide isolation policy:
        LOADER:
            allocate distinct loader, verify defining loader identity
            execute assertions
            cleanup tasks/caches/TCCL/resources
        JVM:
            spawn java process with explicit args, env, classpath/module path
            capture stdout/stderr, enforce timeout, read exit status
            cleanup process tree and external fixtures
    record test evidence and repeatability
~~~

Đây là **pseudocode**, không phải một test framework cụ thể. Cả hai mức cô lập nên đi kèm cleanup và assertions về **đúng state**, không chỉ kiểm tra “không có exception”.

## 12. Những lỗi kiểm thử thường gặp

**Lỗi 1 — “new loader chắc chắn new class”.** Sai. Parent-first có thể trả class do parent định nghĩa. Luôn so `type.getClassLoader()` và `Class<?> ==`.

**Lỗi 2 — “new loader reset toàn bộ static fields”.** Sai. Chỉ những class do loader mới định nghĩa có bản static state riêng. Static state của parent/JDK classes còn chung.

**Lỗi 3 — “ClassLoader.close() làm JVM quên class ngay”.** Sai. Closing không cưỡng bức class unloading; các strong references khác còn giữ lớp/loader.

**Lỗi 4 — “đổi TCCL rồi mọi loadClass dùng nó”.** Sai. Chỉ các API chủ động lấy context loader (một số ServiceLoader/resource lookup) bị tác động. `Class.forName(name, true, explicitLoader)` dùng loader được truyền tường minh.

**Lỗi 5 — “reload() trên ServiceLoader reset loader”.** Sai. `reload()` xóa cache provider của object ServiceLoader đó; không tạo loader mới hoặc reset class initialization.

**Lỗi 6 — “chạy test trong thứ tự khác mà pass là đủ”.** Không đủ. Nếu outcome phụ thuộc thứ tự, có leak hoặc shared state chưa được khai báo. Dùng fresh loader/fork và kiểm soát fixtures.

**Lỗi 7 — “JVM mới hoàn toàn sạch mọi thứ”.** Sai. File/database/network/external service, thời gian hệ thống, environment hoặc shared temp directory có thể còn dữ liệu từ run trước.

**Lỗi 8 — “ProcessBuilder.start rồi không đọc stderr có sao đâu”.** Có thể treo khi pipe đầy; cần drain/redirect stdout/stderr và quản lý exit/timeouts.

**Lỗi 9 — “process fork đồng nghĩa sandbox”.** Sai. Child Java chạy theo OS user/quyền của process nếu không đổi; cần isolation ở tầng OS/container cho code không tin cậy.

**Lỗi 10 — “dùng System.gc() để reset JVM giữa các bài test”.** Sai. GC không reset singleton/parent classes/system properties, không bảo đảm class unloading và không làm JVM giống process mới.

**Lỗi 11 — “ClassNotFoundException là kết quả giống ở mọi loader”.** Không đúng: source classpath, parent delegation, module graph và dynamic URLs có thể khác. Phải ghi rõ class loader được hỏi và đường tìm thực tế.

**Lỗi 12 — “cùng tên class đủ để cast an toàn”.** Sai. Defining loader tham gia identity. Nếu hai loader cùng define một API interface, có thể gặp `ClassCastException`/`ServiceConfigurationError`; đặt API chung ở parent.

## 13. Hướng dẫn debug khi hai kịch bản ảnh hưởng lẫn nhau

Khi test A chạy riêng PASS, nhưng chạy sau test B FAIL:

1. **In defining loader:** `type.getClassLoader()`, class name và module. Xác định A/B có thật sự dùng Class khác không.
2. **Kiểm tra parent delegation:** ClassFile có bị system classpath chứa trước không? Có shared API và implementation bị trộn không?
3. **In static state trước và sau:** Những class nào do parent định nghĩa? Singleton/cache của host có cần cleanup?
4. **Kiểm tra TCCL ngay tại worker:** Submitter và worker không mặc định giống nhau.
5. **Xem `ServiceLoader`/SPI provider cache:** Có giữ object từ scenario cũ không?
6. **Xem threads còn sống:** Worker/task/callback/plugin thread có kết thúc không? ThreadLocal và TCCL đã restore chưa?
7. **Dọn file, database, system properties:** Nếu fork vẫn fail, hướng tới state ngoài JVM.
8. **Chạy fork độc lập:** Nếu lỗi biến mất chỉ khi fork, tìm process-wide state/shared runtime như static host caches, JNI, JVM startup options.
9. **Chụp heap dump/JFR khi cần:** Nếu loader cũ còn reachable sau undeploy, tìm `Path To GC Roots` từ cache/threads/listeners thay vì chỉ tin `close()`.
10. **Viết test regression deterministic:** Thiết lập đầy đủ tiền điều kiện, tách scenario, assert kết quả và cleanup theo lifecycle.

Một diagnostic fragment hữu ích:

~~~java
Class<?> type = loader.loadClass("lab.Counter");
System.out.println("Name: " + type.getName());
System.out.println("Defining loader: " + type.getClassLoader());
System.out.println("Module: " + type.getModule());
System.out.println("TCCL: "
        + Thread.currentThread().getContextClassLoader());
~~~

Đây là **fragment**, cần biến `loader`. Các dòng loader/module/TCCL phụ thuộc môi trường, nên **không gắn stdout cố định** cho fragment này. Có thể dùng `Class<?> ==` thay vì chỉ so chuỗi tên.

## 14. Tự kiểm tra kiến thức

**Câu 1.** Gọi `new URLClassLoader(urls)` hai lần nhưng cả hai trả `String.class`. Có nghĩa lớp `String` đã được định nghĩa riêng bởi từng loader không?

**Đáp án:** Không. `String` là kiểu nền tảng do bootstrap loader định nghĩa; parent delegation trả cùng định nghĩa.

**Câu 2.** Có hai loader A/B riêng, `lab.Counter` chỉ có trên application classpath của parent. `A.loadClass("lab.Counter") == B.loadClass("lab.Counter")` có thể bằng `true` không?

**Đáp án:** Có. Với parent-first, cả hai có thể dùng cùng Class parent. Muốn kiểm tra cô lập child, phải để class target không bị parent lấy mất và xác nhận defining loader.

**Câu 3.** Vì sao static counter ở A có thể là 2 nhưng ở B là 1?

**Đáp án:** Vì `lab.Counter` do hai defining loader khác nhau định nghĩa; mỗi định nghĩa có static fields và initialization state riêng.

**Câu 4.** Một test thay `System.setProperty`; đổi URLClassLoader có reset property không?

**Đáp án:** Không, vì properties tồn tại ở phạm vi JVM/process. Cần reset đúng cách với đồng bộ thích hợp hoặc fork JVM mới.

**Câu 5.** Vì sao fork JVM phù hợp để kiểm tra `System.exit` hoặc `-XX:MaxMetaspaceSize`?

**Đáp án:** Có process độc lập để kết thúc/crash mà không giết test runner; JVM flags được xác định từ lúc launch riêng.

**Câu 6.** Dùng JVM process mới có tự rollback database writes của JVM trước không?

**Đáp án:** Không. Database là state ngoài process; cần database fixture/transaction cleanup/namespace cô lập.

**Câu 7.** `URLClassLoader.close()` có bảo đảm `Class<?>` của plugin biến mất không?

**Đáp án:** Không. Nếu còn Class/object/thread/static cache reference, class/loader có thể còn reachable. Unloading do GC/JVM quyết định.

**Câu 8.** Vì sao cần so `fromA.getClassLoader() == loaderA` khi test static isolation?

**Đáp án:** Để chứng minh class thực sự do loader A định nghĩa, thay vì bị parent loader cung cấp và vô tình chia sẻ static state.

**Câu 9.** Nếu runner tạo JVM con nhưng không đặt timeout, hậu quả là gì?

**Đáp án:** Test có thể treo vô hạn khi child deadlock/chờ I/O; cần timeout, giám sát exit và dọn process.

**Câu 10.** Hai loader mới có bảo đảm hai ServiceLoader trả đúng provider khác nhau không?

**Đáp án:** Không mặc định. Cần service API identity, TCCL/explicit loader, metadata SPI, parent delegation và cache đúng. Loader mới chỉ tạo namespace; discovery policy còn phải xác định.

## Ghi nhớ

**Muốn kiểm chứng độc lập, trước hết hỏi “trạng thái này thuộc class định nghĩa bởi loader nào, hay thuộc JVM/process nào?”** Dùng **loader mới** để kiểm tra class identity, static fields và plugin namespace; dùng **JVM mới** khi cần reset state toàn process, runtime flags, initialization history hoặc cô lập lỗi nặng. Với cả hai, kiểm soát **parent delegation, shared API, classpath/module path, TCCL, caches và cleanup**. JVM fork không thay thế việc cách ly **file/database/network**, và `URLClassLoader.close()` không có nghĩa unloading lập tức.

**Tài liệu chuẩn Java 17:**

- `ClassLoader` và `getClassLoadingLock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- `URLClassLoader` và `close()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- `ProcessBuilder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html
- `Process`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Process.html
- `ModuleLayer` và `defineModulesWithOneLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- `ServiceLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- JLS `12, Execution, Loading, Linking and Initialization: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html
- JVMS `5, Loading, Linking and Initializing: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
