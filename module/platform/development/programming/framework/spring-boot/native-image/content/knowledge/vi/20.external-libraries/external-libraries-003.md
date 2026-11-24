# Metadata đi kèm JAR và hints do Spring integration cung cấp

Một thư viện Java có thể chạy bình thường trên JVM nhưng thiếu thông tin cần thiết khi ứng dụng được biên dịch thành **GraalVM Native Image**. Các framework thường truy cập class, method, resource, serialization type hoặc JDK proxy bằng những cách mà phân tích tĩnh không thể suy ra đầy đủ. Thư viện tương thích native cần cung cấp metadata để trình biên dịch biết những thành phần động nào phải được giữ lại.

Có hai cách phổ biến để nhà phát triển thư viện cung cấp thông tin đó: **đóng gói reachability metadata ngay trong JAR**, hoặc cung cấp một **Spring integration** đóng góp `RuntimeHints` trong quá trình Spring AOT. Ngoài ra, GraalVM duy trì một repository metadata cộng đồng cho nhiều thư viện bên thứ ba chưa tự đóng gói metadata. Các cơ chế này có thể bổ trợ nhau, nhưng có nguồn gốc, phạm vi và thời điểm được nạp khác nhau.

Bài học này hướng dẫn đọc cấu trúc metadata trong JAR, sử dụng GraalVM Reachability Metadata Repository với Gradle/Maven, viết `RuntimeHintsRegistrar` cho Spring, kiểm thử hints và xử lý các trường hợp thiếu hoặc trùng metadata.

## 1. Vì sao thư viện bên ngoài cần cung cấp metadata?

GraalVM Native Image phân tích tĩnh các đường gọi từ entry point để quyết định class, method và resource nào cần đưa vào executable. Khi thư viện thực hiện truy cập động dựa trên dữ liệu chỉ có lúc runtime, compiler có thể không biết đích cần giữ lại.

Ví dụ một SDK thanh toán:

~~~java
public final class PaymentCodec {

    public PaymentRequest decode(String payload)
            throws ReflectiveOperationException {

        Class<?> type = Class.forName(
            "com.acme.payment.model.PaymentRequest"
        );

        Constructor<?> constructor = type.getDeclaredConstructor();
        Object request = constructor.newInstance();

        // Phần giải mã payload được rút gọn để minh họa.
        return (PaymentRequest) request;
    }
}
~~~

Trên JVM, class loader có thể tìm class theo tên chuỗi. Với Native Image, class và constructor cần được nhận diện khi build. Nếu compiler không thể suy ra đường reflection này, ứng dụng có thể gặp lỗi thiếu registration khi chạy native.

Một thư viện bên ngoài thường là nơi hiểu rõ nhất:

- Class nào được nạp động.
- Constructor, method hoặc field nào được gọi bằng reflection.
- Resource nào được đọc theo tên hoặc pattern.
- Interface nào được đưa vào JDK dynamic proxy.
- Kiểu nào được serialize/deserialize bằng cơ chế động.
- Native/JNI entry nào cần metadata.

Vì vậy, **nhà cung cấp thư viện nên đóng gói metadata gần với code thực hiện dynamic access**. Ứng dụng sử dụng thư viện không phải tự đoán mọi chi tiết nội bộ hoặc sao chép metadata từ nhiều nơi.

## 2. Ba nguồn metadata thường gặp

Trong một ứng dụng Spring Boot Native Image, metadata có thể đến từ ba nguồn:

| Nguồn | Ai cung cấp? | Nơi lưu | Khi nào được dùng? |
|---|---|---|---|
| Metadata đóng trong JAR | Nhà phát triển thư viện | `META-INF/native-image/...` bên trong JAR | Native Image đọc từ classpath khi build |
| GraalVM Reachability Metadata Repository | Cộng đồng GraalVM và các nhóm duy trì thư viện | Repository riêng, tra theo tọa độ dependency và version | Native Build Tools tải/nạp trong native build |
| Spring `RuntimeHints` | Spring Framework, Spring Boot hoặc module integration của thư viện | Java code/annotation/`META-INF/spring/aot.factories` | Spring AOT gọi registrar và xuất metadata cho native build |

Một số thư viện có thể đồng thời có metadata trong JAR và entry trong repository cộng đồng. Một Spring integration cũng có thể đăng ký hints cho cùng thư viện. Khi đó cần hiểu từng entry có bổ sung hay lặp lại nhau, tránh mở quá rộng các thành viên reflection.

