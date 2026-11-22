# Gather kết quả từ các nhánh song song

## 1. Bối cảnh: nhiều nhánh xử lý, một quyết định chung

Trong chương **Scatter gather** của module **SPRING_INTEGRATION_PATTERN**, chúng ta học triển khai các Enterprise Integration Patterns bằng **Spring Integration** để xây dựng luồng message ít phụ thuộc và dễ mở rộng. Một message có thể được gửi đến nhiều nhánh xử lý độc lập; các nhánh thực hiện nghiệp vụ, trả kết quả rồi được tập hợp thành một response chung. Mẫu này kết hợp tự nhiên với Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, correlation và kiểm thử.

Giả sử một hệ thống cần **tìm báo giá vận chuyển tốt nhất** cho đơn hàng. Mỗi request được hỏi đồng thời tới ba nhà cung cấp:

- **warehouseSupplier**: báo giá kho nội bộ.
- **partnerSupplier**: báo giá đối tác vận chuyển.
- **backupSupplier**: báo giá dự phòng.

Mỗi nhà cung cấp trả về giá và trạng thái. Ứng dụng muốn nhận **một QuoteReport** gồm cả ba kết quả, ghi rõ nhà cung cấp nào không phản hồi hoặc từ chối báo giá, và chọn giá hợp lệ thấp nhất.

~~~mermaid
flowchart LR
    Q["QuoteRequest"] --> S["Scatter"]
    S --> A["Warehouse supplier"]
    S --> B["Partner supplier"]
    S --> C["Backup supplier"]
    A -->|"SupplierOutcome"| G["Gather / Aggregator"]
    B -->|"SupplierOutcome"| G
    C -->|"SupplierOutcome"| G
    G --> R["QuoteReport + best offer"]
~~~

Nếu các nhà cung cấp có độ trễ khác nhau, phản hồi có thể đến theo thứ tự **partner → backup → warehouse**, không phải thứ tự gửi request. Gather phải nhận diện **những reply thuộc cùng request**, biết khi nào đủ điều kiện kết thúc và không trộn kết quả của hai khách hàng khác nhau.

**Mục tiêu bài học**

1. Phân biệt **Scatter**, **Gather** và **Aggregator**; phân biệt fan-out với xử lý song song thật sự.
2. Hiểu hai kiểu **auction** và **distribution** trong Spring Integration.
3. Thiết kế correlationId, sequenceNumber, sequenceSize và replyChannel để Gather nhận đủ kết quả đúng nhóm.
4. Viết Java DSL dùng ScatterGatherHandler, RecipientListRouter và Aggregator, với nhánh chạy trên bounded Executor.
5. Xác định release strategy, gatherTimeout, groupTimeout, partial result và late arrival.
6. Xử lý một nhánh lỗi mà không mặc định làm mất toàn bộ kết quả, đồng thời không che lỗi hệ thống.
7. Kiểm thử tập hợp đủ kết quả, thứ tự phản hồi bất kỳ, hai request đồng thời, thiếu reply, duplicate và retry.

## 2. Gather thực sự có trách nhiệm gì?

**Scatter** phát một yêu cầu tới nhiều recipient hoặc nhiều sub-flow. **Gather** nhận các reply tương ứng và kết hợp chúng thành một output theo hợp đồng nghiệp vụ.

~~~text
Request
  |
  +-- scatter --> Supplier A -- reply A --+
  +-- scatter --> Supplier B -- reply B --+--> Gather --> Report
  +-- scatter --> Supplier C -- reply C --+
~~~

Gather thường thực hiện bốn việc:

1. **Correlation**: xác định reply nào thuộc cùng một request.
2. **Accumulation**: giữ các reply trong một MessageGroup hoặc cơ chế lưu trạng thái tương đương.
3. **Release**: quyết định đã có đủ thông tin để kết thúc nhóm hay chưa.
4. **Aggregation**: chuyển các reply thành một kết quả cuối cùng có ý nghĩa.

Gather **không tự** xác nhận tất cả hệ thống ngoài đã commit, không tự chống duplicate effect và không tự biết một nhà cung cấp im lặng là lỗi hay kết quả hợp lệ. Những điều đó phải được định nghĩa bởi nghiệp vụ và error/recovery policy.

### 2.1. Gather khác với chỉ nối các message

Nếu ba nhánh cùng gửi vào một channel và có một consumer nhận lần lượt, đó mới là **thu thập message về một nơi**. Để tạo một response đúng, consumer cần biết:

- Request gốc nào sinh ra các reply?
- Dự kiến có bao nhiêu reply?
- Reply thứ hai đến có phải bản lặp của cùng supplier không?
- Khi nào ngừng chờ?
- Một supplier bị lỗi có được tính là đã phản hồi chưa?
- Có được chọn ngay giá đầu tiên hay phải xem hết báo giá?

**Gather** là một điểm đồng bộ hóa kết quả theo hợp đồng, không chỉ là một channel hội tụ.

### 2.2. Scatter-Gather khác Splitter-Aggregator

| Khía cạnh | Scatter-Gather | Splitter-Aggregator |
| --- | --- | --- |
| Input | Một request cần hỏi nhiều recipient | Một payload gồm nhiều item cần chia |
| Scatter/Split | Gửi request tới nhiều nhà cung cấp/nhánh | Tạo child message từ collection hoặc payload |
| Các nhánh xử lý | Thường xử lý các góc nhìn/dịch vụ khác nhau | Thường xử lý các item cùng loại |
| Gather/Aggregate | Hợp nhất các supplier replies | Ghép child results thành batch result |
| Correlation | Liên kết reply về đúng request | Liên kết các child về đúng message cha |
| Timeout | Quan trọng với supplier chậm/mất reply | Quan trọng với child mất hoặc lỗi |

Cả hai đều có thể dùng AggregatingMessageHandler. Tuy nhiên **một request được broadcast tới nhiều supplier** khác với **một danh sách 100 item được Splitter tách ra**; đừng thay tên pattern mà bỏ qua semantics.

## 3. Hai kiểu Scatter-Gather mà Spring Integration hỗ trợ

Spring Integration cung cấp **ScatterGatherHandler** là endpoint request/reply, phối hợp một bên phát request và một bên AggregatingMessageHandler. Có hai biến thể chính:

### 3.1. Auction: phát request tới tất cả subscriber

Biến thể **auction** dùng **PublishSubscribeChannel**. Mỗi subscriber hợp lệ nhận một bản message request; tất cả được mời trả lời để chọn hoặc tổng hợp một kết quả.

Ví dụ: ba nhà vận chuyển đều được hỏi giá để chọn báo giá tốt nhất.

~~~mermaid
flowchart TB
    I["Một request"] --> P["PublishSubscribeChannel"]
    P --> S1["Subscriber A"]
    P --> S2["Subscriber B"]
    P --> S3["Subscriber C"]
    S1 --> G["Gather"]
    S2 --> G
    S3 --> G
~~~

**Lưu ý quan trọng:** PublishSubscribeChannel không có TaskExecutor mặc định sẽ gọi subscribers trên **thread của sender**. Chỉ vì có ba subscriber không có nghĩa chúng chạy song song; muốn parallelism cần Executor phù hợp hoặc một ranh giới bất đồng bộ trong mỗi sub-flow.

Khi cần Aggregator dùng sequence metadata, đặt **applySequence(true)** cho PublishSubscribeChannel nếu cấu hình channel trực tiếp. Với DSL Scatter-Gather từ Spring Integration **6.0**, framework thiết lập applySequence=true thuận tiện cho các biến thể mà nó tạo ra; nếu tự dựng router/channel hoặc dùng phiên bản cũ, phải xác minh cấu hình thực tế.

### 3.2. Distribution: chọn recipient theo điều kiện

Biến thể **distribution** dùng **RecipientListRouter**. Chỉ các recipient có selector phù hợp nhận request.

Ví dụ: với đơn hàng quốc tế mới hỏi thêm customsSupplier; các đơn nội địa chỉ hỏi hai nhà vận chuyển.

~~~mermaid
flowchart LR
    I["QuoteRequest"] --> R["RecipientListRouter"]
    R -->|"Luôn nhận"| A["Warehouse"]
    R -->|"Luôn nhận"| B["Partner"]
    R -->|"International only"| C["Customs"]
    A --> G["Gather"]
    B --> G
    C --> G
~~~

**Dự kiến bao nhiêu reply?** Nếu customs không được chọn, Gather phải kỳ vọng **2**, không phải 3. Đó là lý do applySequence của RecipientListRouter có ý nghĩa: sequenceSize cần phản ánh **số recipient thực sự được chọn**, không phải số mapping tối đa.

### 3.3. Chọn auction hay distribution?

| Nhu cầu | Lựa chọn thường hợp lý |
| --- | --- |
| Mọi supplier đều cần xem request | Auction / PublishSubscribeChannel |
| Recipient chỉ tham gia khi selector khớp | Distribution / RecipientListRouter |
| Cần chọn báo giá thấp nhất từ các supplier được mời | Cả hai; Gather xử lý kết quả |
| Cần tự chạy nhiều thread | Executor trên PublishSubscribeChannel hoặc từng nhánh |
| Cần kết quả của mọi nhánh bắt buộc | Release theo số reply kỳ vọng, fail/timeout rõ |
| Chấp nhận một số supplier không phản hồi | Terminal failure outcome hoặc partial release có trạng thái |

Đừng dùng RecipientListRouter chỉ để mô phỏng thao tác Splitter chia từng dòng trong một list nếu nhu cầu thật là xử lý từng item. Đặt đúng pattern làm cho correlation và trách nhiệm của từng reply dễ hiểu hơn.

## 4. Correlation, sequence và replyChannel là hợp đồng của Gather

Để Aggregator ghép chính xác ba báo giá, mỗi reply cần giữ metadata liên kết với request cha.

| Thông tin | Vai trò |
| --- | --- |
| **requestId** | Định danh nghiệp vụ ổn định qua retry |
| **correlationId** | Nhóm các message reply trong một lần Scatter-Gather |
| **sequenceNumber** | Vị trí logical recipient/nhánh trong tập |
| **sequenceSize** | Số reply mà nhóm dự kiến nhận |
| **replyChannel** | Destination để nhánh trả reply về Gather |
| **errorChannel** | Destination xử lý lỗi của request/nhánh |
| **supplierId** | Danh tính logical của nguồn kết quả, phục vụ chống trùng và audit |

Nếu ba supplier được chọn:

~~~text
Request req-701:
  warehouse -> correlation=G-701, sequenceNumber=1, sequenceSize=3
  partner   -> correlation=G-701, sequenceNumber=2, sequenceSize=3
  backup    -> correlation=G-701, sequenceNumber=3, sequenceSize=3
~~~

Nếu một request mới **req-702** chạy đồng thời, nó phải có một correlation group riêng, ví dụ G-702. Không dùng một key cố định như "quotes" cho mọi request, vì có nguy cơ trộn kết quả giữa các khách hàng.

### 4.1. replyChannel của từng supplier

Trong **ScatterGatherHandler**, framework tạo một reply destination cho Gather (nếu không có gatherChannel bên ngoài), rồi làm giàu message scatter bằng header để hướng các reply về đó.

Do đó, trong từng recipient sub-flow:

- Nếu muốn trả kết quả cho Gather, endpoint cuối phải **tạo reply không null**.
- Không cấu hình outputChannel tường minh sang nơi khác nếu muốn framework sử dụng replyChannel của request.
- Nếu chuyển message qua broker hoặc tái tạo Message thủ công, cần kiểm tra việc **giữ correlation, sequence và reply metadata** theo khả năng serialization của adapter.
- Nếu handler one-way trả null, Gather sẽ **không có reply** của nhánh đó; group có thể không bao giờ đủ.

