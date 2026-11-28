# Temporary root access — Cấp quyền root tạm thời trên Linux

## 1. Bài toán: cần sửa hệ thống nhưng không cần giữ root lâu dài

Một kỹ sư trực ca cần khởi động lại dịch vụ lỗi trên máy Linux. Nếu tài khoản của người đó luôn thuộc nhóm được chạy mọi lệnh bằng `sudo`, quyền quản trị vẫn tồn tại trước và sau sự cố. Một lần mất tài khoản, khóa SSH hoặc phiên làm việc có thể trở thành đường truy cập root lâu dài.

**Temporary root access** là việc cấp khả năng thực hiện tác vụ với đặc quyền root trong một phạm vi và khoảng thời gian xác định. Quyền phải gắn với danh tính, tài nguyên đích, lý do, tác vụ được phép, thời điểm hết hạn và bằng chứng sử dụng. Sau khi công việc kết thúc hoặc điều kiện cấp quyền không còn đúng, hệ thống phải thu hồi quyền theo chính sách.

Trong chương Linux PAM, cần phân biệt hai nghĩa:

- **Privileged Access Management** quản lý vòng đời quyền đặc biệt: yêu cầu, phê duyệt, cấp quyền, giám sát, thu hồi và kiểm toán.
- **Pluggable Authentication Modules** là cơ chế tích hợp xác thực và kiểm tra tài khoản của nhiều chương trình Linux. Các kiểm tra PAM chỉ xảy ra ở những điểm mà ứng dụng gọi chúng; chúng không tự tạo vòng đời JIT đầy đủ cho mọi tiến trình root.

Bài học tập trung vào quản lý quyền đặc biệt trên Linux. Những lệnh minh họa chỉ mô tả thao tác trong môi trường lab đã được cho phép; không chạy trực tiếp trên máy production.

## 2. Mục tiêu và giới hạn của quyền tạm thời

Một quyền cấp tốt trả lời được sáu câu hỏi:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Danh tính | Ai chịu trách nhiệm cho hành động? | Tài khoản cá nhân `opsdemo`, xác thực qua IdP |
| Tài nguyên | Quyền có hiệu lực ở đâu? | Máy `app-lab-01` |
| Hành động | Được làm gì với root? | Khởi động lại đúng `pam-demo.service` |
| Thời gian | Khi nào bắt đầu và kết thúc? | Một cửa sổ 15 phút |
| Điều kiện | Phê duyệt và ngữ cảnh nào phải còn hợp lệ? | Ticket sự cố đang mở, MFA và thiết bị hợp lệ |
| Thu hồi | Hết hạn thì chặn điều gì và xử lý việc đang chạy ra sao? | Chặn lệnh mới; áp dụng chính sách riêng cho phiên đang chạy |

**Just-in-Time (JIT)** giảm thời gian tồn tại của quyền. **Just Enough Administration (JEA)** giới hạn năng lực được cấp. Một cửa sổ root toàn phần kéo dài 15 phút có JIT nhưng chưa chắc có JEA.

Đối với một lần khởi động lại dịch vụ, ưu tiên một hành động được kiểm soát. Chỉ cấp root shell khi thực sự không thể thực hiện công việc bằng quyền hẹp hơn và có cách giám sát, thu hồi phù hợp.

### Root tạm thời không tạo ra root bị giới hạn

Khi người dùng đã điều khiển root toàn phần trong môi trường Linux thông thường, họ có thể sửa cấu hình, tạo đường truy cập mới, lập lịch công việc, thay đổi dịch vụ hoặc can thiệp vào công cụ kiểm soát nằm trên cùng máy. Thời hạn ngắn không ngăn được những hành động đó trong lúc quyền còn hiệu lực.

Vì vậy, quyền root toàn phần không thể được xem như một sandbox có thời gian sống. Với yêu cầu đối kháng hoặc tác vụ rủi ro cao, cần kết hợp quyền hẹp, tài nguyên cô lập, giám sát ngoài máy đích và quy trình phục hồi độ tin cậy. Một bộ đếm giờ chạy trên chính máy mà người dùng có root không đủ bảo đảm cưỡng chế trước người dùng cố ý vô hiệu hóa nó.

## 3. Phân biệt các loại thời hạn

Một hệ thống thường có nhiều đồng hồ. Gọi tất cả là “TTL” khiến thiết kế thu hồi bị thiếu.

| Loại thời hạn | Đối tượng hết hạn | Điều không tự động xảy ra |
| --- | --- | --- |
| Thời hạn phê duyệt | Quyết định cho phép cấp quyền | Không nhất thiết đóng phiên đã được cấp |
| Thời hạn grant | Khả năng sử dụng một quyền đã cấp | Không tự dừng tiến trình root đã khởi chạy |
| Thời hạn chứng thư hoặc token | Khả năng dùng credential theo cách hệ thống kiểm tra | Không tự ngắt kết nối SSH đã xác thực |
| Thời hạn phiên | Kênh truy cập hoặc phiên do broker quản lý | Không chắc đã dừng công việc tách nền hay system service |
| Thời gian cache xác thực sudo | Việc có phải nhập lại mật khẩu hay không | Không xóa quyền trong sudoers |
| Thời gian tối đa của tác vụ | Một lần thực thi được giám sát | Không bảo đảm hoàn tác thay đổi hoặc dừng mọi hậu duệ |

