# Tái sử dụng request field descriptors

## 1. Vì sao cần tái sử dụng FieldDescriptor?

Trong học phần **Spring REST Docs (SPRING_REST_DOCS)** thuộc chương **Tái sử dụng**, các bài kiểm thử HTTP tạo snippet request/response và descriptor để mô tả hợp đồng API. Khi nhiều endpoint nhận payload có cấu trúc gần nhau, việc viết lại cùng một nhóm field descriptor làm test dài, khó cập nhật và dễ tạo mô tả không nhất quán.

Ví dụ các endpoint tạo sản phẩm, nhập sản phẩm từ file và cập nhật sản phẩm đều có những field chung như name, price và description. Nếu mỗi test tự khai báo các field đó, một thay đổi về ý nghĩa hoặc mô tả phải sửa ở nhiều nơi.

Spring REST Docs biểu diễn mô tả payload bằng FieldDescriptor. Các hàm requestFields(...) nhận descriptor để tạo snippet request-fields.adoc và kiểm tra payload thực tế theo mô tả. Ta có thể tổ chức descriptor thành hằng số, factory method hoặc danh sách dùng chung rồi kết hợp với field riêng của từng endpoint.

Sau bài học, bạn có thể:

- Nhận diện các field descriptor dùng chung giữa nhiều request.
- Tổ chức descriptor bằng factory method trả về danh sách mới.
- Kết hợp field chung với field riêng của từng operation.
- Tái sử dụng mô tả cho object lồng nhau và subsection.
- Tránh chia sẻ trạng thái optional/ignored không chủ ý giữa các test.
- Giữ strict validation để phát hiện payload thay đổi mà tài liệu chưa cập nhật.

Ví dụ dùng **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter và MockMvc**. Nếu dùng WebTestClient hoặc REST Assured, cách gọi client khác nhưng danh sách FieldDescriptor vẫn có thể được tổ chức tương tự.

## 2. FieldDescriptor và requestFields(...)

Một request payload có thể là JSON:

```json
{
  "name": "Mechanical Keyboard",
  "description": "Bàn phím cơ cho văn phòng",
  "price": 89.5
}
```

Mỗi field được mô tả bằng fieldWithPath(...):

```java
requestFields(
    fieldWithPath("name").description("Tên sản phẩm"),
    fieldWithPath("description").description("Mô tả sản phẩm"),
    fieldWithPath("price").description("Giá bán")
)
```

Mỗi FieldDescriptor có path, description và metadata như optional, ignored, type hoặc attributes. requestFields(...) dùng descriptor để:

1. Sinh bảng field cho tài liệu.
2. Đối chiếu descriptor với payload request mà test ghi nhận.
3. Báo lỗi nếu payload có field chưa được mô tả hoặc descriptor bắt buộc không xuất hiện.

Đó là lý do tái sử dụng descriptor có lợi hơn việc sao chép một bảng mô tả bằng tay: các test vẫn thực thi kiểm tra hợp đồng cho từng operation.

## 3. Cách 1: hằng số descriptor dùng chung

Nếu các field giống nhau hoàn toàn về path và mô tả, có thể đặt chúng trong một lớp hỗ trợ test:

```java
package com.example.catalog.docs;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

import org.springframework.restdocs.payload.FieldDescriptor;

public final class ProductFieldDescriptors {
    private ProductFieldDescriptors() {}

    public static final FieldDescriptor PRODUCT_NAME =
        fieldWithPath("name").description("Tên sản phẩm");

    public static final FieldDescriptor PRODUCT_DESCRIPTION =
        fieldWithPath("description").description("Mô tả sản phẩm");

    public static final FieldDescriptor PRODUCT_PRICE =
        fieldWithPath("price").description("Giá bán");
}
```

Sử dụng:

```java
document("products-create",
    requestFields(
        PRODUCT_NAME,
        PRODUCT_DESCRIPTION,
        PRODUCT_PRICE
    )
)
```

