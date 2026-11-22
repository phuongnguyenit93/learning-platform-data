# ServiceLoader: Cache provider, reload và giới hạn dùng đồng thời

`java.util.ServiceLoader<S>` là công cụ Java để tìm các **service provider** triển khai một interface hoặc service class mà ứng dụng biết trước. Nó rất hữu ích trong kiến trúc SPI/plugin vì host có thể chỉ phụ thuộc vào một **hợp đồng dịch vụ**; các implementation được khai báo trong `META-INF/services` (classpath) hoặc `provides ... with ...` (JPMS).

Tuy nhiên, `ServiceLoader` không phải “mỗi lần gọi là quét lại mọi JAR rồi tạo object mới”, cũng không phải registry thread-safe hay hệ hot-reload tự động. Java 17 xác định ba đặc điểm quyết định:

1. **Provider được tìm và nạp theo nhu cầu; loader có cache.** Iterator mới sẽ đi qua các provider đã được cache trước khi tiếp tục khám phá provider còn lại. Trong đường iterator, những instance đã tạo được dùng lại.
2. **`reload()` xóa cache của chính `ServiceLoader`.** Việc duyệt lại có thể khám phá và khởi tạo provider mới; iterator/stream **đã lấy trước khi reload phải bỏ đi**. Nhưng `reload()` **không thay đổi những `Class<?>` đã được JVM định nghĩa**, không đóng class loader, không thay JAR trong tiến trình.
3. **Một `ServiceLoader` instance không an toàn khi nhiều thread cùng dùng.** Không đồng thời `iterator()`/`hasNext()`/`next()`/`stream()`/`reload()` trên cùng instance mà không có thiết kế đồng bộ bên ngoài. Thread safety của **provider object** là bài toán khác.

Bài học thuộc **Java core – classloader / Nạp dịch vụ**, tập trung chính xác vào **cache provider, reload và giới hạn dùng đồng thời**. Các ví dụ chạy được trên **JDK 17+**, giải thích rõ khi nào provider constructor chạy, thứ gì được cache, khi nào phải tạo loader mới và cách tổ chức lifecycle không giữ plugin cũ trong bộ nhớ.

## 1. Sơ đồ phân biệt những đối tượng dễ bị gọi chung là “loader”

Một kiến trúc plugin đơn giản:

```text
     HOST APPLICATION
  ┌─────────────────────────────────────┐
  │ Service API: spi.GreetingService    │
  │             │                       │
  │ ServiceLoader<GreetingService>      │
  │   ├─ provider discovery/cache       │
  │   └─ iterator()/stream()/reload()   │
  └─────────────┬───────────────────────┘
                │ dùng một ClassLoader để tra cứu
                ▼
  ┌─────────────────────────────────────┐
  │ ClassLoader (app/URLClassLoader)     │
  │   ├─ tìm META-INF/services/...      │
  │   ├─ load provider implementation   │
  │   └─ định danh runtime Class<?>     │
  └─────────────┬───────────────────────┘
                │
                ▼
  ┌─────────────────────────────────────┐
  │ Provider object(s)                  │
  │ impl.FriendlyService, ...           │
  │ Có state, constructor và lifecycle  │
  └─────────────────────────────────────┘
```

Ba thứ khác nhau:

- **`ServiceLoader<S>` object:** giữ ngữ cảnh tìm dịch vụ và cache provider; `reload` tác động lên **cache bên trong object này**.
- **`ClassLoader` object:** chịu trách nhiệm thấy resource/service descriptor và định nghĩa/nạp Java classes. `ServiceLoader.reload()` **không gọi cơ chế “unload/redefine” tùy ý** trên object này.
- **Provider instance:** object cụ thể do constructor hoặc provider factory method tạo. Nó có thể là stateless, mutable, giữ thread/socket/file handle, hoặc triển khai `AutoCloseable`. `ServiceLoader` không phải lifecycle manager tự gọi `close()` cho mọi provider.

Một interface API phải được host và provider resolve về **cùng runtime type**. Nếu loader plugin tự định nghĩa bản sao của `spi.GreetingService`, provider có thể không assignable với interface host dù binary name giống nhau.

## 2. Provider được tìm thế nào? Discovery khác instantiation

Có hai kiểu triển khai phổ biến.

**Classpath/unnamed module:** provider class được chỉ định trong một resource tên `META-INF/services/<binary-name-của-service>`. Ví dụ:

```text
META-INF/services/spi.GreetingService
```

Nội dung resource:

```text
impl.FriendlyService
```

Tên trong file là **binary name của implementation**, không phải tên file `.class`. File có thể có nhiều provider names, mỗi dòng một tên; Java 17 yêu cầu service-configuration file mã hóa **UTF-8**, hỗ trợ dòng trống và chú thích `#`.

**Named module (JPMS):** module khai báo:

```java
module com.example.plugin {
    requires com.example.api;
    provides spi.GreetingService with impl.FriendlyService;
}
```

Đây là **`module-info.java` minh họa**, chưa phải chương trình độc lập. Host module cần `uses spi.GreetingService;` khi gọi SPI discovery; các module export/readability và `ModuleLayer` phải được cấu hình hợp lệ. Named module có thể sử dụng một **public static provider() factory** trong những điều kiện Javadoc quy định, khác với classpath provider thường dùng public zero-argument constructor.

**Discovery không đồng nghĩa tạo instance:** khi có `ServiceLoader<GreetingService> loader = ServiceLoader.load(GreetingService.class)`, đừng mặc định mọi provider constructor đã chạy. Việc **iterator traversal**, `findFirst()` hoặc `Provider.get()` mới khiến cần đến những instance theo cơ chế tương ứng.

## 3. Cache nghĩa là gì đối với `iterator()`?

Java 17 Javadoc quy định provider được định vị/nạp/khởi tạo **lazily**. Khi dùng `iterator()`:

1. Iterator mới **trả các provider instances đã được cache** của loader đó trước, theo thứ tự chúng được nạp.
2. Sau phần cached, iterator tiếp tục **tìm những provider chưa được duyệt**, và khởi tạo chúng theo nhu cầu.
3. Những instances được tạo qua quá trình iterator traversal được **thêm vào cache**.
4. Một lần gọi `iterator()` khác trên **cùng `ServiceLoader`**, khi chưa `reload()`, có thể trả lại **chính các cached objects**.
5. Nếu đã `reload()`, cache cũ không được phát lại bởi lượt duyệt mới của loader ấy.

