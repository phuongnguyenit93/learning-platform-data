# Iterator, stream và ServiceLoader.Provider trong Java

`ServiceLoader<S>` là cơ chế **Service Provider Interface (SPI)** chuẩn của Java để ứng dụng tìm và sử dụng implementation của một service mà không cần viết cứng tên từng lớp triển khai. Có hai con đường quan trọng để duyệt kết quả tìm thấy:

- **`iterator()`** cung cấp `Iterator<S>`: mỗi phần tử là **instance dịch vụ `S`**. Khi duyệt, ServiceLoader nạp và **khởi tạo provider theo nhu cầu**.
- **`stream()`** (từ Java 9) cung cấp `Stream<ServiceLoader.Provider<S>>`: mỗi phần tử là **một mô tả provider**, có thể xem `type()` trước và chỉ tạo instance khi gọi `get()`.

Khác biệt này không chỉ là lựa chọn cú pháp `for` hay Stream API. Nó quyết định **thời điểm constructor/provider factory được gọi**, khả năng **lọc dựa trên metadata trước khi tạo object**, cách **cache và reload**, cách xử lý lỗi discovery/instantiation, và cách kết hợp SPI với class loader, thread context class loader (TCCL) và Java Platform Module System (JPMS).

Bài này tập trung chính xác vào `Iterator`, `stream` và `ServiceLoader.Provider`, có ví dụ **Java 17 biên dịch/chạy được và stdout đã kiểm tra**, cùng những giới hạn quan trọng khi dùng trong hệ plugin.

## 1. ServiceLoader duyệt cái gì?

Một **service** là interface hoặc abstract class biểu diễn hợp đồng. **Provider** là implementation có thể được framework hoặc ứng dụng tìm thấy theo metadata SPI.

~~~text
                         Service type
                         codec.api.Codec
                               |
                +--------------+---------------+
                |                              |
        Provider A                        Provider B
        codec.impl.Alpha                  codec.impl.Beta
                |                              |
                +--------------+---------------+
                               |
                               v
                     ServiceLoader<Codec>
                         /            \
                        v              v
               iterator()             stream()
               Iterator<Codec>        Stream<Provider<Codec>>
                        |              |
                        v              v
                  Codec instance    Provider descriptor
                                         |
                               +---------+--------+
                               |                  |
                             type()              get()
                               |                  |
                               v                  v
                         Class<? extends    Codec instance
                            Codec>
~~~

Trong code:

~~~java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

Iterator<Codec> objects = loader.iterator();

Stream<ServiceLoader.Provider<Codec>> descriptions =
        loader.stream();
~~~

Đoạn trên chỉ là **fragment kiểu API**: để biên dịch cần khai báo `Codec` và các `import` tương ứng. Một chương trình hoàn chỉnh có ở mục 4.

**`ServiceLoader<S>` implements `Iterable<S>`**, nên có thể dùng enhanced-for:

~~~java
for (Codec codec : loader) {
    System.out.println(codec.id());
}
~~~

Nhưng chú ý: enhanced-for gọi `iterator()` và nhận **instance `Codec`**, không phải `ServiceLoader.Provider<Codec>`.

Ngược lại, phần tử của `loader.stream()` là **`Provider<Codec>`**, chưa phải object `Codec`. Vì vậy:

~~~java
loader.stream()
        .map(ServiceLoader.Provider::get)
        .forEach(codec -> System.out.println(codec.id()));
~~~

Lệnh `map(...::get)` chính là bước lấy hoặc tạo instance từ mỗi provider descriptor. Không thể gọi trực tiếp `codec.id()` trên biến kiểu `Provider<Codec>` trước khi `get()`.

## 2. So sánh iterator, stream, Provider.type và Provider.get

| API | Kiểu giá trị | Điều quan trọng |
| --- | --- | --- |
| `loader.iterator()` | `Iterator<S>` | Duyệt **service instances**; mỗi provider mới được định vị và khởi tạo lười khi cần. |
| `for (S s : loader)` | `S` | Cú pháp tiện của `Iterable`; về bản chất dựa trên `iterator()`. |
| `loader.findFirst()` | `Optional<S>` | Lấy và khởi tạo provider đầu tiên nếu có; hữu ích cho fallback, nhưng “đầu tiên” phụ thuộc thứ tự discovery. |
| `loader.stream()` | `Stream<ServiceLoader.Provider<S>>` | Duyệt **descriptors**, có thể lọc provider trước khi tạo instance. |
| `provider.type()` | `Class<? extends S>` | Trả type của provider theo hợp đồng API, không trả instance dịch vụ. |
| `provider.get()` | `S` | Trả instance của provider; có thể gọi constructor hoặc provider factory. |

Đừng viết code với giả định rằng `stream()` trả `Stream<S>`. Kiểu đúng là:

~~~java
Stream<ServiceLoader.Provider<MyService>> descriptors =
        ServiceLoader.load(MyService.class).stream();
~~~

Đây là fragment, cần khai báo `MyService`. Nếu muốn `Stream<MyService>`, có thể biến đổi bằng `map(Provider::get)`; song điều đó **kích hoạt instantiation** khi stream được tiêu thụ.