**Không nên mặc định chỉ có một nguồn duy nhất.** Hãy kiểm tra metadata thực tế được đưa vào native build, version của thư viện và integration đang dùng.

## 3. Metadata trực tiếp bên trong JAR

GraalVM Native Image tìm reachability metadata trên classpath. Với schema hiện hành, file chính là `reachability-metadata.json`, thường đặt dưới đường dẫn có namespace của thư viện:

~~~text
payment-sdk.jar
└── META-INF/
    └── native-image/
        └── com.acme/
            └── payment-sdk/
                └── reachability-metadata.json
~~~

Đường dẫn này gắn metadata với artifact, giúp tránh xung đột tên giữa nhiều thư viện. Khi JAR là dependency của ứng dụng và nằm trong classpath native build, metadata có thể được Native Image thu thập cùng các metadata khác.

Ví dụ nội dung tối giản:

~~~json
{
  "reflection": [
    {
      "type": "com.acme.payment.model.PaymentRequest",
      "allDeclaredConstructors": true,
      "methods": [
        {
          "name": "validate",
          "parameterTypes": []
        }
      ]
    }
  ],
  "resources": [
    {
      "glob": "com/acme/payment/schema/*.json"
    }
  ]
}
~~~

Ví dụ này yêu cầu giữ constructor được khai báo của `PaymentRequest`, method `validate()` và các resource schema phù hợp. Trong thư viện thực tế, hãy đăng ký đúng constructor/member cần dùng thay vì bật toàn bộ field, method và constructor cho mọi class.

Metadata hiện hành có thể mô tả reflection, JNI, resources, resource bundles, serialization, proxies và một số dynamic feature khác. Schema cụ thể thay đổi theo phiên bản GraalVM; cần đối chiếu schema mà toolchain đang sử dụng.

## 4. Metadata cũ và metadata hiện hành

Các dự án Native Image trước đây thường đóng gói nhiều file JSON riêng:

~~~text
META-INF/native-image/
├── reflect-config.json
├── resource-config.json
├── proxy-config.json
├── jni-config.json
└── serialization-config.json
~~~

Các phiên bản GraalVM mới hỗ trợ định dạng hợp nhất `reachability-metadata.json`. Tên file, schema và một số trường có thể khác giữa các thế hệ toolchain.

| Định dạng | Mục đích | Lưu ý |
|---|---|---|
| `reachability-metadata.json` | Schema hợp nhất cho dynamic features | Nên dùng theo tài liệu và schema của GraalVM mục tiêu |
| `reflect-config.json` | Reflection trong cấu hình cũ | Kiểm tra khả năng tương thích của GraalVM đang dùng |
| `resource-config.json` | Classpath resources trong cấu hình cũ | Có thể được thay bằng phần `resources` của schema mới |
| `proxy-config.json` | JDK dynamic proxy trong cấu hình cũ | Schema mới mô tả proxy trong metadata hợp nhất |
| `jni-config.json` | JNI access trong cấu hình cũ | Kiểm tra schema và hỗ trợ theo phiên bản |

Không đổi tên file cũ thành `reachability-metadata.json` rồi giữ nguyên nội dung. Đó là hai định dạng khác nhau. Nếu thư viện hỗ trợ nhiều phiên bản GraalVM, cần kiểm tra chiến lược đóng gói metadata tương thích và kiểm thử với các toolchain được công bố hỗ trợ.

## 5. Metadata trong JAR được Native Image nạp như thế nào?

Native Image đọc metadata từ các classpath entries khi build. Với ứng dụng Maven/Gradle, các dependency JAR nằm trên classpath native build có thể đóng góp metadata riêng của chúng.

Luồng tổng quát:

~~~mermaid
flowchart TD
    A["Ứng dụng Spring Boot"] --> B["Classpath khi native build"]
    C["payment-sdk.jar"] --> B
    D["json-library.jar"] --> B
    E["jdbc-driver.jar"] --> B
    B --> F["Tìm META-INF/native-image"]
    F --> G["Đọc reachability metadata"]
    H["Spring AOT RuntimeHints"] --> I["Metadata do AOT sinh"]
    G --> J["GraalVM reachability analysis"]
    I --> J
    J --> K["Native executable"]
