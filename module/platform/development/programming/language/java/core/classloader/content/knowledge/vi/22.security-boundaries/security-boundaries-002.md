# Phân biệt cô lập không gian tên với cô lập quyền thực thi

## 1. ClassLoader riêng không có nghĩa là sandbox bảo mật

Java có thể dùng nhiều `ClassLoader` để nạp cùng một binary class name thành những runtime types khác nhau. Điều này giúp hệ plugin tổ chức dependencies, tránh xung đột version, hoặc thay implementation mà không khởi động lại toàn ứng dụng. Nhưng từ đó **không được suy ra** plugin có quyền file, mạng, CPU hoặc heap bị tách riêng.

Có hai câu hỏi hoàn toàn khác nhau:

- **Cô lập không gian tên (namespace isolation):** khi code yêu cầu `com.example.Widget`, ClassLoader nào định nghĩa class ấy? Hai plugins có thể có các bản `com.example.Widget` khác nhau không? Loader nào nhìn thấy resource/JAR nào?
- **Cô lập quyền thực thi (execution/permission isolation):** code plugin được phép đọc/ghi file gì, kết nối tới đâu, gọi native APIs, thay đổi shared state, tạo process hoặc tiêu thụ bao nhiêu CPU/memory?

Ví dụ sơ đồ:

~~~text
                  Host JVM Process
+-------------------------------------------------+
| Application ClassLoader: host + shared API      |
|                                                 |
| Plugin Loader A: class codec.Parser (version 1) |
| Plugin Loader B: class codec.Parser (version 2) |
|                                                 |
|  => A.Parser != B.Parser (runtime class identity)|
|                                                 |
|  SHARED EXECUTION AUTHORITY:                     |
|  * JVM process / OS user                         |
|  * Process filesystem / network permissions     |
|  * Heap, CPU, threads, file descriptors         |
|  * Shared JDK classes, System properties        |
+-------------------------------------------------+
~~~

**Tóm tắt:** ClassLoader là công cụ **tìm/định nghĩa lớp và quản lý namespace**. Nó **không tự tạo một identity OS mới hay chính sách permission riêng cho bytecode plugin**.

Bài thuộc nhóm *Ranh giới bảo mật*, tập trung phân biệt type isolation với quyền thực thi. Bạn sẽ thực hành Java 17+ chứng minh một plugin class được nạp riêng vẫn đọc được file thử nghiệm mà JVM process có quyền đọc và thay đổi được một JVM-wide system property. Sau đó sẽ xem SecurityManager, JPMS, process/container isolation, threat model và cách xây plugin boundary thực tế.

## 2. ClassLoader bảo đảm điều gì?

### 2.1. Runtime class identity gắn với defining loader

Với ordinary Java classes, một runtime type thường được xác định bởi:

~~~text
(binaryName, definingClassLoader)
~~~

Hai object loader khác nhau `L1` và `L2` có thể cùng định nghĩa tên `plugin.impl.Worker`:

~~~java
Class<?> a = loaderA.loadClass("plugin.impl.Worker");
Class<?> b = loaderB.loadClass("plugin.impl.Worker");

System.out.println(a.getName().equals(b.getName())); // có thể true
System.out.println(a == b);                           // có thể false
~~~

Đây là snippet minh họa, không phải chương trình độc lập: hai loader phải có đường tìm classes thích hợp. Nếu cả hai ủy quyền cho **cùng parent**, `a == b` có thể là `true` vì parent trả cùng class.

Để phân biệt việc **loader nào thực sự định nghĩa** class với loader được gọi, dùng:

~~~java
ClassLoader defining = a.getClassLoader();
~~~

Một child loader có thể là *initiating loader* của class do parent định nghĩa theo mô hình delegation. Không phải mọi lần `child.loadClass` đều làm child tự gọi `defineClass`.

### 2.2. Những nhu cầu ClassLoader giúp giải quyết