### Khác nhau ở thời điểm thực thi

Khi tạo một `ServiceLoader` hay chỉ gọi `stream()`, chưa cần tạo tất cả provider instances. Stream pipeline có tính **lazy**: thao tác trung gian `filter`, `map`, `sorted` thường không tự chạy cho tới khi có terminal operation như `findFirst()`, `toList()`, `count()` hoặc `forEach()`.

~~~text
ServiceLoader.load(...)                nhận một loader cho service
        |
        +-- iterator()                 tạo iterator
        |      |
        |      +-- next()              cần một S, có thể instantiate
        |
        +-- stream()                   tạo Stream<Provider<S>>
               |
               +-- filter(p -> p.type()...)
               |       (đánh giá khi duyệt)
               |
               +-- findFirst()
                       |
                       v
                  Provider<S>
                       |
                       +-- get()        tạo/lấy instance S
~~~

Lưu ý chính xác: **“lazy” không có nghĩa toàn bộ metadata/discovery không thể phát sinh lỗi cho tới khi gọi `get()`**. Bản thân việc định vị, đọc metadata SPI và load provider type trong lúc tiêu thụ stream cũng có thể ném `ServiceConfigurationError`. Điểm mạnh của `Provider.type()` là **có thể quyết định có cần tạo instance hay không trước khi gọi `get()`**.

## 3. ServiceLoader.Provider<S> là kiểu gì?

`ServiceLoader.Provider<S>` là interface lồng trong `ServiceLoader` và **extends `Supplier<S>`**. Nó biểu diễn provider do ServiceLoader đã định vị và cung cấp hai phương thức trung tâm:

~~~java
Class<? extends S> type();
S get();
~~~

Đây là **chữ ký khái quát**, không phải khai báo interface riêng để tạo trong project.

### Provider.type(): xem kiểu mà chưa instantiate

Một tình huống điển hình là lọc provider theo annotation, tên class hoặc đặc điểm type:

~~~java
Optional<ServiceLoader.Provider<Codec>> candidate =
        loader.stream()
              .filter(p -> p.type()
                            .isAnnotationPresent(FastCodec.class))
              .findFirst();
~~~

Đây là fragment: `Codec`, annotation `FastCodec` và `loader` cần được khai báo. Việc kiểm tra `p.type()` chỉ yêu cầu metadata type; **không yêu cầu gọi constructor của service object**. Tuy vậy, JVM vẫn có thể phải nạp class và truy vấn metadata/annotation, nên không thể nói “type() hoàn toàn không làm gì” hoặc không có side effects từ các lớp liên quan.

Nếu filter tìm được đúng provider:

~~~java
Codec codec = candidate.orElseThrow().get();
~~~

Lúc này `get()` mới lấy instance. Sử dụng filter trước `get()` giúp tránh tạo object của provider không phù hợp, nhất là khi constructor tốn tài nguyên hoặc plugin có nhiều implementation.

### Provider.get(): tạo instance theo cách provider khai báo

Với provider thông thường trên classpath hoặc một provider class được khai báo trong named module, `get()` có thể gọi constructor/provider creation mechanism. Đối với named module, Java hỗ trợ **provider factory method** là public static no-arg `provider()` theo các điều kiện của `ServiceLoader` API.

~~~java
// Fragment trong named module; class triển khai service ở bên ngoài.
public final class CodecProviderFactory {
    public static Codec provider() {
        return new AlphaCodec();
    }
}
~~~

Đây **không phải phần của ví dụ biên dịch ở mục 4**. Trong named module, descriptor có thể khai báo một provider factory class phù hợp bằng `provides ... with ...`. Điểm cần nhớ:

- Nếu dùng factory method, `Provider.type()` trả **return type của `provider()`**, không nhất thiết là `CodecProviderFactory.class`.
- `Provider.get()` thực thi cơ chế tạo instance theo provider tương ứng và có thể ném `ServiceConfigurationError` nếu không tạo được object hợp lệ.
- **Đừng mặc định gọi `get()` nhiều lần luôn trả cùng object.** `Provider<S>` là một supplier và API không nên bị hiểu như một singleton registry.
- Cơ chế factory provider trong named module không nên đánh đồng với việc ghi tên một class chỉ có factory (không có constructor public no-args) vào `META-INF/services` trên classpath. Classpath provider-configuration cần implementation có constructor provider phù hợp.

Do đó, nếu lọc dựa trên annotation đặt trên **factory class**, `p.type().isAnnotationPresent(...)` có thể không tìm thấy annotation ấy: `type()` có thể là **return type** của factory method, không phải class chứa method.

## 4. Chương trình Java 17 hoàn chỉnh: kiểm tra laziness, cache và reload

Ví dụ dùng một **named module** `codec.demo`, bên trong khai báo service `codec.api.Codec` và một provider `codec.impl.Alpha`. Để đo số lần khởi tạo, constructor provider tăng biến đếm `Probe.created`.

