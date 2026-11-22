# So sánh routing slip với flow tĩnh

## 1. Vấn đề: không phải mọi message đều cần cùng một hành trình

Trong Spring Integration, một **integration flow tĩnh** mô tả trước các endpoint và message channel nối với nhau. Ví dụ, mọi yêu cầu đặt hàng đều đi qua bước chuẩn hóa, kiểm tra hợp lệ, lưu đơn hàng và trả biên nhận. Cấu trúc này minh bạch, dễ đọc và phù hợp khi các bước xử lý tương đối ổn định.

Tuy nhiên, không phải đơn hàng nào cũng cần cùng một danh sách công việc. Đơn nội địa có thể chỉ cần chuẩn hóa và lưu; đơn quốc tế cần thêm bước kiểm tra tuân thủ; đơn giá trị cao còn cần bước phê duyệt. Khi **trình tự các bước phải được chọn riêng cho từng message**, mẫu **Routing Slip** (phiếu định tuyến) trở thành một lựa chọn đáng xem xét.

~~~mermaid
flowchart LR
    subgraph STATIC["Flow tĩnh"]
      S[Input] --> V[Validate]
      V --> N[Normalize]
      N --> P[Persist]
      P --> O[Output]
    end
    subgraph SLIP["Routing Slip theo từng message"]
      I[Input] --> PLAN[Route planner]
      PLAN --> PATH{Itinerary}
      PATH -->|Nội địa| D["validate → persist"]
      PATH -->|Quốc tế| X["validate → compliance → persist"]
      PATH -->|Giá trị cao| R["validate → review → persist"]
    end
~~~

**Routing Slip** là một Enterprise Integration Pattern mô tả **lộ trình dự kiến của một message** dưới dạng danh sách các bước/đích nhận và thông tin bước đang thực hiện. Message lần lượt đi qua các điểm trong danh sách cho đến khi hoàn tất hoặc gặp sự cố. Trong Spring Integration có hỗ trợ mẫu Routing Slip; các chi tiết như header nội bộ, cách khai báo route strategy và cách tự động chuyển sang hop tiếp theo phụ thuộc API và phiên bản framework, vì vậy **không thể chỉ gắn một header tùy ý tên `routePlan` rồi coi đó là Routing Slip của framework**.

Bài học thuộc chương **Routing slip** của module `SPRING_INTEGRATION_PATTERN`. Mục tiêu của module là triển khai Enterprise Integration Patterns bằng Spring Integration để tạo luồng thông điệp ít phụ thuộc, dễ mở rộng, kết hợp Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation, kiểm thử và theo dõi nhánh xử lý. So sánh Routing Slip với flow tĩnh giúp chọn đúng độ linh hoạt, tính minh bạch và mức kiểm soát vận hành.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **flow tĩnh**, **Routing Slip**, **hop**, **route plan** và **con trỏ bước hiện tại**.
2. Chỉ ra điểm giống và khác giữa Routing Slip, Content-Based Router, Router phân cấp, Recipient List và Scatter–Gather.
3. Thiết kế trình tự endpoint theo từng loại message mà vẫn giữ **danh sách endpoint được phép**.
4. Nhận biết các rủi ro về lỗi tại hop giữa, retry, trùng side effect, mất header, route loop và message không có reply.
5. Đọc một ví dụ Java DSL cho flow tĩnh và một ví dụ Java minh họa việc lập kế hoạch hành trình.
6. Xây dựng test cho lộ trình, thứ tự bước, trường hợp thiếu endpoint, kết quả nghiệp vụ, tracing và recovery.

## 2. Flow tĩnh: đường đi được cấu hình trước

### 2.1. Bản chất của flow tĩnh

Trong Spring Integration, ta có thể định nghĩa một đường đi bằng Java DSL:

~~~text
orders.input
    -> validate
    -> normalize
    -> persist
    -> receipt
~~~

Các quan hệ nối endpoint đã có trong cấu hình application context. Khi chương trình chạy, message đi qua các bước theo wiring đó, trừ trường hợp có Router, Filter, lỗi hoặc logic khác làm thay đổi kết quả.

**Flow tĩnh không đồng nghĩa tất cả message phải có kết quả giống nhau.** Một handler có thể thay đổi dữ liệu theo payload, Filter có thể loại message, Router có thể chia nhánh. “Tĩnh” trong bài này chỉ nhấn mạnh **topology và thứ tự các bước cơ sở được khai báo trước ở cấu hình**, chứ không phải cấm mọi điều kiện lúc chạy.

### 2.2. Ưu điểm của đường đi tĩnh

- **Dễ đọc và review:** nhìn Java DSL hoặc sơ đồ đã biết endpoint nào đứng trước/sau.
- **Dễ kiểm thử:** mỗi bước và các nhánh hữu hạn có thể được test theo cấu hình.
- **Hợp đồng rõ:** input/output type, error channel, transaction boundary và reply channel dễ xác định.
- **Vận hành ít bất ngờ:** việc thêm một bước mới thường đòi thay cấu hình hoặc deploy có kiểm soát.
- **Tối ưu quan sát:** dashboard, metric và cảnh báo có thể dựa vào một tập endpoint ổn định.

### 2.3. Hạn chế của flow tĩnh

Nếu sản phẩm có nhiều quy trình rất khác nhau nhưng cố gắng ghép tất cả vào một chuỗi, flow có thể xuất hiện nhiều Router và Filter kiểm tra điều kiện ở khắp nơi:

~~~text
Validate
  -> Router cần compliance?
      -> Compliance hoặc bỏ qua
  -> Router cần review?
      -> Review hoặc bỏ qua
  -> Router cần enrichment?
      -> Enrich hoặc bỏ qua
  -> Persist
~~~

Với vài nhánh, cách này vẫn tốt. Khi số lộ trình tăng lớn và phải chọn **trình tự khác nhau cho từng request**, sơ đồ có thể trở thành đồ thị khó theo dõi. Routing Slip tách **kế hoạch hành trình của message** khỏi một chuỗi wiring cố định.

## 3. Routing Slip: hành trình là dữ liệu đi kèm message

### 3.1. Định nghĩa các thành phần

| Khái niệm | Ví dụ | Vai trò |
|---|---|---|
| **Route plan / itinerary** | `validate → review → persist` | Danh sách bước message phải đi qua. |
| **Hop** | `review` | Một bước xử lý/đích trên hành trình. |
| **Cursor / current index** | `2` | Chỉ số bước hiện tại hoặc kế tiếp. |
| **Route strategy** | Quy tắc chọn đích theo dữ liệu | Tính hay phân giải một bước nếu mô hình cho phép. |
| **Terminal destination** | `orders.completed` / reply | Nơi đi khi hết bước trong slip theo hợp đồng. |
| **Correlation/business context** | `orderId`, `traceId` | Nối các bước và theo dõi kết quả. |

Ở mức khái niệm, một hành trình có thể biểu diễn như:

~~~text
RoutePlan {
  version: "v1",
  hops: ["orders.validate", "orders.compliance", "orders.persist"],
  nextIndex: 0
}

Sau validate:   nextIndex=1
Sau compliance: nextIndex=2
Sau persist:    hoàn tất itinerary
~~~

**Đây là một mô hình minh họa**, không phải JSON schema hoặc tên header chính thức của Spring Integration. Hỗ trợ Routing Slip của framework quản lý lộ trình/hop theo cơ chế riêng. Trong ví dụ code ở phần sau, ta dùng một DTO `RoutePlan` để giải thích cách lập kế hoạch và test; nó không thay thế cấu hình Routing Slip thực tế.

### 3.2. Lộ trình được chọn cho từng message

Giả sử một đơn có ba điều kiện:

- Thị trường `VN` hoặc `INTL`.
- Có cần duyệt thủ công hay không.
- Có cần bổ sung dữ liệu khách hàng hay không.

Message A có thể mang itinerary:

~~~text
validate -> enrich -> persist
~~~

Message B có thể mang itinerary:

~~~text
validate -> compliance -> review -> persist
~~~

