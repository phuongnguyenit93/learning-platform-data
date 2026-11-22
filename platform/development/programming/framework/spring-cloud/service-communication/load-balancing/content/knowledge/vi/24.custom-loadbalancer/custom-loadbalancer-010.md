# Kiểm thử tính đúng, độ công bằng và chi phí thuật toán

Khi tự viết thuật toán cân bằng tải cho **Spring Cloud LoadBalancer**, việc thấy request đi được tới một replica chưa đủ để kết luận thuật toán đúng. Một thuật toán có thể vượt qua kiểm thử thủ công nhưng vẫn chọn nhầm instance đã bị lọc, phân phối lệch kéo dài, gây tranh chấp giữa các thread, tạo quá nhiều đối tượng hoặc làm thời gian chọn đích tăng mạnh khi có hàng nghìn `ServiceInstance`.

Bài này thuộc chương **Tùy biến LoadBalancer** của module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Mục tiêu là xây dựng bộ kiểm thử có thể lặp lại cho **tính đúng (correctness)**, **độ công bằng (fairness)** và **chi phí thuật toán (cost)** trong giao tiếp service-to-service. Các ví dụ nối với service ID, `ServiceInstanceListSupplier`, chính sách discovery/health/zone, RestClient, WebClient và OpenFeign; phần đo hiệu năng tách rõ chi phí của thuật toán chọn instance với tổng thời gian HTTP.

## 1. Ba câu hỏi phải kiểm tra độc lập

| Góc độ | Câu hỏi chính | Tiêu chí kiểm chứng |
|---|---|---|
| **Tính đúng** | Đã chọn instance hợp lệ, đúng service ID, đúng policy chưa? | Không chọn ngoài tập ứng viên, xử lý danh sách rỗng, tôn trọng metadata/request context |
| **Độ công bằng** | Tỷ lệ chọn mỗi instance có phù hợp chiến lược đã công bố không? | Round Robin cân đối trên danh sách ổn định; Random/Weighted theo phân bố xác suất kỳ vọng |
| **Chi phí** | Chọn instance có tốn quá nhiều CPU, memory, allocation hoặc lock contention không? | Độ phức tạp, p95/p99 thời gian chọn, throughput, allocation và mức tranh chấp ở concurrency cao |

Một thuật toán có thể **đúng và công bằng nhưng chậm**, hoặc **nhanh và đúng nhưng không công bằng**, hoặc đạt cả ba khi kiểm thử unit nhưng suy giảm do discovery, retry, cache và HTTP transport trong thực tế.

Ví dụ: bộ chọn “luôn lấy phần tử đầu danh sách” là `O(1)` và có thể không chọn instance ngoài tập ứng viên; nhưng với 3 replica khỏe và cùng trọng số, nó phân phối 100% request đến một backend. Ngược lại, thuật toán quét và sắp xếp toàn bộ candidate list mỗi request có thể chọn đúng đích nhưng tạo `O(n log n)` công việc không cần thiết.

### Ba lớp test cần tách

~~~mermaid
flowchart TB
    A["Tầng 1: Unit test bộ chọn thuần"] --> B["Tầng 2: Test ReactorLoadBalancer và supplier"]
    B --> C["Tầng 3: HTTP integration / chaos / performance"]
    A --> D["Correctness + fairness xác định"]
    B --> E["Request context, discovery, filter, no-instance"]
    C --> F["Instance thật, retry, p99 latency, overhead"]
~~~

Các tầng trả lời những câu hỏi khác nhau. Một unit test `choose()` không chứng minh WebClient đã mang filter LoadBalancer; một bài load test HTTP không chứng minh bộ chọn không có race condition ở danh sách chỉ có một instance.

## 2. Mô hình lựa chọn đích trong Spring Cloud

Spring Cloud LoadBalancer sử dụng `ReactiveLoadBalancer`/`ReactorServiceInstanceLoadBalancer` và nguồn ứng viên `ServiceInstanceListSupplier`. Với service ID `inventory-service`, chuỗi khái niệm:

~~~mermaid
flowchart LR
    A["Caller: service ID"] --> B["ServiceInstanceListSupplier"]
    D["DiscoveryClient"] --> B
    B --> C["Cache / health / zone / hint policy"]
    C --> E["Candidate snapshot"]
    E --> F["Custom ReactorServiceInstanceLoadBalancer"]
    F --> G["Một ServiceInstance hoặc EmptyResponse"]
    G --> H["HTTP client transport"]
~~~

Một số quyết định quan trọng:

- **Nguồn ứng viên**: discovery có thể trả về instance mới/cũ, nhiều instance trong zone khác nhau, hoặc danh sách rỗng.
- **Lọc chính sách**: health, hint, zone, version, sticky preference hoặc request-aware supplier có thể thay đổi tập ứng viên trước khi chọn.
- **Bộ chọn**: Round Robin, Random, Weighted, least-active, hash/affinity hoặc chính sách tùy biến.
- **Tích hợp HTTP**: RestClient, WebClient, OpenFeign chọn instance khi client đã được cấu hình tích hợp Spring Cloud LoadBalancer.
- **Retry**: một *logical request* có thể chọn instance nhiều lần; đo số lần gọi `choose` khác với số request backend nhận được.

Thử nghiệm phải ghi rõ **candidate list tại đúng thời điểm chọn**, không chỉ lấy danh sách đăng ký ban đầu từ registry. Nếu zone filter loại một replica, nó không nên được tính vào mẫu số khi đánh giá công bằng của bộ chọn.

## 3. Viết “hợp đồng đúng” trước khi viết assertions

Ví dụ một bộ chọn Round Robin cho `inventory-service` có hợp đồng:

1. Nếu danh sách rỗng, trả “không có instance”; không cố truy cập index 0.
2. Nếu danh sách một phần tử, trả chính instance đó.
3. Nếu danh sách có N phần tử, chỉ trả một phần tử nằm trong danh sách ứng viên nhận được.
4. Nếu supplier áp dụng zone/hint/health, không chọn lại instance bị loại.
5. Với cùng một **snapshot danh sách ổn định**, sau `k × N` lần chọn liên tiếp, mỗi candidate được chọn `k` lần (bỏ qua việc bắt đầu ở vị trí nào).
6. Với nhiều thread, không có race làm index vượt phạm vi hoặc chọn phần tử ngoài snapshot.
7. Không gọi mạng hay chặn event loop ngay trong logic chọn thuần.
8. Khi không có instance, không được ngụy tạo `DefaultResponse` chứa null.
9. Không dùng state của request trước để làm rò tenant, hint hoặc zone sang request kế tiếp.
10. Khi điều kiện input thay đổi, các invariant **an toàn** vẫn đúng; “luân phiên tuyệt đối” có thể không còn đúng.

Nếu thuật toán là Random/Weighted/Sticky, thay mục 5 bằng hợp đồng tương ứng. Một thuật toán có trọng số **không công bằng** khi đếm raw requests như Round Robin nếu weights không bằng nhau; công bằng ở đây nghĩa là phân phối phù hợp tỷ trọng mục tiêu.

### Bảng test cases tối thiểu

| Input | Hành vi phải kiểm tra | Failure thường gặp |
|---|---|---|
| Không có instance | `EmptyResponse` hoặc Optional empty | `IndexOutOfBoundsException`/divide by zero |
| Một instance | Luôn trả một instance đó | Chọn null hoặc ghi state sai |
| Hai/ba instance | Instance thuộc tập hợp hợp lệ | Trả instance ngoài tập |
| Danh sách có thể đổi | Không crash, không giữ index theo size cũ | `IndexOutOfBoundsException` |
| Weight 0/âm/sai định dạng | Chính sách rõ ràng: reject/fallback | Xác suất âm/NaN/overflow |
| Zone không có ứng viên | Hành vi fallback phù hợp policy | Tự ý chọn cross-zone trái hợp đồng |
| Hint, version, tenant | Chỉ chọn candidate phù hợp policy | Rò ngữ cảnh request cũ |
| Supplier trả lỗi | Propagate/fallback theo contract | Nuốt lỗi thành thành công giả |
| Concurrency cao | Không mất safety/không tạo hotspot nghiêm trọng | Race condition và contention |
| Retry | Có khả năng thay instance nếu policy yêu cầu | Lặp mãi backend lỗi |

## 4. Tách thuật toán chọn thuần khỏi adapter Spring

Một kỹ thuật hữu ích là đặt logic chọn đích vào class nhỏ, **không có HTTP, Spring context hay Reactor**. Khi đó unit tests có thể kiểm tra algorithm độc lập và tái lập kết quả.

Ví dụ `RoundRobinPicker`:

~~~java
package com.example.loadbalancer;

import java.util.List;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.cloud.client.ServiceInstance;

public final class RoundRobinPicker {

    private final AtomicLong sequence = new AtomicLong();

    public Optional<ServiceInstance> pick(
            List<ServiceInstance> candidates) {

        if (candidates == null || candidates.isEmpty()) {
            return Optional.empty();
        }

        long ticket = sequence.getAndIncrement();

        // Hợp lệ ngay cả khi AtomicLong wrap.
        int index = (int) Long.remainderUnsigned(
                ticket,
                candidates.size()
        );

        return Optional.of(candidates.get(index));
    }
}
~~~

### Giải thích thiết kế

