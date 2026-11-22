# Thay phiên bản plugin bằng loader mới trong Java

> **Java Core → ClassLoader → Kiến trúc plugin.** Khi một plugin được cập nhật từ phiên bản V1 sang V2, cách đúng để có **runtime classes mới** thường là tạo **class loader thế hệ mới**, nạp và kiểm tra phiên bản mới, chuyển luồng request sang thế hệ mới, rồi dừng và giải phóng thế hệ cũ. Không dùng `defineClass` lần thứ hai trong loader cũ, không kỳ vọng `URLClassLoader.close()` tự unload mọi class, và không đóng loader trước khi những tác vụ đang chạy với plugin cũ hoàn tất.

## 1. Câu trả lời ngắn

Quy trình khuyến nghị:

~~~text
     Host + Shared API (sống xuyên nhiều lần cập nhật)
                      |
                      v
                Plugin Registry
                      |
       phiên bản đang active: Generation V1
                      |
   (1) chuẩn bị V2 trong URLClassLoader MỚI
   (2) verify artifact / load / instantiate / health check
   (3) atomic routing cutover: active = V2
   (4) không nhận yêu cầu mới cho V1
   (5) drain in-flight V1 / stop timers / unregister callbacks
   (6) close V1 instances và V1 loader-owned resources
   (7) bỏ strong references tới V1
                      |
                      v
            Generation V2 phục vụ
~~~

**Bất biến quan trọng:**

1. Mỗi runtime class có định danh theo **(binary name, defining loader)**. Class `plugin.impl.Handler` do loader V1 định nghĩa và `plugin.impl.Handler` do loader V2 định nghĩa là **hai runtime types khác nhau** dù tên giống hệt.
2. Các **shared API types** dùng để giao tiếp host↔plugin phải được định nghĩa bởi **một loader chung** (thường là host/parent), nếu muốn cast và gọi interface bình thường.
3. Không sửa JAR trên disk rồi đợi JVM tự dùng bytecode mới cho một `Class<?>` đã có. JVM không coi việc đổi file là lệnh redefine class.
4. Thời điểm **publish V2** và thời điểm **retire V1** khác nhau. Nếu có request V1 đang chạy, không được close resources/loader V1 một cách thiếu phối hợp.
5. `URLClassLoader.close()` giải phóng các file/JAR handles thuộc loader; các lớp và instances đã tạo **có thể vẫn hoạt động** nếu được giữ tham chiếu. Không có deadline chắc chắn cho class unloading.
6. Nếu chuẩn bị V2 thất bại, **giữ V1 làm active**; nếu V2 đã publish nhưng cleanup V1 thất bại, đó là một **retirement failure**, không có nghĩa V2 chưa được publish.

## 2. Vì sao phải thay loader thay vì gọi `loadClass` lại?

Với `ClassLoader` thông thường, load một binary name nhiều lần bằng cùng loader phải giữ **cùng runtime `Class<?>`**. Ví dụ:

~~~java
Class<?> first = loader.loadClass("plugin.impl.Handler");
Class<?> again = loader.loadClass("plugin.impl.Handler");

System.out.println(first == again); // true nếu cả hai thành công
~~~

Đây là **snippet** cần biến `loader`. Việc bạn build lại JAR và ghi đè file `Handler.class` không khiến `again` trở thành runtime class mới, vì loader đã nạp tên đó.

Cố gọi `defineClass` lần thứ hai với cùng binary name **trong chính defining loader** sẽ bị từ chối (thường là `LinkageError`). `resolveClass` chỉ yêu cầu linking, không reset trạng thái hay static initializer. `Class.forName` cũng không phải reload API.

Ngược lại:

~~~java
Class<?> oldType = loaderV1.loadClass("plugin.impl.Handler");
Class<?> newType = loaderV2.loadClass("plugin.impl.Handler");

System.out.println(oldType.getName().equals(newType.getName())); // true
System.out.println(oldType == newType);                            // false
~~~

**Dòng cuối chỉ chắc chắn false nếu mỗi loader thực sự tự define bản class của mình.** Nếu hai loader cùng delegate tên `plugin.impl.Handler` về parent, cả hai có thể trả cùng `Class<?>`. Khi thiết kế hot swap phải biết **defining loader** thực tế, không chỉ tạo hai đối tượng loader có tên khác nhau.

### 2.1. Phân biệt versioned runtime class với JVM instrumentation

Java agent/instrumentation có `redefineClasses`/`retransformClasses` trong những giới hạn được đặc tả, chủ yếu để thay method bytecode trên những classes đã được nạp. Đó là cơ chế **khác** và không phải cách phổ quát để cập nhật một plugin với thay đổi API, constructor, fields, module/package layout hoặc dependencies.

Với plugin architecture ứng dụng thông thường, **một loader mới cho một generation mới** giúp cô lập static fields, dependency graph và class identity rõ ràng hơn. Nhưng loader mới tự nó **không** thực hiện data migration, switch routing, cleanup hay đảm bảo thread-safety.

## 3. Ranh giới host ↔ plugin: giữ đúng một shared contract

Giả sử host biết interface:

~~~java
package api;

public interface Plugin extends AutoCloseable {
    String version();

    @Override
    default void close() { }
}
~~~

**Tệp `api/Plugin.java`** trên Java 17+; ở production, `close()` có thể cần giải phóng resources và có contract lỗi rõ ràng. `Plugin` này phải được nạp bởi **shared/host loader** mà cả host và plugin cùng sử dụng.

Kiến trúc:

~~~text
                          Host loader
                    defines api.Plugin
                         /         \
                        /           \
              Plugin loader V1    Plugin loader V2
              defines:             defines:
              plugin.impl.Versioned plugin.impl.Versioned
              libraries V1         libraries V2

           Plugin.class của host == Plugin.class của V1
           Plugin.class của host == Plugin.class của V2

           Versioned.class ở V1 != Versioned.class ở V2
~~~

Quy tắc:

- **Shared contracts:** interfaces, DTOs, annotations và exceptions thật sự đi qua boundary nên ở host/shared loader với versioning rõ ràng.
- **Implementation và private dependencies:** ở loader của từng plugin generation; có thể khác version giữa V1 và V2.
- **Không đóng gói lại API của host vào plugin JAR** theo cách child-first loader tự define `api.Plugin`, nếu host cần cast plugin về `api.Plugin`.
- **Không chia sẻ bừa object của private class V1 với V2:** `plugin.impl.Versioned` của V1 không cast được thành cùng-named `Versioned` của V2.
- Nếu cần giao tiếp giữa các generations, dùng **shared types**, stable primitives, schema/messages hoặc serialization có version rõ ràng; không dùng Java class name làm bằng chứng tương thích.

### 3.1. Parent-first và phiên bản implementation

`URLClassLoader` mặc định tìm ở **parent trước** rồi mới tới URLs của child. Nếu vô tình đưa cả `plugin.impl.Versioned` vào host classpath, loader V1 và V2 có thể trả **class đã được parent định nghĩa**: tưởng đã swap nhưng vẫn chạy code cũ.

Với kiến trúc đơn giản:

- Host classpath chỉ có **shared API + host runtime**.
- Plugin implementation JAR chỉ đưa vào URLs của loader generation.
- Parent của plugin loader là defining loader của shared API.
- Nếu cần child-first để cô lập thư viện version khác nhau, phải giới hạn **theo package**, không làm child-first toàn bộ `java.*` hoặc shared API.

Luôn kiểm tra:

~~~java
System.out.println(implementationType.getClassLoader());
System.out.println(Plugin.class.isAssignableFrom(implementationType));
System.out.println(implementationType.getModule());
~~~

Đây là snippet với `implementationType` đã có. Một class trùng tên mà loader khác thì vẫn khác runtime identity.

## 4. Thực hành Java 17+: hot swap V1 → V2 bằng loader mới

Thí nghiệm gồm một shared API, hai JAR chứa **cùng một binary name** nhưng method trả hai phiên bản, và một host dùng `ReentrantReadWriteLock` để đảm bảo **request đồng bộ** không chạy vào lúc generation cũ đang được thay/đóng.

### 4.1. Cấu trúc thư mục

~~~text
plugin-swap-lab/
├── src/
│   ├── api/api/Plugin.java
│   ├── v1/plugin/impl/Versioned.java
│   ├── v2/plugin/impl/Versioned.java
│   └── host/HostMain.java
└── build/                         (sinh khi chạy lệnh)
    ├── api/
    ├── v1/
    ├── v2/
    ├── host/
    ├── v1.jar
    └── v2.jar
~~~

Tệp **`src/api/api/Plugin.java`**:

~~~java
package api;

public interface Plugin extends AutoCloseable {
    String version();

    @Override
    default void close() { }
}
~~~

Tệp **`src/v1/plugin/impl/Versioned.java`**:

~~~java
package plugin.impl;

import api.Plugin;

public final class Versioned implements Plugin {
    @Override
    public String version() {
        return "v1";
    }
}
~~~

Tệp **`src/v2/plugin/impl/Versioned.java`**:

~~~java
package plugin.impl;

import api.Plugin;

public final class Versioned implements Plugin {
    @Override
    public String version() {
        return "v2";
    }
}
~~~

Đây là **hai source files nằm ở hai cây thư mục khác nhau**, có **cùng package, tên class** và **khác implementation**. Chúng phải được biên dịch thành **hai JAR độc lập**, không cùng một output directory.

### 4.2. Host quản lý generation và chuyển routing

Tệp **`src/host/HostMain.java`**:

~~~java
import api.Plugin;

