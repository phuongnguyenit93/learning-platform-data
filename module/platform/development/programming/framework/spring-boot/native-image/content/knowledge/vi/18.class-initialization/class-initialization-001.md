# Phân biệt nạp lớp, liên kết lớp và khởi tạo lớp

Trong Java, một class không lập tức đi từ file .class thành một đối tượng có thể sử dụng. JVM thực hiện ba nhóm công việc có quan hệ với nhau: **nạp lớp (loading)**, **liên kết lớp (linking)** và **khởi tạo lớp (initialization)**. Hiểu đúng ba giai đoạn này giúp giải thích vì sao static initializer chạy ở một thời điểm nhất định, vì sao `Class.forName` có thể kích hoạt mã tĩnh, và vì sao GraalVM Native Image cần quyết định lớp nào được khởi tạo khi build, lớp nào được khởi tạo khi ứng dụng chạy.

Với Spring Boot Native Image, cần phân biệt thêm Spring AOT với class initialization của GraalVM. Spring AOT phân tích application context và sinh mã hỗ trợ khởi động; GraalVM Native Image phân tích reachability, tạo executable và có thể thực thi một số class initializer ngay trong quá trình tạo image. Đây là những hoạt động khác nhau, dù đều có thể diễn ra trong giai đoạn build.

## 1. Ba giai đoạn trong vòng đời một class

Theo mô hình của Java Virtual Machine, quá trình một class hoặc interface trở nên sẵn sàng sử dụng gồm các giai đoạn chính:

1. **Loading — nạp lớp:** tìm biểu diễn nhị phân của class/interface và tạo đối tượng `Class` tương ứng trong JVM.
2. **Linking — liên kết lớp:** xác minh bytecode, chuẩn bị vùng dữ liệu static và giải quyết các tham chiếu symbolic khi cần.
3. **Initialization — khởi tạo lớp:** thực thi các initializer của class, gồm static field initializers và static initializer block.

Liên kết thường được mô tả thành ba bước nhỏ:

- **Verification:** kiểm tra class file/bytecode có hợp lệ và tuân thủ các ràng buộc của JVM hay không.
- **Preparation:** tạo và gán giá trị mặc định cho các static fields; việc gán giá trị ban đầu theo static field initializer diễn ra ở giai đoạn initialization.
- **Resolution:** chuyển các symbolic references trong constant pool thành tham chiếu cụ thể mà JVM sử dụng. JVM có thể thực hiện resolution sớm hoặc trì hoãn đến lúc tham chiếu được sử dụng, tùy quy định và cách triển khai.

Sơ đồ khái quát:

~~~mermaid
flowchart TD
    A["Class được yêu cầu sử dụng"] --> B["Loading - nạp class"]
    B --> C["Linking - liên kết"]
    C --> D["Verification"]
    D --> E["Preparation"]
    E --> F["Resolution"]
    F --> G["Initialization"]
    G --> H["Class sẵn sàng cho active use"]
~~~

Không nên hiểu sơ đồ này là mọi symbolic reference đều phải được resolve hết trước khi class khởi tạo. JVM cho phép resolution diễn ra theo cách eager hoặc lazy; điều quan trọng là một lỗi liên kết phải được phát hiện khi chương trình sử dụng đường tham chiếu tương ứng theo quy định JVM.

## 2. Loading: JVM tìm và nạp class như thế nào?

Loading là quá trình JVM tìm bytecode hoặc một biểu diễn class phù hợp, rồi tạo đối tượng `Class` đại diện cho kiểu đó. Nguồn có thể là:

- Thư mục class output của ứng dụng.
- JAR trên classpath/module path.
- Runtime image và thư viện của JDK.
- Một nguồn tùy chỉnh thông qua custom class loader.
- Byte array do class loader định nghĩa thông qua `defineClass`.

Trong môi trường Java hiện đại, các class loader phổ biến gồm:

| Class loader | Vai trò khái quát |
| --- | --- |
| Bootstrap class loader | Nạp các class nền tảng cốt lõi của Java |
| Platform class loader | Nạp các platform classes được JDK cung cấp |
| Application/System class loader | Nạp class ứng dụng và thư viện trên classpath/module path |
| Custom class loader | Nạp class theo quy tắc do ứng dụng hoặc framework định nghĩa |

Cơ chế parent delegation thường được sử dụng: class loader hỏi parent trước, rồi mới tự tìm class nếu parent không tìm thấy. Đây là quy tắc phổ biến, nhưng custom class loader có thể triển khai chiến lược khác.