```text
ServiceLoader<GreetingService> L
  ├─ iterator #1
  │     ├─ provider A → tạo instance A1 → cache
  │     └─ provider B → chưa đụng đến → chưa cần tạo
  │
  ├─ iterator #2
  │     ├─ provider A → trả lại A1 từ cache
  │     └─ provider B → khi đến lượt, tạo B1 → cache
  │
  └─ reload()
        ├─ cache cleared
        └─ iterator mới → có thể tạo A2, B2 khi cần
```

**Cache không phải singleton toàn JVM.** Một `ServiceLoader` object khác có cache riêng. Ngay cả trên cùng class loader và cùng service type, việc gọi `ServiceLoader.load(...)` một lần nữa tạo **ServiceLoader instance mới** với cache riêng.

**Cache cũng không hứa provider thread-safe.** Nếu cùng một cached instance `A1` được đưa cho hai consumers, object ấy có thể vẫn có mutable state và phải được đồng bộ theo hợp đồng của implementation.

## 4. `findFirst()` và khả năng dùng lại instance

`findFirst()` (Java 9+) tương đương ý nghĩa “lấy provider đầu tiên qua iterator”. Trong trường hợp một service có đúng một provider được cấu hình và khởi tạo thành công:

```java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

GreetingService first = loader.findFirst().orElseThrow();
GreetingService again = loader.findFirst().orElseThrow();
System.out.println(first == again);
```

Đây là **snippet minh họa** cần import `java.util.ServiceLoader` và service interface `GreetingService`. Kết quả là `true` khi hai lần tìm cùng cached provider qua iterator của **cùng loader**, chưa reload.

**Không lẫn cache với thứ tự lựa chọn:** nếu có nhiều providers, provider “đầu tiên” phụ thuộc discovery order theo classpath/service files hoặc module ordering. Một số thứ tự trong JPMS **không được đặc tả**. Nếu ứng dụng cần chọn provider theo độ ưu tiên, hãy thiết kế metadata/selection rules rõ ràng, đừng mặc định tên class đầu tiên theo bảng chữ cái.

`findFirst()` cũng có thể trả `Optional.empty()` khi không có provider; và có thể ném `ServiceConfigurationError` nếu cấu hình/provider bị lỗi. Nó không âm thầm chuyển mọi lỗi thành empty.

## 5. Thực hành A — cache trước reload, object mới sau reload

Ta dựng đúng **một service và một provider**, để output không phụ thuộc thứ tự khám phá nhiều JAR. Chương trình tạo một `ServiceLoader`, lấy provider hai lần, `reload` và lấy lại.

Cây tệp:

```text
service-cache-lab/
├── src/
│   ├── api/spi/GreetingService.java
│   ├── provider/impl/FriendlyService.java
│   └── host/demo/CacheDemo.java
├── api-out/       (javac tạo)
├── provider-out/  (javac và service descriptor)
└── host-out/      (javac tạo)
```

**Tệp `src/api/spi/GreetingService.java`:**

```java
package spi;

public interface GreetingService {
    String hello(String name);
}
```

**Tệp `src/provider/impl/FriendlyService.java`:**

```java
package impl;

import spi.GreetingService;

public final class FriendlyService implements GreetingService {
    private static int constructions;

    public FriendlyService() {
        int number = ++constructions;
        System.out.println("provider ctor #" + number);
    }

    @Override
    public String hello(String name) {
        return "Hello, " + name;
    }
}
```

Biến static `constructions` phục vụ **quan sát trong demo đơn luồng**, không phải counter thread-safe dùng trong production. Method `hello` không ghi mutable state nên có thể dùng như operation stateless trong bài tập.

**Tệp `src/host/demo/CacheDemo.java`:**

```java
package demo;

import spi.GreetingService;
import java.util.ServiceLoader;

public final class CacheDemo {
    public static void main(String[] args) {
        ServiceLoader<GreetingService> loader =
                ServiceLoader.load(GreetingService.class);

        GreetingService first =
                loader.findFirst().orElseThrow();
        GreetingService second =
                loader.findFirst().orElseThrow();

        System.out.println("before reload same object=" +
                (first == second));
        System.out.println("first result=" + first.hello("Java"));

        loader.reload();

        GreetingService after =
                loader.findFirst().orElseThrow();
        System.out.println("after reload same object=" +
                (first == after));
        System.out.println("after reload same class=" +
                (first.getClass() == after.getClass()));
        System.out.println("after result=" + after.hello("Java"));
    }
}
```

Biên dịch từ thư mục `service-cache-lab` bằng JDK 17+:

```sh
javac --release 17 -d api-out src/api/spi/GreetingService.java
javac --release 17 -cp api-out -d provider-out src/provider/impl/FriendlyService.java
javac --release 17 -cp api-out -d host-out src/host/demo/CacheDemo.java
```

**Bắt buộc tạo service descriptor** ở `provider-out/META-INF/services/spi.GreetingService`. Trên **Windows PowerShell**:

```powershell
New-Item -ItemType Directory -Force provider-out\META-INF\services | Out-Null
Set-Content -Path provider-out\META-INF\services\spi.GreetingService -Value "impl.FriendlyService" -Encoding Ascii
```

Trên **Linux/macOS**:

```sh
mkdir -p provider-out/META-INF/services
printf 'impl.FriendlyService\n' > provider-out/META-INF/services/spi.GreetingService
```

Ở đây tên provider và service chỉ có ASCII nên file tạo ở encoding ASCII cũng là UTF-8 hợp lệ, đáp ứng Javadoc.

Chạy trên **Windows** (phân tách classpath bằng `;`):

```powershell
java -cp "host-out;api-out;provider-out" demo.CacheDemo
```

Chạy trên **Linux/macOS** (phân tách bằng `:`):

```sh
java -cp "host-out:api-out:provider-out" demo.CacheDemo
```

**Stdout trong một tiến trình JVM mới:**

```text
provider ctor #1
before reload same object=true
first result=Hello, Java
provider ctor #2
after reload same object=false
after reload same class=true
after result=Hello, Java
```

### Giải thích chính xác từng kết quả

