# Tách máy admin khỏi máy thường trong PAM

## 1. Vì sao cần tách môi trường quản trị?

Máy làm việc thông thường thường dùng cho email, họp, duyệt web, tài liệu bên ngoài và nhiều ứng dụng phục vụ công việc hằng ngày. Các hoạt động này làm thiết bị tiếp xúc với nội dung và phần mềm từ nhiều nguồn.

Máy dùng cho quản trị đặc quyền lại có khả năng mở phiên tới production, sử dụng quyền nhạy cảm hoặc điều khiển những hệ thống như nguồn danh tính, PAM và vault. Nếu cùng một môi trường vừa xử lý nội dung bên ngoài vừa giữ phiên quản trị, một sự cố trên môi trường đó có thể ảnh hưởng trực tiếp tới đặc quyền.

**Tách máy admin khỏi máy thường** là thiết kế một ranh giới giữa môi trường phục vụ tác vụ thông thường và môi trường khởi tạo, điều khiển công việc quản trị.

Mục tiêu gồm:

- Giảm nơi credential và phiên đặc quyền có thể xuất hiện.
- Giảm khả năng mã độc từ công việc thông thường điều khiển tác vụ quản trị.
- Giới hạn phần mềm, kết nối và dữ liệu trong môi trường admin.
- Tạo nguồn truy cập có thể nhận diện và kiểm tra theo policy PAM.
- Giữ bằng chứng về người dùng, thiết bị, quyền và phiên.

Máy admin chuyên dụng thường được gọi là **privileged access workstation — PAW**. Tên gọi này chỉ có ý nghĩa khi các kiểm soát và vòng đời tương ứng thực sự được áp dụng.

## 2. Ranh giới cần bảo vệ là gì?

Một môi trường quản trị có thể tiếp cận những đối tượng nhạy cảm:

| Đối tượng | Ví dụ | Tác động nếu môi trường admin bị kiểm soát |
|---|---|---|
| Credential | Khóa, token, chứng thư, secret được checkout | Có thể bị lấy hoặc sử dụng ngoài ý định |
| Phiên | SSH, RDP, trình duyệt quản trị | Có thể bị điều khiển hoặc sử dụng lại |
| Input | Lệnh, tham số và yêu cầu phê duyệt | Có thể bị thay đổi trước khi gửi |
| Output | Dữ liệu cấu hình, log và thông tin nhạy cảm | Có thể bị xem hoặc chuyển ra ngoài |
| Công cụ | Client quản trị, script và plugin | Có thể tạo tác vụ ngoài phạm vi |
| Trust | Host key, CA, danh mục target và cấu hình client | Có thể làm người dùng kết nối sai đích |

PAM có thể giữ secret ở gateway để người dùng không nhìn thấy. Điều đó giúp giảm một đường phơi lộ, nhưng không tự ngăn một endpoint bị kiểm soát thao tác trên phiên đã mở.

MFA có thể bảo vệ bước xác thực. Nó không tự xác minh rằng mọi input sau đó đều do người dùng có chủ đích tạo ra.

Vì vậy, bảo vệ nguồn khởi tạo và điều khiển phiên là một phần của kiến trúc PAM, bên cạnh quản lý credential và quyền tại đích.

## 3. Phân biệt tách thiết bị, tách tài khoản và tách phiên

| Biện pháp | Ranh giới tạo ra | Giới hạn cần hiểu |
|---|---|---|
| Tài khoản thường và tài khoản admin riêng | Tách quyền và quy trách nhiệm theo danh tính | Cùng OS bị kiểm soát có thể ảnh hưởng cả hai khi sử dụng |
| Hai profile trình duyệt | Tách một phần dữ liệu ứng dụng | Không tạo ranh giới mạnh với malware có quyền trên OS |
| Hai user session trên một OS | Tách một phần trạng thái người dùng | Kernel và quản trị host vẫn là thành phần dùng chung |
| VM riêng | Tạo ranh giới guest theo khả năng hypervisor | Host và kênh tích hợp có thể ảnh hưởng guest |
| Workspace hoặc desktop từ xa | Chuyển môi trường thực thi sang nơi khác | Client vẫn có thể ảnh hưởng input, output và phiên |
| Thiết bị admin riêng | Tách phần lớn môi trường hằng ngày khỏi nguồn quản trị | Vẫn cần bảo vệ hệ điều hành, quản lý thiết bị và các đường chuyển dữ liệu |

Những biện pháp này có thể kết hợp. Không nên gọi mọi hình thức “mở cửa sổ khác” là mức cách ly tương đương.

