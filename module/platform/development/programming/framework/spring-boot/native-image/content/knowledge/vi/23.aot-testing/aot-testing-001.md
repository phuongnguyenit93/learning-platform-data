# Chạy ứng dụng trên JVM với kết quả AOT đã được sinh

## 1. Vì sao cần chạy AOT trên JVM?

Trong module **SPRING_BOOT_NATIVE_IMAGE**, ứng dụng Spring Boot được xử lý bằng Spring AOT rồi biên dịch thành GraalVM Native Image. Trước khi kiểm tra executable native, có một bước trung gian rất hữu ích: **chạy chính ứng dụng trên JVM nhưng sử dụng mã và tài nguyên đã được Spring AOT sinh ra**.

Chạy theo cách này giúp kiểm tra:

- mã khởi tạo ApplicationContext do AOT sinh có thể được nạp và thực thi;
- bean definitions, injection, proxy và cấu hình được chuẩn bị đúng;
- runtime hints và tài nguyên AOT cần thiết có mặt trong artifact;
- ứng dụng hoạt động với cấu hình runtime dự kiến sau khi dùng AOT;
- khác biệt giữa khởi động Spring thông thường và khởi động bằng AOT có thể được phát hiện trước bước native compilation.

Đây là một bước kiểm thử riêng trong pipeline. Nó vẫn chạy trên JVM, do đó không chứng minh mọi reflection, JNI, resource hay thư viện native đều tương thích với GraalVM. Tuy vậy, nó giúp khoanh vùng lỗi AOT sớm hơn và giảm số lần phải chờ một native build dài để phát hiện lỗi cấu hình.

## 2. Spring AOT sinh ra những gì?

Trong quá trình AOT, Spring phân tích ApplicationContext của ứng dụng ở build time. Từ cấu trúc bean và các cấu hình có thể xác định, Spring sinh mã khởi tạo và metadata để runtime có thể tạo context hiệu quả hơn.

Các đầu ra thường gồm:

- mã Java được sinh để đăng ký bean definitions và khởi tạo context;
- bytecode được biên dịch từ mã AOT;
- tài nguyên/metadata mô tả initializer, reflection, proxy, resource và các truy cập động cần thiết;
- các cấu hình hỗ trợ quá trình Native Image phân tích reachability.

Tên thư mục và cách plugin lưu đầu ra phụ thuộc Spring Boot, Spring Framework, Maven/Gradle và Native Build Tools version. Không nên viết code ứng dụng phụ thuộc vào tên file generated nội bộ nếu không có API công khai yêu cầu điều đó.

Luồng tổng quát:

~~~mermaid
flowchart TB
    S["Source + dependencies + build environment"] --> A["Spring AOT processing"]
    A --> G["Generated sources, bytecode and resources"]
    G --> C["Compile and package AOT output"]
    C --> J["Run on JVM with spring.aot.enabled=true"]
    C --> N["GraalVM Native Image compilation"]
    J --> V["Verify AOT context on JVM"]
    N --> X["Run native executable"]
~~~

## 3. Bật AOT khi chạy JVM

Spring Boot cung cấp property:

~~~properties
spring.aot.enabled=true
~~~

Khi property này được bật, Spring sử dụng ApplicationContext initializer đã được sinh trong quá trình AOT để khởi tạo context. Nếu property không bật, ứng dụng thường đi theo đường khởi tạo Spring thông thường trên JVM.

Với executable JAR đã chứa AOT output, chạy:

~~~bash
java -Dspring.aot.enabled=true -jar target/billing-service.jar
~~~

Đặt system property trước `-jar` để nó có mặt ngay khi SpringApplication bắt đầu bootstrap. Có thể dùng biến môi trường tương ứng:

~~~bash
SPRING_AOT_ENABLED=true java -jar target/billing-service.jar
~~~

Trên Windows PowerShell:

~~~powershell
$env:SPRING_AOT_ENABLED = "true"
java -jar target\billing-service.jar
~~~

Nếu chạy qua IDE, đặt VM option `-Dspring.aot.enabled=true` cho đúng Run Configuration. Đừng chỉ thêm property sau khi ApplicationContext đã bắt đầu khởi tạo.

**Property này chỉ chọn đường khởi tạo AOT đã sinh.** Nó không tự chạy AOT processing, không tự tạo generated classes và không tự thêm chúng vào classpath. Build phải hoàn tất AOT processing, compile và packaging trước khi chạy.

## 4. Chuẩn bị artifact AOT trên Gradle

Spring Boot Gradle plugin cung cấp task AOT, thường có tên `processAot`. Native Build Tools và cấu hình Spring Boot plugin kết nối đầu ra đó với các bước compile/package cần thiết.

