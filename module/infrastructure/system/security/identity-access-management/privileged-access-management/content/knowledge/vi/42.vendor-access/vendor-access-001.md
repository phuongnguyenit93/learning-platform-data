# Vendor privileged account

## 1. Tài khoản đặc quyền của nhà cung cấp là gì?

**Vendor privileged account** là tài khoản hoặc danh tính được dùng bởi nhân sự của nhà cung cấp, đối tác bảo trì hay đơn vị dịch vụ bên ngoài để thực hiện thao tác có quyền cao trên tài sản của tổ chức. Tài sản có thể là máy chủ, thiết bị mạng, cơ sở dữ liệu, nền tảng đám mây, ứng dụng nghiệp vụ hoặc chính hệ thống quản trị truy cập đặc quyền.

Một kỹ sư của hãng phần mềm cần sửa cấu hình dịch vụ sản xuất; một đối tác cần nâng cấp firmware của thiết bị mạng; một đội vận hành thuê ngoài cần chẩn đoán lỗi cơ sở dữ liệu: cả ba đều có thể sử dụng tài khoản đặc quyền của nhà cung cấp.

Điểm quyết định không nằm ở tên tài khoản có chữ `vendor` hay không. Điều cần xem là **ai đang sử dụng danh tính, họ đại diện cho bên nào, và danh tính đó có thể tác động đến đâu**. Tài khoản mang tên một nhân viên nội bộ nhưng được giao cho kỹ sư bên ngoài sử dụng vẫn tạo ra rủi ro truy cập của nhà cung cấp.

Trong PAM, bài toán này cần giải quyết đồng thời bốn câu hỏi:

1. Người đang kết nối là cá nhân nào của nhà cung cấp?
2. Tổ chức đã cho phép cá nhân đó làm công việc gì, trên tài sản nào?
3. Quyền được sử dụng trong khoảng thời gian và qua đường truy cập nào?
4. Tổ chức có thể quan sát, dừng phiên và thu hồi toàn bộ quyền liên quan hay không?

Tài khoản đăng nhập được không đồng nghĩa công việc đã được phê duyệt. Tương tự, có bản ghi phiên không đồng nghĩa mọi thao tác trong phiên đều hợp lệ.

## 2. Vì sao loại tài khoản này cần được quản lý riêng?

Nhân sự bên ngoài thường không đi qua đầy đủ quy trình nhân sự nội bộ. Tổ chức có thể biết hợp đồng với một công ty dịch vụ nhưng không biết kỹ sư nào đã nghỉ việc, chuyển dự án, giao máy tính cho người khác hoặc chuyển công việc cho nhà thầu phụ.

Một số đặc điểm làm rủi ro tăng lên:

- **Nhu cầu không liên tục:** tài khoản chỉ cần vài giờ mỗi tháng nhưng thường được giữ hoạt động cả năm.
- **Quyền rộng để hỗ trợ nhanh:** nhà cung cấp có thể yêu cầu quyền quản trị toàn hệ thống dù công việc chỉ liên quan một dịch vụ.
- **Danh tính gián tiếp:** công ty biết tên nhà cung cấp nhưng không có danh tính riêng cho từng người thực hiện.
- **Thiết bị ngoài quản lý:** máy tính dùng để kết nối có thể không thuộc phạm vi quản trị của tổ chức.
- **Nhiều khách hàng trên một thiết bị:** một máy hỗ trợ có thể lưu thông tin của nhiều môi trường.
- **Đường truy cập đặc biệt:** công cụ hỗ trợ từ xa, kết nối luôn bật hoặc tài khoản cục bộ có thể nằm ngoài hệ thống IAM thông thường.
- **Khó thu hồi đầy đủ:** vô hiệu hóa tài khoản đăng nhập chưa chắc đã kết thúc phiên đang chạy hoặc xóa các khóa đã được cấp.

Một tình huống điển hình: tài khoản `support-admin` được tạo khi triển khai sản phẩm, mật khẩu được gửi cho đội hỗ trợ và không đổi trong nhiều năm. Khi có sự cố, nhiều kỹ sư dùng chung tài khoản. Nhật ký chỉ cho thấy `support-admin` đã đăng nhập; không chứng minh được người thực hiện, yêu cầu công việc hay người phê duyệt.

Mục tiêu quản lý là biến truy cập này từ một quyền thường trực khó truy vết thành **một quyền có chủ thể, có lý do, có phạm vi và có điểm kết thúc**.

## 3. Phân biệt người truy cập, tài khoản đích và credential

Một phiên hỗ trợ có thể đi qua nhiều lớp danh tính. Nếu gộp chúng thành một “tài khoản vendor”, việc thiết kế kiểm soát sẽ thiếu chính xác.

