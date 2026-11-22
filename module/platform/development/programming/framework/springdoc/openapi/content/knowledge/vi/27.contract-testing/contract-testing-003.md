# Xác minh path, HTTP method, operationId và tag

OpenAPI mô tả các endpoint mà client có thể gọi, HTTP method được hỗ trợ, định danh operation và nhóm chức năng của API. Khi dùng springdoc-openapi, phần lớn hợp đồng này được suy ra từ `@RequestMapping`, `@GetMapping`, `@PostMapping`, annotation OpenAPI trên controller và cấu hình tài liệu.

Một controller chạy đúng chưa có nghĩa OpenAPI document mô tả đúng. Endpoint có thể bị thiếu do cấu hình scan, path có thể sai vì ghép mapping, operationId có thể thay đổi khi đổi tên method Java, hoặc tag có thể không nhất quán giữa các operation. Ngược lại, tài liệu có thể liệt kê một operation mà route runtime không xử lý được như client mong đợi.

Bài học này xây dựng contract test để xác minh tài liệu do springdoc sinh ra, so sánh path và HTTP method với route thực tế, kiểm tra operationId và tag, đồng thời phát hiện contract drift trong CI.

## Mục tiêu

Sau bài học, bạn có thể:

- Đọc cấu trúc `paths` và operation trong OpenAPI JSON.
- Xác minh path được ghép đúng từ class-level và method-level mapping.
- Kiểm tra HTTP method được công bố đúng với hành vi của endpoint.
- Đặt và kiểm tra `operationId` ổn định, duy nhất trong một OpenAPI document.
- Chuẩn hóa tag ở controller và operation, kiểm tra tag definitions.
- Viết contract test bằng Spring Boot Test, MockMvc và Jackson.
- Phân biệt kiểm tra tài liệu với kiểm tra route runtime.
- Kiểm tra tài liệu theo từng `GroupedOpenApi`.
- Phát hiện path/method bị thêm, xóa hoặc đổi ngoài dự kiến.
- Đưa các kiểm tra hợp đồng vào pipeline CI.

## 1. Hợp đồng path và operation gồm những gì?

Trong OpenAPI, `paths` là một object ánh xạ path template tới Path Item Object. Mỗi path item có thể chứa operation theo HTTP method. Ví dụ:

~~~yaml
paths:
  /api/products:
    get:
      operationId: listProducts
      tags:
        - products
      summary: Liệt kê sản phẩm
      responses:
        '200':
          description: Danh sách sản phẩm
    post:
      operationId: createProduct
      tags:
        - products
      summary: Tạo sản phẩm
      responses:
        '201':
          description: Sản phẩm đã được tạo
  /api/products/{id}:
    get:
      operationId: getProductById
      tags:
        - products
      summary: Lấy sản phẩm theo ID
      responses:
        '200':
          description: Thông tin sản phẩm
~~~

Trong ví dụ:

- `/api/products` và `/api/products/{id}` là path template.
- `get` và `post` là HTTP method, được viết thường trong JSON/YAML OpenAPI.
- `operationId` định danh một operation trong toàn bộ document.
- `tags` phân nhóm operation trong tài liệu và công cụ tiêu thụ.
- `summary` giúp người đọc hiểu mục đích operation.

Path, method, operationId và tag là các phần riêng biệt của hợp đồng. Đổi một trong các phần này có thể ảnh hưởng đến routing, SDK được sinh, tài liệu hoặc automation của client.

### 1.1. Phân biệt server URL và path

OpenAPI ghép server URL với path để tạo URL gọi hoàn chỉnh:

~~~yaml
servers:
  - url: https://api.example.com/catalog
paths:
  /products:
    get:
      operationId: listProducts
~~~

URL hoàn chỉnh là `https://api.example.com/catalog/products`. Prefix triển khai thuộc server URL nếu đó là base path của gateway; path mô tả resource tương đối với server.

Không đưa cùng một prefix vào cả `servers.url` và path nếu không có chủ đích. Ví dụ server đã kết thúc bằng `/catalog` mà path cũng bắt đầu bằng `/catalog` sẽ tạo URL lặp prefix.

Context path, reverse proxy prefix và server URL có thể thay đổi theo môi trường. Contract test nên kiểm tra path resource và server URL riêng, tránh gộp hostname triển khai vào path assertion.

## 2. Path được tạo từ mapping của Spring như thế nào?