Cách làm có một ưu điểm: **chỉ một provider** nên không phụ thuộc thứ tự discovery giữa nhiều module hoặc nhiều JAR. Output do đó có thể kiểm tra chính xác.

Tạo **năm file** theo cấu trúc:

~~~text
spi-demo/
└── src/
    └── codec.demo/
        ├── module-info.java
        └── codec/
            ├── api/
            │   ├── Codec.java
            │   └── Probe.java
            ├── impl/
            │   └── Alpha.java
            └── app/
                └── Main.java
~~~

### File 1 — src/codec.demo/module-info.java

~~~java
module codec.demo {
    exports codec.api;

    uses codec.api.Codec;

    provides codec.api.Codec with codec.impl.Alpha;
}
~~~

Giải thích:

- `exports codec.api`: công khai package hợp đồng khi module khác cần dùng service type.
- `uses codec.api.Codec`: cho biết code trong named module này tiêu thụ service `Codec`.
- `provides codec.api.Codec with codec.impl.Alpha`: đăng ký một provider cho service.
- Package `codec.impl` **không cần export**: ServiceLoader có cơ chế instantiate provider theo hợp đồng JPMS, không đòi ta công khai implementation package cho mọi module.

### File 2 — src/codec.demo/codec/api/Codec.java

~~~java
package codec.api;

public interface Codec {
    String id();
}
~~~

`Codec` là API contract mà caller sử dụng. Trong hệ nhiều module, các provider phải implements **đúng định nghĩa interface này**, không chỉ một bản khác có cùng binary name.

### File 3 — src/codec.demo/codec/api/Probe.java

~~~java
package codec.api;

public final class Probe {
    private Probe() { }

    public static int created;
}
~~~

`Probe.created` dùng để đo lúc constructor provider được gọi. Đây là biến tĩnh phục vụ ví dụ; ứng dụng production không nên dùng một counter mutable không đồng bộ để ghi nhận khởi tạo provider qua nhiều thread.

### File 4 — src/codec.demo/codec/impl/Alpha.java

~~~java
package codec.impl;

import codec.api.Codec;
import codec.api.Probe;

public final class Alpha implements Codec {
    public Alpha() {
        Probe.created++;
    }

    @Override
    public String id() {
        return "alpha";
    }
}
~~~

Mỗi lần `new Alpha()` thành công, constructor tăng counter lên một. `ServiceLoader` sẽ tạo instance khi được yêu cầu theo đường iterator hoặc `Provider.get()`.

### File 5 — src/codec.demo/codec/app/Main.java

~~~java
package codec.app;

import codec.api.Codec;
import codec.api.Probe;
import java.util.Iterator;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader<Codec> loader =
                ServiceLoader.load(Codec.class);

        System.out.println("Initial count: " + Probe.created);

        ServiceLoader.Provider<Codec> provider = loader.stream()
                .filter(p -> p.type().getSimpleName().equals("Alpha"))
                .findFirst()
                .orElseThrow();

        System.out.println("After type filter: " + Probe.created);

        Codec selected = provider.get();

        System.out.println("After Provider.get: " + Probe.created);
        System.out.println("Selected id: " + selected.id());

        // Dùng ServiceLoader KHÁC để quan sát cache của iterator riêng.
        ServiceLoader<Codec> other =
                ServiceLoader.load(Codec.class);

        Iterator<Codec> firstIterator = other.iterator();
        Codec first = firstIterator.next();

        System.out.println("After iterator.next: " + Probe.created);

        Codec again = other.iterator().next();
        System.out.println("Iterator reused instance: " + (first == again));

        other.reload();

        Codec fresh = other.iterator().next();
        System.out.println("After reload next: " + Probe.created);
        System.out.println("Fresh after reload: " + (first != fresh));
    }
}
~~~

Chạy từ thư mục `spi-demo` bằng **JDK 17 trở lên**:

~~~bash
javac --release 17 -d out --module-source-path src -m codec.demo
java --module-path out -m codec.demo/codec.app.Main
~~~

**Stdout chính xác** đã được đối chiếu bằng biên dịch và chạy với JDK hỗ trợ `--release 17`:

~~~text
Initial count: 0
After type filter: 0
After Provider.get: 1
Selected id: alpha
After iterator.next: 2
Iterator reused instance: true
After reload next: 3
Fresh after reload: true
~~~

### Giải thích từng dòng

1. `ServiceLoader.load(Codec.class)` tạo loader service; chưa có provider instance nào. `Probe.created` ban đầu là `0`.
2. `loader.stream()` tạo một stream của `Provider<Codec>`. Biểu thức `filter(p -> p.type()...)` được chạy khi `findFirst()` tiêu thụ pipeline, nhưng **không gọi `p.get()`**. Bởi thế counter vẫn bằng `0` sau bước lọc.
3. `provider.get()` trả một `Codec` thực tế, constructor của `Alpha` chạy và tăng `Probe.created` thành `1`.
4. Method `id()` trả `alpha`.
5. `other` là **một ServiceLoader khác**. Lệnh `other.iterator().next()` lần đầu cần một service instance và tạo thêm `Alpha`, counter thành `2`.
6. `other.iterator().next()` ở lần gọi kế tiếp trả lại provider instance đã được **cache trong chính `other`**, nên so tham chiếu `first == again` cho `true`. Không có constructor thứ ba trước lúc reload.
7. `other.reload()` xóa các provider cache của `other`. Lần `other.iterator().next()` tiếp theo tìm/nạp lại provider, tạo object mới; counter thành `3` và `first != fresh` là `true`.

