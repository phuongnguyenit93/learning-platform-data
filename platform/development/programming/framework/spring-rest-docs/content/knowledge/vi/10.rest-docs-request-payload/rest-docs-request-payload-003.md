# `fieldWithPath` và đường dẫn trường lồng nhau trong Spring REST Docs

## 1. Mục tiêu và bối cảnh

REST API thực tế hiếm khi nhận một JSON chỉ gồm các trường đơn giản như `name` và `email`. Payload thường có **object lồng nhau**, **mảng các object**, mảng nằm trong mảng và đôi khi có tên trường chứa dấu chấm hoặc các khóa được tạo động. Nếu mô tả nhầm đường dẫn, bảng tài liệu của API có thể thiếu những trường quan trọng hoặc bước sinh tài liệu sẽ thất bại.

Trong **Spring REST Docs**, `fieldWithPath(...)` xác định **vị trí của một trường trong JSON**, còn `requestFields(...)` gom các mô tả thành snippet về request body. Cơ chế này hoạt động cùng bài kiểm thử HTTP bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**. Từ các snippet, nhóm phát triển có thể biên soạn tài liệu Asciidoctor/Markdown và tái sinh tài liệu trong build/CI.

Bài này thuộc chương **Request payload**, tập trung vào việc đọc và viết đường dẫn trường bằng `fieldWithPath` trong các cấu trúc JSON phức tạp. Sau khi học, bạn có thể:

- Dùng cú pháp dấu chấm để trỏ đến trường nằm trong object.
- Dùng `[]` để mô tả phần tử của mảng và trường bên trong từng phần tử.
- Dùng cú pháp ngoặc vuông có dấu nháy cho **tên trường chứa dấu chấm**.
- Biết khi nào có thể dùng ký tự đại diện `*` cho các khóa động.
- Viết bài kiểm thử tạo `request-fields.adoc`, hiểu giới hạn kiểm chứng của snippet và cách xử lý các đường dẫn báo thiếu.

## 2. Bản đồ đường dẫn trường từ một JSON thực tế

Giả sử API tạo đơn hàng `POST /api/orders` nhận request body:

```json
{
  "customer": {
    "id": 42,
    "profile": {
      "displayName": "Nguyễn Minh An",
      "contact": {
        "email": "an@example.com"
      }
    }
  },
  "items": [
    {
      "sku": "SHIRT-001",
      "quantity": 2,
      "options": [
        { "name": "color", "value": "navy" }
      ]
    },
    {
      "sku": "SOCK-002",
      "quantity": 1,
      "options": []
    }
  ],
  "tags": ["gift", "priority"],
  "metadata": {
    "source": "mobile",
    "campaign.name": "fall-2026"
  },
  "attributes": {
    "store": "hcm-01",
    "device": "android"
  }
}
```

Hãy hình dung JSON như cây: object chứa các nhánh mang tên khóa; array chứa phần tử theo vị trí. `fieldWithPath` mô tả **đường đi trong cây** theo cú pháp của Spring REST Docs, không phải một biểu thức truy vấn JSONPath đầy đủ.

| Cần mô tả | Đường dẫn dùng với `fieldWithPath` | Giải thích |
| --- | --- | --- |
| Object khách hàng | `customer` | Trường cấp gốc |
| Mã khách hàng | `customer.id` | Con trực tiếp của `customer` |
| Tên hiển thị | `customer.profile.displayName` | Đi qua hai object lồng nhau |
| Email | `customer.profile.contact.email` | Đi qua ba object lồng nhau |
| Toàn bộ mảng mặt hàng | `items` | Bản thân mảng |
| Mã mặt hàng | `items[].sku` | `sku` trong từng object của `items` |
| Tên tùy chọn | `items[].options[].name` | Object trong mảng `options`, nằm trong `items` |
| Toàn bộ mảng nhãn | `tags` | Bản thân mảng các string |
| Mỗi nhãn | `tags[]` | Một phần tử string của mảng |
| Nguồn đơn hàng | `metadata.source` | Tên khóa thông thường |
| Khóa tên `campaign.name` | `metadata['campaign.name']` | Dấu chấm là **một phần tên khóa** |
| Các giá trị thuộc map động | `attributes.*` | `*` khớp các khóa con trực tiếp của `attributes` |

