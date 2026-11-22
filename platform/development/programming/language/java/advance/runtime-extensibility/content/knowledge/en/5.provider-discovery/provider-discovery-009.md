# Quy tắc truy cập đồng thời và phạm vi lưu giữ đối tượng ServiceLoader

`java.util.ServiceLoader<S>` là cơ chế Java SPI (Service Provider Interface) để tìm các implementation của một service mà ứng dụng không cần biết tên lớp cụ thể khi biên dịch. Nó hữu ích cho plugin, codec, driver, adapter và các khả năng mở rộng được đưa vào class path hoặc module path. Tuy nhiên, **cách dùng `ServiceLoader` ở nhiều luồng và thời gian giữ các đối tượng mà nó tạo ra ảnh hưởng trực tiếp tới tính đúng đắn, tài nguyên và khả năng nạp lại plugin**.

Hai câu hỏi của bài này là:

1. Khi nhiều luồng cùng cần provider, **ai được phép thao tác với đối tượng `ServiceLoader`**, đặc biệt trong discovery, iteration, stream và `reload()`?
2. **Giữ `ServiceLoader` và provider bao lâu, ở đâu, dưới class loader nào**, và điều gì xảy ra khi refresh, thay phiên bản hoặc gỡ plugin?

Nguyên tắc xuyên suốt: **không dùng chung `ServiceLoader` một cách đồng thời; chỉ chia sẻ provider sau khi có chính sách vòng đời và an toàn luồng riêng cho provider đó**.

## 1. Phân biệt bốn đối tượng thường bị đánh đồng

Một hệ thống có thể chứa nhiều thành phần mang ý nghĩa khác nhau:

| Thành phần | Nó đại diện cho gì? | Điều cần quản lý |
| --- | --- | --- |
| `ClassLoader` hoặc `ModuleLayer` | Không gian nhìn thấy class/module và provider | Phạm vi ứng dụng/plugin, khả năng cô lập và dỡ nạp |
| `ServiceLoader<S>` | Đối tượng khám phá service, có **trạng thái và cache nội bộ** | Chủ thể được quyền duyệt, cache, `reload()`; không chia sẻ thao tác đồng thời |
| `ServiceLoader.Provider<S>` | Mô tả provider thu được từ `stream()`; có `type()`, `get()` | Không đồng nhất descriptor với service instance; xác định policy tạo instance |
| `S` (provider instance) | Đối tượng thực thi nghiệp vụ do provider cung cấp | Có thread-safe không, state gì, ai sở hữu, có cần đóng tài nguyên không? |

Một `ServiceLoader` có thể tìm và tạo nhiều provider. Nhưng **service loader an toàn luồng hay không** và **implementation của provider an toàn luồng hay không** là hai vấn đề *độc lập*. Một provider không có mutable state có thể dùng đồng thời sau khi được công bố an toàn; điều đó không làm các phương thức `iterator()`, `stream()`, `reload()` trên cùng `ServiceLoader` trở nên thread-safe.

## 2. Cơ chế lazy discovery và cache của ServiceLoader

`ServiceLoader` khám phá provider **theo nhu cầu**. Không phải cứ gọi `ServiceLoader.load(...)` là tất cả implementation đã được khởi tạo. Một số công việc thực tế xảy ra khi duyệt:

- `loader.iterator()` trả iterator; `hasNext()` và `next()` có thể tiếp tục tìm, nạp và khởi tạo provider.
- `loader.findFirst()` có hành vi tương đương lấy phần tử đầu của iterator, có thể khởi tạo provider.
- `loader.stream()` trả `Stream<ServiceLoader.Provider<S>>`. `Provider.type()` hỗ trợ xem kiểu trước khi khởi tạo; `Provider.get()` lấy instance.
- Việc dùng terminal operation như `toList()`, `findFirst()` hoặc `forEach()` trên stream có thể kích hoạt discovery; không nên coi tạo stream là đã chụp snapshot bất biến.

### Cache theo đường iterator và stream

