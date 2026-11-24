# Impersonation expiration: hết hạn quyền thao tác thay người dùng

## 1. Hết hạn impersonation bảo vệ điều gì?

Trong chương **Impersonation**, impersonation là cơ chế cho phép một actor đã xác thực thao tác trong ngữ cảnh của một người dùng khác theo phạm vi được cấp. Ví dụ: nhân viên hỗ trợ xem giao diện hoặc kiểm tra một giỏ hàng của khách để xử lý sự cố.

Impersonation expiration là việc chấm dứt quyền sử dụng ngữ cảnh đó khi đến thời hạn. Nó không chỉ là ẩn một thanh thông báo, xóa một cookie hoặc chờ một token biến mất khỏi trình duyệt.

Sau deadline, hệ thống phải ngăn:

- Tiếp tục đọc dữ liệu của người dùng bằng phiên thao tác thay đã hết hạn.
- Ghi dữ liệu dựa trên một lần kiểm tra quyền trước hạn.
- Refresh token để âm thầm kéo dài quyền.
- Phát lại request hoặc idempotency response nhằm vượt cửa sổ truy cập.
- Giữ WebSocket, job nền hoặc đường tải dữ liệu hoạt động không giới hạn.
- Tự chuyển sang quyền quản trị của actor rồi thực hiện lại thao tác cũ.

Đây là vấn đề bảo vệ quy tắc nghiệp vụ. Actor có thể vẫn đăng nhập hợp lệ trong cổng hỗ trợ, nhưng quyền thao tác thay một subject cụ thể đã kết thúc.

Bài học tập trung vào deadline như một điều kiện cấp quyền phía máy chủ, gắn với đúng actor, subject, tenant, phiên đăng nhập gốc, hành động và đối tượng.

## 2. Ví dụ và ranh giới danh tính

Giả sử nhân viên hỗ trợ A được phép mở phiên impersonation cho khách hàng U để xử lý vụ việc K.

Chính sách minh họa:

| Thành phần | Quy định |
| --- | --- |
| Actor | A, được xác thực bằng tài khoản nhân viên của chính mình |
| Subject | U, người dùng được thao tác thay |
| Tenant đích | Tenant chứa dữ liệu của U, phải nằm trong phạm vi hỗ trợ của A |
| Lý do | Vụ việc K còn hiệu lực và cho phép loại truy cập này |
| Thời hạn tuyệt đối | Tối đa 10 phút, còn bị giới hạn bởi các điều kiện cha |
| Mặc định | Chỉ đọc những dữ liệu được chính sách cho phép |
| Quyền ghi bổ sung | Chỉ khi có scope cụ thể, ví dụ sửa giỏ hàng còn ở trạng thái nháp |
| Hành động bị cấm trong ví dụ | Thanh toán, đổi mật khẩu, thay MFA, cấp role, cấp thông tin đăng nhập dài hạn |
| Kết thúc | Hết hạn, chủ động dừng hoặc bị thu hồi đều chặn việc sử dụng tiếp |

Scope sửa giỏ hàng là một quyền bổ sung trong ví dụ, không phải quyền mặc định của mọi phiên hỗ trợ.

Ba danh tính hoặc ngữ cảnh cần phân biệt:

- **Actor:** A là người thực sự thực hiện.
- **Subject:** U là người dùng có dữ liệu hoặc quyền nghiệp vụ được xét.
- **Phiên đăng nhập gốc:** phiên xác thực của A mà phiên impersonation được ràng buộc vào.

Không dùng thông tin đăng nhập thật của U để triển khai tính năng. Phiên impersonation không phải phiên khách hàng đã đăng nhập và không nên tạo ra mật khẩu, refresh token hoặc quyền đăng nhập dài hạn của U.

Nhân viên hỗ trợ có thể thuộc một miền quản trị khác tenant đích. Khi đó máy chủ phải xác minh phạm vi hỗ trợ cho tenant đích, không tự coi quyền nhân viên là quyền xuyên mọi tenant.

## 3. Mô hình quyền khi đang impersonation

Một thao tác được phép cần thỏa đồng thời:

~~~text
actor được xác thực và phiên gốc còn hợp lệ
AND actor còn quyền hỗ trợ cho tenant và subject này
AND vụ việc hoặc căn cứ cấp quyền còn hợp lệ
AND phiên impersonation đúng actor, subject và phiên gốc
AND phiên impersonation còn hiệu lực
AND hành động nằm trong scope impersonation
AND subject được phép thực hiện hành động trên đối tượng
AND các business invariants của thao tác vẫn đúng
~~~

Scope impersonation có thể hẹp hơn quyền của subject. Đồng thời, quyền quản trị của actor không được hợp với quyền của subject để tạo ra một quyền rộng hơn.

Ví dụ:

- U không được xem đơn của khách khác thì A đang thao tác thay U cũng không được.
- Scope chỉ cho đọc thì một request sửa giỏ hàng vẫn bị từ chối.
- Giỏ đã khóa để thanh toán thì scope sửa giỏ không tự cho phép mở khóa.
- Giá sản phẩm do máy chủ tính; actor không được sửa giá qua payload chỉ vì đang hỗ trợ.
- A có role quản trị riêng không có nghĩa một endpoint impersonation được bỏ qua hạn chế của mode đó.

Nếu sản phẩm có thao tác quản trị riêng, nó cần tuyến cấp quyền và audit riêng. Không âm thầm chuyển từ impersonation sang tuyến quản trị khi một điều kiện thất bại.

## 4. Business invariants về thời hạn

Các invariant cốt lõi:

1. Mỗi phiên impersonation gắn với một actor, một subject, một tenant đích và một phiên đăng nhập gốc xác định.
2. Những liên kết đó không đổi sau khi phát hành.
3. Deadline do máy chủ tính; client không được chọn hoặc ghi đè.
4. Thời hạn không vượt trần chính sách và những deadline cha áp dụng.
5. Token mới không được kéo dài phiên impersonation cũ.
6. Phiên hết hạn hoặc đã thu hồi không được tự trở lại ACTIVE.
7. Trạng thái ACTIVE trong DB không thay thế kiểm tra thời gian.
8. Đúng tại deadline là hết hiệu lực.
9. Mỗi quyết định có tác động phải kiểm tra thời gian tại điểm quyết định phù hợp.
10. Retry không tạo tác động trùng và cũng không miễn kiểm tra phiên impersonation hiện hành.
11. Kết thúc impersonation không đăng xuất hoặc đổi phiên đăng nhập thật của U.
12. Audit giữ actor A và subject U riêng biệt.

Một chính sách dựa trên thời điểm quyết định có thể dùng:

~~~text
started_at <= decision_time < effective_expires_at
~~~

Nếu có thêm trạng thái, điều kiện đầy đủ còn yêu cầu state cho phép và mọi điều kiện cha còn hiệu lực.

Không dùng hai dấu bằng ở cả hai phía của ranh giới kết thúc:

~~~text
Còn hiệu lực: decision_time < effective_expires_at
Đã hết hạn:   decision_time >= effective_expires_at
~~~

## 5. Tính deadline từ những giới hạn cha

### 5.1. Deadline tuyệt đối khi phát hành

Ví dụ, máy chủ tính:

~~~text
expires_at = min(
    started_at + policy_max_duration,
    original_actor_session_absolute_expiry,
    support_authorization_expiry,
    case_access_expiry
)
~~~

Chỉ đưa vào phép min những deadline thực sự áp dụng. Một căn cứ không có deadline cố định vẫn cần được kiểm tra trạng thái thu hồi và không làm mất trần thời gian của phiên impersonation.

Ví dụ A mở phiên lúc 10:00:

| Điều kiện | Deadline |
| --- | --- |
| Trần impersonation 10 phút | 10:10 |
| Phiên đăng nhập gốc của A | 10:30 |
| Quyền hỗ trợ tạm thời | 10:08 |
| Quyền truy cập vụ việc K | 10:20 |

Kết quả expires_at là 10:08. Không phát hành một token cho phép thao tác thay đến 10:10.

Tại 10:08:00 đúng bằng deadline, phiên đã hết hạn.

### 5.2. Điều kiện cha có thể làm quyền kết thúc sớm hơn

Ngoài deadline được cố định khi phát hành, một lần sử dụng vẫn cần xét điều kiện hiện hành:

- A bị vô hiệu hóa hoặc mất quyền hỗ trợ.
- Phiên đăng nhập gốc bị thu hồi.
- Quyền đối với vụ việc K bị rút.
- Scope hoặc điều kiện truy cập không còn thỏa.
- Subject bị vô hiệu hóa theo chính sách áp dụng cho tính năng này.

Các điều kiện đó có thể chấm dứt quyền trước expires_at.

Nếu subject bị vô hiệu hóa nhưng bộ phận hỗ trợ vẫn cần điều tra hồ sơ, sản phẩm có thể cung cấp một tuyến đọc quản trị riêng. Không tự coi đó là lý do để tiếp tục một phiên impersonation trái chính sách.

### 5.3. Gia hạn phiên đăng nhập gốc không gia hạn phiên cũ

Một lần đăng nhập mới hoặc kéo dài phiên gốc không được tự nâng expires_at đã cấp cho impersonation.

Liên kết parent_actor_session_id phải cố định. Không tự chuyển phiên impersonation sang một phiên gốc mới khi A đăng nhập lại.

Đặc biệt, cần phân biệt hạn của access token dùng để gọi API với hạn tuyệt đối của phiên đăng nhập gốc. Việc luân chuyển access token trong cùng phiên không tự cấp thêm thời gian thao tác thay.

## 6. State machine và hết hạn logic

Một mô hình vòng đời:

~~~mermaid
stateDiagram-v2
    [*] --> ACTIVE: Được cấp theo chính sách
    ACTIVE --> ENDED: Actor chủ động dừng
    ACTIVE --> REVOKED: Thu hồi quyền
    ACTIVE --> EXPIRED: Đến hạn và được đánh dấu
~~~

Không có cạnh EXPIRED → ACTIVE hay REVOKED → ACTIVE. Nếu được phép mở một phiên mới, phải có quyết định phát hành mới, định danh mới và kiểm tra quyền mới.

Hai khái niệm cần phân biệt:

- **Hết hạn logic:** decision_time đã đạt deadline; quyền không còn dùng được.
- **Trạng thái EXPIRED được lưu:** DB hoặc worker đã ghi nhận trạng thái kết thúc.

Một bản ghi có state = ACTIVE và expires_at trong quá khứ vẫn phải bị từ chối. Worker chậm không được kéo dài quyền.

API trạng thái nên tính hiệu lực hiện tại từ dữ liệu chuẩn, không trả “còn hoạt động” chỉ vì chưa chạy job dọn.

Nếu hệ thống đánh dấu EXPIRED ngay khi phát hiện, cần chọn cách commit phù hợp. Ném một exception khiến transaction rollback sẽ hủy cả lần đánh dấu đó. Tuy nhiên, ngay cả khi chưa lưu được EXPIRED, quyết định từ chối vẫn phải dựa trên predicate thời gian.

## 7. Thời điểm kiểm tra và nguồn đồng hồ

### 7.1. Request đến trước hạn chưa chắc được thực hiện

Giả sử deadline là 10:08:00.000:

~~~text
10:07:59.800  Request sửa giỏ hàng bắt đầu.
10:07:59.850  Request chờ khóa giỏ hàng.
10:08:00.100  Request có đủ khóa để quyết định.
~~~

Theo chính sách của bài, request phải bị từ chối. Thời gian đã đọc lúc bắt đầu không chứng minh quyền còn hiệu lực sau khi chờ khóa.

Một trình tự phù hợp:

~~~text
xác thực actor
-> vào transaction
-> xác định và bảo vệ điều kiện cha
-> khóa phiên impersonation
-> khóa đối tượng cần thao tác
-> kiểm tra quyền và dữ liệu hiện hành
-> lấy decision_time
-> kiểm tra deadline
-> ghi thay đổi và audit
-> commit
~~~

