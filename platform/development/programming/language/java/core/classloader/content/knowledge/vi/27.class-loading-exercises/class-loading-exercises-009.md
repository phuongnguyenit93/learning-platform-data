# Thực hiện reload plugin bằng ClassLoader mới trong Java 17

## 1. Mục tiêu thực hành

Trong một hệ thống Java hỗ trợ plugin, yêu cầu “reload plugin” thường có nghĩa:

1. Ứng dụng host đang gọi implementation phiên bản **v1**.
2. Bản **v2** được phát hành với cùng binary name (ví dụ `plugin.EchoPlugin`) nhưng bytecode/hành vi mới.
3. Host **chuẩn bị một class loader mới** và tạo instance của v2.
4. Host chuyển những lời gọi mới sang instance v2 một cách có kiểm soát.
5. Những lời gọi còn đang chạy trên v1 được hoàn tất hoặc hủy theo chính sách, sau đó giải phóng resources và references của **loader cũ**.
6. Nếu chuẩn bị v2 thất bại, v1 vẫn phục vụ thay vì bị dỡ sớm.

**Điều không nên làm:** ghi đè file `.class`/JAR bên dưới loader cũ rồi kỳ vọng `loadClass` sẽ thay định nghĩa runtime đã tồn tại. Trong JVM, một runtime class được nhận diện bởi **binary name + defining class loader**. Loader đã định nghĩa `plugin.EchoPlugin` không biến class đó thành v2 chỉ vì file trên đĩa đổi nội dung.

Bài này xây một ví dụ **Java 17 có thể biên dịch và chạy**: một shared `api.Plugin`, hai implementation v1/v2 cùng binary name, mỗi version nằm ở một output directory riêng, `URLClassLoader` mới cho mỗi generation và một `Manager` dùng `ReentrantReadWriteLock` để tránh race giữa lời gọi và lúc thay plugin.

Kết quả thực hành sẽ chứng minh:

- Hai version cùng thực hiện chung interface mà host biết.
- Sau reload, v2 chạy behavior mới và static field bắt đầu từ trạng thái mới.
- Class v1 và v2 có cùng binary name nhưng khác `Class<?>` và khác defining loader.
- Nếu chuẩn bị candidate từ đường dẫn thiếu thất bại, v1 vẫn là plugin active.
- Loader của v1 được đóng sau khi manager chuyển sang v2; **đóng loader không chứng minh lớp đã được JVM unload**.

## 2. Reload phải tạo một định nghĩa runtime mới

`loader.loadClass("plugin.EchoPlugin")` nhiều lần trên **cùng loader** thường nhận cùng `Class<?>` đã ghi nhận. Ghi đè JAR hoặc thay bytes ở nguồn không viết đè class đã định nghĩa; cố gọi `defineClass` lại cùng binary name trong loader cũ có thể gây `LinkageError`.

Bài lab vì thế tạo hai **loader instances**:

```text
Host/App Loader
  └── api.Plugin (shared API)
       ├── L1 -> plugin.EchoPlugin v1
       └── L2 -> plugin.EchoPlugin v2

(plugin.EchoPlugin, L1) != (plugin.EchoPlugin, L2)
api.Plugin luôn do parent định nghĩa
```

| Cách thay đổi | Có tạo class identity mới? |
| --- | --- |
| Gọi method/loadClass lại qua L1 | Không |
| Sửa file mà L1 đã đọc | Không thay runtime class cũ; dễ trộn resource/dependency |
| Tạo L2 và để L2 thực sự định nghĩa v2 | Có, thuộc generation khác |
| Instrumentation/JVMTI hot swap | Cơ chế riêng với giới hạn, không phải `defineClass` lần hai |
| Restart JVM | Runtime mới, đổi lại chi phí triển khai khác |

**Hai generations cùng tồn tại trong một khoảng thời gian là hợp lệ.** Trọng tâm không phải nạp được v2, mà là bảo vệ lời gọi đang chạy, chỉ publish v2 sau prepare và retire v1 có kiểm soát.

## 3. Kiến trúc reload có kiểm soát

```text
         Requests từ host
                |
                v
          Plugin Manager
          active = v1
                |
                v
          Plugin v1 / L1
                |
                +------------------+
                                   |
                         Chuẩn bị v2 / L2
                         (chưa publish)
                                   |
                 +-----------------+----------------+
                 |                                  |
          Prepare thất bại                    Prepare thành công
                 |                                  |
          Active vẫn v1                 Khóa write / chờ calls v1
                 |                                  |
          Không đóng v1                Active <- v2 / L2
                                                    |
                                           Close plugin v1 / L1
                                                    |
                                           New calls -> v2
```

Hai bước phải phân biệt:

- **Prepare:** dựng loader mới, load/validate implementation, tạo instance candidate; nếu thất bại thì chỉ dispose candidate, không động vào plugin active.
- **Activate/replace:** khi candidate đã sẵn sàng, chặn các lời gọi mới đủ ngắn để chuyển active reference, chờ lời gọi cũ kết thúc và close old resources theo policy.

Trong ví dụ, `ReentrantReadWriteLock` được dùng như một **cổng đồng bộ**:

- Mỗi `invoke` nắm **read lock** trong suốt lời gọi method của plugin.
- `replace` và `close` nắm **write lock**. Write lock chỉ được lấy khi các read lock hiện tại đã được thả.
- Vì vậy, khi thay v1 bằng v2, không có lời gọi v1 đang thực thi **thông qua manager này**.
- Sau swap, những lời gọi lấy read lock mới sẽ thấy v2.

**Giới hạn:** Lock chỉ quản lý các lời gọi qua manager. Nếu plugin tự tạo background thread, timer hoặc callback độc lập, lock này **không tự dừng** chúng. Trong production cần lifecycle hooks, quiesce/drain tasks và cleanup tương ứng.

## 4. Cấu trúc project

Tạo các file:

```text
src/
  api/
    api/
      Plugin.java

  v1/
    plugin/
      EchoPlugin.java

  v2/
    plugin/
      EchoPlugin.java

  host/
    host/
      ReloadPluginDemo.java

out/
  api/
    api/
      Plugin.class
  v1/
    plugin/
      EchoPlugin.class
  v2/
    plugin/
      EchoPlugin.class
  host/
    host/
      ReloadPluginDemo.class
      ...
```

`out` là **kết quả build**, không cần tạo thủ công từng file `.class`. Hai source files `src/v1/plugin/EchoPlugin.java` và `src/v2/plugin/EchoPlugin.java` có cùng declaration `package plugin; public final class EchoPlugin`; điều này hợp lệ vì chúng được biên dịch ra **hai directories riêng**.

