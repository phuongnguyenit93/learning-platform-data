# Nạp lớp an toàn trong Java: Thiết kế quyền sở hữu loader trong cơ chế plugin

## 1. Bài toán: plugin nào sở hữu lớp, loader và tài nguyên?

Một ứng dụng Java có thể mở rộng bằng plugin: host tải các file JAR chứa tính năng mới, tìm class triển khai một interface và gọi chúng. Một bản thiết kế ban đầu có vẻ đơn giản:

```text
Host.jar + api.jar + plugin-a.jar + plugin-b.jar
                  |
                  v
        Class.forName(...) / ServiceLoader
                  |
                  v
              Plugin chạy
```

Khi chỉ có một plugin, mọi thứ có thể hoạt động. Sau vài lần nâng cấp hoặc thêm nhiều plugin, hệ thống gặp các lỗi khó hiểu:

- Plugin A và B cần **hai phiên bản khác nhau của một thư viện**, nhưng cả hai bị ép dùng cùng bản.
- `ClassCastException` xuất hiện dù log in tên class ở hai phía **giống hệt nhau**.
- Host nạp lại file JAR đã cập nhật nhưng vẫn gọi code cũ hoặc giữ file JAR bị khóa trên Windows.
- Sau khi disable plugin, class loader cũ vẫn không được garbage collector thu hồi vì thread, `ThreadLocal` hoặc registry tiếp tục giữ reference.
- Một thư viện dùng **thread context class loader (TCCL)** để phát hiện service provider nhưng không thấy plugin vừa cài.
- Plugin tự đóng một resource thuộc host làm những plugin khác ngừng hoạt động.
- Người vận hành tưởng một class loader riêng đồng nghĩa **sandbox bảo mật**, trong khi plugin vẫn chạy trong cùng JVM với quyền truy cập tương ứng.

Gốc của những lỗi trên là **quyền sở hữu không rõ ràng**: ai sở hữu API dùng chung, ai sở hữu implementation, ai tạo và đóng loader, ai quản lý nhiệm vụ/tài nguyên của plugin, và đối tượng nào được phép tồn tại sau khi plugin ngừng?

**Quy tắc thiết kế trọng tâm:** **Host sở hữu hợp đồng chung và vòng đời của các plugin loader; mỗi phiên bản/phiên hoạt động của một plugin có loader riêng sở hữu implementation và dependency riêng; plugin sở hữu tài nguyên runtime do chính nó tạo và phải dừng sạch trước khi host đóng loader.**

Bài thuộc chủ đề **Nạp lớp an toàn** của module Java 7. `ClassLoader`, `URLClassLoader` với `close()`, `ServiceLoader` và vòng đời resource vẫn dùng trong Java hiện đại; ví dụ được kiểm thử với **JDK 17**. Bài cũng nhắc các lựa chọn mới hơn như `ModuleLayer` (Java 9+) và nhấn mạnh **không sử dụng SecurityManager làm sandbox**: nó đã bị vô hiệu hóa vĩnh viễn kể từ JDK 24.

### Bạn sẽ học được

1. Xác định chủ sở hữu cho **host API, plugin implementation, dependencies, resources và loader**.
2. Giải thích **class identity = binary name + defining class loader**, không chỉ tên đầy đủ của class.
3. Dùng parent-first delegation của `URLClassLoader` để host và plugin cùng nhìn thấy một interface thực sự giống nhau.
4. Thiết kế một loader **mỗi plugin hoặc mỗi phiên bản plugin**, tránh các class collisions và duy trì phạm vi phụ thuộc.
5. Sử dụng `ServiceLoader.load(service, loader)` một cách tường minh; biết ảnh hưởng của TCCL.
6. Hiểu `URLClassLoader.close()` đóng file handles, **không hủy ngay classes đã được định nghĩa và không bảo đảm unloading**.
7. Định nghĩa vòng đời start/stop/quiesce/reload và chặn tài nguyên rò rỉ.
8. Biết giới hạn bảo mật, kiểm tra artifact và chọn process isolation cho code không tin cậy.
9. Phân biệt classpath plugins với **JPMS ModuleLayer** khi cần strong encapsulation.
10. Kiểm thử loader isolation, service discovery, ownership và cleanup bằng một chương trình Java 17 chạy được.

## 2. Những khái niệm không được đánh đồng

| Khái niệm | Nghĩa | Ai nên chịu trách nhiệm |
| --- | --- | --- |
| **Host** | Ứng dụng điều phối plugin và quản lý lifecycle | Quyết định cài, bật/tắt, cập nhật, loại bỏ |
| **Plugin API/SPI** | Interface, DTO, events, capability contracts được chia sẻ | **Host hoặc shared API module** do host quản trị |
| **Plugin implementation** | Code triển khai một plugin cụ thể | Loader của plugin đó định nghĩa |
| **Plugin private dependencies** | Các library chỉ plugin cần | Loader của plugin nếu cấu trúc dependency cho phép |
| **Parent ClassLoader** | Loader thấy API và phần dùng chung | Host xác định; không bị plugin đóng |
| **Plugin ClassLoader** | Loader đại diện một version/instance plugin | **Host plugin manager tạo, giữ, đóng** |
| **TCCL** | Context loader được gắn cho thread | Caller của scope tạm thời quản lý và restore |
| **ServiceLoader** | Cơ chế tìm provider của interface | Host tạo cho một phạm vi plugin, quản lý cache và lifetime |
| **Plugin instance** | Object triển khai API sau khi được nạp | Host giữ reference, plugin phải cung cấp stop/close theo contract |
| **Plugin resources** | Threads, executors, scheduled tasks, file handles, sockets, listeners, caches | Owner tạo resource phải dừng, hủy đăng ký hoặc close |
| **Registry** | Danh sách plugin, providers, callbacks | Host sở hữu; xóa references khi unload |
| **ModuleLayer** | Container module runtime theo JPMS | Host quản lý nếu ứng dụng chọn plugin dạng named modules |

**Hai chiều sở hữu khác nhau:** plugin loader **định nghĩa** classes bên trong plugin; nhưng **host** mới là thành phần **sở hữu vòng đời** và đóng loader đó. Không trao quyền đóng loader trực tiếp cho một plugin đang hoạt động; plugin không được đóng các resources thuộc host hoặc plugin khác.

### 2.1. Host API là biên giới của plugin

Nên đặt interface contract trong một JAR/module chung do host tải trước:

```java
package app.api;

public interface Plugin extends AutoCloseable {
    String id();
    void start(PluginContext context) throws Exception;
    @Override void close() throws Exception;
}
```

Đây là **đoạn thiết kế API minh họa, không phải một file độc lập**: `PluginContext` cần được định nghĩa trong shared API. Trong hệ thống thật, contract nên chỉ chứa những type đã được host sở hữu và phiên bản hóa.

Quan trọng: nếu plugin đóng gói **một bản sao** của `app.api.Plugin` trong JAR và một child-first loader định nghĩa bản sao đó, `pluginInstance instanceof app.api.Plugin` ở host có thể là `false` dù **tên binary giống nhau**. Biên giới contract phải được xác định bằng **cùng một class identity**.

### 2.2. DTO và exception cũng là một phần ABI

Không chỉ interface: các kiểu xuất hiện trong **tham số, return types, generic API, annotations, exceptions, callbacks** cũng phải được chia sẻ và tương thích.

Ví dụ: interface host trả `app.api.JobResult`; nếu plugin tải bản riêng của `JobResult` cùng tên, việc cast/serialization hoặc method linkage có thể thất bại. Do đó host API nên có một tập type biên giới nhỏ, ổn định, không tham chiếu thẳng tới model nội bộ của plugin.

Sử dụng các kiểu dữ liệu ổn định như immutable record/DTO, Java primitives, `String`, collection với payload có schema rõ; tránh để những instance thuộc implementation plugin sống mãi trong global caches của host.

## 3. Class identity: cùng tên chưa chắc cùng class

Ở Java, một type runtime được nhận diện bởi **binary name và defining class loader**.

```text
Loader A defines  plugins.GreeterPlugin  -> Class A
Loader B defines  plugins.GreeterPlugin  -> Class B

Class A.getName().equals(Class B.getName()) = true
Class A == Class B                           = false
Class A.isAssignableFrom(Class B)            = false
```

Nếu hai loader riêng cùng định nghĩa một class `plugins.GreeterPlugin` từ cùng một `.class`, Java vẫn tạo **hai Class objects khác nhau**. Instance của A không phải instance của B dù bytecode tương tự. Tĩnh (`static fields`) của class cũng gắn với class identity đó, không là một singleton chung cho cả hai loaders.

### 3.1. Tại sao có ClassCastException “cùng tên”?

Khi một plugin trả ra object mà host cố ép thành một class có cùng tên nhưng được định nghĩa ở loader khác, runtime type test không khớp. Log chỉ in `getName()` sẽ che mất phần quan trọng.

Thông tin chẩn đoán nên ghi:

```java
Class<?> actual = value.getClass();
System.out.println(actual.getName());
System.out.println(actual.getClassLoader());
System.out.println(expectedType.getClassLoader());
```

Đây là đoạn minh họa với `value` và `expectedType` đã có trong scope. Trong production log cả plugin ID, version, origin JAR, loader identity và API version, không chỉ tên class.

### 3.2. Không nhầm requesting loader và defining loader

Gọi `child.loadClass("java.lang.String")` thường trả Class được định nghĩa bởi bootstrap loader; **không phải** mọi class mà child có thể nhìn thấy đều do child định nghĩa.

Với parent-first:

```text
PluginLoader.loadClass("app.api.Plugin")
      |
      v
  Parent thấy app.api.Plugin
      |
      v
   Trả host-owned Class
```

