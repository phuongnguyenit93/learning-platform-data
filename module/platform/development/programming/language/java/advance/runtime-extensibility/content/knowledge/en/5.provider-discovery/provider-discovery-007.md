# Bộ nhớ đệm của iterator, stream và ảnh hưởng của reload trong Java ServiceLoader

## 1. Bối cảnh: ServiceLoader khám phá provider như thế nào?

`ServiceLoader<S>` (Java 6+, mở rộng với `stream()` từ Java 9) giúp ứng dụng tìm implementation của một **service contract** ở runtime. Chẳng hạn host định nghĩa `TaskProvider`, còn những JAR provider đăng ký implementation bằng `META-INF/services/<tên-đầy-đủ-của-service>` trên class path hoặc bằng `provides ... with ...` trong named module. Host có thể duyệt provider mà không phụ thuộc trực tiếp vào class implementation.

Đề bài này tập trung vào một chi tiết ảnh hưởng lớn tới hành vi lúc chạy: **`ServiceLoader` nạp lười (lazy loading) và ghi nhớ các provider đã tìm/nạp trong bộ nhớ đệm (cache)**. Hai API duyệt quan trọng là:

- `iterator()`: trả về `Iterator<S>`; khi duyệt, các phần tử nhận được là **instance thực** của service.
- `stream()`: trả về `Stream<ServiceLoader.Provider<S>>`; mỗi phần tử là **mô tả/đầu mối tạo provider** (`Provider<S>`), từ đó có thể xem `type()` hoặc gọi `get()` để lấy instance.

Phương thức `reload()` **xóa cache provider của đối tượng `ServiceLoader` đang dùng**. Nó không tự khởi tạo ngay instance mới và không phải cơ chế thay class bytecode, gỡ class cũ hay cập nhật JAR tự động.

### Cần phân biệt bốn đối tượng

| Đối tượng | Vai trò | Có tự giữ instance/provider không? |
| --- | --- | --- |
| `ServiceLoader<S>` | Giữ thông tin service, phạm vi tìm provider (class loader/module layer) và các cache của chính nó | **Có** cache những provider đã được nạp/duyệt |
| `Iterator<S>` | Con trỏ duyệt instance, được tạo bởi `serviceLoader.iterator()` | Đọc lại instance đã cached, sau đó tìm/nạp phần chưa được duyệt |
| `Stream<Provider<S>>` | Pipeline một lần dùng để duyệt metadata của provider | Dùng nguồn provider descriptor của `ServiceLoader`; stream **không phải** danh sách instance mặc định |
| `Provider<S>` | Đầu mối cho `type()` và `get()` | `get()` lấy/tạo instance; không nên giả định luôn trả về cùng một đối tượng |

“Cache” ở đây là cache của **một instance `ServiceLoader`**, không phải cache toàn JVM; `Stream` thông thường cũng có tính lazy nhưng đó là khái niệm khác với cache của `ServiceLoader`. Gọi `ServiceLoader.load(...)` lần nữa sẽ tạo **một `ServiceLoader` khác** có cache riêng; việc cả hai loader thấy cùng một class không bắt buộc chúng chia sẻ đối tượng provider đã tạo.

## 2. Cache của iterator(): nạp đến đâu, nhớ đến đó

Theo Java SE 17 API:

1. Lời gọi `ServiceLoader.load(TaskProvider.class)` tạo service loader. Provider không được đảm bảo đã instantiate ở bước này.
2. `loader.iterator()` tạo một iterator; provider được tìm và instantiate **khi việc duyệt đòi hỏi**, thay vì khởi tạo toàn bộ ngay khi tạo loader.
3. Khi iterator gặp provider cần được instantiate, `ServiceLoader` thêm **instance** đó vào cache tương ứng.
4. Một lần gọi `loader.iterator()` khác trên **cùng loader** sẽ trả lại các instance đã cache **theo thứ tự chúng được nạp trước đó**, rồi tiếp tục tìm và instantiate những provider còn lại khi cần.
5. `loader.findFirst()` là cách tiện lợi lấy provider đầu tiên bằng cơ chế iterator; nếu đầu tiên đã nằm trong cache, nó có thể trả lại chính instance cached.

