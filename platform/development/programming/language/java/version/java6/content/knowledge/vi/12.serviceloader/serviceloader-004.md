# ServiceLoader.load và ClassLoader dùng để khám phá provider trong Java

## 1. Bản chất của ServiceLoader và bài toán khám phá

`java.util.ServiceLoader<S>` là cơ chế chuẩn của Java để **khám phá và nạp các triển khai** (service provider) của một kiểu service `S`, thường là interface hoặc abstract class. Code sử dụng chỉ phụ thuộc vào hợp đồng service; các implementation được đóng gói và đăng ký riêng. Một service có thể không có provider, có một provider hoặc có nhiều provider.

Ba thành phần cần phân biệt:

- **Service contract:** kiểu công khai mà ứng dụng muốn sử dụng, ví dụ `Greeting`.
- **Provider:** class triển khai service, ví dụ `HelloGreeting`.
- **Thông tin đăng ký và phạm vi nhìn thấy:** file `META-INF/services/<tên-service>` khi chạy trên classpath; hoặc khai báo `provides ... with ...` trong named module. `ClassLoader` và module layer quyết định provider nào được nhìn thấy.

`ServiceLoader.load(...)` **tạo đối tượng loader để thực hiện khám phá**, không nhất thiết lập tức tạo mọi provider. Việc tìm kiếm/khởi tạo thường diễn ra **theo nhu cầu** khi duyệt `iterator()`, gọi `findFirst()` hoặc xử lý `stream()`.

`ServiceLoader` không quét mọi class rồi đoán class nào implement interface. Nó dựa trên đăng ký provider hợp lệ và ngữ cảnh nạp lớp. Vì vậy, có class triển khai nằm trong JAR vẫn chưa đủ: provider phải được đăng ký và có thể được nhìn thấy từ loader/module layer được dùng.

Mục tiêu bài học là nắm rõ hai overload quan trọng:

```java
ServiceLoader<MyService> defaults =
        ServiceLoader.load(MyService.class);

ServiceLoader<MyService> explicit =
        ServiceLoader.load(MyService.class, someClassLoader);
```

Đây là đoạn minh họa API; `MyService` và `someClassLoader` cần được định nghĩa trong chương trình của bạn.

## 2. ServiceLoader.load(Service.class) lấy ClassLoader nào?

Overload:

```java
ServiceLoader<S> loader = ServiceLoader.load(ServiceType.class);
```

tương đương về việc chọn class loader với:

```java
ClassLoader contextLoader =
        Thread.currentThread().getContextClassLoader();
ServiceLoader<S> loader =
        ServiceLoader.load(ServiceType.class, contextLoader);
```

`S` và `ServiceType` ở đây chỉ là ký hiệu minh họa, không phải các class có sẵn. Điểm mấu chốt là **`load(Class<S>)` sử dụng context class loader của thread hiện tại**, hay *Thread Context ClassLoader* (TCCL), tại thời điểm tạo `ServiceLoader`.

TCCL là class loader được gán cho thread thông qua `Thread.getContextClassLoader()`/`setContextClassLoader(...)`. Nó có ích khi một thư viện hoặc framework đang chạy bằng một class loader nhưng cần khám phá provider được nạp bởi class loader của ứng dụng/plugin bên ngoài.

**Không nhầm các loader sau:**

| Biểu thức | Ý nghĩa |
| --- | --- |
| `Thread.currentThread().getContextClassLoader()` | Class loader ngữ cảnh gắn với thread hiện tại; `ServiceLoader.load(Service.class)` dùng loader này. |
| `MyService.class.getClassLoader()` | Loader đã định nghĩa kiểu service; có thể khác TCCL. |
| `ClassLoader.getSystemClassLoader()` | Loader hệ thống/application của JVM; không phải lúc nào cũng nhìn thấy plugin nằm trong class loader riêng. |
| `ServiceLoader.load(MyService.class, pluginLoader)` | Sử dụng class loader `pluginLoader` được chỉ định làm điểm bắt đầu khám phá provider. |

TCCL **không mặc nhiên bằng** loader định nghĩa interface, đặc biệt trong ứng dụng có container, plugin hoặc nhiều class loader. Nếu muốn sử dụng đúng loader của một plugin, thường nên truyền nó tường minh khi phạm vi plugin đã được quản lý rõ ràng.

