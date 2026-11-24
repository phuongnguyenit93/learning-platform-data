# Rate policy exception: quản lý ngoại lệ giới hạn tốc độ an toàn

## 1. Ngoại lệ là một quyết định nghiệp vụ có giới hạn

Trong chương **Rate Policies**, rate policy exception là một quyết định cho phép áp dụng giới hạn tốc độ khác với chính sách mặc định trong một phạm vi cụ thể. Ví dụ: tăng tốc độ nhập dữ liệu cho một đối tác trong 15 phút, hỗ trợ một đợt chuyển đổi đã lên lịch hoặc cấp thêm năng lực tạm thời cho một tác vụ được phê duyệt.

Ngoại lệ không chỉ là cấu hình hiệu năng. Nó thay đổi khả năng tạo hành động, chiếm tài nguyên và tác động đến người dùng khác, nên phải được bảo vệ như một quyền nhạy cảm.

Ví dụ xuyên suốt:

~~~text
Tenant: ACME
Chủ thể: ứng dụng tích hợp CRM_SYNC
Hành động: IMPORT_CUSTOMERS
Mặc định: 10 request/giây, burst 20
Ngoại lệ: 30 request/giây, burst 60
Thời gian: 15 phút
Phạm vi thay đổi: bucket tốc độ theo ứng dụng và hành động này

Các kiểm soát vẫn giữ:
  Quyền nhập dữ liệu vào dự án đích
  Trần chung của tenant
  Giới hạn tốc độ theo số bản ghi
  Quota tổng số bản ghi trong kỳ
  Giới hạn tác vụ đồng thời
  Trần bảo vệ của nền tảng
~~~

Tăng tốc độ request không có nghĩa được nhập dữ liệu ngoài quyền hoặc bỏ giới hạn khối lượng công việc. Nếu mỗi request chứa nhiều bản ghi, bộ kiểm soát theo số bản ghi vẫn có thể là nút giới hạn thực tế.

Mục tiêu của bài là thiết kế ngoại lệ sao cho có thể cấp đúng, áp dụng đúng, hết hạn đúng và thu hồi được; đồng thời ngăn client, retry hoặc thay đổi cấu hình biến nó thành đường bỏ qua các quy tắc nghiệp vụ.

## 2. Phân biệt ngoại lệ với các cơ chế gần giống

| Cơ chế | Ý nghĩa | Ràng buộc quan trọng |
| --- | --- | --- |
| Chính sách mặc định | Giới hạn thông thường cho một loại chủ thể và hành động | Phải có nguồn cấu hình tin cậy |
| Ngoại lệ tạm thời | Thay một phần tham số trong phạm vi đã duyệt | Có chủ thể, mức trần, thời gian và lý do |
| Thay đổi gói hoặc hợp đồng | Điều chỉnh quyền dài hạn | Đi qua luồng thương mại và quyền tương ứng |
| Quota | Tổng quyền tiêu thụ tài nguyên theo một phạm vi/kỳ | Không tự tăng chỉ vì tốc độ tăng |
| Concurrency limit | Số công việc cùng hoạt động | Không tương đương request/giây |
| Miễn kiểm tra tùy ý | Bỏ qua toàn bộ kiểm soát | Không phải mô hình ngoại lệ có giới hạn |

Một cách triển khai nguy hiểm là thêm `if (isVip) return ALLOW;` trước mọi kiểm tra. Cách đó không cho biết bỏ qua giới hạn nào, đến khi nào hoặc ai đã duyệt.

Trong bài, ngoại lệ là một **thay đổi tham số có phạm vi** của policy được chọn. Nó không tạo kết quả allow vô điều kiện.

### 2.1. Request rate và chi phí nghiệp vụ

Nếu mỗi request nhập tối đa 100 bản ghi, giới hạn 30 request/giây có thể tương ứng một lượng công việc lớn hơn nhiều so với request chỉ đọc một bản ghi.

Cần phân biệt các meter:

~~~text
REQUEST_ATTEMPTS      : số lần gọi API
CUSTOMER_IMPORT_ITEMS : số bản ghi được tiếp nhận xử lý
ACTIVE_IMPORT_JOBS    : số tác vụ đang hoạt động
PERIOD_IMPORT_QUOTA   : tổng số bản ghi trong kỳ
~~~

Ngoại lệ trên `REQUEST_ATTEMPTS` không thay đổi các meter khác trừ khi có quyết định riêng được phép. Batch, tham số lọc hoặc loại tác vụ không được dùng để biến một request được nới tốc độ thành công việc không giới hạn.

