# Secret lease

## 1. Secret lease là gì?

Trong tích hợp secrets với Privileged Access Management (PAM), **secret lease** là quyền sử dụng một credential hoặc một tập credential trong khoảng thời gian do hệ thống cấp phát kiểm soát. Lease thường đi kèm định danh để theo dõi, thời hạn hiệu lực và khả năng gia hạn hoặc thu hồi. Credential có thể là tên đăng nhập/mật khẩu cơ sở dữ liệu, thông tin truy cập hạ tầng hoặc một credential ngắn hạn khác.

Ví dụ: dịch vụ đối soát cần đọc một số bảng nghiệp vụ trong 15 phút. Dịch vụ xác thực bằng danh tính workload; bộ cấp phát tạo tài khoản có đúng quyền đọc và trả về credential cùng metadata lease. Dịch vụ phải ngừng sử dụng credential khi lease hết hạn, bị thu hồi hoặc bị thay thế.

Lease trả lời ba câu hỏi:

- Credential này được cấp cho ai, để làm công việc gì và trên tài nguyên nào?
- Quyền sử dụng được cấp đến khi nào, trong điều kiện nào có thể tiếp tục?
- Khi không còn được phép sử dụng, hệ thống vô hiệu hóa quyền tại đâu và xác nhận bằng chứng nào?

Thời hạn lease là một phần của kiểm soát truy cập; nó không thay thế least privilege, phân tách môi trường, xác thực workload hay giám sát hành vi.

### 1.1. Lease không đồng nghĩa với bản thân secret

Một secret là dữ liệu nhạy cảm được dùng để xác thực. Lease là thông tin và cơ chế quản lý vòng đời quyền sử dụng dữ liệu đó. Một phản hồi cấp phát có thể chứa cả hai, nhưng chúng cần được xử lý khác nhau.

| Thành phần | Ý nghĩa | Cách xử lý trong tích hợp |
| --- | --- | --- |
| Credential | Giá trị dùng để xác thực vào hệ thống đích | Chỉ chuyển đến thành phần thực sự cần; không ghi log hoặc đưa vào ticket |
| Lease ID | Định danh lần cấp để renew, revoke và đối chiếu audit | Bảo vệ theo thiết kế; không giả định ID luôn vô hại hoặc tự nó đủ để gia hạn |
| TTL | Khoảng thời gian hiệu lực được cấp trong một phản hồi | Sử dụng giá trị thực tế được trả về, không chỉ TTL đã yêu cầu |
| Thời điểm hết hạn | Mốc kết thúc hiệu lực được xác định theo hợp đồng cấp phát | Dùng để lập lịch thay thế và dừng sử dụng trước hạn |
| Thuộc tính renewable | Cho biết lease có thể được xem xét gia hạn | Không xem đây là cam kết mọi lần gia hạn sẽ thành công |
| Version của secret | Phiên bản dữ liệu secret | Không tự chứng minh credential đã có thời hạn hoặc phiên bản cũ đã bị vô hiệu hóa |

Nếu ứng dụng được phép đọc một mật khẩu tĩnh trong 15 phút nhưng mật khẩu vẫn có hiệu lực tại hệ thống đích sau đó, việc hết hạn quyền đọc **không xóa bản sao mật khẩu đã đọc**. Muốn giới hạn khả năng dùng lại, cần cơ chế vô hiệu hóa hoặc thay đổi credential tại đích.

### 1.2. Quan hệ với PAM, JIT và JEA

Just-in-time (JIT) giới hạn khoảng thời gian được cấp quyền. Just-enough-administration (JEA) giới hạn tập thao tác được phép thực hiện. Lease có thể hỗ trợ khoảng thời gian JIT, còn phạm vi quyền phải được thực thi bằng role, policy và quyền tại hệ thống đích.

Một tài khoản quản trị toàn quyền với TTL ngắn vẫn có thể gây thiệt hại lớn trong thời gian còn hiệu lực. Ngược lại, một tài khoản chỉ có quyền phù hợp nhưng tồn tại vô thời hạn vẫn để lại quyền thường trực. Thiết kế PAM cần kiểm soát đồng thời **danh tính, phạm vi quyền và thời gian**.

Với tài khoản người dùng, lease nên liên kết được với phê duyệt, yêu cầu công việc hoặc phiên quản trị. Với tài khoản dịch vụ, lease nên liên kết với danh tính workload, chủ sở hữu, môi trường và mục đích sử dụng.

## 2. Xác định đối tượng thực sự được lease quản lý

Trước khi xây dựng client, cần biết lease kết thúc ở lớp nào.

### 2.1. Credential động

