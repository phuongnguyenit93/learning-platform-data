# Kiểm soát những tài nguyên repository xuất hiện trong hợp đồng

Spring Data repository được thiết kế để truy cập dữ liệu trong ứng dụng. Khi thêm Spring Data REST, một số repository còn được xuất thành HTTP resource với các đường dẫn collection, item, search và association. Điều này rất tiện để tạo API CRUD nhanh, nhưng cũng có nghĩa một interface repository có thể trở thành bề mặt API công khai ngoài dự kiến.

Với Spring Boot dùng springdoc-openapi, cần kiểm soát hai việc riêng: **repository nào được Spring Data REST xuất thành HTTP resource** và **resource nào xuất hiện trong tài liệu OpenAPI**. Ẩn một path khỏi OpenAPI không vô hiệu hóa endpoint runtime. Ngược lại, không xuất repository ở runtime thì springdoc cũng không nên mô tả endpoint đó như một API có thể gọi.

## 1. Repository không tự động là API contract

Một repository như sau chủ yếu là abstraction truy cập dữ liệu:

~~~java
public interface ProductRepository extends JpaRepository<Product, UUID> {
    Optional<Product> findBySku(String sku);
}
~~~

Nếu ứng dụng chỉ dùng Spring Data JPA, interface này không tự tạo HTTP endpoint. Service và controller có thể gọi repository nội bộ:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    private final ProductRepository products;

    ProductController(ProductRepository products) {
        this.products = products;
    }

    @GetMapping("/{id}")
    ProductResponse get(@PathVariable UUID id) {
        Product product = products.findById(id)
                .orElseThrow(ProductNotFoundException::new);
        return ProductResponse.from(product);
    }
}
~~~

Khi có Spring Data REST, repository có thể được xuất thành resource mà không cần controller viết tay. Ví dụ, một repository công khai có thể tạo:

- Collection resource để liệt kê và tạo tài nguyên.
- Item resource để đọc, cập nhật hoặc xóa một tài nguyên.
- Search resource cho các query method được xuất.
- Association resource để điều hướng hoặc cập nhật quan hệ.

Do đó, cần xem repository được xuất như một quyết định thiết kế API. Không nên để việc một interface là public hoặc kế thừa CrudRepository vô tình quyết định hợp đồng dành cho client.

## 2. Spring Data REST tạo ra những resource nào?

Giả sử ứng dụng cấu hình base path là `/data` và có repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;
import java.util.Optional;
import java.util.UUID;

@RepositoryRestResource(
        path = "products",
        collectionResourceRel = "products",
        itemResourceRel = "product"
)
public interface ProductRepository extends JpaRepository<Product, UUID> {

    @RestResource(path = "by-sku", rel = "by-sku")
    Optional<Product> findBySku(String sku);
}
~~~

Spring Data REST có thể tạo các URL dạng:

| Resource | URL minh họa | Mục đích |
|---|---|---|
| Collection | `GET /data/products` | Lấy danh sách sản phẩm. |
| Item | `GET /data/products/{id}` | Lấy một sản phẩm. |
| Search root | `GET /data/products/search` | Khám phá các query method được xuất. |
| Finder | `GET /data/products/search/by-sku?sku=...` | Tìm sản phẩm theo SKU. |

Đường dẫn và các HTTP method thực tế phụ thuộc repository, annotation, cấu hình và phiên bản Spring Data REST. Spring Data REST thường biểu diễn resource bằng HAL, gồm dữ liệu và các liên kết trong `_links`. Vì vậy, hợp đồng không chỉ là DTO JSON phẳng; client còn có thể điều hướng theo link relation.

### 2.1. Repository method có thể trở thành endpoint

Một finder method có thể xuất thành search resource. Ví dụ `findBySku` ở trên được đặt dưới `/search/by-sku`. Annotation `@RestResource` có thể đổi path và relation name, hoặc tắt xuất method bằng `exported = false`.

Không phải mọi method nội bộ đều nên trở thành endpoint. Những method dùng cho batch, xử lý nghiệp vụ, tra cứu nội bộ hoặc truy vấn quản trị cần được giữ lại trong repository nhưng không xuất ra HTTP.

### 2.2. Collection và item resource có thể có tập HTTP method khác nhau

