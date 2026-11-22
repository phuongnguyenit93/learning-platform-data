# Mô tả trường JSON bắt buộc và tùy chọn trong Spring REST Docs

## 1. Mục tiêu của bài học

Khi một REST API nhận JSON, tài liệu cần trả lời được hai câu hỏi: **client phải gửi những trường nào** và **những trường nào có thể bỏ qua**. Nếu tài liệu không phân biệt rõ hai nhóm này, người dùng API dễ gửi thiếu dữ liệu, còn người bảo trì có thể vô tình thay đổi hợp đồng request mà không nhận ra.

Với **Spring REST Docs**, tài liệu được tạo từ bài kiểm thử HTTP bằng MockMvc, WebTestClient hoặc REST Assured. Trong chương **Request payload**, `requestFields(...)` khai báo các trường của JSON request và `fieldWithPath(...).optional()` đánh dấu trường có thể vắng mặt. Các mô tả này trở thành snippet có thể đưa vào tài liệu Asciidoctor hoặc quy trình xuất Markdown và kiểm tra trong build/CI.

Sau bài này, bạn sẽ biết cách:

- Phân biệt trường *bắt buộc* và *tùy chọn* ở cấp độ tài liệu Spring REST Docs.
- Viết descriptor cho trường JSON ở cấp gốc, object lồng nhau và mảng.
- Chứng minh bằng test rằng một trường tùy chọn có thể xuất hiện hoặc vắng mặt.
- Tránh nhầm việc tài liệu hóa bằng `optional()` với kiểm tra đầu vào của ứng dụng.
- Nhận biết lỗi do thiếu descriptor, thiếu trường bắt buộc và xử lý chưa đúng giá trị `null`.

## 2. Trường bắt buộc và tùy chọn nghĩa là gì?

Xét hợp đồng `POST /api/customers` để tạo khách hàng:

```json
{
  "fullName": "Nguyễn Minh An",
  "email": "an@example.com",
  "address": {
    "street": "12 Nguyễn Huệ",
    "city": "TP. Hồ Chí Minh"
  },
  "preferences": {
    "newsletter": true
  }
}
```

Hợp đồng giả định của endpoint như sau:

| JSON path | Kiểu dữ liệu | Trạng thái | Mô tả |
| --- | --- | --- | --- |
| `fullName` | String | Bắt buộc | Họ và tên khách hàng |
| `email` | String | Bắt buộc | Địa chỉ email hợp lệ |
| `address` | Object | Bắt buộc | Địa chỉ liên hệ |
| `address.street` | String | Bắt buộc | Số nhà và tên đường |
| `address.city` | String | Bắt buộc | Thành phố |
| `address.apartment` | String | Tùy chọn | Số căn hộ hoặc tầng |
| `phone` | String | Tùy chọn | Số điện thoại liên hệ |
| `preferences` | Object | Tùy chọn | Các tùy chọn liên lạc |
| `preferences.newsletter` | Boolean | Tùy chọn | Có nhận bản tin hay không |

Ở đây, request mẫu không có `phone` hay `address.apartment` nhưng vẫn hợp lệ theo hợp đồng đã đặt ra. Object `preferences` xuất hiện trong mẫu, song client được phép bỏ qua toàn bộ object này.

Spring REST Docs quy ước:

- `fieldWithPath("email")`: **bắt buộc theo mặc định**. Nếu đường dẫn này không có trong request mẫu đang được tài liệu hóa, việc tạo snippet theo descriptor đó sẽ thất bại.
- `fieldWithPath("phone").optional()`: **tùy chọn trong tài liệu**. Request mẫu có thể không chứa `phone` và bước sinh snippet vẫn được phép thành công.
- `fieldWithPath("preferences.newsletter").optional()`: trường con cũng được phép không xuất hiện, bao gồm trường hợp object cha không xuất hiện.

Quan trọng: đây là quy tắc **kiểm tra sự hiện diện của trường trong payload mẫu để sinh tài liệu**. Nó không tự buộc controller phải trả HTTP 400 khi client gửi thiếu trường, cũng không thay thế `@NotNull`, `@NotBlank`, `@Valid` hoặc các quy tắc nghiệp vụ.

