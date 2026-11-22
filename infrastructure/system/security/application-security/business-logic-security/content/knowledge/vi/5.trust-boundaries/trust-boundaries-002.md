# Ranh giới ứng dụng và cơ sở dữ liệu — Application to database boundary

## 1. Vì sao đây là ranh giới tin cậy nghiệp vụ?

Khi một request đi vào backend, ứng dụng có thể dùng quyền truy cập database để thực hiện những thay đổi mà caller không được tự làm: duyệt đề nghị, thay đổi giá, giữ ngân sách hoặc tạo lệnh đặt hàng.

Database thường thấy tài khoản kết nối của ứng dụng. Nó không tự biết người dùng HTTP nào đang gọi, thuộc tenant nào hoặc có quyền duyệt đối tượng nào. Ứng dụng đang chuyển một ý định từ caller thành thao tác bằng quyền của chính mình.

Đó là lý do ranh giới ứng dụng–database cần được bảo vệ:

> Mỗi thao tác đọc/ghi phải chuyển đúng danh tính, phạm vi và quy tắc nghiệp vụ thành những điều kiện được thực thi nhất quán trên dữ liệu.

Một truy vấn được tham số hóa có thể an toàn trước việc chèn cú pháp SQL nhưng vẫn thực hiện một hành động trái nghiệp vụ. Ví dụ, cập nhật `approved = true` cho một đề nghị của tenant khác vẫn sai dù mọi tham số đều được bind đúng.

Bài này thuộc chương **Trust Boundaries**, tập trung vào quyền theo đối tượng, dữ liệu có thẩm quyền, constraint, transaction, kiểm soát cạnh tranh và idempotency tại nơi ứng dụng tác động tới dữ liệu.

## 2. Hai danh tính không nên bị nhập làm một

| Danh tính | Được dùng ở đâu? | Chứng minh được gì? |
| --- | --- | --- |
| Actor nghiệp vụ | Ngữ cảnh request, job hoặc message. | Người dùng/service nào yêu cầu hành động và có quyền gì. |
| Database principal | Kết nối từ ứng dụng tới database. | Kết nối được phép chạy những thao tác dữ liệu nào theo quyền đã cấp. |

Nếu mọi request dùng cùng một database role, role đó không phân biệt được nhân viên, quản lý hay tenant. Các khác biệt phải được ứng dụng kiểm tra và biểu diễn qua truy vấn, context được quản lý hoặc chính sách dữ liệu phù hợp.

Ví dụ:

```text
Nhân viên tenant A
    → API ứng dụng
    → kết nối bằng app_runtime_role
    → bảng purchase_request của nhiều tenant
```

Nếu API nhận `requestId` rồi thực hiện cập nhật không kiểm tra phạm vi, database có thể chấp nhận hoàn toàn vì role ứng dụng có quyền ghi bảng. Hệ thống đã dùng quyền rộng của mình để thực hiện yêu cầu vượt quyền của caller.

Trong job hoặc consumer, actor vẫn cần được xác định theo nghiệp vụ: service thực thi, nguồn lệnh và căn cứ cho phép. Việc xử lý nền không biến mọi yêu cầu thành lệnh hợp lệ của quản trị viên.

## 3. Ví dụ xuyên suốt và những bất biến cần giữ

Xét quy trình đề nghị mua hàng với chính sách minh họa:

- Mỗi đề nghị thuộc một tenant và một đơn vị.
- Người lập không được tự duyệt.
- Người duyệt phải có quyền trên đơn vị và đủ hạn mức.
- Chỉ nội dung đã gửi duyệt mới được duyệt.
- Sửa nội dung trọng yếu làm tăng phiên bản nghiệp vụ và vô hiệu duyệt cũ.
- Gửi đặt hàng chỉ được chấp nhận cho đúng phiên bản đã duyệt.
- Một phiên bản đề nghị không được tạo hai thao tác đặt hàng đang có hiệu lực.
- Nếu có giữ ngân sách, tổng đã chiếm dụng không được vượt ngân sách được phép.