**Giới hạn có chủ đích của ví dụ:** Chỉ một provider, nên demo không dựa vào thứ tự nạp nhiều provider. Việc `Provider.get()` tạo instance ở đây được quan sát cho **một lần gọi**; không từ đó suy rằng `Provider.get()` có contract cache giống iterator. Sau `reload`, các references `first`/`again` vẫn trỏ object cũ; reload chỉ xóa cache của ServiceLoader, **không hủy object đã được caller giữ**.

## 5. Caching: khác nhau giữa iterator và stream

ServiceLoader tìm provider **lazily** và duy trì những cache phục vụ các đường duyệt.

### Với iterator()

Theo API, mỗi `iterator()` trước hết trả những **provider instances đã được cache bởi những lần duyệt iterator trước** theo thứ tự đã tạo, sau đó mới tìm và tạo thêm provider còn lại khi cần. Vì vậy, gọi lại `loader.iterator()` không có nghĩa chương trình sẽ khởi tạo lại mọi provider từ đầu.

~~~java
ServiceLoader<Codec> services = ServiceLoader.load(Codec.class);

Codec a = services.iterator().next();
Codec b = services.iterator().next();

System.out.println(a == b);
~~~

Đây là **fragment phụ thuộc SPI hợp lệ**. Nếu chỉ có một provider như chương trình phần 4, dòng in là `true`; nếu có nhiều provider, vẫn là phần tử cached đầu tiên khi chưa gọi `reload`.

Nhưng **cache không làm `ServiceLoader` trở thành singleton factory toàn cục**: cache thuộc từng đối tượng `ServiceLoader`, không phải tất cả instances cho service ấy. Một `ServiceLoader.load(...)` khác có cache riêng.

### Với stream()

`stream()` duyệt các **`Provider<S>` descriptors**. Một lần xử lý stream có thể định vị provider và ghi nhận thông tin vào cache riêng của loader cho đường stream. `stream()` không yêu cầu gọi constructor chỉ để cung cấp `Provider.type()`.

Ví dụ:

~~~java
List<String> types = loader.stream()
        .map(p -> p.type().getName())
        .sorted()
        .toList();
~~~

Đây là fragment yêu cầu `List` và `loader` đã khai báo. Nó lấy **tên type**, không tự instantiate service object chỉ để thực thi `map(...type...)`. `sorted()` đòi tiêu thụ các descriptors cần thiết để sắp xếp, nên có thể buộc discovery của **toàn bộ** provider, mặc dù không gọi `get()`.

Nếu sau đó viết:

~~~java
List<Codec> instances = loader.stream()
        .map(ServiceLoader.Provider::get)
        .toList();
~~~

đây cũng là fragment. Bây giờ terminal operation tiêu thụ stream và **gọi `get()`** cho những phần tử được đi qua, nên có thể tạo provider objects.

### Không nhầm hai loại cache và identity

- **Iterator cache** gắn với những provider **instances** mà `iterator()` đã thực sự trả.
- **Stream cache** gắn với provider descriptions được định vị qua `stream()`; đừng đồng nhất nó với một singleton instance cache.
- **`Provider.get()` không hứa luôn trả đúng object như lần gọi `get()` trước**; không tự so sánh identity rồi dùng làm contract ứng dụng.
- Sau `reload()`, các cache được xóa và lần duyệt tiếp theo discovery lại; các object, streams hoặc descriptors mà **code bên ngoài còn giữ** không tự biến mất.
- `ServiceLoader` được tài liệu mô tả **không an toàn để dùng đồng thời tùy tiện trên nhiều thread**. Nếu hệ plugin nhiều thread cùng khám phá/reload, cần thiết kế đồng bộ/ownership rõ ràng hoặc dùng instance ServiceLoader theo context phù hợp.

## 6. reload(): dùng khi nào, tránh dùng sai khi nào?

`reload()` xóa các provider cache của **chính đối tượng ServiceLoader**:

~~~java
ServiceLoader<Codec> services = ServiceLoader.load(Codec.class);

// ... duyệt providers ...

services.reload();

// Sử dụng iterator() hoặc stream() MỚI để thấy cache đã xóa.
~~~

Đây là fragment. Những trường hợp có thể cần reload:

- Hệ thống phát hiện provider artifact mới mà **class loader được chọn đã có khả năng nhìn thấy**.
- Ứng dụng chủ động yêu cầu discovery lại metadata.
- Test có thay đổi nguồn provider được loader nhìn thấy và muốn reset cache giữa các lần duyệt.

**Điểm không được suy diễn từ `reload()`:**

