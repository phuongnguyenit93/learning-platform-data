# Quyền đọc log trong Java: bảo vệ dữ liệu, phân quyền và kiểm toán truy cập

## 1. Mục tiêu

**Quyền đọc log** là quyền xem hoặc truy xuất những sự kiện mà ứng dụng và hạ tầng đã ghi lại. Trong hệ thống Java, log có thể xuất hiện ở console, file, container runtime, hệ thống thu thập tập trung, dashboard, công cụ phân tích, kho lưu trữ lâu dài và bản sao phục vụ điều tra.

Log hữu ích để gỡ lỗi và phát hiện sự cố, nhưng **không phải dữ liệu công khai**. Một record tưởng như đơn giản có thể tiết lộ user ID, địa chỉ IP, nội dung request, tên dịch vụ nội bộ, trace ID, tên đối tác, đường dẫn hệ thống, thông tin giao dịch hoặc bí mật bị ghi nhầm. Vì vậy đọc log phải được kiểm soát như đọc dữ liệu có độ nhạy cảm thực tế của log, không chỉ như xem text file.

Sau bài này, bạn sẽ:

1. Phân biệt quyền **xem, truy vấn, tải xuống/xuất, chia sẻ và quản trị/xóa log**.
2. Hiểu nguyên tắc **least privilege**, RBAC, ABAC, phạm vi tenant/môi trường, cấp quyền có thời hạn và cơ chế khẩn cấp.
3. Biết các điểm cần bảo vệ trong ứng dụng Java, filesystem, Kubernetes và hệ thống logging tập trung.
4. Thực hành ví dụ **Java 17 độc lập** về phân quyền đọc theo vai trò, tenant và độ nhạy cảm; hiểu rõ giới hạn của mô phỏng này.
5. Thiết kế audit truy cập, phát hiện hành vi đọc bất thường và quy trình xử lý yêu cầu xem log chứa dữ liệu nhạy cảm.
6. Kiểm thử quyền đọc âm tính để không rò rỉ log qua API, export, backup hoặc dashboard.

## 2. Vì sao quyền đọc log liên quan đến quyền riêng tư?

Một log có thể chứa thông tin của người khác ngay cả khi người ghi log không chủ ý. Ví dụ:

~~~text
2026-11-10T02:14:32Z WARN order-service payment verification failed
userId=u-4821 tenant=tenant-a requestId=req-17
~~~

Record giả định trên đã chứa một **định danh liên kết được với tài khoản** và tên tenant. Nếu log còn ghi email, token, cookie, request body hoặc thông tin sức khỏe, hậu quả đọc trái phép có thể nghiêm trọng hơn.

Một người có quyền xem log của một namespace hoặc tổ chức có thể:

- Xem thông tin của người dùng, khách hàng hoặc tenant khác.
- Học được cấu trúc nội bộ, API, đường dẫn, tên host và thời điểm hoạt động.
- Thu thập token/credential vô tình bị log để tiếp tục truy cập trái phép.
- Xuất số lượng lớn bản ghi ra thiết bị cá nhân hoặc dịch vụ không được phê duyệt.
- Đọc log sự cố bảo mật khi cuộc điều tra còn cần hạn chế thông tin.
- Kết hợp nhiều bản ghi riêng lẻ để suy ra hoạt động hoặc danh tính.

**Nguyên tắc bảo vệ đầu tiên:** không ghi secret hoặc dữ liệu cá nhân không cần thiết. **Nguyên tắc thứ hai:** dù đã có redaction, vẫn phải quản lý quyền đọc. Redaction và access control là hai lớp phòng thủ bổ sung, không thay thế nhau.

Trong một hệ thống ghi log tập trung, **quyền đọc một dòng** có thể ít rủi ro hơn **quyền truy vấn toàn bộ dữ liệu 90 ngày**. Cùng là "read", nhưng quy mô, phạm vi và khả năng trích xuất rất khác nhau.

## 3. Phân biệt các loại quyền trên log

| Hành động | Ý nghĩa | Rủi ro và yêu cầu |
| --- | --- | --- |
| **View** | Xem một trang log đã được giới hạn scope. | Lộ dữ liệu trên màn hình, chụp ảnh, copy. |
| **Search / Query** | Tìm, lọc theo trường và khoảng thời gian. | Có thể mở rộng phạm vi thành hàng triệu record; cần ràng buộc scope ở backend. |
| **Download / Export** | Tạo file CSV/JSON/ZIP hoặc dữ liệu để phân tích ngoài hệ thống. | Dễ nhân bản dữ liệu, vượt retention, phát tán; cần quyền và audit riêng. |
| **Share** | Cấp quyền, liên kết hoặc chuyển kết quả cho người khác. | Vượt phạm vi người được phép xem; link công khai có thể mất kiểm soát. |
| **Stream / Follow** | Xem log liên tục trong thời gian thực. | Có thể thu dữ liệu nhạy cảm mới mà không cần truy vấn lại. |
| **Configure** | Đổi mức log, appender, pipeline, masking hoặc retention. | Có thể làm log chứa thêm dữ liệu hoặc chuyển sang đích khác. |
| **Delete / Modify** | Xóa, thay đổi hoặc điều chỉnh vòng đời bản ghi. | Ảnh hưởng điều tra, tính toàn vẹn và nghĩa vụ lưu giữ. |
| **Manage access** | Cấp, thu hồi hoặc ủy quyền quyền. | Có thể gián tiếp mở toàn bộ dữ liệu; cần kiểm soát cao. |

**Read-only không đồng nghĩa vô hại.** Người chỉ có quyền đọc vẫn có thể copy, chụp màn hình hoặc xuất dữ liệu nếu hệ thống cho phép. Chính sách phải xem cả **phạm vi** và **kênh thoát dữ liệu**.

Một thiết kế tốt tách quyền kỹ thuật **READ**, **EXPORT**, **DELETE** và **MANAGE_ACCESS** thay vì dùng chung vai trò "log administrator". Ngoài ra cần phân biệt quyền xem **log đã mask** với quyền xem **raw log**.

## 4. Nguyên tắc least privilege

**Least privilege (quyền tối thiểu)** nghĩa là một danh tính chỉ có những khả năng cần thiết để hoàn thành nhiệm vụ được giao, trong phạm vi và thời gian cần thiết.

Một yêu cầu xem log nên trả lời được:

- **Ai?** Danh tính người dùng/service account đã được xác thực.
- **Làm gì?** Xem, truy vấn, follow hay export?
- **Dữ liệu nào?** Service, environment, tenant, namespace, sensitivity, thời gian.
- **Vì sao?** Điều tra ticket, vận hành định kỳ, an ninh hoặc audit.
- **Trong bao lâu?** Quyền thường trực hay quyền tạm thời đến một thời điểm?
- **Ai phê duyệt?** Người quản lý dữ liệu hoặc cơ chế được tổ chức ủy quyền.
- **Ai biết việc truy cập?** Có audit trail và tín hiệu giám sát hay không?