Tách tài khoản là cần thiết cho nhiều thiết kế nhưng chưa đủ để đạt mục tiêu tách endpoint. Ngược lại, có hai laptop nhưng dùng cùng browser sync, secret và công cụ không kiểm soát cũng có thể nối lại ranh giới đã tách.

## 4. Nguyên tắc về nguồn tin cậy

Một thành phần có thể điều khiển môi trường admin trở thành một phần của ranh giới bảo vệ môi trường đó.

Ví dụ:

- Host có thể đọc hoặc sửa bộ nhớ và storage của VM theo quyền, cơ chế và trạng thái nền tảng.
- Hệ thống quản lý endpoint có thể cài phần mềm hoặc chạy lệnh trên PAW.
- Công cụ hỗ trợ từ xa có thể điều khiển màn hình và input.
- Nguồn image hoặc cập nhật có thể thay mã thực thi.
- Tài khoản có quyền phục hồi danh tính hoặc đăng ký thiết bị có thể thay đổi điều kiện truy cập.

Do đó, cần lần theo chuỗi điều khiển, không chỉ nhìn thiết bị cuối.

~~~text
Ai quản lý PAW?
  → Ai điều khiển công cụ quản lý đó?
  → Ai được sửa image, policy hoặc gói cập nhật?
  → Ai được reset danh tính và thêm thiết bị?
  → Những quyền này được giới hạn và ghi nhận ra sao?
~~~

Một PAW được khóa cấu hình tại chỗ vẫn có thể bị ảnh hưởng nếu mọi nhân viên hỗ trợ đều có quyền chạy lệnh từ xa không giới hạn trên nó.

Mức kiểm soát của chuỗi quản lý cần phù hợp với đặc quyền mà PAW có thể sử dụng.

## 5. Các mô hình triển khai và giới hạn

### 5.1. Máy admin vật lý riêng

Một thiết bị dành cho quản trị có thể giảm việc dùng chung hệ điều hành, ứng dụng và dữ liệu với máy làm việc.

Để đạt mục tiêu, cần giữ vai trò sử dụng rõ:

- Máy thường xử lý email, web và nội dung công việc thông thường.
- Máy admin chỉ dùng ứng dụng, tài liệu và đường truy cập phục vụ quản trị đã được phép.
- Credential và phiên quản trị không được đưa trở lại máy thường.
- Chuyển dữ liệu giữa hai môi trường có quy trình riêng.

Thiết bị riêng không tự loại bỏ rủi ro từ firmware, image, cập nhật, công cụ quản lý hoặc hành vi chuyển tệp. Nó tạo một ranh giới cần được vận hành, không phải bảo đảm tuyệt đối.

### 5.2. Host tin cậy cho quản trị, công việc thường trong VM

Một thiết kế có thể đặt môi trường quản trị trên host được bảo vệ, còn công việc thông thường ở guest cách ly.

Cần đánh giá hypervisor, tài nguyên chia sẻ, thiết bị ngoại vi, clipboard, thư mục dùng chung, mạng và công cụ tích hợp. Guest có mức tin cậy thấp hơn không nên có đường điều khiển host ngoài thiết kế.

Host vẫn là thành phần ảnh hưởng cả hai môi trường. Nếu người dùng cài tùy ý phần mềm thường lệ trực tiếp lên host, ranh giới dự kiến sẽ suy giảm.

### 5.3. VM admin trên máy thường

Nếu host được dùng cho nội dung rủi ro cao và bị kiểm soát, việc đặt một VM admin bên trong không tự bảo vệ guest khỏi chủ thể điều khiển host.

Host có thể có khả năng quan sát, thay đổi hoặc tác động tới hoạt động của guest tùy kiến trúc. Vì vậy, VM không tự nâng mức tin cậy của máy nền.

Mô hình này có thể có giá trị cho một số mục tiêu cách ly ứng dụng, nhưng phải ghi đúng giới hạn khi đánh giá nguồn quản trị đặc quyền.

### 5.4. Remote admin desktop từ máy thường

Một desktop quản trị tập trung có thể giúp quản lý công cụ, credential và dữ liệu phía server. Tuy nhiên, máy thường vẫn là nơi người dùng nhìn màn hình và nhập lệnh.

Nếu client bị ảnh hưởng, đối tượng tấn công có thể tác động tới phiên hoặc dữ liệu hiển thị, dù private key hay secret không được tải về client.

