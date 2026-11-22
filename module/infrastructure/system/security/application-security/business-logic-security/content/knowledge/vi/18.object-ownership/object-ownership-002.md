# Shared object ownership: kiểm soát đồng sở hữu đối tượng nghiệp vụ

## 1. Mục tiêu bài học

Trong chương **Object Ownership** của module **Bảo mật logic nghiệp vụ** (mã dịch vụ: SECURITY_APPLICATION_SECURITY_BUSINESS_LOGIC_SECURITY), **shared object ownership** là mô hình một đối tượng có nhiều chủ thể được công nhận là owner theo chính sách của ứng dụng.

Ví dụ, một hồ sơ đề xuất mua hàng có hai người cùng chịu trách nhiệm cập nhật nội dung và gửi xử lý. Việc đồng sở hữu giúp cộng tác và duy trì trách nhiệm khi một người vắng mặt, nhưng cũng mở thêm các đường lạm dụng nếu quyền của owner không được định nghĩa rõ.

Các rủi ro thường gặp gồm tự thêm mình làm owner, biến quyền sửa thành quyền chia sẻ, một owner loại bỏ những người còn lại, dùng ownership để bỏ qua phê duyệt hoặc thu hồi không hết quyền sau khi rời hồ sơ.

Sau bài học, bạn có thể:

- Phân biệt owner, người được chia sẻ, editor, người tạo và người duyệt.
- Mô hình hóa các quan hệ đồng sở hữu có tenant, phạm vi, trạng thái và lịch sử.
- Định nghĩa quyền riêng cho nội dung, chia sẻ, thay owner và xóa đối tượng.
- Bảo vệ bất biến owner cuối cùng bằng transaction và kiểm soát concurrency.
- Xử lý invitation, nhóm, thu hồi, cache và công việc bất đồng bộ theo nguồn quyền.
- Xây dựng các tình huống kiểm thử tấn công vào quan hệ ownership.

## 2. Đồng sở hữu khác chia sẻ quyền truy cập

Một đối tượng có thể có nhiều quan hệ:

| Quan hệ | Ý nghĩa minh họa | Không tự suy ra |
|---|---|---|
| Creator | Người tạo đối tượng ban đầu | Luôn là owner hiện tại hoặc luôn được xem sau khi bị thu hồi |
| Owner | Người chịu trách nhiệm và có nhóm quyền owner được quy định | Có mọi quyền của hệ thống hoặc được tự duyệt |
| Co-owner | Một owner trong tập nhiều owner | Được một mình thay đổi mọi quyết định quan trọng |
| Editor | Được sửa các phần nội dung cho phép | Được thêm owner, chia sẻ lại hoặc xóa hồ sơ |
| Viewer | Được xem dữ liệu trong phạm vi cho phép | Được export toàn bộ hoặc xem mọi trường nhạy cảm |
| Assignee | Người đang được giao xử lý một bước | Trở thành owner lâu dài |
| Reviewer | Người được giao nhiệm vụ xét duyệt | Có quyền quản lý ownership hoặc sửa nội dung cần duyệt |
| Beneficiary | Người hưởng lợi từ nghiệp vụ | Có quyền điều khiển đối tượng |

Không nên gọi mọi người được chia sẻ là owner nếu quyền và trách nhiệm của họ thực tế khác nhau.

### 2.1. Ownership là quan hệ có ngữ nghĩa nghiệp vụ

Một mảng ownerIds có thể biểu diễn danh sách người sở hữu, nhưng chưa trả lời được:

- Ai được thêm hoặc xóa một phần tử?
- Mỗi owner có quyền nào?
- Có cần nhiều owner xác nhận thao tác quan trọng không?
- Người được mời nhưng chưa chấp nhận đã được tính là owner chưa?
- Một người có hai tài khoản có được tính hai lần không?
- Khi owner rời tenant, ai chịu trách nhiệm cho hồ sơ?
- Quan hệ được tạo do cấp trực tiếp, qua nhóm hay qua ủy quyền?
- Thu hồi ownership có xóa quyền khác của người đó không?

Cần giải quyết những câu hỏi này trước khi dùng danh sách owner để cấp quyền.

### 2.2. Đồng sở hữu không tự tạo phê duyệt độc lập

Nếu một hồ sơ có hai owner, điều đó không chứng minh đã có hai người xem xét một khoản chi.

Ownership là quan hệ quản lý đối tượng. Approval là quyết định có thời điểm, nội dung, revision và thẩm quyền cụ thể.

Một owner có thể được gửi hồ sơ, nhưng muốn approve còn phải đáp ứng chính sách reviewer, hạn mức và phân tách nhiệm vụ. Lịch sử tạo/sửa trọng yếu không biến mất khi người đó được thêm hoặc bị xóa khỏi tập owner.

## 3. Chính sách minh họa cho hồ sơ mua hàng chung

Bài học dùng một mô hình giả định:

- Hồ sơ thuộc một tenant xác định.
- Có nhiều owner là các person khác nhau, có membership hợp lệ trong tenant.
- Viewer và editor là quan hệ cộng tác riêng.
- Owner được sửa nội dung ở trạng thái cho phép và gửi hồ sơ.
- Quyền quản lý ownership là hành động được kiểm soát riêng.
- Thay đổi owner quan trọng phải đáp ứng chính sách xác nhận của hồ sơ/tenant.
- Hồ sơ hoạt động bình thường phải có ít nhất một quan hệ owner ACTIVE theo mô hình lưu trữ.
- Người được mời chưa chấp nhận không được tính là owner ACTIVE.
- Duyệt và thực hiện mua hàng dùng quy tắc nghiệp vụ độc lập với ownership.

Các quyền cụ thể có thể khác ở sản phẩm khác. Điều cần giữ là chúng phải được định nghĩa và thực thi tường minh.