Nếu điều kiện phê duyệt hoặc scope thay đổi đồng thời, chúng cũng cần tham gia cơ chế nhất quán. Chỉ đọc trong transaction không tự làm điều kiện đó bất biến.

### 7.2. Quyết định và commit là hai mốc khác nhau

Bài này chọn điều kiện còn hiệu lực tại thời điểm quyết định sau khi có đủ khóa.

Ví dụ quyết định lúc 10:07:59.999 và commit lúc 10:08:00.003 vẫn có thể hợp lệ theo hợp đồng đó. Không dùng giờ trả HTTP để thay accepted_at hoặc decision_time.

Nếu sản phẩm yêu cầu việc phát hành dữ liệu hay tác động thực tế phải xảy ra trước deadline, cần thêm kiểm soát tại chính điểm phát hành hoặc thực thi. Một lần kiểm tra trước commit không tự chứng minh yêu cầu nghiêm ngặt hơn.

### 7.3. Đồng hồ do máy chủ chọn

Không tin now, clientSentAt hoặc expiresAt trong request. Đồng hồ đếm ngược trên UI chỉ phục vụ trải nghiệm.

Nên có một nguồn thời gian chuẩn trong miền quyết định, ví dụ thời gian thực của cơ sở dữ liệu sau khi đã lấy khóa. Phải phân biệt biểu thức trả:

- Thời điểm bắt đầu transaction.
- Thời điểm bắt đầu câu lệnh.
- Thời gian thực tại lúc được đánh giá.

Không mặc định một hàm tên “current time” có ngữ nghĩa phù hợp. Implementation phải được kiểm chứng trên hệ quản trị đang dùng.

UTC giúp thống nhất biểu diễn instant nhưng không tự đồng bộ đồng hồ. Hệ thống còn cần theo dõi sai lệch và phản ứng khi nguồn thời gian mất độ tin cậy.

Độ chính xác khi lưu, ký token và so sánh cũng phải thống nhất. Không cắt riêng now xuống giây trong khi deadline giữ mili giây, vì cách đó có thể tạo thêm một khoảng chấp nhận muộn.

## 8. Refresh, idle timeout và việc mở phiên mới

### 8.1. Refresh không phải gia hạn impersonation

Nếu có access token riêng cho mode này, thời hạn của token không được vượt deadline của phiên và những giới hạn áp dụng.

Khi refresh hoặc cấp lại token, máy chủ vẫn phải kiểm tra:

- Đúng actor, subject, tenant và parent session.
- Phiên impersonation còn hiệu lực.
- Điều kiện hỗ trợ hiện hành còn thỏa.
- Scope không mở rộng.
- Deadline tuyệt đối giữ nguyên.

Không làm:

~~~text
Mỗi lần refresh:
    expires_at = now + 10 phút
~~~

Một client có thể gọi liên tục và giữ quyền mãi.

Refresh token còn tồn tại cũng không chứng minh còn quyền refresh. Đặc biệt, không trả refresh token đăng nhập của U cho A để sử dụng sau khi mode hỗ trợ kết thúc.

### 8.2. Idle timeout là giới hạn bổ sung

Nếu chính sách có thời gian không hoạt động tối đa:

~~~text
effective_expires_at = min(
    expires_at tuyệt đối,
    last_qualifying_activity_at + idle_timeout,
    những deadline cha hiện hành áp dụng
)
~~~

Cập nhật last_qualifying_activity_at không được làm thay đổi expires_at tuyệt đối.

Cần định nghĩa hoạt động nào được tính. Ví dụ này chỉ tính một số thao tác nghiệp vụ được máy chủ chấp nhận, không tính:

- Polling trạng thái phiên.
- Refresh token.
- Ping giữ kết nối.
- Request bị từ chối.
- Phát lại kết quả idempotency.

Nếu client tự khai lastActivityAt, người dùng có thể kéo dài phiên hoặc ghi thời điểm tương lai.

Kiểm tra idle deadline và cập nhật hoạt động phải nhất quán khi có nhiều request. Một phiên đã hết idle timeout không được hồi sinh chỉ vì request mới đến và ghi last activity trước khi kiểm tra.

### 8.3. Mở phiên mới là quyết định mới

Có thể cho phép A mở một phiên mới sau khi phiên trước kết thúc, nhưng cần kiểm tra lại quyền, vụ việc, subject, scope và các giới hạn phát hành.

Nếu sản phẩm cần giới hạn tổng thời gian thao tác thay theo vụ việc hoặc actor, phải có quota hoặc chính sách bổ sung. Giới hạn 10 phút mỗi session không tự ngăn việc mở hàng trăm session liên tiếp.

Một retry của thao tác tạo phiên với cùng idempotency key nên nhận lại quyết định tạo ban đầu. Nếu phiên đó đã hết hạn, không âm thầm tạo một phiên mới bằng cùng key.

Đăng nhập lại, refresh, mở tab khác hoặc request thất bại không phải căn cứ tự động mở lại impersonation.

## 9. Dữ liệu phiên và transaction bảo vệ thao tác

### 9.1. Bản ghi quyền thao tác thay

Một impersonation_session có thể chứa:

| Trường | Vai trò |
| --- | --- |
| session_id | Định danh phiên thao tác thay |
| actor_id | Người thực sự được cấp quyền |
| subject_id | Người dùng đích |
| target_tenant_id | Phạm vi dữ liệu đích |
| parent_actor_session_id | Phiên đăng nhập gốc đã cấp căn cứ |
| support_authorization_id | Quyền hỗ trợ hoặc quyết định cấp quyền liên quan |
| case_id | Vụ việc làm căn cứ |
| allowed_actions | Scope được máy chủ cấp |
| started_at, expires_at | Khoảng thời gian tuyệt đối |
| last_qualifying_activity_at | Hoạt động được tính cho idle timeout nếu có |
| state, row_version | Vòng đời và kiểm soát ghi |
| ended_at, end_reason | Dấu vết kết thúc |

