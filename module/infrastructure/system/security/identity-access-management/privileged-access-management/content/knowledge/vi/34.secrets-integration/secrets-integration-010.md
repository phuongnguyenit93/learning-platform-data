# Xử lý secret manager outage

## 1. Vì sao sự cố secret manager là bài toán PAM?

Secret manager lưu trữ hoặc cấp phát các dữ liệu nhạy cảm như mật khẩu tài khoản dịch vụ, khóa API và credential truy cập hệ thống. Trong hệ thống quản lý truy cập đặc quyền (PAM), secret manager có thể tham gia vào việc cấp credential cho phiên quản trị, xác thực workload, luân chuyển mật khẩu và thu hồi quyền truy cập tạm thời. Khi thành phần này gián đoạn, ảnh hưởng không chỉ là ứng dụng không đọc được một giá trị cấu hình: tổ chức có thể mất khả năng mở phiên quản trị hoặc không chứng minh được credential nào vẫn còn hiệu lực.

Mục tiêu xử lý sự cố là giữ các nghiệp vụ được phép hoạt động trong giới hạn đã thiết kế, đồng thời bảo vệ least privilege, thời hạn quyền, khả năng thu hồi và bằng chứng kiểm toán. Không nên coi khả năng kết nối tới hệ thống đích là bằng chứng đủ để tiếp tục sử dụng một credential đặc quyền.

Ví dụ xuyên suốt bài: ứng dụng thanh toán lấy credential cơ sở dữ liệu qua secret manager. Một nhóm vận hành dùng PAM để mở phiên bảo trì trên cùng cơ sở dữ liệu. Khi secret manager mất kết nối trong 20 phút, ứng dụng đang chạy có thể còn connection hợp lệ, trong khi yêu cầu mở một phiên quản trị mới cần quyết định cấp quyền mới. Hai trường hợp này phải có chính sách riêng.

Sau bài học, người học cần phân biệt được các dạng gián đoạn, xác định hành động được phép trong chế độ suy giảm, thiết kế cache có giới hạn và lập runbook phục hồi mà không tạo quyền quản trị thường trực.

## 2. Xác định chính xác thành phần đang hỏng

Một thông báo “không lấy được secret” chưa đủ để kết luận toàn bộ secret manager bị ngừng hoạt động. Lỗi có thể nằm trên đường mạng, cơ chế nhận dạng workload, policy, chính hệ thống quản lý secret hoặc hệ thống đích sử dụng credential.

| Quan sát | Hướng điều tra ban đầu | Điều không nên suy diễn |
|---|---|---|
| Timeout tới endpoint | DNS, routing, proxy, firewall, tải dịch vụ | Credential chắc chắn đã hết hạn |
| TLS handshake thất bại | Chuỗi tin cậy, thời gian hệ thống, tên endpoint | Có thể bỏ kiểm tra chứng thư để phục hồi |
| Lỗi xác thực workload | Token, chứng thư, identity provider, cấu hình audience | Cần đổi mật khẩu tài khoản đích |
| Từ chối theo policy | Quyền đọc đường dẫn, identity, thay đổi policy | Đây là lỗi tạm thời nên cứ retry |
| Đọc được secret nhưng đăng nhập đích thất bại | Version credential, trạng thái rotation, khóa tài khoản đích | Secret manager còn hoạt động nghĩa là secret luôn đúng |
| Chỉ một vùng hoặc một client lỗi | Phạm vi mạng, endpoint, cấu hình client | Toàn hệ thống phải chuyển sang break-glass |

Các hướng điều tra này là điểm bắt đầu, không phải chẩn đoán chắc chắn. Cần đối chiếu log đã che dữ liệu nhạy cảm, trạng thái dependency và một phép thử có kiểm soát từ đúng vùng bị ảnh hưởng.

Tách riêng các khả năng của secret manager: đọc static secret, cấp dynamic credential, gia hạn lease, xác thực client, luân chuyển credential và ghi audit. Một khả năng có thể hỏng trong khi khả năng khác vẫn hoạt động. Chỉ báo health tổng quát không chứng minh rằng luồng cấp credential phục vụ PAM đã sẵn sàng.

## 3. Phân loại credential và quyết định fail-closed

### 3.1. Static secret và dynamic credential

