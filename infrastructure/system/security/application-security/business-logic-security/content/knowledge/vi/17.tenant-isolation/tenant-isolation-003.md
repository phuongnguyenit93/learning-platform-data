# Tenant scoped commands: ràng buộc lệnh nghiệp vụ theo tenant

## 1. Một lệnh đúng nghiệp vụ vẫn có thể tác động sai tenant

Một hệ thống quản lý chi phí phục vụ nhiều doanh nghiệp. An có quyền duyệt ở tenant A. An gọi API duyệt với ID đề nghị thuộc tenant B. Ứng dụng kiểm tra role `EXPENSE_APPROVER`, tìm hồ sơ bằng ID và cập nhật trạng thái thành `APPROVED`.

Role của An hợp lệ ở A, state machine của hồ sơ B cũng cho phép duyệt, nhưng hai điều đó không tạo quyền duyệt hồ sơ B.

**Tenant scoped command** là lệnh nghiệp vụ có phạm vi tenant được xác minh và giữ nhất quán từ lúc tiếp nhận tới khi cập nhật dữ liệu, phát sự kiện và thực hiện tác động liên quan.

Một lệnh như `approveExpense`, `changePayee` hay `startPayment` phải trả lời được:

- Chủ thể đang hành động trong tenant nào và có quyền sử dụng ngữ cảnh đó không?
- Đối tượng đích và các tham chiếu phụ thuộc có thuộc phạm vi được phép không?
- Quyền hành động được lấy từ đúng tenant hay bị gộp từ nơi khác?
- Cập nhật, idempotency, cache và thông điệp có cùng giữ phạm vi đó không?
- Nếu ngữ cảnh tenant thiếu hoặc không khớp, hệ thống có dừng trước tác động không?

Trong bảo vệ logic nghiệp vụ, tenant là một phần của căn cứ phân quyền và định danh dữ liệu. Nó không chỉ là bộ lọc giao diện hoặc một trường dùng cho báo cáo.

## 2. Tenant selection khác với tenant authorization

Người dùng có thể chọn tenant qua URL, header, subdomain hoặc giao diện chuyển tổ chức. Giá trị được chọn chỉ cho biết họ muốn thao tác ở đâu, không chứng minh họ được phép ở đó.

| Dữ liệu | Ý nghĩa đúng | Điều không được tự suy ra |
|---|---|---|
| `tenantId` trên route | Tenant mà request nhắm tới | Người gọi là thành viên hoặc có quyền hành động |
| Tenant trong token | Claim đã được xác thực theo cơ chế token | Membership vẫn còn hiệu lực nếu hệ thống yêu cầu kiểm tra hiện hành |
| Tenant đang hiển thị trên UI | Ngữ cảnh điều hướng của client | Mọi request do client gửi đều được phép |
| Tenant của đối tượng trong DB | Nguồn sở hữu/phạm vi của bản ghi | Người biết ID đối tượng được phép dùng nó |
| Tenant do service chuyển tiếp | Ngữ cảnh được service khai báo | Nguồn khai và quyền đại diện đã được xác minh |

### 2.1. Một người có thể có quyền khác nhau ở nhiều tenant

An có thể là quản trị viên ở A và chỉ được xem ở B. Khi xử lý lệnh trong B, không được dùng hợp của mọi role An có trên toàn hệ thống.

```text
Sai:
    An có APPROVER ở đâu đó → An được duyệt tại B.

Đúng:
    xác định tenant B
    → kiểm tra membership/quyền trong B
    → kiểm tra quyền trên hồ sơ cụ thể của B.
```

Ngay cả khi người dùng thuộc cả A và B, mỗi lệnh vẫn cần một phạm vi rõ. Tư cách thành viên nhiều tenant không làm mọi dữ liệu giữa các tenant được dùng lẫn nhau.

### 2.2. Các nguồn tenant không được mâu thuẫn âm thầm

Nếu route là A, header là B và body là C, cần hợp đồng rõ về nguồn được chấp nhận và cách xử lý mâu thuẫn. Một thiết kế đơn giản là chỉ nhận tenant nghiệp vụ từ route, bỏ tenant khỏi DTO và từ chối dữ liệu mâu thuẫn khi có thể xuất hiện.

Không để mỗi lớp tự chọn một nguồn khác nhau: controller kiểm tra A, repository ghi B, còn event mang C. Nếu token được ràng buộc tenant cụ thể, route phải phù hợp ràng buộc đó theo hợp đồng xác thực.

## 3. Mô hình ngữ cảnh tenant đã được xác minh

Ngữ cảnh xử lý nên thể hiện tối thiểu:

```text
chủ thể thực hiện
+ tenant mục tiêu đã được xác minh
+ hành động
+ ngữ cảnh đại diện nếu có
+ các căn cứ quyền cần thiết
```

Ứng dụng có thể dùng một kiểu như `AuthorizedTenantContext` để phân biệt ngữ cảnh đã kiểm tra với `tenantId` thô từ request.

Tên kiểu không tự tạo bảo đảm an ninh. Cần kiểm soát nơi xây ngữ cảnh và không deserialize một object mang tên “authorized” trực tiếp từ body rồi tin nó.

### 3.1. Phân biệt kiểm tra ngữ cảnh với quyền theo đối tượng

Kiểm tra membership trong tenant là bước nền. Người dùng vẫn có thể chỉ được duyệt phòng A, chỉ được sửa hồ sơ của mình hoặc không được tự duyệt.

Một quyết định cho lệnh mới có thể được diễn đạt:

```text
được xác thực
AND được dùng tenant mục tiêu
AND có quyền hành động trong tenant đó
AND đối tượng thuộc phạm vi được phép
AND các quan hệ và bất biến nghiệp vụ đạt
AND trạng thái, căn cứ và version phù hợp
```

Tenant isolation không thay thế authorization theo đối tượng. Ngược lại, một role đủ rộng trong tenant cũng không được vượt ranh giới sang tenant khác.

### 3.2. Thiếu tenant phải dừng, không mở rộng truy vấn

Một lỗi nguy hiểm trong query builder là:

```text
nếu có tenantId thì thêm WHERE tenant_id = ...
nếu thiếu tenantId thì truy vấn toàn bộ
```

Với repository dùng cho lệnh tenant, thiếu ngữ cảnh phải là lỗi, không phải yêu cầu chạy ở chế độ toàn hệ thống. Tương tự, không fallback sang tenant mặc định hoặc tenant đầu tiên mà người dùng từng truy cập để hoàn thành lệnh mơ hồ.

## 4. Thiết kế hợp đồng command ở ranh giới API

Một lệnh duyệt có thể có dạng:

```http
POST /tenants/{tenantId}/expense-requests/{expenseId}/approve
Content-Type: application/json
Idempotency-Key: client-command-key

{
  "expectedVersion": 12,
  "basisPackageId": "basis-4",
  "note": "Đã đối chiếu chứng từ"
}
```

Trong thiết kế này:

- Tenant mục tiêu lấy từ route rồi được xác minh với danh tính người gọi.
- Body chỉ chứa đầu vào của hành động duyệt.
- Người duyệt, tenant của bản ghi, trạng thái đích và thời điểm ghi nhận do server xác định.
- `expectedVersion` và `basisPackageId` biểu thị căn cứ người gọi muốn xử lý; server vẫn phải đối chiếu với dữ liệu hiện tại.

Không cho body tự gán `actorId`, `approvedBy`, `state`, `tenantId` của aggregate hoặc thông tin membership để vượt kiểm tra.

### 4.1. Lệnh tạo phải lấy tenant từ ngữ cảnh đáng tin

Khi tạo hồ sơ, server đặt tenant từ ngữ cảnh đã được phép. Không nhận một entity có `tenantId` tùy ý rồi lưu bằng repository tổng quát.

Một bản ghi mới cần thỏa mãn các ràng buộc tenant của dữ liệu liên quan ngay từ lúc tạo. Không đợi đến khi duyệt hoặc chi trả mới phát hiện nó tham chiếu nhà cung cấp hay tài khoản nhận tiền của tenant khác.

### 4.2. Tenant của aggregate không phải field sửa thông thường

Không để `PATCH` đổi tenant của một hồ sơ như đổi ghi chú. Việc chuyển dữ liệu giữa tenant, nếu nghiệp vụ có hỗ trợ, là lệnh hoặc workflow riêng có quyền, ràng buộc và audit cho cả hai phía cần thiết.

Đổi `tenant_id` đơn lẻ có thể để lại dòng con, bằng chứng, approval, ledger và operation ở các phạm vi khác nhau. Không được dùng nó như cách “sửa nhầm tenant” mà bỏ qua tính nhất quán của toàn bộ hồ sơ.

### 4.3. ID khó đoán không phải điều kiện phân quyền

UUID hoặc ID ngẫu nhiên giúp giảm khả năng đoán, nhưng không chứng minh quyền trên đối tượng. ID có thể xuất hiện trong log, đường dẫn, email hoặc một tích hợp hợp lệ rồi bị dùng ở sai ngữ cảnh.

Lệnh vẫn phải được kiểm tra theo tenant và quyền đối tượng, kể cả khi ID được thiết kế duy nhất toàn hệ thống.

## 5. Truy vấn và cập nhật phải giữ phạm vi tenant