Ví dụ, nhân viên hỗ trợ khách hàng có thể cần xem log đã ẩn thông tin nhạy cảm của **một tenant**, nhưng không cần xem raw authentication headers của tất cả tenant. Kỹ sư SRE có thể cần chẩn đoán lỗi infrastructure mà không cần toàn quyền xuất dữ liệu cá nhân. Nhóm an ninh có thể cần quyền cao hơn trong một cuộc điều tra, nhưng điều đó không đồng nghĩa họ tự động được xóa log hoặc cấp quyền cho chính mình.

### 4.1. Ma trận quyền tham khảo

Đây là **policy minh họa**, không phải mặc định có sẵn của Java hay một nền tảng cụ thể:

| Vai trò | Log vận hành đã mask | Log nội bộ chi tiết | Log nhạy cảm có kiểm soát | Export | Quản trị quyền |
| --- | --- | --- | --- | --- | --- |
| **Support** | Đọc theo tenant/ticket được giao | Không | Không | Không mặc định | Không |
| **Developer** | Đọc dev/test và phạm vi production được cấp tạm | Có trong môi trường được phép | Không mặc định | Theo phê duyệt | Không |
| **SRE** | Đọc service/environment phụ trách | Đọc theo nhiệm vụ | Cần quy trình bổ sung | Tách quyền export | Không mặc định |
| **Security investigator** | Theo phạm vi vụ việc | Theo phạm vi vụ việc | Chỉ khi được phê duyệt | Có kiểm soát/ticket | Không mặc định |
| **Platform administrator** | Theo nhiệm vụ quản trị | Không tự động có quyền xem dữ liệu tenant | Không mặc định | Không mặc định | Quản trị cơ chế, có phân tách nhiệm vụ |
| **Service account / log shipper** | Thường chỉ **ghi/chuyển tiếp**, không cần đọc truy vấn | Không áp dụng | Không áp dụng | Không | Không |

Nếu một tổ chức có ràng buộc bảo mật khác, ma trận phải được điều chỉnh theo phân loại dữ liệu, hợp đồng, chính sách nội bộ và pháp luật áp dụng. Không coi nhãn chức danh như một bằng chứng đủ để cấp toàn quyền.

### 4.2. Phạm vi quyền có nhiều chiều

Một quyết định READ đúng cần xét **nhiều điều kiện cùng lúc**:

~~~text
allow =
    authenticated_identity
    AND authorized_action
    AND permitted_service
    AND permitted_environment
    AND permitted_tenant
    AND permitted_classification
    AND permitted_time_window
    AND approval_valid_if_required
~~~

Đây là mô hình logic, không phải cú pháp của framework. Quan trọng là **không chỉ kiểm tra role**. Vai trò SECURITY ở tenant A không nên tự cho phép xem log tenant B nếu không có quyền cụ thể.

Một người có quyền đọc log ở dev không tự có quyền đọc log production. Một token có quyền query không nhất thiết được cấp quyền export. Mỗi yêu cầu phải được kiểm tra lại tại backend.

## 5. Authentication, authorization, audit: ba việc khác nhau

- **Authentication (xác thực):** xác định ai đang truy cập, thông thường qua SSO/OIDC, service identity, mTLS hoặc cơ chế phù hợp.
- **Authorization (ủy quyền):** xác định danh tính đó có được thực hiện hành động cụ thể trên log cụ thể hay không.
- **Auditing (kiểm toán):** ghi lại ai đã yêu cầu quyền gì, đối tượng/phạm vi nào, khi nào và kết quả allow/deny.

Một dashboard có nút "Ẩn log nhạy cảm" chỉ là UI. **Authorization phải được thực thi tại dịch vụ truy vấn hoặc storage API**, không chỉ bằng cách ẩn nút ở frontend. Nếu API vẫn trả raw data, người dùng có thể gọi API trực tiếp.

Không tin biến userId/role/tenant gửi từ trình duyệt làm căn cứ cấp quyền. Backend phải lấy principal từ token/session đã xác thực và kiểm tra token issuer, audience, expiry, phạm vi và quyền theo cấu hình an toàn.

### 5.1. Fail closed, không "bỏ qua kiểm tra khi lỗi"

Khi không xác thực được, không nhận được policy, không xác định tenant hoặc không có dữ liệu approval cần thiết, mặc định **DENY**. Không dùng nhánh "Nếu policy server timeout thì cho đọc tạm" đối với raw log chứa thông tin nhạy cảm.

Thông báo deny không nên lộ nội dung record, raw token, tên người dùng khác hay chi tiết tồn tại/không tồn tại của một tenant không được phép xem. Backend vẫn cần ghi audit nội bộ đủ để điều tra.

### 5.2. Quyền có thời hạn và break-glass

Một quy trình **just-in-time access** có thể yêu cầu:

1. Người yêu cầu nêu ticket/vấn đề, service, tenant, môi trường, loại dữ liệu.
2. Hệ thống hoặc người có thẩm quyền phê duyệt.
3. Cấp quyền hẹp trong thời gian định trước.
4. Audit mọi truy vấn/đợt export theo policy.
5. Tự thu hồi quyền khi hết hạn, hoàn tất công việc hoặc khi phát hiện vi phạm.

**Break-glass** là quyền khẩn cấp, không phải vai trò mặc định để né RBAC. Phải có điều kiện kích hoạt, thời hạn, lý do, cảnh báo và review sau sự kiện. Không tạo tài khoản chia sẻ không thể truy danh tính cá nhân.

## 6. Ví dụ Java 17 độc lập: kiểm tra quyền xem và export

Đoạn mã sau minh họa **server-side access policy** dựa trên:

- Danh tính actor.
- Tenant của actor và tenant của log.
- Vai trò (SUPPORT, SRE, SECURITY).
- Mức phân loại của bản ghi (GENERAL, INTERNAL, RESTRICTED).
- Hành động VIEW hay EXPORT.
- Quyền phê duyệt export, ở đây được mô phỏng bằng cờ đã cấp từ nguồn đáng tin cậy.

Trong demo, SUPPORT chỉ đọc GENERAL, SRE đọc GENERAL/INTERNAL, SECURITY đọc mọi mức **trong tenant mình được cấp**. Export chỉ được phép cho SECURITY đã có phê duyệt. Tất cả yêu cầu đều để lại một dòng audit; khi bị từ chối **không trả message**.

Đặt tên file **LogAccessDemo.java**:

~~~java
public final class LogAccessDemo {

    enum Role {
        SUPPORT, SRE, SECURITY
    }

    enum Classification {
        GENERAL, INTERNAL, RESTRICTED
    }

    enum Action {
        VIEW, EXPORT
    }

    record Principal(
            String id,
            String tenant,
            Role role,
            boolean exportApproved) {
    }

