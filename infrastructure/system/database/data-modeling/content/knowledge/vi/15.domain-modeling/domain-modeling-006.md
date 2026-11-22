# Vòng đời, quyền sở hữu và thao tác làm thay đổi trạng thái

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả **vòng đời** của một thực thể bằng trạng thái, sự kiện và những chuyển trạng thái được phép thay vì chỉ liệt kê cột status.
- Xác định **chủ sở hữu dữ liệu**, aggregate root, người có quyền phát lệnh và hệ thống có thẩm quyền với từng quy tắc.
- Thiết kế **command nghiệp vụ** có điều kiện trước, kết quả sau và lỗi rõ ràng; bảo vệ bất biến khi nhiều tác nhân cùng thao tác.
- Phân biệt **trạng thái lưu trữ**, **trạng thái suy ra theo thời gian**, **lịch sử chuyển trạng thái** và **dữ liệu snapshot**.
- Ánh xạ mô hình vòng đời sang khóa, ràng buộc, chỉ mục, transaction và cơ chế kiểm soát đồng thời.
- Xử lý những thay đổi xuyên aggregate bằng hợp đồng tích hợp, idempotency, sự kiện và các trạng thái trung gian phù hợp.

Trong module **DATABASE_DATA_MODELING**, mục tiêu không phải tạo thật nhiều bảng, mà là chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng, có thể tiến hóa và kiểm chứng. Một entity có ID, quan hệ và các cột vẫn chưa đủ nếu ta không biết **ai được đổi trạng thái**, **đổi bằng thao tác nào**, **điều kiện gì phải đúng** và **dữ liệu lịch sử có được giữ lại không**. Đó là nội dung trọng tâm của bài thuộc chương **Mô hình miền** này.

## 1. Vòng đời trong mô hình miền là gì?

**Vòng đời (lifecycle)** của một thực thể mô tả quá trình từ khi được tạo, qua các trạng thái và hành vi hợp lệ, cho đến khi kết thúc hoặc được lưu trữ theo chính sách. Vòng đời giúp trả lời những câu hỏi không được giải quyết chỉ bằng quan hệ khóa ngoại:

- Một phiếu đã đóng có thể được sửa nội dung không?
- Một lệnh bị gửi lại có khiến trạng thái tiến thêm lần thứ hai không?
- Ai được hủy, ai được phê duyệt, và hủy có được phép sau khi công việc bắt đầu?
- Hệ thống có cần xóa bản ghi khi hoàn tất hay phải lưu lịch sử?
- Khi hai yêu cầu đến đồng thời, yêu cầu nào được phép thắng?

Ví dụ xuyên suốt là **MaintenanceTicket**, phiếu yêu cầu bảo trì một thiết bị trong doanh nghiệp. Người dùng gửi lỗi, bộ phận hỗ trợ phân loại, kỹ thuật viên xử lý và người có thẩm quyền đóng phiếu. Thiết bị và hồ sơ kỹ thuật viên có vòng đời riêng.

Một phiếu có thể đi qua các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> NEW: CreateTicket
    NEW --> TRIAGED: TriageTicket
    TRIAGED --> IN_PROGRESS: StartWork
    IN_PROGRESS --> RESOLVED: ResolveTicket
    RESOLVED --> CLOSED: CloseTicket
    RESOLVED --> IN_PROGRESS: ReopenTicket
    NEW --> CANCELLED: CancelTicket
    TRIAGED --> CANCELLED: CancelTicket
    CLOSED --> [*]
    CANCELLED --> [*]
~~~

Đây là **chính sách minh họa**, không phải luật bất biến cho mọi doanh nghiệp. Trong một quy trình khác, quản trị viên có thể hủy khi đang xử lý, hoặc một phiếu CLOSED được mở lại theo chính sách bảo hành. Nếu nghiệp vụ cho phép, cần thêm command, điều kiện và lịch sử tương ứng thay vì sửa trực tiếp status.

### Trạng thái không thay thế toàn bộ ý nghĩa nghiệp vụ

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| **Danh tính** | ticketId | Nhận diện cùng một Ticket dù trạng thái đổi |
| **Trạng thái** | IN_PROGRESS | Diễn đạt giai đoạn hiện tại của Ticket |
| **Hành vi/command** | ResolveTicket | Đề nghị thực hiện thay đổi có chủ đích |
| **Bất biến** | Chỉ IN_PROGRESS mới được RESOLVED | Điều kiện phải giữ đúng sau thao tác |
| **Sự kiện miền** | TicketResolved | Sự thật về thay đổi đã xảy ra |
| **Thời điểm** | resolvedAt, dueAt | Căn cứ về hạn, điều kiện và lịch sử |
| **Chủ sở hữu** | MaintenanceTicket aggregate trong Service Desk | Có quyền quyết định trạng thái của Ticket |

Một entity có thể có nhiều thuộc tính được thay đổi trong cùng một trạng thái. Ví dụ AssignTechnician thay kỹ thuật viên phụ trách nhưng Ticket vẫn là TRIAGED; không cần tạo một status mới cho mọi thay đổi dữ liệu.

## 2. Tách trạng thái nghiệp vụ, trạng thái suy ra và trạng thái kỹ thuật

### 2.1. Trạng thái nghiệp vụ được lưu

NEW, TRIAGED, IN_PROGRESS, RESOLVED, CLOSED và CANCELLED là tập trạng thái có ý nghĩa trong quy trình bảo trì. Chúng cần được đặt tên theo **ngôn ngữ nghiệp vụ**, định nghĩa rõ ai có thể đưa đối tượng vào trạng thái đó và những trường nào bắt buộc có khi chuyển tới.

