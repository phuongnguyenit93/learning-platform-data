# Lỗi khởi tạo lớp và đối tượng không hợp lệ trong image heap

## 1. Hiểu đúng lỗi trước khi thay đổi cấu hình

Trong module **SPRING_BOOT_NATIVE_IMAGE**, Spring Boot dùng **Spring AOT** để chuẩn bị mã và metadata, sau đó GraalVM **Native Image** phân tích tĩnh và biên dịch ứng dụng thành executable. Trong quá trình build, Native Image có thể chạy một phần mã Java, bao gồm static initializer của các lớp được khởi tạo ở build time. Những object được tạo trong giai đoạn này và còn reachable từ ứng dụng có thể được lưu vào **image heap** của executable.

Một lỗi thường gặp có dạng:

~~~text
UnsupportedFeatureException:
An object of type 'com.example.RuntimeCache' was found in the image heap.
This type, however, is marked for initialization at image run time.
This is not allowed for correctness reasons:
All objects that are stored in the image heap must be initialized at build time.
~~~

Tên exception và cách diễn đạt có thể khác theo GraalVM release. Ý nghĩa cốt lõi là: build đã tạo một object thuộc kiểu được yêu cầu khởi tạo ở runtime, nhưng object đó lại đang nằm trong trạng thái ban đầu được đóng gói vào image. Điều này vi phạm quy tắc khởi tạo lớp của Java.

Không nên thêm tùy chọn **--initialize-at-build-time** ngay khi thấy thông báo. Trước tiên phải xác định object đó có thực sự là dữ liệu bất biến, độc lập với môi trường và an toàn để snapshot vào binary hay không. Nếu object giữ trạng thái runtime, cần tìm nơi đã tạo nó trong lúc build và chuyển quá trình tạo về runtime.

Sau bài học, người học có thể:

1. Giải thích build time, runtime, class initialization và image heap.
2. Đọc lỗi UnsupportedFeatureException liên quan đến object trong image heap.
3. Truy ngược object từ static field hoặc object graph về initializer đã tạo nó.
4. Dùng **-H:+PrintClassInitialization** và **--trace-object-instantiation** để thu thập bằng chứng.
5. Chọn **--initialize-at-build-time** hoặc **--initialize-at-run-time** theo bản chất dữ liệu.
6. Refactor static state thành dependency được tạo ở runtime trong Spring Boot.
7. Kiểm tra ảnh hưởng của superclass, subclass và thứ tự khởi tạo.
8. Phân biệt Spring AOT bean-definition generation với việc tạo bean instance.
9. Kiểm tra bí mật, random seed, đường dẫn và cấu hình có bị snapshot vào executable.
10. Viết regression tests để xác nhận native executable hoạt động đúng trên môi trường triển khai.

> **Quy tắc quan trọng:** mọi object nằm trong image heap phải thuộc kiểu đã được khởi tạo tại build time. Nếu một kiểu phải khởi tạo ở runtime, instance của kiểu đó không được xuất hiện trong image heap.

## 2. Build time, runtime và image heap

### 2.1. Native Image có thể chạy mã Java trong lúc build

Khi chạy native-image, builder không chỉ đọc bytecode rồi chuyển từng method thành machine code. Nó còn thực hiện static analysis và có thể chạy một phần mã ứng dụng để tạo trạng thái ban đầu cho executable.

Cần phân biệt:

- **Class loading:** builder nạp định nghĩa lớp. Việc load lớp chưa nhất thiết chạy static initializer.
- **Class initialization:** thực thi static field initializers và khối static theo quy tắc Java.
- **Build-time initialization:** class initializer chạy trong JVM đang thực hiện native-image build.
- **Runtime initialization:** class initializer chỉ chạy khi native executable khởi động và lớp được sử dụng lần đầu.
- **Image heap:** vùng chứa object được tạo trong quá trình build và được giữ lại vì reachable từ ứng dụng, cùng một số class objects và object constants.

Nếu lớp được khởi tạo ở build time, các static fields đã gán giá trị sẽ được snapshot vào executable. Lúc chạy native, lớp đó đã ở trạng thái initialized; static initializer không chạy lại.

### 2.2. Object có thể đi vào image heap từ đâu?

Nguồn phổ biến nhất là static fields của lớp được khởi tạo ở build time:

~~~java
public final class CatalogDefaults {
    static final Map<String, String> LABELS = createLabels();