### 3.1. Ma trận quyền theo quan hệ

| Hành động | Viewer | Editor | Owner |
|---|---|---|---|
| Xem nội dung cơ bản | Có trong scope | Có trong scope | Có trong scope |
| Sửa phần nội dung được phép | Không | Có, đúng trạng thái | Có, đúng trạng thái |
| Sửa trường nhạy cảm/đã được duyệt | Không tự có quyền | Không tự có quyền | Không tự có quyền |
| Gửi hồ sơ | Không | Nếu được cấp riêng | Theo chính sách |
| Mời viewer/editor | Không | Nếu có SHARE riêng | Theo chính sách chia sẻ |
| Thêm/xóa owner | Không | Không | Cần OWNERSHIP_MANAGE và điều kiện thay đổi |
| Xóa hồ sơ | Không | Không | Cần DELETE và điều kiện riêng |
| Approve/chi trả | Không do quan hệ này cấp | Không do quan hệ này cấp | Không do quan hệ này cấp |

Có quan hệ owner không được trở thành một nhánh allow bỏ qua mọi action, trạng thái hoặc hạn chế bắt buộc.

### 3.2. Hai owner không mặc định là mô hình đồng thuận

Có thể có các chính sách:

~~~text
Một owner đủ quyền sửa bản nháp.
Hai owner độc lập phải xác nhận việc xóa hồ sơ giá trị cao.
Quy trình thay owner dùng một ngưỡng và ngoại lệ được quản lý.
~~~

Các quy tắc đó phải được áp dụng theo từng hành động, không suy ra từ số owner đang tồn tại.

Nếu chỉ còn một owner, việc thêm owner thứ hai hoặc phục hồi quyền cần một đường bootstrap/recovery được định nghĩa. Sự đồng ý nhận ownership của người được mời không tự thay thế một lần kiểm tra độc lập mà chính sách yêu cầu.

### 3.3. Quyền hiệu lực cần xét tất cả nguồn

Một người có thể vừa là owner trực tiếp, vừa có quyền qua nhóm hoặc một grant khác.

~~~text
Quyền cho một action =
    có nguồn cấp quyền phù hợp đang hiệu lực
    ∧ đúng tenant và object scope
    ∧ đúng trạng thái/tham số
    ∧ thỏa các hạn chế bắt buộc
~~~

Thu hồi owner không mặc định làm mất một quyền READ độc lập mà người đó vẫn được cấp hợp lệ qua nhóm. Ngược lại, việc có quyền READ từ nhóm không giữ lại OWNERSHIP_MANAGE đã bị thu hồi.

Giao diện và audit cần giải thích đúng nguồn quyền, tránh thông báo “đã thu hồi mọi truy cập” khi chỉ xóa một quan hệ.

## 4. Mô hình dữ liệu quan hệ ownership

Một mô hình có thể tách:

~~~text
business_object
  tenant_id
  object_id
  state
  content_revision
  ownership_version

object_owner
  tenant_id
  object_id
  person_id
  state: ACTIVE / REVOKED
  granted_by
  granted_at
  revoked_by
  revoked_at
  source_reference

object_collaboration_grant
  tenant_id
  object_id
  subject_type
  subject_id
  role_or_actions
  validity
  authority_source

ownership_invitation
  tenant_id
  object_id
  recipient_binding
  intended_role
  state: PENDING / ACCEPTED / REVOKED / EXPIRED
  authority_reference
  expires_at
~~~

Đây là cấu trúc khái niệm, không phải schema bắt buộc.

### 4.1. Person khác account

Nếu Lan có hai userId cùng thuộc một personId, Lan không được tính thành hai người độc lập khi kiểm tra ngưỡng xác nhận.

Nên dùng nguồn danh tính có thẩm quyền để xác định đơn vị độc lập. Không so tên hiển thị hoặc email tùy ý để quyết định hai tài khoản là hai người.

Nếu mô hình cho phép group làm owner, cần quy định riêng ý nghĩa owner là nhóm và người nào được đại diện nhóm; không chỉ thay person_id bằng group_id rồi giữ nguyên mọi phép đếm.

### 4.2. Tenant của đối tượng không do tập owner quyết định

Thêm một owner không được tự đổi tenant_id của đối tượng.

Trong chính sách ví dụ, người nhận ownership phải đủ điều kiện trong cùng tenant. Việc mời một tài khoản bên ngoài cần một mô hình cộng tác bên ngoài được quản lý riêng, không ngầm cấp membership rộng của tenant.

Nếu sản phẩm hỗ trợ chia sẻ xuyên tenant, phải xác định quyền trên tài nguyên đích, dữ liệu được tiết lộ và nguồn thẩm quyền của hai phía. Không bỏ điều kiện tenant chỉ vì actor xuất hiện trong một danh sách owner.

## 5. Thêm đồng sở hữu qua lời mời có kiểm soát

### 5.1. Tạo lời mời là một hành động cấp quyền

Server cần kiểm tra:

- Người mời có quyền cấp đúng loại quan hệ cho chính đối tượng này.
- Role được đề nghị thuộc tập mà người mời được phép cấp.
- Người nhận và tenant đáp ứng chính sách.
- Trạng thái đối tượng cho phép thay đổi chia sẻ/ownership.
- Các xác nhận bổ sung đã có nếu thay owner cần phê chuẩn.
- Lời mời có thời hạn và nguồn thẩm quyền được lưu.

Không cho editor gửi role=OWNER rồi server tin trực tiếp. Quyền sửa nội dung không bao gồm quyền tự mở rộng quan hệ truy cập.

Được sử dụng một quyền cũng không mặc định được cấp lại quyền đó. Chẳng hạn một grant READ cá nhân không tự cho phép mời người khác READ.

