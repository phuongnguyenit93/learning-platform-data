# Ownership parameter tampering: chống sửa tham số để giả mạo quyền sở hữu

## 1. Mục tiêu bài học

Trong chương **Parameter Tampering** của module **Bảo mật logic nghiệp vụ** (mã dịch vụ: SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY), **ownership parameter tampering** là việc sửa các tham số biểu thị chủ sở hữu hoặc quan hệ kiểm soát để vượt quyền trên đối tượng.

Ví dụ, caller đổi ownerPersonId trong body để tự nhận một hồ sơ, hoặc gửi ownerId của mình cạnh objectId của người khác để đánh lừa kiểm tra quyền. Hệ thống có thể vẫn chạy đúng endpoint và đúng trạng thái nhưng xử lý dưới một quan hệ sở hữu không có thật.

Bài học tập trung vào bảo vệ dữ liệu ownership, quyền theo đối tượng, chuyển chủ hợp lệ, transaction, idempotency và các tình huống kiểm thử tấn công logic.

Sau bài học, bạn có thể:

- Nhận diện field sở hữu và phân biệt dữ liệu được đề nghị với bằng chứng quyền.
- Phát hiện kiểm tra sai khi server so actor với owner do client khai thay vì owner thực tế.
- Ngăn mass assignment và thay đổi quan hệ qua endpoint sửa nội dung.
- Thiết kế tạo thay người khác hoặc chuyển ownership như hành động có thẩm quyền riêng.
- Giữ tenant, lịch sử người tạo và hiệu lực quyền đúng khi chuyển chủ hoặc xử lý đồng thời.
- Kiểm tra cả dữ liệu trả về, thay đổi đã commit và các hiệu ứng phát sinh sau request.

## 2. Tham số ownership có thể xuất hiện ở đâu?

| Vị trí | Ví dụ | Rủi ro nếu dùng sai |
|---|---|---|
| Path | /users/u-1/requests/r-1 | Tin userId ở path mà không đối chiếu request |
| Query | ?ownerId=person-A | Coi bộ lọc do caller chọn là bằng chứng quyền |
| Body | ownerPersonId, ownerIds | Tự thêm/xóa owner hoặc chuyển chủ qua update |
| Field quan hệ | customerId, accountId, projectId | Gắn dữ liệu sang chủ thể/phạm vi khác |
| Metadata | createdBy, createdOnBehalfOf | Xóa dấu người tạo thực tế hoặc giả nguồn thao tác |
| Header/cookie ứng dụng | X-Owner, activeAccount | Lấy dữ liệu không được kiểm chứng làm danh tính |
| Message/job | ownerId đi cùng objectId | Worker dùng quan hệ do producer/caller tự khai |
| Link hoặc payload đã mã hóa | owner reference trong URL | Nhầm khả năng giải mã/biết giá trị với quyền hiện tại |

Tên field không quyết định mức độ tin cậy. Một property có tên verifiedOwner cũng vẫn là input chưa có thẩm quyền nếu client có thể tự gán.

Không phải mọi field trên đều là ownership trong mọi sản phẩm. Cần hiểu quan hệ nghiệp vụ cụ thể và những quyền mà quan hệ đó tạo ra.

## 3. Phân biệt actor, owner thực tế và owner được đề nghị

Ba giá trị thường bị trộn lẫn:

~~~text
Actor:
  chủ thể đang thực hiện thao tác, từ ngữ cảnh xác thực.

Current owner:
  quan hệ sở hữu hiện tại từ dữ liệu có thẩm quyền.

Requested owner:
  chủ thể mà caller muốn chọn, lọc hoặc chuyển quyền tới.
~~~

Một requested owner khớp actor không chứng minh actor sở hữu đối tượng đang được yêu cầu.

### 3.1. Ví dụ kiểm tra sai

~~~java
PurchaseRequest read(Actor actor, ReadCommand command) {
    if (!actor.personId().equals(command.ownerPersonId())) {
        throw new Forbidden();
    }

    return requests.findById(command.requestId())
            .orElseThrow(NotFound::new);
}
~~~

Giả sử:

~~~text
Actor = person-A.
Hồ sơ R thuộc person-B.
Caller gửi requestId=R và ownerPersonId=person-A.
~~~

Phép so sánh đầu tiên đúng, nhưng chỉ xác nhận caller đã khai chính ID của mình. Nó không đọc owner của R.

findById sau đó vẫn trả dữ liệu của B nếu không có kiểm tra scope khác. Thay ownerPersonId bằng tên field khác hoặc dùng UUID không sửa được sai lầm này.

### 3.2. Kiểm tra cần gắn với quan hệ thực tế

Trong một chính sách chỉ cho owner xem:

~~~text
resource.tenantId = tenantContext.tenantId
∧ resource.ownerPersonId = authenticatedActor.personId
~~~

Nếu sản phẩm có chia sẻ, quyền nhân viên hoặc nhóm, policy có thể có thêm các nguồn cho phép rõ ràng. Các nguồn đó vẫn phải được xác minh từ server và áp dụng cho đúng action/đối tượng.

Không mở rộng thành “actor biết ownerId” hoặc “actor xem được profile của owner nên được xem mọi hồ sơ”.

### 3.3. Định danh khó đoán không tạo quyền

