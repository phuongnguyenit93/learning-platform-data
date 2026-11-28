# Remote vendor access: kiểm soát truy cập từ xa của nhà cung cấp bằng PAM

## Mục tiêu bài học

Nhà cung cấp có thể cần truy cập hệ thống để bảo trì thiết bị, khắc phục lỗi phần mềm hoặc hỗ trợ một sự cố sản xuất. Khả năng truy cập đó phải đủ để hoàn thành công việc, có thời hạn, gắn với người thực hiện và để lại bằng chứng có thể đối chiếu.

Trong phạm vi Privileged Access Management (PAM), bài học này giúp bạn:

- Phân biệt việc kết nối từ xa với việc được phép sử dụng quyền đặc biệt.
- Thiết kế đường truy cập của nhà cung cấp theo định danh cá nhân, least privilege, Just-in-Time (JIT) và Just Enough Administration (JEA).
- Kết hợp vault, phê duyệt, kiểm soát phiên, giám sát và thu hồi quyền thành một quy trình vận hành.
- Xử lý truy cập khẩn cấp, đổi kỹ thuật viên, phiên bị gián đoạn và trường hợp kết thúc hợp đồng.
- Lập hồ sơ bằng chứng để giải thích ai đã làm gì, trên tài sản nào, trong phạm vi phê duyệt nào.

Các tên tài khoản, tài sản, ticket, thời hạn và ngưỡng trong bài là dữ liệu minh họa. Chúng không phải cấu hình có thể áp dụng nguyên trạng vào một sản phẩm cụ thể.

## 1. Bài toán: bên ngoài tổ chức nhưng có thể chạm vào quyền quản trị

**Remote vendor access** là việc một người thuộc nhà cung cấp, đối tác bảo trì hoặc đơn vị hỗ trợ bên ngoài truy cập tài nguyên của tổ chức từ xa để thực hiện công việc được ủy quyền.

Một tình huống điển hình:

> Ứng dụng quản lý kho phát sinh lỗi khi xử lý đơn hàng. Kỹ thuật viên của hãng cần đọc log, kiểm tra một dịch vụ và có thể khởi động lại dịch vụ đó. Họ không cần tài khoản quản trị miền, không cần đọc toàn bộ cơ sở dữ liệu và không cần truy cập những máy chủ còn lại.

Kết nối mạng thành công chỉ chứng minh người dùng đã đi qua một cổng truy cập. Nó chưa chứng minh rằng người đó được phép đăng nhập máy chủ đích, chạy lệnh đặc quyền hoặc sao chép dữ liệu.

Một thiết kế đầy đủ phải trả lời riêng các câu hỏi:

| Câu hỏi | Kiểm soát cần có | Ví dụ |
|---|---|---|
| Người đang truy cập là ai? | Định danh cá nhân, xác thực và vòng đời tài khoản bên ngoài | Một tài khoản riêng cho từng kỹ thuật viên |
| Vì sao họ được truy cập? | Chủ sở hữu nội bộ, ticket và phê duyệt | Ticket sửa lỗi đã được service owner chấp thuận |
| Họ được chạm vào đâu? | Phân đoạn và giới hạn tài sản | Chỉ máy chủ ứng dụng được ghi trong ticket |
| Họ được làm gì? | Quyền tối thiểu và giới hạn thao tác | Đọc log, xem trạng thái, khởi động lại đúng dịch vụ |
| Quyền tồn tại đến khi nào? | JIT, thời hạn phiên và cơ chế thu hồi | Hết cửa sổ bảo trì hoặc khi ticket đóng |
| Có thể kiểm chứng và dừng được không? | Log, giám sát, chấm dứt phiên và bằng chứng | Đối chiếu phiên PAM với log trên máy đích |

VPN, MFA, vault hay ghi hình phiên đều giải quyết những phần khác nhau của bài toán. Không có một thành phần đơn lẻ nào tự bảo đảm toàn bộ chuỗi kiểm soát.

## 2. Những rủi ro đặc trưng của truy cập nhà cung cấp

### 2.1. Biết tên công ty nhưng không biết người thực hiện

Tài khoản `vendor-support` được nhiều kỹ thuật viên dùng chung khiến log chỉ phản ánh một nhãn tổ chức. Khi xảy ra sự cố, không thể xác định chắc chắn ai đã đăng nhập, ai chuyển mật khẩu cho ai hoặc người đó có còn làm việc cho nhà cung cấp hay không.

Cần phân biệt hai lớp:

- **Danh tính người yêu cầu và điều khiển phiên:** phải là cá nhân có thể quy trách nhiệm.
- **Danh tính thực thi trên hệ thống đích:** có thể là tài khoản kỹ thuật được PAM quản lý, nhưng phải có ánh xạ đáng tin cậy từ tài khoản này về người điều khiển từng phiên.

