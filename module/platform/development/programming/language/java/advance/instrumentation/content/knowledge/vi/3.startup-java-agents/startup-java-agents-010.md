# Thực hành: agent ghi dấu mốc để quan sát thứ tự khởi động JVM

## Mục tiêu và giới hạn thí nghiệm

Trong Java Instrumentation, một **startup agent** là JAR có entry point `premain`, được JVM nhận qua tùy chọn `-javaagent`. Đây là cách đơn giản nhất để quan sát **thời điểm agent bắt đầu và kết thúc** so với phương thức `main` của ứng dụng. Thí nghiệm này tạo một agent chỉ in các dòng mốc; nó **không đăng ký `ClassFileTransformer`, không thay đổi bytecode, không attach vào JVM đang chạy**.

Sau bài này, bạn có thể:

- Viết đúng phương thức `premain(String, Instrumentation)` và đóng gói agent với thuộc tính `Premain-Class`.
- Biên dịch, chạy cùng một ứng dụng **có** và **không có** startup agent bằng JDK 17+.
- Phân biệt thời điểm khởi tạo class agent, chạy `premain`, khởi tạo class ứng dụng, gọi `main`, và khởi tạo một class khi được dùng lần đầu.
- Tự kiểm chứng thứ tự của **hai lần khai báo `-javaagent`**, kể cả khi trỏ đến cùng JAR.
- Giải thích chính xác những gì dấu mốc chứng minh được và những gì chúng **không** đo được.

> Kết luận cần chứng minh bằng thực nghiệm: khi dùng `-javaagent`, JVM gọi `premain` của các agent theo **thứ tự xuất hiện trên dòng lệnh**, sau khi JVM khởi tạo đủ để chạy Java code và **trước khi** gọi `main` của ứng dụng. Đây **không** phải dấu mốc bắt đầu của toàn bộ JVM hay bằng chứng rằng không class/JVM subsystem nào đã được tải trước agent.

## 1. Startup agent đi vào JVM như thế nào?

Một invocation điển hình:

~~~text
java -javaagent:path/to/agent.jar=phase=boot -cp path/to/app example.app.StartupOrderDemo
     |_____________________________|              |____________________________|
             tùy chọn JVM                               chương trình Java
~~~

- `-javaagent:<jarpath>[=<options>]` là tùy chọn của **JVM**: phần `jarpath` trỏ đến JAR chứa agent; chuỗi sau dấu `=` (nếu có) được chuyển nguyên vẹn đến tham số `agentArgs` của `premain`.
- Manifest chính bên trong JAR phải có `Premain-Class: <tên.class.đầy.đủ>`. JVM tải agent class rồi gọi **`public static void premain(String, Instrumentation)`**, hoặc dạng một tham số `premain(String)` khi không có dạng hai tham số phù hợp.
- `premain` phải **trở về bình thường** để quá trình startup tiếp tục. Nếu JVM không tải được agent, không tìm thấy entry point phù hợp, hoặc `premain` ném lỗi chưa xử lý, ứng dụng có thể không tới `main`.
- `Instrumentation` cung cấp API làm việc với class; thí nghiệm chỉ kiểm tra có nhận được đối tượng này và in dấu mốc, không dùng các tính năng biến đổi class.

Cần phân biệt với `agentmain`: đó là entry point liên quan đến agent được khởi động trong một JVM đã chạy (qua cơ chế attach khi được hỗ trợ). Dùng `-javaagent` ở dòng lệnh sẽ gọi **`premain`**, không gọi `agentmain`.

### Những mốc cần quan sát

~~~text
JVM khởi động và chuẩn bị runtime
    │
    ├─ tải/khởi tạo StartupMarkerAgent
    │      └─ [AGENT] class initialized
    ├─ gọi premain(agentArgs, instrumentation)
    │      ├─ [AGENT] premain begin
    │      ├─ [AGENT] options=...
    │      ├─ [AGENT] instrumentation available=true
    │      └─ [AGENT] premain end
    │
    ├─ khởi tạo StartupOrderDemo trước khi thực thi main
    │      └─ [APP] class initialized
    └─ gọi StartupOrderDemo.main(...)
           ├─ [APP] main begin
           ├─ khởi tạo Work khi new Work()
           ├─ [WORK] constructor
           └─ [APP] main end