ID ngẫu nhiên có thể giảm khả năng đoán, nhưng người dùng vẫn có thể biết ID qua notification, log, link chia sẻ, lịch sử hoặc quan hệ hợp lệ khác.

Mọi lần truy cập nhạy cảm vẫn cần kiểm tra quyền theo đối tượng. Một ownerId được encode hoặc hash cũng chưa chứng minh quyền.

## 4. Mô hình nghiệp vụ minh họa

Bài học dùng hồ sơ đề xuất mua hàng với các trường:

~~~text
tenant_id
request_id
owner_person_id
created_by_person_id
assignee_person_id
budget_account_id
state
content_revision
ownership_version
~~~

Chính sách ví dụ:

- Hồ sơ thuộc một tenant ổn định.
- owner_person_id là người sở hữu hiện tại theo quan hệ nghiệp vụ.
- created_by_person_id ghi người tạo thực tế và không đổi theo chuyển chủ.
- assignee_person_id biểu thị người đang xử lý, không tự cấp quyền owner.
- Owner có thể sửa bản nháp nếu đáp ứng các điều kiện khác.
- Chuyển chủ cần quyền và quy trình riêng.
- Duyệt khoản mua cần thẩm quyền reviewer, hạn mức và phân tách nhiệm vụ riêng.
- budget_account_id phải có quan hệ hợp lệ với tenant và hồ sơ; biết ID chưa đủ để sử dụng.

Creator, owner, assignee và reviewer có thể là những người khác nhau.

### 4.1. Bất biến cần bảo vệ

~~~text
Không đọc/ghi đối tượng chỉ vì caller tự khai owner.
Không đổi owner qua command sửa nội dung thông thường.
Không đổi tenant bằng chuyển owner.
Không sửa lịch sử người tạo để né phân tách nhiệm vụ.
Mọi chuyển chủ phải dựa trên thẩm quyền đối với trạng thái hiện tại.
Không tạo khoảng trống hoặc quan hệ owner trái chính sách khi chuyển chủ.
~~~

Các kiểm soát vẫn phải đúng khi caller gửi request trực tiếp, đi qua API batch hoặc dùng một client cũ.

### 4.2. Có quyền sở hữu chưa đủ quyền phê duyệt

Một người có thể chuyển hồ sơ cho B rồi yêu cầu B chuyển lại. Chuỗi này không xóa việc người đó đã tạo/sửa nội dung.

Nếu chính sách cấm người lập tự duyệt, lịch sử đó vẫn phải được kiểm tra. Việc hiện không còn là owner cũng không tự biến một người thành reviewer độc lập.

### 4.3. Tạo thay và chuyển chủ không phải lúc nào cũng là tấn công

Một hệ thống có thể hợp lệ khi cho nhân viên tạo hồ sơ cho người khác hoặc người quản lý chuyển người chịu trách nhiệm.

Điểm cần bảo vệ là quyền thực hiện hành động, tập người nhận được chọn, tenant, trạng thái và các điều kiện liên quan. Không giải quyết bằng cách cấm mọi input ownerId rồi để công cụ nội bộ có một đường bỏ qua không kiểm soát.

## 5. Đọc và tìm kiếm theo ownership

### 5.1. Ràng buộc truy vấn bằng chủ thể đã xác thực

Với chính sách đơn giản chỉ owner được đọc hồ sơ:

~~~sql
SELECT r.request_id, r.description, r.state
FROM purchase_request r
WHERE r.tenant_id = :verified_tenant_id
  AND r.request_id = :request_id
  AND r.owner_person_id = :authenticated_person_id;
~~~

verified_tenant_id và authenticated_person_id lấy từ ngữ cảnh đã kiểm chứng, không lấy từ body/query để caller tự gán.

Ví dụ này chỉ minh họa policy owner-only. Khi có quyền chia sẻ hoặc nhân viên xử lý, cần thêm điều kiện tương ứng dựa trên grant có thẩm quyền; không bỏ toàn bộ ràng buộc vì actor có một role rộng.

Các đường đọc detail, export, attachment và receipt đều cần phạm vi phù hợp, không chỉ endpoint list.

### 5.2. ownerId trong query chỉ là bộ lọc được đề nghị

Một quản lý có thể được phép lọc danh sách theo nhiều owner. Khi đó ownerId là input hợp lệ, nhưng phạm vi hiệu lực vẫn là:

~~~text
Tập hồ sơ được trả =
    tập khớp bộ lọc caller đề nghị
    ∩ tập actor được đọc
    ∩ biên tenant bắt buộc
~~~

Trong endpoint “hồ sơ của tôi”, không gửi ownerId cũng không được khiến server bỏ điều kiện owner và trả mọi hồ sơ.

Tập owner được phép rỗng không được biến thành bỏ bộ lọc. Count, tổng hợp và phân trang cũng phải tuân thủ phạm vi, tránh lộ dữ liệu qua số liệu phụ.

### 5.3. Path cha không thay cho kiểm tra quan hệ

Với:

~~~text
/people/person-A/purchase-requests/R
~~~

Server không được chỉ kiểm tra caller được xem person-A rồi lấy R trên toàn hệ thống. Cần xác minh quan hệ của R với parent trong route và quyền caller trên chính R.

Nếu R thực tế thuộc person-B, một path gắn nhãn person-A không biến nó thành hồ sơ của A.

