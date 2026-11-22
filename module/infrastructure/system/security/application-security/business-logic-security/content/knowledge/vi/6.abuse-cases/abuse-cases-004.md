# Privilege abuse scenario — Kịch bản lạm dụng quyền trong quy trình nghiệp vụ

## 1. Mục tiêu và phạm vi

Trong chương **Abuse Cases**, một kịch bản lạm dụng quyền mô tả cách chủ thể sử dụng một khả năng sẵn có để tạo kết quả vượt thẩm quyền. Chủ thể có thể đã đăng nhập hợp lệ, đang giữ một vai trò thật và không sửa token; lỗi nằm ở cách ứng dụng quyết định quyền đối với hành động và đối tượng cụ thể.

Tài sản bị ảnh hưởng có thể là quyết định phê duyệt, tiền, hàng hóa, dữ liệu, quyền truy cập hoặc khả năng hoàn tất quy trình. Một lần tự duyệt thành công có thể mở đường cho nhiều tác dụng phía sau dù request ban đầu chỉ thay một trạng thái.

Sau bài học, bạn có thể:

- Phân biệt quyền gọi chức năng, quyền theo đối tượng và điều kiện nghiệp vụ.
- Viết abuse scenario có actor, quyền hợp lệ ban đầu, chuỗi hành động và kết quả bị cấm.
- Phát hiện việc ghép quyền từ nhiều phạm vi thành thẩm quyền không được cấp.
- Bảo vệ quy tắc không tự duyệt, giới hạn theo tổ chức/đơn vị và nội dung được chấp nhận.
- Gắn quyết định quyền với máy trạng thái, transaction, idempotency và bằng chứng kiểm toán.
- Thiết kế ma trận kiểm thử cho các đường UI, API, batch và worker.

Ví dụ sử dụng quy trình đề nghị mua hàng trong một tổ chức có nhiều đơn vị. Vai trò, số tiền và chính sách là giả định học tập; không yêu cầu người học truy cập một hệ thống thực để thực hiện tình huống.

## 2. Quyền phải gắn với hành động, đối tượng và điều kiện

Một câu hỏi như “người này có vai trò quản lý không?” chưa đủ để quyết định họ được duyệt đề nghị nào. Cần xác định:

```text
Ai đang thực hiện?
Hành động nào được yêu cầu?
Đối tượng thuộc tenant, đơn vị và quan hệ xử lý nào?
Quyền nào cho phép chính tổ hợp đó?
Trạng thái, hạn mức và phiên bản nào còn hợp lệ?
Có điều kiện cấm như tự duyệt hoặc xung đột trách nhiệm không?
```

### 2.1. Các kiểu sai phạm có thể chồng lên nhau

| Tình huống | Khoảng trống chính |
| --- | --- |
| Người không có quyền duyệt vẫn gọi được chức năng duyệt | Quyền ở cấp chức năng |
| Người được duyệt đơn vị Y lại duyệt đề nghị đơn vị X | Quyền theo đối tượng và phạm vi |
| Người có quyền duyệt đúng đơn vị tự duyệt đề nghị mình lập | Điều kiện tách biệt trách nhiệm |
| Người chỉ được sửa ghi chú sửa luôn `approvedBy` hoặc trạng thái | Quyền theo thuộc tính và thao tác nghiệp vụ |
| Dịch vụ có quyền kỹ thuật rộng làm theo lệnh của người không đủ quyền | Nguồn thẩm quyền và phạm vi ủy quyền |

OWASP API1 phân biệt việc được dùng một chức năng với việc được tác động lên đối tượng được chỉ định. Mã đối tượng dạng UUID hoặc khó đoán không thay cho kiểm tra quyền theo đối tượng. [Nguồn: OWASP Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/).

