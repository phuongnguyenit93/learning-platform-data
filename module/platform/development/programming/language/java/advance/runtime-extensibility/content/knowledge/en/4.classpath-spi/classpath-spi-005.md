# Quan hệ giữa vị trí tệp đăng ký và khả năng nhìn thấy lớp provider

Trong Java SPI (Service Provider Interface) triển khai trên **classpath**, ứng dụng có thể gọi ServiceLoader để tìm các lớp hiện thực một interface mà không cần viết trực tiếp tên lớp vào mã ứng dụng. Tuy nhiên, việc một JAR có chứa lớp provider **không bảo đảm** ServiceLoader tìm được provider đó; ngược lại, tìm được tệp đăng ký cũng **không bảo đảm** nạp được lớp provider.

Bài học này giải thích đúng hai điều kiện liên quan với nhau:

1. **Tệp đăng ký được nhìn thấy dưới dạng resource**: class loader mà ServiceLoader sử dụng phải tìm được resource có đường dẫn chính xác META-INF/services/<tên đầy đủ của service>.
2. **Lớp provider được nhìn thấy dưới dạng class và tương thích với service**: tên lớp ghi trong resource phải nạp được thông qua class loader đang dùng; lớp phải đúng loại, đáp ứng hợp đồng khởi tạo và dùng cùng danh tính kiểu service với ứng dụng.

Đây là hai bước riêng biệt. Một ứng dụng có thể nhìn thấy lớp provider nhưng không thấy tệp đăng ký; cũng có thể nhìn thấy tệp đăng ký nhưng không thể nạp lớp được nêu trong đó.

## 1. Chuỗi khám phá của ServiceLoader trên classpath

Giả sử ứng dụng có service interface **demo.spi.Formatter** và lớp triển khai **demo.impl.UpperFormatter**. Một provider thông thường được tìm qua quá trình sau:

~~~text
Ứng dụng: ServiceLoader.load(Formatter.class)
                       |
                       v
Chọn ClassLoader L
  - Mặc định: context class loader của thread hiện tại (TCCL)
  - Hoặc: ClassLoader truyền tường minh vào load(service, L)
                       |
                       v
Tìm resource: L.getResources("META-INF/services/demo.spi.Formatter")
                       |
           +-----------+-----------+
           |                       |
     Không có resource        Có resource
           |                       |
           v                       v
    Không phát hiện       Đọc UTF-8, lấy tên provider
    provider từ file                |
                                   v
                       Thử nạp demo.impl.UpperFormatter
                       bằng cơ chế class loading tương ứng
                                   |
                      +------------+------------+
                      |                         |
                  Không nạp được             Nạp được
                      |                         |
                      v                         v
             ServiceConfigurationError    Kiểm tra kiểu và
             khi duyệt provider           cách tạo instance
                                                |
                                  +-------------+-------------+
                                  |                           |
                               Hợp lệ                     Không hợp lệ
                                  |                           |
                                  v                           v
                          Tạo provider theo nhu cầu     ServiceConfigurationError
                          và đưa tới ứng dụng          khi duyệt provider
~~~

Sơ đồ tập trung vào **provider trên classpath (unnamed module)**. Trong JVM có named modules, ServiceLoader còn thực hiện khám phá provider theo module descriptor, được phân biệt ở phần sau.

Có hai mốc thời gian cần nhớ:

- Lời gọi ServiceLoader.load(...) chủ yếu tạo đối tượng phục vụ khám phá; việc phân tích tệp, nạp và tạo provider có tính **lazy**, thường xảy ra khi gọi iterator/next, findFirst hoặc xử lý stream.
- Khi không có tệp đăng ký nào phù hợp, thao tác duyệt có thể trả về danh sách rỗng. Khi tệp có khai báo sai, thao tác duyệt thường ném **ServiceConfigurationError**, thay vì im lặng bỏ qua cấu hình lỗi.