Định danh phiên không phải bí mật đủ để cấp quyền. Biết session_id vẫn phải chứng minh đúng actor, phiên gốc và điều kiện hiện hành.

Không cho một API sửa subject_id hoặc parent_actor_session_id của phiên ACTIVE. Chuyển sang khách hàng khác phải là quyết định mới có quyền, thời hạn và audit riêng.

Không cần gắn phiên hỗ trợ vào cookie đăng nhập thật của U. Điều đó dễ làm việc dừng hỗ trợ ảnh hưởng nhầm tới phiên khách hàng.

### 9.2. Phạm vi nhất quán

Ví dụ transaction dưới đây giả sử dữ liệu phiên gốc, quyền hỗ trợ, impersonation session, đối tượng và idempotency có thể được bảo vệ trong cùng một cơ sở dữ liệu hoặc miền nhất quán tương đương.

Một thứ tự khóa minh họa:

1. Bản ghi idempotency.
2. Phiên đăng nhập gốc và những hàng thẩm quyền hỗ trợ cần kiểm tra.
3. Phiên impersonation.
4. Đối tượng nghiệp vụ.
5. Các hàng quota hoặc tổng hợp nếu có.

Mọi luồng dừng, thu hồi và thực thi phải theo giao thức chung đối với các hàng cùng được sử dụng. Nếu chính sách đòi subject còn hoạt động hoặc vụ việc còn cho phép truy cập, dữ liệu quyết định các điều kiện đó cũng cần được bảo vệ thích hợp.

Nếu IAM hoặc quyền hỗ trợ nằm ở một dịch vụ khác, không mặc định một lần HTTP check sẽ commit nguyên tử với DB nghiệp vụ. Cần thiết kế ngữ nghĩa phiên bản, độ mới và thu hồi đáp ứng mức bảo đảm đã chọn.

### 9.3. Mã giả Java: cập nhật giỏ hàng trong scope được cấp

Đây là trường hợp phiên đã được cấp thêm scope UPDATE_CART. Nó không áp dụng cho phiên chỉ đọc.

~~~java
CartUpdateResult updateCart(
        ActorAuthentication actor,
        ImpersonationReference reference,
        CartUpdateCommand cmd) {

    String fingerprint = fingerprint(
        cmd.cartId(), cmd.expectedRevision(), cmd.requestedQuantity()
    );

    return tx.required(connection -> {
        IdempotencyDecision key = idem.acquire(
            connection, actor, reference.sessionId(),
            "UPDATE_CART", cmd.idempotencyKey(), fingerprint
        );

        ImpersonationContext context = security.lockCurrentContext(
            connection, actor, reference
        );

        context.requireBindingsMatch(actor);
        context.requireCurrentParentAndSupportAuthority();
        context.requireActionAllowed("UPDATE_CART");

        Cart cart = carts.lock(
            connection, context.targetTenantId(), cmd.cartId()
        );

        authorization.requireSubjectOwnsCart(context, cart);
        authorization.requireSubjectPermission(context, cart, "UPDATE_CART");

        Instant t = timeSource.nowAfterLocks(connection);
        context.requireLiveAt(t);

        if (key.hasResult()) {
            authorization.requireResultAccess(context, cart, key);
            return key.originalResult();
        }

        cart.requireRevision(cmd.expectedRevision());
        cart.requireDraft();
        long quantity = policy.validateQuantity(cmd.requestedQuantity());
        Money total = pricing.computeServerSide(cart, quantity);

        carts.updateIfCurrent(connection, cart, quantity, total);
        sessions.recordQualifyingActivity(connection, context, t);
        audit.recordImpersonatedChange(connection, context, cart, t);

        CartUpdateResult result = CartUpdateResult.updated(cart.id());
        return idem.complete(connection, key, result);
    });
}
~~~

Hợp đồng đi kèm:

- Đây là mã giả; các API là abstraction của ứng dụng.
- Tất cả thay đổi local liên quan dùng cùng connection và transaction.
- tx.required chỉ trả thành công ra ngoài sau commit.
- lockCurrentContext đọc lại và bảo vệ những điều kiện cần nhất quán.
- Actor không lấy từ body; subject và tenant lấy từ context đã được xác minh.
- requireLiveAt kiểm tra state, deadline tuyệt đối, idle deadline nếu có và các deadline cha áp dụng.
- Thời gian được lấy sau khi đã chờ những khóa cần thiết, không phải thời gian khởi tạo transaction.
- updateIfCurrent kiểm tra revision và số hàng cập nhật; thất bại phải rollback.
- recordQualifyingActivity không thay đổi expires_at tuyệt đối.
- Replay chỉ được trả sau các kiểm tra phiên hiện hành và quyền đọc kết quả; nó không làm mới idle timeout.
- Giá tính phía máy chủ, không nhận giá đã sửa từ client.
- Không gọi dịch vụ mạng chậm khi đang giữ khóa.

Ví dụ chọn từ chối bằng lỗi nếu phiên không còn hiệu lực, không bắt buộc ghi EXPIRED trong transaction đó. Trạng thái lưu có thể được dọn sau; predicate thời gian vẫn phải chặn ngay.

### 9.4. Không cache một lần cho phép thành quyền vĩnh viễn

Middleware có thể kiểm tra sớm để loại request sai, nhưng một kết quả hợp lệ lúc bắt đầu không thay thế kiểm tra cuối tại thao tác cần bảo vệ.

Không truyền authorized = true xuống một hàng đợi rồi dùng nó nhiều phút sau. Một snapshot context có thể hỗ trợ ghi audit, nhưng không tự là quyền thực thi mới sau deadline.

Trong Java, tránh sửa một đối tượng Authentication dùng chung thành danh tính U rồi để nó tồn tại qua request khác. Nếu dùng context theo request hoặc ThreadLocal, phải dọn và truyền ngữ cảnh async một cách có kiểm soát. Worker nhận context cũ vẫn phải áp dụng quy tắc hiệu lực tại điểm thực thi.