~~~

Mỗi dependency có thể đóng góp metadata của chính nó. Native Image hợp nhất thông tin từ các nguồn phù hợp trong quá trình build.

Có một số điều cần kiểm tra:

- JAR thực sự nằm trên classpath của task native build.
- File metadata không bị bỏ khỏi artifact khi đóng gói.
- Đường dẫn nằm đúng dưới `META-INF/native-image`.
- Schema tương thích với GraalVM version.
- Class/member/resource được khai báo tồn tại trong artifact.
- Các dependency bắc cầu mà metadata tham chiếu cũng có mặt.
- Công cụ shading/relocation không ghi đè hoặc làm mất metadata.

**Một file metadata nằm trong source tree chưa đủ.** Cần xác minh file đã đi vào JAR cuối và JAR đó được dùng trong native build.

## 6. Đóng gói metadata khi phát triển thư viện

Nếu bạn phát triển `payment-sdk`, hãy đưa metadata vào resources của module:

~~~text
payment-sdk/
└── src/
    └── main/
        └── resources/
            └── META-INF/
                └── native-image/
                    └── com.acme/
                        └── payment-sdk/
                            └── reachability-metadata.json
~~~

Gradle hoặc Maven sẽ đóng gói file resource vào JAR như các file resource thông thường. Không cần người dùng thư viện tự copy metadata sang ứng dụng nếu JAR được đưa vào classpath native build.

Sau khi package, kiểm tra:

~~~bash
jar tf build/libs/payment-sdk.jar | grep META-INF/native-image
~~~

Với Maven:

~~~bash
jar tf target/payment-sdk.jar | grep META-INF/native-image
~~~

Có thể trích nội dung để xác minh:

~~~bash
unzip -p build/libs/payment-sdk.jar \
  META-INF/native-image/com.acme/payment-sdk/reachability-metadata.json
~~~

Trên Windows, `jar tf` vẫn dùng được nếu JDK đã nằm trong PATH; có thể dùng `jar xf` để giải nén vào thư mục tạm và đọc file JSON. Chỉ đọc artifact sau package mới chứng minh metadata thực sự được đóng gói.

## 7. Vì sao có GraalVM Reachability Metadata Repository?

Không phải thư viện nào cũng được thiết kế từ đầu cho Native Image. Một số thư viện phổ biến có dynamic access nhưng nhà phát triển chưa phát hành metadata trong JAR. Để giảm công việc lặp lại cho từng ứng dụng, cộng đồng duy trì **GraalVM Reachability Metadata Repository**.

Repository chứa metadata được quản lý theo tọa độ Maven của thư viện và các version đã được hỗ trợ. GraalVM Native Build Tools có thể tra repository này để lấy metadata cho dependency khi tạo native image.

Repository có vai trò:

- Bổ sung metadata cho thư viện chưa tự đóng gói.
- Chia sẻ cấu hình đã được kiểm tra giữa nhiều dự án.
- Theo dõi metadata theo version của artifact.
- Giảm việc mỗi ứng dụng phải tự tạo lại cùng một bộ hints.
- Tạo nơi báo cáo và đóng góp khi một dependency chưa có metadata hoặc metadata chưa đầy đủ.

Repository là nguồn metadata cộng đồng, **không phải bằng chứng rằng mọi phiên bản của mọi thư viện đều được hỗ trợ**. Cần kiểm tra đúng `groupId`, `artifactId` và version đang dùng.

## 8. Native Build Tools tự động sử dụng repository

GraalVM Native Build Tools cung cấp plugin Gradle và Maven. Các plugin tích hợp Reachability Metadata Repository để tìm metadata của các thư viện trong dependency graph.

Với Gradle, chạy:

~~~bash
./gradlew nativeCompile
~~~

Với Maven:

~~~bash
./mvnw -Pnative package
~~~

Tùy phiên bản plugin và cấu hình dự án, plugin có thể tự tải metadata repository đã chọn và áp dụng metadata trong native build. Hãy kiểm tra cấu hình plugin và log của phiên bản đang dùng, nhất là khi build trong môi trường offline, proxy hoặc CI không có quyền truy cập repository.

Một số dự án cần khóa version của GraalVM Native Build Tools và metadata repository để build tái lập. Không nên để việc nâng plugin hoặc thay repository version diễn ra ngoài kiểm soát, vì metadata mới có thể sửa hoặc thay đổi hành vi dynamic access.

