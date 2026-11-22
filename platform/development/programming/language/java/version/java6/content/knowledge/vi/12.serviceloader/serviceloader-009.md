# ServiceLoader: Phạm vi class loader và vòng đời nhà cung cấp

## 1. Vấn đề cần giải quyết

`java.util.ServiceLoader<S>` là cơ chế phát hiện và sử dụng các **service provider** (lớp hoặc factory cung cấp implementation của một service). Thay vì gắn chặt ứng dụng với tên class triển khai, code chỉ cần biết hợp đồng của service, chẳng hạn `Greeting` hoặc `Codec`. Khi chạy, `ServiceLoader` tìm những provider được khai báo cho service đó trong phạm vi thích hợp.

Hai câu hỏi rất quan trọng khi dùng cơ chế này trong hệ thống plugin, server, nhiều ứng dụng chung JVM hoặc JPMS (Java Platform Module System):

1. **Phạm vi tìm kiếm:** provider nào được nhìn thấy, phụ thuộc vào `ClassLoader` hoặc `ModuleLayer` nào?
2. **Vòng đời provider:** provider được tạo lúc nào, được cache ở đâu, `reload()` thực sự thay đổi điều gì, và ai phải dọn tài nguyên?

Kiến thức dưới đây áp dụng cho Java hiện đại (Java **17+**). Phần Java 9+ module system và `ServiceLoader.stream()` cũng được dùng vì đây là API hiện hành. Không cần cơ chế extension directory `jre/lib/ext` đã lỗi thời để hiểu `ServiceLoader`.

## 2. Phân biệt ba đối tượng thường bị gọi chung là “loader”

| Thành phần | Vai trò | Có cache instance provider? |
| --- | --- | --- |
| `ClassLoader` | Định nghĩa lớp Java, tìm tài nguyên như `META-INF/services/...`, quyết định visibility/identity của class | Không phải cache provider của `ServiceLoader` |
| `ModuleLayer` | Tập các named module đã được giải quyết và gán class loader; tạo phạm vi tìm provider theo module | Không phải instance cache của `ServiceLoader` |
| `ServiceLoader<S>` | Dựa vào phạm vi đã chọn để tìm provider, rồi tạo/cache provider theo nhu cầu | **Có**, thuộc về từng đối tượng `ServiceLoader` |

**Phạm vi tìm kiếm ≠ phạm vi cache.** Hai đối tượng `ServiceLoader<Greeting>` cùng sử dụng một `ClassLoader` có thể nhìn thấy cùng danh sách provider, nhưng cache riêng và có thể tạo **hai instance provider khác nhau**. Ngược lại, thay thread context class loader sau khi tạo một `ServiceLoader` không tự chuyển phạm vi tìm kiếm của đối tượng đã tạo.

Về **class identity**, một kiểu Java không chỉ được nhận diện bằng tên đầy đủ: trong JVM, định nghĩa class còn gắn với **class loader đã định nghĩa class**. Hai bản `com.example.spi.Greeting` cùng tên do hai class loader khác nhau định nghĩa có thể là hai kiểu khác nhau. Provider nhìn thấy được trên class path vẫn phải tương thích với đúng `Class<Greeting>` mà consumer truyền cho `ServiceLoader`. Vì vậy, trong kiến trúc plugin, service API thường được chia sẻ qua parent/class loader chung, còn class triển khai có thể được nạp bởi loader riêng.

## 3. Các cách chọn phạm vi provider

### 3.1. `ServiceLoader.load(Service.class)`: dùng thread context class loader (TCCL)

Lời gọi tiện lợi:

~~~java
ServiceLoader<Greeting> services = ServiceLoader.load(Greeting.class);
~~~

Tương đương về phạm vi với:

~~~java
ClassLoader context = Thread.currentThread().getContextClassLoader();
ServiceLoader<Greeting> services = ServiceLoader.load(Greeting.class, context);
~~~