Ví dụ có ba provider A, B, C. Nếu lần duyệt đầu chỉ lấy A rồi dừng, cache instance hiện tại mới bao gồm A. Lần duyệt thứ hai có thể trả A từ cache, sau đó instantiate B và C nếu thực sự duyệt tới chúng. **Tạo iterator mới không có nghĩa là bỏ cache.**

Vì thế `for (TaskProvider p : loader) { ... }` trong nhiều vòng lặp trên cùng loader thường tái sử dụng những instance trước đó. Đây là hành vi đáng lưu tâm nếu constructor mở connection, provider giữ trạng thái mutable hoặc có phương thức `close()`: các vòng duyệt lặp lại không tự tạo tài nguyên mới, và `ServiceLoader` cũng không tự gọi `close()` cho provider.

### Tính lazy không đồng nghĩa không thể xảy ra lỗi

`hasNext()` hoặc `next()` có thể gây `ServiceConfigurationError` khi đọc metadata/provider configuration, load class, resolve dependency hoặc instantiate provider. Không nên nhận định “mọi lỗi chỉ xảy ra ở `next()`”. Một provider lỗi có thể làm quá trình discovery ngắt giữa chừng; việc khôi phục bằng cách tiếp tục duyệt chỉ được tài liệu API mô tả là nỗ lực best effort, **không được đảm bảo**.

## 3. Cache của stream(): mô tả provider trước, instance sau

`loader.stream()` trả về `Stream<ServiceLoader.Provider<S>>`. Nó **không** trả thẳng `Stream<S>`. Việc duyệt stream được trì hoãn tới một terminal operation như `findFirst()`, `toList()` hoặc `forEach(...)`.

~~~java
ServiceLoader<TaskProvider> loader = ServiceLoader.load(TaskProvider.class);

// Đọc metadata: chưa cần tạo instance để lọc theo loại provider.
List<Class<? extends TaskProvider>> types = loader.stream()
        .map(ServiceLoader.Provider::type)
        .toList();

// Chỉ khi cần sử dụng mới lấy instance.
List<TaskProvider> instances = loader.stream()
        .map(ServiceLoader.Provider::get)
        .toList();
~~~

**Đây là đoạn minh họa**, cần interface `TaskProvider` và provider đã đăng ký để chạy độc lập. `Provider.type()` hỗ trợ xem type và annotation mà không cần gọi constructor của service implementation. Với provider trong named module được tạo bằng static `provider()` factory method, `type()` trả về **return type của provider method**, không nhất thiết là class chứa method.

Khi stream duyệt, `ServiceLoader` nhớ các **provider descriptor** đã tìm được từ những lần xử lý stream trước. Lần gọi `loader.stream()` mới có thể xử lý các descriptor đã cache trước rồi khám phá thêm provider còn lại. Thứ tự provider phụ thuộc quy tắc lookup, configuration/module; **đừng dựa vào thứ tự ngẫu nhiên giữa các JAR/module** để xác định ưu tiên nghiệp vụ.

Các ranh giới dễ lẫn:

- `Provider.type()` **không có nghĩa** provider instance đã được tạo.
- `Provider.get()` trả về một instance. API không cam kết đó là singleton hay trùng tham chiếu với một lần `get()` khác. Với class-path provider được tạo bằng public no-arg constructor, các lần `get()` có thể dẫn tới nhiều lần xây dựng object. Đừng dùng phép `==` như hợp đồng lựa chọn provider khi đi qua API này.
- **Không giả định cache của `iterator()` và `stream()` có chung cùng một object instance hoặc cùng thời điểm khởi tạo.** Một phía làm việc với instance, phía kia làm việc với `Provider` descriptor; nếu cần quản lý một object duy nhất cho nghiệp vụ, host nên tự sở hữu registry/snapshot rõ ràng.
- `stream()` tạo một Java `Stream` **chỉ được thực hiện một terminal operation**. Dùng lại một stream đã consumed có thể ném `IllegalStateException`; lỗi này khác hoàn toàn với stream bị `reload()` vô hiệu hóa.
- `sorted()`, `collect()` hoặc `toList()` có thể buộc khám phá toàn bộ danh sách descriptor. `findFirst()` có thể dừng sớm. Có metadata của tất cả provider **không đồng nghĩa** đã gọi `get()` cho tất cả.

