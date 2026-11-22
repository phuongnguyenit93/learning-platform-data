# Đặt factory cho bộ descriptor thường dùng

## 1. Mục tiêu của descriptor factory

Trong học phần **Spring REST Docs (SPRING_REST_DOCS)** thuộc chương **Tái sử dụng**, các bài kiểm thử HTTP vừa xác minh API vừa sinh snippet cho request, response và hypermedia. Khi số operation tăng, test có thể lặp lại mô tả về field, parameter, header và link. Nếu mỗi test tự tạo descriptor, nhóm dễ gặp các vấn đề:

- Cùng một field hoặc header có mô tả khác nhau ở các endpoint tương tự.
- Thay đổi contract phải sửa nhiều test.
- Descriptor dùng chung bị trộn với field đặc thù của operation.
- Trạng thái optional/ignored vô tình được chia sẻ giữa các test.
- Helper quá tổng quát khiến người đọc không biết descriptor phù hợp payload nào.

Factory là hàm tạo descriptor theo một hợp đồng cụ thể. Thay vì lưu một bảng mô tả tĩnh, ta tổ chức các factory nhỏ theo resource hoặc nhóm contract. Mỗi operation gọi factory cần thiết rồi kết hợp với descriptor riêng.

Spring REST Docs có descriptor cho nhiều phần của HTTP:

| Thành phần | API descriptor | Snippet |
| --- | --- | --- |
| JSON request fields | fieldWithPath(...), requestFields(...) | request-fields.adoc |
| JSON response fields | fieldWithPath(...), responseFields(...) | response-fields.adoc |
| Path parameters | parameterWithName(...), pathParameters(...) | path-parameters.adoc |
| Query parameters | parameterWithName(...), queryParameters(...) | query-parameters.adoc |
| Form parameters | parameterWithName(...), formParameters(...) | form-parameters.adoc |
| Request headers | headerWithName(...), requestHeaders(...) | request-headers.adoc |
| Response headers | headerWithName(...), responseHeaders(...) | response-headers.adoc |
| Hypermedia links | linkWithRel(...), links(...) | links.adoc |

Mục tiêu của factory catalog không phải gom mọi descriptor vào một danh sách lớn. Mục tiêu là cung cấp các khối nhỏ, có tên rõ, tạo đúng descriptor cho một phần hợp đồng và có thể ghép theo operation.

Ví dụ dùng **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter và MockMvc**. Factory descriptor không phụ thuộc MockMvc; WebTestClient và REST Assured cũng có thể dùng lại.

## 2. Nguyên tắc thiết kế

### Nhóm theo resource và contract

Nên nhóm helper theo resource hoặc phần hợp đồng có ý nghĩa chung:

```text
src/test/java/com/example/catalog/docs/
  common/
    CommonPaginationDescriptors.java
    CommonHeaderDescriptors.java
    CommonLinkDescriptors.java
  product/
    ProductFieldDescriptors.java
    ProductParameterDescriptors.java
    ProductHeaderDescriptors.java
    ProductLinkDescriptors.java
  order/
    OrderFieldDescriptors.java
    OrderParameterDescriptors.java
    OrderLinkDescriptors.java
```

Không cần tạo class cho mỗi descriptor. Nhóm các factory có cùng phạm vi và khả năng được dùng chung.

### Tên factory phải nói rõ nó tạo gì

Tên như fields() hoặc common() không cho biết danh sách phù hợp operation nào. Ưu tiên tên mô tả payload hoặc contract:

```java
productCreateRequestFields()
productSummaryResponseFields()
productSearchQueryParameters()
productResponseHeaders()
productHypermediaLinks()
```

Khi đọc test, tên factory nên giúp reviewer hiểu nhóm descriptor được áp dụng.

### Chia sẻ theo ý nghĩa, không chỉ theo tên

Hai field cùng tên không nhất thiết có cùng nghĩa. Ví dụ status trong Product là trạng thái kinh doanh; status trong Order là trạng thái xử lý đơn. Không dùng chung description chỉ vì path giống nhau.

Tương tự, header Location ở endpoint tạo sản phẩm trỏ tới product resource, còn ở endpoint tạo order trỏ tới order resource. Có thể chia sẻ cách tạo descriptor nếu description đủ trung tính, hoặc dùng factory riêng để mô tả ngữ cảnh.

### Tạo instance mới khi trạng thái có thể thay đổi