Message C có thể mang itinerary:

~~~text
validate -> persist
~~~

**Điểm quan trọng:** các endpoint `validate`, `enrich`, `compliance`, `review`, `persist` vẫn cần được **định nghĩa và đăng ký hợp lệ** trong hệ thống. Routing Slip không biến một tên stage tùy ý thành code hoặc bean có thể chạy. Nó chỉ quyết định **đường đi qua những thành phần đã tồn tại và được phép**.

### 3.3. Lộ trình không nhất thiết được phép tự ý thay đổi

Việc route plan đi cùng message giúp linh hoạt, nhưng nếu một client ngoài hệ thống có thể tự cung cấp:

~~~text
["orders.validate", "orders.skipFraud", "orders.persist"]
~~~

thì đây có thể trở thành cách vượt qua kiểm soát nghiệp vụ. Vì vậy, ở **trust boundary**:

1. Tính route plan từ **dữ liệu đã được xác thực** và policy trong ứng dụng.
2. Không chấp nhận danh sách tên bean/channel tùy ý do client yêu cầu.
3. Sử dụng **allowlist stage**, giới hạn độ dài, thứ tự và các điều kiện tiên quyết.
4. Gắn `policyVersion` hoặc ID hành trình nếu cần audit/replay.
5. Nếu route plan đi qua broker, định nghĩa cách bảo vệ và khôi phục metadata, không gửi object JVM không thể serialize.

## 4. Bảng so sánh tổng quan

| Tiêu chí | Flow tĩnh | Routing Slip |
|---|---|---|
| **Đường đi** | Cố định bởi cấu hình và các nhánh được khai báo. | Một itinerary được xác định cho từng message. |
| **Thời điểm chọn trình tự** | Chủ yếu khi thiết kế/wiring, điều kiện cục bộ lúc chạy. | Có thể lập kế hoạch tại runtime cho từng message. |
| **Thêm loại hành trình** | Thường sửa/điều chỉnh flow, Router hoặc policy. | Có thể bổ sung một chuỗi bước hợp lệ từ tập endpoint sẵn có; stage mới vẫn cần deploy/config. |
| **Khả năng đọc topology** | Rõ từ Java DSL. | Phải nhìn cả cấu hình endpoint **và** itinerary thực tế. |
| **Độ phức tạp vận hành** | Thường thấp hơn khi số nhánh ít. | Cao hơn do cursor, route metadata và biến thể hành trình. |
| **Lỗi giữa luồng** | Tìm lỗi theo bước tĩnh, call stack/trace. | Cần biết thêm hop hiện tại, kế hoạch đã thực hiện và còn lại. |
| **Retry/recovery** | Theo endpoint/transaction/error flow. | Cũng vậy, nhưng cần bảo đảm không bỏ qua hoặc lặp sai hop. |
| **Quan sát** | Metric theo endpoint, channel, nhánh. | Thêm `routePlanId`, version, current hop và trạng thái itinerary. |
| **An toàn** | Topology khó bị input bên ngoài thay đổi nếu cấu hình đúng. | Cần chống route injection/skip step khi nhận itinerary không tin cậy. |
| **Hiệu năng** | Ít thành phần điều phối hơn trong trường hợp đơn giản. | Có overhead lập kế hoạch/phân giải hop; không tự nhanh hơn. |
| **Persistence** | Không tự durable chỉ vì tĩnh. | Không tự durable chỉ vì slip được gắn trong header. |
| **Khi nên chọn** | Quy trình tương đối ổn định, tuyến ít và dễ khai báo. | Nhiều lộ trình hợp lệ, trình tự thay đổi theo message và được kiểm soát. |

**Không có tiêu chí “flow tĩnh = cứng nhắc, Routing Slip = luôn tốt hơn”.** Một flow tĩnh với Router phân cấp có thể đủ linh hoạt và dễ bảo trì hơn Routing Slip đối với nghiệp vụ chỉ có vài biến thể.

## 5. Ví dụ flow tĩnh với Spring Integration Java DSL

### 5.1. Bài toán minh họa

Ứng dụng nhận `OrderCommand`, validate số tiền, tạo `NormalizedOrder` và trả `Receipt`. Mọi request đi qua cùng ba bước theo topology:

~~~text
Gateway -> orders.input
          -> Filter
          -> Transformer
          -> Service Activator
          -> Gateway reply
~~~

Ví dụ hướng tới **Java 17+, Spring Boot 3.x và Spring Integration 6.x** với dependency `spring-boot-starter-integration`. Các type top-level đặt cùng package; trong dự án thực tế cần tách các type `public` thành file Java riêng.

### 5.2. Mã Java DSL

~~~java
import java.math.BigDecimal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.Gateway;
import org.springframework.integration.annotation.IntegrationComponentScan;
import org.springframework.integration.annotation.MessagingGateway;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;

record OrderCommand(String orderId, BigDecimal amountVnd) {}
record NormalizedOrder(String orderId, BigDecimal amountVnd) {}
record Receipt(String orderId, String status) {}

@MessagingGateway
interface OrderGateway {
    @Gateway(requestChannel = "orders.input")
    Receipt submit(OrderCommand command);
}

@Configuration
@EnableIntegration
@IntegrationComponentScan
class StaticOrderFlowConfiguration {

    @Bean
    IntegrationFlow processOrder() {
        return IntegrationFlow.from("orders.input")
                // Bước 1: validation.
                .filter(OrderCommand.class,
                        order -> order.orderId() != null
                                && !order.orderId().isBlank()
                                && order.amountVnd() != null
                                && order.amountVnd().signum() > 0,
                        spec -> spec.throwExceptionOnRejection(true))
                // Bước 2: chuẩn hóa.
                .transform(OrderCommand.class, order ->
                        new NormalizedOrder(
                                order.orderId().trim(),
                                order.amountVnd()))
                // Bước 3: handler tạo reply.
                .handle(NormalizedOrder.class, (order, headers) ->
                        new Receipt(order.orderId(), "ACCEPTED"))
                .get();
    }
}
~~~

**Cách đọc mã:**

- `@MessagingGateway` tạo cửa vào request–reply cho caller Java.
- `Filter` từ chối amount không hợp lệ bằng exception thay vì để Gateway chờ một reply không bao giờ đến.
- `Transformer` tạo DTO mới, không quyết định channel hay lưu kết quả.
- `Service Activator` mô phỏng bước xử lý và trả `Receipt`. Trong thực tế cần persistence, transaction, retry/error handling phù hợp.
- Không có Routing Slip: thứ tự các endpoint được khai báo trực tiếp trong DSL.

Khi gọi:

~~~java
Receipt receipt = orderGateway.submit(
        new OrderCommand("ORD-101", new BigDecimal("1500000")));
// receipt.status() == "ACCEPTED"
~~~

Thao tác này minh họa đường request–reply đồng bộ. Nó **không** bảo đảm đã ghi DB vì ví dụ chưa có database. Nếu có outbound adapter bất đồng bộ hoặc một handler one-way ở cuối, hợp đồng Gateway cần thay đổi.

### 5.3. Làm gì khi có thêm một nhánh?

Giả sử đơn giá trị từ 10 triệu trở lên phải review. Với flow tĩnh, ta có thể đặt Content-Based Router sau Filter và tách hai flow handler:

~~~text
Filter -> Router(amount >= threshold)
             | normal -> normalize -> persist
             | review -> manualReview -> persist
~~~

Đây vẫn là **topology được khai báo trước**. Nó không phải Routing Slip chỉ vì có Router. Nếu mới có hai lộ trình, Router rõ ràng và test theo nhánh có thể đơn giản hơn việc tạo metadata itinerary cho từng message.

## 6. Ví dụ lập itinerary động: chọn các bước cho từng đơn hàng

### 6.1. Đầu bài

Ta muốn chọn một trong các hành trình sau:

| Đặc điểm đơn | Itinerary | Ý nghĩa |
|---|---|---|
| Nội địa, giá trị thấp | `VALIDATE → PERSIST` | Không cần thêm bước đặc biệt. |
| Nội địa, giá trị cao | `VALIDATE → REVIEW → PERSIST` | Duyệt trước khi lưu ở trạng thái đã được xác nhận. |
| Quốc tế, giá trị thấp | `VALIDATE → COMPLIANCE → PERSIST` | Kiểm tra tuân thủ. |
| Quốc tế, giá trị cao | `VALIDATE → COMPLIANCE → REVIEW → PERSIST` | Cả kiểm tra tuân thủ và duyệt giá trị. |

Điểm khác biệt so với sơ đồ flow tĩnh là **một planner tạo danh sách các hop cho từng request**, thay vì ép message đi qua tất cả nhánh rồi đặt Filter “bỏ qua khi không cần”.

### 6.2. Java thuần mô tả route planner

Đoạn mã sau là **mô hình dữ liệu và chính sách itinerary của ứng dụng**. Nó dùng được để test độc lập, nhưng **không phải đoạn cấu hình hoàn chỉnh để kích hoạt Routing Slip tích hợp sẵn của Spring Integration**:

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Set;

enum Stage {
    VALIDATE, COMPLIANCE, REVIEW, PERSIST
}

record WorkflowOrder(
        String orderId,
        String market,
        BigDecimal amountVnd) {}

record RoutePlan(
        String policyVersion,
        List<Stage> hops) {

    RoutePlan {
        Objects.requireNonNull(policyVersion, "policyVersion");
        Objects.requireNonNull(hops, "hops");
        hops = List.copyOf(hops); // Chụp danh sách bất biến.
        if (hops.isEmpty()) {
            throw new IllegalArgumentException("Empty route");
        }
    }
}

final class OrderRoutePlanner {
    private static final BigDecimal REVIEW_THRESHOLD =
            new BigDecimal("10000000");
    private static final Set<String> MARKETS = Set.of("VN", "INTL");

    RoutePlan plan(WorkflowOrder order) {
        if (order == null
                || order.orderId() == null
                || order.orderId().isBlank()
                || order.market() == null
                || !MARKETS.contains(order.market())
                || order.amountVnd() == null
                || order.amountVnd().signum() <= 0) {
            throw new IllegalArgumentException("Invalid workflow order");
        }

        List<Stage> steps = new ArrayList<>();
        steps.add(Stage.VALIDATE);

        if ("INTL".equals(order.market())) {
            steps.add(Stage.COMPLIANCE);
        }
        if (order.amountVnd().compareTo(REVIEW_THRESHOLD) >= 0) {
            steps.add(Stage.REVIEW);
        }

        steps.add(Stage.PERSIST);
        return new RoutePlan("order-routing-v1", steps);
    }
}
~~~

**Giải thích:**

- Planner chấp nhận chỉ hai thị trường **đã được phép**: `VN` và `INTL`.
- Số tiền được giả định **đã chuẩn hóa sang VND** trước khi so sánh; production không dùng ngưỡng VND trực tiếp cho payload USD/EUR chưa quy đổi.
- `VALIDATE` và `PERSIST` là các bước bắt buộc; `COMPLIANCE` và `REVIEW` có điều kiện.
- `List.copyOf` tránh caller sửa lộ trình sau khi đã lập.
- `policyVersion` giúp audit lý do vì sao request cũ đi theo một itinerary khác request mới.
- Tập `Stage` là enum có giới hạn, không dùng tên channel thô từ HTTP header chưa xác thực.

Ví dụ gọi planner:

~~~java
OrderRoutePlanner planner = new OrderRoutePlanner();

RoutePlan vn = planner.plan(new WorkflowOrder(
        "ORD-1", "VN", new BigDecimal("2000000")));
// [VALIDATE, PERSIST]

RoutePlan intlHigh = planner.plan(new WorkflowOrder(
        "ORD-2", "INTL", new BigDecimal("12500000")));
// [VALIDATE, COMPLIANCE, REVIEW, PERSIST]
~~~

### 6.3. Cursor và nguyên tắc chỉ tiến sau khi bước hiện tại hoàn tất

Trong một Routing Slip, **việc đi đến hop kế tiếp không chỉ là tăng index tùy tiện**. Cần biết bước hiện tại có hoàn tất theo contract chưa. Đoạn Java độc lập sau minh họa một cursor an toàn ở mức thuật toán:

~~~java
record RouteProgress(RoutePlan plan, int nextIndex) {
    RouteProgress {
        if (plan == null || nextIndex < 0
                || nextIndex > plan.hops().size()) {
            throw new IllegalArgumentException("Invalid cursor");
        }
    }

    boolean done() {
        return nextIndex == plan.hops().size();
    }

    Stage current() {
        if (done()) {
            throw new IllegalStateException("Route already complete");
        }
        return plan.hops().get(nextIndex);
    }

    RouteProgress complete(Stage finishedStage) {
        if (done() || current() != finishedStage) {
            throw new IllegalStateException(
                    "Cannot skip or repeat route step");
        }
        return new RouteProgress(plan, nextIndex + 1);
    }
}
~~~

Mô phỏng:

~~~java
RouteProgress progress = new RouteProgress(intlHigh, 0);
// current() == VALIDATE

progress = progress.complete(Stage.VALIDATE);
// current() == COMPLIANCE

progress = progress.complete(Stage.COMPLIANCE);
// current() == REVIEW

progress = progress.complete(Stage.REVIEW);
progress = progress.complete(Stage.PERSIST);
// progress.done() == true
~~~

**Cảnh báo quan trọng:** `RouteProgress` chỉ là ví dụ học thuật về cursor. Không dùng nó để thay thế cấu trúc header và thuật toán điều phối của Spring Integration. Cơ chế Routing Slip thực của framework có API, quy tắc phân giải hop và hành vi chuyển tiếp riêng; cần cấu hình phù hợp với phiên bản đang chạy. Nếu tự xây dispatcher bên trên `RouteProgress` mà không có persistence, concurrency control, timeout, transaction và recovery, ta đã tự phát triển một workflow engine đơn giản nhưng thiếu những bảo đảm quan trọng.

### 6.4. Ánh xạ Stage sang endpoint được phép

Planner nên trả **định danh bước thuộc danh sách cho phép**. Lớp integration chịu trách nhiệm ánh xạ thành channel hoặc endpoint Spring Integration:

| Stage đã xác thực | Channel/endpoint dự kiến | Vai trò |
|---|---|---|
| `VALIDATE` | `orders.validate` | Kiểm tra hợp đồng dữ liệu. |
| `COMPLIANCE` | `orders.compliance` | Xác minh tuân thủ từ nguồn tin cậy. |
| `REVIEW` | `orders.review` | Xử lý bước phê duyệt. |
| `PERSIST` | `orders.persist` | Lưu và tạo kết quả cuối. |

Nơi giải quyết danh sách hop phải có **allowlist**, kiểm tra channel tồn tại và thứ tự hợp lệ. Tên stage có thể đổi ánh xạ mà không thay policy nghiệp vụ, nhưng chỉ khi contract, version và khả năng phục hồi tương thích.

Các bước phê duyệt và kiểm tra ở bảng này là **minh họa**. Không được cho một client tự đặt `COMPLIANCE=PASS` hoặc sửa `nextIndex` để đi thẳng đến `PERSIST`.

## 7. Sử dụng Routing Slip với Spring Integration: điều cần hiểu

### 7.1. Không đồng nhất header tự đặt với Routing Slip chuẩn

Spring Integration có hỗ trợ Routing Slip như một phần của khả năng điều phối message. Khi cấu hình theo đúng API framework, routing-slip metadata mô tả các đích/bước cần đi qua và trạng thái tiến triển; hạ tầng có thể dùng metadata đó khi xác định đích chuyển tiếp.

**Hai đoạn code khác nhau:**

~~~java
// Header tùy biến của ứng dụng: chỉ chứa dữ liệu.
MessageBuilder.withPayload(order)
        .setHeader("routePlan", List.of(
                "orders.validate", "orders.persist"))
        .build();
~~~