    private static Map<String, String> createLabels() {
        Map<String, String> labels = new HashMap<>();
        labels.put("SKU-1", "Standard");
        labels.put("SKU-2", "Express");
        return Map.copyOf(labels);
    }
}
~~~

Nếu CatalogDefaults được khởi tạo trong lúc build, map và các object mà map tham chiếu có thể trở thành một phần của image heap.

Object cũng có thể được giữ lại gián tiếp. Ví dụ một static singleton tham chiếu cache, cache tham chiếu client, client tham chiếu connection configuration hoặc resource. Khi một root còn reachable, các object trong graph mà builder giữ lại cũng có thể được lưu cùng.

~~~mermaid
flowchart TD
    A[Build-time initialized class] --> B[Static field]
    B --> C[Singleton object]
    C --> D[Cache]
    D --> E[Client]
    E --> F[Runtime resource or state]
    F --> G[Object graph reaches image heap]
~~~

Vì vậy, chỉ đọc field của lớp được nêu trong lỗi đôi khi chưa đủ. Hãy lần theo cả object graph và xác định root nào khiến instance còn reachable.

### 2.3. static final không đồng nghĩa an toàn

Từ khóa final chỉ ngăn gán lại reference sau khi đã khởi tạo. Nó không biến object mutable thành immutable và không bảo đảm object độc lập với môi trường.

Ví dụ:

~~~java
static final Map<String, String> CACHE = new HashMap<>();
static final Path HOME = Path.of(System.getProperty("user.home"));
static final Instant STARTED_AT = Instant.now();
static final SecureRandom RANDOM = new SecureRandom();
~~~

Các field trên có đặc tính khác nhau:

- CACHE là map mutable.
- HOME phụ thuộc system property của máy build.
- STARTED_AT đóng băng thời điểm build.
- RANDOM có trạng thái entropy/runtime và không nên bị snapshot tùy tiện.

Một static final formatter hoặc bảng tra cứu bất biến, được tạo từ hằng số độc lập môi trường, có thể phù hợp với build-time initialization. Tuy nhiên vẫn phải kiểm tra object graph và hành vi của thư viện cụ thể.

## 3. Vì sao một object runtime lại xuất hiện trong image heap?

Lỗi này thường xuất hiện khi builder phát hiện một instance của lớp được đánh dấu runtime initialization đang bị giữ lại trong image heap.

Các nguyên nhân thường gặp:

| Nguồn tạo object | Ví dụ | Rủi ro |
| --- | --- | --- |
| Static initializer | static final Client CLIENT = new Client() | Client được tạo lúc build thay vì lúc ứng dụng chạy. |
| Static singleton holder | Holder.INSTANCE giữ cache hoặc registry | Object được giữ qua static root. |
| Static factory call | Static field gọi createDefault() | Factory tạo object runtime trong lúc build. |
| Transitive initializer | Lớp A gọi lớp B, B tạo object C | Root không nằm trong lớp được nhắc đến ở lỗi. |
| Thư viện bên thứ ba | Logging, crypto, driver, serializer hoặc native integration | Dependency tạo trạng thái không phù hợp khi class được khởi tạo. |
| Build-time feature/plugin | Native Image Feature hoặc AOT processor tạo object | Object được tạo trong hosted JVM của builder. |

### 3.1. Ví dụ static state phụ thuộc runtime

~~~java
public final class RuntimeEnvironment {
    static final String REGION = System.getenv("APP_REGION");
    static final Path DATA_DIR =
        Path.of(System.getProperty("app.data-dir", "./data"));
    static final Instant CREATED_AT = Instant.now();

    private RuntimeEnvironment() {
    }
}
~~~

Nếu lớp này được khởi tạo trong lúc build, các giá trị có thể phản ánh môi trường build. Khi chạy cùng executable ở một container khác, thay đổi APP_REGION, app.data-dir hoặc thời điểm chạy không làm các static field được tính lại.

Vấn đề có thể không gây lỗi image heap trực tiếp, nhưng là lỗi ngữ nghĩa và cấu hình. Nếu static initializer còn tạo object thuộc lớp runtime-initialized, builder có thể dừng với lỗi image heap.

### 3.2. Ví dụ resource không được snapshot

Các object gắn với tài nguyên của process hiện tại thường phải được tạo ở runtime:

- File descriptor hoặc stream đang mở.
- Socket hoặc network connection.
- Thread đang chạy hoặc executor đã khởi động.
- Native handle hoặc object gắn với native library.
- Client giữ connection pool và trạng thái phiên.
- Cache phụ thuộc cấu hình, dữ liệu hoặc tenant của deployment.

