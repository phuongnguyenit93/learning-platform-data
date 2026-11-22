# Khám phá API từ điểm vào thay vì ghép URI trong client

> **Phạm vi:** Bài học thuộc module **INTEGRATION_API_REST**, chương **Hypermedia**. Người học thực hành thiết kế REST API dựa trên resource, URI, phương thức và mã trạng thái HTTP với hợp đồng dữ liệu rõ ràng. Trọng tâm của bài là biến API thành một tập tài nguyên có thể **khám phá từ điểm vào (entry point)** thông qua liên kết có ngữ nghĩa, thay vì bắt client biết trước và tự nối các đường dẫn. Ví dụ sử dụng HTTP/JSON, HAL, Siren, OpenAPI và Java/Spring; các ý tưởng vẫn áp dụng cho công nghệ tương đương.

## 1. Tình huống: client biết quá nhiều về đường dẫn của server

Giả sử một ứng dụng mobile cần xem danh sách đơn hàng, mở chi tiết, thanh toán và yêu cầu hủy. Một phiên bản client ban đầu được viết như sau:

~~~javascript
// Phản mẫu: client tự giả định cấu trúc đường dẫn.
const base = "https://api.example.test/v1";
const listUrl = base + "/orders";
const orderUrl = base + "/orders/" + orderId;
const cancelUrl = base + "/orders/" + orderId + "/cancel";
const paymentUrl = base + "/orders/" + orderId + "/payments";

// Client cũng tự giả định rằng hủy/thanh toán luôn được phép.
~~~

Khi server chuyển thao tác hủy sang resource có thể theo dõi tại `/order-cancellations`, thay đổi vị trí tài nguyên thanh toán hoặc áp dụng quy tắc chỉ cho hủy khi đơn chưa giao, client cũ có thể hỏng. Client đang phụ thuộc vào **quy tắc tổ chức URI** và **kiến thức trạng thái nghiệp vụ** mà đáng lẽ server phải hướng dẫn qua hợp đồng.

Thiết kế hypermedia đặt ra một hướng khác:

1. Client biết **một điểm vào ổn định**, ví dụ `GET https://api.example.test/entry`.
2. Response công bố các **link relation** như “danh sách đơn”, “tạo đơn” hoặc “hồ sơ hợp đồng”.
3. Client chọn quan hệ có ý nghĩa với mục tiêu, đọc URI tương ứng và tiếp tục theo các liên kết ở representation mới.
4. Khi một hành động không còn hợp lệ, server có thể không quảng bá hành động đó; đồng thời endpoint vẫn **phải** xác thực và kiểm tra quyền/trạng thái khi được gọi.

**Nguyên tắc trung tâm:** client phụ thuộc vào **ý nghĩa quan hệ và hợp đồng biểu diễn**, không phụ thuộc vào phép ghép chuỗi để dự đoán URI của bước tiếp theo.

### 1.1. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt URI của tài nguyên, điểm vào, link relation, link target và **affordance** (khả năng/hành động được quảng bá).
- Thiết kế representation cho phép client tìm các tài nguyên và thao tác tiếp theo.
- Sử dụng hypermedia qua JSON body hoặc HTTP `Link` header; phân biệt với `Location`.
- Đánh giá HAL, Siren, URI Template và giới hạn của từng cách mô tả hành động.
- Viết client đi theo link relation thay vì nối `/orders/{id}` và suy đoán URL.
- Bảo vệ xác thực, phân quyền, SSRF, redirect, cache, idempotency và vòng đời hành động.
- Triển khai ví dụ Java/Spring, mô tả hợp đồng với OpenAPI và kiểm thử khả năng thay đổi URI mà client không bị ảnh hưởng.

## 2. Khái niệm nền tảng: link có ngữ nghĩa khác URL thuần

| Khái niệm | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| **Entry point** | Client bắt đầu khám phá ở đâu? | `https://api.example.test/entry` |
| **Resource** | Tài nguyên có danh tính nào? | Đơn `ord_916` |
| **Representation** | Server công bố gì về tài nguyên tại thời điểm này? | JSON trạng thái đơn và các liên kết |
| **Link target** | Liên kết hướng tới URI nào? | `/v1/orders/ord_916` |
| **Link relation (rel)** | *Vì sao* đích liên quan tới tài nguyên hiện tại? | `self`, `next`, quan hệ nghiệp vụ “orders” |
| **Affordance** | Có thể thực hiện hành động gì, bằng method/media type/đầu vào nào? | Tạo đơn bằng POST theo mẫu request được công bố |
| **Profile / documentation** | Client học ngữ nghĩa của quan hệ và representation ở đâu? | URI profile hoặc tài liệu media type / rel |
| **URI Template** | Server cho phép tạo URI từ biến nào, theo quy tắc nào? | `/v1/orders{?status,limit,cursor}` |

Một URL đơn lẻ chỉ nói “đi tới đâu”. Một link có `rel` nói “**đi tới đó vì mục đích gì**”. Một affordance đủ thông tin còn có thể nói “**thao tác nào được đề nghị, dùng phương thức nào, gửi biểu diễn gì**”.

Ví dụ hai link có cùng target nhưng ý nghĩa khác nhau:

~~~json
{
  "_links": {
    "https://rels.example.test/orders": {
      "href": "/v1/orders"
    },
    "https://rels.example.test/create-order": {
      "href": "/v1/orders",
      "type": "application/json"
    }
  }
}
~~~

Ở đây quan hệ `orders` là “khám phá collection”, còn `create-order` là “đề nghị tạo đơn”. **HAL link không tự mang HTTP method**: client phải biết quy tắc của `create-order` từ tài liệu/profile quan hệ, hoặc dùng định dạng có mô tả action rõ như Siren/HAL-FORMS. Không suy ra rằng mọi link đều phải gọi bằng GET hay cứ có `create-order` thì tự động POST một body bất kỳ.

### 2.1. Relation là hợp đồng ngữ nghĩa, không phải tên method

Một số quan hệ phổ biến có ngữ nghĩa đã được tiêu chuẩn hóa, chẳng hạn `self`, `next`, `prev` và `profile`. Quan hệ nghiệp vụ đặc thù như “tạo đơn”, “yêu cầu hủy”, “xác nhận giao hàng” nên có **URI quan hệ được tài liệu hóa**, ví dụ:

- `https://rels.example.test/orders`: collection đơn hàng có thể xem.
- `https://rels.example.test/create-order`: thao tác tạo đơn với hợp đồng request/response xác định.
- `https://rels.example.test/request-cancellation`: yêu cầu hủy đơn theo điều kiện nghiệp vụ.
- `https://rels.example.test/payment-options`: nơi khám phá lựa chọn thanh toán.

Các URI trên **chỉ là namespace ví dụ**. Tên quan hệ tự đặt không tự trở thành quan hệ tiêu chuẩn của IANA. Tổ chức phải duy trì mô tả ngữ nghĩa ổn định cho client, đặc biệt với action: method, media type, body schema, trạng thái HTTP và hành vi retry.

### 2.2. Hypermedia không thay thế toàn bộ hợp đồng

Client vẫn cần biết:

- Điểm vào hoặc cơ chế bootstrap để tìm điểm vào.
- Media type và cách giải mã representation.
- Ý nghĩa các link relation và action được hỗ trợ.
- Kiểu dữ liệu, validation, trường bắt buộc và cách xử lý lỗi.
- Phương thức HTTP, status code, chính sách xác thực/phân quyền, idempotency và version tương thích.

Hypermedia giúp client **không cần ghi cứng đồ thị URI nội bộ**, nhưng không có nghĩa client trở nên hoàn toàn không cần tài liệu hoặc có thể thực hiện bất kỳ quy trình nghiệp vụ nào mà chưa học semantics.

## 3. Bài toán xuyên suốt: MâyShop Order

Giả sử hệ thống bán hàng có:

- **Khách hàng:** xem đơn của mình, tạo đơn, thanh toán khi được phép, xem giao hàng.
- **Nhân viên hỗ trợ:** xem các đơn thuộc phạm vi được phân quyền và yêu cầu hủy trong trường hợp hợp lệ.
- **Dịch vụ thanh toán:** xử lý giao dịch, trả kết quả bằng webhook đáng tin.
- **Dịch vụ xuất báo cáo:** tạo báo cáo nền, trả URI monitor.

Trạng thái đơn giản hóa:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING_PAYMENT: Tạo đơn
    PENDING_PAYMENT --> PAID: Thanh toán được xác minh
    PENDING_PAYMENT --> CANCELLED: Hủy hợp lệ
    PAID --> SHIPPED: Bàn giao vận chuyển
    PAID --> CANCELLATION_REQUESTED: Đã nhận yêu cầu hủy
    CANCELLATION_REQUESTED --> CANCELLED: Quy trình hủy hoàn tất
    CANCELLATION_REQUESTED --> PAID: Yêu cầu hủy bị từ chối
    SHIPPED --> DELIVERED: Giao hàng thành công
~~~

Đây là **state machine minh họa**, không phải khẳng định mọi hệ thống có cùng quy trình. Điểm quan trọng: **khả năng hành động phụ thuộc trạng thái và quyền hiện tại**. Client không nên tự ghép `/cancel` để thử mọi đơn; server quảng bá quan hệ phù hợp với representation hiện hành.

## 4. Điểm vào: chỉ một URI ổn định để bootstrap

Ví dụ client được cấu hình:

~~~http
GET /entry HTTP/1.1
Host: api.example.test
Accept: application/hal+json
Authorization: Bearer <access-token>
~~~

Response dùng **HAL** (`application/hal+json`):

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Cache-Control: private, no-store

