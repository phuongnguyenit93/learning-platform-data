# GraalVM native image và điều kiện hỗ trợ của phiên bản thư viện

GraalVM Native Image biên dịch ứng dụng Java thành executable dành cho một hệ điều hành và kiến trúc CPU cụ thể. Ứng dụng native thường khởi động nhanh và dùng ít bộ nhớ hơn ứng dụng chạy trên JVM, nhưng cách biên dịch này yêu cầu xác định trước phần lớn code, class, resource, reflection và proxy cần thiết. Vì vậy, một thư viện chạy tốt trên JVM chưa chắc chạy đúng trong native image nếu thư viện dựa vào khả năng nạp class hoặc truy cập reflection tại runtime mà chưa cung cấp reachability metadata.

Với Spring Boot, Spring AOT xử lý một phần lớn công việc này khi build. springdoc-openapi có hỗ trợ GraalVM native image từ Spring Boot 3, nhưng vẫn cần chọn đúng dòng springdoc theo phiên bản Spring Boot, đặt annotation cấu hình đúng cách và kiểm thử chính executable native. Chỉ thấy native build thành công chưa đủ để kết luận endpoint OpenAPI và Swagger UI hoạt động.

Bài này giải thích điều kiện tương thích, cách Spring AOT và GraalVM xử lý ứng dụng, các điểm cần lưu ý khi dùng springdoc, quy trình build và kiểm thử native image, cùng cách đo hiệu năng để quyết định có nên triển khai native hay không.

## 1. Native Image khác ứng dụng chạy trên JVM như thế nào?

Ứng dụng JVM thường mang theo bytecode và chạy trên Java Virtual Machine. JVM có thể nạp class, tạo proxy, dùng reflection và đọc resource từ classpath trong lúc chương trình hoạt động. Native Image thực hiện phân tích tĩnh từ entry point ở build time rồi biên dịch phần code được xem là reachable thành executable.

| Tiêu chí | Chạy trên JVM | GraalVM Native Image |
| --- | --- | --- |
| Nạp class | Có thể nạp class trong runtime theo classpath | Classpath được cố định khi build |
| Reflection | Có thể khám phá class/member lúc chạy | Cần reachability metadata cho truy cập động |
| Resource classpath | Có thể đọc resource có trong JAR/classpath | Resource cần được nhận diện và đưa vào image |
| Dynamic proxy | Có thể tạo proxy trong runtime | Proxy cần được nhận diện và tạo ở build time |
| Khởi động | Có thể cần thời gian khởi tạo và JIT warm-up | Thường khởi động nhanh hơn |
| Tối ưu throughput | JIT có thể tối ưu theo hành vi thực tế khi chạy | Không có JIT warm-up như JVM thông thường |
| Build | Thường nhanh hơn | Native compilation thường lâu và tốn CPU/RAM hơn |
| Phân phối | Cần runtime Java phù hợp | Executable phụ thuộc OS/CPU và môi trường build |

Native Image dựa trên giả định closed-world: những thành phần cần thiết phải được biết khi build. Code không được xác định là reachable có thể bị loại khỏi executable. Điều này giúp tạo binary gọn hơn, nhưng làm lộ các phụ thuộc reflection, resource, serialization hoặc proxy vốn được JVM xử lý linh hoạt.

## 2. Spring AOT là phần bắt buộc trong native image

Spring Boot dùng Ahead-of-Time processing để chuẩn bị ApplicationContext trước khi GraalVM biên dịch. Spring AOT phân tích bean definitions, điều kiện cấu hình và các thành phần Spring đã đăng ký, sau đó tạo mã nguồn, bytecode và runtime hints.

Các file sinh ra thường nằm ở:

| Build tool | AOT generated sources | AOT generated resources |
| --- | --- | --- |
| Maven | target/spring-aot/main/sources | target/spring-aot/main/resources |
| Gradle | build/generated/aotSources | build/generated/aotResources |

Trong resources, Spring có thể tạo metadata dưới META-INF/native-image. Các hint thường mô tả:

- Reflection: class, constructor, field hoặc method được truy cập động.
- Resource: file cần đọc từ classpath.
- Serialization: kiểu dữ liệu cần serialize/deserialize theo cơ chế động.
- Proxy: interface hoặc class proxy cần tạo sẵn.
- JNI: thành phần Java được truy cập từ native code.

Spring AOT tự xử lý nhiều trường hợp phổ biến, chẳng hạn kiểu request/response của controller. Nếu thư viện hoặc code riêng sử dụng cơ chế động mà Spring không suy ra được, cần bổ sung runtime hints hoặc reachability metadata. Không nên thêm hint tràn lan trước khi có lỗi cụ thể, vì metadata quá rộng làm tăng kích thước và che khuất nguyên nhân thật.

## 3. Native image có giả định closed-world

Một số cấu hình Spring vốn được quyết định khi ứng dụng chạy trên JVM lại được quyết định khi AOT xử lý. Điều này ảnh hưởng đến bean definitions:

- @Profile và profile-specific configuration có giới hạn vì bean graph được chốt lúc build.
- @ConditionalOnProperty và các thuộc tính .enabled có thể ảnh hưởng việc tạo bean nên cần giá trị phù hợp tại build time.
- Không thể mong chờ thêm class vào classpath hoặc tạo một tập bean hoàn toàn mới sau khi native executable đã được build.
- Các cấu hình bật/tắt controller hoặc OpenAPI endpoint phải được tính đến trong AOT environment.

Ví dụ, nếu OpenAPI endpoint chỉ được tạo khi property springdoc.api-docs.enabled=true, giá trị dùng lúc AOT build phải cho phép endpoint đó tồn tại trong native image. Đổi property khi chạy executable không thể khôi phục một bean đã bị loại khỏi image ở build time.

Đối với nhiều môi trường triển khai, hãy phân biệt cấu hình thay đổi được ở runtime với điều kiện quyết định bean graph. Các giá trị như host, port hoặc credential thường có thể lấy từ environment khi chạy; sự tồn tại của bean và các nhánh cấu hình động cần được kiểm tra theo giới hạn AOT của phiên bản Spring Boot đang dùng.

## 4. Ma trận tương thích Spring Boot và springdoc-openapi

Phải chọn đúng major version của springdoc theo major version Spring Boot. Không nên chỉ nâng springdoc lên số mới nhất mà bỏ qua ma trận tương thích.

| Spring Boot | Dòng springdoc phù hợp | Ghi chú |
| --- | --- | --- |
| 4.1.x | 3.1.x đến 3.2.x | Theo ma trận tương thích hiện hành của springdoc |
| 4.0.x | 3.0.x | Dùng springdoc 3.x |
| 3.x | 2.x | Xem tài liệu springdoc v2 dành cho Boot 3 |
| 2.x và 1.x | 1.8.0 là dòng open-source cuối | Dòng cũ, đã kết thúc hỗ trợ open-source |

Ma trận chi tiết được cập nhật theo các bản phát hành. Trước khi nâng cấp, hãy xem FAQ/README của springdoc và chọn phiên bản đã được build/test với đúng dòng Spring Boot của dự án. Không suy luận rằng mọi bản 3.x đều tương thích với mọi bản 4.x.

Ví dụ, tài liệu springdoc hiện liệt kê Boot 4.1.x với springdoc 3.1.x–3.2.x và Boot 4.0.x với springdoc 3.0.x. Với Boot 3.x, dùng nhánh springdoc 2.x và tài liệu v2. Khi còn dùng Boot 2.x, cần xem xét nâng cấp nền tảng vì springdoc 1.8.0 đã là dòng cũ không còn hỗ trợ open-source.

## 5. Native image support của springdoc bắt đầu từ Spring Boot 3

springdoc FAQ ghi nhận hỗ trợ native được bổ sung cùng Spring Boot 3. Với ứng dụng Boot 3 hoặc Boot 4, native build đi theo Spring AOT và GraalVM Native Build Tools của hệ sinh thái Spring Boot hiện hành.

Không nhầm hướng dẫn native hiện tại với dự án Spring Native độc lập từng dùng trong giai đoạn trước Boot 3. Hãy dùng Native Image support tích hợp trong Spring Boot, Spring AOT và plugin native build tương thích với phiên bản Boot.