## 4. Thực hành Java 17+: quan sát cache và reload một cách chạy được

Ví dụ dưới đây dùng **một provider duy nhất** và constructor tự in số lần tạo. Nó cho thấy rõ: iterator tái sử dụng instance; reload bỏ cache; một instance đã giao cho caller vẫn tồn tại; stream lấy metadata trước khi tạo object.

### 4.1. Cấu trúc thư mục

~~~text
service-cache-demo/
├── src/
│   ├── demo/
│   │   ├── TaskProvider.java
│   │   ├── CountingProvider.java
│   │   ├── IteratorCacheDemo.java
│   │   └── StreamReloadDemo.java
│   └── META-INF/
│       └── services/
│           └── demo.TaskProvider
└── out/                  # Sinh ra khi biên dịch
~~~

Provider-configuration file phải nằm trên **runtime class path** và có tên trùng **fully qualified binary name** của service interface.

Tệp `src/demo/TaskProvider.java`:

~~~java
package demo;

public interface TaskProvider {
    String name();
}
~~~

Tệp `src/demo/CountingProvider.java`:

~~~java
package demo;

public final class CountingProvider implements TaskProvider {
    private static int sequence;
    private final int id;

    public CountingProvider() {
        id = ++sequence;
        System.out.println("constructor #" + id);
    }

    @Override
    public String name() {
        return "provider-" + id;
    }
}
~~~

Nội dung tệp `src/META-INF/services/demo.TaskProvider`:

~~~text
demo.CountingProvider
~~~

Với cơ chế class path, `CountingProvider` là public class, implement service và có public constructor không tham số. **Named module** có thêm cách khai báo provider bằng `provides ... with ...` và có thể dùng public static `provider()` factory method; ví dụ này cố ý dùng class path để dễ quan sát constructor.

### 4.2. Iterator: cùng cache trước reload, instance mới sau reload

Tệp `src/demo/IteratorCacheDemo.java`:

~~~java
package demo;

import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.ServiceLoader;

public final class IteratorCacheDemo {
    public static void main(String[] args) {
        ServiceLoader<TaskProvider> loader = ServiceLoader.load(
                TaskProvider.class, IteratorCacheDemo.class.getClassLoader());

        TaskProvider first = loader.iterator().next();
        TaskProvider again = loader.iterator().next();
        System.out.println("same before reload = " + (first == again));

        Iterator<TaskProvider> staleIterator = loader.iterator();
        loader.reload();

        try {
            staleIterator.hasNext();
            System.out.println("unexpected");
        } catch (ConcurrentModificationException e) {
            System.out.println("stale iterator = ConcurrentModificationException");
        }

        TaskProvider fresh = loader.iterator().next();
        System.out.println("same after reload = " + (first == fresh));
        System.out.println("old object = " + first.name());
    }
}
~~~

Giải thích:

- Lần `next()` đầu tiên tạo `CountingProvider` id=1 và cache instance.
- Lần `next()` thứ hai trên **iterator mới của cùng loader** lấy lại id=1; constructor **không** chạy lại.
- `staleIterator` được tạo **trước** `reload()`. Sau khi cache bị xóa, `hasNext()` trên iterator cũ ném `ConcurrentModificationException`; dù không hề có hai thread.
- Iterator mới sau reload tạo id=2 khi cần. Instance cũ `first` vẫn sống do biến `first` đang giữ tham chiếu, nên `first.name()` vẫn dùng được.

