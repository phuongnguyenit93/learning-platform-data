# Điều hướng theo rel và mở rộng URI template an toàn

Spring Data REST dùng HAL để mô tả tài nguyên và các liên kết có thể đi tiếp. Client nên tìm liên kết theo **rel** (link relation) trong response rồi gọi URI mà server cung cấp. Khi link có **templated: true**, href là một URI template và cần được mở rộng bằng các biến theo RFC 6570 trước khi gửi request.

Cách này giúp client ít phụ thuộc vào URL cụ thể. Server có thể đổi path hoặc base path mà client vẫn điều hướng được thông qua các relation ổn định.

## 1. HAL mô tả liên kết bằng rel

Một response HAL thường có dữ liệu và đối tượng **_links**:

~~~json
{
  "id": 42,
  "status": "PAID",
  "_links": {
    "self": {
      "href": "https://api.example.com/orders/42"
    },
    "collection": {
      "href": "https://api.example.com/orders"
    },
    "customer": {
      "href": "https://api.example.com/orders/42/customer"
    }
  }
}
~~~

Mỗi key trong **_links** là một relation:

- **self** trỏ tới resource hiện tại.
- **collection** trỏ tới collection chứa resource.
- **customer** trỏ tới association resource của khách hàng liên quan.

Rel mô tả mối quan hệ, không nhất thiết là tên class Java hoặc tên thuộc tính database. Server có thể tùy chỉnh rel; client nên dùng rel mà API công bố thay vì tự suy ra endpoint từ tên entity.

Một link object có thể có metadata như **type**, **title**, **hreflang**, **profile** hoặc **deprecation**. Các trường này giúp client hiểu media type, tiêu đề, ngôn ngữ hoặc trạng thái ngừng hỗ trợ của link.

## 2. Điều hướng theo rel thay vì hard-code URL

Client bắt đầu từ một URI entry point đã biết:

~~~http
GET https://api.example.com/
Accept: application/hal+json
~~~

Response có thể cung cấp link tới collection:

~~~json
{
  "_links": {
    "orders": {
      "href": "https://api.example.com/orders"
    },
    "people": {
      "href": "https://api.example.com/people"
    }
  }
}
~~~

Client lấy href của rel **orders** rồi gọi URI đó:

~~~javascript
const rootResponse = await fetch("https://api.example.com/", {
  headers: { Accept: "application/hal+json" }
});

if (!rootResponse.ok) {
  throw new Error("Cannot load API entry point");
}

const root = await rootResponse.json();
const ordersLink = root._links.orders;

const ordersResponse = await fetch(ordersLink.href, {
  headers: { Accept: "application/hal+json" }
});
~~~

Nếu server đổi path collection từ **/orders** thành **/sales-orders**, client vẫn hoạt động miễn rel **orders** tiếp tục được công bố với href mới.

Không nên tự nối URL theo dạng baseUrl cộng với path cố định. Lấy href từ response giúp client theo đúng mapping, base path và phiên bản API server đang cung cấp.

## 3. Xử lý link đơn, nhiều link và CURIE

Một relation có thể trỏ tới một link hoặc nhiều link. Ví dụ:

~~~json
{
  "_links": {
    "related": [
      {
        "href": "https://api.example.com/orders/42/invoice",
        "type": "application/pdf",
        "title": "Invoice"
      },
      {
        "href": "https://api.example.com/orders/42/receipt",
        "type": "application/pdf",
        "title": "Receipt"
      }
    ]
  }
}
~~~

Client cần xử lý cả hai dạng: nếu relation là object thì dùng link đó; nếu là array thì chọn link dựa trên metadata như **type**, **title** hoặc **hreflang**.

~~~javascript
function linksForRel(links, rel) {
  const value = links?.[rel];
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
}

const documents = linksForRel(order._links, "related");
const invoice = documents.find(link => link.title === "Invoice");
~~~

HAL cũng hỗ trợ compact URI (CURIE) để rút gọn tên relation:

~~~json
{
  "_links": {
    "curies": [
      {
        "name": "ex",
        "href": "https://api.example.com/rels/{rel}",
        "templated": true
      }
    ],
    "ex:approval": {
      "href": "https://api.example.com/orders/42/approval"
    }
  }
}
~~~

Rel **ex:approval** là tên mở rộng theo CURIE **ex**. CURIE dùng để namespace tên relation; nó khác với URI template dùng để tạo URL endpoint. Hãy theo href của relation thực tế như **ex:approval**, không gọi href CURIE như endpoint nghiệp vụ.

## 4. URI template và thuộc tính templated

URI template là URI có các biến cần được cung cấp trước khi gọi. Ví dụ Spring Data REST có thể công bố search link:

~~~json
{
  "_links": {
    "findByStatus": {
      "href": "https://api.example.com/orders/search/findByStatus{?status,page,size,sort}",
      "templated": true
    }
  }
}
~~~

Thuộc tính **templated: true** cho biết href chưa phải URI hoàn chỉnh. Các biến trong ví dụ gồm **status**, **page**, **size** và **sort**.

RFC 6570 định nghĩa các biểu thức thường gặp:

| Biểu thức | Ý nghĩa |
|---|---|
| **{id}** | Chèn biến vào path |
| **{?q,page}** | Mở rộng query string với q và page |
| **{&size,sort}** | Bổ sung biến vào query string đã có |
| **{+path}** | Reserved expansion, giữ một số ký tự dành riêng |
| **{#fragment}** | Mở rộng thành fragment |

Với template:

~~~text
https://api.example.com/orders/search/findByStatus{?status,page,size}
~~~

và giá trị:

~~~json
{
  "status": "PAID",
  "page": 0,
  "size": 20
}
~~~

URI được mở rộng có dạng:

~~~text
https://api.example.com/orders/search/findByStatus?status=PAID&page=0&size=20
~~~

Nếu giá trị chứa ký tự đặc biệt, thư viện URI Template sẽ mã hóa biến đúng vị trí. Ví dụ chuỗi **C++ & Spring Data** cần được mã hóa khi đưa vào query string.

## 5. Mở rộng template bằng thư viện RFC 6570

Nên dùng thư viện hỗ trợ RFC 6570 thay vì tự viết hàm thay placeholder. Với Java và Spring HATEOAS, có thể dùng **org.springframework.hateoas.UriTemplate**:

~~~java
import java.net.URI;
import java.util.Map;
import org.springframework.hateoas.UriTemplate;

String href =
    "https://api.example.com/orders/search/findByStatus{?status,page,size,sort}";

URI target = UriTemplate.of(href).expand(Map.of(
    "status", "PAID",
    "page", 0,
    "size", 20,
    "sort", "createdAt,desc"
));
~~~

Nếu đã có link từ Spring HATEOAS, lấy href từ link rồi mở rộng:

~~~java
Link searchLink = orderCollection.getRequiredLink("findByStatus");

URI target = UriTemplate.of(searchLink.getHref()).expand(Map.of(
    "status", "PAID",
    "page", 0,
    "size", 20
));
~~~

Với JavaScript, chọn một thư viện URI Template tương thích RFC 6570. Đoạn sau mô tả cách gọi ở mức khái niệm; tên hàm cụ thể tùy package:

~~~javascript
const href = orderCollection._links.findByStatus.href;

const target = uriTemplate.expand(href, {
  status: "PAID",
  page: 0,
  size: 20,
  sort: "createdAt,desc"
});

const response = await fetch(target, {
  headers: { Accept: "application/hal+json" }
});
~~~

Không dùng phép thay thế chuỗi thủ công. Cách đó dễ bỏ sót query expansion, biến tùy chọn, dấu phẩy, dấu cách, dấu cộng, dấu ampersand và quy tắc mã hóa theo vị trí.

## 6. Phân biệt link thường và link templated

Client phải kiểm tra thuộc tính **templated**:

~~~javascript
function resolveHref(link, variables, expandTemplate) {
  if (!link || typeof link.href !== "string") {
    throw new Error("HAL link has no href");
  }

  if (link.templated === true) {
    return expandTemplate(link.href, variables);
  }

  return link.href;
}
~~~

- Nếu **templated** là true, dùng RFC 6570 để mở rộng.
- Nếu **templated** không có hoặc là false, dùng href như URI hoàn chỉnh.
- Nếu template yêu cầu biến mà client chưa có, xử lý lỗi rõ ràng thay vì gửi URI còn placeholder.

Không nên giả định mọi href đều là template hoặc mọi template chỉ có dạng biến path đơn giản.

## 7. Mã hóa biến và tránh double encoding

Truyền giá trị gốc cho thư viện URI Template. Không tự URL-encode trước rồi lại đưa vào thư viện, vì có thể tạo double encoding.

Ví dụ giá trị:

~~~text
C++ & Spring Data
~~~

Hãy truyền đúng chuỗi gốc cho biến query. Thư viện sẽ mã hóa dấu cách, dấu cộng và ampersand theo quy tắc RFC 6570.

Các lưu ý:

- Không nối trực tiếp input người dùng vào href.
- Không tự thay dấu cách bằng dấu cộng hoặc chuỗi phần trăm trước khi expansion.
- Không encode toàn bộ URI sau khi đã mở rộng.
- Phân biệt biến nằm trong path với biến nằm trong query.
- Không dùng reserved expansion cho dữ liệu người dùng nếu không cần thiết.
- Kiểm tra kết quả expansion là URI hợp lệ trước khi gọi.

Nếu thư viện chỉ hỗ trợ một phần RFC 6570, kiểm tra các operator và biến mà API đang công bố. Không giả định mọi package có mức hỗ trợ giống nhau.

## 8. Điều hướng theo next, prev và search

Spring Data REST thường cung cấp liên kết điều hướng trong collection representation:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/orders?page=0&size=20"
    },
    "next": {
      "href": "https://api.example.com/orders?page=1&size=20"
    },
    "profile": {
      "href": "https://api.example.com/profile/orders"
    },
    "search": {
      "href": "https://api.example.com/orders/search"
    }
  }
}
~~~

