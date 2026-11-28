# Tenant membership

## 1. Tenant membership là gì?

Trong một hệ thống nhiều tenant, **tenant membership** là quan hệ xác định một chủ thể thuộc tenant nào, đang ở trạng thái nào và có thể được gán quyền trong phạm vi tenant đó ra sao. Tenant có thể đại diện cho một doanh nghiệp, một tổ chức khách hàng hoặc một không gian làm việc có ranh giới truy cập riêng.

Ví dụ, Lan có một tài khoản trên nền tảng quản lý dự án. Lan là quản trị viên của Công ty An và là người xem của Công ty Bình. Hai quan hệ này độc lập:

| Chủ thể | Tenant | Trạng thái membership | Vai trò trong tenant |
|---|---|---|---|
| Lan | Công ty An | ACTIVE | ADMIN |
| Lan | Công ty Bình | ACTIVE | VIEWER |
| Lan | Công ty Cường | Không có membership | Không có |

Việc Lan đăng nhập thành công chỉ xác nhận danh tính của Lan. Việc Lan thuộc Công ty An không cho phép Lan xem dữ liệu Công ty Bình, và quyền ADMIN ở Công ty An không đi theo Lan sang Công ty Bình.

Có thể hình dung:

> Tài khoản trả lời “ai đang sử dụng hệ thống”; membership trả lời “chủ thể này có quan hệ gì với tenant đang xét”; chính sách phân quyền trả lời “trong quan hệ đó, hành động cụ thể có được phép không”.

Membership là một đầu vào quan trọng của quyết định truy cập, nhưng không thay thế toàn bộ cơ chế phân quyền.

## 2. Phân biệt danh tính, membership, vai trò và tenant đang chọn

Bốn khái niệm thường bị trộn lẫn cần được tách rõ:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Danh tính hoặc tài khoản | Chủ thể là ai? | Subject nội bộ `u-174` |
| Tenant | Ranh giới tổ chức hoặc dữ liệu nào? | `tenant-an` |
| Membership | Chủ thể có thuộc tenant đó và còn hiệu lực không? | `u-174` là thành viên ACTIVE của `tenant-an` |
| Vai trò hoặc quyền | Chủ thể được làm gì trong tenant? | ADMIN được mời thành viên; VIEWER chỉ đọc tài nguyên được phép |

“Tenant đang chọn” trong giao diện chỉ là ngữ cảnh điều hướng. Nó không phải bằng chứng rằng tài khoản được phép hoạt động trong tenant đó. Mọi tenant ID từ URL, header, biểu mẫu hay bộ nhớ trình duyệt đều cần được máy chủ kiểm tra.

Tương tự, một tài khoản có trạng thái ACTIVE toàn hệ thống vẫn có thể bị SUSPENDED ở một tenant. Một membership ACTIVE cũng không đủ để truy cập nếu tài khoản đã bị khóa toàn cục hoặc tenant đã bị vô hiệu hóa theo chính sách vận hành.

Một công thức khái niệm cho hành động đọc tài liệu là:

```text
cho phép =
    danh tính đã được xác thực và được phép hoạt động
    AND tenant mục tiêu được phép hoạt động
    AND membership của đúng subject trong đúng tenant là ACTIVE
    AND chính sách cho phép hành động đọc tài liệu
    AND tài liệu thuộc đúng tenant mục tiêu
```

Một số hệ thống còn kiểm tra quyền theo từng tài nguyên, thời hạn truy cập, mức xác thực hoặc điều kiện thiết bị. Do đó, membership ACTIVE không có nghĩa là được đọc mọi dữ liệu trong tenant.

## 3. Mô hình dữ liệu cho membership

### 3.1. Khóa quan hệ bằng subject và tenant

Một mô hình cơ bản thường gồm:

- `subjects`: danh tính nội bộ ổn định của người dùng hoặc loại chủ thể được hệ thống hỗ trợ.
- `tenants`: các tenant và trạng thái của chúng.
- `tenant_memberships`: quan hệ giữa subject và tenant.
- `membership_role_assignments`: các vai trò được gán cho một membership.
- `tenant_invitations`: lời mời chưa nhất thiết đã trở thành membership có hiệu lực.

