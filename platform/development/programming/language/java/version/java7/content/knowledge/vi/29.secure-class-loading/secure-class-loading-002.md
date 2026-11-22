# Giải phóng tệp JAR bằng `URLClassLoader.close()` trong Java

## 1. Khi nào phải giải phóng một tệp JAR?

Một ứng dụng Java có thể nạp plugin từ JAR trong lúc JVM đang chạy, thay vì đưa mọi library vào application classpath lúc khởi động. `java.net.URLClassLoader` cho phép tạo một class loader với URL search path trỏ tới các JAR/thư mục; loader đó tìm classes và resources khi ứng dụng cần.

Điểm dễ quên: việc nạp classes/resources có thể khiến loader **mở tệp JAR và giữ handles**. Nếu một server thay phiên bản plugin nhiều lần mà không quản lý loaders đã cũ, các tệp có thể còn bị mở lâu hơn cần thiết:

- Trên Windows, thao tác thay thế/xóa/đổi tên JAR đang được giữ có thể thất bại.
- Trên Linux/macOS, tệp có thể unlink được dù handles vẫn mở, không có nghĩa tài nguyên đã được giải phóng.
- Nhiều reload liên tiếp có thể tăng số open file descriptors/handles.
- Metadata, classes và object graphs có thể vẫn ở trong memory khi có references tới class loader, không chỉ do file handles.
- Các workers đang chạy trong plugin có thể nạp classes mới **đúng lúc** một thread khác đóng loader, tạo race không có kết quả được đảm bảo.

Từ Java 7, `URLClassLoader` triển khai `java.io.Closeable` và có phương thức `void close() throws IOException`. API này **vẫn còn được hỗ trợ trên Java SE 21 và các JDK hiện đại**. Đó là cách chuẩn để kết thúc vòng đời tài nguyên JAR do loader quản lý, không cần reflection vào JDK internals hoặc trông chờ garbage collector.

Bài học này giải quyết đề bài **“Giải phóng tệp JAR bằng URLClassLoader.close”** trong nhóm **“Nạp lớp an toàn”**.

**Special Note của module:** chỉ dùng kiến thức còn áp dụng hiện nay, không hướng dẫn cách làm lỗi thời. Nội dung dưới đây sử dụng Java 21, `try-with-resources`, `URLClassLoader.close`, `Files` và `JarOutputStream`; **không** dùng finalizer, `Unsafe` hay hack đóng những `JarFile` nội bộ. Các vấn đề security, lifecycle và quyền sở hữu tài nguyên được giải thích riêng.

### Sau khi học, bạn sẽ biết

1. Tạo một `URLClassLoader` để đọc một JAR cụ thể.
2. Đóng loader bằng `try-with-resources` hoặc `close()`.
3. Hiểu thứ gì **không còn nạp được** sau close.
4. Hiểu vì sao classes đã nạp hoặc parent classes có thể vẫn truy cập được sau close.
5. Phân biệt đóng JAR/file handles với class unloading, object cleanup và xóa JAR trên disk.
6. Quản lý `InputStream` khi đọc resource.
7. Xử lý `IOException`/suppressed exceptions và repeated close.
8. Ngăn race giữa `loadClass` và `close`.
9. Dừng plugin có thứ tự: stop admission, drain, cleanup, close, release references.
10. Chạy Java 21 demo tự tạo JAR, nạp class/resource rồi close và xóa file thử.

## 2. Hiểu đúng `URLClassLoader`

`URLClassLoader` là subclass của `SecureClassLoader` và implements `Closeable`. Một instance của nó nhận search path bằng `URL[]`, thường chứa:

- URL `file:` trỏ tới một thư mục (path URL kết thúc bằng dấu `/`).
- URL `file:` trỏ tới một tệp JAR thông thường.
- URL `jar:` theo cú pháp `jar:file:/.../plugin.jar!/entry` trong các trường hợp thích hợp.
- Các URLs có protocol được handler hỗ trợ, nhưng việc thực thi remote dynamic code cần chính sách an toàn riêng.

Ví dụ tạo loader từ JAR path:

~~~java
Path jarPath = Path.of("plugins", "plugin.jar");
URL jarUrl = jarPath.toUri().toURL();
try (URLClassLoader loader = new URLClassLoader(
        new URL[] {jarUrl}, ClassLoader.getPlatformClassLoader())) {
    Class<?> pluginType = loader.loadClass("plugin.Entry");
    // Dùng plugin khi loader còn mở.
}
~~~

Đây là **snippet minh họa**, chưa phải chương trình độc lập: cần imports, tệp `plugins/plugin.jar` và `plugin.Entry` thực sự tồn tại. `ClassLoader.getPlatformClassLoader()` là API Java 9+, còn bài chạy đầy đủ dùng JDK 21 và tự tạo JAR nên không cần file chuẩn bị trước.

### 2.1. Parent delegation và nguồn gốc class

Thông thường `loadClass` hỏi parent trước khi tự tìm class từ URLs của loader. Vì vậy một class trùng tên ở parent có thể được parent định nghĩa, dù JAR con cũng chứa nó. Khi muốn xác minh class thuộc loader plugin:

~~~java
boolean ownedByPluginLoader = pluginType.getClassLoader() == loader;
~~~

Đây là snippet minh họa với `pluginType` và `loader` đã khai báo. Nếu parent load class trước, phép so sánh có thể false. Không nên tưởng mọi class trong JAR đều chắc chắn được định nghĩa bởi loader con.

Một class có **binary name + defining class loader** làm định danh kiểu trong JVM; cùng tên class từ hai loaders khác nhau không nhất thiết cast được cho nhau. Đây là rủi ro riêng của plugin architectures và version switches.

### 2.2. Load “khi cần”, không load toàn bộ JAR ngay

`new URLClassLoader(...)` không hứa sẽ đọc hết các entries hoặc load mọi class ngay trong constructor. Search có thể mở JAR khi cần tìm `loadClass`, `getResource` hoặc `getResourceAsStream`. Do đó `close` đóng các tệp **do loader đã mở**, không tự quét cả filesystem để tìm bất kỳ JAR nào trùng tên.

