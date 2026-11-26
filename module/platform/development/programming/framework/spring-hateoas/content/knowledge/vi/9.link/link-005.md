# type của link

Trong một REST API có hypermedia, link không chỉ chứa URI để client truy cập. Link còn có thể mang metadata giúp client hiểu đích đến. Một metadata hữu ích là `type`: gợi ý media type của representation mà client có thể nhận khi đi theo link. Với Spring HATEOAS, có thể đặt giá trị này bằng `withType(...)` khi tạo `Link`.

Ví dụ, một đơn hàng có thể cung cấp link `download` đến file hóa đơn. Relation `download` cho biết mục đích của link; `type: application/pdf` gợi ý rằng đích link trả về tài liệu PDF. Client có thể dùng thông tin này để chọn biểu tượng, cách mở hoặc quyết định có hỗ trợ định dạng đó hay không.

## `type` mô tả điều gì?

Trong mô hình link của Web Linking, `type` là một media-type hint cho tài nguyên ở đích của link. Giá trị thường là một media type như:

| Giá trị `type` | Representation được gợi ý |
| --- | --- |
| `application/hal+json` | Tài nguyên JSON theo định dạng HAL. |
| `application/json` | Dữ liệu JSON. |
| `application/pdf` | Tài liệu PDF. |
| `text/html` | Trang HTML. |
| `image/png` | Hình ảnh PNG. |

`type` có ý nghĩa khi client muốn biết sơ bộ loại nội dung ở đích mà chưa cần tải tài nguyên. Chẳng hạn, giao diện có thể hiển thị nút tải PDF cho link có type `application/pdf`, hoặc dùng một trình xem phù hợp với media type được công bố.

Đây là thông tin gợi ý, không phải cam kết bất biến rằng server chắc chắn sẽ trả về đúng media type đó trong mọi hoàn cảnh. Đích có thể phụ thuộc vào content negotiation, quyền truy cập, trạng thái tài nguyên hoặc cấu hình server. Client vẫn cần kiểm tra `Content-Type` thực tế trong HTTP response.

## Phân biệt `type`, `rel`, `Accept` và `Content-Type`

Các khái niệm này xuất hiện gần nhau nhưng trả lời những câu hỏi khác nhau:

| Thành phần | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| `rel` | Link này có quan hệ hoặc mục đích gì với tài nguyên hiện tại? | `self`, `next`, `download`, `invoice` |
| `type` của link | Đích link có thể cung cấp representation thuộc media type nào? | `application/pdf` |
| HTTP `Accept` | Client muốn server trả về những media type nào cho request này? | `Accept: application/pdf` |
| HTTP `Content-Type` | Body của response hiện tại thực tế có định dạng nào? | `Content-Type: application/pdf` |

Ví dụ, response HAL có thể công bố một link như sau:

```json
{
  "id": "7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042",
  "status": "PAID",
  "_links": {
    "self": {
      "href": "https://shop.example/api/orders/7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042",
      "type": "application/hal+json"
    },
    "download": {
      "href": "https://shop.example/api/orders/7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042/invoice",
      "type": "application/pdf",
      "title": "Tải hóa đơn PDF"
    }
  }
}
```

Ở đây `rel` là tên relation nằm trong `_links` (`self` và `download`). Thuộc tính `type` mô tả media type của representation ở URI đích. Nó không mô tả định dạng JSON của toàn bộ response HAL hiện tại. Response HAL được xác định bởi media type HTTP của chính response, thường là `application/hal+json`.

Khi client theo link `download`, client có thể gửi `Accept: application/pdf`. Server trả file và đặt `Content-Type: application/pdf` nếu nội dung thực tế là PDF. `type` trong link giúp client chuẩn bị request, còn `Accept` và `Content-Type` vẫn thực hiện vai trò thương lượng và xác nhận định dạng HTTP.

## Đặt type bằng Spring HATEOAS

Spring HATEOAS cung cấp `withType(String)` trên link/link builder. Giá trị truyền vào là media type dạng chuỗi, thường lấy từ các hằng của Spring như `MediaType.APPLICATION_PDF_VALUE` hoặc `MediaTypes.HAL_JSON_VALUE`.

Ví dụ, assembler tạo self link đến representation HAL và link tải hóa đơn PDF:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;