Điểm quan trọng nhất: `items[].sku` **không** có nghĩa “chỉ lấy phần tử đầu tiên”. Ký hiệu `[]` mô tả trường `sku` ở các phần tử mảng, bất kể chỉ số cụ thể. Ngược lại, `metadata['campaign.name']` phải giữ nguyên chuỗi `campaign.name` thành **một tên khóa**; viết `metadata.campaign.name` sẽ được hiểu là hai tầng `campaign` và `name`, không khớp JSON mẫu.

### Phân biệt bốn loại cú pháp

```text
customer.profile.displayName     -> object -> object -> trường
items[].sku                      -> mảng -> từng object -> trường
metadata['campaign.name']        -> object -> khóa có dấu chấm trong tên
attributes.*                     -> object -> các khóa con thay đổi
```

Không cần thêm ký tự `$` ở đầu đường dẫn như nhiều cách viết JSONPath. Khi dùng Spring REST Docs, viết `fieldWithPath("customer.id")`, không viết `fieldWithPath("$.customer.id")`.

## 3. Cú pháp dấu chấm (`.`) và object lồng nhau

Đây là trường hợp phổ biến nhất:

```json
{
  "account": {
    "id": 100,
    "owner": {
      "name": "Bình",
      "contact": {
        "email": "binh@example.com"
      }
    }
  }
}
```

Các descriptor tương ứng:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

fieldWithPath("account")
        .description("Thông tin tài khoản");

fieldWithPath("account.id")
        .description("Mã tài khoản");

fieldWithPath("account.owner")
        .description("Chủ tài khoản");

fieldWithPath("account.owner.name")
        .description("Tên chủ tài khoản");

fieldWithPath("account.owner.contact.email")
        .description("Email của chủ tài khoản");
```

Mỗi phần giữa các dấu chấm là một khóa JSON thuộc một object. Đường dẫn không phụ thuộc vào tên class Java hay tên biến DTO; nó phải phù hợp với **JSON thật được gửi qua HTTP**. Ví dụ, nếu DTO có thuộc tính `displayName` nhưng cấu hình Jackson dùng `@JsonProperty("display_name")`, descriptor cần trỏ đến `display_name`:

```java
fieldWithPath("account.owner.display_name")
        .description("Tên hiển thị theo tên trường JSON");
```

### Tên khóa có dấu chấm: dùng cú pháp ngoặc

Hai JSON sau không tương đương:

```json
{ "config": { "logging.level": "INFO" } }
```

```json
{ "config": { "logging": { "level": "INFO" } } }
```

Đường dẫn tương ứng là:

```java
// Khóa nguyên văn "logging.level"
fieldWithPath("config['logging.level']")
        .description("Mức log");

// Khóa "level" nằm trong object "logging"
fieldWithPath("config.logging.level")
        .description("Mức log");
```

Tương tự, một khóa cấp gốc có tên chứa dấu chấm có thể được mô tả bằng cú pháp ngoặc như `fieldWithPath("['request.id']")`.

**Quy tắc nhớ:** dấu chấm bên ngoài cặp dấu nháy trong cú pháp đường dẫn phân cách các tầng; dấu chấm nằm *trong tên khóa được trích dẫn* là một phần của tên trường. Có thể dùng cú pháp ngoặc cho những tên khóa thường nếu muốn, nhưng dấu chấm dễ đọc hơn khi khóa không có ký tự đặc biệt.

## 4. Cú pháp `[]` và các tầng mảng

### 4.1. Mảng các object

Với JSON:

```json
{
  "products": [
    { "id": "P-01", "quantity": 2 },
    { "id": "P-02", "quantity": 3 }
  ]
}
```

Các đường dẫn:

```java
fieldWithPath("products")
        .description("Danh sách sản phẩm");

fieldWithPath("products[].id")
        .description("Mã sản phẩm");

fieldWithPath("products[].quantity")
        .description("Số lượng từng sản phẩm");
```

`products[].id` diễn đạt cùng một cấu trúc xuất hiện trong các phần tử mảng. Không cần và thường không nên liệt kê `products[0].id`, `products[1].id` chỉ để mô tả schema chung của một danh sách. Điều quan trọng là mỗi object trong mảng tuân theo hợp đồng API.

### 4.2. Mảng giá trị nguyên thủy

Nếu JSON có:

```json
{
  "tags": ["spring", "documentation"]
}
```

Ta có hai cấp mô tả khác nhau:

```java
fieldWithPath("tags")
        .description("Danh sách nhãn");