Trong mô hình giữ lại một bản ghi quan hệ cho mỗi cặp subject–tenant, ràng buộc quan trọng là:

```text
UNIQUE (tenant_id, subject_id)
```

Ràng buộc này ngăn hai yêu cầu chạy đồng thời tạo ra hai membership riêng cho cùng một quan hệ. Nếu cần hỗ trợ nhiều giai đoạn gia nhập, có thể lưu lịch sử sự kiện bên cạnh bản ghi hiện tại. Một thiết kế lưu nhiều bản ghi lịch sử trong cùng bảng phải có ràng buộc phù hợp để không xuất hiện hai quan hệ hiện hành mâu thuẫn.

Không dùng email làm khóa membership. Email có thể thay đổi, có thể xuất hiện trong nhiều nguồn danh tính và không tự chứng minh quyền gia nhập một tenant.

Khi liên kết đăng nhập bên ngoài, hệ thống cần ánh xạ định danh ổn định của nguồn xác thực sang subject nội bộ theo quy tắc liên kết đã xác minh. Không tự gộp hai tài khoản chỉ vì chúng trả về cùng một chuỗi email.

### 3.2. Ví dụ schema tối giản

Ví dụ SQL dưới đây minh họa phần quan hệ thành viên. Nó chưa bao gồm bảng role, lời mời, nhật ký và toàn bộ ràng buộc nghiệp vụ của một ứng dụng hoàn chỉnh.

```sql
CREATE TABLE tenant_memberships (
    membership_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    subject_id VARCHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL,
    authorization_version BIGINT NOT NULL DEFAULT 1,
    joined_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL,
    removed_at TIMESTAMP,
    CONSTRAINT uq_membership_tenant_subject
        UNIQUE (tenant_id, subject_id),
    CONSTRAINT fk_membership_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id),
    CONSTRAINT fk_membership_subject
        FOREIGN KEY (subject_id) REFERENCES subjects(subject_id),
    CONSTRAINT ck_membership_status
        CHECK (status IN ('PENDING', 'ACTIVE', 'SUSPENDED', 'REMOVED'))
);
```

Ý nghĩa của một số trường:

| Trường | Mục đích |
|---|---|
| `membership_id` | Định danh quan hệ để tham chiếu khi gán vai trò và ghi audit |
| `tenant_id`, `subject_id` | Xác định chính xác quan hệ cần đánh giá |
| `status` | Thể hiện khả năng sử dụng membership theo vòng đời |
| `authorization_version` | Giúp phát hiện phiên hoặc cache mang thông tin quyền cũ |
| `joined_at` | Thời điểm quan hệ được kích hoạt theo mô hình đã chọn |
| `removed_at` | Hỗ trợ lưu vết việc rời tenant mà không xóa lịch sử |

`authorization_version` chỉ hữu ích nếu luồng kiểm tra thực sự so sánh nó với trạng thái có thẩm quyền. Việc tăng một con số trong cơ sở dữ liệu tự nó không vô hiệu hóa token đã phát hành.

Nếu vai trò được định nghĩa theo tenant, quan hệ gán vai trò phải bảo đảm role và membership thuộc cùng tenant. Có thể dùng khóa ngoại ghép hoặc một cơ chế ràng buộc tương đương ở tầng lưu trữ; không chỉ dựa vào việc giao diện đã lọc danh sách role.

## 4. Vòng đời của membership

Tên trạng thái tùy thiết kế, nhưng cần định nghĩa rõ hành vi của từng trạng thái.