FAQ springdoc cũng lưu ý một trường hợp cụ thể: nếu đặt @OpenAPIDefinition hoặc @SecurityScheme trên một class chỉ chứa annotation, không có implementation hoặc vai trò cấu hình Spring, class đó có thể bị loại khi native compile. Hãy đặt các annotation này trên một class @Configuration để Spring nhận diện và AOT xử lý đúng.

## 6. Đặt OpenAPI annotation trên class cấu hình

Ví dụ cấu hình metadata và bearer security scheme:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@OpenAPIDefinition(
    info = @Info(
        title = "Order API",
        version = "1.0.0",
        description = "API quản lý đơn hàng"
    )
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class OpenApiConfiguration {
}
~~~

Class này là Spring configuration bean. Annotation OpenAPI được gắn vào một thành phần Spring có thể được phát hiện trong ApplicationContext và xử lý ở giai đoạn AOT.

Nếu class chứa annotation nằm ngoài component scan, native build không thể tự phát hiện nó. Hãy kiểm tra package của configuration class, cấu hình scan và test ApplicationContext với cùng cấu hình dùng để tạo native image.

## 7. Chọn đúng starter theo Web MVC, WebFlux và nhu cầu Swagger UI

springdoc có các starter riêng cho API description và giao diện tài liệu:

| Ứng dụng | Chỉ cần OpenAPI endpoint | Cần Swagger UI |
| --- | --- | --- |
| Spring MVC | springdoc-openapi-starter-webmvc-api | springdoc-openapi-starter-webmvc-ui |
| Spring WebFlux | springdoc-openapi-starter-webflux-api | springdoc-openapi-starter-webflux-ui |

Nếu chỉ dùng OpenAPI JSON/YAML trong CI hoặc cung cấp document cho gateway, starter API có thể là đủ. Nếu cần giao diện tương tác, dùng starter UI tương ứng với web stack.

Không trộn starter Web MVC và WebFlux một cách tùy tiện. Hãy dùng đúng web stack mà ứng dụng đang chạy và tránh kéo nhiều phiên bản swagger-core hoặc swagger-annotations khác nhau qua dependency transitives.

## 8. Đồng bộ dependency và tránh xung đột version

Khi native build thất bại, nguyên nhân có thể đến từ thư viện không tương thích, không chỉ từ GraalVM. Hãy kiểm tra:

- Spring Boot version và Spring Framework version.
- springdoc starter version.
- swagger-core và swagger-annotations version được resolve.
- Jackson modules và custom serializers.
- Native Build Tools plugin version.
- GraalVM JDK version và Java toolchain.
- Thư viện bên thứ ba có reachability metadata hay chưa.

Chạy dependency insight/tree để phát hiện nhiều version của swagger-core, Jackson hoặc Spring Framework cùng tồn tại. Dùng BOM/dependency management phù hợp và không tự ép một dependency con sang version khác nếu chưa kiểm tra ma trận tương thích.

Ví dụ Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Ví dụ Maven:

~~~bash
./mvnw dependency:tree
~~~

Sau khi thay đổi dependency, hãy chạy lại JVM tests, AOT processing và native build. Một build thành công trên JVM không chứng minh metadata của dependency mới đã đầy đủ.

## 9. Build native image bằng Maven

Spring Boot Maven plugin cung cấp AOT processing. Nếu dự án dùng spring-boot-starter-parent, profile native có thể giúp cấu hình process-aot, Native Build Tools và build image.

POM cần có Spring Boot Maven plugin và Native Build Tools Maven plugin trong module ứng dụng:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-maven-plugin</artifactId>
    </plugin>
    <plugin>
      <groupId>org.graalvm.buildtools</groupId>
      <artifactId>native-maven-plugin</artifactId>
    </plugin>
  </plugins>
</build>
~~~

Với cấu hình native profile do Spring Boot parent cung cấp, có thể bắt đầu bằng:

~~~bash
./mvnw -Pnative package
~~~

Nếu dự án tự quản lý plugin executions hoặc không dùng Spring Boot parent, hãy cấu hình process-aot và native goal theo tài liệu Spring Boot/Native Build Tools của đúng phiên bản. Profile native không tự thêm các plugin bị thiếu trong một POM tùy biến.

Một cách khác là dùng Cloud Native Buildpacks để tạo container image có native executable. Cách build này cần Docker daemon và builder phù hợp; đổi lại, pipeline có thể không cần cài GraalVM trực tiếp trên máy chạy build.

## 10. Build native image bằng Gradle

Với Gradle, thêm Native Build Tools plugin cùng Spring Boot plugin:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "4.1.2"
    id("org.graalvm.buildtools.native") version "1.1.14"
}
~~~

