# Kiểm thử tải, rate limit và hành vi khi kho dữ liệu gián đoạn

Một Authorization Server phải giữ được các thuộc tính bảo mật khi lưu lượng tăng cao hoặc một thành phần lưu trữ mất kết nối. Kiểm thử hiệu năng vì thế cần đo thông lượng và độ trễ, đồng thời xác nhận hệ thống không cấp token sai, không bỏ qua giới hạn tốc độ và không làm lộ dữ liệu khi database hoặc kho token gặp sự cố.

Bài này tập trung vào Spring Authorization Server (SAS), với các endpoint thường chịu tải như token endpoint, authorization endpoint và JWK Set endpoint. Ví dụ giả định ứng dụng lưu client, authorization và consent trong database quan hệ; Redis có thể được dùng cho cache hoặc giới hạn tốc độ.

## 1. Xác định mục tiêu và ranh giới kiểm thử

Mỗi grant type có chi phí và đặc điểm khác nhau. Không nên gộp mọi luồng thành một con số tải duy nhất.

| Luồng | Endpoint chính | Điều cần quan sát |
|---|---|---|
| Client Credentials | POST /oauth2/token | Xác thực client, tạo và lưu access token |
| Authorization Code + PKCE | GET /oauth2/authorize, POST /oauth2/token | Session, consent, đổi authorization code |
| Refresh Token | POST /oauth2/token | Đọc authorization, xoay vòng refresh token nếu bật |
| JWKS | GET /oauth2/jwks | Phục vụ public key, cache và thời gian phản hồi |
| Introspection / Revocation | Endpoint tương ứng nếu được bật | Truy vấn trạng thái và thu hồi token |

Một đợt tải chỉ gồm JWKS có thể đạt thông lượng cao vì public key thường được cache; kết quả đó không đại diện cho khả năng cấp token khi mỗi yêu cầu phải đọc và ghi database.

Đặt mục tiêu đo lường trước khi chạy:

- **Thông lượng:** số yêu cầu thành công mỗi giây (RPS), tách theo endpoint và grant type.
- **Độ trễ:** p50, p95, p99; theo dõi thời gian ở ứng dụng và database.
- **Tỷ lệ lỗi:** phân biệt lỗi xác thực dự kiến, 429 do rate limit, lỗi 5xx và timeout dependency.
- **Tài nguyên:** CPU, heap, garbage collection, số thread, connection pool, kết nối database và Redis.
- **Tính đúng đắn:** không cấp token cho yêu cầu thất bại; không mất authorization/consent; token bị thu hồi được xử lý theo chính sách.
- **Khả năng phục hồi:** sau khi dependency hoạt động lại, hệ thống xử lý được tải bình thường.

SLO phải gắn với tải và môi trường cụ thể, ví dụ p95 của Client Credentials dưới ngưỡng đã thống nhất ở 300 RPS trong 15 phút. Không dùng một ngưỡng chung cho mọi hệ thống.

## 2. Thiết kế workload có thể lặp lại

### 2.1 Chuẩn bị dữ liệu

Tạo dữ liệu thử nghiệm riêng, có đủ client để tránh một client duy nhất làm sai lệch kết quả. Bao gồm client dùng Client Credentials, public client dùng Authorization Code + PKCE, client có ít và nhiều scope, cùng các cấu hình TTL khác nhau. Không đưa secret thật hoặc token production vào script tải.

### 2.2 Các pha tải

1. **Baseline:** tải thấp để xác nhận luồng đúng và lấy độ trễ nền.
2. **Ramp-up:** tăng tải từ từ để tìm điểm p95/p99 tăng mạnh.
3. **Sustained load:** giữ tải mục tiêu để phát hiện rò rỉ tài nguyên, pool cạn hoặc tích tụ dữ liệu.
4. **Spike:** tăng tải đột ngột để kiểm tra autoscaling và cơ chế bảo vệ.
5. **Stress:** tăng vượt tải dự kiến trong giới hạn môi trường thử nghiệm để xác định cách suy giảm.
6. **Recovery:** giảm tải và xác nhận độ trễ, tỷ lệ lỗi, connection pool trở lại bình thường.

