# Giữ mô tả chung và mô tả riêng tách biệt

## 1. Vì sao cần tách phần chung và phần riêng?

Trong học phần **Spring REST Docs (SPRING_REST_DOCS)** thuộc chương **Tái sử dụng**, test HTTP tạo snippet từ request và response thực tế. Khi nhiều endpoint chia sẻ một phần contract, ta có thể tái sử dụng descriptor để giảm lặp. Tuy nhiên, nếu gom tất cả field, parameter, header hoặc link vào một helper chung, mô tả của endpoint này có thể bị áp nhầm sang endpoint khác.

Ví dụ Product và Order đều có field id, nhưng ý nghĩa và định dạng có thể khác. Hai endpoint đều có query parameter status, nhưng một bên lọc trạng thái sản phẩm, bên kia lọc trạng thái đơn hàng. Cùng có header Location, nhưng URI đích trỏ tới resource khác nhau.

Nguyên tắc:

- **Phần chung** chứa mô tả có cùng ý nghĩa, path/vị trí và quy tắc xuất hiện.
- **Phần riêng** chứa ngữ nghĩa hoặc hành vi chỉ thuộc một resource, endpoint hay response variant.
- **Composition** ghép hai phần thành bộ descriptor đúng với một operation cụ thể.

Mục tiêu không phải tối đa hóa lượng code dùng chung. Mục tiêu là tái sử dụng đúng phần contract thật sự chung mà vẫn giữ khả năng kiểm tra riêng cho từng endpoint.

Ví dụ dùng **Spring Boot 3.5, Spring REST Docs 3.x, JUnit Jupiter và MockMvc**. Cách tổ chức descriptor không phụ thuộc MockMvc; WebTestClient và REST Assured cũng có thể dùng các factory này.

## 2. Nhận diện ranh giới giữa chung và riêng

Trước khi tạo helper, so sánh các operation theo contract:

| Thành phần | Có thể dùng chung khi | Nên tách riêng khi |
| --- | --- | --- |
| JSON field | Cùng path, kiểu dữ liệu, ý nghĩa và quy tắc optional | Cùng tên nhưng khác ý nghĩa hoặc cấu trúc |
| Path parameter | Cùng tên và cùng ý nghĩa định danh | Cùng tên nhưng định danh resource khác |
| Query parameter | Cùng vị trí, ý nghĩa và quy tắc giá trị | Filter có semantics riêng theo resource |
| Header | Cùng header và cùng ý nghĩa với client | Cùng tên nhưng giá trị/ý nghĩa phụ thuộc endpoint |
| Hypermedia link | Cùng relation và cùng khả năng điều hướng | Relation riêng hoặc điều kiện xuất hiện khác |

Một quy tắc thực tế: nếu phải thêm nhiều điều kiện if, truyền nhiều cờ boolean hoặc sửa description theo endpoint sau khi gọi factory, abstraction có thể đang gom những contract khác nhau. Tách factory thường làm test dễ hiểu hơn.

## 3. Mô hình composition

Một operation có thể được tạo từ ba phần:

```text
Common contract fragments
          +
Resource-specific descriptors
          +
Operation-specific descriptors
          |
          v
   document(operationId, ...)
          |
          v
   generated snippets
```

Ví dụ:

- Common: pagination query page, size.
- Resource-specific: Product có query category; Order có query customerId.
- Operation-specific: endpoint export Product có query format; endpoint list Product không có.

Không đưa format vào factory dùng chung chỉ vì operation khác có cùng kiểu dữ liệu. Phạm vi factory phải phản ánh contract chứ không phản ánh sự tiện lợi khi ghép code.

## 4. Tách request field descriptors

Giả sử Product create và Product import đều nhận name, description, price. Import có thêm sourceSystem.

### Phần chung

