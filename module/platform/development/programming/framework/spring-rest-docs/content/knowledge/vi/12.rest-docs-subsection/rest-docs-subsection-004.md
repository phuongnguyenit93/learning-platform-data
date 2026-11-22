# subsectionWithPath cho danh sách hoặc cấu trúc lồng nhau trong Spring REST Docs

## 1. Mục tiêu và tình huống sử dụng

**Spring REST Docs** tạo tài liệu API từ các bài kiểm thử HTTP thực thi bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**. Khi kiểm thử thành công, thư viện sinh snippet mô tả HTTP request, response, payload, header và tham số. Nhóm phát triển biên soạn các snippet này vào tài liệu **Asciidoctor/Markdown** và tích hợp bước sinh tài liệu vào build, CI.

Bài thuộc chương **Subsection**, tập trung vào **`subsectionWithPath(...)` cho danh sách hoặc cấu trúc JSON lồng nhau**. Khi API trả một mảng gồm nhiều object, mỗi object lại chứa object con, tài liệu dạng bảng phẳng có thể trở nên dài và khó đọc. `subsectionWithPath(...)` giúp mô tả một nhánh như một đơn vị nghiệp vụ mà vẫn giữ tính kiểm chứng đối với các phần khác của payload.

Ví dụ, endpoint đơn hàng trả `items` là danh sách các dòng hàng, mỗi dòng hàng có `pricing` và `options`. Tài liệu tổng quan chỉ cần một hàng cho `items`. Tài liệu tích hợp chuyên sâu có thể đi sâu tới `items[].pricing` hoặc từng field `items[].sku`.

Sau bài học, bạn có thể:

- Dùng `subsectionWithPath("items")` để mô tả toàn bộ mảng và các phần tử bên trong.
- Dùng `subsectionWithPath("items[].pricing")` để mô tả object con lặp lại trong từng phần tử của mảng.
- Phân biệt `subsectionWithPath(...)`, `fieldWithPath(...)` và `beneathPath(...)`.
- Hiểu vì sao kiểm thử payload *strict* có thể vẫn thành công khi phần tử trong subsection thay đổi.
- Thiết kế bảng tổng quan và bảng chi tiết cho cùng endpoint, sinh các snippet có tên rõ ràng và đưa vào tài liệu Asciidoctor/CI.

## 2. Payload mẫu: mảng object và nhiều cấp lồng nhau

Giả sử `GET /orders/ord-204` trả về:

```json
{
  "id": "ord-204",
  "items": [
    {
      "sku": "BOOK-01",
      "quantity": 2,
      "pricing": {
        "unitAmount": 120000,
        "currency": "VND"
      },
      "options": {
        "giftWrapped": true,
        "note": "Giao buổi sáng"
      }
    },
    {
      "sku": "PEN-02",
      "quantity": 1,
      "pricing": {
        "unitAmount": 30000,
        "currency": "VND"
      },
      "options": {
        "giftWrapped": false,
        "note": ""
      }
    }
  ],
  "delivery": {
    "address": {
      "city": "Ho Chi Minh City",
      "country": "VN"
    },
    "contact": {
      "name": "Lan",
      "phone": "0900000000"
    }
  },
  "total": {
    "amount": 270000,
    "currency": "VND"
  }
}
```

Nhìn dưới dạng cây:

```text
response
├── id
├── items                       (mảng)
│   ├── [0]                     (object)
│   │   ├── sku
│   │   ├── quantity
│   │   ├── pricing             (object)
│   │   │   ├── unitAmount
│   │   │   └── currency
│   │   └── options             (object)
│   │       ├── giftWrapped
│   │       └── note
│   └── [1]                     (cấu trúc tương tự)
├── delivery                    (object)
│   ├── address
│   │   ├── city
│   │   └── country
│   └── contact
│       ├── name
│       └── phone
└── total
    ├── amount
    └── currency
```

Có hai cấp độ mô tả tài liệu có ý nghĩa:

- **Tổng quan:** `id`, `items`, `delivery`, `total`. Phần tử mảng và object con được gom vào các subsection.
- **Chi tiết có chọn lọc:** nêu `items[].sku` và `items[].quantity`, nhưng vẫn gom `items[].pricing` và `items[].options` thành các subsection; với `delivery` thì có thể document từng field hoặc gom một nhánh nhỏ.

Ký hiệu `[]` trong path JSON của Spring REST Docs chỉ các phần tử của mảng. `items[].pricing` biểu thị object `pricing` có trong từng item, còn `items[0].pricing` chỉ một phần tử cụ thể và thường không thích hợp làm hợp đồng tổng quát cho danh sách nhiều phần tử.

## 3. subsectionWithPath hoạt động như thế nào?

Hai đoạn sau mô tả cùng một payload nhưng đặt **ranh giới kiểm tra** khác nhau.

### 3.1. Một descriptor cho toàn bộ danh sách

```java
responseFields(
    fieldWithPath("id")
        .description("Mã đơn hàng"),
    subsectionWithPath("items")
        .description("Danh sách dòng hàng trong đơn"),
    subsectionWithPath("delivery")
        .description("Thông tin giao hàng"),
    subsectionWithPath("total")
        .description("Tổng giá trị đơn hàng")
)
```

`subsectionWithPath("items")` là một **field descriptor**. Trong snippet `responseFields` hiện tại, nó mô tả nhánh `items` và coi các hậu duệ như `items[].sku`, `items[].quantity`, `items[].pricing.unitAmount` đã nằm trong phần được document. Vì thế bảng tổng quan không cần liệt kê từng field con.

Điều này **không có nghĩa** mọi field con của `items` đã được kiểm tra theo schema chi tiết. Nếu một item bất ngờ có field `discountCode`, bảng tổng quan vẫn có thể pass vì `items` bao phủ cả nhánh. Nếu API thêm field `createdAt` tại **root**, bảng tổng quan strict sẽ báo thiếu descriptor cho field mới.

### 3.2. Descriptor cho object con trong mỗi phần tử

```java
responseFields(
    fieldWithPath("id")
        .description("Mã đơn hàng"),
    fieldWithPath("items[].sku")
        .description("Mã sản phẩm"),
    fieldWithPath("items[].quantity")
        .description("Số lượng đặt mua"),
    subsectionWithPath("items[].pricing")
        .description("Thông tin giá của từng dòng hàng"),
    subsectionWithPath("items[].options")
        .description("Các tùy chọn cho dòng hàng"),
    subsectionWithPath("delivery")
        .description("Thông tin giao hàng"),
    subsectionWithPath("total")
        .description("Tổng giá trị đơn hàng")
)
```

Với bảng này, các field `sku` và `quantity` của item được document riêng; `pricing` và `options` được document theo subsection. Phạm vi bao phủ của `subsectionWithPath("items[].pricing")` chỉ là nhánh `pricing` ở những phần tử của `items`, **không bao phủ** `items[].sku`, `items[].quantity` hoặc `items[].options`.

Hai cách không nên được áp dụng lẫn lộn trong cùng một snippet nếu mục đích là kiểm soát field con. Chẳng hạn, khai báo thêm `fieldWithPath("items[].sku")` bên cạnh `subsectionWithPath("items")` không giúp bảo đảm mọi phần tử đều có SKU; cần một bảng kiểm tra chi tiết có phạm vi rõ ràng và các assertion nghiệp vụ tương ứng.

### 3.3. Phân biệt ba API

| API | Vai trò | Có bao phủ các field hậu duệ? | Sinh snippet phần body riêng? |
| --- | --- | --- | --- |
| `fieldWithPath("items[].sku")` | Mô tả field cụ thể theo path | Không bao phủ toàn bộ object/mảng anh em | Không |
| `subsectionWithPath("items")` | Mô tả toàn bộ nhánh danh sách trong bảng field | Có, trong phạm vi snippet hiện tại | Không |
| `subsectionWithPath("items[].pricing")` | Mô tả nhánh `pricing` của các item | Có, trong phạm vi từng nhánh được chọn | Không |
| `beneathPath("delivery")` | Trích subtree để tạo snippet riêng | Không phải field descriptor | Có, khi kết hợp `responseBody(...)` |