Ví dụ: nếu Ticket đã RESOLVED thì phải có resolutionCode hợp lệ. Nếu Ticket IN_PROGRESS thì phải có kỹ thuật viên được phân công. Những ràng buộc này có thể được kiểm tra trong aggregate và hỗ trợ thêm bằng ràng buộc dữ liệu.

### 2.2. Trạng thái suy ra theo thời gian

Giả sử một Ticket có dueAt và hiện ở IN_PROGRESS. Khi đồng hồ vượt dueAt, phiếu đã **trễ hạn SLA** mà không có người dùng ra lệnh chuyển trạng thái. Có thể biểu diễn:

~~~text
overdue = now > dueAt AND status NOT IN (RESOLVED, CLOSED, CANCELLED)
~~~

OVERDUE trong trường hợp này là **trạng thái được suy ra** để cảnh báo hoặc báo cáo, không nhất thiết phải là một giá trị trong cùng enum status. Nếu lưu một cột overdue vật lý, phải có cơ chế cập nhật theo thời gian hoặc chấp nhận độ trễ. Không nên trộn chỉ số theo thời gian với vòng đời nếu hai cơ chế có ngữ nghĩa khác nhau.

Tương tự, một Ticket có thể cùng lúc ở trạng thái IN_PROGRESS và có **mức ưu tiên HIGH**. Priority là thuộc tính phân loại, không nhất thiết là trạng thái vòng đời.

### 2.3. Trạng thái kỹ thuật khác trạng thái nghiệp vụ

Một thông điệp xử lý lỗi có thể ở trạng thái RETRYING hoặc DEAD_LETTER; một outbox event có thể PENDING/SENT. Đó là trạng thái **hạ tầng truyền thông**, không phải Ticket đã hoàn tất hay chưa. Tránh gộp chúng vào status của Ticket, vì điều này làm mô hình miền phụ thuộc chi tiết broker và gây nổ số trạng thái.

Một quy tắc hữu ích: chỉ thêm trạng thái nếu người làm nghiệp vụ có thể giải thích **điều gì đã thay đổi về quyền, nghĩa vụ hoặc khả năng thao tác đối với thực thể**.

## 3. Quyền sở hữu dữ liệu khác quyền thực hiện thao tác

Trong một hệ thống, có ít nhất ba câu hỏi cần phân biệt:

1. **Ai sở hữu sự thật nghiệp vụ?** Aggregate/bounded context nào có thẩm quyền tạo và thay đổi dữ liệu?
2. **Ai được yêu cầu thay đổi?** Người dùng hoặc hệ thống nào được cấp quyền thực hiện command?
3. **Ai chịu trách nhiệm lưu trữ và kiểm soát truy cập?** Database, service, nhóm vận hành và các cơ chế phân quyền nào đang thực thi?

Ví dụ:

| Dữ liệu | Chủ sở hữu miền | Ai có thể yêu cầu | Điểm kiểm soát |
| --- | --- | --- | --- |
| Trạng thái MaintenanceTicket | Service Desk / Ticket aggregate | Người phân loại, kỹ thuật viên, người có quyền đóng theo chính sách | Application authorization + hành vi Ticket |
| Tình trạng Asset | Asset Management / Asset aggregate | Quản lý tài sản, quy trình kiểm kê/bảo trì | Command thuộc Asset Management |
| Hồ sơ Technician | Workforce Management | Quản trị nhân sự, chính kỹ thuật viên theo quyền | API và quyền sở hữu của Workforce |
| Kết quả hóa đơn phí bảo trì | Billing / Invoice aggregate | Billing hoặc quy trình tài chính hợp lệ | Command và transaction của Billing |
| Dữ liệu báo cáo bảo trì | Read model/analytics | Người đọc đã được cấp quyền | Projection và quyền truy vấn |

Service Desk có thể lưu **assetId** và **technicianId**, nhưng không được sửa trực tiếp tình trạng tài sản hoặc hợp đồng lao động thông qua Ticket. Nếu khi hoàn tất phiếu phải đánh dấu Asset đã được kiểm tra, Ticket có thể phát sự kiện hoặc yêu cầu qua API của Asset Management.

**Quyền sở hữu không chỉ là tài khoản kết nối cơ sở dữ liệu.** Việc một service có thể chạy UPDATE lên bảng khác vì cùng database không chứng minh nó được phép thay đổi nghiệp vụ của aggregate đó. Ngược lại, chỉ có ID của một Ticket cũng không cấp quyền xem hoặc sửa; authorization và tenant scope phải được kiểm tra riêng.

### Ranh giới aggregate và quyền ghi

Ticket có thể là aggregate root điều phối việc sửa trạng thái, phân công và ghi nhận kết quả. Những dữ liệu chỉ tồn tại để phục vụ Ticket và phải thay đổi nhất quán với Ticket có thể là thành viên bên trong nó. Asset và Technician thường là aggregate khác có vòng đời riêng, vì vậy Ticket chỉ tham chiếu bằng ID và lưu snapshot nếu cần bảo vệ lịch sử.

Đừng chọn một aggregate chỉ vì có quan hệ một-nhiều trên ERD. Ranh giới phải được giải thích bằng **bất biến nào cần được kiểm tra và commit cùng nhau**.

## 4. Thiết kế command và điều kiện chuyển trạng thái

Tên command nên mô tả **ý định nghiệp vụ**, không phải thay cột:

- CreateTicket — tạo phiếu với assetId, requesterId và mô tả lỗi.
- TriageTicket — phân loại, xác định mức ưu tiên và điều kiện xử lý.
- AssignTechnician — phân công kỹ thuật viên khi trạng thái cho phép.
- StartWork — bắt đầu xử lý khi đã phân công.
- ResolveTicket — ghi mã/biện pháp giải quyết, chuyển tới RESOLVED.
- ReopenTicket — ghi lý do chưa đạt, chuyển RESOLVED về IN_PROGRESS.
- CloseTicket — xác nhận kết thúc từ RESOLVED.
- CancelTicket — hủy phiếu NEW/TRIAGED theo chính sách.