Nếu hệ thống cũ bắt buộc dùng một tài khoản cục bộ chung, PAM có thể giảm rủi ro bằng cách giữ bí mật trong vault và gắn việc sử dụng với phiên cá nhân. Nếu nhiều phiên đồng thời dùng cùng tài khoản đích mà log đích không phân biệt được phiên, khả năng quy trách nhiệm vẫn bị hạn chế. Khi đó cần hạn chế đồng thời hoặc áp dụng một cơ chế ánh xạ phù hợp hơn.

### 2.2. Một lần bảo trì trở thành quyền tồn tại lâu dài

Quyền được mở để sửa lỗi nhưng không bị đóng sau đó có thể tồn tại nhiều tháng. Một tài khoản nhà cung cấp bị chiếm dụng lúc này trở thành lối vào có sẵn.

Ngày hết hạn hợp đồng, ngày hết hạn danh tính, thời hạn được phép yêu cầu quyền và thời hạn của một phiên là các mốc khác nhau. Tất cả đều cần có người chịu trách nhiệm và cơ chế thực thi; một dòng ghi chú trong ticket không đủ để làm quyền tự hết hạn.

### 2.3. Thiết bị và tổ chức bên ngoài có mức độ tin cậy khác nhau

Tổ chức không nhất thiết quản lý được máy tính của kỹ thuật viên. Máy đó có thể thiếu bản vá, chứa công cụ không được duyệt hoặc đang bị đánh cắp phiên.

Xác thực mạnh giúp bảo vệ khâu đăng nhập nhưng không vô hiệu hóa mã độc đang điều khiển một phiên hợp lệ. Có thể cần thiết bị đáp ứng điều kiện bảo mật, máy trạm trung gian do tổ chức quản lý hoặc một phương thức hỗ trợ không giao quyền điều khiển trực tiếp.

Máy trạm trung gian cũng không loại bỏ hoàn toàn rủi ro: người ở đầu xa vẫn có thể nhìn màn hình, chụp ảnh hoặc điều khiển một phiên đã được xác thực. Vì vậy vẫn phải giới hạn dữ liệu hiển thị và quyền thực thi.

### 2.4. Phạm vi mạng và phạm vi nghiệp vụ không trùng nhau

Yêu cầu “xem log trên một máy” có thể vô tình được triển khai thành “vào cả mạng quản trị”. Từ một thiết bị được cho phép, kỹ thuật viên có thể tiếp cận tài sản khác bằng đường mạng phụ, công cụ điều khiển từ xa hoặc credential tìm thấy tại máy đích.

Cần kiểm tra cả đường đi được phê duyệt và các đường đi có thể vượt qua cơ chế đó. Giới hạn quyền trong PAM sẽ mất tác dụng nếu cùng tài khoản vẫn đăng nhập được trực tiếp qua một đường khác.

## 3. Mô hình truy cập có thể kiểm soát

Một kiến trúc tham khảo:

```text
Kỹ thuật viên được định danh
        |
        v
Cổng truy cập bên ngoài / IdP
  - xác thực mạnh
  - kiểm tra điều kiện truy cập
        |
        v
PAM access gateway / session broker
  - đối chiếu phê duyệt và thời hạn
  - giới hạn tài sản, tài khoản, thao tác
  - giám sát và chấm dứt phiên
        |
        +------ lấy hoặc cấp credential ------> Vault / cơ chế cấp quyền
        |
        v
Vùng quản trị được phân đoạn
        |
        v
Tài sản đích được phê duyệt
  - quyền thực thi tối thiểu
  - log tại máy, ứng dụng và dữ liệu

Ticket, phê duyệt, log PAM và log đích
        |
        v
Kho bằng chứng / hệ thống giám sát có phân quyền
```

Đây là sơ đồ chức năng. Một sản phẩm có thể thực hiện nhiều vai trò hoặc cần phối hợp với hệ thống khác. Việc có một session broker không mặc nhiên có nghĩa là mọi loại giao thức, kênh phụ hoặc thao tác đều đã được kiểm soát.

### 3.1. Đường mạng

Ở ranh giới mạng, chỉ mở những kết nối cần thiết từ lớp truy cập tới tài sản đích. Với hệ thống cho phép, chỉ chấp nhận kết nối quản trị từ nguồn được kiểm soát như gateway hoặc máy trạm quản trị đã duyệt.

Cần kiểm tra:

- Có thể đăng nhập trực tiếp vào tài sản bằng cùng tài khoản mà bỏ qua PAM không?
- Có công cụ hỗ trợ từ xa khác hoặc đường hầm cũ đang hoạt động không?
- Tài sản được hỗ trợ có thể kết nối sang máy chủ khác ngoài phạm vi không?
- Kỹ thuật viên có thể mở một kênh truyền tệp hoặc phiên nền không bị ghi nhận không?

Một đường hỗ trợ khẩn cấp vẫn có thể tồn tại theo thiết kế, nhưng phải có chủ sở hữu, điều kiện kích hoạt, thời hạn và bằng chứng riêng.

### 3.2. VPN, truy cập theo ứng dụng và máy trạm trung gian

Lựa chọn phụ thuộc vào giao thức, độ nhạy của dữ liệu và khả năng kiểm soát thiết bị:

| Phương án | Điểm cần đánh giá |
|---|---|
| VPN được giới hạn tuyến và đích | Sau khi kết nối, người dùng thực sự tiếp cận được những tài sản, cổng và dịch vụ nào? |
| Cổng truy cập theo ứng dụng hoặc tài nguyên | Cơ chế có kiểm tra đúng người, đúng tài nguyên và các kênh phụ cần dùng không? |
| Phiên qua máy trạm trung gian được quản lý | Công cụ, clipboard, tải tệp, dữ liệu lưu tạm và đường ra mạng được kiểm soát thế nào? |
| Chia sẻ màn hình dưới sự điều khiển của nhân sự nội bộ | Ai thực hiện thao tác cuối cùng, ai theo dõi và bằng chứng ghi nhận được đến đâu? |

Không nên chọn phương án chỉ vì nhãn công nghệ. Cần thử nghiệm các giới hạn trên đường truy cập thực tế.

## 4. Danh tính cá nhân và vòng đời nhà cung cấp

Mỗi kỹ thuật viên cần một định danh có chủ sở hữu nội bộ và ngày hết hạn. Hồ sơ nên thể hiện tối thiểu:

- Công ty và, nếu có, đơn vị thầu phụ.
- Cá nhân được phép làm việc, phương thức xác minh và kênh liên hệ đã thống nhất.
- Người bảo trợ nội bộ, hệ thống được hỗ trợ và hợp đồng hoặc phạm vi công việc liên quan.
- Ngày bắt đầu, ngày hết hạn và điều kiện rà soát lại.
- Cách xác thực, điều kiện thiết bị và cách thông báo khi nhân sự thay đổi.

Nếu dùng liên kết danh tính với IdP của nhà cung cấp, tổ chức vẫn cần chính sách tiếp nhận, ràng buộc phạm vi và cách thu hồi tại phía mình. Không nên coi mọi tài khoản từ một miền email là nhân sự đã được phê duyệt.

Nếu dùng tài khoản bên ngoài do tổ chức quản lý, phải có quy trình cấp, khôi phục xác thực, khóa và rà soát tài khoản đó. Quy trình khôi phục MFA yếu có thể làm suy yếu chính cơ chế đăng nhập mạnh.

### Đổi kỹ thuật viên giữa ca

Không chuyển giao một phiên đang đăng nhập hoặc chia sẻ yếu tố xác thực cho người thay ca. Người mới phải có định danh được duyệt và mở phiên riêng. Ticket có thể giữ nguyên nếu chính sách cho phép, nhưng cần kiểm tra lại người tham gia, cửa sổ truy cập và phạm vi thao tác.

Khi kỹ thuật viên rời nhà cung cấp, tổ chức phải có cách khóa quyền mà không chờ hết một phiên bảo trì đã đặt lịch trước đó.

## 5. Cấp quyền theo công việc: JIT và JEA

**JIT** giới hạn thời gian tồn tại của quyền. **JEA** giới hạn những việc quyền đó cho phép thực hiện. Hai cơ chế bổ sung cho nhau: quyền quản trị toàn hệ thống trong 15 phút vẫn có thể quá rộng; quyền rất hẹp nhưng tồn tại vô thời hạn vẫn tạo rủi ro tích lũy.

Ví dụ, ticket `CHG-4821` yêu cầu kiểm tra dịch vụ `warehouse-api` trên `app-maint-01`. Một hồ sơ yêu cầu minh họa:

```yaml
request_id: CHG-4821
vendor_person: external-tech-17
internal_sponsor: warehouse-service-owner
target_asset: app-maint-01
purpose: Kiem tra loi xu ly don hang
allowed_actions:
  - read_service_logs
  - inspect_service_health
  - restart_warehouse_api
excluded_actions:
  - unrestricted_shell
  - export_customer_database
  - create_persistent_account
access_window:
  starts_at: "2026-12-02T20:00:00+07:00"
  ends_at: "2026-12-02T21:00:00+07:00"
approval_required_before_activation: true
transfer_policy: reviewed_files_only
expiry_behavior:
  block_new_sessions: true
  terminate_existing_sessions: true
```

Đây là mẫu mô tả yêu cầu, không phải schema cấu hình của một sản phẩm. Mỗi hành động phải được ánh xạ sang cơ chế thực thi có thật như vai trò ứng dụng, endpoint quản trị hạn chế hoặc nhóm lệnh được kiểm soát.

### 5.1. Không nhầm phê duyệt với thực thi

Ticket ghi “không xuất dữ liệu” không ngăn được việc xuất dữ liệu nếu phiên vẫn có quyền đọc toàn bộ cơ sở dữ liệu. Tương tự, quyền “chỉ xem log” không nên triển khai bằng tài khoản quản trị toàn máy.

Một số công cụ đọc tệp, trình soạn thảo hoặc công cụ chạy tác vụ có thể mở shell hoặc gọi chương trình khác. Vì vậy, danh sách lệnh cho phép cần được kiểm chứng trong đúng ngữ cảnh thực thi; đối chiếu tên lệnh đơn thuần chưa đủ.