- **Iterator:** loader lưu **các service instance đã được duyệt/khởi tạo**. Lượt iterator sau trên cùng loader thường trả các instance đã cache trước, rồi mới khám phá các provider còn lại. Vì vậy, cùng một loader và cache chưa bị xóa, `loader.iterator().next()` có thể trả lại đúng *cùng object*.
- **Stream:** loader lưu **các provider descriptor được tìm thấy** phục vụ đường `stream()`. Lời gọi `Provider.get()` trả instance theo cách triển khai provider; không nên suy diễn rằng mọi lần gọi `get()` đều cho đúng một singleton hoặc đúng một object mới. Đừng dùng cache của iterator và stream thay thế nhau trong thiết kế vòng đời.
- **`reload()`:** xóa các cache này để các lượt duyệt sau khám phá lại từ đầu. Nó **không đóng**, **không sửa** và **không tự thu hồi** những provider instance mà mã khác đang giữ.

Ví dụ khác biệt cốt lõi:

```java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);

// Đường iterator: materialize service instance khi duyệt.
List<Codec> instances = new ArrayList<>();
for (Codec codec : loader) {
    instances.add(codec);
}

// Đường stream: materialize các provider descriptor; get() mới lấy instance.
List<ServiceLoader.Provider<Codec>> descriptions =
    loader.stream().toList();
```

Đoạn trên là *minh họa API*, cần có interface `Codec` và provider được cấu hình sẵn; phần 6 có project chạy độc lập.

### Quy tắc kiểm chứng cache

Cache thuộc **từng object `ServiceLoader`**, không phải một singleton của JVM. Hai lời gọi tạo hai `ServiceLoader` khác nhau không buộc phải dùng cùng instance provider. Cũng không nên lấy thứ tự “provider đầu tiên” làm chính sách lựa chọn mặc định: thứ tự provider từ named modules có thể không được xác định như mong muốn; nếu có nhiều implementation, hãy định nghĩa tiêu chí chọn rõ ràng.

## 3. Quy tắc truy cập đồng thời: ServiceLoader không thread-safe

Java SE 17 quy định rõ: **instance của `ServiceLoader` không an toàn khi nhiều thread cùng sử dụng**. Quy tắc này áp dụng cho việc duyệt và cập nhật trạng thái nội bộ của cùng một loader, dù code phía ứng dụng chỉ đọc kết quả.

Những đường truy cập không được mặc định chạy đồng thời trên *cùng instance*:

- Thread A gọi `iterator().hasNext()/next()` trong khi B cũng duyệt cùng loader;
- A đang thực thi terminal operation của `loader.stream()`, B gọi `findFirst()` hoặc `iterator()`;
- A duyệt provider còn B gọi `loader.reload()`;
- nhiều request cùng dùng một singleton `ServiceLoader` để khám phá động.

Một tình huống lỗi:

```text
Thread A                         Thread B
-----------------------------    ------------------------------
Iterator<S> it = loader.iterator()
it.hasNext()  // discovery
                                 loader.reload() // xóa cache
it.next()     // iterator cũ
               -> ConcurrentModificationException
```

Sau `reload()`, các iterator đã tạo trước đó **phải bị bỏ**; `hasNext()` hoặc `next()` của chúng có thể ném `ConcurrentModificationException`. Các stream cũ cũng phải bỏ vì nguồn spliterator fail-fast nếu cache bị xóa. Đó là hành vi cụ thể sau reload, **không phải cơ chế tự động làm mọi race condition thành lỗi dễ dự đoán**: khi truy cập loader đồng thời nói chung, chương trình đang vi phạm hợp đồng thread-safety.

Hai suy luận sai thường gặp:

1. “Chỉ gọi `iterator()` rồi đọc thì là read-only, nên nhiều thread dùng chung được.” Sai: việc duyệt có thể thay đổi cache bằng lazy discovery.
2. “Khai báo `volatile ServiceLoader<S> loader` là đủ.” Sai: `volatile` chỉ hỗ trợ visibility của **tham chiếu**; nó không khóa hoặc đồng bộ trạng thái bên trong loader.