### 5.1. Nạp đối tượng bằng định danh có scope

Một truy vấn lấy hồ sơ để duyệt có thể là:

```sql
SELECT id, tenant_id, state, version, basis_package_id,
       requester_id, department_id, amount, currency
FROM expense_request
WHERE tenant_id = :authorized_tenant_id
  AND id = :expense_id
FOR UPDATE;
```

Cú pháp khóa và isolation cụ thể cần phù hợp cơ sở dữ liệu triển khai. Ý nghĩa ở đây là nạp đúng phạm vi và bảo vệ snapshot theo thiết kế đồng thời của lệnh.

Nạp toàn cục rồi lọc tenant ở ứng dụng có thể được triển khai an toàn nếu mọi đường đều kiểm tra trước khi tiết lộ hoặc tác động. Tuy nhiên, cách đó dễ bị bỏ sót khi refactor hoặc tái sử dụng entity; repository yêu cầu tenant giúp làm ranh giới rõ hơn ngay từ truy vấn.

### 5.2. Cập nhật cũng phải có tenant, không chỉ bước đọc

```sql
UPDATE expense_request
SET state = 'APPROVED',
    approved_by = :server_actor_id,
    approved_basis_package_id = basis_package_id,
    version = version + 1
WHERE tenant_id = :authorized_tenant_id
  AND id = :expense_id
  AND state = 'SUBMITTED'
  AND version = :expected_version
  AND basis_package_id = :checked_basis_package_id;
```

Kiểm tra số dòng bị ảnh hưởng. `0` không phải thành công; lệnh phải xử lý không tìm thấy hoặc xung đột theo ngữ cảnh và hợp đồng phản hồi.

Không chạy thêm một truy vấn toàn cục rồi trả chi tiết của hồ sơ ở tenant khác chỉ để giải thích vì sao cập nhật bằng `0`.

Câu SQL trên không tự kiểm tra mọi quyền duyệt. Các điều kiện về phòng ban, hạn mức, không tự duyệt và bằng chứng vẫn phải được thực thi trên dữ liệu được bảo vệ.

### 5.3. Với đối tượng con, kiểm tra cả cha và tenant

Lệnh xóa dòng chi phí cần ràng buộc dòng đó thuộc đúng hồ sơ đang xử lý:

```text
tenant_id = tenant đã được phép
AND expense_id = hồ sơ mục tiêu
AND line_id = dòng mục tiêu
```

Chỉ kiểm tra cùng tenant vẫn có thể cho sửa nhầm dòng của hồ sơ khác trong tenant đó. Tenant isolation và quan hệ cha–con là hai điều kiện cùng cần giữ.

### 5.4. ORM filter không phải toàn bộ hàng rào

Nếu dùng bộ lọc tenant hoặc row policy ở tầng dữ liệu, cần hiểu đường nào có thể bỏ qua: native query, bulk update, kết nối đặc quyền hoặc công cụ quản trị.

Một cơ chế bảo vệ phía cơ sở dữ liệu có thể là lớp bổ sung mạnh, nhưng cấu hình, quyền kết nối và ngữ cảnh phiên phải được kiểm thử. Không mặc định mọi truy vấn đều được bảo vệ chỉ vì một loại repository có filter.

## 6. Giữ tenant nhất quán trên các tham chiếu nghiệp vụ

Một lệnh có tenant đúng vẫn có thể dùng dữ liệu sai tenant qua các ID phụ:

- Nhà cung cấp hoặc tài khoản nhận tiền.
- Báo giá, hợp đồng, ngân sách hoặc mã ưu đãi.
- Basis package, approval round, bằng chứng hoặc payment attempt.
- Membership của người được giao xử lý.

Ví dụ người gọi tạo hồ sơ ở A nhưng gắn tài khoản nhận tiền của B. Nếu chỉ kiểm tra tenant của hồ sơ cha, bước chi trả có thể dùng một tham chiếu không được phép.

### 6.1. Khóa ngoại có tenant giúp bảo vệ quan hệ

Với dữ liệu tenant riêng, có thể thiết kế tham chiếu theo cặp:

```text
expense_request: khóa duy nhất (tenant_id, id)
expense_line:    tham chiếu (tenant_id, expense_id)
                đến expense_request(tenant_id, id)
```

Minh họa ràng buộc:

```sql
ALTER TABLE expense_request
ADD CONSTRAINT uq_expense_tenant_id UNIQUE (tenant_id, id);

ALTER TABLE expense_line
ADD CONSTRAINT fk_expense_line_parent
FOREIGN KEY (tenant_id, expense_id)
REFERENCES expense_request (tenant_id, id);
```