Đây là mô hình đúng cho contract chung. `PluginLoader.loadClass("plugins.GreeterPlugin")` không có ở parent thì child tự tìm class trong plugin JAR.

### 3.3. Sibling loaders không tự thấy classes của nhau

`pluginAClassLoader` và `pluginBClassLoader` đều có parent là host loader. Chúng là **anh em**, không phải parent/child. Một plugin không được mặc nhiên nhìn thấy implementation classes của plugin kia.

Nếu A cần gọi dịch vụ của B, host nên điều phối qua **shared service interface, host registry, DTO và plugin ID** thay vì cho A nhập class private của B bằng reflection.

Điều này làm giảm coupling, giúp reload phiên bản B mà không phải recompile toàn bộ hệ thống. Nó không tự đảm bảo runtime compatibility: host vẫn phải version và validate contract.

## 4. Parent-first delegation: quy tắc mặc định

`ClassLoader.loadClass` theo mặc định:

1. Xem class đã được loader hiện tại nạp hay chưa.
2. Nhờ parent tìm class.
3. Nếu parent không tìm thấy, loader hiện tại tự tìm (`findClass`).

`URLClassLoader(URL[], ClassLoader parent)` dùng cơ chế tìm từ parent trước cho class và resources. Đây là điểm bắt đầu đơn giản, đáng tin cậy cho **classpath-based plugin**.

```java
ClassLoader hostLoader = MyHost.class.getClassLoader();

try (java.net.URLClassLoader pluginLoader =
         new java.net.URLClassLoader(
                 new java.net.URL[]{pluginJar.toUri().toURL()},
                 hostLoader)) {
    Class<?> implementation =
            Class.forName("plugins.Example", true, pluginLoader);
    // Sử dụng implementation theo contract đã kiểm soát.
}
```

**Đoạn minh họa** nằm trong method có `MyHost`, `pluginJar` đã khai báo và `throws Exception` phù hợp. Không copy trần vào một file thiếu class/cấu hình.

### 4.1. Parent-first phù hợp khi nào?

- Host API phải **duy nhất**, không có bản sao trong plugin loader.
- Dữ liệu chuyển qua boundary thuộc các types của parent/host.
- Không có yêu cầu plugin override những class chung của parent.
- Cần loader dễ hiểu và ít nguy cơ shadow implementation nội bộ.

**Nhược điểm:** nếu parent đã có thư viện `com.example.json` phiên bản cũ, plugin muốn private dependency phiên bản khác nhưng **cùng binary name**, parent-first có thể ưu tiên phiên bản của parent. Đây là vấn đề **dependency namespace** cần giải quyết, không chỉ thay ngẫu nhiên thứ tự tìm class.

### 4.2. Child-first có nên dùng?

Một loader tự viết có thể ưu tiên tìm implementation/private dependencies từ plugin trước parent để cô lập nhiều phiên bản. Nhưng nếu áp dụng child-first **cho toàn bộ package**, plugin sẽ nạp bản riêng của host API hoặc thư viện được kỳ vọng phải shared — tạo `ClassCastException`, `LinkageError`, hoặc sai class identity.

Thiết kế thận trọng hơn:

- **Parent-first cố định** cho `java.*` và các API packages thuộc host.
- Chỉ ưu tiên plugin-private packages đã được xác định trong một allowlist rõ.
- Không cho plugin đóng gói và định nghĩa bản sao shared API packages.
- Kiểm tra package sealing, signer consistency, dependencies và lỗi split-package.
- Test với hai plugin cần phiên bản dependency khác nhau.
- Không tự viết child-first loader nếu cấu hình classpath/module layer hoặc namespace relocation đã giải quyết đủ.

**Quan trọng:** JDK chuẩn `URLClassLoader` với parent mặc định không phải một child-first loader. Những đặc tính child-first tùy biến cần code/khung runtime riêng, không được suy từ constructor.

### 4.3. Không chọn null parent để “sandbox”

`new URLClassLoader(urls, null)` không đồng nghĩa môi trường bị cô lập an toàn. Parent `null` mang ý nghĩa delegation tới bootstrap, có thể còn **thiếu các Java platform APIs** ngoài `java.base` và không nhìn thấy shared host contracts.

Nếu code plugin cần các API có thể cho phép, chọn host API loader làm parent. **Class loader isolation không phải security boundary**; nội dung về bảo mật sẽ được phân tích ở phần sau.

## 5. Quy tắc quyền sở hữu cụ thể

Một plugin manager nên có sơ đồ ownership rõ:

```text
Process/JVM (HOST)
  |
  +-- Host API class loader (shared, long-lived)
  |     +-- app.api.Plugin
  |     +-- app.api.PluginContext
  |     +-- app.api.Result
  |
  +-- Plugin Manager (lifecycle owner)
        |
        +-- Plugin Session A@v1
        |     +-- URLClassLoader A1
        |     +-- ServiceLoader/Providers của A1
        |     +-- plugin instance A1
        |     +-- callback registrations / jobs / tasks / data
        |
        +-- Plugin Session B@v3
              +-- URLClassLoader B3
              +-- ServiceLoader/Providers của B3
              +-- plugin instance B3
              +-- callback registrations / jobs / tasks / data
```

**Một session/generation**, không phải chỉ plugin ID, là đơn vị cần quản lý. Khi nâng cấp A từ v1 sang v2, host có thể tạm thời giữ đồng thời **A@v1** và **A@v2** để chuyển traffic hoặc quiesce A@v1 — nhưng phải kết thúc A@v1 và thả reference sau khi chuyển.

### 5.1. Bảng ownership theo sự kiện

| Thành phần | Tạo | Dùng | Dừng/đóng |
| --- | --- | --- | --- |
| Shared `Plugin` API | Host build/deployment | Host + plugin | Theo lifecycle host, không phải khi stop một plugin |
| `URLClassLoader` của A | Host plugin manager | Host discovery/threads của A | Host sau khi A quiesce và không còn load mới |
| `ServiceLoader` của A | Host discovery | Host chọn providers | Host ngừng dùng, bỏ caches/references |
| `Plugin` instance A | ServiceLoader hoặc host factory | Host qua API | Host gọi `close/stop` theo contract của A |
| Executor do plugin A tạo | Plugin A | Tasks A | Plugin A shutdown/await, host giám sát |
| Executor chung của host | Host | Nhiều plugins | Host quản lý, plugin không tự shutdown |
| Listener A đăng ký trên host event bus | Plugin A + host registry | Host events | A hủy registration trước khi unload |
| `ThreadLocal` do A dùng | A hoặc host thread | Threads xử lý A | Cleanup trên chính threads áp dụng, cân nhắc pool boundaries |
| File/socket do A mở | A | A | A đóng đúng scope; host kiểm tra leak |
| Configuration của A | Host cung cấp / A đọc | A | Host quản lý persistence/version; A không xóa tùy tiện |
| Native library/JNI | Thiết kế riêng | Plugin | Unload phức tạp, cần process isolation khi cần |

Nếu một callback của A đang chạy trên executor của host, chỉ gọi `A.close()` là **chưa đủ**: phải ngăn callback mới, chờ callback đang chạy (hoặc cancel đúng contract), hủy đăng ký và bỏ reference.

### 5.2. Không để plugin sở hữu loader riêng mà host không biết

Nếu plugin tùy ý tạo `URLClassLoader` bên trong, rồi giữ reference trong static field hoặc thread, host khó phát hiện và đóng chúng khi disable plugin. Nếu thực sự cho phép plugin tự quản loader con, contract phải yêu cầu plugin báo cáo/đóng loader con và những resource của nó. Mặc định nên để **host lifecycle owner** kiểm soát loader thuộc plugin session.

### 5.3. Plugin không được tự quản quyền truy cập ngoài phạm vi

Việc plugin **định nghĩa classes trong loader riêng** không cấp quyền tự động đọc secrets của host, hoặc được phép đăng ký service tùy ý. PluginContext nên chỉ cung cấp các **capabilities** cần thiết; host vẫn phải thực thi authorization và validate inputs.

**Đừng nhầm API visibility với authorization**: một plugin nhìn thấy interface `SecretStore` không có nghĩa mọi plugin phải được cấp instance chứa credentials của host.

## 6. ServiceLoader: ranh giới discovery theo loader

`java.util.ServiceLoader<S>` là facility tiêu chuẩn để tìm implementations của một interface/service. Với classpath-based plugin, một JAR có thể chứa:

```text
plugin-a.jar
  plugins/GreeterPlugin.class
  plugins/Dependency.class
  META-INF/services/app.api.Greeting
  config/plugin.properties
```

File `META-INF/services/app.api.Greeting` chứa binary name của provider:

```text
plugins.GreeterPlugin
```

Provider trên classpath thường là public class triển khai service và có public no-args constructor. File service-configuration dùng **UTF-8**, tên file là **binary name** của service. Với nested interface, binary name có ký tự `$`; đừng tự thay bằng dấu chấm của canonical nested name.

### 6.1. Chọn loader rõ ràng

```java
ServiceLoader<Greeting> providers =
        ServiceLoader.load(Greeting.class, pluginLoader);
```

**Đoạn minh họa** giả định `Greeting` thuộc host API và `pluginLoader` được tạo bởi host. `ServiceLoader.load(Class, ClassLoader)` tìm provider theo loader chỉ định, tránh phụ thuộc vào TCCL ngẫu nhiên của thread hiện tại.

Nếu dùng:

```java
ServiceLoader<Greeting> providers =
        ServiceLoader.load(Greeting.class);
```

thì overload này lấy **context class loader của current thread**. Trong server thread pool hoặc plugin invocation, context loader có thể không phải loader bạn định dùng; kết quả có thể thiếu provider, lấy provider không mong muốn hoặc giữ loader cũ.

### 6.2. ServiceLoader cũng có vòng đời và cache

