# Giới hạn của cô lập class loader đối với trạng thái và quyền của tiến trình

## 1. Class loader cô lập được điều gì?

Trong hệ thống Java hỗ trợ plugin hoặc nạp thư viện động, ứng dụng có thể sử dụng nhiều \`ClassLoader\` để nạp các thư viện khác phiên bản. Mỗi class trong JVM được nhận diện bởi **tên nhị phân và defining class loader**. Vì vậy, hai loader khác nhau có thể định nghĩa hai class cùng tên, chẳng hạn \`com.vendor.JsonCodec\`, mà hai class đó không có cùng identity.

Cơ chế này giải quyết một nhóm vấn đề thực tế:

- Plugin A có thể dùng phiên bản thư viện \`codec\` khác plugin B.
- Các class nội bộ của plugin không cần nằm chung namespace với class nội bộ của host.
- Khi thiết kế đúng, host có thể chỉ chia sẻ một API SPI ổn định còn các implementation sử dụng dependency riêng.
- Có thể nạp một phiên bản plugin mới bằng loader khác và bỏ tham chiếu loader cũ khi vòng đời của plugin kết thúc.

Nhưng **classloader không tạo tiến trình mới, vùng nhớ hệ điều hành mới hay sandbox quyền**. Mọi code Java chạy trong cùng một JVM vẫn dùng chung nhiều tài nguyên quan trọng. Classloader chỉ là ranh giới về cách định danh và tìm class; nó không tự kiểm soát quyền đọc file, tạo thread, gọi mạng, lấy environment variables hoặc dừng JVM.

## 2. Mô hình ranh giới: namespace khác, tiến trình vẫn chung

\`\`\`text
                       Một tiến trình JVM
+------------------------------------------------------------+
| Heap, GC, system properties, System.out, process resources |
| Native libraries, threads, sockets, files, environment    |
|                                                            |
|  Host / parent classloader                                 |
|    com.example.api.Plugin       <-- API dùng chung         |
|                                                            |
|  Plugin A loader              Plugin B loader              |
|    com.vendor.Codec v1          com.vendor.Codec v2         |
|    com.example.a.PluginA        com.example.b.PluginB       |
|                                                            |
|  Namespace class riêng != memory/process/security riêng   |
+------------------------------------------------------------+
\`\`\`

Trong sơ đồ, hai bản \`Codec\` có thể cùng tên nhưng khác class identity. Dù vậy, cả A và B vẫn là code chạy trong một tiến trình JVM. Nếu một plugin gọi \`System.setProperty(...)\` hoặc sửa một object do host chia sẻ, plugin khác có thể thấy thay đổi đó.

Một hiểu lầm phổ biến là “hai classloader khác nhau thì static state hoàn toàn độc lập”. Phát biểu chính xác hơn: **trường static thuộc về class runtime được xác định bởi cả tên class và defining loader**. Nếu hai loader thực sự định nghĩa hai bản class khác nhau, mỗi bản có static fields riêng. Nhưng static state của các class được nạp bởi parent/shared loader vẫn là chung. Ngoài ra, các biến static chỉ là một phần trạng thái của tiến trình.

## 3. Static state: tách được ở class riêng nhưng không tách ở class chung

Giả sử cả plugin A và plugin B có một class cùng tên \`plugin.Counter\`, và mỗi class được định nghĩa bởi loader riêng. Khi hai loader thực sự tạo hai runtime class khác nhau, hai trường \`Counter.value\` cũng riêng biệt.

Ngược lại:

\`\`\`java
// Class này do host/parent loader định nghĩa:
package com.example.host;

public final class SharedRegistry {
    public static final java.util.Map<String, String> VALUES =
            new java.util.concurrent.ConcurrentHashMap<>();

    private SharedRegistry() {}
}
\`\`\`

Nếu plugin A và B cùng nhìn thấy \`SharedRegistry\` của parent loader, cả hai thao tác trên **cùng một map**. \`ConcurrentHashMap\` giúp an toàn hơn trước truy cập đồng thời ở mức collection; nó không cung cấp quyền hạn hay ngăn plugin xóa/thay đổi giá trị của plugin khác.

Các dạng trạng thái dùng chung thường gặp:

| Nguồn trạng thái | Có được cô lập tự động theo classloader? | Vì sao |
| --- | --- | --- |
| Static field trên class do từng child loader định nghĩa | Có, giữa hai runtime class thực sự khác nhau | Runtime class identity gồm class name và defining loader |
| Static field trên class của parent loader | Không | Các plugin dùng cùng class được định nghĩa bởi parent |
| \`System.getProperties()\` | Không | Đây là properties toàn JVM |
| \`System.out\` / \`System.err\` | Không | Stream chuẩn của tiến trình |
| Heap object được host truyền cho plugin | Không | Cùng object reference |
| File, socket, database, cache ngoài tiến trình | Không | Quyền và kết nối phụ thuộc OS và cấu hình |
| Threads do plugin tạo | Không | Thread thuộc tiến trình; có thể sống lâu hơn vòng đời plugin |
| Thread context classloader | Không tự cô lập | Thread có context loader có thể tham chiếu plugin loader |

Ngay cả khi dependency được isolate hoàn toàn, plugin vẫn có thể phá vỡ dữ liệu được host chia sẻ qua API, hoặc làm cạn memory/CPU của JVM.

## 4. Ví dụ Java 17+: hai classloader, hai static counter, một System property

Ví dụ sau tạo một JAR plugin chứa class \`demo.plugin.Counter\`. Host nạp **cùng một JAR qua hai URLClassLoader riêng**, có parent là platform classloader để bản plugin không được parent/application loader nạp sẵn. Nó minh họa hai điều: static fields của class được định nghĩa ở mỗi loader là riêng, nhưng \`System\` properties là chung.

Cấu trúc thư mục:

\`\`\`text
demo/
  plugin/demo/plugin/Counter.java
  host/Host.java
\`\`\`

\`plugin/demo/plugin/Counter.java\`:

\`\`\`java
package demo.plugin;

public final class Counter {
    private static int count;

    public static int increment() {
        return ++count;
    }

    public static String loaderName() {
        return String.valueOf(Counter.class.getClassLoader());
    }
}
\`\`\`

\`host/Host.java\`:

\`\`\`java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class Host {
    public static void main(String[] args) throws Exception {
        URL pluginUrl = Path.of("plugin.jar").toAbsolutePath().toUri().toURL();
        ClassLoader parent = ClassLoader.getPlatformClassLoader();

        try (URLClassLoader loaderA =
                     new URLClassLoader(new URL[] {pluginUrl}, parent);
             URLClassLoader loaderB =
                     new URLClassLoader(new URL[] {pluginUrl}, parent)) {

            Class<?> classA = Class.forName(
                    "demo.plugin.Counter", true, loaderA);
            Class<?> classB = Class.forName(
                    "demo.plugin.Counter", true, loaderB);

            System.out.println("Same runtime class: " + (classA == classB));
            System.out.println("A counter: "
                    + classA.getMethod("increment").invoke(null));
            System.out.println("A counter: "
                    + classA.getMethod("increment").invoke(null));
            System.out.println("B counter: "
                    + classB.getMethod("increment").invoke(null));

            System.setProperty("demo.shared", "written-by-A");
            System.out.println("Shared property: "
                    + System.getProperty("demo.shared"));
        } finally {
            System.clearProperty("demo.shared");
        }
    }
}
\`\`\`

Từ thư mục \`demo\`, chạy trên shell bash (có \`javac\`, \`jar\`, \`java\`):

\`\`\`bash
mkdir -p out/plugin out/host
javac -d out/plugin plugin/demo/plugin/Counter.java
javac -d out/host host/Host.java
jar --create --file plugin.jar -C out/plugin .
java -cp out/host Host
\`\`\`

Output:

\`\`\`text
Same runtime class: false
A counter: 1
A counter: 2
B counter: 1
Shared property: written-by-A
\`\`\`

**Vì sao?** \`loaderA\` và \`loaderB\` cùng nhìn thấy bytecode nhưng mỗi loader tự định nghĩa \`demo.plugin.Counter\`, nên \`classA != classB\` và static counter riêng. Tuy nhiên \`System.setProperty\` ghi vào một bảng properties toàn JVM nên giá trị vẫn được đọc trong cùng tiến trình, bất kể loader nào thực hiện thao tác.

Trong ví dụ, host tự gọi \`System.setProperty\` để thể hiện tài nguyên chung. Nếu plugin gọi API này thì ảnh hưởng cũng là toàn JVM; classloader không chặn được. \`URLClassLoader.close()\` đóng khả năng truy cập tài nguyên JAR mở bởi loader, nhưng **không xóa các class đã nạp hoặc bảo đảm GC ngay lập tức**.

### Một lưu ý về parent delegation

Theo mô hình parent-first thông thường, nếu parent loader đã định nghĩa \`demo.plugin.Counter\`, yêu cầu load qua child có thể trả chính class của parent. Khi đó \`classA == classB\` có thể là \`true\`, và static field không được tách. Muốn cô lập dependency, cần thiết kế ranh giới package, classpath và parent delegation nhất quán. Không nên tự viết child-first loader toàn diện nếu chưa giải quyết package sealing, resource loading, protected packages, class identity và SPI API sharing.

## 5. Quyền tiến trình: cùng OS identity, không có sandbox mặc định

Mọi plugin chạy trong cùng JVM thông thường hoạt động với quyền mà tiến trình JVM đã có. Classloader không cấp một UID, user account, network namespace hay ACL riêng cho mỗi plugin.

Các khả năng ảnh hưởng toàn tiến trình có thể gồm:

- **Hệ thống file:** đọc/ghi dữ liệu mà tài khoản chạy JVM được phép truy cập.
- **Mạng:** mở kết nối hoặc socket nếu OS/container/network policy cho phép.
- **Environment/config:** đọc environment variables và system properties mà tiến trình thấy; sửa các system properties có thể ảnh hưởng code khác.
- **Tiến trình:** gọi các API để tạo process con, và trong một số ngữ cảnh có thể làm dừng JVM.
- **CPU, bộ nhớ và thread:** gây sử dụng tài nguyên lớn, treo hoặc ảnh hưởng GC của các plugin khác.
- **Native code:** gọi JNI/FFM/native library theo khả năng và cấu hình runtime; code native có thể làm hỏng bộ nhớ của toàn tiến trình.

Java Security Manager từng được dùng làm một phần kiểm soát quyền trong vài hệ thống cũ, nhưng không phải một giải pháp sandbox có thể dựa vào cho Java hiện đại. Security Manager đã bị vô hiệu hóa vĩnh viễn trong JDK 24; với Java 17 nó bị đánh dấu deprecated for removal. Không thiết kế bảo mật plugin mới dựa vào việc gắn Security Manager cho từng classloader.

**Hệ quả:** đối với plugin chưa tin cậy, cần cách ly ở mức tiến trình/OS/container/VM với quyền và giới hạn tài nguyên phù hợp. Một \`URLClassLoader\` riêng không thay thế các cơ chế đó.

## 6. Những đường chia sẻ trạng thái cần chú ý

### A. API hoặc singleton của host

Plugin thường cần tham chiếu API do host cung cấp, ví dụ interface \`PluginContext\` và \`Logger\`. Nếu host đưa cho plugin một object mutable chứa quyền truy cập database hoặc registry, plugin có thể thao tác qua object đó dù class của plugin được load riêng.

Để hạn chế rủi ro với **plugin tin cậy**, có thể thiết kế API hẹp, immutable snapshots, capability-style interfaces và validation ở boundary. Tuy nhiên điều này là **giới hạn theo kiến trúc ứng dụng**, không phải cơ chế ngăn code Java độc hại trong cùng tiến trình truy cập API khác.

### B. ThreadLocal và thread pools

\`ThreadLocal\` lưu giá trị theo **thread**, không theo classloader. Nếu host tái sử dụng một thread pool cho các plugin, dữ liệu ThreadLocal không được dọn có thể tồn tại qua nhiều tác vụ. Class được nạp bởi plugin và các object được tham chiếu bởi thread có thể làm loader không được GC.

Mẫu sử dụng ThreadLocal đúng thường cần \`try/finally\`:

\`\`\`java
private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

static void process(String id) {
    REQUEST_ID.set(id);
    try {
        doWork();
    } finally {
        REQUEST_ID.remove();
    }
}
\`\`\`

Đây là đoạn minh họa đặt trong một class có method \`doWork()\`; nó không phải chương trình độc lập. Trường static \`REQUEST_ID\` thuộc runtime class định nghĩa nó, nhưng dữ liệu ThreadLocal của thread và lifetime của thread có quan hệ rộng hơn việc đóng URLClassLoader.

### C. Thread context classloader (TCCL)

Nhiều framework và \`ServiceLoader.load(S.class)\` dùng thread context classloader để tìm providers. Plugin có thể thay \`Thread.currentThread().setContextClassLoader(...)\`; nếu không phục hồi, task sau trên cùng thread có thể vô tình dùng loader khác.

Mẫu phục hồi:

\`\`\`java
Thread thread = Thread.currentThread();
ClassLoader old = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    invokePlugin();
} finally {
    thread.setContextClassLoader(old);
}
\`\`\`

Đây là đoạn đặt trong method đã có \`pluginLoader\` và \`invokePlugin()\`. Nó giúp giữ tính đúng đắn của runtime host, không biến classloader thành sandbox.

### D. Shutdown hooks, listeners, caches và native libraries

Plugin có thể đăng ký shutdown hook, listeners, JMX MBean, scheduler, executor, driver hoặc cache ở các singleton do parent loader giữ. Nếu không unregister/close, các reference đó giữ plugin class/loader còn sống, gây memory leak và ảnh hưởng thao tác reload. Các thư viện JNI/native còn có rủi ro crash hoặc xung đột ở cấp JVM.

## 7. Đóng classloader không có nghĩa dừng plugin

\`URLClassLoader.close()\` chủ yếu giải phóng tài nguyên mà loader đã mở để nạp class/resources; nó không phải lệnh unload class hay dừng mọi thread của plugin.

Muốn gỡ plugin có kiểm soát, host cần contract vòng đời:

1. Ngừng nhận request mới vào plugin.
2. Đợi công việc đang thực thi kết thúc hoặc hủy theo timeout/policy.
3. Gọi \`close()\`/\`stop()\` của provider; đóng executor, file handles, sockets.
4. Unregister listeners, shutdown hooks, timers, drivers và các registry entries của host.
5. Khôi phục TCCL, dọn ThreadLocal và các reference mạnh ở host.
6. Đóng classloader, bỏ references và quan sát JVM có thể giải phóng loader hay không.

Việc bỏ reference tạo **điều kiện** để garbage collector thu hồi classloader và class metadata; không bảo đảm thời điểm GC hoặc unload ngay lập tức. Nếu có static reference từ shared parent class giữ object của plugin, loader vẫn có thể bị giữ lại.

## 8. Khi nào classloader đủ và khi nào cần tiến trình riêng?

| Mục tiêu | Classloader riêng | Process/container riêng |
| --- | --- | --- |
| Dùng hai phiên bản cùng thư viện | Thường phù hợp khi dependency tree được kiểm soát | Có thể, nhưng tốn chi phí hơn |
| Tránh xung đột tên class | Phù hợp với loader graph được thiết kế đúng | Có |
| Tách static field thuộc class plugin riêng | Có, nếu thực sự định nghĩa class riêng | Có vì heap khác nhau |
| Ngăn plugin thay \`System\` properties chung | Không | Có vì mỗi JVM có properties riêng |
| Ngăn plugin sử dụng CPU/memory quá mức | Không cung cấp quota | Có thể cấu hình quota ở OS/container |
| Giới hạn file/network theo plugin không tin cậy | Không | Có thể áp quyền OS/container/network |
| Tránh plugin crash native làm hỏng host | Không | Cô lập lỗi ở mức process, tùy môi trường |
| Unload plugin deterministically | Không | Dừng process là ranh giới rõ hơn |
| Plugin tin cậy có dependency khác phiên bản | Thường là lựa chọn hợp lý | Có thể không cần |

Lưu ý: process riêng cũng **không tự động bảo đảm an toàn**. Nếu chạy cùng user với cùng quyền đọc file, cùng mount và mạng mở, process vẫn có thể truy cập nhiều tài nguyên của host. Cần kết hợp user identity, filesystem permissions, resource limits, seccomp/AppArmor/SELinux hoặc network policy theo môi trường triển khai.

## 9. Kiến trúc plugin hai mức

Một thiết kế thực tế có thể dùng hai chế độ:

**Plugin tin cậy, cần hiệu năng gọi trực tiếp:**

\`\`\`text
Host JVM
  ├── Shared SPI API (parent loader)
  ├── Plugin A loader + private dependencies
  └── Plugin B loader + private dependencies
\`\`\`

Ở đây mục tiêu là dependency isolation, reload có kiểm soát và quản trị vòng đời. Chỉ chấp nhận JAR được tin cậy và kiểm soát nguồn phát hành.

**Plugin chưa tin cậy hoặc cần giới hạn lỗi/quyền:**

\`\`\`text
Host JVM
    |
    +---- IPC (HTTP/gRPC/stdin-stdout/message queue)
    |
Plugin process/container
    +---- restricted OS user
    +---- filesystem/network permissions
    +---- CPU/memory limits
\`\`\`

Ứng dụng phải xác thực/kiểm tra thông điệp IPC, giới hạn thời gian, dữ liệu đầu vào, kích thước payload và trạng thái khi plugin chết. Một process boundary tạo điều kiện cho ranh giới quyền và lỗi rõ ràng hơn, đồng thời thêm chi phí vận hành và giao tiếp.

## 10. Các lỗi thiết kế thường gặp

| Nhận định sai | Vấn đề thực tế | Sửa thế nào |
| --- | --- | --- |
| “Mỗi plugin loader là một sandbox” | Code vẫn chạy với quyền JVM | Dùng OS/process isolation cho plugin chưa tin cậy |
| “Static luôn riêng cho mọi plugin” | Class của parent/shared loader có static chung | Kiểm tra defining classloader của từng class |
| “Đóng loader tức là unload” | Thread, cache, registry giữ reference | Thiết kế stop/close và dọn reference |
| “Plugin không thể ảnh hưởng plugin khác” | Chia sẻ heap, process properties, tài nguyên và services | Giới hạn shared API; dùng process riêng nếu cần |
| “TCCL thuộc riêng plugin” | TCCL là trạng thái của thread | Khôi phục TCCL bằng finally |
| “Child-first chắc chắn cô lập mọi thứ” | API duplicate/class identity, package sealing, framework conflicts | Thiết kế parent delegation và API boundary |
| “Process riêng là an toàn tuyệt đối” | Process có thể vẫn có cùng OS permissions | Cấu hình quyền và resource quotas |

## 11. Checklist triển khai cô lập phụ thuộc an toàn

- [ ] Ghi rõ mục tiêu là **isolate dependency namespace** hay **isolate untrusted execution**.
- [ ] Giữ SPI API chung ở parent loader và kiểm tra \`Class<?> \` identity giữa host/provider.
- [ ] Kiểm soát version/dependency được load qua từng child loader.
- [ ] Xác định shared mutable objects, singletons, properties, thread pools và registry mà plugin nhìn thấy.
- [ ] Có lifecycle \`start/stop/close\`; dọn ThreadLocal, TCCL, listeners và executors.
- [ ] Không dựa vào classloader để kiểm soát quyền file/network/process.
- [ ] Khi plugin không tin cậy, chạy process/container với OS privileges tối thiểu và quotas phù hợp.
- [ ] Test hai phiên bản dependency cùng tên, test unload/reload và quan sát leak.
- [ ] Kiểm tra artifact đóng gói thực tế, đặc biệt khi shade/relocate hoặc có native libraries.

**Kết luận:** classloader là công cụ quan trọng để quản lý **danh tính class và cô lập phụ thuộc**. Nó không tách heap, thread, system properties, quyền OS hay lỗi native của plugin khỏi JVM host. Mỗi khi yêu cầu là bảo mật, giới hạn tài nguyên hoặc chịu lỗi mạnh, cần đưa ranh giới cô lập xuống cấp process/OS/container và vận hành nó như một thành phần riêng.
