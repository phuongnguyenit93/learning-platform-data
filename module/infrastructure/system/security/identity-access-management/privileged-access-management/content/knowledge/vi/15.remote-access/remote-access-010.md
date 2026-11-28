# Network path restriction trong truy cập quản trị đặc quyền

## 1. Mục tiêu và phạm vi

**Network path restriction** là việc giới hạn các đường mạng mà một chủ thể hoặc thành phần có thể dùng để tiếp cận tài nguyên. Trong truy cập từ xa có PAM, mục tiêu thường là buộc lưu lượng quản trị đi qua những điểm thực thi đã được thiết kế, đồng thời giảm khả năng đi vòng qua chúng.

Ví dụ, một kỹ sư được cấp quyền SSH tới máy chủ production trong 30 phút qua PAM gateway. Thiết kế chưa đạt mục tiêu nếu kỹ sư vẫn có thể dùng VPN để SSH trực tiếp tới máy chủ bằng một credential đã biết. Phiên trực tiếp đó có thể bỏ qua kiểm soát thời gian, liên kết danh tính và ghi nhận hoạt động của gateway.

Bài học tập trung vào bốn kết quả:

- Xác định chính xác nguồn, đích và các chặng của đường quản trị.
- Thực thi các đường được phép và chặn những đường ngoài phạm vi.
- Kết hợp hạn chế mạng với least privilege, JIT/JEA và quản lý credential.
- Thu thập bằng chứng cho cả kết nối được phép, kết nối bị từ chối và giới hạn còn tồn tại.

Hạn chế đường mạng là một lớp của PAM. Nó không tự xác thực con người, không thay quyền tại đích và không tự thu hồi mọi hoạt động sau khi một phiên bị ngắt.

## 2. Phân biệt đường mạng, danh tính và quyền

Một yêu cầu quản trị đi qua nhiều quyết định khác nhau:

| Lớp | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Danh tính | Ai đang yêu cầu truy cập? | Kỹ sư được xác thực bằng danh tính riêng và MFA |
| Ủy quyền PAM | Người đó được mở phiên nào? | Chỉ máy chủ A, thời hạn 30 phút |
| Đường mạng | Thành phần nào được kết nối tới đâu? | Chỉ gateway G được tới cổng SSH của A |
| Credential | Bằng chứng nào được dùng ở đích? | Credential do vault cấp cho gateway |
| Quyền tại đích | Tài khoản thực hiện được thao tác gì? | Chỉ các tác vụ chẩn đoán đã định |
| Phiên và bằng chứng | Hoạt động được giới hạn, quan sát ra sao? | Liên kết session, log đích và ghi nhận của gateway |

Một firewall chấp nhận kết nối từ gateway chưa chứng minh người dùng có quyền thực hiện mọi lệnh. Ngược lại, PAM chỉ hiển thị một máy chủ trong giao diện chưa chứng minh các đường mạng tới máy chủ khác đã bị chặn.

Cần mô tả rõ thành phần **quyết định** và thành phần **thực thi**. Ví dụ, PAM quyết định người dùng được mở phiên tới A; firewall giới hạn nguồn kết nối vào A; hệ điều hành A thực thi quyền của tài khoản được dùng.

## 3. Mô hình đường quản trị tham chiếu

~~~mermaid
flowchart LR
    U["Thiết bị quản trị viên"] -->|Điểm vào được phép| P["PAM: xác thực và ủy quyền"]
    U -->|Luồng client được hỗ trợ| G["Gateway quản trị"]
    P -->|Quyết định cho phiên| G
    G -->|Giao thức quản trị được phép| T["Tài nguyên production"]
    V["Vault hoặc broker"] -->|Credential theo quyền| G
    G -->|Sự kiện phiên| L["Hệ thống lưu bằng chứng"]
    T -->|Log tại đích| L
    U -. "Đường trực tiếp phải bị hạn chế" .-> T
~~~ 

Sơ đồ thể hiện trách nhiệm logic. Có sản phẩm đưa cả lưu lượng người dùng qua cổng PAM; sản phẩm khác cho client kết nối tới gateway sau khi nhận quyền. Cần xác minh luồng thực tế trước khi xây rule.

Đường truy cập có thể gồm:

1. Thiết bị người dùng tới điểm vào.
2. Client hoặc điểm vào tới gateway.
3. Gateway tới target.
4. Gateway tới vault, nguồn danh tính và hệ thống giám sát.
5. Target tới các phụ thuộc cần cho công việc được phép.