@Component
class OrderModelAssembler {

    public EntityModel<OrderDto> toModel(Order order) {
        OrderDto dto = new OrderDto(
                order.getId(), order.getStatus().name(), order.getTotalAmount());

        return EntityModel.of(dto,
                linkTo(methodOn(OrderController.class)
                        .one(order.getId()))
                        .withSelfRel()
                        .withType(MediaTypes.HAL_JSON_VALUE),
                linkTo(methodOn(OrderController.class)
                        .downloadInvoice(order.getId()))
                        .withRel("download")
                        .withType(MediaType.APPLICATION_PDF_VALUE)
                        .withTitle("Tải hóa đơn PDF"));
    }
}
```

`withType(...)` gắn metadata vào link. Nó không cấu hình `produces` cho controller và cũng không tự chuyển đổi response thành PDF. Endpoint đích phải tự trả đúng nội dung và media type.

Ví dụ controller công bố hai representation với media type riêng:

```java
import java.util.UUID;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService service;
    private final OrderModelAssembler assembler;

    OrderController(OrderService service, OrderModelAssembler assembler) {
        this.service = service;
        this.assembler = assembler;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    EntityModel<OrderDto> one(@PathVariable UUID id) {
        return assembler.toModel(service.findById(id));
    }

    @GetMapping(value = "/{id}/invoice", produces = MediaType.APPLICATION_PDF_VALUE)
    ResponseEntity<ByteArrayResource> downloadInvoice(@PathVariable UUID id) {
        byte[] pdf = service.createInvoicePdf(id);
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_PDF)
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=invoice-" + id + ".pdf")
                .body(new ByteArrayResource(pdf));
    }
}
```

`OrderService.createInvoicePdf` đại diện cho logic tạo hoặc lấy file PDF trong ứng dụng. Controller khai báo `produces = MediaType.APPLICATION_PDF_VALUE` và trả `Content-Type` phù hợp. Link assembler dùng cùng method `downloadInvoice` để tạo URI từ mapping, rồi đặt `type` là `application/pdf` để mô tả representation ở đích.

Nếu tạo link từ một URI đã biết mà không cần suy ra từ controller, có thể dùng `Link.of(...)`:

```java
import org.springframework.hateoas.Link;
import org.springframework.http.MediaType;

Link documentation = Link.of(
        "https://docs.example.com/orders",
        "documentation")
        .withType(MediaType.TEXT_HTML_VALUE)
        .withTitle("Tài liệu về đơn hàng");