Nếu code sau đó tham chiếu một dependency chưa load, JVM có thể phải thực hiện thêm class loading. Điều này rất quan trọng khi quyết định thời điểm close.

### 2.3. Cần nạp class đáng tin cậy

`URLClassLoader` chỉ quản lý cách tìm và định nghĩa classes; **nó không phải sandbox**. Nạp và chạy classes từ JAR chưa được kiểm soát có thể cho code đó thực thi trong JVM với quyền của process. Trước khi load, cần kiểm tra source, integrity, dependencies, trust policy; với code không tin cậy, cần isolation ở mức process/OS thay vì chỉ class loader.

## 3. `URLClassLoader.close()` làm chính xác những gì?

Javadoc Java SE 21 mô tả:

**Một:** Sau `close()`, loader không còn dùng để tìm/nạp các classes và resources **mới** do chính loader định nghĩa từ URL search path của nó.

**Hai:** Classes/resources đã được load và những classes/resources thuộc parent hierarchy **vẫn có thể truy cập**. `close` không hủy `Class<?>`, không xóa plugin instances và không thu hồi quyền chạy code đã nạp.

**Ba:** Với `jar:` và `file:` URLs, loader thực hiện best effort để đóng các tệp nó đã mở. Nếu gặp nhiều `IOException`, những lỗi thứ hai trở đi có thể được gắn làm suppressed exceptions.

**Bốn:** Nếu một thread đang `loadClass` đúng lúc thread khác `close`, kết quả của load là **undefined** theo Javadoc. Đây không phải API có safe concurrent load/close guarantee.

**Năm:** Gọi `close()` trên một loader đã closed **không có tác dụng**. Do đó repeated close là idempotent.

### 3.1. Trạng thái trước/sau đóng

| Thành phần/thao tác | Trước close | Sau close |
| --- | --- | --- |
| `loadClass("plugin.A")` chưa từng load | Có thể load từ JAR | Không thể mới load từ search path của loader đã đóng |
| `Class<?>` của `plugin.B` đã load | Accessible | Vẫn accessible khi còn references |
| Method của `plugin.B` đã load | Có thể gọi | Có thể gọi nếu không cần thêm class/resource |
| `java.lang.String` từ parent/bootstrap | Accessible | Vẫn accessible |
| `getResource("config/info.txt")` chỉ có trong JAR con | Có thể tìm thấy | Không còn tìm mới từ JAR loader con |
| `getResourceAsStream` được loader quản lý | Có thể giữ stream đọc | Các resources đã mở qua method này bị close khi loader close |
| File handles do loader mở | Có thể còn mở | Loader cố đóng |
| Object plugin đang chạy | Không tự dừng | **Vẫn không tự dừng** |
| Tệp JAR trên disk | Còn tồn tại | **Không tự bị xóa** |
| Class metadata trong JVM | JVM quản lý | **Không tự unload ngay** |

**Chú ý:** close rồi vẫn gọi được method của class đã load **không có nghĩa mọi lời gọi mãi mãi đều thành công**. Nếu method có lazy resolution của một class khác trong cùng JAR chưa được load, việc thực thi có thể thất bại (ví dụ `NoClassDefFoundError`). Trong production, nên kết thúc active plugin work trước khi close.

### 3.2. Đối tượng loader vẫn tồn tại sau close

`close` không đặt biến `loader` thành null, không xóa mảng từ `getURLs()`, cũng không ép GC. Ví dụ:

~~~java
loader.close();
URL[] oldSearchPath = loader.getURLs();
~~~

Đây là đoạn minh họa khi caller sở hữu loader. Việc `getURLs` còn trả URL **không cho biết tệp JAR vẫn mở** hoặc các URLs ấy có thể tiếp tục load classes mới. Nó là thông tin đường dẫn, không phải phép thử lifecycle tài nguyên.

### 3.3. Parent vẫn có thể cung cấp class/resource

Nếu `loader.loadClass("java.lang.String")` sau close vẫn hoạt động, đây là hành vi hợp lệ do class `String` đến từ bootstrap/platform hierarchy, không có nghĩa JAR plugin đã bị mở lại. Tương tự, một resource có sẵn ở parent có thể còn tìm thấy qua child loader đã closed.

## 4. `try-with-resources` để đóng đúng scope

`URLClassLoader implements Closeable` nên có thể dùng try-with-resources:

~~~java
try (URLClassLoader loader = new URLClassLoader(
        new URL[] {jarPath.toUri().toURL()},
        ClassLoader.getPlatformClassLoader())) {
    Class<?> entry = loader.loadClass("plugin.Entry");
    // Sử dụng trong phạm vi này.
}
// Loader được gọi close() khi rời block.
~~~

Đây là snippet minh họa với `jarPath`/`plugin.Entry` do ứng dụng cung cấp. Nếu body throw, Java vẫn thử `close()` theo contract của try-with-resources. Nếu cả body và close đều throw, lỗi close thường trở thành **suppressed exception** trên lỗi chính của body, không bị im lặng làm mất dấu.

### 4.1. Trường hợp plugin dùng lâu dài

**Phản ví dụ về lifetime:**

~~~java
Object createPlugin(Path jarPath) throws Exception {
    try (URLClassLoader loader = new URLClassLoader(
            new URL[] {jarPath.toUri().toURL()},
            ClassLoader.getPlatformClassLoader())) {
        return loader.loadClass("plugin.Entry")
                .getConstructor().newInstance();
    }
}
~~~

Đây là snippet chưa độc lập và **không nên dùng nếu host sẽ tiếp tục sử dụng plugin về sau**. Factory đã close loader trước khi caller sử dụng object được trả về. Plugin có thể gọi một dependency/resource mới sau đó và thất bại.

**Phương án đúng:** host quản lý một holder/resource bundle gồm plugin instance **và** loader, giữ loader mở trong thời gian plugin ACTIVE, rồi stop/drain/plugin-owned cleanup và close loader đúng lúc.