`ServiceLoader` nạp providers **lazily** và lưu cache các providers đã được tìm/khởi tạo. `reload()` xóa provider cache để một lần duyệt mới phát hiện lại providers, nhưng:

- `reload()` **không phải** thao tác đóng plugin.
- Không tự đóng `URLClassLoader`.
- Không chấm dứt executors/callbacks.
- Không chứng minh classes đã được unloaded.
- Không bảo đảm ứng dụng đang dùng các provider objects cũ đã thả reference.
- `ServiceLoader` instance **không thread-safe** để dùng chung không đồng bộ giữa nhiều concurrent callers.

Để nâng cấp plugin, thiết kế thông thường là **session mới + loader mới**, chứ không chỉ gọi `reload` trên ServiceLoader cũ rồi hy vọng JVM thay thế class definition đã nạp.

### 6.3. Discovery lỗi có thể phá quá trình nạp

Nếu file `META-INF/services` sai tên, provider không implements API host-owned, thiếu constructor, constructor ném exception hoặc dependencies không phù hợp, `ServiceLoader` có thể ném `ServiceConfigurationError` lúc iteration.

Vì vậy discovery phải nằm trong lifecycle `LOADING` có rollback/cleanup:

```text
CREATE_LOADER
    |
    v
DISCOVER_PROVIDER
    |
    +--- ServiceConfigurationError ---> FAIL_LOAD + cleanup
    |
    v
VALIDATE_METADATA + API_VERSION
    |
    v
START_PLUGIN
```

Không bắt mọi lỗi rồi tiếp tục xem plugin như đã sẵn sàng.

### 6.4. ServiceLoader có thể phát hiện providers từ parent

`ServiceLoader.load(S, pluginLoader)` không có nghĩa “chỉ plugin JAR và tuyệt đối không parent”. Resource/class lookup qua loader có delegation; nếu host classpath cũng công bố cùng service, provider từ parent có thể được tìm thấy. Nếu yêu cầu chỉ chọn provider thuộc A, hãy kiểm tra **plugin ID, artifact provenance, `provider.type().getClassLoader()`**, tên class, metadata và chính sách discovery; không dựa mù quáng vào loader đối số.

## 7. Thread context class loader (TCCL)

Một số thư viện sử dụng:

```java
Thread.currentThread().getContextClassLoader()
```

để tìm service, resources hoặc implementation classes. Host có thể cần **tạm đặt TCCL** bằng plugin loader trong phạm vi gọi plugin để các thư viện đó tìm đúng provider.

Mẫu an toàn:

```java
Thread thread = Thread.currentThread();
ClassLoader old = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    // Gọi code plugin hoặc thư viện dùng TCCL.
    invokePlugin();
} finally {
    thread.setContextClassLoader(old);
}
```

Đây là **mã minh họa không độc lập**, với `pluginLoader` và `invokePlugin` do ứng dụng định nghĩa. Điều thiết yếu là `finally` khôi phục **giá trị chính xác trước đó**, không mặc định đặt về system loader.

### 7.1. Tại sao việc quên restore TCCL nguy hiểm?

Thread pool tái sử dụng workers. Nếu một invocation của A đặt TCCL thành loader A mà không restore, task kế tiếp của B hoặc host có thể:

- Discovery sai provider.
- Resolve resources từ A.
- Vô tình giữ reference tới loader A sau khi A đã disable.
- Tạo threads mới kế thừa một context loader không đúng trong các trường hợp có kế thừa TCCL.
- Khó unload A vì worker còn sống và giữ A trong context loader.

**TCCL là thread state, không phải một biến global dùng an toàn cho mọi request.**

### 7.2. Thread mới do plugin tạo

Nếu plugin tự tạo threads, nó phải quản lý lifecycle. Một `Thread` mới có thể kế thừa context class loader của thread tạo nó; vì thế thread đó có thể giữ plugin loader dù code plugin đã “stop”.

Cần có thread factory và executor policy, đặt tên threads, ghi nhận những tasks còn sống, chặn tạo tasks mới khi stopping và khôi phục/đặt context đúng. Khi shutdown, đảm bảo threads thực sự kết thúc hoặc cancellation được xử lý.

### 7.3. Async invocation cần ownership riêng

Nếu host submit một `Runnable` từ plugin A vào executor chung, **việc restore TCCL của thread submit không tự thay đổi TCCL của worker lúc thực thi**. Host cần wrapper chạy trên worker:

```java
Runnable wrapped = () -> {
    Thread t = Thread.currentThread();
    ClassLoader before = t.getContextClassLoader();
    try {
        t.setContextClassLoader(pluginLoader);
        pluginTask.run();
    } finally {
        t.setContextClassLoader(before);
    }
};
```

Đây là đoạn minh họa, với `pluginLoader` và `pluginTask` đã khai báo. Wrapper nên kết hợp một **in-flight counter/lease**, kiểm tra session còn ACTIVE và xử lý exception/cancellation. Nếu chỉ thay TCCL mà không quản lý scope, host vẫn có thể đóng loader trong khi worker chưa kết thúc.

## 8. ClassLoader.close(): đóng nguồn tài nguyên, không unload class ngay

`URLClassLoader` triển khai `Closeable` và có `close()` (API từ Java 7).

Khi gọi `close()`:

- Loader không còn dùng được để tìm/định nghĩa **classes hoặc resources mới** từ các nguồn mà loader sở hữu.
- Những files/JAR handles do loader mở được đóng theo quy tắc API.
- Classes/resources của **parent** vẫn có thể tìm được qua delegation.
- **Classes đã được nạp** có thể tiếp tục dùng bình thường.
- `close()` **không dừng threads**, không gọi `Plugin.close()` hộ bạn.
- `close()` **không bảo đảm class unloading/GC** ngay lập tức.
- Nếu thread khác đang nạp class **trong lúc close**, kết quả không được định nghĩa chặt; phải quiesce trước.

Do vậy chỉ gọi:

```java
pluginLoader.close();
```

**không đủ** cho việc unload một plugin đang chạy.

### 8.1. Điều kiện để loader có cơ hội được GC

Để plugin loader cũ trở thành **eligible for garbage collection**, cần loại bỏ các strong references đang giữ nó hoặc những Class/instances thuộc nó. Các nguồn giữ rất phổ biến:

- Host static registry giữ `Plugin` instance cũ.
- Callback/listener trên host event bus tham chiếu lambda class thuộc plugin.
- `ServiceLoader` cache giữ providers.
- `Thread`/executor/scheduled task vẫn chạy code plugin.
- `Thread.contextClassLoader` của worker vẫn trỏ tới plugin loader.
- `ThreadLocal` của host worker giữ plugin object/class.
- Java reflection `Method`, `Constructor`, `Class<?>` hoặc `MethodHandle` được cache từ plugin.
- Global cache/logging/metrics/JDBC driver registry có reference đến plugin-specific object.
- Plugin resources chưa được đóng, native libraries/JNI giữ state.
- Future/completion callbacks, queues, timers, reactive subscriptions giữ plugin closure.
- Một `ModuleLayer`/service provider list đang được giữ bởi host.

Không được khẳng định `System.gc()` chắc chắn unload plugin. GC và class unloading là những quyết định runtime; test nên xem **giảm live sessions/resources** và dùng profiling/heap dump khi cần, thay vì assert GC ngay lập tức.

### 8.2. Tại sao thử dùng class sau khi loader đã close lại có thể thành công?

Một class đã được định nghĩa trước `close` vẫn là một `Class<?>` hợp lệ và method đã nạp có thể tiếp tục thực thi. Vì thế ví dụ hoàn chỉnh cố tình **gọi một instance còn sống sau khi hai loader đã đóng** và xác minh nó vẫn trả kết quả.

Điều này không mâu thuẫn với Javadoc: `close` ngừng tìm kiếm classes/resources mới từ loader, **không thu hồi mã đang hiện hữu**. Chính plugin lifecycle mới phải chặn lời gọi mới vào một instance đã stop.

### 8.3. Đừng đóng loader của một plugin khác

Một `URLClassLoader` do host sở hữu có thể là nguồn classes cho nhiều providers trong **cùng một plugin session**. Plugin instance A không được tự đóng loader nếu provider A2 còn dùng nó. Host quản lý scope chứa tất cả providers.

Không tạo một loader mỗi provider nếu bạn thực sự cần các provider trong **một plugin artifact** chia sẻ static state và private types. Đơn vị phân tách thích hợp là **plugin session/generation**, không phải tùy ý một class.

## 9. Vòng đời plugin có thể kiểm chứng

Một state machine mẫu:

```text
DISCOVERED
    |
    v
VALIDATED  -- manifest/checksum/API version/dependencies
    |
    v
LOADING    -- create loader, find providers, initialize state
    |
    v
ACTIVE     -- accept invocations / register callbacks
    |
    v
QUIESCING  -- block new work, signal cancellation, wait in-flight
    |
    v
STOPPED    -- plugin closes its resources, listeners unregistered
    |
    v
CLOSED     -- host closes loader, clears registries/caches
```

Nếu một giai đoạn `VALIDATED` hoặc `LOADING` thất bại, host phải đưa session vào `FAILED`, dọn những resource đã tạo được và không công bố plugin là ACTIVE.

### 9.1. Phân biệt “stop” và “loader close”

- **stop plugin:** thông báo plugin không nhận việc mới, hủy listeners, dừng threads, đóng sockets/files của nó, drain những job đang có theo policy.
- **close loader:** host giải phóng những files/URLs của loader sau khi code không cần load thêm.
- **unload classes:** JVM quyết định khi loader và tất cả các class/instances liên quan không còn reachable; không phải một method trong plugin manager.

Đặt tên state/metrics rõ để không xem `loader.close()==success` đồng nghĩa plugin đã sạch hoàn toàn.

