# Tránh mô tả thiếu khi subsection thay đổi cấu trúc trong Spring REST Docs

## 1. Vấn đề: bảng tổng quan có thể vẫn xanh khi schema con đã đổi

**Spring REST Docs** tạo tài liệu REST API có thể kiểm chứng từ các bài kiểm thử HTTP bằng **MockMvc**, **WebTestClient** hoặc **REST Assured**. Khi test thực thi thành công, thư viện sinh snippet mô tả request, response, payload, header và tham số. Các snippet được biên soạn thành tài liệu Asciidoctor/Markdown và đưa vào build, CI.

Khi payload có object lớn hoặc mảng lồng nhau, `subsectionWithPath(...)` giúp bảng field tổng quan ngắn gọn. Nhưng có một rủi ro quan trọng: descriptor subsection xem **các field hậu duệ của nhánh đó là đã được document trong snippet hiện tại**. Nếu một field mới xuất hiện bên trong nhánh, bảng tổng quan có thể vẫn pass dù tài liệu chưa giải thích field mới.

Ví dụ, bảng response chỉ khai báo:

```java
responseFields(
    fieldWithPath("id").description("Mã đơn hàng"),
    subsectionWithPath("payment")
        .description("Kết quả xử lý thanh toán")
)
```

Nếu response bổ sung `payment.providerCode` hoặc `payment.refundState`, bảng tổng quan có thể vẫn hợp lệ do toàn bộ nhánh `payment` đã được bao phủ. Người tích hợp API có thể không biết contract vừa thay đổi.

Bài học này trình bày cách tránh thiếu mô tả khi subsection thay đổi bằng cách:

- phân biệt bảng cha và bảng schema chi tiết;
- tạo snippet strict cho những subsection quan trọng;
- kiểm tra kiểu JSON, path và các quy tắc nghiệp vụ bằng assertion riêng;
- tổ chức test cho field optional, nhánh vắng mặt, mảng rỗng và cấu trúc biến thể;
- dùng CI để buộc tài liệu được cập nhật cùng thay đổi API.

## 2. Hiểu đúng ranh giới kiểm tra của subsection

Giả sử `GET /orders/ord-650` trả response:

```json
{
  "id": "ord-650",
  "status": "PAID",
  "payment": {
    "method": "CARD",
    "state": "CAPTURED",
    "amount": {
      "value": 820000,
      "currency": "VND"
    },
    "card": {
      "brand": "VISA",
      "last4": "4242"
    }
  },
  "delivery": {
    "recipient": "Mai Le",
    "address": {
      "city": "Can Tho",
      "country": "VN"
    }
  }
}
```

Một bảng tổng quan có thể được khai báo:

```java
responseFields(
    fieldWithPath("id").description("Mã đơn hàng"),
    fieldWithPath("status").description("Trạng thái đơn hàng"),
    subsectionWithPath("payment")
        .description("Kết quả xử lý thanh toán"),
    subsectionWithPath("delivery")
        .description("Thông tin giao hàng")
)
```

Bảng có bốn hàng. Nó kiểm tra field cấp gốc được mô tả, bao gồm sự hiện diện của các nhánh bắt buộc. Nhưng nó không yêu cầu liệt kê từng hậu duệ như `payment.method`, `payment.amount.value` hay `payment.card.last4`.

Phân biệt:

| Descriptor | Ranh giới được mô tả | Thay đổi có thể chưa bị phát hiện bởi snippet này |
| --- | --- | --- |
| `fieldWithPath("id")` | Một field cụ thể | Field mới ở các path khác vẫn cần descriptor |
| `subsectionWithPath("payment")` | Toàn bộ nhánh payment và các hậu duệ | Field con mới bên trong payment |
| `subsectionWithPath("delivery.address")` | Nhánh address trong delivery | Field mới nằm dưới delivery.address |
| `responseFields(beneathPath("payment"), ...)` | Các field được khai báo trong snippet chi tiết payment | Field con mới trong phạm vi payment nếu chưa có descriptor phù hợp |
| `responseBody(beneathPath("payment"))` | Body được trích từ payment | Bản thân body snippet không kiểm tra tính đầy đủ schema |

Một test pass chỉ chứng minh các descriptor trong **snippet đó** tương thích với payload theo quy tắc của REST Docs. Nó không chứng minh rằng mọi nhánh con đều đã được mô tả ở nơi khác.

## 3. Chiến lược hai tầng: tổng quan và schema chi tiết

