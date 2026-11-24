# FallbackHeaders và thông tin lỗi được phép chuyển tiếp trong Spring Cloud Gateway

Khi một microservice lỗi, **Spring Cloud Gateway** có thể kích hoạt `CircuitBreaker` để đưa request sang một phương án dự phòng (**fallback**). Nhưng fallback service cần biết *vì sao* request rẽ hướng để trả kết quả phù hợp hoặc ghi nhận sự cố. Nếu gửi nguyên nội dung exception qua HTTP header, Gateway có nguy cơ làm lộ chi tiết triển khai, dữ liệu nhạy cảm hay thông tin của hệ thống upstream.

`FallbackHeaders` là một **GatewayFilter Factory** dành cho trường hợp **Gateway forward tới một đường dẫn fallback, sau đó một route khác chuyển request tới ứng dụng fallback bên ngoài**. Nó đọc thông tin ngoại lệ mà cơ chế CircuitBreaker đã gắn vào exchange và **bổ sung các request headers mang kiểu lỗi và thông điệp lỗi** trước khi chuyển tiếp.

Bài học thuộc chương **Ngắt mạch và dự phòng** của **SPRING_CLOUD_GATEWAY**. Mục tiêu không chỉ là bật bộ lọc, mà còn **quyết định thông tin lỗi nào được phép đi qua ranh giới tin cậy**. Ta sẽ kết hợp route predicate, filter chain, biến đổi path/header, service discovery, xác thực, rate limiting, retry, TLS và quan sát request để vận hành một Gateway microservices an toàn.

> **Phạm vi:** Ví dụ sử dụng **Spring Cloud Gateway Server WebFlux** với namespace `spring.cloud.gateway.routes` thường gặp ở các dòng Gateway 4.x. Các dòng phát hành mới hơn hoặc Gateway Server MVC có thể thay đổi starter, namespace và hành vi tích hợp. Tên factory/thuộc tính cần đối chiếu với tài liệu **đúng phiên bản** trước khi áp dụng. Địa chỉ và service name bên dưới chỉ là môi trường minh họa.

## 1. CircuitBreaker, fallbackUri và FallbackHeaders có trách nhiệm khác nhau

Giả sử Gateway định tuyến `GET /api/catalog/42` đến `catalog-service`. Nếu downstream không khả dụng, có thể cần trả một thông báo dự phòng, chẳng hạn mã `503` với nội dung lỗi tổng quát.

Có ba công việc khác nhau:

| Thành phần | Câu hỏi được giải quyết | Vai trò |
|---|---|---|
| `CircuitBreaker` GatewayFilter | Khi nào một lệnh gọi downstream thất bại hoặc bị ngắt mạch? | Phát hiện lỗi theo chính sách circuit breaker và chuyển sang fallback nếu được cấu hình |
| `fallbackUri: forward:/fallback` | Fallback sẽ được xử lý theo đường dẫn nội bộ nào? | **Forward trong ứng dụng Gateway** đến một handler/route phù hợp |
| `FallbackHeaders` GatewayFilter | Route tới ứng dụng fallback ngoài sẽ nhận những metadata lỗi nào? | Lấy thông tin exception liên quan CircuitBreaker rồi bổ sung **request headers** |
| Fallback service | Client cuối cùng sẽ nhận HTTP status/body nào? | Tạo response an toàn, có thể là dữ liệu degraded hoặc lỗi tổng quát |

`FallbackHeaders` **không tự phát hiện lỗi**, **không thay thế CircuitBreaker**, **không tự sinh fallback response** và **không chọn instance downstream**. Nó là thành phần vận chuyển metadata của exception cho ứng dụng fallback khi có ngữ cảnh lỗi phù hợp.

Một route dùng CircuitBreaker nhưng fallback được xử lý hoàn toàn bởi một handler nội bộ **không nhất thiết cần** `FallbackHeaders`. Ngược lại, chỉ đặt `FallbackHeaders` trên một route mà không có thông tin exception từ CircuitBreaker thì không tự tạo ra lý do thất bại.

### Luồng hai route tới fallback service bên ngoài

~~~mermaid
flowchart TD
    C["Client GET /api/catalog/42"] --> M["Route catalog-main"]
    M --> CB["CircuitBreaker: catalogBreaker"]
    CB -->|Thành công| S["catalog-service"]
    S --> OK["Response bình thường"]
    CB -->|Lỗi / circuit open theo policy| FW["forward:/fallback"]
    FW --> R["Route catalog-fallback"]
    R --> FH["FallbackHeaders đọc exception metadata"]
    FH --> EX["Fallback service qua http:// hoặc lb://"]
    EX --> SAFE["Tạo status/body an toàn"]
    SAFE --> C
    OK --> C
~~~

**Điểm mấu chốt:** `fallbackUri` và URI của route fallback là **hai địa chỉ có chức năng khác nhau**. `forward:/fallback` dùng scheme `forward:` để xử lý trong Gateway; còn `uri: http://localhost:9095` hoặc `lb://fallback-service` trong route thứ hai chỉ nơi ứng dụng fallback thực sự hoạt động.

## 2. Vì sao cần FallbackHeaders khi fallback nằm ở ứng dụng khác?

Trong luồng CircuitBreaker, ngoại lệ có thể được lưu ở **thuộc tính của `ServerWebExchange`** mà các filter và handler trong Gateway có khả năng truy cập. Nhưng khi Gateway chuyển một request HTTP tới **ứng dụng fallback bên ngoài**, thuộc tính Java trong exchange **không tự xuất hiện** ở tiến trình downstream.

Ví dụ một lệnh gọi tới `catalog-service` bị từ chối kết nối:

~~~text
Gateway exchange (trong tiến trình Gateway):
  failure = ConnectException / request failed

HTTP request từ Gateway tới fallback service:
  Chỉ có method, URI, headers, body... theo cơ chế routing
  Không mang toàn bộ ServerWebExchange Java
~~~

`FallbackHeaders` giúp **đưa một số thông tin lỗi vào request headers** trong bước route tới fallback service để ứng dụng bên ngoài có thể phân loại tình huống, ghi metrics hoặc chọn kết quả degraded.