Không đưa các resource này vào static initializer được chạy tại build time. Hãy tạo và đóng chúng theo vòng đời của application context hoặc component runtime.

## 4. Đọc cấu trúc thông báo lỗi

Một thông báo image heap thường chứa ba thông tin quan trọng:

~~~text
An object of type 'com.example.RuntimeCache' was found in the image heap.
This type, however, is marked for initialization at image run time
for the following reason: classes are initialized at run time by default.
This is not allowed for correctness reasons.
~~~

Diễn giải:

1. **Object type:** lớp của instance được tìm thấy trong image heap, ví dụ RuntimeCache.
2. **Initialization policy:** lớp đó đang được cấu hình hoặc mặc định khởi tạo ở runtime.
3. **Correctness constraint:** instance của lớp runtime-initialized không thể tồn tại trong image heap, vì nó sẽ tồn tại trước khi class initializer chạy ở runtime.

Builder có thể đưa ra hai hướng xử lý:

- Nếu object thực sự nên tồn tại như dữ liệu ban đầu của executable, xem xét đánh dấu kiểu tương ứng khởi tạo tại build time sau khi xác minh an toàn.
- Nếu object phải được tạo khi service chạy, tìm initializer hoặc factory đã tạo nó trong quá trình build và chuyển việc khởi tạo đó sang runtime.

Thông báo lỗi là manh mối đầu tiên, chưa phải bằng chứng đủ để chọn một trong hai hướng. Cần truy vết nguồn tạo object và kiểm tra dữ liệu mà object giữ.

## 5. Quy trình chẩn đoán có kiểm soát

### 5.1. Ghi lại đúng toolchain và lệnh build

Trước khi điều tra, lưu:

~~~bash
java -version
native-image --version
native-image --help
~~~

Ghi thêm:

- Spring Boot và Spring Framework version.
- GraalVM distribution và JDK version.
- Native Build Tools Maven/Gradle plugin version.
- Dependency graph của ứng dụng.
- Native build arguments đang được truyền.
- Profile/environment của build và các system properties liên quan.

Option và output có thể thay đổi giữa các GraalVM release. Dùng native-image --help, native-image --expert-options hoặc native-image --print-options của chính toolchain đang build để xác nhận option khả dụng.

### 5.2. Bật báo cáo class initialization

Dùng:

~~~bash
native-image \
  -H:+PrintClassInitialization \
  -jar target/orders-service.jar \
  -o orders-diagnostic
~~~

-H:+PrintClassInitialization giúp theo dõi các lớp được khởi tạo ở build time và lý do chúng được chọn. Đọc danh sách/report được build log chỉ ra, tập trung vào:

- Lớp được khởi tạo trước khi lỗi xuất hiện.
- Lớp được khởi tạo tự động vì được chứng minh an toàn.
- Lớp được kéo vào qua superclass hoặc superinterface có default method.
- Lớp được khởi tạo do static initializer gọi sang lớp khác.
- Lớp có policy runtime nhưng instance lại được tạo từ một initializer chạy lúc build.

Mục tiêu là hiểu vì sao lớp được khởi tạo và chuỗi dependency dẫn tới nó. Không cần chuyển tất cả lớp trong package sang một policy chung.

### 5.3. Truy vết nơi object được tạo

Khi thông báo cho biết object thuộc kiểu com.example.RuntimeCache, thêm option:

~~~bash
native-image \
  --trace-object-instantiation=com.example.RuntimeCache \
  -H:+PrintClassInitialization \
  -jar target/orders-service.jar \
  -o orders-traced
~~~

--trace-object-instantiation yêu cầu builder theo dõi nơi instance của kiểu được chỉ định được tạo trong quá trình image generation. Dùng tên lớp đầy đủ và kiểm tra output của đúng GraalVM version.

Nếu cần theo dõi nhiều kiểu, một số version cho phép danh sách tên lớp phân tách bằng dấu phẩy:

~~~bash
native-image \
  --trace-object-instantiation=com.example.RuntimeCache,com.example.RuntimeClient \
  -H:+PrintClassInitialization \
  -jar target/orders-service.jar \
  -o orders-traced
~~~

Chỉ trace các kiểu đang điều tra. Bật quá nhiều trace làm log khó đọc và tăng chi phí chẩn đoán.

### 5.4. Lần từ constructor về static initializer

Khi có trace, tìm:

1. Constructor hoặc factory method đã tạo instance.
2. Caller trực tiếp của constructor/factory.
3. Static field initializer hoặc static block đã gọi caller đó.
4. Lớp nào đã được khởi tạo trước và vì sao.
5. Object có còn reachable từ static root nào khác hay không.

Nếu trace cho thấy object được tạo bởi RuntimeConfig initializer, hãy xem toàn bộ static fields của RuntimeConfig và các method mà static initializer gọi. Nếu object được tạo bởi dependency, kiểm tra version và cấu hình initialization do thư viện cung cấp trước khi tự thêm option cho dependency.

### 5.5. Sơ đồ khoanh vùng

~~~mermaid
flowchart TD
    A[Build báo object runtime-init trong image heap] --> B[Đọc type và initialization reason]
    B --> C[Bật PrintClassInitialization]
    C --> D[Bật trace-object-instantiation cho type]
    D --> E[Tìm constructor/factory và caller]
    E --> F{Object có cần tồn tại từ lúc build?}
    F -->|Có, immutable và độc lập môi trường| G[Đánh giá build-time initialization]
    F -->|Không, là runtime state/resource| H[Chuyển nơi tạo object sang runtime]
    G --> I[Kiểm tra static fields và object graph]
    H --> J[Runtime-init lớp khởi tạo hoặc refactor static state]
    I --> K[Build lại và chạy regression tests]
    J --> K
    K --> L{Native behavior đúng?}
    L -->|Không| E
    L -->|Có| M[Ghi lại policy và bằng chứng]
~~~

## 6. Cách xử lý thứ nhất: object thực sự phù hợp với image heap

Chỉ dùng hướng này khi object là dữ liệu khởi tạo có thể snapshot an toàn:

- Không chứa secret hoặc credential.
- Không phụ thuộc hostname, user home, working directory hoặc file system của máy build.
- Không phụ thuộc biến môi trường/system property cần đọc lúc deploy.
- Không chứa timestamp hoặc random seed cần thay đổi theo process.
- Không giữ file descriptor, socket, thread, native handle hay resource runtime.
- Không giữ mutable global state cần cô lập giữa process/tenant.
- Không có side effect cần thực hiện ở thời điểm ứng dụng chạy.

Nếu đã xác minh, có thể đánh dấu class cụ thể khởi tạo ở build time:

~~~bash
native-image \
  --initialize-at-build-time=com.example.CatalogDefaults \
  -jar target/orders-service.jar \
  -o orders-service
~~~

Tùy chọn này cũng ảnh hưởng các superclass theo quy tắc class initialization. Hãy kiểm tra toàn bộ lớp liên quan và static fields sau khi thay đổi.

### 6.1. Kiểm tra object graph trước khi cho build time

Ví dụ một bảng cấu hình immutable:

~~~java
public final class CatalogDefaults {
    static final Map<String, String> LABELS = Map.of(
        "SKU-1", "Standard",
        "SKU-2", "Express"
    );

    private CatalogDefaults() {
    }
}
~~~

Nếu dữ liệu chỉ gồm hằng số không nhạy cảm, không phụ thuộc môi trường và được dùng như dữ liệu khởi tạo, build-time initialization có thể phù hợp.

Nhưng nếu map giữ một service object:

~~~java
static final Map<String, Object> COMPONENTS = createComponents();
~~~

thì phải xem từng value và mọi reference transitive. Một map immutable vẫn có thể trỏ đến client, cache hoặc resource runtime.

### 6.2. Không snapshot bí mật hoặc dữ liệu môi trường

Build-time initializer có thể đọc environment variables, system properties, file và các thông tin của máy build. Những giá trị đó có thể trở thành một phần của executable.

Ví dụ không nên snapshot:

~~~java
static final String API_TOKEN = System.getenv("PAYMENT_API_TOKEN");
static final String HOST = System.getenv("HOSTNAME");
static final Path CONFIG =
    Path.of(System.getProperty("user.home"), ".app", "config");
~~~

Nếu build pipeline có secret, static initializer đọc secret đó có thể làm secret đi vào image. Chạy native-image builder trong môi trường build chuyên dụng, không chứa thông tin nhạy cảm không cần thiết; đồng thời chuyển việc đọc cấu hình nhạy cảm sang runtime.

## 7. Cách xử lý thứ hai: object phải được tạo ở runtime

Nếu object biểu diễn trạng thái process hoặc tài nguyên runtime, không cố giữ nó trong image heap. Tìm lớp khởi tạo đã tạo object trong lúc build rồi chuyển initializer đó về runtime.

