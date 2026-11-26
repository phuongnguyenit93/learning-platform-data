# Cacheable response

## Mục tiêu

Một response REST có thể được cache khi máy chủ cho phép client hoặc proxy lưu representation trong một khoảng thời gian, hoặc lưu lại rồi hỏi máy chủ xem representation đó còn mới hay không. Với Spring HATEOAS, representation còn chứa các liên kết `_links` và có thể cả tài nguyên nhúng trong `_embedded`. Vì vậy, cache phải bảo toàn tính đúng đắn của cả dữ liệu lẫn các liên kết mô tả những bước client có thể thực hiện tiếp theo.

Sau bài học, bạn có thể:

- Phân biệt cache HTTP với cache kết quả ở phía server như Spring Cache.
- Chọn chính sách `Cache-Control` phù hợp cho tài nguyên công khai, riêng tư và dữ liệu nhạy cảm.
- Dùng `ETag`, `Last-Modified` và request có điều kiện để giảm tải truyền dữ liệu.
- Áp dụng chính sách cache cho response `EntityModel`, `CollectionModel` hoặc representation HAL.
- Kiểm thử cả response `200 OK` lẫn `304 Not Modified` bằng Spring MVC Test.

## Cacheable response trong HTTP

HTTP cache lưu response representation để tái sử dụng cho request sau. Với một request `GET`, cache thường xác định bản lưu theo method và URI; các header trong `Vary` bổ sung những yếu tố của request dùng để phân biệt các biến thể representation. Response header quyết định response có được lưu hay không, được giữ trong bao lâu và cần xác thực lại khi nào.

Ví dụ, một response HAL có thể chứa dữ liệu đơn hàng cùng các liên kết điều hướng:

```json
{
  "id": "42",
  "status": "PENDING",
  "_links": {
    "self": { "href": "/api/orders/42" },
    "collection": { "href": "/api/orders" },
    "cancel": { "href": "/api/orders/42/cancel" }
  }
}
```

Cache lưu representation này như một đơn vị. Nếu trạng thái đơn hàng thay đổi, liên kết `cancel` không còn hợp lệ, hoặc cấu trúc liên kết thay đổi sau một lần triển khai, cache cũ có thể khiến client nhìn thấy dữ liệu hoặc hành động đã lỗi thời.

### Các chỉ thị Cache-Control thường dùng

| Chỉ thị | Ý nghĩa | Trường hợp sử dụng |
|---|---|---|
| `public` | Cho phép cache dùng chung lưu response nếu các điều kiện HTTP khác cho phép. | Tài nguyên công khai, giống nhau với mọi người dùng. |
| `private` | Chỉ cache riêng của client được phép lưu; cache dùng chung không được lưu response. | Dữ liệu gắn với phiên hoặc tài khoản người dùng. |
| `max-age=120` | Representation được xem là còn mới trong 120 giây. | Dữ liệu ít thay đổi và chấp nhận độ trễ cập nhật ngắn. |
| `s-maxage=300` | Thời gian còn mới dành riêng cho cache dùng chung. | API công khai đi qua reverse proxy hoặc CDN. |
| `no-cache` | Có thể lưu response, nhưng phải xác thực lại với server trước khi tái sử dụng. | Muốn giữ bản lưu nhưng cần kiểm tra dữ liệu còn mới. |
| `no-store` | Cache không được lưu response. | Dữ liệu nhạy cảm hoặc response không được phép lưu trữ. |
| `must-revalidate` | Khi response đã hết hạn, cache phải xác thực lại trước khi dùng. | Không được tiếp tục dùng dữ liệu cũ khi không liên lạc được server. |

`no-cache` không đồng nghĩa với `no-store`: chỉ thị đầu tiên cho phép lưu và yêu cầu xác thực lại, chỉ thị thứ hai cấm lưu. Tương tự, `private` không tự động làm response biến mất sau khi người dùng đăng xuất; nếu dữ liệu nhạy cảm không được lưu trên thiết bị, hãy dùng `no-store`.