Bộ cấp phát tạo credential riêng cho một lần cấp hoặc một chủ thể, thường có quyền được ràng buộc bởi role. Cơ chế hết hạn và thu hồi có thể dựa vào khả năng native của hệ thống đích, thao tác của bộ cấp phát, hoặc kết hợp cả hai.

Ví dụ, tài khoản cơ sở dữ liệu được tạo riêng cho một instance dịch vụ. Khi tài khoản đó bị thu hồi, instance khác không bị ảnh hưởng nếu chúng sử dụng credential riêng và cấu hình không có tài nguyên phụ thuộc dùng chung.

Cần kiểm chứng rõ:

- Hệ thống đích có tự từ chối đăng nhập sau hạn hay cần tác vụ từ bộ cấp phát?
- Xóa hoặc khóa tài khoản có làm mất hiệu lực kết nối đã mở không?
- Giao dịch đang chạy được hoàn tất hay phải hủy?
- Nếu đích không truy cập được lúc thu hồi, yêu cầu được lưu và xử lý lại như thế nào?

Không thể suy ra các câu trả lời này chỉ từ việc API có trường TTL.

### 2.2. Credential tĩnh được checkout

Một số mô hình PAM cấp quyền checkout mật khẩu dùng chung trong một cửa sổ thời gian. Checkout hết hạn không đồng nghĩa mật khẩu cũ mất hiệu lực. Cần quy trình trả quyền, rotation và xác nhận hệ thống đích đã chấp nhận credential mới.

Nếu nhiều consumer dùng cùng một mật khẩu, rotation có thể ảnh hưởng tất cả consumer. Vì vậy, checkout lease và lease cho credential động có mức cô lập khác nhau; không nên áp dụng cùng giả định về thu hồi.

### 2.3. Lease của quyền gọi bộ cấp phát

Workload thường cần một token hoặc phiên xác thực để xin secret, renew và revoke. Vòng đời của quyền gọi bộ cấp phát và vòng đời của credential đích có thể khác nhau.

Token xác thực hết hạn có thể khiến workload không renew được lease. Việc thu hồi token có tự thu hồi các lease đã cấp hay không phụ thuộc mô hình quan hệ và cơ chế của nền tảng. Thiết kế phải xác nhận điều đó, không mặc định một trong hai hành vi.

## 3. Vòng đời lease và các bất biến cần giữ

Có thể mô hình hóa vòng đời tích hợp như sau:

~~~mermaid
stateDiagram-v2
    [*] --> Requesting
    Requesting --> Active: Cấp credential và lease thành công
    Requesting --> Denied: Không đủ quyền hoặc cấp phát thất bại
    Active --> Active: Gia hạn được chấp nhận
    Active --> Replacing: Chuẩn bị credential thay thế
    Replacing --> Active: Chuyển sang lease mới
    Active --> StopUse: Hết hạn hoặc có quyết định thu hồi
    Replacing --> StopUse: Không còn lease hợp lệ
    StopUse --> RevocationPending: Gửi yêu cầu vô hiệu hóa tại đích
    RevocationPending --> Closed: Xác nhận kết quả theo chính sách
    RevocationPending --> RevocationPending: Thử lại và đối soát có giới hạn
    Denied --> [*]
    Closed --> [*]
~~~

Sơ đồ thể hiện trạng thái quản lý của tích hợp, không khẳng định mọi nền tảng cung cấp đúng các tên trạng thái này. Thời điểm consumer dừng sử dụng, thời điểm control plane ghi nhận thu hồi và thời điểm hệ thống đích thực sự vô hiệu hóa credential có thể khác nhau.

Các bất biến nên được thiết kế từ đầu:

1. Consumer không tiếp tục dùng một lease mà nó đã biết là hết hạn hoặc bị thu hồi.
2. Gia hạn thất bại không tự kéo dài thời hạn hiện có.
3. Credential mới chỉ được kích hoạt sau khi đã kiểm tra đúng đích và đúng mức quyền cần thiết.
4. Thu hồi lease cũ chỉ tác động credential cũ; nếu rotation dùng chung identity hoặc password thì phải tính ảnh hưởng trước khi cutover.
5. Không đánh dấu thu hồi hoàn tất chỉ vì đã gửi request.
6. Mọi lần cấp, gia hạn, thay thế và thu hồi đều liên kết được với chủ thể và mục đích sử dụng mà không ghi giá trị secret.

Hết hạn quyền sử dụng và xóa bản sao credential trong ứng dụng đều cần thiết nhưng chưa đủ để chứng minh credential mất hiệu lực tại đích. Ngược lại, đích đã khóa credential cũng không tự chứng minh ứng dụng đã xóa toàn bộ bản sao.

## 4. TTL, gia hạn và giới hạn thời gian tối đa

