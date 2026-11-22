# Chọn tài liệu hướng dẫn đúng phiên bản đang triển khai

Khi dùng springdoc-openapi, cần chọn tài liệu hướng dẫn theo phiên bản Spring Boot và phiên bản springdoc thực tế của ứng dụng. Trang tài liệu mới nhất có thể mô tả API, starter, package hoặc cấu hình không tồn tại trong bản đang chạy. Làm theo hướng dẫn của major version khác có thể dẫn đến dependency không tương thích, import không tồn tại hoặc cấu hình không còn được hỗ trợ.

Quy trình đúng bắt đầu bằng việc xác định dependency đã được resolve trong build và runtime, sau đó đối chiếu với bảng tương thích chính thức. Tiếp theo, mở đúng nhánh tài liệu v1, v2 hoặc v3, kiểm tra release notes của phiên bản cụ thể và thử xác nhận trên OpenAPI document do ứng dụng tạo ra.

## 1. Phân biệt phiên bản ứng dụng và phiên bản tài liệu

Một dự án Spring Boot có nhiều phiên bản liên quan:

| Thành phần | Vai trò | Nơi thường xác định |
|---|---|---|
| Java/JDK | Biên dịch và chạy ứng dụng | Toolchain, compiler config, runtime image |
| Spring Boot | Quản lý nền tảng và dependency | Maven parent/BOM hoặc Gradle plugin/platform |
| Spring Framework | MVC, WebFlux, DI, binding và các API nền tảng | Thường được Spring Boot BOM quản lý |
| springdoc-openapi | Tạo OpenAPI document và tích hợp Swagger UI | Dependency trực tiếp hoặc starter |
| Swagger Core | Mô hình và annotation OpenAPI | Dependency bắc cầu từ springdoc |
| Jackson | Chuyển đổi JSON và metadata serialization | Thường được Spring Boot quản lý |
| OpenAPI Specification | Phiên bản định dạng của document được sinh | Trường openapi trong JSON/YAML |
| API info.version | Phiên bản API mà đội sản phẩm công bố | OpenAPIDefinition hoặc cấu hình |

Ba giá trị thường bị nhầm:

- Spring Boot version xác định nền tảng ứng dụng.
- springdoc version xác định dòng thư viện đang tạo tài liệu.
- OpenAPI version xác định phiên bản đặc tả mà file JSON/YAML tuân theo.

Ví dụ, một ứng dụng có thể chạy Spring Boot 3.5, dùng springdoc 2.10 và tạo document theo OpenAPI 3.1. Giá trị info.version có thể là 2026.11 hoặc 1.4.0 theo quy ước sản phẩm; nó không phải phiên bản springdoc.

## 2. Xác định phiên bản thực tế trước khi mở tài liệu

Không chỉ nhìn vào một dòng version trong pom.xml hoặc build.gradle. Version có thể được quản lý ở parent, BOM, version catalog, plugin, dependency constraint hoặc bị thay đổi bởi dependency resolution.

Ghi nhận tối thiểu:

- Phiên bản Spring Boot được resolve.
- Phiên bản springdoc được resolve ở runtimeClasspath.
- Java toolchain và JDK chạy ứng dụng.
- Spring MVC hay Spring WebFlux.
- Starter có bao gồm Swagger UI hay chỉ cung cấp OpenAPI API endpoint.
- Các module springdoc bổ sung đang được dùng.

Với Maven, kiểm tra phiên bản Spring Boot và springdoc trong dependency tree:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.boot,org.springdoc
~~~

Để xem toàn bộ dependency có liên quan đến Spring và Swagger Core:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework,org.springdoc,io.swagger.core.v3
~~~

Để xem cấu hình POM sau khi kế thừa parent, profile và property được áp dụng:

~~~bash
./mvnw help:effective-pom
~~~

Với Gradle:

~~~bash
./gradlew dependencyInsight --dependency springdoc-openapi --configuration runtimeClasspath
~~~

Kiểm tra thêm Spring Boot:

~~~bash
./gradlew dependencyInsight --dependency spring-boot --configuration runtimeClasspath
~~~

