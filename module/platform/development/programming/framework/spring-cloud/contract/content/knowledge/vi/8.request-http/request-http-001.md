# HTTP method và đường dẫn yêu cầu

## 1. Method và đường dẫn là điểm bắt đầu của hợp đồng HTTP

Trong Spring Cloud Contract, một hợp đồng (contract) mô tả hành vi giao tiếp mà **consumer** được phép kỳ vọng từ **producer**. Với HTTP, consumer gửi một request; producer xử lý request và trả lại response. Nếu producer đổi cách nhận request, consumer có thể bị lỗi ngay cả khi JSON response vẫn giữ nguyên.

Hai yếu tố đầu tiên cần xác định trong phần `request` là:

- **HTTP method:** Consumer gọi `GET`, `POST`, `PUT`, `PATCH`, `DELETE` hay phương thức nào khác?
- **Đường dẫn yêu cầu:** Consumer gọi endpoint nào, ví dụ `/api/orders` hay `/api/orders/ORD-123`?

Theo DSL của Spring Cloud Contract, **method và URL là hai thông tin bắt buộc để định nghĩa một HTTP request**. Phần body, headers và query parameters có thể được bổ sung khi chúng là một phần thỏa thuận giữa các hệ thống.

Bài này thuộc chương **Request HTTP** trong module `SPRING_CLOUD_CONTRACT`. Nó tập trung vào cách khai báo method và đường dẫn bằng **Groovy/YAML DSL**, cách phân biệt path với query, cách biểu diễn tham số động và cách xác minh producer qua generated tests. Các kiến thức này làm nền cho bước phát hành stub, chạy Stub Runner và CI để phát hiện API không tương thích.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Chọn HTTP method phù hợp với mục đích giao tiếp và diễn giải hậu quả khi thay đổi method.
2. Phân biệt **scheme/host**, **path**, **path segment**, **path variable** và **query parameter**.
3. Viết phần `request` với `method` và `urlPath` hoặc `url` trong Groovy DSL.
4. Biểu diễn hợp đồng tương ứng bằng YAML DSL.
5. Thiết kế đường dẫn cố định và đường dẫn có giá trị biến đổi mà không làm matcher quá rộng.
6. Nhận diện thay đổi có thể phá vỡ consumer, và đưa contract test vào producer CI.

## 2. Phân tích một HTTP request từ góc nhìn hợp đồng

Xét request:

~~~http
GET /api/orders/ORD-123?includeItems=true HTTP/1.1
Host: order-service.internal
Accept: application/json
~~~

Các thành phần có vai trò khác nhau:

| Thành phần | Giá trị ví dụ | Vai trò trong hợp đồng |
| --- | --- | --- |
| Method | `GET` | Hành động HTTP mà consumer thực hiện |
| Path | `/api/orders/ORD-123` | Định tuyến tới tài nguyên hoặc hành vi |
| Path variable | `ORD-123` | Giá trị biến đổi nằm trong một đoạn path |
| Query parameter | `includeItems=true` | Tùy chọn hoặc tiêu chí bổ sung cho request |
| Host | `order-service.internal` | Địa chỉ chạy producer, thường thay đổi theo môi trường |
| Request header | `Accept: application/json` | Khai báo định dạng phản hồi mà consumer chấp nhận |

Với URL đầy đủ `https://order-service.internal/api/orders/ORD-123?includeItems=true`, phần `https://order-service.internal` xác định scheme và host, `/api/orders/ORD-123` là **path**, còn `includeItems=true` là **query string**. Dấu `?` phân tách path và query.

Trong phần lớn consumer-driven contract tests, điều quan trọng là **method, path và dữ liệu request mà consumer thực sự gửi**. Host nội bộ thường không cần cố định vào hợp đồng vì có thể khác giữa máy phát triển, CI và môi trường triển khai.

> Contract test quan tâm đến **giao tiếp quan sát được**. Nó không cần biết bên trong producer dùng tên method Java nào, gọi repository nào hoặc bảng cơ sở dữ liệu mang tên gì.

## 3. Chọn HTTP method: chỉ cùng đường dẫn chưa đủ

HTTP method là một phần của giao diện công khai. Hai request có **cùng path nhưng khác method** thường đại diện cho hai hành vi khác nhau.

