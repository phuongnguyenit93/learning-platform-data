# Đánh đổi giữa aggregate lớn, tranh chấp và yêu cầu giao dịch

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao một **aggregate lớn** có thể dễ giữ bất biến nhưng khó mở rộng, và vì sao chia nhỏ aggregate có thể làm xuất hiện yêu cầu phối hợp giao dịch.
- Xác định các **bất biến phải đúng ngay sau commit** và phân biệt chúng với sự nhất quán có thể đạt qua một quy trình nhiều bước.
- Đánh giá ranh giới aggregate bằng mức cạnh tranh ghi, số phần tử phải tải, phạm vi khóa, vòng đời và chi phí transaction, thay vì nhìn số bảng trong ERD.
- Thiết kế các command ghi có điều kiện, khóa lạc quan hoặc bi quan, constraint và giao dịch nguyên tử để tránh mất cập nhật hoặc vượt hạn mức.
- Chọn giữa một aggregate tập trung, nhiều aggregate cùng database và những aggregate độc lập kết nối qua hợp đồng, sự kiện hoặc quyền phân bổ trước.
- Kiểm chứng thiết kế bằng lịch thực thi đồng thời, chỉ số vận hành và tình huống lỗi giữa chừng, đồng thời cân nhắc mô hình quan hệ, document, đồ thị và phân tích.

Trong **DATABASE_DATA_MODELING**, một mô hình tốt không chỉ có tên thực thể và quan hệ chuẩn xác; nó còn phải biến yêu cầu nghiệp vụ thành **cam kết nhất quán có thể thực thi**. Một ranh giới aggregate quá rộng có thể khiến mọi thao tác tranh chấp cùng một root; ranh giới quá nhỏ có thể khiến những điều kiện bắt buộc đúng bị tách ra thành các giao dịch riêng và không còn được bảo vệ. Chủ đề này là quá trình tìm điểm cân bằng, không phải quy tắc "càng nhỏ càng tốt".

## 1. Ba lực kéo khi chọn ranh giới aggregate

**Aggregate** là một đơn vị nhất quán trong mô hình miền, có **aggregate root** quyết định những thay đổi hợp lệ đối với trạng thái thuộc trách nhiệm của nó. Có ba lực kéo chính:

1. **Bất biến nghiệp vụ:** dữ liệu nào phải được quyết định cùng nhau để không xảy ra trạng thái trái luật?
2. **Chi phí và tranh chấp:** có bao nhiêu command cùng cố thay đổi cùng một đơn vị, phải tải và khóa bao nhiêu dữ liệu, cần bao nhiêu lần retry?
3. **Ranh giới transaction và triển khai:** database có cung cấp thao tác nguyên tử phù hợp không; các phần cần phối hợp có ở cùng nguồn sở hữu và nơi lưu trữ không?

Một quan hệ 1-N trong ERD chưa chứng minh N đối tượng con phải ở chung một aggregate. Nhưng chia mỗi bảng thành một aggregate cũng không tự biến một bất biến xuyên bảng thành nhất quán được.

| Cách thiết kế | Lợi thế có thể có | Rủi ro thường gặp |
| --- | --- | --- |
| Một aggregate lớn bao trùm toàn bộ nhóm nghiệp vụ | Quy tắc nội bộ tập trung, dễ hiểu theo một root | Tải nhiều dữ liệu, tranh chấp phiên bản, hot row, transaction dài |
| Nhiều aggregate nhỏ có vòng đời riêng | Giảm dữ liệu phải nạp, độc lập thay đổi, dễ tổ chức quyền sở hữu | Quy tắc liên aggregate cần transaction hoặc giao thức riêng |
| Các aggregate tách service/database | Triển khai và mở rộng độc lập | Không có ACID cục bộ xuyên hệ thống; timeout, retry, trạng thái trung gian và bù |

**Aggregate là ranh giới logic, không nhất thiết là một bảng, một document, một tiến trình hay một khóa vật lý.** Một aggregate có thể trải trên nhiều hàng; một transaction SQL có thể tác động nhiều hàng. Ngược lại, dù cùng bảng, hai hàng có thể là hai aggregate độc lập.

## 2. Tình huống xuyên suốt: ngân sách chi tiêu dự án

Một tổ chức cấp cho dự án **100.000.000 VND** trong quý. Nhân viên gửi yêu cầu chi phí; một yêu cầu được duyệt thì hệ thống **giữ ngân sách** trước khi thực hiện thanh toán. Sau khi khoản chi được ghi nhận chính thức, tiền đã giữ chuyển thành **đã cam kết**. Nếu yêu cầu bị hủy hoặc hết hạn, số đã giữ được trả về hạn mức khả dụng.

Giả sử nghiệp vụ yêu cầu:

- Tổng **đã giữ + đã cam kết không vượt hạn mức** tại bất kỳ lần commit hợp lệ nào.
- Một yêu cầu chi có thể được gửi lại do mất phản hồi, nhưng không được giữ ngân sách hai lần cho cùng một ý định.
- Nhân viên có thể sửa nội dung yêu cầu trước khi duyệt; sau khi đã phê duyệt, số tiền cam kết phải được kiểm soát bằng command khác.
- Hồ sơ dự án, nhân viên, nhà cung cấp và thông tin thanh toán có vòng đời riêng.
- Đôi lúc có **500 yêu cầu trong một giây** cùng hướng tới một quỹ ngân sách; đây là tải minh họa để đánh giá thiết kế, không phải số đo đã kiểm thử.

Ta xác định hai nhóm dữ liệu:

- **BudgetPool**: hạn mức, số đã giữ, số đã cam kết, kỳ ngân sách, đơn vị tiền và quyền cấp hạn mức.
- **ExpenseRequest**: người đề nghị, mục đích, trạng thái duyệt, dòng chi phí, bằng chứng và lịch sử yêu cầu.

Chúng có liên hệ nhưng không hiển nhiên phải nằm chung aggregate. Trước khi quyết định, viết bất biến chính xác.

### Các bất biến và thời điểm cần nhất quán

Ký hiệu với một ngân sách:

- \(L\): hạn mức đã được phê duyệt;
- \(H\): tiền đang được giữ;
- \(C\): tiền đã cam kết/ghi chi theo chính sách;
- \(A=L-H-C\): tiền còn khả dụng.

Điều kiện cốt lõi:

\[
L \ge 0,\quad H \ge 0,\quad C \ge 0,\quad H+C \le L.
\]

Mọi giá trị phải thuộc **cùng loại tiền và cùng phạm vi ngân sách**. Ở ví dụ sử dụng đơn vị **đồng VND nguyên**, không dùng số thực dấu phẩy động để kiểm tra tiền. Nếu hỗ trợ nhiều loại tiền, cần có chính sách chuyển đổi, tỷ giá và cách làm tròn riêng trước khi quyết định hạn mức.