Cần đánh giá nguồn truy cập, xác thực, bảo vệ phiên và kênh chuyển dữ liệu. Không dùng việc “chỉ mở trình duyệt” để suy ra máy nguồn không còn ảnh hưởng tới tác vụ quản trị.

### 5.5. Tách theo phạm vi quản trị

Không phải mọi tác vụ admin có cùng mức ảnh hưởng. Máy quản trị ứng dụng thử nghiệm có thể không phù hợp để điều khiển nguồn danh tính, vault hoặc control plane nhạy cảm.

Có thể cần tách môi trường hoặc quyền quản trị theo phạm vi ảnh hưởng. Tên nhóm hay số lượng lớp không quan trọng bằng việc xác định ai có thể điều khiển ai và credential nào được dùng ở đâu.

## 6. Kiến trúc tham chiếu cùng PAM

~~~mermaid
flowchart LR
    U["Quản trị viên"] --> D["Máy làm việc thường"]
    U --> A["Máy admin được quản lý"]
    D --> B["Email, web và ứng dụng thường"]
    A --> P["PAM: xác thực và ủy quyền"]
    P --> G["Gateway quản trị"]
    G --> T["Target được cấp"]
    V["Vault hoặc broker"] --> G
    M["Nguồn quản lý PAW được bảo vệ"] --> A
    A --> L["Telemetry và bằng chứng"]
    P --> L
    G --> L
    T --> L
    D -. "Đường quản trị cần được hạn chế" .-> T
~~~

Sơ đồ là mô hình logic. Thực tế có thể dùng client gốc, remote desktop hoặc gateway theo giao thức.

Những kết quả cần đạt gồm:

1. PAM có cách nhận diện và đánh giá nguồn admin theo policy.
2. Máy thường không có đường quản trị trực tiếp trái phạm vi.
3. Gateway chỉ tới những target và dịch vụ cần thiết.
4. Credential được cấp qua luồng được ủy quyền.
5. Quyền tại đích khớp tác vụ, không chỉ nhãn role.
6. Có liên kết giữa người dùng, thiết bị, yêu cầu, grant và phiên.
7. Hệ thống quản lý PAW được bảo vệ phù hợp.

Đặt PAW vào một subnet riêng chưa tự chứng minh các kết quả này.

## 7. Quản lý danh tính trên hai môi trường

### 7.1. Tách danh tính theo mục đích

Danh tính phục vụ quản trị target cần có phạm vi và điều kiện sử dụng riêng. Không dùng nó để mở email, duyệt web thông thường hoặc đăng nhập ứng dụng không cần đặc quyền trên máy thường.

Tuy nhiên, phải phân biệt:

- Danh tính đăng nhập PAW.
- Quyền quản trị cục bộ PAW.
- Danh tính vào PAM.
- Tài khoản hiệu lực tại target.
- Danh tính quản lý fleet PAW.

Các vai trò có thể liên kết nhưng không cần là cùng một tài khoản hoặc cùng mức quyền.

Một người quản trị production không mặc nhiên cần quyền quản trị OS của PAW. Công cụ có thể được phân phối qua luồng quản lý riêng thay vì cho mọi người tự cài bằng quyền rộng.

### 7.2. Hạn chế credential và trạng thái dùng chung

Cần xem xét:

- Đồng bộ trình duyệt giữa máy thường và PAW.
- Kho mật khẩu hoặc extension có quyền đọc dữ liệu quản trị.
- Cookie và token được xuất hoặc sao chép.
- SSH agent forwarding và khóa dùng chung.
- Cấu hình client được lấy từ thư mục đồng bộ.
- Tài khoản recovery hoặc thiết bị dự phòng dùng ở cả hai nơi.

Một profile trình duyệt riêng không đủ nếu extension hoặc dịch vụ đồng bộ có thể tiếp cận cả dữ liệu thường và dữ liệu quản trị.

Không sao chép credential từ PAW sang máy thường chỉ để thao tác thuận tiện. Nếu cần dùng công cụ khác, phải thiết kế luồng phù hợp với nguồn truy cập và phạm vi được cấp.

### 7.3. MFA và JIT vẫn cần thiết

PAW được quản lý không tự thay MFA, entitlement và phê duyệt. MFA thành công cũng không tự làm thiết bị trở thành PAW hợp lệ.

PAM cần đánh giá danh tính, nguồn thiết bị và tác vụ theo policy. JIT giúp giảm thời gian giữ quyền; JEA giúp giới hạn hành động sau khi vào target. Chúng bổ sung cho ranh giới endpoint.

## 8. Baseline của máy admin

