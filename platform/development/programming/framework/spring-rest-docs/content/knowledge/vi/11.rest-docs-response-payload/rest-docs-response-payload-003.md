# Trường lồng nhau, mảng và phần tử lặp trong response payload

## 1. Mục tiêu bài học

Trong Spring REST Docs, một response JSON có thể chứa nhiều lớp object và mảng: thông tin khách hàng nằm trong đơn hàng, các kiện hàng nằm trong từng đợt giao, và mỗi kiện lại chứa các dòng sản phẩm. Để tài liệu API có thể kiểm chứng từ bài kiểm thử HTTP, cần mô tả đúng **đường dẫn đến từng trường** trong cấu trúc đó.

Bài học thuộc chương **Response payload** của module **SPRING_REST_DOCS**. Sau khi học, bạn sẽ:

- Viết `fieldWithPath(...)` cho object lồng nhau bằng dấu chấm.
- Viết đường dẫn đến các phần tử lặp trong mảng bằng `[]`, kể cả mảng lồng qua nhiều cấp.
- Phân biệt mảng gốc, mảng giá trị đơn giản, mảng object và object có khóa động.
- Dùng `responseFields(...)` để sinh bảng trường JSON từ kiểm thử MockMvc.
- Hiểu giới hạn của kiểm tra descriptor khi mảng rỗng, giá trị thiếu hoặc kiểu dữ liệu không đồng nhất.
- Tổ chức và tái sử dụng descriptor cho những cấu trúc lặp, rồi nhúng snippet vào Asciidoctor/Markdown trong quy trình build và CI.

Các khái niệm tương tự áp dụng khi dùng WebTestClient hoặc REST Assured; điểm khác biệt nằm ở cách cấu hình test và gắn lời gọi tạo tài liệu. Bài này dùng MockMvc để minh họa xuyên suốt.

## 2. Response có nhiều lớp lồng nhau

Giả sử endpoint `GET /api/orders/2048/shipping` trả response `200 OK`:

```json
{
  "orderId": "ORD-2048",
  "customer": {
    "id": 17,
    "contact": {
      "email": "lan@example.test"
    }
  },
  "shipments": [
    {
      "carrier": "FAST",
      "packages": [
        {
          "packageId": "PKG-1",
          "items": [
            {"sku": "A-01", "quantity": 2},
            {"sku": "A-02", "quantity": 1}
          ]
        },
        {
          "packageId": "PKG-2",
          "items": [
            {"sku": "A-03", "quantity": 4}
          ]
        }
      ]
    },
    {
      "carrier": "STANDARD",
      "packages": [
        {
          "packageId": "PKG-3",
          "items": [
            {"sku": "A-04", "quantity": 1}
          ]
        }
      ]
    }
  ],
  "labels": ["fragile", "priority"],
  "metadata": {
    "route.zone": "HCM"
  }
}
```

Có thể hình dung cây JSON như sau:

```text
response
├── orderId                             STRING
├── customer                            OBJECT
│   ├── id                              NUMBER
│   └── contact                         OBJECT
│       └── email                       STRING
├── shipments                           ARRAY
│   └── []                              OBJECT, lặp nhiều lần
│       ├── carrier                     STRING
│       └── packages                   ARRAY
│           └── []                      OBJECT, lặp nhiều lần
│               ├── packageId           STRING
│               └── items               ARRAY
│                   └── []              OBJECT, lặp nhiều lần
│                       ├── sku         STRING
│                       └── quantity    NUMBER
├── labels                              ARRAY các STRING
└── metadata                            OBJECT
    └── ['route.zone']                  STRING
```

Điểm then chốt: trong `shipments[].packages[].items[].sku` có **ba lần `[]`**, vì để đến `sku` phải đi qua ba mảng khác nhau. Mỗi `[]` biểu diễn việc đi vào các phần tử mảng ở cấp tương ứng.

## 3. Quy tắc viết đường dẫn JSON

`fieldWithPath("...")` của Spring REST Docs dùng cú pháp đường dẫn riêng cho JSON. Không đặt dấu `$` ở đầu như trong biểu thức `jsonPath("$.customer.id")` của MockMvc.

