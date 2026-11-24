# Schedule creation authorization

## 1. Tạo lịch là cấp khả năng thực hiện hành động trong tương lai

Scheduler kích hoạt công việc ở thời điểm hoặc chu kỳ đã định: tạo báo cáo, gửi thông báo, hết hạn một ưu đãi, thu tiền định kỳ hoặc xử lý các đối tượng đến hạn. **Schedule creation authorization** là việc quyết định ai được tạo lịch, lịch đó được phép gọi hành động nào, trên tài nguyên nào, với phạm vi và thời hạn nào.

Một lịch không chỉ là một biểu thức thời gian. Nó lưu lại ý định nghiệp vụ để một thành phần khác thực thi sau này, có thể nhiều lần và khi người tạo không còn trực tuyến. Nếu kiểm tra quyền sơ sài, chức năng này có thể trở thành đường vòng để đọc dữ liệu sai tenant, gửi dữ liệu tới người nhận tùy ý, sửa giá hoặc vượt bước phê duyệt.

Ví dụ, người dùng có quyền xem một báo cáo không mặc nhiên có quyền:

- Tạo lịch xuất toàn bộ dữ liệu làm nền cho báo cáo.
- Gửi báo cáo định kỳ đến một địa chỉ bên ngoài.
- Chạy báo cáo với quyền quản trị của worker.
- Tiếp tục nhận dữ liệu sau khi bị gỡ khỏi dự án.
- Tạo hàng nghìn lịch để vượt hạn mức khai thác dữ liệu hoặc gây quá tải.

Trong bảo mật logic nghiệp vụ, quyền tạo lịch phải gắn với tác động được lập lịch. Nút “Tạo lịch” trên giao diện chỉ là điểm khởi đầu; quyết định cuối cùng nằm ở server và phải giữ đúng bất biến khi request bị sửa, gửi lại hoặc chạy đồng thời.

## 2. Phân biệt ba thời điểm kiểm soát quyền

| Thời điểm | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Tạo lịch | Người gọi có được thiết lập lịch với nội dung này không? | Có được lên lịch gửi báo cáo của dự án A cho nhóm B không? |
| Sửa, bật lại, sao chép lịch | Người gọi có được thay đổi khả năng đã cấp không? | Có được đổi người nhận sang bên ngoài hoặc tăng tần suất không? |
| Thực thi | Lần chạy hiện tại còn được phép tạo tác động không? | Người nhận và phạm vi dữ liệu hiện tại còn hợp lệ không? |

Kiểm tra ở một thời điểm không thay thế hai thời điểm còn lại.

Nếu chỉ kiểm tra lúc chạy, người dùng có thể tích lũy lịch không hợp lệ, chiếm quota, tạo dữ liệu cấu hình sai hoặc khai thác đường thực thi thiếu kiểm tra. Nếu chỉ kiểm tra lúc tạo, lịch có thể tiếp tục khai thác quyền cũ sau khi người dùng hoặc tài nguyên thay đổi.

### 2.1. Chọn mô hình quyền thực thi rõ ràng

Hai mô hình thường gặp:

1. **Quyền hiện tại của chủ thể:** mỗi lần chạy phải xác minh chủ thể còn quyền theo chính sách. Phù hợp với lịch xuất báo cáo nhạy cảm mà việc mất quyền phải chặn các lần xuất mới.
2. **Ủy quyền bền vững có giới hạn:** hệ thống chấp nhận một cam kết nghiệp vụ cụ thể, được phê duyệt hoặc có căn cứ riêng, với hành động, phạm vi, hạn mức và thời hạn rõ ràng. Việc người tạo mất một vai trò không nhất thiết tự hủy cam kết; cần quy tắc thu hồi riêng.

Không tự biến mọi lịch thành ủy quyền vô thời hạn. Với lịch báo cáo trong bài này, giả định hệ thống dùng quyền hiện tại của chủ thể và kiểm tra lại người nhận trước mỗi lần xuất.

Với thanh toán định kỳ, cần mô hình chấp thuận và các bất biến tài chính riêng. Quyền `schedule:create` không thay thế phê duyệt thanh toán, quyền đối với tài khoản hay giới hạn số tiền.

## 3. Mô hình đe dọa và các bất biến cần bảo vệ

### 3.1. Những đầu vào người gọi có thể sửa

Không chỉ kiểm tra dữ liệu từ form. Người gọi có thể tự gửi request để sửa:

- `tenantId`, `projectId`, `reportId` hoặc ID tài nguyên đích.
- Loại hành động, bộ lọc dữ liệu hoặc phiên bản cấu hình báo cáo.
- Người sở hữu, người chạy thay, service account hoặc danh tính phê duyệt.
- Người nhận, danh sách nhóm nhận hoặc đích xuất dữ liệu.
- Tần suất, thời gian bắt đầu, thời gian kết thúc và chế độ chạy bù.
- Trạng thái `ACTIVE`, cờ bỏ kiểm tra quyền hoặc thuộc tính nội bộ không có trên giao diện.
- Idempotency key và số lượng request tạo lịch đồng thời.

Coi toàn bộ payload là yêu cầu của client, không phải bằng chứng về quyền.

### 3.2. Các bất biến

| Bất biến | Hệ quả thiết kế |
| --- | --- |
| Mọi lịch thuộc đúng tenant được phép | Tenant phải được ràng buộc với principal và kiểm tra quan hệ tài nguyên |
| Không cấp khả năng mà người tạo không được phép cấp | Kiểm tra cả hành động, đối tượng, tham số và quyền ủy quyền nếu có |
| Worker không mở rộng quyền của lịch | Worker thực thi trong ngữ cảnh giới hạn, không tự dùng quyền quản trị để quyết định phạm vi |
| Người nhận dữ liệu phải được cho phép | Kiểm tra chính sách xuất/chia sẻ, không chỉ quyền đọc của người tạo |
| Lịch không bỏ qua state machine nghiệp vụ | Hành động chạy về sau vẫn kiểm tra trạng thái và các bước phê duyệt |
| Tổng lượng công việc nằm trong giới hạn | Quota và tần suất được kiểm tra nguyên tử khi tạo |
| Retry request không tạo lịch trùng ngoài ý muốn | Idempotency gắn với nội dung chuẩn hóa và đúng ngữ cảnh |
| Thay đổi ảnh hưởng quyền không được áp dụng âm thầm | Sửa, clone, resume và import đều đi qua chính sách thích hợp |
| Thu hồi quyền có ngữ nghĩa xác định | Có mốc kiểm tra, cơ chế chặn lần chạy mới và xử lý công việc đã bắt đầu |