`subsectionWithPath(...)` dùng trong `requestFields(...)` hoặc `responseFields(...)`. Muốn hiển thị **đoạn JSON** của một nhánh, hãy dùng `requestBody(beneathPath(...))` hoặc `responseBody(beneathPath(...))`. Muốn mô tả **từng field** trong nhánh, kết hợp `beneathPath(...)` với `requestFields(...)` hoặc `responseFields(...)`.

## 4. Ví dụ kiểm thử MockMvc sinh snippet

Ví dụ sau dùng **JUnit 5**, **MockMvc**, **Spring MVC** và **Spring REST Docs**, dành cho **Java 17+**. Test và controller mẫu được đặt trong cùng file để có thể đọc độc lập. Controller trả JSON cố định; ở dự án thật, thay bằng controller của ứng dụng và fixture test ổn định.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseBody;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class OrderItemsDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders
                .standaloneSetup(new SampleOrderController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentOrderOverview() throws Exception {
        mockMvc.perform(get("/orders/{id}", "ord-204")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].sku").value("BOOK-01"))
                .andExpect(jsonPath("$.items[1].quantity").value(1))
                .andDo(document("orders-items-overview",
                        responseFields(
                                fieldWithPath("id")
                                        .description("Mã đơn hàng"),
                                subsectionWithPath("items")
                                        .description("Danh sách dòng hàng"),
                                subsectionWithPath("delivery")
                                        .description("Thông tin giao hàng"),
                                subsectionWithPath("total")
                                        .description("Tổng giá trị đơn hàng")
                        ),
                        responseBody(beneathPath("delivery")
                                .withSubsectionId("delivery"))
                ));
    }

    @Test
    void documentSelectedFieldsInsideItems() throws Exception {
        mockMvc.perform(get("/orders/{id}", "ord-204")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].pricing.unitAmount")
                        .value(120000))
                .andDo(document("orders-items-detailed",
                        responseFields(
                                fieldWithPath("id")
                                        .description("Mã đơn hàng"),
                                fieldWithPath("items[].sku")
                                        .description("Mã sản phẩm"),
                                fieldWithPath("items[].quantity")
                                        .description("Số lượng"),
                                subsectionWithPath("items[].pricing")
                                        .description("Giá của dòng hàng"),
                                subsectionWithPath("items[].options")
                                        .description("Tùy chọn cho dòng hàng"),
                                subsectionWithPath("delivery")
                                        .description("Thông tin giao hàng"),
                                subsectionWithPath("total")
                                        .description("Tổng giá trị đơn hàng")
                        )
                ));
    }

    @RestController
    public static class SampleOrderController {

        @GetMapping(value = "/orders/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<String> findById(@PathVariable String id) {
            if (!"ord-204".equals(id)) {
                return ResponseEntity.notFound().build();
            }

            String json = """
                    {
                      "id": "ord-204",
                      "items": [
                        {
                          "sku": "BOOK-01",
                          "quantity": 2,
                          "pricing": {
                            "unitAmount": 120000,
                            "currency": "VND"
                          },
                          "options": {
                            "giftWrapped": true,
                            "note": "Giao buổi sáng"
                          }
                        },
                        {
                          "sku": "PEN-02",
                          "quantity": 1,
                          "pricing": {
                            "unitAmount": 30000,
                            "currency": "VND"
                          },
                          "options": {
                            "giftWrapped": false,
                            "note": ""
                          }
                        }
                      ],
                      "delivery": {
                        "address": {
                          "city": "Ho Chi Minh City",
                          "country": "VN"
                        },
                        "contact": {
                          "name": "Lan",
                          "phone": "0900000000"
                        }
                      },
                      "total": {
                        "amount": 270000,
                        "currency": "VND"
                      }
                    }
                    """;

            return ResponseEntity.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(json);
        }
    }
}
```

Các test có ba điểm quan trọng:

1. **Ca tổng quan** dùng `subsectionWithPath("items")`: một dòng trong bảng đại diện cho toàn bộ danh sách, kể cả các object lồng bên trong.
2. **Ca chi tiết** dùng `items[].sku` và `items[].quantity`: hiển thị trực tiếp các field được client sử dụng, đồng thời vẫn tóm tắt hai object `pricing` và `options`.
3. **Hai tên tài liệu khác nhau:** `orders-items-overview` và `orders-items-detailed`. Mỗi lần gọi `responseFields(...)` tạo `response-fields.adoc` dưới identifier của test tương ứng. Nếu muốn hai bảng field trong **cùng** identifier, cần các subsection ID/scope khác nhau; tránh hai handler cùng ghi tên snippet.

Trong ví dụ, các assertion `jsonPath` xác minh dữ liệu cụ thể ở ít nhất một phần tử. Đối với API thực tế, hãy bổ sung kiểm tra số phần tử, giá trị tính tiền, điều kiện bắt buộc của từng phần tử và các trường hợp mảng rỗng; `subsectionWithPath` không thay thế logic kiểm thử nghiệp vụ.

## 5. Cách kiểm tra strict thay đổi theo ranh giới subsection

`responseFields(...)` mặc định kiểm tra các field được document trong phạm vi payload. Một field mới không có descriptor thích hợp có thể làm test thất bại. Tuy nhiên, một subsection descriptor coi tất cả hậu duệ của path đó là đã document trong snippet hiện tại.

Giả sử có các thay đổi độc lập:

| Thay đổi trong JSON response | Test tổng quan với `subsectionWithPath("items")` | Test chi tiết dùng `items[].sku`, `items[].quantity` và hai subsection nhỏ |
| --- | --- | --- |
| Thêm `items[0].color` | Có thể pass: nằm trong nhánh `items` | Fail: `color` chưa được document |
| Thêm `items[1].pricing.tax` | Có thể pass | Có thể pass: `pricing` đã được bao phủ ở từng item |
| Thêm `items[1].options.priority` | Có thể pass | Có thể pass: `options` đã được bao phủ ở từng item |
| Thêm `delivery.instructions` | Có thể pass: `delivery` là subsection | Có thể pass: test chi tiết vẫn dùng `subsectionWithPath("delivery")` |
| Thêm `createdAt` tại root | Fail khi chưa khai báo | Fail khi chưa khai báo |
| Bỏ toàn bộ `items` | Fail nếu `items` còn là descriptor bắt buộc | Fail nếu các descriptor item bắt buộc không xuất hiện |

Những kết quả trên nói về **tính đầy đủ của tài liệu field**, không phải toàn bộ contract nghiệp vụ. Một response có field con sai kiểu, sai giá trị hoặc sai số lượng phần tử cần các assertion, kiểm thử validation hoặc contract test bổ sung.

### Trường hợp danh sách rỗng

Một endpoint có thể hợp lệ khi `"items": []`. Đây là trường hợp phải cân nhắc riêng:

- Với bảng tổng quan `subsectionWithPath("items")`, path `items` vẫn hiện diện vì bản thân mảng tồn tại.
- Với bảng chi tiết chỉ mô tả các đường dẫn như `items[].sku`, khi không có phần tử thì không có field `sku` nào để đối chiếu trong ca test đó. Descriptor bắt buộc có thể khiến tài liệu strict thất bại.
- Hãy dùng **một test có danh sách chứa item** để sinh bảng chi tiết, và **một test khác cho danh sách rỗng** để xác nhận behavior theo contract. Không cần ép một test với mảng rỗng sinh bảng chi tiết của phần tử không tồn tại.

Cách tổ chức này giúp tài liệu có ví dụ điển hình, còn test hành vi vẫn bao phủ trường hợp biên.

## 6. Chọn path cho mảng và object sâu

### 6.1. Các pattern phổ biến

| Cấu trúc JSON | Path từ root | Ý nghĩa |
| --- | --- | --- |
| Mảng dòng hàng | `items` | Nhánh danh sách nguyên vẹn |
| SKU trong mỗi dòng hàng | `items[].sku` | Trường `sku` của phần tử mảng |
| Định giá trong từng item | `items[].pricing` | Object con `pricing` lặp lại |
| Tiền đơn vị trong từng item | `items[].pricing.unitAmount` | Field nằm sâu dưới object con của phần tử |
| Object địa chỉ giao hàng | `delivery.address` | Object con của `delivery` |
| Thành phố trong địa chỉ | `delivery.address.city` | Field lá trong object lồng nhau |

Ở cấp root, `subsectionWithPath("delivery.address")` bao phủ `delivery.address.city` và `delivery.address.country`, nhưng **không** bao phủ `delivery.contact.name`. Tương tự, `subsectionWithPath("items[].pricing")` không có trách nhiệm document `items[].options`.

### 6.2. Khi mảng nằm ở root response

Nếu endpoint trả mảng trực tiếp:

```json
[
  {
    "sku": "BOOK-01",
    "pricing": { "unitAmount": 120000, "currency": "VND" }
  },
  {
    "sku": "PEN-02",
    "pricing": { "unitAmount": 30000, "currency": "VND" }
  }
]
```

Đường dẫn đến field `sku` trong các phần tử của mảng root dùng `[].sku`, và đường dẫn đến object con dùng `[].pricing`. Vì vậy có thể mô tả:

```java
responseFields(
    fieldWithPath("[].sku")
        .description("Mã sản phẩm"),
    subsectionWithPath("[].pricing")
        .description("Thông tin giá của từng sản phẩm")
)
```

Điểm khác so với `items[].pricing` là mảng root không có key `items`. Khi soạn descriptor, hãy xuất phát từ **JSON thực tế** mà test nhận được thay vì từ tên class DTO của Java.

### 6.3. Object con của object con

Với `delivery`, một bảng chi tiết từ root có thể là:

```java
responseFields(
    fieldWithPath("id")
        .description("Mã đơn hàng"),
    subsectionWithPath("items")
        .description("Danh sách dòng hàng"),
    subsectionWithPath("delivery.address")
        .description("Địa chỉ giao hàng"),
    fieldWithPath("delivery.contact.name")
        .description("Người liên hệ giao hàng"),
    fieldWithPath("delivery.contact.phone")
        .description("Số điện thoại liên hệ"),
    subsectionWithPath("total")
        .description("Tổng giá trị đơn hàng")
)
```

Bảng này phân tách trách nhiệm rõ hơn: object `address` được tóm tắt, còn `contact.name` và `contact.phone` được ghi chi tiết. Nếu chỉ dùng `subsectionWithPath("delivery")` thì cả `address` lẫn `contact` được gom vào một hàng.

## 7. Khi nào dùng beneathPath để trích riêng cấu trúc lồng nhau?

`subsectionWithPath(...)` chỉ định mức độ bao phủ trong **bảng field hiện tại**. Nếu muốn tài liệu có một đoạn JSON minh họa **chỉ phần `delivery`**, sử dụng:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.beneathPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseBody;

responseBody(
    beneathPath("delivery").withSubsectionId("delivery")
)
```