### 5.2. Link mời không tự xác định người được nhận

Lời mời cần ràng buộc với người nhận theo mô hình danh tính của hệ thống. Có thể là person đã xác định hoặc một địa chỉ đã được kiểm chứng và được ánh xạ an toàn khi chấp nhận.

Không biến việc có link thành quyền nhận ownership cho bất kỳ tài khoản nào, trừ khi sản phẩm chủ ý thiết kế capability như vậy và quản lý đầy đủ phạm vi, thời hạn, thu hồi và rủi ro chuyển tiếp.

Với lời mời ownership theo người nhận, server phải xác nhận tài khoản đang chấp nhận chính là người được mời hợp lệ. Forward link cho người khác không được tạo owner khác.

Token mời không nên được ghi nguyên vào log. Cần có trạng thái dùng một lần, hết hạn và thu hồi theo thiết kế.

### 5.3. Chấp nhận phải kiểm tra lại điều kiện hiện tại

Trong chính sách minh họa, trước khi kích hoạt ownership:

~~~text
Lời mời còn PENDING và chưa hết hạn.
Người nhận khớp binding.
Người nhận còn đủ điều kiện trong tenant.
Nguồn quyền mời và phê chuẩn thay owner còn hợp lệ.
Đối tượng chưa bị xóa/khóa đối với thao tác này.
Không tạo quan hệ owner ACTIVE trùng.
~~~

Nếu người mời đã bị thu hồi quyền trước lúc nhận, lời mời phụ thuộc quyền người mời không được tự kích hoạt. Nếu sản phẩm dùng một phê chuẩn cấp quyền độc lập thuộc về đối tượng, phải mô hình hóa nguồn đó rõ ràng.

Việc ghi invitation=ACCEPTED, owner=ACTIVE, tăng ownership_version, audit và outbox liên quan phải nhất quán. Không đánh dấu đã nhận trước rồi để việc tạo owner có thể thất bại riêng lẻ.

Pending invitation không được dùng làm owner dự phòng để cho phép xóa owner ACTIVE cuối cùng.

## 6. Xác nhận thay đổi ownership

### 6.1. Xác nhận phải gắn với thay đổi cụ thể

Nếu chính sách yêu cầu nhiều người duyệt thay đổi ownership, một proposal có thể chứa:

~~~text
changeId
tenantId, objectId
operation: ADD_OWNER / REMOVE_OWNER
targetPersonId
expectedOwnershipVersion
policyVersion
expiresAt
requiredConfirmations
~~~

Các xác nhận phải gắn với chính proposal đó. Không dùng một phiếu “đồng ý thêm B” để thực hiện “thêm C”, hoặc một thay đổi đã chấp thuận ở đối tượng khác.

Khi thực hiện, server kiểm tra người xác nhận đủ thẩm quyền, ngưỡng đã đạt, các danh tính độc lập đúng yêu cầu và proposal chưa hết hiệu lực/chưa dùng.

### 6.2. Đếm người và nguồn thẩm quyền theo chính sách

Hai account thuộc cùng personId không tạo hai người xác nhận.

Nếu hai nhóm cùng được một người đại diện, người đó cũng không tự trở thành hai người độc lập. Nếu chính sách còn yêu cầu hai nguồn thẩm quyền hoặc hai bộ phận khác nhau, phải giữ đủ bằng chứng để kiểm tra.

Một chữ ký hoặc checkbox nhận lời mời chỉ chứng minh người nhận đồng ý nhận quan hệ, không tự là phê chuẩn quản trị ownership của người có thẩm quyền.

### 6.3. Chống thay đổi dữ liệu sau xác nhận

Sau khi proposal được xác nhận, một thay đổi khác có thể đã làm biến động tập owner hoặc chính sách. Server cần kiểm tra ownership version và quy tắc hiệu lực trước khi thực hiện.

Nếu version không còn phù hợp, có thể yêu cầu đánh giá lại/tạo proposal mới theo chính sách. Không âm thầm áp dụng trên một tập owner khác với tập được dùng để quyết định.

Việc tiêu thụ proposal và thay đổi ownership phải commit cùng nhau. Nếu một bước thất bại, proposal không được mất hiệu lực như thể thay đổi đã thực hiện thành công.

### 6.4. Thiếu người xác nhận không có nghĩa được hạ ngưỡng

Nếu chính sách đòi hai owner độc lập nhưng chỉ còn một người có thể hoạt động, không tự đặt ngưỡng về một để “giải quyết”.

Cần một đường bootstrap/recovery được cấp thẩm quyền riêng, có phạm vi và bằng chứng. Nếu chính sách cho sole owner tự thêm người thứ hai, phải ghi rõ đó là cơ chế được phép, không gọi nó là kiểm soát hai người độc lập.

## 7. Bảo vệ owner cuối cùng

### 7.1. Định nghĩa tập owner được tính

Gọi O(x) là tập person có quan hệ owner ACTIVE trên đối tượng x trong mô hình hiện tại.

Bất biến cục bộ cho đối tượng hoạt động bình thường:

~~~text
|O(x)| ≥ 1
~~~

Không tính các quan hệ PENDING, REVOKED hoặc lời mời chưa chấp nhận.

Cần ràng buộc ngăn quan hệ owner hiện tại bị trùng cho cùng tenant/object/person. Lịch sử cấp và thu hồi có thể được ghi riêng để vẫn giữ đầy đủ bằng chứng.

Bất biến số lượng quan hệ chưa chứng minh mọi owner còn đăng nhập được hoặc membership ngoài hệ thống chưa bị thu hồi. Điều này cần được xử lý ở lifecycle danh tính và phần phục hồi.

### 7.2. Vì sao đọc count rồi xóa là chưa đủ?

