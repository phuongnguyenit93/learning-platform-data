# ServiceConfigurationError và chẩn đoán cấu hình lỗi trong Java ServiceLoader

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Hiểu **java.util.ServiceConfigurationError** báo điều gì, nó khác với việc không có provider và khác với lỗi nghiệp vụ của một provider như thế nào.
2. Xác định lỗi xuất hiện ở bước **phát hiện (discovery)**, **nạp lớp (loading)** hay **tạo instance (instantiation)** khi dùng **ServiceLoader**.
3. Chẩn đoán cấu hình Service Provider Interface (SPI) trong **classpath/JAR** và **Java Platform Module System (JPMS)**.
4. Dùng thông điệp, **cause**, stack trace, kiểm tra nội dung artifact và class loader để tìm nguyên nhân thay vì che lỗi.
5. Thiết kế cách xử lý phù hợp với dịch vụ bắt buộc hoặc plugin tùy chọn và viết kiểm thử ngăn lỗi cấu hình tái xuất hiện.

**Phạm vi:** API chuẩn của JDK còn được hỗ trợ trong các phiên bản Java hiện đại; ví dụ chạy bằng **JDK 17+**. Những tình huống dựa vào classpath vẫn có giá trị trong dự án Java hiện nay. Không cần thư viện lỗi thời hoặc API nội bộ của JDK.

## 1. ServiceConfigurationError là gì?

**java.util.ServiceConfigurationError** là một lớp **kế thừa java.lang.Error**. ServiceLoader sử dụng nó khi có vấn đề trong quá trình **tìm kiếm, nạp hoặc khởi tạo provider** của một dịch vụ. Nó không phải **Exception** và cũng không phải tín hiệu thông thường rằng danh sách provider trống.