### 5.2. Tách trách nhiệm phù hợp với rủi ro

Người yêu cầu là kỹ thuật viên; người chịu trách nhiệm về tác động là chủ sở hữu nội bộ; hệ thống hoặc đội vận hành thực thi chính sách. Những vai trò này cần được tách theo mức rủi ro, tránh tự yêu cầu rồi tự phê duyệt quyền sản xuất.

Với thao tác rủi ro cao, có thể cần thêm người giám sát hoặc phê duyệt riêng. Không phải mọi phiên đọc log đều cần cùng mức thủ tục với thay đổi cấu hình bảo mật; điều quan trọng là phạm vi thực tế tương xứng với mức phê duyệt.

### 5.3. Thay đổi phạm vi khi đang làm việc

Nếu cần thêm tài sản, quyền ghi hoặc thời gian, kỹ thuật viên phải yêu cầu mở rộng. Người phê duyệt đánh giá phần thay đổi trước khi quyền mới được kích hoạt.

Không nên giải quyết bằng cách gửi thêm mật khẩu qua chat hoặc mở một tài khoản quản trị ngoài quy trình. Quyền bổ sung cũng cần thời hạn và phải xuất hiện trong bằng chứng của phiên liên quan.

## 6. Credential: giữ bí mật và kiểm soát việc sử dụng

Mục tiêu là giảm số người biết credential đặc quyền và giảm thời gian credential có giá trị ngoài nhu cầu công việc.

### 6.1. Credential injection và tài khoản ngắn hạn

Khi cơ chế hỗ trợ, PAM có thể lấy credential từ vault rồi thiết lập kết nối mà không hiển thị bí mật cho kỹ thuật viên. Với nền tảng hỗ trợ danh tính hoặc credential ngắn hạn, có thể cấp quyền tạm thời gắn với yêu cầu.

Cần phân biệt:

- Không hiển thị mật khẩu giúp giảm lộ bí mật qua con người.
- Quyền của phiên vẫn quyết định người điều khiển làm được gì.
- Credential được giữ trong vault không tự ngăn tài khoản tạo khóa, token hoặc một cơ chế truy cập mới trên máy đích.

Do đó phải kiểm soát cả đặc quyền của tài khoản, khả năng tạo tính bền vững và đường kết nối trực tiếp.

### 6.2. Trường hợp bắt buộc checkout bí mật

Một số hệ thống cũ buộc người dùng nhận credential. Khi đó cần quy định người nhận, lý do, thời hạn và tài sản; hạn chế việc tiết lộ; theo dõi sử dụng; và luân chuyển sau khi sử dụng theo chính sách.

Đổi mật khẩu có thể ảnh hưởng dịch vụ hoặc kết nối đang dùng tài khoản đó. Cần biết các phụ thuộc và có quy trình kiểm chứng; không áp dụng luân chuyển thiếu kiểm soát lên tài khoản dịch vụ dùng chung.

Mật khẩu mới thường ảnh hưởng lần xác thực tiếp theo. Nó không bảo đảm chấm dứt những phiên, token hoặc tiến trình đã được tạo trước đó. Thu hồi phải xử lý các đối tượng này riêng.

### 6.3. Không biến vault thành nơi lưu mọi thứ vô thời hạn

Credential cần có chủ sở hữu, tài sản liên quan, mục đích sử dụng và vòng đời. Credential dành cho một nhà cung cấp hoặc một chiến dịch hỗ trợ không nên trở thành phương tiện truy cập thường trực mà không có lý do được rà soát.

Không ghi mật khẩu, khóa riêng, token hoặc mã khôi phục vào ticket, đoạn chat hoặc phần mô tả bằng chứng.

## 7. Kiểm soát phiên, truyền tệp và dữ liệu nhạy cảm

### 7.1. Trước khi bắt đầu

Hệ thống cần kiểm tra danh tính, quyền đã duyệt, thời hạn, tài sản và điều kiện truy cập. Người dùng cần được thông báo về việc giám sát và các giới hạn theo chính sách áp dụng.

Thời hạn nên được kiểm tra tại thời điểm tạo phiên và trong vòng đời phiên khi cần. Một yêu cầu được duyệt hôm trước không tự động còn hiệu lực khi điều kiện đã thay đổi.

### 7.2. Trong phiên

Tùy giao thức và mức rủi ro, có thể cần:

- Ghi nhận thời điểm, tài sản, tài khoản đích, người điều khiển và các quyết định chính sách.
- Ghi hình hoặc ghi hoạt động lệnh trong phạm vi công cụ hỗ trợ.
- Giới hạn clipboard, ánh xạ ổ đĩa, truyền tệp và các kênh chuyển tiếp không cần thiết.
- Theo dõi tín hiệu vượt phạm vi, thử đăng nhập tài sản khác hoặc tạo tài khoản mới.
- Cho phép nhân sự được ủy quyền chấm dứt phiên và khóa việc mở lại.