Đây là **tăng khả năng trao đổi thông tin trong một đường đi nội bộ**, không phải lời khuyên gửi exception message tới mọi client bên ngoài. Request headers đến fallback service và response headers trả về browser là hai chiều khác nhau.

### Không nhầm với response headers

~~~http
GET /fallback HTTP/1.1
Host: fallback.internal.test
Execution-Exception-Type: java.net.ConnectException
Execution-Exception-Message: Connection refused
~~~

Đoạn trên minh họa **request Gateway → fallback service**. Nếu fallback service trả:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"code":"CATALOG_TEMPORARILY_UNAVAILABLE","message":"Please retry later"}
~~~

thì browser thường chỉ thấy **response status/body** do fallback service và Gateway trả lại. `FallbackHeaders` không có nhiệm vụ tự copy tất cả các header exception vào response cho client; tuy vậy, **ứng dụng fallback có thể vô tình echo chúng**, nên cần thiết kế và kiểm thử để bảo đảm không lộ.

## 3. Bốn loại header mà FallbackHeaders có thể tạo

Theo mô hình của `FallbackHeaders` trong Gateway Server WebFlux, bốn thuộc tính tên header có thể được tùy biến. Những tên mặc định phổ biến là:

| Thuộc tính cấu hình | Tên header mặc định | Giá trị về mặt ý nghĩa |
|---|---|---|
| `executionExceptionTypeHeaderName` | `Execution-Exception-Type` | Tên kiểu/class của exception mà circuit breaker lưu cho lần thực thi |
| `executionExceptionMessageHeaderName` | `Execution-Exception-Message` | Nội dung `message` của exception ấy |
| `rootCauseExceptionTypeHeaderName` | `Root-Cause-Exception-Type` | Tên kiểu/class của nguyên nhân gốc khi tìm thấy |
| `rootCauseExceptionMessageHeaderName` | `Root-Cause-Exception-Message` | Nội dung message của nguyên nhân gốc khi tìm thấy |

**Không phải request fallback nào cũng có đủ bốn header.** Khi không có thuộc tính exception hoặc không tìm thấy root cause, header liên quan có thể vắng mặt. Exception message có thể rỗng, `null` về mặt API, hoặc bị giới hạn bởi quy tắc hợp lệ của HTTP header; ứng dụng fallback phải kiểm tra thiếu header và không giả định mọi giá trị luôn có.

### Execution exception khác root cause thế nào?

Giả định một HTTP call thất bại, và exception mà CircuitBreaker ghi nhận có dạng:

~~~text
ReactiveClientException
  caused by ConnectionException
    caused by ConnectException("Connection refused")
~~~

- **Execution exception** là exception đại diện cho lần thực thi được lưu trong ngữ cảnh CircuitBreaker; có thể là wrapper.
- **Root cause** là nguyên nhân sâu hơn trong chuỗi `cause` nếu tìm thấy.

Một tình huống circuit đang **OPEN** có thể tạo loại exception biểu thị “không cho phép call” thay vì lỗi kết nối mới. Khi đó không nên suy rằng mọi lần fallback đều có root cause là `ConnectException`.

**Đừng dùng tên class làm hợp đồng nghiệp vụ lâu dài.** Sau khi nâng thư viện hoặc thay implementation (Reactor Netty, Resilience4j, load balancer), exception type hoặc message có thể thay đổi dù ý nghĩa lỗi với client vẫn giống.

### Thông tin trong message có thể nhạy cảm

Thông điệp exception có thể vô tình chứa:

- Hostname nội bộ, service ID, port, URI và query string.
- Một phần đường dẫn filesystem, tên class/package, dữ liệu SQL hoặc cấu trúc schema.
- Dữ liệu người dùng nếu logging/exception handling không che thông tin.
- Trong một số tình huống lỗi do downstream tạo, thông điệp chứa request context có token hoặc định danh nhạy cảm.

**Tùy biến tên header không đồng nghĩa làm sạch nội dung.** Đổi `Execution-Exception-Message` thành `X-Edge-Error-Detail` chỉ đổi tên, **không loại bỏ dữ liệu bí mật**. Đây là giới hạn bảo mật quan trọng nhất của `FallbackHeaders`.

## 4. Cấu hình tối thiểu: CircuitBreaker forward và route fallback ngoài

Giả sử:

- Gateway lắng nghe `http://localhost:8080`.
- Backend catalog ở `http://localhost:9090`.
- Ứng dụng fallback tin cậy ở `http://localhost:9095`, có endpoint `GET /fallback`.

Cấu hình minh họa:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-main
          uri: http://localhost:9090
          predicates:
            - Path=/api/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogBreaker
                fallbackUri: forward:/fallback

        - id: catalog-fallback
          uri: http://localhost:9095
          predicates:
            - Path=/fallback
          filters:
            - name: FallbackHeaders
~~~

**Cách đọc:**

1. Request `/api/catalog/42` match route `catalog-main`.
2. `CircuitBreaker` bảo vệ lệnh gọi tới backend catalog theo chính sách được cấu hình.
3. Nếu gọi thất bại theo những điều kiện mà CircuitBreaker xử lý, Gateway forward nội bộ tới `/fallback`.
4. Route `catalog-fallback` match đường dẫn `/fallback` và dùng `FallbackHeaders`.
5. Gateway chuyển request sang ứng dụng fallback ở `http://localhost:9095`; fallback service có thể nhận các request headers về exception.
6. Fallback service quyết định **HTTP response cuối**.

Ví dụ trên là **lab nội bộ** để quan sát header, chưa phải cấu hình nên đưa nguyên văn lên Internet. Đường dẫn `/fallback` có thể được client gọi trực tiếp; route fallback vì thế cần ranh giới truy cập và lọc headers phù hợp ở production.

### Tại sao fallbackUri không trỏ thẳng URL ngoài?

Với CircuitBreaker GatewayFilter, mẫu `fallbackUri` được hỗ trợ theo thiết kế **forward** đến một đường dẫn nội bộ như `forward:/fallback`. Nếu muốn một ứng dụng fallback chạy ở host/service khác, dùng **route thứ hai** có URI `http://...` hoặc `lb://...` cho đường dẫn forward.

Không tự thay thành:

~~~yaml
# KHÔNG giả định CircuitBreaker hỗ trợ fallback trực tiếp kiểu này:
fallbackUri: http://localhost:9095/fallback
~~~

Khi muốn gọi fallback service ngoài, hãy theo mô hình **forward nội bộ → route fallback → FallbackHeaders → outbound routing** như phần trên và xác minh với đúng phiên bản Gateway.

## 5. Tùy chỉnh tên các header

Một đội vận hành có thể muốn dùng prefix nhất quán trên đường truyền nội bộ, chẳng hạn `X-Edge-Fallback-*`:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-fallback
          uri: http://localhost:9095
          predicates:
            - Path=/fallback
          filters:
            - name: FallbackHeaders
              args:
                executionExceptionTypeHeaderName: X-Edge-Fallback-Exec-Type
                executionExceptionMessageHeaderName: X-Edge-Fallback-Exec-Message
                rootCauseExceptionTypeHeaderName: X-Edge-Fallback-Root-Type
                rootCauseExceptionMessageHeaderName: X-Edge-Fallback-Root-Message
~~~

Đây là một **route fallback thay thế** cho route `catalog-fallback` ở phần 4, không phải đoạn YAML cần copy thêm vào cùng ứng dụng với một route ID trùng nhau.

Các thuộc tính `args` nhận **tên HTTP header**, không phải giá trị exception cố định. Loại exception/message được lấy từ ngữ cảnh thực thi tại runtime nếu có.

| Yêu cầu vận hành | Khả năng của FallbackHeaders |
|---|---|
| Đổi tên bốn header | Có, qua bốn thuộc tính trên |
| Chuyển metadata exception thành request headers | Có, khi có ngữ cảnh lỗi tương ứng |
| Chuyển sang chỉ một mã nghiệp vụ an toàn như `UPSTREAM_UNAVAILABLE` | **Không tự thực hiện** chỉ bằng đổi tên header |
| Che token, địa chỉ nội bộ hoặc PII trong message | **Không tự thực hiện** |
| Tự xác thực fallback service | Không |
| Ép response của fallback thành 503 | Không |
| Truyền cả stack trace hoàn chỉnh | Không phải hợp đồng được mô tả bởi bốn header này |

**Chỉ đổi tên header khi thật sự cần hợp đồng nội bộ rõ ràng.** Nếu chính sách cấm gửi raw exception messages tới ứng dụng bên ngoài, **không nên bật FallbackHeaders chỉ để đổi tên**; hãy dùng cơ chế phân loại lỗi an toàn hoặc đưa ra message đã được làm sạch bằng một handler/filter tùy biến phù hợp.

## 6. Đường đi chính xác của request và metadata lỗi

Một request thất bại có hai lần chuyển hướng xử lý đáng phân biệt: lần đầu gọi catalog, lần sau gọi fallback.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant U as catalog-service
    participant F as fallback-service
    C->>G: GET /api/catalog/42
    G->>G: Match catalog-main + CircuitBreaker
    G->>U: Forward request tới catalog
    U--xG: Lỗi kết nối / exception
    Note over G: CircuitBreaker ghi nhận lỗi và chọn forward:/fallback
    G->>G: Match route catalog-fallback
    G->>G: FallbackHeaders đọc execution exception / root cause
    G->>F: GET /fallback + headers lỗi (nếu có)
    F->>F: Chỉ dùng metadata nội bộ, không echo raw message
    F-->>G: 503 + JSON lỗi tổng quát
    G-->>C: 503 + JSON lỗi tổng quát
~~~

Trong request thực tế, cấu hình route, method, path rewrite, filter order và cách forward của phiên bản có thể ảnh hưởng đường dẫn/phần headers cuối cùng. Sơ đồ cố ý mô tả luồng **khái niệm**. Hãy quan sát request thực tế ở fallback service để xác nhận nó nhận path nào, header nào và có cần đổi path bằng `SetPath`/`RewritePath` hay không.

### Metadata được đưa vào đâu?

Thông tin lỗi phát sinh từ **CircuitBreaker execution** được lưu trong **ngữ cảnh exchange** trong Gateway. `FallbackHeaders` đọc ngữ cảnh đó khi filter chạy trên route fallback rồi mutate **request**. Đừng nhầm nó với:

- Claim trong JWT.
- Request header do client gửi ban đầu.
- HTTP response status/body mà backend catalog trả về.
- Log hoặc trace được ghi bởi hệ thống giám sát.
- Error response JSON mà fallback service cuối cùng tạo ra.

**Thuộc tính exchange không tự đi xuyên process.** Chính request headers là phương tiện truyền dữ liệu sang fallback service trong mẫu này.

### Nếu request tới /fallback trực tiếp thì sao?

Client có thể gọi:

~~~http
GET /fallback HTTP/1.1
Host: gateway.example.test
Execution-Exception-Type: forged-by-client
~~~

Một request trực tiếp không nhất thiết có execution exception do CircuitBreaker vừa tạo. `FallbackHeaders` không phải cơ chế **xác minh nguồn gốc** của header có sẵn. Vì vậy, nếu fallback endpoint public và backend tin header không kiểm tra, client có thể gửi **metadata giả mạo**.

Biện pháp tối thiểu là loại bỏ những header client có thể tự đặt trước khi gắn metadata do Gateway quản lý, đồng thời kiểm soát đường truy cập fallback route. Phần tiếp theo đi sâu vào ranh giới tin cậy này.

## 7. Chính sách thông tin lỗi được phép chuyển tiếp

**Không có danh sách header “an toàn tuyệt đối” cho mọi tổ chức.** Phải phân loại theo nội dung thực, độ tin cậy của fallback service và nhu cầu nghiệp vụ.

