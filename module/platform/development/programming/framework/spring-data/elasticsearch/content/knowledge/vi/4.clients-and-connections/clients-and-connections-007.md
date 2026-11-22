# Connect timeout, socket timeout và thời gian chờ yêu cầu

Khi Spring Data Elasticsearch gửi một thao tác tới Elasticsearch, ứng dụng phải chờ qua nhiều giai đoạn: lấy một kết nối từ connection pool, thiết lập kết nối mạng nếu cần, gửi HTTP request, chờ Elasticsearch xử lý, nhận response và chuyển response thành object Java. Mỗi giai đoạn có thể có giới hạn thời gian riêng.

Nếu cấu hình timeout quá ngắn, ứng dụng có thể báo lỗi dù Elasticsearch vẫn hoạt động bình thường. Nếu timeout quá dài, thread và request có thể bị giữ lâu khi cluster hoặc mạng đang gặp sự cố. Muốn cấu hình hợp lý, trước hết cần phân biệt **connect timeout**, **socket/read timeout**, **connection-pool acquisition timeout** và **request deadline**.

## 1. Vòng đời một request và các điểm có thể timeout

Một thao tác như:

```java
Product product = productRepository.findById("1001").orElse(null);
```

có thể đi qua các bước khái quát sau:

```text
Ứng dụng Spring
      |
      v
Spring Data Elasticsearch
      |
      v
Elasticsearch Java Client
      |
      v
HTTP client / connection pool
      |
      +---- Chờ lấy connection khả dụng
      |
      +---- DNS, TCP connect và TLS handshake
      |
      v
Gửi HTTP request tới Elasticsearch
      |
      v
Elasticsearch tiếp nhận và xử lý
      |
      v
HTTP response được truyền về
      |
      v
Client đọc body, giải mã JSON và trả kết quả
```

Không phải request nào cũng tạo một kết nối TCP mới. HTTP client thường tái sử dụng kết nối trong pool. Khi có sẵn một kết nối phù hợp, request có thể bỏ qua giai đoạn TCP connect và TLS handshake.

Timeout có thể xuất hiện ở các điểm khác nhau:

| Loại timeout | Giai đoạn được giới hạn | Câu hỏi cần trả lời |
|---|---|---|
| Connection-pool acquisition timeout | Chờ mượn connection từ pool | Có connection khả dụng để gửi request không? |
| Connect timeout | Thiết lập kết nối mạng mới | Có kết nối được tới Elasticsearch trong thời gian cho phép không? |
| Socket/read timeout | Đọc dữ liệu từ kết nối | Client có nhận được dữ liệu tiếp theo trong thời gian cho phép không? |
| Request deadline | Toàn bộ thời gian xử lý request ở một tầng | Request có hoàn tất trước hạn chót chung không? |
| Elasticsearch-side timeout | Một hoạt động xử lý bên trong Elasticsearch | Elasticsearch được phép chờ hoặc xử lý hoạt động đó trong bao lâu? |

Các tên gọi có thể khác nhau giữa Apache HttpClient, Elasticsearch Java API Client, Reactor Netty, Spring WebClient và gateway. Khi đọc cấu hình, hãy xác định timeout thuộc tầng nào thay vì chỉ dựa vào tên thuộc tính.

## 2. Connect timeout

**Connect timeout** là khoảng thời gian tối đa HTTP client chờ thiết lập kết nối tới server. Quá trình này có thể gồm việc mở TCP connection và, với HTTPS, thực hiện TLS handshake tùy cách thư viện triển khai timeout.

Ví dụ, ứng dụng đặt connect timeout là 3 giây:

- Nếu kết nối được thiết lập trong 100 ms, request tiếp tục bình thường.
- Nếu server không thể truy cập và quá trình kết nối vượt quá 3 giây, client dừng chờ và phát sinh lỗi timeout.
- Nếu server từ chối kết nối ngay, ứng dụng có thể nhận lỗi connection refused trước khi hết 3 giây. Đây là lỗi kết nối khác với connect timeout.

Connect timeout chủ yếu ảnh hưởng khi client cần tạo kết nối mới. Nếu request sử dụng một connection đang được tái sử dụng từ pool, connect timeout không phải thời gian giới hạn cho toàn bộ request đó.

### Những nguyên nhân thường gặp