Các khả năng này phụ thuộc giao thức và triển khai. Ghi hình desktop không có cùng tính quan sát với log lệnh; log lệnh cũng không mô tả đầy đủ tác động của một chương trình trên dữ liệu.

Ghi hình là bằng chứng hỗ trợ, không phải cơ chế ngăn chặn. Nó cũng có thể chứa dữ liệu nhạy cảm, nên cần mã hóa, kiểm soát người xem và lưu vết truy cập vào chính bản ghi đó.

### 7.3. Truyền tệp có chủ đích

Nhà cung cấp có thể cần đưa bản vá vào hệ thống hoặc lấy gói chẩn đoán ra ngoài. Luồng truyền tệp nên tách thành một hành động được kiểm soát:

1. Xác định người gửi, mục đích, tài sản đích và người duyệt.
2. Tiếp nhận tệp qua kênh đã thống nhất.
3. Kiểm tra nguồn gốc, chữ ký khi có, mã băm và kết quả kiểm tra theo chính sách.
4. Giới hạn nơi lưu, quyền thực thi và thời gian giữ tệp.
5. Với dữ liệu đi ra, kiểm tra nội dung và loại bỏ bí mật hoặc dữ liệu không cần thiết.
6. Ghi lại tệp nào được chuyển, phiên nào liên quan và ai cho phép.

Mã băm giúp đối chiếu đúng tệp, không tự chứng minh tệp an toàn. Quét tệp cũng không phải bảo đảm tuyệt đối.

Gói chẩn đoán có thể chứa cấu hình, token, thông tin khách hàng hoặc dữ liệu từ bộ nhớ. Không coi tên “support bundle” là bằng chứng rằng tệp có thể gửi tự do cho nhà cung cấp.

### 7.4. Phiên bị ngắt hoặc kết nối lại

Mất kết nối ở máy kỹ thuật viên không nhất thiết làm tiến trình trên máy đích dừng lại. Cần xác định chính sách cho phiên treo, thời gian không hoạt động và cách tiếp tục phiên.

Khi kết nối lại, phải kiểm tra quyền còn hiệu lực. Không nên cho phép nối lại một phiên đã hết cửa sổ phê duyệt chỉ vì phiên đó đã được tạo từ trước.

## 8. Thu hồi quyền: kiểm chứng kết quả trên toàn đường truy cập

Thu hồi là một quy trình có nhiều lớp:

| Lớp | Hành động có thể cần | Điều cần kiểm chứng |
|---|---|---|
| Danh tính bên ngoài | Khóa tài khoản, kết thúc phiên danh tính hoặc thu hồi token theo khả năng hệ thống | Không tạo được phiên truy cập mới |
| Quyền được phê duyệt | Hủy grant, lịch truy cập và nhóm quyền tạm | Không kích hoạt lại bằng yêu cầu cũ |
| Phiên PAM | Ngắt phiên và chặn kết nối lại | Gateway đã ngắt đường điều khiển |
| Hệ thống đích | Đóng phiên còn tồn tại, bỏ quyền tạm và xử lý tiến trình liên quan | Không còn quyền hoặc phiên tồn dư ngoài phê duyệt |
| Credential | Luân chuyển hoặc vô hiệu hóa theo loại credential | Bí mật cũ không xác thực được sau thu hồi |
| Dấu vết truy cập lâu dài | Kiểm tra tài khoản, khóa, tác vụ hoặc công cụ hỗ trợ mới | Không có cơ chế truy cập ngoài quy trình |

Không phải nền tảng nào cũng hỗ trợ thu hồi tức thì theo cùng một cách. Cần ghi rõ khoảng trễ, đối tượng chưa thu hồi được và cách xử lý bù.

Chấm dứt kết nối điều khiển không tự hoàn tác thay đổi đã thực hiện hoặc dừng mọi tác vụ chạy nền. Khi nghi ngờ có hành vi bất thường, đội vận hành cần đánh giá tác động trên máy đích thay vì chỉ nhìn trạng thái phiên PAM.

Một tiêu chí hoàn tất có thể là: yêu cầu đã đóng; không mở được phiên mới; phiên đang hoạt động đã xử lý; quyền tạm đã gỡ; credential liên quan đã xử lý; kết quả được xác nhận bằng log hoặc kiểm tra phù hợp.

## 9. Truy cập khẩn cấp và ngoại lệ

Sự cố khẩn cấp cần một đường xử lý nhanh nhưng vẫn có trách nhiệm rõ ràng. Hồ sơ khẩn cấp nên xác định:

- Điều kiện kích hoạt và người nội bộ có quyền tuyên bố tình huống khẩn cấp.
- Kỹ thuật viên được xác minh qua kênh liên hệ đã thiết lập.
- Tài sản, quyền và thời hạn tối đa.
- Người giám sát hoặc người chấp nhận rủi ro.
- Cách thu hồi, bảo vệ bằng chứng và rà soát sau sự cố.