Ví dụ:

~~~java
public final class RuntimeRegistry {
    static final RuntimeCache CACHE = new RuntimeCache();

    private RuntimeRegistry() {
    }
}
~~~

Nếu RuntimeRegistry được khởi tạo ở build time, CACHE có thể được tạo trong image generation. Khi trace xác nhận đây là nguồn tạo object, có thể yêu cầu lớp registry khởi tạo ở runtime:

~~~bash
native-image \
  --initialize-at-run-time=com.example.RuntimeRegistry \
  -jar target/orders-service.jar \
  -o orders-service
~~~

Điều này trì hoãn static initializer của RuntimeRegistry tới runtime. Kiểm tra lại để bảo đảm không còn một static root khác tạo cùng object trong lúc build.

### 7.1. Runtime initialization có chi phí và quy tắc phân cấp

Runtime initialization làm builder giữ lại công việc khởi tạo cho lúc executable chạy. Điều đó có thể:

- Tăng công việc lúc startup.
- Thêm kiểm tra trạng thái initialization trước static field access, static method call và object allocation.
- Kéo các subclass vào runtime initialization theo quy tắc của GraalVM.
- Yêu cầu kiểm tra lại thứ tự khởi tạo và superclass/superinterface.

Quy tắc phân cấp có ý nghĩa cụ thể: khi một lớp được khởi tạo ở build time, các relevant supertypes của nó cũng phải được khởi tạo ở build time; khi một lớp được khởi tạo ở runtime, các relevant subtypes của nó cũng phải được khởi tạo ở runtime. Vì vậy policy có thể ảnh hưởng thêm lớp ngoài tên được ghi trong option. Đọc lại báo cáo class initialization sau mỗi thay đổi để xác nhận phạm vi thực tế.

Không chuyển cả package sang runtime chỉ để giải quyết một object nếu có thể xác định chính xác lớp gây tạo object.

### 7.2. Đừng đánh dấu nhầm lớp chứa object

Giả sử RuntimeCache được tạo từ static initializer của ApplicationDefaults:

~~~java
public final class ApplicationDefaults {
    static final RuntimeCache CACHE = CacheFactory.create();

    private ApplicationDefaults() {
    }
}
~~~

Nếu RuntimeCache cần được tạo ở runtime, điều quan trọng là ngăn ApplicationDefaults gọi factory trong quá trình build. Marking lớp tạo object (ApplicationDefaults) runtime có thể giải quyết nguồn tạo; marking một lớp khác không thay đổi static initializer đang chạy.

Dùng trace để xác nhận class nào thật sự tạo instance. Sau khi thay policy, build lại và kiểm tra object đó không còn được snapshot.

## 8. Refactor static state thành dependency runtime

Đối với ứng dụng Spring Boot, thường dễ kiểm soát vòng đời hơn khi chuyển client/cache/clock thành bean được tạo trong ApplicationContext thay vì static singleton.

### 8.1. Từ static singleton

~~~java
public final class PaymentClientHolder {
    static final PaymentClient CLIENT = PaymentClient.connect(
        System.getenv("PAYMENT_URL")
    );

    private PaymentClientHolder() {
    }
}
~~~

### 8.2. Sang Spring bean

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    PaymentClient paymentClient(
            @Value("${payment.url}") URI paymentUrl) {
        return PaymentClient.connect(paymentUrl);
    }
}
~~~

Spring tạo bean theo lifecycle của application context khi ứng dụng chạy. Cấu hình runtime có thể được đọc từ environment của deployment và client được đóng theo lifecycle phù hợp.

Đảm bảo client có cơ chế cleanup phù hợp, ví dụ bean destroy method hoặc interface lifecycle. Không tạo kết nối mạng trong static initializer.

### 8.3. Inject Clock thay cho static timestamp

~~~java
@Configuration(proxyBeanMethods = false)
class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}

@Service
class InvoiceService {
    private final Clock clock;

    InvoiceService(Clock clock) {
        this.clock = clock;
    }

    Instant createdAt() {
        return Instant.now(clock);
    }
}
~~~

Cách này giữ thời gian ở runtime và dễ test với Clock.fixed(...). Không snapshot Instant.now() trong static field nếu ứng dụng cần thời gian thực tại thời điểm xử lý.

### 8.4. Inject entropy và random generator

