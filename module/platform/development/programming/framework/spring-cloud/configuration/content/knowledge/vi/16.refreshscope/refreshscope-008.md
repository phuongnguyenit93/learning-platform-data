# Tính nhất quán khi nhiều luồng đọc cấu hình đang thay đổi

Một ứng dụng Spring Boot có thể phục vụ hàng trăm request đồng thời trong lúc cấu hình được refresh từ Spring Cloud Config. Khi một thay đổi cập nhật nhiều thuộc tính liên quan, chẳng hạn `capacity` và `refill-period` của rate limiter, các luồng đang chạy cần có một cách đọc nhất quán. Nếu một request đọc một nửa giá trị cũ và một nửa giá trị mới, hành vi có thể sai dù từng giá trị riêng lẻ đều hợp lệ.

Spring Cloud Context cung cấp cơ chế refresh Environment và các bean thuộc `@RefreshScope`. Tuy nhiên, refresh không phải một giao dịch nguyên tử bao trùm mọi bean, mọi request và mọi instance. Muốn bảo đảm một thao tác đọc dùng cùng một phiên bản cấu hình, cần thiết kế snapshot bất biến, thay thế snapshot theo một thao tác nguyên tử và xác định rõ ranh giới nhất quán.

Bài viết giải thích các tình huống cạnh tranh khi refresh, vòng đời target của `@RefreshScope`, cách công bố cấu hình mới an toàn bằng `AtomicReference`, cách giữ một snapshot trong suốt request, và cách kiểm thử nhiều luồng đọc trong lúc cập nhật.

## 1. Vấn đề khi nhiều luồng đọc cùng lúc

Giả sử dịch vụ đơn hàng có chính sách giới hạn request gồm hai thuộc tính:

```yaml
api:
  rate-limit:
    capacity: 100
    refill-period: 1m
    revision: rate-limit-v1
```

Nhóm vận hành muốn thay đổi thành:

```yaml
api:
  rate-limit:
    capacity: 50
    refill-period: 10s
    revision: rate-limit-v2
```

Hai giá trị tạo thành một chính sách. Capacity 100 đi cùng refill period 1 phút; capacity 50 đi cùng refill period 10 giây. Nếu code đọc hai thuộc tính ở hai thời điểm khác nhau trong khi refresh xảy ra, nó có thể quan sát một tổ hợp chưa từng được phát hành.

Ví dụ luồng thực thi:

```text
Thread A: đọc capacity = 100
Thread B: refresh Environment sang capacity=50, refill-period=10s
Thread A: đọc refill-period = 10s
Thread A: thực thi policy (100, 10s)
```

Tổ hợp `(100, 10s)` không thuộc phiên bản cấu hình cũ cũng không thuộc phiên bản mới. Đây là hiện tượng đọc hỗn hợp (mixed snapshot).

Không phải mọi lần đọc property đều tạo ra lỗi. Nếu một thuộc tính độc lập và được đọc một lần, giá trị cũ hoặc mới có thể đều chấp nhận được. Rủi ro xuất hiện khi nhiều giá trị có quan hệ với nhau, khi một request đọc cấu hình nhiều lần, hoặc khi các thành phần cần cùng sử dụng một phiên bản policy.

## 2. Refresh không phải giao dịch nguyên tử trên toàn ứng dụng

Spring Cloud Context có thể làm mới Environment, phát sự kiện thay đổi thuộc tính, rebind một số bean và invalidate target của các bean thuộc `@RefreshScope`. Những thao tác này không tạo thành một giao dịch nguyên tử bao trùm tất cả luồng đang chạy.

Một số tình huống cần phân biệt:

- Environment đã được cập nhật, nhưng một bean thông thường vẫn giữ bản sao cấu hình cũ.
- Một bean mutable được cập nhật qua nhiều field hoặc setter; code đọc đồng thời không có bảo đảm rằng nhiều lần đọc sẽ thấy cùng một phiên bản.
- Target của một bean `@RefreshScope` bị loại khỏi cache, nhưng request đang thực thi có thể vẫn đang dùng target cũ.
- Một request gọi proxy nhiều lần ở những thời điểm khác nhau có thể đi qua các target khác nhau nếu refresh xảy ra giữa các lần gọi.
- Nhiều instance nhận refresh event ở các thời điểm khác nhau; không có cam kết tất cả cùng đổi cấu hình tại một thời điểm toàn cục.

