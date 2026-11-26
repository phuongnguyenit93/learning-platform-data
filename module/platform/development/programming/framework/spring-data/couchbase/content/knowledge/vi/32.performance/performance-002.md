# Đo đường cơ sở theo độ trễ, thông lượng và lượng dữ liệu truyền

## 1. Vì sao phải đo trước khi tối ưu?

Một nhóm đổi từ `CouchbaseRepository.findById` sang SDK `Collection.get` để giảm độ trễ. Một nhóm khác dùng `lookupIn` thay cho GET toàn bộ JSON, thêm secondary index cho SQL++ hoặc tăng mức đồng thời của reactive pipeline. Nếu không có **đường cơ sở (baseline)** trước khi thay đổi, rất khó biết cải thiện là thật hay chỉ do dữ liệu nhỏ hơn, cache đang nóng, tải ít hơn hoặc lỗi bị bỏ qua.

**Baseline hiệu năng** là tập số đo được thu trong **điều kiện đã mô tả và có thể tái lập**, dùng làm mốc trước khi tối ưu. Trong Spring Data Couchbase, ba trục tối thiểu là:

1. **Độ trễ (latency):** thời gian một request hoặc operation hoàn tất, đặc biệt p50/p95/p99.
2. **Thông lượng (throughput):** số thao tác hoàn tất mỗi giây, phân biệt thành công, lỗi và retry.
3. **Lượng dữ liệu truyền (data transfer):** byte ở tầng JSON, SDK, HTTP và mạng thật, được định nghĩa tách biệt.

Bài thuộc chương **Hiệu năng** của module **SPRING_DATA_COUCHBASE**. Phạm vi module là xây dựng tầng dữ liệu Couchbase bằng document mapping, repository, `CouchbaseTemplate` và SQL++; thiết kế bucket/scope/collection, chỉ mục, TTL, CAS, giao dịch và API reactive để đảm bảo hiệu năng, tính nhất quán và khả năng vận hành.

Sau bài học, bạn có thể:

- Định nghĩa workload và SLO trước khi đo.
- Phân biệt latency end-to-end, repository/SDK và server.
- Tính và đọc p50/p95/p99 mà không bị đánh lừa bởi average.
- Phân biệt offered load, completed throughput, goodput và saturation.
- Đo đúng loại byte: logical body, HTTP response và network wire.
- Instrument bằng Micrometer và đối chiếu các metric phía Couchbase.
- Thiết kế benchmark KV/SQL++/reactive công bằng, có warm-up và nhiều mức tải.
- Lập baseline report đủ thông tin để một người khác tái hiện.

Ví dụ dùng Java 17, Spring Boot 3.x, Spring Data Couchbase 5.x, Couchbase Java SDK 3.x và Micrometer ở các phiên bản tương thích. Tên metric SDK/server và chi tiết instrumentation thay đổi theo release, nên ví dụ custom metric **không đồng nghĩa metric SDK tự có**.

## 2. Bắt đầu bằng use case và mục tiêu

Giả sử endpoint lấy đơn hàng:

~~~text
HTTP: GET /orders/{id}
Keyspace: commerce.sales.orders
Document ID: order::O-2026-001
Data path: OrderRepository.findById(...)
Body size: phần lớn 2 KiB, có nhóm 50 KiB
Workload: 100, 300, 600 requests/giây
SLO ví dụ: p99 HTTP dưới 200 ms tại 300 req/s
Error budget ví dụ: lỗi không mong đợi dưới 0,5%
Baseline: latency + goodput + bytes + retry + saturation
~~~

**Tất cả ngưỡng và số liệu là giả định minh họa**, không phải số đo thật. Dự án phải chọn mức tải và SLO từ nhu cầu người dùng/sản phẩm.

Một phiếu benchmark nên ghi:

| Nhóm | Dữ liệu cần xác định |
| --- | --- |
| Nghiệp vụ | Endpoint, tỷ lệ request, trạng thái hợp lệ |
| Đường dữ liệu | Repository, template, SDK KV hay SQL++ |
| Keyspace | Bucket/scope/collection |
| Dataset | Số document, key distribution, JSON sizes |
| Tải | Offered rate, concurrency, thời lượng mỗi phase |
| Client | Java, Spring Data, SDK, JVM heap/GC |
| Cluster | Server version, node layout, Data/Index/Query |
| Mạng | TLS, AZ/region, RTT, proxy |
| Ngữ nghĩa | CAS, durability, consistency, TTL, retry |
| Kết quả | p50/p95/p99, goodput, errors, logical/wire bytes |

Không trộn các request khác nghiệp vụ rồi gọi một con số duy nhất là “Couchbase latency”.

## 3. Xác định ranh giới latency

Một request có nhiều thành phần:

~~~mermaid
flowchart LR
    A["Client HTTP"] --> B["Spring Controller + Auth"]
    B --> C["Repository/Template/SDK"]
    C --> D["SDK queue + network"]
    D --> E["Couchbase Data/Query/Index"]
    E --> F["Network response"]
    F --> G["Mapping + DTO serialization"]
    G --> H["HTTP response"]
~~~

Các ranh giới cần phân biệt:

- **End-to-end client latency:** từ lúc client gửi đến khi nhận response, bao gồm mạng phía client.
- **HTTP server latency:** thời gian trong ứng dụng web, có thể bao gồm xác thực, mapping và downstream.
- **Repository call latency:** gọi tới mapper/repository và nhận entity hoặc lỗi.
- **SDK operation latency:** thời gian client SDK xử lý operation, bao gồm một phần queue/network/server.
- **Couchbase server latency:** thời gian trong Data/Query/Index service theo metric server tương ứng.

