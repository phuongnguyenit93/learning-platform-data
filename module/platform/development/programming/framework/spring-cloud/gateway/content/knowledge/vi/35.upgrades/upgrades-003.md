# Đối chiếu thay đổi mặc định của predicate và filter khi nâng cấp Spring Cloud Gateway

Khi nâng cấp Spring Cloud Gateway, một route vẫn có thể khởi động bình thường nhưng chọn backend khác, không còn khớp một URL cũ hoặc xử lý header theo cách khác. Nguyên nhân thường nằm ở hành vi mặc định của predicate, filter, bộ phân tích đường dẫn hoặc lớp HTTP nền tảng đi kèm phiên bản mới. Vì vậy, cần đối chiếu hành vi thực tế của phiên bản đang chạy với phiên bản đích trước khi triển khai.

Bài này hướng dẫn cách kiểm kê và so sánh các mặc định có ảnh hưởng đến route predicate và filter chain. Trọng tâm là Gateway Server WebFlux. Nếu ứng dụng chuyển giữa Gateway Server WebFlux và Gateway Server MVC, hãy xem đó là một lần chuyển đổi kiến trúc riêng: không giả định hai server có cùng tập predicate, filter, cơ chế thực thi hoặc giá trị mặc định.

## 1. Xác định đúng hai phiên bản cần so sánh

Không suy ra phiên bản Spring Cloud Gateway chỉ từ phiên bản Spring Boot. Gateway được quản lý theo Spring Cloud release train; release train lại có ma trận tương thích với Spring Boot và Spring Framework. Trước khi so sánh, ghi lại chính xác:

- Phiên bản Spring Boot và Spring Framework.
- Phiên bản Spring Cloud release train được import qua BOM.
- Phiên bản artifact Gateway thực tế được resolve, chẳng hạn `spring-cloud-starter-gateway` hoặc starter tương ứng của kiến trúc đang dùng.
- Các dependency override, dependency trực tiếp và cấu hình profile có thể thay đổi hành vi.

Ví dụ kiểm tra dependency bằng Gradle:

```bash
./gradlew dependencyInsight \
  --dependency spring-cloud-gateway-server \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-web \
  --configuration runtimeClasspath
```

Với Maven, dùng `mvn dependency:tree` và lọc các artifact Gateway, Spring WebFlux, Spring Framework cùng Reactor Netty. Lưu lại kết quả của cả bản hiện tại và bản đích. Nếu dependency được quản lý qua BOM, kiểm tra BOM đang được import thay vì chỉ sửa version của một starter riêng lẻ.

Một số dải phiên bản thường gặp để định hướng việc kiểm tra:

| Nhánh nền tảng | Điều cần lưu ý khi đối chiếu |
|---|---|
| Gateway 3.x và nền Spring Boot 2 / Framework 5 | Kiểm tra khác biệt khi chuyển sang nền Boot 3 / Framework 6, đặc biệt các thay đổi nền tảng và namespace Jakarta |
| Gateway 4.x và nền Spring Boot 3 / Framework 6 | Đối chiếu minor release của Gateway, release train và các thay đổi của Spring Framework 6.x |
| Các nhánh Gateway mới hơn | Chọn BOM và ma trận tương thích chính thức tương ứng; không ghép độc lập version Gateway, Boot và Framework |

Bảng này chỉ định hướng nhóm thay đổi cần kiểm tra, không thay thế ma trận tương thích của Spring Cloud. Không có một danh sách mặc định duy nhất áp dụng cho mọi lần nâng cấp: kết quả phụ thuộc cặp phiên bản nguồn/đích và cấu hình ứng dụng.

## 2. Hiểu các lớp tạo nên hành vi mặc định

Một route đang chạy không chỉ chịu ảnh hưởng từ những dòng YAML viết ngay trong route. Khi so sánh, hãy kiểm kê cả các lớp sau:

1. **Route definition:** `id`, `uri`, `order`, predicates và filters khai báo trực tiếp.
2. **Default filters:** các filter cấu hình tại `spring.cloud.gateway.default-filters`, được áp dụng cho nhiều route.
3. **Global filters:** các `GlobalFilter` do Gateway tự cấu hình hoặc do ứng dụng cung cấp; chúng có thể áp dụng cho tất cả route.
4. **HTTP headers filters:** các `HttpHeadersFilter` xử lý header trước khi Gateway gửi request tới upstream, ví dụ loại bỏ hop-by-hop header hoặc tạo forwarded header.
5. **Cấu hình nền tảng:** thuộc tính của Spring Boot, Spring Framework, WebFlux, Reactor Netty, load balancer, security và thư viện khác.
6. **Nguồn route động:** Java `RouteLocator`, `RouteDefinitionLocator`, discovery locator hoặc cấu hình được nạp từ Config Server và môi trường triển khai.

Khi nhiều nguồn cùng khai báo một thuộc tính, giá trị hiệu lực phụ thuộc cơ chế binding và thứ tự ưu tiên cấu hình của Spring Boot. Hãy xem cả `application.yml`, file theo profile, biến môi trường, tham số dòng lệnh và cấu hình Java. Chỉ đọc YAML mặc định trong repository có thể bỏ sót cấu hình đang thực sự chạy ở production.

Phân biệt ba khái niệm:

- **Giá trị mặc định của factory:** giá trị mà một predicate/filter factory sử dụng nếu tham số không được truyền.
- **Giá trị cấu hình hiệu lực:** giá trị sau khi Spring bind property, áp dụng profile và override.
- **Hành vi quan sát được:** kết quả cuối cùng sau khi kết hợp route, filter, global filter, HTTP client và proxy bên ngoài.

Đối chiếu cả ba lớp sẽ giúp tránh nhầm một thay đổi do cấu hình môi trường với một thay đổi mặc định của thư viện.

## 3. Đối chiếu route predicate

Các predicate được kết hợp theo điều kiện AND trong cùng route. Một route chỉ được chọn khi tất cả predicate của nó đều khớp. Khi nhiều route có thể khớp cùng request, thứ tự route (`order`) và các điều kiện cụ thể quyết định route nào được chọn. Vì vậy, một thay đổi nhỏ trong cách so khớp có thể khiến request rơi vào route khác dù cấu hình route cũ vẫn tồn tại.

### Path: dấu `/` cuối và bộ phân tích pattern

`Path` là predicate cần ưu tiên kiểm thử khi nâng cấp. Hành vi khớp dấu gạch chéo cuối có liên quan đến cả phiên bản Gateway và bộ phân tích pattern của Spring Framework. Trong Spring Framework 6, `PathPatternParser` không còn mặc định khớp optional trailing separator như trước. Tuy nhiên, không nên suy ra toàn bộ hành vi của Gateway chỉ từ thay đổi nền tảng này: từng phiên bản Gateway có cấu hình riêng cho Path predicate, trong đó có thể có tham số `matchTrailingSlash`.

Giả sử route khai báo:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: order-detail
          uri: lb://order-service
          predicates:
            - Path=/api/orders/{id}
```

Hãy kiểm tra riêng các request sau ở cả hai phiên bản:

| Request | Điều cần xác nhận |
|---|---|
| `/api/orders/42` | Đường dẫn chuẩn có khớp không |
| `/api/orders/42/` | Dấu `/` cuối có còn được chấp nhận không |
| `/api/orders/42/items` | Pattern có vô tình khớp phần path sâu hơn không |
| `/API/orders/42` | Quy tắc phân biệt chữ hoa/chữ thường có thay đổi không |
| `/api/orders/a%2Fb` | Cách xử lý encoded slash có phù hợp với backend và proxy không |

Không dựa vào việc một request trả `404` để kết luận duy nhất rằng Path predicate không khớp. Request có thể đã khớp route nhưng upstream trả `404`; hãy kiểm tra route ID, log định tuyến và path sau filter.

Nếu cả hai dạng có dấu và không có dấu `/` cuối đều là API hợp lệ, khai báo rõ cả hai pattern theo cú pháp của phiên bản Gateway đang dùng, hoặc chuẩn hóa URL tại một lớp được kiểm soát. Ví dụ cấu hình nhiều pattern trong cùng một Path predicate:

```yaml
predicates:
  - Path=/api/orders/{id},/api/orders/{id}/