Các cột bắt buộc cần có ràng buộc không null phù hợp. Ví dụ chỉ minh họa quan hệ, không phải migration hoàn chỉnh cho mọi schema.

Ràng buộc này giúp ngăn một dòng tự nhận tenant A nhưng trỏ tới cha chỉ có ở B. Nó không thay thế quyền người gọi, trạng thái cha hoặc các bất biến nghiệp vụ khác.

### 6.2. Tài khoản người dùng toàn cục khác membership theo tenant

Một người có thể tồn tại toàn cục và tham gia nhiều tenant. Khi giao xử lý, cần kiểm tra membership và phạm vi trong tenant đích, không chỉ xác nhận global user ID tồn tại.

Nếu mô hình dùng `membershipId`, có thể ràng buộc assignment vào đúng tenant membership. Nếu dùng global user ID, policy vẫn phải xác minh quan hệ tenant tương ứng ở thời điểm cần thiết.

### 6.3. Dữ liệu dùng chung phải được mô hình hóa rõ

Không phải mọi tham chiếu đều bắt buộc thuộc riêng một tenant. Danh mục tiền tệ hoặc một tài nguyên được chia sẻ có thể có quy tắc khác.

Cần phân biệt dữ liệu toàn cục được phép dùng với dữ liệu thuộc tenant khác. Với chia sẻ có kiểm soát, kiểm tra grant chia sẻ, loại hành động và phạm vi. Không coi “ID tồn tại” hoặc “cùng tên nhà cung cấp” là bằng chứng được dùng xuyên tenant.

## 7. Minh họa Java ở lớp ứng dụng

Đoạn dưới minh họa một lệnh duyệt mới; các dependency là hợp đồng do ứng dụng triển khai. Đây không phải ứng dụng hoàn chỉnh. Nhánh idempotency đã xác định lệnh chưa được xử lý thành công trước đó.

```java
record ApproveExpenseCommand(
        long expectedVersion,
        UUID basisPackageId,
        String note) {}

ApprovalReceipt approve(
        UUID routeTenantId,
        UUID expenseId,
        ApproveExpenseCommand command) {

    Actor actor = identity.requireAuthenticatedActor();
    validateShape(command);

    AuthorizedTenantContext context = tenantAccess.requireContext(
            actor, routeTenantId, "APPROVE_EXPENSE");

    return transactions.required(() -> {
        tenantAccess.requireStillValidForCommand(context);

        ExpenseRequest expense = expenses
                .lockByTenantAndId(context.tenantId(), expenseId)
                .orElseThrow(NotFound::new);

        approvalPolicy.requireAllowed(context, expense);

        expense.requireExpectedVersion(command.expectedVersion());
        expense.requireState(ExpenseState.SUBMITTED);
        expense.requireBasis(command.basisPackageId());
        businessRules.requireApprovalReady(expense);

        decisions.appendApproval(
                context.tenantId(), expense,
                context.actualActorId(), command.note());

        int changed = expenses.markApproved(
                context.tenantId(), expense.id(), expense.version(),
                expense.basisPackageId(), context.actualActorId());

        if (changed != 1) {
            throw new Conflict("CONCURRENT_MODIFICATION");
        }

        ApprovalReceipt result = new ApprovalReceipt(
                expense.id(), expense.version() + 1, "APPROVED");

        audit.appendApproval(context, expense, result);
        outbox.appendExpenseApproved(context.tenantId(), expense, result);
        return result;
    });
}
```

Các hợp đồng cần được triển khai rõ:

- `requireContext` xác minh route tenant và thẩm quyền ngữ cảnh; không nhận một context đã được client tự dựng.
- `requireStillValidForCommand` kiểm tra các điều kiện hiện hành bắt buộc theo cam kết của hệ thống. Một lần đọc lại không tự tuần tự hóa với giao dịch thu hồi membership.
- Repository yêu cầu tenant và ID; các tham chiếu basis/vòng/bằng chứng phải thuộc hồ sơ và phạm vi phù hợp.
- `approvalPolicy` xét quyền trong tenant đó, không dùng role của một tenant khác; vẫn kiểm tra không tự duyệt và hạn mức.
- `markApproved` giữ tenant, trạng thái nguồn, version và basis trong điều kiện cập nhật.
- Quyết định, cập nhật, audit thành công và outbox bắt buộc phải cùng transaction nếu muốn nguyên tử như ví dụ.
- Exception phải dẫn tới rollback theo hợp đồng transaction manager, không bị bắt rồi chuyển thành nhánh thành công.

Việc truyền `context` tường minh giúp dễ rà soát ranh giới, nhưng không tự bảo đảm nếu dependency bỏ qua nó. Cần kiểm thử SQL, tác động và các đường thực thi khác.