Ví dụ trên minh họa cấu trúc plugin. Hãy thay phiên bản bằng cặp Spring Boot, Gradle và Native Build Tools tương thích trong dự án. Không dùng số phiên bản ví dụ làm mặc định cho mọi dự án.

Khi plugin đã được cấu hình, task chính thường dùng là:

~~~bash
./gradlew nativeCompile
~~~

Sau khi build xong, chạy executable bằng nativeRun nếu task được plugin cung cấp hoặc chạy trực tiếp binary trong build/native/nativeCompile. Đường dẫn và tên file phụ thuộc tên project, OS và cấu hình binary.

Native Build Tools Gradle plugin yêu cầu GraalVM JDK có native-image. Có thể chọn toolchain hoặc cấu hình GRAALVM_HOME theo tài liệu plugin. Kiểm tra native-image --version trước khi chạy build.

## 11. Dùng đúng GraalVM và Native Build Tools version

Native build phụ thuộc nhiều hơn phiên bản Java thông thường. Cần kiểm tra:

1. Spring Boot version yêu cầu Java tối thiểu nào.
2. Phiên bản GraalVM Native Image được Spring Boot hỗ trợ.
3. Native Build Tools plugin version tương thích.
4. Gradle/Maven version được hỗ trợ.
5. OS và CPU architecture dùng để build binary.

Ví dụ, tài liệu Spring Boot 4.1.2 liệt kê GraalVM Community 25 và Native Build Tools 1.1.14 trong phần yêu cầu native image. Những con số này có thể thay đổi ở patch release hoặc dòng Boot mới hơn; luôn dùng System Requirements của đúng phiên bản đang triển khai.

Đừng chỉ dựa vào việc máy developer đã cài một GraalVM mới nhất. Một GraalVM quá mới hoặc quá cũ so với Spring Boot/Native Build Tools có thể gây lỗi build, thay đổi hành vi reachability hoặc làm CI không tái lập được.

## 12. Hiểu reachability metadata của thư viện

GraalVM thực hiện static analysis để xác định code nào được gọi trực tiếp. Các thao tác động như reflection, đọc resource theo tên, serialization hoặc tạo proxy có thể không được suy ra đầy đủ. Reachability metadata cung cấp thông tin để Native Image giữ lại những thành phần đó.

Metadata có thể đến từ:

- Spring AOT generated hints.
- Metadata đi kèm thư viện trong META-INF/native-image.
- GraalVM Reachability Metadata Repository được Native Build Tools tải về.
- RuntimeHints do ứng dụng tự đăng ký.
- Metadata JSON do nhóm phát triển bổ sung sau khi kiểm tra lỗi thực tế.

Các file JSON có thể mô tả reflection, resource, serialization, JNI và proxy. Không nên copy một reflect-config.json lớn từ dự án khác vì class, member và version dependency có thể khác.

## 13. Kiểm tra thư viện thiếu reachability metadata

Native Build Tools có lệnh liệt kê dependency thiếu metadata trong repository:

~~~bash
./gradlew listLibrariesMissingMetadata
~~~

Với Maven:

~~~bash
./mvnw native:list-libraries-missing-metadata
~~~

Kết quả này giúp nhận diện thư viện cần được xem xét thêm. Không có metadata trong repository không tự động có nghĩa thư viện chắc chắn không chạy được; code có thể không dùng tính năng động đó hoặc Spring AOT có thể đã tạo hint khác. Ngược lại, thư viện có metadata cũng chưa chứng minh mọi code path của ứng dụng đều được bao phủ.