Hai đoạn trên là **minh họa** khi `Greeting` đã được khai báo. TCCL là class loader gắn với thread thực thi **tại thời điểm gọi `load`**. Nó có thể khác loader đã định nghĩa lớp consumer; ví dụ framework/server có thể gán TCCL phù hợp cho ứng dụng đang xử lý.

Hệ quả thực tế:

- Trên những thread có TCCL khác nhau, cùng `ServiceLoader.load(Greeting.class)` có thể tìm ra tập provider khác nhau.
- Đối tượng `ServiceLoader` được tạo dựa vào loader đã chọn lúc gọi `load`. Nếu thread đổi TCCL sau đó, `reload()` vẫn dùng phạm vi cũ; để tìm theo TCCL mới, hãy tạo **ServiceLoader mới**.
- Không cache một `ServiceLoader` tạo bằng overload này ở phạm vi **toàn JVM** nếu có nhiều ứng dụng/tenant với TCCL khác nhau. Oracle cảnh báo cả nguy cơ chọn nhầm provider và giữ tham chiếu làm rò rỉ class loader.

Nếu chủ động thay TCCL trong code tích hợp, cần **khôi phục loader cũ trong `finally`** sau tác vụ để tránh làm bẩn thread được tái sử dụng. Trong môi trường executor hoặc async, đừng giả định worker thread luôn có TCCL giống thread gửi tác vụ.

### 3.2. `ServiceLoader.load(Service.class, classLoader)`: chọn explicit ClassLoader

~~~java
ClassLoader scope = Greeting.class.getClassLoader();
ServiceLoader<Greeting> services =
        ServiceLoader.load(Greeting.class, scope);
~~~

Đoạn minh họa này không phụ thuộc TCCL. Một plugin host có thể truyền loader dành cho plugin cụ thể để tìm provider. Nhưng phạm vi không đơn giản là “chỉ class trong đúng loader đó”:

- Với **classpath/unnamed module**, `ServiceLoader` tìm các file `META-INF/services/<binary-name-of-service>` thông qua `ClassLoader.getResources` và tải tên provider được liệt kê. Provider class phải nhìn thấy được và phải assignable sang service type mà caller yêu cầu.
- Với **named module**, `ServiceLoader` tìm cả provider được khai báo trong các module gắn với loader, parent loader và (theo quy tắc JPMS) các module cùng module layer mà các loader đó tham gia. Một layer dùng nhiều class loader có thể đóng góp provider từ các loader khác trong **cùng layer**.
- Thứ tự discovery phụ thuộc quy tắc của API và nguồn resource/module; **không dùng thứ tự tình cờ để biểu thị mức ưu tiên nghiệp vụ**.

Lưu ý: overload nhận `null` cho tham số class loader có quy tắc fallback riêng tới system class loader (hoặc bootstrap nếu cần), không phải cú pháp để yêu cầu “không tìm provider”. Trong ví dụ và ứng dụng thật, nên truyền loader có chủ ý.

### 3.3. `ServiceLoader.load(ModuleLayer, Service.class)`: chọn lớp module

~~~java
ServiceLoader<Greeting> services =
        ServiceLoader.load(ModuleLayer.boot(), Greeting.class);
~~~

Đoạn trên là ví dụ API độc lập về **cách chọn layer**, chưa cung cấp một provider cụ thể. Overload `load(layer, service)`:

- Tìm provider trong **named modules** của layer chỉ định và các **ancestor layers** của nó.
- **Không tìm** provider từ unnamed modules/classpath chỉ vì chúng tồn tại trong cùng JVM.
- Có thể có nhiều class loader trong một layer; đây là truy vấn theo **cấu trúc module**, khác với việc đơn thuần duyệt một cây class loader.
- Không bảo đảm thứ tự tuyệt đối giữa các module cùng layer. Nếu cần lựa chọn theo tính năng/ưu tiên, dùng thông tin mà service/provider tự công bố.