{
  "_links": {
    "self": {
      "href": "https://api.example.test/entry"
    },
    "https://rels.example.test/orders": {
      "href": "/v1/orders"
    },
    "https://rels.example.test/create-order": {
      "href": "/v1/orders",
      "type": "application/json"
    },
    "https://rels.example.test/report-jobs": {
      "href": "/v1/report-jobs"
    },
    "profile": {
      "href": "/profiles/mayshop-order"
    }
  }
}
~~~

**Diễn giải:** client không cần biết `/v1/orders` khi biên dịch. Client tìm link có rel `https://rels.example.test/orders` rồi theo `href`. Nếu ngày mai collection chuyển sang `/v2/customer-orders` hoặc một gateway khác trong phạm vi tích hợp được phép, server có thể cập nhật target ở entry point; client đọc link mới trong điều kiện vẫn hiểu cùng semantics. Điều này giảm coupling với URI, **không tự đảm bảo mọi thay đổi đều tương thích**.

Server có thể trả tập link khác nhau cho user theo quyền, nhưng **ẩn link không thay thế authorization**. Ngay cả khi một user không thấy link tạo đơn, endpoint POST vẫn phải kiểm tra token và policy.

### 4.1. Entry point nên chứa gì và không nên chứa gì?

**Nên chứa** các quan hệ cấp cao, ví dụ collection tài nguyên, profile, phiên bản/hợp đồng được hỗ trợ và hành động bắt đầu hành trình quan trọng. URI nên có vòng đời dài, được công bố chính thức và ít thay đổi.

**Không nên chứa** mọi đơn hàng, từng trường DB, danh sách mọi endpoint nội bộ, khóa bí mật hoặc quy tắc ghép `/v1/{table}/{id}`. Entry point là **bản đồ có ngữ nghĩa**, không phải bản dump router.

Có thể dùng `/.well-known/...` nếu tổ chức áp dụng và đăng ký/thiết kế đúng cơ chế well-known; không mặc nhiên tự đặt một đường dẫn well-known rồi coi đó là chuẩn phổ quát. Trong bài này `/entry` là điểm vào do API công bố.

### 4.2. Mỗi môi trường chỉ cần một bootstrap

Client có thể giữ cấu hình:

~~~text
Production: https://api.example.test/entry
Staging:    https://staging-api.example.test/entry
~~~

Từ đó client đi theo link relation, không ghép thêm `/v1` hoặc phụ thuộc đường dẫn hạ tầng. Nếu link là URI tương đối như `/v1/orders`, client resolve nó **theo URI của representation nguồn** bằng thuật toán URI chuẩn, không nối chuỗi tùy tiện.

## 5. Đi từ entry point tới danh sách và chi tiết đơn

### 5.1. Client chọn rel “orders”

Sau khi chọn rel `https://rels.example.test/orders`, client gọi:

~~~http
GET /v1/orders HTTP/1.1
Host: api.example.test
Accept: application/hal+json
Authorization: Bearer <access-token>
~~~

Response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
Cache-Control: private, no-store

{
  "_links": {
    "self": {"href": "/v1/orders?limit=2"},
    "next": {"href": "/v1/orders?limit=2&cursor=opaque_abc"},
    "https://rels.example.test/create-order": {
      "href": "/v1/orders",
      "type": "application/json"
    }
  },
  "count": 2,
  "_embedded": {
    "https://rels.example.test/order": [
      {
        "id": "ord_916",
        "status": "PENDING_PAYMENT",
        "_links": {
          "self": {"href": "/v1/orders/ord_916"}
        }
      },
      {
        "id": "ord_917",
        "status": "SHIPPED",
        "_links": {
          "self": {"href": "/v1/orders/ord_917"}
        }
      }
    ]
  }
}
~~~

`count` trong ví dụ chỉ là **số phần tử của trang hiện tại**, không phải tổng số đơn trong database. Nếu API cần tổng số bản ghi, phải có hợp đồng và cân nhắc chi phí đếm. Link `next` là cách điều hướng trang tiếp: client không cần biết thuật toán cursor hay tự xây `?page=2`. Tập `_embedded` cung cấp dữ liệu tóm tắt; link `self` ở từng item giúp mở chi tiết đúng URI server công bố.

**Lưu ý nhất quán ví dụ:** request ban đầu `GET /v1/orders` và `_links.self` là URL chuẩn hóa có `limit=2` (mặc định của ví dụ phân trang), nhằm minh họa server có thể cung cấp URI canonical cho representation. Khi triển khai thật phải xác định rõ page size mặc định và đảm bảo body thực sự khớp với response được gắn rel `self`.

### 5.2. Mở chi tiết đơn: theo `self` chứ không nối ID

Client chọn `_embedded[order][0]._links.self.href` và GET:

~~~http
GET /v1/orders/ord_916 HTTP/1.1
Host: api.example.test
Accept: application/hal+json
Authorization: Bearer <access-token>
~~~

Response ở trạng thái đang chờ thanh toán:

~~~json
{
  "id": "ord_916",
  "status": "PENDING_PAYMENT",
  "currency": "VND",
  "totalAmount": "250000",
  "_links": {
    "self": {"href": "/v1/orders/ord_916"},
    "collection": {"href": "/v1/orders"},
    "https://rels.example.test/payment-options": {
      "href": "/v1/orders/ord_916/payment-options"
    },
    "https://rels.example.test/request-cancellation": {
      "href": "/v1/orders/ord_916/cancellations",
      "type": "application/json"
    }
  }
}
~~~

Đơn đã được giao có thể có representation khác:

~~~json
{
  "id": "ord_917",
  "status": "SHIPPED",
  "currency": "VND",
  "totalAmount": "170000",
  "_links": {
    "self": {"href": "/v1/orders/ord_917"},
    "collection": {"href": "/v1/orders"},
    "https://rels.example.test/tracking": {
      "href": "/v1/shipments/shp_45"
    }
  }
}
~~~

Client nhìn thấy `tracking` mà không tự suy luận từ `orderId` ra shipment ID. Link hủy không xuất hiện vì server hiện không quảng bá hành động hủy trực tiếp trong trạng thái này. Song nếu client lưu link hủy cũ rồi gọi lại, server **vẫn phải kiểm tra** trạng thái hiện hành và trả lỗi phù hợp, chẳng hạn `409 Conflict`, vì link có thể đã cũ hoặc quyền bị thu hồi.

### 5.3. Đừng hiểu “có link” thành “chắc chắn hành động sẽ thành công”

Link thể hiện một **khả năng được đề nghị tại thời điểm tạo representation**. Đến khi client gọi:

- Trạng thái có thể đã đổi do một tác nhân khác.
- Token có thể hết hạn hoặc quyền đã bị thu hồi.
- Tài nguyên có thể bị xóa hoặc tạm thời không sẵn sàng.
- Yêu cầu có thể không qua validation, limit hoặc idempotency check.

Do đó server không được coi việc phát link là lần phân quyền duy nhất. Hypermedia **hướng dẫn client**, còn backend **thi hành bất biến và authorization**.

## 6. Biểu diễn action: HAL link khác Siren action

Trong HAL, `_links` mô tả quan hệ và target; bản thân HAL đơn thuần không chỉ ra toàn bộ method, schema body hoặc tác động. Để mô tả action thực thi với đủ affordance, có thể dùng một media type hỗ trợ action như **Siren**, hoặc mở rộng bằng **HAL-FORMS**, profile/metadata của ứng dụng.

Ví dụ minh họa bằng Siren cho đơn đang được phép yêu cầu hủy:

~~~http
HTTP/1.1 200 OK
Content-Type: application/vnd.siren+json

{
  "class": ["order"],
  "properties": {
    "id": "ord_916",
    "status": "PENDING_PAYMENT"
  },
  "links": [
    {
      "rel": ["self"],
      "href": "/v1/orders/ord_916"
    }
  ],
  "actions": [
    {
      "name": "request-cancellation",
      "title": "Yêu cầu hủy đơn",
      "method": "POST",
      "href": "/v1/orders/ord_916/cancellations",
      "type": "application/json",
      "fields": [
        {
          "name": "reason",
          "type": "text"
        }
      ]
    }
  ]
}
~~~

Mẫu này thể hiện **phương thức POST**, nơi gửi và trường yêu cầu. Nhưng kiểu `text` hoặc tên `reason` chưa mô tả đầy đủ enum, độ dài, quyền, ràng buộc trạng thái hay idempotency. Những quy tắc đó phải được tài liệu hóa và kiểm thử. Ví dụ định dạng theo media type chỉ có giá trị khi client thật sự hỗ trợ media type ấy; không tự đổi Content-Type từ HAL sang Siren mà không có content negotiation/hợp đồng chuyển đổi.

### 6.1. Nên chọn định dạng nào?

| Cách thể hiện | Phù hợp | Giới hạn |
|---|---|---|
| **HAL** (`application/hal+json`) | Navigation qua `_links` và dữ liệu lồng trong `_embedded` | Không tự mô tả đầy đủ HTTP method/body cho action |
| **Siren** (`application/vnd.siren+json`) | Entity, links và các action có method/fields | Client phải hỗ trợ cú pháp, semantics và version của Siren |
| **HAL-FORMS** | Mẫu action/submit trên cơ sở HAL | Thêm profile/template contract và độ phức tạp |
| **JSON:API links** | API tuân thủ JSON:API, cần link và cấu trúc resources chuẩn của nó | Không tự diễn giải mọi workflow/action ngoài quy ước JSON:API |
| **HTTP Link header** | Công bố relation ở tầng header, dùng cả với body không phải JSON | Chỉ có link metadata; phải thống nhất cách client hiểu và theo |
| **JSON tùy biến có `links/actions`** | Hệ sinh thái đóng với contract đơn giản | Phải tự định nghĩa parser, semantics, versioning và tooling |

