# Javadoc như nguồn bổ sung mô tả khi được cấu hình hỗ trợ

Javadoc thường được viết ngay cạnh method và field để giải thích mục đích, dữ liệu đầu vào và kết quả của mã Java. Springdoc-openapi có thể đọc một số Javadoc comment để bổ sung mô tả cho OpenAPI document. Nhờ vậy, cùng một phần giải thích có thể hỗ trợ người đọc source code và người tiêu dùng API trên Swagger UI.

Khả năng này cần được cấu hình đúng. Springdoc không tự đọc mọi Javadoc chỉ vì project có comment trong source. Cần có thư viện `therapi-runtime-javadoc` để đọc metadata lúc runtime và annotation processor `therapi-runtime-javadoc-scribe` để trích xuất Javadoc trong quá trình biên dịch. Nếu thiếu hai phần này, hỗ trợ Javadoc có thể không hoạt động mà không báo lỗi rõ ràng.

## 1. Javadoc đóng vai trò gì trong tài liệu OpenAPI?

Springdoc xây dựng OpenAPI từ controller, cấu hình Spring, kiểu Java và Swagger annotations. Javadoc là một nguồn mô tả bổ sung cho một số thành phần đã được suy luận.

Với các ánh xạ được tài liệu springdoc công bố:

| Nguồn Javadoc | Thành phần OpenAPI được bổ sung |
|---|---|
| Comment của method | `description` của `@Operation` |
| Thẻ `@return` của method | `description` của response trong `@Operation` |
| Comment của field/attribute trong model | `description` của property trong `@Schema` |

Ví dụ, comment trên method controller có thể trở thành mô tả operation; phần `@return` giải thích nội dung response; comment trên field DTO giải thích thuộc tính trong schema.

Javadoc giúp bổ sung nội dung bằng ngôn ngữ tự nhiên. Nó không tự xác định HTTP method, URL, status code, kiểu bảo mật hoặc toàn bộ cấu trúc request/response. Những thông tin đó vẫn được springdoc suy luận từ Spring mapping và kiểu dữ liệu, hoặc cần khai báo bằng Swagger annotations khi không thể suy luận đủ.

## 2. Cơ chế hoạt động: xử lý lúc compile và đọc lúc runtime

Javadoc comment là comment trong source code. JVM không giữ toàn bộ comment này như một phần của reflection metadata thông thường. Vì vậy, springdoc cần một cơ chế riêng để có thể đọc nội dung comment khi tạo tài liệu.

`therapi-runtime-javadoc-scribe` là annotation processor. Trong lúc biên dịch, processor đọc Javadoc và tạo metadata có thể được sử dụng sau đó. `therapi-runtime-javadoc` là thư viện runtime cung cấp khả năng truy xuất metadata đó. Springdoc tích hợp với thư viện runtime để đưa mô tả vào OpenAPI.

Luồng xử lý có thể hình dung như sau:

```text
Java source
   |
   | Javadoc comments
   v
therapi-runtime-javadoc-scribe
   |
   | metadata được tạo khi compile
   v
Build output
   |
   | runtime dependency
   v
therapi-runtime-javadoc
   |
   v
springdoc-openapi
   |
   v
OpenAPI JSON/YAML -> Swagger UI
```

Nếu chỉ thêm thư viện runtime nhưng không chạy annotation processor, metadata cần thiết có thể không được tạo. Nếu chỉ cấu hình processor nhưng thiếu runtime library, springdoc không có thành phần đọc metadata lúc chạy. Cần khai báo đủ cả hai.

## 3. Chọn dependency springdoc phù hợp với web stack

Trong springdoc-openapi 2.x, hỗ trợ Javadoc đã được tích hợp vào `springdoc-openapi-starter-common`. Không cần thêm module cũ `springdoc-openapi-javadoc` cho dự án đang dùng starter 2.x.

Chọn starter theo stack:

| Ứng dụng | Chỉ cần OpenAPI JSON/YAML | Cần Swagger UI |
|---|---|---|
| Spring MVC | `springdoc-openapi-starter-webmvc-api` | `springdoc-openapi-starter-webmvc-ui` |
| Spring WebFlux | `springdoc-openapi-starter-webflux-api` | `springdoc-openapi-starter-webflux-ui` |

Nếu project đã có starter UI, không cần thêm starter API chỉ để bật Javadoc. Các starter UI tương ứng đã kéo theo phần API cần thiết. Phiên bản springdoc phải phù hợp với Spring Boot của project: nhánh 2.x dành cho Spring Boot 3, nhánh 3.x dành cho Spring Boot 4; các project Spring Boot 2 cũ sử dụng nhánh 1.x theo hướng dẫn tương ứng.

Khác biệt về module Javadoc giữa các major version:

| Nhánh springdoc | Cách tích hợp Javadoc |
|---|---|
| v1.8.x | Dùng module riêng `springdoc-openapi-javadoc` cùng starter UI/API tương ứng và Therapi processor/runtime |
| v2.x | Javadoc support được đưa vào `springdoc-openapi-starter-common`; không thêm module v1 |
| v3.x | Dùng starter tương ứng của nhánh hiện tại; không dùng module `springdoc-openapi-javadoc` của v1 |

Không trộn artifact giữa các major version. Khi nâng cấp từ v1 lên v2, bỏ module Javadoc cũ và dùng starter v2 tương thích với Spring Boot 3.

## 4. Thêm runtime library và annotation processor với Maven

Với springdoc 2.x, thêm `therapi-runtime-javadoc` vào dependencies và `therapi-runtime-javadoc-scribe` vào danh sách annotation processor.

```xml
<dependencies>
    <!-- Các dependency Spring Boot và springdoc hiện có -->
    <dependency>
        <groupId>com.github.therapi</groupId>
        <artifactId>therapi-runtime-javadoc</artifactId>
        <version>0.15.0</version>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
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
```

Đặt processor trong `annotationProcessorPaths` để Maven Compiler Plugin chạy nó trong quá trình compile. Nếu project đã cấu hình các processor khác như Lombok hoặc MapStruct, hãy thêm Therapi vào danh sách hiện có thay vì thay thế toàn bộ danh sách; nếu không, các processor cũ có thể ngừng chạy.

Phiên bản `0.15.0` là phiên bản được ví dụ trong tài liệu springdoc v2. Nếu tổ chức quản lý phiên bản dependency tập trung, hãy đưa phiên bản vào dependency management hoặc property theo quy ước của project.

## 5. Cấu hình Gradle

Với Gradle Kotlin DSL (`build.gradle.kts`):

```kotlin
dependencies {
    runtimeOnly("com.github.therapi:therapi-runtime-javadoc:0.15.0")
    annotationProcessor("com.github.therapi:therapi-runtime-javadoc-scribe:0.15.0")
}
```

Với Gradle Groovy DSL (`build.gradle`):

```groovy
dependencies {
    runtimeOnly 'com.github.therapi:therapi-runtime-javadoc:0.15.0'
    annotationProcessor 'com.github.therapi:therapi-runtime-javadoc-scribe:0.15.0'
}
```

`annotationProcessor` đặt processor trên compile classpath dành riêng cho xử lý annotation; `runtimeOnly` đưa thư viện đọc Javadoc vào runtime classpath. Nếu project dùng nhiều source set hoặc module Java riêng, bảo đảm processor và runtime dependency được khai báo ở module thực sự biên dịch controller/DTO và chạy ứng dụng.

## 6. Viết Javadoc cho controller method