### 9.2. Trình tự dừng an toàn

Một quy trình hợp lý:

1. Atomically chuyển session từ `ACTIVE` sang `QUIESCING`; chặn lời gọi/plugin task mới.
2. Gỡ plugin khỏi registry phục vụ traffic mới; giữ session object đủ lâu để dọn dẹp.
3. Dừng timer/job scheduler; hủy registrations và callbacks ở host event bus.
4. Signal cancel/stop, đợi in-flight invocations và background tasks với **deadline**.
5. Gọi API `plugin.stop()/close()` theo contract; plugin giải phóng resources do nó sở hữu.
6. Hủy registration ở libraries dùng context loader, đóng streams và tài nguyên còn mở.
7. Restore TCCL trên những scope workers mà host điều phối; không để TCCL plugin vĩnh viễn trên pool.
8. Đóng ServiceLoader scope, xóa strong references/caches (ServiceLoader không phải Closeable).
9. Đóng `URLClassLoader` bằng TWR hoặc host-managed `close()`, ghi nhận IOException nếu có.
10. Đưa session ra khỏi map/registry active và phát hành trạng thái CLOSED; theo dõi resources để phát hiện leak.

Không nhất thiết mọi hệ thống có đúng các bước theo cùng thứ tự, nhưng bất biến cần giữ là **không còn hoạt động cần loader mới, không có worker đang load class, không để references giữ plugin không cần thiết** trước khi xem việc dừng đã hoàn tất.

### 9.3. Stop không nên giữ lock global khi chạy plugin code

Plugin `stop()` có thể chậm hoặc callback ngược vào host. Nếu host giữ lock của **toàn bộ plugin registry** trong lúc gọi `stop`, dễ gây deadlock hoặc làm mọi plugin khác đứng chờ.

Nên chuyển trạng thái/gate một cách thread-safe, rồi gọi lifecycle callbacks ngoài critical section và dùng timeout/cancellation. Nếu stop thất bại, báo trạng thái rõ (ví dụ `STOP_FAILED`/`LEAK_SUSPECTED`) thay vì giả vờ CLOSED an toàn.

### 9.4. Một plugin có thể chứa nhiều provider

Nếu artifact của A đăng ký ba service providers, host phải quyết định liệu chúng cùng chia sẻ lifecycle hay có từng provider owner riêng. Với một loader thuộc một plugin generation, host thường chịu trách nhiệm dừng **toàn bộ providers** trước khi đóng loader. Không dùng thành công của một provider.close để kết luận mọi provider đã được dọn.

## 10. Bài demo Java 17: hai loaders, một API, cùng tên plugin

Chương trình hoàn chỉnh **`demo.host.PluginLoaderOwnershipDemo`** minh họa:

1. Host định nghĩa interface `Greeting` **một lần** dưới loader ứng dụng.
2. Host dùng `JavaCompiler` (API tiêu chuẩn JDK) để biên dịch source plugin **trong một thư mục tạm do người chạy truyền vào**.
3. Plugin implementation `plugins.GreeterPlugin` implements **host-owned** `Greeting`.
4. Host tạo **hai `URLClassLoader` khác nhau** (A và B), cùng parent là host loader.
5. Hai loader đều trả **chính một `Greeting.class`**, nhưng `plugins.GreeterPlugin` của A và B có **Class identity khác nhau**.
6. Host loader không nhìn thấy plugin implementation (vì implementation không đặt trên host classpath).
7. `ServiceLoader.load(Greeting.class, loaderA/loaderB)` tìm đúng provider theo từng loader.
8. Host tạm dùng TCCL A để gọi overload `ServiceLoader.load(Greeting.class)`, rồi restore TCCL.
9. Loader A đọc resource nằm riêng trong plugin root.
10. Host gọi `close()` của plugin instance A; plugin từ chối lời gọi `greet` mới.
11. Khi các URLClassLoader đã đóng, instance B đã nạp vẫn có thể chạy — chứng minh **close loader không tự stop code đã nạp**.
12. Biên dịch cả host lẫn provider bằng `--release 17 -Xlint:all -Werror`, không cần thư viện ngoài hay database.

### 10.1. Cấu trúc thư mục được tạo

Host file thuộc package `demo.host`:

```text
temporary-directory/
  demo/host/PluginLoaderOwnershipDemo.java
  demo/host/PluginLoaderOwnershipDemo.class
  demo/host/PluginLoaderOwnershipDemo$Greeting.class
  ...
  plugin-content/
    plugins/GreeterPlugin.java
    plugins/GreeterPlugin.class
    META-INF/services/demo.host.PluginLoaderOwnershipDemo$Greeting
    config/plugin.txt
```

File `META-INF/services/...$Greeting` được tạo từ `Greeting.class.getName()` nên binary name chính xác. **Đây là ví dụ classpath-based**, không dùng `module-info.java`; phần JPMS sẽ được giải thích riêng.

### 10.2. Full code: demo/host/PluginLoaderOwnershipDemo.java

```java
package demo.host;

import java.io.InputStream;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.ServiceLoader;
import javax.tools.JavaCompiler;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class PluginLoaderOwnershipDemo {
    public interface Greeting extends AutoCloseable {
        String greet(String name);
        @Override void close();
    }

    private static void check(boolean ok, String reason) {
        if (!ok) throw new AssertionError(reason);
    }

    private static void compilePlugin(Path root) throws Exception {
        Path source = root.resolve("plugins/GreeterPlugin.java");
        Files.createDirectories(source.getParent());
        String body = """
                package plugins;
                public final class GreeterPlugin
                        implements demo.host.PluginLoaderOwnershipDemo.Greeting {
                    private boolean running = true;
                    public GreeterPlugin() {}
                    @Override public String greet(String name) {
                        if (!running) throw new IllegalStateException("stopped");
                        return "hi " + name;
                    }
                    @Override public void close() {
                        running = false;
                    }
                }
                """;
        Files.writeString(source, body, StandardCharsets.UTF_8);
        Path services = root.resolve("META-INF/services")
                .resolve(Greeting.class.getName());
        Files.createDirectories(services.getParent());
        Files.writeString(services, "plugins.GreeterPlugin\n",
                StandardCharsets.UTF_8);
        Path config = root.resolve("config/plugin.txt");
        Files.createDirectories(config.getParent());
        Files.writeString(config, "plugin-owned", StandardCharsets.UTF_8);

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        check(compiler != null, "Requires full JDK");
        try (StandardJavaFileManager fm = compiler.getStandardFileManager(
                null, Locale.ROOT, StandardCharsets.UTF_8)) {
            var units = fm.getJavaFileObjects(source.toFile());
            var options = List.of("--release", "17", "-encoding", "UTF-8",
                    "-Xlint:all", "-Werror", "-classpath",
                    System.getProperty("java.class.path"),
                    "-d", root.toString());
            boolean compiled = Boolean.TRUE.equals(compiler.getTask(
                    null, fm, null, options, null, units).call());
            check(compiled, "Cannot compile plugin provider");
        }
    }

    public static void main(String[] args) throws Exception {
        check(args.length == 1, "Pass a plugin output directory");
        Path pluginRoot = Path.of(args[0]);
        compilePlugin(pluginRoot);
        System.out.println("plugin compiled = true");

        ClassLoader host = PluginLoaderOwnershipDemo.class.getClassLoader();
        ClassLoader oldContext =
                Thread.currentThread().getContextClassLoader();
        URL url = pluginRoot.toUri().toURL();
        Greeting loadedBeforeClose;

        try (URLClassLoader a =
                     new URLClassLoader(new URL[] {url}, host);
             URLClassLoader b =
                     new URLClassLoader(new URL[] {url}, host)) {
            check(a.loadClass(Greeting.class.getName()) == Greeting.class
                    && b.loadClass(Greeting.class.getName()) == Greeting.class,
                    "API contract must be host-owned");
            System.out.println("shared host contract = true");

            Class<?> ca =
                    Class.forName("plugins.GreeterPlugin", true, a);
            Class<?> cb =
                    Class.forName("plugins.GreeterPlugin", true, b);
            check(ca != cb && ca.getName().equals(cb.getName())
                    && ca.getClassLoader() == a
                    && cb.getClassLoader() == b
                    && !ca.isAssignableFrom(cb), "loader identity");
            System.out.println(
                    "same plugin name has distinct classes = true");

            boolean parentCannotLoad = false;
            try {
                Class.forName("plugins.GreeterPlugin", false, host);
            } catch (ClassNotFoundException expected) {
                parentCannotLoad = true;
            }
            check(parentCannotLoad,
                    "host should not own implementation");
            System.out.println(
                    "parent cannot load implementation = true");

            Greeting ga = ServiceLoader.load(Greeting.class, a)
                    .findFirst().orElseThrow();
            Greeting gb = ServiceLoader.load(Greeting.class, b)
                    .findFirst().orElseThrow();
            check(ga.getClass() == ca && gb.getClass() == cb
                    && "hi Ada".equals(ga.greet("Ada"))
                    && "hi Bob".equals(gb.greet("Bob")),
                    "ServiceLoader provider discovery");
            System.out.println(
                    "ServiceLoader per-loader lookup = PASS");

            try {
                Thread.currentThread().setContextClassLoader(a);
                Greeting viaContext = ServiceLoader.load(Greeting.class)
                        .findFirst().orElseThrow();
                check(viaContext.getClass() == ca,
                        "context loader provider mismatch");
            } finally {
                Thread.currentThread().setContextClassLoader(oldContext);
            }
            check(Thread.currentThread().getContextClassLoader()
                            == oldContext, "TCCL was not restored");
            System.out.println("context loader restored = true");

            try (InputStream data =
                         a.getResourceAsStream("config/plugin.txt")) {
                check(data != null,
                        "plugin resource was not found");
                check("plugin-owned".equals(new String(
                        data.readAllBytes(), StandardCharsets.UTF_8)),
                        "plugin resource mismatch");
            }
            System.out.println("plugin resource read = true");

            ga.close();
            boolean rejected = false;
            try {
                ga.greet("Ada");
            } catch (IllegalStateException expected) {
                rejected = true;
            }
            check(rejected, "plugin stop contract not enforced");
            System.out.println("plugin stop enforced = true");

            loadedBeforeClose = gb;
        } finally {
            Thread.currentThread().setContextClassLoader(oldContext);
        }

        check("hi Bob".equals(loadedBeforeClose.greet("Bob")),
                "loaded class still callable after loader close");
        loadedBeforeClose.close();
        System.out.println(
                "closing loader does not stop loaded code = true");
        System.out.println("checks = PASS");
    }
}
```

