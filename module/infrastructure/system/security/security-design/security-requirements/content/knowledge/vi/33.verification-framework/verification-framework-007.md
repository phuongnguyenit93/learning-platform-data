# Yêu cầu session management — Đặc tả và kiểm chứng vòng đời phiên

## 1. Session management cần bảo vệ điều gì?

**Session management** là cơ chế liên kết các lần tương tác với một ngữ cảnh đã được xác thực, duy trì ngữ cảnh đó trong thời hạn được phép và làm mất hiệu lực khi điều kiện an toàn không còn đáp ứng.

Một lần đăng nhập thành công không giải quyết toàn bộ vòng đời. Hệ thống vẫn cần biết request sau thuộc phiên nào, phiên còn hiệu lực không, chủ thể còn được phép hoạt động không, quyền hiện hành là gì và phiên đã bị logout/thu hồi ở nơi khác chưa.

Trong chương **Verification framework**, thuộc module `SECURITY_SECURITY_DESIGN_SECURITY_REQUIREMENTS`, mục tiêu là chuyển “phiên phải an toàn” thành yêu cầu có phạm vi, điểm thực thi, ngưỡng đo, hành vi lỗi và bằng chứng kiểm thử. Bài liên kết xác thực, phân quyền, dữ liệu, logging và phục hồi với một vòng đời phiên có thể kiểm chứng.

Sau bài học, người học cần có khả năng:

- Xác định loại phiên, credential và ranh giới tin cậy của từng client/kênh.
- Đặc tả tạo, đổi ID, sử dụng, timeout, step-up, logout và thu hồi.
- Phân biệt cookie hết hạn với phiên phía server mất hiệu lực.
- Kiểm tra race, nhiều replica, cache, kết nối dài và trạng thái sau restore.
- Tạo ma trận yêu cầu–thiết kế–test–bằng chứng thay vì chỉ kiểm tra vài cookie flag.

Tên header, schema và ngưỡng trong bài là profile minh họa, không phải mặc định áp dụng cho mọi sản phẩm hay tuyên bố tuân thủ một tiêu chuẩn cụ thể. Nếu ánh xạ sang framework bên ngoài, cần chốt phiên bản, phạm vi và từng control với bằng chứng tương ứng.

## 2. Các khái niệm và profile cần phân biệt

| Khái niệm | Ý nghĩa | Điều không tự suy ra |
| --- | --- | --- |
| Session ID | Giá trị giúp bên nhận tìm hoặc xác minh ngữ cảnh phiên | Có ID đúng thì mọi thao tác nghiệp vụ đều được phép |
| Opaque session | ID không tự mang quyền có thể đọc từ client; trạng thái được quản lý ở server | Dữ liệu phía server tự an toàn nếu mọi replica/cache không kiểm tra thu hồi |
| Access token | Credential được chấp nhận để truy cập một tài nguyên/phạm vi | Xóa cookie hoặc thu hồi refresh token làm mọi access token mất hiệu lực ngay |
| Refresh token | Credential xin cấp tiếp access token theo hợp đồng | Được phép dùng như phiên quản trị không thời hạn |
| Authentication context | Chủ thể, cách/mức xác thực và thời điểm có bằng chứng | Field do client tự khai là bằng chứng đã xác thực mạnh |
| Step-up/reauthentication | Xác minh bổ sung cho thao tác cần bảo đảm cao hơn hoặc mới hơn | Tự động khởi động lại mọi timeout hoặc tăng mọi quyền |
| Session revocation | Quyết định làm mất quyền sử dụng phiên trong phạm vi xác định | Tác dụng đã được chấp nhận trước đó tự hoàn tác |
| Session cookie | Cookie dùng chuyên chở credential hoặc tham chiếu phiên | Đóng browser chắc chắn đã xóa phiên server hoặc mọi bản sao token |

Profile chính của bài là web application dùng opaque session ID qua cookie, với trạng thái authoritative ở server. Mobile/API client, SSO và token tự chứa có thể cần profile riêng; không áp cookie flag như một cơ chế bảo vệ cho một bearer token gửi theo cách khác.

Xác thực phiên và phân quyền nghiệp vụ là hai bước liên quan nhưng khác nhau. Phiên hợp lệ chỉ cung cấp chủ thể/context được tin cậy. API vẫn phải kiểm tra tenant, object, operation và trạng thái nghiệp vụ hiện hành.

## 3. Mô hình đe dọa và ranh giới tin cậy

### 3.1. Tài sản và giả định

Tài sản gồm session credential, ngữ cảnh xác thực, dữ liệu tài khoản/tenant, quyền tạo tác dụng nghiệp vụ, trạng thái thu hồi và bằng chứng audit.

Giả định tác nhân có thể gửi request tùy ý, chọn một ID trước đăng nhập, giữ lại token từng bị lộ, phát lại request, truy cập một tài khoản quyền thấp hoặc khai thác đầu vào/script không được kiểm soát. Lỗi đồng hồ, cache, replication và restore cũng có thể làm phiên cũ hoạt động trở lại.

Một session ID hợp lệ thường là bearer credential: ai có nó có thể sử dụng quyền mà cơ chế phiên cho phép trong những điều kiện tương ứng. Không giả định ID khó đoán là đủ nếu nó bị lộ qua URL, log, script hoặc thiết bị bị chiếm.

```text
Browser/client
  [dữ liệu và timestamp tự khai chưa đáng tin]
           |
           | kênh truyền được bảo vệ + credential theo profile
           v
Ingress / ứng dụng / session middleware
  [cookie/header parse, lookup, thời gian và auth context]
           |
           v
Session store + account/security state có thẩm quyền
  [ACTIVE/REVOKED, expiry, epoch, quyền hiện hành]
           |
           v
Authorization tại API / object / tenant / operation
           |
           v
Tác dụng nghiệp vụ + audit
```

Kết nối dài, worker xử lý sau và gateway cũng phải có ranh giới thực thi rõ. Kiểm tra phiên lúc thiết lập kết nối không tự bảo đảm mọi message gửi sau đó vẫn được phép.

### 3.2. Kịch bản đe dọa

| Risk ID | Kịch bản | Hậu quả | Hướng yêu cầu |
| --- | --- | --- | --- |
| SER-01 | Session ID có thể đoán hoặc suy ra từ user/time | Chiếm phiên không cần biết credential đăng nhập | CSPRNG, entropy và không dùng định danh dự đoán được |
| SER-02 | Attacker chọn ID trước login, host giữ nguyên sau login | Session fixation | Tạo ID mới và vô hiệu hóa binding cũ khi xác thực/đổi quyền |
| SER-03 | Token xuất hiện trong URL, log hoặc kênh không được bảo vệ | Lộ bearer credential và replay | Chuyên chở đúng profile, cookie/kênh an toàn, logging tối thiểu |
| SER-04 | Client sửa expiry/last activity hoặc heartbeat tự giữ phiên | Phiên tồn tại ngoài giới hạn dự kiến | Thời gian server và idle/absolute độc lập |
| SER-05 | Logout chỉ xóa cookie, token cũ còn hợp lệ | Sử dụng lại phiên sau logout | Invalidate server và kiểm tra ở mọi điểm thực thi |
| SER-06 | Replica/cache giữ state ACTIVE sau revoke | Tiếp tục có authorization mới | Ngân sách propagation/cache và test xuyên replica |
| SER-07 | Phiên giữ quyền cũ sau khóa tài khoản/đổi quyền | Đọc/ghi ngoài quyền hiện hành | Account state/epoch và authorization hiện hành |
| SER-08 | Cookie được gửi theo request không do người dùng chủ động | CSRF với tác dụng dưới danh tính nạn nhân | Cơ chế CSRF và kiểm tra nguồn/request phù hợp |
| SER-09 | XSS đọc token hoặc dùng browser gửi request có cookie | Chiếm phiên hoặc hành động trong phiên | Hạn chế đọc credential và kiểm soát XSS/đầu vào/sink độc lập |
| SER-10 | Step-up tự khai hoặc proof quá cũ | Thao tác nhạy cảm thiếu xác thực cần thiết | Auth context/độ mới có nguồn và ràng buộc thao tác |
| SER-11 | Refresh/retry hoặc login đồng thời tạo state không nhất quán | Phát hành quyền lặp, vượt quota hoặc làm sống token cũ | Atomic state transition và hợp đồng concurrent/replay |
| SER-12 | WebSocket/stream tiếp tục sau khi phiên hết hạn | Duy trì dữ liệu/tác dụng quá hạn | Kiểm tra message hoặc đóng kết nối trong ngân sách |
| SER-13 | Restore mang lại phiên/epoch trước thu hồi | Quyền cũ hoạt động trở lại | Khôi phục state thu hồi đúng hoặc buộc xác thực lại |
| SER-14 | Tin IP/User-Agent như danh tính phiên | Khóa nhầm người dùng hoặc bỏ lọt attacker cùng mạng | Tín hiệu rủi ro bổ sung, không thay credential/context |