Ví dụ, chứng thư SSH hết hạn lúc 10:15 không có nghĩa mọi tiến trình của phiên đăng nhập lúc 10:05 sẽ bị dừng lúc 10:15. Chứng thư thường được dùng khi thiết lập kết nối, còn vòng đời kết nối và tiến trình là vấn đề khác.

Tương tự, đặt `timestamp_timeout=0` cho sudo nhằm yêu cầu xác thực lại theo cấu hình sudo. Nó không định nghĩa rằng quyền sudo tồn tại đúng 15 phút.

Cần định nghĩa rõ hai yêu cầu riêng:

1. **Chặn sử dụng mới:** sau thời điểm hết hạn, không được mở phiên hoặc bắt đầu hành động đặc quyền mới.
2. **Xử lý hoạt động đang tồn tại:** phiên, tiến trình hoặc công việc đã bắt đầu trước hết hạn được dừng, tiếp tục có kiểm soát hay chuyển cho người vận hành khác.

Nếu hệ thống chỉ đáp ứng yêu cầu thứ nhất, không được báo cáo rằng toàn bộ khả năng root đã biến mất.

## 4. Vòng đời của một grant

Một grant nên có định danh riêng, chẳng hạn `GRANT-2087`, và trạng thái có thể theo dõi:

```text
REQUESTED -> APPROVED -> PROVISIONING -> ACTIVE -> REVOKING -> REVOKED
                 |             |           |
                 |             |           +-> EXPIRED -> REVOKING
                 |             +-> FAILED -> CLEANUP_REQUIRED
                 +-> CANCELLED

Yêu cầu bị từ chối: REQUESTED -> DENIED
```

Các tên trạng thái chỉ là minh họa, không phải schema bắt buộc của một sản phẩm.

### Yêu cầu và phê duyệt

Người yêu cầu cung cấp mục đích, máy đích, phạm vi tác vụ, thời gian cần thiết và ticket liên quan. Danh tính người dùng phải được xác thực đủ mạnh; việc đã đăng nhập vào cổng PAM không mặc nhiên đủ cho một hành động root nhạy cảm.

Cơ chế phê duyệt có thể là người phê duyệt hoặc chính sách tự động cho tác vụ đã được chuẩn hóa. Dù theo cách nào, cần lưu phiên bản chính sách và điều kiện dẫn tới quyết định. Không cho phép người dùng tự biến một yêu cầu “restart dịch vụ” thành root shell khi thực thi.

### Cấp và kích hoạt

Hệ thống chỉ đánh dấu `ACTIVE` sau khi xác nhận quyền đã được áp dụng đúng đích. Một request được phê duyệt nhưng provision thất bại không phải là grant có thể sử dụng.

Trước khi kích hoạt, kiểm tra lại thời hạn và tình trạng phê duyệt. Nếu yêu cầu chờ provision quá lâu đến mức đã hết hạn, không được tạo lại một cửa sổ đầy đủ chỉ vì thao tác cấp mới vừa hoàn tất.

### Thu hồi và đóng

Hết hạn, kết thúc sớm, hủy phê duyệt, tài khoản bị khóa hoặc tín hiệu rủi ro đều có thể dẫn tới thu hồi. Kết quả thu hồi cần phân biệt:

- Đã chặn sử dụng mới.
- Đã xóa cấu hình cấp quyền.
- Đã xử lý phiên và công việc đang chạy theo chính sách.
- Đã thu hồi hoặc xử lý credential liên quan.
- Đã lưu được bằng chứng và các ngoại lệ còn tồn tại.

`REVOKED` phải biểu thị một điều kiện được kiểm chứng, không chỉ là “đã gửi yêu cầu xóa quyền”.

## 5. Chọn cơ chế phù hợp với công việc

### 5.1. Broker thực thi tác vụ đã định nghĩa

Người dùng gọi một tác vụ có tên và tham số được kiểm tra. Broker xác minh grant ngay trước lúc thực thi, sau đó dùng cơ chế đặc quyền được quản lý để chạy tác vụ trên máy đích.

Đây thường là lựa chọn phù hợp cho các hoạt động lặp lại như restart dịch vụ được phép hoặc thu thập một gói chẩn đoán được giới hạn.

Thiết kế cần kiểm soát toàn bộ đầu vào. Nếu tham số chứa tên script, đường dẫn tùy ý hoặc chuỗi được ghép vào shell, “tác vụ cố định” có thể trở thành chạy lệnh tùy ý.

### 5.2. Sudo với quyền hẹp được provision tạm thời

Hệ thống quản lý tạo một rule cho tài khoản cá nhân và tác vụ cụ thể, sau đó xóa rule theo vòng đời grant.