### 4.3. Stream: type trước, Provider.get() sau; stream cũ hết hiệu lực

Tệp `src/demo/StreamReloadDemo.java`:

~~~java
package demo;

import java.util.ConcurrentModificationException;
import java.util.ServiceLoader;
import java.util.stream.Stream;

public final class StreamReloadDemo {
    public static void main(String[] args) {
        ServiceLoader<TaskProvider> loader = ServiceLoader.load(
                TaskProvider.class, StreamReloadDemo.class.getClassLoader());

        Stream<ServiceLoader.Provider<TaskProvider>> metadataStream = loader.stream();
        System.out.println("stream created");

        ServiceLoader.Provider<TaskProvider> entry =
                metadataStream.findFirst().orElseThrow();
        System.out.println("type = " + entry.type().getSimpleName());

        System.out.println("first get = " + entry.get().name());
        System.out.println("second get = " + entry.get().name());

        Stream<ServiceLoader.Provider<TaskProvider>> staleStream = loader.stream();
        loader.reload();

        try {
            staleStream.findFirst();
            System.out.println("unexpected");
        } catch (ConcurrentModificationException e) {
            System.out.println("stale stream = ConcurrentModificationException");
        }

        var newEntry = loader.stream().findFirst().orElseThrow();
        System.out.println("type after reload = " + newEntry.type().getSimpleName());
    }
}
~~~

Ở đây `metadataStream.findFirst()` dùng terminal operation và chỉ lấy metadata provider; constructor chưa cần chạy. `entry.get()` mới yêu cầu instance. Với provider class ở ví dụ và hành vi Java 17, hai lời gọi `get()` sẽ tạo hai object mới và in hai dòng constructor. Nhưng **đừng thiết kế dựa vào một giả định singleton hay identity cụ thể khi dùng `Provider.get()`**; hãy quản lý lifecycle trong host nếu phải dùng chung một instance.

`staleStream` được tạo trước `reload()` nhưng chưa thực hiện terminal operation. Spliterator lấy từ `ServiceLoader.stream()` kiểm tra thay đổi cache; khi bắt đầu duyệt sau reload, nó phát hiện generation đã thay đổi và ném `ConcurrentModificationException`. Chúng ta tạo **stream mới** sau reload để duyệt tiếp.

### 4.4. Biên dịch và chạy

Chạy các lệnh sau **tại thư mục `service-cache-demo`** bằng PowerShell với JDK 17+ đã cài:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac -encoding UTF-8 -d out src/demo/TaskProvider.java src/demo/CountingProvider.java src/demo/IteratorCacheDemo.java src/demo/StreamReloadDemo.java
Copy-Item -Recurse -Force src/META-INF out/META-INF
java -cp out demo.IteratorCacheDemo
java -cp out demo.StreamReloadDemo
~~~

Output của `IteratorCacheDemo`:

~~~text
constructor #1
same before reload = true
stale iterator = ConcurrentModificationException
constructor #2
same after reload = false
old object = provider-1
~~~

Output của `StreamReloadDemo` (quá trình `java` thứ hai là JVM mới nên biến static `sequence` bắt đầu lại từ 0):

~~~text
stream created
type = CountingProvider
constructor #1
first get = provider-1
constructor #2
second get = provider-2
stale stream = ConcurrentModificationException
type after reload = CountingProvider
~~~

Nếu constructor in thiếu/thừa, trước tiên kiểm tra provider-configuration file được copy nguyên dạng vào `out/META-INF/services/demo.TaskProvider`, class path thật sự chỉ chứa ví dụ mong muốn và chương trình đang chạy một JVM mới. Có thể dùng `jar tf` khi đóng gói thành JAR.

## 5. reload() thực sự làm gì với iterator, stream và instance cũ?

Java SE 17 mô tả `reload()` là thao tác **xóa provider caches của ServiceLoader**. Các lời gọi `iterator()` hoặc `stream()` *mới sau reload* quay về trạng thái tìm provider lười từ đầu; những iterator/stream được lấy *trước reload* phải bị loại bỏ.