Các bất biến chính:

```text
I1. Mọi đọc/ghi đều thuộc đúng tenant và phạm vi đối tượng của actor.

I2. Quyết định duyệt thuộc về actor đủ quyền,
    khác người lập và gắn đúng businessVersion.

I3. Chuyển trạng thái chỉ đi theo các cạnh được phép.

I4. Kiểm tra rồi ghi không bị một cập nhật cạnh tranh làm mất hiệu lực
    mà hệ thống vẫn chấp nhận kết quả như cũ.

I5. Bản ghi thao tác nghiệp vụ không bị nhân đôi bởi retry.

I6. Các thay đổi cục bộ tạo thành một quyết định
    được commit hoặc rollback theo cùng ranh giới transaction.

I7. Tác động bên ngoài được gắn với ý định đã commit
    và có cơ chế xử lý lặp/kết quả chưa rõ.
```

Không phải mọi bất biến đều có thể nằm trong một `CHECK`. Phân công đúng trách nhiệm giữa ứng dụng và database giúp bảo vệ chúng trên mọi đường ghi.

## 4. Dữ liệu nằm trong database vẫn cần nguồn gốc rõ ràng

Một số field có thể bắt nguồn từ client:

- Ghi chú, địa chỉ giao hoặc thông tin người dùng khai.
- Mã hàng và số lượng muốn mua.
- Mã báo giá muốn áp dụng.
- Phiên bản mà người dùng đã xem.

Những field khác phải do hệ thống xác lập theo chính sách:

- Tenant và quan hệ sở hữu sau khi kiểm chứng ngữ cảnh.
- Người phê duyệt.
- Giá và tổng tiền có hiệu lực.
- Trạng thái quyết định.
- Phiên bản nội dung đã được duyệt.
- Mã thao tác đặt hàng và căn cứ giữ ngân sách.

Nếu một endpoint từng lưu trực tiếp `approvedBy` do client gửi, việc đọc lại field đó từ database không biến nó thành bằng chứng phê duyệt hợp lệ.

Cần phân biệt:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| Đã lưu | Dữ liệu tồn tại trong kho lưu trữ. |
| Đúng cấu trúc | Dữ liệu đáp ứng kiểu, miền giá trị hoặc schema. |
| Có nguồn hợp lệ | Dữ liệu được tạo qua đường ghi có thẩm quyền. |
| Đúng hiện tại | Dữ liệu còn phù hợp với phiên bản, trạng thái và thời điểm ra quyết định. |

Một dữ kiện có thể đáp ứng thuộc tính đầu nhưng không đáp ứng các thuộc tính còn lại.

## 5. Từ request sang command có phạm vi

### 5.1. Không cập nhật entity bằng mọi field trong body

Một body như sau không nên được bind nguyên khối vào entity rồi lưu:

```json
{
  "tenantId": "tenant-other",
  "status": "APPROVED",
  "approvedBy": "director-01",
  "approvedBusinessVersion": 9,
  "totalMinor": 1
}
```

Caller có thể đang yêu cầu duyệt một đề nghị, nhưng không có quyền tự chọn các sự thật trên.

Command tối thiểu có thể là:

```java
record ApproveRequestCommand(
    UUID requestId,
    long expectedBusinessVersion,
    String comment
) {}
```

Actor đến từ cơ chế xác thực. Tenant phải được đối chiếu với membership và đối tượng. Quyền duyệt, số tiền và phiên bản hiện tại được lấy từ nguồn server có thẩm quyền.

`expectedBusinessVersion` chỉ nói “đây là phiên bản tôi đã xem”, không chứng minh phiên bản đó đang tồn tại hoặc được phép duyệt.

### 5.2. Tham số hóa giải quyết cú pháp, quyền giải quyết ý nghĩa

Truy vấn tham số hóa:

```sql
SELECT id, tenant_id, state, business_version
FROM purchase_request
WHERE tenant_id = :tenant_id
  AND id = :request_id;
```

