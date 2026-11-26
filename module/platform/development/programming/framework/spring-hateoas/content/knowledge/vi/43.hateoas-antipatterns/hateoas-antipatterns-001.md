# Hard-code URI ở client

Một client REST thường bắt đầu bằng một URI để tìm API entry point. Từ đó, server có thể cung cấp các link giúp client đi tới collection, resource liên quan và action tiếp theo. Anti-pattern xuất hiện khi client bỏ qua các link đó, tự ghép URI từ chuỗi cố định, tên controller, cấu trúc path hoặc quy tắc phân trang mà server chưa công bố.

Ví dụ, client tự tạo đường dẫn `/api/v1/orders/42` từ một base URL và một order ID. Cách làm này khiến client phụ thuộc vào cấu trúc route của server. Khi server chuyển resource sang `/orders/42`, đổi prefix, thêm gateway hoặc thay đổi cấu trúc collection, client có thể hỏng dù semantics nghiệp vụ không đổi.

HATEOAS giải quyết sự phụ thuộc này bằng cách để server công bố các link theo relation. Client biết ý nghĩa cần tìm, chẳng hạn `orders`, `self`, `customer`, `next` hoặc `cancel`, rồi sử dụng URI được trả về. Với Spring HATEOAS, `Traverson` hỗ trợ duyệt các relation trong representation; `Link` và `LinkDiscoverer` hỗ trợ đọc, kiểm tra và mở rộng link.

Bài học này giải thích vì sao hard-code URI là anti-pattern, phần nào của cấu hình client vẫn cần biết trước, và cách xây client Spring sử dụng link do server cung cấp để thích ứng khi URI thay đổi.

## Mục tiêu

Sau bài học, bạn có thể:

- Nhận diện các dạng hard-code URI trong REST client.
- Giải thích coupling giữa client và cấu trúc route của server.
- Phân biệt API entry point cần cấu hình với URI tài nguyên cần khám phá động.
- Duyệt relation bằng `Traverson` trong Spring HATEOAS.
- Đọc link từ `EntityModel` hoặc `CollectionModel` và gọi URI đích.
- Mở rộng URI template từ link server cung cấp.
- Dùng relation `next`, `self`, `customer` và relation action thay cho việc tự ghép path.
- Thiết kế client xử lý link vắng mặt và lỗi HTTP.
- Kiểm thử client khi server đổi URI nhưng giữ nguyên relation semantics.

## Anti-pattern: client tự xây URI

Giả sử một ứng dụng có API quản lý đơn hàng. Client biết base URL, sau đó tự ghép path và ID:

~~~java
String url = apiBaseUrl + "/api/v1/orders/" + orderId;

Order order = restTemplate.getForObject(url, Order.class);
~~~

Hoặc client đặt route vào hằng số:

~~~java
static final String ORDERS_PATH = "/api/v1/orders";
static final String ORDER_PATH = ORDERS_PATH + "/{id}";
~~~

Ở quy mô nhỏ, code này có vẻ đơn giản. Nhưng client đang biết quá nhiều chi tiết triển khai của server:

- Prefix `/api/v1` là cấu trúc route do server lựa chọn.
- `/orders/{id}` là quy tắc định tuyến nội bộ được đưa vào client.
- Client giả định ID được đặt trực tiếp trong path.
- Client phải biết cách tạo URI cho từng thao tác.
- Client có thể phải thay đổi đồng thời với server dù hợp đồng nghiệp vụ không đổi.

Nếu server đổi từ:

~~~text
/api/v1/orders/42
~~~

sang:

~~~text
/commerce/orders/42
~~~

client vẫn gọi URI cũ và nhận `404 Not Found`. Vấn đề không nằm ở dữ liệu đơn hàng hoặc nghiệp vụ đọc đơn hàng. Client đã gắn chặt vào route cũ.

### Những dạng hard-code thường gặp