| Trạng thái | Ý nghĩa | Được dùng để truy cập nghiệp vụ? |
|---|---|---|
| PENDING | Đã có yêu cầu hoặc quan hệ chờ hoàn tất điều kiện gia nhập | Chưa |
| ACTIVE | Đã hoàn tất điều kiện gia nhập, chưa bị đình chỉ hoặc loại bỏ | Có thể, nếu các điều kiện phân quyền khác cũng đạt |
| SUSPENDED | Quan hệ tạm thời không được sử dụng | Không |
| REMOVED | Quan hệ đã chấm dứt | Không |

Một lời mời chưa được chấp nhận có thể chỉ tồn tại trong bảng invitation. Không nhất thiết phải tạo một subject hoặc một membership PENDING khi người được mời chưa có tài khoản.

Các chuyển trạng thái thường gặp:

```text
PENDING   --hoàn tất chấp thuận/phê duyệt--> ACTIVE
ACTIVE    --đình chỉ---------------------> SUSPENDED
SUSPENDED --khôi phục có thẩm quyền------> ACTIVE
ACTIVE    --rời tenant/bị loại bỏ--------> REMOVED
SUSPENDED --chấm dứt quan hệ-------------> REMOVED
```

Mỗi mũi tên phải có điều kiện và người thực hiện được phép. Không cung cấp một API chung cho phép client gửi bất kỳ giá trị `status` nào rồi cập nhật trực tiếp.

Gia nhập lại sau khi REMOVED cần là một quyết định rõ ràng. Hệ thống có thể kích hoạt lại bản ghi cũ theo một lần phê duyệt mới, nhưng không nên tự động khôi phục mọi vai trò đặc quyền từng có. Lịch sử cũ phục vụ audit, không phải căn cứ cấp lại quyền.

## 5. Cấp membership bằng lời mời

Một luồng mời thành viên an toàn có thể triển khai theo trình tự:

1. Người mời đăng nhập và chọn tenant.
2. Máy chủ kiểm tra membership của người mời còn ACTIVE trong tenant đó và người mời có quyền mời thành viên.
3. Máy chủ xác định vai trò được phép cấp. Có quyền mời không mặc nhiên có quyền cấp OWNER hoặc ADMIN.
4. Hệ thống tạo invitation gắn với tenant, đối tượng nhận dự kiến, vai trò đã được phê duyệt và thời hạn.
5. Người nhận đăng nhập, chứng minh đáp ứng điều kiện nhận lời mời và xác nhận gia nhập.
6. Máy chủ kiểm tra lại invitation và điều kiện phê duyệt còn hiệu lực, rồi tạo hoặc kích hoạt membership trong giao dịch phù hợp.
7. Hệ thống đánh dấu invitation đã sử dụng và ghi audit.

Token mời cần khó đoán, có hạn sử dụng, có thể thu hồi và chỉ dùng một lần. Có thể chỉ lưu giá trị băm của token để hạn chế tác động khi dữ liệu lưu trữ bị lộ. Không ghi token nguyên vẹn vào log.

Nếu invitation ràng buộc với email, ứng dụng phải kiểm tra bằng chứng kiểm soát địa chỉ tương ứng từ luồng đã tin cậy; không lấy trường email do client tự gửi làm chứng cứ. Email trong invitation là điều kiện nhận lời mời theo chính sách, không trở thành định danh chính của membership.

Việc chấp nhận invitation nên xử lý nguyên tử các bước kiểm tra chưa dùng, tạo quan hệ và đánh dấu đã dùng. Hai lần nhấp hoặc hai request đồng thời không được tạo hai quan hệ hay gán hai bộ vai trò khác nhau. Với invitation đã được chính subject đó chấp nhận thành công, ứng dụng có thể trả lại kết quả cũ theo thiết kế idempotency; không diễn giải request lặp thành một lần cấp quyền mới.

Lời mời cũng có thể hết tính hợp lệ trước thời hạn trên token: tenant đã bị khóa, lời mời bị thu hồi hoặc quyền cấp vai trò không còn đáp ứng chính sách. Máy chủ cần có quy tắc kiểm tra các tình huống này ở lúc chấp nhận.

## 6. Cấp membership từ SSO, directory và provisioning