fieldWithPath("tags[]")
        .description("Một nhãn trong danh sách");
```

`tags` nói về toàn bộ array. `tags[]` nói về từng phần tử, trong trường hợp này là String. Cần phân biệt rõ hai cấp nếu muốn tài liệu giải thích cả ý nghĩa danh sách lẫn ý nghĩa từng giá trị.

### 4.3. Mảng bên trong mảng

Với JSON:

```json
{
  "groups": [
    ["A", "B"],
    ["C"]
  ]
}
```

Có thể mô tả:

```java
fieldWithPath("groups")
        .description("Các nhóm mã");

fieldWithPath("groups[]")
        .description("Một nhóm mã, biểu diễn bằng mảng");

fieldWithPath("groups[][]")
        .description("Một mã trong nhóm");
```

Mỗi cặp `[]` thể hiện một cấp array. Khi gặp cấu trúc mảng nhiều tầng và object trộn lẫn, hãy đọc đường dẫn từ trái sang phải, qua từng cấp theo đúng cấu trúc mẫu.

### 4.4. Mảng object chứa mảng object

Trong ví dụ tạo đơn hàng, đường dẫn `items[].options[].value` gồm:

1. `items[]`: một phần tử thuộc mảng mặt hàng;
2. `options[]`: một phần tử thuộc mảng tùy chọn của mặt hàng đó;
3. `value`: trường thuộc object tùy chọn.

```java
fieldWithPath("items[].options[].value")
        .description("Giá trị của từng tùy chọn sản phẩm");
```

**Khi sinh snippet, nên cung cấp dữ liệu mẫu có ít nhất một phần tử ở những nhánh cần tài liệu hóa.** Nếu tất cả `options` đều là mảng rỗng, bài kiểm thử không có giá trị thực tế để đối chiếu những descriptor như `items[].options[].name` và `items[].options[].value`. Kiểm thử trường hợp mảng rỗng nên là một tình huống riêng theo contract.

## 5. Ký tự đại diện `*` khi tên khóa thay đổi

Không phải JSON object nào cũng có danh sách khóa cố định. Một API có thể nhận map thuộc tính:

```json
{
  "attributes": {
    "store": "hcm-01",
    "device": "android",
    "campaign": "holiday"
  }
}
```

Nếu contract cho phép client gửi những **khóa bất kỳ có giá trị cùng kiểu**, có thể dùng wildcard:

```java
fieldWithPath("attributes")
        .description("Map các thuộc tính bổ sung");

fieldWithPath("attributes.*")
        .description("Giá trị thuộc tính bổ sung");