### Nạp lớp không đồng nghĩa với khởi tạo lớp

Có thể yêu cầu JVM nạp một class mà chưa chạy static initializer:

~~~java
ClassLoader loader = Thread.currentThread().getContextClassLoader();

Class<?> type = Class.forName(
        "com.example.nativeimage.ReportFormatter",
        false,
        loader
);
~~~

Tham số `false` yêu cầu không khởi tạo class trong lời gọi `Class.forName` này. Class có thể được nạp và liên kết theo nhu cầu, nhưng static initializer chưa bị kích hoạt chỉ bởi lời gọi đó.

Một cách khác thường gặp:

~~~java
Class<?> type = ReportFormatter.class;
~~~

Class literal lấy đối tượng `Class` của kiểu. Nó có thể khiến class được nạp, nhưng bản thân class literal **không phải active use làm khởi tạo class** theo quy tắc Java.

Ngược lại, `Class.forName("com.example.nativeimage.ReportFormatter")` dùng overload một tham số có hành vi tương đương yêu cầu khởi tạo class (`initialize = true`) nếu class chưa được khởi tạo.

## 3. Linking: verification, preparation và resolution

### Verification — xác minh bytecode

JVM kiểm tra class file và các quan hệ kiểu để bảo đảm bytecode không vi phạm những quy tắc cần thiết khi thực thi. Ví dụ, bytecode phải có kiểu toán hạng phù hợp, không được sử dụng stack sai cấu trúc và các truy cập kiểu phải hợp lệ.

Nếu class không vượt qua verification, JVM có thể báo `VerifyError`. Đây là lỗi liên kết, không phải lỗi logic bên trong static initializer.

### Preparation — chuẩn bị static fields

Trong preparation, JVM cấp vùng dữ liệu cần thiết cho static fields và gán **giá trị mặc định theo kiểu**:

~~~java
public class InitializationExample {

    static int count = 42;
    static boolean enabled = true;
    static String label = "ready";
}
~~~

Ở bước preparation, các field static trước tiên có giá trị mặc định:

- `count` là `0`.
- `enabled` là `false`.
- `label` là `null`.

Các biểu thức `42`, `true` và `"ready"` được xử lý trong giai đoạn initialization, ngoại trừ các biến hằng compile-time có quy tắc đặc biệt được trình biên dịch có thể inline vào nơi sử dụng.

Preparation không chạy constructor của object và cũng không chạy static initializer block.

### Resolution — giải quyết symbolic references

Bytecode thường tham chiếu class, method và field bằng symbolic reference. Resolution biến những tham chiếu đó thành cách truy cập cụ thể mà runtime sử dụng.

Ví dụ, khi một class gọi `repository.findById(...)`, bytecode chứa tham chiếu tới kiểu và method. JVM cần xác định method tương ứng và kiểm tra các quy tắc truy cập/kiểu liên quan.

Nếu không tìm thấy class hoặc method được yêu cầu, lỗi có thể xuất hiện dưới dạng `NoClassDefFoundError`, `NoSuchMethodError`, `NoSuchFieldError` hoặc lỗi linkage khác. Do resolution có thể trì hoãn, một ứng dụng đôi khi chỉ gặp lỗi khi đi vào nhánh code hiếm dùng.

## 4. Initialization: khi nào static initializer chạy?

Initialization là giai đoạn JVM thực thi các khởi tạo tĩnh của class. Các thành phần chính gồm:

- Static field initializer không phải compile-time constant.
- Các static initializer block.
- Những thao tác được thực hiện theo thứ tự xuất hiện trong phần khai báo class.

Ví dụ:

~~~java
public class StartupSettings {

    static String mode = readMode();

    static {
        System.out.println("Static block: mode=" + mode);
    }

    static int retryCount = 3;

    private static String readMode() {
        System.out.println("Reading mode");
        return "safe";
    }
}
~~~

Khi class được khởi tạo, các static field initializer và static block chạy theo thứ tự xuất hiện trong source. Với ví dụ trên, output theo thứ tự là:

~~~text
Reading mode
Static block: mode=safe
~~~

Field `retryCount` nhận giá trị `3` trong cùng quá trình initialization sau khi static block phía trước đã chạy.

### Active use — các hành động kích hoạt initialization