Spring Boot không tự cung cấp toàn bộ hints cho mọi thư viện bên thứ ba. Spring Boot dựa vào GraalVM Reachability Metadata Repository và metadata do chính thư viện/integration cung cấp cho những trường hợp ngoài khả năng suy luận của Spring.

## 9. Kiểm tra dependency thiếu metadata với Gradle

Native Build Tools cung cấp task để liệt kê dependency chưa có metadata trong repository.

~~~bash
./gradlew listLibrariesMissingMetadata
~~~

Task này giúp xác định các direct external runtime dependencies chưa được repository hỗ trợ và có thể đưa ra báo cáo hoặc liên kết issue tương ứng, tùy phiên bản plugin.

Kết quả không có nghĩa tất cả đường dynamic access đều đã được test. Một thư viện có metadata vẫn có thể có code path chưa được bao phủ hoặc version mới có thay đổi hành vi.

Khi cần kiểm tra sâu:

1. Xem tọa độ dependency và version trong report.
2. Xác minh dependency có phải runtime dependency thực sự không.
3. Kiểm tra metadata có được plugin tải vào native build không.
4. Chạy native test với các chức năng mà thư viện cung cấp.
5. Nếu thiếu metadata, cân nhắc tự bổ sung tạm thời và đóng góp upstream.

Không tự động loại dependency khỏi report chỉ vì nó là thư viện phụ. Một dependency bắc cầu vẫn có thể thực hiện reflection hoặc truy cập resource động trong runtime.

## 10. Kiểm tra dependency thiếu metadata với Maven

Với GraalVM Maven plugin, có thể chạy:

~~~bash
./mvnw native:list-libraries-missing-metadata
~~~

Goal này quét các direct external runtime dependencies theo cách plugin hỗ trợ, đối chiếu với metadata repository và có thể ghi báo cáo JSON dưới thư mục `target/native`.

Khi đọc kết quả, cần phân biệt:

- Dependency chưa có metadata trong repository.
- Dependency đã có metadata nhưng code path cụ thể vẫn thiếu hint.
- Dependency không được dùng trong runtime artifact.
- Dependency chỉ phục vụ test hoặc build.
- Metadata có sẵn nhưng plugin chưa được cấu hình để sử dụng.

Nếu task báo thiếu metadata, không nhất thiết phải tự viết toàn bộ hints ngay lập tức. Trước hết kiểm tra release metadata, issue hiện có, native support của thư viện và cách tích hợp mà nhà cung cấp khuyến nghị.

## 11. Đưa metadata repository vào JAR để build ở nơi khác

Thông thường, metadata repository chỉ được dùng trong native build do Native Build Tools quản lý. Nhưng có tình huống ứng dụng được đóng gói thành JAR trước, sau đó một công cụ khác mới chuyển JAR thành native image, ví dụ Paketo Buildpacks hoặc pipeline do tổ chức tự xây dựng.

Trong trường hợp đó, có thể **copy metadata repository vào chính JAR** để công cụ downstream nhìn thấy metadata từ classpath.

Với Gradle, Native Build Tools cung cấp task `collectReachabilityMetadata`. Có thể nối đầu ra task vào JAR:

~~~groovy
tasks.named("jar") {
    from collectReachabilityMetadata
}
~~~

Task tải metadata vào thư mục build/native-reachability-metadata theo cấu trúc `META-INF/native-image/...`. Việc thêm đầu ra vào JAR giúp artifact tự mang theo metadata cần thiết cho bước native conversion bên ngoài.

Với Maven, GraalVM Native Build Tools cung cấp goal `add-reachability-metadata`. Có thể khai báo execution:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>add-reachability-metadata</id>
            <goals>
                <goal>add-reachability-metadata</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Goal này thường được gắn vào phase `generate-resources` theo cấu hình plugin. Kiểm tra lại hành vi với version Native Build Tools đang dùng.

**Không phải ứng dụng nào cũng cần copy repository metadata vào JAR.** Nếu native image được tạo trực tiếp bằng plugin đã tích hợp repository, plugin có thể dùng metadata mà không cần đóng gói lại trong application JAR.

## 12. Spring RuntimeHints là một nguồn khác

Spring Framework cung cấp API `RuntimeHints` để mô tả các dynamic access mà Spring AOT cần chuyển cho GraalVM.