SSO giúp xác thực người dùng, nhưng xác thực thành công chưa đủ để kết luận người đó là thành viên của mọi tenant sử dụng cùng nhà cung cấp danh tính.

Cần xác định rõ nguồn có thẩm quyền đối với membership:

| Cách cấp | Căn cứ tạo quan hệ | Điều cần kiểm soát |
|---|---|---|
| Mời thủ công | Người có thẩm quyền trong tenant phê duyệt | Người nhận, vai trò và thời hạn của invitation |
| Quản trị viên thêm trực tiếp | Một thao tác quản trị đã được kiểm tra quyền | Subject đích và phạm vi quyền người quản trị được cấp |
| Provisioning từ directory | Kết nối được tenant cấu hình và dữ liệu đồng bộ hợp lệ | Phạm vi tenant, trạng thái và quy tắc gỡ thành viên |
| Just-in-time khi đăng nhập | Chính sách của một kết nối danh tính đã được tenant chấp thuận | Điều kiện gia nhập và vai trò mặc định ít quyền |

Không cấp membership chỉ vì email có hậu tố giống tên miền công ty. Tên miền có thể là một tín hiệu trong quy trình gia nhập đã được cấu hình, nhưng cần gắn với tenant, bằng chứng kiểm soát và chính sách cụ thể.

Một nhóm từ directory cũng không nên trở thành role toàn hệ thống bằng cách so khớp tên nhóm. Mapping phải gắn với đúng kết nối danh tính và đúng tenant. Hai tenant có thể cùng có nhóm tên “Administrators” nhưng chúng không chia sẻ quyền.

Với JIT, cần quyết định điều gì xảy ra khi một membership đã bị REMOVED trước đó. Nếu mỗi lần đăng nhập SSO lại tự tạo ACTIVE, thao tác loại bỏ người dùng trong ứng dụng sẽ mất tác dụng. Thiết kế phải xác định nguồn nào có quyền tái cấp quan hệ và cách ghi nhận quyết định đó.

Nếu quản trị thủ công và provisioning cùng được phép cập nhật một membership, phải có quy tắc giải quyết xung đột. Ví dụ, trạng thái khóa khẩn cấp của ứng dụng có thể cần được giữ cho đến khi người có thẩm quyền gỡ khóa, thay vì bị lần đồng bộ định kỳ tiếp theo ghi đè.

## 7. Kiểm tra membership trong mỗi ngữ cảnh truy cập

### 7.1. Ràng buộc ba định danh

Đối với một request truy cập dữ liệu tenant, máy chủ phải ràng buộc ít nhất:

```text
subject đã xác thực
       +
tenant mục tiêu đã được kiểm tra
       +
tài nguyên thực sự thuộc tenant mục tiêu
```

Ví dụ request:

```http
GET /tenants/tenant-an/documents/doc-82
Authorization: Bearer <access-token>
```

Luồng xử lý khái niệm:

```text
subject = lấy từ ngữ cảnh xác thực đã được kiểm chứng
tenant  = phân giải tenant mục tiêu của request
membership = tìm theo (tenant.id, subject.id)

nếu membership không tồn tại hoặc không ACTIVE:
    từ chối

nếu chính sách không cho membership thực hiện document.read:
    từ chối

document = tìm theo (tenant.id, documentId)

nếu document không tồn tại hoặc quyền trên document không đạt:
    từ chối theo quy ước phản hồi của API

trả về document
```

Tenant ID trong URL là dữ liệu yêu cầu, không phải dữ liệu đáng tin cậy sẵn có. Máy chủ biến nó thành ngữ cảnh được phép sử dụng sau khi kiểm tra các điều kiện liên quan.

Việc tìm membership chỉ bằng `subject_id` là sai vì một subject có thể thuộc nhiều tenant. Việc kiểm tra chỉ có membership mà bỏ qua trạng thái cũng cho phép tài khoản đã bị đình chỉ tiếp tục sử dụng quan hệ.

### 7.2. Truy vấn tài nguyên luôn có tenant scope

