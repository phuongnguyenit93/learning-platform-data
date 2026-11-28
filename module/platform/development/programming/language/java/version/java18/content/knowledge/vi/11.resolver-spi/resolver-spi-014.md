# ServiceLoader và system class loader: phạm vi provider được InetAddress phát hiện

## 1. Vấn đề thực tế

Một ứng dụng có thể nạp các thư viện bằng nhiều class loader: class loader của ứng dụng, class loader của plugin, hoặc class loader do framework tạo. Nếu một plugin mang theo implementation của `InetAddressResolverProvider`, liệu `InetAddress.getByName(...)` có tự động dùng implementation ấy?

**Không nhất thiết.** Từ Java 18, API `java.net.InetAddress` có cơ chế mở rộng việc phân giải tên và địa chỉ IP qua `java.net.spi.InetAddressResolverProvider`. Cơ chế phát hiện provider của `InetAddress` dựa vào `ServiceLoader` với **system class loader**. Vì vậy, điều quyết định là provider có được tìm thấy trong phạm vi nạp dịch vụ đó hay không; việc một class loader riêng có thể tự nạp lớp provider chưa đủ.

Bài học tập trung vào hợp đồng API này trên các JDK hiện đại, đặc biệt là phạm vi tìm kiếm, cách đăng ký và cách xác minh provider được dùng.

## 2. Ba thành phần cần phân biệt

| Thành phần | Vai trò |
| --- | --- |
| `InetAddress` | API mà mã ứng dụng gọi để phân giải tên máy thành địa chỉ IP và thực hiện các thao tác liên quan đến tra cứu ngược. |
| `InetAddressResolverProvider` | Điểm mở rộng (SPI): cung cấp một `InetAddressResolver` để `InetAddress` sử dụng. |
| `ServiceLoader` | Cơ chế Java tìm implementation đã đăng ký dưới dạng service provider, dựa trên class loader và cấu hình module/class path tương ứng. |

Trong API này, `InetAddressResolver` định nghĩa hai thao tác chính:

- `lookupByName(String host, InetAddressResolver.LookupPolicy lookupPolicy)` trả về luồng địa chỉ IP phù hợp với chính sách tra cứu.
- `lookupByAddress(byte[] addr)` thực hiện tra cứu ngược từ địa chỉ IP sang tên máy; có thể ném `UnknownHostException` khi không giải được.

`InetAddressResolverProvider` cung cấp `name()` và `get(Configuration)`. Thông qua `Configuration.builtinResolver()`, provider có thể lấy resolver tích hợp của JDK để ủy quyền các truy vấn mà nó không tự xử lý.

Điểm quan trọng: đây là **resolver dùng chung ở cấp JVM** cho `InetAddress`, không phải một resolver được chọn riêng cho từng đối tượng `InetAddress`, từng thread hoặc từng class loader gọi API.

## 3. System class loader giới hạn phạm vi phát hiện như thế nào?

Trong nhiều ứng dụng thông thường, system class loader là class loader nạp các lớp của ứng dụng ở class path. Có thể xem nó bằng:

~~~java
ClassLoader systemLoader = ClassLoader.getSystemClassLoader();
System.out.println(systemLoader);
~~~

JVM không bắt buộc mọi môi trường phải có cùng tên/lớp implementation của system class loader. Hãy dựa vào `ClassLoader.getSystemClassLoader()` thay vì giả định nó luôn là một lớp cụ thể.

Cần tách biệt hai cách sử dụng `ServiceLoader`:

~~~java
import java.net.spi.InetAddressResolverProvider;
import java.util.ServiceLoader;

// Lời gọi tiện ích thông thường: sử dụng thread context class loader.
var byContextLoader = ServiceLoader.load(InetAddressResolverProvider.class);

// Phạm vi class loader dùng để tìm provider cho InetAddress.
var bySystemLoader = ServiceLoader.load(
        InetAddressResolverProvider.class,
        ClassLoader.getSystemClassLoader());
~~~