**Bất biến quan trọng:** `api.Plugin` chỉ có một bản runtime ở `out/api` do loader chung của host định nghĩa. Không đưa `out/v1` và `out/v2` vào application classpath trong lúc chạy host.

## 5. Shared API — hợp đồng ổn định giữa host và mọi phiên bản

File `src/api/api/Plugin.java`:

```java
package api;

public interface Plugin extends AutoCloseable {
    String execute(String input);

    @Override
    void close();
}
```

Giải thích:

- `execute` là entry point mà host gọi, trả `String` từ Java core, không làm rò kiểu private của plugin qua chữ ký.
- `AutoCloseable` biểu diễn lifecycle; `Plugin.close()` override và **không khai báo checked exception** trong interface shared này.
- `URLClassLoader.close()` vẫn có thể ném `IOException`; đó là việc host phải xử lý riêng.
- Đây là **contract**; plugin v1/v2 đều compile against `out/api` và ủy quyền `api.Plugin` về parent ở runtime.

Một shared API thực tế có thể khai `start(PluginContext)`, `quiesce()`, `stop()`, health checks, DTO/request/response và domain exception. Những kiểu đó cũng phải được parent/shared loader định nghĩa thống nhất nếu dùng qua boundary.

**Không đổi interface tùy tiện giữa hai lần reload.** Một plugin được compile với API v2 nhưng host chỉ có API v1 có thể gặp `NoSuchMethodError`/`AbstractMethodError`/lỗi binary compatibility ngay cả khi class loader khác nhau đã hoạt động đúng.

## 6. Plugin v1: behavior và static state của thế hệ đầu

File `src/v1/plugin/EchoPlugin.java`:

```java
package plugin;

import api.Plugin;

public final class EchoPlugin implements Plugin {
    private static int calls;

    @Override
    public String execute(String input) {
        return "v1:" + input + ":" + (++calls);
    }

    @Override
    public void close() {
        System.out.println("CLOSE=v1");
    }
}
```

`calls` là **static field** của `plugin.EchoPlugin` do defining loader L1 định nghĩa. Trong demo tuần tự, ba lời gọi v1 sẽ cho `:1`, `:2` và `:3`.

**Cảnh báo production:** `++calls` không thread-safe. Chúng ta chỉ dùng demo để quan sát static class state sau reload; với plugin phục vụ đồng thời, cân nhắc `AtomicInteger`/synchronization và xác định trạng thái nào cần persist/migrate.

`close()` in một marker; trong plugin thực, nó thường giải phóng stream, connection, thread/executor, listener, scheduler và resources. Chỉ in marker **không làm class unload**.

## 7. Plugin v2: cùng tên lớp, triển khai khác

File `src/v2/plugin/EchoPlugin.java`:

```java
package plugin;

import api.Plugin;

public final class EchoPlugin implements Plugin {
    private static int calls;

    @Override
    public String execute(String input) {
        return "v2:" + input + ":" + (++calls);
    }

    @Override
    public void close() {
        System.out.println("CLOSE=v2");
    }
}
```

So với v1:

- **Binary name giống:** `plugin.EchoPlugin`.
- **Shared interface giống:** `api.Plugin` của host.
- **Hành vi khác:** prefix `v2:`.
- **Static state khác:** `calls` của class v2 độc lập với static field của class v1 do defining loaders khác nhau.

Nếu host thấy `v2:hello:1` sau reload, đó là bằng chứng thực tế rằng một generation runtime mới đang xử lý lời gọi (kết hợp với kiểm tra `Class<?>` identity ở phần dưới).

## 8. Host Java 17: tạo loader mới và chuyển generation

File `src/host/host/ReloadPluginDemo.java`:

```java
package host;

import api.Plugin;
import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public final class ReloadPluginDemo {
    static final class Generation implements AutoCloseable {
        final URLClassLoader loader;
        final Plugin plugin;
        final Class<?> type;

        Generation(URLClassLoader loader, Plugin plugin, Class<?> type) {
            this.loader = loader;
            this.plugin = plugin;
            this.type = type;
        }

        @Override
        public void close() throws IOException {
            try (loader) {
                plugin.close();
            }
        }
    }

    static Generation prepare(Path pluginDirectory) throws Exception {
        URL source = pluginDirectory.toUri().toURL();
        URLClassLoader loader = new URLClassLoader(
                "generation-" + pluginDirectory.getFileName(),
                new URL[]{source},
                Plugin.class.getClassLoader());

        try {
            Class<?> type = Class.forName(
                    "plugin.EchoPlugin", true, loader);

            Plugin instance =
                    (Plugin) type.getConstructor().newInstance();

            return new Generation(loader, instance, type);
        } catch (Exception | LinkageError failure) {
            try {
                loader.close();
            } catch (IOException closeFailure) {
                failure.addSuppressed(closeFailure);
            }
            throw failure;
        }
    }

    static final class Manager implements AutoCloseable {
        private final ReentrantReadWriteLock gate =
                new ReentrantReadWriteLock(true);

        private Generation current;

        String invoke(String message) {
            gate.readLock().lock();
            try {
                if (current == null) {
                    throw new IllegalStateException("No active plugin");
                }
                return current.plugin.execute(message);
            } finally {
                gate.readLock().unlock();
            }
        }

        Class<?> activeType() {
            gate.readLock().lock();
            try {
                if (current == null) {
                    throw new IllegalStateException("No active plugin");
                }
                return current.type;
            } finally {
                gate.readLock().unlock();
            }
        }

        void replace(Generation next) throws IOException {
            gate.writeLock().lock();
            try {
                Generation previous = current;
                current = next;
                if (previous != null) {
                    previous.close();
                }
            } finally {
                gate.writeLock().unlock();
            }
        }

        @Override
        public void close() throws IOException {
            gate.writeLock().lock();
            try {
                Generation previous = current;
                current = null;
                if (previous != null) {
                    previous.close();
                }
            } finally {
                gate.writeLock().unlock();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try (Manager manager = new Manager()) {
            manager.replace(prepare(Path.of("out/v1")));
            Class<?> oldType = manager.activeType();

            System.out.println("FIRST=" + manager.invoke("hello"));
            System.out.println("SECOND=" + manager.invoke("world"));

            try {
                Generation missing =
                        prepare(Path.of("out/missing"));
                manager.replace(missing);
            } catch (ClassNotFoundException expected) {
                System.out.println(
                        "PREPARE_FAILED=ClassNotFoundException");
            }

            System.out.println("STILL=" + manager.invoke("again"));

            Generation next = prepare(Path.of("out/v2"));
            manager.replace(next);

            Class<?> newType = manager.activeType();
            System.out.println("AFTER=" + manager.invoke("hello"));

            System.out.println("SAME_BINARY_NAME="
                    + oldType.getName().equals(newType.getName()));
            System.out.println("SAME_RUNTIME_CLASS="
                    + (oldType == newType));
            System.out.println("SHARED_API="
                    + (Plugin.class.isAssignableFrom(oldType)
                       && Plugin.class.isAssignableFrom(newType)));
            System.out.println("DIFFERENT_DEFINERS="
                    + (oldType.getClassLoader()
                       != newType.getClassLoader()));
        }
    }
}
```