Tài liệu Spring Integration cũng nêu có thể cấu hình **gatherChannel** tường minh để các supplier gửi reply vào channel đó. Đây là một lựa chọn kiến trúc; không nhất thiết phải dùng khi các sub-flow local có thể trả reply theo header.

### 4.2. Sequence không phải idempotency key

SequenceNumber=2 chỉ nói đây là **phản hồi có vị trí số 2** trong nhóm, không chứng minh nhà cung cấp đã xử lý thành công, cũng không đảm bảo event chỉ được gửi một lần.

Với retry:

~~~text
idempotencyKey = trustedTenantId + ":" + requestId + ":" + supplierId
~~~

Một retry từ partner dùng lại requestId và supplierId để tránh gửi lặp tác động có side effect. Nhưng một lượt so sánh giá mới, có chủ đích, có thể cần requestId mới dù sku giữ nguyên.

### 4.3. Mất header hoặc sai correlation có hậu quả gì?

- Không có **correlationId** phù hợp: reply không được gom vào đúng nhóm.
- **sequenceSize=0/thiếu** mà dùng release strategy mặc định: Gather có thể không biết đã đủ.
- Mỗi branch tạo correlationId mới: không có nhóm nào đủ số lượng.
- Một branch làm mất **replyChannel**: reply không về Gather.
- Một branch trả về message không giữ metadata request cần thiết: có thể lỗi routing hoặc timeout.
- Copy header do khách hàng tự cung cấp mà không xác minh: có thể làm lộ error/reply ra channel ngoài ý định.

Chỉ số correlation của framework phục vụ **kết hợp các message trong lần xử lý**; nếu cần đối soát và khôi phục qua restart, phải bổ sung **requestId nghiệp vụ** và trạng thái bền.

## 5. Khi nào Gather được phép release?

Với ba nhánh bắt buộc, quy tắc thông thường là **đợi đủ ba reply**. Aggregator mặc định có thể dùng SimpleSequenceSizeReleaseStrategy: so sánh quy mô nhóm với sequence metadata để quyết định release.

~~~mermaid
flowchart TD
    A["Reply tới Gather"] --> C["Tìm MessageGroup theo correlationId"]
    C --> S["Lưu reply trong MessageGroupStore"]
    S --> D{"ReleaseStrategy có đủ điều kiện?"}
    D -->|"Chưa đủ"| W["Tiếp tục đợi"]
    D -->|"Đủ"| G["MessageGroupProcessor / Aggregation"]
    G --> O["QuoteReport"]
~~~

### 5.1. Đợi tất cả vs chọn một phần đủ tốt

| Release policy | Khi dùng | Đổi lại |
| --- | --- | --- |
| **Tất cả N reply** | Tất cả supplier bắt buộc hoặc cần audit đầy đủ | Latency phụ thuộc nhánh chậm nhất |
| **Tối thiểu K reply** | Đủ dữ liệu để ra quyết định có kiểm soát | Có thể bỏ qua báo giá tốt hơn đến muộn |
| **Có ít nhất một offer đạt điều kiện** | Quyết định nhanh với một mục tiêu rõ | Cần chứng minh kết quả sớm đã đủ tốt |
| **Hết thời gian chờ** | Không thể giữ request vô hạn | Partial/incomplete phải được công bố |

**Không thay quy tắc tất cả N bằng size() >= K chỉ để tránh timeout**, nếu nghiệp vụ đòi đủ N. Một chiến lược K-of-N phải có hợp đồng rõ ràng về missing supplier, report status, late reply và khả năng một giá tốt hơn đến sau.

### 5.2. Một failure outcome có được tính là reply?

Có, nếu contract định nghĩa mỗi supplier trả **một SupplierOutcome terminal**:

- SUCCESS, có giá.
- UNAVAILABLE, không cung cấp được giá.
- REJECTED, từ chối hợp lệ theo nghiệp vụ.

Khi đó ba outcomes (trong đó một UNAVAILABLE) vẫn có thể làm group đủ **3/3**. Gather trả QuoteReport với **2 giá và 1 supplier unavailable**, chứ không giả vờ đủ ba báo giá hợp lệ.

Ngược lại, nếu nhánh chỉ ném exception rồi không trả message, Gather có thể **đợi thiếu reply**. ErrorMessage trên errorChannel không tự được tính là một SupplierOutcome trong group.

### 5.3. Không nhầm nhóm đầy đủ với mọi side effect đã commit

Aggregator chỉ biết những reply nó **nhận được**. Một supplier có thể trả trạng thái ACCEPTED nhưng chưa thật sự hoàn thành nghiệp vụ ở phía ngoài. Nếu Scatter-Gather được dùng cho thao tác thay đổi trạng thái (không chỉ lấy báo giá), cần xác định rõ ý nghĩa từng reply và idempotency ở mỗi branch.

## 6. Ví dụ Java 17: định nghĩa request, outcome và report

Ví dụ sau minh họa ba nhà cung cấp được hỏi báo giá. Chúng ta định nghĩa outcome có kiểu để ngay cả **nhánh từ chối cung cấp giá** vẫn trả một message cho Gather, thay vì im lặng.

### 6.1. Request và các kết quả

~~~java
import java.math.BigDecimal;
import java.util.List;

record QuoteRequest(
        String requestId,
        String sku,
        int quantity) {
    QuoteRequest {
        if (requestId == null || requestId.isBlank()
                || sku == null || sku.isBlank()
                || quantity <= 0 || quantity > 1000) {
            throw new IllegalArgumentException("INVALID_QUOTE_REQUEST");
        }
    }
}

record SupplierOutcome(
        String requestId,
        String supplierId,
        String status,
        BigDecimal totalPriceVnd,
        String errorCode) {

    static SupplierOutcome success(
            QuoteRequest request,
            String supplierId,
            BigDecimal price) {
        if (price == null || price.signum() <= 0) {
            throw new IllegalArgumentException("INVALID_SUPPLIER_PRICE");
        }
        return new SupplierOutcome(
                request.requestId(), supplierId,
                "SUCCESS", price, null);
    }

    static SupplierOutcome unavailable(
            QuoteRequest request,
            String supplierId,
            String errorCode) {
        return new SupplierOutcome(
                request.requestId(), supplierId,
                "UNAVAILABLE", null, errorCode);
    }
}

record QuoteReport(
        String requestId,
        int expectedSuppliers,
        int receivedOutcomes,
        String reportStatus,
        SupplierOutcome bestOffer,
        List<SupplierOutcome> outcomes) {}
~~~

**Hợp đồng mẫu:**

- SUCCESS đi kèm **totalPriceVnd** dương.
- UNAVAILABLE là một kết quả terminal **có ý nghĩa nghiệp vụ**, không có giá và có errorCode.
- Report phân biệt đầy đủ phản hồi (**receivedOutcomes=3**) với đầy đủ báo giá hợp lệ (**có thể chỉ 2 SUCCESS**).
- Nếu tất cả UNAVAILABLE, **bestOffer=null** có chủ đích và reportStatus phải nói rõ NO_OFFER.

Trong production nên dùng enum thay cho các chuỗi trạng thái và validate supplierId theo allowlist. requestId phải ổn định cho một yêu cầu logic; khi khách hàng chủ động yêu cầu báo giá mới, có thể cấp requestId mới.

### 6.2. Port của từng nhánh

~~~java
interface SupplierQuotePort {
    SupplierOutcome quote(QuoteRequest request);
}
~~~

Port có thể được triển khai bằng HTTP, database, mô hình tính toán hoặc adapter. Hàm quote() phải có hợp đồng rõ cho lỗi:

- Không có giá: trả SupplierOutcome UNAVAILABLE theo điều kiện nghiệp vụ.
- Dữ liệu request sai: báo lỗi ở ingress trước khi scatter hoặc dùng lỗi domain đã phân loại.
- Timeout/hạ tầng: quyết định retry riêng supplier hoặc trả failure outcome sau khi đã kết luận terminal.
- Không được tự trả null vì Gather cần một reply của nhánh.

## 7. Gather: chọn báo giá thấp nhất nhưng giữ tất cả outcomes

Một Gather không nên chỉ lấy message đến đầu tiên hoặc chỉ giữ giá thấp nhất rồi quên các supplier khác. Để kiểm toán và giải thích được quyết định, trả **QuoteReport** gồm danh sách outcomes được sắp xếp ổn định.

~~~java
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.springframework.integration.store.MessageGroup;

final class QuoteReportFactory {
    private static final int EXPECTED_SUPPLIERS = 3;

    private QuoteReportFactory() {}

    static QuoteReport fromGroup(MessageGroup group) {
        List<SupplierOutcome> outcomes = group.getMessages().stream()
                .map(message -> (SupplierOutcome) message.getPayload())
                .sorted(Comparator.comparing(
                        SupplierOutcome::supplierId))
                .toList();

        if (outcomes.size() != EXPECTED_SUPPLIERS) {
            throw new IllegalStateException("INCOMPLETE_SUPPLIER_GROUP");
        }

        String requestId = outcomes.get(0).requestId();
        Set<String> identities = new HashSet<>();
        for (SupplierOutcome outcome : outcomes) {
            if (!requestId.equals(outcome.requestId())) {
                throw new IllegalStateException("MIXED_REQUEST_IDS");
            }
            if (!identities.add(outcome.supplierId())) {
                throw new IllegalStateException("DUPLICATE_SUPPLIER_REPLY");
            }
        }

        SupplierOutcome best = outcomes.stream()
                .filter(outcome -> "SUCCESS".equals(outcome.status()))
                .min(Comparator
                        .comparing(SupplierOutcome::totalPriceVnd)
                        .thenComparing(SupplierOutcome::supplierId))
                .orElse(null);

        long successCount = outcomes.stream()
                .filter(outcome -> "SUCCESS".equals(outcome.status()))
                .count();
        String reportStatus = successCount == EXPECTED_SUPPLIERS
                ? "COMPLETE"
                : best == null ? "NO_OFFER" : "PARTIAL_SUPPLIER_FAILURE";

        return new QuoteReport(
                requestId,
                EXPECTED_SUPPLIERS,
                outcomes.size(),
                reportStatus,
                best,
                List.copyOf(outcomes));
    }
}
~~~

**Điểm thiết kế của ví dụ:**

1. Cần **đúng ba terminal outcomes**, một từ mỗi supplier.
2. Hai message cùng supplierId gây lỗi duplicate thay vì lặng lẽ được xem là hai nguồn báo giá.
3. Khi đủ 3 outcomes nhưng một supplier UNAVAILABLE, reportStatus là PARTIAL_SUPPLIER_FAILURE; vẫn chọn giá thấp nhất **trong những offer hợp lệ**.
4. Khi cả ba UNAVAILABLE, reportStatus là NO_OFFER, không có bestOffer.
5. Thứ tự arrivals không tác động kết quả vì outcomes được sort theo supplierId.

Đây là **processor của nhóm đầy đủ**. Nếu muốn phát report khi chỉ có 2/3 replies vì timeout, phải thiết kế **processor riêng cho partial group** dựa trên manifest supplier kỳ vọng và trả trạng thái INCOMPLETE; không dùng đoạn code trên rồi tự thay EXPECTED_SUPPLIERS bằng số message đã đến.

### 7.1. Default release strategy không kiểm tra mọi invariant

ReleaseStrategy của Aggregator quyết định khi nào nhóm đủ điều kiện release, không thay thế toàn bộ validation của QuoteReportFactory. Với phiên bản Spring Integration 5.0+, mặc định dùng **SimpleSequenceSizeReleaseStrategy** khi không cấu hình partial release; nó tối ưu hiệu năng nhưng không phải một hệ thống dedup reply bền.

Nếu một supplier trả message trùng còn supplier khác chưa phản hồi, chính sách phát hiện duplicate phải được kiểm thử. Không suy ra rằng số message bằng sequenceSize đồng nghĩa đã nhận đúng mỗi supplier một kết quả.