Chặng 4 là đường phụ trợ quan trọng, nhưng việc gateway kết nối được tới vault không đồng nghĩa nó cần được tới mọi máy chủ. Chặng 5 cũng cần chú ý: người dùng vào đúng target vẫn có thể tạo kết nối tiếp sang tài nguyên khác nếu quyền và mạng tại target cho phép.

## 4. Kiểm kê đường mạng trước khi viết rule

### 4.1. Xác định đối tượng được bảo vệ

Mỗi tài nguyên cần có định danh, owner, môi trường và điểm quản trị rõ ràng. Không chỉ ghi tên máy chủ; cần nhận biết các endpoint có thể thực hiện thao tác quản trị:

- SSH, RDP hoặc giao thức quản trị tương tác khác.
- Web quản trị và API điều khiển.
- Console, giao diện hypervisor hoặc bộ điều khiển tập trung.
- Cổng quản trị ngoài băng.
- Endpoint truy cập qua mạng riêng, mạng công cộng hoặc mạng đối tác.
- Các địa chỉ IPv4, IPv6, interface phụ và địa chỉ thay đổi theo cụm.

Một thiết bị có thể được quản lý qua nhiều giao thức. Bảo vệ SSH qua gateway nhưng để web quản trị mở rộng chỉ tạo ra phạm vi kiểm soát một phần.

### 4.2. Lập ma trận luồng được phép

Một ma trận hữu ích cần có nguồn, đích, mục đích và owner, thay vì chỉ danh sách cổng.

| Nguồn | Đích | Dịch vụ minh họa | Mục đích | Điều kiện |
|---|---|---|---|---|
| Thiết bị quản trị được quản lý | Điểm vào PAM | Kênh ứng dụng bảo mật | Xác thực và yêu cầu truy cập | Danh tính và policy hợp lệ |
| Nhóm gateway production | Nhóm target production A | SSH | Phiên quản trị đã cấp | Đúng target và giao thức |
| Nhóm gateway production | Vault | API được bảo vệ | Lấy credential theo policy | Danh tính dịch vụ được cấp quyền |
| Gateway | Dịch vụ phân giải tên được duyệt | DNS theo thiết kế | Phân giải endpoint | Giới hạn resolver và đường kết nối |
| Gateway và target | Hệ thống log | Kênh thu thập được hỗ trợ | Lưu bằng chứng | Quyền gửi và bảo vệ truyền tải |
| Thiết bị người dùng | Target production A | SSH trực tiếp | Không thuộc luồng thông thường | Bị từ chối |
| Target production A | Target production B | Kênh quản trị | Không có nhu cầu trong tình huống | Bị từ chối theo phạm vi |

Các dịch vụ trong bảng chỉ minh họa. Cổng, hướng khởi tạo và giao thức phải lấy từ triển khai thực tế, bao gồm cả những kết nối phụ mà sản phẩm yêu cầu.

### 4.3. Ghi lại điểm quan sát

Với mỗi chặng, cần biết có thể thu bằng chứng ở đâu:

- Log quyết định của PAM.
- Log kết nối của gateway.
- Flow log hoặc log từ chối ở lớp mạng.
- Log host firewall.
- Log xác thực và hoạt động ở đích.

Một điểm ghi nhận không nhìn thấy toàn bộ đường. Flow log có thể chứng minh một luồng mạng được chấp nhận, nhưng không đủ để kết luận người dùng đã chạy lệnh nào trong phiên mã hóa.

## 5. Các nguyên tắc thiết kế chính

### 5.1. Chỉ mở những luồng có mục đích cụ thể

Bắt đầu từ nhu cầu đã biết rồi cho phép các luồng tương ứng. Một rule kiểu “gateway tới mọi mạng nội bộ, mọi dịch vụ” tạo phạm vi ảnh hưởng rộng nếu gateway hoặc một phiên bị lợi dụng.

Phạm vi rule nên hẹp theo các chiều có thể thực thi:

~~~text
Nguồn được quản lý
  + đích được kiểm kê
  + dịch vụ cần dùng
  + hướng kết nối
  + môi trường phù hợp
  + owner và vòng đời thay đổi
~~~

Không phải thiết bị nào cũng hỗ trợ mọi chiều trên. Nếu rule mạng chỉ phân biệt địa chỉ và cổng, các điều kiện danh tính, thời gian hoặc tác vụ cần được thực thi ở lớp khác.

### 5.2. Thực thi ở phía tài nguyên khi có thể

Giới hạn tại điểm vào giúp giảm lưu lượng không phù hợp, nhưng không nên là nơi duy nhất bảo vệ target. Một đường mạng mới, VPN khác hoặc host trung gian có thể bỏ qua điểm vào đó.