## 3. Business invariants của một ngoại lệ

### 3.1. Đúng chủ thể, đúng hành động, đúng phạm vi

Một ngoại lệ chỉ có hiệu lực khi đồng thời khớp:

~~~text
tenant
subject hoặc service identity
action/policy dimension
resource scope nếu có
phiên bản chính sách được phê duyệt
khoảng thời gian hiệu lực
trạng thái phê duyệt và thu hồi
~~~

Ngoại lệ của CRM_SYNC không mặc nhiên áp dụng cho mọi ứng dụng trong ACME. Ngoại lệ cho nhập dữ liệu không áp dụng cho xuất dữ liệu hoặc thay quyền quản trị.

Đối với tài nguyên cụ thể, quyền trên đối tượng vẫn được kiểm tra riêng. Khớp policy exception không chứng minh actor được thao tác tài nguyên đó.

### 3.2. Chỉ thay đổi chiều chính sách đã được duyệt

Quyết định cuối cùng có dạng:

~~~text
allow =
    xác thực hợp lệ
    AND quyền trên đối tượng hợp lệ
    AND trạng thái nghiệp vụ cho phép
    AND quota còn đủ
    AND concurrency được phép
    AND mọi rate policy bắt buộc đều cho phép
~~~

Ngoại lệ chỉ biến đổi policy thuộc chiều được cấp. Các kiểm soát còn lại tiếp tục được áp dụng theo phiên bản hiện hành.

Không lấy một giá trị min giữa các giới hạn khác đơn vị rồi cho rằng đã kết hợp đúng. Request/giây, bản ghi/giây và số job đồng thời cần những phép kiểm tra tương ứng.

### 3.3. Có trần và thời hạn rõ ràng

Một ngoại lệ hữu hạn dùng khoảng:

~~~text
starts_at <= decision_time < expires_at
~~~

Tại đúng `expires_at`, ngoại lệ không còn được chọn. Worker cập nhật trạng thái chưa chạy không được kéo dài khoảng đó.

Các tham số cần có giới hạn theo chính sách quản lý ngoại lệ:

- Tốc độ tối đa và burst tối đa.
- Thời lượng tối đa.
- Phạm vi chủ thể và hành động được phép cấp.
- Tổng mức tăng có thể chấp nhận cho tenant hoặc nhóm dịch vụ.
- Người có thẩm quyền duyệt theo mức tăng và rủi ro.

Không diễn giải ngày hết hạn bị thiếu thành “không bao giờ hết hạn”. Một nhu cầu dài hạn nên được quản lý như thay đổi chính sách hoặc quyền chính thức, không bằng chuỗi ngoại lệ vô hạn không được xem xét.

### 3.4. Thay đổi không tạo thêm ngân sách ngoài quyết định

Cấp lại, bật tắt hoặc đổi revision của ngoại lệ không được tự làm đầy bucket. Nếu mỗi thay đổi policy tạo một bucket mới đầy token, người có khả năng yêu cầu nhiều ngoại lệ có thể liên tục nhận burst mới.

Một request cũng không được chọn ngoại lệ nào còn nhiều token nhất hoặc cộng dồn mọi ngoại lệ đang khớp.

Bộ đếm phải có danh tính ổn định theo meter và phạm vi nghiệp vụ. Revision và exception ID phục vụ quyết định chính sách, không mặc nhiên trở thành cách tạo một số dư mới.

### 3.5. Quyết định có thể truy vết

Mỗi ngoại lệ cần liên kết được:

- Ai đề nghị, ai duyệt và theo quyền nào.
- Nội dung và phiên bản đã duyệt.
- Thời gian bắt đầu, kết thúc và thu hồi.
- Policy nguồn cùng các trần bắt buộc.
- Các điểm thực thi đã nhận revision nào.
- Các quyết định sử dụng ngoại lệ hoặc bị từ chối.

Một chuỗi ghi chú “đã đồng ý tăng rate” không đủ xác định chính xác mức tăng và phạm vi đã được phép.

## 4. Ranh giới tin cậy và mô hình đe dọa

### 4.1. Client không được tự chọn trạng thái được miễn

Các trường sau không phải bằng chứng:

~~~json
{
  "tenantId": "tenant-khac",
  "isInternal": true,
  "isVip": true,
  "rateLimitExempt": true,
  "approved": true,
  "allowedRate": 999999,
  "expiresAt": "2099-01-01T00:00:00Z"
}
~~~