## 8. Tạo ba supplier giả lập để học cơ chế Gather

Để minh họa đường xử lý, ba supplier được triển khai bằng phép tính thuần. Giá ở đây chỉ là **dữ liệu mô phỏng**, không phản ánh giá vận chuyển thực.

~~~java
import java.math.BigDecimal;

final class WarehouseSupplier implements SupplierQuotePort {
    @Override
    public SupplierOutcome quote(QuoteRequest request) {
        return SupplierOutcome.success(
                request,
                "WAREHOUSE",
                BigDecimal.valueOf(85_000L)
                        .multiply(BigDecimal.valueOf(request.quantity())));
    }
}

final class PartnerSupplier implements SupplierQuotePort {
    @Override
    public SupplierOutcome quote(QuoteRequest request) {
        return SupplierOutcome.success(
                request,
                "PARTNER",
                BigDecimal.valueOf(80_000L)
                        .multiply(BigDecimal.valueOf(request.quantity())));
    }
}

final class BackupSupplier implements SupplierQuotePort {
    @Override
    public SupplierOutcome quote(QuoteRequest request) {
        return SupplierOutcome.success(
                request,
                "BACKUP",
                BigDecimal.valueOf(95_000L)
                        .multiply(BigDecimal.valueOf(request.quantity())));
    }
}
~~~

Nếu request có **quantity=2**, giá lần lượt là 170.000 VND, 160.000 VND và 190.000 VND. Gather sẽ chọn **PARTNER** làm bestOffer mà vẫn giữ đủ ba offers để đối chiếu.

## 9. Java DSL: Scatter-Gather với các nhánh chạy song song

Spring Integration Java DSL có phương thức **scatterGather(scatterer, gatherer, options)**. Ở ví dụ này:

- **scatterer** khai báo ba recipient sub-flows.
- Mỗi sub-flow có một **ExecutorChannel** để việc xử lý diễn ra trên thread pool.
- Endpoint cuối trong mỗi sub-flow trả **SupplierOutcome**.
- **gatherer** sử dụng QuoteReportFactory làm MessageGroupProcessor.
- **options** giới hạn thời gian ScatterGatherHandler đợi kết quả.
- Report được gửi tới một QueueChannel dùng cho ví dụ/kiểm thử.

### 9.1. Cấu hình flow

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableIntegration
class QuoteScatterGatherConfig {

    @Bean
    SupplierQuotePort warehouseSupplier() {
        return new WarehouseSupplier();
    }

    @Bean
    SupplierQuotePort partnerSupplier() {
        return new PartnerSupplier();
    }

    @Bean
    SupplierQuotePort backupSupplier() {
        return new BackupSupplier();
    }

    @Bean
    MessageChannel quoteRequestsChannel() {
        return new DirectChannel();
    }

    @Bean
    QueueChannel quoteReportsChannel() {
        return new QueueChannel();
    }

    @Bean
    ThreadPoolTaskExecutor quoteWorkers() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(3);
        executor.setMaxPoolSize(6);
        executor.setQueueCapacity(30);
        executor.setThreadNamePrefix("quote-worker-");
        return executor;
    }

    @Bean
    IntegrationFlow quoteComparisonFlow(
            @Qualifier("warehouseSupplier")
            SupplierQuotePort warehouse,
            @Qualifier("partnerSupplier")
            SupplierQuotePort partner,
            @Qualifier("backupSupplier")
            SupplierQuotePort backup,
            @Qualifier("quoteWorkers")
            ThreadPoolTaskExecutor executor) {

        return IntegrationFlow.from("quoteRequestsChannel")
                .scatterGather(
                        scatter -> scatter
                                .recipientFlow(flow -> flow
                                        .channel(c -> c.executor(executor))
                                        .handle(QuoteRequest.class,
                                                (request, headers) ->
                                                        warehouse.quote(request)))
                                .recipientFlow(flow -> flow
                                        .channel(c -> c.executor(executor))
                                        .handle(QuoteRequest.class,
                                                (request, headers) ->
                                                        partner.quote(request)))
                                .recipientFlow(flow -> flow
                                        .channel(c -> c.executor(executor))
                                        .handle(QuoteRequest.class,
                                                (request, headers) ->
                                                        backup.quote(request))),
                        gather -> gather
                                .outputProcessor(
                                        QuoteReportFactory::fromGroup),
                        options -> options
                                .gatherTimeout(5_000))
                .channel("quoteReportsChannel")
                .get();
    }
}
~~~

**Lưu ý phiên bản:** ví dụ hướng tới Spring Integration Java DSL **6.x trở lên**, nơi DSL Scatter-Gather tiện lợi cấu hình applySequence cho scatterer do nó tạo. Nếu dự án dùng phiên bản khác, đối chiếu API tương ứng và kiểm thử các sequence headers thực nhận; không sao chép cấu hình rồi suy luận một cách máy móc.

### 9.2. Vì sao đây là xử lý song song?

Không có ExecutorChannel, mỗi recipient có thể được dispatch theo thứ tự trên thread gọi ScatterGatherHandler; tổng thời gian có thể gần bằng tổng thời gian ba supplier.

Với ExecutorChannel và pool đủ capacity, ba thao tác supplier được **submit** để chạy độc lập. Khi các tác vụ thực sự có thể chạy đồng thời:

~~~text
Tổng thời gian xử lý gần
  max(latency warehouse, latency partner, latency backup)
  + overhead scatter/gather
~~~

Điều này là **ước lượng khi đủ tài nguyên và không có bottleneck chung**, không phải bảo đảm của framework. Thread pool bị quá tải, connection pool nhỏ, rate limit ở supplier, lock chung hoặc network chậm có thể làm latency lớn hơn đáng kể.

### 9.3. Vì sao handler cuối phải trả reply?

Trong từng nhánh, đoạn:

~~~java
.handle(QuoteRequest.class,
        (request, headers) -> warehouse.quote(request))
~~~

trả một **SupplierOutcome không null**, giúp Spring Integration tạo reply để Gather nhận. Nếu thay bằng:

~~~java
// Phản ví dụ cho Scatter-Gather cần đủ 3 replies:
.handle(QuoteRequest.class, (request, headers) -> {
    warehouse.quote(request);
    return null;
})
~~~

nhánh Warehouse không tạo reply. Gather không tự coi thao tác đã gọi quote là một outcome; group có thể chỉ có hai message và đợi tới timeout. Endpoint one-way có thể hợp lệ ở flow khác, nhưng không đáp ứng **hợp đồng request/reply** của ví dụ.

### 9.4. Không đặt outputChannel khác ở cuối nhánh

Nếu nhánh Warehouse trả outcome nhưng định tuyến output sang một channel khác không dẫn về Gather, ScatterGatherHandler vẫn có thể thiếu reply. Ví dụ cần dùng cơ chế **replyChannel** mà ScatterGatherHandler đã gắn; nếu hệ thống có gatherChannel riêng, mọi nhánh phải được cấu hình gửi về đúng gatherChannel đó.

**Đừng tự gắn replyChannel từ dữ liệu client chưa tin cậy**. Các channel điều khiển và metadata correlation phải do thành phần nội bộ tạo hoặc xác minh.

### 9.5. Gửi request thử nghiệm

~~~java
import org.springframework.messaging.support.MessageBuilder;

QuoteRequest request = new QuoteRequest(
        "req-701", "SKU-99", 2);

// Bean quoteRequestsChannel được inject từ Spring.
quoteRequestsChannel.send(
        MessageBuilder.withPayload(request).build());

// Bean quoteReportsChannel là QueueChannel trong ví dụ.
var response = quoteReportsChannel.receive(5_000);
if (response == null) {
    throw new IllegalStateException("QUOTE_REPORT_TIMEOUT");
}
QuoteReport report = (QuoteReport) response.getPayload();
~~~

Với ba supplier giả lập và không có lỗi, report gồm ba outcomes, reportStatus COMPLETE và bestOffer.supplierId bằng PARTNER.

**Phân biệt hai thời gian chờ:** gatherTimeout(5_000) là thời gian **ScatterGatherHandler chờ aggregator reply**; receive(5_000) ở producer là thời gian **test/client chờ đọc output QueueChannel**. Hai thời gian này không thay thế nhau. Trong mô hình DirectChannel ở ingress, lời gọi send() có thể đã chờ Scatter-Gather xong trước khi tới câu lệnh receive().

## 10. Gather theo thứ tự hoàn thành, không theo thứ tự khai báo

Khi ba nhà cung cấp được xử lý trên ExecutorChannel, reply của chúng có thể đến theo bất kỳ thứ tự nào:

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant SG as ScatterGatherHandler
    participant W as Warehouse
    participant P as Partner
    participant B as Backup
    participant G as Aggregator
    C->>SG: req-701
    par Ba yêu cầu đồng thời
        SG->>W: req-701
        SG->>P: req-701
        SG->>B: req-701
    end
    P-->>G: PARTNER, 160000, sequence=2
    B-->>G: BACKUP, 190000, sequence=3
    Note over G: 2/3 replies, tiếp tục đợi
    W-->>G: WAREHOUSE, 170000, sequence=1
    G-->>SG: QuoteReport, 3/3 replies
    SG-->>C: Report
~~~

**Không giả định:** phần tử đầu tiên trong MessageGroup là supplier đầu tiên được khai báo, và phần tử cuối là supplier chậm nhất trong mọi lần chạy. Thứ tự arrival là thuộc tính vận hành thay đổi theo thread scheduling, network và tải.

### 10.1. Hai kiểu sắp xếp khác nhau

- **Sắp kết quả trong báo cáo** theo supplierId, thời gian hoặc mức giá giúp output dễ đọc. Điều này không thay đổi cách các nhánh thực thi.
- **Giữ thứ tự thực thi nghiệp vụ** đòi hỏi một chiến lược riêng, thường làm mất tính song song. Không thể vừa bảo đảm mọi side effect được commit theo thứ tự cố định vừa tự do thực thi song song mà không thêm coordination.

Trong ví dụ báo giá, thứ tự thực thi không quan trọng; mọi supplier độc lập. Chỉ **quy tắc chọn bestOffer** và thứ tự hiển thị report cần deterministic.

### 10.2. Một request đã vào hai group khác nhau là lỗi

Nếu branch tự tạo correlationId thay vì giữ correlation do Scatter-Gather cung cấp, reply có thể bị tách thành nhiều nhóm:

~~~text
req-701:
    warehouse -> correlation=G-701-A
    partner   -> correlation=G-701-B
    backup    -> correlation=G-701-C
~~~

Mỗi nhóm chỉ nhận 1/3 reply và không release theo default. Khi cần biến đổi payload, dùng Transformer/Handler sao cho **reply metadata được giữ đúng**; không tự gắn một correlationId mới cho mỗi supplier nếu mục đích là cùng một Gather.

## 11. Một nhánh không phản hồi: timeout khác lỗi nghiệp vụ

Với ba supplier, một nhánh có thể:

- Trả kết quả hợp lệ nhưng chậm.
- Trả UNAVAILABLE có chủ đích.
- Bị timeout HTTP và chưa biết request đã được xử lý hay chưa.
- Ném exception trước khi tạo reply.
- Đã tạo reply nhưng gửi nhầm outputChannel.
- Reply sau khi Gather đã kết thúc.

Không gộp mọi trường hợp vào một nhãn FAILED chung. Phải phân biệt **terminal response**, **missing reply**, **unknown state** và **late arrival**.

### 11.1. Gather timeout: thời gian đợi một kết quả đã aggregate

Trong ScatterGatherHandler, **gatherTimeout** là giới hạn chờ kết quả của aggregator. Với cấu hình đồng bộ, thread thực hiện Scatter-Gather có thể bị giữ khi chờ. Nếu không có kết quả trước hạn, handler có thể trả null; khi **requiresReply=true** (mặc định), nó báo lỗi kiểu ReplyRequiredException.