| Method | Ý nghĩa thông dụng | Ví dụ trong dịch vụ đơn hàng | Điểm cần chú ý |
| --- | --- | --- | --- |
| `GET` | Đọc biểu diễn tài nguyên, không chủ đích thay đổi trạng thái | `GET /api/orders/ORD-123` | Consumer có thể phụ thuộc cấu trúc phản hồi hoặc mã `404` |
| `POST` | Gửi dữ liệu để xử lý hoặc tạo tài nguyên theo API | `POST /api/orders` | Có thể cần request body, `201` hoặc status khác theo thỏa thuận |
| `PUT` | Tạo/thay thế trạng thái tài nguyên theo ngữ nghĩa API | `PUT /api/orders/ORD-123` | Thông thường hướng tới tính idempotent |
| `PATCH` | Thay đổi một phần tài nguyên | `PATCH /api/orders/ORD-123` | Phải thống nhất media type và cấu trúc bản vá |
| `DELETE` | Yêu cầu xóa tài nguyên | `DELETE /api/orders/ORD-123` | Phản hồi có thể là `204`, `200` hoặc status đã công bố |
| `HEAD` | Nhận headers như `GET` nhưng không có response body | `HEAD /api/orders/ORD-123` | Có thể quan trọng với cache hoặc kiểm tra sự tồn tại |
| `OPTIONS` | Mô tả phương thức/tùy chọn giao tiếp | `OPTIONS /api/orders` | Có thể liên quan đến CORS/preflight |

Bảng trên nêu **ngữ nghĩa HTTP thông dụng**, không áp đặt status cố định cho mọi dịch vụ. Contract phải mô tả **hành vi API thực tế đã được producer và consumer thống nhất**.

Ví dụ, một consumer chỉ gọi:

~~~http
GET /api/orders/ORD-123 HTTP/1.1
~~~

sẽ không tự động tương thích nếu producer ngừng hỗ trợ `GET` và yêu cầu `POST /api/orders/lookup`. Ngay cả khi producer vẫn trả một body JSON giống hệt, request của consumer cũ sẽ không còn đi vào đúng endpoint.

### 3.1. Method nên được chọn theo hành vi, không theo tên hàm Java

Một method Java tên `getOrder()` có thể được ánh xạ thành `@PostMapping`; tên method Java không quyết định HTTP method. Ngược lại, việc đổi tên method Java từ `findById` sang `lookupOrder` không phải breaking change nếu endpoint HTTP quan sát được vẫn giữ nguyên.

Trong contract DSL, khai báo **method mà client thật gửi**. Chỉ thêm contract cho phương thức khác khi có consumer thực sự sử dụng.

### 3.2. Idempotency là vấn đề ngữ nghĩa cần kiểm thử đúng tầng

Theo ngữ nghĩa HTTP, `GET` là safe, còn `PUT` và `DELETE` được thiết kế với tính idempotent. Tuy nhiên, **một contract chỉ kiểm chứng request/response tiêu biểu không chứng minh hành vi idempotent khi gọi lặp lại**. Nếu tính lặp lại không tạo tác dụng phụ là yêu cầu quan trọng, cần bổ sung integration/domain tests tương ứng.

## 4. Định nghĩa method và path trong Groovy DSL

Cấu trúc hợp đồng tối thiểu:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description('Lấy đơn hàng theo mã')

    request {
        method 'GET'
        urlPath('/api/orders/ORD-123')
    }

    response {
        status OK()
    }
}
~~~

Giải thích:

- `Contract.make { ... }` tạo một định nghĩa hợp đồng.
- `request { ... }` khai báo điều kiện request mà consumer gửi.
- `method 'GET'` yêu cầu HTTP method là `GET`.
- `urlPath('/api/orders/ORD-123')` khai báo phần **path** của URL.
- `response { status OK() }` cam kết producer trả HTTP `200` cho tình huống trên.

Hợp đồng vừa nêu hợp lệ ở mức ý tưởng nhưng **chưa kiểm tra JSON body hoặc media type**, vì hai phần đó chưa được khai báo. Trong bài toán thực tế, nên bổ sung những trường mà consumer sử dụng.

### 4.1. Dùng cú pháp chuỗi hoặc helper method

Groovy DSL hỗ trợ cách khai báo tương đương cho method và status:

~~~groovy
request {
    method 'GET'
    urlPath '/api/orders/ORD-123'
}

response {
    status 200
}
~~~

Có thể dùng helper:

~~~groovy
request {
    method GET()
    urlPath('/api/orders/ORD-123')
}

response {
    status OK()
}
~~~

**Chọn một phong cách trong dự án** để thống nhất cách đọc, nhưng điều cần giữ ổn định là method và path của giao diện HTTP. Không đổi `GET` thành `POST` chỉ vì khác phong cách DSL.

### 4.2. Một hợp đồng đầy đủ hơn

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_confirmed_order')
    description('Consumer truy vấn một đơn hàng đã xác nhận')

    request {
        method 'GET'
        urlPath('/api/orders/ORD-123')
        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            orderId: 'ORD-123',
            status: 'CONFIRMED',
            totalAmount: 199000
        )
    }
}
~~~

Contract xác định **đúng method và path** mà consumer dùng, đồng thời ghi nhận headers và response body quan trọng. Generated test phía producer phải xác minh hành vi này với fixture phù hợp; stub sinh từ contract cung cấp response mẫu để consumer kiểm tra.

Một tệp contract riêng thường nằm trong thư mục như:

~~~text
src/test/resources/contracts/orders/get_confirmed_order.groovy
~~~

