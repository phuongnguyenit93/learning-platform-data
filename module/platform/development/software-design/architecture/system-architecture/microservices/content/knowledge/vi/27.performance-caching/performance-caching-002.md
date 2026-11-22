# Độ trễ đuôi và ảnh hưởng của lời gọi fan-out

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Hiệu năng và bộ nhớ đệm.  
> **Mục tiêu:** giải thích **tail latency** (độ trễ đuôi) trong hệ microservices, ảnh hưởng của các lời gọi fan-out song song hoặc nối tiếp, và cách thiết kế đường xử lý, cache, deadline, concurrency, fallback và quan sát hệ thống để bảo vệ p95/p99, tính đúng đắn và trải nghiệm người dùng.

## 1. Bài toán: một trang nhanh trung bình nhưng rất chậm ở đuôi

Giả sử một hệ thống thương mại điện tử có **Product Page BFF** phục vụ trang chi tiết sản phẩm. Một request từ người dùng có thể khiến BFF gọi:

- Catalog Service để lấy tên, mô tả và ảnh.
- Pricing Service để lấy giá hợp lệ.
- Inventory Service để lấy thông tin tồn kho.
- Reviews Service để lấy đánh giá.
- Recommendation Service để lấy gợi ý.
- Promotions Service để kiểm tra chương trình khuyến mãi.
- Delivery Service để tính thời gian giao dự kiến.

Phần lớn từng dịch vụ phản hồi trong 20–80 ms, nhưng đôi lúc một lời gọi mất 500–900 ms vì cache miss, queue wait, GC pause, network jitter hoặc truy vấn database chậm. Nếu BFF **đợi đủ tất cả kết quả**, một lời gọi chậm làm cả trang chậm.

Nhóm vận hành có thể nhìn thấy trung bình từng dịch vụ là 45 ms và nghĩ rằng hệ thống rất nhanh. Nhưng 1% request chậm của mỗi dependency có thể xuất hiện ở một tỷ lệ lớn request tổng hợp vì **mỗi request cha tạo nhiều cơ hội gặp một nhánh chậm**.

Đây là bài toán **tail latency amplification** do fan-out, đặc biệt quan trọng với API aggregation, GraphQL resolver, service orchestration, search, recommendation, batch lookup và hệ thống nhiều tầng gọi RPC.

## 2. Latency, percentile và tail latency

**Latency** là khoảng thời gian từ một mốc bắt đầu đến kết thúc được định nghĩa. Cần ghi rõ đo ở đâu: client, Gateway, server xử lý, outbound RPC, database, queue hay giao diện render.

**Tail latency** tập trung vào những request chậm nhất của phân phối.

| Metric | Ý nghĩa |
| --- | --- |
| **p50** | Khoảng 50% request không chậm hơn ngưỡng này |
| **p90** | Khoảng 90% request không chậm hơn ngưỡng này |
| **p95** | Khoảng 95% request không chậm hơn ngưỡng này |
| **p99** | Khoảng 99% request không chậm hơn ngưỡng này; 1% nằm ở đuôi chậm |
| **p99.9** | Khoảng 99,9% request không chậm hơn ngưỡng này; 0,1% ở đuôi chậm |
| **Maximum** | Giá trị lớn nhất trong cửa sổ đo, nhạy với outlier và kích thước mẫu |

Ví dụ Inventory Service:

~~~text
p50    32 ms
p90    65 ms
p95    90 ms
p99   280 ms
p99.9 970 ms
~~~

Nếu chỉ báo average 48 ms, đội phát triển dễ bỏ qua nhóm người dùng đang chờ lâu gấp nhiều lần.

**Percentile không phải thời gian của tất cả người dùng.** Khi có ít request, p99.9 có thể không ổn định; cần xem kích thước mẫu, cách tính histogram và khoảng thời gian quan sát.

### 2.1. Các lớp độ trễ

Một request có thể tiêu tốn thời gian ở:

1. DNS, TCP/TLS connection hoặc connection pool acquisition.
2. API Gateway, authentication và routing.
3. Queue đợi thread, coroutine, event loop hoặc semaphore.
4. Application logic, serialization, validation.
5. RPC tới service khác.
6. Database query, lock wait, disk I/O hoặc transaction commit.
7. Retry, backoff, timeout và xử lý fallback.
8. Truyền response và render trên client.

Tối ưu logic Java mất 5 ms có thể không thay đổi p99 nếu 300 ms nằm ở queue wait hoặc một dependency từ xa.

## 3. Fan-out và fan-in

**Fan-out:** một lời gọi cha tạo nhiều lời gọi con.  
**Fan-in:** cha thu thập kết quả để quyết định khi nào có thể hoàn thành.

~~~mermaid
flowchart LR
  Client[Web/Mobile] --> BFF[Product Page BFF]
  BFF --> CAT[Catalog]
  BFF --> PRICE[Pricing]
  BFF --> INV[Inventory]
  BFF --> REV[Reviews]
  BFF --> REC[Recommendations]
  BFF --> DEL[Delivery]
  CAT --> JOIN[Join responses]
  PRICE --> JOIN
  INV --> JOIN
  REV --> JOIN
  REC --> JOIN
  DEL --> JOIN
  JOIN --> Client
~~~

Số lời gọi con có thể lớn hơn số service: một BFF gọi Inventory cho 20 SKU riêng lẻ đã tạo ít nhất 20 outbound calls tới cùng một service.

Cần phân biệt:

- **Sequential fan-out:** gọi service B sau khi service A hoàn thành.
- **Parallel fan-out:** bắt đầu nhiều lời gọi và đợi kết quả.
- **Nested fan-out:** một dependency lại gọi nhiều dependency khác.
- **Conditional fan-out:** chỉ gọi những service thực sự cần cho request.
- **Optional fan-out:** có thể trả response trước khi phần dữ liệu không thiết yếu sẵn sàng.

Một request có fan-out nhiều tầng có thể tạo hàng chục hoặc hàng trăm thao tác nội bộ, kể cả khi người dùng chỉ nhìn thấy một HTTP request.

## 4. Critical path: vì sao song song không có nghĩa luôn nhanh?

Với ba lời gọi nối tiếp:

~~~text
Catalog 40 ms -> Pricing 70 ms -> Inventory 80 ms
Tổng phần chờ gần đúng: 190 ms
~~~

Nếu ba lời gọi thực sự chạy song song và **tất cả đều bắt buộc**, phần chờ gần đúng:

~~~text
max(40, 70, 80) = 80 ms
~~~

Cộng thêm overhead BFF, network, serialization và scheduler.

Trong đồ thị phức tạp:

~~~text
Catalog 40 ms -> Pricing 70 ms -> Inventory 80 ms
               \-> Reviews 120 ms
               \-> Recommendations 60 ms
~~~