Đối với các subsection quan trọng, nên có hai bảng với hai mục đích:

**Bảng tổng quan** cho người đọc biết response gồm những nhóm dữ liệu nào và nhóm có ý nghĩa gì. `subsectionWithPath` phù hợp ở đây.

**Bảng chi tiết strict** liệt kê field trong subsection để phát hiện thay đổi schema. Dùng `responseFields(beneathPath(...), ...)` với descriptor chi tiết.

Ví dụ bảng payment:

```java
responseFields(
    beneathPath("payment").withSubsectionId("payment"),
    fieldWithPath("method")
        .description("Phương thức thanh toán"),
    fieldWithPath("state")
        .description("Trạng thái giao dịch thanh toán"),
    fieldWithPath("amount.value")
        .description("Giá trị số tiền"),
    fieldWithPath("amount.currency")
        .description("Mã đơn vị tiền tệ"),
    fieldWithPath("card.brand")
        .description("Thương hiệu thẻ"),
    fieldWithPath("card.last4")
        .description("Bốn chữ số cuối của thẻ")
)
```

Các đường dẫn tính từ gốc subsection đã trích. Trong bảng payment, dùng `amount.value` thay cho `payment.amount.value`. Bảng này strict trong phạm vi payment: nếu response thêm `payment.providerCode` mà chưa có descriptor, test có thể thất bại và yêu cầu cập nhật tài liệu.

Nếu một field con lại là một object lớn cần được quản lý riêng, có thể dùng subsection ở cấp sâu hơn hoặc tạo bảng riêng cho nhánh đó. Hãy chọn ranh giới sao cho không còn khoảng trống giữa bảng tổng quan và các bảng chi tiết mà contract cần bảo vệ.

### 3.1. Mỗi nhánh quan trọng nên có người chịu trách nhiệm

Không phải mọi object đều cần một bảng chi tiết. Một nhánh nhỏ, ổn định hoặc nội bộ có thể được giải thích ở mức tổng quan. Nhưng những nhánh ảnh hưởng tới tích hợp, tiền tệ, xác thực, quyền truy cập, trạng thái xử lý hay dữ liệu người dùng thường cần kiểm tra chi tiết.

Bảng phân công minh họa:

| Nhánh | Tài liệu nên có | Lý do |
| --- | --- | --- |
| `payment` | Bảng chi tiết strict | Thay đổi field có thể ảnh hưởng đối soát hoặc trạng thái thanh toán |
| `delivery` | Bảng chi tiết strict | Người tích hợp cần biết người nhận và địa chỉ |
| `metadata` nội bộ | Có thể chỉ dùng subsection tổng quan | Không phải mọi key nội bộ đều thuộc contract công khai |
| `items[]` | Bảng field trong từng phần tử | Client cần biết SKU, số lượng và giá |
| `audit` | Tùy phạm vi công khai | Có thể cần một tài liệu riêng nếu endpoint công bố dữ liệu audit |

Đây là quyết định thiết kế tài liệu dựa trên contract; không phải mọi subsection đều cần tạo snippet chi tiết chỉ để làm số lượng file tăng lên.

## 4. Ví dụ MockMvc: test tổng quan và test chi tiết