Vị trí thực tế có thể cấu hình lại bằng Maven hoặc Gradle plugin; không nên suy ra vị trí từ tên package của controller.

## 5. `url` và `urlPath` khác nhau ở đâu?

Spring Cloud Contract Groovy DSL cho phép khai báo URL của request bằng **`url` hoặc `urlPath`**. Hai lựa chọn **không được khai báo đồng thời trong cùng một contract**.

~~~groovy
request {
    method 'GET'
    url('/api/orders/ORD-123')
}
~~~

và:

~~~groovy
request {
    method 'GET'
    urlPath('/api/orders/ORD-123')
}
~~~

Trong các trường hợp đơn giản, cả hai có thể biểu diễn cùng path. Tuy nhiên, tài liệu Spring Cloud Contract **khuyến nghị `urlPath` cho đường dẫn tương đối, độc lập với host**. Cách này phù hợp khi producer chạy ở nhiều địa chỉ hoặc cổng khác nhau trong local test và CI.

`url` cũng hỗ trợ URL tuyệt đối:

~~~groovy
request {
    method 'GET'
    url('http://localhost:8888/api/orders/ORD-123')
}
~~~

Đây là cú pháp được hỗ trợ nhưng có thể trói cấu hình vào môi trường cụ thể. Nếu consumer không cam kết một host cố định, đừng đưa hostname/cổng tạm thời vào contract chỉ vì nó đang hoạt động trên máy phát triển.

**Không làm điều này:**

~~~groovy
request {
    method 'GET'
    url('/api/orders/ORD-123')
    urlPath('/api/orders/ORD-123') // Sai: dùng đồng thời url và urlPath
}
~~~

Hãy chọn đúng một trong hai. Với nội dung của bài này, các ví dụ ưu tiên `urlPath` khi chỉ cần định danh đường dẫn.

## 6. Định nghĩa method và path bằng YAML DSL

Cùng hợp đồng tra cứu đơn hàng có thể viết dưới dạng YAML:

~~~yaml
name: get_confirmed_order
description: Consumer truy vấn một đơn hàng đã xác nhận
request:
  method: GET
  urlPath: /api/orders/ORD-123
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    orderId: ORD-123
    status: CONFIRMED
    totalAmount: 199000
~~~

Các trường chính:

| Groovy | YAML | Ý nghĩa |
| --- | --- | --- |
| `method 'GET'` | `method: GET` | HTTP method mà consumer gửi |
| `urlPath('/api/orders/ORD-123')` | `urlPath: /api/orders/ORD-123` | Path của request |
| `url('/api/orders/ORD-123')` | `url: /api/orders/ORD-123` | Một cách khai báo URL khác |
| `response { status OK() }` | `response: status: 200` | Status producer cam kết |

Trong YAML, `request.method` và `request.urlPath` nằm trong mapping `request`. Không đặt `urlPath` ở cấp ngoài ngang hàng với `response`, vì khi đó định nghĩa không còn đúng cấu trúc request của Spring Cloud Contract.

Cũng **không thêm đồng thời `request.url` và `request.urlPath`** trong cùng một contract YAML. Chọn một thuộc tính.

### 6.1. Chọn định dạng DSL theo dự án

Groovy phù hợp khi nhóm cần DSL linh hoạt, matcher, list/map lồng nhau và logic biểu diễn có kiểm soát. YAML dễ tiếp cận với người quen đọc dữ liệu khai báo. Cả hai đều tạo ra những cam kết về method/path tương tự, nên **tránh duy trì hai bản trùng nhau của cùng một tương tác** trong thư mục nguồn contract đang được build đọc.

## 7. Path, path variable và route template

Xét hai request:

~~~http
GET /api/orders/ORD-123 HTTP/1.1
GET /api/orders/ORD-456 HTTP/1.1
~~~

Cả hai có thể được Spring MVC route tới:

~~~java
@GetMapping("/api/orders/{orderId}")
public OrderView findById(@PathVariable String orderId) {
    return orderService.findById(orderId);
}
~~~

`{orderId}` trong `@GetMapping` là **placeholder của framework định tuyến server**. Nó không phải là chuỗi path mà consumer sẽ gửi qua HTTP. Consumer gửi một giá trị cụ thể, chẳng hạn `ORD-123`.

Vì thế, hợp đồng cho một request cụ thể nên dùng:

~~~groovy
request {
    method 'GET'
    urlPath('/api/orders/ORD-123')
}
~~~

Thay vì giả định rằng:

~~~groovy
request {
    method 'GET'
    urlPath('/api/orders/{orderId}')
}
~~~

sẽ tự biến thành matcher cho mọi ID. Nếu không cấu hình matcher, dấu ngoặc nhọn có thể bị hiểu như phần ký tự của đường dẫn, không giống cơ chế xử lý `@PathVariable` của Spring MVC. **Route template ở server và request matcher trong contract là hai khái niệm khác nhau.**

### 7.1. Một path segment có thể là ID, slug hoặc phiên bản