```

Không khai báo hai dòng `Path` riêng trong cùng route để biểu diễn hai lựa chọn thay thế: các predicate riêng trong route được kết hợp với nhau, khiến request phải thỏa mãn cả hai. Sau khi thay đổi, kiểm thử URL có và không có dấu `/` cuối.

### Các predicate còn lại cần có ca kiểm thử đại diện

| Predicate | Mặc định hoặc hành vi cần đối chiếu | Ca kiểm thử nên có |
|---|---|---|
| `Host` | Cách so khớp hostname pattern và host lấy từ request | Host chính, subdomain, host viết hoa/thường, request không có host hợp lệ |
| `Method` | Tập method được chấp nhận; method không khai báo có bị route khác bắt không | GET, HEAD, POST, OPTIONS và method không hỗ trợ |
| `Header` | Tên header, biểu thức regex và cách xử lý header vắng mặt | Header đúng, sai chữ hoa/thường, thiếu header, giá trị chứa ký tự đặc biệt |
| `Query` | Phân biệt query parameter có mặt với giá trị khớp regex | Không có tham số, tham số rỗng, lặp tham số, giá trị Unicode hoặc đã encode |
| `Cookie` | Cách đọc cookie và so khớp regex | Cookie thiếu, nhiều cookie, giá trị có ký tự cần escape |
| `RemoteAddr` | Địa chỉ peer thực tế hay địa chỉ đã được proxy tin cậy cung cấp | Gọi trực tiếp, qua ingress, qua nhiều proxy và header forwarding giả mạo |
| `Between` | Biên thời gian, timezone và thời điểm chuyển ngày/giờ | Trước biên, đúng biên, sau biên, timezone khác UTC và DST nếu áp dụng |
| `Before` / `After` | Biên thời gian có tính bao gồm hay không theo phiên bản | Request ngay trước, đúng thời điểm và ngay sau mốc |
| `Weight` | Nhóm, trọng số, cách chọn route và ảnh hưởng khi route thay đổi | Nhiều route cùng group, tỷ lệ phân phối khi tăng tải và khi một route bị gỡ |
| `XForwardedRemoteAddr` | Header được dùng để xác định địa chỉ client và độ tin cậy proxy | Chuỗi nhiều địa chỉ, proxy không tin cậy và header do client tự gửi |

Đặc biệt với `RemoteAddr`, không tin tưởng mọi giá trị `X-Forwarded-For` do client gửi trực tiếp. Nếu Gateway đứng sau proxy, chỉ sử dụng resolver và số lượng proxy tin cậy phù hợp với topology thực tế. Cấu hình sai có thể làm predicate chọn route theo địa chỉ giả mạo, ảnh hưởng đến ACL, rate limit hoặc phân vùng tenant.

Với `Between`, `Before` và `After`, dùng thời gian có timezone rõ ràng và kiểm thử tại đúng biên. Một route hoạt động ở môi trường UTC có thể chọn khác ở môi trường dùng timezone địa phương nếu cấu hình mốc thời gian không nhất quán.

## 4. Đối chiếu filter chain

Filter có thể thay đổi request trước khi gọi upstream hoặc thay đổi response trước khi trả về client. Khi nâng cấp, cần xác minh cả giá trị tham số, thứ tự thực thi và tác động lên body/header.

### Thứ tự filter và phạm vi áp dụng

Các filter khai báo trong route, `default-filters` và `GlobalFilter` có thể cùng tham gia xử lý. Gateway kết hợp các filter tương thích rồi sắp xếp theo `Ordered`. Phần pre-filter chạy theo thứ tự tăng dần; phần post-filter được thực hiện khi chain quay về, thường theo chiều ngược lại. Không suy luận thứ tự chỉ từ vị trí dòng YAML nếu filter có `order` riêng.

Ví dụ một cấu hình default filter:

```yaml
spring:
  cloud:
    gateway:
      default-filters:
        - AddRequestHeader=X-Gateway, edge
        - RemoveRequestHeader=X-Internal-Debug
