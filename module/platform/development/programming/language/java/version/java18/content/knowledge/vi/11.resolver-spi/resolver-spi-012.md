# Đăng ký provider trên classpath bằng META-INF/services và đóng gói đúng tên lớp triển khai

> **Phạm vi:** Bài thuộc chương **Resolver SPI** của `JAVA_VERSION_JAVA18`. JEP 418 (Java 18) cho phép ứng dụng cung cấp `InetAddressResolverProvider` để thay đổi cách `InetAddress` phân giải tên. Bài này hướng dẫn đăng ký provider bằng **service configuration file** trên classpath, biên dịch và đóng gói đúng cấu trúc JAR, xác nhận provider được phát hiện và xử lý lỗi cấu hình. Đây là các API và quy tắc `ServiceLoader` vẫn còn áp dụng trên JDK hiện đại; không dùng cơ chế nội bộ hoặc legacy.

## 1. Hai đối tượng khác nhau: service provider và resolver

JEP 418 định nghĩa hai vai trò:

- `java.net.spi.InetAddressResolverProvider`: **service provider**, do JDK phát hiện và dùng để tạo resolver.
- `java.net.spi.InetAddressResolver`: **resolver**, có phương thức `lookupByName(String, LookupPolicy)` và `lookupByAddress(byte[])` để thực sự tra cứu địa chỉ và hostname.

Khi ứng dụng gọi một API như `InetAddress.getByName("service.lab.invalid")` lần đầu sau khi VM đã khởi động đầy đủ, JDK sử dụng `ServiceLoader` với **system class loader** để tìm `InetAddressResolverProvider`. Provider được chọn sẽ được gọi `get(Configuration)` để tạo resolver dùng chung ở phạm vi JVM.

~~~text
java -cp "app;provider.jar" Demo
                  │
                  ▼
      System class loader thấy provider.jar
                  │
                  ▼
META-INF/services/java.net.spi.InetAddressResolverProvider
                  │
                  ▼
    example.resolver.DemoResolverProvider
                  │
                  ▼
       public constructor không tham số
                  │
                  ▼
       provider.get(Configuration)
                  │
                  ▼
          InetAddressResolver
                  │
                  ▼
     lookupByName / lookupByAddress
~~~

**Điểm quyết định:** Tên *service* dùng để đặt tên tệp là `java.net.spi.InetAddressResolverProvider`; tên *provider implementation* được ghi **bên trong** tệp. Hai tên không thể hoán đổi cho nhau.

## 2. Đường dẫn service file phải chính xác tuyệt đối

Trong JAR dùng trên classpath, `ServiceLoader` tìm resource:

~~~text
META-INF/services/java.net.spi.InetAddressResolverProvider
~~~

Tên tệp là **binary name đầy đủ của lớp service**, không phải tên lớp triển khai, không phải tên module và cũng không có phần mở rộng `.txt`.

Giả sử provider thuộc package `example.resolver` và có lớp:

~~~java
package example.resolver;

public final class DemoResolverProvider
        extends java.net.spi.InetAddressResolverProvider {
    // ...
}
~~~

Nội dung của service configuration file là một dòng:

~~~text
example.resolver.DemoResolverProvider
~~~

Đối chiếu:

| Thành phần | Giá trị đúng | Không dùng |
|---|---|---|
| Thư mục resource | `META-INF/services/` | `META-INF/service/`, `meta-inf/services/` |
| Tên file service | `java.net.spi.InetAddressResolverProvider` | `InetAddressResolver`, `DemoResolverProvider` |
| Nội dung file | `example.resolver.DemoResolverProvider` | `DemoResolverProvider`, đường dẫn `example/resolver/...` |
| Encoding | UTF-8 | File cấu hình sai encoding hoặc có dấu BOM không được nhận diện đúng |
| Vị trí trong JAR | Resource ở **gốc archive** | `resources/META-INF/services/...` nằm sâu bên trong archive |

Tên package và tên lớp **phân biệt chữ hoa/chữ thường**, bất kể một số filesystem khi phát triển không phân biệt chữ hoa/chữ thường.