| Hạng mục | Trước `reload()` | Sau `reload()` |
| --- | --- | --- |
| Cache instance của iterator | Chứa những provider instance đã được duyệt | Bị xóa; lần duyệt mới có thể instantiate lại |
| Cache provider descriptor của stream | Chứa provider đã discover qua stream | Bị xóa; stream mới tra cứu lại khi cần |
| Iterator đã tạo trước đó | Có thể đi tiếp hoặc lấy cached instance | `hasNext()/next()` ném `ConcurrentModificationException` khi sử dụng |
| Stream đã tạo trước đó | Có thể thực hiện một terminal operation | Nguồn spliterator là fail-fast sau reload; bỏ stream cũ và tạo stream mới |
| Object instance đã trả cho caller | Caller có thể giữ tham chiếu | **Không bị hủy**; vẫn tồn tại nếu còn tham chiếu |
| Provider class đã load trong JVM | Đã được class loader định nghĩa | **Không bị unload/redefine** chỉ vì reload |
| Các provider JAR/module nhìn thấy được | Do class loader/module layer quyết định | **Không tự mở rộng** phạm vi tìm class/JAR/module |
| Thread đang sử dụng plugin | Có thể có request đang chạy | **Không bị dừng** bởi reload |

**Hệ quả lớn nhất:** `reload()` làm mới **cache discovery/instantiation của một loader**, chứ không thay thế toàn bộ trạng thái runtime. Nếu một request đang giữ provider instance cũ, request đó vẫn có thể tiếp tục; nếu instance cũ giữ file handle, thread, connection pool hay ClassLoader, `reload()` không tự giải phóng chúng.

### 5.1. Vì sao lại có ConcurrentModificationException?

Đây là hành vi **fail-fast đối với thay đổi trạng thái cache**. Một iterator/stream đã gắn với trạng thái cache/generation cũ sẽ không biết duyệt nhất quán như thế nào sau khi cache bị reset. Java SE 17 quy định:

- Iterator `hasNext()` và `next()` sau `reload()`: ném `ConcurrentModificationException`.
- Spliterator nguồn của `stream()`: fail-fast nếu provider cache bị xóa.

Tên exception thường gắn với concurrency nhưng **một thread duy nhất** gọi `reload()` ở giữa hai thao tác cũng có thể tạo ra nó. Ngược lại, fail-fast **không** phải cơ chế khóa hay bảo đảm an toàn đa luồng.

### 5.2. Reload không giống “stream reusable”

Hai lỗi cần phân biệt bằng ví dụ:

~~~java
// Minh họa riêng: source là một ServiceLoader<TaskProvider> hợp lệ.
var once = loader.stream();
once.count();          // Terminal operation đầu tiên
once.count();          // IllegalStateException: đã dùng stream

var stale = loader.stream();
loader.reload();
stale.findFirst();     // ConcurrentModificationException do cache reset
~~~

Đây là **đoạn minh họa không độc lập**, cố ý thể hiện hai lỗi; không gộp vào ứng dụng production. Trong thực tế, quy tắc an toàn nhất là **tạo stream mới cho mỗi lần duyệt** và **không giữ iterator/stream qua điểm reload**.

### 5.3. Reload không đảm bảo thấy JAR mới

Một số nhầm lẫn cần loại bỏ:

- Nếu bạn copy một plugin JAR mới vào thư mục `plugins/` nhưng **class loader hiện tại không có URL đó**, gọi `reload()` không tự bổ sung URL/class path. Cần cơ chế loader có khả năng nhìn thấy provider đó hoặc tạo loader/module layer phù hợp.
- Nếu provider class đã được load bởi class loader, sửa bytecode trên đĩa rồi gọi `reload()` **không** làm class ấy được định nghĩa lại từ bytecode mới. Java class identity gắn với binary name và defining class loader.
- Nếu muốn hot-deploy/hot-swap implementation hoặc cách ly versions, thường cần quản lý **một thế hệ plugin loader** mới (ví dụ `URLClassLoader` hoặc `ModuleLayer` phù hợp), khởi tạo provider mới, chuyển traffic, dừng provider cũ và bỏ tham chiếu cũ. Chỉ dùng `reload()` là chưa đủ.
- Nếu `ServiceLoader.load(Service.class)` dùng overload một tham số, nó lấy **thread context class loader** tại thời điểm tạo loader. Việc thay TCCL của thread về sau không tự đổi phạm vi của `ServiceLoader` đã tạo; cần tạo loader mới với class loader đúng.