Hãy kiểm tra runtime behavior bằng native executable và test các chức năng thực tế, đặc biệt các tính năng dùng reflection, custom serializer, plugin, classpath scanning hoặc resource động.

## 14. Bổ sung reflection hints cho kiểu dữ liệu cần binding

Spring AOT thường suy ra hint cho request/response type của controller. Nếu một kiểu dữ liệu được dùng qua reflection hoặc binding động mà AOT không phát hiện, có thể đăng ký thêm hint.

Ví dụ:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@RegisterReflectionForBinding({
    CreateOrderRequest.class,
    OrderResponse.class
})
class ApiNativeBindingHints {
}
~~~

Chỉ đăng ký các kiểu thực sự cần thiết. Annotation này hữu ích khi một kiểu được bind/serialize động mà đường đi tĩnh không đủ để Spring AOT suy ra. Không cần thêm hint cho mọi DTO theo thói quen nếu Spring đã tự tạo metadata.

Nếu thiếu resource hoặc proxy thay vì reflection, hãy dùng RuntimeHints API tương ứng. Đọc thông báo lỗi native image để xác định đúng loại hint cần bổ sung.

## 15. Bổ sung RuntimeHints khi thư viện cần resource hoặc proxy

Spring Framework cung cấp RuntimeHintsRegistrar để đăng ký reflection, resource, serialization và proxy. Ví dụ minh họa đăng ký một resource cụ thể:

~~~java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class ApiDocumentationHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.resources().registerPattern(
            "META-INF/example-api/banner.txt"
        );
    }
}
~~~

Đăng ký registrar qua @ImportRuntimeHints trên một configuration class hoặc theo cơ chế Spring Framework tương ứng. Ví dụ trên chỉ minh họa resource hint; thay pattern bằng đúng resource mà ứng dụng thực sự đọc.

Không đăng ký toàn bộ META-INF hoặc toàn bộ classpath nếu chỉ thiếu một file. Hint quá rộng có thể làm native image lớn hơn và che giấu việc thư viện đang phụ thuộc resource ngoài dự kiến.

## 16. Lưu ý đặc biệt cho OpenAPI annotation và Swagger UI

Khi dùng springdoc trong native image, hãy kiểm tra riêng các thành phần sau:

- Class cấu hình có @OpenAPIDefinition và @SecurityScheme phải được Spring phát hiện, nên khai báo @Configuration.
- Controller và functional route phải tồn tại trong bean graph tại thời điểm AOT.
- DTO, enum, generic wrapper và custom serializer phải được phản ánh đúng trong schema và response.
- Nếu cần Swagger UI, static resources của starter UI phải có trong native image.
- Nếu chỉ cần JSON/YAML, có thể dùng starter API để giảm thành phần UI không cần thiết.
- GroupedOpenApi bean và OpenAPI customizer phải được đăng ký khi AOT xử lý.
- Các điều kiện springdoc.api-docs.enabled, packages-to-scan và paths-to-match phải đúng ở build time.

Một native executable có thể khởi động thành công nhưng thiếu OpenAPI endpoint, thiếu group hoặc không render được Swagger UI. Vì vậy, hãy kiểm tra từng endpoint sau khi chạy binary.

## 17. Phân biệt OpenAPI endpoint và Swagger UI

springdoc thường cung cấp:

| Endpoint | Nội dung |
| --- | --- |
| /v3/api-docs | OpenAPI JSON |
| /v3/api-docs.yaml | OpenAPI YAML |
| /swagger-ui.html | Swagger UI entry point theo cấu hình mặc định |

Nếu ứng dụng chỉ dùng API starter, Swagger UI không nhất thiết tồn tại. Nếu dùng UI starter, kiểm tra cả HTML, JavaScript, CSS và OpenAPI config mà UI tải về.

Native image build không tự biến OpenAPI document thành file tĩnh ở build time. springdoc vẫn tạo document từ Spring mappings và metadata khi ứng dụng native chạy. Nếu cần một file JSON/YAML cố định để publish trong pipeline, dùng bước export tài liệu riêng trong build; đừng giả định native compile đã xuất sẵn specification.