### Quy tắc nội dung file

Theo đặc tả `ServiceLoader`, provider configuration file:

- Được mã hóa **UTF-8**. Nên lưu UTF-8 không BOM để không có ký tự thừa trước tên lớp đầu tiên.
- Ghi **mỗi tên lớp provider trên một dòng**; dùng fully qualified binary name.
- Cho phép dòng trống và khoảng trắng/tab quanh tên lớp.
- Cho phép ghi chú bắt đầu bằng ký tự `#`; phần sau `#` trên cùng dòng bị bỏ qua.
- Có thể chứa nhiều tên provider, nhưng với Resolver SPI nên hạn chế vì JDK chọn provider đầu tiên được phát hiện và thứ tự đó không được bảo đảm.
- Nếu tên cùng một provider lặp lại, `ServiceLoader` bỏ qua bản ghi trùng.

Ví dụ file hợp lệ:

~~~text
# Service provider cho bài thực hành
example.resolver.DemoResolverProvider
~~~

Để giảm rủi ro khi đóng gói, một provider trong một file cấu hình là lựa chọn dễ kiểm soát nhất.

## 3. Cấu trúc dự án minh họa

Ta sẽ tạo một provider ánh xạ hostname `service.lab.invalid` đến địa chỉ IPv4 tài liệu `203.0.113.17`, rồi chuyển hostname/IP khác cho resolver tích hợp của JDK. Tên miền `.invalid` và dải `203.0.113.0/24` phù hợp cho ví dụ, không nhằm trỏ tới máy chủ thật.

Cấu trúc thư mục:

~~~text
classpath-resolver-demo/
├── src/
│   ├── example/
│   │   └── resolver/
│   │       └── DemoResolverProvider.java
│   └── Demo.java
├── resources/
│   └── META-INF/
│       └── services/
│           └── java.net.spi.InetAddressResolverProvider
└── build/                    # được tạo khi biên dịch
    ├── classes/
    ├── app/
    └── resolver-provider.jar
~~~

Đây là dự án **classpath**: không tạo `module-info.java` và không dùng `--module-path` trong lệnh chạy minh họa. Những phần khác biệt với JPMS được giải thích ở phần sau.

## 4. Triển khai lớp provider đúng hợp đồng

Tệp `src/example/resolver/DemoResolverProvider.java`:

~~~java
package example.resolver;

import java.net.InetAddress;
import java.net.UnknownHostException;
import java.net.spi.InetAddressResolver;
import java.net.spi.InetAddressResolver.LookupPolicy;
import java.net.spi.InetAddressResolverProvider;
import java.util.Arrays;
import java.util.Objects;
import java.util.stream.Stream;

public final class DemoResolverProvider
        extends InetAddressResolverProvider {

    private static final String MANAGED_HOST = "service.lab.invalid";
    private static final byte[] MANAGED_IP = {
            (byte) 203, 0, 113, 17
    };

    // Quan trọng đối với provider trên classpath:
    // public, không tham số, không khởi tạo mạng hoặc gọi DNS.
    public DemoResolverProvider() {
    }

    @Override
    public String name() {
        return "classpath-demo-resolver";
    }

    @Override
    public InetAddressResolver get(Configuration configuration) {
        Objects.requireNonNull(configuration, "configuration");

        // Resolver do JDK cung cấp để ủy quyền những tên ngoài phạm vi.
        InetAddressResolver builtIn = configuration.builtinResolver();

        return new InetAddressResolver() {
            @Override
            public Stream<InetAddress> lookupByName(
                    String host, LookupPolicy policy)
                    throws UnknownHostException {
                Objects.requireNonNull(host, "host");
                Objects.requireNonNull(policy, "policy");

                if (!MANAGED_HOST.equalsIgnoreCase(host)) {
                    // KHÔNG dùng InetAddress.getAllByName(host) ở đây.
                    return builtIn.lookupByName(host, policy);
                }

                // Mapping nội bộ chỉ có địa chỉ IPv4.
                if ((policy.characteristics() & LookupPolicy.IPV4) == 0) {
                    throw new UnknownHostException(
                            "No requested address family for " + host);
                }

                // Tạo InetAddress từ byte có sẵn, không truy vấn DNS.
                return Stream.of(
                        InetAddress.getByAddress(host, MANAGED_IP));
            }

            @Override
            public String lookupByAddress(byte[] addr)
                    throws UnknownHostException {
                Objects.requireNonNull(addr, "addr");
                if (addr.length != 4 && addr.length != 16) {
                    throw new IllegalArgumentException(
                            "IP must contain 4 or 16 bytes");
                }

                if (Arrays.equals(addr, MANAGED_IP)) {
                    return MANAGED_HOST;
                }

                // KHÔNG gọi getCanonicalHostName() để fallback.
                return builtIn.lookupByAddress(addr);
            }
        };
    }
}
~~~