Spring Data REST suy luận method HTTP dựa trên các method repository được hỗ trợ. Ví dụ, nếu repository không cung cấp khả năng xóa phù hợp thì resource item không nhất thiết hỗ trợ DELETE. Tuy nhiên, với repository kế thừa CrudRepository/JpaRepository, nhiều CRUD method được kế thừa sẵn.

Nếu API chỉ cho đọc, hoặc không cho client xóa trực tiếp, cần cấu hình exposure rõ ràng. Không dựa vào việc UI không hiển thị nút xóa để coi endpoint đã được vô hiệu hóa.

## 3. Tắt xuất toàn bộ một repository

Nếu repository chỉ phục vụ nghiệp vụ nội bộ, đánh dấu exported=false ở cấp repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import java.util.UUID;

@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<AuditRecord, UUID> {
}
~~~

Repository vẫn có thể được inject và dùng trong service, job hoặc listener. Annotation này ngăn Spring Data REST xuất nó thành HTTP resource. Nó không xóa bean repository và không ngăn truy cập dữ liệu nội bộ qua code ứng dụng.

Một repository không được xuất sẽ không có collection/item/search resource tương ứng để springdoc mô tả. Sau khi thay đổi, kiểm tra cả HTTP endpoint và tài liệu OpenAPI để xác nhận kết quả.

## 4. Chuyển từ mặc định sang opt-in

Theo mặc định, Spring Data REST xuất các repository public phù hợp với quy tắc detection mặc định. Điều này thuận tiện cho ứng dụng CRUD đơn giản, nhưng dễ tạo API mới khi nhóm phát triển thêm repository public.

Có thể cấu hình repository detection strategy để giới hạn repository được xuất:

| Strategy | Ý nghĩa |
|---|---|
| DEFAULT | Xuất repository public hoặc repository được đánh dấu bằng RepositoryRestResource, trừ khi exported=false. |
| ALL | Xem xét tất cả repository, không phụ thuộc visibility hoặc annotation. |
| VISIBILITY | Chỉ xét repository interface public. |
| ANNOTATED | Chỉ xuất repository được đánh dấu bằng RepositoryRestResource hoặc RestResource và không bị exported=false. |

Để có chính sách opt-in rõ ràng, Spring Data REST 3.1 trở lên cung cấp `disableDefaultExposure()`. Phương thức này chuyển detection sang ANNOTATED và tắt việc mặc định xuất repository methods; các repository và method cần được đánh dấu tường minh.

~~~java
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Component
class RepositoryExposureConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.disableDefaultExposure();
        config.setBasePath("/data");
        config.setDefaultPageSize(20);
        config.setMaxPageSize(100);
    }
}
~~~

Với cấu hình trên:

- Repository không được đánh dấu rõ ràng sẽ không tự động trở thành resource.
- Repository được xuất cần được khai báo bằng `@RepositoryRestResource`.
- Query method cần được đánh dấu `@RestResource` nếu default method exposure đã bị tắt.
- Base path là `/data`.
- Page size mặc định là 20 và không vượt quá 100 qua cấu hình Spring Data REST.

Nếu đang dùng Spring Data REST trước 3.1, kiểm tra API của phiên bản đó. Có thể cấu hình detection strategy ANNOTATED trực tiếp, nhưng cần xác minh riêng chính sách xuất repository methods vì `disableDefaultExposure()` còn tắt default method exposure.

### 4.1. Chỉ dùng ANNOTATED có thể chưa đủ

`setRepositoryDetectionStrategy(ANNOTATED)` kiểm soát repository nào được xem xét để xuất. Nếu ứng dụng vẫn bật mặc định xuất repository methods, các CRUD method của repository đã được chọn có thể tiếp tục được xuất theo quy tắc mặc định.

Nếu mục tiêu là opt-in ở cả repository lẫn method, dùng `disableDefaultExposure()` trên phiên bản hỗ trợ. Cách này làm cho ý định công bố API được thể hiện tường minh trong source code.

## 5. Tắt một query method nhưng giữ repository

Một repository có thể cần giữ finder method cho service nội bộ nhưng không cho client gọi trực tiếp. Dùng `@RestResource(exported = false)` trên method:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;
import java.util.List;
import java.util.UUID;

@RepositoryRestResource(path = "users")
public interface UserRepository extends JpaRepository<User, UUID> {

    @RestResource(path = "by-status", rel = "by-status")
    List<User> findByStatus(UserStatus status);

    @RestResource(exported = false)
    List<User> findByEmail(String email);
}
~~~

