# Giới hạn độ phức tạp của route runtime

## 1. Bối cảnh và vấn đề cần giải quyết

Trong chương **Dynamic router** thuộc module **SPRING_INTEGRATION_PATTERN**, chúng ta học triển khai Enterprise Integration Patterns bằng **Spring Integration** để xây dựng các luồng thông điệp ít phụ thuộc, dễ mở rộng và có thể theo dõi. Dynamic Router giúp thay đổi cách chọn đường đi **khi ứng dụng đang chạy**. Đây là khả năng có ích khi chuyển lưu lượng sang hệ thống dự phòng, mở một tuyến xử lý mới hoặc cập nhật chính sách nghiệp vụ mà không phải dừng toàn bộ ứng dụng.

Tuy nhiên, sự linh hoạt này tạo thêm một loại rủi ro: **độ phức tạp của route không còn cố định tại thời điểm triển khai**.

Hãy tưởng tượng hệ thống giao vận nhận sự kiện DispatchRequested. Ban đầu mỗi message đi đến một trong hai nhánh:

- **standardChannel**: đơn thông thường.
- **manualReviewChannel**: đơn giá trị cao hoặc có rủi ro.

Sau đó nhóm vận hành liên tục thêm điều kiện: đơn quốc tế, đơn ưu tiên, đơn thuộc một tenant đặc biệt, đơn khuyến mại, các nhánh audit, notification, regional fulfillment và dự phòng. Nếu cho phép mọi quy tắc mở thêm recipient rồi các recipient lại định tuyến tiếp, một message có thể chạm hàng chục endpoint, lặp vô hạn hoặc quá tải hàng đợi.

~~~mermaid
flowchart LR
    P["DispatchRequested"] --> R["Dynamic Router"]
    R --> A["Standard"]
    R --> B["Review"]
    R --> C["Partner"]
    B --> R2["Router mới"]
    R2 --> D["Audit"]
    R2 --> E["Notification"]
    R2 --> R
~~~

Mũi tên từ Router mới quay lại Dynamic Router minh họa một **chu trình**. Nếu không có giới hạn, cùng message có thể tiếp tục chạy quanh topology, tạo lỗi stack overflow trong các nhánh đồng bộ hoặc backlog tăng không kiểm soát ở các nhánh bất đồng bộ.

**Mục tiêu bài học**

1. Nhận diện những chiều làm độ phức tạp của routing tăng tại runtime: số rule, chi phí predicate, số destination, fan-out, số hop, vòng lặp, số phiên bản cấu hình và concurrency.
2. Phân biệt **router đổi mapping runtime** với **rule nghiệp vụ thay đổi runtime** và **tạo toàn bộ IntegrationFlow mới runtime**.
3. Đặt giới hạn kiểm chứng được thay vì chỉ dựa vào nhận xét “ít rule là tốt”.
4. Xây dựng policy snapshot bất biến, cập nhật nguyên tử, allowlist channel và fallback an toàn.
5. Hiểu các API Spring Integration như **setChannelMapping**, **setChannelMappings**, **replaceChannelMappings**, **RecipientListRouterManagement** và **Control Bus**.
6. Kiểm thử tải, fan-out, route cycle, cập nhật đồng thời, rollback và sự khác biệt giữa các instance.

## 2. Dynamic Router là gì trong Spring Integration?

Về bản chất, một Router thường làm ba việc:

1. **Tính channel identifier** từ payload, headers hoặc logic nghiệp vụ.
2. **Ánh xạ identifier sang tên channel**.
3. **Phân giải tên channel thành MessageChannel** để gửi message.

Spring Integration hỗ trợ nhiều kiểu router như **HeaderValueRouter**, **PayloadTypeRouter**, router dùng SpEL hoặc POJO. Một router vẫn có thể đưa ra các kết quả khác nhau theo message mà chưa thực sự là “dynamic configuration”: biểu thức routing được cố định khi ứng dụng khởi tạo.

**Dynamic Router** theo Enterprise Integration Patterns nhấn mạnh rằng **quy tắc chọn route hoặc bảng ánh xạ có thể thay đổi trong lúc hệ thống đang vận hành**.

Ví dụ, mapping ban đầu:

~~~text
STANDARD -> standardChannel
REVIEW   -> manualReviewChannel
~~~

Khi bảo trì dịch vụ review, đội vận hành có thể đổi:

~~~text
STANDARD -> standardChannel
REVIEW   -> reviewBackupChannel
~~~

Nếu đổi có kiểm soát, application không cần restart để chuyển traffic. Nhưng nếu rule mới tạo ra đường quay về upstream router, sự cố có thể diễn ra ngay sau khi kích hoạt.

### 2.1. Ba cách làm routing thay đổi

| Cách | Điều thay đổi | Rủi ro phức tạp đặc trưng |
| --- | --- | --- |
| **Đổi channel mapping** | Key như REVIEW trỏ sang channel khác | Sai bean, vòng lặp, trạng thái trung gian khi cập nhật từng key |
| **Đổi policy chọn key** | Ngưỡng, danh mục, điều kiện theo thời gian/tenant | Số điều kiện tăng, logic khó dự đoán, kết quả khác giữa các lần retry |
| **Thêm/bớt recipient** | Số destination trong RecipientListRouter | Fan-out, duplicate recipient, lỗi một nhánh tác động các nhánh khác |
| **Đăng ký IntegrationFlow runtime** | Cả endpoint, channel và topology mới | Lifecycle, tài nguyên, xung đột tên bean, cleanup, observability |

Bài này tập trung vào **giới hạn độ phức tạp của quyết định và đường đi**. Khi cần đăng ký/xóa IntegrationFlow runtime, còn phải quản lý lifecycle bằng IntegrationFlowContext và quyền sở hữu bean; không nên coi đó là một thao tác đổi mapping đơn giản.

### 2.2. Dynamic không có nghĩa chạy song song

Một router có thể chọn nhiều destination, nhưng bản thân việc cập nhật mapping không tạo thread mới. Cách dispatch phụ thuộc channel đích:

- **DirectChannel** thường xử lý đồng bộ trên thread sender.
- **ExecutorChannel** chuyển dispatch qua executor.
- **QueueChannel** giữ message cho consumer/poller.
- **PublishSubscribeChannel** có thể phát tới nhiều subscriber.

Thay topology có thể thay **latency**, **thread**, **transaction boundary**, **error propagation** và khả năng backlog. Vì vậy kiểm tra độ phức tạp phải bao gồm cả chi phí vận hành, không chỉ số điều kiện trong code.

## 3. Những chiều của độ phức tạp route runtime

Nên xác định các biến đo được thay vì chỉ đếm số dòng trong file cấu hình:

| Ký hiệu | Ý nghĩa | Rủi ro khi tăng |
| --- | --- | --- |
| **R** | Số rule/predicate cần đánh giá | CPU, latency, khó xác định rule nào thắng |
| **C** | Chi phí trung bình hoặc tối đa của mỗi predicate | Blocking I/O, truy vấn DB lặp, timeout |
| **F** | Số recipient được chọn cho một message ở một router | Fan-out, số task và side effect |
| **H** | Số chặng routing tối đa trên một đường | Latency, vòng lặp và depth stack |
| **V** | Số phiên bản cấu hình đang cùng tồn tại | Replay không nhất quán, khó rollback |
| **Q** | Số message tồn đọng ở các hàng đợi | Tốn bộ nhớ/đĩa, trễ xử lý |
| **T** | Số tenant/nhóm có chính sách riêng | Cardinality và áp lực quản lý cấu hình |
| **E** | Số cạnh hợp lệ trong đồ thị channel/endpoint | Khó review route cycle và fan-out |

Một router chọn một nhánh sau khi duyệt tuyến tính R rule có chi phí quyết định **xấp xỉ O(R × C)** trong trường hợp phải xét mọi rule. Nếu tra mapping bằng hash map sau khi tính key, phép tra tên channel thường nhỏ hơn nhiều; tuy nhiên các bước tự tính key bằng truy vấn mạng hoặc chạy script phức tạp có thể thống trị tổng thời gian.

Nếu một message fan-out đều tối đa F nhánh ở mỗi tầng, tổng số node có thể tăng gần:

\[
1 + F + F^2 + \dots + F^H
= \frac{F^{H+1}-1}{F-1}\quad (F>1).
\]

Đây là **giới hạn minh họa cho cây phân nhánh đầy đủ**, không phải lời khẳng định mọi IntegrationFlow tăng theo hàm mũ. Trong thực tế, branch có thể kết thúc sớm, hội tụ hoặc không fan-out. Điều đáng chú ý là **F và H cùng không bị giới hạn** sẽ tạo ra worst case rất lớn.

Ví dụ F=3, H=4 tạo tối đa **121 vị trí xử lý** nếu mọi nhánh đều tách ba ở từng tầng (tính cả gốc). Chỉ cần thêm một tầng nữa, giới hạn tăng thành **364 vị trí**. Nếu một số nhánh tạo side effect, chi phí và nguy cơ trùng lặp tăng nhanh.

### 3.1. Không phải mọi rule đều có chi phí như nhau

So sánh:

~~~java
// Tính toán rẻ, không có side effect:
boolean needsReview(OrderEvent event) {
    return event.amountVnd().compareTo(REVIEW_THRESHOLD) >= 0;
}

// Cấu trúc đáng cân nhắc: mỗi lần route phải truy vấn network.
boolean needsReviewWithRemoteLookup(OrderEvent event) {
    return riskService.lookup(event.customerId()).requiresReview();
}
~~~

Đoạn code trên là **minh họa các loại predicate**, với OrderEvent, REVIEW_THRESHOLD và riskService là những dependency giả định. Predicate thứ hai có thể gây latency lớn, tăng số request, timeout và tạo vòng lỗi khi riskService cần gọi ngược về flow.

Nếu quyết định route phụ thuộc thông tin từ dịch vụ ngoài, cân nhắc **làm giàu message ở bước riêng** với timeout/circuit breaker, rồi định tuyến bằng một rule thuần trên dữ liệu đã làm giàu. Điều này giúp kiểm thử chi phí và failure của từng bước.