Handler này đã được dùng trong test `documentOrderOverview` và sinh snippet `response-body-delivery.adoc`. Nó tách riêng dữ liệu `delivery`; các phần `items` và `total` ở ngoài nhánh này không thuộc nội dung đoạn body trích.

Muốn document từng field bên trong `delivery` bằng một bảng riêng:

```java
responseFields(
    beneathPath("delivery").withSubsectionId("delivery-fields"),
    fieldWithPath("address.city")
        .description("Thành phố giao hàng"),
    fieldWithPath("address.country")
        .description("Mã quốc gia"),
    fieldWithPath("contact.name")
        .description("Tên người nhận"),
    fieldWithPath("contact.phone")
        .description("Số điện thoại liên hệ")
)
```

Vì `beneathPath("delivery")` đã chọn nhánh, đường dẫn field trong bảng chi tiết là **tương đối**: `address.city`, không phải `delivery.address.city`. Snippet tạo ra có tên `response-fields-delivery-fields.adoc`.

Với mảng `items`, có thể tạo một bảng chi tiết ngay từ root bằng `items[].sku` hoặc chọn subtree để làm việc với root mới có kiểu array. Khi chọn subtree là array, descriptor phải khớp cấu trúc sau trích, chẳng hạn các field dưới từng phần tử sẽ có tiền tố `[]` thay vì `items[]`. Điều này cần được xác nhận bằng dữ liệu test cụ thể và phiên bản REST Docs mà dự án sử dụng.