Spring MVC ghép mapping ở cấp controller với mapping ở cấp method. Ví dụ:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping
    List<ProductResponse> listProducts() {
        // ...
    }

    @GetMapping("/{id}")
    ProductResponse getProduct(@PathVariable UUID id) {
        // ...
    }

    @PostMapping
    ProductResponse createProduct(
            @RequestBody CreateProductRequest request) {
        // ...
    }
}
~~~

Các route dự kiến là:

| Class mapping | Method mapping | HTTP method | Path được công bố |
|---|---|---|---|
| `/api/products` | `@GetMapping` | GET | `/api/products` |
| `/api/products` | `@GetMapping("/{id}")` | GET | `/api/products/{id}` |
| `/api/products` | `@PostMapping` | POST | `/api/products` |

Hãy kiểm tra path sau khi ghép mapping, không chỉ nhìn annotation ở một cấp.

### 2.1. Path variable

Với `@PathVariable`, tên biến trong path template cần khớp với parameter được mô tả:

~~~java
@GetMapping("/{id}")
@Operation(
    operationId = "getProductById",
    summary = "Lấy sản phẩm theo ID"
)
ProductResponse getProduct(@PathVariable("id") UUID productId) {
    // ...
}
~~~

Path trong OpenAPI là `/api/products/{id}` và parameter có tên `id`. Tên biến Java là `productId` vì annotation đã chỉ rõ `id`. Nếu không khai báo tên tường minh, việc suy ra tên parameter có thể phụ thuộc metadata biên dịch và cấu hình. Với path variable công khai, khai báo tên rõ ràng giúp hợp đồng ổn định.

Path parameter phải được đánh dấu required trong OpenAPI. Đây là yêu cầu của path template; một path parameter tùy chọn không phải cách biểu diễn hợp lệ cho cùng một route.

### 2.2. Mapping có nhiều path

Spring cho phép một handler ánh xạ tới nhiều path:

~~~java
@GetMapping({"/products", "/items"})
@Operation(
    operationId = "listProducts",
    tags = {"products"}
)
List<ProductResponse> listProducts() {
    // ...
}
~~~

Tùy cách springdoc tạo document, mỗi path được công bố thành một Path Item operation. Vì `operationId` phải duy nhất trong một document, không giả định cùng một ID có thể lặp lại cho hai path. Nếu một handler được công bố ở nhiều path, hãy kiểm tra JSON thực tế và đặt định danh riêng hoặc thiết kế một canonical path phù hợp với chính sách API.

### 2.3. Path phân biệt chữ hoa/thường và dấu gạch chéo

Các path `/api/products`, `/api/Products` và `/api/products/` có thể được xem là các path khác nhau trong hợp đồng. Không dựa vào hành vi redirect hoặc tùy chọn path matching của môi trường để coi chúng tương đương.

Chọn một quy ước nhất quán, thường dùng chữ thường và không thêm trailing slash cho collection path. Contract test nên so sánh path string chính xác để phát hiện thay đổi ngoài ý muốn.

### 2.4. Path filter và endpoint bị ẩn

springdoc có thể giới hạn endpoint bằng `pathsToMatch`, `pathsToExclude` hoặc `packagesToScan`. Controller không xuất hiện trong tài liệu chưa chắc route runtime không tồn tại.

Các annotation như `@Hidden` hoặc `@Operation(hidden = true)` có thể loại controller/operation khỏi OpenAPI. Đây là quyết định công bố tài liệu, không phải biện pháp bảo vệ route. Nếu endpoint vẫn được gọi được, hãy kiểm tra authorization riêng.

Khi contract test chạy trên một group tài liệu, chỉ so sánh với tập path dự kiến của group đó. Đừng yêu cầu public group chứa endpoint internal bị loại có chủ đích.

## 3. Xác minh HTTP method

Trong OpenAPI 3.1, các method operation chuẩn là:

`get`, `put`, `post`, `delete`, `options`, `head`, `patch` và `trace`.

HTTP method được biểu diễn bằng property chữ thường trong Path Item Object:

~~~yaml
paths:
  /api/products/{id}:
    get:
      operationId: getProductById
    put:
      operationId: replaceProduct
    patch:
      operationId: updateProduct
    delete:
      operationId: deleteProduct
~~~

Không nhầm method HTTP với tên Java method. Một Java method tên `findAll` có thể xử lý GET; một method tên `create` có thể xử lý POST. Contract test phải kiểm tra HTTP method trong OpenAPI và request method runtime.

### 3.1. Dùng mapping tường minh

Ưu tiên annotation chuyên biệt:

~~~java
@GetMapping
@PostMapping
@PutMapping("/{id}")
@PatchMapping("/{id}")
@DeleteMapping("/{id}")
~~~

Khi dùng `@RequestMapping`, khai báo rõ `method`:

~~~java
@RequestMapping(
    path = "/{id}",
    method = RequestMethod.DELETE
)
void deleteProduct(@PathVariable UUID id) {
    // ...
}
~~~

Mapping không chỉ định method có thể nhận nhiều loại request tại runtime. Điều đó làm hợp đồng khó dự đoán và không nên được dùng cho endpoint resource thông thường.

### 3.2. Một path có nhiều method

Một path có thể chứa nhiều operation:

~~~yaml
paths:
  /api/products:
    get:
      operationId: listProducts
    post:
      operationId: createProduct
~~~

Contract test nên kiểm tra tập method chính xác cho mỗi path. Việc chỉ kiểm tra GET tồn tại sẽ không phát hiện một DELETE vô tình bị công bố.

### 3.3. Method phụ thuộc phiên bản OpenAPI

HTTP QUERY được mô tả bằng operation `query` trong OpenAPI 3.2. Nếu document của dự án là OpenAPI 3.1, không thêm property này như một method chuẩn. Khi chuyển sang 3.2, cần xác minh Springdoc, parser, validator, Swagger UI, generator, Spring MVC/WebFlux và gateway đều xử lý đúng.

Bài học này dùng tập method OpenAPI 3.1 trong ví dụ test cơ bản. Nếu dự án đã xác nhận dùng OAS 3.2, hãy bổ sung `query` vào tập method được kiểm tra và thêm fixture/runtime test riêng.

## 4. operationId là định danh ổn định của operation

`operationId` là định danh duy nhất cho một operation trong OpenAPI document. Công cụ sinh SDK thường dùng giá trị này để tạo tên method hoặc hàm client. Một số công cụ tài liệu và contract automation cũng dùng nó để đối chiếu operation qua các lần phát hành.

Ví dụ:

~~~yaml
paths:
  /api/products:
    get:
      operationId: listProducts
    post:
      operationId: createProduct
  /api/products/{id}:
    get:
      operationId: getProductById
~~~

### 4.1. Khai báo operationId tường minh

Với Springdoc, có thể dùng `@Operation(operationId = "...")`:

~~~java
@GetMapping
@Operation(
    operationId = "listProducts",
    summary = "Liệt kê sản phẩm",
    tags = {"products"}
)
List<ProductResponse> listProducts() {
    // ...
}
~~~

Nếu để Springdoc tự sinh ID, tên được tạo ra có thể phụ thuộc method name, controller hoặc cấu hình. Đổi tên method Java trong một refactor nội bộ có thể làm thay đổi operationId và kéo theo đổi tên hàm trong SDK. Với API có client bên ngoài, đặt operationId tường minh để kiểm soát thay đổi.

### 4.2. Quy ước đặt tên

Chọn một quy ước nhất quán, ví dụ:

| Hành động | operationId |
|---|---|
| Liệt kê sản phẩm | `listProducts` |
| Lấy theo ID | `getProductById` |
| Tạo mới | `createProduct` |
| Thay thế toàn bộ | `replaceProduct` |
| Cập nhật một phần | `updateProduct` |
| Xóa | `deleteProduct` |

Nên dùng tên thể hiện hành động và tài nguyên. Tránh ID chung chung như `get`, `create` hoặc tên phụ thuộc controller như `productControllerMethod1`.

### 4.3. Kiểm tra tính duy nhất

OpenAPI yêu cầu operationId nếu được cung cấp phải duy nhất trong document. Nên áp dụng chính sách dự án mạnh hơn: mọi operation công khai đều phải có operationId không rỗng và ổn định.

Khi kiểm tra, duyệt tất cả operation trong `paths`, không chỉ các path mà test đang quan tâm. Nếu document dùng webhooks hoặc callbacks, mở rộng kiểm tra sang những operation ở các cấu trúc đó.

Không dùng operationId giống nhau cho hai HTTP method khác nhau trên cùng path. Ví dụ GET và POST `/api/products` vẫn là hai operation riêng và cần ID riêng.

## 5. Tag dùng để nhóm operation

Tag giúp tổ chức API theo tài nguyên hoặc miền nghiệp vụ. Ví dụ:

~~~yaml
tags:
  - name: products
    description: Các thao tác quản lý sản phẩm