## 3. Dùng `fieldWithPath` và `optional()` đúng cách

Các descriptor của ví dụ trên có thể viết như sau:

```java
import org.springframework.restdocs.payload.FieldDescriptor;
import org.springframework.restdocs.payload.JsonFieldType;

import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

private static final FieldDescriptor[] CUSTOMER_FIELDS = {
        fieldWithPath("fullName")
                .type(JsonFieldType.STRING)
                .description("Họ và tên khách hàng"),

        fieldWithPath("email")
                .type(JsonFieldType.STRING)
                .description("Địa chỉ email hợp lệ"),

        fieldWithPath("address")
                .type(JsonFieldType.OBJECT)
                .description("Địa chỉ liên hệ"),

        fieldWithPath("address.street")
                .type(JsonFieldType.STRING)
                .description("Số nhà và tên đường"),

        fieldWithPath("address.city")
                .type(JsonFieldType.STRING)
                .description("Thành phố"),

        fieldWithPath("address.apartment")
                .type(JsonFieldType.STRING)
                .description("Số căn hộ hoặc tầng")
                .optional(),

        fieldWithPath("phone")
                .type(JsonFieldType.STRING)
                .description("Số điện thoại liên hệ")
                .optional(),

        fieldWithPath("preferences")
                .type(JsonFieldType.OBJECT)
                .description("Các tùy chọn liên lạc")
                .optional(),

        fieldWithPath("preferences.newsletter")
                .type(JsonFieldType.BOOLEAN)
                .description("Có nhận bản tin hay không")
                .optional()
};
```

Trong đoạn này:

1. Những descriptor không có `.optional()` được coi là bắt buộc theo mặc định.
2. `.description(...)` giải thích ý nghĩa của trường cho người đọc tài liệu; nên ghi rõ quy tắc nghiệp vụ khi cần.
3. `.type(JsonFieldType.X)` xác định kiểu hiển thị trong tài liệu. **Đừng dùng `.type(...)` như phép xác thực JSON Schema đầy đủ** hoặc thay thế kiểm thử validation.
4. Với object tùy chọn `preferences`, cả descriptor của **object cha** và của **trường con có thể vắng mặt** đều được đánh dấu `.optional()`.

### 3.1. Quy tắc cho object lồng nhau

Giả sử `address` là bắt buộc nhưng `address.apartment` tùy chọn:

```java
fieldWithPath("address")
        .type(JsonFieldType.OBJECT)
        .description("Địa chỉ liên hệ"),

fieldWithPath("address.city")
        .type(JsonFieldType.STRING)
        .description("Thành phố"),

fieldWithPath("address.apartment")
        .type(JsonFieldType.STRING)
        .description("Số căn hộ")
        .optional()
```

Nếu request thiếu `address`, descriptor `address` và `address.city` không còn dữ liệu phù hợp, nên bài kiểm thử tài liệu hóa phải báo vấn đề. Nếu request có `address` và `address.city` nhưng thiếu `address.apartment`, đó là trường hợp được phép.

Ngược lại, khi một nhánh như `preferences` có thể bị bỏ qua hoàn toàn, chỉ đánh dấu object cha `.optional()` **không bảo đảm** mọi descriptor trường con đều tùy chọn. Mỗi descriptor có tính bắt buộc riêng; hãy xem xét và đánh dấu các đường dẫn con cho đúng hợp đồng.

### 3.2. Quy tắc cho mảng JSON

Xét một request khác có trường `contacts`:

```json
{
  "contacts": [
    { "type": "EMAIL", "value": "an@example.com" },
    { "type": "PHONE", "value": "0900000000", "label": "Cá nhân" }
  ]
}
```

Đường dẫn của trường trong từng phần tử mảng dùng cú pháp `[]`:

```java
fieldWithPath("contacts")
        .type(JsonFieldType.ARRAY)
        .description("Danh sách phương thức liên hệ"),

fieldWithPath("contacts[].type")
        .type(JsonFieldType.STRING)
        .description("Loại phương thức liên hệ"),

fieldWithPath("contacts[].value")
        .type(JsonFieldType.STRING)
        .description("Giá trị liên hệ"),

fieldWithPath("contacts[].label")
        .type(JsonFieldType.STRING)
        .description("Nhãn gợi nhớ")
        .optional()
```

`contacts[].label` là một trường có thể thiếu ở một số phần tử. Tuy nhiên, `.optional()` trên descriptor **không diễn đạt đầy đủ** các quy tắc như “mỗi phần tử phải có `type` và `value`”, “mảng phải chứa ít nhất một phần tử” hoặc “một loại contact chỉ được xuất hiện một lần”. Những điều kiện đó cần DTO validation và các test nghiệp vụ riêng.

Với mảng rỗng, các đường dẫn trường con như `contacts[].type` không có dữ liệu mẫu để quan sát. Hãy dùng một request có phần tử đại diện khi sinh bảng mô tả chi tiết, và viết test riêng cho các trường hợp mảng rỗng/thiếu mảng.

## 4. Ví dụ kiểm thử MockMvc sinh tài liệu từ JSON thực tế

Ví dụ dưới đây sử dụng Spring Boot, JUnit 5 và Spring REST Docs tích hợp MockMvc. Giả định `POST /api/customers` đã tồn tại, chấp nhận JSON theo hợp đồng trên và trả `201 Created` khi request hợp lệ. Dự án cần `spring-boot-starter-test` và `spring-restdocs-mockmvc` trong test dependencies.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.restdocs.payload.FieldDescriptor;
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
class CustomerRequestDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    private static final FieldDescriptor[] CUSTOMER_FIELDS = {
            fieldWithPath("fullName")
                    .type(JsonFieldType.STRING)
                    .description("Họ và tên khách hàng"),
            fieldWithPath("email")
                    .type(JsonFieldType.STRING)
                    .description("Địa chỉ email hợp lệ"),
            fieldWithPath("address")
                    .type(JsonFieldType.OBJECT)
                    .description("Địa chỉ liên hệ"),
            fieldWithPath("address.street")
                    .type(JsonFieldType.STRING)
                    .description("Số nhà và tên đường"),
            fieldWithPath("address.city")
                    .type(JsonFieldType.STRING)
                    .description("Thành phố"),
            fieldWithPath("address.apartment")
                    .type(JsonFieldType.STRING)
                    .description("Số căn hộ hoặc tầng")
                    .optional(),
            fieldWithPath("phone")
                    .type(JsonFieldType.STRING)
                    .description("Số điện thoại liên hệ")
                    .optional(),
            fieldWithPath("preferences")
                    .type(JsonFieldType.OBJECT)
                    .description("Các tùy chọn liên lạc")
                    .optional(),
            fieldWithPath("preferences.newsletter")
                    .type(JsonFieldType.BOOLEAN)
                    .description("Có nhận bản tin hay không")
                    .optional()
    };

    @Test
    void documentCreateCustomerWithSomeOptionalFieldsMissing() throws Exception {
        String requestJson = """
                {
                  "fullName": "Nguyễn Minh An",
                  "email": "an@example.com",
                  "address": {
                    "street": "12 Nguyễn Huệ",
                    "city": "TP. Hồ Chí Minh"
                  },
                  "preferences": {
                    "newsletter": true
                  }
                }
                """;

        mockMvc.perform(post("/api/customers")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(requestJson))
                .andExpect(status().isCreated())
                .andDo(document("customers-create",
                        requestFields(CUSTOMER_FIELDS)));
    }

    @Test
    void documentCreateCustomerWithoutPreferences() throws Exception {
        String requestJson = """
                {
                  "fullName": "Trần Bình",
                  "email": "binh@example.com",
                  "address": {
                    "street": "85 Lê Lợi",
                    "city": "Đà Nẵng"
                  }
                }
                """;

        mockMvc.perform(post("/api/customers")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(requestJson))
                .andExpect(status().isCreated())
                .andDo(document("customers-create-minimal",
                        requestFields(CUSTOMER_FIELDS)));
    }
}
```

Hai test dùng chung bộ descriptor nhưng gửi các biến thể request khác nhau. Test thứ nhất bỏ `phone` và `address.apartment`; test thứ hai bỏ thêm toàn bộ `preferences`. Nếu endpoint thực sự trả `201` và mô tả các trường phù hợp với payload, Spring REST Docs sẽ sinh snippet ở hai thư mục:

```text
build/generated-snippets/
├── customers-create/
│   └── request-fields.adoc
└── customers-create-minimal/
    └── request-fields.adoc