Ví dụ SDK operation nhanh hơn 3 ms nhưng service mất thêm 12 ms khi convert JSON và serialize HTTP, endpoint chưa chắc nhanh hơn. **Đo cả end-to-end và data access** để xác định tác động của tối ưu.

### 3.1. Đo elapsed time bằng đồng hồ đơn điệu

Để đo thời lượng, ưu tiên `System.nanoTime()` hoặc `Timer`. Không lấy chênh lệch `Instant.now()` làm nguồn duy nhất cho benchmark vì wall clock có thể được điều chỉnh.

~~~java
long started = System.nanoTime();
try {
    return orders.get(key);
} finally {
    long nanos = System.nanoTime() - started;
    // Ghi vào Timer/histogram thay vì log từng request.
}
~~~

Không `System.out.println` trong mỗi hot request khi chạy benchmark; logging đồng bộ có thể trở thành bottleneck.

## 4. p50, p95, p99 quan trọng hơn một con số trung bình

| Metric | Ý nghĩa |
| --- | --- |
| p50 | Khoảng 50% request có latency không vượt giá trị này |
| p95 | Khoảng 95% request có latency không vượt giá trị này |
| p99 | Khoảng 99% request có latency không vượt giá trị này |
| average | Tổng latency chia số request; có thể che phần đuôi |
| max | Request chậm nhất trong tập mẫu, dễ chịu outlier |

Một bảng **giả định minh họa**:

| Chỉ số | HTTP latency |
| --- | ---: |
| p50 | 24 ms |
| p95 | 95 ms |
| p99 | 180 ms |
| Average | 38 ms |
| Max | 920 ms |

Một tối ưu có thể giảm average nhưng lại làm p99 tăng vì GC, network retry hoặc queue ở tải cao. Với hot endpoint, p95/p99 và error rate thường là chỉ số ra quyết định quan trọng.

### 4.1. Không lấy trung bình p99 của các instance

Percentile không có tính cộng trung bình như throughput. Trung bình của p99 từ 5 instances **không phải** p99 của toàn bộ fleet.

Muốn tổng hợp cần histogram buckets hoặc latency distribution có thể merge theo cùng cửa sổ thời gian và cấu hình bucket. Micrometer client-side percentiles và histogram aggregate ở Prometheus có semantics khác nhau.

### 4.2. Mẫu quá ít làm p99 thiếu ổn định

Chạy 20 lần GET rồi báo p99 không đủ cơ sở cho nhiều workload. Cần đủ request hoàn tất để có tail observations, ghi sample count và duration. Không có một ngưỡng mẫu chung phù hợp mọi phân bố; xác định mức tin cậy bằng số liệu và độ biến thiên.

## 5. Throughput và offered load không giống nhau

- **Offered load:** số yêu cầu load generator cố gửi mỗi giây.
- **Completed throughput:** số yêu cầu được hoàn tất mỗi giây.
- **Goodput:** số yêu cầu nghiệp vụ hữu ích hoàn tất thành công mỗi giây.
- **SDK operation throughput:** số thao tác SDK gửi/hoàn tất mỗi giây; có thể lớn hơn HTTP throughput do fan-out/retry.

Ví dụ giả định:

| Offered req/s | Completed req/s | Unexpected errors | Nhận xét |
| ---: | ---: | ---: | --- |
| 100 | 100 | 0,0% | Dư công suất |
| 300 | 299 | 0,2% | Ổn định |
| 600 | 505 | 3,0% | Queue/saturation |
| 900 | 530 | 12,0% | Độ trễ tăng, ít tăng output |

Không phải benchmark đo được. Khi tăng offered rate mà completed throughput không còn tăng, p99/timeouts tăng, hệ thống có thể đã bão hòa.

### 5.1. Goodput khác retry count

Ví dụ ứng dụng phục vụ 1.000 HTTP requests thành công nhưng SDK phải thực hiện 1.250 KV operations vì retry, thì **1.250 op/s không phải 1.250 yêu cầu nghiệp vụ/s**.

Cần ghi:

- HTTP/business successes/second.
- SDK operations/second.
- Retry attempts/second.
- Timeout/ambiguous outcomes.
- Unexpected errors và cancellations.

Một tối ưu làm operation count tăng nhưng business successes không đổi có thể đang tăng tải cluster.

### 5.2. Phân loại lỗi đúng hợp đồng

Một GET key không tồn tại có thể là **expected miss**, không phải lỗi hạ tầng. Ngược lại, timeout hoặc RBAC failure không được biến thành 404 vì catch-all.

Tách:

1. Success hợp lệ.
2. Expected miss/business rejection.
3. Unexpected error.
4. Timeout/cancelled/in-flight khi kết thúc window.

Nếu chỉ tính latency của success mà loại toàn bộ timeout chậm nhất, báo cáo có thể quá lạc quan.

## 6. Concurrency và luật Little

Trong trạng thái ổn định, luật Little:

\[L = \lambda W\]

Trong đó:

- `L`: số request trung bình trong hệ thống.
- `λ`: thông lượng trung bình, requests/giây.
- `W`: thời gian trung bình một request ở trong hệ thống, giây.