~~~

Sơ đồ diễn tả **các dấu mốc do ví dụ này tạo ra**, không phải bản đồ đầy đủ mọi hoạt động class loading/class initialization bên trong JVM. Đặc biệt, `ClassLoader` có thể **tải** một class trước khi nó được **khởi tạo** (chạy `<clinit>`). Chỉ in từ static initializer không xác định thời điểm class được tải.

## 2. Chuẩn bị dự án nhỏ không cần framework

Yêu cầu: **JDK 17 hoặc mới hơn** với các lệnh `java`, `javac` và `jar` trong `PATH`. Kiểm tra:

~~~bash
java -version
javac -version
jar --version
~~~

Tạo cấu trúc thư mục sau (tên file, package và đường dẫn phải khớp):

~~~text
startup-agent-lab/
├── manifest.mf
├── src/
│   ├── agent/
│   │   └── example/
│   │       └── agent/
│   │           └── StartupMarkerAgent.java
│   └── app/
│       └── example/
│           └── app/
│               └── StartupOrderDemo.java
└── build/                        # được tạo khi biên dịch
    ├── agent/
    ├── app/
    └── startup-marker-agent.jar
~~~

Hãy chạy các lệnh còn lại từ thư mục gốc `startup-agent-lab/`.

### File 1 — agent chỉ ghi mốc

`src/agent/example/agent/StartupMarkerAgent.java`:

~~~java
package example.agent;

import java.lang.instrument.Instrumentation;

public final class StartupMarkerAgent {
    static {
        System.out.println("[AGENT] class initialized");
    }

    private StartupMarkerAgent() {
        // Không cần tạo instance: JVM gọi premain dạng static.
    }

    public static void premain(String agentArgs, Instrumentation instrumentation) {
        System.out.println("[AGENT] premain begin");
        System.out.println("[AGENT] options=" + agentArgs);
        System.out.println("[AGENT] instrumentation available=" + (instrumentation != null));
        System.out.println("[AGENT] premain end");
    }
}
~~~

**Giải thích từng dấu mốc:**

1. `[AGENT] class initialized` được in khi lớp `StartupMarkerAgent` được **khởi tạo** trước khi gọi phương thức static `premain`. Static initializer thuộc vòng đời class; nó không phải chính `premain`.
2. `premain begin` chứng tỏ JVM đã chuyển quyền điều khiển vào callback khởi động của agent.
3. `options=...` xác nhận JVM đưa đối số sau dấu `=` của `-javaagent` vào một **String**. JVM không tự parse thành map các cặp key/value.
4. `instrumentation available=true` xác nhận chữ ký hai tham số nhận đối tượng `Instrumentation` trong lần khởi động hợp lệ; nó **không** nói rằng class nào đã được instrument.
5. `premain end` chứng tỏ agent hoàn thành việc in mốc; sau đó phương thức trả về và JVM mới tiếp tục vào `main`.

Agent không gọi `instrumentation.addTransformer(...)`, `retransformClasses(...)`, `redefineClasses(...)` hay tạo thread. Nhờ vậy, thứ tự dòng in có ít yếu tố nhiễu.

### File 2 — ứng dụng tạo các mốc đối chiếu

`src/app/example/app/StartupOrderDemo.java`:

~~~java
package example.app;

public final class StartupOrderDemo {
    static {
        System.out.println("[APP] class initialized");
    }

    public static void main(String[] args) {
        System.out.println("[APP] main begin");
        new Work();
        System.out.println("[APP] main end");
    }

    private static final class Work {
        static {
            System.out.println("[WORK] class initialized");
        }

        Work() {
            System.out.println("[WORK] constructor");
        }
    }
}
~~~