## 18. Kiểm tra native executable sau khi build

Chạy binary trong môi trường tương tự production:

~~~bash
./build/native/nativeCompile/application
~~~

Tên và đường dẫn executable phụ thuộc Gradle project và OS. Với Maven, binary thường nằm trong target sau native plugin execution hoặc trong image được build bằng Buildpacks.

Gọi OpenAPI JSON:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  --output openapi-native.json
~~~

Gọi YAML:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs.yaml \
  --output openapi-native.yaml
~~~

Kiểm tra file JSON:

~~~bash
jq -e '.openapi and .paths and (.paths | length > 0)' openapi-native.json
~~~

Nếu có Swagger UI, mở /swagger-ui.html và kiểm tra browser tải được swagger-config, OpenAPI JSON và static assets. Nếu dùng OAuth2 hoặc bearer security, kiểm tra security scheme trong document và luồng xác thực trên môi trường test.

## 19. Không chỉ kiểm tra native build thành công

Build thành công chỉ xác nhận GraalVM tạo được executable. Một bộ xác minh cần chạy các đường đi thực tế:

1. ApplicationContext khởi động trong native mode.
2. Controller quan trọng trả status và media type đúng.
3. OpenAPI JSON/YAML endpoint trả 200 và parse được.
4. Tất cả path/method mong đợi xuất hiện trong document.
5. Request DTO và response DTO được serialize đúng.
6. Validation và error response hoạt động.
7. Security scheme, OAuth2, group và customizer hoạt động.
8. Swagger UI assets có thể tải nếu starter UI được dùng.
9. Các route dùng reflection hoặc custom converter được gọi thực tế.
10. Native executable hoạt động trong container/OS mục tiêu.

Hãy kiểm tra cả response thực tế và OpenAPI document. Một schema có thể được sinh đúng nhưng Jackson serializer trong native runtime vẫn thiếu metadata cho một nhánh dữ liệu ít khi chạy.

## 20. Dùng tracing agent khi thiếu metadata

GraalVM Native Image Tracing Agent có thể quan sát reflection, resource và proxy usage khi ứng dụng chạy trên JVM. Agent tạo cấu hình gợi ý dựa trên những đường đi đã được thực thi.

Có thể chạy ứng dụng hoặc test với agent, sau đó dùng các thao tác thực tế như:

- Gọi endpoint tạo và đọc dữ liệu.
- Mở OpenAPI JSON/YAML.
- Mở Swagger UI nếu dùng.
- Kích hoạt error handler và validation.
- Dùng security scheme, custom converter và grouped docs.

Sau khi dừng ứng dụng, agent ghi metadata vào thư mục cấu hình. Hãy review file sinh ra, loại bỏ metadata của test infrastructure không cần cho runtime và thêm phần cần thiết vào source resources theo hướng dẫn của GraalVM.

Tracing agent chỉ ghi nhận code path đã chạy. Nó không tự phát hiện mọi nhánh có thể xảy ra. Nếu chưa gọi endpoint nhóm, loại DTO hoặc lỗi hiếm, metadata cần thiết cho nhánh đó có thể không được tạo.

## 21. Chạy test trong native mode

Native Build Tools hỗ trợ biên dịch và chạy test trên native image. Với Gradle, task thường dùng là:

~~~bash
./gradlew nativeTest
~~~

Với Maven, Native Build Tools cung cấp native test goal và cần JUnit Platform phù hợp. Hãy cấu hình test dependencies, Surefire và Native Build Tools theo tài liệu phiên bản đang dùng.

Không cần chuyển toàn bộ test suite sang native mode ngay lập tức. Một lộ trình thực tế:

- Chạy unit tests trên JVM để phản hồi nhanh.
- Chạy integration tests trên JVM để kiểm tra nghiệp vụ và hệ thống ngoài.
- Chạy một tập smoke/critical tests trên native image.
- Mở rộng native tests cho code path có nhiều reflection hoặc custom serialization.