```

Trong đó `*` biểu diễn các khóa con tại cấp tương ứng của object `attributes`. Mục đích là mô tả **cấu trúc map có tên khóa động**, chứ không phải tự động sinh mô tả riêng cho từng key. Hãy ghi rõ quy tắc tên key, giới hạn giá trị và những key bị cấm nếu API có các điều kiện đó.

So sánh:

| JSON object | Descriptor | Ý nghĩa |
| --- | --- | --- |
| `{ "attributes": {"store": "hcm"} }` | `attributes.store` | Chỉ một khóa `store` cụ thể |
| `{ "attributes": {"store": "hcm"} }` | `attributes.*` | Những khóa thuộc map `attributes` |
| `{ "items": [{"sku": "A"}] }` | `items[].sku` | Trường `sku` của các object trong mảng |

`*` không có nghĩa giống `[]`: wildcard biểu diễn **tên trường** thay đổi, còn `[]` đi qua **phần tử mảng**. Nếu map chứa dữ liệu khác kiểu, hãy mô tả contract rõ hơn, cân nhắc descriptor phù hợp hoặc một cấu trúc DTO có thể kiểm soát, thay vì giả định mọi giá trị đồng nhất.

## 6. Ví dụ hoàn chỉnh với MockMvc: sinh snippet cho payload nhiều tầng

Phần này dùng Spring Boot 3.x, JUnit 5, Java 17 và Spring REST Docs MockMvc. Giả sử endpoint `POST /api/orders` đã tồn tại và trả **HTTP 201 Created** khi request hợp lệ. Cần có dependency `spring-boot-starter-test` và `spring-restdocs-mockmvc` trong cấu hình kiểm thử.

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

Bài test gửi đúng request JSON ở mục 2 và mô tả các đường dẫn quan trọng:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.restdocs.payload.JsonFieldType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class OrderNestedPayloadDocumentationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentNestedOrderRequest() throws Exception {
        String requestJson = """
                {
                  "customer": {
                    "id": 42,
                    "profile": {
                      "displayName": "Nguyễn Minh An",
                      "contact": {
                        "email": "an@example.com"
                      }
                    }
                  },
                  "items": [
                    {
                      "sku": "SHIRT-001",
                      "quantity": 2,
                      "options": [
                        { "name": "color", "value": "navy" }
                      ]
                    },
                    {
                      "sku": "SOCK-002",
                      "quantity": 1,
                      "options": []
                    }
                  ],
                  "tags": ["gift", "priority"],
                  "metadata": {
                    "source": "mobile",
                    "campaign.name": "fall-2026"
                  },
                  "attributes": {
                    "store": "hcm-01",
                    "device": "android"
                  }
                }
                """;

        mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.APPLICATION_JSON)
                    .content(requestJson))
                .andExpect(status().isCreated())
                .andDo(document("orders-nested-request",
                        requestFields(
                                fieldWithPath("customer")
                                        .type(JsonFieldType.OBJECT)
                                        .description("Thông tin khách hàng"),
                                fieldWithPath("customer.id")
                                        .type(JsonFieldType.NUMBER)
                                        .description("Mã khách hàng"),
                                fieldWithPath("customer.profile")
                                        .type(JsonFieldType.OBJECT)
                                        .description("Hồ sơ khách hàng"),
                                fieldWithPath("customer.profile.displayName")
                                        .type(JsonFieldType.STRING)
                                        .description("Tên hiển thị"),
                                fieldWithPath("customer.profile.contact")
                                        .type(JsonFieldType.OBJECT)
                                        .description("Thông tin liên hệ"),
                                fieldWithPath("customer.profile.contact.email")
                                        .type(JsonFieldType.STRING)
                                        .description("Email liên hệ"),

                                fieldWithPath("items")
                                        .type(JsonFieldType.ARRAY)
                                        .description("Danh sách mặt hàng"),
                                fieldWithPath("items[].sku")
                                        .type(JsonFieldType.STRING)
                                        .description("Mã sản phẩm"),
                                fieldWithPath("items[].quantity")
                                        .type(JsonFieldType.NUMBER)
                                        .description("Số lượng"),
                                fieldWithPath("items[].options")
                                        .type(JsonFieldType.ARRAY)
                                        .description("Các tùy chọn mặt hàng"),
                                fieldWithPath("items[].options[].name")
                                        .type(JsonFieldType.STRING)
                                        .description("Tên tùy chọn"),
                                fieldWithPath("items[].options[].value")
                                        .type(JsonFieldType.STRING)
                                        .description("Giá trị tùy chọn"),

                                fieldWithPath("tags")
                                        .type(JsonFieldType.ARRAY)
                                        .description("Các nhãn đơn hàng"),
                                fieldWithPath("tags[]")
                                        .type(JsonFieldType.STRING)
                                        .description("Một nhãn"),
                                fieldWithPath("metadata")
                                        .type(JsonFieldType.OBJECT)
                                        .description("Metadata của đơn hàng"),
                                fieldWithPath("metadata.source")
                                        .type(JsonFieldType.STRING)
                                        .description("Nguồn tạo đơn"),
                                fieldWithPath("metadata['campaign.name']")
                                        .type(JsonFieldType.STRING)
                                        .description("Tên chiến dịch"),

                                fieldWithPath("attributes")
                                        .type(JsonFieldType.OBJECT)
                                        .description("Các thuộc tính mở rộng"),
                                fieldWithPath("attributes.*")
                                        .type(JsonFieldType.STRING)
                                        .description("Giá trị thuộc tính mở rộng")
                        )));
    }
}
```

Sau khi bài kiểm thử vượt qua kỳ vọng HTTP và bước tài liệu hóa, thư mục kết quả thường có dạng:

```text
build/generated-snippets/
└── orders-nested-request/
    ├── http-request.adoc
    ├── http-response.adoc
    └── request-fields.adoc
```

