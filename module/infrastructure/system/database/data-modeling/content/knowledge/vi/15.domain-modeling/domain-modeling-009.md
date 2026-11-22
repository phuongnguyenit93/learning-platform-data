# Tránh mô hình chỉ có getter, setter khi quy tắc nghiệp vụ cần được bảo vệ

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận ra **mô hình miền thiếu hành vi** (*anemic domain model*) và phân biệt nó với DTO, bản ghi đọc, entity lưu trữ hoặc CRUD thực sự đơn giản.
- Chuyển các setter tùy ý thành **thao tác có ý nghĩa nghiệp vụ** cùng điều kiện trước, điều kiện sau và lỗi rõ ràng.
- Đặt **bất biến** (*invariant*) tại aggregate root, value object, domain service hoặc constraint cơ sở dữ liệu theo đúng phạm vi trách nhiệm.
- Đóng đường ghi trực tiếp vào entity con và trạng thái nội bộ, nhưng vẫn hỗ trợ truy vấn, ánh xạ persistence và kiểm thử.
- Kết hợp hành vi miền với transaction, kiểm tra phiên bản, constraint và kiểm soát quyền để bảo vệ trạng thái trong môi trường nhiều request đồng thời.
- Đánh giá khi nào mô hình giàu hành vi có lợi, khi nào một transaction script hoặc mô hình dữ liệu đơn giản là lựa chọn phù hợp.

Trong **DATABASE_DATA_MODELING**, yêu cầu nghiệp vụ cần được chuyển thành thực thể, quan hệ, ràng buộc, khóa và lược đồ có thể kiểm chứng. Nếu chỉ tạo lớp với các trường và getter/setter, một hệ thống có thể **lưu được dữ liệu** nhưng không bảo vệ được ý nghĩa của dữ liệu. Vấn đề không nằm ở cú pháp getter hay setter; vấn đề là **ai có thể đặt đối tượng vào trạng thái sai, và có cơ chế nào ngăn điều đó trước khi commit hay không**.

## 1. Mô hình chỉ có getter, setter có thể hỏng như thế nào?

Giả sử hệ thống quản lý **yêu cầu mua sắm nội bộ**. Một nhân viên tạo PurchaseRequest gồm các dòng sản phẩm, nộp để phê duyệt, rồi người đủ thẩm quyền quyết định duyệt hoặc từ chối.

Những quy tắc nghiệp vụ được xác nhận:

- Chỉ yêu cầu ở trạng thái **DRAFT** được thêm, xóa hoặc sửa dòng hàng.
- Dòng hàng phải có số lượng dương và đơn giá VND dương.
- Không được **SUBMIT** một yêu cầu không có dòng hàng.
- Chỉ yêu cầu đã **SUBMITTED** mới được **APPROVE**.
- Người tạo yêu cầu không được tự duyệt yêu cầu của mình.
- Khi đã duyệt, nội dung chi phí phải được giữ nguyên; nếu cần điều chỉnh thì thực hiện quy trình khác.
- Tổng chi phí bằng tổng thành tiền các dòng, không được để người dùng tự ghi một con số không khớp.

Một lớp theo kiểu chỉ chứa dữ liệu:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

// Phản ví dụ: lớp không bảo vệ bất biến.
class PurchaseRequestData {
    private UUID id;
    private String status;
    private long totalVnd;
    private List<PurchaseLineData> lines = new ArrayList<>();

    public void setStatus(String status) { this.status = status; }
    public void setTotalVnd(long totalVnd) { this.totalVnd = totalVnd; }
    public List<PurchaseLineData> getLines() { return lines; }

    // Các getter/setter khác...
}

class PurchaseLineData {
    public UUID productId;
    public int quantity;
    public long unitPriceVnd;
}
~~~

Một đoạn mã ở bất cứ đâu có thể gọi setStatus("APPROVED") trên yêu cầu chưa nộp; gọi setTotalVnd(1) dù dòng hàng cộng lại thành nhiều triệu; hoặc lấy getLines().clear() để xóa hết dòng sau khi phê duyệt. Dù controller có kiểm tra trước khi gọi setter, một luồng batch, API mới hoặc tiến trình nhập dữ liệu vẫn có thể bỏ qua kiểm tra đó.

**Lỗi không phải vì có getter.** Một getter chỉ đọc dữ liệu có thể an toàn; một setter cục bộ có kiểm tra cũng không tự động sai. Lỗi thiết kế ở đây là **quyền sửa trạng thái quá rộng và không có nơi duy nhất chịu trách nhiệm bảo vệ quy tắc**.

### Dấu hiệu của anemic domain model

| Dấu hiệu | Rủi ro | Câu hỏi cần đặt ra |
| --- | --- | --- |
| Entity chỉ có trường và setter công khai | Mọi caller có thể tạo trạng thái không hợp lệ | Thao tác nghiệp vụ nào mới thực sự được phép? |
| Service chỉ gọi nhiều setter theo thứ tự | Quy tắc rải rác, dễ quên và dễ chạy dở | Những thay đổi nào phải thành một đơn vị? |
| Tổng tiền, số dư hoặc trạng thái suy ra được lưu tùy ý | Dữ liệu mâu thuẫn nhau | Có nên tính lại thay vì cho đặt trực tiếp? |
| Trả về List/Map nội bộ có thể sửa | Caller đổi entity con mà root không biết | Có thể trả immutable view/snapshot không? |
| Controller quyết định mọi trạng thái | Batch, listener hoặc import bỏ qua luật | Bất biến thuộc component nào? |
| Chỉ kiểm tra hợp lệ ở giao diện | Request trực tiếp hoặc đồng thời phá quy tắc | Database và domain có lớp bảo vệ nào? |