## 8. Idempotency, cache và khóa nghiệp vụ

### 8.1. Idempotency phải có namespace phù hợp tenant

Hai tenant có thể gửi cùng chuỗi `Idempotency-Key`. Điều đó không được làm request của A nhận kết quả hay chặn lệnh của B ngoài hợp đồng.

Một phạm vi có thể gồm:

```text
tenant + chủ thể + hành động + đối tượng + client key
```

Kèm fingerprint của nội dung có ý nghĩa. Đây là một lựa chọn hợp đồng, không phải công thức duy nhất cho mọi API.

Không trả kết quả idempotency trước khi xác minh người gọi được nhận kết quả trong tenant tương ứng. Biết key không tạo quyền xem response đã lưu.

Nhánh replay không thực hiện lại transition và không đòi trạng thái nguồn cũ vẫn còn như một lệnh mới. Nhưng nó vẫn cần kiểm tra quyền nhận kết quả hiện tại theo policy.

### 8.2. Chống lặp nghiệp vụ không chỉ dựa vào client key

Người dùng có thể đổi key hoặc một service khác có thể gửi lại cùng ý định. Trạng thái nguồn, logical operation và constraint nghiệp vụ vẫn phải ngăn duyệt hoặc chi trả trùng.

Các khóa duy nhất của dữ liệu tenant cần phản ánh phạm vi đúng, chẳng hạn tenant cộng số tham chiếu nội bộ. Với một nghĩa vụ được thiết kế toàn cục, dùng khóa theo ngữ nghĩa toàn cục đó; không tự thêm tenant làm mất điều kiện duy nhất cần giữ.

### 8.3. Cache không được trộn ngữ cảnh

Cache entity, quyền hoặc response cần key và điều kiện hợp lệ phù hợp tenant. Key chỉ có `expenseId` có thể gây nhầm nếu ID cục bộ trùng hoặc đường đọc dùng sai namespace.

Cache quyết định thường còn phụ thuộc chủ thể, action, resource version và policy/authority version. Một permit ở A không được tái sử dụng tại B chỉ vì user ID và tên action giống nhau.

Xóa cache của một tenant cũng không phải thao tác thu hồi quyền toàn hệ thống. Cần semantics rõ về phạm vi thay đổi và các bản sao token/cache còn lại.

## 9. Sự kiện, queue, worker và callback

### 9.1. Tenant phải được giữ qua ranh giới bất đồng bộ

Một thông điệp nội bộ có thể cần:

```text
messageId
tenantId
commandType
aggregateId + aggregateVersion
operationId
originatingActorReference
delegation/accepted-command reference nếu có
correlationId
```

Tenant nên được lấy từ ngữ cảnh và dữ liệu đã được server xác minh. Không sao chép một trường tenant không đáng tin từ body vào event rồi để consumer mặc định coi event là có thẩm quyền.

Kênh message, producer và loại thông điệp phải có quyền phù hợp. Chỉ có `tenantId` trong envelope không chứng minh nguồn gửi được phép tác động tenant đó.

### 9.2. Consumer có quyền nhiều tenant vẫn phải giới hạn từng lệnh

Worker có thể dùng credential truy cập nhiều tenant để xử lý hàng đợi. Điều đó không có nghĩa một message bất kỳ được chọn tenant và aggregate tùy ý.

Consumer cần xác minh nguồn/hợp đồng, dựng ngữ cảnh đúng, nạp aggregate theo tenant và ID, rồi kiểm tra operation, trạng thái và version. Không lấy `aggregateId` toàn cục rồi bỏ qua tenant vì “worker là service nội bộ”.

Quyền cần còn hiệu lực lúc nhận hay lúc thực thi phải được định nghĩa. Nếu công việc chạy theo ủy nhiệm đã được chấp nhận, lưu và kiểm tra đúng căn cứ ủy nhiệm; không dùng role rộng của worker để âm thầm bù cho người dùng bị từ chối.

### 9.3. Callback bên ngoài cần liên kết phía server

Một callback thanh toán có chữ ký hợp lệ vẫn có thể thuộc tài khoản tích hợp hoặc operation của tenant khác.

Cần đối chiếu nguồn tích hợp, tài khoản nhận sự kiện, operation đã tạo và các thuộc tính như số tiền/loại tiền. Tenant của workflow phải được suy ra hoặc xác nhận qua liên kết có thẩm quyền phía server, không chỉ tin tenant body hoặc header callback khai.

```text
nguồn được xác thực
→ tài khoản tích hợp đúng
→ operation đã liên kết
→ tenant và aggregate đúng
→ kết quả hợp lệ cho trạng thái hiện tại
→ ghi nhận chống trùng
```

