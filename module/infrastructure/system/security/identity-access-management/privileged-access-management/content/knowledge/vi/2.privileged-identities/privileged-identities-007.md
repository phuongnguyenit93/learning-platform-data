# Network administrator identity

## 1. Danh tính quản trị mạng là gì?

**Network administrator identity** là danh tính được trao khả năng quản trị các thành phần mạng hoặc cơ chế điều khiển mạng. Thành phần đó có thể là router, switch, firewall, thiết bị VPN, bộ cân bằng tải, hệ thống quản lý mạng, controller, hoặc các tài nguyên mạng ảo trong nền tảng cloud.

Danh tính này có thể thuộc về một người quản trị, một chuyên gia hỗ trợ bên ngoài hoặc một công cụ tự động hóa. Trong PAM — Privileged Access Management, cần biết chủ thể thực sự là ai hoặc là workload nào, được thực hiện hành động gì, trên phạm vi nào và trong khoảng thời gian nào.

Đặc quyền quản trị mạng không chỉ là đăng nhập được vào thiết bị. Một danh tính có thể rất nhạy cảm nếu nó được phép:

- Thay đổi định tuyến, chính sách firewall hoặc phân đoạn mạng.
- Cấp quyền truy cập VPN hoặc sửa điều kiện truy cập quản trị.
- Thay đổi cấu hình xác thực, cấp quyền và ghi nhận hoạt động quản trị.
- Sửa cấu hình controller để áp dụng xuống nhiều thiết bị.
- Lấy bản cấu hình có chứa thông tin nhạy cảm hoặc truy cập cơ chế bắt gói.
- Tắt log, thay đích gửi log, khởi động lại thiết bị hoặc xóa cấu hình.
- Tạo tài khoản, cấp token hoặc thay đổi role quản trị của người khác.

Một tài khoản không mang tên `admin` vẫn có thể có các khả năng này. Ngược lại, hai tài khoản cùng tên trên hai miền mạng có thể có phạm vi ảnh hưởng hoàn toàn khác nhau. Cần đánh giá **quyền hiệu lực và đường tác động thực tế**, không suy từ tên tài khoản.

### Danh tính không phải là địa chỉ mạng

Địa chỉ IP, tên thiết bị hoặc việc một kết nối đến từ mạng quản trị cung cấp ngữ cảnh truy cập, nhưng không tự xác định người sử dụng. Nhiều người có thể đi qua cùng một máy trung gian hoặc cùng một địa chỉ NAT.

Một bản ghi chỉ có “đăng nhập từ máy quản trị” chưa đủ để liên kết thao tác với cá nhân. Chuỗi cần theo dõi là:

```text
Người hoặc workload
    -> Danh tính đã xác thực
    -> Role và phạm vi được cấp
    -> Phiên CLI / web / API / console
    -> Thiết bị, controller hoặc tài nguyên mạng bị tác động
    -> Thay đổi và kết quả thực tế
```

## 2. Vì sao đây là một danh tính đặc quyền nhạy cảm?

Mạng kết nối ứng dụng, dữ liệu, hệ thống nhận dạng và công cụ vận hành. Vì vậy, một thay đổi mạng có thể ảnh hưởng đồng thời đến nhiều hệ thống dù người quản trị không có tài khoản quản trị trên các máy chủ đó.

| Khả năng quản trị | Ảnh hưởng có thể xảy ra nếu bị lạm dụng hoặc thao tác sai |
|---|---|
| Sửa chính sách firewall hoặc nhóm quy tắc mạng | Mở đường truy cập ngoài dự kiến, chặn dịch vụ hoặc làm mất ranh giới giữa các vùng |
| Thay đổi định tuyến | Làm gián đoạn kết nối hoặc chuyển lưu lượng qua đường không được dự kiến |
| Sửa VLAN, VRF hoặc cơ chế phân đoạn tương ứng | Thay đổi phạm vi kết nối và các ranh giới tin cậy |
| Quản trị VPN hoặc truy cập từ xa | Mở rộng khả năng tiếp cận hệ thống nội bộ hoặc khóa người dùng hợp lệ |
| Cấu hình bắt gói hoặc sao chép lưu lượng | Làm lộ nội dung hoặc siêu dữ liệu trong phạm vi mà cơ chế quan sát cho phép |
| Quản trị controller hoặc hệ thống quản lý tập trung | Phân phối thay đổi đến nhiều thiết bị và khu vực |
| Sửa AAA, tài khoản cục bộ hoặc chính sách quản trị | Tự mở rộng quyền, duy trì đường truy cập hoặc làm suy yếu truy vết |
| Quản trị log và bản sao cấu hình | Làm mất bằng chứng, lộ thông tin nhạy cảm hoặc cản trở khôi phục |