paths:
  /api/products:
    get:
      operationId: listProducts
      tags:
        - products
~~~

Swagger UI thường dùng tag để nhóm operation thành các phần có thể mở rộng/thu gọn. SDK generator có thể dùng tag để nhóm method thành class hoặc namespace. Vì vậy, đổi tag có thể làm thay đổi cách tổ chức SDK ngay cả khi URL và response không đổi.

### 5.1. Khai báo tag ở controller

Có thể mô tả tag cho controller bằng `@Tag`:

~~~java
import io.swagger.v3.oas.annotations.tags.Tag;

@RestController
@RequestMapping("/api/products")
@Tag(
    name = "products",
    description = "Các thao tác quản lý sản phẩm"
)
class ProductController {
    // ...
}
~~~

Để hợp đồng rõ ràng, có thể gắn tag tường minh trên từng operation:

~~~java
@GetMapping
@Operation(
    operationId = "listProducts",
    tags = {"products"}
)
List<ProductResponse> listProducts() {
    // ...
}
~~~

Không dựa hoàn toàn vào tên class hoặc tên package để suy ra tag nếu tên nhóm là một phần của hợp đồng tài liệu.

### 5.2. Tag definitions và operation tags

OpenAPI có hai nơi liên quan:

- Root-level `tags` khai báo metadata như tên và description của nhóm.
- `operation.tags` gắn operation vào một hoặc nhiều nhóm.

Tên tag phải khớp chính xác giữa hai nơi. Một operation có thể dùng tag chưa được khai báo ở root theo đặc tả, nhưng để tài liệu nhất quán, dự án có thể đặt policy yêu cầu mọi tag đang dùng phải có root definition.

Tên tag phân biệt chữ hoa/thường theo giá trị chuỗi. `products` và `Products` không nên được xem là cùng một tag.

### 5.3. Một operation có nhiều tag

OpenAPI cho phép một operation có nhiều tag:

~~~java
@Operation(
    operationId = "searchProducts",
    tags = {"products", "search"}
)
~~~

Chỉ dùng nhiều tag khi operation thực sự thuộc nhiều nhóm. Tránh thêm tag tùy tiện để làm operation xuất hiện ở nhiều nơi vì có thể làm giao diện tài liệu và SDK trở nên khó đoán.

## 6. Tổ chức annotation cho hợp đồng ổn định

Ví dụ controller có path, method, operationId và tag tường minh:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/products")
@Tag(
    name = "products",
    description = "Các thao tác quản lý sản phẩm"
)
class ProductController {

    @GetMapping
    @Operation(
        operationId = "listProducts",
        summary = "Liệt kê sản phẩm",
        tags = {"products"}
    )
    List<ProductResponse> listProducts() {
        // Gọi service và trả kết quả
        return List.of();
    }

    @GetMapping("/{id}")
    @Operation(
        operationId = "getProductById",
        summary = "Lấy sản phẩm theo ID",
        tags = {"products"}
    )
    ProductResponse getProduct(@PathVariable("id") UUID id) {
        // Gọi service và trả kết quả
        return null;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(
        operationId = "createProduct",
        summary = "Tạo sản phẩm",
        tags = {"products"}
    )
    ProductResponse createProduct(
            @RequestBody CreateProductRequest request) {
        // Gọi service và trả kết quả
        return null;
    }
}
~~~

`ProductResponse` và `CreateProductRequest` là DTO của ứng dụng. Phần thân method được rút gọn để tập trung vào metadata hợp đồng; khi chạy test tích hợp, thay phần thân bằng xử lý service thật hoặc mock phù hợp.

Điểm cần giữ nhất quán:

- Class mapping tạo prefix `/api/products`.
- Method mapping tạo path cụ thể.
- Annotation Spring xác định HTTP method runtime.
- `@Operation.operationId` xác định ID công khai.
- `@Operation.tags` gắn operation vào nhóm đã định.
- `@Tag` cung cấp mô tả cho nhóm.

## 7. Lấy OpenAPI JSON trong contract test

Springdoc thường cung cấp JSON tại `/v3/api-docs`. Nếu cấu hình `springdoc.api-docs.path` hoặc dùng group, endpoint có thể khác. Hãy dùng đúng URL trong cấu hình ứng dụng.

Ví dụ dependency cho ứng dụng Spring MVC:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Trong contract test, dùng MockMvc gọi endpoint tài liệu và Jackson đọc JSON:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiContractTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    protected JsonNode readOpenApi() throws Exception {
        MvcResult result = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn();

        return objectMapper.readTree(
            result.getResponse().getContentAsString()
        );
    }
}
~~~