### 10.3. Lệnh biên dịch và chạy

Chương trình cần **full JDK 17+** vì sử dụng `ToolProvider.getSystemJavaCompiler()`. Nếu chỉ có runtime image thiếu compiler, nên biên dịch plugin trước như một bước build/deployment, không dynamic compile ở runtime.

Ví dụ với terminal trong thư mục tạm đang dành riêng cho demo:

```bash
javac --release 17 -Xlint:all -Werror -encoding UTF-8 -d . demo/host/PluginLoaderOwnershipDemo.java
java -cp . demo.host.PluginLoaderOwnershipDemo plugin-content
```

Trên Windows/PowerShell, các lệnh `javac` và `java` tương tự; hãy chạy trong thư mục tạm không chứa plugin-content trên **host classpath**. Lệnh `-d .` tạo package directories tương ứng, và chương trình tự biên dịch file plugin vào `plugin-content`.

**Stdout chính xác của lượt chạy thực tế bằng Java 17:**

```text
plugin compiled = true
shared host contract = true
same plugin name has distinct classes = true
parent cannot load implementation = true
ServiceLoader per-loader lookup = PASS
context loader restored = true
plugin resource read = true
plugin stop enforced = true
closing loader does not stop loaded code = true
checks = PASS
```

**Đã thử với** `javac --release 17 -Xlint:all -Werror` cho host và provider; không còn warning, toàn bộ assertions PASS. Chương trình tự ghi source và class của plugin trong thư mục được chỉ định. Để dọn demo, đóng chương trình rồi xóa **chỉ thư mục tạm bạn đã tạo**; không xóa project hoặc thư mục chứa dữ liệu thật.

### 10.4. Vì sao service API dùng nested interface?

`Greeting` là một public nested interface của host class. Host và cả hai plugin loaders cùng dùng chính `Greeting.class` nhờ parent delegation.

Javadoc `ServiceLoader` yêu cầu file cấu hình classpath đặt tên theo **binary name** của service. Nested interface có binary name dạng:

```text
demo.host.PluginLoaderOwnershipDemo$Greeting
```

Dùng `Greeting.class.getName()` tránh nhầm với canonical name có dấu chấm giữa class ngoài và class trong. Không có gì đặc biệt cản việc một plugin implementation class implements nested interface public.

Trong sản phẩm lớn, nên tách `Greeting` thành `app.api.Greeting` trong một API artifact rõ ràng thay vì nested interface trong main class.

### 10.5. Vì sao hai loader cùng classpath nhưng khác Class identity?

Chúng có **hai instances URLClassLoader**. Mỗi loader tự định nghĩa `plugins.GreeterPlugin` từ `plugin-content`; `Class.forName(...,true,a)` và `Class.forName(...,true,b)` trả hai `Class<?>` khác nhau dù binary name giống nhau.

Đó là minh họa trực tiếp cho việc cùng một plugin artifact có thể có **hai generations độc lập**, nhưng chúng vẫn chia sẻ host API.

### 10.6. Vì sao plugin instance B còn gọi được sau loader.close?

Vì loader close **không unload class đã được JVM định nghĩa**. Đây là behavior quan trọng cần nhận thức để thiết kế lifecycle.

Trong demo, B còn reference ở biến `loadedBeforeClose` nên class/instance vẫn sống; đó là **chủ đích để chứng minh giới hạn**. Production muốn unload A/B phải **ngừng chấp nhận lời gọi mới, stop instances, bỏ references**, không chỉ close URLClassLoader.

### 10.7. Vì sao plugin provider phải có public constructor?

Ở classpath service configuration, một provider phải có public no-args constructor và implements shared service. Class `GreeterPlugin` trong demo đáp ứng điều đó. `ServiceLoader` instantiates lazily, không chạy constructor ngay khi host chỉ tạo một URLClassLoader.

Không tự nhận mọi plugin JAR đều an toàn chỉ vì ServiceLoader tìm ra một provider đúng type: constructor/static initializer cũng là **arbitrary executable code**, phải nằm trong trust model phù hợp.

### 10.8. Vì sao try-with-resources chỉ cho URLClassLoader?

`URLClassLoader` có `close()`, nên host dùng TWR. `ServiceLoader` **không phải AutoCloseable**; nó giữ cache providers và cần **thả references**, không tự gọi `close()` lên ServiceLoader.

Trong bài, provider có `Greeting extends AutoCloseable` và host gọi `ga.close()`/`loadedBeforeClose.close()` riêng. Đây là hai lifecycle distinct: plugin instance stop trước, loader close giải phóng JAR handles.

### 10.9. Độ tin cậy của stdout

Chương trình dùng các invariant không phụ thuộc thời gian hoặc scheduling:

- Cùng parent nghĩa cùng API class.
- Hai defining loaders riêng tạo class identities khác nhau.
- ServiceLoader được truyền loader tường minh.
- TCCL được đặt rồi restore trong finally.
- Resource và plugin instance có lifecycle rõ.
- Việc close loader không tự hủy object đã nạp.

Không có việc giả định class unloading hoàn thành hoặc `System.gc()` đồng bộ với code. Demo còn **cố ý** không sử dụng API quản lý security cũ.

## 11. Hot reload và nâng cấp plugin không ảnh hưởng các plugin khác

Để cập nhật plugin A từ v1 lên v2, cần xem mỗi bản là một **generation/session mới**.

Một chiến lược an toàn:

```text
ACTIVE(A@v1)
       |
       +-- tải A@v2 bằng loader mới
       |     |
       |     +-- validate artifact, ABI, dependencies
       |     +-- create loader A2, discover, start
       |
       +-- atomic switch routing A -> A2
       |
       +-- A1 QUIESCING: stop accepting calls
       +-- await callbacks/tasks or cancel with deadline
       +-- A1.stop / close resources
       +-- remove A1 from registries / provider caches
       +-- URLClassLoader A1.close
       +-- drop strong references to A1
```

Không ghi đè `plugin-a.jar` đang được loader A1 sử dụng rồi kỳ vọng JVM thay thế class definition trong loader đó. Class đã được định nghĩa không tự động biến thành implementation mới khi file nguồn thay đổi.

### 11.1. Hot reload cần quản lý chuyển trạng thái nguyên tử

Nếu thread T1 vừa lấy provider A1 khỏi registry, còn host T2 đã thay routing sang A2 và bắt đầu đóng loader A1, T1 vẫn có thể sắp gọi A1. Vì vậy **chỉ thay map entry không đủ**.

Dùng cơ chế session **lease/in-flight counter**, reference-holding scope hoặc synchronized state gate:

- Caller lấy **lease** khi session còn ACTIVE.
- Switch routing khiến caller mới chỉ lấy A2.
- Host chờ A1 có **in-flight == 0** trước khi đóng.
- Timeout dẫn đến policy cancel/force stop rõ, không âm thầm tiếp tục.

### 11.2. ABI versioning

Các câu hỏi cần trả lời:

- Plugin khai báo hỗ trợ API host version nào?
- Host giữ compatibility ra sao khi thêm method vào interface?
- DTO/schema có giữ backward compatibility không?
- Plugin có thể yêu cầu minimum Java version nào?
- Dependency graph của plugin có trùng package với host API không?
- Metadata/plugin ID và code signatures có được xác minh không?

Một `NoSuchMethodError` hoặc `AbstractMethodError` khi nạp plugin có thể chỉ ra mismatch ABI giữa plugin và host. Không coi đó là lỗi nghiệp vụ bình thường có thể retry vô hạn.

### 11.3. Không cho version mới thay đổi state chung không có protocol

Một plugin v2 có thể cần migration data riêng. Loader ownership không tạo transaction giữa plugin state v1/v2. Hãy version config/state storage, có bước migration và rollback deployment nếu không tương thích.

Nếu đang có jobs chưa xử lý ở v1, chính sách phải quy định drain, cancel, requeue hay chuyển trạng thái. Không đóng loader v1 trong khi những jobs đó vẫn mang reference tới class/private DTO v1.

## 12. Class loader leaks: những điểm cần điều tra

Một plugin có thể đã đóng URLClassLoader mà vẫn rò bộ nhớ nếu những references còn tồn tại. Ma trận:

| Đường giữ reference | Vì sao giữ loader | Cleanup cần làm |
| --- | --- | --- |
| Host map `pluginId -> instance` | Instance class định nghĩa bởi loader plugin | Xóa entry sau quiesce |
| `ServiceLoader` cache | Cache provider instances | Thả ServiceLoader và providers cũ |
| Event bus listener | Listener lambda/class của plugin | Unregister listener |
| `ScheduledExecutorService` | Scheduled tasks giữ Runnable plugin | Cancel futures, shutdown/await executor |
| Host worker TCCL | Thread giữ ClassLoader reference | Restore sau mọi plugin call |
| `ThreadLocal` | Worker sống lâu giữ plugin object | Remove trên đúng execution context |
| Static cache host | Class/Method/MethodHandle/annotation plugin cached | Xóa cache theo plugin generation |
| Plugin-created thread | Stack/execution object giữ plugin classes | Signal stop, join với deadline |
| JDBC driver registry | Driver/plugin instance có thể bị host/global registry giữ | Deregister theo provider contract/ownership |
| Logging/metrics registry | Appenders, gauges, filters, callbacks giữ class plugin | Unregister/close |
| Java NIO WatchService / file channels | Native/file resource còn mở | Close resources do plugin tạo |
| Native/JNI libraries | State may be process-scoped | Cẩn trọng: có thể cần process per plugin |
| Reactive subscription | Captured callback/observer | Cancel/unsubscribe |
| Loaded Class/Method reflection refs | Host giữ `Class<?>`/`Method` | Không cache ngoài session lifetime |
| ModuleLayer/plugin provider registry | Layer/caches giữ modules và classes | Xóa session-specific refs |

### 12.1. Cách kiểm thử leak đúng

Một test nên:

1. Nạp plugin N lần qua N loaders/generations.
2. Với mỗi phiên, thực hiện `start → stop → close`.
3. Assert không còn active jobs/listeners/registrations và file handles không bị giữ.
4. Theo dõi heap/classloader statistics **sau quiescence**, dùng profiler hoặc Java Flight Recorder/heap dump nếu cần.
5. Không assert `System.gc()` chắc chắn chạy và unload ngay.
6. Bảo đảm chính **test harness** không giữ plugin instance/Class/ServiceLoader strong references quá lâu.

`WeakReference<ClassLoader>` có thể dùng làm **tín hiệu hỗ trợ chẩn đoán**, nhưng không nên biến thời gian GC thành hợp đồng deterministic của production.

### 12.2. Memory leak không chỉ là heap size

Plugin thread bị kẹt còn có thể giữ network sockets, file descriptors hoặc CPU; URLClassLoader.close giải phóng một số JAR file handles **không thay thế đóng** mọi resource plugin mở. Test cần theo dõi thread count, scheduled jobs, opened files, registry size và provider references.

## 13. JPMS ModuleLayer: lựa chọn hiện đại khác với classpath loader

Từ **Java 9**, JPMS hỗ trợ named modules và `ModuleLayer`. Nếu plugin được triển khai như **named modules**, host có thể tạo layer riêng và tìm service providers theo module configuration.

API liên quan:

- `ModuleFinder.of(paths...)` tìm module descriptors.
- `Configuration.resolve(...)` giải graph dependency.
- `ModuleLayer.defineModulesWithOneLoader(...)` tạo loader chung cho modules trong layer.
- `ModuleLayer.defineModulesWithManyLoaders(...)` tạo loader riêng cho mỗi module trong layer.
- `ServiceLoader.load(layer, ServiceType.class)` tìm providers trong một layer/ancestors.
- `module-info.java` dùng `exports`, `requires`, `uses`, `provides ... with ...`.

Ví dụ sơ đồ module concept:

```text
host.api module
    exports app.api

plugin.alpha module
    requires host.api
    provides app.api.Plugin with plugins.alpha.AlphaPlugin

host runtime
    uses app.api.Plugin
    discovers providers via ModuleLayer
```

Đây là **sơ đồ**, không phải một module-info.java hoàn chỉnh có thể biên dịch một mình.

### 13.1. Vì sao cân nhắc ModuleLayer?

- Graph dependencies được resolve theo named modules.
- Exports/opens làm rõ module encapsulation.
- `uses/provides` là cách khai báo service provider trong named modules.
- Host có thể xây layer và loader topology theo các modules liên quan.
- Có thể phù hợp với hệ thống plugin có graph/module boundaries rõ và cần hỗ trợ nhiều modules.

Nhưng JPMS **không tự trở thành sandbox cho untrusted code**. Module boundaries chủ yếu về visibility/encapsulation, không thay OS process isolation hoặc authorization.

### 13.2. Không trộn công thức classpath và module path

Với classpath plugin, `META-INF/services/<binaryName>` là cơ chế chuẩn. Với named module provider, service declaration chính nằm ở `module-info.java`; discovery theo `ServiceLoader.load(layer,service)` và module graph.

Tài nguyên trong named module còn chịu các quy tắc `exports/opens` và resource lookup. Không giả định mọi `ClassLoader.getResource` trong JPMS có cùng visibility với classpath JAR.

### 13.3. ModuleLayer không có close() cho toàn layer

`ModuleLayer` không phải `AutoCloseable` theo nghĩa một URLClassLoader của classpath. Nếu cần unload/reload, vẫn phải quản lý sessions, strong references, tasks và resource ownership. Phải tách **module graph lifetime**, loader instances và plugin instances — không tìm một phép `layer.close()` tự xử lý mọi thứ.

## 14. Bảo mật: loader riêng không phải sandbox

Đây là cảnh báo quan trọng về **nạp lớp an toàn**.

Một `URLClassLoader` riêng chủ yếu phân tách **class namespace và visibility theo delegation**. Nó **không tự ngăn** plugin thực hiện filesystem I/O, network requests, reflection trong phạm vi được phép hay tạo threads khi code đó chạy trong JVM host.

Đặc biệt, **Security Manager đã bị vô hiệu hóa vĩnh viễn từ JDK 24**; không nên thiết kế plugin sandbox mới phụ thuộc vào `SecurityManager`, policy files, `System.setSecurityManager` hoặc `AccessController.doPrivileged` theo những mẫu legacy. Không hứa plugin sẽ bị hạn chế quyền chỉ vì dùng `URLClassLoader` hay `ModuleLayer`.

### 14.1. Với plugin tin cậy

Nếu plugin được phát hành bởi chính nhóm phát triển hoặc nhà cung cấp đáng tin, chạy in-process có thể hợp lý:

- Chỉ chấp nhận artifact đã được ký/đối chiếu checksum đáng tin.
- Có allowlist publisher, plugin ID, phiên bản API.
- Kiểm tra dependency provenance, SBOM và vulnerability policies.
- Chỉ cấp capability host cần thiết.
- Quản lý lifecycle, timeouts và resource budgets.
- Có rollback plugin version và audit trail.

Những biện pháp này **giảm rủi ro** chứ không biến plugin thành sandbox hoàn toàn.

### 14.2. Với plugin chưa tin cậy

Nếu người dùng bất kỳ có thể tải code JVM lên và host cần chống file/network access hoặc memory/CPU abuse, **không chạy trực tiếp trong host JVM chỉ dựa vào ClassLoader**.

Thay vào đó cân nhắc:

- **Process riêng** cho plugin với account/permissions tối thiểu.
- Container/OS sandbox có filesystem/network/resource isolation phù hợp.
- IPC/API contract rõ (gRPC/HTTP/queues), validate input và output.
- CPU/memory/time limits, cancellation và kill process policy.
- Secrets không xuất hiện trong process của plugin nếu không cần.
- Theo dõi crash isolation; plugin process chết không kéo host JVM chết.

Một plugin có thể khiến JVM chết qua `System.exit`/native code hoặc chiếm resources; tách process là một biên giới mạnh hơn so với child class loader.

### 14.3. Artifact validation xảy ra trước class initialization

`Class.forName(name,true,loader)` có thể kích hoạt class initialization. `ServiceLoader` có thể chạy provider constructor khi iterate. Do đó **validate artifact/trust/API metadata trước khi kích hoạt code**; đừng xem tìm thấy tên class là một bước hoàn toàn không có side effects.

Trong demo, `Class.forName(..., true, a)` cố ý initialize provider, nhưng demo chỉ dùng nguồn plugin tự tạo và chạy trong thư mục tạm do host kiểm soát. Không biến mã này thành công cụ nạp plugin không tin cậy trực tiếp.

## 15. Testing plan cho một plugin manager production

| Nhóm kiểm thử | Thiết lập | Assertion |
| --- | --- | --- |
| API identity | Một shared API, hai plugin loaders | `child.loadClass(API)==API.class` |
| Implementation identity | Hai loaders cùng nạp một binary name | `ClassA != ClassB` |
| Sibling isolation | Plugin A/B classes ở roots riêng | B không tự resolve private class A |
| Provider discovery | `META-INF/services` hợp lệ | `ServiceLoader.load(API,loaderA)` thấy provider A |
| Malformed service file | Sai provider name/constructor | `ServiceConfigurationError` và cleanup |
| Resource lookup | Resource riêng của A | A đọc đúng resource, B không lấy nhầm nếu policy cần isolation |
| TCCL restore | Scoped invocation bị lỗi hoặc thành công | Worker TCCL trở về giá trị trước |
| Thread pool reuse | Chạy A rồi B trên một worker | B không còn context loader A |
| Close lifecycle | Stop rồi loader close | Không nhận new work, files/streams giải phóng |
| Already-loaded code | Giữ instance sau loader close | Có thể chạy; không xem close là stop |
| Hot reload | Nạp v1 và v2 bằng loaders khác nhau | Traffic switch, in-flight drained, version đúng |
| Shared dependencies | API/DTO parent-owned | Không ClassCast/LinkageError do duplicate ABI |
| Conflicting private libs | A/B cần versions khác | Thiết kế class lookup không vô tình dùng một version |
| Cache cleanup | Listener, service cache, method handle registry | Không còn references tới generation cũ |
| Module compatibility | Named modules + ModuleLayer | Dependency graph exports/uses/provides đúng |
| Trust boundary | Plugin artifact không tin cậy | Process isolation hoặc policy phù hợp, không ClassLoader sandbox |
| Java version mismatch | Plugin compile JDK mới hơn runtime | Báo `UnsupportedClassVersionError` rõ, không retry |
| Permission/code errors | Plugin static initializer/constructor ném | Không publish plugin ACTIVE |
| Concurrent unload | Invocation đang chạy | Quiesce + lease/deadline trước close |
| Runtime metrics | Nạp và stop nhiều lần | Thread/job/registration counts quay về baseline |

