# Điều kiện biên dịch hoặc phụ thuộc cho tính năng đọc Javadoc

springdoc-openapi có thể dùng Javadoc trong mã nguồn Java để bổ sung mô tả cho OpenAPI. Tính năng này cần hai thành phần của Therapi: annotation processor `therapi-runtime-javadoc-scribe` chạy khi biên dịch và thư viện `therapi-runtime-javadoc` có mặt lúc ứng dụng chạy.

Hai thành phần có nhiệm vụ khác nhau. Annotation processor đọc comment Javadoc từ source code và ghi chúng thành tài nguyên trên classpath. Thư viện runtime đọc các tài nguyên đó để springdoc-openapi đưa nội dung vào tài liệu OpenAPI. Chỉ thêm thư viện runtime hoặc chỉ thêm annotation processor đều chưa đủ.

## 1. Javadoc được dùng ở những vị trí nào?

Theo tích hợp Javadoc của springdoc-openapi, các nội dung sau được ánh xạ vào OpenAPI:

| Vị trí Javadoc | Vị trí trong OpenAPI | Ví dụ |
|---|---|---|
| Comment của method | `description` của `@Operation` | Mô tả mục đích endpoint |
| Thẻ `@return` của method | `description` của response | Giải thích dữ liệu response |
| Comment của field/attribute trong DTO | `description` của `@Schema` cho field | Giải thích ý nghĩa thuộc tính |

Ví dụ controller:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/products")
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    /**
     * Tìm sản phẩm theo mã định danh.
     *
     * @return thông tin sản phẩm tương ứng với mã đã yêu cầu
     */
    @GetMapping("/{id}")
    public ProductResponse getById(@PathVariable String id) {
        // Tìm và trả về sản phẩm
        return productService.findById(id);
    }
}

interface ProductService {
    ProductResponse findById(String id);
}
~~~

Comment trên method được dùng làm mô tả operation; nội dung `@return` được dùng làm mô tả response. Nếu cần mô tả path parameter `id`, hãy khai báo thêm `@Parameter(description = "...")` hoặc annotation tương ứng. Không nên mặc định rằng mọi thẻ Javadoc như `@param` hay `@throws` đều tự động trở thành metadata OpenAPI.

Thẻ `@return` cung cấp mô tả cho response được springdoc suy ra từ method. Nếu operation có nhiều status code hoặc nhiều response body, khai báo từng response bằng `@ApiResponse` để mô tả đầy đủ hợp đồng.

Ví dụ DTO:

~~~java
public class ProductResponse {

    /** Mã định danh duy nhất của sản phẩm. */
    private String id;