    record LogEntry(
            String id,
            String tenant,
            Classification classification,
            String message) {
    }

    static boolean isAllowed(
            Principal actor, LogEntry entry, Action action) {
        // Khong cho phep doc cheo tenant.
        if (!actor.tenant().equals(entry.tenant())) {
            return false;
        }

        // Xuat du lieu la quyen rieng, khong suy ra tu VIEW.
        if (action == Action.EXPORT) {
            return actor.role() == Role.SECURITY
                    && actor.exportApproved();
        }

        return switch (actor.role()) {
            case SUPPORT ->
                    entry.classification() == Classification.GENERAL;
            case SRE ->
                    entry.classification() != Classification.RESTRICTED;
            case SECURITY -> true;
        };
    }

    static void access(
            Principal actor, LogEntry entry, Action action) {
        boolean allowed = isAllowed(actor, entry, action);

        // Audit dung dinh danh/decision, khong ghi raw message.
        System.out.printf(
                "AUDIT actor=%s action=%s event=%s decision=%s%n",
                actor.id(), action, entry.id(),
                allowed ? "ALLOW" : "DENY");

        if (allowed) {
            System.out.printf(
                    "%s event=%s message=%s%n",
                    action, entry.id(), entry.message());
        } else {
            System.out.println("ACCESS DENIED");
        }
    }