Một lưu ý thực tiễn: không lưu một `ServiceLoader` tạo từ overload mặc định vào singleton dùng chung cho nhiều ứng dụng/plugin có TCCL khác nhau; instance này giữ ngữ cảnh khám phá của lần tạo và có thể gây chọn sai provider hoặc giữ tham chiếu khiến class loader không được giải phóng.

## 3. ServiceLoader.load(Service.class, ClassLoader loader) làm gì?

Overload:

```java
ServiceLoader<MyService> services =
        ServiceLoader.load(MyService.class, pluginLoader);
```

sử dụng `pluginLoader` làm **điểm bắt đầu** để tìm provider. Với provider trên classpath (unnamed module), Java tìm các resource đăng ký `META-INF/services/<fully-qualified-service-name>` qua khả năng truy cập resource của loader, rồi nạp lớp provider có thể nhìn thấy từ loader đó.

Với provider trong **named modules**, thuật toán Java hiện đại cũng xem xét provider được khai báo trong các module phù hợp với class loader và module layer liên quan; vì vậy không thể mô tả cơ chế này đơn giản là quét một thư mục JAR.

Một số hệ quả:

1. Loader chỉ có thể tìm provider nằm trong phạm vi mà nó có thể truy cập. `ClassLoader.getSystemClassLoader()` không tự phát hiện mọi JAR do child class loader riêng nạp.
2. Provider phải tương thích đúng **định danh runtime** của service. Trong Java, cùng tên đầy đủ nhưng bị định nghĩa bởi hai class loader khác nhau có thể là **hai kiểu không tương đương**. Tạo trùng interface `Greeting` trong cả host lẫn plugin dễ gây lỗi `not a subtype`.
3. Với `load(service, null)`, API dùng **system class loader** (hoặc bootstrap loader nếu không có system loader); `null` không có nghĩa là quét toàn bộ mọi class loader.
4. Khám phá provider khác với `Class.forName("...")`: lệnh sau nạp class theo tên do bạn cung cấp, còn `ServiceLoader` phát hiện các class thông qua hợp đồng service và dữ liệu đăng ký.

Có thể hình dung:

```text
Ứng dụng gọi ServiceLoader.load(Greeting.class, pluginLoader)
       |
       +-- phạm vi class loader / named modules liên quan
       |
       +-- provider đăng ký trong META-INF/services (classpath)
       |
       +-- kiểm tra provider triển khai đúng Greeting
       |
       +-- iterator(), findFirst(), stream() -> tải/khởi tạo theo nhu cầu
```

## 4. Đăng ký provider trên classpath

Giả sử service là:

```java
package demo.spi;

public interface Greeting {
    String greet(String name);
}
```

Một implementation là:

```java
package demo.impl;

import demo.spi.Greeting;

public class HelloGreeting implements Greeting {
    @Override
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Khi dùng classpath, provider được đăng ký bằng **file resource**, tên file phải đúng tên đầy đủ của service:

```text
META-INF/services/demo.spi.Greeting
```

Nội dung file UTF-8 (một provider trên mỗi dòng):

```text
demo.impl.HelloGreeting
```

Quy tắc cần nhớ:
- Tên resource là **tên đầy đủ của service**, không phải tên provider; tên provider nằm **bên trong** file.
- File chứa tên class provider đầy đủ, từng dòng; hỗ trợ dòng trắng và chú thích bằng `#`.
- Nếu có nhiều provider, liệt kê từng provider trên một dòng; trùng tên provider được bỏ qua.
- Với provider trên classpath, implementation phải là class public, triển khai service và có constructor public không tham số (constructor mặc định của một class public không khai báo constructor cũng đáp ứng).
- File resource phải nằm trên **classpath của class loader được dùng**. Khi đóng gói thành JAR, nó nằm ở đường dẫn `META-INF/services/...` bên trong JAR, không chỉ tồn tại ở thư mục source.

Nếu provider có code đúng nhưng thiếu file này, `ServiceLoader` thường **trả về tập kết quả rỗng**, không tự báo rằng một implementation “đáng lẽ phải tồn tại”.

