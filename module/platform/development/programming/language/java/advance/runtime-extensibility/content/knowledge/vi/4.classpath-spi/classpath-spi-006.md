# Thêm hoặc bỏ JAR provider mà không sửa mã ứng dụng chủ

## Mục tiêu và tình huống

Trong hệ thống có khả năng mở rộng lúc chạy, ứng dụng chủ (host) có thể cần hỗ trợ thêm những cách xử lý mới: bộ đọc định dạng, bộ chuyển đổi dữ liệu, bộ xuất báo cáo hay adapter kết nối dịch vụ. Nếu host phải import từng lớp cụ thể rồi thêm một nhánh điều kiện mỗi lần xuất hiện plugin, ta phải sửa, biên dịch và phát hành lại mã host cho một thay đổi vốn thuộc về plugin.

**Java Service Provider Interface (SPI)** giải quyết vấn đề khám phá implementation trên **classpath**: host phụ thuộc vào một giao diện chung, còn mỗi JAR provider đóng gói implementation và tệp khai báo dịch vụ. Khi khởi động JVM với một tập JAR provider khác, cùng mã host có thể tìm thấy một tập implementation khác qua \`java.util.ServiceLoader\`.

Bài này tập trung vào thao tác **thêm hoặc bỏ JAR provider mà không thay đổi mã nguồn host**. “Lúc chạy” cần hiểu chính xác: trong mô hình classpath thông thường, danh sách JAR được quyết định khi **khởi động tiến trình Java**. Việc đưa thêm JAR vào thư mục sau khi host đã khởi động không khiến application classloader tự nhìn thấy JAR đó; \`ServiceLoader.reload()\` cũng không biến classpath tĩnh thành cơ chế hot-plug.

Sau bài học, có thể:

- Định nghĩa hợp đồng SPI dùng chung giữa host và provider.
- Đóng gói từng provider thành JAR độc lập, kèm khai báo \`META-INF/services\`.
- Khởi chạy **cùng một chương trình host** với 0, 1 hoặc nhiều provider bằng cách thay đổi nội dung thư mục plugin và khởi động lại.
- Phân biệt thay đổi tập JAR lúc deploy với nạp/hủy provider động trong một JVM đang chạy.
- Kiểm tra việc phát hiện provider, tương thích API, xử lý lỗi cấu hình và giới hạn của classpath.

## 1. Quan hệ giữa host, SPI và provider JAR

Giả sử ứng dụng chào người dùng theo nhiều ngôn ngữ. Host chỉ biết hợp đồng:

~~~java
public interface GreetingService {
    String id();
    String greet(String name);
}
~~~

Đây là **bản rút gọn để giải thích**; phần tiếp theo cung cấp mã đầy đủ có package và lệnh biên dịch. Có thể có provider tiếng Việt và tiếng Anh cùng triển khai \`GreetingService\`.

~~~text
                 +----------------------+
                 |  host.jar            |
                 |  ServiceLoader       |
                 +-----------+----------+
                             |
                             v
                 +----------------------+
                 |  greeting-api.jar    |
                 |  GreetingService     |
                 +----------------------+
                             ^
           +-----------------+-----------------+
           |                                   |
+----------+-----------+             +---------+------------+
| greeting-vi.jar       |             | greeting-en.jar       |
| VietnameseGreeting    |             | EnglishGreeting       |
| META-INF/services/... |             | META-INF/services/... |
+----------------------+             +----------------------+
~~~

Cấu trúc này có ba vai trò riêng biệt:

| Thành phần | Host biết gì? | Có thể thay đổi thế nào? |
| --- | --- | --- |
| **SPI/API JAR** | Giao diện \`GreetingService\` và quy ước dùng nó | Thay đổi theo chính sách phiên bản chung |
| **Host JAR** | Tên service, cách tìm provider và gọi phương thức của giao diện | Không cần sửa khi thêm một implementation tương thích |
| **Provider JAR** | Implementation, descriptor khai báo, phụ thuộc riêng nếu có | Có thể thêm/bỏ/thay thế ở bản triển khai mới |

Host không tạo \`new VietnameseGreeting()\`, không import \`EnglishGreeting\` và không hard-code danh sách tên lớp provider. Tập provider khả dụng đến từ các JAR thực sự hiện diện trên runtime classpath.

### Cơ chế của ServiceLoader trên classpath

Với service interface \`example.spi.GreetingService\`, mỗi provider JAR phải chứa tệp có **đường dẫn chính xác**:

~~~text
META-INF/services/example.spi.GreetingService
~~~

Nội dung tệp là tên nhị phân đầy đủ của lớp implementation, mỗi dòng một lớp:

~~~text
example.provider.vi.VietnameseGreeting
~~~

Khi host gọi \`ServiceLoader.load(GreetingService.class)\`, cơ chế SPI dùng classloader liên quan để tìm resource cấu hình \`META-INF/services/example.spi.GreetingService\`, đọc tên lớp provider, rồi tạo instance khi được duyệt. Phát hiện và khởi tạo mang tính **lazy**: việc có một \`ServiceLoader\` không đồng nghĩa mọi provider đã được khởi tạo. Khi lặp qua các phần tử, lỗi descriptor hay khởi tạo có thể mới xuất hiện.

Đối với provider classpath truyền thống, lớp implementation cần là subtype hợp lệ của service, có thể truy cập và có public constructor không tham số. Tệp descriptor **không được đặt tùy ý**, và \`javac\` chỉ biên dịch tệp \`.java\`; khi đóng gói JAR phải đưa resource descriptor vào bằng bước riêng. Trên JPMS module path, khai báo \`uses\`/\`provides\` và quy tắc provider có khác biệt; ví dụ trong bài dùng **classpath và JAR thông thường**.

## 2. Ví dụ đầy đủ trên Java 17

Ví dụ không yêu cầu Maven, Gradle hay thư viện bên ngoài. Cần JDK 17 trở lên, có các lệnh \`javac\`, \`java\` và \`jar\`.

Cấu trúc tệp nguồn đặt dưới thư mục làm việc \`spi-demo\`:

~~~text
spi-demo/
  src/
    api/example/spi/GreetingService.java
    host/example/host/HostApp.java
    vi/example/provider/vi/VietnameseGreeting.java
    vi/META-INF/services/example.spi.GreetingService
    en/example/provider/en/EnglishGreeting.java
    en/META-INF/services/example.spi.GreetingService
  build/                         (tạo bằng các lệnh bên dưới)
~~~

Tên package và đường dẫn tệp phải tương ứng. Tên tệp trong \`META-INF/services\` là **tên đầy đủ của interface**, không phải tên provider.

### 2.1. Hợp đồng API dùng chung

Tệp \`src/api/example/spi/GreetingService.java\`:

~~~java
package example.spi;

/**
 * Hợp đồng nhỏ được host và mọi provider cùng sử dụng.
 */
public interface GreetingService {
    /** Mã provider dùng để trình bày và nhận diện. */
    String id();

    /** Tạo lời chào cho tên được truyền vào. */
    String greet(String name);
}
~~~

API không nhắc đến lớp provider nào, cũng không tham chiếu thư viện riêng. \`id()\` dùng để hiển thị và sắp thứ tự ổn định trong demo. Hệ thống thực tế cần quy tắc xử lý trùng ID nếu dùng ID để chọn provider; ở đây chưa cần thêm cơ chế registry.

### 2.2. Host chỉ dùng SPI và ServiceLoader

Tệp \`src/host/example/host/HostApp.java\`:

~~~java
package example.host;

import example.spi.GreetingService;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.ServiceLoader;

public final class HostApp {
    private HostApp() {
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "An" : args[0];

        List<GreetingService> providers = new ArrayList<>();
        ServiceLoader.load(GreetingService.class).forEach(providers::add);

        // Không dựa vào thứ tự tìm được từ classpath.
        providers.sort(Comparator.comparing(GreetingService::id));

        if (providers.isEmpty()) {
            System.out.println("Không có provider");
            return;
        }

        for (GreetingService provider : providers) {
            System.out.println(
                    provider.id() + " = " + provider.greet(name));
        }
    }
}
~~~

Điểm mấu chốt là **không có import nào từ \`example.provider.*\`**. Host không biết có bao nhiêu provider. Việc sắp xếp theo \`id()\` trong demo giúp output có thứ tự xác định khi thêm nhiều JAR; thứ tự ServiceLoader duyệt các provider không nên được xem là thứ tự ưu tiên nghiệp vụ ổn định.

Dòng \`forEach(providers::add)\` khiến \`ServiceLoader\` duyệt các provider và khởi tạo chúng. Nếu provider không thể tải/khởi tạo, có thể phát sinh \`ServiceConfigurationError\` tại thời điểm này. Trong ứng dụng thực tế, chính sách fail-fast hay bỏ qua plugin lỗi cần được thiết kế rõ ràng, không đơn giản nuốt mọi lỗi.

### 2.3. Provider tiếng Việt

Tệp \`src/vi/example/provider/vi/VietnameseGreeting.java\`:

~~~java
package example.provider.vi;

import example.spi.GreetingService;

public final class VietnameseGreeting implements GreetingService {
    public VietnameseGreeting() {
    }

    @Override
    public String id() {
        return "vi";
    }

    @Override
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Tạo tệp văn bản **\`src/vi/META-INF/services/example.spi.GreetingService\`** với đúng một dòng:

~~~text
example.provider.vi.VietnameseGreeting
~~~

Descriptor nằm trong JAR provider, độc lập với host. Đừng viết path tệp hoặc tên lớp không đầy đủ vào nội dung descriptor.

### 2.4. Provider tiếng Anh

Tệp \`src/en/example/provider/en/EnglishGreeting.java\`:

~~~java
package example.provider.en;

import example.spi.GreetingService;

public final class EnglishGreeting implements GreetingService {
    public EnglishGreeting() {
    }

    @Override
    public String id() {
        return "en";
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Tạo tệp **\`src/en/META-INF/services/example.spi.GreetingService\`** với đúng một dòng:

~~~text
example.provider.en.EnglishGreeting
~~~

Mỗi provider có descriptor riêng; cùng trỏ đến \`GreetingService\` nhưng đăng ký hai lớp khác nhau. Các JAR provider không cần phụ thuộc trực tiếp vào nhau. Nếu sau này provider dùng JSON, HTTP client hoặc một SDK bên thứ ba, các kiểu đó nên nằm bên trong implementation, không xuất hiện trong chữ ký \`GreetingService\`.

## 3. Biên dịch host một lần, đóng gói hai JAR provider

Tại thư mục \`spi-demo\`, dùng Bash trên Linux/macOS hoặc một shell tương thích. Chạy khi đã tạo đầy đủ sáu tệp nguồn/resource ở mục 2:

~~~bash
mkdir -p build/api build/host build/vi build/en build/plugins

# 1. Biên dịch API và tạo greeting-api.jar.
javac --release 17 -encoding UTF-8 \
  -d build/api src/api/example/spi/GreetingService.java
jar --create --file build/greeting-api.jar -C build/api .

# 2. Host chỉ biên dịch với API, không cần lớp provider.
javac --release 17 -encoding UTF-8 \
  -cp build/greeting-api.jar \
  -d build/host src/host/example/host/HostApp.java
jar --create --file build/host.jar -C build/host .

# 3. Mỗi provider biên dịch với cùng API.
javac --release 17 -encoding UTF-8 \
  -cp build/greeting-api.jar \
  -d build/vi src/vi/example/provider/vi/VietnameseGreeting.java
jar --create --file build/greeting-vi.jar \
  -C build/vi . -C src/vi META-INF/services

javac --release 17 -encoding UTF-8 \
  -cp build/greeting-api.jar \
  -d build/en src/en/example/provider/en/EnglishGreeting.java
jar --create --file build/greeting-en.jar \
  -C build/en . -C src/en META-INF/services
~~~

Lệnh \`jar -C build/vi . -C src/vi META-INF/services\` lấy cả lớp \`.class\` đã biên dịch và thư mục khai báo SPI. Tương tự với provider tiếng Anh. Nếu chỉ đóng gói \`.class\` mà quên \`META-INF/services\`, \`ServiceLoader\` có thể không phát hiện provider dù implementation tồn tại trong JAR.

Có thể kiểm tra cấu trúc JAR bằng:

~~~bash
jar --list --file build/greeting-vi.jar
jar --list --file build/greeting-en.jar
~~~

Trong kết quả, phải thấy file \`META-INF/services/example.spi.GreetingService\` và các lớp \`example/provider/.../*.class\`. Thứ tự entry trong danh sách JAR không quan trọng. Trước khi sao chép JAR vào \`build/plugins\`, thư mục này được tạo nhưng còn trống.

## 4. Thêm và bỏ JAR mà không sửa host

Các lần chạy sau dùng **cùng \`build/host.jar\` và \`build/greeting-api.jar\`**. Chỉ nội dung thư mục \`build/plugins\` thay đổi. Mỗi lệnh \`java\` mở một JVM **mới**, nhờ vậy launcher xử lý lại classpath khi startup.

Dòng classpath \`build/plugins/*\` là wildcard do **Java launcher** mở rộng sang những JAR trực tiếp trong thư mục. Hãy giữ ký tự \`*\` trong dấu ngoặc kép để shell không tự xử lý nó theo cách ngoài ý muốn. Java launcher không tìm đệ quy các thư mục con của \`build/plugins\`.

### Trạng thái A: không có JAR provider

~~~bash
java -cp "build/greeting-api.jar:build/host.jar:build/plugins/*" \
  example.host.HostApp
~~~

Output:

~~~text
Không có provider
~~~

Đây là một kết quả hợp lệ của demo: không có JAR nào cung cấp \`GreetingService\`, nên host chạy và xử lý danh sách rỗng theo chính sách được viết sẵn.

### Trạng thái B: thêm JAR tiếng Việt

~~~bash
cp build/greeting-vi.jar build/plugins/
java -cp "build/greeting-api.jar:build/host.jar:build/plugins/*" \
  example.host.HostApp
~~~

Output:

~~~text
vi = Xin chào, An!
~~~

Không cần mở tệp \`HostApp.java\`, gọi một factory tên riêng, hay biên dịch lại \`host.jar\`.

### Trạng thái C: thêm JAR tiếng Anh, giữ JAR tiếng Việt

~~~bash
cp build/greeting-en.jar build/plugins/
java -cp "build/greeting-api.jar:build/host.jar:build/plugins/*" \
  example.host.HostApp
~~~

Output:

~~~text
en = Hello, An!
vi = Xin chào, An!
~~~

Host chủ động sắp xếp theo ID nên output nhất quán. Nếu bỏ lệnh \`sort\`, không nên khẳng định provider nào luôn được in trước khi dùng wildcard classpath.

### Trạng thái D: bỏ JAR tiếng Việt khỏi thư mục plugin

~~~bash
rm build/plugins/greeting-vi.jar
java -cp "build/greeting-api.jar:build/host.jar:build/plugins/*" \
  example.host.HostApp
~~~

Output:

~~~text
en = Hello, An!
~~~

Việc xóa ở đây chỉ áp dụng cho **bản sao** \`build/plugins/greeting-vi.jar\` trong thư mục demo; tệp đã biên dịch \`build/greeting-vi.jar\` vẫn còn để có thể thêm lại. Trong triển khai thật, một bước rollout/rollback thường di chuyển hoặc thay thế JAR rồi khởi động lại dịch vụ một cách kiểm soát.

### Ghi chú Windows

Trên Windows, ký tự phân cách classpath là dấu **chấm phẩy** \`;\` thay cho dấu hai chấm \`:\`. Sau khi đã có các JAR và thư mục plugin, lệnh khởi chạy bằng PowerShell là:

~~~powershell
java -cp "build/greeting-api.jar;build/host.jar;build/plugins/*" example.host.HostApp
~~~

PowerShell có thể dùng \`Copy-Item build/greeting-vi.jar build/plugins/\` và \`Remove-Item -LiteralPath build/plugins/greeting-vi.jar\` để thêm/bỏ bản sao plugin. Các lệnh biên dịch Bash phía trên dùng dấu \`\\\` để xuống dòng; trên PowerShell, hãy viết mỗi lệnh \`javac\`/\`jar\` thành một dòng hoặc dùng cú pháp nối dòng phù hợp của PowerShell.

## 5. Vì sao thêm/bỏ JAR thay đổi kết quả?

Trình tự mỗi lần khởi động:

1. Java launcher nhận classpath gồm \`greeting-api.jar\`, \`host.jar\` và các JAR khớp \`build/plugins/*\` tại thời điểm khởi động.
2. JVM nạp \`HostApp\` và \`GreetingService\`. Chương trình gọi \`ServiceLoader.load(GreetingService.class)\` mà không biết lớp implementation cụ thể.
3. Classloader tìm các resource \`META-INF/services/example.spi.GreetingService\` từ những JAR có thể nhìn thấy.
4. ServiceLoader đọc các tên provider, tải các lớp cần thiết, kiểm tra phù hợp với service và khởi tạo theo cơ chế SPI khi duyệt.
5. Host nhận các đối tượng qua kiểu \`GreetingService\`, sắp xếp theo \`id()\`, gọi \`greet()\` và in kết quả.

Khi **thêm** một JAR đúng chuẩn trước lần khởi động tiếp theo, bước 1 và 3 có thêm một descriptor/provider, vì vậy danh sách host duyệt có thêm phần tử. Khi **bỏ** JAR, descriptor của provider ấy không còn thấy từ classpath mới, nên nó biến mất khỏi danh sách.

**Lưu ý về ServiceLoader.load:** lời gọi một tham số sử dụng thread context classloader theo hợp đồng API Java. Trong ví dụ launcher thông thường, loader này có thể nhìn thấy các JAR trên application classpath. Khi chạy trong application server, framework, custom classloader hoặc môi trường đa loader, phải chọn đúng loader hoặc dùng biến thể \`ServiceLoader.load(service, classLoader)\` khi cần; nếu không thấy descriptor thì danh sách có thể rỗng dù JAR tồn tại trên đĩa.

### Những điều không tự xảy ra

- Thả một JAR mới vào \`build/plugins\` **khi tiến trình đang chạy** không tự cập nhật các URL/tài nguyên của application classloader đã được thiết lập.
- \`ServiceLoader.reload()\` chỉ xóa cache provider của **ServiceLoader instance hiện có**, để các lần duyệt sau đọc lại qua classloader đang dùng. Nếu classloader không nhìn thấy JAR mới, \`reload()\` không thể phát hiện JAR mới.
- Xóa hoặc thay JAR trên đĩa khi tiến trình đang chạy không đảm bảo gỡ lớp, đối tượng hay thread đã được nạp. Classloader có thể tiếp tục giữ các lớp cũ, và cách hệ điều hành xử lý tệp JAR đang mở cũng khác nhau.
- Classpath SPI không phải hệ thống quản lý vòng đời plugin đầy đủ. Nếu cần nạp/gỡ thực sự trong một JVM, phải thiết kế classloader riêng, cơ chế phát hiện nguồn JAR, cache/reload, đóng tài nguyên và chính sách cô lập tương ứng. Đó là phạm vi phức tạp hơn bài SPI classpath cơ bản.

## 6. Đóng gói và triển khai an toàn

Để việc thay JAR không làm host bất ổn, nên giữ quy ước rõ ràng ở ranh giới host/provider.

### Một bản API chung

Cả host và plugin biên dịch dựa trên \`greeting-api.jar\` tương thích. Không đưa thêm một bản khác của \`GreetingService.class\` vào JAR provider, không rename/shade service interface rồi kỳ vọng ServiceLoader coi đó là cùng một kiểu. Trong JVM, danh tính lớp phụ thuộc vào cả tên lớp **và classloader định nghĩa**; hai bản lớp cùng tên nhưng do hai loader khác nhau định nghĩa vẫn có thể không tương thích.

Provider nên dùng hợp đồng nhỏ, ổn định. Nếu thêm method abstract vào interface, đổi tên package hoặc kiểu tham số, provider được biên dịch từ trước có thể hỏng khi host gọi. Công bố dải phiên bản API hỗ trợ và chạy kiểm thử host mới với provider cũ trước khi cập nhật.

### Tài nguyên và cấu hình JAR

Mỗi provider JAR cần chứa:

- Lớp implementation thực sự triển khai SPI.
- Descriptor \`META-INF/services/<tên đầy đủ của service>\` có đúng lớp provider.
- Những tài nguyên bắt buộc của implementation, nếu có.

Nếu dự án dùng Gradle/Maven, descriptor thường đặt ở \`src/main/resources/META-INF/services/...\` để được đưa vào JAR cùng resources. Nếu dùng plugin build tạo descriptor tự động, cần kiểm tra artifact cuối cùng thay vì chỉ nhìn mã nguồn.

Một service có thể có nhiều provider; mỗi JAR có descriptor riêng. Nếu nhiều JAR dùng cùng tên lớp/provider hay dùng cùng ID nghiệp vụ, cần định nghĩa rõ cách phát hiện trùng và xử lý. Demo sắp xếp theo ID nhưng **không** đặt chính sách chống trùng; một ứng dụng sản xuất nên từ chối ID trùng hoặc có chính sách chọn cụ thể.

### Phụ thuộc và rủi ro classpath chung

Ví dụ sử dụng Java chuẩn, nên provider không có phụ thuộc ngoài. Với plugin thực tế, chỉ chép riêng \`plugin.jar\` vào thư mục không đảm bảo đủ class phụ thuộc. Cần đóng gói và khai báo runtime dependencies phù hợp, chẳng hạn JAR phụ thuộc trong thư mục \`lib/*\` bổ sung vào classpath hoặc cách đóng gói được kiểm soát.

**Classpath thông thường không cô lập các dependency version của plugin.** Hai provider đòi các phiên bản thư viện không tương thích có thể đụng độ vì cùng không gian tải lớp. Nếu cần cô lập độc lập từng plugin, thiết kế custom classloader/module layer với quy tắc chia sẻ API là một hướng khác, không phải khả năng tự động của ServiceLoader trên cùng classpath.

**Plugin trên classpath chạy mã Java trong cùng JVM và có quyền truy cập tương ứng với tiến trình host.** Chỉ nạp JAR tin cậy, xác minh nguồn/bản build và chính sách phát hành; SPI không phải sandbox bảo mật.

### Chiến lược deploy và rollback

Khi cập nhật dịch vụ lâu dài, có thể dùng quy trình:

1. Biên dịch và test provider mới với phiên bản API mà host đang dùng.
2. Kiểm tra nội dung JAR và \`META-INF/services\`; giữ metadata phiên bản, nguồn phát hành và checksum nếu quy trình triển khai cần.
3. Đưa JAR cần bật vào thư mục plugin; đưa JAR cần tắt ra khỏi thư mục ấy. Tránh để song song hai bản cùng provider khi chưa có quy ước trùng tên/ID.
4. Khởi động lại host hoặc tạo instance mới với classpath mới; xem log danh sách ID provider đã nạp.
5. Kiểm tra hành vi nghiệp vụ; khi rollback, khôi phục tập JAR cũ và khởi động lại theo cùng cơ chế.

Host **không đổi source code** trong toàn bộ quy trình. Hệ thống vẫn cần kiểm soát việc vận hành, phiên bản và thời điểm khởi động để cập nhật có hiệu lực.

## 7. Các lỗi thường gặp và cách xác định nguyên nhân

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Có JAR nhưng host in “Không có provider” | JAR không nằm trong runtime classpath; thiếu descriptor; descriptor sai đường dẫn; context classloader không nhìn thấy JAR | In classpath, kiểm tra \`jar --list --file\`, đối chiếu tên interface và loader |
| \`ServiceConfigurationError\` | Tên provider trong descriptor sai, lớp không thể tải, không phải subtype hoặc không thể khởi tạo theo quy tắc SPI | Đọc nguyên văn thông báo và cause, kiểm tra FQCN, constructor, API version, classloader |
| \`NoClassDefFoundError\` | Thiếu lớp phụ thuộc khi provider được tải hoặc chạy | Kiểm tra runtime dependencies và artifact của provider |
| \`ClassCastException\` hoặc lỗi “not a subtype” | Có thể do service API bị nạp thành hai danh tính lớp khác nhau hoặc provider triển khai sai hợp đồng | Kiểm tra classloader và tránh đóng gói bản API riêng |
| Kết quả có provider ngoài dự kiến | JAR cũ còn trong thư mục, nhiều descriptor được tìm thấy, thư mục plugin chứa bản trùng | Liệt kê JAR đang có, kiểm tra descriptor từng JAR và quy tắc ID |
| Thêm JAR rồi gọi \`reload()\` vẫn không thấy | Classloader hiện tại không biết JAR mới | Khởi động lại JVM với classpath mới hoặc triển khai cơ chế loader động có chủ đích |
| Thay JAR đang chạy nhưng kết quả vẫn cũ | Lớp/provider cũ đã được nạp, giữ trong cache hoặc đối tượng ứng dụng | Khởi động lại hoặc quản lý lifecycle/unload bằng cơ chế riêng |

Không nên bắt toàn bộ \`Throwable\` rồi tiếp tục chạy như thể mọi lỗi provider là bình thường. Chọn chính sách rõ ràng: dịch vụ bắt buộc thì thất bại sớm với chẩn đoán; dịch vụ tùy chọn thì có thể cô lập và báo cáo lỗi nếu hệ thống được thiết kế để làm điều đó.

## 8. Kiểm thử để chứng minh host độc lập với provider

Bộ kiểm thử tối thiểu nên bao gồm các tình huống sau, luôn xuất phát từ **cùng** mã và artifact host:

| Tập JAR trong \`build/plugins\` | Kết quả mong đợi |
| --- | --- |
| Trống | \`Không có provider\` |
| Chỉ \`greeting-vi.jar\` | Một dòng \`vi = Xin chào, An!\` |
| Chỉ \`greeting-en.jar\` | Một dòng \`en = Hello, An!\` |
| Cả hai JAR | Hai dòng, sắp xếp theo ID: \`en\` rồi \`vi\` |
| Loại bỏ JAR tiếng Việt rồi khởi động lại | Chỉ còn \`en\` |
| Đổi nội dung descriptor thành tên lớp sai trong một bản thử riêng | Phát hiện lỗi nạp service, không silently chấp nhận provider sai |
| Provider được biên dịch với API không tương thích | Phát hiện lỗi lúc biên dịch, liên kết hoặc khi duyệt/gọi tùy loại thay đổi |

Để xác nhận tính độc lập thật sự, thử **biên dịch host chỉ với API JAR**. Không đưa các JAR implementation vào compile classpath của host. Sau đó thử chạy cùng host JAR với nhiều tập provider; nếu cần sửa import, gọi constructor cụ thể hoặc thay logic \`if/else\` trong host mỗi khi thêm provider, thiết kế chưa đạt mục tiêu mở rộng của SPI.

Có thể bổ sung logging sau khi duyệt để ghi ID và loại provider đã chọn; trong hệ thống sản xuất, ghi cả phiên bản và nguồn JAR nếu thông tin này phục vụ vận hành. Tránh cho thứ tự duyệt ngẫu nhiên trở thành quy tắc chọn provider trong nghiệp vụ.

## 9. Khi nào áp dụng và giới hạn cần nhớ

**Phù hợp** khi host có một điểm mở rộng ổn định, provider có thể đóng gói độc lập, và việc bật/tắt provider thông qua **thay classpath ở lần startup tiếp theo** là đủ: parser, exporter, codec, connector hoặc adapter tùy chọn. Đây là một cách giảm phụ thuộc giữa host và phần triển khai.

**Chưa đủ** nếu yêu cầu bật/tắt JAR không gián đoạn trong một JVM đã chạy, cô lập dependency khác phiên bản, giới hạn quyền truy cập của plugin không tin cậy hoặc quản lý lifecycle phức tạp. Các yêu cầu đó cần cơ chế bổ sung. ServiceLoader có ích ngay cả khi dùng trong một kiến trúc loader phức tạp hơn, nhưng bản thân nó không giải quyết toàn bộ các bài toán ấy.

Quy tắc thực hành: **host sở hữu hợp đồng và cách sử dụng service; provider sở hữu implementation và thông tin đăng ký; bộ JAR có mặt trên runtime classpath quyết định các provider mà host có thể khám phá**. Với cách phân tách đó, thêm hoặc bỏ một provider tương thích là thao tác triển khai và khởi động lại, không phải thay đổi mã nguồn host.