- `AtomicLong` giúp các thread lấy ticket khác nhau mà không phải khóa toàn bộ method.
- `Long.remainderUnsigned` xử lý ticket như số nguyên không dấu, tránh lỗi index âm khi counter vượt `Long.MAX_VALUE`.
- `Optional.empty()` báo không có ứng viên.
- Thuật toán trả về **một instance đang nằm trong danh sách input**, không tạo object ServiceInstance mới.
- Với danh sách **ổn định**, lần chọn thứ `i` có index `i mod N`, nên trong mỗi N lượt sẽ chọn mỗi phần tử một lần.
- Nếu danh sách thay đổi kích thước/thứ tự, tiêu chí “luân phiên từng replica” không còn bảo đảm giữa hai snapshots; thuộc tính an toàn *selected ∈ current candidates* vẫn phải giữ.
- Code giả định `candidates` là một **snapshot danh sách read-only** trong toàn thời gian lời gọi. Nếu supplier cung cấp list có thể bị sửa đồng thời, cần tạo snapshot ở ranh giới publisher/supplier; không nên `List.copyOf` vô điều kiện ở mỗi lần chọn nếu muốn đánh giá chi phí `O(1)`.

Lưu ý: đây là **thuật toán minh họa để kiểm thử**, không phải đề xuất thay `RoundRobinLoadBalancer` chuẩn của Spring Cloud. Implementation chuẩn có logic/callback và xử lý riêng (chẳng hạn supplier chỉ có một instance) mà custom adapter phải cân nhắc khi triển khai production.

## 5. Unit test tính đúng: rỗng, một instance, nhiều instance

Tạo bộ mẫu bằng `DefaultServiceInstance`:

~~~java
package com.example.loadbalancer;

import java.util.List;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.ServiceInstance;

public final class Fixtures {

    private Fixtures() {}

    public static List<ServiceInstance> threeInstances() {
        return List.of(
                new DefaultServiceInstance(
                        "A", "inventory-service", "127.0.0.1", 8081, false),
                new DefaultServiceInstance(
                        "B", "inventory-service", "127.0.0.1", 8082, false),
                new DefaultServiceInstance(
                        "C", "inventory-service", "127.0.0.1", 8083, false)
        );
    }
}
~~~

JUnit Jupiter test:

~~~java
package com.example.loadbalancer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.ServiceInstance;

class RoundRobinPickerTest {

    @Test
    void emptyListNeverSelectsAnInstance() {
        RoundRobinPicker picker = new RoundRobinPicker();

        assertTrue(picker.pick(List.of()).isEmpty());
    }

    @Test
    void aSingleCandidateIsAlwaysSelected() {
        RoundRobinPicker picker = new RoundRobinPicker();
        ServiceInstance only = Fixtures.threeInstances().get(0);

        for (int i = 0; i < 100; i++) {
            assertEquals(only, picker.pick(List.of(only)).orElseThrow());
        }
    }

    @Test
    void oneCompleteCycleChoosesEveryCandidate() {
        RoundRobinPicker picker = new RoundRobinPicker();
        List<ServiceInstance> instances = Fixtures.threeInstances();

        for (int i = 0; i < 3; i++) {
            assertEquals(instances.get(i),
                    picker.pick(instances).orElseThrow());
        }
    }
}
~~~

Test này **deterministic** vì `RoundRobinPicker` khởi tạo ticket bằng 0. Với Spring `RoundRobinLoadBalancer` có seed ban đầu hoặc cách cập nhật cursor khác, không nên assert phần tử đầu tiên luôn là A: thay bằng kiểm tra *trong N lần chọn đã thấy đủ N ứng viên*.

### Test thuộc tính an toàn khi danh sách đổi

~~~java
@Test
void neverChoosesOutsideTheCurrentSnapshot() {
    RoundRobinPicker picker = new RoundRobinPicker();
    List<ServiceInstance> all = Fixtures.threeInstances();

    List<List<ServiceInstance>> snapshots = List.of(
            all,
            all.subList(0, 2),
            List.of(all.get(2)),
            List.of(),
            List.of(all.get(1), all.get(2))
    );

    for (int round = 0; round < 500; round++) {
        for (List<ServiceInstance> current : snapshots) {
            var selected = picker.pick(current);

            if (current.isEmpty()) {
                assertTrue(selected.isEmpty());
            } else {
                assertTrue(selected.isPresent());
                assertTrue(current.contains(selected.orElseThrow()));
            }
        }
    }
}
~~~

Bài test không yêu cầu một replica phải được chọn số lần bằng nhau xuyên những snapshots khác nhau. **Fairness phải được đánh giá trên tập ứng viên có cùng điều kiện**, không gom tất cả request vào một mẫu chung.

## 6. Unit test tính công bằng xác định của Round Robin

Với N instance không đổi, Round Robin lý tưởng có:

\[
|c_i-c_j|\leq1 \quad \text{với mọi }i,j
\]

sau `K` lượt chọn tuần tự hoặc đồng thời đã hoàn tất, nếu một counter duy nhất được chia sẻ và mỗi lần chọn tạo đúng một ticket.

Ví dụ cho 3 instances, 12.000 lần chọn:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

@Test
void equalCandidatesHaveExactlyEqualCountAcrossFullCycles() {
    RoundRobinPicker picker = new RoundRobinPicker();
    var instances = Fixtures.threeInstances();

    Map<String, Integer> counts = new HashMap<>();

    for (int i = 0; i < 12_000; i++) {
        String id = picker.pick(instances)
                .orElseThrow()
                .getInstanceId();

        counts.merge(id, 1, Integer::sum);
    }

    assertEquals(4_000, counts.get("A"));
    assertEquals(4_000, counts.get("B"));
    assertEquals(4_000, counts.get("C"));
}
~~~

Đây là **bài test đúng cho bộ chọn trên input ổn định**, không phải cam kết số HTTP responses thành công từ ba backend đều bằng nhau: retry, timeout, connection reuse và việc các instance có tải khác nhau có thể làm số response/latency khác dù số lần chọn đồng đều.

Với `K` không chia hết cho `N`, kiểm tra `max(counts)-min(counts)≤1` thay vì yêu cầu các counts phải bằng nhau tuyệt đối. Khi kiểm tra test của implementation Spring sẵn có, nên cho phép seed ban đầu không biết trước.

## 7. Concurrency test: safety trước fairness

Trong production, nhiều thread hoặc reactive subscriptions có thể gọi bộ chọn đồng thời. Một implementation như sau **không an toàn**:

~~~java
// Anti-pattern: increment không atomic.
private long position = 0;

int next = (int) (position++ % candidates.size());
~~~

Hai thread có thể cùng đọc một ticket, làm mất lượt, gây phân phối lệch. Đổi thành `AtomicLong` hoặc cơ chế concurrency control khác là giải pháp cho race về counter, nhưng vẫn cần kiểm thử danh sách ứng viên, callback và state per-request.

Test với 16 workers:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.LongAdder;
import org.junit.jupiter.api.Test;

@Test
void concurrentCallsKeepPerInstanceCountsBalanced()
        throws Exception {

    RoundRobinPicker picker = new RoundRobinPicker();
    var instances = Fixtures.threeInstances();

    int workers = 16;
    int loopsPerWorker = 600; // 9600 calls, chia hết cho 3.
    ConcurrentHashMap<String, LongAdder> counts =
            new ConcurrentHashMap<>();

    ExecutorService executor =
            Executors.newFixedThreadPool(workers);

    try {
        List<Future<?>> futures = new ArrayList<>();

        for (int worker = 0; worker < workers; worker++) {
            futures.add(executor.submit(() -> {
                for (int i = 0; i < loopsPerWorker; i++) {
                    String id = picker.pick(instances)
                            .orElseThrow()
                            .getInstanceId();

                    counts.computeIfAbsent(
                            id, key -> new LongAdder()
                    ).increment();
                }
            }));
        }

        for (Future<?> future : futures) {
            future.get(10, TimeUnit.SECONDS);
        }
    } finally {
        executor.shutdownNow();
    }

    assertEquals(3_200L, counts.get("A").sum());
    assertEquals(3_200L, counts.get("B").sum());
    assertEquals(3_200L, counts.get("C").sum());
}
~~~

Đây là test correctness/concurrency, **không phải benchmark throughput**. Timeout ở `future.get(...)` chỉ giúp test không treo vô hạn; đừng coi 10 giây là latency SLO của thuật toán. Đối với race khó tái hiện, chạy nhiều lịch trình xen kẽ có chủ đích hoặc dùng concurrency stress harness phù hợp ở pipeline riêng.

Một rủi ro khác là **gọi `choose` hai lần cho cùng request**, không phải race trong picker. Khi retry ở nhiều tầng, số lần chọn và số request backend nhận có thể khác nhau; trước khi kết luận “mất ticket”, cần xác định đơn vị quan sát là selection hay HTTP attempt.

## 8. Property-based testing và kiểm thử đầu vào bất thường

Unit tests với 3 instances là bước đầu. Thuật toán custom cần kiểm thử nhiều kích thước list, tập metadata và thứ tự ứng viên khác nhau.

Các property hữu ích:

- **Safety**: `selected == empty` khi `candidates.isEmpty()`; nếu khác rỗng, `selected ∈ candidates`.
- **Identity**: `selected.getServiceId()` phải bằng service ID mà supplier bảo đảm; nếu thuật toán nhận trực tiếp danh sách không lọc, cần validation hoặc contract với supplier.
- **Không sửa input**: chọn đích không đổi thứ tự/size/metadata của candidate list được chia sẻ.
- **Không nhân bản chọn đích**: một lời gọi chooser chỉ xuất một `Response<ServiceInstance>`.
- **Determinism với seed**: một thuật toán Random có RNG được inject và seed cố định cho cùng input phải tạo chuỗi có thể tái lập trong unit test.
- **Constrained eligibility**: nếu request chỉ cho phép zone A, không trả zone B trừ khi chính sách fallback được mô tả.
- **Bounded complexity**: không lặp vô hạn khi tổng trọng số bằng 0 hoặc metadata sai.
- **Không để overflow**: counter, tổng weight và index vẫn hợp lệ sau lượng thao tác rất lớn/giá trị cận biên.