Vì vậy gatherTimeout không có nghĩa “đủ 2/3 replies thì tự tổng hợp 2”. Nó chỉ giới hạn **thời gian chờ phía request/reply**.

Ví dụ:

~~~text
Expected suppliers: 3
Arrived in 5 seconds: WAREHOUSE, PARTNER
Missing: BACKUP

Aggregator vẫn chờ 3/3
ScatterGatherHandler gatherTimeout=5000ms
=> Caller không nhận được QuoteReport đầy đủ
~~~

Đây là kết quả đúng nếu hợp đồng **bắt buộc đủ ba nguồn**, nhưng ứng dụng phải có lỗi và trạng thái phục hồi dễ hiểu thay vì để caller treo không giới hạn.

### 11.2. Group timeout: quyết định làm gì với MessageGroup chưa đủ

Aggregator có cơ chế **groupTimeout** hoặc **groupTimeoutExpression** để kích hoạt xử lý nhóm chưa đủ khi hết hạn. Nếu bật **sendPartialResultOnExpiry**, nó có thể tạo result từ group đã có và phát ra một partial result, tùy cấu hình release/expiry.

~~~mermaid
flowchart TD
    A["Aggregator nhận 2/3 outcomes"] --> B{"Đủ nhóm?"}
    B -->|"Có"| C["Report COMPLETE / PARTIAL_SUPPLIER_FAILURE"]
    B -->|"Không"| D["Đợi đến groupTimeout"]
    D --> E{"Cho partial release?"}
    E -->|"Có"| F["Report INCOMPLETE, missing supplier"]
    E -->|"Không"| X["Expire/discard theo policy"]
~~~

Nếu muốn caller thực sự nhận partial result, **gatherTimeout phải tương thích với groupTimeout và độ trễ scheduler**. Ví dụ groupTimeout=2 giây, gatherTimeout=10 giây có cơ hội cho aggregator phát partial trước khi ScatterGatherHandler hết hạn. Dùng cùng một mức timeout sát nhau sẽ dễ tạo race condition.

**Quan trọng:** groupTimeout mặc định thường tính từ lần message gần nhất của group; nếu muốn hạn cuối cố định từ khi request bắt đầu, dùng deadline nghiệp vụ hoặc groupTimeoutExpression dựa trên timestamp của group theo khả năng phiên bản đang dùng. Không mặc định mọi timeout đều đo từ thời điểm request tới.

### 11.3. Partial report cần contract riêng

QuoteReportFactory.fromGroup() ở phần trước cố ý yêu cầu **đủ ba terminal outcomes**. Nếu bật partial release mà vẫn dùng factory ấy, nó sẽ ném INCOMPLETE_SUPPLIER_GROUP. Để hỗ trợ partial, cần một processor khác.

Ví dụ domain dành cho incomplete:

~~~java
import java.util.List;

record PartialQuoteReport(
        String requestId,
        String reportStatus,
        List<String> missingSuppliers,
        List<SupplierOutcome> arrivedOutcomes,
        SupplierOutcome bestSoFar) {}
~~~

Quy tắc:

1. Đọc tập supplier được **mời tham gia** từ manifest đáng tin (trong ví dụ cố định là WAREHOUSE, PARTNER, BACKUP).
2. Đối chiếu danh tính từng outcome.
3. Tính missingSuppliers bằng tập dự kiến trừ tập đã nhận.
4. Đặt reportStatus=INCOMPLETE nếu thiếu bất kỳ reply nào.
5. Nếu cần chọn bestSoFar, ghi rõ đó là **giá tốt nhất tạm thời**, không đồng nghĩa giá tốt nhất khi mọi nhà cung cấp tham gia.

Đừng chỉ dùng outcomes.size() để suy ra expectedSuppliers, vì chính trường hợp thiếu reply là khi size hiện tại **nhỏ hơn** số nguồn được mời.

### 11.4. Một handler trả null có ý nghĩa gì?

Nếu nhà cung cấp không có báo giá, cách đúng với hợp đồng **một reply mỗi supplier** là:

~~~java
return SupplierOutcome.unavailable(
        request,
        "BACKUP",
        "NO_QUOTE_FOR_SKU");
~~~

Không nên:

~~~java
// Sai trong flow cần đủ phản hồi:
if (notAvailable) {
    return null;
}
~~~

Trong Service Activator one-way, return null có thể là một kết thúc bình thường của nhánh, nhưng đối với Gather đang kỳ vọng 3/3 reply thì nhánh đó sẽ thiếu một outcome. Muốn dùng chiến lược **K-of-N** không chờ nhánh thiếu, cần xác định release policy khác và trạng thái incomplete rõ ràng.

## 12. Khi một nhánh lỗi, đừng vô tình hủy giá trị của hai nhánh khác

Spring Integration lưu ý **Scatter-Gather có đặc thù lỗi multi-request-reply**. Nếu một sub-flow đồng bộ ném exception lên ScatterGatherHandler, exception có thể truyền về upstream và kết quả của các nhánh khác không còn được dùng để tạo report.

Với nhánh chạy bất đồng bộ, exception thường được chuyển thành ErrorMessage thông qua MessagePublishingErrorHandler khi executor/adapter hỗ trợ. Nhưng **ErrorMessage gửi tới errorChannel không tự trở thành reply của Gather**.

~~~mermaid
flowchart LR
    R["Scatter req-701"] --> W["Warehouse: SUCCESS"]
    R --> P["Partner: timeout"]
    R --> B["Backup: SUCCESS"]
    W --> G["Gather có 2/3"]
    B --> G
    P -.-> E["ErrorMessage / errorChannel"]
    E -.-> X["Chưa phải SupplierOutcome"]
~~~

Nếu muốn nhận ba kết quả terminal, lỗi được dự đoán phải được biến thành **một failure outcome rõ ràng** cho đúng supplier.

### 12.1. Phân loại lỗi theo từng supplier

| Lỗi | Có thể trả terminal outcome ngay? | Cách xử lý phù hợp |
| --- | --- | --- |
| Supplier chủ động từ chối SKU | Có | UNAVAILABLE / NO_QUOTE |
| Supplier trả dữ liệu sai hợp đồng | Có thể | INVALID_SUPPLIER_RESPONSE; đồng thời alert |
| HTTP 429 | Không phải lúc nào | Retry giới hạn, rate limit; sau đó timeout/terminal |
| HTTP timeout | Chưa chắc | Retry idempotent nếu phù hợp, hoặc UNKNOWN |
| Không resolve được channel | Không | Lỗi topology, cần sửa cấu hình |
| Thread pool từ chối task | Không | Backpressure và lỗi admission |
| NullPointerException do bug | Không nên âm thầm | Alert, quarantine/retry sau sửa code |
| Reply đến muộn sau deadline | Không còn đóng góp vào report đã phát | Late-arrival policy, không sửa report âm thầm |

Không dùng catch(Exception) để chuyển mọi lỗi hệ thống thành báo giá không khả dụng. Điều đó che lỗi deploy, schema hoặc circuit breaker và khiến báo cáo có vẻ hợp lệ dù framework đã lỗi.

### 12.2. Xử lý lỗi dự đoán ngay trong nhánh

Ví dụ một adapter supplier có một exception domain đã phân loại:

~~~java
final class SupplierUnavailableException
        extends RuntimeException {
    SupplierUnavailableException(String message) {
        super(message);
    }
}

final class SafePartnerQuoteAdapter implements SupplierQuotePort {
    private final SupplierQuotePort remote;

    SafePartnerQuoteAdapter(SupplierQuotePort remote) {
        this.remote = remote;
    }

    @Override
    public SupplierOutcome quote(QuoteRequest request) {
        try {
            return remote.quote(request);
        } catch (SupplierUnavailableException expected) {
            return SupplierOutcome.unavailable(
                    request,
                    "PARTNER",
                    "PARTNER_TEMPORARILY_UNAVAILABLE");
        }
    }
}
~~~

Adapter này bắt đúng loại lỗi domain đã được xem là terminal sau chính sách retry (nếu có). Nó **không** nuốt NullPointerException hoặc lỗi runtime bất ngờ. Nếu một timeout chưa xác định kết quả khiến yêu cầu nghiệp vụ không thể kết luận terminal, cần lưu trạng thái UNKNOWN hoặc xử lý bằng đường timeout/recovery phù hợp, chứ không nhất thiết trả UNAVAILABLE ngay.

### 12.3. ErrorMessage compensation cho nhánh bất đồng bộ

Spring Integration có thể cấu hình **errorChannel** của ScatterGatherHandler để khi một sub-flow async lỗi, một error flow tạo **compensation reply** cho Gather. Với Java DSL:

~~~java
// Mảnh DSL minh họa options của Scatter-Gather:
.scatterGather(
        scatterer -> scatterer
                .recipientFlow(/* supplier A flow */)
                .recipientFlow(/* supplier B flow */),
        gatherer -> gatherer
                .outputProcessor(QuoteReportFactory::fromGroup),
        options -> options
                .gatherTimeout(10_000)
                .errorChannel("quoteScatterErrors"))
~~~

Để compensation thực sự tới Gather, response từ error handler cần giữ **replyChannel, correlationId, sequenceNumber, sequenceSize** và những metadata Scatter-Gather dùng để quản lý gatherResultChannel/reply gốc.

Theo tài liệu, khi error handler lấy **failedMessage** từ MessagingException rồi tạo Message bù:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.MessageBuilder;

// Mảnh phương thức gọi từ error flow, không phải main()
Message<SupplierOutcome> makeCompensation(
        MessagingException failure) {

    Message<?> failedMessage = failure.getFailedMessage();
    if (failedMessage == null
            || !(failedMessage.getPayload() instanceof QuoteRequest request)) {
        throw new IllegalStateException(
                "Không đủ metadata để phục hồi Gather", failure);
    }

    Object source = failedMessage.getHeaders().get("supplierId");
    if (!(source instanceof String supplierId)
            || !java.util.Set.of(
                    "WAREHOUSE", "PARTNER", "BACKUP")
                    .contains(supplierId)) {
        throw new IllegalStateException(
                "Không rõ supplier lỗi", failure);
    }

    // Chỉ sử dụng đường này khi lỗi đã được phân loại
    // và nghiệp vụ cho phép một terminal failure outcome.
    return MessageBuilder
            .withPayload(SupplierOutcome.unavailable(
                    request, supplierId, "SUPPLIER_FAILED"))
            .copyHeaders(failedMessage.getHeaders())
            .build();
}
~~~

Trong flow thật, phải gắn **supplierId** vào header **bằng code nội bộ của từng nhánh**, không từ input không tin cậy; ví dụ một Header Enricher trước bước I/O. Đồng thời error handler cần kiểm tra nguyên nhân lỗi và chính sách retry trước khi gọi makeCompensation(). Đây là **mảnh minh họa**, chưa phải một error flow hoàn chỉnh.

**Không copy toàn bộ raw headers từ nguồn bên ngoài vào output công khai.** Việc copy metadata ở trên nhằm giữ các routing headers nội bộ của failedMessage để compensation về Gather; phải có ranh giới tin cậy tại ingress và chính sách dữ liệu phù hợp.

### 12.4. Không tạo hai replies cho cùng supplier

Một timeout có thể khiến:

1. Supplier thực sự đã tạo reply, nhưng response network bị mất.
2. Error handler tạo một compensation UNAVAILABLE.
3. Một reply thật đến muộn với cùng supplierId.

Gather và kho trạng thái phải có chính sách **một terminal outcome cho một supplier trong một request**. Nếu hai results cùng xuất hiện:

- Không tính là hai nhà cung cấp.
- Không tự overwrite báo cáo terminal đã công bố.
- Ghi nhận duplicate/late reply và đối soát nếu cần.

Một khóa có thể là **requestId + supplierId** (và tenantId đáng tin nếu cần). Việc xử lý duplicate ở Aggregator/MessageStore phải được kiểm thử; không cho rằng default release strategy đã tự tạo đúng semantics.

## 13. MessageGroupStore, late reply và vòng đời của một group

Aggregator dùng **MessageGroupStore** để tích lũy reply. Với ví dụ local và ngắn, một in-memory store đủ minh họa. Với workload cần khôi phục qua restart, phải chọn persistent store, transaction, locking và chính sách cleanup tương ứng.

### 13.1. Group được tạo, release và expire như thế nào?

~~~text
Group mới
   -> nhận reply #1
   -> nhận reply #2
   -> nhận reply #3
   -> ReleaseStrategy cho phép release
   -> MessageGroupProcessor tạo QuoteReport
   -> Group được marked complete hoặc expired
~~~

Theo tài liệu Aggregator, khi group đã hoàn tất:

- Nếu **expireGroupsUponCompletion=false** (mặc định), framework có thể giữ metadata của group đã hoàn tất để phát hiện và discard reply đến muộn.
- Nếu **expireGroupsUponCompletion=true**, group bị xóa; một reply đến sau với cùng correlation ID có thể **tạo group mới**, gây tập hợp sai hoặc báo cáo trùng.
- Với group bị timeout, **expireGroupsUponTimeout** có semantics riêng, khác với complete bình thường.

Điều này dẫn đến một trade-off: giữ metadata quá lâu chiếm MessageStore; xóa quá sớm có thể cho phép late message tái lập group. Phải chọn **retention phù hợp với thời gian redelivery tối đa**, thay vì giữ vĩnh viễn hoặc xóa ngay theo thói quen.

### 13.2. Correlation group và report nghiệp vụ có vòng đời khác nhau

Một Scatter-Gather local có thể hoàn tất trong vài trăm mili giây, nhưng requestId của báo giá vẫn được lưu nhiều giờ để tra cứu. Bởi vậy:

- **MessageGroup** là trạng thái kỹ thuật để assemble reply trong một attempt.
- **QuoteReport** là kết quả nghiệp vụ, có thể cần được lưu cùng requestId.
- **Processing ledger** ghi trạng thái từng supplier để phục hồi khi một attempt lỗi.
- **Outbox** dùng khi cần phát kết quả hoặc nhiệm vụ tiếp theo bền.

Đừng dùng một MessageGroup in-memory làm **nguồn sự thật duy nhất** cho một nghiệp vụ cần sống qua restart hoặc nhiều instance.

### 13.3. Group store trong môi trường nhiều instance

Khi reply có thể đến các instance khác nhau, cần một cơ chế correlation có thể chia sẻ giữa các process, hoặc đảm bảo mọi reply của một request về cùng một instance:

- Dùng shared persistent MessageGroupStore với lock/transaction phù hợp.
- Hoặc dùng broker routing theo correlation key để đưa replies về cùng một worker.
- Hoặc chuyển Gather sang một service sở hữu persistent state theo requestId.

Chỉ thay SimpleMessageStore bằng database chưa đủ nếu các consumer có race condition hoặc không cùng hợp đồng correlation. Phải kiểm thử concurrent arrivals, duplicate, database failover và group cleanup.

### 13.4. Reply quá hạn không được đổi kết quả âm thầm

Giả sử QuoteReport INCOMPLETE được phát sau 3 giây, rồi supplier BACKUP gửi offer rẻ hơn vào giây thứ 8. Có thể chọn một trong hai chính sách:

1. **Freeze result:** báo cáo đã công bố là kết quả cuối theo deadline; late reply được lưu/audit nhưng không ảnh hưởng lựa chọn.
2. **Revisioned result:** phát báo cáo version 2, đánh dấu version 1 đã được cập nhật; downstream phải hiểu update và có idempotency.

Không tự thay đổi một báo cáo đã dùng để đặt hàng hoặc thanh toán mà không có hợp đồng version/compensation. Late reply không chỉ là sự kiện kỹ thuật; nó có thể ảnh hưởng quyết định nghiệp vụ đã thực thi.

## 14. Thiết kế thời gian chờ theo deadline chung

Một flow Gather với nhiều supplier có ba loại timeout dễ nhầm:

| Loại | Đặt ở đâu | Ý nghĩa |
| --- | --- | --- |
| **Supplier HTTP timeout** | Mỗi supplier adapter | Bao lâu chờ một nhà cung cấp |
| **Aggregator groupTimeout** | MessageGroup / Aggregator | Khi nào xử lý group chưa đủ reply |
| **ScatterGatherHandler gatherTimeout** | Endpoint request/reply | Bao lâu caller đợi kết quả đã aggregate |
| **Gateway timeout** | Gateway bên ngoài | Bao lâu client của flow đợi reply |
| **Queue sendTimeout** | Kênh gửi có capacity | Bao lâu đợi để gửi được message vào channel |

Những timeout này **không đồng nghĩa**, cũng không nên đặt ngẫu nhiên bằng nhau.

### 14.1. Ví dụ ngân sách 8 giây

Giả sử SLA trả báo giá là **8 giây**:

~~~text
Client deadline                      8.0 s
  scatter overhead                   0.1 s
  supplier timeout                   4.0 s
  error/recovery + aggregation        1.0 s
  gather/client margin                2.9 s
~~~

Đây là một phân bổ minh họa. Nếu mỗi supplier có ba retry nối tiếp 4 giây, tổng thời gian sẽ vượt SLA mặc dù scatter chạy song song. Do đó retry count và backoff phải nằm trong **deadline tổng**, không chỉ cấu hình từng endpoint độc lập.

### 14.2. Nhánh chậm nhất chi phối latency của chính sách all-of-N

Nếu ba supplier hoàn tất trong 300 ms, 800 ms và 2.200 ms, Gather đợi cả ba sẽ không thể trả kết quả đầy đủ trước khoảng 2.200 ms (cộng overhead), dù hai reply đầu tới rất sớm.

Nếu SLA không chấp nhận chờ supplier thứ ba, có thể dùng partial release hoặc **K-of-N**, nhưng phải công bố **không phải mọi supplier đều được tham khảo**. Không tuyên bố “giá rẻ nhất thị trường” khi chỉ nhận được một phần offer.

### 14.3. Không để group tồn tại vĩnh viễn

Một group chờ thiếu reply không chỉ giữ một object; với tải lớn, hàng trăm nghìn group có thể tích tụ trong MessageGroupStore.

Các biện pháp:

- Bounded queue và bounded executor.
- Group timeout/expiry hoặc persistent progress state.
- Monitoring số nhóm đang chờ và tuổi nhóm.
- Dead-letter/recovery đối với supplier lỗi liên tục.
- Giới hạn tối đa số reply trong một group.
- Lọc duplicate reply và input không rõ danh tính.

Nếu cần chờ hàng giờ/ngày, nên cân nhắc **workflow bền với state machine** hơn là giữ request/reply caller block trong ScatterGatherHandler.

## 15. Song song không có nghĩa không tốn tài nguyên

Một chương trình dùng ExecutorChannel cho ba nhánh thường có hai dạng tải:

1. **Số request Scatter-Gather đồng thời**: bao nhiêu request đang chờ đủ replies?
2. **Số supplier tasks đồng thời**: mỗi request có thể tạo tới ba tasks.

Nếu có 200 request đồng thời và mỗi request gửi 3 tasks, có thể tạo **600 supplier invocations** gần nhau. Chỉ tăng thread pool để giảm timeout có thể làm quá tải database, HTTP connection pool hoặc rate limit của supplier.

### 15.1. Bounded TaskExecutor

Trong ví dụ trước, ThreadPoolTaskExecutor có:

~~~text
corePoolSize = 3
maxPoolSize  = 6
queueCapacity = 30
~~~

Đó là một **cấu hình demo**, không phải khuyến nghị production cho mọi tải. Khi queue đã đầy, executor có thể từ chối task; cần chính sách backpressure, admission, retry và báo lỗi cụ thể. Đừng coi task bị từ chối là một supplier đã trả UNAVAILABLE nếu request chưa từng được dispatch.

### 15.2. I/O blocking và giới hạn kết nối

Nếu quote supplier dùng HTTP blocking, worker thread bị giữ trong lúc chờ. Một pool nhỏ có thể bảo vệ tài nguyên nhưng tăng latency; pool quá lớn có thể khiến hệ thống bị quá tải ngoài khả năng xử lý.

Nên đo và giới hạn:

- Concurrent connections theo supplier.
- Timeout kết nối và đọc response.
- Số attempts và backoff.
- Circuit breaker khi supplier gặp sự cố.
- Rate limit và bulkhead theo supplier, không để một nhà cung cấp lỗi chiếm toàn bộ pool.
- Số request Scatter-Gather đồng thời đang chờ.

### 15.3. Không phải mọi Publisher đều chạy đồng thời

PublishSubscribeChannel mặc định dispatch đồng bộ. RecipientListRouter cũng không tự tạo các thread độc lập cho từng recipient. Chỉ khi có executor/channel/adapter async phù hợp, các nhánh mới có khả năng được xử lý song song thực sự.

Một sơ đồ có ba mũi tên **không phải** bằng chứng đã có parallelism. Test thực tế cần xác minh overlap hoặc thông lượng dưới tải, không dựa vào tên Scatter-Gather.

## 16. Replay và idempotency của mỗi supplier

Gather một kết quả từ ba supplier không đảm bảo request chỉ được gửi một lần. Nếu một message bị broker redeliver, Gateway retry hoặc operator phát lại request, toàn bộ thao tác scatter có thể được thực hiện thêm lần nữa.

### 16.1. Phân biệt ba loại khóa

| Định danh | Phạm vi | Mục đích |
| --- | --- | --- |
| **requestId** | Một yêu cầu báo giá logic | Tracking/replay qua các attempts |
| **correlationId** | Một nhóm scatter/gather | Ghép replies trong một attempt |
| **supplierId** | Một nhánh logical | Biết nguồn outcome và chống đếm trùng |
| **attemptId** | Một lần thử kỹ thuật | Metrics/tracing, không thay idempotency key |

Với nghiệp vụ cần chống side effect:

~~~text
businessOperationKey = tenantId + ":" + requestId + ":" + supplierId
~~~

Nếu đang chỉ **đọc báo giá** qua API read-only, retry thường ít rủi ro side effect hơn. Nhưng nếu supplier ghi một reservation, tạo đơn hàng hoặc khóa giá, idempotency key phải được provider chấp nhận/ghi nhận đúng hợp đồng.

### 16.2. Retry tất cả nhánh sau partial success

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant S as Scatter
    participant A as Supplier A
    participant B as Supplier B
    participant D as Supplier C
    C->>S: Request req-701, attempt 1
    S->>A: Request
    S->>B: Request
    S->>D: Request
    A-->>S: Success
    B-->>S: Success
    D--xS: Timeout
    C->>S: Retry request req-701
    S->>A: Request lần nữa
    S->>B: Request lần nữa
    S->>D: Request lần nữa
    Note over A,B: Idempotency nếu có side effect
~~~

Nếu chỉ có supplier C lỗi, một hệ thống có persistent progress có thể retry **riêng C** thay vì lại gọi A và B. Cách tối ưu này đòi hỏi lưu trạng thái từng supplier và tập replies đã nhận; ScatterGatherHandler local **không tự tạo một workflow inbox/outbox bền**.

### 16.3. Không dùng MessageHeaders.ID làm khóa nghiệp vụ

Một Message có thể được tạo lại khi đi qua Transformer/adapter hoặc sau restart; MessageHeaders.ID là metadata kỹ thuật, không đại diện cho một yêu cầu báo giá logical. Dùng requestId ổn định theo hợp đồng.