Native test giúp phát hiện khác biệt chỉ xuất hiện sau AOT/native compilation. Nhưng test chạy trên JVM vẫn hữu ích để kiểm tra logic và nghiệp vụ với chi phí thấp hơn.

## 22. Kiểm tra lỗi native thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Native build báo missing reflection registration | Thiếu reflection hint cho class/member được truy cập động | Xem class trong lỗi, kiểm tra AOT hint và đăng ký đúng kiểu |
| Endpoint OpenAPI trả 404 | API docs bean không được tạo ở AOT build hoặc endpoint bị tắt | Kiểm tra component scan và springdoc.api-docs.enabled lúc build |
| @OpenAPIDefinition biến mất | Annotation nằm trên class không được Spring nhận diện | Chuyển annotation sang class @Configuration |
| Security scheme không xuất hiện | Config class không được scan hoặc annotation holder bị loại | Kiểm tra OpenApiConfiguration và native document |
| DTO có field thiếu trong JSON | Reflection/binding/serializer metadata chưa đủ hoặc Jackson config khác | Kiểm tra response native, custom serializer và binding hints |
| Swagger UI trả 404 asset | UI starter hoặc resource chưa được đưa vào image | Kiểm tra starter và resource hints của dependency |
| OpenAPI group biến mất | GroupedOpenApi bean không được tạo trong AOT context | Kiểm tra điều kiện bean, profile và cấu hình build time |
| JVM chạy nhưng native lỗi | Một code path dùng reflection/resource/proxy chưa có metadata | Dùng tracing agent và native tests |
| Native image build thất bại do toolchain | GraalVM, Java, Boot hoặc Native Build Tools không tương thích | Đối chiếu system requirements của đúng Boot version |
| Binary chạy trên máy build nhưng không chạy ở máy khác | Binary phụ thuộc OS, architecture hoặc native libraries | Build cho đúng target và kiểm tra runtime dependencies |
| Build rất lâu hoặc hết RAM | Native compilation tốn CPU/RAM, chạy song song quá nhiều | Giới hạn parallel builds và cấp tài nguyên CI phù hợp |

## 23. Native image không phải lúc nào cũng nhanh hơn JVM

Native Image thường có lợi thế startup và memory footprint, đặc biệt với ứng dụng khởi động thường xuyên hoặc chạy ngắn hạn. Nhưng ứng dụng JVM có JIT compiler có thể đạt throughput rất tốt sau warm-up. Native executable không có cùng cơ chế JIT tối ưu theo profile runtime.

Với API server chạy liên tục, cần đo:

- Thời gian từ process start tới readiness.
- Thời gian tải OpenAPI document lần đầu.
- Latency p50, p95 và p99 của endpoint nghiệp vụ.
- Throughput ở tải ổn định.
- RSS/working set sau warm-up.
- CPU usage và garbage collection behavior.
- Kích thước container image và executable.
- Thời gian build native image.

Không dùng riêng startup time để kết luận native tốt hơn. Nếu ứng dụng chạy lâu, throughput và tail latency có thể quan trọng hơn vài trăm mili giây khởi động.

## 24. Benchmark JVM và native một cách công bằng

Khi so sánh hai bản build:

1. Dùng cùng source code, dependency, cấu hình và dữ liệu.
2. Dùng cùng CPU, memory limit và network.
3. Đo JVM sau warm-up và native sau khi đạt trạng thái ổn định.
4. Chạy cùng workload và số request đồng thời.
5. Lặp lại nhiều lần và ghi lại biến thiên.
6. Đo cả cold start lẫn steady state.
7. Tách thời gian build image khỏi thời gian runtime.
8. Kiểm tra chức năng và response trước khi so sánh hiệu năng.

Với springdoc, đo riêng request /v3/api-docs nếu endpoint này được gọi thường xuyên. Tạo document có thể tốn CPU và allocation; native startup nhanh không có nghĩa việc sinh OpenAPI document cũng miễn phí.

Nếu OpenAPI endpoint chủ yếu được dùng khi phát triển hoặc bởi portal nội bộ, có thể không cần tối ưu nó như endpoint nghiệp vụ có lưu lượng cao. Hãy chọn workload theo hành vi thực tế của hệ thống.