Nếu Pricing cần Catalog trước, còn Reviews và Recommendations bắt đầu cùng lúc sau Catalog, critical path có thể là 40 + 70 + 80 = 190 ms. Cần vẽ dependency thật để xác định đường chậm nhất.

**Không cộng p99 của mọi dependency như thể tất cả nối tiếp. Cũng không lấy max các số p99 riêng lẻ rồi tuyên bố đó là p99 của cha.** Percentile của tổng hoặc maximum phụ thuộc phân phối, tương quan, thứ tự và overlap của các lời gọi.

## 5. Toán học: xác suất gặp ít nhất một lời gọi chậm

Giả sử mỗi lời gọi có xác suất **p** chậm hơn một ngưỡng thời gian. Một request cha phải đợi **n** lời gọi con.

Nếu giả sử các sự kiện chậm **độc lập** và có cùng xác suất:

\[
P(\text{không lời gọi nào chậm})=(1-p)^n
\]

Do đó:

\[
P(\text{ít nhất một lời gọi chậm})=1-(1-p)^n
\]

Ví dụ mỗi dependency chậm hơn 200 ms ở **1%** lời gọi. Một request có 20 lời gọi bắt buộc:

\[
1-(0.99)^{20} \approx 0.1821
\]

Tức là khoảng **18,2%** request cha có ít nhất một nhánh chậm, dù từng nhánh riêng chỉ có 1% trường hợp chậm.

| Số lời gọi bắt buộc n | Xác suất chậm một lời gọi | Xác suất có ít nhất một lời gọi chậm |
| ---: | ---: | ---: |
| 1 | 1% | 1,0% |
| 5 | 1% | 4,9% |
| 10 | 1% | 9,6% |
| 20 | 1% | 18,2% |
| 50 | 1% | 39,5% |
| 20 | 5% | 64,2% |

Các giá trị chỉ là mô hình **giả định độc lập**, không phải con số bảo đảm cho production.

### 5.1. Hàm phân phối của maximum

Với n lời gọi đồng thời, độc lập, cùng phân phối có hàm tích lũy F(t):

\[
T_{\mathrm{fanout}}=\max(T_1,T_2,\ldots,T_n)
\]

\[
P(T_{\mathrm{fanout}}\leq t)=F(t)^n
\]

Muốn 99% phần fan-out của cha hoàn thành trước t với n=20, mỗi lời gọi phải thỏa:

\[
F(t)\geq (0.99)^{1/20}\approx 0.9994976
\]

Tức là t gần với **p99.95 của một lời gọi** nếu các giả định ở trên đúng.

Đây là lý do thiết kế **20 dependency cùng p99 = 200 ms** không có nghĩa endpoint tổng hợp sẽ đạt p99 = 200 ms.

### 5.2. Sự chậm có thể tương quan

Các lời gọi cùng dùng network, DNS, database, Redis, cluster hoặc API Gateway thường không độc lập. Một incident có thể làm tất cả nhánh cùng chậm. Vì vậy:

- Đừng dùng công thức trên như dự báo chính xác khi có shared bottleneck.
- Dùng distributed traces để thấy tương quan.
- Đo latency theo region, zone, node, dependency và cache-hit/miss cohort.
- Kiểm thử cả một straggler độc lập lẫn lỗi dùng chung.

**Tail latency trong thực tế phải được đo bằng dữ liệu thật; công thức là công cụ để hiểu hướng rủi ro.**

## 6. Ví dụ phân phối hai điểm: p95 của cha bị kéo dài

Giả sử mỗi lời gọi độc lập:

- 99% lời gọi mất 50 ms.
- 1% lời gọi mất 500 ms.
- BFF gọi 20 child song song và đợi tất cả.
- Bỏ qua overhead.

Khoảng 81,8% request không gặp child chậm và hoàn thành phần fan-out ở 50 ms. Khoảng 18,2% có ít nhất một child 500 ms và phải đợi 500 ms.

Trong mô hình này:

~~~text
Child p50  = 50 ms
Child p95  = 50 ms
Child p99  = 50 hoặc 500 ms tùy quy ước vị trí phân vị tại điểm nhảy
Child p99.9 = 500 ms

Fan-out parent p50 = 50 ms
Fan-out parent p95 = 500 ms
Fan-out parent p99 = 500 ms
~~~

Điểm minh họa là **phần đuôi của cha xấu hơn đáng kể** khi đợi maximum của nhiều lời gọi. Với phân phối thực liên tục, cần xác định chính xác định nghĩa percentile thay vì dùng trường hợp biên rời rạc để tranh luận một giá trị p99 của child.

Nếu chỉ ba dependency cần thiết phải hoàn thành, xác suất có ít nhất một nhánh chậm còn:

\[
1-(0.99)^3 \approx 2.97\%
\]

Chuyển 17 nhánh không thiết yếu ra khỏi điều kiện **wait-all** có thể cải thiện đáng kể phần tail, miễn fallback không làm sai ý nghĩa nghiệp vụ.

## 7. Mô hình fan-out làm tăng tải xuống hệ thống

Giả sử Product BFF nhận 1.000 request/giây, mỗi request tạo 20 outbound calls:

~~~text
1.000 requests/s * 20 calls/request
= 20.000 downstream calls/s
~~~

Nếu một số lời gọi retry, tổng số **attempt** còn cao hơn 20.000. Nếu các service con cũng fan-out, một request ở edge có thể kích hoạt nhiều tầng công việc.

### 7.1. Amplification factor

Có thể đo:

- **Child calls per parent request.**
- **Retry attempts per logical operation.**
- **Hedged attempts per logical operation.**
- **Cache miss fetch count.**
- **Database queries per external request.**
- **CPU milliseconds hoặc network bytes per request.**

Một request 300 ms nhưng sinh 100 calls có thể không bền vững khi traffic tăng gấp 10 lần.

### 7.2. Retry storm

Khi Inventory chậm, BFF retry. Nếu Gateway cũng retry BFF, và client lại retry Gateway, số attempt có thể nhân theo từng tầng. Khi bottleneck là queue saturation, retry thêm làm tải tăng và latency còn xấu hơn.

Đặt **một retry policy có owner**, bounded attempts, backoff+jitter và **retry budget**. Không tự động retry mọi tầng.

## 8. Queueing: nguyên nhân phổ biến của tail latency

Nhiều request chậm vì **chờ tài nguyên**, không phải vì logic xử lý tăng chi phí:

- Connection pool hết connection.
- Thread pool hết worker.
- Semaphore/bulkhead hết permit.
- Database bị lock.
- CPU throttling hoặc GC pause.
- Disk IOPS hoặc network throughput saturation.
- Worker xử lý request nặng trước request nhẹ.

Theo mô hình hàng đợi M/M/1 lý tưởng:

\[
E[W]=\frac{1}{\mu-\lambda}
\]

Trong đó λ là tốc độ request đến, μ là tốc độ phục vụ, với λ nhỏ hơn μ.

Nếu μ = 100 req/s:

| λ | Utilization λ/μ | E[W] theo M/M/1 |
| ---: | ---: | ---: |
| 50 req/s | 50% | 20 ms |
| 80 req/s | 80% | 50 ms |
| 90 req/s | 90% | 100 ms |
| 95 req/s | 95% | 200 ms |
| 99 req/s | 99% | 1.000 ms |

M/M/1 không phản ánh đầy đủ production có nhiều worker và arrival burst, nhưng cho thấy **khi hệ thống gần bão hòa, thời gian chờ tăng rất nhanh**.

### 8.1. Liên hệ với Little’s Law

Trong trạng thái ổn định:

\[
L=\lambda W
\]

Trong đó L là số request trong hệ thống trung bình, λ là throughput và W là thời gian trong hệ thống trung bình.

Nếu hệ thống duy trì 1.000 req/s và W tăng từ 0,1 s lên 0,8 s, số request in-flight trung bình có thể tăng từ khoảng 100 lên 800. Các request giữ connection, memory hoặc thread lâu hơn, tạo vòng lặp xấu.

Little’s Law áp dụng cho **giá trị trung bình**, không trực tiếp cho p99. Dùng nó để lý giải tại sao tail latency và concurrency limit có quan hệ chặt chẽ.

## 9. Phân biệt dependency bắt buộc và tùy chọn

Một cách giảm fan-out tail hiệu quả là không đợi những dữ liệu không cần thiết để hoàn thành tác vụ cốt lõi.

| Dependency | Bắt buộc cho trang sản phẩm? | Hành vi khi chậm |
| --- | --- | --- |
| Catalog | Có | Trả lỗi hoặc bản cache còn hợp lệ theo chính sách |
| Pricing | Có khi hiển thị/đặt giá | Không tự trả giá 0 hoặc giá stale không được phép |
| Inventory | Có nếu cam kết còn hàng/checkout | Hiển thị UNKNOWN hoặc chặn hành động mua tùy contract |
| Reviews | Thường không | Bỏ phần đánh giá hoặc đánh dấu unavailable |
| Recommendations | Thường không | Hiển thị ít gợi ý hoặc dữ liệu cache hợp lệ |
| Promotions | Phụ thuộc nghiệp vụ | Không âm thầm bỏ logic giảm giá bắt buộc |
| Delivery ETA | Tùy bước mua | Phân biệt dự kiến và cam kết giao hàng |

**Optional không có nghĩa được trả dữ liệu giả.** Nếu Reviews timeout, trả trạng thái unavailable thay vì biểu diễn như thể sản phẩm chưa có review.

### 9.1. Ví dụ partial response

~~~json
{
  "productId": "BOOK-101",
  "name": "Sách Java",
  "price": {
    "amountMinor": 150000,
    "currency": "VND"
  },
  "inventory": {
    "status": "IN_STOCK",
    "available": 8
  },
  "reviews": {
    "status": "UNAVAILABLE",
    "items": []
  },
  "recommendations": {
    "status": "READY",
    "items": [
      { "productId": "BOOK-102" }
    ]
  }
}
~~~

Đây là contract minh họa. Client phải hiểu sự khác biệt giữa:

- **READY nhưng items rỗng:** không có dữ liệu phù hợp.
- **UNAVAILABLE:** dữ liệu không thể lấy trong ngân sách.
- **STALE:** dữ liệu cache có tuổi nhất định.
- **ERROR:** lỗi vượt khả năng fallback.

Không để latency tối ưu bằng cách hy sinh tính đúng đắn của giá, quyền truy cập, thanh toán hoặc tồn kho cam kết.

## 10. Deadline tổng và timeout từng lời gọi

**Timeout** giới hạn thời gian đợi một thao tác.  
**Deadline** giới hạn thời gian của **toàn bộ request/workflow**.

Ví dụ BFF có deadline 400 ms:

~~~text
Client budget          400 ms
Gateway/routing         45 ms
Remaining at BFF       355 ms
BFF aggregation         25 ms
Network/response        30 ms
Budget cho child calls 300 ms
~~~

Nếu Inventory được cấu hình timeout 800 ms, nó có thể làm việc lâu hơn thời điểm client còn chờ. Điều đó làm tăng lượng work vô ích trong lúc quá tải.

Các quy tắc:

1. Tổng deadline xác định ở ingress theo SLO.
2. Truyền ngân sách còn lại qua các tầng hoặc dùng deadline propagation được framework hỗ trợ.
3. Child timeout không được lớn hơn thời gian còn lại của parent.
4. Tách connect timeout, response timeout và queue acquisition timeout.
5. Retry dùng chung budget, không reset deadline cho mỗi attempt.
6. Optional call cần cutoff trước required path.
7. Parent timeout nên hủy/cancel operation ở nơi client/transport hỗ trợ.
8. Không giả định cancellation chắc chắn dừng công việc ở server từ xa.

### 10.1. Parallel không có nghĩa chia ngân sách đều

Nếu ba child song song đều phải hoàn thành trong 300 ms, không cần máy móc cho mỗi child 100 ms. Vì thời gian của chúng overlap, có thể đặt giới hạn hợp lý theo SLO từng dependency nhưng vẫn nằm trong deadline chung.

Ngược lại, nếu có chuỗi **Catalog → Pricing → Inventory**, cần giữ ngân sách cho từng bước tiếp theo. Nếu Catalog chiếm hết 300 ms, bước sau khó có cơ hội thành công.

## 11. Absolute deadline, monotonic clock và clock skew

Trong process Java, đo **thời gian đã trôi** bằng clock đơn điệu như **System.nanoTime()**. Không dùng đồng hồ hệ thống có thể bị điều chỉnh để đo khoảng chờ ngắn.

Ví dụ lớp quản lý deadline:

~~~java
import java.time.Duration;

public final class RequestBudget {
    private final long endNanos;

    private RequestBudget(long endNanos) {
        this.endNanos = endNanos;
    }

    public static RequestBudget start(Duration budget) {
        if (budget.isZero() || budget.isNegative()) {
            throw new IllegalArgumentException("budget must be positive");
        }
        return new RequestBudget(System.nanoTime() + budget.toNanos());
    }

    public Duration remaining() {
        long nanos = Math.max(0L, endNanos - System.nanoTime());
        return Duration.ofNanos(nanos);
    }

    public boolean expired() {
        return endNanos - System.nanoTime() <= 0L;
    }
}
~~~

Đoạn code minh họa cho deadline ngắn trong **cùng một process**. Sản phẩm thật cần giới hạn giá trị đầu vào và xét overflow nếu cho duration cực lớn.

