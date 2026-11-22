# Tái sử dụng response field descriptors

## 1. Vì sao nên tái sử dụng response field descriptors?

Trong học phần **Spring REST Docs (SPRING_REST_DOCS)** thuộc chương **Tái sử dụng**, các bài kiểm thử HTTP tạo snippet từ response thực tế và dùng field descriptor để mô tả hợp đồng payload. Nhiều endpoint thường trả cùng một cấu trúc hoặc một phần dữ liệu chung: thông tin sản phẩm, người dùng, địa chỉ, metadata phân trang hoặc object lỗi. Nếu mỗi test tự khai báo lại field, tài liệu dễ lệch cách gọi, mô tả không nhất quán và tốn công bảo trì.

Spring REST Docs biểu diễn mô tả JSON response bằng FieldDescriptor. Hàm responseFields(...) nhận các descriptor, tạo snippet response-fields.adoc và kiểm tra cấu trúc payload mà test ghi nhận. Ta có thể gom field dùng chung thành factory method, sau đó ghép thêm field riêng cho từng endpoint.

Ví dụ nhiều API đều trả:

```json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "price": 89.5
}
```

Các field id, name và price có thể dùng chung mô tả. Tuy nhiên endpoint chi tiết có thể trả thêm description và inventory; endpoint tìm kiếm có thể trả danh sách sản phẩm cùng page metadata. Tái sử dụng descriptor cần giữ đúng phạm vi payload của từng operation.

Sau bài học, bạn có thể:

- Tạo bộ response FieldDescriptor dùng chung cho nhiều operation.
- Dùng factory method trả về descriptor mới, tránh chia sẻ trạng thái vô tình.
- Kết hợp field chung với field riêng của response.
- Tái sử dụng descriptor cho object lồng nhau, array và response envelope.
- Xử lý field optional, ignored và relaxed response fields.
- Giữ strict validation để phát hiện response thay đổi mà tài liệu chưa cập nhật.

Ví dụ dùng **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter và MockMvc**. Với WebTestClient hoặc REST Assured, cách gọi client khác nhưng việc tổ chức các FieldDescriptor có thể dùng chung.

## 2. responseFields(...) và FieldDescriptor

Một response JSON:

```json
{
  "id": 42,
  "name": "Mechanical Keyboard",
  "price": 89.5,
  "active": true
}
```

Có thể mô tả bằng:

```java
responseFields(
    fieldWithPath("id").description("Mã sản phẩm"),
    fieldWithPath("name").description("Tên sản phẩm"),
    fieldWithPath("price").description("Giá bán"),
    fieldWithPath("active").description("Sản phẩm đang được kinh doanh")
)
```

Mỗi FieldDescriptor mô tả một path trong response, cùng thông tin như description, type, optional, ignored hoặc attributes. responseFields(...) dùng các descriptor để:

1. Sinh bảng field cho tài liệu.
2. Kiểm tra các field thực tế trong response.
3. Phát hiện field chưa được mô tả hoặc descriptor bắt buộc không xuất hiện trong payload.

Nhờ đó descriptor không chỉ là dữ liệu trình bày. Chúng còn giúp test kiểm soát contract giữa server và client.

## 3. Tạo factory method cho response field dùng chung

Đặt descriptor hỗ trợ tài liệu trong test source set:

```java
package com.example.catalog.docs;

import java.util.List;
import org.springframework.restdocs.payload.FieldDescriptor;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

public final class ProductResponseDescriptors {
    private ProductResponseDescriptors() {}

    public static List<FieldDescriptor> productSummaryFields() {
        return List.of(
            fieldWithPath("id").description("Mã sản phẩm"),
            fieldWithPath("name").description("Tên sản phẩm"),
            fieldWithPath("price").description("Giá bán")
        );
    }
}
```

Dùng trong operation:

```java
document("products-find",
    responseFields(ProductResponseDescriptors.productSummaryFields())
)
```

Mỗi lần gọi factory tạo danh sách và các FieldDescriptor mới. List.of(...) không cho thêm hoặc xóa phần tử, giúp bộ descriptor không bị chỉnh sửa cấu trúc ngoài ý muốn.

### Vì sao factory hữu ích hơn một instance static?

