# Theo dõi khởi tạo và dỡ lớp bằng log tag phù hợp trong Java

## 1. Mục tiêu: phân biệt đúng các sự kiện trong vòng đời lớp

Khi phân tích ứng dụng Java có nhiều thư viện, plugin, framework hoặc cơ chế reload, câu hỏi “lớp này đã khởi tạo chưa?” khác hẳn “JVM đã nạp lớp chưa?” hay “lớp đã được dỡ khỏi JVM chưa?”. **Class loading**, **class initialization** và **class unloading** là các sự kiện có điều kiện, thời điểm và ý nghĩa khác nhau. JVM HotSpot cung cấp **Unified Logging** qua tùy chọn `-Xlog` để quan sát chúng theo các nhóm tag riêng.

Bài này tập trung vào **chọn đúng log tag, tái hiện sự kiện, đọc log có căn cứ và hạn chế của bằng chứng** trên HotSpot JDK 17+. Những câu lệnh dưới đây dựa trên cú pháp `java` của JDK 17; JVM khác như OpenJ9 có thể dùng hệ thống log và tùy chọn khác.

| Sự kiện | Ý nghĩa | Log HotSpot cần xem |
|---|---|---|
| **Loading** | JVM lấy/định nghĩa một lớp hoặc interface; class đã có định danh runtime theo tên và defining loader | `class+load` |
| **Linking/resolution** | JVM verify, prepare hoặc resolve các symbolic reference | `class+resolve` khi cần phân tích sâu; không đồng nhất với initialization |
| **Initialization** | JVM thực hiện quy trình khởi tạo class/interface, gồm thực thi các initializer tĩnh khi có | `class+init` |
| **Unloading** | JVM ghi nhận dỡ một lớp/interface đã nạp khi vòng đời và điều kiện thu hồi cho phép | `class+unload` |
| **Garbage collection** | Chu kỳ GC; dữ liệu thời gian/loại thu gom để đối chiếu với unloading | `gc` hoặc các nhóm `gc*` khi cần |
| **Metaspace** | Bối cảnh sử dụng/cấp phát bộ nhớ metadata của JVM | `gc+metaspace` ở level phù hợp và các công cụ thống kê khác |

Không suy luận “có dòng load ⇒ chắc chắn đã init” hoặc “GC đã chạy ⇒ mọi class không dùng nữa đã unload”. Một lớp có thể được **load nhưng chưa init**; một class loader đã mất tham chiếu mạnh cũng chỉ làm các lớp do nó định nghĩa **đủ điều kiện** để có thể unload, chứ không tạo cam kết về thời điểm.

### Sơ đồ ý nghĩa

```text
Nhận yêu cầu dùng lớp
       │
       ▼
   Loading ──────────────► [class,load]
       │
       ▼
   Linking / resolution
       │
       ▼
Active use kích hoạt? ── Không ──► Có thể vẫn chưa init
       │ Có
       ▼
   Initialization ───────► [class,init]
       │
       ▼
 Lớp/loader tồn tại, được ứng dụng sử dụng
       │
       ▼
 Loader/lớp đủ điều kiện thu hồi?
       │ Có, và JVM thực hiện unloading
       ▼
   Unloading ────────────► [class,unload]
```

Đây là sơ đồ để phân loại **ý nghĩa log**; nó không khẳng định thời gian của mọi bước đều tuyến tính, hay mỗi bước đều xuất hiện chính xác một dòng. JVM có quyền trì hoãn resolution; một số log có thể được ghi bởi các thread khác nhau.

## 2. Chọn đúng `-Xlog` tag và level

Unified Logging có cú pháp tổng quát:

```text
-Xlog[:[tag-selection][:[output][:[decorators][:output-options]]]]
```

Trong `tag-selection`:

- `class+load` nghĩa là **tập tag kết hợp** `class` và `load`.
- Dấu phẩy trong `class+load=info,class+init=info,class+unload=info` nghĩa là **nhiều lựa chọn** độc lập.
- `=info` chọn các thông điệp từ level `info` trở lên trong ngưỡng severity của lựa chọn đó; `debug`/`trace` chi tiết hơn, có thể làm log tăng rất mạnh.
- Nếu không có `*` sau tổ hợp tag, selection khớp **chính xác tập tag**. `class*=debug` khớp các tập tag chứa `class` và sẽ rộng/ồn hơn.
- `-Xlog:help` hiển thị tag, level, decorator và output-option của **chính runtime Java đang chạy**. Nếu một lựa chọn không được HotSpot nhận diện, đọc error và trợ giúp thay vì giả định cờ hoạt động.