Các dấu mốc nằm ở **ba giai đoạn khác nhau**: static initializer của class chứa `main`; chính thân `main`; static initializer và constructor của `Work`. `new Work()` là chỗ đầu tiên ứng dụng chủ động dùng `Work`, nên sẽ kích hoạt khởi tạo class `Work` trước khi chạy constructor của nó. Mỗi lần chạy lệnh `java` ở đây là một **tiến trình JVM mới**, vì thế các static initializer có cơ hội chạy lại khi chạy lần tiếp theo.

### File 3 — manifest nhận diện startup agent

`manifest.mf` (tạo file văn bản UTF-8, kết thúc bằng dòng trống):

~~~text
Manifest-Version: 1.0
Premain-Class: example.agent.StartupMarkerAgent

~~~

`Premain-Class` phải là **binary name** của class agent, bao gồm package, chứ không phải tên file `.java` hoặc `.class`. Đây là thông tin JVM đọc trong JAR agent để xác định phương thức cần gọi. Không đặt nhầm `Main-Class` vào chỗ của `Premain-Class`. Thí nghiệm không yêu cầu `Can-Redefine-Classes`, `Can-Retransform-Classes` hay các quyền instrumentation khác.

## 3. Biên dịch và đóng gói JAR

Trên macOS/Linux (Bash hoặc shell POSIX), từ thư mục gốc dự án:

~~~bash
mkdir -p build/agent build/app

javac --release 17 -d build/agent \
  src/agent/example/agent/StartupMarkerAgent.java

javac --release 17 -d build/app \
  src/app/example/app/StartupOrderDemo.java

jar --create --file build/startup-marker-agent.jar \
  --manifest manifest.mf -C build/agent .
~~~

Trên Windows PowerShell, thực hiện các lệnh tương đương:

~~~powershell
New-Item -ItemType Directory -Force -Path build/agent, build/app | Out-Null

javac --release 17 -d build/agent src/agent/example/agent/StartupMarkerAgent.java
javac --release 17 -d build/app src/app/example/app/StartupOrderDemo.java

jar --create --file build/startup-marker-agent.jar --manifest manifest.mf -C build/agent .
~~~

`--release 17` chọn mức tương thích nguồn/API/class file của Java 17; dùng JDK 21 chạy những lệnh này vẫn được. Tùy chọn `-d` đặt bytecode vào thư mục đích theo package. Với `jar ... -C build/agent .`, JAR phải chứa `example/agent/StartupMarkerAgent.class` và `META-INF/MANIFEST.MF`. Kiểm tra danh sách:

~~~bash
jar --list --file build/startup-marker-agent.jar
~~~

Nếu lệnh `jar` báo không thấy file/class, kiểm tra **đúng thư mục đang đứng**, đường dẫn `src/...`, và rằng compiler đã tạo `build/agent/example/agent/StartupMarkerAgent.class`. Không cần đưa app class vào agent JAR: app được cung cấp riêng qua `-cp build/app`.

## 4. Chạy không agent: lấy baseline

Chạy:

~~~bash
java -cp build/app example.app.StartupOrderDemo
~~~

**Stdout dự kiến chính xác**:

~~~text
[APP] class initialized
[APP] main begin
[WORK] class initialized
[WORK] constructor
[APP] main end
~~~

Đối chiếu: ứng dụng vẫn chạy bình thường; không có bất kỳ dòng `[AGENT]` nào vì agent JAR **chưa được truyền bằng `-javaagent`**. JVM khởi tạo class `StartupOrderDemo` trước khi thực thi `main`, rồi class `Work` được khởi tạo ở lần dùng chủ động đầu tiên trong đoạn code này.

## 5. Chạy với một startup agent

Trên macOS/Linux:

~~~bash
java -javaagent:build/startup-marker-agent.jar=phase=boot \
  -cp build/app example.app.StartupOrderDemo
~~~

Trên Windows PowerShell:

~~~powershell
java "-javaagent:build/startup-marker-agent.jar=phase=boot" -cp build/app example.app.StartupOrderDemo
~~~

