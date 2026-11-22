# Ranh giới của hot reload và trạng thái đang được sử dụng

## 1. Hot reload thực sự thay đổi điều gì?

**Hot reload plugin** trong cùng JVM thường được triển khai bằng cách tạo một ClassLoader mới, nạp implementation phiên bản mới, rồi chuyển những yêu cầu mới sang instance mới mà không restart toàn bộ ứng dụng. Nhưng thay đổi một biến trỏ đến plugin **không tự cập nhật** code, object, stack frame hay trạng thái mà những yêu cầu đang chạy đã nhận trước đó.

Với `URLClassLoader` và plugin JAR, cần phân biệt:

| Đối tượng/công việc | Khi chuyển từ v1 sang v2 |
|---|---|
| Lượt nhận request mới | Có thể định tuyến sang provider v2 |
| Request đã cầm reference tới provider v1 | Vẫn dùng object/class v1 nếu không có logic chuyển riêng |
| Runtime class `plugin.EchoPlugin` đã được loader v1 định nghĩa | Không đổi bytecode theo file JAR mới |
| Static field của implementation v1 | Không tự copy sang static field của implementation v2 |
| Session, callback, stream, thread do v1 tạo | Không tự hủy hoặc chuyển ownership |
| Database, file, message broker | Không tự migrate hoặc rollback vì đã thay loader |
| `URLClassLoader.close()` | Đóng nguồn lookup/JAR handles, không bảo đảm class unloading |

**Ranh giới cốt lõi:** *Chuyển tuyến cho công việc tương lai* khác với *hoàn tất, di chuyển hoặc hủy công việc/trạng thái hiện tại*. Một plugin system an toàn cần có protocol về **version/generation, pinning, drain/quiescence, migration và disposal**, không chỉ `new URLClassLoader(...)`.

## 2. Vì sao phiên bản mới cần defining loader mới?

JVM định danh một runtime class bằng **(binary name, defining loader)**. Khi `demo.plugin.EchoPlugin` V1 và V2 được **hai loader riêng thực sự định nghĩa**, chúng có thể cùng tồn tại nhưng không phải cùng `Class<?>`, nên object/static fields của V1 không tự biến thành V2. Cả hai phải implement API/DTO do **host/shared parent** định nghĩa để giao tiếp bình thường. Gọi lại `loadClass` trên loader cũ hoặc thay file JAR không tự redefine code; instrumentation là cơ chế khác với các giới hạn riêng. Phân biệt này là nền để bài tập dưới đây xét **state đã pin vào từng generation**.

## 3. Định nghĩa một Generation và ranh giới sử dụng

Một **generation** là tập hợp có cùng lifecycle:

- ID/version của bản plugin và artifact bất biến.
- ClassLoader dùng để nạp bản đó.
- Provider instance và implementation classes của bản đó.
- Bộ đếm các lượt sử dụng (*leases*, *in-flight*).
- Trạng thái vòng đời: ACTIVE, RETIRING, QUIESCENT, CLOSED.
- Các tài nguyên do generation quản lý: stream, callback, scheduler, executor, service registrations.

Một request **acquire** generation trước khi bắt đầu công việc và **release** sau khi đã hoàn toàn không còn sử dụng nó. Khi reload, host đổi nơi cấp lease mới sang v2; v1 chuyển sang **RETIRING**. Chỉ khi v1 không còn lease và không còn hoạt động ngoài lease, mới đóng nguồn class/resource của v1.

~~~text
Thời điểm t0: current = v1
  Request A -> acquire(v1) ------------------------- release(v1)
                        |
Thời điểm t1:           +-- reload / current = v2
                            Request B -> acquire(v2) -- release(v2)

v1 không cấp lease mới sau t1.
v1 có thể phục vụ A sau t1.
v1 chỉ close khi A thực sự hoàn tất và tài nguyên v1 đã được dọn.
~~~

**Không dùng `currentPlugin = newPlugin; oldLoader.close();` ngay sau đó** khi vẫn có task đang sử dụng v1. Theo Java SE 17, nếu một thread đang nạp class qua `URLClassLoader` khi thread khác gọi `close()`, kết quả của lần nạp đồng thời đó **không xác định**. Class đã nạp có thể vẫn hoạt động, nhưng lần đầu cần dependency/resource mới sau close có thể thất bại.

## 4. Tách các loại trạng thái trước khi reload

### 4.1. State nằm trong loader cũ