Với code consumer trong **explicit named module**, `module-info.java` phải khai báo `uses` cho service; module chứa service phải đọc được (`requires` nếu cần). Module provider khai báo `provides ... with ...`. Ví dụ các **đoạn khai báo minh họa**, mỗi đoạn thuộc một tệp `module-info.java` khác nhau:

~~~java
// Module API: com.example.spi
module com.example.spi {
    exports com.example.spi;
}
~~~

~~~java
// Module consumer: com.example.app
module com.example.app {
    requires com.example.spi;
    uses com.example.spi.Greeting;
}
~~~

~~~java
// Module provider: com.example.greeting.english
module com.example.greeting.english {
    requires com.example.spi;
    provides com.example.spi.Greeting
        with com.example.greeting.english.EnglishGreeting;
}
~~~

Các đoạn module descriptor này minh họa contract nhưng **chưa phải dự án chạy độc lập**, vì chưa có source `Greeting` và `EnglishGreeting` tương ứng. Trong named module, provider có thể được tạo bằng **public no-args constructor** hoặc, nếu áp dụng, public static no-args `provider()` trả về service type. Với provider cấu hình trên **classpath** qua `META-INF/services`, triển khai kiểu provider class public và public no-args constructor như ví dụ ở phần 5.

### 3.4. `loadInstalled` có vai trò khác

`ServiceLoader.loadInstalled(Service.class)` trong Java hiện đại dùng **platform class loader** (tương đương truyền `ClassLoader.getPlatformClassLoader()`). Nó thường **không thấy** provider thông thường trên application classpath/module path. Không dùng nó như cách mặc định tìm plugin của ứng dụng; cũng không áp dụng hướng dẫn cũ về thư mục `jre/lib/ext` đã bị loại bỏ.

## 4. Vòng đời: discover → instantiate → cache → reload

### 4.1. Tạo đối tượng loader chưa đồng nghĩa tạo provider

~~~text
ServiceLoader.load(...)
    │ tạo đối tượng ServiceLoader cho scope đã chọn
    ▼
iterator() / stream()
    │ tìm provider theo nhu cầu
    ├─ iterator.next() → tạo instance provider (nếu chưa cache)
    │                   → cache instance trong ServiceLoader
    └─ stream() → duyệt các Provider<S> metadata theo nhu cầu
                  → Provider.get() khi thật sự cần instance
    ▼
lặp lại iterator() trên cùng ServiceLoader
    → dùng lại instance provider đã được cache
    ▼
reload()
    → xóa cache của ServiceLoader đó
    → vòng lặp sau tìm/tạo lại theo scope ban đầu
~~~

`ServiceLoader.load(...)` tạo đối tượng phục vụ discovery; constructor của provider **thường chưa được gọi ngay**. Với `iterator()`, việc tìm/khởi tạo diễn ra khi iterator được tiêu thụ: các provider đã cache được trả trước, provider chưa có được tạo theo nhu cầu.

Điểm khác giữa hai đường dùng:

- `iterator()` trả các **instance `S`**. Đối tượng `ServiceLoader` lưu cache provider instance đã tạo; gọi `iterator()` lần nữa trên **cùng** loader sẽ gặp lại instance đã cache.
- `stream()` (Java 9+) trả `ServiceLoader.Provider<S>`, cho phép xem `type()`/lọc provider trước khi gọi `get()` để lấy instance. Đừng nhầm cache các entry/descriptor của stream với cam kết rằng mọi lần `Provider.get()` đều phải trả cùng object. Nếu ứng dụng cần lifecycle singleton, hãy quản lý lifecycle riêng theo hợp đồng của nó.

### 4.2. `reload()` làm gì?

~~~java
services.reload();
~~~

`reload()` **xóa cache provider** của **đúng đối tượng `ServiceLoader` đang gọi**. Lần lặp hoặc stream sau sẽ lại tìm các provider và khởi tạo khi cần. Với kiểu provider có public constructor trả instance mới như ví dụ phần 5, sau `reload` sẽ có instance mới.

`reload()` **không** tự động:

- đóng tài nguyên/`close()` của instance provider cũ;
- thu hồi các tham chiếu provider mà caller đang giữ;
- thay class loader/TCCL/module layer mà đối tượng `ServiceLoader` đã chọn;
- unload class, thay bytecode, cài JAR mới hay xây module layer mới;
- đồng bộ cache của những `ServiceLoader` khác.

Nếu ứng dụng thay đổi tập provider động, `reload` chỉ phát huy trong giới hạn provider hiện **có thể được scope class loader/module layer đó phát hiện**. Thường cần cấu hình loader/layer mới phù hợp khi plugin mới không nằm trong scope cũ.

**Không dùng iterator/stream cũ sau `reload()`.** API yêu cầu loại bỏ chúng; chúng có thể ném `ConcurrentModificationException` khi sử dụng tiếp. Tạo iterator/stream mới sau khi reload.

### 4.3. Instance có vòng đời riêng với cache

Một provider có thể mở kết nối, thread pool hoặc file handle khi được tạo. `ServiceLoader` chỉ lo **tìm, tạo, giữ cache**; bản thân nó **không cung cấp lifecycle `start/stop/close` thống nhất cho provider**. Nếu service có tài nguyên, thiết kế một contract riêng, ví dụ interface mở rộng `AutoCloseable`, và để component sở hữu provider gọi `close()` khi ngừng dùng.

Không giả định việc `reload()` đã giải phóng tài nguyên. Một instance cũ vẫn có thể hoạt động nếu caller còn giữ tham chiếu. Vì mỗi `ServiceLoader` có cache riêng, hai loader nhìn cùng provider class có thể sở hữu **hai instance riêng biệt**, trừ khi chính provider factory chủ động dùng shared instance; API không tự đảm bảo singleton toàn JVM.

## 5. Ví dụ Java 17+ có thể chạy: quan sát cache và vòng đời

Ví dụ sử dụng **classpath SPI** để chạy bằng JDK mà không cần hệ thống module riêng. Tạo bốn tệp ở đúng cấu trúc:

~~~text
spi-demo/
├── Greeting.java
├── HelloProvider.java
├── Demo.java
└── META-INF/
    └── services/
        └── Greeting
~~~

**Tệp `Greeting.java`:**

~~~java
public interface Greeting {
    String greet();
}
~~~

**Tệp `HelloProvider.java`:**

~~~java
public final class HelloProvider implements Greeting {
    private static int created = 0;
    private final int id;

    public HelloProvider() {
        id = ++created;
        System.out.println("constructor #" + id);
    }

    public static int createdCount() {
        return created;
    }

    @Override
    public String greet() {
        return "hello-" + id;
    }
}
~~~

**Tệp `META-INF/services/Greeting`** phải chứa đúng một dòng, là binary name của provider. Với ví dụ dùng default package này, tên là:

~~~text
HelloProvider
~~~

Trong dự án thực tế dùng package, tên file phải là **fully qualified binary name của service**, còn mỗi dòng là **binary name của provider**; ví dụ `META-INF/services/com.example.spi.Greeting` chứa `com.example.provider.EnglishGreeting`. File provider-configuration phải có encoding **UTF-8**. Không dùng `module-info.java` trong ví dụ classpath này.

**Tệp `Demo.java`:**

~~~java
import java.util.ServiceLoader;

public final class Demo {
    public static void main(String[] args) {
        ClassLoader scope = Greeting.class.getClassLoader();

        ServiceLoader<Greeting> services =
                ServiceLoader.load(Greeting.class, scope);

        System.out.println("after load: " + HelloProvider.createdCount());

        Greeting first = services.iterator().next();
        System.out.println("first: " + first.greet());

        Greeting again = services.iterator().next();
        System.out.println("same cached: " + (first == again));

        services.reload();
        Greeting fresh = services.iterator().next();
        System.out.println("new after reload: " + (first != fresh));
        System.out.println("old still works: " + first.greet());

        ServiceLoader<Greeting> independent =
                ServiceLoader.load(Greeting.class, scope);
        Greeting other = independent.iterator().next();
        System.out.println("separate cache: " + (fresh != other));
    }
}
~~~