**Không truyền trực tiếp System.nanoTime() giữa microservices**, vì đồng hồ monotonic mỗi process không có chung mốc gốc. Giao thức RPC có thể truyền thời lượng còn lại hoặc mốc deadline đã được thiết kế có xử lý clock skew.

Nếu client gửi deadline tùy ý, server vẫn phải **cap theo giới hạn nội bộ**; không để client quyết định giữ worker vô hạn.

## 12. Cancellation và work tiếp tục sau timeout

Một HTTP client timeout không chứng minh server bên kia đã dừng công việc:

- Request có thể đã được nhận và đang truy vấn database.
- Cancellation signal có thể không lan qua framework.
- Một task đã vào queue vẫn có thể chạy sau khi caller bỏ đi.
- Remote operation có side effect có thể đã commit.
- Retry mới có thể đến trước khi attempt cũ kết thúc.

Để hạn chế công việc vô ích:

- Dùng timeout đúng tại HTTP/DB client.
- Truyền cancellation tới task và query nơi hỗ trợ.
- Kiểm tra request context trước thao tác đắt tiền hoặc side effect.
- Giới hạn in-flight và queue.
- Đo số task tiếp tục sau parent cancellation.
- Với side effect, dùng idempotency và trạng thái nghiệp vụ để xử lý kết quả không chắc chắn.

Đặc biệt với payment: **timeout không đồng nghĩa chưa thanh toán**. Truy vấn transaction status trước khi retry.

## 13. Ví dụ Spring WebFlux: song song với fallback có kiểm soát

Một Product Page BFF có thể gọi nhiều dependency qua reactive WebClient:

~~~java
import java.time.Duration;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ProductPageService {

    private final CatalogClient catalog;
    private final PricingClient pricing;
    private final InventoryClient inventory;
    private final ReviewsClient reviews;

    public ProductPageService(
            CatalogClient catalog,
            PricingClient pricing,
            InventoryClient inventory,
            ReviewsClient reviews
    ) {
        this.catalog = catalog;
        this.pricing = pricing;
        this.inventory = inventory;
        this.reviews = reviews;
    }

    public Mono<ProductPage> load(String productId) {
        Mono<ProductInfo> info = catalog.fetch(productId)
            .timeout(Duration.ofMillis(180));

        Mono<PriceQuote> price = pricing.quote(productId)
            .timeout(Duration.ofMillis(200));

        Mono<StockStatus> stock = inventory.status(productId)
            .timeout(Duration.ofMillis(200));

        Mono<ReviewSummary> review = reviews.summary(productId)
            .timeout(Duration.ofMillis(100))
            .onErrorReturn(ReviewSummary.unavailable());

        return Mono.zip(info, price, stock, review)
            .map(tuple -> new ProductPage(
                tuple.getT1(),
                tuple.getT2(),
                tuple.getT3(),
                tuple.getT4()
            ))
            .timeout(Duration.ofMillis(350));
    }
}
~~~

Những kiểu **CatalogClient, PricingClient, InventoryClient, ReviewsClient, ProductInfo, PriceQuote, StockStatus, ReviewSummary, ProductPage** là abstractions minh họa của ứng dụng, không phải lớp tích hợp sẵn.

Trong ví dụ:

- Catalog, Pricing và Inventory được coi là **required**.
- Reviews là optional; khi lỗi hoặc timeout có thể trả trạng thái unavailable.
- Mono.zip chờ các Mono thành phần hoàn thành và kết hợp kết quả.
- Overall timeout giúp giới hạn thời gian chờ tổng.
- Các lời gọi có thể chạy đồng thời nếu adapter client thật sự bất đồng bộ.

Điều cần bổ sung cho production:

1. Propagate parent deadline; không reset 350 ms sau khi request đã mất thời gian ở Gateway.
2. Đặt connect/read/response timeout trong HTTP client, body size và connection pool.
3. Bounded concurrency và rate limit; reactive không làm dependency có capacity vô hạn.
4. Error mapping cho required dependency; không trả 200 với giá giả.
5. Instrument tracing và metrics theo child span.
6. Thử cancellation: hủy subscription không đảm bảo backend ngừng xử lý.
7. Không đặt tác vụ blocking JDBC hoặc synchronous network I/O trên event-loop.
8. Cân nhắc fallback rất cụ thể; onErrorReturn sẽ che mọi loại lỗi của Reviews trong ví dụ, còn production có thể cần phân biệt timeout/permission/contract error.

Các timeout cố định chỉ để dễ học, không phải SLO khuyến nghị mặc định.

## 14. Blocking I/O, thread pool và bounded queue

Với mô hình blocking I/O, phát sinh fan-out bằng quá nhiều thread hoặc unbounded executor có thể tạo tài nguyên không kiểm soát.

Một ví dụ executor có giới hạn:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public final class InventoryExecution {
    public static ThreadPoolExecutor boundedPool() {
        return new ThreadPoolExecutor(
            12, 12,
            0L, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(100),
            new ThreadPoolExecutor.AbortPolicy()
        );
    }
}
~~~

Con số **12 worker và queue 100** là minh họa, phải chọn bằng load test và capacity của Inventory.

Khi queue đầy, **RejectedExecutionException** cần được chuyển thành phản hồi overload/fallback phù hợp. Executor là tài nguyên dùng chung và có lifecycle, **không tạo trong mỗi HTTP request**.

Nếu Pricing, Reviews và Inventory cùng dùng một pool, Reviews chậm có thể chiếm hết worker và ngăn Pricing chạy. Nên cân nhắc **bulkhead theo dependency hoặc mức ưu tiên**, kết hợp connection pool riêng khi cần.

### 14.1. Virtual threads không loại bỏ tải xuống

Java 21 hỗ trợ virtual threads, giúp giảm chi phí nhiều tác vụ blocking chờ I/O trong các điều kiện phù hợp. Nhưng:

- DB connection pool vẫn hữu hạn.
- Downstream chỉ xử lý được một lượng QPS nhất định.
- Socket, memory và rate limit vẫn có giới hạn.
- Một request tạo 100 child calls vẫn nhân tải.
- Cần semaphore, rate limiter, queue cap hoặc bulkhead dù thread rẻ.

Virtual threads hỗ trợ **mô hình lập trình**, không giải quyết tự động fan-out amplification.

## 15. Bulkhead: chặn dependency chậm lan sang dependency khác

**Bulkhead** chia hạn mức tài nguyên để một phần suy giảm không chiếm hết năng lực chung.

Ví dụ giả định:

~~~text
Inventory:        max 30 in-flight calls
Pricing:          max 40 in-flight calls
Reviews:          max 10 in-flight calls
Recommendations:  max  8 in-flight calls
~~~

Cần xác định:

- Max concurrent calls theo mỗi instance.
- Max wait/queue length.
- Rejection semantics (fast fail, fallback, 503, hoặc 429 theo contract).
- Metrics permits in use, queue wait, rejection, latency.
- Số replica caller; 30 permits mỗi replica trên 10 replica có thể thành 300 calls tới backend.

Một semaphore minh họa:

~~~java
import java.time.Duration;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class BoundedInventoryClient {
    private final Semaphore permits = new Semaphore(30);
    private final InventoryClient delegate;

    public BoundedInventoryClient(InventoryClient delegate) {
        this.delegate = delegate;
    }

    public StockStatus fetch(String sku, Duration waitBudget)
            throws InterruptedException {
        long nanos = Math.max(0L, waitBudget.toNanos());

        if (!permits.tryAcquire(nanos, TimeUnit.NANOSECONDS)) {
            throw new InventoryOverloadedException();
        }

        try {
            return delegate.fetchStock(sku);
        } finally {
            permits.release();
        }
    }
}
~~~

InventoryClient, StockStatus và InventoryOverloadedException là kiểu miền minh họa. Phải cấu hình timeout trên delegate.fetchStock, vì nếu một call bị treo vô hạn thì permit vẫn bị giữ.

Với async APIs, release permit khi operation kết thúc hoặc cancellation được xử lý đúng, **không release ngay sau khi khởi tạo future**.

## 16. Admission control và load shedding

Một service gần bão hòa thường nên **từ chối một phần công việc** hơn là nhận tất cả rồi làm mọi request timeout.

Những lựa chọn:

- Limit concurrency khi in-flight vượt ngưỡng.
- Queue nhỏ và có giới hạn.
- Rate limit theo client/tenant.
- Giảm các nhánh optional như Recommendations.
- Tạm ngừng job báo cáo nặng trong lúc checkout quá tải.
- Ưu tiên tài nguyên cho hành động nghiệp vụ thiết yếu.
- Trả HTTP 429 hoặc 503 theo ý nghĩa lỗi và contract API.

Không dùng “shed load” để bỏ kiểm tra bảo mật hoặc bỏ qua logic giao dịch bắt buộc. Nếu quá tải ở Pricing, trả lỗi rõ còn tốt hơn trả giá 0 để đủ 200.

## 17. Retry: giúp lỗi tạm thời nhưng có thể làm tail tệ hơn

Retry có lợi với transient failure như một connection reset ngắn. Nhưng nếu dependency chậm vì queue saturation, retry tạo thêm tải và kéo dài queue.

Chính sách retry:

1. Chỉ retry operation an toàn theo semantics.
2. Giới hạn số attempt.
3. Exponential backoff có jitter.
4. Có **retry budget** theo tỷ lệ traffic.
5. Không retry ở tất cả các tầng của cùng logical operation.
6. Không retry nếu parent deadline không còn đủ.
7. Với thao tác side effect, phải có idempotency key và trạng thái xác định.
8. Quan sát tỷ lệ retry, retry success và retry-amplified QPS.

Ví dụ còn 180 ms trong request:

- Attempt đầu đã chờ 130 ms rồi timeout.
- Còn 50 ms, chưa tính backoff và serialize response.
- Nếu downstream thường mất 90 ms, retry tiếp ít có ích và làm tăng tải.

**Một retry sau timeout không được coi là “miễn phí”.** Nó ăn vào budget còn lại của caller.

## 18. Hedged request: thêm một attempt dự phòng có kiểm soát

**Hedging** là gửi attempt dự phòng nếu attempt đầu có dấu hiệu straggler, sau đó chọn kết quả hợp lệ hoàn thành sớm.

~~~text
t=0   Gửi read tới replica A
t=90  A chưa trả; gửi read dự phòng tới replica B
t=110 B trả thành công; chốt kết quả
t=120 A có thể vẫn xử lý dù caller cố cancel
~~~

Hedging có thể giúp khi latency của các replica có thành phần độc lập. Nhưng chỉ nên áp dụng khi:

- Operation read-only/idempotent hoặc có cơ chế dedup chắc chắn.
- Có giới hạn số hedge và tỷ lệ request được hedge.
- Replica dự phòng thuộc failure domain phù hợp; tránh cùng backend bottleneck.
- Dữ liệu trả về đáp ứng consistency contract.
- Có deadline và tài nguyên đủ.
- Có metrics đo hiệu quả p99 **và extra load**.
- Có cách tắt hedging nhanh khi backend bão hòa.

Không hedge payment charge hoặc thao tác ghi state nếu chưa thiết kế idempotency chặt chẽ. Hedging có thể gây **thêm tải chính vào nơi đang bị quá tải**.

## 19. Circuit breaker: fail-fast khi dependency suy giảm

Circuit breaker thường có trạng thái:

- **CLOSED:** cho phép lời gọi và thu thập số liệu lỗi/chậm.
- **OPEN:** từ chối nhanh các lời gọi mới.
- **HALF_OPEN:** thử số lượng call giới hạn để kiểm tra phục hồi.

Với Reviews tùy chọn, breaker OPEN cho phép trả nhanh **UNAVAILABLE** thay vì giữ request cha. Với Pricing bắt buộc, breaker OPEN nên trả lỗi có cấu trúc — không phải giá giả.

Circuit breaker không thay thế:

- Deadline và timeout.
- Bulkhead/concurrency limit.
- Rate limiting.
- Cache strategy.
- Theo dõi overload ở DB/network.
- Business fallback semantics.

Chú ý ngưỡng slow-call và failure-call cần đủ mẫu và cửa sổ thống kê hợp lý; nếu chỉ có 2 request mà 1 request lỗi, không nên suy ra service phải bị chặn toàn vùng ngay.

## 20. Cache để giảm fan-out trên đường nóng

Có nhiều tầng cache:

| Tầng | Dữ liệu phù hợp | Cần chú ý |
| --- | --- | --- |
| Browser/CDN | Static assets, ảnh | TTL, invalidation |
| BFF/edge | Product summary public | Cache key, cá nhân hóa |
| Local cache | SKU metadata, policy snapshot | Dữ liệu khác nhau giữa replica |
| Distributed cache | Danh mục, recommendation | Cache itself có thể quá tải |
| Read model/materialized view | Trang tổng hợp đã chuẩn bị | Eventual consistency, projection lag |
| Database buffer/query cache | Read hot data | Lock, IOPS, invalidation |

Cache giúp giảm số outbound calls và latency cho **cache hits**. Tuy nhiên nếu cache hit 95%, 5% miss còn lại có thể quyết định p99; phải đo **cache miss penalty** và sự khác biệt giữa cohort.

### 20.1. Request coalescing và cache stampede

Khi một sản phẩm hot hết TTL, hàng trăm request đồng thời có thể đều cache miss và gọi cùng dependency. Đây là **thundering herd/cache stampede**.