Không khởi tạo random seed trong static initializer được chạy ở build time. Dùng API phù hợp với nhu cầu bảo mật và runtime của ứng dụng, sau đó tạo dependency ở runtime. Với dữ liệu nhạy cảm, kiểm tra hướng dẫn JCA/SecureRandom của GraalVM release và cấu hình provider tương ứng.

Không thay SecureRandom bằng Random chỉ để tránh lỗi build. Đó là thay đổi ngữ nghĩa và có thể làm yếu bảo mật.

## 9. Quan hệ với Spring AOT

Spring AOT và Native Image build time là hai giai đoạn liên quan nhưng không đồng nhất.

Theo tài liệu Spring Boot hiện hành:

- Spring AOT khởi động ứng dụng tới khi các bean definitions có thể được xác định.
- AOT tạo mã source, bytecode cho proxy và GraalVM hints.
- Bean instances không được tạo trong chính giai đoạn AOT processing.
- Native Image builder tiếp tục phân tích và có thể chạy class initializers hoặc build-time code.

Vì vậy, khi gặp object trong image heap, đừng kết luận ngay Spring AOT đã khởi tạo bean đó. Hãy xem static initializer, Native Image Feature, dependency và mã build-time thực tế đã tạo object.

### 9.1. Kiểm tra mã AOT được sinh

Các đường dẫn được Spring Boot hiện hành mô tả:

| Build tool | Generated AOT source | Generated AOT resources |
| --- | --- | --- |
| Maven | target/spring-aot/main/sources | target/spring-aot/main/resources |
| Gradle | build/generated/aotSources | build/generated/aotResources |

Đường dẫn có thể khác theo Spring Boot/plugin version. Dùng chúng để đọc mã generated và hiểu bean definition/hints đã được tạo; không chỉnh trực tiếp generated output vì build tiếp theo có thể ghi đè.

### 9.2. Static initialization trong dependency

Lỗi có thể bắt nguồn từ dependency chứ không phải code ứng dụng. Ví dụ, một thư viện có thể tạo logger factory, registry hoặc provider trong static initializer. Khi gặp lỗi:

1. Xác định artifact và version sở hữu lớp.
2. Kiểm tra release notes/Native Image support của dependency.
3. Cập nhật dependency nếu có bản sửa tương thích.
4. Kiểm tra metadata/configuration mà thư viện cung cấp.
5. Chỉ thêm initialization policy sau khi hiểu initializer và trạng thái được tạo.

Không đánh dấu toàn bộ package dependency build-time chỉ vì một lớp gây lỗi.

## 10. Cấu hình diagnostics trong Maven và Gradle

Các ví dụ dưới đây dùng Native Build Tools. Hợp nhất vào plugin/profile hiện có và kiểm tra DSL theo version dự án.

### 10.1. Maven

Có thể thêm build arguments phục vụ chẩn đoán:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>-H:+PrintClassInitialization</buildArg>
            <buildArg>--trace-object-instantiation=com.example.RuntimeCache</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

Chạy native build theo profile dự án:

~~~bash
./mvnw -Pnative package
~~~

Sau khi đã xác định policy cần thiết, thêm option runtime/build-time tương ứng vào profile production. Giữ các trace option trong profile chẩn đoán riêng để tránh tạo log lớn ở mọi build.

### 10.2. Gradle Kotlin DSL

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("-H:+PrintClassInitialization")
            buildArgs.add(
                "--trace-object-instantiation=com.example.RuntimeCache"
            )
        }
    }
}
~~~

Chạy:

~~~bash
./gradlew nativeCompile
~~~

Sau khi xác định nguồn lỗi, thay trace option bằng initialization policy phù hợp, ví dụ:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add(
                "--initialize-at-run-time=com.example.RuntimeRegistry"
            )
        }
    }
}
~~~

### 10.3. Tách profile debug và production

Giữ hai cấu hình có mục đích rõ ràng:

| Cấu hình | Options | Mục tiêu |
| --- | --- | --- |
| Diagnostic | -H:+PrintClassInitialization, --trace-object-instantiation | Tìm nguyên nhân trong quá trình build. |
| Production | Initialization policy đã xác minh | Tạo executable cuối cùng với semantics đúng. |

Không giữ trace options vô thời hạn nếu không cần. Sau khi sửa, build lại với cấu hình gần production và chạy native tests.

## 11. Kiểm tra bảo mật và tính đúng đắn

Build-time initialization là snapshot trạng thái. Vì vậy phải kiểm tra cả correctness lẫn security.

### 11.1. Dữ liệu không nên xuất hiện trong image

Không để static initializer snapshot:

- API keys, passwords, OAuth tokens hoặc private keys.
- Random seeds cần được tạo mới ở runtime.
- User home, hostname, current working directory hoặc đường dẫn chỉ đúng trên máy build.
- Timestamp hoặc cache state cần phản ánh thời điểm chạy.
- File handles, socket, thread và native handles.
- Configuration khác nhau giữa staging và production.

Oracle GraalVM security guidance cảnh báo thông tin được tính trong static initializer có thể được lưu vào executable, bao gồm sensitive data và random seed. Vì vậy, chạy builder trong môi trường chuyên dụng, không đưa secrets không cần thiết vào build environment.

### 11.2. Kiểm tra cùng executable với cấu hình runtime khác nhau

Một regression test hữu ích:

1. Build native executable một lần.
2. Chạy với APP_REGION=ap-southeast-1.
3. Chạy lại cùng executable với APP_REGION=eu-west-1.
4. Xác nhận application đọc giá trị tương ứng ở mỗi lần chạy.
5. Xác nhận client/cache/path được tạo theo runtime configuration.
6. Kiểm tra không có dữ liệu nhạy cảm từ máy build bị đóng băng trong executable.

Nếu hai lần chạy vẫn dùng cùng một giá trị cũ, kiểm tra static field hoặc initializer đã snapshot cấu hình lúc build.

## 12. Các lỗi xử lý thường gặp

| Cách xử lý sai | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Thêm --initialize-at-build-time cho cả package | Có thể snapshot thêm secrets, environment và resource state. | Trace object, kiểm tra field/object graph rồi chọn lớp hẹp nhất. |
| Chỉ mark kiểu object runtime | Nguồn tạo object có thể nằm trong initializer của lớp khác. | Dùng --trace-object-instantiation để tìm culprit. |
| Cho rằng static final luôn immutable | Final chỉ khóa reference, không khóa object graph. | Kiểm tra loại object và transitive references. |
| Tắt strict image heap hoặc bỏ qua lỗi | Có thể che giấu sai khác semantics và resource state. | Sửa initialization policy hoặc refactor nguồn tạo object. |
| Mark cả package runtime | Tăng chi phí kiểm tra initialization và startup; có thể kéo subclass vào policy. | Dùng class-level policy nếu đủ. |
| Chỉ build lại mà không test runtime | Build pass chưa chứng minh configuration được đọc đúng lúc chạy. | Test nhiều runtime env và native executable. |
| Sửa file AOT generated | Build sau có thể ghi đè và không sửa nguồn. | Sửa source/configuration/Feature sở hữu hành vi. |
| Thay SecureRandom bằng Random | Làm thay đổi bảo đảm bảo mật. | Giữ API bảo mật và chuyển khởi tạo về runtime. |
| Đổ lỗi cho Spring bean lifecycle | Spring AOT không tạo bean instances trong phase xử lý bean definitions. | Truy vết static initializer và build-time code thực tế. |

## 13. Bài thực hành: xử lý RuntimeCache bị đưa vào image heap

**Bối cảnh:** dịch vụ Spring Boot có RuntimeRegistry chứa static singleton. Native build thất bại vì RuntimeCache được tìm thấy trong image heap, trong khi kiểu này được đánh dấu khởi tạo ở runtime. Cache cần đọc cấu hình lúc deploy và không được chia sẻ trạng thái từ máy build.

### Nhiệm vụ

1. Ghi lại GraalVM/JDK, Spring Boot, Native Build Tools và dependency versions.
2. Lưu nguyên thông báo lỗi, đặc biệt object type và initialization reason.
3. Build với -H:+PrintClassInitialization để xác định lớp được khởi tạo và lý do.
4. Build lại với --trace-object-instantiation=com.example.RuntimeCache.
5. Tìm static initializer/factory đã tạo RuntimeCache.
6. Kiểm tra static fields và object graph của RuntimeRegistry.
7. Xác định cache có thể là immutable build-time data hay phải được tạo theo runtime configuration.
8. Nếu cache là runtime state, refactor thành Spring bean hoặc chuyển lớp tạo object sang runtime initialization.
9. Nếu có object dữ liệu thực sự phù hợp với image heap, chứng minh nó immutable, độc lập môi trường và không chứa secret trước khi chọn build-time initialization.
10. Build native executable lại với policy hẹp nhất.
11. Chạy cùng executable với hai bộ runtime configuration khác nhau và xác nhận cache được tạo theo từng process.
12. Chạy JVM tests, AOT-on-JVM và native integration/smoke tests.
13. Lưu build log, trace, initialization policy và test report.