Theo quy tắc Java, class thường được khởi tạo ngay trước lần đầu tiên xảy ra một trong các tình huống active use sau:

1. Tạo instance bằng `new` của class.
2. Gọi một static method được khai báo bởi class.
3. Gán vào hoặc đọc một static field được khai báo bởi class, nếu field đó không phải compile-time constant.
4. Một số thao tác reflection yêu cầu khởi tạo class, ví dụ `Class.forName(name)` với overload mặc định `initialize = true`.

Ví dụ:

~~~java
public class LazyHolder {

    static {
        System.out.println("LazyHolder initialized");
    }

    static void run() {
        System.out.println("run");
    }

    static final int CONSTANT = 10;
    static int counter = 0;
}
~~~

Các hành động sau có ý nghĩa khác nhau:

~~~java
Class<?> type = LazyHolder.class;
// Class literal không tự kích hoạt initialization.

int value = LazyHolder.CONSTANT;
// Compile-time constant có thể được inline; không cần initialize LazyHolder.

int current = LazyHolder.counter;
// Đọc static field không phải compile-time constant: kích hoạt initialization.

LazyHolder.run();
// Gọi static method: class đã được initialize trước khi method chạy.
~~~

### Compile-time constant là ngoại lệ quan trọng

Một constant variable là biến `final` kiểu primitive hoặc `String`, được khởi tạo bằng constant expression theo định nghĩa của Java. Ví dụ:

~~~java
public class BuildConstants {
    public static final int DEFAULT_PORT = 8080;
    public static final String SERVICE = "billing";
}
~~~

Trình biên dịch có thể inline giá trị của các biến này vào bytecode nơi sử dụng. Chỉ đọc `BuildConstants.DEFAULT_PORT` hoặc `BuildConstants.SERVICE` không nhất thiết kích hoạt initialization của `BuildConstants`.

Ngược lại, field sau không phải compile-time constant:

~~~java
public static final String MODE = System.getenv("APP_MODE");
~~~

Giá trị phụ thuộc lời gọi method ở runtime, vì vậy không phải constant expression. Việc đọc field này có thể kích hoạt initialization của class.

## 5. Thứ tự khởi tạo class, superclass và interface

Khi một class được khởi tạo lần đầu, JVM phải xử lý các quan hệ kế thừa trước khi chạy phần initializer của class đó.

Ví dụ:

~~~java
class Parent {
    static {
        System.out.println("Parent initialized");
    }
}

class Child extends Parent {
    static {
        System.out.println("Child initialized");
    }
}
~~~

Lần đầu sử dụng `Child` theo cách kích hoạt initialization sẽ khởi tạo `Parent` trước rồi mới đến `Child`:

~~~text
Parent initialized
Child initialized
~~~

Quy tắc này tránh việc class con chạy static initialization trước class cha mà nó phụ thuộc.

### Interface có quy tắc khác class

Khởi tạo một interface **không tự động khởi tạo các superinterfaces của nó** chỉ vì quan hệ kế thừa interface. Đây là điểm khác với việc khởi tạo class và superclass.

Khi khởi tạo một class, JVM còn phải khởi tạo những superinterfaces của class đó có khai báo default methods, theo thứ tự phù hợp với quan hệ interface. Mục đích là bảo đảm các default methods có thể được sử dụng với trạng thái static đã khởi tạo.

Ví dụ:

~~~java
interface HasDefaultAction {
    int VERSION = initializeVersion();

    static int initializeVersion() {
        System.out.println("HasDefaultAction initialized");
        return 1;
    }

    default void execute() {
    }
}

class ActionService implements HasDefaultAction {
    static {
        System.out.println("ActionService initialized");
    }
}
~~~

Khi `ActionService` được khởi tạo, interface `HasDefaultAction` có default method nên được khởi tạo trước class. Nếu interface không khai báo default method, việc khởi tạo class triển khai không nhất thiết kích hoạt initialization của interface đó.

## 6. Class initialization là thread-safe và chỉ thực hiện một lần

JVM đồng bộ hóa quá trình initialization của mỗi class/interface. Nếu nhiều thread cùng lần đầu sử dụng một class:

- Một thread thực hiện initializer.
- Các thread khác cần class đó phải chờ quá trình initialization hoàn tất.
- Khi initialization thành công, các thread tiếp theo sử dụng trạng thái đã khởi tạo.
- JVM không chạy lại static initializer mỗi lần gọi static method hoặc tạo instance.