Descriptor có các phương thức cấu hình như optional() và ignored(). Nếu một operation cần field bắt buộc nhưng operation khác cho phép vắng mặt, factory nên tạo descriptor mới cho từng trường hợp. Tránh giữ một instance static rồi thay đổi nó theo test.

## 3. Factory cho request và response fields

Tạo class hỗ trợ Product:

```java
package com.example.catalog.docs;

import java.util.ArrayList;
import java.util.List;
import org.springframework.restdocs.payload.FieldDescriptor;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

public final class ProductFieldDescriptors {
    private ProductFieldDescriptors() {}

    public static List<FieldDescriptor> productCreateRequestFields() {
        return List.of(
            fieldWithPath("name").description("Tên sản phẩm"),
            fieldWithPath("description").description("Mô tả sản phẩm"),
            fieldWithPath("price").description("Giá bán")
        );
    }

    public static List<FieldDescriptor> productSummaryResponseFields() {
        return List.of(
            fieldWithPath("id").description("Mã sản phẩm"),
            fieldWithPath("name").description("Tên sản phẩm"),
            fieldWithPath("price").description("Giá bán")
        );
    }

    public static List<FieldDescriptor> productDetailResponseFields() {
        List<FieldDescriptor> fields =
            new ArrayList<>(productSummaryResponseFields());
        fields.add(fieldWithPath("description")
            .description("Mô tả chi tiết sản phẩm"));
        fields.add(fieldWithPath("inventory.available")
            .description("Số lượng có thể bán"));
        return fields;
    }
}
```

Request và response có factory riêng vì dù cùng có field name và price, chúng là hai contract khác nhau. Summary và detail response chia sẻ một phần cấu trúc; detail factory tạo list mới rồi thêm field riêng.

Sử dụng:

```java
document("products-create",
    requestFields(ProductFieldDescriptors.productCreateRequestFields())
);

document("products-summary",
    responseFields(ProductFieldDescriptors.productSummaryResponseFields())
);

document("products-detail",
    responseFields(ProductFieldDescriptors.productDetailResponseFields())
);
```

## 4. Factory cho parameter và header

### Query parameter phân trang

```java
public final class CommonPaginationDescriptors {
    private CommonPaginationDescriptors() {}

    public static List<ParameterDescriptor> queryParameters() {
        return List.of(
            parameterWithName("page")
                .description("Số trang, bắt đầu từ 0"),
            parameterWithName("size")
                .description("Số phần tử trên mỗi trang")
        );
    }
}
```

Endpoint Product ghép thêm category:

```java
static List<ParameterDescriptor> productSearchParameters() {
    List<ParameterDescriptor> parameters =
        new ArrayList<>(CommonPaginationDescriptors.queryParameters());
    parameters.add(parameterWithName("category")
        .description("Danh mục sản phẩm"));
    return parameters;
}
```

Endpoint Order có thể ghép customerId và status. Mặc dù hai endpoint cùng có status, mô tả phải theo đúng domain:

```java
static List<ParameterDescriptor> orderSearchParameters() {
    List<ParameterDescriptor> parameters =
        new ArrayList<>(CommonPaginationDescriptors.queryParameters());
    parameters.add(parameterWithName("customerId")
        .description("Mã khách hàng"));
    parameters.add(parameterWithName("status")
        .description("Trạng thái đơn hàng"));
    return parameters;
}
```

Dùng factory với queryParameters(...). Không tái sử dụng cùng factory cho path/form nếu vị trí và ngữ nghĩa parameter khác nhau.

### Response header

Nếu nhiều endpoint trả JSON, có thể tạo descriptor Content-Type dùng chung:

```java
public final class CommonHeaderDescriptors {
    private CommonHeaderDescriptors() {}

    public static HeaderDescriptor jsonContentType() {
        return headerWithName("Content-Type")
            .description("Media type của response body");
    }
}
```

Endpoint tạo resource thêm Location:

```java
static List<HeaderDescriptor> productCreateResponseHeaders() {
    return List.of(
        CommonHeaderDescriptors.jsonContentType(),
        headerWithName("Location")
            .description("URI của sản phẩm vừa được tạo")
    );
}
```

Nếu cùng header có mô tả khác theo ngữ cảnh, tạo factory theo resource. Nếu header có thể vắng ở một response variant, tạo factory riêng với optional() thay vì thay đổi descriptor dùng chung.

## 5. Factory cho hypermedia links

Nhiều tài nguyên HAL có relation self và profile:

```java
public final class CommonLinkDescriptors {
    private CommonLinkDescriptors() {}

    public static List<LinkDescriptor> resourceLinks() {
        return List.of(
            linkWithRel("self")
                .description("Liên kết tới tài nguyên hiện tại"),
            linkWithRel("profile")
                .description("Mô tả cấu trúc tài nguyên")
        );
    }
}
```

Product bổ sung orders:

```java
static List<LinkDescriptor> productLinks() {
    List<LinkDescriptor> links =
        new ArrayList<>(CommonLinkDescriptors.resourceLinks());
    links.add(linkWithRel("orders")
        .description("Danh sách đơn hàng của sản phẩm"));
    return links;
}
```

Collection có relation phân trang:

```java
static List<LinkDescriptor> productCollectionLinks() {
    return List.of(
        linkWithRel("self").description("Collection hiện tại"),
        linkWithRel("next").description("Trang tiếp theo").optional(),
        linkWithRel("prev").description("Trang trước").optional()
    );
}
```

Không dùng một bộ link cho mọi response. next có thể optional trong collection nhưng không có ý nghĩa ở resource detail. Factory riêng thể hiện đúng contract của từng representation.

## 6. Ghép factory trong operation documentation

Một operation có thể sử dụng nhiều nhóm descriptor cùng lúc:

```java
mockMvc.perform(
        post("/api/products")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Keyboard",
                  "description": "Mechanical keyboard",
                  "price": 89.5
                }
                """)
    )
    .andExpect(status().isCreated())
    .andDo(document("products-create",
        requestFields(ProductFieldDescriptors.productCreateRequestFields()),
        responseHeaders(ProductHeaderDescriptors.createResponseHeaders()),
        responseFields(ProductFieldDescriptors.productSummaryResponseFields()),
        links(ProductLinkDescriptors.productLinks())
    ));
```

Đây là cách ghép các nhóm descriptor. Trong test thực tế, response phải có các header và hypermedia relation được mô tả; truyền descriptor không tự tạo header hoặc link trong ứng dụng.

Đặt operation ID ổn định và dùng ID đó trong Asciidoctor include. Khi contract thay đổi, test sẽ báo lỗi ở phần descriptor tương ứng.

## 7. Thiết kế factory có thể mở rộng

### Trả về List hay varargs?

Factory trả List thuận tiện khi cần ghép các nhóm:

```java
List<FieldDescriptor> fields = new ArrayList<>(commonFields());
fields.addAll(endpointSpecificFields());
```

Varargs phù hợp với nhóm cố định nhỏ và điểm gọi ngắn. Khi cần kết hợp nhiều nhóm, List thể hiện rõ thứ tự và phạm vi. Dùng overload mà phiên bản Spring REST Docs hỗ trợ; nếu API nhận varargs, chuyển list thành mảng descriptor đúng kiểu.

### Dùng prefix khi cấu trúc giống nhau

Địa chỉ giao hàng và thanh toán có cùng field nhưng path khác:

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
```

Factory nhận prefix chỉ nên dùng khi schema thật sự giống nhau. Nếu một địa chỉ có field hoặc quy tắc khác, tách factory riêng để không che sự khác biệt contract.

### Không biến factory thành framework

Tránh xây dựng DSL tổng quát hoặc reflection registry chỉ để tạo một vài descriptor. Một factory Java nhỏ, tên rõ và trả list mới thường dễ đọc hơn. Chỉ nâng cấp cấu trúc khi nhiều test/module thật sự chia sẻ cùng contract và có chi phí bảo trì rõ ràng.

## 8. Strict, optional, ignored và relaxed

Factory cần bảo toàn ý nghĩa kiểm tra của REST Docs:

| Cấu hình | Tác dụng |
| --- | --- |
| Descriptor mặc định | Field/parameter/header/link được mô tả và kiểm tra |
| optional() | Thành phần có thể vắng mặt |
| ignored() | Thành phần bị loại khỏi bảng và kiểm tra descriptor thông thường |
| relaxed descriptor | Cho phép thành phần ngoài danh sách mô tả xuất hiện |

Không tạo factory chung tên allFields() rồi đánh dấu phần lớn field ignored để tái sử dụng cho nhiều payload. Cách này làm strict validation mất khả năng phát hiện contract drift.

Nếu description bắt buộc ở POST nhưng optional ở PATCH, hãy có hai factory. Nếu link next chỉ có ở collection, đặt optional ở collection factory thay vì factory resource chung. Nếu response header có thể vắng ở một variant, tạo factory header cho variant đó.

## 9. Tổ chức package và kiểm soát phạm vi

Đặt helper trong test source set:

```text
src/test/java/com/example/catalog/docs/
  common/
    CommonPaginationDescriptors.java
    CommonHeaderDescriptors.java
    CommonLinkDescriptors.java
  product/
    ProductFieldDescriptors.java
    ProductParameterDescriptors.java
    ProductHeaderDescriptors.java
    ProductLinkDescriptors.java
  order/
    OrderFieldDescriptors.java
    OrderParameterDescriptors.java
    OrderLinkDescriptors.java