Tương tự, `loader.stream().parallel()` không phải cách an toàn để parallelize discovery. Nếu muốn xử lý provider song song, hãy khám phá theo một luồng, tạo snapshot các instance thích hợp, rồi mới xử lý snapshot dưới chính sách thread-safety của provider.

## 4. Ba chiến lược truy cập đúng

### Chiến lược A — Khám phá một lần, công bố snapshot bất biến (thường nên chọn)

Registry hoặc bootstrap thread sở hữu `ServiceLoader`, duyệt **tuần tự**, xác thực provider, chuyển kết quả sang `List.copyOf(...)` rồi công bố qua `volatile` hoặc `AtomicReference`. Các request threads chỉ đọc **snapshot**, không động vào loader.

```text
Registry thread (một chủ thể)       Request threads
--------------------------------   --------------------------------
ServiceLoader.load(...)
duyệt / kiểm tra provider
List.copyOf(loaded)
atomic publish(snapshot) ------->  đọc snapshot đã công bố
                                   gọi provider theo thread-safety contract
                                   không gọi ServiceLoader
```

Cách này tách trạng thái không thread-safe của discovery khỏi đường request; phù hợp khi provider set ít thay đổi. `List.copyOf` chỉ bất biến *cấu trúc danh sách*, **không biến các provider stateful thành thread-safe**. Cần giải quyết provider state ở phần 5.

Khi refresh, registry xây snapshot mới hoàn chỉnh rồi **hoán đổi tham chiếu một lần**. Request đang giữ snapshot cũ có thể hoàn thành với provider cũ. Không được đóng provider cũ khi vẫn còn request đang dùng nó.

### Chiến lược B — Đồng bộ hóa toàn bộ truy cập tới loader

Nếu nhất thiết nhiều thread cần gọi loader, dùng **cùng một lock** bảo vệ cả discovery, iteration, stream terminal operation và `reload()`. Khóa chỉ có hiệu lực nếu *mọi* đường dùng loader tuân thủ nó. Với stream lazy, không được khóa lúc tạo stream rồi thả khóa trước khi xử lý stream.

```java
synchronized (loader) {
    List<Codec> snapshot = new ArrayList<>();
    for (Codec codec : loader) {
        snapshot.add(codec);
    }
    // Phần dữ liệu được trả ra nên là bản sao, tránh rò iterator.
}
```

Đây chỉ là trích đoạn có sẵn biến `loader` và kiểu `Codec`. `synchronized(loader)` là *quy ước khóa của ứng dụng*, không phải cam kết đồng bộ do `ServiceLoader` tự cung cấp. `reload()` cũng phải được thực hiện dưới **cùng lock**. Cách này đúng nếu quản lý nhất quán nhưng dễ tăng contention; thường nên công bố snapshot để request không phải đợi discovery.

### Chiến lược C — Loader riêng theo chủ thể/vòng đời

Có thể tạo `ServiceLoader` riêng cho từng application context, plugin manager hoặc thread (nếu thật sự cần phân vùng), rồi không dùng instance đó đồng thời. Cần đánh đổi chi phí discovery/cache và đảm bảo chọn đúng class loader. **Loader riêng mỗi request** thường là lãng phí và khiến vòng đời khó quản lý; **loader static dùng chung toàn JVM** lại có nguy cơ giữ tham chiếu của ứng dụng đã bị dỡ.

Không có một lựa chọn toàn cục đúng cho mọi hệ thống; lựa chọn phụ thuộc khả năng thay provider, isolation giữa tenant/app, và ai sở hữu tài nguyên.

## 5. Chính sách chia sẻ provider instance

Giải quyết thread-safety của `ServiceLoader` **chưa đủ**. Sau khi công bố `List<S>`, cùng một instance có thể được nhiều request gọi đồng thời. Cần ghi rõ hợp đồng provider:

| Loại provider | Có thể giữ và dùng chung không? | Gợi ý triển khai |
| --- | --- | --- |
| Stateless, immutable, không dùng state không thread-safe | Thường có, khi được khởi tạo và công bố an toàn | Singleton ở cấp application/plugin registry; snapshot chung |
| Stateful nhưng tự đồng bộ hoặc thread-safe theo tài liệu | Có, trong giới hạn contract | Chú ý throughput, shutdown và tài nguyên |
| Stateful, không thread-safe (bộ đệm mutable, session, transaction state) | Không gọi đồng thời cùng instance | Tạo instance riêng theo request/session, dùng factory hoặc pool có quy tắc |
| Provider chứa tài nguyên cần đóng | Chỉ giữ trong vòng đời sở hữu rõ ràng | Định nghĩa `close`/`AutoCloseable`, đợi in-flight requests kết thúc |
| Provider của tenant/plugin version riêng | Không trộn phạm vi dù cùng interface | Registry/snapshot/class loader hoặc module layer theo tenant/version |

**Không được suy luận phạm vi instance từ `ServiceLoader`.** Việc iterator cache một instance không biến provider thành thread-safe singleton. Ngược lại, gọi `Provider.get()` không phải một bảo đảm API rằng “mỗi request sẽ được một object mới độc lập”; factory method của provider có thể chủ động trả singleton. Khi cần request-scoped object, hãy công bố **factory với hợp đồng tạo instance riêng** và xác minh hành vi của implementation.

Ví dụ provider xử lý `String` thuần, không giữ mutable field, thường phù hợp để chia sẻ. Provider chứa `StringBuilder` dùng làm buffer chung giữa nhiều request có nguy cơ race; cần biến buffer thành biến local hoặc thiết kế isolation phù hợp. Tạo `ConcurrentHashMap` để lưu kết quả không tự làm toàn bộ các field/phương thức của provider an toàn.

### Công bố đúng theo Java Memory Model

`List.copyOf(...)` trả một list không cho sửa cấu trúc; nếu gán vào một biến shared thông thường mà thiếu quan hệ *happens-before*, reader có thể không nhận bản cập nhật theo cách được bảo đảm. Dùng:

- `private static volatile List<S> active = List.of();` và một writer xây xong list rồi gán;
- hoặc `AtomicReference<List<S>>` với `set/get`, phù hợp khi cần các thao tác atomic thêm.

Provider phải được khởi tạo đầy đủ trước khi publish; không làm rò `this` trong constructor. Sau khi publish, provider shared vẫn phải bảo đảm các quy tắc thread-safety riêng nếu trạng thái của nó thay đổi.

## 6. Ví dụ chạy độc lập trên Java 17: discovery một luồng, snapshot chia sẻ, reload có kiểm soát

Ví dụ có **một** provider stateless đổi chữ sang chữ hoa. Thread main sở hữu `ServiceLoader`; hai worker chỉ dùng snapshot đã công bố. Sau khi cả hai worker hoàn tất, main gọi `reload()` để tái khám phá. Chương trình cho thấy cache iterator trước reload, instance mới sau reload và snapshot cũ vẫn hoạt động.

Tạo cấu trúc:

```text
service-loader-demo/
├── src/
│   └── demo/
│       ├── api/Processor.java
│       ├── provider/UpperProcessor.java
│       └── App.java
└── resources/
    └── META-INF/
        └── services/
            └── demo.api.Processor
```

**`src/demo/api/Processor.java`**

```java
package demo.api;

public interface Processor {
    String process(String input);
}
```

**`src/demo/provider/UpperProcessor.java`**

```java
package demo.provider;

import demo.api.Processor;
import java.util.Locale;

public final class UpperProcessor implements Processor {
    public UpperProcessor() {}

    @Override
    public String process(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
```

**`resources/META-INF/services/demo.api.Processor`** (một dòng tên class provider, không có extension):

```text
demo.provider.UpperProcessor
```

Đây là đăng ký provider ở **class path**. File phải nằm dưới `META-INF/services/` trong classpath runtime; tên file là **fully qualified name của service interface**, dòng nội dung là **fully qualified name của provider implementation**. Với Java module có `module-info.java`, có thể dùng `uses`/`provides ... with ...` thay cho file cấu hình classpath.

**`src/demo/App.java`**