Nếu dependency được khai báo qua version catalog, catalog cho biết version yêu cầu; dependencyInsight cho biết version thực tế được Gradle chọn sau resolution.

## 3. Bảng tương thích Spring Boot và springdoc

Bảng dưới đây tóm tắt các dòng tương thích được công bố trong tài liệu Springdoc tại thời điểm biên soạn, ngày 20-11-2026. Hãy mở bảng chính thức trước mỗi lần nâng cấp vì phạm vi hỗ trợ và patch version có thể thay đổi.

| Spring Boot | Dòng springdoc tương thích được công bố |
|---|---|
| 4.1.x | 3.1.x đến 3.2.x |
| 4.0.x | 3.0.x |
| 3.5.x | 2.8.x đến 2.10.x |
| 3.4.x | 2.7.x đến 2.8.x |
| 3.3.x | 2.6.x |
| 3.2.x | 2.3.x đến 2.5.x |
| 3.1.x | 2.2.x |
| 3.0.x | 2.0.x đến 2.1.x |
| 2.7.x và một số nền tảng Boot 1.5.x cũ | 1.6.0 trở lên theo bảng v1 |
| 2.6.x và một số nền tảng Boot 1.5.x cũ | 1.6.0 trở lên theo bảng v1 |
| 2.5.x | 1.5.9 trở lên |
| 2.4.x | 1.5.0 trở lên |
| 2.3.x | 1.4.0 trở lên |
| 2.2.x | 1.2.1 trở lên |
| 2.0.x | 1.0.0 trở lên |

Quy tắc major tổng quát:

- Spring Boot 2 và các ứng dụng Boot 1 cũ thuộc dòng Springdoc v1.
- Spring Boot 3 thuộc dòng Springdoc v2.
- Spring Boot 4 thuộc dòng Springdoc v3.

Không suy diễn rằng mọi patch version trong cùng major đều tương thích như nhau. Bảng chi tiết theo minor ở trên có ý nghĩa khi chọn phiên bản cho một ứng dụng đang được triển khai.

## 4. Lưu ý khi bảng tương thích chưa có dòng cho phiên bản Boot mới

Tại thời điểm biên soạn, trang Spring Boot công bố 4.2.0 là bản ổn định. Tuy nhiên, bảng tương thích Springdoc đang liệt kê Boot 4.1.x và 4.0.x mà chưa có hàng 4.2.x.

Điều này không đủ căn cứ để khẳng định springdoc 3.2.x đã được kiểm thử với Boot 4.2.0. Không tự mở rộng phạm vi 4.1.x sang 4.2.x chỉ vì cùng major.

Khi gặp phiên bản chưa có trong bảng:

1. Kiểm tra lại trang compatibility matrix và ngày cập nhật.
2. Tìm release note hoặc issue chính thức xác nhận hỗ trợ phiên bản đó.
3. Kiểm tra Spring Framework và Java baseline của Spring Boot mới.
4. Nếu cần thử nghiệm, tạo nhánh thử riêng và chạy kiểm tra startup, OpenAPI JSON, Swagger UI và integration tests.
5. Ghi rõ đây là tổ hợp đang thử nghiệm nếu chưa có xác nhận chính thức.
6. Chỉ chọn tổ hợp được công bố hỗ trợ cho production khi yêu cầu vận hành cần mức tương thích đã được xác nhận.

Không dùng dòng Snapshot làm bằng chứng cho một release ổn định. Snapshot có thể thay đổi và không có cùng cam kết tương thích với bản phát hành chính thức.

## 5. Chọn đúng nhánh tài liệu v1, v2 hoặc v3

Springdoc duy trì tài liệu theo major version. Hãy dùng trang tương ứng với dependency đang chạy:

| Dòng thư viện | Nền tảng chính | Tài liệu cần mở |
|---|---|---|
| Springdoc v1 | Spring Boot 1/2 cũ | https://springdoc.org/v1/ |
| Springdoc v2 | Spring Boot 3 | https://springdoc.org/v2/ |
| Springdoc v3 | Spring Boot 4 | https://springdoc.org/ |