## 2. Phân biệt cấu trúc dữ liệu với mô hình nghiệp vụ

Không nên kết luận tất cả lớp chứa dữ liệu đều cần đổi thành object có nhiều hành vi. Cùng một hệ thống có thể có các mô hình với trách nhiệm khác nhau:

| Loại đối tượng | Vai trò | Getter/setter có thể phù hợp? |
| --- | --- | --- |
| **Request DTO** | Nhận dữ liệu từ HTTP/API | Có, nhưng dữ liệu chưa được tin cậy; phải validate và chuyển thành command |
| **Response DTO** | Xuất thông tin cho client | Getter hoặc immutable record là bình thường |
| **Read model / projection** | Phục vụ màn hình, thống kê, tìm kiếm | Thường chủ yếu là dữ liệu, không sở hữu quy tắc ghi |
| **Persistence row / ORM mapping** | Ánh xạ cột và quan hệ lưu trữ | Có thể có accessor do framework yêu cầu; cần giới hạn đường ghi |
| **Value object** | Diễn đạt một giá trị có ràng buộc | Thường bất biến, kiểm tra ngay khi khởi tạo |
| **Entity / aggregate root** | Sở hữu danh tính, vòng đời và bất biến | Nên có thao tác nghiệp vụ khi tồn tại quy tắc cần bảo vệ |
| **Domain service** | Diễn đạt quy tắc miền không thuộc tự nhiên một entity | Chứa hành vi nghiệp vụ, không chỉ CRUD |

Ví dụ một response DTO có thể chứa {requestId, status, totalVnd, lines}; việc nó có getter hoàn toàn không gây vấn đề vì DTO **không phải nguồn có thẩm quyền để chuyển trạng thái yêu cầu**.

Ngược lại, nếu PurchaseRequest là aggregate root chịu trách nhiệm quy tắc nộp/duyệt, cho caller thay trạng thái bằng một setter công khai là trao quyền viết tắt qua ranh giới nghiệp vụ.

## 3. Xác định bất biến trước khi chọn phương thức

**Bất biến** là điều kiện phải đúng tại mọi trạng thái hợp lệ mà mô hình cam kết duy trì. Hãy viết bất biến dưới dạng có thể kiểm tra, sau đó xác định **điểm sở hữu**.

| Bất biến | Phạm vi kiểm tra | Nơi chịu trách nhiệm |
| --- | --- | --- |
| quantity > 0 và unitPriceVnd > 0 | Một dòng hàng | PurchaseLine value object/entity |
| lineId là duy nhất trong yêu cầu | Một PurchaseRequest | Aggregate root |
| Chỉ DRAFT được sửa dòng | Trạng thái và dòng hàng | Aggregate root |
| SUBMITTED phải có ít nhất một dòng | Tập dòng và trạng thái | Aggregate root, giao thức ghi DB |
| APPROVED có người duyệt khác người yêu cầu | Trạng thái và hai danh tính | Aggregate root, kiểm tra quyền ở application |
| Tổng tiền bằng tổng quantity × unitPrice | Toàn bộ dòng | Tính từ dòng trong root; nếu lưu cache phải cập nhật nguyên tử |
| Tổng ngân sách nhiều yêu cầu không vượt hạn mức | Nhiều PurchaseRequest và nguồn ngân sách | Budget aggregate/cơ chế cấp quyền có thẩm quyền |

Không đưa **toàn bộ ngân sách, hồ sơ nhân viên và nhà cung cấp** vào PurchaseRequest chỉ để có thể gọi getter của chúng. Những đối tượng đó có thể là aggregate khác. PurchaseRequest giữ định danh và bằng chứng/phiên bản cần thiết; quyền duyệt và ngân sách được phối hợp qua các nguồn có thẩm quyền.

### Command thay cho thay cột tùy ý

| Command nghiệp vụ | Điều kiện trước | Điều kiện sau khi thành công |
| --- | --- | --- |
| AddLine | DRAFT; lineId mới; productId hợp lệ; số lượng/đơn giá dương | Có thêm dòng; tổng tính từ dòng cập nhật |
| ChangeQuantity | DRAFT; dòng tồn tại; số lượng mới dương | Dòng được thay thế bằng giá trị hợp lệ |
| RemoveLine | DRAFT; dòng tồn tại | Dòng bị xóa; DRAFT có thể tạm rỗng |
| SubmitRequest | DRAFT; có dòng; phép tính tổng hợp lệ | Trạng thái chuyển SUBMITTED |
| ApproveRequest | SUBMITTED; actor khác requester; actor đã được kiểm quyền | Trạng thái chuyển APPROVED, lưu approverId |
| RejectRequest | SUBMITTED; actor có quyền; có lý do | Trạng thái chuyển REJECTED |
| CancelRequest | DRAFT hoặc SUBMITTED; actor có quyền | Trạng thái chuyển CANCELLED |

Ở đây, một thao tác **AddLine** có thể làm nhiều trường thay đổi; một thao tác **ApproveRequest** có thể ghi trạng thái, người duyệt, thời gian và lịch sử phê duyệt. Các cập nhật này phải được xem là **một quyết định nghiệp vụ**, không phải các setter độc lập.

## 4. Thiết kế aggregate root với API mang ý nghĩa miền

Một sơ đồ trách nhiệm:

~~~mermaid
flowchart LR
    HTTP["HTTP request / UI"] --> DTO["Request DTO"]
    DTO --> APP["Application service"]
    APP --> AUTH["Kiểm quyền và kiểm tra phạm vi"]
    APP --> ROOT["PurchaseRequest aggregate root"]
    ROOT -->|"điều phối thay đổi"| LINE["PurchaseLine"]
    ROOT --> REPO["PurchaseRequestRepository"]
    REPO --> DB[("DB transaction")]
    APP -.->|"budgetId / approval evidence"| EXT["Aggregate hoặc service khác"]