```java
package demo;

import demo.api.Processor;
import java.util.*;
import java.util.concurrent.*;

public final class App {
    // Bản tham chiếu được publish atomically sau discovery.
    private static volatile List<Processor> active = List.of();

    // Chỉ registry/main thread gọi phương thức này.
    private static void publish(ServiceLoader<Processor> loader) {
        List<Processor> found = new ArrayList<>();
        for (Processor p : loader) {
            found.add(p);
        }
        if (found.isEmpty()) {
            throw new IllegalStateException("No providers");
        }
        active = List.copyOf(found);
    }

    public static void main(String[] args) throws Exception {
        // Tránh phụ thuộc TCCL ngẫu nhiên của worker pool.
        ServiceLoader<Processor> loader =
            ServiceLoader.load(Processor.class, App.class.getClassLoader());

        publish(loader);
        List<Processor> first = active; // chụp snapshot một lần

        System.out.println("providers=" + first.size());
        System.out.println(
            "cached=" + (loader.iterator().next() == first.get(0)));

        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            // Workers chỉ dùng provider stateless trong snapshot,
            // không đụng đến chính đối tượng ServiceLoader.
            Future<String> a =
                pool.submit(() -> first.get(0).process("hello"));
            Future<String> b =
                pool.submit(() -> first.get(0).process("world"));

            // Lấy kết quả theo thứ tự a rồi b nên stdout ổn định.
            System.out.println("one=" + a.get());
            System.out.println("two=" + b.get());
        } finally {
            pool.shutdown();
        }

        // Đã hoàn tất hai Future; giờ main mới thao tác loader.
        loader.reload();
        publish(loader);

        System.out.println(
            "newAfterReload=" + (active.get(0) != first.get(0)));
        System.out.println(
            "oldStillWorks=" + first.get(0).process("java"));
    }
}
```

Tại thư mục `service-loader-demo`, chạy bằng **PowerShell** trên Windows:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out src/demo/api/Processor.java src/demo/provider/UpperProcessor.java src/demo/App.java
Copy-Item -Recurse -Force resources/META-INF out/
java -cp out demo.App
```

Các lệnh tạo class file ở `out` và chép metadata SPI vào `out/META-INF/services`; vì thế Java tìm thấy provider qua classpath `out`. Trên macOS/Linux có thể thay bước chép bằng `cp -R resources/META-INF out/`.

**Stdout đã kiểm tra với `javac --release 17` và `java`:**

```text
providers=1
cached=true
one=HELLO
two=WORLD
newAfterReload=true
oldStillWorks=JAVA
```

Phân tích:

1. `ServiceLoader.load(..., App.class.getClassLoader())` chỉ rõ class loader cần tìm SPI. `publish` duyệt iterator trên main thread, khởi tạo `UpperProcessor` rồi lưu trong `List.copyOf`. Biến `volatile active` công bố tham chiếu với visibility phù hợp.
2. `loader.iterator().next() == first.get(0)` là `true`: cùng `ServiceLoader` đã cache instance từ lượt duyệt trước; chưa gọi `reload()`.
3. Hai tác vụ dùng cùng provider stateless; chúng không chạm vào loader. `Future.get()` giúp lấy kết quả theo thứ tự ổn định và bảo đảm task đã hoàn tất trước khi reload.
4. `reload()` xóa cache. Lượt `publish` kế tiếp tạo lại instance của provider classpath có constructor public không tham số, nên identity khác. Đây là **hành vi trong ví dụ này**, không bảo đảm mọi provider/factory ở mọi cấu hình luôn tạo object mới.
5. Biến `first` vẫn giữ tham chiếu snapshot cũ, nên `oldStillWorks=JAVA`. Điều này chứng minh `reload()` **không hủy hay đóng đối tượng đã trao cho ứng dụng**.

**Giới hạn có chủ đích của ví dụ:** chỉ một provider được cấu hình; main thread là chủ duy nhất của loader; `reload` xảy ra sau khi hai tác vụ kết thúc. Nếu triển khai hot reload trong khi request đang chạy, cần quản lý thời gian sống của snapshot và đóng tài nguyên theo phần tiếp theo. Không suy luận từ code rằng mọi provider share được giữa các thread.

## 7. Reload, snapshot version và thu hồi tài nguyên

`reload()` phục vụ việc khám phá lại provider ở một loader hiện có. Nó **không**:

- làm các `ServiceLoader.Provider<S>` hoặc `S` đang được giữ ở nơi khác tự mất hiệu lực;
- gọi `close()` trên provider hoặc chờ request đang dùng provider kết thúc;
- hủy class loader, unload class hay tự mở rộng tập class/module mà loader hiện tại nhìn thấy;
- khóa các thread khác đang sử dụng loader;
- đảm bảo provider sau reload có identity mới trong mọi kiểu cấu hình.

Một quy trình refresh an toàn trong ứng dụng nhiều luồng:

1. Chỉ một **registry thread** chịu trách nhiệm discovery/reload. Với nhiều lệnh refresh, tuần tự hóa chúng bằng lock/queue phù hợp.
2. Tạo và validate **snapshot mới**: đúng service type, version, feature/capability, cấu hình và trạng thái khởi tạo; nếu thất bại thì giữ snapshot đang phục vụ, tùy chính sách lỗi.
3. Công bố snapshot mới bằng một lần gán `volatile` hoặc `AtomicReference.set`. Các request mới đọc snapshot hiện hành; request đã giữ snapshot cũ tiếp tục với dữ liệu nhất quán.
4. Ngừng cấp request mới cho snapshot cũ. **Chờ in-flight operations hoàn thành** hoặc dùng reference counting/lease/grace period trước khi đóng provider cũ theo hợp đồng.
5. Bỏ tham chiếu từ registry, static cache, listener, thread-local, executor/task và các cơ chế đăng ký khác tới provider/class loader cũ khi muốn dỡ plugin. Garbage collector chỉ thu hồi khi thực sự không còn strong reference.

Có thể hình dung:

```text
T0: active -> Snapshot V1 -> Provider V1
                    ^ request A đã lấy V1