1. Nó **không tự tạo class loader mới**, không thêm URL/JAR vào loader, không tạo module layer mới và không thay các quan hệ `requires`/`exports`/`opens`.
2. Nó **không unload** những Class hoặc service objects đã tạo trước đó.
3. Nó không bảo đảm sẽ tìm thấy provider mới nếu class loader/module layer hiện tại **không thể nhìn thấy** provider đó.
4. Nó không chuyển định nghĩa `Codec` đang được consumer dùng sang interface cùng tên của loader khác.
5. Những **iterator và stream đã tạo trước `reload()` nên bị bỏ**, không dùng tiếp. API có cơ chế fail-fast và có thể ném `ConcurrentModificationException` khi những iterator/stream cũ được tiêu thụ sau khi cache bị xóa.

Ví dụ xử lý lỗi đúng về vòng đời:

~~~java
Iterator<Codec> oldIterator = services.iterator();
services.reload();

// Đừng tiếp tục oldIterator: lấy iterator mới.
Iterator<Codec> newIterator = services.iterator();
~~~

Đây là fragment yêu cầu biến `services` tồn tại; lời gọi `newIterator` không bảo đảm có provider nếu metadata/source không phù hợp.

### findFirst() có liên quan gì?

`findFirst()` là tiện ích tương đương việc dùng iterator để lấy provider đầu tiên:

~~~java
Codec chosen = ServiceLoader.load(Codec.class)
        .findFirst()
        .orElseGet(DefaultCodec::new);
~~~

Đây là fragment giả định có `DefaultCodec implements Codec`; không phải chương trình độc lập. `findFirst()` **có thể instantiate** provider đầu tiên, không phải lựa chọn thay `stream().filter(p -> p.type()...)` khi ta muốn kiểm tra metadata trước.

## 7. Iterator hay stream nên chọn trong từng trường hợp?

| Nhu cầu | Cách dùng hợp lý | Lưu ý |
| --- | --- | --- |
| Chạy lần lượt mọi provider | `for (S s : loader)` / `iterator()` | Tạo instance khi duyệt; phù hợp xử lý từng service. |
| Chỉ cần một provider đầu tiên | `loader.findFirst()` | Thứ tự discovery không luôn ổn định với nhiều named modules. |
| Chỉ chọn provider mang annotation trên type | `loader.stream().filter(p -> p.type()...).map(Provider::get)` | Lọc trước khi tạo instance. |
| Liệt kê loại provider phục vụ diagnostics | `loader.stream().map(p -> p.type().getName())` | Không cần khởi tạo service object chỉ để in tên. |
| Sắp xếp providers theo type | `stream().sorted(comparing(p -> p.type().getName()))` | Sắp xếp buộc khám phá các phần tử cần thiết và không bảo đảm cùng lựa chọn khi provider set đổi. |
| Muốn tái khám phá sau thay đổi | `loader.reload()` rồi lấy iterator/stream mới | Đừng giữ stream/iterator cũ qua reload. |
| Cần lifecycle/singleton provider cụ thể | Tự quản lý instances qua registry của ứng dụng | Không coi `Provider.get()` là singleton contract. |

### Filter theo metadata: ví dụ an toàn về mặt ý tưởng

Giả sử các implementation được gắn annotation runtime `@CodecPriority` và service type có nhiều providers:

~~~java
List<Codec> selected = loader.stream()
        .filter(p -> p.type().isAnnotationPresent(CodecPriority.class))
        .map(ServiceLoader.Provider::get)
        .toList();
~~~

Đây là fragment chỉ minh họa lựa chọn; để chạy cần khai báo annotation `CodecPriority` với `@Retention(RUNTIME)`, service `Codec` và những providers phù hợp. Các provider không qua filter **không bị gọi `get()` từ pipeline này**. Nhưng việc định vị/kiểm tra class và metadata vẫn có thể phát sinh lỗi hoặc tốn chi phí.

**Factory caveat:** Nếu provider trong named module khai báo static factory, `p.type()` có thể là **return type của factory**. Annotation đặt trên factory class không nhất thiết được nhìn thấy bởi `p.type()`. Chọn metadata ở nơi mà ServiceLoader API thật sự cung cấp.

## 8. SPI discovery: classpath và named modules khác nhau

`ServiceLoader` không tự quét mọi class có `implements Codec`. Nó cần **đăng ký provider** theo quy tắc SPI.

### 8.1. Provider trên classpath / unnamed module

Một JAR/classpath provider thường có resource:

~~~text
META-INF/services/codec.api.Codec
~~~

Nội dung (UTF-8), ví dụ:

~~~text
codec.impl.Alpha
codec.impl.Beta
~~~

Đây là **minh họa file provider-configuration**. Muốn chạy một project classpath hoàn chỉnh phải có `Codec`, `Alpha`, `Beta` và resource nằm đúng vị trí trên classpath. Không phải file dùng trong demo named module ở mục 4.