Trang tài liệu chính có thể được cập nhật để mô tả major version hiện hành. Nếu ứng dụng vẫn dùng v1 hoặc v2, hãy chuyển đến nhánh tài liệu versioned thay vì sao chép dependency hoặc code mẫu từ trang mới nhất.

Các loại tài liệu cần đối chiếu:

- Getting started: starter và cấu hình tối thiểu.
- Modules: MVC, WebFlux, UI, API-only và add-on.
- Migration guide: thay đổi giữa các major version.
- FAQ: lỗi đã biết và cách xử lý theo dòng thư viện.
- Configuration properties: tên property, kiểu dữ liệu và default.
- Release notes: thay đổi ở patch/minor cụ thể.
- Javadoc/API reference: package, class và method của đúng version.

## 6. Ví dụ chọn tài liệu theo phiên bản đang chạy

### Trường hợp A: Spring Boot 3.5.x

Nếu dependency tree cho thấy Spring Boot 3.5.x và springdoc 2.9.x:

1. Chọn tài liệu Springdoc v2.
2. Dùng bảng tương thích xác nhận 2.9.x thuộc dải hỗ trợ cho Boot 3.5.x.
3. Đọc phần starter và cấu hình trong https://springdoc.org/v2/.
4. Khi gặp khác biệt API, mở release notes của đúng patch 2.9.x.
5. Không lấy import hoặc ví dụ migration sang v3 nếu chưa nâng Boot 4.

### Trường hợp B: Spring Boot 4.0.x

Nếu ứng dụng dùng Boot 4.0.x:

1. Chọn Springdoc v3 theo bảng tương thích.
2. Dùng tài liệu hiện hành tại https://springdoc.org/.
3. Kiểm tra starter và package của v3.
4. Đọc migration guide nếu source được nâng từ v2.
5. Kiểm tra các thay đổi nền tảng của Spring Boot 4 song song với thay đổi Springdoc.

### Trường hợp C: Spring Boot 2.7.x

Nếu ứng dụng cũ đang dùng Boot 2.7.x:

1. Chọn dòng Springdoc v1 tương thích.
2. Mở https://springdoc.org/v1/.
3. Không copy starter v2 hoặc v3 vào ứng dụng Boot 2.
4. Nếu đang lên kế hoạch nâng Boot 3, thực hiện migration theo lộ trình riêng và kiểm tra các thay đổi javax sang jakarta.

## 7. Xác định đúng web stack trước khi chọn ví dụ

Sau khi chọn đúng major version, cần chọn đúng nhánh tích hợp:

| Web stack | Cần Swagger UI | Chỉ cần OpenAPI document |
|---|---|---|
| Spring MVC | Starter WebMVC UI tương ứng với major | Starter WebMVC API tương ứng |
| Spring WebFlux | Starter WebFlux UI tương ứng với major | Starter WebFlux API tương ứng |

Ví dụ với dòng v2:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

Ví dụ này dành cho Spring MVC và có Swagger UI. Với WebFlux, dùng starter WebFlux UI. Nếu không cần UI, chọn starter API-only tương ứng.

Không ghép starter WebMVC và WebFlux cùng lúc chỉ để thử. Nếu ứng dụng có cả spring-boot-starter-web và spring-boot-starter-webflux, hãy xác định loại application context thực sự được Spring Boot chọn.

Tên artifact và package có thể thay đổi giữa major version. Đọc phần modules và migration của đúng nhánh trước khi copy dependency.

## 8. Phân biệt tài liệu theo major với release notes theo patch

Tài liệu major version giải thích API và kiến trúc tổng quát của dòng thư viện. Release notes của patch/minor cho biết:

- Bug nào được sửa.
- Framework hoặc JDK nào được bổ sung hỗ trợ.
- Dependency bắc cầu nào được nâng.
- Property hoặc default nào thay đổi.
- Class, method hoặc package nào được thêm, đổi hoặc loại bỏ.
- Có workaround hoặc breaking behavior nào cần chú ý.

Ví dụ, nếu project dùng springdoc 2.8.6, trang v2 là tài liệu nền tảng. Khi điều tra lỗi chỉ xuất hiện từ 2.8.5 lên 2.8.6, cần đọc changelog/release của 2.8.5 và 2.8.6 thay vì chỉ đọc lại getting started.

