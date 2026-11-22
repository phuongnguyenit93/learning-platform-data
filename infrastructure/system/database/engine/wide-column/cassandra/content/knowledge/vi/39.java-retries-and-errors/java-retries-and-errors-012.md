# Deadline toàn nghiệp vụ, backoff và tránh nhân số lần thử qua nhiều lớp

> **Chương:** Retry và lỗi Java  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — hiểu hệ cơ sở dữ liệu Apache Cassandra phân tán, khóa phân vùng, thiết kế bảng theo truy vấn, nhất quán đọc/ghi, CQL, replication, compaction, repair, xử lý lỗi và kết nối bằng Java Driver.

Giả sử endpoint Java `POST /orders` gọi hai microservice, kiểm tra hạn mức, sau đó ghi vào Cassandra. Gateway đợi tối đa 2 giây. Khi Cassandra chậm, gateway thử lại ba lần; service A cũng thử lại ba lần; service B lại thử ba lần; còn Java Driver có thể thử coordinator khác. Người dùng chỉ bấm nút **một lần**, nhưng cluster có thể nhận **hàng chục yêu cầu**. Đúng lúc backend quá tải, retry lại đổ thêm tải xuống, khiến thời gian phục hồi kéo dài.

Vấn đề không chỉ nằm ở việc “nên retry bao nhiêu lần”. Phải trả lời đồng thời:

1. **Toàn bộ nghiệp vụ còn bao nhiêu thời gian?** Nếu người gọi đã hết hạn, việc gửi CQL mới thường không còn giá trị.
2. **Lỗi nào có thể thử lại?** Timeout không chứng minh mutation chưa được thực hiện; một số operations không idempotent.
3. **Ai được quyền retry?** Driver, repository, service, HTTP client, gateway và job queue không được tự nhân attempts ngoài kiểm soát.
4. **Đợi bao lâu trước khi thử lại?** Exponential backoff + jitter phải vừa tôn trọng deadline vừa giúp backend giảm tải.
5. **Làm thế nào để biết retry đang giúp hay gây hại?** Đo số CQL executions trên mỗi yêu cầu nghiệp vụ, deadline misses, retry budget, p99 và Cassandra overload.

**Phạm vi kỹ thuật:** Java Driver 4.x, đặc biệt tài liệu **Apache Java Driver 4.19**; Cassandra 4.x–5.x. Mọi cấu hình và số thời gian trong bài là **ví dụ thiết kế cho lab**, không phải ngưỡng production được khuyến nghị cho mọi cụm. Chọn thông số thật theo latency distribution, SLO, RF/CL, tình trạng GC/network và yêu cầu dữ liệu.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa **deadline toàn nghiệp vụ** và phân biệt nó với timeout của từng HTTP/CQL request.
2. Tính số lần thử tối đa ở backend khi nhiều lớp độc lập retry, kể cả speculative executions.
3. Hiểu hành vi `DefaultRetryPolicy`, `basic.request.timeout`, `Statement.setTimeout` và flag `setIdempotent` của Java Driver 4.x.
4. Áp dụng **capped exponential backoff + full jitter**, giới hạn attempts và retry budget trên toàn dịch vụ.
5. Tách lỗi cấu hình vĩnh viễn, lỗi tạm thời, quá tải, timeout chưa rõ kết quả và CAS conflict.
6. Viết Java dùng đồng hồ monotonic, đặt timeout theo thời gian **còn lại**, không tạo request mới sau deadline.
7. Thiết kế một điểm sở hữu retry, kết hợp load shedding, concurrency limit và circuit breaker phù hợp.
8. Đo và kiểm thử failure injection để chứng minh retry **không phá tính đúng dữ liệu** và **không khuếch đại quá mức**.

## 2. Deadline toàn nghiệp vụ không phải timeout của một lệnh CQL

### 2.1. Timeout, deadline và budget

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Timeout cho một bước** | Giới hạn chờ một thao tác cụ thể | Một lần `session.execute()` tối đa 600 ms |
| **Deadline toàn nghiệp vụ** | Mốc kết thúc của toàn bộ request/workflow | HTTP yêu cầu phải hoàn thành trong 1.500 ms kể từ lúc vào gateway |
| **Remaining budget** | Thời gian còn lại tại mỗi checkpoint | Sau auth, validation, cache: còn 880 ms |
| **Reserve/guard band** | Thời gian dành cho xử lý response, ghi log, trả HTTP hoặc cleanup | Giữ 100–150 ms cuối |
| **Retry budget** | Lượng attempts phụ được phép, không chỉ giới hạn theo từng request | Tối đa 1 retry/request và tỷ lệ retry toàn dịch vụ không vượt ngưỡng được đo |

Với một luồng tuần tự:

\[
T_{\text{business}} =
T_{\text{gateway}}+T_{\text{auth}}+T_{\text{service}}+
\sum T_{\text{CQL attempts}}+\sum T_{\text{backoff}}+
T_{\text{serialize}}.
\]

**Deadline** yêu cầu tổng này không vượt giới hạn đã được phê duyệt. Nếu mỗi thành phần tự chọn timeout 2 giây, rồi mỗi lớp thử lại, tổng thời gian có thể lớn hơn rất nhiều thời gian người dùng sẵn sàng đợi.

### 2.2. Một budget minh họa 1.500 ms

| Thời điểm từ khi nhận request | Hoạt động | Budget còn lại |
|---|---|---:|
| 0 ms | Gateway nhận request; budget tổng 1.500 ms | 1.500 ms |
| 120 ms | Hoàn thành auth/validation | 1.380 ms |
| 300 ms | Hoàn thành đọc cache và một lời gọi phụ | 1.200 ms |
| 300 ms | Giữ 150 ms để tạo response | **1.050 ms** cho phần dữ liệu còn lại |
| 900 ms | CQL chậm hoặc thất bại sau 600 ms | 600 ms tổng, chỉ 450 ms trước vùng reserve |
| 950 ms | Nếu có retry owner và đã backoff 50 ms | 550 ms tổng, chỉ 400 ms cho lần mới |
| 1.350 ms | Bắt buộc kết thúc công việc phụ trước reserve | 150 ms còn lại |
| 1.500 ms | Deadline nghiệp vụ | 0 ms |

**Không thể** cấp timeout 1.500 ms cho *mỗi* lệnh CQL bắt đầu lúc t=900 ms. Khi đó riêng lời gọi đã có thể kết thúc lúc t=2.400 ms, dù caller không còn chờ.

Công thức chung trước khi gửi một downstream request:

~~~text
remaining = business_deadline - now
usable = remaining - response_reserve

if usable <= min_useful_attempt:
    fail_fast / trả deadline exceeded
else:
    cql_timeout = min(configured_cql_ceiling, usable)
    gửi duy nhất request được phép trong ngân sách này
~~~

Nếu có retry owner, **cả backoff lẫn lần thử tiếp** cũng tiêu thụ `usable`, không được cộng thêm một timeout mới vào deadline cũ.

### 2.3. Đồng hồ monotonic trong Java

Một deadline **trong cùng JVM process** nên đo thời gian đã trôi qua bằng `System.nanoTime()`, không lấy thời gian đồng hồ tường như `LocalDateTime.now()` rồi trừ: NTP chỉnh clock, timezone hoặc DST có thể làm số đo trôi ngược/nhảy tới.

~~~java
long startedNanos = System.nanoTime();
long budgetNanos = java.time.Duration.ofMillis(1500).toNanos();

// Thực hiện một bước nghiệp vụ.
long elapsedNanos = System.nanoTime() - startedNanos;
long remainingNanos = budgetNanos - elapsedNanos;
if (remainingNanos <= 0L) {
    throw new IllegalStateException("Business deadline exceeded");
}
~~~

`System.nanoTime()` **không phải timestamp UTC** và không được gửi nguyên giá trị của nó qua máy khác. Trong một JVM, nó thích hợp cho elapsed time. Nếu lan deadline qua HTTP/gRPC:

- Có thể truyền **deadline UTC tuyệt đối** với đồng hồ các host đồng bộ, nhưng phải tính đến skew.
- Hoặc truyền **remaining duration** (giảm theo elapsed) cùng thông tin bắt đầu/tiến trình; mỗi hop khởi tạo monotonic deadline **ngắn hơn** budget nhận được, không reset về 1.500 ms.
- Nếu protocol đã có deadline/context propagation chuẩn, ưu tiên dùng cơ chế của framework thay vì tạo header tùy ý.
- Một hop không được tự “tăng” deadline theo timeout mặc định của mình. Caller hủy/bỏ cuộc **không có nghĩa server đã dừng xử lý mutation**.

## 3. Retry amplification: vì sao tầng nào cũng retry là nguy hiểm?

### 3.1. Attempts nhân nhau, không cộng nhau

Giả sử một yêu cầu nghiệp vụ đi qua ba lớp, mỗi lớp cho **3 attempts tổng cộng**, tính cả lần đầu:

~~~text
Client HTTP:           3 attempts
    Service A:         3 attempts / client attempt
        Service B:     3 attempts / service A attempt
            Cassandra request

Tệ nhất: 3 × 3 × 3 = 27 lời gọi tới B/Cassandra
~~~

Nếu thêm Driver cho 2 executions trong một số lỗi phù hợp, mức lý thuyết có thể thành **54 lần thực thi CQL**, chưa tính speculative execution hoặc luồng phụ khác. Các loại lỗi cụ thể có thể khiến policy ngừng sớm, nên đây là **cận thiết kế về số attempts**, không khẳng định DefaultRetryPolicy luôn retry mọi request.

Ví dụ nổi tiếng trong thực hành hệ phân tán: **5 lớp, mỗi lớp 3 attempts ⇒ 3⁵ = 243** cơ hội gọi tới tầng dưới cùng cho một hành động. **Chú ý cách đếm:** “3 attempts” là *1 lần đầu + 2 lần retry*. Nếu mô tả “3 retries” theo nghĩa *3 lần thử lại ngoài lần đầu*, mỗi lớp có 4 attempts.

\[
A_{\text{deepest}}^{\max} = \prod_{i=1}^{n} A_i,
\]

trong đó `A_i` là tổng số attempts được phép ở tầng `i`, gồm cả lần đầu. Với speculative execution, mỗi lời gọi driver còn có thể phát ra **nhiều executions song song**, mỗi execution có đường retry riêng, làm hệ số tải tăng hơn nữa.

### 3.2. Bảng thử tính cho một yêu cầu

| Retry configuration | Số attempts tầng sâu tối đa | Nhận xét |
|---|---:|---|
| Gateway 1, service 1, Driver 1 | 1 | Không khuếch đại |
| Gateway 2, service 1, Driver 2 | 4 | Lớp trên và Driver cùng retry |
| Gateway 3, service 3, Driver 2 | 18 | Có nguy cơ nhân tải lớn |
| Bốn lớp đều 3 attempts | 81 | Retry storm khi lỗi cùng lúc |
| Năm lớp đều 3 attempts | 243 | Không nên thiết kế mặc định |

**Nhân số lượng requests không có nghĩa nhân tổng thời gian theo đúng tỷ lệ** vì có song song, timeout/early exit, nhưng backend vẫn phải trả giá bằng pool slots, coordinator work, replica reads/writes, CPU, network và tombstone/compaction pressure.

### 3.3. Vòng phản hồi xấu khi backend quá tải

~~~mermaid
flowchart TD
    A["Cassandra chậm / một replica lỗi"] --> B["Timeout và 5xx tăng"]
    B --> C["Gateway + service + driver đều retry"]
    C --> D["CQL attempts/s và inflight requests tăng"]
    D --> E["CPU / network / queue / GC / compaction tăng"]
    E --> A
    C --> F["Client bỏ cuộc, nhưng in-flight server work có thể còn"]
    F --> D
~~~

**Backoff chỉ trì hoãn retry**, không tự loại bỏ hệ số nhân. Cần **một điểm chịu trách nhiệm số lần thử** và giới hạn toàn bộ time/traffic budget.

## 4. Ai nên sở hữu retry?

### 4.1. Chọn một nơi quyết định chủ yếu

| Lớp | Có thể được quyền retry? | Khuyến nghị thiết kế |
|---|---|---|
| UI/mobile/browser | Có thể thử lại một thao tác đọc sau lỗi transient | Không retry POST thay đổi trạng thái nếu không có idempotency key và contract rõ |
| API gateway/ingress | Có thể xử lý lỗi kết nối trước khi upstream thực thi | Không retry mọi 5xx và không tăng tổng deadline |
| Orchestrating service | Hiểu nghiệp vụ, deadline và idempotency | Thường là nơi tốt để **quyết định retry toàn workflow** |
| Downstream microservice | Có thể có retry rất hạn chế nếu giữ bất biến | Cần hợp đồng với caller, không tự chọn attempts cao |
| Cassandra Java Driver | Retry rất hạn chế khi policy đánh giá có khả năng an toàn | Giữ default hoặc dùng custom theo kế hoạch; **không coi là không retry** |
| Cassandra coordinator/replicas | Thực hiện công việc nội bộ theo CL/replication/Paxos | Không kiểm soát trực tiếp bằng vòng retry của ứng dụng |
| Job/queue consumer | Broker có thể redeliver, DLQ/backoff dài hạn | Redelivery cũng là một tầng retry, cần dedup/idempotency |

Hai chiến lược dễ quản lý:

**Chiến lược A — retry do Driver xử lý:** Gateway, service và repository **không** tự retry CQL. Java Driver dùng `DefaultRetryPolicy` và request timeout nhỏ hơn **business remaining budget**. Điều này phù hợp nhiều workload request-response. Nhưng Driver vẫn có một số internal retries/hard-coded reprepare; cần đo.

**Chiến lược B — retry do service sở hữu:** Chọn một lớp ứng dụng duy nhất để backoff theo outcome/idempotency. Driver policy được cấu hình/cài đặt để **không thêm các retry policy-level ngoài dự kiến** (custom `RetryPolicy` đã review; một số hard-coded recovery trước khi request gửi vẫn tồn tại). Gateway không retry cùng nghiệp vụ; service có attempts, deadline và retry token budget toàn cục.

**Không giả định `DefaultRetryPolicy` có nghĩa Driver luôn chỉ gửi đúng một request.** Nó có thể retry giới hạn, bên cạnh các trường hợp fallback trước khi gửi network, tự reprepare hoặc xử lý node bootstrapping. Nếu service còn gọi `execute` lặp lại, phải tính cả hai tầng.

### 4.2. Retry ở tầng quá cao và quá thấp đều có giá

Retry từ gateway có thể phát lại **cả workflow**, gồm auth, kiểm tra tồn kho, gọi thanh toán và đọc/ghi nhiều bảng — tốn hơn retry đúng một truy vấn nhỏ. Retry quá thấp ở Driver lại thiếu hiểu biết nghiệp vụ: nó không biết thao tác chuyển trạng thái có thể gây gửi email hay không.

Quy tắc chọn: **giao retry cho tầng có đủ thông tin về idempotency và deadline, đồng thời có thể giới hạn được tổng tải**. Những tầng khác chỉ trả outcome có ý nghĩa hoặc retry cực hạn chế đã được tính trong budget.

### 4.3. Retry policy không thay thế load shedding

Khi Cassandra thật sự bão hòa, “thử lại thông minh hơn” vẫn là thêm công việc. Cần:

- **Admission control:** từ chối hoặc xếp hàng có giới hạn ngay đầu hệ thống.
- **Concurrency limit/bulkhead:** giới hạn số request CQL cùng lúc.
- **Retry token budget:** chỉ dùng một lượng attempts phụ rất nhỏ khi hệ thống còn khỏe.
- **Circuit breaker** có kiểm soát: hạn chế request xuống đích đang lỗi để cho phép hồi phục, tránh đồng loạt half-open không jitter.
- **Backpressure:** không nhận thêm việc nếu backlog đã quá khả năng hoàn thành trước deadline.