**Static secret** thường là một giá trị tồn tại cho tới khi được thay đổi hoặc thu hồi, chẳng hạn mật khẩu của một tài khoản dịch vụ. Việc lấy được một bản sao trước sự cố không bảo đảm rằng bản sao đó vẫn là version đang được chấp nhận.

**Dynamic credential** được cấp theo yêu cầu với thời hạn hoặc lease xác định. Nếu không gia hạn được, client phải xử lý theo giới hạn hiện có. Không được tự kéo dài lease, tính lại thời hạn từ lần đọc cache gần nhất hoặc coi việc kết nối đích thành công là xác nhận rằng quyền đã được gia hạn.

Lease ở secret manager và trạng thái thực tế tại hệ thống đích không nhất thiết thay đổi đồng thời. Credential hết lease nhưng vẫn được đích chấp nhận có thể phản ánh việc thu hồi chưa hoàn tất. Đây là tình huống cần kiểm soát và đối soát, không phải lý do cho phép sử dụng quá hạn.

### 3.2. Quyết định theo hành động và mức đặc quyền

Fail-closed nghĩa là từ chối một hành động khi không chứng minh được các điều kiện cho phép hành động đó. Phạm vi áp dụng cần được ghi rõ cho từng luồng, thay vì đặt một cờ “cho phép khi lỗi” dùng chung.

| Hành động | Cách xử lý điển hình đã được thiết kế trước |
|---|---|
| Cấp credential quản trị mới | Từ chối khi thiếu xác thực, phê duyệt hoặc kiểm tra quyền bắt buộc |
| Mở rộng quyền hoặc phạm vi tài nguyên | Từ chối; outage không tạo thêm quyền |
| Gia hạn credential tạm thời | Chỉ coi là thành công sau xác nhận hợp lệ từ hệ thống có thẩm quyền |
| Tái sử dụng credential dịch vụ đã cache | Chỉ cho phép nếu policy riêng chấp nhận và mọi giới hạn còn hiệu lực |
| Tiếp tục phiên đặc quyền đang mở | Theo thời hạn phiên, khả năng giám sát và điều kiện thu hồi đã định trước |
| Khởi động workload chưa có credential | Chờ hoặc dừng có kiểm soát; không lấy secret từ nơi không được quản lý |
| Truy cập khẩn cấp phục hồi hạ tầng | Dùng quy trình break-glass đã chuẩn bị, có phạm vi và thời hạn riêng |

Nếu chính sách yêu cầu xác nhận thu hồi hoặc quyền hiện tại theo thời gian thực, mất kết nối tới nguồn xác nhận là đủ để chặn yêu cầu đó. Cache không thể thay thế một điều kiện bắt buộc mà hệ thống hiện không kiểm chứng được.

## 4. Thiết kế chế độ suy giảm trước khi có sự cố

### 4.1. Đặt giới hạn phục vụ rõ ràng

Với mỗi luồng sử dụng secret, cần xác định trước:

- Chủ sở hữu nghiệp vụ và chủ sở hữu credential.
- Hành động được phép tiếp tục, phạm vi tài nguyên và mức đặc quyền tối đa.
- Có cho phép dùng cache hay không; tuổi cache và thời gian suy giảm tối đa.
- Thời hạn credential, lease, token xác thực và phiên quản trị.
- Điều kiện dừng ngay, ví dụ nghi ngờ lộ credential, yêu cầu thu hồi hoặc mất khả năng ghi audit bắt buộc.
- Cách chặn cấp mới nhưng cho phép kết thúc công việc đang chạy trong giới hạn được duyệt.

Các giới hạn là cấu hình được phê duyệt trước, không được client tự nới rộng khi gặp lỗi. Một job đọc dữ liệu ít nhạy cảm và một phiên quản trị có khả năng thay đổi quyền không nên dùng chung chính sách suy giảm chỉ vì cùng đọc một secret manager.

### 4.2. Trạng thái hoạt động

Một mô hình vận hành dễ theo dõi gồm bốn trạng thái:

```text
NORMAL
  | dependency lỗi, đã xác nhận phạm vi
  v
DEGRADED_BOUNDED
  | hết giới hạn / có yêu cầu thu hồi / không đủ điều kiện kiểm soát
  v
BLOCKED

DEGRADED_BOUNDED hoặc BLOCKED
  | dependency phục hồi và vượt qua kiểm tra chức năng
  v
RECOVERING
  | đối soát version, lease, quyền và audit hoàn tất
  v
NORMAL
```

Không phải luồng nào cũng được vào `DEGRADED_BOUNDED`. Luồng yêu cầu xác thực quyền trực tiếp có thể chuyển từ `NORMAL` sang `BLOCKED`. Việc endpoint trả lời trở lại chỉ đủ để bắt đầu `RECOVERING`, chưa đủ để tuyên bố mọi credential và phiên đều an toàn.

## 5. Cache secret có giới hạn

### 5.1. Cache không phải bản vault thứ hai

Cache giúp giảm số lần gọi và có thể duy trì một số luồng khi dependency gián đoạn. Đổi lại, nó kéo dài thời gian tồn tại của bản sao secret, làm chậm nhận biết rotation hoặc revocation và tạo thêm nơi cần bảo vệ.

Chỉ cache đúng credential cần cho workload; khóa cache phải phân biệt identity, môi trường, tài nguyên, vai trò và version phù hợp. Không dùng một cache chung cho các workload khác quyền. Ưu tiên giới hạn bản sao trong bộ nhớ nếu kiến trúc cho phép; vẫn phải kiểm soát quyền đọc tiến trình, crash dump và các đường xuất dữ liệu chẩn đoán.

Nếu thiết kế bắt buộc lưu cache xuống đĩa, phải có phương án mã hóa, quản lý khóa giải mã, quyền file, thời gian lưu và phục hồi đã được đánh giá. Không để credential đặc quyền xuất hiện trong repository, image, file cấu hình dùng chung, log hay bản backup thiếu kiểm soát. Mã hóa cache không loại bỏ rủi ro nếu kẻ tấn công đồng thời truy cập được khóa và tiến trình giải mã.

### 5.2. Tính hạn sử dụng theo giới hạn ngắn nhất

Ví dụ một credential động được cấp lúc 09:00, hết hạn lúc 09:30. Chính sách cache cho phép giữ tối đa 10 phút từ lần xác minh có thẩm quyền gần nhất là 09:12. Tổ chức cho phép chế độ suy giảm tối đa 8 phút kể từ 09:15. Client dành biên an toàn 1 phút trước thời hạn credential.

```text
Giới hạn credential sau biên an toàn: 09:29
Giới hạn tuổi cache:                 09:22
Giới hạn chế độ suy giảm:            09:23

Thời điểm dừng dùng cache:           09:22
```

Đây là ví dụ chính sách, không phải thời lượng khuyến nghị dùng cho mọi hệ thống. Nếu có thêm thời hạn phê duyệt hoặc phiên, tiếp tục lấy giới hạn ngắn nhất. Cần chặn sớm hơn khi có sự kiện thu hồi hoặc nghi ngờ lộ lọt.

Tuổi cache phải tính từ một lần xác minh có thẩm quyền; đọc cache không làm mới tuổi cache. Sau khi tiến trình restart, không được mặc định tạo một cửa sổ suy giảm mới. Nếu không tái dựng được mốc thời gian tin cậy và trạng thái cần thiết, client phải từ chối sử dụng cache.

Thời gian tuyệt đối và đồng hồ đơn điệu cần được dùng phù hợp để tránh việc chỉnh đồng hồ làm kéo dài cửa sổ sử dụng. Nếu sai lệch thời gian vượt mức đã thiết kế, coi đó là điều kiện không còn chứng minh được hiệu lực credential.

### 5.3. Pseudocode kiểm tra cache

Đoạn dưới là mã giả mô tả quyết định chính sách, không phải API của một sản phẩm:

```text
function mayUseCachedCredential(request, entry, incident, policy, now):
    if not policy.allowsCachedUse(request.action):
        return DENY
    if policy.requiresOnlineAuthorization(request.action):
        return DENY
    if not exactIdentityAndScopeMatch(request, entry):
        return DENY
    if entry.revokedOrSuspectedCompromised:
        return DENY
    if not trustworthyTimeAndPersistedIncidentState(incident, now):
        return DENY
    if not requiredLocalControlsAvailable(request):
        return DENY

    deadline = minimum(
        entry.credentialNotAfter - policy.expirySafetyMargin,
        entry.lastAuthoritativeValidation + policy.maxCacheAge,
        incident.degradedStartedAt + policy.maxDegradedDuration,
        request.approvalNotAfter
    )

    if now >= deadline:
        return DENY

    recordDecisionWithoutSecret(request, entry.versionId, deadline)
    return ALLOW_EXISTING_SCOPE_ONLY
```

Với static secret không có thời hạn do nguồn cấp công bố, policy vẫn phải tạo giới hạn sử dụng cache rõ ràng. Không diễn giải “không có expiry” thành cho phép dùng vô hạn. Các mốc không áp dụng phải được biểu diễn rõ trong thiết kế; thiếu một mốc bắt buộc là lỗi, không được âm thầm bỏ qua.

## 6. Hạn chế lỗi dây chuyền khi dependency gián đoạn

### 6.1. Timeout và retry có ngân sách

Đặt timeout kết nối và timeout toàn yêu cầu trong ngân sách độ trễ của nghiệp vụ. Retry chỉ phù hợp với lỗi tạm thời và thao tác có tính an toàn khi lặp lại. Dùng exponential backoff có jitter, giới hạn số lần thử và tổng thời gian retry.

Lỗi cấp quyền bị từ chối không tự biến thành lỗi tạm thời. Retry liên tục không sửa được policy nhưng có thể làm tăng tải, che mất nguyên nhân và kích hoạt khóa tài khoản hoặc rate limit.

Đặc biệt thận trọng với yêu cầu cấp credential mới: một lần timeout có thể xảy ra sau khi server đã cấp credential nhưng trước khi client nhận phản hồi. Không lặp vô hạn thao tác cấp phát. Sử dụng cơ chế chống trùng do hệ thống hỗ trợ hoặc đối soát theo định danh yêu cầu; nếu chưa biết kết quả thì ghi nhận trạng thái chưa xác định và xử lý theo runbook.

### 6.2. Circuit breaker và chống dồn tải

Circuit breaker tạm dừng gọi dependency sau khi vượt ngưỡng lỗi, rồi cho một lượng nhỏ yêu cầu thăm dò khi đến thời điểm thử lại. Nó giảm tải và giúp ứng dụng phản hồi có kiểm soát, nhưng không cấp quyền bỏ qua kiểm tra bảo mật.

Khi hàng nghìn tiến trình cùng hết cache hoặc khởi động lại, chúng có thể đồng thời yêu cầu secret. Có thể giảm hiện tượng này bằng cách gộp các lần refresh đồng thời cho cùng identity/tài nguyên, làm mới sớm có jitter trong thời hạn cho phép và giới hạn concurrency. Không gộp yêu cầu giữa các identity khác quyền.

Sau phục hồi, mở lưu lượng theo từng nhóm client. Tránh restart toàn bộ workload cùng lúc để “xóa lỗi”, vì restart vừa làm mất cache hợp lệ vừa có thể tạo đợt tải lớn lên secret manager và identity provider.

### 6.3. Connection đang tồn tại

Một connection cơ sở dữ liệu đang mở có thể tiếp tục làm việc sau khi credential dùng để mở connection đã hết hạn hoặc bị thay đổi, tùy cơ chế của hệ thống đích. Vì vậy cần quản lý tuổi connection, tuổi phiên và khả năng đóng phiên riêng với TTL của secret.

Nếu quy định yêu cầu dừng quyền vào một thời điểm, không chỉ chặn lấy secret mới: phải có cách kết thúc session hoặc connection tương ứng. Khi không thể thực thi yêu cầu thu hồi, ghi nhận sai lệch, giới hạn truy cập tại lớp có thể kiểm soát và chuyển xử lý theo sự cố bảo mật phù hợp.

## 7. Break-glass cho phục hồi hạ tầng

Break-glass là một đường truy cập khẩn cấp được quản lý trước. Nó không phải thao tác sao chép credential quản trị từ máy cá nhân hoặc dùng chung mật khẩu được gửi qua chat khi secret manager ngừng hoạt động.