Baseline cần theo nền tảng và môi trường, nhưng có thể tổ chức theo các mục tiêu sau:

| Nhóm kiểm soát | Kết quả cần hướng tới |
|---|---|
| Nguồn cài đặt | Image và gói phần mềm có nguồn quản lý, phiên bản và owner |
| Khởi động và lưu trữ | Bảo vệ phù hợp với nguy cơ thay đổi trái phép hoặc mất thiết bị |
| Tài khoản cục bộ | Quyền tối thiểu và vòng đời rõ |
| Phần mềm | Chỉ ứng dụng phục vụ công việc được cho phép |
| Cập nhật | Có quy trình kiểm tra, triển khai và xử lý lỗi |
| Bảo vệ endpoint | Khả năng phát hiện, hạn chế và thu thập dữ liệu theo thiết kế |
| Trust của client | Host key, CA và endpoint được quản lý |
| Phiên cục bộ | Khóa màn hình, thời hạn và xử lý mất thiết bị phù hợp |
| Dữ liệu | Hạn chế lưu secret và dữ liệu nhạy cảm không cần thiết |
| Quản lý từ xa | Chỉ nguồn, vai trò và tác vụ được ủy quyền |
| Giám sát | Nhận diện thiết bị, trạng thái và sự kiện quan trọng |

Một phần mềm có chữ ký không tự có nghĩa mọi cách sử dụng của nó đều an toàn. Cần biết nguồn, mục đích, quyền thực thi và vòng đời cập nhật.

Công cụ endpoint chạy với quyền cao cũng tạo một đường quản lý quan trọng. Quyền vào console quản lý, thay policy hoặc phân phối gói cần được kiểm soát tương ứng.

Không đưa credential production vào golden image. Clone image không nên làm nhiều thiết bị có cùng danh tính máy hoặc cùng secret riêng theo cách trái thiết kế.

## 9. Hạn chế phần mềm và nội dung trên PAW

PAW cần những công cụ đủ cho công việc, nhưng mỗi ứng dụng, extension, plugin hoặc script đều mở thêm đường xử lý dữ liệu và thực thi mã.

Cần làm rõ:

- Công cụ nào được dùng cho nhóm target nào.
- Ai được thêm hoặc cập nhật công cụ.
- Nguồn tải và nơi kiểm tra gói.
- Khả năng chạy script hoặc plugin ngoài danh mục.
- Quyền đọc credential, cookie và cấu hình client.
- Dữ liệu nào được giữ lại sau phiên.

Tài liệu vận hành cũng có thể chứa nội dung chủ động hoặc liên kết ngoài. Có thể dùng tài liệu đã được quản lý, bản tham chiếu phù hợp hoặc một môi trường riêng để xử lý nội dung bên ngoài.

Nếu cần một công cụ mới trong sự cố, phải có luồng tiếp nhận khả thi. Một baseline quá khó sử dụng có thể khiến người vận hành tìm đường đi vòng; vấn đề cần được giải quyết bằng khả năng hỗ trợ công việc, không bằng cách mặc định bỏ kiểm soát.

Công cụ và script được tải từ máy thường cần được xem là đầu vào qua ranh giới tin cậy. Một tên tệp quen thuộc không chứng minh nội dung không thay đổi.

## 10. Kiểm soát mạng và nhận diện thiết bị

### 10.1. Chỉ mở những đường cần thiết

PAW có thể cần tới:

- Nguồn danh tính và dịch vụ MFA.
- Điểm vào PAM hoặc gateway.
- Dịch vụ quản lý và cập nhật.
- DNS, thời gian và hạ tầng phụ trợ.
- Kho công cụ hoặc tài liệu được phép.
- Hệ thống telemetry và log.

Cần kiểm kê các dependency này. Không mở mọi egress chỉ vì một công cụ chưa hoạt động.

Ở phía target, cần hạn chế đường quản trị từ máy thường, VPN hoặc mạng khác theo kiến trúc. Nếu target vẫn nhận credential trực tiếp từ mọi thiết bị, PAW có thể chỉ là một lựa chọn sử dụng, chưa phải nguồn bắt buộc.

### 10.2. Địa chỉ IP không đủ làm danh tính thiết bị

Một subnet riêng hỗ trợ phân vùng nhưng có thể chứa nguồn khác hoặc có đường NAT. Cần hiểu nguồn mà điểm thực thi thực sự nhìn thấy.