## 5. Ví dụ chạy được: plugin ClassLoader, overload mặc định và overload tường minh

Ví dụ sau chạy bằng **JDK 17+**, không yêu cầu thư viện bên ngoài. Chúng ta biên dịch service và ứng dụng host vào `out/host`, còn implementation vào `out/plugin`. Khi chạy host, plugin **không nằm trong application classpath**, nên overload mặc định ban đầu không thể nhìn thấy provider; một `URLClassLoader` riêng sẽ nhìn thấy nó.

### 5.1. Cấu trúc file

Tạo chính xác các file/thư mục sau:

```text
src/
  demo/
    spi/
      Greeting.java
    impl/
      HelloGreeting.java
    app/
      Main.java
out/
  host/
  plugin/
    META-INF/
      services/
        demo.spi.Greeting
```

`out/host` được để trống trước khi biên dịch. File `out/plugin/META-INF/services/demo.spi.Greeting` chứa đúng một dòng `demo.impl.HelloGreeting`.

### 5.2. Service contract

`src/demo/spi/Greeting.java`:

```java
package demo.spi;

public interface Greeting {
    String greet(String name);
}
```

### 5.3. Plugin provider

`src/demo/impl/HelloGreeting.java`:

```java
package demo.impl;

import demo.spi.Greeting;

public class HelloGreeting implements Greeting {
    @Override
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Class không khai báo constructor, nên Java cung cấp constructor mặc định public vì class là public. Nó phù hợp yêu cầu classpath provider của `ServiceLoader`.

### 5.4. Ứng dụng host và quản lý Thread Context ClassLoader

`src/demo/app/Main.java`:

```java
package demo.app;