    public static void main(String[] args) {
        Principal support = new Principal(
                "support-a", "tenant-a", Role.SUPPORT, false);
        Principal sre = new Principal(
                "sre-a", "tenant-a", Role.SRE, false);
        Principal security = new Principal(
                "security-a", "tenant-a", Role.SECURITY, true);

        LogEntry general = new LogEntry(
                "ev-1", "tenant-a", Classification.GENERAL,
                "service started");
        LogEntry internal = new LogEntry(
                "ev-2", "tenant-a", Classification.INTERNAL,
                "retry count=2");
        LogEntry restricted = new LogEntry(
                "ev-3", "tenant-a", Classification.RESTRICTED,
                "risk event: sensitive fields redacted");
        LogEntry otherTenant = new LogEntry(
                "ev-4", "tenant-b", Classification.GENERAL,
                "another tenant event");

        access(support, general, Action.VIEW);
        access(support, restricted, Action.VIEW);
        access(sre, internal, Action.VIEW);
        access(sre, restricted, Action.VIEW);
        access(security, restricted, Action.VIEW);
        access(security, otherTenant, Action.VIEW);
        access(security, restricted, Action.EXPORT);
        access(sre, internal, Action.EXPORT);
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac LogAccessDemo.java
java LogAccessDemo
~~~

**stdout xác định**:

~~~text
AUDIT actor=support-a action=VIEW event=ev-1 decision=ALLOW
VIEW event=ev-1 message=service started
AUDIT actor=support-a action=VIEW event=ev-3 decision=DENY
ACCESS DENIED
AUDIT actor=sre-a action=VIEW event=ev-2 decision=ALLOW
VIEW event=ev-2 message=retry count=2
AUDIT actor=sre-a action=VIEW event=ev-3 decision=DENY
ACCESS DENIED
AUDIT actor=security-a action=VIEW event=ev-3 decision=ALLOW
VIEW event=ev-3 message=risk event: sensitive fields redacted
AUDIT actor=security-a action=VIEW event=ev-4 decision=DENY
ACCESS DENIED
AUDIT actor=security-a action=EXPORT event=ev-3 decision=ALLOW
EXPORT event=ev-3 message=risk event: sensitive fields redacted
AUDIT actor=sre-a action=EXPORT event=ev-2 decision=DENY
ACCESS DENIED
~~~

**Giải thích kết quả:**

- SUPPORT xem được ev-1 vì GENERAL, nhưng bị từ chối ev-3 vì RESTRICTED.
- SRE xem được ev-2 INTERNAL, không được xem ev-3 RESTRICTED.
- SECURITY xem ev-3 cùng tenant; nhưng **không xem được ev-4** vì đó là tenant khác.
- SECURITY được EXPORT ev-3 vì cờ phê duyệt export; SRE không được suy ra EXPORT chỉ vì họ có quyền VIEW ev-2.
- Mỗi yêu cầu tạo dòng AUDIT **không chứa message**. Khi DENY, hệ thống chỉ in ACCESS DENIED.
- Switch expression, record và enum đều tương thích JDK 17; chương trình không có dependency ngoài, I/O mạng, file hoặc thời gian thực nên stdout ổn định.

### Giới hạn bảo mật của ví dụ

Đây là **mô phỏng minh họa chính sách**, không phải một hệ thống IAM production:

1. Principal đang được tạo cứng trong main; ứng dụng thực phải xác thực token/session và nhận role/scope từ nguồn đáng tin cậy. **Không lấy role hoặc exportApproved từ tham số client gửi**.
2. Trường tenant/classification trong event phải được tạo và bảo vệ bởi pipeline có thẩm quyền. Không tin client tự gắn nhãn GENERAL cho dữ liệu nhạy cảm.
3. In một dòng "AUDIT" trên stdout không bảo đảm audit bền vững, chống sửa hoặc độc lập với dữ liệu được bảo vệ. Production cần audit trail và retention riêng.
4. Hàm access không thực sự tạo file export. Với export thật, phải kiểm tra approval, phạm vi, dung lượng, thời hạn tải về và kiểm soát điểm đến; cần audit riêng.
5. Chỉ có ba mức classification để học. Hệ thống thực có thể cần nhiều điều kiện hơn: service, environment, ticket, purpose, time window, geographic policy và field-level redaction.
6. Cần kiểm tra **ở mọi API trả dữ liệu**, bao gồm phân trang, chi tiết event, query aggregator, streaming, saved search và export. Một API quên gọi policy vẫn có thể làm lộ log.

**Mẫu quan trọng:** việc từ chối phải diễn ra **trước khi raw record được gửi qua mạng tới người không có quyền**. Không thể tải toàn bộ raw log về browser rồi mới ẩn những dòng không nên xem.

## 7. RBAC và ABAC trong thực tế

**RBAC (role-based access control)** ánh xạ vai trò đến quyền, ví dụ Support được VIEW masked logs, SRE được QUERY service họ vận hành. Nó dễ quản trị khi có nhóm nhân sự rõ ràng.

**ABAC (attribute-based access control)** bổ sung điều kiện theo thuộc tính actor, tài nguyên và ngữ cảnh: tenant, classification, service, môi trường, purpose, ticket ID, thời gian, nguồn mạng hoặc tình trạng phê duyệt.

Trong log platform đa tenant, **RBAC + ABAC** thường phù hợp hơn một trong hai cơ chế riêng lẻ:

~~~text
Actor:
  authenticated id, role, assigned tenant(s), expiration
             │
             ▼
Request:
  action, service, environment, tenant, time window
             │
             ▼
Log resource:
  tenant, classification, owner, storage scope
             │
             ▼
Authorization policy
        ┌────┴─────┐
      ALLOW       DENY
        │           │
        ▼           ▼
   Filter/query   No data
   + redact      returned
        └────┬─────┘
             ▼
          Audit
~~~

Cần tránh lỗ hổng **IDOR/BOLA**: nếu endpoint cho phép chọn tenant bằng query string, backend phải so sánh với tenant được cấp cho principal. Một URL hoặc filter như tenant=tenant-b **không thể tự mở rộng quyền**.

### 7.1. Authorization ở đâu?

Đặt kiểm tra ở **server-side enforcement point**, trước lệnh query hoặc retrieval trả raw data. Phía storage hoặc log backend cũng nên có quyền tối thiểu thực tế: không dùng một backend service account siêu quyền rồi chỉ dựa vào frontend check.

Ví dụ API có thể giới hạn scope ở query:

~~~text
GET /logs?service=orders&tenant=tenant-a
~~~

Nhưng backend phải tự xác định **tenant-a có nằm trong phạm vi được cấp** hay không, giới hạn service/time range và tối thiểu hóa fields được trả. Không chấp nhận cách:

~~~text
Frontend chỉ hiện tenant-a
Backend lại chấp nhận tenant-b nếu client tự sửa request
~~~

Đây là mô tả lỗi authorization, không phải endpoint có thật cần dùng.

### 7.2. Cấp quyền theo từng field

Không phải ai được xem log cũng cần xem cùng một nội dung. Ví dụ hỗ trợ khách hàng có thể thấy:

~~~json
{
  "event": "payment.failed",
  "tenant": "tenant-a",
  "request_id": "req-17",
  "result": "DECLINED",
  "account_number": "[REDACTED]"
}
~~~

Nhóm xử lý sự cố được phê duyệt có thể được xem thêm thông tin chẩn đoán. Tuy nhiên không nên lưu raw secret chỉ để dùng cơ chế "hiện/ẩn" tại dashboard. Cách an toàn hơn là **không ghi secret từ nguồn**, tách các dữ liệu thật sự cần bảo mật vào hệ thống có kiểm soát riêng.

Redaction tại giao diện không đủ nếu network response, export endpoint hoặc saved query vẫn chứa raw field. Nên thực hiện redaction trước khi dữ liệu vượt sang principal không có quyền.

## 8. Đọc file log trên máy chủ: quyền hệ điều hành

Ứng dụng Java có thể ghi ra file bằng JUL FileHandler, Logback FileAppender/RollingFileAppender, Log4j2 RollingFile hoặc backend tương tự. Khi log là file, **quyền đọc do hệ điều hành và filesystem thực thi**, không phải do riêng SLF4J hay một dòng logger.info() quyết định.

### 8.1. Ví dụ POSIX/Linux

Một chính sách tham khảo:

- User chạy app là **appuser** và cần ghi log.
- Group đọc log được phép là **logreaders**.
- Người dùng khác không được đọc.
- Thư mục chứa log chỉ được truy cập bởi những danh tính được phép.

Có thể diễn đạt policy bằng permission bits:

~~~text
Directory: drwxr-x---  (750)
Log file:  -rw-r-----  (640)
Owner:     appuser
Group:     logreaders
~~~

Ý nghĩa:

- Với file **640**, owner có read/write; group chỉ read; others không có quyền.
- Với directory **750**, owner có read/write/search; group có read/search, others không thể traverse vào thư mục.
- Quyền **x (search/traverse) trên directory** cần thiết để mở file bên trong; chỉ đặt read cho file mà không cho traverse thư mục vẫn có thể bị từ chối.
- Đây là ví dụ quyền cơ bản, chưa bao gồm POSIX ACL, user namespace, root/capabilities, container mount và quyền trên các thư mục cha.

Các lệnh sau **chỉ minh họa** trên một máy Linux đã có đúng user/group và file; không chạy nguyên văn trên production khi chưa xác nhận owner, process và deployment:

~~~bash
# Kiểm tra quyền và owner trước khi thay đổi.
ls -ld /var/log/order-service
ls -l /var/log/order-service/application.log

# Ví dụ thay đổi permission bits, cần quyền phù hợp.
chmod 750 /var/log/order-service
chmod 640 /var/log/order-service/application.log
~~~

Không dùng **chmod 777** hoặc đặt thư mục log trong web root để “chữa lỗi permission”. Điều đó có thể mở rộng khả năng đọc và sửa log ngoài ý muốn.

Cần kiểm soát **umask**, owner/group được đặt khi tạo file, cấu hình file rotation và quyền của file mới sau rollover. Một file log hôm nay là 640 nhưng file rotate ngày mai là 644 vẫn gây rò rỉ. Tốt nhất cấp quyền an toàn **từ lúc file được tạo**, thay vì tạo file quá rộng rồi mới sửa.

### 8.2. Java NIO và quyền POSIX

Java 17 có API **PosixFilePermissions** khi filesystem hỗ trợ POSIX permission view. Đoạn mã dưới đây chỉ là **minh họa tích hợp** trong ứng dụng có sẵn Path và file log; nó **không tự chạy độc lập**:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.PosixFilePermissions;

// Chỉ áp dụng trên filesystem hỗ trợ PosixFileAttributeView.
Path logPath = Path.of("/var/log/order-service/application.log");
Files.setPosixFilePermissions(
        logPath,
        PosixFilePermissions.fromString("rw-r-----"));
~~~

Một hệ filesystem không hỗ trợ POSIX, ví dụ môi trường Windows thông dụng, có thể ném **UnsupportedOperationException**. Windows thường dùng **NTFS ACL**; không coi chuỗi "rw-r-----" là cách phân quyền phổ quát.

**Quan trọng:** sửa permission sau khi file đã được tạo không xóa được mọi rủi ro do một khoảng thời gian ban đầu quyền quá rộng. Trong production, ưu tiên file/directory creation policy, quyền của user chạy app và hạ tầng quản lý filesystem. Ngoài ra, một process chạy bằng quyền cao hoặc account khác vẫn có thể truy cập thông qua cơ chế hệ điều hành; kiểm thử theo **danh tính thực**, không chỉ nhìn output ls.

### 8.3. Đừng cho người đọc quyền viết hoặc quản trị

Nhóm hỗ trợ xem log thường chỉ cần read/search, không cần:

- Sửa hoặc xóa file log.
- Thay đổi owner/group, ACL hoặc policy rotate.
- Đổi cấu hình ghi log để bật DEBUG và làm phát sinh dữ liệu nhạy cảm.
- Truy cập thư mục chứa database, secret hoặc cấu hình ngoài phạm vi.

Nếu ứng dụng ghi file bằng user appuser, log shipper có thể cần đọc file để chuyển sang collector. Điều đó không có nghĩa tài khoản log shipper cần quyền sửa file hoặc đọc mọi thư mục của host.

## 9. Container và Kubernetes: quyền xem stdout không nằm trong Java API

Trong hệ thống container, ứng dụng thường ghi ra stdout/stderr; kubelet/container runtime lưu và phục vụ log theo cơ chế nền tảng. **Ai gọi được kubectl logs** được kiểm soát bởi quyền truy cập Kubernetes API và những cơ chế liên quan, không phải Logger.setLevel() trong Java.

### 9.1. Pod log là một subresource

Trong Kubernetes RBAC, log của Pod là subresource **pods/log**. Với một Pod cụ thể trong namespace, thao tác đọc log thường cần verb **get** trên **pods/log**. Nếu dùng lệnh tự tìm Pod bằng tên hoặc selector, có thể cần thêm quyền **get/list** Pod để tìm đối tượng.

Ví dụ Role chỉ cấp quyền xem Pod metadata và Pod logs trong namespace **orders-staging**, không cấp create/update/delete:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: orders-log-reader
  namespace: orders-staging
rules:
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list"]
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get"]
~~~

Để Role có hiệu lực cho một nhóm danh tính đã xác thực, cần **RoleBinding** phù hợp. Ví dụ YAML minh họa:

~~~yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: orders-log-reader-binding
  namespace: orders-staging
subjects:
  - kind: Group
    name: staging-log-readers
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: orders-log-reader
  apiGroup: rbac.authorization.k8s.io
~~~

Đây là manifest minh họa. Nhóm **staging-log-readers** phải tồn tại trong cơ chế identity của cluster và namespace phải phù hợp. Khi áp dụng thực tế, cần kiểm tra quyền quản trị hiện có, chính sách nhóm, các RoleBinding/ClusterRoleBinding khác và admission controls.

**Cảnh báo phạm vi:** Role trên không giới hạn riêng deployment "orders"; nó cho phép đọc log của **những Pod phù hợp trong toàn namespace orders-staging** theo quyền đã cấp. Kubernetes RBAC không tự giới hạn pods/log theo label selector chỉ vì tên Role chứa "orders". Nếu nhiều tenant chia sẻ namespace và cần cách ly mạnh, hãy thiết kế namespace/identity và cơ chế truy vấn riêng tương ứng.

### 9.2. Kiểm tra quyền thực tế

Ví dụ cho danh tính hiện tại đã kết nối tới đúng cluster:

~~~bash
kubectl auth can-i get pods/log -n orders-staging
kubectl auth can-i list pods -n orders-staging
~~~

Lệnh đầu hỏi người gọi có quyền **get pods/log** trong namespace; lệnh thứ hai hỏi có quyền liệt kê Pod hay không. Kết quả **yes/no** phụ thuộc kubeconfig, credentials và các authorization rules đang áp dụng. Một lệnh can-i đơn lẻ không thay thế test end-to-end việc người dùng có thật sự xem được nội dung nào; còn có namespace, container, token, policy và hệ thu thập phía sau.

Lệnh xem log minh họa:

~~~bash
kubectl logs -n orders-staging pod/order-service-abc123
~~~

Tên Pod chỉ là ví dụ; phải dùng tên thật. Với nhiều container có thể cần **-c**; **-f** là follow, mang rủi ro thu thập dữ liệu liên tục. Không gửi kubeconfig hoặc bearer token trong câu lệnh chia sẻ.

### 9.3. Các đường đọc khác không đi qua kubectl logs

Ngay cả khi một người không có quyền pods/log, họ có thể được cấp quyền khác tới:

- Dashboard log tập trung (Loki, Elastic, OpenSearch hoặc nền tảng tương đương).
- Log files trên node hoặc volume, nếu có quyền hạ tầng phù hợp.
- Container runtime hoặc công cụ CI/CD.
- Bộ nhớ lưu trữ, object storage, snapshot hoặc backup.
- Dịch vụ support xuất log để gửi qua ticket.

Ngược lại, cấp quyền **pods/log** không tự cho họ quyền query mọi index của hệ thống log tập trung. Muốn kiểm soát quyền đọc thật sự cần **kiểm kê mọi đường truy cập đến cùng dữ liệu**. RBAC ở một nơi không bảo vệ bản sao xuất sang nơi khác.

## 10. Quyền đọc log tập trung và tài khoản dịch vụ

Một kiến trúc thường gặp:

~~~text
Java applications
        │
        ▼
  stdout / file
        │
        ▼
  agent / collector
        │
        ▼
  central log storage
        │
     ┌──┴──────────────┬───────────────┐
     ▼                 ▼               ▼
 dashboards         query API       export/archive
     │                 │               │
     └────── authn + authz + audit ─────┘
~~~

Các định danh/permission nên tách:

- **Application producer**: quyền ghi log vào local output, không cần query toàn bộ dữ liệu lịch sử.
- **Log shipper/exporter**: quyền gửi dữ liệu vào endpoint/namespace được chỉ định; không cần quyền tìm kiếm tất cả log hay xóa index.
- **Analyst/Support**: quyền đọc dữ liệu theo service/tenant/time range, thường là bản đã redact.
- **Security investigator**: quyền có điều kiện trên log nhạy cảm phục vụ vụ việc, thời hạn và audit.
- **Platform operator**: quyền quản trị hạ tầng/pipeline theo nhiệm vụ; không tự suy ra quyền raw log mọi tenant.
- **Storage administrator**: quyền quản trị index, retention, backup; nếu có thể truy cập nội dung thì đó phải được coi là đường đọc và kiểm soát tương ứng.

**Đừng dùng cùng một API key quyền admin cho appender ghi log và dashboard truy vấn.** Nếu application bị chiếm quyền, key siêu quyền biến sự cố ở một service thành khả năng đọc/xóa log của toàn hệ thống.

### 10.1. Tách môi trường

Dev, test, staging và production phải có policy đọc rõ ràng. Người có quyền dev không tự có quyền đọc production; tài khoản CI không nên dùng quyền đọc raw production logs để chạy test. Có thể phân vùng theo tenant, namespace, index, project hoặc account tùy công nghệ, nhưng cần đảm bảo **cách ly thực**, không chỉ đặt environment=prod trong mỗi record.

Một search query có filter tenant chưa chắc đủ nếu user vẫn có thể xóa filter đó. Hãy áp dụng scope tại tầng cấp quyền dữ liệu hoặc query service không thể bypass bằng cách chỉnh URL.

### 10.2. Saved search, dashboard và export

Một dashboard có thể tự động chia sẻ dữ liệu qua:

- Public link hoặc embedded iframe.
- Scheduled email/PDF/CSV.
- API key được gắn cứng trong client.
- Saved query với quyền được kế thừa không đúng.
- Download button xuất nhiều trường hơn bản đang hiển thị.
- Cache/CDN hoặc object storage chứa file export.

Cần kiểm tra **quyền xem dashboard không đồng nghĩa quyền query/export raw log**. Nếu một report được gửi cho người không có quyền hệ thống gốc, chính report đã trở thành **bản sao dữ liệu mới** và cần chính sách chia sẻ/lưu giữ riêng.

## 11. Audit hành vi đọc log

Đọc log có thể là hoạt động thường ngày, nhưng cũng có thể là hành vi tra cứu dữ liệu trái phép. Một **audit trail cho log access** nên ghi đủ để chứng minh ai đã làm gì mà không lặp lại dữ liệu nhạy cảm.

Những thuộc tính hữu ích:

| Trường | Ý nghĩa |
| --- | --- |
| **actor_id** | Danh tính đã xác thực, không dùng tên tự khai từ request. |
| **action** | VIEW, QUERY, FOLLOW, EXPORT, SHARE, MANAGE_ACCESS. |
| **target_scope** | Service, tenant, environment, index, classification hoặc event IDs phù hợp. |
| **time_range** | Cửa sổ dữ liệu được truy vấn. |
| **request_time / result** | Khi nào và ALLOW/DENY/ERROR. |
| **query_id** | Mã truy vấn để liên kết audit với request, tránh ghi nguyên câu query chứa PII. |
| **purpose / ticket** | Lý do, ticket hoặc approval tương ứng khi policy yêu cầu. |
| **record_count / export_size** | Quy mô truy cập/xuất dữ liệu. |
| **network/device context** | Thông tin được phép thu thập để điều tra, không quá mức cần thiết. |

Ví dụ **một sự kiện audit đã được tối thiểu hóa**:

~~~json
{
  "actor_id": "security-a",
  "action": "EXPORT",
  "scope": "tenant-a/orders-prod/restricted",
  "query_id": "qry-428",
  "ticket": "INC-104",
  "result": "ALLOW",
  "record_count": 6
}
~~~

Đây là JSON minh họa, không chứa dữ liệu raw log. Hệ thống thật cần bổ sung timestamp, định danh request, thời gian truy cập và thông tin policy tương ứng. Không ghi access token, mật khẩu hoặc toàn bộ dữ liệu đã truy vấn vào audit event.

### 11.1. Audit không chỉ cho DENY

Các truy vấn hợp lệ có thể vẫn rủi ro nếu phạm vi quá rộng hoặc hành vi khác thường. Theo dõi:

- Số lượng record export lớn bất thường.
- Truy vấn nhiều tenant trong một thời gian ngắn.
- Các lần truy cập ngoài giờ hoặc từ vị trí/thiết bị khác thường theo chính sách.
- Tăng đột biến truy vấn dữ liệu nhạy cảm sau khi role thay đổi.
- Dùng tài khoản dịch vụ để truy vấn ngoài chức năng đã được phép.
- Tăng số lần DENY có liên hệ cùng actor hoặc cùng nhóm resources.

Tránh viết audit truy cập chỉ vào **chính hệ thống log mà người bị điều tra có quyền sửa/xóa**. Nếu cần bảo đảm cao, hãy lưu audit trail ở ranh giới tin cậy riêng, có quyền ghi và đọc hạn chế, retention/monitoring phù hợp.

### 11.2. Không gây vòng lặp logging

Nếu mỗi lần đọc audit log lại ghi vào cùng audit log và hệ thống viewer quét liên tục, có thể tạo nhiễu hoặc vòng lặp. Thiết kế audit pipeline riêng, phân loại sự kiện tự động và kiểm thử đường đọc. Không tắt audit toàn bộ chỉ để tránh volume; có thể đặt chính sách sampling/aggregation cho hoạt động kỹ thuật ít nhạy cảm nếu được phê duyệt, nhưng các event truy cập nhạy cảm phải đáp ứng yêu cầu lưu vết.

## 12. Quyền riêng tư ở các bản sao và vòng đời dữ liệu

Giữ log trong storage chính có RBAC tốt là chưa đủ nếu **bản sao** nằm ngoài phạm vi kiểm soát.

Các bản sao cần tính đến:

- Bản dump do người điều tra tải xuống.
- File tạm khi gửi log qua support ticket.
- Attachments trong email, chat hoặc issue tracker.
- CI build artifacts chứa stdout hoặc test logs.
- Snapshot của storage, backup và archive.
- File trên máy local, ổ đĩa cá nhân hoặc bộ nhớ tạm của script phân tích.
- Cache của dashboard, proxy hoặc API gateway.

Với mỗi bản sao phải biết **ai được đọc, ở đâu, khi nào xóa, cách thu hồi chia sẻ và có mã hóa khi lưu/truyền hay không**.

### 12.1. Retention và xóa

Thời gian lưu log phụ thuộc mục đích, chính sách nội bộ, hợp đồng và pháp luật áp dụng. Không có một con số retention chung đúng cho mọi ứng dụng Java. Không lưu vô hạn chỉ vì storage rẻ; cũng không xóa sớm dữ liệu đang được yêu cầu bảo toàn phục vụ điều tra hợp lệ.

Nếu dữ liệu cá nhân xuất hiện trong log, cần đánh giá trách nhiệm kiểm soát: tối thiểu hóa, phân loại, phạm vi truy cập, lưu giữ, xóa và các nghĩa vụ liên quan. Có thể cần quy trình legal hold hoặc retention exception, nhưng phải có thẩm quyền và audit.

### 12.2. Mã hóa không thay cho authorization

**Encryption at rest** và **TLS in transit** giảm rủi ro dữ liệu bị đọc từ disk/network ngoài ý muốn. Nhưng nếu một người có quyền query API nhận lại plaintext qua dashboard, mã hóa không ngăn người đó xem và trích xuất. Ngược lại, RBAC tốt không thay thế encryption khi dữ liệu đi qua mạng hoặc backup không được bảo vệ.

Tương tự, **hashing/masking** giúp giảm dữ liệu hiện ra nhưng có giới hạn. Hash của một giá trị định danh có entropy thấp có thể bị dò; việc nhiều log cùng chứa cùng một hash vẫn có thể cho phép liên kết hoạt động. Cần quyết định theo mục đích, mô hình đe dọa và chính sách dữ liệu.

## 13. Khác biệt giữa quyền xem log và quyền thay đổi logging

Người có quyền **đổi logging.level.root=DEBUG**, sửa pattern để in HTTP headers hoặc cấu hình appender gửi sang endpoint khác có thể làm tăng lượng thông tin được thu thập. Ngay cả khi không có quyền đọc raw log trực tiếp, quyền thay đổi cấu hình vẫn có thể tạo đường rò rỉ trong tương lai.

Nên tách:

- **READ**: tra cứu log đã được phép.
- **CONFIGURE**: thay level/pattern/sampling/filter ở phạm vi được cấp.
- **MANAGE_SINK**: đổi endpoint/collector/index, có thể ảnh hưởng quyền truy cập.
- **EXPORT**: tạo bản sao dữ liệu.
- **DELETE**: xóa record hoặc thay retention.
- **GRANT**: thay permission của actor khác.

Review mọi quyền **gián tiếp dẫn đến đọc**: sửa mã ứng dụng để log secret, truy cập file backup, thêm exporter thứ hai, cấp token query cho mình hoặc disable redaction. Đây là lý do log privacy không thể giải quyết bằng một RoleBinding duy nhất.

## 14. Kiểm thử quyền đọc log

### 14.1. Ma trận kiểm thử tối thiểu

| Tình huống | Kỳ vọng |
| --- | --- |
| Chưa đăng nhập gọi query API | DENY, không trả raw log. |
| User hợp lệ không có READ | DENY, không trả dữ liệu hay metadata nhạy cảm. |
| SUPPORT xem log đã mask trong tenant được cấp | ALLOW đúng phạm vi, không có raw secret. |
| SUPPORT yêu cầu log RESTRICTED | DENY, không lộ nội dung. |
| SRE xem service ngoài trách nhiệm | DENY theo scope. |
| User tenant A sửa query thành tenant B | DENY hoặc scope B bị loại ở backend; không phụ thuộc UI. |
| Người có VIEW gọi EXPORT | DENY nếu không có quyền EXPORT riêng. |
| Token hết hạn hoặc bị thu hồi | DENY ngay khi policy yêu cầu; không dùng quyền cũ quá thời hạn. |
| Role cao nhưng không có approval theo vụ việc | DENY dữ liệu đòi approval. |
| Break-glass hết hạn | Quyền bị thu hồi và có audit/review. |
| User xem dashboard nhưng gọi API raw trực tiếp | Không được bypass redaction/authorization. |
| Saved search, follow, pagination, bulk API | Cùng một chính sách scope ở mọi endpoint. |
| Log được export thành CSV/ZIP | Kiểm tra authorization, nhãn, TTL, lưu trữ an toàn, audit. |
| Log rotate/backup/archive | Quyền trên bản sao không rộng hơn policy cho phép. |
| Kubernetes pods/log namespace khác | DENY theo RBAC; kiểm tra các binding bổ sung. |
| Nhân viên thay đổi nhóm quyền | Quyền cũ được thu hồi theo thời hạn tổ chức quy định. |
| Đọc log audit của chính actor | Không cho tự sửa/xóa audit trail; kiểm soát quyền độc lập. |
| Thử xem file qua symlink/path traversal | Không thể thoát khỏi thư mục/nguồn dữ liệu được phép. |
| Query cực rộng hoặc liên tục | Rate/size limit, approval và cảnh báo phù hợp. |

### 14.2. Cách viết assertion

Dùng log test với **event ID riêng** và thông điệp giả:

~~~text
ev-101 GENERAL tenant-a "health check successful"
ev-102 RESTRICTED tenant-a "sensitive event redacted"
ev-103 GENERAL tenant-b "other tenant event"
~~~

Kiểm tra không chỉ HTTP status code, mà cả **response body**:

- Nếu DENY, không có event message, raw fields hoặc count tiết lộ thông tin không được phép.
- Nếu ALLOW, kết quả chỉ thuộc tenant/service/time range được cấp.
- Một request kết hợp hai tenant không được trả gộp dữ liệu ngoài phạm vi actor.
- Export và saved search không mở rộng hơn quyền view/query đã được cấp.
- Raw secret không được đưa vào payload rồi ẩn chỉ tại frontend.
- Audit có cả ALLOW/DENY và có thể tương quan với request ID mà không chứa nội dung nhạy cảm.

Test âm tính quan trọng hơn việc chỉ kiểm tra rằng admin xem được mọi thứ. Đối với multi-tenant, kiểm tra **một actor ở tenant A không truy cập được tenant B** ngay cả khi query sửa bằng tay.

### 14.3. Test đối với quyền file và Kubernetes

Với file trên POSIX, nên kiểm tra bằng **hai danh tính OS thật khác nhau**, không chỉ dựa vào chmod output. Với Kubernetes, dùng các danh tính test có quyền được cấp thực tế, tránh giả định ClusterRoleBinding không tạo quyền rộng hơn Role cục bộ.

Nếu hệ thống logging trung tâm tồn tại song song, cần test cả **Kubernetes API** lẫn **query API của collector/storage**, vì chúng là hai đường đọc độc lập.

## 15. Quy trình xử lý yêu cầu đọc log nhạy cảm

Một yêu cầu hỗ trợ cần xem log khách hàng có thể xử lý theo quy trình:

1. **Tiếp nhận**: xác định mục đích, ticket, service, môi trường, thời gian và tenant liên quan.
2. **Tối thiểu hóa**: có thể giải quyết bằng metrics, trace summary hoặc log đã mask không?
3. **Xác nhận quyền**: danh tính requester, role/scope hiện tại và có cần approval không.
4. **Cấp quyền hẹp**: thời hạn ngắn, tenant/service cụ thể, mức classification cần thiết.
5. **Truy cập có giám sát**: ghi audit cho query và export; giới hạn record count, field và time window.
6. **Chia sẻ kết quả**: không gửi raw log qua kênh không được phê duyệt; dùng bản đã sanitize/mask khi đủ.
7. **Đóng yêu cầu**: thu hồi grant, xử lý file export, lưu audit/ticket theo retention.
8. **Review**: nếu cần truy cập lặp lại thường xuyên, cải thiện dashboard/trường log để giảm nhu cầu quyền raw.

Khi xảy ra sự cố nghiêm trọng, có thể có quy trình break-glass, nhưng vẫn cần lý do, thời hạn, thông báo và review hậu kiểm.

## 16. Chẩn đoán khi quyền đọc bị cấp quá rộng

Ví dụ nhóm support vô tình có quyền đọc mọi namespace production.

**Bước 1 — Khoanh vùng quyền thực tế:** xác định identity/provider, role/group, token/credential, RoleBinding/ClusterRoleBinding, quyền dashboard/query API, backup và export. Không kết luận từ tên một Role.

**Bước 2 — Hạn chế rủi ro:** thu hồi hoặc thu hẹp grant gây lộ ngoài policy, xử lý session/token khi cần và giữ bằng chứng kiểm toán. Không xóa audit hoặc lịch sử truy cập để “dọn dẹp”.

**Bước 3 — Xác định dữ liệu có thể đã bị đọc:** kiểm tra audit ALLOW, query IDs, time ranges, downloads, số lượng record và các bản sao liên quan. Phân biệt **có quyền truy cập** với **đã thực sự truy cập**.

**Bước 4 — Đánh giá ảnh hưởng:** phân loại nội dung log (PII, secret, thông tin tenant, security evidence), đối tượng bị ảnh hưởng và yêu cầu báo cáo theo chính sách/pháp luật áp dụng. Nếu secret bị lộ, đánh giá rotation/revocation theo quy trình an ninh.

**Bước 5 — Ngăn tái diễn:** sửa policy-as-code, bổ sung negative tests, tăng logging access audit, kiểm tra quyền export và định kỳ review grants.

Không khắc phục bằng cách chỉ ẩn dashboard nếu raw query API và export token vẫn mở. Cần xác nhận lại bằng **tài khoản có quyền thấp** sau khi sửa.

## 17. Những hiểu lầm phổ biến

1. **“Chỉ xem log, không sửa được thì an toàn.”** Sai; quyền read có thể làm lộ thông tin cá nhân và secret.
2. **“Log production không chứa PII vì app không có form PII.”** Sai; framework, exception, headers, trace metadata và thư viện có thể vô tình ghi dữ liệu.
3. **“Đã mask ở UI nghĩa là dữ liệu được bảo vệ.”** Sai nếu raw API/export vẫn gửi toàn bộ record.
4. **“Admin hạ tầng mặc định cần toàn quyền đọc raw log.”** Không nhất thiết. Quản trị nền tảng và quyền xem dữ liệu có thể tách.
5. **“Chỉ cần Kubernetes RBAC.”** Sai nếu người dùng còn xem log qua SIEM/dashboard/file/backup.
6. **“Role đọc một namespace là chỉ đọc một deployment.”** Không. RBAC pods/log có thể cho xem các Pod trong toàn namespace theo scope quyền.
7. **“Có VIEW thì có thể EXPORT.”** Không nên suy ra. Export tạo bản sao dễ lan truyền, cần policy riêng.
8. **“File mode 640 là đủ trên mọi hệ điều hành.”** Sai; Windows, POSIX ACL, group, symlink và identity có ngữ nghĩa khác.
9. **“Mã hóa storage thay thế quyền đọc.”** Sai; query API có thể giải mã và trả plaintext cho người có credential.
10. **“Read logs không cần audit.”** Sai; truy vấn và export là hoạt động có ý nghĩa bảo mật.
11. **“Không cần thu hồi quyền tạm thời nếu người đó vẫn làm việc ở nhóm.”** Sai; quyền nên gắn với nhu cầu và thời hạn.
12. **“Có thể gửi nguyên log trong ticket/chat cho tiện.”** Không an toàn nếu kênh đó có quyền truy cập rộng hơn log platform.
13. **“Log shipper cần quyền admin để chắc chắn không mất log.”** Sai; thường chỉ cần những quyền đọc nguồn/ghi đích cụ thể.
14. **“Một kết quả can-i là đủ chứng minh toàn bộ hệ thống an toàn.”** Sai; đó là một kiểm tra permission ở một API scope, không bao quát đường dữ liệu khác.
15. **“Ẩn secret ở viewer là đủ.”** Không; cần ngăn ghi secret và bảo vệ mọi bản sao.
16. **“Deny mà trả tên event/tenant đầy đủ cũng không sao.”** Có thể gây information disclosure; nội dung deny cũng cần tối thiểu hóa.

## 18. Bài tập ôn luyện

**Bài 1.** Chạy LogAccessDemo.java và giải thích vì sao SECURITY không đọc được ev-4 dù là vai trò cao nhất trong demo.

**Bài 2.** Mở rộng policy bằng thuộc tính **environment**. Chỉ cho SRE đọc production khi service thuộc danh sách trách nhiệm của họ; test âm tính với staging/prod và service khác.

**Bài 3.** Thay quyền exportApproved bằng một record Approval gồm actorId, ticket, scope và expiry. Mô tả nguồn dữ liệu đáng tin cậy, kiểm tra tại backend và điều gì xảy ra khi approval hết hạn. Không cho client tự gán approved=true.

**Bài 4.** Trên môi trường POSIX thử nghiệm, tạo một file log giả với quyền 640 trong thư mục 750. Kiểm tra bằng hai OS users: một thành viên group logreaders và một user ngoài group. Giải thích quyền x trên directory.

**Bài 5.** Đọc cấu hình Role/RoleBinding Kubernetes trong mục 9. Xác định nó cho phép xem log của những Pod nào và vì sao nó không tự giới hạn theo deployment name.

**Bài 6.** Thiết kế quyền cho ba nhóm: Support chỉ được xem masked log của tenant được giao; SRE theo service; Security truy vấn raw log của một vụ việc có phê duyệt. Liệt kê các endpoint VIEW, QUERY, FOLLOW, EXPORT cần kiểm soát.

**Bài 7.** Một dashboard hiển thị dữ liệu đã mask nhưng API trả raw JSON. Phân tích cách khai thác rò rỉ và vị trí phải thực thi redaction/authorization.

**Bài 8.** Một người có quyền production logs đã export 1 triệu dòng rồi gửi vào một chat room. Xác định các biện pháp kỹ thuật và quy trình nhằm phòng ngừa, phát hiện và phản ứng.

**Bài 9.** Xây dựng checklist review quyền log định kỳ: grants không còn dùng, tài khoản nghỉ việc, token hết hạn, public link, export trong 30 ngày, backup/archive và break-glass history.

## 19. Kết luận

**Quyền đọc log là quyền truy cập dữ liệu, không phải chỉ là quyền mở một file text.** Mức độ rủi ro phụ thuộc vào dữ liệu trong log, độ rộng của phạm vi truy vấn, tenant, môi trường, thời gian lưu và khả năng export.

Muốn bảo vệ quyền riêng tư trong Java logging, hãy kết hợp **không ghi dữ liệu thừa + redaction + danh tính đã xác thực + authorization thực thi ở backend + least privilege theo scope + audit mọi truy cập + kiểm soát bản sao/retention**. File permissions, Kubernetes RBAC và quyền của hệ thống tập trung là các **lớp kiểm soát khác nhau**; phải kiểm tra toàn bộ đường từ JVM đến dashboard và archive.

**Điểm cốt lõi:** khi có người hỏi "Ai được đọc log này?", câu trả lời không nên là "ai có link dashboard". Cần xác định rõ **ai, đọc phần nào, để làm gì, khi nào, bằng quyền nào và hoạt động đó được kiểm toán như thế nào**.

### Tài liệu tham khảo

- OWASP Logging Cheat Sheet — Protection, data to exclude, verification: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP Developer Guide — Security Logging and Monitoring: https://devguide.owasp.org/en/04-design/02-web-app-checklist/09-logging-monitoring/
- Kubernetes — Using RBAC Authorization, pods/log subresource: https://kubernetes.io/docs/reference/access-authn-authz/rbac/
- Kubernetes — kubectl logs: https://kubernetes.io/docs/reference/kubectl/generated/kubectl_logs/
- Oracle JDK 17 — PosixFilePermissions: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFilePermissions.html
- Oracle JDK 17 — PosixFileAttributeView: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/attribute/PosixFileAttributeView.html
- NIST SP 800-92 — Guide to Computer Security Log Management: https://csrc.nist.gov/pubs/sp/800/92/final