Một truy vấn đọc tài liệu có thể thể hiện trực tiếp điều kiện tenant và membership:

```sql
SELECT d.document_id, d.title
FROM documents d
WHERE d.tenant_id = :tenant_id
  AND d.document_id = :document_id
  AND EXISTS (
      SELECT 1
      FROM tenant_memberships m
      WHERE m.tenant_id = d.tenant_id
        AND m.subject_id = :authenticated_subject_id
        AND m.status = 'ACTIVE'
  );
```

Đây chỉ là phần kiểm tra quan hệ và ranh giới tenant. Nếu ứng dụng có role, quyền theo tài liệu hoặc trạng thái khóa toàn cục, các điều kiện đó vẫn phải được thực thi.

Với cập nhật dữ liệu, cũng cần ràng buộc tenant trong câu lệnh ghi. Không kiểm tra một tài liệu rồi chạy một câu `UPDATE` khác chỉ theo document ID do client gửi mà đánh mất tenant scope.

Nếu membership có thể bị thu hồi giữa lúc kiểm tra và lúc ghi, cần xác định mức nhất quán mà nghiệp vụ yêu cầu. Thao tác nhạy cảm có thể cần kiểm tra lại trong cùng giao dịch, khóa phù hợp hoặc đối chiếu phiên bản quyền để tránh dùng kết quả kiểm tra đã lỗi thời. Một lần kiểm tra ở đầu request không tự bảo đảm rằng quyền vẫn còn ở thời điểm mọi tác vụ phía sau thực hiện.

## 8. Membership trong phiên đăng nhập, token và cache

Token có thể chứa tenant đang hoạt động hoặc một phiên bản quyền để hỗ trợ xử lý request. Tuy nhiên:

- Token hợp lệ về chữ ký không chứng minh membership vẫn ACTIVE tại thời điểm hiện tại.
- Một role được chụp vào token có thể đã bị thay đổi trong cơ sở dữ liệu.
- Token cấp cho tenant A không được tái sử dụng như bằng chứng quyền trong tenant B.
- Danh sách tenant trong giao diện có thể là dữ liệu cache và cần được kiểm tra lại khi chuyển tenant.

Khi người dùng đổi tenant, máy chủ cần xác minh membership của tenant mới. Nếu phát hành token gắn tenant, việc phát hành phải diễn ra sau kiểm tra đó. Nếu dùng phiên chung cho nhiều tenant, từng request vẫn cần được đánh giá trong tenant cụ thể.

Cache membership cần có khóa chứa cả tenant và subject:

```text
membership-cache:{tenant_id}:{subject_id}
```

Nếu cache quyết định truy cập còn phụ thuộc role, tài nguyên hoặc phiên bản chính sách, khóa hoặc cơ chế vô hiệu hóa cũng phải phản ánh các đầu vào đó. Khóa chỉ theo user ID có thể làm quyền của tenant này bị dùng nhầm cho tenant khác.

Có thể kết hợp thời hạn cache ngắn, sự kiện vô hiệu hóa, phiên bản quyền và tra cứu trực tiếp cho hành động nhạy cảm. Thiết kế cần nêu rõ khoảng thời gian tối đa một quyết định cũ có thể còn được sử dụng. Nếu cần thu hồi tức thời, không thể chỉ trông chờ token tự hết hạn mà không có cơ chế kiểm tra hiệu lực hiện tại.

Không mặc định cho phép khi dịch vụ kiểm tra membership lỗi. Một hệ thống được phép dùng bản cache còn hiệu lực khi nguồn dữ liệu tạm gián đoạn phải có chính sách rõ ràng về tuổi cache và loại hành động được phép, thay vì coi lỗi tra cứu là membership ACTIVE.

## 9. Thu hồi membership và quản lý đặc quyền

Loại bỏ thành viên khỏi một tenant phải làm mất khả năng sử dụng quyền của tenant đó, không chỉ làm biến mất tên người dùng khỏi màn hình quản trị.