Ví dụ 2.000 req/s và average duration 25 ms tương ứng khoảng 50 requests in-flight ở trạng thái ổn định. Đây là minh họa quan hệ, **không bảo đảm đặt concurrency 50 sẽ tạo được 2.000 req/s**.

Khi queueing tăng, in-flight có thể tăng nhưng throughput không tăng tương ứng. Đừng tăng `flatMap` concurrency, HTTP threads hay pool sizes vô hạn.

### 6.1. Open-loop và closed-loop load

**Closed-loop:** mỗi virtual user gửi request tiếp theo sau khi request trước hoàn thành. Khi hệ thống chậm, tốc độ đến có thể tự giảm.

**Open-loop/arrival-rate:** công cụ cố duy trì tốc độ gửi được ấn định, hữu ích để nhìn rõ hệ thống đáp ứng ra sao khi offered rate tăng.

Chọn mô hình tải theo mục tiêu và ghi rõ trong báo cáo. Nếu closed-loop làm offered load sụt khi latency tăng, đừng kết luận cluster vẫn ổn định chỉ vì request rate không tăng nữa.

### 6.2. Coordinated omission

Nếu load generator ngừng gửi request trong khoảng hệ thống bị chậm, các thời gian chờ mà người dùng thực tế có thể gặp sẽ bị bỏ qua. Đây là rủi ro **coordinated omission**. Hiểu công cụ tính latency/arrival schedule thế nào và dùng mô hình đo nhất quán giữa baseline/candidate.

## 7. “Bytes transferred” phải chỉ rõ tầng đo

| Tầng | Đo gì | Cách đo gợi ý |
| --- | --- | --- |
| KV document body | Serialized JSON bytes đã decode ở client | SDK `contentAsBytes().length` khi hỗ trợ |
| SDK/protocol | Body + metadata + protocol framing | Telemetry/protocol metrics thích hợp |
| Wire/network | Số byte thực qua mạng, có TLS/compression/retry | Network counters, capture được phép |
| HTTP response body | Serialized DTO bytes trả cho caller | HTTP instrumentation |
| SQL++ result | Rows/metadata được trả về | Query telemetry và logical row-size estimate |

**Không dùng byte length của Java String để biểu diễn số byte trên mạng.** UTF-8 có thể dùng nhiều byte cho một ký tự; TLS/protocol overhead và compression cũng thay đổi wire bytes.

### 7.1. Số byte logical và wire có thể khác nhau

Nếu document sau giải nén có 50 KiB JSON nhưng compression tốt, network response body có thể nhỏ hơn 50 KiB. Ngược lại, framing/TLS/retries có thể tăng tổng byte thực.

Một SQL++ response chỉ gồm ba field HTTP có thể nhỏ dù Query service đã scan/fetch nhiều rows nội bộ. Phải phân biệt **data processed** và **data returned**.

### 7.2. Đơn vị

- `KiB` = 1.024 bytes.
- `MiB` = 1.048.576 bytes.
- `MB` = 1.000.000 bytes theo quy ước thập phân.
- `Mbps` thường là triệu bit/s, khác MiB/s.
- Một byte gồm 8 bit.

Một báo cáo chỉ ghi “10 MB traffic” không rõ đơn vị, chiều dữ liệu hay thời gian đo sẽ khó so sánh.

## 8. Ước tính logical payload throughput

Với `N` successful operations và byte body `B_i`:

\[B_{logical,total}=\sum_{i=1}^{N}B_i\]

Trong khoảng `T` giây:

\[R_{logical}=B_{logical,total}/T\]

Ví dụ giả định 1.000 GET/s, response body trung bình 4 KiB:

~~~text
1.000 GET/s * 4 KiB/GET = 4.000 KiB/s
                        ≈ 3,9 MiB/s logical body
Không tính:
  KV request/protocol metadata
  TLS framing, retransmission
  compression và retry
  HTTP response ở tầng API
~~~

Đây **không phải phép đo NIC**. Muốn đánh giá giới hạn network/egress cần counter thực ở tầng mạng.

### 8.1. Tail payload size

Hai nhóm cùng average 4 KiB nhưng khác tail:

- 99% documents 1 KiB, 1% rất lớn.
- Mọi document khoảng 4 KiB.

Nhóm thứ nhất có thể gây spike p99, memory allocation và bandwidth. Vì vậy cần theo dõi distribution kích thước JSON (p50/p95/p99 bytes) chứ không chỉ average.

## 9. Thiết kế workload đại diện

Một baseline cần mô tả ít nhất:

| Yếu tố | Vì sao quan trọng |
| --- | --- |
| Document count | 100 nghìn khác 50 triệu |
| JSON size distribution | GET 2 KiB khác GET 200 KiB |
| Key popularity | Uniform khác hot keys/Zipf-like |
| Hit/miss ratio | Missing key và hit có đường xử lý khác |
| Read/write mix | GET khác CAS replace/transaction |
| Query selectivity | Trả 1 row khác trả 1.000 rows |
| Index definitions | Query plan và tài nguyên khác |
| Consistency/durability | Bảo đảm mạnh hơn có thể tốn latency |
| TTL/maxTTL | Key hết hạn có thể làm hit ratio thay đổi |
| TLS/network placement | RTT và egress khác |
| Cache state | Warm cache khác cold start |

Không benchmark trên 100 documents luôn hot rồi dùng kết quả làm cam kết cho production hàng triệu documents.

### 9.1. Workload nên tách thành các đường