Một consumer thường chỉ biết hợp đồng **Service/SPI**, ví dụ **GreetingService**. Các provider tự đăng ký qua **META-INF/services/** khi dùng classpath hoặc **provides ... with ...** trong **module-info.java** khi dùng named modules. ServiceLoader đọc đăng ký đó rồi cung cấp các triển khai cho consumer.

~~~text
Consumer
  │
  ├── ServiceLoader.load(Service.class)
  │
  └── duyệt iterator()/stream()
        │
        ├── phát hiện khai báo provider
        ├── nạp, kiểm tra lớp/phương thức provider
        ├── tạo instance khi được yêu cầu
        └── trả instance triển khai Service
                  │
                  └── consumer mới gọi phương thức nghiệp vụ
~~~

Nếu chuỗi này gặp một đăng ký sai hoặc provider không tạo được, **ServiceConfigurationError** có thể xuất hiện. Nhưng cần phân biệt ba kết quả:

| Kết quả | Ý nghĩa | Cách ứng xử |
| --- | --- | --- |
| **Không có provider** (iterator/stream không có phần tử) | Chưa khám phá được provider nào trong phạm vi đang xét | Nếu provider là bắt buộc, báo lỗi thiếu cấu hình ở tầng ứng dụng; nếu tùy chọn, có thể tiếp tục theo chính sách |
| **ServiceConfigurationError** | Đã có lỗi khi ServiceLoader tìm/nạp/tạo provider hoặc khi kiểm tra điều kiện sử dụng ServiceLoader | Báo lỗi cấu hình rõ ràng, giữ cause/stack trace để sửa artifact hoặc triển khai |
| **Lỗi trong phương thức nghiệp vụ** sau khi đã nhận instance | Provider đang thực hiện một thao tác cụ thể và thao tác đó thất bại | Xử lý theo contract của nghiệp vụ; không mặc định coi là lỗi đăng ký SPI |

**Quan trọng:** Không có provider **không tự động** làm ServiceLoader ném ServiceConfigurationError. Ví dụ, **findFirst()** có thể trả **Optional.empty()** nếu không có provider hợp lệ nào được tìm thấy và không phát sinh lỗi khi khám phá.

### Vì sao lớp này kế thừa Error?

Lỗi cấu hình SPI thể hiện vấn đề nghiêm trọng về cấu hình runtime hoặc khả năng nạp provider. Do đó, không nên mặc định coi nó là lỗi người dùng có thể thử lại vô hạn. Tuy nhiên, tại ranh giới khởi tạo plugin, ứng dụng **có thể bắt riêng ServiceConfigurationError** để bổ sung thông tin chẩn đoán, đóng gói thông báo rõ ràng hoặc dừng khởi động có kiểm soát. Tránh **catch (Throwable)** hoặc **catch (Error)** rộng vì có thể che các lỗi JVM nghiêm trọng khác.

## 2. Thời điểm phát sinh lỗi: tính lazy của ServiceLoader

ServiceLoader **tìm và tạo provider theo nhu cầu**. Vì vậy, việc tạo đối tượng loader không đồng nghĩa đã nạp thành công toàn bộ provider.

Các API cần biết:

| API | Điều xảy ra | Vị trí nên kiểm tra lỗi |
| --- | --- | --- |
| **ServiceLoader.load(Service.class)** | Tạo loader dùng thread context class loader; trong named module còn kiểm tra điều kiện module khai báo dịch vụ | Có thể lỗi ngay tại lời gọi nếu module caller không có **uses** phù hợp hoặc service không truy cập được |
| **loader.iterator()** | Lấy iterator phục vụ việc duyệt lazy | Khi gọi **hasNext()**, **next()** hoặc vòng **for-each** |
| **loader.stream()** | Tạo stream các **ServiceLoader.Provider<S>** | Trong thao tác terminal/duyệt khiến provider được tìm hoặc nạp |
| **Provider.type()** | Lấy kiểu provider để xem metadata mà chưa yêu cầu tạo instance | Quá trình duyệt để có Provider có thể đã thất bại ở bước nạp |
| **Provider.get()** | Lấy/tạo instance thông qua constructor hoặc provider method | Có thể lỗi tại đây do constructor/factory |
| **loader.reload()** | Xóa cache provider của loader để lần duyệt tiếp theo tải lại theo phạm vi hiện tại | Không tự tải JAR từ đĩa vào class loader cũ, không sửa metadata và không phải giải pháp hot deployment |

Ví dụ minh họa, **không phải chương trình Java độc lập**:

~~~java
ServiceLoader<MyService> loader = ServiceLoader.load(MyService.class);

// Nếu có provider cấu hình sai, lỗi có thể xuất hiện khi duyệt:
try {
    for (MyService service : loader) {
        // Consumer đã có instance tại đây.
        use(service);
    }
} catch (ServiceConfigurationError error) {
    // Báo lỗi kèm stack trace/cause ở đúng ranh giới bootstrap.
    throw new IllegalStateException("Không khởi tạo được SPI MyService", error);
}
~~~

**use(service)** và **MyService** trong đoạn trên là ký hiệu của ứng dụng, không phải API có sẵn của JDK. Cách bắt trong ví dụ mang tính định hướng; nếu phương thức **use** cũng tự ném ServiceConfigurationError thì ranh giới bắt sẽ bao gồm cả lỗi đó. Trong code thực tế, nên **tách pha khám phá/khởi tạo khỏi pha gọi nghiệp vụ** như ví dụ chạy được ở mục 4.

### Iterator và stream không hoàn toàn giống nhau

- **Iterator<S>** trả về trực tiếp instance loại **S**; lỗi tạo instance thường xảy ra trong **hasNext()/next()**.
- **Stream<Provider<S>>** cho phép đọc **type()** và lọc provider trước khi **get()**; quá trình tìm/nạp provider vẫn có thể thất bại trong lúc stream được tiêu thụ.
- Sau khi đã gặp lỗi duyệt, Java chỉ có thể cố gắng tìm provider tiếp theo theo cách **best effort**; không có bảo đảm mọi lỗi đều có thể bỏ qua an toàn. Nếu cấu hình bắt buộc bị hỏng, nên sửa cấu hình thay vì tiếp tục duyệt vô hạn.

## 3. Những nguyên nhân còn gặp trong Java hiện đại

### 3.1. Khi chạy bằng classpath và META-INF/services

Classpath là cơ chế triển khai vẫn được hỗ trợ. Provider JAR hoặc thư mục output cần chứa tệp:

~~~text
META-INF/services/<tên nhị phân đầy đủ của service>
~~~

Ví dụ, với service **demo.spi.GreetingService**, tên tệp phải là:

~~~text
META-INF/services/demo.spi.GreetingService
~~~

Nội dung tệp là danh sách **tên nhị phân đầy đủ của provider**, mỗi tên một dòng:

~~~text
demo.providers.HelloProvider
demo.providers.OtherProvider
~~~

Các lỗi thường gặp:

| Triệu chứng hoặc nguyên nhân | Vì sao xảy ra | Cách xác minh |
| --- | --- | --- |
| Sai đường dẫn hoặc sai tên file dịch vụ | ServiceLoader không tìm đúng resource | Xem nội dung JAR và đường dẫn **META-INF/services/**, đối chiếu với **Service.class.getName()** |
| Tệp có provider **demo.providers.MissingProvider** nhưng runtime không có class | ServiceLoader đọc được đăng ký nhưng không nạp được class | Kiểm tra tên package/class, artifact được triển khai và runtime classpath |
| Provider không **implements/extends** service | Kiểu đăng ký không tương thích với contract | Kiểm tra implements và bản contract thực tế trên runtime |
| Provider class không public hoặc không có **public no-arg constructor** cần thiết trong cấu hình classpath | ServiceLoader không thể tạo provider theo contract | Kiểm tra access modifier và constructor của class thực tế trong JAR |
| Constructor hoặc static initialization thất bại | Không tạo được provider; cause thường chỉ rõ lý do sâu hơn | Đọc chuỗi **getCause()** và toàn bộ stack trace, kiểm tra dependency/config bắt buộc |
| Dependency của provider thiếu hoặc sai phiên bản | Provider có thể tìm thấy nhưng không liên kết/nạp/khởi tạo được | Kiểm tra classpath thực tế, cause như **NoClassDefFoundError** hoặc lỗi liên kết tương thích |
| Nội dung service file sai cú pháp hoặc không đọc được | Tệp phải đúng định dạng, mã hóa **UTF-8** | Kiểm tra tài nguyên thực tế trong artifact, ký tự lạ, comment và quy tắc đặt tên |
| Fat/shaded JAR đóng gói sai resource | Khi hợp nhất JAR, một tệp **META-INF/services/** có thể bị mất hoặc ghi đè | Kiểm tra artifact **cuối cùng** đã triển khai; cấu hình cơ chế gộp service files của build tool |

Tệp service cho phép dòng trống, khoảng trắng ở hai đầu và phần chú thích bắt đầu bằng **#**. Các tên provider bị lặp sẽ được bỏ qua; **lặp cùng một tên không tự nó là lỗi cấu hình**. Tuy nhiên, nhiều provider khác nhau có thể cùng hiện diện và cần chính sách lựa chọn rõ ràng.

Với classpath, không dùng **public static provider()** của JPMS như một cách thay thế constructor. Provider được khai báo trong tệp **META-INF/services/** phải đáp ứng quy tắc tạo instance dành cho provider kiểu classpath.

### 3.2. Khi chạy bằng named modules (JPMS)

Với named modules, khai báo ở **module-info.java**:

~~~java
// Trong consumer module (minh họa, giả sử com.example.spi là module của API):
module com.example.app {
    requires com.example.spi;
    uses demo.spi.GreetingService;
}
~~~

~~~java
// Trong provider module:
module com.example.provider {
    requires com.example.spi;
    provides demo.spi.GreetingService
        with demo.providers.HelloProvider;
}
~~~

Đây là **hai module descriptors minh họa**, không phải hai tệp cùng tên trong một thư mục. Module chứa contract phải export package API tương ứng. Provider module phải được runtime **resolve** trong module graph/layer thích hợp.

Các vấn đề đặc trưng:

- **Thiếu uses**: module consumer gọi ServiceLoader cho service nhưng không khai báo **uses**; điều này có thể gây **ServiceConfigurationError ngay ở load(...)**.
- **Thiếu provides**: provider module có class triển khai nhưng không công bố nó qua **provides ... with ...**; khi đó consumer thường không thấy provider (không nhất thiết ném ServiceConfigurationError).
- **Provider module chưa được resolve**: JAR hiện diện trên module path chưa bảo đảm mọi provider đều tham gia module graph. Kiểm tra cách khởi động, root modules, service binding và module layer. Không giải quyết bằng cách thêm **requires** từ consumer trực tiếp đến provider khi mục tiêu là tách SPI.
- **Khai báo provides sai**: provider class không tồn tại, không đúng contract, thiếu constructor/factory phù hợp hoặc quá trình tạo instance thất bại.
- **Lẫn classpath và module path**: khai báo dùng cho named module không tương đương hoàn toàn với service resource của classpath. Xác nhận đường đi runtime thật sự của JAR.

Trong **named modules**, ServiceLoader còn hỗ trợ **provider method** dạng **public static** không tham số, tên chính xác là **provider**, có kiểu trả về tương thích service. Một provider module có thể đăng ký class factory có phương thức này mà class factory không trực tiếp implements service. Cách này **không áp dụng** cho provider đóng gói trên classpath hoặc automatic module, vốn cần provider constructor phù hợp. Đây là cơ chế JPMS vẫn được hỗ trợ, không phải lỗi thời.

## 4. Ví dụ chạy được: chẩn đoán provider hợp lệ, cấu hình lỗi và không có provider

Ví dụ dùng **JDK 17+** ở chế độ **classpath**, không cần thư viện ngoài. Nó tách ba pha: **khám phá/khởi tạo**, **xử lý cấu hình hỏng**, và **thực hiện nghiệp vụ**. Điều đó ngăn catch của pha khởi tạo che nhầm lỗi nghiệp vụ.

### 4.1. Cấu trúc dự án

~~~text
spi-diagnostics/
├── src/
│   └── demo/
│       ├── spi/GreetingService.java
│       ├── providers/HelloProvider.java
│       └── app/DiagnoseService.java
└── resources/
    └── META-INF/
        └── services/
            └── demo.spi.GreetingService
~~~

**src/demo/spi/GreetingService.java**

~~~java
package demo.spi;

public interface GreetingService {
    String greeting();
}
~~~

**src/demo/providers/HelloProvider.java**

~~~java
package demo.providers;

import demo.spi.GreetingService;

public final class HelloProvider implements GreetingService {
    public HelloProvider() {}

    @Override
    public String greeting() {
        return "Hello Java";
    }
}
~~~

**src/demo/app/DiagnoseService.java**

~~~java
package demo.app;

import demo.spi.GreetingService;
import java.util.ArrayList;
import java.util.List;
import java.util.ServiceConfigurationError;
import java.util.ServiceLoader;

public final class DiagnoseService {
    public static void main(String[] args) {
        List<GreetingService> providers = new ArrayList<>();

        try {
            ServiceLoader<GreetingService> loader =
                    ServiceLoader.load(GreetingService.class);

            for (GreetingService provider : loader) {
                providers.add(provider);
            }
        } catch (ServiceConfigurationError error) {
            System.err.println("INVALID_PROVIDER_CONFIGURATION");

            if (Boolean.getBoolean("service.diagnostics")) {
                error.printStackTrace(System.err);
            }

            System.exit(2);
            return;
        }

        if (providers.isEmpty()) {
            System.out.println("NO_PROVIDER");
            return;
        }

        for (GreetingService provider : providers) {
            System.out.println(
                    provider.getClass().getName() + ": " + provider.greeting());
        }
    }
}
~~~

Để code xử lý minh bạch:

- **try/catch** chỉ bao phần **ServiceLoader.load** và vòng duyệt lấy instance; khi cấu hình SPI hỏng, chương trình in token lỗi và thoát với mã 2.
- Chỉ khi bật **-Dservice.diagnostics=true**, chương trình mới in stack trace chi tiết. Ở sản phẩm thật, nên ghi log có ngữ cảnh và giới hạn dữ liệu nhạy cảm; đừng log token, mật khẩu hoặc nội dung cấu hình bí mật.
- Sau khi khám phá xong, việc gọi **greeting()** diễn ra **ngoài catch** của lỗi ServiceLoader. Nếu nghiệp vụ thất bại, nó được xử lý theo chính sách riêng.
- Token **NO_PROVIDER** diễn tả danh sách trống, không phải ServiceConfigurationError.

**resources/META-INF/services/demo.spi.GreetingService**

~~~text
demo.providers.HelloProvider
~~~

Tệp này cần được giữ ở **UTF-8** khi đóng gói. Với bài chạy trong thư mục output đơn giản, hãy copy nó vào cùng classpath root với các file **.class**.

### 4.2. Biên dịch và chạy thành công

Lệnh dưới đây dùng shell Bash (Linux/macOS, Git Bash hoặc môi trường tương đương) tại thư mục **spi-diagnostics**:

~~~bash
mkdir -p out/META-INF/services
javac -encoding UTF-8 -d out \
    src/demo/spi/GreetingService.java \
    src/demo/providers/HelloProvider.java \
    src/demo/app/DiagnoseService.java
cp resources/META-INF/services/demo.spi.GreetingService \
   out/META-INF/services/
java -cp out demo.app.DiagnoseService
~~~

**Stdout chính xác:**

~~~text
demo.providers.HelloProvider: Hello Java
~~~

Trên PowerShell, có thể thay **mkdir -p** và **cp** bằng **New-Item -ItemType Directory -Force** và **Copy-Item** tương ứng. Các lệnh **javac** và **java** giữ nguyên, nhưng cú pháp nối dòng của shell sẽ khác.

### 4.3. Tạo cấu hình sai có chủ đích

Thay **duy nhất tài nguyên trong thư mục out** bằng một class provider không tồn tại:

~~~bash
printf '%s\n' 'demo.providers.MissingProvider' \
    > out/META-INF/services/demo.spi.GreetingService
java -cp out demo.app.DiagnoseService
~~~

**Stderr chính xác** của code bắt lỗi ở trên:

~~~text
INVALID_PROVIDER_CONFIGURATION
~~~

Chương trình trả **exit code 2**. Provider được khai báo nhưng class không tồn tại, nên khi duyệt ServiceLoader phát sinh ServiceConfigurationError. Ở lần chạy này, Java không tự in thêm stack trace vì cờ diagnostic chưa bật.

Muốn xem lỗi gốc, chạy:

~~~bash
java -Dservice.diagnostics=true -cp out demo.app.DiagnoseService
~~~

Bạn vẫn thấy dòng **INVALID_PROVIDER_CONFIGURATION**, sau đó là stack trace có **ServiceConfigurationError** cùng chi tiết về provider. **Nội dung và số dòng stack trace tùy phiên bản JDK/đường dẫn chạy**, vì vậy không nên kiểm thử bằng cách so sánh toàn bộ stack trace thành một chuỗi cố định.

### 4.4. So sánh với trường hợp không đăng ký provider

Xóa **tệp đăng ký chỉ trong out** rồi chạy lại:

~~~bash
rm out/META-INF/services/demo.spi.GreetingService
java -cp out demo.app.DiagnoseService
~~~

**Stdout chính xác:**

~~~text
NO_PROVIDER
~~~

Điểm khác biệt: không có tài nguyên đăng ký nên loader trả danh sách trống; ứng dụng tự quyết định in **NO_PROVIDER**. Khi tài nguyên tồn tại nhưng khai báo một class sai, loader báo **ServiceConfigurationError**.

Các lệnh xóa/sửa ở mục này chỉ thao tác trên **artifact output để thử nghiệm**; tệp nguồn ở **resources/** vẫn giữ cấu hình hợp lệ.

## 5. Quy trình chẩn đoán lỗi trong dự án thực tế

Khi thấy **java.util.ServiceConfigurationError**, hãy kiểm tra theo thứ tự từ runtime đang chạy tới khai báo nguồn. Mục tiêu là tìm **lỗi đầu tiên có nguyên nhân cụ thể**, thay vì thay đổi mù quáng toàn bộ dependency.

### Bước 1: Ghi lại dấu vết đủ để đối chiếu

Lưu:

- Thời điểm và thao tác gây lỗi: lúc **ServiceLoader.load**, khi **iterator.hasNext()/next()**, khi consume **stream()** hay tại **Provider.get()**.
- **Tên đầy đủ của service** và **provider** mà thông điệp nêu ra, nếu có.
- **exception class**, **message**, **getCause()**, các nguyên nhân lồng nhau và phần stack trace thuộc ứng dụng; JDK thường chứa ngữ cảnh có ích ngay trong thông điệp.
- Phiên bản JDK, cách chạy **classpath/module path**, danh sách artifact thực sự deploy và cơ chế class loader hoặc module layer.
- Lỗi có xảy ra chỉ ở một môi trường, khi build fat JAR hay khi chạy bằng IDE không.

Ví dụ chẩn đoán, **đặt trong catch đã có ở ranh giới bootstrap**:

~~~java
System.err.println("Service load failed: " + error.getMessage());
Throwable cause = error.getCause();
while (cause != null) {
    System.err.println("Caused by " + cause.getClass().getName()
            + ": " + cause.getMessage());
    cause = cause.getCause();
}
~~~

Đoạn này là **minh họa để nhúng vào chương trình**, không phải file Java độc lập. Trong môi trường production, dùng logger, correlation ID và lọc thông tin nhạy cảm; chỉ in stack trace đầy đủ trong kênh chẩn đoán được kiểm soát. **Cause có thể null** nên không tự suy đoán nguyên nhân nếu không có dữ liệu.

### Bước 2: Đối chiếu service thực tế với resource trong artifact

Với classpath, kiểm tra chính xác:

~~~text
SERVICE = demo.spi.GreetingService
RESOURCE = META-INF/services/demo.spi.GreetingService
PROVIDER = demo.providers.HelloProvider
~~~

Các thao tác hữu ích:

~~~bash
jar --list --file app.jar
jar --list --file provider.jar
~~~

Tìm tệp **META-INF/services/demo.spi.GreetingService** và **demo/providers/HelloProvider.class** trong JAR liên quan. **jar --list** không sửa artifact; tên file trong JAR phân biệt chữ hoa/chữ thường. Nếu muốn đọc trực tiếp nội dung service file, dùng công cụ giải nén phù hợp trong thư mục kiểm tra riêng. So sánh **artifact đang chạy**, không chỉ thư mục **src/main/resources** trước build.

Với Maven/Gradle, kiểm tra bước copy resource, đóng gói JAR, đóng gói dependency và cơ chế hợp nhất **META-INF/services/** nếu tạo fat/shaded JAR. Không suy luận rằng file tồn tại trong source thì chắc chắn có trong artifact cuối.

### Bước 3: Kiểm tra class loader và phạm vi tìm kiếm

**ServiceLoader.load(Service.class)** mặc định sử dụng **thread context class loader**. Trong container, ứng dụng plugin, application server hoặc môi trường có nhiều class loader, class/resource có thể tồn tại nhưng không nhìn thấy từ loader đang dùng.

Đoạn debug sau **chỉ phục vụ trường hợp classpath/unnamed modules**:

~~~java
ClassLoader cl = Thread.currentThread().getContextClassLoader();
String resource = "META-INF/services/" + MyService.class.getName();

System.out.println("TCCL: " + cl);
if (cl != null) {
    var urls = cl.getResources(resource);
    while (urls.hasMoreElements()) {
        System.out.println("Service resource: " + urls.nextElement());
    }
}
~~~

**MyService** là interface của ứng dụng; đoạn trên phải được đặt trong phương thức có thể ném hoặc xử lý **IOException**. Việc tìm resource như vậy **không thay thế** kiểm tra khai báo **provides** của named modules. Chỉ in URL/tên loader ở môi trường chẩn đoán; không để lộ đường dẫn nhạy cảm trong log công khai.

Nếu cần chỉ định class loader rõ ràng, API hiện hành hỗ trợ:

~~~java
ServiceLoader<MyService> loader =
        ServiceLoader.load(MyService.class, chosenClassLoader);
~~~

Đây là đoạn minh họa; **chosenClassLoader** phải là class loader phù hợp thực sự của ứng dụng. Đừng đổi bừa sang **ServiceLoader.loadInstalled(...)**: API đó dùng platform class loader và có thể không nhìn thấy provider trên application classpath/module path.

### Bước 4: Kiểm tra điều kiện JPMS nếu dùng named modules

- Consumer module có **requires** module export contract và **uses** service chưa?
- Provider module có **provides Service with Provider** đúng tên chưa? **provider()**/constructor có đúng quy tắc chưa?
- Provider module đã nằm trong module graph/layer mà lời gọi ServiceLoader đang xét chưa?
- Có bản contract trùng hoặc lỗi phân tách class/module làm provider không thực sự assignable với service không?
- Nếu tạo **ModuleLayer** riêng, có dùng phạm vi load phù hợp, ví dụ **ServiceLoader.load(layer, Service.class)** khi cần khám phá provider của layer đó không?