### 16.4. Không đánh dấu thành công quá sớm

Một supplier trả HTTP 202 Accepted có thể chỉ xác nhận yêu cầu đã vào queue, chưa có báo giá. Nếu Gather đang yêu cầu **giá cuối cùng**, không coi ACCEPTED là SUCCESS có totalPriceVnd.

Cần contract rõ cho trạng thái PENDING và deadline; nếu quyết định chờ kết quả async dài hạn, một workflow bền với event kết quả sau có thể phù hợp hơn request/reply ngay lập tức.

## 17. Unit test cho báo cáo và kết quả của từng supplier

Hãy kiểm tra hợp đồng dữ liệu trước khi chạy Spring Integration. Unit test giúp tách lỗi nghiệp vụ khỏi lỗi channel/correlation.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class SupplierOutcomeTest {

    @Test
    void supplierSuccessContainsPositivePrice() {
        QuoteRequest request = new QuoteRequest(
                "req-800", "SKU-1", 2);

        SupplierOutcome result = SupplierOutcome.success(
                request, "WAREHOUSE",
                new BigDecimal("170000"));

        assertEquals("req-800", result.requestId());
        assertEquals("WAREHOUSE", result.supplierId());
        assertEquals("SUCCESS", result.status());
        assertEquals(new BigDecimal("170000"),
                result.totalPriceVnd());
        assertNull(result.errorCode());
    }

    @Test
    void unavailableOutcomeIsTerminalButNotAPrice() {
        QuoteRequest request = new QuoteRequest(
                "req-801", "SKU-2", 1);

        SupplierOutcome result = SupplierOutcome.unavailable(
                request, "PARTNER", "NO_QUOTE");

        assertEquals("UNAVAILABLE", result.status());
        assertNull(result.totalPriceVnd());
        assertEquals("NO_QUOTE", result.errorCode());
    }

    @Test
    void invalidPriceIsNotAcceptedAsSuccess() {
        QuoteRequest request = new QuoteRequest(
                "req-802", "SKU-3", 1);

        assertThrows(IllegalArgumentException.class,
                () -> SupplierOutcome.success(
                        request,
                        "BACKUP",
                        BigDecimal.ZERO));
    }
}
~~~

### 17.1. Những invariant cần kiểm tra trong QuoteReportFactory

Ngoài ví dụ trên, cần unit test với một MessageGroup giả lập có:

1. Ba outcomes hợp lệ từ ba supplier → COMPLETE và giá nhỏ nhất đúng.
2. Hai SUCCESS, một UNAVAILABLE → PARTIAL_SUPPLIER_FAILURE.
3. Ba UNAVAILABLE → NO_OFFER.
4. Hai outcomes cùng supplierId → từ chối duplicate.
5. Outcomes có hai requestId khác nhau → từ chối mixed group.
6. Group chỉ 2/3 → không được tạo COMPLETE.

Nếu tạo MessageGroup trong unit test, hãy dùng các API/constructor của phiên bản Spring Integration đang sử dụng và gắn các header sequence/correlation đúng cách. Điều này không thay thế integration test cần framework thực tế phát và tập hợp replies.

## 18. Integration test với Spring context: đủ ba kết quả

Vì QuoteScatterGatherConfig đã định nghĩa flow và ba supplier giả lập, có thể kiểm thử trực tiếp bằng **JUnit 5 + spring-test**. QuoteReportsChannel là QueueChannel, nên sau khi ScatterGatherHandler đồng bộ hoàn tất, test có thể lấy report bằng receive(0).

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.List;
import java.util.Set;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(QuoteScatterGatherConfig.class)
class QuoteScatterGatherTest {

    @Autowired
    @Qualifier("quoteRequestsChannel")
    MessageChannel input;

    @Autowired
    @Qualifier("quoteReportsChannel")
    QueueChannel reports;

    @BeforeEach
    void clearReports() {
        while (reports.receive(0) != null) {
            // Dọn queue của test trước nếu Spring context được tái sử dụng.
        }
    }

    @Test
    void gathersThreeRepliesAndChoosesCheapest() {
        QuoteRequest request = new QuoteRequest(
                "req-901", "SKU-9", 2);

        assertTrue(input.send(
                MessageBuilder.withPayload(request).build()));

        Message<?> reply = reports.receive(0);
        assertNotNull(reply);

        QuoteReport report = (QuoteReport) reply.getPayload();
        assertEquals("req-901", report.requestId());
        assertEquals(3, report.expectedSuppliers());
        assertEquals(3, report.receivedOutcomes());
        assertEquals("COMPLETE", report.reportStatus());
        assertEquals("PARTNER", report.bestOffer().supplierId());
        assertEquals(new BigDecimal("160000"),
                report.bestOffer().totalPriceVnd());

        assertEquals(Set.of(
                "WAREHOUSE", "PARTNER", "BACKUP"),
                report.outcomes().stream()
                        .map(SupplierOutcome::supplierId)
                        .collect(java.util.stream.Collectors.toSet()));
        assertNull(reports.receive(0));
    }

    @Test
    void concurrentRequestsKeepTheirOwnCorrelation() throws Exception {
        ExecutorService producers = Executors.newFixedThreadPool(2);
        try {
            Callable<Boolean> first = () -> input.send(
                    MessageBuilder.withPayload(
                            new QuoteRequest(
                                    "req-902", "SKU-2", 1)).build());
            Callable<Boolean> second = () -> input.send(
                    MessageBuilder.withPayload(
                            new QuoteRequest(
                                    "req-903", "SKU-3", 3)).build());

            Future<Boolean> sentA = producers.submit(first);
            Future<Boolean> sentB = producers.submit(second);
            assertTrue(sentA.get());
            assertTrue(sentB.get());

            Message<?> resultA = reports.receive(1_000);
            Message<?> resultB = reports.receive(1_000);
            assertNotNull(resultA);
            assertNotNull(resultB);

            QuoteReport reportA =
                    (QuoteReport) resultA.getPayload();
            QuoteReport reportB =
                    (QuoteReport) resultB.getPayload();

            // Thứ tự hai report không được bảo đảm.
            assertEquals(Set.of("req-902", "req-903"),
                    Set.of(reportA.requestId(), reportB.requestId()));
            assertEquals(3, reportA.receivedOutcomes());
            assertEquals(3, reportB.receivedOutcomes());

            for (QuoteReport report : List.of(reportA, reportB)) {
                assertTrue(report.outcomes().stream().allMatch(
                        outcome -> report.requestId()
                                .equals(outcome.requestId())));
            }
        } finally {
            producers.shutdownNow();
        }
    }
}
~~~

**Điều hai test chứng minh:**

- Một request được fan-out tới ba supplier và kết hợp thành đúng một QuoteReport.
- QuoteReport giữ cả ba nguồn, chọn bestOffer theo giá và quy tắc tie-break.
- Hai request xử lý đồng thời không trộn replies nếu correlation và flow được cấu hình đúng.
- Test không phụ thuộc thứ tự về của hai reports.

**Giới hạn:** các supplier mô phỏng chạy rất nhanh, nên test này không chứng minh rằng **ba lời gọi supplier đã overlap trong thời gian**. Có thể Executor được sử dụng nhưng thực tế vẫn hoàn tất gần như nối tiếp vì scheduling. Để xác minh parallelism, cần test rào đồng bộ như phần kế tiếp.

## 19. Kiểm thử ba nhánh thực sự có thể chạy đồng thời

Một cách kiểm chứng đúng parallelism là dùng **CountDownLatch hoặc CyclicBarrier** trong ba supplier giả lập: mọi branch phải bắt đầu trước khi bất kỳ branch nào được phép hoàn tất. Nếu flow thực thi ba branch tuần tự trên một thread, test sẽ bị timeout.

### 19.1. Test probe dùng latch

~~~java
import java.math.BigDecimal;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

final class ParallelQuoteProbe {
    final CountDownLatch allStarted = new CountDownLatch(3);
    final CountDownLatch release = new CountDownLatch(1);