### 3.3. Bất biến bảo mật

1. Chỉ credential do hệ thống cấp trong đúng profile được gắn với ngữ cảnh phiên hợp lệ.
2. Đăng nhập/đổi đặc quyền không giữ lại quyền sử dụng một ID đã bị fixation theo hợp đồng.
3. Không có authorization mới từ phiên quá hạn, bị thu hồi hoặc tài khoản không còn được phép, sau giới hạn hiệu lực đã công bố.
4. Hoạt động không được phép và tín hiệu do client tự khai không tự kéo dài tuổi phiên.
5. Phiên hợp lệ không thay quyền object/tenant hay bằng chứng step-up còn mới.
6. Lỗi hạ tầng và restore không tự chuyển phiên chưa xác minh thành ACTIVE.

## 4. Hồ sơ yêu cầu cho từng loại phiên

| Nhóm | Nội dung cần chốt |
| --- | --- |
| Client/kênh | Browser, mobile, API, SSO, gateway, WebSocket; profile nào dùng credential nào |
| Tạo phiên | Điều kiện auth thành công, nguồn ID, dữ liệu anonymous được di chuyển nếu có |
| Chuyên chở | Cookie/header phù hợp, origin/host/path, bảo vệ đường truyền và kênh bị cấm |
| State | Authoritative store, lookup, auth time, last activity, absolute/idle deadline và epoch |
| Quyền | Subject, tenant, auth strength, operation cần step-up và nguồn quyền hiện hành |
| Hết hiệu lực | Logout một phiên/tất cả phiên, khóa tài khoản, credential reset, đổi quyền và revoke |
| Phân tán | Replica/cache/gateway, kết nối dài, độ mới state và ngân sách chặn authorization mới |
| Concurrency | Login, rotate, refresh, activity và logout cạnh tranh; giới hạn phiên đồng thời |
| Dữ liệu/audit | Secret lưu ở đâu, metadata nào được log, quyền xem/quản lý phiên |
| Phục hồi | Session store lỗi, nguồn thời gian lỗi, restore, policy revision và điều kiện mở lại |

Thư viện/framework có session middleware không tự giải quyết những quyết định này. Cần kiểm tra cấu hình và hành vi có hiệu lực, kể cả khi gateway và ứng dụng cùng tham gia xác minh.

## 5. Profile thời gian và vòng đời minh họa

### 5.1. Các ngưỡng của ví dụ

| Thuộc tính | Giá trị minh họa | Điều kiện áp dụng |
| --- | --- | --- |
| Session ID | 32 byte ngẫu nhiên từ CSPRNG, biểu diễn base64url không padding | ID opaque do server cấp, không chứa user/role/tenant có thể tự khai |
| Idle timeout | 20 phút | Từ hoạt động hợp lệ thuộc loại được server xác định là gia hạn idle |
| Absolute lifetime | 8 giờ | Từ auth time/anchor của phiên; traffic hoặc rotate ID không tự reset |
| Step-up freshness | 5 phút | Cho operation nhạy cảm theo proof được xác minh, đồng thời phiên vẫn phải hợp lệ |
| Revocation bound | Không quá 30 giây từ commit revoke tới chặn authorization mới ở mọi điểm trong phạm vi | Phải tính cache, replica, gateway và kênh kết nối dài |
| Cache quyết định allow | Tối đa 5 giây và chỉ khi bằng chứng còn đủ tin cậy | Không làm fallback ACTIVE vô hạn khi store không đọc được |
| Phiên đồng thời | Tối đa 5 phiên ACTIVE cho một tài khoản theo phạm vi đã chốt | Kiểm tra/cấp slot nguyên tử xuyên các replica |

Các giá trị là quyết định rủi ro của ví dụ, cần được chủ dịch vụ phê duyệt. Sản phẩm có thể cần profile khác; thay ngưỡng phải kiểm tra lại test biên và khả năng thu hồi.

### 5.2. Idle và absolute không thay thế nhau

Ký hiệu:

```text
auth_at          = mốc xác thực/anchor phiên do server tạo
last_activity_at = hoạt động hợp lệ cuối được server công nhận
now              = thời điểm đáng tin tại điểm quyết định

absolute_due = auth_at + 8 giờ
idle_due     = last_activity_at + 20 phút

Chỉ đạt điều kiện thời gian khi:
    now < absolute_due
    và now < idle_due
```

Tại đúng một trong hai deadline, phiên không còn đạt điều kiện thời gian của profile này. Không làm tròn hoặc cắt phần lẻ để nhận thêm thời gian ngoài chủ đích.

Request bị từ chối, ping/heartbeat hoặc một field `interactive=true` do client tự gửi không tự gia hạn idle. Server cần định nghĩa loại hoạt động nào được tính và cập nhật có kiểm soát. Một attacker có token hợp lệ vẫn có thể tạo hoạt động được phép; idle timeout không ngăn mọi trường hợp sử dụng token bị lộ, nên vẫn cần absolute lifetime và thu hồi.

Rotate ID chỉ thay credential/binding theo hợp đồng, không tự biến `auth_at` thành bây giờ. Nếu policy cho phép bắt đầu vòng đời mới sau full reauthentication, cần chứng cứ xác thực mới và quyết định rõ; step-up cho một operation không mặc nhiên làm mới mọi clock.

### 5.3. Vòng đời ở server

```text
Chưa có phiên xác thực
  → xác thực thành công + tạo binding/ID mới
  → ACTIVE
       ├→ hoạt động hợp lệ: cập nhật idle có giới hạn
       ├→ step-up/đổi quyền: transition + rotation theo policy
       ├→ idle hoặc absolute hết hạn: không được authorize mới
       ├→ logout/revoke/account event: REVOKED
       └→ state không đủ tin cậy: chặn theo policy, không suy thành ACTIVE
```

Xóa một row quá hạn để dọn dữ liệu và từ chối sử dụng phiên quá hạn là hai việc khác nhau. Không chờ job cleanup chạy mới coi deadline có hiệu lực. Bằng chứng thu hồi/epoch cần được giữ đủ cho mọi credential hoặc bản sao state còn có thể xuất hiện theo hợp đồng.

## 6. Bộ yêu cầu có thể kiểm chứng