giúp biểu diễn điều kiện theo tenant và đối tượng. `:tenant_id` vẫn phải đến từ ngữ cảnh được kiểm chứng; thay một field client thành tham số SQL không làm nó đáng tin.

Giá trị dữ liệu cần được bind bằng cơ chế của driver/ORM. Những phần cấu trúc không thể bind như tên cột sắp xếp phải được chọn từ tập cho phép do ứng dụng định nghĩa, tránh ghép trực tiếp chuỗi caller gửi.

Cả hai lớp đều cần thiết: bảo vệ cấu trúc câu lệnh và kiểm tra hành động mà câu lệnh thực hiện.

## 6. Database constraint: lớp bảo vệ dữ liệu chung

Constraint hữu ích vì mọi đường ghi chịu cùng điều kiện, bao gồm API, batch và công cụ nội bộ dùng role tương ứng. Chúng nên bảo vệ những thuộc tính có thể biểu diễn chắc chắn ở tầng dữ liệu.

| Quy tắc | Ứng dụng | Database |
| --- | --- | --- |
| Actor có quyền duyệt đơn vị này | Kiểm tra danh tính và policy. | Có thể hỗ trợ bằng mô hình quyền/chính sách dữ liệu. |
| Số lượng và số tiền trong miền cho phép | Kiểm tra input và nghiệp vụ. | Kiểu, `NOT NULL`, `CHECK` phù hợp. |
| Quan hệ con cùng tenant với cha | Kiểm tra phạm vi và thông báo lỗi. | Khóa ngoại gồm tenant và định danh. |
| Không có hai operation trùng nghiệp vụ | Phối hợp idempotency và trạng thái. | Unique constraint đúng khóa. |
| Kiểm tra và cập nhật cùng quyết định | Tổ chức transaction. | Atomic update, khóa, isolation. |
| Giá được chấp nhận theo hợp đồng | Dùng nguồn và chính sách có thẩm quyền. | Ràng buộc cấu trúc; không tự biết mọi chính sách giá. |

### 6.1. Ví dụ constraint và ý nghĩa NULL

SQL dưới đây dùng cú pháp PostgreSQL để minh họa một phần mô hình:

```sql
CREATE TABLE purchase_request (
    tenant_id UUID NOT NULL,
    id UUID NOT NULL,
    created_by UUID NOT NULL,
    state TEXT NOT NULL,
    business_version BIGINT NOT NULL CHECK (business_version > 0),
    row_version BIGINT NOT NULL CHECK (row_version >= 0),
    total_minor BIGINT NOT NULL CHECK (total_minor >= 0),
    currency TEXT NOT NULL,
    approved_by UUID,
    approved_business_version BIGINT,

    PRIMARY KEY (tenant_id, id),

    CHECK (state IN (
        'DRAFT', 'SUBMITTED', 'APPROVED',
        'DISPATCH_PENDING', 'ORDERED', 'CANCELLED'
    )),

    CHECK (
        approved_by IS NULL OR approved_by <> created_by
    ),

    CHECK (
        state NOT IN ('APPROVED', 'DISPATCH_PENDING', 'ORDERED')
        OR (
            approved_by IS NOT NULL
            AND approved_business_version IS NOT NULL
            AND approved_business_version = business_version
        )
    )
);
```

Các ràng buộc này giữ được một số điều kiện cấu trúc:

- Người được ghi là đã duyệt khác người lập.
- Trạng thái cần phê duyệt phải có đủ tham chiếu phiên bản.
- Số tiền không âm và trạng thái thuộc tập đã định nghĩa.

Chúng chưa chứng minh người duyệt thực sự là actor hiện tại, có quyền trên đơn vị hoặc đủ hạn mức. Role ứng dụng có quyền ghi vẫn có thể đưa một mã người duyệt khác vào nếu đường ghi không được bảo vệ.

Với SQL, một biểu thức `CHECK` có thể không từ chối hàng khi kết quả là `UNKNOWN` do NULL. Vì vậy, chỉ viết `approved_business_version = business_version` chưa thay thế điều kiện `IS NOT NULL` khi nghiệp vụ bắt buộc có giá trị.

