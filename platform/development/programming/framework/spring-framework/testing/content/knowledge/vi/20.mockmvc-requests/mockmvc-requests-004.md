# Body JSON, XML và nội dung nhị phân

## 1. Request body trong MockMvc

Khi kiểm thử một endpoint nhận dữ liệu trong HTTP request body, MockMvc cho phép đặt nội dung body trực tiếp vào request được dựng bằng `MockHttpServletRequestBuilder`. Hai phương thức thường dùng là:

- `content(String)`: truyền nội dung dạng chuỗi, phù hợp với JSON hoặc XML viết trực tiếp trong test.
- `content(byte[])`: truyền mảng byte, phù hợp với dữ liệu đã được serialize hoặc payload nhị phân như ảnh, tệp và dữ liệu giao thức riêng.

Một request có body thường cần khai báo `Content-Type` để Spring MVC biết định dạng dữ liệu gửi lên. Có thể khai báo định dạng response mong muốn bằng header `Accept`.

```java
mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
                {"customerId":"C-100","quantity":2}
                """))
    .andExpect(status().isCreated());
```

Trong ví dụ, `Content-Type` mô tả body của request; `Accept` mô tả kiểu nội dung client muốn nhận trong response. Hai header có mục đích khác nhau. Nếu endpoint chỉ nhận JSON nhưng test gửi `application/xml`, Spring MVC có thể trả về `415 Unsupported Media Type`. Nếu endpoint không thể tạo response thuộc kiểu mà `Accept` yêu cầu, kết quả có thể là `406 Not Acceptable`.

Các ví dụ trong bài giả định `mockMvc` đã được cấu hình. Có thể lấy đối tượng này từ `@AutoConfigureMockMvc` trong Spring Boot test, từ `MockMvcBuilders.webAppContextSetup(...)`, hoặc dựng bằng `MockMvcBuilders.standaloneSetup(...)` khi chỉ cần kiểm thử một controller.

## 2. Gửi JSON body

JSON là định dạng phổ biến cho API HTTP. Controller Spring MVC thường nhận JSON bằng `@RequestBody`; một `HttpMessageConverter` sẽ đọc byte của request và chuyển JSON thành Java object.

Ví dụ endpoint nhận yêu cầu tạo đơn hàng:

```java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest request) {
        OrderResponse response = new OrderResponse("O-100", request.customerId());
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}

record CreateOrderRequest(String customerId, int quantity) {}

record OrderResponse(String orderId, String customerId) {}
```