Trong ví dụ, query method tìm theo status vẫn có thể được xuất theo quy tắc mặc định, còn finder theo email vẫn dùng được từ code Java nhưng không được xuất thành search endpoint.

Hãy kiểm tra cả search root và path finder. Nếu method bị tắt, link relation tương ứng không nên xuất hiện trong HAL search resource và path đó không nên có trong OpenAPI.

## 6. Kiểm soát CRUD method và HTTP method

Khi repository kế thừa CrudRepository hoặc JpaRepository, các method như save và delete có thể tạo ra khả năng POST, PUT, PATCH hoặc DELETE. Nếu muốn giữ repository nhưng hạn chế thao tác từ client, có hai hướng:

1. Override method CRUD liên quan và gắn `@RestResource(exported = false)` theo đúng API của phiên bản Spring Data đang dùng.
2. Dùng `RepositoryRestConfiguration.getExposureConfiguration()` để giới hạn HTTP method ở collection hoặc item resource.

Ví dụ vô hiệu hóa PATCH cho item resource:

~~~java
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.http.HttpMethod;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
class RestMethodExposureConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {
        config.getExposureConfiguration()
                .withItemExposure((metadata, methods) ->
                        methods.disable(HttpMethod.PATCH));
    }
}
~~~

Ví dụ này áp dụng cho item exposure theo cấu hình toàn cục. Nếu chỉ muốn hạn chế một domain type, dùng các API type-specific của ExposureConfiguration, chẳng hạn cấu hình `forDomainType(Product.class)`, rồi kiểm tra đúng method mà phiên bản Spring Data REST cung cấp.

Không nên giả định tắt một method Java sẽ luôn tắt đúng một HTTP method. Một số method repository có thể được dùng chung để triển khai nhiều HTTP operation. Tài liệu Spring Data REST lưu ý rằng việc tắt CRUD method kế thừa cần override đầy đủ các overload tương ứng; với delete, cần kiểm tra cả dạng nhận ID và dạng nhận entity theo phiên bản đang dùng.

### 6.1. Giới hạn PUT tạo mới và PATCH cập nhật

Spring Data REST cung cấp cấu hình exposure để điều khiển một số hành vi item resource:

~~~java
config.getExposureConfiguration()
        .forDomainType(Product.class)
        .disablePutForCreation();
~~~

Lệnh trên vô hiệu hóa việc dùng PUT để tạo item resource trực tiếp cho domain type Product. Có thể kết hợp các rule global hoặc type-specific để chỉ cho phép những thao tác phù hợp với hợp đồng.

Nếu API cần workflow nghiệp vụ phức tạp như duyệt đơn hàng, hoàn tiền, publish hoặc chuyển trạng thái, một endpoint controller riêng thường diễn đạt tốt hơn việc mở CRUD trực tiếp lên entity.

## 7. Ẩn association resource và field không dành cho client

Spring Data REST có thể xuất liên kết tới association của entity. Ví dụ, Product có quan hệ tới Supplier hoặc Review. Nếu một quan hệ chỉ phục vụ nội bộ, có thể đánh dấu property bằng `@RestResource(exported = false)`:

~~~java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.ManyToOne;
import org.springframework.data.rest.core.annotation.RestResource;
import java.util.UUID;

@Entity
class Product {

    @Id
    @GeneratedValue
    private UUID id;

    private String name;

    @ManyToOne
    @RestResource(exported = false)
    private Supplier supplier;
}
~~~

Việc này kiểm soát việc xuất property/association qua Spring Data REST. Hãy xác minh representation HAL và association resource thực tế sau khi cấu hình.

### 7.1. Không dùng ẩn association thay cho bảo vệ dữ liệu nhạy cảm

Ẩn một association link không đồng nghĩa mọi field nhạy cảm của entity đều được bảo vệ. Nếu entity có password hash, secret, internal note hoặc thông tin riêng tư, hãy thiết kế representation công khai chỉ gồm field cần thiết.

Các lựa chọn:

- Dùng DTO riêng trong controller.
- Dùng projection chỉ chọn field được phép xuất.
- Dùng Jackson annotation phù hợp cho field không được serialize.
- Tách entity persistence khỏi representation dành cho client.

Spring Data REST có thể cho phép projection làm xuất hiện field theo cách khác với representation mặc định. Vì vậy, khi ẩn field bằng `@RestResource(exported = false)`, phải rà soát mọi projection liên quan và không đưa field nhạy cảm trở lại qua projection.

