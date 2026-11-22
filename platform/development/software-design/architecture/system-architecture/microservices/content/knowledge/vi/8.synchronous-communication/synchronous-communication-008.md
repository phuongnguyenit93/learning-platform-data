# Tránh chuỗi gọi dài và gọi nối tiếp không cần thiết

> **Nguyên tắc:** Trong hệ thống microservices, mỗi lời gọi đồng bộ nằm trên đường trả lời người dùng đều tiêu tốn ngân sách độ trễ và có thể khiến lỗi ở dịch vụ phụ thuộc lan truyền. Hãy xác định **critical path**, giữ lại những quyết định thật sự cần hoàn thành trước phản hồi, song song hóa những bước độc lập khi an toàn, gộp các lời gọi lặp và đưa công việc không cần chờ ra khỏi đường phản hồi. Không đổi tính đúng đắn nghiệp vụ lấy một con số latency đẹp.

Bài học thuộc nhóm **Giao tiếp đồng bộ** của kiến trúc hệ thống và microservices. Trọng tâm không chỉ là giảm số request HTTP/gRPC, mà là giảm **phụ thuộc chờ nối tiếp**, **khuếch đại request (request amplification)** và **điểm nghẽn tải** trong khi vẫn giữ ranh giới nghiệp vụ, dữ liệu và quy tắc nhất quán.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt thời gian xử lý nội bộ của một service với thời gian phản hồi đầu cuối.
2. Nhận diện **chuỗi gọi tuần tự**, **fan-out**, **remote N+1**, **critical path** và lời gọi qua lại không cần thiết.
3. Đánh giá bước nào bắt buộc nối tiếp, bước nào có thể song song, bước nào được phép thực hiện sau.
4. Giải thích khi nào batching, API tổng hợp, cache, read model và event-driven processing giúp giảm phụ thuộc chờ.
5. Thiết kế timeout, deadline, retry, concurrency limit, idempotency và xử lý sự cố phù hợp.
6. Dùng distributed tracing và metric để xác định bottleneck thực tế, đo lại p95/p99, throughput và độ tin cậy.
7. Thiết kế ví dụ Java/Spring Boot cho lời gọi song song có giới hạn và loại bỏ vòng lặp RPC.

## 2. Chuỗi gọi đồng bộ dài là gì?

Một request ở giao diện có thể đi qua nhiều microservice:

~~~text
Browser
  |
  v
API Gateway
  |
  v
Order Service
  |
  +--> Customer Service
           |
           +--> Address Service
                    |
                    +--> Region Service
                             |
                             +--> Tax Service
                                      |
                                      +--> Policy Service
~~~

Nếu các service phải lần lượt đợi kết quả của service phía dưới trước khi trả kết quả lên phía trên, ta có **chuỗi gọi đồng bộ sâu**. Mỗi hop có thể thêm thời gian tạo/lấy kết nối, xác thực, truyền mạng, serialize/deserialize, xử lý nghiệp vụ, truy cập database, queue trong server và trả kết quả.

Một luồng có nhiều lời gọi không tự động là sai. Có những quyết định thực sự phải phụ thuộc kết quả trước, chẳng hạn xác định thuế sau khi biết địa chỉ giao hàng. Nhưng nếu các service chỉ làm nhiệm vụ chuyển tiếp thông tin, hoặc bước cuối không ảnh hưởng phản hồi người dùng, chuỗi sâu thường tạo ra chi phí có thể tránh được.

### 2.1. Những hệ quả phổ biến

- **Latency tích lũy:** phản hồi của dịch vụ ngoài cùng chờ nhiều downstream.
- **Tail latency:** một nhánh chậm kéo p95/p99 đầu cuối tăng mạnh.
- **Availability coupling:** một dependency chậm hoặc lỗi có thể làm request tổng thất bại.
- **Request amplification:** một request bên ngoài sinh nhiều request nội bộ.
- **Resource exhaustion:** thread, connection, pool hoặc database bị chiếm trong lúc chờ.
- **Khó điều tra lỗi:** log, trace và retry trải rộng trên nhiều service.
- **Ràng buộc thay đổi:** những API chỉ chuyển tiếp có thể bị buộc thay đổi theo nhau.

Đích thiết kế là **giảm thời gian phải chờ và mức phụ thuộc thực**, không phải cấm mọi RPC.

## 3. Critical path: đường xử lý quyết định phản hồi

**Critical path** là chuỗi công việc phụ thuộc có tổng thời gian lớn nhất trong đồ thị tác vụ bắt buộc để tạo phản hồi. Với một yêu cầu đơn giản:

~~~text
Validate request
      |
      +--> Query Pricing --------+
      |                          +--> Assemble response
      +--> Query Inventory ------+
~~~

Nếu Pricing và Inventory độc lập sau khi đã nhận SKU và quantity, có thể khởi chạy hai nhánh đồng thời rồi chờ cả hai hoàn thành. Ngược lại:

~~~text
Get shipping address
      |
      v
Choose delivery region
      |
      v
Compute shipping fee
~~~

Nếu fee phụ thuộc vùng giao hàng, gọi bước cuối trước khi biết region là sai dữ liệu. Muốn giảm chiều sâu phải thiết kế lại hợp đồng hoặc đặt các quyết định liên quan trong đúng bounded context, thay vì tạo thêm thread và hy vọng thứ tự không còn quan trọng.

### 3.1. Mô hình chi phí tuần tự

Với ba RPC thực hiện theo thứ tự A → B → C:

~~~text
T_sequential ~= T_A + T_B + T_C + T_overhead
~~~

Ví dụ minh họa với giả định cố định:

~~~text
Authentication         20 ms
Customer lookup        50 ms
Address lookup         65 ms
Tax calculation        90 ms
Response assembly      15 ms
----------------------------
Approximate total     240 ms
~~~

Các số là giả định học tập. Độ trễ thực có phân phối, mức tải và chi phí phụ thuộc lẫn nhau. Trong production, hãy đo thời gian đầu cuối từ request thật.