Client có thể yêu cầu một mức tăng, nhưng giá trị được phê duyệt và dùng để thực thi phải do server xác định từ dữ liệu có thẩm quyền.

Một header `X-Rate-Exception: true` hoặc exception ID trong request không tự làm ngoại lệ hợp lệ. Resolver phải tự đối chiếu actor, tenant, action, scope và thời gian.

Nếu dùng IP làm một chiều nhận diện, chỉ dùng địa chỉ được xác định qua ingress/proxy tin cậy với quy tắc xử lý header rõ ràng. Không dùng một `X-Forwarded-For` do người gọi tùy ý gửi làm căn cứ cấp ngoại lệ.

### 4.2. Control plane và data plane có quyền khác nhau

**Control plane** tạo, phê duyệt, thay đổi và thu hồi ngoại lệ.

**Data plane** áp dụng chính sách cho các request hoặc công việc thực tế.

Service được gọi API nhập dữ liệu không mặc nhiên được sửa policy giới hạn tốc độ. Người hỗ trợ xem cấu hình cũng không mặc nhiên được duyệt ngoại lệ.

| Chủ thể | Khả năng minh họa | Điều kiện |
| --- | --- | --- |
| Người vận hành tenant | Đề nghị tăng rate | Đúng tenant và ứng dụng quản lý |
| Người duyệt | Duyệt trong thẩm quyền | Đúng phạm vi, mức tăng và thời lượng |
| Bộ thực thi | Đọc policy và tiêu thụ token | Không tự mở rộng spec đã duyệt |
| Người ứng cứu | Thu hồi hoặc xử lý ngoại lệ khẩn | Có quyền chuyên biệt và audit |
| Kiểm toán viên | Đọc quyết định và lịch sử | Có quyền đọc phạm vi liên quan |

Nếu chính sách yêu cầu tách người đề nghị và người duyệt, phải kiểm tra quan hệ đó trong lệnh phê duyệt. Có hai tên role khác nhau nhưng cùng một người thực hiện vẫn có thể vi phạm yêu cầu phân tách.

### 4.3. Các hành vi lạm dụng điển hình

| Hành vi | Lỗ hổng có thể bị khai thác | Kiểm soát |
| --- | --- | --- |
| Đổi tenant hoặc subject | Ngoại lệ tra chỉ bằng ID | Phân quyền và khóa phạm vi tenant |
| Gửi header nội bộ giả | Tin đầu vào từ client | Danh tính được xác thực, ingress tin cậy |
| Dùng ngoại lệ nhập cho API khác | Match URL hoặc prefix quá rộng | Action/policy key chuẩn hóa phía server |
| Xin nhiều ngoại lệ nhỏ | Cộng dồn hoặc chọn mức lớn nhất tùy ý | Quy tắc chồng lấp và ngân sách tổng |
| Bật tắt liên tục | Mỗi revision tạo bucket đầy | Meter key ổn định và chuyển trạng thái bảo toàn |
| Đổi API key | Bucket chỉ gắn với credential ngắn hạn | Chủ thể nghiệp vụ ổn định và trần cấp cha |
| Sửa sau duyệt | Dấu duyệt không gắn nội dung | Spec bất biến hoặc revision/hash được duyệt |
| Gọi lúc cache lỗi | Fail-open thành bỏ mọi kiểm tra | Fallback đã định nghĩa, giữ trần bắt buộc |
| Gửi lại approve/extend | Retry cộng thêm thời hạn | Idempotency và định danh nghiệp vụ |
| Hết hạn nhưng node giữ cache | Chỉ dựa trạng thái APPROVED | Predicate thời gian và kiểm soát phiên bản |

### 4.4. Chuẩn hóa hành động trước khi match

Một hành động nghiệp vụ có thể đi qua nhiều route, phiên bản API hoặc tác vụ nền. Nếu từng route dùng policy key khác nhau, người gọi có thể chia tải qua các đường tương đương.

Server nên ánh xạ request đã được phân loại sang action và meter chuẩn. Nội dung request có thể ảnh hưởng trọng số nhưng không được tự đặt tên meter để tránh bucket đang bị giới hạn.

Không dùng một chuỗi URL chưa chuẩn hóa, một tên action do client khai báo hoặc một nhãn debug làm nguồn duy nhất cho quyết định ngoại lệ.