Cách này rõ ràng khi descriptor có cùng path, description và trạng thái optional/ignored. Tuy vậy, FieldDescriptor có các phương thức cấu hình như optional() hoặc ignored() làm thay đổi descriptor. Không nên lấy một instance static dùng chung rồi cấu hình khác nhau trong từng test. Một test đánh dấu descriptor là optional có thể vô tình ảnh hưởng operation khác sử dụng cùng instance.

Nếu cùng field bắt buộc ở endpoint A nhưng tùy chọn ở endpoint B, factory method tạo descriptor mới cho mỗi operation sẽ an toàn hơn.

## 4. Cách 2: factory method trả về descriptor mới

Đây là cách nên ưu tiên khi descriptor có trạng thái khác nhau giữa endpoint. Mỗi lần gọi factory, tạo FieldDescriptor mới:

```java
package com.example.catalog.docs;

import java.util.List;
import org.springframework.restdocs.payload.FieldDescriptor;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

public final class ProductFieldDescriptors {
    private ProductFieldDescriptors() {}

    public static List<FieldDescriptor> commonProductRequestFields() {
        return List.of(
            fieldWithPath("name").description("Tên sản phẩm"),
            fieldWithPath("description").description("Mô tả sản phẩm"),
            fieldWithPath("price").description("Giá bán")
        );
    }
}
```

Sử dụng:

```java
document("products-create",
    requestFields(ProductFieldDescriptors.commonProductRequestFields())
)
```

Overload requestFields(List<FieldDescriptor>) nhận danh sách descriptor. List.of(...) trả về danh sách không thể thêm/xóa phần tử; factory tạo các descriptor mới mỗi lần gọi.

### Tạo bộ descriptor khác nhau theo hợp đồng

Giả sử POST yêu cầu đủ field, còn PATCH cho phép từng field vắng mặt:

```java
public static List<FieldDescriptor> productCreateFields() {
    return List.of(
        fieldWithPath("name").description("Tên sản phẩm"),
        fieldWithPath("description").description("Mô tả sản phẩm"),
        fieldWithPath("price").description("Giá bán")
    );
}

public static List<FieldDescriptor> productUpdateFields() {
    return List.of(
        fieldWithPath("name").description("Tên sản phẩm").optional(),
        fieldWithPath("description").description("Mô tả sản phẩm").optional(),
        fieldWithPath("price").description("Giá bán").optional()
    );
}
```

Mỗi method tạo descriptor mới và thể hiện rõ hợp đồng của operation. Không lấy danh sách dùng chung rồi gọi optional() trên các descriptor trong một test.

## 5. Kết hợp field dùng chung với field riêng

Nhiều endpoint có tập field chung nhưng vẫn có field đặc thù. Ví dụ tạo sản phẩm có thêm initialStock; nhập sản phẩm có thêm sourceSystem.

Có thể ghép bằng ArrayList:

```java
static List<FieldDescriptor> productCreateWithStockFields() {
    List<FieldDescriptor> fields =
        new ArrayList<>(ProductFieldDescriptors.commonProductRequestFields());

    fields.add(
        fieldWithPath("initialStock")
            .description("Số lượng tồn kho ban đầu")
    );
    return fields;
}
```

Truyền danh sách đã ghép:

```java
document("products-create-with-stock",
    requestFields(productCreateWithStockFields())
)
```

Hoặc thêm nhiều field riêng:

```java
static List<FieldDescriptor> productImportFields() {
    List<FieldDescriptor> fields =
        new ArrayList<>(ProductFieldDescriptors.commonProductRequestFields());
    fields.add(fieldWithPath("sourceSystem")
        .description("Hệ thống nguồn của bản ghi"));
    fields.add(fieldWithPath("externalId")
        .description("Mã sản phẩm tại hệ thống nguồn"));
    return fields;
}
```

Đặt tên factory theo operation hoặc nhóm hợp đồng để người đọc hiểu danh sách nào đang được áp dụng. Không tạo một danh sách duy nhất chứa mọi field của mọi endpoint; strict validation sẽ mất ý nghĩa nếu operation phải mô tả field không thuộc payload của nó.

## 6. Ví dụ MockMvc dùng descriptor ở nhiều operation