Một điều kiện tổng quát có thể diễn đạt như sau:

~~~text
ALLOW_CREATE =
    actor được xác thực và hoạt động
    AND actor có quyền tạo loại lịch trong tenant này
    AND actor được phép lập lịch hành động đã yêu cầu
    AND actor có quyền cần thiết trên các tài nguyên đích
    AND tham số và đích nhận nằm trong phạm vi cho phép
    AND quyền ủy quyền hợp lệ nếu tạo thay chủ thể khác
    AND điều kiện phê duyệt được thỏa mãn
    AND giới hạn thời gian, tần suất và quota được thỏa mãn.
~~~

Đây là các điều kiện đồng thời, không phải danh sách để chọn một điều kiện bất kỳ.

## 4. Kiểm tra quyền theo hành động, đối tượng và tham số

### 4.1. Quyền tạo lịch không phải quyền làm mọi việc qua scheduler

Có thể định nghĩa các quyền theo nhu cầu sản phẩm:

| Quyền minh họa | Điều nó cho phép | Điều cần kiểm tra thêm |
| --- | --- | --- |
| `schedule:create` | Bắt đầu yêu cầu tạo lịch trong phạm vi được cấp | Loại hành động, tài nguyên, người nhận và giới hạn |
| `report:view` | Xem báo cáo theo chính sách | Có được xuất, xuất định kỳ và chia sẻ không? |
| `report:schedule-export` | Lập lịch xuất một báo cáo | Dữ liệu và đích nhận cụ thể có hợp lệ không? |
| `schedule:create-on-behalf` | Tạo lịch thay một chủ thể trong phạm vi được cấp | Chủ thể nào, loại tác động nào và căn cứ ủy quyền nào? |
| `schedule:manage` | Quản lý những lịch được phép | Có được thay người nhận, chủ thể hoặc nội dung tác động không? |

Đây là các tên quyền minh họa. Một hệ thống có thể dùng mô hình vai trò, thuộc tính hoặc quan hệ khác, nhưng vẫn phải thể hiện các quyết định tương đương.

Quyền quản lý lịch không tự mang theo quyền truy cập nội dung dữ liệu. Ví dụ, nhân viên vận hành có thể được tạm dừng một lịch lỗi mà không được đọc báo cáo của khách hàng.

### 4.2. Quyền theo đối tượng: kiểm tra cả chuỗi quan hệ

Request tạo lịch gửi báo cáo có `projectId` và `reportId` cần kiểm tra:

~~~text
actor thuộc tenant được chọn;
project thuộc tenant đó;
report thuộc project được chọn;
actor được phép lập lịch xuất report;
cấu hình report không mở rộng ra tài nguyên ngoài phạm vi được cấp;
người nhận và đích xuất phù hợp với chính sách chia sẻ.
~~~

Không chỉ kiểm tra actor có quyền trên project rồi tin một `reportId` bất kỳ. Tương tự, xác minh report thuộc tenant chưa đủ nếu actor chỉ có quyền ở một phần dự án.

Nếu báo cáo dựa trên tập tài nguyên động, cần định nghĩa rõ tập đó được đánh giá theo quyền hiện tại hay theo một phạm vi đã chốt. Không lưu truy vấn “tất cả dữ liệu tenant” rồi cho rằng ID báo cáo hợp lệ sẽ bảo đảm mọi lần chạy đều đúng quyền.

### 4.3. Quyền theo tham số: kiểm soát nội dung bên trong một hành động hợp lệ

Cùng hành động `REPORT_EXPORT` nhưng mức rủi ro có thể khác nhau:

| Tham số | Lựa chọn thông thường | Lựa chọn cần quyền hoặc điều kiện bổ sung |
| --- | --- | --- |
| Trường dữ liệu | Số liệu tổng hợp | Thông tin cá nhân hoặc chi tiết giao dịch |
| Người nhận | Người dùng nội bộ có quyền | Người ngoài tổ chức hoặc nhóm chứa thành viên ngoài phạm vi |
| Khoảng dữ liệu | Khoảng thời gian giới hạn | Toàn bộ lịch sử hoặc dữ liệu của nhiều dự án |
| Tần suất | Theo giới hạn của loại báo cáo | Chu kỳ ngắn gây xuất dữ liệu liên tục |
| Định dạng/đích xuất | Định dạng và nơi lưu được quản lý | URL hoặc nơi nhận do client tự chỉ định |

Không coi việc chọn được một action trong allowlist là kết thúc phân quyền. Các tham số có thể thay đổi bản chất tác động mà action tạo ra.

## 5. Danh tính nào chịu trách nhiệm cho lịch?

Cần phân biệt:

| Danh tính | Vai trò |
| --- | --- |
| Actor | Người thực sự gửi yêu cầu tạo hoặc sửa lịch |
| Owner | Người hoặc đơn vị quản lý lịch theo mô hình sản phẩm |
| Authority subject | Chủ thể có quyền làm căn cứ cho lần thực thi |
| Execution principal | Tài khoản kỹ thuật của scheduler/worker |
| Approver | Người hoặc cơ chế phê duyệt khi chính sách yêu cầu |

Các giá trị có thể trùng nhau trong trường hợp đơn giản, nhưng không nên nhập thành một trường `userId`.

Actor đến từ thông tin xác thực đã được server kiểm chứng. Owner và authority subject phải được server suy ra hoặc kiểm tra theo chính sách. Execution principal là danh tính của worker, không phải lý do cho phép nó truy cập mọi dữ liệu.

### 5.1. Tạo lịch thay người khác

Nếu API nhận `runAsUserId`, server phải kiểm tra riêng quyền tạo thay, phạm vi ủy quyền, chủ thể đích và loại tác động. Không chấp nhận chỉ vì actor có quyền tạo lịch cho chính mình.