import demo.spi.Greeting;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) throws Exception {
        // Chỉ out/host nằm trên classpath khi khởi động ứng dụng.
        boolean defaultFound =
                ServiceLoader.load(Greeting.class).findFirst().isPresent();
        System.out.println("defaultFound=" + defaultFound);

        URL pluginUrl = Path.of("out/plugin").toAbsolutePath().toUri().toURL();

        // Parent thấy service contract trong out/host.
        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] { pluginUrl }, Greeting.class.getClassLoader())) {

            Greeting explicit =
                    ServiceLoader.load(Greeting.class, pluginLoader)
                            .findFirst()
                            .orElseThrow();

            System.out.println("explicit=" + explicit.greet("Lan"));

            Thread thread = Thread.currentThread();
            ClassLoader previous = thread.getContextClassLoader();
            try {
                // load(Greeting.class) sẽ sử dụng TCCL mới.
                thread.setContextClassLoader(pluginLoader);

                Greeting viaContext =
                        ServiceLoader.load(Greeting.class)
                                .findFirst()
                                .orElseThrow();

                System.out.println("context=" + viaContext.greet("Lan"));
            } finally {
                // TCCL là trạng thái của thread: luôn khôi phục.
                thread.setContextClassLoader(previous);
            }
        }
    }
}
```

`URLClassLoader` ở đây được dùng có chủ đích để tạo phạm vi plugin riêng trên classpath. Constructor được truyền parent là loader của `Greeting`, bảo đảm host và provider dùng **cùng một service type**. `try-with-resources` đóng `URLClassLoader` sau khi xong; `finally` khôi phục TCCL, kể cả khi có lỗi.

### 5.5. Biên dịch, chạy và kiểm tra output

Từ thư mục gốc chứa `src` và `out`:

```bash
javac -d out/host src/demo/spi/Greeting.java src/demo/app/Main.java
javac -cp out/host -d out/plugin src/demo/impl/HelloGreeting.java
java -cp out/host demo.app.Main
```

Các thư mục `out/host` và `out/plugin` phải được tạo trước, cùng file đăng ký `out/plugin/META-INF/services/demo.spi.Greeting` như ở trên. Ở cả Windows, Linux và macOS, ba lệnh trên dùng đúng **một đường dẫn** cho mỗi `-cp`, nên không có sự khác nhau về dấu phân cách classpath.

Output chính xác:

```text
defaultFound=false
explicit=Xin chào, Lan!
context=Xin chào, Lan!
```

**Vì sao?**

1. Khi chạy `java -cp out/host`, TCCL mặc định của thread chính chỉ nhìn thấy classpath của host; nó không thấy resource đăng ký và class provider trong `out/plugin`. Vì vậy `defaultFound=false`.
2. `new URLClassLoader(..., Greeting.class.getClassLoader())` biết thêm URL của `out/plugin`. `ServiceLoader.load(Greeting.class, pluginLoader)` đọc file đăng ký, tải provider và tạo instance: in dòng `explicit=...`.
3. Khi tạm đặt TCCL là `pluginLoader`, overload ngắn `ServiceLoader.load(Greeting.class)` cũng phát hiện provider đó: in dòng `context=...`.
4. Cuối cùng TCCL được khôi phục, và plugin loader được đóng. Điều này tránh rò rỉ ngữ cảnh sang xử lý khác.

**Không nhầm:** `setContextClassLoader` chỉ thay cách tra cứu context loader của thread. Nó không biến provider thành một phần của `out/host` và không nạp lại các class đã định nghĩa.

## 6. ServiceLoader trong Java module system (JPMS, Java 9+)

Java hiện đại hỗ trợ khám phá provider trong **named modules**. Với đường này, việc đăng ký thường nằm trong `module-info.java` thay vì file `META-INF/services`.

Ví dụ giả định ba named module:

`demo.spi/module-info.java`:

```java
module demo.spi {
    exports demo.spi;
}
```

`demo.provider/module-info.java`:

```java
module demo.provider {
    requires demo.spi;
    provides demo.spi.Greeting with demo.impl.HelloGreeting;
}
```

`demo.app/module-info.java`:

```java
module demo.app {
    requires demo.spi;
    uses demo.spi.Greeting;
}
```

Ba đoạn `module-info.java` trên **minh họa khai báo của các module khác nhau**, không phải ba file đặt chung trong một source folder. Các source Java `Greeting`, `HelloGreeting`, `Main` cần được biên dịch/đóng gói theo đúng module path khi chuyển ví dụ classpath ở trên sang ứng dụng module hóa.

Ý nghĩa:
- `exports` công khai package chứa service contract cho consumer/provider.
- `requires` khai báo dependency đến module chứa service.
- `provides ... with ...` đăng ký provider ở cấp module; package implementation thường **không cần export**.
- `uses ...` là khai báo bắt buộc trong module tiêu thụ nếu gọi `ServiceLoader.load` cho service đó; thiếu `uses` có thể gây `ServiceConfigurationError`.
- Runtime phải **resolve** provider module vào module layer thích hợp. Đừng chỉ đặt JAR ở một thư mục tùy ý rồi kỳ vọng sẽ được phát hiện.

`ServiceLoader.load(service, loader)` có thể khám phá cả provider trong named modules theo thuật toán module/class loader của JDK, không chỉ dựa vào `META-INF/services`. Nếu ứng dụng xây dựng **ModuleLayer** riêng và muốn tìm provider trong layer đó cùng các layer cha, API phù hợp là:

```java
ServiceLoader<Greeting> loader =
        ServiceLoader.load(pluginLayer, Greeting.class);
```

Đây là snippet minh họa khi biến `pluginLayer` đã là một `ModuleLayer` hợp lệ. Overload này chỉ tìm provider trong **named modules** của layer được truyền và các layer tổ tiên; nó không quét provider trong unnamed modules trên classpath. Đây là lý do phải phân biệt *ClassLoader-based discovery* với *ModuleLayer-based discovery* trong ứng dụng plugin có JPMS.

## 7. Khởi tạo lười, cache, stream và reload

`ServiceLoader` thực hiện khám phá/khởi tạo **lazily**:
- `ServiceLoader.load(...)` tạo loader cho service. Đừng hiểu nó là thao tác quét và khởi tạo tất cả provider ngay.
- Vòng `for (Greeting g : serviceLoader)` hoặc `iterator()` đưa ra instance provider theo nhu cầu. Các instance đã tạo được cache trong **chính ServiceLoader đó**.
- `findFirst()` lấy provider đầu tiên hoặc `Optional.empty()` nếu không có. Với nhiều provider, không nên xem provider “đầu tiên” là một ưu tiên nghiệp vụ bền vững nếu bạn không kiểm soát đầy đủ quy tắc thứ tự.
- `stream()` trả các đối tượng `ServiceLoader.Provider<S>`; `Provider.type()` đọc kiểu provider, `Provider.get()` lấy một instance. Có thể lọc theo metadata trước khi khởi tạo provider.
- `reload()` xóa cache provider của ServiceLoader. Những lần duyệt sau sẽ khám phá lại; nó **không tự thêm JAR vào class loader, không làm thay đổi module layer và không thay thế class đã được JVM tải**.

Minh họa chọn provider theo kiểu Java 9+:

```java
ServiceLoader<Greeting> loader = ServiceLoader.load(Greeting.class);
loader.stream()
        .map(ServiceLoader.Provider::get)
        .forEach(greeting -> System.out.println(greeting.greet("Lan")));