```

Đối với URI nội bộ, link builder từ controller thường an toàn hơn vì URI được tạo theo mapping hiện hành. Với URI ngoài, `Link.of` phù hợp khi địa chỉ là một phần cấu hình hoặc được cung cấp từ nguồn dữ liệu đáng tin cậy.

## HAL serialize type như thế nào?

Trong HAL, metadata của link được serialize bên trong object của relation. Ví dụ:

```json
{
  "_links": {
    "download": {
      "href": "https://shop.example/api/orders/42/invoice",
      "type": "application/pdf",
      "title": "Tải hóa đơn PDF"
    }
  }
}
```

`href` là URI đích; `type` là media-type hint; `title` là nhãn dễ đọc cho người dùng hoặc công cụ. Client có thể đọc các thuộc tính này để trình bày liên kết phù hợp. `type` là metadata tùy chọn: nếu server không biết rõ media type đích hoặc endpoint hỗ trợ nhiều representation qua content negotiation, có thể bỏ qua thuộc tính này thay vì công bố một giá trị gây hiểu nhầm.

Một relation có thể có nhiều link. Nếu các link cùng relation nhưng trỏ đến các loại nội dung khác nhau, mỗi link có thể mang `type` riêng. Tuy nhiên, hãy đặt relation sao cho ý nghĩa chung vẫn nhất quán và client có thể chọn link phù hợp dựa trên metadata.

## Khi nào nên đặt `type`?

Nên đặt `type` khi server biết tương đối chắc chắn media type mà URI đích cung cấp và thông tin này giúp client ra quyết định trước khi truy cập. Ví dụ:

- Link `download` trỏ đến file PDF ổn định.
- Link `image` trỏ đến ảnh PNG hoặc JPEG.
- Link `self` trỏ đến resource HAL JSON có media type đã xác định.
- Link `documentation` trỏ đến trang HTML.

Có thể bỏ `type` trong các trường hợp sau:

- Đích hỗ trợ nhiều media type và server không biết client sẽ chọn loại nào.
- Media type có thể thay đổi theo trạng thái hoặc cấu hình nhưng response không công bố rõ.
- Thông tin chỉ được suy đoán từ phần mở rộng của URI.
- Link trỏ đến một endpoint không kiểm soát được và không có metadata đáng tin cậy.

Không nên dùng `type` để thay thế `rel`. `rel` cho biết client đang theo quan hệ nào; `type` cho biết loại representation được gợi ý ở đích. Một link `invoice` có thể có type `application/pdf`; relation `invoice` vẫn cần được giữ nguyên ngay cả khi hệ thống thay cách lưu file hoặc URI đích.

## Kiểm thử metadata type

Kiểm thử response HAL giúp bảo vệ metadata của link như một phần hợp đồng API. Với MockMvc, có thể kiểm tra relation, URI và type:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.hateoas.MediaTypes;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrderLinkTypeTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void invoiceLinkAdvertisesPdfMediaType() throws Exception {
        String id = "7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042";

        mockMvc.perform(get("/api/orders/{id}", id)
                        .accept(MediaTypes.HAL_JSON))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(MediaTypes.HAL_JSON))
                .andExpect(jsonPath("$._links.download.type")
                        .value("application/pdf"))
                .andExpect(jsonPath("$._links.download.href")
                        .value(org.hamcrest.Matchers.endsWith("/api/orders/" + id + "/invoice")));
    }

    @Test
    void invoiceEndpointReturnsPdfContentType() throws Exception {
        mockMvc.perform(get("/api/orders/{id}/invoice",
                        "7d3d5f70-8fcb-4d5d-9b3c-7c52b2a10042")
                        .accept("application/pdf"))
                .andExpect(status().isOk())
                .andExpect(content().contentType("application/pdf"));
    }
}
```

Test cần có fixture với đơn hàng tương ứng và dữ liệu hóa đơn có thể tạo được. Test đầu xác minh metadata `type` mà client nhìn thấy trong HAL; test thứ hai xác minh endpoint thực sự trả PDF. Hai kiểm tra này bổ sung cho nhau: một kiểm tra lời gợi ý trong link, một kiểm tra media type HTTP thực tế.

Các lỗi thường gặp:

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Nhầm `type` với `rel` | Client hiểu sai mục đích link. | Dùng `rel` cho quan hệ và `type` cho media type đích. |
| Đặt `type` nhưng endpoint trả định dạng khác | Client chọn sai trình xử lý nội dung. | Đồng bộ metadata với `produces` và kiểm thử `Content-Type`. |
| Nghĩ `withType` tự cấu hình controller | Endpoint không thực sự trả representation được gợi ý. | Cấu hình `produces` và response body riêng tại endpoint. |
| Dùng phần mở rộng URL làm type | Media type có thể sai hoặc lỗi thời. | Dùng media type do server kiểm soát và xác minh. |
| Dùng `type` thay cho content negotiation | Client không thương lượng được định dạng cần nhận. | Gửi `Accept` và đọc `Content-Type` của response. |

## Nguyên tắc thiết kế

- Dùng `withType(String)` để thêm media-type hint vào link khi biết loại representation ở đích.
- Dùng giá trị media type chuẩn như `application/pdf`, `text/html` hoặc `application/hal+json`.
- Giữ `rel` để mô tả ý nghĩa quan hệ; không dùng `type` làm tên hành động.
- Đồng bộ type hint với `produces` và `Content-Type` của endpoint đích.
- Xem `type` là gợi ý và luôn xử lý response dựa trên HTTP headers thực tế.
- Kiểm thử cả thuộc tính `type` trong HAL và media type thực tế của endpoint.

Thuộc tính `type` giúp client hiểu sơ bộ nội dung ở đích link và chuẩn bị cách xử lý phù hợp. Khi được công bố chính xác, nó bổ sung thông tin có ích cho hypermedia mà không làm thay đổi vai trò của relation, content negotiation hoặc HTTP response headers.