Các import chính đặt ở đầu file test:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import java.util.HashSet;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Nếu tài liệu được bảo vệ bởi Spring Security, test cần cung cấp principal hoặc token test phù hợp. Đừng mở endpoint tài liệu công khai chỉ để test vượt qua authorization.

## 8. Kiểm tra path, method, operationId và tag bằng Jackson

Đọc JSON thành JsonNode giúp kiểm tra cấu trúc mà không phụ thuộc thứ tự property trong file. Thêm test và các helper sau vào cùng class `OpenApiContractTest`:

~~~java
private static final Set<String> HTTP_METHODS = Set.of(
    "get", "put", "post", "delete",
    "options", "head", "patch", "trace"
);

@Test
void documentsProductPathsAndOperations() throws Exception {
    JsonNode document = readOpenApi();
    JsonNode paths = document.path("paths");

    assertEquals(
        Set.of("/api/products", "/api/products/{id}"),
        fieldNames(paths)
    );

    assertEquals(
        Set.of("get", "post"),
        methodsAt(paths, "/api/products")
    );
    assertEquals(
        Set.of("get"),
        methodsAt(paths, "/api/products/{id}")
    );

    assertOperation(
        document, "/api/products", "get",
        "listProducts", "products"
    );
    assertOperation(
        document, "/api/products", "post",
        "createProduct", "products"
    );
    assertOperation(
        document, "/api/products/{id}", "get",
        "getProductById", "products"
    );

    assertEquals(
        Set.of("products"),
        tagNames(paths.path("/api/products").path("get"))
    );
    assertDeclaredTag(document, "products");
    assertUniqueOperationIds(paths);
}

private static Set<String> fieldNames(JsonNode object) {
    Set<String> names = new HashSet<>();
    object.fieldNames().forEachRemaining(names::add);
    return names;
}

private static Set<String> methodsAt(JsonNode paths, String path) {
    Set<String> methods = new HashSet<>();
    JsonNode pathItem = paths.path(path);

    for (String method : HTTP_METHODS) {
        if (pathItem.has(method)) {
            methods.add(method);
        }
    }
    return methods;
}

private static void assertOperation(
        JsonNode document,
        String path,
        String method,
        String expectedOperationId,
        String expectedTag) {

    JsonNode operation = document
        .path("paths")
        .path(path)
        .path(method);

    assertFalse(
        operation.isMissingNode(),
        () -> "Thiếu operation " + method + " " + path
    );
    assertEquals(
        expectedOperationId,
        operation.path("operationId").asText()
    );
    assertTrue(
        containsText(operation.path("tags"), expectedTag),
        () -> "Operation thiếu tag " + expectedTag
    );
}

private static boolean containsText(JsonNode array, String expected) {
    if (!array.isArray()) {
        return false;
    }
    for (JsonNode item : array) {
        if (expected.equals(item.asText())) {
            return true;
        }
    }
    return false;
}

private static Set<String> tagNames(JsonNode operation) {
    Set<String> names = new HashSet<>();
    JsonNode tags = operation.path("tags");
    if (tags.isArray()) {
        for (JsonNode tag : tags) {
            names.add(tag.asText());
        }
    }
    return names;
}

private static void assertDeclaredTag(
        JsonNode document, String expectedTag) {

    assertTrue(
        containsNamedTag(document.path("tags"), expectedTag),
        () -> "Chưa khai báo root tag " + expectedTag
    );
}

private static boolean containsNamedTag(
        JsonNode tags, String expected) {

    if (!tags.isArray()) {
        return false;
    }
    for (JsonNode tag : tags) {
        if (expected.equals(tag.path("name").asText())) {
            return true;
        }
    }
    return false;
}
~~~

Tập method trên phù hợp với operation chuẩn của OpenAPI 3.1. Nếu dự án đã chuyển sang OAS 3.2 và có HTTP QUERY, bổ sung `query` sau khi xác minh các công cụ trong pipeline hỗ trợ nó.

## 9. Kiểm tra operationId duy nhất trên toàn document

Một test riêng giúp phát hiện ID trùng giữa các path:

~~~java
private static void assertUniqueOperationIds(JsonNode paths) {
    Set<String> seen = new HashSet<>();

    paths.fields().forEachRemaining(pathEntry -> {
        String path = pathEntry.getKey();
        JsonNode pathItem = pathEntry.getValue();

        for (String method : HTTP_METHODS) {
            JsonNode operation = pathItem.get(method);
            if (operation == null) {
                continue;
            }

            String operationId =
                operation.path("operationId").asText("");

            assertFalse(
                operationId.isBlank(),
                () -> "Operation thiếu operationId: "
                    + method + " " + path
            );
            assertTrue(
                seen.add(operationId),
                () -> "operationId bị trùng: " + operationId
            );
        }
    });
}
~~~

Đoạn kiểm tra này áp dụng policy dự án: mọi operation trong `paths` phải có ID. Theo đặc tả, operationId không bắt buộc phải xuất hiện, nhưng nếu có thì phải duy nhất. Với API public và code generation, bắt buộc ID tường minh thường giúp hợp đồng ổn định hơn.

Nếu OpenAPI document có `webhooks` hoặc callback chứa operation, mở rộng test để duyệt cả các operation đó. Không được coi kiểm tra riêng `paths` là kiểm tra đầy đủ mọi operation trong một document phức tạp.

## 10. Kiểm tra route runtime bên cạnh tài liệu

Contract test tài liệu xác minh springdoc công bố gì. MockMvc test route xác minh ứng dụng thực sự xử lý request ra sao. Hai kiểm tra bổ sung cho nhau.

Ví dụ:

~~~java
@Test
void routesDocumentedProductMethods() throws Exception {
    mockMvc.perform(get("/api/products"))
        .andExpect(status().isOk());

    mockMvc.perform(
        get("/api/products/{id}",
            "11111111-1111-1111-1111-111111111111")
    ).andExpect(status().isOk());

    mockMvc.perform(post("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Bàn phím mẫu"
                }
                """))
        .andExpect(status().isCreated());
}
~~~

Test cần import:

~~~java
import org.springframework.http.MediaType;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
~~~

Ví dụ giả định controller/service xử lý các request trên và trả status tương ứng. Với endpoint cần xác thực, gắn user hoặc JWT test. Nếu controller trả 404/405 trong khi OpenAPI công bố operation, hợp đồng và runtime đang lệch nhau.

### 10.1. Kiểm tra method không được công bố

Nếu path chỉ hỗ trợ GET và POST, contract test có thể xác minh không xuất hiện DELETE trong OpenAPI:

~~~java
assertFalse(
    document.path("paths")
        .path("/api/products")
        .has("delete")
);
~~~

Không nên suy ra method không được hỗ trợ chỉ vì test không gọi nó. Hãy kiểm tra cả cấu trúc OpenAPI lẫn hành vi HTTP. Trong môi trường có Spring Security, request có thể bị chặn trước khi tới handler; status 401/403 không chứng minh route method tồn tại hay không.

## 11. Kiểm tra tag definitions và quy ước nhóm

Một project có thể đặt các quy ước:

- Tên tag viết thường, dạng số nhiều hoặc tên miền nghiệp vụ.
- Mỗi operation có ít nhất một tag.
- Mọi tag được sử dụng phải có root-level definition.
- Mỗi tag có description dễ hiểu.
- Không tạo tag trùng tên chỉ khác chữ hoa/thường.

Đây là policy của dự án, không phải mọi điều kiện đều bắt buộc bởi OpenAPI. Ví dụ test kiểm tra operation có tag:

~~~java
assertTrue(
    containsText(
        document.path("paths")
            .path("/api/products")
            .path("get")
            .path("tags"),
        "products"
    )
);
~~~

Nếu tag bị đổi từ `products` thành `catalog`, URL có thể không đổi nhưng Swagger UI và SDK generator có thể nhóm lại operation. Hãy đưa tag vào review contract diff nếu client hoặc developer portal phụ thuộc nhóm này.

### Tag theo nhiều nhóm

Nếu operation có tag `products` và `search`, test cần xác minh cả hai tên. Không kiểm tra vị trí phần tử đầu tiên nếu thứ tự tag không phải một phần của policy. So sánh tập giá trị sẽ ít nhạy với thay đổi thứ tự không có ý nghĩa.

Nếu dự án cần thứ tự tag hiển thị trong Swagger UI, hãy kiểm tra root-level `tags` riêng vì thứ tự khai báo ở đó có thể được renderer dùng để sắp xếp nhóm.

## 12. Kiểm tra theo GroupedOpenApi

Khi ứng dụng chia tài liệu public, partner và internal, mỗi group là một OpenAPI document riêng. Ví dụ:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/public/**")
        .pathsToExclude("/api/public/internal/**")
        .build();
}
~~~

Group có tên `public` thường được lấy tại `/v3/api-docs/public`. Test group cần xác minh:

- Path public được xuất hiện.
- Path internal bị loại khỏi public document.
- Method và operationId của public operation đúng.
- Tag public được khai báo và sử dụng đúng.
- Document internal/partner có tập path riêng theo chính sách.

Không kiểm tra `/v3/api-docs` rồi suy ra tất cả group đều đúng. Gọi đúng endpoint của từng group và chạy cùng bộ assertion cho từng document.

## 13. Phát hiện contract drift

Contract drift xảy ra khi tài liệu thay đổi ngoài dự kiến hoặc runtime không còn khớp tài liệu đã phát hành. Những thay đổi sau cần được review:

| Thay đổi | Tác động có thể có |
|---|---|
| Xóa path | Client không gọi được endpoint cũ |
| Đổi path hoặc path variable | URL và cách gọi client thay đổi |
| Xóa HTTP method | Operation cũ không còn khả dụng |
| Thêm method ngoài ý muốn | Công bố bề mặt API chưa được duyệt |
| Đổi operationId | Tên method trong SDK có thể thay đổi |
| Đổi tag | Operation chuyển nhóm trong UI/SDK |
| Đổi tên path parameter | Client phải đổi tên biến/argument |
| Đổi group filter | Operation có thể biến mất khỏi artifact public |

### 13.1. So sánh với baseline

Lưu OpenAPI JSON của bản phát hành trước như một artifact có version. Khi build bản mới:

1. Sinh document mới từ ứng dụng.
2. Chuẩn hóa JSON để bỏ khác biệt không có ý nghĩa như thứ tự key.
3. So sánh path và method.
4. So sánh operationId và tags.
5. So sánh schema/parameters/responses nếu pipeline contract yêu cầu.
6. Phân loại thay đổi breaking, non-breaking hoặc cần review.

Không so sánh text thuần rồi kết luận mọi khác biệt đều là breaking. Thay đổi thứ tự JSON hoặc format YAML không nhất thiết thay đổi hợp đồng. Dùng parser hoặc semantic diff tool hiểu OpenAPI để so sánh cấu trúc.

### 13.2. Không tự động chấp nhận operationId mới

Thêm operation mới thường là mở rộng hợp đồng, nhưng vẫn cần review xem endpoint có được phép public không. Đổi operationId hiện hữu có thể làm SDK client đổi tên hàm. Hãy yêu cầu reviewer xác nhận lý do và kế hoạch cập nhật consumer.

### 13.3. Snapshot và assertion có mục tiêu

Snapshot toàn bộ OpenAPI document có thể tạo diff lớn do timestamp, thứ tự schema hoặc formatter. Dùng assertion có mục tiêu cho path/method/operationId/tag cốt lõi; dùng semantic diff cho phần còn lại. Snapshot chỉ nên là bằng chứng hỗ trợ, không phải tiêu chí duy nhất.

## 14. Đưa contract test vào CI

Một pipeline có thể thực hiện theo thứ tự:

~~~text
Compile application
        |
        v
Start Spring test context
        |
        v
Fetch /v3/api-docs (and each group)
        |
        v
Assert paths and HTTP methods
        |
        v
Assert operationId uniqueness
        |
        v
Assert tags and group filters
        |
        v
Exercise runtime routes with MockMvc
        |
        v
Compare with released OpenAPI baseline
        |
        v
Publish document / SDK
~~~

Các bước nên thất bại rõ ràng nếu path/method bị thiếu, operationId trùng hoặc tag không đúng policy. Không publish artifact mới nếu contract test chưa đạt.

### 14.1. Giữ test độc lập với thứ tự JSON

Jackson JsonNode và tập Set phù hợp để kiểm tra các property không có ý nghĩa thứ tự. Chỉ kiểm tra thứ tự khi nó là yêu cầu hiển thị được thống nhất.

### 14.2. Kiểm tra đúng endpoint tài liệu

Nếu ứng dụng có `springdoc.api-docs.path` tùy chỉnh hoặc group, cấu hình test phải gọi đúng endpoint. Nếu endpoint tài liệu cần quyền truy cập, test phải sử dụng cơ chế xác thực dành cho test.

### 14.3. Lưu bằng chứng contract

Lưu OpenAPI artifact và kết quả semantic diff theo build/release. Điều này giúp xác định thay đổi nào đã được đưa vào bản phát hành và hỗ trợ điều tra khi SDK hoặc client gặp lỗi.

## 15. Lỗi thường gặp khi viết contract test

| Lỗi | Vì sao chưa đủ | Cách khắc phục |
|---|---|---|
| Chỉ kiểm tra HTTP status của `/v3/api-docs` | Document có thể hợp lệ nhưng path/method sai | Parse JSON và assert từng operation |
| Chỉ kiểm tra controller mapping | Không phát hiện filter/group/hidden làm mất operation | Kiểm tra OpenAPI JSON |
| Chỉ kiểm tra Swagger UI hiển thị | UI có thể che việc thiếu metadata hoặc operation | Assert trực tiếp document |
| Dựa vào tên method Java làm operationId | Refactor có thể đổi SDK method name | Khai báo operationId tường minh |
| Chỉ kiểm tra operationId được quan tâm | ID khác có thể bị trùng | Duyệt tất cả operation trong document |
| So sánh tag theo index | Thứ tự tag có thể không phải hợp đồng | So sánh tập tag |
| Bắt buộc mọi tag theo chuẩn OpenAPI | Đây có thể là policy riêng, không phải yêu cầu chuẩn | Ghi rõ quy ước nội bộ và test theo policy |
| Gộp server prefix vào path assertion | Sai khác theo môi trường dễ làm test lỗi | Kiểm tra `servers` và `paths` riêng |
| Không test route runtime | Document có thể mô tả endpoint không chạy được | Thêm MockMvc/WebTestClient test |
| Chỉ test default document | Group public/internal có thể sai khác | Test từng group |
| Dùng snapshot text nguyên văn | Diff nhiễu do format/thứ tự | Dùng JSON tree và semantic diff |

## 16. Bài thực hành tổng hợp

Tạo một API quản lý sản phẩm với các operation:

| HTTP method | Path | operationId | Tag |
|---|---|---|---|
| GET | `/api/products` | `listProducts` | `products` |
| GET | `/api/products/{id}` | `getProductById` | `products` |
| POST | `/api/products` | `createProduct` | `products` |
| PUT | `/api/products/{id}` | `replaceProduct` | `products` |
| DELETE | `/api/products/{id}` | `deleteProduct` | `products` |

Thực hiện:

1. Đặt class-level `@RequestMapping("/api/products")`.
2. Dùng mapping chuyên biệt cho từng HTTP method.
3. Khai báo `@Operation(operationId = "...")` cho mọi operation.
4. Khai báo tag `products` với description rõ ràng.
5. Gọi `/v3/api-docs` bằng MockMvc.
6. Assert tập path chính xác.
7. Assert tập method chính xác cho từng path.
8. Assert operationId của từng operation.
9. Duyệt toàn bộ operation để phát hiện ID trùng hoặc rỗng.
10. Assert mọi operation dùng tag `products` và root-level tag được khai báo.
11. Gọi các route thực tế bằng GET, POST, PUT và DELETE để xác minh routing.
12. Tạo một public group và xác minh path internal không xuất hiện.
13. Thử đổi tên một operationId và quan sát contract diff.
14. Đưa các test vào CI và chặn phát hành nếu contract thay đổi ngoài dự kiến.

### Tiêu chí hoàn thành

- [ ] Path trong OpenAPI khớp path sau khi ghép class-level và method-level mapping.
- [ ] Không có path sai chữ hoa/thường hoặc trailing slash ngoài ý muốn.
- [ ] HTTP method được công bố đúng với route runtime.
- [ ] Tập method của mỗi path khớp hợp đồng đã duyệt.
- [ ] Mỗi operation có operationId tường minh theo policy dự án.
- [ ] operationId duy nhất trong document.
- [ ] Tag trên operation khớp tag definition và quy ước dự án.
- [ ] Không có tag không mong muốn hoặc operation bị thiếu do group filter.
- [ ] Path và method được kiểm tra trực tiếp từ `/v3/api-docs`.
- [ ] Runtime route được kiểm tra bằng MockMvc/WebTestClient.
- [ ] Contract diff được review trước khi phát hành.
- [ ] CI lưu lại artifact và kết quả kiểm tra hợp đồng.

## Tiếp tục học

Sau bài này, hãy mở rộng contract test sang parameters, request/response schemas, status code, security requirement và backward compatibility. Path, HTTP method, operationId và tag là lớp định danh đầu tiên của operation; chúng cần ổn định để client, SDK và developer portal có thể dựa vào hợp đồng lâu dài.
