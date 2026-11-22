# Phân biệt nhóm tài liệu với @Tag và phiên bản API

Khi một ứng dụng Spring Boot có nhiều controller, nhiều nhóm người dùng hoặc nhiều phiên bản endpoint, tài liệu OpenAPI có thể trở nên dài và khó tra cứu. springdoc-openapi cung cấp **document group** để tạo nhiều tài liệu OpenAPI từ cùng một ứng dụng. Trong mỗi tài liệu, **@Tag** phân loại operation theo chức năng. Còn **phiên bản API** xác định hợp đồng mà client đang tích hợp và cách server duy trì các hành vi tương thích.

Ba khái niệm này liên quan nhưng giải quyết ba vấn đề khác nhau:

- Group quyết định operation nào xuất hiện trong một tài liệu OpenAPI.
- Tag đặt operation vào các nhóm chức năng bên trong một tài liệu.
- API version xác định phiên bản hợp đồng và hành vi endpoint mà client sử dụng.

Hiểu rõ ranh giới này giúp tổ chức Swagger UI, duy trì API v1/v2 và tránh nhầm việc chia tài liệu với việc thay đổi endpoint hoặc quyền truy cập.

## 1. Phân biệt group, tag và API version

| Khái niệm | Mục đích | Cách khai báo phổ biến | Kết quả |
|---|---|---|---|
| Document group | Tạo một tài liệu OpenAPI từ một tập operation được lọc | GroupedOpenApi, springdoc.group-configs | Một tài liệu riêng, truy cập bằng URL nhóm |
| Tag | Phân loại operation theo chức năng trong tài liệu | @Tag, @Operation(tags = ...) | Nhóm operation trong Swagger UI và OpenAPI |
| API version | Quản lý hợp đồng API theo phiên bản | Path, header, media type hoặc chiến lược định tuyến khác | Các endpoint/hành vi tương ứng với từng phiên bản |

Ví dụ một ứng dụng thương mại điện tử có thể tổ chức như sau:

- Group public-v1 chứa các endpoint công khai của API v1.
- Group internal-v1 chứa endpoint quản trị và tích hợp nội bộ của API v1.
- Trong group public-v1, các operation được gắn tag Catalog, Orders và Customers.
- API v2 có thể thay đổi cấu trúc response hoặc quy tắc nghiệp vụ và được công bố trong group public-v2.

Group không tự tạo phiên bản API, tag không lọc endpoint ra khỏi tài liệu, và việc tạo group không thay đổi route runtime. Các endpoint vẫn do Spring MVC và cấu hình ứng dụng quyết định.

## 2. Document group trong springdoc-openapi

Một document group là một góc nhìn tài liệu được tạo từ các endpoint của ứng dụng. Mỗi group có thể chọn controller theo package, đường dẫn hoặc các điều kiện lọc mà phiên bản springdoc hỗ trợ.

Ví dụ:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiGroupConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public-v1")
            .pathsToMatch("/api/v1/public/**")
            .build();
    }

    @Bean
    GroupedOpenApi internalApi() {
        return GroupedOpenApi.builder()
            .group("internal-v1")
            .pathsToMatch("/api/v1/internal/**")
            .build();
    }
}
~~~