Tại thư mục `spi-demo` (có `META-INF` trực tiếp bên dưới), chạy:

~~~bash
javac Greeting.java HelloProvider.java Demo.java
java -cp . Demo
~~~

Stdout dự kiến **chính xác** khi chỉ có một provider được khai báo trong tệp cấu hình trên và chạy từ thư mục mẫu:

~~~text
after load: 0
constructor #1
first: hello-1
same cached: true
constructor #2
new after reload: true
old still works: hello-1
constructor #3
separate cache: true
~~~

**Diễn giải từng mốc:**

1. Dòng `after load: 0` chứng tỏ tạo `ServiceLoader` không kích hoạt constructor provider.
2. `iterator().next()` lần đầu tạo `HelloProvider #1`. Lần kế tiếp trên **cùng** `ServiceLoader` trả instance đó (`same cached: true`).
3. Sau `services.reload()`, lần `next()` tiếp theo tạo `HelloProvider #2`; object `first` vẫn tồn tại và vẫn có thể được gọi.
4. Tạo đối tượng `ServiceLoader` thứ hai cùng `scope` tạo cache khác, vì thế xuất hiện constructor `#3`. Cùng ClassLoader **không đồng nghĩa cùng provider instance**.

**Đầu ra có chủ ý phụ thuộc cấu hình thử nghiệm.** Nếu bạn thêm provider khác hoặc chạy từ classpath chứa file `META-INF/services/Greeting` khác, `iterator().next()` có thể chọn provider khác; khi đó không dùng stdout trên để suy ra thứ tự discovery. Ví dụ bảo đảm tính xác định bằng cách giữ duy nhất cấu hình provider trong thư mục chạy.

## 6. Khi tích hợp plugin, phải thiết kế ranh giới vòng đời

### Phạm vi theo ứng dụng/plugin

- **Chọn loader/layer theo ngữ cảnh dùng thực tế.** Nếu plugin tách classloader, host nên kiểm soát chỗ khởi tạo `ServiceLoader.load(service, pluginLoader)` hoặc `load(pluginLayer, service)`. Đừng để một `ServiceLoader` global phục vụ lẫn các ứng dụng với scope khác nhau.
- **Chia sẻ service API phù hợp.** Nếu host và plugin tạo hai bản class `Greeting` độc lập, provider có thể không cast/assign được sang service type của host dù có cùng tên. Ưu tiên để phần API service được nhìn thấy qua loader chung.
- **Xác định ai sở hữu provider.** Chỉ component có quyền dừng provider và bỏ các reference cần thiết mới nên quản lý lifecycle/close. Nếu có cache hoặc thread pool gắn với provider, phải có kế hoạch giải phóng.
- **Đừng xem `reload` như hot swap.** Muốn triển khai bản plugin mới cần chiến lược cập nhật classloader/module layer và tham chiếu tới provider cũ; `reload` chỉ reset cache `ServiceLoader`.
- **Không cache provider/ServiceLoader vô thời hạn** ở singleton toàn JVM khi plugin có thể unload. Reference từ singleton, thread, static holder hoặc cache có thể giữ classloader/plugin không được GC.

### Threading và lỗi

- `ServiceLoader` **không thread-safe**. Đừng cho nhiều thread đồng thời gọi `iterator()`, `stream()`, `findFirst()` hoặc `reload()` trên cùng instance mà không có cơ chế đồng bộ phù hợp. Nếu cần song song, thiết kế lifecycle access hoặc loader riêng.
- Thread safety của **provider instance** là hợp đồng riêng của provider, không tự có vì được `ServiceLoader` khởi tạo hoặc cache.
- Việc tìm/đọc cấu hình/tạo provider có thể lỗi **khi duyệt**, không chỉ khi gọi `load()`. `ServiceConfigurationError` có thể xuất hiện từ `iterator().hasNext()/next()`, `stream()` khi xử lý, hoặc `Provider.get()`. Nó là **`Error`**, nên xử lý có chủ đích tại ranh giới plugin thay vì bắt mọi `Exception` rồi bỏ qua.
- Nếu ứng dụng cần chọn provider theo chất lượng, khả năng, version hay ưu tiên, hãy định nghĩa tiêu chí trong service metadata/contract. Không tin rằng `findFirst()` luôn trả implementation “mặc định” ở mọi môi trường.