Sự khác nhau giữa **không resolve module** và **resolve rồi nhưng provider không tạo được** quyết định hướng điều tra. Thêm module path không tự bảo đảm mọi provider được chọn để khởi chạy.

### Bước 5: Điều tra lỗi tạo instance và dependency

Nếu provider class hiện diện nhưng vẫn lỗi:

1. Kiểm tra provider có **public constructor không tham số** phù hợp với cách đăng ký, hoặc **provider()** public static trả đúng service đối với named module.
2. Đọc **root cause**: lỗi file cấu hình, thiếu dependency, quyền tài nguyên, biến môi trường bắt buộc, static initialization, lỗi phiên bản binary.
3. Thử khởi tạo provider trong kiểm thử riêng **với cùng runtime dependency** để xác định lỗi thuộc bản thân provider hay bước khám phá.
4. Đảm bảo không làm side effect nặng trong constructor nếu có thể; ưu tiên factory/lifecycle rõ ràng khi provider cần mạng, credential hoặc tài nguyên tốn kém.

**ClassNotFoundException/NoClassDefFoundError/LinkageError** và lỗi constructor có thể xuất hiện trong cause chain, nhưng không có một chuỗi message duy nhất cho mọi JDK. Ưu tiên kiểu lỗi, vị trí và dependency thực tế.

