# Hardening admin workstation

## 1. Máy trạm quản trị là một phần của đường đặc quyền

Admin workstation là thiết bị hoặc môi trường làm việc dùng để thực hiện tác vụ quản trị nhạy cảm. Hardening là quá trình giảm khả năng bị xâm nhập, giới hạn tác động nếu xảy ra sự cố và duy trì những điều kiện bảo vệ đó trong suốt vòng đời thiết bị.

Trong PAM, máy trạm có thể mở portal, sử dụng MFA, kích hoạt grant và điều khiển phiên tới máy production. Nếu thiết bị bị kiểm soát, tác nhân có thể can thiệp vào phiên, đọc dữ liệu hiển thị hoặc thực hiện hành động bằng danh tính người đang đăng nhập.

Microsoft nhấn mạnh rằng mức bảo đảm của phiên đặc quyền bị giới hạn bởi mức bảo vệ của thiết bị khởi tạo. Jump server hoặc tài nguyên đích được bảo vệ tốt không tự loại bỏ rủi ro từ endpoint nguồn bị kiểm soát. [Microsoft — Privileged access devices](https://learn.microsoft.com/en-us/security/privileged-access-workstations/privileged-access-devices)

Do đó, hardening không chỉ là bật một sản phẩm chống mã độc hoặc đánh dấu máy “compliant”. Nó cần kết nối thiết bị, danh tính, công cụ quản trị, mạng, PAM và bằng chứng vận hành.

Bài học thuộc chương Admin workstation, tập trung vào thiết bị phục vụ người quản trị hạ tầng nhạy cảm. Các profile và quy trình dưới đây là mô hình tham khảo; cấu hình thật phải phù hợp hệ điều hành, phần cứng, giao thức quản trị và khả năng thực thi của tổ chức.

## 2. Xác định tài sản cần bảo vệ và ranh giới sử dụng

### 2.1. Không chỉ bảo vệ mật khẩu

| Tài sản hoặc khả năng | Vì sao nhạy cảm? |
|---|---|
| Phiên đăng nhập PAM/IdP | Có thể dẫn tới kích hoạt hoặc sử dụng quyền |
| Token, ticket và credential trong bộ nhớ | Có thể phục vụ truy cập tiếp theo theo giao thức |
| Authenticator và private key thiết bị | Tham gia chứng minh danh tính |
| Dữ liệu hiển thị trong phiên | Có thể chứa cấu hình, log hoặc thông tin nhạy cảm |
| Công cụ quản trị và script | Có thể thực hiện thay đổi trên nhiều tài nguyên |
| Quyền quản trị máy trạm | Có thể sửa chính môi trường dùng quyền đặc biệt |
| Agent và kênh quản lý tập trung | Có thể triển khai mã hoặc thay policy trên thiết bị |

MFA giúp bảo vệ bước xác thực, nhưng không xác nhận mọi thao tác sau đó là ý định đúng của người dùng. Credential không xuất khỏi authenticator cũng không tự bảo vệ nội dung phiên khỏi một endpoint đã bị kiểm soát.

### 2.2. Tách công việc đặc quyền khỏi nội dung rủi ro cao

Một máy dùng cho tác vụ quản trị mạnh nên có phạm vi sử dụng rõ. Email thông thường, duyệt web tùy ý, tài khoản cá nhân, công cụ giải trí hoặc môi trường thử mã không kiểm soát làm tăng bề mặt tiếp xúc.

Microsoft phân biệt việc duyệt web phổ thông với việc dùng browser để vào một tập website quản trị đã biết; hướng dẫn PAW giới hạn ứng dụng và hoạt động ngoài nhiệm vụ đặc quyền. [Microsoft — Device roles and profiles](https://learn.microsoft.com/en-us/security/privileged-access-workstations/privileged-access-devices)

Trong thiết kế của bài, người quản trị có môi trường làm việc thông thường riêng. Tài khoản quản trị không được sử dụng như tài khoản duyệt email hoặc đăng nhập tùy ý trên máy thông thường.

Chỉ tạo một browser profile khác không tạo ra ranh giới tương đương hai môi trường được bảo vệ. Các profile vẫn có thể chung hệ điều hành và những quyền kiểm soát bên dưới.

### 2.3. Môi trường ảo không tự tạo nguồn sạch

Một desktop quản trị từ xa có thể giúp tập trung quản lý và giới hạn dữ liệu, nhưng cần xét cả thiết bị điều khiển nó. Nếu host nguồn không đáng tin, kênh nhập liệu, hiển thị hoặc phiên truy cập từ host đó vẫn là rủi ro cần xử lý.

Không nên gọi một VM là PAW chỉ vì bên trong đã bật vài policy. Cần đánh giá hypervisor/host, đường quản lý, cách xác thực, clipboard, thiết bị chuyển tiếp và quyền truy cập console.

## 3. Xây baseline từ nguồn có kiểm soát

### 3.1. Kiểm kê và gắn chủ sở hữu

Mỗi thiết bị cần có định danh tài sản, người hoặc nhóm chịu trách nhiệm, mục đích quản trị, mức nhạy cảm và những hệ thống được phép tiếp cận.

Baseline nên chỉ rõ:

- Loại phần cứng và hệ điều hành được hỗ trợ.
- Nguồn cài đặt, firmware, driver và ứng dụng.
- Cấu hình boot, mã hóa và bảo vệ credential cần thiết.
- Quyền cục bộ, phần mềm được chạy và đường mạng được phép.
- Agent quản lý, phát hiện sự cố và chuyển bằng chứng.
- Điều kiện để được dùng PAM và cách xử lý lệch cấu hình.
- Quy trình thay thế, recovery và thu hồi thiết bị.

Không dùng một bản checklist chung rồi coi mọi máy đã đạt cùng mức bảo vệ. Một số kiểm soát phụ thuộc phần cứng, phiên bản hoặc cách tích hợp.

### 3.2. Provisioning trước khi dùng quyền mạnh

Một luồng minh họa:

```mermaid
flowchart LR
    A[Tiếp nhận và kiểm kê thiết bị] --> B[Cài đặt từ nguồn được quản lý]
    B --> C[Áp baseline, cập nhật và agent]
    C --> D[Kiểm tra trạng thái thực tế]
    D --> E[Đăng ký device identity]
    E --> F[Cho phép đường PAM phù hợp]
    F --> G[Giám sát drift và bảo trì]
    G --> H[Thu hồi hoặc tái cấp khi cần]
```

Đăng ký một máy đã có dấu hiệu xâm nhập vào hệ thống quản lý không tự làm nó an toàn. Nếu không có căn cứ về trạng thái ban đầu, cần xử lý theo quy trình xác minh hoặc tái cấp thiết bị phù hợp.

### 3.3. Desired state khác với effective state

Policy đã được gửi xuống không đồng nghĩa đã có hiệu lực. Có thể còn chờ reboot, phần cứng không hỗ trợ, agent lỗi hoặc một cấu hình khác ghi đè.

Cần kiểm tra kết quả thực tế và giữ reference của lần đánh giá. Ví dụ, bản ghi cho biết “mã hóa đã được yêu cầu” chưa đủ để kết luận volume đang được bảo vệ.

## 4. Bảo vệ boot, lưu trữ và tiếp cận vật lý

### 4.1. Chuỗi khởi động và firmware

Tùy nền tảng, baseline có thể yêu cầu firmware được quản lý, cơ chế xác minh boot, bảo vệ cấu hình khởi động và cập nhật từ nguồn được phép.

Cần kiểm tra khả năng thật, cách khóa cấu hình phù hợp và quy trình khôi phục khi thay phần cứng hoặc cập nhật firmware. Không bật một cơ chế làm máy không khởi động được rồi giải quyết bằng cách tắt toàn bộ bảo vệ.

Một lần kiểm tra boot đạt yêu cầu không tự chứng minh mọi phần mềm chạy sau đó không có lỗ hổng hoặc không bị lạm dụng. Đây là một lớp bảo vệ trong chuỗi.

### 4.2. Mã hóa ổ đĩa và recovery key

Mã hóa volume giúp bảo vệ dữ liệu khi thiết bị bị mất, bị lấy cắp hoặc bị xử lý không phù hợp lúc loại bỏ. BitLocker là một ví dụ trên Windows; hiệu lực và yêu cầu triển khai phụ thuộc cấu hình, phần cứng và chính sách. [Microsoft — BitLocker](https://learn.microsoft.com/en-us/windows/security/operating-system-security/data-protection/bitlocker/)

Trong thiết kế PAM, cần bảo vệ cả recovery key:

- Lưu ở kho do tổ chức quản lý với quyền truy cập riêng.
- Ghi nhận ai đã xem hoặc sử dụng.
- Có cách lấy lại khi cần mà không phụ thuộc hoàn toàn vào máy đang lỗi.
- Không lưu bản dễ truy cập cùng thiết bị hoặc trong ticket phổ thông.
- Xử lý vòng đời key theo sự kiện và khả năng nền tảng.

Mã hóa dữ liệu trên đĩa không thay thế bảo vệ phiên đang mở. Khi hệ thống đã cho người dùng hợp lệ đọc dữ liệu, cần kiểm soát process, phiên và quyền truy cập trong trạng thái đang chạy.

### 4.3. Khóa màn hình và trạng thái không sử dụng

Thiết bị cần có cách khóa khi không sử dụng và chính sách mở lại phù hợp. Việc đóng nắp, sleep, hibernate hoặc remote disconnect có thể có ngữ nghĩa khác nhau theo nền tảng.

Cần định nghĩa trạng thái nào được chấp nhận trong môi trường có nguy cơ mất thiết bị, ai được mở lại và tác động tới phiên PAM. Không coi mọi dạng “màn hình không còn hiện” là tương đương với đăng xuất hoặc kết thúc quyền.

## 5. Danh tính cục bộ và bảo vệ credential

### 5.1. Người vận hành không nên mặc định là local admin

Người dùng thiết bị có thể cần quyền mạnh trên hệ thống đích nhưng không nhất thiết cần toàn quyền sửa máy trạm nguồn mỗi ngày.

Tách khả năng vận hành công cụ khỏi khả năng tắt agent, sửa trust store, cài driver hoặc thay policy giúp giảm đường tăng quyền trên nguồn quản trị. Khi cần bảo trì local, có thể dùng quyền có hạn theo quy trình được quản lý.

Không chia sẻ một mật khẩu local admin cho mọi PAW. Tài khoản dự phòng cục bộ cần được quản lý, giới hạn sử dụng và có bằng chứng tương ứng.

### 5.2. Giảm việc credential mạnh xuất hiện trên máy trạm

Ưu tiên mô hình PAM cho broker sử dụng credential đích khi tích hợp hỗ trợ và tác vụ không cần người dùng nhìn giá trị secret. Chỉ cấp khả năng đọc secret khi có nhu cầu và quyết định riêng.

Không đưa mật khẩu quản trị vào script, shortcut, command history hoặc cấu hình công cụ. Credential trong biến môi trường, file cấu hình và bộ nhớ cũng cần được xét theo loại ứng dụng; việc không hiển thị trên giao diện không đồng nghĩa không thể bị sử dụng.

Cần quản lý credential cache, phiên browser, SSH key, ticket và những cơ chế lưu đăng nhập theo giao thức thực tế. Không dùng một biện pháp cho mọi loại credential rồi tuyên bố đã bảo vệ toàn bộ.

### 5.3. Cơ chế cách ly credential có phạm vi cụ thể

Trên Windows, Credential Guard dùng VBS để cách ly một số secret được bảo vệ, như những credential liên quan NTLM/Kerberos theo phạm vi tính năng. Nó không thay thế mọi kiểm soát khác hoặc bảo vệ mọi token ứng dụng. [Microsoft — Credential Guard](https://learn.microsoft.com/en-us/windows/security/identity-protection/credential-guard/)

Khi áp dụng, cần xác minh khả năng phần cứng/phần mềm, trạng thái chạy thực tế và tương thích ứng dụng. Không chỉ nhìn tên hệ điều hành hoặc một checkbox cấu hình.

Với hệ điều hành khác, lựa chọn bảo vệ credential phải dựa trên cơ chế mà nền tảng hỗ trợ. Không áp dụng nguyên tên tính năng Windows cho mọi thiết bị trong đội quản trị.

### 5.4. Không mở rộng quyền qua cơ chế chuyển tiếp

Credential delegation, agent forwarding, clipboard chứa secret hoặc file cấu hình được copy sang máy đích có thể mở rộng nơi bằng chứng xác thực được sử dụng.

Cần biết cơ chế nào đang bật, tác vụ có thực sự cần không và bên nhận có thể làm gì. Không bật chuyển tiếp chỉ để giảm một lần nhập liệu khi nó làm tăng phạm vi tin cậy ngoài yêu cầu.

## 6. Giảm bề mặt phần mềm được chạy

### 6.1. Danh mục công cụ đủ cho công việc

Một máy trạm quản trị cần có công cụ cần thiết và nguồn cung cấp rõ: browser quản trị, client PAM, terminal, công cụ cloud hoặc phần mềm hỗ trợ tác vụ đã được chấp nhận.

Thiếu công cụ có thể thúc đẩy người dùng tải bản không kiểm soát hoặc quay về máy thông thường. Vì vậy, hardening cần đi cùng cách yêu cầu và phân phối phần mềm nhanh nhưng có thẩm quyền.

Không dùng PAW làm nơi build thử, chạy package tùy ý hoặc kiểm tra script từ Internet. Công cụ có interpreter, plugin hoặc extension cần được quản lý như một khả năng chạy mã.

### 6.2. Application control cần được thiết kế và kiểm tra

Application control có thể giới hạn phần mềm được phép chạy dựa trên policy. Microsoft cung cấp hướng dẫn riêng về thiết kế trust, code signing, quản lý plugin và triển khai chế độ audit/enforcement trên Windows. [Microsoft — Application Control](https://learn.microsoft.com/en-us/windows/security/application-security/application-control/app-control-for-business/)

Trong mô hình bài học, quy trình triển khai gồm:

1. Xác định tập công cụ và luồng công việc hợp lệ.
2. Chọn cách xác lập trust phù hợp, không chỉ dựa vào thư mục dễ ghi.
3. Kiểm tra script, module, interpreter, plugin và công cụ cập nhật.
4. Quan sát các tác vụ thật trong pilot.
5. Áp enforcement khi có đủ dữ liệu và đường xử lý lỗi.
6. Theo dõi ngoại lệ, thay phiên bản và các phần mềm không còn cần.

Phần mềm có chữ ký không tự có nghĩa không thể bị lạm dụng hoặc không có lỗ hổng. Baseline vẫn cần quản lý phiên bản, cấu hình và khả năng mà công cụ cung cấp.

Một policy chỉ cho chạy công cụ hợp lệ nhưng cho công cụ đó tải và chạy mã tùy ý có thể chưa đạt mục tiêu. Cần xét toàn bộ luồng thực thi thay vì chỉ tên executable ban đầu.

### 6.3. Browser quản trị cần cấu hình riêng

Browser thường là cửa vào IdP, PAM và console cloud. Cần quản lý extension, profile, đồng bộ dữ liệu, tải xuống và những website được phép theo nhiệm vụ.

Không đồng bộ profile cá nhân hoặc password store cá nhân vào môi trường đặc quyền. Extension cũng có thể tiếp cận nội dung trang hoặc phiên theo quyền của nó, nên cần giới hạn và review.

Việc hạn chế website không thay thế kiểm tra TLS, tên dịch vụ và cơ chế xác thực chống phishing. Ngược lại, MFA mạnh không làm mọi extension trở nên an toàn.

## 7. Mạng, giao thức và dữ liệu đi qua phiên

### 7.1. Chỉ mở những đường cần thiết

Máy trạm cần tiếp cận đúng các dịch vụ để vận hành: IdP, PAM, broker, nguồn cập nhật, quản lý thiết bị, DNS, đồng bộ thời gian và telemetry phù hợp với kiến trúc.

Một danh sách egress không được thiếu những phụ thuộc cần thiết rồi buộc người dùng tắt firewall. Cần kiểm kê và kiểm tra các đường chính, failover và recovery.

Đường tới tài nguyên nhạy cảm nên theo mô hình đã chọn, chẳng hạn chỉ tới cổng PAM/broker từ endpoint người dùng. Nếu vẫn có đường quản trị trực tiếp, cần biết ai được dùng và nó chịu policy nào.

Máy nằm trong VPN không tự đáp ứng mọi điều kiện thiết bị. Nguồn mạng, danh tính và trạng thái máy trạm phải được xét riêng.

### 7.2. Không bỏ kiểm tra danh tính máy chủ

Khi công cụ gặp lỗi certificate, host key hoặc trust chain, không nên cấu hình bỏ kiểm tra để “cho chạy được”. Cần xử lý đúng nguồn trust, tên dịch vụ và thay đổi hợp lệ.

Một đường mạng nội bộ cũng có thể chứa thành phần bị cấu hình sai hoặc bị kiểm soát. Bảo vệ kênh và xác minh bên nhận vẫn có ý nghĩa.

Kênh quản lý thiết bị và cập nhật có thể triển khai mã lên PAW, nên cũng cần danh tính, quyền và bảo vệ riêng. Một tài khoản hỗ trợ rộng trên hệ thống quản lý có thể trở thành đường tác động tới nhiều máy đặc quyền.

### 7.3. Clipboard, file transfer và thiết bị chuyển tiếp

Các kênh phụ có thể đưa dữ liệu hoặc mã qua ranh giới phiên. Cần quyết định từng loại:

| Kênh | Câu hỏi cần xác định |
|---|---|
| Clipboard | Cho text hay file; có chứa secret không; chiều nào được phép? |
| File transfer | Ai được gửi/nhận; file được kiểm tra và lưu ở đâu? |
| Drive redirection | Máy đích có thể tiếp cận dữ liệu trên PAW không? |
| USB hoặc thiết bị chuyển tiếp | Tác vụ nào cần; có ảnh hưởng authenticator không? |
| In hoặc export | Dữ liệu nhạy cảm có thể được đưa ra ngoài bằng cách nào? |
| Remote support | Ai điều khiển; người dùng có biết; audit bao phủ gì? |

Không cần cấm mọi thiết bị ngoại vi một cách máy móc: phương thức xác thực hoặc thiết bị trợ năng có thể cần hỗ trợ. Nhưng những khả năng cần thiết phải được cấp có chủ ý và kiểm tra, không để mặc định mở mọi kênh.

## 8. Patch, telemetry và chống lệch cấu hình

### 8.1. Cập nhật là hoạt động liên tục

Baseline cần bao gồm hệ điều hành, firmware, driver, browser, client PAM, SDK/công cụ quản trị và extension. Một máy có OS mới nhưng công cụ quản trị cũ vẫn có thể có khoảng trống.

Tổ chức cần xác định thời hạn xử lý theo mức độ và tác động, nguồn phát hành, cách kiểm tra tương thích, vòng pilot và cách xác nhận cập nhật có hiệu lực. Không có một con số thời gian chung phù hợp cho mọi lỗ hổng và mọi thiết bị.

Khi rollback, cần xét việc có đưa trở lại phiên bản hoặc cấu hình đã bị loại do rủi ro hay không. “Bản trước chạy được” không tự đồng nghĩa có thể dùng cho tác vụ đặc quyền hiện tại.

### 8.2. Agent đang cài không đồng nghĩa đang bảo vệ

Cần biết agent phát hiện sự cố, quản lý cấu hình và chuyển log còn hoạt động không, có bị tắt hoặc quá lâu không kết nối không. Những dữ liệu này cần gắn với device identity và thời điểm quan sát.

Một trạng thái “healthy” không chứng minh tuyệt đối không có xâm nhập. Nó là một tín hiệu trong mô hình rủi ro, có giới hạn phát hiện và độ mới.

### 8.3. Drift phải dẫn tới hành động rõ

Ví dụ về drift:

- Người dùng được thêm vào local administrators ngoài quy trình.
- Application control không còn enforcement theo baseline.
- Một extension mới có quyền không được chấp nhận.
- Dịch vụ telemetry bị tắt hoặc không còn đủ mới.
- Thiết bị không áp dụng patch bắt buộc trong thời hạn.
- Trust store hoặc cấu hình proxy thay đổi ngoài thẩm quyền.

Policy cần xác định drift nào chặn quyền mới, drift nào đưa máy vào luồng khắc phục và drift nào cần ứng phó sự cố. Không chỉ tạo dashboard rồi để máy tiếp tục sử dụng mọi grant.

## 9. Gắn device posture với quyết định PAM

### 9.1. Posture phải có nguồn và độ mới

Một payload do client tự gửi như `compliant: true` không đủ để chứng minh thiết bị đáp ứng baseline. PAM cần nhận dữ liệu từ nguồn được tin cậy và liên kết nó với đúng thiết bị, phiên hoặc lần tương tác theo kiến trúc.

Những câu hỏi cần trả lời:

| Câu hỏi | Ý nghĩa |
|---|---|
| Device identity được xác minh thế nào? | Tránh chỉ dựa vào hostname hoặc nhãn tự khai |
| Ai đánh giá posture? | Biết nguồn và thẩm quyền dữ liệu |
| Dữ liệu còn mới không? | Không dùng một kết quả cũ vô thời hạn |
| Baseline nào được áp dụng? | Phân biệt profile quản trị với máy làm việc thường |
| Có trạng thái unknown không? | Không biến thiếu dữ liệu thành đạt yêu cầu |
| Kiểm tra ở bước nào? | Login, kích hoạt, reconnect hoặc đánh giá lại |
| Drift tác động tới phiên ra sao? | Biết cách ngăn quyền mới và xử lý quyền đang dùng |

Không phải mọi tổ chức đều có cùng khả năng attestation hoặc đánh giá liên tục. Cần ghi rõ những gì thực sự được đo và thực thi, tránh hứa một mức bảo vệ không có nguồn dữ liệu hỗ trợ.

### 9.2. Posture tốt không thay thế authorization

Trong mô hình của bài, mở phiên production cần đồng thời:

```text
Danh tính cá nhân hợp lệ
AND mức xác thực và độ mới phù hợp
AND device identity và posture đạt chính sách
AND role/assignment áp dụng đúng scope
AND grant còn hiệu lực cho đúng tài nguyên và profile
AND broker/recording bắt buộc sẵn sàng
```

Máy đạt baseline không cho người dùng quyền trên mọi hệ thống. Grant đã được duyệt cũng không cho phép sử dụng từ một thiết bị không đáp ứng điều kiện bắt buộc.

### 9.3. Giới hạn giữa kiểm tra lúc đầu và trong phiên

Nếu chỉ đánh giá posture lúc kích hoạt, không được mô tả như đã kiểm tra mọi thay đổi trong suốt phiên. Muốn phản ứng khi thiết bị bị đánh dấu rủi ro, cần có kênh sự kiện, ánh xạ phiên, giới hạn độ trễ và điểm thực thi.

Kết thúc phiên PAM không tự ngăn mọi task nền hoặc credential đã tiết lộ trên đích. Thiết kế thu hồi cần xét phạm vi thực tế.

## 10. Ví dụ: PAW cho chẩn đoán production

### 10.1. Mục tiêu

Kỹ sư trực ca cần đọc trạng thái và log vận hành đã giới hạn trên một máy thanh toán. Tác vụ không cần tải công cụ tùy ý, nhận mật khẩu đích hoặc mở shell quản trị toàn quyền.

Tổ chức cấp PAW với profile riêng và đường tới broker. Môi trường email, duyệt web thông thường và phát triển phần mềm nằm trên thiết bị/môi trường khác theo mô hình đã quản lý.

### 10.2. Profile ý định minh họa

```yaml
device_profile_ref: privileged-workstation-v5
usage:
  administrative_tasks_only: true
  personal_profile_sync: denied
local_privilege:
  operator_is_local_admin: false
  maintenance_requires_authorized_temporary_access: true
platform:
  supported_os_and_firmware: required
  approved_boot_protection: required
  disk_encryption_verified: required
  credential_protection_profile: required
software:
  managed_application_catalog: required
  execution_policy: approved_applications
  browser_extensions: approved_set
network:
  management_path_ref: approved-pam-broker-path
  arbitrary_management_bypass: denied
security_signals:
  device_identity: required
  posture_source_ref: approved-device-management
  freshness_policy_ref: privileged-device-freshness-v2
pam:
  grant_required: true
  target_profile_ref: diagnostic-readonly
  target_secret_disclosure: denied
  recording_required: true
```

Đây là dữ liệu giả mô tả mục tiêu, không phải một cấu hình có thể nhập trực tiếp vào hệ điều hành hoặc PAM. Mỗi yêu cầu phải được ánh xạ tới kiểm soát có thật và kiểm tra trạng thái thực tế.

### 10.3. Luồng sử dụng

1. Thiết bị được cấp từ nguồn kiểm soát và áp baseline.
2. Dịch vụ quản lý xác nhận device identity cùng posture theo policy.
3. Kỹ sư đăng nhập bằng danh tính cá nhân và phương thức xác thực phù hợp.
4. PAM kiểm tra posture, role, scope và grant trước khi mở phiên.
5. Broker dùng credential đúng profile, không tiết lộ password cho endpoint.
6. Tài khoản/JEA trên đích giới hạn khả năng chẩn đoán.
7. Recording và audit liên kết actor, device, grant và session.
8. Khi kết thúc, quyền có hạn và trạng thái phiên được đối soát.

Một công cụ đã được phép chạy trên PAW không tự được phép thao tác mọi tài nguyên. Nó vẫn phải dùng đúng identity và chịu authorization.

### 10.4. Một số tình huống cần phản ứng

| Tình huống | Hành vi mong muốn |
|---|---|
| Kỹ sư dùng máy làm việc thường để kích hoạt grant | Không coi là đạt profile PAW |
| PAW thiếu dữ liệu posture bắt buộc | Chưa cho quyền nhạy cảm theo nhánh thông thường |
| Agent báo drift nghiêm trọng | Chặn quyền mới và xử lý phiên chịu ảnh hưởng theo policy |
| Cần một công cụ chưa có trong danh mục | Đi qua luồng phân phối/ngoại lệ có thẩm quyền |
| Recorder lỗi | Không tự chuyển sang đường trực tiếp |
| Kỹ sư cần đọc password dù grant chỉ cho phiên | Yêu cầu quyền riêng; không suy ra từ khả năng mở phiên |
| Công cụ báo lỗi TLS | Xử lý trust/configuration, không bỏ xác minh tùy tiện |

## 11. Vận hành, ngoại lệ và phục hồi thiết bị

### 11.1. Thay baseline theo vòng có kiểm chứng

Thay đổi hardening có thể ảnh hưởng công cụ, driver, authenticator hoặc luồng remote access. Cần có môi trường kiểm tra và pilot đại diện cho tác vụ thật.

Quy trình nên ghi trạng thái trước/sau, người thay đổi, tác vụ đã kiểm tra và phần chưa xác nhận. Khi một kiểm soát gây lỗi, cần xác định nguyên nhân cụ thể trước khi tạo ngoại lệ.

Ngoại lệ có thể chỉ áp dụng cho một ứng dụng, phiên bản, thiết bị hoặc thời hạn. Tránh biến một sự cố tương thích cục bộ thành việc tắt bảo vệ cho toàn bộ đội quản trị.

### 11.2. Recovery không trở thành đường tăng quyền thường trực

Cần chuẩn bị trường hợp mất authenticator, thiết bị hỏng, cập nhật lỗi hoặc mất kết nối quản lý. Có thể cần thiết bị dự phòng đã được cấp theo baseline và quy trình recovery riêng.

Không đăng nhập tài khoản quản trị mạnh trên một máy tùy ý chỉ vì PAW đang lỗi. Nếu có break-glass, phải có danh tính, scope, thời hạn, bằng chứng và hậu kiểm rõ.

Quyền hỗ trợ PAW cũng cần được cấp và giám sát. Một nhân viên hỗ trợ có thể điều khiển máy trạm đang giữ phiên đặc quyền, nên remote support không phải hoạt động vô hại chỉ vì có ticket.

### 11.3. Cách ly khi nghi xâm nhập

Một luồng ứng phó có thể gồm:

1. Ghi nhận thiết bị, actor, thời gian và các phiên liên quan.
2. Hạn chế hoặc cô lập theo thẩm quyền, cân nhắc tác động vận hành.
3. Ngăn thiết bị nhận quyền mới.
4. Xử lý phiên IdP, PAM, broker và grant chịu ảnh hưởng.
5. Đánh giá credential hoặc dữ liệu có thể đã bị lộ.
6. Bảo toàn bằng chứng cần thiết.
7. Xác định cách tái cấp hoặc khôi phục từ nguồn tin cậy.
8. Kiểm tra lại trước khi cho sử dụng quyền đặc biệt.

Chỉ gỡ một process hoặc quét không thấy cảnh báo chưa đủ để tự kết luận máy đã trở lại trạng thái tin cậy. Cách phục hồi phụ thuộc loại sự cố và mức bảo đảm cần thiết.

Nếu tái cấp máy với device identity mới, cần giữ quan hệ điều tra với tài sản cũ nhưng không tự cho credential hoặc trust cũ sống lại. Cấp lại trạng thái compliant phải dựa trên kết quả hiện tại.

### 11.4. Loại bỏ và bàn giao

Khi thiết bị hết nhiệm vụ, cần thu hồi device identity, quyền truy cập, credential liên quan và xử lý dữ liệu theo quy trình. Không chỉ xóa tên thiết bị khỏi danh sách quản lý.

Bàn giao cho người khác cần xem lại tài khoản, profile, certificate, cache và bằng chứng cần giữ. Một tên tài sản không đổi không có nghĩa mọi quan hệ quyền trước đó vẫn phù hợp.

## 12. Bằng chứng và đánh giá hiệu lực

### 12.1. Những gì cần chứng minh

| Nhóm bằng chứng | Câu hỏi |
|---|---|
| Inventory | Máy nào, ai chịu trách nhiệm, được dùng cho mức quyền nào? |
| Baseline | Phiên bản nào, thay đổi gì, ai có thẩm quyền? |
| Effective state | Kiểm soát có thực sự hoạt động, lúc nào được xác nhận? |
| Software | Công cụ và extension nào được cài/chạy, nguồn nào? |
| Local privilege | Ai có quyền sửa máy, quyền tạm bắt đầu/kết thúc ra sao? |
| PAM use | Thiết bị gắn với actor, grant và session nào? |
| Drift/incident | Dấu hiệu nào, quyết định gì, kết quả thực thi ra sao? |
| Recovery | Máy được tái cấp hoặc trở lại sử dụng bằng căn cứ nào? |

Không cần sao chép secret để chứng minh một công cụ có khả năng sử dụng credential. Log cần tránh password, token phiên, private key, recovery key và dữ liệu không cần thiết.

Telemetry thiết bị cũng có thể chứa thông tin nhạy cảm về tác vụ hoặc người dùng. Cần quản lý quyền xem, export và lưu giữ phù hợp với mục đích.

### 12.2. Không chỉ đo số máy được gán policy

Các chỉ số hữu ích có thể gồm tỷ lệ thiết bị thực sự đạt baseline, độ mới posture, thời gian tồn tại drift, mức tuân thủ cập nhật, ngoại lệ quá hạn và thời gian xác nhận thu hồi quyền khi mất thiết bị.

Một thiết bị “đã enroll” nhưng lâu không có dữ liệu không nên được coi như thiết bị vừa được xác minh. Ngược lại, không nên đánh giá chất lượng hardening chỉ bằng số công cụ bị chặn mà bỏ qua khả năng hoàn thành tác vụ đúng đường.

### 12.3. Thực hành trên lab

Chọn một máy lab hoặc môi trường thử nghiệm không có credential production. Xây baseline cho một tác vụ hẹp: mở phiên chẩn đoán qua broker và đọc log được phép.

Định nghĩa nguồn cài đặt, quyền local, phần mềm được chạy, mạng cần thiết, cơ chế bảo vệ credential và điều kiện posture. Ghi cách xác nhận từng yêu cầu thay vì chỉ ghi “enabled”.

Sau đó kiểm tra các tình huống: công cụ ngoài danh mục; extension không được phép; tài khoản thường cố sửa policy; posture quá cũ; thay cấu hình proxy; lỗi certificate; recorder không sẵn sàng và yêu cầu mở phiên từ thiết bị không đạt profile.

Cuối cùng, mô phỏng một drift hoặc báo mất thiết bị bằng dữ liệu giả. Mô tả điểm chặn quyền mới, cách đối soát phiên còn chạy, credential có thể chịu ảnh hưởng và điều kiện cho thiết bị trở lại dùng PAM.

Đầu ra cần thể hiện một môi trường quản trị được bảo vệ theo vòng đời, không chỉ một ảnh cấu hình tại ngày cài đặt. Máy trạm phải hỗ trợ công việc cần thiết trong phạm vi rõ, còn PAM vẫn chịu trách nhiệm kiểm tra danh tính, quyền, thời hạn và bằng chứng cho từng lần sử dụng đặc quyền.