Lời gọi `ServiceLoader.load(Service.class)` thường dùng **thread context class loader (TCCL)** của thread hiện tại. Nhưng `InetAddress` không dựa vào việc ứng dụng đổi TCCL để chọn resolver hệ thống. Nếu TCCL nhìn thấy provider còn system class loader không nhìn thấy, một phép liệt kê `ServiceLoader` từ TCCL có thể thành công trong khi `InetAddress` vẫn không dùng provider đó.

### Những trường hợp thường gặp

| Vị trí/cách đóng gói provider | Kết quả cần hiểu |
| --- | --- |
| JAR trên application class path, có khai báo `META-INF/services` chính xác | Provider có thể được phát hiện qua system class loader. |
| Named module đã được resolve, có `provides ... with ...` và nằm trong phạm vi nạp dịch vụ phù hợp | Provider có thể được phát hiện qua cơ chế service của hệ module. |
| JAR chỉ nằm trong custom child class loader, không hiện diện với system class loader | Không tự động trở thành provider của `InetAddress`. |
| Chỉ đặt TCCL trỏ tới custom class loader | Không đủ để thay resolver hệ thống mà `InetAddress` sử dụng. |
| Tự gọi `ServiceLoader.load(..., childLoader)` trong mã plugin | Chỉ chứng minh **lời gọi ServiceLoader ấy** thấy provider; không phải bằng chứng `InetAddress` đã chọn nó. |
| Nhiều provider cùng được phát hiện | Chỉ provider đầu tiên được phát hiện được dùng; không nên dựa vào thứ tự để thiết kế hệ thống. |

Với hệ module, **có JAR trên module path** chưa đồng nghĩa module đó đã được resolve trong cấu hình chạy. Cũng không nên giả định module được tạo trong một `ModuleLayer` riêng, hoặc thư viện trong class loader của application server, sẽ tự được chọn làm resolver của `InetAddress`.

Sơ đồ luồng khái quát:

~~~mermaid
flowchart TD
    A["Mã ứng dụng gọi InetAddress"] --> B["Resolver hệ thống của JVM"]
    B --> C["ServiceLoader phát hiện provider trong phạm vi system class loader"]
    C --> D{"Tìm thấy provider?"}
    D -->|Có| E["Chọn provider được phát hiện đầu tiên"]
    D -->|Không| F["Dùng resolver tích hợp của JDK"]
    E --> G["Provider tạo InetAddressResolver"]
    G --> H["Thực hiện tra cứu tên / địa chỉ"]
    F --> H
~~~

Sơ đồ mô tả **quyết định khởi tạo resolver hệ thống**; không có nghĩa mỗi lần gọi `getByName` đều chạy lại `ServiceLoader`.

## 4. Ví dụ provider ủy quyền cho resolver tích hợp

Để quan sát luồng mà không viết một DNS resolver mới, ta tạo một provider ghi log rồi ủy quyền cho resolver tích hợp. Các API dùng trong ví dụ là API công khai từ Java 18 và còn có ý nghĩa trên JDK hiện đại.

Tệp `src/main/java/demo/dns/TracingResolverProvider.java`:

~~~java
package demo.dns;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolverProvider;
import java.util.stream.Stream;

public final class TracingResolverProvider extends InetAddressResolverProvider {

    public TracingResolverProvider() {
    }

    @Override
    public String name() {
        return "tracing-resolver";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        InetAddressResolver delegate = configuration.builtinResolver();

        return new InetAddressResolver() {
            @Override
            public Stream<InetAddress> lookupByName(
                    String host,
                    InetAddressResolver.LookupPolicy lookupPolicy)
                    throws UnknownHostException {

                System.err.println("[resolver] lookupByName: " + host);
                return delegate.lookupByName(host, lookupPolicy);
            }

            @Override
            public String lookupByAddress(byte[] addr)
                    throws UnknownHostException {

                System.err.println("[resolver] lookupByAddress");
                return delegate.lookupByAddress(addr);
            }
        };
    }
}
~~~

Ở đây:

1. `TracingResolverProvider` là implementation của SPI và có constructor công khai không tham số để `ServiceLoader` có thể khởi tạo.
2. `name()` trả về tên của provider; việc ghi tên ở đây **không thay thế** cơ chế đăng ký service.
3. `get(Configuration)` dùng `builtinResolver()` để lấy resolver tích hợp, tạo một `InetAddressResolver` có hành vi rõ ràng.
4. Phương thức `lookupByName` chuyển nguyên `lookupPolicy` đến delegate, tránh tự ý bỏ qua các yêu cầu về IPv4/IPv6 và thứ tự ưu tiên.
5. Phương thức `lookupByAddress` cũng ủy quyền, giữ đầy đủ cả chiều tra cứu ngược.

**Không gọi `InetAddress.getByName(...)` từ chính implementation của `lookupByName(...)` để «ủy quyền».** Khi resolver tùy chỉnh đã được kích hoạt, cách gọi đó có thể dẫn đến việc đi lại qua chính resolver và gây đệ quy. Hãy sử dụng `configuration.builtinResolver()` khi mục đích là dựa trên resolver tích hợp.

Đây là ví dụ phục vụ học tập: ghi log trên đường tra cứu có thể làm lộ tên máy được truy vấn. Khi triển khai thực tế, cần quản lý dữ liệu log và bảo đảm implementation sử dụng an toàn từ nhiều thread.

## 5. Đăng ký provider trên class path

Khi provider là một thư viện thông thường, tạo tệp service descriptor trong resources:

`src/main/resources/META-INF/services/java.net.spi.InetAddressResolverProvider`

Nội dung tệp chỉ gồm tên đầy đủ của lớp provider:

~~~text
demo.dns.TracingResolverProvider
~~~

Khi đóng gói JAR, bảo đảm đường dẫn chính xác là:

~~~text
tracing-resolver.jar
├── demo/dns/TracingResolverProvider.class
├── demo/dns/TracingResolverProvider$1.class
└── META-INF/services/java.net.spi.InetAddressResolverProvider
~~~

Tên service descriptor phải là **tên đầy đủ của interface SPI**; nội dung phải trỏ đúng lớp provider. Provider và descriptor phải nằm trong phần mà system class loader tìm được khi chạy chương trình.

Ví dụ ứng dụng kiểm tra:

~~~java
package demo.app;

import java.net.InetAddress;
import java.util.Arrays;

public final class Main {
    public static void main(String[] args) throws Exception {
        System.out.println(Arrays.toString(
                InetAddress.getAllByName("localhost")));
    }
}
~~~

Nếu `app.jar` chứa ứng dụng và `tracing-resolver.jar` chứa provider đã đóng gói đúng, có thể chạy theo dạng:

~~~bash
# macOS / Linux: dấu ':' phân cách các mục class path
java -cp "app.jar:tracing-resolver.jar" demo.app.Main
~~~

~~~powershell
# Windows: dấu ';' phân cách các mục class path
java -cp "app.jar;tracing-resolver.jar" demo.app.Main
~~~

Khi `InetAddress` thực sự gọi resolver và truy vấn chưa được đáp ứng từ cache, đầu ra lỗi chuẩn có thể có dòng tương tự:

~~~text
[resolver] lookupByName: localhost
~~~

Không dùng một dòng log đơn lẻ làm tiêu chí duy nhất để kết luận: JVM có thể đã thực hiện truy vấn trước khi vào `main`, và kết quả `InetAddress` có thể được cache. Nên chạy bằng **JVM mới** cho từng phép thử và đối chiếu với phép liệt kê provider ở phần chẩn đoán.

## 6. Đăng ký bằng named module

Với Java Platform Module System, service provider được khai báo trong `module-info.java` của **module provider**:

~~~java
module demo.resolver {
    provides java.net.spi.InetAddressResolverProvider
        with demo.dns.TracingResolverProvider;
}
~~~

Một module tiêu thụ `InetAddress` không cần thêm `uses` chỉ để gọi `InetAddress.getByName(...)`. Chính cơ chế nội bộ của JDK sử dụng service này. Nếu ứng dụng **trực tiếp** gọi `ServiceLoader.load(InetAddressResolverProvider.class)` từ một named module riêng, module trực tiếp gọi `ServiceLoader` cần khai báo `uses` theo quy tắc JPMS.