Hãy viết bảng chuyển trạng thái thay vì để client gửi một giá trị status tùy ý:

| Command | Trạng thái cho phép trước | Điều kiện khác | Trạng thái sau |
| --- | --- | --- | --- |
| TriageTicket | NEW | priority hợp lệ; actor có quyền phân loại | TRIAGED |
| AssignTechnician | TRIAGED, IN_PROGRESS | technicianId hợp lệ; có quyền phân công | Không đổi |
| StartWork | TRIAGED | technicianId đã được phân công | IN_PROGRESS |
| ResolveTicket | IN_PROGRESS | resolutionCode không rỗng; actor đủ quyền | RESOLVED |
| ReopenTicket | RESOLVED | Có lý do; vẫn có kỹ thuật viên phù hợp | IN_PROGRESS |
| CloseTicket | RESOLVED | Có xác nhận/kiểm tra kết quả theo chính sách | CLOSED |
| CancelTicket | NEW, TRIAGED | Có lý do; actor được phép hủy | CANCELLED |

**Điều kiện trước (precondition)** là điều kiện để command được chấp nhận. **Điều kiện sau (postcondition)** diễn tả kết quả đúng khi command thành công. Cần định nghĩa cả lỗi: không tồn tại, không có quyền, trạng thái không hợp lệ, xung đột phiên bản, tham chiếu không hợp lệ hoặc phụ thuộc bên ngoài chưa sẵn sàng.

Ví dụ ResolveTicket:

~~~text
Command: ResolveTicket(ticketId, resolutionCode, expectedVersion, requestId)

Precondition:
  - Ticket tồn tại trong tenant hiện tại
  - Actor có quyền resolve Ticket này
  - Ticket đang IN_PROGRESS
  - resolutionCode không rỗng
  - expectedVersion khớp phiên bản hiện tại

Success:
  - Ticket.status = RESOLVED
  - Ticket.resolutionCode được lưu
  - version tăng đúng một lần
  - Có bản ghi lịch sử TicketResolved
  - Sự kiện cần phát được ghi cùng transaction

Failure:
  - Không thay đổi Ticket nửa chừng
  - Trả mã lỗi nghiệp vụ/xung đột rõ ràng
~~~

Một command thành công có thể thay nhiều trường cùng lúc. Vì vậy **thao tác nghiệp vụ là đơn vị nhất quán**, không phải từng lệnh UPDATE riêng lẻ ở controller.

## 5. Ví dụ Java: root tự bảo vệ vòng đời

Ví dụ sau mô hình hóa những chuyển trạng thái chính mà không chứa I/O. Ở ứng dụng thật, việc kiểm quyền actor, truy xuất Asset/Technician và transaction nằm ngoài mã minh họa miền này.

~~~java
import java.util.Objects;
import java.util.UUID;

enum TicketStatus {
    NEW, TRIAGED, IN_PROGRESS, RESOLVED, CLOSED, CANCELLED
}

record TicketId(UUID value) {
    TicketId {
        Objects.requireNonNull(value);
    }
}

record TechnicianId(UUID value) {
    TechnicianId {
        Objects.requireNonNull(value);
    }
}

// Aggregate root: chỉ thao tác qua các phương thức có nghĩa nghiệp vụ.
final class MaintenanceTicket {
    private final TicketId id;
    private TicketStatus status = TicketStatus.NEW;
    private TechnicianId assignedTechnician;
    private String resolutionCode;
    private long version;

    MaintenanceTicket(TicketId id) {
        this.id = Objects.requireNonNull(id);
    }

    void triage() {
        require(TicketStatus.NEW);
        status = TicketStatus.TRIAGED;
    }

    void assign(TechnicianId technicianId) {
        if (status != TicketStatus.TRIAGED
                && status != TicketStatus.IN_PROGRESS) {
            throw new IllegalStateException("Assignment not allowed");
        }
        assignedTechnician = Objects.requireNonNull(technicianId);
    }

    void startWork() {
        require(TicketStatus.TRIAGED);
        if (assignedTechnician == null) {
            throw new IllegalStateException("Technician required");
        }
        status = TicketStatus.IN_PROGRESS;
    }

    void resolve(String code) {
        require(TicketStatus.IN_PROGRESS);
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("Resolution required");
        }
        resolutionCode = code.strip();
        status = TicketStatus.RESOLVED;
    }

    void reopen(String reason) {
        require(TicketStatus.RESOLVED);
        if (reason == null || reason.isBlank()) {
            throw new IllegalArgumentException("Reason required");
        }
        // Lý do mở lại sẽ được lưu trong lịch sử command/event.
        resolutionCode = null;
        status = TicketStatus.IN_PROGRESS;
    }

    void close() {
        require(TicketStatus.RESOLVED);
        status = TicketStatus.CLOSED;
    }

    void cancel(String reason) {
        if (status != TicketStatus.NEW
                && status != TicketStatus.TRIAGED) {
            throw new IllegalStateException("Cancellation not allowed");
        }
        if (reason == null || reason.isBlank()) {
            throw new IllegalArgumentException("Reason required");
        }
        status = TicketStatus.CANCELLED;
    }

    TicketStatus status() { return status; }
    TicketId id() { return id; }
    long version() { return version; }

    private void require(TicketStatus expected) {
        if (status != expected) {
            throw new IllegalStateException(
                "Expected " + expected + ", actual " + status);
        }
    }
}
~~~

Ở đây version là **phiên bản lưu trữ**. Ví dụ chưa có repository nên không tăng version trong từng phương thức; khi persistence lưu thành công theo giao thức khóa lạc quan, repository phải cập nhật phiên bản đồng nhất với object được lưu. Không được hiểu rằng đọc version từ một object in-memory sẽ tự giải quyết hai transaction cạnh tranh.