## 4. Thiết lập ngân sách độ phức tạp

Một tổ chức có thể đặt **route budget** ở mức ứng dụng và kiểm tra trước khi kích hoạt rule mới. Các con số sau chỉ là **ví dụ học tập**, không phải mặc định hoặc giới hạn của Spring Integration.

| Thuộc tính | Ngân sách ví dụ | Hành động khi vượt |
| --- | ---: | --- |
| Số rule hoạt động trong một policy | 24 | Từ chối cấu hình mới hoặc tách domain có chủ đích |
| Số recipient tối đa ở một router | 3 | Reject cấu hình fan-out quá rộng |
| Số routing hop trong một workflow | 8 | Chuyển sang error/quarantine, không route thêm |
| Số lần quay lại cùng bước cho một event | 1, nếu flow không thiết kế vòng hợp lệ | Phát hiện cycle và dừng |
| Số phiên bản policy giữ cho replay | Theo thời hạn event sống | Quản lý retention và migration |
| Dung lượng hàng đợi mỗi nhánh | Bounded theo throughput/latency SLO | Backpressure hoặc từ chối có kiểm soát |
| Thời gian quyết định route | Theo latency SLO | Cảnh báo, tối ưu rule; không cho phép I/O vô hạn |

**Ngân sách có ý nghĩa khi gắn với SLO và số liệu thực tế.** Một route chỉ có hai rule nhưng mỗi rule gọi API 10 giây vẫn tệ hơn 20 rule thuần chạy trong vài microgiây. Bốn recipient độc lập có thể hợp lý nếu tất cả là yêu cầu nghiệp vụ và hệ thống có capacity, còn hai recipient cùng ghi một side effect có thể là lỗi.

### 4.1. Ba cấp kiểm soát

1. **Trước kích hoạt:** validate rule count, tên destination, trùng recipient, tham chiếu bean, khả năng tạo chu trình và compatibility.
2. **Khi xử lý message:** giới hạn hop/fan-out theo runtime budget, timeout có kiểm soát, fallback/error flow và idempotency.
3. **Sau kích hoạt:** metrics, tracing, theo dõi tài nguyên, canary và rollback về snapshot cũ nếu vượt SLO.

Một static validator không bắt được mọi vòng lặp khi route phụ thuộc payload hoặc strategy thay đổi theo trạng thái runtime. Ngược lại, chỉ dùng hop counter runtime không chứng minh topology đã an toàn khi triển khai. Nên có cả hai.

## 5. Đồ thị routing: kiểm tra vòng lặp và fan-out

Biểu diễn topology bằng đồ thị có hướng:

- **Đỉnh:** Router, handler, channel hoặc nhóm bước có semantics rõ.
- **Cạnh:** một message có thể được chuyển từ đỉnh này đến đỉnh khác.
- **Nhánh có điều kiện:** cạnh chỉ được dùng khi predicate khớp.
- **Vòng:** có đường quay lại một đỉnh đã đi qua.

~~~mermaid
flowchart LR
    A["ingress"] --> R1["router A"]
    R1 -->|"STANDARD"| S["standard handler"]
    R1 -->|"REVIEW"| R2["router B"]
    R2 -->|"normal"| C["review handler"]
    R2 -->|"wrong mapping"| R1
~~~

Đường **R1 → R2 → R1** là một chu trình tiềm năng. Nếu router chạy đồng bộ và liên tục chọn vòng này, có thể gây call stack tăng không kiểm soát. Nếu vòng đi qua queue, message có thể quay vòng lâu dài và làm nghẽn consumer.

### 5.1. Kiểm tra tĩnh trên candidate config

Trước khi kích hoạt, chạy một phép **DFS/topological validation** trên các cạnh do candidate cung cấp:

1. Xác định danh sách destination được phép.
2. Chuẩn hóa các cạnh, kiểm tra tên endpoint/channel tồn tại.
3. Phát hiện duplicate edge hoặc recipient identity.
4. Dùng DFS để phát hiện chu trình nếu workflow **bắt buộc acyclic**.
5. Ước lượng fan-out tối đa hoặc số route hop trên các đường hợp lệ.
6. Từ chối candidate không đáp ứng budget; ghi lý do rõ ràng.

Nếu workflow cố ý lặp như **retry có giới hạn**, không nên từ chối mọi cycle một cách tuyệt đối. Thay vào đó, đánh dấu các cạnh lặp hợp lệ và yêu cầu **điều kiện dừng** cùng budget số attempt/hop. Vòng retry nghiệp vụ có điều kiện khác với một cycle vô tình do mapping.

### 5.2. Kiểm soát runtime với hop budget

Trong các flow có router lồng nhau, mỗi lần đi qua một ranh giới routing cần cập nhật **routeHops** do server quản lý. Trước khi gửi tiếp:

- Nếu vượt maxHops, **dừng** và gửi error/quarantine có metadata.
- Nếu một bước không được phép lặp mà đã được ghé thăm, báo cycle.
- Nếu nhận message từ client hoặc broker chưa tin cậy, **không tin** header routeHops do client tự đặt.

Hop budget chỉ giúp **giới hạn thiệt hại**; không thay thế kiểm tra topology. Với replay, cần phân biệt **số hop trong một attempt** và **tổng số attempt**; reset hop ở mỗi replay có thể hợp lệ nhưng phải có **retry budget bền** riêng để không lặp vô hạn qua các lần khởi động.

## 6. Đừng biến dữ liệu bên ngoài thành tên channel tùy ý

Rủi ro an toàn lớn nhất của dynamic router là dùng một **routing key chưa tin cậy** làm **bean name**. Một input như **internalAdminChannel** hoặc **routerInputChannel** không được tự động trở thành destination hợp lệ chỉ vì bean tương ứng tồn tại.

Trong AbstractMappingMessageRouter, **channelKeyFallback=true** cho phép dùng key chưa map làm tên channel. Khi ứng dụng có input chưa tin cậy, thường nên đặt **channelKeyFallback(false)** và ánh xạ key từ một **allowlist cố định** sang những channel đã được kiểm tra.

~~~mermaid
flowchart LR
    U["Client / Broker event"] --> B["Validate + authenticate"]
    B --> K["Policy tính routing key"]
    K --> M{"Allowlisted mapping"}
    M -->|"STANDARD"| S["standardChannel"]
    M -->|"REVIEW"| R["reviewChannel"]
    M -->|"Unknown"| Q["quarantineChannel"]
~~~

Các quy tắc bổ sung:

- Tenant, role, quyền và trạng thái nghiệp vụ phải đến từ dữ liệu **được xác minh**, không chỉ header mang tên trusted.
- Không cho người dùng thêm tên channel, Java class name hoặc biểu thức SpEL tùy ý vào runtime rule.
- Nếu có API quản trị để đổi rule, tách nó khỏi API gửi message; yêu cầu xác thực mạnh, phân quyền, audit và giới hạn tần suất.
- Không cho route mới bỏ qua bước audit, validation hoặc kiểm tra quyền bắt buộc.
- Khi cần dynamic destination từ bên ngoài, dùng **registry/alias đã kiểm soát** thay vì phân giải mọi tên bean trong ApplicationContext.

**Giới hạn độ phức tạp cũng là một biện pháp an toàn**: nó ngăn một rule lỗi hoặc bị lạm dụng mở hàng trăm nhánh, tạo vòng lặp hoặc thao tác vào các endpoint không phù hợp.

## 7. Kiến trúc đề xuất: policy động, tập channel hữu hạn

Một cách giới hạn độ phức tạp là **cho phép policy thay đổi**, nhưng không cho phép nó tự tạo ra mọi tên channel trong hệ thống.

Ví dụ policy có thể thay đổi ngưỡng rủi ro, loại hàng cần review, hoặc thời gian kích hoạt. Kết quả cuối cùng chỉ được nằm trong ba route key:

~~~text
STANDARD
REVIEW
QUARANTINE
~~~

Topology đến ba channel được khai báo và kiểm thử từ trước. Khi policy đổi, route vẫn có **ba đích khả dĩ**; không có khả năng tự tăng số recipient, thêm một channel name từ client hay quay lại input do bảng mapping không giới hạn.

~~~mermaid
flowchart TD
    E["DispatchRequested"] --> V["Validate input + tenant"]
    V --> P["Immutable policy snapshot<br/>version=N"]
    P --> D{"Route decision"}
    D -->|"STANDARD"| S["standardChannel"]
    D -->|"REVIEW"| R["reviewChannel"]
    D -->|"UNKNOWN/INVALID"| Q["quarantineChannel"]
~~~

Đây là **dynamic business policy** với **fixed routing topology**. Nếu yêu cầu nghiệp vụ chỉ cần đổi tiêu chí chọn nhánh, giải pháp này thường dễ kiểm soát hơn việc thêm/xóa IntegrationFlow hoặc recipient liên tục tại runtime.

### 7.1. Lợi ích của snapshot bất biến

- Mỗi quyết định route đọc **một policy hoàn chỉnh**, không thấy ngưỡng mới nhưng danh sách loại hàng cũ.
- Có **version** để log, truy vết và rollback.
- Có thể validate candidate trước khi kích hoạt.
- Một bản cập nhật chỉ thay tham chiếu snapshot, không sửa từng rule tại chỗ.
- Không cần khóa dài quanh toàn bộ quá trình route.

**Giới hạn:** AtomicReference chỉ bảo đảm cập nhật tham chiếu **trong một JVM**. Nó không đồng bộ các instance của ứng dụng, không tự lưu phiên bản qua restart, và không khiến mọi endpoint của cả workflow tự dùng cùng snapshot nếu chúng tiếp tục đọc global policy ở các thời điểm khác nhau.

## 8. Cài đặt policy snapshot bằng Java 17+

Ví dụ sau dùng một quy tắc đơn giản:

- Hàng thuộc danh mục rủi ro cần review.
- Hoặc đơn đạt ngưỡng giá trị cần review.
- Còn lại đi standard.