## 6. Cách thiết kế việc làm mới provider an toàn trong ứng dụng thực

`ServiceLoader` **không thread-safe**. Không nên để một thread duyệt trong khi thread khác gọi `reload()` trên cùng instance, và cũng không nên chia sẻ iterator/stream có thể bị đổi generation mà không điều phối.

### Mức 1: Chỉ cần nạp lại cache ở điểm dừng an toàn

Dùng khi tất cả truy vấn discovery đều chạy tuần tự, provider source vẫn nằm trong cùng phạm vi loader:

1. Ngừng phát sinh lần duyệt mới trên loader cũ và chờ các lần duyệt hiện tại hoàn tất.
2. Đảm bảo mọi iterator và stream cũ đã bị bỏ; nếu còn object cũ đang chạy, tách lifecycle của chúng.
3. Gọi `loader.reload()`.
4. Với mỗi lần tra cứu mới, tạo `loader.iterator()` hoặc `loader.stream()` mới. Chỉ bắt đầu dùng các instance mới sau khi xác thực cấu hình.
5. Đóng tài nguyên do host quản lý của thế hệ cũ khi không còn request sử dụng.

### Mức 2: Snapshot bất biến cho nhiều request đồng thời

Đối với một host phục vụ request trên nhiều thread, thuận tiện hơn là dùng discovery để tạo một **snapshot các instance đã chọn**, rồi cho request đọc snapshot. Khi refresh, xây dựng snapshot mới ở một luồng điều phối, kiểm tra nó đầy đủ trước khi công bố; traffic đọc một tham chiếu được thay thế nguyên tử.

Đoạn minh họa **không độc lập**, giả định `TaskProvider`, `pluginClassLoader` và `activeProviders` đã được khai báo đúng kiểu:

~~~java
ServiceLoader<TaskProvider> discovery =
        ServiceLoader.load(TaskProvider.class, pluginClassLoader);

List<TaskProvider> nextProviders = discovery.stream()
        .map(ServiceLoader.Provider::get)
        .toList();                    // Materialize và kiểm tra trước khi publish

List<TaskProvider> previous =
        activeProviders.getAndSet(nextProviders); // AtomicReference<List<TaskProvider>>

// Chỉ dừng/đóng các provider trong previous khi không còn request đang dùng chúng.
~~~

`Stream.toList()` (Java 16+) tạo danh sách không thể sửa qua các operation thêm/xóa của `List`; điều đó **không làm từng provider instance trở nên thread-safe**. Có thể cần một đối tượng `Generation` chứa danh sách provider, class loader, phiên bản và lifecycle tracker, để điều phối việc dừng/giải phóng đúng thế hệ. Nếu host không quản lý thời điểm request cũ hoàn thành, việc đóng provider sớm có thể làm request đang chạy thất bại.

### Mức 3: Plugin được thay JAR/version lúc chạy

Tạo class loader/module layer mới cho thế hệ mới, discovery và validate provider trong thế hệ mới, rồi hoán đổi snapshot chỉ khi đã sẵn sàng. Sau khi thế hệ cũ không còn request, dừng provider, đóng tài nguyên của plugin, bỏ reference đến instance/`Class`/`ClassLoader` và đóng `URLClassLoader` khi thích hợp. `URLClassLoader.close()` đóng tài nguyên loader nhưng **không ép JVM unload class ngay lập tức**.