**Điều kiện cần** để một provider được phát hiện qua cơ chế tệp đăng ký classpath là đường dẫn resource đúng và nhìn thấy được, tên provider được khai báo đúng, lớp provider có thể được loader cần thiết nạp và đáp ứng hợp đồng service. Việc lớp và tệp nằm cạnh nhau chỉ là một cách đóng gói thuận tiện; **không phải** điều kiện bắt buộc.

## 2. Tệp đăng ký phải nằm ở đâu?

Với SPI trên classpath, tên resource luôn theo mẫu:

~~~text
META-INF/services/<fully.qualified.ServiceType>
~~~

Ví dụ:

~~~text
META-INF/services/demo.spi.Formatter
~~~

Nội dung UTF-8 của tệp này:

~~~text
demo.impl.UpperFormatter
~~~

Phải phân biệt **tên tệp** và **nội dung tệp**:

| Thành phần | Dùng tên của ai? | Ví dụ |
| --- | --- | --- |
| Tệp trong META-INF/services | **Service interface hoặc service class** | META-INF/services/demo.spi.Formatter |
| Một dòng trong tệp | **Lớp provider triển khai service** | demo.impl.UpperFormatter |
| Class file thực tế | Đường dẫn package của provider | demo/impl/UpperFormatter.class |

Tên phải là **tên nhị phân đầy đủ** (fully qualified binary name), khớp chữ hoa/chữ thường. Không thêm phần mở rộng .class, không ghi đường dẫn filesystem thay tên lớp và không dùng tên đơn giản UpperFormatter khi provider nằm trong package. Tệp đăng ký không phải file Java, không phải annotation và không được đặt cùng thư mục package với Formatter.class.

Một tệp có thể chứa nhiều provider, mỗi tên trên một dòng, có dòng trống và chú thích bắt đầu bằng #. Tên bị lặp lại trong cùng tệp hoặc xuất hiện ở nhiều tệp cấu hình cùng service sẽ được ServiceLoader bỏ qua bản trùng khi khám phá. Thứ tự provider trên classpath phụ thuộc thứ tự các resource mà loader tìm được, rồi đến thứ tự tên trong mỗi tệp; ứng dụng không nên coi thứ tự classpath toàn hệ thống là chính sách ưu tiên bền vững.

### Đường dẫn nguồn và đường dẫn runtime là hai chuyện khác nhau

Trong dự án Maven/Gradle thông dụng, tệp được **viết** ở:

~~~text
provider-project/src/main/resources/META-INF/services/demo.spi.Formatter
~~~

Nhưng khi chạy, nó phải nằm tại **gốc classpath root hoặc gốc JAR** ở vị trí:

~~~text
META-INF/services/demo.spi.Formatter
~~~

Khi đóng gói một provider JAR đúng, cấu trúc cuối cùng có thể như sau:

~~~text
provider.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── services/
│       └── demo.spi.Formatter
└── demo/
    └── impl/
        └── UpperFormatter.class
~~~