| Dạng | Ví dụ | Rủi ro |
|---|---|---|
| Ghép path từ ID | `"/orders/" + id` | Phụ thuộc cấu trúc URI và vị trí ID |
| Lưu route trong constant | `ORDERS_PATH = "/api/v1/orders"` | Mỗi thay đổi route cần sửa và phát hành client |
| Đoán endpoint liên quan | Từ `/orders/42` suy ra `/orders/42/customer` | Server có thể dùng resource hoặc route khác |
| Tự xây pagination URL | `"?page=" + (page + 1)` | Bỏ qua quy tắc phân trang và filter của server |
| Thay version trong chuỗi | Đổi `/v1/` thành `/v2/` | Giả định phiên bản mới giữ cấu trúc path cũ |
| Tự dựng action URI | `"/orders/" + id + "/cancel"` | Không biết action có khả dụng với resource hiện tại hay không |
| Dựa vào thứ tự segment | Cắt `/orders/42` để lấy `42` rồi ghép route khác | Phụ thuộc định dạng URI thay vì semantics |

Các cách trên đều khiến client phải hiểu cấu trúc URI của server. Nếu route thay đổi, client phải được cập nhật dù link relation và ý nghĩa resource có thể vẫn giữ nguyên.

## Vì sao hard-code URI gây coupling?

URI là định danh của resource, còn route là một lựa chọn triển khai. Khi client tự ghép URI, client biến route thành một phần hợp đồng ngầm. Điều này gây ra một số hệ quả:

1. **Thay đổi đồng bộ:** server và tất cả client có thể phải phát hành cùng thời điểm.
2. **Khó triển khai gateway:** khi thêm reverse proxy hoặc chuyển service, prefix và cấu trúc path có thể thay đổi.
3. **Khó điều hướng có điều kiện:** client tự giả định action tồn tại thay vì nhận biết khả năng server công bố.
4. **Lặp logic:** nhiều client tự xây URI theo những quy tắc khác nhau.
5. **Khó tiến hóa API:** server khó tổ chức lại resource hoặc route mà không phá client cũ.
6. **Sai lệch phân trang và lọc:** client tự tính URL tiếp theo có thể làm mất sort, filter, cursor hoặc token phân trang.

Sơ đồ dưới đây mô tả khác biệt:

~~~mermaid
flowchart TD
    subgraph A["Client tự ghép URI"]
      A1["Biết route /api/v1/orders/{id}"]
      A2["Ghép ID và query"]
      A3["Gọi URI được suy đoán"]
      A1 --> A2 --> A3
    end
    subgraph B["Client duyệt hypermedia"]
      B1["Gọi API entry point"]
      B2["Đọc relation orders"]
      B3["Theo href server cung cấp"]
      B4["Đọc relation self / next / customer"]
      B1 --> B2 --> B3 --> B4
    end
~~~

Trong cách thứ hai, client vẫn hiểu vocabulary của API, nhưng không cần biết route cụ thể cho từng resource.

## Client vẫn cần biết điều gì trước?

HATEOAS không loại bỏ mọi cấu hình. Một client cần biết cách bắt đầu và cách diễn giải giao thức:

- **API entry point:** URI gốc hoặc địa chỉ discovery được cung cấp qua cấu hình môi trường, DNS, service registry hay tài liệu tích hợp.
- **Media type:** định dạng hypermedia mà client hỗ trợ, ví dụ `application/hal+json`.
- **Authentication:** cách lấy và gửi credential theo hợp đồng bảo mật.
- **Relation semantics:** ý nghĩa của các relation chuẩn IANA hoặc extension relation đã được tài liệu hóa.
- **Business data:** dữ liệu đầu vào và quy tắc nghiệp vụ mà client cần gửi.

Điểm cần tránh là hard-code mọi URI tài nguyên và action phía sau entry point. Client thường cần một entry point ổn định để bootstrap; sau đó nó nên đi theo các link được server công bố.

Ví dụ cấu hình entry point theo môi trường:

~~~yaml
remote:
  orders:
    entry-point: https://api.example.com/
~~~

Giá trị này là cấu hình triển khai, không phải route của từng resource. Mỗi môi trường có thể đặt entry point khác nhau mà client không phải sửa code.

Không nên lấy ví dụ HATEOAS thành lý do để bỏ qua cấu hình hoặc discovery. Nếu URI entry point cũng thay đổi mà không có cơ chế discovery ổn định, client vẫn cần được cập nhật hoặc nhận cấu hình mới.

## Server công bố link để client khám phá

Một API root có thể công bố collection đơn hàng:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/"
    },
    "orders": {
      "href": "https://api.example.com/commerce/orders"
    }
  }
}
~~~

Client chỉ cần biết relation `orders`. Nó không cần biết route `/commerce/orders`.