Class loader/JPMS cũng không phải sandbox bảo mật: chỉ nạp mã plugin được tin cậy, hoặc tách process/container nếu cần thực thi mã không tin cậy.

## 7. Những tình huống thực tế và quyết định phù hợp

| Tình huống | Nên làm | Không nên suy diễn |
| --- | --- | --- |
| Vòng lặp dùng `iterator()` nhiều lần trên cùng loader | Hiểu rằng provider instance cached sẽ được dùng lại; quản lý state/thread-safety | “Mỗi vòng lặp là một provider mới” |
| Muốn liệt kê implementation theo annotation mà chưa khởi tạo | `stream().filter(p -> p.type()...).toList()` | “`stream()` luôn gọi constructor” |
| Cần khởi tạo provider sau khi chọn | `Provider.get()` và quản lý instance do host sở hữu | “`get()` luôn singleton như cache iterator” |
| Sau một lần duyệt, muốn tìm lại source provider | `reload()` tại điểm điều phối an toàn, rồi tạo iterator/stream mới | “Có thể dùng tiếp iterator/stream cũ” |
| Thấy `ConcurrentModificationException` | Kiểm tra reload giữa vòng duyệt và mọi quyền truy cập đa luồng | “Chắc chắn có hai thread sửa cùng collection” |
| Provider mới không xuất hiện | Kiểm tra metadata SPI, class loader visibility, module layer, runtime class path | “Gọi reload nhiều lần sẽ tự tìm JAR mới” |
| Provider cũ vẫn chạy sau reload | Hoàn thành lifecycle/drain request, loại reference và giải phóng resource đúng lúc | “Reload sẽ gọi stop/close” |
| Cần refresh an toàn dưới tải | Build/validate snapshot mới rồi swap nguyên tử, drain thế hệ cũ | “ServiceLoader có sẵn đồng bộ hóa đa luồng” |

## 8. Bẫy thường gặp khi xử lý exception và trạng thái

### 8.1. Nhầm lỗi discovery với lỗi cache invalidation

- `ServiceConfigurationError`: lỗi cấu hình provider, load/instantiate provider, resource metadata hoặc dependency (có thể phát sinh khi `hasNext()`/`next()` hoặc terminal operation stream).
- `ConcurrentModificationException`: trong ngữ cảnh đề bài, iterator/stream cũ tiếp tục dùng sau `reload()`; có thể xuất hiện ngay cả với một thread.
- `IllegalStateException`: Java Stream bị dùng lại sau terminal operation.
- `ClassNotFoundException`/`NoClassDefFoundError`: class không tìm thấy hoặc không định nghĩa/khởi tạo được trong phạm vi loader; phải kiểm tra nguyên nhân và dependency, không quy mọi lỗi thành “cache cũ”.

Đừng nuốt `ServiceConfigurationError` rồi silently bỏ qua provider: có thể làm host hoạt động thiếu tính năng mà không có cảnh báo. Nên log service type, nguồn class loader/module, provider-configuration location (khi có thể) và exception cause; trong hệ plugin có mức lỗi cô lập, ghi rõ chính sách skip/fallback.

### 8.2. Rò rỉ bộ nhớ do cache và tham chiếu cũ

`ServiceLoader` sống lâu có thể giữ instance/provider metadata, kéo theo class loader, các class của plugin và resource gián tiếp. `reload()` xóa cache bên trong loader đó nhưng **không xóa reference trong registry khác**, thread-local, static field, listener hoặc request đang giữ instance. Hãy điều tra nơi giữ strong reference thay vì coi `reload()` là lệnh GC.

### 8.3. Sai giả định về thứ tự

Cache bảo toàn thứ tự **đã được nạp**; không có nghĩa nhà cung cấp nào đó luôn đứng đầu trong mọi cấu hình class path/module layer. Nếu host cần priority hoặc capability, cần metadata và quy tắc sắp xếp/chọn tường minh. Gọi `findFirst()` phù hợp khi provider đầu tiên theo discovery order thực sự đã đủ.