Quyền của người hỗ trợ hoặc người được chia sẻ vẫn do policy quyết định trên quan hệ thực, không do tên đường dẫn tạo ra.

### 5.4. Một đối tượng thực thi phải có một nguồn định danh rõ

Mẫu nguy hiểm:

~~~text
Authorize requestId từ path.
Mapper nhận requestId khác trong body.
Repository lưu hoặc trả đối tượng theo ID trong body.
~~~

Cần một định danh target được server sử dụng nhất quán. Nếu API giữ cả path ID và body ID vì tương thích, kiểm tra chúng trùng nghĩa sau chuẩn hóa hoặc từ chối mâu thuẫn.

Tương tự, không authorize theo query ownerId nhưng cập nhật theo body ownerId mà không kiểm tra lại.

Với field trùng trong JSON hoặc tham số lặp không được hỗ trợ, decode cần nhất quán giữa các tầng. Không để một tầng dùng giá trị đầu còn tầng khác dùng giá trị cuối.

## 6. Tạo hồ sơ và tạo thay người khác

### 6.1. Tạo cho chính mình

Nếu endpoint chỉ cho tạo hồ sơ của actor:

~~~text
owner_person_id = authenticated actor personId
created_by_person_id = người khởi tạo thực tế
tenant_id = verified tenant context
~~~

Các giá trị này do server xác lập.

Caller có thể cung cấp nội dung được phép, nhưng không được thay owner để ghi hồ sơ cho người khác, né quota theo người dùng hoặc che nguồn khởi tạo.

Một hidden field chứa ownerId chỉ hỗ trợ UI; nó không có thẩm quyền hơn bất kỳ input nào khác.

### 6.2. Tạo thay là một quyền riêng

Nếu cho phép tạo cho targetPerson:

- Actor phải có quyền tạo thay trong phạm vi đối tượng/tenant đó.
- Target person phải đủ điều kiện nhận hồ sơ.
- Tài khoản ngân sách và các liên kết phải phù hợp.
- Sự đồng ý hoặc xác nhận cần thiết phải theo chính sách.
- createdBy vẫn ghi đúng actor thực tế; người được tạo thay được lưu ở quan hệ riêng.

Không thay createdBy bằng targetPerson chỉ để làm bản ghi trông như do target tự tạo.

Nếu API nhận createdOnBehalfOf, đó là đích được đề nghị cần kiểm chứng. Nó không thay danh tính caller đang được xác thực.

### 6.3. Chuyển chủ không được tự chuyển trách nhiệm tài chính

Ownership có thể ảnh hưởng hiển thị, trách nhiệm xử lý hoặc quyền quản lý. Nó không tự cho phép đổi tài khoản ngân sách, người thanh toán hay người thụ hưởng.

Nếu nghiệp vụ cho phép chuyển các nghĩa vụ đó, cần quyền và transaction riêng tương ứng.

Ví dụ đổi owner không được làm mất một lần tiêu thụ quota đã gắn với người khởi tạo hoặc làm khoản chi xuất hiện dưới ngân sách khác mà chưa có thẩm quyền. Nguồn tính hạn mức phải được định nghĩa rõ và giữ lịch sử phù hợp.

## 7. Chặn takeover qua mass assignment

### 7.1. Có quyền sửa nội dung không có quyền sửa ownership

Giả sử actor là editor được cấp quyền trên R. Caller gửi:

~~~json
{
  "description": "Cập nhật nội dung",
  "ownerPersonId": "editor-person",
  "createdByPersonId": "another-person",
  "tenantId": "another-tenant",
  "state": "APPROVED"
}
~~~

Nếu handler copy mọi property có cùng tên vào entity, quyền edit đã trở thành khả năng tự làm owner, sửa nguồn gốc và nhảy trạng thái.

Cần một hợp đồng command hẹp, ví dụ chỉ có description và expectedVersion cho hành động sửa mô tả. Các thay đổi khác dùng command có quyền riêng.

### 7.2. Kiểm soát tại đầu vào và domain

Một thiết kế có thể:

~~~text
Decoder:
  chỉ nhận field của command;
  từ chối field nhạy cảm không được phép.

Application:
  nạp đối tượng đúng scope và kiểm tra action.

Domain:
  phương thức thay mô tả không thể thay owner/creator/tenant.

Repository:
  ghi đối tượng đã qua kiểm tra, giữ biên tenant và version.
~~~

Chọn hợp đồng từ chối field ngoài danh sách giúp phát hiện client sai hoặc cố sửa tham số. Nếu sản phẩm chọn bỏ qua field lạ, vẫn phải chứng minh không tầng nào khác đọc payload thô để tạo hiệu ứng.

Không chỉ loại ownerId ở cấp trên mà bỏ sót owner.id, ownerIds, profile.owner hoặc một alias khác có cùng tác dụng trong cấu trúc lồng nhau.

### 7.3. Read-only trên UI hoặc response chưa phải bảo vệ input

Một field không xuất hiện trong form, bị disabled hoặc chỉ được trả ra khi GET vẫn có thể được gửi bằng request trực tiếp.

Cũng không mặc định một cấu hình serialization chỉ đọc đã kiểm soát mọi đường deserialization, import hoặc mapper khác. Phải kiểm tra hành vi của endpoint thực sự.