### 4.1. TTL yêu cầu khác TTL được cấp

Giả sử consumer yêu cầu TTL 30 phút, nhưng policy của role chỉ cho phép 15 phút. Consumer phải chấp nhận hoặc từ chối kết quả dựa trên TTL được cấp; không được lập lịch như thể đã nhận 30 phút.

Thời hạn thực tế còn có thể bị ràng buộc bởi cửa sổ phê duyệt, giới hạn của hệ thống đích, giới hạn của danh tính cấp phát và chính sách riêng của backend. Đây là các điểm cần xác nhận khi tích hợp, không phải mọi backend đều áp dụng giống nhau.

Một phản hồi minh họa, không phải schema API của sản phẩm cụ thể:

~~~json
{
  "leaseId": "lease-example-8c42",
  "issuedAt": "2030-01-10T09:00:00Z",
  "expiresAt": "2030-01-10T09:15:00Z",
  "ttlSeconds": 900,
  "renewable": true,
  "target": "orders-db-test",
  "role": "reconcile-readonly",
  "credential": {
    "username": "<dynamic-username>",
    "password": "<secret-delivered-through-protected-channel>"
  }
}
~~~

Các giá trị trong ví dụ chỉ mô tả ý nghĩa. Tên field, mốc tính TTL và cách biểu diễn credential phải theo hợp đồng thực tế. Không in toàn bộ phản hồi API trong log để “tiện debug”.

### 4.2. Gia hạn không có nghĩa là cộng TTL vô hạn

Với một mô hình có giới hạn tuổi thọ tuyệt đối, gọi:

- \(t_0\): thời điểm cấp ban đầu.
- \(T_{max}\): tuổi thọ tối đa được phép kể từ lần cấp đó.
- \(t\): thời điểm backend xử lý gia hạn.
- \(\Delta\): thời lượng được đề nghị cho lần gia hạn.

Mốc hết hạn mới trong mô hình minh họa phải thỏa:

\[
t_{expiry,new} \leq \min(t + \Delta,\ t_0 + T_{max})
\]

Đây là ràng buộc thiết kế cho ví dụ, không phải công thức API chung. Backend có thể từ chối gia hạn hoặc cấp thời hạn ngắn hơn. Phản hồi đã được backend xác nhận mới là căn cứ cập nhật deadline.

Ví dụ lease được cấp lúc phút 0, TTL ban đầu 15 phút, tuổi thọ tối đa 45 phút:

| Thời điểm xử lý | Thao tác | Mốc hết hạn được cấp trong ví dụ |
| --- | --- | --- |
| Phút 0 | Cấp lease mới | Phút 15 |
| Phút 10 | Xin gia hạn thêm thời lượng 15 phút từ hiện tại | Phút 25 |
| Phút 20 | Gia hạn được chấp nhận | Phút 35 |
| Phút 30 | Gia hạn được chấp nhận nhưng bị chặn bởi giới hạn tuyệt đối | Phút 45 |
| Phút 40 | Xin 15 phút nhưng không thể vượt giới hạn | Không vượt phút 45; cần chuyển sang lease mới |

Không diễn giải “gia hạn 15 phút” thành “cộng 15 phút vào hạn cũ” nếu API không quy định như vậy. Không giả định mọi nền tảng đều có giới hạn tuổi thọ tuyệt đối giống ví dụ; cơ chế lease định kỳ hoặc mô hình khác phải được xử lý theo hợp đồng riêng.

Ngay cả khi **renewable=true**, backend vẫn có thể từ chối vì policy thay đổi, identity không còn quyền, lease đã kết thúc hoặc hệ thống đích không đáp ứng. Consumer cần cả luồng renew và luồng thay thế credential.

### 4.3. Lập lịch trước hạn và quản lý sai lệch đồng hồ

Không đợi sát thời điểm hết hạn mới renew. Cần dành thời gian cho độ trễ, retry, lấy lease thay thế và chuyển connection pool.

Một mô hình lập lịch đơn giản:

~~~text
usableDeadline = expiryDeadline - safetyMargin
renewAt = thời điểm nằm đủ sớm trước usableDeadline
retryBudget <= usableDeadline - now
~~~

Nếu tính theo TTL còn lại, có thể chọn một khoảng trước hạn, chẳng hạn khi đã dùng khoảng một nửa TTL, rồi thêm jitter có giới hạn để nhiều instance không renew đồng thời. Đây là tham số vận hành cần đo và điều chỉnh, không phải hằng số bảo mật áp dụng cho mọi workload.

Các nguyên tắc về thời gian:

- Lưu mốc UTC cho audit, đối chiếu sự kiện và điều tra.
- Dùng đồng hồ đơn điệu để đo khoảng chờ trong tiến trình, tránh timer bị ảnh hưởng bởi việc chỉnh đồng hồ hệ thống.
- Khi chuyển TTL hoặc mốc hết hạn thành deadline nội bộ, tính cả ý nghĩa TTL trong API, thời gian request và sai số đồng hồ.
- Không mặc định TTL bắt đầu từ lúc client nhận phản hồi nếu nó được tính từ lúc server cấp.
- Sau restart, không khôi phục deadline đơn điệu cũ; phải xác minh hoặc lấy lại lease theo cơ chế được phép.

Nếu thời gian hữu dụng còn lại không đủ cho một lần retry an toàn, chuyển sang phương án thay thế hoặc dừng sử dụng theo chính sách.

## 5. Tích hợp lease vào ứng dụng và connection pool

### 5.1. Phân công trách nhiệm rõ ràng

Có hai cách triển khai phổ biến ở mức kiến trúc:

| Cách tích hợp | Trách nhiệm chính | Điểm cần thiết kế |
| --- | --- | --- |
| Ứng dụng quản lý lease | Client trong ứng dụng xác thực, cấp, renew, thay thế và revoke | Đồng bộ giữa luồng xử lý, tránh renew trùng, phân loại lỗi |
| Agent hoặc thành phần trung gian quản lý lease | Thành phần trung gian lấy và duy trì credential, thông báo thay đổi cho ứng dụng | Kênh bàn giao secret, tính nhất quán khi cập nhật, reload và xác nhận ứng dụng đã sử dụng phiên bản mới |

Có agent không đồng nghĩa ứng dụng không cần xử lý hết hạn. Nếu ứng dụng chỉ đọc file một lần khi khởi động, agent có thể đã thay credential trên đĩa nhưng pool vẫn giữ credential cũ trong bộ nhớ.

Cần quy định rõ ai là owner của lease, ai được renew, ai được revoke, ai phát tín hiệu thay đổi và ai xác nhận cutover. Khi có nhiều bản sao ứng dụng, không để mọi bản sao tự quản lý một lease dùng chung nếu chưa có cơ chế phối hợp.

### 5.2. Quy trình thay credential có kiểm soát

Với credential động độc lập cho từng thế hệ, một quy trình thay thế có thể gồm:

1. Lấy lease B trong khi lease A vẫn còn đủ thời gian hữu dụng.
2. Kiểm tra B có thể xác thực vào đúng hệ thống đích và thực hiện phép thử tối thiểu, không gây thay đổi nghiệp vụ.
3. Tạo pool hoặc thế hệ kết nối mới dùng B.
4. Chuyển yêu cầu mới sang thế hệ B bằng cơ chế đồng bộ hoặc cập nhật tham chiếu nguyên tử.
5. Cho kết nối cũ của A hoàn tất trong thời gian drain giới hạn; không nhận yêu cầu mới vào A.
6. Đóng kết nối A còn lại theo chính sách khi hết thời gian drain.
7. Yêu cầu thu hồi A và xác nhận kết quả theo khả năng của backend.
8. Giải phóng tham chiếu tới credential A; tránh tạo thêm bản sao trong bộ nhớ, log hoặc file tạm.

Thời gian chồng lấn giữa A và B phải đủ cho chuyển đổi nhưng được giới hạn. Nếu cấp B làm thay đổi mật khẩu của cùng một tài khoản A, quy trình song song này có thể không phù hợp: cần thiết kế rotation và reload theo đúng tính chất tài khoản dùng chung.

Khi phát hiện nghi ngờ lộ credential, ưu tiên ứng phó sự cố có thể yêu cầu thu hồi ngay, đóng phiên hoặc chấp nhận gián đoạn thay vì drain như thay thế định kỳ.

### 5.3. Giả mã điều phối vòng đời

Giả mã sau mô tả luồng quyết định, không phải SDK hoặc chương trình có thể chạy trực tiếp:

~~~text
current = acquireLease(workloadIdentity, approvedRole)
validateLeaseMetadata(current)
activateAfterTargetCheck(current)
scheduleBefore(current.usableDeadline)

onScheduledMaintenance():
    snapshot = current

    if snapshot.isKnownRevoked() or now() >= snapshot.usableDeadline:
        stopNewWorkUsing(snapshot)
        replaceOrEnterControlledUnavailableState()
        return

    if snapshot.isRenewable() and replacementNotYetRequired(snapshot):
        result = tryRenewWithBoundedRetry(snapshot.leaseId)

        if result.isConfirmedSuccess():
            if current.stillRefersTo(snapshot):
                applyAuthoritativeLeaseMetadata(result)
            scheduleNextMaintenance()
            return

        if result.isTerminalFailure():
            beginReplacementWhileTimeRemains()
            return

        if result.isTransientOrAmbiguous() and retryFitsRemainingBudget():
            scheduleRetryWithJitter()
            return

    beginReplacementWhileTimeRemains()