Tùy nền tảng, có thể kết hợp:

- Kiểm soát giữa các vùng mạng.
- Rule gắn với interface hoặc nhóm tài nguyên.
- Host firewall tại đích.
- Ràng buộc nguồn truy cập trong dịch vụ quản trị.
- Danh tính workload hoặc kênh xác thực giữa các thành phần.

Số lớp không phải mục tiêu tự thân. Điều cần đạt là chặn được đường đi vòng liên quan và có owner chịu trách nhiệm cho từng lớp.

### 5.3. Tách vùng theo phạm vi ảnh hưởng

Không mặc định một gateway duy nhất phải quản trị mọi môi trường. Có thể tách gateway hoặc connector theo production, non-production, nhóm nhạy cảm, vùng mạng hay tenant.

Việc tách giúp giới hạn đích mà một thành phần bị xâm phạm có thể tiếp cận. Đổi lại, nó tăng số thành phần, rule, dependency và công việc vận hành.

Quyết định cần dựa trên phạm vi ảnh hưởng và khả năng quản lý, không chỉ số lượng gateway.

### 5.4. Giữ kiểm soát cho cả đường phụ trợ

Gateway thường cần tới nguồn danh tính, vault, DNS, đồng bộ thời gian, log và kênh cập nhật. Nếu mở toàn bộ egress để “hệ thống chạy được”, các đường phụ trợ có thể trở thành đường phát tán hoặc đưa dữ liệu ra ngoài.

Cần kiểm kê các luồng này theo mục đích và xác định hành vi khi dependency mất. Ví dụ, nếu policy bắt buộc lưu bằng chứng, sự cố kết nối tới kho log cần có hành vi rõ; không tự chuyển sang một đường quản trị trực tiếp rộng hơn.

## 6. Nguồn mà target nhìn thấy có thể khác nguồn ban đầu

### 6.1. Proxy và NAT

Trong nhiều mô hình proxy, target nhìn thấy địa chỉ của gateway thay vì địa chỉ thiết bị người dùng. Nếu có NAT, target hoặc firewall có thể chỉ thấy địa chỉ đã dịch.

Vì vậy cần xác định **địa chỉ nguồn tại từng điểm thực thi**, không lấy địa chỉ người dùng rồi áp dụng cho mọi chặng.

Ví dụ:

~~~text
Người dùng:        192.0.2.25
Gateway:          198.51.100.10
Nguồn sau NAT:    198.51.100.20
Target:           203.0.113.40
~~~

Đây là các địa chỉ dành cho tài liệu minh họa. Trong thiết kế, rule tại target phải dùng nguồn quan sát thực tế theo kiến trúc và có kiểm chứng.

Nếu nhiều hệ thống cùng dùng một nguồn NAT, cho phép địa chỉ đó có thể mở quyền kết nối cho nhiều chủ thể hơn dự kiến. Cần xem xét tách nguồn, bổ sung danh tính ở lớp khác hoặc thay đổi ranh giới thực thi.

### 6.2. Cụm gateway và failover

Một gateway dự phòng có thể dùng địa chỉ hoặc đường ra khác gateway đang hoạt động. Nếu chỉ cho phép node đầu tiên, failover có thể làm mất truy cập. Nếu xử lý bằng cách mở cả dải mạng quá rộng, phạm vi kiểm soát lại suy giảm.

Cần kiểm kê toàn bộ nguồn hợp lệ, đường đi khi chuyển vùng và cơ chế cập nhật. Kiểm thử phải có tình huống failover thật trong phạm vi an toàn, không chỉ xem cấu hình node chính.

### 6.3. Nhóm bảo mật và nhãn tài nguyên

Một số nền tảng cho phép rule tham chiếu nhóm tài nguyên hoặc danh tính thành phần thay vì địa chỉ cố định. Cách này có thể giảm công việc cập nhật IP, nhưng phạm vi phụ thuộc vào cách nhóm và membership được quản lý.

Nếu bất kỳ workload nào cũng có thể gia nhập nhóm “PAM gateway”, rule tham chiếu nhóm đó sẽ không còn giới hạn đúng nguồn mong muốn. Quyền thay đổi membership là một phần của ranh giới bảo vệ.

## 7. Đích động, DNS và xác minh máy chủ

Tên DNS giúp định danh endpoint nhưng không tự đảm bảo tài nguyên đích hợp lệ.

Cần tách ba bước:

1. PAM chọn target từ danh mục được quản lý.
2. Hệ thống phân giải endpoint theo thiết kế.
3. Gateway xác minh danh tính máy chủ bằng cơ chế của giao thức.

Một rule theo địa chỉ IP có thể trở nên lỗi thời khi tài nguyên thay địa chỉ. Một rule theo FQDN phụ thuộc vào khả năng sản phẩm: cách phân giải, thời điểm cập nhật, cache, wildcard và cách xử lý nhiều địa chỉ.

Không mặc định rule FQDN là bộ lọc URL hoặc là bằng chứng rằng máy chủ ở địa chỉ đó đúng danh tính.

Nếu tên hợp lệ bị đổi sang endpoint không mong muốn, các lớp xác minh host key, chứng thư hoặc danh tính dịch vụ vẫn cần hoạt động. Mã hóa kết nối mà bỏ xác minh đích có thể bảo vệ đường truyền tới nhầm nơi.

Danh mục target và quyền sửa danh mục cũng cần được kiểm soát. Nếu người dùng tùy ý gửi hostname và cổng cho gateway, gateway có thể trở thành điểm kết nối tới các đích ngoài phạm vi.

## 8. Các đường đi vòng thường bị bỏ sót

### 8.1. VPN cấp quyền tới cả vùng quản trị

VPN cung cấp kết nối nhưng không tự buộc mọi phiên đi qua PAM. Nếu thiết bị người dùng có thể tới trực tiếp cổng quản trị của target, cần xử lý ở rule mạng và dịch vụ liên quan.

Một thiết kế có thể cho VPN tới cổng PAM nhưng không tới target. Khả năng này phải được kiểm thử từ đúng vị trí và nhóm người dùng dự kiến.

### 8.2. Target có nhiều interface hoặc hai ngăn xếp địa chỉ

Rule bảo vệ interface quản trị IPv4 không tự bảo vệ một địa chỉ IPv6, interface công cộng hoặc mạng dự phòng khác.

Phải kiểm kê các đường thật sự tồn tại và xác định chính sách tương ứng. Không nên dùng kết quả kiểm thử trên một địa chỉ để suy ra mọi endpoint của tài nguyên đều đã được bảo vệ.

### 8.3. Web, API, console và đường ngoài băng

Chặn SSH trực tiếp không xử lý API có quyền quản trị, web console hoặc giao diện ngoài băng. Mỗi đường cần được:

- Đưa vào luồng được quản lý.
- Hạn chế bằng kiểm soát tương đương theo khả năng.
- Hoặc ghi nhận ngoại lệ có owner, phạm vi và thời hạn.

Một ngoại lệ đã được ghi lại vẫn là ngoại lệ; nó không trở thành bằng chứng rằng mọi truy cập đã đi qua PAM.

### 8.4. Forwarding, tunnel và kênh bổ sung

Một phiên SSH được cấp tới A có thể hỗ trợ forwarding hoặc tạo tunnel nếu client, gateway và đích cho phép. Các kênh này có thể mở đường tới dịch vụ mà người dùng không được tiếp cận trực tiếp.

Cần đánh giá theo khả năng thực tế của giao thức và sản phẩm:

- Có cho phép port forwarding hay không.
- Có cho phép agent forwarding hay chuyển tiếp danh tính không.
- Có cho truyền file, ánh xạ ổ đĩa hoặc clipboard không.
- Có hạn chế đích của kênh bổ sung không.
- Có quan sát được hoạt động trên các kênh đó không.

Chặn một loại forwarding tại gateway chưa chắc ngăn mọi cách tạo kết nối từ chương trình chạy trên target. Quyền tại đích và egress của target vẫn cần phù hợp với nhiệm vụ.

### 8.5. Target trở thành điểm trung chuyển

Nếu người dùng có quyền chạy chương trình trên A và A được tới B, việc chỉ cho gateway kết nối A chưa đủ để cô lập B khỏi phiên đó.

Cần kết hợp các biện pháp theo nhu cầu:

- JEA hoặc role tại đích giới hạn khả năng thực thi.
- Egress của A chỉ tới các dependency cần thiết.
- B giới hạn nguồn và danh tính quản trị.
- Giảm credential hoặc token có thể sử dụng từ A.
- Giám sát hành vi kết nối tiếp theo trong phạm vi cho phép.

Không tuyên bố đã ngăn di chuyển ngang chỉ vì menu PAM chỉ có một target.

## 9. Kết hợp với vault, JIT và JEA

### 9.1. Vault giảm phơi lộ credential, mạng giới hạn nơi sử dụng