### Hồ sơ kết quả

| Bằng chứng | Nội dung cần lưu |
| --- | --- |
| Toolchain | GraalVM/JDK, Spring Boot, Native Build Tools và dependencies. |
| Error | Full error, object type và initialization reason. |
| Class initialization | Output -H:+PrintClassInitialization. |
| Instantiation trace | Output --trace-object-instantiation. |
| Root cause | Static field, initializer, factory và object graph. |
| Policy | Class được chọn build-time hoặc runtime và lý do. |
| Refactor | Source class/bean chịu trách nhiệm tạo runtime state. |
| Security | Kiểm tra secret, random seed và environment snapshot. |
| Regression | JVM, AOT-on-JVM, native tests với runtime configurations khác nhau. |
| Release evidence | Native build log, executable và known limitations. |

### Tiêu chí hoàn thành

- [ ] Giải thích được vì sao instance runtime-initialized không được ở image heap.
- [ ] Xác định được object type từ thông báo lỗi.
- [ ] Dùng được -H:+PrintClassInitialization.
- [ ] Dùng được --trace-object-instantiation.
- [ ] Tìm được static root hoặc initializer tạo object.
- [ ] Chọn đúng giữa build-time initialization và runtime initialization.
- [ ] Không snapshot secret, random seed hoặc environment-specific state.
- [ ] Refactor runtime resource thành dependency có lifecycle phù hợp.
- [ ] Native executable build thành công và chạy với nhiều runtime configuration.
- [ ] Regression tests xác nhận behavior sau khi sửa.

## 14. Câu hỏi tự đánh giá

1. Native Image tạo image heap từ những nguồn nào?
2. Class loading khác class initialization như thế nào?
3. Vì sao object của lớp runtime-initialized không được xuất hiện trong image heap?
4. static final có bảo đảm object không mutable và an toàn để snapshot không?
5. -H:+PrintClassInitialization cung cấp thông tin gì?
6. --trace-object-instantiation giúp tìm nguồn tạo object như thế nào?
7. Khi nào nên dùng --initialize-at-build-time?
8. Khi nào nên dùng --initialize-at-run-time?
9. Vì sao cần tìm lớp khởi tạo object thay vì chỉ đánh dấu kiểu object?
10. Những quy tắc superclass/subclass ảnh hưởng initialization policy ra sao?
11. Spring AOT tạo bean definitions khác gì tạo bean instances?
12. Làm thế nào kiểm tra secret hoặc runtime configuration không bị snapshot vào executable?

## 15. Tài liệu chính thức

Các option và initialization policy phụ thuộc GraalVM release. Luôn kiểm tra tài liệu/native-image --help của toolchain đang dùng:

- [GraalVM Native Image — Class Initialization](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/ClassInitialization/): build-time initialization, safe classes và -H:+PrintClassInitialization.
- [GraalVM Native Image — Specify Class Initialization Explicitly](https://www.graalvm.org/latest/reference-manual/native-image/guides/specify-class-initialization/): --initialize-at-build-time và --initialize-at-run-time.
- [GraalVM Native Image — Basics](https://www.graalvm.org/latest/reference-manual/native-image/basics/): build time, runtime, image heap và static analysis.
- [GraalVM Native Image — Command-line Options](https://www.graalvm.org/jdk25.5/reference-manual/native-image/overview/Options/): xác nhận --trace-object-instantiation và option availability theo version.
- [Oracle GraalVM — Security Considerations in Native Image](https://docs.oracle.com/en/graalvm/jdk/25/docs/security-guide/native-image/): nguy cơ snapshot secrets, random seeds và runtime initialization.
- [Oracle GraalVM SDK — RuntimeClassInitialization](https://docs.oracle.com/en/graalvm/jdk/25/sdk/org/graalvm/nativeimage/hosted/RuntimeClassInitialization.html): API cấu hình class initialization trong Native Image Feature.
- [Spring Boot — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html): Spring AOT, generated bean definitions, generated source và hints.

**Điểm cần nhớ:** lỗi image heap là dấu hiệu object được tạo trong build time nhưng thuộc kiểu cần khởi tạo runtime. Hãy trace nguồn tạo, kiểm tra object graph và dữ liệu được snapshot; chỉ chọn build-time initialization cho dữ liệu thực sự an toàn, còn runtime state phải được tạo trong vòng đời ứng dụng.

