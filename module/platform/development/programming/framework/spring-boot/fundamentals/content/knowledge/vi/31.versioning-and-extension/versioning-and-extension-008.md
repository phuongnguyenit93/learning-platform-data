# AOT, runtime hints và native image ở mức khái niệm

Spring Boot truyền thống thường chạy ứng dụng trên JVM. Khi khởi động, JVM nạp class, tạo object, phân tích cấu hình và dùng các cơ chế như reflection hoặc proxy để lắp ghép Spring ApplicationContext. JVM còn có thể tối ưu code trong lúc chạy bằng Just-In-Time compiler (JIT).

Với các ứng dụng cần khởi động nhanh, dùng ít bộ nhớ hoặc chạy trong môi trường ngắn hạn, quá trình khởi động và chi phí runtime của mô hình truyền thống có thể trở thành yếu tố cần tối ưu. Spring Framework 6 và Spring Boot 3 đưa **Ahead-of-Time processing (AOT)** vào quy trình build để phân tích ứng dụng sớm hơn, tạo mã khởi tạo và cung cấp thông tin cần thiết cho các môi trường runtime hạn chế khả năng khám phá động.

Khi kết hợp AOT với **GraalVM Native Image**, ứng dụng Java có thể được biên dịch thành executable native dành cho một hệ điều hành và kiến trúc CPU cụ thể. Kết quả thường khởi động nhanh và có footprint bộ nhớ thấp hơn trong nhiều workload, nhưng build phức tạp hơn và một số tính năng động của Java cần được khai báo rõ ràng.

Ba khái niệm cần phân biệt:

- **AOT processing**: phân tích application ở build time và tạo source/resource/hints để giảm công việc động lúc startup.
- **Runtime hints**: metadata mô tả những thao tác runtime như reflection, truy cập resource, serialization hoặc tạo proxy mà native compiler cần biết trước.
- **Native image**: executable được tạo từ application và dependencies bằng native-image compiler, có thể chạy trực tiếp trên nền tảng đích mà không cần JVM cài riêng theo cách chạy JAR truyền thống.

AOT và native image có liên quan nhưng không phải một khái niệm. AOT-generated application vẫn có thể chạy trên JVM; native image là một kiểu đóng gói/runtime khác sử dụng thông tin AOT.

## 1. Từ JVM truyền thống đến AOT và native image

Một ứng dụng Spring Boot thông thường được đóng gói thành executable JAR:

~~~text
demo-app.jar
├── application classes
├── application resources
├── Spring libraries
├── third-party dependencies
└── Spring Boot loader
~~~

Khi chạy:

~~~bash
java -jar demo-app.jar
~~~

JVM khởi động, nạp class, tạo Spring context và xử lý các request. Trong quá trình chạy, JIT compiler có thể tối ưu các đoạn code được thực thi thường xuyên dựa trên profiling runtime.

Native image có quy trình khác. Native compiler phân tích những class/method có thể được sử dụng, các metadata và runtime hints trong lúc build để tạo executable:

~~~text
Source + dependencies
        |
        v
Spring AOT processing
        |
        +--> Generated Java sources
        +--> Generated resources
        +--> Runtime hints
        |
        v
Native Image compiler
        |
        v
Platform-specific executable
~~~

Có thể so sánh:

| Tiêu chí | Chạy JAR trên JVM | Chạy native image |
| --- | --- | --- |
| Artifact chính | JAR chứa bytecode và dependencies | Executable native theo OS/CPU |
| Runtime | Cần JVM tương thích | Không cần JVM riêng theo mô hình chạy JAR |
| Biên dịch | Java source thành bytecode; JIT tối ưu lúc chạy | Native compiler tạo machine code lúc build |
| Khởi động | JVM và application cùng khởi tạo | Thường nhanh hơn đáng kể |
| Bộ nhớ | Có JVM runtime và heap phù hợp | Thường có footprint thấp hơn ở nhiều workload |
| Tối ưu throughput | JIT có thể tối ưu theo hành vi thực tế | Không có JIT profiling tương tự trong runtime truyền thống |
| Reflection/dynamic loading | Nhiều khả năng được xử lý linh hoạt | Cần metadata/hints cho các trường hợp không thể phân tích tĩnh |
| Build | Thường nhanh và đơn giản hơn | Thường lâu hơn, cần native toolchain và nhiều tài nguyên |
| Tính portable | Một JAR có thể chạy trên nhiều OS với JVM phù hợp | Binary gắn với nền tảng build |
| Debugging/diagnostics | Hệ sinh thái JVM trưởng thành | Một số công cụ và hành vi khác biệt |

Không có lựa chọn tốt nhất cho mọi ứng dụng. Hãy chọn theo workload, thời gian khởi động, bộ nhớ, cách scale, độ phức tạp dependency và chi phí build/release.

## 2. AOT processing thực hiện việc gì?

Spring cần biết những bean nào sẽ được tạo, configuration nào được áp dụng, dependency được kết nối ra sao và proxy nào cần thiết. Trong mô hình runtime truyền thống, một phần công việc này được thực hiện động khi application khởi động.

AOT processing chuyển một phần công việc đó sang build time. Spring phân tích cấu hình ứng dụng trong một môi trường build xác định và sinh ra các thành phần hỗ trợ khởi tạo context.

Ở mức khái niệm, quy trình gồm:

1. Build tool chuẩn bị main classes, resources và dependencies.
2. Spring AOT khởi tạo/đánh giá application context trong quá trình build.
3. Framework phân tích bean definitions và các cấu hình liên quan.
4. Framework sinh mã Java và resources thể hiện cách khởi tạo đã được phân tích.
5. Runtime hints được thu thập để mô tả những khả năng động cần có.
6. Các output AOT được dùng khi chạy ứng dụng trên JVM hoặc làm đầu vào cho native-image compilation.

~~~mermaid
flowchart TD
    A["Java source + application config"] --> B["Compile main classes"]
    B --> C["Spring AOT processing"]
    C --> D["Phân tích bean/configuration graph"]
    C --> E["Thu thập RuntimeHints"]
    D --> F["Generated initialization code"]
    E --> G["Reflection/resource/proxy metadata"]
    F --> H["AOT-processed application"]
    G --> H
    H --> I["Chạy trên JVM"]
    H --> J["Native Image compilation"]
    J --> K["Native executable"]
~~~

AOT không đơn giản là chạy `javac` sớm hơn. Nó hiểu một phần cấu trúc Spring application để tạo cách khởi tạo tối ưu và metadata cho runtime.

### 2.1. Những công việc có thể được thực hiện sớm

Tùy ứng dụng và framework integration, AOT có thể xử lý trước:

- Phân tích bean definitions và dependency graph.
- Phân tích configuration classes và điều kiện auto-configuration.
- Tạo mã đăng ký/khởi tạo bean.
- Tạo hoặc mô tả proxy cần thiết.
- Chuẩn bị metadata truy cập reflection.
- Ghi nhận resource cần được đưa vào native image.
- Chuẩn bị metadata cho serialization và các tính năng động được hỗ trợ.

Một số thao tác vẫn diễn ra lúc runtime, ví dụ tạo bean instance, kết nối database, bind server socket, đọc request hoặc thực hiện business logic. AOT giảm công việc khám phá/thiết lập có thể biết trước; nó không biến ứng dụng thành một chương trình không còn runtime.