### 8.1. Vai trò của từng thành phần

**`Generation`** giữ ba đối tượng thuộc cùng một plugin deployment:

- `URLClassLoader loader`: nguồn class riêng của thế hệ này.
- `Plugin plugin`: instance implementation được host dùng qua shared API.
- `Class<?> type`: runtime class token, dùng để chẩn đoán identity.

`Generation.close()` gọi `plugin.close()` rồi đóng loader nhờ try-with-resources. Nếu `plugin.close()` ném runtime exception, cấu trúc try-with-resources vẫn cố đóng URLClassLoader. Nếu close JAR/URL resources ném `IOException`, caller có thể nhận exception đó; việc xử lý thật cần logging và chính sách cleanup phù hợp.

**`prepare`** tạo **một URLClassLoader mới cho mỗi lần gọi**, với parent là `Plugin.class.getClassLoader()`. Trong ví dụ application classpath sạch, parent thấy `api.Plugin` nhưng không thấy `plugin.EchoPlugin`, nên child loader định nghĩa implementation riêng.

**`prepare` không “chỉ đọc metadata”**: `Class.forName(..., true, loader)` có thể kích hoạt static initialization, và constructor gọi trong `newInstance` thực thi plugin code. Vì vậy, chỉ đưa artifact **đã được tin cậy/kiểm tra** vào pha prepare; trong production không đánh đồng “chưa activate” với “chưa thực thi mã plugin”.

Nếu lookup/constructor/linking thất bại theo các loại đã catch, candidate loader được đóng và exception được ném lại. `Manager.current` chưa bị thay, nên bản active cũ vẫn phục vụ. Đoạn catch chỉ bao phủ `Exception | LinkageError`; nó **không** biến mọi `Error` nghiêm trọng như `OutOfMemoryError` thành lỗi có thể rollback an toàn.

**`Manager.invoke`** giữ read lock xuyên suốt lời gọi `plugin.execute`. `replace` cần write lock, vì thế chờ các lời gọi qua manager kết thúc trước khi thay active reference và đóng old generation.

**`Manager.activeType`** trả runtime `Class<?>` để chứng minh class identity. Trả token ra ngoài session cho phép caller **giữ loader cũ sống**; đây là thao tác phục vụ bài test, không phải API production nên khuyến khích giữ lâu dài.

**`Manager.close`** đặt active thành null và đóng generation còn hoạt động, ngăn request mới sử dụng plugin qua manager.

### 8.2. Vì sao giữ read lock trong toàn bộ plugin call?

Giả sử worker R1 đang chạy `plugin.execute` của v1, trong khi R2 yêu cầu reload:

```text
R1: acquire readLock
R1: gọi v1.execute()
R2: yêu cầu writeLock -> phải chờ
R1: trả kết quả, release readLock
R2: acquire writeLock
R2: current <- v2, close v1
R2: release writeLock
R3: acquire readLock -> gọi v2
```

Điều này tránh một loại race rất phổ biến: host đóng old loader ngay khi worker còn đang load resources/classes hoặc chạy code v1. Java SE 17 cảnh báo concurrent `URLClassLoader.close()` với class load có kết quả không xác định.

Nhược điểm: plugin call chậm hoặc bị treo có thể giữ read lock quá lâu và khiến reload bị chặn. Production cần timeout/cancellation/operation tracking; có thể dùng reference-counted generations thay vì một read–write lock giữ xuyên invocation, nhưng phải đảm bảo **không close generation khi còn in-flight callers**.

### 8.3. Vì sao không gán current = null trước khi chuẩn bị v2?

Nếu xóa active trước pha prepare, một lỗi như `ClassNotFoundException` hoặc constructor exception của v2 khiến host **không còn plugin đang phục vụ**, dù v1 vẫn có thể hoạt động.

Ở demo, v2 được chuẩn bị trước:

```java
Generation next = prepare(Path.of("out/v2"));
manager.replace(next);
```

Do đó, khi `prepare` thất bại, `replace` không chạy và v1 không bị thay.

**Ghi chú giao dịch:** `replace` trong demo chuyển `current` sang v2 **trước** khi gọi `previous.close()`. Nếu shutdown v1 ném lỗi, v2 **đã được publish** dù `replace` ném exception. Vì vậy đây là **atomic switch cho các lời gọi đi qua lock**, không phải một transaction toàn cục bảo đảm rollback mọi side effects. Hệ thống production nên tách bước activation khỏi cleanup, báo trạng thái riêng, idempotent stop, và quyết định rollback/failover rõ ràng.

## 9. Build và chạy: Linux/macOS Bash

Đứng ở thư mục gốc chứa `src`:

```bash
mkdir -p out/api out/v1 out/v2 out/host

javac -d out/api src/api/api/Plugin.java

javac -cp out/api -d out/v1 src/v1/plugin/EchoPlugin.java

javac -cp out/api -d out/v2 src/v2/plugin/EchoPlugin.java

javac -cp out/api -d out/host \
  src/host/host/ReloadPluginDemo.java

java -cp "out/api:out/host" host.ReloadPluginDemo
```

**Cực kỳ quan trọng:** classpath của lệnh `java` chỉ có `out/api` và `out/host`. Không đưa `out/v1` hoặc `out/v2` vào application classpath khi chạy; nếu không parent-first delegation có thể khiến loader chung tìm thấy implementation trước và làm hỏng tính độc lập của generation.

Các lệnh `javac` biên dịch v1 và v2 **riêng biệt**, mỗi lượt tham chiếu `out/api` để implement đúng shared interface.

## 10. Build và chạy: Windows PowerShell

PowerShell dùng dấu `;` làm classpath separator:

```powershell
New-Item -ItemType Directory -Force out/api,out/v1,out/v2,out/host

javac -d out/api src/api/api/Plugin.java

javac -cp out/api -d out/v1 src/v1/plugin/EchoPlugin.java

javac -cp out/api -d out/v2 src/v2/plugin/EchoPlugin.java

javac -cp out/api -d out/host src/host/host/ReloadPluginDemo.java

java -cp "out/api;out/host" host.ReloadPluginDemo
```