## 8. Projection thay đổi representation, không thay thế exposure policy

Projection cho phép chọn tập field được đưa vào representation. Ví dụ:

~~~java
import org.springframework.data.rest.core.config.Projection;
import java.math.BigDecimal;

@Projection(name = "summary", types = Product.class)
interface ProductSummary {
    String getName();
    BigDecimal getPrice();
}
~~~

Có thể dùng projection làm excerpt mặc định:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import java.util.UUID;

@RepositoryRestResource(
        path = "products",
        excerptProjection = ProductSummary.class
)
interface ProductRepository extends JpaRepository<Product, UUID> {
}
~~~

Projection giúp representation collection gọn hơn, nhưng không tự ẩn repository, finder, CRUD method hoặc association resource. Nếu client có thể yêu cầu projection khác, cần kiểm tra projection nào được phát hiện và field nào chúng trả về.

Không dùng projection làm lớp authorization. Nếu một nhóm client được phép xem field khác nhóm còn lại, cần policy bảo mật hoặc API representation riêng theo quyền; một projection công khai không tự phân biệt danh tính client.

## 9. Giới hạn phân trang và sắp xếp của repository resource

Spring Data REST thường hỗ trợ các tham số page, size và sort trên collection resource. Nếu không giới hạn, client có thể yêu cầu trang quá lớn hoặc sort trên field không phù hợp.

Có thể cấu hình qua application.yml:

~~~yaml
spring:
  data:
    rest:
      base-path: /data
      default-page-size: 20
      max-page-size: 100
~~~

Hoặc cấu hình base path và page size trong `RepositoryRestConfigurer` như phần trước. Chỉ nên duy trì một nguồn cấu hình chính để tránh giá trị trong properties và Java config khác nhau.

Spring Data REST cung cấp sort theo thuộc tính domain. Nếu hợp đồng chỉ cho phép một số sort field, cần kiểm soát ở tầng query/repository hoặc chuyển endpoint sang controller chuyên biệt với allow-list. Đừng mặc định rằng giới hạn max page size cũng giới hạn field sort.

Với API công khai, cân nhắc dùng DTO response và query parameter rõ ràng nếu cần quy tắc sort/filter nghiêm ngặt, thay vì để toàn bộ cấu trúc repository quyết định hợp đồng.

## 10. Springdoc tích hợp Spring Data REST

Springdoc có hỗ trợ tích hợp Spring Data REST. Property `springdoc.enable-data-rest` bật/tắt phần tích hợp này; giá trị mặc định được tài liệu springdoc công bố là `true` khi tính năng và class tương ứng có mặt.

Ví dụ giữ tích hợp:

~~~yaml
springdoc:
  enable-data-rest: true
~~~

Nếu không muốn springdoc đưa Spring Data REST endpoints vào tài liệu:

~~~yaml
springdoc:
  enable-data-rest: false
~~~

**Lưu ý:** `springdoc.enable-data-rest: false` chỉ tắt tích hợp Springdoc cho Spring Data REST. Nó không tắt các HTTP resource mà Spring Data REST đã xuất. Muốn ngăn client gọi resource, phải thay đổi exposure ở Spring Data REST hoặc bảo vệ endpoint bằng Spring Security.

### 10.1. Phân biệt ba lớp điều khiển

| Cơ chế | Tác động | Không có tác dụng |
|---|---|---|
| `@RepositoryRestResource(exported = false)` | Không xuất repository thành HTTP resource. | Không xóa repository bean hoặc cấm service nội bộ dùng nó. |
| `@RestResource(exported = false)` | Ẩn repository method hoặc property/association khỏi Spring Data REST. | Không tự thay đổi quyền truy cập của endpoint controller khác. |
| `springdoc.enable-data-rest=false` | Không đưa Spring Data REST endpoints qua integration của springdoc. | Không vô hiệu hóa HTTP resource runtime. |
| `GroupedOpenApi.pathsToExclude(...)` | Loại path khỏi một OpenAPI group. | Không xóa endpoint và không tạo authorization. |
| Spring Security | Chặn hoặc cho phép request runtime theo identity/authority. | Không tự loại operation khỏi OpenAPI nếu chưa cấu hình tài liệu. |