OWASP API5 đề cập việc chủ thể truy cập chức năng ngoài thẩm quyền, bao gồm chức năng quản trị nằm ở những endpoint khác nhau. Tên URL không tự xác định ai được dùng chức năng. [Nguồn: OWASP Broken Function Level Authorization](https://github.com/OWASP/API-Security/blob/master/editions/2023/en/0xa5-broken-function-level-authorization.md).

### 2.2. Quyền hợp lệ có thể bị dùng sai ngữ cảnh

Không phải kịch bản nào cũng bắt đầu bằng đánh cắp tài khoản hoặc nâng quyền kỹ thuật. Một người có thể có nhiều nhiệm vụ thật, nhưng ứng dụng áp dụng quyền của nhiệm vụ này sang đối tượng của nhiệm vụ khác.

Các nhãn như “leo thang ngang” hoặc “leo thang dọc” hữu ích khi phân loại. Khi viết yêu cầu và kiểm thử, cần nêu chính xác hành động và điều kiện bị vượt, thay vì chỉ dựa vào nhãn.

## 3. Kịch bản chính: quyền duyệt sai đơn vị và tự duyệt

### 3.1. Quyền hợp lệ ban đầu

Nhân viên `E-12`, có định danh con người `PERSON-12`, làm việc trong tenant `T-01` với hai nhiệm vụ:

| Quyền | Hành động | Phạm vi | Hạn mức minh họa |
| --- | --- | --- | --- |
| `G-CREATE-X` | Lập và gửi đề nghị | Đơn vị X | Tối đa 20.000.000 VND mỗi đề nghị |
| `G-APPROVE-Y` | Duyệt đề nghị | Đơn vị Y | Tối đa 5.000.000 VND mỗi đề nghị |

Chính sách yêu cầu người duyệt khác con người đã lập. Quyền duyệt ở Y không áp dụng cho X. Người lập không được sửa trạng thái phê duyệt qua chức năng chỉnh bản nháp.

### 3.2. Giả định sai của một triển khai dễ bị lạm dụng

Giả sử endpoint duyệt chỉ kiểm tra:

```text
actor có bất kỳ vai trò APPROVER nào
AND số tiền không vượt hạn mức duyệt lớn nhất của actor
AND đề nghị đang SUBMITTED
```

Nó bỏ qua đơn vị của quyền duyệt và quan hệ người lập. Với tổng tiền 3.000.000 VND, các điều kiện này vẫn có thể đạt dù đề nghị thuộc X và do chính `E-12` tạo.

### 3.3. Chuỗi hành động trong môi trường minh họa

1. `E-12` lập đề nghị `PR-711` của đơn vị X với số tiền 3.000.000 VND.
2. Nhân viên gửi đề nghị, đưa nó từ `DRAFT` sang `SUBMITTED` hợp lệ.
3. Nhân viên gọi chức năng duyệt cho `PR-711` bằng chính phiên đã xác thực.
4. Máy chủ thấy vai trò duyệt từ nhiệm vụ Y, kiểm tra hạn mức chung và cho phép.
5. Đề nghị được gắn bằng chứng duyệt trái chính sách, có thể kích hoạt bước mua hoặc thanh toán tiếp theo.

Yêu cầu minh họa ở bước 3:

```http
POST /purchase-requests/PR-711/approve
Content-Type: application/json

{
  "expectedContentVersion": 4
}
```

Request không cần chứa SQL injection, token giả hay một trường đặc biệt. Nó có thể hợp lệ về kỹ thuật; kết quả phải bị chặn do thiếu quyền cho X và vi phạm không tự duyệt.

### 3.4. Mô tả kịch bản để đưa vào yêu cầu

| Thuộc tính | Nội dung |
| --- | --- |
| Mã | `PRIV-APPROVAL-001` |
| Actor | Nhân viên có nhiều nhiệm vụ hợp lệ trong cùng tenant |
| Tài sản | Tính hợp lệ của quyết định phê duyệt và tác dụng được mở khóa sau duyệt |
| Tiền điều kiện | Được lập ở X, được duyệt ở Y; có đề nghị X do mình lập |
| Điểm yếu | Kiểm tra role/hạn mức toàn cục; bỏ phạm vi của grant và quan hệ người lập |
| Kết quả bị cấm | Duyệt ngoài đơn vị được cấp hoặc tự duyệt |
| Oracle kiểm thử | Đề nghị vẫn `SUBMITTED`; không có quyết định duyệt thành công hoặc tác vụ thực thi mới |

Người duyệt hợp lệ khác, có quyền với X và đủ hạn mức, vẫn cần được phục vụ. Một biện pháp chặn mọi tài khoản có nhiều vai trò không thay cho mô hình quyền đúng.

## 4. Bất biến và biểu thức quyết định quyền

### 4.1. Phải có căn cứ cho đúng tổ hợp điều kiện

Với chính sách dựa trên các grant độc lập trong ví dụ:

```text
Tồn tại một grant g sao cho:
  g thuộc đúng tài khoản actor
  AND g đang có hiệu lực
  AND g cho phép APPROVE
  AND g.tenantId = request.tenantId
  AND g.unitId = request.unitId
  AND request.totalVnd <= g.limitVnd

Đồng thời:
  actor.personId != request.createdByPersonId
  AND request.state = SUBMITTED
  AND expectedContentVersion = request.contentVersion
```

Không lấy hành động từ grant này, đơn vị từ grant khác và hạn mức lớn nhất từ một grant thứ ba rồi ghép thành quyền mới. Nếu sản phẩm cho phép kết hợp quyền theo một cơ chế khác, phép kết hợp đó phải được định nghĩa rõ trong chính sách.

### 4.2. Không tự duyệt là điều kiện độc lập

Ngay cả khi `E-12` được cấp thêm quyền duyệt đúng đơn vị X, chính sách không tự duyệt vẫn phải chặn đề nghị của chính người đó.

Nếu mục tiêu là hai con người độc lập, so sánh hai tài khoản không đủ. Một người dùng tài khoản thường để lập rồi tài khoản nâng quyền để duyệt vẫn là tự duyệt theo mục tiêu đó. Cần định danh con người được quản lý đáng tin, đồng thời giữ cả tài khoản thao tác để truy vết.

### 4.3. Từ chối không được tạo tác dụng thành công

Khi yêu cầu bị chặn trước thay đổi:

- Không chuyển sang `APPROVED`.
- Không ghi người duyệt như một quyết định đã chấp nhận.
- Không phát sự kiện duyệt thành công hoặc tác vụ mua/thanh toán.
- Có thể ghi dấu vết lần thử bị từ chối qua cơ chế thích hợp.

Phản hồi lỗi không chứng minh an toàn nếu hệ thống đã đẩy một lệnh xuống worker trước khi kiểm tra. Quyết định quyền phải bảo vệ điểm tạo tác dụng, không chỉ câu trả lời cho người gọi.

## 5. Ví dụ Java: giữ các điều kiện trong cùng một grant

Đoạn mã minh họa bước quyết định, chưa thực hiện transaction, xác thực phiên hoặc ghi cơ sở dữ liệu. Các record được dựng từ nguồn đã xác minh; định danh và miền dữ liệu bắt buộc được giả định đã kiểm tra. Không bind trực tiếp JSON vào `Actor` hoặc `ApprovalGrant`.

```java
import java.time.Instant;
import java.util.List;
import java.util.UUID;

enum Permission { CREATE, APPROVE }
enum RequestState { DRAFT, SUBMITTED, APPROVED, CANCELLED }

record Actor(UUID accountId, UUID personId, UUID tenantId) {}

record ApprovalGrant(
        UUID id, UUID accountId, UUID tenantId, UUID unitId,
        Permission permission, long limitVnd,
        Instant validUntil, boolean enabled, long version) {}

record RequestView(
        UUID id, UUID tenantId, UUID unitId,
        UUID createdByPersonId, long totalVnd,
        long contentVersion, RequestState state) {}

record ApprovalEvidence(
        UUID requestId, UUID actorAccountId, UUID actorPersonId,
        UUID grantId, long grantVersion,
        long contentVersion, long amountVnd, Instant decidedAt) {}

final class ApprovalPolicy {
    static ApprovalEvidence decide(
            Actor actor,
            RequestView request,
            List<ApprovalGrant> grants,
            long expectedContentVersion,
            Instant now) {

        if (!actor.tenantId().equals(request.tenantId())) {
            throw new IllegalStateException("FORBIDDEN");
        }
        if (actor.personId().equals(request.createdByPersonId())) {
            throw new IllegalStateException("SELF_APPROVAL_FORBIDDEN");
        }
        if (request.state() != RequestState.SUBMITTED) {
            throw new IllegalStateException("INVALID_STATE");
        }
        if (request.contentVersion() != expectedContentVersion) {
            throw new IllegalStateException("CONTENT_CHANGED");
        }
        if (request.totalVnd() <= 0) {
            throw new IllegalStateException("INVALID_AMOUNT");
        }

        ApprovalGrant matched = grants.stream()
                .filter(g -> g.enabled()
                        && now.isBefore(g.validUntil())
                        && g.permission() == Permission.APPROVE
                        && g.accountId().equals(actor.accountId())
                        && g.tenantId().equals(request.tenantId())
                        && g.unitId().equals(request.unitId())
                        && request.totalVnd() <= g.limitVnd())
                .findFirst()
                .orElseThrow(() -> new IllegalStateException("FORBIDDEN"));

        return new ApprovalEvidence(
                request.id(), actor.accountId(), actor.personId(),
                matched.id(), matched.version(),
                request.contentVersion(), request.totalVnd(), now);
    }
}
```

Các điều kiện về hành động, tenant, đơn vị, tài khoản, thời hạn và hạn mức đều được xét trên **cùng một grant**. Không có bước gom mọi đơn vị vào một tập rồi dùng hạn mức lớn nhất của tài khoản như quyền chung.

Kiểm tra tự duyệt đứng độc lập nên thêm một grant đúng đơn vị vẫn không bỏ được điều kiện này. `now` phải đến từ nguồn thời gian máy chủ theo chính sách; không lấy timestamp tùy ý từ lệnh client.

`ApprovalEvidence` là kết quả nội bộ để lưu và truy vết, không phải chứng nhận mà bất kỳ client nào có thể tự gửi để mở bước tiếp theo. Việc chuyển qua ranh giới dịch vụ cần bảo vệ nguồn và phạm vi sử dụng.

Các thông báo lỗi trong đoạn mã là mã lý do nội bộ. Lớp API phải có chính sách phản hồi nhất quán, tránh lộ thông tin đối tượng ngoài phạm vi chỉ vì thứ tự kiểm tra khác nhau.

## 6. Đặt kiểm soát ở điểm thực thi và giữ điều kiện tới lúc ghi

### 6.1. Kiểm tra UI và gateway chỉ là một phần

Giao diện có thể ẩn nút duyệt khi actor không có quyền. Gateway có thể kiểm tra đã đăng nhập và có scope tổng quát. Service nghiệp vụ vẫn cần kiểm tra grant và đối tượng tại thao tác duyệt.

OWASP Authorization khuyến nghị từ chối mặc định và kiểm tra quyền ở mỗi yêu cầu. Với ví dụ này, điều đó có nghĩa kiểm tra lại phạm vi, quan hệ người lập và điều kiện hiện hành trước tác dụng. [Nguồn: OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html).

Mọi đường gây cùng quyết định cần được kiểm soát tương đương: API web, ứng dụng di động, endpoint nội bộ, batch và tác vụ vận hành. Không để một API “cập nhật chung” ghi `APPROVED` mà không chạy điều kiện duyệt.

### 6.2. Trạng thái và quyền có thể đổi giữa đọc và ghi

Luồng điều phối có thể là:

```text
BEGIN TRANSACTION
  1. Tải đối tượng theo tenant và mã; khóa hoặc giữ phiên bản cần thiết.
  2. Tải quyền và quan hệ từ nguồn đáng tin theo hợp đồng độ mới.
  3. Đánh giá ApprovalPolicy trên nội dung hiện hành.
  4. Ghi chuyển SUBMITTED → APPROVED có kiểm tra phiên bản.
  5. Lưu bằng chứng và outbox của quyết định thành công.
COMMIT
```

Các luồng sửa nội dung, đổi phân công, hủy và duyệt cần phối hợp cùng chiến lược nhất quán. Nếu cập nhật có điều kiện không tác động đúng một đối tượng mong đợi, không báo đã duyệt và không phát tác vụ thành công.

Transaction không tự làm mọi nguồn quyền nhất quán. Nếu quyền bị thu hồi đồng thời, cần chính sách hiệu lực rõ. Yêu cầu ngăn mọi quyết định chưa commit sau thu hồi cần cơ chế phối hợp như khóa/phiên bản nguồn quyền; một bản cache cũ không đáp ứng được điều kiện mạnh đó.

### 6.3. Giữ nội dung được duyệt khỏi bị thay thế

Sau khi duyệt, việc sửa tiền, sản phẩm, người hưởng hoặc đơn vị có thể làm bằng chứng không còn đúng nghĩa. Chính sách có thể cấm sửa trực tiếp hoặc yêu cầu vô hiệu hóa quyết định và duyệt lại.

Không sửa `createdByPersonId` để làm điều kiện không tự duyệt có vẻ đạt. Danh tính người lập được ghi từ ngữ cảnh tại thao tác tạo và cần giữ lịch sử đúng; chuyển người phụ trách không tự thay đổi ai đã lập nội dung.

Tương tự, không tăng hạn mức hoặc đổi grant bằng payload của chính lệnh duyệt. Quản trị quyền là một hành động khác, có thẩm quyền và bằng chứng riêng.

## 7. Những biến thể cần đưa vào mô hình lạm dụng

| Biến thể | Cách quy tắc có thể bị bỏ qua | Điều cần bảo vệ |
| --- | --- | --- |
| Đổi mã đối tượng | Dùng chức năng hợp lệ trên đề nghị ngoài phạm vi | Hành động và quan hệ với từng đối tượng |
| Gán thuộc tính ngoài quyền | Chức năng sửa ghi chú nhận thêm `state` hoặc `approvedBy` | Danh sách trường/lệnh được phép và thao tác miền |
| Tài khoản thứ hai | Cùng một người đóng cả vai lập và duyệt | Danh tính con người theo mục tiêu kiểm soát |
| Tự cấp vai trò | Quyền quản trị bị dùng để tạo quyền duyệt cho chính mình ngoài chính sách | Ai được cấp gì, cho ai và điều kiện áp dụng |
| Mượn chế độ đại diện | Hệ thống ghi khách là người lập thay vì nhân viên thực sự | Chuỗi actor, người được đại diện và người quyết định |
| Batch bỏ kiểm tra từng dòng | Một số dòng trái quyền đi cùng những dòng hợp lệ | Phạm vi và tách biệt trách nhiệm cho từng đối tượng |
| Service có quyền rộng | Service làm theo lệnh chưa được cấp phép của caller | Danh tính service và nguồn thẩm quyền của từng ý định |
| Ngoại lệ tùy ý | `force=true` hoặc `skipApproval` được tin trực tiếp | Năng lực ngoại lệ riêng, phạm vi và điều kiện rõ ràng |

### 7.1. Không gộp vai trò của caller với quyền kỹ thuật của service

Một worker có thể có quyền ghi nhiều đề nghị vì nó phục vụ nhiều người. Điều đó không cho phép mọi caller yêu cầu worker duyệt thay mình.

Worker cần nhận một ý định đã được tiếp nhận qua kiểm soát đúng, giữ định danh người khởi tạo và quyết định áp dụng, đồng thời xác thực nguồn thông điệp. Một trường `approved=true` hoặc `actorId` trong message không tự chứng minh thẩm quyền.

Khi hành động là thực thi một quyết định đã duyệt, worker phải kiểm tra quyết định đúng đối tượng, nội dung và bước quy trình. Không dùng quyết định của đề nghị A để mở lệnh cho đề nghị B.

### 7.2. Không đồng nhất quản trị hệ thống với miễn trừ nghiệp vụ

Một vai trò quản trị có thể được phép cấp quyền hoặc hỗ trợ vận hành, nhưng chính sách không tự duyệt vẫn có thể áp dụng cho mọi con người. Nếu có ngoại lệ hợp lệ, cần mô hình hành động ngoại lệ, căn cứ, hạn mức và kiểm tra sau đó.

Một nhánh “nếu admin thì cho phép tất cả” làm mất ý nghĩa những điều kiện đã viết bên dưới và khiến kiểm thử phạm vi thường không bao phủ được đường mạnh nhất.

## 8. Vòng đời quyền và gửi lại yêu cầu

### 8.1. Quyền tại thời điểm gọi phải đáp ứng chính sách hiện hành

Chữ ký token đúng không tự chứng minh mọi grant vẫn còn hiệu lực. Thay đơn vị, hết hạn quyền tạm thời, đình chỉ nhân viên hoặc giảm hạn mức cần được phản ánh theo độ trễ thu hồi đã cam kết.

Nếu thiếu dữ liệu để chứng minh được phép, từ chối hoặc trì hoãn theo hợp đồng; không biến lỗi tải quyền thành mặc định cho phép. Cache quyền cần phạm vi và thời hạn thích hợp, không dùng chung theo tên role rồi trộn tenant hoặc đơn vị.

### 8.2. Idempotency không phải một quyền truy cập

Gửi lại cùng lệnh duyệt cần không tạo thêm quyết định hoặc tác vụ. Khóa API phải gắn chủ thể, thao tác và nội dung; khóa nghiệp vụ và chuyển trạng thái bảo vệ cả khi caller dùng khóa khác.

Đọc lại kết quả đã lưu vẫn cần kiểm tra quyền xem đối tượng theo chính sách. Biết khóa idempotency hoặc mã quyết định không cho phép người khác xem hoặc tái sử dụng quyết định đó cho hành động mới.

### 8.3. Quyết định bền vững khác với phiên cá nhân

Một quyết định đã commit có thể được dịch vụ thực thi sau khi người duyệt hết phiên. Cần định nghĩa liệu quyền bị thu hồi về sau có vô hiệu hóa quyết định chưa thực thi hay không, thay vì để worker tự suy đoán.

Worker dùng danh tính dịch vụ và chính sách hiệu lực quyết định; không mượn token cũ của người dùng. Dù chọn chính sách nào, việc thu hồi không được cho actor tạo thêm lệnh mới bằng bằng chứng cũ ngoài phạm vi.

## 9. Bằng chứng để giải thích ai được phép làm gì

Một quyết định duyệt nên truy được:

```text
actorAccountId, actorPersonId
người được đại diện và người khởi tạo thực tế nếu có
tenantId, unitId, requestId
action, outcome, reasonCode
grantId, grantVersion hoặc phiên bản chính sách
contentVersion, amountVnd
stateBefore, stateAfter
operationId, correlationId, decidedAt
```

Những dữ liệu này giúp phân biệt “có vai trò duyệt” với “đã dùng grant nào để duyệt đề nghị này”. Chỉ ghi `user=E-12, action=approve` không giải thích được vì sao phạm vi được chấp nhận.

Bằng chứng thành công cần nhất quán với thay đổi đã commit. Dấu vết từ chối cần ghi đúng kết quả và tồn tại theo cơ chế phù hợp khi transaction nghiệp vụ rollback.

Không ghi token phiên, bí mật hoặc dữ liệu nhạy cảm không cần thiết. Quyền sửa/xóa lịch sử cần được kiểm soát riêng; người có quyền duyệt không mặc nhiên được sửa bằng chứng của chính mình.

Tín hiệu điều tra có thể gồm nhiều lần vượt đơn vị, tự duyệt bằng nhiều tài khoản, chuyển phân công ngay trước duyệt, cặp người lập–duyệt tập trung bất thường hoặc gia tăng sử dụng ngoại lệ. Các tín hiệu đó cần ngữ cảnh; chúng không tự chứng minh mọi hoạt động liên quan là sai.

## 10. Kiểm thử scenario bằng ma trận quyền và chuỗi thao tác

### 10.1. Ma trận tối thiểu cho kịch bản chính

| Actor và đối tượng | Kết quả mong đợi |
| --- | --- |
| `E-12` chỉ được duyệt Y, duyệt đề nghị X của người khác | Từ chối do sai phạm vi |
| `E-12` chỉ được duyệt Y, duyệt đề nghị X do mình lập | Từ chối; không có bằng chứng/tác vụ thành công |
| `E-12` được cấp thêm quyền duyệt X, duyệt đề nghị X của mình | Vẫn từ chối do tự duyệt |
| Tài khoản khác của `PERSON-12` duyệt đề nghị của cùng người | Vẫn chặn theo chính sách hai con người độc lập |
| Người khác có grant X đúng hành động, còn hiệu lực và đủ hạn mức | Cho phép nếu trạng thái và phiên bản cũng đạt |
| Actor có quyền tạo X và grant duyệt Y hạn mức cao | Không ghép thành quyền duyệt X |
| Actor có grant duyệt X hạn mức thấp và grant Y hạn mức cao | Không mượn hạn mức Y để duyệt X vượt hạn mức X |
| Actor tenant khác có cùng tên role và mã đơn vị | Không tác động được đề nghị của `T-01` |
| Người duyệt hợp lệ gửi phiên bản nội dung cũ | Không chấp nhận nội dung chưa được xem |
| Đề nghị đã hủy hoặc chưa gửi | Không chuyển thẳng sang `APPROVED` |
| API sửa bản nháp nhận thêm `approvedBy`, `state`, `createdByPersonId` | Không sửa được trường ngoài quyền để vượt quy tắc |
| Batch có cả dòng hợp lệ và dòng tự duyệt | Xử lý đúng hợp đồng từng phần/toàn bộ, không bỏ kiểm tra từng dòng |
| Grant hết hạn hoặc bị vô hiệu hóa | Lệnh mới không dùng được quyền theo hợp đồng hiệu lực |
| Nguồn quyền lỗi hoặc thiếu thuộc tính quan trọng | Không cho phép mặc định |
| Retry, hai endpoint hoặc hai worker cùng duyệt một đề nghị | Không tạo hai quyết định mới hoặc tác dụng trùng |
| Caller gửi message tự nhận đã được duyệt | Không được service có quyền rộng thực hiện khi thiếu nguồn thẩm quyền hợp lệ |

Với mọi kết quả từ chối trước thay đổi, kiểm tra cả trạng thái, người duyệt, lịch sử, outbox và tác dụng xuống hệ thống sau. Không chỉ assert mã phản hồi.

### 10.2. Kiểm thử các thay đổi đơn lẻ trong cùng ngữ cảnh

Bắt đầu từ một trường hợp được phép, rồi lần lượt đổi đúng một yếu tố: tenant, đơn vị, chủ thể, quan hệ người lập, hạn mức, trạng thái hoặc phiên bản. Mỗi biến thể cần một kết quả dự kiến rõ.

Cũng cần trường hợp nhiều grant để phát hiện phép ghép quyền sai. Chỉ kiểm thử mỗi tài khoản có đúng một role thường không bộc lộ lỗi của tài khoản đa nhiệm.

### 10.3. Chọn tầng kiểm thử phù hợp

Kiểm thử đơn vị xác minh hàm policy bằng dữ liệu actor/grant/đối tượng rõ ràng và thời gian cố định. Kiểm tra ngay trước, đúng thời điểm và sau hạn quyền theo quy ước đã chọn.

Kiểm thử API xác minh danh tính không lấy từ JSON, tenant được kiểm tra, trường hệ thống không bị gán và mọi đường gọi đều thực thi chính sách.

Kiểm thử tích hợp cơ sở dữ liệu xác minh khóa, phiên bản, rollback và ghi bằng chứng nguyên tử. Khi kiểm tra duyệt cạnh tranh hoặc sửa nội dung cạnh tranh, cần transaction độc lập và điểm đồng bộ có chủ đích.

Kiểm thử worker/batch và phục hồi xác minh việc truyền nguồn thẩm quyền, hiệu lực quyết định, retry và trạng thái sau lỗi. Các tình huống trong bài là đặc tả kiểm thử, chưa phải kết quả thực thi của một hệ thống cụ thể.

## 11. Ưu tiên và xử lý khi phát hiện lạm dụng quyền

Mức ảnh hưởng phụ thuộc quyền sai mở được điều gì: chỉ đọc thêm một dữ liệu, thay đổi quyết định, cấp thêm năng lực hay phát tác dụng khó đảo ngược. Cần xem cả tác động trực tiếp và những bước phía sau tin vào quyết định sai đó.

Khi xác định một đường lách, giới hạn hoặc sửa đường thực thi bị ảnh hưởng, rồi rà những đường gây cùng hành động. Vá một nút UI hoặc một URL không đủ nếu endpoint batch hay công cụ nội bộ vẫn ghi trực tiếp.

Đối soát những quyết định liên quan theo grant, phạm vi, người lập–duyệt và phiên bản tại thời điểm đó. Đừng kết luận mọi quyết định của tài khoản nhiều vai trò đều sai; cũng đừng chỉ sửa trạng thái rồi xóa bằng chứng về tác dụng đã phát.

Nếu cần thu hồi quyền hoặc đình chỉ actor, xử lý phiên, cache và công việc đang chờ theo chính sách. Các tác dụng đã ra ngoài có thể cần quy trình khắc phục riêng; thay role không tự đảo ngược một lệnh mua hay thanh toán.

Quyền quản trị trực tiếp database hoặc lịch sử có thể nằm ngoài ranh giới service layer. Cần xác định và quản lý các năng lực đó thay vì cho rằng một hàm policy đủ chống người có thể sửa tùy ý dữ liệu và bằng chứng.

Sau khắc phục, giữ kiểm thử hồi quy gắn với điều kiện cụ thể đã bị bỏ qua: phạm vi grant, không tự duyệt hoặc nguồn thẩm quyền. Số request bị chặn không phải tiêu chí duy nhất; người duyệt hợp lệ vẫn phải hoàn thành được công việc đúng.

## 12. Mẫu viết privilege abuse scenario

```text
Actor và quyền hợp lệ ban đầu:
  Tài khoản, con người, role/grant và phạm vi nào thực sự được cấp?

Tài sản/đối tượng:
  Dữ liệu, quyết định, tiền hoặc quyền nào sẽ bị ảnh hưởng?

Kết quả bị cấm:
  Hành động nào trên đối tượng nào là ngoài thẩm quyền?

Tiền điều kiện và chuỗi hành động:
  Actor tận dụng chức năng, grant, chế độ đại diện hoặc đường gọi nào?

Giả định sai:
  Hệ thống nhầm đăng nhập với được phép, gom quyền sai phạm vi,
  bỏ quan hệ đối tượng hay bỏ điều kiện nghiệp vụ ở đâu?

Quyết định đúng:
  Căn cứ grant, tenant, đối tượng, hạn mức, trạng thái,
  phiên bản và tách biệt trách nhiệm phải đồng thời thỏa gì?

Điểm thực thi và tính nhất quán:
  UI, API, batch, service và worker được bảo vệ như thế nào?
  Điều kiện được giữ tới lúc commit và tạo tác dụng ra sao?

Bằng chứng và kiểm thử:
  Grant nào giải thích được quyết định?
  Trường hợp được phép và bị cấm được chứng minh bằng dữ liệu nào?
```

Một kịch bản lạm dụng quyền được mô tả tốt làm rõ **quyền được cấp, ngữ cảnh áp dụng và điều kiện cấm vượt qua**. Khi những yếu tố đó được thực thi cùng nhau ở thao tác nghiệp vụ, một vai trò hợp lệ không còn dễ bị dùng làm căn cứ cho hành động sai đối tượng hoặc sai trách nhiệm.