~~~text
Routing Slip của Spring Integration:
  - Cần khai báo bằng cơ chế header/processor hỗ trợ
    Routing Slip của framework theo đúng phiên bản.
  - Cần có endpoint/channel được phép và phân giải được.
  - Mỗi hop phải chuyển tiếp message theo hợp đồng thích hợp.
  - Hạ tầng quản lý thông tin điều hướng của slip,
    không chỉ đọc một header tùy ý tên "routePlan".
~~~

Đoạn `setHeader("routePlan", ...)` **không tự khiến Spring Integration điều phối message**. Nó chỉ tạo metadata do ứng dụng định nghĩa. Tránh đặt một tên header rồi khẳng định framework tự chạy qua danh sách đó.

Khi triển khai Routing Slip thực tế, nên tra cứu API ở đúng phiên bản `spring-integration-core` đang dùng, đặc biệt các khái niệm liên quan **Routing Slip header value processor, route strategy, output channel và reply-producing endpoint**. Không sao chép cú pháp DSL từ phiên bản khác nếu chưa xác minh.

### 7.2. Vì sao reply-producing endpoint quan trọng?

Với một số cách triển khai Routing Slip, message chỉ có thể tới bước kế tiếp khi endpoint hiện tại **phát ra message kết quả để tiếp tục**. Nếu dùng một handler một chiều chỉ thực hiện side effect và kết thúc, hành trình có thể không còn message để chuyển sang hop sau.

~~~text
Slip: [validate, enrich, persist]

validate nhận Message<Order>
   -> trả Message<Order> hoặc payload hợp lệ
   -> slip tiếp tục tới enrich

enrich nhận Order
   -> trả EnrichedOrder
   -> slip tiếp tục tới persist

persist nhận EnrichedOrder
   -> ghi DB và trả Receipt / kết quả cuối theo contract
~~~

Ngược lại:

~~~java
// Minh họa một handler kết thúc một chiều:
.handle(message -> {
    saveToDatabase(message.getPayload());
    // Không phát reply để đi tiếp.
})
~~~

Nếu còn hop sau handler này, không được tự suy luận rằng Routing Slip vẫn chạy tiếp. Khi thiết kế một itinerary, **đặt rõ input/output schema và trách nhiệm phát message của từng bước**, đặc biệt với outbound adapter một chiều.

### 7.3. Explicit output channel có thể ảnh hưởng điều hướng

Trong flow tĩnh, một endpoint thường có output channel cụ thể được khai báo trong cấu hình. Routing Slip lại muốn điều hướng dựa trên itinerary. Nếu endpoint vừa có **output channel cố định** vừa mang routing-slip metadata, thứ tự ưu tiên phân giải đích phải được hiểu theo loại endpoint và cấu hình framework.

Đừng giả định “gắn Routing Slip sẽ tự ghi đè mọi `outputChannel` tĩnh”. Nếu output channel tĩnh luôn được dùng, message có thể bỏ qua ý định ở slip; nếu endpoint không tạo reply, slip cũng không có điểm để tiếp tục. Kiểm thử **một message thật đi qua tất cả các hop** ở phiên bản Spring Integration đã chọn là cách xác nhận tốt nhất.

### 7.4. Ranh giới thread và transport

Khi itinerary đi qua `DirectChannel` trong cùng thread, việc quan sát thứ tự khá trực quan. Với `ExecutorChannel`, `QueueChannel` hoặc message broker, phải xem xét:

- Thứ tự xử lý và bước hiện tại có được giữ ổn định?
- Header Routing Slip có được truyền qua adapter/converter hay bị lọc?
- Reply channel hoặc transport return-address có hợp lệ không?
- Handler đang chạy dở gặp timeout thì cursor và trạng thái nghiệp vụ sẽ ra sao?
- Retry từ broker có thể làm một hop chạy lại không?

**Routing Slip không tự là cơ chế persistence.** Nếu process chết khi message đang nằm trong queue in-memory hoặc giữa hai lần publish/ack, lộ trình có thể không tiếp tục đúng ý nếu không có store/broker và idempotency.

## 8. Những lỗi riêng của Routing Slip

### 8.1. Không thể phân giải một hop

Một itinerary có thể chứa:

~~~text
["orders.validate", "orders.compliance", "orders.persist"]
~~~

nhưng `orders.compliance` chưa có bean/channel trong application context, đã bị đổi tên hoặc endpoint subscribe chưa khởi động. Đây là các lỗi khác nhau:

| Loại lỗi | Ví dụ | Phản ứng cần có |
|---|---|---|
| **Hop không nằm trong allowlist** | Caller gửi `orders.skipCompliance`. | Từ chối ngay khi lập/nhận itinerary, ghi audit phù hợp. |
| **Đích không tồn tại** | Bean `orders.compliance` không được đăng ký. | Báo lỗi cấu hình; không tự bỏ qua hop quan trọng. |
| **Channel có nhưng không có subscriber** | `DirectChannel` còn tồn tại, handler đã stop. | Dispatch failure/timeout theo contract, không coi hop đã hoàn tất. |
| **Queue đầy** | Hop tiếp theo dùng `QueueChannel` capacity hữu hạn. | Bounded wait, backpressure, retry hoặc recovery có kiểm soát. |
| **Handler không phát reply** | Outbound adapter một chiều là hop giữa. | Kiểm tra lại hợp đồng chuyển tiếp; không đánh dấu đã hoàn thành tất cả. |
| **Header itinerary bị mất** | Qua HTTP/Kafka/JMS adapter nhưng không mapping. | Dừng/fail closed hoặc tái tạo từ nguồn đáng tin, không đoán đường đi. |

Routing Slip cho phép **lộ trình khác nhau**, đồng thời tăng số trường hợp cần kiểm soát. Flow tĩnh cũng có lỗi channel hoặc handler, nhưng đường đi cố định giúp sớm phát hiện một số lỗi cấu hình.

### 8.2. Lỗi tại hop giữa: tiếp tục, thử lại hay hủy hành trình?

Giả sử slip có bốn hop:

~~~text
VALIDATE -> COMPLIANCE -> REVIEW -> PERSIST
~~~

và `COMPLIANCE` timeout. Ba hành động có thể được đề xuất nhưng không tương đương:

1. **Retry COMPLIANCE:** nếu là lỗi tạm thời và bước có idempotency/backoff phù hợp.
2. **Chuyển sang recovery:** ví dụ `WAITING_FOR_VERIFICATION` hoặc quarantine có lưu trạng thái và deadline.
3. **Fail toàn request:** trả lỗi hoặc trạng thái chưa thể xử lý; không tự nhảy tới `REVIEW` và `PERSIST`.

**Không được tăng cursor qua một bước bắt buộc chỉ vì nó lỗi.** Việc bỏ qua kiểm tra tuân thủ rồi vẫn persist như một đơn đã đạt chuẩn là sai nghiệp vụ, dù công nghệ có cho phép chuyển channel tiếp.

### 8.3. Retry cả itinerary có thể nhân đôi side effect

~~~text
VALIDATE   -> success
COMPLIANCE -> success
REVIEW     -> success
PERSIST    -> timeout sau khi DB có thể đã commit
~~~

Nếu restart hành trình từ `VALIDATE` mà không có trạng thái và idempotency, ta có thể làm lại các bước đã có tác động ngoài. Đặc biệt, `PERSIST` timeout không chứng minh việc ghi DB thất bại. Vì vậy:

- Gắn **business operation ID** ổn định, như `orderId` + `operationType` hoặc `workflowAttemptId` theo contract.
- Mỗi hop có **idempotency key** nếu phát sinh side effect; không chỉ dùng `MessageHeaders.ID` vì message mới có thể mang UUID khác.
- Lưu bằng chứng hop đã hoàn tất ở nơi bền vững nếu cần recovery qua crash.
- Khi kết quả không chắc chắn, **reconcile** trạng thái hệ thống đích trước khi thực hiện lại.
- Phân biệt **retry hop hiện tại** với **replan itinerary** khi policy thay đổi.