Nếu queue delay gần bằng deadline, **không enqueue thêm**. Một request được timeout trong queue của driver cũng tiêu thụ tài nguyên và làm kết quả nghiệp vụ trễ.

## 5. Hành vi thực của Java Driver 4.x

### 5.1. Request timeout của Driver 4.x

Tài liệu Driver 4.19 xác nhận:

- `basic.request.timeout` hoặc `Statement.setTimeout(Duration)` là giới hạn **tổng thời gian của một lần `session.execute`** bao gồm Driver retry/speculative executions.
- Nếu bật request throttling, **thời gian nằm trong throttling queue cũng tính vào timeout**.
- Timeout này **không phải deadline của toàn HTTP request**, không cộng trừ thời gian auth/serialize/HTTP khác.
- Nếu workflow có nhiều câu CQL, mỗi lần `execute` có timeout riêng. Với paging, việc fetch các trang về sau phát sinh những requests bổ sung; phải tính deadline ở tầng nghiệp vụ cho toàn bộ quá trình tiêu thụ kết quả.

Ví dụ HOCON dành cho **lab**:

~~~hocon
datastax-java-driver {
  basic.request.timeout = 700 milliseconds
  basic.request.default-idempotence = false

  advanced.retry-policy.class = DefaultRetryPolicy
  advanced.speculative-execution-policy.class = NoSpeculativeExecutionPolicy

  profiles {
    short-read {
      basic.request.timeout = 400 milliseconds
      basic.request.consistency = LOCAL_QUORUM
    }
  }
}
~~~

Đây là **các giá trị ví dụ để học cách đặt giới hạn**, không phải default của mọi release. `DefaultRetryPolicy` đã là policy mặc định; `NoSpeculativeExecutionPolicy` cũng là lựa chọn mặc định. Khai báo để nhìn rõ nơi phát sinh retry/sự thực thi song song. Timeout nên đo theo workload thật; cấu hình 400 ms quá nhỏ có thể gây lỗi với cluster chậm, còn 700 ms quá lớn có thể vi phạm deadline ngắn.

### 5.2. DefaultRetryPolicy không retry vô điều kiện

| Phản hồi/lỗi | Hành vi mặc định theo tài liệu Driver 4.19 | Điều cần hiểu |
|---|---|---|
| `UnavailableException` | Tối đa **một lần** thử coordinator kế tiếp trong trường hợp phù hợp | Coordinator đầu có thể có thông tin lỗi node chưa cập nhật |
| `ReadTimeoutException` | Tối đa một lần trên **cùng coordinator** khi đã có đủ replica trả lời nhưng chưa nhận data | Không retry mọi read timeout |
| `WriteTimeoutException` | Chỉ có điều kiện retry rất hạn chế, ví dụ write type `BATCH_LOG`; các loại khác thường rethrow | Ghi có thể đã áp dụng ở một số replica |
| Kết nối đóng khi request đã gửi và không nhận response | Retry policy có thể thử coordinator khác nếu statement **idempotent** | Không biết chắc request trước đã được áp dụng |
| `OverloadedException`, một số server errors | Với statement idempotent có thể retry coordinator khác | Lỗi quá tải diện rộng thường **không** được cứu bằng tăng attempts |
| `QueryValidationException`, `ProtocolError`, lỗi không thể sửa bằng retry | Rethrow theo hard-coded rules | Sửa CQL/schema/driver, đừng retry |
| Không tìm được connection trước khi gửi message, reprepare, node bootstrapping | Driver có thể tự xử lý một số trường hợp **ngoài RetryPolicy** | Quan sát request-level metrics thay vì giả định policy quyết định mọi lần |

**Cảnh báo:** các chi tiết bảng này nói về **DefaultRetryPolicy** và không mô tả mọi custom/bản phân phối. Retry policy chỉ được gọi đối với những tình huống phù hợp và nhìn chung **chỉ retry các statement được đánh dấu idempotent**; không nên quảng bá “Driver luôn retry một lần” cho mọi lỗi.

### 5.3. Không nên dùng ConsistencyDowngradingRetryPolicy làm cách chữa timeout

Chính sách này có thể hạ CL trong những tình huống cụ thể (ví dụ `QUORUM → ONE`) hoặc coi một ghi đã ACK một số replicas là thành công, làm yếu yêu cầu nhất quán của ứng dụng. Với quy tắc **write ở QUORUM rồi read ở QUORUM**, việc tự hạ consistency có thể phá invariant. **Không bật nó chỉ để làm giảm biểu đồ lỗi**. Cần sự chấp thuận nghiệp vụ và test failure modes trước khi đổi CL.

### 5.4. Speculative execution không phải retry sau lỗi

Speculative execution gửi yêu cầu bổ sung **trước khi** lần đầu trả về nếu chậm. Nó có thể giảm p99 với node bị GC pause nhưng tăng tải cluster.

~~~hocon
# Chỉ để hiểu phương thức cấu hình; KHÔNG bật tùy tiện trên production:
datastax-java-driver {
  advanced.speculative-execution-policy {
    class = ConstantSpeculativeExecutionPolicy
    max-executions = 2
    delay = 100 milliseconds
  }
}
~~~

Trong Driver 4.x, speculative execution mặc định **tắt** và chỉ được lên lịch cho request **idempotent**. Mỗi execution có thể chịu retry độc lập. Khi một execution “thắng”, response của bản khác có thể bị bỏ qua nhưng **Cassandra không cung cấp việc hủy mutation đã gửi đến server một cách bảo đảm**.

Không bật speculation cho counter increments, non-idempotent list prepend, CAS side-effect hoặc một thao tác có thể tạo bản ghi trùng ở hệ thống ngoài. Theo dõi `speculative-executions`, `pool.orphaned-streams`, `pool.in-flight` và độ trễ trước/sau; không chỉ nhìn p99 của client.

## 6. Phân loại lỗi trước khi retry

### 6.1. Ma trận diễn giải outcome

| Loại lỗi/kết quả | Có chứng minh không thực thi? | Retry gợi ý |
|---|---|---|
| CQL syntax/invalid query, permission denied, schema mismatch | Thường là lỗi vĩnh viễn ở request hiện tại | **Không retry**; sửa cấu hình/CQL/schema |
| Authentication/TLS/hostname validation lỗi | Không thể kết nối đúng bảo mật | Không retry mù; khôi phục credentials/trust/cert |
| `UnavailableException` | Coordinator không thấy đủ replicas cho CL tại thời điểm đó | Có thể thử coordinator khác **rất hạn chế** theo Driver default; nếu rộng khắp, fail fast |
| `ReadTimeoutException` | Read chưa có response đúng CL; không phải write commit | Tùy dataPresent/received và idempotency; để policy đánh giá |
| `WriteTimeoutException`/`WriteFailureException` | **Không** chứng minh mutation chưa áp dụng | Với non-idempotent write: **UNKNOWN**, reconcile trước retry |
| `DriverTimeoutException` | Driver hết deadline cho request, có thể chưa nhận response | **UNKNOWN với mutation**, không coi là rollback |
| `OverloadedException` | Cluster đang bảo vệ tài nguyên | Chủ yếu giảm tải/backoff/load shedding, không đổ thêm requests |
| `RequestThrottlingException` | Throttler không nhận hoặc không xếp hàng request | Admission/backpressure; có thể chưa gửi CQL nhưng **không** là giấy phép retry vô hạn |
| `BusyConnectionException` (có thể nằm trong `AllNodesFailedException`) | Pool/stream ids hết | Điều tra concurrency, pool, backpressure; tăng retry thường làm nặng hơn |
| LWT `wasApplied() == false` | **CAS precondition không thỏa** | Không phải lỗi transient; báo conflict hoặc tính lại |
| LWT timeout/mất ACK | Outcome có thể không rõ dù mutation đã được áp dụng | Idempotency marker/reconciliation; không tự đổi thành CAS false |