Ví dụ, quản trị viên một dự án có thể được tạo lịch báo cáo cho nhóm của dự án đó; điều này không cho phép chọn một quản trị viên tenant làm authority subject để xuất thêm dữ liệu.

Nếu không có nhu cầu tạo thay, loại bỏ trường này khỏi API công khai. Không để một trường nội bộ có thể được bind tự động từ JSON.

### 5.2. Tạo lịch trong phiên impersonation

Một nhân viên hỗ trợ đang thao tác thay khách hàng không tự được tạo một lịch tiếp tục chạy nhiều tháng. Cần quyết định rõ hành động này có thuộc scope hỗ trợ không và có yêu cầu chấp thuận riêng không.

Nếu được phép, lưu actor thật, effective subject, căn cứ cho phép và chủ thể quyền dùng cho các lần chạy. Kết thúc phiên impersonation không tự xác định lịch phải tiếp tục hay dừng; chính sách cần quy định và thực thi việc đó.

Không được dùng việc tạo lịch để chuyển một quyền hỗ trợ ngắn hạn thành quyền truy cập dài hạn mà hệ thống chưa cho phép.

## 6. Thiết kế request hẹp và kiểm tra ở server

### 6.1. Ví dụ API cho một loại lịch cụ thể

Một request minh họa:

~~~http
POST /projects/project-17/report-schedules
Authorization: Bearer <credential>
Idempotency-Key: create-report-schedule-901
Content-Type: application/json

{
  "reportId": "report-81",
  "recipientGroupId": "group-finance",
  "timing": {
    "type": "DAILY",
    "localTime": "08:00",
    "timeZone": "Asia/Ho_Chi_Minh"
  },
  "startsAt": "2026-12-01T00:00:00Z",
  "endsAt": "2026-12-31T23:59:59Z",
  "format": "SUMMARY_PDF"
}
~~~

Ví dụ dùng thời gian và định dạng do sản phẩm hỗ trợ; không ngụ ý mọi hệ thống phải cho lịch hàng ngày, cho phép PDF hoặc dùng các giới hạn giống nhau.

Request không cung cấp `createdBy`, `approvedBy`, `status`, service account, câu lệnh thực thi hoặc một URL nhận dữ liệu tùy ý. Tenant được xác định từ ngữ cảnh request đã kiểm chứng và quan hệ tài nguyên; nếu API cho chọn tenant, lựa chọn đó vẫn phải được xác minh với quyền thành viên.

Một API scheduler tổng quát có thể hỗ trợ nhiều action, nhưng mỗi action cần schema và chính sách riêng. Không truyền nguyên một map `jobArguments` không có ràng buộc xuống worker.

### 6.2. Các lớp kiểm tra

| Lớp | Việc cần làm |
| --- | --- |
| Cấu trúc | Kiểu dữ liệu, trường bắt buộc, độ dài, schema hỗ trợ, trường không được phép |
| Chuẩn hóa | Định dạng thời gian, kiểu lịch, định danh và giá trị mặc định theo quy tắc rõ ràng |
| Xác thực | Principal hợp lệ, tài khoản và ngữ cảnh truy cập đáp ứng chính sách |
| Quyền chức năng | Có được tạo loại lịch và lập lịch action này không? |
| Quyền đối tượng | Tenant, project, report và nhóm nhận có quan hệ hợp lệ không? |
| Quyền theo tham số | Định dạng, bộ lọc, dữ liệu xuất và đích nhận có được phép không? |
| Giới hạn | Tần suất, thời hạn, số lịch và lượng công việc dự kiến |
| Phê duyệt | Được active ngay hay phải chờ phê duyệt? |
| Tính nguyên tử | Quyền, quota và bản ghi lịch có nhất quán trước cạnh tranh không? |

Chuẩn hóa không được âm thầm thay đổi ý nghĩa yêu cầu. Nếu sản phẩm không hỗ trợ lịch mỗi phút, không tự chuyển thành mỗi giờ mà không cho người gọi biết chính xác điều đã được chấp nhận.

Với field nội bộ như `skipAuthorization` hoặc `approved`, nên từ chối đầu vào trái schema thay vì trộn vào entity. Điều quan trọng là chúng không có khả năng điều khiển quyết định server.

### 6.3. Đích nhận dữ liệu là một tài nguyên cần phân quyền

Một nhóm nhận hợp lệ về cú pháp chưa chắc hợp lệ về bảo mật. Cần xét nhóm có thuộc tenant, có được phép nhận loại dữ liệu đó, và thành viên của nhóm có nằm trong phạm vi chia sẻ không.

Nếu dùng nhóm động, membership có thể thay đổi sau khi tạo lịch. Với ví dụ báo cáo ở đây, cần kiểm tra lại người nhận thực tế khi chạy, không coi nhóm đã được chấp nhận một lần là đích nhận an toàn vĩnh viễn.

Nếu sản phẩm cho webhook, nên có mô hình đích nhận được đăng ký và cấp quyền riêng. Bên cạnh quyền chia sẻ dữ liệu, còn cần kiểm soát đích mạng để tránh dùng scheduler gọi tới địa chỉ nội bộ hoặc chuyển tiếp dữ liệu ngoài phạm vi cho phép.

## 7. Luồng tạo lịch nguyên tử

### 7.1. Thứ tự xử lý tổng quát

~~~mermaid
sequenceDiagram
    participant U as Người gọi
    participant API as Schedule API
    participant P as Chính sách quyền
    participant DB as Database
    participant D as Bộ đăng ký lịch

    U->>API: Yêu cầu tạo lịch và idempotency key
    API->>API: Xác thực, kiểm tra schema, chuẩn hóa
    API->>DB: BEGIN, đọc dữ liệu và khóa cần thiết
    API->>P: Kiểm tra action, tài nguyên, tham số, chủ thể
    P-->>API: Cho phép với giới hạn và yêu cầu phê duyệt
    API->>DB: Claim idempotency, kiểm tra và giữ quota
    API->>DB: Ghi lịch, audit và outbox
    API->>DB: COMMIT
    DB-->>API: Đã commit
    API-->>U: ID, version, trạng thái và cấu hình đã chấp nhận
    D->>DB: Đọc outbox đã commit
    D->>D: Đăng ký theo trạng thái và version hợp lệ