Routing Slip không tự bảo đảm exactly-once trên nhiều database, broker và HTTP service. Các cơ chế transaction, outbox, consumer deduplication và compensation cần được thiết kế riêng.

### 8.4. Khi Gateway timeout trước khi slip chạy xong

Nếu dùng một `@MessagingGateway` để chờ kết quả từ một hành trình nhiều bước:

~~~text
HTTP client
  -> Gateway reply timeout: 5 s
        -> compliance HTTP timeout: 4 s
        -> review processing: 3 s
        -> persist: 1 s
~~~

thì deadline Gateway có thể hết trước khi message tới hop cuối. Caller đã nhận timeout **không có nghĩa** tất cả hop đều tự bị hủy. Một message bất đồng bộ có thể còn tiếp tục xử lý, tạo reply đến muộn và side effect.

Thiết kế cần nêu rõ:

1. **Deadline tổng** và deadline của từng downstream.
2. Trạng thái gửi trả khi chưa thể kết luận hoàn tất, như `PENDING` hoặc lỗi có thể tra cứu lại.
3. Cơ chế **late reply** và cleanup.
4. Nguyên tắc retry của client để tránh tạo hai workflow cho một đơn.
5. Nơi lưu trạng thái nếu công việc dài hơn một request HTTP.

Với bước phê duyệt kéo dài hàng giờ hoặc nhiều ngày, Routing Slip đơn thuần thường **không đủ** làm workflow orchestrator; cần state persistence, timeout, resume, compensation và operator controls theo yêu cầu.

## 9. Không tạo vòng lặp và không để itinerary quá dài

### 9.1. Những chuỗi có nguy cơ

Một itinerary do policy sai hoặc input giả mạo có thể chứa cùng một hop nhiều lần:

~~~text
VALIDATE -> REVIEW -> VALIDATE -> REVIEW -> ...
~~~

Hoặc một route strategy ở hop giữa có thể trả về channel vừa xử lý, gây chu trình ngay cả khi danh sách đầu không lộ vòng lặp. Với `DirectChannel`, điều này có thể tạo dispatch đệ quy; với executor/queue có thể tăng tải đến khi quá sức.

### 9.2. Các bất biến an toàn

**Một route plan hợp lệ** cho ví dụ đơn hàng nên thỏa:

- `VALIDATE` đứng đầu, `PERSIST` đứng cuối.
- `COMPLIANCE` chỉ được phép cho thị trường `INTL`.
- `REVIEW` chỉ được phép khi cần duyệt theo policy tin cậy.
- Không stage nào xuất hiện lặp nếu quy trình không có vòng lặp hợp lệ.
- Có giới hạn **maxHops**, ví dụ 8 theo chính sách của ứng dụng.
- Mọi stage thuộc một allowlist đã biết, và mọi output channel có consumer/contract hợp lệ.
- Cursor chỉ được tăng sau khi hoàn tất một bước đúng vị trí.
- Mỗi attempt có deadline và trạng thái lỗi để tránh loop vô hạn.

Minh họa bộ kiểm tra route plan bằng Java thuần:

~~~java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

final class RoutePlanValidator {
    private static final int MAX_HOPS = 8;

    void validate(RoutePlan plan) {
        List<Stage> hops = plan.hops();

        if (hops.size() > MAX_HOPS
                || hops.get(0) != Stage.VALIDATE
                || hops.get(hops.size() - 1) != Stage.PERSIST) {
            throw new IllegalArgumentException(
                    "Invalid itinerary boundaries");
        }

        Set<Stage> unique = new HashSet<>(hops);
        if (unique.size() != hops.size()) {
            throw new IllegalArgumentException("Duplicate hop");
        }
    }
}
~~~

Đây mới kiểm tra một số **bất biến cấu trúc**, chưa kiểm tra có phải đơn quốc tế hay bước review có bắt buộc không. Với chính sách nghiêm ngặt, validator cần nhận thêm dữ liệu nghiệp vụ đã xác thực hoặc kết quả của planner để kiểm tra **không bỏ bước bắt buộc**. Đồng thời, không nên lấy `MAX_HOPS=8` làm giới hạn mặc định của Spring Integration; đây là con số minh họa do ứng dụng chọn.

### 9.3. Cẩn thận khi route plan thay đổi giữa lúc message đang chạy

Giả sử:

~~~text
T1: policy-v1 -> validate, compliance, persist
T2: đã hoàn tất validate
T3: hệ thống deploy policy-v2 -> validate, fraud, compliance, persist
T4: message tiếp tục chạy
~~~

Có nên tự thay itinerary giữa đường để áp dụng `policy-v2`? Không mặc định. Thay đổi giữa chừng có thể bỏ hoặc chạy lại bước, làm hỏng replay và audit. Nên định nghĩa:

- **Plan snapshot:** đóng băng lộ trình và version lúc bắt đầu.
- **Replanning checkpoint:** chỉ thay policy ở điểm được cho phép, có migration và audit.
- **Compatibility:** các stage cũ phải còn được hỗ trợ trong thời gian có message dở.
- **Recovery:** message đang chờ qua broker/store phải đọc được metadata plan của phiên bản cũ.

Flow tĩnh cũng cần chiến lược tương thích khi deploy, nhưng Routing Slip làm vấn đề **version của itinerary trên từng message** hiện hữu hơn.

## 10. Routing Slip, Router phân cấp, Recipient List và Scatter–Gather

### 10.1. Cùng là “route” nhưng khác câu hỏi

~~~mermaid
flowchart TB
    Q{Nhu cầu}
    Q -->|Chọn một nhánh lúc này| R[Content-Based Router]
    Q -->|Nhiều quyết định theo cây| H[Hierarchical Router]
    Q -->|Theo một chuỗi bước khác nhau| S[Routing Slip]
    Q -->|Phát cho nhiều recipient| L[Recipient List / Publish–Subscribe]
    Q -->|Gửi nhiều yêu cầu và chờ kết quả| G[Scatter–Gather / Aggregator]
~~~

| Câu hỏi thiết kế | Mẫu phù hợp | Điều cần bổ sung |
|---|---|---|
| “Đơn nội địa đi nhánh A, đơn quốc tế đi nhánh B?” | Content-Based Router. | Channel mapping, default/error route. |
| “Trong nhánh quốc tế, tiếp tục chia mức độ rủi ro?” | Router phân cấp. | Quan sát từng tầng, xử lý nhánh không có consumer. |
| “Mỗi message có itinerary các bước riêng?” | Routing Slip. | Plan/cursor, whitelisting, reply-producing steps, retry/recovery. |
| “Một event gửi cùng lúc tới audit, email, analytics?” | Recipient List hoặc Publish–Subscribe. | Delivery/retry/error handling từng nhánh. |
| “Phải đủ fraud và inventory mới xác nhận đơn?” | Scatter–Gather/Aggregator. | Correlation, expected recipients, release, timeout. |

Một flow thực tế có thể **kết hợp** các mẫu. Ví dụ Routing Slip đưa message đến hop `validate`, rồi một Router tại đó chọn nhánh kiểm tra chi tiết. Nhưng càng nhiều cơ chế định tuyến, việc xác minh thứ tự, điều kiện bỏ qua và hành vi retry càng quan trọng.

### 10.2. Routing Slip là đường đi tuần tự, không tự fan-out

Nếu itinerary là:

~~~text
validate -> fraud -> persist
~~~

điều đó có nghĩa **đi qua lần lượt các bước** theo thiết kế, không tự tạo ba message chạy đồng thời. Nếu muốn Fraud và Inventory chạy song song, cần một fan-out ở bước phù hợp và có quy tắc tổng hợp nếu cần kết quả chung. Đừng dùng một danh sách stage tuần tự rồi mong framework tự chạy parallel và gather.

### 10.3. Routing Slip không thay thế state machine cho quy trình dài ngày