Theo khả năng nền tảng, có thể dùng danh tính thiết bị, chứng thư, trạng thái quản lý và các tín hiệu được xác minh. Phải kiểm tra nguồn và độ mới của dữ liệu, không nhận trường “is_admin_workstation=true” do client tự khai.

Một thiết bị không có telemetry mới không tự là thiết bị an toàn. Hành vi khi dữ liệu thiếu hoặc cũ cần được policy xác định.

### 10.3. Không bỏ sót các endpoint quản trị

Máy thường có thể không SSH được nhưng vẫn mở web, API, console hoặc giao diện ngoài băng. Mỗi đường cần được kiểm kê và áp dụng ranh giới tương ứng.

Tương tự, pipeline hoặc công cụ tự động có thể tạo tác động production mà không dùng phiên tương tác từ PAW. Cần nhận diện chúng như các đường đặc quyền khác, không tuyên bố PAW đã bao phủ mọi thay đổi chỉ từ việc chặn SSH.

## 11. Chuyển dữ liệu giữa máy thường và máy admin

### 11.1. Các kênh dễ nối lại ranh giới

Các ví dụ gồm:

- Clipboard.
- Shared folder và ổ đĩa ánh xạ.
- Đồng bộ đám mây.
- USB và thiết bị ngoại vi.
- Drag-and-drop giữa host và guest.
- Truyền file qua remote desktop hoặc SSH.
- Tải trực tiếp script từ ticket hoặc chat.
- Sao chép profile trình duyệt, cookie hoặc cấu hình có secret.

Một đường chuyển tiện lợi có thể mang cả mã thực thi, dữ liệu nhạy cảm và trạng thái xác thực. Cần đánh giá theo mục đích chứ không chỉ theo tên tính năng.

### 11.2. Luồng tiếp nhận công cụ hoặc script

Một mô hình minh họa:

~~~text
Nội dung từ bên ngoài
  → nơi tiếp nhận được quản lý
  → kiểm tra nguồn, nội dung và quyền cần dùng
  → phê duyệt hoặc xuất bản theo quy trình
  → kho artifact được bảo vệ
  → PAW lấy phiên bản đã được chấp nhận.
~~~

Hash giúp đối chiếu nội dung, nhưng chỉ có ý nghĩa khi giá trị kỳ vọng đến từ nguồn tin cậy. Một hash đi cùng tệp từ cùng một nguồn chưa được xác minh không tự chứng minh tệp hợp lệ.

Quét hoặc kiểm tra không bảo đảm phát hiện mọi nội dung có hại. Quy trình cần kết hợp nguồn, review, giới hạn quyền và phạm vi sử dụng.

### 11.3. Dữ liệu đi ra

Log, cấu hình và kết quả chẩn đoán có thể chứa secret hoặc dữ liệu nhạy cảm. Cần có đường xuất phù hợp với mục đích và nơi nhận, không chỉ mở mọi tính năng tải tệp.

Một restriction kỹ thuật có thể chỉ áp dụng cho một kênh. Ví dụ, chặn clipboard không tự ngăn mọi cách chuyển thông tin qua màn hình hoặc chương trình được phép. Phải ghi đúng giới hạn.

## 12. Policy minh họa cùng PAM

~~~yaml
# Mã giả mô tả ý định, không phải cấu hình sản phẩm.
policy:
  id: approved-admin-source-example
  action: open_privileged_session
  subject_group: approved-production-operators

  source:
    require_managed_admin_device: true
    device_identity_source: trusted_device_inventory
    posture_source: trusted_management_service
    reject_client_self_asserted_posture: true
    evaluate_freshness: true

  authentication:
    accepted_profile: verified_privileged_mfa_profile

  authorization:
    require_current_entitlement: true
    require_approval_when_applicable: true
    role: approved_task_role
    target_group: approved-production-targets

  path:
    entry: approved_pam_entry
    gateway_pool: approved_production_gateways
    direct_access_from_standard_devices: outside_allowed_path

  session:
    apply_approved_time_limits: true
    resume_requires_current_policy_check: true
    data_channels: approved_channels_only

  evidence:
    link_subject_device_request_and_session: true
~~~

Các trường này chỉ mô tả điều cần đạt. Việc triển khai phải chỉ ra cơ chế nhận diện thiết bị, dữ liệu posture, điểm kiểm tra và khả năng thực thi.

Nếu hệ thống chỉ phân biệt nguồn IP, không được ghi rằng đã xác minh mạnh danh tính PAW. Nếu clipboard hoặc file transfer không kiểm soát được trên giao thức đang dùng, cần xử lý giới hạn đó thay vì coi dòng data_channels đã có hiệu lực.