onReplacementReady(candidate):
    validateLeaseMetadata(candidate)
    verifyTargetAndMinimumRequiredAccess(candidate)
    swapActiveGenerationAtomically(candidate)
    drainOldGenerationWithinDeadline()
    revokeOldLeaseAndTrackOutcome()

onShutdown():
    stopAcceptingNewWork()
    closeOwnedConnections()
    attemptOwnedLeaseRevocationWithinShutdownBudget()
~~~

Trong triển khai thật, cần chống xử lý phản hồi cũ: một renew đang chờ cho lease A có thể trả về sau khi ứng dụng đã chuyển sang B. Phản hồi của A không được ghi đè trạng thái của B.

Chỉ một tác vụ nên quyết định renew hoặc replace cho một lease trong cùng owner tại một thời điểm. Nếu không, nhiều luồng có thể đồng thời cấp lease mới, để lại tài khoản dư và làm mất dấu quan hệ giữa lease với consumer.

Shutdown hook chỉ hỗ trợ thu hồi chủ động; nó có thể không chạy khi tiến trình bị kill, máy mất điện hoặc mạng đứt. Cơ chế hết hạn, thu hồi phía cấp phát và đối soát vẫn phải hoạt động độc lập.

## 6. Xử lý lỗi và trạng thái không chắc chắn

### 6.1. Phân loại lỗi theo hậu quả

| Tình huống | Diễn giải | Hành động cần thiết |
| --- | --- | --- |
| Timeout khi renew | Chưa biết server có nhận và chấp nhận hay không | Không tự kéo dài deadline; kiểm tra trạng thái hoặc retry theo hợp đồng API |
| Backend tạm thời không truy cập được | Có thể còn lease hợp lệ trong một khoảng hữu hạn | Tiếp tục trong hạn nếu policy cho phép; retry có giới hạn và chuẩn bị thay thế |
| Lease không renewable hoặc bị từ chối dứt khoát | Renew không thể tiếp tục theo yêu cầu hiện tại | Lấy lease mới nếu vẫn được phép; không lặp renew vô hạn |
| Lease được xác nhận revoked | Credential không còn được phép sử dụng | Dừng dùng và xử lý kết nối liên quan ngay theo chính sách |
| Hết hạn mà chưa có credential thay thế | Không còn cơ sở cho quyền truy cập hiện tại | Dừng truy cập bằng credential đó; báo trạng thái suy giảm hoặc không sẵn sàng |
| Revoke không tới được hệ thống đích | Quyết định thu hồi đã có nhưng thực thi chưa được xác nhận | Giữ trạng thái pending, cảnh báo, đối soát và thử lại có kiểm soát |
| Timeout khi acquire | Có thể credential đã được tạo dù client chưa nhận được | Dùng idempotency hoặc cơ chế truy vết nếu backend hỗ trợ; theo dõi lease mồ côi |

Không đồng nhất mọi lỗi HTTP thành “thử lại sau”. Mã lỗi cụ thể và tính an toàn của retry phải được ánh xạ theo API thực tế.

Nếu acquire có thể tạo tác dụng phụ, retry mù có thể tạo nhiều tài khoản. Một request ID do client sinh giúp đối chiếu audit nhưng **không tự làm thao tác trở thành idempotent**; backend phải có cơ chế tương ứng.

### 6.2. Fail closed phải thể hiện bằng hành vi

Khi hết thời hạn được phép, ứng dụng cần ngừng tạo thao tác mới bằng credential đó. Tùy loại workload, nó có thể từ chối yêu cầu phụ thuộc tài nguyên, dừng nhận job mới hoặc chuyển sang trạng thái chờ có giới hạn.

Không triển khai “dự phòng” bằng cách:

- Chuyển sang tài khoản quản trị lâu dài được nhúng trong cấu hình.
- Bỏ qua deadline vì kết nối cũ vẫn chạy.
- Nới quyền cho role để renew dễ hơn.
- Coi lỗi xác thực là lý do ghi password ra log.

Quyền truy cập khẩn cấp cần một quy trình break-glass riêng với phê duyệt, giới hạn thời gian, giám sát và kiểm tra sau sử dụng. Nó không nên là nhánh tự động âm thầm trong client quản lý lease.

### 6.3. Không biến lỗi thành đợt cấp phát hàng loạt

Khi bộ cấp phát phục hồi sau sự cố, nhiều instance có thể cùng renew hoặc xin lease mới. Cần jitter, backoff có giới hạn, giới hạn concurrency và cơ chế hạn chế tốc độ.