ORM save không biết actor có quyền đổi từng field hay không. Quyền và quy tắc phải được thực thi trước khi ghi.

## 8. Chuyển owner là đề nghị thay đổi, không phải bằng chứng quyền

Input có thể gồm:

~~~json
{
  "targetPersonId": "person-B",
  "expectedOwnershipVersion": 7
}
~~~

targetPersonId biểu thị người nhận được đề nghị. expectedOwnershipVersion giúp phát hiện dữ liệu cũ. Cả hai đều không chứng minh actor được chuyển chủ.

Nếu có expectedOwnerId, nó cũng chỉ là một tiền điều kiện so sánh với trạng thái hiện tại, không phải bằng chứng actor kiểm soát owner đó.

### 8.1. Kiểm tra nguồn và đích

Trước một thay đổi hợp lệ, cần kiểm tra:

- Thẩm quyền actor trên đối tượng và ownership hiện tại.
- Quyền thực hiện action chuyển chủ, không chỉ READ hoặc EDIT.
- Tenant và phạm vi nguồn.
- Đích nhận đủ điều kiện, đúng phạm vi và còn hoạt động.
- Sự đồng ý hoặc xác nhận độc lập nếu chính sách yêu cầu.
- Trạng thái đối tượng cho phép chuyển.
- Hạn mức, phê duyệt, job hoặc trách nhiệm bị ảnh hưởng.

Một userId có tồn tại không có nghĩa có thể trở thành owner của mọi hồ sơ.

### 8.2. Đổi owner không đổi tenant

Trong mô hình ví dụ, transfer chỉ diễn ra trong cùng tenant. Không cho targetPerson ở tenant B làm lý do tự đổi tenant_id của hồ sơ A.

Nếu có migration hoặc chia sẻ xuyên tenant, cần quy trình có thẩm quyền cho chính loại thay đổi đó, không nhét vào một endpoint đổi owner thông thường.

### 8.3. Liên kết khác không được dùng làm đường vòng

Một actor có thể không sửa ownerPersonId trực tiếp nhưng thử thay budgetAccountId, parentId hoặc projectId để làm đối tượng đi vào scope do họ kiểm soát.

Những trường làm thay đổi quyền hoặc nghĩa vụ cũng cần kiểm tra riêng: quyền tại nguồn/đích, quan hệ thật của đối tượng và trạng thái sau thay đổi.

Bảo vệ một field có tên ownerId chưa đủ nếu một field khác có thể gián tiếp thay cùng quan hệ kiểm soát.

## 9. Java minh họa sửa nội dung an toàn

Mã sau là phác thảo tầng ứng dụng, không phải chương trình độc lập. Actor và tenant context đã được kiểm chứng; command không chứa field ownership.

~~~java
record EditDescriptionCommand(
        RequestId requestId,
        long expectedContentRevision,
        String description) {
}

EditResult editDescription(
        Actor actor, EditDescriptionCommand command) {
    return transactions.required(() -> {
        var request = requests.lockForUpdate(
                actor.tenantId(), command.requestId());

        var facts = authorizationFacts.requireFor(
                actor, PURCHASE_EDIT_DRAFT, request);

        authorization.requirePermit(
                actor, PURCHASE_EDIT_DRAFT, request, facts);

        requireState(request, DRAFT);
        requireContentRevision(
                request, command.expectedContentRevision());

        var before = request.auditSnapshot();
        var description = descriptions.validateAndNormalize(
                command.description());

        request.changeDescriptionAndAdvanceRevision(description);
        requests.save(request);
        audit.insertDescriptionChanged(actor, before, request);

        return new EditResult(
                request.id(), request.contentRevision());
    });
}
~~~

Các điểm cần bảo đảm:

- Request được nạp trong đúng tenant.
- Policy dùng owner/grant thực tế của chính request, không dùng owner do caller tự khai.
- Command chỉ cho phép thay mô tả; không có một map tùy ý để thay quan hệ quyền.
- Phương thức domain không đổi owner, creator, tenant, budget account hoặc trạng thái duyệt.
- Mọi đường chuyển ownership cùng tham gia cơ chế bảo vệ trên đối tượng gốc.
- Audit và thay đổi nội dung tham gia transaction theo hợp đồng.
- Exception bắt buộc làm rollback, kết quả thành công chỉ được trả sau commit.

Nếu request thô gửi thêm ownerPersonId, decoder xử lý đúng chính sách field ngoài danh sách trước khi vào handler. Việc không có field đó trong record chưa đủ nếu một tầng khác vẫn đọc body thô để lưu.

Các helper require không dùng Java assert để thực thi bảo mật.

### 9.1. Cập nhật có điều kiện có thể là một lớp bảo vệ

Với policy chỉ cho owner sửa mô tả DRAFT, một câu lệnh khái niệm là:

~~~sql
UPDATE purchase_request
SET description = :description,
    content_revision = content_revision + 1
WHERE tenant_id = :verified_tenant_id
  AND request_id = :request_id
  AND owner_person_id = :authenticated_person_id
  AND state = 'DRAFT'
  AND content_revision = :expected_content_revision;
~~~

Phải kiểm tra đúng số dòng tác động. Nếu không cập nhật được, không được tiếp tục tạo audit thành công, notification hoặc job như thể đã sửa.