Tùy cấu hình REST Docs, thư mục có thể chứa thêm các snippet khác như `curl-request.adoc`, `httpie-request.adoc` hoặc `request-body.adoc`. `request-fields.adoc` là snippet được tạo từ `requestFields(...)` trong ví dụ.

### Trình tự xác minh

1. MockMvc gửi request JSON đến endpoint trong môi trường test.
2. `.andExpect(status().isCreated())` xác nhận HTTP status mà ví dụ mong đợi.
3. `requestFields(...)` đối chiếu các descriptor với request payload mẫu để sinh bảng trường.
4. Các đường dẫn có dữ liệu được đưa vào snippet dưới dạng tên trường, kiểu và mô tả.
5. Nếu bài test và tạo snippet đều thành công, Asciidoctor có thể include bảng từ thư mục output.

**Giới hạn quan trọng:** Spring REST Docs kiểm tra việc tài liệu hóa đối với payload thực tế được đưa vào test. Nó **không phải** công cụ xác thực JSON Schema tổng quát: khai báo `.type(JsonFieldType.STRING)` và `.description("...")` chủ yếu phục vụ tài liệu, không tự bảo đảm rằng mọi request của API ngoài thực tế đều có đúng kiểu hoặc thỏa mãn các ràng buộc nghiệp vụ.

## 7. Trường bắt buộc, tùy chọn và nhánh không phải lúc nào cũng xuất hiện

Theo mặc định, descriptor được khai báo với `fieldWithPath(...)` là **bắt buộc trong bước tài liệu hóa**. Nếu request mẫu thiếu trường được mô tả là bắt buộc, bước sinh snippet có thể thất bại.

Khi hợp đồng cho phép không gửi trường, dùng `.optional()`:

```java
fieldWithPath("customer.profile.contact.phone")
        .type(JsonFieldType.STRING)
        .description("Số điện thoại, có thể bỏ qua")
        .optional()
```

Ví dụ `phone` không có trong JSON ở mục 2, nhưng descriptor này vẫn có thể được đưa vào bảng nhờ `.optional()`.

Khi **cả một object** có thể vắng mặt, cần xem xét trạng thái tùy chọn của các descriptor bên trong nó. Ví dụ:

```java
fieldWithPath("shipping")
        .type(JsonFieldType.OBJECT)
        .description("Thông tin giao hàng, tùy chọn")
        .optional(),

fieldWithPath("shipping.receiverName")
        .type(JsonFieldType.STRING)
        .description("Tên người nhận khi có giao hàng")
        .optional(),

fieldWithPath("shipping.address.city")
        .type(JsonFieldType.STRING)
        .description("Thành phố giao hàng")
        .optional()
```

Đánh dấu object cha là tùy chọn không tự biến các descriptor con thành tùy chọn. Nếu trường con có ràng buộc “bắt buộc **khi** object cha xuất hiện”, cần kiểm tra thêm với test/validation, vì `.optional()` một mình không biểu đạt được toàn bộ điều kiện đó.

Phân biệt thêm:

- **Không có khóa:** trường thực sự vắng mặt trong JSON.
- **Có khóa nhưng giá trị `null`:** JSON vẫn chứa tên trường nhưng giá trị là `null`; quy tắc cho phép hay từ chối `null` thuộc hợp đồng và validation.
- **Có khóa với object/mảng rỗng:** nhánh tồn tại nhưng có thể không có phần tử hoặc trường con để mô tả.
- **Có khóa nhưng sai kiểu:** có thể khiến tài liệu mô tả sai nếu chỉ trông chờ `.type(...)`; hãy bổ sung test nghiệp vụ và validation.

Trong bài kiểm thử tài liệu hóa, nên dùng request mẫu đại diện có đủ nhánh để mọi đường dẫn quan trọng được thể hiện. Những nhánh tùy chọn vắng mặt hoặc mảng rỗng cần có test khác để xác minh hành vi API.

## 8. `fieldWithPath` so với `subsectionWithPath`

Khi object lớn, bạn có thể chọn chỉ mô tả một nhánh như một khối:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.subsectionWithPath;

subsectionWithPath("customer.profile")
        .description("Thông tin hồ sơ khách hàng");