Các phần cần được xử lý theo chính sách thu hồi gồm:

- Chuyển membership sang trạng thái không được truy cập và ghi nguyên nhân.
- Gỡ hoặc làm mất hiệu lực các gán quyền phụ thuộc membership.
- Vô hiệu hóa cache và phiên tenant hoặc cơ chế kiểm tra token có liên quan.
- Kiểm tra lại tác vụ nền, kết nối dài và hoạt động đang dùng quyền của thành viên.
- Xử lý các credential hoặc ủy quyền tenant được cấp theo quan hệ đó.
- Chuyển quyền sở hữu tài nguyên nếu nghiệp vụ yêu cầu, đồng thời giữ lịch sử người tạo.

Một người bị loại khỏi tenant A vẫn có thể là thành viên hợp lệ của tenant B. Thu hồi membership tenant A không nhất thiết phải khóa tài khoản toàn cục của người đó. Ngược lại, sự cố chiếm đoạt tài khoản có thể cần một quyết định khóa toàn cục riêng.

Không suy diễn rằng mọi workload do người dùng từng tạo đều phải bị xóa. Cần phân biệt credential cá nhân hoạt động theo quyền thành viên với workload thuộc tổ chức và có danh tính riêng. Mỗi loại có vòng đời, người sở hữu vận hành và chính sách thu hồi tương ứng.

Đối với đặc quyền quản trị:

- Quyền quản lý thành viên phải gắn với tenant và hành động cụ thể.
- Người được mời người khác không mặc nhiên được cấp mọi role.
- Thay đổi OWNER hoặc cấp quyền nhạy cảm có thể yêu cầu xác thực lại hoặc phê duyệt bổ sung.
- Tự rời tenant phải được kiểm tra bằng quy tắc riêng nếu làm tenant không còn người quản trị hợp lệ.

Nếu chính sách yêu cầu tenant luôn có ít nhất một OWNER, hai OWNER cùng rời tenant là một tình huống cạnh tranh cần xử lý ở phía máy chủ. Đếm OWNER ở hai request độc lập rồi cùng cho phép rời đi có thể làm mất cả hai OWNER. Cần tuần tự hóa quyết định trên cùng tenant hoặc áp dụng cơ chế nhất quán tương đương.

Tài khoản hỗ trợ nền tảng không nên được cấp quyền xuyên tenant chỉ vì một cờ role chung xuất hiện trong phiên. Truy cập hỗ trợ, nếu sản phẩm cho phép, cần là luồng đặc quyền riêng với tenant đích, phạm vi, thời hạn và audit rõ ràng.

## 10. Audit của membership

Nhật ký membership cần giúp trả lời được ai đã thay đổi quan hệ nào, ở tenant nào, khi nào và dựa trên căn cứ gì.

Một sự kiện có thể chứa:

```json
{
  "event_type": "tenant_membership.suspended",
  "tenant_id": "tenant-an",
  "membership_id": "m-508",
  "subject_id": "u-174",
  "actor_subject_id": "u-009",
  "previous_status": "ACTIVE",
  "new_status": "SUSPENDED",
  "source": "tenant_admin",
  "reason_code": "ACCESS_REVIEW",
  "request_id": "req-728",
  "occurred_at": "2026-04-08T09:00:00Z"
}
```

Thời điểm trên là dữ liệu ví dụ. Trong triển khai thực tế, thời gian, actor và nguồn thao tác phải do hệ thống ghi nhận từ ngữ cảnh đáng tin cậy.

Ngoài sự kiện thành công, những lần cố gắng gia nhập trái phép, dùng invitation đã thu hồi hoặc cấp role vượt thẩm quyền cũng có giá trị phát hiện sự cố. Log không được chứa token mời, access token hoặc thông tin bí mật dùng để xác thực.

Khi một tài khoản rời tenant, lịch sử audit vẫn cần giữ được định danh chủ thể theo chính sách lưu trữ. Việc xóa hoặc ẩn thông tin hồ sơ không nên làm mọi sự kiện cũ biến thành hành động của một chủ thể không thể phân biệt.