| ID | Yêu cầu | Owner | Bằng chứng đạt |
| --- | --- | --- | --- |
| SMR-01 | Mỗi client/kênh phải có profile phiên, credential, nguồn state/time, auth context, lifecycle và điểm thực thi được phê duyệt. | Kiến trúc/IAM | Danh mục browser/API/gateway/kết nối dài và hợp đồng profile đầy đủ, không bỏ kênh phụ |
| SMR-02 | ID opaque phải do server cấp từ CSPRNG; profile ví dụ dùng 32 byte ngẫu nhiên, không suy từ user/time/counter. Không tự tạo phiên theo ID do client chọn. | Ứng dụng/IAM | Kiểm tra nguồn sinh/biểu diễn và xử lý unknown ID; lấy mẫu ID không được dùng như bằng chứng duy nhất về entropy |
| SMR-03 | Credential chỉ đi qua kênh/profile được phép. Cookie ví dụ có Secure, HttpOnly, SameSite phù hợp, host/path đúng; không truyền ID trong URL hoặc log. | Ứng dụng/browser | Kiểm tra response/request qua đúng browser/proxy và các kênh log/trace; không có credential trên đường bị cấm |
| SMR-04 | Sau login và transition đặc quyền theo policy, phải tạo binding/ID mới, vô hiệu binding cũ phù hợp và không giữ fixation. | IAM/ứng dụng | ID được đặt trước login không trở thành phiên xác thực; token cũ không dùng được sau transition có hiệu lực |
| SMR-05 | Idle 20 phút và absolute 8 giờ phải được server thực thi độc lập; tại deadline từ chối. Chỉ hoạt động hợp lệ được duyệt mới gia hạn idle, không reset absolute vì traffic/rotation. | Ứng dụng/nền tảng | Test ngay trong/đúng/ngay ngoài cả hai biên, ping, request bị từ chối và cập nhật activity cạnh tranh |
| SMR-06 | Logout/revoke phải vô hiệu phía server và chặn authorization mới trên mọi replica/gateway trong 30 giây từ commit theo profile. Cache allow tối đa 5 giây không được gia hạn mù khi state không đủ mới. | IAM/nền tảng | Replay token cũ ở mọi điểm sau cutoff; đối chiếu revoke commit, cache/state và quyết định thực tế |
| SMR-07 | Phiên hợp lệ vẫn phải qua account state, quyền hiện hành, tenant/object và điều kiện nghiệp vụ; không tin role/tenant client tự khai. | Ứng dụng/IAM | Tài khoản khóa, role cũ, đổi tenant/object và API ngoài quyền đều không tạo tác dụng trái phép |
| SMR-08 | Operation cần step-up phải kiểm chứng mức/phương thức và proof còn mới theo policy; ví dụ freshness dưới 5 phút, phiên vẫn hợp lệ và proof ràng buộc đúng chủ thể/context. | IAM/chủ ứng dụng | Proof giả, sai user/context, tương lai/quá cũ hoặc phiên hết hạn không cho operation đi qua |
| SMR-09 | Với browser cookie, request tạo tác dụng phải có chống CSRF/kiểm tra nguồn phù hợp; cookie flag không thay kiểm soát CSRF hoặc XSS. | Ứng dụng/browser | Test request cross-site, nguồn không được phép, thiếu/sai token/context và XSS-related sinks theo phạm vi |
| SMR-10 | Credential phải được bảo vệ khi lưu/truy cập; profile opaque có thể lưu digest lookup thay raw ID, metadata chỉ được sửa bởi dịch vụ có quyền. Không công bố bearer qua audit/quản lý phiên. | IAM/dữ liệu | Kiểm tra store, backup, API danh sách phiên, log/debug; không thấy raw ID/secret ở nơi bị cấm |
| SMR-11 | Giới hạn 5 phiên ACTIVE/tài khoản trong ví dụ phải có phạm vi và xử lý nguyên tử; khi vượt, policy nêu từ chối hay thu hồi phiên nào. | IAM/nền tảng | Login đồng thời qua nhiều replica không vượt quota; danh sách/quản lý phiên không lộ session credential |
| SMR-12 | Nếu hỗ trợ refresh, remember-me hoặc SSO, phải đặc tả lifetime, rotation/replay, phạm vi logout/revoke và phụ thuộc bên ngoài. Không tuyên bố stateless token bị revoke tức thì chỉ vì cookie bị xóa. | IAM/tích hợp | Token cũ, refresh đồng thời/replay và logout local/upstream được kiểm tra đúng hợp đồng |
| SMR-13 | WebSocket/stream/kênh dài phải kiểm tra quyền tiếp tục hoặc đóng trong bound đã duyệt khi expiry/revoke; heartbeat không tự kéo dài phiên. | Nền tảng/ứng dụng | Kết nối mở trước logout không tiếp tục đọc/ghi trái policy sau cutoff; kiểm tra message và quyền hiện hành |
| SMR-14 | Khóa tài khoản, reset credential/MFA hoặc thay quyền phải có quy tắc thu hồi/epoch/rotation rõ cho các phiên liên quan. | IAM/chủ tài khoản | Phiên/role snapshot cũ không hoạt động ngoài chính sách; cấp phiên mới cần proof xác thực phù hợp |
| SMR-15 | State/time/configuration không đủ tin cậy phải đi luồng lỗi, không fallback authenticated/ACTIVE hoặc dựa vô hạn vào cache. | Nền tảng/IAM | Tiêm store lỗi, stale cache, thời gian sai và record không hợp lệ; không tạo authorization thiếu bằng chứng |
| SMR-16 | Audit/metric phải phân biệt create/rotate/expire/revoke/deny/step-up, gắn reference an toàn và policy revision, không log credential hoặc dữ liệu nhạy cảm dư thừa. | Vận hành/bảo mật | Truy vết được lifecycle và latency revoke; log không có cookie/token/CSRF secret có thể dùng lại |
| SMR-17 | Yêu cầu phiên phải được kiểm chứng trên mọi điểm thực thi trong phạm vi, có test dương/âm, race và topology triển khai. | QA/kiến trúc | Bằng chứng API/browser/proxy/replica/kênh dài, không chỉ cấu hình middleware hoặc unit test |
| SMR-18 | Restore phải bảo toàn tính đúng của revocation/epoch/time; nếu không chứng minh được, không phục hồi ACTIVE một cách mù quáng và có luồng yêu cầu xác thực lại. | Vận hành/IAM | Snapshot trước logout/reset không làm phiên cũ sống lại; ứng dụng phục hồi với policy hiện hành |

### 6.1. Mẫu đặc tả chi tiết cho timeout

```text
ID: SMR-05
Mục tiêu: không nhận authorization mới từ phiên ngoài tuổi được phép
Phạm vi: web opaque session của profile minh họa
Nguồn thời gian: server/nguồn state đủ tin cậy theo thiết kế
Anchor: auth_at gắn với proof xác thực, không lấy từ client
Hoạt động: last_activity_at chỉ do server cập nhật cho loại request được phép
Điều kiện thời gian:
  now < auth_at + 8 giờ
  now < last_activity_at + 20 phút
Không đạt:
  - Không tạo authorization mới bằng phiên đó
  - Thực hiện luồng xác thực lại/lỗi theo profile
  - Audit reason phân loại, không ghi session credential
Rotation thường lệ: không tự thay auth_at
Proof: test biên, record/epoch, quyết định và tác dụng thực tế
Owner: IAM, ứng dụng và nền tảng
```

Đây là điều kiện thời gian, chưa đủ để chứng minh phiên hợp lệ: state, account, thu hồi, auth strength và authorization vẫn phải được kiểm tra.

## 7. Tạo phiên, rotation và chuyên chở credential

### 7.1. Login không giữ fixation