### 3.2. Mô hình chi phí song song

Nếu hai việc độc lập có thời gian 70 ms và 110 ms:

~~~text
Sequential:
  Work A (70) -> Work B (110)     ~= 180 ms

Parallel:
  Work A (70) ----------------+
                             +--> Join  ~= 110 ms + overhead
  Work B (110) ---------------+
~~~

Trong điều kiện lý tưởng, thời gian hoàn thành hai nhánh song song gần bằng **thời gian nhánh chậm nhất**, cộng chi phí điều phối và tổng hợp kết quả. Tổng CPU/network thực hiện vẫn còn; thậm chí tăng áp lực đồng thời lên downstream.

### 3.3. Không cộng các p95 rồi cho là p95 cuối

p95 là phân vị của một phân phối. Tổng p95 từng RPC không nhất thiết bằng p95 toàn request; tương tự max của các giá trị p99 từng nhánh không phải p99 tổng khi có nhiều nhánh. Trace end-to-end là bằng chứng đáng tin hơn phép cộng các percentile đơn lẻ.

**Cần phân biệt:** tổng thời lượng các span trong trace, thời gian người dùng chờ và mức tải tài nguyên không phải cùng một đại lượng.

## 4. Ba kiểu cấu trúc thường gây chậm

### 4.1. Chuỗi sâu nhiều tầng

~~~text
Client -> A -> B -> C -> D -> E -> Database
~~~

A phụ thuộc E qua nhiều lớp trung gian. Nếu B–D không sở hữu quyết định nghiệp vụ riêng mà chỉ chuyển tiếp request, nên xem lại ranh giới API và trách nhiệm service.

### 4.2. Remote N+1

Một endpoint trả về 100 đơn, rồi cho từng đơn gọi Customer API để lấy tên:

~~~text
GET /orders
  |-> read 100 orders
  |-> getCustomer(order 1)
  |-> getCustomer(order 2)
  |-> getCustomer(order 3)
  ...
  +-> getCustomer(order 100)
~~~

Đây là biến thể của **N+1 query** qua mạng. Với 100 đơn, có thể tạo 100 RPC tới Customer, và hơn thế nữa nếu mỗi đơn có nhiều dòng hàng cần gọi Catalog. Nếu tất cả thực hiện tuần tự, độ trễ tích lũy rất lớn; nếu song song vô giới hạn, tải lên Customer có thể tăng đột biến.

### 4.3. Fan-out lồng nhau

~~~text
Gateway (1 request)
  |
  v
Aggregator
  |----> A: 20 internal calls
  |----> B: 30 internal calls
  +----> C: 10 internal calls
                 |
                 +--> D: 20 more calls
~~~

Một request bên ngoài có thể tạo hàng chục hoặc hàng trăm request nội bộ. Một thiết kế song song làm latency người gọi giảm ở tải nhẹ nhưng tăng tổng workload, queueing và nguy cơ timeout ở tải lớn.

**Độ sâu** ảnh hưởng critical path; **độ rộng** ảnh hưởng fan-out, tài nguyên và xác suất gặp nhánh chậm. Hai yếu tố cần được đo riêng.

## 5. Phân loại lời gọi theo ý nghĩa nghiệp vụ

Trước khi tối ưu, hãy hỏi mỗi bước có thuộc **lời hứa của API** không.

| Loại bước | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Bắt buộc để trả lời đúng | Xác thực quyền; báo giá cuối cùng; kiểm tra điều kiện xác nhận giao dịch | Giữ trên critical path, rút ngắn và bảo vệ deadline |
| Cần trong response nhưng độc lập | Lấy profile và danh sách đơn để dựng dashboard | Có thể song song hoặc dùng API tổng hợp |
| Tùy chọn cho trải nghiệm | Recommendation, badge, ảnh phụ | Có thể fallback hoặc tải sau |
| Không ảnh hưởng kết quả ngay | Email xác nhận, analytics, indexing | Xử lý sau bằng event/queue khi phù hợp |
| Dữ liệu tổng hợp có thể trễ | Bảng báo cáo, search index, lịch sử hiển thị | Read model/projection hoặc cache |
| Thay đổi trạng thái xuyên context | ReserveStock, CapturePayment | Thiết kế transaction/state machine rõ rồi chọn sync/async |

Nếu một dịch vụ chỉ cần trả “đã tiếp nhận yêu cầu”, nó có thể trả trạng thái PENDING theo hợp đồng. Nếu response hứa “đã thanh toán”, thì Payment phải có bằng chứng trạng thái phù hợp trước lời hứa đó.

### 5.1. Phân biệt nhận yêu cầu và hoàn tất

~~~text
201 Created:
  orderId = O-1001
  status  = CONFIRMED
  meaning: những điều kiện xác nhận theo chính sách đã hoàn thành

202 Accepted:
  orderId = O-1001
  status  = PENDING
  meaning: hệ thống đã nhận, các bước còn tiếp tục xử lý
~~~

Trả 202 có thể giảm thời gian chờ browser, nhưng không làm **thời gian nghiệp vụ hoàn tất** tự giảm. Người dùng cần đường truy vấn trạng thái hoặc nhận thông báo khi có kết quả.

## 6. Quan sát bằng distributed tracing trước khi sửa

Đầu tiên, ghi nhận cấu trúc request thật thay vì đoán từ sơ đồ code. Một distributed trace nên thể hiện:

- Span của Gateway và từng service, cùng quan hệ parent-child.
- Endpoint/RPC name, start/end time, trạng thái, lỗi và retry.
- Thời gian local work so với thời gian chờ downstream.
- Các span chạy song song hay nằm tuần tự.
- Số lần gọi cùng downstream trong một request.
- Connection acquisition, DB query, queue wait và thread pool saturation khi có instrumentation.
- Trace/correlation ID được truyền xuyên ranh giới.
- Luồng nào nằm trên critical path và thường làm p95/p99 cao.

Một trace mô phỏng:

~~~text
GET /checkout-preview                     480 ms
 |-- Auth                                 25 ms
 |-- Read Cart                            30 ms
 |-- Pricing                             100 ms
 |-- Inventory                           120 ms
 |-- Recommendations                     260 ms
 +-- Serialize response                   20 ms
~~~

Không thể suy ra thời gian request bằng cách cộng các span nếu chúng chạy chồng lấn. Nếu Recommendations là tùy chọn và đang giữ response chờ 260 ms, đó là ứng viên tốt để tách khỏi đường chính hoặc có fallback.

### 6.1. Đo đường xử lý đến người dùng

Metrics baseline cần bao gồm p50/p95/p99, throughput, error rate, timeout rate, số RPC nội bộ/request, độ sâu chuỗi, mức độ fan-out, CPU, memory, DB query latency và connection pool utilization. Với một endpoint quan trọng, cần biết tỷ lệ request đi qua nhánh chậm thay vì chỉ xem một trace lẻ.

### 6.2. Gắn tối ưu với mục tiêu đo được

Ví dụ, “p95 của checkout-preview dưới 500 ms trong điều kiện traffic 300 request/giây” có thể kiểm chứng. “Làm microservices nhanh hơn” quá mơ hồ để chọn thay đổi.

## 7. Kỹ thuật 1: đưa việc không cần chờ ra khỏi critical path

Trước khi thay giao thức, hãy kiểm tra xem endpoint có đang chờ các tác vụ phụ hay không.

~~~text
Before:
POST /orders
  -> Create Order
  -> Send email
  -> Write analytics
  -> Update recommendations
  -> Return

After (when business contract allows):
POST /orders
  -> Commit Order + outbox record
  -> Return actual Order state

Outbox publisher -> Event broker
    |-> Notification worker
    |-> Analytics consumer
    +-> Recommendation consumer
~~~

Nếu email provider chậm 4 giây, request tạo đơn không cần chịu trễ đó nếu email không quyết định việc tạo đơn thành công. Tương tự, một lỗi gửi email sau khi Order đã commit không nên khiến API nói “không tạo được đơn”, từ đó gây retry trùng.

### 7.1. Lưu sự kiện bền vững

Đừng commit Order xong rồi phát event mà không xử lý tình huống phát lỗi. Transactional outbox ghi thay đổi Order và bản ghi “cần phát event” trong cùng transaction cục bộ. Publisher đọc outbox rồi phát tới broker, có thể retry; consumer cần idempotency để tránh xử lý trùng.

Outbox không làm database của Notification và database Ordering cùng commit atomically. Nó giúp tránh mất ý định phát event do lỗi giữa thao tác ghi trạng thái và publish.

### 7.2. Không dời quyết định bắt buộc ra sau

Ví dụ, phí vận chuyển hoặc báo giá cuối cùng là điều kiện khách đồng ý mua. Không được dùng giá “ước lượng” chưa được hợp đồng chấp nhận để trả trạng thái CONFIRMED, rồi xử lý giá thật sau. Tách việc nền chỉ đúng nếu không thay đổi ý nghĩa phản hồi.

## 8. Kỹ thuật 2: song song hóa các truy vấn độc lập

Nếu dashboard cần profile và recent orders dựa trên customerId đã xác thực:

~~~text
Before:
Authentication -> Profile -> Orders -> Response

After:
Authentication -> +-> Profile ---+
                  +-> Orders ----+-> Response
~~~

Hai nhánh có thể chạy song song khi không cần kết quả của nhau và chính sách nhất quán cho phép. Với dữ liệu cần cùng snapshot hoặc version, việc đọc song song từ hai service không tự đảm bảo kết quả cùng thời điểm.

### 8.1. Trường hợp không được song song hóa mù

~~~text
Validate coupon
      |
      v
Calculate final payable amount
      |
      v
Authorize payment
~~~

Payment cần số tiền sau giảm giá. Nếu lấy giá cũ rồi authorize đồng thời với Validate coupon, hệ thống có thể thu sai tiền. Đây là dependency thật sự; cải tiến phù hợp là giảm work bên trong Pricing hoặc thiết kế lại contract, không phải tạo futures cho hai bước phụ thuộc.

### 8.2. Giữ ranh giới nghiệp vụ

Song song query Pricing và Inventory không có nghĩa Ordering được cập nhật bảng tồn kho hay chính sách giá. Mỗi bounded context vẫn sở hữu dữ liệu và bất biến của mình. Cách phân chia câu trả lời có thể đổi, quyền quyết định không đổi.

## 9. Ví dụ Spring Boot: fan-out có giới hạn

Một use case tổng hợp trang tài khoản gọi hai port truy vấn:

~~~java
package example.dashboard;

import java.util.List;

interface ProfilePort {
    Profile getProfile(String customerId);
}

interface OrderHistoryPort {
    List<OrderSummary> recentOrders(String customerId);
}

record Profile(String displayName) {}
record OrderSummary(String orderId, String status) {}
record DashboardView(Profile profile, List<OrderSummary> orders) {}
~~~

Khai báo executor có giới hạn thay vì tạo thread tự do cho mỗi request:

~~~java
package example.dashboard;

import java.util.concurrent.Executor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class QueryExecutorConfig {
    @Bean("dashboardIoExecutor")
    Executor dashboardIoExecutor() {
        var pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(8);
        pool.setMaxPoolSize(16);
        pool.setQueueCapacity(100);
        pool.setThreadNamePrefix("dashboard-io-");
        pool.initialize();
        return pool;
    }
}
~~~

Gọi đồng thời hai truy vấn độc lập:

~~~java
package example.dashboard;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.TimeUnit;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
class DashboardService {
    private final ProfilePort profiles;
    private final OrderHistoryPort orders;
    private final Executor executor;

    DashboardService(
            ProfilePort profiles,
            OrderHistoryPort orders,
            @Qualifier("dashboardIoExecutor") Executor executor) {
        this.profiles = profiles;
        this.orders = orders;
        this.executor = executor;
    }