**Request coalescing/single-flight** cho nhiều request cùng key dùng chung một fetch:

~~~text
Request A --\
Request B ---> Shared fetch BOOK-101 ---> Cache ---> A/B/C
Request C --/
~~~

Cần:

- Key đủ ngữ cảnh: tenant, currency, locale, customer segment, permission, version.
- Không gộp dữ liệu người dùng khác nếu kết quả cá nhân hóa.
- Giới hạn số waiter và thời gian chờ.
- Xử lý shared fetch thất bại không để map in-flight giữ key mãi.
- Metric coalesced count và wait duration.

Cache key chỉ là productId khi giá khác theo tenant có thể gây rò rỉ dữ liệu hoặc tính sai tiền.

### 20.2. Stale-while-revalidate

Có thể trả dữ liệu cũ đã được phép trong khi refresh ở nền với những trường như mô tả hoặc gợi ý. **Không mặc định dùng giá tồn từ cache cũ để charge tiền**, vì giá giao dịch có freshness và chính sách nghiệp vụ riêng.

Giá trị stale cần có tuổi tối đa, nguồn, version và điều kiện chấp nhận rõ.

## 21. Materialized view: chuyển fan-out khỏi request path

Một kiến trúc khác là tạo **ProductPageReadModel** từ các sự kiện Catalog, Reviews và Recommendations. Khi client gọi BFF, BFF đọc projection thay vì fan-out đến mọi service.

~~~mermaid
flowchart LR
  CAT[Catalog events] --> BROKER[Event broker]
  REV[Review events] --> BROKER
  REC[Recommendation events] --> BROKER
  BROKER --> PROJ[Projection builder]
  PROJ --> STORE[(Product page read model)]
  CLIENT[Client] --> BFF[BFF]
  BFF --> STORE
  BFF --> LIVE[Authoritative price/stock if required]
~~~

Lợi ích:

- Giảm số lời gọi trên critical path.
- Giảm tail amplification và tải runtime.
- Dễ cache/read tối ưu cho UX.
- Có thể phục vụ nhanh ngay khi downstream tạm chậm.

Đánh đổi:

- Eventual consistency.
- Projection lag và nhu cầu replay/backfill.
- Outbox/inbox, idempotency, event ordering.
- Quản lý schema/version và ownership.
- Phân quyền dữ liệu và cache invalidation.

Không biến projection thành nguồn authoritative cho mọi trường nếu nghiệp vụ cần xác nhận mới nhất tại checkout.

## 22. Batching: giảm N+1 calls

Nếu trang hiển thị 30 SKU và BFF gọi 30 request đơn tới Inventory, có thể cân nhắc batch endpoint:

~~~http
POST /api/inventory/batch-lookup HTTP/1.1
Content-Type: application/json

{
  "skus": ["SKU-1", "SKU-2", "SKU-3"]
}
~~~

Một batch có thể giảm connection overhead và pressure do fan-out. Nhưng:

- Giới hạn batch size/body size.
- Có thể cần partial error per item.
- Một item chậm không nên làm toàn batch treo không cần thiết.
- Query với danh sách rất lớn có thể tạo DB plan xấu.
- Không để một tenant dùng batch vô hạn.
- Nếu cần ưu tiên, tách batch theo loại công việc.

Mục tiêu không chỉ giảm số HTTP requests mà là giảm **total resource cost** và cải thiện p99 thực tế.

## 23. Lazy loading và conditional fan-out

Không phải mọi dữ liệu của trang phải xuất hiện ở response đầu tiên:

- Reviews nằm dưới phần cuộn có thể tải khi người dùng mở.
- Recommendations có thể tải sau khi nội dung chính hiển thị.
- Shipping ETA chỉ được gọi khi có địa chỉ phù hợp.
- Product metadata có thể đưa vào read model.
- Các trường giống nhau được request bởi nhiều component có thể gộp và cache.

Một số ứng dụng dùng **GraphQL/DataLoader** để batch các field lookup hoặc tránh N+1 queries. Tuy nhiên GraphQL không tự động giải quyết N+1: resolver có thể vẫn gọi nhiều downstream service nếu không có batching/coalescing đúng.

Cân bằng:

- Request quan trọng trả nhanh.
- Contract client vẫn rõ và nhất quán.
- Không làm UI tạo hàng chục request riêng mà không kiểm soát.
- Có cancellation khi người dùng rời trang.
- Dữ liệu có freshness policy.

## 24. Distributed tracing để tìm đường gây chậm

Một trace ví dụ:

~~~text
Product BFF                 0-360 ms
  Catalog GET              10-55 ms
  Pricing GET              11-110 ms
  Inventory GET            12-290 ms
  Reviews GET              13-210 ms
  Recommendations GET      13-125 ms
  Response aggregation    290-360 ms
~~~

Trace giúp trả lời:

- Các child thực sự parallel hay vô tình sequential?
- Nhánh nào trên critical path?
- Queue wait/connection acquisition nằm ở đâu?
- Có retry hoặc hedge nào tạo work dư?
- Có child request tiếp tục sau parent timeout?
- Có cùng key được fetch lặp do cache stampede?
- Một slow request có đi qua nhiều service dùng chung bottleneck?

**Không cộng toàn bộ child duration** rồi kết luận đó là wall-clock latency của parent: các khoảng có thể overlap.

Tracing phải được nối context giữa các service. Sampling có thể bỏ lỡ p99.9; nên giữ slow/error traces khi phù hợp và dùng histogram/metrics để có bức tranh tổng.

## 25. Instrumentation và metrics cần có

| Nhóm | Metric | Mục tiêu |
| --- | --- | --- |
| Endpoint | request duration histogram | p50/p95/p99 theo route |
| Dependency | outbound duration histogram | tìm dependency chậm |
| Fan-out | child calls per parent | đo amplification |
| Critical path | latest required completion | tìm straggler quyết định thời gian |
| Retry | attempts per operation | kiểm soát retry storm |
| Hedging | extra attempts, winner rate | đánh giá lợi ích và chi phí |
| Queue | wait, depth, rejected | phát hiện saturation |
| Connection pool | active/pending, acquire timeout | tách queue/network latency |
| Cache | hit, miss, stale served, stampede | giải thích tail của miss |
| Fallback | partial response rate | thấy chất lượng trải nghiệm |
| Cancellation | aborted work, late completions | đo công việc vô ích |
| Runtime | CPU, GC, memory, I/O | tìm bottleneck |
| Business | checkout errors, price mismatch | không hy sinh correctness |

### 25.1. Percentile không được lấy trung bình giữa replica

Nếu pod A có p99 100 ms với 100 request, pod B p99 200 ms với 1.000 request, pod C p99 500 ms với 10.000 request, không lấy trung bình ba số p99 để kết luận p99 cluster.