**Không phân loại bằng cách tìm chuỗi `"timeout"` trong thông báo lỗi**. Dùng class/cause theo Driver version, thông tin coordinator, CL, số replica nhận/required khi có và metrics. Một exception có thể được bọc trong `CompletionException`/`ExecutionException` ở luồng bất đồng bộ.

### 6.2. Phân biệt timeout server và timeout driver

~~~text
ReadTimeoutException:
  Coordinator nhận query nhưng không đủ phản hồi/data trước read timeout
  do Cassandra server quyết định.

WriteTimeoutException:
  Coordinator nhận mutation nhưng không đủ ACK trong thời gian server.
  Một số replicas có thể đã nhận ghi.

DriverTimeoutException:
  Client-side request deadline hết; driver không nhận kết quả kịp.
  Có thể do queue, network, coordinator, retry/speculation.

BusinessDeadlineExceeded:
  Workflow đã dùng hết budget, bất kể một câu CQL riêng có thể
  vừa thành công hoặc còn đang chạy.
~~~

Không đặt `read_request_timeout_in_ms` hay server write timeout **tùy tiện cao hơn hàng chục lần** chỉ để giảm lỗi ở client. Sự tương tác giữa timeout client/server, RF/CL, network RTT và backpressure phải được đo có mục tiêu.

### 6.3. LWT false và request timeout là hai outcome khác nhau

Với:

~~~sql
UPDATE retry_lab.jobs_by_id
SET status = 'RUNNING', version = 2
WHERE job_id = 11111111-1111-4111-8111-111111111111
IF version = 1;
~~~

Nếu `ResultSet.wasApplied() == false`, đã biết điều kiện không thỏa tại lúc CAS kiểm tra. Nếu request timeout, mutation **có thể đã nâng version lên 2** nhưng response mất. Retry y nguyên có thể trả false do lần đầu đã thành công. Vì thế phải phân biệt ***conflict thật*** với ***unknown outcome***, không biến cả hai thành “retryable error”.

## 7. Idempotency: điều kiện bắt buộc trước khi thử lại ghi

### 7.1. Định nghĩa đúng

Một operation **idempotent** nếu chạy nhiều lần tạo **cùng trạng thái dữ liệu cuối** như chạy một lần, trong điều kiện nghiệp vụ của operation đó. Nó **không** có nghĩa “request không thể gây tải”, “luôn trả cùng mã HTTP” hay “Cassandra rollback nếu timeout”.

| CQL/operation | Đánh giá sơ bộ | Điều phải kiểm tra |
|---|---|---|
| `SELECT` không side effect | Thường idempotent | Paging, CL, snapshot khác nhau theo thời gian vẫn có thể cho dữ liệu khác |
| `UPDATE ... SET status='DONE'` | Thường idempotent về giá trị | Timestamp/TTL, triggers/outbox và ghi cạnh tranh có thể làm kết quả khác |
| `INSERT` cùng PK và giá trị cố định | Có thể idempotent về row value | Timestamp/TTL, last-write-wins và duplicate downstream effects |
| `UPDATE counter = counter + 1` | **Không idempotent** | Retry có thể tăng 2 lần |
| `UPDATE list_col = ['x'] + list_col` | **Không idempotent** | Retry có thể prepend hai lần |
| `INSERT ... IF NOT EXISTS` | Cần xét semantics kết quả | Lần đầu true, lần sau false dù cùng business request |
| `UPDATE ... IF version = n` | Cần idempotency/reconcile riêng | False ở retry có thể do lần đầu đã commit |
| Gửi email/payment bên ngoài sau ghi | Không tự idempotent | Cần operation ID, outbox/dedup ở hệ thống ngoài |

Java Driver 4.x đặt `basic.request.default-idempotence = false` theo mặc định. Với prepared SELECT:

~~~java
PreparedStatement ps = session.prepare(
    "SELECT status FROM retry_lab.jobs_by_id WHERE job_id = ?");

BoundStatement read = ps.bind(jobId)
    .setIdempotent(true); // Chỉ đúng vì query này là đọc thuần.
~~~

**Đánh dấu theo statement**, không bật `default-idempotence = true` cho toàn session khi application có counter/LWT/batch hoặc thao tác không idempotent. Prepared statements không tự làm cho một mutation idempotent.

### 7.2. TTL và timestamp làm retry tinh vi hơn

Một `INSERT ... USING TTL 60` được gửi lại 30 giây sau với TTL=60 có thể **gia hạn hiệu lực** so với kỳ vọng ban đầu. Cùng giá trị nhưng deadline đã thay đổi; vì vậy nó **không idempotent về retention deadline**.

Nếu cần giữ hạn:

- Lưu `expires_at_utc` của nghiệp vụ, tính TTL **còn lại** trước mỗi lần gửi, không lấy lại TTL ban đầu.
- Có chiến lược timestamp/conflict khi concurrent writes.
- Nếu đã hết hạn, **không dùng USING TTL 0**, vì TTL 0 nghĩa không hết hạn.
- Với dữ liệu auth/session cần expiration chính xác, kiểm tra deadline ở tầng nghiệp vụ, không chỉ chờ Cassandra compaction.

Ngay cả một UPDATE gán giá trị cố định có thể có write timestamp mới khi retry và ghi đè một phiên bản đồng thời. Cần xem **idempotency theo invariant và concurrency**, không chỉ nhìn hai câu CQL có cùng literal.

### 7.3. Operation ID cho API tạo resource

Một mẫu:

~~~text
POST /jobs
  Idempotency-Key = "request-uuid-123" (ví dụ, không dùng secret)

Service:
  1. Xác thực request ID và payload hash theo scope của caller.
  2. Lưu marker operation trong partition/registry được thiết kế.
  3. Chỉ thực hiện transition nếu chưa hoàn tất.
  4. Khi timeout, đọc lại marker + trạng thái trước khi tạo lần nữa.
  5. Trả lại outcome nhất quán với lần đầu, không nhân side effect.
~~~

**Lưu ý:** chỉ gắn header idempotency key chưa bảo đảm dedup. Phải có **dữ liệu bền vững**, key scoping, retention, concurrency control (có thể LWT) và xử lý lỗi khi ghi marker/side effect không atomic. Không sao chép key của người dùng khác hoặc log toàn bộ key nếu nó là token nhạy cảm.

## 8. Exponential backoff có giới hạn và jitter

### 8.1. Vì sao fixed delay không đủ?

Nếu 10.000 client cùng timeout rồi đợi đúng 100 ms, chúng thường gửi lại **đồng loạt** ở t+100 ms, gây thêm đỉnh tải. Exponential backoff tăng khoảng chờ sau mỗi thất bại; **jitter** phân tán thời điểm gửi để các client không đồng bộ hoàn toàn.

Một công thức **full jitter**:

\[
cap_k=\min(maxDelay,\ baseDelay \times 2^{k-1}),\quad
sleep_k\sim Uniform(0,\ cap_k).
\]

Trong đó `k` là **số lần retry đang chuẩn bị**, bắt đầu k=1. Ví dụ `baseDelay=50 ms`, `maxDelay=400 ms`:

| Retry thứ k | Cap của delay | Khoảng random có thể chọn |
|---|---:|---|
| 1 | 50 ms | 0–50 ms |
| 2 | 100 ms | 0–100 ms |
| 3 | 200 ms | 0–200 ms |
| 4 | 400 ms | 0–400 ms |
| 5+ | 400 ms | 0–400 ms |

Không nên hiểu bảng là **ngủ đúng** 50/100/200/400 ms. Full jitter chọn một giá trị ngẫu nhiên từ khoảng tương ứng. Cũng không nên chọn delay lớn hơn **remaining deadline**; khi không đủ thời gian cho backoff **và** một lần thử có ý nghĩa, hãy dừng.