| Nhu cầu | Cơ chế hợp lý | Phần ClassLoader không giải quyết |
|---|---|---|
| Plugin A cần phiên bản `codec-v1`, B cần `codec-v2` | Loader riêng theo plugin, phân chia namespace | Không cấp hai quyền đọc file/network khác nhau |
| Host không compile phụ thuộc implementation | Parent-shared API + loader dành cho implementation | Không ngăn plugin gọi public Java APIs |
| Reload plugin | Tạo loader mới, bỏ reference tới loader cũ khi an toàn | Không đảm bảo dừng code/threads đang chạy |
| Tìm provider | `ServiceLoader` với loader/layer thích hợp | Không tự chặn provider truy cập OS |
| Giữ hai classes trùng binary name | Hai defining loaders khác nhau | Không tạo OS identities khác nhau |
| Tổ chức named modules | JPMS/ModuleLayer + loader mapping | Không tự giới hạn quyền CPU/memory/network |
| Tránh xung đột resources | Phân bố JAR paths và delegation | Không tạo isolation chống code cố ý phá host |

Một ClassLoader hữu ích cho **đóng gói, sự tương thích và class lifecycle**. Chính các ranh giới này không đủ chống plugin độc hại trong cùng process.

### 2.3. Lỗi `ClassCastException` không phải dấu hiệu security boundary

Nếu interface `plugin.api.Service` được host và plugin loaders định nghĩa thành hai runtime classes:

~~~text
HostLoader     -> plugin.api.Service#H
PluginLoader   -> plugin.api.Service#P
~~~

thì một implementation của `Service#P` không nhất thiết cast được sang `Service#H`. Lỗi type identity như vậy phản ánh **hai definitions khác nhau**, không có nghĩa plugin đã bị hạn chế đọc file hay dùng network.

Thiết kế API xuyên boundary nên cho parent loader định nghĩa **một bản interface/DTO chung**, còn implementation/private dependencies do loader con nạp. Kể cả khi API isolation đúng, permission isolation vẫn là vấn đề độc lập.

## 3. Quyền thực thi nằm ở đâu?

### 3.1. Một JVM process có quyền OS nhất định

Trong một ứng dụng chạy bằng service account, các threads của host và plugin cùng thực thi **trong cùng process**. Nếu không có policy cưỡng chế riêng, các file/socket/process APIs chịu quyền của process đó.

Ví dụ capability cần kiểm soát:

- File: đọc, tạo, ghi, xóa và duyệt đường dẫn.
- Network: kết nối ra Internet/nội mạng, lắng nghe port, DNS.
- Process/native: tạo process con, JNI/FFM khi khả dụng và được cho phép theo runtime.
- CPU/RAM/threads: sử dụng tài nguyên chung của JVM.
- Secrets: environment variables, secret files, credentials cấp cho process.
- Process-wide configuration: `System.setProperty`, global logging, shared registries.
- Shared objects: callbacks, static singletons từ class do parent định nghĩa, caches.

**Quyền đọc một path không suy ra quyền đọc mọi path.** OS, tài khoản và policy cụ thể quyết định mỗi thao tác. Nhưng **ClassLoader khác nhau tự nó không làm những quyền ấy khác nhau**.

### 3.2. Shared classes có state chung

Mỗi runtime class riêng có **static fields riêng**, kể cả hai classes có cùng binary name nhưng defining loaders khác nhau.

Ngược lại, các class của Java platform và shared API được nạp chung vẫn có state chung. `java.lang.System` là ví dụ dễ kiểm chứng: JVM system properties được chia sẻ giữa code của host và plugins trong cùng process.

~~~java
System.setProperty("example.flag", "changed");
System.out.println(System.getProperty("example.flag"));
~~~

Đoạn snippet minh họa này không tạo một map riêng cho từng plugin. Nếu cần state độc lập, hãy truyền một context riêng hoặc đưa plugin sang process riêng. Cũng đừng truyền secrets vào một shared context rồi hy vọng loader ngăn plugin đọc.

### 3.3. Một namespace khác không đồng nghĩa một principal khác

Trong thiết kế bảo mật, **principal/security identity** là đối tượng mà chính sách ủy quyền áp dụng, ví dụ một OS user, process sandbox identity hoặc authenticated service principal. **ClassLoader object** không đương nhiên là principal mà OS dùng để kiểm tra quyền.

~~~text
ClassLoader identity:  "Ai định nghĩa class này?"
OS identity:           "Process nào/user nào đang thao tác?"
Application authz:     "Caller này được thực hiện operation nào?"
~~~

Cần có **đường cưỡng chế thật** giữa code và resource. Gắn nhãn `SandboxClassLoader` hoặc chọn URL riêng không đủ để kernel chặn file operations.