Một provider line là **binary name**, không phải đường dẫn `.class`; có thể có comment bắt đầu bằng `#` và dòng trắng theo quy tắc API. Classpath provider phải có điều kiện tạo instance thích hợp, thông thường **public class với public no-arg constructor** và implement/extend service type. Không thể lấy class bất kỳ chỉ chứa một method tĩnh rồi xem như classpath provider hợp lệ theo cùng cách với provider factory của named module.

ServiceLoader sử dụng resource lookup (`ClassLoader.getResources(...)`) khi tìm provider-configuration trong unnamed modules. **Thứ tự các cấu hình** phụ thuộc thứ tự resource được loader tìm và thứ tự tên provider trong file; các tên duplicate được bỏ qua theo API. Không nên mong mọi runtime/classpath đều trả danh sách provider giống nhau nếu classpath hoặc class loader thay đổi.

### 8.2. Provider trong named module / module layer

Named module khai báo:

~~~java
module codec.demo {
    exports codec.api;
    uses codec.api.Codec;
    provides codec.api.Codec with codec.impl.Alpha;
}
~~~

Đây là metadata chính xác của **ví dụ chạy được**. Với consumer ở **named module**, khai báo `uses service.Type` là một điều kiện quan trọng khi sử dụng ServiceLoader từ module đó. Provider ở named module được định nghĩa bằng `provides ... with ...`; một module không nên khai báo provider thuộc một module khác.

Một provider trong named module có thể:

- Có provider constructor phù hợp, hoặc
- Có public static no-arg `provider()` factory method theo hợp đồng `ServiceLoader`.

Classpath provider-configuration là cơ chế dành cho unnamed modules và có các điều kiện khác; không mặc định dùng factory method đó cho provider trên classpath.

### 8.3. ServiceLoader.load(ModuleLayer, Class)

Khi chương trình tạo dynamic `ModuleLayer` cho plugin, API:

~~~java
ServiceLoader<MyService> services =
        ServiceLoader.load(pluginLayer, MyService.class);
~~~

là **fragment** yêu cầu `pluginLayer` và `MyService` đã được khai báo. Overload này khám phá provider trong **named modules** của layer được chọn và các parent layers theo quy tắc API; **không tìm provider ở unnamed modules** theo overload này.

Thứ tự quét là **layer được chỉ định trước, sau đó những parent layers** theo quy tắc duyệt của API. Thứ tự giữa các modules trong cùng layer không được định nghĩa; vì thế không chọn provider đầu tiên trong ứng dụng quan trọng mà không có tiêu chí ưu tiên rõ ràng.

### 8.4. Load bằng TCCL hay loader tường minh?

Hai overload sau có thể quan sát tập providers khác nhau:

~~~java
ServiceLoader<MyService> a =
        ServiceLoader.load(MyService.class);

ServiceLoader<MyService> b =
        ServiceLoader.load(MyService.class, pluginClassLoader);
~~~

Đây là fragment. Lời gọi `load(MyService.class)` dùng **thread context class loader (TCCL)**; lời gọi hai tham số dùng class loader đã chỉ định. Với thread pool, TCCL trên worker **không tự bằng TCCL của thread gửi công việc**, nên kết quả discovery có thể khác. Các hệ plugin có class loader riêng nên chọn cách cung cấp loader/mapping rõ ràng, tránh giữ ServiceLoader trong cache global qua nhiều deployment.

Dù chọn TCCL đúng, provider vẫn phải có **type identity tương thích** với interface `MyService` của consumer. Hai bản service interface cùng tên được định nghĩa bởi hai class loader khác nhau vẫn là hai kiểu JVM riêng; việc đảo thứ tự provider resource không sửa được split identity.

## 9. Lỗi xuất hiện ở iterator, stream và Provider.get

Không phải tất cả lỗi ServiceLoader nổ ngay khi gọi `ServiceLoader.load(...)`. Việc nạp/lọc/khởi tạo diễn ra lười nên exception thường xuất hiện **lúc bắt đầu tiêu thụ kết quả**.

| Thời điểm | Lỗi có thể phát sinh |
| --- | --- |
| `iterator().hasNext()` / `iterator().next()` | `ServiceConfigurationError` khi metadata/provider không hợp lệ, không nạp/instantiate được. |
| Terminal operation trên `stream()` | `ServiceConfigurationError` khi quá trình discovery, loading hoặc kiểm tra provider type gặp lỗi. |
| `Provider.get()` | `ServiceConfigurationError` nếu constructor/factory thất bại, trả null trong trường hợp factory, hoặc provider không thể instantiate. |
| Dùng iterator/stream cũ sau `reload()` | `ConcurrentModificationException` theo cơ chế fail-fast của API. |
| Provider class sử dụng API type khác defining loader | `ServiceConfigurationError` hoặc lỗi type/linkage liên quan, tùy nơi phát hiện bất nhất. |
| Provider được khai báo nhưng thiếu dependency | Có thể là `ServiceConfigurationError` với cause như `ClassNotFoundException`/`NoClassDefFoundError`, tùy tình huống. |