Không dùng một bài blog cũ hoặc câu trả lời trên diễn đàn làm bằng chứng thay thế cho release note chính thức. Nếu phải dùng workaround từ cộng đồng, kiểm chứng nó trên phiên bản đang chạy và ghi lại giới hạn.

## 9. Kiểm tra version của dependency đã resolve trong Maven

POM có thể khai báo version qua property:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>2.x.y</version>
    </dependency>
</dependencies>
~~~

2.x.y chỉ là placeholder. Dùng version cụ thể đã được xác nhận tương thích hoặc quản lý qua BOM/catalog của tổ chức.

Kiểm tra dependency thực tế:

~~~bash
./mvnw dependency:tree -Dincludes=org.springdoc
~~~

Nếu version bị ghi đè bởi dependencyManagement hoặc profile, xem effective POM:

~~~bash
./mvnw help:effective-pom
~~~

Nếu cùng lúc thấy nhiều artifact Springdoc thuộc các major khác nhau, tìm dependency kéo theo và xử lý trước khi dựa vào tài liệu của một version duy nhất.

## 10. Kiểm tra version đã resolve trong Gradle

Với Gradle, version khai báo trong build.gradle hoặc libs.versions.toml có thể khác version cuối cùng do constraints, platform hoặc conflict resolution.

Kiểm tra:

~~~bash
./gradlew dependencyInsight --dependency springdoc-openapi --configuration runtimeClasspath
~~~

Xem toàn bộ runtime dependencies:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Nếu ứng dụng có nhiều source set hoặc module, dùng configuration đúng nơi chứa code đang chạy. Ví dụ dependency của testRuntimeClasspath không nhất thiết giống runtimeClasspath.

Sau khi tìm được version được resolve, chọn tài liệu đúng major và đọc release notes tương ứng.

## 11. Xác định phiên bản trong artifact đã đóng gói

Dependency tree của workspace có thể khác artifact đang chạy trong container hoặc máy chủ.

Nếu ứng dụng dùng executable JAR, có thể kiểm tra nội dung:

~~~bash
jar tf application.jar
~~~

Tìm các JAR lồng trong BOOT-INF/lib, ví dụ:

~~~text
BOOT-INF/lib/springdoc-openapi-starter-webmvc-ui-2.x.y.jar
BOOT-INF/lib/springdoc-openapi-starter-common-2.x.y.jar
~~~

Tên file là một tín hiệu nhanh về version được đóng gói. Với ứng dụng dùng WAR, container image hoặc lớp dependency bên ngoài, kiểm tra artifact thực tế được triển khai và classpath runtime.

Không kết luận chỉ từ file POM của source nếu production đang chạy image được build từ commit hoặc lockfile khác.

## 12. Chọn tài liệu đúng khi gặp lỗi compile

Các lỗi compile thường cho biết source đang dùng API khác với dependency:

| Triệu chứng | Hướng kiểm tra |
|---|---|
| Package import không tồn tại | So sánh package trong code với Javadoc của đúng major |
| Method không tìm thấy | Kiểm tra API signature của release đã resolve |
| Starter không resolve | Kiểm tra tên artifact và major version |
| Annotation không được nhận diện | Kiểm tra Swagger Core dependency và package annotation |
| Cấu hình property không có hiệu lực | Kiểm tra property reference của đúng version |

Ví dụ, một class có thể đã đổi package giữa v1 và v2. Tìm class trong Javadoc/API reference đúng version thay vì thay import theo một bài hướng dẫn cho major khác.

Không sửa bằng cách thêm ngẫu nhiên một dependency Swagger Core hoặc Springdoc cũ vào classpath. Cách đó có thể làm build qua nhưng gây lỗi linkage khi chạy.

## 13. Chọn tài liệu đúng khi lỗi chỉ xuất hiện lúc runtime

Nếu compile thành công nhưng ứng dụng lỗi lúc khởi động hoặc khi gọi /v3/api-docs:

1. Xác nhận version Springdoc được resolve trong runtimeClasspath.
2. Kiểm tra Spring Boot và Spring Framework có nằm trong dải hỗ trợ.
3. Xem dependency tree để phát hiện nhiều major version hoặc Swagger Core bị override.
4. Đọc FAQ và release notes đúng nhánh tài liệu.
5. Xem log auto-configuration và lỗi class loading.
6. Tái hiện bằng một cấu hình tối thiểu trước khi thêm customizer hoặc module phụ.

Các lỗi như NoSuchMethodError, NoClassDefFoundError hoặc ClassNotFoundException thường liên quan tới API/classpath không đồng bộ. Đọc tài liệu của đúng dependency đang được nạp, không chỉ version khai báo trực tiếp.

## 14. Phân biệt phiên bản OpenAPI document với springdoc

Endpoint mặc định thường là:

~~~text
/v3/api-docs
~~~

Trong JSON trả về, trường openapi thể hiện phiên bản đặc tả:

~~~json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Order API",
    "version": "1.0.0"
  }
}
~~~

Ví dụ này có ba giá trị khác nhau:

- 3.1.0 là phiên bản OpenAPI Specification.
- 1.0.0 là phiên bản API do đội sản phẩm công bố.
- Version springdoc là version của dependency trong build, không nằm trong hai trường trên.

Không chọn tài liệu Springdoc v3 chỉ vì JSON có openapi: 3.1.0. Major của springdoc được chọn theo khả năng tương thích với Spring Boot và dependency thực tế.

## 15. Không dùng tài liệu migration thay cho hướng dẫn cấu hình hằng ngày

Migration guide dành cho thời điểm chuyển giữa các major hoặc thay đổi API lớn. Khi ứng dụng đã chạy ổn định trên một dòng:

- Dùng getting started/configuration của đúng major để cấu hình thường ngày.
- Dùng FAQ để điều tra các lỗi đã biết.
- Dùng release notes khi nâng patch/minor.
- Dùng migration guide khi thay major.
- Dùng Javadoc/API reference khi cần xác minh class hoặc method cụ thể.

Không áp dụng toàn bộ hướng dẫn migration vào một project không thực hiện migration. Một số thay đổi chỉ cần thiết khi chuyển nền tảng và có thể làm code cũ thay đổi không cần thiết.

## 16. Đối chiếu Java và Spring Framework requirements

Bảng tương thích Springdoc/Spring Boot không thay thế yêu cầu nền tảng của Spring Boot.

Trước khi nâng:

- Kiểm tra Java version tối thiểu và tối đa được Spring Boot hỗ trợ.
- Kiểm tra Spring Framework version được Boot BOM quản lý.
- Kiểm tra Maven/Gradle version.
- Kiểm tra servlet container hoặc web runtime nếu deploy WAR.
- Kiểm tra thư viện bên thứ ba có hỗ trợ namespace Jakarta hoặc thay đổi của Spring Framework không.

Ví dụ, Spring Boot 4.x dùng Spring Framework 7.x và Java tối thiểu 17 theo system requirements. Nếu một thư viện add-on chỉ hỗ trợ Spring Framework 6, việc chọn Springdoc đúng ma trận vẫn chưa đủ để bảo đảm toàn ứng dụng tương thích.

## 17. Giữ dependency management nhất quán

Trong Maven, ưu tiên Spring Boot parent hoặc dependency management để giữ Spring Framework và các thư viện nền tảng cùng bộ phiên bản. Quản lý springdoc ở một property hoặc dependencyManagement rõ ràng.

Trong Gradle, dùng version catalog, platform/BOM và dependency constraints theo quy ước dự án. Không khai báo cùng một dependency với nhiều version ở các module mà không có chính sách resolution thống nhất.

Tránh override tùy tiện:

- Spring Framework modules.
- Swagger Core.
- Jackson.
- Servlet API hoặc Jakarta API.
- Các module springdoc bắc cầu.

Nếu phải override do một lỗi đã xác nhận, ghi rõ nguyên nhân, phạm vi, version bị ép và test bảo vệ. Không thêm dependency cũ chỉ để làm mất lỗi compile.

## 18. Kiểm tra đúng tài liệu cho MVC, WebFlux và UI/API-only