Chạy trong một working directory mới/sạch, tránh có class `plugin.EchoPlugin` từ lần build khác trên parent classpath. Nếu dùng IDE, cũng cần kiểm tra **run configuration** có vô tình thêm v1/v2 vào classpath của host không.

## 11. Stdout dự kiến và kiểm chứng thực tế

Với Java 17+ và project sạch như trên:

```text
FIRST=v1:hello:1
SECOND=v1:world:2
PREPARE_FAILED=ClassNotFoundException
STILL=v1:again:3
CLOSE=v1
AFTER=v2:hello:1
SAME_BINARY_NAME=true
SAME_RUNTIME_CLASS=false
SHARED_API=true
DIFFERENT_DEFINERS=true
CLOSE=v2
```

Đây là kết quả xác định của **demo tuần tự**. Mã đã được biên dịch và chạy thử bằng OpenJDK 21 với các API/cú pháp tương thích Java 17; kết quả khớp đúng các dòng trên. Việc chạy thử trên JDK 21 **không đồng nghĩa** đã chạy bằng JDK 17 cụ thể.

### Diễn giải từng nhóm kết quả

**Hai lời gọi đầu v1:**

```text
FIRST=v1:hello:1
SECOND=v1:world:2
```

Cùng class `plugin.EchoPlugin` của L1 sử dụng cùng static field `calls`.

**Chuẩn bị bản không tồn tại:**

```text
PREPARE_FAILED=ClassNotFoundException
STILL=v1:again:3
```

`out/missing` không chứa class `plugin.EchoPlugin`, parent classpath cũng không có class đó. Candidate lookup báo `ClassNotFoundException` và `prepare` dọn candidate loader. `replace` chưa được gọi, nên manager vẫn trỏ v1.

**Swap:**

```text
CLOSE=v1
AFTER=v2:hello:1
```

Marker `CLOSE=v1` từ lifecycle method của plugin cũ xuất hiện khi manager thay generation. Sau đó bản v2 xử lý lời gọi mới với prefix khác; static `calls` của runtime class v2 bắt đầu tại 0 nên lời gọi đầu cho `:1`.

**Type identity:**

```text
SAME_BINARY_NAME=true
SAME_RUNTIME_CLASS=false
SHARED_API=true
DIFFERENT_DEFINERS=true
```

`oldType` và `newType` cùng `getName()` nhưng khác `Class<?>` identity. Cả hai assignable sang `api.Plugin` của host. Hai `getClassLoader()` khác nhau nên có hai defining loaders.

**Shutdown cuối:**

```text
CLOSE=v2
```

Try-with-resources của `Manager` đóng generation v2. Không có dòng nào chứng minh v1/v2 đã được GC hoặc class unloaded; marker chỉ chứng minh callback `close()` đã được gọi.

## 12. Phân biệt chuẩn bị, kích hoạt, dừng và class unloading

Một reload thật gồm các sự kiện khác nhau:

| Sự kiện | Xảy ra trong demo | Có bảo đảm unload class không? |
|---|---|---|
| Tạo L2 | `prepare(out/v2)` | Không |
| Load v2 class | `Class.forName` với L2 | Không |
| Khởi tạo v2 instance | Reflection constructor | Không |
| Đổi active từ v1 sang v2 | `Manager.replace` | Không |
| Chờ lời gọi cũ hoàn tất | Write lock chờ read locks | Không, chỉ với calls qua manager |
| Gọi `v1.close()` | Lifecycle callback | Không |
| Gọi `L1.close()` | `Generation.close()` | Không |
| Bỏ references tới L1 và class v1 | Cần theo dõi mọi references/roots | Tạo điều kiện có thể reclaim |
| GC/class unloading | Quyết định JVM | Không có deadline |

### Class unloading theo JLS 17 §12.7

JVM chỉ có thể unload một class/interface nếu **defining loader** của nó có thể được garbage collector reclaim; bản thân việc đủ điều kiện không bắt buộc JVM unload ngay.

Trong demo, biến:

```java
Class<?> oldType = manager.activeType();
```

vẫn giữ `Class<?>` cũ để làm bài kiểm tra identity sau reload. Điều đó **có thể tiếp tục giữ L1 reachable**. Đây là lựa chọn có chủ ý để minh họa, không phải cách giữ trong production.

Muốn cho L1 có cơ hội được reclaim, sau khi kiểm chứng phải bỏ cả reference `oldType`, mọi instance/lambda/reflection metadata của v1, listener registries, cache entries, TCCL và background tasks tương ứng; **không được kết luận “CLOSE=v1” nghĩa L1 đã GC**.

### Close không hủy được code đang chạy

`URLClassLoader.close()` đóng nguồn URL/JAR resources và ảnh hưởng việc tìm class/resource mới. Các runtime classes đã load và objects đã tạo vẫn có thể được dùng khi còn reachable. Nếu plugin tự khởi động thread khác và thread ấy còn giữ code/objects v1, close loader không tự stop thread.

**Lời khuyên:** triển khai `Plugin.close()` thực sự làm lifecycle cleanup, đồng thời host theo dõi worker/scheduler của plugin. Nếu plugin không đáng tin, class-loader isolation không phải security sandbox; cần process-level isolation khi threat model đòi hỏi.

## 13. Ví dụ vì sao sửa file JAR tại chỗ là sai

Giả sử triển khai:

```text
plugins/current/plugin.jar
```

và host dùng một `URLClassLoader` trỏ vào file đó. Bạn ghi đè `plugin.jar` bằng v2 khi host vẫn dùng loader L1.

Những điều có thể xảy ra:

- Class `plugin.EchoPlugin` đã loaded vẫn là runtime class v1 do L1 định nghĩa.
- Một class `plugin.Helper` chưa được loaded có thể được đọc về sau từ bytes JAR vừa thay, khiến một generation trộn code v1/v2.
- Resources/service descriptors có thể bị đọc từ bản khác với class đã load.
- JAR handles/caching/file replacement semantics khác nhau giữa filesystem/JDK; trên Windows còn có thể gặp file locking.
- `NoSuchMethodError`/`NoSuchFieldError` hoặc hành vi sai do ABI không nhất quán.

Đừng dùng “đã copy xong JAR mới” như một synchronization protocol giữa deploy process và JVM runtime.

**Cách thích hợp hơn:** mỗi version là một **immutable release directory/JAR riêng**:

```text
plugins/releases/plugin-1.0/plugin.jar
plugins/releases/plugin-2.0/plugin.jar
```

