# Delegation scope — Phạm vi ủy quyền trong bảo mật logic nghiệp vụ

## 1. Ủy quyền phải trả lời được “được làm gì, trên cái gì?”

Trong chương **Delegation**, phạm vi ủy quyền là tập các thao tác mà một chủ thể được phép thực hiện thay chủ thể khác, trên những đối tượng và trong những điều kiện đã xác định.

Ví dụ, quản lý A cho nhân viên B duyệt hoàn tiền của cửa hàng S1 trong ca làm việc, mỗi yêu cầu tối đa 2 triệu đồng. Điều này không có nghĩa B được duyệt hoàn tiền của mọi cửa hàng, sửa giá đơn hàng, đổi nơi nhận tiền hoặc tiếp tục ủy quyền cho C.

Một bản ghi “B được làm thay A” quá rộng để làm ranh giới bảo mật. Hệ thống cần giữ được:

- Chủ thể đang thao tác và chủ thể cung cấp thẩm quyền vẫn được phân biệt.
- Người nhận chỉ dùng phần quyền đã được phép chuyển giao.
- Phạm vi không tự mở rộng khi đổi tenant, đối tượng, kênh gọi hoặc số lượng grant.
- Hết hạn, thu hồi và thay đổi quyền nguồn có tác động được quy định.
- Ủy quyền không bỏ qua phê duyệt, state machine, hạn mức tổng hoặc cơ chế chống trùng.

Bài học tập trung vào cách mô hình hóa và thực thi những điều kiện này.

## 2. Phân biệt danh tính, quyền nguồn và bản ủy quyền

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| Người ủy quyền — delegator | Chủ thể cung cấp một phần thẩm quyền có thể chuyển giao | Quản lý A |
| Người nhận — delegate | Chủ thể được chỉ định sử dụng quyền đó | Nhân viên B |
| Người đang thao tác — actor | Danh tính đã xác thực của lần gọi thực tế | B hoặc service được phép đại diện |
| Quyền nguồn — source authority | Căn cứ cho phép A cấp phần quyền này | Quyền duyệt hoàn tiền trong merchant M1 |
| Bản ủy quyền — delegation grant | Quyết định cụ thể, có phạm vi và vòng đời | B duyệt tại S1, trần 2 triệu, trong một ca |
| Đối tượng nghiệp vụ | Tài nguyên thực sự bị đọc hoặc thay đổi | Yêu cầu hoàn tiền và giao dịch gốc |

### 2.1. Quyền thực hiện không tự bao gồm quyền chuyển giao

Một người có thể được duyệt hoàn tiền nhưng không được cấp quyền duyệt cho người khác. Vì vậy, lúc tạo grant phải kiểm tra cả:

~~~text
Có thẩm quyền nguồn phù hợp
AND phần thẩm quyền đó được phép ủy quyền
AND được cấp cho đúng loại người nhận
AND phạm vi đề nghị không vượt phạm vi được chuyển giao
~~~

Không triển khai “ai gọi được endpoint nghiệp vụ thì gọi được endpoint ủy quyền tương ứng”.

### 2.2. Người nhận không nhất thiết đã có sẵn quyền nghiệp vụ đó

B có thể chưa có quyền duyệt hoàn tiền trực tiếp; mục đích của ủy quyền chính là cho B một đường thẩm quyền có giới hạn.

Vì vậy, không mặc định tính quyền bằng cách giao tất cả quyền nghiệp vụ trực tiếp của A với tất cả quyền nghiệp vụ trực tiếp của B. Cách đó có thể làm ủy quyền không hoạt động.

Thay vào đó, kiểm tra B có đủ **điều kiện nhận và sử dụng** quyền: tài khoản hợp lệ, quan hệ với tenant, trạng thái nhân sự, yêu cầu xác thực và các ràng buộc của tổ chức. Thẩm quyền nghiệp vụ cho thao tác đang xét đến từ grant và quyền nguồn hợp lệ.

Nếu B có quyền trực tiếp khác, hệ thống có thể đánh giá đường quyền trực tiếp đó riêng. Không ghép một phần quyền trực tiếp với một phần grant để tạo ra quyền mạnh hơn mà không có chính sách cho phép.

### 2.3. Không che mất người thực sự hành động

Không đổi danh tính B thành A rồi chỉ ghi “A đã duyệt”. Giao dịch cần thể hiện B hành động theo grant nào và thay mặt ai.