Giả sử controller có hai endpoint tạo mới và nhập sản phẩm:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {
    @PostMapping
    ProductResponse create(@RequestBody ProductRequest request) {
        return new ProductResponse(42L, request.name(), request.price());
    }

    @PostMapping("/import")
    ProductResponse importProduct(@RequestBody ProductImportRequest request) {
        return new ProductResponse(43L, request.name(), request.price());
    }

    record ProductRequest(String name, String description, BigDecimal price) {}
    record ProductImportRequest(
        String name, String description, BigDecimal price, String sourceSystem
    ) {}
    record ProductResponse(long id, String name, BigDecimal price) {}
}
```

Các test có thể dùng chung descriptor:

```java
@WebMvcTest(ProductController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductRequestDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void createProduct() throws Exception {
        mockMvc.perform(post("/api/products")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name": "Keyboard",
                      "description": "Mechanical keyboard",
                      "price": 89.5
                    }
                    """))
            .andExpect(status().isOk())
            .andDo(document("products-create",
                requestFields(
                    ProductFieldDescriptors.commonProductRequestFields()
                )
            ));
    }

    @Test
    void importProduct() throws Exception {
        mockMvc.perform(post("/api/products/import")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "name": "Keyboard",
                      "description": "Mechanical keyboard",
                      "price": 89.5,
                      "sourceSystem": "ERP"
                    }
                    """))
            .andExpect(status().isOk())
            .andDo(document("products-import",
                requestFields(productImportFields())
            ));
    }
}
```

Trong ví dụ, cả hai operation dùng chung mô tả name, description và price; operation import bổ sung sourceSystem. Mỗi operation có ID riêng nên snippet được ghi vào folder riêng. Descriptor vẫn kiểm tra payload tương ứng; field import chưa được mô tả sẽ làm test strict mode báo lỗi.

## 7. Tái sử dụng descriptor cho object lồng nhau

Một nhóm field có thể lặp lại dưới các object khác nhau:

```json
{
  "shippingAddress": {
    "street": "1 Nguyen Hue",
    "city": "Ho Chi Minh City",
    "postalCode": "700000"
  },
  "billingAddress": {
    "street": "2 Le Loi",
    "city": "Ho Chi Minh City",
    "postalCode": "700000"
  }
}
```

Không thể dùng cùng path street cho cả hai object trong một payload vì path phải xác định vị trí. Hãy tạo factory nhận prefix:

```java
static List<FieldDescriptor> addressFields(String prefix, String label) {
    return List.of(
        fieldWithPath(prefix + ".street")
            .description("Đường của " + label),
        fieldWithPath(prefix + ".city")
            .description("Thành phố của " + label),
        fieldWithPath(prefix + ".postalCode")
            .description("Mã bưu chính của " + label)
    );
}

static List<FieldDescriptor> checkoutFields() {
    List<FieldDescriptor> fields = new ArrayList<>();
    fields.addAll(addressFields("shippingAddress", "địa chỉ giao hàng"));
    fields.addAll(addressFields("billingAddress", "địa chỉ thanh toán"));
    return fields;
}
```

Factory tạo các path khác nhau nhưng tái sử dụng cách mô tả field. Nếu muốn mô tả một object lồng nhau như một subsection thay vì từng field, cân nhắc subsectionWithPath(...). Khi đã mô tả một subsection, tránh mô tả trùng lặp cả subtree và từng field con trong cùng descriptor.

## 8. Tổ chức helper trong test source

Descriptor phục vụ tài liệu thường chỉ cần dùng khi test, vì thế có thể đặt helper trong test source set:

```text
src/
  test/
    java/
      com/example/catalog/
        docs/
          ProductFieldDescriptors.java
          AddressFieldDescriptors.java
        ProductRequestDocumentationTest.java
        ProductImportDocumentationTest.java