| Thành phần | Ví dụ | Câu hỏi cần trả lời |
|---|---|---|
| Cá nhân bên ngoài | Nguyễn An, kỹ sư của Vendor A | Người thật nào chịu trách nhiệm cho phiên? |
| Danh tính truy cập | `ext.an.vendor-a` | Cá nhân xác thực vào cổng truy cập bằng cách nào? |
| Quyền truy cập được duyệt | Bảo trì dịch vụ trên `app-prod-02` trong hai giờ | Ai cho phép, vì công việc gì và đến khi nào? |
| Tài khoản đặc quyền đích | `svc-support-admin`, tài khoản quản trị cục bộ hoặc role tạm thời | Hệ thống đích thực thi quyền của tài khoản nào? |
| Credential | Mật khẩu, khóa SSH, chứng thư hoặc token | Ai giữ, ai nhìn thấy, hiệu lực bao lâu và thu hồi bằng cách nào? |
| Phiên làm việc | Phiên được broker qua PAM | Hoạt động nào đã diễn ra và có thể dừng ở đâu? |

**Một người – một danh tính truy cập** là nguyên tắc giúp quy trách nhiệm ở đầu vào. Điều này không buộc mọi hệ thống cũ phải có ngay một tài khoản quản trị riêng cho từng kỹ sư.

Ví dụ, thiết bị cũ chỉ hỗ trợ một tài khoản quản trị. PAM có thể giữ credential của tài khoản đó và cho các kỹ sư đã xác thực riêng đi qua broker. Tuy nhiên, tổ chức phải giữ được ánh xạ:

```text
Cá nhân bên ngoài
    -> danh tính đăng nhập
    -> yêu cầu và phê duyệt
    -> phiên PAM
    -> tài khoản đích
    -> sự kiện tại hệ thống đích
```

Nếu nhà cung cấp biết mật khẩu và có đường kết nối trực tiếp đến thiết bị, họ có thể bỏ qua broker. Khi đó, nhật ký PAM chỉ phản ánh các phiên đi qua PAM; nó không bao phủ toàn bộ việc sử dụng tài khoản đích.

## 4. Xác định đúng loại tài khoản trước khi cấp quyền

### 4.1. Tài khoản dành cho cá nhân thực hiện hỗ trợ

Đây là danh tính gắn với một kỹ sư cụ thể. Nó cần có tên người, tổ chức sử dụng lao động, người bảo trợ nội bộ và trạng thái vòng đời rõ ràng.

Không cho phép luân phiên nhiều kỹ sư dùng cùng danh tính đăng nhập để tiết kiệm số lượng tài khoản. Nếu một người vắng mặt và đồng nghiệp thay ca, người thay phải sử dụng danh tính riêng và nhận quyền phù hợp.

### 4.2. Tài khoản đích được PAM quản lý

Đây có thể là tài khoản cục bộ trên máy chủ hoặc thiết bị. Tổ chức giữ quyền quản lý credential và chỉ cung cấp khả năng thực hiện công việc đã được duyệt.

Ưu tiên cơ chế broker hoặc credential injection để kỹ sư không phải nhận mật khẩu. Cơ chế này giảm việc tiết lộ credential, nhưng không tự loại bỏ khả năng một quản trị viên trong phiên tạo thêm tài khoản, khóa hoặc tác vụ duy trì truy cập. Quyền trong phiên và kiểm tra sau công việc vẫn cần được thiết kế riêng.

### 4.3. Danh tính máy dùng bởi dịch vụ của nhà cung cấp

Agent giám sát, công cụ đồng bộ hoặc hệ thống hỗ trợ tự động có thể dùng API token, chứng thư hay workload identity. Đây là danh tính không tương tác, cần cơ chế xác thực và vòng đời phù hợp với máy.

Không chuyển tài khoản người dùng sang “không yêu cầu MFA” chỉ để phục vụ tự động hóa. Tách danh tính máy, giới hạn tài sản và thao tác, xác định chủ sở hữu và quản lý secret theo cơ chế riêng.

### 4.4. Tài khoản khẩn cấp phục vụ hỗ trợ

Trong sự cố nghiêm trọng, tổ chức có thể cần đường hỗ trợ khẩn cấp. Tài khoản này vẫn cần được kiểm soát: người kích hoạt được định danh, lý do được ghi lại, quyền có thời hạn, phiên được theo dõi và có rà soát sau sử dụng.

Không coi tài khoản dùng hằng ngày của nhà cung cấp là tài khoản khẩn cấp để bỏ qua quy trình phê duyệt.

## 5. Một bản ghi kiểm kê hữu ích cần có gì?

Kiểm kê không chỉ là danh sách username. Bản ghi phải đủ để quyết định tài khoản có còn cần thiết và có thể thu hồi được hay không.

