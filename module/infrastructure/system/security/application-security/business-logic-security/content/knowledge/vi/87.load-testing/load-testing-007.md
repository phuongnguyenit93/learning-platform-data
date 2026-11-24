# Kiểm tra tính toàn vẹn trong kiểm thử tải (Load test integrity checks)

Trong chương **Load Testing** của module bảo vệ logic nghiệp vụ, kiểm thử tải cần trả lời đồng thời hai câu hỏi: hệ thống xử lý được bao nhiêu công việc và các công việc đó có còn đúng quy tắc khi nhiều yêu cầu cạnh tranh, retry hoặc gặp lỗi một phần hay không.

**Load test integrity checks** là các kiểm tra nhằm phát hiện mất dữ liệu, ghi trùng, vượt hạn mức, chuyển trạng thái trái phép, sai phạm vi quyền hoặc sai lệch giữa dữ liệu nội bộ và hiệu ứng bên ngoài trong một lần chạy tải. Một lần chạy có độ trễ đẹp nhưng hoàn tiền hai lần vẫn thất bại về an toàn nghiệp vụ.

Bài học tập trung vào business invariants, state machine, quyền theo đối tượng, transaction và idempotency dưới tải. Mô hình, số tiền và workload bên dưới là ví dụ tổng hợp cho môi trường kiểm thử; adapter bên thanh toán và các đích tạo hiệu ứng phải được cấu hình đúng phạm vi test.

## 1. Định nghĩa đúng đơn vị quan sát

### 1.1. Một HTTP request không đồng nghĩa một nghiệp vụ

Một ý định hoàn tiền có thể đi qua nhiều lần thử:

```text
businessIntent = hoàn 40.000 VND cho giao dịch đã xác định
    attempt-1 → ứng dụng gửi lệnh, client nhận timeout
    attempt-2 → client retry cùng ý định
    callback-1 → provider thông báo thành công
    callback-2 → giao lại cùng sự kiện
```

Chuỗi này có nhiều request, nhưng theo hợp đồng giả định chỉ được tạo một khoản hoàn. Nếu báo cáo chỉ đếm `2xx`, số request hoặc số callback, ta chưa biết đã có bao nhiêu hiệu ứng tài chính thực sự.

Cần phân biệt:

| Đơn vị | Ý nghĩa |
|---|---|
| Business intent | Một ý định nghiệp vụ có định danh và nội dung ổn định |
| Attempt | Một lần thử gửi hoặc thực thi ý định |
| Event | Một sự kiện nghiệp vụ hoặc tích hợp có danh tính riêng |
| Delivery | Một lần giao event; cùng event có thể được giao nhiều lần |
| Committed record | Bản ghi đã commit, không phải dữ liệu đang nằm trong transaction chưa kết thúc |
| Financial effect | Khoản thu/hoàn thực tế theo hợp đồng tích hợp, phân biệt với số lần gọi HTTP |
| Ledger posting | Ghi nhận tài chính nội bộ; số dòng phụ thuộc mô hình sổ và không mặc định bằng số giao dịch |

Một giao dịch hợp lệ có thể có nhiều capture, nhiều bước hoặc nhiều bút toán nếu mô hình cho phép. Vì vậy, quy tắc “mỗi ý định chỉ một hiệu ứng” phải gắn với loại ý định cụ thể, không áp đặt lên mọi đơn hàng hoặc mọi hàng trong ledger.

### 1.2. Ba lớp kết quả cần tách biệt

- **Hiệu năng:** độ trễ, thông lượng, tài nguyên và backlog.
- **Kết quả nghiệp vụ:** thành công, từ chối vì hết hạn mức, không đủ quyền, trạng thái sai hoặc xung đột được xử lý theo thiết kế.
- **Tính toàn vẹn:** dữ liệu và hiệu ứng có tuân thủ bất biến hay không, kể cả với request trả lỗi hoặc timeout.

Một phản hồi từ chối vì coupon đã hết lượt có thể đúng về nghiệp vụ. Một phản hồi `500` có thể xảy ra sau khi tiền đã được thu. Cần quan sát trạng thái bền vững và hệ thống ngoài để phân loại, không suy từ status code sang kết quả tiền.

## 2. Chuyển quy tắc nghiệp vụ thành kiểm tra toàn vẹn

### 2.1. Các bất biến điển hình

| Nhóm | Bất biến cần đặc tả | Sai lệch có thể xuất hiện dưới tải |
|---|---|---|
| Giới hạn tiền | Tổng đã hoàn và đang giữ chỗ không vượt mức được phép | Hai transaction cùng tiêu một số dư |
| Idempotency | Retry cùng ý định không tạo thêm hiệu ứng trái hợp đồng | Timeout dẫn tới lệnh hoàn thứ hai |
| Trạng thái | Chỉ các chuyển trạng thái hợp lệ được commit | Callback cũ kéo trạng thái thành công lùi lại |
| Quyền | Actor chỉ tác động đúng đối tượng, action và tenant | Cache hoặc worker dùng quyền sai ngữ cảnh |
| Số lượng | Tổng đã giữ và đã sử dụng không vượt quota/tồn khả dụng theo mô hình | Nhiều request cùng lấy lượt coupon cuối |
| Quan hệ | Payment, refund, order và tenant liên kết đúng | Cập nhật nhầm đối tượng sau khi đổi payload hoặc dùng batch |
| Giá và currency | Amount/currency khớp dữ liệu đã được chấp nhận | Race giữa báo giá mới và thanh toán theo giá cũ |
| Tích hợp | Trạng thái nội bộ được đối soát với hiệu ứng bên ngoài | Provider thành công nhưng local ghi thất bại |
| Khả năng xử lý tiếp | Ý định đã chấp nhận có kết quả hoặc công việc bền vững để tiếp tục | Commit trạng thái nhưng mất công việc gửi đi |