Một số điểm thiết kế:

- Không công khai setStatus, setResolutionCode hay cho ứng dụng tự sửa trường nội bộ.
- TicketId và TechnicianId là **value object định danh**, không kéo toàn bộ Technician vào Ticket.
- Trạng thái CLOSED và CANCELLED là **kết thúc theo chính sách mẫu**; không có command sửa tùy tiện sau khi kết thúc.
- Lý do hủy/mở lại có thể được lưu trong một lịch sử domain event hoặc bản ghi audit; ví dụ chỉ thể hiện kiểm tra đầu vào.
- Cần phân biệt **domain event** mô tả điều đã xảy ra với **command** yêu cầu thực hiện: TicketResolved chỉ được tạo khi ResolveTicket đã thành công.

Nếu một quy tắc liên quan nhiều aggregate, chẳng hạn kỹ thuật viên không được nhận quá số ca đang hoạt động, Ticket không nên tự cập nhật lịch làm việc của Technician. Chủ sở hữu lịch/khả dụng phải thực hiện bước đặt chỗ hoặc xác nhận phân công theo giao thức riêng.

## 6. Ánh xạ vòng đời sang PostgreSQL

Trong lược đồ minh họa, Service Desk sở hữu Ticket, lịch sử thao tác và outbox. Asset và Technician có thể thuộc hệ thống khác nên Ticket chỉ lưu ID tham chiếu.

~~~sql
CREATE SCHEMA IF NOT EXISTS service_desk;

CREATE TABLE service_desk.maintenance_ticket (
    tenant_id UUID NOT NULL,
    ticket_id UUID NOT NULL,
    asset_id UUID NOT NULL,
    requester_id UUID NOT NULL,
    assigned_technician_id UUID,
    status VARCHAR(16) NOT NULL DEFAULT 'NEW'
        CHECK (status IN (
            'NEW', 'TRIAGED', 'IN_PROGRESS',
            'RESOLVED', 'CLOSED', 'CANCELLED'
        )),
    priority VARCHAR(8) NOT NULL DEFAULT 'NORMAL'
        CHECK (priority IN ('LOW', 'NORMAL', 'HIGH')),
    summary TEXT NOT NULL CHECK (length(trim(summary)) > 0),
    resolution_code TEXT,
    due_at TIMESTAMPTZ,
    status_changed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    PRIMARY KEY (tenant_id, ticket_id),
    CONSTRAINT resolution_required_after_work
        CHECK (
            status NOT IN ('RESOLVED', 'CLOSED')
            OR (resolution_code IS NOT NULL AND length(trim(resolution_code)) > 0)
        ),
    CONSTRAINT technician_required_when_work_started
        CHECK (
            status NOT IN ('IN_PROGRESS', 'RESOLVED', 'CLOSED')
            OR assigned_technician_id IS NOT NULL
        )
);

CREATE TABLE service_desk.ticket_transition_history (
    tenant_id UUID NOT NULL,
    ticket_id UUID NOT NULL,
    version BIGINT NOT NULL,
    command_id UUID NOT NULL,
    from_status VARCHAR(16) NOT NULL,
    to_status VARCHAR(16) NOT NULL,
    actor_id UUID NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reason TEXT,
    PRIMARY KEY (tenant_id, ticket_id, version),
    UNIQUE (tenant_id, command_id),
    FOREIGN KEY (tenant_id, ticket_id)
        REFERENCES service_desk.maintenance_ticket (tenant_id, ticket_id)
);

CREATE TABLE service_desk.outbox_event (
    event_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    aggregate_id UUID NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ
);

-- Tra cứu phiếu chưa hoàn thành theo hạn xử lý trong tenant.
CREATE INDEX ticket_open_by_due
    ON service_desk.maintenance_ticket (tenant_id, due_at)
    WHERE status IN ('NEW', 'TRIAGED', 'IN_PROGRESS');

-- Hàng đợi công việc theo kỹ thuật viên và trạng thái.
CREATE INDEX ticket_assignee_worklist
    ON service_desk.maintenance_ticket
        (tenant_id, assigned_technician_id, status)
    WHERE assigned_technician_id IS NOT NULL;
~~~

Một vài nhận xét:

- **Khóa (tenant_id, ticket_id)** bảo vệ phạm vi tenant. Truy vấn và command cũng phải dùng tenant_id cùng authorization; ID không phải giấy phép truy cập.
- **CHECK** bảo vệ tập trạng thái và hai điều kiện ở cấp hàng: Ticket RESOLVED/CLOSED có mã giải quyết; Ticket IN_PROGRESS trở đi có kỹ thuật viên. CHECK **không** tự kiểm soát thứ tự chuyển trạng thái hoặc người được phép thao tác.
- **Foreign key nội bộ** liên kết lịch sử với Ticket; việc không có FK đến Asset/Technician là lựa chọn khi chúng có chủ sở hữu độc lập, không phải lý do bỏ kiểm tra sự tồn tại/hợp lệ.
- **Lịch sử** có phiên bản và command_id để truy vết thay đổi; trong hệ thống thực, cần định nghĩa dữ liệu nào đủ cho audit, có cần mã sự kiện, before/after snapshot hay thời điểm nhận lệnh riêng không.
- **Outbox** là cơ chế hỗ trợ phát sự kiện tích hợp sau commit; nó khác bảng lịch sử nghiệp vụ. Một event có thể không cần phát ra ngoài, và một thay đổi có thể phát nhiều thông điệp.
- **Index** phục vụ hai kiểu truy vấn cụ thể; tạo chỉ mục theo nhu cầu thực và kiểm tra kế hoạch truy vấn, không tạo chỉ mục trên mọi cột.