Điểm mạnh là tận dụng cơ chế Linux quen thuộc và giữ được dấu vết người gọi. Tuy nhiên, một rule sudo thông thường không tự có TTL chỉ vì tên file chứa timestamp. Cần thành phần quản lý thời hạn, cleanup và kiểm chứng.

Cũng cần kiểm tra những nguồn quyền khác như rule cũ, nhóm quản trị hoặc cấu hình sudo được include từ nơi khác. Xóa một rule JIT không có tác dụng nếu cùng người dùng vẫn có `ALL=(ALL) ALL` qua một nguồn khác.

### 5.3. Nhóm đặc quyền tạm thời

Một số hệ thống cấp quyền bằng cách thêm người dùng vào nhóm được phép quản trị. Cách này dễ tích hợp nhưng phạm vi có thể rộng và vòng đời danh tính phức tạp hơn vẻ ngoài.

Xóa người dùng khỏi nhóm trong nguồn danh tính không cập nhật tức thời supplementary groups đã gắn với mọi tiến trình đang chạy. Bộ nhớ đệm NSS/SSSD, phiên đăng nhập mới và cách ứng dụng kiểm tra quyền cũng ảnh hưởng kết quả.

Do đó, chỉ kiểm tra danh sách thành viên ở directory là chưa đủ. Cần xác định chương trình nào thực sự quyết định quyền, nó lấy thông tin ở đâu, cache trong bao lâu và phiên hiện có chịu tác động thế nào.

### 5.4. SSH certificate hoặc credential ngắn hạn

Credential ngắn hạn có thể giảm khả năng tái sử dụng credential cũ và ràng buộc danh tính với cửa sổ truy cập. Nhưng quyền đăng nhập và quyền nâng lên root là hai lớp riêng.

Nếu chứng thư chỉ cho phép đăng nhập tài khoản thường, việc cấp sudo vẫn cần chính sách riêng. Nếu đăng nhập trực tiếp root, phải giải quyết khả năng truy vết người dùng cá nhân, thu hồi phiên và rủi ro của root toàn phần.

Không phát một mật khẩu root dùng chung rồi xem việc hết hạn grant là đã xóa được tri thức về mật khẩu đó. Credential đã được tiết lộ phải được xử lý như credential đã lộ cho người nhận; thu hồi có thể cần xoay vòng và kiểm tra các đường sử dụng liên quan.

## 6. Mô hình cấp quyền cho một lần restart dịch vụ

Giả sử ticket `INC-2087` yêu cầu restart `pam-demo.service` trên `app-lab-01`. Người vận hành là `opsdemo`.

Một bản ghi yêu cầu có thể biểu diễn như sau:

```yaml
requestId: REQ-2087
subject: opsdemo
target: app-lab-01
action: restart-pam-demo-service
reason: "Khôi phục dịch vụ trong lab theo INC-2087"
approvalId: APR-2087
notBefore: "2026-11-27T10:00:00+07:00"
expiresAt: "2026-11-27T10:15:00+07:00"
maxActiveSessions: 1
allowRootShell: false
renewalRequiresApproval: true
```

Đây là **dữ liệu minh họa**, không phải cấu hình có thể đưa nguyên vào một sản phẩm. Sản phẩm hoặc control plane phải định nghĩa cách kiểm tra từng trường; chỉ lưu field không làm chính sách có hiệu lực.

### 6.1. Bảo đảm tác vụ hẹp thực sự

Trước khi cho phép restart, cần xác minh:

- Binary được gọi và đường dẫn thực tế thuộc cấu hình tin cậy của máy đích.
- Tên dịch vụ được cố định, không nhận tùy ý từ người dùng.
- Unit file, drop-in, executable, script, environment file và tài nguyên có ảnh hưởng tới lệnh chạy đặc quyền được bảo vệ khỏi người nhận grant.
- Dịch vụ không đọc plugin hoặc cấu hình có thể được người dùng sửa để chạy code với quyền cao hơn.
- Tài khoản đó không có một đường quản trị khác khiến việc giới hạn grant trở nên vô nghĩa.

Ví dụ, nếu người dùng sửa được script được `ExecStart` gọi với root, quyền restart dịch vụ có thể trở thành khả năng thực thi code root do chính người dùng cung cấp.

Việc giới hạn “một lệnh” chỉ có giá trị khi các đối tượng mà lệnh phụ thuộc cũng được bảo vệ.

### 6.2. Minh họa sudoers trong lab

Sau khi xác minh đường dẫn và phiên bản sudo của lab, một rule tối giản có thể có dạng:

```sudoers
Defaults:opsdemo timestamp_timeout=0
opsdemo ALL=(root) PASSWD: /usr/bin/systemctl restart pam-demo.service
```

Rule này minh họa việc cho đúng tài khoản chạy đúng command line dưới root. Nó **không chứa cơ chế hết hạn** và không phải cấu hình production hoàn chỉnh.

Các lưu ý cần đọc cùng ví dụ:

1. `ALL` ở vị trí host không phải danh sách máy đích của grant. Việc phân phối file chỉ tới máy được cấp quyền phải do hệ thống provision kiểm soát.
2. `PASSWD` không tự cấu hình MFA. Cách xác thực sudo phụ thuộc chính sách sudo và tích hợp xác thực của môi trường.
3. `timestamp_timeout=0` xử lý cache xác thực, không thu hồi rule sau 15 phút.
4. Quyền sudo có tính tổng hợp với cấu hình khác. Một rule hẹp không hạn chế được một rule rộng hơn mà tài khoản cũng đang được hưởng.
5. Không thêm wildcard, không cho `sh -c` nhận dữ liệu tùy ý, không mở quyền chỉnh sửa unit chỉ để giải quyết lỗi vận hành.
6. Không giả định một tùy chọn hạn chế shell escape sẽ biến root shell hoặc mọi chương trình đa năng thành môi trường an toàn.

Trong hệ thống thật, thành phần provision cần validate cú pháp bằng công cụ phù hợp như `visudo`, bảo đảm owner/mode của sudoers, áp dụng thay đổi nhất quán và kiểm tra cả cấu hình hiệu lực. Đường dẫn `systemctl` phải được xác minh trên máy đích, không sao chép mù từ ví dụ.

### 6.3. Trách nhiệm của bộ quản lý grant

Bộ quản lý grant phải liên kết rule với `grantId`, tài khoản, máy đích và thời hạn tuyệt đối. Nó chịu trách nhiệm:

- Không áp dụng quyền trước `notBefore`.
- Không kích hoạt quyền khi phê duyệt đã bị hủy hoặc đã hết hạn.
- Chặn sử dụng mới theo cơ chế được thiết kế.
- Xóa rule đã provision sau khi grant kết thúc.
- Tìm và xử lý quyền còn sót sau lỗi hoặc reboot.
- Ghi nhận kết quả thực tế thay vì chỉ ghi “đã chạy cleanup”.

Nếu dùng rule local và một bộ hẹn giờ để xóa rule, cần đánh giá độ trễ cleanup và kịch bản timer bị ngừng. Không mô tả thời điểm `expiresAt` là biên cưỡng chế chính xác nếu thực tế người dùng vẫn dùng được quyền cho đến lúc rule được xóa.

Để có biên kiểm tra tốt hơn cho lệnh mới, có thể dùng broker hoặc điểm kiểm tra quyền thực thi đáng tin cậy có xác minh grant. Nhưng việc kiểm tra vẫn phải gắn với thao tác thực sự; một kiểm tra ở đầu phiên không đủ cho mọi lệnh về sau.

## 7. Kiểm tra quyền ngay tại thời điểm sử dụng

Một cách suy luận cho quyết định cho phép:

```text
allow =
    danh_tính_được_xác_thực
    AND phê_duyệt_còn_hiệu_lực
    AND grant_đang_ACTIVE
    AND notBefore <= thời_gian_tin_cậy < expiresAt
    AND tài_nguyên_khớp_chính_xác
    AND hành_động_và_tham_số_nằm_trong_phạm_vi
    AND điều_kiện_rủi_ro_còn_đạt
    AND giới_hạn_phiên_chưa_bị_vượt
```

Đây là mô hình quyết định, không phải một chương trình cấp quyền hoàn chỉnh.

Điểm kiểm tra phải được đặt ở nơi người dùng không thể bỏ qua. Nếu broker chỉ kiểm tra rồi trả về một root credential dùng được trực tiếp bên ngoài broker, các lần sử dụng sau có thể không còn đi qua quyết định này.

### Race condition quanh thời điểm hết hạn

Giả sử yêu cầu đến lúc 10:14:59 nhưng phải xếp hàng đến 10:15:03 mới thực thi. Cần kiểm tra lại trước khi bắt đầu tác vụ; thời điểm vào hàng đợi không nên trở thành giấy phép vô hạn.

Tương tự, phê duyệt có thể bị hủy giữa lúc tạo phiên và lúc chạy lệnh. Hệ thống cần định nghĩa ranh giới giữa “đã chấp nhận” và “đã bắt đầu”, đồng thời xử lý thu hồi đang diễn ra.

Không thể loại bỏ mọi khoảng đua chỉ bằng một biểu thức kiểm tra thời gian. Thiết kế cần xác định rõ điểm quyết định, thời gian chấp nhận trễ và cách phát hiện hành động phát sinh sau thu hồi.

### Thời gian và nguồn trạng thái

Dùng thời gian máy chủ hoặc nguồn thời gian được hệ thống kiểm soát để quyết định hạn, không tin thời gian do client tự gửi.

Với việc đếm khoảng thời gian trong một tiến trình, đồng hồ monotonic giúp tránh một số ảnh hưởng của việc chỉnh wall clock. Với grant tồn tại qua reboot hoặc giữa nhiều node, vẫn cần mốc thời gian và cơ chế khôi phục trạng thái phù hợp. Không thể dùng riêng một bộ đếm trong RAM để bảo đảm quyền đã hết hạn sau khi máy khởi động lại.