### 8.1. Dữ liệu nghiệp vụ và bản quyết định

~~~java
import java.math.BigDecimal;

record DispatchRequested(
        String eventId,
        String tenantId,
        String category,
        BigDecimal amountVnd) {}

record RoutedDispatch(
        DispatchRequested event,
        String routeKey,
        long policyVersion) {}
~~~

Trong production, **tenantId phải đến từ nguồn đã xác thực**; không coi giá trị tenantId bên trong record là tự động đáng tin. EventId cần ổn định qua retry của cùng một sự kiện.

### 8.2. Định nghĩa snapshot bất biến có validation

~~~java
import java.math.BigDecimal;
import java.util.Objects;
import java.util.Set;

record RoutePolicySnapshot(
        long version,
        BigDecimal reviewThresholdVnd,
        Set<String> riskCategories) {

    RoutePolicySnapshot {
        if (version <= 0) {
            throw new IllegalArgumentException("Version không hợp lệ");
        }
        if (reviewThresholdVnd == null
                || reviewThresholdVnd.signum() <= 0) {
            throw new IllegalArgumentException("Ngưỡng không hợp lệ");
        }
        Objects.requireNonNull(riskCategories, "riskCategories");
        if (riskCategories.size() > 16) {
            throw new IllegalArgumentException("Quá nhiều category rule");
        }
        for (String category : riskCategories) {
            if (category == null
                    || !category.matches("[A-Z0-9_-]{1,40}")) {
                throw new IllegalArgumentException("Category sai định dạng");
            }
        }
        riskCategories = Set.copyOf(riskCategories);
    }
}
~~~

Ở đây **16** là ngân sách ví dụ cho một bộ rule dạng membership, không phải một giới hạn của Spring Integration. Constructor dùng **Set.copyOf** để tránh code khác thay đổi collection sau khi publish snapshot. Record giúp giữ references không thể gán lại, còn immutable collection ngăn thay đổi tập category qua tham chiếu.

### 8.3. Policy engine chọn một route key hữu hạn

~~~java
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

final class BoundedRoutingPolicy {
    private final AtomicReference<RoutePolicySnapshot> current;

    BoundedRoutingPolicy(RoutePolicySnapshot initial) {
        current = new AtomicReference<>(
                Objects.requireNonNull(initial));
    }

    RoutedDispatch decide(DispatchRequested event) {
        validate(event);

        // Đọc đúng một snapshot cho một lần quyết định.
        RoutePolicySnapshot snapshot = current.get();
        String normalizedCategory =
                event.category().trim().toUpperCase(Locale.ROOT);

        boolean review =
                event.amountVnd().compareTo(
                        snapshot.reviewThresholdVnd()) >= 0
                || snapshot.riskCategories().contains(normalizedCategory);

        return new RoutedDispatch(
                event,
                review ? "REVIEW" : "STANDARD",
                snapshot.version());
    }

    void activate(RoutePolicySnapshot next) {
        Objects.requireNonNull(next, "next");

        // Hàm cập nhật không có side effect, an toàn khi CAS thử lại.
        current.updateAndGet(previous -> {
            if (next.version() <= previous.version()) {
                throw new IllegalArgumentException(
                        "Version mới phải lớn hơn version hiện tại");
            }
            return next;
        });
    }

    RoutePolicySnapshot currentSnapshot() {
        return current.get();
    }

    private static void validate(DispatchRequested event) {
        if (event == null
                || event.eventId() == null
                || event.eventId().isBlank()
                || event.tenantId() == null
                || event.tenantId().isBlank()
                || event.category() == null
                || event.category().isBlank()
                || event.amountVnd() == null
                || event.amountVnd().signum() <= 0) {
            throw new IllegalArgumentException(
                    "DispatchRequested chưa hợp lệ");
        }
    }
}
~~~

**Điểm đáng chú ý:**

1. Route key chỉ có thể là **STANDARD** hoặc **REVIEW** trong ví dụ; số destination không tăng theo số category.
2. Không truy vấn database, gọi HTTP hoặc thực thi script tại mỗi lần route.
3. Quyết định có **policyVersion** đi kèm để truy vết phiên bản đã dùng.
4. Bản cập nhật bị từ chối nếu version không tiến lên; đây là một policy versioning minh họa.
5. Việc cập nhật ở JVM này **không tự đẩy** đến các JVM khác. Cần cơ chế phân phối phiên bản, xác nhận đồng bộ và rollback ở mức hệ thống.

Nếu cần rollback một bản policy sai, không nhất thiết tái sử dụng số version cũ. Có thể tạo **version mới** có nội dung tương đương bản tốt trước đó, để lịch sử version vẫn tăng đơn điệu và có audit trail rõ ràng.

### 8.4. Ghép policy với Java DSL

~~~java
import java.math.BigDecimal;
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
class BoundedRouterConfiguration {

    @Bean
    BoundedRoutingPolicy boundedRoutingPolicy() {
        return new BoundedRoutingPolicy(
                new RoutePolicySnapshot(
                        1,
                        new BigDecimal("10000000"),
                        Set.of("HAZMAT", "OVERSIZE")));
    }

    @Bean
    MessageChannel dispatchInputChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel standardChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel reviewChannel() {
        return new DirectChannel();
    }

    @Bean
    MessageChannel quarantineChannel() {
        return new DirectChannel();
    }

    @Bean
    IntegrationFlow boundedDispatchFlow(BoundedRoutingPolicy policy) {
        return IntegrationFlow.from("dispatchInputChannel")
                .transform(DispatchRequested.class, policy::decide)
                .<RoutedDispatch, String>route(
                        RoutedDispatch::routeKey,
                        mapping -> mapping
                                .channelMapping(
                                        "STANDARD", "standardChannel")
                                .channelMapping(
                                        "REVIEW", "reviewChannel")
                                .channelKeyFallback(false)
                                .defaultOutputChannel(
                                        "quarantineChannel"))
                .get();
    }
}
~~~

Các channel đích cần có **consumer/subflow** thực. Bước Transformer tạo RoutedDispatch để giữ cả event và policyVersion; các handler downstream phải đọc đúng kiểu payload, không giả định họ vẫn nhận DispatchRequested.

Quarantine là đường xử lý an toàn cho một route key không được ánh xạ. **Dữ liệu đầu vào không hợp lệ** trong code policy hiện tại ném exception trước khi đến Router, nên cần error handling/validation riêng. Không nên hiểu defaultOutputChannel sẽ tự bắt mọi exception của Transformer.

**Phần động** ở ví dụ là dữ liệu của BoundedRoutingPolicy được cập nhật trong lúc chạy, còn bảng channelMapping hữu hạn. Đây là cách cố ý **giới hạn độ phức tạp route runtime**.

### 8.5. Handler nhánh chỉ thực hiện trách nhiệm của mình

~~~java
interface StandardDispatchPort {
    void submit(DispatchRequested event);
}

interface ReviewDispatchPort {
    void review(DispatchRequested event);
}

// Đặt trong lớp @Configuration bên trên:
@Bean
IntegrationFlow standardFlow(StandardDispatchPort port) {
    return IntegrationFlow.from("standardChannel")
            .handle(RoutedDispatch.class, (decision, headers) -> {
                port.submit(decision.event());
                return null;
            })
            .get();
}

@Bean
IntegrationFlow reviewFlow(ReviewDispatchPort port) {
    return IntegrationFlow.from("reviewChannel")
            .handle(RoutedDispatch.class, (decision, headers) -> {
                port.review(decision.event());
                return null;
            })
            .get();
}
~~~

Hai port là abstraction nghiệp vụ minh họa. Bản triển khai có thể thêm idempotency theo eventId + logicalRecipientId, retry và transaction phù hợp. Nếu một event chạy lại sau khi policy đã đổi, cần xác định liệu nó phải theo **route cũ** hay route mới; xem phần nhất quán và replay.

## 9. Giới hạn fan-out khi phải chọn nhiều recipient

Không phải dynamic routing nào cũng chỉ chọn một đích. Một hệ thống có thể cần phát sự kiện đến **audit**, **notification**, **risk review** và các đối tác theo điều kiện. Khi dùng RecipientListRouter, cần quản lý cả **số lượng recipient** lẫn **tính duy nhất của trách nhiệm**.

### 9.1. Đừng thêm cùng destination nhiều lần

~~~java
// Đáng ngờ: cùng auditChannel được đăng ký hai lần.
.routeToRecipients(r -> r
        .recipientMessageSelector("auditChannel",
                message -> isPriority(message.getPayload()))
        .recipientMessageSelector("auditChannel",
                message -> isInternational(message.getPayload())))
~~~

Nếu audit cần nhận khi **priority hoặc international**, hãy dùng **một recipient** với điều kiện OR:

~~~java
.routeToRecipients(r -> r
        .recipientMessageSelector("auditChannel",
                message -> isPriority(message.getPayload())
                        || isInternational(message.getPayload())))
~~~

Hai ví dụ là **mảnh DSL minh họa** và giả định hàm isPriority/isInternational đã được định nghĩa. Không nên dựa vào framework tự loại mọi entry trùng ở tất cả phiên bản/cách cấu hình; ứng dụng nên kiểm tra topology và test số lần handler thực nhận.

### 9.2. Không nhận danh sách recipient trực tiếp từ message bên ngoài

Người dùng có thể gửi danh sách 1.000 recipient, nhưng nghiệp vụ chỉ cho phép các kênh nội bộ AUDIT, RISK và NOTIFICATION. Ta cần:

1. Chuyển **recipient identity** vào enum/tập alias được phép.
2. Xác thực quyền, loại sự kiện và số recipient.
3. Dùng **Set** để phát hiện hoặc ngăn lặp identity, không phải để che lỗi cấu hình một cách im lặng.
4. Ánh xạ alias hợp lệ sang channel đã khai báo.
5. Từ chối hoặc quarantine khi fan-out vượt ngân sách.