Khi thiết bị bị cách ly hoặc mất trạng thái hợp lệ, cần biết policy ảnh hưởng cấp mới, resume và phiên đang chạy như thế nào. Một kiểm tra lúc mở chưa tự tạo giám sát liên tục.

## 13. Ví dụ xuyên suốt: vận hành hai môi trường

### 13.1. Bối cảnh

Linh có:

- Máy làm việc để email, họp, tài liệu và ứng dụng thông thường.
- PAW được quản lý để thực hiện tác vụ production.
- Danh tính riêng cho việc quản trị theo policy.
- Luồng PAM tới role chẩn đoán trên app-prod-a.

Linh nhận một script hỗ trợ qua ticket bên ngoài. Script cần được xem xét trước khi sử dụng với đặc quyền.

### 13.2. Chuẩn bị công việc

Linh không sao chép trực tiếp script từ máy thường rồi chạy trên PAW. Nội dung được tiếp nhận qua luồng artifact đã thiết kế, kiểm tra nguồn và tác vụ, sau đó xuất bản phiên bản được chấp nhận.

Yêu cầu PAM xác định đúng target, role, cửa sổ và nhu cầu dữ liệu. Nếu công việc chỉ cần chẩn đoán, không tự cấp quyền quản trị toàn bộ.

### 13.3. Mở phiên từ PAW

PAM kiểm tra danh tính, MFA, entitlement, phê duyệt và nguồn thiết bị theo policy. Gateway mở đúng target và dùng credential theo quyền được cấp.

Linh không cần biết secret tại đích nếu kiến trúc đã hỗ trợ môi giới credential. Bằng chứng liên kết Linh, PAW, request, grant, gateway session và account tại đích.

### 13.4. Nhu cầu phát sinh

Trong phiên, Linh muốn lấy một file log ra để gửi vendor. Đây là nhu cầu về dữ liệu cần đi qua luồng đã được phép. Không tự bật mọi ánh xạ ổ đĩa hoặc đồng bộ thư mục giữa hai máy.

Nếu công cụ mới hoặc quyền bổ sung là cần thiết, xử lý thay đổi theo quy trình. Việc đang ở PAW không tự cho phép mở rộng tác vụ.

### 13.5. Kết thúc

Kết thúc công việc, hệ thống xử lý phiên và grant theo vòng đời. Dữ liệu tạm được xử lý theo policy, giữ bằng chứng cần thiết mà không lưu secret thừa.

Máy thường vẫn không có credential, cookie hoặc đường mở lại phiên production từ thao tác đồng bộ. Nếu một session tại target chưa xác nhận kết thúc, cần giữ rõ trạng thái đó.

## 14. Vận hành, hỗ trợ và phương án dự phòng

### 14.1. Có owner cho toàn bộ vòng đời

Một PAW cần có owner cho:

- Cấp phát và đăng ký.
- Baseline và phần mềm.
- Patch và firmware theo phạm vi quản lý.
- Chứng thư, danh tính thiết bị và authenticator.
- Hỗ trợ từ xa.
- Mất thiết bị và ứng phó sự cố.
- Backup, reprovision và thu hồi.
- Xử lý khi người dùng đổi vai trò hoặc rời tổ chức.

Không nên để người dùng phải tự tìm gói cài và tự sửa cấu hình đặc quyền vì không có luồng hỗ trợ.

### 14.2. Hỗ trợ PAW cũng là tác vụ đặc quyền

Tài khoản helpdesk, công cụ remote support và hệ thống quản lý PAW cần phạm vi và quy trách nhiệm. Nếu chúng điều khiển được máy có phiên quản trị nhạy cảm, ảnh hưởng của chúng có thể lớn hơn một endpoint thông thường.

Cần xem xét việc truy cập trong lúc có phiên, quyền xem màn hình, tải tệp, chạy lệnh và lấy dữ liệu. Không mặc định một sản phẩm hỗ trợ từ xa phù hợp mọi ranh giới chỉ vì đã được dùng trên máy thường.

### 14.3. PAW hỏng hoặc cần cập nhật

Phải có phương án duy trì khả năng quản trị: thiết bị dự phòng được quản lý, reprovision từ nguồn tin cậy hoặc đường khẩn cấp có phạm vi.

Không để PAW hỏng tự trở thành lý do mặc định cho phép mọi laptop thường truy cập production. Nếu cần ngoại lệ, ghi rõ chủ thể, thiết bị, target, thời hạn, thẩm quyền và các điều kiện còn lại.

