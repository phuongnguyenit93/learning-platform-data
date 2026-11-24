# Delegation audit — Dấu vết kiểm toán cho hành động được ủy quyền

## 1. Audit phải giải thích được ai đã dùng quyền của ai

Trong chương **Delegation**, audit là việc lưu bằng chứng có cấu trúc về quá trình cấp, thay đổi, sử dụng và thu hồi quyền ủy quyền. Mục tiêu không chỉ là biết “có một request thành công”, mà là giải thích một tác động nghiệp vụ đã được cho phép và thực hiện như thế nào.

Ví dụ, quản lý A ủy quyền cho B duyệt hoàn tiền tại cửa hàng S1. B duyệt một yêu cầu; worker sau đó gửi lệnh cho bên thanh toán. Nếu log chỉ ghi “A hoàn tiền thành công”, hệ thống đã làm mất cả danh tính người thực sự thao tác lẫn sự khác nhau giữa duyệt và chuyển tiền.

Một dấu vết có ích cần trả lời:

- Ai thực sự thực hiện hành động, có service nào làm trung gian?
- Người đó dựa trên grant nào, phiên bản nào và nguồn thẩm quyền nào?
- Họ được phép thao tác trên đối tượng, số tiền và nội dung nào?
- Chính sách nào được dùng và kết quả kiểm tra là gì?
- Quyết định mới được tính là cho phép, đã commit hay đã tạo tác dụng phụ bên ngoài?
- Grant có bị thay đổi, hết hạn hoặc thu hồi trước ranh giới quyết định không?
- Có retry, sự kiện lặp, thiếu sự kiện hoặc dấu hiệu sửa dấu vết không?

Audit hỗ trợ điều tra và phát hiện sai lệch. Nó không thay thế phân quyền, state machine, transaction hoặc kiểm tra bất biến nghiệp vụ.

## 2. Những sự kiện nào cần được ghi?

### 2.1. Vòng đời quyền ủy quyền

| Nhóm sự kiện | Thông tin cần giải thích |
|---|---|
| Đề nghị và cấp grant | Ai đề nghị, ai được phép cấp, cấp cho ai, phạm vi nào |
| Kích hoạt hoặc chấp thuận grant | Điều kiện nào đã thỏa, phiên bản nào có hiệu lực |
| Sửa phạm vi | Trước/sau khác nhau thế nào, ai cho phép mở rộng hoặc thu hẹp |
| Đình chỉ và khôi phục | Lý do, người ra quyết định, thời điểm hiệu lực |
| Thu hồi | Ai yêu cầu, khi nào thu hồi có hiệu lực, phiên bản quyền sau thay đổi |
| Hết hạn | Hạn đã chốt và thời điểm hệ thống ghi nhận việc hết hạn |
| Ủy quyền tiếp | Quan hệ grant cha/con, nguồn gốc và điều kiện chuyển giao |
| Thay đổi quyền nguồn | Grant nào có thể bị ảnh hưởng và chính sách xử lý |

Không ghi “đã thu hồi” chỉ vì nhận được yêu cầu thu hồi. Nếu quy trình còn chờ xác nhận hoặc đồng bộ, phải phân biệt yêu cầu và trạng thái có hiệu lực.

Tương tự, một job chạy trễ lúc 10:05 ghi nhận grant hết hạn từ 10:00 không được làm 10:05 trở thành thời điểm kết thúc quyền. Hạn hiệu lực và thời điểm quan sát là hai dữ liệu khác nhau.

### 2.2. Sử dụng và kết quả nghiệp vụ

Tên sự kiện cần phản ánh đúng điều đã được chứng minh:

| Sự kiện minh họa | Ý nghĩa |
|---|---|
| `DELEGATED_ACTION_DENIED` | Một lần thử bị từ chối; chưa khẳng định có tác động nghiệp vụ |
| `DELEGATED_APPROVAL_COMMITTED` | Quyết định duyệt đã được ghi bền vững vào trạng thái nghiệp vụ |
| `EXECUTION_COMMAND_COMMITTED` | Lệnh thực thi bất biến đã được tiếp nhận trong transaction |
| `EXECUTION_SUBMITTED` | Có bằng chứng đã gửi lệnh đến bên xử lý |
| `EXECUTION_CONFIRMED` | Kết quả bên ngoài đã được xác minh theo hợp đồng |
| `EXECUTION_OUTCOME_UNKNOWN` | Chưa đủ bằng chứng kết luận kết quả |
| `IDEMPOTENT_RESULT_RETURNED` | Trả lại kết quả cũ, không thực hiện một ý định mới |

Đây là bộ tên minh họa của ứng dụng, không phải chuẩn giao thức bắt buộc.

Không dùng một sự kiện `SUCCESS` chung cho tất cả các giai đoạn. Một kiểm tra quyền trả allow chưa chứng minh transaction đã commit; một lệnh đã gửi chưa chứng minh tiền đã hoàn thành công.