Nếu cần báo cáo Ticket quá hạn theo thời gian hiện tại, truy vấn trạng thái đang mở cùng due_at thay vì dựa vào cột overdue dễ bị cũ.

### Trạng thái đã chốt khác thao tác xóa bản ghi

CLOSED, CANCELLED là trạng thái **vòng đời nghiệp vụ**, không đồng nghĩa xóa vật lý. Một Ticket có thể CLOSED từ lâu nhưng vẫn phải được giữ để đối soát, đo thời gian xử lý hoặc đáp ứng quy định lưu trữ. Nếu cần phân tầng lưu trữ, hãy dùng chính sách retention/archive riêng. Không nên biến delete_at thành status hoặc tự động xóa mọi dòng khi một phiếu đóng.

## 7. Một command phải được commit nguyên tử

Giả sử kỹ thuật viên gửi ResolveTicket trong lúc người quản lý có thể đang phân công lại. Cần bảo vệ cả trạng thái và phiên bản:

~~~sql
BEGIN;

-- Repository đã kiểm tra actor có quyền với ticket/tenant.
UPDATE service_desk.maintenance_ticket
SET status = 'RESOLVED',
    resolution_code = :resolution_code,
    status_changed_at = CURRENT_TIMESTAMP,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND ticket_id = :ticket_id
  AND status = 'IN_PROGRESS'
  AND assigned_technician_id IS NOT NULL
  AND version = :expected_version
RETURNING version;

-- Ứng dụng phải kiểm tra đúng một hàng được cập nhật.
-- Nếu 0 hàng: ROLLBACK và xử lý NOT_FOUND / INVALID_STATE /
-- VERSION_CONFLICT theo kiểm tra an toàn phù hợp.
-- :new_version dưới đây là version từ RETURNING.

INSERT INTO service_desk.ticket_transition_history
    (tenant_id, ticket_id, version, command_id,
     from_status, to_status, actor_id, reason)
VALUES
    (:tenant_id, :ticket_id, :new_version, :command_id,
     'IN_PROGRESS', 'RESOLVED', :actor_id, :resolution_code);

INSERT INTO service_desk.outbox_event
    (event_id, tenant_id, aggregate_id, aggregate_version,
     event_type, payload)
VALUES
    (:event_id, :tenant_id, :ticket_id, :new_version,
     'TicketResolved', :payload);

COMMIT;
~~~

Đoạn SQL minh họa **một nhánh thành công**. Ứng dụng không được chạy hai câu INSERT nếu UPDATE trả về 0 hàng. Nếu ghi lịch sử hoặc outbox thất bại, toàn bộ transaction phải rollback, gồm cả UPDATE. Payload outbox và command_id cần được sinh, kiểm tra và truyền từ lớp điều phối phù hợp, không được lấy tùy ý từ client chưa xác thực.

### Khóa lạc quan và trạng thái không thay đổi

Giả sử T1 và T2 cùng đọc Ticket version 5:

1. T1 chạy ResolveTicket với expectedVersion = 5 và commit thành công, version = 6.
2. T2 chạy AssignTechnician với expectedVersion = 5; dù command cho phép ở IN_PROGRESS trong bản sao T2 đã đọc, UPDATE có điều kiện version 5 sẽ thất bại.
3. T2 phải đọc lại Ticket, đánh giá điều kiện nghiệp vụ hiện tại và quyết định có retry theo command mới hay trả xung đột.

Đây là **optimistic locking**. Nếu số người sửa cùng một Ticket rất cao, có thể cân nhắc khóa bi quan, nhưng phải phân tích thời gian chờ, deadlock và thứ tự nắm khóa.

Mọi thao tác ghi có thể ảnh hưởng bất biến, kể cả **AssignTechnician không đổi status**, phải tham gia cơ chế version hoặc khóa chung của Ticket. Nếu có đường UPDATE thẳng bỏ qua root, một cơ chế phiên bản ở command chuẩn không đủ bảo đảm tính nhất quán.

### Idempotency không giống kiểm tra version

Nếu kỹ thuật viên gửi ResolveTicket, server commit thành công nhưng phản hồi mất do mạng, client retry cùng lệnh. Lần retry có thể thấy Ticket đã RESOLVED và nghĩ rằng "trạng thái sai". Điều đó không nhất thiết nghĩa là lần đầu thất bại.

Để phân biệt một retry với **một ý định mới**, dùng commandId/requestId bền vững:

- Với cùng commandId, trả lại kết quả đã xử lý mà không phát lại tác động nghiệp vụ.
- Với commandId khác, kiểm tra trạng thái và phiên bản theo quy tắc bình thường.
- Phải lưu dấu command và kết quả trong phạm vi transaction liên quan, hoặc có giao thức xử lý phục hồi khi hệ thống lỗi giữa chừng.

Unique(tenant_id, command_id) trên lịch sử giúp ngăn ghi trùng bản ghi chuyển trạng thái, nhưng **chưa đủ để bảo đảm trả đúng kết quả của lệnh lặp** trong mọi tình huống (ví dụ command phân công không đổi trạng thái, lệnh bị từ chối, hoặc phản hồi cần chứa thêm dữ liệu). Hệ thống có thể cần một bảng idempotency riêng lưu trạng thái xử lý/kết quả và quy tắc giữ khóa request.

## 8. Thao tác xuyên aggregate: hợp đồng và sự kiện

Khi Ticket RESOLVED, doanh nghiệp có thể muốn cập nhật lịch bảo trì của Asset và gửi thông báo cho người yêu cầu. Đây là hai nghĩa vụ **bên ngoài Ticket**:

~~~mermaid
sequenceDiagram
    participant U as Technician
    participant T as Service Desk / Ticket
    participant B as Event Bus
    participant A as Asset Management
    participant N as Notification

    U->>T: ResolveTicket(ticketId, commandId)
    T->>T: Validate + commit Ticket & outbox
    T-->>U: Ticket RESOLVED
    T->>B: TicketResolved(eventId, ticketId, assetId)
    B-->>A: TicketResolved
    A->>A: Kiểm tra chính sách, cập nhật Asset qua root
    B-->>N: TicketResolved
    N->>N: Gửi thông báo idempotent
~~~

Ticket không tự sửa trực tiếp trạng thái Asset. Asset Management quyết định cách diễn giải TicketResolved, điều kiện để đánh dấu Asset đã được bảo trì và khả năng từ chối nếu Asset đã chuyển chủ hay đang trong quy trình khác.

**Eventual consistency** có thể phù hợp với cập nhật báo cáo hoặc thông báo. Nhưng nếu nghiệp vụ quy định **không thể ResolveTicket trước khi thiết bị vượt qua kiểm định bắt buộc**, ta phải đặt bước xác nhận với Asset Management **trước khi hoàn tất** hoặc dùng trạng thái trung gian như RESOLUTION_PENDING. Không để sự kiện đến sau trở thành cách "hy vọng" một bất biến bắt buộc sẽ đúng.

Các quy tắc tích hợp cần ghi rõ:

| Vấn đề | Quyết định phải có |
| --- | --- |
| Thông điệp đến hai lần | Consumer deduplicate theo eventId hoặc idempotency key |
| Thông điệp đến không đúng thứ tự | Dùng version/sequence của aggregate nguồn và xử lý sự kiện cũ |
| Publisher lỗi sau commit | Outbox được relay và retry, tránh mất sự kiện do cập nhật DB rồi publish rời rạc |
| Consumer lỗi giữa chừng | Retry an toàn, inbox/dedup và dead-letter/reconciliation |
| Bên nhận từ chối thay đổi | Ghi trạng thái xử lý lỗi, bù hoặc gọi quy trình xử lý theo chính sách |
| Chờ bên ngoài quá lâu | Timeout, deadline, trạng thái trung gian và khả năng tra cứu tiến độ |

Không nhầm **trạng thái Ticket** với **trạng thái gửi thông điệp**. Đây là hai vòng đời khác nhau, do hai thành phần khác nhau sở hữu.

## 9. Lịch sử, thời gian và khả năng kiểm toán

Vòng đời không chỉ có giá trị status hiện tại. Đối với bảo trì, cần biết Ticket đã đi qua những giai đoạn nào, ai thực hiện, khi nào và dựa vào lý do gì.

| Dữ liệu | Ý nghĩa | Cách lưu thường gặp |
| --- | --- | --- |
| status | Trạng thái mới nhất | Cột trên aggregate root |
| status_changed_at | Lần thay đổi trạng thái gần nhất | Cột trên root, cập nhật chỉ khi status đổi |
| created_at | Thời gian tạo bản ghi | Cột hệ thống, đồng hồ có thẩm quyền |
| occurred_at | Thời gian sự kiện nghiệp vụ xảy ra | Lịch sử nghiệp vụ, cần định nghĩa nguồn thời gian |
| recorded_at | Thời gian hệ thống nhận/ghi sự kiện | Lịch sử phục vụ đối chiếu độ trễ |
| version | Phiên bản của root | Bảo vệ ghi đồng thời và thứ tự thay đổi |
| actorId / commandId | Ai yêu cầu và yêu cầu nào | Audit/idempotency; phải kiểm quyền |
| reason / resolutionCode | Bối cảnh quyết định | Dữ liệu nghiệp vụ; cần chính sách bảo vệ/retention |

**Thời gian hiệu lực** (*valid time*) và **thời gian ghi nhận** (*transaction/recorded time*) không nhất thiết giống nhau. Ví dụ kỹ thuật viên hoàn thành lúc 14:00 nhưng hệ thống ngoại tuyến đồng bộ dữ liệu lúc 15:30. Nếu báo cáo SLA cần thời điểm thật, cần quy tắc xác thực thời điểm hoàn thành và ghi cả hai dấu thời gian; không thể lấy created_at của message thay cho thời điểm nghiệp vụ mà không suy xét.

Một bảng lịch sử chuyển trạng thái **không tự trở thành event sourcing**. Với event sourcing, sự kiện là nguồn sự thật để tái dựng trạng thái theo quy tắc version và replay; mô hình ở đây dùng hàng Ticket hiện tại làm nguồn ghi chính, lịch sử để truy vết. Outbox lại phục vụ vận chuyển thông điệp tích hợp. Chọn kiến trúc theo nhu cầu, không vì có bảng tên event.

### Sửa sai lịch sử không có nghĩa xóa dấu vết

Giả sử ResolveTicket nhập nhầm resolutionCode. Có thể cần command CorrectResolution hoặc bổ sung sự kiện điều chỉnh với lý do và người phê duyệt, thay vì ghi đè/xóa không dấu vết. Nếu thông tin chứa dữ liệu cá nhân, yêu cầu ẩn danh/xóa phải cân bằng với nghĩa vụ lưu trữ theo chính sách áp dụng; không giữ vô thời hạn tất cả payload chỉ để "audit".

### Kết thúc, lưu trữ và xóa là ba hành vi khác nhau

- **CloseTicket:** thay đổi vòng đời nghiệp vụ sang CLOSED.
- **ArchiveTicket:** chuyển dữ liệu cũ sang lưu trữ ít truy cập, có thể vẫn giữ khả năng tra cứu.
- **Delete/Anonymize:** xóa hoặc khử nhận dạng theo quyền và chính sách dữ liệu, không mặc định xảy ra ngay khi CLOSED.