```

Danh sách các tệp khác trong từng thư mục phụ thuộc cấu hình sinh snippet của dự án. Đặt tên tài liệu riêng giúp hai test không ghi đè cùng một bộ kết quả. Bảng trường có thể được đưa vào Asciidoctor bằng:

```adoc
== Tạo khách hàng

=== Các trường của request

include::{snippets}/customers-create/request-fields.adoc[]
```

Biến `{snippets}` phải được cấu hình trỏ đúng tới thư mục `build/generated-snippets`. Khi xuất tài liệu Markdown, cần bộ template hoặc bước chuyển đổi phù hợp; đừng mặc định rằng Spring REST Docs tạo sẵn `request-fields.md`.

**Lưu ý về cột “Bắt buộc”:** `.optional()` ảnh hưởng cách REST Docs đánh giá sự hiện diện của trường khi sinh tài liệu. Việc bảng được sinh có cột “Optional/Required” hay không phụ thuộc template snippet được dùng. Muốn người đọc nhìn thấy rõ, hãy viết mô tả cụ thể hoặc tùy biến template để hiển thị thông tin này.

## 5. Phân biệt trường vắng mặt, `null` và giá trị rỗng

Ba payload sau có ý nghĩa khác nhau:

```json
{
  "fullName": "Nguyễn Minh An",
  "email": "an@example.com",
  "address": { "street": "12 Nguyễn Huệ", "city": "TP. Hồ Chí Minh" }
}
```

```json
{
  "fullName": "Nguyễn Minh An",
  "email": "an@example.com",
  "address": { "street": "12 Nguyễn Huệ", "city": "TP. Hồ Chí Minh" },
  "phone": null
}
```

```json
{
  "fullName": "Nguyễn Minh An",
  "email": "an@example.com",
  "address": { "street": "12 Nguyễn Huệ", "city": "TP. Hồ Chí Minh" },
  "phone": ""
}
```

| Trường hợp | Ý nghĩa của payload | Điều cần xác minh |
| --- | --- | --- |
| Không có khóa `phone` | Client không gửi giá trị | Có được áp dụng giá trị mặc định hay bỏ qua không? |
| Có `"phone": null` | Client gửi khóa với giá trị JSON `null` | API có chấp nhận `null` không? |
| Có `"phone": ""` | Client gửi chuỗi rỗng | API có chấp nhận chuỗi rỗng không? |

`.optional()` dùng để nói rằng **đường dẫn có thể không xuất hiện trong payload mẫu**. Nó không khẳng định API phải chấp nhận mọi giá trị `null`, `""`, `" "` hoặc các kiểu JSON khác. Đó là trách nhiệm của contract, validation và test endpoint.

Với một trường bắt buộc như `email`, “phải có mặt” vẫn chưa đủ: thường còn cần “không rỗng” và “đúng định dạng email”. Chẳng hạn DTO có thể sử dụng Jakarta Bean Validation:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

record CreateCustomerRequest(
        @NotBlank String fullName,
        @NotBlank @Email String email,
        @NotNull @Valid AddressRequest address,
        String phone,
        PreferencesRequest preferences
) {}

record AddressRequest(
        @NotBlank String street,
        @NotBlank String city,
        String apartment
) {}

record PreferencesRequest(Boolean newsletter) {}
```