**Stdout dự kiến chính xác**:

~~~text
[AGENT] class initialized
[AGENT] premain begin
[AGENT] options=phase=boot
[AGENT] instrumentation available=true
[AGENT] premain end
[APP] class initialized
[APP] main begin
[WORK] class initialized
[WORK] constructor
[APP] main end
~~~

Từ output này rút ra được ba nhận xét **trong phạm vi chương trình thử nghiệm**:

1. JVM khởi tạo class agent rồi gọi callback `premain` của nó. Chuỗi `phase=boot` là dữ liệu vào của agent, **không** tự làm Java thực hiện hành động có tên “boot”.
2. Agent kết thúc `premain` **trước** khi in `[APP] main begin`. Đây là đặc tính được API `java.lang.instrument` bảo đảm: `premain` của startup agent chạy trước `main` của ứng dụng.
3. Đoạn `[APP] class initialized` xuất hiện trước dòng `main begin`, nhưng **sau** các mốc agent trong **ví dụ cụ thể** vì agent không chủ động tải/khởi tạo class ứng dụng. Trong hệ thống lớn, code của agent có thể tự tải class khác trong `premain`; không được suy ra quy tắc “mọi `<clinit>` của ứng dụng đều chạy sau premain” từ một log đơn lẻ.

Dùng một tiến trình đơn, một thread, các `System.out.println` liên tiếp lên cùng `System.out` khiến phép thử dễ đọc. Các log từ JVM, native runtime, thư viện khác hoặc `System.err` có thể xen giữa và không phải mốc do chương trình này phát ra.

## 6. Thử hai startup agent để kiểm chứng thứ tự trên dòng lệnh

Đặc tả cho phép lặp tùy chọn `-javaagent` và **cho phép dùng cùng một agent JAR nhiều lần**. Không cần viết agent thứ hai: chạy chính JAR vừa tạo với hai chuỗi options khác nhau.

macOS/Linux:

~~~bash
java -javaagent:build/startup-marker-agent.jar=first \
  -javaagent:build/startup-marker-agent.jar=second \
  -cp build/app example.app.StartupOrderDemo
~~~

Windows PowerShell:

~~~powershell
java "-javaagent:build/startup-marker-agent.jar=first" "-javaagent:build/startup-marker-agent.jar=second" -cp build/app example.app.StartupOrderDemo
~~~

**Stdout dự kiến**:

~~~text
[AGENT] class initialized
[AGENT] premain begin
[AGENT] options=first
[AGENT] instrumentation available=true
[AGENT] premain end
[AGENT] premain begin
[AGENT] options=second
[AGENT] instrumentation available=true
[AGENT] premain end
[APP] class initialized
[APP] main begin
[WORK] class initialized
[WORK] constructor
[APP] main end
~~~

Hai lời gọi `premain` xảy ra theo **thứ tự `first` rồi `second`**. Dòng `[AGENT] class initialized` chỉ có **một lần** trong thí nghiệm: cùng một agent class được nạp bởi system class loader trong cùng tiến trình, và Java chỉ khởi tạo một class identity một lần. Không có hai đối tượng `StartupMarkerAgent`; `premain` là phương thức static và được JVM gọi hai lần theo hai khai báo agent.

Để kiểm chứng điều này không phải do sort theo tên, **đảo thứ tự** hai tùy chọn:

~~~bash
java -javaagent:build/startup-marker-agent.jar=second \
  -javaagent:build/startup-marker-agent.jar=first \
  -cp build/app example.app.StartupOrderDemo
~~~

Trên PowerShell, có thể dùng cùng câu lệnh một dòng và đổi `first`/`second` trong hai tham số được đặt trong dấu nháy kép. Output agent khi đó bắt đầu bằng `options=second` rồi mới đến `options=first`; toàn bộ mốc ứng dụng vẫn nằm sau các lời gọi `premain`.