~~~

Application service chịu trách nhiệm điều phối use case, kiểm quyền, nạp/lưu aggregate, xử lý transaction và giao tiếp hệ thống ngoài. Aggregate root chịu trách nhiệm **quyết định trạng thái nội bộ sau command có hợp lệ không**. Value object chịu trách nhiệm tính hợp lệ của chính giá trị.

Thiết kế này không có nghĩa application service phải hoàn toàn không chứa logic: nó vẫn phải kiểm quyền, điều phối giao dịch và thực hiện các quy tắc về quy trình liên aggregate. Nhưng nó không nên lặp lại điều kiện "chỉ DRAFT được sửa dòng" ở năm controller khác nhau.

### Đường đọc và đường ghi khác nhau

Cho phép đọc trạng thái, ID, tổng tiền hoặc danh sách dòng bất biến thường hữu ích. Điều cần tránh là caller có thể sửa **trực tiếp bộ nhớ nội bộ** rồi phá bất biến mà root không biết.

Trong Java có thể dùng:

- field private và phương thức có tên nghiệp vụ;
- record/value object bất biến cho thành viên khi phù hợp;
- List.copyOf hoặc Map.copyOf để trả collection không sửa được;
- constructor/factory xác nhận đầu vào;
- kiểu ID riêng khi cần giảm nhầm lẫn;
- repository có đường phục hồi trạng thái được kiểm soát, không công khai tùy tiện.

**Đóng gói không thay thế kiểm tra quyền.** Người dùng biết requestId không có nghĩa được phép duyệt; application service phải lấy actor từ ngữ cảnh bảo mật đã xác thực, không tin một approverId do client tùy ý cung cấp.

## 5. Ví dụ Java 17: hành vi thay vì getter/setter

Ví dụ sau dùng **đơn vị đồng VND nguyên** với kiểu long; trong hệ thống đa tiền tệ cần value object Money với currency, thang đo và quy tắc làm tròn phù hợp. Nó chỉ mô hình hóa bất biến nội bộ yêu cầu mua sắm, chưa quản lý hạn mức ngân sách chung.

~~~java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;

enum PurchaseStatus {
    DRAFT, SUBMITTED, APPROVED, REJECTED, CANCELLED
}

record PurchaseLine(
        UUID lineId, UUID productId, int quantity, long unitPriceVnd) {
    PurchaseLine {
        Objects.requireNonNull(lineId);
        Objects.requireNonNull(productId);
        if (quantity <= 0) throw new IllegalArgumentException("quantity");
        if (unitPriceVnd <= 0) throw new IllegalArgumentException("unit price");
    }

    long lineTotalVnd() {
        return Math.multiplyExact((long) quantity, unitPriceVnd);
    }

    PurchaseLine withQuantity(int newQuantity) {
        return new PurchaseLine(lineId, productId, newQuantity, unitPriceVnd);
    }
}

final class PurchaseRequest {
    private final UUID requestId;
    private final UUID requesterId;
    private final Map<UUID, PurchaseLine> lines = new LinkedHashMap<>();
    private PurchaseStatus status = PurchaseStatus.DRAFT;
    private UUID approvedBy;
    private String rejectionReason;
    private long version;

    PurchaseRequest(UUID requestId, UUID requesterId) {
        this.requestId = Objects.requireNonNull(requestId);
        this.requesterId = Objects.requireNonNull(requesterId);
    }

    void addLine(UUID lineId, UUID productId, int qty, long priceVnd) {
        requireDraft();
        PurchaseLine line = new PurchaseLine(lineId, productId, qty, priceVnd);
        if (lines.containsKey(lineId)) {
            throw new IllegalArgumentException("Duplicate line ID");
        }
        // Đảm bảo tổng mới không vượt giới hạn long trước khi ghi.
        Math.addExact(totalVnd(), line.lineTotalVnd());
        lines.put(lineId, line);
        version++;
    }

    void changeQuantity(UUID lineId, int newQuantity) {
        requireDraft();
        PurchaseLine current = lines.get(lineId);
        if (current == null) throw new IllegalArgumentException("Unknown line");
        PurchaseLine updated = current.withQuantity(newQuantity);
        // Kiểm tra tổng trước khi cập nhật trạng thái.
        long nextTotal = 0;
        for (PurchaseLine line : lines.values()) {
            nextTotal = Math.addExact(nextTotal,
                line.lineId().equals(lineId)
                    ? updated.lineTotalVnd() : line.lineTotalVnd());
        }
        lines.put(lineId, updated);
        version++;
    }

    void removeLine(UUID lineId) {
        requireDraft();
        if (lines.remove(lineId) == null) {
            throw new IllegalArgumentException("Unknown line");
        }
        version++;
    }

    void submit() {
        requireDraft();
        if (lines.isEmpty()) throw new IllegalStateException("Empty request");
        totalVnd(); // kiểm tra tổng, bao gồm tràn số nếu có
        status = PurchaseStatus.SUBMITTED;
        version++;
    }

    void approve(UUID authenticatedApproverId) {
        requireSubmitted();
        Objects.requireNonNull(authenticatedApproverId);
        if (requesterId.equals(authenticatedApproverId)) {
            throw new IllegalStateException("Self approval forbidden");
        }
        approvedBy = authenticatedApproverId;
        status = PurchaseStatus.APPROVED;
        version++;
    }