## 10. Idempotency khi impersonation đã hết hạn

### 10.1. Không thực hiện lại và không tiết lộ thêm

Tình huống:

~~~text
10:07:59.900  Cập nhật giỏ hàng thành công, commit.
10:08:00.100  Client mất phản hồi, retry cùng key.
10:08:00.100  Phiên impersonation đã hết hạn.
~~~

Hệ thống phải bảo toàn kết quả của lần đầu và không cập nhật giỏ lần nữa. Tuy nhiên, theo chính sách của bài, endpoint impersonation cũng không tiếp tục trả dữ liệu của U bằng phiên đã hết hạn.

Kết quả phù hợp là lỗi phiên hết hạn cho lần retry, trong khi bản ghi nghiệp vụ và idempotency của lần trước vẫn được giữ.

Nếu sản phẩm cần cho nhân viên tra cứu biên nhận sau đó, cung cấp một tuyến kiểm tra riêng dựa trên quyền actor hiện hành và dữ liệu được phép xem. Không tái sử dụng phiên đã hết hạn như một quyền đọc vô thời hạn.

Đây là hai yêu cầu đồng thời:

~~~text
retry không gây tác động lần hai
AND retry không miễn kiểm tra quyền truy cập hiện hành
~~~

Không đưa nhánh return cachedResponse lên trước mọi kiểm tra impersonation chỉ vì đó là cách xử lý idempotency của một endpoint thông thường.

### 10.2. Key phải gắn với ngữ cảnh

Không để key của A thao tác thay U được dùng để lấy phản hồi của một phiên khác hoặc một subject khác.

Namespace và fingerprint nên ràng buộc các thành phần phù hợp:

- Actor đã xác thực.
- Tenant đích.
- Impersonation session.
- Loại thao tác.
- Nội dung nghiệp vụ, đối tượng và revision liên quan.

Same key với payload khác phải bị từ chối xung đột. Nội dung subject hoặc tenant không được lấy tùy ý từ client để tra phản hồi của người khác.

Đọc trạng thái key trong nội bộ transaction không có nghĩa được phép trả nội dung cho caller. Quyền truy cập phải được kiểm tra trước khi phát phản hồi.

### 10.3. Đổi mode không phải lý do retry tự động

Sau khi hết hạn, không tự gửi lại request với:

- Quyền actor bình thường.
- Một impersonation session mới.
- Subject khác.
- Key mới nhằm né lỗi.

Nếu người dùng chủ động mở phiên mới rồi thử một hành động mới, ràng buộc nghiệp vụ vẫn phải bảo vệ tác động trùng. Idempotency gắn với session khác không tự nhận diện hai request là cùng một ý định.

Với thao tác không tự idempotent, cần định danh nghiệp vụ hoặc ràng buộc duy nhất thích hợp. Trong ví dụ giỏ hàng, expectedRevision giúp ngăn áp dụng lại một thay đổi trên revision cũ; nó không thay thế mọi cơ chế chống trùng của các nghiệp vụ khác.

## 11. Dừng mode và trở về ngữ cảnh actor

### 11.1. Dừng impersonation không đăng xuất khách hàng

Khi A chọn “Dừng thao tác thay”, server xác minh quyền sở hữu phiên hoặc quyền thu hồi tương ứng, rồi kết thúc phiên đó.

Không:

- Xóa phiên đăng nhập thật của U.
- Đổi mật khẩu hoặc vô hiệu hóa tài khoản U.
- Tạo một phiên đăng nhập U mới.
- Chuyển sang một subject được truyền trong redirect.
- Dùng dữ liệu trong browser để khôi phục danh tính có đặc quyền.

Phiên đăng nhập gốc của A có thể vẫn còn hiệu lực. UI có thể đưa A về khu vực hỗ trợ sau một thao tác chuyển mode rõ ràng, qua ngữ cảnh actor đã được server xác thực.

### 11.2. Endpoint dừng sau khi đã hết hạn

Có thể cho phép actor đã xác thực gọi một endpoint dừng hoặc xem metadata tối thiểu của chính phiên mình sau khi deadline qua.

Đây là quyền quản lý phiên theo actor, không phải tiếp tục thao tác thay U. Endpoint này không được trả giỏ hàng, đơn hàng hoặc dữ liệu subject ngoài phạm vi riêng được cấp.

Lệnh dừng nên idempotent: phiên đã ENDED, EXPIRED hoặc REVOKED thì trả trạng thái kết thúc phù hợp, không mở lại. Audit giữ được nguyên nhân kết thúc thực tế.

Nếu actor đã đăng xuất, mọi thao tác impersonation gắn với phiên gốc đó phải bị chặn theo chính sách; việc dọn bản ghi có thể do hệ thống thực hiện.

### 11.3. Không fallback khi tham chiếu impersonation lỗi

Nếu request được gửi trong mode impersonation nhưng session đã hết hạn hoặc không hợp lệ, trả lỗi rõ ràng sau khi xác minh quyền nhận thông tin lỗi.

Không làm:

~~~text
Không xác minh được impersonation:
    bỏ context này
    chạy lại bằng role ADMIN của actor
~~~

Cách đó biến hết hạn thành một đường nâng quyền, đồng thời khiến audit phản ánh sai ý định của thao tác.

Client cũng không nên tự retry một lệnh ghi dưới mode khác. Một thao tác chuyển mode phải là quyết định mới, không thay đổi âm thầm cơ sở cấp quyền của request đã gửi.

## 12. Browser, nhiều tab và cache

### 12.1. UI hỗ trợ người dùng nhận biết mode

Giao diện nên thể hiện rõ:

- A đang thao tác thay U.
- Tenant hoặc phạm vi đích.
- Scope chính và deadline.
- Cách kết thúc mode.

Đồng hồ đếm ngược giúp tránh thao tác sát hạn nhưng server vẫn là nơi quyết định.