Việc duyệt tín dụng trong nhiều ngày có thể có trạng thái `WAITING_FOR_APPROVAL`, `APPROVED`, `REJECTED`, `EXPIRED`, thêm yêu cầu compensation hoặc operator override. Đó là bài toán **quy trình trạng thái bền vững**. Routing Slip có thể hỗ trợ chỉ dẫn endpoint ở các giai đoạn kỹ thuật, nhưng không tự cung cấp persistence, timers, signal handling, authorization và khả năng khôi phục toàn bộ một workflow dài hạn.

## 11. Quan sát Routing Slip so với flow tĩnh

### 11.1. Flow tĩnh: biết topology từ cấu hình

Với flow tĩnh:

~~~text
orders.input -> filter -> transform -> handler
~~~

Khi điều tra, có thể dựa vào sơ đồ cấu hình, channel và metric của từng endpoint để biết một message **dự kiến** đi qua đâu. Nếu không có nhánh động, tập đường đi khá nhỏ.

### 11.2. Routing Slip: cần biết cả topology và itinerary thực tế

Với Routing Slip, sơ đồ tổng thể chỉ cho thấy **những stage có thể chạy**; muốn giải thích một request phải có **route plan đã chọn** và **hop đã thực hiện**.

~~~text
event=ROUTE_PLANNED orderId=ORD-2002 traceId=T-2002
  planVersion=order-routing-v1
  hops=[VALIDATE,COMPLIANCE,REVIEW,PERSIST]

event=HOP_STARTED orderId=ORD-2002 traceId=T-2002
  planVersion=order-routing-v1 hopIndex=1 hop=COMPLIANCE

event=HOP_FAILED orderId=ORD-2002 traceId=T-2002
  hopIndex=1 hop=COMPLIANCE reason=HTTP_TIMEOUT retryable=true

event=HOP_RETRIED orderId=ORD-2002 traceId=T-2002
  hopIndex=1 hop=COMPLIANCE attempt=2
~~~

Đây là **schema log ứng dụng đề xuất**, không phải output mặc định của Spring Integration. Những thông tin quan trọng:

| Field | Giải thích |
|---|---|
| `orderId` / business ID | Truy nguyên nghiệp vụ xuyên message mới. |
| `traceId` | Liên kết log/span giữa các endpoint và dịch vụ. |
| `planVersion` | Biết quy tắc dùng để chọn itinerary. |
| `planId` / workflow attempt ID | Phân biệt các lần thực hiện của cùng đơn. |
| `hopIndex` và `hop` | Xác định vị trí lỗi và bước đang chờ. |
| `attempt` | Phân biệt retry của hop với một bước mới. |
| `outcome` / `failureReason` | Biết đã completed, skipped có phép, failed hay waiting. |

Không log toàn bộ payload chứa dữ liệu nhạy cảm hoặc dùng `orderId`, `traceId` làm metric label có cardinality cao.

### 11.3. Message History khác itinerary

**Message History** có thể ghi dấu các component Spring Integration đã đi qua nếu được bật. Nhưng:

- **Itinerary** thể hiện các bước **dự kiến**.
- **Message History** thể hiện những component **đã được framework tracking**.
- **Business outcome log** thể hiện bước có thật sự xử lý, ghi nhận hoặc commit thành công không.
- **Distributed trace** giúp nối span qua thread/process nếu propagation được cấu hình.

Không dùng Message History làm thay thế một **durable audit trail** cho việc phê duyệt hay xác minh tuân thủ. Một hop có thể xuất hiện trong history dù side effect downstream sau đó fail.

### 11.4. Metrics đề xuất

| Chỉ số | Flow tĩnh | Routing Slip |
|---|---|---|
| Input/processed rate từng endpoint | Có | Có |
| Error/retry/timeout rate từng endpoint | Có | Có |
| Queue depth, executor saturation | Có nếu dùng async | Có nếu dùng async |
| Số message theo itinerary version | Không bắt buộc | Nên theo dõi |
| Hop count trung bình/tối đa | Ít cần nếu topology đơn giản | Hữu ích để phát hiện plan phình ra |
| Route-plan validation failures | Ít liên quan | Nên theo dõi |
| Stuck routes / oldest unfinished itinerary | Theo workflow nếu có | Quan trọng nếu cần resume |
| Hop transition failures | Theo dispatch/handler | Quan trọng vì có nhiều đích kế tiếp |

Các metric theo `hop` và `planVersion` nên dùng tập giá trị có giới hạn. Giữ business/trace ID trong log/tracing có chính sách lưu trữ, không dùng làm label.

## 12. Kiểm thử hai phương án

### 12.1. Unit test cho route planner

Với `OrderRoutePlanner` và `RoutePlan` ở phần 6, có thể dùng JUnit 5 để xác nhận hành trình chính xác theo từng loại đơn:

~~~java
import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OrderRoutePlannerTest {
    private final OrderRoutePlanner planner =
            new OrderRoutePlanner();

    @Test
    void domesticLowValueHasTwoSteps() {
        RoutePlan plan = planner.plan(
                new WorkflowOrder("O-1", "VN",
                        new BigDecimal("9999999")));

        assertEquals(
                List.of(Stage.VALIDATE, Stage.PERSIST),
                plan.hops());
    }

    @Test
    void domesticAtThresholdRequiresReview() {
        RoutePlan plan = planner.plan(
                new WorkflowOrder("O-2", "VN",
                        new BigDecimal("10000000")));

        assertEquals(
                List.of(Stage.VALIDATE, Stage.REVIEW, Stage.PERSIST),
                plan.hops());
    }

    @Test
    void internationalLowValueRequiresCompliance() {
        RoutePlan plan = planner.plan(
                new WorkflowOrder("O-3", "INTL",
                        new BigDecimal("5000000")));

        assertEquals(
                List.of(Stage.VALIDATE, Stage.COMPLIANCE,
                        Stage.PERSIST),
                plan.hops());
    }

    @Test
    void internationalHighValueRequiresBothChecks() {
        RoutePlan plan = planner.plan(
                new WorkflowOrder("O-4", "INTL",
                        new BigDecimal("25000000")));

        assertEquals(
                List.of(Stage.VALIDATE, Stage.COMPLIANCE,
                        Stage.REVIEW, Stage.PERSIST),
                plan.hops());
    }

    @Test
    void unknownMarketDoesNotProduceAnItinerary() {
        assertThrows(IllegalArgumentException.class, () ->
                planner.plan(new WorkflowOrder(
                        "O-5", "UNKNOWN",
                        new BigDecimal("3000000"))));
    }

    @Test
    void invalidAmountDoesNotProduceAnItinerary() {
        assertThrows(IllegalArgumentException.class, () ->
                planner.plan(new WorkflowOrder(
                        "O-6", "VN", BigDecimal.ZERO)));
    }
}
~~~

**Kết quả test chỉ xác nhận policy chọn itinerary**, không xác nhận Spring Integration đã dispatch message theo itinerary. Để kiểm thử cơ chế Routing Slip thật, cần cấu hình header processor/route strategy của framework và test endpoint chuyển tiếp bằng đúng phiên bản đang sử dụng.

### 12.2. Unit test cursor không được bỏ bước

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RouteProgressTest {

    @Test
    void completesAllHopsInDeclaredOrder() {
        RoutePlan plan = new RoutePlan("v1", List.of(
                Stage.VALIDATE, Stage.COMPLIANCE, Stage.PERSIST));
        RouteProgress progress = new RouteProgress(plan, 0);

        assertEquals(Stage.VALIDATE, progress.current());
        progress = progress.complete(Stage.VALIDATE);

        assertEquals(Stage.COMPLIANCE, progress.current());
        progress = progress.complete(Stage.COMPLIANCE);

        assertEquals(Stage.PERSIST, progress.current());
        progress = progress.complete(Stage.PERSIST);
        assertTrue(progress.done());
    }

    @Test
    void cannotSkipRequiredComplianceHop() {
        RoutePlan plan = new RoutePlan("v1", List.of(
                Stage.VALIDATE, Stage.COMPLIANCE, Stage.PERSIST));
        RouteProgress progress = new RouteProgress(plan, 1);

        assertThrows(IllegalStateException.class, () ->
                progress.complete(Stage.PERSIST));
        assertFalse(progress.done());
    }

    @Test
    void duplicateHopIsRejectedByExampleValidator() {
        RoutePlan plan = new RoutePlan("v1", List.of(
                Stage.VALIDATE, Stage.REVIEW,
                Stage.REVIEW, Stage.PERSIST));

        assertThrows(IllegalArgumentException.class, () ->
                new RoutePlanValidator().validate(plan));
    }
}
~~~