Đây là các lớp khác nhau. Khi muốn một resource hoàn toàn không tồn tại đối với client, hãy điều khiển Spring Data REST exposure và authorization. Khi chỉ muốn tài liệu public không hiển thị một operation nhưng endpoint vẫn được nhóm nội bộ sử dụng, hãy tách group và bảo vệ group tương ứng.

## 11. Kiểm soát nội dung OpenAPI theo group

Nếu ứng dụng có cả resource public và internal, tạo group theo path đã duyệt:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class RepositoryOpenApiGroups {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
                .group("public")
                .pathsToMatch("/data/products/**")
                .pathsToExclude("/data/products/search/internal")
                .build();
    }

    @Bean
    GroupedOpenApi internalApi() {
        return GroupedOpenApi.builder()
                .group("internal")
                .pathsToMatch("/data/**")
                .build();
    }
}
~~~

Ví dụ minh họa cách chọn path; pattern exclude cụ thể cần được kiểm tra với matcher của phiên bản springdoc và đường dẫn thực tế. Nếu public API chỉ gồm một vài resource, allow-list bằng các path cụ thể thường dễ review hơn exclude một số pattern rộng.

Group public có thể được xuất ở `/v3/api-docs/public` và group internal ở `/v3/api-docs/internal`. Bảo vệ URL tài liệu nội bộ bằng Spring Security; group không phải access control.

## 12. Kiểm tra OpenAPI và runtime sau khi giới hạn exposure

Sau mỗi thay đổi repository exposure, kiểm tra cả endpoint HTTP và OpenAPI:

1. Repository được phép xuất có collection path đúng.
2. Item resource có đúng HTTP method được phép.
3. Query method bị ẩn không xuất hiện dưới search root.
4. Association bị ẩn không còn link/representation tương ứng.
5. Repository exported=false không còn collection/item/search resource.
6. Springdoc phản ánh đúng path và method còn tồn tại.
7. Projection không làm lộ field đã loại khỏi representation công khai.
8. Group public không chứa path nội bộ.

Giả sử base path là `/data` và ProductRepository được xuất:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.hamcrest.Matchers.containsString;

@SpringBootTest
@AutoConfigureMockMvc
class RepositoryExposureContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesProductCollectionAndDocumentsIt() throws Exception {
        mockMvc.perform(get("/data/products"))
                .andExpect(status().isOk());

        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(content().string(containsString("/data/products")));
    }

    @Test
    void doesNotExposeInternalAuditRepository() throws Exception {
        mockMvc.perform(get("/data/internal-audit-records"))
                .andExpect(status().isNotFound());

        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(content().string(org.hamcrest.Matchers.not(
                        containsString("/data/internal-audit-records"))));
    }
}
~~~

Test trên giả định repository audit đã bị tắt bằng `@RepositoryRestResource(exported = false)` và ứng dụng không có controller khác dùng cùng path. Spring Data REST có thể trả status khác tùy mapping và security configuration; điều quan trọng là xác minh endpoint không thể thực hiện thao tác và không còn được công bố trong tài liệu.

### 12.1. Kiểm tra search resource và HAL links

Với finder method có path `by-sku`, kiểm tra search resource:

~~~java
mockMvc.perform(get("/data/products/search"))
        .andExpect(status().isOk())
        .andExpect(content().string(containsString("by-sku")));
~~~

Nếu method đã gắn `@RestResource(exported = false)`, link relation tương ứng không nên xuất hiện. Kiểm tra HAL response giúp phát hiện endpoint còn được discoverable dù path OpenAPI đã bị lọc.

### 12.2. Kiểm tra OpenAPI có tích hợp Data REST hay không

Khi `springdoc.enable-data-rest=true`, kiểm tra path của repository resource trong /v3/api-docs. Khi đặt false, kiểm tra chúng không còn xuất hiện do integration này; sau đó vẫn gọi endpoint runtime để xác nhận Spring Data REST còn hoạt động nếu đó là chủ đích.

Đừng chỉ test JSON. Cần kiểm tra HTTP methods thực tế, HAL links, status code và quyền truy cập.

## 13. Những lỗi thường gặp