| Nhóm thông tin | Dữ liệu nên quản lý |
|---|---|
| Danh tính | Mã danh tính, họ tên, nhà cung cấp, đơn vị trực tiếp sử dụng lao động |
| Bảo trợ nội bộ | Người chịu trách nhiệm nghiệp vụ, chủ tài sản, đầu mối vận hành |
| Mục đích | Dịch vụ được hỗ trợ, loại thao tác, môi trường được phép |
| Tài sản | Nhóm máy chủ, thiết bị, ứng dụng hoặc subscription cụ thể |
| Cơ sở cho phép | Hợp đồng hoặc thỏa thuận dịch vụ liên quan, ticket hoặc change |
| Thời hạn | Ngày bắt đầu, ngày hết hạn danh tính, thời hạn từng lần cấp quyền |
| Đường truy cập | Cổng truy cập, broker, connector và điều kiện thiết bị |
| Quyền | Role, tài khoản đích, lệnh hoặc tác vụ được phép |
| Credential | Loại credential, nơi quản lý, chính sách xoay vòng hoặc hủy |
| Thu hồi | Chủ thể có quyền dừng phiên và cách vô hiệu hóa từng lớp |
| Bằng chứng | Mã phê duyệt, mã phiên, vị trí lưu nhật ký, kết quả rà soát |

Ví dụ dưới đây là bản ghi minh họa, không phải schema của một sản phẩm PAM:

```yaml
externalIdentity:
  id: ext-vendor-a-an
  person: Nguyen An
  vendor: Vendor A
  sponsor: owner-app-platform
  identityExpiresAt: "2030-06-30T10:00:00Z"

allowedSupport:
  environment: production
  targets:
    - app-prod-02
  role: application-service-maintainer
  accessPath: pam-session-broker
  standingPrivilege: false

sessionRequirements:
  approvedRequest: true
  personalMfa: true
  maximumGrantMinutes: 120
  observationRequired: true
  fileTransfer: approved-only

revocation:
  owner: internal-pam-operations
  terminateActiveSessions: true
  revokeTemporaryCredentials: true
  reconcileTargetChanges: true
```

Ngày hết hạn danh tính là giới hạn cho quan hệ truy cập dài hạn; nó không có nghĩa kỹ sư được giữ quyền quản trị liên tục đến ngày đó. Một danh tính còn hiệu lực có thể chưa có bất kỳ quyền đặc quyền nào ở thời điểm hiện tại.

## 6. Vòng đời tài khoản: từ yêu cầu đến xóa quyền

### 6.1. Bước 1 — Xác nhận nhu cầu và người chịu trách nhiệm

Trước khi tạo tài khoản, chủ tài sản nội bộ cần xác nhận:

- Nhà cung cấp đang hỗ trợ sản phẩm hay dịch vụ nào.
- Người cụ thể nào cần tham gia và có được phép dùng nhà thầu phụ hay không.
- Công việc có thực sự yêu cầu đặc quyền.
- Môi trường, tài sản và thời gian dự kiến.
- Ai phê duyệt, ai giám sát và ai có thể ra lệnh dừng.

Người bảo trợ nội bộ chịu trách nhiệm xác nhận nhu cầu tồn tại. Người bảo trợ không mặc nhiên có quyền phê duyệt mọi tài sản; quyết định cấp quyền vẫn phải theo phạm vi được ủy quyền.

Nếu nhà cung cấp chỉ cần xem log đã được lọc, có thể cung cấp dữ liệu đó thay vì mở một phiên quản trị hệ thống sản xuất.

### 6.2. Bước 2 — Tạo danh tính cá nhân và đăng ký xác thực

Danh tính truy cập phải gắn với người thật đã được xác minh qua quy trình của tổ chức. Việc nhận một email mang tên công ty nhà cung cấp chưa đủ để chứng minh người đó được chỉ định cho công việc.

Tài khoản nên được cấu hình để:

- Sử dụng xác thực đa yếu tố phù hợp với mức rủi ro.
- Có ngày hết hạn và người bảo trợ.
- Không tự nhận nhóm quản trị mặc định.
- Không dùng chung với công việc quản trị nội bộ.
- Có cơ chế khóa và phục hồi xác thực do tổ chức kiểm soát.

Nếu dùng liên kết danh tính với nhà cung cấp, cần hiểu ai có thể phát hành hoặc thay đổi danh tính phía họ. Việc liên kết giúp giảm quản lý mật khẩu cục bộ, nhưng tổ chức vẫn cần kiểm soát ủy quyền ở phía mình và có khả năng chặn truy cập khi cần.

### 6.3. Bước 3 — Cấp quyền theo yêu cầu cụ thể

Một yêu cầu có chất lượng cần mô tả tài sản đích, công việc, lý do cần đặc quyền, thời gian và kết quả mong đợi. “Hỗ trợ hệ thống theo hợp đồng” quá rộng để xác định quyền cho một phiên.

Kết hợp:

- **Least privilege:** chỉ cấp quyền đủ cho tác vụ.
- **JIT:** kích hoạt quyền gần thời điểm sử dụng và tự hết hạn.
- **JEA hoặc giới hạn tác vụ tương đương:** giới hạn hành động quản trị khi nền tảng hỗ trợ.
- **Phê duyệt theo phạm vi:** đúng chủ tài sản hoặc người được ủy quyền.