| Đối tượng cần mô tả | Đường dẫn `fieldWithPath` | Ý nghĩa |
| --- | --- | --- |
| Mã đơn hàng | `orderId` | Trường trực tiếp ở object gốc |
| Thông tin khách hàng | `customer` | Cả object `customer` |
| Email khách hàng | `customer.contact.email` | Đi qua hai object lồng nhau |
| Danh sách đợt giao | `shipments` | Mảng object |
| Đơn vị giao của từng đợt | `shipments[].carrier` | Trường trong các phần tử của `shipments` |
| Mảng kiện thuộc từng đợt | `shipments[].packages` | Mảng lồng trong object ở mảng ngoài |
| Mã của từng kiện | `shipments[].packages[].packageId` | Trường qua hai mảng |
| Mảng dòng hàng trong kiện | `shipments[].packages[].items` | Mảng ở cấp lồng thứ ba |
| Mã sản phẩm của từng dòng | `shipments[].packages[].items[].sku` | Trường qua ba mảng |
| Số lượng ở từng dòng | `shipments[].packages[].items[].quantity` | Trường qua ba mảng |
| Các nhãn phân loại | `labels` | Mô tả toàn bộ mảng chuỗi |
| Khóa chứa dấu chấm | `metadata['route.zone']` | Chỉ đúng khóa `route.zone`, không phải object `route` chứa `zone` |

### 3.1. Object lồng nhau: thêm dấu chấm cho mỗi cấp

```java
fieldWithPath("customer")
    .description("Thông tin khách hàng của đơn");

fieldWithPath("customer.id")
    .description("Mã định danh khách hàng");

fieldWithPath("customer.contact")
    .description("Thông tin liên lạc");

fieldWithPath("customer.contact.email")
    .description("Email liên hệ của khách hàng");
```

Đường dẫn `customer.contact.email` khác hoàn toàn một key cấp gốc tên `"customer.contact.email"`. Với key chứa dấu chấm ngay trong tên, phải dùng bracket notation:

```json
{
  "metadata": {
    "route.zone": "HCM"
  }
}
```

```java
fieldWithPath("metadata['route.zone']")
    .description("Mã khu vực tuyến giao");
```

Có thể kết hợp dot và bracket notation trong một đường dẫn. Ví dụ `metadata['route.zone']` trỏ tới object `metadata` rồi tới **một key** tên `route.zone`.

### 3.2. Mảng object: dùng `[]` cho các phần tử lặp

Với `shipments`, mỗi phần tử là object có `carrier` và `packages`:

```java
fieldWithPath("shipments")
    .description("Các đợt giao hàng của đơn");

fieldWithPath("shipments[].carrier")
    .description("Đơn vị vận chuyển của từng đợt giao");

fieldWithPath("shipments[].packages")
    .description("Các kiện hàng của từng đợt giao");
```

Không nên tài liệu hóa bằng `shipments[0].carrier` nếu hợp đồng API áp dụng cho **mọi đợt giao**, vì số phần tử có thể thay đổi. `[]` biểu diễn đường dẫn khái quát; chỉ số cụ thể chỉ phù hợp với trường hợp thực sự có ý nghĩa cố định theo vị trí.

### 3.3. Nhiều tầng mảng: đếm số lần phải đi qua mảng

Để mô tả mã hàng của từng dòng trong từng kiện thuộc từng đợt:

```java
fieldWithPath("shipments[].packages[].items[].sku")
    .description("Mã sản phẩm của dòng hàng trong kiện");

fieldWithPath("shipments[].packages[].items[].quantity")
    .description("Số lượng sản phẩm trong dòng hàng");
```

Đọc đường dẫn từ trái sang phải:

1. `shipments[]` — duyệt từng đợt giao.
2. `packages[]` — trong mỗi đợt, duyệt từng kiện.
3. `items[]` — trong mỗi kiện, duyệt từng dòng hàng.
4. `sku` hoặc `quantity` — trường cần mô tả ở mỗi dòng hàng.

Một lỗi điển hình là viết `shipments.packages.items.sku`; cách đó bỏ mất các cấp array và không khớp với cấu trúc response thực tế.

### 3.4. Mảng giá trị nguyên thủy và mảng tại gốc

Với `"labels": ["fragile", "priority"]`, có thể mô tả toàn bộ mảng:

```java
fieldWithPath("labels")
    .description("Các nhãn phân loại của đơn hàng");
```