| Quy tắc | Đúng ngay sau commit? | Nơi có thẩm quyền |
| --- | --- | --- |
| Không giữ/cam kết quá L | Có | BudgetPool, nơi cấp quyền sử dụng quỹ |
| Cùng requestId không được tăng H hai lần | Có | Nơi lưu quyền giữ và kết quả command |
| Một khoản giữ chỉ được xác nhận hoặc giải phóng một lần | Có | Vòng đời BudgetReservation |
| ExpenseRequest APPROVED có thông tin phê duyệt hợp lệ | Có | ExpenseRequest |
| Thông tin ngân sách hiển thị trên dashboard cập nhật tức thì | Không nhất thiết; tùy SLA đọc | Projection/read model |
| Thanh toán ngân hàng thành công sau khi duyệt | Quy trình nhiều bước | Payment/Accounting có thẩm quyền |

Người thiết kế phải phân biệt **"ngân sách không bao giờ được cấp vượt hạn"** với **"mọi màn hình lập tức biết số dư mới"**. Có thể cho phép báo cáo trễ, nhưng không được dựa vào báo cáo trễ để quyết định cấp tiền mới.

## 3. Phương án A: aggregate lớn chứa mọi yêu cầu chi

Một phương án trực quan là xem **ProjectBudget** là root, chứa tất cả ExpenseRequest và thông tin giữ ngân sách:

~~~mermaid
flowchart TB
    S["Commands: Submit / Hold / Approve / Cancel"]
    S --> B
    subgraph Big["Aggregate ProjectBudget"]
        B["ProjectBudget root"]
        E1["ExpenseRequest #1"]
        E2["ExpenseRequest #2"]
        E3["... hàng nghìn yêu cầu khác"]
        B --> E1
        B --> E2
        B --> E3
    end
~~~

**Ưu điểm:**

- Root có thể kiểm tra tổng hạn mức và các thành viên trong một giao dịch nghiệp vụ.
- Các command liên quan cùng ngân sách được diễn đạt tập trung.
- Với quỹ nhỏ, ít yêu cầu, đơn giản và ít biến động, mô hình có thể rất phù hợp.

**Chi phí:**

- Nếu root được ORM nạp như cả một object graph, mỗi lệnh giữ 100.000 đồng có thể phải nạp rất nhiều ExpenseRequest không liên quan.
- Nếu mọi command ghi tăng **một version của root**, hai người sửa hai yêu cầu không liên quan vẫn có thể bị optimistic-lock conflict.
- Một hàng root/điểm khóa chung có thể trở thành **hot spot**; transaction giữ khóa lâu làm tăng thời gian chờ.
- Lịch sử dài hạn phát triển không giới hạn, nhưng dữ liệu cần nhất quán cho một lần cấp quỹ chỉ gồm hạn mức và quyền giữ đang hiệu lực.
- Dùng một root cho mọi dự án và mọi quý làm mức tranh chấp lớn hơn cả nhu cầu nghiệp vụ.

Không phải aggregate lớn **luôn** khóa toàn bộ bảng: database có thể khóa theo hàng và repository có thể thực hiện cập nhật tăng dần, không nạp toàn bộ dữ liệu. Vấn đề là **mô hình có buộc các thay đổi độc lập tranh chấp một đơn vị logic hay không**, cộng với cách ORM, repository và transaction hiện thực điều đó.

### Dấu hiệu root quá rộng

Một số chỉ dấu cần đo, không chỉ phỏng đoán:

- số phần tử và byte phải tải để thực hiện một command nhỏ;
- tỷ lệ phiên bản xung đột khi nhiều người sửa các phần khác nhau;
- thời gian chờ khóa và số deadlock;
- p95/p99 độ trễ ghi tăng mạnh khi tải hoặc số thành viên tăng;
- phải giữ transaction mở trong lúc gọi API ngoài;
- nhiều team cần sửa các phần có vòng đời độc lập của cùng root.

Nếu những vấn đề này xuất hiện, không nhất thiết phải tách ngay. Trước tiên xác định **bất biến tối thiểu thực sự đòi hỏi một quyết định chung**.

## 4. Phương án B: BudgetPool quyết định quyền chi, ExpenseRequest độc lập

Phân tích lại: **việc chi không vượt hạn mức** không đòi root BudgetPool chứa nội dung đề xuất, hóa đơn và ghi chú của hàng nghìn ExpenseRequest. Nó chỉ cần quản lý hạn mức và những quyền giữ/cam kết có thể đối soát.

~~~mermaid
flowchart LR
    App["Use case xét duyệt"]
    App -->|"Reserve(amount, requestId)"| Pool
    App -->|"Approve / Reject"| Expense

    subgraph A["Aggregate BudgetPool"]
        Pool["BudgetPool root<br/>limit, held, committed"]
        R["BudgetReservation<br/>reservationId, amount, status"]
        Pool --> R
    end

    subgraph E["Aggregate ExpenseRequest"]
        Expense["ExpenseRequest root<br/>reason, line items, approval"]
    end

    Expense -.->|"budgetId, reservationId"| Pool
~~~

Trong mô hình này:

- **BudgetPool** là nguồn có thẩm quyền cấp quyền giữ, chuyển quyền giữ thành cam kết và giải phóng quyền giữ.
- **BudgetReservation** có thể là thành viên của BudgetPool được lưu ở một bảng riêng; tất cả thao tác trên nó phải đi qua cùng giao thức ghi của BudgetPool.
- **ExpenseRequest** có trạng thái và vòng đời độc lập; chỉ giữ budgetId/reservationId, không tự tăng/giảm số dư bằng đường tắt.
- **Project**, **Employee** và **Payment** thuộc các nguồn khác; giữ ID hay snapshot cần thiết thay vì kéo toàn bộ vào BudgetPool.

Một ExpenseRequest được sửa mô tả không cần tranh version của BudgetPool. Chỉ khi hành động có tác động lên **quyền sử dụng ngân sách** thì phải đến điểm phân xử ngân sách.

### Gộp và tách theo câu hỏi nào?

| Câu hỏi | Nếu câu trả lời là có | Gợi ý |
| --- | --- | --- |
| Hai thuộc tính bắt buộc thay đổi cùng lúc để root còn hợp lệ? | Có | Ứng viên nằm trong cùng aggregate |
| Entity có vòng đời/phê duyệt riêng và được sửa không ảnh hưởng quỹ? | Có | Ứng viên làm root độc lập |
| Chỉ cần hiển thị hai nhóm dữ liệu cạnh nhau? | Có | Dùng JOIN/read model, không gộp root vì màn hình |
| Tất cả người dùng cùng tranh một giới hạn chung? | Có | Phải có một cơ chế phân xử chung hoặc phân quyền quota được chứng minh an toàn |
| Hai aggregate thuộc cùng database, cần commit một bước cùng nhau? | Có | Có thể dùng transaction liên root có chủ đích; hiểu chi phí phụ thuộc |
| Hai bên ở database/service độc lập? | Có | Thiết kế trạng thái trung gian, idempotency và quy trình bù |