Object fields, static fields trong implementation, caches, `Class<?>`, reflection metadata, private singletons và phiên xử lý của v1 có thể vẫn được giữ bởi các request hoặc host. Khi class implementation v2 được loader mới định nghĩa, **static fields v2 là các fields khác**, kể cả khi mã nguồn khai báo giống hệt nhau.

### 4.2. State do host sở hữu

Shared DTO/API types, singleton ở loader parent, HTTP router, session repository, thread pool dùng chung, các bảng định tuyến generation và caches host có thể tồn tại qua reload. Chúng là **nguồn tương thích hoặc nguồn leak**, tùy có vô tình giữ old instance/class hay không.

### 4.3. State bên ngoài JVM

Database, message broker, files, distributed cache và external sessions sống độc lập với ClassLoader. Chúng không tự hỗ trợ hot migration. Nếu v1 và v2 cùng ghi vào schema đang thay đổi, có thể xảy ra lỗi nghiệp vụ ngay cả khi classloading hoàn toàn chính xác.

**Kết luận về state:** “Code v2 đã sẵn sàng” không đồng nghĩa “dữ liệu/sessions/jobs đã chuyển an toàn”. Hãy thiết kế migration protocol riêng, có versioned schema và rollback policy.

## 5. Ví dụ Java 17+: hai phiên bản plugin với một interface chung

Bài thực nghiệm sẽ chứng minh bằng stdout xác định:

1. Request A lấy plugin v1 trước reload và chạy với v1.
2. Sau reload, request B mới lấy v2.
3. v1 và v2 có implementation class cùng FQCN nhưng khác runtime identity.
4. Hai implementation dùng **một API type chung** của parent.
5. Request A còn giữ v1 vẫn gọi được v1 sau cutover.
6. Static counter của v2 bắt đầu lại, không lấy counter của v1.
7. Loader v1 chỉ đóng sau khi request A release lease; loader v2 đóng khi manager dừng.

### 5.1. Cấu trúc thư mục

~~~text
hot-reload-demo/
├── api-src/
│   └── demo/api/PluginService.java
├── host-src/
│   └── HotReloadDemo.java
├── v1-src/
│   └── demo/plugin/EchoPlugin.java
├── v2-src/
│   └── demo/plugin/EchoPlugin.java
├── v1-resources/
│   └── META-INF/services/demo.api.PluginService
└── v2-resources/
    └── META-INF/services/demo.api.PluginService
~~~

Hai file `EchoPlugin.java` có cùng package/FQCN nhưng nội dung khác và được biên dịch **vào hai output directories riêng biệt**, sau đó đóng thành hai JAR riêng. Khi chạy, **chỉ API và host** có trên application classpath.

### 5.2. Shared API

File **`api-src/demo/api/PluginService.java`**:

~~~java
package demo.api;

public interface PluginService {
    String version();
    String handle(String input);
}
~~~

Không để implementation-only classes của plugin lộ ra trong chữ ký API nếu host cần gọi qua nhiều loaders. Các DTO/exception/callback mà cả hai bên trao đổi cũng nên do loader chung định nghĩa.

### 5.3. Plugin v1

File **`v1-src/demo/plugin/EchoPlugin.java`**:

~~~java
package demo.plugin;

import demo.api.PluginService;

public final class EchoPlugin implements PluginService {
    private static int calls;

    public EchoPlugin() {
    }

    @Override
    public String version() {
        return "v1";
    }

    @Override
    public String handle(String input) {
        return "v1#" + (++calls) + ":" + input;
    }
}
~~~

`calls` là static state thuộc class v1. Demo thực hiện các lời gọi tuần tự; `++calls` không thread-safe nếu plugin xử lý nhiều requests song song. Production cần `AtomicInteger` hoặc cơ chế đồng bộ thích hợp.

### 5.4. Plugin v2

File **`v2-src/demo/plugin/EchoPlugin.java`**:

~~~java
package demo.plugin;

import demo.api.PluginService;

public final class EchoPlugin implements PluginService {
    private static int calls;

    public EchoPlugin() {
    }

    @Override
    public String version() {
        return "v2";
    }

    @Override
    public String handle(String input) {
        return "v2#" + (++calls) + ":" + input;
    }
}
~~~

Giá trị static counter v2 bắt đầu từ 0 trong runtime class v2, độc lập với số lời gọi mà v1 đã xử lý.

### 5.5. Service descriptor