Đường truy cập này cần có dependency đủ độc lập để không bị cùng một lỗi vô hiệu hóa. Ví dụ, nếu muốn dùng credential khẩn cấp để sửa chính secret manager, cơ chế lấy credential đó không được chỉ phụ thuộc vào secret manager đang hỏng. Tuy vậy, sự độc lập phải được giới hạn và kiểm toán để không tạo một cửa hậu quản trị lâu dài.

Một quy trình điển hình gồm:

1. Người chỉ huy sự cố xác nhận nhu cầu, hệ thống đích và hành động phục hồi cụ thể.
2. Người có thẩm quyền phê duyệt hoặc kích hoạt cơ chế khẩn cấp đã được quy định; xác thực người thực hiện bằng phương án còn hoạt động.
3. Cấp quyền tối thiểu trong thời gian ngắn nhất khả thi, gắn với một cá nhân và mã sự cố. Dùng lệnh hoặc vai trò hạn chế theo JEA nếu cơ chế phục hồi hỗ trợ.
4. Giám sát, ghi lại thao tác và cảnh báo việc sử dụng tài khoản khẩn cấp. Nếu hệ thống audit trung tâm lỗi, thực hiện phương án ghi bằng chứng thay thế đã duyệt, có bảo vệ tính toàn vẹn.
5. Kết thúc phiên, thu hồi quyền tạm, luân chuyển credential đã sử dụng và xác minh tại hệ thống đích.

Nếu điều kiện kiểm soát bắt buộc của break-glass không đáp ứng được, không tự sáng tác đường truy cập khác trong lúc sự cố. Cần chuyển tới người có thẩm quyền theo kế hoạch ứng cứu đã có.

## 8. Runbook xử lý sự cố

### Giai đoạn A — Xác nhận và khoanh vùng

Xác nhận thời điểm bắt đầu, vùng ảnh hưởng, loại thao tác bị lỗi và dependency liên quan. Dùng request ID, loại lỗi và latency để điều tra; không yêu cầu người dùng dán secret hoặc token đầy đủ vào ticket.

Liệt kê workload, phiên đặc quyền và credential quan trọng bị ảnh hưởng. Xác định credential nào sắp hết hạn, job nào cần credential mới, job nào có thể kết thúc an toàn và phiên nào có nghĩa vụ thu hồi ngay.

### Giai đoạn B — Kích hoạt chính sách suy giảm

Chặn cấp mới hoặc gia hạn khi không đủ điều kiện. Chỉ cho phép cache theo policy của từng luồng, công bố thời điểm hết cửa sổ phục vụ và theo dõi thời gian còn lại. Hạn chế thay đổi policy, topology hoặc rotation không cần thiết trong khi chưa rõ trạng thái hệ thống.

Không đồng nhất việc tạm hoãn rotation thông thường với bỏ qua một yêu cầu rotation do lộ lọt. Trường hợp nghi ngờ credential bị lộ cần đường xử lý và thu hồi khẩn cấp riêng, kể cả phải chấp nhận gián đoạn nghiệp vụ.

### Giai đoạn C — Phục hồi dependency

Nhóm sở hữu secret manager xử lý nguyên nhân theo kiến trúc được hỗ trợ: có thể là mạng, chứng thư, identity, cụm dịch vụ hoặc storage. Chuyển endpoint hoặc failover chỉ dùng cấu hình đã kiểm thử, vẫn xác minh TLS, nguồn tin cậy, policy và tính nhất quán cần thiết.

Trong quá trình này, nhóm PAM theo dõi phiên và quyền đang tồn tại; nhóm ứng dụng thực hiện drain hoặc dừng có kiểm soát khi hết hạn. Không kéo dài TTL trên client để né thời điểm dừng đã công bố.

### Giai đoạn D — Đối soát trước khi trở về bình thường

Thử luồng chức năng bằng identity kiểm thử có quyền tối thiểu: xác thực, đọc hoặc cấp credential, sử dụng tại tài nguyên đích, xử lý lease và quan sát audit tương ứng. Phép thử cần đúng phạm vi bị ảnh hưởng, không dùng credential quản trị cao nhất chỉ để kiểm tra health.