Cơ chế này giúp bảo đảm static initialization không bị chạy đồng thời nhiều lần trong cùng một class loader.

Tuy nhiên, static initializer không nên thực hiện công việc nặng hoặc chờ đợi không kiểm soát. Nếu initializer gọi code tạo vòng chờ giữa các thread, truy cập hệ thống ngoài hoặc làm startup kéo dài, toàn bộ thread cần class đó có thể bị ảnh hưởng.

### Initialization thất bại

Nếu static initializer ném exception:

- Nếu exception không phải `Error`, JVM thường bọc nó trong `ExceptionInInitializerError`.
- Class được đánh dấu là initialization thất bại (erroneous) trong class loader đó.
- Những lần active use sau có thể gặp `NoClassDefFoundError` thay vì thử chạy lại initializer.

Ví dụ:

~~~java
public class BrokenSettings {

    static {
        if (System.getenv("REQUIRED_SECRET") == null) {
            throw new IllegalStateException("Missing REQUIRED_SECRET");
        }
    }
}
~~~

Nếu biến môi trường thiếu khi class được khởi tạo, class đó không thể được xem như chưa từng chạy initializer để thử lại sau khi biến môi trường được thêm vào. Cách thiết kế tốt hơn là đọc cấu hình theo lifecycle ứng dụng, validate ở thời điểm phù hợp và báo lỗi cấu hình rõ ràng.

## 7. Phân biệt class initialization với Spring bean initialization

Spring Boot có một vòng đời bean riêng. Không nên đồng nhất nó với initialization của class theo JVM.

| Khái niệm | Phạm vi | Ví dụ |
| --- | --- | --- |
| Class loading | JVM | Nạp `PaymentService.class` |
| Class initialization | JVM | Chạy `static { ... }` của `PaymentService` |
| Object construction | Java object | Gọi `new PaymentService(...)` |
| Bean creation | Spring container | Tạo object, inject dependency, áp dụng BeanPostProcessor |
| Bean initialization callbacks | Spring lifecycle | `@PostConstruct`, `InitializingBean`, init method |
| Spring AOT | Build-time processing | Phân tích context và sinh mã đăng ký/khởi tạo bean |
| Native Image class initialization | GraalVM build/runtime policy | Chọn static initializer nào chạy khi tạo image và initializer nào chạy khi executable hoạt động |

Ví dụ:

~~~java
@Service
public class PaymentService {

    static {
        System.out.println("Class initialized");
    }

    public PaymentService() {
        System.out.println("Object constructed");
    }

    @PostConstruct
    void initializeBean() {
        System.out.println("Spring bean initialized");
    }
}
~~~

Ba dòng log đại diện cho ba sự kiện khác nhau:

1. JVM khởi tạo class `PaymentService` và chạy static block.
2. Spring tạo một instance bằng constructor.
3. Spring thực hiện bean initialization callback sau dependency injection theo lifecycle.

Một class có thể được khởi tạo trước khi Spring tạo bean instance của nó. Một class cũng có thể được dùng để tạo object không do Spring quản lý; khi đó class initialization vẫn xảy ra nhưng Spring bean lifecycle không xảy ra.

## 8. Spring AOT và GraalVM xử lý class initialization ở những thời điểm nào?

Trong quy trình Spring Boot Native Image, có ít nhất hai quá trình build-time cần phân biệt:

### Spring AOT processing

Spring AOT phân tích application context để nhận biết bean definitions, dependency graph, cấu hình và các đóng góp từ framework. Nó sinh mã khởi tạo context và runtime hints phục vụ native compilation.

Trong quá trình phân tích, Spring có thể cần tạo hoặc gọi một số thành phần hạ tầng để xử lý cấu hình. Vì vậy, static initializer hoặc code của một số bean/processor có thể được thực thi trong tiến trình AOT chạy trên JVM. Việc này **không đồng nghĩa** trạng thái static của mọi class được đóng gói vào native executable.

### GraalVM Native Image build

Native Image phân tích reachability và áp dụng chính sách class initialization. Tùy class và cấu hình, GraalVM có thể:

- Khởi tạo class trong quá trình tạo image (build-time initialization).
- Trì hoãn class initialization đến khi native executable chạy (run-time initialization).

Khi class được khởi tạo ở build time, trạng thái static tương ứng có thể được lưu trong image heap và trở thành trạng thái ban đầu của executable. Khi class được cấu hình khởi tạo ở runtime, initializer sẽ chạy trong tiến trình native theo quy tắc initialization của runtime.

