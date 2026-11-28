# Đo chuẩn bằng tải đại diện cho đọc, ghi, đăng nhập và hết hạn

Benchmark Spring Session cần mô phỏng cách người dùng thực sự tạo, sử dụng và kết thúc phiên. Một bài test chỉ gửi nhiều request GET tới một endpoint không phản ánh đầy đủ chi phí của session: request đọc có thể vẫn cập nhật `lastAccessedTime`, đăng nhập phải xác thực credentials và lưu `SecurityContext`, request ghi có thể serialize attributes lớn, còn hết hạn liên quan tới TTL hoặc tác vụ cleanup của backend.

Mục tiêu của đo chuẩn là trả lời được: hệ thống phục vụ được bao nhiêu người dùng đồng thời với tỷ lệ đọc/ghi/đăng nhập nào, latency ở percentile cao ra sao, backend session chịu tải thế nào, và khi tăng số node hoặc thay đổi cấu hình thì giới hạn hiệu năng nằm ở đâu.

## 1. Xác định câu hỏi benchmark trước khi chạy

Một benchmark hữu ích bắt đầu bằng giả thuyết hoặc câu hỏi đo lường cụ thể. Ví dụ:

- Với 2.000 session đang hoạt động, repository Redis/JDBC xử lý được bao nhiêu request mỗi giây?
- Khi mỗi session chứa `SecurityContext` và một số attributes nghiệp vụ, p95/p99 của lookup và save là bao nhiêu?
- Đăng nhập đồng thời tạo tải CPU từ password hashing tới mức nào, và session store chiếm bao nhiêu thời gian?
- Khi một nhóm lớn session hết hạn cùng lúc, Redis expiration hoặc JDBC cleanup có làm tăng latency của request đang hoạt động không?
- Tăng từ hai lên bốn application instances có cải thiện throughput hay chỉ làm database/Redis quá tải?
- Cấu hình serializer, flush/save mode hoặc connection pool nào làm thay đổi chi phí ghi session?

Không gộp mọi câu hỏi vào một con số “requests per second”. Mỗi phép đo cần nêu rõ workload, kích thước dữ liệu, số session, topology, thời gian chạy, mức lỗi và điều kiện đạt SLA.

## 2. Tách các loại thao tác cần đo

Ít nhất nên có bốn nhóm workload riêng, sau đó mới ghép chúng thành một luồng người dùng tổng hợp.

| Workload | Hoạt động | Chi phí cần quan sát |
|---|---|---|
| Đọc session | Request mang cookie, repository tìm session và ứng dụng đọc attributes | Lookup latency, deserialize, cập nhật last access, write phát sinh nếu có |
| Ghi session | Thêm/sửa/xóa attributes và lưu session | Serialize, bytes ghi, Redis command hoặc SQL update, transaction latency |
| Đăng nhập | Xác thực credentials, tạo/đổi session ID, lưu `SecurityContext`, phát cookie | Password hashing, authentication provider, session creation/save, cookie/redirect |
| Hết hạn | Để session idle quá timeout, kiểm tra bị từ chối, dọn dữ liệu vật lý | Expiration detection, TTL, cleanup throughput, event delay và ảnh hưởng tới request khác |

Một endpoint “đọc” không nhất thiết là read-only đối với repository. Khi Spring Session truy cập session, `lastAccessedTime` có thể được cập nhật và metadata có thể phải được ghi lại. Hành vi cụ thể phụ thuộc repository, flush mode, save mode và phiên bản. Vì vậy, phải đo số lần đọc và ghi backend thực tế thay vì suy luận từ HTTP method GET.

## 3. Xây dựng workload đại diện người dùng

Benchmark nên mô tả một phiên người dùng từ lúc đăng nhập tới khi kết thúc:

1. Người dùng mở ứng dụng và đăng nhập.
2. Trình duyệt giữ cookie session ID.
3. Người dùng thực hiện nhiều request đọc hồ sơ, trang chính hoặc dữ liệu cá nhân.
4. Một phần request cập nhật giỏ hàng, tùy chọn hoặc trạng thái phiên.
5. Người dùng có thể logout hoặc ngừng hoạt động cho tới khi session hết hạn.

Tỷ lệ giữa các hoạt động phải lấy từ log/metrics đã được ẩn danh hoặc giả định sản phẩm được xác nhận. Ví dụ, nếu một lần đăng nhập tạo ra hàng chục request đọc và vài request ghi, benchmark cần giữ tỷ lệ gần như vậy. Không chọn tỷ lệ 50% login chỉ vì dễ tạo tải; đăng nhập có password hashing thường có profile CPU khác với request đọc session.

Hãy ghi rõ:

- Số người dùng ảo đồng thời và số session đang tồn tại.
- Tỷ lệ đăng nhập mới, session đã đăng nhập, đọc, ghi, logout và idle expiry.
- Think time giữa các request.
- Kích thước session attribute nhỏ, trung bình và lớn.
- Số lượng attributes và kiểu dữ liệu thực tế.
- Tỷ lệ session hoạt động lại so với session mới.
- Tỷ lệ request tới từng application instance.
- Tỷ lệ session hết hạn trong mỗi phút.

Mỗi virtual user cần có cookie jar riêng hoặc cơ chế lưu cookie riêng. Nếu mọi virtual user dùng cùng session ID, kết quả sẽ bị méo bởi contention trên một session và không đại diện cho hàng nghìn người dùng.

## 4. Chuẩn bị dữ liệu session thực tế

Session benchmark cần gần với dữ liệu production nhưng không được dùng cookie, password, principal hoặc attributes thật của người dùng.

Tạo các nhóm dữ liệu giả:

| Nhóm | Nội dung giả lập | Mục đích |
|---|---|---|
| Nhỏ | Principal ID giả, vài authority, locale | Đo chi phí tối thiểu |
| Trung bình | Security context giả lập phù hợp, cart ID, preferences, feature flags | Gần với phiên thông thường |
| Lớn | Nhiều attributes hoặc payload DTO lớn có version | Tìm giới hạn serialization và network |
| Nhiều thuộc tính | Nhiều key nhỏ, tổng byte có thể không lớn | Đo overhead quản lý attribute và SQL/Redis operations |

Không lưu entity graph lớn hoặc dữ liệu nghiệp vụ không cần thiết chỉ để tạo payload benchmark. Nếu production đang lưu object lớn, benchmark phải phản ánh điều đó và kết quả nên dẫn tới quyết định giảm payload hoặc chuyển dữ liệu sang kho nghiệp vụ.

Đo cả số byte serialized và số attribute. Hai session có cùng tổng kích thước nhưng khác số lượng attributes có thể tạo số thao tác backend khác nhau, đặc biệt khi repository lưu attribute riêng lẻ.

## 5. Cố định môi trường để so sánh có ý nghĩa

Một lần chạy chỉ có giá trị so sánh khi các yếu tố quan trọng được ghi lại và giữ ổn định.

**Application:** cùng build, JDK, Spring Boot, Spring Session, Spring Security, serializer, cấu hình timeout và logging. Ghi lại CPU/memory limit và số instance.

**Session store:** cùng loại Redis/JDBC, phiên bản, topology, persistence, eviction policy, schema/index, connection pool và network path như môi trường mục tiêu.

**Load generator:** đủ CPU/network để không trở thành bottleneck. Nếu generator quá tải, số request phát ra thấp hơn cấu hình và latency đo được có thể sai lệch.

**Network:** ghi lại RTT giữa application và Redis/database, TLS, proxy và load balancer. Không so sánh một lần chạy local loopback với một lần chạy qua nhiều subnet rồi kết luận khác biệt do serializer.

**Dữ liệu:** dùng cùng số session hoạt động, payload distribution, TTL và trạng thái warm/cold giữa các lần so sánh.