Nếu chức năng ghi phiên không hoạt động, cần áp dụng hành vi đã thiết kế: từ chối phiên đặc quyền theo chính sách, hoặc sử dụng đường khẩn cấp đã được phê duyệt với biện pháp bù cụ thể. Không tự chuyển sang một công cụ điều khiển khác rồi mặc định coi như mức kiểm soát vẫn tương đương.

Nếu PAM hoặc IdP gặp sự cố, tài khoản khẩn cấp và đường thay thế phải nằm trong kế hoạch được kiểm thử trước. Sau khi dùng, phải kiểm tra phạm vi thực tế, thu hồi quyền, xử lý credential và lưu lại người chịu trách nhiệm.

Thời điểm hết hạn hợp đồng vẫn có hiệu lực trong tình huống khẩn cấp. Nếu cần tiếp tục công việc, người có thẩm quyền phải xử lý việc gia hạn hoặc ngoại lệ có thời hạn; không âm thầm giữ tài khoản hoạt động.

## 10. Quy trình vận hành từ yêu cầu đến đóng phiên

### Bước 1: tiếp nhận và xác minh

Nhân sự nội bộ xác minh nhu cầu, nhà cung cấp và kỹ thuật viên. Không cấp quyền chỉ dựa vào một email tự xưng là hỗ trợ kỹ thuật.

Đầu ra là yêu cầu có mục đích, người thực hiện, tài sản, cửa sổ truy cập và chủ sở hữu nội bộ.

### Bước 2: thu hẹp phạm vi

Xác định thao tác tối thiểu và dữ liệu cần xem. Ưu tiên chẩn đoán ở môi trường phù hợp hoặc chia sẻ dữ liệu đã giảm nhạy cảm nếu cách đó đáp ứng công việc.

Nếu phải vào sản xuất, ghi rõ lý do và tác động có thể xảy ra.

### Bước 3: phê duyệt và chuẩn bị

Người có trách nhiệm chấp thuận phạm vi. Đội vận hành chuẩn bị vai trò, chính sách phiên, đường mạng và kế hoạch xử lý tác động của thao tác.

Trước phiên, xác nhận gateway, vault và cơ chế ghi nhận cần thiết đang sẵn sàng.

### Bước 4: kích hoạt và theo dõi

Người dùng xác thực bằng danh tính cá nhân. Hệ thống cấp quyền theo cửa sổ đã duyệt và liên kết phiên với ticket.

Nếu xuất hiện nhu cầu ngoài phạm vi, áp dụng quy trình mở rộng thay vì sửa chính sách tùy tiện giữa phiên.

### Bước 5: kết thúc và thu hồi

Khi công việc hoàn tất, hết thời hạn hoặc bị hủy, chấm dứt phiên theo chính sách; gỡ quyền tạm; xử lý credential và kiểm tra tài sản đích.

Nếu công việc chưa xong, tạo hoặc phê duyệt lần truy cập tiếp theo với phạm vi phù hợp.

### Bước 6: đóng hồ sơ bằng chứng

Đối chiếu phạm vi được duyệt với thao tác và kết quả thực tế. Ghi nhận ngoại lệ, thay đổi đã thực hiện, việc thu hồi và người xác nhận.

Đóng ticket sau khi các hạng mục cần thiết đã được kiểm chứng; tránh lấy trạng thái ticket làm bằng chứng duy nhất rằng quyền đã bị thu hồi.

## 11. Bộ bằng chứng có thể đối chiếu

Một hồ sơ phiên nên cho phép nối các sự kiện bằng mã yêu cầu, mã phiên và định danh tài sản:

| Nhóm bằng chứng | Nội dung hữu ích |
|---|---|
| Yêu cầu | Mục đích, kỹ thuật viên, tài sản, thao tác và thời hạn |
| Phê duyệt | Người duyệt, thời điểm, phạm vi và ngoại lệ |
| Xác thực | Danh tính, kết quả, điều kiện được đánh giá và thời gian |
| Kích hoạt quyền | Quyền được cấp, tài khoản đích, thời điểm bắt đầu và hết hạn |
| Hoạt động phiên | Mã phiên, giao thức, mốc thời gian và vị trí bản ghi khi có |
| Log đích | Sự kiện đăng nhập, thao tác và thay đổi liên quan |
| Truyền tệp | Hướng truyền, tệp, mã băm, kiểm tra và người cho phép |
| Thu hồi | Quyền đã gỡ, phiên đã ngắt, credential đã xử lý và kết quả xác nhận |

Đồng bộ thời gian và ghi rõ múi giờ giúp đối chiếu sự kiện giữa hệ thống. Mã phiên PAM có thể không xuất hiện nguyên dạng trong log đích, nên cần mô tả cách tương quan bằng tài khoản, nguồn kết nối, tài sản và mốc thời gian.

Bằng chứng cần được bảo vệ khỏi sửa hoặc xóa trái phép. Người điều khiển phiên không nên có khả năng xóa bản ghi kiểm toán của chính mình.

Thời hạn lưu phải dựa trên chính sách, hợp đồng và yêu cầu áp dụng của tổ chức; không có một con số chung phù hợp cho mọi phiên nhà cung cấp. Cần giới hạn dữ liệu thu thập, phân quyền người xem và xử lý bản ghi hết hạn theo quy trình.