Khi mô tả mảng giá trị đơn giản, phần `description` cần nói rõ kiểu và ý nghĩa của từng giá trị nếu người dùng API cần biết; danh sách các phần tử không có tên trường riêng như object.

Nếu response **gốc là mảng**:

```json
[
  {"eventId": "EV-1", "type": "PICKED_UP"},
  {"eventId": "EV-2", "type": "IN_TRANSIT"}
]
```

Các đường dẫn đúng là:

```java
responseFields(
    fieldWithPath("[]").description("Các sự kiện vận chuyển"),
    fieldWithPath("[].eventId").description("Mã sự kiện"),
    fieldWithPath("[].type").description("Loại sự kiện")
)
```

`[]` ở đầu nói rằng **chính root của response là một mảng**. Không thêm tiền tố `events` hoặc `data` nếu JSON không có các trường đó.

### 3.5. Khóa động: wildcard `*` khác với phần tử mảng `[]`

Một số API trả object được lập chỉ mục theo mã động, ví dụ:

```json
{
  "warehouses": {
    "HCM": {"available": 12},
    "HAN": {"available": 8}
  }
}
```

Tên `HCM` và `HAN` là **key của object**, không phải các phần tử array. Có thể dùng wildcard:

```java
responseFields(
    fieldWithPath("warehouses")
        .description("Số lượng theo kho"),
    fieldWithPath("warehouses.*.available")
        .description("Số lượng hàng sẵn có tại từng kho")
)
```

Dùng `*` khi phần tên key thay đổi, còn dùng `[]` khi dữ liệu thực sự là array JSON. `warehouses[].available` sai với ví dụ này vì `warehouses` là object. Không nên dùng wildcard tràn lan vì có thể làm bảng tài liệu khó biết được key hợp lệ; hãy mô tả thêm quy tắc tên key trong `description`.

## 4. Kiểm thử MockMvc sinh tài liệu cho mảng lồng nhiều tầng

Ví dụ đầy đủ dưới đây dùng JUnit Jupiter, Spring MVC, Spring REST Docs MockMvc và Jackson. Java 17+ được sử dụng cho `record`; controller mẫu tạo response ổn định để sinh snippet.

```java
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.junit.jupiter.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class NestedShippingResponseDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider documentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new ShippingController())
                .apply(documentationConfiguration(documentation))
                .build();
    }

    @Test
    void documentNestedShippingResponse() throws Exception {
        mockMvc.perform(get("/api/orders/{id}/shipping", 2048)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.orderId").value("ORD-2048"))
                .andExpect(jsonPath(
                        "$.shipments[0].packages[0].items[0].sku")
                        .value("A-01"))
                .andExpect(jsonPath(
                        "$.shipments[1].packages[0].items[0].quantity")
                        .value(1))
                .andDo(document("shipping-nested",
                        responseFields(
                                fieldWithPath("orderId")
                                        .description("Mã đơn hàng"),
                                fieldWithPath("customer")
                                        .description("Thông tin khách hàng"),
                                fieldWithPath("customer.id")
                                        .description("Mã khách hàng"),
                                fieldWithPath("customer.contact")
                                        .description("Thông tin liên lạc"),
                                fieldWithPath("customer.contact.email")
                                        .description("Email khách hàng"),
                                fieldWithPath("shipments")
                                        .description("Danh sách đợt giao"),
                                fieldWithPath("shipments[].carrier")
                                        .description("Đơn vị vận chuyển"),
                                fieldWithPath("shipments[].packages")
                                        .description("Các kiện trong đợt giao"),
                                fieldWithPath(
                                        "shipments[].packages[].packageId")
                                        .description("Mã kiện hàng"),
                                fieldWithPath(
                                        "shipments[].packages[].items")
                                        .description("Các dòng hàng trong kiện"),
                                fieldWithPath(
                                        "shipments[].packages[].items[].sku")
                                        .description("Mã sản phẩm trong kiện"),
                                fieldWithPath(
                                        "shipments[].packages[].items[].quantity")
                                        .description("Số lượng sản phẩm"),
                                fieldWithPath("labels")
                                        .description("Nhãn phân loại đơn hàng"),
                                fieldWithPath("metadata")
                                        .description("Metadata của response"),
                                fieldWithPath("metadata['route.zone']")
                                        .description("Mã khu vực tuyến giao")
                        )
                ));
    }

    @RestController
    static class ShippingController {

        @GetMapping(
                value = "/api/orders/{id}/shipping",
                produces = MediaType.APPLICATION_JSON_VALUE)
        ShippingResponse shipping(@PathVariable("id") long id) {
            return new ShippingResponse(
                    "ORD-" + id,
                    new Customer(17, new Contact("lan@example.test")),
                    List.of(
                            new Shipment("FAST", List.of(
                                    new ShippingPackage("PKG-1", List.of(
                                            new Item("A-01", 2),
                                            new Item("A-02", 1))),
                                    new ShippingPackage("PKG-2", List.of(
                                            new Item("A-03", 4))))),
                            new Shipment("STANDARD", List.of(
                                    new ShippingPackage("PKG-3", List.of(
                                            new Item("A-04", 1)))))),
                    List.of("fragile", "priority"),
                    Map.of("route.zone", "HCM")
            );
        }
    }

    record Contact(String email) {}
    record Customer(long id, Contact contact) {}
    record Item(String sku, int quantity) {}
    record ShippingPackage(String packageId, List<Item> items) {}
    record Shipment(String carrier, List<ShippingPackage> packages) {}
    record ShippingResponse(
            String orderId,
            Customer customer,
            List<Shipment> shipments,
            List<String> labels,
            Map<String, String> metadata) {}
}
```