| Path | Segment biến đổi | Cần thống nhất gì? |
| --- | --- | --- |
| `/api/orders/ORD-123` | `ORD-123` | Định dạng mã và quy tắc lookup |
| `/api/products/keyboard-01` | `keyboard-01` | Slug có phân biệt chữ hoa/thường không? |
| `/api/users/42/addresses/7` | `42` và `7` | Định danh từng tài nguyên và thứ bậc |
| `/api/v1/orders/ORD-123` | `v1` và `ORD-123` | Version của API là một phần path |
| `/api/files/report%20november.pdf` | Segment đã mã hóa khoảng trắng | Quy tắc encode và decode path |

Không cần kiểm tra mọi ID có thể tồn tại; nên chọn **các đường đi tiêu biểu mà consumer sử dụng** và các matcher hợp lý để nhận diện định dạng hợp lệ.

### 7.2. Path có phân biệt dấu gạch chéo cuối không?

Hai path sau khác nhau ở mức chuỗi:

~~~text
/api/orders
/api/orders/
~~~

Một ứng dụng có thể tự chuyển hướng hoặc chấp nhận cả hai, nhưng hành vi đó phụ thuộc framework và cấu hình routing. Không mặc định hai path luôn tương đương. Nếu consumer phụ thuộc vào việc path có hoặc không có dấu `/` cuối, hãy quyết định rõ endpoint được cam kết và kiểm thử theo hành vi thật.

## 8. Request path động: sử dụng regex có chủ đích

Nếu producer cần phục vụ nhiều mã đơn hàng, contract có thể dùng **regex** để so khớp đường dẫn khi tạo stub, đồng thời cung cấp **giá trị cụ thể** để generated producer test có request ổn định.

Ví dụ Groovy:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description('Đường dẫn theo định dạng mã đơn hàng')

    request {
        method 'GET'
        url $(consumer(regex('/api/orders/ORD-[0-9]+')),
              producer('/api/orders/ORD-123'))
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(orderId: 'ORD-123')
    }
}
~~~

Diễn giải:

- `consumer(regex('/api/orders/ORD-[0-9]+'))`: matcher phía **stub/consumer** chấp nhận các đường dẫn khớp mẫu ID.
- `producer('/api/orders/ORD-123')`: giá trị path **cụ thể** dùng khi generated producer test gửi request.
- `method 'GET'` vẫn là một phần bắt buộc của điều kiện khớp; regex trên path không làm thay đổi method.

**Cẩn thận với response body của stub:** Hợp đồng minh họa vẫn trả `orderId: ORD-123` ngay cả khi consumer gọi `/api/orders/ORD-456` và path regex cho phép request đó. Nếu consumer yêu cầu ID trong response luôn bằng ID đã gửi, cần thiết kế thêm cơ chế tương ứng (ví dụ response templating phù hợp), giới hạn stub về path cố định hoặc tách tình huống. Matcher đường dẫn rộng **không tự làm dữ liệu response động theo biến path**.

### 8.1. Regex cần mô tả chính xác điều mà consumer được phép gửi

Ví dụ:

| Matcher | Ý nghĩa | Rủi ro |
| --- | --- | --- |
| `/api/orders/ORD-[0-9]+` | ID bắt đầu `ORD-` và theo sau là chữ số | Tốt khi đây là định dạng public |
| `/api/orders/.+` | Mọi path segment không rỗng | Có thể chấp nhận cả ID sai định dạng |
| `/api/.*` | Gần như toàn bộ API | Dễ khớp nhầm endpoint khác |
| Path literal `/api/orders/ORD-123` | Đúng một ví dụ | Ổn định cho kịch bản kiểm thử, nhưng không mô tả dải ID |

Pattern cần khớp **toàn bộ đoạn được framework kiểm tra** theo ngữ nghĩa regex mà Spring Cloud Contract dùng; tránh viết một regex mơ hồ và kỳ vọng nó chỉ so khớp substring.

### 8.2. Vì sao không dùng regex cho mọi path?

Nếu consumer thực sự gọi endpoint cố định `/api/orders/summary`, một regex như `/api/orders/.+` có thể vô tình khớp cả `summary` và các ID. Điều này khiến stub hoạt động khác producer thật hoặc che giấu nhầm lẫn giữa endpoint cố định và endpoint có path variable.

Ưu tiên literal khi kịch bản thực sự cố định; chỉ dùng regex khi giá trị biến đổi có ý nghĩa giao tiếp. Khi các matcher có vùng khớp chồng nhau, cần bổ sung điều kiện phân biệt hoặc thiết kế lại phạm vi hợp đồng, không dựa vào thứ tự file.

## 9. Path và query parameters: không được nhập làm một

Hai request sau có **cùng path**, nhưng query khác nhau:

~~~http
GET /api/orders?status=PAID&page=0 HTTP/1.1
GET /api/orders?status=PENDING&page=0 HTTP/1.1
~~~