## 4. Ví dụ Java 17+ chạy độc lập: hai loader, một process

Ví dụ được giới hạn an toàn: host tạo **một file tạm chỉ chứa chuỗi MARKER_OK**, truyền `Path` cho plugin và sau đó xóa file. Plugin A chỉ đọc file này và sửa **một system property có tên riêng dành cho demo**; plugin B đọc lại property. Không yêu cầu internet, công cụ bên ngoài hoặc quyền đặc biệt.

### 4.1. Cấu trúc dự án

~~~text
demo/
├── src/
│   ├── plugin/
│   │   └── example/plugin/Probe.java
│   └── host/
│       └── BoundaryDemo.java
└── build/
    ├── plugin/
    │   └── example/plugin/Probe.class
    └── host/
        └── BoundaryDemo.class
~~~

Khi chạy chỉ thêm `build/host` vào application classpath. **Không đưa `build/plugin` vào `-cp`**, vì nếu parent tìm được `Probe` trước thì hai child loaders có thể nhận cùng class và phép so identity không còn chứng minh mong muốn.

### 4.2. Tệp `src/plugin/example/plugin/Probe.java`

~~~java
package example.plugin;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class Probe {
    public static String readMarker(Path path) throws IOException {
        return Files.readString(path, StandardCharsets.UTF_8);
    }

    public static String readSharedProperty() {
        return System.getProperty("demo.shared.flag");
    }

    public static void changeSharedProperty() {
        System.setProperty("demo.shared.flag", "PLUGIN_CHANGED");
    }
}
~~~

Đây là plugin implementation bình thường, không có custom permission hoặc API bỏ qua sandbox. `Files` và `System` là public JDK classes mà code plugin có thể sử dụng khi chạy trong JVM với quyền phù hợp.

### 4.3. Tệp `src/host/BoundaryDemo.java`

~~~java
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class BoundaryDemo {
    public static void main(String[] args) throws Exception {
        Path marker = Files.createTempFile("plugin-permission-", ".txt");
        try {
            Files.writeString(marker, "MARKER_OK", StandardCharsets.UTF_8);
            System.setProperty("demo.shared.flag", "HOST_INITIAL");
            URL pluginRoot = Path.of("build/plugin").toUri().toURL();
            ClassLoader parent = BoundaryDemo.class.getClassLoader();

            try (URLClassLoader loaderA =
                         new URLClassLoader(new URL[] {pluginRoot}, parent);
                 URLClassLoader loaderB =
                         new URLClassLoader(new URL[] {pluginRoot}, parent)) {

                Class<?> a = loaderA.loadClass("example.plugin.Probe");
                Class<?> b = loaderB.loadClass("example.plugin.Probe");

                System.out.println("sameBinaryName="
                        + a.getName().equals(b.getName()));
                System.out.println("differentRuntimeClasses=" + (a != b));
                System.out.println("differentDefiningLoaders="
                        + (a.getClassLoader() != b.getClassLoader()));

                Method read = a.getMethod("readMarker", Path.class);
                System.out.println("pluginCanReadHostFile="
                        + "MARKER_OK".equals(read.invoke(null, marker)));

                a.getMethod("changeSharedProperty").invoke(null);
                System.out.println("hostSeesPluginPropertyChange="
                        + "PLUGIN_CHANGED".equals(
                                System.getProperty("demo.shared.flag")));

                Method readSetting = b.getMethod("readSharedProperty");
                System.out.println("otherLoaderSeesSameProperty="
                        + "PLUGIN_CHANGED".equals(
                                readSetting.invoke(null)));
            }
        } finally {
            Files.deleteIfExists(marker);
            System.clearProperty("demo.shared.flag");
        }
    }
}
~~~

Giải thích:

- `URLClassLoader loaderA` và `loaderB` là **hai object khác nhau**, cùng trỏ tới một directory chứa bytecode. Mỗi loader tự định nghĩa `example.plugin.Probe` vì parent không nhìn thấy class đó.
- Host không compile với `Probe.java`; reflection gọi public static methods của class được load. Đây là kỹ thuật của demo, còn production có thể dùng shared SPI/interface.
- `Files.createTempFile` tạo file marker, `writeString` ghi text, `finally` xóa file khi xong.
- `Files.readString` chạy **trong cùng process** với host. ClassLoader khác không tự loại quyền đọc file mà process có.
- `System.setProperty` thay đổi JVM-wide state, nên host và plugin B đều quan sát được.
- `try-with-resources` đóng loader resources. Việc này không đồng nghĩa thu hồi mọi class đã define hoặc dừng tất cả threads.

