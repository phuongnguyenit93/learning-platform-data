# Kiểm thử giới hạn bộ lọc, phạm vi trường và hợp đồng dữ liệu

## 1. Kiểm thử điều mà client và tầng dữ liệu thực sự quan sát

Trong chương **Bộ lọc và payload web** của module **SPRING_DATA_COMMONS**, một endpoint hoạt động đúng cần nhiều hơn việc nhận được `Predicate`, DTO hoặc projection.

Cần xác minh đồng thời:

- Bộ lọc có đúng ý nghĩa, số lượng và phạm vi được công bố không?
- Trường nào được phép lọc, sắp xếp, ghi hoặc trả về?
- Request sai có bị xử lý theo hợp đồng, trước khi tạo tác động dữ liệu không?
- Tenant, quyền sở hữu và các điều kiện bắt buộc của server có còn được giữ khi request thiếu hoặc sai bộ lọc không?
- JSON đầu ra và thông tin phân trang có đúng schema mà client đang dùng không?

Một unit test gọi trực tiếp controller không đi qua mapping HTTP, argument resolver, message converter hay validation MVC. `MockMvc` đi qua `DispatcherServlet` trong môi trường Servlet mô phỏng và phù hợp để kiểm tra các bước đó; xem [tổng quan MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc/overview.html).

Bài này dùng ví dụ Java 17, Spring MVC, Boot 3.5 và Commons 3.5. Những đoạn kiểm thử có repository thực chọn JPA làm ví dụ cụ thể. Với module dữ liệu khác, giữ mục tiêu kiểm thử và điều chỉnh fixture, transaction cùng cơ chế truy vấn theo module đó.

Các test minh họa là tiêu chí cho một API đã triển khai chính sách được mô tả. Chúng không khẳng định mọi hành vi như từ chối khóa lạ hoặc trả mã lỗi nghiệp vụ đều do Spring Data tự cung cấp.

## 2. Viết hợp đồng trước khi viết assertion

### 2.1. Hợp đồng GET danh sách

Giả sử `GET /products` có chính sách:

| Thành phần | Hợp đồng của ví dụ |
| --- | --- |
| `name` | Một giá trị, từ 1 đến 64 ký tự, tìm chứa không phân biệt hoa/thường |
| `status` | Tối đa 20 giá trị lặp, mỗi giá trị là `ACTIVE` hoặc `ARCHIVED`; nhiều giá trị nghĩa là `in` |
| Khóa filter được mở | `name`, `status` |
| Khóa điều khiển khác | `page`, `size`, `sort` |
| Khóa không được công bố | Từ chối bằng `400`, không âm thầm bỏ qua |
| `page` | Số nguyên không âm, bắt đầu từ 0 |
| `size` | Từ 1 đến 100; vượt giới hạn trả `400` |
| Sort | Chỉ `id`, `name`, `price`; tối đa hai `Sort.Order` |
| Phạm vi dữ liệu | Luôn có điều kiện tenant lấy từ server |
| Response | `content` và metadata `page`; mỗi phần tử chỉ có `id`, `name`, `price`, `status` |

Con số 64, 20 và 100 là lựa chọn của API trong bài, không phải mặc định phổ quát của Commons.

Trong ví dụ, số lượng giá trị `status` được đếm theo số giá trị request gửi, kể cả trùng nhau. Quyết định này ngăn việc chuẩn hóa trùng lặp vô tình làm sai chính sách giới hạn.

### 2.2. Hợp đồng POST tạo dữ liệu

Giả sử `POST /products` nhận JSON:

```json
{
  "name": "Keyboard Mini",
  "price": 100000.00,
  "tags": ["office", "compact"]
}
```

Chính sách của ví dụ:

| Thành phần | Hợp đồng |
| --- | --- |
| `name` | Bắt buộc, không chỉ có khoảng trắng, tối đa 80 ký tự |
| `price` | Bắt buộc, không âm |
| `tags` | Bắt buộc, tối đa 8 phần tử; từng phần tử có giới hạn độ dài |
| Trường ghi được | Chỉ `name`, `price`, `tags` |
| Trường do server quản lý | ID, tenant, trạng thái ban đầu và metadata auditing |
| Trường JSON ngoài hợp đồng | Từ chối bằng `400` trong cấu hình ví dụ |
| Request không hợp lệ | Không tạo hoặc thay đổi dữ liệu |

Không dùng một danh sách trường duy nhất cho mọi việc. Một trường được trả về chưa chắc được ghi; một trường được sort chưa chắc được dùng làm filter.

### 2.3. Hợp đồng lỗi

Ví dụ lỗi giới hạn filter:

```json
{
  "code": "INVALID_QUERY",
  "message": "Tham số truy vấn không hợp lệ",
  "fieldErrors": [
    {
      "field": "status",
      "code": "TOO_MANY_VALUES"
    }
  ]
}
```

Ví dụ dùng `INVALID_BODY` cho payload không hợp lệ. Đây là mã do ứng dụng thiết kế và exception handler phải thực hiện.