```

Descriptor phục vụ kiểm thử và tài liệu nên nằm trong test source. Không để production code phụ thuộc Spring REST Docs nếu ứng dụng runtime không cần. Nếu nhiều module cần dùng chung, cân nhắc test-fixture module và chỉ export factory có contract ổn định.

## 10. Ví dụ MockMvc sử dụng factory catalog

Một test tìm kiếm có thể kết hợp factory:

```java
@WebMvcTest(ProductController.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class ProductDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void searchProducts() throws Exception {
        mockMvc.perform(
                get("/api/products")
                    .queryParam("page", "0")
                    .queryParam("size", "20")
                    .queryParam("category", "keyboard")
                    .accept(MediaType.APPLICATION_JSON)
            )
            .andExpect(status().isOk())
            .andDo(document("products-search",
                queryParameters(
                    ProductParameterDescriptors.productSearchParameters()
                ),
                responseFields(
                    ProductFieldDescriptors.productSearchResponseFields()
                )
            ));
    }
}
```

Khi cần mô tả request headers, response headers hoặc links, thêm factory tương ứng vào document(...). Không include snippet mà operation không tạo.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Một field có description khác nhau giữa endpoint tương tự | Test tự khai báo descriptor ở nhiều nơi. | Tạo factory chung khi ngữ nghĩa thực sự giống nhau. |
| Descriptor chung yêu cầu field không tồn tại | Dùng bộ descriptor quá rộng cho payload khác nhau. | Chia factory theo request/response shape. |
| Test khác bị ảnh hưởng optional/ignored | Chia sẻ instance descriptor đã cấu hình. | Factory tạo descriptor mới theo operation. |
| Danh sách ghép bị trùng path/relation | Common và endpoint factory cùng thêm một thành phần. | Chỉ định rõ phần sở hữu và kiểm tra danh sách ghép. |
| Mô tả sai ý nghĩa parameter/header | Chia sẻ theo tên mà không xét ngữ cảnh. | Tách factory theo resource hoặc contract. |
| Strict validation không phát hiện field mới | Dùng relaxed/ignored quá rộng. | Thu hẹp relaxed và giữ strict cho operation đại diện contract đầy đủ. |
| Helper khó tìm | Gom mọi descriptor vào một lớp khổng lồ. | Chia theo resource và nhóm contract. |
| Test phụ thuộc production module | Đặt helper REST Docs trong main source set. | Chuyển helper vào test source hoặc test-fixture module. |

## 12. Bài thực hành

Tạo API Catalog có operation tạo sản phẩm, tìm sản phẩm và tìm đơn hàng.

1. Tạo ProductFieldDescriptors cho request create, response summary và response detail.
2. Tạo CommonPaginationDescriptors và ghép vào ProductParameterDescriptors cùng OrderParameterDescriptors.
3. Tạo CommonHeaderDescriptors cho JSON Content-Type; tạo header factory riêng cho response tạo sản phẩm có Location.
4. Tạo CommonLinkDescriptors cho self/profile; ghép relation riêng cho product và order.
5. Viết MockMvc test dùng factory catalog trong document(...).
6. Tạo field optional ở PATCH nhưng bắt buộc ở POST; xác nhận hai factory không chia sẻ trạng thái.
7. Cố ý thêm field hoặc relation chưa mô tả để quan sát strict validation.
8. Include snippet được sinh vào Asciidoctor và chạy clean test asciidoctor.

**Tiêu chí hoàn thành:** biết phân nhóm descriptor theo resource/contract; đặt tên factory rõ; ghép nhóm chung với phần riêng; không chia sẻ trạng thái descriptor ngoài ý muốn; giữ strict validation và tạo snippet có thể include vào tài liệu.

## 13. Tài liệu tham khảo

- [Spring REST Docs — Request and Response Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html)
- [Spring REST Docs — Hypermedia](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/hypermedia.html)
- [Spring REST Docs API Documentation](https://docs.spring.io/spring-restdocs/docs/current/api/)
