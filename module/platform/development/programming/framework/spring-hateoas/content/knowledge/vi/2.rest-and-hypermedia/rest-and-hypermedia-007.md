# Code on demand

**Code on demand** (gửi mã theo yêu cầu) là một ràng buộc tùy chọn trong kiến trúc REST. Server có thể chuyển mã thực thi tới client để bổ sung khả năng cho client tại thời điểm chạy. Trình duyệt tải một JavaScript module từ server rồi thực thi module đó là ví dụ quen thuộc. Thay vì phải đóng gói mọi hành vi vào ứng dụng client ngay từ đầu, client có thể nhận thêm một phần hành vi khi cần.

Trong module Spring HATEOAS, cần hiểu code on demand cùng với hypermedia: liên kết có thể giúp client khám phá một tài nguyên chứa mã, nhưng liên kết và mã thực thi là hai thứ khác nhau. Spring HATEOAS hỗ trợ tạo representation và link; nó không tự tải, xác minh hay thực thi mã trên client.

## Vị trí của code on demand trong REST

REST được mô tả bằng một tập hợp ràng buộc kiến trúc. Các ràng buộc thường được nhắc đến gồm client-server, stateless, cache, uniform interface, layered system và code on demand. Năm ràng buộc đầu tạo nên nền tảng của phong cách REST; **code on demand là tùy chọn**. Một API có thể tuân theo REST mà không gửi chương trình thực thi cho client.

Code on demand cho phép server mở rộng chức năng của client bằng cách gửi mã mà môi trường client có thể chạy, chẳng hạn JavaScript trong trình duyệt. Cách này có thể giảm lượng logic phải cài đặt sẵn trong client và cho phép bổ sung hành vi mà không cần phát hành lại toàn bộ ứng dụng client. Đổi lại, client phải tin tưởng nguồn mã, hỗ trợ môi trường thực thi tương ứng và chấp nhận những hệ quả về bảo mật, hiệu năng cũng như khả năng tương thích.

Không nên nhầm code on demand với **HATEOAS**. HATEOAS yêu cầu client điều hướng trạng thái ứng dụng thông qua các điều khiển hypermedia trong representation. Code on demand cho phép server gửi thêm mã để client thực thi. Một API có thể cung cấp link HATEOAS mà không gửi mã; ngược lại, một trang web có thể tải JavaScript mà không thiết kế API theo HATEOAS.

## Luồng hoạt động

Một luồng đơn giản có thể diễn ra như sau:

1. Client gửi request lấy tài nguyên, ví dụ một đơn hàng.
2. Server trả representation của đơn hàng, kèm dữ liệu và các link hypermedia.
3. Nếu client nhận ra một relation dùng để khám phá module client, nó đọc `href` và metadata của link.
4. Client kiểm tra nguồn mã có nằm trong danh sách tin cậy và loại nội dung có được hỗ trợ hay không.
5. Client tải module, kiểm tra response và thực thi theo chính sách của ứng dụng.
6. Module mở rộng giao diện hoặc hành vi client; khi cần truy cập dữ liệu, nó tiếp tục dùng API và các link được công bố.

Điểm quyết định nằm ở client: client phải hiểu relation, hỗ trợ media type và có chính sách cho phép thực thi mã. Việc server gửi một link không buộc client phải tải hoặc chạy tài nguyên đích.

## Ví dụ với Spring HATEOAS và JavaScript module

Giả sử API trả về đơn hàng và công bố thêm một module JavaScript có thể hiển thị tiện ích cho màn hình đơn hàng. Ứng dụng quy ước relation URI `https://api.example.com/rels/client-module` để chỉ link tới module này. Đây là relation do API định nghĩa; client phải biết ý nghĩa của nó qua hợp đồng API và server cần giữ ý nghĩa của relation ổn định.

Controller có thể cung cấp module như một tài nguyên riêng:

```java
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/client-modules")
class ClientModuleController {

    @GetMapping(value = "/order-panel.js", produces = "text/javascript")
    ResponseEntity<Resource> orderPanel() {
        Resource module = new ClassPathResource("client-modules/order-panel.js");
        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType("text/javascript"))
            .body(module);
    }
}
```

Ví dụ giả định file `client-modules/order-panel.js` nằm trong `src/main/resources`. Trong ứng dụng thực tế, có thể dùng cơ chế static resource của Spring Boot hoặc một máy chủ tài nguyên tĩnh để phục vụ module. Điều quan trọng là server trả đúng nội dung mã và media type phù hợp.

Controller tài nguyên đơn hàng có thể gắn link tới module vào representation:

```java
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;

EntityModel<Order> toModel(Order order) {
    Link self = linkTo(methodOn(OrderController.class).one(order.getId()))
        .withSelfRel();

    Link clientModule = linkTo(
            methodOn(ClientModuleController.class).orderPanel())
        .withRel("https://api.example.com/rels/client-module")
        .withType("text/javascript");

    return EntityModel.of(order, self, clientModule);
}
```

Đây là một phương thức minh họa có thể đặt trong controller hoặc assembler; `Order`, `OrderController` và phần truy xuất dữ liệu thuộc ứng dụng. `withRel(...)` gắn relation URI đã quy ước cho link, còn `withType("text/javascript")` cung cấp gợi ý về loại nội dung đích. `type` chỉ là metadata của link, không phải chỉ thị bắt buộc trình duyệt thực thi mã.

Với HAL JSON, một representation minh họa có thể trông như sau:

```json
{
  "id": 42,
  "status": "PENDING",
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "https://api.example.com/rels/client-module": {
      "href": "https://api.example.com/client-modules/order-panel.js",
      "type": "text/javascript"
    }
  }
}
```

Client có thể nhận ra relation URI `https://api.example.com/rels/client-module` và tải module. Ví dụ sau minh họa kiểm tra origin trước khi import:

```javascript
const response = await fetch("https://api.example.com/orders/42", {
  headers: { Accept: "application/hal+json" }
});

if (!response.ok) {
  throw new Error(`Không thể tải đơn hàng: ${response.status}`);
}

const order = await response.json();
const moduleLink = order._links?.["https://api.example.com/rels/client-module"];

if (moduleLink?.type === "text/javascript") {
  const moduleUrl = new URL(moduleLink.href, response.url);
  const trustedOrigins = new Set(["https://api.example.com"]);

  if (!trustedOrigins.has(moduleUrl.origin)) {
    throw new Error("Nguồn module không được tin cậy");
  }

  const orderPanel = await import(moduleUrl.href);
  orderPanel.installOrderPanel(order);
}
```

Module được tải có thể xuất hàm cài đặt giao diện:

```javascript
export function installOrderPanel(order) {
  const panel = document.querySelector("#order-panel");
  if (!panel) return;

  const message = document.createElement("p");
  message.textContent = `Đơn hàng ${order.id}: ${order.status}`;
  panel.replaceChildren(message);
}
```

Đoạn mã client chỉ là ví dụ khái niệm. Ứng dụng cần có phần tử `#order-panel`, xử lý lỗi mạng và kiểm soát phiên bản module. Khi import module từ origin khác, trình duyệt còn áp dụng quy tắc CORS cho JavaScript module và chính sách Content Security Policy của trang. Việc kiểm tra origin trong ví dụ là một lớp allowlist cơ bản, không thay thế quy trình phát hành và kiểm duyệt mã.

## Lợi ích và giới hạn

Code on demand có thể đem lại một số lợi ích:

- **Mở rộng client:** server cung cấp thêm hành vi cho những client có khả năng hỗ trợ mà không cần đóng gói tất cả chức năng vào bản cài đặt ban đầu.
- **Tải theo nhu cầu:** client chỉ tải module khi representation và trạng thái hiện tại cho thấy module có ích.
- **Tách dữ liệu và hành vi:** API có thể tiếp tục trả dữ liệu tài nguyên, trong khi phần mã giao diện hoặc xử lý bổ sung được phân phối như một tài nguyên riêng.

Tuy nhiên, cơ chế này cũng có giới hạn:

- Client phải có runtime tương thích với ngôn ngữ và phiên bản module.
- Mã tải về có thể tăng thời gian tải, chi phí mạng và độ phức tạp khi debug.
- Client phải tin tưởng server phát hành mã. Một module độc hại có thể thực thi với quyền của trang, đọc dữ liệu mà trang truy cập được hoặc gửi request thay mặt người dùng.
- Hai phía cần quản lý tương thích giữa module, dữ liệu representation và các endpoint mà module gọi.
- Không phải mọi client REST đều có khả năng hoặc chính sách cho phép thực thi mã được tải về; client chỉ đọc dữ liệu có thể bỏ qua relation này.

## Nguyên tắc bảo mật và vận hành

Chỉ phân phối mã từ nguồn đã được tổ chức tin cậy và qua quy trình review, kiểm thử, phát hành. Với trình duyệt, nên dùng HTTPS, giới hạn origin được phép tải script, cấu hình Content Security Policy phù hợp và tránh nạp module từ URL tùy ý do dữ liệu đầu vào cung cấp. Không dùng `eval` hoặc cơ chế thực thi chuỗi tùy tiện để chạy nội dung từ response.

Mã module chạy trong môi trường client và có thể có quyền tương đương mã ứng dụng cùng trang. Vì vậy, không đặt bí mật hoặc thông tin xác thực đặc quyền trong module; không coi việc ẩn một link là cơ chế phân quyền; và vẫn phải xác thực, phân quyền mọi request API ở server. Nếu cần chạy mã không đáng tin cậy, hãy xem xét một môi trường cô lập phù hợp thay vì import trực tiếp vào ứng dụng chính.

Nên version hóa URL module hoặc có chiến lược cache rõ ràng để tránh client dùng mã cũ với hợp đồng API mới. Server cần công bố loại nội dung chính xác; client cần xử lý trường hợp link vắng mặt, module không tải được hoặc phiên bản không tương thích. Link hypermedia giúp khám phá tài nguyên, nhưng không loại bỏ nhu cầu quản lý vòng đời mã.

## Khi nào nên dùng?

Code on demand phù hợp khi client có runtime đáng tin cậy, nhu cầu mở rộng hành vi rõ ràng và lợi ích của việc phân phối module theo nhu cầu lớn hơn chi phí bảo mật, vận hành và tương thích. Một ví dụ thường gặp là ứng dụng web tải module giao diện theo từng khu vực chức năng.

Với một REST API Spring HATEOAS thông thường, việc trả `EntityModel`, `CollectionModel`, HAL và các link tới tài nguyên thường đã đủ để client điều hướng và thao tác. Chỉ nên thêm link tới mã thực thi khi thực sự cần gửi hành vi cho client. Hãy nhớ ba điểm: code on demand là tùy chọn của REST; hypermedia link có thể giúp khám phá module nhưng không tự thực thi module; và quyết định tải, tin cậy, chạy mã luôn cần nằm trong chính sách có chủ đích của client.
