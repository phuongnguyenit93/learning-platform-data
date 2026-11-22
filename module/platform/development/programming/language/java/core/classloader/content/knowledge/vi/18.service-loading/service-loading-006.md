# Khám phá provider và khởi tạo lười với ServiceLoader trong Java

## 1. Service provider là gì và vì sao cần khám phá động?

Trong Java, một **service** thường là một interface hoặc abstract class công khai mô tả hợp đồng mà ứng dụng cần; **service provider** là một implementation có thể được cài đặt và phát hiện lúc chạy. Mã tiêu thụ chỉ phụ thuộc vào **service contract**, không phải tên lớp triển khai cụ thể.

Ví dụ, một ứng dụng hỗ trợ nhiều bộ giải mã:

```java
package example.spi;

public interface Codec {
    String decode(byte[] input);
}
```

Đây là **file interface minh họa**, không phải một ví dụ chương trình độc lập. Nhà cung cấp A, B có thể triển khai interface này và đăng ký qua metadata hoặc `module-info.java`. Ứng dụng dùng `ServiceLoader<Codec>` để khám phá các provider có sẵn.

`java.util.ServiceLoader<S>` là API chuẩn cho **service-provider loading (SPI)**, không phải container dependency injection tổng quát. Nó có thể tìm implementation từ:
- **Classpath/unnamed modules**: tệp metadata `META-INF/services/<binary-service-name>`.
- **Named modules (JPMS)**: khai báo `provides ... with ...` trong module descriptor; consumer khai báo `uses ...`.
- **ModuleLayer** tạo động: có overload để tìm providers trong layer và các layer cha.

Điều quan trọng của đề bài là **khám phá provider (discovery)** và **khởi tạo lười (lazy instantiation)** là **hai hoạt động có thể xảy ra ở thời điểm khác nhau**.

## 2. “Lazy” thực sự nghĩa là gì?

Lệnh:

```java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);
```

**Không có nghĩa** Java ngay lập tức đọc xong mọi service descriptors, nạp mọi provider class và gọi constructor của tất cả provider. Thay vào đó, `ServiceLoader` cung cấp cơ chế truy vấn **theo nhu cầu**:

1. Tạo đối tượng `ServiceLoader` cho một service type và một ngữ cảnh class loader/layer.
2. Khi bắt đầu duyệt, tìm các provider declarations phù hợp từ module descriptors hoặc `META-INF/services`.
3. Tải và kiểm tra provider type khi cần.
4. **Instantiate provider** khi consumer cần một provider instance (ví dụ `Iterator.next()`, `findFirst()` hoặc `Provider.get()`).
5. Giữ cache các provider đã tìm/nạp/khởi tạo theo ngữ nghĩa của phương thức duyệt, để những lần duyệt tiếp theo có thể dùng lại.
6. `reload()` xóa cache của chính đối tượng `ServiceLoader`; provider sẽ được khám phá/nạp/khởi tạo lại khi duyệt tiếp, nhưng class đã định nghĩa và static initializer đã chạy thành công **không tự được reset**.

Sơ đồ:

```text
ServiceLoader.load(Service.class)
             │
             ▼
       ServiceLoader object
             │
             ├── iterator()
             │      ├── hasNext() → khám phá tên/provider khi cần
             │      └── next()    → lấy/tạo provider instance
             │
             ├── findFirst()      → lấy/tạo provider đầu tiên nếu có
             │
             └── stream()
                    └── Provider<S>
                          ├── type() → Class<?> của provider type
                          └── get()  → provider instance
             │
             ▼
          Provider được dùng
```

**Lưu ý:** các phương thức tìm `hasNext()`/duyệt stream **có thể làm I/O, tìm tệp cấu hình, tải class và phát sinh lỗi**. “Lazy” không có nghĩa chúng luôn miễn phí. Điều được trì hoãn là **khám phá và instantiate theo nhu cầu**, thay vì tạo mọi provider ngay khi gọi `ServiceLoader.load`.

## 3. Hai khái niệm cần tách: loading và initialization

Trong JVM:
- **Loading**: ClassLoader/JVM tìm và định nghĩa runtime class.
- **Linking**: JVM verification, preparation, resolution theo quy tắc.
- **Initialization**: JVM chạy các biểu thức khởi tạo static field và `static { ... }` khi có active use thích hợp.
- **Instantiation**: tạo **object instance**, chạy constructor và các initializers liên quan.

Một provider class có thể được **load mà chưa initialized**. Khi `ServiceLoader.Provider.type()` trả về `Class<?>`, việc lấy kiểu provider thông thường không yêu cầu tạo instance. Ngược lại, khi `Provider.get()` tạo object bằng constructor hay provider factory method, class sẽ được khởi tạo theo quy tắc Java nếu chưa từng initialized.

Ví dụ:

```java
// Trích đoạn: providerClass đã tồn tại ở loader được chọn.
Class<?> providerClass =
        Class.forName("demo.impl.Alpha", false, providerLoader);
// Chưa chủ động yêu cầu chạy Alpha.<clinit>.

Object provider = providerClass.getDeclaredConstructor().newInstance();
// Có thể buộc khởi tạo Alpha và chạy constructor.
```

Đoạn này là trích đoạn reflection, **không phải quy trình thay thế đầy đủ cho ServiceLoader**. ServiceLoader còn kiểm tra service contract, metadata, module rules và provider constructor/factory.

**Không đánh đồng** “provider đã được phát hiện” với “provider instance đã được tạo”, và cũng không đánh đồng “object ServiceLoader đã được tạo” với “provider đã được tìm thấy”.

## 4. API chính của ServiceLoader