    DashboardView load(String customerId) {
        var profileFuture = CompletableFuture.supplyAsync(
                () -> profiles.getProfile(customerId), executor);

        var ordersFuture = CompletableFuture.supplyAsync(
                () -> orders.recentOrders(customerId), executor);

        CompletableFuture.allOf(profileFuture, ordersFuture)
                .orTimeout(350, TimeUnit.MILLISECONDS)
                .join();

        return new DashboardView(
                profileFuture.join(), ordersFuture.join());
    }
}
~~~

**Giới hạn của ví dụ:** 350 ms chỉ là số giả định. Timeout trên CompletableFuture giới hạn thời gian chờ kết quả, **không bảo đảm hủy** HTTP call đang block; phải cấu hình timeout của HTTP client và cancellation phù hợp. Khi một future lỗi, ứng dụng cần ánh xạ CompletionException thành phản hồi hoặc partial result theo contract. Executor và connection pool cần sizing qua đo tải; mã chỉ minh họa cách diễn tả hai nhánh độc lập, không phải cấu hình production hoàn chỉnh.

### 9.1. Tránh parallelStream cho fan-out không kiểm soát

~~~java
return ids.parallelStream()
        .map(catalogClient::getProduct)
        .toList();
~~~

Đoạn trên có thể phát nhiều RPC theo số phần tử đầu vào mà không có giới hạn rõ theo tải của Catalog, khiến quá tải khi ids dài. Nếu có API batch, hãy ưu tiên batch. Nếu cần fan-out, dùng concurrency limiter, deadline và pool có cấu hình đo được.

### 9.2. Reactive không tự xóa phụ thuộc tuần tự

WebClient, Mono.zip và Flux có thể thực hiện I/O bất đồng bộ, nhưng nếu B cần kết quả A thì A.flatMap(B) vẫn phụ thuộc A. Chuyển toàn bộ code sang reactive không làm rút ngắn một chuỗi service gồm những quyết định thật sự nối tiếp.

## 10. Kỹ thuật 3: batching để giảm remote N+1

Ví dụ code dễ gây N+1:

~~~java
var orders = orderRepository.findRecent(customerId);

for (var order : orders) {
    var profile = customerClient.getById(order.customerId());
    // Combine order and profile
}
~~~

Nếu có 100 order, đoạn code có thể tạo 100 RPC, kể cả khi nhiều order của cùng một khách. Giải pháp là thu thập khóa duy nhất và hỏi dữ liệu theo lô:

~~~text
1. Read recent orders.
2. Extract distinct customerIds.
3. Call one bounded batch API for those IDs.
4. Join results locally into view models.
~~~

Pseudocode Java:

~~~java
var orders = orderRepository.findRecent(customerId);

var customerIds = orders.stream()
        .map(Order::customerId)
        .distinct()
        .toList();

var customers = customerClient.getByIds(customerIds);

var views = orders.stream()
        .map(o -> toView(o, customers.get(o.customerId())))
        .toList();
~~~

Đây là minh họa ý tưởng; Order, toView và getByIds cần được định nghĩa trong ứng dụng cụ thể. API batch cần giới hạn số ID, kích thước payload, quyền truy cập theo ID, partial failure, dữ liệu thiếu, pagination và có thể chia batch khi danh sách quá lớn.

**Không biến 100 RPC nhỏ thành một request khổng lồ** mà không đo; một batch rất lớn có thể tăng memory, latency và head-of-line blocking. Batch size phải dựa trên workload và SLO.

## 11. Kỹ thuật 4: thiết kế query API theo use case

Nếu Catalog sở hữu tên, ảnh và category của sản phẩm, một màn chi tiết không nên bắt client gọi:

~~~text
GET /products/{id}/name
GET /products/{id}/thumbnail
GET /products/{id}/category
GET /products/{id}/brand
~~~

Một API như GET /products/{id}/summary có thể trả đúng những trường màn hình cần, giảm round trip. Tuy nhiên nó vẫn nên trả **DTO dành cho contract**, không phơi bày nguyên JPA entity hoặc cấu trúc bảng.

### 11.1. API composition và BFF

Một Backend for Frontend (BFF) có thể ghép dữ liệu từ các service để đáp ứng nhu cầu của web/mobile:

~~~text
Web app -> Web BFF -> Catalog + Reviews + Pricing
Mobile  -> Mobile BFF -> Catalog + Pricing + Availability
~~~

BFF có ích khi client không nên tự orchestration nhiều backend. Nó vẫn cần hạn chế fan-out, deadline, cache/fallback và quan sát. BFF không nên trở thành nơi chứa quy tắc nghiệp vụ thuộc Pricing, Inventory hay Ordering.

### 11.2. Bỏ các tầng chỉ proxy nếu không có trách nhiệm

~~~text
Before: A -> B -> C -> D

Possible review:
- B or C có thực sự sở hữu nghiệp vụ riêng?
- A có thể lấy dữ liệu từ owner qua hợp đồng phù hợp?
- B có nên trả view đã tổng hợp?
- Có thể duy trì một projection phục vụ nhu cầu đọc?
~~~

Bỏ tầng proxy có thể giảm hop, nhưng **cho A gọi D trực tiếp không tự động tốt hơn** nếu nó tạo coupling, vượt quyền truy cập hoặc làm rò rỉ mô hình. Cần tôn trọng boundary và hợp đồng.

## 12. Kỹ thuật 5: read model/projection cho các màn tổng hợp

Một trang lịch sử đơn cần tên sản phẩm, giá chốt, trạng thái vận chuyển và trạng thái hỗ trợ. Nếu với mỗi dòng trên danh sách đều gọi nhiều service, fan-out tăng theo số dòng.

Có thể duy trì một read model:

~~~text
[Ordering] -- OrderConfirmed -----+
[Catalog]  -- ProductPublished ---+--> Projection updater
[Shipping] -- ShipmentChanged ----+
                                          |
                                          v
                                  [OrderView Store]
                                          |
                                          v
                                GET /my-orders
~~~