1. SDK KV GET bằng ID.
2. Repository `findById` của cùng entity.
3. SQL++ query lọc theo field có index.
4. KV GET document lớn hoặc subdocument `lookupIn`.
5. UPSERT/REPLACE theo CAS, có TTL/expiry options.
6. Multi-key reads với concurrency giới hạn.
7. Reactive pipeline thực tế nếu ứng dụng dùng WebFlux.

Mỗi đường có histogram, throughput và bytes riêng. Một trung bình chung sẽ che mất bottleneck.

## 10. Chuẩn bị dữ liệu và môi trường test

Trước khi đo:

- Tạo keyspace và index theo cấu hình gần production.
- Nạp dữ liệu giả lập, không dùng PII/OTP/session token thật.
- Kiểm tra giá trị `maxTTL` và liệu document có expire trong lúc benchmark.
- Tạo key list cố định theo phân bố hit/miss/hotness mong muốn.
- Giữ tỷ lệ document sizes như workload thực.
- Không chạy index rebuild hoặc migration không liên quan trong đo, trừ khi đó là tình huống muốn kiểm thử.
- Đồng bộ clocks và ghi topology client/cluster.

Ví dụ keyspace:

~~~text
commerce.sales.orders
commerce.checkout.carts
commerce.auth.sessions
commerce.processing.export_jobs
~~~

Cùng một ID ở collection khác có thể cho not-found. Khi so baseline/candidate phải giữ đúng bucket/scope/collection.

### 10.1. Đừng dùng một hot key nếu production có nhiều key

Một benchmark chỉ đọc `order::O-1` liên tục có thể đo cache behavior/hot-key path thay vì traffic thực. Nếu production có nhóm top keys rất nóng, phải mô phỏng **đúng phân bố** thay vì cố uniform.

Với CAS writes, mọi worker ghi một key có thể làm conflict tăng mạnh; đây chỉ là workload hợp lệ nếu production thật có hot key như vậy.

## 11. Ghi rõ môi trường để tái lập

~~~text
Run ID: baseline-performance-002
Commit/application release: <revision>
JDK/Spring Boot/Spring Data/SDK: <versions>
Couchbase Server version/edition: <version>
Node layout: <Data/Query/Index services, CPU/memory>
Keyspace: commerce.sales.orders
Dataset: <count, size distribution, key skew>
TLS/network: <same AZ/cross AZ, RTT, proxy>
Read/write mix: <percentages>
Query consistency: <NOT_BOUNDED/REQUEST_PLUS/etc>
Durability/CAS/TTL: <options>
SDK retry and timeouts: <policy>
JVM heap/GC: <config>
Warm-up: <duration/load>
Measurement: <duration/load>
Arrival rate/concurrency: <values>
Results: <histograms, successes, errors, bytes, saturation>
~~~

Một báo cáo thiếu phiên bản SDK, Query/Index layout hay key distribution sẽ khó tái lập hơn nhiều so với báo cáo có đủ metadata.

## 12. Warm-up, steady state và cold-start test

~~~mermaid
flowchart LR
    A["Provision dataset + index"] --> B["Warm-up"]
    B --> C["Steady-state measurement"]
    C --> D["Export metrics + context"]
    D --> E["Lưu baseline"]
~~~

Warm-up loại bớt nhiễu từ JIT, class loading, TLS handshake, SDK routing discovery, connection pool và cache warming.

Không nên xóa cache server tùy tiện ở production để làm benchmark. Nếu cold-start quan trọng, chạy **một workload cold-start riêng** và ghi rõ nó không cùng điều kiện với steady-state.

Sau mỗi load step, thống kê chỉ tính theo window đã định. Các request in-flight lúc kết thúc phải có quy tắc xử lý rõ, tránh đếm offered như completed.

## 13. Instrument KV GET bằng Micrometer

Đây là **custom app metrics**, không phải tên mặc định của Couchbase SDK:

~~~java
import com.couchbase.client.core.error.DocumentNotFoundException;
import com.couchbase.client.java.Collection;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class OrderKvProbe {

    private final Collection orders;
    private final MeterRegistry registry;
    private final DistributionSummary bodyBytes;

    public OrderKvProbe(Collection orders, MeterRegistry registry) {
        this.orders = orders;
        this.registry = registry;
        this.bodyBytes = DistributionSummary.builder(
                        "app.couchbase.kv.body.bytes")
                .baseUnit("bytes")
                .description("Logical KV response body bytes")
                .tag("collection", "orders")
                .register(registry);
    }

    public byte[] getRaw(String id) {
        Timer.Sample sample = Timer.start(registry);
        String outcome = "success";

        try {
            byte[] bytes = orders.get(id).contentAsBytes();
            bodyBytes.record(bytes.length);
            return bytes;
        } catch (DocumentNotFoundException ex) {
            outcome = "not_found";
            throw ex;
        } catch (RuntimeException ex) {
            outcome = "error";
            throw ex;
        } finally {
            sample.stop(registry.timer(
                    "app.couchbase.kv.get.duration",
                    "collection", "orders",
                    "outcome", outcome
            ));
        }
    }
}
~~~

Ý nghĩa:

- Timer gồm thời gian SDK call và lấy body bytes; **không phải HTTP end-to-end**.
- Body bytes đo **JSON sau decode**, không phải TLS wire bytes.
- Nhãn outcome giúp tách success, not-found, error.
- Không dùng document ID, user ID hay request ID làm metric tag: gây cardinality cực lớn.
- Cần cấu hình Timer histogram nếu muốn aggregate percentiles ở backend.