| Loại thông tin | Mức rủi ro | Khuyến nghị |
|---|---|---|
| Mã lỗi nghiệp vụ trừu tượng, ví dụ `UPSTREAM_UNAVAILABLE` | Thấp nếu không tiết lộ nội bộ | Ưu tiên dùng trong contract/response |
| Correlation ID ngẫu nhiên, không chứa danh tính | Thấp–trung bình | Có thể chuyển để tra cứu logs, kiểm tra định dạng/nguồn |
| Tên exception class, ví dụ `ConnectException` | Trung bình | Chỉ chuyển qua kênh nội bộ khi có lý do |
| Root-cause exception class | Trung bình–cao | Có thể tiết lộ thư viện/framework hoặc topology |
| Raw exception message | Cao hoặc không xác định | Mặc định **không xuất qua trust boundary** nếu chưa được đánh giá |
| URI/hostname nội bộ và query string | Cao tùy endpoint | Không trả client; cân nhắc che cả khi chuyển giữa services |
| Access token, API key, cookie/session ID | Rất cao | **Không đưa vào error headers/logs** |
| Stack trace đầy đủ, SQL/connection string | Rất cao | Chỉ lưu trong hệ thống chẩn đoán được bảo vệ, tránh đưa vào HTTP metadata |

Một chính sách thực tế có thể định nghĩa:

- **Client chỉ nhận:** `code`, thông điệp người dùng, correlation ID, status theo hợp đồng; có thể có `Retry-After` khi đã xác định thời gian chờ hợp lý.
- **Fallback service nội bộ nhận:** mã phân loại lỗi **đã được làm sạch**, route/service ID được phê duyệt, correlation ID.
- **Observability nội bộ nhận:** nguyên nhân kỹ thuật chi tiết ở mức cần thiết, nhưng phải redact token/PII và giới hạn quyền đọc.

### FallbackHeaders có phù hợp mọi ranh giới tin cậy không?

**Không.** Factory được thiết kế để chuyển **execution exception details**, bao gồm message. Nếu ứng dụng fallback là một dịch vụ do bên thứ ba quản lý hoặc ở một miền bảo mật kém tin cậy, việc gửi raw message có thể vi phạm chính sách dữ liệu.

Nếu chỉ muốn đưa một mã ổn định `CATALOG_UNAVAILABLE`, lựa chọn tốt hơn có thể là:

1. Để fallback service trả mã đó theo ngữ cảnh route/endpoint đã biết, **không cần FallbackHeaders**; hoặc
2. Xây dựng handler/filter tùy biến phân loại exception trong Gateway, **lọc bỏ chi tiết nhạy cảm** rồi chỉ tạo header được cho phép; hoặc
3. Duy trì `FallbackHeaders` trong một mạng nội bộ tin cậy, nhưng có lớp kiểm soát/bỏ những header không cho phép trước bước outbound, được kiểm thử nghiêm ngặt.

Không nên coi việc chỉ sửa tên bốn header là một bước sanitization.

## 8. Ngăn giả mạo và chặn rò rỉ credentials trên route fallback

Khi route fallback có thể nhận cả request nội bộ lẫn request từ client, cần tránh trộn **header client tự gửi** với **header do Gateway tạo**.

Ở route lab dùng tên mặc định, có thể áp dụng các filter xóa request headers đầu vào trước `FallbackHeaders`:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-fallback
          uri: http://localhost:9095
          predicates:
            - Path=/fallback
          filters:
            - RemoveRequestHeader=Execution-Exception-Type
            - RemoveRequestHeader=Execution-Exception-Message
            - RemoveRequestHeader=Root-Cause-Exception-Type
            - RemoveRequestHeader=Root-Cause-Exception-Message
            - RemoveRequestHeader=Authorization
            - RemoveRequestHeader=Cookie
            - name: FallbackHeaders
~~~

**Cấu hình này chỉ thích hợp trong lab hoặc một đường truyền nội bộ đã được phê duyệt.** Nó thể hiện ý định xóa các header trùng tên do client đưa vào và không chuyển tiếp credentials tới fallback service khi không cần. Nhưng sau đó `FallbackHeaders` vẫn có thể thêm **raw exception messages**, nên **chưa đủ** để đạt chính sách chỉ truyền mã lỗi đã làm sạch.

Thêm lưu ý:

- `RemoveRequestHeader` là filter **request**; nó không xóa thông tin đã lộ trong logs, body hoặc response.
- Các filter phải thực sự chạy theo thứ tự mong muốn **trước outbound routing**. Cần xác minh request backend nhận và tác động của default/global filters.
- Client vẫn có thể gọi thẳng `/fallback` nếu route/path được public. Nên hạn chế ở ingress/network/security layer và xem cơ chế forward nội bộ có bị tác động khi chặn path ấy không.
- Nếu fallback service cần xác thực, sử dụng **service-to-service authentication** được thiết kế riêng, không chuyển đại trà Authorization/Cookie từ client.
- Với các deployment có proxy, kiểm tra `Forwarded`, `X-Forwarded-*`, `Host` và các header nội bộ theo chính sách trusted proxies.
- Một filter chỉ remove bốn tên mặc định **không chặn tên tùy biến** nếu bạn đã dùng `X-Edge-Fallback-*`. Hãy đồng bộ danh sách xóa và tên cấu hình thực tế.

**Không dựa vào việc FallbackHeaders chỉ chạy khi có exception để chứng minh caller là Gateway nội bộ.** Nguồn thực sự của request phải được xác minh bằng mạng, identity/service credential hoặc cơ chế tin cậy tương đương.

## 9. Phương án an toàn hơn khi chỉ cần mã lỗi

Nếu yêu cầu bảo mật quy định **fallback service không được nhận tên class hay exception message**, hãy ưu tiên endpoint fallback cố định và response an toàn, bỏ `FallbackHeaders`:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-main
          uri: http://localhost:9090
          predicates:
            - Path=/api/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogBreaker
                fallbackUri: forward:/fallback

        - id: catalog-fallback
          uri: http://localhost:9095
          predicates:
            - Path=/fallback
          filters:
            - RemoveRequestHeader=Authorization
            - RemoveRequestHeader=Cookie
            - SetRequestHeader=X-Edge-Fallback-Category,CATALOG_UNAVAILABLE
~~~

Trong ví dụ, fallback service biết **loại fallback theo route/endpoint**, chứ không cần biết raw exception. Header phân loại chỉ là metadata nội bộ. **Không tin header này nếu fallback route bị client gọi trực tiếp**; vẫn phải chặn hoặc xác minh caller và xóa header client tự gửi trước khi gắn header tin cậy.