FieldDescriptor có các phương thức cấu hình như optional() và ignored(). Các phương thức này cấu hình chính descriptor được gọi. Nếu giữ một instance static rồi thay đổi trạng thái trong test, một operation có thể làm ảnh hưởng descriptor mà operation khác dùng.

Factory method tránh việc chia sẻ instance đã bị cấu hình theo ngữ cảnh. Đây là lựa chọn phù hợp khi một field bắt buộc trong response A nhưng có thể vắng trong response B.

## 4. Kết hợp field dùng chung với field riêng

Một endpoint có thể trả summary fields, endpoint khác trả thêm metadata hoặc thông tin liên quan. Hãy tạo danh sách mới rồi ghép field riêng:

```java
static List<FieldDescriptor> productDetailFields() {
    List<FieldDescriptor> fields =
        new ArrayList<>(ProductResponseDescriptors.productSummaryFields());

    fields.add(
        fieldWithPath("description")
            .description("Mô tả chi tiết sản phẩm")
    );
    fields.add(
        fieldWithPath("inventory.available")
            .description("Số lượng có thể bán")
    );
    return fields;
}
```

Dùng:

```java
document("products-detail",
    responseFields(productDetailFields())
)
```

Một endpoint khác có thể trả thêm trạng thái xuất bản:

```java
static List<FieldDescriptor> productAdminFields() {
    List<FieldDescriptor> fields =
        new ArrayList<>(ProductResponseDescriptors.productSummaryFields());
    fields.add(
        fieldWithPath("published")
            .description("Sản phẩm đã được công bố")
    );
    fields.add(
        fieldWithPath("createdAt")
            .description("Thời điểm tạo sản phẩm")
    );
    return fields;
}
```

Không gom mọi field của mọi response vào một bộ descriptor toàn cục. Khi đó mỗi operation phải mô tả field không thuộc response của nó, hoặc phải dùng ignored/relaxed quá rộng. Hãy tái sử dụng phần hợp đồng thật sự chung và giữ field đặc thù ở factory riêng.

## 5. Tái sử dụng nested object descriptors

Các response có thể chia sẻ object lồng nhau như địa chỉ, thông tin người tạo hoặc thông tin tiền tệ. Ví dụ:

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

Path descriptor cần chứa prefix để phân biệt vị trí:

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

static List<FieldDescriptor> checkoutResponseFields() {
    List<FieldDescriptor> fields = new ArrayList<>();
    fields.addAll(addressFields("shippingAddress", "địa chỉ giao hàng"));
    fields.addAll(addressFields("billingAddress", "địa chỉ thanh toán"));
    return fields;
}
```

Factory nhận prefix tái sử dụng cách mô tả nhưng sinh path riêng cho từng object. Nếu chỉ muốn xem subtree như một đơn vị, có thể dùng subsectionWithPath(...). Khi đã mô tả một subsection, tránh đồng thời liệt kê lặp lại toàn bộ field con trong cùng bảng nếu điều đó làm tài liệu dư thừa.

## 6. Tái sử dụng descriptor cho array và collection

Response collection thường có array:

```json
{
  "items": [
    {"id": 42, "name": "Keyboard", "price": 89.5},
    {"id": 43, "name": "Mouse", "price": 29.0}
  ],
  "totalElements": 2
}
```

Descriptor có thể mô tả field bên trong phần tử bằng wildcard path:

```java
static List<FieldDescriptor> productItemFields(String prefix) {
    return List.of(
        fieldWithPath(prefix + "id").description("Mã sản phẩm"),
        fieldWithPath(prefix + "name").description("Tên sản phẩm"),
        fieldWithPath(prefix + "price").description("Giá bán")
    );
}

static List<FieldDescriptor> productSearchResponseFields() {
    List<FieldDescriptor> fields = new ArrayList<>(
        productItemFields("items[].")
    );
    fields.add(
        fieldWithPath("totalElements")
            .description("Tổng số sản phẩm phù hợp")
    );
    return fields;
}
```

Với JSON path của Spring REST Docs, cú pháp wildcard [] biểu diễn phần tử array. Kiểm tra path thực tế và phiên bản REST Docs khi áp dụng cho nested array hoặc cấu trúc phức tạp. Descriptor phải khớp dữ liệu response mà test nhận được.

Một cách khác là dùng subsection descriptor cho array nếu tài liệu chỉ cần xác nhận phần tử tồn tại như một nhóm mà không cần bảng từng field. Chọn mức chi tiết phù hợp với người tích hợp API.

## 7. Tổ chức response envelope dùng chung

Nhiều API bọc dữ liệu trong một response envelope:

```json
{
  "data": {
    "id": 42,
    "name": "Keyboard"
  },
  "meta": {
    "requestId": "req-test-01"
  }
}
```

Nếu mọi endpoint đều dùng cùng cấu trúc data/meta, có thể tạo factory theo prefix:

```java
static List<FieldDescriptor> responseMetadataFields() {
    return List.of(
        fieldWithPath("meta.requestId")
            .description("Mã request để truy vết")
    );
}