Collection có thể công bố các link phân trang:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/commerce/orders?page=0&size=20"
    },
    "next": {
      "href": "https://api.example.com/commerce/orders?page=1&size=20"
    }
  }
}
~~~

Nếu server thay cấu trúc pagination sang cursor:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/commerce/orders?cursor=eyJvZmZzZXQiOjB9"
    },
    "next": {
      "href": "https://api.example.com/commerce/orders?cursor=eyJvZmZzZXQiOjIwfQ"
    }
  }
}
~~~

client vẫn theo relation `next`. Nó không phải biết server chuyển từ `page` sang `cursor`, cũng không phải tự tính token tiếp theo.

Một order resource có thể công bố:

~~~json
{
  "id": "42",
  "status": "SUBMITTED",
  "_links": {
    "self": {
      "href": "https://api.example.com/commerce/orders/42"
    },
    "customer": {
      "href": "https://api.example.com/parties/7"
    },
    "cancel": {
      "href": "https://api.example.com/commerce/order-cancellations/42"
    }
  }
}
~~~

Client tìm `customer` để xem khách hàng và `cancel` để khám phá action hủy. Các link có thể trỏ tới route khác nhau, nhưng relation vẫn diễn đạt ý nghĩa.

## Duyệt relation bằng Traverson

Spring HATEOAS cung cấp `Traverson` cho client muốn duyệt một chuỗi link relation. `Traverson` bắt đầu từ một URI entry point và media type, sau đó tìm relation tiếp theo trong representation nhận được.

Ví dụ, API root công bố link `orders`. Client dùng `Traverson` để lấy collection:

~~~java
import java.net.URI;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.MediaTypes;
import org.springframework.hateoas.client.Traverson;

URI entryPoint = URI.create("https://api.example.com/");

Traverson traverson = new Traverson(
    entryPoint,
    MediaTypes.HAL_JSON
);

ParameterizedTypeReference<CollectionModel<EntityModel<Order>>> responseType =
    new ParameterizedTypeReference<>() {};

CollectionModel<EntityModel<Order>> orders =
    traverson.follow("orders").toObject(responseType);
~~~

Client biết relation `orders` và media type HAL. `Traverson` tải API root, tìm link có relation `orders`, rồi gọi URI được tìm thấy để deserialize collection.

`Traverson` là client đồng bộ dựa trên HTTP client blocking. Nó phù hợp với ứng dụng Spring MVC hoặc tác vụ đồng bộ. Với luồng reactive, hãy dùng `WebClient` đã cấu hình hypermedia decoder và thực hiện cùng nguyên tắc: đọc relation, lấy href, rồi gọi URI server công bố.

Trong ứng dụng thật, hãy lấy `entryPoint` từ cấu hình thay vì đặt URL cố định trong source code. `Order` ở ví dụ là DTO chứa dữ liệu nghiệp vụ; `EntityModel<Order>` giữ thêm các link được server trả về.

### Duyệt link tiếp theo thay vì tự tính page

Nếu collection trả về relation `next`, client có thể theo relation đó:

~~~java
CollectionModel<EntityModel<Order>> nextPage =
    traverson.follow("orders", "next")
        .toObject(responseType);
~~~

Chuỗi relation `orders`, `next` có nghĩa: bắt đầu từ API root, theo link collection `orders`, rồi từ collection theo link `next`. Client không tự tạo query string và không cần biết server dùng offset, page number hay cursor.

Nếu không có relation `next`, client nên hiểu rằng representation hiện tại không công bố trang tiếp theo. Không tự suy ra URL tiếp theo bằng cách tăng số trang.

### Lấy link từ EntityModel

Khi đã có một `EntityModel<Order>`, có thể lấy link theo relation:

~~~java
import org.springframework.hateoas.IanaLinkRelations;
import org.springframework.hateoas.Link;

EntityModel<Order> orderModel = orders.getContent().iterator().next();

Link self = orderModel.getRequiredLink(IanaLinkRelations.SELF);
Link customer = orderModel.getRequiredLink("customer");
~~~

Đoạn lấy phần tử đầu tiên giả định collection không rỗng. Trong ứng dụng thực tế, hãy kiểm tra `orders.getContent().isEmpty()` hoặc chọn item theo dữ liệu nghiệp vụ trước khi lấy link.

`getRequiredLink()` phù hợp khi contract yêu cầu relation phải có. Nếu link có thể vắng mặt, dùng `getLink()` để nhận `Optional<Link>` và xử lý trường hợp không có link:

~~~java
orderModel.getLink("cancel").ifPresent(link -> {
    // Hiển thị hoặc thực hiện quy trình hủy khi relation được công bố.
});
~~~

Không dùng `getRequiredLink()` cho action tùy thuộc quyền hoặc trạng thái nếu action có thể không xuất hiện. Nếu relation bắt buộc theo contract mà server không trả, đó là lỗi hợp đồng cần được phát hiện.

## Gọi URI được cung cấp trong link

Client không cần ghép path để gọi resource liên quan. Nó có thể sử dụng href đã nhận:

~~~java
import java.net.URI;

import org.springframework.core.ParameterizedTypeReference;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestTemplate;

Link customerLink = orderModel.getRequiredLink("customer");
URI customerUri = customerLink.toUri();

ResponseEntity<EntityModel<Customer>> response =
    restTemplate.exchange(
        customerUri,
        HttpMethod.GET,
        HttpEntity.EMPTY,
        new ParameterizedTypeReference<EntityModel<Customer>>() {}
    );
~~~

Ví dụ giả định `RestTemplate` đã được cấu hình message converter hỗ trợ HAL và các hypermedia type cần thiết. Spring HATEOAS cung cấp `HypermediaRestTemplateConfigurer` để đăng ký các converter hypermedia phù hợp. Khi cấu hình client, hãy bảo đảm request gửi `Accept: application/hal+json` và converter có thể deserialize link.

Nếu ứng dụng dùng `WebClient`, nguyên tắc tương tự: lấy URI từ `Link`, sau đó truyền URI đó cho request builder. Cấu hình decoder hypermedia để có thể đọc `EntityModel` hoặc `CollectionModel` từ HAL response.

Không thay đổi URI server cung cấp bằng cách nối thêm path segment. Nếu cần mở rộng template, hãy dùng URI template mà server công bố.

## Xử lý URI template do server cung cấp

Một link có thể là URI template thay vì URI hoàn chỉnh:

~~~json
{
  "_links": {
    "search": {
      "href": "https://api.example.com/commerce/orders{?status,createdAfter}",
      "templated": true
    }
  }
}
~~~

Client không cần tự đoán tên query parameter hoặc cách encode. Nó đọc link và điền các biến đã được công bố:

Giả sử `orderCollection` là `EntityModel` hoặc model hypermedia đã được deserialize từ representation có relation `search`:

~~~java
import java.util.Map;

import org.springframework.hateoas.Link;

Link search = orderCollection.getRequiredLink("search");

String searchUri = search.expand(Map.of(
    "status", "OPEN",
    "createdAfter", "2026-01-01"
)).getHref();
~~~

Sau khi mở rộng, client gửi request tới `searchUri`. Nếu server thay query parameter hoặc cấu trúc template, server cập nhật link; client chỉ cần hiểu semantics của relation và các biến đã được tài liệu hóa.

Không tự nối query string vào href đã có. Việc nối chuỗi có thể tạo query trùng lặp, encode sai ký tự hoặc làm hỏng URI template.

## Action cũng phải được khám phá, không được đoán

Một client không nên tự dựng action URI từ resource URI:

~~~java
// Anti-pattern: client tự đoán route hủy đơn hàng.
String cancelUri = apiBaseUrl + "/orders/" + orderId + "/cancel";
restTemplate.postForLocation(cancelUri, request);
~~~

Server có thể công bố relation `cancel` khi action khả dụng:

~~~json
{
  "id": "42",
  "status": "SUBMITTED",
  "_links": {
    "self": {
      "href": "/commerce/orders/42"
    },
    "cancel": {
      "href": "/commerce/order-cancellations/42"
    }
  }
}
~~~

Client tìm relation và sử dụng link:

~~~java
orderModel.getLink("cancel").ifPresent(cancelLink -> {
    URI cancelUri = cancelLink.toUri();
    // Gửi request tới URI do server công bố.
});
~~~

Link relation tự nó không mô tả đầy đủ HTTP method hoặc body. Nếu client cần biết cách thực hiện action, server có thể công bố affordance bằng API Spring HATEOAS và media type phù hợp, chẳng hạn HAL-FORMS. Client đọc affordance để biết method, input properties và target.