Một lời gọi RecipientListRouter có thể gửi tới nhiều channel; việc gọi **send() thành công** không bảo đảm tất cả side effect downstream đã commit, đặc biệt khi nhánh là ExecutorChannel/QueueChannel hoặc adapter async.

### 9.3. RecipientListRouter có thể thay đổi lúc runtime

Spring Integration cung cấp **RecipientListRouterManagement** để thêm/bớt recipient qua các thao tác quản lý và có thể tiếp cận bằng **Control Bus/JMX** khi được bật. Khả năng này giúp bảo trì tuyến mà không restart, nhưng không tự giới hạn:

- Bao nhiêu recipient có thể được thêm.
- Ai được quyền cập nhật.
- Có duplicate identity hay đường vòng không.
- Việc nhiều thao tác cập nhật liên tiếp có được xem là một snapshot nguyên tử hay không.
- Các message đang chạy có thấy cùng một tập recipient hay không.

Trước khi thực hiện cập nhật, hãy kiểm tra **candidate recipient set** như một đơn vị logic. Nếu business yêu cầu tất cả message trong một khoảng thời gian phải thấy đúng một version, cần thiết kế **snapshot/versioning** tương ứng, không mặc định coi nhiều lệnh add/remove riêng lẻ là một giao dịch.

## 10. Cơ chế quản lý mapping runtime của Spring Integration

Với các router kế thừa **AbstractMappingMessageRouter**, Spring Integration cung cấp những phương thức quản lý cụ thể:

| API | Tác dụng | Cần lưu ý |
| --- | --- | --- |
| **setChannelMapping(key, channelName)** | Thêm hoặc đổi một mapping | Nhiều lần gọi không tạo một thay đổi nguyên tử toàn bảng |
| **removeChannelMapping(key)** | Xóa một mapping | Có thể tạo khoảng trống khi chuyển cấu hình |
| **getChannelMappings()** | Lấy mapping hiện tại để quan sát | Không dùng bản đọc cũ làm chứng cứ phiên bản mới |
| **setChannelMappings(Map)** | Cập nhật bảng mapping theo map | Validate map trước, ưu tiên khi cập nhật chương trình |
| **replaceChannelMappings(Properties)** | Thay bảng mapping, thích hợp với Control Bus | Chỉ nhận string keys/values phù hợp |
| **setChannelKeyFallback(false)** | Không dùng key chưa map làm tên channel | Bảo vệ allowlist, giảm nguy cơ vòng lặp |
| **setDynamicChannelLimit(n)** | Giới hạn số tên channel động được **giữ để báo cáo** | **Không phải** giới hạn fan-out, số hop hay số destination được phép |

**Lưu ý quan trọng:** tên phương thức **setDynamicChannelLimit** dễ làm người đọc tưởng nó ngăn router gửi tới quá nhiều channel. Theo Java API, mục tiêu của thuộc tính này là giới hạn việc **ghi nhớ các tên channel động cho báo cáo**, không phải một quota bảo mật cho fan-out hoặc độ sâu luồng.

### 10.1. Vì sao nhiều update đơn lẻ nguy hiểm?

Giả sử ứng dụng muốn chuyển:

~~~text
A -> channel1
B -> channel2
~~~

sang:

~~~text
A -> channel3
B -> channel4
~~~

Nếu gọi lần lượt setChannelMapping(A, channel3), rồi setChannelMapping(B, channel4), giữa hai thao tác có một khoảng thời gian bảng mapping chứa **A mới, B cũ**. Message đồng thời có thể được định tuyến theo tổ hợp chưa từng được phê duyệt.

~~~mermaid
sequenceDiagram
    participant U as Admin
    participant R as Router
    participant M as Message producer
    U->>R: setChannelMapping(A, channel3)
    M->>R: Message key B
    R-->>M: channel2 từ bảng tạm
    U->>R: setChannelMapping(B, channel4)
~~~

Tài liệu chính thức Spring Integration khuyến nghị **cập nhật toàn bộ bảng** khi cần thay đổi nguyên tử các key liên quan. Từ Spring Integration 4.0, cơ chế replaceChannelMappings hỗ trợ Control Bus thay toàn bảng; khi cập nhật trong mã Java, **setChannelMappings(Map)** là lựa chọn rõ kiểu hơn.

Một lần cập nhật bảng mapping có thể nguyên tử ở **router trong một process** nhưng không đồng nghĩa thay đồng thời **toàn bộ cấu hình của mọi router, mọi instance và mọi message đang xử lý**. Cần có version/rollout coordinator nếu hệ thống phân tán yêu cầu nhất quán.

### 10.2. Ví dụ áp đặt ngân sách trước khi update

~~~java
import java.util.Map;
import java.util.Set;

import org.springframework.integration.router.HeaderValueRouter;

final class SafeMappingUpdater {
    private static final int MAX_MAPPINGS = 12;
    private static final Set<String> ALLOWED_CHANNELS = Set.of(
            "standardChannel",
            "reviewChannel",
            "reviewBackupChannel",
            "quarantineChannel");

    void activate(
            HeaderValueRouter router,
            Map<String, String> candidate) {

        if (candidate == null
                || candidate.isEmpty()
                || candidate.size() > MAX_MAPPINGS) {
            throw new IllegalArgumentException("Quá giới hạn mappings");
        }
        if (!ALLOWED_CHANNELS.containsAll(candidate.values())) {
            throw new IllegalArgumentException(
                    "Destination nằm ngoài allowlist");
        }
        for (String key : candidate.keySet()) {
            if (key == null
                    || !key.matches("[A-Z0-9_-]{1,40}")) {
                throw new IllegalArgumentException(
                        "Routing key không hợp lệ");
            }
        }

        // Có thể thêm kiểm tra cycle, quyền và bean resolution
        // trước khi thực hiện thay đổi.
        router.setChannelMappings(Map.copyOf(candidate));
    }
}
~~~

Đây là lớp **validation trước cập nhật**. Nó chưa kiểm tra liệu các bean channel tồn tại, có subscriber, có route cycle hay không; cần bổ sung kiểm tra topology và quản trị rollout. Nếu candidate không hợp lệ, hàm **không gọi router.setChannelMappings**.

**Đừng truyền thẳng Map do client HTTP gửi lên** vào setChannelMappings. Chỉ cho phép thao tác qua kênh quản trị đã xác thực, phân quyền và có audit; mỗi thay đổi nên mang policyVersion, người phê duyệt và nguyên nhân.

### 10.3. Control Bus không phải endpoint công khai

Control Bus cho phép gửi **control message** để gọi các phương thức quản trị trên component. Đây là khả năng mạnh; nếu expose nó trực tiếp ra môi trường không tin cậy, người ngoài có thể thay route hoặc thao tác những bean khác.

Các biện pháp vận hành:

- Giới hạn ingress của control channel và xác thực admin.
- Phê duyệt candidate trước khi tạo control message.
- Bật audit log cho ai thay đổi, old/new version, kết quả apply và rollback.
- Không cho người dùng nhập SpEL tùy ý.
- Không để Control Bus chia sẻ đường vào với event nghiệp vụ chưa tin cậy.

**Control Bus giải quyết việc cập nhật**, không tự tạo cơ chế policy validation, phân quyền và kiểm soát tác động theo nhiều service.

## 11. Guard runtime: giới hạn hop cho một message

Static validator chỉ biết những đường có trong cấu hình được duyệt. Khi điều kiện route thay đổi liên tục hoặc một nhánh trả message ngược lên upstream, nên có giới hạn hop **thực thi trong luồng**.

Một guard tối thiểu nhận Message<?> đã qua ranh giới xác thực, đọc số hop **do nội bộ quản lý** và tạo message tiếp theo với số hop tăng thêm một.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

final class RouteHopGuard {
    private final int maxHops;

    RouteHopGuard(int maxHops) {
        if (maxHops <= 0) {
            throw new IllegalArgumentException("maxHops phải dương");
        }
        this.maxHops = maxHops;
    }

    Message<?> enterNextRouter(Message<?> message) {
        Object raw = message.getHeaders().get("trustedRouteHops");

        int previous;
        if (raw == null) {
            previous = 0;
        } else if (raw instanceof Integer value && value >= 0) {
            previous = value;
        } else {
            throw new IllegalArgumentException(
                    "Header hop count không hợp lệ");
        }

        if (previous >= maxHops) {
            throw new IllegalStateException(
                    "ROUTING_HOP_BUDGET_EXCEEDED");
        }

        return MessageBuilder.fromMessage(message)
                .setHeader("trustedRouteHops", previous + 1)
                .build();
    }
}
~~~

**Cách dùng:** đặt guard ở **trước mỗi ranh giới router** cần được tính hop. Nếu workflow dùng nhiều service, mỗi chặng phải truyền một metadata đáng tin hoặc một state riêng với giới hạn tương đương. Khi vượt budget, lỗi cần đi vào một **error flow/quarantine** có phân loại, không tiếp tục route về cùng channel.

### 11.1. Điều guard không thể tự giải quyết

- Nếu có code gửi message trực tiếp tới một channel **bỏ qua guard**, budget không có hiệu lực trên đường đó.
- Nếu producer bên ngoài tự đặt trustedRouteHops=0 và adapter copy thẳng, nó có thể **reset** giới hạn. Phải tạo lại hoặc xác minh header tại trust boundary.
- Nếu mỗi lần retry được tạo một message mới với hop count=0, vẫn có thể **retry vô hạn giữa nhiều attempts**. Cần giới hạn retries bền và thời gian sống của workflow.
- Nếu bước xử lý vừa gửi message về upstream vừa sinh message con, phải theo dõi **tổng số deliveries/branch** khi yêu cầu có ngân sách chung, không chỉ hop depth của một nhánh.
- Nếu có vòng lặp hợp lệ, cần quy định **logical iteration ID** và giới hạn số lần lặp; không chỉ dùng visited channel name rồi cấm mọi lần quay lại.

**Không đặt giới hạn bằng một phép tính trên header đơn lẻ nếu source có thể tự sửa header.** Một hệ thống phân tán cần cơ chế ký hoặc tin cậy producer, hoặc giữ ngân sách workflow tại một state store đáng tin.