static List<FieldDescriptor> productEnvelopeFields() {
    List<FieldDescriptor> fields = new ArrayList<>();
    fields.add(fieldWithPath("data.id").description("Mã sản phẩm"));
    fields.add(fieldWithPath("data.name").description("Tên sản phẩm"));
    fields.addAll(responseMetadataFields());
    return fields;
}
```

Nếu cấu trúc data thay đổi giữa endpoint, tách factory tương ứng. Không giả định mọi response đều có cùng payload chỉ vì cùng được bọc trong một envelope.

## 8. Ví dụ MockMvc dùng chung response descriptors

Giả sử hai endpoint trả một sản phẩm, nhưng endpoint detail có thêm description và inventory:

```java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping("/{id}")
    ProductDetail find(@PathVariable long id) {
        return new ProductDetail(
            id, "Mechanical Keyboard", 89.5,
            "Bàn phím cơ", 12
        );
    }

    @GetMapping("/{id}/summary")
    ProductSummary summary(@PathVariable long id) {
        return new ProductSummary(id, "Mechanical Keyboard", 89.5);
    }

    record ProductSummary(long id, String name, double price) {}
    record ProductDetail(
        long id, String name, double price,
        String description, int available
    ) {}
}
```

Test:

```java
@WebMvcTest(ProductController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductResponseDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void productSummary() throws Exception {
        mockMvc.perform(get("/api/products/{id}/summary", 42)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andDo(document("products-summary",
                responseFields(
                    ProductResponseDescriptors.productSummaryFields()
                )
            ));
    }

    @Test
    void productDetail() throws Exception {
        mockMvc.perform(get("/api/products/{id}", 42)
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andDo(document("products-detail",
                responseFields(productDetailFields())
            ));
    }
}
```

Hai operation tái sử dụng mô tả id, name và price; operation detail thêm description và available. Mỗi operation có ID riêng nên snippet response-fields.adoc được tạo trong folder riêng. Nếu server thêm field ngoài descriptor, strict validation sẽ báo lỗi để tài liệu được cập nhật.

## 9. Optional, ignored và relaxed response fields

Response có thể khác nhau theo trạng thái tài nguyên hoặc quyền của người dùng. Field có thể optional:

```java
fieldWithPath("publishedAt")
    .description("Thời điểm công bố")
    .optional()
```

Field nội bộ có thể được bỏ khỏi bảng:

```java
fieldWithPath("internalVersion")
    .ignored()
```

Các lựa chọn có ý nghĩa khác nhau:

| Cách dùng | Ý nghĩa |
| --- | --- |
| Descriptor mặc định | Field được mô tả và kiểm tra ở strict mode |
| optional() | Field có thể vắng mặt |
| ignored() | Field bị bỏ khỏi bảng và không được kiểm tra như field được mô tả |
| relaxedResponseFields(...) | Cho phép field khác tồn tại ngoài tập descriptor |

Không chia sẻ một FieldDescriptor instance giữa nhiều test nếu một test cần thay trạng thái optional/ignored. Hãy tạo descriptor mới trong factory để mỗi operation có cấu hình độc lập.

Relaxed mode hữu ích khi một response có nhiều field ngoài phạm vi tài liệu hiện tại hoặc khi tài liệu chỉ tập trung vào một phần payload. Tuy nhiên, nếu mọi response đều dùng relaxed mode, server có thể đổi hoặc thêm field mà test không nhắc nhóm cập nhật tài liệu.

## 10. Tách descriptor theo response variant

Một endpoint có thể trả nhiều dạng response theo trạng thái:

- Thành công: object đầy đủ.
- Không tìm thấy: problem detail.
- Không có nội dung: 204 No Content.
- Chưa xác thực hoặc không đủ quyền: response lỗi có cấu trúc riêng.

Không dùng một bộ response field descriptor cho các payload hoàn toàn khác nhau. Tạo operation ID riêng cho từng tình huống quan trọng và factory descriptor tương ứng:

```java
document("products-find-success",
    responseFields(productSummaryFields())
);

document("products-find-not-found",
    responseFields(problemDetailFields())
);
```

Nếu response 204 không có body, không gọi responseFields(...) chỉ để sinh bảng rỗng. Dùng HTTP response snippet và assertion status/header để ghi đúng hợp đồng.

## 11. Tổ chức helper class

Có thể đặt helper trong test source set:

```text
src/
  test/
    java/
      com/example/catalog/
        docs/
          ProductResponseDescriptors.java
          AddressResponseDescriptors.java
          ProblemResponseDescriptors.java
        ProductResponseDocumentationTest.java
```

Nguyên tắc:

- Chia helper theo resource hoặc nhóm response có cùng contract.
- Tên method diễn tả payload, ví dụ productSummaryFields() và productDetailFields().
- Factory trả về descriptor mới khi có khác biệt optional/ignored.
- Giữ field đặc thù trong helper riêng của response variant.
- Chỉ chia sẻ field có cùng path và ý nghĩa; không dùng chung chỉ vì tên field giống nhau.
- Không để helper tài liệu test phụ thuộc service/controller production.

Field status có thể mang ý nghĩa khác nhau giữa response domain và HTTP status code. Descriptor chỉ mô tả JSON path, vì vậy cần đặt description rõ để người đọc không nhầm field body với HTTP status.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Response field bị lặp | Ghép hai factory cùng tạo một path. | Kiểm tra path và xác định nguồn descriptor duy nhất. |
| Một test ảnh hưởng optional của test khác | Chia sẻ FieldDescriptor instance rồi cấu hình trạng thái. | Factory tạo instance mới theo operation. |
| Endpoint detail thiếu field descriptor | Chỉ dùng factory summary. | Ghép các field riêng của response detail. |
| Test báo field không được mô tả | Payload mới có field ngoài descriptor ở strict mode. | Cập nhật contract/descriptor hoặc dùng relaxed mode có giới hạn. |
| Test báo field bắt buộc vắng mặt | Descriptor không optional nhưng response không có field. | Sửa implementation hoặc đánh dấu optional nếu contract cho phép. |
| Nested path không khớp | Prefix hoặc JSON path sai. | Đối chiếu response body và dùng path đầy đủ. |
| Array descriptor không khớp | Dùng sai wildcard hoặc cấu trúc array lồng nhau. | Kiểm tra path notation và payload test thực tế. |
| Bảng quá dài hoặc trùng lặp | Mô tả mọi field của subtree trong khi chỉ cần tổng quan. | Dùng subsection descriptor hoặc tách trang/operation. |

## 13. Bài thực hành

Tạo API Catalog với ba response:

1. GET /api/products/{id}/summary trả id, name và price.
2. GET /api/products/{id} trả các field summary cùng description và inventory.available.
3. GET /api/products trả items array cùng totalElements.

Thực hiện:

1. Tạo ProductResponseDescriptors.productSummaryFields() trả descriptor mới.
2. Tạo productDetailFields() bằng cách ghép field summary với field detail.
3. Tạo factory nhận prefix để mô tả address lồng nhau ở shippingAddress và billingAddress.
4. Tạo descriptor cho items[] và totalElements của collection response.
5. Viết MockMvc test, dùng responseFields(...) với operation ID riêng.
6. Thử optional, ignored và relaxedResponseFields; ghi lại khác biệt strict validation.
7. Chạy clean test và Asciidoctor; so sánh response-fields.adoc giữa summary, detail và collection.

**Tiêu chí hoàn thành:** tái sử dụng được response descriptors mà không lặp mô tả; ghép đúng field riêng theo từng response; xử lý nested path và array; giữ optional/ignored độc lập; strict validation phát hiện thay đổi contract ngoài ý muốn.

## 14. Tài liệu tham khảo

- [Spring REST Docs — Request and Response Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/PayloadDocumentation.html)
- [Spring REST Docs — FieldDescriptor API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/FieldDescriptor.html)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