Nếu tham chiếu operation chỉ duy nhất trong phạm vi tài khoản tích hợp, phải giữ phạm vi đó trong phép tra cứu. Không giả định mọi số tham chiếu bên ngoài đều duy nhất toàn hệ thống.

### 9.4. Outbox và inbox cũng phải có tenant đúng

Một event hợp lệ về tên nhưng mang tenant sai có thể khiến downstream ghi dữ liệu hoặc phát thông báo sang tổ chức khác. Bản ghi outbox nên ràng buộc với aggregate và transaction nguồn; consumer kiểm tra các liên kết cần thiết.

Chống trùng message phải theo namespace đã định. Không để một message ID của A làm consumer bỏ qua công việc hợp lệ của B nếu ID chỉ được cam kết duy nhất trong tenant.

## 10. Ngữ cảnh ambient, connection pool và nhiều tab

### 10.1. Current tenant toàn cục dễ gây nhầm request

Không dùng một biến dùng chung trong process để giữ tenant hiện tại của mọi request. Các request đồng thời có thể ghi đè ngữ cảnh của nhau.

Một trường “tenant đang chọn” trên hồ sơ người dùng cũng không đủ làm nguồn duy nhất cho mọi lệnh. Tab A đang xử lý tenant A, tab B chuyển sang B; lệnh từ tab A không được âm thầm áp dụng vào B chỉ vì trạng thái phiên đã đổi.

Tenant mục tiêu nên được biểu đạt rõ trong request và được xác minh cho chính request đó. Client cần gửi ý định rõ, server cần từ chối mâu thuẫn thay vì đoán.

### 10.2. Thread-local không tự an toàn qua executor hoặc async

Nếu framework dùng ngữ cảnh gắn luồng, cần thiết lập và khôi phục/xóa đúng vòng đời, kể cả khi exception xảy ra. Thread pool có thể tái sử dụng luồng cho tenant khác.

Tác vụ async không nên mặc định thừa hưởng một tenant ambient đúng. Truyền ngữ cảnh có kiểm soát hoặc dựng lại từ command envelope đã xác minh khi bắt đầu task.

Nếu có ngữ cảnh lồng nhau, cần khôi phục ngữ cảnh trước đó theo thiết kế, không chỉ gán một giá trị rồi quên xử lý. Mục tiêu là không để tác vụ sau dùng tenant của tác vụ trước.

### 10.3. Ngữ cảnh ở connection/session cơ sở dữ liệu

Một cơ chế lọc tenant dựa trên session connection cần xử lý connection pool: thiết lập đúng trước truy vấn, giới hạn vòng đời và reset/khôi phục phù hợp trước khi connection được dùng lại.

Không có tenant hợp lệ phải chặn truy vấn của lệnh tenant, không tắt row policy hoặc filter để “tránh lỗi”. Các kết nối đặc quyền có thể có hành vi khác, cần được giới hạn và kiểm thử riêng.

### 10.4. Ngữ cảnh bất biến không đóng băng mọi quyền

Một object context bất biến giúp tránh thay tenant giữa chừng, nhưng membership và quyền bên dưới vẫn có thể bị thu hồi. Cam kết độ mới và ràng buộc với transaction phải được thiết kế riêng.

Tương tự, khóa hàng aggregate không tự khóa membership, policy hoặc kho danh tính ngoài hệ thống. Không khẳng định thu hồi tức thời chỉ vì lệnh có transaction.

## 11. Batch, quản trị nhiều tenant và workflow xuyên tenant

### 11.1. Batch trong một tenant

Một thiết kế đơn giản là mỗi batch có một ngữ cảnh tenant duy nhất. Tất cả phần tử phải được nạp trong phạm vi đó, với kiểm tra quyền theo từng đối tượng.

`WHERE id IN (...)` thiếu điều kiện tenant là một lỗi thường gặp. Cũng không chỉ kiểm tra phần tử đầu rồi áp quyền chung cho mọi phần tử còn lại.

Chọn rõ chế độ toàn bộ hoặc từng phần. Nếu toàn bộ, không commit các lệnh đầu rồi mới phát hiện một ID ngoài phạm vi. Nếu từng phần, outcome phải đúng và không tiết lộ dữ liệu ngoài quyền.

### 11.2. Công cụ quản trị nhiều tenant

Một người hỗ trợ nền tảng có thể được cấp khả năng thao tác ở nhiều tenant. Mỗi lệnh vẫn cần tenant mục tiêu rõ, quyền quản trị tương ứng và dấu vết người thao tác thực tế.