    /** Tên hiển thị của sản phẩm trong danh mục. */
    private String name;

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
~~~

Comment của field có thể trở thành mô tả schema property tương ứng. Kết quả cuối cùng cần được kiểm tra trong `/v3/api-docs`, vì tên property và schema còn chịu ảnh hưởng của Jackson, accessor và cấu hình model converter.

## 2. Vì sao cần cả annotation processor và runtime library?

Therapi chia công việc thành hai giai đoạn:

1. **Compile time:** `therapi-runtime-javadoc-scribe` đọc comment trong source Java và ghi nội dung vào classpath resources khi biên dịch.
2. **Runtime:** `therapi-runtime-javadoc` đọc các resource đã được tạo để ứng dụng có thể truy xuất Javadoc khi springdoc xây dựng OpenAPI.

| Thành phần | Thời điểm cần | Vai trò |
|---|---|---|
| `therapi-runtime-javadoc-scribe` | Compile time | Annotation processor trích xuất Javadoc từ source |
| `therapi-runtime-javadoc` | Runtime | Đọc Javadoc đã được đóng gói trên classpath |
| springdoc-openapi starter | Runtime | Dùng metadata để tạo OpenAPI JSON/YAML |

Nếu thiếu processor, comment chưa được ghi thành tài nguyên. Nếu thiếu runtime library, ứng dụng không có thành phần đọc những tài nguyên đó. Tài liệu springdoc cảnh báo tính năng Javadoc có thể thất bại âm thầm khi thiếu một trong hai thành phần; vì vậy không nên chỉ kiểm tra việc ứng dụng khởi động thành công.

Không cần chạy lệnh `javadoc` để tạo HTML documentation. Cơ chế này dùng annotation processor trong quá trình biên dịch Java, sau đó đọc metadata ở runtime.

## 3. Chọn springdoc starter phù hợp

Javadoc support không thay thế starter dành cho web stack. Chọn starter theo Spring MVC hoặc WebFlux và nhu cầu giao diện:

| Nhu cầu | Starter thường dùng |
|---|---|
| Spring MVC, chỉ cung cấp OpenAPI JSON/YAML | `springdoc-openapi-starter-webmvc-api` |
| Spring MVC, có cả Swagger UI | `springdoc-openapi-starter-webmvc-ui` |
| Spring WebFlux, chỉ cung cấp OpenAPI JSON/YAML | `springdoc-openapi-starter-webflux-api` |
| Spring WebFlux, có cả Swagger UI | `springdoc-openapi-starter-webflux-ui` |

Hướng dẫn Javadoc của springdoc v2 nêu các starter `webmvc-api` và `webflux-api` cho trường hợp chỉ cần endpoint OpenAPI. Nếu ứng dụng cần Swagger UI, dùng starter UI tương ứng với web stack. Dù chọn starter nào, vẫn phải cấu hình cặp Therapi processor/runtime.

Ví dụ dưới đây dùng springdoc v2 cho Spring Boot 3 và phiên bản Therapi `0.15.0` được tài liệu springdoc v2 minh họa. Hãy chọn springdoc starter tương thích với dòng Spring Boot của dự án và quản lý version thống nhất bằng BOM hoặc dependency management.

Không trộn hướng dẫn giữa major version: tài liệu springdoc v1 từng hướng dẫn artifact `springdoc-openapi-javadoc`, trong khi hướng dẫn v2 sử dụng trực tiếp cặp `therapi-runtime-javadoc` và `therapi-runtime-javadoc-scribe` như các ví dụ bên dưới. Với Spring Boot 4/springdoc v3, chọn starter thuộc dòng tương thích và kiểm tra tài liệu đúng major version trước khi áp dụng.

## 4. Cấu hình Maven

### 4.1. Thêm thư viện runtime

Trong `pom.xml`, thêm runtime library:

~~~xml
<dependency>
    <groupId>com.github.therapi</groupId>
    <artifactId>therapi-runtime-javadoc</artifactId>
    <version>0.15.0</version>
</dependency>
~~~

Thư viện này phải có trên runtime classpath của ứng dụng. Không đặt nó ở scope `test` hoặc `provided` nếu ứng dụng cần đọc Javadoc khi chạy.

### 4.2. Đăng ký annotation processor trong Maven Compiler Plugin

Thêm `therapi-runtime-javadoc-scribe` vào `annotationProcessorPaths`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <annotationProcessorPaths>
                    <path>
                        <groupId>com.github.therapi</groupId>
                        <artifactId>therapi-runtime-javadoc-scribe</artifactId>
                        <version>0.15.0</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Khi dùng Spring Boot parent hoặc Maven plugin management của dự án, có thể bỏ phần version của compiler plugin nếu version đã được quản lý tập trung. Điều quan trọng là processor phải thực sự nằm trên processor path của lần compile source chứa Javadoc.

Nếu dự án còn dùng Lombok, MapStruct hoặc annotation processor khác, khai báo chúng trong cùng `annotationProcessorPaths`. Khi cấu hình processor path tường minh, không nên giả định các processor khác vẫn được tự động tìm thấy từ compile classpath.

### 4.3. Chạy build sạch

Sau khi thay đổi cấu hình, chạy:

~~~bash
mvn clean package
~~~

`clean` loại bỏ output biên dịch cũ để tránh kiểm tra nhầm metadata được tạo từ lần build trước. `package` biên dịch source, chạy annotation processor và đóng gói ứng dụng.

## 5. Cấu hình Gradle

Với Gradle Java plugin, khai báo runtime library trong `implementation` và annotation processor trong `annotationProcessor`:

~~~groovy
dependencies {
    implementation "com.github.therapi:therapi-runtime-javadoc:0.15.0"
    annotationProcessor "com.github.therapi:therapi-runtime-javadoc-scribe:0.15.0"
}
~~~

Nếu dùng Gradle Kotlin DSL (`build.gradle.kts`):

~~~kotlin
dependencies {
    implementation("com.github.therapi:therapi-runtime-javadoc:0.15.0")
    annotationProcessor("com.github.therapi:therapi-runtime-javadoc-scribe:0.15.0")
}
~~~

`annotationProcessor` gắn processor với tác vụ biên dịch Java. Không đặt processor vào `implementation` với mục đích thay thế cấu hình này; dependency runtime không tự bảo đảm annotation processor được gọi.

Chạy build sạch:

~~~bash
./gradlew clean bootJar
~~~

Trên Windows có thể dùng:

~~~powershell
.\gradlew.bat clean bootJar
~~~

Nếu dự án chỉ tạo JAR thông thường, dùng tác vụ `jar` thay cho `bootJar` theo plugin đang áp dụng.

## 6. Điều kiện của môi trường biên dịch

Để Javadoc được trích xuất ổn định, kiểm tra các điều kiện sau:

- Source Java chứa comment phải được biên dịch với `therapi-runtime-javadoc-scribe` trên processor path.
- Annotation processing không bị tắt bằng cấu hình compiler như `-proc:none`.
- CI và máy lập trình viên dùng cùng cấu hình Maven/Gradle, tránh tình trạng IDE tạo output khác build server.
- Với IntelliJ IDEA, bật annotation processing trong phần cấu hình compiler nếu IDE tự biên dịch source.
- Với dự án nhiều module, module chứa source DTO/controller cần chạy processor khi biên dịch.
- Runtime application phải có `therapi-runtime-javadoc` và các resource do processor tạo phải được đóng gói cùng class hoặc JAR chứa source đã xử lý.

Nếu build bằng Maven hoặc Gradle nhưng IDE chạy compiler riêng, việc build thành công trong terminal không đảm bảo IDE cũng tạo metadata tương tự. Hãy bật annotation processing trong IDE hoặc ủy quyền build/run cho Maven/Gradle.

### 6.1. Dự án nhiều module

Giả sử cấu trúc dự án:

~~~text
application/
  pom.xml
domain-api/
  pom.xml
  src/main/java/...
web-app/
  pom.xml
  src/main/java/...
~~~

Nếu DTO nằm trong `domain-api`, annotation processor phải chạy khi biên dịch `domain-api`. Chỉ thêm processor ở `web-app` không thể trích xuất ngược comment từ một JAR DTO đã được biên dịch mà thiếu metadata.

Ứng dụng cuối cùng cần runtime library để đọc metadata từ các dependency JAR trên classpath. Với Maven multi-module, có thể quản lý cấu hình compiler plugin ở parent để các module chứa source cần tài liệu được kế thừa. Với Gradle multi-project, khai báo `annotationProcessor` trong từng subproject có Java source cần xử lý.

## 7. Quy tắc ưu tiên giữa Javadoc và Swagger annotations

Javadoc là cách bổ sung mô tả từ source code, còn Swagger annotations cho phép kiểm soát trực tiếp nội dung OpenAPI. Khi cả hai cùng cung cấp description cho một vị trí, springdoc ưu tiên giá trị trong Swagger annotation.

Ví dụ:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

/**
 * Tìm sản phẩm theo mã từ danh mục.
 */
@Operation(
    summary = "Tra cứu sản phẩm",
    description = "Mô tả chính thức được dùng trong OpenAPI."
)
@GetMapping("/{id}")
public ProductResponse getById(@PathVariable String id) {
    // ...
}
~~~

Trong trường hợp này, `description` từ `@Operation` được dùng thay cho comment Javadoc. Có thể tận dụng quy tắc này khi cần ghi đè mô tả chung bằng nội dung chính xác hơn cho hợp đồng API.

Tương tự, nếu field có `@Schema(description = "...")`, giá trị annotation sẽ được ưu tiên cho schema property. Tránh duy trì hai mô tả mâu thuẫn; nếu dùng annotation để ghi đè, hãy xem đó là nội dung chính thức của tài liệu.

## 8. Phân biệt Javadoc extraction với -parameters

Một số cấu hình Java compiler thường bị nhầm với tính năng đọc Javadoc:

| Cấu hình | Mục đích |
|---|---|
| Therapi annotation processor | Trích xuất comment Javadoc thành classpath resource |
| Therapi runtime library | Đọc resource Javadoc lúc ứng dụng chạy |
| Compiler option `-parameters` | Giữ tên tham số method trong bytecode để reflection có thể đọc tên tham số |

`-parameters` không trích xuất Javadoc và không thay thế `therapi-runtime-javadoc-scribe`. Ngược lại, Therapi không thay thế `-parameters` nếu dự án cần giữ tên tham số cho các cơ chế reflection khác.

Nếu muốn mô tả parameter trong OpenAPI, dùng `@Parameter` khi cần nội dung chính xác. Không dựa vào việc có Javadoc processor để suy ra mọi mô tả cho `@PathVariable`, `@RequestParam` hoặc `@RequestHeader`.

## 9. Kiểm tra Javadoc đã đi vào OpenAPI

Sau khi build và khởi động ứng dụng:

1. Mở `/v3/api-docs`.
2. Tìm operation của method có Javadoc.
3. Kiểm tra `description` có nội dung comment method.
4. Kiểm tra response description có nội dung `@return`.
5. Tìm schema DTO và kiểm tra property description có nội dung comment field.
6. Nếu có Swagger UI, mở operation và schema để kiểm tra nội dung hiển thị.

Ví dụ một phần OpenAPI kỳ vọng:

~~~yaml
paths:
  /products/{id}:
    get:
      description: Tìm sản phẩm theo mã định danh.
      responses:
        "200":
          description: thông tin sản phẩm tương ứng với mã đã yêu cầu
components:
  schemas:
    ProductResponse:
      type: object
      properties:
        id:
          type: string
          description: Mã định danh duy nhất của sản phẩm.
        name:
          type: string
          description: Tên hiển thị của sản phẩm trong danh mục.
~~~

Nội dung YAML trên là minh họa kết quả mong đợi. Tên schema, path, status và cấu trúc JSON thực tế phụ thuộc controller, DTO, Jackson và cấu hình OpenAPI của ứng dụng.

Nếu Javadoc không xuất hiện, kiểm tra lần lượt:

1. Runtime dependency `therapi-runtime-javadoc` có trong runtime classpath không?
2. Annotation processor `therapi-runtime-javadoc-scribe` có được gọi khi compile module chứa source không?
3. Annotation processing có bị tắt trong IDE hoặc build profile không?
4. JAR chứa class DTO/controller có mang theo resource metadata do processor tạo không?
5. Ứng dụng đang chạy đúng artifact mới sau `clean package` hoặc `clean bootJar` không?
6. Có Swagger annotation `description` đang ghi đè Javadoc không?

Tài liệu springdoc lưu ý rằng thiếu thành phần Javadoc có thể không làm ứng dụng khởi động thất bại. Vì vậy, việc endpoint `/v3/api-docs` trả về HTTP 200 chưa chứng minh Javadoc đã được đọc.

## 10. Lỗi thường gặp

**Chỉ thêm `therapi-runtime-javadoc`.** Runtime library không tự đọc source Javadoc nếu compile chưa chạy annotation processor. Thêm `therapi-runtime-javadoc-scribe` vào processor path.

**Chỉ thêm annotation processor.** Processor có thể tạo resource nhưng ứng dụng thiếu runtime reader. Thêm `therapi-runtime-javadoc` vào runtime classpath.

**Đặt processor trong `implementation`.** Dependency thông thường không thay thế cấu hình `annotationProcessor` của Gradle hoặc `annotationProcessorPaths` của Maven.

**IDE không bật annotation processing.** Build từ IDE có thể không tạo metadata. Bật annotation processing hoặc dùng Maven/Gradle để build.

**Chỉ cấu hình processor ở module ứng dụng.** Nếu Javadoc nằm trong DTO thuộc module khác, processor phải chạy ở module chứa DTO khi module đó được biên dịch.

**Build incremental giữ lại output cũ.** Dùng `clean` rồi build lại để kiểm tra việc trích xuất từ source hiện tại.

**Dùng Javadoc và `@Operation` nhưng thấy nội dung annotation.** Đây là quy tắc ưu tiên của springdoc. Swagger annotation description được dùng khi cả hai cùng tồn tại.

**Cho rằng `-parameters` bật Javadoc support.** Tùy chọn này giữ tên tham số trong bytecode, không tạo resource Javadoc.

**Cho rằng tạo Javadoc HTML là đủ.** Javadoc HTML do Maven Javadoc Plugin hoặc lệnh `javadoc` tạo không thay thế metadata runtime mà Therapi cần.

## 11. Danh sách rà soát trước khi đưa vào CI

- [ ] Chọn springdoc starter đúng với Spring MVC hoặc WebFlux.
- [ ] Có `therapi-runtime-javadoc` trên runtime classpath.
- [ ] Có `therapi-runtime-javadoc-scribe` trên annotation processor path.
- [ ] Version Therapi được quản lý thống nhất.
- [ ] Annotation processing không bị tắt.
- [ ] Module chứa controller/DTO có Javadoc đã chạy processor.
- [ ] Resource metadata được đóng gói trong artifact.
- [ ] CI thực hiện clean build trước khi tạo artifact phát hành.
- [ ] `/v3/api-docs` hiển thị method, response và field description mong đợi.
- [ ] Swagger annotation description được dùng có chủ đích khi cần ghi đè Javadoc.
- [ ] Không nhầm Javadoc extraction với compiler option `-parameters`.

## Tài liệu tham khảo

- [springdoc-openapi v2 – Javadoc support](https://springdoc.org/v2/#javadoc-support): mapping Javadoc vào operation, response và schema; dependency cùng annotation processor cần thiết.
- [Therapi Runtime Javadoc](https://github.com/dnault/therapi-runtime-javadoc): cách annotation processor ghi Javadoc vào classpath resources và runtime library đọc lại.
- [Therapi Runtime Javadoc Scribe trên Maven Central](https://central.sonatype.com/artifact/com.github.therapi/therapi-runtime-javadoc-scribe): tọa độ artifact annotation processor.
- [Maven Compiler Plugin – Annotation Processor Paths](https://maven.apache.org/plugins/maven-compiler-plugin/compile-mojo.html#annotationProcessorPaths): cấu hình processor path trong Maven.
- [Gradle – Java Plugin dependency configurations](https://docs.gradle.org/current/userguide/java_plugin.html#sec:java_plugin_and_dependency_management): cấu hình `annotationProcessor` và runtime dependencies.