Kiểm tra các task hiện có:

~~~bash
./gradlew tasks --all
~~~

Chạy AOT processing:

~~~bash
./gradlew processAot
~~~

Sau đó compile/package theo task graph mà plugin của dự án cung cấp. Một số cấu hình có các task như `compileAotJava` và `processAotResources`; kiểm tra chúng trong task list và xác nhận đầu ra được đưa vào runtime classpath hoặc executable JAR:

~~~bash
./gradlew compileAotJava processAotResources bootJar
~~~

Nếu plugin version của dự án đã nối các task này vào `bootJar`, chỉ cần chạy task đóng gói theo cấu hình đó. Tránh gọi task không tồn tại hoặc tự thêm output generated hai lần.

Chạy JAR với AOT:

~~~bash
java -Dspring.aot.enabled=true -jar build/libs/billing-service.jar
~~~

### 4.1. Dùng bootRun

Có thể cấu hình `bootRun` để bật property:

~~~kotlin
tasks.named<org.springframework.boot.gradle.tasks.run.BootRun>("bootRun") {
    systemProperty("spring.aot.enabled", "true")
}
~~~

Tuy nhiên, `bootRun` phải có cả AOT generated classes và resources trên runtime classpath. Chỉ đặt system property mà không đưa AOT output vào classpath sẽ không tạo ra một lần chạy AOT hợp lệ. Nếu không chắc task wiring của plugin, hãy chạy executable JAR đã được đóng gói và xác minh AOT output nằm trong artifact.

## 5. Chuẩn bị artifact AOT trên Maven

Spring Boot Maven plugin cung cấp goal `process-aot`. Dự án cần cấu hình goal này trong lifecycle/profile dùng để tạo AOT assets và bảo đảm output được compile/package cùng ứng dụng.

Ví dụ khai báo execution trong `spring-boot-maven-plugin` nếu POM chưa có execution tương ứng:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>process-aot</id>
            <goals>
                <goal>process-aot</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Nếu parent/profile của dự án đã khai báo execution `process-aot`, không thêm bản thứ hai. Kiểm tra effective POM và lifecycle binding của plugin version đang dùng.

Chạy goal AOT theo cấu hình dự án:

~~~bash
./mvnw spring-boot:process-aot
~~~

Sau đó chạy lifecycle compile/package để đầu ra AOT được đưa vào artifact theo cấu hình plugin:

~~~bash
./mvnw package
~~~

Chạy executable JAR:

~~~bash
java -Dspring.aot.enabled=true -jar target/billing-service.jar
~~~

Tên profile, execution ID và vị trí output có thể khác trong từng dự án. Nếu dự án dùng profile `native`, chỉ kích hoạt profile đó khi nó thực sự được định nghĩa trong POM. Không giả định rằng `mvn test` mặc định đã chạy AOT processing.

## 6. Xác minh AOT output đã nằm trong runtime artifact

Trước khi chạy, hãy kiểm tra artifact thực sự chứa đầu ra được sinh. Việc task `processAot` kết thúc thành công chưa đủ nếu generated output chưa được compile hoặc chưa được đóng gói.

Với JAR:

~~~bash
jar tf target/billing-service.jar
~~~

Với Gradle, thay bằng đường dẫn JAR trong `build/libs`. Kiểm tra:

- generated AOT classes đã được compile và có trong artifact;
- metadata/initializer cần thiết được đóng gói;
- resource mà AOT hoặc ứng dụng cần vẫn tồn tại;
- không có hai bản generated output xung đột do packaging lặp.

Không nên phụ thuộc vào một tên generated class cụ thể trong test ứng dụng. Tên class nội bộ có thể đổi theo phiên bản Spring. Hãy xác minh thông qua việc khởi động ứng dụng với `spring.aot.enabled=true` và kiểm tra hành vi.

Nếu artifact thiếu AOT initializer, hãy kiểm tra task graph/lifecycle, source set generated, compile output và packaging configuration. Không chữa bằng cách tắt `spring.aot.enabled`; làm vậy chỉ chuyển ứng dụng về đường khởi tạo thường và không còn kiểm tra kết quả AOT.

## 7. Điều kiện build time và cấu hình runtime

Đây là khác biệt quan trọng nhất khi chạy ứng dụng AOT trên JVM.

Spring AOT xử lý ApplicationContext ở build time. Những điều kiện quyết định cấu trúc bean có thể được đánh giá khi đó, ví dụ:

- `@ConditionalOnClass`;
- `@ConditionalOnProperty`;
- `@Profile`;
- các điều kiện auto-configuration khác;
- bean definitions được đăng ký động trong quá trình refresh context.