T1: registry tạo Snapshot V2, chưa công bố
T2: active -> Snapshot V2 -> Provider V2
                                 ^ request B mới
    request A vẫn có V1, hoàn tất an toàn
T3: hết request giữ V1 -> đóng tài nguyên V1 (nếu ownership cho phép)
T4: bỏ tham chiếu V1 và loader cũ khi gỡ phiên bản
```

Trong triển khai thật, điều kiện “hết request giữ V1” phải có cơ chế cụ thể; **`List.copyOf` và `volatile` không giải quyết việc chờ in-flight**. Nếu provider dùng chung giữa V1/V2, đóng theo mỗi snapshot có thể làm hỏng provider vẫn được sử dụng; cần xác định ownership và chỉ đóng một lần.

Provider không bắt buộc triển khai `AutoCloseable`. Nếu interface SPI có yêu cầu tài nguyên, có thể định nghĩa một interface kế thừa `AutoCloseable` hoặc adapter quản lý lifecycle một cách tường minh. Không được coi `reload()` là thao tác giải phóng socket, thread, file hoặc kết nối cơ sở dữ liệu.

## 8. Phạm vi giữ ServiceLoader theo ClassLoader và ModuleLayer

### `load(Service.class)` và thread context class loader

`ServiceLoader.load(S.class)` sử dụng **thread context class loader (TCCL)** ở thời điểm gọi. Trong application server, plugin host hoặc thread pool, TCCL có thể khác nhau giữa các luồng/app. Vì vậy hai nơi gọi cùng API có thể khám phá **tập provider khác nhau**.

Một lưu ý quan trọng từ JavaDoc: không nên cache một loader tạo qua `load(S.class)` ở phạm vi **toàn JVM** nếu nhiều ứng dụng/context có class loader riêng. Cache dài hạn có thể nhìn thấy provider của ứng dụng khác hoặc giữ class loader làm rò rỉ bộ nhớ.

Khi đã biết chủ sở hữu, ưu tiên thiết kế rõ ràng:

- `ServiceLoader.load(S.class, selectedClassLoader)`: chỉ rõ phạm vi class loader phù hợp với SPI và provider.
- `ServiceLoader.load(moduleLayer, S.class)`: duyệt provider trong module layer được chỉ định và các layer tổ tiên theo API; không dùng cách này để tìm provider ở unnamed modules như classpath.
- Giữ loader/registry ở **cấp application/plugin manager/tenant** phù hợp; không biến nó thành global cache không phân biệt bối cảnh.

Class cùng fully qualified name nhưng do hai class loader khác nhau định nghĩa là hai **kiểu khác nhau**. Service API cần được chia sẻ qua class loader/module quan hệ đúng; nếu plugin nạp lại bằng loader mới nhưng provider đang cast sang bản sao interface cũ, có thể phát sinh `ClassCastException` hoặc `ServiceConfigurationError`.

### Reload không đồng nghĩa hot deployment

`reload()` chỉ buộc loader **tra cứu lại** theo môi trường hiện nó biết. Để bổ sung/đổi code plugin thực sự, hệ thống có thể cần class loader/module layer mới, provider registry mới và chính sách chuyển version. Nếu vẫn dùng class loader cũ và giữ tham chiếu tới class cũ, Java không tự nạp đè class chỉ vì gọi `reload()`. Nếu muốn unload, không được để static cache, TCCL, background thread hay listener vô tình giữ loader cũ.

## 9. Truy cập bằng stream và Provider.get(): lưu ý về instance scope

`ServiceLoader.Provider<S>` giúp xem `type()` trước khi gọi `get()`. Với module có provider factory method, kiểu từ `type()` phản ánh kiểu trả về của provider method, không nhất thiết là class triển khai factory.

Tránh dạng sau nếu mục tiêu là **một instance duy nhất trên application** mà chưa có chính sách rõ:

```java
ServiceLoader.load(Codec.class)
    .stream()
    .map(ServiceLoader.Provider::get)
    .forEach(codec -> register(codec));