Không có một định dạng tốt nhất cho mọi đội ngũ. Chọn dựa trên yêu cầu discoverability, SDK/client thực tế, mức phức tạp workflow, chuẩn hóa và chi phí vận hành. Tránh “giống HAL một chút” nhưng lại gắn media type HAL sai cấu trúc.

## 7. HTTP `Link` header và `Location`: hai khái niệm khác nhau

Hypermedia có thể hiện diện trong response header:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Link: </v1/orders?limit=20&cursor=opaque_next>; rel="next"
Link: </profiles/orders>; rel="profile"

{"data":[{"id":"ord_916"}]}
~~~

Header `Link` cho phép công bố target và relation theo ngữ nghĩa Web Linking. Client vẫn cần giải mã đúng dấu phân cách, dấu ngoặc, tham số và resolve URI tương đối theo ngữ cảnh. Đừng parse bằng `split(",")` hoặc `split(";")` một cách tùy tiện, vì cú pháp link và quoted-string có thể phức tạp; dùng parser tương thích HTTP Link.

### 7.1. So sánh `Location` và `Link`

| Header | Ý nghĩa trong HTTP | Ví dụ |
|---|---|---|
| `Location` | Định danh tài nguyên chính mới tạo với `201`; hoặc URI đích của redirect `3xx` | `201 Location: /v1/orders/ord_916` |
| `Link` | Mô tả một hay nhiều liên kết có relation so với response context | `Link: </v1/orders?cursor=...>; rel="next"` |
| `Content-Location` | Định danh URI tương ứng representation trong response theo HTTP semantics | Không phải cách thay thế `Location` hay `Link` |

Ví dụ tạo đơn đồng bộ:

~~~http
HTTP/1.1 201 Created
Location: https://api.example.test/v1/orders/ord_916
Link: </v1/orders>; rel="collection"
Content-Type: application/hal+json

{
  "id": "ord_916",
  "_links": {
    "self": {"href": "/v1/orders/ord_916"},
    "collection": {"href": "/v1/orders"}
  }
}
~~~

`Location` chỉ **tài nguyên đã tạo**, còn `Link` và `_links` giúp khám phá tài nguyên liên quan. Có thể dùng cả hai; nếu lặp cùng relation trong body và header, phải đảm bảo chúng nhất quán.

### 7.2. Công việc bất đồng bộ cũng cần đường theo dõi

Nếu POST yêu cầu tạo báo cáo mất nhiều thời gian:

~~~http
HTTP/1.1 202 Accepted
Location: https://api.example.test/v1/operations/op_42
Retry-After: 3
Content-Type: application/hal+json

{
  "id": "op_42",
  "status": "QUEUED",
  "_links": {
    "self": {"href": "/v1/operations/op_42"}
  }
}
~~~

Ở đây quy ước `Location` trỏ tới **operation monitor** do ứng dụng công bố; `202` không tự bắt buộc mọi API dùng header này. Khi task chạy xong, response từ `GET /operations/op_42` có thể cung cấp rel `https://rels.example.test/result` dẫn tới báo cáo, hoặc server trả `303 See Other` với `Location` đến tài nguyên kết quả. Quyết định phải được mô tả rõ, nhất là khi một số client tự động theo redirect.

## 8. URI Template: khi nào được phép “tạo” URI?

Yêu cầu “đừng ghép URI” không có nghĩa client không bao giờ được cung cấp tham số. Một collection có thể hỗ trợ filter, sort và pagination. Điểm khác biệt là **server công bố URI Template và biến hợp lệ**, còn client áp dụng thuật toán mở rộng theo hợp đồng, thay vì tự giả định thứ tự và cú pháp path/query.

Ví dụ HAL có `templated: true`:

~~~json
{
  "_links": {
    "https://rels.example.test/search-orders": {
      "href": "/v1/orders{?status,limit,cursor}",
      "templated": true
    }
  }
}
~~~

Đây là một **URI Template** theo cú pháp `{?status,limit,cursor}`. Với các biến:

~~~json
{"status":"PAID","limit":20}
~~~

Kết quả logic:

~~~text
/v1/orders?status=PAID&limit=20
~~~

Một thư viện URI Template đúng chuẩn phải encode giá trị và áp dụng đúng cú pháp của biểu thức. Không dùng `String.replace("{status}", rawInput)` với dữ liệu tùy ý, vì ký tự `&`, `#`, `?`, dấu cách và Unicode có thể làm thay đổi URI hoặc gây lỗi.

### 8.1. Các quy tắc cần công bố đi cùng template

- Biến nào được phép và kiểu dữ liệu của nó: `status` là enum, `limit` là số nguyên 1–100, `cursor` là token opaque.
- Biến nào bắt buộc, mặc định, có thể bỏ qua và có thể lặp.
- Ý nghĩa filter, sort, timezone, currency và độ dài query cho phép.
- Tài nguyên nào được trả và quyền truy cập nào áp dụng.
- Cách phân trang: nếu server đã trả link `next` hoàn chỉnh, client nên **đi theo next** thay vì tự sửa `cursor`.

Hypermedia template **không loại bỏ validation**. Client vẫn có thể tạo URL ngoài ngưỡng, cố tình sửa query hoặc truy cập link đã hết hạn; server phải từ chối theo hợp đồng.

### 8.2. URI Template và link cụ thể có vai trò khác nhau

| Loại | Ví dụ | Cách client sử dụng |
|---|---|---|
| Link cụ thể | `/v1/orders/ord_916` | GET URI chính xác được cung cấp |
| Link trang kế tiếp | `/v1/orders?cursor=opaque_next` | GET nguyên link, không đoán cursor mới |
| URI Template | `/v1/orders{?status,limit}` | Expand bằng thư viện theo biến/kiểu đã công bố |
| Action có body | `POST /v1/orders/ord_916/cancellations` | Dùng method và schema do profile/action mô tả; không đoán từ href |

Một liên kết template hỗ trợ query dựa trên tham số của người dùng, nhưng không trao quyền tìm kiếm biểu thức SQL tùy ý. Giữ allowlist field–operator, filter cost budget và phân quyền nhất quán.

## 9. Đọc API theo một hành trình: link → representation → action → link

~~~mermaid
sequenceDiagram
    participant C as Client
    participant API as REST API
    C->>API: GET /entry
    API-->>C: 200 + rel orders/create-order
    C->>API: GET href của rel orders
    API-->>C: 200 + item self + next
    C->>API: GET href self của item
    API-->>C: 200 + rel payment-options/cancellation
    C->>API: POST action theo semantics đã công bố
    API-->>C: 201 + Location hoặc 202 + monitor
    C->>API: GET URI kết quả/monitor
    API-->>C: 200 representation + rel tiếp theo
~~~

Trục chính của workflow là **relation**, không phải chuỗi route. Cả khi kết quả là `201` hoặc `202`, client đọc `Location` theo ngữ nghĩa tương ứng, sau đó dùng link mới để tiếp tục. Client không cần đoán ID, nơi lưu hay version endpoint đằng sau resource.

### 9.1. Client nên biết trước điều gì?

Một client đặt hàng cần hiểu workflow, ví dụ:

1. Tìm `orders` để hiển thị danh sách.
2. Tìm `create-order`, đọc yêu cầu body/method từ tài liệu hoặc affordance, gửi request.
3. Sau `201`, theo `Location` của đơn mới rồi đọc representation.
4. Nếu có `payment-options`, hiển thị các phương án thanh toán; không giả định mọi đơn đều thanh toán được.
5. Nếu có `request-cancellation`, có thể đề nghị hủy theo hợp đồng.
6. Với `next`, tiếp tục duyệt danh sách mà không tự tạo offset/cursor.

**Điều client cần biết là mục tiêu và ý nghĩa tương tác**, còn đích URI cụ thể do API cung cấp. Không cần viết một interpreter hypermedia tổng quát mới có thể hưởng lợi; một client chuyên biệt hỗ trợ một tập rel hữu hạn là lựa chọn thực tế.

### 9.2. Thiếu link không phải tình trạng lỗi HTTP

Nếu representation không có rel `request-cancellation`, client nên không hiển thị hành động hủy (hoặc hiển thị disabled với giải thích UX nếu domain contract có lý do). Không nên tự tạo URL `/cancel` để “thử vận may”. Tuy nhiên, thiếu link có thể do quyền, trạng thái, phiên bản profile hoặc server policy; client **không nên suy ra nguyên nhân duy nhất** trừ khi representation cho biết rõ.

## 10. So sánh hai kiểu client

**Client dựa trên path tĩnh:**

~~~javascript
async function cancelOrder(orderId, reason) {
  return http.post(
    "/v1/orders/" + encodeURIComponent(orderId) + "/cancel",
    {reason}
  );
}
~~~

**Client dựa trên affordance/hypermedia:**

~~~text
orderRepresentation = GET(orderLink.href)
action = findAction(
    orderRepresentation,
    "https://rels.example.test/request-cancellation"
)
if action absent:
    disableCancellation()
else:
    validateActionContract(action)
    POST(action.href, {"reason": selectedReason})
    followLocationOrRelevantRel()
~~~

Trong ví dụ thứ hai, `POST` là quy tắc đã được client biết từ semantics của relation/affordance, **không phải suy đoán từ URL**. Nếu representation chỉ có HAL `_links` mà không có method, client cần tài liệu rel `request-cancellation` nói rằng đó là POST với media type và schema cụ thể. Nếu dùng Siren action, client có thể đọc method ngay từ representation.

Thay đổi route từ `/v1/orders/{id}/cancel` sang `/v1/orders/{id}/cancellations` không nhất thiết khiến client thứ hai hỏng, miễn relation và hành vi còn tương thích và client có quyền gọi target mới.

## 11. Thiết kế client khám phá API một cách bền vững

### 11.1. Thuật toán tổng quát