Comment của method được dùng làm `description` của operation. Thẻ `@return` được dùng làm mô tả response.

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    /**
     * Trả về các sản phẩm mà người gọi hiện tại được phép xem.
     * Kết quả được sắp xếp theo thời điểm tạo, mới nhất trước.
     *
     * @return danh sách sản phẩm phù hợp với truy vấn hiện tại
     */
    @GetMapping
    List<ProductResponse> listProducts() {
        return productService.listVisibleProducts();
    }
}
```

Khi Javadoc support hoạt động, springdoc có thể tạo operation tương tự:

```yaml
paths:
  /api/products:
    get:
      description: >-
        Trả về các sản phẩm mà người gọi hiện tại được phép xem.
        Kết quả được sắp xếp theo thời điểm tạo, mới nhất trước.
      responses:
        '200':
          description: danh sách sản phẩm phù hợp với truy vấn hiện tại
```

Đây là hình dạng minh họa của phần metadata liên quan; document thực tế còn có thể chứa `operationId`, tags, content và schema được suy luận từ controller cùng DTO.

Nên viết mô tả method theo hành vi API mà client quan sát được. Tránh đưa chi tiết triển khai như tên repository, câu SQL, cache nội bộ hoặc thuật toán không ảnh hưởng hợp đồng.

## 7. Viết Javadoc cho field của DTO

Comment của field trong model có thể trở thành `description` của property trong schema.

```java
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.util.UUID;

@Schema(name = "ProductResponse", description = "Thông tin sản phẩm được API trả về")
public class ProductResponse {

    /** Mã định danh ổn định được cấp cho sản phẩm. */
    private UUID id;

    /** Tên sản phẩm hiển thị cho khách hàng. */
    private String name;

    /** Giá bán hiện tại theo đơn vị tiền tệ của cửa hàng. */
    private BigDecimal price;

    // Constructors, getters and setters
}
```

Phần schema có thể được sinh tương tự:

```yaml
ProductResponse:
  type: object
  properties:
    id:
      type: string
      format: uuid
      description: Mã định danh ổn định được cấp cho sản phẩm.
    name:
      type: string
      description: Tên sản phẩm hiển thị cho khách hàng.
    price:
      type: number
      description: Giá bán hiện tại theo đơn vị tiền tệ của cửa hàng.
```

Javadoc field chỉ bổ sung ý nghĩa của thuộc tính. Kiểu dữ liệu thường được springdoc suy luận từ Java type/Jackson model; ràng buộc như required, min/max, format hoặc enum có thể cần Bean Validation và `@Schema`.

## 8. Kết hợp Javadoc với Swagger annotations

Javadoc và Swagger annotations có thể cùng tồn tại. Khi cả hai cung cấp description cho cùng thành phần, tài liệu springdoc quy định mô tả từ Swagger annotation được ưu tiên.

Ví dụ method:

```java
/**
 * Trả về các sản phẩm mà người gọi hiện tại được phép xem.
 *
 * @return danh sách sản phẩm phù hợp với truy vấn hiện tại
 */