JIT chỉ điều chỉnh thời gian; nếu cấp toàn quyền quản trị trong hai giờ, kỹ sư vẫn có toàn quyền trong hai giờ đó. Muốn giảm phạm vi hành động phải thiết kế role, endpoint quản trị hoặc công cụ được phép.

### 6.4. Bước 4 — Thực hiện phiên qua đường được quản lý

Quyền truy cập tài nguyên cần đi qua điểm kiểm soát được xác định. Việc mở VPN thành công không nên tự động cho phép truy cập toàn bộ mạng quản trị.

Tùy kiến trúc, đường đi có thể là:

```text
Kỹ sư được định danh
    -> xác thực và kiểm tra điều kiện truy cập
    -> yêu cầu đã được phê duyệt
    -> PAM broker hoặc điểm quản trị được kiểm soát
    -> đúng tài sản và tài khoản đích được cấp
```

Hệ thống nên kiểm tra lại quyền khi bắt đầu phiên, không chỉ ở thời điểm tạo ticket. Một phê duyệt cũ không được dùng để bỏ qua tài khoản đã bị khóa, tài sản đã chuyển phạm vi hoặc cửa sổ bảo trì đã kết thúc.

### 6.5. Bước 5 — Kết thúc công việc và đối soát

Khi kỹ sư báo hoàn thành, cần xác nhận cả kết quả công việc lẫn trạng thái quyền:

- Dịch vụ đã đạt điều kiện bàn giao.
- Quyền tạm thời đã hết hoặc bị thu hồi.
- Phiên đã đóng; phiên treo được xử lý.
- Credential đã được xoay vòng, hủy hoặc để hết hạn theo thiết kế.
- Các thay đổi tài khoản, khóa, nhóm và cấu hình được đối soát.
- Nhật ký và phê duyệt có thể liên kết với nhau.

Không đánh giá công việc hoàn tất chỉ bằng việc đóng ticket trong khi phiên đặc quyền vẫn còn mở.

### 6.6. Bước 6 — Rà soát và offboarding

Khi nhân sự thay đổi hoặc hợp đồng kết thúc, xử lý cả danh tính dài hạn và những khả năng truy cập phát sinh trong quá trình hỗ trợ.

Các đối tượng cần rà soát gồm danh tính truy cập, nhóm quyền, tài khoản đích, chứng thư, token, khóa SSH, lịch tác vụ, connector hỗ trợ từ xa và phiên đang hoạt động.

Tài khoản không sử dụng trong một khoảng thời gian có thể cần khóa để rà soát. Tuy nhiên, “không có log đăng nhập” chỉ có ý nghĩa khi nguồn log đủ bao phủ các đường truy cập liên quan.

## 7. Thiết kế quyền theo công việc, không theo nhãn nhà cung cấp

Một cách cấp quyền dễ gây lỗi là tạo nhóm `VendorAdmins`, thêm mọi kỹ sư hỗ trợ vào nhóm và gán quyền quản trị cho toàn bộ máy chủ.

Cách làm rõ hơn là mô tả công việc trước:

| Công việc | Quyền có thể phù hợp | Quyền cần cân nhắc riêng |
|---|---|---|
| Đọc trạng thái dịch vụ | Xem tình trạng và log đã được giới hạn | Đọc toàn bộ dữ liệu khách hàng |
| Khởi động lại một dịch vụ | Điều khiển đúng dịch vụ qua tác vụ được giới hạn | Quản trị toàn máy chủ |
| Thay đổi cấu hình ứng dụng | Ghi đúng cấu hình và chạy bước kiểm tra được duyệt | Tạo người dùng hoặc thay chính sách xác thực |
| Nâng cấp phần mềm | Quyền triển khai trong cửa sổ bảo trì | Giữ quyền cài đặt thường trực |
| Chẩn đoán cơ sở dữ liệu | Các phép quan sát cần thiết, tài khoản hoặc role phù hợp | Xuất toàn bộ dữ liệu hoặc tạo quản trị viên mới |
| Bảo trì thiết bị cũ | Phiên broker đến thiết bị được chỉ định | Kết nối trực tiếp từ mọi nguồn |

Không phải tác vụ nào cũng giới hạn được bằng một tập lệnh đơn giản. Một lệnh có thể gọi shell, nạp plugin hoặc thực thi script khác; một trình soạn thảo chạy với quyền cao có thể trở thành đường thực thi lệnh tùy ý.

Khi tác vụ thực sự yêu cầu quyền rộng, cần thể hiện rõ điều đó trong yêu cầu và chọn biện pháp bổ sung: tài sản hẹp, thời gian ngắn, giám sát trực tiếp khi cần, hạn chế đường truyền tệp và đối soát thay đổi sau phiên.