### 4.2. Owner chịu trách nhiệm đóng

Component tạo loader thường chịu trách nhiệm đóng. Nếu một API nhận loader từ code khác, nó không nên tự đóng loader không thuộc quyền mình. Việc đóng loader đang được nhiều plugin tasks chia sẻ có thể chặn những loads hợp lệ của các tasks đó.

Trong class loader hierarchy, không đóng parent loader của JVM chỉ vì bạn sở hữu một `URLClassLoader` con.

### 4.3. Nếu phải đóng thủ công

Code dài hạn có thể giữ loader làm field và implement `AutoCloseable`:

~~~java
@Override
public void close() throws IOException {
    // Chỉ khi đã quiesce/drain mọi hoạt động đang dùng loader.
    loader.close();
}
~~~

Đây là snippet minh họa, chưa khai báo class/field. Trước khi đóng, component nên ngừng admission; đảm bảo cleanup không bỏ qua loader nếu plugin-specific shutdown ném exception (dùng `finally` hoặc aggregation phù hợp).

## 5. Quản lý resource streams bên trong JAR

`URLClassLoader.getResourceAsStream(name)` có thể trả `InputStream`, hoặc `null` nếu resource không có.

~~~java
try (InputStream in = loader.getResourceAsStream("config/info.txt")) {
    if (in == null) {
        throw new IOException("Resource not found");
    }
    String content = new String(in.readAllBytes(), StandardCharsets.UTF_8);
}
~~~

Đây là snippet minh họa, cần imports và loader đang mở. `readAllBytes` phù hợp dữ liệu nhỏ; với resource không kiểm soát kích thước, cần streaming và byte budget để tránh giữ payload lớn trong heap.

**Hai lớp ownership:**

- Người gọi sở hữu `InputStream` của một tác vụ, nên đóng sớm bằng try-with-resources.
- Owner của `URLClassLoader` chịu trách nhiệm đóng loader sau toàn bộ lifecycle plugin.

Javadoc nêu rằng nếu loader được close, những resources mở qua `URLClassLoader.getResourceAsStream` cũng sẽ được đóng. Tuy nhiên điều đó **không có nghĩa** mọi stream mở bằng `getResource(name).openStream()` hay mọi `JarFile` do các components khác tạo đều do loader quản lý. Đóng từng resource theo đúng owner.

### 5.1. Resource đã trả về URL trước close

Giả sử bạn giữ `URL url = loader.getResource("config/info.txt")`, rồi close loader. Giá trị `url` không bị tự động biến mất; nếu bạn tự gọi `url.openStream()` sau đó, nó có thể mở một connection **riêng** không do loader cũ sở hữu và chịu cache/locking behavior khác. Vì vậy **không dùng một URL đã lưu** để chứng minh loader vẫn active, cũng không bỏ qua closing streams mở trực tiếp.

### 5.2. Nếu stream đang được đọc khi close

Không nên giả định việc đọc sẽ hoàn tất bình thường hoặc luôn có cùng loại exception. Nếu plugin workers đang đọc stream/JAR mà loader bị close, kết quả phụ thuộc đường đọc và resource state. Nên dừng nhận work mới và drain các streams/loads đang dùng trước khi close.

### 5.3. JAR mở riêng cần đóng riêng

~~~java
try (JarFile jar = new JarFile(jarPath.toFile())) {
    // Inspect entries do code này sở hữu.
}
~~~

Đây là snippet minh họa với `jarPath` và imports. Một `JarFile` mở **ngoài** loader có ownership độc lập. `loader.close()` không được xem là “đóng toàn bộ JarFile trong JVM”. Tương tự, `ZipFile`, `FileSystems.newFileSystem`, `Files.newInputStream`, native libraries và custom URLConnections có lifecycle riêng.

## 6. Close không phải unload class hoặc dừng plugin

Không có public `ClassLoader.unloadClass(...)` để gọi thay `close`. JVM có thể unload classes khi defining loader và các classes/instances không còn reachable; đó là quyết định của GC/runtime, không phải kết quả tức thì của close.

Những tham chiếu có thể giữ một plugin loader sống lâu:

- Plugin instances được host giữ trong registry/cache.
- `Class<?>`, `Method`, `MethodHandle` hoặc reflection artifacts được lưu ở host.
- Listeners/callbacks vẫn đăng ký với event bus.
- Threads do plugin tạo vẫn sống.
- Thread context class loader (`Thread.currentThread().getContextClassLoader()`) còn trỏ tới plugin loader.
- `ThreadLocal` hoặc static fields/caches vẫn liên kết đến objects của plugin.
- Futures, scheduled tasks, native callbacks hoặc service registry references.

**Quy trình đúng:** stop admission → drain/cancel jobs có policy → unregister listeners → close plugin-owned resources → close loader → bỏ strong references → cho JVM thu hồi khi có thể.

`System.gc()` không bảo đảm unload classes hay giải phóng JAR ngay. Không khuyên dùng `finalize()` hoặc hack JDK-internal reflection để đóng JAR — những cách này không phù hợp Special Note về API hiện hành.

### 6.1. Close không thu hồi quyền thực thi

Code plugin đã nạp vẫn có thể tiếp tục chạy nếu còn thread/instance; close không revoke permission, không dừng CPU, không tự rollback DB writes hoặc I/O side effects. Trong kiến trúc plugin, cần contract `start/stop` hoặc `AutoCloseable` riêng của plugin.

### 6.2. Giới hạn của “already loaded can still work”

Nếu class `plugin.First` đã load và method `message()` chỉ trả literal, gọi sau close có thể thành công. Nếu method tham chiếu `plugin.Helper` chưa load và loader cần đọc thêm JAR thì có thể phát sinh linkage error. Đây là lý do không để production requests tiếp tục dùng một plugin đã retired chỉ vì một demo gọi method sau close thành công.

### 6.3. Class unloading metrics