`total_minor >= 0` cũng chỉ kiểm tra miền số, không chứng minh giá đúng. Đơn vị tiền nhỏ nhất, loại tiền và quy tắc tính tiền phải được định nghĩa theo nghiệp vụ.

### 6.2. Khóa ngoại cần thể hiện tenant

Ví dụ bảng con:

```sql
CREATE TABLE purchase_request_line (
    tenant_id UUID NOT NULL,
    request_id UUID NOT NULL,
    line_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),

    PRIMARY KEY (tenant_id, request_id, line_id),

    FOREIGN KEY (tenant_id, request_id)
        REFERENCES purchase_request (tenant_id, id)
);
```

Khóa ngoại ghép ngăn một dòng hàng khai tenant A nhưng trỏ tới đề nghị chỉ tồn tại dưới tenant B. Nó không xác nhận caller có quyền sửa đề nghị A; quyền đó vẫn cần được thực thi.

## 7. Chuyển trạng thái và phiên bản phải được bảo vệ khi ghi

Một mẫu dễ sai:

```text
Đọc đề nghị.
Kiểm tra state == SUBMITTED.
Kiểm tra nội dung và quyền duyệt.
Một request khác sửa nội dung.
Ghi state = APPROVED theo kết quả kiểm tra trước đó.
```

Khoảng cách giữa kiểm tra và sử dụng kết quả là vấn đề TOCTOU. Cách bảo vệ phải nối quyết định với đúng dữ liệu được kiểm tra.

Một cập nhật lạc quan minh họa:

```sql
UPDATE purchase_request
SET state = 'APPROVED',
    approved_by = :authenticated_actor_id,
    approved_business_version = business_version,
    row_version = row_version + 1
WHERE tenant_id = :trusted_tenant_id
  AND id = :request_id
  AND state = 'SUBMITTED'
  AND business_version = :expected_business_version
  AND row_version = :expected_row_version
  AND created_by <> :authenticated_actor_id;
```

Ứng dụng phải kiểm tra số dòng được cập nhật bằng đúng một. Nếu bằng không, không được tiếp tục tạo kết quả duyệt như thể lệnh đã thành công.

SQL này giả định quyền trên đơn vị và hạn mức đã được kiểm tra theo chiến lược nhất quán thích hợp. Điều kiện `created_by <> actor` không thay thế toàn bộ phân quyền.

### 7.1. Business version và row version

- `businessVersion` tăng khi nội dung có ý nghĩa với quyết định thay đổi.
- `rowVersion` giúp phát hiện cập nhật trên bản ghi, kể cả đổi trạng thái.

Một lần duyệt có thể tăng row version mà không tăng business version. Đổi số lượng hoặc nhà cung cấp phải tăng phiên bản nội dung và vô hiệu hiệu lực duyệt cũ theo chính sách.

Nếu nội dung nằm trong bảng dòng hàng, mọi đường sửa dòng hàng cần phối hợp với phiên bản ở bản ghi cha. Khóa hàng cha chỉ có tác dụng bảo vệ giao thức này khi các đường sửa liên quan cũng tuân theo nó.

Không chỉ bảo vệ phương thức “edit” chính. Import, bulk update và thao tác sửa tay cũng có thể làm nội dung thay đổi mà quên tăng phiên bản.

## 8. Transaction không tự giữ mọi bất biến nhiều hàng

Transaction bảo vệ nhóm thay đổi theo các bảo đảm của database. Nó không tự biết quy tắc như “tổng các khoản giữ ngân sách không vượt hạn mức”.

Ví dụ hai transaction cùng đọc:

```text
Ngân sách còn lại: 10 triệu.

T1 thấy còn 10 triệu → định giữ 7 triệu.
T2 thấy còn 10 triệu → định giữ 7 triệu.

Nếu cả hai cùng ghi một khoản giữ riêng:
  tổng mới = 14 triệu > 10 triệu.
```