Các điểm cần nhớ khi `ServiceLoader` tạo lớp trên classpath:

1. Lớp provider phải là lớp concrete `public`, được load bằng class loader mà JDK sử dụng và là subtype của `InetAddressResolverProvider`.
2. Có **constructor `public` không tham số** để `ServiceLoader` tạo instance; tránh phụ thuộc vào constructor nhận DI container, database client hoặc tham số cấu hình.
3. Ghi đúng tên đầy đủ `example.resolver.DemoResolverProvider` vào service configuration file.
4. Triển khai `name()` và `get(Configuration)`. Tên từ `name()` hữu ích cho chẩn đoán nhưng không điều khiển thứ tự lựa chọn provider.
5. Giữ constructor và `get` nhẹ. Nếu provider hoặc resolver trong lúc khởi tạo gọi lại `InetAddress.getByName(...)`, có thể tạo chu trình nạp lớp hoặc đệ quy.

Provider này cung cấp cả forward lẫn reverse lookup. Với hostname/IP ngoài phạm vi quản lý, nó ủy quyền trực tiếp qua `Configuration.builtinResolver()` để giữ hành vi hệ thống mà không quay vòng lại API `InetAddress`.

## 5. Viết ứng dụng kiểm chứng có thể chạy độc lập

Tệp `src/Demo.java`:

~~~java
import java.net.InetAddress;
import java.net.spi.InetAddressResolverProvider;
import java.util.ServiceLoader;

public final class Demo {
    public static void main(String[] args) throws Exception {
        // Chẩn đoán: tìm provider qua system class loader,
        // đúng loader mà InetAddress sử dụng để tìm service.
        var providers = ServiceLoader.load(
                InetAddressResolverProvider.class,
                ClassLoader.getSystemClassLoader());

        providers.stream()
                .map(provider -> provider.type().getName())
                .forEach(name -> System.out.println(
                        "Discovered provider: " + name));

        // API ứng dụng bình thường: resolver được JDK chọn.
        InetAddress result =
                InetAddress.getByName("service.lab.invalid");

        System.out.println("Resolved: " + result.getHostAddress());
    }
}
~~~

Kết quả khi đúng provider được phát hiện và được chọn:

~~~text
Discovered provider: example.resolver.DemoResolverProvider
Resolved: 203.0.113.17
~~~

Dòng chẩn đoán `Discovered provider` chứng minh `ServiceLoader` tìm thấy lớp, nhưng **không bảo đảm** rằng nó sẽ là provider được JDK chọn khi có nhiều provider. Dòng `Resolved` kiểm chứng kết quả phân giải từ cấu hình hiện tại của JVM.

Đây là ví dụ dành cho JDK 18 trở lên. `var` và `ServiceLoader.Provider.type()` đã có trước Java 18, không phụ thuộc API đang ở giai đoạn preview.

## 6. Biên dịch, đóng gói JAR và chạy trên classpath

Các lệnh sau dành cho **PowerShell trên Windows**, chạy từ thư mục `classpath-resolver-demo`. Không cần Maven hay Gradle để hiểu cơ chế classpath.