Mỗi bất biến phải có oracle và phạm vi. Ví dụ, “không âm” chỉ đúng với loại số dư không cho vay; “tổng hoàn bằng tổng thu” chỉ đúng khi toàn bộ khoản thu đều được phép hoàn và đã yêu cầu hoàn toàn bộ.

### 2.2. Mô hình hoàn tiền để minh họa

Gọi:

```text
R = tổng tiền được phép hoàn theo giao dịch gốc và chính sách
F = tổng khoản hoàn đã được ghi nhận thành công
P = tổng khoản đang giữ chỗ để xử lý
available = R − F − P

F >= 0
P >= 0
F + P <= R
```

Với `R = 100.000`, `F = 30.000`, `P = 20.000`, phần còn lại là 50.000 VND. Hai ý định khác nhau cùng yêu cầu hoàn 40.000 không được làm tổng giữ chỗ mới thành 80.000.

Khi khoản 20.000 đang giữ chỗ chuyển thành hoàn thành công, `F` tăng 20.000 và `P` giảm 20.000. Tổng `F + P` không đổi. Nếu cả hai cùng giữ khoản này, tiền bị đếm hai lần; nếu cả hai cùng bỏ khoản này, hệ thống có thể cho hoàn thêm trái phép.

Một khoản timeout chưa biết kết quả không được tùy tiện chuyển thành thất bại cuối cùng để giải phóng giữ chỗ. Mô hình trạng thái phải biểu diễn được sự chưa xác định và cơ chế đối soát.

### 2.3. Tính nhất quán nội bộ chưa đủ chứng minh đúng chính sách

Nếu cả amount được duyệt, khoản giữ chỗ và lệnh provider đều bị sửa từ 40.000 thành 60.000 theo cùng một lỗi, chúng có thể khớp nhau nhưng vẫn trái phép. Cần đối chiếu thêm với dữ liệu có thẩm quyền: báo giá, hạn mức, quyền của actor, chính sách và nội dung ý định đã chấp nhận.

Ngược lại, lấy expected từ chính helper production có thể khiến test sao chép lỗi. Nên có ví dụ tính tay, mô hình tham chiếu hoặc kế hoạch workload độc lập cho các trường hợp quan trọng.

## 3. Thiết kế workload làm lộ điều kiện gây lỗi

### 3.1. Có tải phân tán và tải cạnh tranh tài nguyên

Nếu mỗi virtual user dùng một order riêng, test có thể tạo nhiều request song song mà không kiểm tra tranh chấp hạn mức. Cần chủ đích cả hai nhóm:

| Nhóm workload | Đặc điểm | Mục tiêu |
|---|---|---|
| Phân tán | Nhiều actor và tài nguyên độc lập | Kiểm tra xử lý diện rộng, dữ liệu không lẫn giữa người dùng |
| Tài nguyên nóng | Nhiều ý định cùng nhắm một order, ví, coupon hoặc quota | Kiểm tra giữ chỗ, khóa và cập nhật có điều kiện |
| Retry | Nhiều attempt dùng cùng business intent và key theo hợp đồng | Kiểm tra deduplication và trạng thái đang xử lý |
| Nhiều ý định khác nhau | Key khác nhau nhưng cùng tiêu hạn mức | Kiểm tra bất biến tổng, không chỉ idempotency |
| Trái phép có kiểm soát | Actor khác owner/tenant hoặc thiếu role | Kiểm tra quyền vẫn giữ dưới tải và cache nóng |
| Sự kiện bất đồng bộ | Delivery trùng, đến trễ hoặc đảo thứ tự | Kiểm tra state machine và đối soát |

Một request vừa sai tenant vừa vượt amount có thể bị chặn vì lý do không phải mục tiêu. Tạo các nhóm dữ liệu tập trung để biết ranh giới nào thực sự được kiểm tra.

### 3.2. Giữ dữ liệu đối chứng còn đủ điều kiện

Test một lần dùng coupon có thể thành công, nhưng ở phút tiếp theo coupon đã hết lượt và mọi request đều bị từ chối. Thông lượng phản hồi lúc đó không còn phản ánh cùng loại nghiệp vụ ban đầu.

Phải quyết định trước workload nào cố ý làm cạn tài nguyên và workload nào cần bổ sung dữ liệu để duy trì một cơ cấu kết quả. Việc bổ sung phải theo cơ chế test có kiểm soát, không lén reset hạn mức trong khi đang đo một bất biến trên cùng tài nguyên.

Đối chứng được phép cần có đủ số lần thực thi thành công. Nếu mọi request hợp lệ đều bị chặn, hệ thống có thể không vi phạm tiền nhưng lần chạy chưa chứng minh khả năng xử lý công việc mục tiêu.

### 3.3. Tải chào vào, tải thực gửi và tải hoàn thành

Phân biệt số ý định được lên lịch, số thực sự bắt đầu, số attempt gửi đi và số ý định đạt kết quả cuối cùng. Công cụ tạo tải có thể không phát đủ workload khi thiếu tài nguyên hoặc khi mô hình chờ phản hồi làm chậm tốc độ phát.

Với mô hình vòng lặp chờ response, hệ thống chậm có thể tự làm giảm số yêu cầu mới. Với mô hình phát theo lịch độc lập, cần theo dõi các tác vụ không bắt đầu đúng lịch hoặc không được phát. Mỗi mô hình phục vụ câu hỏi khác nhau; báo cáo phải nêu tải thực đạt, không chỉ cấu hình mong muốn.

Retry cũng là tải thật. Ghi cả số ý định duy nhất và tổng attempt để không che khuất khuếch đại tải do timeout.

## 4. Thiết kế định danh và khả năng quan sát

### 4.1. Chuỗi định danh phải truy được xuyên các bước

Một lần chạy nên liên kết được:

```text
runId
  └─ scenarioId
      └─ businessIntentId
          ├─ attemptId
          ├─ idempotency scope + key
          ├─ resourceId + tenantId + actorId
          ├─ outbox/message identifiers
          └─ provider reference + financial transaction identifier
```

Không đổi business intent hoặc key ở mỗi retry nếu mục tiêu là kiểm tra cùng ý định. Đồng thời, không dùng một key chung cho mọi ý định độc lập trừ ca cố ý kiểm tra xung đột.

Phạm vi uniqueness phải theo hợp đồng. Một provider transaction ID có thể chỉ duy nhất trong một provider và merchant account; khi đối soát, dùng đủ namespace cần thiết thay vì coi chuỗi ID là duy nhất toàn cục.

### 4.2. Nguồn quan sát cần độc lập đủ mức

| Nguồn | Điều có thể chứng minh | Giới hạn |
|---|---|---|
| Nhật ký của load generator | Ý định đã lên lịch, attempt, phản hồi và timeout phía client | Không chứng minh transaction đã rollback |
| Database/snapshot nghiệp vụ | Trạng thái và bản ghi đã commit | Có thể chưa phản ánh hiệu ứng ngoài chưa đối soát |
| Outbox/inbox | Công việc bền vững và sự kiện đã tiếp nhận | Có bản ghi không đồng nghĩa đã có hiệu ứng tiền |
| Fake/sandbox provider hoặc nguồn đối soát phù hợp | Giao dịch bên ngoài và trạng thái của chúng | Cần liên kết đúng intent và mốc chốt |
| Audit quyền | Actor, action, tenant và quyết định liên quan | Không thay thế kiểm tra dữ liệu thực bị tác động |

Trace ID hữu ích để điều tra nhưng không tự là business identity. Request retry thường có trace khác nhau; một ý định vẫn phải được nhận diện xuyên qua chúng.

### 4.3. Tránh để quan sát làm sai phép đo

Kiểm tra toàn bộ database sau từng request có thể tạo thêm tải và contention ngoài kịch bản. Có thể tách kiểm tra online nhẹ khỏi đối soát đầy đủ sau mỗi phase hoặc sau khi chốt dữ liệu.

Lưu chi tiết theo intent ở nơi phù hợp cho đối soát; metric tổng hợp dùng nhãn có số lượng giá trị kiểm soát được. Gắn mọi order ID hoặc user ID vào label metric có thể làm chi phí quan sát tăng mạnh. Việc lấy mẫu trace không được biến thành lấy mẫu cho một bất biến bắt buộc phát hiện mọi khoản tiền trùng.

## 5. Chọn mốc đọc dữ liệu để tránh kết luận sai

### 5.1. Trong tải và sau tải là hai loại kiểm tra

**Trong tải**, kiểm tra các bất biến phải đúng ở mọi trạng thái đã commit, chẳng hạn không có khoản giữ chỗ âm hoặc `F + P` vượt mức được phép trong một snapshot nhất quán.

**Sau tải**, kiểm tra tính đầy đủ, các trạng thái chưa kết thúc và sự khớp giữa ứng dụng với provider sau khi đã xử lý công việc theo mốc chốt. Một intent còn đang xử lý tại thời điểm ngừng phát request không tự là dữ liệu hỏng.

Chấm dứt load generator không đồng nghĩa hệ thống đã yên: queue, worker, retry scheduler, callback và request đang chạy vẫn có thể tiếp tục tạo dữ liệu.

### 5.2. Dùng snapshot nhất quán và phạm vi chốt rõ ràng

Không đọc `F` ở thời điểm trước commit, rồi đọc `P` ở thời điểm sau commit chuyển giữ chỗ sang thành công và cộng hai giá trị tùy ý. Các truy vấn riêng có thể tạo ra tổ hợp chưa từng tồn tại trong một trạng thái hợp lệ.

Với kiểm tra nội bộ, dùng một snapshot có semantics phù hợp của database hoặc nguồn tổng hợp được cập nhật nguyên tử theo thiết kế. Không mặc định hai câu `SELECT` riêng, một read replica đang trễ hoặc mọi isolation level đều cho cùng loại bằng chứng.

Với nhiều hệ thống, thường không có một transaction chung bao trùm mọi nguồn. Cần mốc chốt/watermark hoặc tập intent được theo dõi đến trạng thái đủ để đối soát, cùng thời hạn chờ và quy tắc phân loại còn chưa xác định.

Warm-up cũng phải được tính đúng: công việc tạo ở warm-up có thể hoàn tất trong phase đo. Tách namespace hoặc ghi nguồn gốc từng intent, đồng thời giữ đầy đủ các khoản nền ảnh hưởng hạn mức của tài nguyên đang xét. Lọc bỏ mọi bản ghi ngoài `runId` rồi quên giữ chỗ ban đầu có thể làm oracle tính sai số dư.

## 6. Ví dụ Java: kiểm tra snapshot tài chính nội bộ

### 6.1. Phạm vi mô hình

Đoạn Java 17 trở lên dưới đây minh họa bộ kiểm tra thuần, không truy cập database hoặc provider. Đầu vào phải là snapshot nhất quán, đã kiểm tra schema và có đầy đủ lịch sử liên quan tới các order được chọn, bao gồm số dư nền trước lần chạy.

Hợp đồng cục bộ của ví dụ:

- Một refund intent có một amount/currency cố định.
- `RESERVED` có đúng một giữ chỗ đang hoạt động và chưa có posting hoàn thành.
- `SUCCEEDED` có đúng một **posting nghiệp vụ hoàn tiền** và không còn giữ chỗ hoạt động.
- `FAILED` là thất bại cuối cùng, không có posting và không còn giữ chỗ.
- Đổi trạng thái, giữ chỗ và posting tương ứng được commit nguyên tử trong miền dữ liệu này.
- Một posting liên kết một giao dịch provider qua khóa có đủ namespace.