- Elasticsearch không chạy hoặc không lắng nghe trên host/port cấu hình.
- Ứng dụng dùng sai hostname, port hoặc giao thức HTTP/HTTPS.
- DNS phân giải chậm hoặc không phân giải được.
- Firewall, network policy, proxy hoặc security group chặn kết nối.
- Server quá tải hoặc mạng giữa ứng dụng và Elasticsearch có độ trễ cao.
- TLS handshake thất bại hoặc kéo dài do cấu hình chứng chỉ, proxy hay mạng.

### Cách phân biệt lỗi kết nối

| Biểu hiện | Ý nghĩa thường gặp |
|---|---|
| Connection refused | Đã tiếp cận được đích mạng nhưng cổng không chấp nhận kết nối, thường do service chưa chạy hoặc sai port. |
| Connect timed out | Client không thiết lập được kết nối trong thời hạn cấu hình; cần kiểm tra mạng, host và trạng thái server. |
| Unknown host / DNS resolution failure | Tên máy chủ không phân giải được thành địa chỉ IP. |
| SSL handshake exception | Kết nối TLS gặp vấn đề về chứng chỉ, giao thức hoặc cấu hình bảo mật. |

Không nên tăng connect timeout ngay khi gặp lỗi. Trước hết hãy kiểm tra hostname, port, giao thức, trạng thái Elasticsearch và khả năng kết nối từ chính máy/container đang chạy ứng dụng.

## 3. Socket timeout và read timeout

**Socket timeout** thường được dùng để chỉ thời gian tối đa client chờ dữ liệu khi đọc từ socket. Trong nhiều HTTP client, nó tương ứng với read timeout hoặc socket SO_TIMEOUT.

Sau khi request được gửi, client chờ response từ Elasticsearch. Nếu không nhận được dữ liệu trong khoảng thời gian quy định, thao tác đọc có thể phát sinh lỗi như:

```text
java.net.SocketTimeoutException: Read timed out
```

Ví dụ, socket timeout là 20 giây:

1. Client gửi request thành công.
2. Elasticsearch bắt đầu xử lý.
3. Trong 20 giây tiếp theo client không nhận được dữ liệu để tiếp tục đọc.
4. Client báo read timeout.

Điều này không tự động chứng minh Elasticsearch đã dừng xử lý. Request có thể đã tới server và server vẫn đang chạy truy vấn sau khi client ngừng chờ. Vì vậy, timeout phía client không đồng nghĩa thao tác phía server chắc chắn chưa xảy ra.

### Socket timeout có phải tổng thời gian request?

Không nhất thiết. Với nhiều HTTP client, socket timeout là giới hạn chờ cho một lần đọc hoặc khoảng thời gian không nhận được dữ liệu, chứ không phải một deadline tuyệt đối tính từ lúc bắt đầu request.

Ví dụ, một response lớn được truyền thành nhiều phần. Nếu dữ liệu tiếp tục đến đều đặn, mỗi lần đọc có thể hoàn tất trong giới hạn socket timeout dù tổng thời gian tải response dài hơn giá trị đó. Ngược lại, nếu server tạm ngừng gửi dữ liệu quá lâu, client có thể timeout giữa chừng.

Hành vi chính xác phụ thuộc HTTP client và phiên bản đang dùng. Đọc tài liệu của transport thực tế trước khi coi socket timeout là giới hạn tổng thời gian.

### Những nguyên nhân thường gặp

- Elasticsearch đang xử lý truy vấn tốn nhiều thời gian.
- Query quét quá nhiều dữ liệu, dùng aggregation nặng hoặc truy vấn trên nhiều shard.
- Cluster thiếu CPU, RAM, I/O hoặc đang chịu tải cao.
- Response quá lớn hoặc đường truyền mạng chậm.
- Gateway, proxy hoặc load balancer làm gián đoạn response.
- Timeout được đặt thấp hơn thời gian xử lý bình thường của nghiệp vụ.

Khi gặp read timeout, hãy kiểm tra thời gian xử lý, query, kích thước response, trạng thái cluster và log ở cả phía ứng dụng lẫn Elasticsearch. Tăng timeout có thể phù hợp với một truy vấn vốn cần thời gian dài, nhưng không xử lý được nguyên nhân như query kém hiệu quả hoặc cluster quá tải.

## 4. Connection-pool acquisition timeout