Ý nghĩa của ba nhóm thao tác:

- `perform(get(...))` tạo HTTP request giả lập, controller và Jackson tạo response JSON.
- `andExpect(jsonPath(...))` kiểm tra **giá trị cụ thể** bằng cú pháp JSONPath, bao gồm chỉ số phần tử tại vị trí muốn xác nhận.
- `andDo(document("shipping-nested", responseFields(...)))` khai báo **hợp đồng trường**, kiểm tra các path và sinh `response-fields.adoc`.

Trong bảng sinh ra, `shipments` được mô tả như array, `shipments[].packages` cũng là array, trong khi `shipments[].packages[].items[].sku` là chuỗi và `...quantity` là số. Nội dung `description` nên phản ánh ý nghĩa của dữ liệu mà người tích hợp API cần biết.

**Phạm vi xác minh:** việc mô tả `shipments[].packages[].items[].sku` cho biết path này có trong payload thử nghiệm. Không nên coi đó là phép đảm bảo rằng *mọi* dòng hàng trong *mọi* response đều chứa `sku`. Đối với ràng buộc bắt buộc ở từng phần tử hoặc quy tắc nghiệp vụ phức tạp, hãy dùng assertion riêng hoặc schema validation phù hợp.

## 5. Phần tử lặp không có nghĩa là luôn có phần tử

Ba trường hợp có tác động khác nhau đến việc xác minh:

### 5.1. Mảng có phần tử đại diện

```json
{
  "shipments": [
    {
      "carrier": "FAST",
      "packages": [
        {
          "packageId": "PKG-1",
          "items": [{"sku": "A-01", "quantity": 2}]
        }
      ]
    }
  ]
}
```

Fixture này cho phép tìm các path sâu như `shipments[].packages[].items[].sku` và `...quantity`. Đây thường là fixture thích hợp cho **bài kiểm thử sinh tài liệu cấu trúc**.

### 5.2. Mảng rỗng

```json
{
  "shipments": []
}
```

`shipments` vẫn là một trường có thật, nhưng không có `shipments[].carrier` hoặc các trường con của `packages` để quan sát. Nếu khai báo các trường con là bắt buộc, bước sinh tài liệu có thể thất bại do không tìm thấy field.

Không nên sửa toàn bộ descriptor con thành `optional()` chỉ để làm fixture rỗng chạy qua nếu hợp đồng thực tế yêu cầu các trường đó **khi phần tử tồn tại**. Một cách có chủ đích hơn là dùng kiểm thử riêng cho trường hợp danh sách rỗng, trong khi test tạo tài liệu dùng fixture đủ cấu trúc đại diện.

### 5.3. Có mảng rỗng ở một nhánh nhưng nhánh khác có dữ liệu

```json
{
  "shipments": [
    {"carrier": "FAST", "packages": []},
    {
      "carrier": "STANDARD",
      "packages": [
        {"packageId": "PKG-3", "items": [{"sku": "A-04", "quantity": 1}]}
      ]
    }
  ]
}
```