### 6.1. Tạo thư mục build và biên dịch

~~~powershell
New-Item -ItemType Directory -Force -Path build/classes, build/app | Out-Null

javac -d build/classes src/example/resolver/DemoResolverProvider.java

javac -d build/app src/Demo.java
~~~

Ở bước này, `javac` chỉ biên dịch file Java thành `.class`. **Nó không tự đưa resource `META-INF/services` vào `build/classes`** chỉ vì resource nằm trong thư mục `resources`.

### 6.2. Đưa cả class file lẫn service resource vào cùng JAR

~~~powershell
jar --create --file build/resolver-provider.jar -C build/classes . -C resources .
~~~

Giải thích:

- `-C build/classes .` thêm các class file nằm dưới `build/classes` vào gốc archive.
- `-C resources .` thêm nội dung thư mục `resources` vào gốc archive, bao gồm `META-INF/services/...`.
- JAR tạo ra chứa **cả implementation class và provider configuration file**, nên dễ triển khai bằng một file duy nhất.

Cách đóng gói này được khuyến nghị trong bài học vì giảm rủi ro tệp service nằm trong một JAR nhưng lớp implementation lại không có trên classpath. Tuy nhiên, đặc tả `ServiceLoader` vẫn cho phép resource và lớp provider nằm ở hai JAR khác nhau **nếu class loader nhìn thấy cả hai**.

### 6.3. Kiểm tra nội dung JAR trước khi chạy

~~~powershell
jar --list --file build/resolver-provider.jar
~~~

Các mục tối thiểu cần xuất hiện:

~~~text
META-INF/services/java.net.spi.InetAddressResolverProvider
example/resolver/DemoResolverProvider.class
~~~

Có thể còn có `META-INF/MANIFEST.MF` và các thư mục trung gian. Đó là bình thường.

Nếu thấy:

~~~text
resources/META-INF/services/java.net.spi.InetAddressResolverProvider
~~~

thì cấu trúc JAR đã sai: resource bị lồng dưới `resources`, `ServiceLoader` sẽ không tìm ở đường dẫn chuẩn. Hãy sửa lệnh đóng gói để đưa **nội dung** thư mục resources vào gốc archive.

### 6.4. Chạy ứng dụng

~~~powershell
java -cp "build/app;build/resolver-provider.jar" Demo
~~~

Dấu phân cách classpath trên Windows là dấu chấm phẩy `;`. Trên Linux/macOS, đổi thành dấu hai chấm `:`:

~~~shell
java -cp "build/app:build/resolver-provider.jar" Demo
~~~

Nếu ứng dụng và provider đều đặt trong một JAR chung, vẫn phải bảo đảm resource `META-INF/services/...` và class provider nằm đúng vị trí trong JAR ấy. Không cần `Class-Path` trong manifest khi đã truyền đầy đủ `-cp` trong lệnh chạy.

## 7. Quy trình chẩn đoán khi provider không được nạp

Khi tên `service.lab.invalid` không phân giải thành `203.0.113.17`, đừng vội sửa logic `lookupByName`. Kiểm tra từng tầng theo thứ tự:

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Không có dòng `Discovered provider` | JAR hoặc service resource không nằm trên classpath. | Kiểm tra `-cp` và `jar --list`. |
| Có JAR nhưng provider không được phát hiện | File service đặt sai đường dẫn hoặc sai tên service. | Tìm đúng `META-INF/services/java.net.spi.InetAddressResolverProvider`. |
| Provider name trong file không load được | Sai package, sai tên class hoặc thiếu dependency. | So khớp với `package` và vị trí `.class` trong JAR. |
| `ServiceConfigurationError` | Service file hỏng; class không load được; subtype/constructor không hợp lệ. | Kiểm tra UTF-8, cấu trúc file, public no-args constructor và classpath. |
| Provider được phát hiện nhưng kết quả không theo ý muốn | JVM chọn provider khác do có nhiều provider. | Liệt kê provider được tìm thấy, loại bỏ provider không mong muốn. |
| Kết quả khác sau khi sửa JAR | Resolver đã được cài trong JVM hiện tại hoặc có cache. | Chạy bằng **tiến trình JVM mới**. |
| Chỉ gặp lỗi khi đóng gói fat/uber-JAR | Các file service bị ghi đè khi merge dependency. | Cấu hình cơ chế merge `META-INF/services` của công cụ đóng gói. |
| Chạy qua module path không thấy provider | JAR được triển khai theo JPMS/automatic module khác classpath. | Dùng `module-info.java` với `provides ... with ...` cho named module. |