@Operation(description = "Trả về các sản phẩm đang hoạt động trong cửa hàng hiện tại.")
@GetMapping
List<ProductResponse> listProducts() {
    return productService.listVisibleProducts();
}
```

`@Operation(description = ...)` là nguồn description được ưu tiên cho operation này. Javadoc vẫn có thể hữu ích cho tài liệu source code, nhưng sẽ không ghi đè mô tả tường minh trong Swagger annotation.

Ví dụ field:

```java
/** Giá trước khi áp dụng chương trình khuyến mãi. */
@Schema(description = "Giá cuối cùng khách hàng phải thanh toán.")
private BigDecimal price;
```

`@Schema(description = ...)` được ưu tiên cho property. Cách kết hợp này hữu ích khi muốn Javadoc giải thích code cho lập trình viên, trong khi OpenAPI dùng cách diễn đạt ngắn gọn và hướng tới client hơn.

## 9. Javadoc không thay thế `@Operation`, `@ApiResponse` và `@Parameter`

Javadoc phù hợp với mô tả dạng văn bản. Với metadata có cấu trúc, nên tiếp tục dùng Swagger annotations hoặc Spring mapping.

| Thông tin cần mô tả | Cơ chế phù hợp |
|---|---|
| HTTP method và path | `@GetMapping`, `@PostMapping`, `@RequestMapping` |
| Summary và mô tả operation tường minh | `@Operation` |
| Response code và response schema | `@ApiResponse`, `@ApiResponses` |
| Query/path/header parameter | `@Parameter`, `@Parameters` và Spring parameter annotations |
| Request body schema | `@RequestBody` của Spring cùng `@Content`/`@Schema` khi cần mô tả rõ |
| Field description mặc định | Javadoc trên field hoặc `@Schema(description = ...)` |
| Security scheme và requirement | `@SecurityScheme`, `@SecurityRequirement` |
| Example cụ thể | `@ExampleObject`, `@Parameter(example = ...)`, `@Schema(example = ...)` |
| Required, giới hạn và validation | Bean Validation và `@Schema` |

Tài liệu springdoc nêu rõ các ánh xạ Javadoc chính là method comment, `@return` và field/attribute comment. Không nên mặc định mọi tag Javadoc như `@throws`, `@see`, `@since` hoặc `@param` đều trở thành phần tử OpenAPI tương ứng. Với parameter description, khai báo `@Parameter` là cách tường minh và dễ kiểm tra hơn.

## 10. Quy tắc ưu tiên khi description bị khai báo nhiều nơi

Khi một thành phần có cả Javadoc và Swagger annotation, Swagger annotation có description sẽ thắng. Do đó, nếu cập nhật Javadoc mà Swagger UI không thay đổi, hãy kiểm tra xem `@Operation(description = ...)`, `@ApiResponse(description = ...)` hoặc `@Schema(description = ...)` có đang cung cấp giá trị riêng hay không.

Nên thống nhất quy ước trong nhóm:

- Dùng Javadoc làm mô tả mặc định khi chưa cần nội dung OpenAPI đặc biệt.
- Dùng Swagger annotation khi cần mô tả riêng cho hợp đồng API.
- Không duy trì hai đoạn description khác nhau mà không có lý do; chúng dễ khiến source documentation và API documentation mâu thuẫn.
- Nếu annotation ghi đè Javadoc, hãy cập nhật cả hai khi nội dung có ý nghĩa cho cả người đọc code và API consumer.

## 11. Kiểm tra dependency và annotation processor đã hoạt động

Khi Javadoc không xuất hiện trong OpenAPI, hãy kiểm tra theo thứ tự:

1. Project đang dùng đúng springdoc starter cho Spring MVC hoặc WebFlux.
2. Runtime classpath có `therapi-runtime-javadoc`.
3. Compile có chạy `therapi-runtime-javadoc-scribe`.
4. Processor được cấu hình trong đúng module chứa source controller và DTO.
5. Build tool thực sự chạy annotation processing, không bị cấu hình compiler tắt.
6. Các file source có Javadoc comment ở đúng method hoặc field.
7. Không có Swagger annotation description ghi đè Javadoc.
8. Ứng dụng được chạy từ build output mới nhất sau khi thêm processor.

Với Maven, xem log compile để xác nhận compiler plugin và annotation processor được thực thi. Với Gradle, kiểm tra configuration `annotationProcessor` của source set tương ứng. Sau khi mới bật processor, thực hiện clean build để chắc chắn metadata được tạo lại; không chỉ khởi động lại bằng class output cũ.

Lưu ý: tài liệu springdoc cảnh báo nếu thiếu runtime library hoặc annotation processor, Javadoc support có thể fail silently. Vì vậy, việc ứng dụng khởi động thành công không chứng minh tính năng đã được cấu hình đầy đủ.

## 12. Xác minh nội dung trong OpenAPI JSON/YAML

Sau khi chạy ứng dụng, lấy OpenAPI document mặc định:

```bash
curl -fS http://localhost:8080/v3/api-docs -o openapi.json
```

Kiểm tra operation description:

```bash
jq '.paths["/api/products"].get.description' openapi.json
```

Kiểm tra response description:

```bash
jq '.paths["/api/products"].get.responses["200"].description' openapi.json
```

Kiểm tra field description trong schema:

```bash
jq '.components.schemas.ProductResponse.properties.name.description' openapi.json
```

Nếu ứng dụng xuất YAML, có thể kiểm tra `/v3/api-docs.yaml` hoặc dùng YAML parser. Các URL này có thể thay đổi nếu project cấu hình `springdoc.api-docs.path` hoặc chạy dưới context path.

Kết quả cần đối chiếu với nội dung Javadoc trong source. Đừng chỉ kiểm tra Swagger UI; kiểm tra JSON/YAML giúp xác định description đã thực sự được ghi vào OpenAPI document hay chỉ hiển thị ở một lớp giao diện.

## 13. Kiểm tra trên Swagger UI

Swagger UI hiển thị description được lấy từ OpenAPI document:

- Method Javadoc xuất hiện trong phần mô tả operation.
- `@return` có thể xuất hiện ở mô tả response tương ứng.
- Field Javadoc xuất hiện trong mô tả property của schema model.

Nếu description dài, nên chia thành các câu hoặc đoạn ngắn. Nội dung cần giải thích ý nghĩa, điều kiện sử dụng, đơn vị, múi giờ hoặc quy tắc nghiệp vụ mà tên field không thể hiện. Tránh lặp lại nguyên văn tên thuộc tính hoặc viết đoạn văn quá dài trong một dòng.

Swagger UI chỉ trình bày OpenAPI document. Nếu document không có description, cần sửa nguồn metadata hoặc cấu hình processor; thay đổi CSS hay giao diện UI không giải quyết được nguyên nhân.

## 14. Ví dụ hoàn chỉnh: controller và DTO dùng Javadoc

Ví dụ kết hợp Javadoc cho method/field và annotation cho các phần cần cấu trúc:

```java
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.util.UUID;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import java.util.List;