Một client hỗ trợ hypermedia không nên cố “đoán dự phòng” các đường dẫn. Luồng xử lý cơ bản:

~~~text
entry = GET(configuredEntryPoint, Accept=expectedMediaType)
assertSuccessful(entry)
root = parseByContentType(entry)

ordersLink = findRelation(root, "https://rels.example.test/orders")
if ordersLink missing:
    showFeatureUnavailable()
else:
    ordersUri = safelyResolve(entry.uri, ordersLink.href)
    page = GET(ordersUri)
    renderOrders(page)

    while userRequestsNextPage:
        next = findRelation(page, "next")
        if next missing:
            stopPagination()
        else:
            page = GET(safelyResolve(page.uri, next.href))
            appendOrders(page)

    selected = findRelation(selectedOrderItem, "self")
    order = GET(safelyResolve(page.uri, selected.href))
    renderOrderAndAvailableActions(order)
~~~

Thuật toán này giả định client **đã hiểu** media type và quan hệ `orders`/`next`/`self`. Client phải xử lý status không thành công, quyền, timeout, representation không hợp lệ, nhiều target cho một relation và URI bên ngoài miền tin cậy.

### 11.2. Ba điều client tuyệt đối không nên mặc định

1. **Không tự coi rel là path:** `orders` không đồng nghĩa với chuỗi `/orders`. Target có thể là `/v2/purchases` hoặc URI khác do server công bố.
2. **Không tự suy method từ route:** `/orders/{id}/cancellations` không thể được gọi bằng POST chỉ vì tên path; method phải đến từ affordance hoặc tài liệu relation.
3. **Không tin một link tồn tại mãi:** URI có thể đổi, trạng thái hành động có thể hết hiệu lực và resource có thể bị xóa. Client phải chấp nhận `404`, `409`, `410` hoặc `403` theo ngữ nghĩa hợp đồng.

### 11.3. Client HTTP tối thiểu với Java

Ví dụ Java 17+ dùng `HttpClient` và Jackson để **đọc một rel** từ HAL root; tập trung vào discovery, không phải SDK hoàn chỉnh:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Set;

public final class DiscoveredOrdersClient {
    private static final String ORDERS_REL =
        "https://rels.example.test/orders";
    private static final Set<String> ALLOWED_HOSTS =
        Set.of("api.example.test"); // Cấu hình theo môi trường tin cậy.

    private final HttpClient http = HttpClient.newHttpClient();
    private final ObjectMapper json = new ObjectMapper();
    private final URI entry = URI.create("https://api.example.test/entry");

    public JsonNode loadOrders(String token) throws Exception {
        HttpRequest rootReq = HttpRequest.newBuilder(entry)
            .header("Accept", "application/hal+json")
            .header("Authorization", "Bearer " + token)
            .GET()
            .build();
        HttpResponse<String> root = http.send(
            rootReq, HttpResponse.BodyHandlers.ofString());
        if (root.statusCode() != 200) {
            throw new IllegalStateException(
                "Entry point HTTP " + root.statusCode());
        }

        JsonNode entryJson = json.readTree(root.body());
        JsonNode ordersLink =
            entryJson.path("_links").path(ORDERS_REL);
        String href = ordersLink.path("href").asText(null);
        if (href == null || href.isBlank()
                || ordersLink.path("templated").asBoolean(false)) {
            throw new IllegalStateException(
                "Orders link missing or unsupported");
        }

        URI ordersUri = resolveAllowed(entry, href);
        HttpRequest listReq = HttpRequest.newBuilder(ordersUri)
            .header("Accept", "application/hal+json")
            .header("Authorization", "Bearer " + token)
            .GET()
            .build();
        HttpResponse<String> list = http.send(
            listReq, HttpResponse.BodyHandlers.ofString());
        if (list.statusCode() != 200) {
            throw new IllegalStateException(
                "Orders HTTP " + list.statusCode());
        }
        return json.readTree(list.body());
    }

    static URI resolveAllowed(URI base, String href) {
        URI target = base.resolve(href).normalize();
        if (!"https".equalsIgnoreCase(target.getScheme())
                || target.getHost() == null
                || !ALLOWED_HOSTS.contains(
                    target.getHost().toLowerCase())) {
            throw new SecurityException("Untrusted hypermedia link");
        }
        if (target.getUserInfo() != null) {
            throw new SecurityException("Credentials in URL");
        }
        return target;
    }
}
~~~

Đây là mẫu nhỏ, **không phải thư viện client production**. Trong ứng dụng thật cần kiểm tra Content-Type, schema, timeout, lỗi mạng, redirect, status `401/403/429/503`, token audience, xử lý nhiều link và cho phép cấu hình **cổng/host tin cậy** theo môi trường. Nếu client hỗ trợ link sang đối tác ngoài, không nên gửi bearer token của API nội bộ sang đối tác; phải sử dụng cơ chế cấp quyền riêng.

Hàm `resolveAllowed` minh họa nguyên tắc kiểm tra đích. Khi có IPv6, IDN, redirect chain, hostname thay đổi qua DNS, proxy hoặc link tới storage download, chính sách mạng/credential cần sâu hơn danh sách một host. Không dùng host allowlist như biện pháp duy nhất chống SSRF trong các thành phần server-side có quyền truy cập mạng nội bộ.

### 11.4. Một rel có thể có nhiều link

Một relation có thể có nhiều đích hoặc các phiên bản representation, ngôn ngữ, loại media khác nhau. Một số media type cho phép một relation ánh xạ sang danh sách link. Client nên có quy tắc lựa chọn theo `type`, `hreflang`, profile hoặc điều kiện khác của contract, không mặc định parser luôn thấy một object.

Ví dụ client hỗ trợ cả `application/json` và `application/pdf` khi tải một báo cáo cần chọn link theo loại định dạng được công bố, không lấy link đầu tiên rồi kỳ vọng JSON.

## 12. Thiết kế server Java/Spring: công bố rel thay vì xuất router nội bộ

Ví dụ Spring MVC dưới đây sử dụng Map để thể hiện đúng shape HAL; nếu hệ thống lớn có thể dùng Spring HATEOAS hoặc thư viện hypermedia hỗ trợ media type, link builder và representation model. Mục tiêu là hiểu **trách nhiệm server**, không phải ép tất cả dự án dùng một thư viện.

### 12.1. Controller cho entry point

~~~java
import java.net.URI;
import java.security.Principal;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EntryPointController {
    private static final String ORDERS_REL =
        "https://rels.example.test/orders";
    private static final String CREATE_ORDER_REL =
        "https://rels.example.test/create-order";

    private final URI publicBaseUri =
        URI.create("https://api.example.test");
    private final OrderAuthorization authorization;

    public EntryPointController(OrderAuthorization authorization) {
        this.authorization = authorization;
    }

    @GetMapping(value = "/entry", produces = "application/hal+json")
    public ResponseEntity<Map<String, Object>> entry(Principal principal) {
        Map<String, Object> links = new LinkedHashMap<>();
        links.put("self",
            Map.of("href", publicBaseUri.resolve("/entry").toString()));
        links.put(ORDERS_REL,
            Map.of("href", publicBaseUri.resolve("/v1/orders").toString()));
        links.put("profile",
            Map.of("href", publicBaseUri.resolve(
                "/profiles/mayshop-order").toString()));

        if (authorization.canCreateOrder(principal)) {
            links.put(CREATE_ORDER_REL,
                Map.of("href",
                    publicBaseUri.resolve("/v1/orders").toString(),
                       "type", "application/json"));
        }
        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType("application/hal+json"))
            .cacheControl(CacheControl.noStore())
            .body(Map.of("_links", links));
    }
}

interface OrderAuthorization {
    boolean canCreateOrder(Principal caller);
    boolean canRequestCancellation(Principal caller, OrderView order);
}

record OrderView(String id, String status, String currency) {}
~~~

**Chú ý:** domain trong code là ví dụ; `OrderAuthorization` phải dùng danh tính đáng tin cậy do Spring Security xác thực, không dựa vào một header tùy ý. `publicBaseUri` phải được đưa từ cấu hình môi trường hoặc xây từ metadata của proxy **đã được tin cậy**; đừng sử dụng bừa giá trị `Host`/`Forwarded` do client có thể giả để sinh link độc hại.

### 12.2. Controller chi tiết với affordance theo trạng thái

~~~java
import java.net.URI;
import java.security.Principal;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/v1/orders")
public class OrderHypermediaController {
    private static final String CANCEL_REL =
        "https://rels.example.test/request-cancellation";
    private static final String PAYMENT_REL =
        "https://rels.example.test/payment-options";

    private final URI publicBaseUri =
        URI.create("https://api.example.test");
    private final OrderReadUseCase orders;
    private final OrderAuthorization authorization;

    public OrderHypermediaController(
            OrderReadUseCase orders, OrderAuthorization authorization) {
        this.orders = orders;
        this.authorization = authorization;
    }