Ban đầu có owner A và B. Hai command có thẩm quyền cùng chạy:

~~~text
T1 đọc count = 2, dự định xóa A.
T2 đọc count = 2, dự định xóa B.
T1 xóa A và commit.
T2 xóa B và commit.
Kết quả: không còn owner.
~~~

Mỗi command nhìn riêng đều nghĩ còn một owner. Toàn hệ thống lại vi phạm bất biến.

Một cách bảo vệ là khóa cùng một dòng gốc đối tượng trước mọi thao tác làm thay đổi tập owner. Sau khi có khóa, đọc tập hiện tại, kiểm tra và ghi trong cùng transaction.

Tất cả đường thêm/xóa/kích hoạt ownership phải tham gia giao thức phù hợp; chỉ khóa trong một endpoint không bảo vệ các đường khác.

### 7.3. Java minh họa thu hồi owner

Đây là phác thảo tầng ứng dụng cho owner là person trực tiếp. Nó dùng repository và policy giả định, không phải chương trình độc lập.

Giả định mọi thay đổi ownership tuân thủ khóa gốc, và helper requireExecutable xác minh proposal, binding, nguồn quyền, xác nhận và hiệu lực.

~~~java
OwnershipResult removeOwner(
        Actor actor, RemoveOwnerCommand cmd) {
    return transactions.required(() -> {
        var object = objects.lockForUpdate(
                actor.tenantId(), cmd.objectId());

        authorization.requirePermit(
                actor, OWNERSHIP_MANAGE, object);
        requireOwnershipVersion(
                object, cmd.expectedOwnershipVersion());

        var change = ownerChanges.lockForUpdate(
                actor.tenantId(), cmd.changeId());
        ownerChangePolicy.requireExecutable(
                actor, object, change,
                REMOVE_OWNER, cmd.targetPersonId());

        var owners = ownerships.findActivePeople(
                object.tenantId(), object.id());
        requireContains(owners, cmd.targetPersonId());

        long remaining = owners.stream()
                .filter(id -> !id.equals(cmd.targetPersonId()))
                .distinct()
                .count();
        requireAtLeastOneOwner(remaining);

        ownerships.revoke(
                object.tenantId(), object.id(),
                cmd.targetPersonId(), actor.personId());
        change.markConsumed();
        object.bumpOwnershipVersion();

        ownerChanges.save(change);
        objects.save(object);
        audit.insertOwnerRemoved(actor, object, change);
        outbox.insertOwnershipChanged(object, change);

        return OwnershipResult.from(object);
    });
}
~~~

Khóa không tự làm người gọi có quyền. Kiểm tra authorization và proposal vẫn cần dùng dữ liệu có thẩm quyền.

Các hàm require phải là validation bắt buộc, không dùng Java assert làm lớp kiểm soát bảo mật. Exception tại bước bắt buộc phải rollback cả quan hệ owner, version, proposal, audit và outbox của lần thay đổi.

Ví dụ chưa trình bày receipt idempotency. Nếu API hỗ trợ replay, cùng command hợp lệ trả kết quả cũ mà không thu hồi lại hoặc tăng version lần nữa; cùng key nhưng khác đối tượng/người bị thu hồi phải được phát hiện.

### 7.4. Vì sao version trên từng dòng owner chưa đủ?

Nếu T1 sửa dòng của A còn T2 sửa dòng của B, hai version riêng có thể đều khớp.

Bất biến “còn ít nhất một owner” trải trên cả tập owner của đối tượng. Cần cơ chế bảo vệ tập/tài nguyên chung, chẳng hạn khóa gốc hoặc giao thức cập nhật nguyên tử tương đương được thiết kế đúng.

Một unique constraint giúp chống trùng quan hệ. Nó không tự ngăn cả hai quan hệ khác nhau bị xóa.

## 8. Cùng sở hữu không được làm mất kiểm soát nội dung

### 8.1. Command sửa không được sửa luôn quan hệ quyền

Một payload cập nhật hồ sơ không nên được bind trực tiếp vào toàn bộ entity:

~~~json
{
  "title": "Đề xuất mua thiết bị",
  "ownerIds": ["attacker-person"],
  "tenantId": "another-tenant",
  "status": "APPROVED"
}
~~~

Editor có thể được đổi title nhưng không được thay ownerIds, tenantId hoặc chuyển trạng thái phê duyệt.

Các thay đổi ownership cần command, quyền và transaction riêng. Server xác định danh tính người thao tác từ ngữ cảnh xác thực; không tin grantedBy hoặc approvedBy do client gửi.

### 8.2. Nhiều owner cùng sửa vẫn cần version

Hai owner có thể cùng đọc revision 5 rồi ghi thay đổi khác nhau. Nếu dùng ghi đè cuối cùng mà không có quy tắc, số tiền hoặc người thụ hưởng có thể bị thay bằng dữ liệu cũ.

Cần expected version/revision hoặc cơ chế hợp nhất phù hợp với loại dữ liệu. Dữ liệu tài chính và nội dung đã duyệt thường cần từ chối xung đột hoặc yêu cầu xem lại, không hợp nhất tùy tiện.

Quyết định approve phải gắn với đúng nội dung được xem. Việc cả hai người đều là owner không cho phép sửa dữ liệu đã được phê duyệt mà giữ nguyên hiệu lực quyết định cũ.

### 8.3. Content version và ownership version bảo vệ các phụ thuộc khác nhau

Có thể tách hai version để tránh mọi thay đổi cộng tác đều làm xung đột chỉnh sửa nội dung. Tuy nhiên, command phụ thuộc cả nội dung lẫn ownership phải kiểm tra cả hai hoặc các bằng chứng tương đương.