Nếu gateway lấy credential từ vault và không tiết lộ cho người dùng, nguy cơ dùng lại secret ngoài luồng có thể giảm. Tuy vậy, credential vẫn có thể có nguồn phơi lộ khác và gateway vẫn là thành phần đặc quyền.

Khi có khả năng, nên giới hạn nơi credential có thể được dùng, phạm vi tài khoản tại đích và vòng đời của nó. Một credential bị lộ sẽ có tác động thấp hơn nếu tài nguyên còn kiểm soát nguồn truy cập, quyền và thời hạn phù hợp.

Rotation cần xét dependency. Không đổi credential của dịch vụ đang hoạt động chỉ để chứng minh một rule mạng đã bị đóng.

### 9.2. JIT không đồng nghĩa phải tạo rule firewall cho từng phiên

JIT có thể được thực thi bằng grant tạm thời, credential ngắn hạn, policy cấp phiên hoặc tổ hợp nhiều lớp. Kiến trúc có thể giữ đường gateway tới target ổn định và chỉ cấp quyền mở phiên khi có nhu cầu.

Nếu chọn rule mạng tạm thời cho từng yêu cầu, cần thiết kế:

- ID của yêu cầu và rule liên quan.
- Thời điểm bắt đầu và hết hạn.
- Hành vi khi thao tác tạo hoặc xóa rule lỗi.
- Cơ chế dọn rule mồ côi.
- Xử lý race condition giữa hai phiên dùng chung nguồn và đích.
- Bằng chứng cho việc rule hết hiệu lực.

Một rule bị xóa chưa chắc làm mọi kết nối đang tồn tại kết thúc ngay. Thiết bị stateful có thể giữ trạng thái theo hành vi cụ thể; phải kiểm chứng và bổ sung kết thúc phiên khi mục tiêu yêu cầu.

### 9.3. JEA xử lý quyền thao tác bên trong đường đã mở

Network path restriction giới hạn khả năng tới dịch vụ. JEA giới hạn tác vụ mà chủ thể có thể thực hiện khi đã vào dịch vụ đó.

Nếu tài khoản đích vẫn có toàn quyền và tự tạo kết nối ra ngoài, một đường tới đúng máy chủ vẫn có thể dẫn tới tác động rộng. Quyền hiệu lực cần khớp nhiệm vụ, không chỉ role hiển thị trong PAM.

## 10. Ví dụ thiết kế: chẩn đoán một máy chủ production

### 10.1. Bối cảnh

Kỹ sư Linh cần xem tình trạng dịch vụ trên app-prod-a trong 30 phút. Công việc không yêu cầu sửa cấu hình, truy cập app-prod-b hoặc kết nối database quản trị.

Giả định môi trường có gateway production, vault và role chẩn đoán tại đích. Khả năng của từng thành phần đã được kiểm chứng trước khi dùng cho tình huống.

### 10.2. Ý định policy

~~~yaml
# Mã giả mô tả ý định; không phải cấu hình để triển khai trực tiếp.
request:
  subject: engineer-linh
  target: app-prod-a
  role: diagnostics
  duration_minutes: 30

session:
  entry: approved-pam-entry
  gateway_pool: prod-diagnostics
  credential_source: approved-vault
  credential_export: false
  additional_tunnels: disallowed

network_intent:
  allow:
    - source: prod-diagnostics-gateways
      destination: app-prod-a-management
      service: approved-ssh-service
  deny_in_scope:
    - source: remote-user-network
      destination: app-prod-a-management
      service: direct-admin-access
    - source: app-prod-a
      destination: app-prod-b-management
      service: admin-access-without-approved-need
~~~

Policy trên mô tả mong muốn. Nó không chứng minh firewall hoặc hệ điều hành đã thực thi các điều kiện đó.

### 10.3. Luồng được phép

1. Linh xác thực bằng danh tính cá nhân và đáp ứng điều kiện PAM.
2. PAM cấp phiên đúng app-prod-a và role chẩn đoán.
3. Gateway phân giải target từ danh mục và xác minh máy chủ.
4. Gateway lấy credential theo quyền được cấp.
5. Luồng gateway tới app-prod-a đi qua rule mạng phù hợp.
6. Quyền tại đích giới hạn thao tác chẩn đoán.
7. Log liên kết yêu cầu, gateway, tài khoản đích và hoạt động.

### 10.4. Những điều cần chứng minh riêng