Runtime hints có thể mô tả:

- Reflection: class, constructor, method và field.
- Resources: file hoặc pattern trong classpath.
- Serialization: kiểu dữ liệu Java serialization.
- JDK dynamic proxies: tập interface cần proxy.

Spring AOT thu thập hints khi xử lý `ApplicationContext` và xuất cấu hình native tương ứng. Điều này phù hợp khi thư viện tích hợp sâu với Spring và biết rõ những dynamic access cần thiết trong quá trình vận hành của chính component.

Ví dụ thư viện cần reflection cho request model, đọc schema và tạo proxy interface:

~~~java
public final class PaymentSdkRuntimeHints
        implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
            PaymentRequest.class,
            MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS
        );

        hints.resources().registerPattern(
            "com/acme/payment/schema/*.json"
        );

        hints.proxies().registerJdkProxy(
            PaymentGateway.class
        );
    }
}
~~~

Các import được lược bớt để tập trung vào API. Chọn đúng `MemberCategory` theo thao tác thực tế; nếu code chỉ đọc metadata hoặc chỉ gọi constructor, không nên mở toàn bộ thành viên.

## 13. Kích hoạt registrar bằng @ImportRuntimeHints

Một `RuntimeHintsRegistrar` chỉ được gọi khi Spring biết cách đăng ký nó. Cách khai báo phổ biến là dùng `@ImportRuntimeHints` trên component hoặc configuration liên quan:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PaymentSdkRuntimeHints.class)
class PaymentSdkNativeConfiguration {
}
~~~

Nếu thư viện cung cấp Spring Boot auto-configuration, configuration này có thể được đăng ký qua cơ chế auto-configuration của Spring Boot. Khi đó hints chỉ được đóng góp khi integration tương ứng được kích hoạt.

Một lựa chọn khác là đặt annotation gần component cần hints:

~~~java
@Component
@ImportRuntimeHints(PaymentSdkRuntimeHints.class)
class PaymentClient {
    // Các thao tác dynamic access của SDK.
}
~~~

Spring Framework khuyến nghị đặt `@ImportRuntimeHints` càng gần component cần hints càng tốt. Khi component không được đưa vào `BeanFactory`, hints gắn với nó cũng không cần được đóng góp. Cách này giúp hạn chế metadata thừa.

Không dùng registrar chung cho mọi tính năng nếu chỉ một module nhỏ cần một số resource hoặc reflection. Hãy chia hints theo component hoặc integration để dễ kiểm tra và bảo trì.

## 14. Đăng ký RuntimeHintsRegistrar qua META-INF/spring/aot.factories

Với thư viện muốn đăng ký registrar tĩnh, Spring hỗ trợ file:

~~~text
META-INF/spring/aot.factories
~~~

Nội dung ví dụ:

~~~properties
org.springframework.aot.hint.RuntimeHintsRegistrar=\
com.acme.payment.PaymentSdkRuntimeHints
~~~

Spring AOT tìm implementation được khai báo trong file này và gọi `registerHints` trong build time. Đây là cách phù hợp với thư viện hạ tầng muốn đóng góp hints mà không cần gắn registrar vào một bean cụ thể.

Cần lưu ý:

- File phải nằm trong resources và được đóng gói vào JAR.
- Tên interface và implementation phải đúng package.
- Nếu nhiều JAR cùng cung cấp file cùng đường dẫn, cần kiểm tra cơ chế merge resources của công cụ đóng gói.
- Registrar không nên phụ thuộc bean nghiệp vụ hoặc gọi dịch vụ ngoài trong quá trình đăng ký hints.
- Nếu hints chỉ cần khi một component cụ thể được dùng, `@ImportRuntimeHints` thường có phạm vi rõ hơn.

## 15. Nên đặt GraalVM metadata hay Spring hints ở đâu?

Lựa chọn phụ thuộc đối tượng sử dụng thư viện:

| Tình huống | Cách cung cấp nên cân nhắc |
|---|---|
| Thư viện Java thuần, không phụ thuộc Spring | Đóng gói GraalVM reachability metadata trong JAR |
| Thư viện có dynamic access dùng chung cho mọi framework | JAR metadata hoặc đóng góp vào GraalVM Reachability Metadata Repository |
| Thư viện có logic tích hợp Spring, cần biết component nào được đăng ký | Spring `RuntimeHintsRegistrar` và `@ImportRuntimeHints` |
| Spring Boot starter cung cấp auto-configuration | Registrar gắn với auto-configuration hoặc component tương ứng |
| Ứng dụng tự gọi reflection/resource động riêng | Hints trong chính ứng dụng |
| Dependency chưa có metadata upstream | Tạm bổ sung metadata có kiểm soát, kiểm thử và đóng góp upstream |
| JAR được chuyển native bởi buildpack/công cụ ngoài Native Build Tools | Đóng gói metadata cần thiết vào JAR để downstream đọc được |

Một thư viện có thể phát hành core JAR thuần Java cùng module `payment-sdk-spring` riêng. Core JAR mang GraalVM metadata dùng chung; module Spring cung cấp registrar và auto-configuration. Cách chia module này tránh bắt người dùng không dùng Spring phải kéo thêm dependency Spring chỉ để nhận hints.

Nếu cả JAR metadata và Spring hints cùng mô tả một thành viên, hãy kiểm tra chúng có thực sự trùng và có khác nhau về quyền truy cập hay không. Trùng lặp không phải lúc nào cũng gây lỗi, nhưng làm tăng khó khăn khi cập nhật và có thể vô tình mở rộng phạm vi metadata.

## 16. Kiểm thử RuntimeHintsRegistrar bằng RuntimeHintsPredicates

Spring cung cấp `RuntimeHintsPredicates` để kiểm tra registrar đã đóng góp đúng hints chưa. Đây là unit test nhanh, không cần biên dịch native image.

Ví dụ kiểm tra resource:

~~~java
class PaymentSdkRuntimeHintsTests {

    @Test
    void registersPaymentSchemaResources() {
        RuntimeHints hints = new RuntimeHints();

        new PaymentSdkRuntimeHints().registerHints(
            hints,
            getClass().getClassLoader()
        );

        assertThat(
            RuntimeHintsPredicates.resource()
                .forResource("com/acme/payment/schema/v1.json")
        ).accepts(hints);
    }
}
~~~

Có thể dùng predicate tương ứng cho reflection, serialization và proxy. Test nên kiểm tra chính xác class/member hoặc interface mà component cần, thay vì chỉ kiểm tra rằng `RuntimeHints` không rỗng.

Những test này xác nhận **registrar khai báo đúng thông tin**. Chúng chưa chứng minh native executable thực sự chạy hết các code path; vẫn cần native integration test.

## 17. RuntimeHints Agent và GraalVM Tracing Agent

Có hai công cụ thu thập dynamic access dễ bị nhầm:

| Công cụ | Mục đích | Cách sử dụng |
|---|---|---|
| Spring RuntimeHints Agent | Theo dõi lời gọi dynamic access trong test và hỗ trợ đối chiếu với hints do Spring cung cấp | Dùng module `org.springframework:spring-core-test` |
| GraalVM Native Image Tracing Agent | Quan sát reflection, proxy, JNI, resource và các dynamic feature khi ứng dụng chạy trên JVM | Chạy ứng dụng/test với `-agentlib:native-image-agent` |

Spring RuntimeHints Agent phù hợp để kiểm tra một thư viện Spring integration có đóng góp đủ hints cho các thao tác mà test thực hiện hay không. GraalVM Tracing Agent phù hợp để thu thập reachability metadata JSON cho Native Image từ các luồng ứng dụng đã chạy.

Ví dụ chạy JVM với GraalVM Tracing Agent:

~~~bash
java \
  -agentlib:native-image-agent=config-output-dir=target/native-agent-config \
  -jar target/application.jar
~~~

Sau khi chạy các luồng cần thiết và dừng ứng dụng, kiểm tra metadata trong thư mục output. Agent chỉ ghi nhận code path thực sự được thực thi. Nếu test không đi qua serializer, plugin, profile hoặc nhánh nghiệp vụ nào thì metadata cho nhánh đó có thể không được tạo.

**Không đưa nguyên output agent vào thư viện hoặc production mà chưa review.** Metadata agent có thể chứa entry dành cho test infrastructure, class không cần thiết hoặc thông tin phụ thuộc môi trường.

## 18. Kiểm soát version, điều kiện và phạm vi metadata

Metadata phải được kiểm thử cùng version thư viện và toolchain mà dự án hỗ trợ.