| API | Kết quả | Mức độ lazy cần nhớ |
|---|---|---|
| `ServiceLoader.load(S.class)` | Tạo service loader theo **TCCL** hiện tại | Chưa instantiate mọi providers |
| `ServiceLoader.load(S.class, loader)` | Dùng explicit `ClassLoader` | Cũng khám phá theo nhu cầu |
| `ServiceLoader.load(layer, S.class)` | Tìm providers từ `ModuleLayer` và các parent layers | Không tìm provider từ unnamed modules theo overload này |
| `serviceLoader.iterator()` | `Iterator<S>` | `hasNext` có thể khám phá; `next` lấy/tạo instance |
| `serviceLoader.findFirst()` | `Optional<S>` | Tương đương lấy provider đầu tiên từ iterator |
| `serviceLoader.stream()` | `Stream<ServiceLoader.Provider<S>>` | Xem provider descriptions/type trước khi tạo instance |
| `provider.type()` | `Class<? extends S>` | Xem kiểu mà không cần instantiate provider |
| `provider.get()` | `S` | Lấy hoặc tạo instance theo provider contract |
| `serviceLoader.reload()` | `void` | Xóa cache providers của chính ServiceLoader |

Các overload `load` **không có cùng ngữ cảnh tìm kiếm**. Với ứng dụng plugin, chọn đúng loader hoặc layer quan trọng không kém việc chọn interface service.

## 5. Ví dụ đầy đủ Java 17+: provider classpath và lazy instantiation

Ta sẽ tạo một service interface `demo.spi.Greeting`, hai provider classes và một host. Provider chứa static initializer và constructor in ra console, để thấy rõ **khi nào** Java thực sự tạo instance.

### 5.1. Cấu trúc thư mục

```text
spi-demo/
├── src/
│   ├── demo/
│   │   ├── spi/Greeting.java
│   │   ├── impl/AlphaGreeting.java
│   │   ├── impl/BetaGreeting.java
│   │   └── app/Host.java
│   └── META-INF/
│       └── services/
│           └── demo.spi.Greeting
└── out/
    ├── demo/...
    └── META-INF/services/demo.spi.Greeting
```

### 5.2. Service contract: src/demo/spi/Greeting.java

```java
package demo.spi;

public interface Greeting {
    String message();
}
```

### 5.3. Provider A: src/demo/impl/AlphaGreeting.java

```java
package demo.impl;

import demo.spi.Greeting;

public final class AlphaGreeting implements Greeting {
    static {
        System.out.println("Alpha initialized");
    }

    public AlphaGreeting() {
        System.out.println("Alpha constructed");
    }

    @Override
    public String message() {
        return "alpha";
    }
}
```

### 5.4. Provider B: src/demo/impl/BetaGreeting.java

```java
package demo.impl;

import demo.spi.Greeting;

public final class BetaGreeting implements Greeting {
    static {
        System.out.println("Beta initialized");
    }

    public BetaGreeting() {
        System.out.println("Beta constructed");
    }

    @Override
    public String message() {
        return "beta";
    }
}
```

### 5.5. Provider configuration file

Tạo tệp đúng đường dẫn:

```text
src/META-INF/services/demo.spi.Greeting
```

Nội dung **hai dòng theo thứ tự**:

```text
demo.impl.AlphaGreeting
demo.impl.BetaGreeting
```

Tên **tệp** phải trùng **binary name** của service type, không phải tên provider; nội dung chứa binary names của implementations. Không thêm `.class` vào tên tệp metadata.

### 5.6. Host: src/demo/app/Host.java

```java
package demo.app;

import demo.spi.Greeting;
import java.util.Iterator;
import java.util.ServiceLoader;

public final class Host {
    private static void iteratorDemo() {
        ServiceLoader<Greeting> services =
                ServiceLoader.load(
                        Greeting.class,
                        Host.class.getClassLoader()
                );

        System.out.println("loader created");
        Iterator<Greeting> items = services.iterator();
        System.out.println("iterator created");

        System.out.println("has first: " + items.hasNext());
        System.out.println("before first next");
        Greeting first = items.next();
        System.out.println("first message: " + first.message());

        System.out.println("has second: " + items.hasNext());
        System.out.println("before second next");
        Greeting second = items.next();
        System.out.println("second message: " + second.message());

        Greeting cached = services.iterator().next();
        System.out.println("first cached object: " + (cached == first));

        services.reload();
        System.out.println("after reload");
        Greeting recreated = services.iterator().next();
        System.out.println("new first instance: " + (recreated != first));
    }

    private static void streamDemo() {
        ServiceLoader<Greeting> services =
                ServiceLoader.load(
                        Greeting.class,
                        Host.class.getClassLoader()
                );

        System.out.println("loader created");
        ServiceLoader.Provider<Greeting> provider =
                services.stream().findFirst().orElseThrow();

        System.out.println("provider type: "
                + provider.type().getName());
        System.out.println("before provider get");

        Greeting instance = provider.get();
        System.out.println("message: " + instance.message());
    }

    public static void main(String[] args) {
        if (args.length == 1 && "stream".equals(args[0])) {
            streamDemo();
        } else {
            iteratorDemo();
        }
    }
}
```

Chương trình có hai chế độ chạy trong **hai JVM processes riêng** để static initializer của Alpha không bị gọi sẵn từ chế độ khác. Cả hai chế độ dùng cùng interface, implementations và metadata.

### 5.7. Biên dịch và chuẩn bị resource

Tại thư mục `spi-demo`, dùng JDK 17+.

Trên Bash:

```bash
mkdir -p out/META-INF/services
javac --release 17 -d out src/demo/spi/Greeting.java src/demo/impl/AlphaGreeting.java src/demo/impl/BetaGreeting.java src/demo/app/Host.java
cp src/META-INF/services/demo.spi.Greeting out/META-INF/services/demo.spi.Greeting
```