Đây là **ví dụ minh họa cho điều kiện đầu vào**, không phải phần cấu hình bắt buộc của REST Docs. Controller cần kích hoạt validation phù hợp, ví dụ bằng `@Valid` trên `@RequestBody`. Khi sử dụng DTO này, cần có dependency validation trong dự án. Cũng phải xác định rõ các quy tắc ngoài `@NotBlank`, chẳng hạn số điện thoại có định dạng nào và `newsletter` khi vắng mặt sẽ được xử lý ra sao.

Bạn nên viết kiểm thử riêng cho:

- Thiếu `email` hoặc `address`: endpoint trả lỗi validation theo hợp đồng (thường là HTTP 400 khi được cấu hình đúng).
- `email` rỗng hoặc không đúng định dạng.
- Không có `phone`, `preferences` hoặc `address.apartment`: endpoint vẫn xử lý hợp lệ.
- Có `phone: null` và `phone: ""`: endpoint xử lý theo quy tắc đã công bố.

Những test này kiểm tra **hành vi của API**, còn `requestFields` kiểm tra **mức độ mô tả payload mẫu trong tài liệu**. Kết hợp cả hai mới có hợp đồng request đủ tin cậy.

## 6. Các tình huống dễ gây hiểu nhầm

### 6.1. Trường bắt buộc có điều kiện

Ví dụ quy tắc “nếu `deliveryMethod` là `SHIP`, `shippingAddress` phải có mặt; nếu là `PICKUP`, `shippingAddress` có thể vắng mặt”.

Nếu đặt:

```java
fieldWithPath("shippingAddress")
        .description("Địa chỉ giao hàng")
        .optional()
```

thì Spring REST Docs sẽ cho phép đường dẫn vắng mặt khi tạo snippet, **nhưng không kiểm tra điều kiện `deliveryMethod == SHIP`**. Hãy kiểm tra riêng hai biến thể hợp lệ và biến thể thiếu địa chỉ khi `SHIP`, đồng thời mô tả điều kiện bằng lời hoặc tài liệu dạng bảng. Với API phức tạp, có thể cần schema hoặc quy tắc validation riêng cho từng biến thể.

### 6.2. Một object cha che mất chi tiết của con

Ví dụ:

```java
fieldWithPath("address")
        .description("Địa chỉ liên hệ")
```

Trong một số cách tài liệu hóa, khai báo object ở cấp cha có thể được coi là đã bao phủ các trường con của nó khi kiểm tra trường chưa được mô tả. Vì vậy, chỉ dựa vào việc test không báo lỗi **không chứng minh** rằng mọi trường con đều được giải thích. Khi hợp đồng yêu cầu chi tiết, hãy khai báo `address.street`, `address.city`, `address.apartment` như ví dụ chính.

Nếu muốn cố ý trình bày cả nhánh dưới một hàng tài liệu, có thể dùng `subsectionWithPath("address")`; lúc đó cần tài liệu khác giải thích các trường con nếu người dùng API cần biết.

### 6.3. `ignored()` và `relaxedRequestFields(...)` không đồng nghĩa với tùy chọn

```java
fieldWithPath("internalTrace")
        .description("Mã theo dõi kỹ thuật")
        .ignored()
```

`ignored()` nghĩa là trường đã được nhận diện nhưng **không đưa vào bảng mô tả**, phù hợp khi một trường kỹ thuật không cần công bố. Nó không tự tuyên bố trường đó có thể vắng mặt theo hợp đồng API.

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.relaxedRequestFields;