Chạy từng workload riêng trước khi chạy hỗn hợp. Với workload hỗn hợp, ghi rõ tỷ trọng, chẳng hạn 60% Client Credentials, 25% refresh token, 10% authorization code exchange và 5% JWKS. Hãy thay tỷ trọng minh họa bằng số liệu sử dụng thực tế đã được ẩn danh.

### 2.3 Ví dụ k6 cho Client Credentials

Đoạn script sau minh họa cách tạo tải lên token endpoint. Cung cấp endpoint và thông tin client thử nghiệm qua biến môi trường của k6; không commit secret vào repository.

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';
import encoding from 'k6/encoding';

export const options = {
  stages: [
    { duration: '2m', target: 20 },
    { duration: '5m', target: 100 },
    { duration: '10m', target: 100 },
    { duration: '2m', target: 0 },
  ],
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
  },
};

const tokenUrl = __ENV.TOKEN_URL;
const clientId = __ENV.CLIENT_ID;
const clientSecret = __ENV.CLIENT_SECRET;
const scope = __ENV.SCOPE || 'api.read';
const basic = encoding.b64encode(clientId + ':' + clientSecret);

export default function () {
  const response = http.post(
    tokenUrl,
    'grant_type=client_credentials&scope=' + encodeURIComponent(scope),
    {
      headers: {
        Authorization: 'Basic ' + basic,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      tags: { endpoint: 'token', grant_type: 'client_credentials' },
    },
  );

  check(response, {
    'token endpoint returns 200': (r) => r.status === 200,
    'response contains access_token': (r) => {
      try { return Boolean(r.json('access_token')); } catch (_) { return false; }
    },
    'response contains token_type': (r) => {
      try { return Boolean(r.json('token_type')); } catch (_) { return false; }
    },
  });

  sleep(1);
}
~~~

Threshold trong ví dụ chỉ là ngưỡng minh họa. Đặt threshold theo SLO và cấu hình phần cứng của môi trường thử nghiệm. Điều chỉnh sleep và số virtual users tùy mục tiêu: đo throughput thuần hay mô phỏng hành vi client thực tế.

## 3. Kiểm thử rate limit

Rate limit bảo vệ Authorization Server khỏi client lỗi, credential stuffing, token harvesting và đột biến lưu lượng. Chính sách cần xác định khóa giới hạn, cửa sổ thời gian, mức giới hạn, phản hồi khi vượt ngưỡng và cách xử lý khi bộ đếm phân tán không sẵn sàng.

### 3.1 Chọn khóa giới hạn

| Endpoint / luồng | Khóa có thể áp dụng | Lưu ý |
|---|---|---|
| Token endpoint | Client ID đã xác thực; IP như lớp bảo vệ bổ sung | Tránh để một NAT lớn làm khóa toàn bộ client hợp lệ |
| Authorization endpoint | IP, session và tín hiệu rủi ro | Tránh khóa người dùng sau ít thao tác hợp lệ |
| JWKS | Cache ở proxy/CDN và giới hạn tổng thể | Không tính mỗi lần tải public key như một lần cấp token |
| Introspection | Client đã xác thực và quota theo resource server | Cache ngắn tùy yêu cầu thu hồi |
| Revocation | Client đã xác thực và IP | Giữ giới hạn đủ để xử lý sự cố thu hồi |

Với token endpoint, chỉ dùng IP có thể gây false positive khi nhiều dịch vụ đi qua cùng NAT. Chỉ dùng client ID cũng chưa đủ cho yêu cầu chưa xác thực hoặc tấn công phân tán. Có thể kết hợp giới hạn tổng theo IP trước xác thực với quota theo client sau xác thực.

### 3.2 Phản hồi khi vượt ngưỡng

Khi vượt giới hạn, trả HTTP 429 Too Many Requests. Nếu tính được thời gian chờ, gửi Retry-After theo định dạng HTTP hợp lệ. Phản hồi OAuth cần nhất quán với chính sách lỗi của hệ thống; không trả stack trace, trạng thái nội bộ hoặc thông tin bí mật.

Client cần tôn trọng Retry-After, dùng exponential backoff có jitter và phân biệt 429 với lỗi credential, cấu hình client hoặc lỗi tạm thời 5xx. Không retry vô hạn vì có thể tạo thêm tải.

Không retry mù quáng yêu cầu đổi authorization code: code thường chỉ dùng một lần. Nếu client không biết yêu cầu đã được xử lý hay chưa do timeout, cần quy trình phục hồi phù hợp với trạng thái authorization thay vì gửi lại code liên tục.

### 3.3 Bộ ca kiểm thử rate limit

Với mỗi chính sách, kiểm tra:

1. Ngay dưới giới hạn: yêu cầu hợp lệ vẫn được xử lý.
2. Đúng ngưỡng: hành vi khớp định nghĩa cửa sổ và thuật toán.
3. Vượt ngưỡng: trả 429 và không tạo token.
4. Hết thời gian chờ: quota phục hồi theo đúng cửa sổ.
5. Hai client khác nhau: quota client A không làm cạn quota client B nếu chính sách độc lập.
6. Nhiều instance: quota được thực thi nhất quán trên toàn cụm.
7. Đồng thời cao: không có race condition khiến số yêu cầu vượt quota đáng kể.
8. Redis gián đoạn: hành vi đúng với lựa chọn fail-open hoặc fail-closed đã công bố.

Nếu dùng Redis làm bộ đếm, thao tác tăng và đặt TTL cần nguyên tử. Tránh thực hiện INCR và EXPIRE như hai lệnh tách rời mà không có bảo đảm, vì instance có thể dừng giữa hai lệnh và để lại khóa không hết hạn. Có thể dùng Lua script hoặc primitive nguyên tử phù hợp với thư viện. Với token bucket hoặc sliding window, kiểm tra cả ranh giới cửa sổ và sai lệch đồng hồ giữa các node.

### 3.4 Vị trí thực thi

Có thể giới hạn ở API gateway, reverse proxy hoặc trong ứng dụng. Gateway thuận tiện cho giới hạn theo IP và bảo vệ sớm; ứng dụng có thể áp dụng quota theo client đã xác thực. Nếu dùng cả hai, định nghĩa rõ thứ tự và tổng hạn mức để tránh vô tình giới hạn hai lần.

Trong Spring Security, filter giới hạn tốc độ phải nằm đúng vị trí trong security filter chain và chỉ áp dụng cho endpoint dự kiến. Xác định cách lấy IP từ proxy tin cậy; không tin trực tiếp header X-Forwarded-For do client tùy ý gửi. Kiểm thử cả đường đi qua gateway và gọi trực tiếp vào ứng dụng nếu kiến trúc cho phép.

## 4. Kiểm thử khi kho dữ liệu gián đoạn

Spring Authorization Server có thể dùng nhiều loại lưu trữ. Lập bản đồ dữ liệu và dependency trước khi gây lỗi:

| Thành phần | Dữ liệu | Ảnh hưởng khi không truy cập được |
|---|---|---|
| RegisteredClientRepository | Client, grant type, redirect URI, scope | Không thể xác thực hoặc tải cấu hình client mới |
| OAuth2AuthorizationService | Authorization, access token, refresh token, authorization code | Không lưu được token hoặc không tra cứu được trạng thái |
| OAuth2AuthorizationConsentService | Consent của người dùng | Không thể đọc hoặc lưu consent |
| Database / transaction manager | Giao dịch và tính nhất quán | Giao dịch có thể rollback hoặc timeout |
| Redis / rate-limit store | Bộ đếm quota, cache | Mất khả năng áp quota phân tán hoặc cache |
| Key store / KMS | Khóa ký và khóa mã hóa | Có thể không ký hoặc giải mã được dữ liệu |

Một hệ thống có thể lưu khóa ký JWT ở local keystore nhưng lưu authorization trong database. Khả năng ký JWT không có nghĩa là có thể cấp token an toàn: nếu việc lưu authorization thất bại, token endpoint phải xử lý lỗi và không trả token mà hệ thống không thể quản lý theo chính sách. Nếu khóa ký nằm trong KMS, sự cố KMS có thể ảnh hưởng trực tiếp tới khả năng ký token.

### 4.1 Nguyên tắc fail-safe

Quyết định fail-open hay fail-closed cần được đưa ra riêng cho từng chức năng:

- **Cấp token:** nếu không thể ghi trạng thái bắt buộc hoặc xác nhận giao dịch thành công, không trả token thành công.
- **Đọc client và kiểm tra redirect URI:** không tự động chấp nhận cấu hình chưa xác minh khi repository không truy cập được.
- **Consent:** không bỏ qua yêu cầu consent chỉ vì kho consent lỗi.
- **Introspection:** nếu không thể xác minh trạng thái theo chính sách, không khẳng định token còn hiệu lực.
- **Revocation:** nếu không ghi được trạng thái thu hồi, báo lỗi phù hợp; không xác nhận thu hồi thành công giả.
- **Rate limit:** lựa chọn fail-open hoặc fail-closed theo rủi ro. Với endpoint cấp token nhạy cảm, fail-closed thường an toàn hơn, nhưng cần cân nhắc việc Redis lỗi làm ngừng cấp token trên diện rộng.
- **JWKS:** nếu public key hiện tại có thể được phục vụ an toàn từ cache và chưa hết hạn chính sách, có thể tiếp tục phục vụ cache trong thời gian ngắn. Không tạo hoặc công bố khóa không hợp lệ để che giấu lỗi kho khóa.

Không biến lỗi dependency thành phản hồi 200 với body rỗng hoặc token giả. Không trả chi tiết exception, SQL, hostname nội bộ hoặc credential cho client.

### 4.2 Ma trận fault injection

| Sự cố | Cách tạo trong môi trường thử nghiệm | Kết quả cần xác minh |
|---|---|---|
| Database từ chối kết nối | Dừng database hoặc chặn kết nối từ ứng dụng | Token flow lỗi có kiểm soát; không phát hành token không được lưu |
| Database tăng latency | Dùng proxy gây trễ hoặc giới hạn tài nguyên | Timeout hữu hạn; pool không cạn vô hạn; p99 được ghi nhận |
| Database mất kết nối giữa giao dịch | Ngắt kết nối trong lúc ghi authorization | Rollback hoặc trạng thái nhất quán; không có phản hồi thành công sai |
| Redis không sẵn sàng | Dừng node hoặc chặn cổng | Rate limit theo đúng chính sách dự phòng |
| Redis chậm | Thêm độ trễ mạng | Không giữ thread vô hạn; timeout và metric thể hiện rõ |
| KMS / key store lỗi | Dùng endpoint giả lập hoặc quyền thử nghiệm bị từ chối | Không ký bằng khóa ngoài chính sách; lỗi được phân loại |
| Một node ứng dụng mất kết nối | Chặn riêng đường mạng từ một instance | Các node khác hoạt động theo kiến trúc; load balancer loại node lỗi khi cần |

Ưu tiên fault injection ở môi trường cô lập. Bắt đầu với một dependency và một loại lỗi; sau đó mới kết hợp lỗi với tải. Ghi lại thời điểm bắt đầu, thời điểm khôi phục, số request đang chạy và số request thất bại để đối chiếu log, trace và metric.

### 4.3 Timeout, connection pool và transaction

Kiểm thử phải xác nhận timeout có giới hạn ở nhiều lớp: kết nối, đọc dữ liệu, lấy connection từ pool và timeout giao dịch. Nếu timeout ở ứng dụng dài hơn timeout ở load balancer, client có thể nhận lỗi trước khi ứng dụng biết giao dịch đã hoàn tất hay chưa. Nếu pool cho phép chờ vô hạn, database chậm có thể giữ toàn bộ request thread.

Theo dõi số connection đang dùng/nhàn rỗi/đang chờ, thời gian chờ lấy connection, thời gian truy vấn, số truy vấn timeout, transaction rollback, request timeout, thread pool và hàng đợi request.

Circuit breaker có thể ngăn ứng dụng liên tục gọi dependency đang lỗi. Xác định rõ exception nào được tính là lỗi, thời gian mở, số request thử lại và cách phục hồi. Tránh retry thao tác ghi không có bảo đảm idempotency vì có thể tạo trạng thái khó đoán khi kết quả giao dịch không rõ.

## 5. Xây dựng kiểm thử tích hợp

Kiểm thử đơn vị xác nhận cách ứng dụng phản ứng với exception giả lập, nhưng không chứng minh được hành vi connection pool, transaction và mạng. Kết hợp ba lớp:

- **Unit test:** xác minh chính sách fail-open/fail-closed, mapping lỗi và quy tắc rate limit.
- **Integration test:** dùng database/Redis thật trong container để kiểm tra repository, transaction và quota đa instance.
- **Load/fault test:** tạo tải qua HTTP trong khi chủ động làm chậm hoặc ngắt dependency.

Có thể dùng Testcontainers để chạy database và Redis cùng loại với môi trường triển khai. Để mô phỏng lỗi mạng và độ trễ, đặt Toxiproxy giữa ứng dụng và dependency. Bài kiểm thử cần điều khiển được thời điểm bật/tắt proxy và luôn khôi phục dependency sau assertion.

Một kiểm thử cấp token khi database ngừng hoạt động nên xác minh:

1. Gửi yêu cầu Client Credentials hợp lệ khi database hoạt động và xác nhận token được cấp.
2. Chặn kết nối database.
3. Gửi lại yêu cầu và xác nhận nhận lỗi phù hợp, có thời gian phản hồi hữu hạn.
4. Xác nhận response không chứa access token.
5. Xác nhận log không chứa client secret hoặc token.
6. Khôi phục database và gửi yêu cầu mới.
7. Xác nhận hệ thống hoạt động lại và không cần restart thủ công.
8. Kiểm tra dữ liệu authorization để bảo đảm không có bản ghi dở dang.

Với Redis, chạy nhiều instance ứng dụng cùng dùng một store để xác nhận quota là toàn cụm. Nếu mỗi instance dùng bộ đếm cục bộ, tổng request cho phép có thể tăng theo số instance. Ví dụ quota 100 request/phút trên mỗi node với ba node có thể vô tình thành 300 request/phút.

## 6. Quan sát và chẩn đoán kết quả

Kết quả kiểm thử phải cho biết hệ thống chậm ở đâu và vì sao. Dùng metric có nhãn giới hạn cardinality; không đưa access token, refresh token, authorization code, client secret, session ID hoặc user ID vào nhãn metric.

| Nhóm | Metric / dữ liệu |
|---|---|
| HTTP | Request count, status code, latency histogram theo endpoint và grant type |
| OAuth | Số lần cấp token, lỗi grant, lỗi client authentication, số lần refresh/revocation |
| Rate limit | Request bị giới hạn, lỗi kết nối store, thời gian thao tác bộ đếm |
| Database | Pool active/idle/pending, query latency, timeout, rollback |
| Redis | Command latency, connection error, timeout, memory và eviction |
| JVM | Heap, GC pause, CPU, thread và request queue |
| Resilience | Circuit breaker state, retry count, dependency health |

Log nên có correlation ID để nối request với trace. Ghi loại grant, endpoint, kết quả và mã lỗi nội bộ đã chuẩn hóa; tránh ghi credential hoặc token. Với OAuth error, phân biệt lỗi nghiệp vụ như invalid_client, invalid_grant, invalid_scope với lỗi dependency nội bộ. Không để dashboard gộp 429, 4xx xác thực và 5xx thành một tỷ lệ lỗi duy nhất.

Khi p99 tăng, đối chiếu trace token endpoint với thời gian xác thực client, truy vấn repository, ghi authorization và ký token. Nếu thời gian chờ connection pool tăng cùng database latency, tăng số thread ứng dụng thường không giải quyết được nguyên nhân và có thể làm tình hình xấu hơn.

## 7. Các tình huống kiểm thử đầu cuối

| ID | Kịch bản | Kết quả mong đợi |
|---|---|---|
| ST-01 | Tải Client Credentials ở baseline | Token hợp lệ; latency và error rate nằm trong SLO |
| ST-02 | Tăng dần tải token endpoint | Xác định điểm bão hòa; tài nguyên không tăng trưởng vô hạn |
| ST-03 | Tải đồng thời từ nhiều client | Quota và dữ liệu client độc lập |
| ST-04 | Vượt quota token endpoint | 429; không tạo token; có thông tin retry phù hợp |
| ST-05 | Nhiều node cùng áp quota | Tổng quota toàn cụm đúng chính sách |
| ST-06 | Redis ngừng hoạt động | Hành vi fail-open/fail-closed đúng thiết kế |
| ST-07 | Database ngừng trước yêu cầu cấp token | Lỗi có kiểm soát; không trả token |
| ST-08 | Database ngắt giữa lúc ghi | Không có trạng thái authorization dở dang gây cấp token sai |
| ST-09 | Database chậm dưới tải | Timeout hữu hạn; pool và thread phục hồi |
| ST-10 | Khôi phục database và Redis | Request thành công trở lại; không cần restart ngoài dự kiến |
| ST-11 | JWKS khi database lưu authorization lỗi | JWKS hoạt động theo nguồn khóa riêng; không nhầm khả năng phục vụ khóa với khả năng cấp token |
| ST-12 | Tải hỗn hợp kèm fault injection | SLO, giới hạn bảo vệ và hành vi suy giảm vẫn đúng |

ST-11 chỉ phù hợp nếu khóa ký được quản lý độc lập với database authorization. Điều chỉnh kịch bản theo kiến trúc thực tế.

## 8. Quy trình thực hiện một đợt kiểm thử

1. Ghi lại phiên bản ứng dụng, cấu hình Spring, cấu hình pool, loại database/Redis, số instance và cấu hình gateway.
2. Chuẩn bị client và dữ liệu thử nghiệm; xác nhận luồng OAuth hoạt động ở tải thấp.
3. Chạy baseline cho từng grant type và endpoint.
4. Chạy ramp-up và sustained load; lưu kết quả thô, dashboard và trace mẫu.
5. Bật rate limit; chạy lại ở dưới ngưỡng, tại ngưỡng và vượt ngưỡng.
6. Chạy workload nhiều instance để kiểm tra quota phân tán.
7. Chạy fault injection từng dependency ở tải thấp, rồi lặp lại ở tải mục tiêu.
8. Khôi phục dependency; xác nhận dữ liệu, quota, connection pool và latency trở về bình thường.
9. So sánh kết quả với SLO; ghi rõ tải, môi trường, cấu hình và mọi sai khác.
10. Tạo hành động khắc phục có người phụ trách và tiêu chí đo lại.

Không so sánh hai lần chạy nếu khác cấu hình phần cứng, số instance, dataset, phiên bản ứng dụng hoặc tỷ trọng workload mà không ghi rõ khác biệt. Lưu script, tham số chạy và phiên bản dữ liệu giả lập để tái hiện kết quả.

## 9. Tiêu chí hoàn thành

Một đợt kiểm thử đạt yêu cầu khi:

- Mỗi endpoint và grant type quan trọng có baseline và kết quả tải riêng.
- SLO về latency, throughput và error rate được đo trong workload đã định nghĩa.
- Rate limit đúng ở dưới ngưỡng, tại ngưỡng, vượt ngưỡng và khi chạy nhiều instance.
- Sự cố database, Redis và kho khóa được mô phỏng; phản hồi đúng chính sách đã chọn.
- Không có token được trả về khi thao tác lưu trữ bắt buộc thất bại.
- Timeout và pool có giới hạn; ứng dụng không bị treo vô thời hạn khi dependency chậm.
- Sau khi dependency phục hồi, hệ thống hoạt động lại và dữ liệu vẫn nhất quán.
- Log, metric và trace đủ để xác định nguyên nhân mà không làm lộ credential hoặc token.
- Kết quả có thể tái hiện từ script, cấu hình và dữ liệu thử nghiệm đã lưu.

Kiểm thử tải và fault injection giúp xác định giới hạn vận hành của Authorization Server. Dùng kết quả để điều chỉnh quota, timeout, connection pool, cache, số instance và SLO; sau mỗi thay đổi đáng kể, chạy lại workload để xác nhận tác động.