    void reject(String reason) {
        requireSubmitted();
        if (reason == null || reason.isBlank()) {
            throw new IllegalArgumentException("Rejection reason required");
        }
        rejectionReason = reason.strip();
        status = PurchaseStatus.REJECTED;
        version++;
    }

    void cancel() {
        if (status != PurchaseStatus.DRAFT
                && status != PurchaseStatus.SUBMITTED) {
            throw new IllegalStateException("Cannot cancel in " + status);
        }
        status = PurchaseStatus.CANCELLED;
        version++;
    }

    long totalVnd() {
        long total = 0;
        for (PurchaseLine line : lines.values()) {
            total = Math.addExact(total, line.lineTotalVnd());
        }
        return total;
    }

    List<PurchaseLine> linesView() {
        return List.copyOf(lines.values()); // các record là bất biến
    }
    UUID id() { return requestId; }
    UUID requesterId() { return requesterId; }
    PurchaseStatus status() { return status; }
    UUID approvedBy() { return approvedBy; }
    long version() { return version; }

    private void requireDraft() {
        if (status != PurchaseStatus.DRAFT) {
            throw new IllegalStateException("Request is not editable");
        }
    }
    private void requireSubmitted() {
        if (status != PurchaseStatus.SUBMITTED) {
            throw new IllegalStateException("Request is not submitted");
        }
    }
}
~~~

Ở đây **PurchaseLine** là bản ghi bất biến có lineId; root thay một bản ghi khi số lượng đổi. Dòng hàng vẫn có **danh tính trong nghiệp vụ** dù object Java chứa nó được thay mới. Tính bất biến của record và List.copyOf ngăn caller đổi trạng thái dòng thông qua collection trả về.

**totalVnd() được tính từ dòng**, không phải setter trên một trường total để client tự đặt. Math.multiplyExact/Math.addExact giúp phát hiện phép toán vượt miền giá trị của long; với giá trị quá lớn cần lựa chọn kiểu số phù hợp thay vì bỏ kiểm tra. Việc tăng version trong bộ nhớ chỉ là đánh dấu phiên bản miền; **repository vẫn phải kiểm tra phiên bản ban đầu khi ghi**.

Ví dụ chưa có trạng thái hồi phục từ database, sự kiện miền, thông tin về ngày duyệt hoặc quyền hạn mức. Repository phải cung cấp cách **rehydrate** đối tượng từ dữ liệu đã lưu mà không gọi các command như addLine/approve để tái diễn hành vi nghiệp vụ và phát tác động phụ. Sau khi nạp, root cần có trạng thái, dòng hàng và version chính xác; cách hiện thực tùy framework nhưng không nên mở các setter công khai cho mọi caller.

Nếu hệ thống cần tính thuế, nhiều tiền tệ, chiết khấu hoặc định mức mua hàng, nên đưa chúng thành value object/quy tắc rõ ràng và xác định đúng nguồn sở hữu; đừng dồn mọi chính sách liên hệ thống vào một lớp PurchaseRequest quá lớn.

## 6. Đừng nhầm kiểm tra dữ liệu đầu vào với bất biến nghiệp vụ

Có ba lớp kiểm soát bổ sung cho nhau:

| Lớp | Kiểm tra phù hợp | Ví dụ |
| --- | --- | --- |
| **API / input validation** | Kiểu dữ liệu, định dạng, field bắt buộc, giới hạn kích thước request | quantity là số nguyên, lineId có cú pháp UUID |
| **Domain model** | Điều kiện nghiệp vụ phụ thuộc trạng thái, quan hệ giữa các trường, chuyển trạng thái hợp lệ | Chỉ DRAFT được sửa; không tự duyệt; SUBMITTED phải có dòng |
| **Database** | Khóa, UNIQUE, CHECK, FK, transaction và kiểm tra đồng thời | quantity > 0, lineId duy nhất, optimistic version |

Không có lớp nào thay thế trọn vẹn hai lớp còn lại:

- API validation không bảo vệ batch job hoặc command nội bộ không qua HTTP.
- Domain model trong bộ nhớ không tự bảo vệ hai tiến trình cùng ghi vào một hàng.
- CHECK constraint của SQL không thuận tiện để diễn đạt mọi chính sách như quyền duyệt dựa trên cấp bậc hay trạng thái ngân sách ở hệ thống khác.

Một quy tắc có thể xuất hiện ở nhiều lớp vì **mục đích bảo vệ khác nhau**. Ví dụ quantity > 0 được kiểm ở constructor để phát hiện lỗi sớm và ở database CHECK để chặn dữ liệu sai từ bất kỳ đường ghi nào. Điều đó không phải trùng lặp vô ích khi trách nhiệm mỗi lớp được xác định rõ.

## 7. Đặt hành vi tại entity, value object hay domain service?

Không phải quy tắc nào cũng thuộc về aggregate root:

**Value object:** Money, DateRange, Quantity. Chúng bảo vệ tính hợp lệ của chính giá trị. Ví dụ một DateRange không cho phép end trước start; một Money không tự cộng hai loại tiền không tương thích.

**Entity con:** PurchaseLine có thể có hành vi thay số lượng được kiểm soát, nhưng root PurchaseRequest mới quyết định **lúc nào** được thay vì điều kiện phụ thuộc trạng thái DRAFT. Bên ngoài không được lấy entity con rồi sửa trực tiếp bỏ qua root.

**Aggregate root:** Điều kiện liên nhiều dòng hoặc liên trạng thái yêu cầu, như "chỉ DRAFT sửa dòng" hay "không tự duyệt". Root cũng là cửa vào để repository ghi một đơn vị nhất quán.