**Nguyên tắc:** Dùng `subsectionWithPath` để quyết định **độ sâu của bảng**, dùng `beneathPath` để quyết định **phần JSON được trích làm snippet**.

## 8. Áp dụng cho request payload

Cơ chế hoàn toàn tương tự với `requestFields(...)`. Giả sử `POST /orders` nhận:

```json
{
  "customerId": "cus-17",
  "items": [
    {
      "sku": "BOOK-01",
      "quantity": 2,
      "customization": {
        "giftMessage": "Chúc mừng!"
      }
    }
  ],
  "delivery": {
    "address": {
      "city": "Ho Chi Minh City",
      "country": "VN"
    }
  }
}
```

Nếu tài liệu tổng quan chỉ cần liệt kê ba nhánh:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;

requestFields(
    fieldWithPath("customerId")
        .description("Mã khách hàng"),
    subsectionWithPath("items")
        .description("Các sản phẩm và lựa chọn đi kèm"),
    subsectionWithPath("delivery")
        .description("Thông tin giao hàng")
)
```

Để kiểm tra và document một phần field của từng item:

```java
requestFields(
    fieldWithPath("customerId")
        .description("Mã khách hàng"),
    fieldWithPath("items[].sku")
        .description("Mã sản phẩm"),
    fieldWithPath("items[].quantity")
        .description("Số lượng đặt mua"),
    subsectionWithPath("items[].customization")
        .description("Tùy biến sản phẩm"),
    subsectionWithPath("delivery")
        .description("Thông tin giao hàng")
)
```

Hai ví dụ trên là **hai lựa chọn snippet**; nếu muốn sinh cả hai bảng trong cùng bộ tài liệu, đặt chúng dưới các identifier riêng hoặc dùng công cụ chọn subsection để tạo snippet tên riêng. Với request, kiểm tra tài liệu giúp phát hiện client test gửi field ngoài phần đã mô tả; vẫn cần kiểm thử validation ở controller để bảo vệ các quy tắc nghiệp vụ như `quantity > 0`.

## 9. optional, ignored, relaxed và dữ liệu không đồng nhất

### 9.1. Nhánh danh sách tùy chọn

Nếu hợp đồng cho phép **vắng hoàn toàn** key `items`, có thể đánh dấu:

```java
subsectionWithPath("items")
    .optional()
    .description("Danh sách dòng hàng, nếu có")