Thay đổi định tuyến không tự động làm mất hiệu lực mọi cơ chế mã hóa đầu cuối. Khả năng đọc hoặc can thiệp nội dung còn phụ thuộc giao thức, kiểm tra danh tính đầu cuối và các kiểm soát khác. Tuy nhiên, thay đổi đường đi vẫn có thể gây ảnh hưởng lớn đến tính sẵn sàng và ranh giới truy cập.

**Blast radius** là phạm vi thiệt hại có thể phát sinh từ một điểm bị chiếm dụng. Đối với danh tính quản trị mạng, phạm vi đó có thể là một thiết bị, một cơ sở, một vùng mạng hoặc toàn bộ hạ tầng do controller quản lý. Tài khoản quản trị controller đôi khi có phạm vi lớn hơn nhiều tài khoản quản trị thiết bị riêng lẻ.

## 3. Hiểu các mặt phẳng mạng và vai trò của AAA

### 3.1. Mặt phẳng quản trị, điều khiển và dữ liệu

Một cách nhìn khái niệm thường dùng là:

| Mặt phẳng | Chức năng | Liên quan đến danh tính quản trị |
|---|---|---|
| Management plane — mặt phẳng quản trị | Cấu hình, giám sát và vận hành thiết bị hoặc nền tảng | Nơi tiếp nhận các phiên và yêu cầu quản trị như CLI, web, API |
| Control plane — mặt phẳng điều khiển | Duy trì trạng thái và quyết định điều khiển hoạt động mạng | Người có quyền cấu hình có thể thay đổi hành vi điều khiển, chẳng hạn chính sách định tuyến |
| Data plane — mặt phẳng dữ liệu | Chuyển tiếp, lọc hoặc xử lý lưu lượng theo trạng thái và chính sách | Thay đổi quản trị có thể tác động đến lưu lượng nghiệp vụ |

Ranh giới triển khai cụ thể phụ thuộc kiến trúc. Việc phân loại này giúp thấy rằng một phiên đi vào management plane có thể tạo thay đổi trên cả control plane và data plane.

Đặt giao diện quản trị trong một vùng riêng giúp giảm khả năng tiếp cận, nhưng không thay thế việc xác thực và cấp quyền. Người đã vào được vùng quản trị cũng không nên mặc nhiên được toàn quyền trên mọi thiết bị.

### 3.2. AAA: xác thực, cấp quyền và ghi nhận hoạt động

**AAA** gồm ba chức năng:

- **Authentication — xác thực:** principal nào đang truy cập và có đáp ứng điều kiện xác thực không?
- **Authorization — cấp quyền:** principal đó được thực hiện tác vụ nào trên thiết bị hoặc nền tảng nào?
- **Accounting — ghi nhận hoạt động:** những sự kiện truy cập, sử dụng quyền và thao tác nào được lưu lại?

Các cơ chế như TACACS+ hoặc RADIUS có thể tham gia hệ thống AAA tùy nền tảng và cách tích hợp. Mức hỗ trợ phân quyền lệnh, ghi nhận thao tác, quản lý phiên và các đường giao diện không giống nhau giữa mọi thiết bị. Không nên suy rằng bật một giao thức AAA là đã có đầy đủ kiểm soát cho cả CLI, web và API.

AAA tập trung giúp quản lý danh tính và policy nhất quán hơn. PAM có thể bổ sung kiểm soát yêu cầu truy cập, quản lý credential, môi giới phiên và bằng chứng. Hai thành phần cần được thiết kế cùng với quyền tại thiết bị hoặc controller, thay vì coi việc đăng nhập qua PAM là thay thế mọi cơ chế cấp quyền ở đích.

### 3.3. Tài khoản cục bộ và hành vi dự phòng

Nhiều thiết bị có tài khoản cục bộ hoặc cơ chế truy cập dự phòng khi hệ thống AAA không sẵn sàng. Cần biết rõ:

- Trong điều kiện nào thiết bị chuyển sang phương thức xác thực dự phòng?
- Tài khoản cục bộ có thể dùng qua những giao diện nào?
- Quyền tại đích được xác định như thế nào khi hệ thống trung tâm không hoạt động?
- Sự kiện có được giữ cục bộ và thu thập lại sau khi kết nối phục hồi không?
- Có cách nào lợi dụng lỗi kết nối để đi vào một đường dự phòng yếu hơn không?

Không nên vô hiệu hóa tùy tiện mọi đường dự phòng khi chưa có phương án khôi phục. Đồng thời, một tài khoản cục bộ toàn quyền dùng thường xuyên, dùng chung mật khẩu và ít được quan sát có thể làm mất tác dụng của luồng kiểm soát trung tâm.

## 4. Những loại danh tính phải có trong kiểm kê