- Constructor in `#1` vì `findFirst()` đầu tiên buộc khởi tạo provider instance đầu tiên.
- `findFirst()` thứ hai từ **cùng `ServiceLoader`** nhận object cached; không gọi constructor lần nữa.
- `reload()` xóa cache provider của chính loader; `findFirst()` kế tiếp duyệt lại và tạo object mới, constructor in `#2`.
- `first == after` bằng `false` vì đây là hai instance.
- `first.getClass() == after.getClass()` bằng `true` vì ta **không thay class loader**, không định nghĩa lại class; chỉ tạo instance mới của **cùng runtime provider class**.
- `reload()` không gọi `close()` cho object `first`. Biến `first` vẫn giữ tham chiếu đến object cũ và hoàn toàn có thể gọi `first.hello(...)` sau reload nếu API/lifecycle của ứng dụng cho phép.

**Bài học:** reload **provider cache** khác với reload **class definition**. Nó không thay source JAR, không cập nhật bytecode của class đã loaded và không reset static field `constructions` về 0.

## 6. Những thứ `reload()` không thực hiện

Khi gọi:

```java
serviceLoader.reload();
```

Đây là snippet cần `serviceLoader` đã khai báo. Phương thức có tác dụng **xóa provider cache của `ServiceLoader` ấy** để các lần iterator/stream tiếp theo thực hiện discovery lazily từ đầu.

Nó **không**:

- Ép JVM **unload** provider classes đã được load.
- Định nghĩa lại bytecode của các classes đã được định nghĩa trong cùng defining loader.
- Thay `ClassLoader` object, `ModuleLayer` hoặc TCCL ngầm.
- Đổi đường dẫn `META-INF/services` nếu class loader không được cấu hình để thấy nguồn mới.
- Gọi `close()`/`stop()` trên provider objects đã phát cho host.
- Ngắt các tasks đang giữ provider instances cũ.
- Bảo đảm một JAR mới bị chép đè sẽ thay thế implementation của class đã loaded.
- Tạo một “atomic switchover” an toàn giữa consumers trên nhiều threads.
- Làm cho `ServiceLoader` thread-safe.

Nếu hệ thống cần **plugin hot reload**, phải xử lý **plugin lifecycle, class loader mới, discovery scope, dependency identity và references**. `reload()` chỉ là một bước có thể hữu ích trong trường hợp provider discovery có thay đổi mà classloader hiện tại thực sự nhìn thấy được.

### `reload` vẫn có ích khi nào?

Ví dụ, class loader hoặc module configuration được cập nhật theo cơ chế được hỗ trợ và **nguồn discovery của cùng ServiceLoader context** có thể nhìn thấy provider chưa từng được khám phá; `reload` buộc lần duyệt sau quét lại. Nhưng nếu class loader đã load `impl.Plugin` từ JAR phiên bản cũ, `reload` **không biến `impl.Plugin` thành runtime class khác**.

## 7. Iterator cũ sau `reload()`: phải bỏ, không tiếp tục dùng

Javadoc Java 17 nêu rõ: iterator được lấy từ `ServiceLoader.iterator()` **trước reload** không còn dùng được sau khi cache bị xóa. Các phương thức `hasNext()` và `next()` có thể ném **`ConcurrentModificationException`** theo cơ chế fail-fast.

```text
ServiceLoader L
   │
   ├─ Iterator old = L.iterator()
   │
   ├─ old.hasNext()          → hoạt động khi chưa reload
   │
   ├─ L.reload()             → provider cache cleared
   │
   ├─ old.hasNext()/next()   → ConcurrentModificationException
   │
   └─ Iterator fresh = L.iterator()
                              → discovery mới, từ cache mới
```

**Tên `ConcurrentModificationException` không đồng nghĩa nhất thiết có hai threads.** Ngay cả một thread gọi `reload()` rồi tiếp tục dùng iterator cũ cũng có thể gặp exception. Đó là **invalidation của iterator**, khác với race do nhiều threads thực thi.

Không nên bắt exception này rồi **tiếp tục dùng old iterator**. Hãy tạo **iterator mới** sau reload, và quy định vùng ownership rõ ràng.

## 8. Thực hành B — minh họa iterator fail-fast sau reload

Giữ lại service, provider, descriptor và các thư mục `api-out`, `provider-out` từ thực hành A. Thêm tệp **`src/host/demo/IteratorDemo.java`**:

```java
package demo;

import spi.GreetingService;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.ServiceLoader;

public final class IteratorDemo {
    public static void main(String[] args) {
        ServiceLoader<GreetingService> loader =
                ServiceLoader.load(GreetingService.class);

        Iterator<GreetingService> old = loader.iterator();
        System.out.println("old has provider=" + old.hasNext());

        loader.reload();

        try {
            old.hasNext();
            System.out.println("old iterator invalidated=false");
        } catch (ConcurrentModificationException expected) {
            System.out.println("old iterator invalidated=true");
        }

        GreetingService fresh =
                loader.findFirst().orElseThrow();
        System.out.println("fresh result=" + fresh.hello("B"));
    }
}
```

Biên dịch:

```sh
javac --release 17 -cp api-out -d host-out src/host/demo/IteratorDemo.java
```

Chạy trên Windows:

```powershell
java -cp "host-out;api-out;provider-out" demo.IteratorDemo
```

Hoặc Linux/macOS:

```sh
java -cp "host-out:api-out:provider-out" demo.IteratorDemo
```

**Stdout với đúng một provider:**

```text
old has provider=true
old iterator invalidated=true
provider ctor #1
fresh result=Hello, B
```

`old.hasNext()` trước reload xác định provider tồn tại nhưng **không cần tạo instance** của nó; constructor được gọi sau đó khi `findFirst()` lấy fresh provider. Vì chương trình chạy ở **một JVM mới**, bộ đếm constructor static bắt đầu lại và in `#1`.

**Đừng khái quát mọi `hasNext()` là vô hại:** quá trình lazy discovery có thể cần đọc descriptor và load provider metadata; lỗi `ServiceConfigurationError` có thể phát sinh ở `hasNext()` hoặc `next()` tùy tình huống. Chỉ nói rằng ví dụ này không instantiate provider bằng `old.hasNext()`.

## 9. `stream()` và `ServiceLoader.Provider<S>` khác iterator ra sao?

Java 9+ có:

```java
ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

loader.stream()
      .filter(provider -> provider.type().getName()
              .startsWith("impl."))
      .map(ServiceLoader.Provider::get)
      .forEach(service ->
              System.out.println(service.hello("Java")));
```