- **Path:** `/api/orders`
- **Query parameters:** `status` và `page`

Trong Groovy DSL, nên nhóm chúng dưới `urlPath { queryParameters { ... } }`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('list_paid_orders')

    request {
        method GET()

        urlPath('/api/orders') {
            queryParameters {
                parameter 'status': 'PAID'
                parameter 'page': 0
                parameter 'size': 20
            }
        }

        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            items: [
                [orderId: 'ORD-123', status: 'PAID']
            ],
            page: 0
        )
    }
}
~~~

Contract mô tả request có path `/api/orders` và các query parameters cần thiết. Dùng literal đơn giản sẽ tạo điều kiện so khớp tương ứng; khi tham số cần biến đổi, Spring Cloud Contract hỗ trợ các query parameter matcher như `equalTo`, `containing`, `matching`.

### 9.1. Ví dụ YAML tương đương

~~~yaml
name: list_paid_orders
request:
  method: GET
  urlPath: /api/orders
  queryParameters:
    status: PAID
    page: 0
    size: 20
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    items:
      - orderId: ORD-123
        status: PAID
    page: 0
~~~

Trong YAML DSL, `queryParameters` là một mapping bên trong `request`. Cách biểu diễn này phân tách path và query rõ ràng; không tự coi `status=PAID` là path variable.

### 9.2. Phân biệt path variable với query parameter

| Request | Ý nghĩa | Cách mô tả |
| --- | --- | --- |
| `GET /api/orders/ORD-123` | Tra cứu một đơn cụ thể | Giá trị ID nằm trong `urlPath` |
| `GET /api/orders?status=PAID` | Tìm các đơn theo trạng thái | `urlPath('/api/orders')` + `queryParameters` |
| `GET /api/orders/ORD-123?includeItems=true` | Tra cứu một đơn với tùy chọn mở rộng | ID trong path, tùy chọn trong query |
| `GET /api/orders?page=2` | Phân trang tập hợp | Path cố định, chỉ số trang trong query |

Không thể tự chuyển `GET /api/orders/ORD-123` thành `GET /api/orders?id=ORD-123` mà vẫn coi là tương thích, trừ khi producer cố ý hỗ trợ cả hai cách và consumer được cập nhật hoặc đã sử dụng cả hai.

### 9.3. Có cần khai báo mọi query parameter?

Không. Một contract tốt ràng buộc các query parameters mà consumer **cần và thực sự phụ thuộc**. Nếu consumer không quan tâm một tham số tùy chọn, việc cố định nó có thể làm stub trở nên không cần thiết quá chặt. Ngược lại, nếu consumer phụ thuộc vào bộ lọc `status=PAID`, không mô tả query đó có thể khiến stub trả dữ liệu không đúng tình huống.

Bên cạnh đó, **tham số query thiếu, có giá trị rỗng và có giá trị cụ thể** là các trạng thái khác nhau. Nếu API có ý nghĩa khác nhau cho các trường hợp này, cần tạo những kịch bản contract riêng phù hợp.

## 10. Method và path là chưa đủ khi consumer có thêm điều kiện

Spring Cloud Contract định nghĩa HTTP request tối thiểu qua method và URL, nhưng đôi khi chỉ hai yếu tố đó chưa đủ để phân biệt hành vi. Những phần khác trong request có thể làm producer chọn một nhánh xử lý khác:

| Thành phần bổ sung | Ví dụ | Vì sao cần ghi vào contract? |
| --- | --- | --- |
| `Content-Type` | `application/json` | Producer cần biết cách parse request body |
| `Accept` | `application/json` hoặc `application/xml` | Consumer yêu cầu kiểu response cụ thể |
| Header nghiệp vụ | `X-Tenant-Id` | Request có thể định tuyến/giới hạn dữ liệu theo tenant |
| Query | `includeItems=true` | Đổi cấu trúc hoặc mức chi tiết phản hồi |
| Request body | JSON tạo đơn hàng | `POST` hoặc `PATCH` thường phụ thuộc payload |
| Path version | `/api/v2/orders` | Xác định phiên bản giao diện |

Ví dụ hai contract có thể cùng dùng `GET /api/orders/ORD-123` nhưng khác header `Accept` và vì vậy mong nhận response media type khác. Khi thiết kế stub, cần đưa điều kiện thực sự phân biệt hai trường hợp vào contract; nếu cả hai mapping khớp cùng request mà cho response khác nhau, kết quả consumer test có thể không như mong muốn.

### 10.1. Ví dụ request POST với đúng method và endpoint

~~~groovy
request {
    method POST()
    urlPath('/api/orders')
    headers {
        contentType(applicationJson())
    }
    body(
        customerId: 'CUS-7',
        items: [
            [sku: 'BK-1', quantity: 2]
        ]
    )
}
~~~

Nếu producer đổi thành `POST /api/order` (thiếu `s`) hoặc `PUT /api/orders`, generated producer test/consumer stub tương ứng cần phản ánh sự khác biệt. Không sửa contract cho khớp code mới mà chưa xem xét consumer cũ có bị ảnh hưởng không.