Nếu tệp còn bị đóng gói thành **src/main/resources/META-INF/services/demo.spi.Formatter** bên trong JAR, ServiceLoader tìm đường dẫn bắt đầu từ META-INF/services sẽ không thấy nó. Tương tự, một file ở **META-INF/service/** (thiếu chữ s), tên interface sai package hay khác chữ hoa/chữ thường cũng không khớp.

Resource phải thực sự được đưa vào bản build. Chỉ tạo tệp trong source tree chưa đủ; hãy kiểm tra sản phẩm cuối cùng bằng lệnh jar --list hoặc jar --describe-module tùy mục đích. Đừng suy luận từ IDE rằng tệp chắc chắn có trong JAR.

## 3. Vì sao tìm được tệp đăng ký vẫn có thể không nạp được provider?

Sau khi thấy dòng demo.impl.UpperFormatter, ServiceLoader còn phải làm việc với **class**, không chỉ với resource.

Một provider trên classpath thông thường phải:

1. Là **lớp public, concrete** triển khai hoặc kế thừa đúng kiểu service; tránh abstract class hoặc interface dùng làm provider classpath.
2. Có **public constructor không tham số** để ServiceLoader khởi tạo; các constructor còn lại có thể tồn tại nhưng không thay thế điều kiện này.
3. Có bytecode của chính nó và các lớp phụ thuộc cần thiết được class loader nạp được.
4. Khi kiểm tra kiểu, thực sự **assignable** tới đối tượng Class của service mà ứng dụng đã truyền vào ServiceLoader.

Yếu tố cuối rất quan trọng: trong JVM, danh tính lớp gắn với **tên nhị phân và class loader định nghĩa lớp**. Hai kiểu cùng tên demo.spi.Formatter nhưng được định nghĩa bởi hai class loader khác nhau là hai Class khác nhau. Vì vậy, một provider biên dịch với một bản Formatter riêng trong child-first loader có thể bị đánh giá là không triển khai Formatter của host.

Cách thiết kế thường dùng cho plugin là đặt **service API chung ở loader cha**, để provider loader ủy quyền nạp Formatter cho cha. Plugin giữ riêng lớp triển khai và phụ thuộc đặc thù, còn host cùng plugin dùng chung một đối tượng Class cho interface.

### Các kiểu “nhìn thấy” khác nhau

- **Resource visibility**: loader tìm được tệp đăng ký qua getResources(path).
- **Class visibility**: loader nạp được tên provider và những phụ thuộc của provider.
- **Type compatibility**: provider thật sự là subtype/implementation của cùng Class service mà caller dùng.
- **Instantiation**: provider có constructor hợp lệ và khởi tạo thành công.

Chỉ thỏa một hoặc hai bước đầu vẫn chưa đủ. Không nên dùng Class.forName(providerName) với loader mặc định làm chứng cứ duy nhất, bởi caller của phương thức đó và ServiceLoader có thể dùng hai loader khác nhau.

## 4. Ví dụ Java 17: ba JAR và hai cách chọn class loader

Ví dụ tự chạy này cố ý tách ba thành phần:

- **api.jar**: hợp đồng demo.spi.Formatter dùng chung.
- **provider.jar**: lớp demo.impl.UpperFormatter cùng tệp META-INF/services/demo.spi.Formatter.
- **app.jar**: ứng dụng dùng ServiceLoader.

Cấu trúc file nguồn:

~~~text
spi-demo/
└── src/
    ├── demo/
    │   ├── spi/
    │   │   └── Formatter.java
    │   ├── impl/
    │   │   └── UpperFormatter.java
    │   └── app/
    │       └── Main.java
    └── META-INF/
        └── services/
            └── demo.spi.Formatter
~~~

**File src/demo/spi/Formatter.java:**

~~~java
package demo.spi;

public interface Formatter {
    String format(String input);
}
~~~

**File src/demo/impl/UpperFormatter.java:**

~~~java
package demo.impl;

import demo.spi.Formatter;
import java.util.Locale;

public final class UpperFormatter implements Formatter {
    public UpperFormatter() {
    }

    @Override
    public String format(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

**File src/META-INF/services/demo.spi.Formatter:**

~~~text
demo.impl.UpperFormatter
~~~

**File src/demo/app/Main.java:**

~~~java
package demo.app;

import demo.spi.Formatter;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ServiceLoader;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            show("context", ServiceLoader.load(Formatter.class));
            return;
        }

        if (args.length == 1 && args[0].equals("child")) {
            // Classpath hệ thống của lần chạy này không chứa provider.jar.
            show("context", ServiceLoader.load(Formatter.class));

            URL providerUrl = Path.of("build/provider.jar").toUri().toURL();
            try (URLClassLoader pluginLoader = new URLClassLoader(
                    new URL[] { providerUrl },
                    Formatter.class.getClassLoader())) {

                // Loader này thấy provider.jar và dùng chung Formatter từ cha.
                show("child", ServiceLoader.load(Formatter.class, pluginLoader));
            }
            return;
        }

        throw new IllegalArgumentException("Dùng không đối số hoặc child");
    }

    private static void show(String label, ServiceLoader<Formatter> loader) {
        int count = 0;
        for (Formatter provider : loader) {
            count++;
            System.out.println(label + " -> "
                    + provider.getClass().getName() + ": "
                    + provider.format("Xin chào"));
        }
        System.out.println(label + " count=" + count);
    }
}
~~~

Code không phụ thuộc framework hay thư viện bên ngoài. Chương trình chạy trên **JDK 17+**; đầu ra cố định vì chỉ có một provider và định dạng chuỗi dùng Locale.ROOT.

### Biên dịch và đóng gói

Từ thư mục **spi-demo**, chạy trong Bash (Linux/macOS/Git Bash):

~~~bash
mkdir -p build/api build/provider build/app build/provider/META-INF/services

javac -encoding UTF-8 -d build/api src/demo/spi/Formatter.java
javac -encoding UTF-8 -cp build/api -d build/provider src/demo/impl/UpperFormatter.java
cp src/META-INF/services/demo.spi.Formatter build/provider/META-INF/services/
javac -encoding UTF-8 -cp build/api -d build/app src/demo/app/Main.java

jar --create --file build/api.jar -C build/api .
jar --create --file build/provider.jar -C build/provider .
jar --create --file build/app.jar -C build/app .
~~~

Trên Windows PowerShell, có thể thay lệnh mkdir -p bằng New-Item -ItemType Directory -Force cho từng thư mục và thay cp bằng Copy-Item. Các lệnh javac và jar còn lại giữ nguyên.

Kiểm tra nội dung JAR sau build:

~~~bash
jar --list --file build/provider.jar
~~~

Trong danh sách phải có cả hai entry:

~~~text
META-INF/services/demo.spi.Formatter
demo/impl/UpperFormatter.class
~~~

Lưu ý: lệnh jar --list còn có thể hiển thị thư mục và manifest; hai dòng trên là **các entry cần kiểm tra**, không phải toàn bộ stdout.

### Thí nghiệm A: classpath không chứa provider.jar

~~~bash
java -cp "build/api.jar:build/app.jar" demo.app.Main
~~~

Kết quả chính xác:

~~~text
context count=0
~~~

Ứng dụng có interface Formatter và mã gọi ServiceLoader, nhưng loader mặc định không nhìn thấy tệp đăng ký trong provider.jar vì JAR đó chưa được đưa vào classpath. Không tìm được provider không đồng nghĩa code UpperFormatter sai.

### Thí nghiệm B: đưa provider.jar vào classpath

~~~bash
java -cp "build/api.jar:build/provider.jar:build/app.jar" demo.app.Main
~~~

Kết quả chính xác:

~~~text
context -> demo.impl.UpperFormatter: XIN CHÀO
context count=1
~~~

Bây giờ context class loader của thread chính (ở ứng dụng chạy tiêu chuẩn này là application class loader) nhìn thấy tệp META-INF/services/demo.spi.Formatter và lớp demo.impl.UpperFormatter, đồng thời provider triển khai Formatter lấy từ api.jar.

### Thí nghiệm C: provider.jar chỉ có trong child URLClassLoader

Giữ provider.jar ngoài classpath hệ thống và truyền tham số child:

~~~bash
java -cp "build/api.jar:build/app.jar" demo.app.Main child
~~~

Kết quả chính xác:

~~~text
context count=0
child -> demo.impl.UpperFormatter: XIN CHÀO
child count=1
~~~

Đây là bằng chứng quan trọng về quan hệ **vị trí resource – loader được chọn – khả năng nạp class**:

- Lần gọi ServiceLoader.load(Formatter.class) dùng context class loader của thread hiện tại. Loader này không có provider.jar nên không thấy đăng ký.
- Lần gọi ServiceLoader.load(Formatter.class, pluginLoader) dùng URLClassLoader mới có URL trỏ đến provider.jar. Nó thấy tệp đăng ký và nạp provider.
- Parent của pluginLoader là Formatter.class.getClassLoader(); nhờ ủy quyền từ loader con sang loader cha cho service API, provider và host cùng dùng một kiểu Formatter.

Nếu sau đó gọi ServiceLoader.load(Formatter.class) từ thread đã tạm **đặt context class loader thành pluginLoader**, lần khám phá cũng có thể thấy provider; phải khôi phục loader cũ trong finally và tránh giữ lại class loader/plugin đã được đóng. Sử dụng tham số loader tường minh thường dễ kiểm soát hơn khi host chủ động quản lý từng plugin.

**Trên Windows**, classpath separator là dấu chấm phẩy (**;**), còn trên Linux/macOS là dấu hai chấm (**:**). Vì vậy phần -cp của ví dụ A có thể viết -cp "build/api.jar;build/app.jar" trong PowerShell. Đây là dấu phân cách phần tử classpath, không thuộc đường dẫn META-INF/services trong JAR.

## 5. Thí nghiệm phân biệt “có class” với “có đăng ký”

Từ build/provider đã tạo ở trên, có thể đóng thêm hai JAR cố tình tách phần lớp và phần resource:

~~~bash
# Chỉ chứa package demo/impl/..., không chứa META-INF/services
jar --create --file build/class-only.jar -C build/provider demo

# Chỉ chứa META-INF/services/..., không chứa demo/impl/...
jar --create --file build/registry-only.jar -C build/provider META-INF
~~~

**Trường hợp 1 — chỉ có class, thiếu tệp đăng ký:**

~~~bash
java -cp "build/api.jar:build/class-only.jar:build/app.jar" demo.app.Main
~~~

Kết quả:

~~~text
context count=0
~~~

JVM có thể nạp lớp provider nếu được yêu cầu bằng tên, nhưng ServiceLoader không có resource khai báo provider để khám phá.

**Trường hợp 2 — chỉ có đăng ký, không có class:**

~~~bash
java -cp "build/api.jar:build/registry-only.jar:build/app.jar" demo.app.Main
~~~

Khi duyệt provider, chương trình sẽ thất bại với **ServiceConfigurationError**, do tên demo.impl.UpperFormatter được khai báo nhưng không thể nạp. Stack trace và cách diễn đạt chính xác có thể thay đổi theo phiên bản JDK; điểm cần kiểm tra là **lỗi lúc khám phá/nạp provider**, chứ không phải một danh sách rỗng hợp lệ.

**Trường hợp 3 — class và đăng ký ở hai JAR khác nhau nhưng cùng nhìn thấy được:**

~~~bash
java -cp "build/api.jar:build/registry-only.jar:build/class-only.jar:build/app.jar" demo.app.Main
~~~

Kết quả:

~~~text
context -> demo.impl.UpperFormatter: XIN CHÀO
context count=1
~~~

Điều này chứng minh **resource và provider class không bắt buộc nằm chung một JAR**. Điều quyết định là loader khởi đầu được ServiceLoader sử dụng nhìn thấy resource và nạp được provider trong mô hình class loading hiệu lực. Tuy vậy, khi phân phối plugin độc lập, đóng chung khai báo và implementation vào một provider JAR thường giúp tránh thiếu một trong hai phần.

## 6. Quan hệ giữa class loader cha, con và thread context class loader

Một class loader có thể tìm resource hoặc class từ những vị trí khác nhau. Với URLClassLoader thông dụng, yêu cầu thường được ủy quyền lên parent trước; một số container/plugin framework dùng quy tắc khác. Bởi vậy, **không suy luận quyền nhìn thấy chỉ từ việc class hoặc JAR tồn tại trên ổ đĩa**. Phải xét loader cụ thể mà ServiceLoader đang dùng, parent chain, URL/classpath được gán và các chính sách của framework.

| Phân bố thực tế | Loader truyền cho ServiceLoader | Hệ quả thường gặp |
| --- | --- | --- |
| Provider JAR không có trong bất kỳ URL/classpath nào của loader được dùng | Application loader | Không thấy tệp đăng ký, 0 provider từ JAR đó |
| Đăng ký và class cùng trong provider JAR mà loader thấy | Application loader | Tìm resource và nạp provider thành công nếu hợp đồng hợp lệ |
| Lớp provider thấy được nhưng resource không nằm đúng đường dẫn | Loader có class | Không tự nhận biết provider; 0 provider từ tệp thiếu |
| Resource nhìn thấy, lớp provider không nạp được | Loader có resource | ServiceConfigurationError khi duyệt |
| Loader con thấy provider JAR, loader cha chỉ thấy service API | Loader con | Thành công khi chia sẻ cùng service Class qua parent |
| Loader cha chỉ thấy API, ứng dụng gọi ServiceLoader.load(service) trong thread có TCCL là cha | Loader cha | Không tìm được provider chỉ nằm ở loader con |
| Plugin có bản sao riêng của API được định nghĩa thành Class khác | Có thể thấy resource và lớp | Có thể gặp lỗi provider không là subtype của service bên host |

Trường hợp tài nguyên được tìm từ loader cha nhưng lớp nằm ở loader con cần phân tích theo **loader khởi đầu trong ServiceLoader.load(service, loader)**. Theo hợp đồng Java SE 17, provider được đăng ký bằng tệp resource có thể nằm JAR khác với tệp; lớp provider phải nhìn thấy được từ loader **ban đầu được truy vấn** để tìm resource, không nhất thiết trùng loader cuối cùng tìm ra resource đó.

**TCCL (thread context class loader)** cho phép hạ tầng chung, dù được định nghĩa trong loader cha, tìm extension của ứng dụng chạy dưới loader con. Mặc định, ServiceLoader.load(Formatter.class) tương đương lời gọi với Thread.currentThread().getContextClassLoader(). TCCL là trạng thái của từng thread, nên môi trường server, thread pool, worker hoặc executor có thể chọn loader khác thread gọi ban đầu.

Trong host plugin, nên quy định một quy tắc nhất quán: sử dụng **ServiceLoader.load(Service.class, pluginLoader)** mỗi lần khám phá, hoặc quản lý TCCL có chủ đích và luôn khôi phục sau khi thao tác. Tránh cache một ServiceLoader dùng TCCL cho tất cả ứng dụng/tenant: loader được dùng khi tạo nó có thể không phù hợp cho yêu cầu sau và việc giữ cache có thể ngăn thu gom class loader cũ.

## 7. Chẩn đoán lỗi theo đúng thứ tự

Khi ServiceLoader không trả provider mong muốn, kiểm tra từ **artifact -> resource -> class -> type -> khởi tạo**, thay vì đoán lỗi constructor ngay.

### Bước 1 — kiểm tra sản phẩm đóng gói

Kiểm tra provider JAR đã thật sự có class và resource:

~~~bash
jar --list --file build/provider.jar
~~~

Tìm chính xác META-INF/services/demo.spi.Formatter và demo/impl/UpperFormatter.class. Với ứng dụng dùng Maven/Gradle, xem JAR **sau khi build/shade/fat-jar**, không chỉ cây thư mục nguồn. Nếu resource đã bị bỏ khỏi JAR, chuyển vào đúng src/main/resources và cấu hình copy resources.

### Bước 2 — xác định loader và dò resource thật

Đây là đoạn chẩn đoán để đưa **bên trong chương trình có sẵn Formatter trên classpath** (không phải một tệp Java chạy độc lập):

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();
String path = "META-INF/services/" + demo.spi.Formatter.class.getName();
var found = loader.getResources(path);
while (found.hasMoreElements()) {
    System.out.println(found.nextElement());
}
~~~

Không in ra URL nào nghĩa là loader đó không nhìn thấy resource qua getResources(path). Nếu có URL, mở đúng tệp để xác nhận tên provider và encoding. Kết quả có thể gồm nhiều resource từ các JAR khác nhau; ServiceLoader có thể ghép các khai báo hợp lệ. Trong container hoặc môi trường dùng class loader đặc biệt, xem lớp thực tế của loader và thứ tự parent.

### Bước 3 — dùng chính loader đó kiểm tra lớp provider

Đoạn chẩn đoán sau cũng chạy trong một chương trình đã import hoặc có API demo.spi.Formatter, sử dụng chính biến loader từ bước trên:

~~~java
Class<?> candidate = Class.forName(
        "demo.impl.UpperFormatter", false, loader);
System.out.println(demo.spi.Formatter.class.isAssignableFrom(candidate));
System.out.println(candidate.getClassLoader());
System.out.println(demo.spi.Formatter.class.getClassLoader());
~~~

- **ClassNotFoundException**: loader không nạp được tên provider; kiểm tra JAR, classpath, parent/child, tên package.
- **NoClassDefFoundError hoặc lỗi liên kết tương tự**: có thể thiếu phụ thuộc hoặc phiên bản class không phù hợp; kiểm tra dependency tree và bytecode/JDK.
- **isAssignableFrom trả false**: provider không thực thi đúng service API, hoặc có bản sao API riêng khiến danh tính Class khác nhau.
- **Các bước trên qua nhưng ServiceLoader vẫn lỗi**: kiểm tra tính public, constructor public không tham số, exception lúc khởi tạo và nội dung tệp cấu hình.

Class.forName(..., false, loader) **chỉ dùng để chẩn đoán khả năng nạp kiểu, chưa khởi tạo provider**. Kết quả của nó không thay cho việc kiểm tra toàn bộ quá trình ServiceLoader. Nếu hệ thống chỉ dùng plugin loader tường minh, thay biến loader bằng **đúng plugin loader** thay vì TCCL.

### Bước 4 — so khớp triệu chứng với nguyên nhân

| Triệu chứng | Nguyên nhân cần thử trước | Cách xác nhận |
| --- | --- | --- |
| Duyệt xong 0 provider | Không thấy resource hoặc tên resource sai | getResources(path) rỗng; jar --list không có entry |
| Có resource nhưng lỗi Provider ... not found | Provider class không nhìn thấy | Class.forName với đúng loader thất bại |
| Lỗi provider not a subtype | API bị nạp thành hai kiểu khác nhau hoặc class triển khai sai | isAssignableFrom, so sánh class loader của service API |
| Lỗi no public no-args constructor | Provider classpath không có constructor public không tham số | Kiểm tra mã class và constructor |
| Chạy bằng IDE được, đóng JAR mất provider | Resource không được copy, plugin JAR không nằm trong runtime classpath | So sánh build output và lệnh khởi chạy |
| Tìm được bằng loader con nhưng không tìm được qua load(service) | TCCL đang là loader khác | In TCCL, gọi load(service, pluginLoader) |
| Một số provider xuất hiện, số khác không | Resource nằm ở classpath khác, thiếu class/dependency hoặc configuration lỗi | Liệt kê tất cả URL resource, duyệt từng provider có xử lý lỗi rõ ràng |
| Sau thêm plugin không xuất hiện | Class loader hoặc ServiceLoader cache vẫn dùng cấu hình cũ | Kiểm tra loader/URL đang hiệu lực và cơ chế reload/discovery |

Trong môi trường thực, bắt ServiceConfigurationError ở ranh giới nạp plugin để ghi log đủ ngữ cảnh (service, provider, loader, artifact) và có chính sách cô lập lỗi. Không nên che lỗi bằng cách trả danh sách rỗng vì sẽ làm người vận hành tưởng là chưa cài plugin.

## 8. Những giới hạn và sai lầm đóng gói hay gặp

### Đổi tên package, shading và fat JAR

Khi build tool ghép nhiều thư viện vào một fat/uber JAR, các JAR có thể cùng chứa META-INF/services/demo.spi.Formatter. Nếu chỉ chép đè một tệp, một số provider sẽ mất đăng ký. Cần **merge service descriptor** bằng chức năng build tương ứng, đồng thời cập nhật tên service/provider trong descriptor khi relocate package.

Ví dụ: class được relocate từ demo.impl.UpperFormatter thành shaded.demo.impl.UpperFormatter nhưng tệp vẫn ghi tên cũ; ServiceLoader thấy registration nhưng không nạp được tên provider cũ. Ngược lại, class đúng mà descriptor bị lọc khỏi JAR thì phát hiện 0 provider.

### Thư mục chứa JAR chưa chắc nằm trong classpath

Đặt provider.jar trong thư mục plugins/ không có nghĩa application class loader tự quét nó. Lệnh -cp chỉ đọc các phần tử được khai báo; cú pháp wildcard dạng lib/* thường mở rộng các JAR **trực tiếp trong lib**, không đệ quy mọi thư mục con. Nếu host nạp plugin động, phải chủ động cấp URL cho plugin loader và dùng loader đó khi gọi ServiceLoader.

Không coi đường dẫn tương đối trong workspace là bằng chứng ở production; trong Java, -cp và working directory thực tế tại lúc chạy mới quyết định những phần tử được tra cứu. Với một JAR thực thi bằng java -jar, tùy chọn -cp người dùng cấp sẽ bị bỏ qua cho đường tìm kiếm class của launcher; cần dùng manifest Class-Path hoặc cơ chế launcher/loader phù hợp, nên kiểm tra mode khởi chạy cụ thể.

### reload không sửa được classpath sai

ServiceLoader.reload() xóa cache provider đã được khám phá của **chính đối tượng ServiceLoader** và cho phép lần duyệt tiếp theo khám phá lại. Nó không tự thêm JAR vào URLClassLoader, không sửa tên entry META-INF/services, không giúp class đã ở loader khác trở thành nhìn thấy được và không bảo đảm unload class. Hệ thống plugin động thường cần một class loader/phiên plugin được quản lý riêng, cùng quy trình đóng tài nguyên và giải phóng tham chiếu.

### Phạm vi service trên classpath và module path

Bài này tập trung classpath. Với **explicit named Java module**, provider thường được công bố qua module-info.java:

~~~java
module demo.provider {
    requires demo.api;
    provides demo.spi.Formatter with demo.impl.UpperFormatter;
}
~~~

Module tiêu thụ service tương ứng khai báo uses demo.spi.Formatter; host cần cấu hình module path, khả năng đọc module và module layer phù hợp. Không thể kết luận tệp META-INF/services của mô hình classpath là phương tiện duy nhất cho tất cả Java SPI. Automatic module có quy tắc tương thích riêng; không đem kết quả lớp/descriptor của classpath áp dụng máy móc cho một ứng dụng đang chạy module path.

## 9. Checklist kiểm tra trước khi phát hành provider

1. **Service name**: tên tệp chính xác META-INF/services/<binary name của service>, đúng chữ hoa/chữ thường, encoding UTF-8.
2. **Registration content**: mỗi dòng là provider binary name, tên đã cập nhật theo shading/relocation.
3. **Artifact**: JAR thành phẩm chứa đường dẫn resource đúng và class bytecode cần thiết, không chỉ hiện diện trong source tree.
4. **Runtime visibility**: loader được ServiceLoader thực sự sử dụng nhìn thấy resource qua getResources và nạp được class/provider dependencies.
5. **Shared API identity**: host và provider dùng cùng Class cho service, không có bản sao không tương thích giữa các loader.
6. **Construction**: provider classpath là lớp concrete public, có public constructor không tham số và khởi tạo không gây lỗi.
7. **Discovery code**: gọi đúng phiên bản load(service, loader) hoặc quản lý TCCL; nhớ rằng provider được khám phá lazy, lỗi có thể xuất hiện khi duyệt.
8. **Packaging tests**: kiểm tra lần chạy chỉ có API, có provider, chỉ có class, chỉ có registration và hai JAR tách riêng; chạy từ lệnh phát hành thực tế.
9. **Lifecycle**: khi hot reload, tái tạo loader/dịch vụ đúng phạm vi và giải phóng các tham chiếu giữ loader cũ; không xem reload() là giải pháp cho tất cả thay đổi classpath.

Một quy trình kiểm tra tốt luôn trả lời đủ **“loader có thấy resource không?”**, **“loader có nạp được provider không?”**, **“provider có đúng service Class và được tạo hợp lệ không?”**. Vị trí tệp đăng ký quyết định bước **khám phá**, còn khả năng nhìn thấy và tương thích của lớp provider quyết định bước **nạp/khởi tạo**; cả hai phải đúng để SPI trên classpath vận hành.

**Tài liệu tham khảo chính thức:** [Java SE 17 ServiceLoader API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html).