Đây là **snippet**, cần imports cho `ServiceLoader` và `GreetingService`. `stream()` cung cấp các **`Provider<S>` descriptors**:

- `provider.type()` trả provider type để xét metadata/annotations mà chưa phải tạo service instance.
- `provider.get()` trả một instance của provider; với named modules, provider factory method có thể được dùng.
- `stream()` cũng **lazy**: terminal operation mới thực sự duyệt.
- `ServiceLoader` có cơ chế **cache providers đã được stream khám phá**; Javadoc mô tả xử lý các cached providers trước khi tìm những provider còn lại.
- **Không suy luận rằng gọi `Provider.get()` nhiều lần luôn trả cùng singleton instance.** `Provider.get()` là API tạo/nhận một instance theo provider implementation; Javadoc không hứa cached-instance identity tương tự iterator traversal.
- Với các service providers trong named modules, `Provider.type()` có thể phản ánh return type của provider factory method, không nhất thiết provider factory class itself.

### Cache của `stream` không nên bị đồng nhất với cache instance của `iterator`

Iterator dùng cache instance phục vụ việc duyệt `S`. Stream duyệt `Provider<S>` descriptors và chỉ khi gọi `Provider.get()` mới lấy instance. Hãy coi **caching behavior được Javadoc ghi theo từng API**; đừng phụ thuộc một chi tiết nội bộ rằng tất cả provider instances phát qua `stream` và `iterator` đều có identity nhất định.

Nếu mục tiêu là **một service object dùng lặp lại**, hãy lấy instance đúng một lần, đặt nó trong registry do ứng dụng sở hữu, sau đó quản lý concurrency/lifecycle của registry ấy.

### Stream cũ sau reload

Javadoc cũng yêu cầu **bỏ stream đã lấy trước reload**. `spliterator` nguồn của stream có hành vi fail-fast nếu cache đã được clear và có thể ném `ConcurrentModificationException`. Không gọi `reload()` giữa một stream pipeline đang được tiêu thụ hoặc giữa phần tạo stream và terminal operation; tạo stream mới sau reload.

## 10. `ServiceLoader` không thread-safe: hiểu đúng phạm vi cảnh báo

Java 17 Javadoc tuyên bố rõ: **instances of `ServiceLoader` are not safe for use by multiple concurrent threads**.

Điều này là cảnh báo về **chính `ServiceLoader<S>` object**, vì nó có cache và trạng thái duyệt lazy, có thể bị thay đổi khi các calls tương tác. Những cặp thao tác đáng tránh:

- Thread A duyệt `for (S s : loader)` trong khi thread B gọi `loader.reload()`.
- Hai threads cùng dùng **một `ServiceLoader`** và đồng thời mở/tiến hành hai iterators chưa được phối hợp.
- Một thread dùng `stream()` và thread khác làm thay đổi cache bằng iteration/reload.
- Lưu một `ServiceLoader` VM-wide rồi để các tenants/applications với TCCL khác nhau truy cập chung.
- Dùng `parallel()` trực tiếp trên stream của `ServiceLoader` để khám phá provider trong khi không xét thread-safety.

Ngay cả khi một lần chạy tình cờ không báo lỗi, điều đó **không biến `ServiceLoader` thành thread-safe**.

Nhưng có một ranh giới khác: **provider implementation có thread-safe hay không**. Sau khi host đã chọn một `GreetingService` instance, việc hai threads gọi `service.hello(...)` đồng thời có an toàn không phụ thuộc **implementation contract**, không phụ thuộc `ServiceLoader` cache.

Do đó phân biệt:

```text
ServiceLoader object  ── không thread-safe khi truy cập đồng thời
        │
        ▼
Provider instance    ── có thể thread-safe hoặc không; phải xem contract
        │
        ▼
Business operation   ── cần bảo vệ mutable state nếu có
```

## 11. Ba hướng xử lý concurrency hợp lý

### Cách A: Khởi tạo trên một thread, snapshot rồi mới phân phát

1. Tạo và duyệt `ServiceLoader` trong một giai đoạn discovery **tuần tự**.
2. Lưu các provider instances hoặc provider factories vào một danh sách/registry có ownership rõ ràng.
3. Công bố snapshot **bất biến về cấu trúc** cho worker threads.
4. Chỉ gọi provider instance đồng thời nếu chính provider **được thiết kế thread-safe**; nếu không, bảo vệ bằng lock hoặc tạo instance riêng cho mỗi worker.

Với service stateless, đây thường là cách đơn giản và hiệu quả.

### Cách B: Đồng bộ toàn bộ tương tác với cùng ServiceLoader

Ví dụ:

```java
final Object guard = new Object();
final ServiceLoader<GreetingService> loader =
        ServiceLoader.load(GreetingService.class);

synchronized (guard) {
    for (GreetingService service : loader) {
        // Đưa kết quả vào registry nội bộ.
    }
}
```

Đây là **snippet**, không phải chương trình độc lập. **Mọi đường gọi `iterator`, `stream`, `reload` đối với cùng loader phải tuân cùng chính sách bảo vệ**. Không được khóa riêng lúc lấy `Iterator` nhưng lại thả khóa rồi duyệt ở thread khác — trạng thái lazy còn tiếp tục bị thay đổi tại `hasNext/next`.

Đồng bộ cũng **không tự bảo vệ** những provider objects đã trao cho consumers; đó là lớp concurrency khác.

### Cách C: Mỗi công việc tạo ServiceLoader riêng

Nếu không cần chia sẻ cache, các tasks có thể dùng **ServiceLoader instances riêng** với cùng service type và loader được cấu hình phù hợp. Điều này tránh dùng chung trạng thái ServiceLoader, nhưng có thể tạo nhiều provider instances và tăng chi phí discovery. Không coi các providers là thread-safe chỉ vì ServiceLoader không bị dùng chung.

**Khuyến nghị theo ngữ cảnh:** đối với ứng dụng có provider lifecycle dài, thường nên làm **discovery một lần**, xây immutable registry và quản lý thay thế version bằng cơ chế rõ ràng thay vì gọi `ServiceLoader` đồng thời trên mỗi request.

## 12. Thực hành C — snapshot tuần tự, gọi provider trên hai worker threads

Dùng lại `GreetingService`, `FriendlyService` và descriptor từ thực hành A. Tệp mới **`src/host/demo/SnapshotDemo.java`**:

```java
package demo;

import spi.GreetingService;
import java.util.ArrayList;
import java.util.List;
import java.util.ServiceLoader;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public final class SnapshotDemo {
    public static void main(String[] args) throws Exception {
        ServiceLoader<GreetingService> loader =
                ServiceLoader.load(GreetingService.class);

        List<GreetingService> found = new ArrayList<>();
        for (GreetingService provider : loader) {
            found.add(provider);
        }
        List<GreetingService> snapshot = List.copyOf(found);

        // Chỉ sau khi discovery xong mới chạy tác vụ đồng thời.
        GreetingService service = snapshot.get(0);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> a =
                    pool.submit(() -> service.hello("A"));
            Future<String> b =
                    pool.submit(() -> service.hello("B"));

            System.out.println("job A=" + a.get());
            System.out.println("job B=" + b.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch:

```sh
javac --release 17 -cp api-out -d host-out src/host/demo/SnapshotDemo.java
```

Chạy Windows:

```powershell
java -cp "host-out;api-out;provider-out" demo.SnapshotDemo
```

Chạy Linux/macOS:

```sh
java -cp "host-out:api-out:provider-out" demo.SnapshotDemo
```

**Stdout:**

```text
provider ctor #1
job A=Hello, A
job B=Hello, B
```

- Provider được khởi tạo trong **main thread** khi duyệt `loader`; một provider nên chỉ in một constructor marker.
- `List.copyOf` tạo danh sách bất biến về cấu trúc. Nó **không tự biến nội dung provider thành immutable hay thread-safe**.
- Hai workers gọi method `hello` của **cùng provider instance**. Bài tập này an toàn vì `FriendlyService.hello` không thay đổi shared state; constructor counter không bị thay đổi ở những calls ấy.
- Hai futures được chờ/in theo **thứ tự A rồi B**, nên stdout được xác định mặc dù hai tasks có thể thực sự chạy theo thứ tự bất kỳ.
- `ServiceLoader` **không bị gọi bởi worker threads**. Đây là điểm chính của chiến lược snapshot, không phải dùng `synchronized` bên trong provider một cách tình cờ.

Nếu service là stateful (ví dụ counter mutable hoặc dùng non-thread-safe parser), cần thiết kế **instance per task, pooling, synchronization**, hoặc serial executor ở lớp provider. Snapshot chỉ ngăn race trên provider discovery/cache.

## 13. `reload()` và concurrency không tạo atomic hot-swap

Giả sử host đang chạy request qua `oldProvider`. Một quản trị viên gọi `serviceLoader.reload()` rồi chọn `newProvider`. Điều gì xảy ra?

- `reload()` **không thu hồi** object `oldProvider` khỏi những threads đã giữ reference.
- Threads đang gọi method của `oldProvider` vẫn có thể tiếp tục dùng nó.
- Nếu provider sở hữu socket/file/thread, `reload()` không gọi cleanup.
- Nếu các consumers đọc trực tiếp một mutable list được thay đổi đồng thời, có thể thấy trạng thái không nhất quán.
- Nếu reload xảy ra trong khi iterator/stream cũ đang duyệt, có thể thấy `ConcurrentModificationException` hoặc race ngoài hợp đồng thread-safety.

Một cách thiết kế registry:

```text
  Giai đoạn discovery mới (tuần tự, loader riêng khi cần)
           │
           ▼
  Validate tất cả provider candidates
           │
           ▼
  Tạo snapshot registry mới đầy đủ
           │
           ▼
  Công bố snapshot mới bằng một phép gán atomic
           │
           ▼
  Dừng nhận request mới vào registry cũ
           │
           ▼
  Chờ/huỷ các tác vụ cũ theo lifecycle contract
           │
           ▼
  Close provider resources và loader cũ khi an toàn
```

Sơ đồ này là **pattern kiến trúc**, không phải guarantee mà `ServiceLoader` cung cấp. Có thể dùng `AtomicReference<Registry>` hoặc volatile reference cho một registry immutable và giao thức quiescence/active request tracking. **Atomic publish** giải quyết visibility của reference mới, còn việc hoàn tất công việc trên provider cũ vẫn cần lifecycle protocol.

## 14. ClassLoader mới khác hoàn toàn `ServiceLoader.reload()`

Hai tiến trình sau không tương đương:

**A. Cùng ClassLoader, gọi reload:**

```text
URLClassLoader L1 defines impl.FriendlyService → Class C1
ServiceLoader S1 (using L1)
  → first provider instance P1
  → S1.reload()
  → next provider instance P2

P1 != P2
P1.getClass() == P2.getClass()    (cùng C1)
```

**B. ClassLoader mới, discovery mới:**

```text
URLClassLoader L1 defines impl.FriendlyService → Class C1
URLClassLoader L2 defines impl.FriendlyService → Class C2

C1 != C2                        (khác defining loader)
```

Trường hợp B thường được dùng để nạp **phiên bản plugin khác** sau khi đã thay artifact và có loader mới. Nhưng cần shared API identity: `spi.GreetingService` ở host và hai plugins phải resolve về **cùng runtime interface Class<?>**, thường qua parent API loader.

Một lưu ý: nếu parent đã định nghĩa `impl.FriendlyService` và `URLClassLoader` dùng parent-first, cả L1 và L2 có thể trả **cùng class của parent** thay vì tự define C1/C2. Vì thế integration test phải **không đặt provider implementation trên host classpath** khi muốn kiểm thử per-plugin class loader.

## 15. Thực hành D — hai ClassLoader và reload cache trong một loader

Dùng **chính `provider-out`** từ thực hành A, nhưng lần này **không đặt nó trên application classpath**. Chỉ có host và shared API ở application loader; hai child `URLClassLoader` cùng được cấp URL tới `provider-out`.

Tệp **`src/host/demo/LoaderIdentityDemo.java`**:

```java
package demo;

import spi.GreetingService;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ServiceLoader;