`ServiceConfigurationError` là một **Error**, không phải checked exception. Không nên bắt toàn bộ `Error` hoặc im lặng nuốt mọi lỗi để “bỏ qua provider hỏng”. Thường nên ghi **service name, provider name/type, class loader, module/layer, cause** rồi fail có kiểm soát. Theo API, một số lần duyệt có thể cố tiếp tục sau lỗi, nhưng **không bảo đảm luôn phục hồi được** khỏi cấu hình provider sai.

### Mẫu chẩn đoán tại boundary

Fragment sau giả định `loader` là `ServiceLoader<Codec>` đã tạo từ service tương thích:

~~~java
try {
    for (ServiceLoader.Provider<Codec> p :
            loader.stream().toList()) {

        Class<? extends Codec> type = p.type();

        System.out.println("Provider type: " + type.getName());
        System.out.println("Defining loader: " + type.getClassLoader());
        System.out.println("Module: " + type.getModule().getName());

        Codec instance = p.get();
        System.out.println("Instance: " + instance.id());
    }
} catch (java.util.ServiceConfigurationError error) {
    System.err.println("SPI discovery/creation failed: " + error);
}
~~~

Đây là **fragment** chứ không phải một chương trình độc lập. Ở project thực tế, nên phân biệt việc enumerate toàn bộ providers (qua `toList()`) với việc tạo instances (qua `get()`), và log cause chi tiết. `getModule().getName()` có thể trả `null` đối với **unnamed module**, không nên giả định luôn có tên.

Nếu class provider nạp thành công nhưng `serviceType.isAssignableFrom(providerType)` sai, cần kiểm tra **API JAR trùng** và defining loaders; sửa discovery một mình không làm hai interface cùng tên thành cùng type.

## 10. Performance và quản lý tài nguyên: lazy không đồng nghĩa miễn phí

Dù ServiceLoader lazy, những bước dưới đây vẫn có thể gây chi phí đáng kể:

- Tra cứu `META-INF/services` qua URLClassLoader có thể truy cập JAR, filesystem hoặc URL từ xa tùy cấu hình.
- Nạp metadata của nhiều provider types để làm filter/sort.
- Reflection/validation để xác nhận class implements service và được phép instantiate.
- Chạy static initialization hoặc constructor khi gọi `Provider.get()` / iterator, bao gồm I/O, tạo thread hoặc giữ cache do provider tự làm.
- `sorted(...)`, `toList()` hoặc phép duyệt toàn bộ có thể buộc discover tất cả providers, trong khi `findFirst()` có thể dừng sớm theo thứ tự discovery.

Khi chỉ cần chọn một implementation đủ điều kiện, một pipeline dựa trên `Provider.type()` rồi `findFirst()` sẽ tránh instantiate tất cả provider chỉ để đọc metadata. Nhưng **đừng phụ thuộc thứ tự first provider** nếu dùng nhiều named modules hoặc có yêu cầu ưu tiên nghiệp vụ: đặt tiêu chí rõ như annotation priority, tên hoặc config và cân nhắc xung đột.

ServiceLoader không sở hữu lifecycle của provider sau khi nó đã được chuyển cho caller. Nếu provider mở socket, thread pool hay native resource, hãy quản lý và đóng **theo hợp đồng service riêng**. `reload()` không gọi `close()` cho object cũ.

## 11. Những hiểu nhầm thường gặp

**“`ServiceLoader.stream()` trả luôn `Stream<Codec>`.”** Sai: nó trả `Stream<ServiceLoader.Provider<Codec>>`. Muốn instances cần `map(Provider::get)` hoặc đường iterator.

**“`Provider.type()` tạo object dịch vụ rồi lấy `getClass()`.”** Sai: nó trả provider type mà không cần instantiate service object. Tuy nhiên, việc định vị/load metadata vẫn có thể xảy ra.

**“`Provider.type()` luôn là class factory trong named module.”** Sai: nếu module dùng public static `provider()`, `type()` trả **return type của factory**, có thể khác class chứa factory.

**“Gọi `Provider.get()` hai lần chắc chắn cùng singleton.”** Không được bảo đảm. Nếu cần singleton hoặc lifecycle cụ thể, tự quản lý cache/object theo hợp đồng ứng dụng.

**“Iterator không có cache nên duyệt lại tạo provider mới.”** Sai: ServiceLoader cache những instances đã được trả bởi iterator; ví dụ Java 17 cho thấy lấy lại instance cached qua iterator mới của **cùng loader**.

**“`reload()` sẽ tự phát hiện JAR bất kỳ mới đặt vào ổ đĩa.”** Sai: nó chỉ xóa cache; class loader/module layer hiện tại phải nhìn thấy artifact, và điều kiện discovery vẫn phải đúng.

**“`findFirst()` luôn cho provider có ưu tiên cao nhất.”** Không. Thứ tự giữa các named modules có thể không xác định; dùng tiêu chí rõ nếu cần chọn một implementation tối ưu.

**“Mọi lỗi sẽ ném ngay từ `ServiceLoader.load`.”** Không. Discovery/instantiation lazy khiến lỗi thường phát sinh từ `hasNext`, `next`, terminal stream operation hoặc `Provider.get`.