Đối soát các yêu cầu chưa rõ kết quả, các lease đáng lẽ phải hết hạn, credential phát sinh trong cửa sổ sự cố và các lần rotation dang dở. Chỉ sau đó mới mở lại lưu lượng từng phần và kết thúc chế độ suy giảm.

### Giai đoạn E — Kết thúc và cải tiến

Thu hồi quyền khẩn cấp, kết thúc phiên không còn cần thiết, xử lý credential đã dùng trong break-glass và hoàn tất bằng chứng sự cố. Ghi nguyên nhân, phạm vi, thời gian gián đoạn, quyết định chính sách và hành động cải tiến. Tách việc dịch vụ đã phục hồi khỏi việc mọi rủi ro và sai lệch sau sự cố đã được xử lý xong.

## 9. Rotation dang dở và phục hồi credential

Một tình huống khó là secret manager bị gián đoạn đúng lúc đổi mật khẩu tài khoản dịch vụ. Có ít nhất ba trạng thái cần kiểm tra: giá trị tại hệ thống đích, version được lưu trong secret manager và version client đang cache. Chúng có thể chưa đồng bộ.

Không lặp rotation một cách mù quáng hoặc thử nhiều mật khẩu liên tục. Điều này có thể tạo thêm version chưa xác định hoặc gây khóa tài khoản. Dùng journal, audit và kiểm tra có kiểm soát của connector để xác định bước nào đã hoàn thành, theo cơ chế mà hệ thống hỗ trợ.

Sau khi xác minh version có hiệu lực, cập nhật client bằng luồng quản lý bình thường, làm mới connection theo từng đợt và xác nhận việc thu hồi version cũ tại đích. Nếu đích hỗ trợ cửa sổ chồng lấn credential, giới hạn cửa sổ đó theo policy; không giả định mọi hệ thống đều hỗ trợ hai version đồng thời.

Nếu phải phục hồi secret manager từ backup, cần xem backup có phản ánh credential tại đích hay không. Một snapshot lưu trữ có thể hợp lệ về kỹ thuật nhưng chứa mật khẩu cũ hoặc thiếu thông tin lease mới. Khôi phục dữ liệu không tự khôi phục tính nhất quán giữa secret manager, client và hệ thống đích.

## 10. Quan sát và bằng chứng kiểm toán

Theo dõi cả khả năng phục vụ lẫn giới hạn an toàn. Một dashboard chỉ hiển thị HTTP thành công có thể bỏ qua việc ứng dụng đang dùng cache sắp quá hạn hoặc credential không còn đáp ứng policy.

| Nhóm tín hiệu | Ví dụ cần theo dõi | Ý nghĩa vận hành |
|---|---|---|
| Dependency | Timeout, lỗi xác thực, lỗi cấp quyền, latency theo vùng | Khoanh vùng nguyên nhân và đường ảnh hưởng |
| Credential | Thời hạn còn lại, lỗi gia hạn, yêu cầu cấp phát chưa rõ kết quả | Dự báo thời điểm phải dừng và nhu cầu đối soát |
| Cache | Tuổi cache, số lần dùng trong suy giảm, yêu cầu bị chặn vì hết hạn | Kiểm chứng chính sách cache được thực thi |
| Phiên PAM | Phiên mới bị chặn, phiên sắp hết hạn, phiên chưa thu hồi được | Kiểm soát quyền quản trị còn tồn tại |
| Khẩn cấp | Kích hoạt break-glass, người sử dụng, hạn kết thúc | Đảm bảo ngoại lệ có người chịu trách nhiệm |
| Phục hồi | Kết quả thử chức năng, lệch version, audit chờ đồng bộ | Xác định điều kiện trở lại bình thường |

Bằng chứng nên có mã sự cố, thời gian, workload hoặc cá nhân, định danh tài nguyên không nhạy cảm, hành động, kết quả, lý do quyết định và policy áp dụng. Không ghi giá trị secret, private key, token, header xác thực hay toàn bộ phản hồi chứa credential. Định danh version cũng cần kiểm tra mức nhạy cảm trước khi ghi log.

Nếu phải ghi audit cục bộ, cần giới hạn dung lượng, bảo vệ quyền đọc/ghi, theo dõi lỗi ghi và có kế hoạch đồng bộ sau phục hồi. Khi hết khả năng ghi mà audit là điều kiện bắt buộc của một hành động, hành động đó phải bị chặn theo policy. Không âm thầm bỏ log để giữ hệ thống chạy.