Mỗi transaction có thể commit nguyên vẹn nhưng kết quả tổng vẫn sai nếu cơ chế cô lập/khóa không bảo vệ bất biến.

### 8.1. Một điểm phối hợp cho ngân sách chung

Có thể biểu diễn phần còn được giữ bằng một hàng ngân sách có thẩm quyền:

```sql
UPDATE department_budget
SET available_minor = available_minor - :amount_minor,
    reserved_minor = reserved_minor + :amount_minor,
    version = version + 1
WHERE tenant_id = :tenant_id
  AND department_id = :department_id
  AND budget_period_id = :budget_period_id
  AND currency = :currency
  AND :amount_minor > 0
  AND available_minor >= :amount_minor;
```

Điều kiện cần:

- Hàng ngân sách được xác định duy nhất theo đúng phạm vi.
- Các cột số tiền không NULL, không âm và có miền đủ để tránh tràn số.
- Kiểm tra đúng một hàng được cập nhật.
- Tạo bản ghi giữ ngân sách và cập nhật đề nghị trong cùng transaction.
- Nếu bước sau thất bại, rollback cả việc giảm phần khả dụng.
- Hủy hoặc chuyển giữ chỗ thành đã dùng phải là chuyển đổi hợp lệ, tránh hoàn trả hai lần.

Nếu dùng cách đọc tổng các khoản giữ rồi chèn một hàng mới, cần cơ chế khóa/isolation phù hợp cho tập dữ liệu đó. Khóa một khoản giữ riêng không tự bảo vệ tổng ngân sách chung.

### 8.2. Chọn cơ chế theo bất biến

| Cơ chế | Vai trò | Giới hạn cần hiểu |
| --- | --- | --- |
| Khóa bi quan | Buộc thao tác liên quan phối hợp trên dữ liệu khóa. | Phải khóa đúng phạm vi và thống nhất giao thức giữa các đường ghi. |
| Cập nhật có điều kiện | Kiểm tra điều kiện và ghi trong cùng câu lệnh. | Không tự bao phủ quyền hoặc dữ liệu ở nguồn khác. |
| Kiểm soát phiên bản | Phát hiện dữ liệu đã đổi trước khi chấp nhận ghi. | Mọi thay đổi liên quan cần cập nhật phiên bản thích hợp. |
| Mức cô lập mạnh hơn | Ngăn hoặc phát hiện thêm các cách xen kẽ gây sai. | Có thể phát sinh lỗi giao dịch cần retry toàn quyết định. |
| Constraint | Giữ điều kiện dữ liệu trên các đường ghi. | Không tự biểu diễn toàn bộ workflow hoặc chính sách động. |

Deadlock hoặc lỗi tuần tự hóa có thể cần retry. Khi retry, phải thực hiện lại các kiểm tra trên dữ liệu phù hợp; không chỉ chạy lại phần ghi với quyết định cũ.

## 9. Retry và khóa duy nhất của thao tác nghiệp vụ

Client có thể không nhận được response dù transaction đã commit. Nếu gửi lại tạo một lệnh đặt hàng mới, bất biến bị phá.

Một khóa nghiệp vụ minh họa:

```sql
ALTER TABLE dispatch_operation
ADD CONSTRAINT uq_dispatch_business_operation
UNIQUE (
    tenant_id,
    request_id,
    business_version,
    operation_type
);
```

Các cột khóa cần không NULL và phản ánh đúng chính sách. Mô hình này giả định một operation cho loại tác động trên mỗi phiên bản đề nghị. Nếu nghiệp vụ cho phép nhiều lần giao hoặc đặt bổ sung, phải bổ sung định danh phân biệt hợp lệ thay vì bỏ bảo đảm chống trùng.

### 9.1. Idempotency key và khóa nghiệp vụ hỗ trợ nhau