### 13.1. Đọc p95/p99 đúng cách

Micrometer có thể export histogram hoặc client-side percentiles. Với nhiều instances, phải dùng dữ liệu histogram có bucket đồng nhất để tổng hợp phân bố, không lấy trung bình giá trị p99 từng instance.

Nếu số mẫu thấp, ghi sample count và tránh diễn giải p99 như một SLA có độ tin cậy cao.

## 14. Đo repository và HTTP riêng

Đường đi:

~~~text
HTTP server
  → Authorization + service
    → repository.findById(id)
      → Spring Data mapping + SDK + Couchbase
    → map Entity -> DTO
  → HTTP serialization
~~~

Đặt Timer riêng quanh `repository.findById` để đo đường data access có mapping. Đồng thời, bật HTTP server duration phù hợp trong Spring Boot Actuator/Micrometer hoặc OpenTelemetry để đo request tổng.

Một tối ưu có thể giảm KV latency nhưng tăng DTO conversion hoặc response bytes. Nếu chỉ nhìn Timer repository, dễ kết luận sai.

Cần đối chiếu:

- HTTP p95/p99.
- Repository/SDK p95/p99.
- CPU/GC của ứng dụng.
- Server Data/Query/Index latency.
- Response payload size.

## 15. Reactive: đo từ subscription, không phải từ lúc dựng Mono

Với Reactor, Publisher có thể chưa chạy khi service tạo object `Mono`. Nếu bắt đầu timer lúc build pipeline, thời gian chờ trước subscription có thể làm sai phép đo.

~~~java
import java.util.concurrent.TimeUnit;
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.Timer;
import reactor.core.publisher.Mono;

Mono<byte[]> readReactive(
        String id, Timer duration, DistributionSummary bodyBytes) {

    return Mono.defer(() -> {
        long started = System.nanoTime();

        return orders.reactive()
                .get(id)
                .map(r -> {
                    byte[] bytes = r.contentAsBytes();
                    bodyBytes.record(bytes.length);
                    return bytes;
                })
                .doFinally(signal -> duration.record(
                        System.nanoTime() - started,
                        TimeUnit.NANOSECONDS
                ));
    });
}
~~~

Giả định `orders` là Collection trong lớp bao quanh, Timer và DistributionSummary được tạo trước.

- `Mono.defer` bắt đầu một phép đo mới cho từng subscription.
- `doFinally` đo đến complete/error/cancel; phân loại outcome riêng khi báo.
- Concurrency, demand, backpressure và scheduling có thể ảnh hưởng latency.
- `Mono.timeout` là timeout pipeline, không phải document TTL.
- Không dùng `block()` trên WebFlux event loop trong benchmark.

## 16. SQL++ baseline: ghi cả query plan và consistency

Ví dụ:

~~~sql
SELECT META(o).id AS id, o.status, o.total
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = $customerId
  AND o.status = $status
LIMIT 20;
~~~

Một query benchmark phải lưu:

1. Statement và parameters.
2. Index definitions và trạng thái.
3. `EXPLAIN` plan.
4. Số document match và số rows trả về.
5. Projection và logical result size.
6. Scan consistency: `NOT_BOUNDED`, `REQUEST_PLUS` hoặc token-based khi phù hợp.
7. Query timeout và retry.
8. Query/Index/Data service metrics.

`REQUEST_PLUS` có mục tiêu index visibility khác `NOT_BOUNDED`. Benchmark thay đổi consistency đồng thời với tối ưu SQL++ là **khác correctness contract**, không phải so sánh hiệu năng công bằng.

### 16.1. Một query trả ít bytes vẫn có thể scan rất nhiều

~~~sql
EXPLAIN
SELECT META(o).id AS id, o.status
FROM `commerce`.`sales`.`orders` AS o
WHERE o.customerId = "u-42";
~~~

Query có thể trả 20 rows nhưng plan đọc nhiều index entries hoặc fetch nhiều document. Logical response bytes không bằng internal processing cost; xem index scan, fetch, sort và Query/Index CPU.

### 16.2. Ước lượng result bytes

Nếu đã có `QueryResult.rowsAsObject()`, có thể serialize lại từng row thành UTF-8 để **ước lượng logical JSON bytes**, nhưng không phải wire bytes:

~~~java
import java.nio.charset.StandardCharsets;
import com.couchbase.client.java.json.JsonObject;

long logicalBytes = 0L;
for (JsonObject row : queryResult.rowsAsObject()) {
    logicalBytes += row.toString()
            .getBytes(StandardCharsets.UTF_8).length;
}
~~~

Phép tính này có overhead serialization thêm; không nhất thiết nên bật trên mọi hot query production. Bỏ qua metadata/protocol/compression nên **không dùng làm network billing**.

## 17. Quan sát phía SDK và Couchbase Server

Custom app metrics chỉ là một phần. Hãy đối chiếu metrics/tracing SDK và Server theo version:

| Tầng | Tín hiệu |
| --- | --- |
| SDK | Operation latency, timeouts/retries, queue/in-flight nếu có |
| Data service | KV operation rate, CPU, memory, disk, latency |
| Query service | Query duration, request/errors, queue |
| Index service | Scan rate, index health/lag, memory |
| JVM | CPU, heap, GC pauses, threads, allocation |
| Network | Ingress/egress, RTT, retransmits, bandwidth |
| HTTP app | Duration, status mix, response bytes |