Ví dụ pseudo-code của property test:

~~~text
repeat for lists with size from 0 to 1_000:
    snapshot = immutableCopy(generatedInstances)
    response = picker.pick(snapshot)

    if snapshot is empty:
        assert response is empty
    else:
        assert response is present
        assert snapshot contains response.instance

    assert snapshot remains unchanged
~~~

Có thể dùng jqwik hoặc QuickTheories cho generated inputs; không cần bắt buộc cài framework property testing chỉ để chạy ví dụ cơ bản. Nếu generator được dùng ở CI, lưu seed và thông tin input khi test fail để tái lập lỗi.


## 9. Nối bộ chọn thuần vào ReactorServiceInstanceLoadBalancer

Để ứng dụng Spring Cloud dùng bộ chọn vừa test, cần một adapter thực hiện `ReactorServiceInstanceLoadBalancer.choose(Request)`. Adapter chịu trách nhiệm gọi **`ServiceInstanceListSupplier.get(request)`** thay vì tự đọc danh sách IP từ YAML, chuyển kết quả thành `DefaultResponse` hoặc `EmptyResponse` và thông báo callback nếu supplier yêu cầu.

~~~java
package com.example.loadbalancer;

import java.util.List;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.DefaultResponse;
import org.springframework.cloud.client.loadbalancer.EmptyResponse;
import org.springframework.cloud.client.loadbalancer.Request;
import org.springframework.cloud.client.loadbalancer.Response;
import org.springframework.cloud.loadbalancer.core.ReactorServiceInstanceLoadBalancer;
import org.springframework.cloud.loadbalancer.core.SelectedInstanceCallback;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import reactor.core.publisher.Mono;

public final class TestedRoundRobinLoadBalancer
        implements ReactorServiceInstanceLoadBalancer {

    private final ObjectProvider<ServiceInstanceListSupplier> provider;
    private final RoundRobinPicker picker = new RoundRobinPicker();

    public TestedRoundRobinLoadBalancer(
            ObjectProvider<ServiceInstanceListSupplier> provider) {
        this.provider = provider;
    }

    @Override
    public Mono<Response<ServiceInstance>> choose(Request request) {
        return Mono.defer(() -> {
            ServiceInstanceListSupplier supplier =
                    provider.getIfAvailable();

            if (supplier == null) {
                return Mono.just(new EmptyResponse());
            }

            return supplier.get(request)
                    .next()
                    .map(candidates -> chooseFrom(supplier, candidates))
                    .defaultIfEmpty(new EmptyResponse());
        });
    }

    private Response<ServiceInstance> chooseFrom(
            ServiceInstanceListSupplier supplier,
            List<ServiceInstance> candidates) {

        var selected = picker.pick(candidates);

        if (selected.isEmpty()) {
            return new EmptyResponse();
        }

        ServiceInstance instance = selected.orElseThrow();

        if (supplier instanceof SelectedInstanceCallback callback) {
            callback.selectedServiceInstance(instance);
        }

        return new DefaultResponse(instance);
    }
}
~~~

**Những điểm phải test trong adapter:**

- `Mono.defer(...)` để thực thi lấy supplier lúc subscribe, không “chụp” kết quả ở lúc dựng publisher.
- `get(request)` để giữ `Request` context cho hint/zone/retry-aware supplier; chỉ gọi `get()` có thể bỏ qua thông tin request mà policy cần.
- `.next()` lấy một snapshot từ `Flux<List<ServiceInstance>>`. Nếu Flux không phát giá trị, trả `EmptyResponse` thay vì Mono trống không rõ nghĩa.
- List rỗng cũng trả `EmptyResponse`; không báo callback đã chọn instance.
- Nếu `supplier` triển khai `SelectedInstanceCallback`, callback chỉ chạy khi chọn thành công.
- Supplier error được propagate; không tự biến một lỗi registry nghiêm trọng thành response có server giả.
- Thuật toán `RoundRobinPicker` dùng một counter trong **một instance adapter**. Spring Cloud tạo LoadBalancer child contexts theo service ID; không được dùng một static counter để vô tình chia cursor giữa các service ID nếu không có lý do.

Đây là adapter minh họa cho tính đúng của bộ chọn Round Robin. Trong production cần cân nhắc semantics của các phiên bản Spring Cloud đang dùng, health/discovery fallback, callback và thread safety của source supplier. Không tự viết bộ chọn khi implementation có sẵn của Spring đáp ứng yêu cầu.

## 10. Đăng ký thuật toán chỉ cho một service ID

Sử dụng `@LoadBalancerClient`:

~~~java
package com.example.order;

import com.example.loadbalancer.InventoryLbConfiguration;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLbConfiguration.class
)
public class LoadBalancerRoutingConfiguration {
}
~~~

Cấu hình cho LoadBalancer child context:

~~~java
package com.example.loadbalancer;

import org.springframework.beans.factory.annotation.Bean;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.cloud.loadbalancer.core.ReactorLoadBalancer;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.cloud.loadbalancer.support.LoadBalancerClientFactory;
import org.springframework.core.env.Environment;

public class InventoryLbConfiguration {

    @Bean
    ReactorLoadBalancer<ServiceInstance> testedLoadBalancer(
            Environment environment,
            LoadBalancerClientFactory clientFactory) {

        String serviceId =
                environment.getProperty(
                        LoadBalancerClientFactory.PROPERTY_NAME
                );

        return new TestedRoundRobinLoadBalancer(
                clientFactory.getLazyProvider(
                        serviceId,
                        ServiceInstanceListSupplier.class
                )
        );
    }
}
~~~

Đặt `InventoryLbConfiguration` **ngoài phạm vi component scan** của application, hoặc không gắn annotation khiến nó được quét thành cấu hình global. Đây là điểm quan trọng trong Spring Cloud: cấu hình của `@LoadBalancerClient` cần được áp dụng cho đúng service ID. Các bean `ReactorLoadBalancer<ServiceInstance>` vô tình xuất hiện ở parent context có thể ảnh hưởng các service khác.

Trong ví dụ này, dùng một bean cùng `@LoadBalancerClient` chỉ dành cho `inventory-service`. Service `payment-service` vẫn có thể dùng Round Robin mặc định hoặc cấu hình riêng.

### Không gọi thử bằng URI vật lý khi muốn test LoadBalancer

~~~java
// URI logic: LoadBalancer có thể chọn ServiceInstance.
inventoryRestClient.get()
        .uri("http://inventory-service/api/items/123");

// URI vật lý: không còn kiểm tra service-id based selection.
ordinaryRestClient.get()
        .uri("http://localhost:8081/api/items/123");
~~~

Với WebClient, test đúng builder `@LoadBalanced` hoặc filter `ReactorLoadBalancerExchangeFilterFunction`. Với OpenFeign, `@FeignClient(name="inventory-service")` không có `url` tĩnh và integration phù hợp phải được cấu hình. Nếu Feign được cấp URL cố định, request có thể bỏ qua client-side LoadBalancer; test thuật toán sẽ không có ý nghĩa.

## 11. Test Reactive adapter: supplier, EmptyResponse và callback

Sau khi thuật toán thuần đã đúng, cần kiểm tra **đường tích hợp** với `ServiceInstanceListSupplier`. Spring Cloud có utility `ServiceInstanceListSuppliers.toProvider(...)` để tạo provider từ danh sách instance tĩnh trong test, giúp không phải khởi động service registry.

Ví dụ test bằng Reactor Test:

~~~java
package com.example.loadbalancer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.loadbalancer.DefaultRequest;
import org.springframework.cloud.loadbalancer.support.ServiceInstanceListSuppliers;
import reactor.test.StepVerifier;

class TestedRoundRobinLoadBalancerTest {

    @Test
    void choosesOnlyInstancesFromSupplier() {
        ServiceInstance a = new DefaultServiceInstance(
                "A", "inventory-service", "127.0.0.1", 8081, false);
        ServiceInstance b = new DefaultServiceInstance(
                "B", "inventory-service", "127.0.0.1", 8082, false);

        var provider = ServiceInstanceListSuppliers.toProvider(
                "inventory-service", a, b
        );
        var loadBalancer =
                new TestedRoundRobinLoadBalancer(provider);

        StepVerifier
                .create(loadBalancer.choose(new DefaultRequest<>()))
                .assertNext(response -> {
                    assertTrue(response.hasServer());
                    assertEquals("A",
                            response.getServer().getInstanceId());
                })
                .verifyComplete();
    }

    @Test
    void emptySupplierProducesNoServer() {
        var provider = ServiceInstanceListSuppliers.toProvider(
                "inventory-service"
        );
        var loadBalancer =
                new TestedRoundRobinLoadBalancer(provider);

        StepVerifier
                .create(loadBalancer.choose(new DefaultRequest<>()))
                .assertNext(response ->
                        assertFalse(response.hasServer()))
                .verifyComplete();
    }
}
~~~

`DefaultRequest` và `StepVerifier` nằm trong các test dependencies tương ứng. Dùng Spring Boot test hoặc `reactor-test` phù hợp với release train của module. Nếu test implementation có seed ngẫu nhiên, đừng assert A là instance đầu tiên; ví dụ trên assert A vì `RoundRobinPicker` minh họa khởi tạo ticket bằng 0.

Bổ sung các test riêng cho adapter:

1. Supplier phát danh sách mới ở subscription thứ hai: adapter phải đọc danh sách mới.
2. Supplier phát một danh sách rỗng: kết quả `hasServer() == false`.
3. Supplier trả `Flux.empty()`: cũng phải không có instance.
4. Supplier phát exception: behavior phải được định nghĩa và không có response thành công giả.
5. Supplier nhận `Request` có hint/zone: test rằng adapter gọi `get(request)` và không bỏ context.
6. Supplier triển khai `SelectedInstanceCallback`: callback được gọi đúng một lần cho selection thành công, không gọi khi rỗng.
7. Hai service IDs với hai child contexts: test thuật toán được áp dụng đúng scope.
8. Nếu contract custom yêu cầu idle instance có metadata riêng, test callback/state per-instance không bị rò qua các service khác.

Không cần viết integration test đầy đủ vào unit test này. Tầng adapter chỉ kiểm tra contract giữa bộ chọn, reactive supplier và response wrapper.

## 12. Fairness: định nghĩa theo **lượt chọn** trước khi đo HTTP

Giả sử ba replica A/B/C có cùng trọng số và luôn đủ điều kiện:

- **Round Robin**: sau K lượt chọn với danh sách cố định, counts giữa các replica lệch tối đa một.
- **Uniform Random**: mỗi lượt có xác suất `p_i = 1/3`; không bảo đảm đúng 1/3 trong cửa sổ ngắn.
- **Weighted Random**: nếu weights 3:1:1, xác suất mục tiêu lần lượt là 60%, 20%, 20%.
- **Sticky/affinity**: cùng session/user có thể được ghim vào một replica; sự công bằng theo từng session **không giống** công bằng theo request.
- **Least-active/concurrency-aware**: ưu tiên instance ít request đang xử lý; counts có thể lệch để bảo vệ latency.
- **Zone preference**: nếu request ở zone A, count toàn cục không cân bằng giữa các zone là kết quả có chủ đích.

Đầu tiên phải chọn **đơn vị đo**:

| Đơn vị | Câu hỏi | Vì sao có thể khác? |
|---|---|---|
| LoadBalancer selections | Bộ chọn đã chọn A/B/C bao nhiêu lần? | Gần nhất với fairness của thuật toán |
| HTTP attempts | HTTP transport thực sự gửi bao nhiêu lần? | Retry có thể tạo nhiều attempt; connect fail |
| Completed HTTP responses | Có bao nhiêu response thành công/lỗi? | Replica chậm có nhiều request còn in-flight |
| Requests/sec thành công | Replica xử lý bao nhiêu throughput? | Sức chứa/CPU/DB/backend queue khác nhau |
| In-flight requests | Bao nhiêu lời gọi đang chạy trên instance? | Thời gian phục vụ khác nhau |
| Bytes/CPU time | Backend chịu bao nhiêu tài nguyên? | Payload/cost mỗi request khác nhau |

**Công bằng về số lượt chọn không có nghĩa công bằng về CPU hoặc latency.** Nếu mỗi request tới A mất 5 ms còn B mất 500 ms, Round Robin vẫn có thể chia đều lượt chọn, nhưng B tích lũy in-flight và có p99 cao.

## 13. Độ công bằng xác suất của Random

Với N lượt chọn độc lập và cố định danh sách n instance, uniform random có:

\[
p_i=\frac{1}{n},\qquad E[C_i]=Np_i
\]

và nếu mỗi lượt độc lập:

\[
\mathrm{Var}(C_i)=Np_i(1-p_i),\quad
\sigma_i=\sqrt{Np_i(1-p_i)}.
\]

Ví dụ 3 instance, 9.000 lượt chọn:

\[
E[C_i]=3000,\quad
\sigma_i=\sqrt{9000\times\frac13\times\frac23}
\approx44.72.
\]

Do đó, counts kiểu `A=2954, B=3022, C=3024` là hoàn toàn có thể xảy ra. Không được viết test “mỗi instance chính xác 3.000 lần” cho Random, và cũng không được kết luận thuật toán sai chỉ vì hai request liên tiếp cùng vào A.

### Kiểm thử random không flaky

Dùng hai tầng:

**Tầng deterministic:** Inject RNG có seed cố định, xác nhận với cùng seed và danh sách cùng thứ tự thì chuỗi được tái lập, mọi index nằm trong `[0,n)`. Test này phát hiện bug logic và giúp debug.

**Tầng statistical:** Chạy sample đủ lớn, đếm các lựa chọn và so với kỳ vọng bằng một mức lệch cho phép được tính trước. Đừng dùng ngưỡng ngẫu nhiên hoặc lấy sample 20 requests rồi đánh giá phân phối.

Ví dụ một picker có RNG injection:

~~~java
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.IntUnaryOperator;
import org.springframework.cloud.client.ServiceInstance;

public final class RandomPicker {

    private final IntUnaryOperator nextIndex;

    public RandomPicker(IntUnaryOperator nextIndex) {
        this.nextIndex = nextIndex;
    }

    public static RandomPicker production() {
        return new RandomPicker(bound ->
                ThreadLocalRandom.current().nextInt(bound));
    }

    public Optional<ServiceInstance> pick(
            List<ServiceInstance> candidates) {
        if (candidates == null || candidates.isEmpty()) {
            return Optional.empty();
        }

        int index = nextIndex.applyAsInt(candidates.size());

        if (index < 0 || index >= candidates.size()) {
            throw new IllegalStateException("RNG index out of bounds");
        }

        return Optional.of(candidates.get(index));
    }
}
~~~

Trong unit test:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.Random;

@Test
void fixedSeedMakesRandomSelectionReproducible() {
    var instances = Fixtures.threeInstances();

    RandomPicker p1 =
            new RandomPicker(new Random(2026)::nextInt);
    RandomPicker p2 =
            new RandomPicker(new Random(2026)::nextInt);

    for (int i = 0; i < 500; i++) {
        assertEquals(
                p1.pick(instances).orElseThrow().getInstanceId(),
                p2.pick(instances).orElseThrow().getInstanceId()
        );
    }
}
~~~

Với production picker dùng `ThreadLocalRandom`, test phân bố chỉ nên là một **statistical test có xác suất fail giả được kiểm soát** hoặc chạy như nonblocking performance/quality gate, không làm flaky mọi pull request.

### Ngưỡng thống kê thay vì một con số tùy ý

Nếu `\hat p_i = C_i/N` và mỗi lượt chọn là Bernoulli độc lập cho instance i, bất đẳng thức Hoeffding cho:

\[
P(|\hat p_i-p_i|\ge\varepsilon)
\le 2e^{-2N\varepsilon^2}.
\]

Với n instance, union bound đơn giản cho xác suất có bất kỳ tỷ lệ nào vượt ngưỡng:

\[
P(\exists i:|\hat p_i-p_i|\ge\varepsilon)
\le 2n e^{-2N\varepsilon^2}.
\]

Ví dụ N = 10.000, n = 3 và `\varepsilon = 0.03` (lệch 3 điểm phần trăm), ngưỡng trên rất nhỏ theo giả thiết **independent, identical distribution và p_i cố định**. Đây là cách thiết kế threshold có cơ sở cho **uniform random trong snapshot ổn định**, không áp dụng trực tiếp cho sticky sessions, adaptive least-request hay danh sách biến động.

Một test random fail có thể là bug RNG, input lệch, policy lọc trước chọn hoặc lỗi trong phương pháp đo. Không tự sửa thuật toán chỉ vì một sample ngắn bất thường.

## 14. Fairness có trọng số: mục tiêu khác equal split

Giả sử trọng số mục tiêu:

| Instance | Weight | Target share |
|---|---:|---:|
| A | 3 | 60% |
| B | 1 | 20% |
| C | 1 | 20% |

Xác suất lý tưởng:

\[
p_i=\frac{w_i}{\sum_j w_j},\qquad E_i=Np_i.
\]

Nếu N=10.000, kỳ vọng A=6.000, B=2.000, C=2.000. Một bài test yêu cầu counts bằng 3.333 cho mỗi backend ở đây là **sai hợp đồng**.

Spring Cloud cung cấp `WeightedServiceInstanceListSupplier` và `WeightFunction` để xác định trọng số instance; mặc định có thể đọc metadata key `weight` theo tài liệu. Khi thử thuật toán custom, cần xác định **trọng số được diễn giải ở supplier hay tại chính chooser** để tránh “double weighting”.

Hai chiến lược có thể gặp:

- **Weighted sampling bằng bảng cumulative**: xây tổng weight rồi rút số trong `[0,total)`; nếu quét tuyến tính mỗi lần chọn thì chi phí `O(n)`; binary search prefix sums cho `O(log n)` nếu dữ liệu được chuẩn bị trước.
- **Weighted supplier**: biến đổi tập ứng viên/tỷ trọng ở tầng supplier. Bộ chọn Round Robin/Random phía sau thấy tập đầu ra; không suy đoán tỷ lệ chỉ từ metadata gốc.

### Test cho weights không hợp lệ

| Input | Kiểm tra |
|---|---|
| Tất cả weight >0 | Phân bố mục tiêu và membership |
| Một weight =0 | Được loại hay fallback? Contract phải định nghĩa |
| Weight âm | Reject hoặc xử lý theo quy tắc an toàn |
| Weight quá lớn | Tổng không overflow; không tạo danh sách bản sao khổng lồ |
| Metadata thiếu | Default weight theo policy, ví dụ 1 nếu dùng supplier mặc định tương ứng |
| Metadata parse fail | Fallback hoặc fail fast có log an toàn |
| Weights đổi trong runtime | Cập nhật snapshot/alias table nhất quán |
| Một instance biến mất | Điều chỉnh tổng weight và tập ứng viên ngay khi snapshot mới tới |