Một số nguyên tắc:

- Gắn metadata với đúng tọa độ và version artifact.
- Cập nhật metadata khi thư viện đổi class, method, resource hoặc cách triển khai.
- Dùng conditional metadata nếu schema và use case hỗ trợ, để chỉ bật entry khi type liên quan reachable.
- Không bật `allDeclaredMethods` hoặc `allDeclaredFields` trên cả package chỉ để làm hết lỗi.
- Không đăng ký class không có trong artifact với kỳ vọng metadata sẽ tự nạp class.
- Không coi metadata là cách cho phép nạp JAR plugin mới sau khi native executable đã build.
- Kiểm tra schema JSON theo phiên bản GraalVM mục tiêu.

Với metadata schema mới, entry có thể dùng điều kiện `typeReached` để giới hạn khi metadata có hiệu lực. Điều kiện này giúp giảm ảnh hưởng của metadata không cần thiết, nhưng cần hiểu đúng thời điểm type được xem là reached.

Một thay đổi trong library có thể làm metadata cũ không còn đúng. Vì vậy, nên chạy native tests khi nâng version dependency, đặc biệt với các thư viện serializer, ORM, HTTP client, logging, validation và driver.

## 19. Chẩn đoán khi metadata của thư viện không được áp dụng

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| JAR có metadata nhưng native build vẫn báo thiếu registration | JAR không nằm trên classpath native build hoặc sai đường dẫn | Kiểm tra nội dung JAR và classpath |
| Metadata JSON không được đọc | Sai tên file, sai thư mục hoặc schema không tương thích | Xác minh `META-INF/native-image` và schema |
| Hints Spring không xuất hiện | Registrar chưa được import hoặc đăng ký tĩnh | Kiểm tra `@ImportRuntimeHints`, `aot.factories` và component scan |
| Registrar chạy nhưng thiếu method | Member category hoặc signature chưa đúng | Đối chiếu thao tác thực tế và bổ sung hint hẹp |
| Repository không cung cấp metadata | Version dependency chưa có entry hoặc plugin chưa cấu hình repository | Chạy task kiểm tra missing metadata và xem report |
| Metadata có trong repository nhưng buildpack không thấy | Repository metadata chỉ được dùng trong plugin build; JAR chưa mang metadata | Dùng task collect/add metadata khi downstream cần JAR tự chứa |
| Sau khi nâng dependency mới xuất hiện lỗi | Metadata cũ không còn khớp implementation | Cập nhật repository/plugin hoặc metadata của thư viện |
| Native test chỉ lỗi ở profile khác | AOT/profile hoặc code path đó chưa được kiểm thử | Build đúng profile và chạy test native cho profile đó |
| File metadata bị mất trong shaded JAR | Công cụ đóng gói xử lý duplicate resource không đúng | Kiểm tra merge strategy và nội dung JAR cuối |

Để phát hiện thiếu registration sớm, có thể bật `--exact-reachability-metadata` khi build trên GraalVM hỗ trợ tùy chọn này, sau đó chạy native executable với `-XX:MissingRegistrationReportingMode=Warn`. Khi kiểm thử, chế độ `Exit` có thể giúp phát hiện trường hợp code bắt `Throwable` và vô tình che lỗi missing registration. Kiểm tra tài liệu phiên bản GraalVM trước khi dùng các cờ này.

## 20. Quy trình thực hành: đóng gói hints cho một thư viện Spring

Giả sử bạn phát triển thư viện `payment-sdk` có các yêu cầu:

- Đọc schema JSON từ classpath.
- Dùng reflection để tạo `PaymentRequest`.
- Tạo JDK proxy cho interface `PaymentGateway`.
- Được sử dụng trong ứng dụng Spring Boot Native Image.

### Bước 1 — Xác định dynamic access

Liệt kê class, constructor, method, resource và proxy cần thiết. Tách những gì có thể suy ra tĩnh khỏi những gì phụ thuộc runtime data.

### Bước 2 — Đóng gói GraalVM metadata trong core JAR

Tạo file:

~~~text
src/main/resources/META-INF/native-image/com.acme/payment-sdk/reachability-metadata.json
~~~

Đưa vào file các reflection/resource/proxy/serialization entries mà core SDK thực sự cần. Build JAR và xác minh bằng `jar tf`.