## 8. Quản lý credential của nhà cung cấp

### 8.1. Ưu tiên giữ credential trong phạm vi quản lý

Nếu nền tảng cho phép, kỹ sư nên mở phiên mà không nhận mật khẩu tài khoản đích. Credential được giữ trong vault và sử dụng bởi broker hoặc cơ chế được kiểm soát.

Lợi ích là giảm việc sao chép mật khẩu vào email, ticket, trình quản lý mật khẩu cá nhân hay máy tính hỗ trợ. Nhưng phải kiểm tra thực tế sản phẩm và giao thức: một nhãn “không lộ mật khẩu” không đảm bảo người có quyền quản trị trên hệ thống đích không thể tạo đường truy cập khác.

### 8.2. Khi bắt buộc phải giao credential

Một số thiết bị hoặc quy trình bảo trì có thể yêu cầu cung cấp credential trực tiếp. Khi đó cần có quy trình checkout rõ ràng:

1. Xác thực cá nhân nhận credential.
2. Xác nhận yêu cầu và phạm vi tài sản.
3. Ghi nhận thời điểm cấp và giới hạn sử dụng.
4. Kiểm soát đường truy cập tương ứng.
5. Đổi hoặc thu hồi credential sau sử dụng theo thiết kế.
6. Xác minh credential cũ không còn sử dụng được trong phạm vi cần bảo vệ.

Không ghi mật khẩu vào trường mô tả ticket hoặc bản ghi phiên. Nếu mật khẩu đã bị tiết lộ ngoài kênh được phép, việc đánh dấu ticket là riêng tư không thay thế cho thu hồi hoặc xoay vòng.

### 8.3. Phân biệt xoay vòng, hết hạn và thu hồi

- **Xoay vòng mật khẩu:** thay giá trị bí mật dùng cho lần xác thực tiếp theo.
- **Hết hạn credential:** credential không còn hợp lệ sau thời điểm được cấu hình và được hệ thống thực thi.
- **Thu hồi credential:** chủ động làm credential mất hiệu lực trước hạn, nếu cơ chế hỗ trợ.
- **Dừng phiên:** chấm dứt kết nối hoặc ngữ cảnh đã được thiết lập.

Các hành động này không tương đương. Đổi mật khẩu có thể không kết thúc phiên đã xác thực. Thu hồi danh tính ở cổng truy cập có thể không làm token đã phát hành mất hiệu lực ngay. Chứng thư có thời hạn ngắn vẫn có cửa sổ sử dụng đến lúc hết hạn nếu đích không kiểm tra cơ chế thu hồi phù hợp.

Vì vậy, quy trình thu hồi phải xác định hành động cho từng loại credential và từng lớp phiên, đồng thời kiểm tra kết quả thực tế.

### 8.4. Không xoay vòng mù tài khoản có phụ thuộc

Một tài khoản hỗ trợ đôi khi bị dùng thêm cho dịch vụ hoặc tác vụ định kỳ. Đổi mật khẩu mà không biết phụ thuộc có thể làm gián đoạn hệ thống.

Cần tách tài khoản người thao tác khỏi tài khoản dịch vụ. Với phụ thuộc đã tồn tại, kiểm kê, chuyển đổi có kế hoạch và xác minh hoạt động trước khi coi việc xoay vòng là ổn định.

## 9. Giám sát phiên và bằng chứng

Một bộ bằng chứng hữu ích cần nối được **người – quyền được duyệt – hoạt động thực tế – kết quả thu hồi**.

Các dữ liệu thường cần liên kết:

- Mã danh tính cá nhân và nhà cung cấp.
- Mã yêu cầu, change hoặc sự cố.
- Người phê duyệt và thời gian phê duyệt.
- Tài sản, tài khoản đích và quyền được cấp.
- Thời điểm bắt đầu, kết thúc, dừng hoặc hết hạn.
- Nhật ký tại cổng truy cập, PAM và hệ thống đích.
- Thao tác truyền tệp, nâng quyền hoặc tạo credential nếu thu thập được.
- Kết quả thu hồi, xoay vòng và bàn giao công việc.

Dùng mã phiên hoặc mã liên kết để đối chiếu các nguồn. Đồng bộ thời gian giúp dựng lại trình tự, nhưng không nên chỉ dựa vào timestamp nếu có nhiều phiên gần nhau.

### 9.1. Recording có giới hạn

Video màn hình không nhất thiết cho biết mọi lệnh chạy trong nền. Nhật ký lệnh không nhất thiết phản ánh đầy đủ nội dung thao tác qua giao diện đồ họa. Kết nối mã hóa hoặc giao thức không được proxy hỗ trợ có thể làm giảm mức quan sát.

Vì thế, cần biết rõ đang ghi cái gì, phần nào không quan sát được và khi nào phải bổ sung log tại đích. Quy tắc dừng hoặc không cho mở phiên khi ghi hình lỗi cũng phải được xác định theo loại công việc; không mặc định mọi hệ thống PAM có cùng hành vi.