Một lần nữa, đây là test thuật toán cursor **do bài học tự định nghĩa**, không phải test chi tiết implementation nội bộ của framework.

### 12.3. Integration test cho flow tĩnh

Với `StaticOrderFlowConfiguration` ở phần 5, dùng Spring Test và JUnit 5:

~~~java
import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.messaging.MessagingException;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(StaticOrderFlowConfiguration.class)
class StaticOrderFlowTest {

    @Autowired
    private OrderGateway gateway;

    @Test
    void validOrderPassesStaticPipeline() {
        Receipt receipt = gateway.submit(
                new OrderCommand(" ORD-7 ",
                        new BigDecimal("2000000")));

        assertEquals("ORD-7", receipt.orderId());
        assertEquals("ACCEPTED", receipt.status());
    }

    @Test
    void invalidAmountIsRejectedByFilter() {
        assertThrows(MessagingException.class, () ->
                gateway.submit(new OrderCommand(
                        "ORD-8", BigDecimal.ZERO)));
    }
}
~~~

Test này chứng minh Filter/Transformer/handler của **flow tĩnh** hoạt động trong cấu hình ví dụ. Chưa có database, transaction, external gateway hoặc retry. Loại exception ở test có thể phụ thuộc cách framework và gateway bọc lỗi; khi chạy trên một phiên bản cụ thể, kiểm tra cả cause nếu cần.

### 12.4. Ma trận integration test cho Routing Slip thực

Khi bổ sung cấu hình routing slip thực tế bằng API đúng phiên bản Spring Integration, cần test thêm:

| Trường hợp | Điều cần chứng minh |
|---|---|
| Plan `VALIDATE → PERSIST` | Chỉ hai hop tương ứng được nhận; hop `COMPLIANCE` và `REVIEW` không chạy. |
| Plan `VALIDATE → COMPLIANCE → REVIEW → PERSIST` | Thứ tự các hop đúng, không bỏ và không chạy thêm. |
| Một hop không tồn tại | Lỗi được báo rõ, message không tự nhảy sang bước sau. |
| Endpoint giữa là one-way handler | Theo contract, phát hiện hành trình không tiếp tục; không trả “complete”. |
| Một hop ném exception | Error/retry policy được áp dụng ở đúng hop, cursor không bỏ qua bước bắt buộc. |
| Reply-producing handler tạo message mới | Metadata cần thiết để tiếp tục hành trình được giữ hoặc chuyển đúng. |
| Adapter mất routing-slip metadata | Có lỗi/recovery rõ; không chọn route mặc định mù. |
| Hop sau là `QueueChannel` | Có poller/consumer, timeout/backpressure và tình huống queue đầy được test. |
| Một bước được retry sau timeout | Không tạo side effect trùng nếu lần đầu có thể đã commit. |
| Gateway timeout giữa đường | Late outcome được quản lý, request không bị coi completed sớm. |
| Plan từ client có stage lạ | Bị từ chối bởi allowlist, không resolve arbitrary bean names. |
| Route có cycle hoặc quá nhiều hop | Guard về hop limit và chính sách loop thực sự có hiệu lực. |
| Deploy đổi plan version khi có message chờ | Hành trình cũ không bị thay đổi ngoài ý muốn. |

Với các bước bất đồng bộ, dùng **latch/await có timeout hữu hạn** thay vì `Thread.sleep` để phỏng đoán trạng thái. Không chạy một bài test loop nguy hiểm mà không có max-steps/deadline và cơ chế dừng; một vòng lặp đồng bộ có thể cạn stack rất nhanh.

## 13. Quyết định chọn flow tĩnh hay Routing Slip

### 13.1. Một cây quyết định

~~~mermaid
flowchart TD
    Q{Các message có gần như cùng trình tự?}
    Q -->|Có| STATIC[Flow tĩnh]
    Q -->|Không| V{Chỉ vài nhánh lựa chọn rõ ràng?}
    V -->|Có| ROUTER[Flow tĩnh + Router/Filter]
    V -->|Không| W{Có nhiều itinerary hợp lệ theo từng message?}
    W -->|Có| SLIP[Cân nhắc Routing Slip]
    W -->|Không| STATIC
    SLIP --> LONG{Quy trình chờ ngoài nhiều giờ/ngày?}
    LONG -->|Có| ENGINE[Workflow/state machine bền vững]
    LONG -->|Không| CHECK[Kiểm soát plan, hop, retry, security, metrics]
~~~

Không cần chọn Routing Slip cho mọi flow có hai hoặc ba điều kiện. Độ phức tạp bổ sung phải có lợi ích rõ về khả năng thay đổi trình tự công việc và giảm phụ thuộc giữa planner với endpoint.

### 13.2. Đánh giá theo yêu cầu

| Yêu cầu | Gợi ý | Vì sao |
|---|---|---|
| Luôn validate → transform → persist | Flow tĩnh | Ít indirection, dễ test và quan sát. |
| Hai nhánh normal/review | Router hoặc flow tĩnh có điều kiện | Số nhánh nhỏ, đường đi dễ thể hiện trực tiếp. |
| Quy trình nội địa và quốc tế có hai cây quyết định | Router phân cấp | Mỗi nhánh có quy tắc riêng, wiring vẫn minh bạch. |
| Mỗi request chọn từ hàng chục itinerary hợp lệ theo policy | Routing Slip đáng cân nhắc | Trình tự là dữ liệu theo từng request, có thể tách planner khỏi execution. |
| Event gửi đồng thời tới audit và analytics | Pub/Sub hoặc Recipient List | Fan-out, không phải chuỗi bước nối tiếp. |
| Bắt buộc đủ fraud và inventory để xác nhận | Scatter–Gather/Aggregator | Cần tổng hợp phản hồi chứ không chỉ route theo danh sách. |
| Xét duyệt thủ công kéo dài nhiều ngày | Workflow engine/state machine bền vững | Cần timers, persistence, signals, timeout, compensation. |
| Cần trace, retry và monitoring | Cả hai đều cần | Routing Slip không thay thế error flow hoặc observability. |

### 13.3. Chi phí vận hành cần cộng vào quyết định

Routing Slip có thể giảm số lượng nhánh khai báo tĩnh, nhưng thường thêm chi phí:

- Quy trình phê duyệt và version của route planner.
- Kiểm soát bảo mật đối với itinerary và destination.
- Logging/metrics theo hop, route version và route outcome.
- Test tính hợp lệ của mọi tổ hợp itinerary.
- Recovery khi message đã hoàn tất một phần nhưng application crash.
- Khả năng tương thích giữa messages đang chạy và bản deploy mới.
- Xử lý khi một hop đang paused, queue đầy hoặc trả reply muộn.

Nếu không có nguồn lực vận hành những phần này, flow tĩnh với vài Router tường minh thường an toàn và dễ kiểm soát hơn.

## 14. Các sai lầm phổ biến