### Không bỏ qua ServiceConfigurationError

`ServiceLoader` có thể ném `ServiceConfigurationError` nếu file cấu hình không hợp lệ, lớp provider không tồn tại, không phải subtype của service hoặc không có constructor phù hợp.

Nếu JDK đã phát hiện một provider nhưng việc khởi tạo resolver thất bại, **không có bảo đảm** rằng JDK sẽ bỏ qua lỗi và tự chuyển sang resolver tích hợp. Javadoc `InetAddressResolverProvider` quy định exception/error từ việc tạo custom resolver được truyền về caller kích hoạt lookup.

Vì vậy cần tách biệt:

- **Không tìm thấy provider:** JDK có thể sử dụng resolver tích hợp.
- **Tìm thấy provider nhưng lỗi khi nạp/tạo resolver:** cần sửa lỗi provider hoặc service configuration; không coi đây là cơ chế fallback.

## 8. Classpath và module path không phải hai cách gọi tương đương

Bài này dùng resource `META-INF/services`, phù hợp với provider trong JAR trên **application classpath**.

Khi triển khai provider dưới dạng **named module**, cơ chế khai báo chuẩn là:

~~~java
module demo.resolver {
    provides java.net.spi.InetAddressResolverProvider
            with example.resolver.DemoResolverProvider;
}
~~~

Trong trường hợp đó, lớp provider được xác định bằng `provides ... with ...` trong `module-info.java`. Module phải có mặt trong module graph khi JVM chạy, chẳng hạn bằng `--module-path` và cách resolve module thích hợp.

| Kiểu triển khai | Nơi khai báo service |
|---|---|
| Classpath JAR | `META-INF/services/java.net.spi.InetAddressResolverProvider` |
| Named module (JPMS) | `module-info.java` với `provides ... with ...` |

Đừng nghĩ chỉ cần di chuyển JAR từ `-cp` sang `--module-path` là mọi cơ chế đăng ký sẽ có cùng hợp đồng. Hãy xác định ứng dụng đang dùng classpath hay module path để chọn cách đăng ký rõ ràng. `ServiceLoader` có các quy tắc riêng cho automatic modules, nhưng triển khai dưới dạng named module với `provides` là cách dễ kiểm soát nhất nếu dự án đã dùng JPMS.

## 9. Lưu ý về thứ tự provider và vòng đời trong JVM

Javadoc `InetAddressResolverProvider` quy định:

- JVM duy trì **một resolver dùng chung** cho `InetAddress` sau khi khởi tạo.
- Provider được tìm qua `ServiceLoader` dùng system class loader.
- **Provider đầu tiên** theo thứ tự discovery do implementation quyết định được dùng để tạo resolver.
- Không có hợp đồng chọn provider theo tên `name()`, tên lớp, tên file JAR hoặc thứ tự ta mong muốn trên classpath.

Nếu hệ thống cần nhiều cách phân giải, đừng đóng gói nhiều provider rồi dựa vào thứ tự để chọn một. Nên có **một provider điều phối**, thực hiện lookup nội bộ trước và ủy quyền phần còn lại cho `configuration.builtinResolver()`.

Một lưu ý khác: việc gọi `ServiceLoader.reload()` trong ứng dụng không phải cơ chế thay thế resolver đã được `InetAddress` cài dùng chung. Khi sửa nội dung provider JAR hoặc service file, hãy kiểm chứng từ **JVM mới**.