Việc không có link `cancel` có thể có nghĩa action không khả dụng với resource hoặc principal hiện tại. Client nên ẩn thao tác tương ứng hoặc thông báo phù hợp. Server vẫn phải kiểm tra quyền và trạng thái khi nhận request; link không phải ranh giới bảo mật.

## Quan hệ chuẩn và custom relation

Client cần biết semantics của relation, nhưng không cần biết href sẽ có cấu trúc nào. Ưu tiên relation chuẩn IANA khi có ý nghĩa phù hợp, ví dụ:

- `self`: resource hiện tại.
- `next`: trang tiếp theo.
- `collection`: collection liên quan.
- `item`: item trong collection.
- `help`: tài liệu trợ giúp.

Nếu API dùng custom relation, hãy định nghĩa URI relation ổn định và tài liệu hóa semantics. Client cần hiểu vocabulary đã công bố, nhưng không nên phụ thuộc vào URL đích.

Ví dụ, `https://api.example.com/rels/approval` định danh relation phê duyệt. Href của link có thể là `/workflow/approvals/42` hôm nay và `/approvals/42` trong lần triển khai sau. Nếu semantics không đổi, client vẫn tìm relation `approval` và theo href mới.

Không dùng `LinkRelationProvider` để làm client phụ thuộc vào tên class hoặc route. Provider hỗ trợ server tạo relation nhất quán; client chỉ nên dựa vào relation được công bố và tài liệu contract.

## Những trường hợp hard-code URI vẫn hợp lý

Không phải mọi URI xuất hiện trong client đều là anti-pattern. Một số URI thuộc cấu hình hoặc hợp đồng bootstrap:

| URI hoặc giá trị | Có thể cấu hình cố định? | Lý do |
|---|---|---|
| API entry point | Có | Client cần điểm bắt đầu hoặc discovery URI |
| URI của identity provider/token endpoint | Có, theo cấu hình bảo mật | Được cung cấp bởi cấu hình OAuth/OIDC hoặc metadata discovery |
| URI relation chuẩn IANA | Có thể biết trong code | Đây là vocabulary ổn định, không phải route resource cụ thể |
| URI extension relation | Có thể biết qua contract | Là định danh semantics, không phải href của một resource cụ thể |
| URI của từng order/customer | Không nên tự dựng | Server công bố qua link |
| URI trang tiếp theo | Không nên tự tính | Server công bố relation `next` |
| URI action `cancel` | Không nên tự đoán | Server công bố theo khả năng hiện tại |
| URI query/template | Không nên tự tạo từ giả định | Server cung cấp template và biến |

Một entry point có thể được cấu hình theo môi trường. Nếu API công bố một relation `service-desc`, `describedby` hoặc tài liệu discovery, client có thể theo link đó để tìm hiểu thêm contract.

## Xử lý link vắng mặt và lỗi điều hướng

Client HATEOAS cần phân biệt ba trường hợp:

1. **Relation tùy chọn không xuất hiện:** action hoặc resource liên quan hiện không khả dụng. Client không nên tự dựng URI thay thế.
2. **Relation bắt buộc không xuất hiện:** response có thể vi phạm contract. Client nên ghi nhận lỗi tích hợp rõ ràng.
3. **Link có tồn tại nhưng request thất bại:** quyền, trạng thái hoặc điều kiện resource có thể đã thay đổi sau khi representation được tạo. Client xử lý HTTP status như bình thường.

Ví dụ với relation tùy chọn:

~~~java
orderModel.getLink("cancel")
    .ifPresentOrElse(
        link -> showCancelAction(link),
        () -> hideCancelAction()
    );
~~~

Đây là pseudo-code mô tả luồng UI; `showCancelAction` và `hideCancelAction` là hàm của ứng dụng. Trong client thực tế, cần tránh giữ action link vô thời hạn vì trạng thái resource có thể thay đổi.

Không nên tự động thử một URI được đoán khi relation không có. Hành động đó đưa client trở lại coupling với route và có thể vượt qua ý định công bố khả năng của server.

## Kiểm thử để phát hiện coupling URI

Một cách kiểm thử hữu ích là thay đổi href trong fixture hypermedia nhưng giữ nguyên relation. Client đúng sẽ tiếp tục hoạt động vì nó tìm relation thay vì so sánh route.

Ví dụ hai API root có cùng semantics nhưng href khác nhau:

~~~json
{
  "_links": {
    "orders": {
      "href": "https://api.example.com/commerce/orders"
    }
  }
}
~~~

và:

~~~json
{
  "_links": {
    "orders": {
      "href": "https://gateway.example.net/store/order-collection"
    }
  }
}
~~~

Client chỉ yêu cầu relation `orders`, vì vậy cả hai representation đều hợp lệ nếu target đáp ứng semantics đã tài liệu hóa.

Ở phía server, MockMvc test nên xác nhận relation và href được công bố:

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
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
class ApiRootLinksTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publishesOrdersRelation() throws Exception {
        mockMvc.perform(get("/")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.orders.href").exists());
    }
}
~~~

Ở phía client, có thể dùng mock server trả về HAL fixture với href thay đổi và xác nhận client vẫn gọi đúng link. Một test contract nên kiểm tra:

- Client chỉ phụ thuộc API entry point và relation đã tài liệu hóa.
- Client không nối chuỗi `/orders/{id}` hoặc `/cancel`.
- Client dùng href được server cung cấp.
- Client theo `next` thay vì tự tăng page number.
- Client xử lý relation tùy chọn bị thiếu.
- Client không suy luận HTTP method chỉ từ relation.
- Client vẫn hoạt động khi href thay đổi nhưng relation semantics giữ nguyên.

Đừng viết test chỉ assert rằng href luôn bằng một route cụ thể nếu mục tiêu là kiểm tra client không phụ thuộc route. Phía server có thể có contract test cho URI hiện tại, nhưng phía client nên kiểm tra cách tìm relation và theo link.

## Lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Ghép URI từ base URL và ID | Client phụ thuộc cấu trúc route | Theo link `self` hoặc relation phù hợp |
| Lưu toàn bộ path trong constant | Mọi thay đổi route kéo theo phát hành client | Chỉ cấu hình entry point, khám phá resource qua link |
| Tự dựng URL trang kế tiếp | Mất filter, cursor hoặc sort do server quản lý | Theo relation `next` |
| Đoán URI action từ tên resource | Gọi action không tồn tại hoặc không khả dụng | Tìm relation/affordance do server công bố |
| Thay chuỗi `/v1` thành `/v2` | Giả định route và semantics phiên bản mới giống nhau | Khám phá link phiên bản kế tiếp hoặc cấu hình versioning theo contract |
| Xem relation là HTTP method | Gửi sai method hoặc payload | Đọc affordance hoặc tài liệu thao tác |
| Coi mọi link đều bắt buộc | Client lỗi khi action tùy chọn bị lược bỏ | Dùng `getLink()` cho relation tùy chọn |
| Tự đoán URI khi link không có | Vượt qua khả năng server công bố và tái tạo coupling | Xử lý link vắng mặt theo semantics |
| Giữ link action quá lâu | Client có thể dùng link đã hết hiệu lực | Refresh representation và xử lý lỗi HTTP |
| Không cấu hình hypermedia converter | Không deserialize được `EntityModel` hoặc HAL | Đăng ký converter/decoder phù hợp |
| Hard-code custom relation không có tài liệu | Client và server hiểu khác nhau về relation | Công bố URI relation và semantics |

## Ghi nhớ

Hard-code URI ở client biến cấu trúc route của server thành hợp đồng ngầm, khiến thay đổi path, gateway hoặc pagination dễ làm hỏng tích hợp. Client vẫn cần một API entry point và phải hiểu media type, authentication cùng semantics của relation; sau đó nên khám phá URI resource và action từ link server công bố. Spring HATEOAS `Traverson` hỗ trợ duyệt relation, còn `EntityModel` và `Link` cho phép lấy href và gọi resource liên quan. Hãy theo `next` thay vì tự tính trang, theo `cancel` thay vì đoán route, mở rộng URI template do server cung cấp và kiểm thử rằng client vẫn hoạt động khi href thay đổi nhưng relation semantics giữ nguyên.

## Tài liệu tham khảo

- [Spring HATEOAS – Traverson](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#client.traverson)
- [Spring HATEOAS – Client-side Support](https://docs.spring.io/spring-hateoas/docs/current/reference/html/#client)
- [Spring HATEOAS – Traverson API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/client/Traverson.html)
- [Spring HATEOAS – Link API](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/Link.html)
- [RFC 8288 – Web Linking](https://www.rfc-editor.org/rfc/rfc8288.html)
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html)