| Loại danh tính hoặc cơ chế truy cập | Ví dụ mục đích | Cách liên kết trách nhiệm |
|---|---|---|
| Tài khoản cá nhân quản trị mạng | Một kỹ sư quản lý thiết bị trong khu vực được giao | Liên kết với người cụ thể, vai trò công việc và phạm vi quyền |
| Role quản trị trên controller | Quản lý chính sách của một vùng hoặc nhiều thiết bị | Liên kết với người hoặc workload nhận role và phạm vi tài nguyên do controller điều khiển |
| Tài khoản cục bộ tại thiết bị | Khôi phục hoặc hỗ trợ giới hạn khi AAA lỗi | Ghi nhận người được phép dùng, credential được quản lý và điều kiện kích hoạt |
| Danh tính nhà cung cấp | Hỗ trợ thiết bị hoặc xử lý lỗi theo thời hạn | Liên kết với cá nhân bên ngoài, nhiệm vụ, người chịu trách nhiệm và hạn kết thúc |
| Danh tính tự động hóa mạng | Sao lưu cấu hình, triển khai policy hoặc kiểm tra tuân thủ | Liên kết với workload, chủ sở hữu dịch vụ và lần thực thi |
| Danh tính quản trị truy cập ngoài băng | Quản lý console server hoặc nền tảng khôi phục | Liên kết với người, quyền trên từng cổng hoặc từng nhóm thiết bị |
| Credential hoặc token cho API quản trị | Gọi API thiết bị hoặc nền tảng quản lý mạng | Xác định dùng cho con người hay workload, phạm vi và vòng đời |

Danh tính của chính thiết bị dùng để giao tiếp với dịch vụ khác không mặc nhiên là danh tính quản trị của con người. Tuy nhiên, credential đó vẫn cần được xem xét nếu bị lộ có thể tạo đường đặc quyền. Cần phân biệt chủ thể sử dụng và khả năng thực tế của từng credential.

### Đường quản trị không chỉ có SSH

Phạm vi kiểm kê cần xét các đường đang tồn tại, chẳng hạn:

- CLI qua SSH hoặc giao diện tương ứng được nền tảng hỗ trợ.
- Giao diện quản trị web.
- API trên thiết bị, controller hoặc nền tảng cloud.
- Console trực tiếp, console server và đường quản trị ngoài băng.
- Công cụ quản lý mạng hoặc nền tảng tự động hóa có quyền cấu hình.
- Cơ chế giám sát có khả năng ghi hoặc thay đổi cấu hình, nếu được bật.
- Tài khoản và credential khôi phục hoặc hỗ trợ.

Nếu chỉ đưa SSH qua PAM nhưng vẫn cho phép API token toàn quyền từ nhiều nơi, đặc quyền vẫn có đường đi ngoài phạm vi giám sát dự kiến.

## 5. Xác định quyền theo tác vụ và phạm vi mạng

### 5.1. Không đồng nhất mọi công việc với toàn quyền

Một kỹ sư kiểm tra trạng thái cổng không nhất thiết cần quyền thay đổi routing hoặc tạo tài khoản quản trị. Một tác vụ sao lưu cấu hình không vì thế cần quyền xóa cấu hình hoặc sửa hệ thống AAA.

Ma trận dưới đây là ví dụ phân rã nhu cầu, không phải bộ role có sẵn trên mọi thiết bị:

| Nhiệm vụ | Phạm vi nên mô tả | Quyền hoặc khả năng cần xem xét |
|---|---|---|
| Theo dõi tình trạng | Nhóm thiết bị hoặc vùng phụ trách | Xem trạng thái phù hợp, không tự động cho đọc toàn bộ thông tin nhạy cảm |
| Chẩn đoán kết nối | Thiết bị, mạng và khoảng thời gian của sự cố | Những thao tác chẩn đoán được cho phép; giới hạn bắt gói và dữ liệu thu thập |
| Sửa chính sách truy cập | Tập quy tắc, đối tượng mạng và môi trường liên quan | Thay đổi đúng phần được giao, kiểm tra ảnh hưởng và ghi nhận thay đổi |
| Bảo trì thiết bị | Thiết bị và cửa sổ bảo trì | Nạp cấu hình, khởi động lại hoặc thay đổi phần mềm theo nhiệm vụ |
| Quản trị AAA | Chính sách, nhóm danh tính và phạm vi quản trị | Khả năng tạo, gán và thu hồi quyền; cần kiểm soát vì có thể tác động nhiều quản trị viên |
| Sao lưu cấu hình | Thiết bị nguồn và nơi lưu bản sao | Quyền đọc cần thiết, bảo vệ nội dung và hạn chế quyền phá hủy bản sao |
| Truy cập khẩn cấp | Tài nguyên và kịch bản khôi phục đã xác định | Đủ quyền xử lý tình huống, có điều kiện sử dụng và xử lý sau truy cập |

### 5.2. Quyền chỉ đọc vẫn có thể nhạy cảm

Cấu hình mạng có thể chứa thông tin về topology, địa chỉ, quan hệ tin cậy hoặc thông tin xác thực ở những dạng khác nhau. Tùy thiết bị và cách lưu trữ, một số giá trị bí mật có thể được che, mã hóa hoặc không cho xuất. Không nên mặc định rằng mọi bản cấu hình đều an toàn để chia sẻ.