Backoff không được vượt quá deadline sử dụng. Nếu thời gian retry theo backoff đã lớn hơn phần thời gian an toàn còn lại, ứng dụng cần chuyển trạng thái thay vì tiếp tục chờ trong khi dùng credential hết hạn.

## 7. Thu hồi lease và xác nhận tại hệ thống đích

Có ít nhất ba mốc cần phân biệt:

1. **Quyết định dừng quyền:** policy, người vận hành hoặc workflow xác định lease không còn được phép sử dụng.
2. **Ghi nhận ở control plane:** hệ thống cấp phát nhận yêu cầu và quản lý trạng thái thu hồi.
3. **Thực thi ở đích:** credential bị vô hiệu hóa và các phiên liên quan được xử lý theo yêu cầu.

Một API trả “accepted” có thể chỉ xác nhận nhận công việc bất đồng bộ. Cần xác định “revocation completed” có nghĩa gì trong hợp đồng: đã cập nhật metadata, đã thay đổi tài khoản tại đích, hay còn bao gồm đóng phiên.

### 7.1. Kết nối hiện hữu là một đối tượng kiểm soát riêng

Một phiên đã xác thực có thể có vòng đời khác credential tạo phiên. Không nên giả định đổi password, xóa lease hoặc khóa tài khoản luôn chấm dứt mọi kết nối hiện hữu.

Nếu yêu cầu an ninh là “sau thu hồi không còn thao tác đặc quyền”, phải kiểm chứng cả:

- Đăng nhập mới bằng credential cũ bị từ chối.
- Kết nối đã mở trước đó còn chạy được câu lệnh hay không.
- Transaction dài, phiên bị treo hoặc tác vụ nền được xử lý thế nào.
- Có cần cơ chế terminate session riêng ở đích không.
- Thời gian từ quyết định thu hồi đến khi hành vi truy cập thực sự chấm dứt.

Tính năng đóng phiên, quyền cần để thực hiện và ảnh hưởng giao dịch phụ thuộc hệ thống đích. Phép thử nên được thực hiện trên môi trường kiểm thử được cấp quyền.

### 7.2. Revoke pending phải quan sát được

Nếu backend không thể kết nối tới đích, ghi nhận lease ở trạng thái cần xử lý; không chỉ xóa bản ghi quản lý để làm báo cáo “sạch”.

Quy trình đối soát cần tìm được lease đến hạn nhưng chưa xác nhận vô hiệu hóa, credential tồn tại tại đích mà thiếu owner hợp lệ và lease không còn consumer sử dụng. Tùy kiến trúc, TTL native tại đích có thể giảm phụ thuộc vào control plane, nhưng cần kiểm chứng hành vi thực tế.

Trong ứng phó sự cố, thu hồi credential và điều tra hành vi là hai phần bổ sung cho nhau. Thu hồi không đảo ngược dữ liệu đã đọc, thay đổi đã thực hiện hoặc bí mật khác đã bị lấy trong thời gian credential còn hiệu lực.

## 8. Chọn thời hạn và quyền quản lý lease theo rủi ro

TTL nên xuất phát từ công việc và khả năng vận hành, không chỉ từ mong muốn “càng ngắn càng tốt”.

| Yếu tố | Câu hỏi cần trả lời | Ảnh hưởng đến thiết kế |
| --- | --- | --- |
| Độ nhạy cảm của quyền | Credential có thể tác động đến dữ liệu hoặc hạ tầng nào? | Quyền càng mạnh càng cần hạn chế thời gian, phạm vi và giám sát |
| Độ dài công việc | Job kéo dài bao lâu, có điểm dừng an toàn không? | Quyết định renew, thay credential giữa chừng và xử lý transaction |
| Năng lực backend | Có chịu được tần suất cấp và renew của toàn fleet không? | TTL quá ngắn có thể làm tăng tải và nguy cơ gián đoạn |
| Tốc độ chuyển credential | Ứng dụng reload hoặc thay pool mất bao lâu? | Cần đủ biên an toàn trước hạn |
| Phụ thuộc mạng | Mất kết nối tới bộ cấp phát trong bao lâu là kịch bản cần xử lý? | Xác định ngân sách retry và chế độ suy giảm trong thời hạn còn hiệu lực |
| Khả năng thu hồi tại đích | Có khóa credential và kết thúc phiên đáng tin cậy không? | Quyết định biện pháp bổ sung và cách đo thời gian thu hồi |
| Phê duyệt JIT | Cửa sổ cho phép kết thúc vào lúc nào? | Lease và renew không được vượt phạm vi đã được phê duyệt |