## 5. Vòng đời, phê duyệt và thay đổi ngoại lệ

### 5.1. State machine của quyết định

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING: Gửi đề nghị
    PENDING --> APPROVED: Duyệt spec cụ thể
    PENDING --> REJECTED: Từ chối
    APPROVED --> REVOKED: Thu hồi
    APPROVED --> EXPIRED: Ghi nhận đã hết hạn
    REJECTED --> [*]
    REVOKED --> [*]
    EXPIRED --> [*]
~~~

`APPROVED` không đồng nghĩa có hiệu lực ở mọi thời điểm. Một ngoại lệ đã duyệt nhưng chưa đến `starts_at` không được dùng; ngoại lệ qua `expires_at` cũng không được dùng dù trạng thái chưa đổi.

Việc triển khai xuống điểm thực thi có tiến độ riêng. “Đã duyệt trong database” và “mọi điểm thực thi đã nhận policy” không phải cùng một sự kiện.

### 5.2. Phê duyệt phải gắn với spec đầy đủ

Spec cần bao gồm tối thiểu:

~~~text
tenant, subject, action, scope
policy dimension
base policy revision
rate, burst và đơn vị
starts_at, expires_at
lý do và căn cứ năng lực
các giới hạn có thể và không thể nới
~~~

Một dấu duyệt chỉ trên exception ID là không đủ nếu các trường trên còn được sửa trực tiếp.

Có thể lưu một hash của spec chuẩn hóa cùng revision được duyệt. Hash giúp ràng buộc nội dung trong quy trình; nó không thay thế phân quyền, bảo vệ đường ghi hoặc chứng minh một actor bất kỳ có thẩm quyền duyệt.

### 5.3. Sửa nội dung sau duyệt

Nếu thay subject, action, rate, burst hoặc thời hạn:

1. Tạo revision/spec mới hoặc một quyết định mới.
2. Đánh giá lại mức trần và thẩm quyền.
3. Duyệt đúng nội dung mới.
4. Kích hoạt theo quy tắc thay thế đã thiết kế.
5. Giữ lịch sử của revision cũ.

Không sửa `expires_at` tại chỗ mà vẫn giữ bằng chứng “đã duyệt” cũ như thể không có gì thay đổi.

Gia hạn là một thay đổi cần thẩm quyền. Retry cùng lệnh gia hạn không được cộng thêm một khoảng thời gian mỗi lần.

### 5.4. Phê duyệt không phải quyền dùng một lần

Một ngoại lệ rate thường được dùng cho nhiều request trong khoảng hiệu lực. Không cần “tiêu thụ phê duyệt” sau request đầu tiên như một lệnh thanh toán một lần.

Điều cần chống lặp là thao tác tạo, duyệt, gia hạn và các quyền lợi tăng ngân sách riêng nếu có. Việc sử dụng nhiều request vẫn bị kiểm soát bởi tốc độ, burst, quota và các giới hạn liên quan.

Nhầm hai mô hình có thể gây hai lỗi ngược nhau: ngoại lệ hết tác dụng sau request đầu, hoặc một phê duyệt duy nhất được dùng để tạo vô hạn ngoại lệ mới.

## 6. Mô hình dữ liệu và lệnh quản lý

### 6.1. Một spec tối thiểu

Lược đồ PostgreSQL minh họa cho ngoại lệ theo tenant, subject, action và một chiều policy:

~~~sql
CREATE TABLE rate_policy_exception (
    tenant_id UUID NOT NULL,
    exception_id UUID NOT NULL,
    subject_id UUID NOT NULL,
    action_code TEXT NOT NULL,
    dimension_code TEXT NOT NULL,
    base_policy_revision BIGINT NOT NULL CHECK (base_policy_revision > 0),
    spec_revision BIGINT NOT NULL CHECK (spec_revision > 0),
    refill_units_per_second NUMERIC(18, 6) NOT NULL
        CHECK (refill_units_per_second > 0),
    burst_units BIGINT NOT NULL CHECK (burst_units > 0),
    starts_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    state TEXT NOT NULL CHECK (
        state IN ('DRAFT', 'PENDING', 'APPROVED',
                  'REJECTED', 'REVOKED', 'EXPIRED')
    ),
    requested_by UUID NOT NULL,
    approved_by UUID,
    approved_spec_hash BYTEA,
    approved_at TIMESTAMPTZ,
    reason TEXT NOT NULL,
    PRIMARY KEY (tenant_id, exception_id),
    CHECK (expires_at > starts_at),
    CHECK (approved_by IS NULL OR approved_by <> requested_by),
    CHECK (
        state NOT IN ('APPROVED', 'REVOKED', 'EXPIRED')
        OR (
            approved_by IS NOT NULL
            AND approved_spec_hash IS NOT NULL
            AND approved_at IS NOT NULL
        )
    )
);
~~~