Câu SQL minh họa không bao phủ mọi policy chia sẻ/nhân viên. Phải xây điều kiện theo đúng quyền thực tế, không nới thành một nhánh OR thoát khỏi tenant để hỗ trợ role khác.

### 9.2. Quyền và kiểm tra concurrency phải nói về cùng dữ liệu

Nếu policy đọc owner=A nhưng trước khi ghi owner đã thành B, quyền của A có thể không còn áp dụng.

Khóa/version/cập nhật có điều kiện phải bảo vệ các dữ kiện ảnh hưởng quyền. Mọi đường ghi liên quan cần tuân thủ cùng giao thức.

Nếu membership hoặc grant ở nguồn ngoài, transaction cục bộ không tự khóa được nguồn đó. Cần cam kết về độ mới, hiệu lực thu hồi và kiểm chứng phù hợp.

## 10. Thiết kế chuyển chủ có chủ đích

### 10.1. Một lifecycle hai bước minh họa

~~~text
Đề nghị chuyển từ A sang B
    → kiểm tra thẩm quyền và điều kiện
    → lưu transfer PENDING gắn đối tượng, tenant và owner version
    → B chấp nhận hoặc có xác nhận theo chính sách
    → kiểm tra lại điều kiện thực hiện
    → commit owner=B và transfer=COMPLETED
~~~

Trong khi PENDING, B chưa được quyền owner chỉ vì có lời mời. A vẫn là owner theo dữ liệu hiện tại, trừ khi chính sách dùng một trạng thái hạn chế riêng.

Link hoặc mã transfer cần ràng buộc với đối tượng, người nhận, mục đích và thời hạn phù hợp. Có link không mặc định cho phép một tài khoản khác nhận thay.

### 10.2. Xác nhận phải gắn đúng proposal

Khi hoàn tất transfer, server cần kiểm tra:

~~~text
Người chấp nhận đúng người nhận được ràng buộc.
Proposal đúng tenant và đối tượng.
Đích nhận không bị thay sau khi xác nhận.
Proposal còn hiệu lực, chưa dùng hoặc bị thu hồi.
Owner/version hiện tại phù hợp với proposal.
Nguồn thẩm quyền và các xác nhận cần thiết còn hợp lệ.
Trạng thái hồ sơ cho phép hoàn tất.
~~~

Nếu actor ban đầu không có quyền chuyển, việc người nhận đồng ý không tự hợp thức hóa proposal đó.

Không dùng confirmation cho “chuyển R1 cho B” để thực hiện “chuyển R2 cho C”.

### 10.3. Commit nguyên tử, không để khoảng trống

Trong mô hình owner đơn, thao tác hoàn tất có thể thực hiện trong một transaction:

~~~text
Khóa đối tượng và proposal theo thứ tự thống nhất.
Kiểm tra binding, version, quyền và điều kiện.
Đặt owner mới.
Tăng ownership_version.
Đánh dấu proposal đã hoàn tất/được tiêu thụ.
Ghi audit và outbox thay đổi quyền.
Commit.
~~~

Không xóa owner cũ rồi commit trước khi gán owner mới.

Nếu là mô hình nhiều owner, thêm/xóa các quan hệ phải bảo vệ bất biến tương ứng, chẳng hạn không để thao tác quản trị xóa owner ACTIVE cuối cùng.

Khi bước bắt buộc lỗi, cả thay owner, version, proposal và audit/outbox của lần đó phải rollback theo hợp đồng.

### 10.4. Creator và lịch sử tham gia vẫn giữ nguyên

Sau chuyển chủ:

~~~text
current owner: B
createdBy: vẫn là actor tạo ban đầu
material contributors: giữ lịch sử thực tế
~~~

Nếu A từng sửa nội dung trọng yếu, A không tự trở thành reviewer độc lập chỉ vì owner hiện tại là B.

Nếu thay owner làm ảnh hưởng một approval hoặc phạm vi reviewer, chính sách phải xác định cách đánh giá lại. Không tự xóa lịch sử quyết định hoặc giữ nguyên mọi quyết định mà không xét phụ thuộc.

### 10.5. Xung đột giữa edit và transfer

Hai command có thể cùng chạy trên đối tượng đang thuộc A:

~~~text
Nếu edit của A thắng:
    thay đổi hợp lệ được commit trước transfer;
    transfer xử lý theo version/chính sách mới.

Nếu transfer thắng:
    edit phải đánh giá quan hệ quyền hiện tại;
    A không còn được dựa vào ownership đã mất.
~~~

A có thể còn một quyền EDIT độc lập qua nhóm, tùy policy. Vì vậy kết quả cần dựa trên các nguồn quyền còn hiệu lực, không đơn giản cấm mọi action của một former owner.

Điều bị cấm là dùng một quyết định cũ dựa vào ownership A rồi ghi lên trạng thái mà quyền đó không còn đủ căn cứ.

## 11. Link, chữ ký và dữ liệu ownership đã mã hóa

### 11.1. Encode không chứng minh quyền

Base64, một chuỗi khó đọc, hidden field hoặc một owner reference được mã hóa không tự cho phép caller truy cập đối tượng.

Ngay cả khi server giải mã được giá trị, vẫn phải xác định giá trị đó có ý nghĩa gì và caller có thẩm quyền sử dụng nó không.