- Idempotency key nhận diện các lần gửi được coi là cùng yêu cầu.
- Khóa nghiệp vụ ngăn hai request khác key tạo cùng một tác động bị cấm.
- Ràng buộc trạng thái ngăn tác động ở thời điểm không hợp lệ.
- Phân quyền ngăn một bên lấy kết quả hoặc thực hiện operation ngoài phạm vi.

Cùng key nhưng khác payload cần được xử lý theo hợp đồng rõ ràng. Trước khi trả kết quả cũ, phải kiểm tra quyền phù hợp.

`SELECT` thấy operation chưa tồn tại rồi `INSERT` không thay thế unique constraint. Hai transaction có thể cùng thấy “chưa có”.

### 9.2. Không nuốt lỗi constraint rồi tiếp tục tác động

Nếu chèn operation bị trùng, không coi đó là một operation mới hợp lệ rồi vẫn gọi đối tác. Cần đọc/đối chiếu operation đã có trong phạm vi quyền và trả trạng thái phù hợp theo transaction semantics của database.

Tương tự, số dòng cập nhật bằng không không phải thành công im lặng. Nó có thể biểu thị xung đột, hết quota hoặc trạng thái không còn phù hợp.

## 10. Ranh giới transaction trong mã ứng dụng

Một lần duyệt có thể cần đồng thời:

1. Tạo bản ghi quyết định.
2. Cập nhật trạng thái và phiên bản đề nghị.
3. Ghi audit cục bộ.
4. Ghi outbox để thông báo sau commit.

Nếu chỉ một phần được commit, dữ liệu có thể tự mâu thuẫn.

```java
// Minh họa kiến trúc; các abstraction cần được hiện thực đúng ở ứng dụng.
ApprovalResult approve(
        Actor actor, UUID tenantId, ApproveRequestCommand command) {

    return transaction.required(() -> {
        PurchaseRequest request = requests.loadForUpdate(
            tenantId, command.requestId()
        ).orElseThrow(NotFound::new);

        access.requireCanApprove(actor, request);
        request.requireSubmitted();
        request.requireBusinessVersion(command.expectedBusinessVersion());

        ApprovalPolicy policy = policies.applicableTo(request);
        policy.requireDifferentCreator(actor, request);
        policy.requireWithinLimit(actor, request.total(), request.currency());

        Approval approval = approvals.issueFor(
            request, actor, policy, clock.instant()
        );
        request.approve(approval);

        approvals.insert(approval);
        requests.save(request);
        audit.appendApproved(actor, request, approval);
        outbox.appendApprovalCreated(approval);

        return ApprovalResult.from(approval);
    });
}
```

Ví dụ giả định các thao tác cục bộ tham gia cùng transaction thực sự. Mở một kết nối khác, chạy tác vụ bất đồng bộ hoặc gọi sang service khác không tự thừa hưởng bảo đảm này.

Nếu quyền, chính sách hoặc hạn mức bị đổi đồng thời, cần quyết định cách đồng bộ hoặc thời điểm hiệu lực. Khóa request không tự khóa bảng membership hay trạng thái của một service phân quyền.

Khi một thao tác thất bại, exception không được bị xử lý theo cách khiến phần dữ liệu trước đó vẫn commit ngoài ý định. Cần kiểm tra hành vi transaction thật của framework/driver đang dùng.

## 11. Transaction database không bao trùm tác động HTTP

Một chuỗi dễ gây sai:

```text
Gọi đối tác tạo đơn thành công.
Ghi operation vào database bị lỗi.
Client retry.
Gọi đối tác tạo thêm một đơn.
```

Đảo thứ tự cũng có rủi ro: database đã commit nhưng tiến trình dừng trước khi gọi đối tác.

### 11.1. Outbox nối trạng thái với ý định gửi

Trong cùng transaction cục bộ:

```text
Chuyển APPROVED → DISPATCH_PENDING.
Tạo dispatch_operation có định danh ổn định.
Ghi outbox tham chiếu operation.
Commit.
```

Worker sau đó gửi yêu cầu theo operation đó. Outbox giúp không mất ý định gửi sau commit; nó không tự bảo đảm chỉ giao message một lần.