**Domain service:** Dùng khi một quy tắc thuần nghiệp vụ không thuộc tự nhiên một entity/value object đơn lẻ. Chẳng hạn đánh giá chính sách phân quyền mua theo ngạch, hạn mức và loại hàng có thể là một policy/domain service nhận đầu vào cần thiết và trả về một quyết định; root nhận một bằng chứng/quyết định hợp lệ nếu quy trình yêu cầu.

**Application service:** Nạp PurchaseRequest, xác thực actor, hỏi policy/service khác, gọi hành vi miền, điều phối transaction và lưu repository. Nó không nên trở thành một "god service" chứa mọi câu lệnh if về trạng thái nội bộ.

Một sơ đồ phân chia:

~~~mermaid
sequenceDiagram
    participant U as User/API
    participant A as Application Service
    participant P as Approval Policy
    participant R as PurchaseRequest root
    participant D as Repository/DB

    U->>A: ApproveRequest(requestId)
    A->>A: Xác thực actor, tenant, quyền truy cập
    A->>D: Load request + version
    D-->>A: Aggregate ở SUBMITTED
    A->>P: Check approval scope, threshold, budget policy
    P-->>A: Approved for attempt / rejected
    A->>R: approve(authenticatedApproverId)
    R->>R: Chặn tự duyệt, kiểm trạng thái
    A->>D: Save with expectedVersion + transaction
    D-->>A: Commit hoặc version conflict
    A-->>U: Kết quả command
~~~

Nếu chính sách phải được kiểm tra **ngay thời điểm commit**, một câu trả lời từ policy service có thể đã cũ. Cần thiết kế token phê duyệt có hiệu lực, khóa/phiên bản tại nguồn có thẩm quyền hoặc giao thức xác nhận phù hợp. Không nghĩ rằng việc gọi một method giàu hành vi tự giải quyết vấn đề dữ liệu bên ngoài thay đổi đồng thời.

## 8. Ánh xạ mô hình giàu hành vi sang PostgreSQL

Một aggregate có thể trải qua **nhiều bảng**. Ví dụ dưới đây có bảng request và các dòng; chúng vẫn là một đơn vị nhất quán khi đường ghi được thiết kế đúng.

~~~sql
CREATE SCHEMA IF NOT EXISTS procurement;

CREATE TABLE procurement.purchase_request (
    tenant_id UUID NOT NULL,
    request_id UUID NOT NULL,
    requester_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN (
            'DRAFT', 'SUBMITTED', 'APPROVED', 'REJECTED', 'CANCELLED'
        )),
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    approved_by UUID,
    approved_at TIMESTAMPTZ,
    rejection_reason TEXT,
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, request_id),
    CONSTRAINT approval_fields_match_status
        CHECK (
            (status = 'APPROVED') =
            (approved_by IS NOT NULL AND approved_at IS NOT NULL)
        ),
    CONSTRAINT cannot_self_approve
        CHECK (approved_by IS NULL OR approved_by <> requester_id),
    CONSTRAINT rejection_reason_required
        CHECK (
            status <> 'REJECTED' OR
            (rejection_reason IS NOT NULL AND length(trim(rejection_reason)) > 0)
        )
);

CREATE TABLE procurement.purchase_line (
    tenant_id UUID NOT NULL,
    request_id UUID NOT NULL,
    line_id UUID NOT NULL,
    product_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL CHECK (unit_price_vnd > 0),
    PRIMARY KEY (tenant_id, request_id, line_id),
    FOREIGN KEY (tenant_id, request_id)
        REFERENCES procurement.purchase_request(tenant_id, request_id)
);

CREATE INDEX purchase_request_pending_approval
    ON procurement.purchase_request(tenant_id, created_at)
    WHERE status = 'SUBMITTED';
~~~

**Đây là lược đồ phục vụ ví dụ.** Giá/tiền tệ có thể cần snapshot, chính sách thuế và trạng thái phê duyệt nhiều cấp trong hệ thống thực; khi đó phải mô hình hóa thêm, không tự mở rộng bằng những setter không kiểm soát.

### Constraint bảo vệ được điều gì?

- **PRIMARY KEY** và **FOREIGN KEY** bảo vệ danh tính và quan hệ dòng thuộc request cùng tenant.
- **CHECK** bảo vệ số lượng, đơn giá dương, và một số quan hệ giữa status với approvedBy/approvedAt.
- **UNIQUE/PK** ngăn hai lineId trùng nhau trong cùng request.
- **Index có điều kiện** hỗ trợ truy vấn danh sách chờ duyệt; không phải ràng buộc chuyển trạng thái.

Chúng **chưa** bảo vệ được yêu cầu "SUBMITTED phải có ít nhất một dòng", "chỉ DRAFT được sửa dòng" hoặc "người dùng có quyền phê duyệt theo cấp bậc". Những quy tắc này cần hành vi miền cùng giao thức ghi và kiểm quyền; khi cần chống cả những đường ghi SQL ngoài ứng dụng, cân nhắc trigger/procedure, quyền DB và kiểm toán phù hợp.

Trong ví dụ, không lưu totalVnd ở request để tránh một nguồn dữ liệu trùng lặp có thể lệch. Khi số dòng hữu hạn, có thể tính tổng từ purchase_line hoặc projection. Nếu cần tổng lưu vật lý cho hiệu năng, phải coi nó là dữ liệu được cập nhật **nguyên tử** cùng các dòng khi chúng đổi.

## 9. Hành vi trong bộ nhớ cần transaction và concurrency control

Giả sử T1 và T2 cùng đọc PurchaseRequest ở DRAFT, version 6:

1. T1 thêm một dòng và lưu request thành version 7.
2. T2 cũng thêm dòng khác dựa trên phiên bản 6.
3. Nếu repository chỉ ghi lại toàn bộ danh sách không kiểm tra version, T2 có thể ghi đè dòng T1 (**lost update**) hoặc hai bên cùng ghi một trạng thái không dự kiến.

Một **optimistic locking protocol** ở root:

~~~sql
BEGIN;

-- Mọi command sửa dòng phải khóa/đổi phiên bản root trước khi sửa bảng con.
UPDATE procurement.purchase_request
SET version = version + 1
WHERE tenant_id = :tenant_id
  AND request_id = :request_id
  AND status = 'DRAFT'
  AND version = :expected_version
RETURNING version;

-- Nếu 0 hàng: ROLLBACK và báo VERSION_CONFLICT hoặc INVALID_STATE.
-- Nếu 1 hàng: INSERT/UPDATE/DELETE purchase_line theo kết quả domain.

UPDATE procurement.purchase_line
SET quantity = :new_quantity
WHERE tenant_id = :tenant_id
  AND request_id = :request_id
  AND line_id = :line_id
  AND :new_quantity > 0;

-- Phải kiểm tra cập nhật đúng 1 hàng; nếu không, ROLLBACK.
COMMIT;
~~~

Đây là một **ví dụ thay số lượng** sau khi domain đã gọi changeQuantity, không phải lệnh được phép chạy trực tiếp từ HTTP. Mọi đường ghi thêm, xóa, sửa dòng phải theo cùng quy trình khóa root trước. Nếu một worker khác UPDATE purchase_line mà không kiểm trạng thái/version của root, quy tắc "SUBMITTED không được sửa dòng" có thể bị phá.

### Giao dịch phê duyệt

Lúc duyệt, status và approver được ghi nguyên tử:

~~~sql
BEGIN;

UPDATE procurement.purchase_request AS p
SET status = 'APPROVED',
    approved_by = :authenticated_approver_id,
    approved_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE p.tenant_id = :tenant_id
  AND p.request_id = :request_id
  AND p.status = 'SUBMITTED'
  AND p.requester_id <> :authenticated_approver_id
  AND p.version = :expected_version
  AND EXISTS (
      SELECT 1 FROM procurement.purchase_line AS l
      WHERE l.tenant_id = p.tenant_id
        AND l.request_id = p.request_id
  )
RETURNING version;

-- Nếu 0 hàng: không coi là phê duyệt thành công, ROLLBACK.
-- Nếu có audit/outbox, ghi cùng transaction trước COMMIT.
COMMIT;
~~~

SQL kiểm tra status và sự tồn tại của dòng, nhưng **EXISTS một mình không đủ** nếu có đường ghi xóa dòng không tuân thủ giao thức khóa root. Khi mọi thao tác sửa dòng đều khóa root trước, yêu cầu không thể bị xóa dòng cuối một cách hợp lệ trong lúc duyệt. Nếu muốn ràng buộc được bảo vệ ngay cả khi có đường SQL trực tiếp, cần bổ sung quyền và cơ chế ở DB.

**Lưu ý về version:** Java ví dụ tăng version trong bộ nhớ mỗi khi thay đổi. Repository cần giữ **originalVersion** khi nạp để đưa vào :expected_version, sau đó lưu đúng phiên bản cuối đã được domain tạo; ở SQL trên một command thay một bước nên version tăng 1. Nếu một use case gọi nhiều hành vi trước commit, không được âm thầm bỏ qua chênh lệch version; thiết kế một giao thức thống nhất cho giá trị phiên bản cuối và các event/audit liên quan.

### Tầng DB và ứng dụng không nên có đường ghi cạnh tranh nhau

Một tổ chức chỉ cho các service ghi qua repository có kiểm quyền; vai trò DB của dashboard chỉ được SELECT. Nếu nhiều dịch vụ tự cập nhật cùng bảng vì tiện dùng chung database, không còn một nơi rõ ràng chịu trách nhiệm bất biến.

Đóng gói trong Java có giá trị lớn nhưng không đủ nếu có script/batch trực tiếp sửa bảng. Đường ghi và quyền truy cập DB là phần của **thiết kế mô hình dữ liệu vật lý**.

## 10. Kiểm thử hành vi thay vì kiểm thử setter

Unit test nên mô tả **luật**, không chỉ kiểm tra set rồi get trả lại giá trị. Ví dụ JUnit 5 cho lớp trên:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.util.UUID;

class PurchaseRequestTest {
    @Test
    void cannotSubmitEmptyRequest() {
        var request = new PurchaseRequest(UUID.randomUUID(), UUID.randomUUID());
        assertThrows(IllegalStateException.class, request::submit);
        assertEquals(PurchaseStatus.DRAFT, request.status());
    }

    @Test
    void cannotEditAfterSubmitting() {
        var request = new PurchaseRequest(UUID.randomUUID(), UUID.randomUUID());
        var lineId = UUID.randomUUID();
        request.addLine(lineId, UUID.randomUUID(), 2, 100_000);
        request.submit();
        assertThrows(IllegalStateException.class,
            () -> request.changeQuantity(lineId, 3));
        assertEquals(200_000, request.totalVnd());
    }

    @Test
    void requesterCannotApproveOwnPurchase() {
        var requester = UUID.randomUUID();
        var request = new PurchaseRequest(UUID.randomUUID(), requester);
        request.addLine(UUID.randomUUID(), UUID.randomUUID(), 1, 250_000);
        request.submit();
        assertThrows(IllegalStateException.class,
            () -> request.approve(requester));
        assertEquals(PurchaseStatus.SUBMITTED, request.status());
    }