Nên assert status, mã lỗi và field liên quan. Không khóa test vào toàn bộ thông điệp dịch ngôn ngữ hoặc thông báo exception nội bộ nếu chúng không phải hợp đồng công khai.

## 3. Phân biệt bốn phạm vi trường

| Phạm vi | Cơ chế thường liên quan | Điều cần chứng minh |
| --- | --- | --- |
| Trường được lọc | `QuerydslBindings` và chính sách kiểm tra query parameter | Chỉ path được công bố tham gia predicate |
| Trường được sắp xếp | Resolver `Pageable`/`Sort` và kiểm tra sort riêng | Không lọt path nội bộ qua `sort` |
| Trường được ghi | Request DTO, projection/form binding, mapper và service | Client không thay đổi tenant, ID hoặc auditing |
| Trường được trả về | Response DTO/projection và serializer | JSON không có field ngoài schema |

Whitelist của `QuerydslBindings` kiểm soát việc tạo predicate từ path. Nó không tự bảo vệ sort, request body hoặc JSON đầu ra.

Trong builder Commons 3.5, path không khả dụng có thể bị bỏ qua. Vì vậy, để test `tenantId=8` phải trả `400`, ứng dụng cần một chính sách kiểm tra khóa request riêng. Xem [QuerydslPredicateBuilder](https://raw.githubusercontent.com/spring-projects/spring-data-commons/3.5.x/src/main/java/org/springframework/data/querydsl/binding/QuerydslPredicateBuilder.java).

Tương tự, cấu hình `maxPageSize` ở resolver có thể giới hạn giá trị được resolve thay vì từ chối request. Nếu hợp đồng yêu cầu `size=101` trả `400`, cần kiểm tra giá trị đầu vào trước khi chỉ còn nhìn thấy giá trị đã được resolver chuẩn hóa.

Với form/model binding, `WebDataBinder.setAllowedFields(...)` thuộc đường binding đó. Không mặc định rằng nó cũng lọc field JSON được Jackson đọc. Spring khuyến nghị dùng model đầu vào riêng và kiểm soát trường được bind; xem [thiết kế model trong tài liệu InitBinder](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html).

## 4. Dữ liệu kiểm thử phải phân biệt được các lỗi

Một tập dữ liệu quá đồng nhất có thể khiến bộ lọc sai vẫn trả đúng số dòng.

Dùng fixture:

| ID | Tenant | Tên | Giá | Trạng thái | Ghi chú nội bộ |
| --- | --- | --- | --- | --- | --- |
| 41 | 7 | Keyboard Mini | 100000 | ACTIVE | NOTE-41 |
| 42 | 7 | Mouse Pro | 200000 | ARCHIVED | NOTE-42 |
| 51 | 8 | Keyboard Mini | 100000 | ACTIVE | NOTE-51 |
| 52 | 8 | Desk | 300000 | ACTIVE | NOTE-52 |

Thiết kế này giúp phát hiện:

- Thiếu điều kiện tên: request `name=key` có thể trả thêm sản phẩm 42.
- Thiếu điều kiện tenant: sản phẩm 51 có cùng tên và trạng thái với 41 nên có thể lọt vào.
- Xử lý sai nhiều trạng thái: request hai trạng thái có thể bị mất sản phẩm 42.
- Lộ field: các giá trị ghi chú được đặt rõ để nhận ra trong response.
- Sai metadata tổng: tenant 7 có hai sản phẩm, toàn bộ kho có bốn.

Dùng thứ tự sort xác định, chẳng hạn `id ASC`, khi assertion phụ thuộc thứ tự. Với test chỉ quan tâm tập kết quả, so sánh tập ID thay vì thứ tự ngẫu nhiên từ kho dữ liệu.

## 5. Chọn mức kiểm thử theo điều cần chứng minh

| Mức kiểm thử | Phù hợp cho | Chưa tự chứng minh |
| --- | --- | --- |
| Unit test policy/mapper | Giới hạn số giá trị, độ dài, cardinality và mapping trường | Resolver, conversion và serializer thực tế |
| `@WebMvcTest` với collaborator giả | HTTP status, DTO validation và schema lỗi trong web slice | Metadata repository và thực thi predicate tại store |
| `@SpringBootTest` + `@AutoConfigureMockMvc` + repository thực | Binding qua MVC, điều kiện thực thi, tenant và JSON kết quả | Giới hạn của reverse proxy hoặc container HTTP thật |
| HTTP test qua server thật | Giới hạn URI/body, giải mã URL và cấu hình triển khai | Tự động rollback transaction giữa client và server |

`@WebMvcTest` giới hạn các thành phần được nạp. Khi kiểm tra Querydsl binding, phải bảo đảm customizer, Q-type và metadata cần thiết có mặt; không suy rằng một web slice mặc định chứa toàn bộ repository. Xem [API WebMvcTest](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/servlet/WebMvcTest.html).

`@SpringBootTest` kết hợp `@AutoConfigureMockMvc` cho phép dùng context ứng dụng với request mô phỏng. Khi chuyển sang server thật ở `RANDOM_PORT`, client và server có thể chạy trong transaction khác nhau; annotation transaction trên test không tự rollback những ghi dữ liệu do server thực hiện. Chi tiết nằm trong [tài liệu kiểm thử Boot](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html).

## 6. Khung kiểm thử tích hợp qua MockMvc

Giả định ứng dụng đã có:

- Repository `ProductRepository` hỗ trợ truy vấn cần kiểm tra.
- Domain `Product` có constructor theo fixture dưới đây và mapping JPA tương ứng.
- `ProductStatus` gồm `ACTIVE`, `ARCHIVED`.
- Một interface ứng dụng `TenantScope` có phương thức `Long requiredTenantId()`.
- Endpoint và error handler thực hiện hợp đồng ở phần 2.

Test dùng database riêng, ban đầu rỗng, và transaction rollback cho mỗi test đồng bộ. Constructor domain trong ví dụ là quy ước fixture, cần điều chỉnh theo entity của dự án.

```java
package example.catalog;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.math.BigDecimal;
import java.util.List;

import jakarta.persistence.EntityManager;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
@Import(ProductWebContractTest.FixedTenant.class)
@WithMockUser(authorities = {"products:read", "products:write"})
class ProductWebContractTest {

    @Autowired MockMvc mvc;
    @Autowired ProductRepository repository;
    @Autowired EntityManager entityManager;

    @BeforeEach
    void seed() {
        repository.saveAll(List.of(
                new Product(41L, 7L, "Keyboard Mini",
                        new BigDecimal("100000"), ProductStatus.ACTIVE,
                        "NOTE-41"),
                new Product(42L, 7L, "Mouse Pro",
                        new BigDecimal("200000"), ProductStatus.ARCHIVED,
                        "NOTE-42"),
                new Product(51L, 8L, "Keyboard Mini",
                        new BigDecimal("100000"), ProductStatus.ACTIVE,
                        "NOTE-51"),
                new Product(52L, 8L, "Desk",
                        new BigDecimal("300000"), ProductStatus.ACTIVE,
                        "NOTE-52")));

        entityManager.flush();
        entityManager.clear();
    }

    @Test
    void nameFilterKeepsTenantScope() throws Exception {
        mvc.perform(get("/products")
                        .param("name", "key")
                        .param("sort", "id,asc"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content.length()").value(1))
                .andExpect(jsonPath("$.content[0].id").value(41))
                .andExpect(jsonPath("$.page.totalElements").value(1));
    }

    @Test
    void emptyFilterStillKeepsTenantScope() throws Exception {
        mvc.perform(get("/products").param("sort", "id,asc"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content.length()").value(2))
                .andExpect(jsonPath("$.content[0].id").value(41))
                .andExpect(jsonPath("$.content[1].id").value(42))
                .andExpect(jsonPath("$.page.totalElements").value(2));
    }

    @Test
    void clientCannotSelectAnotherTenant() throws Exception {
        mvc.perform(get("/products").param("tenantId", "8"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_QUERY"));
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class FixedTenant {

        @Bean
        @Primary
        TenantScope fixedTenantScope() {
            return () -> 7L;
        }
    }
}
```

`flush` và `clear` giúp phép kiểm tra truy vấn đi qua trạng thái dữ liệu đã đồng bộ, thay vì chỉ dựa vào các đối tượng đang giữ trong persistence context.

Bean tenant cố định giúp kiểm tra service có giữ điều kiện tenant hay không. Nó **không kiểm tra** việc ứng dụng suy tenant từ danh tính đã đăng nhập; cần test riêng cho bước đó. `@WithMockUser` cung cấp danh tính và authority trong test, không tự tạo chính sách tenant.

Không mock repository trả sẵn đúng hai dòng cho các test trên rồi kết luận predicate tenant đã đúng. Muốn chứng minh filter được thực thi, cần repository và dữ liệu có khả năng làm lộ lỗi.

## 7. Kiểm thử giới hạn bộ lọc ở đúng biên

Các phương thức sau có thể bổ sung vào lớp kiểm thử phần 6, với import JUnit parameterized test và các matcher tương ứng.

### 7.1. Độ dài tên và giá trị rỗng

```java
@ParameterizedTest
@CsvSource({"64,200", "65,400"})
void nameLengthBoundary(int length, int expectedStatus) throws Exception {
    mvc.perform(get("/products").param("name", "a".repeat(length)))
            .andExpect(status().is(expectedStatus));
}

@Test
void blankNameIsRejectedInsteadOfRemovingTheFilter() throws Exception {
    mvc.perform(get("/products").param("name", ""))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_QUERY"));
}

@Test
void repeatedNameIsRejectedByTheApiContract() throws Exception {
    mvc.perform(get("/products").param("name", "key", "mouse"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_QUERY"));
}
```

Import bổ sung:

```java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
```

Các assertion `400` ở đây kiểm tra chính sách API đã chọn. Mặc định của framework có thể bỏ qua một giá trị rỗng hoặc binding `first(...)` có thể chỉ dùng giá trị đầu tiên; vì vậy test cần chứng minh lớp kiểm tra request không để hành vi đó thay thế hợp đồng.

Nên thêm trường hợp chỉ có khoảng trắng theo quy tắc chuẩn hóa của API. `""`, `" "` và một giá trị rỗng trong tập tham số lặp không nhất thiết đi qua cùng một nhánh xử lý.

### 7.2. Nhiều giá trị status

```java
@Test
void twentyStatusValuesAreAccepted() throws Exception {
    String[] values = java.util.stream.IntStream.range(0, 20)
            .mapToObj(i -> i % 2 == 0 ? "ACTIVE" : "ARCHIVED")
            .toArray(String[]::new);

    mvc.perform(get("/products")
                    .param("status", values)
                    .param("sort", "id,asc"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.content.length()").value(2))
            .andExpect(jsonPath("$.content[0].id").value(41))
            .andExpect(jsonPath("$.content[1].id").value(42));
}

@Test
void twentyOneStatusValuesAreRejected() throws Exception {
    String[] values = java.util.Collections.nCopies(21, "ACTIVE")
            .toArray(String[]::new);

    mvc.perform(get("/products").param("status", values))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_QUERY"))
            .andExpect(jsonPath("$.fieldErrors[0].field").value("status"));
}
```

Fixture có cả hai trạng thái trong tenant 7. Vì thế test đầu kiểm tra được ý nghĩa `in`, không chỉ việc HTTP trả `200`.

Nếu error handler có thể trả nhiều lỗi không theo thứ tự cố định, thay assertion phần tử đầu bằng kiểm tra tập field lỗi. Không tạo phụ thuộc thứ tự mảng lỗi khi hợp đồng không quy định nó.

Nên có thêm ca enum không hợp lệ, như `status=UNKNOWN`. Nó kiểm tra chuyển kiểu và xử lý lỗi, khác với bộ lọc hợp lệ nhưng không tìm thấy dữ liệu.

### 7.3. Page size và sort cần kiểm tra riêng

```java
@Test
void pageSizeAboveTheContractIsRejected() throws Exception {
    mvc.perform(get("/products").param("size", "101"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_QUERY"));
}

@Test
void internalSortFieldIsRejected() throws Exception {
    mvc.perform(get("/products").param("sort", "internalNote,asc"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_QUERY"));
}

@Test
void aSingleSortParameterCannotHideThreeOrders() throws Exception {
    mvc.perform(get("/products").param("sort", "id,name,price,asc"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_QUERY"));
}
```

Một tham số `sort` có thể chứa nhiều thuộc tính. Giới hạn hai `Sort.Order` phải kiểm tra số order thực tế, không chỉ số lần khóa `sort` xuất hiện.

Bổ sung các ca `size=1`, `size=100`, `size=0`, `page=-1`, số vượt miền biểu diễn và nhiều giá trị cho tham số phải là đơn trị. Từng ca cần kỳ vọng rõ: từ chối hay chuẩn hóa. Bài chọn từ chối giá trị ngoài hợp đồng.

### 7.4. Đặt giới hạn trước bước cần được bảo vệ

Nếu việc đếm giá trị chỉ chạy trong thân controller sau khi `@QuerydslPredicate` đã chuyển đổi toàn bộ request, nó chưa giới hạn chi phí của chính bước binding.

Với giới hạn nhằm bảo vệ binding, cần đặt policy ở vị trí thích hợp trước argument resolution, chẳng hạn một interceptor hoặc filter được thiết kế cho endpoint. Kiểm tra thêm rằng request vượt giới hạn không đi tới bước truy vấn hoặc tác động dữ liệu.

Có thể dùng collaborator giả trong web test hoặc bộ đếm truy vấn của môi trường tích hợp để quan sát điều này. Không dùng một assertion thời gian rất ngắn trên máy phát triển làm bằng chứng duy nhất.

## 8. Kiểm thử phạm vi trường ghi của JSON payload

### 8.1. Request DTO phải thể hiện đúng trường được ghi

Ví dụ DTO cho hợp đồng POST:

```java
package example.catalog;

import java.math.BigDecimal;
import java.util.List;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateProductRequest(
        @NotBlank @Size(max = 80) String name,
        @NotNull @DecimalMin("0.00") BigDecimal price,
        @NotNull @Size(max = 8)
        List<@NotBlank @Size(max = 24) String> tags) {
}
```

Phương thức controller cần kích hoạt validation, ví dụ bằng `@Valid @RequestBody CreateProductRequest request`, với Bean Validation provider phù hợp. MVC hỗ trợ validation cho `@RequestBody`; xem [tài liệu RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html).

Không có `tenantId` trong DTO giúp tách dữ liệu ghi của client khỏi dữ liệu server quản lý. Tuy nhiên, DTO thiếu field không tự chứng minh request có field dư sẽ bị từ chối.

Với đường Jackson 2 thông thường của Boot 3.5, một cấu hình có thể dùng cho chính sách từ chối unknown property là:

```yaml
spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
```

Ứng dụng vẫn phải dùng đúng mapper và không có annotation hoặc custom converter làm thay đổi chính sách đó. Cấu hình feature Jackson qua các property tương ứng được áp dụng bởi [JacksonAutoConfiguration của Boot](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.5.0/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/jackson/JacksonAutoConfiguration.java).

Test phải nạp cùng chính sách thực sự của ứng dụng. Chỉ bật feature trong test để assertion xanh, trong khi cấu hình phục vụ client khác đi, sẽ tạo kết luận sai.

### 8.2. Kiểm tra từng trường server quản lý một cách độc lập

Một payload có sáu field cấm cùng lúc có thể bị từ chối vì chỉ một field. Nó chưa chứng minh năm field còn lại cũng được bảo vệ.

Bổ sung vào lớp test:

```java
@Autowired
com.fasterxml.jackson.databind.ObjectMapper objectMapper;

static java.util.stream.Stream<org.junit.jupiter.params.provider.Arguments>
serverManagedFields() {
    return java.util.stream.Stream.of(
            org.junit.jupiter.params.provider.Arguments.of("id", 9001L),
            org.junit.jupiter.params.provider.Arguments.of("tenantId", 8L),
            org.junit.jupiter.params.provider.Arguments.of("status", "ARCHIVED"),
            org.junit.jupiter.params.provider.Arguments.of(
                    "internalNote", "CLIENT-NOTE"),
            org.junit.jupiter.params.provider.Arguments.of("createdBy", "client"),
            org.junit.jupiter.params.provider.Arguments.of(
                    "createdDate", "2026-01-01T00:00:00Z"));
}

@ParameterizedTest
@org.junit.jupiter.params.provider.MethodSource("serverManagedFields")
void serverManagedFieldsCannotBeWritten(
        String field, Object value) throws Exception {

    long before = repository.count();

    var body = objectMapper.createObjectNode();
    body.put("name", "New Keyboard");
    body.put("price", 150000);
    body.putArray("tags").add("office");
    body.set(field, objectMapper.valueToTree(value));

    mvc.perform(post("/products")
                    .with(csrf())
                    .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
                    .content(objectMapper.writeValueAsBytes(body)))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_BODY"));

    org.assertj.core.api.Assertions.assertThat(repository.count())
            .isEqualTo(before);
}
```

Import static bổ sung:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
```

Giá trị đưa vào mỗi field được chọn để hợp lý với kiểu dữ liệu thường dùng. Nếu cố tình gửi một kiểu vô nghĩa, test có thể chỉ phát hiện lỗi chuyển kiểu thay vì việc field đó đáng lẽ không được ghi.

`csrf()` phục vụ test có Spring Security và CSRF đang hoạt động. Nó giúp request đến được bước cần kiểm tra; không để lỗi CSRF `403` bị nhầm thành validation payload thành công. Xem [kiểm thử CSRF với MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html).

### 8.3. Kiểm tra biên validation và trạng thái sau request

Ma trận tối thiểu cho DTO:

| Đầu vào | Kỳ vọng theo hợp đồng |
| --- | --- |
| `name` thiếu, null hoặc toàn khoảng trắng | `400 INVALID_BODY` |
| Tên 80 ký tự | Hợp lệ nếu các trường còn lại hợp lệ |
| Tên 81 ký tự | `400 INVALID_BODY` |
| `price` âm | `400 INVALID_BODY` |
| `price` bằng 0 | Hợp lệ |
| `tags` có 8 phần tử hợp lệ | Hợp lệ |
| `tags` có 9 phần tử | `400 INVALID_BODY` |
| Một tag rỗng hoặc dài quá 24 ký tự | `400 INVALID_BODY` |
| JSON hỏng cú pháp | `400` theo schema lỗi đã công bố |

Sau request bị từ chối, kiểm tra số dòng và các trường quan trọng chưa bị thay đổi. Với endpoint cập nhật, số dòng không đổi vẫn có thể che giấu một cập nhật sai; phải đọc lại bản ghi đích.

Sau một request tạo hợp lệ, lấy ID từ response rồi đọc lại dữ liệu để kiểm tra tenant thuộc server, trạng thái ban đầu đúng và các field ghi được đã lưu đúng. Nếu auditing được bật, kiểm tra thông tin auditor và thời điểm theo cơ chế đã cấu hình, thay vì so sánh chính xác với đồng hồ hệ thống không được kiểm soát.

Khai báo `BigDecimal` không tự bảo đảm mọi chuỗi JSON đều bị từ chối: Jackson có thể có quy tắc coercion. Nếu hợp đồng yêu cầu JSON number và cấm chuỗi số, phải cấu hình coercion phù hợp rồi kiểm tra cả hai dạng.

## 9. Projection payload và collection cần bộ ca riêng

### 9.1. Các JSONPath được hỗ trợ phải được kiểm tra qua HTTP

Ví dụ interface đọc payload:

```java
import java.math.BigDecimal;
import java.util.List;

import org.springframework.data.web.JsonPath;
import org.springframework.data.web.ProjectedPayload;

@ProjectedPayload
public interface ProductPayload {

    @JsonPath({"$.name", "$.product.name"})
    String getName();

    @JsonPath({"$.price", "$.product.price"})
    BigDecimal getPrice();

    @JsonPath({"$.tags", "$.product.tags"})
    List<String> getTags();
}
```

Ví dụ minh họa hai hình dạng dữ liệu. Cần dependency và converter hỗ trợ JSONPath theo phiên bản đang dùng; xem [web databinding của Commons](https://docs.spring.io/spring-data/commons/reference/3.5/repositories/core-extensions-web.html).

Với endpoint thực sự dùng projection này, kiểm tra:

- Payload phẳng và payload lồng đều đưa đúng giá trị vào lệnh nghiệp vụ.
- Thiếu path, path có null và path sai kiểu được xử lý đúng hợp đồng.
- Khi cả hai vị trí cùng xuất hiện, quy tắc ưu tiên hoặc từ chối mơ hồ được công bố rõ.
- Một object không liên quan như `audit.name` không vô tình thay tên sản phẩm.
- Field ngoài getter không được chuyển tiếp thành dữ liệu ghi của domain.
- Giới hạn collection vẫn được thực thi ở đúng đường xử lý payload.

Các biểu thức JSONPath quá rộng như `$..name` có thể đọc tên ở nhiều vị trí. Nếu hợp đồng chỉ hỗ trợ hai vị trí cụ thể, kiểm thử cần chứng minh dữ liệu ngoài hai vị trí đó không làm thay đổi giá trị nghiệp vụ.

Không suy rằng getter của projection tự thực hiện toàn bộ validation. Nếu ứng dụng dựa vào constraint trên projection hoặc proxy, phải kiểm tra constraint thực sự chạy. Một cách khác là đọc projection rồi tạo command có validation tường minh trước khi ghi.

Chính sách unknown property của DTO Jackson cũng không tự chứng minh JSONPath projection từ chối mọi field thừa: hai đường đọc payload có cơ chế khác nhau.

### 9.2. Phân biệt collection binding từ tham số request với mảng JSON

Với projection được bind từ tham số request/form, các khóa dạng `tags[0]`, `tags[1]` có thể đi qua `ProxyingHandlerMethodArgumentResolver` và `MapDataBinder`.

Tài liệu Commons hiện mô tả giới hạn mặc định 1024 phần tử cho collection-like binding và property `spring.data.web.projection.collection-limit`, cấu hình qua `spring.properties` hoặc system property. Cần đối chiếu đúng phiên bản có tính năng đó; không suy rằng mọi bản vá của một dòng Commons đều có cùng cơ chế.

Giới hạn này thuộc đường binding tương ứng, không thay cho `@Size(max = 8)` của mảng trong JSON DTO hoặc giới hạn byte của toàn request.

Khi phiên bản hỗ trợ và ứng dụng chọn collection limit bằng 8, bộ ca nên có:

| Dạng đầu vào form/projection | Mục đích |
| --- | --- |
| Chỉ số liên tục từ 0 đến 6 | Trường hợp dưới biên |
| Chỉ số liên tục từ 0 đến 7 | Trường hợp đúng biên |
| Có chỉ số 8 | Trường hợp cần collection vượt biên |
| Chỉ gửi một khóa `tags[8]` | Phát hiện cách đếm chỉ dựa vào số khóa gửi |
| Collection lồng nhau | Kiểm tra giới hạn tại cấu trúc mà binder thực sự tạo |

Theo hợp đồng chọn từ chối, trường hợp vượt biên phải trả lỗi đầu vào được xử lý rõ, không ghi một phần dữ liệu và không trở thành lỗi server ngoài dự kiến.

Property được resolver đọc theo cơ chế của phiên bản cụ thể và thường cần có trước khi tạo resolver/context. Đừng giả định rằng thêm tên tương tự vào `@SpringBootTest(properties = ...)` luôn tương đương một Spring property hoặc JVM system property mà thành phần đó đọc.

Khi kiểm tra những cấu hình giới hạn khác nhau, cần tính đến context caching và việc khôi phục cấu hình dùng chung. Test phải chứng minh giới hạn thực sự đang có hiệu lực, không chỉ chứng minh một chuỗi cấu hình đã được khai báo.

## 10. Kiểm tra chính xác field đầu ra và metadata

Chỉ kiểm tra một field bí mật vắng mặt chưa phát hiện được field nội bộ mới xuất hiện sau này. Với một response có schema đóng, kiểm tra tập field thực tế sẽ mạnh hơn.

Bổ sung các import:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;

import com.fasterxml.jackson.databind.JsonNode;
```

Sử dụng `objectMapper` đã được inject trong lớp test:

```java
@Test
void responseContainsOnlyThePublishedFields() throws Exception {
    String json = mvc.perform(get("/products")
                    .param("page", "0")
                    .param("size", "1")
                    .param("sort", "id,asc"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.content.length()").value(1))
            .andExpect(jsonPath("$.content[0].id").value(41))
            .andExpect(jsonPath("$.content[0].price").isNumber())
            .andExpect(jsonPath("$.content[0].status").isString())
            .andExpect(jsonPath("$.page.number").value(0))
            .andExpect(jsonPath("$.page.size").value(1))
            .andExpect(jsonPath("$.page.totalElements").value(2))
            .andExpect(jsonPath("$.page.totalPages").value(2))
            .andReturn()
            .getResponse()
            .getContentAsString(StandardCharsets.UTF_8);

    JsonNode root = objectMapper.readTree(json);

    assertThat(fieldNames(root))
            .containsExactlyInAnyOrder("content", "page");

    assertThat(fieldNames(root.path("page")))
            .containsExactlyInAnyOrder(
                    "size", "number", "totalElements", "totalPages");

    for (JsonNode product : root.path("content")) {
        assertThat(fieldNames(product))
                .containsExactlyInAnyOrder(
                        "id", "name", "price", "status");
    }
}

private static Set<String> fieldNames(JsonNode node) {
    assertThat(node.isObject()).isTrue();

    Set<String> fields = new HashSet<>();
    node.fieldNames().forEachRemaining(fields::add);
    return fields;
}
```

Assertion nội dung có một phần tử giúp kiểm tra tập field không trở thành một vòng lặp rỗng luôn thành công.

Metadata tổng cần phản ánh tập dữ liệu đã giới hạn tenant, không phải tổng toàn kho. Với tenant 7 có hai sản phẩm và page size bằng 1, tổng số trang là 2. Một endpoint trả đúng bản ghi đầu nhưng đếm tổng trên mọi tenant vẫn sai hợp đồng.

Nếu API chủ động cho phép thêm field tương thích, hãy điều chỉnh chính sách schema tương ứng. Không dùng schema đóng chỉ vì test dễ viết; lựa chọn phải đến từ hợp đồng dữ liệu.

Cũng cần kiểm tra:

- Trang không có kết quả vẫn giữ kiểu mảng và metadata phù hợp.
- Request dùng quy ước số trang nào, response dùng quy ước nào.
- Sort và filter không làm dữ liệu tenant khác lọt vào metadata hoặc nội dung.
- Response từ DTO, projection hoặc chế độ `VIA_DTO` thực sự có hình dạng đã công bố.
- Nội dung lỗi không làm lộ ghi chú nội bộ, câu truy vấn hoặc stack trace ngoài hợp đồng.

Thay đổi schema phân trang phải được xem như thay đổi giao tiếp với client. Kiểu Java trả về giống nhau không bảo đảm JSON runtime vẫn giống nhau.

## 11. Hợp đồng lỗi cần được kiểm thử độc lập

Một ma trận lỗi hữu ích:

| Trường hợp | Điều cần assert |
| --- | --- |
| Khóa query không được công bố | Status và `INVALID_QUERY`; không thực thi tìm kiếm ngoài dự kiến |
| Enum hoặc số sai định dạng | Lỗi đầu vào, không biến thành lọc rỗng |
| Quá nhiều giá trị | Đúng giới hạn, đúng field lỗi |
| JSON hỏng hoặc field không hợp lệ | Mã lỗi body theo hợp đồng, không tạo dữ liệu |
| Thiếu quyền | Chính sách xác thực/phân quyền thực tế; không nhầm với validation |
| Không có kết quả tìm kiếm hợp lệ | `200` với trang rỗng theo hợp đồng, khác request sai |
| Kho dữ liệu không truy cập được | Lỗi vận hành thích hợp; không ánh xạ thành “không có dữ liệu” |

Đối với lỗi thuộc ứng dụng, có thể thêm assertion:

```java
.andExpect(jsonPath("$.code").value("INVALID_QUERY"))
.andExpect(jsonPath("$.message").isString())
.andExpect(jsonPath("$.trace").doesNotExist())
```

Không chỉ kiểm tra `is4xxClientError()` cho mọi ca. Nếu request payload bị CSRF chặn bằng `403`, test đó chưa kiểm tra body validation. Nếu đường dẫn sai trả `404`, nó cũng chưa kiểm tra giới hạn filter.

Các request dùng `@WithMockUser` trong ví dụ tập trung vào logic endpoint. Cần nhóm test khác xác minh quyền truy cập thật, bao gồm người chưa đăng nhập, người thiếu authority và cách suy tenant từ principal. Tài liệu [Spring Security về danh tính trong MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html) mô tả các cơ chế hỗ trợ test này.

Tránh bắt mọi exception rồi đổi thành cùng một `400`. Cách đó có thể khiến lỗi lập trình, lỗi kết nối hoặc lỗi mapping được che dưới dạng request không hợp lệ.

## 12. Những giới hạn cần kiểm thử ngoài MockMvc

`MockMvc.param(...)` đưa tham số vào request mô phỏng; nó không chứng minh reverse proxy hoặc container đã áp dụng giới hạn trên URI thực.

Tương tự, tạo sẵn một byte array rồi đưa vào `MockMvc.content(...)` không đủ chứng minh giới hạn đọc body trên đường truyền HTTP đang hoạt động.

| Giới hạn | Mức kiểm thử cần có |
| --- | --- |
| Số giá trị filter và độ dài sau giải mã | HTTP application test, cùng kiểm tra policy trước binding nếu cần |
| Tổng độ dài URI/query string | Request qua server/container hoặc đường triển khai tương ứng |
| Số byte body | HTTP thật qua thành phần chịu trách nhiệm giới hạn |
| JSON lồng sâu | Parser và cấu hình thực tế, không chỉ DTO validation |
| Collection của projection/form | Resolver/binder tương ứng và đúng phiên bản |
| Mảng trong JSON DTO | Message converter cùng validation collection |
| Số order sort, page size | Resolver và policy của ứng dụng |
| Chi phí truy vấn hoặc giới hạn đếm | Tích hợp với store và dữ liệu đại diện |

Các mã như `413` cho body quá lớn hoặc `414` cho URI quá dài cần được công bố theo cấu hình triển khai. Chúng không phải hành vi do Commons tự bảo đảm cho mọi endpoint.

Khi thử giới hạn, dùng kích thước ngay dưới biên, đúng biên và vượt một đơn vị. Không cần tạo payload cực lớn chỉ để kiểm tra một giới hạn nhỏ.

Cũng cần tách:

- Độ dài chuỗi theo đơn vị mà Java hoặc validator sử dụng.
- Số ký tự theo quy ước nghiệp vụ.
- Số byte của UTF-8 trên đường truyền.

Các test `"a".repeat(...)` trong bài cố tình dùng ASCII để xác định rõ biên đơn giản. API có người dùng nhập tiếng Việt nên bổ sung Unicode, dấu kết hợp và quy tắc chuẩn hóa nếu chúng ảnh hưởng hợp đồng.

## 13. Duy trì bộ kiểm thử khi domain và phiên bản thay đổi

Một thay đổi nhỏ trong entity có thể làm phạm vi web thay đổi nếu API dựa vào binding rộng. Vì thế, khi thêm field mới, đổi alias hoặc đổi customizer, cần kiểm tra lại những hợp đồng liên quan.

Một số phép kiểm tra bổ sung có giá trị:

- Đổi thứ tự các giá trị `status` nhưng giữ cùng tập giá trị không làm thay đổi tập kết quả khi sort đã xác định.
- Mở rộng tập trạng thái được lọc có thể mở rộng kết quả trong tenant, nhưng không đưa dữ liệu tenant khác vào.
- Thêm một điều kiện `AND` hợp lệ không làm rộng tập kết quả đầy đủ.
- Thay đổi field không được ghi trong request không được thay đổi dữ liệu server quản lý.
- Thêm field nội bộ vào domain không tự làm field đó xuất hiện trong response đóng.

Với phép kiểm tra quan hệ tập kết quả, cần so sánh tập đầy đủ hoặc một phạm vi đủ kiểm soát. So sánh riêng trang đầu có thể gây kết luận sai vì phân trang làm các bản ghi dịch chuyển giữa các trang.

Nếu chạy tích hợp bằng database khác với môi trường triển khai, xác định các trường hợp phải kiểm tra lại trên engine thật: so sánh chuỗi, sort, null, precision số và những phép toán Querydsl mà store dịch khác nhau. Commons cung cấp abstraction, không làm mọi backend có hành vi vật lý giống nhau.

Sau khi đổi phiên bản, giữ sự phân biệt giữa:

1. Hành vi framework thực sự hỗ trợ ở phiên bản đó.
2. Chính sách ứng dụng chủ động bổ sung.
3. Hợp đồng mà client đã được công bố.

Một test thất bại có thể cho biết cấu hình không còn được nạp, mapper đã thay đổi, resolver đang chuẩn hóa khác hoặc customizer không còn được chọn như trước. Không sửa kỳ vọng theo output mới trước khi xác định thay đổi đó có đúng hợp đồng không.

## 14. Tiêu chí hoàn tất một nhóm kiểm thử

Có thể xem nhóm kiểm thử đủ cho phạm vi đã chọn khi nó chứng minh được các kết quả sau:

| Phạm vi | Bằng chứng cần có |
| --- | --- |
| Bộ lọc | Có ca đúng ý nghĩa và ca sai định dạng, không chỉ kiểm tra HTTP thành công |
| Giới hạn | Có dưới biên, đúng biên và vượt biên tại thành phần thực thi giới hạn |
| Phạm vi trường | Phân biệt filter, sort, input ghi và output |
| Tenant | Có dữ liệu tenant khác dễ khớp filter; cả nội dung lẫn tổng đều đúng phạm vi |
| Payload | Có thiếu/null/sai kiểu/trường dư và trường hợp hợp lệ |
| Tác động dữ liệu | Request bị từ chối không tạo hoặc thay đổi dữ liệu ngoài hợp đồng |
| JSON | Assert field, kiểu dữ liệu, metadata và lỗi theo schema đã chọn |
| Môi trường | Test nạp đúng resolver, converter, customizer và policy cần kiểm tra |

Bộ kiểm thử tốt làm rõ điều API chấp nhận, điều nó từ chối và dữ liệu nào được phép đi qua từng ranh giới. Khi các ranh giới đó được kiểm tra bằng request cùng dữ liệu có khả năng phân biệt lỗi, các abstraction web của Spring Data Commons mới được sử dụng đúng trong bối cảnh repository và kho dữ liệu thực tế.