### 8.4. Nhầm giới hạn phạm vi cache với lifecycle của service

`ServiceLoader` quản lý tìm/instantiate provider nhưng không quản lý toàn bộ lifecycle ứng dụng. Nếu provider là stateful service, singleton theo host, hoặc cần start/stop/health-check, hãy xây service registry/container riêng. Cache mặc định có ích cho discovery nhưng không đủ thay thế service management.

## 9. Checklist QA và bài tập củng cố

Thực hiện các test sau với ứng dụng mẫu (mỗi test độc lập hoặc khởi tạo loader mới cho từng tình huống):

1. **Lazy iterator:** tạo loader nhưng chưa `next()`; xác nhận chưa thấy dòng constructor, sau `next()` thấy đúng một lần.
2. **Cache instance:** lấy `loader.iterator().next()` hai lần trên cùng loader, xác nhận `== true` và constructor chạy một lần.
3. **Partial discovery:** thêm provider thứ hai trong `META-INF/services/demo.TaskProvider`. Lần đầu chỉ lấy một provider; lần sau duyệt hết và kiểm tra cache được mở rộng khi cần.
4. **Stream metadata:** chỉ thực hiện `stream().map(Provider::type).toList()` và kiểm tra không có log constructor provider; tiếp đó `Provider.get()` để quan sát việc instantiate.
5. **Hai lần Provider.get():** trong ví dụ `CountingProvider`, hai lần gọi tạo instance mới; không dựa vào identity này như một singleton contract tổng quát.
6. **Reload:** tạo iterator và stream, gọi `reload()`, dùng lại các bộ duyệt cũ để thấy `ConcurrentModificationException`; tạo bộ duyệt mới và xác nhận hoạt động.
7. **Old reference:** giữ object id=1 trước reload; sau reload vẫn gọi được `name()` trên object cũ và lấy object mới qua iterator.
8. **One-shot Stream:** cố dùng hai terminal operation trên cùng stream; phân biệt `IllegalStateException` với cache invalidation.
9. **TCCL/loader visibility:** thử thay class loader được truyền vào `load(service, loader)`. Khi provider JAR không được loader nhìn thấy, `reload()` không tự khắc phục.
10. **Concurrency/lifecycle:** tạo một coordinator duy nhất thực hiện refresh, publish snapshot bất biến và thử nhiều request song song; xác định rõ khi nào thế hệ cũ được đóng.

### Câu hỏi tự kiểm tra

- Cache thuộc về `ServiceLoader` hay về từng lời gọi `iterator()`?
- Vì sao `stream()` trả `Provider<S>` thay vì `S`?
- Gọi `type()` có bắt buộc instantiate implementation không?
- Hai lần `Provider.get()` có được API cam kết trả cùng instance không?
- `reload()` có làm mọi instance cũ biến mất không?
- Tại sao dùng iterator cũ sau reload có thể ném `ConcurrentModificationException` dù một thread?
- Nếu copy JAR mới vào thư mục nhưng nó chưa thuộc class loader, `reload()` có tác dụng gì?
- Vì sao khi refresh cho nhiều request, snapshot mới + chuyển traffic có thể an toàn hơn việc chia sẻ một `ServiceLoader` đang reload?

Nếu trả lời được bằng **cơ chế** và kiểm chứng bằng log constructor/identity cùng exception, bạn đã nắm được trọng tâm: **iterator cache instance, stream giúp duyệt provider descriptor, còn reload đặt lại trạng thái discovery của cùng `ServiceLoader` và làm các bộ duyệt cũ không còn hợp lệ**.

## 10. Tài liệu chuẩn

- Java SE 17 API — `ServiceLoader` (đặc biệt “Timing of provider discovery”, “iterator”, “stream”, “reload”, “Concurrency”): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Java SE 17 API — `ServiceLoader.Provider`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html
- Java SE 17 API — `Stream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html
- Java SE 17 API — `ConcurrentModificationException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ConcurrentModificationException.html