Chính sách cần nêu rõ sai lệch đồng hồ cho phép, xử lý khi mất đồng bộ và hành vi khi không đọc được trạng thái grant.

## 8. Thu hồi: từ chặn lệnh mới tới xử lý phần còn sống

Thu hồi không phải một thao tác đơn lẻ. Có thể chia công việc thành bốn lớp.

### 8.1. Lớp quyền được cấp

Xóa rule JIT, gỡ membership hoặc vô hiệu hóa quyền ở broker. Sau đó kiểm tra không còn đường nào thuộc grant cho phép tạo hành động đặc quyền mới.

Thao tác phải đúng đích. Không xóa hàng loạt cấu hình sudo hoặc mọi membership chỉ vì một request hết hạn.

Các grant có thể chồng lấp. Nếu hai ticket cùng cấp một quyền cho một người, đóng grant thứ nhất không nên làm hỏng grant thứ hai. Ngược lại, cũng không được để một refcount sai duy trì quyền sau khi tất cả grant đã kết thúc.

### 8.2. Lớp credential và cache

Thu hồi token, capability hoặc credential theo cơ chế hỗ trợ. Nếu credential đã được người dùng biết, chỉ khóa giao diện lấy credential không làm credential đó biến mất khỏi trí nhớ hoặc bản sao của họ.

`sudo -k` hoặc `sudo -K` liên quan tới timestamp cache của sudo cho người dùng thực hiện lệnh; chúng không xóa rule sudoers, không thay mật khẩu root và không kết thúc tiến trình root.

Nếu dùng chứng thư SSH, xác minh chính sách đối với kết nối mới và cách xử lý credential bị thu hồi trước hạn. Không giả định mọi node lập tức nhận cùng trạng thái khi có cache hoặc mất kết nối.

### 8.3. Lớp phiên

Hệ thống cần xác định các phiên nào thuộc grant. Có thể cần đóng kênh do broker quản lý hoặc kết thúc phiên đăng nhập tương ứng theo chính sách.

Đóng một kết nối SSH không có nghĩa mọi tiến trình liên quan đều dừng. Session multiplexer, tiến trình tách nền, công việc lên lịch và system service có thể có vòng đời khác.

Một thao tác kết thúc toàn bộ phiên của người dùng cũng có thể ảnh hưởng công việc không thuộc grant. Do đó, cần liên kết session với grant và chọn cách xử lý có phạm vi rõ ràng.

### 8.4. Lớp tiến trình và thay đổi bền vững

Xóa quyền không đảo ngược hành động đã hoàn thành. Những việc sau có thể còn tồn tại:

- Tiến trình root đã khởi chạy.
- Dịch vụ vừa được khởi động.
- Tác vụ được đăng ký để chạy sau.
- File, key hoặc cấu hình đã bị thay đổi.
- Credential mới hoặc đường truy cập được tạo trong cửa sổ quyền.

Có thể quản lý tác vụ bằng scope/cgroup và timeout để hỗ trợ theo dõi, dừng theo nhóm. Tuy nhiên, root toàn phần có thể tác động vào cơ chế local; không coi cgroup là ranh giới bảo mật bất biến trước chủ thể có root không bị hạn chế.

Nếu phát hiện hành vi ngoài phạm vi, chuyển sang quy trình ứng phó sự cố và xác minh độ tin cậy của máy. Một sự kiện “grant revoked” không chứng minh máy đích chưa bị thay đổi.

## 9. Chọn chính sách cho công việc chạy qua thời điểm hết hạn

Hai mô hình thường gặp:

| Mô hình | Hành vi khi grant hết hạn | Phù hợp khi |
| --- | --- | --- |
| Chặn bắt đầu mới | Từ chối tác vụ mới; tác vụ đã chạy được theo dõi đến khi kết thúc | Tác vụ có phạm vi cố định và rủi ro gián đoạn lớn |
| Kết thúc phiên hoặc tác vụ | Chặn tác vụ mới và yêu cầu dừng hoạt động đang chạy | Phiên tương tác hoặc tác vụ có thể dừng an toàn |

Không có một lựa chọn đúng cho mọi công việc. Dừng đột ngột thao tác đang ghi dữ liệu có thể gây lỗi; cho root shell tiếp tục vô hạn lại phá vỡ mục tiêu giới hạn thời gian.

Một chính sách thực tế có thể quy định:

- Restart đơn lẻ: quyết định quyền tại thời điểm bắt đầu; kết quả được theo dõi đến hoàn tất trong thời gian tối đa đã định.
- Phiên tương tác: cảnh báo trước hết hạn và kết thúc qua cơ chế quản lý phiên nếu không được gia hạn hợp lệ.
- Migration hoặc thay đổi dài: yêu cầu kế hoạch riêng với giới hạn thời gian và điểm dừng an toàn; không xin grant ngắn rồi mặc nhiên kéo dài bằng tiến trình nền.
- Hết hạn trong tình huống nguy hiểm: có quy trình ngoại lệ được ghi nhận, người chịu trách nhiệm và thời điểm kết thúc rõ ràng.