Không chạy benchmark cạnh một workload không kiểm soát trên cùng Redis/database. Nếu backend được dùng chung, phải đo và ghi lại tải nền.

## 6. Đo riêng chi phí repository và chi phí endpoint

Hai phép đo bổ sung cho nhau:

- **Repository-level benchmark:** gọi thao tác tạo, tìm, lưu và xóa session qua repository trong môi trường kiểm thử được kiểm soát. Nó giúp cô lập serializer, backend và connection pool.
- **End-to-end benchmark:** gửi HTTP qua load balancer, security filters và ứng dụng như người dùng thật. Nó đo toàn bộ chi phí gồm TLS, authentication, controller, session filter, repository và response.

Repository-level benchmark không thay thế end-to-end vì có thể bỏ qua cookie, filter, SecurityContext và logic cập nhật last access. End-to-end không luôn chỉ ra bottleneck nằm ở đâu. Dùng cả hai để phân rã thời gian.

Với đăng nhập, nên đo riêng:

1. Authentication/password verification không lưu session (trong test cô lập).
2. Tạo session và lưu SecurityContext bằng repository.
3. Toàn bộ POST login thực tế qua Spring Security.

Password encoder có thể tiêu tốn CPU đáng kể. Nếu chỉ đo login end-to-end, không thể kết luận toàn bộ latency là chi phí của Spring Session.

## 7. Chọn mô hình tải: số người dùng hay tốc độ đến

Hai mô hình phổ biến trả lời những câu hỏi khác nhau:

| Mô hình | Cách tạo tải | Phù hợp |
|---|---|---|
| Closed workload | Giữ một số virtual users; mỗi user gửi request rồi chờ think time | Mô phỏng tập người dùng đồng thời có hành vi tương tác |
| Open workload | Phát request theo arrival rate định trước, không giảm tốc độ chỉ vì hệ thống phản hồi chậm | Kiểm tra khả năng chịu tốc độ đến ổn định và phát hiện queueing/saturation |

Closed workload có thể tự giảm tốc độ khi server chậm vì mỗi VU phải chờ response trước khi gửi request kế tiếp. Điều này đôi khi che giấu overload. Open workload giúp kiểm tra hệ thống ở arrival rate mục tiêu, nhưng cần load generator đủ mạnh và cấu hình đủ VU để giữ tốc độ đó.

Trong k6, `ramping-vus` thường dùng cho closed workload; `constant-arrival-rate` hoặc `ramping-arrival-rate` dùng cho open workload. Gatling và JMeter có các mô hình tương đương. Chọn mô hình theo câu hỏi, không chỉ theo công cụ quen thuộc.

## 8. Ví dụ k6 cho luồng session đã đăng nhập

Ví dụ sau mô phỏng mỗi VU đăng nhập một lần, sau đó lặp lại request đọc và ghi bằng cookie mà VU nhận được. k6 giữ cookie jar riêng cho từng VU. Endpoint và payload cần điều chỉnh theo ứng dụng thật.

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'https://test.example.internal';
let authenticated = false;

export const options = {
  scenarios: {
    authenticated_sessions: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '2m', target: 50 },
        { duration: '5m', target: 200 },
        { duration: '5m', target: 200 },
        { duration: '2m', target: 0 }
      ]
    }
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    'http_req_duration{operation:read}': ['p(95)<300'],
    'http_req_duration{operation:write}': ['p(95)<500']
  }
};