**Tách aggregate không tự loại bỏ contention.** Nếu mọi command vẫn phải giành một hạn mức L chung, hàng BudgetPool vẫn là điểm phân xử chung. Nhưng tách có thể làm các thay đổi **không liên quan đến hạn mức** không còn tranh chấp với nó, đồng thời giảm dữ liệu phải tải.

## 5. Mô tả command, vòng đời và bất biến trước khi viết SQL

Quyền giữ ngân sách có vòng đời riêng:

~~~mermaid
stateDiagram-v2
    [*] --> HELD: ReserveBudget
    HELD --> COMMITTED: CommitBudget
    HELD --> RELEASED: ReleaseBudget
    HELD --> EXPIRED: ExpireBudgetHold
    COMMITTED --> [*]
    RELEASED --> [*]
    EXPIRED --> [*]
~~~

Các chuyển trạng thái mẫu:

| Command | Điều kiện trước | Cập nhật nguyên tử | Không được xảy ra |
| --- | --- | --- | --- |
| ReserveBudget | Quỹ OPEN; amount dương; A đủ; chưa xử lý requestId | Thêm Reservation HELD, tăng H | H+C vượt L; tạo hai quyền giữ từ một requestId |
| CommitBudget | Reservation HELD, chưa hết hạn; có bằng chứng duyệt theo chính sách | HELD → COMMITTED, H giảm và C tăng cùng số tiền | Tăng C lần nữa khi retry |
| ReleaseBudget | Reservation HELD và được phép hủy | HELD → RELEASED, H giảm | Trừ H hai lần |
| ExpireBudgetHold | Reservation HELD và đã hết hạn | HELD → EXPIRED, H giảm | Giải phóng khoản đã COMMITTED |
| ChangeBudgetLimit | Người duyệt có quyền; L mới ≥ H+C | Sửa L có điều kiện | Làm quỹ bị âm khả dụng sau commit |

Nếu một khoản chi đã COMMITTED cần hoàn hoặc điều chỉnh, đó là một **command nghiệp vụ mới** với quyền và bằng chứng riêng, không nên cho phép sửa trạng thái tùy ý từ COMMITTED về HELD.

### Ví dụ Java: root giữ bất biến trong bộ nhớ

Ví dụ sử dụng số nguyên biểu diễn **đồng VND** để tránh sai số của double; đây chỉ là mô hình miền rút gọn, không phải toàn bộ repository hay hệ thống kiểm toán:

~~~java
import java.util.Objects;
import java.util.UUID;

record BudgetId(UUID value) {
    BudgetId { Objects.requireNonNull(value); }
}

final class BudgetPool {
    private final BudgetId id;
    private long limitVnd;
    private long heldVnd;
    private long committedVnd;

    BudgetPool(BudgetId id, long limitVnd,
               long heldVnd, long committedVnd) {
        this.id = Objects.requireNonNull(id);
        if (limitVnd < 0 || heldVnd < 0 || committedVnd < 0
                || heldVnd > limitVnd
                || committedVnd > limitVnd - heldVnd) {
            throw new IllegalArgumentException("Invalid budget");
        }
        this.limitVnd = limitVnd;
        this.heldVnd = heldVnd;
        this.committedVnd = committedVnd;
    }

    long availableVnd() {
        return limitVnd - heldVnd - committedVnd;
    }

    void reserve(long amountVnd) {
        requirePositive(amountVnd);
        if (availableVnd() < amountVnd) {
            throw new IllegalStateException("Insufficient budget");
        }
        heldVnd = Math.addExact(heldVnd, amountVnd);
    }

    void commit(long amountVnd) {
        requirePositive(amountVnd);
        if (heldVnd < amountVnd) {
            throw new IllegalStateException("Not held");
        }
        heldVnd -= amountVnd;
        committedVnd = Math.addExact(committedVnd, amountVnd);
    }

    void release(long amountVnd) {
        requirePositive(amountVnd);
        if (heldVnd < amountVnd) {
            throw new IllegalStateException("Not held");
        }
        heldVnd -= amountVnd;
    }

    private static void requirePositive(long amountVnd) {
        if (amountVnd <= 0) {
            throw new IllegalArgumentException("amount <= 0");
        }
    }
}
~~~

Lớp này minh họa **bất biến tổng tiền**, nhưng chưa chứng minh một Reservation cụ thể có được commit hoặc release lần đầu hay không. Tầng miền/repository quản lý **reservationId, requestId và trạng thái** phải phối hợp với root trong cùng transaction để ngăn xử lý trùng. Đồng thời, kiểm tra in-memory không đủ khi hai JVM cùng nạp ngân sách; database phải có cơ chế đồng bộ hóa.

## 6. Lược đồ quan hệ phục vụ ranh giới đã chọn

Với PostgreSQL, có thể lưu BudgetPool ở một bảng, BudgetReservation ở bảng khác. Đây vẫn có thể là **một aggregate logic** nếu BudgetPool điều phối mọi thao tác ghi làm thay đổi quyền giữ ngân sách.

~~~sql
CREATE SCHEMA IF NOT EXISTS finance;

CREATE TABLE finance.budget_pool (
    tenant_id UUID NOT NULL,
    budget_id UUID NOT NULL,
    period_code VARCHAR(16) NOT NULL,
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    state VARCHAR(12) NOT NULL DEFAULT 'OPEN'
        CHECK (state IN ('OPEN', 'FROZEN', 'CLOSED')),
    limit_vnd BIGINT NOT NULL CHECK (limit_vnd >= 0),
    held_vnd BIGINT NOT NULL DEFAULT 0 CHECK (held_vnd >= 0),
    committed_vnd BIGINT NOT NULL DEFAULT 0 CHECK (committed_vnd >= 0),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    PRIMARY KEY (tenant_id, budget_id),
    CONSTRAINT no_budget_overspend
        CHECK (held_vnd <= limit_vnd
           AND committed_vnd <= limit_vnd - held_vnd)
);

CREATE TABLE finance.budget_reservation (
    tenant_id UUID NOT NULL,
    reservation_id UUID NOT NULL,
    budget_id UUID NOT NULL,
    expense_request_id UUID NOT NULL,
    request_id UUID NOT NULL,
    amount_vnd BIGINT NOT NULL CHECK (amount_vnd > 0),
    state VARCHAR(12) NOT NULL
        CHECK (state IN ('HELD', 'COMMITTED', 'RELEASED', 'EXPIRED')),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, reservation_id),
    UNIQUE (tenant_id, request_id),
    FOREIGN KEY (tenant_id, budget_id)
        REFERENCES finance.budget_pool (tenant_id, budget_id)
);