### 15.1. Unit test và integration test khác nhau

**Unit test** có thể dùng một `URLClassLoader` chứa class files nhỏ và test `Class` identity, SPI providers, TCCL, state machine.

**Integration test** phải dùng plugin JAR thật trong môi trường giống production với:

- Dependencies và Class-Path manifest thực tế.
- Mở/đóng file JAR trên Windows/Linux.
- Logging framework, scheduled jobs, JDBC drivers nếu plugin dùng.
- Runtime module access/JDK versions.
- Concurrency giữa load/unload và traffic.
- Memory profiling sau nhiều generations.
- Phân loại errors cho vận hành: `ClassNotFoundException`, `NoClassDefFoundError`, `ServiceConfigurationError`, `LinkageError`, `UnsupportedClassVersionError`, `IllegalAccessError`, `ExceptionInInitializerError`.

Không cố viết một unit test luôn PASS rồi kết luận mọi dependency version có thể isolate đúng; lỗi integration classpath/module graph cần được test riêng.

### 15.2. Những assertion nên tránh

- “Sau `close()`, mọi instance đã nạp phải ném lỗi.” **Sai.**
- “Sau `System.gc()`, class loader chắc chắn biến mất ngay.” **Sai.**
- “Hai class cùng binary name thì cast được.” **Sai nếu defining loaders khác nhau.**
- “Một ServiceLoader reload đủ để hot swap code đã nạp.” **Sai.**
- “Một ClassLoader riêng ngăn plugin truy cập dữ liệu nhạy cảm.” **Không phải sandbox.**
- “TCCL là thuộc tính của request nên tự restore.” **Sai; đây là state của thread.**
- “`ClassLoader.close` luôn được gọi tự động khi provider.close.” **Không có quan hệ đó.**
- “Parent-first đảm bảo mọi private dependency plugin độc lập.” **Không khi parent đã định nghĩa cùng binary name.**
- “Named module luôn unload cùng ModuleLayer object.” **Không có cam kết như vậy.**

## 16. Các lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Đưa host API vào cả host và child-first plugin | Duplicate class identity, `ClassCastException` | Shared API parent-owned |
| Một loader toàn cục nạp tất cả plugins | Dependency collisions, khó unload riêng | Một loader/session hoặc layer theo nhu cầu |
| Mỗi provider một loader dù cùng plugin cần share state | Class identity và static state bị tách không mong muốn | Dùng một plugin generation loader hợp lý |
| Xem `URLClassLoader.close` là unload tức thời | Threads/classes vẫn hoạt động | Lifecycle stop + drop refs |
| Để plugin tự đóng parent loader | Hỏng host và plugins khác | Host sở hữu loader lifetime |
| Không gọi plugin.stop khi đóng loader | Tasks/callbacks tiếp tục chạy | Quiesce và stop trước close |
| Quên unregister event listener | Host registry giữ plugin class | Unregister bằng token/handle |
| Quên restore TCCL | Plugin loader bị giữ bởi thread pool | try/finally quanh invocation |
| Dùng `ServiceLoader.load(S)` trên worker bất kỳ | Discovery phụ thuộc TCCL ngẫu nhiên | `load(S,explicitLoader)` khi biết loader |
| Dùng ServiceLoader như thread-safe registry | Races/caches bất ngờ | Chỉ dùng theo contract và bảo vệ concurrency |
| Tưởng `ServiceLoader.reload` đóng providers | Provider/loader refs còn sống | Stop/close/drop refs riêng |
| Đưa plugin type vào global cache host | Class loader memory leak | Cache per-generation và cleanup |
| Giữ static singleton ở parent trỏ plugin | Loader cũ không collectible | Release references |
| Chọn parent null để sandbox | Không bảo đảm API visibility/security | Chọn parent API + process security |
| Dùng child-first không giới hạn | Duplicate API/JDK libs, linkage errors | Parent-first với allowlist rõ |
| Không kiểm soát plugin ID/version | Hot reload dùng nhầm generation | Session key gắn version/generation |
| Đóng loader khi thread khác đang load | Undefined load result | Quiesce + in-flight wait |
| Chỉ đo heap, không đo threads/files | Leak ngoài heap | Track all resources |
| `System.gc` trong test bắt buộc | Test flaky, noncontractual | Leak profiling, resource invariants |
| Chạy arbitrary plugin trong JVM và tin loader cách ly | Security exposure | Process/container sandbox |
| Dùng SecurityManager làm sandbox mới | API bị vô hiệu hóa JDK 24+ | OS/process isolation |
| Thả loader nhưng giữ ServiceLoader providers | Provider cache vẫn giữ refs | Clear registries/strong refs |
| Nạp plugin từ URL không kiểm tra | Supply-chain/network risk | Validate artifact/signature/hash |
| Nhầm module encapsulation với sandbox | Không giới hạn mọi I/O/quyền process | Authorization và OS isolation |
| Dùng private classes plugin trong DTO host | ABI coupling, reload khó | Shared DTO hoặc neutral serialization |
| Không test hai phiên bản cùng lúc | Version collisions không được phát hiện | Multi-generation tests |
| Không rollback khi ServiceLoader lỗi | Half-loaded session | Fail-load cleanup |
| Không hủy futures khi stop | Callback giữ loader | Cancel/drain futures |
| Không giới hạn plugin constructor/start | Load hang, startup blocked | Timeouts/policy; untrusted needs process isolation |

## 17. Bài tập tự luyện có đáp án

### Bài 1 — Ai sở hữu Plugin API?

Một plugin implements `app.api.Plugin`. Interface này nên được nạp bởi host loader hay loader của từng plugin?

**Đáp án:** Nên là **host/shared API loader**. Nếu mỗi plugin tự định nghĩa bản copy API, host và plugin có thể có hai class identities khác nhau.

### Bài 2 — Class identity

Hai loader A và B đều nạp `plugins.X` từ cùng file JAR. `A.loadClass("plugins.X")==B.loadClass("plugins.X")` có nhất thiết true?

**Đáp án:** Không. Nếu A và B tự định nghĩa class đó, chúng là các `Class<?>` khác nhau dù binary name giống nhau.

### Bài 3 — Cùng API

Vì sao instance từ loader A và B vẫn có thể cast thành `app.api.Plugin` của host?

**Đáp án:** Vì cả hai loader **delegate host API** về cùng parent `Class<?>`, nên cùng implements đúng runtime interface identity.

### Bài 4 — Parent-first

Với `new URLClassLoader(urls,hostLoader)`, khi parent đã có class cần nạp, class nào được ưu tiên?

**Đáp án:** Parent-first theo mặc định. Child chỉ tự tìm khi parent không giải quyết được request.

### Bài 5 — Parent null

`URLClassLoader(urls,null)` có phải sandbox giới hạn I/O an toàn không?

**Đáp án:** Không. Nó thay topology delegation và có thể làm mất visibility của platform/host API, không tạo OS security boundary.

### Bài 6 — Private dependencies

Plugin A và B cần hai phiên bản khác nhau của cùng dependency. Dùng một loader chung cho cả hai có tốt không?

**Đáp án:** Thường không. Dùng generation-scoped loaders và kiểm soát dependency lookup, hoặc module/classpath design phù hợp.

### Bài 7 — Child-first

Vì sao không nên child-first mọi package?

**Đáp án:** Plugin có thể định nghĩa duplicate shared API và dependencies của host, gây incompatible class identities và linkage errors. Parent-first cho host API, child-first có chọn lọc khi thật cần.

### Bài 8 — ServiceLoader

Host có plugin loader A. Nên dùng `ServiceLoader.load(Api.class,A)` hay overload không loader nếu cần discovery chắc chắn từ A?

**Đáp án:** Ưu tiên overload truyền **explicit loader**. Overload một tham số dùng TCCL của thread đang chạy.

### Bài 9 — Service file

Với nested interface `com.example.Host$Plugin`, tên resource SPI trên classpath phải theo canonical name hay binary name?

**Đáp án:** Binary name: `META-INF/services/com.example.Host$Plugin`.

### Bài 10 — reload

Gọi `ServiceLoader.reload()` có unload classes/đóng instance/URLClassLoader cũ không?

**Đáp án:** Không. Nó xóa provider cache của ServiceLoader, không làm lifecycle cleanup.

### Bài 11 — TCCL

Vì sao phải restore TCCL trong `finally`?

**Đáp án:** Worker threads được tái sử dụng; nếu không restore, task khác có thể dùng provider/loader sai và giữ plugin loader cũ sống lâu.

### Bài 12 — Plugin threads

Một plugin tạo executor và không shutdown khi stop. Hậu quả?

**Đáp án:** Threads/tasks có thể tiếp tục chạy, giữ references tới plugin classes/loader và tiêu thụ resources. Plugin owner phải shutdown/cancel/await theo deadline.

### Bài 13 — Loader close

`URLClassLoader.close()` có tự ngăn các method của class đã loaded tiếp tục chạy không?

**Đáp án:** Không. Class/instance đã nạp vẫn có thể dùng được.

### Bài 14 — GC

Host đóng loader và gọi `System.gc()`. Có bảo đảm class đã unloaded?

**Đáp án:** Không. Cần hết reachable references và GC class unloading phụ thuộc runtime; không có guarantee synchronous.

### Bài 15 — Resource stream

Plugin loader mở resource từ JAR. Ai nên đảm bảo stream đã đọc xong được close?

**Đáp án:** Code mở stream phải dùng TWR/close đúng scope. Host còn phải đóng loader khi plugin session kết thúc.

### Bài 16 — Event bus

Plugin A đăng ký listener lên host bus, sau đó host đóng loader A nhưng không unregister listener. Điều gì xảy ra?