Trên Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force out/META-INF/services | Out-Null
javac --release 17 -d out src/demo/spi/Greeting.java src/demo/impl/AlphaGreeting.java src/demo/impl/BetaGreeting.java src/demo/app/Host.java
Copy-Item src/META-INF/services/demo.spi.Greeting out/META-INF/services/demo.spi.Greeting
```

File cấu hình provider **không được javac tự biên dịch/sao chép**; phải copy resource hoặc dùng build tool (Maven/Gradle) đưa nó vào artifact cuối cùng.

Kết quả nên có:

```text
out/
├── demo/
│   ├── spi/Greeting.class
│   ├── impl/AlphaGreeting.class
│   ├── impl/BetaGreeting.class
│   └── app/Host.class
└── META-INF/services/demo.spi.Greeting
```

### 5.8. Chạy chế độ iterator

```bash
java -cp out demo.app.Host
```

Stdout:

```text
loader created
iterator created
has first: true
before first next
Alpha initialized
Alpha constructed
first message: alpha
has second: true
before second next
Beta initialized
Beta constructed
second message: beta
first cached object: true
after reload
Alpha constructed
new first instance: true
```

Giải thích:

1. `load(Greeting.class, loader)` tạo đối tượng service loader: chưa in gì từ Alpha/Beta.
2. `iterator()` tạo iterator; `hasNext()` tìm metadata và cho biết có provider đầu tiên, nhưng chưa gọi constructor Alpha.
3. `next()` lấy instance đầu tiên, nên static initializer Alpha chạy lần đầu, rồi constructor Alpha chạy, rồi `message()` trả `alpha`.
4. Provider B chưa được khởi tạo ở thời điểm Alpha được dùng. Khi gọi `next()` lần hai, Beta mới được instantiate.
5. Một iterator mới từ **cùng ServiceLoader** sẽ trả lại provider objects đã cache trước khi tìm các provider còn lại. Vì thế `cached == first` in `true`.
6. `reload()` xóa provider cache. Lần duyệt tiếp theo tạo một **instance Alpha mới**, nhưng **không chạy lại** `Alpha.<clinit>`: static initialization thành công diễn ra một lần cho cùng runtime class.
7. `reload()` không định nghĩa lại Alpha bằng ClassLoader mới, không đổi binary name hoặc bytecode, và không tự “hot reload” JAR đã ghi đè.

### 5.9. Chạy chế độ stream trong JVM riêng

```bash
java -cp out demo.app.Host stream
```

Stdout:

```text
loader created
provider type: demo.impl.AlphaGreeting
before provider get
Alpha initialized
Alpha constructed
message: alpha
```

`stream().findFirst()` trả một `Provider<Greeting>` descriptor. `provider.type()` cho biết class provider mà **không tạo instance**, nên static initializer Alpha chưa chạy từ bước này. `provider.get()` mới lấy provider instance, kích hoạt initialization và constructor nếu đây là lần đầu.

**Không được suy ra** rằng `ServiceLoader.Provider.get()` luôn memoize một object cụ thể khi gọi nhiều lần. Đừng dùng `get() == get()` như hợp đồng singleton. Khi cần chia sẻ một instance theo vòng đời, ứng dụng nên quản lý nó, hoặc dùng provider factory/lifecycle có thiết kế rõ ràng.

## 6. Cơ chế tìm metadata trên classpath

Khi dùng provider configuration ở unnamed module/classpath, `ServiceLoader` tìm resources theo đường dẫn:

```text
META-INF/services/<binary-name-of-service>
```

Với ví dụ trên:

```text
META-INF/services/demo.spi.Greeting
```

Các tệp provider configuration có những quy tắc quan trọng:

- Phải được mã hóa **UTF-8**.
- Mỗi dòng hợp lệ chứa **binary name đầy đủ** của một provider class.
- Dòng trống và khoảng trắng/tab bao quanh tên được bỏ qua.
- Ký tự `#` mở đầu comment; phần còn lại của dòng sau `#` bị bỏ qua.
- Một provider class name lặp trong một hoặc nhiều configuration files sẽ được bỏ qua ở những lần trùng tên khi loader xử lý theo contract.
- Provider có thể nằm trong JAR khác tệp service configuration, miễn classloader được sử dụng **nhìn thấy** implementation.
- Thứ tự các provider trong **một file cấu hình** ảnh hưởng thứ tự duyệt; với nhiều resources, thứ tự phụ thuộc `ClassLoader.getResources` và những quy tắc phối hợp provider modules. Không nên xem “first provider” là thứ tự toàn cục ổn định khi triển khai phức tạp.

Ví dụ metadata hợp lệ:

```text
# Các provider dành cho Greeting
demo.impl.AlphaGreeting    # ưu tiên theo file này

demo.impl.BetaGreeting
```

### Sai vị trí và sai tên

Những cấu trúc sau **không tương đương**:

```text
META-INF/services/demo.spi.Greeting      [đúng tên service]
META-INF/services/demo.impl.AlphaGreeting [sai: tên provider]
META-INF/service/demo.spi.Greeting       [sai thư mục]
META-INF/services/demo.spi.Greeting.txt  [sai: thừa extension]
```

Nếu thiếu metadata hoặc metadata nằm sai path, `ServiceLoader` có thể không nhìn thấy provider dù `AlphaGreeting.class` có trên classpath. Ngược lại, metadata có tên provider không tồn tại, không assignable hoặc không có constructor phù hợp có thể gây `ServiceConfigurationError` trong lúc duyệt.

## 7. Khi nào provider được load, link, initialize và instantiate?

Ở classpath provider kiểu constructor, các sự kiện có thể xảy ra như sau:

```text
ServiceLoader.load(S.class, loader)
         │
         └── có object ServiceLoader

iterator.hasNext() / stream operation
         │
         ├── tìm provider configuration
         ├── phân tích provider names
         └── có thể tải/kiểm tra provider classes
                    │
                    ▼
iterator.next() / findFirst() / Provider.get()
         │
         ├── bảo đảm provider sẵn sàng tạo
         ├── initialization của provider class nếu cần
         ├── gọi public no-arg constructor
         └── trả object S
```

Đây là **sơ đồ ý nghĩa**, không phải cam kết `hasNext` tuyệt đối không làm bất kỳ class loading nào; các implementation/JVM có thể liên kết các kiểu theo thời điểm khác nhau.

Khi test, hãy phân biệt **dấu hiệu từ static initializer** và **constructor**:

```java
static {
    System.out.println("Provider class initialized");
}

public ExampleProvider() {
    System.out.println("Provider object constructed");
}
```