Khi nhận lỗi hết hạn, UI dừng gửi hành động impersonation, đóng hoặc làm mới các thành phần liên quan và cho phép trở về ngữ cảnh actor theo luồng được thiết kế. Không chỉ ẩn banner trong khi API vẫn mang session cũ.

### 12.2. Nhiều tab cần ngữ cảnh rõ ràng

Nếu một cookie toàn trình duyệt chỉ chứa “subject hiện tại”, việc tab thứ nhất đổi khách có thể khiến tab thứ hai gửi lệnh trên khách khác.

Nên có tham chiếu mode rõ ràng cho từng request hoặc ngữ cảnh tab, với server xác minh actor, subject và tenant tương ứng. Cơ chế cụ thể tùy kiến trúc nhưng không được dựa vào một biến toàn cục mơ hồ.

Dừng một phiên phải chặn đúng phiên đó. Nếu chính sách muốn dừng mọi phiên của actor, cần thao tác và căn cứ rõ ràng.

Các endpoint dùng cookie vẫn cần bảo vệ request theo cơ chế chống giả mạo và quản lý phiên của ứng dụng. Thêm impersonation không được làm mất những kiểm soát hiện có.

### 12.3. Cache phải phân biệt actor và subject

Không dùng một cache key chỉ theo URL cho các phản hồi có thể khác nhau giữa actor, subject, tenant và mode. Một phản hồi của U không được trả cho một ngữ cảnh khác vì URL giống nhau.

Dữ liệu nhạy cảm cần chính sách cache phù hợp. Sau khi kết thúc mode, UI nên loại bỏ dữ liệu subject còn giữ trong state hoặc cache phía ứng dụng để tránh hiển thị nhầm.

Điều đó không thể thu hồi dữ liệu đã được người dùng hợp lệ nhận trước đó. Mục tiêu của expiry là chặn việc cấp quyền và phát hành dữ liệu mới theo hợp đồng, không phải xóa ngược mọi bản sao đã tồn tại.

## 13. WebSocket, stream, job và đường tải dữ liệu

### 13.1. Handshake hợp lệ không cấp quyền vô hạn

Một WebSocket được mở trước deadline có thể tiếp tục sống sau deadline. Nếu server chỉ xác thực khi handshake, client giữ được kênh đọc hoặc ghi ngoài thời hạn.

Cần quy định và thực thi:

- Kiểm tra thời hạn tại các thông điệp hoặc tác động được bảo vệ.
- Chặn sự kiện mới khi quyền hết hiệu lực.
- Hủy đăng ký hoặc đóng kết nối theo chính sách.
- Không dựa duy nhất vào timer phía browser.

Timer đóng kết nối phía server hỗ trợ vận hành, nhưng kiểm tra thời gian ở đường xử lý vẫn cần thiết để chịu được trễ lịch chạy.

Với luồng dữ liệu dài, chọn đơn vị quyết định phù hợp như mỗi thông điệp hoặc mỗi đợt phát hành. Khi đòi chặn dữ liệu mới sau hạn, cần kiểm tra trước khi server phát đơn vị dữ liệu đó; không thể lấy thời điểm client nhận gói tin làm mốc mà server kiểm soát hoàn toàn.

### 13.2. Job được tạo trước hạn chưa chắc được chạy sau hạn

Một job mang yêu cầu thực hiện thao tác thay U sau này phải kiểm tra lại quyền theo chính sách khi thực thi. Không coi việc enqueue trước hạn là quyền vô thời hạn.

Phân biệt hai trường hợp:

| Công việc | Ý nghĩa |
| --- | --- |
| Gửi thông báo về một thay đổi đã commit hợp lệ | Hệ quả của quyết định đã ghi |
| Job thực hiện một thay đổi chưa được quyết định | Một hành động mới cần điều kiện cấp quyền tương ứng |

Consumer của thông báo cần xác minh sự kiện và chống xử lý trùng. Consumer của hành động mới còn phải kiểm tra phiên hoặc một quyền thực thi riêng được thiết kế rõ ràng.

Không tạo một job dài hạn chỉ để đưa tác động ra ngoài đường kiểm tra impersonation.

### 13.3. Token tải file có thể vượt deadline

Nếu phiên hỗ trợ được phép tạo đường tải có chữ ký, thời hạn của đường tải phải được thiết kế cùng hợp đồng impersonation.

Một URL còn dùng được sau khi phiên hết hạn có thể trở thành quyền truy cập độc lập ngoài ý muốn. Chỉ rút ngắn exp của token không tự hỗ trợ thu hồi ngay nếu nơi nhận không kiểm tra trạng thái phiên.

Có thể cần:

- Cấm loại artifact đó trong mode này.
- Dùng proxy kiểm tra phiên hiện hành trước khi phát dữ liệu.
- Hoặc cấp một quyền độc lập hẹp với thời hạn và ngữ nghĩa thu hồi được chính sách cho phép.

Trong chính sách minh họa chỉ đọc hạn chế, không mặc định cho phép xuất hàng loạt, cấp API key hoặc tạo quyền tải dài hạn. Những hành động đó cần quyết định riêng, không suy ra từ quyền xem một màn hình.

## 14. Những thiết kế dễ làm expiry mất tác dụng