Không đo toàn bộ Data/Query/Index server CPU rồi quy hết cho một endpoint nếu nhiều ứng dụng cùng dùng cluster.

### 17.1. Tracing khác histogram

Distributed tracing giúp thấy **một request** chậm ở phần nào. Histogram giúp biết **phân bố hàng nghìn requests**.

Không lấy một trace p99 “đại diện” rồi thay thế thống kê. Với nested spans, không cộng duration cha và con vì thời gian bị tính lặp.

## 18. Đo network bytes có kiểm soát

Các nguồn có thể dùng:

- Host/container interface counters.
- Network metrics ở service mesh/proxy nếu có.
- Couchbase Server network metrics phù hợp.
- SDK instrumentation hoặc connection telemetry theo bản đang chạy.
- Packet capture được phê duyệt trong môi trường kiểm thử.

Cẩn thận: network counters toàn node chứa traffic nền, DCP/replication, Query/Index, TLS overhead. Nếu đo trước/sau ở cùng cluster có workload khác, không tự suy chênh lệch byte thuộc về endpoint được tối ưu.

Không tắt TLS, log nội dung OTP/session hoặc capture packet chứa PII chỉ để có con số bandwidth. Tuân thủ quy trình bảo mật và retention.

## 19. Đo nhiều mức tải, không chỉ một điểm

Ví dụ kế hoạch thử nghiệm:

~~~text
Pha nạp dataset: hoàn tất trước đo
Warm-up: theo thời lượng và workload đã định
Step A: offered 100 req/s, đo steady state
Step B: offered 300 req/s, đo steady state
Step C: offered 600 req/s, đo steady state
Step D: offered 900 req/s, đo steady state
Cooldown: export metrics, dừng load
~~~

Tại mỗi bước ghi:

- Offered vs completed requests/second.
- Goodput và expected misses.
- p50/p95/p99 cùng sample count.
- Timeout/retry/error rate.
- Logical JSON bytes/s, HTTP bytes/s, network egress.
- CPU, memory, GC, SDK queue, Data/Query/Index load.

Không trộn histogram ở step A và step D rồi báo một “p99 chung” không nêu tải. Nếu throughput không tăng nữa nhưng p99 tăng, có thể đã bão hòa.

## 20. Chọn công cụ tạo tải đúng mục tiêu

Nếu muốn đo HTTP endpoint, có thể dùng k6, Gatling, JMeter hoặc công cụ HTTP có điều khiển arrival-rate, concurrency và thu thập latency. Với KV SDK trực tiếp, dùng harness chuyên biệt kiểm soát số operations và kết quả, không giả định một HTTP benchmark là benchmark KV.

**JMH** phù hợp hơn cho microbenchmark Java như serialization, mapper CPU hoặc thuật toán tạo key; không tự thay thế bài test distributed throughput và network latency end-to-end.

Load generator phải đủ CPU/socket/network capacity. Nếu chính nó nghẽn, offered rate thực giảm, baseline sẽ sai.

## 21. Quy trình baseline có thể tái lập

~~~mermaid
flowchart TD
    A["Chọn use case + SLO"] --> B["Chốt dataset, key distribution"]
    B --> C["Khóa versions/topology/config"]
    C --> D["Provision index, warm-up"]
    D --> E["Chạy các load steps"]
    E --> F["Thu latency, goodput, bytes, errors"]
    F --> G["Xác định bottleneck"]
    G --> H["Lưu baseline + raw histograms"]
    H --> I["Thay một biến tối ưu"]
    I --> J["Chạy lại cùng workload"]
~~~

Trình tự:

1. Xác định use case, response contract và acceptance criteria.
2. Chọn đường dữ liệu cần đo: KV, repository, template, SQL++.
3. Chuẩn bị dataset đủ lớn với size/key distribution đại diện.
4. Khóa versions, timeout/retry, durability/consistency, TLS/network.
5. Warm-up, kiểm tra client/server đã sẵn sàng.
6. Chạy load steps đến vùng tải mục tiêu và gần saturation.
7. Thu các histogram/throughput/bytes/errors cùng timestamps.
8. Kiểm tra client có tạo được offered load và server có resource bottleneck không.
9. Lưu artifacts/run ID và toàn bộ config.
10. Thực hiện tối ưu từng yếu tố, kiểm thử correctness rồi đo lại cùng điều kiện.

Chỉ thay query plan, projection, batch size hoặc concurrency rồi kết luận từ số đo khi **các biến khác được giữ ổn định** hoặc đã ghi rõ.

## 22. Mẫu bảng kết quả baseline

**Toàn bộ số trong bảng sau là giả lập minh họa, không phải benchmark đã thực hiện:**

| Workload | Offered/s | Goodput/s | p50 | p95 | p99 | Avg logical body | Unexpected errors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| KV GET 2 KiB | 300 | 298 | 7 ms | 19 ms | 42 ms | 2 KiB | 0,2% |
| Repo findById 2 KiB | 300 | 297 | 10 ms | 25 ms | 55 ms | 2 KiB | 0,3% |
| SQL++ query 20 rows | 100 | 99 | 22 ms | 80 ms | 170 ms | 15 KiB | 0,5% |
| KV GET 50 KiB | 300 | 294 | 17 ms | 68 ms | 140 ms | 50 KiB | 0,8% |

Không so row SQL++ trả 20 rows với row KV trả một document rồi tuyên bố toàn bộ chênh lệch do Query overhead: **khối lượng công việc khác nhau**.

### 22.1. Tác động của payload size