Lược đồ ví dụ chọn chính sách tách người đề nghị và người duyệt. Nếu sản phẩm có quy tắc khác, phải mô hình hóa quyền tương ứng, không bỏ kiểm tra chỉ để một lệnh cụ thể chạy được.

Các mức tối đa, thời lượng tối đa, tư cách người duyệt, resource scope và quyền với subject vẫn cần kiểm tra từ chính sách server. Khóa ngoại ghép cần giữ các quan hệ trong tenant phù hợp.

Không dùng kiểu số thực nhị phân cho tham số nếu cần tính token chính xác theo đơn vị nhỏ nhất. Bộ thực thi có thể dùng fixed-point hoặc một biểu diễn số có độ chính xác đã định nghĩa.

### 6.2. Lệnh duyệt phải là một transaction

Luồng tham chiếu:

1. Xác thực actor và quyền duyệt trong tenant.
2. Nhận quyền xử lý idempotency.
3. Khóa policy scope hoặc bản ghi điều phối cho phạm vi liên quan.
4. Khóa exception và kiểm tra revision/trạng thái.
5. Kiểm tra spec, giới hạn quản lý ngoại lệ và các ngoại lệ chồng lấp.
6. Lưu bằng chứng duyệt đúng spec.
7. Ghi revision policy mới và outbox triển khai.
8. Ghi audit và kết quả idempotency.
9. Commit rồi mới trả kết quả.

Khóa riêng exception không ngăn hai exception khác ID được duyệt đồng thời cho cùng phạm vi. Cần một điểm điều phối chung hoặc ràng buộc tương đương để bảo vệ quy tắc chồng lấp và ngân sách tổng.

### 6.3. Mã giả tầng lệnh

~~~java
ApprovalResult approve(Actor actor, ApproveExceptionCommand cmd, String key) {
    TenantId tenant = actor.verifiedTenant();
    access.requireCanAttemptApproval(actor, tenant, cmd.exceptionId());

    return transactions.required(() -> {
        IdempotencyDecision idem = idempotency.claimOrReplay(
            tenant, actor.id(), "APPROVE_RATE_EXCEPTION_V1",
            key, requestHash.of(cmd)
        );

        if (idem.isReplay()) {
            access.requireCanReadApproval(actor, idem.result());
            return idem.result();
        }

        ScopeKey scope = exceptions.readVerifiedScope(tenant, cmd.exceptionId());
        policyScopes.lock(scope);
        RateException exception = exceptions.lock(tenant, cmd.exceptionId());

        policy.requireScopeUnchanged(scope, exception);
        access.requireCurrentApprovalAuthority(actor, exception);
        policy.requirePendingRevision(exception, cmd.expectedRevision());
        policy.requireWithinExceptionCeilings(exception);
        policy.requireNoConflictingApprovedScope(exception);
        policy.requireSeparationOfDuties(actor, exception);

        Instant decisionTime = databaseClock.currentInstant();
        policy.requireStillApprovable(exception, decisionTime);

        ApprovedSpec approved = approvals.bindExactSpec(actor, exception);
        PolicyRevision revision = policyScopes.advanceRevision(scope);
        exceptions.markApproved(exception, approved, revision);
        outbox.appendPolicyUpdate(scope, revision);
        audit.appendApproval(actor, exception, approved);

        ApprovalResult result = ApprovalResult.accepted(
            exception.id(), revision, "PENDING_ENFORCEMENT"
        );
        idempotency.complete(idem.requestId(), result);
        return result;
    });
}
~~~

Đây là mã giả. Các repository phải thật sự thực hiện giao thức khóa và tenant scope được mô tả. Nếu đọc scope trước khi khóa, cần kiểm tra nó không thay đổi như trong ví dụ; một thiết kế khác có thể dùng scope bất biến ngay từ khi tạo.

Lời gọi ra hệ thống enforcement không nằm trong transaction SQL. Outbox làm thay đổi có thể chuyển giao và retry, nhưng không làm mọi điểm thực thi cập nhật tức thời.