Đây là **đoạn trong class**, không phải tệp độc lập. Một static initializer thường chạy một lần cho **mỗi runtime class** khi init thành công. Constructor có thể chạy nhiều lần nếu ứng dụng tạo nhiều provider instances, kể cả sau `ServiceLoader.reload()` hoặc với những ServiceLoader objects khác nhau.

Nếu constructor ném exception, `ServiceLoader` thường trình bày lỗi dưới dạng `ServiceConfigurationError` khi consumer thực sự duyệt/instantiate provider.

## 8. Iterator, findFirst và stream: chọn đúng API

### 8.1. iterator() cho trường hợp muốn các instances

```java
ServiceLoader<Greeting> services = ServiceLoader.load(Greeting.class);
for (Greeting greeting : services) {
    System.out.println(greeting.message());
}
```

Đây là **trích đoạn**, giả định `Greeting` khả dụng và đã import `ServiceLoader`. Enhanced for-loop sử dụng `iterator()`, vì thế có thể instantiate các providers trong quá trình duyệt.

Lưu ý **duyệt không bắt buộc tìm mọi provider ngay**: nếu vòng lặp `break` sau provider đầu tiên, các providers sau có thể chưa được instantiate.

### 8.2. findFirst() cho trường hợp chỉ cần một

```java
Greeting selected = ServiceLoader
        .load(Greeting.class)
        .findFirst()
        .orElseThrow();
```

Đây là trích đoạn. `findFirst()` dùng lazy iteration để lấy provider đầu tiên nếu có; không cần instantiate toàn bộ providers. Nếu không có provider, `Optional` rỗng. Nếu metadata/provider hỏng, **không** bảo đảm trả `Optional.empty()`: vẫn có thể ném `ServiceConfigurationError`.

**Thứ tự provider** là phần của contract và môi trường triển khai. Đừng dùng `findFirst()` để thực thi thứ tự ưu tiên nghiệp vụ trong hệ có nhiều JAR/modules mà không định nghĩa thứ tự một cách rõ ràng.

### 8.3. stream() khi cần chọn theo metadata của provider type

```java
ServiceLoader<Greeting> services = ServiceLoader.load(Greeting.class);
ServiceLoader.Provider<Greeting> selected = services.stream()
        .filter(p -> p.type().getSimpleName().startsWith("Alpha"))
        .findFirst()
        .orElseThrow();

Greeting instance = selected.get();
```

Đây là trích đoạn. `Provider.type()` giúp xem kiểu provider **trước** khi instantiate. Điều này hữu ích nếu cần chọn provider theo annotation/class metadata hoặc theo tên class, tránh khởi tạo mọi candidates tốn kém.

Nhưng:
- Provider type có thể vẫn phải được **load/verified**.
- Đọc annotation qua reflection có những chi phí và ràng buộc riêng.
- `type()` không nhất thiết trả class có public no-arg constructor.
- Với **named-module provider factory method**, `type()` trả **return type của provider()**, không nhất thiết trả class factory khai báo trong `provides`.

**Lưu ý quan trọng:** Duyệt `stream()` và gọi `Provider.get()` không nên được coi là cùng hành vi cache instance với `iterator()`. Thiết kế rõ ràng nơi nào sở hữu provider object.

## 9. Cache của ServiceLoader và ý nghĩa reload()

`ServiceLoader` duy trì cache các providers đã được tải trong quá trình duyệt. Với `iterator()`, những lần duyệt sau của **cùng đối tượng** trước tiên trả lại **các instances đã cache** theo thứ tự khởi tạo, rồi tiếp tục khám phá những provider còn lại.

`reload()`:
- Xóa cache của đối tượng `ServiceLoader`, cho phép những lần duyệt sau khám phá lại provider declarations.
- Có thể tạo **instance mới** từ cùng provider class, nếu được yêu cầu.
- Không xóa object vẫn còn references ở nơi khác.
- Không “unload” class khỏi JVM.
- Không đảm bảo nạp lại class bytes đã được defining loader định nghĩa trước.
- Không tự làm provider đã stop/đã hủy tài nguyên trở lại trạng thái hoạt động.

### Sau reload, iterator cũ còn dùng được không?

Không nên tiếp tục dùng iterator hoặc stream đã lấy từ `ServiceLoader` trước khi gọi `reload()`. Với iterator, `hasNext()` và `next()` có thể ném `ConcurrentModificationException` khi cache đã bị xóa. Hãy tạo **iterator/stream mới** sau khi reload.

### Đọc lại resource thay đổi

Nếu bạn thay file `META-INF/services` trong một nguồn mà loader có thể nhìn thấy, `reload()` có thể khiến ServiceLoader thử khám phá danh sách providers mới. Nhưng việc phản ánh tệp mới còn phụ thuộc cách ClassLoader/resource cache hoạt động; nếu loader đã đóng, hoặc JAR còn nằm trong cache, đơn giản `reload()` có thể không đạt mục tiêu hot deployment.

**Muốn reload một phiên bản class mới thật sự**, thường cần một defining ClassLoader mới, quản lý stop/start plugin và những references cũ. `ServiceLoader.reload()` không thay thế kiến trúc hot-reload.

## 10. Thread Context ClassLoader và phạm vi nhìn thấy provider

Overload:

```java
ServiceLoader.load(Greeting.class)
```

sử dụng **Thread Context ClassLoader (TCCL)** của thread hiện tại theo contract `ServiceLoader`. Điều này hữu ích khi framework nằm ở loader cha nhưng provider implementation chỉ có trong plugin loader con.

Overload explicit:

```java
ServiceLoader.load(Greeting.class, pluginLoader)
```

chọn `pluginLoader` trực tiếp. Đây là trích đoạn cần có biến `pluginLoader` và interface service hợp lệ.

### Mô hình host/plugin

```text
Application ClassLoader
   ├── service API: demo.spi.Greeting
   └── host framework
             │
             ▼ sử dụng TCCL hoặc explicit loader
Plugin URLClassLoader
   ├── demo.impl.AlphaGreeting
   └── META-INF/services/demo.spi.Greeting
```

Nếu framework chỉ hỏi loader của chính nó, nó có thể **không thấy** provider ở child. Đổi TCCL đúng scope hoặc truyền loader cụ thể sẽ giúp khám phá provider.