```

`subsectionWithPath(...)` dùng để mô tả **cả phần cấu trúc nằm dưới** một đường dẫn, không yêu cầu liệt kê chi tiết từng trường con trong snippet hiện tại. Cách này hữu ích khi có nhiều tài liệu con riêng hoặc chỉ cần bảng tổng quan.

Trong khi đó:

```java
fieldWithPath("customer.profile.displayName")
        .description("Tên hiển thị");

fieldWithPath("customer.profile.contact.email")
        .description("Email liên hệ");
```

cho phép bảng tài liệu nêu rõ các trường mà client cần biết. Khi muốn tài liệu chi tiết, nên khai báo riêng từng trường có ý nghĩa.

Lưu ý: với Spring REST Docs, việc đã mô tả **một object hoặc mảng cha** có thể khiến các trường con được xem là đã được bao phủ khi phát hiện trường chưa được tài liệu hóa. Vì vậy, một test `requestFields` chạy thành công **không tự chứng minh rằng từng trường con đều có mô tả riêng**. Hãy thiết kế bảng descriptor theo mức chi tiết mà người sử dụng API cần.

## 9. Cách nhận biết đường dẫn sai và đọc lỗi

Giả sử payload là:

```json
{
  "items": [{ "sku": "BOOK-001" }],
  "metadata": { "campaign.name": "back-to-school" }
}
```

Các đường dẫn sau thể hiện lỗi thường gặp:

| Descriptor viết sai | Vấn đề | Cách viết đúng |
| --- | --- | --- |
| `item[].sku` | Sai tên khóa `items` | `items[].sku` |
| `items.sku` | Bỏ qua cấp array | `items[].sku` |
| `items[0].sku` | Gắn vào một chỉ số cụ thể thay vì mô tả cấu trúc chung | `items[].sku` |
| `metadata.campaign.name` | Chia tên khóa `campaign.name` thành hai object | `metadata['campaign.name']` |
| `attributes[]` | Coi map các key động như một mảng | `attributes.*` |
| `$.items[].sku` | Dùng tiền tố của JSONPath thông thường | `items[].sku` |

Các lỗi khác:

| Triệu chứng | Nguyên nhân có thể gặp | Hướng xử lý |
| --- | --- | --- |
| Test báo field chưa được tài liệu hóa | JSON có khóa mới nhưng chưa có descriptor | Bổ sung `fieldWithPath`, mô tả rõ cấu trúc |
| Test báo thiếu field | Sai path, sai chữ hoa/thường hoặc trường bắt buộc vắng mặt trong mẫu | So sánh trực tiếp path với JSON thực tế, thêm `.optional()` chỉ khi contract cho phép |
| Không mô tả được `items[].options[].value` | Không có phần tử trong mảng `options` của request mẫu | Gửi test có phần tử đại diện và test mảng rỗng riêng |
| Khóa chứa dấu chấm không khớp | Dùng dot notation thay vì ngoặc trích dẫn | Viết `metadata['campaign.name']` |
| Một số trường con không xuất hiện trong bảng | Chỉ mô tả object cha hoặc dùng `subsectionWithPath` | Khai báo descriptor chi tiết cho từng trường cần công bố |
| Test HTTP thành công nhưng không có `request-fields.adoc` | Chưa gọi `document(..., requestFields(...))` hoặc output path khác | Kiểm tra cấu hình REST Docs và thư mục snippets |
| Bảng mô tả đúng nhưng API vẫn nhận dữ liệu sai | Tài liệu hóa không thay thế validation | Bổ sung Bean Validation và kiểm thử lỗi HTTP phù hợp |

Trong chế độ `requestFields(...)` mặc định, các trường chưa được tài liệu hóa có thể gây lỗi. Có thể dùng `relaxedRequestFields(...)` khi cố ý muốn mô tả chỉ một phần của JSON, nhưng cách này cho phép trường dư không được mô tả và có thể che giấu thay đổi hợp đồng.

## 10. Tái sử dụng trong WebTestClient, REST Assured và tài liệu build

Điểm chung giữa ba phương pháp kiểm thử là phần mô tả:

```java
requestFields(
        fieldWithPath("items").description("Danh sách mặt hàng"),
        fieldWithPath("items[].sku").description("Mã sản phẩm")
)
```

Điểm khác nhau nằm ở **vị trí gắn hoạt động sinh snippet vào luồng kiểm thử HTTP**:

| Công cụ | Cách gắn tài liệu (minh họa) |
| --- | --- |
| MockMvc | `.andDo(document("orders", requestFields(...)))` |
| WebTestClient | `.expectBody().consumeWith(document("orders", requestFields(...)))` |
| REST Assured | `.filter(document("orders", requestFields(...)))` |

Mỗi loại dùng `document(...)` và cấu hình của **module Spring REST Docs tích hợp tương ứng**. Ví dụ MockMvc dùng `MockMvcRestDocumentation.document`, WebTestClient dùng `WebTestClientRestDocumentation.document`, còn REST Assured dùng `RestAssuredRestDocumentation.document`.

Khi kết hợp Asciidoctor, có thể viết `src/docs/asciidoc/api.adoc`:

```adoc
= Orders REST API
:toc: left