### 8.2. Hàm Java tính full jitter

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

static Duration fullJitterDelay(
        int retryIndex, long baseMs, long maxMs) {
    if (retryIndex < 1 || baseMs < 1 || maxMs < baseMs
            || maxMs == Long.MAX_VALUE) {
        throw new IllegalArgumentException("Invalid backoff config");
    }

    long capMs = baseMs;
    for (int i = 1; i < retryIndex; i++) {
        capMs = capMs >= maxMs / 2
                ? maxMs
                : Math.min(maxMs, capMs * 2);
    }

    long sampledMs = ThreadLocalRandom.current().nextLong(capMs + 1);
    return Duration.ofMillis(sampledMs);
}
~~~

Hàm này **chỉ tính thời gian chờ**, không tự ngủ hoặc retry. Nếu dùng async:

~~~java
// Pseudocode: scheduler chạy một lần sau backoff, không dùng sleep
// trong Netty/driver callback.
//
// Duration delay = fullJitterDelay(retryIndex, 50, 400);
// if (delay.plus(minUsefulAttempt).compareTo(deadline.remaining()) >= 0)
//     completeDeadlineExceeded();
// else
//     scheduler.schedule(() -> attemptAgainIfStillAllowed(),
//                        delay.toMillis(), TimeUnit.MILLISECONDS);
~~~

**Không gọi `Thread.sleep` trong `RetryPolicy` của Java Driver**: policy callback chạy trên các luồng I/O và việc block có thể làm treo xử lý các request khác. Nếu cần trì hoãn, triển khai scheduling ở **tầng service** đã sở hữu retry, không phải ngủ trong callback policy.

### 8.3. Backoff phải đi kèm giới hạn

Một vòng retry hợp lý có ba “cửa” đồng thời:

~~~text
retry_allowed =
    operation_is_safe_to_repeat
    AND error_is_transient_and_retryable
    AND attempts_used < max_attempts
    AND retry_token_budget_has_capacity
    AND now + jitter_delay + min_useful_attempt + reserve < deadline
    AND downstream_not_overloaded_beyond_safe_threshold
~~~

Nếu một cửa đóng, dừng. **Capped backoff không có nghĩa chờ mãi ở maxDelay**: phải có `maxAttempts`, deadline và retry token budget.

### 8.4. Retry-After, circuit breaker và overload

Một service HTTP có thể trả `Retry-After` khi quá tải. Hãy tôn trọng nó **nếu** thời gian đó còn nằm trong deadline và caller cho phép retry, không bỏ qua để gửi sớm hơn. Nhưng Cassandra CQL không cung cấp cùng một HTTP `Retry-After` chung cho mọi error. Với Cassandra overload, thường cần **giảm admission rate, queue depth và số request đồng thời**, chứ không chỉ tăng delay một chút rồi tiếp tục gửi.

Circuit breaker cần **half-open probes có giới hạn**, nếu không hàng ngàn service instance có thể cùng thử mở lại và tạo đỉnh tải mới. Retry budget (ví dụ vài phần trăm lưu lượng thành công trong một khoảng trượt) nên được kiểm chứng bằng số liệu; tỷ lệ cụ thể tùy hệ thống.

## 9. Java Driver: đặt timeout theo remaining budget

### 9.1. Một lớp Deadline dùng monotonic clock

Ví dụ sau chỉ dùng Java standard library, có thể tái sử dụng trong một JVM:

~~~java
import java.time.Duration;

public final class Deadline {
    private final long startedNanos;
    private final long budgetNanos;

    private Deadline(Duration budget) {
        if (budget.isZero() || budget.isNegative()) {
            throw new IllegalArgumentException("Budget must be positive");
        }
        this.startedNanos = System.nanoTime();
        this.budgetNanos = budget.toNanos();
    }

    public static Deadline start(Duration budget) {
        return new Deadline(budget);
    }

    public Duration remaining() {
        long elapsed = System.nanoTime() - startedNanos;
        long left = budgetNanos - elapsed;
        return Duration.ofNanos(Math.max(0L, left));
    }

    public boolean expired() {
        return remaining().isZero();
    }

    public Duration usable(Duration reserve) {
        Duration result = remaining().minus(reserve);
        return result.isNegative() ? Duration.ZERO : result;
    }
}
~~~

Đoạn code này giả định budget nhỏ/không gây tràn `Duration.toNanos()` và chạy trong cùng process. Production có thể cần xử lý overflow, tracing context, cancellation và framework deadline semantics; **không truyền `startedNanos` qua máy khác**.

### 9.2. Gửi một SELECT với timeout co theo budget

Ví dụ service **không thêm vòng retry CQL ở tầng service**. Driver giữ DefaultRetryPolicy giới hạn và speculative execution tắt như mục 5.1; toàn nghiệp vụ được bảo vệ bằng một `Deadline`.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import java.time.Duration;
import java.util.Optional;
import java.util.UUID;

static Optional<String> readJobStatus(
        CqlSession session, PreparedStatement prepared,
        UUID jobId, Deadline deadline) {

    // PreparedStatement nên tạo/cached khi startup, không prepare
    // cho mỗi HTTP request nếu có thể tránh.
    Duration usable = deadline.usable(Duration.ofMillis(100));
    Duration configuredCeiling = Duration.ofMillis(700);
    Duration timeout = usable.compareTo(configuredCeiling) < 0
            ? usable : configuredCeiling;

    if (timeout.compareTo(Duration.ofMillis(50)) < 0) {
        throw new IllegalStateException("Insufficient business budget");
    }

    BoundStatement statement = prepared.bind(jobId)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setIdempotent(true)   // SELECT không có side effect.
        .setTimeout(timeout); // Giới hạn execute lần này, gồm Driver retries.

    ResultSet rs = session.execute(statement);

    // Khi caller đã hết deadline, không xem response đến muộn là
    // thành công của HTTP request đang chờ.
    if (deadline.expired()) {
        throw new IllegalStateException("Business deadline exceeded");
    }

    Row row = rs.one();
    return row == null
        ? Optional.empty()
        : Optional.ofNullable(row.getString("status"));
}
~~~

Chuẩn bị statement ở startup:

~~~java
PreparedStatement readById = session.prepare(
    "SELECT status FROM retry_lab.jobs_by_id WHERE job_id = ?");
~~~

**Giới hạn ví dụ:** `IllegalStateException` là placeholder cho exception nghiệp vụ `DeadlineExceeded`; production cần mapping sang HTTP/gRPC, logging/tracing và cleanup thích hợp. Đoạn code **không** tự thực hiện ngoại vi nhiều bước; nơi gọi phải dùng **cùng đối tượng Deadline** xuyên auth, cache, CQL, serialize. Đừng tạo Deadline mới với 1.500 ms ở đầu mỗi repository method.

Khi timeout/cancel, Cassandra có thể vẫn đang thực thi một mutation đã gửi. Kiểm tra `deadline.expired()` sau response là bảo vệ **response contract**, không phải lệnh rollback dữ liệu.

### 9.3. Request profile và statement là immutable

Driver 4.x statement có các setter **trả instance mới**:

~~~java
BoundStatement base = readById.bind(jobId);
BoundStatement timed = base
    .setIdempotent(true)
    .setTimeout(Duration.ofMillis(250))
    .setExecutionProfileName("short-read");

// Phải execute "timed", không execute "base" và
// kỳ vọng các setter đã sửa base tại chỗ.
session.execute(timed);
~~~

Khi dùng execution profile `short-read` có timeout mặc định 400 ms, `setTimeout(250 ms)` trên statement có thể override nó. Một bug quên gán return value làm timeout/retry policy thực tế khác hẳn tài liệu thiết kế.

### 9.4. Synchronous vs asynchronous và cancellation

`session.executeAsync` trả `CompletionStage`; bạn có thể gắn timeout/propagate cancellation theo framework. Tuy nhiên:

- Hủy future ở phía Java **không đảm bảo Cassandra hủy work đã gửi tới coordinator/replicas**.
- Khi caller bỏ cuộc, **không enqueue retry mới** và không tiêu thụ thêm pages nếu không còn ai cần.
- Không block event-loop/Netty callback bằng ngủ/backoff, I/O đồng bộ hoặc xử lý CPU lớn.
- Nếu cần quản lý deadline cho **nhiều CQL calls** trong một saga, outer orchestrator phải sở hữu absolute/monotonic deadline; driver timeout chỉ giới hạn từng call.

## 10. Nếu service thật sự sở hữu retry: backoff ở đúng một tầng

### 10.1. Cấu trúc vòng lặp có kiểm soát

Nếu operation an toàn để lặp lại, và service cần retry một lỗi transient mà Driver default không xử lý, một **sơ đồ quyết định**:

~~~text
deadline = businessDeadlineFromCaller()
maxAttempts = 2           # tính cả lần đầu
retryBudget = sharedTokenBudgetForThisService()

for attemptIndex in 1..maxAttempts:
    if deadline has no useful time:
        return DEADLINE_EXCEEDED

    execute downstream request with timeout <= remaining minus reserve

    if result is success:
        return SUCCESS
    if result is non-retryable:
        return ERROR / BUSINESS_CONFLICT
    if result is UNKNOWN write outcome:
        reconcile or fail UNKNOWN; never blindly repeat
    if attemptIndex == maxAttempts or tokenBudget exhausted:
        return ERROR

    delay = fullJitter(retryIndex=attemptIndex)
    if delay + usefulAttempt + reserve >= remaining:
        return DEADLINE_EXCEEDED
    schedule next attempt after delay
~~~

**Điều kiện thiết kế:** nếu service là owner attempts, **tắt/gắn giới hạn rõ Driver policy-level retries và speculative executions** qua policy đã kiểm thử. Dù vậy, Driver vẫn có thể xử lý một số pre-send/reprepare nội bộ; metric phải đếm thực tế. Cũng cần ngăn retry tại HTTP client/gateway/queue bên ngoài hoặc đưa chúng vào ngân sách thống nhất.

### 10.2. Không ngủ trong Driver RetryPolicy

Tài liệu `RetryPolicy` chính thức nhấn mạnh callbacks chạy trên luồng I/O; **không được gọi `Thread.sleep`** để làm backoff. Muốn triển khai delayed retries, làm ở tầng service với scheduler và một điểm quản lý attempt counter.

Trong ứng dụng có reactive pipeline, tiếp tục trên scheduler hoặc reactive delay operator phù hợp, **không** biến non-blocking pipeline thành thread-per-retry không giới hạn. Một request đã hết deadline phải được gỡ khỏi hàng đợi.

### 10.3. Đặt ngân sách retry toàn dịch vụ

Chỉ giới hạn `maxAttempts = 2` theo từng request chưa đủ: khi backend từ chối 100% requests, lưu lượng vẫn có thể **gấp đôi**. Cần **retry budget theo tổng lưu lượng**.

Ví dụ chính sách để thảo luận:

~~~text
requests ban đầu: 10.000 / phút
retry budget: tối đa 200 attempts phụ / phút trong giai đoạn ổn định
max attempts/request: 2
business deadline: 1.500 ms
overload/circuit open: không dùng token retry, fail fast
~~~

Các con số là **minh họa**. Khi requests mới 10.000/phút và retry budget 200/phút, extra load được giới hạn tối đa khoảng 2% **nếu token budget được thực thi nhất quán** trên mỗi instance/cluster ứng dụng. Trong hệ đa instance, phải định nghĩa ngân sách theo process hay shared budget và hiệu ứng khi scale-out; không vô tình cấp cùng 200 tokens cho mỗi replica app rồi làm con số toàn hệ thống lớn gấp N.

## 11. Java/CQL lab: chứng minh deadline và retry không làm sai dữ liệu

### 11.1. Chuẩn bị

Lab cần Cassandra 4.x/5.x và Java Driver 4.x. Với cluster ba node ở DC thực tên `dc1`, dùng RF=3; nếu chỉ một node, đổi RF/CL cho phù hợp trước khi chạy.

~~~bash
nodetool status
nodetool describecluster
nodetool version
~~~

Trong `cqlsh`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS retry_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS retry_lab.jobs_by_id (
  job_id uuid PRIMARY KEY,
  status text,
  version int,
  updated_at timestamp
);

INSERT INTO retry_lab.jobs_by_id
  (job_id, status, version, updated_at)
VALUES (
  11111111-1111-4111-8111-111111111111,
  'NEW',
  1,
  '2026-11-21T09:00:00Z'
);

SELECT status, version
FROM retry_lab.jobs_by_id
WHERE job_id = 11111111-1111-4111-8111-111111111111;
~~~

`IF NOT EXISTS` không sửa schema cũ. Trước khi đo, xác minh `DESCRIBE KEYSPACE retry_lab`, `DESCRIBE TABLE retry_lab.jobs_by_id`, tên DC và RF thật. Không dùng dữ liệu chứa thông tin người dùng thực trong fault injection.

### 11.2. Case A — một SELECT có deadline toàn request

Thực hiện qua application endpoint lab:

1. Tạo một Deadline 1.500 ms tại ingress; dùng cùng deadline cho auth, business logic và read CQL.
2. Đặt driver timeout `min(700 ms, remaining - 100 ms)` trước mỗi attempt.
3. Ghi `business_elapsed_ms`, `driver_call_ms`, `remaining_before_cql_ms`, `attempt_count` và response status.
4. Thêm độ trễ có kiểm soát **ở proxy/lab layer** trước CQL rồi kiểm tra có **fail fast** khi remaining thấp.
5. Nếu caller đã hết deadline, hệ thống không khởi chạy CQL mới hoặc tạo retry mới.

Không thí nghiệm bằng cách tắt ngẫu nhiên replica production hoặc xóa SSTable; dùng cluster/proxy được phép, có rollback.

### 11.3. Case B — timeout xảy ra sau khi mutation có thể thành công

Trong lab:

~~~sql
UPDATE retry_lab.jobs_by_id
SET status = 'RUNNING', version = 2
WHERE job_id = 11111111-1111-4111-8111-111111111111
IF version = 1;
~~~

Tạo kiểm thử có kiểm soát nơi **phản hồi từ coordinator bị delay/blackhole sau khi request có thể đã được xử lý**. Java có thể thấy timeout. Sau đó đọc:

~~~sql
SELECT status, version
FROM retry_lab.jobs_by_id
WHERE job_id = 11111111-1111-4111-8111-111111111111;
~~~

Nếu version là 2, thao tác có thể đã commit dù client thấy timeout. Nếu chưa đổi, vẫn không được kết luận mọi timeout tương tự đều an toàn để retry. Ghi outcome UNKNOWN, reconcile bằng operation ID/version và chiến lược của service.

### 11.4. Case C — counter không được retry như SELECT

Một bảng riêng **chỉ cho lab**:

~~~sql
CREATE TABLE IF NOT EXISTS retry_lab.request_counter (
  counter_id uuid PRIMARY KEY,
  total counter
);

UPDATE retry_lab.request_counter
SET total = total + 1
WHERE counter_id = 22222222-2222-4222-8222-222222222222;
~~~

Nếu response của UPDATE counter bị mất rồi request được gửi lại, giá trị có thể tăng 2. **Không** đánh dấu counter increment `setIdempotent(true)` chỉ vì muốn có automatic retry. Khi cần count exactly-once theo nghiệp vụ, nên thiết kế aggregation/dedup từ event ID thay vì giả định counter write được retry an toàn.

### 11.5. Case D — ba lớp retry độc lập

Thiết lập thử nghiệm proxy/mock (không đổi mã Driver production):

~~~text
Client attempts: 3
Service A attempts: 3
Service B attempts: 3
Driver recoverable attempts: đo thực tế (không ép giả định)