### 11.2. Chữ ký bảo vệ nội dung theo một hợp đồng cụ thể

Một payload được server ký có thể giúp phát hiện việc sửa nội dung. Nhưng nó không tự chứng minh quan hệ ownership vẫn còn hiệu lực ở hiện tại.

Nếu hệ thống dùng một token/link có quyền hạn, cần ràng buộc phù hợp như:

~~~text
nguồn phát hành và mục đích
actor/người nhận hoặc loại capability được cho phép
tenant, object, action
đích chuyển quyền nếu có
thời hạn, nonce và trạng thái dùng/thu hồi
version hoặc điều kiện quyền cần kiểm tra
~~~

Không lấy một token chỉ xác nhận owner ở thời điểm cũ để bỏ qua việc đối tượng đã chuyển chủ. Không dùng chữ ký cho một field riêng rồi cho phép đổi objectId bên ngoài field đó.

Nguồn phát hành, cách xác minh và quyền mà token thật sự cấp phải được thiết kế rõ. Một JSON do client tự tuyên bố signed=true không có giá trị.

### 11.3. Không để link cũ mở rộng dữ liệu trả về

Nếu quyền xem một link chia sẻ khác quyền owner, endpoint cần thực thi đúng tập action và field được phép.

Một token READ không được dùng tại endpoint transfer hoặc approve. Một link chuyển chủ cũng không tự cho phép đọc toàn bộ hồ sơ tài chính trước khi caller được cấp quyền theo chính sách.

## 12. Cache, worker và retry sau khi ownership đổi

### 12.1. Cache không được giữ mãi quyền của former owner

Có thể cache entity hoặc dữ liệu quyền, nhưng điểm quyết định phải đáp ứng cam kết hiệu lực thu hồi.

Một cache entry “R thuộc A” cũ có thể khiến A tiếp tục truy cập sau khi chuyển cho B. Cần version, vô hiệu hóa hoặc kiểm chứng phù hợp; chỉ thêm userId vào key chưa chứng minh dữ liệu đã mới.

Entity cache phải giữ biên tenant. Response còn phụ thuộc action, projection và nguồn quyền người nhận.

Outbox hỗ trợ phát thông báo thay đổi bền vững, nhưng consumer xử lý sau không tự tạo hiệu lực tức thời ở mọi endpoint.

### 12.2. Worker không tin ownerId được gửi như bằng chứng

Một job cần có tenant, operationId, resource và nguồn thẩm quyền được ràng buộc từ đường tạo công việc hợp lệ.

Không để producer gửi ownerId=A rồi worker coi A là owner hiện tại mà không kiểm tra. Cũng không “sửa” một job lỗi bằng cách tự gán object.ownerId về caller.

Nếu job tiếp tục sau chuyển chủ, quyền thực thi phải theo chính sách công việc: được chốt cho một operation cụ thể hay phải kiểm tra lại. Ghi nhận hiệu ứng đã xảy ra không giống xin phép tạo hiệu ứng mới.

### 12.3. Idempotency bảo vệ khỏi lặp, không cấp quyền

Một transfer đã commit nhưng mất response cần có đường tra cứu/replay an toàn. Cùng key và cùng command không được tăng ownership version hoặc chuyển lại lần nữa.

Receipt phải có scope tenant/caller/action phù hợp và kiểm tra quyền xem kết quả. Former owner không mặc định tiếp tục được đọc toàn bộ đối tượng mới chỉ vì biết key cũ.

Nếu cùng key nhưng targetPersonId hoặc objectId khác, phải phát hiện xung đột nội dung. Không sử dụng receipt của một lần chuyển hợp lệ để cho phép chuyển một đối tượng khác.

## 13. Kiểm thử ownership parameter tampering

### 13.1. Chuẩn bị dữ liệu phân biệt được lỗi

Tạo trong tenant T1:

~~~text
person-A sở hữu request RA.
person-B sở hữu request RB.
person-E chỉ được EDIT mô tả của RA qua grant riêng.
person-M có quyền tạo thay/chuyển chủ trong một phạm vi xác định.
~~~

Tạo thêm request RC ở tenant T2. Các nội dung có giá trị phân biệt được để phát hiện dữ liệu bị trả nhầm, không chỉ kiểm tra ID.

Quyền reviewer và quyền duyệt nghiệp vụ được thiết lập riêng nếu cần kiểm tra phân tách nhiệm vụ.

### 13.2. Ma trận tình huống