```java
public final class ProductCommonFields {
    private ProductCommonFields() {}

    public static List<FieldDescriptor> createFields() {
        return List.of(
            fieldWithPath("name").description("Tên sản phẩm"),
            fieldWithPath("description").description("Mô tả sản phẩm"),
            fieldWithPath("price").description("Giá bán")
        );
    }
}
```

### Phần riêng và composition

```java
public final class ProductImportFields {
    private ProductImportFields() {}

    public static List<FieldDescriptor> requestFields() {
        List<FieldDescriptor> fields =
            new ArrayList<>(ProductCommonFields.createFields());
        fields.add(
            fieldWithPath("sourceSystem")
                .description("Hệ thống nguồn của bản ghi")
        );
        return fields;
    }
}
```

Operation create dùng phần chung:

```java
document("products-create",
    requestFields(ProductCommonFields.createFields())
)
```

Operation import ghép phần chung và riêng:

```java
document("products-import",
    requestFields(ProductImportFields.requestFields())
)
```

Field sourceSystem không bị yêu cầu trong request create và strict validation vẫn có thể phát hiện field mới chưa được mô tả trong từng payload.

## 5. Cùng tên field nhưng khác ngữ nghĩa

Không phải mọi field trùng tên đều nên dùng chung descriptor:

| Resource | Field | Ý nghĩa |
| --- | --- | --- |
| Product | status | Trạng thái kinh doanh: ACTIVE, DISCONTINUED |
| Order | status | Trạng thái xử lý: PENDING, PAID, SHIPPED |

Tách factory:

```java
static FieldDescriptor productStatusField() {
    return fieldWithPath("status")
        .description("Trạng thái kinh doanh của sản phẩm");
}

static FieldDescriptor orderStatusField() {
    return fieldWithPath("status")
        .description("Trạng thái xử lý đơn hàng");
}
```

Nếu chỉ dùng một commonStatusField() với mô tả “Trạng thái”, bảng tài liệu mất thông tin quan trọng cho client. Chỉ dùng chung khi ý nghĩa nghiệp vụ thật sự tương đồng, không chỉ vì JSON path giống nhau.

## 6. Tách parameter chung và parameter riêng

### Pagination dùng chung

```java
public final class CommonQueryParameters {
    private CommonQueryParameters() {}

    public static List<ParameterDescriptor> pagination() {
        return List.of(
            parameterWithName("page")
                .description("Số trang, bắt đầu từ 0"),
            parameterWithName("size")
                .description("Số phần tử trên mỗi trang")
        );
    }
}
```

### Bộ lọc riêng cho từng resource

```java
static List<ParameterDescriptor> productSearch() {
    List<ParameterDescriptor> parameters =
        new ArrayList<>(CommonQueryParameters.pagination());
    parameters.add(
        parameterWithName("category")
            .description("Danh mục sản phẩm")
    );
    parameters.add(
        parameterWithName("status")
            .description("Trạng thái kinh doanh của sản phẩm")
    );
    return parameters;
}

static List<ParameterDescriptor> orderSearch() {
    List<ParameterDescriptor> parameters =
        new ArrayList<>(CommonQueryParameters.pagination());
    parameters.add(
        parameterWithName("customerId")
            .description("Mã khách hàng")
    );
    parameters.add(
        parameterWithName("status")
            .description("Trạng thái xử lý đơn hàng")
    );
    return parameters;
}
```

Phần pagination được chia sẻ; filter vẫn thuộc Product hoặc Order. Hai descriptor status được tạo riêng vì semantics khác nhau.

## 7. Tách response headers chung và riêng

Một số response đều trả JSON, nên Content-Type có thể dùng chung:

```java
static HeaderDescriptor jsonContentType() {
    return headerWithName("Content-Type")
        .description("Media type của response body");
}
```

Nhưng Location cần mô tả theo resource:

```java
static List<HeaderDescriptor> productCreatedHeaders() {
    return List.of(
        jsonContentType(),
        headerWithName("Location")
            .description("URI của sản phẩm vừa được tạo")
    );
}

static List<HeaderDescriptor> orderCreatedHeaders() {
    return List.of(
        jsonContentType(),
        headerWithName("Location")
            .description("URI của đơn hàng vừa được tạo")
    );
}
```

Nếu mô tả Location chung chung là “URI tài nguyên mới”, mô tả đó có thể chấp nhận được, nhưng factory riêng thường giúp tài liệu rõ hơn khi resource có semantics hoặc quy tắc URI khác nhau.

## 8. Tách hypermedia links chung và riêng

HAL resource thường có self; Product có thêm orders, Order có thêm customer và cancel:

```java
static List<LinkDescriptor> commonResourceLinks() {
    return List.of(
        linkWithRel("self")
            .description("Liên kết tới tài nguyên hiện tại")
    );
}

static List<LinkDescriptor> productLinks() {
    List<LinkDescriptor> links =
        new ArrayList<>(commonResourceLinks());
    links.add(
        linkWithRel("orders")
            .description("Danh sách đơn hàng của sản phẩm")
    );
    return links;
}

static List<LinkDescriptor> orderLinks() {
    List<LinkDescriptor> links =
        new ArrayList<>(commonResourceLinks());
    links.add(
        linkWithRel("customer")
            .description("Khách hàng của đơn hàng")
    );
    links.add(
        linkWithRel("cancel")
            .description("Hủy đơn hàng nếu trạng thái cho phép")
    );
    return links;
}
```

Không đưa orders, customer và cancel vào danh sách chung. Một response chỉ nên được kiểm tra với relation mà contract của resource đó yêu cầu.

## 9. Optional, ignored và relaxed phải thuộc đúng phạm vi

Một field có thể bắt buộc ở POST nhưng optional ở PATCH. Một link next chỉ có ở collection. Một header có thể vắng trong response 204. Không thay đổi descriptor chung để xử lý các trường hợp này.

Tạo factory riêng:

```java
static FieldDescriptor requiredDescription() {
    return fieldWithPath("description")
        .description("Mô tả sản phẩm");
}

static FieldDescriptor optionalDescription() {
    return fieldWithPath("description")
        .description("Mô tả sản phẩm")
        .optional();
}

static LinkDescriptor optionalNextLink() {
    return linkWithRel("next")
        .description("Trang tiếp theo")
        .optional();
}
```

Ý nghĩa:

| Cấu hình | Cách dùng phù hợp |
| --- | --- |
| Mặc định | Contract yêu cầu thành phần có mặt và được mô tả |
| optional() | Thành phần được phép vắng mặt trong variant hợp lệ |
| ignored() | Thành phần không thuộc phạm vi snippet hiện tại |
| Relaxed descriptor | Operation chỉ mô tả một phần và chấp nhận thành phần khác |

Strict mode giúp phát hiện field, parameter, header hoặc link mới chưa được tài liệu hóa. Relaxed mode hữu ích khi một test có phạm vi hẹp, nhưng nếu dùng quá rộng thì contract drift có thể không được phát hiện.

## 10. Ví dụ composition trong MockMvc test

Một operation tạo Product có thể ghép request fields, response headers, response fields và links:

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
        requestFields(ProductCommonFields.createFields()),
        responseHeaders(ProductHeaderDescriptors.productCreatedHeaders()),
        responseFields(ProductResponseDescriptors.summaryFields()),
        links(ProductLinkDescriptors.productLinks())
    ));
```

Đây là ví dụ composition. Controller phải thực sự trả header và HAL links được mô tả; descriptor chỉ ghi nhận và kiểm tra response, không tự thêm header/link vào ứng dụng.

Một operation Order sẽ dùng các factory tương ứng của Order. Phần chung có thể dùng lại, nhưng relation và mô tả nghiệp vụ vẫn riêng.

## 11. Quy tắc đặt tên và tổ chức helper

Một cấu trúc dễ tìm:

```text
src/test/java/com/example/api/docs/
  common/
    CommonQueryParameters.java
    CommonHeaderDescriptors.java
    CommonLinkDescriptors.java
  product/
    ProductCommonFields.java
    ProductImportFields.java
    ProductHeaderDescriptors.java
    ProductLinkDescriptors.java
  order/
    OrderFieldDescriptors.java
    OrderParameterDescriptors.java
    OrderHeaderDescriptors.java
    OrderLinkDescriptors.java