| Thiết kế | Lỗi nghiệp vụ | Hướng xử lý |
| --- | --- | --- |
| Hết giờ chỉ ẩn banner | Server vẫn cho gọi API | Kiểm tra deadline phía máy chủ |
| Chỉ nhìn state = ACTIVE | Worker chậm kéo dài quyền | Kiểm tra cả trạng thái và thời gian |
| Refresh đặt lại TTL từ now | Có thể giữ mode vô hạn | Deadline tuyệt đối bất biến |
| Token còn hạn thì coi hợp lệ | Bỏ qua session hoặc điều kiện cha đã kết thúc | Kiểm tra theo hợp đồng trạng thái hiện hành |
| Chỉ kiểm tra đầu request | Chờ khóa qua deadline vẫn ghi | Quyết định lại sau khi có đủ khóa |
| Return idempotency response trước kiểm tra phiên | Rò rỉ dữ liệu qua phản hồi cũ | Kiểm tra quyền hiện hành trước replay |
| Context lỗi thì fallback sang actor | Request đổi sang tuyến đặc quyền | Từ chối mode lỗi, chuyển mode rõ ràng |
| Copy credential của U | Quyền sống ngoài session hỗ trợ | Dùng context impersonation có giới hạn |
| Dừng hỗ trợ bằng logout U | Làm ảnh hưởng phiên khách hàng thật | Kết thúc đúng impersonation session |
| WebSocket chỉ kiểm tra handshake | Kênh vẫn đọc hoặc ghi sau hạn | Kiểm soát thông điệp và đóng theo chính sách |
| Job giữ snapshot authorized | Thực hiện muộn bằng quyền cũ | Kiểm tra lúc thực thi hoặc quyền riêng |
| Cache không có mode và subject | Trả dữ liệu nhầm ngữ cảnh | Phân vùng cache và kiểm tra truy cập |

## 15. Kiểm thử ranh giới và tình huống tấn công

### 15.1. Ma trận kiểm thử

| Tình huống | Điều cần chứng minh |
| --- | --- |
| Ngay trước deadline | Có thể thực hiện nếu đủ mọi điều kiện khác |
| Đúng deadline | Bị từ chối |
| Ngay sau deadline | Bị từ chối, không phụ thuộc worker |
| State vẫn ACTIVE nhưng quá giờ | Không đọc hoặc ghi bằng phiên đó |
| Request bắt đầu trước hạn, lấy khóa sau hạn | Dùng thời gian quyết định mới và từ chối |
| Quyết định trước hạn, commit sau hạn | Theo hợp đồng đã chọn, không nhầm với giờ trả HTTP |
| Parent actor session hết hạn sớm hơn | Phiên impersonation không vượt parent |
| Parent session bị thu hồi trước deadline | Chặn thao tác mới |
| Actor đăng nhập lại | Phiên cũ không tự gắn parent mới |
| Actor mất quyền hỗ trợ | Không tiếp tục dựa vào token cũ |
| Vụ việc mất quyền truy cập | Áp dụng điều kiện cha hiện hành |
| Subject không còn thỏa chính sách | Không dùng impersonation để bỏ hạn chế |
| Client sửa expiresAt hoặc now | Không thay đổi deadline hoặc đồng hồ chuẩn |
| Refresh liên tục | Không thay expires_at tuyệt đối |
| Ping hoặc polling trạng thái | Không làm mới idle timeout theo ví dụ |
| Request idle đã hết hạn đến rồi ghi activity | Không hồi sinh phiên |
| Cấp lại token | Token không vượt deadline hiệu lực |
| Tạo phiên retry cùng key sau khi phiên cũ hết hạn | Không tự mở phiên mới |
| Retry sau commit, trước hết hạn | Có thể trả kết quả cũ nếu còn quyền |
| Retry sau commit, sau hết hạn | Chặn truy cập theo mode, không gây tác động mới |
| Key trùng khác payload hoặc context | Không lấy nhầm phản hồi |
| Key mới cho cùng tác động cũ | Ràng buộc revision hoặc nghiệp vụ ngăn tác động trùng |
| Sai actor, subject hoặc tenant | Không dùng được session tham chiếu |
| Scope chỉ đọc gửi lệnh ghi | Bị từ chối dù session còn hạn |
| Sửa giá hoặc bỏ bước checkout | Các business invariants vẫn được giữ |
| Dừng phiên hỗ trợ | Không đăng xuất U |
| Session hết hạn và actor có role ADMIN | Không fallback rồi thực hiện lệnh cũ |
| Hai tab thao tác hai subject | Không đổi nhầm ngữ cảnh giữa tab |
| WebSocket đi qua deadline | Không tiếp tục tác động bằng quyền đã kết thúc |
| Job chạy sau deadline | Theo quy tắc thực thi, không dùng snapshot vô hạn |
| Link tải hoặc artifact phát sinh | Không tạo cửa truy cập dài hơn quyền đã được cấp |
| Cache trả dữ liệu sau chuyển mode | Không rò dữ liệu sang actor hoặc subject khác |

### 15.2. Kiểm thử đồng thời

Dùng nhiều connection thật trên hệ quản trị mục tiêu để kiểm tra:

- Thu hồi parent session đua với cập nhật giỏ.
- Dừng impersonation đua với một lệnh ghi.
- Request chờ khóa đối tượng qua deadline.
- Hai request cạnh tranh cập nhật hoạt động và kiểm tra idle timeout.
- Refresh đua với thu hồi.
- Retry sau lỗi deadlock hoặc rollback.

Một cách điều phối:

1. Transaction A giữ khóa đối tượng.
2. B bắt đầu trước deadline và bị chặn.
3. Cho thời điểm quyết định vượt deadline bằng cơ chế kiểm thử phù hợp.
4. Nhả khóa A.
5. Khẳng định B không dùng timestamp cũ để cập nhật dữ liệu.

Cần kiểm thử cả implementation lấy giờ thật của DB. Mock timeSource không phát hiện được một hàm đang trả giờ bắt đầu transaction.

Dùng barrier, latch hoặc cơ chế điều phối để chạm đúng điểm cạnh tranh, thay vì chỉ gửi request tuần tự hoặc sleep ngẫu nhiên.

### 15.3. Dữ liệu cần kiểm tra sau commit

Không chỉ dựa vào HTTP 200 hoặc 403. Sau mỗi kịch bản cần kiểm tra:

- Thay đổi nghiệp vụ chỉ tồn tại nếu quyết định hợp lệ.
- Không có thay đổi riêng lẻ sau rollback.
- Revision và số tiền khớp dữ liệu máy chủ.
- Deadline tuyệt đối không tăng do refresh, replay hoặc activity.
- Audit ghi đúng actor, subject, tenant và session.
- Không có kết quả idempotency mới trỏ đến một tác động chưa commit.
- Retry không trừ quota hoặc gây tác động thêm lần nữa.
- Phiên U thật và các phiên hỗ trợ không liên quan không bị kết thúc nhầm.

