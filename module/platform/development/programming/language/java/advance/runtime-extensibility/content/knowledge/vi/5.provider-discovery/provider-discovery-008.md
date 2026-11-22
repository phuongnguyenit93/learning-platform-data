# ServiceConfigurationError có thể xuất hiện khi khám phá hoặc khởi tạo provider

## 1. Bối cảnh: khám phá provider khác với khởi tạo provider

Trong Java, `java.util.ServiceLoader` là một cơ chế tìm các implementation của một **service contract** (interface hoặc abstract class) mà không cần hard-code từng implementation trong chương trình. Ứng dụng đóng vai trò **consumer/host**; mỗi implementation được phát hành như một **provider**. Ví dụ, host định nghĩa `Greeting`, còn các plugin cung cấp `EnglishGreeting`, `VietnameseGreeting`.

Một quy trình sử dụng có thể có nhiều giai đoạn:

1. **Tạo bộ nạp (`ServiceLoader.load(...)`):** tạo đối tượng quản lý việc tìm provider. Thao tác này thường chưa khởi tạo tất cả provider.
2. **Khám phá (`discovery`):** đọc danh sách provider trong `META-INF/services` hoặc metadata module JPMS, xác định provider có thể được tìm thấy.
3. **Nạp và kiểm tra kiểu:** JVM/`ServiceLoader` tìm class, kiểm tra tính hợp lệ và sự phù hợp với service contract.
4. **Khởi tạo (`instantiation`):** tạo instance bằng constructor hoặc cơ chế `provider()` được JPMS hỗ trợ trong những trường hợp thích hợp.
5. **Gọi nghiệp vụ:** host gọi method trên instance đã nhận.

**`java.util.ServiceConfigurationError` có thể xuất hiện khi Java phát hiện provider được cấu hình không hợp lệ, không tìm/nạp được, không phù hợp contract hoặc không thể khởi tạo.** Một điểm dễ nhầm là lỗi có thể đến khá muộn: code gọi `ServiceLoader.load(...)` thành công nhưng chỉ vỡ khi duyệt iterator, lấy `Provider` từ stream hoặc gọi `Provider.get()`.

`ServiceConfigurationError` là subclass của `java.lang.Error`, **không phải `Exception`**. Vì vậy `catch (Exception e)` không bắt được lỗi này. Mặc dù tên chứa “configuration”, thông tin lỗi có thể liên quan đến quá trình nạp class, liên kết hoặc chạy constructor, chứ không chỉ là sai cú pháp tệp cấu hình.

### 1.1. Vắng provider và provider lỗi là hai tình huống khác nhau

- **Không tìm được provider nào:** với `ServiceLoader` thông thường, một iterator rỗng có `hasNext() == false`; `stream().findFirst()` có thể cho `Optional.empty()`. Đây không tự động là `ServiceConfigurationError`.
- **Có khai báo provider nhưng khai báo/implementation hỏng:** lúc Java phân tích hoặc tạo provider có thể ném `ServiceConfigurationError`.
- **Provider đã được tạo nhưng method nghiệp vụ thất bại:** exception của method đó (ví dụ `IOException`, `IllegalStateException`) không tự động chuyển thành `ServiceConfigurationError` chỉ vì instance được tìm qua `ServiceLoader`.

Phân biệt ba tình huống này giúp host trả đúng thông báo: “không có plugin” khác với “plugin đã khai báo nhưng không thể nạp”, và khác với “plugin chạy rồi nhưng xử lý thất bại”.

## 2. Lỗi xuất hiện ở đâu trong API?

Xem một đoạn code phổ biến:

```java
ServiceLoader<Codec> loader = ServiceLoader.load(Codec.class);
for (Codec codec : loader) {
    System.out.println(codec.name());
}
```