Read model là **bản sao dành cho đọc**, được cập nhật từ hợp đồng sự kiện. Nó không thay thế nguồn sự thật hay quyền ghi của các context. Khi consumer bị trễ, projection có thể stale; cần nêu rõ độ trễ chấp nhận được, quy trình replay/rebuild, xử lý event trùng, sự kiện sai thứ tự và reconciliation.

Ví dụ, lịch sử đơn có thể hiển thị status shipping trễ vài giây. Nhưng quyết định hoàn tiền hoặc thu tiền cần dựa vào nơi sở hữu trạng thái có thẩm quyền và quy tắc được chỉ định, không dựa mù vào projection.

## 13. Kỹ thuật 6: cache đúng chỗ

Cache thường có ích cho dữ liệu ít đổi như taxonomy, các cấu hình công khai hoặc read-heavy reference data. Trước khi cache, phải xác định:

- Cache key có bao gồm thị trường, currency, phân khúc hoặc quyền truy cập không?
- TTL là bao lâu và sai lệch tạm thời có được phép không?
- Có invalidation theo event/version để giảm stale không?
- Khi nhiều request cùng cache miss, có stampede làm quá tải downstream không?
- Có được negative cache kết quả không tồn tại hoặc lỗi tạm thời không?
- Dữ liệu có nhạy cảm theo tenant hoặc người dùng không?

Cache giá, quyền truy cập, inventory availability và payment status cần thận trọng đặc biệt vì stale data có thể làm kết quả nghiệp vụ sai. Nếu Pricing cung cấp quote có quoteId và expiry, consumer phải tôn trọng thời điểm hiệu lực thay vì dùng giá cũ không điều kiện.

**Cache không sửa được data ownership sai.** Ordering đọc thẳng bảng Pricing rồi cache vẫn phụ thuộc schema nội bộ của Pricing.

## 14. Khi nào không được bỏ lời gọi đồng bộ?

Có các bước buộc phải hoàn tất trước khi đưa ra lời hứa:

- Xác thực người yêu cầu có quyền đọc dữ liệu nhạy cảm.
- Kiểm tra báo giá cuối cùng trước khi khách chấp nhận thanh toán.
- Đánh giá giới hạn tín dụng trước khi xác nhận khoản vay.
- Xác minh điều kiện tồn kho trước khi hứa chắc chắn có hàng.
- Kiểm tra một business invariant quyết định có chấp nhận lệnh hay không.

Tại các bước này, hãy tối ưu placement và contract, lập deadline, giới hạn retry và xử lý lỗi rõ. **Không chuyển async chỉ để frontend nhanh hơn nếu điều đó làm response nói sai trạng thái.**

### 14.1. Giữ invariant ở service sở hữu

Ví dụ Inventory bảo đảm không giữ quá lượng hàng có thể bán. Dù Ordering gọi bằng REST, gRPC hay message, Inventory vẫn phải kiểm soát concurrency và transaction nội bộ. Để bỏ một network hop, Ordering không được trực tiếp UPDATE bảng inventory.

### 14.2. Một quy trình có thể kết hợp sync và async

Ví dụ Order có thể lấy quote đồng bộ, sau đó lưu đơn PENDING và gửi ReserveStock command bất đồng bộ. Nhưng nếu nghiệp vụ bắt buộc xác nhận đủ hàng trước khi trả trạng thái CONFIRMED, cần chờ kết quả giữ hàng hoặc điều chỉnh lời hứa của API.

## 15. Deadline, timeout và retry trong chuỗi gọi

Một lỗi thường gặp: Browser đợi 800 ms, nhưng Gateway, Order và Inventory mỗi nơi đặt timeout 3 giây; retry xảy ra ở nhiều tầng. Request có thể tiếp tục tiêu tốn tài nguyên khi người dùng đã bỏ cuộc.

Cần lập **ngân sách thời gian đầu cuối**:

~~~text
Client deadline        800 ms
Gateway/auth budget     80 ms
Ordering local         120 ms
Downstream critical    450 ms
Response/margin        150 ms
~~~

Các con số chỉ là ví dụ. Deadline nên được truyền qua những lời gọi con khi môi trường cho phép, hoặc mỗi lớp tính được thời gian còn lại. Timeout HTTP client vẫn cần cấu hình riêng.

### 15.1. Retry amplification

Giả sử A gọi B, B gọi C và cả hai tầng đều retry tối đa ba lần khi thất bại:

~~~text
Request A
   |
   +-- B attempt 1 -> C attempt 1,2,3
   +-- B attempt 2 -> C attempt 1,2,3
   +-- B attempt 3 -> C attempt 1,2,3

Potential calls to C = 9 for one A request
~~~

Chỉ cần thêm fan-out, một request có thể tạo tải lớn đúng lúc downstream quá tải. Nên giới hạn retry, dùng backoff/jitter, không retry quá deadline, chọn một lớp chịu trách nhiệm và phân biệt lỗi tạm thời với lỗi nghiệp vụ.

### 15.2. Timeout không có nghĩa chưa xử lý

Payment có thể đã commit nhưng response bị mất. Ordering timeout không chứng minh Payment thất bại. Nếu retry bằng paymentId mới, có thể thu tiền hai lần. Cần idempotency key ổn định, tra kết quả theo operationId và reconciliation.

Hủy chờ HTTP cũng không tự rollback tác vụ đã bắt đầu ở service khác. Nếu cần bù trừ, phải có state machine/Saga và lệnh compensation phù hợp.

## 16. Bounded concurrency: song song mà không quá tải

Nếu một Aggregator nhận 500 request/giây và mỗi request gọi song song 20 downstream, một lớp có thể tạo 10.000 request nội bộ/giây chưa kể retry. Ở tải nhẹ, song song làm một request nhanh hơn; ở tải lớn, saturation có thể làm toàn hệ thống chậm hơn.

Các lựa chọn thường dùng:

- Executor hoặc connection pool có giới hạn.
- Semaphore/bulkhead giới hạn RPC đồng thời theo downstream.
- Batch API giảm số request trên một use case.
- Caching/projection cho dữ liệu đọc lặp lại.
- Rate limit, queueing hoặc backpressure khi hệ thống đầy.
- Deadline và circuit breaker phù hợp với loại dependency.
- Load test ở mức traffic bình thường và peak.

**Mục tiêu không phải chạy càng nhiều RPC đồng thời càng tốt.** Mục tiêu là đạt latency SLO với error rate và tài nguyên chấp nhận được.

### 16.1. Bảo vệ workload quan trọng

Nếu cùng một thread/connection pool phục vụ truy vấn search nặng và thanh toán, search tăng tải có thể làm checkout chậm. Có thể cô lập pool hoặc áp giới hạn tài nguyên theo loại việc. Quyết định nên dựa trên trace, profile và sức chứa thực tế.

## 17. Suy giảm có kiểm soát và partial response

Cần định nghĩa rõ nhánh **bắt buộc** và **tùy chọn**:

~~~text
Checkout:
  Required: Auth, valid price, order decision
  Optional: Recommendations, decorative badges
~~~

Nếu Recommendations trả 503, UI có thể bỏ khối gợi ý. Nếu Pricing không phản hồi và chưa có quote hợp lệ, không được tự sử dụng giá 0 hay giá cache chưa được phép để hoàn tất đơn.

Các chiến lược:

- **Fail fast:** kết thúc sớm khi bước bắt buộc không thể đáp ứng deadline.
- **Partial response:** trả phần có sẵn nếu contract cho phép và chỉ rõ dữ liệu thiếu.
- **Fallback:** sử dụng nguồn thay thế được nghiệp vụ chấp nhận, với TTL/version phù hợp.
- **Graceful degradation:** chỉ giảm tính năng phụ.
- **Async continuation:** nếu quy trình được phép chờ, trả PENDING/operationId.
- **Circuit breaker/bulkhead:** ngăn lỗi dây chuyền và cạn tài nguyên.

Một nhánh có thể tùy chọn ở màn hình này nhưng bắt buộc ở use case khác. Ví dụ điểm thưởng có thể chỉ để hiển thị, hoặc là điều kiện tính số tiền khách phải trả. Cần phân loại theo **hành vi nghiệp vụ cụ thể**.

## 18. Code smell: RPC ẩn trong mapper và getter

Một mapper tưởng là thuần dữ liệu:

~~~java
public OrderView toView(Order order) {
    var customerName =
            customerClient.getName(order.customerId());
    var productImage =
            catalogClient.getImage(order.productId());

    return new OrderView(
            order.id(), customerName, productImage);
}
~~~

Nếu mapper chạy trên 200 order, nó có thể tạo 400 RPC. Người review chỉ nhìn tên toView không nhận ra I/O. Nên tách giai đoạn **fetch dữ liệu** và **map dữ liệu**:

~~~text
1. Load orders once.
2. Collect distinct customer and product IDs.
3. Fetch bounded batches (possibly independent and parallel).
4. Assemble views locally without network calls in mapper.
~~~

Tác vụ I/O cần hiển thị rõ trong service orchestration để kiểm soát timeout, giới hạn tải và tracing.

## 19. Lựa chọn REST, gRPC hay message có thay đổi vấn đề không?

| Cách giao tiếp | Có thể giúp gì? | Không tự giải quyết gì? |
| --- | --- | --- |
| REST/HTTP | Contract rộng, dễ tích hợp và debug | Chuỗi chờ nhiều hop, transaction phân tán |
| gRPC | Typed contract, hiệu quả với một số workload, streaming | Phụ thuộc tuần tự nếu caller vẫn phải chờ |
| Queue | Buffer công việc, tách thời điểm producer/consumer | Lời hứa hoàn tất ngay, data consistency và idempotency |
| Pub/sub events | Nhiều consumer phản ứng độc lập, giảm chặn request | Schema/semantic coupling, duplicate delivery |
| Read model | Giảm fan-out đọc tổng hợp | Staleness, replay, reconciliation |
| Local module call | Bỏ network overhead và đơn giản transaction | Cần bảo vệ module boundary và ownership |

Không có công nghệ thay cho phân tích dependency graph. Chuyển một chuỗi A → B → C từ REST sang gRPC có thể giảm overhead nhưng vẫn là ba bước nối tiếp nếu B phải chờ C. Chuyển sang Kafka có thể khiến API trả sớm hơn, nhưng nhiệm vụ nghiệp vụ có thể vẫn chưa hoàn tất.

## 20. Khi nào ranh giới service đang tạo chuỗi gọi thừa?

Một thiết kế chia theo tầng kỹ thuật có thể trông như:

~~~text
Order API Service
  -> Order Validation Service
  -> Order Business Service
  -> Order Repository Service
  -> Order Database
~~~

Nếu các thành phần chỉ phục vụ cùng một năng lực Order, không có model, data ownership hoặc nhịp thay đổi độc lập, phân tán chúng có thể tăng latency và coupling mà không tăng tự chủ. Có thể nên đưa chúng về cùng Ordering Context/module/service để giữ các bất biến cần transaction cục bộ.

Ngược lại, Pricing và Inventory là những context thực sự khác nhau; đừng gộp hoặc cho đọc/ghi database xuyên miền chỉ để xóa một RPC. Thay đổi boundary cần cân nhắc domain, quyền sở hữu dữ liệu, contract, deployment independence và lợi ích kinh doanh.

### 20.1. Tối ưu mà không làm distributed monolith tệ hơn

Nếu A trực tiếp đọc database của D để “bỏ qua B và C”, có thể khiến schema coupling cao và phá data ownership. Một API tổng hợp của D hoặc read projection do A quản lý thường tốt hơn nếu đáp ứng yêu cầu dữ liệu và độ trễ.

**Số hop nhỏ là dấu hiệu hữu ích, không phải mục tiêu tối thượng.** Một sơ đồ ít mũi tên nhưng phụ thuộc trực tiếp bảng dữ liệu của nhau vẫn là kiến trúc dễ vỡ.