TCCL là trạng thái ambient trên thread. Khi đổi tạm thời, phải restore:

```java
// Trích đoạn trong code host:
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();
try {
    thread.setContextClassLoader(pluginLoader);
    ServiceLoader<Greeting> services =
            ServiceLoader.load(Greeting.class);
    services.findFirst().ifPresent(
            greeting -> System.out.println(greeting.message())
    );
} finally {
    thread.setContextClassLoader(previous);
}
```

**Không** gọi `Class.forName("demo.impl.AlphaGreeting")` rồi mong nó tự lấy TCCL: overload `Class.forName(String)` dùng loader của caller, không phải TCCL.

### Trong thread pool

Thread pool có worker được tạo **từ trước**. Việc main thread đổi TCCL lúc submit task không đảm bảo worker dùng TCCL mới. Nếu task cần provider của plugin, truyền loader tường minh hoặc dùng wrapper set/restore ngay trong worker thread.

Không để TCCL plugin lưu trên thread pool sau khi request kết thúc: nó vừa có thể gây nhầm provider, vừa giữ strong reference đến plugin ClassLoader, cản trở unloading khi redeploy.

## 11. JPMS: uses/provides trong named modules

Trên module path, service provider được đăng ký bằng `module-info.java` chứ không cần `META-INF/services`.

Tạo service contract:

```java
package svc.api;

public interface Greeting {
    String message();
}
```

Module API:

```java
module svc.api {
    exports svc.api;
}
```

Module consumer:

```java
module svc.host {
    requires svc.api;
    uses svc.api.Greeting;
}
```

Module provider:

```java
module svc.provider {
    requires svc.api;
    provides svc.api.Greeting
            with svc.provider.HelloGreeting;
}
```

Với các descriptors trên:
- `requires svc.api`: consumer/provider đọc service contract.
- `uses svc.api.Greeting`: consumer khai báo nó sử dụng service này; đây là điều kiện quan trọng khi caller nằm trong explicit named module.
- `provides ... with ...`: module provider khai báo implementation.
- Package `svc.provider` **không cần export** chỉ để ServiceLoader instantiate provider theo quy tắc modules.

Không cần ép mọi implementation package thành public API của provider module.

### Named-module provider constructor so với factory method

Đối với **explicit named module** có `provides`, provider có hai cách:

1. Provider class có **public no-arg constructor**, tạo object trực tiếp; class provider phải assignable sang service.
2. Provider class có **public static provider()** không tham số, với return type assignable sang service; ServiceLoader gọi factory method. Lúc này class chứa factory **không nhất thiết implements service**.

Ví dụ provider factory trong module:

```java
// Trích đoạn class trong explicit named provider module:
package svc.provider;

import svc.api.Greeting;

public final class GreetingFactory {
    public static Greeting provider() {
        return new HelloGreeting();
    }
}
```

Đây là **trích đoạn có dependencies**, không phải một chương trình độc lập. Descriptor thích hợp có thể dùng `provides svc.api.Greeting with svc.provider.GreetingFactory;`. Với module factory, `Provider.type()` trả **return type** của `provider()`, không bắt buộc là class `GreetingFactory`.

**Đặc biệt:** providers được liệt kê trong `META-INF/services` trên classpath, hoặc provider của **automatic module**, cần public no-arg constructor theo contract tương ứng; **provider factory method không được hỗ trợ cho các hình thức này như explicit named module provides**.

## 12. Ví dụ JPMS đầy đủ: lazy provider từ module descriptor

Ví dụ tiếp theo bổ sung minh họa module path chạy độc lập với ví dụ classpath.

### 12.1. Cấu trúc

```text
mod-spi/
└── src/
    ├── svc.api/
    │   ├── module-info.java
    │   └── svc/api/Greeting.java
    ├── svc.provider/
    │   ├── module-info.java
    │   └── svc/provider/HelloGreeting.java
    └── svc.host/
        ├── module-info.java
        └── svc/host/Main.java
```

Tạo đúng các files:

`src/svc.api/module-info.java`

```java
module svc.api {
    exports svc.api;
}
```

`src/svc.api/svc/api/Greeting.java`

```java
package svc.api;

public interface Greeting {
    String message();
}
```

`src/svc.provider/module-info.java`

```java
module svc.provider {
    requires svc.api;
    provides svc.api.Greeting with svc.provider.HelloGreeting;
}
```

`src/svc.provider/svc/provider/HelloGreeting.java`

```java
package svc.provider;

import svc.api.Greeting;

public final class HelloGreeting implements Greeting {
    static {
        System.out.println("Module provider initialized");
    }

    public HelloGreeting() {
        System.out.println("Module provider constructed");
    }

    @Override
    public String message() {
        return "hello JPMS";
    }
}
```

`src/svc.host/module-info.java`

```java
module svc.host {
    requires svc.api;
    uses svc.api.Greeting;
}
```

`src/svc.host/svc/host/Main.java`

```java
package svc.host;

import svc.api.Greeting;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        ServiceLoader<Greeting> services =
                ServiceLoader.load(Greeting.class);

        System.out.println("ServiceLoader created");
        Greeting provider = services.findFirst().orElseThrow();
        System.out.println("Provider message: " + provider.message());
    }
}
```

### 12.2. Biên dịch và chạy

Trong thư mục `mod-spi` với JDK 17+:

```bash
javac --module-source-path src -d mods src/svc.api/module-info.java src/svc.api/svc/api/Greeting.java src/svc.provider/module-info.java src/svc.provider/svc/provider/HelloGreeting.java src/svc.host/module-info.java src/svc.host/svc/host/Main.java
java --module-path mods --add-modules svc.provider --module svc.host/svc.host.Main
```

Dùng `--add-modules svc.provider` để đảm bảo provider module được đưa vào module graph của lượt chạy này. Chỉ đặt artifact trên module path **không phải luôn đủ** để module được resolve.

Stdout:

```text
ServiceLoader created
Module provider initialized
Module provider constructed
Provider message: hello JPMS
```