**Điều được bảo đảm:** thứ tự gọi `premain` theo các khai báo startup agent và việc mỗi `premain` phải trả về trước khi launcher tiếp tục vào ứng dụng. **Điều không được bảo đảm:** thứ tự mọi class loading, thread phụ, JIT compilation, hay log phát ra từ công cụ khác. Nếu một `premain` tạo thread bất đồng bộ hoặc agent khác biến đổi class, các mốc do thread/callback đó sinh ra có thể xen kẽ.

## 7. Đọc kết quả đúng ở tầng JVM

### `-javaagent` không đồng nghĩa với chuyển đổi bytecode

Việc nhận `Instrumentation` chỉ cho biết JVM cung cấp API để agent *có thể* instrumentation. Ví dụ **không hề** đăng ký transformer, không đổi tên class, không sửa method, không cấy probe vào mã ứng dụng. Dòng `[WORK] constructor` đến từ **mã ứng dụng vốn có**, không phải do agent chèn vào.

Nếu mục tiêu chỉ quan sát thời điểm startup, ghi log ngay trong `premain` là đủ. Đừng làm thí nghiệm phức tạp bằng `ClassFileTransformer` hoặc attach API trước khi đã hiểu mốc này.

### Load, initialize và execute là các pha khác nhau

- **Loading:** JVM/class loader tìm và định nghĩa class. Không thể dùng một static initializer để chứng minh khoảnh khắc class bắt đầu được tải.
- **Initialization:** thực hiện khởi tạo class (tương ứng cơ chế `<clinit>` khi có công việc static). `[AGENT] class initialized`, `[APP] class initialized`, `[WORK] class initialized` là mốc ở pha này.
- **Execution:** thực thi callback `premain`, `main` hoặc constructor `Work()`. Constructor không phải class initializer.

Trong ứng dụng nhiều module, class loader riêng, logger async hoặc nhiều thread, log thực tế không nhất thiết có mọi mốc giống chương trình minh họa. Tránh kết luận rằng agent chạy *trước khi JVM tồn tại*, hoặc rằng JVM chưa load một class nào trước `premain`.

### Dấu mốc và thời gian tuyệt đối

Các nhãn trên xác nhận **thứ tự tương đối**, không đo thời gian startup từ lúc hệ điều hành tạo process. Nếu cần đo độ trễ, lấy mốc thời gian trong cùng JVM và tính chênh lệch; `System.nanoTime()` chỉ hữu ích để tính **duration** giữa các lần đọc, không phải timestamp wall-clock hoặc thời điểm bắt đầu JVM. Thực nghiệm hiện tại cố ý giữ log ngắn, dễ so sánh và có output dự đoán được.