### 2.2. AOT không thay thế Java compiler

Java source vẫn cần được biên dịch. AOT processing sử dụng application classes và dependencies đã chuẩn bị để phân tích Spring configuration, rồi sinh thêm source/resource. Nếu source không compile được, AOT không thể biến nó thành một ứng dụng hợp lệ.

Các giai đoạn vẫn có quan hệ:

~~~text
Java compile
    |
    v
Spring AOT processing
    |
    v
Compile generated AOT sources
    |
    v
JVM execution hoặc native-image compilation
~~~

Build tool tích hợp các task này thành một task graph; thứ tự cụ thể phụ thuộc plugin và cấu hình project.

## 3. AOT có thể dùng mà không cần native image

Đây là điểm dễ nhầm: **AOT processing không bắt buộc ứng dụng phải trở thành native executable**.

Một ứng dụng có thể tạo generated AOT code rồi tiếp tục chạy trên JVM. Khi đó:

- Artifact vẫn chạy trong JVM.
- Các mã khởi tạo được sinh sẵn có thể giảm một phần công việc setup.
- Những thư viện và tính năng runtime vẫn cần tương thích với cách ứng dụng được AOT xử lý.
- Bạn không cần native-image compiler chỉ để hiểu hoặc thử AOT processing trên JVM.

Native image sử dụng output AOT cùng hints để xây dựng executable native. Vì vậy, quy trình thường có hai lựa chọn đầu ra:

~~~text
                     +--> AOT application chạy trên JVM
Spring AOT output ---|
                     +--> Native Image compiler --> Native executable
~~~

### 3.1. Khi nào AOT trên JVM hữu ích?

Có thể cân nhắc khi muốn:

- Đo tác động của AOT mà chưa thay đổi cách triển khai runtime.
- Tìm các tính năng động chưa tương thích native image.
- Kiểm tra generated initialization code.
- Chuẩn bị dần ứng dụng cho native compilation.
- Giữ cách vận hành JAR/JVM trong khi đánh giá lợi ích.

AOT trên JVM không tự đảm bảo startup sẽ cải thiện như native image. Cần benchmark cùng ứng dụng, cùng dữ liệu và cùng môi trường.

### 3.2. Native image là bước tiếp theo, không phải tên khác của AOT

AOT processing tạo ra thông tin build-time. Native Image compiler sử dụng thông tin đó để tạo executable. Nếu build chỉ chạy AOT task rồi đóng gói JAR, bạn vẫn có thể đang phát hành JVM application.

Khi đọc CI log, hãy xác định task nào thực sự tạo native executable thay vì suy luận từ chữ “AOT” xuất hiện trong output.

## 4. Native Image và closed-world assumption

GraalVM Native Image dùng phân tích reachability để xác định phần code nào có thể được gọi từ entry point của ứng dụng. Các class, method và resource có thể truy cập được sẽ được đưa vào image theo quy tắc compiler và metadata.

Cách tiếp cận này thường được gọi là **closed-world assumption**: compiler cần có khả năng xác định trước những thành phần có thể được sử dụng. Nó khác JVM truyền thống, nơi ứng dụng có thể nạp class hoặc khám phá method linh hoạt khi đang chạy.

Ví dụ:

~~~java
Class<?> type = Class.forName(className);
Object instance = type.getDeclaredConstructor().newInstance();
~~~

Trong JVM truyền thống, class name có thể đến từ cấu hình runtime và class loader có thể tìm class nếu nó nằm trên classpath. Với native image, compiler không thể luôn biết mọi giá trị có thể có của `className`. Nếu class hoặc constructor không được nhận diện là reachable, code có thể lỗi khi chạy native executable.

### 4.1. Reachability analysis

Native Image phân tích quan hệ gọi và metadata để tìm các thành phần có thể đạt tới từ application entry points. Nó có thể loại phần code không reachable khỏi executable, giúp giảm footprint.

Nhưng những đường truy cập gián tiếp như reflection, dynamic proxy, resource lookup hoặc serialization có thể không hiện rõ trong call graph thông thường.

### 4.2. Vì sao thiếu metadata gây lỗi?

Giả sử một thư viện đọc class name từ YAML, sau đó gọi reflection để tạo object. Native compiler không nhất thiết nhìn thấy class đó được sử dụng trực tiếp.

Nếu không có hint/metadata phù hợp, có thể xảy ra:

- Không tìm thấy class trong native image.
- Không truy cập được constructor hoặc method.
- Không tạo được proxy.
- Không tìm thấy resource.
- Serialization/deserialization thất bại.
- Một tính năng hoạt động trên JVM nhưng lỗi trong native executable.

Điểm quan trọng: lỗi này có thể chỉ xuất hiện **sau khi native image đã build thành công**, tại thời điểm chạy nhánh code chưa được khai báo metadata đầy đủ.

## 5. Runtime hints là gì?

Runtime hints là các khai báo cho Spring AOT biết những khả năng runtime nào cần được giữ lại hoặc cho phép khi build native image.

Spring Framework cung cấp API để mô tả các nhóm chính:

| Nhóm hint | Mục đích | Ví dụ |
| --- | --- | --- |
| Reflection | Truy cập class/member bằng reflection | Constructor, field, method |
| Resources | Đưa file/resource vào image | Template, schema, JSON, certificate public |
| Proxies | Tạo proxy theo interface | JDK dynamic proxy |
| Serialization | Hỗ trợ Java serialization cho type được chỉ định | Object cần serialize/deserialize |
| Native metadata bổ sung | Các yêu cầu đặc thù của runtime/library | JNI hoặc class initialization theo cấu hình native toolchain |

Runtime hints không phải một cơ chế mã hóa secret hoặc thay thế dependency management. Chúng là metadata kỹ thuật cho compiler/runtime biết một số thao tác động cần được hỗ trợ.

### 5.1. Hint không tạo dependency bị thiếu

Nếu ứng dụng dùng `com.vendor.sdk.Client` nhưng dependency không có trong build, đăng ký reflection hint cho class đó không thể làm class tự xuất hiện.

Trước khi thêm hints, cần xác nhận:

- Dependency có trong runtime classpath không?
- Class/resource có thực sự được đóng gói không?
- Thao tác động nào khiến compiler không nhìn thấy usage?
- Thư viện đã cung cấp reachability metadata chưa?
- Có API Spring Framework nào khai báo thay cho custom hint không?

### 5.2. Chỉ đăng ký quyền truy cập cần thiết

Không nên mở reflection cho toàn bộ package hoặc mọi member chỉ để loại bỏ lỗi build. Hint càng rộng có thể làm tăng kích thước image và giữ lại nhiều code hơn cần thiết.

Hãy đăng ký đúng class, member và resource mà ứng dụng thực sự dùng.

## 6. Reflection hints

Reflection cho phép code tìm class, constructor, method hoặc field khi runtime. Frameworks như JSON binding, ORM, dependency injection, validation và mapping libraries có thể dùng reflection.

Ví dụ:

~~~java
Class<?> type = Class.forName("com.example.shop.PaymentRequest");
Constructor<?> constructor = type.getDeclaredConstructor();
Object request = constructor.newInstance();
~~~

Với native image, class và constructor được truy cập theo cách này có thể cần reflection metadata.

Spring RuntimeHints API cho phép khai báo:

~~~java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.aot.hint.TypeReference;

public class PaymentRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
                TypeReference.of(PaymentRequest.class),
                MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS
        );
    }
}
~~~

Ví dụ chỉ minh họa ý tưởng đăng ký public constructors và public methods cho type cụ thể. Hãy chọn member categories dựa trên cách thư viện thực sự truy cập object.

### 6.1. Gắn RuntimeHintsRegistrar vào configuration

Có thể import registrar:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PaymentRuntimeHints.class)
public class PaymentConfiguration {
}
~~~

Khi Spring AOT xử lý configuration, registrar được gọi để bổ sung hints tương ứng.

### 6.2. @RegisterReflectionForBinding

Với các DTO được dùng trong data binding/serialization scenarios mà Spring hỗ trợ, có thể dùng annotation:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;

@RegisterReflectionForBinding({
        PaymentRequest.class,
        PaymentResponse.class
})
@Configuration(proxyBeanMethods = false)
public class PaymentBindingConfiguration {
}
~~~

Annotation này giúp đăng ký reflection hints cần thiết cho binding các type được chỉ định. Nó phù hợp hơn việc tự viết hàng loạt member hints khi mục tiêu là hỗ trợ binding qua các integration Spring tương ứng.

Không nên hiểu annotation là giải pháp cho mọi thư viện reflection. Nếu một third-party library thực hiện reflection theo cách riêng, cần kiểm tra reachability metadata hoặc bổ sung hints phù hợp.

### 6.3. Đăng ký class khác với đăng ký mọi class trong package

Nếu chỉ có hai DTO cần binding, hãy đăng ký hai DTO đó. Đừng mở toàn bộ package bằng một cấu hình reflection tổng quát nếu không có lý do.

Metadata chính xác giúp image chỉ giữ các thành phần cần thiết và giảm nguy cơ phụ thuộc ngầm vào code không được khai báo.

## 7. Resource hints

Ứng dụng Java có thể đọc file từ classpath:

~~~java
try (InputStream input =
        getClass().getResourceAsStream("/templates/invoice.html")) {
    // Đọc template.
}
~~~

Trong JVM, resource có thể được tìm thấy từ thư mục classes hoặc dependency JAR. Native image cần biết resource nào phải được đưa vào executable.

Ví dụ đăng ký pattern:

~~~java
public class PaymentRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.resources().registerPattern("templates/payment/*.html");
        hints.resources().registerPattern("schemas/payment/*.json");
    }
}
~~~

Pattern được tính theo resource path trong classpath. Hãy đăng ký phạm vi vừa đủ; pattern quá rộng có thể làm executable chứa nhiều tài nguyên không cần thiết.

### 7.1. Resource không phải filesystem file

Một resource nằm trong JAR/native image không nhất thiết có đường dẫn file vật lý. Code nên ưu tiên stream:

~~~java
try (InputStream input = resource.getInputStream()) {
    // Parse resource.
}
~~~

Thay vì giả định:

~~~java
File file = resource.getFile();
~~~

Cách đọc qua stream thường phù hợp hơn với resource được đóng gói trong archive hoặc native image.

### 7.2. Resource được tạo lúc runtime

Nếu ứng dụng tạo file tạm, tải dữ liệu từ remote hoặc ghi file vào thư mục writable, đó là filesystem/runtime behavior, không phải resource tĩnh cần đưa vào image.

Không đăng ký một pattern resource để thay thế việc cấu hình thư mục lưu dữ liệu runtime.

## 8. Proxy hints

Spring và nhiều thư viện dùng proxy để triển khai các tính năng như:

- AOP và method interception.
- Transaction management.
- Security method interception.
- Lazy loading.
- Interface-based client hoặc adapter.

JDK dynamic proxy thường tạo proxy cho một tập interface. Native image cần biết các interface proxy có thể được tạo.

Ví dụ đăng ký:

~~~java
hints.proxies().registerJdkProxy(
        PaymentGateway.class,
        Auditable.class
);
~~~

Đây là phần của một `RuntimeHintsRegistrar`. Hint nói rằng runtime cần khả năng tạo JDK proxy triển khai các interface đã chỉ định.

### 8.1. JDK proxy và class-based proxy

JDK proxy triển khai interface. Class-based proxy có thể dựa vào subclass generation hoặc cơ chế proxy khác. Spring AOT và native support có thể xử lý nhiều trường hợp phổ biến bằng generated code/hints, nhưng không nên giả định mọi bytecode generation library đều tự tương thích.

Nếu một thư viện tự tạo class/proxy bằng bytecode ở runtime, hãy kiểm tra tài liệu native support của thư viện. Có thể cần một integration khác hoặc thay cách thiết kế.

### 8.2. Hints không sửa giới hạn thiết kế proxy

Nếu method không thể được override theo quy tắc Java hoặc proxy không thể intercept lời gọi self-invocation, thêm proxy hint không thay đổi semantics của method call. Hãy phân biệt lỗi native metadata với giới hạn AOP/proxy của chính thiết kế ứng dụng.

## 9. Serialization hints

Một số ứng dụng sử dụng Java object serialization hoặc thư viện yêu cầu metadata type khi chuyển object thành dữ liệu.

Spring RuntimeHints có thể đăng ký type cho serialization:

~~~java
hints.serialization().registerType(PaymentSnapshot.class);
~~~

Đây là ví dụ về một type cần được giữ metadata serialization trong native image.

### 9.1. JSON binding không đồng nghĩa Java serialization

Jackson JSON binding, Spring HTTP message conversion và Java native serialization là các cơ chế khác nhau. Không nên thêm serialization hint chỉ vì một DTO được trả về từ REST controller.

Với JSON binding, cần dùng cơ chế reflection/binding hints phù hợp với Jackson và Spring integration. Hãy xác định đúng serializer/deserializer thực tế.

### 9.2. Kiểm tra thư viện serialization

Nếu ứng dụng dùng thư viện serialization bên ngoài, kiểm tra thư viện có native support hoặc reachability metadata sẵn không. Thêm hint cho một class có thể chưa đủ nếu thư viện còn cần constructor, field, annotation hoặc resource khác.

## 10. Third-party libraries và reachability metadata

Ứng dụng Spring Boot hiếm khi chỉ dùng code do team tự viết. Các dependency có thể sử dụng reflection, proxy, resources, JNI hoặc dynamic class loading bên trong.

Một thư viện native-ready có thể cung cấp reachability metadata để compiler biết những thành phần cần thiết. Hệ sinh thái GraalVM có Reachability Metadata Repository và các cách phân phối metadata đi cùng dependency.

Khi dùng dependency mới, hãy kiểm tra:

- Nhà phát triển có công bố hỗ trợ GraalVM Native Image không?
- Dependency version hiện tại có metadata phù hợp không?
- Metadata có được build tool/native toolchain tự nhận diện không?
- Có cần cấu hình bổ sung cho feature bạn sử dụng không?
- Test suite có chạy qua native executable không?

Không nên kết luận một thư viện tương thích native chỉ vì ứng dụng JVM dùng nó bình thường.

### 10.1. Native compatibility là thuộc tính của cách sử dụng

Một thư viện có thể tương thích native trong trường hợp A nhưng cần hint bổ sung ở trường hợp B. Ví dụ, API thông thường có thể được compiler nhìn thấy tĩnh, còn một extension system nạp class theo tên cấu hình runtime lại cần metadata bổ sung.