```

Các filter trên được áp dụng rộng cho route thuộc cấu hình đó. Nếu một route cần giữ header bị loại bỏ hoặc cần giá trị header khác, hãy kiểm tra thứ tự và phạm vi filter để tránh xung đột. Không giả định filter khai báo trong route luôn chạy trước hoặc sau mọi global filter.

Với custom filter, ghi rõ `getOrder()` hoặc triển khai `Ordered` khi thứ tự là một phần của hợp đồng. Kiểm thử thứ tự bằng log có route ID và correlation ID, không chỉ dựa vào tên bean.

### Các filter có tham số mặc định đáng chú ý

Một số giá trị mặc định thường ảnh hưởng trực tiếp đến hành vi production:

| Filter | Giá trị mặc định thường gặp trong Gateway Server WebFlux | Điều cần kiểm tra khi nâng cấp |
|---|---|---|
| `Retry` | Số lần retry mặc định là 3; method mặc định là GET; series mặc định là 5XX; danh sách exception mặc định bao gồm lỗi I/O và timeout; backoff không tự bật | Kiểm tra lại retry count, method, status series, exception, backoff, jitter và body có thể replay hay không |
| `RequestRateLimiter` với Redis limiter | `replenishRate`, `burstCapacity` và `requestedTokens` thường có mặc định 1 nếu không khai báo | Xác nhận key resolver, đơn vị token, Redis script, response khi bị giới hạn và giá trị hiệu lực theo route |
| `DedupeResponseHeader` | Chiến lược mặc định thường là `RETAIN_FIRST` | Kiểm tra header trùng do upstream và Gateway cùng thêm, nhất là CORS header |
| `StripPrefix` | Số segment cần bỏ phải được cấu hình trong filter; không nên dựa vào một giá trị ngầm định cho route | Kiểm tra path đầu vào, path chuyển tiếp và trường hợp có dấu `/` cuối |
| `RewritePath` | Biểu thức regex và replacement do cấu hình cung cấp | Kiểm tra escaping YAML, capture group, encoded path và path backend nhận được |
| `CircuitBreaker` | Không tự tạo circuit breaker cho mọi route chỉ vì starter đã có mặt; route phải khai báo filter và cấu hình phù hợp | Kiểm tra tên circuit breaker, trạng thái mở/đóng, fallback và timeout của implementation |
| `SetPath`, `PrefixPath`, `AddRequestHeader`, `SetRequestHeader`, `RemoveRequestHeader` | Giá trị cần thay đổi được nêu trong tham số filter | Kiểm tra header/path trước và sau filter, thứ tự giữa các filter và tác động đến chữ ký request |

Các giá trị trong bảng là mốc kiểm tra phổ biến, không phải cam kết rằng mọi minor release, starter hoặc implementation đều giữ nguyên. Hãy xác nhận trực tiếp với metadata và mã nguồn của artifact Gateway đã resolve ở cả hai phiên bản. Đặc biệt, `RequestRateLimiter` có thể dùng limiter khác Redis; khi đó các giá trị mặc định và cách tính token phụ thuộc implementation được cấu hình.

### Retry: thay đổi nhỏ có thể tạo tải lớn

Không nên xem retry là một cơ chế tăng độ tin cậy miễn phí. Ví dụ một request GET lỗi 5XX có thể được thử lại theo cấu hình mặc định. Khi nâng cấp, nếu số lần thử, tập method hoặc tập exception thay đổi, lưu lượng upstream trong thời điểm lỗi có thể tăng đáng kể.

Ví dụ cấu hình tường minh để không phụ thuộc ngầm vào giá trị mặc định:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-read
          uri: lb://catalog-service
          predicates:
            - Path=/catalog/**
          filters:
            - name: Retry
              args:
                retries: 2
                methods: GET
                series: SERVER_ERROR
                exceptions:
                  - java.io.IOException
                  - java.util.concurrent.TimeoutException
```