| Hiểu nhầm | Hậu quả | Cách làm đúng |
|---|---|---|
| “Flow tĩnh không được có Router.” | Tạo Routing Slip không cần thiết. | Flow tĩnh có thể dùng Router/Filter và nhiều nhánh khai báo trước. |
| “Routing Slip là gửi song song đến nhiều recipient.” | Nhầm itinerary tuần tự với fan-out. | Dùng Recipient List/Publish–Subscribe nếu cần nhiều đích cùng nhận. |
| “Gắn header `routePlan` là framework tự route.” | Message không tự chuyển sang hop tiếp theo. | Dùng đúng cơ chế Routing Slip của Spring Integration theo phiên bản. |
| “Routing Slip tạo stage mới từ một string.” | Resolve đích không hợp lệ hoặc nguy cơ route injection. | Stage phải được cấu hình sẵn và nằm trong allowlist. |
| “Routing Slip luôn nhanh hơn flow tĩnh.” | Thêm overhead lập kế hoạch/phân giải hop. | Đo workload, chọn theo độ phức tạp và nhu cầu. |
| “Handler one-way giữa slip vẫn tự gửi tiếp.” | Hành trình dừng trước khi tới hop cuối. | Định nghĩa output/reply của từng endpoint trung gian. |
| “Có outputChannel tĩnh thì slip luôn được ưu tiên.” | Message có thể đi tuyến khác dự kiến. | Hiểu semantics phân giải output của endpoint/framework. |
| “Bước compliance lỗi có thể skip để hoàn thành.” | Vi phạm điều kiện nghiệp vụ. | Không tăng cursor khi chưa đạt điều kiện bắt buộc. |
| “Retry toàn itinerary luôn an toàn.” | Nhân đôi side effect đã commit. | Idempotency, checkpoint/recovery và retry đúng hop. |
| “Routing Slip trong header đồng nghĩa bền vững.” | Mất kế hoạch khi message/process mất. | Store/broker, retention/ack và persistence nếu cần. |
| “Message ID luôn giữ nguyên qua mọi hop.” | Đứt trace sau Transformer/adapter. | Dùng business ID, trace ID và correlation phù hợp. |
| “Có slip thì không cần errorChannel.” | Lỗi không được xử lý hay quan sát. | Thiết kế retry/error/recovery ở mỗi hop theo execution model. |
| “Deploy policy mới nên tự sửa slip đang chạy.” | Hành trình thay đổi không kiểm soát. | Version/snapshot hoặc migration tại checkpoint có audit. |
| “Chỉ cần test planner thì biết routing chạy đúng.” | Chưa kiểm tra dispatch, subscribers, reply, adapter. | Unit test planner và integration test từng hop. |
| “Routing Slip là workflow engine dài hạn.” | Thiếu state/timers/compensation/durable resume. | Dùng orchestration/state machine bổ sung khi cần. |

## 15. Bài tập thực hành

1. **Flow tĩnh:** triển khai `Filter → Transformer → Service Activator` như phần 5. Viết test payload không hợp lệ bị từ chối và payload hợp lệ trả `Receipt`.
2. **Thêm Router:** bổ sung nhánh review cho đơn từ 10 triệu trở lên vào flow tĩnh. Vẽ topology mới và so sánh số endpoint với phương án routing slip.
3. **Route planner:** dùng `OrderRoutePlanner` lập itinerary cho bốn loại đơn. Viết bảng chân trị gồm thị trường, mức tiền, các hop cần chạy.
4. **Cursor:** dùng `RouteProgress` mô phỏng đi từng hop, cố tình complete `PERSIST` khi `COMPLIANCE` chưa hoàn tất để xác minh bị từ chối.
5. **Allowlist:** thêm stage lạ vào một request từ client. Thiết kế cách từ chối trước khi resolve channel và ghi log không tiết lộ dữ liệu nhạy cảm.
6. **Spring Routing Slip thật:** theo tài liệu API phiên bản Spring Integration của dự án, cấu hình routing-slip header/processor và các reply-producing endpoint. Test một message đi qua hai hop, một message đi qua bốn hop.
7. **One-way endpoint:** biến hop giữa thành outbound adapter không có reply. Giải thích vì sao hành trình có thể không tiếp tục và sửa hợp đồng chuyển tiếp.
8. **Lỗi giữa đường:** làm `COMPLIANCE` timeout; chỉ retry hop đó theo policy có giới hạn, không skip đến `PERSIST`.
9. **Duplicate:** giả lập `PERSIST` đã commit nhưng reply mất. Dùng operation ID/idempotency key để ngăn tạo hai đơn khi client retry.
10. **Adapter:** cho message mang slip đi qua broker, kiểm tra metadata được map và khôi phục đúng; không serialize `replyChannel` object nội bộ.
11. **Version:** lập plan theo `policy-v1`, sau đó giả lập deployment `policy-v2` trước khi message hoàn tất. Xác định khi nào kế hoạch được phép đổi.
12. **Observability:** thêm `planVersion`, `hopIndex`, `HOP_STARTED`, `HOP_FAILED`, `HOP_COMPLETED` vào log; tìm đúng hop thất bại từ một trace.
13. **Điều phối dài ngày:** thay bước `REVIEW` bằng chờ một người duyệt trong ba ngày. Đánh giá vì sao cần durable state/timer thay vì chỉ dựa trên một routing-slip header.

### Câu hỏi tự kiểm tra

**Câu 1:** Một flow tĩnh có Content-Based Router chia thành ba nhánh. Nó có tự trở thành Routing Slip không? **Không.** Router chọn đích tại một điểm quyết định; Routing Slip mô tả itinerary các bước của từng message.

**Câu 2:** Nếu một message mang header tùy biến `routePlan=["A","B"]`, Spring Integration có chắc chắn tự chạy A rồi B không? **Không.** Cần dùng cơ chế Routing Slip mà framework hỗ trợ, endpoint/channel hợp lệ và quy tắc chuyển tiếp phù hợp.

**Câu 3:** Một hop giữa xử lý xong side effect nhưng không phát message output. Có thể kết luận slip tiếp tục sang hop kế không? **Không.** Phải kiểm tra hợp đồng reply-producing endpoint và cách framework định tuyến output.

**Câu 4:** Việc thêm Routing Slip có làm message trong QueueChannel in-memory tự bền vững qua restart không? **Không.** Durability phụ thuộc store/broker và cơ chế acknowledgment riêng.

**Câu 5:** Nếu `COMPLIANCE` timeout, có nên bỏ qua để tới `PERSIST` khi hop đó là bước bắt buộc? **Không.** Cần lỗi, retry có giới hạn hoặc recovery; không tự tăng cursor.

**Câu 6:** Một đơn quốc tế giá trị cao theo ví dụ sẽ có itinerary nào? **VALIDATE → COMPLIANCE → REVIEW → PERSIST**, với điều kiện dữ liệu đã được xác thực.

**Câu 7:** Khi hai nhánh fraud và inventory phải chạy song song và trả đủ kết quả, Routing Slip tuần tự có phải pattern phù hợp nhất không? **Không hẳn.** Cân nhắc Scatter–Gather/Aggregator với correlation, release strategy và timeout.

**Câu 8:** Route planner được unit test đầy đủ có đủ chứng minh production flow đã đi đúng channel không? **Chưa.** Cần integration test cho routing-slip processor, channel, endpoint, metadata và failure modes.

## 16. Kết luận

**Flow tĩnh** phù hợp khi trình tự xử lý tương đối ổn định, topology có thể diễn tả rõ bằng Java DSL và các Router/Filter hữu hạn. **Routing Slip** phù hợp khi mỗi message cần một hành trình gồm các bước khác nhau và việc lập kế hoạch trình tự nên được tách khỏi triển khai từng endpoint.

Routing Slip mang lại độ linh hoạt nhưng cũng yêu cầu kỷ luật: **allowlist các bước, khóa phiên bản plan, quản lý hop/cursor, bảo toàn metadata qua adapter, hiểu reply/output semantics, không skip bước bắt buộc, thiết kế retry/idempotency và đo lường từng hop**. Nó không tự đảm bảo fan-out, aggregation, persistence hay orchestration dài hạn.

Trong `SPRING_INTEGRATION_PATTERN`, hãy chọn mẫu đơn giản nhất thể hiện đúng hợp đồng nghiệp vụ: flow tĩnh + Router khi các nhánh ít và rõ ràng; Routing Slip khi thực sự cần itinerary theo message; Recipient List/Publish–Subscribe cho fan-out; Scatter–Gather/Aggregator khi cần gom nhiều kết quả. Kết hợp error channel, correlation, distributed tracing và kiểm thử toàn bộ đường đi để flow vừa ít phụ thuộc vừa có thể vận hành và phục hồi an toàn.