RFC 8693 phân biệt ngữ nghĩa delegation với impersonation và mô tả claim actor trong ngữ cảnh token exchange. Việc dùng giao thức này vẫn cần một chính sách nghiệp vụ xác định quyền được chuyển giao. [RFC 8693](https://www.rfc-editor.org/rfc/rfc8693.html)

## 3. Các chiều của phạm vi ủy quyền

Một scope an toàn thường là một điều kiện nhiều chiều, không phải một chuỗi role đơn lẻ.

| Chiều phạm vi | Ví dụ cần làm rõ |
|---|---|
| Thao tác | Đọc yêu cầu, duyệt, từ chối, thực thi, hủy, xuất dữ liệu |
| Loại đối tượng | Yêu cầu hoàn tiền, hóa đơn, đơn mua hàng |
| Tenant và đơn vị | Merchant M1, cửa hàng S1 |
| Tập đối tượng | Các ID cụ thể hoặc điều kiện chọn có ngữ nghĩa xác định |
| Giá trị tiền | Tiền tệ, trần từng lệnh, giá trị dùng so sánh |
| Hạn mức cộng dồn | Tổng nghĩa vụ qua một envelope hoặc chu kỳ |
| Thời gian | Bắt đầu, kết thúc loại trừ, chu kỳ ngân sách |
| Trạng thái | Chỉ duyệt yêu cầu đang chờ, không sửa giao dịch đã hoàn tất |
| Trường dữ liệu | Có được thay người hưởng, tài khoản nhận hoặc số tiền không? |
| Kênh và dịch vụ nhận | Chỉ sử dụng tại API/service được xác định |
| Điều kiện người nhận | Tài khoản hoạt động, đúng quan hệ tổ chức, xác thực phù hợp |
| Khả năng ủy quyền tiếp | Có được cấp grant con, sâu tối đa bao nhiêu? |
| Ràng buộc trách nhiệm | Không tự duyệt, không tạo hai chữ ký độc lập từ cùng nguồn bị cấm |

Quyền đọc cũng cần phạm vi. Cho phép xem đủ dữ liệu để duyệt một yêu cầu không mặc nhiên cho phép tìm kiếm, tải toàn bộ khách hàng hoặc xuất toàn bộ giao dịch của tenant.

### 3.1. Phân tách action theo ý nghĩa nghiệp vụ

Các action sau không tương đương:

~~~text
REFUND_READ
REFUND_APPROVE
REFUND_EXECUTE
REFUND_CHANGE_DESTINATION
DELEGATION_CREATE
~~~

Nếu B được `REFUND_APPROVE`, server không tự suy ra B được đổi tài khoản nhận tiền hoặc thực thi mọi lệnh hoàn.

Nếu một action nghiệp vụ cần đọc dữ liệu để thực hiện, chính sách có thể cho đọc phần cần thiết trong đúng ngữ cảnh. Không dùng sự phụ thuộc đó để cấp một quyền đọc không giới hạn.

### 3.2. Không để các điều kiện bị mất quan hệ

Giả sử A cấp:

~~~text
Quy tắc 1: đọc tại S1.
Quy tắc 2: duyệt tại S2.
~~~

Nếu hệ thống gom thành:

~~~text
actions = {READ, APPROVE}
stores = {S1, S2}
~~~

rồi cho phép mọi tổ hợp, B sẽ có thêm quyền duyệt tại S1 ngoài ý định ban đầu.

Hãy giữ quan hệ bằng từng rule hoàn chỉnh:

~~~json
{
  "rules": [
    {"action": "REFUND_READ", "storeIds": ["s1"]},
    {"action": "REFUND_APPROVE", "storeIds": ["s2"]}
  ]
}
~~~

Cùng nguyên tắc đó áp dụng cho tiền tệ, trần tiền, loại đối tượng và tenant. Không lấy action từ grant này, phạm vi từ grant khác và trần cao nhất từ grant thứ ba.

## 4. Ví dụ xuyên suốt: duyệt hoàn tiền trong một cửa hàng

Giả sử:

- A có quyền nguồn duyệt hoàn tiền trong merchant M1, tối đa 20 triệu mỗi yêu cầu.
- Chính sách cho phép A chuyển giao một phần quyền này.
- B đủ điều kiện nhận ủy quyền trong M1.
- A cấp cho B quyền duyệt tại cửa hàng S1, mỗi yêu cầu tối đa 2 triệu.
- Khoảng hiệu lực từ `2026-11-22T01:00:00Z` đến trước `2026-11-22T09:00:00Z`.
- Envelope ủy quyền có ngân sách 5 triệu trong khoảng đã chốt, dùng chung cho các grant cùng envelope.
- Không cho ủy quyền tiếp, đổi nơi nhận tiền hoặc tự duyệt.

Một bản ghi phía server có thể mang ý nghĩa:

~~~json
{
  "delegationId": "delegation-example",
  "version": 1,
  "sourceAuthorityId": "authority-a-example",
  "envelopeId": "envelope-example",
  "delegatorPrincipalId": "person-a",
  "delegatePrincipalId": "person-b",
  "tenantId": "merchant-m1",
  "rules": [
    {
      "action": "REFUND_APPROVE",
      "storeIds": ["store-s1"],
      "currency": "VND",
      "maxAmount": "2000000",
      "allowedRefundState": "PENDING_APPROVAL"
    }
  ],
  "validFrom": "2026-11-22T01:00:00Z",
  "validUntil": "2026-11-22T09:00:00Z",
  "allowSubdelegation": false,
  "status": "ACTIVE"
}
~~~

Các giá trị là giả định để minh họa. `envelopeId` trỏ đến sổ hạn mức có biên thời gian và ngân sách riêng; không tự tạo ngân sách mới khi thay token hoặc cấp thêm grant.

| Thao tác của B | Kết quả xét phạm vi |
|---|---|
| Duyệt 1,5 triệu tại S1, đúng thời gian và dữ liệu | Có thể phù hợp; vẫn cần kiểm tra nguồn quyền, ngân sách và bất biến |
| Duyệt 3 triệu tại S1 | Vượt trần từng yêu cầu |
| Duyệt 1 triệu tại S2 | Sai phạm vi cửa hàng |
| Duyệt yêu cầu thuộc merchant khác | Sai tenant |
| Đổi tài khoản nhận trước khi duyệt | Không được cấp action này |
| Cấp quyền tương tự cho C | Không được ủy quyền tiếp |
| Duyệt đúng mốc 09:00Z | Ngoài khoảng hiệu lực |
| Duyệt yêu cầu do chính B lập | Vi phạm tách biệt trách nhiệm |
| Dùng hai grant cùng envelope để nhận ngân sách hai lần | Không được phép |

Việc grant nhỏ hơn quyền nguồn ở trần tiền chưa chứng minh toàn bộ scope hợp lệ. Vẫn phải kiểm tra mọi chiều phạm vi.

## 5. Tính phạm vi hiệu lực theo một đường thẩm quyền hoàn chỉnh

### 5.1. Kiểm tra lúc cấp và lúc sử dụng

Lúc cấp grant:

~~~text
Phạm vi được cấp
    nằm trong phần quyền nguồn được phép chuyển giao
    AND phù hợp chính sách cấp ủy quyền
    AND người nhận đủ điều kiện
~~~

Lúc sử dụng, với mô hình ủy quyền phụ thuộc quyền nguồn đang hiệu lực trong bài:

~~~text
Yêu cầu hợp lệ theo ủy quyền khi:
    đúng actor được chỉ định
    AND grant còn hiệu lực
    AND có đường quyền nguồn hợp lệ
    AND yêu cầu thuộc toàn bộ điều kiện của đường đó
    AND người nhận vẫn đủ điều kiện
    AND không vi phạm ràng buộc nghiệp vụ hoặc trách nhiệm
~~~

Phạm vi thực dùng không vượt phần đã cấp ban đầu, kể cả khi A được tăng quyền sau đó. A được nâng trần từ 20 triệu lên 50 triệu không tự làm grant 2 triệu của B thành 50 triệu.

Nếu A bị thu hẹp quyền nguồn, phần B được sử dụng cũng phải bị chặn hoặc thu hẹp theo chính sách này. Đây là lựa chọn **ủy quyền phụ thuộc quyền nguồn**. Nếu một hệ thống cho phép một loại cấp quyền độc lập tồn tại sau khi quyền nguồn thay đổi, phải thiết kế và phê duyệt loại đó riêng.

OWASP nhấn mạnh việc kiểm tra quyền trên từng yêu cầu và đúng tài nguyên. Grant có hiệu lực không thay thế kiểm tra đối tượng hiện tại. [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)

### 5.2. Nhiều grant là nhiều đường được đánh giá

Một cách biểu diễn:

~~~text
Cho phép nếu tồn tại ít nhất một đường thẩm quyền
    bao phủ trọn vẹn yêu cầu
    và mọi ràng buộc toàn cục đều thỏa.
~~~

Không ghép các mảnh không đủ điều kiện từ nhiều đường thành một đường mới.

Ví dụ:

~~~text
Grant G1: S1, tối đa 2 triệu.
Grant G2: S2, tối đa 8 triệu.

Không suy ra: S1, tối đa 8 triệu.
~~~

Nếu nghiệp vụ hỗ trợ cơ chế cộng gộp hoặc kết hợp grant, phải định nghĩa rõ phép kết hợp, sổ hạn mức và bằng chứng. Không coi việc có nhiều grant là lý do mặc định để cộng thẩm quyền.

### 5.3. Các ràng buộc toàn cục vẫn áp dụng

Ngay cả khi có một grant phù hợp, vẫn cần giữ:

- Tổng tiền đã hoàn và đang giữ không vượt số tiền đủ điều kiện hoàn.
- Ngân sách envelope không bị vượt do nhiều người cùng sử dụng.
- Không tự duyệt hoặc lách số người độc lập.
- Không thực hiện sai trạng thái hoặc bỏ qua bước phê duyệt bắt buộc.
- Không tạo tác dụng phụ trùng khi retry.

Scope giới hạn phần quyền được chuyển giao. Nó không tạo ngoại lệ cho mọi quy tắc của hệ thống.

## 6. Đối tượng trong scope: snapshot hay điều kiện động?

### 6.1. Hai cách chọn tài nguyên

**Danh sách chốt lúc cấp:** grant chỉ bao gồm các request ID cụ thể. Tài nguyên mới không tự được thêm.

**Điều kiện động:** grant áp dụng cho các yêu cầu đang thuộc cửa hàng S1 và đáp ứng các điều kiện khác. Tài nguyên mới có thể được bao phủ nếu đó là ngữ nghĩa đã được cấp.

Không chọn một cách mà mô tả như cách còn lại. “Tất cả yêu cầu hiện có” khác “mọi yêu cầu hiện tại và tương lai tại S1”.

### 6.2. Thay đổi quan hệ đối tượng phải được kiểm tra lại

Nếu yêu cầu được chuyển từ S1 sang S2, một grant chỉ áp dụng S1 không tự tiếp tục có hiệu lực cho thao tác mới.

Cần đọc tenant, cửa hàng, trạng thái và quan hệ giao dịch gốc từ dữ liệu phía server. Không tin một `storeId` trong body để kết luận đối tượng thuộc scope.

Nếu người dùng được phép đổi thuộc tính dùng trong điều kiện scope, cần ngăn họ chuyển đối tượng tạm thời vào phạm vi để duyệt rồi chuyển ra. Có thể cần kiểm soát việc chuyển đơn vị, chốt snapshot và duyệt lại khi quan hệ quan trọng thay đổi.

Tên hoặc tiền tố chuỗi không phải quan hệ sở hữu đáng tin. ID giống nhau ở hai tenant cũng không được làm dữ liệu bị tra cứu nhầm phạm vi.

### 6.3. Trường bị thiếu không có nghĩa là không giới hạn

Quy định rõ:

- Danh sách rỗng là không có quyền hay yêu cầu không hợp lệ?
- Không có trần tiền là lỗi hay một loại quyền đặc biệt?
- Ký hiệu wildcard có được hỗ trợ không?
- Không có thời điểm kết thúc có được cấp không?

Trong ví dụ, scope bắt buộc thiếu hoặc không giải thích được sẽ bị từ chối. Không dùng default rộng như “mọi tenant”, “mọi action” hoặc “không hết hạn” chỉ để tránh lỗi null.

## 7. Ví dụ Java: kiểm tra các điều kiện scope cục bộ

Đoạn mã Java 17+ sau chỉ minh họa kiểm tra các chiều của grant trực tiếp trong ví dụ. Dữ liệu được tải và xác minh ở server, không phải đối tượng bind nguyên trạng từ request.

Tiền trong ví dụ là số nguyên VND theo hợp đồng. Các phép tổng hợp hạn mức thực tế còn cần kiểm tra tràn số và cập nhật nguyên tử.

~~~java
import java.time.Instant;
import java.util.Set;

final class DelegatedRefundScope {
    enum Action { REFUND_APPROVE }
    enum RefundState { PENDING_APPROVAL, APPROVED, COMPLETED }

    record Actor(String principalId, String tenantId) {}

    record GrantView(
            String delegatorId,
            String delegateId,
            String tenantId,
            Set<Action> actions,
            Set<String> storeIds,
            long maxAmountVnd,
            Instant validFrom,
            Instant validUntil,
            boolean active) {

        GrantView {
            actions = Set.copyOf(actions);
            storeIds = Set.copyOf(storeIds);
            if (maxAmountVnd <= 0
                    || !validFrom.isBefore(validUntil)) {
                throw new IllegalArgumentException("Invalid delegation scope");
            }
        }
    }

    record RefundView(
            String tenantId,
            String storeId,
            String makerPrincipalId,
            String currency,
            long amountVnd,
            RefundState state) {}

    static boolean matchesLocalScope(
            Actor actor,
            GrantView grant,
            RefundView refund,
            Instant decisionAt) {

        return grant.active()
                && actor.principalId().equals(grant.delegateId())
                && actor.tenantId().equals(grant.tenantId())
                && refund.tenantId().equals(grant.tenantId())
                && grant.actions().contains(Action.REFUND_APPROVE)
                && grant.storeIds().contains(refund.storeId())
                && "VND".equals(refund.currency())
                && refund.amountVnd() > 0
                && refund.amountVnd() <= grant.maxAmountVnd()
                && !decisionAt.isBefore(grant.validFrom())
                && decisionAt.isBefore(grant.validUntil())
                && refund.state() == RefundState.PENDING_APPROVAL
                && !actor.principalId().equals(refund.makerPrincipalId())
                && !grant.delegatorId().equals(refund.makerPrincipalId());
    }
}
~~~

Ví dụ chọn quy tắc không cho cả người nhận lẫn người cung cấp quyền nguồn duyệt thay yêu cầu do chính họ lập. Nhờ đó, A không thể lập yêu cầu rồi nhờ B dùng chính quyền ủy quyền của A để vượt điều kiện không tự duyệt.

Các kiểm tra **chưa có** trong hàm:

- Quyền nguồn hiện tại và việc A được phép chuyển giao.
- Trạng thái tài khoản, điều kiện nhận quyền và quan hệ đại diện.
- Tổng ngân sách envelope, chuỗi grant cha nếu có.
- Quan hệ với giao dịch thanh toán gốc và đích hoàn tiền hợp lệ.
- Phiên bản nội dung, số phê duyệt độc lập và cơ chế chống trùng.
- Khóa, transaction và tính mới của dữ liệu quyền.

Tên `matchesLocalScope` phản ánh giới hạn đó. Kết quả true không phải quyết định thực thi hoàn tiền cuối cùng.

Các trường định danh phải được chuẩn hóa và kiểm tra không thiếu ở tầng tạo dữ liệu nội bộ. Không tạo grant hợp lệ chỉ bằng cách cho client chọn `active=true`.

## 8. Ủy quyền tiếp không được mở rộng phạm vi

### 8.1. Quyền con phải bị giới hạn bởi đường cha

Nếu hệ thống hỗ trợ A → B → C, cần kiểm tra B có quyền ủy quyền tiếp. Có quyền sử dụng grant không mặc nhiên có quyền tạo grant con.

Các điều kiện điển hình:

~~~text
action con nằm trong action được cha cho phép chuyển tiếp
scope đối tượng con nằm trong scope cha
trần tiền con không vượt trần còn áp dụng của cha
thời gian con không vượt khoảng hiệu lực của cha
dịch vụ nhận và điều kiện sử dụng con không rộng hơn cha
grant cha và quyền nguồn còn hiệu lực
giới hạn độ sâu và chống vòng lặp được thỏa
~~~

Với cùng đại lượng tiền và cùng đơn vị, một trần hiệu lực có thể bị giới hạn bởi trần nhỏ nhất trên đường. Điều đó không đủ cho các chiều scope khác: tập tài nguyên và điều kiện phải được giao theo đúng ngữ nghĩa.

### 8.2. Không nhân ngân sách bằng grant con

Giả sử envelope gốc có 5 triệu. B cấp hai grant con, mỗi grant ghi “5 triệu”. Nếu mỗi grant con có bộ đếm riêng không liên hệ gốc, tổng sử dụng có thể thành 10 triệu.

Một thiết kế cần giữ ngân sách dùng chung hoặc cấp phát các phần có sổ kiểm soát:

- Nếu dùng chung, mỗi lần giữ tiền phải kiểm tra cả hạn mức con và hạn mức gốc.
- Nếu chia phần, tổng phần cấp phát không được vượt phần có thể cấp của cha.
- Hủy rồi tạo grant khác không tự reset phần đã tiêu.
- Thay token hoặc đổi ID không tạo một envelope mới.

Không dùng trường `maxAmount` từng lệnh thay cho ngân sách tổng. Một người có thể gửi nhiều lệnh dưới trần và vẫn vượt tổng được phép.

### 8.3. Thu hồi cha và chống vòng lặp

Trong mô hình phụ thuộc quyền nguồn của bài, grant con không được dùng cho quyết định mới nếu cha hết hạn, bị thu hồi hoặc không còn đường quyền hợp lệ.

Cần lưu quan hệ nguồn, parent và root đủ để kiểm tra và audit. Chặn vòng như A → B → A nếu chính sách không hỗ trợ, đồng thời giới hạn độ sâu để tránh đường kiểm tra không kiểm soát.

Không chỉ lưu tên người cuối cùng rồi bỏ mất lịch sử nguồn thẩm quyền.

## 9. Token, service và nguy cơ dùng quyền rộng thay người gọi

### 9.1. Một scope trong token chưa mô tả đủ nghiệp vụ

Chuỗi `refund:approve` không tự thể hiện cửa hàng, tiền tệ, trần từng lệnh, ngân sách tổng hoặc người được đại diện.

Có thể dùng token trỏ đến grant ở server, hoặc một cơ chế mang điều kiện chi tiết đã được xác thực. Dù chọn cách nào, resource server vẫn phải kiểm tra hành động cụ thể.

RFC 9396 định nghĩa `authorization_details` để mang dữ liệu yêu cầu quyền chi tiết hơn trong OAuth. Các trường và ý nghĩa của loại quyền cụ thể vẫn cần được triển khai và thống nhất trong hệ thống. [RFC 9396](https://www.rfc-editor.org/rfc/rfc9396.html)

Không coi việc dùng JSON có nhiều trường là bằng chứng các điều kiện đó đã được thực thi.

### 9.2. Ràng buộc đúng dịch vụ và actor

Nếu token chỉ dành cho dịch vụ hoàn tiền, không chấp nhận nó tại dịch vụ chi trả chỉ vì cùng một issuer. Kiểm tra nguồn phát hành, dịch vụ nhận và loại token theo hợp đồng xác thực.

Nếu grant gắn với B, lần gọi phải chứng minh actor phù hợp với B hoặc đường đại diện được phép. Một bearer token không tự chống việc bị sao chép và dùng bởi người khác; mô hình token và biện pháp bảo vệ phải phù hợp với yêu cầu ràng buộc người dùng.

Không dùng `delegationId` như một mật khẩu bí mật duy nhất. Biết ID không chứng minh người gọi là người nhận được chỉ định.

### 9.3. Tránh confused deputy

Một service có tài khoản kỹ thuật quyền rộng nhận yêu cầu từ B. Nếu service chỉ kiểm tra “B được gọi tôi” rồi dùng quyền quản trị để hoàn tiền bất kỳ, nó đã làm mất scope của người gọi.

Khi qua service trung gian, cần truyền ngữ cảnh đã xác thực hoặc một lệnh nghiệp vụ đã được chốt, gồm:

- Actor thực tế và nguồn thẩm quyền.
- Grant, phiên bản và đường ủy quyền.
- Đối tượng, action và nội dung đã được cho phép.
- Dịch vụ nhận, thời hạn hoặc ranh giới cam kết cần áp dụng.

Không lấy header công khai như `X-Act-As` làm nguồn có thẩm quyền. Bên nhận cũng không nên chỉ tin một chuỗi actor được nhét vào message mà thiếu xác thực nguồn và kiểm soát nội dung.

## 10. Transaction, ngân sách và ranh giới thu hồi

### 10.1. Luồng xử lý tham chiếu

~~~text
BEGIN
  1. Xác định actor từ ngữ cảnh xác thực.
  2. Đọc grant, đường nguồn và đối tượng trong đúng tenant.
  3. Điều phối dữ liệu cần giữ nhất quán.
  4. Kiểm tra phiên bản, trạng thái, thời gian và scope.
  5. Kiểm tra điều kiện actor và xung đột trách nhiệm.
  6. Kiểm tra idempotency cho cùng ý định.
  7. Với ý định mới:
       - xác minh các bất biến nghiệp vụ;
       - kiểm tra và giữ ngân sách envelope cần thiết;
       - ghi bằng chứng duyệt theo đúng nội dung;
       - cập nhật trạng thái nếu đã đủ chính sách.
  8. Lưu kết quả và audit.
COMMIT
~~~

Đây là luồng khái niệm, không phải thứ tự khóa dùng được cho mọi database. Đọc dữ liệu trước khi khóa không đủ nếu dữ liệu đó có thể đổi; cần đọc lại hoặc xác minh phiên bản trong ranh giới quyết định.

Trong PostgreSQL, khóa hàng có thể điều phối các thay đổi cạnh tranh trên dữ liệu liên quan. Phải chọn đúng bản ghi đại diện và giao thức truy cập cho bất biến đang bảo vệ. [PostgreSQL Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)

### 10.2. Ngân sách có phần đang giữ

Với envelope 5 triệu trong ví dụ:

~~~text
tiền đã sử dụng + tiền đang giữ + nghĩa vụ mới <= 5.000.000 VND
~~~

Hai request đồng thời không được cùng đọc phần dư rồi cùng vượt giới hạn. Kiểm tra và tăng phần giữ cần được điều phối hoặc cập nhật có điều kiện.

Chính sách phải xác định lúc nào tính tiền: trong ví dụ, nghĩa vụ được giữ khi chấp nhận phê duyệt qua envelope; khi hoàn tiền thành công thì chuyển từ đang giữ sang đã sử dụng. Không cộng hai lần cùng nghĩa vụ.

Nếu một yêu cầu cần nhiều chữ ký, cần định nghĩa cách quy trách nhiệm và tính hạn mức. Không tự giữ toàn bộ số tiền một lần cho mỗi chữ ký rồi coi đó là cùng một sổ, cũng không bỏ hẳn phần giữ vì “mới duyệt, chưa chuyển tiền”.

Khi yêu cầu hủy hoặc thất bại, chỉ giải phóng theo trạng thái cuối được xác nhận. Timeout bên thanh toán có thể là kết quả chưa rõ; không tự coi như chưa chi.

### 10.3. Thu hồi phải có mức bảo đảm rõ ràng

Khóa một bản ghi hoàn tiền không tự khóa nguồn quyền ở một dịch vụ IAM khác. `@Transactional` cũng không tự bao trùm nhiều kho dữ liệu hoặc cache.

Hệ thống cần quy định:

- Thu hồi có hiệu lực tại thời điểm nào?
- Node được phép dùng cache cũ tối đa bao lâu?
- Grant cha bị thu hồi ảnh hưởng grant con thế nào?
- Lệnh đã được tiếp nhận nhưng chưa gửi ra ngoài được xử lý ra sao?
- Nếu không xác minh được nguồn quyền, hành động chờ hay bị từ chối?

Token còn hạn không tự chứng minh grant chưa bị thu hồi. Nếu cần thu hồi trước khi quyết định mới được cam kết, phải có cơ chế kiểm tra trạng thái, phiên bản quyền hoặc phối hợp tương ứng.

Không mô tả thu hồi “ngay lập tức ở mọi nơi” khi thực tế chỉ chờ token hết hạn.

## 11. Scope phải được giữ tới cổng thực thi

### 11.1. Bằng chứng duyệt không phải cờ không giới hạn

Trong ví dụ, bằng chứng của B cần gắn với:

~~~text
actor B và delegator A
grant ID, phiên bản và source authority
refund request ID và phiên bản nội dung
số tiền, tiền tệ, giao dịch gốc và đích hoàn hợp lệ
scope và chính sách đã dùng
envelope và phần nghĩa vụ đã ghi nhận
thời điểm quyết định
~~~

Nếu số tiền hoặc đích hoàn thay đổi, bằng chứng cũ không tự được dùng cho bản mới. Nếu scope của grant bị thu hẹp, cổng thực thi phải áp dụng chính sách hiệu lực đã chọn.

Trong bài, chọn kiểm tra đường ủy quyền còn hợp lệ tại cổng tạo lệnh thực thi. Nếu B duyệt trước 09:00Z nhưng tới sau 09:00Z mới chuẩn bị tạo lệnh, không mặc định grant vẫn cho phép: cần quyền hợp lệ khác hoặc quy trình xử lý tiếp theo.

Một nghiệp vụ khác có thể chọn duy trì hiệu lực cho lệnh đã cam kết trước hạn. Điều đó phải được định nghĩa rõ; không để worker tự lựa chọn theo cách thuận tiện.

### 11.2. Tách biệt người duyệt không chỉ dựa trên tài khoản

Giả sử chính sách yêu cầu hai nguồn phê duyệt độc lập. A cấp cho cả B và C cùng quyền duyệt, rồi B và C cùng ký.

Nếu chính sách coi hai người đại diện cùng một nguồn quyền là một vị trí trách nhiệm, hai chữ ký đó không tạo đủ hai nguồn độc lập. Cần giữ provenance của grant và định nghĩa cách tính vị trí, không chỉ đếm hai account ID.

Không có một quy tắc độc lập chung cho mọi tổ chức. Điều bắt buộc là chính sách phải chọn rõ vai trò của actor, delegator và nguồn quyền trong phép tính.

### 11.3. Lệnh và sự kiện không được làm rơi điều kiện

Sau kiểm tra cuối, có thể ghi lệnh thực thi bất biến và outbox cùng transaction. Worker gửi đúng nội dung đã chốt.

Không để worker nhận một ID rồi dùng quyền hệ thống đọc nội dung mới đã bị sửa, bỏ qua scope và bằng chứng ban đầu. Nếu worker phải đánh giá lại, nó cần đủ nguồn dữ liệu và chính sách để làm điều đó đúng.

Outbox không tự bảo đảm tác dụng phụ chỉ xảy ra một lần. Cần định danh nghiệp vụ ổn định, cơ chế xử lý lặp và đối soát kết quả bên ngoài.

## 12. Vòng đời grant và thay đổi phạm vi

~~~mermaid
stateDiagram-v2
    [*] --> Proposed
    Proposed --> Active: kiểm tra nguồn và chấp thuận cấp
    Proposed --> Rejected: không được phép cấp
    Active --> Expired: đạt validUntil
    Active --> Revoked: thu hồi
    Active --> Suspended: tạm đình chỉ
    Suspended --> Active: cho phép khôi phục
    Suspended --> Revoked: thu hồi
    Suspended --> Expired: hết thời gian
~~~

Khôi phục không được tự kéo dài thời hạn hoặc tăng trần.

Khi sửa scope:

- Mở rộng đối tượng, action, tiền hoặc thời hạn phải được xét như một thay đổi cấp quyền.
- Thu hẹp cần xác định tác động đến token, cache và bằng chứng đang chờ.
- Lưu phiên bản và lịch sử thay vì sửa mất dấu vết.
- Token trỏ tới phiên bản cũ phải có cách xử lý theo chính sách.
- Không tạo envelope mới chỉ để bỏ phần ngân sách đã sử dụng.

Một thông tin có thể thay đổi mà không tăng quyền vẫn có ý nghĩa audit. Không quyết định tính an toàn chỉ dựa vào việc một con số trần có giảm hay không.

Với idempotency, cùng ý định retry không được cấp thêm grant hoặc duyệt thêm lần nữa. Khi trả kết quả cũ sau khi grant hết hạn, vẫn cần quyền đọc phù hợp; trả kết quả đã có không đồng nghĩa thực hiện lại hành động.

## 13. Kiểm thử tình huống tấn công logic

Bảng sau là kịch bản cho một triển khai, không phải kết quả đã chạy kiểm thử hệ thống cụ thể.

| Tình huống | Điều phải giữ |
|---|---|
| Người có quyền dùng nhưng không có quyền chuyển giao tạo grant | Không cấp được ủy quyền |
| Scope đề nghị vượt quyền nguồn ở một chiều | Không chấp nhận chỉ vì các chiều khác nhỏ hơn |
| B duyệt S2 bằng grant chỉ cho S1 | Không vượt phạm vi đối tượng |
| Sửa tenant hoặc store trong body | Dữ liệu server quyết định quan hệ thực |
| Grant cho đọc S1 và duyệt S2 | Không sinh thêm quyền duyệt S1 do gom tập |
| G1 cho S1 trần thấp, G2 cho S2 trần cao | Không ghép thành S1 trần cao |
| B chưa có quyền duyệt trực tiếp nhưng có grant hợp lệ | Cho phép theo đường ủy quyền nếu mọi điều kiện khác thỏa |
| B dùng quyền trực tiếp hợp lệ khác | Đánh giá đường đó riêng, không ghép sai với grant |
| Đúng mốc validFrom và validUntil | Gồm mốc đầu, loại mốc cuối |
| A được tăng quyền sau khi cấp grant | B không tự được tăng scope |
| A bị thu hẹp hoặc mất quyền nguồn | Áp dụng đúng mô hình phụ thuộc đã chọn |
| Cấp grant con khi không cho phép | Bị từ chối |
| Grant con rộng hơn cha hoặc cha hết hiệu lực | Không được dùng cho quyết định mới |
| Tạo vòng hoặc vượt độ sâu | Không có đường kiểm tra vô hạn hoặc mở rộng quyền |
| Tạo nhiều grant/token cùng envelope | Không nhân ngân sách |
| Hai request đồng thời vượt phần dư | Chỉ tiếp nhận trong giới hạn tổng |
| Người lập nhờ người nhận dùng quyền của mình để ký | Không vượt quy tắc tách biệt đã định |
| Hai delegate cùng nguồn ký hai vị trí độc lập | Áp dụng đúng quy tắc nguồn trách nhiệm |
| Thay người hưởng hoặc số tiền sau duyệt | Bằng chứng cũ không áp cho bản mới |
| Service dùng tài khoản quản trị thay người gọi | Không làm mất scope và nguồn thẩm quyền |
| Token đúng chữ ký nhưng sai dịch vụ nhận hoặc sai actor | Không được dùng ngoài hợp đồng xác thực |
| Biết delegation ID của người khác | Không đủ để sử dụng grant |
| Thu hồi, cache cũ hoặc nguồn quyền lỗi | Hành vi đúng mức bảo đảm đã công bố |
| Retry, sự kiện lặp hoặc timeout | Không tạo thêm grant, bằng chứng hoặc tác dụng phụ |

Kiểm thử cần quan sát cả quyết định, bản ghi đã commit, sổ ngân sách và kết quả nghiệp vụ. Một request bị trả lỗi chưa chứng minh không có tác dụng phụ trước đó.

Các ca hợp lệ cũng quan trọng: một thiết kế bắt B phải có sẵn toàn bộ quyền trực tiếp có thể từ chối sai mọi ủy quyền thực sự.

## 14. Audit và các bất biến cốt lõi

Audit cần thể hiện ai đã cấp, ai đã dùng, dùng thay ai, theo đường quyền nào và trên nội dung nào. Ghi cả thay đổi, đình chỉ, hết hạn, thu hồi và kết quả sử dụng.

Quyền đọc audit phải phù hợp với tenant và trách nhiệm. Không ghi token đầy đủ, bí mật hoặc dữ liệu tài khoản nhạy cảm không cần thiết vào log chung.

Những bất biến chính:

- Một hành động có ít nhất một đường thẩm quyền hoàn chỉnh, còn hiệu lực.
- Phạm vi được chuyển giao không vượt phần được phép chuyển giao.
- Danh tính actor và nguồn thẩm quyền không bị đánh tráo.
- Tập rule giữ đúng quan hệ giữa action, đối tượng và điều kiện.
- Nhiều grant hoặc nhiều cấp không tự tăng phạm vi hay ngân sách.
- Ủy quyền không lách tách biệt trách nhiệm, state machine hoặc bất biến tiền.
- Bằng chứng và lệnh thực thi gắn với đúng phiên bản nội dung.
- Retry và thay đổi vòng đời không tạo tác dụng phụ trùng hoặc reset quyền lợi.

Phạm vi ủy quyền là một ranh giới nghiệp vụ cụ thể. Thiết kế tốt cho phép người nhận làm đúng phần việc được giao, đồng thời giữ nguyên các giới hạn mà người cấp và toàn hệ thống phải tuân thủ.