```

`optional()` cho phép field không hiện diện trong ca kiểm thử. Tuy nhiên, `items` vắng mặt khác với `"items": []`; nên có test riêng cho mỗi trường hợp API cho phép.

### 9.2. Nhánh con không đồng nhất giữa các phần tử

Nếu object `options` chỉ có ở một số item, khai báo path `items[].options` với `optional()` theo hợp đồng; đồng thời viết các ca test item có/không có options. Đừng suy luận rằng một descriptor `optional()` thay thế cho việc kiểm tra tính bắt buộc của field ở **từng** phần tử khi số phần tử và cấu trúc thay đổi.

Với response phức tạp, assertion hoặc validation bổ sung có thể kiểm tra rằng mọi item đều có `sku`, số lượng là số dương và thông tin tiền tệ hợp lệ. `subsectionWithPath("items")` không tự chứng minh các điều kiện đó.

### 9.3. ignored và relaxed

- `ignored()` cho phép mô tả một path đã biết là được bỏ qua trong bảng nhưng vẫn có vai trò trong kiểm tra các field đã được xử lý. Chỉ nên dùng khi không công bố field đó là chủ đích.
- `relaxedResponseFields(...)` và `relaxedRequestFields(...)` cho phép tồn tại field chưa được document. Tiện lợi khi tài liệu chỉ giới thiệu vài field nhưng sẽ giảm khả năng phát hiện schema ngoài dự kiến.
- `subsectionWithPath(...)` giúp giữ bảng ngắn **mà vẫn áp dụng strict cho những phần ngoài nhánh được bao phủ**. Vì vậy nếu đã biết ranh giới object/mảng cần tóm tắt, đây thường là lựa chọn rõ nghĩa hơn nới lỏng toàn bộ payload.

## 10. Sinh snippet và nhúng Asciidoctor

Sau khi chạy các test trong mục 4, thư mục output thông dụng với Gradle là `build/generated-snippets`. Những snippet chính gồm:

| Đường dẫn | Nguồn | Mục đích |
| --- | --- | --- |
| `orders-items-overview/response-fields.adoc` | `responseFields(...)` tổng quan | Bảng `id`, `items`, `delivery`, `total` |
| `orders-items-overview/response-body-delivery.adoc` | `responseBody(beneathPath("delivery")...)` | Đoạn JSON của `delivery` |
| `orders-items-overview/http-response.adoc` | Snippet HTTP response mặc định | Response đầy đủ đã kiểm thử |
| `orders-items-detailed/response-fields.adoc` | `responseFields(...)` chi tiết | Bảng có các đường dẫn `items[].sku`, `items[].quantity`, `items[].pricing`, `items[].options` |

Một đoạn tài liệu `src/docs/asciidoc/orders.adoc` có thể tham chiếu:

```asciidoc
= Order API
:toc: left