### 11.2. Quản lý fan-out budget

Giới hạn maxHops không giới hạn được số nhánh được sinh ở một router. Với recipient list, cần kiểm tra:

~~~text
selectedRecipients.size <= maxFanoutPerRouter
~~~

Nếu nhiều router nối nhau, còn cần giới hạn **totalDispatchesPerEvent** hoặc resource budget toàn workflow nếu nghiệp vụ yêu cầu. Một counter cho toàn workflow phải được cập nhật đúng trong môi trường đồng thời/phân tán; một biến local ở một JVM không đủ làm quota toàn cụm.

**Mô hình chi phí:** một message ở tầng đầu fan-out 3 nhánh rồi mỗi nhánh tách 3 tiếp, số deliveries có thể tăng ngay cả khi độ sâu chỉ là 2. Với nhánh có I/O tốn kém, ngân sách fan-out quan trọng ngang hop depth.

## 12. Route runtime thay đổi khi các message đang xử lý

Khi cấu hình được cập nhật, ba nhóm message có thể tồn tại:

1. **Đã được định tuyến** trước thời điểm cập nhật và đang chạy downstream.
2. **Đang ở giữa** quá trình tính key hoặc resolve destination.
3. **Mới tới** sau khi bản policy mới được kích hoạt.

Với snapshot immutable, mỗi lần **decide()** trong ví dụ dùng đúng một snapshot để chọn route và gắn policyVersion. Nhưng nó không quyết định toàn bộ các bước sau phải dùng version nào nếu chúng lại đọc policy global.

### 12.1. Pin version theo logical event

Nếu cùng một sự kiện phải **giữ route như lần xử lý đầu** qua retry/redelivery, cần lưu một quyết định bền:

~~~text
eventId: evt-9001
policyVersion: 12
routeKey: REVIEW
decisionStatus: COMMITTED
~~~

Sau khi event được tiếp nhận lần đầu, hệ thống có thể lưu quyết định route cùng eventId (inbox/outbox hoặc workflow state). Khi replay, lấy **routeKey đã commit** thay vì tính lại với policy mới. Nếu route cũ không còn phục vụ, cần chính sách migration/quarantine; không tự ý dùng route mới nếu điều đó có thể làm side effect lặp hoặc sai luồng.

Nếu nghiệp vụ chấp nhận **route được tính lại theo policy mới** khi retry, cần ghi rõ quyết định đó và bảo đảm consumer idempotent. Hai lựa chọn đều có thể hợp lý nhưng không thể mặc định thay thế nhau.

### 12.2. Thay route không tự hủy side effect trước đó

Giả sử event đã được gửi đến reviewChannel theo version 12 nhưng version 13 đổi routeKey REVIEW sang reviewBackupChannel. Khi producer retry toàn bộ event:

- Review cũ có thể đã tạo phiếu xử lý.
- Review mới có thể tạo một phiếu khác.

Muốn bảo đảm chỉ có **một logical review request**, phải dùng **idempotency key ổn định** như tenantId + eventId + logicalActionId, và quy định nguồn sở hữu tác vụ. Thay mapping không tự di chuyển trạng thái xử lý hoặc rollback phiếu ở channel cũ.

### 12.3. Đa instance và rollout theo version

AtomicReference trong mỗi JVM không phân phối thay đổi giữa replica A/B/C. Khi update policy:

1. Publish candidate với **version** và checksum.
2. Mỗi instance tải/validate candidate.
3. Coordinator đợi đủ acknowledgment hoặc đưa instance chưa đồng bộ ra khỏi nhận lưu lượng cần tính nhất quán.
4. Kích hoạt version theo chiến lược rollout: đồng loạt có điều phối, canary hoặc gradual.
5. Ghi lại instance nào đang chạy version nào.
6. Khi rollback, phát hành version mới có nội dung policy cũ, tránh tranh chấp phiên bản.

**Không có một chiến lược đúng cho mọi hệ thống.** Canary có thể hợp lý khi mỗi event độc lập và route khác nhau tạm thời được chấp nhận; một số workflow đòi hỏi mọi message của cùng một correlation group dùng cùng policyVersion.

## 13. Xử lý lỗi và đường mặc định

Dynamic router cần phân biệt **không chọn được route** với **route đã chọn nhưng xử lý thất bại**.

| Trường hợp | Bản chất | Hành động |
| --- | --- | --- |
| Routing key chưa có mapping | Unknown/unsupported route | Default output channel hoặc fail fast |
| Rule mới trả tên bean chưa tồn tại | Lỗi cấu hình hoặc deploy chưa xong | Từ chối kích hoạt từ trước; khi runtime lỗi thì cảnh báo |
| Destination có DirectChannel không subscriber | Lỗi wiring/delivery | Không coi là unknown key |
| ExecutorChannel từ chối task | Backpressure/rejection | Retry có giới hạn, không tạo task vô hạn |
| QueueChannel nhận message nhưng không có poller | Backlog | Giám sát độ sâu, thời gian chờ, health consumer |
| Handler gọi external API thất bại | Lỗi downstream | Error flow, retry/idempotency theo branch |
| Rule chậm hoặc throw exception | Lỗi lúc quyết định | Fail fast/quarantine, ghi version và lý do |
| Hop/fan-out budget vượt ngưỡng | Vi phạm policy tài nguyên | Dừng route, error/quarantine, alert |

### 13.1. Default output channel không phải mạng an toàn cho mọi lỗi

Một default output channel được dùng khi router **không xác định được channel phù hợp** theo cấu hình. Nó **không tự thu nhận** mọi exception của một handler đã được chọn. Những lỗi sau send còn tùy thuộc DirectChannel, ExecutorChannel, QueueChannel, adapter và error handler.

Nếu cần gửi message unknown tới quarantine, hãy có **consumer thực sự lưu thông tin**. Một channel có tên quarantineChannel mà không có subscriber/poller có thể trở thành dead-end. Nếu lưu message chỉ trong RAM, khả năng replay sau restart không được bảo đảm.

### 13.2. channelKeyFallback và resolutionRequired

Trong **AbstractMappingMessageRouter**:

- **channelKeyFallback** điều khiển việc dùng một key chưa map như **tên channel**. Thường nên tắt với nguồn chưa tin cậy.
- **resolutionRequired** quyết định có chấp nhận tên channel không resolve được hay không. Thường nên để true để sai tên được phát hiện.
- **defaultOutputChannel** quy định đích fallback khi không xác định được route hợp lệ.

Từ **Spring Integration 6.0**, đặt default output channel cũng đặt channelKeyFallback=false theo mặc định. Cấu hình kết hợp defaultOutputChannel, channelKeyFallback=true và resolutionRequired=true bị từ chối khi khởi tạo vì mâu thuẫn.

Những tùy chọn này **không tự tạo maxRules, maxHops hoặc maxFanout**; giới hạn độ phức tạp vẫn phải được thiết kế ở lớp ứng dụng/topology.

### 13.3. ignoreSendFailures không chặn fan-out gây quá tải

Với router chọn nhiều recipient, ignoreSendFailures(true) có thể cho phép tiếp tục gửi các recipient khác sau một số lỗi gửi đồng bộ. Nó **không giảm** số recipient được chọn, không bảo đảm một nhánh lỗi sẽ được retry và có thể che khuất tác vụ bắt buộc thất bại.

Sử dụng một **bounded executor/queue**, timeout và error channel đúng vị trí. Với side effect quan trọng, cần idempotency và cơ chế durable delivery nếu có yêu cầu phục hồi sau restart.

## 14. Giảm chi phí đánh giá rule

Không phải lúc nào cũng cần thêm hardware để xử lý policy có nhiều rule. Có thể giảm độ phức tạp bằng cách:

1. **Chuẩn hóa dữ liệu trước khi route**: country code, category, eventType có kiểu/giá trị hợp lệ.
2. **Tách validation và enrichment** khỏi router để predicate chỉ đọc dữ liệu sẵn có.
3. **Ưu tiên key hữu hạn**: sau khi tính một routeKey, lookup tới channel theo map thay vì nhiều điều kiện rẽ nhánh phân tán.
4. **Chia domain rule hợp lý**: payment rules không nên nằm cùng một rule chain với document ingestion nếu không có yêu cầu.
5. **Tổ chức thứ tự điều kiện có chủ đích**: kiểm tra điều kiện rẻ trước nhưng không làm thay đổi precedence nghiệp vụ.
6. **Tránh regex không kiểm soát**: giới hạn pattern, input length và không cho user upload biểu thức/script tùy ý.
7. **Giảm I/O trong predicate**: cache có TTL/phiên bản hoặc enrichment ở bước riêng; xem xét tính nhất quán dữ liệu.
8. **Không tạo Dynamic IntegrationFlow cho từng message** khi một router và tập channel cố định đủ dùng.

### 14.1. Rule precedence và tính giải thích được

Nếu có nhiều rule cùng khớp, cần quy định:

- **First match wins**: một route được chọn theo thứ tự ưu tiên rõ ràng.
- **Highest priority wins**: chọn rule có priority lớn nhất, tie-break có định nghĩa.
- **All matches**: fan-out tới tất cả recipient phù hợp nhưng phải có maxFanout và dedup recipient identity.

Không trộn ba semantics trong cùng một router mà không công bố hợp đồng. Khi cập nhật runtime, một thay đổi thứ tự rule có thể đổi route dù mọi predicate giữ nguyên.

**Khuyến nghị:** giữ kết quả đánh giá dễ giải thích, ví dụ decision có **routeKey, policyVersion, ruleId**. Nếu cần ghi log lý do chi tiết, lưu ruleId có tập giá trị nhỏ thay vì toàn bộ biểu thức hoặc payload.

### 14.2. Khi nào nên chia router thành nhiều tầng?

Chia một router 100 rule thành 10 router không tự động tốt hơn. Nó có thể giảm số predicate xét trên từng message nếu tầng đầu chọn đúng domain, nhưng cũng có thể tạo thêm hop, channel, lỗi và ranh giới transaction.