relaxedRequestFields(
        fieldWithPath("email").description("Email khách hàng"),
        fieldWithPath("phone").description("Số điện thoại").optional()
)
```

`relaxedRequestFields(...)` cho phép request mẫu có **các trường chưa được tài liệu hóa**. Nó vẫn yêu cầu các descriptor bắt buộc đã khai báo xuất hiện trong payload. Ngược lại, `optional()` chỉ thay đổi yêu cầu hiện diện **của đúng descriptor đó**. Với tài liệu API công khai cần nắm đầy đủ các trường, ưu tiên `requestFields(...)` chặt chẽ.

### 6.4. “Bắt buộc” trong tài liệu không có nghĩa là “không thể `null`”

Không nên suy luận từ `fieldWithPath("email")` rằng request có `email: null` chắc chắn bị server từ chối. Hành vi đó cần được quyết định ở tầng DTO/validation và được kiểm thử. Khi mô tả hợp đồng, ghi rõ các điều kiện như “bắt buộc, chuỗi không rỗng, đúng định dạng email”, thay vì chỉ để người đọc suy đoán từ tên trường.

## 7. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể gặp | Cách xử lý |
| --- | --- | --- |
| Test sinh snippet báo thiếu `phone` | Quên `.optional()` cho trường mà request mẫu không gửi | Xác nhận hợp đồng và thêm `.optional()` nếu thực sự tùy chọn |
| Test báo thiếu `preferences.newsletter` | Object `preferences` tùy chọn, nhưng descriptor trường con vẫn bắt buộc | Đánh dấu `.optional()` cho các descriptor con có thể vắng mặt |
| Thêm `nickname` vào JSON làm test thất bại | `requestFields(...)` chặt chẽ phát hiện trường chưa tài liệu hóa | Thêm descriptor và mô tả trạng thái bắt buộc/tùy chọn |
| Test mô tả thành công nhưng API vẫn chấp nhận thiếu `email` | Chưa triển khai validation hoặc kiểm tra nghiệp vụ tương ứng | Thêm validation và test HTTP cho trường bắt buộc |
| Bảng không có cột bắt buộc/tùy chọn | Template snippet đang dùng không hiển thị thuộc tính `optional` | Mô tả rõ trong `description(...)` hoặc tùy biến template |
| Request mẫu có mảng rỗng, khó xác minh trường con | Không có phần tử đại diện cho các đường dẫn như `items[].sku` | Tạo test dữ liệu có phần tử và test rỗng riêng |
| Test HTTP chạy được nhưng không sinh `request-fields.adoc` | Thiếu `document(..., requestFields(...))` hoặc cấu hình REST Docs | Kiểm tra tích hợp test, tên snippet và `outputDir` |

Các lỗi liên quan trường thiếu hoặc chưa tài liệu hóa thường phát sinh ở bước sinh snippet trong quá trình chạy test. Vì thế, CI nên chạy test tài liệu hóa trước khi kết xuất Asciidoctor. Trường hợp `requestFields` báo lỗi là cơ hội để đối chiếu hợp đồng API với DTO và request thực tế, tránh khắc phục bằng cách nới lỏng toàn bộ việc kiểm tra một cách vô thức.

## 8. Thực hành tự kiểm chứng

Hãy mở rộng API tạo khách hàng:

1. Thêm `referralCode` kiểu String, **tùy chọn**. Thêm descriptor với `.optional()`, nhưng không thêm trường này vào request mẫu. Chạy test và xác nhận việc sinh snippet thành công.
2. Gửi thêm `referralCode` trong request mẫu. Chạy test lần nữa và kiểm tra cùng một bộ descriptor vẫn dùng được.
3. Đổi hợp đồng để `address.postalCode` là **bắt buộc**. Thêm descriptor không có `.optional()` nhưng cố tình bỏ trường này khỏi request mẫu. Quan sát test tài liệu hóa thất bại, sau đó thêm dữ liệu đúng để test vượt qua.
4. Tạo test gửi `email: ""` hoặc thiếu `email` để kiểm tra API từ chối đầu vào theo ràng buộc validation, thay vì chỉ trông chờ `requestFields`.
5. Chèn snippet `customers-create/request-fields.adoc` vào Asciidoctor và xác nhận thông tin tùy chọn hiển thị rõ ràng theo template/mô tả của dự án.

**Tiêu chí hoàn thành:** Bạn chỉ sử dụng `.optional()` cho các trường được phép vắng mặt trong hợp đồng; với các trường bắt buộc, bài kiểm thử tài liệu hóa thể hiện sự hiện diện của chúng; các điều kiện như không rỗng, đúng định dạng hoặc bắt buộc có điều kiện được kiểm tra bằng những test API phù hợp. Bảng request payload được sinh lại trong build mỗi khi API thay đổi.