### 9.2. Bảo vệ cả bằng chứng lẫn dữ liệu xuất hiện trong bằng chứng

Bản ghi phiên có thể chứa dữ liệu nhạy cảm. Quyền xem, tải và xóa bản ghi phải được giới hạn; bản ghi cần có cơ chế bảo vệ tính toàn vẹn và thời hạn lưu theo chính sách đã được phê duyệt.

Người thực hiện phiên không nên có khả năng tự xóa dấu vết của mình. Người quản trị PAM cũng cần được giám sát phù hợp, vì họ có thể tác động đến chính điểm kiểm soát.

## 10. Thu hồi phải đi qua nhiều lớp

Giả sử kỹ sư cần bị chặn ngay vì được phát hiện dùng sai quyền. Chỉ khóa tài khoản ngoài chưa đủ để kết luận truy cập đã kết thúc.

| Lớp | Hành động có thể cần | Bằng chứng cần kiểm tra |
|---|---|---|
| Danh tính đầu vào | Khóa danh tính, bỏ nhóm hoặc chặn liên kết tương ứng | Lần đăng nhập mới bị từ chối |
| Quyền đã cấp | Hủy grant đang có và yêu cầu chưa sử dụng | Không thể mở phiên mới bằng phê duyệt cũ |
| Phiên tại cổng hoặc PAM | Dừng phiên và kết nối liên quan | Phiên không còn hoạt động |
| Phiên ở hệ thống đích | Chấm dứt ngữ cảnh còn tồn tại nếu cần | Hoạt động đặc quyền thực sự dừng |
| Credential đã cấp | Đổi mật khẩu, hủy token, thu hồi khóa hoặc chứng thư theo cơ chế | Credential cũ không còn được chấp nhận hoặc đã hết hạn được xác minh |
| Đường truy cập | Chặn tuyến truy cập được sử dụng trái phép | Không còn đường trực tiếp ngoài kiểm soát |
| Thay đổi duy trì truy cập | Rà soát tài khoản, khóa, nhóm, tác vụ và agent mới | Không còn khả năng truy cập ngoài phạm vi đã duyệt |

Dừng phiên ở broker cũng không đảm bảo mọi tiến trình con trên đích đều kết thúc. Một tác vụ đã được khởi chạy có thể tiếp tục chạy. Cần xác định xem điều đó là một phần hợp lệ của công việc hay cần xử lý trong quy trình ứng phó.

Trong sự cố, việc bảo toàn bằng chứng và khôi phục dịch vụ cần được điều phối bởi đầu mối nội bộ. Nhà cung cấp không nên là bên duy nhất có khả năng thu hồi tài khoản mà chính họ đang sử dụng.

## 11. Ví dụ xuyên suốt: hỗ trợ lỗi dịch vụ sản xuất

### 11.1. Yêu cầu ban đầu

Ứng dụng thanh toán gặp lỗi kết nối. Vendor A đề nghị một kỹ sư đăng nhập bằng tài khoản quản trị miền để kiểm tra toàn bộ cụm máy chủ.

Chủ dịch vụ xác nhận cần hỗ trợ, nhưng yêu cầu ban đầu chưa chỉ ra vì sao phải có quyền quản trị miền. Đội nội bộ cung cấp thông tin chẩn đoán ban đầu, sau đó thu hẹp công việc thành kiểm tra và điều chỉnh cấu hình một dịch vụ trên `app-prod-02`.

### 11.2. Thiết kế phiên

- Kỹ sư Nguyễn An sử dụng danh tính cá nhân `ext-vendor-a-an`.
- Người bảo trợ xác nhận kỹ sư được chỉ định cho yêu cầu này.
- Chủ tài sản phê duyệt cửa sổ hỗ trợ hai giờ.
- Quyền được cấp cho đúng máy và tác vụ cần thiết.
- Kỹ sư mở phiên qua PAM; credential đích do tổ chức quản lý.
- Truyền tệp chỉ được bật cho gói chẩn đoán đã được duyệt.
- Nhân sự nội bộ theo dõi khi thao tác có tác động cao.

Nếu phát hiện phải thay đổi ngoài phạm vi, kỹ sư dừng ở điểm kiểm soát để yêu cầu bổ sung. Việc đã được mở phiên không cấp thẩm quyền mở rộng công việc.

### 11.3. Kết thúc và xác minh

Sau khi sửa lỗi:

1. Đội nội bộ kiểm tra dịch vụ và xác nhận cấu hình đã thay đổi.
2. Phiên kết thúc và grant bị thu hồi.
3. Credential được xử lý theo chính sách của loại tài khoản.
4. Kiểm tra không có tài khoản hoặc khóa hỗ trợ mới ngoài thay đổi đã duyệt.
5. Liên kết log, phê duyệt, kết quả kiểm tra và mã phiên vào hồ sơ công việc.