Cần ghi đúng kỳ vọng cho người dùng trước khi cấp quyền. Nếu có khoảng gia hạn để đóng công việc an toàn, khoảng đó cũng phải là chính sách có giới hạn, không phải lỗi cleanup được đổi tên.

## 10. Gia hạn, nhiều phiên và quyền chồng lấp

Gia hạn là một quyết định mới. Không nên để người dùng tự làm mới TTL bằng cách mở tab, gửi heartbeat hoặc đăng nhập lại.

Khi gia hạn:

1. Đánh giá lại lý do và điều kiện rủi ro.
2. Phê duyệt theo chính sách tương ứng.
3. Lưu thời hạn cũ, thời hạn mới và người hoặc policy quyết định.
4. Áp dụng thay đổi nhất quán tới điểm thực thi.
5. Thông báo kết quả sau khi xác minh, không khi request mới chỉ được tiếp nhận.

Các giới hạn cần xem xét gồm tổng thời gian quyền liên tục, số lần gia hạn, số phiên đồng thời và số máy được truy cập.

Nếu người dùng có ba phiên cùng dùng một grant, thu hồi một phiên không phải thu hồi grant. Nếu có hai grant độc lập, phải xác định phiên đang dùng grant nào và quyền thực tế xuất phát từ đâu.

Người vận hành cũng có thể giữ một shell cũ sau khi quyền nhóm đã thay đổi. Bài kiểm tra thu hồi cần bao gồm phiên trước thay đổi và phiên mới, không chỉ đăng nhập lại một lần rồi kết luận.

## 11. Hành vi khi mất kết nối hoặc control plane gặp lỗi

Quyền tạm thời cần một chính sách mất kết nối rõ ràng.

### Không xác minh được grant mới

Mặc định an toàn cho tác vụ JIT là từ chối cấp hoặc sử dụng mới khi không thể xác minh những điều kiện bắt buộc. Không tự cấp một grant mới chỉ vì service phê duyệt chậm.

Tuy nhiên, yêu cầu vận hành có thể cần cơ chế khẩn cấp. Cơ chế đó phải là break-glass được thiết kế trước, có phạm vi, xác thực, giám sát và hậu kiểm riêng; không phải fallback ngầm sang root dùng chung.

### Máy đích mất liên lạc

Nếu node không nhận được lệnh thu hồi, cần biết quyền có tự kết thúc ở điểm thực thi hay đang phụ thuộc hoàn toàn vào cleanup từ xa. Hệ thống trung tâm phải biểu thị trạng thái chưa xác nhận, thay vì đánh dấu thành công vì đã gửi message.

Nếu có cache grant để hoạt động khi offline, cần giới hạn thời gian và phạm vi cache, xử lý thu hồi sớm chưa truyền tới node, đồng thời nêu rõ cửa sổ rủi ro.

### Reboot và phục hồi

Sau reboot, thành phần thực thi phải khôi phục hoặc đối chiếu trạng thái grant trước khi tiếp tục cho phép sử dụng. Rule local tồn tại trên đĩa không được biến quyền 15 phút thành quyền qua nhiều ngày.

Một bộ đối soát định kỳ nên phát hiện:

- Rule hoặc membership không có grant hợp lệ.
- Grant đã hết hạn nhưng cấu hình còn tồn tại.
- Phiên không còn chủ sở hữu grant.
- Lỗi cleanup chưa xử lý.
- Sai lệch giữa control plane và máy đích.

Đối soát hỗ trợ phục hồi; nó không thay thế điểm kiểm tra quyền nếu yêu cầu cần chặn ngay ở biên thời gian.

## 12. Bằng chứng giám sát và kiểm toán

Mỗi chuỗi sự kiện nên liên kết được qua `requestId`, `approvalId`, `grantId`, `sessionId` và máy đích. Các định danh này giúp phân biệt một hành động hợp lệ với một lần sử dụng quyền ngoài ticket.

Bằng chứng cần đủ trả lời:

- Ai yêu cầu, ai phê duyệt và điều kiện nào được dùng?
- Quyền gì được cấp, trên máy nào, trong cửa sổ nào?
- Khi nào quyền thực sự có thể sử dụng?
- Lệnh hoặc tác vụ nào được chấp nhận hay từ chối?
- Khi nào thu hồi được yêu cầu và từng bước thu hồi được xác nhận?
- Có phiên, tác vụ hoặc lỗi nào còn tồn tại sau hạn?

Ví dụ dòng thời gian:

```text
10:00:00  REQ-2087 được phê duyệt theo policy phiên bản 12
10:00:04  GRANT-2087 ACTIVE trên app-lab-01
10:03:11  opsdemo bắt đầu restart-pam-demo-service
10:03:14  Tác vụ hoàn tất, exit status được ghi nhận
10:15:00  Grant hết hạn; điểm thực thi từ chối yêu cầu mới
10:15:02  Cleanup cấu hình local được xác nhận
10:15:03  Đối soát phiên và công việc thuộc grant hoàn tất
```

