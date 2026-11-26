# Timeout kết nối, đọc và giới hạn chờ của transport

## 1. Vì sao Spring Vault cần timeout?

Ứng dụng Java dùng **Spring Vault** gửi HTTP request đến **HashiCorp Vault** để đăng nhập, đọc KV secrets, tạo token, gia hạn lease, gọi Transit encryption hoặc yêu cầu chứng chỉ PKI. Những thao tác này có thể diễn ra khi khởi động ứng dụng lẫn khi đang xử lý request nghiệp vụ. Nếu kết nối đến Vault bị nghẽn hoặc phía máy chủ không phản hồi, một lời gọi đồng bộ của `VaultTemplate` có thể giữ thread lâu hơn mức ứng dụng chấp nhận.

**Timeout** quy định một giới hạn chờ trong transport HTTP. Nó giúp:

- Phát hiện nhanh kết nối không thiết lập được hoặc endpoint không trả dữ liệu.
- Hạn chế thời gian thread bị giữ, nhất là khi nhiều lời gọi Vault cùng bị chậm.
- Tạo tín hiệu để ứng dụng áp dụng chiến lược xử lý lỗi, retry và quan sát vận hành.

Timeout **không** thay thế cho policy, xác thực workload, thời hạn token/lease hay cơ chế chịu lỗi của cụm Vault. Để cấu hình đúng, cần xác định rõ đang chờ ở **giai đoạn nào** của HTTP request.

## 2. Các giai đoạn của một lời gọi HTTP

Một request từ `VaultTemplate` có thể đi qua các giai đoạn sau:

```text
Java / VaultTemplate
  |
  +-- [1] Chờ lấy kết nối rảnh từ HTTP connection pool (nếu có pool)
  |
  +-- [2] Phân giải DNS và thiết lập TCP tới host:port (nếu cần kết nối mới)
  |
  +-- [3] Bắt tay TLS và xác minh chứng chỉ (khi dùng HTTPS)
  |
  +-- [4] Gửi HTTP request
  |
  +-- [5] Chờ response và đọc các byte của response body
  |
  v
Vault API / Load balancer / Reverse proxy
```

Không phải request nào cũng trải qua đầy đủ các bước. Ví dụ, khi HTTP client tái sử dụng kết nối keep-alive, nó có thể bỏ qua việc tạo TCP/TLS mới. Tùy thư viện HTTP, phân giải DNS, bắt tay TLS và ghi request cũng có thể được quản lý bằng các cơ chế timeout riêng.

| Giới hạn | Bắt đầu có ý nghĩa ở đâu? | Điều nó **không** đảm bảo |
| --- | --- | --- |
| **Connect timeout** | Khi thiết lập kết nối mạng tới endpoint. | Không giới hạn toàn bộ thời gian thực thi Vault API. |
| **Read/socket timeout** | Khi đang đợi dữ liệu từ kết nối đã thiết lập. | Không nhất thiết là deadline cho **toàn bộ** HTTP response. |
| **Connection-request / pool-acquire timeout** | Khi chờ một kết nối khả dụng từ connection pool. | Không phải thời gian bắt tay TCP với Vault. |
| **Overall timeout / deadline** | Giới hạn thời gian cho toàn bộ thao tác, **nếu client hoặc lớp gọi hỗ trợ**. | Không tự phát sinh khi chỉ đặt connect và read timeout. |

Tên thuộc tính và chính xác từng mốc thời gian phụ thuộc HTTP client (JDK, Apache HttpClient, v.v.) và phiên bản thư viện. Không giả định mọi `ClientHttpRequestFactory` đều cung cấp cả bốn loại giới hạn.

## 3. Connect timeout: chờ thiết lập kết nối

**Connect timeout** giới hạn giai đoạn kết nối tới Vault endpoint, chẳng hạn `vault.example.internal:8200`. Nó hữu ích khi đường mạng lỗi, địa chỉ đích không phản hồi hoặc proxy không thể kết nối đến backend.

Giả sử cấu hình connect timeout là 3 giây. Nếu kết nối TCP không hoàn tất trong ngưỡng do HTTP client áp dụng, lời gọi thường thất bại bằng lỗi I/O liên quan đến kết nối. Tuy nhiên:

- `Connection refused` có thể xuất hiện **ngay lập tức** khi không có listener ở port, không nhất thiết cần chờ hết 3 giây.
- DNS lookup và TLS handshake có thể có giới hạn khác, nên `3 giây` không phải cam kết rằng cả thao tác sẽ kết thúc sau đúng 3 giây.
- Khi tái sử dụng kết nối HTTP hiện có, connect timeout thường không được dùng cho request đó.
- Khi truy cập qua load balancer, đích mà Java kết nối trực tiếp là địa chỉ của load balancer, không nhất thiết là một Vault node.

Điều quan trọng là **connect timeout xử lý rủi ro không tạo được kết nối**, còn xử lý Vault chậm trả kết quả thuộc giai đoạn đọc dữ liệu.

## 4. Read timeout: chờ dữ liệu phản hồi

Sau khi đã thiết lập kết nối và gửi request, Vault có thể mất thời gian để xử lý thao tác như xác thực, đọc secrets hoặc cấp chứng chỉ. **Read timeout** giới hạn việc chờ dữ liệu từ HTTP connection theo ngữ nghĩa của transport.

Ví dụ, đặt read timeout là 10 giây giúp phát hiện trường hợp kết nối còn tồn tại nhưng Vault hoặc proxy không gửi dữ liệu trong khoảng chờ cho phép.

Điểm dễ nhầm:

> Read timeout thường là giới hạn cho **một khoảng đợi đọc dữ liệu** trên socket. Nếu phía máy chủ liên tục gửi từng phần dữ liệu trước khi khoảng đợi hết hạn, tổng thời gian nhận response có thể vượt quá giá trị read timeout.

Vì thế, đặt `connectTimeout = 3000` và `readTimeout = 10000` **không đồng nghĩa** với một deadline cứng là 13 giây. DNS, TLS handshake, connection-pool wait, số lần đọc, retry và xử lý ở lớp ứng dụng có thể làm tổng thời gian lớn hơn.

Một read timeout quá thấp dễ tạo lỗi giả khi Vault đang chịu tải hoặc thao tác PKI cần xử lý thêm. Ngược lại, timeout quá dài có thể khiến thread ứng dụng tích tụ khi Vault gặp sự cố.

## 5. Giới hạn chờ ở connection pool và deadline tổng

### 5.1. Pool-acquire timeout khác connect timeout

Trong ứng dụng có nhiều request đồng thời, HTTP client có thể tái sử dụng một **connection pool**. Khi mọi kết nối đã được sử dụng và pool đạt giới hạn, request mới phải **chờ lấy connection**, ngay cả khi Vault vẫn hoạt động bình thường.

Ví dụ:

```text
10 kết nối tối đa tới Vault
10 request đang giữ kết nối
request thứ 11 -> đợi pool cấp kết nối -> mới được gửi HTTP request
```

Với client hỗ trợ pooling, hãy cấu hình giới hạn số kết nối và **thời gian chờ cấp kết nối** (thường gọi là `connectionRequestTimeout`, `poolAcquireTimeout` hoặc tên tương đương). Giá trị này khác với connect timeout: kết nối TCP mới có thể chưa hề được thử khi request đang đợi trong hàng chờ của pool.

Khi dùng `SimpleClientHttpRequestFactory` trong ví dụ phía dưới, bạn chỉ đặt trực tiếp connect/read timeout. Nếu cần kiểm soát pool-acquire timeout, hãy chọn một HTTP client có pool (ví dụ Apache HttpClient phù hợp phiên bản Spring Framework) và cấu hình cơ chế lấy connection **ngay trên client đó**. Không suy luận rằng thuộc tính `connection-timeout` của Spring Cloud Vault tự áp dụng cho mọi hàng chờ của mọi loại connection pool.

### 5.2. Deadline cho một thao tác nghiệp vụ

Một ứng dụng có thể đặt mục tiêu: “mỗi lần xử lý request thanh toán chỉ dành tối đa 2 giây để tra cứu secret”. Mục tiêu đó là **ngân sách thời gian** của nghiệp vụ. Connect/read timeout là các cấu hình thấp hơn, không tự thay thế deadline này.