```

Không nhất thiết tạo helper cho mỗi field. Tổ chức theo resource/aggregate hoặc nhóm payload dùng chung. Mục tiêu là người viết test tìm được descriptor, hiểu phạm vi sử dụng và không phải duy trì abstraction quá phức tạp.

Nguyên tắc:

- Đặt tên method theo payload hoặc operation, ví dụ commonProductRequestFields() và productImportFields().
- Dùng factory trả list mới nếu descriptor có trạng thái khác nhau giữa operation.
- Chỉ chia sẻ field có cùng path, ý nghĩa và quy tắc optional/ignored.
- Giữ field đặc thù trong factory của operation tương ứng.
- Tránh để helper test phụ thuộc controller hoặc service production.
- Chỉ tạo test-fixture module nếu nhiều module test thực sự cần dùng chung.

## 9. Strict validation, optional và ignored khi reuse

Tái sử dụng descriptor không nên làm giảm kiểm tra hợp đồng:

| Trạng thái | Ý nghĩa |
| --- | --- |
| Mặc định | Field được kỳ vọng có trong payload và được mô tả |
| optional() | Field có thể vắng mặt |
| ignored() | Field được bỏ qua trong bảng và kiểm tra descriptor |
| relaxedRequestFields(...) | Cho phép field payload chưa mô tả nằm ngoài danh sách descriptor |

Nếu field bắt buộc ở endpoint tạo mới nhưng optional ở endpoint cập nhật, không dùng chung một FieldDescriptor instance đã gọi optional(). Tạo hai danh sách riêng bằng factory để không chia sẻ trạng thái.

Chỉ dùng ignored cho field thật sự ngoài phạm vi tài liệu hiện tại. Dùng relaxed mode khi test có phạm vi hẹp; không chuyển toàn bộ suite sang relaxed để che field mới chưa được tài liệu hóa.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Field bị lặp trong request-fields snippet | Hai danh sách cùng thêm một path. | Kiểm tra path trước khi ghép list và giữ một nguồn cho mỗi field. |
| Test này làm test khác chuyển field thành optional | Chia sẻ FieldDescriptor instance và thay đổi trạng thái. | Tạo descriptor mới bằng factory cho mỗi operation. |
| Endpoint import báo field chưa mô tả | Chỉ dùng danh sách field cơ bản và quên field riêng. | Ghép descriptor đặc thù vào danh sách chung. |
| Endpoint create yêu cầu field không có trong payload | Dùng một bộ descriptor cho request shape khác nhau. | Tạo factory theo hợp đồng từng operation. |
| Field lồng nhau không được nhận diện | Path thiếu prefix hoặc sai cấu trúc JSON. | Dùng path đầy đủ như shippingAddress.street. |
| Tài liệu không phát hiện field mới | Dùng relaxedRequestFields quá rộng. | Trở lại strict mode hoặc thu hẹp relaxed descriptor. |
| Helper class khó hiểu | Gom mọi field của mọi resource vào một lớp. | Chia helper theo payload/resource và đặt tên theo phạm vi. |

## 11. Bài thực hành

Tạo API Catalog với ba request shape:

1. POST /api/products: nhận name, description, price.
2. POST /api/products/import: nhận các field trên và thêm sourceSystem.
3. PATCH /api/products/{id}: nhận các field cập nhật có thể vắng mặt.

Thực hiện:

1. Tạo helper ProductFieldDescriptors với factory trả về các field cơ bản.
2. Dùng factory trong test create và import; ghép thêm sourceSystem cho operation import.
3. Tạo factory riêng cho update, đánh dấu field optional theo hợp đồng PATCH.
4. Chạy test và so sánh request-fields.adoc của ba operation.
5. Thử dùng chung descriptor instance rồi gọi optional ở một operation; quan sát nguy cơ trạng thái rò rỉ, sau đó thay bằng factory tạo instance mới.
6. Thêm shippingAddress và billingAddress, dùng factory nhận prefix để tạo path descriptor.
7. Chạy clean test và Asciidoctor; xác nhận snippet được sinh theo từng operation và strict validation vẫn phát hiện field chưa mô tả.

**Tiêu chí hoàn thành:** tổ chức được descriptor dùng chung mà không lặp định nghĩa; kết hợp field riêng của endpoint; tái sử dụng cấu trúc nested path; không làm rò optional/ignored giữa operation; giữ kiểm tra contract và sinh tài liệu từ test.

## 12. Tài liệu tham khảo

- [Spring REST Docs — Request and Response Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/PayloadDocumentation.html)
- [Spring REST Docs — FieldDescriptor API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/FieldDescriptor.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