Không biến thiếu tenant thành chế độ wildcard. Một lệnh vận hành toàn nền tảng phải có hợp đồng và thẩm quyền riêng, không dùng chung một fallback bí mật của API tenant.

Nếu orchestrator chia một công việc thành nhiều lệnh theo tenant, nó cần quyền cho từng phạm vi và idempotency phù hợp. Nhiều transaction hoặc nhiều cơ sở dữ liệu không tự trở thành một transaction nguyên tử chỉ vì có một request bên ngoài.

### 11.3. Workflow xuyên tenant có chủ ý

Một số nghiệp vụ có thể liên quan hai tổ chức. Khi đó cần mô hình rõ các bên, quyền đọc/ghi của từng bên và điều kiện chuyển dữ liệu hoặc giá trị.

Không mô hình hóa bằng cách tùy ý thay tenant trong một command vốn được thiết kế cho một tenant. Có thể cần một loại aggregate/lệnh riêng với source tenant, destination tenant và căn cứ thẩm quyền tương ứng.

Sự cho phép ở phía nguồn không tự tạo quyền ở phía đích. Các ngoại lệ chia sẻ phải cụ thể và được kiểm thử; không mở toàn bộ truy cập chéo chỉ để hỗ trợ một tình huống hợp lệ.

### 11.4. Chuyển dữ liệu cần bảo vệ toàn bộ liên kết

Nếu có workflow chuyển tenant, cần xét bản ghi con, bằng chứng, approval, tài nguyên lưu trữ, khóa cache, operation đang mở và lịch sử. Không được giữ approval cũ mà không đánh giá liệu nó còn có ý nghĩa ở tenant đích.

Với operation bên ngoài đang chưa rõ kết quả, phải giải quyết hoặc quản lý nó theo quy trình trước khi chuyển dữ liệu làm mất khả năng đối soát. Thay tenant không xóa sự thật một tác động đã được gửi.

## 12. Từ chối và audit không làm lộ dữ liệu tenant khác

Với tài nguyên không tồn tại trong phạm vi người gọi được dùng, có thể trả `404` theo chính sách che sự tồn tại. Với người được biết tài nguyên nhưng không có quyền hành động, `403` có thể phù hợp.

Cần nhất quán giữa status, body và các endpoint liên quan. Không trả `404` rồi thêm tên tenant, owner hoặc số tiền của hồ sơ vào message.

### 12.1. Không có tác động nghiệp vụ khi bị chặn

Nhánh deny phải không ghi approval, không đổi trạng thái, không tạo operation chi trả và không phát event cho phép tác động. Audit từ chối hoặc bộ đếm an ninh có thể được ghi theo hợp đồng riêng.

Một transaction cục bộ không rollback được lệnh mạng đã gửi. Vì vậy, tenant và quyền phải được xác lập trước khi tạo tác động; các bước bất đồng bộ cần hợp đồng thẩm quyền rõ như phần 9.

### 12.2. Audit giữ đủ ngữ cảnh nhưng giới hạn dữ liệu

Thông tin hữu ích gồm chủ thể thực tế, tenant mục tiêu đã xác minh, action, tham chiếu aggregate/operation, version và mã lý do. Với quản trị hoặc đại diện, giữ cả ngữ cảnh đại diện cần thiết.

Không ghi nguyên token, secret, tài liệu nhạy cảm hoặc toàn bộ response của tenant khác chỉ để chẩn đoán một request bị chặn. Quyền xem log và công cụ tìm kiếm log cũng phải phù hợp phạm vi dữ liệu.

Nếu audit từ chối nằm trong transaction bị rollback, nó có thể mất. Cần cơ chế ghi nhận thích hợp; lỗi audit không được trở thành lý do bỏ kiểm tra tenant.

## 13. Kiểm thử lệnh theo tenant

### 13.1. Fixture phải phân biệt membership và quyền

Tạo ít nhất hai tenant, hai người ở các tenant khác nhau và một người thuộc cả hai nhưng có quyền khác nhau. Có người đủ role trong A nhưng không có role đó trong B.

Nếu mô hình cho phép ID cục bộ, chủ động dùng cùng ID ở hai tenant để phát hiện key/truy vấn thiếu scope. Nếu ID được ràng buộc duy nhất toàn cục, giữ fixture hợp lệ và vẫn thử ID thực của tenant khác, cùng các tham chiếu phụ bị trộn.

### 13.2. Ma trận tình huống