import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public final class HostMain {

    static final class Generation implements AutoCloseable {
        final URLClassLoader loader;
        final Plugin plugin;
        final Class<?> type;

        private Generation(
                URLClassLoader loader,
                Plugin plugin,
                Class<?> type) {
            this.loader = loader;
            this.plugin = plugin;
            this.type = type;
        }

        static Generation open(Path jar) throws Exception {
            URL url = jar.toAbsolutePath().toUri().toURL();
            URLClassLoader loader = new URLClassLoader(
                new URL[] {url},
                Plugin.class.getClassLoader());

            try {
                Class<?> type =
                    loader.loadClass("plugin.impl.Versioned");
                Plugin instance = Plugin.class.cast(
                    type.getDeclaredConstructor().newInstance());
                return new Generation(loader, instance, type);
            } catch (Exception | LinkageError failure) {
                try {
                    loader.close();
                } catch (IOException closeError) {
                    failure.addSuppressed(closeError);
                }
                throw failure;
            }
        }

        @Override
        public void close() throws Exception {
            // Đóng plugin trước, rồi đóng file/JAR handles của loader.
            // try-with-resources giữ suppressed exceptions nếu cùng lỗi.
            try (URLClassLoader closing = loader) {
                plugin.close();
            }
        }
    }

    static final class Registry implements AutoCloseable {
        private final ReentrantReadWriteLock lock =
                new ReentrantReadWriteLock(true);
        private Generation active;

        Registry(Generation initial) {
            active = initial;
        }

        String request() {
            lock.readLock().lock();
            try {
                return active.plugin.version();
            } finally {
                lock.readLock().unlock();
            }
        }

        Class<?> activeType() {
            lock.readLock().lock();
            try {
                return active.type;
            } finally {
                lock.readLock().unlock();
            }
        }

        void replace(Path newJar) throws Exception {
            // PREPARE: làm ngoài write lock để request V1 vẫn chạy.
            Generation prepared = Generation.open(newJar);

            Generation previous;
            lock.writeLock().lock();
            try {
                previous = active;
                active = prepared;  // CUTOVER
            } finally {
                lock.writeLock().unlock();
            }

            // Khi lấy được write lock, mọi request() cũ dưới
            // read lock đã hoàn tất; giờ có thể retire V1.
            if (previous != null) {
                previous.close();
            }
        }

        @Override
        public void close() throws Exception {
            Generation previous;
            lock.writeLock().lock();
            try {
                previous = active;
                active = null;
            } finally {
                lock.writeLock().unlock();
            }
            if (previous != null) {
                previous.close();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try (Registry registry = new Registry(
                Generation.open(Path.of("build/v1.jar")))) {
            Class<?> oldType = registry.activeType();

            System.out.println("before=" + registry.request());
            registry.replace(Path.of("build/v2.jar"));

            Class<?> newType = registry.activeType();
            System.out.println("after=" + registry.request());
            System.out.println("same implementation class="
                    + (oldType == newType));
            System.out.println("shared contract="
                    + (Plugin.class == newType.getInterfaces()[0]));
        }
    }
}
~~~

### 4.3. Biên dịch và chạy

Từ thư mục `plugin-swap-lab`, dùng **POSIX shell** (Linux/macOS, Git Bash) và JDK 17 trở lên:

~~~bash
mkdir -p build/api build/v1 build/v2 build/host

# API nằm trong host classpath.
javac --release 17 -d build/api src/api/api/Plugin.java

# Hai implementation cùng tên, build riêng.
javac --release 17 -cp build/api -d build/v1 \
    src/v1/plugin/impl/Versioned.java
javac --release 17 -cp build/api -d build/v2 \
    src/v2/plugin/impl/Versioned.java

jar --create --file build/v1.jar -C build/v1 .
jar --create --file build/v2.jar -C build/v2 .

# Host KHÔNG được cho v1.jar/v2.jar vào classpath.
javac --release 17 -cp build/api -d build/host \
    src/host/HostMain.java

java -cp "build/api:build/host" HostMain
~~~

Trên Windows PowerShell/CMD, thay dấu phân tách classpath bằng `;` và tạo thư mục bằng lệnh phù hợp. Lệnh chạy:

~~~powershell
java -cp "build/api;build/host" HostMain
~~~

**Stdout đã được kiểm chứng với OpenJDK 21 khi biên dịch `--release 17`:**

~~~text
before=v1
after=v2
same implementation class=false
shared contract=true
~~~

Phân tích:

1. `v1.jar` được define bởi `URLClassLoader` thế hệ V1. `Plugin` là shared type định nghĩa bởi loader của host.
2. `Generation.open(v2.jar)` tạo **một URLClassLoader mới**, tìm cùng tên `plugin.impl.Versioned` rồi tạo object mới. Nó không đụng tới `Class<?>` của V1.
3. `Registry.replace` chỉ nhận write lock sau khi chuẩn bị V2 thành công, thay reference `active`, rồi close resources V1.
4. `oldType != newType` vì hai implementation classes do hai defining loaders khác nhau tạo.
5. `Plugin.class == newType.getInterfaces()[0]` vì implementation V2 sử dụng đúng shared API do parent loader định nghĩa.
6. `oldType` vẫn là biến local giữ `Class<?>` của V1. Do đó demo **không chứng minh unload** sau `close()`; nó chỉ chứng minh version swap và type identity.

**Giới hạn lab rất quan trọng:** Code là ví dụ **synchronous, single-administrator** với operations `request`/`replace`/`close`. Nó **chưa** xử lý nhiều thread cùng gọi `replace`/`close`, trạng thái STOPPING, plugin tự tạo background jobs, migration state, callback đa luồng hay policy timeout. Không nên copy thẳng vào sản phẩm internet-facing mà thiếu các phần lifecycle production ở các mục sau.

### 4.4. Tại sao đọc/ghi bằng lock giải quyết race trong ví dụ?

Trong `request()`, read lock được giữ cho **toàn bộ lời gọi vào plugin**. Khi `replace` lấy được write lock, không còn request cũ đang giữ read lock; việc đổi `active` diễn ra tại một điểm tuyến tính rõ. Một request mới đến sau write lock sẽ dùng V2.

Đây là trade-off: request có thể chờ trong lúc cutover, và một request V1 chạy rất lâu sẽ khiến write lock chờ lâu. Tuy nhiên example không đóng V1 loader giữa chừng. Trong hệ throughput cao, có thể thay read/write lock bằng generation **leases/reference counts** có giao thức retire atomic, nhưng không được dùng một reference swap đơn độc rồi close vội.

## 5. Thiết kế vòng đời production: chuẩn bị → publish → retire

Một plugin thế hệ nên có **state machine** tối thiểu:

~~~text
NEW
 |
 +-> PREPARING
 |      |
 |      +-> PREPARED -- health-check --> READY
 |      |                            |
 |      |                            v
 |      |                         ACTIVE
 |      |                            |
 |      |                            v
 |      |                         DRAINING
 |      |                            |
 |      |                            v
 |      |                         CLOSED
 |      |
 |      +-> FAILED -> CLEANUP -> CLOSED
 |
 +-> FAILED
~~~

Không phải API có sẵn trong JDK; đây là **quy ước container/host** cần hiện thực bằng lock, immutable generation descriptor và transitions được phép.

### 5.1. PREPARE — xây V2 mà không phá V1

Một bước chuẩn bị đầy đủ thường gồm:

1. Nhận artifact V2 từ một **đường dẫn versioned/immutable** (ví dụ tên file chứa hash hoặc version, không ghi đè v1.jar đang chạy).
2. Kiểm tra checksum/signature nguồn, content trust, minimum Java runtime version và dependency compatibility.
3. Tạo `URLClassLoader`/custom loader mới, parent là shared API loader, giữ rõ danh sách JAR dependencies.
4. Nạp entry point của V2; kiểm tra `Plugin.class.isAssignableFrom(implType)` bằng **runtime Class identity**, không chỉ so tên.
5. Khởi tạo plugin/Dependency Injection context, verify cấu hình, kết nối cần thiết và **health check** trong phạm vi tài nguyên có thể rollback.
6. Đảm bảo callback/resources tạo trong PREPARE có cơ chế cleanup nếu bất kỳ bước nào thất bại.
7. Chưa publish V2 tới request router cho đến khi trạng thái READY.

**Cảnh báo:** `ClassLoader.loadClass(name)` tự nó không bắt buộc chạy static initializer; nhưng `new`, `Class.forName(name,true,loader)`, constructor/DI và một số reflection APIs có thể kích hoạt `<clinit>` và side effects. Chuẩn bị V2 có thể tiêu thụ tài nguyên hoặc gọi external services **trước cutover**. Vì vậy PREPARE không được được quảng bá là “chỉ kiểm tra, tuyệt đối không có tác dụng phụ”.

### 5.2. COMMIT/PUBLISH — điểm chuyển traffic

Khi V2 READY, host thay **active-generation reference** bằng thao tác atomic hoặc một critical section được bảo vệ. Mỗi request phải có quy ước sử dụng **đúng một generation** trong suốt operation. Không đọc active lúc đầu, rồi đọc lại giữa request và vô tình kết hợp class V1 với state/callback của V2.

Ở lab mục 4, write lock làm điểm publish rõ ràng. Trong một hệ nhiều instance/process, một `AtomicReference` ở một JVM **không** làm cutover atomic trên toàn cluster; cần load balancer/routing/version coordination và rollout/rollback policy cấp hệ thống.

### 5.3. RETIRE — dọn V1 khi không còn công việc cũ

Khi V2 active:

1. Đánh dấu V1 là **DRAINING** và không cấp handle/request mới cho V1.
2. Chờ các **leases/in-flight requests** của V1 kết thúc hoặc cancel theo timeout/policy; không ép đóng khi class/resource của V1 đang được tìm.
3. Stop plugin-owned timers, executors, watchers và long-running background jobs.
4. Unregister event listeners, MBeans, HTTP routes, scheduled callbacks, ServiceLoader/DI caches và những registry host đang giữ objects V1.
5. Gọi `close()`/`stop()` lifecycle của V1 provider instances theo thứ tự tài nguyên phù hợp.
6. Close `URLClassLoader` V1 và file/JAR handles thuộc nó, xử lý `IOException` có thể có suppressed exceptions.
7. Bỏ strong references còn giữ `Class<?>`, `Method`, plugin objects, classloader và `ThreadLocal` values; restore TCCL về loader trước đó.
8. Theo dõi GC/class unloading một cách **quan sát được**, không dựa `System.gc()` để hứa unload ngay.

**Không đóng parent/shared loader** khi V1 kết thúc: parent vẫn phục vụ host và V2.

## 6. Lỗi concurrency tinh vi: `AtomicReference` không tự bảo vệ lifetime

Mẫu dễ sai:

~~~java
// PSEUDOCODE: sai nếu retire V1 đồng thời.
Generation generation = active.get();
return generation.plugin.call();
~~~

Song song, admin có thể làm:

~~~java
Generation old = active.getAndSet(newGeneration);
old.close();
~~~

Interleaving lỗi:

~~~text
Request R                         Admin
  g = active.get() => V1
                                    active = V2
                                    V1.close()
  g.plugin.call()                 <-- gọi V1 sau khi đã close
~~~

**Atomic swap chỉ bảo vệ reference**, không cấp “quyền sử dụng” (lifetime lease) cho request đã đọc được V1. Nếu V1 close làm đóng network client, executor hoặc resource mà method cần, request sẽ lỗi dù `Class<?>` V1 vẫn tồn tại.

Có hai hướng thiết kế:

- **Read/write lock trên toàn synchronous call:** như lab; update lấy write lock rồi mới close. Đơn giản, dễ chứng minh, nhưng request dài giữ read lock và kéo dài cutover.
- **Generation lease/reference counting đúng giao thức:** request phải **acquire lease atomically với trạng thái chưa-retired**; sau đó release trong `finally`. Admin chuyển active, đánh dấu V1 retired, đợi số lease còn lại về 0, rồi mới close. Nếu acquire V1 thất bại sau khi V1 bị retire, request retry lấy V2. Không chỉ `AtomicInteger.incrementAndGet` sau `active.get()` mà bỏ bước kiểm tra trạng thái: vẫn có cửa sổ race.

### 6.1. Sơ đồ lease đúng về ý tưởng

~~~text
Request:
  repeat:
      gen = active.get()
      lease = gen.tryAcquireUnlessRetired()
  until lease succeeds

  try:
      return gen.invoke(request)
  finally:
      lease.release()

Admin:
  newGen = prepare(version2)
  oldGen = atomicPublish(newGen)
  oldGen.markRetired()
  wait until oldGen.activeLeases == 0
  oldGen.stopAndClose()
~~~

Đây là **pseudocode**, không phải Java method có sẵn; cần thiết kế `tryAcquireUnlessRetired` và `markRetired` thành một state machine atomic/được khóa đúng. Tùy policy, admin cũng cần ngăn một request acquire oldGen trong khoảng **swap→retire** bằng gating hoặc bắt generation không còn active; nếu không, cutover semantics bị trễ dù close vẫn có thể an toàn khi đợi leases.

**Đối với async task:** Lease phải sống đến khi `CompletionStage`, callback, coroutine/virtual thread hoặc background work **thực sự kết thúc**, không chỉ khi method trả về một `Future`. Nếu plugin tự spawn thread nằm ngoài request lifecycle, cần stop/quiesce riêng.

### 6.2. Một request có được trộn V1 và V2 không?

Nên chọn một trong hai contract rõ ràng:

- **Request-affinity:** request acquire generation khi bắt đầu, dùng chính generation đó đến khi xong; các callbacks thuộc request cũng giữ lease. Phù hợp hot reload không cần ngắt request cũ.
- **Hard cutover/cancel:** admin chặn request mới, cancel/drain request cũ theo timeout rồi chuyển version. Phù hợp thay đổi giao thức/state không tương thích.

Không viết code gọi `PluginService old` rồi `PluginService new` trong cùng transaction mà thiếu quy tắc data compatibility. Việc classes có thể cùng tồn tại trong JVM không đồng nghĩa business state có thể dùng lẫn.

## 7. Rollback, failure modes và cách xử lý đúng

| Thời điểm lỗi | Trạng thái hệ thống | Xử lý |
| --- | --- | --- |
| Download/checksum/signature V2 lỗi | V1 vẫn ACTIVE | Không tạo/publish generation mới |
| V2 không nạp được class/dependency | V1 vẫn ACTIVE | Close loader V2 vừa tạo, ghi nguyên nhân |
| V2 constructor/`<clinit>` ném lỗi | V1 vẫn ACTIVE nếu chưa publish | Cleanup các tài nguyên V2 đã tạo; không ghi đè V1 |
| V2 health check thất bại | V1 vẫn ACTIVE | Mark V2 FAILED, cleanup rồi giữ router V1 |
| V2 đã publish, request V2 gặp business lỗi | V2 ACTIVE | Nếu rollback cần **policy chuyển lại V1** khi V1 còn phù hợp, hoặc tạo fresh generation của bản ổn định |
| V2 publish thành công, close V1 lỗi | V2 vẫn ACTIVE | Báo RETIREMENT_FAILED, tiếp tục cleanup/audit; **không giả vờ cutover chưa xảy ra** |
| V1 có request chạy lâu | V2 có thể đã ACTIVE | DRAIN với lease/timeout; không close sớm |
| JVM crash/process restart | Không có runtime state cũ | Khôi phục từ artifacts + external persisted state, không dựa vào classloader |

### 7.1. Trước publish: có thể rollback bằng cách bỏ V2

Trường hợp dễ nhất: PREPARE thất bại. Host không thay `active`, nên toàn bộ request còn dùng V1. Nhưng “rollback” không có nghĩa undo mọi **tác dụng phụ** mà constructor/start của V2 đã thực hiện. Nếu V2 viết database hoặc gửi message trước publish, bạn cần idempotence, transaction, compensating action hoặc staging policy riêng.

### 7.2. Sau publish: không gọi close failure là rollback

Trong lab, `replace` gán `active=prepared` rồi gọi `previous.close()`. Nếu `previous.close()` ném exception, **V2 vẫn đang active**. Code gọi `replace` có thể thấy exception, nên API production cần phân biệt ít nhất:

- `PREPARE_FAILED`: chưa publish;
- `PUBLISHED_CLEANUP_PENDING`: V2 đã publish, V1 chưa cleanup xong;
- `COMPLETE`: V2 đã publish, V1 đã retire.

Nếu dùng một boolean success/fail cho cả ba trạng thái, hệ vận hành có thể vô tình trigger retry/cutover lần hai và tạo thêm loader leak.

### 7.3. Rollback version thực tế

Nếu V2 có lỗi nghiệp vụ sau khi đã nhận traffic:

- Khi V1 **còn sống/không retired** và schema compatible, host có thể route trở lại V1 với protocol tương ứng.
- Nếu V1 **đã closed**, không giả định nó vẫn có thể tiếp tục nạp dependencies; thay vào đó **tạo loader mới** từ immutable V1 artifact nếu muốn khởi chạy lại V1.
- Database schema/messages/API có thể đã thay đổi theo V2; rollback bytecode mà không rollback/migrate state chưa chắc an toàn.
- Giữ các artifact versioned immutable để có thể reproduce. Tránh sửa trực tiếp JAR đang được loader sử dụng (trên Windows còn có thể không đổi tên/xóa do file handles).

## 8. `URLClassLoader.close()`: tài nguyên được đóng, class không biến mất

Javadoc mô tả `URLClassLoader.close()`:

- Ngăn loader tiếp tục nạp **classes/resources mới do nó tự tìm/định nghĩa** qua URL path.
- Classes/resources đã nạp trước đó **vẫn truy cập được**; classes từ parent delegation cũng vẫn truy cập.
- Đối với `jar:`/`file:`, đóng những file/JAR handles mà loader đã mở theo khả năng của implementation.
- Nếu một thread đang nạp class đồng thời thread khác gọi `close()`, **kết quả load không xác định** — tuyệt đối không dùng làm giao thức shutdown.
- `close()` có thể ném `IOException`; nếu nhiều lỗi khi đóng file, những lỗi sau có thể trở thành **suppressed exceptions**.
- Gọi `close()` lần nữa sau khi đã close không có thêm tác dụng.

**Không được suy ra:**

- `oldInstance.method()` sẽ lập tức ném lỗi vì class cũ “đã bị xóa”. Method đã loaded có thể vẫn thực thi; nhưng nếu nó lần đầu yêu cầu nạp một class/resource khác thuộc loader đã close, có thể lỗi.
- Static state của V1 tự reset.
- Background threads do V1 tạo tự dừng.
- Cache/static registry/ThreadLocal giữ V1 tự bị dọn.
- `URLClassLoader.close()` tự gọi `close()` cho từng provider, DB connection, HTTP client, executor, watcher hoặc file stream mà **application code** trực tiếp mở.
- Class unloading hay giải phóng Metaspace xảy ra đồng bộ ngay lúc close.

Với custom `ClassLoader` không extends `URLClassLoader`, **không có method `ClassLoader.close()` chuẩn**. Nếu loader tự giữ `JarFile`, channels hoặc sockets, bạn phải cung cấp `AutoCloseable` owner rõ ràng.

### 8.1. Phân biệt close loader với class unloading

Runtime class của V1 chỉ **có thể** được unload khi không còn roots/reachable objects phù hợp và JVM/GC quyết định thực hiện. Những tham chiếu giữ V1 bao gồm:

- `Class<?>`, `Method`, `Constructor` hoặc instance được host cache.
- Một object provider V1 trong `ServiceLoader`/DI container registry.
- Running thread stack frames đang thi hành bytecode V1.
- `Thread.currentThread().getContextClassLoader()` trên worker sống lâu.
- `ThreadLocal` value/key giữ class hoặc object của plugin.
- `static` map ở loader host, callback/listener/event queue giữ lambda/object V1.
- Executor, scheduler, async task, logging appender, JDBC driver và native/JNI references còn sống.
- ModuleLayer/ClassLoader references hoặc framework metadata caches.

`System.gc()` chỉ là gợi ý; không tạo SLA unload ngay. Nếu dùng HotSpot có logging hỗ trợ, có thể theo dõi class load/unload qua `-Xlog:class+load=info,class+unload=info` và heap dump/`jcmd` để tìm **strong reference path** giữ loader.

## 9. TCCL, ServiceLoader và các tài nguyên plugin dễ quên

### 9.1. Context class loader (TCCL)

Một plugin host có thể đặt TCCL để framework parent-loader tìm providers ở plugin loader:

~~~java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    frameworkCall();
} finally {
    thread.setContextClassLoader(previous);
}
~~~

Đây là **snippet**, cần biến `pluginLoader` và method `frameworkCall` trong dự án. Nếu quên `finally`, thread pool worker có thể giữ loader V1 sau khi đã swap sang V2, gây **provider discovery sai phiên bản** và chặn class unloading.

`new Thread(...)` thường kế thừa TCCL tại **thread construction time**; pool worker đã tạo từ trước **không tự nhận** TCCL của submitter ở mỗi `submit`. Không dùng TCCL vô tình của worker như nguồn quyết định active generation.

### 9.2. ServiceLoader cache và provider identity

`ServiceLoader.load(Service.class)` dùng TCCL ở thời điểm tạo đối tượng ServiceLoader. `ServiceLoader.load(Service.class, pluginLoader)` dùng loader tường minh, thường phù hợp plugin manager hơn. Provider cache của `ServiceLoader` không tự chuyển sang V2 khi bạn swap active loader.

- Khi thay generation, tạo **ServiceLoader mới** với loader/layer V2 nếu cần khám phá providers V2.
- `reload()` xóa provider cache của ServiceLoader hiện tại, **không** biến loaded class V1 thành class V2.
- Bỏ references và unregister providers V1 ở host; `close(pluginLoaderV1)` không tự gỡ mọi registrations.
- `ServiceLoader` instance không thread-safe; không cùng lúc duyệt và reload trên nhiều threads mà thiếu synchronization.

### 9.3. ThreadLocal, JDBC, logging, background jobs

Một lỗi hot reload thường không nằm ở `loadClass` mà nằm ở **resource ownership**:

- Plugin đăng ký JDBC driver vào `DriverManager`, MBean vào platform server, metrics exporter vào host registry — cần unregister.
- Plugin tạo executor/scheduler: stop tasks, await termination, xử lý interrupts và không để TCCL V1 trên workers chung.
- Plugin dùng `ThreadLocal`: remove khi context scope kết thúc; nếu giá trị tham chiếu object V1, worker host sống lâu có thể giữ loader V1.
- Plugin đăng ký event listener/callback vào một host singleton: unregister/cancel, tránh lambda V1 bị giữ.
- Plugin dùng JNI/native libraries: Java loader close không đồng nghĩa library OS được unload ngay; xem ràng buộc native lifetime.
- Plugin ghi log qua appender/file watcher riêng: đóng theo lifecycle của chính thư viện log, không kỳ vọng URLClassLoader quản lý.

## 10. Dependency versioning, package split và class identity

Một plugin V2 có thể sử dụng phiên bản thư viện khác V1. Loader mới giúp cô lập dependencies nếu chúng thực sự do mỗi plugin loader định nghĩa. Nhưng không phải lúc nào cũng an toàn:

- Nếu host parent đã nạp `com.example.lib.Client`, child parent-first có thể nhận **bản host** thay vì bản plugin. Hãy tách packages/loader policy nếu cần private version.
- Nếu host expose một public API dùng loại `com.example.lib.Client` trong method signature, type này là một phần **shared contract** và không thể tùy ý đổi defining loader giữa generations.
- Nếu cùng tên DTO do V1/V2 define riêng, cast/serialization trực tiếp có thể fail. Dùng shared DTO, stable schema, JSON/protobuf/records chung hoặc mapping explicit.
- `Package sealing` và signer/certificate consistency vẫn áp dụng khi nạp signed JARs; child-first tùy tiện có thể va chạm package semantics.
- Với JPMS, thêm `module-info.java` thay đổi resolution và `requires/exports/opens`; giữ đúng module graph/layer bên cạnh classloader identity.

### 10.1. Không dùng `getName()` để kiểm tra compatibility

~~~java
// Sai: hai classes có thể trùng tên mà không cast được.
boolean looksEqual =
        oldType.getName().equals(newType.getName());

// Đúng cho runtime identity:
boolean sameType = oldType == newType;

// Đúng cho shared contract:
boolean implementsApi =
        Plugin.class.isAssignableFrom(newType);
~~~

Đây là snippet với biến `oldType`/`newType` sẵn có. `isAssignableFrom` giúp xác minh class implement đúng host interface, nhưng không thay checks về binary compatibility, constructor, method behavior, resource ownership và module permissions.

## 11. ModuleLayer và plugin versions trong JPMS (Java 9+)

Nếu plugin được triển khai bằng **named modules**, chỉ tạo `URLClassLoader` mới cho JAR là không đủ để tự động thay module đã resolved trong boot layer. JPMS có mô hình **ModuleLayer** và module configurations:

1. Tìm module artifacts V2 qua `ModuleFinder`.
2. Resolve module graph với parent configuration thích hợp; xử lý `requires`, `exports`, `opens`, `provides/uses`.
3. Tạo **ModuleLayer mới** gắn modules tới một hoặc nhiều loader theo `defineModulesWithOneLoader`/`defineModulesWithManyLoaders` khi phù hợp.
4. Chỉ publish service objects của layer V2 sau validation.
5. Retire layer V1 bằng **bỏ tất cả references** tới layer/loader/classes/providers khi không còn work; không có thao tác Java SE phổ quát kiểu `ModuleLayer.unload()`.

Các lời gọi dưới đây là **pseudocode cấu trúc**, không phải chương trình có thể chạy nguyên văn:

~~~java
ModuleFinder finder = ModuleFinder.of(version2ModulePath);
Configuration config = parentLayer.configuration().resolve(
        finder, ModuleFinder.of(), Set.of("plugin.module"));

ModuleLayer v2 = parentLayer.defineModulesWithOneLoader(
        config, sharedApiLoader);
~~~

Cần import `java.lang.module.ModuleFinder`/`Configuration`, `java.util.Set` và biến `version2ModulePath`/`parentLayer`/`sharedApiLoader` đã có. Không phải mọi module graph/layer đều có thể resolve một cách tùy ý nếu packages/names/dependencies xung đột. `ModuleLayer` mới không tự đảm bảo unload V1 hoặc migration state.

**Lựa chọn kiến trúc:** Nếu ứng dụng chỉ cần plugin JAR classpath với SPI, `URLClassLoader` + shared API parent thường đơn giản hơn. Nếu muốn strong encapsulation/module descriptors/services theo JPMS, dùng module layers và kiểm tra module access riêng.

## 12. Không biến ClassLoader thành sandbox bảo mật

ClassLoader mới cho generation V2 giải quyết **class identity và dependency isolation** trong cùng JVM; nó không giới hạn file/network/CPU/threads mà code plugin được phép sử dụng. Trên JDK 24+, Security Manager đã bị vô hiệu hóa vĩnh viễn (JEP 486). Nếu plugin không tin cậy, chạy trong process/OS sandbox với quyền, resource limits và giao thức IPC phù hợp; hot swap trong cùng JVM không phải security boundary.

## 13. Checklist QA trước khi cho phép version swap

**Artifact / compatibility**

- [ ] V2 JAR path immutable/versioned; checksum/signature/provenance đã kiểm tra.
- [ ] Java bytecode version, dependency versions và module/JAR metadata phù hợp runtime.
- [ ] Shared API do host parent define, không có bản API riêng bị child define lại.
- [ ] Entry point có public constructor hoặc factory được contract cho phép; API compatible.
- [ ] Health check phân biệt verify/cấu hình và side effects do `<clinit>`/constructor.

**Cutover / concurrency**

- [ ] Có một **điểm publish atomic/locked** cho active generation.
- [ ] Request/callback đã acquire V1 được phép chạy đến đâu? Có lease/read lock/cancellation policy.
- [ ] Không đóng V1 khi `loadClass`/`getResource` hoặc methods còn chạy thiếu phối hợp.
- [ ] Nhiều admin/swap/close concurrent được serialization và kiểm tra state chính xác.
- [ ] Timeout khi draining V1; nếu timeout không tuyên bố cleanup complete.
- [ ] Callback async giữ đúng generation, không mix V1/V2 trong cùng transaction khi incompatible.

**Cleanup / observability**

- [ ] V1 ngừng timers/executors, unsubscribe listeners và unregister SPI/registries.
- [ ] Provider instances, sockets, DB pools, watchers và file handles được close đúng owner.
- [ ] TCCL của worker được restore; ThreadLocal chứa object V1 được remove.
- [ ] URLClassLoader V1 được close sau quiesce; suppressed exceptions được log.
- [ ] Host bỏ references tới `Class`, `Method`, ServiceLoader cache, plugin instance và ModuleLayer cũ.
- [ ] Đo loaders/threads/Metaspace/file handles qua nhiều lần swap, không dựa vào một lần GC.
- [ ] Báo trạng thái PREPARE_FAILED khác PUBLISHED_CLEANUP_PENDING khác COMPLETE.

## 14. Test plan nên có cho plugin manager

| Kiểm thử | Kết quả cần chứng minh |
| --- | --- |
| V1→V2 cùng binary name, loader mới | Method trả hành vi V2 và `oldType != newType` |
| Shared API identity | `Plugin.class.isAssignableFrom(v2Impl) == true` |
| Cố update file JAR nhưng giữ loader cũ | Không có giả định JVM tự tạo class mới |
| Invalid V2 JAR hoặc thiếu entry point | Không publish; V1 vẫn nhận requests |
| V2 constructor/health-check fail | Đóng resource V2 đã tạo; không chuyển active |
| 100 requests V1 đang chạy trong lúc swap | Không close V1 trước khi in-flight xong theo policy |
| Request đến sau cutover | Nhận V2, không bị route ngẫu nhiên về V1 |
| V1 close() ném lỗi | V2 vẫn active; báo retirement failure rõ |
| Hot reload lặp 100+ lần | Không có xu hướng tăng không kiểm soát của threads/loaders/handles |
| TCCL trên executor workers | Không còn reference loader V1 sau stop |
| V1 provider trong ServiceLoader/DI cache | Registry/cache cleanup đúng, không gọi provider sau retire |
| Rollback V2→stable V1 artifact | Loader mới được tạo; external schema/state compatible |
| Two concurrent admins cùng replace/close | Không orphan loader, không publish sau shutdown |
| JPMS layer V2 nếu áp dụng | Module graph/services/access đúng, không giữ layer V1 |

### 14.1. Quan sát lớp nạp và unload

Với JDK HotSpot hỗ trợ unified logging:

~~~bash
java -Xlog:class+load=info,class+unload=info \
    -cp "build/api:build/host" HostMain
~~~

Log cho biết load/unload events khi chúng xảy ra; một demo còn giữ `oldType` thì class V1 có thể chưa đủ điều kiện unload. `-Xlog` là cơ chế JVM implementation, không phải Java language API bắt buộc mọi vendor cùng format.

Có thể dùng `jcmd`/Java Flight Recorder/heap dump và thread dumps để truy vết loader retention. Kiểm tra tools có sẵn trong JDK trước khi dùng, giữ lại generation id + artifact hash + loader identity trong diagnostic logs để phân biệt V1/V2.

## 15. Những hiểu nhầm cần tránh

1. “Copy JAR mới đè lên V1.jar làm JVM tự lấy code mới.” — **Sai** với class đã load.
2. “Gọi `loader.loadClass` thêm lần nữa sẽ re-define class.” — **Sai**; cùng loader bình thường trả cùng `Class<?>`.
3. “Đổi `ProtectionDomain` hoặc `CodeSource` có thể reset class identity.” — **Sai**.
4. “Tạo loader mới nhưng parent có V1 class vẫn bảo đảm V2.” — **Sai**; delegation có thể trả bản parent.
5. “Cùng tên `api.Plugin` nghĩa là host cast được.” — **Sai** nếu defining loaders khác.
6. “Gọi `URLClassLoader.close()` lập tức unload lớp cũ.” — **Sai**.
7. “Close loader tự shutdown tất cả plugin threads/DB connections.” — **Sai**.
8. “`AtomicReference.getAndSet` rồi close ngay V1 an toàn với mọi request.” — **Sai** nếu còn request giữ reference V1.
9. “Chuẩn bị V2 có nghĩa chưa có side effects.” — **Sai**; static initializer/constructor/start có thể đã thực thi.
10. “Lỗi close V1 sau publish đồng nghĩa V2 chưa active.” — **Sai**; cần phân biệt commit và cleanup result.
11. “`ServiceLoader.reload()` hot-reload bytecode từ JAR mới.” — **Sai**; nó reset provider cache.
12. “Một loader mới tự giải quyết mọi incompatibility DB schema/API.” — **Sai**; cần migration/versioning riêng.
13. “ModuleLayer có method unload dùng khi hết plugin.” — **Không có** Java SE unload API kiểu này.
14. “Tách classloader là sandbox an toàn cho plugin không tin cậy.” — **Sai**, đặc biệt trên JDK 24+ không còn Security Manager.
15. “Một lần `System.gc()` mà chưa thấy unload là chứng minh memory leak.” — **Sai**; cần tìm strong roots và quan sát dài hạn.

## 16. Bài tập tự kiểm tra

1. V1 và V2 cùng define `plugin.impl.Versioned` từ hai `URLClassLoader` mới. Có phải một runtime class không? **Không**, nếu mỗi loader thực sự define chính class đó.
2. Plugin V2 implement `api.Plugin` do host parent define, host có cast được không? **Có**, khi implementation compatible và access hợp lệ.
3. Tại sao không đặt V1 implementation JAR vào host classpath trong lab? **Parent-first có thể trả class V1 cho cả hai loaders**.
4. `Generation.open(V2)` lỗi khi V1 active, có nên publish V2? **Không**; giữ V1 và cleanup V2.
5. Khi `active` vừa chuyển sang V2, một V1 request chưa kết thúc thì xử lý thế nào? **Draining/lease hoặc lock, không close V1 trước hạn**.
6. `URLClassLoader.close()` có xóa `Class<?>` đã load không? **Không**.
7. Nếu V1 close thất bại sau swap, active là gì? **V2**; phải báo lỗi retirement riêng.
8. Vì sao không đơn giản dùng `AtomicReference` cho mọi thao tác? **Atomic swap không bảo vệ lifetime của object đã đọc trước swap**.
9. Hot swap có dừng background executor của V1 tự động không? **Không**, cần lifecycle riêng.
10. Một instance `ServiceLoader` đang cache V1 providers sẽ tự chuyển sang V2 khi TCCL đổi không? **Không**.
11. Muốn rollback V1 sau khi loader V1 đã close, nên làm gì? **Khởi tạo generation mới từ artifact V1 immutable**.
12. Vì sao một host static map có thể gây classloader leak? **Nó giữ plugin classes/objects, kéo dài lifetime của defining loader**.
13. Có cần đóng shared parent loader sau mỗi plugin update không? **Không**, parent thuộc host và các generations khác.
14. Java 24+ có thể giới hạn plugin bằng Security Manager/ProtectionDomain như trước không? **Không**, phải dùng các boundary khác nếu cần.
15. Khi dùng named modules, phải quản lý thêm điều gì? **ModuleLayer/configuration/readability/exports/opens/provider resolution**.

## 17. Tài liệu chính thức

1. [JVMS 5.3 — Loading, defining loader và runtime type identity](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): tên class + defining loader, initiating loaders, loading constraints.
2. [JLS 12.2 — Loading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.2): good classloader consistency và yêu cầu cùng tên trả cùng runtime Class trong loader.
3. [ClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): delegation, `findLoadedClass`, `defineClass`, `loadClass`, resource lookup.
4. [URLClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLClassLoader.html): `close`, đã-load classes, file/JAR handles, concurrent close limitations.
5. [AutoCloseable — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html): cleanup và try-with-resources.
6. [ReentrantReadWriteLock — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html): read/write lock và concurrency policy.
7. [Thread — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): TCCL và thread inheritance.
8. [ServiceLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): provider discovery/cache, `reload` và classloader/module layers.
9. [ModuleLayer — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ModuleLayer.html): nạp một configuration module trong layer mới.
10. [JEP 486 — Security Manager permanently disabled](https://openjdk.org/jeps/486): vì sao `ClassLoader`/`ProtectionDomain` không thể làm security sandbox cho plugin trên JDK 24+.

**Kết luận:** Thay plugin V1 bằng V2 là **chuyển cả một generation**, không phải cập nhật riêng một `Class<?>`. Hãy dùng **loader mới**, giữ **shared API identity**, chuẩn bị/kiểm thử V2 trước khi publish, chuyển routing theo **giao thức an toàn với in-flight requests**, rồi retire V1 theo resource ownership. `URLClassLoader.close()` giúp đóng JAR handles nhưng **không** tự dừng threads, tự unload class hay thay thế lifecycle/rollback policy.