Host xác thực artifact v2, tạo loader mới từ đường dẫn v2, chuyển active generation rồi stop/close v1. Không sửa artifact cũ khi L1 vẫn có thể đọc thêm class/resource.

## 14. Deploy release an toàn và tránh TOCTOU

Với plugin lấy từ nguồn mạng hoặc shared directory, cần xác thực **đúng bytes sẽ dùng để thực thi**. Một quy trình production:

1. **Build/package:** tạo JAR/module artifact nhất quán, có version và dependency manifest.
2. **Approve:** ký manifest hoặc pin digest artifact từ nguồn phê duyệt độc lập.
3. **Download/stage:** tải về thư mục do actor tin cậy quản lý, giới hạn quyền ghi.
4. **Verify:** kiểm tra signature/hash của toàn artifact/dependencies, không chỉ entry class.
5. **Snapshot:** giữ artifact đã verified ở nơi immutable, không cho actor khác sửa giữa check và load.
6. **Prepare candidate loader** từ snapshot v2.
7. **Health-check candidate** trước activation trong phạm vi có thể; tránh tác dụng phụ không kiểm soát.
8. **Activate:** điều phối requests/trạng thái và chuyển generation.
9. **Observe/rollback:** giám sát behavior, sẵn đường fallback nếu v2 lỗi.
10. **Retire old:** dừng tasks v1, unregister listeners, clear caches, close loader và bỏ references.

**Lưu ý quan trọng:** `prepare` demo dùng `Class.forName(..., true, loader)` và tạo instance, vì vậy đã thực thi code candidate trước lúc publish. Artifact phải được trust/verified **trước khi** gọi `prepare`; không dùng chuẩn bị plugin như một vùng sandbox.

Nếu cần rollback tức thì sau khi v2 nhận traffic, có thể giữ v1 tạm thời theo một **grace period** thay vì close ngay, rồi retire sau khi v2 đạt health criteria. Nhưng phải giới hạn số generations giữ sống, tránh Metaspace leak do giữ vô hạn old loaders.

## 15. Vì sao shared API phải ở parent loader?

Ở runtime:

```java
Plugin plugin = (Plugin) type.getConstructor().newInstance();
```

Phép cast hợp lệ vì `plugin.EchoPlugin` của cả hai loaders triển khai **chính `api.Plugin` do parent loader định nghĩa**.

Nếu plugin v2 chứa bản riêng `api.Plugin` và một custom child-first loader tự định nghĩa bản đó, thì:

```text
("api.Plugin", hostLoader) != ("api.Plugin", pluginLoader)
```

Object implementation có thể không assignable sang `Plugin.class` của host, dẫn đến `ClassCastException` hoặc `LinkageError` do loader constraints khi liên kết những reference types trong method descriptors.

**Giữ trong shared API loader:** interface, DTO, exception contracts và các types đi qua host/plugin boundary. **Giữ trong child plugin loader:** implementation/private dependencies có version khác nhau. Tránh đưa `lib.private.*` vào public method parameters/returns của `api.Plugin`.

Với Java module system (JPMS) và `ModuleLayer`, ngoài loader identity còn phải xét module readability, `exports` và `opens`. Ví dụ ở đây chủ động dùng **classpath** để tập trung vào classloader reload, không giả định mọi rules của named modules được bypass.

## 16. State migration: static state không tự chuyển sang loader mới

V1 và v2 có class riêng, vì vậy:

```java
private static int calls;
```

trong hai versions là **hai static fields độc lập**. `AFTER=v2:hello:1` là hệ quả của code demo: v2 bắt đầu thế hệ mới.

Nếu plugin production cần giữ thông tin như user sessions, counters, checkpoints, subscriptions hoặc workflow state, cần một protocol explicit:

```text
v1 quiesce()
  -> exportState() sang shared DTO / serialized schema
  -> validate schema và version compatibility
  -> create v2
  -> importState(snapshot) trước activation
  -> health check
  -> switch traffic
  -> stop v1, release loader
```

Đây là kiến trúc minh họa, **không phải các method có sẵn** trong `api.Plugin` của demo. Nếu muốn triển khai, mở rộng shared API bằng contract rõ ràng và version hóa.

Đừng chuyển trực tiếp `Class<?>`, private objects hoặc lambda của v1 qua boundary để v2 giữ. Những object ấy có runtime identity gắn với L1; nếu v2 lưu chúng thì L1 còn reachable và cách diễn giải type/ABI có thể sai. DTO do parent định nghĩa hoặc định dạng serialization độc lập classloader thường dễ quản lý hơn.

### Khi migration thất bại

Nếu import state v1→v2 không thành công, **không publish candidate** và để v1 tiếp tục phục vụ. Nếu đã quiesce v1, cần quy trình resume/thaw cẩn thận. Không dừng v1 trước khi biết có thể khôi phục dịch vụ.

**Idempotency và external side effects:** nếu v2 đã ghi database/message queue trong pha health check hoặc prepare, rollback con trỏ active không tự đảo ngược side effect. Vì vậy “atomic reload” không nên bị hiểu là transaction của mọi I/O.

## 17. Đồng thời: từ demo lock sang production drain

Read–write lock của demo dễ hiểu nhưng có hạn chế:

- Write lock chờ mọi read locks; một method lâu hoặc treo có thể trì hoãn reload vô hạn.
- Nếu plugin giữ lại work asynchronous sau khi method `execute` trả về, read lock đã được thả nhưng task cũ vẫn có thể chạy.
- Plugin có thể tự gọi lại manager từ một thread hoặc reenter code và tạo lock/lifecycle coupling ngoài dự kiến.
- Đóng loader ngay trong write lock có thể làm tăng thời gian chặn requests.
- Nếu `plugin.close()` gọi lại manager, có thể tạo reentrancy/deadlock logic, tùy call path.

Một thiết kế khác dùng **lease/reference count**:

```text
Acquire active generation -> increment inFlight
Run plugin call
Release generation -> decrement inFlight

Reload:
  prepare v2
  atomically publish v2
  mark v1 retired
  refuse NEW leases for v1
  wait until v1.inFlight == 0
  close v1
```

Đây là pseudocode/sơ đồ thuật toán. Nếu triển khai cần bảo đảm thao tác acquire lease và publish retirement không race: không thể đơn giản đọc `AtomicReference` rồi tăng counter quá muộn, vì retire có thể đóng loader trước khi tăng. Dùng một state machine/lock/CAS protocol đúng.

**Trade-off:**