Một quyền xem cấu hình, tải bản sao hoặc bắt gói có thể tạo ảnh hưởng về bảo mật dữ liệu dù không cho sửa thiết bị. Cần xác định đúng dữ liệu được thấy, nơi lưu kết quả và ai có thể truy cập lại.

### 5.3. Quyền gián tiếp và sự tập trung trên controller

Người được sửa template áp dụng cho hàng trăm thiết bị có thể gây ảnh hưởng lớn dù không đăng nhập trực tiếp từng thiết bị. Người sửa kho mã tự động hóa hoặc thay credential của công cụ triển khai cũng có thể điều khiển thay đổi mạng gián tiếp.

Khi đánh giá một role, hãy kiểm tra khả năng:

- Áp dụng policy đến nhóm thiết bị ngoài nhiệm vụ.
- Thay phạm vi quản lý hoặc thêm tài nguyên vào nhóm được điều khiển.
- Sửa template, script hoặc quy trình chạy với quyền cao.
- Lấy credential quản trị thiết bị từ nền tảng.
- Tạo token, gán role hoặc sửa policy cấp quyền.
- Tắt kiểm soát và xóa bằng chứng.

Một danh tính trên controller phải được đánh giá theo toàn bộ tập tài nguyên mà nó thực sự điều khiển được, không chỉ theo một máy chủ đang chạy controller.

## 6. Áp dụng PAM cho quản trị mạng

### 6.1. Liên kết với cá nhân và tách ngữ cảnh quản trị

Người quản trị nên có danh tính cá nhân để yêu cầu và sử dụng đặc quyền. Việc tách công việc hằng ngày khỏi ngữ cảnh quản trị có thể được thực hiện bằng tài khoản quản trị riêng, role tạm thời hoặc kết hợp các cơ chế phù hợp với nền tảng.

Điểm cần đạt là không dùng đặc quyền rộng cho những hoạt động không cần thiết, đồng thời vẫn liên kết được người khởi tạo với tài khoản đích và phiên. Khi bắt buộc dùng tài khoản đích chung, PAM cần giúp kiểm soát người sử dụng và hạn chế đường đăng nhập trực tiếp ngoài quy trình.

### 6.2. JIT: giới hạn cửa sổ quản trị

**JIT — just-in-time access** cấp hoặc kích hoạt đặc quyền khi có nhu cầu, trong thời hạn xác định. Ví dụ, kỹ sư chỉ nhận quyền sửa firewall của một vùng trong cửa sổ thay đổi được chấp thuận.

Cần kiểm soát cả quyền yêu cầu role, phạm vi thiết bị và khả năng gia hạn. Một tài khoản có thể tự kích hoạt mọi role vô hạn vẫn có đường đặc quyền rất rộng.

Đối với thiết bị mạng, phải hiểu khi nào thay đổi role có hiệu lực: ở lần đăng nhập tiếp theo, khi chạy thao tác mới hay thông qua cơ chế khác. Quyền hết hạn trong hệ thống trung tâm chưa chắc làm mất hiệu lực một phiên CLI, phiên web hoặc API token đang tồn tại.

### 6.3. JEA và giới hạn thao tác

**JEA — just-enough administration** là giới hạn khả năng quản trị ở đúng tác vụ cần thiết. Trên hệ thống mạng, ý tưởng này có thể được thực hiện bằng role tại controller, phân quyền trên thiết bị, endpoint tác vụ hoặc cơ chế hạn chế lệnh mà nền tảng hỗ trợ.

Không nên chỉ dựa vào một danh sách tên lệnh mà bỏ qua:

- Tham số có thể làm phạm vi thao tác rộng hơn.
- Chế độ lệnh, lệnh viết tắt hoặc cách biểu diễn tương đương.
- Khả năng gọi shell, chạy script, nạp tệp hoặc thực thi lệnh lồng nhau.
- Các giao diện khác có quyền tương đương nhưng không chịu cùng kiểm soát.
- Việc đổi cấu hình hôm nay tạo ra quyền rộng hơn cho lần truy cập sau.

Phân quyền lệnh và giới hạn tác vụ cần phù hợp với hành vi thực tế của thiết bị. Không thể mặc định một policy áp dụng được nguyên vẹn cho mọi hệ điều hành mạng.

### 6.4. Vault và vòng đời credential

Vault giúp quản lý credential đích, kiểm soát ai được dùng hoặc đọc credential và hỗ trợ luân chuyển. Khi nền tảng tích hợp cho phép, người vận hành có thể mở phiên mà không được hiển thị mật khẩu thiết bị.

Cần tránh dùng cùng một credential quản trị cho nhiều miền mạng độc lập. Nếu credential đó bị lộ, phạm vi ảnh hưởng có thể bao phủ tất cả các thiết bị dùng lại nó.