### Cấu hình tối thiểu theo câu hỏi

**Chỉ biết lớp nào được nạp:**

```bash
java -Xlog:class+load=info -cp . InitTrace
```

**Chỉ theo dõi khi khởi tạo:**

```bash
java -Xlog:class+init=info -cp . InitTrace
```

**Chỉ theo dõi class unloading:**

```bash
java -Xlog:class+unload=info -cp . UnloadTrace
```

**Theo dõi cả ba loại sự kiện và đối chiếu GC:**

```bash
java -Xlog:class+load=info,class+init=info,class+unload=info,gc=info -cp . InitTrace
```

`UnloadTrace` và `InitTrace` được tạo trong các phần thực hành bên dưới. Trên HotSpot, `-verbose:class` tương đương logging class load và class unload ở mức `info` theo tài liệu JDK 17; **không thay thế `class+init`** khi đề bài là quan sát khởi tạo.

Chú ý `-Xlog:class=info` không đồng nghĩa ba selection trên. Tag `class` đứng một mình là một tag set khác với `class+load` và `class+init`. Khi điều tra sự kiện cụ thể, dùng đúng tổ hợp được tài liệu hỗ trợ.

### Ghi ra file để giảm nhiễu stdout

```bash
java -Xlog:class+load=info,class+init=info,class+unload=info,gc=info:file=class-events-%p.log:time,uptime,pid,tid,level,tags:filecount=5,filesize=10M -cp . InitTrace
```

Trong cấu hình này:

- `file=class-events-%p.log` ghi log ra file có PID, thuận tiện phân biệt nhiều JVM; thư mục chạy cần quyền ghi.
- `time,uptime,pid,tid,level,tags` bổ sung thời gian đồng hồ, thời gian kể từ khi JVM chạy, PID/TID, level và tags để tương quan sự kiện.
- `filecount=5,filesize=10M` giới hạn dung lượng/rotation theo cơ chế Unified Logging; việc rotation được mô tả là xấp xỉ kích thước cấu hình.
- Log JVM đi vào file; lệnh `System.out.println` của chương trình vẫn ra stdout, giúp tách hai luồng quan sát.

Muốn xem log và ứng dụng cùng console mà không cần file, giữ `:stdout:uptime,level,tags`:

```bash
java -Xlog:class+load=info,class+init=info,class+unload=info:stdout:uptime,level,tags -cp . InitTrace
```

Trên Windows PowerShell, có thể đặt toàn bộ tham số `-Xlog:...` trong cặp dấu nháy khi shell/parser yêu cầu. Cú pháp dùng dấu phẩy là **một đối số JVM**, không phải các đối số tùy ý.

## 3. Thí nghiệm Java 17+: thấy rõ load trước init

Để quan sát initialization, cần thiết kế chương trình sao cho lớp mục tiêu được load trước, rồi mới có **active use**. Một `Class.forName` có overload `initialize=false` giúp thể hiện điểm khác biệt.

Tạo file **`InitTrace.java`**:

```java
public final class InitTrace {
    static final class Target {
        // Constant variable: compiler có thể inline giá trị.
        static final int CONSTANT = 7;

        // Không phải compile-time constant.
        static int counter = 42;

        static {
            System.out.println("Target.<clinit> executed");
        }

        static void ping() {
            System.out.println("Target.ping");
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("1. Class.forName(false)");
        Class.forName("InitTrace$Target", false,
                InitTrace.class.getClassLoader());

        System.out.println("2. Constant = " + Target.CONSTANT);
        System.out.println("3. Read counter");
        System.out.println("Counter = " + Target.counter);

        System.out.println("4. Call ping");
        Target.ping();

        System.out.println("5. Class.forName(true) after init");
        Class.forName("InitTrace$Target", true,
                InitTrace.class.getClassLoader());
        System.out.println("6. Done");
    }
}
```