Đối soát nhiều bảng cần một ảnh chụp nhất quán hoặc cơ chế đồng bộ phù hợp. Không đọc hai phần dữ liệu ở hai phía của một commit rồi kết luận có sai lệch.

## 16. Audit và phản hồi khi hết hạn

Audit một phiên nên giữ:

- Ai yêu cầu và ai được cấp quyền.
- Subject, tenant và vụ việc.
- Parent actor session.
- Scope, căn cứ và phiên bản chính sách.
- started_at, expires_at và các deadline đã giới hạn việc cấp.
- Thời điểm và lý do kết thúc.
- Actor nào đã dừng hoặc thu hồi.
- Các quyết định có tác động cùng decision_time.
- Những lần thử dùng phiên sau khi kết thúc.

Không ghi log như thể U trực tiếp thao tác. Một thay đổi cần nhận diện được A là actor và U là subject, cùng session_id dùng để cấp quyền.

Không ghi token, cookie, bí mật ký hoặc toàn bộ dữ liệu nhạy cảm của subject. Quyền xem audit là một quyền riêng.

Metric hữu ích gồm:

- Số phiên đang hiệu lực theo nhóm phạm vi.
- Tỷ lệ hết hạn, chủ động dừng và bị thu hồi.
- Lần thử dùng phiên quá hạn.
- Request chờ khóa qua deadline.
- Refresh hoặc activity có dấu hiệu kéo dài quyền bất thường.
- Sai actor, sai subject và sai parent session.
- Kết nối dài hoặc job chưa kết thúc đúng hợp đồng.
- Độ trễ cập nhật trạng thái và vô hiệu hóa cache.

Không dùng mọi session_id hoặc subject_id làm nhãn metric có số lượng giá trị không giới hạn. Dùng metric tổng hợp và log được kiểm soát cho điều tra cụ thể.

Phản hồi hết hạn nên rõ để client dừng mode, chẳng hạn mã nghiệp vụ IMPERSONATION_EXPIRED. Không tiết lộ thông tin của session thuộc actor khác cho người chỉ đoán được ID.

Nếu một thay đổi đã commit trước khi hết hạn nhưng client chưa nhận kết quả, thông báo không nên khẳng định thay đổi chắc chắn chưa xảy ra. Hệ thống cần cách đối soát qua một tuyến có quyền phù hợp thay vì hướng dẫn client gửi lại mù quáng.

## 17. Tự phân tích một phiên hỗ trợ

Phiên S thuộc actor A, subject U, parent P, expires_at = 10:08:00.000.

| Tình huống | Cách xử lý đúng trong ví dụ |
| --- | --- |
| A refresh token lúc 10:07:59 | Không được cấp quyền vượt 10:08 |
| API nhận request lúc 10:07:59.900, quyết định lúc 10:08:00.010 | Hết hạn; thời điểm gửi không cứu được quyền |
| Bản ghi S còn ACTIVE lúc 10:09 vì worker dừng | Vẫn từ chối |
| Giỏ đã cập nhật trước hạn, retry sau hạn | Không ghi lại; endpoint impersonation từ chối truy cập theo S |
| A đăng nhập lại thành P2 | S vẫn gắn P, không tự hồi sinh |
| UI ẩn banner nhưng giữ WebSocket cũ | Server vẫn phải chặn quyền đã kết thúc |
| A chọn dừng S | Không đăng xuất tài khoản U |
| Request S lỗi nhưng A có quyền quản trị riêng | Không tự thực hiện lại dưới quyền quản trị |
| Một thông báo về thay đổi đã commit được gửi sau hạn | Xử lý theo quyết định đã ghi, không cấp thao tác thay mới |
| Một job muốn sửa dữ liệu U sau hạn | Cần điều kiện thực thi hợp lệ, không dùng S đã hết hạn |

Nếu các thành phần đưa ra kết luận khác nhau cho những trường hợp này, hệ thống có thể đang dùng nhiều định nghĩa “phiên còn hiệu lực” cùng lúc.

## 18. Checklist áp dụng

- Actor, subject, tenant đích và parent actor session có tách biệt rõ không?
- Có tạo quyền impersonation riêng thay vì sao chép credential của subject không?
- Deadline có do máy chủ cấp và bị chặn bởi các giới hạn cha không?
- Refresh, activity hoặc đăng nhập lại có vô tình kéo dài phiên cũ không?
- Quy tắc idle timeout có định nghĩa hoạt động được tính không?
- Đúng tại deadline có bị coi là hết hạn ở mọi đường xử lý không?
- Có kiểm tra cả state và thời gian, không phụ thuộc worker không?
- Thời gian quyết định có lấy sau khi chờ khóa bằng nguồn chuẩn không?
- Điều kiện actor, parent, vụ việc và subject hiện hành có được tái xác minh không?
- Scope impersonation có hẹp hơn hoặc bằng quyền được phép, không hợp thêm role quản trị không?
- Object ownership, trạng thái, giá và các bước phê duyệt có vẫn được bảo vệ không?
- Idempotency replay có phải qua kiểm tra phiên và quyền hiện hành không?
- Kết thúc mode có tránh logout khách hàng và tránh fallback đặc quyền không?
- Nhiều tab, cache và context async có giữ đúng actor và subject không?
- WebSocket, stream, job và link tải có cùng hợp đồng thời hạn không?
- Audit có chứng minh được ai thao tác thay ai, theo phiên nào và tại instant nào không?

Một phiên impersonation an toàn chỉ cho phép thao tác thay trong cửa sổ và phạm vi đã cấp. Khi quyền đó kết thúc, mọi tuyến sử dụng phải ngừng dựa vào nó, trong khi các quyết định đã commit và danh tính actor thật vẫn được bảo toàn để đối soát.