~~~

Nếu lịch ở `PENDING_APPROVAL`, bộ đăng ký không được kích hoạt nó. Outbox nói “đã tạo bản ghi lịch” khác với “được phép thực thi”.

Quyết định phân quyền cần dùng trạng thái nhất quán với dữ liệu tạo lịch theo ngữ nghĩa đã chọn. Nếu quyền hoặc membership ở hệ thống ngoài database, phải có thiết kế phiên bản, thu hồi và kiểm tra khi chạy; một transaction nội bộ không tự khóa được dịch vụ quyền bên ngoài.

### 7.2. Pseudocode Java

Mã giả sau minh họa API chỉ tạo lịch xuất báo cáo. Không gắn với một framework cụ thể.

~~~java
ScheduleResponse createReportSchedule(
        AuthenticatedPrincipal principal,
        ProjectId projectId,
        CreateReportScheduleRequest request,
        IdempotencyKey key) {

    // Chỉ kiểm tra/chuẩn hóa đầu vào, chưa coi request là được cấp quyền.
    NormalizedReportSchedule proposal = normalizeAndValidate(request);
    TrustedTenantContext tenant = tenantResolver.requireAllowed(principal);

    return database.transaction(tx -> {
        Project project = projects.requireInTenant(
                tx, tenant.id(), projectId);

        Report report = reports.requireInProject(
                tx, tenant.id(), project.id(), proposal.reportId());

        RecipientGroup recipients = groups.requireInTenant(
                tx, tenant.id(), proposal.recipientGroupId());

        CreationDecision decision = authorization.requireCreateReportSchedule(
                tx, principal, tenant, project, report, recipients, proposal);

        // Claim có ràng buộc duy nhất và fingerprint nội dung chuẩn hóa.
        IdempotencyClaim claim = idempotency.claimOrLoad(
                tx, tenant.id(), principal.id(),
                "CREATE_REPORT_SCHEDULE", key,
                fingerprint(project.id(), proposal));

        if (claim.isCompleted()) {
            Schedule existing = schedules.requireById(
                    tx, tenant.id(), claim.scheduleId());
            authorization.requireCanReadCreationResult(principal, existing);
            return ScheduleResponse.from(existing);
        }

        // Dùng thời gian server; xét cả tần suất và phạm vi hiệu lực.
        TimingPlan plan = timingPolicy.validateAndPlan(
                proposal.timing(), proposal.startsAt(),
                proposal.endsAt(), decision, clock.instant());

        ScheduleQuota quota = quotas.lockForUpdate(
                tx, tenant.id(), "REPORT_EXPORT");

        quota.requireFits(plan, decision);
        quota.reserveForCreation(plan);

        // Actor/authority subject/status được server xác lập.
        Schedule schedule = Schedule.createReportExport(
                tenant.id(),
                principal.id(),
                decision.authoritySubject(),
                project.id(),
                report.id(),
                recipients.id(),
                proposal.format(),
                plan,
                decision.initialState(),
                decision.policyReference());

        schedules.insert(tx, schedule);
        quotas.save(tx, quota);
        auditOutbox.append(tx, ScheduleCreated.from(schedule, decision));
        idempotency.complete(tx, claim, schedule.id());

        return ScheduleResponse.from(schedule);
    });
}
~~~

Các giả định cần giữ khi triển khai:

1. Hàm `requireCreateReportSchedule` kiểm tra cả quyền tạo lịch lẫn action, đối tượng và tham số; không chỉ kiểm tra một role.
2. Các dữ liệu ảnh hưởng quyền và điều kiện tạo phải được bảo vệ theo mức nhất quán đã định nghĩa, chẳng hạn khóa, version hoặc kiểm tra thay đổi trước commit.
3. Claim idempotency có unique constraint và được ghi cùng transaction. Cần xử lý tranh chấp, rollback và fingerprint không khớp.
4. Quota được kiểm tra và giữ chỗ nguyên tử. Nhánh đọc kết quả cũ không giữ quota lần nữa.
5. Trạng thái ban đầu do server chọn. Client không thể tự đặt `ACTIVE` hoặc tự điền approver.
6. Audit/outbox được ghi cùng bản ghi lịch. Lỗi ghi bằng chứng bắt buộc hoặc lỗi giữ quota làm transaction rollback.
7. `database.transaction` chỉ trả kết quả thành công sau khi commit hoàn tất.
8. Bộ tiêu thụ outbox và dispatcher đọc trạng thái/version đáng tin, không tin một payload cũ như quyền thực thi vĩnh viễn.

Mã giả chỉ minh họa luồng cho loại lịch đã giới hạn. Nếu hệ thống cho tạo thay người khác hoặc nhiều loại action, các lựa chọn đó phải được kiểm tra và đưa vào nội dung chuẩn hóa, fingerprint và quyết định quyền.

### 7.3. TOCTOU: quyền thay đổi giữa kiểm tra và sử dụng

Một khoảng hở có thể là:

~~~text
T1: API kiểm tra actor còn quyền xuất báo cáo.
T2: Quản trị viên thu hồi quyền.
T3: API commit lịch ACTIVE dựa trên kết quả cũ.
~~~

Cần xác định mốc có hiệu lực. Có thể dùng khóa hoặc version của dữ liệu quyền khi nó cùng nguồn nhất quán, hoặc chấp nhận một mốc cấp quyền được định nghĩa rõ rồi kiểm tra lại trước thực thi.

Không chỉ cache một kết quả “allow” vô thời hạn. Nếu yêu cầu thu hồi phải chặn nhanh, thiết kế phải có cơ chế làm mất hiệu lực và kiểm tra tương ứng.

Với một lịch đã tạo nhưng chưa chạy, dispatcher/worker cần từ chối lần chạy mới khi không còn quyền theo mô hình của lịch. Việc tạo lịch thành công trước đó không vượt qua được quyết định thu hồi có hiệu lực sau này.

## 8. Tần suất, thời hạn và quota là một phần của quyết định cho phép

### 8.1. Một lịch hợp lệ về cú pháp vẫn có thể bị cấm

Cần kiểm tra theo loại hành động:

- Khoảng cách tối thiểu giữa các lần chạy.
- Số lần dự kiến trong một cửa sổ thời gian.
- Thời hạn hiệu lực và ngày kết thúc bắt buộc nếu chính sách yêu cầu.
- Số tài nguyên và số người nhận của mỗi lần chạy.
- Số lịch đang hoạt động, đang chờ duyệt hoặc đang giữ quota.
- Chế độ chạy bù khi hệ thống ngừng hoạt động.
- Có được chạy ngay khi tạo hoặc chọn thời điểm quá khứ không?

Ví dụ minh họa: một loại báo cáo chỉ được chạy tối đa bốn lần mỗi ngày và chỉ cho phép người nhận nội bộ. Dù parser hiểu lịch mỗi phút, người dùng vẫn không được tạo lịch đó.

### 8.2. Tính cả fan-out

Giả sử một cấu hình cho phép:

~~~text
50 lịch
x 4 lần chạy mỗi giờ
x 24 giờ
= 4.800 lần chạy mỗi ngày

4.800 lần chạy
x 10 người nhận
= 48.000 lượt chuyển báo cáo mỗi ngày
~~~

Đếm số lịch đơn thuần không phản ánh chi phí hoặc lượng dữ liệu xuất. Cần tính gần đúng hoặc đặt giới hạn bảo thủ trên các chiều quan trọng, rồi tiếp tục kiểm soát khi thực thi.

Nếu bộ lọc hoặc membership nhóm là động, lượng công việc có thể tăng sau ngày tạo. Quyết định tạo lịch không thay thế giới hạn kích thước và fan-out tại thời điểm chạy.

### 8.3. Quota phải chống request đồng thời

Mẫu sau có race condition:

~~~text
Nếu số lịch hiện có < 10:
    tạo lịch mới
~~~

Hai request có thể cùng thấy có chín lịch và đều tạo thêm một lịch. Cần khóa/counter có điều kiện hoặc cơ chế tương đương để kiểm tra và giữ quota nguyên tử.

Quota có thể áp dụng theo actor, tenant, action và tài nguyên. Chỉ giới hạn theo actor có thể bị vượt bằng nhiều tài khoản; chỉ giới hạn theo tenant có thể để một người chiếm hết phần của cả nhóm.

Lịch đang chờ duyệt cũng tiêu thụ dữ liệu và có thể giữ quota. Cần chính sách hết hạn, giải phóng quota và giới hạn số yêu cầu chờ. Việc giải phóng hoặc chuyển quota giữa các trạng thái phải an toàn khi xử lý lặp lại.

### 8.4. Thời gian cần được hiểu theo nghiệp vụ

Một lịch “08:00 mỗi ngày tại múi giờ đã chọn” khác với “mỗi 24 giờ tính từ lần trước”. Lưu được cả quy tắc lặp và múi giờ, thay vì chỉ đổi lần chạy đầu sang UTC rồi bỏ mất ý nghĩa ban đầu.

Với múi giờ có chuyển đổi giờ mùa, có thời điểm địa phương bị lặp hoặc không tồn tại. Hệ thống cần quy tắc rõ cho các trường hợp đó và có cách xem trước các lần chạy dự kiến.

Server phải dùng nguồn thời gian đáng tin khi kiểm tra quá hạn và thời điểm bắt đầu. Không dựa vào trường `clientNow` để cho phép tạo lịch đã hết hiệu lực.

Chạy bù cũng cần chính sách. Sau một tuần ngừng hoạt động, không mặc định phát tất cả lần chạy bị lỡ thành một đợt xuất dữ liệu hoặc thanh toán mà người tạo chưa được phép gây ra.

## 9. Phê duyệt và kích hoạt phải gắn với đúng phiên bản lịch

### 9.1. State machine minh họa

~~~mermaid
stateDiagram-v2
    [*] --> PENDING_APPROVAL: Cần phê duyệt
    [*] --> ACTIVE: Chính sách cho phép kích hoạt trực tiếp
    PENDING_APPROVAL --> ACTIVE: Phê duyệt đúng phiên bản và kiểm tra lại
    PENDING_APPROVAL --> REJECTED: Từ chối
    PENDING_APPROVAL --> EXPIRED: Quá hạn chờ duyệt
    PENDING_APPROVAL --> REVOKED: Thu hồi
    ACTIVE --> PAUSED: Tạm dừng
    PAUSED --> ACTIVE: Đủ quyền và điều kiện khi bật lại
    ACTIVE --> REVOKED: Thu hồi
    PAUSED --> REVOKED: Thu hồi
    ACTIVE --> EXPIRED: Hết thời hạn
    PAUSED --> EXPIRED: Hết thời hạn
~~~

Không phải mọi lịch đều cần người phê duyệt riêng. Nhưng nếu chính sách yêu cầu phê duyệt, việc đó phải được thực thi ở server và không bị bỏ qua bằng một endpoint khác.

### 9.2. Approval phải ràng buộc với nội dung

Bằng chứng phê duyệt nên tham chiếu:

~~~text
schedule_id
schedule_version
action
authority_subject
resource_scope
destination_scope
timing và thời hạn
giới hạn nghiệp vụ liên quan
fingerprint của nội dung cần phê duyệt
approver hoặc căn cứ chính sách tự động
thời hạn của quyết định
~~~

Nếu đã duyệt gửi báo cáo tổng hợp hàng tuần cho nhóm nội bộ, sau đó đổi thành báo cáo chi tiết hàng giờ cho đích ngoài, approval cũ không còn áp dụng cho nội dung mới.

Khi dùng tách biệt người tạo và người duyệt, kiểm tra actor thật của hai hành động. Hai phiên đăng nhập khác nhau của cùng một người không tạo ra hai người độc lập.

Quyền duyệt cũng cần ràng buộc tenant và loại tác động. Một người có quyền duyệt lịch của dự án A không được phê duyệt lịch thuộc dự án B chỉ bằng cách đổi ID.

### 9.3. Kích hoạt cần kiểm tra lại các điều kiện có thể thay đổi

Giữa lúc gửi duyệt và lúc duyệt, report có thể bị chuyển phạm vi, nhóm nhận có thành viên mới, actor mất quyền hoặc quota thay đổi.