Worker và đối tác cần idempotency hoặc đối soát phù hợp. Khi timeout, kết quả có thể chưa rõ, không phải chắc chắn chưa có tác động.

### 11.2. Đừng dùng lệnh mới để che kết quả chưa rõ

Nếu đối tác đã tạo đơn nhưng response bị mất, retry bằng một operation ID mới có thể tạo đơn thứ hai.

Giữ mã thao tác ổn định, truy vấn kết quả theo hợp đồng và có đường xử lý trường hợp chưa xác định. Rollback database cục bộ không xóa được đơn đã tạo ở hệ thống khác.

## 12. Quyền database, connection pool và ORM

### 12.1. Quyền kết nối cần phù hợp nhiệm vụ

Một ứng dụng xử lý request thường không cần quyền thay đổi schema hoặc cấp quyền database cho bên khác. Tách quyền chạy ứng dụng, migration và tác vụ quản trị giúp giới hạn tác động của lỗi.

Quyền database bổ sung cho phân quyền nghiệp vụ. Có quyền `UPDATE` bảng không có nghĩa actor được duyệt mọi đề nghị; thiếu quyền schema cũng không tự ngăn được một câu `UPDATE` sai tenant.

Nếu dùng stored procedure để tập trung thao tác, cần xem cả quyền gọi và quyền ghi trực tiếp. Procedure không giữ được bất biến trên toàn hệ thống nếu một đường khác vẫn sửa bảng theo cách bỏ qua quy tắc.

### 12.2. Context tenant và connection pool

Một số hệ thống truyền context actor/tenant vào session database hoặc dùng chính sách lọc ở mức hàng.

Cần bảo đảm:

- Context xuất phát từ ngữ cảnh được ứng dụng kiểm chứng.
- Được thiết lập trong phạm vi rõ và không rò qua request sau.
- Hành vi khi thiếu context được xác định.
- Kết nối được trả về pool không mang context cũ sang tenant khác.
- Job nền và đường truy vấn đặc biệt cũng thiết lập context đúng.
- Các role và đường thực thi có khả năng bỏ qua chính sách được kiểm soát.

Nếu dùng row-level security, phải kiểm tra bằng đúng role runtime và cấu hình triển khai. Một chính sách tồn tại trong schema chưa chứng minh mọi truy vấn thực tế đều chịu chính sách đó.

Database không tự kiểm chứng membership chỉ vì ứng dụng đặt một biến tenant trong session. Độ tin cậy của context vẫn phụ thuộc đường thiết lập và quyền có thể thay đổi nó.

### 12.3. ORM không thay thế quy tắc

ORM giúp ánh xạ và truy cập dữ liệu, nhưng:

- Repository `findById` có thể thiếu phạm vi tenant.
- Entity được bind từ body có thể bị gán field nhạy cảm.
- Bulk/native update có thể bỏ qua validation hoặc cơ chế phiên bản ở tầng entity.
- Flush có thể xảy ra vào thời điểm khác với lúc lập trình viên nghĩ câu lệnh được ghi.
- Dữ liệu đã tải vào bộ nhớ có thể không còn mới.
- Đọc từ replica hoặc cache có thể chưa thấy quyết định vừa commit.

Điểm ra quyết định quan trọng cần dùng dữ liệu và cơ chế nhất quán đáp ứng bất biến, thay vì mặc định mọi lần đọc qua repository đều là sự thật hiện tại.

## 13. Những kiểm thử cần có tại ranh giới

