# Recovery notification entity: mô hình thực thể thông báo khôi phục tài khoản

Khi tài khoản được khôi phục, hệ thống có thể cần gửi hướng dẫn, mã dùng một lần hoặc cảnh báo rằng một phương thức xác thực đã thay đổi. Nếu chỉ lưu `emailSent = true`, ứng dụng không biết thư nào được gửi, gửi đến phiên bản địa chỉ nào, nhà cung cấp đã tiếp nhận hay đã giao, và lần gửi lại có tạo trùng hay không.

**Recovery notification entity** là thực thể quản lý một thông báo có mục đích xác định, gắn với sự kiện khôi phục và một đích nhận được chính sách cho phép. Nó theo dõi ý định thông báo, cách gửi và kết quả vận chuyển; nó không tự chứng minh người dùng đã kiểm soát tài khoản.

Trong SECURITY_AUTHENTICATION_ACCOUNT_RECOVERY, mô hình cần hỗ trợ khôi phục mật khẩu, MFA, passkey và thiết bị, đồng thời tránh làm lộ bí mật hoặc biến kênh thông báo thành đường chiếm đoạt tài khoản.

## 1. Xác định một bản ghi thông báo đại diện cho điều gì

Một cách định nghĩa rõ ràng là:

> Một notification đại diện cho một thông điệp của một sự kiện, với một mục đích, một kênh và một phiên bản đích nhận cụ thể.

Ví dụ, cùng một sự kiện hoàn tất khôi phục có thể tạo:

- Một cảnh báo email đến địa chỉ thông báo đã đăng ký.
- Một cảnh báo push đến thiết bị đủ điều kiện nhận.
- Một thông báo khác đến một địa chỉ đã được chính sách yêu cầu.

Đó là các notification khác nhau, có thể thành công hoặc thất bại độc lập.

Ngược lại, ba lần thử gửi cùng một email do lỗi tạm thời là ba delivery attempt của cùng notification. Không nên tạo ba sự kiện “khôi phục hoàn tất” để hợp thức hóa ba lần retry.

Cần phân biệt các thực thể:

| Thực thể | Trách nhiệm |
| --- | --- |
| Recovery event | Ghi nhận một sự kiện nghiệp vụ đã xảy ra |
| Recovery notification | Ý định gửi một thông điệp cụ thể cho một đích |
| Notification attempt | Một lần tương tác với hệ thống gửi |
| Provider receipt | Phản hồi hoặc callback từ nhà cung cấp |
| Recovery challenge | Bằng chứng được yêu cầu và quy tắc xác minh |
| Recovery transaction | Trạng thái của toàn bộ lần khôi phục |

Nếu email có chứa mã, mã thuộc cơ chế challenge. Notification chỉ là phương tiện vận chuyển nội dung được phép gửi.

## 2. Phân biệt hướng dẫn khôi phục và cảnh báo bảo mật

Hai loại thông điệp thường dùng cùng hạ tầng nhưng có mục đích khác nhau.

| Mục đích | Ví dụ | Điều cần tránh |
| --- | --- | --- |
| `RECOVERY_CHALLENGE` | Gửi mã hoặc liên kết dùng cho một bước xác minh | Gửi lại nội dung đã hết hạn hoặc gửi đến đích chưa được phép |
| `RECOVERY_STARTED_NOTICE` | Cảnh báo về một lần khôi phục khi chính sách yêu cầu | Tạo thư hàng loạt từ yêu cầu công khai không kiểm soát |
| `RECOVERY_COMPLETED_NOTICE` | Thông báo tài khoản vừa được khôi phục | Diễn đạt như người nhận đã chấp thuận sự kiện |
| `FACTOR_CHANGED_NOTICE` | Cảnh báo phương thức khôi phục hoặc MFA thay đổi | Chỉ báo cho một đích mới do chính người thay đổi vừa cung cấp |
| `RECOVERY_REVIEW_NOTICE` | Thông tin về bước xử lý thủ công | Tiết lộ hồ sơ hoặc dữ liệu nhận dạng không cần thiết |

Danh sách là ví dụ của một sản phẩm, không phải bộ loại thông báo bắt buộc cho mọi hệ thống.