-- Một yêu cầu chi không có hai quyền giữ hoạt động/cam kết.
CREATE UNIQUE INDEX one_live_budget_reservation_per_expense
    ON finance.budget_reservation (tenant_id, expense_request_id)
    WHERE state IN ('HELD', 'COMMITTED');

-- Truy vấn dọn những quyền giữ quá hạn.
CREATE INDEX held_budget_expiry
    ON finance.budget_reservation (expires_at)
    WHERE state = 'HELD';
~~~

**Các ràng buộc có tác dụng gì?**

- CHECK trên budget_pool kiểm soát phép tính cục bộ theo hàng: \(H+C \le L\). Nó không chứng minh tổng các dòng reservation bằng H/C.
- UNIQUE(tenant_id, request_id) bảo vệ tính duy nhất của một yêu cầu giữ; khi retry phải so sánh nội dung với yêu cầu cũ, không chỉ dựa vào ID trùng.
- UNIQUE có điều kiện ngăn hai quyền giữ còn hiệu lực hoặc đã cam kết cho cùng một ExpenseRequest. Nếu nghiệp vụ cho phép nhiều đợt chi độc lập cho một ExpenseRequest, cần đổi khóa nghiệp vụ, không giữ chỉ mục không còn đúng.
- FK ghép tenant_id và budget_id bảo vệ quan hệ trong nguồn sở hữu. expense_request_id chỉ là ID tham chiếu đến aggregate ExpenseRequest, không mặc định cấp quyền sửa ExpenseRequest.
- Chỉ mục theo expires_at phục vụ tác vụ giải phóng hết hạn; mọi chỉ mục vẫn có chi phí duy trì khi ghi và phải đánh giá với workload thực tế.

**Giới hạn quan trọng:** bộ đếm H, C phải khớp với quyền giữ/cam kết trong bảng reservation. PostgreSQL CHECK không thể tự đối chiếu tổng nhiều hàng bằng một phép CHECK thông thường. Tất cả đường ghi làm đổi reservation phải cập nhật pool trong cùng transaction, bảo đảm quyền thực thi chỉ đi qua API/repository thích hợp; có thể bổ sung trigger hoặc đối soát nếu chính sách an toàn yêu cầu.

## 7. Giao dịch nguyên tử: giữ ngân sách mà không chi quá hạn

Một command ReserveBudget có thể thực hiện bằng các bước dưới đây trong **một transaction**:

~~~sql
BEGIN;

INSERT INTO finance.budget_reservation
    (tenant_id, reservation_id, budget_id, expense_request_id,
     request_id, amount_vnd, state, expires_at)
VALUES
    (:tenant_id, :reservation_id, :budget_id, :expense_request_id,
     :request_id, :amount_vnd, 'HELD', :expires_at)
ON CONFLICT DO NOTHING
RETURNING reservation_id;

-- Nếu 0 hàng: ROLLBACK. Kiểm tra requestId đã xử lý
-- hay một ExpenseRequest đã có quyền giữ; không tăng H.

UPDATE finance.budget_pool
SET held_vnd = held_vnd + :amount_vnd,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND budget_id = :budget_id
  AND state = 'OPEN'
  AND :amount_vnd > 0
  AND limit_vnd - held_vnd - committed_vnd >= :amount_vnd
RETURNING version;

-- Nếu UPDATE 0 hàng: ROLLBACK cả INSERT; trả hết hạn mức,
-- quỹ không OPEN hoặc quỹ không tồn tại theo kết quả kiểm tra.

COMMIT;
~~~

Ở mức SQL, điều kiện so sánh cùng thao tác UPDATE là phần quyết định. Giả sử H+C = 30 triệu, L = 100 triệu và **hai yêu cầu 70 triệu** đến gần như đồng thời. Cả hai có thể đọc trước đó rằng còn 70 triệu, nhưng hai UPDATE trên **cùng một hàng budget_pool** sẽ phải đồng bộ hóa. Theo cơ chế khóa hàng của PostgreSQL ở mức READ COMMITTED, UPDATE chờ giao dịch đang sửa hàng, rồi đánh giá lại điều kiện trên phiên bản hàng đã commit. Tối đa một yêu cầu được tăng H lên 100 triệu.

Nếu chỉ dùng:

~~~text
SELECT remainingBudget;
if remainingBudget >= amount:
    INSERT reservation;
    UPDATE budget_pool theo giá trị đã tính trong bộ nhớ;
~~~

thì hai request có thể cùng nhìn thấy ngân sách cũ và chấp nhận quá hạn hoặc ghi đè giá trị. **Một phép kiểm tra trước rồi ghi sau không được bảo vệ đồng thời không tương đương với cập nhật có điều kiện nguyên tử.**

### Kiểm tra lỗi, rollback và retry

Ứng dụng phải kiểm tra kết quả từng statement. Nếu INSERT không trả hàng, **không chạy UPDATE**. Nếu UPDATE không trả hàng, rollback INSERT. Dữ liệu requestId giống nhau nhưng amount khác nhau phải được báo xung đột thay vì âm thầm coi là một lần retry hợp lệ.

Khi client mất phản hồi sau COMMIT, lần gửi lại với requestId cũ không được cấp thêm quỹ. Hệ thống đọc reservation hiện có, kiểm tra tenant/budget/amount/expense_request_id có khớp và trả về kết quả đã lưu. requestId dùng cho **ý định command**, không thay thế reservationId hay ID của ExpenseRequest.

Nếu DB báo deadlock, serialization failure hoặc lỗi kết nối khiến kết quả commit không rõ, retry phải theo chính sách phù hợp và **giữ ổn định requestId**; không mù quáng tạo yêu cầu mới rồi làm nhân đôi quyền giữ.

## 8. Chuyển HELD sang COMMITTED hoặc RELEASED

Một quyền giữ cụ thể có thể được **commit đúng một lần**. Không được chỉ trừ H bằng amount truyền từ caller mà không kiểm tra trạng thái reservation.

### Commit khoản đã giữ

~~~sql
BEGIN;

UPDATE finance.budget_reservation
SET state = 'COMMITTED'
WHERE tenant_id = :tenant_id
  AND reservation_id = :reservation_id
  AND state = 'HELD'
  AND expires_at > clock_timestamp()
RETURNING budget_id, amount_vnd;

-- Nếu 0 hàng: không sửa budget_pool.
-- Nếu 1 hàng: lấy budget_id, amount_vnd thực từ RETURNING.