HTTP client thường duy trì một pool gồm nhiều kết nối để tái sử dụng. Mỗi kết nối đang được sử dụng có thể chưa sẵn sàng cho request khác, tùy cách pool và giao thức quản lý kết nối.

Khi tất cả connection khả dụng đều đang bận hoặc pool đạt giới hạn, request mới phải chờ một connection được trả về pool. Thời gian chờ này có thể được giới hạn bằng **connection request timeout**, **connection-pool timeout** hoặc tên tương tự.

Ví dụ:

- Pool chỉ có thể phục vụ một số lượng request đồng thời nhất định.
- Nhiều request đồng thời đang chiếm hết connection.
- Request tiếp theo phải chờ.
- Nếu không có connection được giải phóng trước thời hạn, client báo lỗi chờ lấy connection.

Đây không phải connect timeout. Trong trường hợp pool cạn, client thậm chí chưa bắt đầu kết nối mạng tới Elasticsearch.

Các nguyên nhân thường gặp:

- Lượng request đồng thời vượt khả năng pool.
- Request trước đó bị chậm và giữ connection lâu.
- Response body không được đọc/đóng đúng cách ở đoạn code tự quản lý HTTP response.
- Pool được cấu hình quá nhỏ so với tải.
- Elasticsearch hoặc mạng phản hồi chậm làm connection bị chiếm dụng lâu.

Nếu lỗi xuất hiện khi tải tăng, hãy xem số request đồng thời, thời gian giữ connection, số connection đang leased/available/pending và giới hạn pool. Chỉ tăng số connection có thể chuyển áp lực sang Elasticsearch; cần kiểm tra năng lực cluster và giới hạn tải cùng lúc.

## 5. Request timeout và deadline của request

Cụm từ **request timeout** thường gây nhầm lẫn vì các thư viện và tầng hệ thống dùng nó theo những nghĩa khác nhau.

Ở cấp ứng dụng, request deadline có thể là tổng ngân sách thời gian từ lúc một thao tác bắt đầu cho đến khi ứng dụng cần trả kết quả. Ngân sách này có thể bao gồm:

- Chờ connection trong pool.
- Thiết lập kết nối mới nếu cần.
- Gửi request.
- Chờ Elasticsearch xử lý.
- Đọc response.
- Giải mã response và xử lý kết quả trong ứng dụng.

Ví dụ, một API của ứng dụng có deadline 25 giây. Nếu việc lấy connection mất 2 giây, thiết lập kết nối mất 1 giây và chờ response mất 20 giây, tổng thời gian đã gần hết ngân sách. Một socket timeout 20 giây không có nghĩa toàn bộ request chắc chắn kết thúc trong 20 giây.

Không phải mọi phiên bản Spring Data Elasticsearch đều cung cấp một thuộc tính chung tên `requestTimeout` trong `ClientConfiguration`. `withConnectTimeout(...)` và `withSocketTimeout(...)` là hai cấu hình thường dùng; deadline tổng thể, timeout chờ connection trong pool hoặc các timeout riêng khác có thể cần cấu hình ở HTTP client bên dưới hoặc ở tầng ứng dụng.

### Deadline ở các tầng khác nhau

Một request từ trình duyệt có thể đi qua nhiều tầng:

```text
Browser
  |
  v
API Gateway / Load Balancer
  |
  v
Spring Boot Controller
  |
  v
Spring Data Elasticsearch
  |
  v
HTTP Client
  |
  v
Elasticsearch
```

Mỗi tầng có thể đặt thời hạn riêng. Nếu gateway ngừng chờ sau 15 giây nhưng ứng dụng và Elasticsearch được cấu hình chờ 60 giây, người dùng vẫn nhận lỗi gateway trước khi các tầng bên dưới hoàn tất. Request ở server có thể vẫn tiếp tục chạy tùy cơ chế hủy của từng tầng.

Một thiết kế tốt cần có ngân sách thời gian nhất quán: các tầng bên trong nên có cơ hội trả lỗi có kiểm soát trước khi tầng bên ngoài hết hạn. Đồng thời cần dành một phần thời gian cho xử lý và trả response, không dùng toàn bộ ngân sách chỉ cho thao tác Elasticsearch.

### Timeout ở tầng ứng dụng

Với API bất đồng bộ, một số abstraction cho phép đặt deadline cho kết quả. Ví dụ với Reactor:

```java
Mono<Product> productMono =
    reactiveProductRepository.findById("1001")
        .timeout(Duration.ofSeconds(25));
```

Hoặc với một `CompletableFuture`:

```java
future.orTimeout(25, TimeUnit.SECONDS);
```

Đây là ví dụ về giới hạn thời gian chờ kết quả ở abstraction tương ứng. Cách timeout truyền xuống transport và việc request HTTP thực sự được hủy hay không phụ thuộc client, phiên bản và cách tích hợp. Hoàn tất một future bằng timeout không tự chứng minh công việc bên dưới đã dừng.

Đối với thao tác đồng bộ, không nên chỉ đưa lời gọi blocking vào một thread khác rồi timeout việc chờ thread đó. Nếu HTTP call bên dưới vẫn chạy, thread và connection vẫn có thể bị giữ. Hãy ưu tiên timeout do HTTP transport hỗ trợ và kiểm tra cơ chế cancellation thực tế.

## 6. Timeout ở phía Elasticsearch

Timeout phía client và timeout phía Elasticsearch phục vụ hai mục đích khác nhau.

Ví dụ, Search API có tham số `timeout`:

```http
POST /products/_search?timeout=2s
{
  "query": {
    "match": {
      "name": "wireless mouse"
    }
  }
}
```

Đây là giới hạn liên quan đến thời gian Elasticsearch dành cho hoạt động tìm kiếm. Khi hết thời gian, response có thể có:

```json
{
  "timed_out": true,
  "hits": {
    "total": {
      "value": 0,
      "relation": "eq"
    },
    "hits": []
  }
}
```

Response minh họa cho thấy cần đọc trường `timed_out`, thông tin shard và các kết quả trả về để biết truy vấn có hoàn tất đầy đủ hay không. Một search timeout phía server không giống socket timeout: trong trường hợp thứ nhất Elasticsearch báo trạng thái xử lý tìm kiếm; trong trường hợp thứ hai client không nhận được dữ liệu đúng hạn.

Các API Elasticsearch khác có thể có tham số timeout riêng, chẳng hạn thời gian chờ một điều kiện cluster hoặc thao tác quản trị. Ý nghĩa của từng tham số phải được đọc theo API cụ thể. Không nên thêm `timeout=...` vào mọi endpoint và coi đó là deadline tổng thể của HTTP request.

## 7. Cấu hình connect timeout và socket timeout trong Spring Data Elasticsearch

Với Spring Data Elasticsearch sử dụng Elasticsearch Java API Client, có thể cấu hình hai giá trị này thông qua `ClientConfiguration`.

Ví dụ cấu hình minh họa:

```java
import java.time.Duration;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;

@Configuration
public class ElasticsearchClientConfig extends ElasticsearchConfiguration {

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
            .connectedTo("localhost:9200")
            .withConnectTimeout(Duration.ofSeconds(3))
            .withSocketTimeout(Duration.ofSeconds(20))
            .build();
    }
}
```

Trong ví dụ:

- `connectedTo("localhost:9200")` khai báo địa chỉ Elasticsearch.
- `withConnectTimeout(Duration.ofSeconds(3))` giới hạn thời gian thiết lập kết nối mới.
- `withSocketTimeout(Duration.ofSeconds(20))` giới hạn thời gian chờ đọc dữ liệu theo hành vi của HTTP transport.

Đây là các giá trị minh họa cho môi trường phát triển, không phải giá trị mặc định hay khuyến nghị cho mọi hệ thống. Hãy điều chỉnh theo độ trễ mạng, tải, kích thước response và yêu cầu của nghiệp vụ.

Tên lớp cấu hình và package có thể khác giữa các thế hệ Spring Data Elasticsearch. Ví dụ trên dùng cấu hình dựa trên Elasticsearch Java API Client ở các phiên bản Spring Data tương ứng. Với dự án cũ dùng cấu hình `AbstractElasticsearchConfiguration`, RestHighLevelClient hoặc một transport khác, hãy dùng API được hỗ trợ bởi đúng phiên bản dependency của dự án; không trộn cấu hình của hai loại client.

### Kiểm tra cấu hình có được áp dụng không

Sau khi cấu hình, cần xác nhận ứng dụng thực sự tạo client từ bean/configuration này:

- Kiểm tra Spring context chỉ có cấu hình client mong muốn.
- Kiểm tra repository và `ElasticsearchOperations` đang dùng cùng client được cấu hình.
- Xem log khởi tạo client và cấu hình môi trường đang chạy.
- Kiểm tra cấu hình profile, biến môi trường hoặc bean khác có ghi đè cấu hình hay không.

Tạo một client mới cho mỗi lần gọi repository sẽ làm mất lợi ích của connection pool và có thể gây ra nhiều kết nối không cần thiết. Client nên được quản lý theo vòng đời của ứng dụng thông qua Spring bean.

## 8. Tùy chỉnh HTTP client bên dưới

Khi cần kiểm soát thêm thời gian chờ lấy connection từ pool hoặc một thiết lập transport cụ thể, có thể phải tùy chỉnh HTTP client được Elasticsearch client sử dụng.

Với một số thế hệ Elasticsearch REST Client dựa trên Apache HttpClient 4, API cấu hình thấp hơn có các khái niệm như:

```java
requestConfigBuilder
    .setConnectTimeout(3_000)
    .setSocketTimeout(20_000)
    .setConnectionRequestTimeout(2_000);
```

Đoạn trên chỉ minh họa tên các thiết lập ở tầng Apache HttpClient 4. Cách đưa cấu hình này vào Spring Data phụ thuộc phiên bản và callback mà phiên bản đó cung cấp. Các phiên bản dùng transport khác có API khác; không sao chép đoạn cấu hình này vào dự án nếu dependency thực tế không dùng Apache HttpClient 4.

Hãy xác định chính xác các dependency đang chạy, ví dụ Elasticsearch Java API Client, Elasticsearch REST Client, Apache HttpClient hoặc Reactor Netty, rồi cấu hình theo tài liệu của transport đó. Tránh tự tạo một HTTP client thứ hai trong khi Spring Data vẫn đang dùng client cũ, vì điều đó khiến cấu hình mới không có tác dụng.

Với ứng dụng reactive, đường truyền có thể được quản lý bởi WebClient/Reactor Netty. Khi đó cần xem riêng các giới hạn như connect timeout, response timeout, connection-provider pending acquire timeout và cancellation. Không mặc định rằng `withSocketTimeout` của cấu hình imperative cũng áp dụng cho reactive client.

## 9. Chọn giá trị timeout như thế nào?

Không có một bộ giá trị phù hợp với mọi ứng dụng. Cách chọn nên bắt đầu từ ngân sách thời gian của nghiệp vụ và số liệu đo thực tế.

Giả sử một API cần trả kết quả trong khoảng 25 giây. Một cấu hình minh họa có thể phân bổ:

| Giai đoạn | Ngân sách minh họa |
|---|---:|
| Chờ connection trong pool | 2 giây |
| Thiết lập kết nối mới | 3 giây |
| Chờ response/read | 15–20 giây |
| Xử lý kết quả và trả response | Phần thời gian còn lại |

Đây là ví dụ để tư duy về ngân sách, không phải công thức cộng chính xác cho mọi HTTP client. Socket timeout có thể là thời gian chờ đọc giữa các lần nhận dữ liệu, nên không nhất thiết tương đương tổng thời gian truyền response.

Một số nguyên tắc thực tế:

1. **Connect timeout nên đủ ngắn để phát hiện đích mạng không thể truy cập.** Kết nối mạng mới thường không cần chờ lâu như một truy vấn tìm kiếm phức tạp.
2. **Socket/read timeout phải phù hợp với request hợp lệ lâu nhất.** Truy vấn aggregation hoặc tải response lớn có thể cần thời gian dài hơn thao tác đọc theo ID.
3. **Pool acquisition timeout cần phản ánh mức chờ chấp nhận được.** Chờ pool quá lâu thường là dấu hiệu tải đồng thời hoặc pool chưa phù hợp.
4. **Deadline tổng thể phải tính cả các bước trước và sau Elasticsearch.** Đừng để gateway hết hạn trước khi ứng dụng có cơ hội trả lỗi có kiểm soát.
5. **Không tăng mọi timeout cùng lúc.** Nếu lỗi đến từ pool cạn hoặc query chậm, tăng socket timeout có thể chỉ làm request giữ tài nguyên lâu hơn.

Nên đo latency ở các mức percentile như p50, p95 và p99 trong điều kiện tải thực tế. Giá trị p99 giúp phát hiện các request chậm ở phần đuôi phân phối. Hãy kết hợp số liệu này với SLA của API, giới hạn của gateway và khả năng xử lý của cluster để chọn timeout.