Muốn kiểm tra classloader leak, dùng JFR/heap dump/JVM classloading metrics và theo dõi số loaders/classes retained qua nhiều reload cycles. **Đừng chỉ kiểm tra Files.delete trên Linux**, vì unlink semantics không cho biết còn giữ open handles hay không.

## 7. Concurrent `loadClass` với `close` là race không được hỗ trợ

Oracle Javadoc nói: nếu một thread đang load class khi close được gọi, **kết quả load undefined**.

~~~text
Worker A                             Shutdown B
--------                             ----------
loader.loadClass("plugin.Helper")
    | (đang tra cứu JAR)
    |                                 loader.close()
    +-------------- RACE -------------+
~~~

Không được giả định A chắc chắn thành công hay luôn ném `ClassNotFoundException`. Cần điều phối lifecycle ở tầng ứng dụng.

### 7.1. Một state machine rõ ràng

~~~text
ACTIVE
  | - nhận requests/classes mới
  v
STOPPING
  | - từ chối admission mới, chuyển traffic sang version khác
  v
DRAINING
  | - đợi active tasks/in-flight class loads hoàn tất tới deadline
  v
CLOSING
  | - dừng plugin, đóng resource/streams/executors do plugin sở hữu
  | - loader.close()
  v
CLOSED
  | - dọn JAR cũ khi không còn owner khác giữ
  v
RELEASED
~~~

Đây là **state machine do ứng dụng thiết kế**, không phải trạng thái tự động của `URLClassLoader`. Nếu check `active=true` và tăng số leases là hai thao tác tách biệt không atomic, request có thể lọt vào sau khi shutdown vừa thấy in-flight count bằng 0. Cần lock hoặc admission protocol đồng bộ khi quyết định “accept request” và “bắt đầu STOPPING”.

### 7.2. Deadline của việc dừng

Nếu tasks không kết thúc trong khoảng thời gian cho phép, không nên cứ chờ vô hạn. Phải có cancellation/retry/error policy cụ thể và xác định liệu tasks có đang trong native I/O hoặc đoạn code không thể interrupt không. `Thread.interrupt()` không bảo đảm stop tức thì. `URLClassLoader.close` không phải cách cancel tasks; đừng gọi close trong lúc threads đang load classes chỉ để ép chúng dừng.

### 7.3. Hot reload qua hai đường dẫn versioned

Tạo loader mới từ `plugin-v2.jar`, validate plugin v2, chuyển traffic/route sang v2, rồi drain và close loader của `plugin-v1.jar`. Giữ **đường dẫn JAR riêng cho từng version** giúp giảm nhu cầu overwrite file đang mở và hỗ trợ rollback. Nếu initialization v2 fail, phải đóng loader v2 trong error path.

## 8. Tệp JAR sau khi close: Windows vs POSIX

### 8.1. Tại sao `Files.delete` cần close trên Windows?

Trên Windows, một tệp đang mở có thể không thể xóa hoặc rename do file sharing/locking rules. `URLClassLoader.close()` đóng file handles mà loader đã mở, giúp giải phóng file đúng vòng đời. **Tuy nhiên**, antivirus/indexers, một `JarFile` khác hoặc một process khác vẫn có thể giữ file. Do vậy close không tự bảo đảm thao tác delete sẽ luôn thành công.

### 8.2. Xóa được trên Linux không chứng minh loader đã close

POSIX filesystems có thể cho unlink một filename dù file descriptors vẫn mở; dữ liệu sẽ chỉ được giải phóng khi handles cuối cùng đóng. Vì vậy chỉ in `Files.delete()==success` không đủ để kết luận mọi resources đã được release. Dùng đúng lifecycle, kiểm tra open descriptors và ứng dụng references.

### 8.3. JAR vẫn nằm trên disk sau close

`URLClassLoader.close()` **không tự xóa file JAR**. Cleanup file là trách nhiệm deployment code sau khi xác minh không còn resource owners. Mẫu Java bên dưới tạo JAR **tạm** thuộc chính chương trình nên nó chủ động xóa; code production không được xóa JAR người dùng chỉ vì loader của một component đã close.

### 8.4. Tại sao `getURLs()` không phải test open-file state?

`getURLs()` trả search path URL từng được cấu hình, không phải danh sách file descriptors hiện đang mở. Một loader đã close có thể vẫn trả URL cũ. Không dùng số URLs hoặc một `URL` còn sống để kết luận file lock chưa được giải phóng.

## 9. Ngoại lệ từ `close` và try-with-resources

Contract:

~~~java
public void close() throws IOException
~~~

Đây là chữ ký minh họa của public method.

- Loader cố gắng đóng tất cả các tệp nó đã mở.
- Nó bắt các `IOException` nội bộ khi đóng từng file để thử những file còn lại.
- Nếu chỉ một IOException, nó ném lại lỗi đó.
- Nếu nhiều lỗi, lỗi thứ hai và các lỗi tiếp theo được thêm vào `getSuppressed()` của lỗi đầu.
- Unchecked exceptions và errors **không nhất thiết** bị bắt bởi cơ chế best-effort này.
- Lần close tiếp theo khi đã closed là no-op.

### 9.1. Khi body cũng lỗi

Với try-with-resources, nếu code trong body throw, exception đóng resource từ `close` thường được gắn làm suppressed exception của lỗi body. Đây là một tầng suppressed khác với nhiều IOException được gom bên trong riêng `URLClassLoader.close`. Khi xử lý incident, kiểm tra primary exception, `getCause()` và `getSuppressed()` thay vì chỉ log message đầu.

### 9.2. Không nuốt lỗi I/O khi cleanup

Nếu close lỗi, nên ghi nhận version/path của plugin, exception và suppressed exceptions trong log phù hợp. Tránh dùng file URL chứa secrets trong log công khai. Nếu vẫn có file lock, deployment nên trì hoãn retry/xóa file với backoff policy, không lập tức overwrite. **Không gọi GC** như một biện pháp chữa file handle lock.

### 9.3. Close lặp