Client nên theo **next** để lấy trang kế tiếp thay vì tự tăng page number. Tương tự, dùng **prev** nếu server công bố. Khi server thay đổi cách phân trang hoặc thêm cursor, client vẫn dựa vào relation mà không cần tự tính URL.

Rel **search** dẫn tới search resource. Client có thể đọc response của search resource để khám phá query method và URI template tương ứng.

Quy trình điều hướng:

1. GET entry point.
2. Theo rel **orders** tới collection.
3. Theo rel **search** để khám phá truy vấn.
4. Chọn rel của query method cần dùng.
5. Nếu link templated, mở rộng bằng thư viện RFC 6570.
6. Gọi URI kết quả và tiếp tục theo các rel trong response.

## 9. Kiểm tra và giới hạn đích đến của link

Link do server trả về là dữ liệu đầu vào của client. Không nên gửi token hoặc cookie tới một host bất kỳ chỉ vì response chứa href đó.

Trước khi gọi link, đặc biệt trong client có bearer token hoặc cookie:

- Chỉ chấp nhận scheme được phép, thường là HTTPS trong production.
- Kiểm tra host và port nằm trong danh sách API origin tin cậy.
- Nếu href tương đối, resolve dựa trên URI của response đã nhận.
- Không tự động chuyển tiếp Authorization tới origin khác.
- Không theo link tới scheme nguy hiểm như javascript hoặc data.
- Không cho phép template variable làm thay đổi host ngoài dự kiến.
- Xử lý redirect theo chính sách bảo mật của client.

Với server-side client, việc fetch href tùy ý còn có thể tạo SSRF. Hãy kiểm tra destination trước khi gửi request và áp dụng network egress policy phù hợp.

HAL giúp client khám phá API, nhưng không có nghĩa mọi URI trong response đều được phép gọi với mọi credential.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Client gọi URL sai sau khi server đổi path | Client hard-code endpoint | Điều hướng theo rel và href |
| Request còn nguyên dấu ngoặc nhọn trong URL | Không kiểm tra templated hoặc chưa expand | Dùng URI Template library khi templated là true |
| Query value chứa dấu ampersand làm tách tham số | Tự nối chuỗi, không mã hóa biến | Truyền giá trị gốc vào RFC 6570 expander |
| Giá trị bị mã hóa hai lần | Encode trước rồi lại expand | Chỉ encode tại một bước do thư viện thực hiện |
| Không tìm thấy rel mong muốn | Quan hệ tùy chỉnh, CURIE hoặc tên rel khác dự kiến | Đọc _links và theo đúng tên server công bố |
| Relation trả về nhiều link | Client giả định link luôn là object | Chuẩn hóa object/array và chọn theo metadata |
| Token bị gửi sang host khác | Tin href mà không kiểm tra origin | Allowlist origin và không chuyển tiếp credential tùy tiện |
| Pagination bỏ sót hoặc lặp URL | Tự tính next thay vì theo link server | Dùng rel next/prev được trả về |

## 11. Checklist cho client

- Gửi Accept phù hợp, thường là **application/hal+json**.
- Bắt đầu từ entry point hoặc URI được cấu hình chính thức.
- Tìm link trong **_links** bằng relation name.
- Hỗ trợ relation có một link hoặc nhiều link.
- Theo rel **self**, **next**, **prev**, **search** và association rel khi cần.
- Kiểm tra **templated: true** trước khi mở rộng href.
- Dùng thư viện RFC 6570 để expand URI template.
- Truyền biến gốc và để thư viện xử lý encoding.
- Không hard-code path hoặc tự thay placeholder.
- Xác thực scheme, host và port trước khi gửi credential.
- Resolve relative URI dựa trên URI của response.
- Xử lý link deprecation và media type theo metadata server công bố.

Tài liệu tham khảo chính thức:

- [Spring Data REST — Repository resources and HAL links](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring HATEOAS — Traverson and client-side navigation](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring HATEOAS — URI templates](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/UriTemplate.html)
- [RFC 6570 — URI Template](https://www.rfc-editor.org/rfc/rfc6570)
- [HAL specification](https://stateless.group/hal_specification.html)