```

Đoạn trên là snippet trong một phương thức có thể truy cập `Greeting`, sử dụng context loader có provider đã đăng ký. Nếu có nhiều provider, số dòng và thứ tự phụ thuộc vào môi trường. Với bài toán lựa chọn provider theo nghiệp vụ, hãy định nghĩa tiêu chí cụ thể (tên, capability, cấu hình), kiểm tra trường hợp không có provider, và tránh phụ thuộc thứ tự không được bảo đảm.

`ServiceLoader` **không bảo đảm thread safety**. Không dùng chung instance loader rồi vừa `reload()` vừa duyệt từ các thread khác. Khi gọi `reload()`, những iterator/stream cũ có thể bị vô hiệu; tạo iterator/stream mới sau `reload()`.

## 8. Debug khi provider không được khám phá

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không có provider (`findFirst().isEmpty()`) | Chưa đăng ký, resource sai tên/vị trí, provider ngoài phạm vi loader, module chưa được resolve | Xác minh `META-INF/services/<FQCN>` hoặc `uses/provides`, classpath/module path, TCCL/explicit loader. |
| Có file service nhưng không tìm thấy provider | Resource nằm trong source chứ không nằm trong output JAR/classpath, hoặc loader không nhìn thấy nó | Mở JAR/output để xác minh đường dẫn; xem `loader.getResources(...)` cho trường hợp classpath. |
| `ServiceConfigurationError: Provider ... not found` | Sai FQCN, thiếu class/dependency của provider | Kiểm tra tên package/class, runtime classpath, các dependency của provider. |
| `ServiceConfigurationError: ... not a subtype` | Provider không triển khai đúng service runtime, hoặc có hai bản sao service class do hai loader định nghĩa | Cho plugin dùng chung service contract qua parent/shared loader, không đóng gói trùng bản interface. |
| Lỗi constructor/provider | Provider classpath không public hoặc thiếu constructor public không tham số; hoặc provider khởi tạo thất bại | Sửa provider, xem nguyên nhân gốc của `ServiceConfigurationError`. |
| Named module gọi `load` bị lỗi | Module caller thiếu `uses` hoặc không có quyền truy cập kiểu service | Khai báo `uses` và `requires` phù hợp trong `module-info.java`. |
| Provider được thấy trong môi trường này nhưng không thấy ở môi trường khác | TCCL, classpath/module path hoặc module layer khác nhau | So sánh loader hiện tại và artifact runtime thực tế. |

Đối với provider đăng ký theo classpath, một cách chẩn đoán resource là:

```java
ClassLoader cl = Thread.currentThread().getContextClassLoader();
var urls = cl.getResources("META-INF/services/demo.spi.Greeting");
while (urls.hasMoreElements()) {
    System.out.println(urls.nextElement());
}
```

Đây là **snippet chẩn đoán**, nên đặt trong phương thức có `throws IOException` hoặc xử lý exception thích hợp. Danh sách URL được in phụ thuộc runtime. Nó chỉ giúp xác minh **service file dạng classpath** mà loader truy cập được, không liệt kê đầy đủ provider đăng ký qua `provides` trong named modules.

Khi gặp `ServiceConfigurationError`, nhớ rằng lỗi có thể chỉ xuất hiện khi bắt đầu duyệt `iterator`, gọi `findFirst` hoặc xử lý `stream`, dù lệnh `ServiceLoader.load` trước đó đã trả về một object. Ngoại lệ do `uses` trong named module có thể được phát hiện sớm ngay khi gọi `load`.

Đừng xử lý lỗi cấu hình provider bằng cách bắt `ServiceConfigurationError` rồi âm thầm bỏ qua tất cả. Nó có thể phản ánh lỗi triển khai nghiêm trọng. Cần ghi nhận service, loader, artifact và nguyên nhân để sửa đúng chỗ.

## 9. Thiết kế an toàn và tránh lỗi thường gặp

1. **Giữ service contract tại một nơi dùng chung.** Parent loader cần thấy interface; plugin không nên mang một bản copy class service có cùng tên nhưng khác loader.
2. **Không sử dụng TCCL như trạng thái toàn cục bất biến.** Nó thuộc thread. Khi tạm thay trong framework hoặc executor, luôn khôi phục trong `finally`. Nếu xử lý bất đồng bộ, đừng giả định thread tiếp theo tự kế thừa chính xác ngữ cảnh mong muốn.
3. **Không phụ thuộc provider đầu tiên nếu nhiều implementation.** Thứ tự còn tùy module, loader và file service; chọn provider theo policy nghiệp vụ rõ ràng.
4. **Đừng coi `reload` là hot reload class.** Muốn nạp plugin artifact mới có thể cần cập nhật cấu trúc class loader/module layer riêng, quản lý tài nguyên và vòng đời plugin.
5. **Coi provider là code thực thi.** Constructor/factory của provider có thể chạy logic bất kỳ. Chỉ nạp plugin đáng tin, kiểm soát artifact và dependency; `ServiceLoader` không phải sandbox bảo mật.
6. **Chú ý vòng đời loader.** Giữ cache/static references đến class loader cũ, service loader hoặc provider có thể ngăn GC sau khi plugin đã bị gỡ. Với `URLClassLoader` do mình tạo, quản lý đóng tài nguyên khi thích hợp.
7. **Không cấu hình classpath và module path lẫn lộn mà thiếu kiểm tra.** Provider classpath đăng ký theo `META-INF/services`; provider trong named modules khai báo `provides`. Phạm vi khám phá tương ứng có thể khác nhau.
8. **Không mặc định số kết quả là một.** Service contract có thể có 0, 1 hoặc nhiều provider. Ứng dụng phải xác định cách xử lý khi thiếu provider hoặc có nhiều lựa chọn.

## 10. Tự kiểm tra

**Câu 1.** Gọi `ServiceLoader.load(Greeting.class)` trong thread mà TCCL là `pluginLoader`. Class loader nào được dùng để bắt đầu khám phá?

**Đáp án:** `pluginLoader`, vì overload một đối số sử dụng `Thread.currentThread().getContextClassLoader()`.

**Câu 2.** JAR chứa `demo.impl.HelloGreeting` nhưng không có `META-INF/services/demo.spi.Greeting` và provider không được khai báo trong named module. Chỉ gọi `ServiceLoader.load(Greeting.class)` có tìm thấy nó không?

**Đáp án:** Không. Sự tồn tại của class triển khai không đồng nghĩa nó đã được đăng ký làm provider.

**Câu 3.** `Greeting` do host loader nạp, nhưng plugin đóng gói thêm một bản `demo.spi.Greeting` và dùng loader định nghĩa lại bản copy đó. Rủi ro gì?

**Đáp án:** Hai class có thể khác định danh runtime dù cùng tên; provider có nguy cơ bị xem là không phải subtype của `Greeting` mà host yêu cầu.

**Câu 4.** Gọi `serviceLoader.reload()` có khiến một JAR chưa được thêm vào classloader trở thành provider khả dụng không?

**Đáp án:** Không. `reload()` chỉ xóa cache của `ServiceLoader`; khả năng nhìn thấy artifact vẫn do class loader/module layer quyết định.

## 11. Tài liệu chính thức

- [Oracle Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): quy tắc tìm provider trong classpath/named modules, overload `load`, TCCL, `iterator`, `stream`, `reload` và các lỗi cấu hình.
- [Oracle Java SE 25 — ClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): nạp class và resources, system loader, quan hệ phân cấp class loader.
- [Oracle Java SE 17 — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html): module layer khi phát triển kiến trúc plugin dựa trên JPMS.