Ví dụ ngưỡng xác nhận xóa hồ sơ phụ thuộc giá trị hồ sơ. Nếu số tiền tăng sau lúc xác nhận, ownership version không đổi cũng chưa đủ để thực hiện proposal cũ.

Các điều kiện ảnh hưởng quyền phải được xác định và bảo vệ, không chỉ trường thuận tiện nhất để version.

### 8.4. Xóa đối tượng là hành động riêng

Một owner bị chiếm tài khoản không nên mặc định có thể xóa vĩnh viễn mọi dữ liệu và bằng chứng chỉ vì có quyền sửa hồ sơ.

Quy tắc DELETE có thể phụ thuộc trạng thái, thời hạn, nghĩa vụ đang xử lý hoặc xác nhận nhiều người. Nếu hỗ trợ archive/soft delete, các đường đọc/ghi phải thực thi đúng trạng thái đó.

Không xóa đối tượng để thoát một khoản chi đang xử lý hoặc làm mất lịch sử phê duyệt. Nghiệp vụ đã phát sinh cần một quy trình kết thúc/phục hồi phù hợp.

## 9. Ownership qua nhóm và quyền kế thừa

### 9.1. Group owner không chỉ là một kiểu ID khác

Nếu đối tượng thuộc một nhóm, cần xác định:

- Thành viên nào được đại diện nhóm cho từng action.
- Ai được thay membership của nhóm.
- Group admin có được tự thêm mình rồi thực hiện quyền owner không.
- Nhóm có phạm vi tenant và đối tượng nào.
- Khi nhóm rỗng hoặc bị khóa, hồ sơ được xử lý ra sao.
- Ngưỡng độc lập đếm nhóm, người thực hiện hay nguồn thẩm quyền.

Cấp quyền quản lý membership có thể gián tiếp cấp quyền trên nhiều đối tượng nhóm đang sở hữu. Vì vậy đây cũng là một đường cần kiểm soát.

Không suy ra quyền owner của một người chỉ từ chức danh hoặc email có cùng miền với nhóm.

### 9.2. Hai nhóm chưa chắc là hai người độc lập

Một người có thể thuộc cả group-A và group-B. Nếu hai nhóm là đồng owner và yêu cầu hai người xác nhận, cùng một person không được ký hai lần qua hai “mũ” khác nhau.

Nếu chính sách yêu cầu hai đơn vị đại diện, có thể cần cả điều kiện khác người và khác nguồn đại diện. Lưu danh tính thực tế cùng quan hệ nhóm được sử dụng.

Một dòng group owner tồn tại cũng chưa chứng minh có người đủ điều kiện đại diện nhóm tại thời điểm quyết định.

### 9.3. Quyền cha–con cần được đặc tả

Ví dụ folder chung có nhiều owner và chứa các hồ sơ con. Chính sách cần nói rõ:

~~~text
Quyền nào được kế thừa?
Những loại con nào được áp dụng?
Con có thể có owner/grant riêng không?
Có chặn kế thừa ở một mức nào không?
Chuyển con sang cha khác làm thay đổi quyền thế nào?
~~~

Không mặc định owner của folder có mọi quyền trên payment hoặc dữ liệu nhạy cảm được liên kết từ folder.

Nếu thu hồi ownership ở cha, quyền nhận qua đường kế thừa tương ứng phải hết hiệu lực theo hợp đồng. Grant trực tiếp độc lập ở con có thể vẫn còn; cần đánh giá các nguồn còn hiệu lực thay vì xóa hoặc giữ mọi quyền theo một quy tắc chung.

### 9.4. Đổi nhóm hoặc đổi đối tượng cha có thể là thay đổi quyền

Chuyển hồ sơ sang nhóm/folder khác có thể cấp quyền cho một tập người mới. Cần kiểm tra quyền chuyển tại nguồn và đích, dữ liệu sẽ bị lộ và các điều kiện phê duyệt liên quan.

Không coi đây luôn là một thay đổi phân loại vô hại. Thao tác MOVE hoặc thay parent phải dùng quy tắc quyền và version phù hợp.

## 10. Thu hồi đúng nguồn quyền

### 10.1. Grant thuộc về đối tượng và delegation cá nhân khác nhau

Hai cách thiết kế có thể có ngữ nghĩa khác:

~~~text
Object-bound grant:
  một grant đã được cấp hợp lệ cho đối tượng;
  tiếp tục hiệu lực theo chính sách của đối tượng.

Personal delegation:
  quyền sử dụng phụ thuộc vào nguồn thẩm quyền
  của một người cụ thể.
~~~

Nếu owner A bị thu hồi, delegation phụ thuộc A cần bị thu hồi/tính lại theo hợp đồng. Nhưng một grant cộng tác đã được cấp độc lập thuộc về đối tượng không nhất thiết mất hiệu lực chỉ vì A là người bấm cấp lúc trước.

Cần lưu authority_source để phân biệt. Không ngầm chọn một trong hai cách khi dữ liệu không cho biết.

Lịch sử granted_by=A cũng không có nghĩa A tiếp tục giữ quyền trên grant hoặc đối tượng.

### 10.2. Pending invitation cần quy tắc hiệu lực nguồn

Trong chính sách lời mời ở bài này, lời mời phụ thuộc quyền người mời phải được kiểm tra lại khi nhận. Một owner bị loại không được tiếp tục cấp quyền qua link đã gửi trước đó.

Nếu invitation đã được một quy trình quản trị độc lập phê chuẩn, hiệu lực có thể theo nguồn đó. Phải lưu và kiểm tra rõ, không dùng một boolean “đã gửi mail” làm bằng chứng đủ.

### 10.3. Cache, token và liên kết tải

Sau khi ownership thay đổi:

- Các command nhạy cảm phải thấy dữ liệu quyền đủ mới theo cam kết.
- Cache hoặc chỉ mục quyền cần bị vô hiệu hóa/tính lại phù hợp.
- Token hoặc session chứa ảnh chụp quyền không được giữ quyền owner vô hạn.
- Danh sách đối tượng “của tôi” cần phản ánh nguồn quyền còn hiệu lực.
- Link tải đã cấp cần có hợp đồng hiệu lực/thu hồi rõ ràng.

Outbox giúp phát thông báo thay đổi bền vững, nhưng việc consumer xử lý sau không tự bảo đảm thu hồi tức thời ở mọi nơi. Nếu nghiệp vụ cần hiệu lực ngay, điểm tạo hiệu ứng phải có cơ chế kiểm tra đáp ứng điều đó, chẳng hạn kiểm chứng version quyền hiện tại.

Với liên kết tải là capability có thời hạn, không hứa thu hồi ngay nếu kiến trúc chỉ chờ link hết hạn. Nếu cần thu hồi sớm, phải có cơ chế thực thi tương ứng.

### 10.4. Công việc đã được tạo trước lúc thu hồi

Cần phân biệt:

- Trả kết quả/receipt của command đã hoàn tất.
- Tiếp tục một job chưa tạo hiệu ứng.
- Ghi nhận sự thật bên ngoài đã xảy ra.

Quyền tiếp tục job khi người khởi tạo mất ownership phải do chính sách công việc quy định. Worker dùng nguồn thẩm quyền và tenant đã được ràng buộc, không coi membership cũ là giấy phép vĩnh viễn.

Nếu hiệu ứng tài chính đã xảy ra, phải ghi nhận và giải quyết nghĩa vụ; xóa owner không hoàn tác thế giới bên ngoài.

### 10.5. Thu hồi quan hệ không thu hồi dữ liệu đã nhận

Thu hồi có thể ngăn các lần đọc hoặc hành động tiếp theo theo hợp đồng. Nó không xóa được bản sao dữ liệu mà người dùng đã tải hợp lệ trước đó.

Điều này làm rõ vì sao quyền export, dữ liệu nhạy cảm và chia sẻ ra ngoài cần được kiểm soát ngay lúc cấp, thay vì chỉ dựa vào khả năng xóa owner sau này.

## 11. Owner rời tổ chức và đối tượng cần phục hồi

### 11.1. Có owner row chưa chắc có người còn đủ điều kiện

Một person có thể bị khóa hoặc mất membership trong tenant trong khi quan hệ owner vẫn ACTIVE.

Không giữ quyền của một người đã bị thu hồi chỉ để duy trì số lượng owner nhìn có vẻ hợp lệ. Cần kiểm tra quyền thực tế và xử lý đối tượng mất người đại diện hợp lệ.

Nếu yêu cầu là mọi đối tượng ACTIVE luôn có owner đủ điều kiện, các luồng thay đổi membership cần được phối hợp với lifecycle đối tượng. Một job quét sau không tạo ra bảo đảm đồng bộ tức thời.

### 11.2. Trạng thái recovery rõ ràng hơn việc tự nhận quyền

Một chính sách có thể đưa đối tượng vào chế độ hạn chế khi không còn owner đủ điều kiện, rồi yêu cầu một tenant steward được cấp thẩm quyền xử lý.

Recovery cần xác định:

~~~text
Ai được xử lý đối tượng nào?
Cần bằng chứng/lý do gì?
Có cần người xác nhận độc lập không?
Người nhận mới có đủ điều kiện không?
Quyền nào được cấp và từ thời điểm nào?
Lịch sử, approval và job hiện có được giữ/xử lý ra sao?
~~~

Không cho người đầu tiên mở đối tượng tự claim ownership. Cũng không để một admin toàn cục tự động trở thành owner nghiệp vụ của mọi đối tượng.

Quyền hỗ trợ phục hồi cần có action/scope và audit riêng.

### 11.3. Giữ lịch sử sau khi danh tính ngừng hoạt động

Owner rời tổ chức không được làm mất bằng chứng ai đã tạo, sửa, chia sẻ hoặc duyệt nội dung.

Không ánh xạ lịch sử sang một nhân sự mới chỉ vì email cũ được tái sử dụng. Giữ định danh ổn định và quan hệ lịch sử phù hợp với chính sách dữ liệu.

Thay owner mới cũng không tự hợp thức hóa một quyết định cũ vốn thiếu phân tách nhiệm vụ.

## 12. Audit và quyền xem danh sách owner

Audit nên cho biết actor thực tế, đối tượng/tenant, loại thay đổi, người nhận hoặc bị thu hồi, nguồn quyền, proposal/xác nhận liên quan và ownership version trước/sau.

Nên phân biệt:

~~~text
Đề nghị thay đổi
Lời mời đã gửi
Người nhận đã chấp nhận
Quan hệ owner được kích hoạt
Quan hệ bị thu hồi
Recovery được thực hiện
~~~

Không ghi những trạng thái đó như cùng một sự kiện “đã chia sẻ”.

Danh sách owner, email lời mời và membership nhóm có thể là dữ liệu nhạy cảm. API phải kiểm tra quyền xem; một objectId đoán được không cho phép liệt kê người liên quan.

Response bị từ chối không nên tiết lộ toàn bộ owner hoặc tài khoản nội bộ. Không log token mời, thông tin xác thực hay payload nhạy cảm chỉ để phục vụ hỗ trợ.

## 13. Kiểm thử các đường lạm dụng đồng sở hữu

### 13.1. Bộ dữ liệu nền

Chuẩn bị một đối tượng X thuộc tenant A:

~~~text
Owner ACTIVE:
  person-A
  person-B

Editor:
  person-E

Viewer:
  person-V

Reviewer độc lập:
  person-R, có quyền review phù hợp