Một luồng minh họa:

```text
1. Kiểm tra request và cơ chế chống tấn công phù hợp luồng xác thực.
2. Xác minh credential/proof theo policy, kể cả bước bổ sung nếu bắt buộc.
3. Lấy account state/epoch có thẩm quyền; xác nhận còn được cấp phiên.
4. Sinh session ID mới, không dùng ID do request tự chọn.
5. Trong transition nhất quán:
     - kiểm tra quota và tạo state của phiên mới;
     - ràng buộc subject, auth context, auth_at, activity và policy;
     - vô hiệu binding cũ thuộc luồng transition theo hợp đồng.
6. Chỉ sau khi state bền vững đủ điều kiện, trả credential mới qua profile.
7. Audit bằng reference an toàn; không ghi raw session ID.
```

Nếu cần chuyển giỏ hàng hoặc dữ liệu anonymous sang phiên đã đăng nhập, chỉ chuyển dữ liệu được phép và kiểm tra lại ownership. Không sao chép role, chủ thể hoặc proof xác thực do ngữ cảnh anonymous tự khai.

Rotation phải có quy tắc cho request đang chạy và ID cũ. Không công bố đã đổi ID an toàn khi ID cũ vẫn có thể authorize ngoài transition/grace policy đã duyệt. Với chuyển đặc quyền, profile ví dụ không cho một ID biết trước tiếp tục dùng như phiên mới được nâng quyền.

### 7.2. Cookie minh họa

```http
Set-Cookie: __Host-session=<opaque-id>; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
```

Trong profile, cookie không có Domain, có Path=/ và chỉ chuyên chở qua HTTPS. Prefix `__Host-` có thể bổ sung ràng buộc ở client hỗ trợ quy tắc prefix; không dùng sự hỗ trợ prefix như bằng chứng duy nhất thay cho kiểm tra server/host/origin.

Secure hạn chế chuyên chở cookie theo điều kiện kênh của client; HttpOnly hạn chế truy cập qua API script thông thường. HttpOnly không ngăn một script XSS đang chạy trong origin sử dụng browser để tạo request có cookie. Cần kiểm soát XSS và quyền tại API riêng.

SameSite cần phù hợp các luồng điều hướng, SSO và tích hợp thực tế. Lax trong ví dụ không thay chống CSRF; đặc biệt không dùng GET thông thường để tạo tác dụng nghiệp vụ. Nếu phải dùng profile cross-site khác, cần kiểm thử cookie, nguồn, credentialed request và bảo vệ CSRF theo đúng hợp đồng. CORS cũng không thay xác thực/phân quyền hay cơ chế CSRF.

Cookie Path không phải ranh giới phân quyền giữa mọi ứng dụng cùng origin. Session cookie không được phát tán sang host/path/profile không cần thiết. Header cache như no-store cho response nhạy cảm cần được kiểm tra qua đường triển khai, không được coi là cách thu hồi mọi bản sao credential từng bị lộ.

Không có Max-Age trong ví dụ không có nghĩa phiên server tồn tại tới lúc browser đóng. Browser có thể giữ/khôi phục trạng thái theo hành vi của nó; server vẫn phải áp idle/absolute deadline độc lập.

### 7.3. Parse và xử lý request

Session middleware cần quy định cách nhận đúng cookie/header của profile, giới hạn kích thước và xử lý giá trị trùng/xung đột. Nếu cùng tên session cookie có nhiều giá trị qua proxy/framework, không tùy ý chọn first/last để tạo hai cách hiểu khác nhau. Phải test cách các lớp parse/ghép cookie thực sự hoạt động.

ID sai dạng hoặc không có trong store không được dùng làm khóa để tự tạo phiên xác thực. Không chấp nhận thêm một query parameter session ID như fallback khi cookie không có.

Một request có thể bị từ chối vì credential không hợp lệ, phiên hết hạn, thiếu quyền hoặc không thể kiểm tra state. Hành vi response cần rõ theo client/profile; không trả thành công với ngữ cảnh guest rồi vẫn chạy tác dụng yêu cầu tài khoản. Lý do nội bộ phải đủ phân loại nhưng không lộ secret hoặc chi tiết tài khoản ngoài policy.

## 8. Ví dụ Java cho ID opaque và điều kiện phiên

Ví dụ JDK 17 dùng 32 byte từ SecureRandom, base64url và digest lookup cho profile opaque. Nó không phải một session framework hoàn chỉnh.

```java
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Objects;

public final class SessionRequirementExample {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Base64.Encoder ENCODER =
            Base64.getUrlEncoder().withoutPadding();
    private static final Duration IDLE = Duration.ofMinutes(20);
    private static final Duration ABSOLUTE = Duration.ofHours(8);

    public enum State { ACTIVE, REVOKED }
    public record StoredSession(
            Instant authenticatedAt,
            Instant lastActivityAt,
            long accountEpoch,
            State state) {
        public StoredSession {
            Objects.requireNonNull(authenticatedAt);
            Objects.requireNonNull(lastActivityAt);
            Objects.requireNonNull(state);
        }
    }

    public static String newSessionId() {
        byte[] bytes = new byte[32];
        RANDOM.nextBytes(bytes);
        return ENCODER.encodeToString(bytes);
    }

    public static String lookupDigest(String sessionId)
            throws NoSuchAlgorithmException {
        if (sessionId == null || !sessionId.matches("[A-Za-z0-9_-]{43}")) {
            throw new IllegalArgumentException("Invalid session ID format");
        }
        byte[] raw = Base64.getUrlDecoder().decode(sessionId);
        if (raw.length != 32 || !ENCODER.encodeToString(raw).equals(sessionId)) {
            throw new IllegalArgumentException("Non-canonical session ID");
        }
        return HexFormat.of().formatHex(
                MessageDigest.getInstance("SHA-256").digest(raw));
    }

    public static boolean hasActiveSession(
            StoredSession session, long currentAccountEpoch,
            boolean accountIsActive, Instant now) {
        if (session == null || now == null || !accountIsActive) {
            return false;
        }
        if (session.state() != State.ACTIVE
                || session.accountEpoch() != currentAccountEpoch
                || session.lastActivityAt().isBefore(session.authenticatedAt())
                || now.isBefore(session.authenticatedAt())
                || now.isBefore(session.lastActivityAt())) {
            return false;
        }
        return now.isBefore(session.authenticatedAt().plus(ABSOLUTE))
                && now.isBefore(session.lastActivityAt().plus(IDLE));
    }
}
```

32 byte ngẫu nhiên tương ứng không gian giá trị 256 bit trước khi mã hóa; chuỗi base64url không padding trong profile có 43 ký tự. Mã hóa không tạo thêm entropy. Kiểm tra canonical bảo đảm không có nhiều cách biểu diễn được nhận cho cùng bytes trong hợp đồng ví dụ.

Digest lookup không được coi là password hashing: đầu vào ở đây là credential ngẫu nhiên entropy cao do server cấp, không phải mật khẩu người dùng. Digest không thay bảo vệ store, quyền sửa metadata hoặc chống lộ raw ID. Không dùng digest như một token thay thế được API chấp nhận trực tiếp.

`hasActiveSession` giả định record, account state/epoch và now đến từ nguồn đủ tin cậy. Nó không tự đọc store, kiểm tra độ mới cache, set cookie, xử lý CSRF, authorization tenant/object, step-up hoặc logout. Kết quả true chưa cho phép mọi operation.

Khi persist phiên, cần ràng buộc duy nhất và transition đúng trước khi phát cookie. Lỗi CSPRNG/mật mã/store phải đi luồng lỗi; không fallback sang counter, timestamp hoặc một ID mặc định. Unit test helper này không chứng minh framework/proxy thực sự áp cookie và revoke đúng.