## 25. Khi nào nên chọn native image?

| Bối cảnh | Native Image đáng thử? | Lý do |
| --- | --- | --- |
| Serverless hoặc scale-to-zero | Có | Startup và memory footprint có thể giảm cold-start cost |
| Worker ngắn hạn | Có | Thời gian khởi động chiếm tỷ lệ lớn |
| API service nhiều replica, memory limit chặt | Có, cần benchmark | Có thể giảm memory mỗi replica |
| API server chạy liên tục với throughput cao | Cần benchmark kỹ | JVM JIT có thể cho throughput tốt hơn |
| Dự án phụ thuộc nhiều plugin/classpath scanning runtime | Cần đánh giá kỹ | Closed-world có thể yêu cầu nhiều hints hoặc thay đổi thiết kế |
| Thư viện quan trọng chưa hỗ trợ native | Chưa nên chuyển production | Rủi ro lỗi runtime và chi phí bảo trì cao |
| CI không đủ CPU/RAM để native compile | Có thể không phù hợp | Native build có chi phí tài nguyên đáng kể |

Đối với springdoc, native image phù hợp khi ứng dụng đã có dependency matrix đúng, OpenAPI config được Spring nhận diện và các endpoint tài liệu đã được kiểm tra trên binary thật. Nếu Swagger UI không cần trong production, có thể chỉ đóng gói API docs endpoint hoặc chỉ export specification ở build pipeline.

## 26. Checklist trước khi phát hành native image có springdoc

- [ ] Spring Boot và springdoc version khớp compatibility matrix.
- [ ] GraalVM JDK, Java toolchain và Native Build Tools phù hợp với Spring Boot.
- [ ] Spring AOT processing chạy thành công với đúng build-time configuration.
- [ ] Controller, RouterFunction, GroupedOpenApi và customizer cần thiết được phát hiện.
- [ ] @OpenAPIDefinition và @SecurityScheme nằm trên class @Configuration.
- [ ] DTO, Jackson module và custom serializer hoạt động trong native runtime.
- [ ] Reachability metadata của thư viện được kiểm tra.
- [ ] Chỉ bổ sung RuntimeHints cho reflection/resource/proxy thực sự cần.
- [ ] /v3/api-docs và /v3/api-docs.yaml trả document hợp lệ.
- [ ] Swagger UI và static assets hoạt động nếu được đóng gói.
- [ ] Security scheme, OAuth2, validation và error response đã được smoke test.
- [ ] Native executable chạy được trên OS/architecture mục tiêu.
- [ ] Đã đo startup, memory, throughput, latency và build time.
- [ ] Đã so sánh lợi ích runtime với chi phí native build và bảo trì metadata.

Native Image đem lại lợi ích rõ nhất khi startup và memory là yếu tố quyết định. Với Spring Boot và springdoc, kết quả tốt phụ thuộc vào ba điều: chọn đúng cặp phiên bản, để Spring AOT nhận diện đầy đủ cấu hình OpenAPI, và kiểm tra các endpoint trên native executable thực tế. Hãy quyết định dựa trên số đo và test runtime thay vì chỉ dựa vào việc native compilation thành công.

## Tài liệu tham khảo

- [springdoc-openapi – FAQ: GraalVM support và compatibility matrix](https://springdoc.org/faq.html)
- [springdoc-openapi – Introduction và hỗ trợ GraalVM](https://springdoc.org/)
- [springdoc-openapi v2 – Tài liệu cho Spring Boot 3.x](https://springdoc.org/v2/)
- [Spring Boot – Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html)
- [Spring Boot – Ahead-of-Time Processing](https://docs.spring.io/spring-boot/maven-plugin/aot.html)
- [Spring Boot – Advanced Native Images Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html)
- [Spring Boot – System Requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [GraalVM – Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)
- [GraalVM Native Build Tools – Gradle Plugin](https://graalvm.github.io/native-build-tools/latest/gradle-plugin)
- [GraalVM Native Build Tools – Maven Plugin](https://graalvm.github.io/native-build-tools/latest/maven-plugin)