`Posting` ở đây là ghi nhận một hiệu ứng hoàn tiền trong mô hình giản lược, không phải từng dòng debit/credit của hệ thống kế toán kép. Nếu ứng dụng có các trạng thái hoặc cách ghi sổ khác, cần mô hình tham chiếu tương ứng, không áp nguyên các điều kiện này.

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

public final class LoadIntegrityChecks {
    public enum State { RESERVED, SUCCEEDED, FAILED }

    public record RefundBudget(
            String orderId, String tenantId, String currency, long limitMinor) {}

    public record Refund(
            String id, String orderId, String tenantId, String currency,
            long amountMinor, State state) {}

    // Chỉ chứa các giữ chỗ còn hoạt động ở snapshot đang xét.
    public record Reservation(
            String id, String refundId, String currency, long amountMinor) {}

    public record ProviderKey(
            String provider, String merchantAccount, String transactionId) {}

    public record Posting(
            String id, String refundId, ProviderKey providerKey,
            String currency, long amountMinor) {}

    public static void verify(
            List<RefundBudget> budgets,
            List<Refund> refunds,
            List<Reservation> reservations,
            List<Posting> postings) {

        Map<String, RefundBudget> budgetByOrder =
                indexUnique(budgets, RefundBudget::orderId);
        Map<String, Refund> refundById = indexUnique(refunds, Refund::id);
        indexUnique(reservations, Reservation::id);
        indexUnique(postings, Posting::id);

        for (RefundBudget budget : budgets) {
            check(budget.limitMinor() >= 0, "negative refund budget");
        }
        for (Refund refund : refunds) {
            RefundBudget budget = budgetByOrder.get(refund.orderId());
            check(budget != null, "refund has no known order");
            check(budget.tenantId().equals(refund.tenantId()), "tenant mismatch");
            check(budget.currency().equals(refund.currency()), "currency mismatch");
            check(refund.amountMinor() > 0 && refund.state() != null,
                    "invalid refund intent");
        }

        var heldRefunds = new HashSet<String>();
        var postedRefunds = new HashSet<String>();
        var providerKeys = new HashSet<ProviderKey>();
        var heldByOrder = new HashMap<String, Long>();
        var postedByOrder = new HashMap<String, Long>();

        for (Reservation hold : reservations) {
            Refund refund = refundById.get(hold.refundId());
            check(refund != null, "orphan reservation");
            check(heldRefunds.add(refund.id()), "multiple active reservations");
            check(refund.state() == State.RESERVED, "hold/state mismatch");
            check(hold.currency().equals(refund.currency())
                    && hold.amountMinor() == refund.amountMinor(),
                    "hold/intent amount mismatch");
            heldByOrder.merge(refund.orderId(), hold.amountMinor(),
                    (left, right) -> Math.addExact(left, right));
        }

        for (Posting posting : postings) {
            Refund refund = refundById.get(posting.refundId());
            check(refund != null, "orphan posting");
            check(postedRefunds.add(refund.id()), "multiple postings for one intent");
            check(posting.providerKey() != null
                    && providerKeys.add(posting.providerKey()),
                    "missing or reused provider transaction");
            check(refund.state() == State.SUCCEEDED, "posting/state mismatch");
            check(posting.currency().equals(refund.currency())
                    && posting.amountMinor() == refund.amountMinor(),
                    "posting/intent amount mismatch");
            postedByOrder.merge(refund.orderId(), posting.amountMinor(),
                    (left, right) -> Math.addExact(left, right));
        }

        for (Refund refund : refunds) {
            boolean held = heldRefunds.contains(refund.id());
            boolean posted = postedRefunds.contains(refund.id());
            switch (refund.state()) {
                case RESERVED -> check(held && !posted, "invalid reserved intent");
                case SUCCEEDED -> check(posted && !held, "invalid succeeded intent");
                case FAILED -> check(!held && !posted, "invalid failed intent");
            }
        }

        for (RefundBudget budget : budgets) {
            long held = heldByOrder.getOrDefault(budget.orderId(), 0L);
            long posted = postedByOrder.getOrDefault(budget.orderId(), 0L);
            long used = Math.addExact(held, posted);
            check(used <= budget.limitMinor(),
                    "refund budget exceeded for " + budget.orderId());
        }
    }

    private static <T> Map<String, T> indexUnique(
            List<T> rows, Function<T, String> key) {
        var result = new HashMap<String, T>();
        for (T row : rows) {
            String id = key.apply(row);
            check(id != null && !id.isBlank(), "missing identity");
            check(result.putIfAbsent(id, row) == null, "duplicate identity: " + id);
        }
        return result;
    }