Các path sâu vẫn có thể được tìm thấy ở đợt giao thứ hai. Tuy nhiên, đối chiếu descriptor của REST Docs không thay thế việc xác nhận quy tắc của **từng phần tử**: ví dụ mỗi shipment có được phép không có package không, item có bắt buộc quantity lớn hơn 0 không. Cần kiểm thử những ca này một cách tường minh.

## 6. Optional, null và kiểu dữ liệu ở cấu trúc lặp

Với một response mẫu:

```json
{
  "shipments": [
    {
      "carrier": "FAST",
      "packages": [
        {"packageId": "PKG-1", "note": null}
      ]
    }
  ]
}
```

Nếu `note` có thể không xuất hiện hoặc là chuỗi ở những response khác, có thể ghi:

```java
import org.springframework.restdocs.payload.JsonFieldType;

fieldWithPath("shipments[].packages[].note")
    .type(JsonFieldType.STRING)
    .optional()
    .description("Ghi chú tùy chọn của kiện, có thể vắng mặt hoặc null");
```

Trong ví dụ, `note` có giá trị `null` nhưng hợp đồng mong đợi chuỗi khi có nội dung. `type(JsonFieldType.STRING)` thể hiện kiểu dự kiến trong snippet; `optional()` cho phép path vắng mặt. Hai điều này không tương đương nhau.

Khi path lặp nhận giá trị với nhiều kiểu JSON trong cùng payload, Spring REST Docs có thể suy ra kiểu `VARIES`. Đây là tín hiệu cần xem lại hợp đồng: liệu trường có chủ đích cho phép nhiều kiểu hay fixture đang không nhất quán? Có thể chỉ định `type(...)` để trình bày kiểu kỳ vọng, nhưng vẫn nên kiểm tra riêng nếu cần bắt buộc mọi phần tử có kiểu xác định.

Cần phân biệt:

| Payload | Ý nghĩa |
| --- | --- |
| `{"note": "Giao trước 17h"}` | Field hiện diện và có kiểu chuỗi |
| `{"note": null}` | Field hiện diện, giá trị JSON là `null` |
| `{}` | Field không hiện diện |
| `{"packages": []}` | Mảng `packages` có mặt nhưng không có phần tử |
| `{"packages": null}` | Field `packages` hiện diện với giá trị `null`, không phải mảng |

Nếu hợp đồng có các quy tắc dạng “mảng luôn có ít nhất một phần tử”, “không phần tử nào được null” hoặc “mỗi package phải có packageId”, hãy bổ sung kiểm thử chuyên biệt. Descriptor trong ví dụ minh họa cấu trúc tài liệu, không bao phủ mọi ràng buộc đó.

## 7. Tái sử dụng descriptor cho các phần tử lặp

Khi một cấu trúc xuất hiện ở nhiều endpoint, không nên viết lại cùng mô tả cho mọi vị trí. Spring REST Docs hỗ trợ `andWithPrefix(...)` để ghép tiền tố đường dẫn vào một nhóm `FieldDescriptor`.

Ví dụ một dòng hàng luôn gồm `sku` và `quantity`:

```java
import org.springframework.restdocs.payload.FieldDescriptor;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

static FieldDescriptor[] itemFields() {
    return new FieldDescriptor[] {
            fieldWithPath("sku").description("Mã sản phẩm"),
            fieldWithPath("quantity").description("Số lượng sản phẩm")
    };
}
```

Nhóm này có thể được dùng ở endpoint trả **một dòng hàng**:

```java
responseFields(itemFields())
```

Hoặc dùng trong response vận chuyển lồng nhiều mảng:

```java
responseFields(
        fieldWithPath("orderId").description("Mã đơn hàng"),
        fieldWithPath("customer").description("Khách hàng"),
        fieldWithPath("shipments").description("Các đợt giao"),
        fieldWithPath("shipments[].packages")
                .description("Các kiện trong mỗi đợt"),
        fieldWithPath("shipments[].packages[].items")
                .description("Các dòng hàng trong từng kiện")
        // Thêm các descriptor khác của response tại đây
).andWithPrefix("shipments[].packages[].items[].", itemFields())
```

Hai descriptor mới có đường dẫn hoàn chỉnh:

- `shipments[].packages[].items[].sku`
- `shipments[].packages[].items[].quantity`