## 11. Một endpoint, nhiều method: nên tạo các contract riêng

Giả sử producer có cùng đường dẫn `/api/orders/ORD-123` nhưng hỗ trợ:

~~~http
GET /api/orders/ORD-123 HTTP/1.1
~~~

~~~http
PATCH /api/orders/ORD-123 HTTP/1.1
Content-Type: application/json

{"status":"CANCELLED"}
~~~

~~~http
DELETE /api/orders/ORD-123 HTTP/1.1
~~~

Đây là **ba tương tác khác nhau**. Không cố nhét ba method vào một dòng `method`, và không mặc định một contract được viết cho `GET` sẽ bảo vệ `PATCH` hoặc `DELETE`.

Có thể tổ chức thành các file:

~~~text
src/test/resources/contracts/orders/
├── get_order.groovy
├── cancel_order.groovy
└── delete_order.groovy
~~~

Hoặc nhóm các contract có liên quan vào một tệp trả về danh sách `Contract.make`. Dù chọn cách nào, **mỗi contract phải có điều kiện request riêng và phản hồi mong đợi riêng**.

### 11.1. HTTP `404`, `405` và thay đổi đường dẫn

Trong những ứng dụng web thông dụng:

- `404 Not Found` thường xảy ra khi không có route/tài nguyên phù hợp, nhưng không phải mọi `404` đều do path không tồn tại.
- `405 Method Not Allowed` thường xảy ra khi route được nhận diện nhưng method không được hỗ trợ.
- `301`, `302` hoặc `308` có thể xuất hiện nếu server/proxy thực hiện redirect.

Mã cụ thể phụ thuộc server, routing, security và cấu hình ứng dụng. Hợp đồng cần bám vào **status thực sự là cam kết với consumer**, không suy ra máy móc rằng đổi method luôn tạo `405` hay đổi path luôn tạo `404`.

## 12. Những thay đổi nào phá vỡ hợp đồng method/path?

Xét consumer đang gửi `GET /api/v1/orders/ORD-123`. Các thay đổi producer có tác động khác nhau:

| Thay đổi từ producer | Có thể tương thích với consumer cũ? | Lý do |
| --- | --- | --- |
| Đổi sang `POST /api/v1/orders/ORD-123` và bỏ `GET` | Không | Consumer vẫn gửi `GET` |
| Đổi path sang `/api/v2/orders/ORD-123` và bỏ v1 | Không | Consumer vẫn dùng path v1 |
| Giữ endpoint cũ, bổ sung endpoint mới | Có thể | Consumer cũ vẫn gọi được endpoint đã cam kết |
| Đổi tên method Java hoặc class controller | Có | Không thay đổi giao tiếp HTTP nếu routing/response giữ nguyên |
| Thêm path segment bắt buộc `/tenant/1` | Không với client cũ | Request cũ không khớp endpoint mới |
| Chuyển `orderId` từ path sang query và bỏ path cũ | Không | Client cũ không tự đổi URL |
| Thêm query parameter tùy chọn có default tương thích | Thường có thể | Request cũ vẫn hợp lệ nếu server giữ hành vi đã cam kết |
| Thêm query parameter bắt buộc | Có thể phá vỡ | Client cũ không gửi trường mới |
| Chuyển `/api/orders` thành `/api/orders/` | Phụ thuộc cấu hình | Path có thể được phân biệt ở router/proxy |

**Chiến lược tiến hóa API:** Nếu cần đổi method hoặc path, có thể giữ route cũ trong thời gian chuyển đổi, bổ sung route mới, cập nhật consumer theo lộ trình và chỉ xóa route cũ khi đã xác minh không còn consumer phụ thuộc. Một phiên bản URL mới không tự động khiến client cũ tương thích.

## 13. Producer tests và Stub Runner kiểm chứng method/path ra sao?

Với contract:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('get_order_by_id')

    request {
        method GET()
        urlPath('/api/orders/ORD-123')
    }

    response {
        status OK()
        body(
            orderId: 'ORD-123',
            status: 'CONFIRMED'
        )
    }
}
~~~

Luồng thông dụng:

~~~mermaid
flowchart TD
    A["Contract: GET /api/orders/ORD-123"] --> B["Plugin sinh test phía producer"]
    B --> C["Test gọi producer/MockMvc bằng GET và path đã định"]
    C --> D{"Phản hồi phù hợp contract?"}
    D -- "Không" --> E["Producer verification thất bại"]
    D -- "Có" --> F["Producer verification đạt"]
    A --> G["Plugin sinh stub cho request tương ứng"]
    F --> H["Phát hành stub artifact có version"]
    G --> H
    H --> I["Consumer test dùng Stub Runner"]
    I --> J["Kiểm tra client gọi đúng method/path"]
~~~