== GET /orders/{id}

Trả về danh sách dòng hàng, thông tin giao hàng và tổng giá trị đơn.

=== HTTP response

include::{snippets}/orders-items-overview/http-response.adoc[]

=== Cấu trúc response tổng quan

include::{snippets}/orders-items-overview/response-fields.adoc[]

=== Chi tiết các field quan trọng trong danh sách

include::{snippets}/orders-items-detailed/response-fields.adoc[]

=== Ví dụ dữ liệu giao hàng

include::{snippets}/orders-items-overview/response-body-delivery.adoc[]
```

Biến `snippets` phải trỏ đến thư mục đầu ra của REST Docs. Tên snippet có thể khác nếu dự án tùy chỉnh template hoặc identifier; hãy đối chiếu với file được tạo sau test. Đoạn trên dùng template Asciidoctor; nếu dự án dùng Markdown, cần template và cơ chế nhúng tương ứng.

### Đưa vào Gradle và CI

Với dự án đã áp dụng plugin Asciidoctor và có các dependency test phù hợp, cấu hình Gradle (Groovy DSL) có thể gồm:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    inputs.dir snippetsDir
    dependsOn tasks.named('test')
    attributes 'snippets': snippetsDir
}
```

Chạy:

```bash
./gradlew clean test asciidoctor
```

Trong CI, hãy để bước dựng tài liệu phụ thuộc vào kiểm thử thành công. Nhờ vậy, thay đổi contract làm test fail sẽ ngăn việc xuất bản tài liệu không còn khớp với HTTP exchange. Với Maven, đường dẫn output thông dụng là `target/generated-snippets` và cần cấu hình plugin tài liệu tương ứng.

## 11. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân phổ biến | Cách xử lý |
| --- | --- | --- |
| Test tổng quan vẫn pass khi thêm field vào item | `subsectionWithPath("items")` đã bao phủ mọi field con | Viết bảng chi tiết hoặc assertion nếu cần kiểm soát field mới |
| Test chi tiết fail khi thêm `items[0].color` | Bảng chỉ mô tả `sku`, `quantity`, `pricing`, `options` | Thêm descriptor cho `items[].color` nếu đó là thay đổi hợp đồng |
| Test vẫn pass khi thêm `items[].pricing.tax` | `items[].pricing` là subsection nên bao phủ hậu duệ | Viết descriptor chi tiết cho `pricing` khi cần |
| Test fail khi mảng `items` rỗng | Path như `items[].sku` có thể không có giá trị để đối chiếu | Dùng fixture có item cho snippet chi tiết, test riêng mảng rỗng |
| Dùng `items[0].sku` rồi bỏ sót item còn lại | Path chỉ chọn phần tử cụ thể | Dùng `items[].sku` cho hợp đồng áp dụng cho cả danh sách |
| Dùng `delivery.address.city` trong `responseFields(beneathPath("delivery"), ...)` | Descriptor đang tính từ root trong khi extractor đã chọn `delivery` | Dùng `address.city` |
| Không thấy `response-body-delivery.adoc` | Chưa dùng `responseBody(beneathPath(...))` hoặc ID khác dự kiến | Kiểm tra handler, identifier, subsection ID và output sau test |
| Asciidoctor báo không tìm thấy snippet | Sai biến `snippets` hoặc bước test chưa chạy | Đồng bộ đường dẫn và thứ tự task build |