## 3. Lưu đúng các danh tính và đường quyền

### 3.1. Không làm mất actor

Các trường có thể gồm:

| Trường | Ngữ nghĩa cần được định nghĩa rõ |
|---|---|
| `actorPrincipalId` | Chủ thể đã xác thực thực sự thực hiện thao tác nghiệp vụ |
| `delegatorPrincipalId` | Chủ thể cấp grant trực tiếp được dùng |
| `sourceAuthorityOwnerId` | Chủ thể cung cấp thẩm quyền gốc nếu có chuỗi |
| `executingService` | Service thực thi hoặc ghi nhận sự kiện |
| `initiatingActorId` | Người khởi tạo lệnh, nếu tác vụ chạy bất đồng bộ |
| `grantPath` | Đường grant và phiên bản từ nguồn đến actor |

Với A → B → C:

~~~text
Actor thực hiện: C
Người cấp grant trực tiếp cho C: B
Chủ thể nguồn gốc: A
Đường grant: grant A->B, rồi grant B->C
~~~

Một service account gửi lệnh không tự thay thế danh tính C trong lịch sử nghiệp vụ. Ngược lại, không được ghi service đang chạy là C nếu nó chỉ đại diện cho một lệnh C đã khởi tạo.

RFC 8693 phân biệt delegation với impersonation và mô tả claim actor khi trao đổi token. Audit ứng dụng cần quy định cách ánh xạ ngữ cảnh đã xác thực vào các trường của mình; không tự suy ra mọi trường từ một claim duy nhất. [RFC 8693](https://www.rfc-editor.org/rfc/rfc8693.html)

### 3.2. Tách dữ liệu đã xác minh khỏi dữ liệu tự khai

Không lấy các trường sau từ body rồi ghi như sự thật:

~~~json
{
  "actorPrincipalId": "director-a",
  "delegatorPrincipalId": "director-b",
  "decision": "ALLOW",
  "approvedAmount": "100000000",
  "policyVersion": "trusted-policy"
}
~~~

Actor đến từ ngữ cảnh xác thực; grant và nguồn quyền đến từ dữ liệu được kiểm tra; số tiền và đối tượng đến từ snapshot nghiệp vụ.

Nếu request cố dùng grant của người khác, có thể ghi một tham chiếu được khai báo để điều tra, nhưng phải phân biệt với grant đã xác minh. Không tự gán hành động cho chủ grant bị nhắm tới.

Nếu xác thực chưa thành công, không bịa một actor đã được chứng minh. Sự kiện xác thực thất bại và sự kiện một người đã xác thực bị từ chối ủy quyền có ý nghĩa khác nhau.

### 3.3. Correlation ID không phải bằng chứng danh tính

Request ID, trace ID và thông tin client gửi có ích để nối sự kiện. Chúng không chứng minh người gọi là ai hoặc ai đã cấp quyền.

Giới hạn kích thước, định dạng và nguồn của các giá trị này. Nếu giữ ID do client cung cấp, phân biệt nó với ID server tạo; không để người gọi giả correlation rồi làm audit trông như hành động của một phiên khác.

## 4. Giữ bằng chứng quyết định tại thời điểm sử dụng

### 4.1. Không tái dựng quá khứ từ cấu hình hiện tại

Giả sử B đã duyệt lúc 09:10 bằng grant phiên bản 3. Đến 09:30, grant được thu hẹp còn phiên bản 4.

Nếu điều tra bằng cách lấy grant hiện tại rồi áp vào hành động 09:10, hệ thống có thể kết luận sai rằng B đã vượt phạm vi.

Cần giữ hoặc tham chiếu tới bằng chứng bất biến của:

- Grant và phiên bản đã dùng, bao gồm các grant cha có liên quan.
- Quyền nguồn và phiên bản hoặc snapshot có thể giải thích.
- Phạm vi hiệu lực đã được tính: action, tenant, đơn vị, tiền tệ, trần và thời gian.
- Chính sách, quy tắc tách biệt trách nhiệm và điều kiện áp dụng.
- Nội dung đối tượng, số tiền và phiên bản mà quyết định dựa vào.
- Trạng thái và thời điểm tại ranh giới quyết định.
- Cơ chế kiểm tra hiệu lực quyền, bao gồm giới hạn tính mới nếu có.

Không phải lúc nào cũng phải sao chép mọi dữ liệu vào từng event. Có thể dùng tham chiếu đến snapshot bất biến được bảo vệ và có thời gian lưu phù hợp.

Một tham chiếu trỏ tới bản ghi sẽ bị sửa đè hoặc xóa sớm không đủ để giải thích quá khứ.

### 4.2. Ghi cả phạm vi được cấp và phạm vi thực dùng

Grant có thể bao phủ nhiều cửa hàng, nhưng hành động cụ thể chỉ liên quan S1. Cần biết cả grant cho phép gì và lần này đã dùng phần nào.

Với hoàn tiền, snapshot có thể gồm:

~~~text
request ID và contentVersion
giao dịch gốc và cửa hàng phía server
số tiền, tiền tệ, đích hoàn theo quan hệ hợp lệ
action thực hiện
grant ID/version và đường nguồn
policyVersion
envelope hạn mức và tham chiếu bản ghi giữ tiền nếu có
~~~

Không lưu chỉ một chuỗi “scope hợp lệ”. Điều tra cần dữ liệu đủ để kiểm tra vì sao hợp lệ.

### 4.3. Lý do ổn định, thông điệp có thể thay đổi

Dùng mã lý do như:

~~~text
DELEGATION_EXPIRED
DELEGATION_REVOKED
ACTION_OUT_OF_SCOPE
RESOURCE_OUT_OF_SCOPE
SOURCE_AUTHORITY_INVALID
SELF_APPROVAL_FORBIDDEN
CONTENT_VERSION_MISMATCH
~~~

Mã phục vụ truy vấn và phát hiện. Thông điệp hiển thị có thể được dịch hoặc thay câu chữ mà không làm mất khả năng phân loại.

Chi tiết nội bộ không nhất thiết được trả hết cho client. Audit phải có quyền đọc phù hợp; nó không phải kênh công khai để dò grant hoặc tài nguyên của tenant khác.

## 5. Một audit event có cấu trúc

### 5.1. Ví dụ sự kiện đã commit

~~~json
{
  "eventId": "event-example-001",
  "schemaVersion": 1,
  "eventType": "DELEGATED_APPROVAL_COMMITTED",
  "tenantId": "merchant-example",
  "decisionId": "decision-example",
  "operationId": "operation-example",
  "occurredAt": "2026-11-22T09:10:00Z",
  "recordedAt": "2026-11-22T09:10:00Z",
  "actorPrincipalId": "person-b",
  "delegatorPrincipalId": "person-a",
  "sourceAuthorityOwnerId": "person-a",
  "executingService": "refund-service",
  "authority": {
    "delegationId": "delegation-example",
    "delegationVersion": 3,
    "grantPath": [
      {"grantId": "delegation-example", "version": 3}
    ],
    "sourceSnapshotRef": "authority-snapshot-example",
    "effectiveScopeRef": "scope-snapshot-example",
    "policyVersion": "refund-delegation-v2"
  },
  "target": {
    "type": "REFUND_REQUEST",
    "id": "refund-example",
    "contentVersion": 4,
    "snapshotRef": "refund-snapshot-example",
    "amount": "1500000",
    "currency": "VND"
  },
  "action": "REFUND_APPROVE",
  "outcome": "COMMITTED",
  "reasonCode": "POLICY_SATISFIED",
  "requestId": "request-server-example"
}
~~~

Các giá trị là dữ liệu giả định. Event khẳng định quyết định duyệt đã commit, không khẳng định tiền đã chuyển.

`schemaVersion` là phiên bản cấu trúc event. Nó khác phiên bản grant, phiên bản nội dung đối tượng và phiên bản chính sách.

### 5.2. ID theo mục đích

| ID | Dùng để làm gì? |
|---|---|
| `eventId` | Định danh duy nhất một sự kiện; không thay đổi khi phát lại |
| `decisionId` | Nối bằng chứng kiểm tra quyền với kết quả liên quan |
| `operationId` | Định danh ý định hoặc thao tác nghiệp vụ được tiếp nhận |
| `delegationId` và version | Xác định grant đã dùng |
| Target ID và contentVersion | Xác định nội dung đã được duyệt |
| `requestId` | Nối log của một lần gọi |
| Command hoặc provider operation ID | Nối lệnh thực thi và kết quả bên ngoài |

Một operation có thể có nhiều request retry và nhiều event theo các giai đoạn. Không dùng request ID làm định danh duy nhất của quyền lợi hoặc khoản chi.

ID vẫn có thể là dữ liệu nhạy cảm trong bối cảnh cụ thể. Không coi việc thay tên người bằng ID là đã loại bỏ mọi yêu cầu bảo vệ.

## 6. Ghi audit cùng transaction nghiệp vụ

### 6.1. Tránh khoảng trống giữa thay đổi và ghi dấu vết

Hai cách triển khai dễ sai:

~~~text
A. Ghi log "duyệt thành công", rồi commit nghiệp vụ.
   -> Commit thất bại nhưng log vẫn trông như đã thành công.

B. Commit nghiệp vụ, rồi gọi hệ thống audit qua mạng.
   -> Tiến trình chết giữa hai bước, giao dịch có thật nhưng thiếu audit.
~~~

Với thao tác nhạy cảm, một phương án là lưu thay đổi nghiệp vụ và audit event trong cùng transaction nội bộ. Cùng transaction đó ghi outbox để chuyển event sang kho tra cứu tập trung.

~~~text
BEGIN
  - Kiểm tra và điều phối grant, quyền nguồn và đối tượng.
  - Kiểm tra scope, trạng thái và phiên bản nội dung.
  - Kiểm tra idempotency và các bất biến nghiệp vụ.
  - Ghi quyết định duyệt hoặc lệnh nghiệp vụ.
  - Ghi audit event cho thay đổi này.
  - Ghi outbox tham chiếu cùng eventId.
  - Lưu kết quả idempotency.
COMMIT

Sau commit:
  - Publisher chuyển event từ outbox.
  - Kho audit tập trung nhận và xử lý lặp an toàn.
~~~

Một event có tên “committed” có thể được chuẩn bị trước commit, nhưng nó chỉ trở thành bằng chứng đã commit khi bản ghi đó thực sự nằm trong transaction thành công. Một log stdout in ra trước commit không có cùng mức bảo đảm.

### 6.2. Audit sự kiện bị từ chối không được biến mất theo rollback

Nếu ghi sự kiện từ chối trong transaction rồi ném exception làm rollback toàn bộ, sự kiện đó có thể mất theo.

Cần một đường ghi bền vững cho lần thử bị từ chối: transaction độc lập thích hợp, kênh security event có xác nhận hoặc cơ chế khác được thiết kế rõ. Đường đó không được vô tình commit thay đổi nghiệp vụ đang bị từ chối.

Phân biệt:

~~~text
DELEGATED_ACTION_DENIED:
    Có lần thử, không được phép thực hiện.

TRANSACTION_ABORTED:
    Thao tác chưa được commit theo thông tin hệ thống biết.

DELEGATED_APPROVAL_COMMITTED:
    Có thay đổi nghiệp vụ đã commit.
~~~

Không đánh dấu committed khi chỉ mới vượt qua kiểm tra quyền. Nếu trạng thái commit chưa rõ do mất kết nối, cần tra cứu/đối soát theo operation ID trước khi kết luận.

### 6.3. Hành vi khi hệ thống audit gặp lỗi

| Lỗi | Hành vi trong thiết kế minh họa |
|---|---|
| Không ghi được audit bắt buộc trong transaction nội bộ | Không commit thao tác nhạy cảm đó |
| Kho tập trung tạm không nhận nhưng audit và outbox cục bộ đã bền vững | Có thể tiếp tục trong giới hạn backlog đã thiết kế |
| Backlog gần vượt khả năng lưu an toàn | Cảnh báo và áp dụng chính sách tiếp nhận phù hợp |
| Không ghi được sự kiện từ chối | Hành động vẫn bị từ chối; kích hoạt cơ chế xử lý mất khả năng quan sát |
| Chỉ công cụ tìm kiếm audit lỗi | Không suy ra dữ liệu nguồn đã mất; kiểm tra kho và tiến độ chuyển |

Đây là lựa chọn kiến trúc cần được quy định theo độ nhạy cảm. Không để một lệnh ghi audit lỗi bị nuốt im lặng trong khi giao dịch vẫn được báo có bằng chứng đầy đủ.

Cũng không buộc mọi thao tác phải chờ một hệ thống tra cứu ở xa nếu đã có bằng chứng cục bộ và đường chuyển bền vững phù hợp.

## 7. Minh họa Java: dựng sự kiện từ quyết định đã xác minh

Đoạn mã Java 17+ chỉ minh họa việc ánh xạ dữ liệu nội bộ sang event có cấu trúc. Nó không thực hiện kiểm tra quyền hoặc transaction.

~~~java
import java.time.Instant;
import java.util.List;
import java.util.UUID;

final class DelegationAuditFactory {
    record GrantRef(String id, long version) {}

    record Identities(
            String actorPrincipalId,
            String delegatorPrincipalId,
            String sourceAuthorityOwnerId,
            String executingService) {}

    record AuthorityEvidence(
            List<GrantRef> grantPath,
            String sourceSnapshotRef,
            String effectiveScopeRef,
            String policyVersion) {

        AuthorityEvidence {
            grantPath = List.copyOf(grantPath);
        }
    }

    record Target(
            String resourceId,
            long contentVersion,
            String snapshotRef) {}

    // Chỉ được tạo từ kết quả đánh giá đã xác minh ở server.
    record CheckedApproval(
            String tenantId,
            UUID decisionId,
            Instant decisionAt,
            Identities identities,
            AuthorityEvidence authority,
            Target target) {}

    record AuditEvent(
            UUID eventId,
            int schemaVersion,
            String eventType,
            String tenantId,
            UUID decisionId,
            UUID operationId,
            Instant occurredAt,
            Instant recordedAt,
            Identities identities,
            AuthorityEvidence authority,
            Target target) {}

    static AuditEvent prepareCommitEvent(
            UUID eventId,
            UUID operationId,
            CheckedApproval approval,
            Instant recordedAt) {

        return new AuditEvent(
                eventId,
                1,
                "DELEGATED_APPROVAL_COMMITTED",
                approval.tenantId(),
                approval.decisionId(),
                operationId,
                approval.decisionAt(),
                recordedAt,
                approval.identities(),
                approval.authority(),
                approval.target());
    }
}
~~~

Các điều kiện sử dụng cần giữ:

1. `CheckedApproval` đến từ tầng đánh giá quyền và snapshot, không bind trực tiếp từ JSON client.
2. Kiểm tra trường bắt buộc, nguồn danh tính và phạm vi tenant nằm trong đường tạo dữ liệu nội bộ.
3. `eventId` được tạo khi ghi sự kiện mới, sau đó lưu và dùng lại khi phát lại; không tạo ID khác mỗi lần publisher retry.
4. Event này chỉ có ý nghĩa committed khi được lưu cùng thay đổi nghiệp vụ trong transaction thành công.
5. Serializer có schema rõ ràng; không serialize nguyên token, request body hoặc đối tượng security context.
6. `List.copyOf` tránh việc bên gọi sửa danh sách đường grant sau khi dựng bằng chứng; nó không tạo xác thực mật mã.

Mô hình record giúp giữ cấu trúc tường minh, nhưng bản thân một đối tượng Java không chứng minh các dữ liệu bên trong là đúng. Độ tin cậy đến từ nguồn dữ liệu, kiểm tra và cơ chế lưu trữ.

## 8. Retry, phát lại và thứ tự sự kiện

### 8.1. Một event được chuyển nhiều lần vẫn là một event

Publisher có thể gửi event thành công rồi mất xác nhận. Nó gửi lại cùng `eventId`; phía nhận phải xử lý lặp an toàn bằng khóa duy nhất phù hợp, chẳng hạn theo nguồn phát và event ID.

Nếu cùng ID xuất hiện với payload khác, cần coi đó là bất thường về tính toàn vẹn hoặc lỗi triển khai, không âm thầm ghi đè.

Không cộng tiền hoặc số lần sử dụng grant dựa trên mọi message nhận được. Một event duyệt, một event tạo lệnh và một event xác nhận có thể cùng liên quan một khoản tiền nhưng không phải ba khoản.

Sổ ngân sách và giao dịch nghiệp vụ có thẩm quyền riêng. Audit tập trung hỗ trợ đối chiếu, không nên trở thành bộ đếm cấp quyền chỉ vì tiện truy vấn log.

### 8.2. Retry của request không phải sử dụng quyền mới

Nếu client retry cùng ý định đã commit:

- Trả kết quả cũ theo hợp đồng idempotency.
- Không thêm một phê duyệt độc lập.
- Không giữ thêm ngân sách hoặc tạo lệnh chi mới.
- Nếu ghi sự kiện trả kết quả cũ, liên kết với operation ban đầu.
- Vẫn kiểm tra quyền đọc kết quả hiện tại.

Nếu grant đã bị thu hồi sau giao dịch cũ, việc được xem lại kết quả không có nghĩa được phép thực hiện lại hành động. Quyền đọc và quyền tạo tác động mới cần được đánh giá theo chính sách tương ứng.

### 8.3. Thời gian và thứ tự cần nhiều bằng chứng

Phân biệt:

| Mốc | Ý nghĩa |
|---|---|
| `occurredAt` | Mốc nghiệp vụ được event mô tả, chẳng hạn lúc ra quyết định |
| `recordedAt` | Lúc nguồn tạo hoặc ghi bản ghi |
| `ingestedAt` | Lúc kho tập trung nhận được event |
| Version hoặc thứ tự theo đối tượng | Liên hệ giữa các thay đổi của cùng grant hoặc yêu cầu |

Các mốc thời gian không tự tạo thứ tự toàn cục chính xác giữa các máy. Thời gian trong một event cũng không nhất thiết là thời điểm commit vật lý.

Dùng version, quan hệ nhân quả và ID thao tác để bổ sung. Nếu hệ thống dùng sequence, phải hiểu cách cấp số: khoảng trống có thể do rollback hoặc cơ chế cấp số, không mặc định chứng minh đã bị xóa log.

Event đến muộn hoặc đến sai thứ tự ở kho tập trung không tự chứng minh hệ thống nghiệp vụ xử lý sai.

## 9. Điều tra việc sử dụng quanh thời điểm thu hồi

### 9.1. Ví dụ timeline

Giả sử chính sách yêu cầu đường ủy quyền còn hợp lệ ở cổng tạo lệnh thực thi:

| Mốc tại nguồn | Sự kiện |
|---|---|
| 09:00 | A cấp grant cho B |
| 09:10 | B duyệt yêu cầu bản 4; approval và audit commit |
| 09:11 | Grant bị thu hồi có hiệu lực |
| 09:12 | Worker kiểm tra trước khi tạo lệnh thực thi, bị chặn vì thu hồi |
| 09:13 | Kho tập trung mới nhận event duyệt của 09:10 do chuyển trễ |

Không kết luận “B duyệt sau thu hồi” chỉ vì event duyệt xuất hiện trong kho lúc 09:13.

Cũng không kết luận “tiền đã được hoàn” chỉ vì có event approval committed. Cần tìm lệnh thực thi và kết quả được xác nhận.

### 9.2. Race giữa thu hồi và sử dụng

Nếu thu hồi và tiếp nhận thao tác mới cùng lúc, cần một ranh giới quyết định nhất quán.

Khi chúng dùng cùng dữ liệu và giao thức khóa, có thể xác định thao tác nào được cam kết trước trong phạm vi đó. PostgreSQL cung cấp khóa hàng phục vụ điều phối, nhưng phải áp dụng đúng vào các bản ghi tham gia bất biến. [PostgreSQL Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)

Khóa bản ghi hoàn tiền không tự khóa quyền trong IAM bên ngoài. Audit nên ghi bằng chứng nguồn và phiên bản đã kiểm tra cùng mức bảo đảm của cơ chế sử dụng, thay vì khẳng định luôn thấy quyền mới nhất.

Nếu lệnh đã được tiếp nhận hợp lệ trước thu hồi và chính sách cho hoàn thành lệnh đã cam kết, việc thực thi sau đó không tự là vi phạm. Nếu chính sách yêu cầu kiểm tra ngay trước gửi ra ngoài, phải có bằng chứng của bước đó.

### 9.3. Các bước điều tra một thao tác

1. Xác định operation ID và đối tượng đúng tenant.
2. Tìm actor, service và đường grant đã dùng.
3. Lấy snapshot của grant, quyền nguồn và chính sách đúng phiên bản.
4. Đối chiếu nội dung, số tiền, trạng thái và điều kiện scope tại quyết định.
5. Kiểm tra quan hệ với người lập và tập phê duyệt độc lập.
6. Kiểm tra ngân sách và phần nghĩa vụ đã ghi nhận.
7. Nối tới lệnh thực thi, lần gửi và kết quả bên ngoài.
8. Đối chiếu thu hồi, hết hạn, thay đổi và retry.
9. Phân biệt dữ liệu đã có với phần còn thiếu hoặc chưa đủ tin cậy.

Một bộ audit thiếu event không cho phép khẳng định chắc chắn rằng hành động chưa xảy ra. Cần đối chiếu với dữ liệu nghiệp vụ, outbox và nguồn kết quả.

## 10. Bảo vệ audit khỏi sửa, xóa và giả mạo

### 10.1. Phân tách quyền ghi, đọc và quản trị

Người được ủy quyền thực hiện nghiệp vụ không mặc nhiên được sửa dấu vết của mình. Các quyền sau cần được tách theo nhu cầu:

- Ghi event từ các service được xác thực.
- Đọc lịch sử trong phạm vi tenant hoặc hồ sơ được phép.
- Điều tra liên tenant theo quyền kiểm toán riêng.
- Xuất dữ liệu, thay thời gian lưu hoặc quản trị kho.
- Xóa theo quy trình vòng đời được kiểm soát.

Một tài khoản chỉ được insert theo giao diện ứng dụng chưa tạo ra kho bất biến trước quản trị viên database. Mức bảo vệ thực tế phải được mô tả đúng.

OWASP khuyến nghị bảo vệ log khỏi truy cập và sửa đổi không được phép, đồng thời kiểm tra khả năng ghi log và vận hành đường thu thập. [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

### 10.2. Hash không tự chứng minh nguồn gốc

Hash payload có ích để so sánh hai bản event. Nếu kẻ xấu sửa được cả payload và hash, nó không tự ngăn được giả mạo.

Một chuỗi hash cũng có giới hạn:

- Cần quy tắc serialization và phiên bản schema ổn định.
- Kẻ có thể viết lại toàn chuỗi có thể tính lại hash.
- Xóa phần đuôi có thể khó nhận ra nếu không có mốc đối chiếu độc lập.
- Chuỗi đúng không chứng minh ứng dụng đã ghi đủ mọi hành động ngay từ đầu.

Theo mô hình đe dọa, có thể cần chữ ký, khóa được quản lý tách biệt, mốc kiểm chứng bên ngoài, bản sao độc lập hoặc kho lưu có cơ chế chống sửa phù hợp.

Không gọi một log “không thể chối bỏ” chỉ vì nó có SHA-256 hoặc nằm trên một database riêng.

### 10.3. Sửa sai bằng sự kiện bổ sung

Nếu ghi sai metadata hoặc phát hiện bằng chứng cũ không chính xác, không âm thầm sửa lịch sử để làm nó trông như chưa có lỗi.

Có thể thêm sự kiện hiệu chỉnh tham chiếu event cũ, nêu nguồn, lý do và người có quyền hiệu chỉnh. Giữ được dữ liệu ban đầu và diễn giải đã được thay đổi.

Không tạo một event xác nhận thành công chỉ để lấp một khoảng trống chưa biết kết quả.

## 11. Dữ liệu nhạy cảm và log injection

### 11.1. Ghi đủ bằng chứng, không sao chép mọi dữ liệu

Tránh ghi trực tiếp:

- Access token, refresh token, khóa API, cookie phiên hoặc OTP.
- Toàn bộ request body chứa thông tin thanh toán.
- Bí mật dùng ký hoặc mã hóa.
- Dữ liệu cá nhân không liên quan đến quyết định.
- Toàn bộ idempotency key nếu một tham chiếu nội bộ đủ dùng.

OWASP lưu ý loại bỏ hoặc xử lý phù hợp các dữ liệu nhạy cảm trong log và bảo vệ đường ghi trước dữ liệu không đáng tin. [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)

Một fingerprint của dữ liệu ít khả năng biến đổi vẫn có thể bị dò nếu miền giá trị nhỏ. Không coi hash của email hoặc số điện thoại là tự động ẩn danh an toàn.

Nếu cần bảo vệ tham chiếu bằng kỹ thuật mật mã, phải chọn cơ chế và quản lý khóa theo mục tiêu truy vết, quyền đọc và mô hình đe dọa của hệ thống.

### 11.2. Không để comment giả thành một event

Người dùng có thể nhập comment chứa xuống dòng, ký tự điều khiển hoặc chuỗi giống một log hệ thống.

Dùng serializer có cấu trúc, giới hạn độ dài và xử lý ký tự theo kênh xuất. Không nối chuỗi không tin cậy vào dòng log để người đọc hiểu nhầm thành một sự kiện thứ hai.

Khi dựng giao diện xem audit, xử lý an toàn nội dung hiển thị. Khi xuất bảng dữ liệu, xét cả nguy cơ nội dung người dùng bị diễn giải thành công thức bởi công cụ mở file.

Không ghi exception bằng cách dump toàn bộ security context. Chi tiết phục vụ debug phải đi qua cùng quy tắc bảo vệ dữ liệu.

### 11.3. Retention phải giữ được liên kết bằng chứng

Chọn thời gian lưu theo chính sách đã được tổ chức xác định, mục tiêu điều tra và yêu cầu áp dụng. Không có một số ngày chung phù hợp cho mọi hệ thống.

Cần bảo đảm một event còn được lưu không trỏ đến snapshot đã bị xóa ngoài dự kiến. Thiết kế cả backup, archive, khôi phục và các bản xuất; không chỉ bảng đang hoạt động.

Mọi thao tác đọc nhạy cảm, xuất hàng loạt hoặc thay chính sách lưu audit cũng có thể cần dấu vết riêng.

## 12. Phát hiện lạm dụng và kiểm tra tính đầy đủ

### 12.1. Các tín hiệu nên xem xét

| Dấu hiệu | Cần đối chiếu |
|---|---|
| Một actor thử nhiều grant không thuộc mình | Danh tính đã xác minh, ID bị khai và nguồn request |
| Nhiều lần vượt cửa hàng hoặc tenant | Scope thực, target phía server và mã từ chối |
| Sử dụng grant đã thu hồi | Mốc quyết định, hiệu lực thu hồi và giới hạn đồng bộ |
| Nhiều grant ngắn hạn cùng nguồn | Envelope, ngân sách và hành vi hủy/cấp lại |
| A lập yêu cầu rồi B dùng grant của A duyệt | Quan hệ người lập và chính sách tách biệt |
| Hai delegate cùng nguồn được tính hai vị trí độc lập | Provenance và tập bằng chứng thực sự được chọn |
| Tăng tiền hoặc đổi người hưởng sau duyệt | ContentVersion và snapshot trước cổng thực thi |
| Có lệnh thực thi nhưng thiếu bằng chứng duyệt bắt buộc | Sổ nghiệp vụ, audit nguồn và outbox |
| Event cùng ID nhưng payload khác | Nguồn phát, schema và dấu hiệu sửa dữ liệu |
| Backlog kéo dài hoặc thiếu một producer | Tiến độ gửi, watermark và số lượng đối chiếu |

Tín hiệu không tự là kết luận gian lận. Một lần gửi sau thu hồi có thể là retry trả kết quả cũ, và một event đến muộn có thể do đường chuyển.

### 12.2. Đối soát với dữ liệu có thẩm quyền

Một số kiểm tra nền:

~~~text
Mỗi approval đã commit có bằng chứng audit tương ứng.
Mỗi lệnh thực thi có operation ID và snapshot nguồn.
Mỗi event trong outbox có trạng thái chuyển có thể truy vết.
Event đã chuyển có thể được tìm theo cùng eventId ở nơi nhận.
Không cộng event lặp thành giao dịch mới.
Tổng nghĩa vụ được đối soát theo sổ nghiệp vụ, không theo mọi dòng log.
~~~

Không so sánh số event tổng một cách máy móc: một operation có thể sinh nhiều loại event, một request bị từ chối không có bản ghi giao dịch và một publisher có thể phát lại.

Với event nghiệp vụ bắt buộc, tránh sampling làm mất bằng chứng từng thao tác. Với từ chối khối lượng lớn, nếu dùng tổng hợp hoặc giới hạn lưu chi tiết để bảo vệ tài nguyên, phải ghi rõ giới hạn quan sát và không tuyên bố có đủ từng lần thử.

## 13. Kiểm thử tình huống tấn công và lỗi vận hành

Bảng này là kịch bản cho một triển khai, không phải kết quả đã chạy kiểm thử hệ thống cụ thể.

| Tình huống | Điều cần xác minh |
|---|---|
| Client tự gửi actor, delegator hoặc outcome | Audit dùng dữ liệu đã xác minh, phân biệt dữ liệu tự khai |
| Dùng grant của tenant khác | Không gán hành động sai chủ thể hoặc làm lộ dữ liệu tenant khác |
| Chuỗi A → B → C qua service | Giữ được actor thực, delegator trực tiếp, nguồn gốc và đường grant |
| Scope hoặc quyền nguồn đổi sau hành động | Tái dựng được quyết định từ đúng snapshot |
| Nghiệp vụ rollback sau khi chuẩn bị event | Không xuất hiện event committed có thẩm quyền cho thay đổi chưa commit |
| Audit bắt buộc ghi lỗi | Không commit thao tác nhạy cảm theo chính sách đã chọn |
| Bị từ chối rồi transaction rollback | Dấu vết lần thử được ghi theo đường độc lập đã thiết kế |
| Tiến trình chết ngay sau commit | Audit và outbox vẫn có thể được phục hồi |
| Publisher mất xác nhận rồi gửi lại | Cùng eventId, không nhân số giao dịch |
| Cùng eventId nhưng payload khác | Không ghi đè im lặng |
| Kho nhận sự kiện sai thứ tự hoặc chậm | Không suy luận thu hồi/sử dụng chỉ từ thứ tự đến |
| Duyệt và thu hồi đồng thời | Dấu vết đủ giải thích ranh giới quyết định và phiên bản đã dùng |
| Timeout bên thanh toán | Ghi kết quả chưa rõ, không bịa thành công hoặc thất bại cuối |
| Một người dùng hai tài khoản | Có định danh chủ thể để kiểm tra tính độc lập |
| Comment chứa dòng log giả hoặc nội dung thực thi | Không tạo event giả hoặc thực thi khi hiển thị/xuất |
| Token hoặc bí mật xuất hiện trong lỗi | Không bị sao chép vào audit chung |
| Người dùng đọc audit ngoài tenant | Bị chặn theo quyền đối tượng |
| Admin sửa hoặc xóa dấu vết | Cơ chế bảo vệ và phát hiện đúng mô hình đe dọa |
| Archive hoặc snapshot hết thời gian lưu | Liên kết bằng chứng và chính sách xóa được kiểm tra |
| Khôi phục từ backup | Đối soát được operation, audit và tiến độ chuyển |

Kiểm thử nên quan sát dữ liệu sau commit và sau phục hồi, không chỉ xác nhận một hàm logger đã được gọi. Một mock xác nhận “append được gọi một lần” chưa chứng minh audit tồn tại khi tiến trình chết hoặc transaction rollback.

## 14. Các bất biến của delegation audit

Một hệ thống audit hữu ích cần giữ:

- Không đánh tráo actor với người cung cấp quyền hoặc service thực thi.
- Mỗi quyết định có thể gắn với đúng đường grant, chính sách và nội dung.
- Sự kiện phân biệt lần thử, quyết định, commit, gửi và xác nhận kết quả.
- Thao tác nhạy cảm đã commit không mất dấu vết bắt buộc trong khoảng lỗi được thiết kế.
- Retry và phát lại không tạo thêm hành động nghiệp vụ trong báo cáo.
- Thứ tự đến và timestamp không bị dùng như bằng chứng vượt quá khả năng của chúng.
- Audit được bảo vệ về quyền truy cập, tính toàn vẹn, khả năng lưu và dữ liệu nhạy cảm.
- Điều tra nêu rõ phần đã biết, phần chưa rõ và nguồn đối chiếu.

Dấu vết kiểm toán tốt cho phép nối từ người đã hành động, qua quyền được ủy quyền, tới thay đổi nghiệp vụ thực sự xảy ra. Chính mối liên hệ đó giúp phát hiện việc vượt scope, lách phê duyệt hoặc tạo tác dụng phụ trùng.