~~~mermaid
flowchart TD
    S["Source + dependencies"] --> A["Spring AOT trên JVM"]
    A --> G["Generated code + runtime hints"]
    G --> N["GraalVM Native Image analysis"]
    N --> P{"Class initialization policy"}
    P -->|"Build time"| B["Chạy initializer khi tạo image"]
    B --> H["Lưu trạng thái static vào image heap"]
    P -->|"Run time"| R["Để initializer cho native process"]
    H --> X["Native executable"]
    R --> X
    X --> U["Ứng dụng sử dụng class"]
~~~

Hai pha build có thể chạy static initializer trong hai tiến trình và ngữ cảnh khác nhau. Đừng giả định một side effect xảy ra trong Spring AOT JVM sẽ tự động trở thành static state trong native image. Hãy xác định chính xác log và pha mà initializer được chạy.

## 9. Build-time initialization và run-time initialization trong Native Image

### Build-time initialization

Khi GraalVM khởi tạo class ở build time, các static field và trạng thái liên quan có thể được đưa vào image heap. Điều này có thể giảm công việc phải làm khi ứng dụng khởi động.

Ví dụ, một class chỉ chứa bảng dữ liệu bất biến, được tạo xác định từ hằng số trong source, có thể phù hợp để khởi tạo sớm:

~~~java
public final class CurrencyTable {

    static final Map<String, Integer> FRACTIONS = Map.of(
            "USD", 2,
            "JPY", 0,
            "VND", 0
    );

    private CurrencyTable() {
    }
}
~~~

Nếu initializer chỉ tạo dữ liệu xác định và không phụ thuộc môi trường runtime, build-time initialization có thể là lựa chọn hợp lý. Tuy nhiên, cần kiểm tra chi phí image heap và tương thích với phiên bản GraalVM.

### Run-time initialization

Một class nên được khởi tạo lúc runtime nếu static initializer phụ thuộc vào trạng thái của môi trường thực thi:

~~~java
public final class RuntimeSettings {

    static final String APP_MODE =
            System.getenv().getOrDefault("APP_MODE", "default");

    static final long STARTED_AT = System.currentTimeMillis();

    private RuntimeSettings() {
    }
}
~~~

Nếu class này bị khởi tạo ở build time, giá trị môi trường và timestamp có thể bị ghi vào image heap từ máy build. Native executable khi chạy trong container khác sẽ không tự tính lại các giá trị đó.

Những dấu hiệu thường cần runtime initialization:

- Đọc environment variables hoặc system properties.
- Lấy current time hoặc tạo giá trị ngẫu nhiên.
- Tạo thread, executor hoặc scheduler.
- Mở file/socket hoặc khởi tạo native resource.
- Phát hiện hostname, network interface hoặc cấu hình máy.
- Truy cập secret, credentials hoặc đường dẫn chỉ tồn tại trong container runtime.

Tốt hơn nữa, nhiều giá trị không cần static field. Có thể đọc chúng qua constructor injection, `@ConfigurationProperties` hoặc một service có lifecycle rõ ràng. Khi đó, ứng dụng không phải phụ thuộc vào thời điểm class initialization để lấy cấu hình runtime.

## 10. Cấu hình GraalVM class initialization

GraalVM Native Image cung cấp các option để kiểm soát thời điểm khởi tạo class. Hai option thường gặp:

- `--initialize-at-build-time=<class-or-package>`: yêu cầu khởi tạo các class được chỉ định khi build image.
- `--initialize-at-run-time=<class-or-package>`: trì hoãn initialization của các class được chỉ định tới runtime.

Ví dụ yêu cầu `RuntimeSettings` được khởi tạo khi native executable chạy:

~~~text
--initialize-at-run-time=com.example.nativeimage.RuntimeSettings
~~~

Ví dụ này chỉ minh họa tên class. Hãy thay bằng class thực tế và kiểm tra option của phiên bản Native Image đang sử dụng.

### Maven Native Build Tools

Có thể thêm argument vào cấu hình `native-maven-plugin`:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--initialize-at-run-time=com.example.nativeimage.RuntimeSettings</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

Nếu project đã có cấu hình plugin trong parent hoặc profile native, hãy thêm argument vào cấu hình hiện tại để tránh khai báo plugin trùng lặp. Kiểm tra log để xác nhận argument được truyền tới Native Image.