Nếu cache một alias table hoặc prefix sums để tiết kiệm `O(n)` cho mỗi lượt chọn, nhớ **invalidate** khi tập instance hoặc weight thay đổi. Benchmark chỉ chạy với list cố định có thể không phát hiện chi phí rebuild table.

## 15. Đo fairness khi discovery, zone, health thay đổi

Một lỗi đánh giá rất phổ biến: lấy tổng số lần chọn A/B/C trong một giờ, rồi trách thuật toán “chọn B quá ít” dù B chỉ đủ điều kiện trong 10 phút.

Với uniform random và tập ứng viên `C_t` tại lượt chọn t, xác suất hợp lệ thay đổi theo thời gian:

\[
p_i(t)=
\begin{cases}
1/|C_t| & i\in C_t\\
0 & i\notin C_t
\end{cases}
\]

Kỳ vọng số lượt chọn i:

\[
E_i=\sum_{t=1}^{N}p_i(t).
\]

Với weighted random, thay `1/|C_t|` bằng trọng số i chia tổng trọng số của các ứng viên **đủ điều kiện tại t**. Không chia đều lượt chọn của cả giờ khi danh sách instance thay đổi.

Cần ghi lại:

- `serviceId`, `instanceId`, phiên bản snapshot và timestamp;
- Candidate set **sau** zone/hint/health filtering;
- Request context làm thay đổi eligibility, nhưng tránh log tenant/user ID nhạy cảm;
- Weight/affinity rules có hiệu lực;
- Retry attempt, no-instance và fallback path;
- Tên thuật toán/load-balancer policy đang chạy.

**Nếu policy là sticky preference**, fairness theo request toàn cục không phải mục tiêu duy nhất. Một tenant có 80% traffic có thể làm instance của tenant đó nhận 80% lượt chọn theo cách hợp lệ. Khi đó nên đánh giá độ phân bố **theo key/session** hoặc số khóa được gán cho mỗi replica, đồng thời đo hotspot theo lưu lượng thực tế.

## 16. Chỉ số fairness bổ trợ và giới hạn

Có thể dùng các thước đo sau, nhưng phải nêu mục tiêu phân phối trước:

**Độ lệch tỷ phần tuyệt đối:**

\[
\Delta_i=|\hat p_i-p_i|.
\]

Dễ giải thích: nếu mục tiêu 20% và quan sát 24%, lệch **4 điểm phần trăm**.

**Sai số tương đối:**

\[
R_i=\frac{|\hat p_i-p_i|}{p_i},\quad p_i>0.
\]

Phù hợp khi muốn so mức lệch của replica có weight nhỏ với replica lớn; đừng dùng khi target probability bằng 0.

**Chỉ số Jain cho nhóm instance tương đương:**

\[
J=\frac{(\sum_i c_i)^2}{n\sum_i c_i^2},\quad
\frac1n\le J\le1.
\]

`J=1` nếu các counts bằng nhau. Nhưng một giá trị Jain cao **không chứng minh** mọi request đã đến đúng instance, và Jain trên raw counts **không đúng mục tiêu** cho Weighted 3:1:1.

Để đánh giá target weights, có thể dùng tỷ số chuẩn hóa `r_i=C_i/E_i` với `E_i>0`, sau đó tính Jain trên `r_i`. Chỉ số này gần 1 khi tỷ lệ thực tương đối sát kỳ vọng; tuy nhiên cần số mẫu đủ lớn và theo dõi riêng instance có expected count rất nhỏ.

**Chi-square goodness-of-fit**:

\[
\chi^2=\sum_{i=1}^{n}\frac{(O_i-E_i)^2}{E_i}.
\]

Chỉ phù hợp khi giả định phân bố xác suất và tính độc lập hợp lý; expected counts cần đủ lớn theo tiêu chuẩn kiểm định sử dụng. Không dùng chi-square trực tiếp để “chứng minh” đúng/sai Round Robin hoàn toàn xác định hay adaptive load balancing phụ thuộc trạng thái.

**Kết luận về fairness:** luôn bắt đầu bằng **hợp đồng thuật toán + đơn vị đo + cửa sổ quan sát + tập ứng viên hợp lệ**. Một con số fairness đơn lẻ không thay thế bốn thông tin đó.


## 17. Chi phí thuật toán: mô hình độ phức tạp

Chi phí phải được đo theo **số ứng viên n**, **số requests Q**, cách truy cập metadata và mức concurrency. Không phải mọi thuật toán “chọn một phần tử” đều `O(1)`.

| Chiến lược / thao tác | Chi phí một lượt chọn (mô hình) | State/phần chuẩn bị | Rủi ro vận hành |
|---|---|---|---|
| Round Robin trên danh sách có sẵn | `O(1)` | `O(1)` counter | Atomic contention khi concurrency rất cao |
| Uniform Random trên danh sách có sẵn | `O(1)` | `O(1)` | Không đảm bảo fairness ở cửa sổ ngắn |
| Weighted Random quét cumulative weights mỗi lần | `O(n)` | `O(1)` nếu không lưu bảng | CPU tăng theo số candidates |
| Weighted Random + prefix sum + binary search | `O(log n)` | `O(n)` bộ nhớ, `O(n)` rebuild | Phải rebuild khi instance/weight đổi |
| Weighted Random + alias method | `O(1)` | `O(n)` setup/memory | Tốn chi phí rebuild, dữ liệu động khó cache |
| Least-active quét số request đang chạy | `O(n)` | `O(n)` counters | Race/telemetry stale; scan tốn CPU |
| Power of two choices | Khoảng `O(1)` nếu lookup/so sánh số ít candidates | `O(n)` hoặc tùy telemetry | Chỉ gần đúng least-active, state updates |
| Consistent hashing (sorted ring) | `O(log(vn))` lookup | `O(vn)` ring với v virtual nodes mỗi instance; build/sort tốn công | Hash skew, memory, rebalancing |
| Lọc zone/hint/health từ list | Thường `O(n)` | Phụ thuộc supplier/cache | Dễ bị tính nhầm vào cost chooser |
| Copy hoặc sort danh sách trước mỗi chọn | `O(n)` hoặc `O(n log n)` | Allocation mới mỗi request | Làm mất ưu điểm O(1) của chooser |

`O(1)` là **độ phức tạp tiệm cận theo n**, không có nghĩa latency thực bằng 0 và không thay đổi theo số thread. Ngay cả Round Robin dùng `AtomicLong` có thể tạo cache-line contention khi hàng trăm thread dùng cùng một cursor.

### Ví dụ tính cost theo số yêu cầu

Nếu một chooser quét 1.000 candidates cho mỗi lần chọn, với 10.000 calls/giây, nó có thể phải kiểm tra khoảng 10 triệu phần tử/giây, **chưa tính** filtering, alloc và network. Một chooser `O(1)` có thể giảm phần cost này, nhưng nếu mỗi HTTP request tốn 50 ms và danh sách chỉ có ba instance, hiệu quả end-to-end có thể không đáng kể.

Quan trọng hơn, nếu supplier luôn tạo `new ArrayList<>(instances)` hoặc sắp xếp lại danh sách mỗi lần chọn, đo mỗi `picker.pick(...)` sẽ bỏ qua chi phí lớn nhất. Tách rõ:

\[
T_{\text{selection path}} =
T_{\text{supplier}} +
T_{\text{filter}} +
T_{\text{algorithm}} +
T_{\text{reactive/adaptation}}.
\]

Và tổng latency lời gọi HTTP:

\[
T_{\text{end-to-end}} =
T_{\text{queue/pool}} +
T_{\text{selection path}} +
T_{\text{connect/TLS}} +
T_{\text{backend}} +
T_{\text{response}} +
T_{\text{retry/backoff}}.
\]

Các thành phần có thể chồng lấp tùy pipeline/transport; phương trình là **mô hình phân rã** để đo và so sánh, không phải công thức đo tuyệt đối của mọi HTTP request.

## 18. Benchmark riêng thuật toán bằng JMH

Đừng dùng vòng `System.nanoTime()` tự viết quanh mỗi lần chọn và kết luận từ vài microseconds: JIT optimization, dead-code elimination, GC, scheduler và CPU frequency có thể làm số đo sai. **JMH** phù hợp hơn để microbenchmark Java.

Ví dụ skeleton dùng JMH và bộ chọn ở mục 4:

~~~java
package com.example.loadbalancer.benchmark;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Threads;
import org.openjdk.jmh.annotations.Warmup;
import org.openjdk.jmh.infra.Blackhole;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.ServiceInstance;
import com.example.loadbalancer.RoundRobinPicker;

@State(Scope.Benchmark)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 10)
@Fork(2)
@Threads(8)
public class RoundRobinPickerBenchmark {

    @Param({"1", "10", "100", "1000"})
    public int instanceCount;

    private List<ServiceInstance> instances;
    private RoundRobinPicker picker;

    @Setup(Level.Trial)
    public void setup() {
        var list = new ArrayList<ServiceInstance>();

        for (int i = 0; i < instanceCount; i++) {
            list.add(new DefaultServiceInstance(
                    "inst-" + i,
                    "inventory-service",
                    "127.0.0.1",
                    10000 + i,
                    false
            ));
        }

        instances = List.copyOf(list);
        picker = new RoundRobinPicker();
    }

    @Benchmark
    public void pick(Blackhole blackhole) {
        blackhole.consume(
                picker.pick(instances).orElseThrow()
        );
    }
}
~~~

Muốn chạy benchmark này cần thêm JMH core và annotation processor tương ứng, một profile/build target riêng. **Không đưa microbenchmark vào unit-test suite chạy mỗi commit** vì kết quả rất nhạy môi trường và kéo dài pipeline. Code trên là mẫu thiết kế benchmark, không phải số đo đã chạy cho module.