    SupplierOutcome invoke(
            QuoteRequest request,
            String supplierId,
            long unitPrice) {

        allStarted.countDown();
        try {
            if (!release.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("PARALLEL_PROBE_TIMEOUT");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("PROBE_INTERRUPTED", ex);
        }

        return SupplierOutcome.success(
                request,
                supplierId,
                BigDecimal.valueOf(unitPrice)
                        .multiply(BigDecimal.valueOf(request.quantity())));
    }
}
~~~

Đưa ba call tới probe này vào ba recipient sub-flow thay cho các SupplierQuotePort ở phần cấu hình; mỗi branch truyền supplierId và unitPrice tương ứng.

Test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.support.MessageBuilder;

// Đây là phần thân của integration test đã inject:
// MessageChannel input; QueueChannel reports; ParallelQuoteProbe probe.
@Test
void threeSupplierTasksCanOverlap() throws Exception {
    ExecutorService callerPool = Executors.newSingleThreadExecutor();
    try {
        Future<Boolean> send = callerPool.submit(() ->
                input.send(MessageBuilder
                        .withPayload(new QuoteRequest(
                                "req-parallel", "SKU-P", 1))
                        .build()));

        // Ba suppliers phải đi vào probe trước khi được release.
        assertTrue(probe.allStarted.await(
                3, TimeUnit.SECONDS));
        probe.release.countDown();

        assertTrue(send.get(8, TimeUnit.SECONDS));
        assertNotNull(reports.receive(1_000));
    } finally {
        probe.release.countDown(); // Không treo worker nếu assertion lỗi.
        callerPool.shutdownNow();
    }
}
~~~

**Điều kiện của test:** cần một **Spring context test riêng** trong đó ba supplier bean của QuoteScatterGatherConfig được thay bằng ba port gọi cùng một ParallelQuoteProbe. Đoạn @Test là mảnh phương thức chèn vào lớp test đó, **không chạy độc lập** nếu chưa khai báo các injected fields và flow test. Đây là phép kiểm tra overlap deterministic hơn việc chỉ đo elapsed milliseconds hoặc gọi Thread.sleep.

### 19.2. Không giữ cùng một probe qua nhiều test

CountDownLatch sau khi về 0 không thể reset. Tạo probe mới cho từng test hoặc dùng test context riêng. Đồng thời phải giải phóng latch trong finally, vì nếu assertion thất bại mà worker vẫn đợi, suite có thể treo hoặc làm nhiễu các test khác.

### 19.3. Test không chứng minh production luôn đạt SLA

Ba task cùng chạm probe chứng minh **có khả năng overlap** trong test context, không chứng minh hệ thống production có đủ CPU, HTTP connections, thread pool hoặc capacity để mọi request đều hoàn tất trước deadline.

Production vẫn cần load test đo **p95/p99 gather duration, active worker count, queue depth, supplier timeouts và tỉ lệ partial reports**.

## 20. Test nhánh UNAVAILABLE và nhóm thiếu reply

Một bài kiểm thử production không thể chỉ có ba supplier trả giá thành công. Ít nhất phải mô phỏng **một reply là failure outcome** và **một nhánh không phát reply**; hai trường hợp này khác nhau hoàn toàn với Gather.

### 20.1. Nhánh trả failure outcome có chủ đích

Thay PartnerSupplier trong test bằng:

~~~java
final class UnavailablePartnerSupplier
        implements SupplierQuotePort {

    @Override
    public SupplierOutcome quote(QuoteRequest request) {
        return SupplierOutcome.unavailable(
                request,
                "PARTNER",
                "NO_CAPACITY");
    }
}
~~~

Với WAREHOUSE và BACKUP vẫn trả offer:

~~~text
Expected: 3 replies
Received:
  WAREHOUSE -> SUCCESS
  PARTNER   -> UNAVAILABLE
  BACKUP    -> SUCCESS

Gather group = 3/3 terminal outcomes
Report:
  reportStatus = PARTIAL_SUPPLIER_FAILURE
  bestOffer    = WAREHOUSE
  receivedOutcomes = 3
~~~

Đây là **partial supplier success**, không phải **partial aggregation**. Aggregator vẫn có đủ ba kết quả terminal để release.

### 20.2. Nhánh không reply

Trong một Spring context test riêng, cố tình cấu hình Partner sub-flow trả null:

~~~java
// Chỉ dùng làm phản ví dụ trong test.
.recipientFlow(flow -> flow
        .handle(QuoteRequest.class, (request, headers) -> null))
~~~

Khi đó Gather mặc định kỳ vọng 3 replies nhưng chỉ nhận 2. Với gatherTimeout ngắn được cấu hình tường minh, kiểm thử phải xác minh:

1. Không có QuoteReport COMPLETE được tạo.
2. Caller nhận timeout/reply-required failure theo semantics của endpoint phiên bản đang dùng.
3. Nhóm chưa đủ không được giữ vô hạn mà không có cleanup policy.
4. Nếu bật partial aggregation, report phải chỉ rõ supplier nào thiếu.

Không dùng Thread.sleep để “đợi chắc đã xong”. Dùng các công cụ đồng bộ/timeout bounded như CompletableFuture, Awaitility hoặc MessageGroupStore được kiểm tra có hạn.

### 20.3. Lỗi trong sub-flow đồng bộ

Tạo một nhánh xử lý đồng bộ ném IllegalStateException trước khi reply. Test xác nhận exception của branch có thể truyền ra caller và không tạo một kết quả Gather đầy đủ. Đây là hành vi khác so với một reply SupplierOutcome.unavailable hợp lệ.

Khi product yêu cầu “một supplier lỗi không làm hỏng hai báo giá còn lại”, phải thiết kế **error boundary riêng trong mỗi sub-flow**, không dựa vào việc ScatterGatherHandler tự bỏ qua mọi exception.

### 20.4. Lỗi trong sub-flow bất đồng bộ

Tạo một nhánh chạy trên ExecutorChannel ném exception. Bố trí errorChannel nhận ErrorMessage, lấy failedMessage và kiểm tra metadata correlation/reply. Nếu dùng compensation, phát **một** SupplierOutcome terminal về Gather, rồi xác minh report có đủ ba outcomes.

Đồng thời tạo test khi error handler không thể xác định supplierId hoặc missing failedMessage: **không đoán supplier**, mà đưa lỗi vào quarantine/alert. Một compensation mang sai source identity có thể làm Aggregator ghép nhầm hoặc đếm trùng.

## 21. Một mẫu cấu hình Gather cho partial release

Trong bài thực hành nâng cao, nếu nghiệp vụ chấp nhận quyết định từ hai trong ba supplier và hạn xử lý là vài giây, có thể cấu hình cơ chế timeout của Aggregator riêng với gatherTimeout.

~~~java
// Chỉ là mảnh DSL tập trung vào Gather; các recipient flows
// được định nghĩa tương tự ví dụ trước.
.scatterGather(
        scatterer -> scatterer
                .recipientFlow(/* supplier A */)
                .recipientFlow(/* supplier B */)
                .recipientFlow(/* supplier C */),
        gatherer -> gatherer
                .groupTimeout(2_000)
                .sendPartialResultOnExpiry(true)
                .outputProcessor(PartialQuoteReportFactory::fromGroup),
        options -> options
                .gatherTimeout(10_000))
~~~

Để biến mảnh cấu hình thành chương trình thực thi, cần định nghĩa:

- Các recipientFlow có reply như phần Java DSL đầy đủ.
- **PartialQuoteReportFactory** biết tập supplier được mời và phân biệt INCOMPLETE với COMPLETE.
- Một MessageGroupStore và cleanup/late-arrival policy phù hợp.
- Deadline theo từng request, không chỉ các con số cố định minh họa.

**groupTimeout không tự kiểm tra đủ 2 replies.** Khi nhóm chỉ có 1 reply mà timeout, cấu hình partial có thể vẫn phát result từ 1 reply nếu policy cho phép. Nếu business yêu cầu ít nhất 2, hãy đặt **ReleaseStrategy và partial processor** kiểm tra minCount hoặc một workflow state phù hợp; đừng nói “groupTimeout=2000 nghĩa là 2-of-3”.

### 21.1. K-of-N không đồng nghĩa tìm được giá tốt nhất

Nếu K=2, N=3 và BACKUP là nhà cung cấp rẻ nhất nhưng trả lời chậm, một báo cáo kết thúc ngay sau hai replies có thể chọn sai khi so với đầy đủ ba offer. Đó là trade-off nghiệp vụ.

Khi xác định K:

- Công bố số nhà cung cấp đã phản hồi.
- Định nghĩa tối thiểu bao nhiêu offers hợp lệ, không chỉ bao nhiêu terminal outcomes.
- Ghi rõ trạng thái INCOMPLETE/PARTIAL.
- Có SLA cho late reply và quy tắc freeze/update report.
- Đừng thực hiện thanh toán tự động trên một report chưa đạt mức tin cậy yêu cầu.

### 21.2. Khi nào không nên dùng request/reply Scatter-Gather?

Không nên giữ một request thread chờ quá lâu khi:

- Nhà cung cấp có thể phản hồi sau nhiều phút/giờ.
- Mỗi nhánh là một saga có nhiều side effect và compensation.
- Hệ thống cần phục hồi sau restart mà không mất tiến độ.
- Một request có hàng nghìn recipients hoặc không biết trước số replies.
- Cần chỉnh sửa quyết định nhiều lần khi replies đến muộn.

Khi đó, một **workflow bất đồng bộ có inbox/outbox và trạng thái từng supplier** thường hợp lý hơn. Vẫn là logic Scatter-Gather ở mức pattern, nhưng không nhất thiết triển khai bằng một ScatterGatherHandler chặn caller.

## 22. Theo dõi chất lượng Gather

Một flow có thể scatter được nhiều request, nhưng nếu Gather thường xuyên thiếu reply thì chức năng tổng hợp vẫn không đáp ứng nghiệp vụ. Cần đo cả điểm đầu và cuối.

| Metric / tín hiệu | Ý nghĩa |
| --- | --- |
| **scatter_requests_total** | Tổng request được phát đi |
| **scatter_selected_recipients{route}** | Số recipients được mời, theo route hữu hạn |
| **supplier_requests_total{supplier}** | Số attempt gọi từng supplier |
| **supplier_outcomes_total{supplier,status}** | Các terminal outcomes theo nguồn |
| **supplier_latency_seconds{supplier}** | Độ trễ supplier |
| **gather_expected_replies** | Số reply dự kiến theo một correlation group |
| **gather_received_replies** | Số reply đã nhận, không phải số success |
| **gather_duration_seconds** | Thời gian từ scatter đến kết quả |
| **gather_timeout_total** | Số request hết thời gian chờ |
| **gather_partial_report_total** | Số báo cáo INCOMPLETE |
| **gather_group_pending** | Số group chưa release |
| **gather_group_age_seconds** | Tuổi các group đang chờ |
| **gather_late_reply_total** | Reply đến sau deadline hoặc sau group completion |
| **gather_duplicate_reply_total** | Nhiều reply cùng supplier identity/request |
| **gather_correlation_errors_total** | Reply thiếu hoặc sai correlation metadata |
| **gather_error_recovery_failed_total** | Error flow không tạo được compensation/alert |
| **scatter_executor_rejections_total** | Task không được chấp nhận vì quá tải |

Các metric có nhãn supplier/route nên giới hạn theo **allowlist**. Không dùng requestId, orderId, tenantId tùy ý hay raw error message làm metric label vì cardinality và nguy cơ lộ dữ liệu. Chúng có thể được dùng trong log/tracing có kiểm soát truy cập và retention phù hợp.

### 22.1. Ví dụ log quyết định Gather

~~~json
{
  "requestId": "req-701",
  "expectedSuppliers": 3,
  "receivedOutcomes": 3,
  "successfulOffers": 2,
  "supplierFailures": 1,
  "bestSupplier": "WAREHOUSE",
  "reportStatus": "PARTIAL_SUPPLIER_FAILURE",
  "gatherDurationMs": 1820
}
~~~

Đây là **log mẫu**. Không log raw supplier credentials, token, thông tin khách hàng hoặc toàn bộ HTTP response. Nếu một request nhận 2/3 outcomes vì một supplier im lặng, reportStatus phải là INCOMPLETE thay vì PARTIAL_SUPPLIER_FAILURE theo phân biệt trong bài.

### 22.2. Alert cần quan tâm

- Tỉ lệ gatherTimeout tăng sau khi đổi thread pool hoặc supplier adapter.
- Nhiều nhóm pending quá thời hạn cho phép.
- Một supplier không còn trả reply nhưng request vẫn được phát đến supplier ấy.
- Group có duplicate sequenceNumber hoặc supplierId.
- Kết quả bestOffer bất thường do schema/currency conversion.
- ErrorMessage đi vào global errorChannel nhưng không được phục hồi đúng Gather.
- Report cho cùng requestId được phát hai lần sau redelivery/restart.
- Queue depth tăng trong khi số request mới không tăng tương ứng.

**Quan sát nguyên nhân:** một timeout có thể do supplier chậm, worker pool bị starvation, mất header replyChannel, group correlation sai hoặc Aggregator không release. Đừng kết luận “supplier timeout” chỉ vì caller không nhận report.

## 23. Phương án Auction với PublishSubscribeChannel

Ví dụ Java DSL đầy đủ ở trên sử dụng biến thể **distribution**, vì nó khai báo RecipientListRouter với ba recipientFlow. Khi muốn broadcast cùng request đến một tập subscriber đã khai báo sẵn, có thể dùng biến thể **auction** với PublishSubscribeChannel.

Một channel auction có TaskExecutor:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.PublishSubscribeChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

// Trong @Configuration đã có bean quoteWorkers.
@Bean
PublishSubscribeChannel quoteAuctionChannel(
        ThreadPoolTaskExecutor quoteWorkers) {
    PublishSubscribeChannel channel =
            new PublishSubscribeChannel(quoteWorkers);
    channel.setApplySequence(true);
    return channel;
}
~~~

Các supplier Service Activator có thể đăng ký là subscriber của **quoteAuctionChannel**. Ở biến thể auction của ScatterGatherHandler, channel này làm nhiệm vụ **scatterChannel**; một AggregatingMessageHandler vẫn chịu trách nhiệm Gather.

**Không dùng cùng lúc cả auction scatterChannel và recipient-list scatterer** như thể đó là hai bước bắt buộc. Đó là hai phương án khác nhau. Với Bean/Java configuration thuần, cần cấu hình channel, gatherer, replyChannel và applySequence rõ; Java DSL có hỗ trợ convenience để lắp Scatter-Gather nhưng phải kiểm tra API đúng phiên bản.

### 23.1. Auction có giống một PublishSubscribeChannel thông thường?

Không hoàn toàn. PublishSubscribeChannel chỉ phát message tới subscribers; **nó không tự đợi các reply và tạo QuoteReport**. Phần Gather do ScatterGatherHandler và AggregatingMessageHandler đảm nhận.

Khi sử dụng PublishSubscribeChannel bên ngoài Scatter-Gather, nếu subscriber trả reply nhưng không có nơi xử lý reply, đó vẫn chưa phải một hệ thống Scatter-Gather đúng nghĩa.

### 23.2. Khi nào không đặt Executor trên cả hai tầng?

Nếu PublishSubscribeChannel đã có executor, có thể không cần thêm ExecutorChannel ngay đầu từng sub-flow cho cùng một nhiệm vụ. Hai tầng executor nối nhau có thể làm tăng thread hops, hàng đợi và khiến việc tính tổng deadline khó hiểu.

Chọn một ranh giới async có chủ đích, trừ khi cần bulkhead/cô lập capacity theo từng supplier. Dùng metrics/trace để xác nhận điểm thực hiện I/O và lượng backpressure thực tế.

## 24. Những sai lầm thường gặp khi Gather kết quả song song

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Tưởng Scatter-Gather tự chạy parallel | Nhánh có thể chạy nối tiếp | ExecutorChannel hoặc PublishSubscribeChannel có executor |
| Chỉ kết nối ba replies vào một channel | Không có correlation/release đúng | Aggregator hoặc workflow state |
| Không bật applySequence khi tự dựng scatterer | Gather không biết đủ N | Kiểm tra sequence metadata |
| Dùng correlation key cố định cho mọi request | Trộn offers của các request khác nhau | Correlation riêng theo request/attempt |
| Xóa replyChannel ở một nhánh | Gather thiếu result | Bảo toàn routing headers nội bộ |
| Handler cuối trả null | Không có reply, group có thể treo | Trả outcome terminal không null |
| Một supplier lỗi đồng bộ không được xử lý | Hủy tác dụng replies từ nhánh khác | Error boundary và compensation riêng |
| ErrorMessage được xem như một reply bình thường | Nhầm payload Throwable với business outcome | Chuyển lỗi thành outcome có kiểu khi phù hợp |
| Đặt gatherTimeout nhưng không groupTimeout/cleanup | Group thiếu reply tiếp tục tồn tại | Phân biệt hai timeout, quản lý MessageGroupStore |
| Cho phép partial release rồi dùng processor đủ 3 | Processor báo lỗi khi group chỉ có 2 | Partial report contract và factory riêng |
| Dùng count replies thay vì recipient identities | Một supplier lặp có thể che supplier thiếu | Dedup theo requestId + supplierId |
| Xóa group ngay sau release | Late reply có thể tạo group mới | Retention/tombstone và late-arrival policy |
| Bật retry toàn Scatter-Gather vô điều kiện | Gọi lại những nhánh đã có side effect | Per-supplier idempotency và retry budget |
| Dùng MessageHeaders.ID để chống trùng | ID kỹ thuật có thể đổi qua redelivery | Business requestId và supplierId |
| Thread pool không giới hạn | Quá tải HTTP/DB và queue | Bounded pool, rate limit, circuit breaker |
| Coi một báo giá ACCEPTED là hoàn tất | Quyết định trước khi có final price | Outcome semantics rõ |
| Chọn bestOffer theo thứ tự arrival | Kết quả không deterministic | Comparator theo giá và tie-break |
| Không log expected/received | Không biết nhánh nào thiếu | Manifest, metrics, tracing |

## 25. Bài thực hành: Gather kết quả từ ba dịch vụ kiểm tra đơn hàng

Một hệ thống xử lý đơn hàng cần lấy kết quả từ ba dịch vụ:

- **inventoryCheck**: có đủ hàng không?
- **fraudCheck**: mức rủi ro là gì?
- **shippingEstimate**: dự kiến phí vận chuyển bao nhiêu?

Request:

~~~java
record OrderAssessmentRequest(
        String requestId,
        String orderId,
        String tenantId,
        int itemCount) {}
~~~

Ba nhánh trả kết quả có kiểu:

~~~text
InventoryOutcome:
  supplierId = INVENTORY
  available = true/false

FraudOutcome:
  supplierId = FRAUD
  risk = LOW / MEDIUM / HIGH

ShippingOutcome:
  supplierId = SHIPPING
  estimatedCost = số tiền hợp lệ
~~~

Một **AssessmentReport** tổng hợp:

1. requestId gốc.
2. Các nguồn đã phản hồi.
3. Kết quả của từng nguồn, bao gồm failure outcome nếu có.
4. Trạng thái COMPLETE, DEGRADED, INCOMPLETE hoặc FAILED theo hợp đồng.
5. Quyết định: APPROVE, MANUAL_REVIEW hoặc HOLD.

### 25.1. Các bước thực hành

1. Xây dựng ba port, dùng record outcome hoặc sealed hierarchy có định danh supplier rõ.
2. Tạo IntegrationFlow với Scatter-Gather distribution và ba recipientFlow.
3. Thêm ExecutorChannel với bounded ThreadPoolTaskExecutor để kiểm tra việc chạy song song.
4. Để mỗi branch trả **một result không null**; lỗi domain đã biết trở thành terminal failure outcome có mã an toàn.
5. Dùng Aggregator tạo AssessmentReport khi đủ ba terminal outcomes.
6. Kiểm tra correlationId/sequenceNumber/sequenceSize thực nhận ở từng branch và Gather.
7. Dùng CountDownLatch xác minh ba branch có thể overlap.
8. Cho fraudCheck chậm hơn hai nhánh còn lại, chứng minh Aggregator đợi đúng policy.
9. Cho shippingEstimate không trả reply, xác minh gatherTimeout và trạng thái/cleanup của group.
10. Bổ sung groupTimeout và partial processor cho báo cáo INCOMPLETE có danh sách nguồn thiếu.
11. Gửi hai requestId khác nhau đồng thời; không được trộn các outcomes.
12. Mô phỏng reply trùng từ inventoryCheck và reply đến muộn sau partial report.
13. Cho fraudCheck ném exception async, tạo error flow có compensation hợp lệ hoặc quarantine nếu không thể.
14. Retry request sau khi một nhánh có side effect; xác minh idempotency key theo logical action.
15. Thêm metrics cho duration, expected/received, supplier failures, group pending và late reply.

### 25.2. Tiêu chí đạt

| Tiêu chí | Kết quả cần quan sát |
| --- | --- |
| Fan-out đúng | Ba supplier được mời một lần theo policy |
| Parallelism | Cả ba branch cùng chạm concurrency probe trước khi release |
| Correlation | Mỗi request có một group riêng |
| Gather đầy đủ | 3/3 terminal outcomes tạo một AssessmentReport |
| Lỗi nghiệp vụ một branch | Được thể hiện như outcome, không xóa hai branch khác |
| Lỗi kỹ thuật một branch | Error flow/retry hoặc incomplete report rõ ràng |
| Group timeout | Không báo COMPLETE nếu còn reply thiếu |
| Duplicate reply | Không được đếm như supplier thứ tư |
| Late reply | Tuân theo freeze hoặc revision policy |
| Replay | Không tạo side effect trùng ngoài hợp đồng |
| Monitoring | Phân biệt timeouts, errors, incomplete, duplicate và latency |

### 25.3. Câu hỏi tự kiểm tra

1. Scatter khác Gather ở vai trò nào?
2. PublishSubscribeChannel mặc định có tạo nhiều thread không?
3. Auction và distribution có sự khác biệt gì trong việc chọn recipients?
4. Vì sao sequenceSize phải dựa trên số recipient thực sự được chọn?
5. Header replyChannel của nhánh phải dẫn tới đâu?
6. Một terminal UNAVAILABLE outcome có được tính là reply không?
7. Một ErrorMessage trên global errorChannel có được tự tính là reply cho Aggregator không?
8. Vì sao cùng requestId có thể có nhiều correlation groups qua các lần retry?
9. Gather dựa vào thứ tự arrival có phải quyết định deterministic không?
10. gatherTimeout và groupTimeout khác nhau như thế nào?
11. Khi bật partial release, tại sao QuoteReportFactory yêu cầu 3 outcomes không còn phù hợp?
12. Một supplier trả hai replies còn supplier khác im lặng gây vấn đề gì?
13. expireGroupsUponCompletion có ảnh hưởng như thế nào tới late reply?
14. Vì sao tăng số worker threads không tự giải quyết mọi timeout?
15. Khi nào nên thay request/reply ScatterGatherHandler bằng workflow bền?

## 26. Checklist trước khi triển khai

- Đã chọn rõ **auction** hay **distribution** theo quy tắc mời supplier.
- Có giới hạn số recipient và số request đang scatter đồng thời.
- Parallelism được tạo bằng executor/channel phù hợp và **đã được kiểm thử**.
- Mỗi request có correlation group riêng; mỗi branch giữ đúng sequence metadata.
- Endpoint cuối mỗi branch có **reply không null** khi hợp đồng cần Gather.
- Tất cả replies trở về đúng gather/replyChannel đã được cấu hình.
- Manifest expected suppliers được quản lý, không suy ra từ số replies đã tới.
- ReleaseStrategy phản ánh đúng all-of-N, K-of-N hoặc deadline nghiệp vụ.
- ErrorMessage và failure outcome được phân biệt; lỗi async có errorChannel/recovery.
- Timeout supplier, groupTimeout, gatherTimeout và Gateway timeout có ngân sách nhất quán.
- Partial result được đánh dấu INCOMPLETE và có danh sách nguồn thiếu.
- QuoteReport/AssessmentReport không phụ thuộc thứ tự replies đến.
- Có duplicate protection theo requestId + supplierId hoặc logical action.
- MessageGroupStore, group expiry, tombstone và late-arrival policy phù hợp SLA.
- Có persistent progress/outbox/inbox nếu phải phục hồi qua restart.
- Side effects tại supplier có idempotency hoặc đối soát thích hợp.
- Thread pool, HTTP connection pools, queues và rate limits đều được giới hạn.
- Log/metrics phân biệt scatter attempts, supplier outcomes và gather completed/incomplete.
- Test có ít nhất: success, one failure outcome, missing reply, async error, concurrent requests, parallel overlap, duplicate và timeout.

**Kết luận:** Gather kết quả từ các nhánh song song không chỉ là thu đủ một vài message. Một Scatter-Gather đáng tin cần xác định **ai được mời**, **mỗi reply thuộc request nào**, **thế nào là đủ kết quả**, **điều gì xảy ra khi một nhánh lỗi hoặc trễ**, và **khi nào report được phép công bố**. Trong Spring Integration, kết hợp ScatterGatherHandler, RecipientListRouter hoặc PublishSubscribeChannel, Aggregator, correlation/sequence, ExecutorChannel và error handling đúng chỗ giúp xây dựng quy trình tổng hợp nhanh, có thể kiểm thử và quan sát được mà không che giấu kết quả thiếu.

## Tài liệu tham khảo

- [Spring Integration Reference — Scatter-Gather](https://docs.spring.io/spring-integration/reference/scatter-gather.html): auction/distribution, ScatterGatherHandler, replyChannel, error handling, gatherTimeout và configuration.
- [Spring Integration Reference — Aggregator](https://docs.spring.io/spring-integration/reference/aggregator.html): MessageGroup, correlation/release strategy, groupTimeout, partial result và late-arrival.
- [Spring Integration Reference — PublishSubscribeChannel](https://docs.spring.io/spring-integration/reference/channel/configuration.html): executor, applySequence và xử lý lỗi.
- [Spring Integration Reference — Java DSL](https://docs.spring.io/spring-integration/reference/dsl.html): scatterGather, recipientFlow, outputProcessor và channel.
- [Spring Integration API — ScatterGatherSpec](https://docs.spring.io/spring-integration/docs/6.5.2/api/org/springframework/integration/dsl/ScatterGatherSpec.html): gatherTimeout, gatherChannel và errorChannel.
- [Spring Integration API — AggregatorSpec](https://docs.spring.io/spring-integration/docs/6.2.6/api/org/springframework/integration/dsl/AggregatorSpec.html): groupTimeout, sendPartialResultOnExpiry, releaseStrategy.
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): ErrorMessage, errorChannel và xử lý exception đồng bộ/bất đồng bộ.
- [Enterprise Integration Patterns — Scatter-Gather](https://www.enterpriseintegrationpatterns.com/patterns/messaging/BroadcastAggregate.html): mô hình phát yêu cầu tới nhiều recipient và tổng hợp replies.