Nếu thêm deleted_at, phải nêu rõ đó là **dấu xóa mềm của dữ liệu**, không phải một trạng thái công việc mới. Cũng phải kiểm tra tính duy nhất và truy vấn có loại trừ hàng đã xóa mềm hay không.

## 10. Chọn cấu trúc dữ liệu theo vòng đời và quyền sở hữu

| Kiểu lưu trữ | Cách mô hình hóa | Lưu ý |
| --- | --- | --- |
| **Quan hệ** | Ticket root, bảng lịch sử và outbox; FK cho thành viên nội bộ | Transaction, CHECK, UNIQUE, index theo trạng thái/hạn; root phải kiểm soát ghi |
| **Document** | Một document Ticket chứa trạng thái và dữ liệu nghiệp vụ cục bộ, lịch sử có thể tách riêng | Cần biết phạm vi cập nhật nguyên tử; document quá lớn nếu nhúng lịch sử vô hạn |
| **Đồ thị** | Ticket liên kết Asset, Technician, Incident/RootCause qua cạnh | Quan hệ không tự quyết định chủ sở hữu hoặc tính nguyên tử; không nên sửa vòng đời nguồn khác qua một cạnh |
| **Phân tích/cột** | FactTicketTransition, dimension Technician/Asset, snapshot thời gian xử lý | Dùng để đo SLA và xu hướng, không phải nguồn quyết định command khi dữ liệu có độ trễ |

**Vòng đời quan trọng hơn cấu trúc vật lý.** Có thể đặt Ticket và lịch sử ở hai bảng hay một document, nhưng không làm mất yêu cầu mỗi command phải có trạng thái hợp lệ, kiểm soát phiên bản, sự kiện ghi nhận và điểm có thẩm quyền.

Trong phân tích, thời gian ở từng trạng thái có thể được tính từ chuỗi transition. Cần xử lý trạng thái mở (không có thời điểm kết thúc), trường hợp mở lại và thời gian hiệu lực khác thời gian ghi nhận. Không nên tính SLA bằng cách lấy CLOSED - CREATED trong mọi nghiệp vụ, vì thời gian chờ khách hàng hoặc tạm ngưng có thể được miễn trừ theo chính sách.

## 11. Quy trình thực hành để chuyển yêu cầu thành vòng đời

Khi nhận một yêu cầu như "không cho đóng phiếu nếu chưa có kết quả xử lý", hãy đi qua các bước:

1. **Liệt kê thực thể có danh tính và vòng đời:** Ticket, Asset, Technician, Invoice... Không suy luận chỉ từ tên bảng.
2. **Chỉ ra hệ thống sở hữu mỗi sự thật:** Ticket status của Service Desk, tình trạng thiết bị của Asset Management, kết quả thanh toán của Billing.
3. **Ghi trạng thái tối thiểu:** chỉ thêm khi có ý nghĩa nghiệp vụ khác nhau về quyền/hành vi.
4. **Ghi command và actor:** ai được yêu cầu, có phải qua phê duyệt, command có idempotent không?
5. **Lập bảng transition:** trạng thái trước, các điều kiện, trạng thái sau, dữ liệu bắt buộc và thông điệp sau commit.
6. **Phân loại bất biến:** nội bộ root, liên nhiều hàng cùng DB, hoặc xuyên aggregate/service.
7. **Thiết kế storage:** ID, FK có chủ đích, CHECK, version, lịch sử, index và transaction. Xác định snapshot dữ liệu cần giữ.
8. **Kiểm thử cạnh tranh và lỗi:** hai actor sửa cùng lúc, retry cùng commandId, thông điệp trễ, quyền bị thu hồi, hệ thống nguồn không phản hồi.
9. **Định nghĩa kết thúc vòng đời:** đóng, lưu trữ, xóa mềm, xóa vật lý, giữ lịch sử/ẩn danh.

Phần đầu của bước thiết kế là **luật nghiệp vụ**, không phải câu SQL. SQL giúp thực thi những luật đã được hiểu đúng, không thể tự khám phá chúng từ tên cột.

## 12. Bài tập: vòng đời yêu cầu hoàn tiền

**Tình huống:** Một sàn thương mại có RefundRequest gắn với Order và Payment. Người mua gửi yêu cầu hoàn tiền cho một phần đơn đã thanh toán. Nhân viên duyệt, hệ thống gửi lệnh hoàn cho cổng thanh toán, có thể nhận kết quả trễ hoặc lặp. Khi hoàn tiền thành công, yêu cầu kết thúc; khi thất bại có thể thử lại theo chính sách.

### Câu hỏi

1. Đề xuất trạng thái tối thiểu cho RefundRequest và bảng transition. Phân biệt PROCESSING (đã gửi lệnh hoàn và đang chờ kết quả) với REFUNDED và FAILED; xác định trạng thái nào có thể thử lại.
2. Ai sở hữu RefundRequest, Order, Payment? Người mua hoặc nhân viên có quyền **yêu cầu** thao tác nào và ai được ghi kết quả hoàn tiền có thẩm quyền?
3. Viết ba bất biến nội bộ RefundRequest và ít nhất một điều kiện cần phối hợp với Payment hoặc Order.
4. Chọn những dữ liệu phải lưu snapshot (số tiền, tiền tệ, lý do, dòng hàng/đơn giá đã mua) và những ID cần giữ để đối chiếu.
5. Hai tiến trình cùng duyệt một RefundRequest, hoặc cổng gửi hai lần RefundSucceeded, có thể gây hậu quả gì? Đề xuất version, commandId và paymentRefundId để tránh hoàn tiền trùng.
6. Phác thảo bảng RefundRequest và RefundTransitionHistory, kể cả những ràng buộc có thể dùng SQL CHECK/UNIQUE và những điều kiện buộc phải có transaction hoặc tích hợp liên hệ thống.