### Thiết kế benchmark không thiên lệch

1. **Warmup** đầy đủ để JIT có cơ hội tối ưu.
2. **Fork** nhiều JVM mới, tránh trạng thái đã “làm nóng” của test trước.
3. **Param n** bằng 1, 10, 100, 1000 (có thể thêm 10.000 nếu hệ thống thực có tập lớn).
4. **Concurrency**: đo một thread và 8/32 threads; một số thuật toán dùng lock/Atomic có kết quả khác.
5. **Snapshot**: benchmark trên immutable list giống input production; đừng tạo list trong vòng đo `pick` nếu muốn cô lập thuật toán.
6. **Consume result** bằng `Blackhole` để tránh optimizer loại bỏ công việc.
7. **Tách phân bổ bộ nhớ**: đo allocations/op, GC rate và objects tạo ra nếu thuật toán dựng bảng tạm.
8. **Kiểm tra biến động**: xem nhiều forks và phân phối kết quả, không chỉ một số trung bình.
9. **Giữ môi trường ổn định**: số core, CPU scaling, JVM/GC, JDK, cgroup quotas, memory và thermal throttling.
10. **Đo tail latency** nếu p99 selection quan trọng; average time không tự thay thế p99.

Có thể bổ sung benchmark `Mode.Throughput` và `Mode.SampleTime` theo mục tiêu, sử dụng JMH fixtures riêng. Với weighted selection, báo cáo rõ phần chuẩn bị bảng có nằm trong benchmark hay không; nếu topology thay đổi thường xuyên, cost rebuild có thể lớn hơn cost chọn.

### Tránh benchmark sai do khởi tạo trước

Một benchmark chỉ đo `pick(candidates)` có thể cho ra `O(1)` rất tốt, nhưng WebClient thật còn đi qua Reactor, `ServiceInstanceListSupplier`, health filtering và connector. Do đó cần một benchmark thứ hai đo **supplier → reactive choose → response**, và một test end-to-end đo HTTP. Không dùng kết quả microbenchmark để tuyên bố tổng thời gian API giảm tương ứng.

## 19. Benchmark các trường hợp làm thay đổi chi phí

Đừng chỉ thử `n=3`, weights đều và không có concurrent requests. Một bộ thí nghiệm có kiểm soát:

| Biến kiểm soát | Giá trị gợi ý | Điều cần quan sát |
|---|---|---|
| Số instances | 1, 10, 100, 1000 | Độ phức tạp theo n |
| Threads/subscriptions | 1, 8, 32 | Atomic contention và thread-safety |
| Tần suất đổi topology | Không đổi; đổi mỗi 1s; đổi mỗi 100ms | Chi phí rebuild/cache invalidation |
| Số weights khác nhau | Đều; lệch 10:1; zero/invalid | Weighted picker handling |
| Lọc zone/hint | Không lọc; lọc còn 1/10 instances | Cost filter và fairness trên candidate set |
| Cache | Cache hit/miss có đo riêng | Discovery/selection overhead |
| Retry | Tắt; một retry có budget | Số `choose` thực tế |
| Backend latency | 1ms, 50ms, 500ms | Selection overhead so với network/backend |
| Response payload | Nhỏ và lớn | Codec/network chi phí có thể che cost picker |
| Số service IDs | 1 và nhiều client contexts | Memory và init overhead của child contexts |

Khi so benchmark, giữ số backend, rate, concurrency và retry giống nhau. Nếu một thuật toán có fallback/affinity khác baseline, nó có thể thay đổi request mix và backend latency; lúc đó so p99 HTTP không còn cô lập chi phí selection.

### Tách cold path và warm path

Spring Cloud LoadBalancer tạo child context cho từng service ID **lazily** theo mặc định. Lời gọi đầu có thể bao gồm khởi tạo context, lấy discovery lần đầu hoặc làm nóng connection pool. Không so nó với lượt gọi thứ một triệu của thuật toán khác.

Nên đo riêng:

- **Cold start / first selection**: thời gian từ request đầu tiên tới lúc có lựa chọn, có thể gồm child context init.
- **Warm steady-state**: sử dụng supplier/cache đã ổn định.
- **Topology update**: thay instances/weights/metadata rồi đo độ trễ và chi phí cập nhật.
- **Recovery**: replica được thêm lại sau health check, cần xem khoảng trễ từ update đến khi được chọn.

Nếu ứng dụng cấu hình eager-load contexts, so sánh phải phản ánh việc chuyển chi phí khởi tạo sang startup thay vì “biến mất” khỏi hệ thống.

## 20. Integration test: hai/ba backend và service ID thật

Để xác minh thuật toán qua HTTP client, dựng một lab:

~~~text
caller :8080
  |
  | GET http://inventory-service/whoami
  v
Spring Cloud LoadBalancer + custom algorithm
  |
  +--- inventory A :8081
  +--- inventory B :8082
  +--- inventory C :8083
~~~

`application.yml` trong caller với `SimpleDiscoveryClient`:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
              - uri: http://localhost:8083
~~~

Trong inventory-service, cho mỗi replica trả cổng đang lắng nghe:

~~~java
package com.example.inventory;

import java.util.Map;
import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class InstanceController {

    private final Environment environment;

    public InstanceController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/whoami")
    public Map<String, String> whoami() {
        return Map.of(
                "instance",
                environment.getProperty("server.port", "unknown")
        );
    }
}
~~~

Chạy cùng service trên các cổng 8081–8083 và kiểm tra từng backend trực tiếp trước khi test routing. Caller cung cấp endpoint `GET /proxy/whoami` qua `@LoadBalanced RestClient.Builder` hoặc `@LoadBalanced WebClient.Builder`, hay một `@FeignClient(name="inventory-service")`. Endpoint proxy cần triển khai riêng trong lab.

PowerShell minh họa:

~~~powershell
1..60 | ForEach-Object {
    Invoke-RestMethod "http://localhost:8080/proxy/whoami"
}
~~~

Với custom Round Robin và tập instance **ổn định**, 60 selections có thể chia đều 20/20/20. Nhưng nếu HTTP timeout/retry, proxy lỗi hoặc các request khác dùng chung `inventory-service`, **60 responses thành công không nhất thiết tương ứng đúng 60 selections**. Để kiểm chứng thuật toán, đo tại lifecycle selection và đối chiếu backend access logs.

### Test đúng phạm vi áp dụng

Thêm client `payment-service` dùng chính sách mặc định. Gọi nó và xác nhận custom algorithm của inventory **không** được áp dụng nhầm. Điều này phát hiện lỗi đặt `@LoadBalancerClient` configuration trong component scan khiến bean custom bị đăng ký global.

### Test cả ba loại HTTP client

| Client | Cấu hình chọn service ID | Kiểm chứng |
|---|---|---|
| RestClient | `@LoadBalanced RestClient.Builder` | URI host là `inventory-service`; request tới một replica |
| WebClient | `@LoadBalanced WebClient.Builder` hoặc Reactor LoadBalancer filter | Có subscribe Mono; selection theo service ID |
| OpenFeign | `@FeignClient(name="inventory-service")` không có URL tĩnh | Được Spring Cloud LoadBalancer tích hợp; method gọi đúng replica |

Với WebClient, **không gọi `block()` trên event-loop thread** để test trong ứng dụng reactive. Dùng `StepVerifier`/`WebTestClient` hoặc subscription tự nhiên do framework quản lý.

## 21. Kiểm thử lỗi, health, zone, retry và circuit breaker

Fairness của bộ chọn không được đo tách khỏi chính sách ứng viên. Một kịch bản test lỗi cần phân biệt ít nhất:

### 21.1. Một replica chết

~~~text
A :8081  healthy
B :8082  stopped
C :8083  healthy
~~~

Nếu supplier vẫn chứa B (ví dụ SimpleDiscoveryClient tĩnh), custom selector **có thể chọn B một cách hợp lệ theo input đã cho**, dẫn đến connect error. Điều đó chưa chứng minh chooser chọn sai. Hãy test hai trường hợp:

1. **Không health filtering:** B vẫn nằm trong candidates, connect failure và retry có giới hạn; đếm selection/attempt.
2. **Có health filtering:** sau khi health supplier đánh dấu B unhealthy, candidates không chứa B; bộ chọn không được chọn B nữa.

Với `HealthCheckServiceInstanceListSupplier`, có thể có cơ chế cập nhật/cache riêng; cần test khoảng thời gian chuyển trạng thái chứ không yêu cầu backend được loại ngay tức khắc.

### 21.2. Zone/hint/affinity

Nếu policy chỉ cho phép zone HCM, tạo candidates có metadata zone HCM/Hanoi. Gửi request có request context/hint phù hợp rồi test **supplier output** trước và **selection output** sau.

Lưu ý một số zone-preference/hint suppliers có thể **fallback về full list** khi không còn ứng viên thỏa filter; vì thế test phải bám **contract thật của supplier đang cấu hình**, không tự suy rằng mọi hint đều hard-filter.

Đối với sticky session, test hai tính chất:

- Cùng affinity key và tập ứng viên ổn định: selection tuân theo policy sticky.
- Instance sticky biến mất hoặc bị loại: policy xác định fallback/rebalance, không chọn instance không còn trong candidates.

### 21.3. Retry và chuyển instance

Nếu retry-aware supplier được bật, request retry có thể nhận danh sách **ưu tiên tránh instance trước đó**. Đừng bắt mọi retry phải đổi replica trong mọi tình huống: khi chỉ còn một instance hợp lệ hoặc policy cho phép lựa chọn lại, cùng replica có thể được chọn lại.

Test thêm:

- Retry không vượt giới hạn khi network failure/503.
- POST/PUT có side effect chỉ được retry khi bảo đảm idempotency.
- Timeout tổng bao trùm các attempts/backoff.
- Metrics phân biệt logical request, selection và HTTP attempts.
- Nếu circuit breaker OPEN, request có thể bị chặn **trước khi** LoadBalancer chọn instance; fairness counts ở thời điểm đó không tăng theo số client calls.

### 21.4. Tập ứng viên rỗng

Nếu không có ServiceInstance, adapter phải trả `EmptyResponse`/`hasServer=false` và HTTP client thể hiện lỗi phù hợp (thường 503 trong một số integration). Không tự tạo một instance giả hoặc trả null rồi tiếp tục gọi network.


## 22. Observability: thu thập đúng dữ liệu trước khi kết luận

Trong production, không thể đặt breakpoint cho mỗi `choose()`. Cần quan sát theo **service ID, policy, instance và kết quả**, với nhãn đủ hữu ích nhưng không làm metric cardinality bùng nổ.

Spring Cloud LoadBalancer có `LoadBalancerLifecycle`; khi bật Micrometer statistics support và có `MeterRegistry`, một số meters của LoadBalancer sẽ được đăng ký.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    loadbalancer:
      stats:
        micrometer:
          enabled: true

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics
~~~

Cần có Spring Boot Actuator và một metrics registry phù hợp. Tên meter/tags cụ thể tùy Spring Cloud release train. Ví dụ Spring Cloud có meter `loadbalancer.requests.active` cho các request đang active; những meter/counter khác liên quan success/failure có thể được cung cấp bởi lifecycle instrumentation.

Các sự kiện cần phân biệt:

| Sự kiện | Điều cần biết | Đơn vị |
|---|---|---|
| Candidate snapshot | Những instance nào thực sự đủ điều kiện | Danh sách theo service ID/policy |
| Selection | Chooser đã chọn instance nào | Một lượt `choose` |
| No-instance | Không tìm thấy candidate hợp lệ | Một lần chọn thất bại |
| HTTP attempt | Transport đã thử gửi tới đâu | Một attempt |
| HTTP completion | Status hoặc lỗi transport | Response/exception |
| Retry | Lời gọi logic có bao nhiêu attempts | Một retry |
| Latency | Chi phí supplier, filter, picker và network | Duration |
| In-flight | Backend đang có bao nhiêu request chưa hoàn tất | Gauge |
| Dynamic update | Danh sách/weights đổi khi nào | Event/version |

### Không để metrics làm méo hiệu năng

Một custom picker cực nhanh nhưng tạo tag động cho từng user/session/request có thể khiến `MeterRegistry` giữ hàng triệu series, làm chi phí instrumentation lớn hơn thuật toán. Nên dùng:

- Tên service ID đã kiểm soát.
- Instance ID hoặc zone nếu số lượng hữu hạn và policy observability cho phép.
- Tên thuật toán và operation có số lượng giới hạn.
- Kết quả `selected`, `empty`, `error` và policy version có bounded values.

Tránh raw URI với SKU trong path, bearer token, user ID, tenant ID không giới hạn hoặc correlation ID làm **metric label**. Có thể dùng correlation/trace ID trong **sampled logs/traces** theo chính sách bảo vệ dữ liệu, không phải nhãn histogram.

### Đối chiếu event ở ba lớp

~~~text
Controller:            logical request count
LoadBalancer:          selection count, selected instance
HTTP transport:        attempts, connect failures, timeout
Backend:               received requests, status, latency
~~~

Với retry, controller có thể ghi 1 request nhưng LoadBalancer ghi 2 selections và backend chỉ nhận 1 request (attempt đầu fail trước khi kết nối). Nếu cứ lấy số backend responses chia cho tổng caller requests để đánh giá fairness, kết luận rất dễ sai.

Nếu ứng dụng có nhiều **caller replicas**, mỗi replica có thể giữ state Round Robin riêng. Tổng hợp counts toàn hệ thống có thể lệch trong cửa sổ ngắn do seed và tải khác nhau; điều này không nhất thiết là lỗi race của algorithm.

## 23. Phân biệt latency của chooser với latency của dịch vụ

Để biết custom thuật toán có đáng triển khai, đo theo hai tầng:

### 23.1. Tầng algorithm

Giữ cố định candidate snapshot và đo:

- Nanoseconds hoặc microseconds mỗi `pick`.
- CPU time và ops/second theo một và nhiều threads.
- Allocated bytes/op.
- GC frequency/pressure khi stress test.
- Contention trong `AtomicLong`, lock, cache-line hoặc shared mutable maps.
- Tác động của n và việc metadata/weights thay đổi.

Ví dụ Round Robin có `O(1)` nhưng `AtomicLong` có thể thành điểm tranh chấp dưới concurrency cực cao. Một thread-local random picker có thể giảm tranh chấp; đổi lại nó chỉ công bằng theo xác suất.

### 23.2. Tầng end-to-end

Gửi request HTTP thật và đo:

- Throughput thành công (RPS).
- Error rate: 4xx, 5xx, timeout, no-instance, connect failures.
- p50/p95/p99 latency theo **logical request**.
- p95/p99 latency theo **HTTP attempt**.
- Số connections, pool waits, CPU/memory của caller.
- CPU, queue depth và in-flight của từng backend.
- Backend overload/hotspot khi weights hoặc throughput phân phối không đều.

Nếu JMH cho thấy thời gian chọn giảm từ 1 µs xuống 100 ns nhưng p99 API vẫn 180 ms, không nên kết luận thuật toán mới “nhanh gấp 10 lần” cho người dùng. Nó giảm chi phí ở một thành phần nhỏ; hiệu quả toàn hệ thống phải được chứng minh riêng.

### 23.3. Báo cáo benchmark có thể tái lập

| Trường | Nội dung cần ghi |
|---|---|
| JVM/JDK | Vendor, version, heap, GC |
| CPU và môi trường | Số cores, cgroup quota, hệ điều hành |
| Spring Cloud version | Release train/Commons/LoadBalancer |
| Candidate set | Số instances, weights, zone/hint mix |
| Thuật toán | Version, cấu hình, policy fallback |
| Caching | Hit/miss, topology update cadence |
| Load | RPS, concurrency, test duration, warmup |
| Retry/timeout | Có bật không, max attempts |
| Metrics | Overhead instrumentation enabled/disabled |
| Kết quả | Throughput, latency distributions, CPU, allocations, errors |
| Độ tin cậy | Số lần chạy, variance, CI/benchmark host |

Không đưa **số liệu benchmark giả** vào report. Nếu chưa chạy đo, ghi “chưa đo” thay vì nội suy từ Big-O. Benchmark production candidate set có n nhỏ và request rate thấp có thể chứng minh thuật toán phức tạp hơn vẫn đủ tốt; Big-O chỉ là một phần của quyết định thiết kế.

## 24. Thiết lập tiêu chí pass/fail để CI không flaky

Một pipeline thực tế có thể chia kiểm thử thành các nhóm:

| Nhóm | Chạy khi nào? | Gate điển hình |
|---|---|---|
| Unit correctness | Mọi pull request | Không chọn sai instance, không exception vô lý |
| Property-based correctness | Mọi PR hoặc nightly | Không vi phạm membership/invariants; seed có thể tái lập |
| Concurrency stress | Nightly hoặc dedicated CI | Không race, deadlock, lost update |
| Deterministic Round Robin fairness | Mọi PR | `max(count)-min(count)≤1` trên list ổn định |
| Statistical Random fairness | Nightly/dedicated job | Lệch so target trong ngưỡng có cơ sở xác suất |
| Request-aware supplier integration | Mọi PR | Zone/hint/health/retry policies không bị bỏ qua |
| End-to-end multi-replica | Mọi PR hoặc CI tích hợp | Client gọi qua service ID, correct backend response |
| JMH microbenchmark | Khi đổi thuật toán hoặc nightly | Phân tích regression, không dùng threshold cứng trên máy chia sẻ |
| HTTP load/performance | Trước release/performance lab | SLO p95/p99 và error budget được đáp ứng |
| Fault injection/recovery | Pre-release hoặc định kỳ | Failover, no-instance, topology update, retry bounded |

### Ví dụ acceptance criteria rõ ràng

Một đội có thể quy định:

- **Correctness:** 100% generated inputs hợp lệ không làm chọn ngoài candidate snapshot; no-instance trả đúng response.
- **Stable Round Robin:** 12.000 selections trên 3 candidate cố định cho counts 4.000/4.000/4.000.
- **Weighted Random:** trong một phép thử lớn, tỷ lệ gần target theo ngưỡng thống kê đã tính trước; không yêu cầu chính xác tuyệt đối mỗi lần chạy.
- **Dynamic discovery:** trong một snapshot không chứa B, không lượt chọn nào trả B; fairness của window trước/sau update được đánh giá riêng.
- **Performance:** không có regression CPU/allocations đáng kể so baseline trong cùng môi trường đo; p95/p99 API không vượt SLO vận hành.
- **Recovery:** khi loại replica lỗi, retry/health supplier và selector không tạo vòng lặp vô hạn hoặc lựa chọn instance ngoài tập cho phép.

Đây là **ví dụ chính sách**, không phải tiêu chuẩn cố định của Spring Cloud. Điều chỉnh theo traffic, backend heterogeneity và fairness objective thực tế.

### Lỗi thiết kế test cần tránh

Một số anti-pattern:

~~~java
// Sai với Random: không thể yêu cầu chính xác 50/50.
assertEquals(500, countAAfter1000RandomRequests);