Người tạo trong lịch sử:
  person-A
~~~

Tạo thêm đối tượng Y ở tenant B để kiểm tra biên tenant. Nếu ID chỉ duy nhất trong tenant, có thể cố ý cho X và Y có cùng objectId cục bộ.

Các test cần xác nhận cả hành vi được cho phép và bị từ chối. Ví dụ editor sửa trường hợp lệ phải vẫn hoạt động, trong khi đổi owner qua cùng đường sửa bị chặn.

### 13.2. Ma trận tình huống

| Tình huống | Điều phải kiểm chứng |
|---|---|
| Editor gửi ownerIds trong PATCH nội dung | Không thêm/xóa owner qua quyền sửa |
| Viewer gọi endpoint mời hoặc quản lý owner | Không tạo invitation/grant ngoài quyền |
| Owner mời người nhận nhưng yêu cầu role vượt quyền cấp | Không kích hoạt quan hệ trái phép |
| Forward link mời cho tài khoản khác | Không nhận ownership nếu không khớp recipient binding |
| Invitation hết hạn, bị thu hồi hoặc đã dùng | Không tạo thêm owner |
| Người mời mất thẩm quyền trước acceptance | Áp dụng đúng quan hệ phụ thuộc, không dùng quyền cũ vô hạn |
| Pending invitation là “người còn lại” | Không cho xóa owner ACTIVE cuối cùng |
| Hai command cùng xóa hai owner còn lại | Tập owner không về rỗng; không tiêu thụ hai proposal trái bất biến |
| Một người dùng hai account xác nhận thay owner | Không đủ hai người độc lập |
| Hai nhóm cùng do một person đại diện | Không được đếm thành hai người nếu chính sách yêu cầu khác người |
| Proposal được duyệt cho target B nhưng command đổi sang C | Binding không khớp; không thay ownership |
| Ownership version đổi sau khi xác nhận | Không áp dụng proposal cũ tùy tiện |
| Thu hồi owner nhưng người đó có READ độc lập qua nhóm | Không giữ quyền owner; READ còn hay mất đúng nguồn grant |
| Thu hồi parent ownership | Mất quyền kế thừa tương ứng, grant trực tiếp ở con xử lý đúng chính sách |
| Đổi nhóm/folder/parent để đưa đối tượng vào scope mới | Cần quyền chuyển và kiểm tra tác động chia sẻ |
| Actor ở tenant khác biết objectId | Không được quản lý hoặc liệt kê owner của X |
| Lỗi audit/outbox bắt buộc khi thu hồi | Rollback quan hệ, version và việc tiêu thụ proposal |
| Retry thay đổi đã commit | Không tăng version hoặc tạo hiệu ứng quyền lần nữa |
| Owner cuối cùng bị vô hiệu hóa danh tính | Người đó không còn truy cập; đối tượng đi qua policy recovery phù hợp |
| Xóa ownership rồi cố tự duyệt nội dung mình từng sửa | Lịch sử phân tách nhiệm vụ vẫn được kiểm tra |
| Link tải/cache được tạo trước thu hồi | Hiệu lực theo đúng cam kết, không giả định đã thu hồi ngay |
| Job của owner đã bị thu hồi còn pending | Tiếp tục/chặn đúng chính sách job và nguồn thẩm quyền |

### 13.3. Kiểm thử xóa owner đồng thời

Tạo hai proposal hợp lệ trên cùng ownership version ban đầu:

~~~text
Proposal P1: xóa person-A.
Proposal P2: xóa person-B.
~~~

Dùng hai transaction/kết nối độc lập, điều phối để hai command thật sự cạnh tranh tại điểm bảo vệ tập owner.

Sau khi cả hai kết thúc, đọc lại bằng transaction mới:

- Còn ít nhất một owner ACTIVE trong mô hình đối tượng bình thường.
- Chỉ thay đổi hợp lệ được commit.
- Proposal không thực hiện không bị đánh dấu như đã tiêu thụ thành công.
- ownership_version, audit và outbox tương ứng với đúng thay đổi đã commit.
- Không có một response thành công cho thao tác thực tế đã rollback.

Không chỉ chạy hai command nối tiếp hoặc mock count=2 ở cả hai lần. Cần kiểm tra giao thức transaction thật sự bảo vệ bất biến xuyên nhiều dòng.

### 13.4. Chèn lỗi giữa thu hồi và hoàn tất transaction

Ví dụ đặt lỗi có kiểm soát khi ghi outbox bắt buộc:

~~~text
Trước:
  owners = {A, B}
  ownership_version = 7
  proposal = approved, chưa dùng

Trong transaction:
  thu hồi A
  tăng version
  đánh dấu proposal đã dùng
  insert outbox → lỗi

Sau rollback:
  owners = {A, B}
  ownership_version = 7
  proposal chưa bị tiêu thụ thành công
  không có audit thành công của thay đổi
  không có event thay ownership của lần thử
~~~

Ca kiểm thử này chứng minh các thay đổi bắt buộc cùng ranh giới commit, thay vì chỉ chứng minh các hàm save đã được gọi.

Nếu trace/security event của lần lỗi được ghi độc lập, phải phân biệt nó với audit nghiệp vụ thành công.

### 13.5. Kiểm thử thu hồi theo nhiều nguồn quyền

Cho B vừa là owner trực tiếp của X, vừa có grant READ qua group-G. Thu hồi owner trực tiếp của B.

Kiểm tra:

~~~text
B không còn quyền owner chỉ từ quan hệ đã thu hồi.
B vẫn chỉ có các action mà group-G thực sự cấp.
B không được quản lý owner hoặc xóa X nếu không có nguồn cấp riêng.
UI/audit không tuyên bố đã xóa mọi truy cập khi READ còn hiệu lực.
~~~