Đánh giá theo **critical path latency**, số quyết định trung bình, khả năng observability và mức độ ổn định của topology. Nếu một tầng có khả năng rẽ sang mọi tầng khác, chi phí và độ khó hiểu có thể còn tăng.

## 15. Unit test cho policy snapshot

Điều cần chứng minh không chỉ là route đúng khi khởi động, mà còn:

- Candidate hợp lệ mới được kích hoạt.
- Decision luôn trả route key trong tập cho phép.
- Một quyết định sử dụng đồng nhất **routeKey + policyVersion**.
- Sau khi cập nhật, chính sách mới có tác dụng với message mới.
- Version cũ hoặc trùng không âm thầm ghi đè version hiện hành.

### 15.1. Cập nhật policy nhưng không tăng topology

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.Set;

import org.junit.jupiter.api.Test;

class BoundedRoutingPolicyTest {

    @Test
    void newSnapshotChangesDecisionWithinFixedRouteKeys() {
        BoundedRoutingPolicy policy = new BoundedRoutingPolicy(
                new RoutePolicySnapshot(
                        1,
                        new BigDecimal("10000000"),
                        Set.of("HAZMAT")));

        DispatchRequested event = new DispatchRequested(
                "evt-100", "tenant-A", "NORMAL",
                new BigDecimal("5000000"));

        RoutedDispatch before = policy.decide(event);
        assertEquals("STANDARD", before.routeKey());
        assertEquals(1, before.policyVersion());

        policy.activate(new RoutePolicySnapshot(
                2,
                new BigDecimal("1000000"),
                Set.of("HAZMAT")));

        RoutedDispatch after = policy.decide(event);
        assertEquals("REVIEW", after.routeKey());
        assertEquals(2, after.policyVersion());
    }

    @Test
    void rejectsBackwardVersionAndExcessiveRules() {
        BoundedRoutingPolicy policy = new BoundedRoutingPolicy(
                new RoutePolicySnapshot(
                        5, new BigDecimal("10000000"), Set.of()));

        assertThrows(IllegalArgumentException.class,
                () -> policy.activate(
                        new RoutePolicySnapshot(
                                4, new BigDecimal("100000"), Set.of())));

        assertEquals(5, policy.currentSnapshot().version());
        assertThrows(IllegalArgumentException.class,
                () -> new RoutePolicySnapshot(
                        6, BigDecimal.TEN, Set.of(
                                "C01","C02","C03","C04","C05",
                                "C06","C07","C08","C09","C10",
                                "C11","C12","C13","C14","C15",
                                "C16","C17")));
    }
}
~~~

Unit test **không cần Spring context**. Nó giúp kiểm soát policy engine trước khi ghép với IntegrationFlow.

### 15.2. Cập nhật đồng thời và snapshot consistency

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.junit.jupiter.api.Test;

class ConcurrentPolicySnapshotTest {