Hãy kiểm tra use case cụ thể, không chỉ đọc badge “GraalVM supported”.

### 10.2. Tránh tự viết metadata trùng lặp

Nếu dependency đã cung cấp reachability metadata chính xác, việc thêm một bộ cấu hình thủ công khác có thể gây khó bảo trì. Ưu tiên metadata do thư viện sở hữu; chỉ bổ sung phần còn thiếu của ứng dụng hoặc integration đặc thù.

## 11. Spring AOT và điều kiện cấu hình

Spring Boot có thể đánh giá một số điều kiện configuration trong AOT processing, ví dụ:

- `@ConditionalOnClass`.
- `@ConditionalOnProperty`.
- `@Profile`.
- Các condition của auto-configuration.
- Bean definitions và configuration import graph.

Vì một phần quyết định được thực hiện trong build time, **môi trường dùng để chạy AOT processing cần phù hợp với application configuration dự kiến khi chạy**.

Ví dụ một module chỉ được tạo khi:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "app.payment",
        name = "enabled",
        havingValue = "true"
)
public class PaymentConfiguration {
}
~~~

Nếu AOT processing diễn ra với property khiến configuration không được áp dụng, generated application có thể không chứa module đó như bạn kỳ vọng ở runtime.

### 11.1. Runtime property và build-time decision khác nhau

Không phải mọi property đều bị cố định trong AOT. Những giá trị cấu hình được đọc trong runtime theo cách thông thường vẫn có thể thay đổi khi chạy. Điều cần chú ý là các giá trị được dùng để quyết định cấu trúc bean/configuration trong quá trình AOT có thể ảnh hưởng generated output.

Hãy phân biệt:

- **Cấu hình tạo cấu trúc application**: profile/condition quyết định bean nào được đăng ký.
- **Cấu hình vận hành runtime**: URL, timeout, credentials hoặc giá trị nghiệp vụ được đọc lúc chạy nếu thiết kế hỗ trợ.
- **Cấu hình native build**: target platform, build options và metadata compiler.

### 11.2. Không đưa secret production vào AOT build

AOT build không phải nơi để cung cấp credential production. Không bake password, token hoặc private key vào image hoặc generated artifact.

Hãy inject secrets từ secret manager/environment ở runtime. Nếu một property condition cần quyết định cấu trúc application tại build time, chỉ dùng giá trị cấu hình không nhạy cảm và có chính sách build/release rõ ràng.

### 11.3. Nhiều profile có bean graph khác nhau

Nếu `dev` và `prod` đăng ký các implementation khác nhau bằng `@Profile`, một generated AOT application được tạo với một profile build-time không thể được giả định tự tái cấu trúc toàn bộ bean graph theo mọi profile runtime.

Có thể cần tạo AOT/native artifact riêng cho từng cấu hình cấu trúc, hoặc thiết kế variation theo runtime property/strategy mà AOT support cho phép. Hãy kiểm tra behavior của phiên bản Boot và build setup đang dùng.

## 12. Những tính năng Java cần chú ý khi chuyển sang native

Native Image không phải lúc nào cũng hỗ trợ mọi thao tác động giống JVM. Những nhóm cần xem xét:

| Tính năng | Rủi ro | Cách tiếp cận |
| --- | --- | --- |
| Reflection | Class/member không được khai báo metadata | Spring RuntimeHints hoặc metadata của dependency |
| Dynamic class loading | Class name chỉ biết lúc runtime | Giảm dynamic loading hoặc cung cấp metadata/build-time registration |
| Resource lookup | File không được đưa vào image | Đăng ký resource pattern |
| JDK dynamic proxy | Interface proxy không được nhận diện | Đăng ký proxy hints |
| Runtime bytecode generation | Class mới được tạo khi ứng dụng chạy | Dùng integration hỗ trợ AOT hoặc thay thiết kế |
| Java serialization | Type/member metadata thiếu | Serialization hints và test native |
| JNI | Native library hoặc symbol chưa được cấu hình | Kiểm tra GraalVM/native metadata và platform library |
| Class initialization | Static state bị khởi tạo sai thời điểm | Xem xét build-time/runtime initialization |
| ServiceLoader | Provider không được nhận diện | Kiểm tra service metadata và resource inclusion |
| Scripting/plug-in systems | Nạp code động từ bên ngoài | Xác định giới hạn; có thể không phù hợp native |

### 12.1. Dynamic class loading

Nếu ứng dụng cho phép admin nhập tên class tùy ý để nạp plugin, mô hình closed-world của native image sẽ gặp khó khăn. Native executable không thể tự chứa mọi class chưa biết lúc build.

Một hướng khác là chọn danh sách implementation đã biết và đăng ký chúng rõ ràng:

~~~java
Map<String, PaymentProvider> providers = Map.of(
        "card", new CardPaymentProvider(),
        "bank", new BankPaymentProvider()
);
~~~

Cách này làm khả năng sử dụng trở nên tường minh và dễ phân tích hơn. Nếu thật sự cần nạp code tùy ý sau deploy, JVM có thể phù hợp hơn.

### 12.2. Runtime bytecode generation

Một số thư viện tạo subclass hoặc bytecode mới khi chạy. Native Image thường cần code đó được tạo trước hoặc có một cơ chế được hỗ trợ.

Spring AOT có thể sinh sẵn một số proxy/initialization artifacts mà framework biết cách xử lý. Nhưng nó không thể tự động biến mọi thư viện bytecode-generation thành native-compatible.

### 12.3. ServiceLoader

Một thư viện có thể tìm provider bằng `ServiceLoader`. Hãy kiểm tra provider metadata và resource được đóng gói đúng trong native image. Nếu provider được phát hiện động qua classpath mà không được compiler nhận diện, có thể cần metadata/hints theo cách thư viện hỗ trợ.

## 13. Static initialization và build-time initialization

Java class có thể thực hiện công việc trong static initializer:

~~~java
public class RuntimeSettings {

    static final String REGION =
            System.getenv("APP_REGION");

    static final Instant STARTED_AT = Instant.now();
}
~~~

Trong môi trường native image, một số class có thể được khởi tạo tại build time theo quy tắc/cấu hình compiler. Nếu static initializer đọc environment variable, thời gian hiện tại, file hoặc network resource, giá trị đó có nguy cơ phản ánh môi trường build thay vì môi trường chạy.

### 13.1. Tránh side effects trong static initializer

Không nên dùng static initialization để:

- Kết nối database hoặc network.
- Đọc credential runtime.
- Ghi file.
- Lấy thời gian cần phản ánh lúc ứng dụng khởi động.
- Đọc biến môi trường khác nhau giữa build và deployment.
- Tạo global mutable state phụ thuộc môi trường.

Đưa những việc đó vào bean initialization hoặc lifecycle phù hợp ở runtime.

### 13.2. Build-time init khác runtime init

GraalVM cung cấp các tùy chọn điều khiển thời điểm class initialization. Đây là cấu hình native compiler, cần dùng có chủ đích vì việc chuyển initialization sang build time có thể đóng băng state hoặc kích hoạt side effects sớm.

Không nên tùy tiện đặt cả package third-party thành build-time initialized chỉ để native compilation chạy qua. Hãy xem tài liệu thư viện và kiểm tra output diagnostic của compiler.