| Tình huống | Kỳ vọng |
|---|---|
| Người A dùng route A với ID hồ sơ B | Không đọc hoặc thay đổi hồ sơ B |
| Người thuộc cả A/B có quyền duyệt chỉ ở A | Không dùng role A để duyệt tại B |
| Route, header, token binding hoặc body tenant mâu thuẫn | Xử lý đúng hợp đồng, không để các lớp chọn scope khác nhau |
| Lệnh tạo gửi tenant đặc quyền trong body | Tenant bản ghi do ngữ cảnh được phép quyết định |
| `PATCH` cố đổi tenant của aggregate | Không chuyển tenant qua đường sửa thông thường |
| Hồ sơ A tham chiếu supplier/payee/basis của B | Không dùng tham chiếu trái phạm vi |
| Dòng con cùng tenant nhưng thuộc hồ sơ khác | Không sửa/xóa qua parent ID không khớp |
| Tài nguyên toàn cục hoặc chia sẻ hợp lệ | Luồng được phép hoạt động theo policy chia sẻ cụ thể |
| Hai tenant dùng cùng idempotency key | Không trả nhầm kết quả hoặc chặn nhau ngoài hợp đồng |
| Cache cùng resource ID nhưng khác tenant/ngữ cảnh | Không dùng entry của tenant khác |
| Message tenant A nhưng aggregate/operation thuộc B | Consumer không tác động B theo khai báo sai |
| Callback hợp lệ về nguồn nhưng sai tài khoản tích hợp/operation | Không ghi nhận kết quả cho tenant khác |
| Worker xử lý A rồi B trên cùng luồng | Không rò ngữ cảnh ambient giữa các task |
| Connection pool tái sử dụng phiên cơ sở dữ liệu | Filter/session context không mang tenant cũ sang request mới |
| Batch chứa ID ngoài tenant | Đúng chế độ nguyên tử/từng phần, không sửa ngoài phạm vi |
| Công cụ admin hoặc import thiếu tenant | Không fallback truy vấn/ghi toàn hệ thống |
| Membership bị thu hồi trong lúc lệnh chạy | Hành vi đúng cam kết nhất quán và độ mới |
| Người độc lập đủ quyền thực hiện lệnh trong tenant của mình | Thành công nếu các điều kiện nghiệp vụ khác đạt |

### 13.3. Kiểm tra tác động, không chỉ response

Sau request bị từ chối, kiểm tra trạng thái và basis của cả hai tenant, tập quyết định, operation, outbox và dữ liệu con. Một response lỗi không chứng minh repository chưa cập nhật nhầm tenant.

Với thông điệp hoặc callback, kiểm tra cả dữ liệu downstream và tác động ngoài hệ thống qua fake/điểm quan sát phù hợp. Không chỉ assert event có một trường `tenantId` đúng tên.

### 13.4. Kiểm thử xen kẽ và ranh giới tin cậy

Chạy có điều khiển hai request khác tenant dùng chung thread pool, cache hoặc connection pool. Chèn lỗi để xác nhận ngữ cảnh được dọn/khôi phục ngay cả khi task trước thất bại.

Kiểm thử qua API thật của ứng dụng cho route, token và DTO; integration test cho truy vấn, khóa ngoại, transaction và filter dữ liệu. Unit test với context dựng sẵn không chứng minh được ngữ cảnh đó được xác minh đúng ở đầu vào.

## 14. Tự rà soát tenant scoped commands

Trước khi hoàn tất một lệnh thay đổi dữ liệu, hãy trả lời được:

1. Tenant mục tiêu đến từ đâu và được xác minh với chủ thể bằng cách nào?
2. Nếu các nguồn tenant mâu thuẫn hoặc thiếu, hệ thống có dừng thay vì đoán không?
3. Quyền hành động có được lấy đúng tenant và vẫn kiểm tra đối tượng cụ thể không?
4. Truy vấn đọc, cập nhật, dữ liệu con và các tham chiếu phụ có giữ cùng scope không?
5. Tenant của aggregate có được bảo vệ khỏi sửa tùy ý không?
6. Cache, idempotency và khóa nghiệp vụ có namespace đúng theo ngữ nghĩa dữ liệu không?
7. Event, consumer, callback và service tạo hộ có giữ nguồn thẩm quyền và tenant đã xác minh không?
8. Thread pool, async và connection pool có thể mang ngữ cảnh cũ sang tác vụ khác không?
9. Batch, công cụ quản trị và chia sẻ xuyên tenant có hợp đồng riêng rõ ràng không?
10. Kiểm thử có xác nhận dữ liệu và tác động ở tenant không được phép vẫn an toàn không?

Một lệnh được giới hạn tenant đúng nghĩa phải giữ cùng phạm vi đã được cấp phép qua mọi bước thực thi. Ranh giới đó cần tồn tại trong quyền, dữ liệu và tác động, kể cả khi có gửi lại yêu cầu, xử lý bất đồng bộ hoặc một chủ thể tham gia nhiều tenant.