public final class LoaderIdentityDemo {
    public static void main(String[] args) throws Exception {
        URL location = Path.of("provider-out")
                .toAbsolutePath().toUri().toURL();
        URL[] urls = { location };
        ClassLoader sharedApiLoader =
                GreetingService.class.getClassLoader();

        try (URLClassLoader firstLoader =
                     new URLClassLoader(urls, sharedApiLoader);
             URLClassLoader secondLoader =
                     new URLClassLoader(urls, sharedApiLoader)) {

            ServiceLoader<GreetingService> firstServices =
                    ServiceLoader.load(
                            GreetingService.class, firstLoader);
            ServiceLoader<GreetingService> secondServices =
                    ServiceLoader.load(
                            GreetingService.class, secondLoader);

            GreetingService a =
                    firstServices.findFirst().orElseThrow();
            GreetingService b =
                    secondServices.findFirst().orElseThrow();

            System.out.println("same provider Class across loaders=" +
                    (a.getClass() == b.getClass()));
            System.out.println("a defined by first=" +
                    (a.getClass().getClassLoader() == firstLoader));
            System.out.println("b defined by second=" +
                    (b.getClass().getClassLoader() == secondLoader));
            System.out.println("both implement host API=" +
                    (GreetingService.class.isInstance(a)
                            && GreetingService.class.isInstance(b)));

            firstServices.reload();
            GreetingService a2 =
                    firstServices.findFirst().orElseThrow();

            System.out.println("same object after reload=" +
                    (a == a2));
            System.out.println("same Class after reload=" +
                    (a.getClass() == a2.getClass()));
        }
    }
}
```

Biên dịch (đọc shared API từ `api-out`, không cần provider implementation tại compile time):

```sh
javac --release 17 -cp api-out -d host-out src/host/demo/LoaderIdentityDemo.java
```

**Windows:**

```powershell
java -cp "host-out;api-out" demo.LoaderIdentityDemo
```

**Linux/macOS:**

```sh
java -cp "host-out:api-out" demo.LoaderIdentityDemo
```

**Stdout trong cấu hình đã nêu:**

```text
provider ctor #1
provider ctor #1
same provider Class across loaders=false
a defined by first=true
b defined by second=true
both implement host API=true
provider ctor #2
same object after reload=false
same Class after reload=true
```

**Tại sao constructor cùng in `#1` hai lần?** Static field `constructions` thuộc runtime class `impl.FriendlyService` mà **mỗi defining loader riêng** đã định nghĩa. Vì hai lớp có class identity khác nhau, mỗi lớp bắt đầu static counter từ 0. Khi reload `firstServices`, class từ first loader **không đổi**, nên constructor lần tiếp theo của **lớp thứ nhất** in `#2`.

`ServiceLoader.load(GreetingService.class, firstLoader)` nhận loader tường minh để tìm descriptor/provider, nhưng provider tiếp tục delegate interface `spi.GreetingService` lên shared parent. Vì thế host cast/API assignability vẫn đúng.

**Đóng loader:** `try-with-resources` đóng `URLClassLoader` resources khi block kết thúc; không bảo đảm JVM unload ngay object/classes còn references. Khi ứng dụng thật có provider đang phục vụ request, **đừng close class loader trước khi lifecycle kết thúc**.

## 16. Thứ tự provider và cache: không thiết kế dựa trên thứ tự ngầm

Với classpath providers, thứ tự khám phá thường theo:

- thứ tự mà class loader `getResources("META-INF/services/...")` trả service configuration files;
- thứ tự các provider names trong mỗi descriptor;
- xử lý trùng provider names theo Javadoc.

Với named modules, `ServiceLoader` có quy tắc riêng theo module/layer và một số thứ tự **không được xác định**. Vì vậy không nên giả định `findFirst()` luôn chọn “provider tốt nhất” hoặc toàn bộ modules được duyệt theo tên.

Nếu ứng dụng có nhiều providers và cần ưu tiên:

1. Mỗi provider khai báo capability/priority dưới một **contract rõ ràng**.
2. Discovery tất cả candidates tuần tự.
3. Xác thực type/capability.
4. Sắp xếp/chọn theo tiêu chí của ứng dụng, có xử lý trường hợp trùng mức ưu tiên.
5. Cache selected instance/registry sau khi đã quyết định.

Đừng để thứ tự JAR files tình cờ quyết định provider dành cho giao dịch nhạy cảm.

## 17. `ServiceConfigurationError` trong quá trình lazy loading

Do ServiceLoader **lazy**, lỗi không nhất thiết phát sinh ngay khi gọi `ServiceLoader.load(...)`. Javadoc chỉ rõ:

- `Iterator.hasNext()` và `next()` có thể ném `ServiceConfigurationError` khi đọc descriptor, nạp provider hoặc tạo instance.
- Stream operations có thể ném lỗi tại **thời điểm thực sự duyệt**, và `Provider.get()` có thể lỗi lúc tạo provider.
- `findFirst()` cũng có thể báo lỗi khi provider đầu tiên không hợp lệ.
- Nếu provider-configuration file sai định dạng, tên class không tồn tại, provider không assignable vào đúng service type, hoặc constructor/factory thất bại, error có thể mang cause liên quan.

Một số lỗi hay gặp:

| Triệu chứng | Khả năng nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy provider, `findFirst()` empty | Descriptor/module declaration không được runtime loader nhìn thấy | Kiểm tra `META-INF/services`, JAR entries, TCCL/explicit loader, JPMS |
| `ServiceConfigurationError: Provider ... not found` | Provider class không có ở classpath/module scope | Kiểm tra binary name, JAR, loader URL/delegation |
| Provider not a subtype | Host và plugin dùng hai runtime copies của service API hoặc provider khai báo sai | So `Class<?>`, defining loader, shared API graph |
| Constructor/factory lỗi | Provider init/constructor method ném exception hoặc cấu hình không hợp lệ | Xem cause, log provider identity, sửa lifecycle |
| Iterator `ConcurrentModificationException` sau reload | Đang dùng iterator cũ bị invalidated | Bỏ iterator cũ, tạo iterator mới sau reload |
| Concurrent iteration/reload thất thường | Một `ServiceLoader` bị truy cập từ nhiều threads | Serialize discovery/reload hoặc snapshot/ownership |
| Provider “không đổi” dù update JAR | ClassLoader đã định nghĩa class cũ; reload chỉ clear provider cache | Triển khai loader/version lifecycle, không gọi reload như redefine |
| Memory leak khi reload plugin liên tục | Host giữ provider instance, registry, ServiceLoader, ClassLoader, TCCL hoặc threads | Unregister callbacks, stop tasks, close resources, release references |

### Không nuốt lỗi cấu hình một cách mù quáng