## 9. Timeout, activity và step-up trong hệ thống phân tán

### 9.1. Cập nhật activity không làm sống lại phiên

`last_activity_at` phải do server tạo ở điểm hoạt động được chấp nhận theo policy, không lấy từ request header/client clock. Cập nhật cần kiểm tra state/epoch và điều kiện thời gian tương ứng; không ghi lại ACTIVE chỉ vì một request cũ hoàn tất sau logout.

Với request cạnh tranh, tránh để bản cập nhật trễ ghi đè activity mới hơn thành thời điểm cũ. Cần cơ chế nguyên tử/kiểm tra version phù hợp, đồng thời không cho một touch với thời gian cũ gia hạn một phiên đã hết hạn tại điểm cập nhật. Deadline phải được thực thi ở điểm quyết định, không phụ thuộc thứ tự job cleanup.

Đồng hồ đơn điệu hữu ích để đo timeout/độ trễ nội bộ, nhưng không lấy giá trị đơn điệu của máy A so trực tiếp với Instant hoặc giá trị máy B. Cần nguồn thời gian/state có hợp đồng cho các replica. Khi chất lượng thời gian không đủ, không tự sửa auth_at/last_activity_at thành bây giờ để hết lỗi.

### 9.2. Step-up không phải một field do client gửi

Ví dụ operation thay credential hoặc quản lý quyền cần proof bổ sung có độ mới dưới 5 phút. Host phải xác minh chủ thể, phương thức/mức xác thực theo policy, thời điểm và context của proof. Một boolean `mfa=true` trong body hoặc một timestamp do client nhập không có thẩm quyền này.

Tại đúng `verified_step_up_at + 5 phút`, profile ví dụ yêu cầu step-up mới. Phiên đã quá hạn/bị thu hồi không được sử dụng chỉ vì có một proof còn mới. Quyền nghiệp vụ vẫn phải đủ và proof không được áp cho subject/context khác.

Nếu transition thay auth strength hoặc đặc quyền yêu cầu đổi ID, phải liên kết proof, phiên mới và vô hiệu binding cũ theo SMR-04. Không tự reset absolute lifetime chỉ bằng một touch hoặc thay đổi cookie name.

### 9.3. IP/User-Agent và quota phiên

IP, User-Agent hay thông tin thiết bị là tín hiệu rủi ro/quan sát, không phải credential. Người dùng có thể đổi mạng và nhiều người có thể dùng chung địa chỉ; attacker cũng có thể dùng thông tin tương tự. Nếu policy dùng các tín hiệu đó để yêu cầu step-up hoặc chặn, cần quy tắc và test, không coi chúng là danh tính tuyệt đối.

Với giới hạn 5 phiên ACTIVE/tài khoản, profile có thể từ chối tạo phiên thứ sáu và cho người dùng quản lý phiên qua luồng đã xác thực. Kiểm tra số lượng và cấp slot phải nhất quán xuyên replica, có xử lý phiên đã hết hạn/thu hồi. Trang danh sách dùng public management reference riêng theo policy, không trả raw session ID.

## 10. Logout, thu hồi và sự kiện tài khoản

### 10.1. Xóa cookie và vô hiệu state là hai phần

Logout của phiên web cần có transition phía server theo hợp đồng, rồi yêu cầu client bỏ credential tương ứng. Cookie xóa phải dùng đúng name/path/domain scope của cookie cần xóa; với profile minh họa không có Domain:

```http
Set-Cookie: __Host-session=; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=0
Cache-Control: no-store
```

Header trên không làm bản sao token đã bị lộ biến mất. Bên nhận vẫn phải từ chối replay bằng state thu hồi/epoch/expiry. Không trả nghĩa “đã logout hoàn toàn theo hợp đồng” nếu bước invalidate bắt buộc chưa bền vững mà chỉ xóa cookie ở browser.

Logout/đổi tài khoản và endpoint quản lý phiên cần bảo vệ request theo profile, gồm chống CSRF khi dùng cookie. Không dùng một URL GET thông thường để tạo tác dụng logout hoặc thu hồi tùy ý mà chưa có hợp đồng an toàn rõ.

Phân biệt logout một phiên, tất cả phiên của tài khoản và logout ở hệ thống định danh bên ngoài. Tài khoản người dùng phải được cấp đúng quyền để xem/thu hồi các phiên của mình; không nhận một management reference bất kỳ rồi bỏ kiểm tra ownership.

### 10.2. Ngân sách thu hồi xuyên các điểm thực thi

```text
T0 = thời điểm revoke được commit ở nguồn state có thẩm quyền
T0 + 30 giây = hạn cuối chặn authorization mới trong phạm vi profile
```

Cần kiểm tra app replica, gateway, cache, các API và kênh dài. Thời điểm request đến hoặc timestamp client gửi không được dùng để vượt cutoff khi authorization thực sự chỉ diễn ra sau đó.

Giới hạn cache allow 5 giây trong ví dụ phải được thực thi cùng nguồn/time evidence đủ tin cậy. Khi cache hết độ mới và store không đọc được, không gia hạn allow vô hạn. Nếu dùng sự kiện đẩy, vẫn cần quy tắc cho message mất/trễ và replica tách mạng; nhận được event tại một instance không chứng minh mọi nơi đã thu hồi.

Một request đã được authorize trước điểm chặn có thể đã tạo tác dụng. Revoke không tự rollback khoản ghi, message hoặc cuộc gọi ngoài đã được chấp nhận. Đối với operation yêu cầu không commit sau sự kiện thu hồi, cần kiểm tra/serialization với epoch/state tại ranh giới tác dụng bằng thiết kế nhất quán phù hợp, không chỉ check cookie ở đầu request.

Worker xử lý sau không được tin một field `authenticated=true` do bên ngoài gửi. Phải có bằng chứng tiếp nhận và chính sách quyền tại thời điểm nghiệp vụ yêu cầu; một session từng hợp lệ không cấp quyền thực hiện tác vụ mãi mãi.

### 10.3. Khóa tài khoản, reset credential và thay quyền

Profile phải quy định sự kiện nào làm revoke một số hay tất cả phiên. Ví dụ khóa tài khoản hoặc reset credential/MFA có thể tăng account security epoch và yêu cầu xác thực lại cho phạm vi liên quan. Phiên mang epoch cũ không được tiếp tục chỉ vì row của nó còn ACTIVE.

Khi gỡ role hoặc chuyển quyền tenant, không giữ snapshot role cũ vô thời hạn trong phiên. Có thể kiểm tra quyền hiện hành hoặc invalidation/epoch theo hợp đồng; phải chứng minh bound thực tế. Cấp thêm quyền/đổi auth strength cần kiểm tra proof và rotation khi policy yêu cầu, không tin role mới do client tự gửi.

Nếu quy trình recovery cho phép tạo phiên mới, phải dựa trên proof mới phù hợp và state tài khoản hiện hành. Không lấy một phiên trước reset rồi tự đánh dấu đã reauthenticate mà không có chứng cứ.

### 10.4. Kết nối dài

Với WebSocket/stream, cần quyết định kiểm tra mỗi message, kiểm tra định kỳ và/hoặc cưỡng chế đóng khi expiry/revoke. Cách nào cũng phải đạt bound đã công bố cho việc tiếp tục đọc/ghi dữ liệu theo quyền.

Handshake hợp lệ lúc mở kết nối không cho phép mọi message sau đó. Test phải giữ kết nối mở qua idle/absolute deadline và logout, thử gửi/nhận dữ liệu sau cutoff. Ping/heartbeat không tự đổi activity theo profile; quyền subscription theo tenant/object vẫn phải còn hợp lệ.