### 4.4. Biên dịch và thực thi

Linux/macOS, chạy từ thư mục `demo`:

~~~sh
mkdir -p build/plugin build/host
javac --release 17 -d build/plugin src/plugin/example/plugin/Probe.java
javac --release 17 -d build/host src/host/BoundaryDemo.java
java -cp build/host BoundaryDemo
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/plugin, build/host | Out-Null
javac --release 17 -d build/plugin src/plugin/example/plugin/Probe.java
javac --release 17 -d build/host src/host/BoundaryDemo.java
java -cp build/host BoundaryDemo
~~~

### 4.5. Stdout chính xác đã kiểm chứng

~~~text
sameBinaryName=true
differentRuntimeClasses=true
differentDefiningLoaders=true
pluginCanReadHostFile=true
hostSeesPluginPropertyChange=true
otherLoaderSeesSameProperty=true
~~~

Demo đã biên dịch bằng `javac --release 17` và chạy thành công với JDK trong môi trường thông thường không bật legacy SecurityManager hay OS policy đặc biệt cấm đọc file tạm. Output không phụ thuộc tên file tạm hoặc chuỗi định danh loader.

### 4.6. Đọc kết quả

| Output | Bằng chứng |
|---|---|
| `sameBinaryName=true` | Hai class có cùng binary name |
| `differentRuntimeClasses=true` | Hai class objects khác identity |
| `differentDefiningLoaders=true` | Loader A/B thật sự định nghĩa class riêng |
| `pluginCanReadHostFile=true` | Plugin A đọc được marker file do host tạo trong cùng process |
| `hostSeesPluginPropertyChange=true` | Plugin A thay đổi global JVM property, host thấy thay đổi |
| `otherLoaderSeesSameProperty=true` | Plugin B cũng thấy state mới dù implementation class của B khác |

**Không kết luận quá mức:** demo chỉ chứng minh code plugin có thể đọc **file marker được truyền path và được process cho phép**, không chứng minh có thể đọc mọi file trên máy; đó là việc của OS policy. Nó chứng minh **tách class identity không tự tách quyền của process**.

### 4.7. Các phép thử mở rộng

**Thử A — Thêm plugin vào system classpath:** parent có thể định nghĩa `Probe` thay hai child loaders, khiến `differentRuntimeClasses=false`. Quyền file OS không tự đổi.

**Thử B — Không gửi `Path` cho plugin:** plugin không có path cụ thể để gọi method trong ví dụ. Nhưng đây là **kiểm soát luồng dữ liệu theo hợp đồng**, không phải ranh giới an toàn chống code plugin có thể gọi public Java APIs khác.

**Thử C — Chạy plugin trong process riêng:** cấp cho plugin process một OS user/filesystem view không có quyền đọc marker. Nếu policy thực sự chặn, code dù biết path cũng không thể đọc. Chính **OS/process enforcement** tạo sự khác biệt.

**Thử D — Thêm static field vào `Probe`:** mỗi runtime class của A/B có static field riêng. Trong khi đó `System` là shared JDK class nên state của nó dùng chung. Cần phân biệt **statics per runtime class** và **globals của process/shared classes**.

## 5. Vì sao SecurityManager không phải lời giải mới cho plugin sandbox?

Trong các JDK cũ, một `SecurityManager` được bật cùng policy phù hợp có thể kiểm tra một số thao tác nhạy cảm qua `Permission`/`ProtectionDomain`. **Một ClassLoader riêng không tự bật cơ chế đó**; việc gán `CodeSource` hoặc `ProtectionDomain` cũng không khiến hệ điều hành cấp một bộ quyền độc lập.

Các mốc cần nhớ:

| Phiên bản | Hành vi cần lưu ý |
| --- | --- |
| **JDK 17** | JEP 411 đánh dấu `SecurityManager` là **deprecated for removal**; mã legacy còn phụ thuộc chính sách và cấu hình. |
| **JDK 17–23** | Khả năng bật/cài manager và cảnh báo thay đổi theo bản JDK; cần kiểm tra runtime cụ thể. |
| **JDK 24+** | JEP 486 **permanently disabled**: không thể bật qua startup flag hay `System.setSecurityManager`. |