## 11. Ví dụ xuyên suốt: Lan thuộc hai tenant

Giả sử:

```text
Lan / tenant-an   : ACTIVE, ADMIN
Lan / tenant-binh : ACTIVE, VIEWER
```

Các quyết định cần diễn ra như sau:

| Tình huống | Quyết định mong đợi | Căn cứ |
|---|---|---|
| Lan mời người vào tenant-an | Có thể cho phép | Membership ACTIVE và role ADMIN có quyền mời |
| Lan mời người vào tenant-binh | Từ chối | VIEWER không có quyền mời |
| Lan đổi URL từ tenant-an sang tenant-cuong | Từ chối | Không có membership ở tenant-cuong |
| Lan dùng tenant-an nhưng gửi ID tài liệu của tenant-binh | Không trả tài liệu | Truy vấn và quyền tài nguyên bị ràng buộc bởi tenant-an |
| Lan bị SUSPENDED ở tenant-an rồi dùng token cũ | Từ chối theo cơ chế thu hồi đã thiết kế | Trạng thái hoặc phiên bản quyền hiện tại không còn cho phép |
| Lan tiếp tục đọc tài liệu được phép ở tenant-binh | Có thể cho phép | Membership tenant-binh vẫn ACTIVE và quyền đọc vẫn đạt |

Điểm quan trọng là mọi quyết định đều được đánh giá trên đúng cặp subject–tenant và đúng hành động. Không có bước nào lấy role ADMIN của tenant-an rồi dùng cho tenant-binh.

Nếu giao diện vẫn hiển thị tenant-an sau khi Lan bị đình chỉ vì danh sách tenant chưa được làm mới, API vẫn phải từ chối quyền đã bị thu hồi. Việc làm mới giao diện giúp trải nghiệm rõ ràng hơn, nhưng kiểm soát truy cập nằm ở phía máy chủ.

## 12. Các lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Lưu một role chung trên user cho mọi tenant | Quyền quản trị bị lan sang tenant khác | Gán role theo membership và tenant |
| Lấy tenant từ client rồi dùng ngay | Client có thể yêu cầu thao tác trong tenant không được phép | Kiểm tra subject–tenant và quyền hành động |
| Tìm tài nguyên chỉ bằng ID | Có thể đọc hoặc sửa dữ liệu ngoài tenant mục tiêu | Truy vấn có tenant scope và kiểm tra quyền tài nguyên |
| Xem lời mời đã gửi là membership ACTIVE | Người chưa hoàn tất gia nhập có thể có quyền | Phân biệt invitation với quan hệ đã được kích hoạt |
| Tin email hoặc tên nhóm để tự cấp quyền | Tạo quan hệ hoặc đặc quyền sai tenant | Xác minh nguồn và mapping theo tenant |
| Gỡ thành viên nhưng giữ cache/token quyền cũ vô hạn | Quyền cũ tiếp tục được sử dụng | Có thời hạn và cơ chế vô hiệu hóa phù hợp yêu cầu thu hồi |
| JIT tự hồi sinh mọi membership REMOVED | Việc loại bỏ thành viên không có hiệu lực bền vững | Xác định thẩm quyền tái cấp và trạng thái chặn |
| Xóa tài khoản toàn cục khi rời một tenant | Làm gián đoạn quan hệ hợp lệ ở tenant khác | Tách vòng đời account và membership |
| Không xử lý cạnh tranh khi đổi OWNER | Tenant có thể mất toàn bộ OWNER | Kiểm soát nhất quán thao tác thay đổi đặc quyền |

Một thiết kế membership tốt biểu diễn được quan hệ hiện tại, giữ được lịch sử và kiểm tra được quan hệ đó trong từng quyết định truy cập. Khi kết hợp membership với RBAC hoặc ABAC, phiên đăng nhập, provisioning và audit, hệ thống mới duy trì được nguyên tắc ít quyền nhất trong từng tenant.