Ví dụ dùng JUnit 5, Java 17+, Spring MVC Test và Spring REST Docs. Controller mẫu trả JSON cố định để minh họa sinh snippet; trong dự án thực tế, thay bằng controller và fixture của ứng dụng.

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
class OrderSubsectionContractTest {

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
        mockMvc.perform(get("/orders/{id}", "ord-650")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("ord-650"))
                .andExpect(jsonPath("$.payment").isMap())
                .andDo(document("orders-get-overview",
                        responseFields(
                                fieldWithPath("id")
                                        .description("Mã đơn hàng"),
                                fieldWithPath("status")
                                        .description("Trạng thái đơn hàng"),
                                subsectionWithPath("payment")
                                        .description("Kết quả xử lý thanh toán"),
                                subsectionWithPath("delivery")
                                        .description("Thông tin giao hàng")
                        )
                ));
    }

    @Test
    void documentPaymentContract() throws Exception {
        mockMvc.perform(get("/orders/{id}", "ord-650")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.payment.method").value("CARD"))
                .andExpect(jsonPath("$.payment.amount.value").isNumber())
                .andExpect(jsonPath("$.payment.card.last4").value("4242"))
                .andDo(document("orders-get-payment",
                        responseFields(
                                beneathPath("payment")
                                        .withSubsectionId("payment"),
                                fieldWithPath("method")
                                        .description("Phương thức thanh toán"),
                                fieldWithPath("state")
                                        .description("Trạng thái giao dịch"),
                                fieldWithPath("amount.value")
                                        .description("Giá trị số tiền"),
                                fieldWithPath("amount.currency")
                                        .description("Mã tiền tệ"),
                                fieldWithPath("card.brand")
                                        .description("Thương hiệu thẻ"),
                                fieldWithPath("card.last4")
                                        .description("Bốn chữ số cuối của thẻ")
                        ),
                        responseBody(
                                beneathPath("payment")
                                        .withSubsectionId("payment")
                        )
                ));
    }

    @RestController
    static class SampleOrderController {

        @GetMapping(value = "/orders/{id}",
                    produces = MediaType.APPLICATION_JSON_VALUE)
        ResponseEntity<String> getOrder(@PathVariable("id") String id) {
            if (!"ord-650".equals(id)) {
                return ResponseEntity.notFound().build();
            }

            String json = """
                    {
                      "id": "ord-650",
                      "status": "PAID",
                      "payment": {
                        "method": "CARD",
                        "state": "CAPTURED",
                        "amount": {
                          "value": 820000,
                          "currency": "VND"
                        },
                        "card": {
                          "brand": "VISA",
                          "last4": "4242"
                        }
                      },
                      "delivery": {
                        "recipient": "Mai Le",
                        "address": {
                          "city": "Can Tho",
                          "country": "VN"
                        }
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

Hai test có hai identifier riêng vì chúng sinh bộ snippet độc lập:

- `orders-get-overview`: bảng tổng quan và các subsection.
- `orders-get-payment`: bảng schema chi tiết và body của payment.

Trong dự án có thể dùng cùng một identifier nếu đã thiết kế một test/document operation duy nhất với các handler và tên snippet không trùng. Ví dụ trên tách identifier để làm rõ ranh giới kiểm thử; không nên để hai test không liên quan cùng ghi vào một file snippet có tên giống nhau.

## 5. Thử nghiệm schema drift: thêm field mới trong subsection

Giả sử API bổ sung:

```json
{
  "payment": {
    "providerCode": "BANK-X"
  }
}
```

Nếu chỉ chạy test tổng quan `orders-get-overview` với `subsectionWithPath("payment")`, field con mới có thể không khiến snippet đó thất bại. Đây chính là khoảng trống cần kiểm soát.

Khi chạy test chi tiết `orders-get-payment`, bảng strict chỉ khai báo `method`, `state`, `amount.value`, `amount.currency`, `card.brand` và `card.last4`. Vì `providerCode` xuất hiện dưới payment nhưng chưa được mô tả, test chi tiết có thể thất bại và buộc nhóm cập nhật contract.

Quy trình xử lý thay đổi:

1. Xác định field mới có thuộc API contract công khai hay chỉ là chi tiết nội bộ.
2. Nếu công khai, thêm descriptor `fieldWithPath("providerCode")` vào bảng payment với mô tả ý nghĩa.
3. Cập nhật ví dụ payload hoặc tài liệu nghiệp vụ liên quan.
4. Nếu cần, thêm assertion cho định dạng/giá trị của field; descriptor chỉ xác nhận cấu trúc tài liệu, không thay thế kiểm thử nghiệp vụ.
5. Chạy lại test và dựng tài liệu để các snippet được cập nhật cùng thay đổi.

Nếu field mới không thuộc contract công khai, cần có quyết định rõ ràng về cách xử lý; có thể dùng `ignored()` cho một field đã biết và có chủ đích loại khỏi bảng. Không sử dụng `ignored()` như một cách né việc cập nhật tài liệu.

## 6. Đừng chỉ dựa vào field documentation để kiểm tra kiểu và giá trị

Field documentation giúp xác minh path và việc mô tả field. Nó không thay thế mọi assertion cần thiết về schema runtime và nghiệp vụ.

Ví dụ `fieldWithPath("amount.value")` không tự đảm bảo đơn vị là đồng Việt Nam, không xác nhận số tiền luôn dương và không chứng minh tổng tiền được tính đúng. Hãy kết hợp:

```java
.andExpect(jsonPath("$.payment.amount.value").isNumber())
.andExpect(jsonPath("$.payment.amount.currency").value("VND"))
.andExpect(jsonPath("$.payment.card.last4").value(org.hamcrest.Matchers.matchesPattern("\\d{4}")))
```

Các assertion này kiểm tra kiểu/value quan trọng cho fixture cụ thể. Nếu cần kiểm tra điều kiện như số tiền dương, có thể dùng matcher phù hợp hoặc giải mã response thành object rồi assert quy tắc nghiệp vụ. Đừng làm cho tài liệu mô tả một contract chặt hơn hành vi được API bảo đảm.

### 6.1. Kiểm tra object vẫn là object

Một response thay đổi `payment` từ object thành một chuỗi hoặc mảng không tương đương với contract trước đó. Có thể dùng assertion JSON để kiểm tra `payment` là object, đồng thời dùng bảng field để xác minh các path cụ thể.

### 6.2. Kiểm tra mảng và phần tử

Với subsection `items` là mảng object, tài liệu chi tiết có thể dùng `items[].sku` và `items[].quantity`. Nhưng cần assertion riêng về:

- số lượng phần tử nếu API quy định;
- mỗi item có SKU hợp lệ;
- quantity phải thỏa miền giá trị;
- các field lồng như pricing có đúng kiểu và đơn vị;
- thứ tự phần tử nếu thứ tự là một phần của contract.

`subsectionWithPath("items")` không xác nhận các điều kiện trên.

## 7. Tránh lỗ hổng khi subsection có cấu trúc optional hoặc biến thể

### 7.1. Field optional trong một subsection

Nếu `payment.transactionReference` chỉ xuất hiện sau khi giao dịch được tạo, khai báo:

```java
fieldWithPath("transactionReference")
    .optional()
    .description("Mã tham chiếu khi giao dịch đã được tạo")
```

`optional()` cho phép field vắng mặt trong ca test; nó không có nghĩa field có thể có bất kỳ kiểu hoặc nội dung nào.

Nên có test cho cả hai trạng thái: có mã tham chiếu và chưa có mã tham chiếu, nếu đó là hai trạng thái hợp lệ trong contract. Snippet tài liệu cần thể hiện rõ trường có thể vắng mặt.

### 7.2. Toàn bộ subsection có thể vắng mặt

Nếu `payment` không tồn tại đối với đơn hàng chưa thanh toán, descriptor cha có thể dùng:

```java
subsectionWithPath("payment")
    .optional()
    .description("Thông tin thanh toán nếu đơn hàng đã khởi tạo giao dịch")
```

Test chi tiết `beneathPath("payment")` cần payload thực sự có payment để trích và document. Không nên dùng extractor này trong test của biến thể response không có nhánh. Thay vào đó:

- test có payment: sinh snippet body và bảng chi tiết;
- test chưa có payment: xác minh response theo contract, không gọi extractor của nhánh vắng mặt.

### 7.3. Mảng rỗng

`"items": []` khác với không có key `items`. Nếu bảng chi tiết mô tả `items[].sku` và `items[].quantity`, fixture mảng rỗng không có phần tử để đối chiếu các field đó. Dùng một test có ít nhất một item để sinh snippet schema và một test riêng xác minh mảng rỗng nếu API cho phép.

### 7.4. Cấu trúc union hoặc nhiều biến thể

Một subsection có thể thay đổi shape theo loại giao dịch. Ví dụ `payment.method` là `CARD` có `card.last4`, còn `BANK_TRANSFER` có `bankReference`. Không nên gom hai cấu trúc khác nhau vào một bảng field giả định mọi path luôn có mặt.

Có thể tổ chức:

- một bảng tổng quan cho `payment`;
- bảng chi tiết cho từng biến thể hoặc discriminator;
- test có dữ liệu cho từng biến thể;
- descriptor optional chỉ khi field thật sự optional trong contract chung.

Nếu API định nghĩa rõ discriminator, tài liệu phải giải thích cách người dùng chọn bảng/shape phù hợp.

## 8. Áp dụng cho request subsection

Rủi ro thiếu mô tả cũng xuất hiện ở request. Giả sử `POST /orders` nhận:

```json
{
  "customerId": "cus-25",
  "delivery": {
    "recipient": "Mai Le",
    "address": {
      "city": "Can Tho",
      "country": "VN"
    },
    "instructions": "Gọi khi đến nơi"
  },
  "items": [
    {
      "sku": "BK-101",
      "quantity": 1
    }
  ]
}
```

Bảng request tổng quan:

```java
requestFields(
    fieldWithPath("customerId")
        .description("Mã khách hàng"),
    subsectionWithPath("delivery")
        .description("Thông tin phục vụ việc giao đơn"),
    subsectionWithPath("items")
        .description("Các dòng hàng trong đơn")
)
```

Bảng request chi tiết của delivery:

```java
requestFields(
    beneathPath("delivery").withSubsectionId("delivery"),
    fieldWithPath("recipient")
        .description("Người nhận"),
    fieldWithPath("address.city")
        .description("Thành phố giao hàng"),
    fieldWithPath("address.country")
        .description("Mã quốc gia"),
    fieldWithPath("instructions")
        .optional()
        .description("Hướng dẫn bổ sung cho việc giao hàng")
)
```

Bảng tổng quan không phát hiện mọi field mới trong `delivery`. Bảng detail strict sẽ phát hiện field mới chưa được mô tả. Với request, nên kiểm tra thêm validation nghiệp vụ như customer tồn tại, SKU hợp lệ, quantity dương và địa chỉ bắt buộc.

## 9. Tên snippet và biên soạn tài liệu

Giả sử operation identifier `orders-get-payment` và subsection ID `payment`, các snippet quan trọng nằm dưới `build/generated-snippets/orders-get-payment/`:

| Tệp | Nội dung |
| --- | --- |
| `response-fields-payment.adoc` | Bảng field payment đã kiểm tra |
| `response-body-payment.adoc` | Body payment được trích |
| `http-response.adoc` | HTTP response đầy đủ nếu test có sinh snippet mặc định |

Một trang Asciidoctor có thể nhúng:

```asciidoc
== GET /orders/{id}

=== Response tổng quan

include::{snippets}/orders-get-overview/response-fields.adoc[]

=== Hợp đồng payment

payment là kết quả xử lý thanh toán gắn với đơn hàng.
Các field và ví dụ JSON được trích từ cùng response của ca kiểm thử.

include::{snippets}/orders-get-payment/response-body-payment.adoc[]
include::{snippets}/orders-get-payment/response-fields-payment.adoc[]
```

Phần văn bản "payment là kết quả..." được viết thủ công để giải thích ý nghĩa. Snippet chỉ mang dữ liệu và bảng descriptor.

Nếu tài liệu dùng nhiều trang, chuyển phần chi tiết vào trang Payment rồi liên kết từ trang Order bằng anchor/xref của hệ thống xuất bản. Build phải biên soạn cả trang chính và trang chi tiết để phát hiện snippet/include thiếu.

## 10. Tích hợp Gradle và CI để phát hiện tài liệu thiếu

Với dự án đã cấu hình plugin Asciidoctor và dependency Spring REST Docs, có thể ràng buộc build như sau (Groovy DSL):

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

Trong CI, nên bảo đảm:

1. Test tổng quan và test subsection chi tiết đều chạy.
2. Asciidoctor chạy sau các test sinh snippet.
3. Các file `include` dùng đúng operation identifier và subsection ID.
4. Không lấy snippet cũ từ lần build trước làm tài liệu cho API mới.
5. Khi bảng strict fail, yêu cầu người thay đổi schema cập nhật descriptor, văn bản và ví dụ liên quan.

Với Maven, thư mục snippet thường là `target/generated-snippets`; cần cấu hình plugin để bước dựng tài liệu phụ thuộc vào test. Nếu dùng Markdown, chọn template và bước ghép Markdown phù hợp với pipeline dự án.

### 10.1. Những gì CI kiểm tra được và chưa kiểm tra được

| Kiểm tra | REST Docs/build có thể hỗ trợ? | Cần bổ sung |
| --- | --- | --- |
| Field mới ngoài subsection đã document | Có, bảng strict cấp cha | Bổ sung descriptor |
| Field mới trong subsection được bao phủ ở bảng cha | Chỉ khi có snippet chi tiết strict | Bảng detail cho subsection |
| JSON path bắt buộc bị thiếu | Có, descriptor không optional | Xem xét contract/optional |
| Giá trị số tiền tính đúng | Không chỉ từ field descriptor | Assertion nghiệp vụ |
| Link tới trang con tồn tại | Build tài liệu có thể phát hiện include file thiếu | Kiểm tra xref/anchor nếu pipeline không kiểm tra |
| Ý nghĩa nghiệp vụ trong Description chính xác | Không thể tự xác nhận | Review nội dung/QA |
| Ví dụ không chứa dữ liệu nhạy cảm | Không tự bảo đảm | Fixture giả và kiểm tra dữ liệu |

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Thêm field con nhưng test vẫn pass | Chỉ có `subsectionWithPath` ở bảng cha | Tạo bảng strict bằng `beneathPath` |
| Bảng chi tiết báo field chưa document | Payload có field mới hoặc descriptor không đầy đủ | Xác định field có thuộc contract; thêm descriptor hoặc xử lý rõ ràng |
| Bảng chi tiết báo thiếu field bắt buộc | Field vắng mặt hoặc path sai | Đối chiếu response và dùng `optional()` chỉ khi contract cho phép |
| Không trích được subsection | Nhánh không có trong fixture hoặc path sai | Sinh snippet từ test có nhánh; test biến thể vắng mặt riêng |
| Snippet body có nhưng không có bảng field | Chỉ gọi `responseBody(...)` | Thêm `responseFields(...)` để document schema |
| Assertion pass nhưng tài liệu schema thiếu field | Assertion chỉ kiểm tra một số giá trị | Bổ sung descriptor strict cho toàn bộ phạm vi cần bảo vệ |
| Bảng strict pass dù field mới đã biết nhưng không công khai | Descriptor dùng `ignored()` có chủ ý | Ghi nhận quyết định và lý do trong tài liệu/review |
| Field mới bị bỏ qua vì dùng relaxed | `relaxedResponseFields` không kiểm tra field chưa mô tả | Dùng strict khi cần bắt schema drift |
| Tài liệu CI khác kết quả local | Dữ liệu test không ổn định hoặc snippet cũ | Dùng fixture cố định, clean output và kiểm tra task dependency |

## 12. Bài thực hành

Dùng `OrderSubsectionContractTest` ở mục 4 và thực hiện:

1. **Thay đổi field trong payment:** thêm `providerCode` vào JSON controller. Xác minh test tổng quan có thể vẫn pass, còn test chi tiết strict phát hiện field mới.
2. **Cập nhật contract:** thêm descriptor `fieldWithPath("providerCode")` vào bảng payment, mô tả ý nghĩa và chạy lại.
3. **Thay đổi kiểu:** đổi `payment.amount.value` từ số sang chuỗi. Viết assertion kiểm tra kiểu số và quan sát test phát hiện thay đổi.
4. **Field optional:** loại `payment.transactionReference` khỏi response fixture. Thêm descriptor `optional()` nếu contract cho phép; thử bỏ optional để so sánh.
5. **Subsection vắng mặt:** tạo response chưa khởi tạo payment. Viết test riêng kiểm tra response và không gọi extractor payment trong test đó.
6. **Mảng rỗng:** tạo response có `items: []`. Tách test kiểm tra mảng rỗng khỏi test sinh bảng schema của các phần tử.
7. **CI:** chạy `./gradlew clean test asciidoctor` trong dự án đã cấu hình, xác nhận cả snippet tổng quan và chi tiết được sinh và được nhúng.

**Tiêu chí hoàn thành:** giải thích được vì sao bảng cha có thể pass khi field con đổi, tạo được bảng strict cho subsection quan trọng, chọn đúng trường hợp optional/biến thể, và thiết lập build để phát hiện tài liệu thiếu khi contract thay đổi.

## 13. Câu hỏi tự kiểm tra

**1. Tại sao `subsectionWithPath("payment")` có thể che khuất field mới?**

Vì descriptor đó bao phủ toàn bộ nhánh payment và các hậu duệ trong snippet hiện tại. Bảng cha không liệt kê riêng từng field con.

**2. Cách nào giúp phát hiện field con mới?**

Tạo bảng strict bằng `responseFields(beneathPath("payment"), ...)` và liệt kê các field mà contract yêu cầu document.

**3. `responseBody(beneathPath("payment"))` có kiểm tra đủ schema không?**

Không. Nó trích body; bảng field strict mới kiểm soát việc document các field.

**4. Có nên đánh dấu tất cả field là optional để test không fail?**

Không. `optional()` phải phản ánh contract thật. Lạm dụng nó làm tài liệu mất khả năng phát hiện field bắt buộc bị thiếu.

**5. Khi subsection vắng mặt thì sao?**

Dùng test riêng cho biến thể không có subsection. Snippet chi tiết dùng `beneathPath` nên được sinh từ test có nhánh cần trích.

## Tài liệu tham khảo

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html): field/subsection descriptors, path, optional fields và relaxed documentation.
- [Spring REST Docs — Reference Documentation](https://docs.spring.io/spring-restdocs/reference/): cấu hình test, snippet, Asciidoctor và tích hợp build.