## 12. Tình huống thực hành: hỗ trợ lỗi ứng dụng kho

### Bối cảnh

Nhà cung cấp cần xử lý lỗi dịch vụ trên `app-maint-01`. Kỹ thuật viên được phép đọc log và khởi động lại `warehouse-api`. Cửa sổ hỗ trợ là 20:00–21:00. Không có yêu cầu đọc dữ liệu khách hàng hay quản trị cơ sở dữ liệu.

### Thiết kế ban đầu

- Tạo hoặc sử dụng danh tính cá nhân còn hiệu lực của kỹ thuật viên.
- Gắn người bảo trợ nội bộ và ticket với đúng tài sản.
- Yêu cầu xác thực mạnh và điều kiện thiết bị phù hợp.
- Cấp phiên qua gateway với vai trò hạn chế cho đúng dịch vụ.
- Cấm đường đăng nhập quản trị trực tiếp ngoài phương án đã duyệt.
- Bật ghi nhận cần thiết và quy định dừng phiên lúc hết hạn.
- Cho phép nhận tệp qua luồng kiểm tra riêng nếu sau này có nhu cầu.

### Diễn biến và quyết định

| Thời điểm | Sự kiện | Cách xử lý |
|---|---|---|
| 19:55 | Kỹ thuật viên thử bắt đầu phiên | Chưa cấp quyền trước cửa sổ |
| 20:05 | Đăng nhập và đọc log dịch vụ | Cho phép nếu các điều kiện còn hợp lệ |
| 20:20 | Đề nghị xuất toàn bộ cơ sở dữ liệu | Không cấp trong phạm vi hiện tại; đánh giá lại nhu cầu và phương án giảm dữ liệu |
| 20:35 | Đề nghị khởi động lại đúng dịch vụ | Thực hiện theo quyền và điều kiện đã duyệt |
| 20:50 | Một kỹ thuật viên khác muốn tiếp quản | Xác minh, phê duyệt người mới và mở phiên riêng |
| 21:00 | Cửa sổ kết thúc | Chặn phiên mới và kết thúc phiên hiện hữu theo chính sách |
| Sau phiên | Ticket báo đã sửa xong | Kiểm tra log, thu hồi và bằng chứng trước khi đóng hồ sơ |

Nếu đến 20:55 vẫn cần thêm 30 phút, kỹ thuật viên không tự kéo dài phiên. Người có trách nhiệm phê duyệt gia hạn trước khi quyền mới có hiệu lực. Nếu không được duyệt, phiên kết thúc và công việc được bàn giao theo kế hoạch.

### Những gì cần chứng minh sau phiên

Có thể chỉ ra đúng cá nhân đã thực hiện công việc; người đó chỉ tiếp cận tài sản trong phạm vi; thao tác có liên kết với yêu cầu; dữ liệu không được xuất ngoài phê duyệt; và các quyền tạm đã được thu hồi.

Nếu còn một tiến trình chẩn đoán chạy nền hoặc credential chưa luân chuyển được, hồ sơ phải ghi trạng thái thực tế, người xử lý và thời hạn khắc phục. Không đánh dấu thu hồi hoàn tất chỉ vì người dùng đã đóng cửa sổ trình duyệt.

## 13. Kiểm chứng thiết kế trước khi đưa vào vận hành

Thử nghiệm trong môi trường và phạm vi được phép. Đánh giá kết quả kỹ thuật, không chỉ nhìn các tùy chọn trên giao diện cấu hình.

| Phép thử | Kết quả mong đợi |
|---|---|
| Người chưa được duyệt yêu cầu cùng tài sản | Bị từ chối và có sự kiện giải thích |
| Tài khoản hợp lệ đăng nhập trước hoặc sau cửa sổ | Không kích hoạt được quyền ngoài thời hạn |
| Phiên được duyệt thử tài sản khác | Không có đường hoặc quyền truy cập tương ứng |
| Vai trò đọc log thử thao tác ngoài phạm vi | Bị hạn chế bằng cơ chế thực thi |
| Kỹ thuật viên thử kết nối trực tiếp bỏ gateway | Không thành công theo đường truy cập đã thiết kế |
| Thử truyền tệp khi chưa có quyền | Bị chặn trên các kênh đã xác định |
| Cửa sổ hết hạn khi phiên còn mở | Thực thi đúng chính sách phiên hiện hữu |
| Tài khoản bị khóa khi đang có phiên | Quan sát rõ lớp nào thu hồi ngay, lớp nào cần hành động bổ sung |
| Ghi phiên hoặc vault không sẵn sàng | Xử lý đúng chính sách và tạo cảnh báo phù hợp |
| Đóng phiên rồi kiểm tra tài sản đích | Không bỏ sót quyền, phiên hoặc tác vụ ngoài phạm vi |
| Đổi mật khẩu sau checkout | Bí mật cũ không mở phiên mới; phiên cũ được xử lý riêng |
| Kiểm tra người xem bằng chứng | Chỉ vai trò được phép xem và việc xem được ghi nhận |