## 10. Chẩn đoán lỗi timeout

Khi thấy một lỗi timeout, hãy xác định nó xảy ra ở giai đoạn nào trước khi thay đổi cấu hình.

| Dấu hiệu hoặc exception | Khả năng liên quan | Việc cần kiểm tra |
|---|---|---|
| `ConnectTimeoutException`, connect timed out | Thiết lập kết nối mới | Host, port, DNS, firewall, route mạng, trạng thái node. |
| `ConnectException: Connection refused` | Server không chấp nhận kết nối | Elasticsearch có chạy không, port có đúng không, service có listen không. |
| `SocketTimeoutException: Read timed out` | Chờ đọc response | Query, tải cluster, response size, mạng, proxy và socket timeout. |
| Connection pool timeout / timeout waiting for connection | Chờ lấy connection | Mức đồng thời, pool capacity, thời gian giữ connection và response chậm. |
| Reactor `TimeoutException` | Timeout ở reactive chain hoặc transport | Vị trí đặt `timeout(...)`, cấu hình Reactor Netty và cancellation. |
| HTTP 429 | Server từ chối hoặc giới hạn tải | Áp lực cluster, thread pool, giới hạn request và chính sách retry. |
| HTTP 502/503/504 | Gateway, proxy hoặc service upstream | Log của gateway, trạng thái upstream, deadline từng tầng và sức khỏe Elasticsearch. |

### Một quy trình điều tra có thứ tự

**Bước 1 — Xác nhận địa chỉ và kết nối cơ bản**

Từ đúng máy hoặc container chạy ứng dụng, kiểm tra hostname, port, DNS, giao thức và khả năng kết nối. Kiểm tra Elasticsearch có sẵn sàng nhận request hay không. Nếu request chưa kết nối được, chưa cần điều tra query.

**Bước 2 — Xác định exception gốc**

Spring có thể bọc exception từ HTTP client trong exception khác. Đọc toàn bộ cause chain và log stack trace để tìm lỗi gốc. Phân biệt connect timeout, read timeout, pool timeout, DNS và lỗi TLS.

**Bước 3 — So sánh thời gian ở các tầng**

Ghi nhận thời điểm bắt đầu/kết thúc thao tác tại ứng dụng, thời gian chờ HTTP, thời gian xử lý phía Elasticsearch nếu có thể quan sát và thời gian ở gateway. Nếu gateway timeout sau 15 giây trong khi client timeout là 30 giây, cần xem lại thứ tự deadline.

**Bước 4 — Thử request đơn giản và query thực tế**

So sánh một request nhẹ như kiểm tra cluster health hoặc lấy document theo ID với query gây timeout. Nếu chỉ một query chậm, hãy kiểm tra mapping, query, aggregation, số shard và kích thước response.

**Bước 5 — Kiểm tra tải đồng thời và pool**

Quan sát số request đang chạy, thời gian chờ connection, connection đang sử dụng và số request pending. Nếu lỗi tăng theo concurrency, cần điều tra pool và giới hạn tải.

**Bước 6 — Điều chỉnh một biến và đo lại**

Thay đổi một timeout hoặc một yếu tố hiệu năng mỗi lần, sau đó chạy lại cùng kịch bản tải. So sánh latency, tỷ lệ lỗi, tài nguyên client và cluster. Cách này giúp biết thay đổi nào thực sự cải thiện hệ thống.

## 11. Retry khi timeout

Retry có thể giúp vượt qua lỗi mạng tạm thời, nhưng timeout tạo ra một tình huống không chắc chắn: client không biết request đã tới server và được xử lý hay chưa.

Ví dụ, ứng dụng gửi lệnh ghi document. Elasticsearch nhận và ghi thành công, nhưng response bị mất trên đường truyền. Client hết thời gian chờ. Nếu ứng dụng gửi lại một request ghi khác, có thể tạo ra dữ liệu trùng hoặc thực hiện cùng một tác động hai lần.

Cần phân biệt:

- **Read request** như tìm kiếm hoặc lấy document thường phù hợp để retry khi lỗi tạm thời, nhưng vẫn phải giới hạn số lần và tổng thời gian.
- **Index document với ID xác định** có thể được thiết kế để retry an toàn hơn nếu cùng một request ghi đè đúng document theo semantics mong muốn.
- **Tạo document với ID tự sinh** có thể tạo nhiều document khi retry.
- **Bulk request** có thể thành công một phần. Cần đọc kết quả từng item để chỉ retry những item phù hợp, thay vì gửi lại mù toàn bộ batch.
- **Update có script hoặc thao tác tăng/giảm giá trị** có thể không idempotent. Retry có thể áp dụng tác động nhiều lần.

Một chính sách retry cần có số lần tối đa, exponential backoff, jitter và tổng retry budget. Không retry vô hạn và không retry ngay lập tức theo vòng lặp dày đặc, vì điều đó có thể làm cluster đang quá tải càng quá tải hơn.

Trước khi retry thao tác ghi, hãy xác định tính idempotent, cách chọn document ID và khả năng request trước đã được thực hiện. Timeout là trạng thái kết quả không xác định, không phải bằng chứng chắc chắn rằng thao tác thất bại.

## 12. Những sai lầm thường gặp

- **Chỉ tăng socket timeout khi gặp connect timeout.** Hai lỗi xảy ra ở hai giai đoạn khác nhau; tăng read timeout không sửa được lỗi thiết lập kết nối.
- **Coi socket timeout là tổng thời gian request.** Nhiều transport dùng nó làm giới hạn chờ đọc, không phải deadline end-to-end.
- **Bỏ qua thời gian chờ pool.** Request có thể chưa hề gửi tới Elasticsearch nhưng vẫn timeout vì không lấy được connection.
- **Đặt timeout ở gateway dài hơn mọi tầng bên trong mà không có kế hoạch.** Client bên ngoài có thể bỏ cuộc trong khi công việc ở server vẫn giữ tài nguyên.
- **Tạo Elasticsearch client mới cho từng thao tác.** Điều này làm giảm hiệu quả tái sử dụng connection và có thể tạo nhiều kết nối.
- **Retry mọi thao tác ghi sau timeout.** Server có thể đã thực hiện request trước khi response bị mất.
- **Dùng timeout phía Elasticsearch thay cho timeout mạng.** Search timeout không thay thế connect timeout hay socket timeout.
- **Đặt timeout quá dài để che giấu query chậm.** Request sẽ giữ thread và connection lâu hơn, làm giảm khả năng phục vụ các request khác.

## 13. Checklist cấu hình và vận hành

Khi triển khai client Spring Data Elasticsearch, hãy xác nhận:

- Địa chỉ cluster, port, HTTP/HTTPS, authentication và TLS đúng với môi trường.
- Client được quản lý bởi Spring và tái sử dụng qua các thao tác.
- Connect timeout phù hợp với môi trường mạng.
- Socket/read timeout phù hợp với thời gian xử lý và kích thước response dự kiến.
- Pool acquisition timeout được xem xét nếu transport cho phép cấu hình.
- Deadline ở tầng ứng dụng, gateway và các service liên quan nhất quán.
- Reactive và imperative client được cấu hình theo đúng transport mà chúng sử dụng.
- Log ghi được loại exception gốc và thời gian request.
- Metrics theo dõi latency, timeout rate, concurrency và trạng thái connection pool.
- Retry có giới hạn và an toàn với loại thao tác đang thực hiện.

## 14. Bảng tra cứu nhanh

| Câu hỏi | Timeout cần xem |
|---|---|
| Không mở được kết nối tới Elasticsearch | Connect timeout |
| Request phải chờ connection khả dụng trong pool | Connection-pool acquisition timeout |
| Đã gửi request nhưng chờ response quá lâu | Socket/read timeout |
| Muốn giới hạn tổng thời gian của thao tác ở tầng ứng dụng | Request deadline / application timeout |
| Muốn giới hạn thời gian một truy vấn Search phía Elasticsearch | Search API timeout |
| Request bên ngoài hết hạn trước khi backend hoàn tất | Deadline của gateway và các tầng bên trong |

Connect timeout, socket timeout và request deadline là những giới hạn ở các giai đoạn khác nhau. Khi Spring Data Elasticsearch báo timeout, hãy xác định request đang chờ lấy connection, thiết lập kết nối, đọc response hay chờ toàn bộ nghiệp vụ. Từ đó mới chọn đúng nơi cấu hình, kiểm tra nguyên nhân và quyết định có cần retry hay tối ưu query.