### Gradle Native Build Tools

Ví dụ Groovy DSL:

~~~groovy
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add(
                "--initialize-at-run-time=com.example.nativeimage.RuntimeSettings"
            )
        }
    }
}
~~~

API DSL và tên binary có thể thay đổi theo phiên bản plugin. Với Kotlin DSL, dùng property/API typed tương ứng của phiên bản đang cài.

### Có nên ép toàn bộ package khởi tạo ở build time?

Không nên dùng `--initialize-at-build-time` cho toàn bộ ứng dụng chỉ để giảm startup. Điều đó có thể khiến static initializer của thư viện chạy trên máy build và đóng băng trạng thái không phù hợp vào image. Bắt đầu từ policy mặc định của toolchain, đọc warning/trace, rồi chỉ điều chỉnh class có lý do rõ ràng.

Một class có thể phụ thuộc vào superclass hoặc các thành phần khác; việc thay đổi initialization policy cần xem xét cả quan hệ phụ thuộc. Native Image có thể từ chối một cấu hình không nhất quán hoặc yêu cầu điều chỉnh thêm class liên quan.

## 11. Ví dụ lỗi do static state bị đóng băng ở build time

Giả sử ứng dụng cần chọn endpoint theo môi trường:

~~~java
public final class ApiEndpoint {

    static final String BASE_URL =
            System.getenv().getOrDefault(
                    "PARTNER_API_URL",
                    "https://sandbox.example.test"
            );

    private ApiEndpoint() {
    }
}
~~~

Nếu `ApiEndpoint` được khởi tạo trong quá trình native-image build, `BASE_URL` có thể giữ giá trị từ môi trường build. Khi chạy container production với `PARTNER_API_URL=https://api.partner.example`, ứng dụng vẫn có thể sử dụng URL sandbox đã được lưu trong image heap.

Cách sửa tốt hơn là đưa cấu hình vào runtime bean:

~~~java
@ConfigurationProperties(prefix = "partner.api")
public record PartnerApiProperties(URI baseUrl) {
}
~~~

~~~java
@Service
public class PartnerClient {

    private final PartnerApiProperties properties;

    public PartnerClient(PartnerApiProperties properties) {
        this.properties = properties;
    }

    public URI baseUrl() {
        return properties.baseUrl();
    }
}
~~~

Với cấu hình runtime:

~~~yaml
partner:
  api:
    base-url: https://api.partner.example
~~~

Spring Binder nhận giá trị khi ứng dụng chạy và inject vào bean. Nếu môi trường deployment thay đổi, có thể cung cấp property khác mà không cần đóng băng endpoint vào static initializer.

Nếu không thể thay đổi thiết kế thư viện và class bắt buộc phải đọc trạng thái runtime trong static initializer, hãy cân nhắc `--initialize-at-run-time` cho class đó. Nhưng trước tiên nên đánh giá khả năng chuyển logic ra khỏi static initializer vì cách này thường dễ kiểm thử và vận hành hơn.

## 12. Chẩn đoán class initialization trong Native Image

Các triệu chứng sau thường giúp khoanh vùng vấn đề:

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Giá trị environment trong native sai so với container | Static field bị khởi tạo ở build time | Kiểm tra initializer, trace và runtime initialization policy |
| Native build báo class initialization không hợp lệ | Initializer thực hiện thao tác không hỗ trợ trong hosted/build-time context | Xác định class gây lỗi và xem có nên trì hoãn initialization |
| Startup native chậm bất thường | Nhiều class thực hiện công việc nặng ở runtime initialization | Đo startup, xem trace và đánh giá class có thể khởi tạo an toàn ở build time không |
| JVM chạy nhưng native báo lỗi khi dùng một class | Khác biệt initialization policy hoặc dependency của class | Đọc exception và class initialization trace |
| Lỗi `ExceptionInInitializerError` | Static initializer ném exception lần đầu | Tìm exception gốc trong static block/field initializer |
| Những lần dùng sau báo `NoClassDefFoundError` | Class đã bị đánh dấu erroneous sau lần initialization thất bại | Khởi động tiến trình mới sau khi sửa nguyên nhân |
| Timestamp/random value giống nhau giữa nhiều lần chạy binary | Giá trị đã được tính ở build time và lưu trong image heap | Kiểm tra static initializer và chuyển sang runtime |
| Lỗi do thread hoặc socket được tạo trong initializer | Build-time initialization cố tạo resource gắn với process/OS | Trì hoãn initialization hoặc chuyển tạo resource vào lifecycle runtime |