Major version đúng vẫn chưa đủ nếu mở nhầm phần hướng dẫn cho stack khác.

Hãy xác nhận:

- Ứng dụng dùng Spring MVC hay WebFlux.
- Cần Swagger UI hay chỉ cần JSON/YAML.
- Có dùng Spring Data REST, HATEOAS, security hoặc module tích hợp khác không.
- Endpoint docs có được đặt dưới context path hoặc reverse proxy không.

Trong nhánh tài liệu đã chọn, mở phần module tương ứng. Không sao chép một dependency MVC vào ứng dụng WebFlux chỉ vì ví dụ nằm ở đầu trang.

## 19. Xác minh document được tạo sau khi chọn đúng tài liệu

Sau khi cấu hình theo tài liệu đúng version, khởi động ứng dụng và tải document:

~~~bash
curl -fS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Kiểm tra cấu trúc:

~~~bash
jq '{openapi, info, paths: (.paths | keys)}' openapi.json
~~~

Nếu dùng Swagger UI, xác nhận UI tải được cấu hình và OpenAPI document. Nếu chỉ dùng starter API-only, không kỳ vọng UI assets có mặt.

Kiểm tra thêm:

- Path và HTTP method.
- Request/response schema.
- Parameter name và location.
- Security schemes và requirements.
- Response status và media type.
- Grouped document nếu có.
- Server URL khi chạy sau gateway.

Một trang hướng dẫn đúng version vẫn không bảo đảm cấu hình của ứng dụng đúng; output runtime là bước xác nhận cuối.

## 20. Quản lý Snapshot và prerelease

Snapshot, milestone hoặc release candidate phù hợp khi cần thử tính năng chưa có trong stable release hoặc kiểm tra tương thích với nền tảng mới.

Trước khi dùng prerelease:

1. Xác định rõ lý do cần thử.
2. Đọc release notes của đúng milestone/RC.
3. Cô lập trong branch hoặc môi trường thử nghiệm.
4. Không trộn snapshot và stable modules cùng major nếu không có hướng dẫn.
5. Chạy build, startup, OpenAPI generation và integration tests.
6. Ghi rõ version prerelease trong artifact và deployment metadata.
7. Thay bằng stable release khi đã có bản phù hợp.

Không dùng snapshot làm dependency production chỉ vì nó mới hơn. Snapshot có thể thay đổi mà không giữ tương thích nhị phân hoặc cấu hình.

## 21. Ví dụ quy trình chọn phiên bản hoàn chỉnh

Giả sử dependencyInsight cho thấy:

~~~text
Spring Boot: 3.5.x
Spring Framework: 6.2.x
springdoc-openapi: 2.9.x
Web stack: Spring MVC
UI: enabled
~~~

Quy trình:

1. Đối chiếu Boot 3.5.x với bảng tương thích và xác nhận springdoc 2.9.x nằm trong dải được công bố.
2. Mở tài liệu v2 tại https://springdoc.org/v2/.
3. Chọn phần WebMVC UI vì ứng dụng dùng MVC và cần Swagger UI.
4. Đọc configuration properties của v2 trước khi thay đổi path hoặc UI behavior.
5. Nếu gặp lỗi, mở FAQ v2 và release notes của 2.9.x.
6. Sau khi cấu hình, tải /v3/api-docs và xác nhận path, schema, security.
7. Lưu kết quả contract test cùng build artifact.

Nếu ứng dụng được nâng lên Boot 4, phải đánh giá lại toàn bộ quy trình: chuyển sang dòng springdoc v3 theo bảng tương thích, đọc tài liệu v3, rà soát starter/package và kiểm tra migration của Spring Boot.

## 22. Lỗi thường gặp khi chọn sai tài liệu