    private static void check(boolean valid, String message) {
        if (!valid) {
            throw new IllegalStateException(message);
        }
    }
}
```

Số tiền là số nguyên theo đơn vị nhỏ nhất đã xác định cho từng currency; ví dụ tiền ở bài học dùng VND scale 0. Chuyển đổi từ API/provider phải theo hợp đồng currency của hệ thống. Các tổng trong mã được tính riêng theo order và currency tương ứng, không cộng trực tiếp các đơn vị tiền khác nhau.

`Math.addExact` làm tràn số trở thành lỗi quan sát được thay vì âm thầm tạo tổng sai. Trong công cụ đối soát thực tế, có thể thu thập nhiều vi phạm cùng lúc và dùng kiểu số phù hợp với quy mô tổng hợp. Ví dụ trên dừng ở lỗi đầu tiên để dễ đọc.

### 6.2. Những trường hợp bộ kiểm tra phải phân biệt

| Snapshot theo hợp đồng cục bộ | Kết quả cần có |
|---|---|
| Budget 100.000, posting 30.000, giữ chỗ 20.000, quan hệ hợp lệ | Qua các kiểm tra nội bộ tương ứng |
| Budget 100.000, posting 30.000, giữ chỗ 80.000 | Vi phạm hạn mức |
| Một intent có hai giữ chỗ hoạt động | Vi phạm cardinality dù tổng tiền vẫn dưới trần |
| `SUCCEEDED` nhưng không có posting | Vi phạm liên kết trạng thái/ghi nhận theo hợp đồng nguyên tử |
| `FAILED` vẫn có giữ chỗ hoạt động | Vi phạm giải phóng giữ chỗ theo mô hình |
| Hai posting dùng lại cùng provider key trong cùng namespace | Ghi nhận trùng giao dịch |
| Reservation hoặc posting trỏ tới intent không tồn tại | Vi phạm quan hệ hoặc snapshot không đủ dữ liệu |

Đây là ví dụ mã học tập, không khẳng định đã được chạy trong một project cụ thể. Bộ nạp snapshot phải xác minh schema, namespace provider và độ đầy đủ của phạm vi dữ liệu trước khi dùng các kết quả để kết luận.

### 6.3. Những điều bộ kiểm tra này chưa chứng minh

Kiểm tra nội bộ không biết chắc provider có tạo một giao dịch ngoài sổ hay không. Nó cũng chưa chứng minh actor có quyền tạo refund, budget lấy đúng chính sách hay amount của mọi record không bị sai đồng loạt.

Cần thêm đối soát bên ngoài và oracle quyền/giá độc lập. Một callback đang trễ có thể làm provider đã thành công trong khi local còn giữ chỗ; tình huống đó cần phân loại đang đối soát, không tự suy rằng local snapshot đã hỏng. Nếu thiết kế nội bộ cũng dùng nhiều bước thay vì transaction nguyên tử cho các record trên, mô hình kiểm tra phải thể hiện các trạng thái trung gian hợp lệ ấy.

## 7. Đối soát từ kế hoạch workload tới hiệu ứng bên ngoài

### 7.1. Theo dấu tính đầy đủ của một ý định

Với phạm vi lần chạy đã chốt, đối chiếu chuỗi:

```text
ý định và oracle từ workload
        ↓
quyết định tiếp nhận / từ chối có thẩm quyền
        ↓
bản ghi nghiệp vụ + công việc bền vững nếu cần
        ↓
giao dịch provider được liên kết theo danh tính
        ↓