### Một hướng giải

Một state machine có thể là:

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> APPROVED: ApproveRefund
    REQUESTED --> REJECTED: RejectRefund
    REQUESTED --> CANCELLED: CancelRefund
    APPROVED --> PROCESSING: SubmitRefund
    PROCESSING --> REFUNDED: RefundSucceeded
    PROCESSING --> FAILED: RefundFailed
    FAILED --> PROCESSING: RetryRefund (theo chính sách)
    REFUNDED --> [*]
    REJECTED --> [*]
    CANCELLED --> [*]
~~~

- RefundRequest là aggregate có refundRequestId, orderId, paymentId và amount/currency snapshot. Order và Payment vẫn có người sở hữu riêng.
- RefundRequest không được duyệt nếu yêu cầu bị hủy/từ chối; amount phải dương và trong phạm vi số tiền được hoàn cho phép. Quy tắc **tổng số tiền của nhiều yêu cầu hoàn không vượt khoản thanh toán** cần điểm phân xử ở Payment/Refund ledger có thẩm quyền, không thể được bảo vệ chỉ bằng CHECK trên một RefundRequest riêng lẻ.
- Chỉ trạng thái APPROVED mới được SubmitRefund; RefundSucceeded phải gắn paymentRefundId và kết quả xác thực từ bên xử lý. Retry phải dùng idempotency key phù hợp với cùng ý định hoàn tiền để không tạo giao dịch trùng.
- Lưu lịch sử ai duyệt, khi nào, số tiền, cơ sở tính và kết quả tích hợp. Không thay đổi đơn giá lịch sử khi Catalog cập nhật giá.
- Optimistic locking bảo vệ hai nhân viên duyệt cạnh tranh; outbox/inbox và idempotency bảo vệ lỗi giao tiếp. Đối soát với Payment xử lý trường hợp hệ thống nhận được phản hồi trễ sau timeout.

Đặc biệt, nếu Payment báo thành công nhưng RefundRequest vẫn PROCESSING do consumer tạm lỗi, cần quy trình phục hồi thay vì tự gửi một giao dịch hoàn **mới**. Sự khác biệt giữa "chưa nhận được kết quả" và "chắc chắn chưa thực hiện" có ý nghĩa tài chính quan trọng.

## 13. Các lỗi thường gặp và checklist

| Lỗi thiết kế | Hệ quả | Cách sửa |
| --- | --- | --- |
| Controller cho cập nhật status tùy ý | Bỏ qua precondition và các trạng thái bị cấm | Command miền với bảng transition rõ ràng |
| Trộn OVERDUE với quy trình xử lý | Trạng thái phụ thuộc đồng hồ trở nên cũ | Tính trạng thái suy ra hoặc quản lý cập nhật theo thời gian riêng |
| Một service sửa thẳng bảng của bounded context khác | Không có một chủ sở hữu dữ liệu, khó tiến hóa | Gọi command/hợp đồng qua nguồn có thẩm quyền |
| Chỉ kiểm tra status ở UI | Worker/batch/API khác có thể ghi sai | Bất biến ở miền và đường ghi DB được bảo vệ |
| Ghi Ticket rồi publish event ở transaction khác mà không phục hồi | Mất sự kiện khi crash giữa hai bước | Outbox cùng commit và cơ chế relay/retry |
| Retry không có commandId | Nhân đôi tác động hoặc phát sự kiện sai | Idempotency và kết quả lệnh bền vững |
| Ghi trạng thái nhưng không lưu lịch sử | Không biết ai chuyển, vì sao, thời điểm nào | Transition history/audit có chính sách |
| Xóa bản ghi ngay khi CLOSED | Mất khả năng đối soát và phân tích | Phân biệt đóng, archive, delete/anonymize |
| Cho command bỏ qua tenant hoặc authorization | Rò rỉ và sửa dữ liệu sai tổ chức | Kiểm quyền với tenant và tài nguyên cụ thể |
| Lưu một status cho cả workflow và message relay | Phức tạp và lẫn trách nhiệm | Tách trạng thái miền khỏi trạng thái hạ tầng |

**Checklist trước khi chốt mô hình dữ liệu:**

- Trạng thái có diễn đạt đúng nghiệp vụ, không bị trộn với priority, deadline hay trạng thái broker không?
- Có bảng command/transition nêu rõ điều kiện trước, điều kiện sau, actor và lỗi không?
- Mỗi trường và bất biến có chủ sở hữu rõ ràng, không bị nhiều service sửa tùy tiện không?
- Những biến đổi trong một aggregate có được commit nguyên tử với version/lock và constraint cần thiết không?
- Các thao tác retry, timeout, concurrent edit, thông điệp trùng/đến trễ có được kiểm thử không?
- Có dữ liệu snapshot, lịch sử, actor, thời gian và định danh yêu cầu đủ để truy vết không?
- Có phân biệt kết thúc nghiệp vụ, lưu trữ dài hạn và xóa/ẩn danh theo chính sách không?
- Kiểu lưu trữ và chỉ mục đã phục vụ đúng command, truy vấn, tính nhất quán và khả năng tiến hóa chưa?

**Kết luận:** Mô hình dữ liệu miền không chỉ là tập thực thể có khóa và quan hệ. **Vòng đời** giải thích những trạng thái hợp lệ; **quyền sở hữu** xác định ai có thẩm quyền với dữ liệu; **command** xác định cách thay đổi trạng thái mà vẫn giữ bất biến. Khi kết hợp chúng với transaction, kiểm soát đồng thời, lịch sử, sự kiện và chính sách lưu trữ, ta có một thiết kế rõ ràng, có thể kiểm chứng và đủ linh hoạt để phát triển cùng yêu cầu nghiệp vụ.