```

Quy tắc:

- Tên class cho biết resource hoặc phạm vi contract.
- Tên method cho biết request/response và operation/variant.
- Chỉ chia sẻ descriptor có cùng path, vị trí, ý nghĩa và quy tắc xuất hiện.
- Factory tạo descriptor mới nếu trạng thái optional/ignored khác nhau.
- Phần riêng được ghép tại factory operation hoặc resource.
- Đặt helper trong test source; chỉ tạo test-fixture module nếu nhiều module thực sự cần chia sẻ.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Endpoint bị yêu cầu field không thuộc payload | Dùng factory chung quá rộng. | Tách field riêng và chỉ ghép phần contract thực sự chung. |
| Cùng tên field có mô tả sai | Chia sẻ theo tên thay vì semantics. | Tạo descriptor riêng theo resource. |
| Parameter status có mô tả nhập nhằng | Dùng chung factory cho Product và Order. | Tách filter factory theo domain. |
| Header Location mô tả sai resource | Dùng mô tả chung không đủ ngữ cảnh. | Tạo header factory riêng nếu semantics khác. |
| Response yêu cầu relation không thuộc resource | Dùng một danh sách links cho mọi operation. | Tách link factory theo resource. |
| Test khác bị ảnh hưởng optional | Chia sẻ instance descriptor đã cấu hình. | Factory trả instance mới theo operation. |
| Strict validation không phát hiện contract drift | Relaxed/ignored dùng quá rộng. | Thu hẹp relaxed và giữ strict ở operation chính. |
| Helper có nhiều cờ boolean | Một factory đang phục vụ nhiều contract khác nhau. | Tách thành các factory có tên và semantics rõ. |

## 13. Bài thực hành

Tạo API Catalog với Product và Order:

1. Cả hai có pagination query page và size.
2. Product có filter category và Product status; Order có customerId và Order status.
3. Cả hai response đều có JSON Content-Type; mỗi resource có mô tả Location riêng khi tạo mới.
4. HAL Product có self/orders; HAL Order có self/customer/cancel.

Thực hiện:

1. Tạo CommonQueryParameters cho pagination.
2. Tạo ProductSearchParameters và OrderSearchParameters, ghép pagination với filter riêng.
3. Tạo CommonHeaderDescriptors cho Content-Type và header factory riêng cho Product/Order Location.
4. Tạo common self link rồi ghép relation riêng cho Product và Order.
5. Viết MockMvc test, truyền đúng factory vào document(...) theo operation.
6. Tạo một field optional ở PATCH nhưng bắt buộc ở POST; xác nhận factory không chia sẻ trạng thái.
7. Cố ý thêm parameter hoặc relation chưa mô tả để kiểm tra strict validation.
8. Include snippet trong Asciidoctor, chạy clean test và dựng tài liệu.

**Tiêu chí hoàn thành:** phân biệt được contract chung và riêng; chia sẻ đúng phần có cùng semantics; ghép descriptor theo operation; quản lý optional/ignored/relaxed đúng phạm vi; giữ strict validation để phát hiện thay đổi API.

## 14. Tài liệu tham khảo

- [Spring REST Docs — Request and Response Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — Query Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/query-parameters.html)
- [Spring REST Docs — HTTP Headers](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-headers.html)
- [Spring REST Docs — Hypermedia](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/hypermedia.html)
- [Spring REST Docs API Documentation](https://docs.spring.io/spring-restdocs/docs/current/api/)