Do đó, không nên diễn giải thành công của endpoint refresh là bằng chứng mọi request đã chuyển sang cùng một phiên bản cấu hình.

## 3. Vòng đời target của @RefreshScope

`@RefreshScope` tạo một scoped proxy cho bean. Proxy giữ quyền truy cập đến target hiện tại; target được lưu trong scope cache. Khi refresh scope, các target đang cache bị invalidate và callback hủy tài nguyên được gọi nếu có. Lần gọi tiếp theo qua proxy sẽ tạo target mới và bind các giá trị từ Environment hiện tại.

Ví dụ:

```java
@Component
@RefreshScope
public class OrderPolicy {

    @Value("${api.rate-limit.capacity:100}")
    private int capacity;

    @Value("${api.rate-limit.refill-period:1m}")
    private Duration refillPeriod;

    public PolicySnapshot snapshot() {
        return new PolicySnapshot(capacity, refillPeriod);
    }
}
```

`OrderPolicy` được inject vào service thông qua proxy. Khi scope được refresh, target mới sẽ được tạo ở lần truy cập kế tiếp.

Cơ chế này giúp thay target bean mà không cần restart toàn bộ JVM, nhưng cần lưu ý:

- Request đang giữ reference tới target cũ có thể tiếp tục thực thi bằng target đó.
- Nếu một request gọi nhiều method qua proxy, refresh có thể xảy ra giữa các lần gọi.
- Nếu target quản lý tài nguyên như connection, executor hoặc client có trạng thái, callback hủy target cần được thiết kế để không đóng tài nguyên khi còn thao tác đang dùng.
- Nhiều bean refresh scope được invalidate không đồng nghĩa tất cả target mới được tạo cùng lúc.
- `@RefreshScope` không tự cung cấp một snapshot nhất quán cho toàn bộ object graph hoặc toàn bộ request.

Với bean chỉ cung cấp một cấu hình bất biến và method trả về một snapshot duy nhất, proxy thường là ranh giới phù hợp. Nếu request cần nhiều thành phần cùng đọc một phiên bản policy, hãy capture snapshot một lần ở ranh giới request và truyền nó xuyên suốt quá trình xử lý.

## 4. Vì sao bean cấu hình mutable có thể tạo trạng thái trung gian?

Một bean cấu hình mutable có thể trông như sau:

```java
@Component
@ConfigurationProperties(prefix = "api.rate-limit")
public class MutableRateLimitProperties {

    private int capacity;
    private Duration refillPeriod;

    public int getCapacity() {
        return capacity;
    }

    public void setCapacity(int capacity) {
        this.capacity = capacity;
    }

    public Duration getRefillPeriod() {
        return refillPeriod;
    }

    public void setRefillPeriod(Duration refillPeriod) {
        this.refillPeriod = refillPeriod;
    }
}
```

Nếu các thuộc tính được cập nhật riêng lẻ, hai getter được gọi ở hai thời điểm khác nhau có thể quan sát các giá trị thuộc hai lần cập nhật. Việc đánh dấu từng field là `volatile` chỉ cải thiện khả năng nhìn thấy giá trị của từng field; nó không biến cập nhật nhiều field thành một thao tác nguyên tử.

Tương tự, gọi `Environment.getProperty(...)` nhiều lần không tạo ra một transaction đọc snapshot. Nếu Environment hoặc nguồn cấu hình liên quan thay đổi giữa các lần đọc, ứng dụng không nên mặc định các kết quả thuộc cùng một phiên bản.

Với nhóm thuộc tính có quan hệ, nên bind thành một object bất biến rồi thay toàn bộ reference khi có phiên bản mới. Nhờ đó, luồng đọc chỉ cần lấy reference một lần và sử dụng các field của cùng một object.

## 5. Mô hình snapshot bất biến

Một snapshot là một object đại diện cho toàn bộ bộ giá trị cần dùng trong một thao tác. Nên dùng record hoặc class bất biến, không cung cấp setter và không sửa field sau khi tạo.

Ví dụ:

```java
import java.time.Duration;

public record RateLimitPolicy(
        int capacity,
        Duration refillPeriod,
        String revision) {

    public RateLimitPolicy {
        if (capacity < 1) {
            throw new IllegalArgumentException(
                    "capacity phải lớn hơn 0");
        }
        if (refillPeriod == null
                || refillPeriod.isZero()
                || refillPeriod.isNegative()) {
            throw new IllegalArgumentException(
                    "refillPeriod phải lớn hơn 0");
        }
        if (revision == null || revision.isBlank()) {
            throw new IllegalArgumentException(
                    "revision không được để trống");
        }
    }
}
```