| Yêu cầu | Cách kiểm chứng theo phạm vi |
|---|---|
| Linh không SSH trực tiếp từ mạng người dùng | Thử kết nối có kiểm soát từ đúng nguồn, đối chiếu log từ chối |
| Gateway chỉ tới đích được cấp | Kiểm tra policy target và rule thực thi, thử yêu cầu ngoài phạm vi |
| Không mở thêm đường tới B | Kiểm tra quyền phiên, kênh bổ sung và rule liên quan ở A/B |
| Role chẩn đoán không có quyền sửa cấu hình | Kiểm tra quyền hiệu lực bằng thao tác an toàn |
| Hết 30 phút thì truy cập kết thúc theo policy | Quan sát cấp mới, phiên đang mở và kết quả tại đích |
| Credential được xử lý đúng vòng đời | Kiểm tra grant hoặc credential liên quan, không suy từ kết quả mạng |

Nếu chặng A tới B chưa được kiểm tra, báo cáo giữ trạng thái chưa kiểm chứng. Không gộp nó vào kết quả của thử nghiệm từ thiết bị Linh tới A.

## 11. Triển khai thay đổi mà vẫn giữ khả năng vận hành

### 11.1. Chuẩn bị

Trước khi áp dụng hạn chế, cần có:

- Ma trận luồng được owner xác nhận.
- Các dependency cần thiết của gateway và target.
- Cách thu thập log và kiểm tra kết quả.
- Đường phục hồi được phép nếu mất truy cập.
- Phạm vi rollout và điều kiện rollback rõ ràng.

Phân biệt truy cập quản trị của con người với lưu lượng ứng dụng và tự động hóa. Một máy chủ có thể vừa là target quản trị vừa là thành phần dịch vụ; rule quá rộng theo máy hoặc subnet có thể gây tác động ngoài dự kiến.

### 11.2. Áp dụng theo nhóm nhỏ

Có thể bắt đầu bằng một nhóm target đại diện, xác minh luồng được phép và bị từ chối, rồi mở rộng theo kết quả.

Nếu nền tảng có khả năng quan sát hoặc đánh giá policy trước khi chặn, dữ liệu đó có ích để phát hiện dependency. Tuy nhiên, log quá khứ không đảm bảo đã thấy mọi tác vụ định kỳ hoặc đường phục hồi ít dùng.

Khi mở rộng, cần kiểm tra lại membership, nguồn NAT, failover và khác biệt giữa các vùng. Không sao chép rule chỉ dựa trên tên môi trường.

### 11.3. Break-glass có phạm vi

Đường khẩn cấp cần được thiết kế trước: ai có quyền dùng, từ đâu, tới tài nguyên nào, credential nào, thời gian và bằng chứng ra sao.

Nếu đường khẩn cấp vẫn luôn mở rộng và credential có thể dùng thường xuyên, nó có thể trở thành đường đi vòng thông thường.

Sau khi sử dụng, cần thu hồi quyền tạm, xử lý credential theo thiết kế, kiểm tra rule và lưu dấu người chịu trách nhiệm. Việc hệ thống đã hoạt động lại không tự chứng minh ngoại lệ khẩn cấp đã được đóng.

### 11.4. Rollback đúng đối tượng

Nếu rule mới làm mất đường quản trị hợp lệ, rollback cần khôi phục đúng thay đổi đã áp dụng. Không mở mọi nguồn tới mọi cổng để giải quyết một lỗi chưa phân loại.

Cần xác định lỗi do đường mạng, phân giải tên, xác minh máy chủ, xác thực hay quyền tại đích. Mỗi lớp cần một cách xử lý khác nhau.

## 12. Kiểm thử đường được phép và đường bị từ chối

Một bộ kiểm chứng nên bao phủ cả hành vi bình thường và các đường đi vòng có liên quan:

| Tình huống | Kết quả cần quan sát |
|---|---|
| Người có quyền mở đúng target qua gateway | Phiên thành công và có liên kết bằng chứng |
| Người chưa có quyền dùng cùng gateway | Không mở phiên chỉ vì đường mạng đang cho phép |
| Kết nối trực tiếp từ mạng người dùng | Bị chặn tại lớp đã thiết kế |
| Gateway tới target ngoài nhóm được phép | Bị chặn theo policy hoặc lớp mạng tương ứng |
| Truy cập qua địa chỉ phụ hoặc IPv6 | Không tạo đường ngoài phạm vi |
| Client yêu cầu hostname hoặc cổng tùy ý | Không làm gateway kết nối ngoài danh mục |
| Gateway dự phòng nhận phiên | Dùng đúng nguồn và phạm vi được cho phép |
| DNS đổi địa chỉ | Hành vi khớp thiết kế, vẫn xác minh danh tính đích |
| Tunnel hoặc forwarding ngoài phạm vi | Không được mở bằng khả năng bị cấm |
| Target thử tiếp cận tài nguyên quản trị khác | Bị giới hạn theo yêu cầu đã xác định |
| Thu hồi khi phiên còn mở | Đo được kết quả tại từng lớp |
| Rule tạm hết hạn | Không còn quyền mới, xử lý phiên cũ theo thiết kế |
| Rule bị thay đổi ngoài quy trình | Có khả năng phát hiện và xác định owner |
| Mất dependency quan trọng | Hành vi theo policy, không tự xuất hiện đường rộng |