Ở đây `Codec` là service interface do ứng dụng định nghĩa, không phải API sẵn có trong JDK. Vòng `for-each` thực hiện thao tác của iterator phía sau; nếu metadata hoặc provider hỏng, lỗi có thể nổ **bên trong quá trình lặp**, dù dòng `load(...)` đã chạy xong.

| API hoặc thao tác | Điều có thể diễn ra | Điểm cần chú ý |
| --- | --- | --- |
| `ServiceLoader.load(service)` / `load(service, classLoader)` | Tạo loader và thực hiện một số kiểm tra ban đầu | Không bảo đảm đã tìm, kiểm tra và tạo mọi provider; một số điều kiện không hợp lệ có thể lỗi ngay khi gọi |
| `loader.iterator()` | Lấy iterator để khám phá/khởi tạo lazy | Chưa thể kết luận provider hợp lệ chỉ vì tạo iterator thành công |
| `iterator.hasNext()` | Có thể đọc/parse khai báo provider hoặc duyệt thông tin module | Metadata lỗi có thể lộ ra ở bước tìm phần tử kế tiếp |
| `iterator.next()` | Có thể tìm class, kiểm tra subtype, gọi constructor hoặc factory phù hợp | Provider không nạp được hay khởi tạo thất bại có thể ném `ServiceConfigurationError` |
| `loader.stream()` và terminal operation | Stream các đối tượng `ServiceLoader.Provider<S>`, cũng được xử lý lazy | Lỗi có thể phát sinh khi duyệt stream; không xem `stream()` là phép kiểm thử toàn bộ |
| `provider.type()` / `provider.get()` | Tìm kiểu provider hoặc lấy instance (tùy cách đóng gói) | `get()` có thể thất bại lúc khởi tạo provider |
| `loader.reload()` | Xóa cache provider của loader để lần duyệt mới tìm lại | Không tự sửa tệp cấu hình, class bị thiếu hoặc constructor lỗi |

Có thể hình dung tiến trình:

```text
ServiceLoader.load(...)
    |
    v
ServiceLoader (thường chưa có tất cả instance)
    |
    v
iterator / stream: đọc khai báo provider
    |                     |
    | metadata sai        +--> ServiceConfigurationError
    v
tìm class, xác minh provider hợp lệ
    |                     |
    | class/type lỗi      +--> ServiceConfigurationError
    v
khởi tạo provider
    |                     |
    | constructor/factory +--> ServiceConfigurationError
    v
nhận instance, gọi method nghiệp vụ
                          |
                          +--> lỗi nghiệp vụ tùy contract, không mặc định là ServiceConfigurationError
```

Đây là sơ đồ khái niệm. API có thể gộp hoặc trì hoãn từng giai đoạn khác nhau tùy cơ chế classpath hay JPMS. Không dựa vào giả định một lỗi cụ thể luôn phát sinh tại đúng `hasNext()` hay đúng `next()` ở mọi bản Java.

## 3. Các nguyên nhân phổ biến khi khám phá provider

### 3.1. Tệp cấu hình trên classpath không hợp lệ

Với provider được khai báo qua classpath, Java tìm resource có đường dẫn:

```text
META-INF/services/<tên nhị phân đầy đủ của service>
```

Ví dụ service là `com.example.spi.Codec` thì tên tệp là:

```text
META-INF/services/com.example.spi.Codec
```

Nội dung thường là tên nhị phân đầy đủ của từng class provider, mỗi tên một dòng, mã hóa UTF-8; dòng trống và chú thích sau `#` được phép theo định dạng service configuration. Ví dụ:

```text
# Các provider hỗ trợ Codec
com.example.codec.JsonCodec
com.example.codec.XmlCodec
```

Các lỗi cần tìm:

- Tên class không hợp lệ về cú pháp trong tệp cấu hình.
- Đường dẫn tệp cấu hình không đúng tên service hoặc resource bị đóng gói nhầm nơi; tình huống này thường khiến **không tìm được provider**, nhưng không nhất thiết ném lỗi.
- Tệp khai báo một class không còn tồn tại sau refactor hoặc chưa được đóng gói vào JAR/classpath.
- Có nhiều JAR chứa cùng tệp service; cấu hình được tổng hợp lúc khám phá và một tệp hỏng vẫn có thể làm quá trình duyệt thất bại.
- Một JAR shaded/relocated đã đổi package class nhưng descriptor vẫn chứa tên cũ.
- Resource hoặc một mục khai báo không thể đọc/parse đúng cách.

Điểm quan trọng: một JAR hợp lệ về định dạng ZIP vẫn có thể chứa *service configuration* sai. Việc `jar tf plugin.jar` chạy thành công không kiểm chứng rằng từng provider sẽ được tải và tạo instance.

### 3.2. Class được khai báo nhưng không phù hợp service contract

Ví dụ resource yêu cầu `com.example.codec.JsonCodec`, nhưng class đó không implement/extend `com.example.spi.Codec` tương ứng. Java có thể báo `ServiceConfigurationError` thay vì trả về một instance không đúng kiểu.

Cần chú ý **class identity = tên class + class loader định nghĩa class**. Hai class có cùng tên `com.example.spi.Codec` do hai class loader độc lập định nghĩa có thể là hai kiểu Java khác nhau. Một plugin có thể chứa bản sao của interface SPI khiến implementation “trông đúng tên” nhưng không assignable cho service interface của host.

Cách giảm lỗi: để API/SPI chung nằm ở một class loader được chia sẻ theo thiết kế, kiểm soát dependency duplicate và kiểm tra class loader thực tế. Không dùng tên class dưới dạng string để kết luận chắc chắn hai `Class<?>` là cùng một loại.

### 3.3. Sai điều kiện khởi tạo hoặc class không thể nạp

Với provider trên classpath, dạng thông dụng cần một class provider phù hợp service và **public constructor không tham số** để `ServiceLoader` tạo instance. Những tình huống hỏng có thể gồm:

- Class provider không thể truy cập đúng quy định.
- Không có public zero-argument constructor trong cơ chế classpath tương ứng.
- Constructor ném exception khi xây dựng instance.
- Dependency của class thiếu hoặc không tương thích khi liên kết/nạp, làm provider không thể được tạo.
- Static initialization hoặc các bước liên kết class gặp lỗi.

Trong một số đường đi, lỗi gốc được bọc làm `ServiceConfigurationError` và xem qua `getCause()`. Tuy nhiên các lỗi JVM/linkage nghiêm trọng khác cũng có thể phát sinh riêng; không mặc định mọi `LinkageError` hoặc `ExceptionInInitializerError` đều được bao lại theo một hình thức giống nhau.

### 3.4. Khác biệt khi dùng JPMS

Trong hệ thống Java module có tên rõ ràng (JPMS), provider có thể được khai báo trong `module-info.java`:

```java
module example.codec.provider {
    requires example.codec.api;
    provides com.example.spi.Codec
        with com.example.codec.JsonCodec;
}
```

Module consumer thường cần khai báo `uses` cho service:

```java
module example.codec.host {
    requires example.codec.api;
    uses com.example.spi.Codec;
}
```

Với provider trong **explicit named module**, JPMS hỗ trợ một số trường hợp dùng **public static `provider()` factory method** để trả về instance của service; do đó không áp quy tắc “mọi provider bắt buộc có public no-arg constructor” lên mọi kiểu module deployment. Host cần đọc đúng quy tắc cơ chế đang dùng.

Lỗi có thể đến từ việc consumer không khai báo `uses` khi được yêu cầu, khai báo `provides ... with ...` sai, class/provider method không hợp lệ, class không thể khởi tạo, hoặc bố cục module layer sai. Đừng sửa lỗi JPMS bằng cách thêm `META-INF/services` một cách máy móc; kiểm tra module descriptor và đường nạp thực tế trước.

## 4. Ví dụ Java 17+ chạy được: lỗi khi tìm class và lỗi trong constructor