## 11. Diễn tập có kiểm soát

Diễn tập giúp chứng minh hành vi thực tế trước khi dependency bị lỗi thật. Nên thực hiện trong môi trường hoặc phạm vi được phép, dùng credential kiểm thử và có phương án kết thúc diễn tập rõ ràng.

| Tình huống thử | Hành vi mong đợi |
|---|---|
| Timeout khi đọc secret | Retry có giới hạn; chỉ dùng cache nếu đủ điều kiện |
| Policy trả từ chối | Không rơi vào nhánh fallback cho lỗi mạng |
| Dynamic credential sắp hết hạn | Dừng trước giới hạn an toàn nếu không gia hạn thành công |
| Restart trong chế độ suy giảm | Không tạo cửa sổ cache hoặc outage mới để kéo dài quyền |
| Mất audit bắt buộc | Chặn đúng hành động phụ thuộc audit hoặc dùng phương án thay thế đã duyệt |
| Rotation bị ngắt giữa chừng | Phát hiện trạng thái chưa rõ; đối soát thay vì thử credential hàng loạt |
| Dependency vừa phục hồi | Mở lại theo đợt, kiểm tra version/lease và tránh dồn tải |
| Phiên cũ còn sống sau thu hồi | Phát hiện và thực hiện biện pháp kết thúc phiên theo thiết kế |

Kết quả cần ghi được cả thời điểm bắt đầu chặn và lý do. Một bài thử không đạt nếu ứng dụng chỉ “không crash” nhưng tiếp tục dùng credential quá hạn hoặc mất dấu vết truy cập.

## 12. Tình huống thực hành

Lúc 09:15, ứng dụng thanh toán mất kết nối secret manager. Credential hiện tại hết hạn 09:30; cache có hạn sử dụng đến 09:22 theo ví dụ ở trên. Một quản trị viên yêu cầu mở phiên bảo trì lúc 09:17, trong khi một phiên quản trị khác đã được phê duyệt tới 09:20.

Ứng dụng chỉ được tiếp tục trong phạm vi cache đã cho phép tới trước 09:22 và phải có kế hoạch drain/dừng phù hợp. Nếu xuất hiện yêu cầu thu hồi hoặc nghi ngờ lộ credential trước đó, giới hạn này không còn là căn cứ cho phép tiếp tục.

Yêu cầu mở phiên bảo trì mới bị từ chối nếu không thể hoàn tất các kiểm tra bắt buộc. Chỉ kích hoạt break-glass khi công việc thực sự phục vụ ứng cứu và đáp ứng quy trình khẩn cấp. Phiên đang có không được tự kéo dài qua 09:20; nếu mất kiểm soát bắt buộc trước đó thì phải xử lý theo điều kiện dừng của phiên.

Secret manager trả lời lại lúc 09:19. Nhóm vận hành chuyển sang `RECOVERING`, thử luồng cấp và sử dụng credential có kiểm soát, kiểm tra audit, đối soát các yêu cầu chưa rõ kết quả rồi làm mới client theo từng đợt. Thời điểm endpoint hồi phục không tự động hủy các giới hạn đang áp dụng cho phiên cũ.

Câu hỏi tự kiểm tra:

1. Vì sao việc cơ sở dữ liệu vẫn chấp nhận credential không chứng minh rằng credential được phép dùng tiếp?
2. Những mốc thời gian nào cần lấy giá trị nhỏ nhất để tính hạn dùng cache?
3. Tại sao không nên retry giống nhau cho lỗi mạng, lỗi cấp quyền và timeout sau yêu cầu cấp credential?
4. Nếu đã phục hồi từ backup nhưng version credential tại đích mới hơn, cần kiểm tra gì trước khi mở lưu lượng?
5. Bằng chứng nào cho thấy break-glass đã kết thúc cả về phiên truy cập lẫn credential?

Một thiết kế xử lý outage tốt cho phép trả lời rõ ba câu hỏi tại mọi thời điểm: ai còn được truy cập tài nguyên nào, quyền đó hết hiệu lực khi nào và tổ chức có bằng chứng nào để xác minh quyết định ấy.
