# Giới hạn của thay thế plugin so với instrumentation hoặc khởi động lại tiến trình

## 1. Ba cách cập nhật mã Java đang chạy

Một ứng dụng Java mở rộng qua plugin có thể cần đổi implementation khi tiến trình vẫn đang phục vụ request. Tuy nhiên, **thay JAR trên đĩa không có nghĩa JVM tự thay các class đã được nạp**. Cần phân biệt ba chiến lược độc lập:

1. **Thay thế plugin bằng class loader/module layer mới:** nạp một bản implementation mới dưới danh tính class mới, chuyển lưu lượng sang nó rồi ngừng bản cũ.
2. **Instrumentation/redefinition/retransformation:** dùng `java.lang.instrument.Instrumentation` và cơ chế hỗ trợ của JVM để thay đổi định nghĩa của các class đã được nạp, trong giới hạn khả năng của runtime.
3. **Khởi động lại JVM/process:** dừng phiên cũ, xây dựng process mới từ một tập artifact cố định và khởi tạo toàn bộ state theo quy trình startup.

Ba cách này khác nhau về class identity, trạng thái heap, tương thích API, thời gian gián đoạn, độ phức tạp rollback và ranh giới lỗi. Không có cách nào tự động bảo đảm zero downtime hoặc rollback mọi side effect.

## 2. So sánh nhanh

| Tiêu chí | Plugin mới, loader mới | Instrumentation | Restart tiến trình |
|---|---|---|---|
| Thay đổi implementation | Được, với class mới và routing mới | Có, trong giới hạn class redefinition của JVM | Được, bằng artifact/process mới |
| Thay đổi cấu trúc class/schema | Có thể với version mới, miễn API crossing-boundary tương thích | HotSwap chuẩn thường hạn chế thêm/xóa/đổi field/method, superclass, interface; tùy VM capability | Được khi binary/config/dependency mới tương thích |
| Class identity | Bản cũ và mới là hai class khác nhau nếu defining loader khác | Giữ identity của class đang được redefine | Tạo identity mới trong JVM mới |
| State hiện có | Phải migrate hoặc giữ bên ngoài plugin | Existing objects vẫn tồn tại; semantics có thể không đổi hoàn toàn | Phải phục hồi từ storage/checkpoint hoặc chấp nhận mất in-memory state |
| Resource cũ | Cần đóng thread, socket, listener, registry và class loader | Bytecode mới không tự giải phóng resource đã tạo | OS thu hồi tài nguyên process khi thoát, nhưng external side effect vẫn tồn tại |
| Rollback | Có thể chuyển routing lại nếu bản cũ còn hoạt động | Khó hơn: cần redefine ngược và xử lý state đã đổi | Thường chạy lại release/process cũ theo deployment policy |
| Cô lập lỗi | Cùng process với host nếu không tách worker | Cùng process | Process mới tách lỗi do process cũ, nhưng vẫn cần deployment an toàn |

Không nên đánh đồng class loader isolation với security sandbox. Plugin có thể có cùng quyền process và gây lỗi toàn hệ thống dù dùng loader riêng.

## 3. Thay plugin qua class loader mới: điểm mạnh và giới hạn

Java cho phép một loader mới định nghĩa class có cùng binary name với class ở loader cũ. Hai class này là **hai runtime types khác nhau**, dù source và tên package giống nhau. Đây là lý do host có thể giữ hai phiên bản plugin đồng thời, nhưng cũng là nguồn gây `ClassCastException` nếu lẫn API class giữa loaders.

Mô hình hợp lý:

```text
Host/Application Loader
   |-- stable plugin-api.jar (interface + DTO chung)
   |
   +-- PluginLoaderV1 --> implementation v1 + dependencies v1
   |
   +-- PluginLoaderV2 --> implementation v2 + dependencies v2

Router: active = service instance from V2
```