Nếu cần một giới hạn tổng thực sự, phải dùng tính năng deadline/overall request timeout mà HTTP client hỗ trợ, hoặc cơ chế kiểm soát thời gian ở tầng gọi phù hợp. Với lời gọi đồng bộ, chỉ đặt timeout bên ngoài qua `Future` rồi hủy task chưa chắc đã ngắt được I/O đang chặn: cần kiểm tra hành vi hủy request và dọn tài nguyên của client thực tế.

Khi có retry, ngân sách thời gian còn phải bao gồm **mọi lần thử và thời gian backoff**. Ví dụ, hai lần thử với 10 giây đợi đọc mỗi lần cộng thời gian nghỉ có thể vượt xa mục tiêu phản hồi 10 giây, dù connect timeout chỉ là 3 giây.

## 6. Cấu hình timeout khi dùng Spring Vault trực tiếp

Với **Spring Vault** sử dụng `VaultTemplate`, timeout được thiết lập qua HTTP request factory được truyền cho template. Ví dụ dưới đây sử dụng `SimpleClientHttpRequestFactory` của Spring Web để thể hiện rõ hai giới hạn cơ bản:

```java
import java.util.Objects;

import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.authentication.TokenAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.core.VaultTemplate;

VaultEndpoint endpoint = new VaultEndpoint();
endpoint.setScheme("https");
endpoint.setHost("vault.example.internal");
endpoint.setPort(8200);

SimpleClientHttpRequestFactory httpFactory =
        new SimpleClientHttpRequestFactory();
httpFactory.setConnectTimeout(3_000);  // 3 giây
httpFactory.setReadTimeout(10_000);    // 10 giây

// Token từ môi trường chỉ để minh họa cách tạo ClientAuthentication.
String token = Objects.requireNonNull(
        System.getenv("VAULT_TOKEN"), "Thiếu VAULT_TOKEN");
ClientAuthentication authentication = new TokenAuthentication(token);

VaultTemplate vaultTemplate =
        new VaultTemplate(endpoint, authentication, httpFactory);
```

Trong cách cấu hình này:

1. `VaultEndpoint` xác định **scheme, host, port** của Vault.
2. `SimpleClientHttpRequestFactory` áp dụng connect/read timeout bằng **mili giây** cho HTTP client được `VaultTemplate` sử dụng.
3. `ClientAuthentication` cung cấp cơ chế xác thực. Token chỉ dùng để minh họa; triển khai thực tế nên chọn xác thực theo workload như Kubernetes authentication hoặc AppRole khi phù hợp.

**Lưu ý quan trọng về TLS:** HTTPS vẫn cần chứng chỉ máy chủ hợp lệ và CA được JVM/HTTP client tin cậy. Timeout không sửa lỗi `SSLHandshakeException`. Khi dùng CA nội bộ, cấu hình truststore hoặc SSL cho đúng client; không tắt xác minh chứng chỉ để “chữa timeout”.

Nếu ứng dụng có nhiều `VaultTemplate`, session manager hoặc HTTP client tự tạo, hãy xác định **đường gọi nào dùng HTTP client nào**. Đặt timeout cho một template không đảm bảo mọi tác vụ đăng nhập, gia hạn token và quản lý lease khác đều dùng cùng request factory.

### Khi nào chọn HTTP client có pool?

Ví dụ trên phù hợp để thấy rõ cách đặt connect/read timeout. Với lưu lượng lớn, HTTP client có quản lý pool có thể giúp kiểm soát số kết nối, thời gian đợi lấy kết nối và tài nguyên. Khi chuyển sang Apache HttpClient hoặc thư viện khác, cần kiểm tra sự tương thích giữa **Spring Framework/Spring Vault** và **phiên bản HTTP client** trước khi cấu hình thuộc tính thời gian. Các lớp và đơn vị timeout có thể khác nhau giữa các phiên bản.

## 7. Cấu hình khi sử dụng Spring Cloud Vault

Nếu ứng dụng dùng **Spring Cloud Vault** với cơ chế cấu hình tự động tương ứng, có thể thiết lập các thuộc tính:

```yaml
spring:
  cloud:
    vault:
      uri: "https://vault.example.internal:8200"
      connection-timeout: 3000 # mili giây
      read-timeout: 10000      # mili giây
```