Ghi số HTTP calls và CQL executions trên mỗi business_request_id.
Đo p99, inflight, retry budget exhausted và backend throughput.
Sau đó bỏ retry ở hai lớp, đo lại khi giữ tải lỗi giống nhau.
~~~

So sánh phải giữ cùng lỗi kích hoạt, tỷ lệ request, dữ liệu và CL. Nếu layer nào retry chỉ trong một số lỗi, kết quả thực có thể thấp hơn cận tích. **Mục tiêu** là chứng minh retry fan-out bằng telemetry, không phải tạo ra đúng 27 hay 54 requests bằng mọi giá.

### 11.6. Case E — deadline và paging

Truy vấn hàng nghìn records với page size nhỏ. Nếu cả query có 10 trang, `basic.request.timeout` áp cho các CQL requests tương ứng, không tự bảo đảm **toàn bộ vòng lặp paging** nằm trong 1.500 ms. Trong code đọc nhiều trang, kiểm tra `deadline.remaining()` **trước khi yêu cầu/fetch trang tiếp theo**, giới hạn số trang/rows và ngắt tiêu thụ khi caller đã hết budget.

## 12. Ma trận kiểm thử

| Tình huống | Mong đợi | Điều không được làm |
|---|---|---|
| Backend khỏe | Một request nghiệp vụ tạo số CQL executions gần mức thiết kế | Bật retry/speculation khi không cần |
| Một replica chậm | DefaultRetryPolicy chỉ retry những trường hợp được hỗ trợ | Retry mọi lỗi đến khi đạt CL |
| Mất toàn local DC | Fail fast đúng chính sách locality/DR | Tự hạ CL và failover qua remote DC không phê duyệt |
| `WriteTimeoutException` | Outcome mutation có thể UNKNOWN | Trả “chưa ghi” và gửi lại vô hạn |
| `ReadTimeoutException` transient | Có thể thử lại trong budget nếu read idempotent | Mỗi microservice tăng attempts riêng |
| CQL syntax/authorization error | Dừng/sửa CQL hoặc role | Backoff rồi gửi cùng request mãi |
| Cassandra overload | Giảm admission và retry budget | Đổ thêm requests để “vượt qua” overload |
| Request đã quá deadline | Không gửi thêm CQL/retry | Reset timeout ở repository |
| User POST bị timeout | Idempotency/reconcile trước replay | Tạo đơn/side effect lần hai |
| Speculative execution bật | Theo dõi số executions phụ và stream IDs | Coi nó là miễn phí hay cancellable server-side |
| Paging dài | Bảo vệ deadline trên toàn loop | Cho mỗi page timeout mới vô hạn |
| LWT false | Conflict đúng theo business invariant | Phân loại thành retryable network error |

### 12.1. Bảng đo thực nghiệm

| Metric | Baseline | Fault injection | Sau điều chỉnh retry | Mục tiêu |
|---|---|---|---|---|
| P95/P99 business latency | _điền_ | _điền_ | _điền_ | Theo SLO |
| HTTP requests / original action | _điền_ | _điền_ | _điền_ | Không nhân ngoài budget |
| CQL executions / business request | _điền_ | _điền_ | _điền_ | Bị giới hạn có đo |
| Retry attempts/s | _điền_ | _điền_ | _điền_ | Trong retry budget |
| DriverTimeout / ReadTimeout / WriteTimeout | _điền_ | _điền_ | _điền_ | Phân loại riêng |
| UNKNOWN write outcomes | _điền_ | _điền_ | _điền_ | Có reconcile |
| Driver pool in-flight/available streams | _điền_ | _điền_ | _điền_ | Không chạm ngưỡng cạn |
| Throttling queue size/delay | _điền_ | _điền_ | _điền_ | Không giữ request hết hạn |
| Cassandra p99/GC/compaction | _điền_ | _điền_ | _điền_ | Không tạo cascading failure |
| Duplicate business effects | _điền_ | _điền_ | _điền_ | 0 nếu nghiệp vụ bắt buộc |

**Đếm cả các attempts ẩn**: gateway retries, HTTP client retries, service retries, driver retries, speculative executions và queue redeliveries. Trên Java Driver 4.x, các metrics **mặc định bị tắt**, phải kích hoạt loại metrics cần dùng theo tài liệu và kiểm tra chi phí quan sát. Không giả mạo số liệu từ một request mẫu.

## 13. Kỹ thuật chống cascading failure ngoài retry

### 13.1. Concurrency limit và queue có chiều dài hữu hạn

Theo định luật Little, với thông lượng đầu vào ổn định, thời gian xử lý tăng thường khiến số request in-flight tăng. Khi Cassandra chậm, một hàng đợi vô hạn sẽ tích lũy **những request đã hết giá trị do deadline quá hạn**.

Giới hạn phù hợp:

- Số request đồng thời ở HTTP service và mỗi CqlSession/workload class.
- Số jobs trong queue, có chính sách bỏ jobs hết hạn.
- Số active retries và retry tokens; ưu tiên requests mới có cơ hội thành công hơn hàng loạt retry cũ.
- Số connection streams/pool và độ trễ throttler queue; tránh để pool hết stream IDs rồi đổ thêm lỗi và retry.

Java Driver 4.x cung cấp `ConcurrencyLimitingRequestThrottler`/`RateLimitingRequestThrottler` nếu bạn cần throttling theo session, nhưng không mặc định biến việc xếp hàng thành hoàn tất nhanh. Thời gian chờ queue vẫn tính vào Driver request timeout; cần đo `throttling.delay`, `throttling.queue-size` và `throttling.errors`.

### 13.2. Fail fast có thể tốt hơn retry

Nếu local DC không đủ replica để thỏa `LOCAL_QUORUM`, thử lặp một cách bừa bãi ít có khả năng thành công và có thể tăng overload. Cần bảo toàn chính sách nhất quán; **không tự chuyển `LOCAL_QUORUM → ONE`** chỉ để giảm HTTP 5xx.

Mặt khác, khi một coordinator có thông tin membership lỗi thời, retry một lần sang coordinator khác theo DefaultRetryPolicy có thể hữu ích. Vì vậy lựa chọn tốt không phải “cấm mọi retry”, mà là **chỉ retry lỗi có khả năng phục hồi với chi phí và deadline được kiểm soát**.

### 13.3. Hedging/speculation phải tính vào retry budget

Một read được gửi đồng thời đến hai coordinator có thể trả nhanh hơn, nhưng vẫn là **hai executions** cạnh tranh tài nguyên. Nếu mức tải hiện tại gần capacity, thêm hedging có thể làm p99 tổng hệ thống tệ hơn.

Đừng chỉ tính số lần `session.execute` được gọi từ Java: **một execute có thể tạo hơn một execution** khi speculative policy được bật. Đo thực bằng Driver metrics/tracing mẫu thấp và Cassandra request counters.

## 14. Các ngộ nhận thường gặp