| Lỗi | Vì sao xảy ra | Cách khắc phục |
|---|---|---|
| Copy dependency v3 vào Boot 3 | Chọn trang tài liệu hiện hành mà không kiểm tra major | Đối chiếu Boot version và chọn v2 |
| Dùng ví dụ v2 trong Boot 4 | Code sample thuộc Springdoc v2 | Mở tài liệu v3 và migration guide |
| Dùng tài liệu v1 cho starter v2 | Trang cũ có package/artifact khác | Chọn /v2 và kiểm tra resolved dependency |
| Chọn patch mới nhất nhưng Boot minor chưa hỗ trợ | Chỉ so sánh major | Dùng compatibility matrix chi tiết |
| Dùng docs Snapshot cho stable | Nhầm prerelease với stable | Mở release notes và chọn stable phù hợp |
| Compile được nhưng runtime lỗi linkage | Dependency graph bị trộn hoặc override | Xem runtime dependency tree và classpath |
| Swagger UI không có | Dùng starter API-only | Chọn UI starter nếu cần giao diện |
| UI có nhưng document thiếu operation | Sai filter, stack hoặc customizer | Kiểm tra config và OpenAPI JSON |
| Bản local đúng, production sai | Artifact hoặc dependency được deploy khác | Kiểm tra JAR/image và runtime classpath |

## 23. Checklist trước khi áp dụng một hướng dẫn

- [ ] Đã xác định Spring Boot version thực tế.
- [ ] Đã xác định springdoc version thực tế trong runtimeClasspath.
- [ ] Đã kiểm tra Java và Spring Framework requirements.
- [ ] Đã đối chiếu đúng hàng trong compatibility matrix.
- [ ] Đã mở đúng nhánh tài liệu v1, v2 hoặc v3.
- [ ] Đã chọn đúng MVC/WebFlux và UI/API-only.
- [ ] Ví dụ dependency dùng đúng artifact và major version.
- [ ] Property và API được xác nhận trong tài liệu của version đang dùng.
- [ ] Release notes được đọc khi thay patch/minor.
- [ ] Migration guide được dùng khi thay major.
- [ ] Không có nhiều major Springdoc hoặc Swagger Core bị trộn.
- [ ] OpenAPI JSON được tải và kiểm tra sau thay đổi.
- [ ] Integration/contract test xác nhận document và runtime.
- [ ] Artifact production được xác minh là đúng build đã kiểm tra.

## 24. Nguyên tắc duy trì tài liệu theo phiên bản

- Ghi lại Spring Boot, Java và springdoc version trong hồ sơ build/release.
- Lưu dependency tree hoặc SBOM của artifact đã triển khai.
- Đặt link tới tài liệu versioned trong hướng dẫn nội bộ của dự án.
- Không dùng trang latest làm tham chiếu duy nhất cho hệ thống cũ.
- Khi nâng version, kiểm tra compatibility matrix trước, release notes sau và migration guide nếu đổi major.
- Cập nhật code sample nội bộ sau khi xác nhận trên version thực tế.
- Ghi rõ phần nào là stable support, phần nào mới được thử nghiệm.
- Kiểm tra lại tài liệu khi dependency được thay qua BOM hoặc platform.

## Kết luận

Chọn tài liệu Springdoc bắt đầu từ phiên bản Spring Boot và springdoc đã được resolve trong runtime, không bắt đầu từ trang tìm kiếm đầu tiên hoặc version mới nhất. Đối chiếu minor line trong compatibility matrix, mở đúng nhánh v1, v2 hoặc v3, rồi chọn phần MVC/WebFlux và UI/API-only phù hợp. Khi bảng chưa có phiên bản Boot mới, không tự suy diễn tương thích; hãy tìm xác nhận chính thức hoặc đánh dấu tổ hợp là thử nghiệm. Cuối cùng, kiểm tra dependency graph, đọc release notes/migration guide đúng phạm vi và xác minh OpenAPI JSON cùng runtime behavior. Cách làm này giữ cho hướng dẫn, source code và artifact đang triển khai cùng một phiên bản sự thật.

## Tài liệu tham khảo

- [Springdoc documentation hiện hành và compatibility matrix](https://springdoc.org/)
- [Springdoc v2 documentation](https://springdoc.org/v2/)
- [Springdoc v1 documentation](https://springdoc.org/v1/)
- [Springdoc releases](https://github.com/springdoc/springdoc-openapi/releases)
- [Spring Boot system requirements](https://docs.spring.io/spring-boot/system-requirements.html)
- [Spring Boot 4.0 system requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html)
- [Spring Boot 3.5 system requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