## 21. Quy trình tối ưu một endpoint đang chậm

### Bước 1 — Nêu mục tiêu

Ví dụ GET /checkout-preview cần p95 dưới 500 ms ở mức tải mục tiêu, trả báo giá và số lượng tồn theo hợp đồng. Recommendation là tùy chọn.

### Bước 2 — Thu thập baseline

Ghi p50/p95/p99, request rate, error/timeout rate, dependency call count, retry count, DB latency, saturation, cache hit rate và trace cho các request chậm.

### Bước 3 — Vẽ call graph đúng thực tế

~~~text
Auth -> Read Cart
            |
            +-> Pricing --------+
            +-> Inventory ------+-> Assemble
            +-> Recommendation -+
~~~

Kiểm tra nhánh nào tuần tự do phụ thuộc dữ liệu, nhánh nào chỉ tuần tự vì code viết theo thứ tự.

### Bước 4 — Xác định critical path và nhánh tùy chọn

Đánh dấu lời gọi phải có để trả kết quả, bước cho phép partial/fallback, dữ liệu có thể stale và bước có thể xử lý sau commit.

### Bước 5 — Chọn can thiệp nhỏ

Có thể batch pricing cho nhiều SKU, chạy pricing và stock query song song, tách recommendation sang request riêng, hoặc trả read model theo một query. Không cần đổi toàn hệ thống cùng lúc.

### Bước 6 — Thiết kế failure semantics

Nếu Pricing timeout, có được dùng quote còn hiệu lực không? Nếu một SKU thiếu trong batch, response trả gì? Nếu request bị hủy, các command đã gửi xử lý thế nào? Cần chính sách trước khi rollout.

### Bước 7 — Thử nghiệm ở tải đại diện

Đo lại end-to-end latency, throughput, error rate và tải downstream. Đảm bảo không vì giảm p50 mà làm p99 hoặc tỷ lệ lỗi tệ hơn.

### Bước 8 — Theo dõi sau triển khai

Dùng tracing/metrics tiếp tục xác định bottleneck mới, khả năng saturation và business outcome. Kiến trúc được đánh giá bằng hành vi production, không bằng số lượng CompletableFuture đã thêm.

## 22. Ví dụ định lượng: trang thông tin sản phẩm

Tình huống giả định:

~~~text
Product core API           60 ms
Pricing API                85 ms
Availability API          110 ms
Reviews summary API       145 ms
Recommendations API       190 ms
Gateway/assembly           35 ms
~~~

Nếu năm lời gọi tuần tự:

~~~text
T ~= 60 + 85 + 110 + 145 + 190 + 35 = 625 ms
~~~

Nếu bốn nhánh sau Product core độc lập và chạy song song:

~~~text
T ~= 60 + max(85,110,145,190) + 35 = 285 ms
~~~

Nếu Recommendations là tùy chọn và tải riêng:

~~~text
T_main ~= 60 + max(85,110,145) + 35 = 240 ms
Recommendation completed separately.
~~~

Các phép tính là mô hình trực giác, bỏ qua queueing, resource contention và biến động latency. Không được dùng chúng thay benchmark p95/p99 thực. Nếu Pricing cần availability để tính giá theo điều kiện tồn, chúng không độc lập và phép tính song song không còn đúng.

## 23. Những lỗi thường gặp khi tối ưu

**“Cứ dùng CompletableFuture sẽ nhanh.”** Khi hai tác vụ phụ thuộc, chạy song song có thể cho kết quả sai. Quá nhiều futures có thể làm nghẽn thread hoặc connection pool.

**“Dùng WebFlux là không còn chuỗi gọi dài.”** Nonblocking I/O giúp sử dụng tài nguyên hiệu quả, nhưng không tự thay đổi dependency graph.

**“Chuyển REST sang gRPC để xóa latency.”** Serialization có thể cải thiện, nhưng mạng, DB và độ sâu chuỗi vẫn tồn tại.

**“Cache mọi dữ liệu để tránh RPC.”** Cache không tôn trọng TTL/ownership có thể làm sai giá, stock hoặc quyền truy cập.

**“Một request gọi 20 service chắc chắn sai.”** Cần xét critical path, fan-out, workload và mục tiêu; báo cáo nền có thể cần nhiều nguồn mà không làm chậm tương tác người dùng.

**“Nếu đã gửi message thì đã thành công.”** Broker ACK chỉ chứng minh mức tiếp nhận phù hợp cấu hình, không chứng minh nghiệp vụ đã hoàn tất.

**“Timeout là chưa commit.”** Có thể commit rồi mất response; retry phải an toàn và theo dõi trạng thái.

**“Gọi song song càng nhiều càng tốt.”** Downstream saturation làm queueing và tail latency tăng.

**“Bỏ một service trung gian luôn tốt hơn.”** Có thể tạo coupling trực tiếp hoặc phá quyền sở hữu dữ liệu. Cần hiểu boundary và contract.

## 24. Bài tập tình huống

### Bài 1 — Phân biệt nhánh phụ thuộc

Checkout Preview cần lấy cart, báo giá, số lượng tồn và điểm thưởng. Báo giá và tồn kho cùng cần danh sách SKU trong cart; điểm thưởng chỉ dùng hiển thị. Hãy vẽ critical path.

**Gợi ý:** Read Cart trước. Sau đó có thể chạy Pricing và Availability song song nếu chúng độc lập theo chính sách. Điểm thưởng có thể chạy cùng nếu biết customerId, hoặc tải sau nếu không phải điều kiện tính tiền. Không dùng kết quả stale trái với lời hứa checkout.

### Bài 2 — Remote N+1

Một trang hiển thị 150 đơn, mỗi đơn gọi Customer và Catalog để lấy thông tin. Nếu mỗi đơn có một sản phẩm và không có cache, bao nhiêu RPC có thể xảy ra?