Trong ví dụ này, việc chặn ở 10:15:00 và cleanup ở 10:15:02 là hai sự kiện riêng. Nếu hệ thống chỉ chặn được sau cleanup, timeline phải phản ánh đúng thực tế đó.

Không chỉ lưu log trên máy mà người nhận có root toàn phần. Cần đưa sự kiện quan trọng tới nơi lưu trữ độc lập, kiểm soát quyền đọc/xóa và theo dõi khi dòng log bị gián đoạn.

Session recording có thể hỗ trợ điều tra nhưng không bảo đảm quan sát mọi hành vi, nhất là khi người dùng có kênh khác hoặc quyền root can thiệp vào môi trường. Không xem bản ghi terminal là bằng chứng duy nhất.

Hạn chế đưa secret vào lệnh, tham số, output và recording. Che dữ liệu ở giao diện sau khi log đã được ghi không xóa được bản secret trong nơi lưu trữ gốc.

## 13. Kiểm chứng trong lab

Mục tiêu của lab là xác nhận quyền xuất hiện đúng lúc, đúng phạm vi và biến mất theo chính sách. Dùng máy lab có khả năng phục hồi, tài khoản thử và dịch vụ vô hại.

### 13.1. Trước khi cấp

Xác nhận tài khoản không có quyền quản trị thường trực và không có grant khác gây nhiễu kết quả. Ghi nhận cấu hình hiệu lực từ cơ chế quản lý của lab.

Một số lệnh quan sát có thể hữu ích:

```bash
# Danh tính và groups của tiến trình shell hiện tại
id

# Thông tin nhóm được tra cứu cho tài khoản qua cơ chế của hệ thống
id opsdemo

# Các quyền sudo mà chính sách hiện tại hiển thị cho người dùng
sudo -l
```

`id` trong shell hiện tại và `id opsdemo` có thể phản ánh hai góc nhìn khác nhau khi membership vừa thay đổi. Không dùng một kết quả đơn lẻ để suy ra rằng mọi tiến trình đã nhận cùng trạng thái.

`sudo -l` có thể yêu cầu xác thực và chịu ảnh hưởng cấu hình local. Danh sách quyền không thay thế việc kiểm tra một hành động qua đúng điểm thực thi.

### 13.2. Trong cửa sổ quyền

Sau khi grant chuyển `ACTIVE`, thực hiện tác vụ đã được phê duyệt:

```bash
sudo /usr/bin/systemctl restart pam-demo.service
```

Chỉ dùng lệnh này nếu đường dẫn và dịch vụ lab đã được xác minh. Kiểm tra kết quả dịch vụ và audit event liên kết với tài khoản, grant, máy đích.

Kiểm tra một tác vụ không được cấp bị từ chối. Chọn phép thử vô hại, được phép trong lab, chẳng hạn đề nghị broker thực hiện một action ID ngoài allowlist. Không thực hiện lệnh phá hoại để “thử xem có root hay không”.

### 13.3. Sau hết hạn

Thử lại đúng hành động qua cùng đường truy cập. Cần phân biệt lỗi do grant hết hạn với lỗi xác thực hoặc dịch vụ không sẵn sàng.

Ví dụ, `sudo -n` thất bại vì cần nhập mật khẩu không chứng minh rule đã bị thu hồi. Phép thử phải xác minh quyết định phân quyền, không chỉ ghi nhận một exit code khác 0.

Kiểm tra cả phiên đã mở trước hạn và phiên mới. Đối chiếu quyền local, trạng thái broker, credential, phiên và tác vụ theo chính sách đã chọn.

### 13.4. Ma trận kịch bản tối thiểu

| Kịch bản | Kết quả cần quan sát |
| --- | --- |
| Dùng quyền trước notBefore | Bị từ chối |
| Đúng người, đúng máy, đúng tác vụ, trong hạn | Được phép và có audit event |
| Đúng grant nhưng sai máy hoặc sai tác vụ | Bị từ chối |
| Yêu cầu xếp hàng qua expiresAt | Kiểm tra lại trước thực thi |
| Grant hết hạn, mở yêu cầu mới | Bị từ chối theo biên thời gian cam kết |
| Người phê duyệt hủy quyền sớm | Thu hồi theo chính sách và có xác nhận |
| Đóng grant khi có phiên cũ | Phiên được xử lý đúng chính sách, không suy từ phiên mới |
| Grant hết hạn khi tác vụ đang chạy | Áp dụng đúng quy tắc dừng hoặc tiếp tục có giám sát |
| Máy đích reboot trong cửa sổ quyền | Không phục hồi một grant đã hết hạn |
| Cleanup gặp lỗi | Trạng thái chưa hoàn tất, có cảnh báo và đối soát |
| Hai grant chồng lấp | Thu hồi đúng grant, không giữ hoặc xóa nhầm quyền |
| Mất kết nối với control plane | Hành vi offline đúng giới hạn đã công bố |

Mỗi test cần có bằng chứng từ điểm thực thi. Không chỉ chụp màn hình cổng PAM hiển thị “Expired”.