## 11. Refresh token, remember-me và SSO

### 11.1. Token tự chứa và thu hồi

Một access token tự chứa có thể được receiver xác minh mà không đọc session store ở mọi request. Chữ ký đúng và token chưa hết hạn không tự chứng minh local logout hoặc account revoke đã được áp dụng tại receiver đó.

Nếu access token còn hạn 15 phút và receiver không có cơ chế biết revoke sớm, không thể chỉ xóa cookie hoặc refresh token rồi cam kết mọi authorization dừng trong 30 giây. Muốn có bound đó, cần cơ chế kiểm tra state/epoch/introspection phù hợp, thời hạn token đáp ứng bound hoặc một thiết kế khác có kiểm chứng. Không công bố một bảo đảm mà receiver không thể thực thi.

Mỗi loại credential cần có issuer/subject/audience/phạm vi, thời hạn, nguồn kiểm chứng và quy tắc thu hồi tương ứng. Không coi access token, refresh token và opaque session cookie là các chuỗi có thể thay thế cho nhau ở mọi endpoint.

### 11.2. Refresh rotation và replay

Nếu có refresh token, cần định nghĩa dùng một lần/rotation, token family, trạng thái token đã dùng, thời hạn, concurrency và phản ứng khi replay. Việc kiểm tra và cấp token kế tiếp cần chuyển trạng thái nguyên tử để hai request không tự tạo hai nhánh quyền ngoài hợp đồng.

Client có thể gửi refresh đồng thời hợp lệ; policy phải nêu cách client/server phối hợp và cách phân biệt retry với sử dụng lại đáng ngờ theo bằng chứng có thể thu được. Không âm thầm cấp thêm credential vô hạn cho mọi lần dùng token cũ. Nếu thiết kế thu hồi family khi phát hiện reuse, cần test cả tình huống tấn công lẫn concurrency/retry hợp lệ và tác động tới người dùng.

Refresh/retry không được tự vượt lifetime tổng hoặc điều kiện reauthentication của profile. Không để refresh thành đường bỏ qua MFA/step-up hoặc làm account đã khóa hoạt động lại.

### 11.3. Remember-me và đăng xuất liên kết

Remember-me là profile dài hạn cần được quản lý riêng với một session ngắn hạn. Cần ràng buộc tài khoản/thiết bị theo thiết kế, quyền sử dụng, storage, rotation, expiry và thu hồi. Khôi phục ngữ cảnh nhờ credential dài hạn không tự chứng minh người dùng vừa thực hiện xác thực mạnh đủ mới cho thao tác nhạy cảm.

Với SSO, phải nêu local logout tác động tới phiên ứng dụng nào, phiên tại identity provider và ứng dụng khác ra sao. Có thể còn một upstream session cho phép đăng nhập lại mà không nhập credential; không tuyên bố đã kết thúc tất cả phiên ngoài phạm vi đã kiểm chứng.

Callback/redirect xác thực cần được đặc tả theo giao thức tích hợp và context được kiểm chứng, gồm chống giả mạo/replay phù hợp. Không bỏ cơ chế CSRF/context của mọi endpoint chỉ để một luồng SSO hoạt động. Các profile không hỗ trợ refresh/remember-me/SSO phải ghi rõ không áp dụng có căn cứ, không để phần chưa đánh giá được hiểu là đã đạt.

## 12. Audit, lỗi phụ thuộc và phục hồi

### 12.1. Bằng chứng quan sát an toàn

Audit hữu ích gồm create, rotation, expiry reason, logout/revoke scope, account epoch change, step-up và deny. Liên kết bằng session management reference hoặc tham chiếu an toàn có kiểm soát, không ghi raw cookie/access/refresh/CSRF token vào log.

Có thể ghi subject/tenant reference theo quyền, instance, auth context đã xác minh, policy revision, decision time, cache/state age và reason code. Không dùng fingerprint/IP như bằng chứng duy nhất của cùng một người; cũng không thu thập dư thông tin thiết bị chỉ để làm log trông đầy đủ.

Metric cần phân biệt timeout, invalid/revoked, thiếu quyền, state unavailable và step-up required. Với revoke bound, lưu mốc commit cùng quyết định thực tế ở các điểm thực thi để đo, không chỉ thời gian event đến một queue. Giới hạn cardinality và dữ liệu nhạy cảm trong nhãn metric.

### 12.2. Hành vi khi store/time không đủ tin cậy

Khi không có state hợp lệ hoặc cache đã quá tuổi cho phép, request cần phiên không được chuyển sang authenticated dựa trên cookie có vẻ đúng dạng. Profile có thể trả lỗi tạm thời hoặc yêu cầu xác thực lại theo tình huống; không giả vờ đã xác minh để tiếp tục tác dụng nhạy cảm.

Cần quan sát lỗi store, đồng hồ và propagation. Đồng bộ thời gian đang chạy hay lưu timestamp ở UTC không tự chứng minh giờ đúng. Nếu không đủ căn cứ, không thay auth_at/expiry bằng bây giờ hoặc tăng timeout để làm hết lỗi.

### 12.3. Restore không làm sống lại phiên

Snapshot trước logout/reset có thể chứa row ACTIVE và epoch cũ. Restore cần kiểm tra nguồn trạng thái thu hồi/epoch, phiên bản policy và thời gian. Không mở lưu lượng bảo vệ khi chưa chứng minh được state phục hồi không trái quyết định đã có hiệu lực.

Một phương án khi không bảo toàn được bằng chứng thu hồi là không chấp nhận các phiên từ snapshot và buộc xác thực lại theo một thế hệ state/namespace hợp lệ mới. Cơ chế cụ thể phải ngăn ID/epoch cũ vô tình khớp lại, không chỉ đổi nhãn trên dashboard.

Khôi phục ứng dụng, session store và account/security state cần có quy trình phối hợp. Việc browser vẫn giữ cookie không buộc server phải chấp nhận lại phiên cũ; luồng phục hồi phải giải thích và xử lý xác thực lại phù hợp với sản phẩm.

## 13. Thiết kế kiểm chứng theo verification framework

### 13.1. Tách các loại bằng chứng

| Lớp kiểm chứng | Câu hỏi | Bằng chứng điển hình |
| --- | --- | --- |
| Review thiết kế/profile | Anchor, state, điểm thực thi và bound có khả thi không? | Hồ sơ lifecycle, trust boundary, quy tắc cache/revoke/SSO và threat model |
| Review code/config | Nguồn ID, lookup, rotation, timeout và quyền có được triển khai đúng không? | Luồng sinh/persist/validate, config có hiệu lực, điều kiện cập nhật state |
| Unit/component | Phép tính/transition có đúng biên và dữ liệu lỗi không? | Clock kiểm soát, record ACTIVE/REVOKED, epoch, canonical ID và callback outcome |
| Tích hợp API/store | Broker/middleware và DB/cache áp điều kiện thực không? | Replay, race, store outage, quota login và kiểm tra tác dụng ở DB/API |
| Browser/proxy | Cookie, origin, cache và CSRF có hiệu lực trên đường thực tế không? | Request/response đã che credential, browser behavior, redirect/callback theo profile |
| Phân tán/phục hồi | Mọi replica/kênh dài và restore có giữ bound không? | Timeline revoke, test phân vùng/cache cũ và snapshot trước sự kiện |

Một checkbox cấu hình không đủ để kết luận control đạt. Một test âm tính bị chặn do lỗi khác cũng chưa chứng minh điều kiện mục tiêu hoạt động; cần fixture chỉ thay biến đang kiểm tra và test dương tính cùng profile.