// Sai với nhiều caller: RoundRobin cursor không nhất thiết chung.
// Sai với zone filter: 3 instance registered != 3 instance eligible.
// Sai với retry: 1 business request != 1 load-balancer selection.
~~~

Nếu test statistical fail không đều, đừng tăng ngưỡng qua nhiều lần thử cho tới khi test “xanh”. Hãy kiểm tra giả định phân phối, số mẫu, confidence bound và nguồn nondeterminism. Với seeded randomness, log seed và sample counts để tái hiện.

## 25. Khung đánh giá trước khi thay Round Robin mặc định

Trước khi viết và triển khai custom algorithm, trả lời:

**A. Vấn đề cần giải quyết là gì?** Ví dụ instance weights khác nhau, zone locality, sticky session, giảm in-flight overload, affinity theo partition hoặc chi phí cao từ việc quét metadata.

**B. Tầng phù hợp có phải chooser không?** Nhiều bài toán zone/health/weight có thể giải bằng `ServiceInstanceListSupplier` và built-in policy, không cần tự viết `ReactorServiceInstanceLoadBalancer`. Nếu đã có `WeightedServiceInstanceListSupplier`, đừng double-weight ở custom picker.

**C. Thuật toán mới có invariant nào mạnh hơn?** Ví dụ ổn định phân phối khi tăng/giảm replica, bounded load, fairness theo năng lực backend hoặc giảm p99. Nếu không có invariant mới, tăng complexity có thể không đáng.

**D. Giá phải trả?** CPU, memory, lifecycle quản lý state, metadata refresh, risk race và cost debug. Phải đo trên lưu lượng thật hoặc workload mô phỏng có cùng đặc điểm.

**E. Làm sao rollback?** Bật policy bằng cấu hình có phạm vi theo service ID, giữ baseline Round Robin, quan sát metrics/traces và có quy trình khôi phục nhanh khi overload.

Một bảng quyết định minh họa:

| Yêu cầu | Điểm mở rộng nên đánh giá trước | Kiểm thử trọng tâm |
|---|---|---|
| Chia đều instances tương đương | Round Robin mặc định | Counts ổn định, cost thấp |
| Chọn ngẫu nhiên | RandomLoadBalancer | Statistical fairness, random seed tests |
| Weight theo năng lực | Weighted supplier/WeightFunction | Target weighted shares, update weights |
| Zone locality | Zone preference supplier | Không route sai zone khi policy yêu cầu |
| Sticky theo request | Same-instance/session preference hoặc policy affinity | Same-key consistency và fallback khi replica mất |
| Health filtering | HealthCheckServiceInstanceListSupplier | Loại unhealthy, thời gian cập nhật |
| Retry sang replica khác | Retry-aware supplier + policy | Avoid-previous khi đủ ứng viên |
| Least-active/adaptive | Custom selector + telemetry phù hợp | p99 latency, stale counter, concurrency |
| Consistent hashing | Custom policy có key và ring | Churn khi thêm/bớt instance, hotspot, memory |

**Không biến một bài test fairness thành mục tiêu tối ưu duy nhất.** Một bộ chọn chia đều request nhưng làm tăng p99 của service chậm có thể kém hơn weighted/adaptive policy dù raw counts đẹp.

## 26. Bảng chẩn đoán khi kiểm thử thất bại

| Hiện tượng | Khả năng nguyên nhân | Điều cần kiểm tra |
|---|---|---|
| Index vượt giới hạn | Cursor dùng size cũ hoặc danh sách sửa đồng thời | Snapshot immutability, modulo từ size hiện tại |
| Request chọn replica đã bị lọc | Không gọi `supplier.get(request)` hoặc dùng list registry raw | Supplier chain, request context, test eligibility |
| Round Robin không cân bằng trong unit test | Counter không atomic hoặc list thay đổi | Test fixed list, shared state, concurrency |
| Round Robin không cân bằng ở backend | Retry, no-instance, backend timeout, số caller khác nhau | Tách selections/attempts/completions |
| Random hai lần liền chọn A | Hành vi random bình thường | Test sample đủ lớn; không assert luân phiên |
| Weighted distribution sai | Parser weights, double weighting, weight update stale | Metadata và transformed candidate set |
| Chỉ chọn một instance | Health/zone/hint/sticky supplier trả một ứng viên | Ghi candidate snapshot tại thời điểm chọn |
| Chi phí tăng tuyến tính theo số instance | Mỗi lần sort/copy/scan weights | Benchmark từng công đoạn, heap allocations |
| CPU tăng khi nhiều thread | Atomic contention hoặc synchronized block | JMH theo thread count, async-profiler |
| Timeout không đổi dù picker nhanh | HTTP/backend latency chiếm phần lớn | p99 decomposition và transport metrics |
| Callback không chạy | Custom adapter bỏ `SelectedInstanceCallback` | Test success callback, empty path |
| `Mono` không có kết quả khi supplier rỗng | Không dùng `defaultIfEmpty` | Test supplier Flux.empty() |
| `No servers available` dù discovery có instance | Cache/health/hint supplier loại hết | Test final candidate set, no-instance policy |
| Custom policy áp dụng cho payment | Bean configuration bị scan global | `@LoadBalancerClient` child context scope |
| Feign vẫn gọi trực tiếp hostname | `@FeignClient(url=...)` hoặc thiếu LB integration | Cấu hình Feign và LoadBalancer starter |
| Regression chỉ xuất hiện sau deploy | JDK/JVM khác, weights/topology khác, cold contexts | Benchmark metadata và rollout metrics |
| Test random flaky | Sample nhỏ, threshold không có cơ sở | Seed/independent trials/expected shares |

## 27. Checklist kiểm thử thuật toán trước production

- [ ] Có hợp đồng cụ thể cho danh sách rỗng, một instance, nhiều instance và invalid metadata.
- [ ] Thuật toán chỉ chọn một instance trong snapshot đã qua policy lọc.
- [ ] Không mutate shared candidate list hoặc lưu request context trong singleton mutable fields.
- [ ] Unit test Round Robin deterministic, random seed và những edge cases của weights.
- [ ] Concurrency test kiểm tra atomic state, race, vòng lặp vô hạn và callback.
- [ ] Có test `ServiceInstanceListSupplier.get(request)` với request-specific hint/zone/retry.
- [ ] Test `EmptyResponse` khi list rỗng hoặc supplier không emit.
- [ ] Phân biệt fairness theo raw selection, HTTP attempts, responses và backend capacity.
- [ ] Định nghĩa fairness mục tiêu: equal, weighted, sticky, zone hay least-active.
- [ ] Statistical test có sample size/threshold/confidence được chọn trước, không flaky vô cớ.
- [ ] Khi topology thay đổi, fairness tính trên eligibility từng snapshot/window.
- [ ] Không mặc định Round Robin có cùng cursor xuyên tất cả caller replicas.
- [ ] Có integration test với RestClient/WebClient/OpenFeign qua service ID thật.
- [ ] Test scope `@LoadBalancerClient` tránh leak policy sang service khác.
- [ ] Fault-injection test với một replica chết, không instance, discovery chậm và retry bounded.
- [ ] Có JMH benchmark theo n, concurrency, weight/update cadence, allocation và GC.
- [ ] Đo riêng cold path, warm path và chi phí build/rebuild supplier/weight tables.
- [ ] Quan sát p50/p95/p99 end-to-end, không suy ra HTTP speedup từ microbenchmark.
- [ ] Metric labels không chứa user/session/correlation ID hoặc URI động có cardinality vô hạn.
- [ ] Có baseline, rollback plan và đo canary trước khi rollout rộng.
- [ ] Không chạy benchmark performance cứng làm flaky test trên shared CI worker.
- [ ] Báo cáo đủ môi trường, input size, service ID, number of calls, phương pháp đo và sai số.

## Tài liệu tham khảo

- [Spring Cloud Commons — Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): `RoundRobinLoadBalancer`, `RandomLoadBalancer`, `ServiceInstanceListSupplier`, custom configuration, weighted/zone/sticky policies, lifecycle/metrics.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): các thuộc tính cache, health, retry và thống kê của LoadBalancer.
- [Spring Cloud Commons — RoundRobinLoadBalancer source](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/core/RoundRobinLoadBalancer.java): ví dụ `choose(Request)`, `DefaultResponse`/`EmptyResponse` và `SelectedInstanceCallback`.
- [Spring Cloud Commons — ServiceInstanceListSuppliers](https://github.com/spring-cloud/spring-cloud-commons/blob/main/spring-cloud-loadbalancer/src/main/java/org/springframework/cloud/loadbalancer/support/ServiceInstanceListSuppliers.java): helper dựng static supplier/provider phục vụ unit test.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): assertion, lifecycle và parameterized tests.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, kiểm thử reactive pipelines và publisher behavior.
- [JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh): benchmark JVM với forks, warmup, measurement và Blackhole.
- [Micrometer Documentation](https://docs.micrometer.io/micrometer/reference/): metrics, tags, cardinality và phân tích latency.

**Kết luận:** một custom Spring Cloud LoadBalancer đáng tin cậy phải **chọn đúng trong tập ứng viên thực tế**, **phân phối phù hợp chính sách** và **giữ chi phí thấp ở mức tải dự kiến**. Unit/property/concurrency tests chứng minh invariant của bộ chọn; reactive adapter tests chứng minh contract với `ServiceInstanceListSupplier`; integration tests qua RestClient/WebClient/OpenFeign chứng minh đường request theo service ID; benchmark và observability cho biết thuật toán có thật sự cải thiện hiệu năng hệ thống hay không. Chỉ nên rollout khi cả ba chiều đúng, công bằng và chi phí đều được đo bằng cùng một hợp đồng rõ ràng.