**Phía producer:** Generated test gửi request tương ứng với method và path trong DSL. Base class phải cung cấp môi trường chạy phù hợp (chẳng hạn Spring MVC/MockMvc) và fixture để producer trả response theo contract.

**Phía consumer:** Stub Runner có thể khởi chạy stub từ artifact được phát hành. Nếu consumer vô tình đổi method `GET` thành `POST` hoặc gọi sai path, stub mapping của tương tác đã thống nhất có thể không khớp request, giúp phát hiện lỗi ở cách client giao tiếp.

Contract test **không tự kiểm tra mọi route**, càng không thay thế kiểm thử security, cấu hình proxy, hiệu năng hoặc routing ở gateway thật. Nó bảo vệ các tương tác đã được viết, được sinh test và thực sự được chạy.

### 13.1. Đưa producer verification vào CI

Với một dự án Maven đã cấu hình Spring Cloud Contract plugin:

~~~bash
./mvnw -B clean verify
~~~

Với một dự án Gradle đã cấu hình plugin và test tasks phù hợp:

~~~bash
./gradlew clean build
~~~

Các lệnh chỉ minh họa cách chạy pipeline. Việc sinh test và thực thi contract phụ thuộc cấu hình build, phiên bản Spring Boot/Spring Cloud Contract và base test class của dự án.

Một CI có giá trị cần kiểm tra:

1. Contract Groovy/YAML được đưa vào nguồn được plugin đọc.
2. Generated producer tests được **sinh và chạy**, không bị skip.
3. Một thay đổi phá vỡ method/path khiến test thất bại như mong muốn.
4. Stub được phát hành sau khi producer đã vượt qua kiểm chứng tương ứng.
5. Consumer CI sử dụng phiên bản stub được quản lý để phát hiện lời gọi sai endpoint.

## 14. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Contract DSL không hợp lệ | Thiếu `method` hoặc cả `url` và `urlPath` | Kiểm tra hai thuộc tính bắt buộc; chọn đúng một dạng URL |
| Test trả `404` thay vì `200` | Path sai hoặc fixture không có tài nguyên | So sánh request path, controller mapping, setup dữ liệu |
| Test trả `405` | Method sai so với route đã đăng ký | Đối chiếu method của consumer, contract và producer |
| Test sai ở môi trường CI | Hợp đồng khóa host/port local | Dùng path tương đối phù hợp hoặc cấu hình môi trường đúng |
| Stub không khớp request | Query/header khác hoặc regex quá chặt | Kiểm tra điều kiện matching thực tế |
| Stub khớp sai tình huống | Regex quá rộng hoặc mappings chồng lấn | Thu hẹp mẫu/điều kiện phân biệt |
| Path có khoảng trắng/Unicode | Encode khác giữa client và server | Thống nhất cách percent-encode và kiểm tra dữ liệu trên đường truyền |
| Endpoint có dấu slash cuối | Router phân biệt `/orders` và `/orders/` | Thống nhất URL public hoặc kiểm tra redirect có chủ đích |
| Generated test không xuất hiện | Chưa cấu hình plugin, sai đường dẫn contract, build skip | Xem logs của bước sinh và test execution |
| Test chuyển hướng bất ngờ | Gateway, proxy hoặc filter đổi path/redirect | Kiểm tra request target qua từng tầng và cam kết public |

### 14.1. Checklist khi gặp lỗi method/path

Khi generated test thất bại, nên lần lượt đối chiếu:

1. **Contract:** `method` là gì, `url`/`urlPath` là gì, có query/header nào đi kèm?
2. **Generated request:** Test thực gửi đến URL nào, có giá trị path động hay được encode không?
3. **Routing producer:** `@GetMapping`/`@PostMapping`/cấu hình gateway có trùng method và path?
4. **Base class:** Có khởi tạo đúng controller, servlet context path, dữ liệu mẫu và filter?
5. **Response:** Sai vì không tìm thấy route, vì không có dữ liệu hay vì producer phá vỡ cam kết?

Không sửa mã generated test trong thư mục đầu ra của build để che lỗi: ở lần sinh kế tiếp, các thay đổi đó sẽ bị ghi đè. Nguồn sửa là contract, setup hoặc code producer.

## 15. Bài thực hành: xây hợp đồng HTTP cho Inventory Service

Giả sử `Inventory Service` cung cấp ba hành vi:

| Tình huống | Request | Kết quả cần kiểm chứng |
| --- | --- | --- |
| Tra cứu tồn kho | `GET /api/inventory/SKU-100` | `200`, `sku: SKU-100`, `available: 8` |
| Lọc tồn kho theo kho | `GET /api/inventory?warehouse=HCM&page=0` | `200`, danh sách các SKU trong kho |
| Cập nhật tồn kho | `PATCH /api/inventory/SKU-100` | `200`, số lượng mới hoặc mã lỗi nghiệp vụ phù hợp |

### 15.1. Nhiệm vụ