    @Test
    void authorizedApproverCanApproveSubmittedRequest() {
        var requester = UUID.randomUUID();
        var approver = UUID.randomUUID();
        var request = new PurchaseRequest(UUID.randomUUID(), requester);
        request.addLine(UUID.randomUUID(), UUID.randomUUID(), 1, 250_000);
        request.submit();
        request.approve(approver); // Giả định service đã kiểm quyền actor.
        assertEquals(PurchaseStatus.APPROVED, request.status());
        assertEquals(approver, request.approvedBy());
    }
}
~~~

Những test này bảo vệ hành vi **trong một tiến trình**. Cần thêm integration test trên PostgreSQL thật cho những vấn đề không thể mô phỏng đầy đủ bằng mock:

| Kịch bản | Điều cần kiểm chứng |
| --- | --- |
| Hai command sửa cùng version | Tối đa một lần lưu phiên bản cũ thành công; lần còn lại báo conflict |
| Submit đồng thời với xóa dòng cuối | Không tồn tại SUBMITTED với danh sách dòng rỗng sau commit |
| Approve cùng lúc với thay dòng | Không có APPROVED bị sửa dòng sau đó |
| Transaction lưu root thành công nhưng ghi audit/outbox thất bại | Rollback toàn bộ |
| Retry command sau khi client mất phản hồi | Không lặp tác động nghiệp vụ; trả kết quả theo requestId/idempotency |
| Một user duyệt request tenant khác | Authorization và tenant scope phải chặn |
| Script cố sửa dòng bỏ qua root | Bị chặn hoặc phát hiện theo chính sách phòng vệ dữ liệu |

**Không chạy test chỉ với bộ nhớ giả lập rồi kết luận tính nhất quán khi có nhiều process.** Những vấn đề khóa, isolation và conflict cần kiểm chứng với engine lưu trữ thực tế.

## 11. Khi nào mô hình giàu hành vi không phải lựa chọn tối ưu?

Tránh một cực đoan khác: ép mọi bảng vào DDD entity phong phú dù không tồn tại quy tắc nghiệp vụ đáng kể.

Một bảng tham chiếu CountryCode hay LanguageCode ít thay đổi, một DTO hiển thị và một read model phân tích thường không cần hàng chục phương thức miền. Một màn hình quản trị có CRUD đơn giản, không có bất biến xuyên trường/phạm vi và được kiểm soát bằng constraint SQL, có thể dùng **transaction script** hoặc application service mỏng mà vẫn rõ ràng.

| Tình huống | Thiết kế thường phù hợp |
| --- | --- |
| Nhiều chuyển trạng thái, bất biến và thành viên phải nhất quán | Aggregate root có hành vi nghiệp vụ |
| Tính toán giá trị nhỏ, bất biến, tái sử dụng | Value object với constructor/method phù hợp |
| Quy tắc liên nhiều nguồn độc lập | Domain/application service + hợp đồng, không nhúng tất cả vào root |
| CRUD đơn giản với CHECK/FK/UNIQUE đủ bảo vệ | Transaction script hoặc mô hình dữ liệu đơn giản |
| Kết quả tìm kiếm và báo cáo | DTO/read model chủ yếu gồm dữ liệu |
| ORM cần setter hoặc constructor không tham số | Cho framework dùng qua cơ chế giới hạn, không biến thành API nghiệp vụ công khai |

Phương pháp đánh giá: **chi phí để không vi phạm luật nằm ở đâu?** Nếu các quy tắc phức tạp đang bị sao chép giữa controller, batch và listener, đưa chúng về mô hình miền có hành vi thường tạo lợi ích rõ. Nếu nghiệp vụ chỉ cần ghi một bản ghi với ràng buộc hàng đơn giản, một lớp có nhiều hành vi giả tạo sẽ tăng chi phí mà không giảm rủi ro.

**Tránh hai cực đoan:** mô hình nghèo chỉ có setter và mô hình giàu quá mức chứa luôn quyền truy cập DB, gửi email, gọi payment gateway, logic báo cáo và mọi quy trình ngoài ngữ cảnh.

## 12. Tương thích với các mô hình lưu trữ khác nhau

Mục tiêu của aggregate không đổi khi chuyển cơ sở dữ liệu, nhưng **cơ chế bảo vệ** có thể đổi:

| Mô hình lưu trữ | Cách bảo vệ bất biến | Bẫy dễ gặp |
| --- | --- | --- |
| **Quan hệ** | Root ghi nhiều bảng trong transaction, CHECK, FK, UNIQUE, version/lock | ORM cho sửa entity con không qua root; transaction thiếu |
| **Document** | Root và thành viên nhúng trong phạm vi ghi nguyên tử phù hợp, conditional update/version | Mặc định nghĩ mọi document/collection đều update nguyên tử cùng nhau |
| **Đồ thị** | Command qua chủ sở hữu; transaction và constraint theo engine | Đi qua edge rồi sửa bất kỳ node liên quan vì "có liên kết" |
| **Phân tích/cột** | Dùng dữ liệu sự kiện/projection để tổng hợp và kiểm tra xu hướng | Lấy báo cáo cập nhật trễ làm nguồn cấp quyền hoặc phê duyệt |

Ví dụ PurchaseRequest có thể lưu lines trong một document nếu kích thước vừa phải và hệ quản trị hỗ trợ cập nhật nguyên tử cần thiết. Nhưng điều đó không cho phép bỏ kiểm tra DRAFT, version hay self-approval. Nếu chọn bảng quan hệ, quan hệ 1-N vẫn có thể nằm trong **một aggregate logic** và được bảo vệ bằng transaction.

**Mô hình đọc không nhất thiết giống mô hình ghi.** Báo cáo chi tiêu có thể JOIN PurchaseRequest với danh mục sản phẩm và người phê duyệt, hoặc xây projection; nhu cầu ghép đọc không phải lý do cho phép PurchaseRequest sửa hồ sơ nhân viên hay sản phẩm.