| Cơ chế | Ưu điểm | Giới hạn |
|---|---|---|
| Read–write lock xuyên invocation | Dễ chứng minh không close khi còn lời gọi qua manager | Reload chờ synchronous calls hoàn tất |
| Ref-counted generation leases | Swap nhanh, cho old calls drain | Khó đúng hơn, cần guard atomicity giữa acquire/retire |
| Process-level rolling restart | Cách ly loader/native/global state tốt hơn | IPC/process orchestration phức tạp |
| Stop-the-world plugin quiescence | Đơn giản hơn khi workload nhỏ | Downtime dài khi stop/load |

Đối với ứng dụng học tập hoặc plugin chạy trong cùng JVM và calls tương đối ngắn, read–write lock là mô hình thực hành tốt. Với hệ thống production concurrency cao, cần SLA và kiến trúc riêng.

## 18. Hủy tác vụ, TCCL và ngăn classloader leak

Dù `Manager` đã close L1, loader v1 vẫn có thể reachable nếu các thành phần khác giữ references:

| Root sống lâu | Có thể giữ L1 qua | Cleanup cần thiết |
|---|---|---|
| Host static registry | `Class<?>`, `Method`, old Plugin instance | Gỡ entry của generation cũ |
| Listener/event bus | Callback implementation do L1 định nghĩa | Unregister listeners |
| Worker thread pool | `Thread.contextClassLoader` = L1 | Restore TCCL trong chính worker |
| `ThreadLocal` | Value chứa plugin context/instance | `remove()` ở worker thread |
| Scheduled future/executor | Runnable/lambda của plugin v1 | Cancel tasks, shutdown executor, drain |
| Reflection cache | `Method`/`MethodHandle` của class v1 | Clear per-generation cache |
| ServiceLoader/provider registry | Provider objects do L1 định nghĩa | Clear provider references |
| Old `Class<?>` token | Host giữ class metadata của v1 | Bỏ token sau diagnostics |

Ví dụ khi framework yêu cầu TCCL:

```java
Thread worker = Thread.currentThread();
ClassLoader saved = worker.getContextClassLoader();
try {
    worker.setContextClassLoader(pluginLoader);
    // Chạy thao tác cần TCCL của plugin.
} finally {
    worker.setContextClassLoader(saved);
}
```

Snippet này cần biến `pluginLoader` đã có. TCCL phải được khôi phục trên **thread thực sự chạy thao tác**, không chỉ trên thread submit task.

**Không mặc định `URLClassLoader.close()` xóa mọi references hoặc ngắt threads.** Nó đóng resources do URLClassLoader quản lý; class unloading vẫn phụ thuộc reachability và quyết định của JVM.

### Bẫy WeakHashMap

`WeakHashMap<ClassLoader, Class<?>>` có **weak keys nhưng strong values**. Nếu value là class do loader key định nghĩa, value có thể giữ lại loader nên key không tự GC như bạn mong đợi. Đừng đổi host static `HashMap` thành `WeakHashMap` rồi coi đó là fix hoàn chỉnh.

Dễ kiểm soát hơn: cache `Class<?>`/`Method` trong **Generation** và clear khi retire; không giữ strong references ở host registry sau stop.

## 19. Quan sát class loading/unloading khi reload

Trên HotSpot Java 17, chạy demo với Unified Logging:

```bash
java -Xlog:class+load=info,class+unload=info \
     -cp "out/api:out/host" host.ReloadPluginDemo
```

Đối với Windows PowerShell:

```powershell
java -Xlog:class+load=info,class+unload=info -cp "out/api;out/host" host.ReloadPluginDemo
```

Class-load log có thể chứa **hai events** cho `plugin.EchoPlugin`: một khi L1 định nghĩa v1, một khi L2 định nghĩa v2. Chi tiết nguồn, timestamp, tags và định dạng dòng log phụ thuộc JVM. Không suy từ việc tên class xuất hiện hai lần rằng duplicate define trong một loader; ở đây là hai defining loaders độc lập.

**Không có bảo đảm class-unload event** xuất hiện trước khi demo kết thúc. Đặc biệt `oldType` là strong local token được giữ để in kết quả identity; nó có thể giữ L1 còn reachable trong khoảng chạy đó.

Muốn điều tra nhiều vòng hot reload trên service thật:

1. Quan sát số active plugin generations.
2. Quan sát loader instances và số class được định nghĩa bởi từng loader.
3. So sánh Metaspace used/committed và heap references qua nhiều chu kỳ.
4. Kiểm tra TCCL, `ThreadLocal`, callbacks, static maps và generated proxy/Method caches.
5. Dùng heap dump/path-to-GC-root analysis khi nghi classloader leak.
6. Nhớ rằng **Metaspace tăng hoặc thiếu unload log một lần** chưa đủ kết luận leak; VM có thể trì hoãn unload và allocator có thể giữ memory để tái sử dụng.

## 20. Các tình huống lỗi thường gặp

### 20.1. Reload xong vẫn gọi behavior v1

Nguyên nhân có thể:

- Parent application classpath đã chứa `plugin.EchoPlugin` v1; cả L1/L2 parent-first đều nhận class của parent.
- Candidate L2 vô tình trỏ tới directory/JAR v1.
- Host không thực sự thay active reference, chỉ tạo L2 rồi bỏ không.
- Cache `Class<?>`/`Method` toàn cục trả class cũ theo binary name.
- Request handler khác vẫn giữ trực tiếp old plugin instance, không đi qua manager.

Cách kiểm tra:

```java
Class<?> type = activePlugin.getClass();
System.out.println(type.getName());
System.out.println(type.getClassLoader());
```

Snippet cần biến `activePlugin`. So sánh trực tiếp `Class<?>` v1/v2, đường URLs của loader và bản implementation thực sự đang được gọi.

### 20.2. ClassCastException khi ép về shared Plugin

Nếu L2 child-first tự định nghĩa bản riêng `api.Plugin`, implementation của L2 không assignable sang `api.Plugin` của host. Dùng một API artifact ở parent và cho các plugin loaders delegate `api.*` về đúng loader chung. Chữ ký dùng shared DTO/exception types, không plugin-private types.

### 20.3. NoSuchMethodError / AbstractMethodError

Plugin v2 có thể được compile với shared API version khác host. Dù L2 tạo thành công và classpath đúng, ABI mismatch khi linking/invoking vẫn có thể gây lỗi. So sánh `javap -s -p` và dependency versions.

Không sửa bằng cách catch `LinkageError` rồi thử tải bytes không rõ nguồn. Chuẩn bị candidate cần kiểm tra binary compatibility và integration smoke tests.

### 20.4. ClassNotFoundException ở candidate

Có thể do:

- Đường dẫn v2 sai hoặc chưa có files.
- JAR/directory layout không chứa đúng binary name `plugin.EchoPlugin`.
- Dependency của plugin thiếu ở loader graph.
- Parent/child policy sai, JPMS module unresolved nếu dùng named modules.

Trong ví dụ, `out/missing` chủ động gây `ClassNotFoundException` để kiểm tra rollback ở **pha prepare**.

### 20.5. File JAR bị khóa sau stop

`URLClassLoader.close()` giúp đóng các JAR files loader đã mở; nhưng nếu streams/classpath users khác còn giữ file handles, OS hoặc framework có thể vẫn chặn việc xóa/đổi tên file. Không vội giả định cứ close loader là toàn bộ liên quan tới file được giải phóng.

### 20.6. Metaspace tăng không ngừng qua nhiều reload

Rất có thể host đang giữ old generations trong static registry, ThreadLocal/TCCL, event bus, executor hoặc reflection cache. Dùng profiler và GC-root paths để xác nhận. Không chỉ nâng `MaxMetaspaceSize` mà bỏ qua nguồn retention.

### 20.7. Reload thành công nhưng hoạt động lỗi sau một lúc

Candidate có thể pass constructor nhưng fail khi xử lý input thực, load lazy dependency/resource hoặc dùng method chưa kiểm tra. Production nên có health checks/integration tests cho các critical paths và rollback window. Một constructor chạy thành công **không chứng minh toàn bộ plugin an toàn và tương thích**.

### 20.8. Stop làm treo reload

Plugin code có thể blocking vô hạn trong `execute`, giữ read lock khiến write lock chờ. Cần timeout/cancellation/cooperative shutdown và thiết kế tách process nếu code không đáng tin hoặc không thể kiểm soát.

## 21. Kiểm thử bắt buộc trước khi dùng thật

| Test | Kỳ vọng |
|---|---|
| Khởi động v1 | `FIRST=v1:hello:1` |
| Gọi v1 hai lần | State tăng 1→2 |
| Candidate không tồn tại | `ClassNotFoundException` được báo; v1 tiếp tục chạy |
| Prepare v2 | Loader mới tạo, interface cast thành công |
| Thay v1→v2 | Marker `CLOSE=v1`, request tiếp theo vào v2 |
| Static state thế hệ v2 | Bắt đầu `:1` |
| So sánh binary name | Hai classes cùng tên |
| So sánh runtime class identity | Hai classes khác nhau |
| Kiểm tra shared API | Cả hai assignable sang `api.Plugin` của host |
| Concurrency | Không đóng v1 khi lời gọi qua manager chưa hoàn tất |
| Cleanup | URLClassLoader đóng, callbacks/threads/cache được dọn |
| Reload nhiều lần | Không tích lũy old generations vô hạn |
| API evolution | Contract v1/v2 được kiểm tra binary compatibility |
| Artifact verification | Không chạy bytes chưa được approve |
| Rollback | Prepare failure không xóa active v1; post-activation failure có chính sách riêng |

### Test race đáng chú ý

Một thread T1 vào `Manager.invoke` và cố tình block trong v1 `execute`. Thread T2 gọi `replace(v2)`. Trong demo, T2 phải chờ T1 nhả read lock rồi mới close v1. Nếu một test concurrent nhận `CLOSE=v1` **trước khi T1 hoàn thành**, có bug trong cách quản lý ownership/lock hoặc plugin đang chạy theo đường ngoài manager.

Các test concurrency nên dùng `CountDownLatch`/`Phaser` để điều khiển tiến trình thay vì chỉ `Thread.sleep` và đo thời gian; sleep-based tests có thể flaky.

## 22. Thực hành mở rộng sau bài demo

### Bài tập A — thêm phiên bản v3

Tạo `src/v3/plugin/EchoPlugin.java` với behavior `v3:`, biên dịch vào `out/v3`, rồi thay v2→v3 bằng `prepare(Path.of("out/v3"))`. Quan sát class identity khác giữa từng generation và shared API không đổi.

**Kiểm tra:** mỗi phiên bản có static `calls` riêng. Không nên giữ `List<Class<?>> allOldTypes` static chỉ để so sánh tất cả generations trong production.

### Bài tập B — giữ trạng thái nghiệp vụ

Mở rộng `api.Plugin` với `exportState()`/`importState(...)` qua shared DTO chứa số lời gọi. Trước activation, migrate state có schema/version guard. Không truyền trực tiếp instance của `plugin.EchoPlugin` v1 sang plugin v2.

**Kiểm tra:** reload mới tiếp tục counter mong muốn và không giữ old loader reachable qua state object.

### Bài tập C — mô phỏng long-running call

Trong v1, dùng `CountDownLatch` để giữ một lời gọi đang chạy. Trong thread khác, prepare và replace v2. Xác minh v1 không close trước khi lời gọi qua manager hoàn tất. Không dựa vào sleep/console output timing làm điều kiện test duy nhất.

### Bài tập D — lỗi close

Cho `Plugin.close()` ném `RuntimeException` trong v1 và quan sát hành vi `Manager.replace`. Trong thiết kế demo, v2 đã được publish trước khi close v1; exception không rollback active reference. Bổ sung error reporting và cleanup policy tách biệt để manager thông báo chính xác “activation succeeded; retirement failed”.

### Bài tập E — jar đóng gói

Đóng gói hai versions thành hai JAR độc lập bằng `jar --create`. Chỉ cho URLClassLoader v1/v2 biết JAR riêng tương ứng; application classpath chỉ chứa shared API + host.

Ví dụ với output đã biên dịch:

```bash
jar --create --file plugin-v1.jar -C out/v1 .
jar --create --file plugin-v2.jar -C out/v2 .
```

Khi đổi sang JAR, `prepare` phải nhận **đúng URL của JAR file**, không còn URL của thư mục chứa file. Không sửa lệnh mẫu khi vẫn dùng thư mục `out/v1`/`out/v2`; hai chế độ source URLs cần tương ứng.

### Bài tập F — unload diagnostics

Dùng `WeakReference<ClassLoader>` để theo dõi loader cũ sau khi retire và bỏ hết strong references. Bật `-Xlog:class+unload=info` và so sánh. **Không assert bắt buộc weak ref cleared sau một `System.gc()`** vì GC/class unloading không deterministic. Học cách phân tích roots nếu loader vẫn còn.

## 23. Những hiểu lầm cần tránh