Mỗi kết quả nên gắn requirement ID, profile/policy revision, endpoint/kênh, artifact/configuration, môi trường thử, điều kiện trước/sau và evidence reference. Trạng thái chưa kiểm tra, không hỗ trợ hoặc không áp dụng phải có ý nghĩa riêng, không tự chuyển thành PASS.

### 13.2. Ví dụ thời gian cho fixture

Giả sử auth_at = 08:00:00 và last_activity_at = 09:10:00 cùng ngày trong một nguồn thời gian kiểm soát. Absolute due là 16:00:00, idle due là 09:30:00. Nếu không có hoạt động được tính mới, tại 09:30:00 phải từ chối dù còn rất lâu mới tới absolute due.

Trong fixture khác, traffic hợp lệ cập nhật activity tới 15:59:00. Idle due có thể là 16:19:00 nhưng absolute due vẫn 16:00:00. Tại 16:00:00 phải từ chối, không chọn deadline muộn hơn của hai điều kiện.

Nếu revoke được commit tại T0, fixture phải thử token cũ trên từng replica và kênh dài trước/sau T0 + 30 giây. Mốc này đo authorization mới theo hợp đồng, không tự chứng minh tác dụng đã được chấp nhận trước đó đã bị hoàn tác.

## 14. Ma trận kiểm thử nghiệm thu

Dùng tài khoản/tenant, session và proof tổng hợp. Không đưa credential production vào báo cáo. Khi cần replay credential thử, chỉ dùng trong môi trường kiểm soát và che/hủy dữ liệu theo policy sau kiểm thử.

| Test ID | Điều kiện thử | Kết quả mong đợi | Truy vết |
| --- | --- | --- | --- |
| T-SMR-01 | Login hợp lệ, state/policy/store sẵn sàng, request trong thời gian và quyền được phép | Cấp ID mới đúng profile, persist đúng binding, thao tác hợp lệ thành công và audit không lộ token | SMR-01, 02, 03, 17 |
| T-SMR-02 | Client chọn ID trước login, gửi ID đúng dạng nhưng không do server cấp hoặc thêm session ID trong query | Không tự tạo phiên xác thực theo input; login không giữ fixation; fallback query không được dùng | SMR-02, 04 |
| T-SMR-03 | Login/step-up/transition quyền yêu cầu rotation; giữ token cũ và tạo request cạnh tranh | Binding mới đúng chủ thể/proof; ID cũ không authorize ngoài hợp đồng và không sống lại do activity trễ | SMR-04, 08, 14 |
| T-SMR-04 | Kiểm tra cookie qua browser/proxy, host/path, HTTPS, duplicate cookie, response cache và URL/log | Flags/scope đúng profile; parse không nhập nhằng; credential không xuất hiện ở kênh bị cấm | SMR-03, 09, 10 |
| T-SMR-05 | Phiên không có hoạt động gia hạn; thử ngay trước, đúng và ngay sau idle 20 phút | Chỉ thời điểm trước deadline đạt; đúng/sau bị từ chối dù row chưa bị cleanup | SMR-05 |
| T-SMR-06 | Liên tục có hoạt động hợp lệ; thử ngay trước/đúng/sau absolute 8 giờ, rotate ID không full reauth | Traffic/rotation không kéo dài absolute; deadline đúng biên có hiệu lực | SMR-04, 05 |
| T-SMR-07 | Ping, request bị từ chối, client clock giả; activity updates đảo thứ tự và touch sau revoke | Chỉ loại hoạt động được phép gia hạn; không ghi lùi activity hoặc làm state/phiên hết hạn sống lại | SMR-05, 06, 15 |
| T-SMR-08 | Logout/revoke commit, replay token cũ ở mọi app/gateway với cache còn bản ACTIVE | Chậm nhất T0 + 30 giây không có authorization mới trái phạm vi; cookie xóa không phải bằng chứng duy nhất | SMR-06, 16 |
| T-SMR-09 | Khóa account, reset credential/MFA, gỡ role; giữ session hợp lệ rồi đổi tenant/object | Epoch/account state và quyền hiện hành có hiệu lực theo policy; session không tự cho quyền object/tenant khác | SMR-07, 14 |
| T-SMR-10 | Step-up giả/sai subject, còn thiếu phương thức, tương lai, đúng/sau 5 phút hoặc phiên đã hết hạn | Không cho operation nhạy cảm đi qua; proof đúng mới được dùng trong context và không tự reset mọi clock | SMR-08 |
| T-SMR-11 | Cross-site state-changing request, thiếu/sai CSRF context, Origin không được phép và luồng SSO hợp lệ | Request trái hợp đồng bị chặn; luồng hợp lệ vẫn hoạt động; SameSite/CORS/HttpOnly không bị dùng làm thay thế mọi kiểm soát | SMR-03, 09, 12 |
| T-SMR-12 | Kiểm tra session store/backup, log/debug, API danh sách và quản lý phiên, người dùng khác account | Không có raw bearer/CSRF secret ở nơi bị cấm; ownership và reference quản lý đúng phạm vi | SMR-10, 11, 16 |
| T-SMR-13 | Nhiều login đồng thời qua nhiều replica khi đã gần 5 phiên ACTIVE | Quy tắc slot/phạm vi/deny phiên thứ sáu của profile có hiệu lực nguyên tử; không vượt cap do race | SMR-11 |
| T-SMR-14 | Với profile hỗ trợ: refresh đồng thời/replay, remember-me, access token còn hạn và local/upstream logout | Hành vi đúng rotation/family/lifetime/revoke scope; không công bố bound 30 giây nếu receiver không thực thi được | SMR-12 |
| T-SMR-15 | Giữ WebSocket/stream qua idle/absolute/revoke và gửi/nhận message sau cutoff | Không tiếp tục dữ liệu/tác dụng trái policy; đóng hoặc kiểm tra quyền đạt bound, heartbeat không làm mới phiên | SMR-05, 06, 13 |
| T-SMR-16 | Store mất kết nối, cache quá 5 giây, state/time record sai hoặc config thiếu | Không fallback authenticated/ACTIVE; lỗi có reason/quan sát, không sửa timestamp để kéo dài phiên | SMR-15, 16 |
| T-SMR-17 | Restore snapshot trước logout/reset; browser còn giữ cookie và account epoch đã thay | Phiên cũ không sống lại; chỉ mở lưu lượng khi bằng chứng state đủ hoặc buộc full reauth theo policy | SMR-14, 18 |
| T-SMR-18 | Kiểm tra mọi endpoint/kênh được kiểm kê, gồm API phụ, gateway và callback; thay middleware/config | Cùng bất biến được thực thi trong phạm vi; N/A/untested không bị đếm thành đạt | SMR-01, 17 |
| T-SMR-19 | Request authorize trước logout rồi xử lý chậm; lượt khác chỉ authorize sau cutoff hoặc ghi activity sau revoke | Phân biệt tác dụng đã nhận với authorization mới; không tái kích hoạt phiên hoặc nhận mới bằng timestamp client | SMR-05, 06, 07 |
| T-SMR-20 | Policy/timeout đổi, triển khai nhiều replica và restore; kiểm tra audit reason cùng artifact/config revision | Quy tắc áp dụng/transition rõ, test biên được chạy lại và bằng chứng đủ tái dựng quyết định không lộ credential | SMR-15, 16, 17, 18 |

### 14.1. Acceptance criteria theo Given–When–Then

**AC-01 — Chống fixation và trường hợp hợp lệ.** Given một ID do client đặt trước login và một tài khoản thử hợp lệ. When xác thực thành công. Then hệ thống cấp ID mới, persist binding đúng chủ thể/auth context và không dùng ID cũ như phiên xác thực mới. Request hợp lệ trong profile/quyền/thời gian phải thành công; hệ thống chặn mọi request không được coi là đạt.