Biên dịch và chạy với HotSpot JDK 17+:

```bash
javac InitTrace.java
java -Xlog:class+load=info,class+init=info -cp . InitTrace
```

Chương trình tự in chính xác các dòng sau, **nằm xen giữa những dòng logging khác của JVM**:

```text
1. Class.forName(false)
2. Constant = 7
3. Read counter
Target.<clinit> executed
Counter = 42
4. Call ping
Target.ping
5. Class.forName(true) after init
6. Done
```

**Cách phân tích:**

1. `Class.forName("InitTrace$Target", false, loader)` yêu cầu load lớp nhưng **không yêu cầu initialize**. Có thể thấy dòng log `[class,load] InitTrace$Target ...` trước khi chương trình in “3. Read counter”.
2. `Target.CONSTANT` là một **constant variable** kiểu nguyên thủy với hằng biên dịch. Java thường inline `7` vào caller nên chỉ đọc hằng này **không kích hoạt Target initialization**.
3. `Target.counter` là trường static không phải constant variable: lần đọc đầu là **active use** và kích hoạt initialization, chạy initializer tĩnh. JVM có thể ghi `[class,init] ... InitTrace$Target ...` gần lúc chương trình in `Target.<clinit> executed`.
4. `Target.ping()` gọi sau khi lớp đã được init nên không chạy lại static initializer.
5. `Class.forName(..., true, ...)` tiếp tục yêu cầu init nhưng lớp đã được init rồi; không có lần chạy `<clinit>` thứ hai cho cùng runtime class.

Tên nội bộ của nested class là `InitTrace$Target`, khác cách viết Java source `InitTrace.Target`. Class file `InitTrace$Target.class` được tạo cùng `InitTrace.class` sau khi biên dịch.

**Đọc event log cẩn thận:** Dòng `[class,init]` của HotSpot có thể có chỉ số, tên lớp ở dạng `InitTrace$Target` và địa chỉ VM. Những con số/địa chỉ đó **phụ thuộc phiên chạy**, không phải output cố định. Không cần tìm đúng một format text bất biến; kiểm tra **tag, tên lớp, mốc thời gian và thứ tự tương đối**. Đặc biệt, log init có thể báo sự kiện cho các lớp nền tảng của JDK mà code không trực tiếp nhắc tới.

### Vì sao `Target.class` và `Class.forName(false)` không tự chứng minh init?

Một literal `Target.class` có thể lấy `Class` object mà không cần thực hiện class initialization; còn `Class.forName(name, false, loader)` có ý nghĩa rõ ràng là **không initialize tại lệnh đó**. Đây là lý do số dòng `[class,load]` không thể dùng làm số lớp đã init.

Các thao tác thường kích hoạt init theo JLS `12.4.1` gồm: tạo instance của class, gọi static method do class khai báo, đọc/ghi static field do class khai báo **ngoại trừ đọc constant variable**, và một số thao tác reflection. Khi initialize class, JVM xử lý superclass chưa init và những superinterface phù hợp theo đặc tả; thứ tự log có thể chứa nhiều lớp hơn mục tiêu.

Một lớp chỉ initialize **một lần cho mỗi runtime class identity** trong đời sống hợp lệ của nó. Nếu loader khác định nghĩa lớp cùng tên, đó là một class khác và có thể init riêng. Không xem việc có hai event trùng tên là bằng chứng JVM “init lại cùng một lớp” trước khi biết defining loader.

## 4. Đọc `class+load`, `class+init` và `class+unload` có căn cứ

Ví dụ dạng log minh họa, đã lược bỏ các dòng khác và **không đại diện chính xác cho địa chỉ/ID cố định**:

```text
[0.090s][info][class,load] InitTrace$Target source: file:/.../
[0.094s][info][class,init]  ... Initializing 'InitTrace$Target' ...
```

Giải nghĩa từng phần:

- `[0.090s]` là uptime từ lúc JVM khởi động (nếu bật decorator này).
- `[info]` là level.
- `[class,load]` hoặc `[class,init]` là **tập tag của dòng log**. Dấu phẩy xuất hiện trong **cách trình bày tag** của log, trong khi cú pháp selection dùng dấu `+`.
- `source` trong log load có thể là đường JAR, directory, `shared objects file` hoặc dạng khác; không nhất thiết luôn chỉ vào một file local đơn giản.
- `class,init` phản ánh JVM xử lý initialization; nếu lớp không có static initializer có nội dung, vẫn có thể có thông điệp khởi tạo. Không yêu cầu phải nhìn thấy `System.out.println` từ `<clinit>` mới chấp nhận log.

**Hạn chế:** log “class đã load” không chỉ ra rằng loader vẫn reachable sau thời gian dài; log init không đo lượng bộ nhớ cấp phát; log unload không chứng minh nguyên nhân sâu xa khiến loader cuối cùng được thu hồi. Mỗi tag giải đáp một câu hỏi, và nên đối chiếu các bằng chứng khác khi chẩn đoán leak hoặc reload.

## 5. Thí nghiệm: tạo loader riêng và theo dõi class unloading

Class unloading khó tạo ra một cách tất định hơn class initialization. Lớp được định nghĩa bởi loader tồn tại dài hạn thường không thể unload độc lập tùy ý. Ta dùng `URLClassLoader` riêng để định nghĩa lớp plugin, thực hiện một lần, đóng tài nguyên và bỏ **strong reference**, sau đó quan sát log.

### Cấu trúc thư mục

```text
working-directory/
  UnloadTrace.java
  plugin-src/
    plugin/
      Ephemeral.java
  plugin-bin/           (do javac tạo, KHÔNG đặt vào -cp của host)
```

File **`plugin-src/plugin/Ephemeral.java`**:

```java
package plugin;

public final class Ephemeral {
    static {
        System.out.println("plugin.<clinit>");
    }

    public static void touch() {
        System.out.println("plugin.touch");
    }
}
```

File **`UnloadTrace.java`**:

```java
import java.lang.ref.WeakReference;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class UnloadTrace {
    private static WeakReference<ClassLoader> runPlugin()
            throws Exception {
        URL url = Path.of("plugin-bin")
                .toAbsolutePath().toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[] { url },
                ClassLoader.getPlatformClassLoader())) {
            Class<?> clazz = Class.forName(
                    "plugin.Ephemeral", true, loader);
            clazz.getMethod("touch").invoke(null);

            System.out.println("Child defines class: "
                    + (clazz.getClassLoader() == loader));

            // Không trả Class<?> hoặc loader mạnh về main.
            return new WeakReference<>(loader);
        }
    }

    public static void main(String[] args) throws Exception {
        WeakReference<ClassLoader> weak = runPlugin();

        // Chỉ tạo cơ hội GC; không đảm bảo unload.
        for (int i = 0; i < 30 && weak.get() != null; i++) {
            System.gc();
            Thread.sleep(150);
        }

        System.out.println("Loader reference cleared: "
                + (weak.get() == null));
    }
}
```

Để chạy trên shell Bash từ thư mục `working-directory`:

```bash
mkdir -p plugin-bin
javac -d plugin-bin plugin-src/plugin/Ephemeral.java
javac UnloadTrace.java
java -Xlog:class+load=info,class+init=info,class+unload=info,gc=info -cp . UnloadTrace
```

Với Windows PowerShell, chỉ cần tạo thư mục bằng `New-Item -ItemType Directory -Force plugin-bin` (hoặc `mkdir plugin-bin`) rồi chạy ba lệnh `javac` và `java` giống trên.

Những dòng **do ứng dụng** tạo ra lúc bắt đầu luôn là:

```text
plugin.<clinit>
plugin.touch
Child defines class: true
```

Sau đó ứng dụng in một trong hai khả năng:

```text
Loader reference cleared: true
```

hoặc:

```text
Loader reference cleared: false
```

Hai giá trị đều có thể xảy ra. Nếu HotSpot thực sự unload lớp `plugin.Ephemeral` trong cửa sổ quan sát và logging đã bật đúng, log có thể chứa thông điệp gắn tag `[class,unload]` nêu tên lớp đó. Dòng này có mốc thời gian do JVM quyết định; không tự viết một dòng unload giả vào output của ứng dụng.

**Tại sao thí nghiệm có ý nghĩa?**