Host và plugin **phải chia sẻ chính xác một bản định nghĩa contract interface**. Nếu mỗi plugin loader tự định nghĩa lại `demo.api.Service`, instance V2 không nhất thiết assignable sang `demo.api.Service` do host giữ. Chiến lược thường gặp là parent-first đối với API packages, và chỉ cô lập implementation/dependency bên trong plugin loader.

### 3.1. Thay JAR trên disk không thay class đang chạy

Class đã nạp không được định nghĩa lại đơn giản vì bytecode trong file JAR đổi. Nhiều JVM/class loader có cache class và handle JAR; sửa file đang được sử dụng còn có thể gây lỗi I/O hoặc khóa file trên một số OS.

Thay plugin đúng quy trình thường là: tải artifact version mới vào **đường dẫn version hóa**, xác minh checksum/signature, tạo loader mới, nạp plugin mới, chạy health check, chuyển router, đợi request cũ hoàn tất, dọn plugin v1 rồi đóng loader v1. Tránh ghi đè JAR đang được loader sử dụng.

### 3.2. Class unloading không có tính quyết định

Đóng `URLClassLoader` bằng `close()` giúp giải phóng một số tài nguyên loader quản lý, nhưng **không bắt buộc JVM unload class ngay lập tức**. Class và loader có thể còn reachable qua:

- Thread do plugin tạo, context class loader của thread hoặc thread-local values.
- Static registry/singleton, callback listener được host giữ.
- Scheduled task, executor, timer, shutdown hook.
- Proxy, `MethodHandle`, reflection metadata hoặc cache chứa `Class<?>`.
- Object plugin còn nằm trong request đang chạy.
- JNI/native library và các resource đặc biệt.

GC/class unloading phụ thuộc tính reachability và cơ chế JVM; `System.gc()` cũng không hứa unload ngay. Khi quan sát memory leak, tìm tham chiếu giữ loader cũ thay vì chỉ đếm file `.jar` đã xóa.

### 3.3. State và giao dịch đang chạy

Nếu plugin xử lý đơn hàng có session in-memory hoặc giao dịch đang chạy, chuyển sang V2 có thể mất state hoặc tạo hai phiên bản cùng ghi một nguồn dữ liệu. Cần xác định:

- Session/state nào lưu trong plugin và state nào ở service ngoài.
- Có cần migration hoặc versioning của serialized data không.
- Request đang chạy ở V1 được drain hay cancel; timeout là bao nhiêu.
- Có thể phục vụ đồng thời V1/V2 trên cùng schema dữ liệu không.
- Có cần idempotency keys để tránh xử lý lại trong lúc cutover không.

Không nên xóa loader V1 trước khi chắc chắn mọi request và callback liên quan đã hoàn tất.

## 4. Ví dụ Java 17+: thay instance nhưng giữ contract chung

Đoạn ví dụ nhỏ này minh họa ý tưởng routing giữa hai implementation được tạo dưới **cùng một interface contract**. Ví dụ không tự tải JAR; phần class loader riêng được mô tả ở mục sau. Mục tiêu là làm rõ rằng thay instance là bước riêng với class redefinition.

Tạo file `SwitchPlugin.java`:

```java
import java.util.concurrent.atomic.AtomicReference;

public final class SwitchPlugin {
    public interface Service { String apply(String input); }

    public static final class V1 implements Service {
        public String apply(String input) { return "v1:" + input; }
    }

    public static final class V2 implements Service {
        public String apply(String input) { return "v2:" + input; }
    }

    public static void main(String[] args) {
        AtomicReference<Service> active = new AtomicReference<>(new V1());
        System.out.println(active.get().apply("hello"));

        Service candidate = new V2();
        if (!candidate.apply("health").equals("v2:health")) {
            throw new IllegalStateException("candidate failed health check");
        }
        active.set(candidate);
        System.out.println(active.get().apply("hello"));
    }
}
```

Biên dịch và chạy:

```bash
javac SwitchPlugin.java
java SwitchPlugin
```

Stdout chính xác:

```text
v1:hello
v2:hello
```