Nếu thực sự cần phân biệt `TIMEOUT`, `CIRCUIT_OPEN`, `CONNECTION_FAILURE`, hãy dùng một cơ chế phân loại **cho phép danh sách nhỏ các mã chuẩn hóa**, dựa trên exception trong Gateway, không nhét nguyên message/stack trace vào header. Đưa các chi tiết sâu vào logs/tracing được bảo vệ.

### Không chuyển raw lỗi thành 200 một cách máy móc

Một fallback có thể được thiết kế theo hai mô hình:

- **Degraded success:** trả kết quả dự phòng có ý nghĩa, có thể dùng `200` nếu hợp đồng nghiệp vụ cho phép và client biết dữ liệu có thể cũ.
- **Service unavailable:** trả `503`/mã lỗi phù hợp với JSON ổn định để client hiểu yêu cầu chưa được xử lý.

Không phải mọi fallback đều là thành công. Trả 200 cho mọi outage có thể làm hỏng SLO monitoring, che lỗi upstream và khiến client ra quyết định sai. Fallback service phải xác định status theo hợp đồng API.

## 10. Fallback service nên xử lý headers thế nào?

Một controller Spring WebFlux minh họa (ứng dụng **fallback bên ngoài**, không phải code đặt vào Gateway):

~~~java
package example.fallback;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class CatalogFallbackController {

    @GetMapping("/fallback")
    public Mono<ResponseEntity<Map<String, String>>> fallback(
        @RequestHeader(value = "Execution-Exception-Type", required = false)
        String executionType) {

        // Chỉ phân loại để đo lường nội bộ khi caller đã được tin cậy.
        // Không đưa raw exception class/message vào response cho client.
        String safeCode = "CATALOG_TEMPORARILY_UNAVAILABLE";

        return Mono.just(ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .body(Map.of(
                "code", safeCode,
                "message", "Catalog is temporarily unavailable"
            )));
    }
}
~~~

Controller cố ý **không echo `executionType`**. Nó cũng không sử dụng exception class làm quyết định phân quyền hoặc route. Nếu cần metrics theo nhóm lỗi, chỉ phân loại sau khi xác minh caller và sau khi kiểm tra dữ liệu header, với **bounded cardinality** (tập nhãn hữu hạn). Không dùng nguyên tên class/message làm metric label hay log key dễ phát sinh cardinality lớn và rò rỉ thông tin.

Với mô hình production, endpoint fallback thường cần:

- Nhận một tập method và path **đã công bố**; không tự trả thành công cho mọi method nếu chưa xử lý đúng semantics.
- Trả content type, status và JSON body nhất quán với API contract.
- Hạn chế quyền đọc dữ liệu và khả năng truy cập mạng; fallback nên nhẹ hơn downstream chính.
- Có timeout, health check và monitoring độc lập, để fallback không trở thành điểm lỗi chung mới.
- Có cơ chế chống lặp vô hạn: **fallback route không tiếp tục gọi vào chính route catalog lỗi** hoặc forward ngược tới `/fallback`.

## 11. Cấu hình CircuitBreaker: lỗi nào thực sự kích hoạt fallback?

`FallbackHeaders` chỉ hữu ích nếu **CircuitBreaker đã kích hoạt nhánh fallback và có metadata lỗi**. Do đó phải hiểu lỗi nào được tính là thất bại.

