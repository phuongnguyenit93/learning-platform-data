# Đóng gói plugin: Tổ chức lớp, tài nguyên và phụ thuộc riêng trong gói phát hành

Một plugin Java không chỉ là một file JAR chứa vài class. Gói phát hành phải cho host biết **đâu là hợp đồng dùng chung, đâu là implementation của plugin, tài nguyên được tìm ở đâu và các thư viện nào phải được nạp cùng plugin**. Sắp xếp đúng những thành phần này giúp host nạp/gỡ plugin có kiểm soát, tránh xung đột phiên bản và có thể chẩn đoán lỗi khi triển khai.

## 1. Xác định ranh giới trước khi đóng gói

Giả sử một ứng dụng host hỗ trợ các plugin triển khai giao diện Greeter. Có bốn nhóm cần phân biệt:

| Thành phần | Vai trò | Nơi nên đặt |
| --- | --- | --- |
| **Plugin API/SPI** | Hợp đồng mà cả host và plugin cùng biên dịch, chẳng hạn interface Greeter và kiểu dữ liệu trao đổi | Một artifact API ổn định, do class loader dùng chung của host nạp |
| **Plugin implementation** | Class hiện thực SPI, thuật toán, cấu hình nội bộ | JAR của từng plugin |
| **Plugin resources** | File cấu hình, template, message bundle, descriptor dịch vụ, dữ liệu mặc định | Đường dẫn resource trong JAR của plugin hoặc thư mục cấu hình được xác định rõ |
| **Private dependencies** | Các thư viện chỉ implementation này sử dụng | JAR phụ thuộc trong thư mục lib của plugin hoặc đã được đóng gói hợp lệ vào JAR plugin |

**Nguyên tắc class identity:** trong JVM, danh tính một class phụ thuộc vào cả *tên nhị phân* và *class loader đã định nghĩa nó*. Hai bản dev.example.spi.Greeter do hai loader khác nhau định nghĩa là hai kiểu khác nhau, dù bytecode giống hệt. Vì vậy host và plugin phải nhìn thấy **cùng một bản API**. Không kèm bản API trùng lặp như một thư viện riêng bị loader con ưu tiên định nghĩa lại.

**Ranh giới trách nhiệm:** host quyết định cách phát hiện, tạo loader, kiểm tra tương thích và quản lý vòng đời; plugin cung cấp implementation cùng tài nguyên/phụ thuộc thực sự cần thiết. Đóng gói tốt không thay thế chính sách nạp class của host: hai việc phải được thiết kế đồng bộ.

## 2. Cấu trúc mã nguồn và gói phát hành

Ví dụ tối giản dùng Java 17+, một host, một API, một plugin và một thư viện trợ giúp chỉ plugin sử dụng:

~~~text
demo/
├── api/src/main/java/dev/example/spi/Greeter.java
├── helper/src/main/java/dev/example/helper/TextUtil.java
├── plugin/src/main/java/dev/example/plugin/HelloGreeter.java
├── plugin/src/main/resources/
│   ├── META-INF/services/dev.example.spi.Greeter
│   └── hello-plugin/message.txt
└── host/src/main/java/dev/example/host/Host.java
~~~

Sau khi build, nơi cài plugin có dạng:

~~~text
release/
└── hello/
    ├── hello-plugin.jar           # implementation + resource + service descriptor
    └── lib/
        └── plugin-helper.jar      # phụ thuộc riêng của plugin
~~~

File plugin-api.jar ở **classpath của host**; không đặt thêm một bản khác vào release/hello/lib. Bản minh họa sử dụng thư viện helper do chính ta biên dịch để thấy rõ cách liên kết phụ thuộc, không cần tải thư viện từ Internet.

Trong dự án thực tế, nên phân biệt rõ ba loại đường dẫn:

- **Source path:** nơi lưu file .java và resource trước khi build.
- **JAR entry path:** đường dẫn bên trong JAR; Java tìm resource theo đường dẫn này, không dựa vào vị trí file nguồn trên đĩa.
- **Deployment path:** nơi host tìm JAR của plugin và các JAR trong lib lúc chạy.

Đổi đường dẫn thư mục triển khai không tự động đổi đường dẫn resource bên trong JAR.

## 3. Ví dụ chạy được: API, class plugin, resource và dependency riêng

### 3.1. Hợp đồng do host cung cấp

File **api/src/main/java/dev/example/spi/Greeter.java**:

~~~java
package dev.example.spi;