Không nên:

```java
try {
    return loader.findFirst().orElse(null);
} catch (Throwable ignored) {
    return null;
}
```

Đây là **mẫu sai**, không phải method độc lập; nó nuốt cả lỗi class linking/JVM và đánh đồng “không có provider” với “provider broken”. `ServiceConfigurationError` là một `Error` có ý nghĩa cấu hình runtime nghiêm trọng. Nếu ứng dụng muốn optional plugin, có thể bắt riêng lỗi đó ở tầng **quản lý plugin**, giữ context/cause và chính sách fail-fast hoặc skip provider được xác định; đừng giả định tiếp tục iterator sau lỗi luôn phục hồi hoàn hảo.

## 18. TCCL, loader tường minh và giới hạn cache cross-application

`ServiceLoader.load(ServiceType.class)` dùng **thread context class loader (TCCL)** tại lúc tạo ServiceLoader:

```java
ServiceLoader<GreetingService> viaContext =
        ServiceLoader.load(GreetingService.class);

ServiceLoader<GreetingService> explicit =
        ServiceLoader.load(GreetingService.class, pluginLoader);
```

Đây là **snippets**, cần biến `pluginLoader` và interface đã khai báo. Trong container, hai threads có thể có TCCL khác nhau và nhìn thấy providers khác nhau.

Javadoc lưu ý **không nên cache `ServiceLoader.load(service)` VM-wide** ở môi trường nhiều ứng dụng: đối tượng ấy giữ **ngữ cảnh discovery** gắn với TCCL lúc tạo, provider caches có thể không phù hợp với ứng dụng khác; còn có nguy cơ giữ class loader sống.

**Không hiểu nhầm TCCL là defining loader.** TCCL chọn ngữ cảnh khám phá; provider class thực sự được định nghĩa bởi loader nào còn tùy delegation, module graph và URL sources. Nếu host truyền service interface `Class<?>` do host định nghĩa, loader plugin vẫn phải resolve về đúng shared API identity.

Các API liên quan:

- `ServiceLoader.load(Class<S> service)`: dùng TCCL.
- `ServiceLoader.load(Class<S> service, ClassLoader loader)`: chọn loader tường minh.
- `ServiceLoader.load(ModuleLayer layer, Class<S> service)`: khám phá named-module providers trong layer/ancestors; **không** lấy unnamed-module classpath providers như overload theo class loader.
- `ServiceLoader.loadInstalled(service)`: dùng platform loader; không thay thế cách load plugin trên application classpath.

**Không dùng `reload()` để “đổi TCCL” của một ServiceLoader đã tạo.** Nếu ngữ cảnh loader/layer cần thay, tạo một **ServiceLoader mới** với ngữ cảnh mới.

## 19. Provider lifecycle không do ServiceLoader quản lý thay bạn

Provider có thể chỉ là pure function, cũng có thể giữ tài nguyên:

```java
public final class ConnectionProvider
        implements SomeService, AutoCloseable {
    // Có thể sở hữu connection, executor hoặc subscription.

    @Override
    public void close() {
        // Giải phóng tài nguyên theo contract ứng dụng.
    }
}
```

Đây là **mã minh họa**, cần interface `SomeService` và implementation methods cụ thể nếu muốn biên dịch thành chương trình; không phải ví dụ chạy độc lập.

`ServiceLoader.reload()` **không tự gọi `close()`** trên những providers đã được trả cho host. Nếu caller giữ references, object có thể tiếp tục sống.

Một registry có lifecycle hợp lý nên:

- Có interface `start/stop/close` hoặc adapter lifecycle riêng.
- Ngăn tạo request mới trên provider đã bị thay.
- Chờ các requests đang chạy hoàn tất, hoặc hủy chúng có kiểm soát.
- Unregister listeners/callbacks, ngắt background tasks và dọn `ThreadLocal`/TCCL nếu framework đã thay chúng.
- Đóng file/socket/resources của provider; sau đó mới đóng `URLClassLoader` nếu loader thuộc quyền sở hữu của registry.
- Bỏ references tới instances/`Class<?>`/`Method`/`Provider<?>`/ServiceLoader/streams cũ khi muốn cho phép class unloading.

**GC/class unloading không tức thì:** ngay cả sau `URLClassLoader.close()`, một strong reference từ host registry hoặc thread cũng có thể giữ plugin loader và toàn bộ classes sống.

## 20. Chi phí caching và lựa chọn kiến trúc

Cache có lợi:

- Không khởi tạo lại provider instance qua mỗi lượt iterator.
- Tránh discovery/constructor lặp lại khi registry cần dùng dịch vụ nhiều lần.
- Giữ identity/states của provider object ổn định trong một `ServiceLoader` khi chưa reload.

Nhưng cache có trade-off:

- **Provider state được chia sẻ**: nếu provider mutable, những nơi dùng chung một cached instance có thể can thiệp lẫn nhau.
- **Lifetime kéo dài**: `ServiceLoader` có thể giữ provider instances và classes sống lâu hơn dự kiến.
- **Không tự thấy thay đổi**: thêm JAR/module, đổi config hoặc phiên bản implementation cần discovery plan cụ thể.
- **Nguy cơ concurrency** nếu nhiều threads duyệt cache và reload cùng lúc.
- **Khó quản lý phiên bản** nếu một đối tượng ServiceLoader bị giữ toàn JVM trong khi tenants có TCCL khác nhau.

Nếu chỉ cần **một provider chọn một lần khi startup**, việc lưu một immutable registry của providers đã xác thực thường đơn giản hơn. Nếu cần **thay provider lúc runtime**, thiết kế registry theo version/generation và class loader ownership, không chỉ bấm `reload()`.

### “Singleton provider” là quyết định của ai?

`ServiceLoader` giúp cache instance ở đường iterator, nhưng **không phải container quản lý singleton toàn chương trình**. Một provider constructor có thể tạo instance thứ hai khi:

- dùng `ServiceLoader` object khác;
- gọi `reload()` rồi iterate lại;
- dùng provider factory tạo instance theo contract riêng;
- có class loader khác định nghĩa provider type;
- ứng dụng tự gọi constructor/factory ngoài ServiceLoader.

Nếu service bắt buộc singleton theo nghiệp vụ, hãy thiết kế invariant/lifecycle tại provider/container layer; đừng suy nó chỉ từ cache behavior.