trạng thái và ghi nhận tài chính nội bộ sau đối soát
```

Một response xác nhận đã tiếp nhận theo hợp đồng phải dẫn tới tài nguyên hoặc ý định bền vững tương ứng, không phải chỉ tồn tại trong bộ nhớ. Một ý định chưa trả response vẫn có thể đã commit; tìm theo business identity trước khi phân loại là mất.

Các hiệu ứng không khớp workload cần được phân biệt với giao dịch nền hợp lệ hoặc phase khác. Dùng namespace và liên kết đủ rõ để nhận diện hiệu ứng ngoài dự kiến mà không xóa mất lịch sử nền liên quan.

### 7.2. Ma trận sai lệch và cách phân loại

| Quan sát | Cách xử lý khi kiểm tra |
|---|---|
| Client timeout, local và provider đều thành công một lần | Ý định có thể đã thành công; timeout là kết quả attempt |
| Local đang xử lý, provider thành công, callback chưa được xử lý | Chưa kết thúc đối soát; theo dõi tới mốc chốt |
| Local thành công, provider chưa có kết quả đủ tin cậy | Chưa đủ bằng chứng khớp bên ngoài; kiểm tra hợp đồng và nguồn đối soát |
| Một intent có hai giao dịch hoàn thành công ngoài hợp đồng | Vi phạm trùng hiệu ứng, kể cả local chỉ có một posting |
| Provider có khoản hoàn không liên kết được với ý định hợp lệ sau khi chốt đủ dữ liệu | Hiệu ứng mồ côi cần điều tra và có thể là vi phạm |
| Local thất bại cuối cùng, provider thực tế đã hoàn thành công | Sai lệch nghiêm trọng nếu đã xác nhận đủ mốc; kiểm tra giải phóng giữ chỗ và đối soát |
| Amount/currency ở provider khác nội dung đã được duyệt | Vi phạm hợp đồng tài chính |
| Actor bị cấm nhưng có công việc hoặc hiệu ứng được tạo | Vi phạm phân quyền dù các tổng tiền vẫn cân bằng |

Chỉ kết luận vi phạm dựa trên bằng chứng đủ theo hợp đồng. Trạng thái chưa rõ tới hết deadline phải được báo là chưa giải quyết; nó không được biến thành pass chỉ vì chưa quan sát thấy giao dịch trùng.

### 7.3. Không xóa dấu vết trùng khi tổng hợp

Log có thể chứa nhiều lần giao cùng một sự kiện hoặc nhiều lần quan sát cùng giao dịch. Cần chuẩn hóa theo danh tính giao dịch thực, đồng thời kiểm tra xem có nhiều giao dịch thực khác nhau cho cùng intent hay không.

Không dùng `DISTINCT amount` hoặc chỉ lấy giao dịch mới nhất: hai khoản hoàn trái phép có thể cùng amount và currency. Tương tự, chỉ đếm business intent duy nhất ở database sẽ bỏ sót khoản thứ hai đã xảy ra ngoài provider nhưng chưa được ghi local.

Nếu ledger có nhiều dòng cho một hiệu ứng theo thiết kế, đối chiếu theo mô hình bút toán và khóa nghiệp vụ của nó. Không coi mọi cặp dòng bằng nhau là trùng, cũng không gộp hết các dòng trước khi kiểm tra uniqueness và quan hệ.

## 8. Kết hợp tải với lỗi một phần và thay đổi trạng thái

Các profile nên có mục tiêu rõ ràng thay vì chỉ tăng virtual user:

| Profile | Điều kiện tạo ra | Bất biến ưu tiên |
|---|---|---|
| Tăng tải dần | Nhiều công việc đang hoạt động, pool/queue tăng sử dụng | Không mất việc đã chấp nhận, quyền không đổi sai |
| Burst vào tài nguyên nóng | Nhiều ý định cùng tranh hạn mức cuối | Giữ chỗ nguyên tử, không vượt trần |
| Retry sau timeout | Client không biết kết quả attempt trước | Một ý định không sinh thêm hiệu ứng ngoài hợp đồng |
| Provider chậm có kiểm soát | Nhiều giữ chỗ tồn tại lâu hơn | Không giải phóng tiền chỉ vì hết thời gian chờ phía client |
| Worker restart hoặc giao lại message | Công việc có thể bị xử lý nhiều lần | Trạng thái và hiệu ứng vẫn đúng theo business identity |
| Callback trùng/đảo thứ tự | Nhiều đường cập nhật cùng intent | Không ghi trùng và không chuyển trạng thái lùi trái phép |
| Quyền hoặc owner thay đổi | Request/worker gặp dữ liệu quyền mới theo hợp đồng | Không dùng cache hoặc phạm vi cũ ngoài hiệu lực cho phép |

Tiêm lỗi tại điểm đã biết: trước commit, sau commit nhưng trước gửi đi, hoặc sau thành công bên ngoài nhưng trước khi ghi kết quả local. Mỗi điểm chứng minh một đặc tính khác nhau. Lỗi ngẫu nhiên không có dấu mốc thường khó điều tra và có thể không chạm được khoảng trống cần kiểm tra.

Giữ giới hạn thời gian, số tác vụ và khả năng quan sát của fake/adapter test. Nếu hệ thống ngoài trong môi trường test bị quá tải theo cách khác production, nêu giới hạn đó trong kết quả; không suy rộng một đường giả lập chưa phản ánh đúng hợp đồng.

## 9. Đặt tiêu chí kết luận trước khi chạy

### 9.1. Tách ngưỡng hiệu năng và cổng toàn vẹn

| Nhóm tiêu chí | Ví dụ cách đặc tả | Ý nghĩa |
|---|---|---|
| Tải thực đạt | Số ý định/attempt đã thực phát và cơ cấu workload đáp ứng mục tiêu đã chọn | Lần chạy có kiểm tra đúng điều kiện mong muốn không |
| Độ trễ và tài nguyên | Ngưỡng do yêu cầu hệ thống xác định, có nêu endpoint/phase | Hiệu năng dưới workload thực tế |
| Kết quả nghiệp vụ | Tỷ lệ hoặc số ca chấp nhận/từ chối theo kịch bản | Có đủ công việc hợp lệ và ca cạnh tranh để kiểm tra không |
| Vi phạm tài chính | Không có vượt budget, sai amount/currency hoặc trùng hiệu ứng trái hợp đồng | An toàn tài chính trong phạm vi đã đối soát |
| Vi phạm quyền | Không có dữ liệu hoặc hiệu ứng ngoài quyền đã đặc tả | Phân quyền vẫn đúng dưới tải |
| Tính đầy đủ | Ý định đã tiếp nhận có kết quả hoặc trạng thái/công việc hợp lệ theo deadline đã chốt | Không che mất việc hoặc trạng thái treo |
| Chất lượng bằng chứng | Snapshot, dữ liệu provider và liên kết intent đủ cho kiểm tra | Kết luận có dựa trên dữ liệu tin cậy không |

Một khoản hoàn trùng không được hòa vào error rate trung bình rồi được chấp nhận vì vẫn dưới ngưỡng phần trăm. Các bất biến an toàn đã đặc tả phải có tiêu chí riêng; áp lực tải không biến việc vượt quyền hoặc sinh thêm tiền thành kết quả hợp lệ.

Đồng thời, không thể kết luận hệ thống đạt mục tiêu phục vụ chỉ vì nó từ chối tất cả request nên không làm sai tiền. Tính an toàn và khả năng hoàn thành công việc đều phải được báo cáo.

### 9.2. Kết quả chưa xác định là một trạng thái báo cáo riêng

Có thể dùng ba kết luận cho phần toàn vẹn:

- **PASS:** đủ bằng chứng cho phạm vi đã chốt, các bất biến được kiểm tra đều đúng và các điều kiện hoàn tất đạt yêu cầu.
- **FAIL:** đã xác nhận ít nhất một vi phạm theo hợp đồng.
- **INCONCLUSIVE:** chưa có đủ bằng chứng để kết luận, ví dụ còn intent chưa đối soát, snapshot không nhất quán hoặc nguồn provider chưa đủ mốc.

Một số quy trình có thể coi trạng thái chưa giải quyết quá deadline là lỗi hoàn tất hoặc vận hành riêng. Dù dùng nhãn nào, không gộp nó vào PASS cho toàn bộ lần chạy. Hãy báo rõ bất biến nào đã có bằng chứng và phần nào vẫn chưa biết.

Nếu công cụ tạo tải thiếu công suất hoặc fixture làm hầu hết công việc không đủ điều kiện, đó là giới hạn hoặc lỗi thiết kế lần chạy. Sửa điều kiện test và chạy lại trước khi suy ra khả năng chịu tải của ứng dụng.

### 9.3. Ví dụ báo cáo không che mất ý định chưa kết thúc

Các số dưới đây chỉ minh họa cách ghi, không phải kết quả đo thực tế:

```text
legitimate_intents_scheduled = 100
legitimate_intents_started = 96
legitimate_intents_not_started = 4

reconciled_success = 90
definite_business_rejection = 4
unresolved_at_cutoff = 2