Khi kích hoạt, cần kiểm tra những điều kiện mà chính sách yêu cầu còn đúng. Không chỉ đặt `status = ACTIVE` vì có một dòng approval trong database.

Nếu quota đã được giữ khi tạo yêu cầu, bước kích hoạt xác nhận reservation còn hợp lệ và chuyển trạng thái phù hợp, không giữ quota thêm lần nữa. Nếu reservation hết hạn, phải cấp lại theo chính sách trước khi kích hoạt.

### 9.4. Không sửa nội dung đang active trước khi được duyệt

Với thay đổi cần duyệt, có thể tạo version mới ở trạng thái chờ, tách khỏi version đang active. Chính sách xác định version cũ có tiếp tục chạy trong thời gian chờ hay phải tạm dừng.

Không sửa trực tiếp người nhận hoặc action trong bản ghi active rồi mới tạo approval request. Trong khoảng chờ duyệt, dispatcher có thể đã chạy nội dung chưa được cho phép.

Worker cần biết đang dùng version nào và kiểm tra tính hợp lệ của version đó. Một message cũ không được kích hoạt một version đã bị thu hồi.

## 10. Những đường đi phải áp dụng cùng chính sách

### 10.1. Sửa, clone, import và resume

| Đường thao tác | Rủi ro nếu chỉ kiểm tra endpoint tạo mới |
| --- | --- |
| Sửa người nhận | Đổi sang đích ngoài mà không kiểm tra quyền chia sẻ |
| Sửa tần suất hoặc thời hạn | Tăng lượng công việc vượt quyền hoặc làm lịch tồn tại vô hạn |
| Sửa action hoặc tài nguyên | Chuyển lịch ít rủi ro thành tác động nhạy cảm |
| Clone lịch | Sao chép chủ thể quyền hoặc approval mà người clone không có |
| Import cấu hình | Đưa vào field nội bộ như trạng thái, service account hoặc cờ bỏ kiểm tra |
| Resume lịch cũ | Dùng lại quyền đã mất hoặc điều kiện không còn hợp lệ |
| Chuyển owner | Ngầm đổi authority subject và phạm vi dữ liệu |
| Batch API | Tạo nhiều lịch mà không kiểm tra từng đối tượng và tổng quota |

Một helper kiểm tra quyền chỉ được gọi ở controller tạo lịch sẽ không bảo vệ các đường khác. Đặt quy tắc tại lớp nghiệp vụ dùng chung, đồng thời vẫn giữ kiểm soát quyền ở các ranh giới truy cập thích hợp.

Clone tạo một lịch mới phải được đánh giá theo actor hiện tại, nội dung và quota mới. Không sao chép dấu phê duyệt như một thuộc tính trang trí.

### 10.2. Idempotency cho request tạo lịch

Khi client gặp timeout rồi gửi lại yêu cầu, cùng một ý định tạo không nên sinh thêm lịch ngoài ý muốn.

Một phạm vi khóa minh họa:

~~~text
tenant_id + actor_id + operation_type + idempotency_key
~~~

Fingerprint cần bao gồm các đầu vào làm thay đổi ý nghĩa: project, report, người nhận, authority subject nếu được chọn, định dạng, bộ lọc được hỗ trợ, quy tắc thời gian, múi giờ và khoảng hiệu lực.

Cùng key với nội dung khác phải bị từ chối. Nhánh retry hợp lệ trả lịch đã tạo theo quyền truy cập hiện tại, không tạo lại lịch hay giữ quota lần nữa.

Idempotency không ngăn được người dùng chủ động gửi key mới. Nếu sản phẩm cấm nhiều lịch cho cùng một mục đích nghiệp vụ, cần thêm ràng buộc phù hợp. Không tự áp một unique constraint cho mọi cấu hình giống nhau khi sản phẩm vẫn cho phép các lịch riêng biệt hợp lệ.

### 10.3. Lịch hợp lệ không bỏ qua bất biến của từng lần chạy

Một action nhạy cảm vẫn cần quyền theo đối tượng, state machine, transaction và idempotency khi chạy. Ví dụ:

- Lịch hoàn tiền không được hoàn lại một yêu cầu đã hoàn.
- Hai lịch thanh toán không được cùng trả một hóa đơn vượt nghĩa vụ còn lại.
- Lịch cập nhật giá không được sửa một phiên bản giá đã khóa nếu chính sách cấm.
- Lịch xuất báo cáo không được đưa thêm dữ liệu ngoài phạm vi của chủ thể.

Khóa tác động có thể cần ràng buộc với đối tượng và kỳ nghiệp vụ, không chỉ schedule ID. Hai lịch khác nhau cùng nhắm một hóa đơn không được tạo hai lần thanh toán chỉ vì mỗi lịch có khóa riêng.

Tương tự, đổi schedule version không tự tạo quyền thực hiện lại một tác động đã hoàn tất của cùng nghiệp vụ.

## 11. Audit và thu hồi phải giữ được trách nhiệm

### 11.1. Những gì cần ghi nhận khi tạo lịch

Một sự kiện tạo lịch có thể chứa:

| Nhóm | Thông tin minh họa |
| --- | --- |
| Định danh | Event ID, schedule ID, version, request ID và operation ID tạo lịch |
| Danh tính | Actor thật, owner, authority subject và tenant |
| Nội dung | Action, tài nguyên, phạm vi dữ liệu và tham chiếu đích nhận |
| Thời gian | Quy tắc thời gian đã chấp nhận, múi giờ, bắt đầu và kết thúc |
| Quyết định | Chính sách/phiên bản chính sách, kết quả, giới hạn và lý do |
| Phê duyệt | Trạng thái chờ, approval reference và approver nếu đã có |
| Kết quả | Bản ghi lịch đã commit, trạng thái ban đầu và quota liên quan |

Không cần lưu toàn bộ nội dung báo cáo, credential hoặc token thực thi trong audit. Tham chiếu người nhận và phạm vi đã chấp nhận thường hữu ích hơn việc sao chép dữ liệu nhạy cảm.

Không lưu access token ngắn hạn của người tạo như một cách thay thế mô hình quyền lâu dài. Nếu tích hợp bên ngoài đòi hỏi credential, dùng cơ chế quản lý bí mật và ủy quyền phù hợp; không nhúng credential trong cấu hình lịch, URL hoặc payload queue.