- **Cho rằng mọi repository đều chỉ dùng nội bộ**: Spring Data REST có thể xuất repository public thành HTTP resource.
- **Cho rằng springdoc chỉ mô tả controller**: khi bật Data REST integration, tài liệu có thể bao gồm resource được tạo từ repository.
- **Chỉ ẩn path khỏi OpenAPI**: endpoint runtime vẫn có thể gọi được.
- **Chỉ đặt springdoc.enable-data-rest=false**: tính năng xuất HTTP của Spring Data REST vẫn còn.
- **Dùng ANNOTATED nhưng quên method exposure**: repository đã chọn có thể vẫn xuất CRUD/query method theo cấu hình mặc định.
- **Quên exported=false trên repository nhạy cảm**: collection và item resource có thể bị công bố.
- **Quên ẩn finder method nội bộ**: method có thể xuất hiện trong /search.
- **Chỉ ẩn một overload delete**: method khác có thể vẫn hỗ trợ HTTP DELETE tùy phiên bản và mapping.
- **Ẩn association nhưng projection vẫn trả field**: representation khác có thể đưa field trở lại.
- **Dùng projection làm authorization**: projection không phân quyền theo người dùng.
- **Không kiểm tra HAL links**: resource có thể vẫn được discoverable qua link relation.
- **Không giới hạn page size và sort**: client có thể tạo request quá lớn hoặc truy vấn tốn kém.
- **Dùng group như security boundary**: OpenAPI group chỉ lọc tài liệu, không chặn HTTP request.

## 14. Quy trình review repository trước khi xuất API

1. **Liệt kê repository**: xác định interface nào chỉ phục vụ nội bộ và interface nào được thiết kế cho HTTP.
2. **Chọn exposure policy**: dùng opt-in với `disableDefaultExposure()` nếu muốn repository và method phải được đánh dấu rõ.
3. **Đánh dấu repository**: chỉ thêm `@RepositoryRestResource` cho resource đã được duyệt; dùng exported=false cho repository nội bộ.
4. **Rà soát query methods**: ẩn finder không dành cho client bằng `@RestResource(exported = false)`.
5. **Rà soát CRUD methods**: giới hạn POST, PUT, PATCH và DELETE theo nghiệp vụ.
6. **Rà soát association và field**: không xuất quan hệ hoặc dữ liệu nhạy cảm không cần thiết.
7. **Rà soát projection**: bảo đảm không đưa field đã ẩn trở lại.
8. **Giới hạn query**: đặt page size, xem xét sort/filter và chi phí truy vấn.
9. **Cấu hình springdoc**: bật/tắt Data REST integration có chủ đích và chia group theo audience.
10. **Kiểm thử runtime và contract**: kiểm tra resource, HAL links, HTTP methods và /v3/api-docs.

## 15. Checklist review

- [ ] Mỗi repository được phân loại là nội bộ, public hoặc partner-facing.
- [ ] Repository không dành cho HTTP có exported=false.
- [ ] Detection strategy phù hợp với chính sách opt-in/opt-out.
- [ ] Nếu dùng opt-in, default repository method exposure đã được tắt.
- [ ] Query method nội bộ không xuất hiện trong search resource.
- [ ] CRUD HTTP methods khớp nghiệp vụ.
- [ ] Association và field nhạy cảm không bị xuất ngoài ý muốn.
- [ ] Projection không làm lộ lại field đã ẩn.
- [ ] Page size và sort/filter được giới hạn phù hợp.
- [ ] springdoc.enable-data-rest được cấu hình theo chủ đích.
- [ ] Group OpenAPI không bị nhầm là cơ chế authorization.
- [ ] Test kiểm tra cả HAL links, endpoint runtime và OpenAPI paths.

## 16. Tài liệu tham khảo

- [Spring Data REST – Customizing repository exposure](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST – Configuring the REST URL path and hiding resources](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html)
- [Spring Data REST – RepositoryDetectionStrategy](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/mapping/RepositoryDetectionStrategy.RepositoryDetectionStrategies.html)
- [Spring Data REST – RepositoryRestConfiguration](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html)
- [springdoc-openapi – Core properties](https://springdoc.org/core-properties.html)
- [springdoc-openapi v2 – Core properties](https://springdoc.org/v2/core-properties.html)
- [OpenAPI Specification 3.1.2](https://spec.openapis.org/oas/v3.1.2.html)

Repository là thành phần truy cập dữ liệu; Spring Data REST mới quyết định repository nào trở thành HTTP resource; springdoc tích hợp và mô tả các resource được xuất. Hãy thiết lập exposure theo opt-in, giới hạn method và association, kiểm tra projection, rồi xác minh đồng thời HAL runtime và OpenAPI. Khi ba lớp này thống nhất, hợp đồng chỉ công bố đúng tài nguyên mà client được phép sử dụng.