**Đoạn ghép tiền tố trên là minh họa cơ chế**, chưa phải toàn bộ danh sách descriptor cho response ở mục 2. Để sử dụng với chế độ nghiêm ngặt `responseFields(...)`, phải bổ sung đầy đủ các trường còn lại (`customer.id`, `shipments[].carrier`, `metadata['route.zone']`, v.v.) hoặc chủ động mô tả subsection.

Tương tự, có thể dùng:

```java
responseFields(
        fieldWithPath("[]").description("Các dòng hàng")
).andWithPrefix("[].", itemFields());
```

Cách này phù hợp nếu endpoint trả root array của các dòng hàng và mỗi phần tử đều có hai trường đã định nghĩa.

Lợi ích chính của `andWithPrefix(...)` là dùng **một bộ mô tả gốc** cho nhiều cấu trúc: đối tượng đơn lẻ, mảng gốc hoặc mảng lồng nhau. Khi ý nghĩa của `quantity` thay đổi, chỉ cần sửa descriptor gốc ở nơi quản lý chung.

## 8. Khi cấu trúc quá lớn: `subsectionWithPath` và `beneathPath`

Nếu một nhánh quá dài, có thể tách tài liệu thành hai mức.

### 8.1. Mô tả một nhánh ở mức tổng quan

`subsectionWithPath(...)` giúp mô tả cả nhánh cùng các trường con bằng một dòng:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

responseFields(
    fieldWithPath("orderId").description("Mã đơn hàng"),
    subsectionWithPath("customer").description("Thông tin khách hàng"),
    subsectionWithPath("shipments").description("Các đợt giao và kiện hàng"),
    fieldWithPath("labels").description("Nhãn đơn hàng"),
    subsectionWithPath("metadata").description("Metadata bổ trợ")
)
```

Khi khai báo `subsectionWithPath("shipments")`, Spring REST Docs coi các descendant dưới nhánh `shipments` là đã được tài liệu hóa trong phạm vi kiểm tra snippet đó. Điều này phù hợp cho bảng tổng quan; người đọc không nhìn thấy từng path sâu của kiện hàng trong bảng này. Nếu chi tiết đó là hợp đồng quan trọng, hãy tạo bảng con.

### 8.2. Sinh bảng riêng cho một subsection

`beneathPath(...)` cho phép tạo snippet chỉ mô tả field trong một object con. Ví dụ lấy phần `customer.contact`:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;

responseFields(
    beneathPath("customer.contact"),
    fieldWithPath("email")
        .description("Email khách hàng")
)
```

Ở đây `email` là path **tương đối** so với `customer.contact`. Spring REST Docs có thể sinh snippet riêng với tên dạng `response-fields-beneath-customer.contact.adoc`. Điều này thuận tiện để ghép bảng nhỏ vào một trang tài liệu chuyên biệt về dữ liệu khách hàng.

Việc dùng `subsectionWithPath` ở một snippet tổng quan không tự động sinh ra snippet mô tả chi tiết; cần lời gọi `document(...)` cùng `responseFields(beneathPath(...), ...)` riêng khi muốn có bảng chi tiết.

## 9. Lỗi thường gặp khi xử lý phần tử lặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `shipments.carrier` không tìm thấy | `shipments` là mảng object | Dùng `shipments[].carrier` |
| `shipments[].packages.packageId` không tìm thấy | `packages` cũng là mảng | Dùng `shipments[].packages[].packageId` |
| `shipments[].packages[].items.sku` không tìm thấy | Thiếu `[]` ở mảng `items` | Dùng `shipments[].packages[].items[].sku` |
| `metadata.route.zone` không khớp JSON | Key có tên nguyên văn `route.zone` | Dùng `metadata['route.zone']` |
| `warehouses[].available` không khớp | `warehouses` là object với khóa động | Cân nhắc `warehouses.*.available` |
| Descriptor con không tìm thấy khi mảng rỗng | Không có phần tử để quan sát trường con | Dùng fixture có dữ liệu đại diện cho test sinh tài liệu, test mảng rỗng riêng |
| Bảng trường không thể hiện chi tiết nhánh | Đang dùng `subsectionWithPath` cho cả nhánh | Thay bằng các `fieldWithPath` con hoặc tạo snippet con |
| Kiểm thử sinh tài liệu qua nhưng dữ liệu từng phần tử sai | Descriptor không thay thế assertion/schema validation cho từng phần tử | Viết assertion nghiệp vụ hay schema test chuyên biệt |
| `response-fields.adoc` không được tạo | Test chưa chạy hoặc cấu hình REST Docs chưa đúng | Kiểm tra cấu hình MockMvc, lời gọi `document` và thư mục snippet |