total_attempts_for_started_intents = 128
confirmed_integrity_violations = 0
integrity_conclusion = INCONCLUSIVE
```

Ở mức ý định, `90 + 4 + 2 = 96` và `96 + 4 = 100`. Những nhóm kết quả cuối phải loại trừ nhau theo định nghĩa của báo cáo. Không lấy status của attempt cuối làm kết quả intent: một retry bị từ chối sau khi ý định đã thành công không biến ý định ấy thành một ca thất bại nghiệp vụ.

128 attempt không phải 128 giao dịch tài chính. Hai intent chưa rõ có thể chưa được xử lý hoặc đã có hiệu ứng nhưng chưa đủ đối soát; số 0 vi phạm đã xác nhận chưa cho phép kết luận toàn bộ dữ liệu đúng. Bốn intent không bắt đầu còn ảnh hưởng việc lần chạy có đạt tải mục tiêu hay không.

Ca request trái phép nên có thống kê riêng với oracle quyền, số lần thực sự được phát và hiệu ứng quan sát được. Không dùng số lượng response lỗi chung để suy rằng tất cả ca âm đã được kiểm tra đúng ranh giới.

## 10. Quy trình thực hiện một lần chạy có kiểm tra toàn vẹn

### 10.1. Trước khi phát tải

1. Chốt invariants, mô hình trạng thái, phạm vi dữ liệu và tiêu chí kết luận.
2. Ghi phiên bản ứng dụng, schema, policy, cấu hình liên quan và phiên bản generator.
3. Tạo fixture có quan hệ owner/tenant, lịch sử tiền và trạng thái hợp lệ; kiểm tra baseline bằng oracle độc lập.
4. Gán namespace lần chạy và thống nhất định danh intent, attempt, event, delivery, provider transaction.
5. Xác nhận adapter, queue và đích tạo hiệu ứng thuộc môi trường test.
6. Chạy một đối chứng tải nhỏ để xác minh đường được phép, đường bị cấm và khả năng đối soát, không dùng kết quả đó thay cho lần chạy chính.

Nếu baseline đã vi phạm trước khi chạy, cần giải quyết hoặc phân loại rõ dữ liệu lỗi có chủ đích. Không cộng lỗi sẵn có vào kết quả rồi quy cho tải, cũng không âm thầm bỏ qua chúng.

### 10.2. Trong các phase tải

Theo dõi tải thực phát, số ý định, retry, backlog, kết quả nghiệp vụ và các kiểm tra online. Ghi mốc bắt đầu/kết thúc phase để liên kết vi phạm với điều kiện tải.

Khi phát hiện vượt quyền hoặc sai tiền đã xác nhận, lưu bằng chứng trước khi reset hay dọn dữ liệu. Có thể dừng phát thêm các thao tác tạo hiệu ứng theo chính sách của lần chạy và tiếp tục thu thập/đối soát phần đã chấp nhận; quyết định dừng phải giữ được dấu vết nguyên nhân và phạm vi tác động.

Nếu cần giảm hoặc thay đổi tải để điều tra, ghi lại sự thay đổi. Một giai đoạn đã đổi workload không nên được báo như thể vẫn duy trì cùng điều kiện đo ban đầu.

### 10.3. Ngừng phát và xử lý phần còn lại

Sau khi ngừng tạo ý định mới:

- Chờ request đang chạy tới mốc quan sát đã định.
- Theo dõi worker đang xử lý, queue, công việc retry đã lên lịch và callback còn được kỳ vọng.
- Kiểm tra intent đã tiếp nhận nhưng chưa có kết quả hoặc chưa có công việc bền vững phù hợp.
- Dùng deadline cho quá trình hoàn tất và lưu những trạng thái chưa giải quyết khi hết hạn.

Queue đang rỗng chưa chứng minh hệ thống đã yên: worker có thể đang gọi provider, retry có thể chưa tới lịch và callback chưa đến. Điều kiện chốt phải gắn với những nguồn công việc thực sự tồn tại trong kiến trúc.

### 10.4. Chốt bằng chứng và đối soát

Lấy snapshot theo semantics đã chọn, thu kết quả provider tới mốc đủ tin cậy và liên kết với workload. Kiểm tra tối thiểu:

1. Tính đầy đủ và uniqueness của định danh trong từng namespace.
2. Quan hệ order, tenant, actor, intent, giữ chỗ, posting và provider.
3. Amount, currency, phiên bản giá/chính sách và quyền cần thiết.
4. Trạng thái cuối hoặc trạng thái trung gian còn hợp lệ theo deadline.
5. Tổng tiền/quota và các cardinality đã đặc tả.
6. Ý định thiếu, hiệu ứng không có nguồn hợp lệ, công việc mất hoặc lặp trái phép.

Sau đó báo riêng hiệu năng, tính đúng nghiệp vụ, vi phạm toàn vẹn và phần chưa kết luận. Chỉ dọn dữ liệu khi đã giữ đủ artifact cần cho điều tra theo quy trình của môi trường test.

## 11. Các thiết kế kiểm tra dễ tạo cảm giác an toàn sai

| Thiết kế yếu | Điều có thể bị bỏ lọt | Cách cải thiện |
|---|---|---|
| Chỉ dùng latency và tỷ lệ `2xx` | Sai tiền, mất công việc hoặc vượt quyền vẫn có response đẹp | Thêm oracle dữ liệu và hiệu ứng |
| Mỗi virtual user dùng tài nguyên riêng | Không tạo race ở hạn mức chung | Có nhóm tài nguyên nóng với nhiều ý định độc lập |
| Mỗi retry tạo key mới | Test tạo ý định mới thay vì retry cùng ý định | Giữ business identity/key theo hợp đồng |
| Mọi request dùng cùng một key | Deduplication làm giảm mạnh số nghiệp vụ thực | Phân biệt ý định mới với attempt lặp |
| Timeout được tính ngay là thất bại không hiệu ứng | Bỏ sót commit hoặc giao dịch đã xảy ra | Đối soát intent trước khi phân loại cuối |
| Chỉ kiểm tra tổng cuối cùng | Hai lỗi bù trừ hoặc giao dịch trùng bị che | Kiểm tra từng intent, quan hệ và cardinality |
| Cộng trực tiếp kết quả từ nhiều thời điểm đọc | Báo vi phạm từ snapshot chưa từng tồn tại | Dùng mốc đọc và semantics nhất quán |
| Chỉ lọc bản ghi có `runId` | Bỏ lịch sử nền ảnh hưởng số dư/hạn mức | Giữ phạm vi quan hệ và số dư nền cần thiết |
| Dừng generator rồi chốt ngay | Công việc và callback vẫn đang chạy | Có phase hoàn tất, watermark và deadline |
| Dùng `DISTINCT amount` để gộp dữ liệu | Hai giao dịch trùng cùng số tiền bị biến thành một | Đối soát theo danh tính giao dịch có namespace |
| Bỏ qua trạng thái chưa rõ khi hết thời gian chờ | Biến thiếu bằng chứng thành pass | Báo unresolved và kết luận phù hợp |
| Kiểm tra trên mock chỉ trả thành công | Không có retry, lỗi một phần hoặc tranh chấp thực | Fake có trạng thái và integration test ở ranh giới cần thiết |

### 11.1. Dùng lỗi giả định để đánh giá sức mạnh của oracle

Hãy hỏi bộ kiểm tra có phát hiện được nếu hệ thống:

- Đọc số dư trước rồi giữ chỗ sau bằng cập nhật không được bảo vệ.
- Ghi hai khoản hoàn provider cho một ý định nhưng local chỉ lưu một khoản.
- Mất outbox sau khi đã trả xác nhận tiếp nhận.
- Giải phóng giữ chỗ khi client timeout dù provider chưa có kết quả cuối cùng.
- Đếm cả giữ chỗ và posting sau chuyển thành công.
- Dùng membership hoặc quyết định cache của tenant khác.
- Tính lại giao dịch cũ bằng chính sách mới rồi vẫn giữ mọi thành phần nội bộ khớp nhau.

Mỗi lỗi trên cần một loại bằng chứng khác nhau. Bộ kiểm tra tổng tiền nội bộ không thay được quan sát provider; đối soát provider không thay được oracle quyền và phiên bản giá.

### 11.2. Rút lỗi dưới tải thành hồi quy có thể tái hiện

Khi phát hiện sai lệch, giữ run ID, workload seed, phiên bản, clock, các intent liên quan, mốc tiêm lỗi và lịch sự kiện đủ để điều tra. Seed dữ liệu không tái tạo được mọi lịch chạy thread hoặc thứ tự message; cần lưu các điểm điều phối có ý nghĩa.

Sau khi hiểu nguyên nhân, dựng một integration test nhỏ tái hiện đúng tranh chấp hoặc ranh giới lỗi. Giữ lần chạy tải làm bằng chứng bổ sung về điều kiện vận hành; dùng test nhỏ để hồi quy nhanh. Không nhất thiết phải chạy lại một workload khổng lồ để xác nhận mọi sửa đổi cục bộ nếu đã có kiểm tra phù hợp và không còn nghi vấn mới.

## 12. Bài tập áp dụng và tiêu chí hoàn thành

Thiết kế một lần chạy tải cho hệ thống hoàn tiền theo mô hình của bài:

1. Tạo baseline có `R = 100.000`, `F = 30.000`, `P = 20.000` và lưu expected phần còn lại là 50.000 VND.
2. Lập workload gồm ý định độc lập, hai ý định cùng tranh phần còn lại, retry cùng ý định và actor không có quyền.
3. Định nghĩa các namespace và cách liên kết intent, attempt, event, outbox, posting và provider transaction.
4. Viết các kiểm tra nội bộ về quan hệ, state, amount/currency, cardinality và `F + P <= R`.
5. Thêm oracle độc lập về quyền và số tiền được duyệt để phát hiện dữ liệu nội bộ cùng sai một cách nhất quán.
6. Tiêm ít nhất một timeout sau thành công bên ngoài nhưng trước phản hồi hoặc ghi kết quả local; kiểm tra không tạo hiệu ứng trùng.
7. Giao lại một callback và gửi một sự kiện cũ sau sự kiện mới; kiểm tra ghi nhận và chuyển trạng thái.
8. Chọn cách chốt snapshot, phase hoàn tất và deadline; mô tả xử lý các intent chưa đối soát.
9. Báo tải lên lịch, tải thực phát, số attempt và kết quả theo intent bằng các nhóm loại trừ nhau.
10. Tạo một lỗi giả định làm sai tiền hoặc mất công việc; xác minh oracle có bằng chứng phát hiện đúng loại sai lệch đó.
11. Lập báo cáo tách hiệu năng, kết quả nghiệp vụ, vi phạm toàn vẹn và phần chưa kết luận.
12. Rút một tình huống lỗi thành test hồi quy nhỏ có thể điều phối, dùng dữ liệu tổng hợp.

Hoàn thành khi có bằng chứng cho cả **workload thực sự đã diễn ra**, **bất biến được giữ trong dữ liệu đã chốt** và **hiệu ứng bên ngoài khớp ý định được phép**. Một lần chạy không phát hiện vi phạm nhưng thiếu khả năng đối soát phải nêu giới hạn đó rõ ràng.

Kiểm tra toàn vẹn biến kiểm thử tải thành phép đánh giá khả năng xử lý công việc đúng quy tắc dưới áp lực. Kết hợp định danh nghiệp vụ, snapshot nhất quán, transaction, idempotency và đối soát độc lập giúp phát hiện những sai lệch mà độ trễ hay tỷ lệ phản hồi thành công không thể hiện được.