1. Viết hợp đồng Groovy cho `GET /api/inventory/SKU-100`, sử dụng `method` và `urlPath`.
2. Viết hợp đồng YAML tương đương cho cùng tình huống. Không đồng thời kích hoạt hai contract trùng nhau trong cùng source tree khi kiểm chứng build.
3. Viết hợp đồng Groovy thứ hai cho `GET /api/inventory` với hai query parameters `warehouse=HCM` và `page=0`.
4. Chọn một request mẫu cho `PATCH /api/inventory/SKU-100` với body `{"available": 10}`. Giải thích vì sao không thể dùng contract `GET` để kiểm chứng request `PATCH` này.
5. Giả định producer bỏ đường dẫn `/api/inventory/SKU-100` và chỉ hỗ trợ `/api/stock/SKU-100`. Dự đoán bước producer verification nào phải thất bại.
6. Sửa producer để duy trì endpoint cũ hoặc thống nhất contract mới cùng consumer; chạy lại kiểm chứng theo pipeline hiện có.

### 15.2. Gợi ý lời giải Groovy cho tra cứu một SKU

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('inventory_get_sku_success')

    request {
        method GET()
        urlPath('/api/inventory/SKU-100')
        headers {
            accept(applicationJson())
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-100',
            available: 8
        )
    }
}
~~~

### 15.3. Gợi ý lời giải YAML

~~~yaml
name: inventory_get_sku_success
request:
  method: GET
  urlPath: /api/inventory/SKU-100
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-100
    available: 8
~~~

### 15.4. Gợi ý lời giải query parameters

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    name('inventory_search_by_warehouse')

    request {
        method 'GET'
        urlPath('/api/inventory') {
            queryParameters {
                parameter 'warehouse': 'HCM'
                parameter 'page': 0
            }
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            items: [
                [sku: 'SKU-100', available: 8]
            ]
        )
    }
}
~~~

Để kiểm chứng `PATCH`, cần một contract riêng với `method PATCH()` (hoặc `'PATCH'`), `urlPath('/api/inventory/SKU-100')` và body JSON đã thống nhất. Path có thể giống `GET` nhưng method khác, nên hai tình huống phải được kiểm tra độc lập.

### 15.5. Tự đánh giá

- Khi đổi `GET` thành `POST`, test producer cũ phải phản ứng thế nào?
- Khi đổi `/api/inventory/SKU-100` thành `/api/stock/SKU-100`, có nên chỉ sửa contract và bỏ qua consumer đang chạy không?
- Tham số `warehouse=HCM` thuộc path hay query? Nếu bỏ nó khỏi contract, stub có còn phân biệt đúng kho?
- Khi dùng matcher `/api/inventory/SKU-[0-9]+`, vì sao phải cân nhắc dữ liệu response và các endpoint cố định có thể trùng mẫu?

**Đáp án định hướng:** Method và path là cam kết giao tiếp, thay đổi chúng có thể phá vỡ client cũ; query parameters là thành phần riêng; regex nên đủ chặt và response stub cần nhất quán với request thực tế.

## 16. Checklist trước khi lưu một HTTP contract

- [ ] Contract khai báo rõ **method** mà consumer thực sự gửi.
- [ ] Contract sử dụng **một** trong hai thuộc tính `url` hoặc `urlPath`.
- [ ] Path được viết đúng với giao diện công khai, gồm prefix, phiên bản và slash khi cần.
- [ ] Đã phân biệt path variable, query parameter và header.
- [ ] Nếu dùng regex cho path động, có giá trị producer-side cụ thể để generated test chạy ổn định.
- [ ] Matcher không quá rộng khiến stub nhầm endpoint hoặc nhầm dữ liệu trả về.
- [ ] Có các hợp đồng riêng cho những method/tình huống khác nhau mà consumer phụ thuộc.
- [ ] Có fixture và base class đủ để producer trả về kết quả theo contract.
- [ ] Đã đánh giá thay đổi method/path về tương thích với consumer trước khi merge.
- [ ] CI sinh **và chạy** producer tests; stub được phát hành theo phiên bản producer đã xác minh.

## 17. Tài liệu tham khảo

- [Spring Cloud Contract — HTTP Contracts](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/http.html): các thành phần bắt buộc của HTTP request, `url`, `urlPath` và query parameters.
- [Spring Cloud Contract — Dynamic Properties](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract/dsl-dynamic-properties.html): matcher và giá trị consumer/producer dùng trong contract.
- [Spring Cloud Contract — Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML DSL, cấu trúc contract và cơ chế sinh stub/test.

**Ghi nhớ:** **HTTP method và đường dẫn yêu cầu** là hai cam kết đầu tiên của một HTTP contract. `GET /api/orders/ORD-123` là một tương tác khác với `POST /api/orders/ORD-123` hoặc `GET /api/orders?id=ORD-123`. Hãy mô tả đúng request của consumer bằng Groovy/YAML DSL, giữ matcher đủ chính xác và chạy generated producer tests trong CI trước khi phát hành stub.