### Theo dõi class initialization

GraalVM Native Image có option trace class initialization trong các phiên bản hỗ trợ, thường dùng dạng:

~~~text
--trace-class-initialization=com.example.nativeimage.RuntimeSettings
~~~

Option này giúp quan sát class được khởi tạo khi nào và từ đâu. Tên option/định dạng chi tiết có thể thay đổi theo GraalVM release; xác minh bằng `native-image --help` hoặc tài liệu đúng version.

Khi điều tra:

1. Xác định class có static field initializer hoặc static block đáng chú ý.
2. Tìm log/trace cho biết class được khởi tạo ở build time hay runtime.
3. Kiểm tra giá trị static có phụ thuộc environment, thời gian, randomness hoặc resource của máy build không.
4. Nếu class cần môi trường runtime, chuyển logic ra khỏi static initializer hoặc đặt runtime initialization policy phù hợp.
5. Build lại executable và kiểm tra trong container có cấu hình khác máy build.
6. Chạy test nhiều lần và kiểm tra trạng thái static không bị giữ ngoài ý muốn.

Không sửa lỗi class initialization bằng cách thêm reflection hints một cách máy móc. Reflection metadata và class initialization là hai cơ chế khác nhau.

## 13. Bài thực hành: quan sát ba giai đoạn và thời điểm static initializer chạy

Tạo project Spring Boot nhỏ có một class `InitializationProbe`:

~~~java
package com.example.nativeimage;

public final class InitializationProbe {

    static final String BUILD_MARKER = "probe-v1";

    static final String APP_MODE =
            System.getenv().getOrDefault("APP_MODE", "default");

    static {
        System.out.println("InitializationProbe initialized: " + APP_MODE);
    }

    private InitializationProbe() {
    }

    public static String appMode() {
        return APP_MODE;
    }
}
~~~

Tạo một service sử dụng class này:

~~~java
@Service
public class ProbeService {

    public String appMode() {
        return InitializationProbe.appMode();
    }
}
~~~

Thực hiện các bước:

1. Dùng `InitializationProbe.class` để lấy class literal và quan sát rằng static initializer không nhất thiết chạy ở thao tác này.
2. Dùng `Class.forName("com.example.nativeimage.InitializationProbe", false, loader)` rồi xác minh class chưa bị active use để initialize.
3. Gọi `InitializationProbe.appMode()` và quan sát static initializer chạy trước lần gọi đầu tiên.
4. Chạy ứng dụng JVM với `APP_MODE=dev`, sau đó đổi thành `APP_MODE=prod` ở tiến trình mới và so sánh.
5. Build native executable; nếu cần, cấu hình class này runtime initialization bằng `--initialize-at-run-time`.
6. Chạy binary với `APP_MODE=prod`, xác minh giá trị được đọc từ runtime container.
7. Dùng trace class initialization của GraalVM để xem class được khởi tạo ở pha nào.
8. So sánh với một class chỉ tạo dữ liệu bất biến từ hằng số và cân nhắc liệu build-time initialization có phù hợp không.

### Câu hỏi tự kiểm tra

1. Loading, linking và initialization khác nhau ở điểm nào?
2. Verification, preparation và resolution là những phần nào của linking?
3. Vì sao preparation gán giá trị mặc định cho static fields trước khi initializer chạy?
4. Vì sao đọc compile-time constant không nhất thiết khởi tạo class?
5. Tại sao khởi tạo class con có thể kích hoạt khởi tạo superclass và một số superinterfaces?
6. Vì sao class initialization được JVM đồng bộ hóa?
7. `ExceptionInInitializerError` và `NoClassDefFoundError` có thể liên quan nhau như thế nào?
8. Spring AOT processing khác GraalVM build-time class initialization ở điểm nào?
9. Khi nào nên dùng `--initialize-at-run-time`?
10. Vì sao đọc environment variables trong static initializer có thể tạo lỗi khi build native?

**Tiêu chí đạt:** giải thích được loading, linking và initialization theo vòng đời JVM; nhận diện các active use và compile-time constant; mô tả đúng thứ tự superclass/interface, tính thread-safe và lỗi initialization; phân biệt class initialization với Spring bean lifecycle/AOT; đồng thời chọn và kiểm chứng được build-time hoặc run-time initialization phù hợp khi tạo GraalVM Native Image.