UPDATE finance.budget_pool
SET held_vnd = held_vnd - :returned_amount_vnd,
    committed_vnd = committed_vnd + :returned_amount_vnd,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND budget_id = :returned_budget_id
  AND held_vnd >= :returned_amount_vnd
RETURNING version;

-- Nếu 0 hàng: ROLLBACK toàn bộ transaction, báo lệch trạng thái.
COMMIT;
~~~

Phải kiểm tra **đúng một hàng ở cả hai UPDATE** trước khi COMMIT; các tham số returned_* lấy từ kết quả câu đầu, không lấy từ request tùy ý. Lệnh chuyển trạng thái không làm thay đổi tổng H+C, mà chuyển quyền đã giữ sang đã cam kết. Nếu yêu cầu đã COMMITTED, lệnh lặp không chạy lại bước tăng C; đọc trạng thái hiện có để trả kết quả đã xử lý.

Trong ví dụ, clock_timestamp() diễn tả thời gian ở lúc statement kiểm tra. Nếu chính sách yêu cầu "không bao giờ có commit sau chính xác thời điểm hết hạn", cần phân tích kỹ thời điểm phán quyết, độ dài transaction và clock ở nguồn có thẩm quyền; một kiểm tra thời gian ở đầu transaction không tự là bảo đảm đến thời điểm COMMIT.

### Giải phóng khoản giữ

~~~sql
BEGIN;

UPDATE finance.budget_reservation
SET state = 'RELEASED'
WHERE tenant_id = :tenant_id
  AND reservation_id = :reservation_id
  AND state = 'HELD'
RETURNING budget_id, amount_vnd;

-- Chỉ nếu đúng 1 hàng:
UPDATE finance.budget_pool
SET held_vnd = held_vnd - :returned_amount_vnd,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND budget_id = :returned_budget_id
  AND held_vnd >= :returned_amount_vnd;

-- Nếu không cập nhật đúng 1 hàng của pool: ROLLBACK.
COMMIT;
~~~

Nếu hai worker cùng hủy một reservation, chỉ một worker chuyển được HELD → RELEASED. Worker còn lại không có dòng RETURNING, vì vậy không được trừ ngân sách lần hai. Tác vụ hết hạn cũng theo **cùng mẫu chuyển trạng thái có điều kiện** nhưng đổi sang EXPIRED và phải xác minh thời hạn.

Chuyển khoản giữ thành cam kết chỉ có nghĩa **hạn mức ngân sách đã được tiêu dùng theo chính sách**, không mặc nhiên có nghĩa ngân hàng đã chuyển tiền. Payment/Accounting có thể có vòng đời riêng, yêu cầu đối soát và các bút toán điều chỉnh.

## 9. Phân tích tranh chấp: chỗ nóng nằm ở đâu?

Aggregate lớn thường bị chậm bởi hai nguyên nhân khác nhau cần tách bạch:

**Tranh chấp logic:** mọi thay đổi tăng cùng một version hoặc khóa quyết định của root. Hai cập nhật độc lập vẫn có thể xung đột nếu được đặt trong một phạm vi root quá rộng.

**Tranh chấp vật lý:** nhiều transaction cùng cần sửa một hàng/index/partition hoặc giữ khóa lâu. Ngay cả khi tách ExpenseRequest khỏi BudgetPool, lệnh cấp hạn mức vẫn phải cạnh tranh tại hàng BudgetPool vì giới hạn L là chung.

Ví dụ minh họa, nếu mỗi transaction giữ khóa hàng ngân sách trung bình **25 ms**, một hàng cần xử lý tuần tự về lý thuyết chỉ có khoảng **1 / 0,025 = 40 lượt chiếm khóa mỗi giây** trước khi tính thêm thời gian chờ, I/O và biến động. Đây **không phải** một benchmark PostgreSQL hoặc cam kết thông lượng: thời gian giữ khóa thực tế phải được đo, và transaction khác có thể làm nhiều việc song song trên các hàng khác.

### Tác nhân thường làm tăng thời gian giữ khóa

- Nạp hoặc ghi lại cả một object graph hàng nghìn thành viên chỉ để thay một khoản tiền.
- Giữ transaction mở trong lúc gọi HTTP đến Payment, gửi email hoặc đợi người dùng.
- Ghi quá nhiều index, trigger hoặc dòng audit đồng bộ trong đường ghi nóng.
- Các giao dịch khóa nhiều pool nhưng lấy khóa theo thứ tự khác nhau, tạo deadlock.
- Một transaction sửa quá nhiều aggregate không liên quan chỉ vì service có quyền truy cập chung database.
- Sử dụng optimistic locking trên root bị thay đổi liên tục khiến số lần retry tăng nhanh.

Nên **chuẩn bị dữ liệu và gọi dịch vụ ngoài trước/sau transaction** phù hợp với nghiệp vụ, giữ đoạn transaction có khóa càng gọn càng tốt. Nhưng không được chuyển các bước cần nhất quán ra ngoài một cách tùy tiện chỉ để giảm thời gian khóa.

## 10. Chọn cơ chế đồng thời theo đặc tính bất biến

| Cơ chế | Ưu điểm | Giới hạn/cảnh báo |
| --- | --- | --- |
| **Optimistic locking** với version | Đơn giản khi ít xung đột, không giữ khóa trong lúc sửa trên ứng dụng | Root quá nóng làm retry nhiều; phải kiểm tra đúng số hàng ghi |
| **Pessimistic locking** (SELECT FOR UPDATE) | Phân xử trước khi sửa, tiện khi cần kiểm tra nhiều dữ liệu phụ thuộc | Tăng chờ, nguy cơ deadlock, cần thứ tự khóa ổn định |
| **UPDATE có điều kiện** trên cùng một hàng | Giữ phép kiểm tra và thay đổi nguyên tử cho bộ đếm/giới hạn | Hàng vẫn có thể là hot spot; các bên phải dùng cùng giao thức |
| **UNIQUE / CHECK / FK** | Bảo vệ ràng buộc diễn đạt được ở DB ngay cả khi nhiều request chạy | Không thay thế quy tắc nhiều hàng hoặc ý nghĩa trạng thái miền |
| **SERIALIZABLE** và retry | Có thể ngăn các hiện tượng bất thường nhất định khi logic đọc/ghi được viết đúng | Có thể phát sinh serialization failure; phải retry cả transaction, không phải chỉ SQL cuối |
| **Quyền hạn mức phân bổ trước (escrow)** | Giảm phụ thuộc vào một điểm ghi trung tâm cho từng thao tác | Khó cấp lại phần chưa dùng, cân bằng quota, bảo vệ tổng phân bổ |