Sự kiện `schedule.created` chỉ khẳng định lịch đã được tạo bền vững. Nó không khẳng định mọi lần chạy trong tương lai đã được cấp quyền hoặc đã thành công.

### 11.2. Ghi nhận yêu cầu bị từ chối

Các mã lý do nội bộ có thể phân biệt:

~~~text
SCHEDULE_CREATE_NOT_ALLOWED
SCHEDULE_ACTION_NOT_ALLOWED
RESOURCE_SCOPE_DENIED
RECIPIENT_SCOPE_DENIED
DELEGATION_NOT_ALLOWED
TIMING_POLICY_VIOLATION
SCHEDULE_QUOTA_EXCEEDED
APPROVAL_REQUIRED
~~~

`APPROVAL_REQUIRED` có thể là kết quả yêu cầu chờ duyệt thay vì lỗi, tùy API. Hợp đồng phải thể hiện rõ lịch đã được lưu ở trạng thái nào.

Thông báo cho client không nên làm lộ sự tồn tại hoặc chi tiết của tài nguyên ngoài quyền. Hệ thống có thể dùng thông báo ngoài phù hợp và lưu lý do chi tiết trong audit có kiểm soát truy cập.

Sự kiện từ chối ghi trong một transaction rồi rollback cũng sẽ biến mất. Nếu cần ghi bền vững các lần thử này, dùng đường ghi độc lập phù hợp; lỗi ghi nhận không được biến quyết định từ chối thành cho phép.

### 11.3. Thu hồi quyền và lịch đã phát sinh công việc

Khi mất quyền, có thể cần:

1. Ngăn phát sinh lần chạy mới.
2. Làm mất hiệu lực các message chờ chưa tạo tác động theo chính sách.
3. Đánh giá operation đã được chấp nhận hoặc đã bắt đầu.
4. Ghi nhận việc dừng, lý do và những tác động đã xảy ra.

Không hứa rằng thu hồi lịch sẽ đảo ngược báo cáo đã gửi hoặc khoản tiền đã chuyển. Với ví dụ báo cáo dùng quyền hiện tại, worker kiểm tra quyền và người nhận trước lần xuất mới; quyền bị thu hồi phải chặn tác động mới theo mốc hiệu lực đã quy định.

Nếu cần chặn cả cạnh tranh giữa thu hồi và bắt đầu chạy, phải có cơ chế version, khóa hoặc fencing phù hợp ở nơi quyết định tạo tác động. Chỉ kiểm tra một cờ trong giao diện quản lý lịch không đủ.

### 11.4. Các tín hiệu cần theo dõi

- Nhiều lần tạo lịch bị từ chối trên các report hoặc tenant khác nhau.
- Tăng bất thường số lịch, tần suất hoặc số người nhận.
- Các thay đổi liên tục từ đích nội bộ sang đích có mức rủi ro cao hơn.
- Lịch active thiếu quyết định cho phép hoặc approval đúng version.
- Chủ thể không còn quyền nhưng vẫn có lần xuất mới trái chính sách.
- Quota thực tế không khớp với số lịch đang giữ quota.
- Message của version bị thu hồi vẫn tạo tác động.

Đây là tín hiệu để điều tra, không tự nó chứng minh một actor có hành vi xấu. Cần liên kết với quyết định quyền, cấu hình đã commit và tác động thực tế.

## 12. Ví dụ xuyên suốt: tạo lịch gửi báo cáo doanh thu

Giả sử chính sách của tenant có các quy tắc minh họa:

- Người tạo phải có quyền tạo lịch và lập lịch xuất report trong dự án.
- Chỉ được gửi bản tổng hợp cho nhóm nội bộ được phép.
- Mỗi lịch chạy tối đa một lần mỗi ngày và có ngày kết thúc.
- Người nhận và quyền của authority subject được kiểm tra lại trước mỗi lần chạy.
- Các lịch vượt phạm vi thông thường phải qua quy trình riêng; endpoint này không tự nâng quyền.

Một luồng hợp lệ:

1. `user-42` yêu cầu tạo lịch cho `report-81` thuộc `project-17` trong `tenant-a`.
2. Server xác thực actor, xác định tenant và tải report theo quan hệ project–tenant.
3. Server kiểm tra quyền tạo lịch, quyền xuất báo cáo tổng hợp và nhóm `group-finance`.
4. Server kiểm tra thời gian, thời hạn, tần suất và quota.
5. Actor và authority subject được server xác lập; không lấy từ field tự khai.
6. Server ghi lịch version 1, quota reservation, idempotency và audit/outbox trong cùng transaction.
7. Response trả ID, version, trạng thái và lịch đã chấp nhận.
8. Mỗi lần chạy, dispatcher/worker áp dụng quyền hiện tại, kiểm tra người nhận và giới hạn thực thi.

Các request bị sửa phải được xử lý đúng:

| Thay đổi của người gọi | Kết quả mong đợi |
| --- | --- |
| Đổi `reportId` sang report của tenant khác | Không tạo lịch |
| Chọn report trong cùng tenant nhưng ngoài dự án được cấp | Không tạo lịch |
| Đổi nhóm nhận sang nhóm không được chia sẻ dữ liệu | Không tạo lịch |
| Gửi thêm `runAsUserId` là quản trị viên | Không dùng danh tính đó để cấp quyền; từ chối theo schema/chính sách |
| Gửi thêm `status: ACTIVE` hoặc `approvedBy` | Không điều khiển được trạng thái hoặc bằng chứng phê duyệt |
| Đổi tần suất thành mỗi phút | Không chấp nhận cấu hình vượt chính sách |
| Retry cùng key và cùng nội dung sau timeout | Trả lịch cũ theo quyền hiện tại; không giữ quota lần nữa |
| Gửi nhiều key mới để vượt số lịch tối đa | Quota nguyên tử chặn các lịch vượt giới hạn |
| Clone lịch của người có quyền rộng hơn | Phải đánh giá lại theo quyền actor clone, không sao chép quyền rộng |

Sau một tuần, nếu `user-42` bị gỡ khỏi dự án, các lần xuất mới phải dừng theo mô hình quyền đã chọn. Lịch không được tiếp tục chỉ vì thời điểm tạo từng hợp lệ.