Cũng không giữ PAW không cập nhật vô hạn chỉ vì sợ mất đường quản trị. Khả năng dự phòng và quy trình kiểm tra giúp xử lý nhu cầu bảo trì.

### 14.4. Thu hồi và loại bỏ thiết bị

Khi thu hồi, cần xử lý danh tính thiết bị, chứng thư, token, key, dữ liệu cục bộ và quan hệ quản lý theo thiết kế. Chỉ đổi hostname hoặc xóa một bản ghi inventory chưa đủ.

Thiết bị thay thế cần được đăng ký đúng, không sao chép nguyên trạng secret và phiên cũ từ một nguồn không còn tin cậy.

## 15. Khi máy thường hoặc PAW có dấu hiệu bị ảnh hưởng

### 15.1. Máy thường bị nghi xâm phạm

Cần xác định có đường nào nối sang môi trường quản trị:

- Đã dùng credential quản trị trên máy đó chưa?
- Có đồng bộ browser, key hoặc cấu hình không?
- Có remote desktop điều khiển PAW không?
- Có chuyển script hoặc tệp gần thời điểm xảy ra sự cố không?
- Có kênh hỗ trợ hoặc công cụ quản lý dùng chung không?

Hai thiết bị riêng có thể giảm phạm vi ảnh hưởng, nhưng không đủ để tự kết luận PAW an toàn nếu còn các đường giao nhau chưa kiểm tra.

### 15.2. PAW bị nghi xâm phạm

Có thể cần hạn chế nguồn thiết bị, chặn cấp phiên mới, xử lý phiên đang chạy và đánh giá credential, token hoặc tác động tại target theo thẩm quyền.

Khóa một PAW trong inventory không tự thu hồi mọi cookie hoặc phiên mà thiết bị từng sử dụng. Cần lần theo liên kết thiết bị, danh tính, grant và session.

Reprovision từ nguồn tin cậy có thể là một phần phục hồi, nhưng không tự đảo ngược thay đổi tại target hoặc thu hồi credential đã bị lấy. Các phần đó có vòng đời riêng.

### 15.3. Giữ bằng chứng và phục hồi có kiểm soát

Thu thập dữ liệu theo quy trình trước khi làm mất bằng chứng cần thiết. Quyết định khóa, cách ly, khôi phục và cấp quyền lại cần có owner.

Khi trở lại hoạt động, chỉ khôi phục entitlement còn hợp lệ, kiểm tra nguồn thiết bị và thực hiện xác thực theo policy. Không tự đưa mọi ngoại lệ cũ trở lại cùng thiết bị mới.

## 16. Kiểm chứng việc tách môi trường

| Tình huống | Kết quả cần quan sát |
|---|---|
| Máy thường thử mở đường quản trị trực tiếp | Bị hạn chế theo kiến trúc đã định |
| Người dùng có MFA nhưng nguồn thiết bị không hợp lệ | Không bỏ qua điều kiện nguồn của policy |
| Client tự khai là PAW | Không được coi là bằng chứng thiết bị đáng tin |
| PAW thiếu dữ liệu posture mới | Xử lý theo policy, không mặc định an toàn |
| Tài khoản admin dùng để mở ứng dụng thường trên máy thường | Có khả năng hạn chế hoặc phát hiện theo thiết kế |
| Browser sync giữa hai môi trường | Không đưa trạng thái quản trị qua ranh giới trái policy |
| Truyền tệp, clipboard hoặc thư mục dùng chung | Chỉ các kênh được phép có hiệu lực trong phạm vi kiểm tra |
| VM admin nằm trên host không tin cậy | Giới hạn của mô hình được nhận diện đúng |
| Remote desktop từ máy thường | Rủi ro input, output và chiếm phiên được đánh giá |
| Công cụ quản lý PAW bị dùng ngoài thẩm quyền | Có giới hạn quyền và bằng chứng phù hợp |
| PAW hỏng hoặc mất kết nối | Dùng đúng phương án dự phòng, không mở rộng mặc định |
| PAW bị cách ly khi phiên còn hoạt động | Có kết quả riêng cho cấp mới và phiên hiện hữu |
| Thiết bị được thu hồi | Chứng thư, token, key và dữ liệu được xử lý theo phạm vi |
| Target có web, API hoặc console khác | Không bỏ sót đường quản trị ngoài luồng đã kiểm tra |

Kiểm chứng cần dùng tài khoản, thiết bị và target trong phạm vi được phép. Không cần đưa malware thật lên PAW hoặc làm gián đoạn production để chứng minh một ranh giới.