Có thể gửi JSON literal để kiểm soát chính xác nội dung wire format:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "customerId": "C-100",
                  "quantity": 2
                }
                """))
    .andExpect(status().isCreated())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.orderId").value("O-100"))
    .andExpect(jsonPath("$.customerId").value("C-100"));
```

`jsonPath` kiểm tra cấu trúc và giá trị trong JSON response. Biểu thức `$.orderId` đi từ phần tử gốc đến thuộc tính `orderId`. Có thể kiểm tra phần tử mảng, giá trị số, boolean, thuộc tính lồng nhau hoặc sự tồn tại của một trường bằng các biểu thức JSONPath tương ứng.

Nếu đã có request DTO, test cũng có thể dùng `ObjectMapper` của ứng dụng để serialize object:

```java
CreateOrderRequest request = new CreateOrderRequest("C-100", 2);

mockMvc.perform(post("/api/orders")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.APPLICATION_JSON)
        .content(objectMapper.writeValueAsBytes(request)))
    .andExpect(status().isCreated());
```

`writeValueAsBytes` tạo byte array UTF-8 phù hợp để gửi vào `content(byte[])`. Dùng `ObjectMapper` đã cấu hình trong application context giúp test tuân theo các thiết lập serializer của ứng dụng như naming strategy, custom module và định dạng ngày giờ. Khi muốn kiểm tra chính xác tên trường, kiểu dữ liệu hoặc payload mà một client thực sự gửi, JSON literal thường làm ý định của test rõ hơn.

Nên đặt `Content-Type` rõ ràng trong test. Nếu body không có kiểu nội dung phù hợp với mapping `consumes` hoặc converter có thể đọc kiểu Java đích, request có thể không được xử lý như mong muốn.

## 3. Gửi XML body

MockMvc gửi XML theo cách tương tự JSON: đặt `Content-Type` thành `application/xml` và truyền nội dung XML bằng `content(...)`. Để bảo đảm encoding nhất quán, có thể chuyển chuỗi thành byte UTF-8 một cách tường minh.

```java
import java.nio.charset.StandardCharsets;

String xml = """
        <order>
            <customerId>C-100</customerId>
            <quantity>2</quantity>
        </order>
        """;

mockMvc.perform(post("/api/orders/xml")
        .contentType(MediaType.APPLICATION_XML)
        .accept(MediaType.APPLICATION_XML)
        .content(xml.getBytes(StandardCharsets.UTF_8)))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_XML));
```

Nếu controller nhận `@RequestBody String`, Spring có thể chuyển body thành chuỗi để ứng dụng tự xử lý. Nếu controller nhận một DTO Java, ứng dụng cần một `HttpMessageConverter` hỗ trợ XML và kiểu DTO đó. Ví dụ, `MappingJackson2XmlHttpMessageConverter` dùng Jackson XML; thư viện `jackson-dataformat-xml` phải có trên classpath và converter phải được đăng ký trong MVC configuration. Spring Boot có thể cấu hình converter tương ứng khi dependency này hiện diện. Một lựa chọn khác là converter dựa trên JAXB nếu ứng dụng đã dùng JAXB.

Ví dụ mapping XML thành DTO với Jackson XML:

```java
import com.fasterxml.jackson.dataformat.xml.annotation.JacksonXmlRootElement;

@JacksonXmlRootElement(localName = "order")
public class XmlOrderRequest {

    private String customerId;
    private int quantity;

    public XmlOrderRequest() {
    }

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public int getQuantity() {
        return quantity;
    }

    public void setQuantity(int quantity) {
        this.quantity = quantity;
    }
}
```

Controller có thể khai báo:

```java
@PostMapping(path = "/api/orders/xml",
             consumes = MediaType.APPLICATION_XML_VALUE,
             produces = MediaType.APPLICATION_XML_VALUE)
ResponseEntity<XmlOrderResponse> createXml(@RequestBody XmlOrderRequest request) {
    // Xử lý request và trả về DTO response.
}
```

Trong test, có thể dùng chính XML literal ở trên. Converter sẽ đọc các phần tử XML và gán chúng vào thuộc tính DTO. Nếu muốn tạo body từ object, dùng `XmlMapper` của Jackson XML:

```java
XmlMapper xmlMapper = new XmlMapper();
XmlOrderRequest request = new XmlOrderRequest();
request.setCustomerId("C-100");
request.setQuantity(2);

byte[] body = xmlMapper.writeValueAsBytes(request);

mockMvc.perform(post("/api/orders/xml")
        .contentType(MediaType.APPLICATION_XML)
        .content(body))
    .andExpect(status().isOk());
```

Trong ứng dụng thật, nên ưu tiên dùng `XmlMapper` đã được cấu hình hoặc bean serializer của ứng dụng nếu có custom module hay naming rule. Test tạo một `XmlMapper` mặc định có thể tạo payload khác cấu hình production.

Có thể xác minh XML response bằng XPath matcher:

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.xpath;

mockMvc.perform(post("/api/orders/xml")
        .contentType(MediaType.APPLICATION_XML)
        .accept(MediaType.APPLICATION_XML)
        .content(xml.getBytes(StandardCharsets.UTF_8)))
    .andExpect(status().isOk())
    .andExpect(xpath("/receipt/orderId").string("O-100"));
```

XPath kiểm tra nội dung XML theo cấu trúc phần tử. Nếu XML dùng namespace, biểu thức và cấu hình namespace của matcher phải phản ánh namespace đó; một đường dẫn không có namespace có thể không tìm thấy phần tử dù response chứa dữ liệu.

## 4. Gửi nội dung nhị phân

Với body nhị phân, không nên chuyển dữ liệu thành `String` vì thao tác chuyển đổi có thể làm thay đổi byte, đặc biệt với dữ liệu không phải văn bản hoặc chứa byte không hợp lệ theo encoding. Hãy truyền trực tiếp `byte[]` cho `content(byte[])`.

Ví dụ endpoint nhận dữ liệu nhị phân:

```java
@RestController
class ImportController {

    @PostMapping(path = "/api/import",
                 consumes = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    ResponseEntity<Void> importData(@RequestBody byte[] payload) {
        // Xử lý payload nhị phân.
        return ResponseEntity.accepted().build();
    }
}
```

Test gửi byte array trực tiếp:

```java
byte[] payload = new byte[] {
        0x00, 0x01, 0x02, (byte) 0x80, (byte) 0xFF
};

mockMvc.perform(post("/api/import")
        .contentType(MediaType.APPLICATION_OCTET_STREAM)
        .content(payload))
    .andExpect(status().isAccepted());
```

`MediaType.APPLICATION_OCTET_STREAM` biểu thị dữ liệu nhị phân tổng quát. Nếu API nhận một định dạng cụ thể, chẳng hạn PDF hoặc PNG, nên dùng media type tương ứng khi hợp đồng API quy định như vậy. Header này giúp endpoint và converter hiểu loại payload đang được gửi.

### Kiểm tra response nhị phân

Một endpoint tải tệp có thể trả về `ResponseEntity<byte[]>` hoặc một kiểu resource phù hợp. Test nên so sánh byte thực tế thay vì chuyển response thành chuỗi:

```java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

byte[] expected = new byte[] { 0x10, 0x20, (byte) 0xFE };

MvcResult result = mockMvc.perform(get("/api/export")
        .accept(MediaType.APPLICATION_OCTET_STREAM))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_OCTET_STREAM))
    .andReturn();

assertArrayEquals(expected, result.getResponse().getContentAsByteArray());
```

`getContentAsByteArray()` giữ nguyên byte của response. `assertArrayEquals` kiểm tra cả độ dài lẫn từng byte theo đúng thứ tự. Có thể dùng `content().bytes(expected)` trong chuỗi `andExpect` nếu muốn viết assertion ngay trên kết quả MockMvc.

## 5. Phân biệt raw body và multipart upload

Một request có body nhị phân không đồng nghĩa với request upload nhiều phần. `application/octet-stream` thường gửi một payload nhị phân duy nhất. `multipart/form-data` chia request thành nhiều part, ví dụ một part là tệp và part khác là mô tả hoặc metadata.

Với multipart, dùng request builder `multipart(...)` và `MockMultipartFile`:

```java
import org.springframework.mock.web.MockMultipartFile;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;

byte[] fileBytes = new byte[] { 0x01, 0x02, (byte) 0xFF };
MockMultipartFile file = new MockMultipartFile(
        "file", "sample.bin", "application/octet-stream", fileBytes);

mockMvc.perform(multipart("/api/files")
        .file(file)
        .param("description", "sample payload"))
    .andExpect(status().isOk());
```

Controller multipart thường nhận `MultipartFile` qua `@RequestParam` hoặc `@RequestPart`, tùy hợp đồng endpoint. Không dùng `.content(fileBytes)` để mô phỏng multipart nếu controller thực sự yêu cầu các part có tên.

## 6. Content-Type, Accept và message converter

Spring MVC dùng `HttpMessageConverter` để chuyển đổi giữa HTTP body và kiểu Java. Converter được chọn dựa trên kiểu tham số hoặc kiểu trả về, media type và các converter đã đăng ký.

| Thành phần | Ý nghĩa trong request test | Ví dụ |
|---|---|---|
| `contentType(...)` | Cho biết định dạng body gửi đến server. | `APPLICATION_JSON`, `APPLICATION_XML`, `APPLICATION_OCTET_STREAM` |
| `accept(...)` | Cho biết client chấp nhận định dạng response nào. | `APPLICATION_JSON`, `APPLICATION_XML` |
| `content(String)` | Đặt body dạng văn bản. | JSON literal, XML literal |
| `content(byte[])` | Đặt body dưới dạng byte. | JSON/XML đã serialize, ảnh, PDF, payload nhị phân |
| `jsonPath(...)` | Kiểm tra response JSON. | `$.data.id` |
| `xpath(...)` | Kiểm tra response XML. | `/receipt/orderId` |
| `getContentAsByteArray()` | Lấy nguyên byte response. | So sánh nội dung tệp |

`Content-Type` không tự biến đổi body. Nếu gửi một chuỗi JSON nhưng khai báo `text/plain`, server sẽ xử lý request theo media type đó; converter JSON có thể không được chọn. Tương tự, `Accept` không thay đổi request body mà ảnh hưởng đến việc Spring chọn representation cho response.

Với JSON, Spring MVC thường dùng `MappingJackson2HttpMessageConverter` khi Jackson có mặt. Với XML, cần converter XML phù hợp như Jackson XML hoặc JAXB. Với `byte[]`, Spring có converter hỗ trợ mảng byte. Nếu dùng `standaloneSetup`, hãy chắc chắn các converter cần thiết đã được đăng ký; cấu hình MVC đầy đủ trong application context có thể khác cấu hình dựng controller độc lập.

## 7. Lỗi thường gặp khi gửi body

| HTTP status hoặc hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `415 Unsupported Media Type` | `Content-Type` không nằm trong `consumes`, hoặc không có converter đọc media type và kiểu tham số. | Kiểm tra `contentType(...)`, `consumes` và converter được đăng ký. |
| `400 Bad Request` với JSON | JSON sai cú pháp, kiểu dữ liệu không khớp DTO, body rỗng hoặc lỗi đọc body. | Kiểm tra payload, tên trường, kiểu trường và log exception như `HttpMessageNotReadableException`. |
| `400 Bad Request` với XML | XML không hợp lệ, cấu trúc không khớp hoặc converter không thể deserialize DTO. | Kiểm tra well-formed XML, root element, namespace và cấu hình XML converter. |
| `406 Not Acceptable` | Response không có representation phù hợp với `Accept`. | Kiểm tra `accept(...)`, `produces` và converter ghi response. |
| JSON assertion không tìm thấy trường | JSON response có cấu trúc khác biểu thức JSONPath hoặc response không phải JSON. | Kiểm tra status, Content-Type và nội dung response thực tế. |
| XPath không tìm thấy phần tử | XPath sai đường dẫn hoặc XML dùng namespace chưa được xử lý trong matcher. | Xem response XML thực tế và khai báo namespace phù hợp. |
| Byte response khác expected | Dữ liệu bị chuyển qua `String`, bị encode/decode hoặc nội dung mong đợi sai. | Gửi và đọc bằng `byte[]`; so sánh bằng `assertArrayEquals`. |
| POST trả về `403 Forbidden` trong ứng dụng có Spring Security | CSRF protection đang bật và request test chưa có CSRF token hợp lệ. | Nếu endpoint thuộc luồng cần CSRF, dùng request post-processor `csrf()` trong test và kiểm tra security configuration. |

Khi chẩn đoán, nên kiểm tra status trước, sau đó kiểm tra Content-Type và response body. Một lỗi chuyển đổi body có thể xảy ra trước khi controller được gọi, nên breakpoint trong phương thức controller có thể không được kích hoạt.

## 8. Ví dụ kiểm thử ba định dạng trong cùng một lớp

Đoạn dưới đây minh họa cách tổ chức test để mỗi định dạng có một request builder và assertion riêng. Các endpoint `/api/orders`, `/api/orders/xml` và `/api/import` là ví dụ; chúng cần tồn tại trong ứng dụng đang kiểm thử và được cấu hình converter tương ứng.

```java
import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.xpath;

import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

class RequestBodyFormatTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void sendsJsonBody() throws Exception {
        mockMvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                        {"customerId":"C-100","quantity":2}
                        """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.orderId").value("O-100"));
    }

    @Test
    void sendsXmlBody() throws Exception {
        String xml = "<order><customerId>C-100</customerId><quantity>2</quantity></order>";

        mockMvc.perform(post("/api/orders/xml")
                .contentType(MediaType.APPLICATION_XML)
                .accept(MediaType.APPLICATION_XML)
                .content(xml.getBytes(StandardCharsets.UTF_8)))
            .andExpect(status().isOk())
            .andExpect(xpath("/receipt/orderId").string("O-100"));
    }

    @Test
    void sendsBinaryBody() throws Exception {
        byte[] payload = new byte[] { 0x00, 0x01, (byte) 0xFE };

        mockMvc.perform(post("/api/import")
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .content(payload))
            .andExpect(status().isAccepted());
    }
}
```

Lớp ví dụ tập trung vào cách tạo request. Trong dự án thực tế, cần đặt test trong Spring test context thích hợp, chẳng hạn `@WebMvcTest` hoặc `@SpringBootTest` kết hợp `@AutoConfigureMockMvc`, và tiêm `MockMvc` như một dependency. Nếu controller phụ thuộc service, `@WebMvcTest` thường cần mock các dependency đó. Không cần khởi động HTTP server thật để kiểm tra các request này.

## 9. Checklist khi dựng request body

- Xác định endpoint nhận JSON, XML, raw binary hay multipart.
- Đặt `Content-Type` khớp với định dạng body và mapping `consumes`.
- Đặt `Accept` theo representation muốn kiểm tra trong response.
- Dùng `content(String)` cho văn bản; dùng `content(byte[])` khi cần kiểm soát byte hoặc gửi dữ liệu nhị phân.
- Với XML DTO, xác nhận XML `HttpMessageConverter` đã có và được cấu hình trong MockMvc context.
- Kiểm tra JSON bằng JSONPath, XML bằng XPath và binary bằng so sánh byte array.
- Khi test lỗi, xác định lỗi xảy ra ở bước mapping, message conversion, validation, security hay xử lý trong controller.

MockMvc cho phép kiểm thử nội dung HTTP body ngay trong môi trường mock Servlet. Chọn đúng kiểu body, media type và assertion giúp bài test xác minh chính xác hợp đồng request/response của API mà không cần gửi request qua mạng hoặc khởi chạy server thật.