    @GetMapping(value = "/{id}", produces = "application/hal+json")
    public ResponseEntity<Map<String, Object>> get(
            @PathVariable String id, Principal principal) {
        // findVisibleOrder phải kiểm tra owner/tenant và quyền đọc.
        OrderView order = orders.findVisibleOrder(principal, id);
        URI orderUri =
            publicBaseUri.resolve("/v1/orders/" + order.id());

        Map<String, Object> links = new LinkedHashMap<>();
        links.put("self", Map.of("href", orderUri.toString()));
        links.put("collection", Map.of("href",
            publicBaseUri.resolve("/v1/orders").toString()));

        if ("PENDING_PAYMENT".equals(order.status())) {
            links.put(PAYMENT_REL, Map.of("href",
                orderUri.toString() + "/payment-options"));
        }
        if (authorization.canRequestCancellation(principal, order)) {
            links.put(CANCEL_REL, Map.of(
                "href", orderUri.toString() + "/cancellations",
                "type", "application/json"));
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("id", order.id());
        body.put("status", order.status());
        body.put("currency", order.currency());
        body.put("_links", links);

        return ResponseEntity.ok()
            .contentType(MediaType.parseMediaType("application/hal+json"))
            .cacheControl(CacheControl.noStore())
            .body(body);
    }
}

interface OrderReadUseCase {
    OrderView findVisibleOrder(Principal caller, String id);
}
~~~

Đoạn mã cố ý chỉ cho thấy **sự lựa chọn link dựa trên domain và authorization**. URI ID phải là định danh do server tạo, có dạng đã validate/encode; đừng nối raw user input vào URI đích. Trong mã thật nên dùng URI builder có encoding đúng, tránh cấu trúc `String + "/cancellations"` nếu URI có query, fragment hoặc path thay đổi; sử dụng `LinkFactory` thống nhất. Quan trọng hơn, endpoint POST hủy phải **tự kiểm tra lại** quyền và trạng thái trong transaction; không thể tin rằng client chỉ gọi được vì GET trước đó đã trả link hủy.

Nếu dùng Spring HATEOAS, có thể đóng gói `Link`, `EntityModel` hoặc representation model phù hợp để giảm thao tác thủ công, nhưng **đừng để tên controller method tự quyết định toàn bộ semantics**. Quan hệ nghiệp vụ vẫn cần được định nghĩa, documentation và contract tests.

### 12.3. Tạo resource và trả `Location` nhất quán

~~~java
import java.net.URI;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CreateOrderController {
    private final OrderCommandUseCase useCase;
    private final URI publicBaseUri =
        URI.create("https://api.example.test");

    public CreateOrderController(OrderCommandUseCase useCase) {
        this.useCase = useCase;
    }

    @PostMapping(value = "/v1/orders", consumes = "application/json")
    public ResponseEntity<?> create(
            @RequestBody CreateOrderRequest request) {
        // Service thật phải xác thực, phân quyền, kiểm tra
        // dữ liệu, giá, trạng thái, idempotency và lưu bền vững.
        CreatedOrder created = useCase.createAuthorized(request);
        URI location = publicBaseUri.resolve(
            "/v1/orders/" + created.id());
        return ResponseEntity.created(location)
            .contentType(org.springframework.http.MediaType
                .parseMediaType("application/hal+json"))
            .body(Map.of(
                "id", created.id(),
                "status", created.status(),
                "_links", Map.of(
                    "self", Map.of("href", location.toString()))));
    }
}

record CreateOrderRequest(String shippingAddressId) {}
record CreatedOrder(String id, String status) {}

interface OrderCommandUseCase {
    CreatedOrder createAuthorized(CreateOrderRequest request);
}
~~~

Snippet là ví dụ riêng để minh họa HTTP response; khi tích hợp cần lấy caller từ security context/Principal, bổ sung DTO/validation đúng nghiệp vụ và lắp `LinkFactory` dùng chung. Không nên coi tên `createAuthorized` tự bảo đảm xác thực; trách nhiệm thực thi phải có code, policy và test. Có thể trả body rỗng với `201` nếu hợp đồng chỉ cần Location, nhưng có body HAL giúp client tiếp tục khám phá ngay.

## 13. Hợp đồng OpenAPI và hypermedia cần bổ sung cho nhau

OpenAPI mô tả những endpoint và response có thể xảy ra, giúp phát triển SDK, validation và kiểm thử. Hypermedia đưa **các liên kết và affordance hiện hành** vào phản hồi runtime. Cả hai nên khớp nhau:

| Câu hỏi | OpenAPI | Hypermedia runtime |
|---|---|---|
| POST tạo đơn nhận trường gì? | `requestBody` schema | Action/profile có thể dẫn tới schema |
| POST thành công trả gì? | `201` + header `Location` + response schema | Link `self` của đơn mới trong body |
| Một đơn có thể hủy lúc này không? | Mô tả điều kiện/domain errors tổng quát | Quan hệ `request-cancellation` xuất hiện khi có thể đề nghị |
| Trang tiếp theo nằm đâu? | Schema mô tả `next` | Response hiện tại chứa href thật |
| Phải xử lý lỗi nào? | `400/401/403/409/412/429/5xx` và Problem Details | Representation lỗi có thể kèm liên kết tới hướng xử lý |

### 13.1. OpenAPI rút gọn cho entry point và đơn hàng

~~~yaml
openapi: 3.1.0
info:
  title: Mayshop Hypermedia API
  version: 1.0.0
paths:
  /entry:
    get:
      operationId: discoverApi
      summary: Điểm vào để khám phá các quan hệ được hỗ trợ
      security:
        - bearerAuth: []
      responses:
        '200':
          description: Bản đồ link của API theo quyền caller
          content:
            application/hal+json:
              schema:
                $ref: '#/components/schemas/EntryPoint'
        '401':
          description: Cần xác thực
  /v1/orders:
    post:
      operationId: createOrder
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [shippingAddressId]
              properties:
                shippingAddressId: {type: string}
      responses:
        '201':
          description: Đơn đã được tạo
          headers:
            Location:
              required: true
              schema: {type: string, format: uri-reference}
          content:
            application/hal+json:
              schema:
                $ref: '#/components/schemas/Order'
          links:
            CreatedOrder:
              operationId: getOrder
              parameters:
                id: '$response.body#/id'
        '400': {description: Request không hợp lệ}
        '403': {description: Không được phép tạo đơn}
        '409': {description: Xung đột trạng thái hoặc idempotency}
  /v1/orders/{id}:
    get:
      operationId: getOrder
      security:
        - bearerAuth: []
      parameters:
        - name: id
          in: path
          required: true
          schema: {type: string}
      responses:
        '200':
          description: Đơn được phép xem cùng link hiện hành
          content:
            application/hal+json:
              schema:
                $ref: '#/components/schemas/Order'
        '404': {description: Không tìm thấy hoặc không công bố đơn}
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
  schemas:
    HalLink:
      type: object
      required: [href]
      properties:
        href: {type: string}
        templated: {type: boolean}
        type: {type: string}
    EntryPoint:
      type: object
      required: [_links]
      properties:
        _links:
          type: object
          additionalProperties:
            $ref: '#/components/schemas/HalLink'
    Order:
      type: object
      required: [id, status, _links]
      properties:
        id: {type: string}
        status: {type: string}
        currency: {type: string}
        _links:
          type: object
          additionalProperties:
            $ref: '#/components/schemas/HalLink'
~~~

**Điểm phân biệt cần nhớ:** `links` trong một **OpenAPI Response Object** (ví dụ `CreatedOrder`) mô tả quan hệ giữa các operation trong **tài liệu OpenAPI**, không tự động thêm `_links` vào JSON runtime. `_links` thực tế do server trả theo media type HAL; client runtime phải đọc nó. Hãy kiểm thử hai lớp hợp đồng thay vì nghĩ khai báo OpenAPI links tự biến API thành HATEOAS.

Mẫu OpenAPI này được rút gọn, chưa mô tả tất cả relation, trạng thái, schema lỗi, idempotency và collection paging. Trong hệ thống thật, thêm tài liệu cho rel URI, profile, ngữ nghĩa condition action, version và quy tắc authorize. Schema `additionalProperties` ở đây minh họa sự linh hoạt của rel: những rel chưa biết có thể được bỏ qua an toàn, nhưng **không** vì thế mà client được phép thực thi action chưa hiểu.

### 13.2. Profile của relation phải ổn định

Một hồ sơ quan hệ `https://rels.example.test/request-cancellation` nên trả lời:

- Khi nào hành động được đề nghị và ai có quyền?
- HTTP method, media type, request schema và validation là gì?
- Khi thành công: `201 Created` đối với cancellation resource hay `202 Accepted` đối với operation nền?
- Những lỗi chính: `400`, `401`, `403`, `404`, `409`, `412`, `429`?
- Có yêu cầu `Idempotency-Key`, `If-Match`, retry và cơ chế kiểm tra kết quả không?
- Mã trạng thái nghiệp vụ nào dùng được, và việc hủy có thể bất đồng bộ hoặc bị từ chối không?

Client có thể được build theo profile này, không phải đi đọc từng tài liệu mới ở mỗi request. Hypermedia sẽ **cung cấp URI và tính khả dụng hiện tại**; profile cung cấp ngữ nghĩa ổn định để client sử dụng đúng hành động.

## 14. Bảo mật khi client và server theo link

Hypermedia làm giảm phụ thuộc đường dẫn, nhưng nếu triển khai thiếu kiểm soát có thể mở ra lỗi mới. Một link là **dữ liệu đến từ nguồn khác**, không phải giấy phép tuyệt đối để request tới mọi nơi.

### 14.1. SSRF và link target không đáng tin

Đặc biệt nguy hiểm khi **server backend** đọc một JSON bên ngoài và tự động fetch tất cả `href` trong đó. Nếu bên ngoài cung cấp:

~~~json
{
  "_links": {
    "next": {
      "href": "http://127.0.0.1:8080/internal/admin"
    }
  }
}
~~~

Một crawler hoặc API aggregator server-side không được tự fetch URI này. Phải hạn chế scheme, host, cổng và dải địa chỉ đích, chống redirect vào mạng riêng/loopback/link-local, xử lý DNS rebinding và tuân thủ chính sách egress. **Không dùng URL công khai do người dùng nhập để trở thành nguồn tin cậy cho internal service**.

Với mobile/browser client theo link từ API của chính mình, các rủi ro khác có thể là mở trang giả mạo, gửi bearer token sai origin hoặc điều hướng tới một URI chứa dữ liệu nhạy cảm. Giải pháp cần phù hợp loại client, không áp dụng máy móc một allowlist host cho mọi hợp đồng liên miền.

### 14.2. Không gửi token sang origin ngoài ý muốn

Giả sử API cung cấp link tải báo cáo từ object storage hoặc trang thanh toán đối tác. Client **không được mặc định** gắn `Authorization: Bearer <token-api>` vào request tới host mới. Token thường có audience/scope dành cho API gốc; gửi sang bên ngoài gây lộ credential.

Quy tắc thiết kế:

1. Phân biệt link **nội bộ cùng origin** với link **ngoài origin**.
2. Kiểm tra scheme HTTPS, host và redirect theo chính sách tin cậy.
3. Chỉ gửi token khi đích phù hợp audience/scope; dùng luồng xác thực riêng cho đối tác hoặc URL tải hạn chế quyền/thời gian khi cần.
4. Không coi bất kỳ chuỗi `href` nào do client gửi trở lại server là URI hợp lệ; server phải validate quyền và resource.
5. Hạn chế URL nhạy cảm trong log, query string và referrer.

### 14.3. Ẩn affordance không phải authorization

Server có thể bỏ rel `request-cancellation` khi một đơn không cho hủy, nhưng client độc hại có thể gọi POST trực tiếp đến URI từng biết. Endpoint phải xác nhận:

- Token/identity hợp lệ và đúng owner hoặc role.
- Trạng thái đơn tại **thời điểm thay đổi**.
- Bất biến nghiệp vụ, điều kiện thanh toán và sự đồng thời.
- `Idempotency-Key` hoặc precondition nếu quy trình cần chống tác động lặp.
- Quyền truy cập resource kết quả và monitor cũng được kiểm tra lại.

Một luồng an toàn thường kết hợp **GET representation có link đề nghị** với **POST action được authorization trong transaction**. Đừng cố sử dụng việc không trả link như cơ chế duy nhất ngăn BOLA/IDOR.

## 15. Cache, ETag và sự thay đổi của liên kết

Link không phải cấu hình vĩnh viễn. Khi trạng thái đơn từ `PENDING_PAYMENT` sang `PAID`, representation có thể:

- Bỏ relation `payment-options` hoặc `request-cancellation`.
- Thêm relation `tracking`, `invoice` hoặc `refund-request`.
- Thay target URI dù relation giữ nguyên.

Client cache representation quá lâu có thể hiển thị một hành động đã hết hiệu lực. Giải pháp:

- Với dữ liệu nhạy cảm và affordance đổi nhanh, dùng `Cache-Control: no-store` hoặc TTL ngắn có chính sách xác thực phù hợp.
- Có thể dùng `ETag` cho representation và conditional GET `If-None-Match` để giảm payload khi không đổi.
- Khi trạng thái hoặc **tập link có ý nghĩa** thay đổi, validator của representation cần thay đổi phù hợp; đừng giữ ETag cũ chỉ vì vài cột DB không đổi.
- Khi user thay đổi quyền, phải kiểm tra cách phân vùng cache: cùng URI có thể trả representation khác nhau theo principal.
- Nếu dùng `Vary` cho content negotiation (ví dụ `Accept`, `Accept-Language`), cấu hình và kiểm thử đúng với cơ chế cache. `Vary` đơn lẻ không bảo đảm an toàn phân quyền.

### 15.1. Ví dụ conditional GET

~~~http
GET /v1/orders/ord_916 HTTP/1.1
Host: api.example.test
Accept: application/hal+json
If-None-Match: "ord_916-state-v3"
Authorization: Bearer <access-token>
~~~

Nếu representation phù hợp vẫn chưa đổi:

~~~http
HTTP/1.1 304 Not Modified
ETag: "ord_916-state-v3"
Cache-Control: private, max-age=5
Vary: Accept
~~~

Khi chuyển trạng thái và affordance đổi, response `200 OK` nên có ETag mới, body mới và tập rel mới. `304` chỉ hợp lệ khi validator khớp theo ngữ nghĩa HTTP và representation đã chọn chưa thay đổi; không dùng `304` để né kiểm tra quyền.

### 15.2. Có nên cache entry point?

Nếu entry point khác nhau theo quyền, một shared cache có thể làm lộ link riêng tư hoặc trả bản đồ quan hệ không đúng user. Lựa chọn bảo thủ là `Cache-Control: no-store`. Nếu entry point công khai giống nhau với mọi caller, có thể dùng cache hợp lý và version/ETag, nhưng khi chuyển route cần xác định thời gian client nhận thay đổi.

Đừng dựa vào việc client “luôn gọi lại entry point mỗi mili-giây”; có thể cache trong bộ nhớ trong một phiên theo TTL và refresh khi link không còn hợp lệ. Cần có chiến lược retry có giới hạn, không tạo vòng lặp khám phá không kết thúc.

## 16. HTTP semantics vẫn là nền tảng của hypermedia

HATEOAS không cho phép tùy tiện đổi nghĩa HTTP. Quan hệ và target phải đi cùng method, status, cache, validation, phân trang và quy tắc idempotency đúng.

| Hành vi | Method/status điển hình | Hypermedia hỗ trợ gì? |
|---|---|---|
| Đọc entry point | `GET 200` | Công bố relation cấp cao |
| Liệt kê đơn | `GET 200` | `self`, `next`, `prev`, item links |
| Tạo đơn | `POST 201` khi đã tạo | `Location` và `self` của đơn mới |
| Bắt đầu tác vụ nền | `POST 202` khi mới nhận việc | Link/Location tới operation monitor |
| Xem tác vụ đang chạy | `GET 200` + `RUNNING` | Link tới chính operation và action liên quan |
| Tác vụ hoàn thành | `GET 200` + result link, hoặc `303` | Tìm resource kết quả |
| Sửa có điều kiện | `PATCH`/`PUT` + `If-Match` | Action/profile mô tả precondition và payload |
| Đề nghị hủy | `POST` tới cancellation resource theo contract | Chỉ quảng bá khi hành động có ý nghĩa |
| Truy vấn quá thường xuyên | `429` có thể kèm `Retry-After` | Client giảm nhịp polling |

### 16.1. Link action và idempotency

Nếu client gọi một action POST rồi mất kết nối trước khi nhận kết quả, client không nên đoán rằng POST thất bại và thực hiện lại vô hạn. Với thao tác có tác động như tạo đơn, hủy hoặc gửi thanh toán, thiết kế `Idempotency-Key` trong profile/action contract, xác định phạm vi/retention và trả cùng operation/tài nguyên khi retry hợp lệ. Hypermedia **không tự làm POST trở thành idempotent**.

### 16.2. Trạng thái xử lý nền

Một action có thể dẫn đến operation resource và kết thúc bất đồng bộ. Khi đó client nên theo `Location` hoặc rel monitor được công bố, xem `QUEUED/RUNNING/SUCCEEDED/FAILED` và xử lý polling/backoff. Không giả định sự tồn tại của link action đồng nghĩa tác vụ đã hoàn tất hoặc sẽ thành công.

### 16.3. Lỗi cũng có thể cung cấp hướng xử lý

Một response `409 Conflict` khi đơn không thể hủy có thể dùng `application/problem+json` với `type`/`code` và, nếu hợp đồng cần, kèm link tới tài nguyên mới nhất để client refresh. Không biến mọi lỗi thành HTTP 200 chỉ để body luôn có `_links`. Link là **thông tin bổ sung**; HTTP status vẫn phải mô tả đúng kết quả request.

## 17. Tiến hóa API: đổi URI nhưng giữ relation

Đây là lợi ích cần kiểm chứng bằng thực nghiệm, không chỉ khẳng định:

**Phiên bản nội bộ A:**

~~~json
{
  "_links": {
    "https://rels.example.test/orders": {
      "href": "/v1/orders"
    }
  }
}
~~~

**Phiên bản nội bộ B:**

~~~json
{
  "_links": {
    "https://rels.example.test/orders": {
      "href": "/v2/customer-purchases"
    }
  }
}
~~~

Nếu semantics của resource và response media type vẫn tương thích, client đi theo rel `orders` có thể sử dụng target mới mà không đổi code ghép URI. Nhưng nếu JSON, trạng thái, auth, method hoặc nghĩa `orders` thay đổi phá vỡ contract, việc chỉ giữ rel không giải quyết được. **Ổn định quan hệ là điều kiện cần trong chiến lược hypermedia, không phải tấm vé bỏ qua quản lý version.**

### 17.1. Các bước chuyển đổi hệ thống đang dùng path tĩnh

1. **Thống kê client và route hiện có:** bên nào đang hardcode `/v1/orders/{id}`, `/cancel`, page number hoặc payment path?
2. **Định nghĩa tập relation nhỏ:** entry point, orders, create-order, self, next, request-cancellation, result và profile.
3. **Thêm link vào representation hiện tại:** không cần đổi mọi endpoint trong một lần; có thể bổ sung `_links` và content negotiation.
4. **Cập nhật client dần:** ban đầu client vẫn biết entry point và rel, thay mỗi chỗ tự ghép URL bằng follow link.
5. **Chạy thử thay route trên môi trường kiểm thử:** ví dụ đổi `/orders/{id}/cancel` thành `/orders/{id}/cancellations`, không sửa client discovery.
6. **Giữ tương thích client cũ trong thời gian đã định:** redirect hoặc adapter ở gateway khi phù hợp, truyền thông rõ mốc ngừng hỗ trợ.
7. **Theo dõi telemetry và loại route cũ:** chỉ sau khi kiểm tra usage, tỷ lệ lỗi, client version và kế hoạch rollback.

Việc thêm hypermedia không nhất thiết đòi chuyển toàn bộ API thành một framework mới. Có thể bắt đầu với **entry point + self + next + relation cho hành động quan trọng**, rồi mở rộng khi có lợi ích rõ.

### 17.2. Cần version cái gì?

- **Contract relation:** thay đổi ngữ nghĩa relation là breaking change đối với client phụ thuộc nó. Có thể giới thiệu relation mới thay vì sửa nghĩa cũ.
- **Media type/schema:** đổi trường bắt buộc, cách biểu diễn, action shape hoặc profile có thể đòi cơ chế tương thích/version.
- **Entry point:** nên cực kỳ ổn định, có thể cung cấp link tới các nhóm API khác phiên bản.
- **Target URI:** có thể thay đổi thường xuyên hơn nếu client dựa trên link, nhưng cần xét cache, bookmark và link đã lưu.
- **Business workflow:** nếu thao tác cũ không còn được phép, client cần xử lý thiếu affordance hoặc lỗi rõ ràng, không chỉ dựa vào đổi path.

## 18. Quan sát hệ thống: đo được việc client có thực sự khám phá?

Nếu client vẫn hardcode URL dù server đã trả HAL, hypermedia chỉ là trang trí. Cần quan sát:

| Chỉ số/kết quả | Ý nghĩa |
|---|---|
| Tỷ lệ request đến `/entry` theo loại client/version | Client có dùng bootstrap không, hay chỉ gọi route ghi cứng? |
| Tỷ lệ lỗi `404` trên route cũ sau khi đổi target | Khả năng client vẫn ghép URI |
| Tỷ lệ `4xx` trên action theo trạng thái | Client có gọi action không được đề nghị hoặc dùng link cũ không? |
| Lỗi parse media type/relation không biết | Client có tương thích với representation đang phục vụ không? |
| Hit/miss cache, `304`, stale representation | Tập link có được refresh khi trạng thái đổi không? |
| Số request GET tiếp theo từ link `next` | Client có dùng pagination được công bố không? |
| Tỷ lệ retry/duplicate POST có Idempotency-Key | Client đang xử lý lỗi mạng đúng chưa? |
| Latency từ discovery đến hoàn thành hành trình | Hypermedia có bổ sung round trip đáng kể không? |

Không ghi raw bearer token, toàn bộ URL chứa thông tin nhạy cảm hoặc dữ liệu cá nhân vào log chỉ để phân tích discovery. Gắn correlation ID, resource type, rel và client version ở mức an toàn, cân đối với yêu cầu riêng tư.

### 18.1. Đánh đổi hiệu năng

Hypermedia có thể tạo thêm lượt GET nếu client phải tải entry point và từng representation mới biết hành động. Có thể giảm chi phí bằng:

- `_embedded` có chọn lọc để giảm yêu cầu GET chi tiết cho từng item.
- Cache hợp lý cho tài nguyên công khai và link ổn định.
- Cho phép client tiếp tục từ URI đã được cấp trước đó khi còn hiệu lực, thay vì bắt đầu lại entry point cho mọi thao tác.
- Trả representation mới và link ngay trong phản hồi POST thành công.
- Giới hạn depth/size của đồ thị để tránh N+1 network round trips.

Không nên nhúng toàn bộ collection hoặc mọi quan hệ vào một response khổng lồ. Lựa chọn embedding dựa vào use case, số lượng item, quyền và ngân sách tải. Đo p95 end-to-end thay vì chỉ đo một endpoint riêng lẻ.

## 19. Kiểm thử hợp đồng hypermedia

Các bài kiểm thử phải chứng minh hai thứ: **server phát link đúng với trạng thái/quyền** và **client sử dụng link thay vì dự đoán route**.

### 19.1. Ma trận kiểm thử server

| Tình huống | Kỳ vọng |
|---|---|
| GET entry point có quyền đọc đơn | `200`, HAL hợp lệ, có rel `orders` và `profile` |
| GET entry point có quyền tạo đơn | Có rel `create-order` |
| GET entry point không có quyền tạo | Không quảng bá `create-order`; POST vẫn phải tự từ chối |
| GET collection có thêm trang | Có rel `next` với URI cursor hợp lệ |
| GET collection trang cuối | Không có `next` sai hoặc link dẫn tới vòng lặp |
| GET item ở `PENDING_PAYMENT` | Có link/affordance được phép theo policy |
| GET item ở `SHIPPED` | Không quảng bá hành động hủy trực tiếp nếu nghiệp vụ cấm; có tracking khi được phép |
| Token quyền đọc bị thu hồi | GET item hoặc action bị từ chối, dù client có link cũ |
| POST tạo đơn thành công | `201` + Location + `self` khớp resource mới |
| POST tạo report nền | `202` + URI operation theo hợp đồng |
| GET operation thành công | Có link result hoặc `303 Location` đúng |
| Resource/target chuyển sang route mới | Rel và semantics giữ nguyên; client follow link mới được |
| Link URI tương đối | Client resolve đúng theo URI nguồn |
| Content negotiation khác media type | `Content-Type` và body khớp định dạng được chọn hoặc báo lỗi phù hợp |
| ETag cũ sau khi trạng thái đổi | Không trả nhầm `304` khiến client giữ action lỗi thời |
| `Link` header đồng thời với `_links` body | Cùng rel/target theo chính sách nhất quán |

### 19.2. Kiểm thử client, bao gồm trường hợp liên kết độc hại

| Tình huống | Kỳ vọng client |
|---|---|
| Không có rel tùy chọn | Ẩn/tắt tính năng, không đoán URL |
| Có rel mới chưa biết | Bỏ qua an toàn, không tự thực thi action |
| Có nhiều link cùng rel | Chọn theo media type/profile đã hỗ trợ |
| Link `templated` không hỗ trợ | Báo tính năng không hỗ trợ hoặc dùng thư viện expansion đúng |
| Target là `https://api.example.test/v2/orders` | Theo link, không nối `/v1` cũ |
| Target là `http://127.0.0.1/...` | Không tự gọi theo chính sách tin cậy |
| Target là host ngoài với bearer token API | Không tự chuyển token sang host lạ |
| Redirect nhiều bước/vòng lặp | Có giới hạn và kiểm tra đích ở từng bước |
| Response `401/403` | Xử lý xác thực/quyền, không gọi lặp vô hạn |
| Action POST trả `409` vì trạng thái đổi | Tải lại representation và hiển thị lỗi |
| POST mất phản hồi | Retry theo idempotency contract, không tạo tác động trùng |
| Link `next` có cursor hết hạn | Xử lý lỗi và bắt đầu lại truy vấn khi phù hợp |

### 19.3. MockMvc minh họa affordance có điều kiện

~~~java
// Các assertion minh họa: cần cấu hình @WebMvcTest, Spring
// Security, mock use case/authorization và dữ liệu trả về.

mockMvc.perform(get("/entry")
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andExpect(content().contentTypeCompatibleWith(
        "application/hal+json"))
    .andExpect(jsonPath(
        "$._links['https://rels.example.test/orders'].href"
    ).exists());

mockMvc.perform(get("/v1/orders/ord_916")
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$._links['https://rels.example.test/request-cancellation'].href"
    ).exists());

mockMvc.perform(get("/v1/orders/ord_917")
        .accept("application/hal+json"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$._links['https://rels.example.test/request-cancellation']"
    ).doesNotExist());
~~~

Các đoạn trên là **assertion**, chưa phải test class tự chạy. Cần mock `OrderReadUseCase`, `OrderAuthorization`, danh tính và chính sách trạng thái phù hợp. Ngoài kiểm tra link có/không, test POST action thật với trạng thái đã đổi và truy cập sai tenant để xác nhận backend không dựa vào việc ẩn link.

### 19.4. Phép thử quan trọng nhất: đổi đường dẫn mà không sửa client

Một integration/consumer test nên:

1. Cho client chỉ cấu hình `https://api.example.test/entry` và các rel đã tài liệu hóa.
2. Server A trả relation `orders` với target `/v1/orders`.
3. Server B giữ semantics và media type, nhưng trả target `/v2/customer-purchases`; item `self` cũng đổi.
4. Chạy cùng binary client, xác minh nó vẫn đọc danh sách và chi tiết thành công.
5. Đổi target của action request-cancellation theo cùng relation; client vẫn gọi đúng action theo method/schema đã biết.
6. Đo phản hồi khi liên kết cũ hết hạn, link không còn xuất hiện hoặc target bị chặn bởi origin policy.

Nếu test thất bại vì client đang ghép `"/orders/" + id` ở đâu đó, đó là dấu hiệu coupling cụ thể cần sửa. Đây là bằng chứng thực tế về lợi ích hypermedia hơn là chỉ kiểm tra JSON có `_links`.

## 20. Bài thực hành: tái cấu trúc client quản lý đơn hàng

**Bối cảnh:** Nhóm mobile đang sử dụng ba route ghi cứng:

~~~text
GET  /v1/orders
GET  /v1/orders/{id}
POST /v1/orders/{id}/cancel
~~~

Đội backend chuẩn bị đổi cấu trúc:

~~~text
GET  /v2/customer-purchases
GET  /v2/customer-purchases/{publicId}
POST /v2/cancellation-requests
~~~

Đường dẫn mới chỉ là ví dụ; chưa khẳng định việc đổi route là cần thiết. API còn bổ sung workflow hủy bất đồng bộ và có thể trả `202` cùng URI monitor. Những đơn đã giao không được phép hủy trực tiếp; tenant khác không được phép xem hoặc hủy.

### 20.1. Nhiệm vụ

1. **Thiết kế entry point** HAL có ít nhất `self`, rel `orders`, `create-order` và `profile`.
2. **Thiết kế collection** với hai item, `_embedded`, `self` của item và `next` cho phân trang cursor.
3. **Thiết kế hai representation**: đơn `PENDING_PAYMENT` được phép yêu cầu hủy; đơn `SHIPPED` không có affordance hủy trực tiếp.
4. **Chọn một cách mô tả action**: HAL + profile relation hoặc Siren action có method/fields; giải thích ưu/nhược điểm.
5. **Viết mã giả client** chỉ biết entry point và các rel, không ghép URL từ `id` hoặc `version`.
6. **Viết flow HTTP cho hủy bất đồng bộ**: response `202 Accepted`, `Location` trỏ operation, client theo dõi, kết quả `SUCCEEDED/FAILED`.
7. **Thiết kế quyền**: role, owner, token audience, chống gọi URI hủy cũ khi trạng thái đã thay đổi và chống giả mạo link tới host ngoài.
8. **Thêm OpenAPI rút gọn** cho entry point, resource đơn và endpoint hủy; thể hiện `201/202/409` khi phù hợp, media type và response errors.
9. **Lập ít nhất 10 phép thử**: rel đúng/thiếu, đổi route, trạng thái khác nhau, cross-tenant, URI tương đối, link độc hại, redirect, cache stale, retry/idempotency, pagination.
10. **Viết ADR ngắn** nêu quyết định hypermedia, độ phức tạp client, lợi ích thay đổi URI và cách đo thành công sau rollout.

### 20.2. Gợi ý đáp án

Entry point mẫu:

~~~json
{
  "_links": {
    "self": {"href": "/entry"},
    "https://rels.example.test/orders": {
      "href": "/v2/customer-purchases"
    },
    "https://rels.example.test/create-order": {
      "href": "/v2/customer-purchases",
      "type": "application/json"
    },
    "profile": {"href": "/profiles/mayshop-order"}
  }
}
~~~

Đơn được phép hủy có relation:

~~~json
{
  "id": "ord_916",
  "status": "PENDING_PAYMENT",
  "_links": {
    "self": {
      "href": "/v2/customer-purchases/ord_916"
    },
    "https://rels.example.test/request-cancellation": {
      "href": "/v2/cancellation-requests",
      "type": "application/json"
    }
  }
}
~~~

Vì target `/v2/cancellation-requests` không chứa order ID, **hợp đồng action** phải quy định request body có `orderId` hoặc một link/token ngữ cảnh được bảo vệ theo thiết kế. Ví dụ:

~~~http
POST /v2/cancellation-requests HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Idempotency-Key: 8e183a38-d775-4571-b961-55a0b4efcfb7
Content-Type: application/json

{
  "orderId": "ord_916",
  "reason": "CUSTOMER_REQUEST"
}
~~~

Và khi tiếp nhận nền:

~~~http
HTTP/1.1 202 Accepted
Location: https://api.example.test/v2/operations/op_cancel_61
Content-Type: application/hal+json

{
  "id": "op_cancel_61",
  "status": "QUEUED",
  "_links": {
    "self": {"href": "/v2/operations/op_cancel_61"}
  }
}
~~~

Client có thể theo `Location` hoặc rel monitor để đọc kết quả. **Đừng tin `orderId` trong body là bằng chứng có quyền hủy**: backend phải kiểm tra user, tenant, trạng thái và idempotency. Trong trường hợp hành động trả resource yêu cầu hủy đồng bộ, `201` với Location của cancellation resource cũng có thể phù hợp; phải chọn theo những gì đã hoàn tất.

### 20.3. Thang đánh giá gợi ý

| Tiêu chí | Điểm |
|---|---:|
| Entry point và relation có ngữ nghĩa ổn định | 20 |
| Representation collection/item và navigation | 15 |
| Action theo trạng thái và phân quyền | 20 |
| Client không ghép URI, xử lý link/redirect an toàn | 20 |
| HTTP/OpenAPI và idempotency/async đúng | 15 |
| Kiểm thử đổi route, bảo mật và cache | 10 |
| **Tổng** | **100** |

Một bài có nhiều `_links` nhưng client vẫn gọi `/v1/orders/{id}/cancel` từ chuỗi tự nối chưa đạt mục tiêu. Ngược lại, một hệ thống nhỏ chỉ dùng entry point, `self`, `next` và một vài relation trọng yếu vẫn có giá trị nếu chứng minh được client tách khỏi path nội bộ.

## 21. Phản mẫu và cách sửa

| Phản mẫu | Hệ quả | Cách sửa |
|---|---|---|
| Client chỉ đọc `id` rồi tự nối URL | Phụ thuộc cấu trúc route, khó đổi version/path | Theo `self` và relation được công bố |
| Dùng rel như chính tên endpoint `/v1/cancelOrder` | Relation thay đổi khi đổi route, mất tính ổn định | Định nghĩa rel theo **nghĩa nghiệp vụ**, target do server quyết |
| Có `_links` nhưng không tài liệu hóa relation | Client không biết method/schema hoặc tác động | Profile/rel documentation, OpenAPI và ví dụ |
| Cho mọi action link nhưng không xét trạng thái | UI đề nghị thao tác vô nghĩa | Chỉ quảng bá affordance phù hợp theo domain/policy |
| Chỉ ẩn link để bảo vệ endpoint | Client vẫn có thể gọi URI cũ | Authn/authz và state validation ở endpoint |
| Coi HAL link là lệnh POST đầy đủ | Thiếu method, payload và giới hạn | Dùng tài liệu rel hoặc action-capable media type |
| Coi `Location` và `Link` là một | Client nhầm resource mới với quan hệ điều hướng | Dùng mỗi header theo semantics HTTP |
| Dùng raw string replace cho URI Template | Sai encoding, lỗi query và injection | Dùng thư viện RFC 6570, validate biến |
| Theo link tới mọi host, luôn gửi Authorization | Lộ token, nguy cơ SSRF/open redirect | Origin policy, audience/token scope, redirect checks |
| Cache link lâu hơn trạng thái domain | Client thấy action cũ, request thất bại | TTL/ETag phù hợp, refresh và xử lý `409` |
| Cứ GET entry point lại trước mọi request | Tăng độ trễ và tải không cần thiết | Cache hợp lý theo quyền, theo link còn hiệu lực |
| Đổi nghĩa relation cũ mà không version | Client làm sai hành trình dù URI khám phá được | Giữ semantics, thêm rel mới hoặc migration contract |
| Thêm OpenAPI `links` rồi tưởng runtime có HAL | Runtime JSON vẫn thiếu `_links` | Render link trong response và test |
| Dùng `GET` để thực hiện hủy/thanh toán | Vi phạm tính safe của GET, rủi ro prefetch/cache | Dùng method/hành động đúng semantics |

## 22. Checklist trước khi đưa hypermedia API vào production

### Điểm vào và relation

- [ ] Có URI bootstrap ổn định, được cấu hình rõ theo môi trường.
- [ ] Representation entry point có media type đúng và các relation cấp cao.
- [ ] Quan hệ chuẩn và quan hệ nghiệp vụ custom được phân biệt, tài liệu hóa.
- [ ] Rel nghiệp vụ có semantics, method, payload, status và xử lý lỗi rõ ràng.
- [ ] Client không dựa trên phép nối route từ ID hoặc version nội bộ.

### Navigation và action

- [ ] Collection có `self`, `next`/`prev` khi phù hợp, item có link riêng.
- [ ] URI Template được expand/encode đúng và kiểm tra biến, filter, limit.
- [ ] Action chỉ được quảng bá theo trạng thái và quyền tại thời điểm tạo representation.
- [ ] Backend vẫn xác thực, phân quyền và kiểm tra trạng thái khi action được gọi.
- [ ] `201 Location`, `202 monitor`, `303 Location` và `Link` được dùng theo ngữ nghĩa.
- [ ] Client xử lý thiếu rel, rel chưa biết, nhiều target và link hết hạn.

### Bảo mật và hiệu năng

- [ ] Có chính sách scheme/origin/host, kiểm tra redirect và chống SSRF nếu server fetch URL.
- [ ] Không tự gửi bearer token sang origin ngoài hoặc target không phù hợp audience.
- [ ] URI/cursor không chứa secret, dữ liệu nhạy cảm hoặc ID thiếu bảo vệ phân quyền.
- [ ] Cache, ETag và TTL được thiết kế theo quyền và thay đổi của affordance.
- [ ] Có giới hạn link count, depth, payload, request rate và timeout.
- [ ] Không dùng hypermedia để mở rộng tùy ý quyền query hoặc thực hiện side effect bằng GET.

### Hợp đồng và vận hành

- [ ] OpenAPI, profile/relation docs và representation runtime không mâu thuẫn.
- [ ] Có test trạng thái, quyền, pagination, response code và redirect.
- [ ] Có test đổi URI mà không sửa code client.
- [ ] Có telemetry về lỗi route cũ, client version, action conflict và chi phí discovery.
- [ ] Có chính sách versioning cho media type/rel semantics và migration cho client cũ.

## 23. Ghi nhớ

**Khám phá API từ điểm vào** giúp client tìm những tài nguyên và hành động kế tiếp qua **link relation**, thay vì đoán đường dẫn rồi tự nối chuỗi từ ID. Entry point là điểm bootstrap, `self` và `next` giúp điều hướng, relation nghiệp vụ truyền tải mục đích, còn action affordance và profile cho biết phương thức, payload và điều kiện cần thực hiện.

Hypermedia đem lại **tính linh hoạt của cấu trúc URI**, nhưng không tự thay thế HTTP semantics, tài liệu hợp đồng, idempotency hay phân quyền. Một API tốt cần vừa phát liên kết có ý nghĩa ở runtime, vừa kiểm tra quyền/trạng thái khi thực thi, giới hạn việc theo link và xử lý đúng cache/redirect. Cách xác nhận giá trị thực tế nhất là **thay đổi route ở server mà giữ nguyên client dùng relation**, sau đó kiểm thử toàn bộ hành trình nghiệp vụ vẫn hoạt động đúng.