## 12. Bài thực hành

Áp dụng vào ví dụ `OrderItemsDocumentationTest`:

1. **Ranh giới mảng:** Thêm `items[0].color`. Chạy hai test để quan sát khác biệt giữa `subsectionWithPath("items")` và cách document các field con.
2. **Ranh giới object trong mảng:** Thêm `items[1].pricing.tax`. Quan sát rằng `subsectionWithPath("items[].pricing")` bao phủ field mới; sau đó thay descriptor đó bằng các field `items[].pricing.unitAmount`, `items[].pricing.currency` và kiểm tra lại.
3. **Object lồng sâu:** Trong bảng chi tiết, thay `subsectionWithPath("delivery")` bằng `subsectionWithPath("delivery.address")` cùng các field `delivery.contact.name`, `delivery.contact.phone`.
4. **Mảng rỗng:** Tạo biến thể trả `"items": []` và viết test riêng; giải thích vì sao cần tách ca sinh bảng field chi tiết ra khỏi ca kiểm tra mảng rỗng.
5. **Response body subsection:** Sinh và nhúng `response-body-delivery.adoc` vào Asciidoctor. So sánh với `http-response.adoc` để xác nhận chỉ phần dữ liệu cần giải thích được trích.
6. **Build/CI:** Chạy `./gradlew clean test asciidoctor` trong dự án đã cấu hình. Đọc lỗi nếu một descriptor strict thiếu field và cập nhật tài liệu theo contract thực tế.

**Tiêu chí hoàn thành:** người học giải thích được sự khác nhau giữa path `items`, `items[].sku`, `items[].pricing`, chỉ ra được các thay đổi schema mà bảng tổng quan sẽ bỏ qua, và biết chọn cách document riêng từng phần của cấu trúc JSON lồng nhau mà không làm bảng API quá dài.

## 13. Câu hỏi tự kiểm tra

**1. Khi nào nên dùng `subsectionWithPath("items")`?**

Khi muốn mô tả cả danh sách như một khối nghiệp vụ và không yêu cầu bảng hiện tại liệt kê từng field trong phần tử. Nếu hợp đồng cần kiểm soát các field của từng item, thêm test và snippet chi tiết.

**2. `subsectionWithPath("items[].pricing")` có bao phủ `items[].sku` không?**

Không. Nó bao phủ các hậu duệ của `pricing` trên các item, chẳng hạn `items[].pricing.unitAmount`. `sku` là field anh em và cần được document riêng trong bảng strict.

**3. Vì sao hai test dùng response giống nhau có thể cho kết quả khác khi thêm field?**

Vì mỗi test dùng **tập descriptor và ranh giới subsection khác nhau**. Kiểm thử tổng quan chấp nhận field nằm trong nhánh đã bao phủ; kiểm thử chi tiết có thể phát hiện field mới ngoài những subsection nhỏ được khai báo.

**4. Khi chỉ muốn JSON của `delivery`, nên gọi API nào?**

Gọi `responseBody(beneathPath("delivery"))`. `subsectionWithPath("delivery")` chỉ tạo descriptor trong bảng field, không sinh body trích riêng.

**5. Có thể dựa duy nhất vào subsectionWithPath để đảm bảo mọi item đều hợp lệ không?**

Không. Đây là cơ chế document payload. Tính đúng đắn nghiệp vụ như SKU hợp lệ, tổng tiền, quantity dương và quan hệ giữa các field cần assertion hoặc kiểm thử validation riêng.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): field path, document subsection, kiểm tra completeness và trích một phần payload.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): cấu hình MockMvc/WebTestClient/REST Assured, snippet, Asciidoctor và tích hợp build.