Luân chuyển phải xét các phụ thuộc như hệ thống quản lý mạng, công cụ sao lưu và tác vụ tự động hóa. Một thay đổi mật khẩu không được phối hợp có thể làm hỏng hoạt động hợp lệ. Ngược lại, việc giữ một credential dùng chung vô thời hạn để tránh gián đoạn làm tăng khả năng sử dụng lại khi credential bị lộ.

Đổi mật khẩu không tự thu hồi mọi phiên hoặc token được phát hành từ trước. Kế hoạch thu hồi cần chỉ rõ các đối tượng liên quan và cơ chế thực tế của từng hệ thống.

### 6.5. Bảo vệ đường quản trị

Một thiết kế phù hợp có thể sử dụng vùng mạng quản trị, máy trung gian, điều kiện thiết bị và giới hạn nguồn kết nối để giảm số nơi có thể tiếp cận giao diện quản trị. Các kiểm soát này cần đi cùng xác thực và quyền tại đích.

Cần xem cả đường ngoài băng và console server. Đây có thể là đường khôi phục quan trọng, nhưng cũng là nơi có quyền rất cao. Tài khoản quản trị console server không nên trở thành cách không được giám sát để tiếp cận mọi thiết bị.

Thiết kế đường khôi phục cần tính đến sự phụ thuộc vào mạng, DNS, hệ thống nhận dạng và PAM. Một đường được gọi là ngoài băng nhưng vẫn phụ thuộc hoàn toàn vào chính thành phần đang cần khôi phục có thể không đáp ứng được tình huống dự kiến.

## 7. Kiểm kê danh tính và đặc quyền mạng

Một hồ sơ kiểm kê nên mô tả được cả danh tính lẫn tập thiết bị hoặc tài nguyên chịu tác động.

| Nhóm thông tin | Nội dung cần biết |
|---|---|
| Chủ thể | Người cụ thể hoặc workload; đơn vị, nhà cung cấp và chủ sở hữu |
| Principal | Tài khoản tại hệ thống nhận dạng, controller, thiết bị hoặc nền tảng cloud |
| Phạm vi | Thiết bị, nhóm thiết bị, vùng mạng, site, tenant và môi trường |
| Khả năng | Tác vụ, role, quyền sửa cấu hình, quyền cấp quyền và khả năng đọc dữ liệu nhạy cảm |
| Đường truy cập | CLI, web, API, công cụ tự động hóa, console hoặc đường ngoài băng |
| Cơ chế AAA | Nguồn xác thực, cách ánh xạ role và hành vi khi hệ thống trung tâm lỗi |
| Credential | Tham chiếu đối tượng được quản lý, vòng đời và phụ thuộc; không lưu giá trị bí mật |
| Thời hạn | Quyền thường trực hay tạm thời, thời điểm hết hạn, điều kiện gia hạn |
| Bằng chứng | Mã yêu cầu, phiên, sự kiện tại đích và lịch sử thay đổi |
| Khôi phục và thu hồi | Cách dừng truy cập, xử lý credential, bảo toàn log và phục hồi cấu hình |

Ví dụ bản ghi mô tả một quyền quản trị có thời hạn:

```json
{
  "subjectRef": "person-073",
  "identityType": "human",
  "principalRef": "idp:network-operator-073",
  "resourceScope": {
    "site": "branch-a",
    "environment": "production",
    "deviceGroup": "branch-a-access-switches"
  },
  "allowedTasks": [
    "read-approved-port-status",
    "apply-approved-port-configuration"
  ],
  "excludedCapabilities": [
    "manage-administrator-identities",
    "change-aaa-policy",
    "export-sensitive-configuration"
  ],
  "grantMode": "time-bound",
  "requestRef": "network-change-317",
  "credentialRef": "managed-reference-only"
}
```

Đây là dữ liệu minh họa cho việc kiểm kê và diễn đạt yêu cầu, không phải policy thực thi hay schema của một sản phẩm. Những khả năng bị loại trừ chỉ thực sự bị chặn khi được ánh xạ và thực thi bằng cơ chế tương ứng trên toàn bộ đường truy cập có liên quan.

Không đưa mật khẩu thiết bị, khóa VPN, token API hoặc bản cấu hình chứa secret vào hồ sơ này. Nếu cần tham chiếu, dùng định danh của đối tượng được quản lý và kiểm soát quyền truy cập riêng.

## 8. Luồng thay đổi mạng có kiểm soát đặc quyền

Quản lý danh tính và quản lý thay đổi liên quan chặt chẽ nhưng không thay thế nhau. Một thay đổi được phê duyệt vẫn có thể được thực hiện bằng role quá rộng; một role được cấp đúng vẫn có thể bị dùng cho thay đổi sai.

Một luồng tham khảo:

1. **Xác định nhiệm vụ và ảnh hưởng:** mô tả thiết bị, đường kết nối, dịch vụ phụ thuộc, thao tác dự kiến và giới hạn công việc.
2. **Chuẩn bị phương án phục hồi:** giữ bản cấu hình phù hợp, xác định đường khôi phục và khả năng tiếp cận khi kết nối quản trị bị mất.
3. **Cấp quyền phù hợp:** gắn yêu cầu với cá nhân hoặc workload, phạm vi role, điều kiện xác thực và thời hạn.
4. **Thực hiện qua đường được kiểm soát:** mở phiên hoặc dùng công cụ triển khai đã được xác định, ghi lại sự kiện liên quan.
5. **Xác nhận trạng thái thực tế:** kiểm tra thay đổi có áp dụng đúng phạm vi và kết nối nghiệp vụ còn đáp ứng yêu cầu.
6. **Kết thúc đặc quyền:** xử lý quyền, phiên và credential theo cơ chế đã xác định; liên kết kết quả với yêu cầu ban đầu.

Một số nền tảng hỗ trợ kiểm tra cấu hình, giao dịch thay đổi hoặc cơ chế tự hoàn tác nếu không xác nhận. Đây là những khả năng hữu ích khi có sẵn, nhưng không được giả định tồn tại trên mọi thiết bị.

Không nên coi việc chạy lệnh thành công là đủ. Thay đổi có thể chưa được lưu theo cơ chế của thiết bị, bị controller ghi đè hoặc gây ảnh hưởng trên đường lưu lượng chưa được quan sát. Bằng chứng cần phân biệt điều đã yêu cầu, điều đã thực hiện và trạng thái cuối cùng.

## 9. Ghi nhận phiên và bằng chứng điều tra

Để trả lời “ai đã thay đổi mạng và thay đổi gì”, cần liên kết nhiều nguồn bằng chứng.

| Nguồn | Thông tin có thể cung cấp | Giới hạn cần biết |
|---|---|---|
| Hệ thống nhận dạng và AAA | Xác thực, ánh xạ quyền, một số sự kiện sử dụng đặc quyền | Nội dung ghi nhận phụ thuộc tính năng và cấu hình |
| PAM | Yêu cầu, credential được sử dụng, phiên và thao tác được bao phủ | Không tự quan sát đường truy cập đi vòng |
| Thiết bị mạng | Sự kiện đăng nhập, cấu hình, lệnh hoặc thay đổi trạng thái theo hỗ trợ | Nhật ký cục bộ có thể mất hoặc bị thay đổi nếu không được bảo vệ |
| Controller hoặc hệ thống quản lý mạng | Người gọi API, tác vụ triển khai, nhóm tài nguyên và phiên bản cấu hình | Cần liên kết tác vụ tập trung với kết quả trên từng thiết bị |
| Kho lịch sử cấu hình | Khác biệt giữa các phiên bản và khả năng phục hồi | Chênh lệch cấu hình không tự xác định được người khởi tạo |
| Hệ thống giám sát | Thời điểm gián đoạn, thay đổi kết nối và ảnh hưởng dịch vụ | Không thay thế bằng chứng cấp quyền và thao tác |

Mã liên kết, định danh tài nguyên và thời gian nhất quán giúp đối chiếu nguồn log. Đồng bộ thời gian và bảo vệ nơi lưu bằng chứng cần được xem là một phần của thiết kế truy vết.

Ghi hình một phiên CLI không bảo đảm bao phủ API, giao diện web hoặc tác vụ chạy qua controller. Ngay cả trong CLI, khả năng ghi lại lệnh không đồng nghĩa đã biết toàn bộ tác động cuối cùng.

Bản ghi phiên và chênh lệch cấu hình có thể chứa thông tin nhạy cảm. Cần giới hạn người xem, tránh ghi credential khi cơ chế cho phép và bảo vệ dữ liệu bằng chứng. Người thực hiện thay đổi mạng không nên mặc nhiên có khả năng sửa hoặc xóa toàn bộ bằng chứng trung tâm.

## 10. Ví dụ: cấp quyền cho kỹ sư sửa cấu hình tại một chi nhánh

Minh cần điều chỉnh cấu hình cổng mạng của một nhóm switch tại chi nhánh A theo yêu cầu thay đổi đã xác định. Minh không có nhiệm vụ sửa firewall trung tâm, thay routing toàn hệ thống hay quản lý tài khoản quản trị.

### Thiết kế ban đầu dễ phát sinh rủi ro

Nhóm dùng chung một tài khoản toàn quyền cho nhiều chi nhánh. Mật khẩu được lưu trong tài liệu nội bộ. Minh có thể đăng nhập trực tiếp bằng SSH, dùng giao diện web và lấy bản cấu hình. Nhật ký tại đích chỉ ghi tên tài khoản chung.

Nếu credential bị lộ hoặc Minh thao tác nhầm, phạm vi ảnh hưởng có thể vượt khỏi chi nhánh A. Việc xác định người thực hiện từng thay đổi cũng khó hơn vì nhiều người biết cùng mật khẩu.

### Thiết kế gắn với danh tính và tác vụ