## 6. Xử lý lỗi đúng tại ranh giới ứng dụng

### Provider bắt buộc: fail fast, có thông điệp rõ

Nếu ứng dụng không thể chạy đúng khi thiếu provider, hãy kiểm tra sớm lúc startup. Có thể chuyển **ServiceConfigurationError** thành một lỗi khởi tạo có nghĩa nghiệp vụ, nhưng **giữ nguyên cause**:

~~~java
try {
    ServiceLoader<MyService> loader = ServiceLoader.load(MyService.class);
    MyService service = loader.findFirst().orElseThrow(
            () -> new IllegalStateException("Chưa cấu hình MyService provider"));
    register(service);
} catch (ServiceConfigurationError error) {
    throw new IllegalStateException(
            "Cấu hình MyService provider bị lỗi; kiểm tra module/JAR", error);
}
~~~

Đây là mã minh họa nhúng vào bootstrap; **MyService** và **register** do ứng dụng định nghĩa. Nếu contract yêu cầu đúng **một** provider, **findFirst()** chưa đủ để kiểm tra xung đột: cần liệt kê toàn bộ provider và kiểm tra số lượng/ID. Đừng coi provider đầu tiên là ưu tiên nghiệp vụ mặc định.

### Plugin tùy chọn: chỉ bỏ qua khi có chính sách rõ ràng