| Ngộ nhận | Vì sao sai | Cách xử lý |
|---|---|---|
| “Mỗi lớp timeout 2 giây là tổng nghiệp vụ 2 giây” | Nhiều bước/attempts có thời gian cộng dồn | Deadline đầu-cuối và remaining budget |
| “Retry ba lần ở mỗi layer chỉ tốn thêm vài lần” | Attempts **nhân**, không cộng | Một retry owner, đếm fan-out |
| “Driver 4.x luôn chỉ gửi một request CQL” | Default policy, pre-send recovery, reprepare và speculative policy | Đọc config/metrics và test |
| “basic.request.timeout là HTTP deadline” | Nó áp cho một execute, không cho workflow | Propagate deadline ở service |
| “Write timeout = mutation chưa được ghi” | Một số replicas có thể đã ghi hoặc ACK mất | UNKNOWN/reconcile/idempotency |
| “DefaultRetryPolicy retry mọi error” | Chỉ những điều kiện an toàn và phù hợp | Kiểm tra loại lỗi và idempotence |
| “Driver request mặc định idempotent” | Driver 4 mặc định false | Gắn theo semantics từng statement |
| “Cứ setIdempotent(true) là an toàn” | Counter, list prepend, TTL, side effects không tự an toàn | Đánh giá invariant nghiệp vụ |
| “LWT false có thể retry như timeout” | False là precondition không thỏa | Conflict hoặc tính lại CAS |
| “Backoff fixed 100 ms đủ tránh đỉnh tải” | Client dễ đồng bộ thời điểm thử lại | Full jitter + cap |
| “Jitter thay cho deadline/maxAttempts” | Delay ngẫu nhiên vẫn có thể kéo dài mãi | Budget + stop conditions |
| “Hủy future nghĩa Cassandra undo mutation” | Server có thể vẫn đang xử lý | Không phát thêm attempt; reconcile nếu cần |
| “Đổi QUORUM xuống ONE để chống timeout” | Có thể phá guarantee nhất quán | Giữ CL; sửa capacity/availability |
| “Retry khi overload sẽ giúp tự phục hồi” | Retry gây positive feedback tăng tải | Load shedding, token budget, circuit breaker |
| “Timeout per page giới hạn toàn paging” | Các trang sau phát sinh requests khác | Kiểm tra outer deadline mọi bước |

## 15. Bài tập tình huống

### Bài 1 — Tính số attempts tối đa

Gateway có 3 attempts, service có 2, Driver có thể thực hiện 2 executions cho mỗi service call. Một hành động người dùng tối đa tạo bao nhiêu executions ở Cassandra?

**Đáp án:** `3 × 2 × 2 = 12` executions trong cận thiết kế. Không phải 3+2+2=7; kết quả thực phụ thuộc loại lỗi, policy và điều kiện dừng.

### Bài 2 — Budget còn quá ít

Deadline toàn nghiệp vụ 1.200 ms. Sau auth và cache còn 180 ms; giữ 100 ms để trả HTTP và một lần CQL có p99 250 ms. Có nên cấp timeout 600 ms rồi retry không?

**Đáp án:** không. Usable chỉ còn 80 ms, thấp hơn thời gian tối thiểu có ích; nên fail fast/điều chỉnh workflow hoặc dùng phương án async theo hợp đồng. Không reset deadline tại repository.

### Bài 3 — Retry counter

Ứng dụng `UPDATE counter = counter + 1`; nhận timeout, bật `setIdempotent(true)` rồi retry. Hậu quả?

**Đáp án:** có thể tăng 2 lần vì lần đầu đã áp dụng. Cần dedup/event ID/reconciliation thay vì coi counter mutation idempotent.

### Bài 4 — Deadline và driver timeout

`basic.request.timeout = 2 seconds`. Gateway cho endpoint tối đa 800 ms, service bắt đầu CQL khi còn 200 ms. Có đảm bảo request trả trước 800 ms không?

**Đáp án:** không. Driver timeout 2 giây chỉ giới hạn một lần execute; phải tính `remaining - reserve` và đặt timeout theo nó. Nếu quá ít thời gian thì không gửi.

### Bài 5 — LWT false sau timeout

Service gửi `UPDATE ... IF version=4`, bị timeout; retry nhận `wasApplied=false` và version hiện tại là 5. Có chắc lần đầu thất bại?

**Đáp án:** không. Lần đầu có thể đã ghi version 5 rồi mất ACK. Dùng operation ID/invariant state để reconcile, không trả conflict giả định.

### Bài 6 — Full jitter

`base=40 ms`, `cap=320 ms`. Cửa sổ delay cho retry thứ 1–5 là gì?

**Đáp án:** 0–40, 0–80, 0–160, 0–320, 0–320 ms; sample ngẫu nhiên trong cửa sổ, không ngủ cố định ở đầu trên.

### Bài 7 — Layered retries khi overload

Sau khi Cassandra quá tải, HTTP error tăng, tất cả microservices tăng maxAttempts từ 2 lên 5. Tại sao hệ thống tệ hơn?

**Đáp án:** số requests vào backend bị nhân qua các lớp, kéo dài queue/GC/timeout; tạo feedback loop. Cần giảm tải, một retry owner, budget và backoff/jitter thay vì mở rộng attempts.

### Bài 8 — Cancellation

Người dùng đóng trình duyệt; service cancel `CompletionStage` Java Driver, rồi tuyên bố “Cassandra chắc chắn chưa ghi”. Đúng không?

**Đáp án:** không. Hủy phía client không đảm bảo hủy một mutation đã tới server. Không phát thêm requests, ghi outcome unknown khi cần và reconcile sau.

### Checklist cuối bài

- [ ] Có một business deadline toàn luồng, đo bằng monotonic clock trong mỗi JVM.
- [ ] Mỗi downstream timeout <= remaining budget trừ reserve.
- [ ] Không tạo request/retry mới sau khi deadline đã hết.
- [ ] Đếm được attempts ở gateway, service, repository, Driver và queue redelivery.
- [ ] Biết công thức khuếch đại: tích của tổng attempts ở các tầng.
- [ ] Chỉ định **một tầng sở hữu retry chính**; Driver behavior được tính trong budget.
- [ ] Biết DefaultRetryPolicy/Driver 4.x không retry mọi lỗi và idempotence mặc định false.
- [ ] Biết phân biệt DriverTimeout, ReadTimeout, WriteTimeout, Unavailable và overload.
- [ ] Không retry mutation non-idempotent hoặc unknown write outcome khi chưa reconcile.
- [ ] Áp capped exponential backoff + full jitter, maxAttempts và retry token budget.
- [ ] Không sleep/block trong Driver RetryPolicy I/O callback.
- [ ] Có load shedding, bounded queues, concurrency limit và half-open probes hợp lý.
- [ ] Speculative executions được tính vào số attempts thực và capacity budget.
- [ ] Có kiểm thử fault injection, latency p95/p99, timeout/UNKNOWN, duplicate effects và fan-out.

## 16. Tài liệu tham khảo

1. Apache Cassandra Java Driver 4.19 — [Retries](https://apache.github.io/cassandra-java-driver/4.19.0/core/retries/): DefaultRetryPolicy, xử lý Unavailable/ReadTimeout/WriteTimeout, hard-coded recovery và giới hạn.
2. Apache Cassandra Java Driver 4.19 — [Idempotence](https://apache.github.io/cassandra-java-driver/4.19.0/core/idempotence/): flag per-statement, default false, retry/speculation chỉ với request phù hợp.
3. Apache Cassandra Java Driver 4.19 — [Speculative Execution](https://apache.github.io/cassandra-java-driver/4.19.0/core/speculative_execution/): mặc định tắt, executions song song, stream IDs và metric.
4. Apache Cassandra Java Driver 4.19 — [Configuration](https://apache.github.io/cassandra-java-driver/4.19.0/core/configuration/): HOCON, `basic.request.timeout` và execution profiles.
5. Apache Cassandra Java Driver 4.19 — [Statement API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/cql/Statement.html): `setTimeout(Duration)`, `setIdempotent`, immutable statements.
6. Apache Cassandra Java Driver 4.19 — [RetryPolicy API](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/retry/RetryPolicy.html): không block I/O threads và cách tạo custom policy.
7. Apache Cassandra Java Driver 4.19 — [Throttling](https://apache.github.io/cassandra-java-driver/4.19.0/core/throttling/) và [Metrics](https://apache.github.io/cassandra-java-driver/4.19.0/core/metrics/): queue trong request timeout, concurrency limits và quan sát.
8. Google SRE Book — [Addressing Cascading Failures](https://sre.google/sre-book/addressing-cascading-failures/): retry budgets, randomized backoff và tránh retry amplification qua tầng.
9. Amazon Builders' Library — [Timeouts, Retries, and Backoff with Jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/): retry multiplication, deadlines và jitter.
10. Apache Cassandra Documentation — [CQL Data Manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html): semantics của CQL, TTL, counters và LWT.