**Đáp án:** Registry còn giữ listener/object class của A, có thể leak loader và tiếp tục gọi plugin đã disable. Cần unregister.

### Bài 17 — MethodHandle cache

Host cache `MethodHandle` tới một plugin method ở static field. Có thể làm loader cũ không collectible không?

**Đáp án:** Có. MethodHandle có thể giữ target classes/objects. Cần cache per-generation và xóa khi session ngừng.

### Bài 18 — Reload

Host vừa thay routing A@v1 sang A@v2. Được close A@v1 ngay dù có invocation đang chạy không?

**Đáp án:** Không an toàn. Cần in-flight tracking/lease, quiesce, stop rồi close theo protocol.

### Bài 19 — ServiceLoader errors

Provider class không implements shared API hoặc constructor ném lỗi. Cơ chế discovery có thể phát sinh lỗi gì?

**Đáp án:** `ServiceConfigurationError`. Loader session phải đánh dấu FAILED và cleanup.

### Bài 20 — Security

Nếu plugin là code do người dùng bất kỳ upload, chỉ dùng loader riêng có đủ để ngăn file/network access không?

**Đáp án:** Không. Phải thiết kế process/OS/container isolation và giới hạn capabilities.

### Bài 21 — JDK hiện đại

Có nên thiết kế sandbox plugin mới dựa trên `SecurityManager` cho JDK 24+ không?

**Đáp án:** Không. Nó đã bị vô hiệu hóa vĩnh viễn. Cần cơ chế cách ly ngoài JVM.

### Bài 22 — ModuleLayer

`ModuleLayer` có thể dùng trong plugin system từ phiên bản Java nào?

**Đáp án:** Java 9+; dùng module graph, `ModuleFinder`, `Configuration`, `ServiceLoader.load(layer,service)` tùy kiến trúc.

### Bài 23 — Named module provider

Service provider của named module nên khai báo bằng gì?

**Đáp án:** `provides ... with ...` trong `module-info.java`, và consumer thường có `uses ...`. Không đơn giản áp dụng nguyên classpath discovery trong mọi tình huống.

### Bài 24 — Ownership của Connection

Plugin mượn connection từ host-owned pool. Plugin có được shutdown cả pool khi stop không?

**Đáp án:** Không. Nó phải trả/đóng **logical connection nó mượn** theo contract, không đóng tài nguyên quản lý chung do host sở hữu.

### Bài 25 — API DTO

Vì sao không trả thẳng `plugins.PrivateCustomer` ra host API?

**Đáp án:** Host sẽ phụ thuộc vào type do plugin loader định nghĩa, làm reload/ABI khó và giữ loader. Chuyển qua shared DTO/neutral representation.

### Bài 26 — TCCL và async

Host đặt TCCL trong thread submit rồi submit runnable vào pool. Có bảo đảm task trên worker tự có TCCL đúng không?

**Đáp án:** Không. Worker có TCCL riêng; nếu cần đặt context, wrap execution trên worker và restore trong finally.

### Bài 27 — ServiceLoader cache

Host giữ `ServiceLoader` instance ở static field sau khi unload plugin. Có ảnh hưởng gì?

**Đáp án:** Cache có thể giữ providers và class loader references; phải quản lý lifetime của ServiceLoader theo session.

### Bài 28 — Duplicate dependency class

Parent loader đã có `lib.Json` v1, plugin có `lib.Json` v2. Với parent-first, plugin dùng bản nào nếu parent resolve được `lib.Json`?

**Đáp án:** Bản parent. Nếu plugin cần v2, phải điều chỉnh topology/namespace theo thiết kế, không tự tin rằng URLClassLoader đã isolate mọi dependency.

### Bài 29 — Load failure cleanup

`ServiceLoader` ném lỗi trong LOADING sau khi một resource mở thành công. Có nên công bố plugin ACTIVE rồi hy vọng lỗi biến mất?

**Đáp án:** Không. Đưa vào trạng thái FAILED, đóng tài nguyên/loader đã tạo và báo lỗi rõ.

### Bài 30 — Tên class để debug

Chỉ log `type.getName()` có đủ để phân biệt hai class cùng tên dưới A và B không?

**Đáp án:** Không. Log defining `ClassLoader`, origin/generation/plugin ID và class identity.

## 18. Checklist triển khai

- [ ] Đã xác định **host** là owner của plugin manager và loader lifecycle.
- [ ] Đã tách rõ shared API/SPI thành artifact/module do host quản trị.
- [ ] Các kiểu DTO/exception/event qua biên giới thuộc shared contract.
- [ ] Không đóng gói bản copy host API trong plugin-private loader.
- [ ] Đã có plugin ID, version và generation/session identity.
- [ ] Quyết định một loader/layer cho đơn vị plugin thích hợp.
- [ ] Mặc định parent-first cho host API, tránh child-first toàn cục.
- [ ] Có chính sách dependency versions/collision và test nhiều plugins.
- [ ] Hiểu class identity gồm binary name **và defining loader**.
- [ ] Không nhầm requesting loader với defining loader.
- [ ] Dùng `ServiceLoader.load(service, explicitLoader)` khi biết scope.
- [ ] Nếu dùng SPI classpath, tạo `META-INF/services/<binaryName>` UTF-8 đúng.
- [ ] Không dựa vào `ServiceLoader.reload` như lifecycle stop/unload.
- [ ] Không dùng một ServiceLoader instance đa thread không đồng bộ.
- [ ] Quản lý discovery error `ServiceConfigurationError`, rollback LOADING.
- [ ] TCCL được đặt theo scope và **restore trong finally**.
- [ ] Async callback/worker có wrapper context và lease nếu cần.
- [ ] Plugin stop chặn jobs mới, drain/cancel in-flight với deadline.
- [ ] Gọi plugin `stop/close` trước khi host đóng loader.
- [ ] Unregister listeners, callbacks, metrics, subscriptions và caches.
- [ ] Shutdown executors/threads đúng quyền sở hữu.
- [ ] Cleanup ThreadLocal và các reference giữ class/plugin instance.
- [ ] Host đóng `URLClassLoader` sau khi quiesce.
- [ ] Không xem `close` là class unloading/GC bảo đảm.
- [ ] Không đợi `System.gc()` như synchronization mechanism.
- [ ] Chỉ công bố session CLOSED khi lifecycle/cleanup đã được kiểm chứng.
- [ ] Thiết kế hot reload bằng **new generation loader**, không ghi đè bytecode đã nạp.
- [ ] Không trộn private plugin types với global host caches.
- [ ] Có API version compatibility check và metadata/provenance.
- [ ] Nếu dùng JPMS, phân biệt classpath ServiceLoader với named module providers.
- [ ] Không coi ClassLoader/ModuleLayer là sandbox bảo mật.
- [ ] Không dùng SecurityManager làm giải pháp sandbox JDK 24+.
- [ ] Với plugin chưa tin cậy, có OS/process/container isolation.
- [ ] Giới hạn quyền và capabilities plugin nhận từ host.
- [ ] Test class identity, ServiceLoader, TCCL, stop, close và reload.
- [ ] Test leak resources, threads, file handles và registry references.
- [ ] Dùng JDK 17+ để compile/test ví dụ chính, không dùng API deprecated.

## 19. Tài liệu tham khảo chính thức

- [Java SE 25 — ClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, class/resource resolution, `getParent()` và các custom loaders.
- [Java SE 25 — URLClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLClassLoader.html): parent-first constructor, `close()`, tài nguyên, behavior với classes đã nạp.
- [Java SE 25 — ServiceLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): classpath `META-INF/services`, providers, TCCL overload, explicit loader, cache, `reload()` và errors.
- [Java SE 25 — Thread](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): `getContextClassLoader()`, `setContextClassLoader()`.
- [Java SE 25 — ModuleLayer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ModuleLayer.html): named modules, loader topology và module layers.
- [Java SE 25 — ModuleFinder](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/module/ModuleFinder.html): tìm named module artifacts.
- [Oracle JDK 24 — Security Manager permanently disabled](https://docs.oracle.com/en/java/javase/24/security/security-manager-is-permanently-disabled.html): lý do không dựa vào SecurityManager cho kiến trúc plugin mới.
- [Java SE 17 — JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html): compiler API tiêu chuẩn được dùng trong demo.
- [Java SE 17 — Method Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getClassLoader()` và runtime class identity.

## 20. Kết luận

Quyền sở hữu loader là yếu tố trung tâm của một kiến trúc plugin có thể mở rộng và nâng cấp an toàn.

**Host nên sở hữu shared API và quyết định vòng đời loader; mỗi plugin generation có một loader/layer rõ ràng sở hữu implementation và dependencies cần cô lập; plugin instance chịu trách nhiệm giải phóng resources do nó tạo.** Parent-first delegation giữ class identity của contract chung, còn các triển khai plugin có thể riêng biệt dù trùng binary name.

`ServiceLoader` và TCCL giúp discovery, nhưng cũng là những nguồn reference cần dọn sau unload. `URLClassLoader.close()` đóng nguồn file và chặn nạp mới từ loader, **không hủy classes đã nạp, không stop threads và không bảo đảm class unloading**. Muốn hot reload đúng, phải tạo generation mới, quiesce generation cũ, hủy registrations và tasks, đóng resources, đóng loader rồi bỏ strong references.

Cuối cùng, **namespace isolation không phải sandbox**. Với plugin chưa tin cậy, cần process/OS isolation và capability/security model phù hợp; không sử dụng SecurityManager vì đã vô hiệu hóa trên Java hiện đại. Những nguyên tắc này giúp hệ thống plugin Java giữ đúng **class identity, resource ownership, lifecycle và khả năng bảo trì**, từ Java 7 đến các JDK mới.