### Bước 3 — Tạo Spring integration module

Tạo `PaymentSdkRuntimeHints` implement `RuntimeHintsRegistrar`. Dùng `@ImportRuntimeHints` trên configuration/auto-configuration của module Spring để registrar chỉ được áp dụng khi integration được kích hoạt.

### Bước 4 — Kiểm thử hints

Dùng `RuntimeHintsPredicates` kiểm tra resource, reflection, serialization và proxy cần thiết. Nếu thư viện có nhiều dynamic access, bổ sung Spring RuntimeHints Agent trong test để phát hiện lời gọi chưa được hint.

### Bước 5 — Kiểm tra GraalVM repository

Chạy:

~~~bash
./gradlew listLibrariesMissingMetadata
~~~

hoặc:

~~~bash
./mvnw native:list-libraries-missing-metadata
~~~

Kiểm tra `payment-sdk` và các dependency bắc cầu. Nếu thư viện đã tự đóng gói metadata, vẫn cần xác minh plugin không bị cấu hình loại trừ.

### Bước 6 — Build và test native

~~~bash
./gradlew nativeCompile
~~~

hoặc:

~~~bash
./mvnw -Pnative package
~~~

Chạy executable và kiểm thử cả schema load, reflection tạo request, proxy invocation và các luồng serialization. Nếu buildpack hoặc hệ thống downstream nhận JAR thay vì classpath native build trực tiếp, hãy cân nhắc đóng gói metadata repository vào JAR bằng task/goal tương ứng.

### Bảng nghiệm thu

| Hạng mục | Bằng chứng |
|---|---|
| Metadata trong JAR | `jar tf` hiển thị đúng đường dẫn |
| JSON schema | Validate bằng schema tương ứng với GraalVM |
| Spring hints | Unit test `RuntimeHintsPredicates` pass |
| Registrar discovery | AOT log cho thấy registrar được gọi |
| Dependency metadata | Report missing metadata được xem xét |
| Native build | `nativeCompile` hoặc Maven native package thành công |
| Native runtime | Reflection, resource, proxy và serialization chạy được |
| Version compatibility | Ghi lại Spring, GraalVM, Native Build Tools và dependency versions |

## 21. Ghi nhớ

Metadata trong JAR giúp thư viện tự mô tả dynamic access mà Native Image cần, phù hợp với thư viện Java thuần hoặc các yêu cầu dùng chung nhiều framework. GraalVM Reachability Metadata Repository bổ sung metadata cộng đồng cho các dependency chưa tự đóng gói và có thể được Native Build Tools sử dụng tự động trong native build.

Spring `RuntimeHintsRegistrar` phù hợp với logic tích hợp Spring: registrar được phát hiện qua `@ImportRuntimeHints` hoặc `META-INF/spring/aot.factories`, sau đó Spring AOT chuyển hints thành cấu hình native. Hãy đặt hints gần component sử dụng chúng, kiểm tra bằng `RuntimeHintsPredicates` và test native trên các code path thực tế.

Khi phát hành thư viện, nên giữ core metadata và Spring integration ở đúng module, quản lý theo version, khai báo phạm vi tối thiểu và xác minh file thực sự có trong artifact. **Metadata chỉ mô tả dynamic access; nó không thay thế class/bytecode chưa được đóng gói và không bảo đảm một dependency chưa được kiểm thử sẽ tự động tương thích native.**

### Tài liệu tham khảo

- GraalVM — Reachability Metadata: https://www.graalvm.org/latest/reference-manual/native-image/metadata/
- GraalVM — Reachability Metadata Repository: https://github.com/oracle/graalvm-reachability-metadata
- GraalVM Native Build Tools — Gradle Plugin: https://graalvm.github.io/native-build-tools/latest/gradle-plugin
- GraalVM Native Build Tools — Maven Plugin: https://graalvm.github.io/native-build-tools/latest/maven-plugin.html
- Spring Framework — Ahead of Time Optimizations: https://docs.spring.io/spring-framework/reference/core/aot.html
- Spring Boot — Advanced Native Image Topics: https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html

Metadata schema, plugin task và API Spring có thể thay đổi theo phiên bản. Khi phát hành thư viện, hãy pin toolchain và kiểm tra tài liệu của đúng GraalVM, Spring Framework, Spring Boot và Native Build Tools version được hỗ trợ.