Thử nghiệm cần dùng endpoint và tài khoản thuộc phạm vi được phép. Không quét diện rộng hoặc tạo kết nối tới tài nguyên ngoài phạm vi chỉ để hoàn thành bảng.

Một timeout không chứng minh chắc chắn firewall đã chặn đúng. Nó cũng có thể do thiếu route, dịch vụ dừng hoặc endpoint sai. Cần kết hợp trạng thái dịch vụ, nguồn thử và log ở điểm thực thi để phân biệt nguyên nhân.

## 13. Bằng chứng và xử lý sự cố

### 13.1. Hồ sơ bằng chứng tối thiểu

Với một kiểm chứng, nên lưu:

~~~text
ID yêu cầu hoặc thay đổi
Target và owner
Nguồn logic và nguồn quan sát tại điểm thực thi
Đích, giao thức và dịch vụ
Thời điểm, múi giờ và môi trường
Rule hoặc policy cùng phiên bản liên quan
Kết quả mong đợi
Kết quả quan sát và nguồn bằng chứng
Giới hạn quan sát
Người kiểm chứng và việc còn cần xử lý
~~~

Không đưa credential, token hoặc nội dung nhạy cảm không cần thiết vào hồ sơ. Khi cần liên kết nhiều nguồn log, dùng các định danh có thể đối chiếu như request ID, session ID và thông tin luồng trong phạm vi hệ thống hỗ trợ.

### 13.2. Chẩn đoán theo chặng

Khi một phiên hợp lệ không mở được, lần theo đường:

1. Client có tới đúng điểm vào không?
2. Danh tính và quyền PAM có hợp lệ không?
3. Gateway có nhận yêu cầu và chọn đúng target không?
4. DNS hoặc danh mục phân giải đúng endpoint không?
5. Luồng gateway tới target bị từ chối ở đâu?
6. Máy chủ có xác minh được không?
7. Credential và quyền tại đích có phù hợp không?
8. Kênh phụ hoặc luồng trả về có được hỗ trợ không?

Giữ nguyên bằng chứng lỗi trước khi sửa. Không reset credential chỉ vì kết nối TCP thất bại; cũng không mở firewall chỉ vì xác thực bị từ chối.

### 13.3. Khi phát hiện đường đi vòng

Cần xác định phạm vi thực tế: nguồn nào tới được đích nào, qua giao thức nào và có credential hoặc quyền sử dụng hay chưa.

Một đường mạng mở là phát hiện cần xử lý, nhưng không đủ để kết luận đã có xâm nhập. Nếu có dấu hiệu sử dụng trái phép, thực hiện quy trình ứng phó sự cố theo thẩm quyền: bảo toàn log, giới hạn đường liên quan, đánh giá phiên và credential, rồi xác minh tác động.

Sau khắc phục, kiểm tra lại cả đường đi vòng lẫn đường hợp lệ. Chặn thành công đường trực tiếp nhưng làm mất toàn bộ truy cập phục hồi cũng cần được giải quyết.

## 14. Vận hành lâu dài và phát hiện lệch cấu hình

Network path restriction có thể suy giảm khi tài nguyên thay đổi. Những thay đổi cần được đưa vào vòng đời quản trị gồm:

- Thêm target, interface, endpoint hoặc giao thức.
- Mở rộng nhóm gateway hay membership của nhóm tài nguyên.
- Thay nguồn NAT, routing, peering hoặc VPN.
- Thay DNS và mô hình địa chỉ.
- Thêm công cụ automation hoặc đường hỗ trợ nhà cung cấp.
- Tạo ngoại lệ khẩn cấp.
- Thay cách proxy, ghi nhận phiên hoặc xác thực tới đích.

Cần owner cho rule và ngoại lệ, đồng thời kiểm tra khi có sự kiện thay đổi. Rà soát định kỳ giúp tìm tồn đọng, nhưng không thay việc cập nhật kiểm soát khi triển khai mới.