**Isolation level không sửa được sai lầm mô hình.** READ COMMITTED với UPDATE có điều kiện trên cùng một hàng có thể bảo vệ giới hạn cục bộ rất tốt. Nhưng nếu bất biến là "không được có hai lịch thuê trùng nhau" trên **nhiều hàng khác nhau**, chỉ hai SELECT rồi INSERT dưới READ COMMITTED có thể gặp *write skew*. Khi đó cần constraint phù hợp (ví dụ exclusion constraint cho khoảng thời gian ở PostgreSQL), khóa nguồn có thẩm quyền hoặc mức cô lập và cơ chế retry thích hợp.

Một transaction SERIALIZABLE cũng không tự bảo đảm tính nhất quán **xuyên hai dịch vụ độc lập**. Nó chỉ áp dụng trong phạm vi database/transaction nơi cơ chế đó có hiệu lực.

### Khi nào nên khóa lạc quan?

Với ExpenseRequest có ít người sửa cùng lúc, optimistic locking theo request version thường phù hợp. Với BudgetPool mà hàng trăm lệnh cấp quỹ cùng dồn về, phiên bản vẫn có ích cho quản trị và đối soát, nhưng **phép cấp quỹ có điều kiện trực tiếp trên DB** có thể tránh vòng đọc-đổi-ghi lại toàn bộ root rồi retry không cần thiết.

Nếu dùng SELECT ... FOR UPDATE để đọc pool rồi tính toán, giữ khóa chỉ trong transaction ngắn, luôn kiểm tra quyền và mức tiền, và lấy khóa theo thứ tự cố định khi một command đụng nhiều pool.

## 11. Khi nào một transaction cần chạm nhiều aggregate?

Quy tắc thường dùng là **một command sửa một aggregate mỗi lần** để ranh giới nhất quán rõ và giảm phụ thuộc. Tuy nhiên đây là hướng dẫn thiết kế, **không phải hạn chế tuyệt đối của PostgreSQL**.

Ví dụ yêu cầu "duyệt ExpenseRequest **và** cấp quyền giữ BudgetPool phải thành công hoặc cùng thất bại":

- Nếu cả hai thuộc cùng một ứng dụng và cùng PostgreSQL, một **transaction cục bộ** có thể cập nhật ExpenseRequest và BudgetPool/Reservation đồng thời. Đây là sự phụ thuộc có chủ đích giữa hai root; nên giới hạn phạm vi và ghi rõ lý do.
- Nếu hai root có vòng đời khác nhau nhưng không cần hiển thị APPROVED ngay, có thể để ExpenseRequest ở PENDING_BUDGET và chuyển APPROVED chỉ sau khi giữ quỹ thành công.
- Nếu hai root nằm ở hai database hoặc bounded context triển khai độc lập, một transaction SQL cục bộ không bao trùm cả hai. Cần một **quy trình phối hợp** có trạng thái trung gian và xử lý lỗi.

### Tại sao không nhúng mọi thứ vào một aggregate để có transaction?

Một transaction xuyên hai root cùng DB không buộc ta biến chúng thành một object graph có vòng đời chung. Ranh giới aggregate vẫn nói rõ **ai sở hữu bất biến nào**, còn transaction là công cụ giải quyết một nhu cầu nguyên tử cụ thể. Ngược lại, gom mọi thứ vào aggregate lớn cũng không tự tạo ACID xuyên các database độc lập.

Việc một bounded context có nhiều aggregate hay một database dùng nhiều schema cũng không cho biết transaction cục bộ bao phủ tới đâu; phải kiểm tra kiến trúc triển khai và khả năng của hệ quản trị thực tế.

## 12. Khi phải tách database: reservation token và quy trình bù

Giả sử ExpenseRequest thuộc Procurement, còn BudgetPool thuộc Finance; mỗi bên có database riêng.

~~~mermaid
sequenceDiagram
    participant U as Employee
    participant E as Procurement / ExpenseRequest
    participant B as Finance / BudgetPool
    participant P as Payment

    U->>E: SubmitExpense(expenseId)
    E->>E: Ghi PENDING_BUDGET
    E->>B: ReserveBudget(requestId, budgetId, amount)
    B->>B: Điều kiện hạn mức + commit reservation
    B-->>E: Reserved(reservationId, expiresAt)
    E->>E: Ghi BUDGET_HELD
    E->>P: Khởi tạo bước chi theo quy trình
    P-->>E: Kết quả nghiệp vụ
    E->>B: CommitBudget hoặc ReleaseBudget
    B-->>E: Kết quả chuyển quyền giữ
    E->>E: Chuyển trạng thái cuối phù hợp
~~~

Trong kịch bản này:

- BudgetPool **phải bảo vệ H+C ≤ L ngay tại Finance**. Không dựa vào bản sao ngân sách từ Procurement.
- ReservationId/token là **bằng chứng quyền giữ**, có thời hạn và trạng thái. Procurement không được tự tạo token rồi coi ngân sách đã được giữ.
- Các lệnh ReserveBudget, CommitBudget và ReleaseBudget cần **idempotency key** hoặc ngữ nghĩa xử lý lặp rõ ràng.
- Cần xử lý việc Finance giữ quỹ thành công nhưng Procurement mất phản hồi: kiểm tra lại requestId, không tự cấp lần thứ hai.
- Nếu bước sau thất bại, thực hiện **bù** như ReleaseBudget; bù là một command nghiệp vụ được kiểm soát, không phải ROLLBACK ACID xuyên các service.
- Khi giao tiếp qua broker, dùng transactional outbox/inbox hoặc cơ chế bền vững tương ứng để không mất ý định thông báo sau khi commit; bên nhận vẫn phải chịu được thông điệp lặp/đến trễ.

**Đừng dùng eventual consistency để nới lỏng bất biến tuyệt đối.** Trạng thái ExpenseRequest có thể cập nhật trễ, nhưng giới hạn ngân sách tại Finance không được phép bị vượt trong lúc đồng bộ. Khi cần điều kiện xuyên dịch vụ đúng tuyệt đối ngay tại một điểm, phải thiết kế **điểm phân xử có thẩm quyền hoặc giao thức phối hợp mạnh**; không tuyên bố chắc chắn chỉ nhờ sự kiện cuối cùng sẽ đến.

## 13. Khi một điểm cấp hạn mức vẫn quá nóng: chia quota có bảo toàn

Sau khi tách ExpenseRequest, có thể vẫn còn hàng BudgetPool nhận quá nhiều UPDATE. Một cách giảm contention là **phân bổ trước quyền chi** cho các đơn vị độc lập (*escrow quota*, *preallocated credits*).

Ví dụ L = 100 triệu VND. Finance phân bổ:

| Nhóm xử lý | Quota được cấp trước | Đã dùng/giữ cục bộ tối đa |
| --- | ---: | ---: |
| Nhóm A | 40 triệu | 40 triệu |
| Nhóm B | 35 triệu | 35 triệu |
| Nhóm C | 25 triệu | 25 triệu |
| **Tổng** | **100 triệu** | **Không thể vượt 100 triệu nếu mỗi nhóm giữ đúng giới hạn** |

Điều kiện cần:

\[
\sum_i Q_i \le L,\qquad 0 \le U_i \le Q_i.
\]

Nếu mỗi nhóm chỉ chấp nhận khoản chi trong quota riêng đã được cấp, thì tổng quyền chi không vượt L mà mỗi yêu cầu không nhất thiết khóa cùng một hàng ngân sách toàn cục. **Nhưng quota phải được cấp và chuyển giữa các nhóm bằng thao tác được điều phối nguyên tử**. Nếu Finance cấp 40 triệu cho nhóm A rồi cấp lại chính 40 triệu đó cho B trước khi thu hồi quyền cũ, tổng quyền chi có thể vượt hạn mức.

Nhược điểm quan trọng:

- Có thể nhóm A hết quota trong khi nhóm B còn 20 triệu chưa dùng; hệ thống cần cơ chế chuyển hoặc hoàn quota.
- Thu hồi quyền đã phân bổ khi node mất kết nối khó hơn tăng/giảm một bộ đếm tập trung.
- Phải tránh nhân đôi quota do retry, replica cũ hoặc thay đổi phân vùng.
- Báo cáo tổng có thể cập nhật chậm, trong khi giới hạn tổng quyền cấp vẫn cần đúng.

**Phân mảnh dữ liệu không đồng nghĩa phân mảnh được bất biến.** Chỉ chia bảng theo hash của expense_request_id mà cho mỗi shard tự so với L đầy đủ sẽ khiến tổng các shard có thể vượt L. Quota phân bổ trước an toàn vì tổng quyền được phân bổ đã bị giới hạn ngay từ đầu.

Nếu hạn mức thực sự độc lập theo **dự án + quý + hạng mục**, có thể chọn một BudgetPool root cho mỗi tổ hợp đó thay vì tạo escrow phức tạp. Nhưng chỉ được tách khi nghiệp vụ thật sự cho phép giới hạn độc lập; một hạn mức tổng chung vẫn cần chính sách phân phối hoặc kiểm soát toàn cục.

## 14. Trade-off khi đổi công nghệ lưu trữ

| Hệ thống lưu trữ | Cách hiện thực | Điểm cần chú ý |
| --- | --- | --- |
| **Quan hệ** | BudgetPool ở một hàng; Reservation ở bảng phụ; command ghi trong transaction với constraint | Hot row, lock wait, isolation, index và quyền ghi đúng root |
| **Document** | Có thể nhúng quyền giữ hữu hạn trong một BudgetPool document hoặc tách collection | Phạm vi cập nhật nguyên tử của sản phẩm, giới hạn document, xung đột ghi toàn document |
| **Đồ thị** | Liên kết Budget, ExpenseRequest, Employee, Project qua node/edge để phân tích tác động | Edge không tự bảo vệ hạn mức hoặc tạo quyền ghi xuyên root |
| **Phân tích/cột** | FactBudgetTransaction, factExpense và dimension kỳ/dự án | Projection giúp báo cáo, có thể trễ, không nên là nguồn ra quyết định cấp quỹ |

Ở document database, gộp tất cả reservation vào document có thể tiện khi số phần tử nhỏ và được cập nhật nguyên tử. Nhưng nếu số reservation rất lớn, document liên tục lớn lên và cập nhật một trường vẫn tranh chấp tài liệu nóng. Chọn nhúng hay tham chiếu **theo bất biến, workload và giới hạn sản phẩm cụ thể**, không chỉ theo nhãn "NoSQL".

Ở hệ thống quan hệ, nhiều bảng không cản trở một aggregate logic nếu repository bảo đảm giao dịch. Với kho phân tích, nhu cầu JOIN ExpenseRequest với BudgetPool để xem KPI cũng không khiến chúng trở thành một aggregate. **Đường đọc** có thể tổng hợp tự do, còn **đường ghi** phải tôn trọng nguồn sự thật.

## 15. Cách đo và kiểm thử trước khi đổi ranh giới

Một thiết kế được coi là tốt khi các bất biến được giữ và vận hành đáp ứng tải thực tế. Nên ghi ra các chỉ số:

| Chỉ số | Ý nghĩa | Biện pháp xem xét khi xấu |
| --- | --- | --- |
| p50 / p95 / p99 thời gian command | Độ trễ, đặc biệt phần đuôi khi tranh chấp | Tách thời gian DB, chờ khóa, gọi dịch vụ ngoài |
| Lock wait / deadlock | Cạnh tranh và thứ tự giữ khóa | Transaction ngắn, thứ tự khóa cố định, cập nhật ít hàng hơn |
| Optimistic version conflict | Bao nhiêu lệnh phải retry vì root đổi | Giảm phạm vi xung đột không cần thiết, cân nhắc điều kiện ghi |
| Transaction abort/retry rate | Chi phí khi isolation/constraint từ chối | Retry an toàn, tối ưu kiểu khóa, xem lại bất biến |
| Số hàng/byte nạp mỗi command | Aggregate có bị tải quá rộng không | Tối ưu repository và ranh giới dữ liệu |
| Throughput theo budgetId | Root nào là hot spot | Phân đoạn theo bất biến độc lập hoặc quota có bảo toàn |
| Thời gian chờ/hết hạn reservation | Quy trình có bị treo hay gây giữ quỹ lâu không | Deadline, tác vụ expire, đối soát và dashboard |
| Outbox lag / sự kiện trùng | Sức khỏe tích hợp bất đồng bộ | Relay, retry, idempotency, monitoring |

### Các kịch bản bắt buộc kiểm thử

**Kịch bản 1 — Hai khoản cạnh tranh:** quỹ còn 70 triệu, hai request khác nhau đều xin giữ 70 triệu. Sau tất cả commit/rollback, nhiều nhất một quyền giữ được tạo và \(H+C \le L\).

**Kịch bản 2 — Gửi lại cùng requestId:** request đầu commit rồi phản hồi mất. Retry cùng ID không tạo thêm reservation và không tăng H; nếu payload khác, trả lỗi nhất quán.

**Kịch bản 3 — Xác nhận và hủy cùng lúc:** hai command trên một reservation HELD. Chỉ một transition hợp lệ; không vừa tăng C vừa giải phóng cùng khoản giữ.

**Kịch bản 4 — Crash giữa hai bước SQL:** INSERT reservation thành công nhưng UPDATE pool thất bại. Transaction rollback; không còn reservation HELD "mồ côi" bị tính sai.