Khi hợp đồng còn hiệu lực, danh tính cá nhân có thể được giữ ở trạng thái phù hợp để sử dụng cho lần hỗ trợ sau. Nhưng lần hỗ trợ sau phải có quyền mới theo công việc mới, không kế thừa grant của phiên vừa kết thúc.

## 12. Mẫu logic quyết định cấp phiên

Logic dưới đây là mã giả để làm rõ các điều kiện độc lập; nó không phải cấu hình triển khai cho một sản phẩm:

```text
function authorizeVendorSession(identity, request, target, now):
    require identity.isActive
    require identity.isNamedPerson
    require identity.vendorRelationshipIsActive
    require identity.sponsorIsValid
    require identity.authenticationMeetsPolicy
    require identity.deviceAndConnectionMeetPolicy

    require request.isApproved
    require request.approverCanApprove(target)
    require request.personId == identity.id
    require target in request.allowedTargets
    require now within request.approvedWindow
    require request.actions fit request.approvedRole
    require request.isNotRevoked

    require managedAccessPathIsAvailable(target)
    require observationRequirementsAreSatisfied(request, target)

    sessionDeadline = minimum(
        request.windowEnd,
        identity.expiration,
        vendorRelationship.expiration,
        now + policy.maximumSessionDuration
    )

    issueScopedGrant(identity, request, target, sessionDeadline)
    startManagedSession()
```

Điểm hết hạn được tính khi mở phiên chỉ là một phần. Khi danh tính bị khóa hoặc grant bị thu hồi giữa phiên, hệ thống cần cơ chế thực thi thay đổi đó theo thiết kế. Nếu nền tảng chỉ kiểm tra lúc đăng nhập, tổ chức phải biết khoảng trống này và có cách dừng phiên phù hợp.

Cũng cần xử lý khác nhau giữa lỗi điều kiện truy cập và sự cố khẩn cấp. Nếu thiếu quan sát bắt buộc, không âm thầm mở phiên như bình thường; chuyển sang quy trình khẩn cấp được định nghĩa và ghi nhận đầy đủ nếu tổ chức cho phép.

## 13. Ngoại lệ và cách quản lý

### 13.1. Thiết bị chỉ có một tài khoản quản trị

Giữ credential trong PAM, định danh từng người ở đầu vào, kiểm soát đường truy cập và liên kết phiên với tài khoản đích. Hạn chế sử dụng đồng thời nếu làm mất khả năng đối chiếu. Ghi rõ giới hạn quy trách nhiệm tại hệ thống đích.

### 13.2. Nhà cung cấp yêu cầu công cụ hỗ trợ riêng

Kiểm tra công cụ có tạo kết nối luôn bật, tài khoản riêng, khả năng truyền tệp hoặc thực thi từ xa ngoài PAM hay không. Xác định người sở hữu, cách bật/tắt, log và cơ chế thu hồi.

Không coi việc phiên màn hình chính đã được ghi là đủ nếu công cụ còn một đường điều khiển khác không được quản lý.

### 13.3. Cần hỗ trợ ngoài giờ

Có thể chuẩn bị trước danh tính và quy trình trực ca, nhưng quyền đặc quyền chỉ được kích hoạt khi có công việc. Quy trình cần chỉ rõ ai có quyền duyệt ngoài giờ và ai có thể can thiệp vào phiên.

### 13.4. Nhà thầu phụ thay người thực hiện

Không chuyển giao tài khoản của kỹ sư cũ. Xác minh người mới, quan hệ với nhà cung cấp, phạm vi được phép và người bảo trợ; cấp danh tính và quyền riêng. Việc một công ty được ký hợp đồng không tự động xác nhận mọi người mà công ty đó giới thiệu đều được phép truy cập.

### 13.5. Bảo trì làm gián đoạn điểm kiểm soát PAM

Lập kế hoạch đường quản trị và phục hồi trước khi bắt đầu. Nếu cần ngoại lệ khẩn cấp, xác định trước tài sản, người kích hoạt, thời hạn, cách lưu bằng chứng và bước thu hồi. Không để chính công việc bảo trì biến thành một ngoại lệ không có điểm kết thúc.

## 14. Những lỗi thường gặp và dấu hiệu nhận biết