**Gợi ý:** 300 RPC downstream (150 Customer + 150 Catalog), chưa kể truy vấn khác. Nên collect IDs, deduplicate, batch hoặc dùng read model. Nếu nhiều dòng hàng, số lookup còn tăng.

### Bài 3 — So sánh tuần tự và song song

Ba truy vấn độc lập mất 40 ms, 80 ms và 120 ms. Bỏ qua overhead, thời gian tuần tự và song song là bao nhiêu?

**Gợi ý:** Tuần tự gần 240 ms; song song gần 120 ms. Đây không phải bảo đảm p95/p99 của production.

### Bài 4 — Email làm endpoint đặt hàng thất bại

Order đã commit, nhưng Email Service trả 500 khiến API trả lỗi. Client retry và tạo đơn mới. Cần chỉnh gì?

**Gợi ý:** Nếu email không quyết định việc tạo đơn thành công, đưa nó sang consumer async qua outbox/event. Dùng idempotency key cho PlaceOrder; trả đúng trạng thái Order đã commit.

### Bài 5 — Payment timeout

Ordering gọi Payment và timeout; một kỹ sư muốn gửi lại bằng paymentId khác để tránh chờ.

**Gợi ý:** Nguy cơ charge hai lần. Dùng idempotency key/operationId ổn định, tra cứu kết quả và reconciliation theo hợp đồng. Timeout không chứng minh thanh toán thất bại.

### Bài 6 — Song song hóa sai

Một nhóm chạy ValidateCoupon và AuthorizePayment cùng lúc để giảm 100 ms, trong khi số tiền authorize phụ thuộc kết quả coupon.

**Gợi ý:** Hai bước phụ thuộc dữ liệu; song song có thể thu sai tiền. Tối ưu bên trong Pricing hoặc thiết kế request giảm hop, nhưng giữ thứ tự quyết định.

### Bài 7 — Fan-out gây nghẽn

Aggregator nhận 500 request/giây, mỗi request song song gọi 20 RPC. p50 giảm khi test nhẹ nhưng p99 production tăng và connection pool cạn.

**Gợi ý:** Tổng workload tăng. Đo request amplification, giới hạn concurrency, batching, read model và capacity. SLO toàn hệ thống quan trọng hơn latency một request đơn lẻ.

### Bài 8 — Báo cáo từ nhiều context

Màn quản trị hiển thị 20.000 dòng, mỗi dòng cần dữ liệu từ 6 service; chấp nhận báo cáo cập nhật trễ 30 giây.

**Gợi ý:** Projection/read model có thể phù hợp hơn fan-out theo từng dòng. Cần event lag, rebuild, replay, idempotency và reconciliation.

### Bài 9 — Giảm latency nhưng tăng lỗi

Sau batching, p50 giảm 25% nhưng tỷ lệ lỗi tăng từ 0,1% lên 1,5% vào giờ cao điểm. Có nên tuyên bố tối ưu thành công?

**Gợi ý:** Chưa. Cần đánh giá p95/p99, batch limit, memory, queue, DB load, error budget và business outcome. Mục tiêu phải bao gồm độ tin cậy.

### Bài 10 — Bỏ ownership để giảm một hop

Order muốn cập nhật trực tiếp bảng stock thay vì gọi Inventory Service để giảm latency.

**Gợi ý:** Không nên phá quyền sở hữu và invariant của Inventory. Có thể giảm số lần gọi, thiết kế batch reservation, tối ưu Inventory hoặc xem lại sync/async workflow theo nghiệp vụ.

## 25. Checklist trước khi phát hành

- [ ] Đã mô tả use case, SLO và lời hứa của response.
- [ ] Có call graph/trace của luồng thật và xác định critical path.
- [ ] Biết bước nào bắt buộc, tùy chọn, có thể chạy sau.
- [ ] Chỉ song song hóa bước không phụ thuộc dữ liệu hay bất biến.
- [ ] Đã tìm remote calls trong loop, mapper, getter và xử lý N+1.
- [ ] Có đánh giá batching, query API, cache và projection nếu phù hợp.
- [ ] Vẫn giữ ranh giới bounded context và quyền ghi dữ liệu.
- [ ] Có deadline end-to-end và timeout downstream thích hợp.
- [ ] Retry có giới hạn, idempotency và xử lý unknown outcome.
- [ ] Có concurrency cap, pool sizing và backpressure phù hợp.
- [ ] Contract cho phép partial response/fallback khi dùng phương án đó.
- [ ] Có trace/correlation ID, log, metrics và cảnh báo.
- [ ] Dữ liệu cache/projection có stale policy rõ ràng.
- [ ] Đã đo p95/p99, throughput, saturation và error rate dưới tải đại diện.
- [ ] Sau rollout, có thể xác định bottleneck mới và rollback an toàn.

## 26. Ghi nhớ

1. **Critical path quyết định độ trễ đầu cuối.** Giảm các bước bắt buộc chờ có ích hơn tối ưu một đoạn code không nằm trên đường chậm.
2. **Chỉ nối tiếp khi có quan hệ dữ liệu hoặc nghiệp vụ thật.** Những truy vấn độc lập có thể thực hiện song song với giới hạn concurrency.
3. **Remote N+1 và fan-out lồng nhau làm khuếch đại tải.** Dùng batch API, DTO tổng hợp hoặc projection khi có lợi ích rõ.
4. **Đưa việc nền ra khỏi đường trả lời nếu hợp đồng cho phép.** Trả PENDING khác với CONFIRMED; message ACK khác hoàn tất nghiệp vụ.
5. **Giữ đúng invariant và data ownership.** Không phá boundary hoặc dùng stale data bừa bãi chỉ để bỏ một hop.
6. **Deadline, timeout, retry an toàn và idempotency** giúp kiểm soát lỗi dây chuyền trên đường đồng bộ.
7. **Đo ở tải thực bằng tracing và SLO.** Một phương án chỉ tốt khi latency giảm mà tính đúng đắn, khả năng chịu tải và độ tin cậy vẫn đáp ứng yêu cầu.