Ví dụ này độc lập, không cần thư viện ngoài. Nó tạo tạm một resource service configuration để mô phỏng ba tình huống: provider hợp lệ, class provider không tồn tại và constructor provider ném exception. Mỗi tình huống sử dụng một `URLClassLoader` riêng; chương trình dọn tệp tạm sau khi chạy.

Tạo đúng **một tệp `SpiErrorDemo.java`**:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Iterator;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;

public class SpiErrorDemo {
    public interface Greeting {
        String sayHello();
    }

    public static final class Ready implements Greeting {
        public Ready() {}
        @Override public String sayHello() {
            return "hello";
        }
    }

    public static final class Broken implements Greeting {
        public Broken() {
            throw new IllegalStateException("constructor failed");
        }
        @Override public String sayHello() {
            return "never reached";
        }
    }

    static void runCase(String label, String providerName) throws Exception {
        Path root = Files.createTempDirectory("spi-demo-");
        Path services = root.resolve("META-INF").resolve("services");
        Path config = services.resolve(Greeting.class.getName());
        try {
            Files.createDirectories(services);
            Files.writeString(config, providerName + "\n", StandardCharsets.UTF_8);

            try (URLClassLoader loader = new URLClassLoader(
                    new URL[] {root.toUri().toURL()},
                    SpiErrorDemo.class.getClassLoader())) {
                ServiceLoader<Greeting> providers =
                        ServiceLoader.load(Greeting.class, loader);
                System.out.println(label + ": loader created");
                try {
                    Iterator<Greeting> iterator = providers.iterator();
                    Greeting greeting = iterator.next();
                    System.out.println(label + ": " + greeting.sayHello());
                } catch (ServiceConfigurationError error) {
                    System.out.println(label + ": " +
                            error.getClass().getSimpleName());
                }
            }
        } finally {
            Files.deleteIfExists(config);
            Files.deleteIfExists(services);
            Files.deleteIfExists(services.getParent());
            Files.deleteIfExists(root);
        }
    }