- Parent là `ClassLoader.getPlatformClassLoader()`, không phải application class loader nạp `UnloadTrace`. Nếu `plugin-bin` **không** xuất hiện trên classpath của host, `plugin.Ephemeral` sẽ được định nghĩa bởi loader con đúng như câu in `Child defines class: true`.
- `runPlugin()` có scope riêng để tham chiếu local tới `clazz`, `loader` và kết quả reflection hết vòng đời khi phương thức trả về. `WeakReference` không giữ loader sống mạnh.
- `URLClassLoader.close()` chỉ đóng tài nguyên mà loader quản lý, **không phải API bắt buộc unload**.
- `System.gc()` đề nghị GC và có thể bị bỏ qua/không làm phát sinh class unloading trong thời gian quan sát; cấu hình như `-XX:+DisableExplicitGC` khiến việc dựa vào lệnh gọi này càng không đáng tin.
- Nếu `Loader reference cleared: false`, chưa đủ kết luận leak: có thể chưa có chu kỳ GC phù hợp, JVM/JIT còn giữ reference tạm thời hoặc còn đường giữ loader mạnh. Cần kiểm tra thêm trước khi kết luận.
- Nếu weak reference đã clear, đó là dữ kiện hữu ích về reachability/GC của loader; còn câu hỏi **lớp cụ thể đã unload chưa** cần đối chiếu với log `class+unload` và đúng class loader.

Với code thử nghiệm khác dùng thread pool, listener, `ThreadLocal`, static cache hoặc framework registry, các tham chiếu mạnh vẫn có thể giữ instance, `Class<?>` hoặc loader; nếu vậy event unload không xảy ra dù đã gọi `close()`. Trong ứng dụng thực, phải giải phóng lifecycle hoàn chỉnh rồi quan sát **nhiều chu kỳ** trong điều kiện tải thích hợp.

## 6. Phân tích thời gian với GC và metaspace

Khi thấy class unload, nên hỏi thêm **GC nào diễn ra gần thời điểm đó**. Ví dụ:

```bash
java -Xlog:class+unload=info,gc=info:stdout:time,uptime,pid,level,tags -cp . UnloadTrace
```

Dùng cùng log output và decorator nhất quán để so thời điểm. Lưu ý GC log có thể nhắc một “Pause”, “Concurrent Cycle” hoặc giai đoạn khác tùy collector; **không được mặc định mọi GC sẽ unload mọi lớp đủ điều kiện**. Đừng suy từ mỗi dòng “GC” rằng unload chắc chắn đã thực hiện.

Nếu phải điều tra metaspace, có thể sử dụng những tín hiệu bổ trợ như:

```bash
jcmd <pid> VM.classloader_stats
jcmd <pid> VM.metaspace
jcmd <pid> help
```

`<pid>` là placeholder thay bằng PID thực tế. Các lệnh `jcmd` yêu cầu quyền attach và JDK phù hợp. Chúng cung cấp snapshot/thống kê, **không thay thế event log mang tên lớp**. Dung lượng metaspace committed/reserved còn phụ thuộc allocator, chính sách tái sử dụng và những lớp khác đang nạp, nên **không giảm** sau unload cũng chưa chứng minh bị giữ class.

Khi log quá lớn, lọc theo dòng `[class,unload]` và tên class/loader mục tiêu (nếu thông tin loader có trong bản JVM). Tuy vậy, nên **giữ bản log gốc** cùng PID, timestamp, cờ JVM và artifact version, để không mất mốc load/init/GC liên quan.

## 7. Cách đọc bằng chứng theo các tình huống

| Quan sát được | Có thể khẳng định | Chưa thể khẳng định |
|---|---|---|
| `[class,load]` xuất hiện cho `com.example.Plugin` | JVM đã ghi nhận sự kiện nạp lớp này | `<clinit>` đã chạy |
| `[class,init]` xuất hiện cho lớp mục tiêu | JVM bắt đầu/thực hiện quy trình initialization cho lớp | Class đã unload sau đó |
| `[class,unload]` nêu đúng lớp/loader | JVM đã ghi nhận unload tại thời điểm log | Ứng dụng không có leak nào khác |
| Có log GC sau thao tác dispose plugin | JVM có hoạt động GC được ghi nhận | Lớp plugin chắc chắn được unload |
| Không thấy `[class,unload]` sau một lần `System.gc()` | Trong dữ liệu quan sát không ghi nhận unload phù hợp | Đây chắc chắn là class-loader leak |
| Không thấy `[class,init]` khi in compile-time constant | Đây phù hợp quy tắc constant-variable không yêu cầu init | Class chưa từng được nạp |
| Hai event init cùng binary name | Có ít nhất hai event liên quan tên đó ở log | Cùng một runtime class đã init hai lần; cần kiểm tra loader identity |