| Tình huống | Kết quả cần chứng minh |
| --- | --- |
| Actor tenant A dùng ID đề nghị tenant B | Không đọc/ghi dữ liệu ngoài phạm vi. |
| Sửa tenant, người duyệt hoặc giá trong body | Không điều khiển được field server quản lý. |
| Nhân viên tự duyệt | Bị chặn theo policy; không có quyết định duyệt mới. |
| Duyệt phiên bản đã xem cũ | Không phê duyệt nội dung mới ngoài ý định. |
| Sửa dòng hàng đồng thời với duyệt | Không có nội dung chưa duyệt mang trạng thái đã duyệt. |
| Hai lệnh cùng giữ ngân sách | Tổng giữ không vượt phần được phép. |
| Hai request khác key cùng gửi đặt hàng | Không tạo hai operation trái bất biến. |
| Retry sau commit nhưng mất response | Nhận trạng thái của cùng operation theo hợp đồng. |
| Lỗi sau ghi quyết định nhưng trước cập nhật trạng thái | Toàn bộ thay đổi cục bộ rollback phù hợp. |
| Lỗi sau cập nhật nhưng trước ghi outbox | Không commit quyết định thiếu ý định cần phát. |
| Worker gửi lặp | Không nhân tác động nhạy cảm. |
| Hủy hoặc hoàn trả lặp | Không tăng ngân sách/tồn khả dụng giả. |
| Đổi tenant trên cùng connection được tái sử dụng | Không thừa hưởng context cũ. |
| Bulk update hoặc công cụ nội bộ | Vẫn chịu bất biến hoặc quyền ngoại lệ rõ ràng. |
| Role runtime gọi đường dữ liệu khác | Không vô tình bỏ qua chính sách đã dựa vào. |

Các kiểm thử về unique constraint, khóa, isolation và rollback cần chạy ở mức tích hợp với database phù hợp. Mock repository không chứng minh được hành vi tranh chấp thật.

Để kiểm tra race condition, chủ động đồng bộ các luồng tại điểm đọc/ghi liên quan. Sau commit, kiểm tra dữ liệu và tác động, không chỉ mã HTTP.

Kiểm thử constraint cũng nên có dữ liệu NULL và quan hệ chéo tenant. Các trường hợp này dễ bị bỏ sót nếu chỉ kiểm tra luồng hợp lệ.

## 14. Bài tập áp dụng

Một endpoint duyệt đề nghị thực hiện:

```text
1. Nhận toàn bộ entity từ body.
2. Kiểm tra người dùng có role MANAGER.
3. SELECT đề nghị bằng id.
4. Nếu chưa duyệt thì gọi đối tác tạo đơn.
5. UPDATE state = ORDERED.
```

Hãy thiết kế lại:

1. Xác định field nào caller được gửi và field nào server xác lập.
2. Bổ sung quyền theo tenant, đơn vị, đối tượng và hạn mức.
3. Gắn bản duyệt với phiên bản nội dung.
4. Chọn constraint và cơ chế cạnh tranh cho từng bất biến.
5. Xác định các thay đổi phải nằm trong cùng transaction.
6. Chuyển tác động bên ngoài sang operation/outbox với định danh ổn định.
7. Viết một kiểm thử tenant chéo, một kiểm thử sửa nội dung đồng thời và một kiểm thử mất response sau commit.

Một thiết kế rõ phải giải thích được không chỉ “đã kiểm tra”, mà còn “điều kiện vẫn được bảo vệ đến lúc commit bằng cơ chế nào”.

## 15. Những điểm cần ghi nhớ

Ranh giới ứng dụng–database là nơi quyền của caller được chuyển thành thao tác bằng quyền dữ liệu của hệ thống. Ứng dụng cần xác lập đúng actor, phạm vi và quyết định; database cần hỗ trợ giữ cấu trúc, quan hệ, tính duy nhất và các điều kiện cập nhật.

Bảo vệ logic nghiệp vụ tại đây cần phối hợp **command có phạm vi, phân quyền theo đối tượng, constraint, transaction và kiểm soát cạnh tranh**. Với tác động bên ngoài, bổ sung operation ổn định, outbox và idempotency/đối soát phù hợp.

Dữ liệu được lưu, truy vấn được tham số hóa hoặc phương thức có transaction đều là các thành phần của bảo đảm. Bất biến chỉ được giữ khi các thành phần đó cùng bảo vệ đúng một quy tắc trên mọi đường đọc/ghi liên quan.