## 21. Checklist triển khai an toàn

Trước khi dùng `ServiceLoader` trong host/plugin framework:

1. **Chọn service API identity**: interface phải cùng `Class<?>` ở host và provider.
2. **Chọn discovery context**: explicit `ClassLoader`, TCCL hay `ModuleLayer`; không trộn khi thiếu lý do.
3. **Đóng gói descriptor đúng**: `META-INF/services/<service binary name>` cho classpath, `uses`/`provides` cho named modules.
4. **Biết lazy semantics**: `load` chưa nhất thiết tạo provider; iterator/stream/findFirst gây discovery khi được duyệt.
5. **Biết caching semantics**: iterator phát instances cached trước; `stream` cung cấp descriptors; không đoán `Provider.get()` là singleton.
6. **Quy định lúc `reload`**: clear cache, bỏ iterator/stream cũ, không sử dụng song song.
7. **Không chia sẻ `ServiceLoader` thiếu synchronization** giữa threads. Nếu cần throughput, snapshot providers sau discovery tuần tự.
8. **Xác nhận provider thread safety** độc lập; stateful service cần synchronization/factory/instance-per-call.
9. **Xác thực provider configuration errors** với context/cause, không nuốt lỗi.
10. **Không nhầm cache reload với class reload**; chọn class loader mới khi cần nạp definitions khác.
11. **Công bố registry atomic có lifecycle** nếu hot-swap, đảm bảo old consumers kết thúc.
12. **Dọn references và close tài nguyên** của provider/URLClassLoader đúng thời điểm.
13. **Test đúng runtime packaging**; IDE classpath dễ che thiếu descriptors/duplicate APIs.
14. **Test concurrency**: iterate/reload giao nhau phải được ngăn trong thiết kế; service object dùng đồng thời phải được kiểm chứng riêng.

## 22. Câu hỏi tự kiểm tra có đáp án

**1. `ServiceLoader.load(S.class)` có tạo ngay tất cả provider instances không?** Không. Provider discovery và instantiation có tính lazy; iterator/stream/findFirst mới thực hiện công việc theo nhu cầu.

**2. Hai lần `findFirst()` trên cùng ServiceLoader khi chưa reload có thể trả cùng object không?** Có. Khi provider được tạo/cached theo iterator, lượt sau nhận lại cached instance.

**3. `reload()` xóa những gì?** Provider caches của ServiceLoader instance ấy để lần duyệt mới khám phá lại.

**4. `reload()` có thay bytecode của class đã loaded không?** Không. Nó không redefine/unload runtime class.

**5. Tại sao ví dụ A in `provider ctor #2` sau reload nhưng `same class=true`?** Có object mới từ cùng `Class<?>` của cùng defining loader, nên static construction counter tiếp tục tăng.

**6. Sau `reload()` có được dùng iterator cũ không?** Không. Javadoc yêu cầu discard; `hasNext/next` có thể ném `ConcurrentModificationException`.

**7. `ConcurrentModificationException` sau reload có chứng minh hai thread chạy đồng thời không?** Không. Một thread cũng có thể làm iterator cũ invalid bằng `reload`.

**8. `stream()` trả trực tiếp service instance không?** Không. Nó trả `Stream<ServiceLoader.Provider<S>>`; gọi `Provider.get()` để lấy instance.

**9. Có thể gọi `Provider.get()` lặp lại rồi tin chắc cùng object không?** Không. API không hứa singleton identity như thế.

**10. Một `ServiceLoader` có thread-safe không?** Không. Java 17 Javadoc cảnh báo rõ instances không safe cho nhiều concurrent threads.

**11. Sau khi snapshot providers, mọi provider có tự thread-safe không?** Không; provider thread safety là hợp đồng riêng của implementation.

**12. Vì sao `ServiceLoader.load(service)` không nên cache VM-wide trong container?** Vì overload này dùng TCCL; các applications có discovery contexts khác nhau và việc cache có thể giữ class loader/provider sống.

**13. Plugin cập nhật JAR nhưng `reload()` vẫn chạy code cũ: vì sao?** ClassLoader có thể đã định nghĩa runtime class từ bytes cũ; reload chỉ đổi provider cache.

**14. Nếu hai URLClassLoader riêng định nghĩa provider cùng binary name, static counter có chia sẻ không?** Không. Hai runtime class identities có static states riêng.

**15. Host interface trùng tên với bản plugin nhưng cast fail, nguyên nhân có thể là gì?** Shared API bị define hai lần bởi defining loaders khác nhau; cần delegation về đúng API class.

**16. `ServiceLoader.reload()` có gọi `AutoCloseable.close()` trên provider objects cũ không?** Không. Ứng dụng phải tự quản lifecycle.

**17. Khi nào nên tạo ServiceLoader mới thay vì reload cái cũ?** Khi cần đổi discovery loader/TCCL/layer, xây registry theo generation hoặc không muốn chia sẻ caches.

**18. Một service-configuration file có thể bỏ qua những lỗi về provider class không?** Không nên. Cần phân biệt “không có provider” với `ServiceConfigurationError` do cấu hình hoặc class loading/instantiation thất bại.

## 23. Tài liệu chuẩn để đối chiếu

- [Java SE 17 — `ServiceLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider discovery, caching, `iterator`, `stream`, `findFirst`, `reload`, concurrency, TCCL và module layers.
- [Java SE 17 — `ServiceLoader.Provider` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html): `type()`, `get()` và provider descriptors.
- [Java SE 17 — `ClassLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, runtime class visibility và resource lookup.
- [Java SE 17 — `URLClassLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): plugin class loaders từ URL, `close()` và phạm vi lookup.
- [Java SE 17 — `ModuleLayer` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): named module layers khi triển khai providers.
- [Java Virtual Machine Specification, Java SE 17 — Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): defining loader, class identity, loading/linking và class lifecycle.

**Kết luận:** `ServiceLoader` **cache provider phục vụ lazy discovery/iteration**, `reload()` **xóa cache và làm iterator/stream cũ không còn hợp lệ**, nhưng **không nạp lại bytecode của provider class**. Một `ServiceLoader` **không dùng đồng thời an toàn**; hãy phát hiện provider ở giai đoạn được kiểm soát, xây registry/snapshot, đánh giá thread safety của từng provider và quản lý hot-swap bằng lifecycle cùng class loader ownership thật sự.