**AC-02 — Timeout độc lập và đúng biên.** Given profile idle 20 phút, absolute 8 giờ và nguồn thời gian kiểm soát. When không có hoạt động được phép gia hạn tới idle due. Then tại đúng due bị từ chối. When traffic hợp lệ giữ idle mới nhưng tới absolute due. Then vẫn bị từ chối; rotate ID/ping/client clock không tự cấp thêm lifetime.

**AC-03 — Logout/revoke thực sự có hiệu lực.** Given token cũ còn được giữ và nhiều app/gateway replica đang có cache. When revoke được commit tại T0. Then chậm nhất T0 + 30 giây không điểm thực thi nào trong phạm vi tạo authorization mới từ phiên bị thu hồi. Bằng chứng gồm state/epoch/cache age, decision time và tác dụng, không chỉ header xóa cookie.

**AC-04 — Phiên hợp lệ không thay quyền/step-up/CSRF.** Given session ACTIVE trong thời gian. When user gọi object/tenant ngoài quyền, thiếu step-up còn mới hoặc gửi request tạo tác dụng thiếu CSRF context bắt buộc. Then không có tác dụng bị cấm. Chỉ proof/context do nguồn được xác minh mới được dùng; field client tự khai không nâng auth strength hay tenant.

**AC-05 — Race và kênh dài giữ bất biến.** Given request/activity update cạnh tranh với revoke và một kết nối đã mở. When phiên mất hiệu lực. Then update trễ không làm ACTIVE trở lại, message/authorization sau cutoff không được phép; tác dụng đã được chấp nhận trước đó được xử lý/đối soát theo hợp đồng riêng, không tuyên bố tự rollback.

**AC-06 — Lỗi và restore không phục hồi quyền cũ.** Given store/time không đủ tin cậy hoặc snapshot trước quyết định thu hồi. When ứng dụng phục hồi. Then không dùng cache quá tuổi/row ACTIVE cũ để cho qua; xác minh lại state hiện hành hoặc yêu cầu full reauth theo policy. Audit liên kết đúng profile/revision và không ghi credential có thể dùng lại.

### 14.2. Bằng chứng cần lưu

Lưu profile/policy revision, endpoint/kênh và topology, artifact/config có hiệu lực, trạng thái phiên/account/epoch đã che dữ liệu, fixture time/proof, request/response được lọc, kết quả quyền/tác dụng và timeline revoke/restore.

Với cookie, cần kiểm tra browser thực tế và đường proxy chứ không chỉ một unit test tạo chuỗi header. Với expiry/step-up cần kiểm soát thời gian thay vì ngủ nhiều giờ. Với revoke cần thử mọi điểm quyết định đã cam kết, cache cũ và kết nối dài. Với race cần quan sát state sau cùng và tác dụng thực tế, không chỉ response đầu tiên.

## 15. Truy vết và bài tập áp dụng

```text
Mục tiêu giữ đúng danh tính/quyền trong thời hạn được phép
  → SER-xx: đoán/lộ/fixation, timeout sai, revoke trễ, stale role, CSRF, restore sai
  → SMR-xx: profile + lifecycle + ngưỡng + owner + hành vi lỗi
  → Session middleware/store + account epoch + authorization + browser/proxy
  → T-SMR-xx và AC-xx
  → Audit, thu hồi, quản lý phiên và kiểm tra sau phục hồi
```

| Mục tiêu | Yêu cầu | Kiểm chứng tiêu biểu |
| --- | --- | --- |
| Đúng ID, binding và kênh chuyên chở | SMR-01, 02, 03, 04 | T-SMR-01, 02, 03, 04; AC-01 |
| Tuổi phiên và activity không bị kéo dài trái policy | SMR-05, 15 | T-SMR-05, 06, 07, 16; AC-02 |
| Revoke/account state có hiệu lực xuyên topology | SMR-06, 13, 14 | T-SMR-08, 09, 15, 19; AC-03, 05 |
| Quyền, proof và request context độc lập phiên | SMR-07, 08, 09 | T-SMR-09, 10, 11; AC-04 |
| Quản lý credential/profile mở rộng an toàn | SMR-10, 11, 12 | T-SMR-12, 13, 14 |
| Quan sát, coverage và restore có bằng chứng | SMR-16, 17, 18 | T-SMR-16, 17, 18, 20; AC-06 |

Những lỗi đặc tả thường gặp:

- “ID khó đoán nên phiên an toàn”: chưa xét lộ token, fixation, timeout và revoke.
- “Có HttpOnly là hết XSS”: script trong origin vẫn có thể tạo request theo quyền người dùng.
- “Xóa cookie là logout mọi nơi”: chưa vô hiệu state, access token hoặc upstream session.
- “Có traffic là kéo dài phiên”: có thể bỏ mất absolute lifetime và cho heartbeat giữ phiên.
- “JWT có chữ ký nên biết đã revoke”: chữ ký không tự mang trạng thái thu hồi mới nhất.
- “Session ACTIVE nên được truy cập tenant client gửi”: thiếu authorization hiện hành.
- “Restore row ACTIVE là khôi phục đăng nhập”: có thể làm sống quyết định đã bị thu hồi.
- “Framework mặc định xử lý hết”: cần kiểm tra cấu hình, topology và bằng chứng thực tế.

Một ứng dụng giữ nguyên session ID trước/sau login, chỉ đặt idle timeout trong JavaScript và kéo dài nó bằng ping. Logout chỉ xóa cookie; API gateway cache quyền 15 phút. WebSocket chỉ kiểm tra handshake. Khi reset password, account epoch không đổi. Restore session store lấy lại các row ACTIVE của hôm trước.

Hãy thực hiện:

1. Nêu ít nhất sáu kịch bản rủi ro, tài sản và bất biến bị ảnh hưởng.
2. Thiết kế profile browser/API, state/time authority và các điểm thực thi.
3. Viết sáu yêu cầu có ID, owner, ngưỡng, hành vi khi không đạt và bằng chứng.
4. Đặc tả login rotation, idle/absolute, step-up và activity update cạnh tranh.
5. Thiết kế logout/revoke bound xuyên replica/gateway/kết nối dài và giải thích giới hạn tác dụng đã được chấp nhận.
6. Nêu test CSRF, quyền tenant/object, cookie, concurrency, state outage và restore.
7. Nếu dùng refresh/remember-me/SSO, chỉ rõ credential nào còn hiệu lực sau từng loại logout và điều kiện xác thực lại.

Trước khi chấp nhận đặc tả, kiểm tra:

- Profile/client/kênh, state/time authority và owner đã rõ chưa?
- ID, binding/rotation và chuyên chở credential có được kiểm chứng không?
- Idle/absolute/step-up có anchor, biên và hoạt động được phép rõ không?
- Logout/revoke/account event có scope, bound, cache policy và test xuyên topology không?
- Phiên có tách khỏi quyền tenant/object, CSRF và bằng chứng xác thực bổ sung không?
- Refresh/SSO/remember-me/kênh dài có hợp đồng hoặc N/A có căn cứ không?
- Race, quota, lỗi store/time và restore có giữ bất biến không?
- Audit và quản lý phiên có đủ proof mà không lộ bearer credential không?

Yêu cầu session management đạt mục tiêu khi mọi điểm dùng ngữ cảnh phiên đều kiểm tra đúng điều kiện hiện hành và có bằng chứng về cách quyền được tạo, giới hạn rồi chấm dứt trong cả vận hành bình thường lẫn sự cố.