Cả hai file:

- `v1-resources/META-INF/services/demo.api.PluginService`
- `v2-resources/META-INF/services/demo.api.PluginService`

đều chứa đúng một dòng:

~~~text
demo.plugin.EchoPlugin
~~~

`ServiceLoader.load(PluginService.class, child)` sẽ tìm provider trong JAR nhìn thấy bởi `child`. Interface `PluginService` được parent loader định nghĩa nên v1/v2 đều có cùng API identity.

### 5.6. Host quản lý lease và generation

File **`host-src/HotReloadDemo.java`**:

~~~java
import demo.api.PluginService;

import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ServiceLoader;

public final class HotReloadDemo {
    private HotReloadDemo() {
    }

    private static final class Generation {
        final URLClassLoader loader;
        final PluginService provider;
        final String version;

        private int leases;
        private boolean retiring;
        private boolean closed;

        private Generation(URLClassLoader loader, PluginService provider) {
            this.loader = loader;
            this.provider = provider;
            this.version = provider.version();
        }

        static Generation load(Path jar) throws IOException {
            Path file = jar.toAbsolutePath().normalize();
            if (!Files.isRegularFile(file)) {
                throw new IllegalArgumentException("Missing JAR: " + file);
            }

            URL[] urls = {file.toUri().toURL()};
            ClassLoader parent = PluginService.class.getClassLoader();
            URLClassLoader child = new URLClassLoader(urls, parent);

            try {
                PluginService plugin =
                        ServiceLoader.load(PluginService.class, child)
                                .findFirst().orElseThrow();
                if (plugin.getClass().getClassLoader() != child) {
                    throw new IllegalStateException(
                            "Provider must be defined by child");
                }
                return new Generation(child, plugin);
            } catch (RuntimeException | Error problem) {
                try {
                    child.close();
                } catch (IOException cleanup) {
                    problem.addSuppressed(cleanup);
                }
                throw problem;
            }
        }

        synchronized void pin() {
            if (retiring) {
                throw new IllegalStateException("Generation retiring");
            }
            leases++;
        }

        synchronized void unpin() throws IOException {
            if (leases <= 0) {
                throw new IllegalStateException("Unbalanced release");
            }
            leases--;
            closeIfIdle();
        }

        synchronized void retire() throws IOException {
            retiring = true;
            closeIfIdle();
        }

        private void closeIfIdle() throws IOException {
            if (retiring && leases == 0 && !closed) {
                closed = true;
                loader.close();
                System.out.println("loader closed: " + version);
            }
        }
    }

    private static final class Session implements AutoCloseable {
        private final Generation generation;
        private boolean closed;

        Session(Generation generation) {
            this.generation = generation;
        }

        synchronized String call(String input) {
            if (closed) {
                throw new IllegalStateException("Session closed");
            }
            return generation.provider.handle(input);
        }

        synchronized Class<?> implementationClass() {
            if (closed) {
                throw new IllegalStateException("Session closed");
            }
            return generation.provider.getClass();
        }

        synchronized Class<?> apiType() {
            if (closed) {
                throw new IllegalStateException("Session closed");
            }
            return generation.provider.getClass().getInterfaces()[0];
        }

        @Override
        public synchronized void close() throws IOException {
            if (!closed) {
                closed = true;
                generation.unpin();
            }
        }
    }

    private static final class PluginManager implements AutoCloseable {
        private Generation current;

        PluginManager(Path initialJar) throws IOException {
            current = Generation.load(initialJar);
        }

        synchronized Session open() {
            if (current == null) {
                throw new IllegalStateException("Manager closed");
            }
            current.pin();
            return new Session(current);
        }

        synchronized void reload(Path jar) throws IOException {
            if (current == null) {
                throw new IllegalStateException("Manager closed");
            }

            // Candidate nạp thành công rồi mới publish.
            Generation next = Generation.load(jar);
            Generation old = current;
            current = next;
            old.retire();
        }