Nếu một plugin là tùy chọn, ứng dụng có thể:

- Phát hiện từng plugin, kiểm tra và cô lập trạng thái bật/tắt theo chính sách.
- Log tên service, provider, nguyên nhân và trạng thái vô hiệu hóa plugin.
- Tiếp tục **chỉ khi** ứng dụng không phụ thuộc vào khả năng của plugin lỗi; nếu plugin tham gia vào bảo mật, dữ liệu, thanh toán hoặc đường xử lý bắt buộc, việc bỏ qua có thể nguy hiểm.
- Chủ động chọn fallback được cấu hình và kiểm thử; không dựa vào việc lặp lại ngẫu nhiên sau khi gặp ServiceConfigurationError.

Khi một lần duyệt thất bại, khả năng tiếp tục của iterator là **best effort**, không phải bảo đảm phục hồi. **Không viết vòng while retry vô hạn** hoặc catch lỗi rồi bỏ qua mặc định để khiến hệ thống “xanh” giả.

### Giới hạn của reload và concurrency

**reload()** làm loader xóa cache đã tìm/tạo, nhưng:

- Không sửa tệp **META-INF/services/** đã đóng gói sai.
- Không bảo đảm class loader có thể nhìn thấy thư viện vừa thay trên đĩa.
- Không tự hủy hoặc đóng instance cũ mà consumer đang giữ.
- Không biến ServiceLoader thành cơ chế hot swap hay plugin deployment đầy đủ.

**ServiceLoader không thread-safe**. Nếu nhiều thread duyệt hoặc gọi **reload()** trên cùng loader, cần đồng bộ hoặc thực hiện khám phá một lần trong pha startup rồi phân phối kết quả bất biến thích hợp. Mỗi provider có thread safety/lifecycle riêng, phải xét theo contract của nó.

## 7. Kiểm thử giúp phát hiện lỗi cấu hình trước triển khai

Đừng chỉ kiểm tra lớp provider có biên dịch. Cần kiểm tra **artifact runtime thực sự**, vì lỗi SPI thường nằm ở ranh giới packaging:

| Kiểm thử | Kỳ vọng |
| --- | --- |
| Service file đúng, provider load được | Phát hiện và tạo provider thành công; contract tests pass |
| Không có provider | Nhận danh sách rỗng hoặc lỗi thiếu provider do ứng dụng quyết định; không gán nhầm cho ServiceConfigurationError |
| Service file trỏ tới tên class không tồn tại | Gặp ServiceConfigurationError tại bước khám phá/nạp khi duyệt |
| Provider có kiểu không tương thích service | Gặp lỗi cấu hình; sửa bản contract hoặc class triển khai |
| Constructor/factory ném ngoại lệ | Gặp lỗi khi tạo instance; cause giúp xác định lỗi gốc |
| Named module thiếu **uses** | Consumer module không thể dùng ServiceLoader đúng contract; phát hiện ở thử nghiệm khởi chạy module |
| Provider module thiếu **provides** hoặc không resolve | Provider không được phát hiện; xác nhận module graph/layer |
| Fat JAR hoặc bản phát hành cuối | Service resource và provider class còn nguyên sau đóng gói |
| Đa provider | Xác nhận chính sách chọn/ID trùng; không phụ thuộc ngầm vào thứ tự loader |

Trong CI, thực hiện smoke test chạy bằng **chính cách đóng gói production** (module path hoặc classpath) và chỉ dùng dependency chính thức được phép deploy. Việc unit test trực tiếp **new Provider()** là cần thiết nhưng **không đủ** chứng minh ServiceLoader sẽ tìm được provider.

### Những nhầm lẫn phổ biến

1. **“Không tìm thấy provider” = “ServiceConfigurationError”**: sai. Danh sách trống và đăng ký hỏng là hai trạng thái khác nhau.
2. **“ServiceLoader.load(...) chạy không lỗi là cấu hình đã đúng”**: sai. Nhiều lỗi chỉ xuất hiện khi iterator/stream thực sự được tiêu thụ hoặc **Provider.get()** được gọi.
3. **“Cứ reload() là nhận được plugin JAR mới”**: sai. Class loader/module layer và artifact runtime vẫn quyết định phạm vi nhìn thấy.
4. **“Có class Provider.class là đủ”**: sai. Cần đăng ký resource hoặc **provides**, đúng contract, đúng constructor/factory và dependency.
5. **“Bắt mọi Error để ứng dụng chạy tiếp”**: không an toàn. Nếu cần chẩn đoán lỗi SPI, chỉ bắt **ServiceConfigurationError** tại điểm được thiết kế, ghi rõ ngữ cảnh và quyết định fail-fast/fallback theo nghiệp vụ.
6. **“Chỉ kiểm tra file nguồn”**: thiếu. Build hoặc công cụ đóng gói có thể làm mất metadata SPI; luôn kiểm tra artifact đã triển khai.
7. **“Mọi thứ ném ra khi gọi provider đều là lỗi ServiceLoader”**: sai. Lỗi trong phương thức nghiệp vụ sau khi có instance không tự động chuyển thành ServiceConfigurationError.

## 8. Câu hỏi tự kiểm tra

1. Điều gì khác nhau khi service không có provider và khi tệp đăng ký ghi sai tên provider? Nêu vị trí phát hiện từng trường hợp.
2. Vì sao **ServiceLoader.load(...)** có thể thành công nhưng **iterator.next()** hoặc **Provider.get()** mới báo lỗi?
3. Trong classpath, cần kiểm tra chính xác những đường dẫn nào trong JAR để xác nhận SPI đã được đóng gói?
4. Khi dùng named modules, vai trò khác nhau của **requires**, **uses** và **provides ... with ...** là gì?
5. Một provider không tạo được instance do thiếu dependency. Bạn sẽ thu thập message/cause và kiểm tra artifact theo thứ tự nào?
6. Khi nào một plugin lỗi được phép bị vô hiệu hóa, và khi nào phải dừng khởi động?
7. Vì sao không nên đặt tất cả lời gọi nghiệp vụ vào cùng catch block dành cho ServiceConfigurationError?

## Ghi nhớ

**ServiceConfigurationError** là tín hiệu lỗi **cấu hình/khám phá/nạp/khởi tạo provider** của ServiceLoader. Cách chẩn đoán đáng tin cậy là phân biệt **không có provider** với **provider cấu hình hỏng**, quan sát **thời điểm lỗi được ném**, đọc **message/cause**, kiểm tra **META-INF/services hoặc module-info.java**, đối chiếu **class loader/module layer** và kiểm thử **artifact runtime cuối cùng**. Sau khi sửa cấu hình, xác minh lại bằng một smoke test khởi chạy thực tế.

**Tài liệu JDK chính thức:**

- [ServiceLoader — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html): API, provider deployment, quy tắc lỗi, cache và concurrency.
- [ServiceLoader.Provider — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.Provider.html): **type()**, **get()**, quy tắc tạo instance và lỗi.
- [ServiceConfigurationError — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceConfigurationError.html): quan hệ kế thừa **Error** và ý nghĩa ngoại lệ.