public interface Greeter {
    String id();
    String greet(String target);
}
~~~

Interface chỉ chứa những kiểu mà host và plugin đều hiểu. Nếu một phương thức SPI để lộ class của thư viện riêng trong tham số hoặc kiểu trả về, thư viện đó không còn thực sự là private dependency: host cũng phải hiểu kiểu ấy. Với hợp đồng công khai, hãy ưu tiên JDK types hoặc các DTO thuộc artifact API.

### 3.2. Thư viện chỉ plugin sử dụng

File **helper/src/main/java/dev/example/helper/TextUtil.java**:

~~~java
package dev.example.helper;

public final class TextUtil {
    private TextUtil() {}

    public static String compose(String prefix, String target) {
        return prefix + ", " + target + "!";
    }
}
~~~

Helper không được host tham chiếu trực tiếp. Khi chạy, loader dành cho plugin phải tìm được plugin-helper.jar; chỉ đưa JAR vào thư mục lib là chưa đủ nếu host không thêm nó vào đường tìm class.

### 3.3. Class implementation đọc resource của chính plugin

File **plugin/src/main/java/dev/example/plugin/HelloGreeter.java**:

~~~java
package dev.example.plugin;

import dev.example.helper.TextUtil;
import dev.example.spi.Greeter;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;

public final class HelloGreeter implements Greeter {
    @Override
    public String id() {
        return "hello";
    }

    @Override
    public String greet(String target) {
        try (var input =
                 HelloGreeter.class.getResourceAsStream("/hello-plugin/message.txt")) {
            if (input == null) {
                throw new IllegalStateException("Missing hello-plugin/message.txt");
            }
            String prefix =
                    new String(input.readAllBytes(), StandardCharsets.UTF_8).strip();
            return TextUtil.compose(prefix, target);
        } catch (IOException e) {
            throw new UncheckedIOException(e);
        }
    }
}
~~~

File **plugin/src/main/resources/hello-plugin/message.txt** chứa đúng một dòng:

~~~text
Xin chào
~~~

Đường dẫn bắt đầu bằng dấu / trong Class.getResourceAsStream là đường dẫn tuyệt đối từ **gốc classpath của loader định nghĩa HelloGreeter**. Khi build, entry tương ứng trong JAR là hello-plugin/message.txt, không có tiền tố src/main/resources. Việc chỉ định UTF-8 tránh phụ thuộc vào charset mặc định của môi trường.

File **plugin/src/main/resources/META-INF/services/dev.example.spi.Greeter** chứa tên binary của provider, không có đuôi .class:

~~~text
dev.example.plugin.HelloGreeter
~~~

Tên file descriptor phải khớp **tên đầy đủ của interface SPI**; tên trong file phải khớp class implementation. Ví dụ này dùng Java ServiceLoader trên classpath; khi chuyển sang JPMS module path, cơ chế khai báo uses/provides trong module-info.java cần được thiết kế riêng.

### 3.4. Host tạo class loader có đủ JAR

File **host/src/main/java/dev/example/host/Host.java**:

~~~java
package dev.example.host;

import dev.example.spi.Greeter;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ServiceLoader;

public final class Host {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Usage: Host <plugin-directory>");
        }

        Path dir = Path.of(args[0]).toAbsolutePath();
        Path pluginJar = dir.resolve("hello-plugin.jar");
        Path helperJar = dir.resolve("lib/plugin-helper.jar");
        if (!Files.isRegularFile(pluginJar) || !Files.isRegularFile(helperJar)) {
            throw new IllegalArgumentException("Missing plugin or dependency JAR");
        }

        URL[] urls = {pluginJar.toUri().toURL(), helperJar.toUri().toURL()};
        ClassLoader apiLoader = Greeter.class.getClassLoader();

        try (URLClassLoader pluginLoader = new URLClassLoader(urls, apiLoader)) {
            ServiceLoader<Greeter> providers =
                    ServiceLoader.load(Greeter.class, pluginLoader);
            int count = 0;
            for (Greeter provider : providers) {
                System.out.println(provider.id() + " -> " + provider.greet("Java"));
                count++;
            }
            if (count == 0) {
                throw new IllegalStateException("No Greeter provider found");
            }
        }
    }
}
~~~

Đây là **demo với tên file cố định** để dễ kiểm chứng. Host sản phẩm thực tế cần đọc manifest/metadata của plugin, kiểm tra danh sách JAR được phép nạp và quản lý từng loader; không nên suy tên dependency bằng cách ghép tùy tiện từ tên plugin.