Ví dụ cho thấy `AtomicReference` có thể đổi implementation phục vụ **lượt truy cập mới**, nhưng không chuyển trạng thái hoặc kết thúc call đang giữ tham chiếu V1. Production cần in-flight tracking và quiescence, không thể chỉ `set()` rồi đóng toàn bộ V1 ngay lập tức.

### 4.1. Phác thảo nạp JAR version mới

Đoạn sau **minh họa, không chạy độc lập** vì cần `Service` chung và class implementation thực tế:

```java
URL jar = Path.of("plugins/plugin-v2.jar").toUri().toURL();
URLClassLoader loader = new URLClassLoader(
        new URL[] {jar}, Service.class.getClassLoader());

Class<?> type = Class.forName("demo.plugin.ServiceImpl", true, loader);
Service newService = (Service) type.getDeclaredConstructor().newInstance();
```

Cần import `java.net.URL`, `java.net.URLClassLoader`, `java.nio.file.Path`. Loader cha phải cung cấp shared contract `Service`; plugin JAR không nên định nghĩa bản khác của interface này. Khi candidate lỗi, host phải dọn resource/đóng loader vừa tạo. Khi thành công, giữ loader sống cho đến lúc plugin ngừng hoàn toàn.

## 5. Instrumentation: sửa class đã nạp thay vì tạo identity mới

`java.lang.instrument.Instrumentation` là API dành cho Java agent để biến đổi class file trong quá trình load hoặc redefine/retransform các class đã nạp. Cơ chế này khác với cập nhật JAR trên disk và không tự sinh ra từ `ClassLoader` hoặc `ServiceLoader` thông thường.

### 5.1. API chủ chốt

- `addTransformer(ClassFileTransformer, canRetransform)` đăng ký transformer.
- `retransformClasses(Class<?>...)` yêu cầu biến đổi lại class được hỗ trợ.
- `redefineClasses(ClassDefinition...)` cung cấp class bytes mới để redefine class cụ thể.
- `isRedefineClassesSupported()`, `isRetransformClassesSupported()` kiểm tra VM có hỗ trợ khả năng tương ứng.
- `isModifiableClass(Class<?>)` kiểm tra class cụ thể có thể bị sửa hay không.

Những API này cần agent instrumentation, không phải API cập nhật plugin chung. Một Java agent có thể được nạp lúc JVM khởi động bằng `-javaagent:agent.jar`; khả năng attach agent động và các chính sách liên quan phụ thuộc JDK/runtime và cấu hình triển khai.

### 5.2. Giới hạn của redefinition

Trong mô hình JVM HotSwap tiêu chuẩn, việc redefine đã nạp thường không hỗ trợ thay đổi schema như thêm/bớt field/method, đổi tên, modifier, superclass hoặc interface. Một số công cụ thương mại hoặc runtime đặc thù cung cấp khả năng mạnh hơn nhưng không nên coi đó là tính năng chuẩn cho mọi JDK.

Ngay cả khi redefine thành công:

- Object instance đã tạo vẫn giữ identity và state; constructor **không chạy lại**.
- Static initialization (`<clinit>`) không được tự khởi chạy lại chỉ vì redefine.
- Active stack frames có thể tiếp tục chạy bytecode của method version cũ cho đến khi rời frame; các invocation mới có thể dùng định nghĩa mới.
- Thay bytecode không thực hiện migration dữ liệu hay cập nhật giao thức với hệ thống ngoài.
- Lỗi của agent có thể ảnh hưởng JVM host; instrumentation không là ranh giới cô lập process.

Instrumentation phù hợp với monitoring, profiling, hotfix body method trong giới hạn và tooling; không phải lựa chọn mặc định để cập nhật toàn bộ plugin khi API/schema thay đổi.

### 5.3. Ví dụ kiểm tra khả năng bằng agent

Đây là ví dụ **minh họa** về entrypoint agent; nó không cung cấp file JAR agent hoàn chỉnh:

```java
import java.lang.instrument.Instrumentation;

public final class CapabilityAgent {
    public static void premain(String args, Instrumentation inst) {
        System.out.println("redefine: " + inst.isRedefineClassesSupported());
        System.out.println("retransform: " + inst.isRetransformClassesSupported());
    }
}
```

Để dùng `premain`, manifest agent phải khai báo `Premain-Class: CapabilityAgent`; nếu muốn gọi các API redefine/retransform cần khai báo các thuộc tính capability tương ứng theo tài liệu `java.lang.instrument`, và VM phải hỗ trợ. Không suy ra từ ví dụ này rằng `isRedefineClassesSupported()` luôn trả `true` trên mọi Java 17 distribution.

## 6. Restart tiến trình: ranh giới sạch hơn cho dependency và class schema

Khởi động JVM mới là cách dễ hiểu để áp dụng một bộ artifact hoàn chỉnh: tất cả class loader, module graph, static state và native resource trong JVM mới được khởi tạo lại. Thay vì cố thay class đang sống, deployment có thể tạo một process phiên bản mới, kiểm tra sức khỏe rồi chuyển traffic.

Những ưu điểm:

- Có thể cập nhật cấu trúc class, library version và JVM flags một cách nhất quán.
- Dependency graph được dựng lại từ đầu, tránh cache class loader cũ.
- Mỗi process có vòng đời và bộ nhớ riêng; các lỗi internal không nhất thiết làm process khác hỏng.
- Rollback có thể thực hiện bằng cách chạy lại release đã xác nhận, miễn schema/data compatibility cho phép.

Nhưng restart không tự giải quyết mọi thứ:

- In-memory session/cache bị mất nếu không được lưu/khôi phục.
- Database schema migration có thể không backward-compatible.
- External request, message ack hoặc side effect có thể bị xử lý trùng nếu không có idempotency.
- Process cũ cần graceful drain trước khi dừng để giảm gián đoạn.
- Nhiều phiên bản cùng chạy trong rolling deployment có thể cần API/data compatibility hai chiều.

### Rolling/blue-green deployment

Một chiến lược vận hành ổn định là chạy process mới song song, kiểm tra health/readiness, đổi router/load balancer, drain process cũ rồi dừng. Đây là **restart với cơ chế điều phối**, không phải hot replacement trong cùng JVM. Nó có thể đạt thời gian gián đoạn rất thấp khi hệ thống được thiết kế phù hợp, nhưng vẫn phụ thuộc session routing và tính tương thích dữ liệu.

## 7. Chọn chiến lược theo mức thay đổi

| Loại thay đổi | Hướng thường phù hợp | Lý do |
|---|---|---|
| Đổi thuật toán nội bộ plugin, contract ổn định | Plugin loader mới | Có thể song song V1/V2 rồi đổi routing |
| Đổi dependency nội bộ plugin | Plugin loader mới nếu dependency cô lập được | Không xung đột loader chung |
| Đổi method body để sửa lỗi trong cùng class identity | Instrumentation nếu VM và agent hỗ trợ | Không cần tạo instance/version mới nhưng có giới hạn schema |
| Thêm/bớt public API, đổi binary contract | Restart hoặc migration versioned interface/loader | Caller và state cần đồng bộ contract |
| Đổi JVM flags, native libraries, core framework | Restart process | Cần môi trường JVM mới hoàn chỉnh |
| Cần ranh giới crash/resource rõ ràng | Process riêng cho plugin hoặc restart | Class loader không cô lập heap/process |
| Muốn rollback nhanh không mất in-memory state | Cân nhắc plugin loader V1/V2 cùng sống, với state được tách riêng | Cần kiểm soát quiescence và compatibility |

Đây là định hướng, không phải quy tắc tuyệt đối. Nếu plugin đã có native state hoặc thread không thể đóng, ngay cả thay loader mới cũng có thể không sạch; restart thường đáng tin hơn. Nếu chỉ đổi một method body và agent đã tích hợp sẵn, instrumentation có thể tiết kiệm thời gian nhưng cần kiểm thử khắt khe.