Hai bean trên tạo hai tài liệu riêng. Các endpoint khớp /api/v1/public/** được đưa vào group public-v1; endpoint khớp /api/v1/internal/** được đưa vào group internal-v1. Tên group là định danh dùng trong URL tài liệu.

Với Springdoc 2.x, GroupedOpenApi thường nằm trong package org.springdoc.core.models. Ở các dòng phiên bản cũ, package có thể khác; hãy dùng API tương ứng với dependency thực tế của dự án.

### 2.1. Lọc theo package và đường dẫn

Có thể chọn endpoint theo package controller:

~~~java
@Bean
GroupedOpenApi catalogApi() {
    return GroupedOpenApi.builder()
        .group("catalog")
        .packagesToScan("com.example.store.catalog.web")
        .build();
}
~~~

Hoặc lọc theo đường dẫn:

~~~java
@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/partner/**", "/api/v1/partners/**")
        .pathsToExclude("/partner/internal/**")
        .build();
}
~~~

packagesToScan phù hợp khi cấu trúc package phản ánh ranh giới module. pathsToMatch phù hợp khi URL thể hiện ranh giới API. Có thể kết hợp điều kiện lọc nếu cần; hãy xác minh tập operation cuối cùng trong tài liệu được sinh ra, đặc biệt khi một controller có nhiều mapping.

Không nên dùng package name làm hợp đồng công khai cho client. Package là cách tổ chức mã nguồn và có thể thay đổi khi tái cấu trúc. URL và ý nghĩa endpoint mới là phần client tích hợp.

## 3. Cấu hình group bằng application.yml

Ngoài cách tạo bean, có thể khai báo group bằng cấu hình:

~~~yaml
springdoc:
  group-configs:
    - group: public-v1
      paths-to-match:
        - /api/v1/public/**
    - group: internal-v1
      paths-to-match:
        - /api/v1/internal/**
~~~

Cấu hình này tương đương về mục đích với việc tạo các GroupedOpenApi bean đơn giản. Nên chọn một cách quản lý nhất quán để tránh khai báo trùng group bằng cả YAML và Java config.

Một số thuộc tính lọc khác có thể thay đổi theo phiên bản springdoc, chẳng hạn package được quét, path bị loại trừ hoặc điều kiện theo header/media type. Khi sử dụng thuộc tính nâng cao, hãy kiểm tra reference của đúng phiên bản đang cài và xác nhận kết quả /v3/api-docs/{group}.

## 4. URL tài liệu của từng group

springdoc thường cung cấp tài liệu mặc định tại:

~~~text
/v3/api-docs
~~~

Với group tên public-v1, tài liệu của group thường được truy cập tại:

~~~text
/v3/api-docs/public-v1
~~~

Với group internal-v1:

~~~text
/v3/api-docs/internal-v1
~~~

Swagger UI có thể hiển thị danh sách tài liệu để người dùng chọn:

~~~yaml
springdoc:
  swagger-ui:
    urls:
      - name: Public API v1
        url: /v3/api-docs/public-v1
      - name: Internal API v1
        url: /v3/api-docs/internal-v1
~~~

Tên hiển thị trong Swagger UI có thể thân thiện với người dùng hơn tên group. Tên group nên ngắn, ổn định và phù hợp làm một phần URL.

Việc group xuất hiện trong dropdown Swagger UI chỉ giúp chọn tài liệu. Nó không tạo cơ chế phân quyền. Nếu tài liệu nội bộ không được phép công khai, cần bảo vệ endpoint tài liệu và Swagger UI bằng cấu hình bảo mật của ứng dụng hoặc hạ tầng.

## 5. @Tag phân loại operation bên trong tài liệu

@Tag định nghĩa một nhóm chức năng để gom các operation liên quan. Annotation này thường được đặt ở cấp controller:

~~~java
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/products")
@Tag(
    name = "Catalog",
    description = "Tra cứu và quản lý thông tin sản phẩm."
)
public class ProductController {
    // Các endpoint sản phẩm.
}
~~~

Trong tài liệu OpenAPI, tag có tên Catalog giúp Swagger UI hiển thị các operation của controller dưới cùng một nhóm chức năng.

Có thể gắn tag cụ thể cho operation bằng thuộc tính tags của @Operation:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/featured")
@Operation(
    summary = "Lấy sản phẩm nổi bật",
    tags = {"Catalog"}
)
public List<ProductResponse> featured() {
    return productService.findFeatured();
}
~~~

Nếu dùng nhiều tag, operation có thể xuất hiện trong nhiều nhóm tag của cùng tài liệu. Tag không thay đổi URL, HTTP method, quyền truy cập hoặc cách Spring gọi controller.

### 5.1. Khai báo tag ở cấp tài liệu

Có thể định nghĩa mô tả tag ở cấp OpenAPI:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.tags.Tag;

@OpenAPIDefinition(
    info = @Info(
        title = "Store API",
        version = "1.0.0"
    ),
    tags = {
        @Tag(
            name = "Catalog",
            description = "Các thao tác liên quan đến sản phẩm."
        ),
        @Tag(
            name = "Orders",
            description = "Các thao tác liên quan đến đơn hàng."
        )
    }
)
public class OpenApiDefinition {
}
~~~

Định nghĩa tag ở cấp tài liệu hữu ích khi muốn kiểm soát tên và mô tả nhất quán. Các tag được khai báo có thể xuất hiện trong danh sách tag của OpenAPI ngay cả khi không cần suy ra mô tả từ từng controller.

## 6. Group và tag có thể kết hợp với nhau

Một tài liệu group có thể chứa nhiều tag. Ví dụ:

~~~text
Swagger UI
└── Public API v1 (document group)
    ├── Catalog (tag)
    │   ├── GET /api/v1/public/products
    │   └── GET /api/v1/public/products/{id}
    ├── Orders (tag)
    │   ├── POST /api/v1/public/orders
    │   └── GET /api/v1/public/orders/{id}
    └── Customers (tag)
        └── GET /api/v1/public/customers/me
~~~

Group quyết định tập operation được đưa vào tài liệu Public API v1. Tag tổ chức các operation đã nằm trong tài liệu đó theo nghiệp vụ.

Một operation có thể thuộc cùng một tag trong nhiều group nếu operation đó được đưa vào nhiều tài liệu. Ví dụ endpoint tra cứu sản phẩm có thể xuất hiện trong cả tài liệu public và partner nhưng được gắn tag Catalog ở cả hai.

Không nên tạo tag tên Public API v1 chỉ để mô phỏng document group. Làm như vậy chỉ đổi nhãn phân loại trong Swagger UI; tất cả operation vẫn thuộc cùng một tài liệu OpenAPI.

## 7. Phiên bản API là phiên bản của hợp đồng

API version thể hiện một phiên bản hợp đồng mà client có thể tích hợp. Một phiên bản mới thường xuất hiện khi có thay đổi không tương thích như:

- Đổi hoặc xóa field response mà client đang sử dụng.
- Đổi kiểu dữ liệu của field.
- Đổi URL hoặc HTTP method.
- Thay đổi ý nghĩa nghiệp vụ của một operation.
- Thay đổi quy tắc validation hoặc định dạng dữ liệu theo cách làm client cũ không còn hoạt động.

Không phải mọi thay đổi đều cần tăng major version. Bổ sung field tùy chọn hoặc operation mới thường có thể tương thích ngược nếu client được thiết kế để bỏ qua dữ liệu chưa biết. Quy tắc cụ thể cần được xác định trong chính sách versioning của API.

Group không tự tạo API version. Một group tên v2 nhưng vẫn trỏ đến cùng operation v1 không làm endpoint trở thành v2. Ngược lại, endpoint /api/v2/products vẫn là API v2 dù được đưa vào group có tên public.

## 8. Phân biệt openapi version và info.version

Trong tài liệu OpenAPI có hai giá trị phiên bản rất dễ nhầm:

| Trường | Ví dụ | Ý nghĩa |
|---|---|---|
| openapi | 3.1.0 | Phiên bản đặc tả OpenAPI được dùng để viết tài liệu |
| info.version | 2.0.0 | Phiên bản API được tài liệu mô tả |

Ví dụ:

~~~yaml
openapi: 3.1.0
info:
  title: Store API
  version: 2.0.0
~~~

openapi: 3.1.0 không có nghĩa API đang ở phiên bản 3.1.0. Nó chỉ nói tài liệu tuân theo phiên bản OpenAPI 3.1. info.version: 2.0.0 mới là phiên bản API được công bố trong tài liệu này.

Với springdoc, có thể khai báo metadata chung bằng @OpenAPIDefinition hoặc bean OpenAPI. Nếu có nhiều phiên bản API được tạo thành các group riêng, cần bảo đảm mỗi tài liệu có info.version đúng với API mà nó mô tả.

## 9. Versioning bằng URL path

Một chiến lược dễ hiểu và dễ phân nhóm tài liệu là đặt version trong URL:

~~~text
/api/v1/products
/api/v2/products
~~~

Controller có thể được tách theo phiên bản:

~~~java
@RestController
@RequestMapping("/api/v1/products")
public class ProductV1Controller {

    @GetMapping("/{id}")
    public ProductV1Response getById(@PathVariable Long id) {
        return productService.findV1Response(id);
    }
}
~~~

~~~java
@RestController
@RequestMapping("/api/v2/products")
public class ProductV2Controller {

    @GetMapping("/{id}")
    public ProductV2Response getById(@PathVariable Long id) {
        return productService.findV2Response(id);
    }
}
~~~

Sau đó tạo group cho từng version:

~~~java
@Bean
GroupedOpenApi apiV1() {
    return GroupedOpenApi.builder()
        .group("public-v1")
        .pathsToMatch("/api/v1/**")
        .build();
}

@Bean
GroupedOpenApi apiV2() {
    return GroupedOpenApi.builder()
        .group("public-v2")
        .pathsToMatch("/api/v2/**")
        .build();
}
~~~

Ưu điểm của path versioning là URL thể hiện phiên bản rõ ràng, dễ định tuyến, cache và lọc tài liệu. Nhược điểm là version trở thành một phần của URL và có thể cần duy trì nhiều route trong giai đoạn chuyển đổi.

## 10. Cấu hình info.version riêng cho từng group

Khi có nhiều group đại diện cho các phiên bản API, nên đặt metadata riêng để tài liệu không cùng hiển thị một version. Có thể thêm OpenApiCustomizer cho từng group:

~~~java
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class VersionedOpenApiConfiguration {

    @Bean
    GroupedOpenApi publicV1() {
        return GroupedOpenApi.builder()
            .group("public-v1")
            .pathsToMatch("/api/v1/**")
            .addOpenApiCustomizer(openApi -> openApi.info(
                new Info()
                    .title("Store Public API")
                    .version("1.0.0")
                    .description("Hợp đồng API công khai phiên bản 1.")
            ))
            .build();
    }

    @Bean
    GroupedOpenApi publicV2() {
        return GroupedOpenApi.builder()
            .group("public-v2")
            .pathsToMatch("/api/v2/**")
            .addOpenApiCustomizer(openApi -> openApi.info(
                new Info()
                    .title("Store Public API")
                    .version("2.0.0")
                    .description("Hợp đồng API công khai phiên bản 2.")
            ))
            .build();
    }
}
~~~

Customizer trong ví dụ được gắn vào từng GroupedOpenApi, nên metadata info được đặt cho tài liệu tương ứng. Cần kiểm tra /v3/api-docs/public-v1 và /v3/api-docs/public-v2 để xác nhận tiêu đề và info.version không bị ghi đè bởi cấu hình khác.

Nếu dùng @OpenAPIDefinition hoặc bean OpenAPI chung, hãy xem đó là metadata mặc định và cân nhắc customizer riêng cho từng group khi các tài liệu có version khác nhau.

## 11. Versioning bằng header hoặc media type

Không phải API nào cũng đặt version trong URL. Một số hệ thống chọn header:

~~~http
GET /api/products/42
X-API-Version: 2
~~~

Hoặc dùng media type:

~~~http
GET /api/products/42
Accept: application/vnd.example.product-v2+json
~~~

Các cách này giữ URL ổn định nhưng client phải gửi đúng header hoặc media type. Chúng cũng làm việc kiểm thử, cache và cấu hình gateway phức tạp hơn nếu hệ thống không có quy ước thống nhất.

Với các phiên bản dùng chung path và HTTP method, chỉ lọc theo pathsToMatch sẽ không đủ để phân biệt operation. Cần tách controller/package hoặc dùng điều kiện lọc theo header/media type và customizer phù hợp với phiên bản springdoc. Springdoc có các cơ chế lọc bổ sung như headersToMatch hoặc producesToMatch ở những phiên bản hỗ trợ; hãy xác minh cú pháp và kết quả thực tế trước khi dựa vào chúng.

Ví dụ mapping Spring MVC có thể phân biệt header:

~~~java
@GetMapping(
    path = "/api/products/{id}",
    headers = "X-API-Version=1"
)
public ProductV1Response getV1(@PathVariable Long id) {
    return productService.findV1Response(id);
}

@GetMapping(
    path = "/api/products/{id}",
    headers = "X-API-Version=2"
)
public ProductV2Response getV2(@PathVariable Long id) {
    return productService.findV2Response(id);
}
~~~

Đây là ví dụ định tuyến ở runtime. Để tạo hai tài liệu riêng, cần bảo đảm bộ lọc OpenAPI nhận diện đúng hai mapping và mỗi group chỉ chứa operation của version tương ứng. Không giả định pathsToMatch tự phân biệt được chúng vì URL giống nhau.

## 12. Versioning theo package và ranh giới module

Nếu controller v1 và v2 nằm ở package riêng, có thể tạo group theo package:

~~~java
@Bean
GroupedOpenApi versionOne() {
    return GroupedOpenApi.builder()
        .group("v1")
        .packagesToScan("com.example.api.v1")
        .build();
}

@Bean
GroupedOpenApi versionTwo() {
    return GroupedOpenApi.builder()
        .group("v2")
        .packagesToScan("com.example.api.v2")
        .build();
}
~~~

Cách này phù hợp khi tổ chức mã nguồn đã tách controller theo phiên bản. Tuy nhiên, package filter là quy tắc tạo tài liệu, không phải cơ chế bảo đảm tương thích hay định tuyến. Mapping runtime vẫn cần được khai báo rõ trong controller.

## 13. Khi nào group không nên trùng với version?

Group có thể đại diện cho đối tượng đọc tài liệu hoặc phạm vi sản phẩm, còn version là chiều độc lập. Ví dụ:

| Tài liệu | Phạm vi | API version |
|---|---|---|
| public-v1 | API dành cho ứng dụng khách hàng | 1.0.0 |
| public-v2 | API dành cho ứng dụng khách hàng | 2.0.0 |
| partner-v1 | API dành cho đối tác | 1.0.0 |
| internal-v1 | API dùng trong nội bộ | 1.0.0 |

Một API version có thể được trình bày trong nhiều group nếu các nhóm người dùng cần các tập operation khác nhau. Ngược lại, một group có thể bao gồm nhiều module chức năng nhưng vẫn cùng version hợp đồng.

Ví dụ group partner-v1 có thể chứa operation từ Catalog và Orders. Trong tài liệu đó, tag vẫn có thể là Catalog và Orders. Việc tách public/partner là quyết định về phạm vi tài liệu; version vẫn mô tả hợp đồng của API.

Nếu số chiều group tăng quá nhanh, chẳng hạn mọi tổ hợp audience, version và module đều tạo một tài liệu riêng, Swagger UI sẽ khó điều hướng. Hãy chỉ tạo group khi có nhu cầu đọc hoặc phân phối tài liệu thực tế.

## 14. Đánh dấu operation đã deprecated

Khi một operation hoặc field sắp bị loại bỏ, có thể đánh dấu deprecated trong OpenAPI:

~~~java
@GetMapping("/legacy-search")
@Operation(
    summary = "Tìm kiếm sản phẩm theo cách cũ",
    deprecated = true,
    description = "Dùng GET /api/v2/products/search cho tích hợp mới."
)
public List<ProductResponse> legacySearch() {
    return productService.legacySearch();
}
~~~

Với một field schema:

~~~java
public record ProductV1Response(
    Long id,

    @Schema(
        description = "Tên cũ; sẽ được thay thế trong phiên bản sau.",
        deprecated = true
    )
    String legacyName
) {
}
~~~

deprecated = true là thông tin cho người dùng tài liệu và công cụ client. Nó không tự chặn request, không xóa endpoint và không tự chuyển client sang version mới. Việc ngừng hỗ trợ cần có chính sách thời gian, thông báo và kiểm soát runtime riêng.

## 15. Ví dụ OpenAPI thể hiện group, tag và version

Một tài liệu group public-v2 có thể có cấu trúc rút gọn như sau:

~~~yaml
openapi: 3.1.0
info:
  title: Store Public API
  version: 2.0.0
  description: Hợp đồng API công khai phiên bản 2.
tags:
  - name: Catalog
    description: Tra cứu và quản lý sản phẩm.
  - name: Orders
    description: Tạo và tra cứu đơn hàng.
paths:
  /api/v2/products:
    get:
      tags:
        - Catalog
      summary: Lấy danh sách sản phẩm
      responses:
        '200':
          description: Danh sách sản phẩm.
  /api/v2/orders:
    post:
      tags:
        - Orders
      summary: Tạo đơn hàng
      responses:
        '201':
          description: Đơn hàng đã được tạo.
~~~

Trong ví dụ:

- openapi là phiên bản đặc tả OpenAPI.
- info.version là phiên bản API được mô tả.
- tags định nghĩa các nhóm chức năng.
- paths liệt kê các operation được đưa vào tài liệu group.
- Tên group public-v2 được dùng trong cấu hình và URL tài liệu, không phải một field chuẩn riêng trong OpenAPI document.

## 16. Các lỗi thường gặp khi tổ chức tài liệu

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Dùng tag để thay thế document group | Swagger UI chỉ phân loại operation, tài liệu vẫn chứa toàn bộ endpoint | Tạo GroupedOpenApi hoặc group-configs |
| Đặt tên group là v2 nhưng endpoint vẫn là v1 | Người đọc hiểu nhầm version của hợp đồng | Đồng bộ group filter, route và info.version |
| Nghĩ group tạo route runtime | Client gọi URL mới nhưng server không có mapping | Khai báo route/versioning trong Spring MVC riêng |
| Nghĩ group là cơ chế phân quyền | Tài liệu hoặc endpoint nội bộ có thể vẫn truy cập được | Bảo vệ /v3/api-docs/{group} và Swagger UI bằng security |
| Chỉ lọc path khi version nằm trong header | Nhiều mapping cùng path có thể xuất hiện sai group | Lọc theo mapping/header/media type hoặc tách package |
| Dùng info.version để chỉ phiên bản OpenAPI | Công bố nhầm version tài liệu và version API | Phân biệt openapi với info.version |
| Mọi operation dùng tag khác nhau tùy controller | Swagger UI có nhiều nhóm trùng nghĩa | Chuẩn hóa từ điển tag và mô tả |
| Đánh dấu deprecated rồi xóa endpoint ngay | Client chưa kịp chuyển đổi bị lỗi | Có thời gian chuyển tiếp và chính sách ngừng hỗ trợ |
| Tạo quá nhiều group | Người dùng khó chọn đúng tài liệu | Chỉ tạo group theo nhu cầu phân phối/đọc rõ ràng |

## 17. Quy trình thiết kế tài liệu nhiều group và version

Khi tổ chức tài liệu cho một ứng dụng lớn, có thể thực hiện theo trình tự:

1. Xác định các API version đang được hỗ trợ và những thay đổi tương thích giữa chúng.
2. Chọn chiến lược versioning runtime: path, header, media type hoặc cách định tuyến đã thống nhất.
3. Xác định người đọc và phạm vi operation cần công bố: public, partner, internal hoặc theo sản phẩm.
4. Tạo group bằng GroupedOpenApi hoặc springdoc.group-configs theo tiêu chí phù hợp.
5. Đặt tag theo nghiệp vụ để phân loại operation bên trong từng group.
6. Đặt info.title và info.version riêng cho mỗi tài liệu khi cần.
7. Cấu hình Swagger UI để người đọc chọn đúng tài liệu.
8. Bảo vệ endpoint tài liệu theo chính sách truy cập.
9. Kiểm tra /v3/api-docs/{group} và thử endpoint runtime tương ứng.
10. Đánh dấu operation cũ deprecated và quản lý thời điểm ngừng hỗ trợ theo chính sách versioning.

## 18. Kiểm tra tài liệu được sinh ra

Sau khi chạy ứng dụng, kiểm tra các URL:

~~~bash
curl -s http://localhost:8080/v3/api-docs/public-v1
curl -s http://localhost:8080/v3/api-docs/public-v2
~~~

Với từng tài liệu, xác nhận:

- Group chỉ chứa các path và operation dự kiến.
- Không thiếu endpoint cần công bố hoặc xuất hiện endpoint thuộc phạm vi khác.
- Tag có tên, mô tả và phân loại đúng nghiệp vụ.
- info.version đúng với phiên bản API.
- Trường openapi đúng phiên bản đặc tả được cấu hình.
- Operation deprecated được đánh dấu chính xác.
- Các schema và response tương ứng với endpoint runtime.
- Swagger UI hiển thị đúng danh sách tài liệu và tên dễ nhận biết.

Nếu dùng versioning qua header hoặc media type, hãy gọi cùng một URL với từng header/Accept tương ứng và xác minh tài liệu của mỗi group chỉ mô tả đúng mapping. Đây là bước quan trọng vì hai operation có thể cùng path và HTTP method.

## 19. Ghi nhớ

- Document group tạo một tài liệu OpenAPI từ tập operation được lọc.
- GroupedOpenApi và springdoc.group-configs là hai cách phổ biến để khai báo group.
- @Tag và @Operation(tags = ...) phân loại operation bên trong tài liệu.
- Group không tạo endpoint, không đổi hành vi runtime và không cấp quyền truy cập.
- API version là phiên bản hợp đồng; cần được thể hiện nhất quán với chiến lược định tuyến thực tế.
- openapi là phiên bản đặc tả; info.version là phiên bản API được mô tả.
- Path versioning dễ lọc group; header/media type versioning cần điều kiện lọc phù hợp vì nhiều mapping có thể dùng chung URL.
- Một version có thể xuất hiện trong nhiều group; một group cũng có thể chứa nhiều tag.
- deprecated chỉ đánh dấu trong tài liệu, không tự ngừng phục vụ endpoint.
- Luôn kiểm tra từng /v3/api-docs/{group}, Swagger UI và hành vi runtime.

Khi thiết kế tài liệu cho springdoc-openapi, hãy dùng group để chia tài liệu theo phạm vi người đọc hoặc sản phẩm, dùng tag để phân loại operation theo nghiệp vụ và quản lý API version như một phần của hợp đồng tích hợp. Ba lớp được tổ chức riêng nhưng phải khớp nhau trong cấu hình, URL, metadata OpenAPI và hành vi Spring MVC.