    @Test
    void eachDecisionUsesOneCompleteSnapshot() throws Exception {
        BoundedRoutingPolicy policy = new BoundedRoutingPolicy(
                new RoutePolicySnapshot(
                        1, new BigDecimal("10000000"), Set.of()));
        DispatchRequested event = new DispatchRequested(
                "evt-101", "tenant-A", "NORMAL",
                new BigDecimal("5000000"));

        ExecutorService pool = Executors.newFixedThreadPool(6);
        CountDownLatch start = new CountDownLatch(1);

        try {
            List<Future<RoutedDispatch>> results = new ArrayList<>();
            for (int i = 0; i < 200; i++) {
                results.add(pool.submit(() -> {
                    start.await();
                    return policy.decide(event);
                }));
            }
            start.countDown();

            policy.activate(new RoutePolicySnapshot(
                    2, new BigDecimal("1000000"), Set.of()));

            for (Future<RoutedDispatch> result : results) {
                RoutedDispatch d = result.get();
                boolean fromVersion1 =
                        d.policyVersion() == 1
                                && "STANDARD".equals(d.routeKey());
                boolean fromVersion2 =
                        d.policyVersion() == 2
                                && "REVIEW".equals(d.routeKey());
                assertTrue(fromVersion1 || fromVersion2);
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Test chấp nhận **cả version 1 và version 2** vì các thread có thể bắt đầu trước hoặc sau lần activate. Điều nó kiểm tra là **không có tổ hợp nửa cũ nửa mới**, ví dụ version 1 nhưng route REVIEW theo ngưỡng version 2.

Test này chỉ chứng minh AtomicReference snapshot trong **một JVM**. Nó không chứng minh tất cả replica được cập nhật đồng thời hoặc mọi message của một business workflow dùng chung version. Các yêu cầu đó cần integration test với nhiều instance và state store.

## 16. Test hop guard và kiểm tra cycle

### 16.1. Test dừng đúng ngân sách hop

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class RouteHopGuardTest {

    @Test
    void permitsEightHopsButRejectsTheNinth() {
        RouteHopGuard guard = new RouteHopGuard(8);
        Message<?> current =
                MessageBuilder.withPayload("dispatch").build();

        for (int i = 0; i < 8; i++) {
            current = guard.enterNextRouter(current);
        }

        assertEquals(8,
                current.getHeaders().get("trustedRouteHops"));

        Message<?> exhausted = current;
        assertThrows(IllegalStateException.class,
                () -> guard.enterNextRouter(exhausted));
    }

    @Test
    void rejectsMalformedHopHeader() {
        RouteHopGuard guard = new RouteHopGuard(8);

        Message<String> externalLikeMessage =
                MessageBuilder.withPayload("dispatch")
                        .setHeader("trustedRouteHops", "invalid")
                        .build();

        assertThrows(IllegalArgumentException.class,
                () -> guard.enterNextRouter(externalLikeMessage));
    }
}
~~~

**Lưu ý:** test này kiểm tra hàm guard, không chứng minh mọi đường đi trong Spring Integration đều gọi guard. Integration test còn phải tạo một cycle trong graph và xác minh flow dừng bằng error path có giới hạn thay vì chiếm thread hoặc queue vô tận.

### 16.2. Validator DAG đơn giản

Nếu hệ thống **không cho phép bất kỳ route cycle nào**, có thể kiểm tra candidate graph trước lúc activate:

~~~java
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

final class AcyclicRoutingGraphValidator {
    private static final int MAX_NODES = 100;
    private static final int MAX_EDGES = 200;

    private AcyclicRoutingGraphValidator() {}

    static void validate(Map<String, Set<String>> edges) {
        if (edges == null
                || edges.size() > MAX_NODES) {
            throw new IllegalArgumentException("Graph quá lớn");
        }
        long edgeCount = 0;
        for (Map.Entry<String, Set<String>> entry
                : edges.entrySet()) {
            if (entry.getKey() == null || entry.getValue() == null) {
                throw new IllegalArgumentException("Graph không hợp lệ");
            }
            edgeCount += entry.getValue().size();
            if (edgeCount > MAX_EDGES) {
                throw new IllegalArgumentException("Quá nhiều edges");
            }
            if (!edges.keySet().containsAll(entry.getValue())) {
                throw new IllegalArgumentException(
                        "Có destination chưa được khai báo");
            }
        }

        Set<String> done = new HashSet<>();
        Set<String> visiting = new HashSet<>();
        for (String node : edges.keySet()) {
            if (hasCycle(node, edges, done, visiting)) {
                throw new IllegalArgumentException(
                        "Routing graph có cycle");
            }
        }
    }

    private static boolean hasCycle(
            String node,
            Map<String, Set<String>> edges,
            Set<String> done,
            Set<String> visiting) {
        if (visiting.contains(node)) {
            return true;
        }
        if (done.contains(node)) {
            return false;
        }

        visiting.add(node);
        for (String next : edges.getOrDefault(node, Set.of())) {
            if (hasCycle(next, edges, done, visiting)) {
                return true;
            }
        }
        visiting.remove(node);
        done.add(node);
        return false;
    }
}
~~~

Ví dụ kiểm tra:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.Test;

class AcyclicRoutingGraphValidatorTest {

    @Test
    void acceptsSimpleAcyclicGraph() {
        assertDoesNotThrow(() ->
                AcyclicRoutingGraphValidator.validate(Map.of(
                        "ingress", Set.of("router"),
                        "router", Set.of("review", "standard"),
                        "review", Set.of(),
                        "standard", Set.of())));
    }

    @Test
    void rejectsCycleReturningToIngress() {
        assertThrows(IllegalArgumentException.class, () ->
                AcyclicRoutingGraphValidator.validate(Map.of(
                        "ingress", Set.of("router"),
                        "router", Set.of("ingress"))));
    }
}
~~~

Đây là validator cho **một graph trừu tượng đã liệt kê đầy đủ node và edge**. Việc trích xuất topology Spring Integration từ ApplicationContext, subflow, Control Bus và các route được tính bằng code không phải lúc nào cũng xác định tĩnh được. Nếu edge phụ thuộc vào data/runtime, cần kết hợp kiểm tra tĩnh với **hop guard**, số attempt tối đa và integration tests thực.

Trong ứng dụng có vòng nghiệp vụ hợp lệ, hãy dùng validator riêng nhận biết các cạnh lặp được phê duyệt, không thay vì bỏ hẳn mọi kiểm soát cycle.

## 17. Kiểm thử thay thế mapping mà không lộ trạng thái trung gian

### 17.1. Candidate invalid không được tác động bảng hiện tại

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.integration.router.HeaderValueRouter;

class SafeMappingUpdaterTest {

    @Test
    void rejectUnauthorizedDestinationWithoutChangingMappings() {
        HeaderValueRouter router =
                new HeaderValueRouter("trustedRoute");
        router.setChannelMappings(
                Map.of("STANDARD", "standardChannel"));

        SafeMappingUpdater updater = new SafeMappingUpdater();
        Map<String, String> before =
                Map.copyOf(router.getChannelMappings());

        assertThrows(IllegalArgumentException.class,
                () -> updater.activate(router,
                        Map.of("STANDARD", "privilegedOpsChannel")));

        assertEquals(before, router.getChannelMappings());
    }
}
~~~

Test này không cần có subscriber để xác minh validation của mapping. Với một ứng dụng thật, hãy thêm **integration test đồng thời**: nhiều message gửi trong lúc thay mapping A/B, đảm bảo mỗi message chỉ được route theo một bảng hợp lệ và không quan sát tổ hợp cấu hình trung gian.

### 17.2. Những ca cần chạy với Spring context thật

| Trường hợp | Kết quả kỳ vọng |
| --- | --- |
| Candidate ít rule, all channels tồn tại | Kích hoạt thành công, route như dự kiến |
| Candidate có channel ngoài allowlist | Bị từ chối trước khi apply |
| Candidate tạo cycle R1 → R2 → R1 | Bị validator chặn hoặc hop guard dừng |
| Candidate tăng fan-out quá max | Reject hoặc dùng quy trình phê duyệt đặc biệt |
| Một channel bị tháo trong khi còn message | Chính sách drain/stop/quarantine có hiệu lực |
| Đổi mapping hai key liên quan | Không phát sinh tổ hợp tạm ngoài ý muốn |
| Cập nhật snapshot khi đang route | Decision chứa version và key nhất quán |
| Ba instance ở version khác nhau | Phát hiện skew, áp dụng rollout policy |
| Replay event sau khi nâng version | Dùng route đã pin hoặc tính lại theo hợp đồng |
| Timeout của predicate remote | Giới hạn lỗi, không kéo treo router vô hạn |
| Unknown routing key | Default/quarantine hoặc fail fast theo chính sách |
| DirectChannel không có subscriber | Phát hiện lỗi wiring, không coi là key unknown |
| Retry sau partial side effect | Không tạo effect nghiệp vụ trùng |

### 17.3. Property-based và tải

Ngoài test từng trường hợp, có thể tạo hàng nghìn input hợp lệ/ngẫu nhiên và kiểm tra **invariant**:

- Route key luôn thuộc tập **STANDARD/REVIEW** (hoặc tập route hợp lệ đã thiết kế).
- Không có tên channel nào nằm ngoài allowlist.
- Số recipient được chọn không vượt maxFanout.
- Số hop trong một attempt không vượt maxHops.
- Cùng policyVersion và cùng input có kết quả xác định, nếu predicate không phụ thuộc external state.
- Mọi candidate lỗi đều bị từ chối mà policy đang chạy không thay đổi.

Load test nên đo **latency p95/p99 của riêng routing decision**, tổng thời gian flow, CPU, queue depth, tỷ lệ send failures và lượng retry. Một router nhanh trên unit test có thể vẫn là điểm nghẽn nếu nhiều nhánh downstream chậm hoặc ứng dụng tạo fan-out lớn.

## 18. Observability: đo đúng độ phức tạp

Theo dõi cả kết quả **quyết định** và mức độ **mở rộng của workflow**:

| Metric | Mục đích |
| --- | --- |
| **route_decisions_total{route,version}** | Bao nhiêu message chọn từng route/version |
| **route_decision_duration_seconds** | Thời gian tính key/chọn route |
| **route_rule_evaluation_errors_total** | Lỗi tính predicate |
| **route_candidate_rejected_total{reason}** | Candidate mới vượt budget hoặc lỗi validation |
| **route_policy_version_active{instance}** | Phát hiện replica chưa đồng bộ |
| **route_fanout_count** | Số recipient trên mỗi message |
| **route_hop_budget_exceeded_total** | Phát hiện cycle hoặc đường đi quá dài |
| **route_unmatched_total** | Route key không khớp mapping |
| **route_channel_resolution_errors_total** | Mapping tới channel không tồn tại |
| **route_send_failures_total{channel}** | Destination từ chối send |
| **route_queue_depth{channel}** | Backlog của các nhánh có queue |
| **route_replay_count** | Số event được xử lý lại |
| **route_idempotency_skips_total** | Số tác động nghiệp vụ trùng được ngăn |

Trong sản phẩm, nhiều label như **version**, **instance** hoặc **channel** có tập giá trị hữu hạn thì phù hợp. Không dùng **eventId, tenantId, userId hoặc raw routing key không kiểm soát** làm metric label vì cardinality có thể bùng nổ. Chi tiết từng event nên nằm trong tracing/log đã được lọc dữ liệu nhạy cảm.

### 18.1. Ghi lại nguyên nhân route

Một log có cấu trúc có thể chứa:

~~~json
{
  "eventId": "evt-100",
  "policyVersion": 12,
  "routeKey": "REVIEW",
  "matchedRuleId": "HIGH_VALUE",
  "hopCount": 2,
  "decisionDurationMs": 1.8,
  "status": "ROUTED"
}
~~~

Ví dụ chỉ minh họa log nội bộ; không cần log toàn bộ payload, thông tin thanh toán hay dữ liệu cá nhân. Khi có nhiều tenant, tenant ID cần được xử lý theo quyền truy cập và retention của hệ thống log.

### 18.2. Các dấu hiệu cần rollback

- Route decision p99 tăng mạnh ngay sau kích hoạt version mới.
- Tỷ lệ unknown key, failed resolution, hop-budget-exceeded hoặc fallback tăng bất thường.
- Fan-out trung bình hoặc p99 vượt ngân sách.
- Queue depth và tuổi message tăng dù inbound rate không đổi.
- Có đường loop mới, transaction timeout hoặc consumer lỗi lặp.
- Một số instance vẫn giữ policy cũ ngoài thời hạn rollout.
- Lưu lượng vào một nhánh quan trọng giảm về 0 mà không có kế hoạch.

**Rollback nên là thao tác có kiểm soát**, không chỉ đổi lại một mapping bằng tay. Nếu có message đã đi vào nhánh mới và thực hiện side effect, rollback không tự hoàn tác các hiệu ứng đó; cần kiểm soát idempotency và xử lý các message còn tồn đọng.

## 19. Runbook cập nhật Dynamic Router an toàn

Một thay đổi runtime cần quy trình tương đương một bản triển khai nhỏ. Ví dụ đội vận hành muốn chuyển REVIEW từ reviewChannel sang reviewBackupChannel trong giờ bảo trì.

### Bước 1 — Tạo candidate và lý do thay đổi

Lưu:

- Candidate policyVersion.
- Thời điểm dự kiến kích hoạt.
- Routing keys, destination và rule logic mới.
- Danh sách channel/handler bị ảnh hưởng.
- Trạng thái tương thích của nhánh cũ và nhánh mới.
- Người đề xuất, phê duyệt và kế hoạch rollback.

Không cập nhật một mapping chỉ vì một request nghiệp vụ gửi tên destination mới. Mọi candidate phải xuất phát từ nguồn quản trị có quyền và có audit trail.

### Bước 2 — Validate offline trước khi đụng vào live router

1. Kiểm tra schema, version, rule count, fan-out/hop budgets.
2. Kiểm tra **allowlist** của tất cả destination.
3. Kiểm tra channel bean/endpoint cần thiết có tồn tại và healthy.
4. Kiểm tra graph cycle và duplicate route identity.
5. Chạy các test route cho những event mẫu quan trọng và edge cases.
6. Kiểm tra resource budget nếu nhánh mới có throughput thấp hơn.
7. Xác minh các message trong flight sẽ được xử lý thế nào khi chuyển đích.

Nếu candidate không đạt, **không thay đổi** live router. Ghi lý do reject để hỗ trợ người vận hành sửa policy.

### Bước 3 — Triển khai thay đổi nguyên tử ở phạm vi hỗ trợ

- Với bảng mapping: dùng **setChannelMappings(Map)** hoặc **replaceChannelMappings(Properties)** để thay **toàn bộ bảng** khi nhiều key liên quan.
- Với policy thuần Java: build **snapshot bất biến**, rồi thay tham chiếu **một lần**.
- Với nhiều instance: triển khai phiên bản có điều phối và theo dõi version skew.
- Nếu dùng RecipientListRouter management với nhiều thao tác add/remove: đừng mặc định một nhóm thao tác rời là atomic; thiết kế staging/version rõ ràng nếu yêu cầu nhất quán.

### Bước 4 — Quan sát canary và vận hành

Theo dõi route decision, response latency, queue depth, error channel, retry và side effect duplicate. Nếu nhánh mới chỉ được dùng cho một phần traffic, canary phải có **quy tắc chọn cohort ổn định** để cùng một event qua retry không bị chuyển qua lại ngoài ý định.

Một logic canary phụ thuộc vào số ngẫu nhiên **mỗi lần nhận** dễ khiến cùng event vào nhánh A ở attempt đầu và nhánh B ở attempt sau. Thay vào đó, cân nhắc quyết định cohort từ **hash của một stable business key**, hoặc lưu route decision của event tại ingress.

### Bước 5 — Rollback hoặc hoàn tất

Khi có sự cố, phát hành version mới trỏ về cấu hình an toàn trước đó. Đánh dấu các message đã được route bởi version lỗi, theo dõi backlog và xác định có cần replay/reconciliation hay không.

**Rollback mapping không tương đương rollback transaction.** Những task đã gửi email, giữ hàng, thu tiền hoặc gọi đối tác không tự quay về trạng thái trước khi đổi mapping.

## 20. Các lỗi thiết kế hay gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Cho phép runtime thêm rule không giới hạn | Chi phí routing và vận hành tăng không đoán trước | MAX_RULES và validation candidate |
| Cho client cung cấp tên channel trực tiếp | Có thể gửi message vào channel nội bộ ngoài ý định | Allowlist mapping và channelKeyFallback(false) |
| Đổi từng mapping phụ thuộc nhau | Message có thể thấy bảng mapping hỗn hợp | Cập nhật toàn bảng atomically trong phạm vi router |
| Dùng setDynamicChannelLimit để giới hạn fan-out | Hiểu nhầm API quản lý | Max recipients do ứng dụng kiểm tra riêng |
| Cho RecipientListRouter thêm nhiều bản ghi cùng recipient | Duplicate deliveries/side effects | Dùng identity duy nhất, gộp selector |
| Dùng mỗi maxHops nhưng không giới hạn fan-out | Một vài tầng vẫn có thể tạo quá nhiều nhánh | Cả maxHops, maxFanout và total deliveries |
| Chỉ kiểm tra DAG tĩnh | Rule động vẫn có thể tạo vòng lặp không nhận diện | Runtime hop/attempt guard và test |
| Chỉ có hop guard runtime | Cấu hình sai vẫn được kích hoạt và gây lỗi | Preflight topology validation |
| Mỗi predicate gọi API ngoài không timeout | Route decision giữ thread lâu, quá tải | Enrichment riêng, timeout/backoff có giới hạn |
| Dùng một mutable Map bị sửa từng entry | Message nhìn thấy cấu hình tạm thời | Immutable snapshot / full-table replacement |
| Chỉ cập nhật policy trong một JVM | Replica dùng các version khác nhau | Version rollout, xác nhận đồng bộ |
| Gửi lại event và tính route mới không kiểm soát | Side effect có thể chạy ở hai nhánh | Pin route hoặc idempotency theo logical action |
| Dùng default channel để nuốt mọi lỗi | Che lỗi handler và mất message | Phân biệt unknown route với downstream error |
| Dùng ignoreSendFailures thay recovery | Nhánh bắt buộc có thể không hoàn tất | Error flow, retry, durable messaging và monitoring |
| Mở Control Bus cho request chưa xác thực | Cho phép thao tác runtime cấu hình trái quyền | Quản trị riêng, RBAC và audit |
| Không kiểm thử khi tăng số recipient | Backlog, thread pool và hệ thống đích quá tải | Load test, canary và capacity planning |

## 21. Bài thực hành: Dynamic Router có ngân sách

Thiết kế một luồng nhận:

~~~java
record InvoiceIssued(
        String eventId,
        String tenantId,
        String countryCode,
        java.math.BigDecimal totalVnd,
        String customerTier) {}
~~~

Các destination được phép:

| Route key | Channel | Ý nghĩa |
| --- | --- | --- |
| STANDARD | invoiceStandardChannel | Xử lý hóa đơn tiêu chuẩn |
| REVIEW | invoiceReviewChannel | Kiểm tra hóa đơn cần review |
| HOLD | invoiceHoldChannel | Giữ để đối soát |
| QUARANTINE | invoiceQuarantineChannel | Dữ liệu/rule chưa phù hợp |

**Yêu cầu kỹ thuật**

1. Policy runtime thay đổi được ngưỡng review và danh sách countryCode cần giữ HOLD.
2. Mọi policy là snapshot bất biến có version, được validate trước khi activate.
3. Không có hơn 20 rule và không route đến channel ngoài bảng cho phép.
4. Không nhiều hơn hai recipient nếu một event phải gửi thêm audit theo yêu cầu.
5. Không quá 8 routing hops trong một attempt.
6. Policy và graph không được tạo một cycle không có cơ chế dừng rõ ràng.
7. Route decision chứa policyVersion và routeKey đã chọn.
8. Replay cùng eventId phải dùng route decision cũ hoặc theo một quy tắc tính lại đã được định nghĩa rõ.
9. Có fallback cho unknown key, nhưng lỗi gửi tới một channel đã chọn không bị coi là unknown key.
10. Có test cho update policy đồng thời, candidate bị từ chối và rollback.

**Các bước thực hành**

1. Viết InvoiceRoutingPolicySnapshot có reviewThreshold, country codes và version; constructor kiểm tra schema và số phần tử.
2. Viết InvoiceRouterPolicy dùng AtomicReference và một method decide() không gọi I/O.
3. Dùng IntegrationFlow Java DSL với các channelMapping tường minh và channelKeyFallback(false).
4. Tạo adapter cập nhật candidate qua một service nội bộ, không trực tiếp từ API người dùng.
5. Viết SafeMappingUpdater có allowlist và số entry tối đa.
6. Xây dựng một graph validator; tạo test phát hiện cycle quay về input.
7. Viết RouteHopGuard và test đến hop thứ 8 thì dừng ở lần tiếp theo.
8. Cho 200 request vào router trong lúc activate policy mới; kiểm tra routeKey/version luôn hợp lệ.
9. Thử thêm một recipient audit rồi mô phỏng send failure; xác định cơ chế retry/idempotency riêng cho audit.
10. Đưa ra checklist rollout với canary, metrics, policy version skew và rollback.

### Bài toán mở rộng: dynamic routing cho nhiều tenant

Giả sử mỗi tenant muốn chọn chính sách review riêng. Không nên tạo một IntegrationFlow mới cho **từng request**. Có thể quản lý **một tập policy hữu hạn** theo tenant group hoặc một registry policy versioned.

Hãy phân tích:

- Tenant nào được phép có custom policy?
- Mỗi tenant được phép bao nhiêu rule?
- Khi số tenant tăng 1.000 lần, bộ nhớ và thời gian tải policy tăng ra sao?
- Policy cũ tồn tại bao lâu để replay?
- Một admin của tenant A có thể thêm channel thuộc tenant B không?
- Nếu một phiên bản policy bị lỗi, rollback trên những instance nào?

### Câu hỏi tự kiểm tra

1. Dynamic Router khác router có biểu thức cố định nhưng kết quả khác nhau theo message như thế nào?
2. Ba giai đoạn compute key, map key và resolve channel diễn ra theo thứ tự nào?
3. Vì sao số rule nhỏ chưa đủ chứng minh route sẽ nhanh?
4. F=3, H=4 có thể dẫn đến bao nhiêu vị trí xử lý trong cây fan-out đầy đủ?
5. Khi nào cần cả graph validation và hop guard?
6. Có thể dùng setDynamicChannelLimit để ngăn fan-out quá lớn không?
7. Cập nhật hai key bằng hai lời gọi setChannelMapping có nguyên tử không?
8. Khi nào nên dùng setChannelMappings hoặc replaceChannelMappings?
9. Vì sao AtomicReference chưa đủ đảm bảo các instance dùng cùng một policyVersion?
10. Replay sau khi đổi mapping có thể gây duplicate side effect như thế nào?
11. Default output channel có tự bắt exception của downstream handler không?
12. Khi nào nên dùng canary theo stable eventId thay vì random trên mỗi attempt?

## 22. Checklist trước khi đưa Dynamic Router vào production

- Mọi rule và destination được mô tả bằng **schema có version**.
- Có **ngân sách số rule, chi phí predicate, maxFanout, maxHops và queue capacity**.
- Rule mới được validate trước khi kích hoạt, không sửa trực tiếp vào cấu hình sống.
- Routing key đến từ input đã xác thực/chuẩn hóa, không từ tên bean tùy ý.
- **channelKeyFallback(false)** và allowlist được áp dụng khi nguồn không tin cậy.
- Mapping được thay **như một đơn vị** nếu nhiều key phụ thuộc nhau.
- Nếu có RecipientListRouter runtime, candidate recipient set được kiểm tra duplicate và fan-out.
- Graph validation phát hiện cycle hoặc đòi hỏi cơ chế dừng cho vòng lặp hợp lệ.
- Runtime guard được gọi ở mọi ranh giới routing cần tính hop.
- Policy snapshot immutable và route decision có policyVersion.
- Có chính sách replay: pin route cũ hoặc tính lại được định nghĩa minh bạch.
- Có idempotency theo logical action khi route có thể đổi giữa các attempt.
- Error handling phân biệt unknown route, missing channel và downstream failure.
- Control Bus/JMX/API quản trị được bảo vệ, ghi audit và có quy trình rollback.
- Hệ thống đa instance theo dõi version skew và canary rollout.
- Metrics/tracing đo route decision latency, fan-out, hop, queue depth, retry và lỗi.
- Kiểm thử đơn vị, tích hợp, concurrency, cycle, tải và restart tương ứng với yêu cầu độ bền.

**Kết luận:** Giới hạn độ phức tạp của Dynamic Router không phải việc cố định tất cả route mãi mãi. Mục tiêu là **cho phép chính sách thay đổi trong một phạm vi được kiểm chứng**. Kết hợp **tập channel hữu hạn**, **snapshot nguyên tử**, **ngân sách rule/fan-out/hop**, **kiểm tra topology**, **bảo mật Control Bus**, **theo dõi version** và **kiểm thử replay** giúp Spring Integration giữ tính linh hoạt runtime mà không đánh đổi khả năng dự đoán và vận hành.

## Tài liệu tham khảo

- [Spring Integration Reference — Dynamic Routers](https://docs.spring.io/spring-integration/reference/router/dynamic-routers.html): ba bước resolve destination, cập nhật mappings, quản lý Control Bus/JMX và thay bảng nguyên tử.
- [Spring Integration Reference — Router Implementations](https://docs.spring.io/spring-integration/reference/router/implementations.html): HeaderValueRouter, RecipientListRouter và cấu hình Java/Java DSL.
- [Spring Integration API — AbstractMappingMessageRouter](https://docs.spring.io/spring-integration/api/org/springframework/integration/router/AbstractMappingMessageRouter.html): setChannelMappings, replaceChannelMappings, channelKeyFallback và setDynamicChannelLimit.
- [Spring Integration Reference — Common Router Parameters](https://docs.spring.io/spring-integration/reference/router/common-parameters.html): defaultOutputChannel, resolutionRequired, ignoreSendFailures và sendTimeout.
- [Spring Integration Reference — Control Bus](https://docs.spring.io/spring-integration/reference/control-bus.html): điều khiển các component tại runtime và biện pháp quản trị.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): IntegrationFlow, router, Transformer và nhánh xử lý.
- [Spring Integration Reference — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html): đồng bộ/bất đồng bộ, queue, executor và các semantics liên quan.
- [Enterprise Integration Patterns — Dynamic Router](https://www.enterpriseintegrationpatterns.com/patterns/messaging/DynamicRouter.html): nền tảng thiết kế Dynamic Router.