    public static void main(String[] args) throws Exception {
        runCase("valid", Ready.class.getName());
        runCase("missing", "not.present.MissingProvider");
        runCase("broken", Broken.class.getName());
    }
}
```

Chạy trong thư mục chứa tệp (JDK 17 trở lên):

```bash
javac --release 17 SpiErrorDemo.java
java SpiErrorDemo
```

**Đầu ra chính xác** đã được kiểm tra với JDK 17+:

```text
valid: loader created
valid: hello
missing: loader created
missing: ServiceConfigurationError
broken: loader created
broken: ServiceConfigurationError
```

Vì sao có kết quả này?

- `valid`: descriptor trỏ đến `SpiErrorDemo$Ready`, class tồn tại, implement `Greeting` và có public no-arg constructor. `next()` trả instance; `sayHello()` trả “hello”.
- `missing`: descriptor trỏ đến `not.present.MissingProvider`, nhưng không có class đó. `load(...)` vẫn trả về một loader; tới khi `next()` tìm provider, Java phát hiện lỗi cấu hình và ném `ServiceConfigurationError`.
- `broken`: class `SpiErrorDemo$Broken` tồn tại và có constructor đúng hình thức, nhưng constructor ném `IllegalStateException`. `ServiceLoader` không thể tạo provider; lời gọi `next()` phát sinh `ServiceConfigurationError`.

Ví dụ in **loại lỗi**, không in `error.getMessage()`, vì thông điệp chi tiết và đường dẫn có thể thay đổi theo môi trường/JDK. Trong ứng dụng thực tế, phải giữ nguyên stack trace và `getCause()` để không đánh mất nguyên nhân.

Một chi tiết ít được để ý là Java binary name của nested class chứa ký tự `$`; ví dụ sử dụng `Ready.class.getName()` thay vì tự đoán tên resource. Nó cũng minh họa vì sao tên file service phải khớp chính xác binary name của service.

Phần tạo `Files.createTempDirectory` chỉ phục vụ demo tự chạy; khi đóng gói plugin thật, resource service configuration thường nằm bên trong JAR, được build tool tạo/copy. Không cần tạo tệp cấu hình tạm mỗi lần ứng dụng chạy.

## 5. Catch đúng vị trí và không nuốt mất lỗi

Một anti-pattern phổ biến:

```java
try {
    ServiceLoader<Codec> codecs = ServiceLoader.load(Codec.class);
    // Chỉ tạo loader, chưa duyệt các provider.
} catch (Exception e) {
    // Có thể không bắt được ServiceConfigurationError.
}
```

Với `Codec` là interface thuộc ứng dụng, đoạn trên chỉ minh họa vị trí catch; nó không đủ để kiểm tra danh sách provider. Nếu cần bắt lỗi khám phá/khởi tạo, bao quanh **thao tác tiêu thụ provider** và bắt chính xác `ServiceConfigurationError`:

```java
ServiceLoader<Codec> codecs = ServiceLoader.load(Codec.class);
try {
    for (Codec codec : codecs) {
        register(codec);
    }
} catch (ServiceConfigurationError failure) {
    // Dùng hệ thống logging thật để lưu stack trace và cause.
    logProviderFailure(failure);
    throw failure; // Ví dụ: fail-fast khi codec là dependency bắt buộc.
}
```

Hai đoạn trên là **mã tích hợp minh họa**, chưa chạy độc lập vì `Codec`, `register` và `logProviderFailure` thuộc ứng dụng.

Hãy chọn chính sách theo vai trò của service:

- **Provider bắt buộc:** fail-fast với nguyên nhân và ngữ cảnh; không báo khởi động thành công khi thiếu một dependency thiết yếu.
- **Provider tùy chọn:** báo rõ extension bị lỗi, cô lập khi có thể và tiếp tục với các provider độc lập được xác minh an toàn. Để skip riêng từng plugin một cách đáng tin cậy, kiến trúc thường cần ranh giới plugin/module/class loader phù hợp.
- **Provider nghiệp vụ quan trọng hoặc có quyền nhạy cảm:** kiểm tra trust, compatibility và authorization trước khi kích hoạt; không dùng lỗi load làm tín hiệu để tự động chọn một provider ít tin cậy hơn.

**Không giả định có thể cứ `catch` rồi gọi `next()` tiếp trên cùng iterator cho tới khi hết lỗi.** Tài liệu API cho phép một số lần duyệt cố phục hồi sau `ServiceConfigurationError`, nhưng khả năng phục hồi không được bảo đảm trong mọi lỗi/cấu hình. Retry không giới hạn có thể lặp lại chính provider hỏng. Cách an toàn hơn là sửa cấu hình, cô lập nguồn lỗi hoặc dừng theo chính sách rõ ràng.

Tương tự, `loader.reload()` làm mới cache khám phá provider; nó **không** sửa class bị thiếu hay constructor luôn ném exception, và không thay thế việc chỉnh class loader/module layer. Tránh `catch (Error)` hoặc `catch (Throwable)` quá rộng khi chỉ muốn xử lý lỗi cấu hình service, vì sẽ trộn `ServiceConfigurationError` với những lỗi JVM nghiêm trọng khác.

## 6. Chẩn đoán lỗi trong dự án thực tế

Khi nhận `ServiceConfigurationError`, hãy ghi lại **stage**, tên service, provider được khai báo (nếu biết), class loader/module layer và root cause; đừng chỉ log một câu “cannot load plugin”. Một quy trình điều tra có thứ tự:

1. **Xác định vị trí thật trong stack trace:** `ServiceLoader.load(...)`, `hasNext()`, `next()`, `Provider.get()` hay code constructor? Dòng gọi API nào làm lỗi xuất hiện quan trọng hơn chỗ host tạo biến loader.
2. **Đọc `error.getMessage()` và chuỗi `getCause()`:** có tên class/provider, lỗi tên sai, không assignable, constructor lỗi hoặc thiếu dependency không? Giữ stack trace gốc để biết failure xảy ra trước hay trong khởi tạo.
3. **Xác minh service contract và cấu hình classpath:** đường `META-INF/services/<service binary name>` có đúng không; mỗi dòng có là binary name hợp lệ không; class provider có nằm trong artifact deploy thực tế không?
4. **Kiểm tra kiểu/class loader:** provider và host có dùng cùng class identity của SPI không; có package bị shade, duplicate JAR, dependency bị loại hoặc class loader cách ly không?
5. **Kiểm tra constructor/factory và phụ thuộc:** provider có constructor theo cơ chế tương ứng không, có dùng environment variable/credential/config bắt buộc khiến constructor ném không? Với JPMS, kiểm tra cả `uses`/`provides`, module readability và provider method.
6. **Tái hiện bằng artifact/runtime deploy thật:** classpath IDE, unit test và production có thể khác nhau. Thử từng plugin độc lập, kiểm tra Java version, module path và parent class loader.
7. **Sửa nguyên nhân, triển khai lại và kiểm thử vòng đời:** discovery, instantiation và method nghiệp vụ phải được xác nhận riêng; chỉ dùng `reload()` khi chính sách runtime cho phép và môi trường đã thực sự thay đổi.

Các lệnh trợ giúp có thể dùng khi xem một JAR (đổi tên file theo artifact của mình):

```bash
jar tf plugin.jar
jar --describe-module --file plugin.jar
```

Lệnh đầu liệt kê entry để tìm `META-INF/services/...` và class mong đợi. Lệnh sau mô tả thông tin module của JAR khi áp dụng; module tự động và explicit module có đặc tính khác nhau. Những lệnh này **chỉ giúp kiểm tra đóng gói**, không bảo đảm provider có thể được khởi tạo.

Trong một hệ thống dùng nhiều class loader, có thể điều tra resource mà loader nhìn thấy:

```java
String path = "META-INF/services/" + Codec.class.getName();
var resources = pluginClassLoader.getResources(path);
while (resources.hasMoreElements()) {
    System.out.println(resources.nextElement());
}
```

Đây là **đoạn chẩn đoán minh họa**, yêu cầu ứng dụng đã định nghĩa `Codec` và `pluginClassLoader`. URL resource có thể chứa đường dẫn môi trường; khi log production cần cân nhắc thông tin nhạy cảm. Khi API không tìm thấy resource, kết quả rỗng chỉ chứng minh **class loader đang dùng** không thấy resource đó, chưa đủ kết luận JAR nguồn không chứa nó.

### 6.1. Những thông tin hữu ích trong log

| Thông tin | Dùng để |
| --- | --- |
| Service interface/binary name | Biết chính xác hợp đồng đang nạp |
| Provider class (nếu đã biết) | Xác định mục khai báo hỏng |
| Plugin artifact, version, checksum (nếu có) | Phân biệt các bản triển khai thực tế |
| Class loader/module name/layer | Phân biệt xung đột class identity và cấu trúc module |
| Giai đoạn `discovery` hay `instantiate` | Khoanh vùng metadata, nạp class hoặc constructor |
| Error message, full stack, cause chain | Truy lỗi gốc và xác định phương án khôi phục |

Không log token, mật khẩu hoặc nội dung cấu hình bí mật lấy được từ provider; thông tin chẩn đoán nên đủ để tìm lỗi nhưng không làm lộ dữ liệu nhạy cảm.

## 7. Các lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “`ServiceLoader.load()` chạy qua là mọi plugin hợp lệ.” | Provider thường được khám phá/khởi tạo lazy | Kiểm tra trong lúc iterate/`Provider.get()` và khởi tạo thật |
| “Không có plugin thì luôn ném `ServiceConfigurationError`.” | Danh sách rỗng là trạng thái khác với cấu hình hỏng | Kiểm tra `hasNext()`/`Optional` và định nghĩa missing-provider policy |
| “Cứ `catch (Exception)` là bắt được lỗi này.” | `ServiceConfigurationError extends Error` | Bắt đích danh `ServiceConfigurationError` ở ranh giới load |
| “Tệp service có đúng tên nghĩa là class nạp được.” | Descriptor có thể trỏ đến class đã đổi package, thiếu dependency hoặc sai kiểu | Kiểm tra classpath, class loader và instantiation |
| “Mọi provider phải có constructor không tham số.” | Explicit JPMS provider có thể dùng public static `provider()` | Áp đúng quy tắc của deployment mode |
| “Nếu catch rồi next tiếp thì chắc chắn bỏ qua provider hỏng.” | Khả năng iterator phục hồi không bảo đảm | Cô lập plugin hỏng hoặc fail-fast theo chính sách |
| “`reload()` là cách sửa lỗi cấu hình.” | Reload chỉ làm mới cache ServiceLoader | Sửa resource/class/config/constructor gốc |
| “Exception trong method nghiệp vụ luôn là cấu hình lỗi.” | Provider đã khởi tạo, lỗi có thể xảy ra sau đó | Xử lý theo contract của method nghiệp vụ |
| “Mỗi class cùng tên sẽ là cùng kiểu SPI.” | Class loader tham gia xác định type identity | Dùng chung API/SPI class có danh tính đúng |
| “Có thể nuốt lỗi để host luôn chạy.” | Host có thể báo ready nhưng thiếu capability bắt buộc | Có health/status rõ, degrade theo chính sách đã định |

## 8. Checklist kiểm thử khám phá và khởi tạo provider

Một hệ thống extensibility đáng tin nên có các ca kiểm thử sau, chạy bằng **đúng classpath/module path của môi trường phát hành**:

- **Provider hợp lệ:** phát hiện được và gọi method có kết quả đúng.
- **Không có provider:** trả trạng thái rỗng theo contract, không diễn giải nhầm thành provider hỏng.
- **Tệp cấu hình sai cú pháp:** phát hiện lỗi và chỉ rõ metadata nào không hợp lệ.
- **Tên class provider không tồn tại hoặc bị đổi khi đóng gói:** phát hiện lỗi đúng giai đoạn; ghi lại tên class và artifact.
- **Class có tên nhưng không assignable cho service:** không cố cast rồi tiếp tục.
- **Thiếu constructor hợp lệ hoặc constructor ném exception:** ghi nhận `ServiceConfigurationError` cùng nguyên nhân (khi được cung cấp).
- **Thiếu dependency, Java version không phù hợp hoặc class loader bị phân chia SPI:** điều tra linkage/class identity theo đúng môi trường runtime.
- **JPMS khai báo `uses`/`provides` thiếu hoặc sai:** phân biệt lỗi module với lỗi classpath.
- **Nhiều provider gồm cả hợp lệ và hỏng:** xác nhận chiến lược fail-fast/cô lập; không phụ thuộc việc iterator tự phục hồi.
- **Provider triển khai method rồi mới lỗi:** đảm bảo hệ thống xử lý theo contract nghiệp vụ, không gán nhãn nhầm cho service discovery.

Điều cốt lõi là **khám phá một provider và sử dụng thành công provider là hai mức xác nhận khác nhau**. Khi thiết kế hệ thống mở rộng Java, hãy phân biệt metadata được công bố, class có thể nạp, instance có thể khởi tạo, và tác vụ nghiệp vụ có thể thực thi. Đặt error handling quanh đúng giai đoạn, giữ root cause và có chính sách rõ ràng đối với provider bắt buộc hay tùy chọn; như vậy `ServiceConfigurationError` trở thành tín hiệu chẩn đoán có ích thay vì một lỗi “ngẫu nhiên” lúc khởi động.