## 8. Lỗi thường gặp và cách kiểm tra

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Failed to find Premain-Class manifest attribute` | Agent JAR thiếu hoặc sai `Premain-Class` | Kiểm tra `manifest.mf`, build lại JAR với `--manifest manifest.mf`; class name phải đúng package |
| `ClassNotFoundException`/`NoClassDefFoundError` cho agent | Đóng gói sai package hoặc thiếu dependency | Kiểm tra `jar --list --file ...` có `example/agent/StartupMarkerAgent.class` |
| Agent load được nhưng báo phương thức `premain` không hợp lệ | Sai tên, không `public static`, sai chữ ký | Dùng đúng `public static void premain(String, Instrumentation)` |
| JVM dừng trước dòng `[APP] main begin` | Agent JAR lỗi hoặc `premain` ném exception chưa xử lý | Đọc stderr, chạy lại baseline không agent, sửa agent trước |
| `options=null` | Chạy `-javaagent:path.jar` **không có** `=...` | Truyền `=phase=boot` khi muốn đối chiếu chuỗi rõ ràng; giá trị null khi không truyền options là hợp lệ |
| Không xuất hiện mốc `[AGENT]` mà app vẫn chạy | Quên `-javaagent` hoặc đặt sai vị trí | Đặt tùy chọn **trước** tên main class hoặc trước `-jar <app>` |
| `Could not find or load main class ...` | `-cp` trỏ sai thư mục đã biên dịch | Dùng `-cp build/app example.app.StartupOrderDemo` |
| Mốc không được in đúng thứ tự khi tích hợp ứng dụng thật | Log từ nhiều thread, async logger hoặc stderr xen kẽ stdout | Lặp lại thử nghiệm đơn thread; phân biệt mốc ứng dụng/agent với log từ framework |

**Lưu ý về vị trí tham số:** trong câu lệnh `java`, tất cả tùy chọn JVM cần được đặt trước tên class chứa `main`. Chẳng hạn `java -cp build/app example.app.StartupOrderDemo -javaagent:...` **không bật agent**: phần sau tên main class trở thành đối số của `main(String[] args)`.

**Lưu ý manifest:** khoảng trắng sau dấu hai chấm và dòng kết thúc manifest có ý nghĩa theo định dạng JAR manifest. Khi sửa `manifest.mf`, hãy biên dịch/đóng gói lại; thay riêng file ở ngoài không thay đổi nội dung manifest đã nằm trong `.jar`.

## 9. Bài tập kiểm tra hiểu biết

1. **Bỏ `-javaagent`:** số dòng `[AGENT]` là bao nhiêu? **0**. Ứng dụng chạy baseline gồm 5 dòng mốc APP/WORK.
2. **Thêm `=trace` thay `=phase=boot`:** dòng nào thay đổi? Chỉ dòng chứa `[AGENT] options=...`; hành vi sample không đổi vì code chỉ in chuỗi đó.
3. **Lặp cùng JAR hai lần:** `premain` chạy mấy lần? **2** theo hai khai báo; static initializer của cùng agent class identity chỉ chạy **một** lần trong JVM đó.
4. **Đổi thứ tự `-javaagent`:** `first`/`second` xuất hiện theo thứ tự nào? Theo thứ tự được viết trên dòng lệnh, không theo alphabet.
5. **Thêm một lệnh `new Work()` nữa vào `main`:** `[WORK] class initialized` có in hai lần không? **Không** trong cùng JVM; constructor `Work()` in **hai lần** vì tạo hai instance.
6. **Từ output có thể khẳng định agent đã sửa bytecode không?** **Không.** Instrumentation API có sẵn nhưng agent không đăng ký transformer và không sửa mã.
7. **Có thể kết luận agent chạy trước mọi hoạt động nội bộ JVM không?** **Không.** JVM đã khởi tạo một phần runtime và có thể tải class trước `premain`; bảo đảm ở đây là trước ứng dụng `main`.

## 10. Checklist tự xác nhận

- [ ] Đang dùng JDK 17+, có `java`/`javac`/`jar`.
- [ ] Agent class có đúng tên, package và chữ ký `public static void premain(String, Instrumentation)`.
- [ ] `manifest.mf` khai báo `Premain-Class: example.agent.StartupMarkerAgent`.
- [ ] JAR chứa `example/agent/StartupMarkerAgent.class`.
- [ ] Baseline chỉ có các mốc `[APP]` và `[WORK]`.
- [ ] Có một `-javaagent`: tất cả mốc `[AGENT] premain ...` xuất hiện trước mốc `[APP] main begin`.
- [ ] Có hai `-javaagent`: các tùy chọn `first`/`second` được in đúng thứ tự command-line.
- [ ] Khi quan sát log, phân biệt class initialization, invocation `premain`, lời gọi `main` và constructor instance.

## Tài liệu chuẩn

- [Java SE 17 — Package java.lang.instrument, Starting an Agent from the Command-Line Interface](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): manifest `Premain-Class`, chữ ký `premain`, options, lỗi startup và thứ tự nhiều agent.
- [Java SE 21 — Package java.lang.instrument](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): đặc tả API agent; ví dụ cũng hoạt động trên JDK hiện đại.
- [Java SE 17 — JAR Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): cách tạo JAR và thêm manifest.
- [Java SE 17 — Java Launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): vị trí tùy chọn `-javaagent`/`-cp` so với main class.
- [JLS 17 §12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4): quy tắc class initialization, dùng để giải thích các mốc `class initialized`.
