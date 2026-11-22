# Kiểm tra đặc tả và tài nguyên giao diện trên bản native thực tế

Ứng dụng Spring Boot chạy được trên JVM chưa chứng minh bản native image cũng hoạt động đúng. Native image được tạo qua quá trình AOT và phân tích reachability; các lớp, phương thức, tài nguyên hoặc hoạt động reflection không được nhận diện có thể không xuất hiện trong executable cuối cùng. Vì springdoc-openapi sinh tài liệu từ metadata của ứng dụng và Swagger UI còn cần tải các tài nguyên tĩnh, cần kiểm tra cả hai chức năng trên chính binary hoặc container native sẽ được triển khai.

Bài này tập trung vào quy trình xác minh sau khi build native: kiểm tra cấu hình OpenAPI, endpoint JSON/YAML, document group, Swagger UI HTML, JavaScript, CSS và các tài nguyên tùy biến. Bài cũng hướng dẫn xử lý trường hợp annotation OpenAPI bị loại trong quá trình native compilation, bổ sung runtime hints khi có bằng chứng thiếu tài nguyên hoặc reflection, so sánh kết quả JVM/native và tự động hóa smoke test trong CI.

## 1. Vì sao phải kiểm tra bản native riêng?

Trong chế độ JVM, class loader, reflection và việc đọc tài nguyên classpath thường linh hoạt hơn. Native image được tạo bằng phân tích tĩnh và AOT; những phần không được nhận diện là có thể truy cập có thể bị loại khỏi executable hoặc không được đăng ký quyền truy cập lúc chạy.

Các khu vực liên quan tới springdoc cần được xác minh:

- Controller, request mapping và metadata của method.
- DTO, generic type, annotation Swagger và Bean Validation.
- Cấu hình OpenAPI, security scheme và OpenApiCustomizer.
- Các bean GroupedOpenApi.
- Schema được tạo qua Jackson hoặc model converter.
- Endpoint JSON và YAML.
- Tài nguyên Swagger UI nằm trong WebJar.
- Logo, CSS, JavaScript hoặc file OpenAPI tĩnh do ứng dụng bổ sung.
- Reflection, proxy hoặc resource access phát sinh từ custom integration.

Một JVM test thành công chỉ chứng minh luồng chạy trên JVM. Một native build thành công chỉ chứng minh compiler tạo được executable. Cả hai chưa chứng minh endpoint và tài nguyên được phục vụ đúng sau khi binary native khởi động.

## 2. Phân biệt AOT, native executable và native container

Ba khái niệm có liên quan nhưng khác nhau:

| Thành phần | Vai trò |
|---|---|
| AOT processing | Phân tích ApplicationContext ở build time và sinh mã/hints cần thiết |
| Native executable | Binary được biên dịch cho hệ điều hành và kiến trúc đích |
| Native container image | Container đóng gói native executable cùng runtime files cần thiết |

Với Spring Boot, AOT processing là một phần của quy trình tạo native image. Có thể dùng GraalVM Native Build Tools để tạo executable hoặc Cloud Native Buildpacks để tạo container image chứa native executable.

Khi xác minh Swagger UI, hãy kiểm tra đúng artifact định phát hành. Nếu production chạy container native, việc chạy binary trên máy phát triển chưa thay thế được kiểm tra container image, vì image có thể khác về tài nguyên, user, port, environment và filesystem.

## 3. Chọn đúng thế hệ Spring Boot và Springdoc

Hỗ trợ native cần được xem xét theo tổ hợp phiên bản:

- Springdoc ghi nhận hỗ trợ native image từ thế hệ Spring Boot 3.
- Spring Boot 3 thường đi cùng springdoc 2.x.
- Spring Boot 4 đi cùng springdoc 3.x.
- Với các phiên bản cũ hoặc cấu hình đặc biệt, cần kiểm tra compatibility matrix và hướng dẫn native tương ứng.

Không lấy một ví dụ native của Spring Boot 3 rồi áp dụng nguyên trạng cho Spring Boot 4 hoặc ngược lại. AOT engine, GraalVM, JDK, plugin và reachability metadata có thể thay đổi theo thế hệ.

Trước khi build, ghi nhận:

1. Spring Boot version.
2. Springdoc starter và version.
3. Java/GraalVM distribution và version.
4. Maven hoặc Gradle plugin version.
5. Web stack MVC hay WebFlux.
6. Starter có Swagger UI hay chỉ có API docs.
7. OS và CPU architecture của native target.

Tổ hợp version phải nằm trong ma trận hỗ trợ của Spring Boot và Springdoc. Native image cũng phụ thuộc hệ điều hành/kiến trúc; binary tạo cho Linux x64 không thể mặc định chạy trên Windows hoặc ARM64.

## 4. OpenAPI annotation cần nằm trên class cấu hình được giữ lại

Springdoc lưu ý một trường hợp quan trọng khi native compile: nếu đặt @OpenAPIDefinition hoặc @SecurityScheme trên một class không có implementation và class đó không được Spring nhận diện như cấu hình, class có thể bị loại khỏi native executable.

Hãy đặt metadata toàn cục trên một class cấu hình thực sự:

~~~java
import org.springframework.context.annotation.Configuration;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Store API",
        version = "1.0.0",
        description = "API quản lý cửa hàng"
    )
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
public class OpenApiConfiguration {
}
~~~

Class này phải nằm trong vùng component scan hoặc được import rõ ràng. Chỉ thêm @Configuration nhưng đặt class ngoài phạm vi scan vẫn có thể khiến cấu hình không được nạp.

Sau native build, xác minh document có info.title, info.version và security scheme mong đợi. Không chỉ kiểm tra class tồn tại trong source code.

## 5. Kiểm tra các bean tùy biến và document group

Nếu dùng OpenAPI bean, OpenApiCustomizer hoặc GroupedOpenApi, hãy xác nhận các bean đó được tạo trong ApplicationContext native.

Ví dụ group:

~~~java
@Configuration
public class OpenApiGroups {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .build();
    }
}
~~~

Nếu group không xuất hiện trong native document:

- Kiểm tra package của cấu hình có được component scan không.
- Kiểm tra điều kiện @Profile, @ConditionalOnProperty và các conditional bean.
- Kiểm tra group name và pathsToMatch.
- Gọi trực tiếp endpoint group trên binary native.
- So sánh ApplicationContext và profile giữa JVM với native.

Đừng giả định một bean đã có trong JVM test sẽ luôn được đăng ký ở native nếu profile hoặc điều kiện cấu hình khi build khác nhau.

## 6. Phân biệt endpoint OpenAPI với Swagger UI

Hai phần cần được kiểm tra riêng:

| Chức năng | Endpoint/tài nguyên thường gặp |
|---|---|
| OpenAPI JSON | /v3/api-docs |
| OpenAPI YAML | /v3/api-docs.yaml |
| Document group | /v3/api-docs/{group} |
| Trang vào Swagger UI | /swagger-ui.html |
| UI index và tài nguyên tĩnh | /swagger-ui/** |

Endpoint JSON/YAML được tạo bởi springdoc runtime. Swagger UI là giao diện web đọc đặc tả và cần các tài nguyên HTML, JavaScript, CSS, hình ảnh.

Nếu dùng starter API-only, endpoint OpenAPI có thể hoạt động mà không có Swagger UI. Muốn kiểm tra giao diện, ứng dụng phải có starter UI tương ứng với Spring MVC hoặc WebFlux.

Không kết luận native integration hoàn chỉnh chỉ vì /v3/api-docs trả 200. UI có thể vẫn thiếu file JavaScript hoặc CSS.

## 7. Build native bằng Maven

Với Maven và Spring Boot Maven Plugin, profile native do spring-boot-starter-parent cung cấp có thể điều phối AOT processing và các bước cần thiết cho native build. Nếu dự án không dùng parent này, cần cấu hình các execution AOT và Native Build Tools theo tài liệu Spring Boot.

Tạo native executable bằng GraalVM Native Build Tools:

~~~bash
./mvnw -Pnative native:compile
~~~

Trên Windows:

~~~powershell
.\mvnw.cmd -Pnative native:compile
~~~

Hoặc tạo container image native qua Buildpacks:

~~~bash
./mvnw -Pnative spring-boot:build-image
~~~

Buildpacks cần Docker daemon và cấu hình builder phù hợp. Các yêu cầu JDK/GraalVM thay đổi theo dòng Spring Boot và builder; dùng đúng yêu cầu trong tài liệu của phiên bản dự án.

Không nhầm Maven profile tên native với Spring profile của ứng dụng. -Pnative kích hoạt Maven build profile; profile ứng dụng như contract hoặc prod được cấu hình riêng qua Spring environment.

## 8. Build native bằng Gradle

Với Gradle, thêm GraalVM Native Image plugin theo hướng dẫn Spring Boot và GraalVM Native Build Tools. Khi plugin native được áp dụng, Spring Boot Gradle Plugin có thể cấu hình các task AOT.

Ví dụ tạo container image:

~~~bash
./gradlew bootBuildImage
~~~

Với Windows:

~~~powershell
.\gradlew.bat bootBuildImage
~~~

Task bootBuildImage sẽ tạo native image khi build được cấu hình với GraalVM Native Image plugin theo hướng dẫn tương ứng. Nếu dự án dùng task nativeCompile để tạo executable trực tiếp, xác nhận task và output path theo plugin version đang cài.

Không chạy một task native chỉ vì tên task có chữ native. Kiểm tra build log để xác nhận AOT và native-image compilation thực sự được thực hiện.

## 9. Chạy đúng native artifact vừa build

Sau build, khởi chạy executable được tạo ra. Tên file và đường dẫn phụ thuộc artifactId, cấu hình plugin và nền tảng.

Ví dụ trên Linux:

~~~bash
./target/store-service
~~~

Ví dụ trên Windows nếu output là file EXE:

~~~powershell
.\target\store-service.exe
~~~

Nếu build container image:

~~~bash
docker run --rm -p 8080:8080 store-service:latest
~~~

Không dùng java -jar để thay thế bước này. Lệnh java -jar chạy ứng dụng trên JVM, không kiểm tra native executable.

Khi chạy container, dùng cùng profile và biến môi trường như dự kiến triển khai. Nếu profile hoặc cấu hình làm thay đổi controller/group, kết quả OpenAPI có thể khác.

## 10. Chờ native application sẵn sàng

Native executable có thể khởi động nhanh, nhưng thời gian khởi động không đồng nghĩa server đã sẵn sàng nhận request. Ứng dụng vẫn có thể cần kết nối database, load secrets, chạy migration hoặc khởi tạo các bean tùy biến.

Nếu đã bật Actuator readiness:

~~~bash
curl --fail --silent --show-error http://localhost:8080/actuator/health/readiness
~~~

Nếu không có readiness endpoint, có thể polling endpoint OpenAPI với timeout hữu hạn. Khi hết thời gian chờ, in log native process và trạng thái container.

Không gửi request OpenAPI ngay sau khi tạo process rồi xem connection refused là lỗi Springdoc. Trước hết xác nhận ứng dụng đã bind port và hoàn tất startup.

## 11. Kiểm tra OpenAPI JSON trên native binary

Gọi endpoint từ chính tiến trình native:

~~~bash
curl -i http://localhost:8080/v3/api-docs
~~~

Kiểm tra:

- Status code là 2xx, thường là 200.
- Content-Type là JSON.
- Response body parse được.
- Có trường openapi, info và paths.
- Các operation quan trọng có mặt.
- Schema và component reference đầy đủ.
- Security scheme và security requirement đúng.

Có thể dùng jq để smoke check:

~~~bash
curl --fail --silent http://localhost:8080/v3/api-docs \
  | jq -e '.openapi and .info.title and .paths'
~~~

Nếu ứng dụng bật authentication cho tài liệu, request kiểm tra cần dùng credential của test identity. Không tắt security chỉ để curl nhận 200.

Một response 200 chưa đủ nếu body là HTML login page hoặc JSON lỗi của gateway. Hãy xem cả Content-Type và cấu trúc document.

## 12. Kiểm tra OpenAPI YAML

Nếu ứng dụng hỗ trợ endpoint YAML:

~~~bash
curl -i http://localhost:8080/v3/api-docs.yaml
~~~

Xác nhận response là YAML hợp lệ và chứa cùng thông tin cốt lõi với JSON:

- OpenAPI version.
- Info title và version.
- Paths và HTTP methods.
- Request/response schemas.
- Security schemes.
- Document groups.

Nếu JSON hoạt động nhưng YAML không hoạt động, kiểm tra cấu hình endpoint, dependency/runtime và response serialization. Không đổi phần mở rộng file JSON thành .yaml để xem như đã kiểm tra YAML.

## 13. Kiểm tra mọi document group

Với mỗi GroupedOpenApi, gọi URL tương ứng:

~~~bash
curl --fail --silent http://localhost:8080/v3/api-docs/public
curl --fail --silent http://localhost:8080/v3/api-docs/partner
~~~

Tạo bảng kiểm tra cho các group được phát hành:

| Group | Endpoint | Điều cần xác minh |
|---|---|---|
| public | /v3/api-docs/public | Chỉ chứa API công khai |
| partner | /v3/api-docs/partner | Có đúng endpoint đối tác |
| internal | /v3/api-docs/internal | Có đúng schema và policy truy cập |

Đây là tên group minh họa; dùng group thực tế của ứng dụng. Nếu một group biến mất trong native, kiểm tra bean registration, component scan, profile và điều kiện tạo bean.

Việc group không hiển thị trong Swagger UI có thể do cấu hình dropdown. Hãy gọi endpoint group trực tiếp để phân biệt lỗi tạo document với lỗi giao diện.

## 14. Kiểm tra trang vào Swagger UI

Mở đường dẫn mặc định hoặc path đã cấu hình:

~~~bash
curl -i -L http://localhost:8080/swagger-ui.html
~~~

Đường dẫn /swagger-ui.html thường chuyển hướng tới trang index của UI. Kiểm tra redirect và response cuối cùng, thay vì giả định mọi phiên bản phải trả 200 trực tiếp ở URL đầu.

Nếu dùng path tùy biến qua springdoc.swagger-ui.path, hãy gọi đúng path đó. Nếu có context path, thêm context path vào URL.

HTML tải thành công mới chỉ là bước đầu. Browser còn phải tải được CSS, JavaScript, favicon và OpenAPI document. Một trang trắng hoặc thông báo không tải được definition có thể xuất hiện dù HTML ban đầu trả 200.

## 15. Kiểm tra JavaScript, CSS và tài nguyên WebJar

Swagger UI sử dụng các tài nguyên tĩnh được đóng gói trong WebJar. Springdoc mô tả các tài nguyên này trong classpath dưới META-INF/resources/webjars/swagger-ui/<version>/, ví dụ:

- index.html
- swagger-ui-bundle.js
- swagger-ui-standalone-preset.js
- swagger-ui.css
- favicon-32x32.png

Tên và URL HTTP thực tế có thể thay đổi theo version Swagger UI và cách Springdoc phục vụ tài nguyên. Hãy dùng Network panel của browser để lấy chính xác URL mà trang UI yêu cầu.

Với từng request tài nguyên, kiểm tra:

- Status 200 hoặc status hợp lệ theo cache.
- Content-Type đúng loại file.
- Response body không phải trang lỗi HTML.
- Không bị redirect tới trang đăng nhập ngoài dự kiến.
- URL có context path hoặc proxy prefix đúng.

Nếu index HTML trả 200 nhưng bundle JavaScript trả 404, giao diện sẽ không khởi tạo. Nếu CSS trả 404, trang có thể hiện nội dung nhưng bố cục bị lỗi.

## 16. Kiểm tra bằng browser Network và Console

Mở Swagger UI trên URL của native instance rồi dùng Developer Tools:

1. Chọn tab Network và bật Preserve log.
2. Reload trang UI.
3. Lọc các request JS, CSS, image và api-docs.
4. Kiểm tra status, Content-Type và response URL.
5. Mở tab Console để xem lỗi JavaScript, CORS hoặc mixed content.
6. Kiểm tra URL OpenAPI mà UI thực sự tải.
7. Thử chọn từng document group nếu UI có dropdown.
8. Thử Authorize và Try it out theo policy bảo mật của môi trường test.

Kiểm tra trên browser thật đặc biệt hữu ích vì curl chỉ xác nhận HTTP response. Browser còn áp dụng quy tắc same-origin, CORS, mixed content, CSP và xử lý JavaScript.

Nếu dùng reverse proxy, hãy truy cập qua domain và path công khai như người dùng production. Truy cập localhost trực tiếp không kiểm tra được toàn bộ đường đi qua ingress hoặc gateway.

## 17. Kiểm tra custom static resource và file OpenAPI bên ngoài

Ứng dụng có thể thêm:

- Logo hoặc favicon tùy chỉnh.
- CSS/JavaScript cho Swagger UI.
- File OpenAPI JSON/YAML tĩnh.
- File ví dụ hoặc tài liệu bổ sung.
- Resource transformer để sửa index page hoặc tài nguyên WebJar.

Các file này phải được đóng gói trong artifact native và có thể đọc ở runtime. Nếu dùng file trong src/main/resources/static, kiểm tra URL thực tế sau khi build; không chỉ kiểm tra file có mặt trong source tree.

Nếu Swagger UI dùng file OpenAPI tĩnh qua springdoc.swagger-ui.url, xác nhận file đó được phục vụ từ native binary và UI tải được đúng URL. Nếu URL nằm ở máy chủ khác, kiểm tra CORS, TLS và network từ browser.

Với resource transformer tùy biến, kiểm tra cả tài nguyên gốc lẫn nội dung sau transform. Một transformer có thể hoạt động trên JVM nhưng gặp vấn đề khi resource hoặc class được truy cập theo cách không được native metadata nhận diện.

## 18. Bổ sung resource hints khi thật sự thiếu tài nguyên

Spring AOT và metadata từ dependency có thể cung cấp nhiều resource hints. Không nên đăng ký toàn bộ classpath hoặc mọi WebJar một cách rộng rãi chỉ để tránh lỗi. Trước tiên xác định đúng resource bị thiếu từ log native hoặc HTTP response.

Ví dụ ứng dụng có file riêng tại src/main/resources/static/openapi/examples.json và native runtime không tìm thấy file theo cách truy cập classpath tùy biến. Có thể đăng ký resource pattern:

~~~java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.ImportRuntimeHints;
import org.springframework.context.annotation.Configuration;

class OpenApiResourceHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("static/openapi/examples.json");
    }
}

@Configuration
@ImportRuntimeHints(OpenApiResourceHints.class)
class OpenApiNativeConfiguration {
}
~~~

Đường dẫn trong registerPattern là đường dẫn resource classpath tương ứng với cách ứng dụng đọc file. Hãy điều chỉnh theo vị trí thật và kiểm tra trên binary sau khi build lại.

Nếu file được phục vụ bởi Spring MVC static resource handler, trước hết kiểm tra URL và cấu hình resource handler. Runtime hint chỉ giải quyết reachability của resource; nó không sửa URL mapping, context path hoặc security policy.

## 19. Reflection hints cho schema và model tùy biến

Springdoc và các thư viện nền sử dụng metadata của controller, DTO, Jackson và annotation để tạo schema. Spring Boot AOT cùng reachability metadata của dependency xử lý nhiều trường hợp phổ biến.

Nếu custom code dùng reflection động để tìm field, constructor hoặc method mà AOT không thể suy ra, native runtime có thể báo lỗi như missing reflective access hoặc không đọc được metadata. Khi đó:

1. Đọc stack trace để xác định class/member bị thiếu.
2. Xác định code nào thực hiện reflection.
3. Kiểm tra thư viện có reachability metadata hoặc Spring RuntimeHints chưa.
4. Đăng ký đúng type/member cần truy cập.
5. Build lại native image và chạy lại luồng gây lỗi.

Không đăng ký reflection cho toàn bộ package nếu chỉ thiếu một DTO. Hints quá rộng có thể làm native image lớn hơn và che giấu dependency không rõ ràng.

Với kiểu dữ liệu cần binding nhưng chưa được Spring nhận diện, xem xét các cơ chế phù hợp như @RegisterReflectionForBinding hoặc RuntimeHintsRegistrar theo API của Spring Boot version đang dùng. Chỉ thêm hint khi có bằng chứng về member hoặc type cần truy cập.

## 20. Dùng GraalVM tracing agent khi không tìm được hint thiếu

Tracing agent có thể ghi nhận một số hoạt động reflection, resource và proxy khi chạy ứng dụng trên JVM. Sau đó có thể dùng kết quả để điều tra metadata cần thiết cho native image.

Quy trình khái quát:

1. Chạy ứng dụng JVM với native image tracing agent.
2. Gọi các endpoint OpenAPI và Swagger UI cần hỗ trợ.
3. Thực hiện các luồng custom resource, group và schema.
4. Dừng ứng dụng để agent ghi metadata.
5. Review file được sinh ra, loại bỏ hint không cần thiết.
6. Đưa metadata đã xác minh vào vị trí native-image phù hợp.
7. Build lại và kiểm tra native executable.

Tracing agent chỉ ghi nhận những đường chạy đã được thực thi. Nếu không mở Swagger UI hoặc không gọi group endpoint trong phiên tracing, agent có thể không ghi lại tài nguyên hoặc reflection cần cho các luồng đó.

Không sao chép nguyên mọi metadata từ một test suite lớn mà không review. Test infrastructure có thể tạo ra nhiều hint không cần thiết cho runtime production.

## 21. So sánh OpenAPI trên JVM và native

Để phát hiện khác biệt AOT, hãy lấy hai document từ cùng một commit:

1. Chạy ứng dụng trên JVM với profile contract.
2. Lấy JSON/YAML từ endpoint.
3. Chạy native executable với cùng profile và cấu hình.
4. Lấy JSON/YAML từ endpoint native.
5. So sánh hai document sau khi chuẩn hóa các trường phụ thuộc môi trường nếu có.

Các phần cần so sánh:

- Info title, version và description.
- Paths, methods và operationId.
- Parameters và request body.
- Response status, media type và schema.
- Components.schemas và references.
- Security schemes và requirements.
- Tags và document groups.
- Server URL.

Server URL có thể khác nếu host, port, proxy hoặc forwarded headers khác nhau. Hãy chuẩn hóa trường này nếu mục tiêu so sánh là schema/operation; không loại bỏ khác biệt nếu server URL chính là điều cần kiểm tra.

Không chỉ so sánh số lượng path. Hai document có cùng số path vẫn có thể khác request required, response schema hoặc security requirement.

## 22. Kiểm tra cache và request đầu tiên

Springdoc mặc định tính toán và cache OpenAPI description. Request đầu tiên có thể làm phát sinh công việc tạo schema; các request sau thường dùng kết quả đã cache.

Trong native image, kiểm tra cả:

- Request đầu tiên sau startup.
- Request lặp lại sau khi cache đã được tạo.
- Request tới từng group.
- Request có Accept-Language nếu ứng dụng sinh tài liệu theo locale.

Nếu chỉ request đầu tiên lỗi, xem log tạo document và customizer. Nếu mọi request đều chậm, đo thời gian và kiểm tra schema quá lớn, custom converter hoặc logic tùy biến.

Không tắt cache chỉ để làm native test thành công. Chỉ thay đổi cache khi có yêu cầu vận hành cụ thể, rồi đo lại tác động trên JVM và native.

## 23. Kiểm tra Security trên native

Native binary phải giữ cùng policy bảo mật như JVM application. Kiểm tra riêng:

- /v3/api-docs
- /v3/api-docs.yaml
- /v3/api-docs/{group}
- /swagger-ui.html
- /swagger-ui/**

Nếu endpoint yêu cầu authentication, dùng test identity có quyền phù hợp. Một response 401/403 có thể là policy đúng, không phải lỗi native.

Nếu UI tải HTML nhưng request OpenAPI bị 401, hãy xác minh Swagger UI có gửi credential hoặc cookie theo cấu hình hay không. Nếu chỉ group internal bị 403, kiểm tra authority và matcher của group endpoint.

Không mở public toàn bộ tài liệu chỉ để smoke test. Có thể chạy kiểm thử trong network cô lập và dùng credential CI giới hạn quyền.

## 24. Kiểm tra context path và reverse proxy

Ứng dụng có thể chạy dưới context path hoặc được công bố qua ingress. Khi đó, URL UI và API docs phải phản ánh đường dẫn công khai.

Ví dụ URL bên ngoài:

~~~text
https://api.example.com/store
~~~

Các URL cần hoạt động có thể là:

~~~text
https://api.example.com/store/swagger-ui.html
https://api.example.com/store/v3/api-docs
~~~

Kiểm tra:

- Server context path.
- Forwarded headers từ proxy đáng tin cậy.
- springdoc.swagger-ui.path và springdoc.api-docs.path nếu đã tùy biến.
- URL spec mà Swagger UI tải.
- CORS và CSP.
- Route cho /swagger-ui/** và /v3/api-docs/**.

Nếu truy cập trực tiếp native container thành công nhưng qua domain thất bại, tập trung vào ingress, proxy và security headers. Không vội thêm reflection hints vì lỗi có thể nằm ngoài native executable.

## 25. Smoke test tự động trên native executable

Một smoke test tối thiểu nên kiểm tra các HTTP response từ binary native:

~~~bash
curl --fail --silent --show-error http://localhost:8080/v3/api-docs \
  -o target/native-openapi.json

jq -e '.openapi and .info and .paths' target/native-openapi.json

curl --fail --silent --show-error http://localhost:8080/v3/api-docs.yaml \
  -o target/native-openapi.yaml

curl --fail --silent --show-error -L http://localhost:8080/swagger-ui.html \
  -o target/native-swagger-ui.html
~~~

Các lệnh trên giả định endpoint không yêu cầu authentication và YAML endpoint được bật. Nếu có security, bổ sung credential qua secret environment của CI; không ghi token trực tiếp vào script được commit.

HTML output không chứng minh JavaScript/CSS hoạt động. Bổ sung browser test hoặc kiểm tra các URL tài nguyên thực tế từ Network log. Nếu không chạy browser trong CI, ít nhất cần một test HTTP cho các tài nguyên tĩnh quan trọng.

Sau smoke test, chạy OpenAPI validator và contract diff trên JSON/YAML. Mục tiêu là kiểm tra cả khả năng phục vụ và nội dung hợp đồng.

## 26. Kiểm thử native container trong CI

Pipeline nên khởi chạy chính image native vừa build:

~~~text
Build AOT and native image
          |
          v
Start native container
          |
          v
Wait for readiness
          |
          v
Fetch JSON and YAML
          |
          v
Check Swagger UI HTML and static assets
          |
          v
Validate OpenAPI document
          |
          v
Compare with JVM/baseline contract
          |
          v
Stop container and publish test artifacts
~~~

Các bước thực hiện:

1. Build native image trên runner có toolchain phù hợp.
2. Khởi chạy container với profile contract.
3. Chờ readiness với timeout hữu hạn.
4. Gọi JSON, YAML và từng group.
5. Kiểm tra Swagger UI HTML và các tài nguyên JavaScript/CSS.
6. Chạy browser test nếu pipeline có browser automation.
7. Validate OpenAPI và so sánh baseline.
8. Thu thập log khi bất kỳ bước nào thất bại.
9. Dừng container trong bước cleanup luôn được thực hiện.
10. Chỉ phát hành image khi các kiểm tra bắt buộc thành công.

Native build có thể mất nhiều thời gian và tài nguyên hơn JVM build. Có thể cache dependency/build layer theo chính sách CI, nhưng không dùng một binary cũ để thay thế kiểm thử native của commit hiện tại.

## 27. Chẩn đoán lỗi thường gặp

| Triệu chứng trên native | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| /v3/api-docs trả 404 | API docs bị tắt, sai path hoặc starter không phù hợp | Kiểm tra runtime dependency và springdoc.api-docs.path |
| JSON thiếu title hoặc security scheme | Class chỉ mang annotation bị loại khỏi native image | Đặt annotation trên class @Configuration được scan |
| Group không xuất hiện | Group bean không được tạo hoặc profile khác | Kiểm tra component scan, condition và profile |
| JSON có path nhưng thiếu schema | Reflection/binding metadata hoặc custom converter | Xem stack trace và bổ sung hint chính xác |
| /v3/api-docs trả 500 | Lỗi tạo schema, customizer hoặc reflection | Đọc log native process và xác định class/member |
| YAML 404 nhưng JSON hoạt động | Endpoint YAML không được bật hoặc khác cấu hình | Kiểm tra runtime configuration và URL |
| Swagger UI HTML trả 200 nhưng trang trắng | JavaScript bundle hoặc CSS không tải được | Dùng Network/Console để tìm tài nguyên lỗi |
| JS/CSS trả 404 | Sai URL, resource không có trong image hoặc proxy path sai | Kiểm tra WebJar/resource mapping và native image |
| Logo hoặc spec tĩnh bị thiếu | Resource tùy biến không được đóng gói/đăng ký | Kiểm tra classpath và resource hints |
| UI tải được nhưng definition lỗi | URL OpenAPI sai, security hoặc CORS | Kiểm tra request api-docs trong Network |
| JVM hoạt động, native lỗi | AOT/reachability khác nhau | Kiểm tra hints và chạy đúng native binary |
| Chỉ request đầu tiên lỗi | Lỗi trong bước tạo document hoặc cache | Thu log và kiểm tra customizer/model converter |
| Chạy local được, container lỗi | Sai port, user, filesystem, env hoặc architecture | Kiểm tra cấu hình và log trong container |
| Native image build thành công nhưng endpoint không đủ | Build thành công không bảo đảm mọi luồng runtime | Thêm native smoke test cho từng endpoint và resource |

## 28. Checklist trước khi phát hành

Trước khi chấp nhận native artifact, xác minh:

- [ ] Spring Boot, Springdoc, JDK/GraalVM và native plugin thuộc tổ hợp tương thích.
- [ ] AOT processing và native compilation thực sự chạy trong build.
- [ ] Đã khởi chạy binary/container native, không chỉ chạy JVM jar.
- [ ] Profile và biến môi trường giống cấu hình dự kiến phát hành.
- [ ] Class OpenAPI annotation nằm trong cấu hình được Spring scan.
- [ ] OpenAPI JSON trả document hợp lệ.
- [ ] OpenAPI YAML trả nội dung hợp lệ nếu được bật.
- [ ] Mọi document group quan trọng đều truy cập được.
- [ ] Paths, schemas, responses và security scheme khớp hợp đồng kỳ vọng.
- [ ] Swagger UI HTML tải được.
- [ ] JavaScript, CSS, favicon và tài nguyên tùy biến không bị thiếu.
- [ ] UI tải đúng OpenAPI URL.
- [ ] Context path, proxy và security hoạt động đúng.
- [ ] JVM/native document đã được so sánh hoặc kiểm tra với baseline.
- [ ] Native smoke test và validator chạy trong CI.
- [ ] Container/process được cleanup ngay cả khi test thất bại.

## 29. Ghi nhớ

- JVM test không thay thế việc chạy và kiểm tra native executable.
- Native build dùng AOT và reachability analysis; reflection, proxy và resource tùy biến cần được nhận diện.
- Springdoc ghi nhận native support từ Spring Boot 3; phải chọn đúng major version theo Spring Boot.
- Đặt @OpenAPIDefinition và @SecurityScheme trên class @Configuration được component scan.
- Kiểm tra OpenAPI JSON/YAML, document groups và Swagger UI riêng biệt.
- Swagger UI còn phụ thuộc HTML, JavaScript, CSS, favicon và các tài nguyên WebJar.
- Chỉ thêm resource/reflection hints khi log hoặc test xác định đúng phần còn thiếu.
- Tracing agent có thể hỗ trợ tìm metadata nhưng chỉ ghi nhận những luồng đã được chạy.
- So sánh document JVM/native để phát hiện khác biệt do AOT hoặc profile.
- Kiểm tra request đầu tiên, cache, security, context path và reverse proxy.
- CI phải smoke test chính native image/container được build từ commit hiện tại.

Để xác nhận đặc tả và tài nguyên giao diện hoạt động trên bản native thực tế, hãy khởi chạy đúng executable hoặc container sẽ phát hành. Gọi trực tiếp JSON, YAML và từng document group; mở Swagger UI và kiểm tra mọi request JavaScript/CSS trong browser. Nếu có khác biệt so với JVM, dùng log native và reachability metadata để tìm đúng class hoặc resource bị thiếu, sau đó build lại và lặp lại smoke test trên artifact mới.

## Tài liệu tham khảo

- Springdoc FAQ – Is GraalVM supported?: https://springdoc.org/faq.html
- Springdoc OpenAPI v2 documentation: https://springdoc.org/v2/
- Spring Boot – Developing Your First GraalVM Native Application: https://docs.spring.io/spring-boot/how-to/native-image/developing-your-first-application.html
- Spring Boot – Advanced Native Images Topics: https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html
- Spring Boot Maven Plugin – Ahead-of-Time Processing: https://docs.spring.io/spring-boot/maven-plugin/aot.html