@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    /**
     * Trả về các sản phẩm thuộc danh mục được yêu cầu.
     * Kết quả được sắp xếp theo sản phẩm mới tạo gần đây nhất.
     *
     * @return các sản phẩm thuộc danh mục đã chọn
     */
    @Operation(operationId = "listProducts", summary = "Liệt kê sản phẩm")
    @GetMapping
    List<ProductResponse> listProducts(
            @Parameter(description = "Lọc theo danh mục sản phẩm", example = "phu-kien")
            @RequestParam(required = false) String category) {
        return productService.list(category);
    }
}

@Schema(name = "ProductResponse")
class ProductResponse {

    /** Mã định danh ổn định do dịch vụ sản phẩm cấp. */
    private UUID id;

    /** Tên sản phẩm hiển thị trên cửa hàng. */
    private String name;

    /** Giá bán hiện tại theo đơn vị tiền tệ của cửa hàng. */
    private BigDecimal price;

    // Constructors, getters and setters
}
```

Trong ví dụ:

- `@Operation` cung cấp `operationId` và summary tường minh.
- Javadoc của `listProducts` bổ sung operation description.
- Javadoc `@return` bổ sung response description.
- Javadoc của `id`, `name` và `price` bổ sung property description trong `ProductResponse`.
- `@RequestParam` cùng kiểu Java cung cấp thông tin parameter; nếu cần description riêng cho query parameter, thêm `@Parameter`.

Đây là ví dụ minh họa các vị trí metadata. Khi đưa vào project, bổ sung import, service implementation, getters/setters và response annotations phù hợp với cấu trúc thực tế.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Javadoc không xuất hiện trong OpenAPI | Thiếu runtime library hoặc annotation processor | Thêm `therapi-runtime-javadoc` và `therapi-runtime-javadoc-scribe` |
| Build thành công nhưng không có description | Annotation processor không chạy; hỗ trợ có thể fail silently | Kiểm tra cấu hình Maven/Gradle và clean build |
| Method description không thay đổi | `@Operation(description = ...)` đang ghi đè Javadoc | Kiểm tra Swagger annotation description |
| Field description không thay đổi | `@Schema(description = ...)` đang được khai báo | Cập nhật annotation hoặc bỏ description trùng nếu muốn dùng Javadoc |
| `@return` không xuất hiện như mong đợi | Method không có Javadoc tag hoặc response annotation đã có description | Kiểm tra `@return` và `@ApiResponse(description = ...)` |
| Chỉ một module có Javadoc | Processor chỉ cấu hình ở một module | Khai báo processor cho từng module biên dịch source cần tài liệu |
| Maven ngừng chạy Lombok/MapStruct sau khi thêm Therapi | Ghi đè `annotationProcessorPaths` hiện có | Hợp nhất tất cả processor trong cùng cấu hình |
| Swagger UI không hiển thị nội dung mới | OpenAPI JSON/YAML chưa được tạo lại hoặc đang xem group khác | Kiểm tra trực tiếp đúng docs endpoint và build output |
| Dựa vào `@param` nhưng parameter không có description | Không phải mọi Javadoc tag đều được tài liệu hỗ trợ giống nhau | Dùng `@Parameter(description = ...)` để khai báo tường minh |
| Comment chứa chi tiết triển khai gây khó hiểu cho client | Javadoc viết cho người duy trì code, không hướng tới API consumer | Viết mô tả theo hành vi API hoặc ghi đè bằng Swagger annotation |

## 16. Nguyên tắc viết Javadoc tốt cho API

- Mô tả method theo hành vi mà client quan sát được, không chỉ nhắc lại tên method.
- Dùng `@return` để giải thích ý nghĩa dữ liệu trả về, không chỉ ghi “result”.
- Mô tả field bằng ý nghĩa nghiệp vụ, đơn vị, định dạng hoặc quy tắc quan trọng.
- Giữ Javadoc ngắn gọn, rõ ràng và không chứa thông tin nội bộ nhạy cảm.
- Dùng `@Operation`, `@ApiResponse`, `@Parameter` và `@Schema` khi cần metadata có cấu trúc hoặc nội dung riêng cho OpenAPI.
- Bảo đảm runtime library và annotation processor cùng được cấu hình.
- Nếu project có nhiều annotation processor, hợp nhất cấu hình thay vì ghi đè processor hiện tại.
- Kiểm tra OpenAPI JSON/YAML sau compile và chạy ứng dụng.
- Giữ mô tả trong Javadoc và Swagger annotations nhất quán để tránh tài liệu mâu thuẫn.

## Kết luận

Javadoc có thể là nguồn bổ sung hữu ích cho springdoc-openapi: comment của method trở thành operation description, `@return` trở thành response description và comment của field trở thành schema property description. Để tính năng hoạt động, cần cả `therapi-runtime-javadoc` ở runtime và `therapi-runtime-javadoc-scribe` trong annotation processor. Với springdoc 2.x, hỗ trợ Javadoc đã nằm trong starter common; không cần module Javadoc riêng của v1. Khi một Swagger annotation cũng khai báo description, annotation được ưu tiên. Hãy dùng Javadoc cho mô tả tự nhiên, dùng Swagger annotations cho metadata có cấu trúc, rồi xác minh kết quả trong OpenAPI JSON/YAML và Swagger UI.

## Tài liệu tham khảo

- [springdoc-openapi v2 – Javadoc support, section 3.13](https://springdoc.org/v2/)
- [springdoc-openapi v2 – Migrating from v1](https://springdoc.org/v2/migrating-from-springdoc-v1.html)
- [Therapi Runtime Javadoc](https://github.com/dnault/therapi-runtime-javadoc)