## 13. Bài tập thực hành: phiếu đổi trả hàng

**Bối cảnh:** Một cửa hàng cho khách yêu cầu trả hàng trong 30 ngày kể từ khi nhận. Mỗi ReturnRequest gồm một hoặc nhiều ReturnLine. Không được nhận số lượng trả vượt quá số lượng đã mua **trừ số đã trả ở các yêu cầu khác**. Khi kiểm hàng đạt, cửa hàng xác nhận hoàn; kết quả thanh toán được xử lý ở hệ thống Payment riêng. Người dùng không được sửa dòng trả sau khi yêu cầu đã được tiếp nhận.

### Câu hỏi

1. Viết phản ví dụ ReturnRequest với setStatus, setLines và setRefundAmount. Nêu ít nhất ba trạng thái sai mà caller có thể tạo.
2. Đề xuất API miền như addReturnLine, submit, acceptInspection, rejectInspection, authorizeRefund. Mỗi command có điều kiện trước/sau nào?
3. Quy tắc "không trả vượt số lượng đã mua sau khi trừ các lần trả trước" thuộc một ReturnRequest hay cần một **nguồn cấp quyền trả** có thẩm quyền cho nhiều yêu cầu? Vì sao?
4. Những dữ liệu nào nên giữ snapshot (giá đã mua, đơn vị tiền, SKU), ID nào tham chiếu sang Order hoặc Payment?
5. Nếu hai ReturnRequest khác nhau cùng cố trả nốt một sản phẩm cuối, cần cơ chế database/transaction gì để tránh cấp trùng quyền trả?
6. Viết test cho trạng thái đã SUBMITTED thì không còn được addReturnLine, và một test integration thể hiện hai request cạnh tranh.
7. Khi Payment trả kết quả muộn hoặc lặp, ReturnRequest và Payment phối hợp ra sao mà không giả định cả hai ở một transaction?

### Hướng giải định hướng

- ReturnRequest là root cho vòng đời của một yêu cầu và các dòng thuộc nó; không nên công khai setter đổi trạng thái/tổng hoàn. ReturnLine có thể là value object/entity con, với số lượng dương và snapshot giá.
- Tổng tiền hoàn phải được tính từ số lượng và giá đã cam kết theo chính sách. Không lấy giá Catalog hiện tại để thay giá giao dịch cũ.
- Quy tắc giới hạn **tổng số lượng đã trả trên nhiều ReturnRequest** phải được bảo vệ tại một nguồn có thẩm quyền, ví dụ ReturnAllowance/OrderReturnBalance theo (orderId, lineId). Nếu chỉ mỗi ReturnRequest tự kiểm tra các bản sao đã đọc, hai request đồng thời có thể đều chấp nhận số lượng cuối.
- Một phương án quan hệ dùng UPDATE có điều kiện trên hàng allowance (remainingQuantity >= requestedQuantity), đồng thời ghi quyền trả trong **cùng transaction**. Khi chia database, cần token quyền trả, idempotency, trạng thái trung gian và bù rõ ràng.
- Payment là aggregate/ngữ cảnh khác; trả kết quả qua hợp đồng có ID, phiên bản/idempotency. Một RefundSucceeded đến hai lần không được tạo hai lần quyền hoàn; trường hợp timeout cần đối soát thay vì gửi một lệnh hoàn mới mù quáng.
- Có thể dùng JOIN/read model để xem ReturnRequest, Order và Payment cùng nhau nhưng không trao quyền ghi của cả ba cho một aggregate.

## 14. Checklist và kết luận

- Có phải quy tắc nghiệp vụ đang rải rác trong controller, batch, listener hoặc các setter không?
- Những bất biến nào thuộc chính value object, entity con, aggregate root hay nguồn bên ngoài?
- Tên phương thức có diễn đạt **ý định nghiệp vụ** (submit, approve, cancel) thay vì thay trường tùy ý không?
- Getter có trả tham chiếu collection/object có thể sửa nội bộ mà không qua root không?
- Trạng thái, tổng tiền và các dữ liệu dẫn xuất có được cập nhật hoặc tính từ nguồn có thẩm quyền không?
- Input validation, domain validation và DB constraints có trách nhiệm rõ và bổ trợ nhau không?
- Application service có kiểm quyền từ ngữ cảnh xác thực, không tin ID actor do client truyền không?
- Mọi command ghi có transaction, version/lock và xử lý rollback khi nhiều hàng/tiến trình liên quan không?
- Lỗi đồng thời, retry, trạng thái không hợp lệ và đường ghi bỏ qua root đã có test chưa?
- Có tránh việc nhét cả I/O, báo cáo và các aggregate độc lập vào một entity quá lớn không?
- Đường đọc và mô hình vật lý đã được chọn phù hợp với workload, bất biến và chi phí tiến hóa chưa?

**Kết luận:** Mô hình miền không được đánh giá bằng số lượng getter/setter hay số lớp. Khi nghiệp vụ có ràng buộc, **hành vi phải được đặt tại điểm có thẩm quyền bảo vệ ràng buộc ấy**: value object, aggregate root, policy và transaction/constraint thích hợp. Getter có thể phục vụ đọc; setter có thể phục vụ ánh xạ được kiểm soát; nhưng không được để chúng trở thành lối đi tắt phá bất biến. Bằng cách thiết kế command rõ ý nghĩa và kết hợp kiểm soát đồng thời ở nơi lưu trữ, ta chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu an toàn, dễ kiểm chứng và có thể phát triển lâu dài.