GET 50 KiB có thể làm network, serialization và GC cao hơn GET 2 KiB. Nếu thay SDK/repository nhưng kích thước JSON cũng thay đổi, cần phân tách tác động.

### 22.2. Tác động của mapper

Repository findById có converter/entity mapping. SDK `contentAsBytes` trả bytes trực tiếp. Để so công bằng theo endpoint, phải tính cả việc SDK path còn cần decode/map thành DTO, không chỉ so thời gian lấy raw bytes.

## 23. Bảng before/after sau khi tối ưu projection

**Số liệu giả định để học cách đọc báo cáo:**

| Metric | Baseline | Candidate | Đánh giá |
| --- | ---: | ---: | --- |
| HTTP p50 | 35 ms | 31 ms | Có cải thiện |
| HTTP p95 | 130 ms | 100 ms | Tail giảm |
| HTTP p99 | 260 ms | 185 ms | Tail giảm trong tải đo |
| Goodput | 400 req/s | 440 req/s | Output hữu ích tăng |
| Avg JSON body | 48 KiB | 6 KiB | Giảm logical payload |
| Network egress | 25 MiB/s | 10 MiB/s | Cần đo cùng tầng |
| Unexpected errors | 0,3% | 0,4% | Kiểm tra error budget |

Kết luận chỉ hợp lệ nếu dataset, offered load, key distribution, cache, index, timeout và correctness giống nhau. Nếu errors tăng vượt SLO, candidate chưa chắc đạt dù p99 giảm.

## 24. Chẩn đoán: p99 cao nhưng average đẹp

Khả năng:

- GC pause/CPU throttling ở JVM.
- SDK queue hoặc connection saturation.
- Hot keys, CAS conflict hoặc retry storm.
- Query phải đợi scan consistency/index.
- Một tỷ lệ nhỏ document rất lớn.
- Network jitter hoặc cross-zone latency.

Cách điều tra: xem histogram theo kích thước document và operation, SDK/server metrics, application CPU/GC, retries và tracing.

Đừng chỉ tăng KV timeout; nó có thể che dấu queue và làm p99 tệ hơn.

## 25. Chẩn đoán: throughput không tăng khi concurrency tăng

Khả năng:

- Data service/Query service đã bão hòa CPU, memory hoặc I/O.
- Client event loop bị block hoặc thiếu thread.
- Network interface đạt giới hạn.
- Query index hoặc SORT/FETCH tốn tài nguyên.
- Một key được cập nhật quá nhiều dẫn đến CAS contention.
- Retry tăng, làm operation rate cao nhưng business goodput thấp.

Nếu throughput plateau và p99 tăng, nên tìm bottleneck trước khi tăng thêm concurrency. Reactive `flatMap(..., 128)` không tự làm Data service có thêm capacity.

## 26. Chẩn đoán: bytes tăng nhưng số requests không đổi

Các nguyên nhân hay gặp:

- API trả toàn bộ document thay vì chỉ field cần dùng.
- Query trả nhiều rows do filter/limit sai.
- Cùng key bị GET nhiều lần trong một request.
- Retry hoặc phản hồi lỗi dài tăng.
- Compression đổi cấu hình.
- Proxy/TLS hoặc network placement khác.
- Query plan đọc nhiều dữ liệu trước khi trả projection.

Đo đồng thời logical body bytes và network egress. Nếu logical body giữ nguyên mà egress tăng, kiểm tra retry/protocol/traffic nền thay vì chỉ thay JSON mapping.

## 27. Consistency, durability và TTL là biến phải khóa

Hai đường có thể khác độ trễ vì khác **bảo đảm**, không phải code nhanh/chậm:

- SQL++ `NOT_BOUNDED` khác `REQUEST_PLUS`.
- Write thường khác write với mức durability yêu cầu cao.
- `replace` có CAS khác `upsert` vô điều kiện.
- Transaction nhiều document khác KV mutation một document.
- `getAndTouch` làm mới TTL, khác `get` đọc thuần.
- Cache hit khác SDK operation mới.
- Query có index khác Query full scan.

Một tối ưu bằng cách bỏ CAS hoặc hạ consistency có thể “nhanh” nhưng sai nghiệp vụ. Baseline/candidate phải giữ **cùng contract**.

## 28. Multi-key reads và fan-out

Một endpoint cần 40 document keys; nếu dùng blocking GET tuần tự, network round trips có thể cộng dồn. Reactive có thể làm nhiều KV reads đồng thời:

~~~java
import com.couchbase.client.core.error.DocumentNotFoundException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<byte[]> bodies =
        Flux.fromIterable(orderIds)
                .flatMap(
                        id -> orders.reactive()
                                .get(id)
                                .map(result -> result.contentAsBytes())
                                .onErrorResume(
                                        DocumentNotFoundException.class,
                                        ignored -> Mono.empty()
                                ),
                        16
                );
~~~

Con số 16 chỉ là ví dụ. Đo latency **cả batch**, số operations, body bytes, retries và tổng in-flight trên mọi service instances. Một endpoint giảm p50 nhờ fan-out có thể gây saturation trên cluster ở tải cao.

## 29. Metrics không được làm méo benchmark

Không log mọi key, serialize JSON lại nhiều lần hoặc tạo tracing spans chứa payload trên mỗi request nếu mục tiêu là đo đường baseline production.

Thực hành:

- Dùng Timer/histogram thay log đồng bộ.
- Tag có cardinality thấp: operation, collection, outcome.
- Tránh tag document key/user ID/request ID.
- Chọn tracing sampling phù hợp.
- Đo overhead instrumentation nếu thay công cụ giữa baseline/candidate.
- Không log OTP/session token, credential hoặc PII.
- Đo payload bằng byte[] sẵn có nếu có thể.

**Mức instrumentation cần tương đương production** nếu muốn kết quả có giá trị vận hành.

## 30. Cache có thể tạo ra một “tối ưu” giả

Một cache hit không đi qua Couchbase. Nếu baseline không cache nhưng candidate có cache, độ trễ và SDK operations giảm có thể do cache, không phải do chuyển sang KV hoặc `lookupIn`.

Báo:

- Cache enabled/disabled.
- Hit/miss rate.
- Warm/cold state.
- TTL/invalidation.
- Tác động tới consistency, revocation và authorization.
- Requests/bytes xuống Couchbase khi cache miss.

Không chấp nhận candidate p99 đẹp nếu cache trả session bị revoke hoặc order sai quyền.

## 31. Bài tập tình huống

Một checkout-service có:

~~~text
GET /orders/{id}
GET /orders/{id}/status
GET /customers/{id}/orders?status=PAID
POST /orders/{id}/ship
GET /carts/{id}
GET /reports/revenue?month=2026-11
~~~

Dữ liệu:

~~~text
commerce.sales.orders
commerce.checkout.carts
commerce.auth.sessions
commerce.reporting.daily_totals
~~~

**Nhiệm vụ:**

1. Định nghĩa các ranh giới latency cần đo cho `GET /orders/{id}`.
2. Giải thích vì sao p99 quan trọng hơn chỉ average.
3. Thiết kế các load steps và cách đếm offered/completed throughput.
4. Cho biết `contentAsBytes().length` là loại byte nào.
5. Vì sao phải đo HTTP bytes và network egress riêng?
6. Khi nào dùng `lookupIn` và cần đo gì để chứng minh lợi ích?
7. SQL++ query theo customerId cần lưu plan/index/scan consistency nào?
8. Vì sao không so `REQUEST_PLUS` và `NOT_BOUNDED` như hai phiên bản cùng contract?
9. Với 20 order keys, chọn các mức concurrency nào để benchmark reactive?
10. Khi `POST /orders/{id}/ship` dùng CAS, vì sao không được bỏ CAS để benchmark nhanh hơn?
11. Nếu candidate có p99 tốt hơn nhưng timeout tăng, nên kết luận thế nào?
12. Hãy lập bảng baseline gồm p50/p95/p99, goodput, error, logical bytes, wire bytes và resource usage.

**Định hướng:** đo từng workload với bối cảnh xác định; giữ correctness/consistency; dùng phân bố latency, throughput hữu ích và bytes đúng tầng để ra quyết định tối ưu.

## 32. Checklist trước production

- [ ] Use case, keyspace và response contract được ghi rõ.
- [ ] Phân biệt HTTP, repository, SDK và server latency.
- [ ] Có p50/p95/p99, số mẫu và cửa sổ đo.
- [ ] Không lấy trung bình p99 của các instances.
- [ ] Ghi offered, completed và goodput riêng.
- [ ] Expected misses, business rejections, timeout và lỗi hạ tầng được phân loại.
- [ ] Có retry/cancellation/in-flight stats.
- [ ] Logical JSON bytes, HTTP bytes và network wire bytes không bị trộn.
- [ ] Dùng đúng KiB/MiB/MB/Mbps và byte UTF-8.
- [ ] Dataset size, body-size distribution và key popularity đại diện.
- [ ] Tỷ lệ hit/miss, cache state và TTL được khóa.
- [ ] Query plan/index/consistency được lưu khi dùng SQL++.
- [ ] CAS/durability/transaction semantics giữ nguyên trước/sau.
- [ ] Có warm-up và measurement windows ổn định.
- [ ] Ghi JDK, Spring Data, SDK, Server version, TLS và topology.
- [ ] Load generator đủ capacity, arrival model đã định.
- [ ] Thử nhiều mức tải để phát hiện saturation.
- [ ] Metrics tags cardinality thấp, không tiết lộ secrets.
- [ ] Không để instrumentation tự làm sai kết quả.
- [ ] Lưu report/histograms/config cùng run ID.
- [ ] Candidate được kiểm thử correctness và error budget.
- [ ] Không tuyên bố cải thiện chỉ dựa trên một số average.

## 33. Tổng kết

Đo đường cơ sở trong **Spring Data Couchbase** là việc xác định và đo **đúng workload, đúng ranh giới và đúng đơn vị**, chứ không chỉ ghi trung bình mili giây cho một lệnh GET.

Ba trục phải được xem cùng nhau: **độ trễ p50/p95/p99**, **throughput hữu ích đi kèm tỷ lệ lỗi**, và **lượng byte ở logical payload/HTTP/network**. Baseline còn cần kiểm soát key distribution, document size, index/Query plan, consistency, CAS, TTL, reactive concurrency, retry, cache, topology và warm-up.

Khi lưu được đường cơ sở có thể tái lập rồi so candidate trên cùng điều kiện, bạn mới có căn cứ chọn tối ưu đúng: KV theo key, SQL++ index, subdocument projection, giảm dữ liệu truyền, caching hợp lý hoặc tuning SDK. Một tối ưu có giá trị phải cải thiện hiệu năng **mà không làm sai tính nhất quán và yêu cầu nghiệp vụ**.