Các lookup xảy ra trước khi VM khởi động hoàn tất có thể dùng resolver tích hợp. Vì vậy đặt code nạp provider trong static initializer của ứng dụng không phải cách đáng tin cậy để “ép” chọn provider sớm hơn. Hãy đăng ký đúng classpath trước khi khởi chạy JVM.

## 10. Checklist đóng gói và kiểm chứng

| Bước | Điều cần đạt |
|---|---|
| 1. Lớp provider | `public`, concrete, `extends InetAddressResolverProvider`. |
| 2. Constructor | Có `public DemoResolverProvider()` không tham số, không làm việc mạng. |
| 3. Tên service file | Chính xác `META-INF/services/java.net.spi.InetAddressResolverProvider`. |
| 4. Nội dung file | Tên đầy đủ `example.resolver.DemoResolverProvider`, UTF-8. |
| 5. Vị trí resource | Được đóng vào **gốc JAR**, không nằm dưới `resources/`. |
| 6. Class implementation | Có `example/resolver/DemoResolverProvider.class` trong JAR hoặc dependency nhìn thấy từ class loader. |
| 7. Runtime classpath | `java -cp` chứa JAR provider và các dependency cần thiết. |
| 8. Phát hiện provider | `ServiceLoader` liệt kê đúng implementation. |
| 9. Hành vi | `InetAddress.getByName("service.lab.invalid")` trả `203.0.113.17`. |
| 10. Fallback | Hostname ngoài vùng quản lý ủy quyền cho resolver tích hợp. |
| 11. Không có lỗi cấu hình | Không gặp `ServiceConfigurationError` hoặc exception khi tạo resolver. |
| 12. Kiểm tra lại | Dùng JVM mới sau mỗi lần thay đổi JAR/service file. |

## 11. Câu hỏi tự đánh giá

1. Tại sao tên file dưới `META-INF/services` phải là `java.net.spi.InetAddressResolverProvider` mà không phải `InetAddressResolver`?
2. Tại sao nội dung file service phải ghi `example.resolver.DemoResolverProvider` thay vì `DemoResolverProvider`?
3. Dùng `javac -d build/classes` có tự sao chép file trong `resources/META-INF/services` hay không?
4. Nếu `jar --list` cho thấy `resources/META-INF/services/...`, lỗi đóng gói nằm ở đâu?
5. Khi có nhiều provider, `name()` có quyết định provider nào được chọn không?
6. Khi thấy `ServiceConfigurationError`, có được giả định JDK sẽ luôn fallback về resolver tích hợp không?
7. Vì sao gọi `ServiceLoader.load(...)` trong ứng dụng để liệt kê provider không đủ chứng minh provider đó đã được `InetAddress` chọn?
8. Khi chuyển sang named module, cách khai báo provider thay đổi thế nào?
9. Tại sao sau khi thay JAR nên kiểm thử lại trong JVM mới?

**Ghi nhớ:** Trên classpath, đăng ký resolver provider bằng resource UTF-8 **`META-INF/services/java.net.spi.InetAddressResolverProvider`** chứa tên binary đầy đủ **`example.resolver.DemoResolverProvider`**. Đóng gói cả resource và class implementation đúng vị trí trong JAR, đưa JAR lên `-cp`, rồi kiểm chứng bằng `jar --list`, `ServiceLoader` và kết quả thực tế của `InetAddress`. Nếu JDK đã phát hiện một provider nhưng provider lỗi, không dựa vào fallback ngầm; hãy sửa cấu hình hoặc implementation.

## Tài liệu tham khảo chính thức

- [OpenJDK JEP 418 – Internet-Address Resolution SPI](https://openjdk.org/jeps/418).
- [Java SE 26: `ServiceLoader` – Deploying service providers on the class path](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html).
- [Java SE 26: `InetAddressResolverProvider` – provider discovery và khởi tạo resolver](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolverProvider.html).
- [Java SE 26: `InetAddressResolver` – hợp đồng forward/reverse lookup](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/spi/InetAddressResolver.html).