## 14. Các sai lầm thường gặp và cách sửa

### “Thêm vào sudo group rồi xóa sau là xong”

Cách này có thể cấp toàn quyền, gặp cache danh tính, để lại quyền trong phiên cũ và không xử lý tiến trình root. Sửa bằng cách ưu tiên tác vụ hẹp, theo dõi grant tới điểm thực thi và kiểm tra cả phiên hiện có.

### “Đặt timeout sudo 15 phút là quyền hết hạn sau 15 phút”

Thời gian cache xác thực khác thời gian tồn tại của quyền. Sửa bằng cách quản lý grant và cơ chế thu hồi rõ ràng, sau đó kiểm chứng khả năng dùng quyền khi đã xác thực lại đúng cách.

### “Chứng thư SSH hết hạn thì mọi root session dừng”

Credential và kết nối có vòng đời khác nhau. Sửa bằng chính sách phiên và công việc đang chạy; kiểm tra thực tế trên đường truy cập được quản lý.

### “Cho chạy một editor dưới root vẫn là một lệnh”

Editor và nhiều công cụ đa năng có thể ghi file, gọi chương trình khác hoặc cung cấp shell escape. Sửa bằng hành động chuyên biệt hoặc một quy trình chỉnh sửa cấu hình được thiết kế và kiểm soát, không dùng số lượng binary làm thước đo duy nhất cho phạm vi quyền.

### “Đã gửi lệnh revoke tức là đã thu hồi”

Máy đích có thể offline hoặc cleanup thất bại. Sửa bằng trạng thái chờ xác nhận, retry có kiểm soát, đối soát và kiểm tra đường sử dụng thực tế.

### “Root chỉ 5 phút nên không cần xem thay đổi bền vững”

Năm phút vẫn đủ để tạo đường truy cập tồn tại lâu dài. Sửa bằng giảm năng lực, bảo vệ tài nguyên phụ thuộc, giám sát ngoài máy và rà soát thay đổi theo rủi ro của tác vụ.

### “Gia hạn tự động giúp người dùng không bị gián đoạn”

Nếu mọi heartbeat đều kéo dài quyền, đặc quyền có thể thành thường trực. Sửa bằng đánh giá lại, giới hạn thời gian liên tục và lưu bằng chứng phê duyệt gia hạn.

## 15. Bài tập tình huống

Một nhóm vận hành triển khai cơ chế sau:

1. Người dùng xin root cho ticket khẩn.
2. Hệ thống thêm tài khoản vào nhóm quản trị trong 20 phút.
3. Người dùng mở `sudo -i`, sau đó chạy một công việc nền.
4. Hết 20 phút, control plane xóa membership và ghi trạng thái `REVOKED`.
5. Phiên root vẫn hoạt động; node bị mất kết nối trước khi nhận lệnh cleanup bổ sung.

Hãy phân tích các điểm sau:

- Hệ thống đã thu hồi nguồn cấp quyền hay đã thu hồi toàn bộ khả năng root?
- Phiên root hiện tại, công việc nền và membership mới có cùng vòng đời không?
- Bằng chứng nào cần có trước khi chốt thu hồi hoàn tất?
- Chính sách offline và cách kết thúc tác vụ cần được thiết kế thế nào?
- Nếu mục tiêu chỉ là restart một dịch vụ, có cần root shell không?

Một hướng giải quyết hợp lý là thay root shell bằng tác vụ restart đã định nghĩa, kiểm tra grant tại thời điểm thực thi, quản lý thời hạn ở điểm thực thi và đối soát cấu hình local. Nếu công việc thực sự cần root tương tác, phải công bố giới hạn cưỡng chế của quyền root, quản lý phiên và tác vụ đang chạy, lưu bằng chứng độc lập và xử lý trạng thái chưa xác nhận khi node offline.

Không thể kết luận phiên và tiến trình đã mất quyền chỉ từ việc xóa một dòng membership trong directory.

## 16. Tiêu chí hoàn thành một thiết kế temporary root access

Thiết kế đạt yêu cầu khi có thể giải thích và kiểm chứng được đồng thời:

- Danh tính cá nhân, tài nguyên và tác vụ được ràng buộc rõ ràng.
- Quyền được cấp trong cửa sổ thời gian có kiểm soát.
- Quyền hẹp đủ thực hiện công việc, với tài nguyên phụ thuộc được bảo vệ.
- Lệnh hoặc phiên mới bị từ chối sau hạn theo đúng biên thời gian cam kết.
- Phiên và công việc đã tồn tại được xử lý theo chính sách rõ ràng.
- Gia hạn, mất kết nối, reboot, quyền chồng lấp và cleanup lỗi có hành vi xác định.
- Bằng chứng liên kết được từ yêu cầu tới sử dụng và thu hồi.
- Quyền root toàn phần không bị trình bày như một ranh giới cô lập mà nó không cung cấp.

Temporary root access hiệu quả là một vòng đời đặc quyền có điểm thực thi và bằng chứng kiểm chứng. TTL chỉ là một thành phần của vòng đời đó.
