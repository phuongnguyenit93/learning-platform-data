# Pass-the-hash

## 1. Pass-the-hash có ý nghĩa gì đối với PAM?

Pass-the-hash (PtH) dùng hash bị đánh cắp để xác thực mà không biết mật khẩu rõ. Bài này tập trung vào việc tái sử dụng **NT hash** qua NTLM trên Windows. MITRE ATT&CK định danh kỹ thuật này là T1550.002. [MITRE ATT&CK: Pass the Hash](https://attack.mitre.org/techniques/T1550/002/)

Với quản lý truy cập đặc quyền, câu hỏi cần trả lời không chỉ là “ai đã lấy mật khẩu?”. Một câu hỏi quan trọng hơn là: **nếu một thiết bị mất an toàn, vật liệu xác thực có trên thiết bị đó mở được những tài nguyên nào, trong bao lâu và bằng đường nào?**

Ví dụ, một kỹ thuật viên được phê duyệt sửa dịch vụ trên `APP-01`. Người này dùng tài khoản quản trị dùng chung và đăng nhập từ máy trạm làm việc hằng ngày. Nếu vật liệu xác thực của tài khoản bị lấy từ một điểm yếu trong chuỗi này, kẻ xấu có thể tìm cách dùng cùng danh tính tới `APP-02`, `FILE-01` hoặc các máy khác chấp nhận tài khoản đó. Việc biết tên công cụ đánh cắp chưa trả lời được phạm vi sự cố; cần biết quyền thực tế, đường mạng, giao thức và thời điểm.

Sau bài học, người học cần có khả năng:

- Phân biệt NT hash với mật khẩu rõ và bản ghi NTLM challenge-response.
- Nhận diện các điều kiện khiến một hash bị lộ trở thành khả năng di chuyển ngang.
- Kết hợp xác thực Windows, endpoint và phiên PAM để điều tra.
- Thiết kế least privilege, JIT/JEA, vault và rotation nhằm giảm phạm vi ảnh hưởng.
- Đề xuất cách kiểm chứng kiểm soát bằng dữ liệu giả lập và bằng chứng vận hành.

## 2. Cơ chế: vì sao không biết mật khẩu vẫn có thể xác thực?

### 2.1. NT hash là bí mật có khả năng dùng lại

Trong mô hình đơn giản hóa, Windows tính NT hash từ mật khẩu bằng MD4 trên biểu diễn UTF-16LE. Với NTLMv2, khóa phục vụ tính đáp ứng còn được dẫn xuất từ NT hash cùng tên người dùng và miền. Bởi vậy, có NT hash phù hợp có thể đủ để tính đáp ứng mới mà không phải khôi phục mật khẩu rõ. Đây là đặc tính của đường xác thực, không phải bằng chứng hash đã được “giải mã”. [Đặc tả Microsoft MS-NLMP: NTLM v2 Authentication](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-nlmp/5e550938-91d4-459f-b67d-75d70009e3f3)

Có thể hình dung luồng ở mức khái niệm:

```text
Bên yêu cầu nhận challenge của máy chủ
                    |
                    v
Dùng khóa dẫn xuất từ bí mật tài khoản để tính response
                    |
                    v
Máy chủ hoặc bên có thẩm quyền kiểm tra response
                    |
                    v
Nếu hợp lệ và chính sách cho phép: tạo ngữ cảnh truy cập
```

Hash không được gửi nguyên xi trong mọi gói tin. Tên gọi “pass-the-hash” mô tả việc dùng hash làm vật liệu xác thực thay cho mật khẩu rõ, không có nghĩa máy chủ chỉ so sánh một chuỗi hash do client gửi đến.

### 2.2. Không đánh đồng các dạng dữ liệu

| Dữ liệu | Hiểu đúng | Hệ quả khi điều tra |
| --- | --- | --- |
| Mật khẩu rõ | Bí mật người dùng nhập hoặc ứng dụng lưu | Có thể dùng ở nhiều luồng xác thực mà tài khoản được phép |
| NT hash | Giá trị liên quan trực tiếp tới bí mật mật khẩu Windows | Có thể bị dùng trong PtH ở những đường tương thích |
| NTLM challenge-response bắt trên mạng | Đáp ứng gắn với trao đổi xác thực cụ thể | Không đồng nhất với NT hash; không mặc định dùng lại như NT hash |
| Kerberos ticket | Vật liệu xác thực thuộc cơ chế Kerberos | Cần phân tích hướng pass-the-ticket hoặc kỹ thuật Kerberos liên quan |
| Cached domain logon verifier | Dữ liệu hỗ trợ đăng nhập domain khi không liên lạc được DC | Không mặc định coi là NT hash dùng trực tiếp cho PtH |

Đổi từ NTLMv1 sang NTLMv2 không loại bỏ ý nghĩa của việc giữ bí mật NT hash. Ngược lại, thấy một chuỗi có hình thức giống hash cũng chưa chứng minh có thể dùng nó để xác thực. Cần xác định đó là loại vật liệu gì, thuộc danh tính nào và hệ thống đích có chấp nhận đường xác thực tương ứng hay không.

Đối với vault, dữ liệu “không phải mật khẩu rõ” vẫn có thể là bí mật đặc quyền. Không đưa hash, ticket hoặc dữ liệu dump vào ticket hỗ trợ, màn hình phiên PAM hay ví dụ tài liệu.

## 3. Các điều kiện hình thành rủi ro thực tế

Một hash bị lộ không tự động mang lại quyền quản trị mọi máy. Cần phân tích chuỗi điều kiện sau.

### 3.1. Có vật liệu xác thực phù hợp

Nguồn rủi ro có thể là một endpoint bị chiếm quyền, bản sao lưu nhạy cảm, ảnh hệ thống hoặc kho dữ liệu chứa bí mật được bảo vệ không đầy đủ. Quyền và cách truy cập cần thiết khác nhau theo nguồn; không nên giả định người dùng thông thường luôn đọc được vật liệu này.

Đối với PAM, phải kiểm kê nơi tài khoản đặc quyền có thể xuất hiện: máy quản trị, máy đích, broker, dịch vụ chạy nền và công cụ tự động hóa. Danh sách tài khoản trong vault chỉ phản ánh một phần bề mặt phơi lộ nếu tài khoản vẫn được dùng trực tiếp ngoài broker.

### 3.2. Danh tính tương ứng vẫn được chấp nhận

Cần phân biệt tài khoản local và domain:

- Với tài khoản local, điều kiện nguy hiểm phổ biến là cùng mật khẩu quản trị được tái sử dụng trên nhiều máy. Danh tính local thuộc từng máy, nên cùng tên hiển thị không có nghĩa cùng SID.
- Với tài khoản domain, cần xem tài khoản có quyền đăng nhập và quyền trên những hệ thống nào. Tư cách tài khoản domain không đồng nghĩa quyền quản trị toàn miền.
- Tài khoản bị vô hiệu hóa, bị từ chối kiểu đăng nhập hoặc không còn quyền ở đích có thể không tạo được khả năng truy cập mong muốn.

Bằng chứng phải ghi rõ miền hoặc máy có thẩm quyền, SID khi có và thời điểm trạng thái được kiểm tra.

### 3.3. Có đường mạng và giao thức phù hợp

SMB, các đường quản trị từ xa và dịch vụ sử dụng Windows authentication cần được đặt trong ngữ cảnh cấu hình thực tế. Không kết luận mọi cổng RDP mở đều cho phép PtH; chế độ xác thực và chính sách của từng đường truy cập quyết định khả năng sử dụng.

Một máy chủ có thể chấp nhận danh tính nhưng firewall chỉ cho phép máy quản trị chuyên dụng kết nối. Ngược lại, vault bảo vệ tốt mật khẩu vẫn không bù được việc mọi máy trạm có thể truy cập cổng quản trị của toàn bộ server.

### 3.4. Quyền sau xác thực đủ cho hành động tiếp theo

Xác thực thành công và thực thi được hành động quản trị là hai sự kiện khác nhau. Token, membership, quyền trên tài nguyên, kiểu đăng nhập và chính sách máy đích tiếp tục giới hạn hành động.

Do đó, một kết quả kiểm thử cần tách:

```text
Đường mạng có thông?
    -> Xác thực có thành công?
        -> Tài khoản có được cấp quyền cần thiết?
            -> Hành động nào thực sự xảy ra?
```

Nếu chỉ có bằng chứng truy cập share đọc thông thường, không ghi báo cáo thành “đã chiếm toàn quyền máy chủ”.

## 4. Phân biệt với các kỹ thuật dễ nhầm

PtH tập trung vào tái sử dụng hash. Password cracking cố khôi phục mật khẩu từ dữ liệu dẫn xuất. NTLM relay chuyển tiếp trao đổi xác thực tới bên khác, trong khi pass-the-ticket dùng ticket Kerberos. Overpass-the-hash có thể dùng vật liệu liên quan mật khẩu để thu được ticket Kerberos khi điều kiện phù hợp; không phải mọi PtH đều tạo ticket. [MITRE ATT&CK: mô tả PtH và overpass-the-hash](https://attack.mitre.org/techniques/T1550/002/)

Hệ quả đối với lựa chọn kiểm soát:

| Kiểm soát | Giá trị chính | Không nên suy ra |
| --- | --- | --- |
| Mật khẩu dài và riêng biệt | Hạn chế đoán mật khẩu và tái sử dụng giữa tài khoản, máy | Hash đã lộ tự nhiên mất khả năng dùng |
| SMB signing | Bảo vệ tính toàn vẹn SMB; liên quan quan trọng tới phòng chống relay | Mọi xác thực bằng hash hợp lệ đều bị chặn |
| MFA ở cổng PAM | Tăng độ tin cậy của bước người dùng vào PAM | Đường NTLM trực tiếp ở máy đích cũng yêu cầu cùng bước MFA |
| Ưu tiên Kerberos | Giảm phụ thuộc vào NTLM khi được cấu hình và vận hành đúng | Mọi dạng đánh cắp ticket hoặc danh tính đều biến mất |
| Giám sát phiên PAM | Gắn thao tác qua broker với người thực hiện và yêu cầu | Tự động nhìn thấy mọi kết nối đi ngoài broker |

Bảng này là cách phân tích phạm vi bảo vệ. Hiệu quả thực tế cần được đo trên kiến trúc cụ thể, thay vì chỉ đánh dấu sản phẩm hoặc tính năng đã được triển khai.

## 5. PAM cắt chuỗi rủi ro ở đâu?

### 5.1. Kiểm kê quyền và loại bỏ tài khoản dùng chung quá rộng

Bắt đầu bằng các quan hệ có thể kiểm chứng:

```text
Con người / workload
    -> tài khoản đặc quyền
        -> nhóm và quyền hiệu lực
            -> máy hoặc dịch vụ được truy cập
                -> đường truy cập và vật liệu xác thực có thể lưu lại
```

Ví dụ, tài khoản `ops-web` chỉ được dùng để vận hành nhóm web server. Nếu tài khoản còn là local administrator của file server do lịch sử triển khai, đó là cạnh quyền cần loại bỏ, không phải ngoại lệ mặc định.

Tách tài khoản làm việc hằng ngày và tài khoản quản trị giúp giảm việc đưa danh tính nhạy cảm vào trình duyệt, email và phần mềm văn phòng. Tách tầng quản trị giúp một sự cố ở tầng thấp ít có cơ hội tiếp xúc với tài khoản có quyền ở tầng cao hơn. Tuy nhiên, việc tách tên tài khoản sẽ ít giá trị nếu tất cả tài khoản vẫn dùng cùng mật khẩu hoặc đều được đăng nhập từ cùng endpoint không đáng tin cậy.

### 5.2. Mật khẩu quản trị local riêng cho từng máy

Mật khẩu local administrator đồng nhất làm tăng phạm vi dùng lại hash. Windows LAPS hỗ trợ quản lý và luân chuyển mật khẩu quản trị local theo thiết bị, với quyền truy xuất được kiểm soát. [Microsoft Learn: Windows LAPS overview](https://learn.microsoft.com/en-us/windows-server/identity/laps/laps-overview?trk=public_post_comment-text)

Để nghiệm thu trong một đội vận hành, có thể yêu cầu bằng chứng sau:

- Từng thiết bị thuộc phạm vi quản lý có trạng thái rotation gần nhất.
- Người lấy được bí mật có vai trò và lý do truy xuất phù hợp.
- Quy trình triển khai ảnh máy không tái lập mật khẩu dùng chung.
- Thiết bị ngoại tuyến, thiết bị không báo cáo và tài khoản quản trị phụ có chủ sở hữu xử lý.

Đây là tiêu chí vận hành của thiết kế, không phải bảo đảm rằng bật một chính sách sẽ tự sửa mọi mật khẩu đã tồn tại.

Nếu một endpoint bị chiếm quyền liên tục, bí mật mới có thể tiếp tục bị lộ. Rotation phải đi cùng xử lý nguồn xâm nhập.

### 5.3. Vault và credential injection

Vault cần kiểm soát được vòng đời bí mật: đăng ký tài khoản, kiểm tra quyền sở hữu, cấp phát, rotation, đối soát và phục hồi khi rotation thất bại.

Credential injection giảm nhu cầu người vận hành biết hoặc sao chép mật khẩu rõ. Khi đánh giá, cần kiểm tra thêm:

1. Broker dùng danh tính nào để mở kết nối tới máy đích?
2. Bí mật hoặc vật liệu xác thực có xuất hiện trên broker và đích không?
3. Có đường truy cập trực tiếp nào bỏ qua broker?
4. Bằng chứng phiên có liên kết được với tài khoản đích và người yêu cầu không?
5. Rotation đã thành công trên hệ thống có thẩm quyền hay mới chỉ cập nhật bản ghi vault?

Không đặt một bí mật dùng chung cho hàng trăm máy vào vault rồi xem đó là đã hạn chế di chuyển ngang. Vault cải thiện quản trị bí mật; phạm vi quyền và khả năng dùng lại vẫn phải được thiết kế riêng.

### 5.4. JIT và JEA

JIT cấp quyền theo khoảng thời gian và nhu cầu đã được duyệt. JEA giới hạn thao tác quản trị được phép. Kết hợp hai hướng này giúp giảm số tài khoản có quyền thường trực và giảm khả năng một danh tính bị lạm dụng làm mọi việc.

Ví dụ thiết kế cho tác vụ restart dịch vụ:

```text
Yêu cầu: restart dịch vụ web trên APP-01
Người yêu cầu: danh tính cá nhân
Phê duyệt: phạm vi APP-01, thời lượng 20 phút
Quyền được cấp: chỉ thao tác dịch vụ được định danh
Nguồn kết nối: máy quản trị đã đăng ký
Bằng chứng: request -> quyết định cấp quyền -> phiên -> thao tác -> thu hồi
```

Điểm kiểm chứng quan trọng là hiệu lực thực tế. Hết cửa sổ JIT không luôn có nghĩa token, kết nối và tiến trình đã được cấp trước đó tự chấm dứt ngay. Cần kiểm tra truy cập mới và phiên đang tồn tại, rồi quy định cơ chế kết thúc phù hợp.

Một endpoint JEA cũng cần được xem như bề mặt quản trị: các lệnh được phép, tham số, khả năng gọi công cụ ngoài và danh tính thực thi đều phải nằm trong phạm vi thiết kế.

### 5.5. Bảo vệ vật liệu xác thực trên endpoint

Credential Guard dùng cơ chế cách ly dựa trên VBS để bảo vệ một số bí mật xác thực, bao gồm NTLM hash của tài khoản domain. Đây không phải bảo vệ toàn bộ kho SAM hoặc cơ sở dữ liệu AD. Vì vậy, không dùng trạng thái “Credential Guard bật” làm kết luận rằng mọi tài khoản local và mọi bản sao bí mật đều an toàn. [Microsoft Learn: Credential Guard](https://learn.microsoft.com/en-us/windows/security/identity-protection/credential-guard/)

Thiết kế PAM nên gắn trạng thái bảo vệ endpoint với điều kiện cho phép quản trị. Một máy có agent nhưng agent ngừng gửi telemetry nhiều ngày không nên được xem tương đương máy đã xác minh khỏe mạnh.

Với RDP, Remote Credential Guard và Restricted Admin có cách xử lý danh tính khác nhau. Remote Credential Guard yêu cầu Kerberos và không fallback sang NTLM. Cần đọc yêu cầu và giới hạn của từng chế độ trước khi áp dụng cho đường hỗ trợ từ xa. [Microsoft Learn: Remote Credential Guard](https://learn.microsoft.com/en-us/windows/security/identity-protection/remote-credential-guard)

Đặc biệt, việc giảm credential được đưa tới máy đích không đồng nghĩa mọi cách dùng hash để kết nối vào đích bị loại bỏ. Restricted Admin có thể liên quan đến đường lạm dụng PtH khi được cấu hình cho phép; đây là lý do phải xét cả chiều bảo vệ credential và chiều chấp nhận xác thực. [MITRE ATT&CK: trường hợp lạm dụng Restricted Admin](https://attack.mitre.org/techniques/T1550/002/)

### 5.6. Giảm và kiểm soát NTLM theo bằng chứng

Trước khi chặn NTLM, cần audit luồng phụ thuộc, xác định chủ sở hữu và kiểm thử tác động. Microsoft cung cấp chính sách audit hoặc hạn chế NTLM; chặn thiếu chuẩn bị có thể làm ứng dụng và tác vụ vận hành thất bại. [Microsoft Learn: Restrict NTLM outgoing traffic](https://learn.microsoft.com/de-de/windows/security/threat-protection/security-policy-settings/network-security-restrict-ntlm-outgoing-ntlm-traffic-to-remote-servers)

Một lộ trình vận hành có thể gồm:

1. Đo NTLM theo nguồn, đích, tài khoản, dịch vụ và tần suất.
2. Phân loại luồng quản trị, workload và phụ thuộc chưa rõ.
3. Khắc phục cấu hình khiến luồng dự kiến dùng Kerberos chuyển sang NTLM.
4. Thử chính sách hạn chế trên phạm vi nhỏ, có tiêu chí thành công và rollback.
5. Quản lý ngoại lệ bằng chủ sở hữu, hạn hết hiệu lực và kế hoạch xử lý.
6. Kiểm tra cả sự kiện cho phép, bị chặn và sức khỏe nguồn log sau rollout.

Ngoại lệ tồn tại lâu dài mà không có người chịu trách nhiệm thường trở thành đường đi ngoài chính sách PAM.

## 6. Phát hiện: tìm chuỗi bằng chứng, không tìm một Event ID “chắc chắn PtH”

### 6.1. Những gì Windows cho biết

Event 4624 được tạo trên máy nơi hình thành phiên đăng nhập. Với điều tra này, quan tâm tài khoản đích, miền, Logon Type, authentication package, địa chỉ nguồn và Logon ID. Một network logon sử dụng NTLM là tín hiệu cần đặt vào ngữ cảnh, không tự chứng minh PtH. [Microsoft Learn: Event 4624](https://learn.microsoft.com/windows/security/threat-protection/auditing/event-4624)

Event 4776 ghi nhận việc kiểm tra credential bằng NTLM tại máy có thẩm quyền: DC cho tài khoản domain, hoặc máy local cho tài khoản local. Sự kiện cung cấp Source Workstation nhưng không tự cho biết đầy đủ máy tài nguyên đích. [Microsoft Learn: Event 4776](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-10/security/threat-protection/auditing/event-4776)

Một số quan sát bổ sung thường hữu ích khi audit tương ứng đã bật:

| Quan sát | Câu hỏi hỗ trợ trả lời | Giới hạn |
| --- | --- | --- |
| 4624, Logon Type 3, NTLM | Ai hình thành network logon ở đích? | Sao lưu, quản trị và ứng dụng hợp lệ cũng có thể tạo mẫu này |
| 4776 | Bên có thẩm quyền đã kiểm tra tài khoản nào, từ workstation nào? | Không thay thế log máy tài nguyên đích |
| 4672 | Phiên nào được gán các quyền đặc biệt? | Nhiều hoạt động hệ thống hợp lệ cũng sinh sự kiện |
| 4688 hoặc telemetry tiến trình | Sau đăng nhập đã chạy tiến trình nào? | Chi tiết phụ thuộc audit, EDR và quyền thu thập |
| Telemetry truy cập credential nhạy cảm | Có dấu hiệu lấy vật liệu xác thực trước kết nối không? | Thiếu telemetry không chứng minh chưa bị lấy |
| Log broker, vault và JIT | Có yêu cầu và phiên hợp lệ cho cùng tài khoản, đích, thời gian không? | Đường đi ngoài PAM có thể không có session ID |
| Log mạng | Nguồn nào thực sự kết nối tài nguyên nào? | NAT, proxy và broker có thể che nguồn người dùng ban đầu |

Sự vắng mặt của 4648 không chứng minh PtH. Tương tự, không nên yêu cầu mọi vụ việc phải có một Logon Type hoặc tiến trình cố định. Kỹ thuật triển khai, đường truy cập và cấu hình audit làm dấu vết thay đổi.

### 6.2. Chất lượng liên kết danh tính và thời gian

Trước khi viết rule tương quan, cần chuẩn hóa:

- Thời điểm sự kiện theo UTC và độ lệch đồng hồ.
- SID hoặc định danh chuẩn, miền có thẩm quyền và tên tài khoản.
- Host ID ổn định thay vì chỉ hostname hoặc IP có thể thay đổi.
- Vai trò nguồn: workstation thường, máy quản trị, broker hay máy workload.
- Phạm vi cấp quyền: tài khoản, đích, thao tác, nguồn và khoảng hiệu lực.
- Event Record ID cùng máy phát sinh để truy lại dữ liệu gốc.

Logon ID chỉ nên được nối trong phạm vi máy và ngữ cảnh vòng đời phù hợp; nó không phải khóa toàn cục cho mọi endpoint. Với tài khoản local trùng tên, dùng riêng tên `Administrator` sẽ trộn các danh tính thuộc nhiều máy.

Thời gian ingest cũng không phải thời gian xảy ra sự kiện. Một log đến muộn có thể làm rule chạy trước bằng chứng phê duyệt; pipeline cần hỗ trợ đánh giá lại và ghi nhận độ trễ.

### 6.3. Những mẫu đáng ưu tiên điều tra

Một thiết kế cho môi trường PAM có thể nâng mức ưu tiên khi nhiều điều kiện cùng xuất hiện:

- Tài khoản quản trị dùng NTLM từ nguồn không được phép quản trị.
- Tài khoản di chuyển tới nhiều máy ngoài tập đích thường dùng.
- Có xác thực thành công nhưng không tìm được grant hoặc phiên PAM tương ứng.
- Có dấu hiệu lấy credential trên nguồn trước kết nối.
- Sau đăng nhập xuất hiện hành động quản trị khác với tác vụ đã phê duyệt.
- Có truy cập mới sau khi quyền đã thu hồi hoặc bí mật được xác nhận rotation.

Những mẫu này là giả thuyết thiết kế cần hiệu chỉnh. Chúng không phải chữ ký đảm bảo xác định PtH.

Ví dụ, hệ thống sao lưu có thể truy cập nhiều server bằng NTLM. Thay vì miễn trừ toàn bộ tài khoản sao lưu, hãy kiểm tra đúng nguồn, đúng tập đích, lịch chạy, chủ sở hữu và loại thao tác. Một máy nguồn lạ sử dụng cùng tài khoản vẫn phải được điều tra.

## 7. Ví dụ tương quan trên dữ liệu đã chuẩn hóa

Giả sử SIEM có bảng quy ước `AuthEvent` và `PamGrant`. Đây là schema minh họa, không phải tên bảng mặc định của một sản phẩm.

```text
AuthEvent:
  event_id, event_time_utc, target_host_id
  account_id, account_authority, source_host_id
  logon_type, auth_protocol, result

PamGrant:
  grant_id, account_id, target_host_id, source_host_id
  valid_from_utc, valid_until_utc, state, request_id
```

Đối với domain account, `account_id` có thể là SID chuẩn hóa. Đối với local account, khóa phải giữ được máy có thẩm quyền. Pipeline cần đánh dấu “chưa xác định” thay vì ghép bừa tài khoản cùng tên.

Logic minh họa:

```text
for each auth in AuthEvent:
    if auth.result != SUCCESS:
        continue

    if auth.event_id != 4624:
        continue

    if auth.logon_type != NETWORK or auth.auth_protocol != NTLM:
        continue

    if not privileged_inventory.contains(auth.account_id, auth.event_time_utc):
        continue

    grant = find_effective_grant(
        account = auth.account_id,
        target = auth.target_host_id,
        source = auth.source_host_id,
        at = auth.event_time_utc
    )

    reasons = []

    if not management_policy.allows(auth.source_host_id, auth.target_host_id):
        reasons.add("UNAPPROVED_SOURCE_PATH")

    if grant is missing:
        reasons.add("NO_MATCHING_GRANT")

    if auth.source_host_id is unknown:
        reasons.add("SOURCE_IDENTITY_INCOMPLETE")

    if reasons is not empty:
        create_investigation_candidate(
            auth.event_id,
            auth.target_host_id,
            auth.account_id,
            auth.event_time_utc,
            reasons
        )
```

`find_effective_grant` phải xét thời điểm grant thực sự có hiệu lực và bị thu hồi, không chỉ trạng thái hiện tại của bản ghi. Một grant bị thu hồi lúc 09:12 không được dùng để hợp thức hóa đăng nhập mới lúc 09:18 chỉ vì kế hoạch ban đầu cho phép tới 09:30.

Đầu ra là ứng viên điều tra “xác thực đặc quyền NTLM lệch chính sách”, không phải phán quyết PtH. Nhóm điều tra bổ sung 4776, telemetry nguồn, tiến trình đích và bằng chứng phiên để đánh giá giả thuyết.

Cần phân biệt ba trường hợp:

1. **Có bằng chứng phù hợp chính sách:** tiếp tục kiểm tra hành động có đúng phạm vi.
2. **Không tìm được bằng chứng do dữ liệu thiếu:** tạo yêu cầu điều tra và cảnh báo chất lượng dữ liệu.
3. **Có bằng chứng truy cập sai phạm vi:** ưu tiên xử lý; vẫn xác định kỹ thuật thực tế thay vì gán nhãn quá sớm.

## 8. Đọc log 4624 theo cách không làm thay đổi hệ thống

Ví dụ PowerShell dưới đây chỉ đọc Security log trên máy đang chạy và lọc network logon có authentication package NTLM. Chạy trên máy thuộc phạm vi được phép, với quyền đọc log phù hợp. Đây không phải công cụ xác định PtH và không thu thập hash.

```powershell
$windowStart = (Get-Date).AddMinutes(-30)

Get-WinEvent -FilterHashtable @{
    LogName = 'Security'
    Id = 4624
    StartTime = $windowStart
} -ErrorAction Stop | ForEach-Object {
    $eventRecord = $_
    [xml]$eventXml = $eventRecord.ToXml()
    $eventFields = @{}

    foreach ($field in $eventXml.Event.EventData.Data) {
        $eventFields[[string]$field.Name] = [string]$field.'#text'
    }

    if ($eventFields['LogonType'] -eq '3' -and
        $eventFields['AuthenticationPackageName'] -eq 'NTLM') {
        [pscustomobject]@{
            TimeUtc = $eventRecord.TimeCreated.ToUniversalTime()
            Computer = $eventRecord.MachineName
            RecordId = $eventRecord.RecordId
            TargetUserSid = $eventFields['TargetUserSid']
            TargetDomain = $eventFields['TargetDomainName']
            TargetUser = $eventFields['TargetUserName']
            TargetLogonId = $eventFields['TargetLogonId']
            SourceIp = $eventFields['IpAddress']
            SourceWorkstation = $eventFields['WorkstationName']
            NtlmPackage = $eventFields['LmPackageName']
        }
    }
}
```

Chọn field bằng tên trong XML giúp tránh phụ thuộc vị trí phần tử trong mảng `Properties`. Nếu trường nguồn trống hoặc là `-`, cần làm giàu bằng dữ liệu khác; không chuyển thành một địa chỉ nguồn tự suy đoán.

Không có kết quả có thể do không có sự kiện phù hợp, audit chưa bật, retention không đủ hoặc truy vấn sai khoảng thời gian. Trường hợp truy vấn lỗi cần được phân biệt với truy vấn thành công nhưng không có kết quả.

Trong vận hành, không dùng riêng cửa sổ 30 phút làm giới hạn điều tra. Đây chỉ là lựa chọn minh họa cho truy vấn nhỏ; khoảng tìm kiếm phải xuất phát từ timeline và chất lượng log.

## 9. Tình huống điều tra mẫu

Các tên máy, tài khoản và thời điểm dưới đây đều là dữ liệu giả định.

Đội vận hành có các quy định:

- Quản trị server phải đi từ `PAW-OPS-01` qua `PAM-BROKER-01`.
- Tài khoản `CORP\\adm.web.01` được cấp JIT tới `APP-01` từ 09:00 tới 09:20 UTC.
- Máy làm việc `WS-USER-17` không được mở kết nối quản trị tới server.
- Không có grant tới `FILE-01`.

Timeline:

| Thời điểm UTC | Quan sát | Ý nghĩa ban đầu |
| --- | --- | --- |
| 09:02 | Broker mở phiên tới APP-01 theo request đã duyệt | Có hoạt động quản trị dự kiến |
| 09:06 | EDR trên WS-USER-17 báo truy cập bất thường tới thành phần chứa credential | Cần xác minh tiến trình, quyền và chất lượng cảnh báo |
| 09:08 | FILE-01 có 4624, Type 3, NTLM cho adm.web.01 từ WS-USER-17 | Lệch cả nguồn lẫn đích đã được phép |
| 09:08 | DC ghi 4776 cho cùng tài khoản với Source Workstation tương ứng | Bổ sung chứng cứ về kiểm tra NTLM |
| 09:09 | Telemetry FILE-01 ghi hành động tạo tác vụ quản trị không thuộc yêu cầu | Tăng mức nghi ngờ lạm dụng danh tính |

Không dùng grant tới APP-01 để hợp thức hóa sự kiện ở FILE-01. Tương tự, việc tài khoản vừa có một phiên PAM hợp lệ không chứng minh mọi hoạt động của tài khoản trong cùng buổi đều hợp lệ.

Phân tích theo từng câu hỏi:

1. **Nguồn có đúng là WS-USER-17 không?** Đối chiếu tài sản, DHCP, mạng và độ lệch đồng hồ.
2. **Danh tính có khớp không?** So SID, miền và dạng chuẩn hóa thay vì chỉ tên hiển thị.
3. **Đường truy cập có thật sự đi ngoài broker không?** Kiểm tra network flow và log broker.
4. **Có nguồn credential theft khả tín không?** Kiểm tra cảnh báo EDR và tiến trình trước đó.
5. **Có thể giải thích bằng phần mềm hợp lệ không?** Kiểm tra job vận hành, tài khoản dịch vụ và thay đổi gần đây.
6. **Phạm vi hành động sau đăng nhập là gì?** Xác minh quyền và hiện vật thay vì suy ra từ xác thực.

Kết luận ban đầu phù hợp là “nghi lạm dụng tài khoản quản trị bằng NTLM, cần điều tra PtH”. Khi có thêm bằng chứng liên kết vật liệu xác thực bị đánh cắp với hoạt động sử dụng, nhóm mới tăng độ chắc chắn của nhãn kỹ thuật.

## 10. Ứng phó gắn với vòng đời quyền và bí mật

### 10.1. Khoanh vùng và bảo toàn bằng chứng

Thực hiện theo quyền ứng phó đã được tổ chức quy định:

- Ghi nhận tài khoản, máy nguồn, máy đích, thời gian và các đường truy cập liên quan.
- Bảo toàn log và hiện vật cần thiết trong kho chứng cứ có kiểm soát truy cập.
- Cô lập nguồn bị nghi xâm nhập bằng cơ chế phù hợp với mức ảnh hưởng.
- Tạm dừng grant, đường truy cập hoặc danh tính liên quan khi đánh giá rủi ro yêu cầu.
- Kiểm tra tài khoản đặc quyền nào khác đã hiện diện trên nguồn hoặc đích bị ảnh hưởng.

Không gửi dump bộ nhớ hoặc bí mật vào kênh chat điều phối. Nếu phải thu hiện vật nhạy cảm, quy trình cần xác định người được quyền đọc và thời hạn lưu.

### 10.2. Thu hồi quyền và chấm dứt truy cập đang tồn tại

Đổi mật khẩu chỉ tác động một phần vòng đời. Cần phân biệt:

```text
Bí mật cũ còn dùng được cho xác thực mới?
Quyền thành viên hoặc grant còn hiệu lực?
Phiên mạng hiện có còn hoạt động?
Token hoặc tiến trình đã được tạo còn quyền?
Tác vụ, dịch vụ hoặc cơ chế tồn tại lâu dài nào đã được cài?
```

Kế hoạch phải xử lý đúng đối tượng: kết thúc phiên ở broker, phiên trên máy đích, quyền JIT và workload liên quan. Không khẳng định toàn bộ truy cập chấm dứt chỉ vì vault báo rotation thành công.

### 10.3. Rotation và phục hồi từ điểm đáng tin cậy

Với local account bị dùng chung, cần xử lý tất cả máy thuộc nhóm dùng lại mật khẩu được xác định, rồi thay thiết kế thành bí mật riêng. Không chỉ đổi trên máy đầu tiên nhìn thấy.

Với domain account, cần kiểm tra hệ thống phụ thuộc trước khi thay bí mật, có phương án cập nhật dịch vụ và xác nhận thay đổi tại bên có thẩm quyền. Trong sự cố, tốc độ và tính sẵn sàng phải được quyết định trong quy trình ứng phó, không bằng thao tác tùy tiện của một người trực.

Bằng chứng rotation nên gồm:

- Định danh tài khoản và hệ thống có thẩm quyền.
- Thời điểm bắt đầu, hoàn tất và kết quả.
- Xác nhận bí mật mới đã đồng bộ tới đúng thành phần sử dụng.
- Kết quả kiểm tra truy cập mới phù hợp với chính sách.
- Tình trạng phiên cũ và việc xử lý nguồn có thể tiếp tục đánh cắp bí mật.

Nếu còn endpoint bị kiểm soát, việc phát bí mật mới vào cùng endpoint có thể tái tạo sự cố.

### 10.4. Điều kiện đóng sự cố

Một bộ tiêu chí đề xuất cho tổ chức sử dụng PAM:

1. Đã xác định hoặc khoanh vùng hợp lý nguồn và danh tính bị ảnh hưởng.
2. Đã xử lý nguồn xâm nhập theo quy trình phục hồi.
3. Đã thu hồi quyền, xử lý phiên và rotation theo phạm vi thực tế.
4. Đã kiểm tra các đích liên quan thay vì chỉ máy phát cảnh báo ban đầu.
5. Đã khắc phục đường đi ngoài PAM và quyền quá rộng được phát hiện.
6. Đã xác nhận telemetry hoạt động và theo dõi trong khoảng thời gian được đội ứng phó lựa chọn.

Không dùng một khoảng “không có cảnh báo mới” làm tiêu chí duy nhất nếu nguồn log đang lỗi.

## 11. Thực hành kiểm chứng mà không cần tạo hash thật

Bài thực hành này dùng dữ liệu tổng hợp. Mục tiêu là kiểm tra logic phát hiện và quy trình PAM, không thực hiện đánh cắp credential.

### 11.1. Bộ dữ liệu tối thiểu

Chuẩn bị các bản ghi giả lập với định danh nhất quán:

| Mẫu | Xác thực | Grant PAM | Kỳ vọng |
| --- | --- | --- | --- |
| A | Nguồn và đích đúng, trong cửa sổ cho phép | Khớp tài khoản, nguồn, đích, thời gian | Không cảnh báo chỉ vì dùng NTLM; vẫn chịu chính sách NTLM của tổ chức |
| B | Nguồn lạ, đích ngoài phạm vi | Không khớp | Tạo ứng viên điều tra ưu tiên |
| C | Đúng tài khoản, sai máy đích | Có grant tới máy khác | Không coi grant đó là hợp lệ cho sự kiện này |
| D | Truy cập mới sau thời điểm thu hồi | Grant đã hết hiệu lực tại thời điểm sự kiện | Tạo ứng viên điều tra |
| E | Hai local account cùng tên trên hai máy | Chỉ một danh tính được cấp | Không ghép theo tên đơn thuần |
| F | Thiếu nguồn do dữ liệu chưa đầy đủ | Chưa đối chiếu được | Báo thiếu dữ liệu và điều tra, không tự đánh dấu hợp lệ |
| G | Log ingest muộn | Grant có hiệu lực khi sự kiện xảy ra | Đối chiếu theo event time và đánh giá lại |
| H | Tài khoản sao lưu, nguồn khác baseline | Có ngoại lệ chỉ cho nguồn chuẩn | Không miễn trừ toàn bộ tài khoản |

Mỗi kết quả cần giữ lại nguyên nhân, dữ liệu đã dùng và phiên bản logic để người khác tái lập.

### 11.2. Nghiệm thu kiểm soát PAM

Tách kiểm chứng dữ liệu khỏi kiểm chứng hệ thống:

- **Dữ liệu:** rule có phân biệt đúng các mẫu trên không?
- **Đường truy cập:** máy ngoài phạm vi quản trị có bị chặn theo chính sách không?
- **Quyền:** tài khoản chỉ có quyền đã phê duyệt trên đúng đích không?
- **Vòng đời:** cấp, thu hồi và rotation có bằng chứng xác nhận tại hệ thống đích không?
- **Quan sát:** xác thực trên đích có liên kết được với request và phiên PAM không?

Kiểm thử kết nối hoặc thay đổi quyền chỉ thực hiện trong phạm vi được giao và theo quy trình của môi trường. Dữ liệu tổng hợp giúp kiểm tra logic nhưng không thay thế bằng chứng rằng firewall, broker và hệ thống đích thực thi đúng.

## 12. Các nhầm lẫn cần tránh khi viết báo cáo

| Nhận định quá mức | Cách diễn đạt có căn cứ hơn |
| --- | --- |
| “Có NTLM nên chắc chắn là PtH” | Có xác thực NTLM; cần thêm bằng chứng phân biệt hoạt động hợp lệ với lạm dụng |
| “Có MFA nên PtH không thể xảy ra” | MFA bảo vệ đường được tích hợp; cần kiểm tra đường xác thực trực tiếp khác |
| “Hash không phải mật khẩu nên không nhạy cảm” | Hash có thể là vật liệu đủ để xác thực trong đường phù hợp |
| “Bật LAPS nghĩa là hết PtH” | Bí mật local riêng giảm phạm vi tái sử dụng; vẫn cần bảo vệ endpoint và tài khoản domain |
| “Credential Guard bảo vệ toàn bộ bí mật Windows” | Phạm vi bảo vệ có giới hạn; phải xét loại tài khoản và nơi lưu bí mật |
| “Rotation thành công nghĩa là mọi phiên đã bị hủy” | Cần kiểm chứng xác thực mới, phiên cũ, token và tiến trình riêng |
| “Không có log PAM tức là không có quản trị” | Có thể đã đi ngoài broker hoặc telemetry thiếu |
| “Cùng tên local administrator là cùng danh tính” | Phải giữ máy có thẩm quyền và định danh tài khoản khi tương quan |

Điểm cốt lõi của phòng thủ PtH trong PAM là quản lý đồng thời **vật liệu xác thực, quyền hiệu lực, đường truy cập và bằng chứng**. Một danh tính có phạm vi nhỏ, thời gian ngắn và nguồn truy cập được kiểm soát sẽ hạn chế hậu quả khi bí mật bị lộ; telemetry đầy đủ giúp phát hiện những lần sử dụng nằm ngoài phạm vi đó.