Đây là ví dụ giới hạn retry cho request GET và lỗi server. Với POST/PUT hoặc request có body, chỉ bật retry khi đã có idempotency key hoặc cơ chế bảo đảm không tạo giao dịch trùng. Nếu dùng backoff, tính tổng thời gian chờ và số lần thử sao cho không vượt deadline của client. Retry cũng cần được đánh giá cùng circuit breaker để tránh tạo thêm tải khi upstream đang suy giảm.

### RequestRateLimiter: kiểm tra key và đơn vị giới hạn

Giá trị rate limit chỉ có ý nghĩa khi key resolver trả về khóa đúng. Một key dùng chung cho mọi client có thể làm tất cả người dùng chia sẻ cùng một bucket; key dựa trên IP có thể sai nếu Gateway không xử lý forwarded header đúng cách.

Ví dụ cấu hình Redis limiter có giá trị tường minh:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: public-api
          uri: lb://public-api
          predicates:
            - Path=/public/**
          filters:
            - name: RequestRateLimiter
              args:
                redis-rate-limiter.replenishRate: 20
                redis-rate-limiter.burstCapacity: 40
                redis-rate-limiter.requestedTokens: 1
```

Ví dụ trên chỉ minh họa các tham số của Redis limiter; ứng dụng vẫn cần cấu hình `KeyResolver` phù hợp và Redis hoạt động ổn định. Khi so sánh phiên bản, kiểm tra cả trường hợp không resolve được key, Redis timeout và phản hồi khi request bị từ chối. Không dùng IP từ header chưa được proxy tin cậy xác thực làm khóa giới hạn.

## 5. Đối chiếu header filters và header forwarding

Header là vùng dễ bị thay đổi ngoài dự kiến vì Gateway có các filter ở nhiều tầng. Hãy kiểm tra tối thiểu:

- **Hop-by-hop headers:** Gateway có bộ lọc loại bỏ các header hop-by-hop trước khi gửi request tới upstream. Kiểm tra các header như `Connection`, `Keep-Alive`, `Proxy-Authenticate`, `Proxy-Authorization`, `TE`, `Trailer`, `Transfer-Encoding` và `Upgrade` trong đúng ngữ cảnh giao thức. WebSocket có cơ chế xử lý nâng cấp riêng; không tự loại bỏ hoặc tự chèn header handshake chỉ để làm request thường hoạt động.
- **Forwarded headers:** kiểm tra `Forwarded` và nhóm `X-Forwarded-*` được tạo, nối thêm hoặc giữ lại ra sao. Đối chiếu `for`, `host`, `port`, `proto` và `prefix` với topology proxy thực tế.
- **Header trùng:** kiểm tra CORS header, `Set-Cookie`, `Cache-Control`, `Vary` và các header do cả Gateway lẫn upstream cùng thêm. Không dùng một chiến lược dedupe chung cho mọi header; `Set-Cookie` có ngữ nghĩa nhiều giá trị và cần được xử lý cẩn thận.
- **Header nhạy cảm:** xác nhận token, cookie nội bộ và header định danh không bị chuyển tiếp sang service ngoài phạm vi tin cậy.
- **Case và encoding:** tên header không phân biệt chữ hoa/thường theo HTTP, nhưng code custom hoặc hệ thống downstream có thể xử lý sai. Kiểm thử giá trị có Unicode, dấu phẩy và nhiều giá trị header.

Nếu Gateway đứng sau ingress hoặc load balancer, chỉ chấp nhận forwarded header từ proxy đáng tin cậy. Nếu cho phép client gửi trực tiếp `X-Forwarded-For` hoặc `X-Forwarded-Proto` mà không làm sạch header ở biên tin cậy, ứng dụng có thể ghi log sai IP, tạo URL HTTPS giả hoặc vượt qua chính sách bảo mật dựa trên địa chỉ.

## 6. Tạo bảng so sánh mặc định cho phiên bản nguồn và đích

Không chỉ ghi “đã thay đổi” hoặc “không đổi”. Với mỗi predicate/filter đang dùng, lưu cả giá trị cấu hình, giá trị mặc định của artifact và kết quả request thực tế.

| Trường cần ghi | Ví dụ |
|---|---|
| Route ID | `order-detail` |
| Thành phần | `Path` predicate |
| Version nguồn / đích | Phiên bản artifact Gateway đã resolve |
| Giá trị cấu hình | `/api/orders/{id}` |
| Default nguồn / đích | `matchTrailingSlash` và parser behavior của từng version |
| Request kiểm thử | `/api/orders/42/` |
| Kết quả nguồn / đích | route ID được chọn, status và path upstream |
| Mức ảnh hưởng | tương thích, bảo mật, tải upstream hoặc quan sát |
| Cách xử lý | khai báo rõ pattern hoặc chuẩn hóa path |

Có thể quản lý bảng này trong pull request nâng cấp để reviewer thấy được route nào bị ảnh hưởng và vì sao phải thay đổi cấu hình.

### Ma trận kiểm thử tối thiểu

| Nhóm | Ca kiểm thử |
|---|---|
| Path predicate | path chuẩn, trailing slash, path sâu hơn, chữ hoa/thường, encoded path |
| Host / Header / Query / Cookie | giá trị khớp, không khớp, thiếu, lặp và ký tự đặc biệt |
| Method | GET, HEAD, POST, OPTIONS và method không được hỗ trợ |
| RemoteAddr / forwarded | gọi trực tiếp, qua từng proxy, nhiều địa chỉ và header giả mạo |
| Time predicate | trước biên, đúng biên, sau biên, timezone và DST nếu có |
| Route order / Weight | nhiều route cùng khớp, route ưu tiên, phân phối tải và route bị loại bỏ |
| Request filter | header/path trước và sau filter, auth context, retry và rate limit |
| Response filter | status, header trùng, CORS, body streaming, lỗi upstream và response đã commit |
| Global/default filter | route có và không có filter riêng, filter custom và thứ tự pre/post |

Một bài kiểm thử chỉ xác nhận status code thường chưa đủ. Hãy ghi lại route ID được chọn, URI upstream, method, path, header quan trọng và số lần request thực sự tới backend. Với retry hoặc weight, dùng bộ đếm phía upstream để kiểm tra hành vi thay vì chỉ quan sát response cuối cùng.

## 7. Viết regression test cho route

Tạo test cho các trường hợp biên trước khi đổi dependency. Với ứng dụng WebFlux, `WebTestClient` có thể gửi request qua Gateway đang chạy trong test context; backend đích có thể được thay bằng stub server hoặc service giả có bộ đếm request.

Ví dụ khung kiểm thử hai dạng path:

```java
@AutoConfigureWebTestClient
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GatewayPathCompatibilityTest {

    @Autowired
    WebTestClient client;

    @Test
    void routesCanonicalOrderPath() {
        client.get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void handlesTrailingSlashAccordingToApiContract() {
        client.get()
            .uri("/api/orders/42/")
            .exchange()
            .expectStatus().isOk();
    }
}
```

Đây là khung minh họa. Cần khởi tạo stub upstream, cấu hình port động và xác nhận response theo hợp đồng của service. Nếu API chủ ý không chấp nhận trailing slash, test thứ hai phải xác nhận status và route được chọn theo chính sách đó, thay vì ép nó trả `200`.

Để kiểm tra filter chain, có thể cho upstream stub trả lại request method, path và một số header không nhạy cảm dưới dạng JSON. Test sẽ xác minh dữ liệu Gateway thực sự gửi đi. Với response filter, tạo upstream trả header trùng hoặc stream nhiều phần để xác nhận Gateway giữ đúng ngữ nghĩa response.

Chạy cùng một bộ test với dependency nguồn và đích. Nếu dùng profile hoặc route được sinh động, nạp đúng cấu hình tương đương ở cả hai lần chạy. Không dùng hai bộ fixture khác nhau vì sẽ làm kết quả so sánh mất ý nghĩa.

## 8. Quy trình nâng cấp an toàn

1. **Chốt phiên bản:** ghi lại BOM, Boot, Framework, Gateway và dependency HTTP client của bản hiện tại và bản đích.
2. **Kiểm kê route:** xuất toàn bộ route tĩnh, route Java, route từ discovery và route nạp từ cấu hình ngoài. Ghi lại `order`, predicates, filters và metadata.
3. **Thu thập cấu hình hiệu lực:** hợp nhất profile, biến môi trường, tham số dòng lệnh và cấu hình từ Config Server. Đánh dấu các thuộc tính đang dựa vào default.
4. **Ưu tiên kiểm tra thành phần nhạy cảm:** Path/trailing slash, `RemoteAddr`, forwarded header, Retry, RequestRateLimiter, CircuitBreaker, response rewrite và streaming.
5. **Chạy regression test trên bản nguồn:** lưu route ID, upstream, status, header, số lần gọi upstream và thời gian xử lý làm baseline.
6. **Nâng BOM trong nhánh riêng:** không override lẻ dependency Spring Framework hoặc Gateway nếu ma trận tương thích không yêu cầu. Xử lý compile/configuration warning và thay đổi API trước khi đánh giá hành vi runtime.
7. **Chạy cùng test trên bản đích:** so sánh từng kết quả với baseline. Với sai khác, xác định đó là thay đổi có chủ đích, thay đổi mặc định hay cấu hình môi trường bị lệch.
8. **Khai báo tường minh các default quan trọng:** chỉ định rõ giá trị mà hệ thống phụ thuộc vào, chẳng hạn pattern path, retry, rate limit và header strategy. Ghi chú lý do để lần nâng cấp sau không phải suy đoán.
9. **Canary và quan sát:** theo dõi phân bố route, lỗi 4xx/5xx, retry count, rate limit rejection, circuit breaker state, latency và request tới upstream.
10. **Hoàn tất hoặc rollback:** chỉ mở rộng rollout khi hành vi route và filter đáp ứng hợp đồng. Giữ khả năng rollback dependency và cấu hình cùng nhau.

## 9. Checklist review trước khi merge

- [ ] Phiên bản Gateway được resolve phù hợp BOM và ma trận tương thích Boot/Framework.
- [ ] Đã so sánh cả cấu hình trực tiếp, `default-filters`, global filter và HTTP headers filter.
- [ ] Path predicate đã được kiểm thử với trailing slash, path encoded và path case-sensitive.
- [ ] `Host`, `Method`, `Header`, `Query`, `Cookie`, `RemoteAddr` và time predicate có ca kiểm thử tương ứng với route đang sử dụng.
- [ ] Route order và weight không làm request rơi sang backend khác.
- [ ] Retry có method, số lần thử, status/exception và backoff phù hợp; request không idempotent được bảo vệ.
- [ ] Rate limiter có key resolver tin cậy, đơn vị token đúng và hành vi khi Redis lỗi đã được kiểm tra.
- [ ] Header forwarding và hop-by-hop header được kiểm tra qua đúng topology proxy; header giả mạo không được tin cậy.
- [ ] Custom filter có thứ tự rõ ràng và không ghi response hai lần hoặc tiêu thụ body streaming ngoài ý muốn.
- [ ] Regression test nguồn/đích dùng cùng fixture và đã so sánh route ID, upstream, header, body và số lần gọi backend.
- [ ] Canary có metric và log đủ để phát hiện thay đổi hành vi sau rollout.

Nâng cấp an toàn đòi hỏi biết chính xác request nào khớp route nào và filter nào đã thay đổi request/response. Khi các giá trị quan trọng được kiểm kê, khai báo tường minh và kiểm thử trên cả phiên bản nguồn lẫn phiên bản đích, thay đổi mặc định sẽ trở thành sai khác có thể quan sát và xử lý trước khi ảnh hưởng production.