Không nên đặt `public` cho response có nội dung hoặc liên kết phụ thuộc người dùng. Ví dụ, hai người dùng có thể nhận cùng thông tin đơn hàng nhưng chỉ một người có quyền hủy đơn. Nếu proxy dùng chung lưu response chứa liên kết `cancel` rồi trả response đó cho người còn lại, representation đã tiết lộ một hành động không dành cho họ. Với response phụ thuộc tài khoản, thường bắt đầu bằng `private`; với dữ liệu nhạy cảm, cân nhắc `no-store`.

### Validator và request có điều kiện

Thay vì tải lại toàn bộ representation mỗi lần, client có thể gửi validator của bản lưu để hỏi server xem bản đó còn mới không.

- `ETag` là mã định danh validator của representation. Client gửi lại giá trị này trong `If-None-Match`.
- `Last-Modified` cho biết thời điểm representation được sửa lần cuối. Client gửi lại thời điểm này trong `If-Modified-Since`.
- Nếu representation chưa thay đổi và request là `GET` hoặc `HEAD`, server có thể trả `304 Not Modified` không kèm body. Client tiếp tục dùng bản đã lưu.
- Nếu representation đã thay đổi, server trả `200 OK` cùng representation và validator mới.

`ETag` thường chính xác hơn `Last-Modified`, đặc biệt khi dữ liệu có thể thay đổi nhiều lần trong một giây. HTTP ưu tiên kiểm tra `If-None-Match` khi request có cả hai loại validator. Với ETag mạnh, giá trị phải đại diện cho đúng representation; ETag yếu có tiền tố `W/` và biểu thị hai representation tương đương về mặt ngữ nghĩa, dù byte có thể khác nhau.

Một ETag dựa trên `id` và `version` của entity chỉ chính xác nếu mọi thay đổi có thể làm thay đổi response đều làm tăng version đó. Với Spring HATEOAS, response còn có links, embedded resources, thông tin phân trang và biến thể theo media type hoặc ngôn ngữ. Nếu một trong các phần này thay đổi độc lập với entity, validator phải tính đến chúng. Khi không thể xác định an toàn validator cho dữ liệu phụ thuộc người dùng, hãy yêu cầu xác thực lại hoặc tắt lưu cache.

## Áp dụng trong Spring HATEOAS

Spring HATEOAS tập trung tạo representation và liên kết. Controller Spring MVC chịu trách nhiệm gửi HTTP header, còn `EntityModel`, `CollectionModel` và các model phân trang cung cấp nội dung cho representation đó. Bạn có thể đặt chính sách cache trực tiếp trên `ResponseEntity` bằng `CacheControl`.

Ví dụ dưới đây giả định `Order` có `id`, `version` được tăng mỗi khi dữ liệu ảnh hưởng đến representation thay đổi, và `updatedAt` kiểu `Instant`. `OrderModelAssembler` chuyển entity thành `EntityModel<OrderModel>` cùng các liên kết HAL.