Các quyền trên hệ thống cấp phát cũng cần least privilege:

- Consumer chỉ được xin credential của role và môi trường được giao.
- Quyền renew hoặc revoke được ràng buộc theo cơ chế sở hữu của nền tảng.
- Không cấp quyền quản trị lease toàn hệ thống chỉ để consumer thu hồi lease của chính nó.
- Quyền gia hạn không được trở thành cách né phê duyệt lại.
- Danh tính dùng để tạo hoặc thu hồi tài khoản tại đích cần được bảo vệ, kiểm kê và giám sát riêng.

Trong môi trường nhiều tenant hoặc nhiều mức tin cậy, không chia sẻ lease giữa các phạm vi đó chỉ để giảm số lần gọi API.

## 9. Audit và chỉ số vận hành

Một sự kiện lease hữu ích nên cho phép trả lời “ai đã dùng quyền nào, vào lúc nào, vì lý do gì” mà không lộ credential.

Ví dụ sự kiện minh họa:

~~~json
{
  "eventType": "lease.renewal_denied",
  "timestamp": "2030-01-10T09:40:00Z",
  "correlationId": "request-example-54d1",
  "leaseReference": "protected-reference",
  "workload": "reconcile-job/test",
  "target": "orders-db-test",
  "role": "reconcile-readonly",
  "reasonCategory": "lifetime_limit",
  "action": "replacement_started"
}
~~~

Tên workload, role và lease reference cũng có thể tiết lộ cấu trúc hệ thống; áp dụng phân quyền, che dữ liệu và thời gian lưu phù hợp. Tham chiếu lease trong log cần đủ để đối chiếu nhưng không nhất thiết phải là ID đầy đủ.

Các chỉ số nên quan sát:

- Số lease đang hoạt động theo owner, role và môi trường.
- Thời gian hữu dụng còn lại của lease đang phục vụ.
- Tỷ lệ renew thành công, thất bại dứt khoát và lỗi tạm thời.
- Thời gian acquire, renew và chuyển sang credential mới.
- Số lần ứng dụng phải dừng truy cập vì không còn lease hợp lệ.
- Số lease thu hồi pending và tuổi của yêu cầu pending lâu nhất.
- Độ trễ từ quyết định thu hồi đến xác nhận thực thi ở đích.
- Số credential mồ côi phát hiện qua đối soát.

Ngưỡng cảnh báo cần gắn với thời gian còn lại để phục hồi. Cảnh báo khi credential đã hết hạn thường quá muộn để chuyển đổi êm.

Không dùng lease ID duy nhất của từng lần cấp làm nhãn metric có số lượng giá trị không giới hạn. Dùng nhãn ổn định cho tổng hợp; để chi tiết truy vết trong log hoặc kho audit được kiểm soát.

## 10. Bài thực hành: lease cho dịch vụ đối soát

### 10.1. Bối cảnh

Trong môi trường kiểm thử, dịch vụ đối soát cần đọc dữ liệu đơn hàng. Thiết kế minh họa có các điều kiện:

- Danh tính workload riêng cho dịch vụ và môi trường.
- Role chỉ được đọc tập dữ liệu cần cho đối soát; không có quyền DDL hoặc quản trị.
- Credential động riêng cho mỗi instance hoặc mỗi job tùy mô hình sở hữu đã chọn.
- TTL ban đầu 15 phút, tuổi thọ tối đa 45 phút theo policy của bài thực hành.
- Tác vụ bảo trì lease chạy đủ sớm để còn ngân sách retry và chuyển pool.
- Có kênh audit cho cấp phát, renew, thay thế và revoke.
- Không sử dụng dữ liệu thật hoặc credential production.

Các thời lượng trên chỉ là tham số lab. Hệ thống thật phải chọn theo rủi ro và số đo vận hành.

### 10.2. Các tình huống cần thực hiện

| Tình huống | Kết quả cần quan sát |
| --- | --- |
| Cấp lease và truy cập đúng phạm vi | Đọc dữ liệu cho phép thành công; thao tác vượt quyền bị từ chối |
| Xin TTL lớn hơn policy | Consumer sử dụng TTL thực tế backend cấp và lập lại lịch đúng |
| Gia hạn bình thường | Deadline được cập nhật từ phản hồi thành công, không làm đổi phạm vi quyền ngoài chính sách |
| Tiến gần tuổi thọ tối đa | Consumer chuẩn bị credential mới trước khi lease cũ không thể gia hạn đủ thời gian |
| Mất kết nối trong cửa sổ renew | Retry có giới hạn, có jitter, không vượt deadline hữu dụng |
| Mất kết nối đến sau khi lease hết hạn | Không phát sinh truy cập mới bằng credential hết hạn |
| Thu hồi chủ động | Có bằng chứng tại control plane và kiểm tra hành vi xác thực tại đích |
| Giữ một kết nối cũ khi revoke | Xác định rõ kết nối còn hoạt động hay đã kết thúc; áp dụng cơ chế bổ sung nếu cần |
| Ứng dụng restart | Không sử dụng mù credential cache và deadline cũ |
| Timeout khi acquire | Có đối soát lease có thể đã được tạo; không che giấu credential mồ côi |
| Tắt tiến trình đột ngột | Cơ chế hết hạn và xử lý phía cấp phát vẫn làm việc dù không có shutdown hook |