Một cấu hình minh họa có thể chỉ định những HTTP status cần xem là lỗi của CircuitBreaker:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-main
          uri: http://localhost:9090
          predicates:
            - Path=/api/catalog/**
          filters:
            - name: CircuitBreaker
              args:
                name: catalogBreaker
                fallbackUri: forward:/fallback
                statusCodes:
                  - 500
                  - 502
                  - 503
~~~

**Điểm quan trọng:** Một response HTTP `500` từ backend **không nhất thiết tự tạo exception/fallback** nếu bộ lọc và phiên bản không được cấu hình coi status đó là lỗi. Thuộc tính `statusCodes` giúp xác định những mã HTTP sẽ được xử lý là thất bại theo contract của factory ở phiên bản tương ứng.

Không nên đưa `401`/`403` vào danh sách chỉ để “không lộ lỗi”: chúng thường biểu thị vấn đề xác thực/phân quyền và phải trả về client đúng nghĩa. Tương tự, `404` có thể là lỗi tài nguyên không tồn tại hoàn toàn hợp lệ, không phải dấu hiệu backend hỏng.

### Đừng đồng nhất exception type với HTTP status

| Nguồn sự cố | Điều cần xác minh | Metadata FallbackHeaders có thể thấy |
|---|---|---|
| Kết nối upstream bị từ chối | Routing call có phát exception không? | Class/message của exception thực thi |
| Timeout | Timeout do WebClient/Netty/TimeLimiter hay tầng khác tạo? | Có thể là exception timeout hoặc wrapper |
| Circuit đang OPEN | Request có bị breaker chặn và vào fallback không? | Có thể là exception dạng “call not permitted” |
| Backend trả 503 | Có `statusCodes: 503` hoặc policy tương ứng không? | Phụ thuộc cách factory chuyển status thành lỗi |
| Backend trả 404 | Có coi 404 là lỗi không? | Thường **không nên** tự kích hoạt fallback |
| Security chặn bằng 401/403 trước routing | Request có đến CircuitBreaker GatewayFilter không? | Thường **không có** metadata do circuit breaker route sinh |
| Rate limiter trả 429 | Limiter chặn trước hay sau breaker theo filter order? | Không mặc định là upstream failure |

**Fallback không nên che lỗi bảo mật.** Một HTTP 401 do Gateway security từ chối trước route sẽ không chạy CircuitBreaker filter của route; đó là hành vi cần được giữ trong thiết kế.

### Resilience4j và tên instance

Khi dùng Spring Cloud CircuitBreaker với một implementation như Resilience4j, tên `catalogBreaker` được dùng để liên kết với cấu hình instance theo release train phù hợp.

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      catalogBreaker:
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
~~~

Đây là **ví dụ tham số circuit breaker**, không đủ để hoạt động độc lập khi thiếu starter CircuitBreaker reactive và cấu hình thời gian chờ. Trong Gateway Server WebFlux thường cần integration hỗ trợ Reactor, chẳng hạn starter Resilience4j tương ứng với bản Spring Cloud CircuitBreaker. Timeout, TimeLimiter và trạng thái OPEN/HALF_OPEN cần được thử thực tế; không dùng các ngưỡng minh họa như mặc định production.

## 12. Tương tác với Retry, Timeout và LoadBalancer

Một request qua Gateway có thể đi qua cả `Retry`, `CircuitBreaker` và `lb://catalog-service`. Thứ tự của các filter quyết định CircuitBreaker nhìn thấy **một lỗi sau nhiều lần thử** hay từng attempt trong một chuỗi retry.

Ví dụ ý định:

~~~text
Client request
   -> Authentication / Rate limit
   -> CircuitBreaker + Retry theo một thứ tự được kiểm chứng
   -> LoadBalancer chọn catalog instance
   -> Downstream attempts
   -> Nếu thất bại theo policy: forward:/fallback
   -> FallbackHeaders trên route fallback
~~~

Không tự giả định rằng chỉ cần đặt hai dòng YAML theo một thứ tự là mọi implementation sẽ thống nhất semantics trong các trường hợp exception, response status, route ordering, global filters và retry callback. Hãy quan sát execution order và số outbound attempts.

| Tính năng | Rủi ro nếu phối hợp sai | Cần kiểm tra |
|---|---|---|
| `Retry` | Một request client tạo nhiều request tới upstream lỗi | Budget, max retries, backoff, idempotency |
| CircuitBreaker | Mở mạch quá sớm hoặc không phản ánh lỗi đúng | Sliding window, threshold, recorded exceptions/status |
| Timeout/TimeLimiter | Giữ request quá lâu, fallback cũng chậm | Timeout cho upstream và fallback, chặn tài nguyên |
| `lb://` | Một instance lỗi làm tỷ lệ lỗi tăng | Health, discovery state, cân bằng tải và lỗi theo instance |
| Rate limiting | Request vào fallback có thể bị tính hai lần nếu route cũng có limiter | Thiết kế quota trên route chính và route fallback |
| Cache/degraded data | Client nhận dữ liệu cũ như thể dữ liệu mới | Status/metadata minh bạch theo hợp đồng |
| Streaming/SSE | Lỗi xảy ra sau khi response đã commit | Không hứa fallback có thể thay response đã gửi một phần |

**SSE và response đã commit:** Một stream có thể đã gửi headers và vài chunk cho client trước khi downstream lỗi. Khi đó không thể luôn chuyển thành một response fallback mới với status/body hoàn toàn khác. Thiết kế fallback phải xét giới hạn của HTTP response lifecycle.

## 13. Bảo mật fallback route và trust boundary

Thông thường đường đi có ít nhất ba vùng tin cậy:

~~~mermaid
flowchart LR
    C["Public client / browser"] --> E["Ingress / Gateway"]
    E -->|TLS, authenticated route| U["catalog-service"]
    E -->|Internal fallback route| F["fallback-service"]
    E --> LOG["Logs / tracing"]
    F --> LOG
    X["Client tự đặt error headers"] -.-> E
~~~

**Phải xác định ai được quyền gửi request đến `/fallback`.** Nếu route này được công bố ra Internet, một kẻ tấn công có thể gọi trực tiếp hoặc kiểm thử những header được biết tên. Nếu backend fallback sử dụng header exception để quyết định dữ liệu trả ra, nó có thể bị điều khiển bởi người gọi không được tin cậy.

Biện pháp vận hành:

1. **Chặn hoặc hạn chế direct access** tới path fallback ở lớp ingress/security/network phù hợp, nhưng bảo đảm internal forward vẫn hoạt động theo lifecycle thực tế.
2. **Sanitize request headers** để loại các header do client tự gắn trước khi Gateway tạo metadata tin cậy.
3. **Không chuyển tiếp Authorization, Cookie, API key** tới fallback service nếu nó không cần; nếu cần service identity, dùng mTLS/service token phù hợp thay vì credentials của end-user.
4. **Bảo vệ Gateway → fallback bằng TLS/mTLS** hoặc network isolation và kiểm tra certificate trust nếu chính sách yêu cầu.
5. **Không tin raw exception class/message** làm căn cứ cấp quyền; thông tin ấy chỉ mang tính chẩn đoán.
6. **Không echo raw error headers** vào response, browser devtools, logs công khai hoặc metrics labels.
7. **Giới hạn kích thước/tần suất** metadata, có timeout và quan sát fallback response. Exception messages tùy library có thể dài/khó kiểm soát.
8. **Tách lỗi backend khỏi lỗi xác thực/ủy quyền.** Không kích hoạt fallback trả 200 cho một người dùng vốn không được phép truy cập.
9. **Rà soát proxy/filter order** để header trusted do Gateway đặt không bị thay lại bởi một layer phía sau.
10. **Đảm bảo fallback service không bị gọi vòng lặp** hoặc trở thành cổng bypass tới dữ liệu quan trọng.

### Lưu ý khi truyền correlation ID

Một correlation ID đã được kiểm tra/khởi tạo tại Gateway là thông tin hữu ích cho fallback service. Tuy nhiên, **đừng dùng session ID hay access token làm correlation ID**. Mã phải có định dạng/độ dài hợp lý, không chứa PII, có quyền tra cứu logs phù hợp và không bị client chi phối vô hạn.

Có thể gắn một header dạng `X-Request-Id` được quản lý bởi tracing/Gateway filter riêng. `FallbackHeaders` **không tự sinh correlation ID** và không thay thế trace propagation chuẩn như `traceparent`.

## 14. Thực hành: fallback service nhận header nào?

### Chuẩn bị ba thành phần

- **Gateway:** `http://localhost:8080` với hai route `catalog-main` và `catalog-fallback` ở phần 4.
- **Catalog backend:** `http://localhost:9090`, có endpoint `GET /api/catalog/42` khi hoạt động.
- **Fallback backend:** `http://localhost:9095`, endpoint `GET /fallback`, có khả năng log **tên header và trạng thái hiện diện**, không log/raw echo các giá trị nhạy cảm.

Trong lab để minh họa thông tin lỗi, có thể dùng một mock fallback HTTP server trả JSON an toàn; nếu không có mock server, phải tạo backend thực tế trước khi test. Hãy chạy môi trường cô lập, không dùng token thật.

### Bước 1 — Happy path không kích hoạt fallback

Khởi động cả hai backend, sau đó gửi:

~~~bash
curl -i "http://localhost:8080/api/catalog/42"
~~~

Kỳ vọng request đi tới catalog backend và nhận response bình thường. Fallback service **không được gọi** nếu catalog phản hồi thành công theo chính sách CircuitBreaker.

### Bước 2 — Catalog không khả dụng

Tắt riêng catalog backend `localhost:9090`, để fallback backend hoạt động:

~~~bash
curl -i "http://localhost:8080/api/catalog/42"
~~~

Nếu CircuitBreaker và forward route được cấu hình đúng, request sẽ đi qua `forward:/fallback`, match route `catalog-fallback` và được gửi đến fallback backend.

Fallback backend nên ghi nhận an toàn:

~~~text
method: GET
path: /fallback
has Execution-Exception-Type: true
has Execution-Exception-Message: true/false (tùy lỗi)
has Root-Cause-Exception-Type: true/false
has Root-Cause-Exception-Message: true/false

response to caller:
  HTTP 503
  {"code":"CATALOG_TEMPORARILY_UNAVAILABLE", ...}
~~~

**Không kiểm tra bằng cách mặc định phải có đủ bốn header**, bởi exception/root cause tùy tình huống và phiên bản. Quan sát thông tin thực tế, xác định lý do fallback và bảo đảm không có raw exception trong response cuối.

### Bước 3 — Trường hợp HTTP statusCodes

Cho catalog backend chạy lại nhưng trả HTTP `503`. Với cấu hình `CircuitBreaker.statusCodes` ở phần 11 (nếu phiên bản hỗ trợ), Gateway có thể coi 503 là lỗi được xử lý qua fallback. Sau đó bỏ `statusCodes` và so sánh, để hiểu sự khác nhau giữa **HTTP error response** và **exception** trong cơ chế CircuitBreaker.

Đừng dùng `404` để mặc định giả lập outage, vì tài nguyên không tồn tại có thể là response nghiệp vụ hợp lệ.

### Bước 4 — Trực tiếp gọi route fallback và thử spoofing

Trong môi trường test **đã được kiểm soát**:

~~~bash
curl -i "http://localhost:8080/fallback" \
  -H "Execution-Exception-Type: forged-client-value" \
  -H "Execution-Exception-Message: forged-message"
~~~

Trước khi đưa production, cần đảm bảo:

- Request client trực tiếp không được coi là fallback nội bộ có danh tính hợp lệ.
- Backend không tin `forged-client-value` để mở quyền hoặc đưa dữ liệu nhạy cảm.
- Các header đầu vào trùng tên được bỏ đúng theo chính sách.
- Không phải request nào có `Path=/fallback` cũng tự có exception do CircuitBreaker tạo.

Nếu bạn chọn chặn direct access ở security/ingress, phép thử có thể nhận **403/404** theo policy. Nếu direct access vẫn nhận 200 từ fallback backend, đây là dấu hiệu cần đánh giá xem endpoint bị public ngoài ý định hay không.

### Bước 5 — Kiểm tra route fallback không nhận secret

Thực hiện trong môi trường test với **giá trị giả**, không dùng credentials thật:

~~~bash
curl -i "http://localhost:8080/api/catalog/42" \
  -H "Authorization: Bearer demo-only-token" \
  -H "Cookie: SESSION=demo-only-cookie"
~~~

Nếu route fallback áp dụng chính sách bỏ `Authorization` và `Cookie`, backend phải không thấy chúng khi request tới `/fallback`. Nếu vẫn nhận, kiểm tra route/filter order, forward behavior và các thành phần proxy khác. Không coi một lần kiểm thử là đủ trong hệ thống có nhiều Gateway instances.

### Ma trận kiểm thử

| Case | CircuitBreaker fallback? | Header lỗi ở fallback service | HTTP response cuối |
|---|---|---|---|
| Catalog trả 200 | Không | Không có request fallback | 200 hoặc status catalog |
| Catalog kết nối thất bại | Có nếu policy/route đúng | Thông tin exception tùy lỗi | Theo fallback backend, ví dụ 503 |
| Catalog trả 503, `statusCodes` có 503 | Có thể có | Metadata tùy cách factory xử lý status | Theo fallback backend |
| Catalog trả 503, không đánh dấu lỗi status | Không nhất thiết | Có thể không gọi fallback | Có thể trả 503 trực tiếp |
| Client gọi thẳng `/fallback` | Không do catalog CircuitBreaker | Không có metadata từ CB; header client có thể giả | Nên bị chặn hoặc không được tin |
| JWT không hợp lệ | Spring Security có thể chặn trước route | Không có route fallback | Thường 401 |
| Request vượt rate limit | Có thể chặn trước CircuitBreaker | Không nhất thiết có fallback | Thường 429 |

## 15. Chẩn đoán sự cố hay gặp

| Triệu chứng | Nơi cần kiểm tra | Cách xử lý |
|---|---|---|
| Có lỗi catalog nhưng fallback không chạy | CircuitBreaker chưa gắn route, không coi status là lỗi | Xác minh factory, `statusCodes`, exception và route predicates |
| Lỗi "invalid fallbackUri" hoặc không forward như mong đợi | `fallbackUri` không đúng scheme/đường dẫn | Dùng `forward:/fallback` và route fallback riêng |
| Forward tới /fallback nhưng 404 | Không có handler/route match path fallback | Kiểm tra Path predicate, handler mapping, route order |
| Fallback service không được gọi | URI ngoài sai, DNS, load balancer, network hoặc TLS lỗi | Test route fallback trực tiếp trong lab và kiểm tra outbound routing |
| Không có header exception | `FallbackHeaders` thiếu trên route fallback, không có exchange exception attribute | Xem route runtime, đúng flow CB, thông tin lỗi thực tế |
| Có type nhưng thiếu root cause | Exception không có chuỗi cause, implementation khác | Xử lý optional headers trong fallback service |
| Raw exception xuất hiện trong response client | Fallback backend echo header/message hoặc error serializer lộ detail | Trả generic code/message, redact logs và bỏ unsafe headers |
| Header lỗi bị trùng hoặc giả mạo | Client tự gửi header, có filter thêm nhiều lần | Xóa tên header đầu vào trước khi FallbackHeaders; kiểm tra order |
| Fallback trả 200 làm dashboard “xanh” | SLO đo HTTP status cuối mà không có fallback metric | Phân biệt degraded success và upstream failure |
| HTTP 401/403 biến thành fallback | Đánh dấu sai status codes hoặc xử lý exception bảo mật không đúng | Không coi auth errors là outage; rà soát chính sách |
| Fallback cũng chậm/lỗi | Backend dự phòng không khỏe, thiếu timeout/network isolation | Giới hạn thời gian, health check và cơ chế lỗi cuối |
| Chỉ lỗi trên một Gateway node | Cấu hình route/circuit breaker instance khác | Kiểm tra rollout, caches, config, registry, CB metrics |
| Request tạo vòng fallback | Fallback route lại có CircuitBreaker forward cùng path | Loại recursion, tách route/handler rõ ràng |

### Quy trình kiểm tra 6 điểm

1. **Request có match route chính** và đi qua CircuitBreaker filter không?
2. **Nguồn lỗi nào** kích hoạt CircuitBreaker: exception, status code, timeout hay circuit OPEN?
3. **`forward:/fallback` có tới handler/route fallback** đúng không?
4. **`FallbackHeaders` có chạy trên route fallback** và tìm được metadata exception không?
5. **Request đến fallback service** có method/path/headers đúng và không rò credentials không?
6. **Response cuối** có status/body an toàn; observability có ghi lại fallback count, nguyên nhân và độ trễ phù hợp không?

Hãy kết hợp route ID, circuit breaker name, outcome, correlation ID, latency và distributed tracing được cấu hình đúng; **không đặt exception message thô làm metric label**, không ghi Bearer token/cookie/session ID.

## 16. Checklist trước khi đưa vào production

- [ ] Tôi phân biệt `CircuitBreaker`, `fallbackUri: forward:/fallback` và `FallbackHeaders`.
- [ ] Tôi hiểu `FallbackHeaders` thêm **request headers gửi tới fallback service**, không tự thêm response headers cho client.
- [ ] Tôi biết bốn loại header: execution type/message và root-cause type/message, cùng trường hợp chúng vắng mặt.
- [ ] Tôi đã xác minh tên/header args theo đúng phiên bản Gateway Server WebFlux.
- [ ] Tôi không coi việc đổi tên header là che giấu nội dung exception.
- [ ] Tôi chỉ dùng factory để chuyển thông tin lỗi chi tiết khi fallback service thực sự là bên nhận **được tin cậy và được phép**.
- [ ] Tôi đã xác định rõ danh sách thông tin lỗi có thể chuyển tiếp; ưu tiên mã lỗi chuẩn hóa và correlation ID.
- [ ] Tôi không echo raw exception, stack trace, hostname, SQL detail, credential hoặc PII vào response.
- [ ] Tôi loại các header do client tự gửi có thể mạo danh metadata của Gateway.
- [ ] Tôi đã khóa truy cập direct fallback route hoặc đảm bảo fallback backend không tin các header client tự khai.
- [ ] Tôi không chuyển Authorization/Cookie đến fallback nếu không cần và dùng service-to-service authentication nếu cần.
- [ ] Tôi có TLS/mTLS, network isolation và chính sách certificate trust cho chặng Gateway → fallback.
- [ ] Tôi đã kiểm thử lỗi kết nối, timeout, circuit OPEN và `statusCodes` theo policy thực tế.
- [ ] Tôi không biến 401/403/404 nghiệp vụ thành outage fallback nếu không được thiết kế rõ.
- [ ] Tôi hiểu retry/circuit breaker order, số outbound attempts và tác động của rate limiting.
- [ ] Tôi không để fallback route tạo vòng lặp hoặc dùng dữ liệu dự phòng sai hợp đồng.
- [ ] Tôi đã kiểm tra response đã commit/streaming nếu ứng dụng dùng SSE hoặc tải file lớn.
- [ ] Tôi theo dõi fallback count, error rate, latency, circuit state và backend availability trên nhiều Gateway nodes.
- [ ] Tôi đã thực hiện end-to-end test qua ingress/proxy, không chỉ gọi trực tiếp localhost Gateway.
- [ ] Tôi đã rà soát riêng việc dữ liệu debug có bị lộ qua header, log, traces và metrics hay không.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — tìm mục **FallbackHeaders GatewayFilter Factory**, **CircuitBreaker GatewayFilter Factory**, cấu hình fallback và định tuyến **Server WebFlux** đúng phiên bản.
- [Spring Cloud CircuitBreaker Reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/) — circuit breaker integration, Resilience4j và tên instance.
- [Spring Framework — ServerWebExchange](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html) — exchange attributes, request mutation và reactive HTTP lifecycle.
- [Spring Framework — HttpHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/HttpHeaders.html) — HTTP headers và danh sách nhiều giá trị.
- [Resilience4j Documentation](https://resilience4j.readme.io/docs/circuitbreaker) — các trạng thái CLOSED/OPEN/HALF_OPEN, tỷ lệ lỗi và cấu hình breaker.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) — semantics của status và HTTP fields.

**Ghi nhớ:** `FallbackHeaders` là cầu nối **exception metadata của CircuitBreaker** sang **request headers của ứng dụng fallback bên ngoài**, thường qua sơ đồ **CircuitBreaker → `forward:/fallback` → route fallback → FallbackHeaders → fallback service**. Nó hỗ trợ chẩn đoán nhưng **không tự bảo vệ dữ liệu**: class names và đặc biệt raw exception messages chỉ nên chuyển cho bên nhận đã được phép. Trong hợp đồng public, ưu tiên **status/mã lỗi ổn định, thông điệp tổng quát và correlation ID**, đồng thời giữ lỗi kỹ thuật chi tiết trong hệ thống observability được kiểm soát.