## 14. Spring Boot hỗ trợ AOT từ phiên bản nào?

Spring Boot 3 được xây dựng trên Spring Framework 6 và tích hợp AOT/native-image support như một phần của nền tảng. Với Spring Boot 3, không cần dựa vào dự án Spring Native cũ như một plugin độc lập cho mô hình hiện tại.

Ở mức khái niệm:

- Spring Framework cung cấp AOT infrastructure và RuntimeHints API.
- Spring Boot tích hợp AOT processing vào build plugins và application bootstrap.
- GraalVM Native Image compiler tạo executable native.
- GraalVM Native Build Tools hoặc buildpacks có thể điều phối quy trình native compilation.
- Dependency/library có thể cung cấp reachability metadata riêng.

Hãy dùng tài liệu đúng phiên bản Spring Boot và GraalVM đang chạy. Native build toolchain, plugin compatibility và metadata format có thể thay đổi theo version.

## 15. Build AOT/native với Gradle

Trong Gradle project Spring Boot, plugin Spring Boot tích hợp với AOT processing. Khi thêm GraalVM Native Build Tools plugin tương thích, build có thể cung cấp task native compilation.

Ví dụ cấu trúc build ở mức khái niệm:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.x'
    id 'io.spring.dependency-management' version '1.1.x'
    id 'org.graalvm.buildtools.native' version '0.10.x'
}
~~~

Các version ở đây chỉ minh họa dòng plugin; hãy dùng version đã được kiểm tra tương thích với JDK, Spring Boot và GraalVM của project.

### 15.1. Chạy AOT processing

~~~bash
./gradlew processAot
~~~

Task này chạy Spring AOT processing và tạo generated sources/resources phục vụ application. Output directory cụ thể phụ thuộc Gradle plugin/version, thường nằm dưới thư mục build/generated hoặc build output của project.

AOT processing thành công chưa có nghĩa native executable đã được tạo.

### 15.2. Native compile

~~~bash
./gradlew nativeCompile
~~~

Task này yêu cầu native toolchain phù hợp, thường là GraalVM Native Image hoặc môi trường build được cấu hình tương ứng. Spring Boot Gradle plugin có thể liên kết AOT processing vào task graph khi Native Build Tools plugin được áp dụng.

Kết quả là executable native được tạo cho OS/architecture của môi trường build.

### 15.3. Build image bằng buildpacks

Spring Boot Gradle plugin có task `bootBuildImage` để tạo OCI image thông qua Cloud Native Buildpacks khi project được cấu hình phù hợp.

Một buildpack có thể tạo JVM image hoặc native image tùy builder, environment và cấu hình. Không nên suy luận rằng mọi lần `bootBuildImage` đều tạo native image; hãy kiểm tra buildpack configuration và build logs.

### 15.4. Kiểm tra task graph

Có thể xem các task liên quan:

~~~bash
./gradlew tasks --all
~~~

Hoặc:

~~~bash
./gradlew nativeCompile --dry-run
~~~

`--dry-run` giúp quan sát task graph mà không thực hiện build thật. Đây là cách hiểu task dependencies trước khi chạy một native compilation tốn thời gian.

## 16. Build AOT/native với Maven

Spring Boot Maven Plugin cung cấp AOT goals. Với project dùng Spring Boot parent và native profile được cấu hình theo convention, một lệnh phổ biến là:

~~~bash
mvn -Pnative native:compile
~~~

Quá trình thường gồm:

1. Maven chuẩn bị project classes và dependencies.
2. Spring Boot Maven Plugin chạy AOT processing.
3. Generated sources được compile.
4. Native Build Tools gọi GraalVM Native Image compiler.
5. Native executable được tạo trong output directory do plugin cấu hình.

Có thể gọi AOT goal riêng trong project đã cấu hình plugin:

~~~bash
mvn spring-boot:process-aot
~~~

Tên goal và execution wiring phụ thuộc phiên bản Spring Boot Maven Plugin. Kiểm tra POM/effective POM nếu task không được nhận diện hoặc không chạy ở phase mong đợi.

### 16.1. Native profile không tự cài mọi công cụ

Profile Maven thường cấu hình plugin và dependencies cần cho native build. Máy/CI vẫn cần native toolchain tương thích hoặc một build environment được hỗ trợ.

Nếu thiếu native-image executable, build có thể thất bại dù Java compile và AOT processing đã thành công.

### 16.2. Build image qua buildpacks

Spring Boot Maven Plugin có thể tạo OCI image qua buildpacks. Native image cần builder/configuration hỗ trợ và có thể yêu cầu environment variable hoặc buildpack option riêng.

Hãy đọc output để biết buildpack đang tạo JVM image hay native executable image. Đừng chỉ nhìn tên Docker image.

## 17. Native compilation thường nặng hơn JVM build

Native Image compiler phải phân tích reachability và tạo machine code cho một tập code lớn. So với compile Java thông thường, quá trình có thể:

- Mất nhiều phút hoặc lâu hơn tùy project.
- Dùng nhiều CPU và RAM.
- Nhạy với version của GraalVM/Native Build Tools.
- Tốn thời gian khi dependency graph lớn.
- Khó cache hơn một số task Java compile thông thường.

Điều này ảnh hưởng CI/CD: native build có thể cần runner nhiều RAM/CPU hơn và timeout phù hợp.

### 17.1. Tách job native build trong CI

Một pipeline có thể tách:

- Job JVM compile/unit tests.
- Job AOT/native compile.
- Job native smoke/integration tests.
- Job publish artifact/container image.

Nếu native build chỉ chạy ở release branch, cần bảo đảm các thay đổi dependency hoặc runtime hints vẫn được kiểm tra đủ sớm để không phát hiện lỗi native vào phút cuối.

### 17.2. Cache và reproducibility

Native build phụ thuộc toolchain, OS, architecture và metadata. Khi cache, phải bảo đảm cache key phản ánh các input quan trọng như JDK/GraalVM version, plugin, dependencies, build configuration và target platform.

Không tái sử dụng native executable build cho một target OS/architecture khác chỉ vì source revision giống nhau.

## 18. Chạy native executable

Sau khi native compilation thành công, build output chứa executable. Tên và vị trí phụ thuộc Gradle/Maven configuration.

Ví dụ minh họa:

~~~bash
./build/native/nativeCompile/demo-app
~~~

Trên Windows, file executable có thể có phần mở rộng phù hợp như `.exe` tùy toolchain/platform.

Chạy executable:

~~~bash
./demo-app
~~~

Nó khởi động application mà không cần gọi `java -jar`. Tuy nhiên, application vẫn cần các external dependencies như database, message broker, secret source, network và cấu hình runtime.

### 18.1. Binary phụ thuộc nền tảng

Native executable được build cho một hệ điều hành và kiến trúc cụ thể. Binary Linux x86_64 không mặc nhiên chạy trên Windows hoặc ARM64.

Cần build artifact cho đúng target environment hoặc dùng buildpack/container builder hỗ trợ target đó.

### 18.2. Thư viện hệ thống và libc

Executable có thể phụ thuộc các native libraries hoặc ABI của hệ thống đích. Container base image và runtime OS cần tương thích. Build trên một distribution rồi chạy trong image rất tối giản có thể gặp lỗi thiếu shared library.