Nếu điều kiện được đánh giá khi AOT processing, kết quả cấu trúc bean đã được phản ánh vào generated output. Thay đổi property ở runtime không tự làm Spring chạy lại toàn bộ quá trình phân tích và sinh bean graph.

Ngược lại, giá trị cấu hình được bind vào bean khi ứng dụng khởi động vẫn có thể đến từ runtime property sources, chẳng hạn endpoint, timeout, bucket, region hoặc thông tin kết nối. Cần phân biệt **giá trị của bean** với **điều kiện quyết định bean có tồn tại hay không**.

| Thay đổi | Có thể thay đổi khi chạy AOT trên JVM? | Giải thích |
| --- | --- | --- |
| `app.storage.endpoint` được bind vào bean đã tồn tại | Có | Binder đọc property source khi runtime |
| Timeout hoặc tên bucket của bean đã được đăng ký | Có | Đây là giá trị cấu hình runtime |
| Bật `@ConditionalOnProperty` để tạo thêm bean đã bị loại khi AOT | Không tự động | Điều kiện cấu trúc đã được xử lý lúc AOT |
| Thêm classpath dependency sau khi AOT | Không | Generated context không tự phân tích lại classpath |
| Đổi profile làm thay đổi bean definitions | Không an toàn nếu khác profile AOT | Profile condition đã tham gia quyết định cấu trúc |
| Thay secret được đọc từ runtime secret store | Có | Miễn là secret không được dùng làm build-time condition |

Vì vậy, build environment phải đại diện đúng cho cấu trúc ứng dụng dự kiến ở runtime. Nếu staging và production cần bean graph khác nhau do profile/condition, cần tạo AOT output riêng cho từng biến thể hoặc thiết kế tính năng sao cho khác biệt chỉ nằm ở giá trị runtime.

## 8. Ví dụ: chạy cùng một AOT artifact với hai cấu hình runtime

Giả sử dịch vụ có `StorageProperties`:

~~~java
@ConfigurationProperties(prefix = "app.storage")
public record StorageProperties(
    URI endpoint,
    String bucket,
    Duration connectTimeout
) {
}
~~~