Nếu một phép thử không đạt, phải sửa cơ chế hoặc ghi nhận ngoại lệ có chủ sở hữu và thời hạn trước khi mở rộng sử dụng.

## 14. Sai lầm thường gặp

**Dùng tài khoản “nhà cung cấp” chung cho mọi kỹ thuật viên.** Cách này làm mất định danh cá nhân. Hãy gắn danh tính cá nhân với từng phiên, kể cả khi tài khoản đích là tài khoản kỹ thuật dùng chung có kiểm soát.

**Cho rằng có MFA thì có thể mở mạng quản trị rộng.** MFA không giới hạn tài sản và hành động sau đăng nhập. Vẫn cần phân đoạn, quyền tối thiểu và kiểm soát phiên.

**Để mật khẩu trong vault nhưng cho tải về tùy ý.** Vault giảm giá trị nếu bí mật được tiết lộ rộng và không được xử lý sau sử dụng. Ưu tiên cơ chế không hiển thị bí mật và kiểm soát ngoại lệ checkout.

**Coi ghi hình là đủ để ngăn hành vi nguy hiểm.** Bản ghi giúp điều tra nhưng không ngăn thao tác xảy ra. Cần quyền thực thi phù hợp, giám sát và khả năng dừng.

**Khóa tài khoản rồi mặc định phiên đã kết thúc.** Token, kết nối hoặc tiến trình có thể tiếp tục tùy cơ chế. Phải kiểm tra thu hồi trên từng lớp.

**Tự động gửi mọi gói chẩn đoán ra ngoài.** Gói hỗ trợ có thể chứa bí mật hoặc dữ liệu nhạy cảm. Chỉ chuyển phần cần thiết qua luồng được duyệt.

**Giữ quyền sau sự cố để “lần sau tiện hỗ trợ”.** Đây là quyền thường trực phát sinh ngoài nhu cầu. Hãy giữ quy trình yêu cầu thuận tiện, còn quyền cần được cấp theo từng công việc.

## 15. Tự kiểm tra

1. Vì sao kết nối VPN thành công chưa đủ để cho phép kỹ thuật viên khởi động lại dịch vụ?
2. Trong trường hợp tài khoản đích phải dùng chung, cần những gì để truy về cá nhân thực hiện?
3. JIT và JEA giảm hai loại rủi ro khác nhau như thế nào?
4. Nếu người dùng cần tải gói chẩn đoán ra ngoài, quy trình phải bổ sung kiểm soát gì?
5. Vì sao đổi mật khẩu không bảo đảm dừng phiên đang hoạt động?
6. Cần kiểm tra những gì khi quyền hết hạn nhưng một tác vụ vẫn chạy trên máy đích?
7. Nếu PAM không ghi được phiên, ai và chính sách nào quyết định có tiếp tục truy cập?
8. Bằng chứng nào cho phép xác nhận quyền đã thu hồi thay vì chỉ xác nhận ticket đã đóng?

### Gợi ý trả lời

1. VPN cung cấp một mức kết nối; quyền thực thi phải dựa trên danh tính, phê duyệt, tài sản, hành động và thời hạn.
2. Cần danh tính cá nhân tại điểm vào, ánh xạ tới phiên PAM và tài khoản đích, mốc thời gian và log có thể đối chiếu; phải xử lý vấn đề nhiều phiên đồng thời.
3. JIT thu hẹp thời gian quyền tồn tại; JEA thu hẹp khả năng thực thi trong thời gian đó.
4. Cần đánh giá dữ liệu, loại bỏ phần không cần thiết, duyệt việc xuất, kiểm soát kênh nhận và lưu bằng chứng truyền tệp.
5. Phiên hoặc token đã được xác thực có thể còn hiệu lực; cần cơ chế kết thúc và thu hồi riêng.
6. Kiểm tra tác động, người sở hữu tác vụ, quyền tạm, phiên trên máy đích và kế hoạch dừng hoặc bàn giao phù hợp.
7. Quyết định phải theo chính sách và thẩm quyền đã xác lập, với ngoại lệ và biện pháp bù có bằng chứng khi được phép.
8. Cần kết quả gỡ grant, chặn phiên mới, xử lý phiên hiện hữu, quyền tại đích và credential liên quan.

## Kết luận

Truy cập từ xa của nhà cung cấp cần được quản lý như một chuỗi quyền có mục đích: một cá nhân đã xác minh, một công việc được duyệt, một tập tài sản và hành động tối thiểu, một cửa sổ thời gian rõ ràng và một kết quả thu hồi có thể kiểm chứng.

PAM đóng vai trò kết nối định danh, vault, JIT/JEA và giám sát phiên trong chuỗi đó. Chất lượng kiểm soát được thể hiện ở đường truy cập thực tế và bằng chứng thực thi, từ lần yêu cầu đầu tiên cho đến khi không còn quyền tồn dư sau công việc.