## 8. Quy trình cập nhật plugin có kiểm soát

1. **Validate artifact:** xác minh version, checksum/signature, compatibility contract API, dependency versions và policy trước khi nạp.
2. **Stage riêng:** đưa JAR vào đường dẫn không ghi đè artifact đang hoạt động; tạo loader/module layer mới.
3. **Initialize candidate:** tạo instance mới, khởi tạo resource, chạy self-test và health check trước khi nhận traffic.
4. **Cutover:** chuyển định tuyến request mới; bảo đảm consumer nào nắm instance cũ vẫn chạy theo chính sách rõ ràng.
5. **Drain:** chờ in-flight tasks, background jobs và callback cũ kết thúc hoặc timeout.
6. **Stop và cleanup:** dừng plugin cũ theo thứ tự phụ thuộc, gỡ listener, cancel task, đóng resource và loader.
7. **Observe:** giám sát leak loader, thread count, errors, latency và external state.
8. **Rollback:** nếu V2 lỗi, chuyển lại V1 còn healthy hoặc deploy release cũ theo quy trình; không quên side effect đã phát sinh dưới V2.

**Không bao giờ hứa rollback chính xác 100% chỉ bằng đổi `AtomicReference`.** Trạng thái ngoài JVM, dữ liệu đã ghi hoặc event đã phát không tự đảo ngược.

## 9. Những lỗi phổ biến

| Triệu chứng | Nguyên nhân | Khuyến nghị |
|---|---|---|
| Thay JAR nhưng vẫn chạy code cũ | Class đã được JVM định nghĩa và loader cache | Tạo loader mới hoặc restart |
| `ClassCastException` giữa host và plugin | API được định nghĩa bởi nhiều loader | Giữ contract API chung ở parent loader |
| Metaspace tăng sau nhiều lần reload | Loader cũ còn reachable qua thread, listener, static registry | Audit references, cleanup tài nguyên và GC roots |
| File JAR bị khóa khi cập nhật | Loader còn mở JAR/file handle | Dùng artifact versioned, close loader sau drain |
| HotSwap báo unsupported schema change | Instrumentation chỉ hỗ trợ thay đổi giới hạn | Dùng loader mới hoặc restart khi đổi class schema |
| V2 healthy nhưng mất session | State nằm trong instance V1 | Chuyển state sang storage độc lập hoặc có migration |
| Rollback thất bại vì schema DB mới | External data không tương thích với V1 | Áp dụng migration expand/contract, kiểm thử backward compatibility |
| Plugin không dừng được | Thread/native resource không quản lý đúng lifecycle | Thiết kế close/cancel rõ hoặc đưa plugin vào process riêng |

## 10. Checklist phát hành

- [ ] Có contract/version policy cho host và các plugin.
- [ ] Plugin loader mới được tạo từ artifact không ghi đè bản đang chạy.
- [ ] API chung không bị nạp trùng bởi các plugin loaders.
- [ ] Có health check trước cutover và drain in-flight requests sau cutover.
- [ ] Có cleanup toàn bộ thread, executor, listener, resource và loader của bản cũ.
- [ ] Kiểm tra class unloading/metaspace theo workload reload lặp.
- [ ] Instrumentation chỉ dùng khi capability của VM và mức thay đổi schema cho phép.
- [ ] Restart/rolling deployment có kế hoạch session/data migration và rollback release.

**Kết luận:** Thay plugin bằng loader mới tạo một implementation mới nhưng không sửa định nghĩa class đã nạp; instrumentation thay bytecode của class đang tồn tại trong các giới hạn VM; restart xây lại toàn bộ JVM từ artifact mới. Chọn cách cập nhật dựa trên contract compatibility, state migration, resource lifecycle và yêu cầu uptime, thay vì chỉ nhìn vào việc có thể thay file JAR trên đĩa hay không.