        @Override
        public synchronized void close() throws IOException {
            if (current != null) {
                Generation old = current;
                current = null;
                old.retire();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: HotReloadDemo <v1.jar> <v2.jar>");
        }

        Path v1 = Path.of(args[0]);
        Path v2 = Path.of(args[1]);

        try (PluginManager manager = new PluginManager(v1)) {
            try (Session held = manager.open()) {
                Class<?> oldImpl = held.implementationClass();

                System.out.println("before reload: " + held.call("A"));
                manager.reload(v2);

                try (Session fresh = manager.open()) {
                    System.out.println("after reload: "
                            + fresh.call("B"));
                    System.out.println("same implementation class: "
                            + (oldImpl == fresh.implementationClass()));
                    System.out.println("shared API identity: "
                            + (held.apiType() == fresh.apiType()));
                }

                System.out.println("old pinned: " + held.call("C"));

                // Lease cuối của v1 kết thúc: bây giờ loader v1 đóng.
                held.close();
            }

            try (Session next = manager.open()) {
                System.out.println("new next: " + next.call("D"));
            }
        }
    }
}
~~~

**Tính chất trong ví dụ:**

- `PluginManager.open()/reload()` cùng `synchronized` nên thao tác chọn generation và tăng lease không bị chen bởi cutover.
- Một `Session` giữ `Generation` đã acquire. Nó **không** tra cứu lại `current` sau mỗi lời gọi.
- `Session.call()` và `Session.close()` cùng synchronized trên một session, tránh close cùng session xen giữa một lời gọi đồng bộ.
- `Generation.retire()` ngừng cấp lease mới và chỉ close loader nếu `leases == 0`.
- `Generation.load` đóng candidate loader nếu discovery provider lỗi trước khi publish; current cũ vẫn được giữ.
- `PluginManager.reload` nạp candidate **trong lock**, vì vậy các `open()` mới có thể tạm đợi. Production nên cân nhắc prepare/health-check candidate ngoài lock rồi commit bằng một bước ngắn/atomic.
- Đây là **mô hình synchronous**: lease chỉ theo dõi những công việc host biết, không tự thu hồi plugin thread, callback, `CompletableFuture` hoặc tài nguyên bên ngoài.

Một lưu ý xử lý lỗi: trong mã demo, nếu `old.retire()` ném `IOException` lúc đóng loader cũ sau cutover, `current` **đã trỏ tới v2**. Production phải ghi nhận rõ trạng thái partially successful cutover và close failure, thay vì báo “reload thất bại, vẫn ở v1” một cách sai sự thật.

## 6. Biên dịch và chạy Java 17+

Yêu cầu JDK 17+, đứng tại thư mục `hot-reload-demo/`, tạo đúng các tệp như trên.

### Bash (Linux/macOS/Git Bash)

~~~bash
mkdir -p build/api build/host build/v1 build/v2 dist

javac -encoding UTF-8 -d build/api \
  api-src/demo/api/PluginService.java

javac -encoding UTF-8 -cp build/api -d build/host \
  host-src/HotReloadDemo.java

javac -encoding UTF-8 -cp build/api -d build/v1 \
  v1-src/demo/plugin/EchoPlugin.java

javac -encoding UTF-8 -cp build/api -d build/v2 \
  v2-src/demo/plugin/EchoPlugin.java

cp -R v1-resources/META-INF build/v1/
cp -R v2-resources/META-INF build/v2/

jar --create --file dist/v1.jar -C build/v1 .
jar --create --file dist/v2.jar -C build/v2 .

java -cp "build/api:build/host" \
  HotReloadDemo dist/v1.jar dist/v2.jar
~~~

### Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force build/api,build/host,build/v1,build/v2,dist | Out-Null

javac -encoding UTF-8 -d build/api api-src/demo/api/PluginService.java

javac -encoding UTF-8 -cp build/api -d build/host host-src/HotReloadDemo.java

javac -encoding UTF-8 -cp build/api -d build/v1 v1-src/demo/plugin/EchoPlugin.java

javac -encoding UTF-8 -cp build/api -d build/v2 v2-src/demo/plugin/EchoPlugin.java

Copy-Item v1-resources/META-INF -Destination build/v1 -Recurse -Force
Copy-Item v2-resources/META-INF -Destination build/v2 -Recurse -Force

jar --create --file dist/v1.jar -C build/v1 .
jar --create --file dist/v2.jar -C build/v2 .

java -cp "build/api;build/host" HotReloadDemo dist/v1.jar dist/v2.jar
~~~

Kiểm tra JAR:

~~~bash
jar --list --file dist/v1.jar
jar --list --file dist/v2.jar
~~~

Mỗi JAR phải có ít nhất `demo/plugin/EchoPlugin.class` và `META-INF/services/demo.api.PluginService`. Không đóng gói API trong plugin JAR và không đặt plugin JAR vào classpath host của lệnh `java`.

### Stdout chính xác

~~~text
before reload: v1#1:A
after reload: v2#1:B
same implementation class: false
shared API identity: true
old pinned: v1#2:C
loader closed: v1
new next: v2#2:D
loader closed: v2
~~~

Diễn giải:

1. Session cũ nhận v1 nên output đầu là `v1#1:A`.
2. Sau reload, lượt acquire mới nhận v2; counter v2 bắt đầu từ 1.
3. Class của hai implementation không bằng nhau vì **defining loader khác nhau**.
4. Interface API mà hai implementations trực tiếp implements là cùng `PluginService.class` do parent định nghĩa.
5. Session cũ vẫn nhận `v1#2:C` sau khi current chuyển v2.
6. Chỉ khi `held.close()` giải phóng lease cuối của v1 mới có `loader closed: v1`.
7. Lượt mới sau đó dùng v2 và tăng counter v2 lên 2.
8. Khi manager kết thúc, loader v2 được đóng sau các session cuối cùng.

## 7. Cutover không chuyển đối tượng cũ sang class mới

Bước cutover về bản chất là đổi mapping cho **lượt xin lease tiếp theo**:

~~~java
// Trích mã từ PluginManager.reload.
Generation next = Generation.load(jar);
Generation old = current;
current = next;
old.retire();
~~~

Đây không phải cơ chế di chuyển code của stack frame hay object đang sống. Một object v1 vẫn là instance của class v1; static fields của class v1 vẫn thuộc defining loader v1. Hai class implementation cùng FQCN được hai loaders định nghĩa có thể tồn tại **đồng thời** trong JVM.

Đổi `current` không đảm bảo sau thời điểm cutover tất cả response đều do v2 tạo. Request v1 đã acquire trước cutover có thể hoàn tất sau đó. Với các hệ thống cần **strict version switch**, phải drain v1 trước khi publish v2 hoặc áp dụng session affinity/transaction boundary phù hợp.

## 8. Race nguy hiểm trong reference counting

Một mô hình ngây thơ:

~~~java
// Mã minh họa không an toàn nếu swap đồng thời.
Generation generation = current.get();
generation.active.incrementAndGet();
~~~

Giữa hai dòng, thread reload có thể đổi `current` sang v2, thấy count v1 đang 0 rồi close v1. Thread A mới tăng counter quá muộn và dùng loader đã đóng.

Mấu chốt không phải “có AtomicInteger là đủ”, mà là **acquire generation và ghi nhận quyền sử dụng phải nằm trong một giao thức đồng bộ** với retire/close.

Ví dụ `synchronized open()/reload()` là một giải pháp đơn giản, dễ chứng minh: việc chọn current và pin diễn ra trong một critical section; reload không thể retire cùng generation giữa hai thao tác. Các hệ thống lớn có thể dùng ReadWriteLock, CAS state machine, epoch reclamation hoặc versioned router, nhưng phải chứng minh không có race acquire-vs-retire.

Release cũng phải **exactly once**; đặt trong `try-with-resources` hoặc `finally` để exception không làm pin cũ bị giữ vô hạn. Nếu dùng asynchronous APIs, lease phải kéo dài đến khi mọi việc phụ thuộc generation thực sự xong.

## 9. Định nghĩa “không còn ai dùng v1” cẩn thận

Một plugin có thể còn hoạt động sau khi request handler trả về:

- `CompletableFuture`, background callbacks, asynchronous stream processing.
- Scheduled jobs, event bus subscriptions, message consumers.
- Thread pool tasks đang queue hoặc đang chạy.
- `ThreadLocal` và Thread Context ClassLoader (TCCL) còn giữ loader cũ.
- Listener, `Class<?>`, reflection `Method`, lambdas, proxies và cache của host.
- Stream/socket/file/JAR handle do plugin tự mở.
- Object do plugin v1 trả về, được caller giữ ngoài lease.
- Resources thuộc database/caches ngoài JVM.

Nếu một plugin trả `CompletionStage` nhưng còn xử lý bất đồng bộ, release lease **ngay khi nhận stage** có thể đóng loader quá sớm. Cần giữ ownership tới completion/cancellation thật sự và cleanup cả những task phụ thuộc.

Một manager không thể dựa vào `URLClassLoader.close()` để tự kết thúc thread hay listener. Nếu không quản lý các resources ấy, dù ref-count sessions về 0 thì hệ thống **vẫn chưa quiescent**.

## 10. Quiesce, drain và disposal an toàn

~~~text
ACTIVE v1
   |
   | chuẩn bị, validate v2 trước
   v
READY v2
   |
   | cutover atomic, v1 ngừng cấp lease mới
   v
RETIRING v1 + ACTIVE v2
   |
   | drain task v1 và ngừng scheduler/listener v1
   v
QUIESCENT v1
   |
   | close resource do plugin sở hữu, restore TCCL
   | close URLClassLoader, drop references
   v
CLOSED v1
~~~

Đừng coi `ExecutorService.shutdown()` là đã drain xong: phương thức này chỉ ngừng nhận task mới; còn phải `awaitTermination(...)` hoặc theo dõi Futures/in-flight tasks, với timeout và chính sách cancellation rõ ràng.

**Không tự close loader ngay khi timeout** nếu code cũ vẫn có khả năng thực thi/nạp thêm class. Nếu buộc hard-stop plugin không tin cậy, ranh giới tiến trình riêng thường thực tế hơn ClassLoader trong cùng JVM.

`URLClassLoader.close()` đóng nguồn tìm class/resource của chính loader và các file do loader mở, nhưng **không unload ngay** những class đã định nghĩa. Class cũ còn reachable vẫn tồn tại; code cũ còn cần dependency chưa load có thể thất bại sau close. Nếu class loading xảy ra đồng thời với close, Javadoc gọi kết quả là **undefined**.

## 11. State migration phải là hợp đồng riêng

V1 và v2 có thể có các static fields, object graphs, caches và session data hoàn toàn khác nhau. Java không copy các fields đó giữa hai loaders. Không ép kiểu `EchoPlugin` v1 sang `EchoPlugin` v2 rồi mong chuyển state: runtime types khác nhau.

Một giao thức migration thường gồm:

1. Freeze/quiesce vùng state cần snapshot.
2. Export qua DTO/schema ổn định do host/API sở hữu.
3. Version và validate snapshot; transform dữ liệu nếu cần.
4. Import/restore vào v2 trước cutover hoặc theo chính sách phiên.
5. Cutover theo consistency model đã thống nhất.
6. Dọn old state sau khi không còn yêu cầu v1.

Với state bền vững, ưu tiên database/event log hoặc một format được version hóa thay vì serialize object implementation. Java native serialization không tự đảm bảo class loader compatibility, schema migration hay độ an toàn cho dữ liệu không tin cậy.

Nếu v1/v2 chạy chồng thời gian, **không được mặc nhiên** để cả hai ghi cùng database schema hoặc queue offsets theo các contract khác nhau. Cần backward/forward compatibility, idempotency, event versioning, ownership của background jobs và rollback rules.

## 12. Rollback và lỗi trong hai thời điểm khác nhau

**Candidate lỗi trước publish:** Hãy đóng candidate loader, giữ current v1 và báo lỗi. Không đổi router sang v2 chưa sẵn sàng. Demo làm như vậy với lỗi provider discovery.

**Lỗi sau publish:** Router đã trỏ tới v2, có thể còn in-flight v1/v2. Rollback cần lựa chọn:

- Giữ v1 dạng standby nếu policy cho phép và chưa đóng; vẫn phải quản lý leases/resources.
- Hoặc tạo **generation v1 mới** từ artifact cũ đã lưu, không “hồi sinh” bytecode/class object v1 cũ.
- Nếu migration database đã không tương thích ngược, rollback code đơn thuần có thể không an toàn. Cần restore state, compensating transaction hoặc forward fix.

Một close failure của old loader sau cutover không đồng nghĩa cutover thất bại. Cần log chính xác **phase** thất bại và trạng thái current thật, tránh retry mù quáng tạo nhiều generations.

## 13. TCCL, ServiceLoader và API identity

Nếu framework dùng `ServiceLoader.load(service)` hoặc tìm resources qua TCCL, đặt plugin loader trong phạm vi invocation **trên chính thread thực thi**, rồi restore trong `finally`. Plugin provider types phải sử dụng shared API của parent; đối với JPMS, có thêm module layer/service declarations. Không để worker thread cũ giữ TCCL V1 sau cutover.

## 14. Leak và trạng thái JVM toàn cục

Dấu hiệu cần theo dõi qua nhiều lượt reload: các request vẫn trả kết quả V1, classloader/Metaspace tăng, worker threads còn chạy, JAR handles chưa đóng, các registration/`ServiceLoader` caches còn trỏ V1. Đối chiếu generation của request và defining loader trước khi kết luận cutover hỏng; dùng thread/heap dumps và GC-root paths để tìm references giữ V1. Đóng loader không đồng nghĩa unload ngay, và không thể dùng một lần `System.gc()` để xác nhận sạch.

## 15. Khi nào nên tránh hot reload?

Restart/rolling deployment có thể an toàn hơn khi:

- Shared API thay đổi không tương thích nhị phân (`NoSuchMethodError`, `AbstractMethodError`, `LinkageError`).
- Plugin dùng JNI/native libraries hoặc trạng thái process-global khó gỡ.
- Nhiều long-lived sessions cần đảm bảo một version thống nhất.
- Schema migration không hỗ trợ coexistence giữa v1 và v2.
- Plugin sinh thread và side effects mà host không thể kiểm soát.
- Resource ownership chưa rõ; không thể chứng minh quiescence.
- Cần rollback toàn hệ thống theo giao dịch hoặc ranh giới bảo mật mạnh.

Không ép hot reload nếu giá trị kinh doanh không bù được độ phức tạp về lifecycle và consistency.

## 16. Checklist triển khai

1. Shared API/DTO/exception có **một runtime identity** do loader chung định nghĩa?
2. Mỗi version có artifact bất biến, loader và generation ID riêng?
3. Candidate được load/validate/health-check trước publish?
4. Acquire lease + chọn current có đồng bộ với retire/cutover?
5. Lease bao trùm mọi việc đồng bộ và bất đồng bộ thực sự dùng plugin?
6. State migration/serialization có version và schema kiểm chứng được?
7. Có ngừng task mới, drain tasks cũ và dọn callback/thread/TCCL?
8. Có xử lý close failure, timeout, stuck tasks và rollback theo phase?
9. Dữ liệu ngoài JVM có cho phép v1/v2 coexist không?
10. Có metrics theo generation và leak detection đủ để xác nhận cleanup?
11. Có chính sách fallback restart khi hot reload không an toàn?

## 17. Tự kiểm tra

**Câu 1.** Request A đã nhận plugin v1 rồi host reload v2. A có tự chạy code v2 không?

**Đáp án:** Không. Reference và runtime class v1 của A không tự thay đổi.

**Câu 2.** Vì sao hai class `demo.plugin.EchoPlugin` từ v1/v2 có cùng tên mà `==` false?

**Đáp án:** Chúng được hai defining loaders khác nhau định nghĩa.

**Câu 3.** v2 có kế thừa static field `calls` của v1 không?

**Đáp án:** Không. Static fields của hai runtime classes độc lập; muốn chuyển state phải có migration rõ.

**Câu 4.** Sau khi current đổi sang v2, có được gọi `oldLoader.close()` ngay không?

**Đáp án:** Chỉ khi v1 thật sự quiescent, không còn task nào cần load class/resource hoặc dùng nguồn mà loader sở hữu; việc còn in-flight phải drain.

**Câu 5.** `CompletableFuture` chưa hoàn thành nhưng handler đã return, có thể release lease không?

**Đáp án:** Không nếu công việc bất đồng bộ còn phụ thuộc plugin; lease phải kéo dài tới khi việc sử dụng kết thúc.

**Câu 6.** Nếu v2 candidate lỗi trước publish, nên làm gì?

**Đáp án:** Dọn candidate và giữ current v1, không đổi định tuyến sang v2 chưa sẵn sàng.

**Câu 7.** Có đảm bảo không xuất hiện response v1 sau cutover?

**Đáp án:** Không nếu request v1 đã pin. Cần strict drain hoặc session-affinity policy nếu nghiệp vụ đòi hỏi.

## 18. Nguồn chính thức

- [Java SE 17 — URLClassLoader.close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html#close()) — close, JAR handles và class loading đồng thời.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html) — class identity, delegation.
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html) — provider discovery.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html) — shutdown và awaitTermination.
- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html) — tài nguyên/lease có phạm vi.
- [JVMS 17, Chương 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html) — loading, linking, initialization.

**Điểm cần nhớ:** Hot reload bằng ClassLoader mới chỉ thay đổi nơi **yêu cầu tương lai** lấy code. Công việc đang sử dụng v1 phải được **pin, drain và release đúng thời điểm**; state migration và side effects bên ngoài JVM phải có giao thức riêng.