`URLClassLoader.close()` có tính idempotent. Bài test bên dưới gọi close lần hai chỉ để xác minh. Code bình thường chỉ cần một owner đóng một lần; redundant repeated close không phải kỹ thuật tăng độ chắc chắn.

## 10. An toàn thực thi: không dùng URLClassLoader làm sandbox

Chủ đề cha “Nạp lớp an toàn” còn liên quan đến **nguồn và quyền của code**. Một class loader cho phép tìm/nạp classes, không biến những classes đó thành code được cách ly khỏi JVM host.

Không cho input chưa tin cậy quyết định tùy ý `JAR URL` và class name để host nạp/thực thi. Đối với plugins:

1. Chỉ đọc từ deployment allowlist/trust store.
2. Kiểm tra integrity/signature/checksum theo threat model.
3. Pin/scan các dependencies và quy định version.
4. Chạy service với quyền OS tối thiểu.
5. Không lộ handles đến privileged service, secrets hoặc process-wide registries cho plugins không tin cậy.
6. Nếu thật sự phải chạy mã không đáng tin, dùng process/container sandbox và IPC interface riêng.

**Không dùng SecurityManager policy theo hướng dẫn cũ để xây sandbox Java mới.** SecurityManager bị deprecated và bị vô hiệu hóa trên JDK hiện đại; `SecureClassLoader` trong inheritance tree của `URLClassLoader` không tự tạo ra boundary an toàn. Đóng loader không thu hồi capabilities của code đã load.

### 10.1. URL không phải chỉ là local file

`URLClassLoader` nhận URL và có thể liên hệ với nhiều protocols/handlers. Nếu một endpoint cho client gửi URL tùy ý, ứng dụng có thể phát sinh network/file access không mong muốn, thậm chí nạp code attacker. Hạn chế source, scheme, path traversal và chính sách version trước khi tạo loader.

### 10.2. Parent/class identity

Nếu host và plugin dùng interface chung, nên để API chung được định nghĩa bởi parent loader và chỉ để code riêng của plugin trong child loader. Nếu cùng tên `PluginApi` được định nghĩa bởi hai loaders, type identities khác và có thể `ClassCastException` khi tích hợp. `close` không sửa được vấn đề architecture này.

## 11. Java 9+ và những trường hợp không dùng URLClassLoader

`URLClassLoader` vẫn phù hợp cho **classpath-style JARs** trên Java 17/21 và hỗ trợ multi-release JAR theo runtime rules. Nhưng nếu yêu cầu nạp **named modules** với readability/exports/opens của JPMS, cần xem `ModuleFinder`/`ModuleLayer` hoặc một module-aware framework; `URLClassLoader` không tự là module resolver đầy đủ.

`ClassLoader` base class không triển khai `Closeable`, nên các custom loaders có thể cần lifecycle methods riêng. Không gọi close lên mọi class loader bằng cast mù quáng.

Nếu một plugin có JNI/native libraries, chúng có lifecycle/locking riêng; `URLClassLoader.close` không hứa unload native libraries hoặc giải phóng mọi DLL/file handle do JNI tạo.

## 12. Chương trình Java 21 đầy đủ: tạo JAR, nạp, close và dọn

Đây là một demo **tự chứa**, không cần JDBC/network/third-party JAR. Nó tạo thư mục tạm, ghi hai source files cho `plugin.First` và `plugin.Second`, dùng `JavaCompiler` của JDK để compile thành classes, tạo JAR bằng `JarOutputStream`, rồi dùng `URLClassLoader` để nạp class và resource.

Chương trình cố ý:

- Nạp `plugin.First` và gọi method `message()` **trước** close.
- Đọc `config/info.txt` từ JAR, đóng `InputStream` riêng.
- Close loader bằng `try (loader)`.
- Gọi lại method của class đã nạp để chứng minh object/class vẫn truy cập được.
- `loadClass("plugin.First")` trả lại class đã nạp, không yêu cầu đọc JAR mới.
- Truy cập parent class `java.lang.String`.
- Thử nạp `plugin.Second` **lần đầu sau close**, nhận `ClassNotFoundException`.
- Xác minh resource chỉ có trong JAR con không còn được tìm mới sau close.
- Gọi close lại để kiểm chứng idempotence.
- Xóa JAR tạm sau close và dọn toàn bộ thư mục trong `finally`.

**Chú ý về nền tảng:** Dòng kết quả xóa JAR là kết quả của **môi trường kiểm thử**, không phải bảo đảm tệp có thể xóa trên mọi OS nếu antivirus/process khác giữ lock. Chương trình dùng `JavaCompiler` nên phải chạy bằng **full JDK 21**, không phải runtime thiếu compiler.

### 12.1. File Java độc lập

Tạo `src/main/java/demo/UrlClassLoaderCloseExample.java`:

~~~java
package demo;