Tạo snapshot mới sau khi đã bind và validate tất cả thuộc tính. Nếu bất kỳ giá trị nào không hợp lệ, không công bố snapshot đó. Snapshot hiện tại tiếp tục được dùng cho đến khi có phiên bản hợp lệ được thay thế.

Trường `revision` có thể là mã phiên bản cấu hình do pipeline phát hành, Git commit hoặc generation number do ứng dụng quản lý. Nó giúp log và metric chỉ ra request đã dùng bộ cấu hình nào mà không cần ghi các giá trị nhạy cảm.

## 6. Công bố snapshot bằng AtomicReference

`AtomicReference` cho phép thay reference hiện tại bằng một thao tác nguyên tử. Luồng đọc nhận toàn bộ object cũ hoặc toàn bộ object mới; nó không thể nhận một nửa field của mỗi object nếu object bất biến và reader giữ cùng reference.

Ví dụ một provider:

```java
package com.example.orders.config;

import java.util.concurrent.atomic.AtomicReference;

import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.cloud.context.environment.EnvironmentChangeEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class RateLimitPolicyProvider {

    private final Environment environment;
    private final AtomicReference<RateLimitPolicy> current;

    public RateLimitPolicyProvider(Environment environment) {
        this.environment = environment;
        this.current = new AtomicReference<>(loadAndValidate());
    }

    public RateLimitPolicy currentSnapshot() {
        return current.get();
    }

    @EventListener
    public void onEnvironmentChange(EnvironmentChangeEvent event) {
        boolean relevant = event.getKeys().stream()
                .anyMatch(key -> key.startsWith("api.rate-limit."));

        if (!relevant) {
            return;
        }

        // Bind và validate xong rồi mới công bố snapshot.
        RateLimitPolicy candidate = loadAndValidate();
        current.set(candidate);
    }

    private RateLimitPolicy loadAndValidate() {
        return Binder.get(environment)
                .bind("api.rate-limit", RateLimitPolicy.class)
                .orElseThrow(() -> new IllegalStateException(
                        "Thiếu cấu hình api.rate-limit"));
    }
}
```

Trong ví dụ, event listener chỉ phản ứng với các key thuộc nhóm `api.rate-limit`. Nó bind toàn bộ nhóm thành một record và constructor của record thực hiện validation. Chỉ khi quá trình bind và validation thành công, `current.set(candidate)` mới thay reference hiện tại.

Có thể bỏ import không dùng trong đoạn minh họa khi đưa vào dự án thực tế. Dependency và cách đăng ký `EnvironmentChangeEvent` phải phù hợp với Spring Cloud Context đang sử dụng. Nếu hệ thống cần kiểm soát chặt thứ tự cập nhật, hãy đặt thao tác tạo snapshot trong một thành phần refresh chuyên trách và gọi sau khi Environment đã được cập nhật.

Nếu bind hoặc validate thất bại, không thay reference hiện tại. Ứng dụng tiếp tục sử dụng snapshot gần nhất đã được xác nhận hợp lệ, đồng thời cần báo lỗi rõ ràng qua log/metric và đánh dấu lần refresh thất bại. Không nên âm thầm coi Environment mới là trạng thái đã được áp dụng trong khi provider vẫn dùng snapshot cũ.

## 7. Capture snapshot một lần cho mỗi request

Dù provider dùng AtomicReference, request vẫn cần đọc reference một lần. Nếu gọi `currentSnapshot()` nhiều lần trong cùng một luồng xử lý, refresh có thể xảy ra giữa các lần đọc và request có thể dùng hai revision khác nhau.

Ví dụ:

```java
@Service
public class OrderRequestService {

    private final RateLimitPolicyProvider policyProvider;
    private final LocalTokenBucket tokenBucket;

    public OrderRequestService(
            RateLimitPolicyProvider policyProvider,
            LocalTokenBucket tokenBucket) {
        this.policyProvider = policyProvider;
        this.tokenBucket = tokenBucket;
    }

    public OrderResult process(String clientId, OrderCommand command) {
        RateLimitPolicy policy = policyProvider.currentSnapshot();

        if (!tokenBucket.tryConsume(clientId, policy)) {
            throw new TooManyRequestsException();
        }

        return createOrder(command, policy.revision());
    }

    private OrderResult createOrder(
            OrderCommand command,
            String configRevision) {
        // Xử lý nghiệp vụ; revision có thể được gắn vào trace metadata.
        return new OrderResult("accepted", configRevision);
    }
}
```