Ở đây module provider **không export package implementation**, nhưng ServiceLoader vẫn instantiate provider nhờ khai báo `provides`. Consumer chỉ cần service API. Static block/constructor chạy khi `findFirst()` lấy instance, không phải chỉ do tạo đối tượng ServiceLoader.

### 12.3. Nếu tạo plugin ModuleLayer riêng

Với modules được nạp vào child `ModuleLayer`, dùng:

```java
// Trích đoạn: layer đã tạo và Greeting.class là service API chung.
ServiceLoader<Greeting> services =
        ServiceLoader.load(layer, Greeting.class);
```

Overload này tìm providers trong layer và ancestor layers theo contract; **không tìm providers thuộc unnamed modules**. Cần đảm bảo API service được chia sẻ đúng defining loader/module giữa host và providers, nếu không có thể xảy ra lỗi type identity hoặc service configuration.

## 13. ServiceConfigurationError xảy ra lúc nào?

`ServiceLoader` có thể trì hoãn **cả lỗi** đến khi thực sự khám phá hoặc instantiate provider. Không được suy ra `ServiceLoader.load(...)` thành công nghĩa là metadata/provider hoàn toàn đúng.

Một số lỗi điển hình:
- File `META-INF/services/...` sai cú pháp, encoding hoặc I/O khi đọc.
- Provider binary name sai hoặc class file thiếu.
- Provider không assignable sang service interface/class.
- Provider trên classpath không có **public no-arg constructor**, là abstract/interface không phù hợp hoặc constructor ném exception.
- Explicit named-module provider factory method có signature không hợp lệ, trả `null` hoặc ném lỗi.
- Provider code không thể được load/link vì dependency/class version vấn đề.
- Named-module caller không có `uses` phù hợp hoặc service type không accessible.

Khi gặp vấn đề, `ServiceLoader` dùng **`ServiceConfigurationError`**, một subclass của `Error`, thay vì trả “không có provider” trong mọi trường hợp.

### Bắt lỗi tại ranh giới discovery

```java
// Trích đoạn trong ứng dụng có Greeting service.
try {
    for (Greeting g : ServiceLoader.load(Greeting.class)) {
        System.out.println(g.message());
    }
} catch (java.util.ServiceConfigurationError error) {
    System.err.println("Broken service registration: " + error);
    Throwable cause = error.getCause();
    if (cause != null) {
        cause.printStackTrace();
    }
}
```

Đây là trích đoạn; cần interface Greeting hợp lệ và import ServiceLoader. Có thể phát sinh lỗi ở `Iterator.hasNext()`, `next()` hoặc xử lý `stream()`; vì vậy xử lý lỗi phải bao **đúng thao tác duyệt**, không chỉ bao `ServiceLoader.load()`.

Không catch `Throwable` rồi bỏ qua để giả vờ hệ thống có 0 providers. Nếu metadata khai báo provider nhưng sai, đó là **cấu hình lỗi**, khác việc không khai báo provider.

### Có nên tự động bỏ qua provider hỏng rồi lấy provider tiếp?

Tài liệu API nói iterator sau lỗi có thể **cố gắng** tìm provider tiếp theo nhưng **không đảm bảo phục hồi**. Tùy yêu cầu hệ thống, có thể fail fast và báo lỗi cấu hình, hoặc triển khai chính sách retry có kiểm soát. Không viết vòng `while(true)` catch mọi lỗi rồi tiếp tục vô hạn.

## 14. Thứ tự providers và cấu hình chọn implementation

`ServiceLoader.findFirst()` thuận tiện nhưng “first” phụ thuộc source provider declarations và thứ tự lookup, đặc biệt trong các tình huống:
- Nhiều file `META-INF/services` trên classpath.
- Nhiều named modules cùng cung cấp một service.
- Nhiều modules nằm trong cùng `ModuleLayer`.
- ClassLoader cha/con có providers riêng.

Trên classpath, theo contract của ServiceLoader, thứ tự dựa vào `ClassLoader.getResources` cùng thứ tự các tên provider trong từng file. Trong một named module, thứ tự các provider được khai báo trong descriptor được giữ, nhưng **thứ tự giữa modules trong cùng layer không được xác định**.

Vì vậy, nếu ứng dụng cần một provider có **ưu tiên nghiệp vụ** cao nhất:
- Đừng phụ thuộc mù quáng vào `findFirst()` trên một module graph thay đổi.
- Khám phá candidate types qua `stream()`.
- Đọc annotation/metadata priority đã xác định, kiểm tra suitability.
- Chọn theo quy tắc tường minh và chỉ instantiate provider được chọn nếu có thể.
- Nếu sự ưu tiên không thể được xác định mà không instantiate, định nghĩa vòng đời/tài nguyên phù hợp và không gọi constructor vô tội vạ.

Ví dụ chọn theo class name là demo, không phải chiến lược cấu hình ưu tiên đủ tốt cho sản phẩm lớn.

## 15. Provider không nhất thiết là singleton

`ServiceLoader` tạo providers theo nhu cầu; điều này **không tự cho một hợp đồng singleton toàn ứng dụng**.

- Một `ServiceLoader` instance có cache các providers đã được iterator instantiate.
- `ServiceLoader.load(...)` được gọi lại tạo **ServiceLoader object mới** với cache riêng.
- `reload()` có thể làm một ServiceLoader hiện có instantiate lại provider.
- `Provider.get()` phải được xem theo hợp đồng “returns an instance”, **không nên giả định identity ổn định**.
- Static initializer của class provider không nhất thiết chạy lại khi object provider mới được tạo.

Nếu provider mở connection pool, tạo thread, giữ socket hoặc đăng ký listener trong constructor, vòng đời phải được quản lý **ở cấp ứng dụng**. ServiceLoader không có `close()` tự đóng tất cả provider instances. Khi service interface cần cleanup, có thể thiết kế:

```java
// Trích đoạn thiết kế hợp đồng:
public interface ManagedService extends AutoCloseable {
    String name();

    @Override
    void close() throws Exception;
}
```