**Thứ tự chữ in stdout và log có thể bị ảnh hưởng bởi buffering, nhiều thread và việc dùng file output.** Khi cần phân tích timeline chính xác, ưu tiên timestamp/uptime của log, ghi mốc ứng dụng cùng clock, cân nhắc đồng bộ nguồn thời gian và cấu hình asynchronous logging. Không suy ra thứ tự nhân quả tuyệt đối chỉ từ thứ tự xuất hiện khi trộn stdout/stderr/file.

## 8. Quy trình chẩn đoán có thể áp dụng trong dự án

1. **Đặt câu hỏi cụ thể:** “Lớp đã được load nhưng chưa init?”, “Plugin có nhiều lần init dưới loader khác nhau?”, hay “Sau khi unload logic, class loader cũ có được GC và các class đã unload?”.
2. **Bật tag tối thiểu trước sự kiện cần bắt:** `class+load` cho load, `class+init` cho init, `class+unload` cho unload; thêm `gc` khi cần quan hệ thời gian. Nếu tag chỉ bật sau sự kiện, log không tái tạo dữ liệu quá khứ.
3. **Lưu danh tính môi trường:** JDK/vendor, collector, flags, PID, ứng dụng/build version, classpath/module path, loại loader, mốc load/redeploy. Trong hệ thống nhiều process, xác định đúng PID trước khi so.
4. **Tạo thao tác có kiểm soát:** nạp class, gọi static API, load plugin, dispose plugin. Với unload, bỏ strong reference và đủ cửa sổ quan sát; tránh hiểu một lần `System.gc()` là điều kiện bắt buộc.
5. **Đọc các sự kiện theo đúng tag và đúng class identity.** Nếu cùng class name có nhiều loader, đừng gom tất cả vào một thực thể; đối chiếu nguồn class và loader khi JVM phát ra thông tin đó.
6. **Tìm bằng chứng bổ sung nếu cần kết luận nguyên nhân:** class load source, `Class.getClassLoader()`, thống kê loader, GC roots, metaspace, heap dump/JFR theo mức độ phù hợp.
7. **Kết luận theo dữ liệu:** “đã thấy unload class X lúc T” mạnh hơn “metaspace có vẻ giảm”; “chưa có event trong cửa sổ quan sát” khác “chắc chắn leak”.

### Quan sát hoặc thay đổi logging của JVM đang chạy

Trên HotSpot có thể dùng diagnostic command `VM.log` qua `jcmd`, nhưng chỉ có hiệu lực cho **sự kiện từ thời điểm cấu hình được bật trở đi**:

```bash
jcmd <pid> help VM.log
jcmd <pid> VM.log list
```

Tùy phiên bản/runtime, dùng cú pháp hiển thị trong `help VM.log` để bật hoặc đổi output/selection. Nên bật logging ngay từ lúc khởi động cho thí nghiệm tái hiện đáng tin cậy; đừng cố suy luận một lần init đã xảy ra trước khi bật log.

## 9. Lỗi thường gặp khi thiết lập và diễn giải logging

**1. Chỉ bật `class+load` rồi kết luận trạng thái init.** Hai log tag đo hai sự kiện khác nhau. Dùng `class+init` cùng phép thử active use.

**2. Dùng `-Xlog:class=info` thay cho `class+init=info`.** Chọn tag chính xác; dấu `+` kết hợp nhiều tag, dấu `,` tách nhiều selection.

**3. Dùng `-verbose:class` rồi cho rằng đã log initialization.** Theo tài liệu JDK 17, shortcut này bao phủ class loading và unloading, không thay tag init.