```java
import java.time.Duration;
import java.time.temporal.ChronoUnit;
import java.util.UUID;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.WebRequest;

@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderService orderService;
    private final OrderModelAssembler orderModelAssembler;

    OrderController(
            OrderService orderService,
            OrderModelAssembler orderModelAssembler) {
        this.orderService = orderService;
        this.orderModelAssembler = orderModelAssembler;
    }

    @GetMapping(value = "/{id}", produces = MediaTypes.HAL_JSON_VALUE)
    ResponseEntity<EntityModel<OrderModel>> findById(
            @PathVariable UUID id,
            WebRequest request) {

        Order order = orderService.findById(id);

        // Ví dụ này giả định version bao quát mọi thay đổi của representation.
        String etag = "\"" + order.getId() + "-" + order.getVersion() + "\"";
        long lastModified = order.getUpdatedAt()
                .truncatedTo(ChronoUnit.SECONDS)
                .toEpochMilli();

        CacheControl policy = CacheControl.maxAge(Duration.ofMinutes(2))
                .cachePrivate()
                .mustRevalidate();

        // Spring kiểm tra If-None-Match / If-Modified-Since trước khi tạo HAL body.
        if (request.checkNotModified(etag, lastModified)) {
            return ResponseEntity.status(HttpStatus.NOT_MODIFIED)
                    .eTag(etag)
                    .lastModified(lastModified)
                    .cacheControl(policy)
                    .header(HttpHeaders.VARY, HttpHeaders.ACCEPT)
                    .build();
        }

        EntityModel<OrderModel> representation = orderModelAssembler.toModel(order);

        return ResponseEntity.ok()
                .eTag(etag)
                .lastModified(lastModified)
                .cacheControl(policy)
                .header(HttpHeaders.VARY, HttpHeaders.ACCEPT)
                .body(representation);
    }
}
```

Trong ví dụ:

1. `produces = MediaTypes.HAL_JSON_VALUE` chọn representation HAL cho endpoint.
2. `CacheControl` đặt response thành cache riêng, còn mới tối đa hai phút và phải xác thực lại khi hết hạn.
3. `ETag` và `Last-Modified` cung cấp hai validator cho client.
4. `WebRequest.checkNotModified(...)` kiểm tra request có điều kiện trước khi assembler tạo body. Khi bản lưu vẫn mới, controller trả `304` không có body.
5. `Vary: Accept` báo cho cache rằng representation có thể khác nhau theo media type mà client yêu cầu. Nếu API còn biến thể theo `Accept-Language`, hãy thêm header đó vào `Vary`.

Đây là ví dụ cho response có nội dung giống nhau giữa những người dùng được phép xem đơn hàng. Nếu assembler tạo links theo quyền, tenant hoặc trạng thái đăng nhập, `id-version` không còn đủ để đại diện cho toàn bộ response. Khi đó, hãy đưa các yếu tố làm thay đổi representation vào cách tạo validator và cache key, hoặc dùng `no-store` nếu không thể phân biệt an toàn các biến thể. Không dựa vào `Vary: Authorization` như một biện pháp thay thế cho thiết kế cache riêng tư đúng đắn.

Với endpoint dữ liệu nhạy cảm, chính sách có thể đơn giản là:

```java
return ResponseEntity.ok()
        .cacheControl(CacheControl.noStore())
        .body(representation);
```

### Áp dụng cho collection và phân trang

`CollectionModel` và `PagedModel` cũng là representation HTTP, nên có thể dùng `Cache-Control`, `ETag`, `Last-Modified` và `Vary` tương tự response chi tiết. Khi tạo validator cho collection, hãy tính đến tập phần tử, thứ tự sắp xếp, bộ lọc, thông tin phân trang và các liên kết như `first`, `prev`, `self`, `next`, `last`. Hai request có query parameter khác nhau thường là hai URI khác nhau và có thể có representation khác nhau.

Ví dụ, danh sách đơn hàng có thể thay đổi khi có đơn mới dù entity của một đơn hàng cụ thể không đổi. Vì vậy, không dùng version của một phần tử làm ETag cho toàn bộ collection. Có thể dùng version của tập dữ liệu, timestamp cập nhật collection hoặc hash của representation hoàn chỉnh, tùy mô hình dữ liệu.

## Kiểm thử cache behavior

Kiểm thử nên xác minh cả nội dung HAL lẫn header HTTP. Quan trọng nhất là chứng minh request đầu tiên nhận `200` cùng ETag, sau đó request gửi lại ETag đó nhận `304` và không có body.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.hateoas.MediaTypes;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MvcResult;