Request capture snapshot ở đầu thao tác và truyền nó vào các thành phần cần dùng. Dù refresh diễn ra giữa lúc kiểm tra quota và tạo đơn, toàn bộ thao tác vẫn có thể ghi nhận cùng revision. Nếu một nghiệp vụ kéo dài qua nhiều bước hoặc nhiều message, hãy quyết định snapshot được giữ trong suốt workflow hay mỗi bước dùng cấu hình mới; hai lựa chọn có semantics khác nhau.

Không nên để từng component tự gọi provider và lấy snapshot riêng nếu các component cần nhất quán trong cùng một request. Truyền snapshot như tham số tường minh giúp ranh giới phiên bản dễ hiểu và dễ kiểm thử.

## 8. Atomic swap không tự giải quyết mọi trạng thái có thể thay đổi

Snapshot bất biến giải quyết tính nhất quán của các giá trị cấu hình được đọc cùng nhau. Nó không tự quyết định cách chuyển trạng thái nghiệp vụ từ policy cũ sang policy mới.

Ví dụ rate limiter có các bucket đang giữ token. Khi capacity giảm từ 100 xuống 50, có nhiều chính sách khả dĩ:

- Reset bucket về capacity mới.
- Giữ số token hiện tại nhưng giới hạn tối đa ở capacity mới.
- Giữ bucket cũ đến khi hết chu kỳ rồi áp dụng policy mới.
- Chỉ áp dụng policy mới cho client key được tạo sau refresh.

Mỗi lựa chọn có tác động khác nhau đến lưu lượng. Cần tách **policy snapshot** khỏi **state bucket**, rồi định nghĩa rõ cách state chuyển đổi khi revision thay đổi.

Nếu bucket được lưu trong bộ nhớ từng JVM, mỗi instance có state riêng. Atomic swap trong một instance không tạo quota thống nhất toàn cluster. Nếu cần giới hạn toàn cụm, sử dụng gateway hoặc kho trạng thái phân tán và thiết kế cập nhật policy theo cơ chế của hệ thống đó.

## 9. Nhất quán giữa nhiều bean

Một số nghiệp vụ cần nhiều bean dùng cùng một revision. Ví dụ một bean kiểm tra hạn mức và một bean tính phí cùng đọc `billing.policy`. Nếu mỗi bean refresh độc lập, một request có thể gặp tình huống bean A đã dùng revision mới trong khi bean B vẫn dùng revision cũ.

Có ba hướng thiết kế:

1. **Gom các thuộc tính liên quan vào một policy aggregate**: một object bất biến chứa toàn bộ giá trị cần đồng bộ; các component nhận cùng snapshot.
2. **Capture ở ranh giới workflow**: controller, message handler hoặc application service lấy snapshot một lần rồi truyền xuống các tầng.
3. **Dùng version/generation**: mọi snapshot có cùng revision; component có thể từ chối hoặc retry nếu phát hiện revision không tương thích.

Không nên dùng nhiều bean `@RefreshScope` riêng biệt như một giao dịch đa bean. Scope refresh có thể invalidate nhiều target, nhưng không cung cấp một điểm commit nguyên tử cho toàn bộ object graph.

Nếu bắt buộc nhiều thành phần cùng chuyển phiên bản đồng thời trong một JVM, có thể tạo một aggregate snapshot duy nhất và atomically swap reference của aggregate đó. Khi một thao tác bắt đầu, nó lấy aggregate reference một lần và dùng toàn bộ các policy con từ cùng phiên bản.

## 10. Giới hạn nhất quán giữa các instance

Spring Cloud Bus có thể phát sự kiện refresh đến nhiều instance, nhưng việc phân phối sự kiện là bất đồng bộ. Mỗi instance nhận, nạp và công bố cấu hình vào thời điểm riêng. Vì vậy, trong một khoảng chuyển tiếp, instance A có thể dùng revision mới trong khi instance B vẫn dùng revision cũ.

Bus giúp truyền sự kiện; nó không tạo một giao dịch commit đồng thời trên toàn bộ cluster. Nếu cần quan sát và quản lý quá trình chuyển đổi:

- Gắn revision hoặc generation vào mỗi snapshot.
- Log revision khi một instance công bố policy mới.
- Expose metric số instance đang dùng từng revision.
- Theo dõi thời gian từ lúc phát refresh đến lúc từng instance xác nhận.
- Chỉ coi rollout hoàn tất khi đủ instance đã báo revision đích.
- Có kế hoạch rollback nếu một số instance không thể nạp hoặc validate revision mới.

Với thay đổi không tương thích, có thể dùng quy trình hai pha: phát hành phiên bản cấu hình tương thích ngược trước, nâng cấp ứng dụng, rồi mới chuyển sang policy mới. Nếu yêu cầu mọi request toàn cụm phải dùng cùng revision ngay tại một thời điểm, cần một cơ chế điều phối mạnh hơn như quiesce traffic, routing theo revision hoặc một hệ thống policy trung tâm có semantics đồng bộ rõ ràng.

## 11. Kiểm thử tính nhất quán với nhiều luồng

Một test hữu ích nên kiểm tra invariant của snapshot thay vì chỉ xác nhận endpoint refresh trả HTTP 200.

Ví dụ policy có hai phiên bản hợp lệ:

- Revision `v1`: capacity 100, refill period 60 giây.
- Revision `v2`: capacity 50, refill period 10 giây.

Hai tổ hợp chéo `(100, 10s)` và `(50, 60s)` không hợp lệ. Có thể stress test việc nhiều reader lấy snapshot trong khi writer thay đổi reference:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;

class PolicySnapshotConcurrencyTest {

    record Policy(int capacity, Duration refillPeriod, String revision) {
        boolean isValidPair() {
            return (capacity == 100
                    && refillPeriod.equals(Duration.ofSeconds(60))
                    && revision.equals("v1"))
                || (capacity == 50
                    && refillPeriod.equals(Duration.ofSeconds(10))
                    && revision.equals("v2"));
        }
    }

    @Test
    void readersAlwaysObserveOneCompleteRevision() throws Exception {
        Policy v1 = new Policy(100, Duration.ofSeconds(60), "v1");
        Policy v2 = new Policy(50, Duration.ofSeconds(10), "v2");
        AtomicReference<Policy> current = new AtomicReference<>(v1);

        int readerCount = 8;
        ExecutorService pool = Executors.newFixedThreadPool(readerCount + 1);
        CountDownLatch start = new CountDownLatch(1);

        Future<?> writer = pool.submit(() -> {
            await(start);
            for (int i = 0; i < 100_000; i++) {
                current.set((i & 1) == 0 ? v2 : v1);
            }
        });

        Future<?>[] readers = new Future<?>[readerCount];
        for (int i = 0; i < readerCount; i++) {
            readers[i] = pool.submit(() -> {
                await(start);
                for (int j = 0; j < 100_000; j++) {
                    Policy snapshot = current.get();
                    assertThat(snapshot.isValidPair()).isTrue();
                }
            });
        }

        start.countDown();
        writer.get();
        for (Future<?> reader : readers) {
            reader.get();
        }
        pool.shutdown();
        assertThat(pool.awaitTermination(5, TimeUnit.SECONDS)).isTrue();
    }