Các chỉ số có ích gồm tỷ lệ target có đường quản trị được kiểm kê, số đường trực tiếp ngoài phạm vi, số ngoại lệ quá hạn và số rule tạm chưa được dọn. Mẫu số phải rõ: tỷ lệ trong nhóm target đã tích hợp PAM không đại diện cho toàn bộ hạ tầng nếu còn tài nguyên chưa kiểm kê.

Quyền sửa firewall, gateway, danh mục target và nhóm tài nguyên đều có thể thay đổi ranh giới quản trị. Chính các quyền đó cũng cần least privilege, quy trách nhiệm và bằng chứng phù hợp.

## 15. Sai lầm thường gặp

| Sai lầm | Hệ quả | Hướng xử lý |
|---|---|---|
| Cho gateway tới mọi subnet và mọi cổng | Gateway có phạm vi tiếp cận quá rộng | Thu hẹp theo target, dịch vụ và mục đích |
| Có VPN là coi mọi phiên qua PAM | Còn đường quản trị trực tiếp | Giới hạn từ mạng người dùng tới target |
| Chỉ bảo vệ một giao thức | Web, API hoặc console có thể đi vòng | Kiểm kê đầy đủ endpoint quản trị |
| Rule dựa trên IP trước NAT | Mở sai nguồn hoặc chặn nguồn hợp lệ | Xác minh nguồn ở từng điểm thực thi |
| Chỉ kiểm tra node gateway chính | Failover mất truy cập hoặc phải mở rộng khẩn cấp | Kiểm thử cụm và nguồn dự phòng |
| Tin mọi workload cùng subnet với gateway | Mở quyền cho nguồn ngoài dự kiến | Tách nguồn hoặc bổ sung ràng buộc phù hợp |
| FQDN được coi là xác minh máy chủ | Có thể kết nối tới endpoint không mong muốn | Kiểm soát phân giải và xác minh đích |
| Chặn SSH forwarding là coi hết đường trung chuyển | Chương trình ở target vẫn có thể tạo kết nối | Kết hợp quyền tại đích và egress |
| Xóa rule là coi phiên cũ đã dừng | Kết nối hoặc tác vụ có thể còn tồn tại | Kiểm chứng state và xử lý phiên |
| Một timeout được coi là bằng chứng từ chối | Không rõ nguyên nhân thật | Đối chiếu log và trạng thái các chặng |
| Break-glass luôn mở rộng | Đường khẩn cấp thành đường đi vòng | Giới hạn, theo dõi và xử lý sau sử dụng |
| Có firewall log là coi đã có audit hoạt động | Không biết thao tác bên trong phiên | Liên kết bằng chứng mạng, PAM và target |

## 16. Bài tập áp dụng

Một doanh nghiệp cho nhà cung cấp VPN tới toàn bộ mạng quản trị. PAM ghi nhận các phiên SSH qua gateway, nhưng target vẫn nhận SSH trực tiếp từ dải VPN. Gateway chính và gateway dự phòng dùng hai đường NAT khác nhau. Thiết bị còn có web quản trị trên một interface phụ. Khi hết hạn hỗ trợ, đội vận hành xóa một rule tạm rồi báo đã thu hồi toàn bộ truy cập.

Hãy lập phương án trả lời các câu hỏi:

1. Những đường quản trị nào đã được kiểm kê và đường nào còn thiếu?
2. Target nhìn thấy nguồn nào trong từng luồng qua gateway?
3. Rule nào cần giới hạn để buộc đường SSH thông thường đi qua PAM?
4. Web quản trị trên interface phụ cần được xử lý thế nào?
5. Failover có thay đổi nguồn và phạm vi được phép không?
6. Xóa rule tạm đã và chưa chứng minh điều gì đối với phiên đang mở?
7. Cần liên kết những bằng chứng nào để xác nhận thu hồi theo phạm vi?
8. Ai chịu trách nhiệm đóng ngoại lệ và cập nhật khi endpoint thay đổi?

Một hướng phân tích hợp lý là bắt đầu từ ma trận nguồn–đích–dịch vụ, xác minh luồng thực tế qua NAT, rồi xác định lớp thực thi cho từng đường. Sau đó kết hợp giới hạn mạng với danh tính riêng, quyền tại đích, vòng đời credential và kết thúc phiên.

Kết quả đạt yêu cầu khi chỉ rõ đường được phép, đường bị chặn, cơ chế thực thi, bằng chứng và phần chưa kiểm chứng. Chỉ cấu hình một rule hoặc quan sát một phiên đi qua gateway chưa đủ để kết luận mọi truy cập quản trị đã nằm trong phạm vi PAM.