[NIST SP 800-63B-4 về sự kiện tài khoản](https://pages.nist.gov/800-63-4/sp800-63b/events/) mô tả vai trò thông báo độc lập khi khôi phục tài khoản và các sự kiện liên quan, nhằm giúp chủ tài khoản phát hiện gian lận. Mô hình ứng dụng cần giữ được mối liên hệ giữa sự kiện thật và thông báo tương ứng.

Một cảnh báo bảo mật không nên chứa mật khẩu mới hoặc mã dự phòng. Nếu cần cung cấp cách báo cáo sự kiện không được nhận ra, hành động đó phải có thiết kế quyền và phạm vi riêng; không coi việc mở email là đủ để đảo ngược mọi thay đổi tài khoản.

## 3. Đích nhận phải có nguồn gốc và phiên bản

### 3.1. Không lấy địa chỉ tùy ý từ request

Một endpoint khôi phục công khai không được nhận trường `notificationEmail` rồi dùng địa chỉ đó để gửi thông tin nhạy cảm của tài khoản.

Đích nhận cần được xác định từ nguồn mà chính sách cho phép, chẳng hạn địa chỉ thông báo đã đăng ký, liên kết khôi phục đã xác minh hoặc thiết bị đã được ràng buộc phù hợp.

Với thay đổi email hoặc MFA, cần xác định các kênh nhận cảnh báo dựa trên trạng thái và chính sách của sự kiện, thay vì chỉ nhìn đích mới sau thay đổi.

Một phương tiện bị nghi đã xâm nhập có thể cần cách xử lý riêng. Không mặc định mọi kênh cũ đều an toàn, nhưng cũng không cho người gửi yêu cầu tự loại bỏ cảnh báo đến các kênh đã thiết lập.

### 3.2. Snapshot đích nhận

Giả sử thông báo được tạo lúc tài khoản dùng địa chỉ A. Trước khi worker gửi, tài khoản đổi sang B. Nếu worker luôn đọc “email hiện tại”, thông điệp có thể đi đến một đích khác với quyết định ban đầu.

Mô hình nên lưu:

```text
recipientBindingId
recipientBindingVersion
recipientSnapshotRef
recipientPolicyVersion
```

`recipientSnapshotRef` tham chiếu đến dữ liệu đích nhận được bảo vệ, ổn định cho notification đó. Nó không nhất thiết chứa địa chỉ rõ trong bảng chung.

Snapshot không có nghĩa phải gửi bất chấp mọi sự kiện mới. Trước khi gửi, chính sách có thể yêu cầu hủy một challenge nếu giao dịch hoặc đích liên quan đã bị thu hồi. Khi cần thông báo khác, tạo ý định mới có căn cứ; không âm thầm đổi người nhận của bản ghi cũ.

Không dùng địa chỉ đã che làm đích gửi hoặc khóa định danh. Chuỗi như `m***@example.com` chỉ phục vụ trình bày.

## 4. Các nhóm thuộc tính của notification

| Nhóm | Thuộc tính minh họa | Ý nghĩa |
| --- | --- | --- |
| Danh tính | `tenantId`, `notificationId`, `accountId` | Gắn thông báo với đúng phạm vi |
| Nguồn nghiệp vụ | `eventId`, `recoveryTransactionId`, `purpose` | Giải thích vì sao thông báo tồn tại |
| Người nhận | `recipientBindingId`, `recipientBindingVersion`, `recipientSnapshotRef` | Giữ quyết định đích nhận |
| Nội dung | `templateKey`, `templateVersion`, `locale`, `contentContextRef` | Dựng thông điệp nhất quán |
| Lịch gửi | `createdAt`, `nextAttemptAt`, `sendNotAfter` | Kiểm soát thời điểm thử gửi |
| Điều phối | `dispatchState`, `leaseOwner`, `leaseUntil`, `leaseGeneration` | Phối hợp worker |
| Kết quả vận chuyển | `deliveryState`, `providerMessageRef` | Theo dõi những gì nhà cung cấp đã xác nhận |
| Đồng thời | `rowVersion` | Phát hiện cập nhật trên dữ liệu cũ |

`contentContextRef` không nên là một JSON công khai chứa token thô, số điện thoại và thông tin thiết bị đầy đủ. Nếu phải giữ nội dung nhạy cảm để gửi hoặc retry, cần kho lưu trữ được bảo vệ, phạm vi đọc tối thiểu và thời hạn lưu phù hợp.

Template và locale nên được chốt theo lần thông báo. Retry vận chuyển không tự đổi loại thông điệp hoặc tính lại một thời hạn khác.

Nếu lưu thời điểm hết hạn của challenge để trình bày, đó là dữ liệu từ cơ chế challenge. Notification không được tự gia hạn challenge vì email gửi chậm.

## 5. Tách trạng thái gửi khỏi trạng thái giao nhận

Một cột `status = SENT` quá mơ hồ. Có thể tách hai chiều trạng thái.

### 5.1. Dispatch state

| Trạng thái | Ý nghĩa |
| --- | --- |
| `READY` | Có thể được worker nhận để xử lý |
| `LEASED` | Một worker đang giữ quyền xử lý có thời hạn |
| `RETRY_WAIT` | Lỗi tạm thời đã biết; chờ lần thử tiếp theo |
| `UNKNOWN_OUTCOME` | Chưa biết hệ thống gửi đã tiếp nhận hay chưa |
| `ACCEPTED` | Nhà cung cấp đã xác nhận tiếp nhận yêu cầu |
| `FAILED` | Không còn thử theo chính sách hiện tại |
| `CANCELLED` | Ý định gửi đã bị hủy trước khi hoàn tất gửi |

### 5.2. Delivery state

Một mô hình đơn giản có thể có:

```text
UNKNOWN
DELIVERED
UNDELIVERABLE
```

Đây là trạng thái theo bằng chứng vận chuyển mà hệ thống nhận được. Từng kênh có mức xác nhận khác nhau; không phải nhà cung cấp nào cũng có biên nhận giao nhận đáng tin cậy.

Các phân biệt quan trọng:

- Provider accepted không đồng nghĩa đã đến hộp thư.
- Delivered không đồng nghĩa người dùng đã đọc.
- Đã đọc không đồng nghĩa đúng chủ tài khoản đọc.
- Đã mở liên kết không đồng nghĩa giao dịch khôi phục đã hoàn tất.
- Một callback vận chuyển không phải bằng chứng xác minh MFA.

Với email mở ảnh hoặc liên kết bị phần mềm quét truy cập, dữ liệu “open” và “click” còn có thể phản ánh hoạt động tự động. Không dùng chúng để đặt `identityVerified = true`.

Một thông báo được tiếp nhận rồi bị bounce có thể giữ `dispatchState = ACCEPTED` và chuyển `deliveryState = UNDELIVERABLE`. Không sửa lịch sử thành “chưa từng được tiếp nhận”.

## 6. Ví dụ bảng quan hệ

Đoạn SQL theo cú pháp PostgreSQL dưới đây minh họa phần dữ liệu chung. Nó chưa bao gồm đầy đủ các bảng tham chiếu, kho nội dung và quy tắc chuyển trạng thái của một triển khai thực tế.

```sql
CREATE TABLE recovery_notification (
    tenant_id UUID NOT NULL,
    notification_id UUID NOT NULL,
    account_id UUID NOT NULL,
    event_id UUID NOT NULL,
    recovery_transaction_id UUID,

    purpose VARCHAR(40) NOT NULL,
    channel VARCHAR(16) NOT NULL,

    recipient_binding_id UUID NOT NULL,
    recipient_binding_version INTEGER NOT NULL,
    recipient_snapshot_ref UUID NOT NULL,

    template_key VARCHAR(100) NOT NULL,
    template_version VARCHAR(40) NOT NULL,
    locale VARCHAR(40) NOT NULL,
    content_context_ref UUID,

    dispatch_state VARCHAR(24) NOT NULL,
    delivery_state VARCHAR(24) NOT NULL DEFAULT 'UNKNOWN',

    created_at TIMESTAMPTZ NOT NULL,
    next_attempt_at TIMESTAMPTZ,
    send_not_after TIMESTAMPTZ,

    lease_owner VARCHAR(100),
    lease_until TIMESTAMPTZ,
    lease_generation BIGINT NOT NULL DEFAULT 0,

    provider_message_ref VARCHAR(200),
    row_version BIGINT NOT NULL DEFAULT 0,

    PRIMARY KEY (tenant_id, notification_id),

    UNIQUE (
        tenant_id,
        event_id,
        purpose,
        channel,
        recipient_binding_id,
        recipient_binding_version
    ),

    CHECK (recipient_binding_version > 0),
    CHECK (lease_generation >= 0),
    CHECK (row_version >= 0),

    CHECK (channel IN ('EMAIL', 'SMS', 'PUSH')),

    CHECK (dispatch_state IN (
        'READY',
        'LEASED',
        'RETRY_WAIT',
        'UNKNOWN_OUTCOME',
        'ACCEPTED',
        'FAILED',
        'CANCELLED'
    )),

    CHECK (delivery_state IN (
        'UNKNOWN',
        'DELIVERED',
        'UNDELIVERABLE'
    )),

    CHECK (
        (dispatch_state = 'LEASED'
            AND lease_owner IS NOT NULL
            AND lease_until IS NOT NULL)
        OR
        (dispatch_state <> 'LEASED'
            AND lease_owner IS NULL
            AND lease_until IS NULL)
    ),

    CHECK (
        send_not_after IS NULL
        OR send_not_after > created_at
    )
);
```

Ví dụ giới hạn ba kênh để dễ trình bày; danh sách thật cần theo chính sách sản phẩm. `purpose` cũng cần được kiểm soát bằng enum, bảng danh mục hoặc ràng buộc tương ứng.

Trong schema đầy đủ, các khóa ngoại và kiểm tra phạm vi phải bảo đảm tài khoản, sự kiện, giao dịch và snapshot người nhận cùng thuộc đúng tenant và tài khoản. Chỉ lưu các UUID cạnh nhau không tạo ra bảo đảm đó.

Khóa unique minh họa quy tắc “một thông báo cho một sự kiện, mục đích, kênh và phiên bản đích”. Nếu sản phẩm có yêu cầu khác, cần định nghĩa khóa nghiệp vụ tương ứng. Không đổi `eventId` ngẫu nhiên mỗi lần retry để vượt cơ chế chống trùng.

`sendNotAfter` là hạn bắt đầu một lần gửi theo chính sách, không phải bằng chứng rằng token còn hợp lệ khi người nhận mở thư. Giới hạn này còn phải được kiểm tra tại lúc dispatch.

## 7. Từng lần thử gửi là bản ghi riêng

Một notification có thể có nhiều attempt:

```text
NotificationAttempt
  tenantId
  notificationId
  attemptId
  attemptNumber
  leaseGeneration
  startedAt
  finishedAt
  outcome
  providerMessageRef
  sanitizedErrorCode
```

Có thể đặt ràng buộc duy nhất cho `tenantId + notificationId + attemptNumber` và khóa ngoại đến notification.

`outcome` nên phân biệt ít nhất:

- Được tiếp nhận.
- Bị từ chối tạm thời và biết chắc chưa tiếp nhận.
- Bị từ chối vĩnh viễn.
- Không biết kết quả do timeout hoặc mất kết nối.

Không lưu toàn bộ lỗi nhà cung cấp mà chưa lọc. Một thông báo lỗi có thể chứa địa chỉ nhận, URL hoặc nội dung đã gửi.

Số attempt là thông tin vận hành gửi tin, không phải số lần nhập sai mã. Retry email không được đặt lại giới hạn thử challenge.

## 8. Gắn thông báo với thay đổi nghiệp vụ bằng outbox

Một lỗi thường gặp:

```text
Lưu thay đổi tài khoản
Gọi nhà cung cấp gửi thông báo
```

Nếu tiến trình dừng sau bước đầu, thay đổi đã có nhưng thông báo bị mất. Đảo thứ tự cũng không giải quyết được: thư có thể được gửi dù thay đổi cuối cùng bị rollback.

Một cách thiết kế là ghi trong cùng giao dịch cơ sở dữ liệu:

```text
BEGIN
  Áp dụng thay đổi nghiệp vụ được phép
  Ghi sự kiện tài khoản
  Tạo các recovery notification cần thiết
  Tạo outbox record tham chiếu notification
COMMIT
```

Sau commit, bộ phận điều phối đọc outbox và chuyển việc đến worker gửi. Outbox không cần chứa token thô; có thể chỉ giữ định danh notification và thông tin điều phối tối thiểu.

[AWS Prescriptive Guidance về transactional outbox](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html) giải thích việc giải quyết lỗi ghi kép giữa cơ sở dữ liệu và hệ thống thông điệp, đồng thời lưu ý rằng bên nhận cần xử lý thông điệp trùng.

Một thiết kế có thể dùng:

```text
NotificationOutbox
  tenantId
  outboxId
  notificationId
  createdAt
  publishedAt
```

Cần phân biệt `publishedAt` của outbox với `ACCEPTED` của notification. Đẩy một công việc vào hàng đợi chưa có nghĩa nhà cung cấp email đã nhận yêu cầu gửi.

Outbox bảo đảm ý định được lưu cùng thay đổi trong phạm vi giao dịch cơ sở dữ liệu. Nó không tạo ra một giao dịch nguyên tử bao trùm nhà cung cấp bên ngoài.

Nếu chính sách yêu cầu một điều kiện thông báo trước khi cho phép bước tiếp theo, điều kiện đó cần được mô hình hóa rõ. Không đánh dấu đã đạt điều kiện chỉ vì một outbox record tồn tại.

## 9. Worker, lease và kết quả không xác định

### 9.1. Quyền xử lý có thời hạn

Worker cần nhận notification bằng thao tác nguyên tử theo trạng thái và thời điểm đủ điều kiện, rồi ghi:

```text
dispatchState = LEASED
leaseOwner = worker hiện tại
leaseUntil = hạn quyền xử lý
leaseGeneration = giá trị tăng mới
```

Sau đó commit quyền nhận việc trước khi gọi mạng, thay vì giữ khóa cơ sở dữ liệu suốt thời gian chờ nhà cung cấp.

Khi ghi kết quả, worker phải đối chiếu đúng thế hệ lease. Một worker cũ không được ghi đè kết quả của lượt xử lý mới.

Tuy nhiên, số thế hệ chỉ bảo vệ cập nhật nội bộ. Nó không tự ngăn nhà cung cấp nhận hai yêu cầu nếu worker cũ vẫn đang gọi mạng sau khi lease đã hết hạn.

### 9.2. Timeout không phải từ chối

Nếu worker gặp timeout sau khi gửi request, nhà cung cấp có thể đã tiếp nhận thông điệp. Chuyển ngay về `READY` rồi gửi tiếp có thể gây trùng.

Cách xử lý phụ thuộc vào contract nhà cung cấp:

- Dùng cùng khóa idempotency ổn định nếu dịch vụ hỗ trợ với điều kiện phù hợp.
- Tra cứu theo mã tham chiếu mà provider cho phép.
- Chờ callback có thể đối soát.
- Đưa về `UNKNOWN_OUTCOME` và áp dụng chính sách đối soát nếu chưa biết kết quả.

Không tự tuyên bố “exactly once” chỉ vì bảng có unique key. Ràng buộc nội bộ không kiểm soát toàn bộ tác dụng phụ ở hệ thống bên ngoài.

Lease hết hạn cũng cần được xử lý cùng trạng thái attempt. Nếu không chứng minh được lần trước chưa gửi, cần xử lý khả năng kết quả không xác định, thay vì luôn gửi lại.

### 9.3. Retry giữ nguyên ý nghĩa thông báo

Một lần retry vận chuyển phải giữ:

- Notification identity và khóa chống trùng phù hợp.
- Đích nhận theo quyết định đã chốt.
- Mục đích và phiên bản nội dung.
- Challenge hoặc token tương ứng nếu còn được phép sử dụng.

Worker gửi không tự sinh mã mới, kéo dài token hoặc đổi sang một địa chỉ khác để “cứu” thông báo thất bại.

Trước khi gửi challenge, cần kiểm tra hạn gửi và hiệu lực theo chính sách. Một cảnh báo về sự kiện đã xảy ra có thể vẫn cần gửi sau khi token liên quan hết hạn; vì vậy, không áp dụng chung một quy tắc hết hạn cho mọi purpose.

Hủy notification chưa gửi không thu hồi một email đã được provider tiếp nhận. Thu hồi token là trách nhiệm riêng của cơ chế khôi phục.

## 10. Callback, biên nhận và thứ tự sự kiện

Nhà cung cấp có thể gửi callback trùng, đến muộn hoặc khác thứ tự.

Một bảng biên nhận có thể ghi:

```text
ProviderReceipt
  providerAccountId
  providerEventId
  providerMessageRef
  receivedAt
  occurredAt
  mappedDeliveryState
```

Cần kiểm tra tính xác thực của callback theo cơ chế nhà cung cấp, chống xử lý lặp bằng định danh sự kiện phù hợp, rồi đối chiếu với bản ghi gửi mà hệ thống đã biết.

Không tin trực tiếp `accountId` hoặc `tenantId` trong một payload chưa được xác minh. Mối liên hệ tài khoản cần đi qua dữ liệu tương quan đã lưu và phạm vi provider được cấu hình.

Cũng không sắp thứ tự mọi cập nhật chỉ theo thời điểm callback đến. Một sự kiện cũ không nên hạ trạng thái mới một cách vô điều kiện. Quy tắc hợp nhất cần dựa trên loại sự kiện và ý nghĩa thật của từng kênh.

Biên nhận vận chuyển không được gọi thẳng thao tác hoàn tất khôi phục. Nếu nhận được “delivered”, hệ thống chỉ cập nhật bằng chứng giao nhận mà nó thực sự có.

## 11. Bảo vệ bí mật, tránh dò tài khoản và lạm dụng

Notification thường kết hợp thông tin tài khoản, địa chỉ nhận và nội dung có độ nhạy cảm cao. Cần phân tách:

| Dữ liệu | Cách xử lý |
| --- | --- |
| Token hoặc mã dùng một lần | Hạn chế nơi xuất hiện, bảo vệ khi cần lưu để vận chuyển, không ghi log |
| Địa chỉ nhận đầy đủ | Bảo vệ theo quyền truy cập và thời gian lưu |
| Nội dung template công khai | Quản lý phiên bản, không coi là bí mật |
| Ngữ cảnh dựng thư | Chỉ chứa dữ liệu cần thiết hoặc tham chiếu được bảo vệ |
| Mã lỗi vận hành | Chuẩn hóa và loại bỏ dữ liệu nhạy cảm |
| DTO trả cho giao diện | Chỉ công khai thông tin phù hợp với mức xác minh |

Không trả entity lưu trữ trực tiếp qua JSON. Các trường snapshot, provider reference hoặc nội dung có token không nên xuất hiện chỉ vì frontend yêu cầu trạng thái gửi.

[OWASP Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) khuyến nghị phản hồi nhất quán cho tài khoản tồn tại và không tồn tại. API công khai không nên phá nguyên tắc đó bằng một endpoint phụ cho biết thư đã được tạo hoặc giao đến tài khoản nào.

Các giới hạn gửi cần áp dụng cho yêu cầu mới và retry theo phạm vi phù hợp. Không cho client yêu cầu vô hạn thông báo cảnh báo đến một nạn nhân, cũng không cho retry nội bộ vượt mọi ngân sách vận chuyển.

Với cảnh báo bảo mật quan trọng, chính sách hạn chế lạm dụng cần tránh làm mất dấu các sự kiện độc lập. Gộp thông báo, thay kênh hoặc xử lý vận hành phải có quy tắc rõ ràng, không xóa sự kiện nguồn chỉ để giảm số thư.

## 12. Quan sát và lưu giữ

Có thể theo dõi tuổi của notification chưa xử lý, số kết quả không xác định, tỷ lệ provider từ chối và độ trễ từ sự kiện đến tiếp nhận.

Các số liệu cần có tên chính xác. “Provider acceptance rate” không nên được báo cáo như “tỷ lệ người dùng đã được cảnh báo”.

Nhật ký nên dùng định danh notification, event và attempt. Không ghi nguyên nội dung email hoặc địa chỉ đầy đủ trong mọi dòng log để tiện tìm kiếm.

Dữ liệu nhạy cảm dùng để dựng challenge có thể cần xóa sớm hơn metadata vận hành. Khi xóa, cần tính đến giới hạn retry và đối soát; không giữ token vô hạn chỉ vì notification chưa có callback cuối cùng.

Nếu thông báo thất bại sau khi thay đổi tài khoản đã commit, cần xử lý theo chính sách sự cố hoặc kênh thay thế được phép. Không tự hoàn nguyên mật khẩu hay MFA chỉ từ một lỗi gửi thư.

## 13. Ví dụ diễn tiến

Tài khoản hoàn tất một quy trình khôi phục MFA hợp lệ. Trong cùng giao dịch, hệ thống ghi sự kiện thay đổi, tạo notification đến các đích mà chính sách yêu cầu và ghi outbox.

Worker nhận một notification email, nhưng lần gọi provider bị timeout. Attempt được ghi là chưa biết kết quả; notification không bị tạo lại với một định danh ngẫu nhiên khác.

Sau đó, một callback hợp lệ cho biết provider đã tiếp nhận và giao thư. Hệ thống đối soát đúng notification, cập nhật kết quả vận chuyển và giữ lịch sử attempt trước đó. Nó không coi callback là một bước xác minh MFA bổ sung.

Một notification khác qua kênh push thất bại vĩnh viễn. Trạng thái đó được theo dõi riêng và xử lý theo chính sách. Nó không làm email đã giao trở thành thất bại, cũng không tự đảo ngược giao dịch khôi phục.

Mô hình lúc này trả lời được thông báo nào được yêu cầu, đích nào được chọn, đã thử gửi ra sao và biết chắc đến đâu về kết quả. Những câu trả lời đó giúp vận hành cơ chế khôi phục an toàn mà không trộn lẫn thông báo với quyền truy cập tài khoản.