**4. Tắt log hoặc bật sau khi lớp đã init.** JVM thông thường không chạy lại `<clinit>` của cùng runtime class để phục vụ logging. Nếu cần lặp lại từ đầu, chạy JVM mới hoặc thử nghiệm với defining loader mới.

**5. Cho rằng class trùng tên tương đương cùng class.** Class identity dựa trên binary name và defining loader; plugin loader mới có thể định nghĩa cùng tên với class loader cũ.

**6. Nhầm việc không thấy unload với leak đã được chứng minh.** Class unloading phụ thuộc reachability, collector và thời điểm thu gom. Bằng chứng thiếu có thể do tag/level/output, thời gian quan sát, hoặc loader vẫn có đường strong reference hợp lệ.

**7. Gộp log class với GC và kết luận từ một dòng.** GC log chỉ nói về GC; cần event class+unload hoặc bằng chứng loader/GC roots phù hợp.

**8. Không lưu đầy đủ log metadata.** Khi phân tích nhiều JVM, các mốc `[0.100s]` đều tính từ uptime riêng của process; ghép hai process chỉ bằng uptime sẽ gây sai thứ tự. Kết hợp PID, wall time, JDK flags và bản dựng.

**9. Dùng `class*=trace` trên production dài ngày không kiểm soát dung lượng.** Logging rộng có overhead, tăng I/O và gây áp lực lưu trữ. Bật đúng tổ hợp/level, dùng rotation và giới hạn thời gian thu thập.

**10. Đọc log load source rồi cho rằng đó là defining loader.** `source` cho biết nguồn bytes ở ngữ cảnh log; muốn khẳng định class identity cần đối chiếu loader. Với plugin/class loader tùy biến, xác minh `Class.getClassLoader()` và cơ chế delegation.

## 10. Bài luyện tập và đáp án

**Câu 1.** Sau `Class.forName("InitTrace$Target", false, loader)` đã thấy `[class,load]` nhưng chưa thấy `[class,init]`. Đây có phải lỗi?  
**Đáp án:** Không. Đây là hành vi phù hợp với yêu cầu load mà chưa initialize. Đọc `Target.counter` hoặc một active use khác mới tạo điều kiện init.

**Câu 2.** Vì sao đọc `static final int CONSTANT = 7` không nhất thiết gây init?  
**Đáp án:** `CONSTANT` là constant variable được biểu thức hằng compile-time; caller có thể dùng giá trị inline mà không phải truy cập field runtime.

**Câu 3.** `-Xlog:class+load=info,class+init=info,class+unload=info` có nghĩa JVM tự động thực hiện loading/init/unloading không?  
**Đáp án:** Không. Đây là **cấu hình quan sát** những sự kiện khi JVM thực hiện chúng, không phải lệnh cưỡng bức lifecycle.

**Câu 4.** Sau `URLClassLoader.close()` và `System.gc()` không thấy `[class,unload]`. Kết luận được gì?  
**Đáp án:** Chưa quan sát được unload trong cửa sổ đó; cần xác minh tham chiếu mạnh, cấu hình GC, log, thời điểm và loader identity trước khi nói leak.

**Câu 5.** Khi chẩn đoán cùng tên class từ hai plugin loader, thông tin nào giúp tránh nhầm?  
**Đáp án:** Xác định defining loader, nguồn class, PID, version và timeline các sự kiện; binary name đơn lẻ không đủ để nhận diện runtime class.

## Nguồn tham chiếu chính thức

- [Oracle JDK 17 `java` command / Unified Logging / legacy flags mapping](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): cú pháp `-Xlog`, tag/level/output, `TraceClassInitialization → class+init` và `-verbose:class`.
- [Java Language Specification 17 — chương 12, Execution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): `12.4.1` quy định thời điểm class/interface được initialize, `12.4.2` quy trình chi tiết, `12.7` về unloading.
- [Java SE 17 — `Class.forName`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#forName(java.lang.String,boolean,java.lang.ClassLoader)): tham số `initialize` và hành vi của reflection.
- [Java SE 17 — `URLClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): vòng đời loader và `close()`.
- [JDK 17 — `jcmd` manual](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `VM.log`, `VM.classloader_stats` và `VM.metaspace` cho phân tích runtime.