| Thành phần | Thiết kế minh họa |
|---|---|
| Chủ thể | Minh xác thực bằng danh tính cá nhân |
| Phạm vi | Chỉ nhóm switch được giao tại chi nhánh A |
| Thao tác | Xem trạng thái cần thiết và thực hiện thay đổi cổng đã được chấp thuận |
| Quyền ngoài nhiệm vụ | Không cấp khả năng sửa AAA, tạo quản trị viên, đổi routing hoặc truy cập thiết bị chi nhánh khác |
| Thời gian | Cửa sổ quyền bám theo đợt thay đổi; cơ chế kết thúc phiên được xác định |
| Đường truy cập | Qua đường quản trị được kiểm soát; hạn chế giao diện thay thế ngoài phạm vi cấp quyền |
| Credential | Do cơ chế quản lý phù hợp cung cấp; tránh chia sẻ mật khẩu quản trị chung |
| Bằng chứng | Liên kết yêu cầu, danh tính Minh, phiên, thay đổi cấu hình và kết quả trên thiết bị |
| Khôi phục | Có bản cấu hình và đường phục hồi phù hợp nếu thay đổi làm mất kết nối |

Các quyền cụ thể chỉ có thể tách như trên nếu thiết bị hoặc nền tảng cung cấp cơ chế đủ phù hợp. Nếu không thể hạn chế ở mức tác vụ, cần ghi nhận quyền còn rộng, áp dụng biện pháp bù đắp khả thi và không tuyên bố đã đạt giới hạn chưa thực thi được.

### Khi kết nối tới AAA bị mất giữa phiên

Cần phân biệt phiên đang hoạt động với yêu cầu đăng nhập mới. Phiên có thể tiếp tục hoặc bị ảnh hưởng tùy cơ chế của thiết bị. Lần đăng nhập mới có thể dùng đường dự phòng nếu được cấu hình.

Điều cần có từ trước là hiểu rõ hành vi đó, bảo vệ tài khoản dự phòng và biết cách khôi phục. Không nên chỉ phát hiện trong sự cố rằng mọi người đều biết một mật khẩu cục bộ dùng chung cho toàn bộ thiết bị.

### Nếu thay đổi làm mất đường quản trị

Thu hồi quyền hoặc đóng phiên không tự hoàn tác cấu hình đã áp dụng. Đội vận hành phải sử dụng cơ chế rollback hoặc đường khôi phục phù hợp. Đây là lý do quyền, phiên, thay đổi cấu hình và khả năng phục hồi cần được xem cùng nhau.

## 11. Thu hồi và ứng phó khi danh tính quản trị mạng bị chiếm dụng

Khi nghi có sự cố, trước hết cần xác định principal, đường truy cập và tập tài nguyên có thể bị tác động. Phạm vi không chỉ gồm thiết bị đã đăng nhập mà còn có controller, công cụ triển khai, token và credential mà danh tính đó có thể sử dụng.

Những đối tượng cần xem xét gồm:

- Tài khoản cá nhân và khả năng yêu cầu hoặc kích hoạt role quản trị.
- Phiên CLI, web, API và console còn hoạt động.
- Token, khóa và credential đã cấp hoặc có thể đã bị đọc.
- Tài khoản cục bộ, role, khóa truy cập hoặc policy mới được tạo.
- Thay đổi AAA, logging, routing, firewall hoặc cơ chế điều khiển tập trung.
- Bản cấu hình và các tài nguyên chứa credential hoặc thông tin nhạy cảm.
- Công cụ tự động hóa có thể tiếp tục áp dụng thay đổi sau khi người dùng đã bị khóa.

Khóa tài khoản trung tâm có thể ngăn một số đăng nhập mới nhưng chưa chắc dừng mọi truy cập đang tồn tại. Luân chuyển credential cũng chưa chắc chấm dứt token hoặc phiên cũ. Cần xác định hành vi thực tế, phối hợp thao tác thu hồi và theo dõi kết quả tại đích.

Kế hoạch ứng cứu cần tránh tự làm mất đường khôi phục duy nhất. Thứ tự thao tác phải cân nhắc mức nguy hiểm, khả năng giữ quyền kiểm soát và các phụ thuộc đang hoạt động.

Sau khoanh vùng, cần đối chiếu cấu hình với trạng thái tin cậy, tìm đường duy trì truy cập và xác nhận khả năng quan sát đã phục hồi. Chỉ chấm dứt phiên nghi vấn mà không kiểm tra các thay đổi đã thực hiện sẽ bỏ sót hậu quả còn tồn tại.

## 12. Kiểm chứng thiết kế và những lỗi thường gặp

### 12.1. Các câu hỏi kiểm chứng

Trong môi trường hoặc đợt diễn tập có phạm vi được cho phép, có thể kiểm tra:

| Câu hỏi | Kết quả mong đợi |
|---|---|
| Người vận hành có làm được tác vụ đúng trên nhóm thiết bị được giao không? | Tác vụ hợp lệ được thực hiện và có bằng chứng liên kết |
| Cùng danh tính đó có sang thiết bị hoặc vùng khác được không? | Truy cập ngoài phạm vi bị từ chối theo policy |
| CLI bị hạn chế nhưng API hoặc web có cho làm việc tương đương không? | Các đường liên quan không mở quyền vượt ngoài mục tiêu |
| Quyền hết hạn hoặc bị thu hồi khi còn phiên hoạt động thì sao? | Hành vi khớp với mục tiêu đã công bố cho từng loại phiên và token |
| Khi AAA hoặc PAM không sẵn sàng, ai có thể dùng đường dự phòng? | Có đường khôi phục được quản lý, không mở truy cập vô điều kiện |
| Có thể liên kết một thay đổi trên thiết bị với cá nhân hoặc workload không? | Bằng chứng đủ nối yêu cầu, danh tính, phiên và kết quả tại đích |
| Người sửa cấu hình có thể xóa cả log trung tâm và bản sao phục hồi không? | Không vượt qua ranh giới quản trị đã thiết kế |

Đây là gợi ý kiểm chứng cho người học, không phải tuyên bố đã thực hiện kiểm thử trên một hệ thống thực tế.

### 12.2. Những lỗi cần tránh

| Cách hiểu hoặc cách làm | Vì sao chưa đủ |
|---|---|
| Chỉ tìm tài khoản có tên `admin` | Bỏ sót role trên controller, quyền gián tiếp và token API |
| Cho mọi quản trị viên toàn quyền mọi chi nhánh | Một danh tính bị chiếm dụng có phạm vi ảnh hưởng quá rộng |
| Dùng IP nguồn để xác định người thao tác | Máy trung gian hoặc NAT có thể được nhiều người sử dụng |
| Có AAA tập trung là không cần kiểm tra tài khoản cục bộ | Đường dự phòng và console vẫn có thể tồn tại ngoài kiểm soát dự kiến |
| Chỉ đưa SSH vào PAM | Web, API, controller và tự động hóa có thể là đường đặc quyền khác |
| Coi quyền xem cấu hình là không nhạy cảm | Cấu hình và dữ liệu chẩn đoán có thể chứa thông tin cần bảo vệ |
| Đổi mật khẩu là đã thu hồi xong | Phiên, token, khóa và quyền mới tạo có thể còn hiệu lực |
| Ghi hình phiên là đã ngăn thao tác nguy hiểm | Ghi nhận không thay thế giới hạn quyền và kiểm soát thay đổi |
| Đóng mọi đường dự phòng mà không có phương án khôi phục | Có thể mất khả năng xử lý khi mạng hoặc hệ thống nhận dạng lỗi |

## 13. Tình huống tự luyện

Một tổ chức có 30 chi nhánh. Kỹ sư mạng đăng nhập controller bằng tài khoản cá nhân, nhưng mọi người đều được role quản trị toàn hệ thống. Controller lưu credential toàn quyền của thiết bị. Các switch còn một tài khoản cục bộ dùng chung, có thể đăng nhập trực tiếp từ nhiều vùng. Công cụ sao lưu dùng token của một kỹ sư đã chuyển nhóm.

Hãy phân tích:

1. Những danh tính nào thuộc con người, những danh tính nào phục vụ workload và nơi nào đang dùng lẫn hai loại?
2. Danh tính nào có blast radius lớn nhất nếu bị chiếm dụng? Vì sao cần xét cả controller và credential được quản lý?
3. Chỉ thay mật khẩu tài khoản cục bộ có giải quyết được toàn bộ các đường đặc quyền không?
4. Làm sao cấp quyền cho một kỹ sư chỉ bảo trì một nhóm thiết bị tại một chi nhánh?
5. Cần giữ những bằng chứng nào để nối một yêu cầu với thay đổi cuối cùng trên switch?
6. Khi hệ thống AAA lỗi, đường dự phòng cần đáp ứng điều kiện sử dụng và khôi phục nào?
7. Token của công cụ sao lưu cần được xử lý thế nào khi người tạo không còn đảm nhiệm công việc?

Gợi ý: bắt đầu bằng việc lập quan hệ giữa người, principal, role, credential, công cụ và thiết bị. Sau đó giới hạn phạm vi role, tách danh tính tự động hóa, quản lý đường cục bộ và dự phòng, đồng thời kiểm tra khả năng thu hồi theo từng giao diện.

## 14. Ghi nhớ

Danh tính quản trị mạng có thể điều khiển cả kết nối, chính sách truy cập và đường vận hành của nhiều hệ thống. Vì vậy, quản lý danh tính này phải bao quát thiết bị riêng lẻ, controller, tự động hóa, API và các đường khôi phục.

Một thiết kế PAM phù hợp cần liên kết được người hoặc workload với quyền hiệu lực và thay đổi thực tế; giới hạn quyền theo tác vụ, tài nguyên và thời gian; bảo vệ credential; duy trì truy vết; và thu hồi có hiệu lực mà vẫn giữ được khả năng phục hồi mạng.