| Thao tác thử | Kết quả cần kiểm chứng |
|---|---|
| A đọc RB nhưng gửi ownerId=A | Không trả dữ liệu của B |
| A đọc RC ở tenant T2, tự khai tenant/owner | Không vượt biên tenant |
| Gọi path parent A nhưng request thực tế thuộc B | Không tin quan hệ trong URL |
| Path ID là RA, body ID là RB | Không authorize một đối tượng rồi xử lý đối tượng khác |
| Không gửi ownerId ở endpoint “của tôi” | Không biến thành truy vấn mọi owner |
| Lọc owner ngoài quyền | Tập kết quả/response theo policy, không dùng filter làm quyền |
| E gửi PATCH ownerPersonId=E | Không thay ownership bằng quyền sửa |
| Gửi owner.id/ownerIds hoặc alias lồng nhau | Không mở đường đổi quan hệ qua field khác |
| Gửi createdByPersonId khác | Không thay nguồn gốc lịch sử |
| Gửi isOwner=true hoặc role=OWNER | Không trở thành owner |
| Tạo bình thường với ownerId=B | Không tạo thay nếu thiếu thẩm quyền |
| M tạo thay B hợp lệ | Thành công đúng scope, creator vẫn phản ánh M |
| Người chỉ có READ yêu cầu transfer | Không tạo proposal hoặc hiệu ứng quyền |
| Đổi targetPersonId sau khi proposal được xác nhận | Binding không khớp; không chuyển |
| Người khác nhận link dành cho B | Không trở thành owner thay B |
| Proposal đang PENDING | Người nhận chưa tự có quyền owner |
| Người nhận khác tenant hoặc không đủ điều kiện | Không chuyển qua endpoint thông thường |
| Transfer làm đổi creator/budget account ngoài ý định | Bị chặn hoặc không thay các trường đó |
| Hai transfer từ cùng owner version chạy đồng thời | Không dùng hai proposal cũ để ghi đè tùy ý |
| Edit và transfer cạnh tranh | Quyền và nội dung được áp dụng theo thứ tự hợp lệ |
| Lỗi audit/outbox bắt buộc sau đổi owner | Rollback quan hệ, version và proposal |
| Token/link cũ sau chuyển chủ | Không dùng tính toàn vẹn cũ làm quyền hiện tại vô hạn |
| Cache/worker còn owner cũ | Xử lý đúng cam kết thu hồi và nguồn thẩm quyền |
| Replay cùng key nhưng đổi object/target | Không tái sử dụng kết quả cho command khác |
| Bỏ owner rồi cố approve nội dung mình từng tạo | Không xóa được lịch sử phân tách nhiệm vụ |

Các test được phép thành công cũng quan trọng. Không nên “sửa” lỗi bằng cách cấm cả create-on-behalf hoặc transfer hợp lệ mà sản phẩm yêu cầu.

### 13.3. Kiểm thử so sánh owner tự khai

Gọi endpoint đọc với:

~~~text
actor = person-A
target = RB, đang thuộc person-B
owner parameter = person-A
~~~

Kết quả phải là từ chối hoặc không tìm thấy theo hợp đồng API, và response không chứa nội dung RB.

Ca này trực tiếp phát hiện helper chỉ so actor với tham số rồi nạp target không giới hạn scope.

Thử thêm trường hợp chỉ đổi targetId mà giữ nguyên các field còn lại. Một quyền gắn với RA không được tự áp dụng cho RB.

### 13.4. Kiểm thử field takeover và hành vi hợp lệ

Với E là editor:

~~~text
PATCH RA chỉ sửa description hợp lệ:
    có thể thành công.

PATCH RA kèm ownerPersonId=E:
    xử lý theo hợp đồng field nghiêm ngặt;
    ownership không thay đổi.
~~~

Đọc lại bằng transaction mới và kiểm tra owner, creator, tenant, budget account và trạng thái không bị thay ngoài command.

Nếu hợp đồng chọn từ chối toàn bộ request có field nhạy cảm, mô tả cũng không được cập nhật từ lần thử đó. Nếu hợp đồng khác, phải kiểm tra đúng phần được phép thay; không để thông điệp thành công che một thay đổi quyền.

### 13.5. Kiểm thử chuyển chủ đồng thời

Chuẩn bị hai proposal trên cùng owner/version:

~~~text
P1: RA từ A sang B.
P2: RA từ A sang C.
~~~

Dùng hai transaction/kết nối độc lập, điều phối để hai command hoàn tất thật sự cạnh tranh tại điểm kiểm tra/ghi ownership.

Sau khi cả hai kết thúc:

- Chỉ thay đổi phù hợp với thứ tự và policy được commit.
- Proposal cũ không ghi đè kết quả mới mà không kiểm tra.
- ownership version, trạng thái proposal và audit nhất quán.
- Không có thời điểm commit bình thường mà owner bị trống.
- Notification/outbox phản ánh đúng thay đổi đã thành công.

Nếu chính sách chỉ cho phép một proposal active, kiểm thử cả bước tạo proposal đồng thời. Nếu cho nhiều đề nghị, kiểm thử việc vô hiệu hóa/xử lý các proposal còn lại sau khi một proposal hoàn tất.

### 13.6. Kiểm thử rollback và hiệu ứng phụ

Gây lỗi tại một bước bắt buộc sau khi đã đổi owner trong transaction, chẳng hạn ghi audit hoặc outbox.

Đọc lại và xác nhận:

~~~text
owner vẫn là người cũ
ownership version không tăng thành công
proposal chưa bị tiêu thụ như đã hoàn tất
không có event thành công của transfer
không có job dùng quyền owner mới từ lần bị rollback
~~~

Một request trả lỗi nhưng vẫn tạo invitation, grant hoặc job là một lỗi cần phát hiện. Không chỉ kiểm tra status code.

Security/attempt log có thể xuất hiện riêng; phải phân biệt với audit chứng minh transfer đã commit.

### 13.7. Kiểm thử các đường vào khác