Nếu nhóm nhận có thêm một thành viên không đủ điều kiện, hệ thống xử lý theo chính sách đã định nghĩa, chẳng hạn chặn lần xuất hoặc chỉ giao cho các người nhận được phép. Không được âm thầm giao dữ liệu cho người không có quyền.

## 13. Kiểm thử phân quyền tạo lịch

Kiểm thử cần quan sát response, bản ghi lịch, quota, idempotency, audit và khả năng dispatcher tạo công việc. Response từ chối nhưng vẫn để lại một lịch active hoặc giữ quota sai vẫn là lỗi.

| Tình huống | Điều cần kiểm chứng |
| --- | --- |
| Chưa xác thực gọi API tạo | Không tạo lịch, không phát công việc |
| Có quyền đọc report nhưng thiếu quyền tạo lịch | Từ chối theo chính sách, không ngầm cấp quyền tự động hóa |
| Có quyền tạo lịch nhưng thiếu quyền xuất report | Không tạo lịch xuất dữ liệu |
| Đổi tenant hoặc project ID | Không vượt qua ràng buộc thành viên và quan hệ tài nguyên |
| Report cùng tenant nhưng ngoài phạm vi actor | Kiểm tra quyền đối tượng chặn yêu cầu |
| Report ID và project ID không khớp | Không tin riêng từng ID hợp lệ |
| Chọn đích nhận không được chia sẻ dữ liệu | Không tạo lịch dù actor tự xem được report |
| Client tự đặt actor, owner hoặc authority subject | Không thay đổi danh tính đã được server xác lập trái quyền |
| Nhân viên hỗ trợ tạo lịch vượt scope impersonation | Từ chối, giữ được actor thật trong bằng chứng |
| Gửi field nội bộ `approved`, `skipAuthorization`, `status` | Không ảnh hưởng quyết định server |
| Tạo lịch cần duyệt rồi gọi endpoint kích hoạt trực tiếp | Không bỏ qua phê duyệt |
| Tự phê duyệt trong mô hình cấm tự duyệt | Bị chặn theo actor thật |
| Sửa người nhận sau khi được duyệt | Approval cũ không áp dụng cho nội dung mới |
| Thu hồi quyền đồng thời với tạo lịch | Kết quả đúng mốc hiệu lực đã định nghĩa; không chạy mới trái quyền |
| Hai request cùng tranh suất quota cuối | Không vượt quota |
| Hai request đồng thời cùng idempotency key | Một kết quả tạo, không giữ quota hai lần |
| Cùng key nhưng khác report, người nhận hoặc timing | Từ chối xung đột nội dung |
| Lỗi giữa ghi lịch và ghi quota/outbox | Transaction không để lại trạng thái một phần |
| Commit xong nhưng mất response | Retry không tạo thêm lịch |
| Pending approval hết hạn | Không active và giải phóng quota đúng chính sách, kể cả xử lý lặp lại |
| Clone, import hoặc batch request | Áp dụng quyền từng lịch và tổng giới hạn liên quan |
| Resume sau khi mất quyền hoặc hết hạn | Không bật lại bằng quyền cũ |
| Tần suất quá ngắn hoặc thời hạn quá dài | Chặn theo chính sách của action |
| Thời điểm địa phương lặp/không tồn tại | Kết quả theo quy tắc thời gian đã định nghĩa, không phát thêm lần ngoài ý muốn |
| Chạy bù nhiều lần sau downtime | Không vượt chế độ catch-up và giới hạn đã cấp |
| Membership nhóm nhận thay đổi sau khi tạo | Lần chạy mới không gửi cho người nhận trái quyền |
| Report bị mở rộng trường dữ liệu hoặc đổi phạm vi | Không ngầm mở rộng quyền xuất của lịch |
| Message cũ của version bị thu hồi được giao lại | Không kích hoạt lại nội dung đã mất hiệu lực |
| Hai lịch cùng nhắm một tác động tài chính | Bất biến nghiệp vụ vẫn chặn tác động trùng |

Với race condition, dùng điểm đồng bộ để điều khiển thứ tự kiểm tra quyền, giữ quota và commit. Chạy hai request tuần tự không kiểm chứng được cạnh tranh.

Với transaction, đọc lại trạng thái đã commit từ một kết nối độc lập. Kiểm tra cả outbox và quota, không chỉ đếm bản ghi lịch.

Với quyền, kiểm thử cả đường đi được phép và bị cấm cho cùng action. Một hệ thống từ chối mọi request có thể vượt qua toàn bộ test âm nhưng vẫn không đáp ứng chức năng.

Với thời gian, dùng đồng hồ điều khiển được và các trường hợp biên cho starts/ends, múi giờ và chạy bù. Không dựa vào thời điểm test tình cờ chạy để kết luận chính sách đúng.

## 14. Tiêu chí hoàn thành thiết kế

Một thiết kế phân quyền tạo lịch cần trả lời được:

- Ai là actor, owner, authority subject và execution principal?
- Người tạo được phép lập lịch action nào, trên tài nguyên nào, với tham số và người nhận nào?
- Lịch dùng quyền hiện tại hay một ủy quyền bền vững có giới hạn?
- Tần suất, thời hạn, fan-out, quota và chạy bù được kiểm soát ra sao?
- Approval gắn với version và nội dung nào; thay đổi gì bắt buộc xét lại?
- Các đường sửa, clone, import, resume và tạo thay có áp dụng đúng chính sách không?
- Quyền, quota, idempotency, bản ghi lịch và audit có nhất quán khi có lỗi hoặc cạnh tranh không?
- Khi thu hồi quyền, điều gì bị chặn ngay, điều gì đã được chấp nhận và điều gì không thể đảo ngược?
- Lần chạy có tiếp tục giữ quyền theo đối tượng, state machine và bất biến nghiệp vụ không?

Quyết định cho phép tạo lịch phải mô tả được một khả năng thực thi cụ thể và có giới hạn. Khi danh tính, nội dung, tài nguyên, người nhận và thời gian đều được ràng buộc rõ, scheduler mới có thể phục vụ tự động hóa mà vẫn giữ các quy tắc nghiệp vụ của hệ thống.