Nên tổng hợp phân phối bằng **histogram bucket tương thích, raw observations hoặc sketch hỗ trợ merge**. Xem kích thước mẫu và cùng cửa sổ thời gian.

### 25.2. p99.9 cần đủ mẫu

Với 1.000 request, về trung bình chỉ một request nằm trong 0,1% đuôi chậm. Vì vậy p99.9 ước lượng rất nhiễu nếu lưu lượng nhỏ.

Hãy kiểm tra:

- Tổng số request.
- Timeout/error đã được tính thế nào.
- Histogram bucket resolution.
- Region/tenant/version/cohort.
- Cache hit versus miss.
- Response size và traffic burst.
- Vùng thời gian đánh giá.

Không chỉ báo p99 cho request thành công và lờ đi số request timeout; điều đó làm dashboard “xanh” giả.

### 25.3. Tránh high-cardinality metric labels

Không đưa raw URL chứa orderId, userId, traceId, email hoặc một label cho mỗi request vào Prometheus metric. Dùng route template và dependency operation; traceId thuộc hệ tracing với kiểm soát dữ liệu nhạy cảm.

## 26. SLO và error budget cho endpoint tổng hợp

Một SLO minh họa:

> 99% request GET /product-page/{id} phải trả dữ liệu thiết yếu trong 400 ms, đo tại ingress server theo cửa sổ 28 ngày cho thị trường mục tiêu.

Cần định nghĩa:

- Tính cả lỗi 5xx/timeout hay chỉ latency thành công?
- Partial response thiếu Reviews có được xem là success?
- Thiếu Pricing hoặc Inventory có được xem là success?
- Dữ liệu stale được phép bao lâu?
- Phạm vi region/tenant/client?
- Cửa sổ và phương pháp histogram?

**Latency SLO không thay correctness SLO.** Trả 200 trong 100 ms với giá 0 do Pricing timeout là kết quả sai dù p99 trông đẹp.

Khi BFF có 20 nhánh required, mỗi nhánh “p99 < 400 ms” không đủ chứng minh BFF p99 < 400 ms. SLO dependency cần dựa trên call graph, xác suất tail và mức overlap.

Các đòn bẩy kiến trúc:

- Giảm số child required.
- Cache các dữ liệu có freshness phù hợp.
- Batch lookups.
- Dùng read model.
- Giảm queue wait và tăng headroom.
- Deadline/fail-fast khi không thể hoàn thành.
- Fallback chỉ khi domain cho phép.

## 27. Kiểm thử có kiểm soát: một nhánh chậm

Một bài load test nên bắt đầu bằng baseline:

1. Đo BFF p50/p95/p99, throughput và error rate.
2. Đo dependency histograms, queue wait và connection pool.
3. Đếm child attempts per external request.
4. Tách cache hit/miss.
5. Lưu traces của request chậm.

Sau đó inject lỗi trong môi trường cô lập:

- Inventory 1% request chậm thêm 700 ms.
- Reviews 5% request timeout.
- Catalog shared cache bị miss đồng thời.
- Database connection pool saturation.
- Network jitter trong một zone.
- Worker queue chạm giới hạn.
- Client cancel trước response.
- Retry/hedging được bật ở các mức khác nhau.

Kiểm tra:

- p99 BFF đổi ra sao.
- Tải downstream tăng bao nhiêu.
- Partial response có đúng contract?
- Required data có bị trả giả hoặc stale sai?
- Request mồ côi có tiếp tục chạy?
- Hệ thống phục hồi bao lâu sau burst?

Không chạy fault injection làm thanh toán, gửi email hoặc ghi dữ liệu thật bị lặp trên môi trường production thiếu kiểm soát.

## 28. Ví dụ tối ưu Product Page từ wait-all sang thiết kế có deadline

Baseline giả định:

~~~text
Traffic                     1.000 page requests/s
Fan-out                     20 child calls/request
BFF p50                     110 ms
BFF p95                     650 ms
BFF p99                   1.200 ms
Reviews p99                 700 ms
Inventory p99               400 ms
Downstream calls/s       20.000
~~~

### Bước 1 — Xác định critical path

Tracing cho thấy Reviews optional nhưng BFF đang đợi kết quả như required. Cần sửa contract để BFF có thể trả trang khi Reviews chưa sẵn sàng.

### Bước 2 — Giảm fan-out

Mười SKU inventory lookup được gộp thành một batch. Catalog metadata được cache đúng key. Recommendations dùng read model hoặc cache khi phù hợp. Giảm công việc trên đường nóng thay vì chỉ tăng timeout.

### Bước 3 — Áp deadline

BFF nhận 400 ms budget tại ingress và truyền remaining time cho các lời gọi. Reviews có cutoff 100 ms, toàn request không chờ quá deadline đã định nghĩa.

### Bước 4 — Cô lập tài nguyên

Inventory, Pricing và Reviews có bulkhead riêng; queue bounded. Nếu Reviews quá tải, trả unavailable cho phần optional, không chiếm hết thread/connection của Pricing.

### Bước 5 — Kiểm tra retries

Không retry vô điều kiện khi queue đã saturation. Retry attempts bounded, có jitter và nằm trong remaining deadline.

### Bước 6 — Đo lại và canary

Một kết quả giả định sau tối ưu:

~~~text
BFF p50                      95 ms
BFF p95                     240 ms
BFF p99                     380 ms
Downstream calls/s        8.000
Reviews unavailable rate      2%
Pricing correctness errors    0
~~~

Con số minh họa không phải benchmark thực tế. Cần kiểm tra các trường hợp peak traffic, cache miss, region failover, rollout phiên bản và business invariants trước khi chốt thiết kế.

## 29. Những sai lầm thường gặp

1. Chỉ theo dõi average latency, không đo p95/p99.
2. Đặt p99 SLO cho child rồi mặc định parent đạt cùng p99.
3. Cộng p99 mọi child như thể chúng tuần tự.
4. Đợi tất cả nhánh dù Reviews/Recommendations tùy chọn.
5. Đặt timeout child dài hơn remaining parent deadline.
6. Không propagate deadline qua các tầng.
7. Retry mọi timeout trong khi backend đã queue saturation.
8. Hedging mọi request, nhân đôi tải.
9. Dùng queue vô hạn để “không mất request”, khiến tail và memory tăng.
10. Dùng chung thread pool cho dependency quan trọng và không quan trọng.
11. Tưởng virtual threads làm backend có capacity vô hạn.
12. Gọi hàng chục API cho từng SKU mà không batching.
13. Không cache/coalescing hot keys và gặp cache stampede.
14. Cache key thiếu tenant, currency, user segment hoặc quyền truy cập.
15. Fallback giá 0 khi Pricing chậm.
16. Dùng dữ liệu tồn kho stale để cam kết giao hàng khi nghiệp vụ không cho phép.
17. Chỉ tối ưu service không nằm trên critical path.
18. Không đo queue wait và connection acquisition.
19. Bỏ qua correlated failures giữa các dependency.
20. Timeout ở caller nhưng server vẫn xử lý, tạo work amplification.
21. Không instrument retry/hedge/cancellation.
22. Lấy trung bình p99 giữa các pod.
23. Loại request timeout khỏi latency metric và cho rằng p99 tốt.
24. Test với chỉ một hot SKU đã cache nên không phản ánh production.
25. Không kiểm thử cache miss spike và overload.
26. Mở partial response nhưng không cho client biết phần nào unavailable.
27. Không phân biệt success về HTTP với correctness về nghiệp vụ.
28. Không đặt owner cho fallback, SLO và runbook.
29. Bật tính năng mới làm tăng fan-out mà không đo downstream capacity.
30. Không giới hạn số lời gọi con do input của client kiểm soát.