## 7. Lỗi phổ biến và cách nhận diện

| Triệu chứng | Khả năng nguyên nhân | Cách kiểm tra phù hợp |
| --- | --- | --- |
| Không tìm thấy provider trên classpath | Sai tên `META-INF/services`, thiếu resource khi đóng gói, classloader không nhìn thấy JAR | Kiểm tra tên resource, nội dung UTF-8 và classloader được truyền |
| Có provider nhưng `ServiceConfigurationError` | Class không load được, sai service type, constructor không hợp lệ, provider method thất bại | Xem root cause và stack trace lúc iterator/stream chạy; xác minh service class identity |
| Dùng TCCL một thread thấy provider, thread khác không | Hai thread có context loader khác nhau | In/quan sát `getContextClassLoader()` ở thời điểm gọi `load` |
| `reload()` nhưng vẫn không có plugin mới | Provider/JAR không nằm trong scope hiện tại | Kiểm tra classloader/module layer; có thể cần loader/layer mới |
| Sau `reload()` còn thấy kết nối cũ | Provider cũ vẫn được caller giữ; `reload` không close | Xác định owner và gọi shutdown/close theo contract |
| Plugin không unload và bộ nhớ tăng | Cache/global reference/thread giữ classloader/provider | Kiểm tra reference graph, giới hạn scope cache và cleanup |
| Kết quả `findFirst()` thay đổi theo runtime | Không có thứ tự ưu tiên nghiệp vụ được bảo đảm | Chọn theo metadata/rule rõ ràng |

## 8. Tự kiểm tra

1. **Hai `ServiceLoader` cùng tham số `ClassLoader` có bắt buộc dùng chung instance provider?** Không; mỗi `ServiceLoader` quản lý cache riêng.
2. **Tại sao đổi TCCL trên một thread rồi gọi `reload` ở loader cũ không đổi provider scope?** Vì đối tượng loader đã giữ scope được chọn khi tạo.
3. **Có thể dùng `load(layer, service)` để tìm provider trong `META-INF/services` trên unnamed module không?** Không; overload này tìm provider từ named modules của layer và ancestors.
4. **`reload()` có gọi `close()`/`shutdown()` không?** Không; chủ sở hữu provider phải tự thực hiện.
5. **`stream().filter(p -> ...p.type()...)` có bắt buộc tạo instance trước khi filter?** Không; có thể xem metadata/type trước, rồi mới gọi `Provider.get()`.
6. **Có nên dùng chung một `ServiceLoader` cho nhiều thread không đồng bộ?** Không; `ServiceLoader` không thread-safe.
7. **Cùng tên class nhưng khác defining classloader có luôn tương thích kiểu?** Không; cần cùng định nghĩa service API hoặc quan hệ classloader đúng.

## 9. Tài liệu API chính thức (đang áp dụng)

- [Java SE 25 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): overload theo classloader/layer, provider discovery, caching, reload và concurrency.
- [Java SE 25 — `ServiceLoader.Provider`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.Provider.html): xem `type()` và gọi `get()` khi cần instance.
- [Java SE 25 — `ModuleLayer`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ModuleLayer.html): phạm vi các named module và class loader gắn với layer.

Nhớ ba lớp ranh giới: **ClassLoader/ModuleLayer quyết định chỗ tìm provider; ServiceLoader quản lý cache per-instance; ứng dụng quản lý vòng đời tài nguyên của provider.**