Bean đã được đăng ký qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`. File mặc định có thể chứa giá trị phát triển:

~~~yaml
app:
  storage:
    endpoint: https://storage-dev.example.internal
    bucket: invoices-dev
    connect-timeout: 3s
~~~

Sau khi AOT processing và packaging, chạy cùng JAR với cấu hình staging:

~~~bash
APP_STORAGE_ENDPOINT=https://storage-staging.example.internal \
APP_STORAGE_BUCKET=invoices-staging \
APP_STORAGE_CONNECTTIMEOUT=5s \
java -Dspring.aot.enabled=true -jar target/billing-service.jar
~~~

Và chạy cùng JAR với cấu hình production:

~~~bash
APP_STORAGE_ENDPOINT=https://storage.example.internal \
APP_STORAGE_BUCKET=invoices \
APP_STORAGE_CONNECTTIMEOUT=8s \
java -Dspring.aot.enabled=true -jar target/billing-service.jar
~~~

Hai lần chạy có thể dùng các giá trị khác nhau vì properties bean vẫn được bind khi runtime. Điều này không có nghĩa có thể đổi classpath hoặc bật một bean đã bị loại trong quá trình AOT.

Không đưa password/token vào file cấu hình dùng cho AOT processing. Secret cần được cung cấp qua secret manager, environment hoặc config tree khi ứng dụng chạy.

## 9. Kiểm thử AOT trên JVM

Mục tiêu là xác nhận hành vi ứng dụng sau khi dùng generated initializer. Có thể chạy cùng một bộ smoke/integration test với hai chế độ:

1. JVM thông thường: không bật `spring.aot.enabled`.
2. JVM AOT: bật `spring.aot.enabled=true` và dùng artifact chứa generated output.

Ví dụ kiểm tra một endpoint:

~~~bash
java -jar target/billing-service.jar
~~~

Trong terminal khác:

~~~bash
curl -i http://localhost:8080/actuator/health
~~~

Dừng tiến trình rồi chạy AOT:

~~~bash
java -Dspring.aot.enabled=true -jar target/billing-service.jar
~~~

Gọi lại endpoint và các API nghiệp vụ cần thiết. Health endpoint chỉ chứng minh ứng dụng đã khởi động; nó không kiểm tra các đường binding, serializer, resource, provider hay lazy bean chưa được sử dụng. Hãy gọi ít nhất một request đại diện cho mỗi tích hợp quan trọng.

### 9.1. So sánh kết quả

| Hạng mục | JVM thường | JVM với AOT |
| --- | --- | --- |
| Cách khởi tạo context | Phân tích cấu hình và tạo bean theo runtime path thông thường | Dùng generated initializer và AOT assets |
| Runtime | JVM | JVM |
| Reflection/reachability | JVM reflection model | Vẫn là JVM, nhưng dùng cấu trúc AOT đã sinh |
| Bean conditions | Được đánh giá khi context khởi tạo | Điều kiện cấu trúc đã được đánh giá trong AOT |
| Native executable constraints | Không | Không |
| Mục tiêu kiểm tra | Baseline ứng dụng | Tính đúng đắn của generated AOT output |

Không kết luận AOT JVM nhanh hơn chỉ từ một lần chạy. Nếu cần benchmark, đo nhiều lần trong cùng điều kiện, tách thời gian build khỏi startup, kiểm soát JVM warm-up và ghi nhận heap/RSS. Mục tiêu chính của bước này là kiểm tra tính đúng đắn của AOT output.

## 10. Kiểm thử các thành phần dễ bị ảnh hưởng

### 10.1. Bean registration và dependency injection

Kiểm tra các bean quan trọng có tồn tại và dependency được inject đúng. Đặc biệt chú ý:

- bean được đăng ký qua `@Bean` method;
- bean từ auto-configuration;
- bean được tạo có điều kiện;
- factory bean và bean definition registrar tùy biến;
- bean được đăng ký bằng `BeanDefinitionRegistryPostProcessor`.

Các extension tự đăng ký bean trong runtime có thể không tương thích với mô hình AOT nếu chúng cần thay đổi bean graph sau thời điểm AOT xử lý. Khi đó, xem lại thiết kế hoặc bổ sung cơ chế AOT được Spring hỗ trợ.

### 10.2. Configuration properties

Kiểm tra properties bean được đăng ký, bind đúng kiểu và validation vẫn hoạt động. Thử override một giá trị bằng environment variable để xác nhận Binder lấy cấu hình runtime.

Nếu giá trị sai, phân biệt lỗi binding với lỗi condition đã được xử lý lúc build. Một property có thể bind đúng nhưng bean phụ thuộc `@ConditionalOnProperty` vẫn không xuất hiện vì điều kiện đã false khi AOT.

### 10.3. Reflection, proxy và resource

Chạy các luồng thực sự sử dụng:

- Jackson hoặc framework introspect DTO;
- proxy JDK/CGLIB;
- resource được tìm bằng tên động;
- service provider qua `ServiceLoader`;
- thư viện ngoài có reflection.

JVM AOT có thể phát hiện lỗi đăng ký bean hoặc generated initializer, nhưng JVM vẫn có reflection và classloader đầy đủ. Một test pass ở đây không chứng minh Native Image đã giữ mọi constructor, method, resource hay JNI entry point.

### 10.4. Profile và conditional configuration

Ghi lại profile và các property dùng trong AOT processing. Khi chạy, dùng cùng điều kiện cấu trúc đã được chọn. Nếu cần kiểm tra một profile khác, tạo một AOT processing run với profile đó và dùng output riêng.

Không dùng cùng thư mục generated output cho nhiều cấu hình AOT khác nhau nếu chúng có thể ghi đè lẫn nhau. Mỗi biến thể cần build output có thể nhận diện và tái lập.

## 11. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `spring.aot.enabled=true` nhưng không tìm thấy AOT initializer | AOT processing chưa chạy hoặc output không được đóng gói | Kiểm tra `processAot`/`process-aot`, compile và packaging |
| Chạy thường được nhưng chạy AOT không tạo đủ bean | Điều kiện bean được đánh giá với build environment khác | So sánh profile/property/classpath lúc AOT và runtime |
| Đổi environment variable nhưng bean không xuất hiện | Environment variable được dùng trong condition build time | Tách cấu trúc bean khỏi giá trị runtime hoặc build AOT riêng |
| `bootRun` không tìm thấy generated initializer | Runtime classpath chưa chứa AOT output | Kiểm tra task wiring; thử executable JAR đã đóng gói |
| AOT generated source không compile | Mã cấu hình động hoặc extension không tương thích AOT | Xem lỗi generated source và hỗ trợ AOT của extension |
| Test JVM AOT pass nhưng native lỗi reflection | JVM vẫn cho phép reflection động | Bổ sung reachability metadata đúng phạm vi và chạy native test |
| Resource có trên JVM nhưng thiếu trong native | Resource hints hoặc packaging native chưa đủ | Kiểm tra resource input, runtime hints và native executable |
| Profile staging hoạt động nhưng production thiếu bean | AOT output được tạo từ profile khác | Tạo AOT output cho cấu trúc profile tương ứng |
| Thời gian startup không giảm | Ứng dụng bị chi phối bởi I/O, network hoặc tác vụ runtime khác | Đo riêng startup và tìm chi phí thực tế trước khi tối ưu |

Khi điều tra, lưu lại build command, version Spring Boot/Framework, JDK và Native Build Tools, profile/property dùng trong AOT, cùng stack trace đã loại bỏ secret.

## 12. Quy trình thực hành từ source đến JVM AOT

Giả sử dịch vụ billing cần xác minh generated AOT context trước khi build native image.

**Bước 1 — kiểm tra cấu hình build**

- Xác nhận Spring Boot Maven/Gradle plugin tương thích với version dự án.
- Xác nhận AOT task/goal đã được cấu hình.
- Xác định profile, classpath và property ảnh hưởng bean conditions.

**Bước 2 — chạy test JVM thông thường**

~~~bash
./mvnw test
# Hoặc:
./gradlew test
~~~

Đây là baseline để so sánh với AOT runtime.

**Bước 3 — sinh AOT output**

Gradle:

~~~bash
./gradlew processAot
~~~

Maven:

~~~bash
./mvnw spring-boot:process-aot
~~~

**Bước 4 — compile và package AOT output**

Dùng task/lifecycle do plugin version của dự án cấu hình. Xác nhận generated source đã được compile và resources/metadata được đưa vào artifact.

**Bước 5 — chạy JVM với AOT**

~~~bash
java -Dspring.aot.enabled=true -jar target/billing-service.jar
~~~

Thay bằng đường dẫn JAR thực tế nếu dùng Gradle. Gọi health endpoint và các API đại diện cho binding, JSON, resource, proxy và thư viện ngoài.

**Bước 6 — chạy test với cấu hình runtime khác**

Override endpoint, bucket, timeout hoặc property không làm thay đổi bean graph. Xác nhận Binder nhận giá trị mới. Giữ profile và các condition cấu trúc khớp với lần AOT processing.

**Bước 7 — chuyển sang native build**

Khi JVM AOT pass, build native executable bằng Maven/Gradle theo cấu hình module. Tiếp tục chạy native contract test; JVM AOT không thay thế bước đó.

## 13. Checklist trước khi chuyển sang Native Image

- [ ] AOT processing đã chạy thành công.
- [ ] Generated source/bytecode/resources đã được compile và package.
- [ ] Artifact chứa AOT initializer/metadata cần thiết.
- [ ] Đã chạy với `spring.aot.enabled=true` trên JVM.
- [ ] Bean registration và dependency injection hoạt động.
- [ ] Profile/classpath/condition lúc runtime phù hợp với lần AOT processing.
- [ ] Configuration properties vẫn bind giá trị runtime đúng.
- [ ] Đã gọi các API nghiệp vụ, không chỉ health endpoint.
- [ ] Reflection, proxy, resource và ServiceLoader quan trọng đã được kiểm tra trên JVM AOT.
- [ ] Secret không được đưa vào build environment hoặc generated output.
- [ ] Đã ghi lại command, plugin version và cấu hình AOT để tái lập.
- [ ] Đã phân biệt rõ lỗi AOT JVM với lỗi chỉ xuất hiện trong Native Image.

**Ghi nhớ:** để chạy ứng dụng trên JVM bằng kết quả AOT, trước hết phải sinh, compile và đóng gói AOT output; sau đó bật `spring.aot.enabled=true` trước khi SpringApplication bootstrap. Các giá trị cấu hình thông thường vẫn có thể được bind ở runtime, trong khi những điều kiện quyết định bean graph đã được xử lý ở build time. Khi bước JVM AOT hoạt động, tiếp tục kiểm thử native executable để xác nhận reachability, resource, JNI và giới hạn closed-world.

## Tài liệu tham khảo

- [Spring Boot Reference — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/reference/packaging/aot.html): AOT processing, chạy ứng dụng trên JVM với AOT-generated code và cấu hình build.
- [Spring Boot Gradle Plugin — AOT tasks](https://docs.spring.io/spring-boot/gradle-plugin/aot.html): các task AOT và cách tích hợp với Gradle.
- [Spring Boot Maven Plugin — process-aot](https://docs.spring.io/spring-boot/maven-plugin/aot.html): goal xử lý AOT và cấu hình Maven.
- [Spring Framework — AOT Processing](https://docs.spring.io/spring-framework/reference/core/aot.html): generated application context, runtime hints và giới hạn AOT.