== Tạo đơn hàng

=== HTTP request
include::{snippets}/orders-nested-request/http-request.adoc[]

=== Các trường request body
include::{snippets}/orders-nested-request/request-fields.adoc[]

=== HTTP response
include::{snippets}/orders-nested-request/http-response.adoc[]
```

Cần cấu hình biến `{snippets}` trỏ về thư mục đã sinh, ví dụ `build/generated-snippets`. Build nên chạy bài kiểm thử sinh snippets **trước** khi chạy Asciidoctor và đảm bảo task kết xuất phụ thuộc vào đầu ra đó. Trong CI, một thay đổi phá vỡ bài kiểm thử tài liệu hóa phải làm build thất bại. Nếu muốn phát hành Markdown, cần bổ sung template Markdown hoặc bước chuyển đổi thích hợp; snippet mặc định của ví dụ là `.adoc`.

## 11. Bài thực hành

Sử dụng JSON tạo đơn hàng ở mục 2 và bài test MockMvc ở mục 6:

1. **Thêm trường lồng nhau:** đưa `customer.profile.contact.phone` vào JSON và khai báo `fieldWithPath("customer.profile.contact.phone")`. Sau đó bỏ trường khỏi JSON, thêm `.optional()` và xác nhận test tài liệu hóa vẫn thành công.
2. **Thêm cấp mảng:** mỗi mặt hàng có `warehouseAllocations: [{"warehouseId":"HCM","quantity":1}]`. Viết các descriptor `items[].warehouseAllocations`, `items[].warehouseAllocations[].warehouseId` và `items[].warehouseAllocations[].quantity`.
3. **Thử khóa chứa dấu chấm:** thêm `"build.version": "1.2"` vào `metadata`. Cố ý viết `metadata.build.version`, quan sát lỗi, rồi đổi thành `metadata['build.version']`.
4. **Thử map khóa động:** bổ sung `"channel": "partner"` vào `attributes`; kiểm tra xem descriptor `attributes.*` có đáp ứng mục tiêu mô tả map hay không. Ghi rõ rằng các giá trị thuộc map là String.
5. **Kiểm tra tài liệu được xuất:** chạy bài kiểm thử, mở `request-fields.adoc` và xác nhận có mô tả cho object, mảng, trường lồng nhau, khóa chứa dấu chấm, các thuộc tính động. Nhúng snippet vào Asciidoctor để kiểm tra bảng cuối cùng.

### Câu hỏi tự đánh giá

- Vì sao `items[].sku` diễn đạt hợp đồng danh sách tốt hơn việc mô tả từng chỉ số mảng?
- Khi nào `metadata['campaign.name']` khác với `metadata.campaign.name`?
- `attributes.*` khác `attributes[]` như thế nào?
- Việc đã có descriptor `items` có đủ để **người đọc** hiểu các trường `sku`, `quantity` và `options` hay chưa?
- Vì sao vẫn cần kiểm thử validation dù `requestFields` đã tạo bảng thành công?

**Điểm cần nhớ:** `fieldWithPath` trỏ đến **cấu trúc JSON gửi thật qua HTTP**. Dấu chấm biểu diễn object lồng nhau, `[]` biểu diễn tầng array, cú pháp `['...']` giữ nguyên các tên khóa đặc biệt, còn `*` hỗ trợ map có tên khóa động. Dùng đúng các đường dẫn này giúp sinh snippet request payload chi tiết, tái tạo được và dễ phát hiện sai lệch trong chuỗi build/CI.