Lặp các trường hợp quan trọng qua batch, import, API cũ, công cụ hỗ trợ và worker nếu các đường đó tồn tại.

Không cần nhân bản test theo mọi chi tiết kỹ thuật, nhưng phải chứng minh mỗi đường tạo hiệu ứng đều đi qua một cơ chế quyền và field protection tương ứng.

Một endpoint chính an toàn không bù được một endpoint legacy còn cho cập nhật owner tùy ý.

## 14. Ghi dấu và phản hồi lỗi an toàn

Thông tin điều tra có thể gồm:

~~~text
actor thực tế và tenant đã kiểm chứng
action và target object
owner hiện tại từ nguồn có thẩm quyền
owner/target được đề nghị nếu phù hợp để lưu
content revision và ownership version
grant/policy/proposal được dùng
kết quả: denied / pending / committed / rolled back
reason code và command/operationId
~~~

Requested owner và current owner phải được phân biệt. Nếu log chỉ ghi ownerId=A từ payload, người điều tra có thể tưởng A thực sự sở hữu đối tượng.

Không lưu token, raw link bí mật hoặc dữ liệu nhạy cảm không cần thiết. Quyền đọc audit cũng phải có scope.

Response từ chối không nên tiết lộ tên, email hoặc danh sách hồ sơ của owner khác. Có thể dùng thông báo chung và mã tham chiếu, còn chi tiết nguyên nhân giữ trong đường hỗ trợ có thẩm quyền.

Theo dõi các mẫu như đổi targetId liên tục, gửi owner field vào endpoint không hỗ trợ, thử alias hoặc nhiều transfer bị chặn có thể giúp phát hiện lạm dụng. Một lần client gửi sai chưa tự chứng minh có ý đồ tấn công.

## 15. Tình huống thực hành: từ editor thành owner rồi duyệt

E được chia sẻ quyền sửa mô tả RA, do A tạo. E không được chuyển chủ hoặc duyệt hồ sơ này.

E thử:

~~~text
1. PATCH RA với description hợp lệ và ownerPersonId=E.
2. Gọi một endpoint “hồ sơ của tôi” để đọc thêm dữ liệu.
3. Đổi createdByPersonId sang B.
4. Gọi approve, kỳ vọng không còn bị nhận diện là người tạo/sửa.
~~~

Các ranh giới phải chặn:

- Command edit không nhận thay owner hoặc creator.
- READ dùng owner/grant thật, không tin input hoặc một flag isOwner.
- Transfer cần quyền riêng và binding với trạng thái hiện tại.
- Dữ liệu provenance không bị viết lại bởi endpoint thông thường.
- Approval dùng thẩm quyền và lịch sử tham gia thực tế.
- Không tạo decision, reservation hoặc bước chi trả từ chuỗi chưa được cho phép.

Nếu bước 1 bị chặn nhưng bước 3 vẫn được thực hiện qua một công cụ quản trị thiếu kiểm soát, hệ thống vẫn có đường lách. Cần rà soát mọi nơi có khả năng thay các quan hệ mang ý nghĩa quyền.

Nếu E được cấp một quyền hợp lệ mới về sau, đó là nguồn thẩm quyền mới phải được audit; không được viết lại các lần thử cũ như thể E đã có quyền từ đầu.

## 16. Khung rà soát ownership parameters

~~~text
Các field/path/query có ý nghĩa ownership:
Actor thực tế được xác định từ đâu:
Owner hiện tại được đọc từ nguồn nào:
Requested owner là bộ lọc, đích tạo hay đích transfer:

Hành động nào cho phép thay quan hệ:
Quyền đối với nguồn và đích:
Biên tenant và các liên kết liên quan:
Field không được sửa qua update thông thường:
Creator/provenance và lịch sử cần giữ:

Quy tắc proposal, recipient, xác nhận và hiệu lực:
Khóa/version/constraint bảo vệ khi ghi:
Cache, token, worker và receipt sau thay đổi:
Audit và thông tin không được tiết lộ:
Các test ID thay thế, field takeover, concurrency và rollback:
~~~

## 17. Câu hỏi tự kiểm tra

1. Vì sao ownerId do caller khai trùng actor vẫn có thể dẫn đến đọc dữ liệu người khác?
2. Khi ownerId là bộ lọc hợp lệ, server giới hạn kết quả bằng nguồn quyền nào?
3. Endpoint sửa nội dung có đường nào vô tình cập nhật owner/creator/tenant không?
4. Create-on-behalf và transfer khác gì với một input ownerId được tin trực tiếp?
5. expectedOwnerId hoặc ownershipVersion có thay thế được authorization không?
6. Chuyển chủ có thể làm thay đổi quyền nào mà không được phép đổi nghĩa vụ tài chính?
7. Vì sao chữ ký hoặc mã hóa owner reference chưa bảo đảm quyền hiện tại?
8. Khi transfer và edit cùng chạy, dữ kiện ownership nào được bảo vệ tới lúc commit?
9. Lịch sử người tạo/sửa có còn nguyên sau transfer, revoke và retry không?

Nguyên tắc cần giữ là **input có thể đề nghị một quan hệ sở hữu, còn quyền phải dựa trên quan hệ có thẩm quyền và hành động được phép**. Mọi lần đọc, cập nhật, chuyển chủ và xử lý lại phải giữ được sự phân biệt đó.