**“ServiceLoader thread-safe, cứ chia sẻ một instance qua mọi worker.”** Không. Tài liệu API không bảo đảm dùng một ServiceLoader mutable đồng thời an toàn; phải đồng bộ hoặc có ownership rõ khi dùng/reload.

**“SPI classpath và JPMS module registration giống hệt nhau.”** Không. Unnamed modules chủ yếu dùng `META-INF/services`; named modules dùng `provides ... with ...`, cùng những điều kiện `uses`/factory/visibility tương ứng.

## 12. Checklist áp dụng trong project

1. Xác định **service type duy nhất** và nơi định nghĩa API contract.
2. Chọn cách đăng ký provider: `META-INF/services` cho classpath, `provides ... with ...` cho named module.
3. Nếu caller ở named module, khai báo `uses service.Type` theo yêu cầu.
4. Xác định **loader/layer dùng discovery** và TCCL khi API đọc context loader.
5. Dùng `iterator()` hoặc enhanced-for khi thật sự muốn **service instances**.
6. Dùng `stream()` với `Provider.type()` khi cần **lọc/kiểm tra metadata trước**.
7. Chỉ gọi `Provider.get()` sau khi đã quyết định lấy instance.
8. Đừng dựa vào identity của `Provider.get()` như một singleton guarantee.
9. Chỉ dùng `findFirst()` khi thứ tự provider phù hợp hoặc không quan trọng; nếu cần ưu tiên hãy sắp xếp/lọc bằng tiêu chí rõ.
10. Với `reload()`, bỏ iterator/stream cũ và hiểu rằng lifecycle của instances cũ vẫn do caller quản lý.
11. Bắt và báo đúng `ServiceConfigurationError` ở ranh giới khám phá/khởi tạo; không nuốt lỗi cấu hình hỏng.
12. Khi debug, in type, module, **defining class loader**, cause và vị trí provider metadata.
13. Tránh cache ServiceLoader global cho nhiều plugin/TCCL/deployments khác nhau.
14. Test một provider lỗi, provider thiếu dependency, provider constructor thất bại, filter metadata và discovery sau reload.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Kiểu phần tử của `ServiceLoader<Codec>.iterator()` là gì? Của `stream()` là gì?

**Đáp án:** Iterator trả `Codec` instances; stream trả `ServiceLoader.Provider<Codec>` descriptors.

**Câu 2.** Vì sao `stream().filter(p -> p.type()...).findFirst()` thường rẻ hơn duyệt iterator rồi kiểm tra `object.getClass()`?

**Đáp án:** Có thể lọc theo type metadata **trước khi khởi tạo object**, tránh constructor của provider bị loại. Discovery/type loading vẫn có chi phí.

**Câu 3.** `Provider.get()` có bảo đảm luôn trả cùng instance như một singleton không?

**Đáp án:** Không. Nó trả một instance hợp lệ, không có singleton identity guarantee cho mọi lần gọi.

**Câu 4.** Gọi lại `loader.iterator()` trên **cùng đối tượng ServiceLoader** có nhất thiết tạo mới tất cả provider instances không?

**Đáp án:** Không. Các instances đã load qua iterator được cache và được trả trước; những providers chưa load mới được tạo lười.

**Câu 5.** Vì sao gọi `reload()` rồi dùng iterator cũ là sai?

**Đáp án:** Reload xóa cache và làm stale iterator/stream; API có thể ném `ConcurrentModificationException` theo cơ chế fail-fast. Hãy tạo iterator/stream mới.

**Câu 6.** Một named module dùng provider factory có `public static Codec provider()`. `Provider.type()` trả type nào?

**Đáp án:** **Return type của method `provider()`**, theo ServiceLoader API, không nhất thiết là class chứa factory.

**Câu 7.** Một plugin có provider implements `api.Codec` nhưng host không chấp nhận subtype dù tên giống nhau. Điều gì cần kiểm tra?

**Đáp án:** **Defining class loader và identity** của interface `api.Codec` ở host/plugin; hai bản interface cùng tên do loader khác nhau định nghĩa không tương thích chỉ nhờ tên.

## Ghi nhớ

**`iterator()` làm việc với service instances, còn `stream()` làm việc với `ServiceLoader.Provider<S>` descriptors.** `Provider.type()` cho phép kiểm tra loại provider **trước khi instantiate**; `Provider.get()` mới trả instance. ServiceLoader hỗ trợ lazy discovery, cache và `reload`, nhưng cần tránh giả định về singleton, thứ tự giữa named modules hay khả năng đồng thời. Trong hệ plugin, lựa chọn **đúng service interface, class loader/module layer và đăng ký provider** quan trọng không kém lựa chọn iterator hay stream.

**Tài liệu chuẩn (Java SE 17):**

- `ServiceLoader` — iterator, stream, load, reload, findFirst, discovery, caching, errors: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- `ServiceLoader.Provider` — type và get: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html
- `ModuleLayer` — dynamic layers và class loader mapping: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html
- `ClassLoader` — resource lookup và type loading: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