// Trong một test dùng MockMvc và dữ liệu đơn hàng cố định:
MvcResult firstResponse = mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(header().string(HttpHeaders.CACHE_CONTROL,
                containsString("private")))
        .andExpect(header().string(HttpHeaders.CACHE_CONTROL,
                containsString("max-age=120")))
        .andExpect(header().string(HttpHeaders.VARY,
                containsString(HttpHeaders.ACCEPT)))
        .andExpect(jsonPath("$._links.self.href").exists())
        .andReturn();

String etag = firstResponse.getResponse().getHeader(HttpHeaders.ETAG);
assertThat(etag).isNotBlank();

mockMvc.perform(get("/api/orders/{id}", orderId)
                .accept(MediaTypes.HAL_JSON)
                .header(HttpHeaders.IF_NONE_MATCH, etag))
        .andExpect(status().isNotModified())
        .andExpect(content().string(""));
```

Đoạn test giả định fixture đơn hàng không thay đổi giữa hai request và controller dùng chính sách trong ví dụ. Khi kiểm thử ETag thay đổi, cập nhật version hoặc một thành phần của representation rồi gửi lại ETag cũ; kết quả phải là `200 OK` với ETag mới. Nếu links phụ thuộc quyền, hãy kiểm thử hai người dùng có quyền khác nhau để chắc chắn cache không trả representation của người này cho người kia.

## Những lỗi thường gặp

- **Dùng `no-cache` với ý nghĩa cấm lưu:** trình duyệt vẫn có thể lưu response và chỉ xác thực lại trước khi tái sử dụng. Dùng `no-store` khi cần cấm lưu.
- **Đặt `public` cho representation có links theo quyền:** cache dùng chung có thể phát lại liên kết không phù hợp với người nhận. Chọn `private` hoặc `no-store` và thiết kế validator theo đúng biến thể.
- **Tạo ETag chỉ từ entity version:** links, embedded resource, dữ liệu tính toán hoặc cấu trúc HAL có thể thay đổi mà version entity không đổi.
- **Quên `Vary`:** cùng URI có thể trả HAL, JSON hoặc ngôn ngữ khác nhau; cache có thể phát sai biến thể nếu không biết header nào ảnh hưởng representation.
- **Cho rằng cache tự làm mới mọi URI liên quan sau lệnh ghi:** thay đổi một đơn hàng có thể ảnh hưởng cả URI chi tiết, collection, tìm kiếm và thống kê. Hãy chọn TTL phù hợp, xác thực lại bằng validator hoặc chủ động purge cache dùng chung khi cần.
- **Nhầm HTTP cache với `@Cacheable`:** `@Cacheable` lưu kết quả xử lý ở phía server; `Cache-Control` và validator điều khiển cache HTTP ở client hoặc proxy. Hai cơ chế có thể cùng tồn tại nhưng có phạm vi và chiến lược invalidation khác nhau.

## Quy trình lựa chọn chính sách

1. Xác định response có giống nhau với mọi người dùng hay phụ thuộc tài khoản, quyền, tenant hoặc locale.
2. Chọn `public`, `private` hoặc `no-store` theo mức độ chia sẻ và độ nhạy cảm của dữ liệu.
3. Chọn TTL theo mức độ chấp nhận dữ liệu cũ; nếu cần kiểm tra trước mỗi lần tái sử dụng, dùng `no-cache`.
4. Tạo validator bao quát toàn bộ representation, gồm dữ liệu và links HATEOAS.
5. Khai báo `Vary` cho các header thực sự làm thay đổi representation.
6. Kiểm thử response mới, response `304`, validator sau khi dữ liệu thay đổi và các trường hợp khác nhau về quyền hoặc media type.

Cacheable response giúp API giảm băng thông và tải xử lý trong khi vẫn giữ được khả năng điều hướng của hypermedia. Điều kiện quan trọng là cache policy và validator phải mô tả đúng representation mà client nhận được, bao gồm cả các liên kết hành động mà Spring HATEOAS tạo ra.