import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.jar.JarEntry;
import java.util.jar.JarOutputStream;
import java.util.stream.Stream;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public final class UrlClassLoaderCloseExample {
    private UrlClassLoaderCloseExample() {}

    private static void writePluginClass(Path source, String name, String value)
            throws IOException {
        String code = "package plugin;\n"
                + "public final class " + name + " {\n"
                + "  public String message() { return \"" + value + "\"; }\n"
                + "}\n";
        Files.writeString(source, code, StandardCharsets.UTF_8);
    }

    private static void addFile(JarOutputStream jar, Path source, String entryName)
            throws IOException {
        jar.putNextEntry(new JarEntry(entryName));
        Files.copy(source, jar);
        jar.closeEntry();
    }

    private static void deleteTree(Path dir) throws IOException {
        try (Stream<Path> walk = Files.walk(dir)) {
            for (Path path : walk.sorted(Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(path);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("url-loader-close-");
        try {
            Path sources = Files.createDirectories(root.resolve("src/plugin"));
            Path classes = Files.createDirectories(root.resolve("classes"));
            Path first = sources.resolve("First.java");
            Path second = sources.resolve("Second.java");
            writePluginClass(first, "First", "FIRST-OK");
            writePluginClass(second, "Second", "SECOND-OK");

            JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
            if (compiler == null) {
                throw new IllegalStateException("Run with a JDK, not a JRE-only runtime");
            }
            int result = compiler.run(null, null, null,
                    "--release", "21", "-encoding", "UTF-8",
                    "-d", classes.toString(), first.toString(), second.toString());
            if (result != 0) {
                throw new IllegalStateException("Plugin source compilation failed");
            }

            Path archive = root.resolve("sample-plugin.jar");
            try (JarOutputStream jar =
                         new JarOutputStream(Files.newOutputStream(archive))) {
                addFile(jar, classes.resolve("plugin/First.class"),
                        "plugin/First.class");
                addFile(jar, classes.resolve("plugin/Second.class"),
                        "plugin/Second.class");
                jar.putNextEntry(new JarEntry("config/info.txt"));
                jar.write("HELLO-RESOURCE".getBytes(StandardCharsets.UTF_8));
                jar.closeEntry();
            }

            URL url = archive.toUri().toURL();
            URLClassLoader loader = new URLClassLoader(
                    new URL[] {url}, ClassLoader.getPlatformClassLoader());
            Class<?> firstClass;
            Object firstInstance;
            Method messageMethod;
            try (loader) {
                firstClass = loader.loadClass("plugin.First");
                firstInstance = firstClass.getConstructor().newInstance();
                messageMethod = firstClass.getMethod("message");
                System.out.println("owned-by-url-loader="
                        + (firstClass.getClassLoader() == loader));
                System.out.println("before-close=" + messageMethod.invoke(firstInstance));
                try (InputStream in = loader.getResourceAsStream("config/info.txt")) {
                    if (in == null) {
                        throw new IOException("JAR resource is missing");
                    }
                    System.out.println("resource-before-close="
                            + new String(in.readAllBytes(), StandardCharsets.UTF_8));
                }
            }

            System.out.println("already-loaded-after-close="
                    + messageMethod.invoke(firstInstance));
            System.out.println("loaded-class-still-known="
                    + (loader.loadClass("plugin.First") == firstClass));
            System.out.println("parent-class-still-available="
                    + (loader.loadClass("java.lang.String") == String.class));

            boolean newClassBlocked = false;
            try {
                loader.loadClass("plugin.Second");
            } catch (ClassNotFoundException expected) {
                newClassBlocked = true;
            }
            System.out.println("new-class-blocked=" + newClassBlocked);
            System.out.println("new-resource-unavailable="
                    + (loader.getResource("config/info.txt") == null));
            loader.close();
            System.out.println("repeated-close-ok=true");
            Files.delete(archive);
            System.out.println("jar-removed-after-close=" + Files.notExists(archive));
        } finally {
            deleteTree(root);
        }
    }
}
~~~

### 12.2. Biên dịch và chạy

Đặt file ở đường dẫn trên, đứng tại thư mục chứa `src` và dùng JDK 21:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/UrlClassLoaderCloseExample.java
java -cp out demo.UrlClassLoaderCloseExample
~~~

Đây là một chương trình đầy đủ chỉ dùng JDK; `javac` tạo output ở `out`, còn bản thân demo tạo JAR thử nghiệm trong temporary directory và dọn sau khi chạy. Nếu cần kiểm tra trong CI, có thể chạy ở máy có full JDK 21 và quyền ghi vào temporary directory.

### 12.3. Stdout chính xác trong lần kiểm thử

~~~text
owned-by-url-loader=true
before-close=FIRST-OK
resource-before-close=HELLO-RESOURCE
already-loaded-after-close=FIRST-OK
loaded-class-still-known=true
parent-class-still-available=true
new-class-blocked=true
new-resource-unavailable=true
repeated-close-ok=true
jar-removed-after-close=true
~~~

### 12.4. Giải thích theo đầu ra

| Dòng | Điều được kiểm chứng |
| --- | --- |
| `owned-by-url-loader=true` | Class `plugin.First` được định nghĩa bởi loader con |
| `before-close=FIRST-OK` | Class từ JAR được khởi tạo/gọi khi loader còn mở |
| `resource-before-close=HELLO-RESOURCE` | Resource trong JAR đọc được, InputStream được đóng |
| `already-loaded-after-close=FIRST-OK` | Class/instance đã load vẫn có thể hoạt động khi không cần thêm class |
| `loaded-class-still-known=true` | Sau close vẫn trả class đã load trước đó |
| `parent-class-still-available=true` | Parent/bootstrap class vẫn accessible |
| `new-class-blocked=true` | Không thể mới load `plugin.Second` chỉ có trong JAR con đã đóng |
| `new-resource-unavailable=true` | Resource riêng của JAR con không còn tìm mới qua loader |
| `repeated-close-ok=true` | `close` lần hai là no-op |
| `jar-removed-after-close=true` | Trong môi trường test, xóa thành công file JAR tạm sau close |

### 12.5. Tại sao demo chỉ load class First trước close?

Nếu đã nạp cả First và Second trước khi close, việc nạp lại Second có thể trả class đã cached và không chứng minh loader chặn **new load**. Demo cố ý đưa `plugin.Second` vào JAR nhưng chưa hề gọi `loadClass("plugin.Second")` cho tới sau close; đó mới là phép kiểm tra phân biệt rõ.

### 12.6. Vì sao resource name được chọn đặc biệt?

`config/info.txt` chỉ có trong JAR mà demo tự tạo, không có ở parent platform loader. Nếu dùng một resource phổ biến có sẵn trong parent, `loader.getResource` có thể vẫn tìm thấy nó sau close và gây hiểu lầm. Vì vậy các test về resource cần đảm bảo **nguồn resource thuộc loader con**.

### 12.7. Tại sao không dùng `System.gc()` để test?

GC không bảo đảm lịch unload class hoặc đóng file. Demo kiểm tra semantics trực tiếp của `URLClassLoader.close`: new load bị chặn, loaded class còn gọi được và file do loader sở hữu có thể được dọn trên test host. Đây là kiểm thử hợp lý hơn so với ép GC và mong một kết quả ngẫu nhiên.

## 13. Vòng đời plugin/hot reload trong production

Một workflow thường là:

~~~text
Plugin version A đang ACTIVE
      |
      |-- khởi tạo loader version B từ JAR đường dẫn mới
      |-- validate plugin B và các dependencies
      |-- chuyển routing sang plugin B khi B sẵn sàng
      |
Plugin version A -> STOPPING
      |
      |-- từ chối requests mới tới A
      |-- đợi tasks đang chạy trên A hoàn tất hoặc cancel có policy
      |-- gọi pluginA.stop()/close()
      |-- unregister listeners/ThreadLocal/context loader
      |-- close loaderA, xử lý IOException
      |-- drop references tới A và loaderA
      |
      v
Cleanup A.jar khi không còn owners khác
~~~

Điểm quan trọng: nếu new plugin initialization fail, đóng loader mới tạo trong `finally`/try-with-resources; nếu shutdown callback của A fail, vẫn cố đóng các resources khác nhưng giữ báo cáo lỗi. **Không overwrite trực tiếp JAR version A đang được sử dụng** nếu có thể chọn path versioned.

### 13.1. Request admission phải đồng bộ với shutdown

Một volatile flag `accepting=true` mà request check trước khi tăng active count có thể race với thread shutdown. Shutdown có thể thấy active count=0 rồi đóng loader trong khi request mới bắt đầu load class. Cần một protocol đồng bộ check-then-acquire lease hoặc lock bảo đảm không xuất hiện new work sau khi bước drain đã xác định hoàn tất.

### 13.2. Retained classloaders do host

Ngay cả sau close, nếu host cache `Class<?>`, `MethodHandle`, `ServiceLoader`, callback từ plugin hoặc thread contextClassLoader vẫn trỏ tới loader cũ, JVM có thể không unload classes. Do đó file-handle cleanup và heap/class metadata cleanup phải được quan sát **riêng**.

### 13.3. Một loader không phải một security boundary

Nếu JAR do kẻ tấn công kiểm soát, việc đóng loader sau 1 giây **không** ngăn plugin code đã được thực thi đọc secrets trong thời gian ấy. Thực thi code không tin cậy cần process isolation và giới hạn quyền OS; đóng loader chỉ là resource management.

## 14. Những lỗi thường gặp

| Sai lầm | Rủi ro | Cách làm đúng |
| --- | --- | --- |
| Tạo `URLClassLoader` rồi không close | File handles/JAR còn mở quá lâu | Try-with-resources hoặc lifecycle close |
| Mở resource stream rồi không đóng | Stream/file resource bị giữ | Đóng InputStream theo scope |
| Nghĩ close tự xóa JAR | Tệp vẫn nằm trên disk | Deployment cleanup riêng |
| Nghĩ close hủy mọi plugin instance | Instances vẫn có references | Stop plugin, bỏ registry refs |
| Nghĩ close unload Class ngay | JVM không có guarantee đó | Drop references, quan sát GC/JFR |
| Close trong lúc worker load class | Undefined result | Quiesce/drain trước close |
| Trả plugin instance sau khi loader đã close | Lazy class/resource loads có thể fail | Giữ loader mở suốt lifecycle plugin |
| Bỏ qua `IOException` khi close | Che leak/lock và suppressed errors | Report/log lỗi và cleanup best effort |
| Gọi `System.gc()` để giải phóng file | Không có guarantee | `loader.close()` theo owner |
| Dùng JDK-internal reflection/Unsafe | Nonportable, lỗi thời | Public API `close` |
| Chỉ thử Files.delete trên POSIX để chứng minh close | Unlink vẫn có thể thành công khi file mở | Quan sát open handles/lifecycle |
| Nghĩ close bảo đảm delete trên mọi OS | Other processes có thể giữ file | Kiểm tra lỗi thực |
| Dùng `getURLs` để kiểm tra open/closed | Chỉ là search path metadata | State machine do ứng dụng quản lý |
| Nghĩ parent classes ngừng hoạt động sau close | Parent không bị đóng | Phân biệt child và parent |
| Dùng loader như sandbox untrusted plugin | Code có quyền JVM process | Trusted JAR + OS/process isolation |
| Giữ contextClassLoader trỏ loader cũ | Classloader leak | Restore context loader và release refs |
| Trộn duplicated API classes ở parent/child | ClassCastException/type identity | Shared API ở parent theo architecture |
| Dùng classloader để load named module và giả định đầy đủ JPMS | Module rules không tự áp | ModuleFinder/ModuleLayer phù hợp |

## 15. Câu hỏi tự kiểm tra (có lời giải)

**Câu 1.** `URLClassLoader.close()` có từ Java nào?  
**Đáp án:** Java 7 và vẫn được hỗ trợ trên Java hiện đại.

**Câu 2.** Nó đóng những tệp nào?  
**Đáp án:** Những tệp/JAR do loader đã mở cho URL search path của nó, theo best effort; không phải mọi JAR của JVM.

**Câu 3.** `ClassLoader` base có `close` không?  
**Đáp án:** Không; `URLClassLoader implements Closeable`.

**Câu 4.** Vì sao nên dùng try-with-resources?  
**Đáp án:** Tự gọi close cả trong đường thành công và khi body throw, giữ suppressed errors nếu có.

**Câu 5.** `loadClass` class chưa load sau close có còn được đọc từ JAR con?  
**Đáp án:** Không, loader đã đóng không còn new loads từ chính URLs của mình.

**Câu 6.** Class đã load trước close còn dùng được không?  
**Đáp án:** Có thể, nếu không phải resolve/load dependency mới từ closed loader.

**Câu 7.** Parent class sau close?  
**Đáp án:** Vẫn accessible theo delegation.

**Câu 8.** Close có unload classes ngay?  
**Đáp án:** Không. Cần reachability/GC, không có guarantee thời điểm.

**Câu 9.** Close có dừng plugin threads?  
**Đáp án:** Không; phải stop/await tasks riêng.

**Câu 10.** Khi một thread load class, thread khác close?  
**Đáp án:** Kết quả load undefined theo Javadoc, cần tránh race.

**Câu 11.** `close()` có thể throw?  
**Đáp án:** Có `IOException`, với nhiều errors có thể có suppressed exceptions.

**Câu 12.** Close hai lần?  
**Đáp án:** Lần hai no-op.

**Câu 13.** `getResourceAsStream` có phải đóng?  
**Đáp án:** Có. Dùng try-with-resources cho stream, dù loader cũng quản lý resources mở qua method này.

**Câu 14.** `JarFile` mở ngoài loader có bị close theo không?  
**Đáp án:** Không; mỗi owner đóng resource của mình.

**Câu 15.** Xóa JAR thành công trên Linux có chứng minh close?  
**Đáp án:** Không, POSIX có thể unlink file đang mở.

**Câu 16.** Đóng loader xong thì xóa JAR chắc chắn thành công mọi nơi?  
**Đáp án:** Không; permissions/other file holders có thể cản.

**Câu 17.** Vì sao dùng JAR path theo version khi hot reload?  
**Đáp án:** Tránh overwrite file đang mở và hỗ trợ rollback/deployment rõ ràng.

**Câu 18.** TLR/GC hay finalize giúp giải phóng JAR?  
**Đáp án:** Không nên dùng finalizer hoặc GC làm cơ chế close; gọi `URLClassLoader.close`.

**Câu 19.** URLClassLoader có đủ để sandbox code không tin cậy?  
**Đáp án:** Không; cần trusted source và process/OS isolation.

**Câu 20.** Vì sao JAR test có First và Second?  
**Đáp án:** First load trước close; Second chưa load để chứng minh new load bị chặn.

**Câu 21.** Nếu plugin class được host giữ trong static cache?  
**Đáp án:** Loader/class có thể còn reachable và không unload dù đã close.

**Câu 22.** Vì sao phải khôi phục thread contextClassLoader?  
**Đáp án:** Thread pool sống lâu có thể giữ loader cũ, gây retained classes.

**Câu 23.** `getURLs()` sau close trả URL thì loader còn mở không?  
**Đáp án:** Không thể kết luận; đó chỉ là cấu hình search path.

**Câu 24.** Với JPMS named modules, URLClassLoader có tự resolve module graph không?  
**Đáp án:** Không; cần module-aware APIs như `ModuleFinder`/`ModuleLayer`.

## 16. Checklist đưa vào dự án

- [ ] Biết rõ source JAR, parent loader và owner của `URLClassLoader`.
- [ ] Chỉ nạp trusted/allowlisted JARs, kiểm tra integrity theo security policy.
- [ ] Dùng `Path.toUri().toURL()` để trỏ JAR local, không ghép URL tùy tiện.
- [ ] Khi scope ngắn, dùng try-with-resources cho loader.
- [ ] Khi plugin sống lâu, giữ loader mở suốt thời gian plugin ACTIVE.
- [ ] Không trả plugin instance từ factory đã đóng loader quá sớm.
- [ ] Đóng `InputStream`/`JarFile`/`ZipFile`/connection riêng theo ownership.
- [ ] Quản lý plugin threads, listeners, contextClassLoader, caches và resource lifecycle.
- [ ] Ngăn new submissions và class loads trước khi close.
- [ ] Dùng drain/lease protocol đồng bộ để tránh concurrent load/close.
- [ ] Áp deadline và cancellation policy nếu tasks chưa dừng.
- [ ] Close loader bằng `close` và xử lý `IOException`/suppressed errors.
- [ ] Không dùng `System.gc`/finalizer/JDK-internal hacks thay close.
- [ ] Không giả định close tự unload class hoặc xóa JAR.
- [ ] Không giả định xóa JAR thành công trên mọi OS sau close.
- [ ] Với hot reload, ưu tiên versioned JAR paths và chuyển traffic trước khi retire old plugin.
- [ ] Theo dõi open file handles, active plugin tasks và classloader retention.
- [ ] Không dùng URLClassLoader làm sandbox và không phụ thuộc SecurityManager kiểu cũ.
- [ ] Nếu cần JPMS named modules, dùng module-aware lifecycle phù hợp.
- [ ] Áp dụng API Java hiện hành và tuân thủ đầy đủ Special Note.

## 17. Tài liệu chính thức

- [Oracle Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): hợp đồng `close()`, các tài nguyên đã mở, delegation, stream và races.
- [Oracle Java SE 25 — URLClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLClassLoader.html): chứng cứ API tiếp tục hỗ trợ trên JDK mới.
- [Oracle Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, parent delegation và resource lookup.
- [Oracle Java SE 21 — Closeable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Closeable.html): close và tài nguyên.
- [Oracle Java SE 21 — JarFile](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/jar/JarFile.html): owner và cleanup khi mở JAR trực tiếp.
- [Oracle Java SE 21 — JarOutputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/jar/JarOutputStream.html): xây JAR tạm trong ví dụ.
- [Oracle Java SE 21 — Files](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html): tạo temp files và xóa JAR sau close.
- [Oracle Java SE 21 — JavaCompiler](https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html): biên dịch classes của JAR trong demo.
- [Oracle Java SE 21 — ModuleLayer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ModuleLayer.html): lifecycle named modules của JPMS.

**Kết luận:** `URLClassLoader.close()` là API chuẩn giúp **giải phóng các JAR/file handles do loader mở và ngăn nạp classes/resources mới từ loader ấy**. Nó không xóa JAR, không unload classes ngay, không stop threads và không tạo security sandbox. Mẫu an toàn là **xác định owner → stop new loads → drain active work → cleanup plugin → close loader → bỏ references → dọn JAR khi được phép**. Đây là kiến thức còn được hỗ trợ trên Java hiện đại, không cần thủ thuật lỗi thời.