```

Đoạn này là minh họa cần interface `Codec` và hàm `register` trong ứng dụng. Nó có thể phù hợp cho registration tuần tự, nhưng **không đủ** để chứng minh `get()` tạo một singleton, instance mới mỗi lần hoặc thread-safe. Nếu cần chọn provider theo metadata, hãy lọc `Provider.type()` trước, gọi `get()` ở nơi có ownership rõ ràng, và giữ kết quả vào snapshot/registry theo chính sách.

Khi stream đã được lấy từ loader, **xử lý nó dưới quyền sở hữu của registry thread**; không phát tán stream/iterator để request khác tiếp tục duyệt. `stream().parallel()` cũng không giải quyết thread-safety của loader; nếu muốn parallel execution, hãy hoàn tất discovery rồi mới áp dụng concurrency cho các provider đủ điều kiện.

## 10. Lỗi dễ gặp khi vận hành

| Hiện tượng | Nguyên nhân | Xử lý |
| --- | --- | --- |
| `ConcurrentModificationException` lúc `next()` hoặc stream traversal | `reload()` đã xóa cache sau khi iterator/stream được tạo | Bỏ iterator/stream cũ; không reload trong lúc đang duyệt; tuần tự hóa registry |
| Kết quả thiếu/provider khác giữa các thread | Discovery dùng TCCL khác nhau hoặc không cùng module layer | Chỉ rõ class loader/layer theo application/plugin scope |
| Provider bị gọi đồng thời gây kết quả sai | Provider chứa mutable state không thread-safe | Stateless/immutable, đồng bộ hợp lý hoặc instance per request |
| Gỡ plugin nhưng RAM/class loader không được thu hồi | Snapshot, static cache, listener, thread-local hoặc thread còn giữ provider/loader | Đóng theo lifecycle rồi loại bỏ mọi strong reference phù hợp |
| Sau `reload()` đối tượng cũ vẫn chạy | Caller vẫn giữ tham chiếu tới provider cũ | Cần versioned snapshot và quy trình retired/drain |
| Sau `reload()` vẫn không thấy plugin mới | Class loader/layer hiện tại không nhìn thấy provider mới | Xem lại deployment, SPI metadata và phạm vi loader; có thể cần loader mới |
| `ServiceConfigurationError` trong lúc duyệt | File `META-INF/services` sai, class không tải được, constructor/provider method lỗi | Kiểm tra packaging, module `uses/provides`, quyền và lỗi nguyên nhân; fail fast khi bootstrap |
| Cùng provider được khởi tạo nhiều lần ngoài ý định | Tạo nhiều ServiceLoader, gọi `Provider.get()` tùy tiện, reload | Định nghĩa scope và cache ở registry; không dựa vào singleton ngầm |
| Request chậm khi chọn provider | Lazy discovery/constructor chạy trên đường request | Khám phá và validate trước lúc nhận request; publish snapshot đã sẵn sàng |

**Lưu ý `ServiceConfigurationError`:** đây là subclass của `Error`; lazy discovery có thể làm `hasNext()`, `next()` hoặc stream terminal operation phát sinh lỗi muộn. Bọc xử lý tại ranh giới bootstrap/registry để trả thông tin cấu hình hữu ích. Không nên bắt mọi `Throwable` rồi âm thầm tiếp tục với tập provider thiếu; điều đó có thể tạo hành vi không nhất quán.

## 11. Quy tắc chọn phạm vi theo bài toán

| Bài toán | Phạm vi nên xem xét | Cách truy cập |
| --- | --- | --- |
| Dịch vụ không đổi trong suốt vòng đời app | Một registry per application, snapshot bất biến | Registry duyệt một lần; request chỉ đọc snapshot |
| Plugin có hot reload | Registry per plugin context với snapshot version | Discovery/reload tuần tự; atomic publish; drain phiên bản cũ |
| Nhiều tenant/app chung JVM | Loader/layer/registry cách ly theo tenant/app | Không cache `ServiceLoader.load(S.class)` toàn VM |
| Provider stateless, thread-safe | Instance dùng chung theo application/plugin lifetime | Công bố an toàn, gọi trực tiếp từ snapshot |
| Provider stateful không thread-safe | Instance hoặc state gắn request/session | Factory/pool theo hợp đồng, không share instance mù quáng |
| Cần truy cập loader trực tiếp từ nhiều thread | Loader dùng lock chung hoặc phân vùng owner | Mọi iteration/stream/reload đi cùng một cơ chế tuần tự hóa |
| Cần dỡ plugin và trả tài nguyên | Owner/lifecycle tường minh, không chỉ GC | Đợi in-flight, close nếu được sở hữu, xóa strong references |

### Checklist trước khi đưa vào production

- [ ] Xác định ai sở hữu `ServiceLoader`; không có hai thread đồng thời discovery/reload trên cùng instance.
- [ ] Chọn đúng `ClassLoader`/`ModuleLayer` và không vô tình cache ở phạm vi JVM/tenant quá rộng.
- [ ] Phân biệt cache provider instance của iterator và descriptor của stream; không dựa vào `Provider.get()` như chính sách singleton/per-request.
- [ ] Khám phá và validate trước request; công bố snapshot qua `volatile`/`AtomicReference` hoặc cơ chế happens-before tương đương.
- [ ] Chứng minh hoặc quy định thread-safety, scope, resource ownership của **provider instances** riêng biệt.
- [ ] Với reload, bỏ iterator/stream cũ, tạo snapshot version mới, quản lý in-flight requests và đóng tài nguyên cũ đúng thời điểm.
- [ ] Kiểm tra SPI metadata, `ServiceConfigurationError`, thứ tự provider và hành vi khi không có hoặc có nhiều provider.
- [ ] Khi unload class loader, kiểm tra static cache, listener, thread-local, background threads và các tham chiếu còn sống.

Tham khảo API chính thức cho Java 17: [`ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html) và [`ServiceLoader.Provider`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html).

**Kết luận:** `ServiceLoader` là đối tượng **discovery có trạng thái, lazy cache và không thread-safe**. Provider là đối tượng **thực thi có chính sách thread-safety và vòng đời riêng**. Thiết kế đáng tin cậy thường cho một registry sở hữu việc discovery/reload, công bố snapshot an toàn cho request và giải phóng instance/class loader cũ chỉ khi không còn người dùng phụ thuộc vào chúng.