`spring.cloud.vault.connection-timeout` kiểm soát thời gian chờ kết nối; `spring.cloud.vault.read-timeout` kiểm soát thời gian chờ đọc của HTTP client được **Spring Cloud Vault tự cấu hình**. Những ví dụ này là ngưỡng minh họa, cần điều chỉnh theo độ trễ, loại thao tác và yêu cầu của hệ thống.

Phân biệt:

- **Spring Vault** là thư viện dùng `VaultTemplate` và các operations; nếu tự khởi tạo template, bạn tự cung cấp transport với timeout mong muốn.
- **Spring Cloud Vault** tích hợp cấu hình Vault với Spring Boot/Spring Cloud; các thuộc tính `spring.cloud.vault.*` chỉ có hiệu lực khi thành phần tích hợp đó thực sự được sử dụng.
- **Spring Config Data `vault://`**, nếu được bật, là cú pháp import cấu hình. Nó không thay cho `https://` trong `spring.cloud.vault.uri`, cũng không phải một loại timeout.

Không dựa vào giá trị timeout mặc định khi chưa kiểm tra tài liệu của **phiên bản đang triển khai**; cách tạo HTTP client và giá trị mặc định có thể thay đổi theo dependency và cấu hình.

## 8. Chọn ngưỡng timeout theo thao tác và mức chịu lỗi

Không có một cặp connect/read timeout tối ưu cho mọi workload. Hãy bắt đầu từ **ngân sách phản hồi của ứng dụng** và số liệu đo thực tế:

| Thao tác | Đặc điểm | Cách cân nhắc |
| --- | --- | --- |
| Đọc KV secrets lúc startup | Ảnh hưởng trực tiếp thời gian khởi động | Cần giới hạn chờ rõ ràng và quyết định startup có được tiếp tục khi Vault lỗi hay không. |
| Đọc KV secrets trong request người dùng | Ảnh hưởng latency và số thread đang phục vụ | Giữ tổng thời gian trong ngân sách request; cân nhắc cache/kiến trúc giảm phụ thuộc Vault nếu phù hợp. |
| Workload authentication | Quyết định ứng dụng lấy được token hay không | Cần theo dõi cả request login và thời gian chờ của transport. |
| Token/lease renewal | Tác vụ diễn ra gần thời điểm hết hạn | Timeout, retry và lịch gia hạn cần đủ khoảng an toàn trước expiry; timeout không kéo dài TTL. |
| Transit encryption/decryption | Có thể nằm trên đường xử lý nhạy độ trễ | Đo p95/p99, tải đồng thời và độ trễ khi Vault chịu tải. |
| PKI issue/renew | Có thể xử lý lâu hơn KV read | Cân nhắc timeout phù hợp cho API phát hành chứng chỉ và quản lý hậu quả khi client bỏ cuộc. |

Quy trình chọn giá trị thực tế:

1. Đo thời gian kết nối và latency p95/p99 của từng nhóm lời gọi trong điều kiện bình thường và khi tải cao.
2. Xác định ngân sách thời gian cho nghiệp vụ hoặc startup, bao gồm cả retry/backoff nếu có.
3. Chọn connect timeout đủ nhanh để phát hiện endpoint khó truy cập, và read timeout phù hợp với thao tác chậm nhất được phép.
4. Nếu dùng pool, giới hạn số kết nối và thời gian chờ cấp kết nối; không để hàng chờ tăng vô hạn.
5. Chạy thử các kịch bản Vault chậm, mất mạng, standby/leader chuyển đổi, proxy đóng kết nối và CA/TLS cấu hình sai.

Các giá trị 3 giây/10 giây ở trên **không phải khuyến nghị bắt buộc**. Một ứng dụng có SLA 500 ms, một batch job nền và một dịch vụ tự động cấp PKI có thể cần các cấu hình khác nhau.

## 9. Timeout, retry và vòng đời token/lease

### 9.1. Không retry mọi lỗi giống nhau

Timeout là một **lỗi transport**: ứng dụng không nhận được kết quả đúng thời hạn. Nó **không chứng minh** Vault chưa xử lý request.

Ví dụ:

- `GET` để đọc một giá trị KV thường có thể thử lại khi gặp lỗi mạng ngắn hạn, miễn là có giới hạn số lần và backoff.
- Request cấp token, tạo dynamic credentials hoặc phát hành chứng chỉ PKI có thể đã thành công trên Vault dù client gặp read timeout khi đợi response. Thử lại thiếu kiểm soát có thể tạo thêm tài nguyên.
- Transit encrypt nếu được thực hiện lại có thể tạo ciphertext khác do cơ chế mã hóa; không giả định retry cho mọi POST sẽ cho cùng kết quả.

Trước khi retry, cần đánh giá **tính lặp an toàn (idempotency)** của API cụ thể, giới hạn số lần thử, backoff có jitter và ngân sách thời gian tổng. Không biến một lỗi Vault thành hàng trăm request retry đồng thời.

### 9.2. TTL và thời gian chờ HTTP là hai khái niệm khác

Token TTL, lease duration và thời điểm renew/revoke là **vòng đời credential**. Connect/read timeout chỉ tác động đến lúc HTTP client thực hiện request liên quan.

Ví dụ, nếu token chỉ còn 5 giây trước khi hết hạn mà một lần renew có read timeout 15 giây, request có thể kết thúc sau khi token đã hết hạn. Cần cấu hình lịch renewal đủ sớm và theo dõi lỗi renewal, thay vì nghĩ rằng tăng timeout sẽ kéo dài tuổi thọ token.

**Không sử dụng read timeout để thay cho TTL**, và không suy luận `HTTP 403` là lỗi timeout: lỗi HTTP với status code đã được Vault hoặc proxy trả lời thì cần phân tích xác thực, policy, namespace và trạng thái token tương ứng.

## 10. Chẩn đoán và quan sát lỗi

Một số biểu hiện thường gặp:

| Biểu hiện | Giai đoạn cần kiểm tra | Hành động gợi ý |
| --- | --- | --- |
| `UnknownHostException` | DNS | Kiểm tra hostname từ runtime ứng dụng và DNS nội bộ. |
| `ConnectException: Connection refused` | TCP/port | Kiểm tra listener, ingress/Service, port và firewall. |
| `connect timed out` | Kết nối TCP hoặc tầng kết nối của client | Kiểm tra routing, mạng, đích và connect timeout. |
| `Read timed out` | Chờ dữ liệu | Kiểm tra Vault latency, proxy/LB idle timeout, tác vụ chậm và read timeout. |
| Timeout khi đợi connection từ pool | Hàng chờ trong HTTP client | Kiểm tra pool size, số kết nối bận, request chưa được giải phóng và pool-acquire timeout. |
| `SSLHandshakeException` | TLS | Kiểm tra scheme, SAN hostname, CA chain và truststore. |
| HTTP `403` hoặc `404` | Response HTTP đã tới client | Kiểm tra token/policy, mount, KV version, đường dẫn API; đây không phải lỗi connect/read timeout. |
| HTTP `429`, `5xx` | Vault/proxy trả trạng thái lỗi | Xem rate limit/tải hệ thống và chính sách retry phù hợp từng API. |

Trong ứng dụng Spring, lỗi mạng cấp thấp có thể được đóng gói trong ngoại lệ của HTTP client hoặc Spring (ví dụ `ResourceAccessException`). Khi ghi log, giữ **root cause**, tên tác vụ và loại timeout để điều tra, nhưng **không log Vault token, secret, private key, request body nhạy cảm hoặc nguyên vẹn header xác thực**.

Các chỉ số hữu ích gồm thời gian gọi Vault p50/p95/p99, tần suất connect/read/pool timeout, số request đang chờ, số kết nối bận và rảnh, tỷ lệ request thất bại theo thao tác, cùng số lần renewal gần expiry. Quan sát chung các chỉ số này giúp phân biệt Vault chậm thật, pool thiếu kết nối và đường mạng có vấn đề.

## 11. Thử nghiệm và xác minh cấu hình

### 11.1. Kiểm tra đường mạng bằng CLI

Có thể dùng `curl` để kiểm tra endpoint trước khi chạy ứng dụng Java:

```bash
# Kiểm tra Vault HTTP API; dùng --cacert khi endpoint dùng CA nội bộ.
curl --verbose \
  --connect-timeout 3 \
  --max-time 12 \
  --cacert /etc/ssl/certs/vault-ca.pem \
  "https://vault.example.internal:8200/v1/sys/health"
```

`--connect-timeout` là giới hạn giai đoạn kết nối do **curl** áp dụng; `--max-time` là thời gian tối đa cho toàn bộ thao tác **curl**. Đây là ví dụ minh họa sự khác nhau giữa connect timeout và deadline tổng, **không** có nghĩa Spring Vault tự hiểu hai tham số curl đó.

Endpoint `/v1/sys/health` có thể trả mã HTTP khác `200` tùy tình trạng initialized/sealed/standby; việc nhận được HTTP response chứng minh đã liên lạc được tới một HTTP endpoint, không tự chứng minh Vault đang sẵn sàng cho mọi thao tác.

### 11.2. Kiểm thử ứng dụng theo từng loại sự cố

| Tình huống mô phỏng | Kỳ vọng cần xác nhận |
| --- | --- |
| Địa chỉ/port không truy cập được | Lỗi được báo và thread không chờ vô hạn; phân biệt refused với timeout. |
| Mock HTTP server cố tình chậm trả response | Read timeout được áp dụng trong client mà `VaultTemplate` thật sự sử dụng. |
| Connection pool đầy | Request chờ cấp kết nối có giới hạn riêng (nếu client hỗ trợ). |
| TLS hostname/CA sai | Lỗi xác minh TLS được giữ nguyên nguyên nhân; không tự động bỏ qua kiểm tra chứng chỉ. |
| Vault trả `403`, `404` hoặc `5xx` | Ứng dụng xử lý theo HTTP status/API, không phân loại nhầm thành read timeout. |
| Vault chậm trong quá trình login hoặc renew | Chính sách fail/retry và lịch token/lease hoạt động trong ngân sách thời gian. |

Khi mock response chậm, hãy dùng mock HTTP server có điều khiển delay cho một API Vault, sau đó thực hiện lời gọi qua **chính cấu hình client của ứng dụng** và kiểm tra loại ngoại lệ, thời gian quan sát, số lần retry và số kết nối được giải phóng. Kiểm tra tích hợp với Vault thật vẫn cần thiết cho các thao tác authentication, KV, Transit, PKI và renewal.

## 12. Ba tình huống tự suy luận

**Tình huống A — Vault từ chối TCP ngay:** Java gọi `https://vault.example.internal:8200`, port không lắng nghe và nhận `Connection refused` sau vài mili giây. Dù connect timeout là 3 giây, client không cần đợi đủ thời gian; timeout chỉ là **ngưỡng tối đa của giai đoạn tương ứng**, không phải độ trễ bắt buộc.

**Tình huống B — Kết nối thành công nhưng PKI xử lý lâu:** TCP và TLS đều hoàn tất, Vault chưa gửi dữ liệu phản hồi trong 11 giây trong khi read timeout là 10 giây. Request có thể thất bại do timeout đọc. Tăng connect timeout từ 3 lên 30 giây không giải quyết nguyên nhân; cần đo latency, điều chỉnh read timeout và đánh giá tác vụ PKI có thể đã hoàn tất ở phía Vault hay chưa.

**Tình huống C — Vault ổn nhưng pool hết connection:** Mười request đang chiếm mười connection của pool; request tiếp theo phải chờ. Connect timeout 3 giây không giới hạn hàng chờ này nếu pool có cơ chế acquire riêng. Cần thiết lập pool-acquire timeout, quản lý tài nguyên và xem lại tải đồng thời.

### Ghi nhớ

Khi cấu hình Spring Vault, hãy trả lời bốn câu hỏi: **đợi kết nối TCP tối đa bao lâu, đợi dữ liệu phản hồi tối đa bao lâu, đợi connection từ pool bao lâu và toàn bộ nghiệp vụ được phép mất bao lâu?** Dùng connect/read timeout của transport cho đúng hai giai đoạn đầu; bổ sung pool timeout hoặc deadline tổng khi kiến trúc cần. Cuối cùng, kiểm thử cả đường login, KV, Transit, PKI và token/lease để bảo đảm việc chờ và retry phù hợp với từng API.