Buildpacks giúp chuẩn hóa một phần môi trường image, nhưng vẫn phải kiểm tra runtime image thực tế.

## 19. Test ứng dụng AOT và native image

Một ứng dụng chạy được trên JVM chưa chắc chạy được trong native image. Test cần bao phủ cả hành vi thông thường và những đường đi dùng reflection/resources/proxies.

### 19.1. Unit tests trên JVM vẫn cần thiết

Unit test logic độc lập thường tiếp tục chạy trên JVM nhanh và thuận tiện. Không cần biến mọi unit test thành native test.

~~~java
@Test
void calculatesDiscount() {
    assertThat(calculator.discount(1_000, 10))
            .isEqualTo(900);
}
~~~

Các test này kiểm tra business logic nhưng không phát hiện tất cả native metadata issues.

### 19.2. Test Spring AOT processing

AOT processing có thể phát hiện một số vấn đề khi phân tích configuration hoặc tạo generated code. Hãy đưa task AOT vào CI ở mức phù hợp, đặc biệt khi application có nhiều conditional configurations và custom runtime hints.

### 19.3. Test native executable

Các tình huống cần chạy native:

- Jackson deserialize DTO.
- Reflection-based mapper.
- Validation annotations.
- JDK proxy/AOP.
- Resource loading.
- Serialization.
- ServiceLoader hoặc plugin registration.
- Database driver và messaging client.
- Startup/shutdown lifecycle.
- Security configuration và filter chain.

Nếu chỉ chạy JVM unit tests, bạn chưa kiểm tra những khác biệt do closed-world analysis.

### 19.4. Native tests

GraalVM Native Build Tools hỗ trợ các luồng build/test native tùy plugin/version. Trong Gradle, project có thể có task native test khi plugin và test configuration được thiết lập. Trong Maven, có thể cấu hình native test goals tương ứng.

Tên task/goal và điều kiện hỗ trợ thay đổi theo phiên bản plugin. Hãy xác nhận trong task list và documentation thay vì giả định mọi project đều có cùng task.

## 20. Kiểm tra RuntimeHints bằng test

Spring Framework có hỗ trợ kiểm tra runtime hints bằng test utilities. Một test có thể tạo registry, gọi registrar và xác nhận hint cần thiết đã được đăng ký.

Ví dụ khái niệm:

~~~java
class PaymentRuntimeHintsTests {

    @Test
    void registersPaymentRequestReflection() {
        RuntimeHints hints = new RuntimeHints();

        new PaymentRuntimeHints().registerHints(
                hints,
                getClass().getClassLoader()
        );

        RuntimeHintsPredicates.reflection()
                .onType(PaymentRequest.class)
                .test(hints);
    }
}
~~~

Tên utility và predicate cụ thể cần khớp với Spring Framework version của project. Ví dụ cho thấy mục tiêu của test: xác nhận hint được đăng ký, không phải tự chứng minh native executable hoạt động.

### 20.1. Hint registration test chưa đủ

Một test kiểm tra registry có chứa hint không chứng minh:

- Native compiler đã nhận metadata.
- Resource thực sự có trong image.
- Third-party library không cần thêm hint khác.
- Nhánh code production đã được thực thi.
- Binary chạy được trên target OS.

Vẫn cần native build và test runtime ở những luồng có rủi ro.

## 21. AOT/native và Spring testing

Spring test context có thể sử dụng cấu hình và bean graph khác application production. Một số test framework integrations cần AOT processing riêng để tạo context initializer phù hợp.

Gradle/Maven có thể cung cấp các task/goals cho test AOT, nhưng không nên mặc định rằng chạy `test` thông thường đã thực hiện native test.

Hãy xác định:

- Unit test nào chỉ cần JVM.
- Integration test nào cần Spring AOT test processing.
- Test nào cần chạy trên native executable.
- Test nào cần database/container thật.
- Test nào cần target OS/architecture cụ thể.

Một test suite hợp lý thường kết hợp JVM tests nhanh và một nhóm native tests tập trung vào các dynamic features quan trọng.

## 22. Hạn chế của native image trong thiết kế ứng dụng

Native image phù hợp nhất khi application graph và các khả năng runtime có thể mô tả rõ ở build time. Một số thiết kế linh hoạt có thể cần điều chỉnh.

### 22.1. Plugin system nạp code sau deploy

Nếu ứng dụng cho phép copy một JAR plugin mới vào thư mục rồi tự nạp class mà không rebuild, mô hình closed-world gây khó khăn. Native executable không thể tự bổ sung bytecode tùy ý như một JVM process có classpath/plugin loader truyền thống.

Có thể:

- Chuyển plugin thành module đã biết và compile vào image.
- Gọi một external service để cung cấp functionality.
- Dùng JVM runtime cho phần cần dynamic loading.
- Tách plugin host thành process riêng.

### 22.2. Reflection dựa trên cấu hình không giới hạn

Nếu configuration chứa bất kỳ class name nào và ứng dụng dùng reflection để tạo class, việc đăng ký toàn bộ class có thể không khả thi. Hãy cân nhắc registry/allowlist các implementation đã biết.

### 22.3. Runtime-generated bytecode

Thư viện tạo class bằng ASM, Byte Buddy hoặc các cơ chế tương tự cần có hỗ trợ AOT/native phù hợp. Một số use case Spring được xử lý bằng generated code, nhưng không phải mọi runtime generator đều được framework chuyển đổi.

### 22.4. Scripting engines và dynamic languages

Các hệ thống chạy script tùy ý hoặc tải interpreter/runtime động có thể không phù hợp với native image, hoặc cần cấu hình phức tạp. Đánh giá workload trước khi quyết định.

### 22.5. Native library và JNI

Nếu dependency gọi native code, cần kiểm tra shared library có mặt trên target, architecture tương thích và JNI/native metadata được cấu hình. JVM build thành công không bảo đảm native link thành công.

## 23. Đánh đổi hiệu năng: startup, memory và throughput

Native image thường hấp dẫn nhờ startup nhanh và memory footprint thấp, nhưng không nên chỉ đo thời gian start.

| Chỉ số | Native image thường có lợi thế | Điểm cần cân nhắc |
| --- | --- | --- |
| Cold startup | Khởi động rất nhanh trong nhiều ứng dụng | Vẫn phụ thuộc external connections và initialization |
| Memory footprint | Thường thấp hơn trong nhiều workload | Heap/GC và allocation patterns vẫn ảnh hưởng |
| Throughput dài hạn | Có thể đủ tốt với workload ổn định | JVM JIT có thể đạt throughput cao hơn sau warm-up |
| Build duration | — | Native compile thường lâu và tốn tài nguyên |
| Artifact size | Có thể giảm dependency runtime cần phân phối | Binary vẫn có thể lớn do code/resources được giữ |
| Horizontal scale | Hữu ích khi scale-to-zero/scale-out nhanh | Cần cân đối build matrix và image distribution |

### 23.1. Cold start không phải toàn bộ hiệu năng

Một serverless function có thời gian sống ngắn có thể được lợi nhiều từ startup nhanh. Một service chạy liên tục nhiều ngày có thể ưu tiên throughput, profiling và JIT optimization.

### 23.2. Đo bằng workload thật

So sánh JVM và native image trong cùng điều kiện:

- Cùng version code và dependency.
- Cùng dataset và request mix.
- Cùng CPU/memory limits.
- Cùng cấu hình connection pool.
- Có đo cold startup và warm steady-state.
- Có đo p50/p95/p99 latency, throughput và memory.
- Có lặp nhiều lần để giảm ảnh hưởng noise.

Không lấy một lần chạy local làm kết luận production.

## 24. Khi nào nên chọn JVM, AOT hoặc native image?

| Tình huống | Hướng cân nhắc |
| --- | --- |
| Ứng dụng CRUD truyền thống, chạy dài hạn, không có startup constraint | JVM là lựa chọn đơn giản và trưởng thành |
| Muốn thử generated initialization nhưng giữ deployment hiện tại | AOT trên JVM |
| Serverless, scale-to-zero, CLI hoặc workload cần cold start nhanh | Native image đáng được benchmark |
| Nhiều plugin nạp tùy ý sau deploy | JVM thường linh hoạt hơn |
| Dependency chủ yếu không hỗ trợ native | JVM hoặc AOT trên JVM; đánh giá thay thế dependency trước |
| CI có giới hạn CPU/RAM/time | Cân nhắc chi phí native build và release cadence |
| Nhiều OS/architecture targets | Tính chi phí build artifact theo từng target |
| Throughput dài hạn là KPI chính | So sánh native và JVM JIT bằng benchmark thực tế |

Một lựa chọn thực tế có thể là chỉ build native image cho một số service cần cold start, còn phần còn lại tiếp tục dùng JVM.

## 25. Docker và native image

JVM application thường được đóng gói trong image có JRE/JDK hoặc dùng layered JAR với runtime image phù hợp.

Native image có thể được đóng gói trong image nhỏ hơn vì không cần JVM runtime đầy đủ. Tuy nhiên, nó vẫn có thể cần libc, CA certificates, timezone data, DNS support và các thư viện hệ thống khác.

### 25.1. Buildpacks

Spring Boot plugin tích hợp Cloud Native Buildpacks để tạo OCI images. Buildpacks có thể chọn cách build JVM hoặc native tùy builder và environment.

Lợi ích:

- Chuẩn hóa quá trình build container.
- Tạo image theo stack/base image tương thích.
- Quản lý layer và runtime dependencies.
- Hỗ trợ quy trình native build nếu builder có khả năng tương ứng.

Không nên giả định mọi buildpack builder đều có native compiler. Hãy kiểm tra builder capabilities và log.

### 25.2. Build trên target platform

Nếu production chạy Linux ARM64, native binary cần được build cho target đó. Build Linux x86_64 rồi copy binary sang ARM64 không hoạt động chỉ vì cả hai đều dùng Linux.

Dùng native build runner hoặc cross-compilation workflow được hỗ trợ, và test artifact trên target architecture.

### 25.3. Runtime configuration vẫn cần được cung cấp

Native executable vẫn đọc environment variables, external configuration và secrets theo cách ứng dụng được thiết kế. Không nên nhúng production credentials vào binary hoặc build layers.

## 26. Troubleshooting các lỗi AOT/native thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| JVM chạy nhưng native build báo reflection warning/error | Thiếu metadata cho class/member truy cập động | Xác định call path và thêm runtime hints phù hợp |
| Native build thành công nhưng runtime báo class không tồn tại | Class không reachable/không được đưa vào image | Kiểm tra dynamic loading và reflection hints |
| Template/JSON/schema không tìm thấy | Resource chưa được include | Đăng ký resource pattern và test resource access |
| Không tạo được proxy | Thiếu proxy metadata hoặc runtime generator không hỗ trợ | Đăng ký JDK proxy hints hoặc thay integration |
| JSON binding thất bại | DTO/member metadata chưa đủ | Dùng binding hints và test serialization/deserialization |
| Bean khác giữa JVM AOT và native | AOT build-time conditions/profile khác runtime | Kiểm tra active profiles và build-time properties |
| Native compile hết RAM | Project lớn hoặc runner thiếu tài nguyên | Tăng tài nguyên, tối ưu build job, giảm scope metadata |
| Build native rất lâu | Reachability graph/dependencies lớn | Cache hợp lý, tối ưu dependencies và phân tách pipeline |
| Native executable không chạy trên host khác | OS/CPU/ABI không tương thích | Build cho đúng target và kiểm tra shared libraries |
| Giá trị static bị sai trong production | Class initialization ở build time | Tránh static side effects; điều chỉnh init policy |
| Thư viện bên thứ ba không tương thích | Thiếu reachability metadata hoặc dynamic behavior | Kiểm tra support/version hoặc thay thư viện |
| AOT task không được tìm thấy | Plugin/version/build config không phù hợp | Kiểm tra Spring Boot plugin và Native Build Tools |
| JVM test pass nhưng native test fail | Khác biệt reflection/resource/proxy/runtime | Thêm native-focused tests và hints chính xác |

### 26.1. Quy trình điều tra

1. Xác định lỗi xuất hiện ở AOT processing, native compilation hay native runtime.
2. Đọc warning đầu tiên có ý nghĩa, không chỉ dòng build failure cuối cùng.
3. Xác định class/resource/proxy nào được truy cập động.
4. Kiểm tra dependency đã cung cấp reachability metadata chưa.
5. Thêm hint nhỏ nhất có thể.
6. Rebuild native executable.
7. Chạy test đúng nhánh code gây lỗi.
8. Xác nhận artifact trên target OS/architecture.

Không thêm metadata rộng cho cả package chỉ để làm warning biến mất; điều đó có thể che giấu một thiết kế dynamic không phù hợp.

## 27. Một ví dụ end-to-end ở mức khái niệm

Giả sử service payment đọc một DTO từ JSON và tải một email template từ classpath.

DTO:

~~~java
public record PaymentRequest(
        String orderId,
        BigDecimal amount
) {
}
~~~

Template:

~~~text
src/main/resources/templates/payment/receipt.html
~~~

Configuration đăng ký hints:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PaymentRuntimeHints.class)
public class PaymentConfiguration {
}
~~~

Registrar:

~~~java
public class PaymentRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.resources().registerPattern(
                "templates/payment/*.html"
        );
    }
}
~~~

DTO binding có thể được khai báo bằng `@RegisterReflectionForBinding` khi integration cần reflection metadata cho type.

Quy trình:

1. Compile application Java.
2. Spring AOT phân tích configuration và thu thập hints.
3. Generated code/resources được tạo.
4. Native Image compiler phân tích reachable code và metadata.
5. Native executable được tạo cho target platform.
6. Chạy executable và gửi request có JSON body.
7. Xác nhận DTO được bind và template được đọc.
8. Chạy regression test trên native artifact.

Ví dụ này minh họa rằng **AOT hints là một phần của hợp đồng build/runtime**. Nếu bỏ resource hint hoặc binding hint trong một use case cần chúng, ứng dụng có thể chạy JVM nhưng lỗi native.

## 28. Chính sách phát triển ứng dụng sẵn sàng cho AOT

Ngay cả khi chưa quyết định dùng native image, một số thói quen thiết kế giúp ứng dụng dễ chuyển đổi:

- Ưu tiên dependency injection và configuration tường minh.
- Tránh reflection dựa trên class name tùy ý khi không cần.
- Hạn chế runtime bytecode generation không có native support.
- Dùng classpath resource APIs thay vì giả định resource là file vật lý.
- Giữ static initializers không có side effects phụ thuộc môi trường.
- Chọn thư viện có native support/reachability metadata khi native image là mục tiêu.
- Đăng ký hints ở module sở hữu type/resource/proxy.
- Viết integration tests cho các đường binding, serialization và resource loading.
- Không bake secret hoặc runtime environment vào AOT/native build.
- Kiểm tra active profiles và condition values trong AOT processing.
- Tách native build job khỏi JVM build nếu tài nguyên và thời gian khác nhau.
- Build cho đúng OS/architecture của deployment target.

Không cần hy sinh kiến trúc ứng dụng để chạy native bằng mọi giá. Nếu một tính năng cốt lõi dựa vào dynamic loading không phù hợp closed-world model, JVM có thể là lựa chọn kỹ thuật đúng hơn.

## 29. Những ngộ nhận thường gặp

### 29.1. “AOT và native image là một”

Không đúng. AOT xử lý application trước runtime và tạo code/hints. Native Image compiler dùng output đó để tạo executable native. AOT-generated application vẫn có thể chạy trên JVM.

### 29.2. “Native image không còn cần runtime configuration”

Không đúng. Application vẫn cần database URL, credentials, external services, port và các giá trị vận hành. Chỉ có JVM runtime không còn là cách khởi chạy chính.

### 29.3. “Thêm một reflection hint là mọi lỗi native biến mất”

Không đúng. Có thể thiếu resource, proxy, serialization metadata hoặc dependency không tương thích. Phải xác định đúng thao tác động gây lỗi.

### 29.4. “Nếu build native thành công thì ứng dụng chắc chắn hoạt động”

Không đúng. Một nhánh runtime có thể chưa được thực thi trong build hoặc test. Native executable vẫn cần integration/smoke tests.

### 29.5. “Native image luôn nhanh hơn JVM”

Không đúng cho mọi chỉ số. Native image thường có lợi thế startup và memory trong nhiều trường hợp; JVM JIT có thể đạt throughput cao hơn ở workload dài hạn sau warm-up. Cần benchmark.

### 29.6. “Binary native chạy trên mọi máy”

Không đúng. Binary phụ thuộc OS, CPU architecture và các native libraries/ABI cần thiết.

### 29.7. “Mọi thư viện Java đều tương thích native”

Không đúng. Thư viện có reflection, runtime code generation, dynamic loading hoặc JNI có thể cần metadata/integration bổ sung.

### 29.8. “AOT loại bỏ mọi reflection”

Không đúng. AOT giảm một số thao tác động và khai báo metadata cho những thao tác vẫn cần. Reflection vẫn có thể tồn tại nếu được hỗ trợ và khai báo đúng.

## 30. Bài tập thực hành

### Bài tập 1 — Phân biệt ba khái niệm

Vẽ sơ đồ cho một Spring Boot app chạy JAR trên JVM, chạy AOT-generated application trên JVM và chạy native executable. Ghi rõ compiler và runtime nào tham gia mỗi luồng.

### Bài tập 2 — Tìm task AOT

Trong một Gradle Spring Boot project, kiểm tra task list và chạy `processAot`. Quan sát generated sources/resources và giải thích vì sao task này chưa đồng nghĩa đã có native binary.

### Bài tập 3 — Tạo native executable

Cấu hình GraalVM Native Build Tools plugin tương thích với project, chạy `nativeCompile` và xác định executable được tạo ở đâu. Ghi lại OS/architecture và toolchain version.

### Bài tập 4 — Reflection hint

Tạo một DTO được khởi tạo qua reflection từ class name. Chạy JVM và native. Nếu native cần metadata, đăng ký đúng constructor/member cần thiết rồi kiểm tra lại.

### Bài tập 5 — Binding hint

Tạo DTO được Jackson bind từ JSON. Dùng `@RegisterReflectionForBinding` hoặc cơ chế phù hợp, sau đó test serialize/deserialize trên native executable.

### Bài tập 6 — Resource hint

Đọc template từ `src/main/resources`. Build native image và xác nhận resource có mặt. Thử loại bỏ hint để quan sát lỗi nếu use case cần hint, rồi đăng ký pattern hẹp phù hợp.

### Bài tập 7 — Proxy hint

Tạo một interface được dùng làm JDK dynamic proxy. Đăng ký proxy hint trong RuntimeHintsRegistrar và chạy test native. So sánh với class-based proxy use case.

### Bài tập 8 — Build-time conditions

Tạo configuration dùng `@ConditionalOnProperty`. Chạy AOT processing với property true và false, sau đó kiểm tra generated application. Giải thích vì sao property quyết định bean graph cần nhất quán với cách build/deploy.

### Bài tập 9 — Static initializer

Tạo class đọc environment variable trong static initializer. So sánh kết quả khi class được khởi tạo lúc build time và lúc runtime. Thiết kế lại để lấy giá trị trong bean/lifecycle runtime.

### Bài tập 10 — Third-party metadata

Chọn một dependency có reflection/resource behavior. Kiểm tra native support và reachability metadata. Xác định phần nào thư viện cung cấp sẵn và phần nào ứng dụng phải khai báo.

### Bài tập 11 — Benchmark JVM và native

Chạy cùng workload trên JVM và native image. Đo cold startup, memory, throughput và p95 latency. Dùng cùng resource limits và dataset, sau đó đưa ra lựa chọn dựa trên KPI.

### Bài tập 12 — Native smoke test

Tạo native executable, chạy trên đúng OS/architecture mục tiêu, kết nối dependency test và gọi một API. Kiểm tra serialization, resource loading, logging và graceful shutdown.

## 31. Tài liệu tham khảo

- [Spring Boot 3.3 — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/3.3/reference/packaging/aot.html)
- [Spring Framework — AOT Processing và Runtime Hints](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [GraalVM Native Image — Overview](https://www.graalvm.org/latest/reference-manual/native-image/)
- [GraalVM Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)

## 32. Ghi nhớ

**AOT processing, runtime hints và native image là ba phần liên quan của một quy trình, nhưng có vai trò khác nhau.** Spring AOT phân tích cấu hình ứng dụng trong build time và sinh code/resources. Runtime hints khai báo các khả năng động cần được giữ lại, như reflection, resource access, proxy và serialization. GraalVM Native Image compiler sử dụng application cùng metadata để tạo executable native theo nền tảng đích.

AOT có thể được dùng ngay cả khi ứng dụng vẫn chạy trên JVM. Native image thường giúp cold startup và memory footprint trong nhiều workload, nhưng đổi lại build lâu hơn, yêu cầu toolchain/platform cụ thể và hạn chế một số kiểu dynamic loading, reflection hoặc runtime bytecode generation.

Khi chuẩn bị native image, hãy ưu tiên dependency có native support, đăng ký hints tối thiểu cho các thao tác động thực sự cần thiết, kiểm tra điều kiện configuration được đánh giá ở build time và tránh static initialization phụ thuộc môi trường. Chạy unit tests trên JVM vẫn hữu ích, nhưng cần thêm native build, native-focused integration tests và smoke test trên đúng OS/architecture.

Không chọn native chỉ vì binary trông gọn hoặc startup nhanh trong một lần chạy. Hãy đo cold start, memory, throughput, latency, chi phí CI và độ phức tạp vận hành trên workload thực tế.