Sau đó thu hồi membership group-G và kiểm tra quyền READ cập nhật theo cam kết. Ca này phát hiện cả hai lỗi: giữ lại quá nhiều quyền và thu hồi nhầm quyền độc lập.

### 13.6. Kiểm thử lịch sử không bị “rửa” qua ownership

Thử chuỗi:

~~~text
A tạo/sửa số tiền.
B thêm A làm co-owner.
A bị chuyển khỏi editor hoặc bị xóa owner.
A được phân một quyền reviewer ở phạm vi phù hợp.
A cố approve chính nội dung đã tham gia.
~~~

Nếu chính sách cấm người lập/sửa duyệt hồ sơ, bước cuối phải bị chặn dù quan hệ owner hiện tại đã thay đổi.

Đổi role hoặc owner không được viết lại sự thật về ai đã tham gia nội dung.

## 14. Tình huống thực hành: thêm người để chiếm quyền quản lý

X có hai owner A và B. Chính sách yêu cầu hai owner hiện có, khác người, xác nhận thay đổi quan trọng. B bị chiếm tài khoản.

Kẻ tấn công thử:

~~~text
1. B gửi lời mời OWNER cho tài khoản C do mình kiểm soát.
2. C chấp nhận.
3. B và C xác nhận xóa A.
4. B xóa lịch sử hoặc chuyển hồ sơ sang phạm vi khác.
~~~

Những điểm cần phân tích:

- B có được một mình kích hoạt C thành owner không, hay việc đó cũng cần phê chuẩn?
- Sự đồng ý của C có bị nhầm là xác nhận của một owner hiện có không?
- Proposal được gắn với tập owner/version nào?
- Hai account B và C có thực sự là hai person độc lập không?
- Quyền xóa, chuyển và sửa lịch sử có được tách khỏi ownership thông thường không?
- Recovery có ngăn việc A bị loại qua một đường ngoại lệ không đúng thẩm quyền không?

Với chính sách đã nêu, invitation của B không được tự tạo một owner có quyền bỏ phiếu để hoàn tất chính thay đổi chưa được chấp thuận. Mỗi bước cấp thêm quyền phải đáp ứng chính sách tại thời điểm thực hiện.

Nếu một sản phẩm chủ ý cho mọi owner tự do thêm/xóa các owner khác, đó là một mô hình tin cậy khác và phải chấp nhận tác động tương ứng. Không mô tả nó như cơ chế đồng thuận hai người chỉ vì đối tượng hiện có hai owner.

### 14.1. Thay đổi yêu cầu chính sách sẽ đổi hành vi

Cộng tác tài liệu thông thường và quản lý hồ sơ chi trả có thể cần mức kiểm soát khác nhau.

Không nhất thiết mọi sửa đổi nhỏ đều cần toàn bộ owner đồng ý. Có thể tách:

~~~text
Nội dung thông thường:
  một editor/owner đủ quyền thực hiện.

Cấp viewer/editor:
  theo quyền SHARE và giới hạn dữ liệu.

Thay owner, xóa hoặc mở rộng chia sẻ nhạy cảm:
  xác nhận hoặc chính sách quản trị mạnh hơn.

Duyệt/chi trả:
  quy trình nghiệp vụ độc lập.
~~~

Việc tách hành động giúp bảo vệ điểm có rủi ro mà vẫn giữ cộng tác sử dụng được.

## 15. Khung đặc tả shared ownership

Trước khi triển khai, hãy ghi rõ:

~~~text
Đối tượng và tenant đích:
Owner là person, group hay loại principal nào:
Creator, owner, assignee, editor và reviewer khác nhau ra sao:

Quyền mỗi loại quan hệ:
Ai được cấp, nâng, hạ và thu hồi quan hệ:
Các hành động cần nhiều người xác nhận:
Đơn vị độc lập và cách tính quorum:

Invitation, recipient binding, hiệu lực và acceptance:
Bất biến owner cuối cùng:
Khóa/version/constraint bảo vệ tập owner:
Quy tắc chuyển nhóm, parent và kế thừa:

Nguồn quyền object-bound và delegation cá nhân:
Hiệu lực thu hồi ở cache, token, link và job:
Lifecycle danh tính, offboarding và recovery:
Audit, quyền xem danh sách owner và dữ liệu nhạy cảm:
Ca kiểm thử đồng thời, lỗi giữa chừng và vượt quyền:
~~~

## 16. Câu hỏi tự kiểm tra

1. Vì sao editor không nên tự trở thành owner qua một payload cập nhật tổng quát?
2. Hai owner có đồng nghĩa một hành động đã được hai người phê duyệt không?
3. Pending invitation có bảo vệ được bất biến owner cuối cùng không?
4. Vì sao version riêng trên từng dòng owner có thể không chặn hai lần thu hồi đồng thời?
5. Khi một owner bị xóa, những grant nào phụ thuộc họ và những grant nào độc lập?
6. Với group owner, ai được đại diện nhóm và cách nào ngăn đếm trùng cùng một người?
7. Khi owner cuối cùng bị khóa tài khoản, hệ thống giữ an toàn và phục hồi trách nhiệm như thế nào?
8. Thay ownership có ảnh hưởng gì đến approval, lịch sử người sửa và job đang chờ?
9. Giao diện có thể chứng minh “đã thu hồi mọi truy cập” bằng cách nào khi còn nhiều nguồn grant?

Một mô hình đồng sở hữu có thể kiểm chứng phải giữ được **quan hệ quyền rõ ràng, thay đổi có thẩm quyền và trách nhiệm không bị mất khi nhiều người cùng thao tác**. Mọi lời mời, thu hồi, kế thừa và phục hồi đều phải bảo vệ các bất biến đó trong đúng biên tenant và transaction.