`CodeSource` mô tả thông tin nguồn khi có; nó không phải xác thực artifact hoặc sandbox. Để tách quyền truy cập file, network, bí mật và tài nguyên giữa host và plugin không tin cậy, cần một ranh giới **process/OS** được cấu hình và kiểm thử thực tế.

Tài liệu: [JEP 411](https://openjdk.org/jeps/411), [JEP 486](https://openjdk.org/jeps/486), [Oracle JDK 24](https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html). Bài **SecurityManager là cơ chế lịch sử và cần đối chiếu phiên bản JDK** phân tích cụ thể các API legacy, startup flags và migration.

## 6. JPMS strong encapsulation cũng khác sandbox tài nguyên

JPMS cung cấp:

- `requires`: module readability.
- `exports`: package nào được module khác truy cập theo Java access rules.
- `opens`: mở package cho deep reflection theo ngữ cảnh.
- `ModuleLayer`: ánh xạ named modules với loader(s) và module resolution.

Ví dụ descriptor:

~~~java
module plugin.api {
    exports plugin.api;
}
~~~

Ngăn deep reflection vào một package là **cô lập truy cập class/member**, không phải giới hạn OS operations. Một plugin module vẫn có thể gọi `java.nio.file.Files` nếu Java/module access hợp lệ và OS cho phép file operation.

Tương tự, cấu hình `--add-opens` hoặc `--add-exports` làm thay đổi phạm vi Java module access, không phải ACL mạng/file. `ModuleLayer` không tạo kernel namespace hoặc per-module CPU quota. Module graph và loader mapping là công cụ cấu trúc application, không phải container.

## 7. Chọn ranh giới theo mức độ tin cậy

### 7.1. Plugin nội bộ, được kiểm duyệt

Khi code do cùng nhóm phát triển và review, chạy cùng JVM với ClassLoader riêng có thể là lựa chọn hợp lý:

- Dễ gọi Java interface trực tiếp, ít chi phí IPC.
- Hỗ trợ multiple versions của libraries.
- Cho phép plugin lifecycle, nạp lại với loader mới.
- API chung được loader parent định nghĩa một lần.
- Cho phép `ServiceLoader`/module layers để discovery.

Tuy nhiên cần vẫn xử lý resource leaks, timeouts, exception propagation, shared state và version conflicts. **Tin cậy cao** không đồng nghĩa code không thể có bug hoặc ảnh hưởng host.

### 7.2. Plugin của bên thứ ba hoặc multi-tenant

Nếu plugin không cùng trust domain, ranh giới thực thi có thể là:

~~~text
Trusted host JVM
      |
      | IPC request/response + authz
      v
Isolated plugin runner process
  - dedicated OS identity / limited credentials
  - filesystem mounts / allowlists
  - network egress and ingress rules
  - CPU, memory, PID, FD quotas
  - timeout, restart, supervision
      |
      v
Plugin's own ClassLoader (nếu vẫn cần namespace isolation)
~~~

Host không chia sẻ tùy tiện object heap và process privileges với plugin. Một loader bên trong runner vẫn hữu ích cho dependencies, nhưng **quyền thực thi được bảo vệ tại process/OS boundary**.

### 7.3. Containers, sandbox và máy ảo

Container có thể cung cấp isolation hữu ích, nhưng mức an toàn phụ thuộc cấu hình:

- Không cấp quyền privileged, không mount host secrets/filesystem/Docker socket không cần thiết.
- Dùng OS user/capabilities tối thiểu; rootless/user namespace khi phù hợp.
- Giới hạn egress network, seccomp/AppArmor/SELinux, mounts, read-only paths theo môi trường.
- Áp quotas và restart policy; theo dõi logs và resource usage.
- Giữ kernel/runtime đã vá; xác minh image và dependencies.

Container thường chia sẻ kernel với host. Khi threat model yêu cầu cách ly mạnh hơn, cân nhắc VM/hypervisor, process isolation có kiểm soát hoặc dịch vụ thực thi riêng. Không có ranh giới nào an toàn chỉ nhờ tên gọi.

### 7.4. API allowlist là cách thiết kế tốt nhưng không đủ chống code đối nghịch

Một host có thể chỉ cung cấp:

~~~java
public interface PluginContext {
    byte[] readApprovedResource(String id) throws Exception;
    void emitOutput(String value);
}
~~~

Đây là contract minh họa. Với **code hợp tác**, giới hạn methods theo capabilities làm thiết kế rõ hơn. Nhưng nếu plugin bytecode tùy ý trong cùng JVM vẫn truy cập được public JDK APIs, nó **có thể bypass API do host đề xuất**. Muốn cưỡng chế với code không tin cậy, phải đặt policy ở boundary không thể bỏ qua (OS/process/IPC).

### 7.5. Bảng ra quyết định

| Tiêu chí | Một JVM, ClassLoader riêng | Process riêng + OS policy |
|---|---|---|
| Namespace/version isolation | Có thể thực hiện tốt | Có, thêm process boundary |
| Shared Java objects | Trực tiếp qua shared API | Dùng IPC/serialization |
| Chặn truy cập secret file của host | **Không tự làm được** | Có thể nếu user/mounts/credentials đúng |
| Network allowlist per plugin | **Không tự làm được** | Có thể nếu policy được cưỡng chế |
| CPU/memory quota per plugin | Không có quota tin cậy per loader | Có thể áp process/container quotas |
| Một plugin crash làm chết host | Không bảo đảm cô lập | Host có thể giữ process riêng hoạt động |
| Triển khai, debug, latency | Đơn giản hơn | Phức tạp hơn, IPC overhead |
| Plugin đáng tin | Thường đủ cho namespace | Cân nhắc nếu cần fault isolation |
| Plugin đối nghịch/untrusted | **Không đủ** | Cần ranh giới thực thi mạnh hơn |

**Tách namespace là mục tiêu kỹ thuật; tách permissions là mục tiêu bảo mật.** Chọn theo threat model, không chỉ theo cấu trúc code.

## 8. Các rủi ro ClassLoader không thể tự loại bỏ

### 8.1. File và network

Nếu JVM chạy bằng account có quyền đọc một secret file, class được định nghĩa bởi child loader **không tự mất quyền đó**. Plugin có thể gọi public file/network APIs, chịu OS permission checks như các threads khác trong process.

Nếu cần tách tenants: cấp secrets vào từng runner khác nhau hoặc thiết kế broker với authorization; đừng dùng `ClassLoader == tenantIdentity` thay ACL thực sự.

### 8.2. Shared state và can thiệp giữa plugins

Một plugin có thể tác động `System` properties, global logs, static shared caches, các callbacks/registries và mutable objects host truyền vào. Tạo ClassLoader riêng không tạo bản sao của shared JDK classes.

Thiết kế ít shared mutable state, dùng immutable DTOs và ranh giới interface rõ có thể giảm lỗi logic, nhưng với bytecode untrusted cần enforcement ngoài Java object conventions.

### 8.3. Denial of service

Một plugin có thể chiếm CPU, allocate quá nhiều memory, tạo threads hoặc giữ file descriptors. Không có quota CPU/heap/thread **theo ClassLoader** mặc định.

`Future.cancel(true)` hoặc `Thread.interrupt()` có ích khi code hợp tác, **không là kill switch chắc chắn** cho code bị lỗi hoặc đối nghịch. `Thread.stop()` không phải lựa chọn an toàn để sandbox. Process runner riêng có thể bị terminate/restart theo policy của hệ thống.

### 8.4. Class unloading không phải revocation

`URLClassLoader.close()` giải phóng resources loader, nhưng không đảm bảo tất cả loaded classes được unload ngay; instances, threads, `Thread Context ClassLoader`, caches và method handles có thể giữ chúng sống. Đóng loader **không tự thu hồi OS authority** của thread/plugin code đang chạy.

Nếu cần thu hồi quyền cưỡng chế, có thể ngừng/kill process riêng và thu hồi credentials/network policy; cách đó khác hoàn toàn với việc bỏ tham chiếu ClassLoader.

### 8.5. Type safety không đồng nghĩa authorization

JVM bytecode verifier và class loading rules bảo vệ tính nhất quán của type system. Một chương trình **type-safe** vẫn có thể thực hiện hành vi không mong muốn bằng các API hợp lệ với quyền process đã có.

**“JVM từ chối định nghĩa class trùng tên” không chứng minh JVM chặn mọi hành vi file/network của code plugin.**

## 9. Quy trình thiết kế và kiểm chứng plugin boundary

Bắt đầu bằng **threat model**, rồi chọn kỹ thuật theo đúng nguồn rủi ro:

1. **Ai kiểm soát bytecode?** Code nội bộ đã review, partner đã duyệt hay người dùng tùy ý? Kiểm tra publisher, artifact, dependency và khả năng bị thay trước khi chạy.
2. **Tài nguyên nào cần giữ riêng?** Secrets, database, filesystem, network, process lifetime hoặc quyền của những tenants khác. Xác định ai hiện có quyền OS đến chúng.
3. **Mục tiêu cô lập là gì?** Nếu chỉ để mỗi plugin dùng một library version, có thể dùng ClassLoader. Nếu phải chặn hành vi của code đối nghịch, cần process và chính sách OS.
4. **Giao tiếp qua ranh giới như thế nào?** Host phải thực hiện AuthN/AuthZ, validate inputs và outputs, giới hạn message size, timeout, retries và các operation cho phép; worker output vẫn là dữ liệu không tin cậy.
5. **Chứng minh quyền bị chặn ra sao?** Trong môi trường deploy thực, thử đọc file giả lập ngoài allowlist và kết nối test endpoint bị cấm; xác minh OS từ chối, cùng với quota CPU/memory và cleanup sau timeout.

```text
Artifact/source gate → ClassLoader/JPMS (namespace)
                     → Process/OS policy (permissions/quotas)
                     → IPC authorization & validation → Monitoring
```

Các tầng giải quyết các câu hỏi riêng. Một allowlist Java API do host cung cấp có ích với plugin hợp tác, nhưng không ngăn bytecode đối nghịch cùng JVM tự gọi public JDK APIs. Chi tiết supervisor, pipes, timeouts, process tree và IPC nằm trong bài **Tách tiến trình khi cần ranh giới bảo mật mạnh hơn ClassLoader**.

## 10. Những trường hợp dễ nhầm

### “Hai plugins có cùng tên class nhưng khác ClassLoader, vậy đã cô lập”

**Đúng một phần:** chúng có thể là hai runtime types khác nhau, giúp tránh namespace collision. **Sai nếu nói về quyền file/network**: các threads vẫn có thể cùng process authority.

### “JPMS không cho plugin reflect vào private field, vậy plugin không thể đọc secrets”

Không đủ. JPMS hạn chế Java module access, nhưng nếu secret tồn tại trong file/environment/IPC mà process vẫn có quyền đọc, cần chính sách riêng. Cũng đừng đưa secrets vào object graph shared một cách vô ý.

### “Plugin chỉ được cung cấp PluginContext nhỏ nên chắc chắn không thể gọi File APIs”

Không đúng với bytecode tùy ý trong cùng JVM nếu không có enforcement khác. Interface boundary tốt về thiết kế nhưng không tự chặn code không hợp tác.

### “JEP 411 chỉ deprecated; ta vẫn bật SecurityManager mãi được”

Sai: **JEP 486 ở JDK 24 đã vô hiệu hóa vĩnh viễn**. Thiết kế dựa trên `java.policy` không có hướng phát triển bền vững cho JDK mới.

### “Container là sandbox tuyệt đối”

Không. Container cần cấu hình ít quyền, mounts, secrets, egress, capabilities, quotas và cập nhật kernel phù hợp. Đối với threat model mạnh hơn, cân nhắc VM/hypervisor.

### “Đóng loader là dừng plugin”

Không. Loaded classes/instances/threads có thể vẫn tồn tại; tài nguyên OS của process không đổi. Cần lifecycle/shutdown logic, hoặc kill/restart process ở boundary riêng.

### “Signature của JAR cho phép plugin làm gì?”

Chữ ký chủ yếu phục vụ xác minh artifact integrity/origin, **không tự là policy giới hạn I/O**. Có provenance đáng tin không đồng nghĩa code không có lỗi hoặc không phá resource của process.

### “ClassLoader riêng có JVM heap/GC độc lập”

Sai: không có heap, garbage collector và CPU scheduler riêng theo ClassLoader mặc định. Tài nguyên có thể được đo/giới hạn theo process/container, chứ không tự theo loader.

## 11. Câu hỏi và bài tập tự kiểm tra

1. Namespace isolation trả lời câu hỏi gì? Permission isolation trả lời câu hỏi gì?
2. Runtime type identity của ordinary class gắn với những thành phần nào?
3. Vì sao hai ClassLoader khác nhau có thể vẫn trả cùng `Class<?>`?
4. Vì sao `ClassCastException` do loader khác nhau không phải bằng chứng sandbox đã hoạt động?
5. ClassLoader có tự tạo OS identity hoặc tài khoản file permission khác không?
6. Trong demo, vì sao hai runtime classes khác nhau nhưng đều nhìn thấy `System` properties?
7. Static field trong `Probe` do loader A định nghĩa có dùng chung với bản `Probe` của B không?
8. `pluginCanReadHostFile=true` chứng minh điều gì và **không** chứng minh điều gì?
9. Nếu plugin thật sự không được đọc secret file, cần boundary cưỡng chế ở đâu?
10. `ServiceLoader`/`URLClassLoader` giúp vấn đề discovery và dependency như thế nào?
11. `ModuleLayer` và `exports`/`opens` có tự ngăn network egress không?
12. JEP 411 liên quan phiên bản Java nào và JEP 486 liên quan JDK nào?
13. Vì sao `ProtectionDomain`/`CodeSource` không tự bảo đảm file/network sandbox trên JDK 24+?
14. Dùng API wrapper `PluginContext` có ích gì dù không đủ đối phó bytecode đối nghịch?
15. Vì sao plugin không hợp tác có thể làm timeout/cancellation trong cùng JVM thiếu tin cậy?
16. Tại sao URLClassLoader.close không bảo đảm dừng threads và thu hồi OS permissions?
17. Khi plugin A/B cần hai versions library, chọn ClassLoader riêng hay process riêng theo tiêu chí nào?
18. Những điều kiện nào cần kiểm soát ở container để không lộ host secrets?
19. Khi chuyển plugin sang IPC, host cần validate/authz những yếu tố nào?
20. Artifact được ký có thể vẫn chạy lỗi hoặc gây resource exhaustion không?
21. Đâu là nơi đặt CPU/memory quotas thực sự?
22. Vì sao cần test ranh giới quyền trên build/deploy thực tế chứ không chỉ trong IDE?
23. Với hệ multi-tenant, vì sao một ClassLoader mỗi tenant không bằng một security principal mỗi tenant?
24. Hãy vẽ lại sơ đồ ba tầng: classloader namespace, Java module access và OS/process permissions.
25. Nêu một tình huống mà ClassLoader riêng là **đúng giải pháp** và một tình huống mà nó **không đủ**.

**Tiêu chí hoàn thành:** chạy và giải thích được đủ sáu dòng stdout; chứng minh type identity có thể khác nhưng quyền process vẫn chia sẻ; phân biệt Java access control với OS authorization; biết trạng thái SecurityManager Java 17/JDK 24+; đề xuất cách tách quyền thực thi thực sự khi chạy untrusted plugins.

## 12. Tài liệu chuẩn

- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): defining loader, parent delegation và class namespace.
- [JLS §12.2 — Loading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.2): consistency/identity của class loading.
- [Java SE 21 — ModuleLayer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): module-layer mapping, không phải OS sandbox.
- [Java SE 17 — ProtectionDomain](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/ProtectionDomain.html): miền bảo vệ trong Java security architecture lịch sử.
- [JEP 411 — Deprecate the Security Manager for Removal](https://openjdk.org/jeps/411): SecurityManager deprecated for removal từ Java 17.
- [JEP 486 — Permanently Disable the Security Manager](https://openjdk.org/jeps/486): SecurityManager bị vô hiệu hóa ở JDK 24.
- [Oracle JDK 24 Security Developer's Guide](https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html): thay đổi permission APIs và hướng chuyển sang container/OS/VM.

**Kết luận:** ClassLoader tách **namespace và runtime type identity**; JPMS áp dụng **module readability và Java access control**; riêng **quyền file/network/process và resource quotas** cần được cưỡng chế bởi OS/process/runtime boundary phù hợp. Đừng gọi một child ClassLoader là sandbox bảo mật nếu không có policy được thực thi bên ngoài cơ chế class loading.