Đối với DTO Java, tên field trong tài liệu phải phản ánh **JSON sau serialization**. Các quy tắc `@JsonProperty`, naming strategy, bộ lọc trường và điều kiện `@JsonInclude` có thể làm tên trường hoặc sự hiện diện của trường khác đi so với record/class Java.

## 10. Đưa snippet vào tài liệu và CI

Khi bài kiểm thử `document("shipping-nested", ...)` chạy thành công, Spring REST Docs thường đặt các tệp trong thư mục generated snippets của Gradle:

```text
build/generated-snippets/
└── shipping-nested/
    ├── http-request.adoc
    ├── http-response.adoc
    └── response-fields.adoc
```

Danh sách minh họa các tệp liên quan; tùy cấu hình, còn có các snippet mặc định khác. Với Maven, đường dẫn phổ biến là `target/generated-snippets`. Có thể nhúng bảng trường trong Asciidoctor:

```adoc
= Shipping API
:snippets: build/generated-snippets

== Thông tin giao hàng của đơn

=== Ví dụ HTTP response
include::{snippets}/shipping-nested/http-response.adoc[]

=== Cấu trúc JSON response
include::{snippets}/shipping-nested/response-fields.adoc[]
```

Quy trình build/CI cần chạy bài kiểm thử sinh snippet trước khi chạy bước Asciidoctor/đóng gói tài liệu. Nếu thay đổi response làm kiểm thử tài liệu thất bại, pipeline phải dừng để nhóm phát triển cập nhật hợp đồng trước khi xuất bản. Tài liệu cuối có thể được chuyển đổi hoặc biên soạn sang Markdown bằng quy trình thích hợp; snippet mặc định ở đây vẫn là Asciidoctor.

## 11. Bài thực hành

Dùng response ở mục 2 làm đầu vào và triển khai các tình huống sau:

1. Thêm `shipments[].estimatedDate` (chuỗi ngày dự kiến). Bổ sung descriptor và assertion kiểm tra định dạng ngày khi cần.
2. Thêm object `shipments[].packages[].dimensions` với `length`, `width` và `height`. Viết tất cả đường dẫn con và mô tả đơn vị đo.
3. Thay mảng `items` trong một kiện bằng `[]`. Dự đoán descriptor sâu nào có thể không được tìm thấy, rồi kiểm thử một fixture có cấu trúc đại diện và một fixture rỗng.
4. Thêm `shipments[].packages[].note` có thể thiếu hoặc `null`. Quyết định dùng `optional()`, chỉ định kiểu và mô tả ngữ nghĩa của `null`.
5. Tạo endpoint trả root array của các dòng hàng. Tái sử dụng `itemFields()` bằng tiền tố `"[]."`.
6. Đổi `metadata` thành object chứa các khóa khu vực động như `"HCM"`, `"HAN"`. So sánh wildcard `*` với path cố định.
7. Tạo bảng tổng quan với `subsectionWithPath("shipments")`, sau đó tạo một snippet chi tiết cho nhánh nhỏ bằng `beneathPath(...)`.
8. Nhúng `response-fields.adoc` vào Asciidoctor và kiểm tra rằng sửa đổi của fixture được phản ánh trong tài liệu sau khi chạy lại pipeline.

**Tiêu chí hoàn thành:** bạn nhận diện được từng tầng object/mảng, viết đúng `[]` ở mỗi vị trí lặp, xử lý root array và key động, tái sử dụng descriptor có tiền tố, và phân biệt kiểm chứng cấu trúc tài liệu với kiểm tra nghiệp vụ từng phần tử. Nhờ đó, response payload phức tạp vẫn có thể được tài liệu hóa nhất quán từ kiểm thử HTTP trong Spring REST Docs.

### Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): cú pháp field path JSON, root array, wildcard, tái sử dụng descriptor, subsection và các ví dụ kiểm thử.
- [Spring REST Docs — PayloadDocumentation API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/payload/PayloadDocumentation.html): các API `fieldWithPath`, `responseFields`, `subsectionWithPath`, `beneathPath`.