Đây là interface đầy đủ có thể biên dịch trong `ManagedService.java`, nhưng **không đủ tạo ứng dụng SPI độc lập**. Consumer phải gọi `close()` cho provider instances thực sự sở hữu, theo thứ tự và điều kiện phù hợp. Không tự close object dùng chung nếu provider được quản lý bởi container khác.

## 16. ServiceLoader có thread-safe không?

**Không.** Tài liệu `ServiceLoader` nêu các instance **không an toàn khi nhiều thread truy cập đồng thời**. Cache, iterator, stream và `reload()` của một ServiceLoader có trạng thái mutable.

Hệ quả:
- Không chia sẻ một đối tượng `ServiceLoader` cho nhiều thread duyệt và reload đồng thời mà không có phối hợp.
- Nếu nhiều task cần providers, cân nhắc tạo `ServiceLoader` riêng theo scope/thread hoặc dùng khóa ở tầng điều phối.
- Không gọi `reload()` trong lúc thread khác đang dùng iterator/stream của cùng đối tượng.
- Một provider instance có thread-safe hay không là **hợp đồng riêng của implementation**, không được suy ra từ ServiceLoader.
- ClassLoader có thể parallel-capable nhưng **không làm ServiceLoader instance trở thành thread-safe**.

Ví dụ đóng gói đồng bộ ở mức ứng dụng có thể serialize thao tác khám phá/reload, nhưng còn phải xem provider methods có gọi trở lại loader/callback và tránh deadlock. Chỉ dùng `synchronized` bừa trên toàn hệ có thể tạo điểm nghẽn mới.

## 17. Provider discovery có side effects không?

Có thể. Dù ServiceLoader được thiết kế lazy, thời điểm khám phá vẫn có thể thực hiện:
- Tìm/đọc provider config resource qua ClassLoader.
- Tải provider class và dependency khi cần.
- Liên kết/kiểm tra runtime types.
- Gọi constructor hoặc factory method khi instantiate.
- Chạy static initialization khi active use.
- Thực hiện I/O tùy custom ClassLoader (remote URLs, network JAR).
- Gây exception/error khi metadata/bytecode bất hợp lệ.

Do đó không nói “`ServiceLoader.load()` an toàn tuyệt đối và chẳng làm gì” theo nghĩa không thể có bất kỳ ngoại lệ hoặc chi phí nào. Nó **tạo service loader object**, còn phần lớn discovery/instantiate được trì hoãn. Kết quả cụ thể của các thao tác sau tùy môi trường module/loader.

Nếu muốn xây ứng dụng có startup latency thấp, dùng `stream` để lọc khi có thể và tránh instantiate tất cả providers chỉ để đọc tên. Nhưng việc lọc theo `Provider.type()` vẫn có thể load class, nên profiling thực tế là cần thiết.

## 18. Ví dụ lỗi điển hình: provider class có nhưng không tìm thấy

Trường hợp:
- `demo.impl.AlphaGreeting.class` tồn tại trong một thư mục.
- Host dùng `ServiceLoader.load(Greeting.class)`.
- Không có file `META-INF/services/demo.spi.Greeting` trong output hay module descriptor `provides`.

**Kết quả có thể là không tìm thấy provider**, dù bạn gọi `Class.forName("demo.impl.AlphaGreeting")` thành công. `ServiceLoader` không tự quét tất cả classes trong classpath để tìm implementations.

Cách chẩn đoán:

1. Kiểm tra interface service binary name **chính xác**.
2. Kiểm tra tệp `META-INF/services/...` đã được copy vào JAR/out directory chưa.
3. Kiểm tra contents có provider binary names không, encoding UTF-8, không thêm `.class`.
4. Kiểm tra provider class có public no-arg constructor nếu triển khai trên classpath.
5. Kiểm tra loader dùng để tìm configuration và class: explicit loader hay TCCL.
6. Nếu named modules, kiểm tra `uses`/`provides`, module có resolved không, đúng layer không.
7. Nếu cùng binary name service interface được định nghĩa ở hai loaders khác nhau, provider có thể không assignable với service type của consumer.
8. Phân biệt **không có provider** (Optional.empty) và **provider bị lỗi** (ServiceConfigurationError).

Với JAR provider:

```bash
jar --list --file provider.jar
```

Tìm entries tương ứng, ví dụ:

```text
META-INF/services/demo.spi.Greeting
demo/impl/AlphaGreeting.class
```

Đây là hai entries cần tìm, không phải toàn bộ stdout. Đừng kiểm tra chỉ source tree: xác minh **artifact cuối cùng mà JVM thực sự chạy**.

## 19. Lỗi trùng API qua nhiều ClassLoaders

Một lỗi hệ plugin thường gặp:

```text
Host ClassLoader
  └── demo.spi.Greeting       [runtime class A]

Plugin ClassLoader
  ├── demo.spi.Greeting       [runtime class B]
  ├── demo.impl.AlphaGreeting [implements B]
  └── META-INF/services/demo.spi.Greeting

Class A != Class B
```

Nếu provider implements interface B do plugin loader định nghĩa, nhưng host hỏi `ServiceLoader.load(ClassA, pluginLoader)`, provider có thể **không assignable** sang service class A. Đây là vấn đề **class identity**, không phải chỉ thiếu tên class trong configuration.

Giải pháp phổ biến:
- Đặt service API trong loader cha/shared module.
- Plugin loader dùng chính API đó, không tự định nghĩa lại interface.
- Provider implementation có thể nằm trong loader riêng.
- Kiểm tra `providerClass.getClassLoader()` và `serviceClass.getClassLoader()`; đừng so mỗi chuỗi tên.

Nếu custom loader child-first cho mọi package, cần whitelist service API dùng chung để parent-first, tránh định nghĩa trùng contract.

## 20. Reload và vòng đời ClassLoader khi đổi plugin

Có ba lớp vòng đời khác nhau:

| Thành phần | Ý nghĩa của thao tác |
|---|---|
| `ServiceLoader.reload()` | Xóa cache provider discovery/instances của đối tượng ServiceLoader |
| `URLClassLoader.close()` | Đóng tài nguyên tìm class/resource mới của URLClassLoader |
| JVM class unloading | Có thể thu gom runtime class/loader khi không còn reachable và GC thực hiện phù hợp |