Bằng chứng có thể liên kết inventory thiết bị, phiên bản baseline, nguồn posture, request ID, session ID và log target. Không ghi secret hoặc token đầy đủ để chứng minh thiết bị đã được dùng.

## 17. Chỉ số và lỗi thường gặp

Các chỉ số có thể có ích gồm:

- Tác vụ đặc quyền khởi tạo từ nguồn admin đã được xác minh trong phạm vi quan sát.
- Target có đường quản trị từ máy thường chưa được xử lý.
- PAW không có owner hoặc baseline hiện hành.
- Quyền quản lý PAW quá rộng.
- Ngoại lệ nguồn thiết bị quá hạn.
- Credential hoặc phiên quản trị xuất hiện trên máy thường.
- Kênh chuyển dữ liệu chưa được kiểm kê.
- Thời gian từ sự kiện mất thiết bị tới kết quả hạn chế ở các lớp.
- Thiết bị thu hồi nhưng còn danh tính hoặc quyền truy cập.

Mẫu số cần rõ. Có một số PAW đã triển khai không chứng minh mọi truy cập đặc quyền trong hạ tầng đều đi từ chúng.

| Sai lầm | Hệ quả | Hướng xử lý |
|---|---|---|
| Có hai máy nhưng đồng bộ toàn bộ browser và key | Ranh giới bị nối lại qua dữ liệu xác thực | Kiểm soát trạng thái và kênh đồng bộ |
| VM admin trên host thường được coi là nguồn tin cậy cao | Bỏ qua khả năng host điều khiển guest | Đánh giá chuỗi tin cậy của nền tảng |
| Remote desktop được coi là loại bỏ rủi ro client | Input và phiên vẫn có thể bị tác động | Kiểm soát nguồn truy cập và phiên |
| Mọi helpdesk đều quản trị được PAW | Mở rộng quyền điều khiển môi trường đặc quyền | Giới hạn quyền và tác vụ quản lý |
| PAW được phép mọi egress | Tăng đường tiếp xúc và chuyển dữ liệu | Kiểm kê dependency và giới hạn theo mục đích |
| Target vẫn nhận truy cập từ mọi thiết bị | PAW chỉ còn là lựa chọn tự nguyện | Thực thi ranh giới tại đường và đích phù hợp |
| Không có cách tiếp nhận công cụ mới | Người dùng có thể tạo đường đi vòng | Có luồng artifact và hỗ trợ khả thi |
| Đổi thiết bị là coi sự cố đã xử lý | Secret, phiên hoặc thay đổi tại đích có thể còn | Thu hồi và xác minh các lớp liên quan |
| Chỉ đo số lượng PAW | Không thấy phạm vi sử dụng thực tế | Đo đường truy cập và khả năng thực thi |

## 18. Bài tập áp dụng

Một đội có laptop quản trị riêng, nhưng đăng nhập cùng tài khoản trình duyệt để đồng bộ extension, mật khẩu và bookmark với máy thường. Khi cần, họ remote desktop từ máy thường vào laptop quản trị. Script từ email được chép qua thư mục chia sẻ rồi chạy với quyền admin. Mọi nhân viên hỗ trợ có thể dùng công cụ quản lý endpoint để chạy lệnh trên cả hai nhóm máy. PAM ghi nhận phiên SSH, nhưng web quản trị vẫn mở từ VPN thông thường.

Hãy xác định:

1. Những ranh giới nào đã được tách và đường nào nối chúng trở lại?
2. Tài khoản, trạng thái trình duyệt và credential nào cần quản lý riêng?
3. Ai có khả năng điều khiển PAW qua chuỗi quản lý?
4. Remote desktop từ máy thường tạo giới hạn gì?
5. Luồng tiếp nhận script và xuất dữ liệu nên được thiết kế thế nào?
6. Cần thay đổi gì để nguồn admin là điều kiện được thực thi?
7. Bằng chứng nào cho biết quyền, phiên và dữ liệu không đi qua đường ngoài phạm vi?
8. Khi máy thường bị nghi ảnh hưởng, cần kiểm tra quan hệ nào với PAW?

Một thiết kế đạt mục tiêu cần chỉ rõ nguồn tin cậy, quyền điều khiển, kênh giao nhau và cách kiểm chứng. Tách môi trường quản trị có giá trị khi credential và phiên đặc quyền được giữ trong một ranh giới được bảo vệ và vận hành nhất quán với PAM.