| Lỗi thiết kế | Dấu hiệu | Cách điều chỉnh |
|---|---|---|
| Dùng chung danh tính đầu vào | Log chỉ có tên hãng hoặc đội hỗ trợ | Định danh cá nhân và ánh xạ từng phiên |
| Cấp quyền theo thời hạn hợp đồng | Tài khoản quản trị luôn hoạt động nhiều tháng | Tách thời hạn danh tính và thời hạn grant |
| Chỉ kiểm soát VPN | Kết nối mạng thành công là truy cập được nhiều máy | Thêm ủy quyền theo tài sản và tác vụ |
| Có PAM nhưng vẫn có đường trực tiếp | Credential dùng được từ máy ngoài broker | Kiểm soát đường truy cập và credential |
| Tin rằng ghi hình ngăn được mọi sai phạm | Không có quyền dừng hoặc rà soát tại đích | Kết hợp giới hạn quyền, giám sát và thu hồi |
| Chỉ khóa tài khoản khi kết thúc | Phiên, token hoặc khóa vẫn còn hiệu lực | Thu hồi theo từng lớp và xác minh |
| Cho phép tự tạo tài khoản hỗ trợ | Xuất hiện credential không có chủ sở hữu | Đối soát thay đổi và quản lý danh tính phát sinh |
| Không có người bảo trợ | Không ai xác nhận tài khoản còn cần thiết | Gán chủ trách nhiệm và đặt lịch rà soát |
| Trộn tài khoản người và dịch vụ | Xoay vòng làm agent hoặc tác vụ ngừng chạy | Tách danh tính và quản lý phụ thuộc |
| Gia hạn tự động theo thói quen | Không có công việc cụ thể cho lần gia hạn | Yêu cầu xác nhận lại nhu cầu và phạm vi |

## 15. Đánh giá hiệu quả kiểm soát

Một số chỉ số giúp phát hiện lỗ hổng vận hành:

- Tỷ lệ danh tính nhà cung cấp có người bảo trợ và ngày hết hạn hợp lệ.
- Số tài khoản đặc quyền thường trực còn tồn tại cho nhân sự bên ngoài.
- Tỷ lệ phiên liên kết được với yêu cầu đã phê duyệt và một cá nhân cụ thể.
- Số lần cấp quyền vượt thời hạn hoặc vượt phạm vi tài sản.
- Thời gian từ khi có yêu cầu thu hồi đến khi chặn được truy cập ở các lớp liên quan.
- Số credential hoặc đường hỗ trợ phát hiện ngoài kiểm kê.
- Tỷ lệ kiểm tra sau phiên phát hiện tài khoản, khóa hoặc thay đổi chưa được duyệt.
- Số ngoại lệ đã quá hạn mà chưa được xử lý.

Cần xác định mẫu số và phạm vi quan sát. “100% phiên đi qua PAM có recording” không cho biết có bao nhiêu phiên đang đi ngoài PAM. “100% tài khoản trong kho đã xoay vòng” không chứng minh mọi tài khoản đặc quyền của nhà cung cấp đều đã được đưa vào kho.

Có thể dùng các tình huống kiểm tra vận hành như: hết hạn giữa phiên; nhân sự nhà cung cấp đổi đơn vị; cổng truy cập bị khóa nhưng token đích chưa hết hạn; đường truy cập trực tiếp vô tình được mở; hoặc dịch vụ recording không hoạt động. Kết quả cần phản ánh truy cập thực tế, không chỉ trạng thái cấu hình.

## 16. Tự kiểm tra sau bài học

1. **Tài khoản vendor có MFA và VPN đã đủ để được coi là kiểm soát tốt chưa?**  
   Chưa. Cần kiểm soát quyền tại tài sản đích, thời hạn, phê duyệt, đường truy cập, hoạt động trong phiên và thu hồi. MFA chủ yếu củng cố bước xác thực; VPN chủ yếu cung cấp đường kết nối theo cấu hình.

2. **Một thiết bị dùng tài khoản quản trị chung có thể được quản lý trong PAM không?**  
   Có thể, nếu tổ chức kiểm soát credential và đường truy cập, định danh từng người trước broker và giữ được liên kết với phiên. Khả năng quy trách nhiệm vẫn có giới hạn nếu còn đường trực tiếp hoặc log đích không phân biệt phiên.

3. **Đổi mật khẩu sau phiên có đảm bảo nhà cung cấp mất mọi quyền truy cập không?**  
   Không. Cần xem phiên đang tồn tại, token, khóa, chứng thư, tài khoản mới và các cơ chế duy trì truy cập khác.

4. **Danh tính có ngày hết hạn sau sáu tháng có nên giữ quyền quản trị sáu tháng không?**  
   Không nên suy diễn như vậy. Danh tính thể hiện quan hệ truy cập; grant đặc quyền phải gắn với nhu cầu và khoảng thời gian cụ thể.

5. **Ai chịu trách nhiệm xác nhận công việc và thu hồi?**  
   Trách nhiệm phải được phân công cho các đầu mối nội bộ: người bảo trợ, chủ tài sản, vận hành PAM và đầu mối ứng phó khi cần. Nhà cung cấp cung cấp thông tin và thực hiện công việc trong quyền được cấp.

Một vendor privileged account được quản lý tốt phải trả lời được: **ai dùng, dùng để làm gì, trên đâu, trong bao lâu, đã làm gì và quyền đã kết thúc như thế nào**.