Chúng không thay thế cho nhau.

Một plugin manager có thể thực hiện:

```text
stop requests
  ↓
finish/cancel in-flight provider operations
  ↓
unregister callbacks, close provider-owned resources
  ↓
restore TCCL, clear caches/references
  ↓
discard old ServiceLoader and provider instances
  ↓
close old URLClassLoader (if owned)
  ↓
build a new ClassLoader/ModuleLayer for new plugin generation
  ↓
create new ServiceLoader and discover providers again
```

Đừng dùng `ServiceLoader.reload()` như giải pháp hot deployment duy nhất khi bytecode đã được định nghĩa bởi loader cũ. Tương tự, `URLClassLoader.close()` không ép class cũ biến mất và không dừng thread do provider đã tạo.

## 21. Những hiểu nhầm phổ biến

| Nhận định sai | Điều đúng |
|---|---|
| `ServiceLoader.load` tạo tất cả providers ngay | API được thiết kế lazy: discovery/instantiation theo nhu cầu |
| `iterator()` tạo tất cả provider objects | Việc tạo xảy ra khi duyệt, nhất là `next()` |
| `hasNext()` luôn miễn phí, không thể lỗi | Nó có thể tìm config, tải/kiểm tra providers và ném ServiceConfigurationError |
| `stream()` trả Stream<S> | Nó trả `Stream<ServiceLoader.Provider<S>>` |
| `Provider.type()` và `Provider.get()` giống nhau | Một cái trả type, một cái trả instance |
| `Provider.get()` luôn là singleton cache | Không được giả định instance identity toàn cục |
| `findFirst()` luôn trả provider hoặc empty | Metadata hỏng có thể gây ServiceConfigurationError |
| Có implementation .class là đủ | Classpath cần `META-INF/services`, named module dùng `provides` |
| ServiceLoader luôn lấy loader của caller | `load(S.class)` dùng TCCL; có explicit overload |
| Provider class phải export package trong JPMS | `provides` có thể đăng ký implementation không export |
| Classpath provider dùng static provider() factory | Factory provider method chỉ theo contract explicit named module |
| `reload()` unload class mới thay bytes | Nó chỉ xóa provider cache |
| ServiceLoader tự đóng provider sau khi dùng | Ứng dụng/container phải quản lý lifecycle riêng |
| ServiceLoader thread-safe | ServiceLoader instances không an toàn để dùng concurrent không phối hợp |
| `findFirst()` là business priority ổn định mọi môi trường | Thứ tự phụ thuộc cấu hình JAR/module/loader |
| `ServiceConfigurationError` giống thiếu provider | Đây là lỗi cấu hình, không phải Optional.empty |

## 22. Câu hỏi tự kiểm tra

1. **Service và provider khác nhau thế nào?** Service là interface/class hợp đồng; provider là implementation được tìm lúc chạy.
2. **`ServiceLoader.load(...)` có khởi tạo toàn bộ providers ngay không?** Không; discovery và instantiation lazy.
3. **`iterator().hasNext()` có thể gây I/O hoặc lỗi không?** Có, khi tìm metadata/providers.
4. **`iterator().next()` trả gì?** Provider instance thuộc service type.
5. **`stream()` trả Stream của kiểu nào?** `Stream<ServiceLoader.Provider<S>>`.
6. **`Provider.type()` và `get()` khác nhau?** Type trả Class của provider type, get trả instance.
7. **`findFirst()` có đảm bảo không ném ServiceConfigurationError không?** Không.
8. **Đặt file class provider trong JAR mà thiếu service configuration thì sao?** Class có thể tồn tại nhưng ServiceLoader không tự phát hiện nó qua classpath SPI.
9. **Tên file trong META-INF/services là gì?** Binary name của service interface/class.
10. **Provider trên classpath thường cần constructor nào?** Public no-arg constructor.
11. **Named module consumer khai báo gì?** `uses service.Type;` cùng read dependency khi cần.
12. **Named module provider khai báo gì?** `provides service.Type with provider.Type;`.
13. **Module provider có cần export package implementation không?** Không nhất thiết cho ServiceLoader.
14. **`ServiceLoader.load(S.class)` dùng loader nào?** TCCL theo contract.
15. **`reload()` có chạy lại static initializer của class đã init thành công không?** Không.
16. **Sau reload, dùng iterator cũ có an toàn không?** Không; tạo iterator/stream mới.
17. **ServiceLoader có tự cleanup provider resources không?** Không.
18. **Hai class service cùng tên nhưng do hai loaders khác nhau định nghĩa có tương thích không?** Không tự động.
19. **Muốn hot reload bytecode mới, chỉ gọi reload() đủ không?** Không; thường cần loader generation mới.
20. **Lỗi metadata hỏng nên xử lý như gì?** `ServiceConfigurationError`, khác không có provider.

## Tài liệu chuẩn

- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): provider discovery, lazy timing, iterator/stream, provider cache, reload, ordering, module/classpath formats, lỗi ServiceConfigurationError.
- [Java SE 17 — ServiceLoader.Provider](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.Provider.html): `type()` và `get()`.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): binary names, parent delegation và loader identity.
- [Java SE 17 — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): plugin modules và module layer.
- [JLS 17 — §7.7 Module Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html): `uses`, `provides` và module access.
- [JLS 17 — §12.2–12.4](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): loading, linking, initialization.

**Kết luận:** `ServiceLoader` tách **đăng ký/khám phá provider** khỏi **tạo provider instance**. `iterator()` instantiate khi duyệt, `findFirst()` chỉ lấy provider đầu tiên, `stream()` hỗ trợ xem type trước khi gọi `Provider.get()`. Khi làm SPI hoặc hệ plugin, phải chọn đúng ClassLoader/ModuleLayer, phân biệt “không có provider” với “provider cấu hình sai”, và quản lý cache, concurrency cùng vòng đời provider thay vì coi `reload()` là class unloading.