    private static void await(CountDownLatch latch) {
        try {
            latch.await();
        }
        catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(ex);
        }
    }
}
```

Test minh họa chứng minh reader lấy một reference duy nhất sẽ nhận một trong hai snapshot hoàn chỉnh. Nó không kiểm thử toàn bộ Spring Cloud refresh pipeline; integration test cần bổ sung bước cập nhật Environment, phát `EnvironmentChangeEvent` hoặc gọi refresh endpoint, sau đó xác nhận provider công bố revision mới.

Một test tích hợp nên có các bước:

1. Khởi động ứng dụng với revision v1.
2. Gửi nhiều request đồng thời và ghi nhận revision snapshot từng request.
3. Cập nhật nguồn cấu hình sang v2.
4. Kích hoạt refresh.
5. Xác nhận request đã capture v1 có thể hoàn tất với v1 theo thiết kế.
6. Xác nhận request bắt đầu sau khi v2 được công bố chỉ dùng v2.
7. Cố tình cung cấp cấu hình không hợp lệ và xác nhận snapshot gần nhất vẫn được giữ.
8. Kiểm tra metric/log cho biết instance đã chuyển revision hay chưa.

## 12. Xử lý lỗi khi tạo snapshot mới

Một lần refresh có thể thất bại do thiếu key, sai kiểu dữ liệu hoặc vi phạm ràng buộc. Nếu provider thay từng field trước khi phát hiện lỗi, trạng thái đang dùng có thể bị hỏng.

Quy trình an toàn là:

1. Đọc tất cả key cần thiết từ Environment mới.
2. Bind vào object tạm thời.
3. Validate mọi ràng buộc và quan hệ giữa các field.
4. Gắn revision/generation.
5. Chỉ sau khi tất cả bước thành công mới atomically swap reference.
6. Nếu thất bại, giữ snapshot hiện tại, phát metric/log cảnh báo và yêu cầu rollback hoặc sửa cấu hình.

Không nên cập nhật `AtomicReference` trước rồi mới validate. Cũng không nên trả trạng thái refresh thành công nếu provider không thể công bố snapshot mới theo chính sách của ứng dụng. Cần phân biệt refresh Environment thành công với refresh policy aggregate thành công.

Nếu dùng `EnvironmentChangeEvent` listener, hãy chú ý event được phát trong chu trình refresh và thứ tự listener của ứng dụng. Với logic cần chạy sau khi toàn bộ bước refresh hoàn tất, có thể tạo một orchestration service riêng để gọi refresh và công bố snapshot theo trình tự rõ ràng, thay vì dựa vào thứ tự tình cờ giữa nhiều listener.

## 13. Các lỗi thiết kế thường gặp

| Cách làm | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| Đọc từng key từ Environment ở nhiều thời điểm | Có thể kết hợp giá trị từ hai revision | Bind và capture một snapshot bất biến |
| Cập nhật nhiều field mutable trực tiếp | Reader có thể thấy trạng thái trung gian | Tạo object mới rồi atomically swap reference |
| Cho mỗi bean tự lấy snapshot | Một request có thể dùng nhiều revision | Capture ở ranh giới request/workflow |
| Cho rằng @RefreshScope refresh toàn bộ object graph | Scope không cung cấp transaction đa bean | Gom thuộc tính liên quan vào aggregate |
| Cho rằng refresh endpoint thành công nghĩa là tất cả request đã đổi | Request đang chạy có thể vẫn dùng target cũ | Ghi revision và theo dõi trạng thái từng instance |
| Reset mọi state mà không đánh giá | Có thể tạo burst token hoặc thay đổi quota đột ngột | Định nghĩa chính sách chuyển state |
| Dùng AtomicReference cho từng field riêng | Không bảo đảm snapshot nhiều field | Dùng một reference cho cả aggregate |
| Chỉ test refresh HTTP status | Không phát hiện mixed snapshot hoặc lỗi hành vi | Stress test reader/writer và integration test |

## 14. Nguyên tắc vận hành

- Gom các thuộc tính có quan hệ thành một policy aggregate bất biến.
- Bind và validate toàn bộ candidate trước khi công bố.
- Dùng một thao tác atomic swap để thay snapshot hiện tại.
- Mỗi request hoặc workflow capture snapshot đúng một lần nếu cần nhất quán xuyên suốt.
- Dùng `@RefreshScope` cho bean phù hợp với vòng đời tạo lại; không coi nó là giao dịch nguyên tử trên toàn ứng dụng.
- Phân biệt cấu hình đã nạp trong Environment với policy snapshot mà component thực thi đang dùng.
- Gắn revision/generation vào snapshot và quan sát tiến độ refresh từng instance.
- Quy định cách chuyển trạng thái phụ thuộc cấu hình như bucket, cache, pool hoặc client.
- Kiểm thử concurrency, cấu hình lỗi và refresh bất đồng bộ trước khi áp dụng production.
- Không log secret; bảo vệ endpoint refresh và endpoint chẩn đoán.

Tính nhất quán khi refresh là vấn đề về ranh giới đọc và công bố cấu hình. `@RefreshScope` hỗ trợ tạo lại target bean sau khi scope được invalidate, nhưng không tự bảo đảm mọi luồng, mọi bean hoặc mọi instance cùng đổi tại một thời điểm. Một snapshot bất biến được công bố bằng `AtomicReference`, kết hợp với việc capture snapshot ở ranh giới request, giúp mỗi thao tác sử dụng một bộ giá trị hoàn chỉnh. Khi bổ sung revision, validation, kiểm thử concurrency và giám sát từng instance, nhóm có thể thay đổi cấu hình động mà vẫn giải thích được request đã chạy theo phiên bản policy nào.