Tách riêng phép thử “hết hạn” khỏi phép thử “thu hồi chủ động”; hai đường thực thi có thể khác nhau. Với thu hồi bất đồng bộ, đo cả thời điểm request được chấp nhận và thời điểm hệ thống đích từ chối quyền thực sự.

### 10.3. Bằng chứng hoàn thành

Lưu lại timeline cấp, renew, thay thế, dừng sử dụng và xác nhận thu hồi. Ghi rõ sai lệch giữa mốc dự kiến với mốc quan sát, cách xử lý kết nối đang mở và trạng thái lease sau khi job kết thúc.

Bằng chứng không chứa password, bearer token, phản hồi API nguyên vẹn hoặc file dump bộ nhớ. Khi cần chứng minh credential cũ bị từ chối, chỉ lưu kết quả và định danh truy vết đã được bảo vệ.

## 11. Những hiểu nhầm cần tránh

**“Lease hết hạn thì secret tự biến mất ở mọi nơi.”** Lease không thể xóa ngược mọi bản sao đã được consumer lấy. Cần giảm việc sao chép, vô hiệu hóa tại đích và quản lý bản sao cục bộ.

**“Renewable nghĩa là có thể dùng mãi.”** Khả năng renew phụ thuộc policy, danh tính, trạng thái lease và khả năng backend. Consumer vẫn cần đường thay thế.

**“Revoke API thành công nghĩa là mọi phiên đã bị cắt.”** Phải biết response xác nhận đến lớp nào và kiểm tra hành vi của phiên hiện hữu.

**“TTL ngắn thay thế được least privilege.”** Credential quyền lớn vẫn nguy hiểm trong toàn bộ thời gian hiệu lực. Cần giới hạn cả quyền lẫn thời gian.

**“Lưu lease ID là đã có đủ quyền renew.”** Quyền gọi API renew phụ thuộc cơ chế xác thực và phân quyền; ID chỉ định danh đối tượng theo hợp đồng tương ứng.

**“Ứng dụng có agent nên không cần reload credential.”** Thành phần cấp phát và thành phần sử dụng phải phối hợp. Credential được cập nhật nhưng pool không reload vẫn gây lỗi hoặc giữ phiên cũ.

**“Retry càng lâu càng tốt.”** Retry cần phù hợp loại lỗi và thời gian hữu dụng còn lại. Không kéo dài quyền bằng cách bỏ qua hạn khi hệ thống gặp sự cố.

## 12. Tự kiểm tra kiến thức

1. Một mật khẩu tĩnh được đọc qua quyền truy cập có TTL 10 phút. Vì sao bản sao mật khẩu đó vẫn có thể là rủi ro sau phút thứ 10?
2. Consumer yêu cầu TTL 30 phút nhưng nhận 12 phút. Deadline nào phải điều khiển lịch renew và dừng sử dụng?
3. Renew bị timeout. Vì sao consumer không được tự cộng thêm thời gian vào deadline?
4. Một lease còn renewable nhưng đã gần giới hạn tuổi thọ tối đa. Ứng dụng cần chuẩn bị điều gì?
5. Khi chuyển từ credential A sang B, làm thế nào ngăn phản hồi renew muộn của A ghi đè trạng thái B?
6. Làm sao chứng minh thu hồi đã ngăn đăng nhập mới và đã xử lý các phiên tồn tại?
7. Vì sao shutdown hook không đủ để bảo đảm không còn credential mồ côi?
8. Cần những trường audit nào để đối chiếu lease với workload và yêu cầu JIT mà không lộ secret?

Một tích hợp secret lease hoàn chỉnh phải quản lý được quyền từ lúc cấp đến khi kết thúc: consumer biết deadline, có đường gia hạn và thay thế, dừng sử dụng đúng lúc, còn hệ thống cấp phát theo dõi được kết quả vô hiệu hóa tại đích. Đây là nền tảng để PAM giảm quyền thường trực và giữ được bằng chứng vận hành cho tài khoản dịch vụ cũng như các truy cập đặc quyền.