## 30. Checklist thiết kế endpoint fan-out

### Kiến trúc

- [ ] Đã vẽ call graph và critical path.
- [ ] Có giới hạn child calls per parent request.
- [ ] Phân loại required/optional theo nghiệp vụ.
- [ ] Có partial response contract và fallback semantics rõ.
- [ ] Có batching/caching/coalescing khi phù hợp.
- [ ] Dữ liệu tiền, tồn kho và quyền truy cập không bị fallback sai.

### Deadline, concurrency và bảo vệ overload

- [ ] Có overall request deadline.
- [ ] Child timeout không vượt remaining budget.
- [ ] Có connect/response/queue timeout.
- [ ] Executor, connection pool và queue đều bounded.
- [ ] Có bulkhead cho dependency dễ gây cascading failure.
- [ ] Retry bounded và không lặp nhiều tầng.
- [ ] Hedging chỉ ở operation phù hợp và có guardrails.
- [ ] Cancellation được propagate khi có thể.
- [ ] Có load shedding và fail-fast khi thật sự bão hòa.

### Quan sát và kiểm thử

- [ ] Có histogram p50/p95/p99/p99.9 ở nơi volume đủ.
- [ ] Có outbound latency và queue metrics theo dependency.
- [ ] Có distributed tracing cho slow/error requests.
- [ ] Có metric child attempts, retries, hedges và fallback.
- [ ] Đo riêng cache hit/miss.
- [ ] Không lấy trung bình percentile giữa replica.
- [ ] Đã test straggler, correlated failure, stampede và overload.
- [ ] Có business guardrails và không “làm đẹp” p99 bằng cách bỏ request lỗi.

## 31. Câu hỏi tự kiểm tra

**1. Vì sao mỗi dependency chỉ chậm 1% nhưng parent có 20 call có thể chậm 18%?**  
Nếu các call độc lập và tất cả required, xác suất ít nhất một call chậm là **1−0,99^20 ≈ 18,2%**.

**2. Ba lời gọi song song đều mất 100 ms thì parent phải đợi 300 ms không?**  
Không. Nếu thực sự song song và phải đợi cả ba, phần chờ khoảng 100 ms, cộng overhead.

**3. Tại sao không được lấy max(child p99) làm parent p99?**  
Vì maximum của nhiều biến ngẫu nhiên có phân phối khác phân phối từng child; tail amplification phụ thuộc n và correlation.

**4. Khi nào giả định độc lập không phù hợp?**  
Khi nhiều child dùng chung backend, network, node, zone hoặc cùng gặp overload.

**5. Parent chỉ còn 100 ms nhưng child timeout 1.000 ms có vấn đề gì?**  
Child có thể giữ tài nguyên lâu sau khi parent hết hạn, làm tăng work vô ích.

**6. Timeout một Payment call có nghĩa payment chưa charge?**  
Không. Cần idempotency và tra cứu trạng thái trước khi retry.

**7. Vì sao Reviews có thể fallback nhưng Pricing không nên trả 0?**  
Reviews thường optional; giá là thông tin giao dịch có yêu cầu correctness và freshness riêng.

**8. Virtual threads có loại bỏ cần thiết của bulkhead không?**  
Không. Downstream, connection pool và database vẫn có hạn mức.

**9. Cache hit 95% bảo đảm p99 tốt không?**  
Không. 5% miss có thể chậm và quyết định p99.

**10. Khi nào hedging nguy hiểm?**  
Khi tăng tải ở bottleneck chung, operation có side effect hoặc không có giới hạn.

**11. Vì sao aggregate p99 bằng trung bình các p99 là sai?**  
Percentile là thuộc tính của phân phối; cần gộp histogram/observations đúng cách.

**12. Đo gì để biết p99 do queue wait hay service logic?**  
Queue wait, connection acquisition, request duration, downstream spans, saturation và retry attempts.

**13. Thay fan-out runtime bằng read model có đánh đổi gì?**  
Giảm latency nhưng tạo eventual consistency, projection lag và trách nhiệm cập nhật/khôi phục dữ liệu.

**14. Có thể cải thiện p99 bằng cách bỏ request timeout khỏi metric không?**  
Không. Đó là sai lệch đo lường; cần ghi nhận timeout/error theo policy rõ.

**15. Endpoint trả 200 nhanh nhưng thiếu giá có đạt yêu cầu?**  
Không nếu giá là trường bắt buộc. Latency SLO không thay correctness SLO.

## 32. Tài liệu tham khảo

- Google Research — The Tail at Scale: https://research.google/pubs/the-tail-at-scale/
- Google SRE Book — Addressing Cascading Failures: https://sre.google/sre-book/addressing-cascading-failures/
- Google SRE Book — Handling Overload: https://sre.google/sre-book/handling-overload/
- Google SRE Book — Service Level Objectives: https://sre.google/sre-book/service-level-objectives/
- OpenTelemetry — Traces: https://opentelemetry.io/docs/concepts/signals/traces/
- OpenTelemetry — Metrics: https://opentelemetry.io/docs/concepts/signals/metrics/
- Prometheus — Histograms and Summaries: https://prometheus.io/docs/practices/histograms/
- Spring Framework — WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- Project Reactor — Reference Guide: https://projectreactor.io/docs/core/release/reference/
- Resilience4j — Documentation: https://resilience4j.readme.io/docs
- gRPC — Deadlines: https://grpc.io/docs/guides/deadlines/

**Ghi nhớ:** Fan-out giúp giảm độ trễ của các bước có thể chạy song song, nhưng làm tăng số cơ hội gặp straggler và nhân tải xuống dependency. Giảm tail latency bền vững đòi hỏi **giảm số nhánh bắt buộc, kiểm soát critical path, cache và batching, deadline xuyên tầng, giới hạn concurrency, retry/hedging có điều kiện, quan sát phân phối và giữ tính đúng đắn nghiệp vụ**.