Khi chạy, bảo đảm module provider đã được resolve, chẳng hạn với module provider nằm trong thư mục `mods`:

~~~bash
java --module-path mods --add-modules demo.resolver \
     -cp app.jar demo.app.Main
~~~

Lệnh trên minh họa cách bổ sung provider module vào cấu hình khởi động. Thư mục `mods` phải chứa artifact module đã biên dịch đúng; layout cụ thể còn phụ thuộc cách build. Đối với named module khai báo `provides`, không cần đồng thời tạo `META-INF/services` để thay thế cho khai báo trong `module-info.java`.

**Lưu ý:** Nếu `demo.resolver` chỉ là module có mặt trên module path nhưng chưa được resolve, đừng mặc định `InetAddress` sẽ phát hiện nó. Tương tự, chỉ tạo module layer mới khi ứng dụng đã chạy không tự động thay provider được chọn trước đó.

## 7. Thời điểm lựa chọn và ảnh hưởng của nhiều provider

Khi `InetAddress` thiết lập resolver dùng chung, JDK tìm các provider theo cơ chế nêu trên. Nếu không có provider hợp lệ nào được phát hiện, resolver tích hợp được sử dụng. Nếu nhiều provider hiện diện, **provider được phát hiện đầu tiên** là provider được chọn. Thứ tự phát hiện không phải hợp đồng cấu hình ưu tiên ổn định giữa các cách đóng gói và môi trường chạy.

Các hệ quả thực hành:

- Đăng ký một provider chủ đích cho mỗi cấu hình chạy, thay vì phụ thuộc vào thứ tự các JAR hoặc module.
- Hoàn tất việc đóng gói và cấu hình provider trước khi JVM bắt đầu thực hiện phân giải tên. Đổi TCCL hoặc thêm JAR vào class loader riêng sau khi resolver đã được chọn sẽ không thay thế resolver đang dùng.
- Không giả định có thể chọn resolver khác nhau cho từng tenant, plugin hoặc thread bằng cách chuyển context class loader.
- Khi thử thay đổi provider, khởi động một tiến trình JVM mới để phép đo phản ánh cấu hình mới.
- Nếu provider có lỗi đăng ký, lỗi khởi tạo hoặc lỗi khi thực hiện tra cứu, phải điều tra lỗi đó; không giả định JDK luôn bỏ qua lỗi và âm thầm dùng provider kế tiếp.

Resolver do provider cung cấp có thể phục vụ nhiều lời gọi cùng lúc. Khi triển khai sản phẩm, cân nhắc thread safety, chính sách IPv4/IPv6, cache của `InetAddress`, lỗi `UnknownHostException` và tính nhất quán giữa tra cứu thuận/ngược.

## 8. Kiểm tra đúng phạm vi thay vì chỉ kiểm tra có class

Đoạn mã sau là bước chẩn đoán đơn giản để **liệt kê** những provider mà `ServiceLoader` nhìn thấy qua system class loader:

~~~java
import java.net.spi.InetAddressResolverProvider;
import java.util.ServiceLoader;

public final class ProviderDiagnostics {
    public static void main(String[] args) {
        ClassLoader systemLoader = ClassLoader.getSystemClassLoader();

        ServiceLoader<InetAddressResolverProvider> providers =
                ServiceLoader.load(InetAddressResolverProvider.class, systemLoader);

        providers.stream().forEach(provider ->
                System.out.println(provider.type().getName()));
    }
}
~~~

`provider.type()` cho phép quan sát lớp implementation mà không phải tự gọi `provider.get()`. Phép liệt kê giúp xác định lỗi **discovery**, nhưng chưa chứng minh toàn bộ quá trình tạo resolver và tra cứu đều thành công. Để kiểm tra end-to-end, chạy trong JVM mới và thực hiện một truy vấn qua `InetAddress`.

Trường hợp khó hiểu thường gặp là:

~~~java
Thread.currentThread().setContextClassLoader(pluginClassLoader);

// Có thể tìm thấy provider vì dùng TCCL:
ServiceLoader.load(InetAddressResolverProvider.class);

// Không đồng nghĩa InetAddress sẽ chọn provider trong pluginClassLoader:
InetAddress.getByName("example.com");
~~~

Ví dụ trên chỉ minh họa sự khác biệt về **phạm vi class loader**. `pluginClassLoader` là một class loader riêng do ứng dụng tạo; mẫu mã này không phải cách cài resolver hệ thống.

### Quy trình chẩn đoán

| Triệu chứng | Nơi cần kiểm tra |
| --- | --- |
| Lớp provider có trong JAR nhưng phép liệt kê qua system loader rỗng | Kiểm tra `META-INF/services`, tên lớp đầy đủ, class path thực tế hoặc trạng thái resolve của named module. |
| Tự gọi `ServiceLoader` bằng TCCL thấy provider, nhưng system loader không thấy | Provider chỉ nằm trong phạm vi của class loader riêng; kiểm tra mô hình đóng gói/nạp JAR. |
| Nhìn thấy nhiều provider | Loại bỏ đăng ký ngoài ý muốn; bảo đảm cấu hình chỉ có provider cần dùng. |
| Provider được liệt kê nhưng không thấy log phân giải tên | Xác minh provider tạo resolver thành công, truy vấn có đi qua API cần kiểm tra, thời điểm khởi tạo và cache; thử JVM mới. |
| Chỉ gặp lỗi ở packaged application hoặc framework | Kiểm tra cách framework nạp nested JAR, module và class loader. Đừng suy luận từ kết quả chạy trong IDE. |

## 9. Bài thực hành tự kiểm chứng

Thực hiện theo ba cấu hình độc lập, mỗi lần một JVM mới:

1. **Không nạp provider:** chạy ứng dụng chỉ với `app.jar`. Quan sát kết quả `InetAddress.getAllByName("localhost")`, đây là đường dùng resolver tích hợp trong cấu hình không có provider.
2. **Nạp qua system class loader:** bổ sung `tracing-resolver.jar` vào class path hoặc resolve module provider qua JPMS. Liệt kê provider bằng `ProviderDiagnostics`, sau đó chạy thử truy vấn và quan sát log.
3. **Chỉ nạp qua class loader riêng:** bỏ provider khỏi class path/module configuration của hệ thống, đặt nó trong plugin loader, rồi so sánh phép liệt kê qua TCCL với phép liệt kê qua system class loader. Quan sát vì sao thấy service trong plugin chưa đủ để thay resolver hệ thống.

Khi thực hiện, tự trả lời các câu hỏi:

- `ServiceLoader.load(Service.class)` khác `ServiceLoader.load(Service.class, ClassLoader.getSystemClassLoader())` ở điểm nào?
- Vì sao `Class.forName` nạp được lớp provider vẫn chưa chứng minh `InetAddress` sẽ dùng nó?
- Với named module, vì sao có artifact trên module path chưa chắc đủ?
- Vì sao một phép thử provider nên khởi động JVM mới?
- Vì sao dùng `configuration.builtinResolver()` an toàn hơn việc gọi ngược `InetAddress.getByName` từ trong resolver tùy chỉnh?

## 10. Ghi nhớ

**Phạm vi phát hiện** của `InetAddressResolverProvider` gắn với `ServiceLoader` qua **system class loader**. **Phạm vi sử dụng** của resolver được chọn là cấp JVM. Hai điều đó giải thích phần lớn tình huống provider hoạt động khi nạp trực tiếp nhưng không được `InetAddress` sử dụng trong môi trường plugin, framework hoặc module layer riêng.

Để triển khai đáng tin cậy: khai báo provider theo cơ chế service tương ứng với class path hoặc named module; bảo đảm cấu hình khởi động khiến system class loader có thể tìm thấy provider; chỉ để một provider dự kiến; và kiểm chứng trong JVM mới với cả bước phát hiện lẫn truy vấn thực tế.