export default function () {
  if (!authenticated) {
    const login = http.post(
      `${BASE_URL}/login`,
      {
        username: __ENV.TEST_USERNAME,
        password: __ENV.TEST_PASSWORD
      },
      { tags: { operation: 'login' } }
    );

    const loginOk = check(login, {
      'login accepted': (r) => r.status === 200 || r.status === 302
    });

    if (!loginOk) {
      return;
    }
    authenticated = true;
  }

  const read = http.get(`${BASE_URL}/api/session/profile`, {
    tags: { operation: 'read' }
  });
  check(read, { 'profile readable': (r) => r.status === 200 });

  const write = http.post(
    `${BASE_URL}/api/session/preferences`,
    JSON.stringify({ theme: 'dark', locale: 'vi' }),
    {
      headers: { 'Content-Type': 'application/json' },
      tags: { operation: 'write' }
    }
  );
  check(write, { 'preferences saved': (r) => r.status === 200 || r.status === 204 });

  sleep(1);
}
```

Các ngưỡng p95 trong ví dụ chỉ là giá trị minh họa, không phải SLA chung cho Spring Session. Chọn ngưỡng từ yêu cầu sản phẩm và baseline hiện tại.

Đối với form login Spring Security có CSRF, script cần GET trang login, lấy CSRF token và cookie liên quan trước khi POST credentials. Endpoint test không được bỏ qua authentication path nếu mục tiêu là đo login production. Dùng pool tài khoản kiểm thử riêng; không để hàng trăm VU cập nhật cùng một tài khoản hoặc cùng một session. Không đặt credentials thật trong source; truyền qua secret/env được quản lý và che khỏi log.

Biến `authenticated` ở đây giữ trạng thái trong vòng đời VU. Script mẫu không tự đăng nhập lại sau khi session hết hạn; hãy thêm logic re-login nếu workload cần mô phỏng hành vi đó hoặc chạy kịch bản expiration riêng.

## 9. Đo workload đăng nhập riêng

Đăng nhập có profile khác với request đọc session. Một login có thể bao gồm:

- Đọc và xác minh credentials.
- Password hashing/verification.
- Gọi user store hoặc identity provider.
- Session fixation protection và đổi session ID.
- Tạo session, ghi `SecurityContext` và phát cookie.
- Redirect hoặc trả response sau xác thực.

Tạo một scenario riêng để tăng tốc độ login theo từng nấc. Dùng tài khoản kiểm thử độc lập, tránh lockout và tránh contention trên một user record. Đo tỷ lệ login thành công, p50/p95/p99, CPU ứng dụng, latency user store và số session được tạo.

Không benchmark password hashing bằng mật khẩu yếu hoặc encoder khác production rồi dùng kết quả để dự đoán production. Giữ thuật toán và cost factor tương ứng với cấu hình thật, nhưng chỉ dùng credentials giả.

## 10. Đo workload đọc và ghi

### Đọc

Để đo read path:

1. Tạo trước một tập session đủ lớn và phân bố cookie theo VU.
2. Mỗi VU dùng cookie của chính nó để gọi endpoint cần session.
3. Giữ tỷ lệ session hit/miss gần với thực tế.
4. Ghi nhận session payload size và số attributes.
5. Đo repository lookup, deserialize và mọi write metadata do last access.

Không chỉ đo một session duy nhất vì cache nóng và contention trên cùng key có thể làm kết quả quá lạc quan hoặc không đại diện.

### Ghi

Đo riêng các kiểu cập nhật:

- Thay một attribute nhỏ.
- Thay nhiều attributes.
- Cập nhật attribute lớn.
- Xóa attribute.
- Tạo session mới và lưu lần đầu.

Với Spring Session, cấu hình save/flush ảnh hưởng số thao tác backend và thời điểm ghi. Hãy ghi lại `SaveMode`/`FlushMode` nếu repository có hỗ trợ và so sánh trong các lần chạy tách biệt. Không thay đổi nhiều cấu hình cùng lúc vì sẽ không biết yếu tố nào tạo ra khác biệt.

## 11. Đo hết hạn và cleanup

Hết hạn cần ít nhất hai phép đo khác nhau:

1. **Expiration correctness:** session idle quá timeout có bị từ chối khi request tiếp theo tới không?
2. **Physical cleanup:** dữ liệu hết hạn được xóa khỏi Redis/JDBC nhanh tới đâu và chi phí cleanup ảnh hưởng workload đang hoạt động thế nào?

Với Redis, theo dõi TTL/expiration và event/cleanup behavior của repository. Redis có thể dùng lazy và active expiration; thời điểm key bị xóa vật lý không nhất thiết trùng chính xác deadline idle timeout.

Với JDBC, đo `cleanupCron`, số hàng bị xóa, thời lượng query, lock wait và tác động tới connection pool. Cleanup thường chạy theo lịch; session phải bị coi là hết hạn logic ngay cả khi hàng vật lý chưa được xóa.

Kịch bản test expiration:

- Dùng timeout ngắn trong môi trường test riêng, ví dụ 30 giây.
- Đăng nhập và lưu session.
- Không gửi request làm mới last-access trong thời gian chờ.
- Chờ vượt idle timeout một khoảng biên an toàn.
- Gửi request protected và xác nhận session không còn được chấp nhận.
- Quan sát thời điểm dữ liệu được cleanup riêng, không yêu cầu nó bị xóa đúng mili giây timeout.

Không dùng timeout rất ngắn trong benchmark tổng hợp nếu điều đó làm thay đổi workload theo cách không giống production. Kịch bản expiry nên tách riêng hoặc dùng tỷ lệ expiry được xác định trước.

## 12. Đo tác động của một đợt hết hạn lớn

Một hệ thống có thể có nhiều session cùng được tạo trong một khoảng thời gian, ví dụ sau một đợt campaign hoặc sau khi tăng traffic. Khi timeout đồng loạt, backend có thể phát sinh lượng expiration/cleanup lớn.

Thiết kế thử nghiệm:

1. Tạo một cohort session với thời điểm tạo và timeout được kiểm soát.
2. Giữ một cohort session khác vẫn đang hoạt động làm tải nền.
3. Để cohort đầu hết hạn trong một khoảng thời gian ngắn.
4. Đo cleanup throughput, số key/row hết hạn, event delay và tài nguyên backend.
5. Đồng thời đo p95/p99 của request đọc/ghi trên cohort còn hoạt động.
6. Lặp lại với số session và độ phân tán thời gian hết hạn khác nhau.

Mục tiêu là phát hiện expiration storm, cleanup query quá lớn, lock contention hoặc Redis CPU spike. Không chỉ đo tổng thời gian xóa hết session; cần đo tác động tới người dùng vẫn đang hoạt động.

## 13. Warm-up, ramp-up và thời gian đo ổn định

Một lần chạy benchmark nên chia thành các pha:

| Pha | Mục tiêu | Hành động |
|---|---|---|
| Baseline | Biết hệ thống nhàn rỗi | Ghi CPU, memory, pool, Redis/DB metrics khi chưa có tải |
| Warm-up | Nạp class, JIT, connection pool và cache cần thiết | Chạy tải thấp, không dùng phần này làm kết quả chính |
| Ramp-up | Tăng tải từ thấp lên mục tiêu | Tăng VU hoặc arrival rate theo từng nấc |
| Steady state | Đo khi tải ổn định | Giữ tải đủ lâu để thấy GC, pool, cleanup và queue behavior |
| Stress | Tìm giới hạn và failure mode | Tăng vượt tải mục tiêu có kiểm soát |
| Recovery | Đánh giá hệ thống sau khi giảm tải | Giảm tải về thấp/0 và đo thời gian backlog, pool, CPU phục hồi |

Không chỉ chạy 30 giây rồi kết luận. Một số vấn đề chỉ xuất hiện khi session population tăng, Redis memory tiến gần maxmemory, connection pool bị giữ lâu hoặc cleanup chạy theo cron.

Chạy mỗi cấu hình nhiều lần, giữ cùng dữ liệu và điều kiện. Ghi median của các lần chạy cùng với độ biến thiên; nếu kết quả dao động lớn, tìm nguyên nhân trước khi so sánh cấu hình.

## 14. Chỉ số cần thu thập

### 14.1. Từ load generator

- Throughput: requests/second và iterations/second.
- Latency: p50, p90, p95, p99 và max.
- Error rate: HTTP status, timeout, connection error và check failure.
- VU/arrival rate thực tế so với mục tiêu.
- Data sent/received và thời gian DNS/TLS/connect nếu công cụ hỗ trợ.

Không chỉ nhìn average latency. Một hệ thống có average thấp nhưng p99 rất cao vẫn có thể tạo trải nghiệm xấu khi nhiều request chờ backend.

### 14.2. Từ application

- CPU, heap, non-heap, garbage collection và allocation rate.
- Số thread, request queue và connection pool.
- Thời gian authentication/password hashing.
- Session repository lookup/save/delete latency và error count.
- Serialize/deserialize time và payload bytes.
- Số session active/created/expired nếu có metric đáng tin cậy.
- Request latency theo endpoint và operation tag.

### 14.3. Từ Redis

- `used_memory`, `maxmemory`, fragmentation và `evicted_keys`.
- `expired_keys`, command rate, CPU và network throughput.
- Client connections, blocked clients và latency distribution.
- Replication lag/failover events nếu có replica.
- Slow log hoặc latency monitor phù hợp với môi trường.

### 14.4. Từ JDBC database

- Query latency, transaction rate và rows affected.
- Connection pool active/idle/pending và acquisition time.
- Lock waits, deadlocks, rollback và transaction log pressure.
- CPU, I/O, buffer/cache hit và dung lượng bảng/index.
- Execution plan của truy vấn lookup/cleanup.

Đồng bộ timestamp giữa load generator, application và backend để đối chiếu spike theo thời gian. Không ghi session ID, cookie hoặc payload nhạy cảm vào logs/metrics.

## 15. Đo latency theo từng operation

Đừng gộp login, read, write và expiry thành một histogram duy nhất. Gắn tag hoặc metric riêng cho mỗi operation:

| Operation | Thời điểm bắt đầu/kết thúc nên đo |
|---|---|
| Login | Từ lúc gửi credentials tới response authentication hoàn tất |
| Session read | Từ lúc request vào tới lúc session được repository khôi phục; nếu cần, đo riêng backend lookup |
| Session write | Từ lúc bắt đầu cập nhật tới khi repository xác nhận lưu xong |
| Expiration detection | Từ request sau idle timeout tới kết quả session bị từ chối |
| Physical cleanup | Thời gian một chu kỳ cleanup và số session được xóa |
| Logout | Từ request logout tới khi repository xác nhận invalidation và response hoàn tất |

End-to-end latency và repository-only latency không giống nhau. Ví dụ login có thể chậm do password encoder, user database hoặc external identity provider. Hãy dùng tracing hoặc instrumentation để tách các span, nhưng tránh thêm instrumentation nặng chỉ trong một cấu hình benchmark.

## 16. So sánh Redis và JDBC công bằng

Khi so sánh Redis với JDBC, dùng cùng:

- Application build và session attributes.
- Số session đang hoạt động và số request.
- Cookie, timeout, serializer/converter semantics.
- Số application instances và CPU/memory limits.
- Network topology và khoảng cách tới backend tương đương nhất có thể.
- Persistence/replication/HA requirements được ghi rõ.
- Load generator và thời gian warm-up/steady-state.

Không so sánh Redis đơn node không persistence với JDBC cluster có HA rồi chỉ nhìn latency. Đó là hai cấu hình có mức đảm bảo và chi phí khác nhau. Báo cáo phải tách hiệu năng thuần với mức durability/availability được cung cấp.

JDBC thường có transaction và index/query behavior; Redis có command latency và memory/eviction behavior. Chỉ số nội bộ khác nhau, nhưng tiêu chí người dùng như throughput, p95/p99, lỗi và khả năng giữ session qua sự cố vẫn có thể so sánh.

## 17. Các yếu tố cấu hình nên thay đổi có kiểm soát

Mỗi lần chạy chỉ thay một nhóm yếu tố:

- Session payload size và số attributes.
- Số active sessions và tốc độ tạo session mới.
- Tỷ lệ read/write/login/logout.
- Idle timeout và tốc độ session expiry.
- Redis serializer hoặc JDBC conversion strategy.
- Spring Session `FlushMode`/`SaveMode` khi repository hỗ trợ.
- Redis maxmemory/eviction policy hoặc JDBC index/cleanup schedule.
- Application instance count.
- Redis connection/client pool hoặc JDBC connection pool.
- Compression/encryption nếu production có sử dụng.

Ghi lại cấu hình chính xác và version. Không thay serializer, pool size và số node cùng lúc rồi gán toàn bộ cải thiện cho một thay đổi.

## 18. Phát hiện bottleneck từ kết quả

| Dấu hiệu | Bottleneck có thể | Bước xác minh |
|---|---|---|
| App CPU cao, Redis/DB nhàn | Password hashing, serialization, GC hoặc business logic | Profile CPU, allocation và tách login/session spans |
| Redis CPU/latency cao | Command rate, payload lớn, network hoặc Redis shared workload | Kiểm tra command stats, slow log, payload bytes và network |
| JDBC pool pending tăng | Pool nhỏ, query chậm hoặc DB không đủ connection | Xem acquisition time, query plan và DB max connections |
| p99 tăng nhưng p50 ổn | Queueing, lock wait, GC pause hoặc backend tail latency | Đối chiếu traces, GC logs, DB lock và Redis latency |
| Login chậm hơn read nhiều | Password hashing hoặc identity provider | Đo authentication riêng và giữ cost factor production |
| Read path vẫn tạo nhiều writes | Last-access update, flush mode hoặc save policy | Kiểm tra repository operations và SQL/Redis command trace |
| Expiry làm request đang hoạt động chậm | Cleanup/expiration storm, lock hoặc CPU cạnh tranh | Tách cohort expiry và đo cleanup impact |
| Throughput không tăng khi thêm node | Backend store đã bão hòa hoặc load generator giới hạn | So sánh app CPU, backend capacity và generator utilization |
| Session miss tăng khi tải cao | Backend timeout, eviction, serialization lỗi hoặc cookie issue | Phân biệt lookup miss với backend error và deserialize failure |

Không tăng pool size một cách máy móc. Pool lớn hơn có thể làm database quá tải do số connection tổng cộng từ mọi instance tăng lên. Tương tự, thêm application node có thể tăng áp lực lên Redis/JDBC thay vì cải thiện throughput.

## 19. Lập báo cáo benchmark có thể lặp lại

Mỗi báo cáo nên có các trường:

| Nhóm | Thông tin cần ghi |
|---|---|
| Build | Commit/build ID, JDK, Spring Boot, Spring Session, Spring Security |
| Topology | Số app nodes, load balancer, Redis/JDBC topology, network location |
| Session | Số active sessions, payload size distribution, attributes, idle timeout |
| Workload | Read/write/login/logout/expiry ratios, think time, VU hoặc arrival rate |
| Test phases | Warm-up, ramp-up, steady-state, stress, recovery durations |
| Results | Throughput, p50/p95/p99, error rate, resource utilization |
| Backend | Redis memory/eviction/latency hoặc JDBC pool/query/lock metrics |
| SLA | Ngưỡng chấp nhận và pass/fail theo từng operation |
| Notes | Anomaly, tải nền, thay đổi môi trường và giới hạn phép đo |

Ví dụ bảng kết quả (số liệu giả lập, không phải benchmark Spring Session thực tế):

| Cấu hình | Read p95 | Write p95 | Login p95 | Lỗi | Kết luận |
|---|---:|---:|---:|---:|---|
| A: 2 app nodes, Redis nhỏ | 35 ms | 62 ms | 240 ms | 0.1% | Đạt tải cơ sở |
| B: 2 app nodes, Redis tăng capacity | 31 ms | 48 ms | 235 ms | 0.05% | Write cải thiện; login gần như không đổi |
| C: 4 app nodes, Redis giữ nguyên | 54 ms | 91 ms | 260 ms | 1.8% | Backend trở thành bottleneck |

Không dùng số liệu minh họa này làm cam kết hiệu năng. Báo cáo thực tế phải đính kèm script, dữ liệu test giả, cấu hình, timestamp và kết quả raw để người khác có thể chạy lại.

## 20. Quy trình benchmark từ đầu tới cuối

1. Xác định SLA, câu hỏi đo và workload đại diện.
2. Tạo user/session data giả với kích thước gần production.
3. Cố định build, topology, serializer, timeout và backend configuration.
4. Kiểm tra load generator đủ năng lực và cookie jar riêng cho từng VU.
5. Chạy baseline không tải và warm-up.
6. Đo riêng read, write, login và expiry.
7. Chạy workload tổng hợp với tỷ lệ đã xác định.
8. Tăng tải theo từng nấc và giữ steady state đủ lâu.
9. Thu metrics từ generator, application và Redis/JDBC đồng thời.
10. Chạy stress/recovery có kiểm soát để tìm giới hạn và thời gian phục hồi.
11. Lặp lại để xác nhận kết quả ổn định.
12. So sánh một biến cấu hình mỗi lần và lưu báo cáo có thể tái lập.

## 21. Những sai lầm làm benchmark sai lệch

- Dùng một session ID cho mọi VU, tạo contention không giống người dùng thật.
- Chỉ đo GET và gọi đó là read-only dù repository vẫn cập nhật last access.
- Dùng in-memory repository để dự đoán Redis/JDBC production.
- Bỏ qua password hashing hoặc dùng encoder yếu hơn production trong login test.
- Chỉ đo average latency, bỏ qua p95/p99 và error rate.
- Chạy quá ngắn, không có warm-up hoặc không chờ cleanup/expiration cycle.
- Để load generator bị CPU/network saturation mà không nhận ra.
- So sánh backend có topology, persistence hoặc HA khác nhau nhưng không ghi rõ.
- Dùng payload session quá nhỏ hoặc quá lớn so với production.
- Bỏ qua session expiry và cleanup, khiến benchmark không phản ánh churn dài hạn.
- Thay nhiều cấu hình cùng lúc, không thể xác định nguyên nhân cải thiện.
- Dùng dữ liệu hoặc cookie thật của người dùng trong test.

## 22. Nguyên tắc cần nhớ

- Đo riêng đọc, ghi, đăng nhập, logout và hết hạn trước khi ghép thành workload tổng hợp.
- Request đọc session có thể vẫn ghi metadata do cập nhật `lastAccessedTime`; đo backend operations thực tế.
- Mỗi virtual user phải có session/cookie riêng và payload giả gần với production.
- Đo repository-level để cô lập storage và end-to-end để thấy filter, security, cookie và ứng dụng.
- Login cần giữ password encoder và authentication path tương đương production; tách chi phí password hashing khỏi session save khi phân tích.
- Kiểm tra cả expiration correctness lẫn physical cleanup; không yêu cầu cleanup xảy ra chính xác tại thời điểm TTL.
- Dùng closed workload và open workload theo câu hỏi đo; theo dõi tốc độ phát thực tế.
- Thu p50/p95/p99, throughput, error rate, CPU/GC, pool, Redis/JDBC và payload size.
- Giữ môi trường, dữ liệu và topology cố định; warm-up, ramp-up, steady-state, stress và recovery.
- Thay một biến mỗi lần, chạy lặp lại và lưu script/cấu hình/raw result.
- Không dùng benchmark một node/in-memory để suy ra năng lực production nhiều node với Redis/JDBC.