**Kịch bản 5 — Đổi hạn mức đồng thời:** quản trị viên giảm L trong lúc có reserve. Không bao giờ commit L mới thấp hơn H+C.

**Kịch bản 6 — Hai ngân sách liên quan:** command chuyển hạn mức từ Budget A sang B cần nguyên tử ở cùng database, thứ tự khóa ổn định hoặc quy trình liên dịch vụ có trạng thái bù nếu khác nơi lưu.

**Kịch bản 7 — Mất kết nối ở trạng thái không rõ:** client không biết ReserveBudget đã commit chưa. Nó hỏi theo requestId trước khi quyết định retry, tránh ghi lặp.

**Kịch bản 8 — Sai đường ghi:** thử một service phụ ghi trực tiếp reservation không cập nhật pool. Phải được chặn bởi quyền, API/DB constraint/trigger phù hợp hoặc được phát hiện và sửa theo chính sách. Không thể chỉ "tin mọi nhóm sẽ nhớ".

Ngoài unit test miền, cần chạy **integration test trên database thật**, vì khóa, isolation, deadlock và unique constraint không thể được kiểm chứng đầy đủ bằng một mock repository chạy tuần tự.

## 16. Bài tập thực hành: giới hạn voucher của chiến dịch

**Bối cảnh:** Sàn thương mại điện tử chạy chiến dịch tặng voucher trị giá 50.000 VND. Tổng cộng chỉ được phát **10.000 voucher**; mỗi khách có tối đa một voucher còn hiệu lực. Hàng chục nghìn người nhấn nhận trong vài giây. Chiến dịch có tên, mô tả, điều kiện áp dụng và lịch sử chỉnh sửa; mỗi Voucher có vòng đời ISSUED, REDEEMED, EXPIRED, CANCELLED. Hệ thống thanh toán và hệ thống marketing có database riêng.

### Yêu cầu

1. Nếu gom Campaign, mọi Voucher và hồ sơ Customer vào một aggregate, phần nào thực sự cần ở cùng ranh giới bất biến? Điều gì sẽ trở thành điểm tranh chấp?
2. Đề xuất cách tách **CampaignQuota** và **Voucher**. Command nào phải được phân xử tại CampaignQuota?
3. Viết ràng buộc "không phát quá 10.000 voucher" và "một khách chỉ có một voucher còn hiệu lực" dưới dạng bất biến; nêu cơ chế SQL/transaction để bảo vệ.
4. Hai người cùng nhận voucher cuối, và cùng một khách gửi request lặp, hệ thống cần xử lý thế nào?
5. Nếu Voucher và CampaignQuota ở hai database khác nhau, trạng thái trung gian/token quyền cấp nào cần có? Khi một bước thất bại, xử lý bù ra sao?
6. Nếu một CampaignQuota row trở thành hot spot, hãy phân tích phương án quota chia theo khu vực/nhóm, nêu cách bảo đảm tổng quyền phát không vượt 10.000.

### Hướng giải

- Campaign mô tả nội dung, lịch, điều kiện; Customer có hồ sơ độc lập. Quyền phát voucher phải thuộc **một nguồn hạn mức có thẩm quyền**. Không kéo toàn bộ hồ sơ và lịch sử vào một root chỉ để giới hạn số lượng.
- Có thể dùng CampaignQuota có issuedCount và quotaLimit; Voucher là aggregate vòng đời riêng. Khi cấp, dùng transaction với UPDATE có điều kiện issuedCount < quotaLimit, cùng INSERT Voucher và UNIQUE theo (campaignId, customerId) đối với trạng thái phù hợp. Kiểm tra đúng số hàng và rollback nếu không đạt.
- Giao dịch chuyển từ "đã cấp" sang "đã dùng" không tự hoàn lại quota trừ khi chính sách định nghĩa vậy. Cần phân biệt **voucher đã từng phát** với **voucher đang hiệu lực**: hai bất biến có công thức khác nhau.
- Retry phải dùng requestId ổn định; không tăng count lần nữa. Nếu Voucher ở service độc lập, CampaignQuota cấp token quyền phát một lần, Voucher xác nhận kết quả; retry và xử lý bù không được cấp thêm quyền từ cùng token.
- Nếu chia quota 10.000 thành nhiều phần, tổng quota cấp trước cho các phần phải **không quá 10.000**, và chuyển quota phải ngăn dùng song song ở cả nguồn lẫn đích.
- Dashboard marketing có thể dùng bản sao phân tích với độ trễ; **không lấy số phát từ dashboard để quyết định voucher tiếp theo**.

## 17. Checklist ra quyết định và kết luận

Trước khi cố định ranh giới aggregate, hãy tự trả lời:

- Có viết được bất biến phải đúng **ngay sau commit** bằng dữ liệu và phạm vi định danh cụ thể chưa?
- Đơn vị nào có quyền quyết định cấp tài nguyên hoặc đổi trạng thái? Command có đi qua root đó không?
- Những thành viên nào thực sự cần cùng một quyết định nguyên tử, và phần nào chỉ liên quan qua ID hoặc phục vụ đọc?
- Mọi đường ghi có bảo vệ constraint, version/lock và idempotency; có ngăn việc sửa trực tiếp làm hỏng bất biến không?
- Một transaction phải sửa một hay nhiều root? Nếu nhiều, nguyên tử được bảo đảm bởi cùng DB hay một quy trình đã thiết kế rõ?
- Root có số phần tử và mức tranh chấp phù hợp workload; có đo p99, lock wait và retry thay vì chỉ dựa trực giác không?
- Nếu chia quota hoặc shard, có chứng minh được **tổng quyền cấp** vẫn không vượt giới hạn không?
- Nếu bước tích hợp thất bại hoặc kết quả commit không rõ, trạng thái trung gian, retry, bù và đối soát đã được định nghĩa chưa?
- Cấu trúc vật lý quan hệ/document/đồ thị/phân tích có phục vụ cả bất biến ghi và nhu cầu đọc, không đánh tráo vai trò nguồn sự thật không?

**Kết luận:** Ranh giới aggregate là một **quyết định đánh đổi có cơ sở**. Gộp quá nhiều dữ liệu có thể làm transaction và phiên bản trở thành điểm nghẽn; tách không đúng chỗ có thể làm mất khả năng giữ bất biến. Cách thiết kế bền vững là tìm đúng **điểm phân xử của từng quy tắc**, thu hẹp dữ liệu cần commit chung, thực thi điều kiện bằng transaction/constraint phù hợp và chỉ phân tán quyền quyết định khi có giao thức chứng minh được tính an toàn. Nhờ vậy, mô hình dữ liệu vừa phản ánh nghiệp vụ, vừa kiểm chứng được dưới cạnh tranh thực tế và có khả năng tiến hóa khi tải tăng.