| Hiểu lầm | Thực tế |
|---|---|
| “Reload là gọi `loadClass` lần nữa trên loader cũ.” | Runtime class cũ thường được tái sử dụng; muốn generation mới cần loader mới |
| “Sửa JAR tại chỗ là đủ.” | Có thể trộn bytes/resources giữa các generations |
| “Hai class cùng tên nên cùng type.” | Defining loader cũng xác định runtime identity |
| “Tạo L2 trước khi L1 unload là sai.” | Hai runtime classes cùng tên có thể cùng tồn tại bởi hai loaders khác nhau |
| “Mỗi plugin nên tự đóng gói API.” | Shared API type phải được định nghĩa thống nhất ở parent |
| “`URLClassLoader.close()` unload class ngay.” | Close chỉ quản lý loader resources, không ra lệnh GC/unload đồng bộ |
| “Constructor v2 thành công là plugin đã được health-check.” | Constructor không kiểm tra mọi lazy path/dependency |
| “`prepare` không thực thi plugin code.” | `Class.forName(..., true, ...)` và constructor có thể chạy code |
| “Read/write lock xử lý luôn background tasks của plugin.” | Chỉ bảo vệ calls qua manager; plugin-owned tasks cần cleanup riêng |
| “Swap active reference là transaction rollback mọi side effects.” | External side effects và lỗi cleanup cần policy riêng |
| “Static state của v1 sẽ tự chuyển sang v2.” | Mỗi runtime class có static state riêng; migrate qua shared DTO/schema nếu cần |
| “Tôi đã đóng session nên loader chắc chắn GC.” | Cần bỏ tất cả host cache/Class/Method/TCCL/ThreadLocal references; unloading nondeterministic |
| “Chỉ cần TTL là giải quyết old loader leak.” | Phải invalidate theo lifecycle và dừng references/tasks đúng owner |
| “Java ClassLoader là sandbox cho plugin lạ.” | Không; cần process/OS isolation cho threat model cao |

## 24. Bài tập tự kiểm tra

**Câu 1.** Vì sao `new URLClassLoader(...)` cho v2 quan trọng hơn việc sửa `EchoPlugin.class` trên đĩa?

**Đáp án:** Class đã định nghĩa trong L1 gắn với runtime identity của L1; thay file không thay định nghĩa đó. L2 có thể định nghĩa một runtime class mới cùng binary name.

**Câu 2.** Tại sao parent của hai plugin loaders được chọn là `Plugin.class.getClassLoader()`?

**Đáp án:** Để v1/v2 cùng tham chiếu đúng `api.Plugin` mà host dùng; nếu mỗi child định nghĩa API copy, cast/loader constraints có thể sai.

**Câu 3.** Vì sao sau reload in `SAME_BINARY_NAME=true` nhưng `SAME_RUNTIME_CLASS=false`?

**Đáp án:** Tên `plugin.EchoPlugin` giống nhau, nhưng defining loaders L1/L2 là hai objects khác nhau, tạo hai runtime types.

**Câu 4.** Tại sao khi `prepare(out/missing)` thất bại, manager vẫn in `STILL=v1:again:3`?

**Đáp án:** Candidate được dựng ngoài manager; thất bại trước khi `replace` chạy nên active vẫn trỏ v1.

**Câu 5.** Trong demo, read/write lock giải quyết điều gì?

**Đáp án:** Đảm bảo `replace` chờ các lời gọi `invoke` đang giữ read lock hoàn tất trước khi publish v2 và close v1. Nó không quản lý background threads của plugin ngoài manager.

**Câu 6.** Vì sao `CLOSE=v1` không chứng minh class v1 đã unload?

**Đáp án:** Đây chỉ là marker từ plugin lifecycle method. Defining loader còn có thể reachable qua Class token, instance, cache, threads; VM quyết định unloading.

**Câu 7.** Nếu `Plugin.close()` của v1 ném lỗi sau khi current đã được chuyển sang v2, có tự rollback không?

**Đáp án:** Không trong demo. Cần phân biệt activation state và retirement error, thiết kế production error reporting/rollback riêng.

**Câu 8.** Vì sao `AFTER=v2:hello:1` cho thấy static state khác?

**Đáp án:** `calls` thuộc class v2 do loader L2 định nghĩa, độc lập `calls` của v1/L1; lượt gọi đầu của v2 tăng từ 0 lên 1.

**Câu 9.** Nếu host tiếp tục giữ `Class<?> oldType` sau reload, có tác động gì?

**Đáp án:** Token đó có thể giữ runtime class và defining loader L1 reachable, cản việc đủ điều kiện class unloading. Chỉ giữ tạm để debug/test.

**Câu 10.** Vì sao plugin JAR nên immutable sau khi đã verified và đưa vào loader?

**Đáp án:** Tránh TOCTOU, class/resource bytes trộn nhiều versions và khó xác minh nguồn; mỗi generation đọc từ snapshot của đúng release.

**Câu 11.** Nếu v2 cần giữ state v1, có nên cast trực tiếp instance v1 sang implementation class v2 không?

**Đáp án:** Không. Hai implementation types khác defining loader/identity. Dùng shared DTO hoặc versioned serialization schema để migrate state.

**Câu 12.** Nếu plugin tự tạo thread chạy liên tục, chỉ dùng manager write lock có đảm bảo old plugin dừng không?

**Đáp án:** Không. Phải có explicit shutdown/cancellation/await cho plugin-owned thread/executor cùng cleanup TCCL/ThreadLocal.

## 25. Tổng kết và nguồn tham khảo

**Ghi nhớ quy trình đúng:**

1. **Giữ shared API ở parent.**
2. **Build v1/v2 thành những artifacts độc lập** với cùng implementation binary name nhưng loader generations khác nhau.
3. **Verify và prepare v2** trước khi thay active; nếu prepare fail, giữ v1 phục vụ.
4. **Quiesce/drain old calls** bằng lock hoặc generation leases được thiết kế đúng.
5. **Publish v2 có kiểm soát**, rồi retire v1 và đóng resources.
6. **Xóa roots tới old generation** để JVM có cơ hội GC loader và unload classes; đừng đòi unload tức thì.
7. **Quan sát và kiểm thử** behavior, class identity, API compatibility, errors và resource lifecycle.

Tài liệu chuẩn:

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, delegation, `findLoadedClass`, runtime class identity.
- [Java SE 17 — URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): tạo loader theo URL, named constructor, `close()`, cảnh báo concurrency.
- [Java SE 17 — ReentrantReadWriteLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html): read/write locking cho lifecycle handoff.
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `forName`, `getClassLoader` và runtime type tokens.
- [JLS 17 — §§12.2, 12.4, 12.7](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): loading, initialization và unloading.
- [JVMS 17 — §5.3 Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): defining/initiating loaders và loading constraints.
- [Java SE 17 — java command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xlog:class+load`, `-Xlog:class+unload` và JVM diagnostics.