Parent của URLClassLoader là loader đã nạp Greeter. URLClassLoader thông thường ủy quyền cho parent trước; vì vậy host và implementation cùng nhìn thấy một class Greeter. URL của plugin-helper.jar cũng được thêm vào loader, giúp HelloGreeter tìm thấy TextUtil mà host không cần thêm helper vào classpath chung.

### 3.5. Biên dịch, đóng JAR và chạy

Chạy từ thư mục **demo/** trong shell POSIX (Linux/macOS, hoặc bash tương thích); cần JDK 17 trở lên:

~~~bash
mkdir -p build/api build/helper build/plugin build/host release/hello/lib

javac -encoding UTF-8 -d build/api api/src/main/java/dev/example/spi/Greeter.java
jar --create --file build/plugin-api.jar -C build/api .

javac -encoding UTF-8 -d build/helper helper/src/main/java/dev/example/helper/TextUtil.java
jar --create --file release/hello/lib/plugin-helper.jar -C build/helper .

javac -encoding UTF-8 -cp "build/plugin-api.jar:release/hello/lib/plugin-helper.jar" -d build/plugin plugin/src/main/java/dev/example/plugin/HelloGreeter.java
jar --create --file release/hello/hello-plugin.jar -C build/plugin . -C plugin/src/main/resources .

javac -encoding UTF-8 -cp build/plugin-api.jar -d build/host host/src/main/java/dev/example/host/Host.java
java -cp "build/host:build/plugin-api.jar" dev.example.host.Host release/hello
~~~

Kết quả tiêu chuẩn:

~~~text
hello -> Xin chào, Java!
~~~

Trên Windows, thay dấu **:** phân cách các phần của classpath trong tham số -cp bằng dấu **;**, đồng thời tạo thư mục theo cú pháp shell đang dùng. Câu lệnh jar -C đóng nội dung class và resource vào **gốc JAR**; không tạo một tầng thừa build/plugin hoặc src/main/resources trong archive.

Kiểm tra gói plugin:

~~~bash
jar --list --file release/hello/hello-plugin.jar
jar --list --file release/hello/lib/plugin-helper.jar
~~~

Trong hello-plugin.jar phải thấy ít nhất ba entry sau (ngoài META-INF/MANIFEST.MF và thư mục):

~~~text
dev/example/plugin/HelloGreeter.class
META-INF/services/dev.example.spi.Greeter
hello-plugin/message.txt
~~~

Trong plugin-helper.jar phải có dev/example/helper/TextUtil.class. **Không** cần Greeter.class nằm trong hello-plugin.jar hoặc plugin-helper.jar. Nếu thiếu service descriptor, ServiceLoader không phát hiện implementation; nếu thiếu resource, phương thức greet báo lỗi theo kiểm tra ở ví dụ; nếu thiếu helper, việc nạp hoặc sử dụng implementation có thể gây NoClassDefFoundError.

## 4. Chọn hình thức phân phối phụ thuộc riêng

| Phương án | Gói phát hành | Điều cần chú ý |
| --- | --- | --- |
| **Thin plugin JAR + lib/** | JAR plugin chỉ chứa implementation/resource; thư viện phụ thuộc đặt thành JAR riêng bên cạnh | Host phải đưa **tất cả** JAR cần thiết vào class loader của plugin, gồm cả dependency bắc cầu cần thiết |
| **Uber/Fat JAR** | Gộp class và resource của nhiều dependency vào một JAR | Phải gộp ServiceLoader descriptors và resource trùng tên đúng cách; kiểm tra trùng class, giấy phép, chữ ký và các file META-INF đặc biệt |
| **Shading + relocation** | Gộp và đổi package của thư viện có nguy cơ xung đột | Cập nhật mọi tham chiếu class/resource/service phù hợp; xem xét reflection, serialisation và tên class lưu trong cấu hình |
| **JAR lồng JAR** | JAR plugin chứa các file .jar bên trong | URLClassLoader/JDK classpath thông thường **không tự tìm class** trong nested JAR; cần loader hỗ trợ rõ ràng hoặc giải nén an toàn trước khi nạp |

Trong Gradle Java plugin, tác vụ jar mặc định thường đóng **output của source set** (class và resource), không tự gộp các external implementation dependencies vào archive. Tương tự, khai báo Maven/Gradle dependency chỉ đảm bảo quan hệ build/resolution theo cấu hình; nó không có nghĩa host đang chạy sẽ tự quét lib của plugin.

Một cách phân loại dependency trong bản build:

- **API do host cung cấp:** plugin cần ở compile time, nhưng bản phát hành của plugin không kèm một bản API được nạp riêng. Với Gradle có thể dùng cấu hình compileOnly cho SPI tương ứng, tùy thiết kế multi-project.
- **Implementation dependency riêng:** cần ở runtime và phải được phân phối trong lib/, hoặc được gộp/relocate theo chiến lược đã kiểm thử.
- **Dependency cần host và plugin chia sẻ:** phải có thỏa thuận phiên bản và class loader thống nhất; chỉ gọi là private khi không xuất hiện trong API/đối tượng trao đổi với host.
- **Tài nguyên riêng:** đóng cùng JAR hoặc chỉ ra vị trí cấu hình bên ngoài; ưu tiên tiền tố tên thư mục theo plugin để tránh resource collision.

Khi có nhiều plugin, **mỗi plugin nên có dependency closure riêng và class loader/lifecycle rõ ràng**. Dùng một classpath toàn cục cho mọi dependency có thể khiến plugin A vô tình dùng phiên bản thư viện do plugin B đưa vào. Tuy nhiên, parent-first loader vẫn có thể chọn class đã có trong parent, kể cả khi lib của plugin có bản khác: thư mục riêng **chưa đủ** để đảm bảo cô lập phiên bản. Nếu thực sự cần nhiều phiên bản cùng tồn tại, hãy kiểm soát những package được parent cung cấp và những package được nạp riêng (chẳng hạn chính sách child-first có chọn lọc hoặc shading), luôn giữ JDK classes và SPI dùng chung ở phía parent.

## 5. Quy tắc tổ chức class và resource

**Giữ package rõ nghĩa.** Đặt SPI vào package độc lập, ví dụ dev.example.spi; implementation vào package của plugin, ví dụ dev.example.plugin; private helper vào package thuộc thư viện riêng. Tránh đặt class plugin vào package của host hoặc cùng tên class với host rồi dựa vào thứ tự classpath.

**Dùng đúng loader để tìm resource.** Với resource gắn chặt implementation, cách gọi HelloGreeter.class.getResourceAsStream giúp tìm theo loader của class ấy. ClassLoader.getResourceAsStream nhận đường dẫn không bắt đầu bằng /; Class.getResourceAsStream với / dùng đường dẫn từ gốc. Đừng giả định System.getClassLoader() hay working directory tìm được resource chỉ nằm trong plugin JAR.

**Lưu ý context class loader (TCCL).** Một số framework/provider dùng Thread.currentThread().getContextClassLoader() để tra cứu class và service. Host có thể cần đặt TCCL bằng loader của plugin trong phạm vi lời gọi thích hợp, rồi **khôi phục trong finally** để không ảnh hưởng tác vụ khác. Ví dụ ở trên dùng overload ServiceLoader.load(service, loader) nên chỉ rõ loader tìm provider.

**Namespace của resource cũng có thể va chạm.** Hai plugin đều có config.yml ở gốc JAR sẽ khó phân biệt nếu host tìm theo class loader chung. Đặt resource dưới đường dẫn riêng như hello-plugin/; cân nhắc cách parent-first tìm resource trước khi khẳng định đó là tài nguyên riêng.

**Đừng xuất lộ dependency private qua SPI.** Nếu host nhận về đối tượng thuộc thư viện riêng và muốn ép kiểu/call method, class identity và phiên bản trở thành hợp đồng ngoài ý muốn. Chuyển qua DTO ổn định của API hoặc kiểu JDK.

**Cơ chế discovery phải được đóng gói đầy đủ.** Với ServiceLoader trên classpath, file META-INF/services/<tên đầy đủ SPI> là một resource của JAR, không phải class và cũng không phải Java manifest. Nếu dùng metadata riêng như plugin.properties hoặc JSON manifest, host phải có code đọc và xác thực nó; Java không tự kích hoạt plugin chỉ vì file tồn tại.

## 6. Version, vòng đời và tính an toàn của gói

Một release nên khai báo/ghi nhận ít nhất **plugin ID, plugin version, API compatibility, entry point/discovery convention, Java target version, tập dependency đã khóa phiên bản và checksum**. Có thể giữ metadata trong manifest hoặc file riêng theo hợp đồng của host. Dùng version pinning và dependency lock khi build; CI tạo cùng một tập artifact dự kiến, kiểm tra license và nguồn dependency.

Tại runtime, host nên thực hiện thứ tự:

1. Khám phá thư mục/gói plugin và kiểm tra metadata, file tồn tại, checksum/chữ ký theo chính sách triển khai.
2. Kiểm tra Java/API compatibility; phát hiện trùng plugin ID và yêu cầu dependency không thỏa.
3. Tạo class loader/module layer với đúng classpath của plugin; giữ SPI thống nhất với host.
4. Nạp provider, kiểm tra type, cấu hình, resource và chạy kiểm thử khởi tạo nhẹ; nếu thất bại, ghi rõ **plugin ID + phiên bản + nguyên nhân**.
5. Theo dõi plugin đang hoạt động; khi dừng, hủy đăng ký, kết thúc task/thread, đóng stream, socket, JDBC pool và loader thích hợp.

Đóng URLClassLoader giải phóng khả năng truy cập file JAR của loader, nhưng **không đảm bảo JVM unload ngay class**. Nếu còn thread, static cache, ThreadLocal, callback hoặc reference từ host tới class/object thuộc plugin, loader có thể tiếp tục được giữ sống. Cơ chế cập nhật nóng cần quy trình dừng/khởi tạo lại và xử lý trạng thái riêng; không giả định chỉ thay JAR trên đĩa là lớp đang nạp tự đổi.

Class loader là ranh giới namespace, **không phải sandbox bảo mật**. Plugin chạy trong cùng JVM có thể sử dụng quyền của tiến trình. Không nạp mã không tin cậy vào host chỉ vì nó nằm trong JAR riêng; với mã chưa tin cậy cần cách ly tiến trình/container, kiểm soát quyền và giao thức trao đổi phù hợp.

## 7. Lỗi thường gặp và cách kiểm tra

| Triệu chứng | Nguyên nhân đáng kiểm tra | Cách xử lý |
| --- | --- | --- |
| ServiceLoader không thấy provider | Thiếu/sai META-INF/services, sai tên binary, provider không nằm trong loader | Liệt kê JAR entries; kiểm tra descriptor, provider có triển khai SPI và loader được truyền đúng |
| ServiceConfigurationError: not a subtype hoặc ClassCastException | Host và plugin đang thấy **hai bản SPI khác class loader** | Đảm bảo SPI đến từ loader chung; bỏ bản API được loader plugin định nghĩa lại |
| ClassNotFoundException / NoClassDefFoundError | Thiếu dependency runtime, sai URL hoặc dependency bắc cầu chưa được mang theo | Liệt kê đủ JAR runtime; so dependency tree và deployment classpath |
| NoSuchMethodError / IncompatibleClassChangeError | Thư viện thực tế được nạp khác bản dùng lúc biên dịch, ABI không tương thích | Kiểm tra class được loader nào nạp; ghim version và kiểm thử với chính gói phát hành |
| Resource trả về null | File không nằm trong JAR, sai đường dẫn hoặc tìm bằng loader khác | Dùng jar --list; kiểm tra dấu / và đường dẫn nội bộ; ưu tiên class gốc của plugin |
| Chạy từ IDE được, cài plugin không chạy | IDE thêm dependency vào classpath toàn cục nhưng release không mang theo | Kiểm thử bằng JAR đã đóng gói trên classpath chỉ chứa host và API |
| Lỗi sau nhiều lần reload | Plugin chưa dừng thread/callback hoặc host vẫn giữ reference tới loader | Theo dõi lifecycle và memory/class loader; cleanup trước khi thay phiên bản |

**Checklist trước khi phát hành:** (1) build sạch từ source; (2) chỉ rõ API chung và dependency riêng; (3) kiểm tra nội dung archive gồm class, META-INF/services và resource; (4) kiểm tra dependency bắc cầu, phiên bản và xung đột; (5) chạy integration test với host thực tế từ thư mục release đã đóng gói, không dựa vào IDE; (6) thử một trường hợp thiếu JAR/resource để xác nhận lỗi có thể chẩn đoán; (7) thử hai plugin có phụ thuộc khác phiên bản nếu hệ thống tuyên bố hỗ trợ cô lập; (8) thử stop/reload và quan sát reference, thread, file handle.

Khi tổ chức đúng **API dùng chung – implementation – resource – private dependencies**, gói plugin có thể được triển khai, kiểm tra và nâng cấp độc lập với mã nguồn host, trong giới hạn compatibility và class-loader policy đã xác định.