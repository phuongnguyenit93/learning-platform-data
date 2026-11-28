# LAPS và local admin password

## 1. Vấn đề cần giải quyết

Một doanh nghiệp có thể bảo vệ tài khoản Domain Admin rất chặt nhưng vẫn để hàng trăm máy Windows dùng cùng mật khẩu local administrator. Khi kẻ tấn công lấy được bí mật xác thực của tài khoản đó trên một máy, họ có thể thử dùng lại nó trên những máy khác. Mật khẩu dùng chung biến một sự cố tại endpoint thành đường di chuyển ngang trong hệ thống.

Windows LAPS, viết tắt của **Local Administrator Password Solution**, giúp quản lý mật khẩu của tài khoản quản trị cục bộ trên từng thiết bị Windows. Thay vì phân phối một mật khẩu chung, mỗi thiết bị có mật khẩu riêng, được thay đổi theo chính sách và sao lưu vào đích lưu trữ được hỗ trợ. Người được ủy quyền có thể truy xuất mật khẩu cho một nhu cầu hỗ trợ cụ thể.

Trong Privileged Access Management, giá trị của LAPS không chỉ là tạo mật khẩu mạnh. Cần quản lý toàn bộ chuỗi:

**Tài khoản được quản lý → thiết bị thuộc phạm vi → quyền truy xuất → mục đích sử dụng → đổi mật khẩu → bằng chứng kiểm toán.**

Sau bài này, người học cần có khả năng:

- Phân biệt local administrator, quản trị viên miền và phạm vi của LAPS.
- Thiết kế nơi sao lưu, chính sách mật khẩu và quyền truy xuất.
- Phân biệt expiration, rotation, backup và xử lý phiên đăng nhập.
- Vận hành một ca hỗ trợ có kiểm soát và xác minh kết quả.
- Nhận diện cấu hình sai, tài khoản bị bỏ sót và quyền đọc quá rộng.

## 2. Local administrator và phạm vi đặc quyền

### 2.1. Cùng tên không có nghĩa cùng danh tính

Tài khoản local thuộc về từng máy Windows. Ví dụ, `WIN-APP-017\Administrator` thuộc máy `WIN-APP-017`; nó khác `CORP\Administrator` trong Active Directory.

Hai máy có thể cùng có tài khoản tên Administrator nhưng đó là hai danh tính khác nhau. Rủi ro xuất hiện khi chúng dùng cùng một mật khẩu: một bí mật có thể được tái sử dụng để truy cập nhiều máy.

Tài khoản Administrator tích hợp có định danh SID với RID kết thúc bằng `-500`. Đổi tên không biến nó thành tài khoản mới và không thay thế việc quản lý mật khẩu. Khi dùng cơ chế nhắm tài khoản tích hợp của Windows LAPS, cần hiểu chính sách nhận diện tài khoản thay vì chỉ dựa vào tên hiển thị.

### 2.2. LAPS không quản lý mọi loại đặc quyền

LAPS không phải công cụ thay mật khẩu Domain Admin, không tự quản lý mọi tài khoản dịch vụ và không tự kiểm soát thành viên của mọi nhóm quản trị.

Windows LAPS còn có khả năng quản lý mật khẩu DSRM trên domain controller khi đáp ứng điều kiện tương ứng. DSRM phục vụ phục hồi dịch vụ thư mục, khác với local administrator thông thường trên member server. Cần thiết kế luồng quản lý riêng cho domain controller.

| Việc cần làm | Câu hỏi kiểm soát | Vai trò của LAPS |
|---|---|---|
| Kiểm soát quyền local admin | Ai cần quyền quản trị trên máy? | Phải phối hợp quản trị nhóm và cơ chế elevation |
| Quản lý mật khẩu | Bí mật được tạo, lưu và đổi thế nào? | Chức năng cốt lõi |
| Kiểm soát sử dụng | Ai lấy mật khẩu, dùng để làm gì, trong bao lâu? | Cần quy trình PAM, ticket và giám sát |
| Thu hồi truy cập | Phiên hoặc quyền nào cần chấm dứt? | Rotation chỉ là một phần |

Có LAPS không phải lý do để duy trì quyền local admin thường trực cho mọi người dùng. Quản lý mật khẩu và loại bỏ đặc quyền không cần thiết là hai biện pháp bổ trợ nhau.

## 3. Windows LAPS và Microsoft LAPS cũ

Tên “LAPS” có thể chỉ hai thế hệ giải pháp.

**Microsoft LAPS cũ**, thường gọi là legacy LAPS, dùng cơ chế client và các thuộc tính AD tương ứng. Khi khảo sát môi trường cũ, có thể gặp `ms-Mcs-AdmPwd` và `ms-Mcs-AdmPwdExpirationTime`.

**Windows LAPS** là cơ chế tích hợp trong các phiên bản Windows phù hợp, với bộ chính sách, công cụ PowerShell và khả năng lưu trữ riêng. Tùy nền tảng và cấu hình, nó có thể sao lưu vào AD DS hoặc Microsoft Entra ID. Với AD DS, dữ liệu sử dụng họ thuộc tính `msLAPS-*`; khả năng mã hóa và lịch sử mật khẩu cần các điều kiện tương ứng.

Không coi hai thế hệ là hoàn toàn tương đương:

- Có dữ liệu legacy không chứng minh Windows LAPS đang xử lý chính sách mới.
- Đọc được mật khẩu legacy không chứng minh có thể giải mã mật khẩu Windows LAPS.
- Công cụ, thuộc tính, quyền và hành vi phải khớp với thế hệ đang triển khai.
- Cần xác định thành phần thực sự quản lý tài khoản và nguồn mật khẩu hiện hành.

Khi di chuyển, dùng nhóm thử nghiệm riêng, kiểm tra tương tác với cấu hình cũ và xác nhận cơ chế có hiệu lực. Tránh để hai công cụ độc lập cùng thay mật khẩu của một tài khoản.

Các ví dụ trong bài sử dụng Windows LAPS. Khả năng phụ thuộc phiên bản Windows, mức chức năng miền và phương thức quản lý phải được đối chiếu với môi trường triển khai trước khi đưa vào production.

## 4. Vòng đời mật khẩu

Một vòng đời vận hành điển hình:

1. Thiết bị nhận chính sách và xác định tài khoản cần quản lý.
2. Thành phần LAPS trên máy xử lý chính sách, tạo hoặc thay mật khẩu khi đủ điều kiện.
3. Thiết bị sao lưu dữ liệu mật khẩu vào đích được cấu hình.
4. Người được ủy quyền truy xuất mật khẩu theo nhu cầu đã phê duyệt.
5. Người đó dùng tài khoản trên đúng máy, trong phạm vi công việc.
6. Mật khẩu được đổi theo lịch, sau sử dụng hoặc theo yêu cầu xử lý sự cố.
7. Người vận hành xác minh kết quả, lưu bằng chứng và kết thúc quyền truy cập tạm thời nếu có.

Thiết bị phải thực sự xử lý chính sách để hoàn tất phần thay đổi phía máy. Sửa một thuộc tính trong thư mục không đồng nghĩa mật khẩu trên máy đổi ngay.

### 4.1. Bốn trạng thái dễ nhầm

| Trạng thái | Ý nghĩa | Chưa chứng minh |
|---|---|---|
| Chính sách đã được gán | Thiết bị thuộc phạm vi cấu hình | Máy đã nhận và áp dụng thành công |
| Có mật khẩu trong kho lưu | Tồn tại dữ liệu sao lưu | Dữ liệu chắc chắn khớp trạng thái máy hiện tại |
| Đã yêu cầu hết hạn | Đã tạo điều kiện cho rotation | Mật khẩu trên máy đã được đổi |
| Rotation và backup được xác nhận | Chu kỳ xử lý có kết quả kiểm chứng | Mọi phiên đăng nhập cũ đã chấm dứt |

Máy offline, restore từ snapshot hoặc gặp lỗi kết nối có thể làm sai giả định về thời điểm cập nhật. Quy trình phải xác minh cả kết quả tại thiết bị và nơi sao lưu.

### 4.2. Đổi mật khẩu không tự thu hồi mọi phiên

Đổi mật khẩu làm bí mật cũ không còn phù hợp cho lần xác thực tiếp theo khi mật khẩu mới có hiệu lực. Nó không bảo đảm đóng mọi phiên đã đăng nhập, token đã cấp hoặc kết nối đang tồn tại.

Nếu mục tiêu là chấm dứt truy cập, cần kiểm tra phiên, tiến trình và các cơ chế thu hồi liên quan. Hành động sau xác thực của Windows LAPS có thể hỗ trợ tùy nền tảng và cấu hình; phải kiểm thử hành vi cụ thể trước khi dựa vào chúng.

## 5. Chọn nơi sao lưu

### 5.1. AD DS

Trong mô hình AD DS, dữ liệu gắn với đối tượng máy tính. Cần chuẩn bị schema, quyền để máy cập nhật dữ liệu của chính nó và quyền cho các nhóm vận hành.

Thiết kế cần trả lời:

- Máy nằm trong OU nào, chính sách bao phủ đúng phạm vi không?
- Máy có quyền ghi các thuộc tính LAPS cần thiết không?
- Nhóm nào được đọc dữ liệu và nhóm nào được giải mã?
- Quyền kế thừa và các quyền quản trị rộng ảnh hưởng thế nào?
- Khi không truy cập được AD, quy trình phục hồi hoạt động ra sao?

Windows LAPS có thể lưu mật khẩu AD dưới dạng mã hóa hoặc không mã hóa ở cấp thuộc tính, tùy cấu hình. Mã hóa mật khẩu yêu cầu mức chức năng miền phù hợp, tối thiểu Windows Server 2016, cùng cấu hình giải mã hợp lệ.

Mã hóa tăng thêm một ranh giới bảo vệ, nhưng không biến một miền đã bị chiếm quyền quản trị thành kho bí mật độc lập và an toàn tuyệt đối. Vẫn cần bảo vệ danh tính quản trị, backup AD và các cơ chế kiểm soát quyền.

Các thuộc tính thường gặp:

| Thuộc tính | Vai trò |
|---|---|
| `msLAPS-PasswordExpirationTime` | Thời điểm hết hạn dùng trong điều phối vòng đời |
| `msLAPS-Password` | Dữ liệu mật khẩu khi dùng cơ chế lưu không mã hóa của Windows LAPS |
| `msLAPS-EncryptedPassword` | Dữ liệu mật khẩu đã mã hóa |

Không đưa giá trị thuộc tính chứa mật khẩu vào báo cáo kiểm kê thông thường. Báo cáo trạng thái chỉ cần thiết bị, thời gian, chính sách và kết quả.

### 5.2. Microsoft Entra ID

Với kiểu thiết bị và mô hình join được hỗ trợ, Windows LAPS có thể sao lưu mật khẩu vào Microsoft Entra ID. Cấu hình tenant, chính sách thiết bị và quyền truy xuất phải được thiết kế đồng bộ.

Cần kiểm tra:

- Kiểu join có phù hợp với phương thức sao lưu không?
- Tenant đã cho phép khả năng cần dùng và thiết bị đã nhận chính sách chưa?
- Người hỗ trợ có quyền đọc credential hay chỉ được xem thông tin thiết bị?
- Quyền có thể được giới hạn phạm vi và kích hoạt tạm thời không?
- Sự kiện truy xuất và thay đổi cấu hình có được thu thập không?

Xem danh sách thiết bị và đọc mật khẩu local administrator là hai năng lực khác nhau về mức độ nhạy cảm.

### 5.3. Hybrid join không có nghĩa sao lưu kép

Một thiết bị hybrid joined không vì thế mà tự có hai bản sao lưu mật khẩu đồng thời. Chính sách sao lưu của Windows LAPS chọn một đích cho cấu hình đang áp dụng.

Phải biết nguồn nào thực sự chứa mật khẩu hiện hành. Không xây dựng quy trình dựa trên giả định “AD không có thì chắc Entra có” khi chưa kiểm chứng.

## 6. Xác định tài khoản được quản lý

### 6.1. Tài khoản tích hợp hay tài khoản riêng?

Có thể chọn Administrator tích hợp hoặc một tài khoản local administrator riêng phù hợp với thiết kế tổ chức.

Với tài khoản tích hợp, cần hiểu cơ chế nhận diện của chính sách khi tài khoản bị đổi tên. Với tài khoản riêng, phải bảo đảm tài khoản tồn tại và có trạng thái phù hợp.

**Chỉ cấu hình tên tài khoản không mặc nhiên tạo tài khoản trên mọi phiên bản Windows.** Khả năng tự động tạo hoặc quản lý tài khoản chỉ có trên nền tảng phù hợp và khi cấu hình tương ứng được bật. Nếu không dùng khả năng đó, việc tạo tài khoản thuộc quy trình provisioning riêng.

Quản lý mật khẩu thành công cũng không chứng minh tài khoản có thể đăng nhập bằng mọi phương thức. Còn phải xét trạng thái enabled, quyền đăng nhập, chính sách xác thực và đường kết nối.

### 6.2. Không bỏ sót các local admin khác

Không giả định một cấu hình Windows LAPS sẽ tự luân chuyển mật khẩu của mọi tài khoản local administrator trên máy.

| Tài khoản ví dụ | Trạng thái | Việc cần làm |
|---|---|---|
| Administrator tích hợp | Được LAPS quản lý | Kiểm tra đúng tài khoản, chính sách và backup |
| `support-old` | Tài khoản cũ dùng chung mật khẩu | Xác minh owner, loại bỏ hoặc quản lý riêng |
| `vendor-maint` | Nhà cung cấp sử dụng | Đánh giá nhu cầu, thời hạn và đường truy cập |

Nếu chỉ bảo vệ tài khoản đầu tiên nhưng giữ các tài khoản khác với mật khẩu dùng chung, đường di chuyển ngang vẫn tồn tại.

### 6.3. Không dùng tài khoản LAPS làm service account

Dịch vụ, scheduled task hoặc automation phụ thuộc mật khẩu của tài khoản này có thể lỗi sau rotation.

Cần dùng danh tính dịch vụ và cơ chế quản lý credential phù hợp với workload. Không kéo dài vô hạn tuổi mật khẩu LAPS chỉ để duy trì một phụ thuộc dịch vụ sai thiết kế.

## 7. Thiết kế chính sách

Chính sách cần bao phủ nhiều hơn độ dài mật khẩu.

| Nhóm cấu hình | Quyết định cần đưa ra |
|---|---|
| Đích sao lưu | AD DS hay Entra ID |
| Tài khoản | Tài khoản nào được quản lý, cách tạo và duy trì |
| Đặc tính mật khẩu | Độ dài, quy tắc sinh và tương thích công cụ hỗ trợ |
| Tuổi mật khẩu | Chu kỳ đổi và xử lý thiết bị vắng mặt lâu |
| Bảo vệ dữ liệu AD | Mã hóa, principal giải mã, lịch sử nếu cần |
| Sau xác thực | Khoảng chờ và hành động được hỗ trợ |
| Vận hành | Ai được đọc, ai được yêu cầu rotation, cách lưu bằng chứng |

### 7.1. Tuổi mật khẩu theo rủi ro

Tuổi mật khẩu cần cân bằng mức độ nhạy cảm, khả năng thiết bị offline và yêu cầu hỗ trợ.

Ví dụ, tổ chức có thể chọn chu kỳ vài tuần cho workstation và chính sách khác cho máy nhạy cảm. Đây là lựa chọn minh họa, không phải một giá trị áp dụng cho mọi môi trường.

Không dùng chu kỳ ngắn để che giấu quyền đọc quá rộng. Nếu quá nhiều người luôn có thể đọc mật khẩu hiện hành, thay đổi nhanh chỉ giảm một phần thời gian tồn tại của bản sao cũ.

### 7.2. Rotation theo lịch và sau sử dụng

Rotation theo lịch giới hạn tuổi của bí mật. Rotation sau sử dụng giảm thời gian một mật khẩu đã được con người biết tiếp tục còn giá trị.

Tùy nền tảng, Windows LAPS có cơ chế post-authentication action sau khi phát hiện việc sử dụng tài khoản được quản lý. Cần kiểm tra sự kiện nào được phát hiện, thời gian chờ và hành động được hỗ trợ.

Đọc mật khẩu từ thư mục không đồng nghĩa thiết bị đã nhận biết một lần đăng nhập. Đổi mật khẩu và kết thúc phiên cũng không phải cùng một thao tác.

Các hành động sau xác thực có thể ảnh hưởng phiên quản trị và công việc đang chạy. Phải thử với phương thức hỗ trợ thật, bao gồm console và các công cụ remote support được tổ chức cho phép.

### 7.3. Tránh nguồn chính sách mâu thuẫn

Thiết bị có thể nhận cấu hình từ GPO, MDM hoặc cơ chế khác. Khi có nhiều nguồn, phải hiểu cách Windows LAPS lựa chọn chính sách trong môi trường đó.

Không kết luận cấu hình có hiệu lực chỉ từ ảnh chụp một GPO hoặc trang quản trị. Cần kiểm tra trạng thái tại thiết bị, sự kiện xử lý và bản sao lưu tương ứng.

## 8. Least privilege cho quyền truy xuất

### 8.1. Tách năng lực vận hành

Nên phân biệt ba năng lực:

1. **Xem trạng thái**: biết thiết bị có chính sách, backup hoặc lỗi nào.
2. **Truy xuất mật khẩu**: nhận credential có thể cho quyền quản trị trên thiết bị.
3. **Yêu cầu hết hạn**: tác động vòng đời mật khẩu theo quyền được giao.

Quyền yêu cầu hết hạn không tự động là quyền đọc. Người đọc mật khẩu cũng không mặc nhiên cần quyền sửa toàn bộ chính sách triển khai.

Helpdesk phụ trách workstation trong một OU không nên được đọc mật khẩu của server hoặc máy quản trị Tier 0.

### 8.2. Quyền đọc và giải mã trong AD

Với mật khẩu được mã hóa, cần xét cả quyền truy cập dữ liệu và danh tính có thể giải mã. Hai lớp này phải được cấu hình và kiểm tra cùng nhau.

Có quyền đọc thuộc tính không có nghĩa luôn lấy được plaintext nếu không có khả năng giải mã phù hợp. Cấu hình principal giải mã cũng không thay thế kiểm soát ACL hoặc quản trị nhóm.

Các quyền như “All Extended Rights”, quyền kế thừa rộng và quyền quản trị đối tượng có thể làm phạm vi thực tế lớn hơn dự kiến. Không chỉ xem nhóm đọc LAPS vừa tạo; phải kiểm tra quyền hữu hiệu và đường cấp quyền.

### 8.3. Quyền tạm thời vẫn cần rotation

Có thể yêu cầu người hỗ trợ kích hoạt quyền đọc trong thời gian ngắn, liên kết với ticket và giới hạn phạm vi.

Tuy nhiên, quyền hết hạn không làm bí mật đã đọc tự biến mất khỏi trí nhớ, clipboard hoặc một bản sao ngoài kiểm soát. Rotation và vệ sinh môi trường hỗ trợ vẫn cần thiết.

Khi đổi membership trong AD, phải xét token và phiên đăng nhập hiện có. Xóa một người khỏi nhóm không có nghĩa mọi quyền và mọi phiên cũ bị thu hồi tức thì.

## 9. Ví dụ triển khai Windows LAPS với AD DS

Các lệnh sau minh họa miền giả định `corp.example`. Thay tên OU, nhóm và máy bằng đối tượng được phê duyệt trong môi trường thực tế.

Đây là các thao tác có thể thay đổi schema, quyền hoặc vòng đời credential. Thực hiện trong lab hoặc change đã được tổ chức cho phép, bằng tài khoản có quyền phù hợp với từng việc.

### 9.1. Chuẩn bị schema và self permission

Mở rộng schema có phạm vi toàn forest, cần nằm trong kế hoạch thay đổi hạ tầng.

~~~powershell
# Thực hiện trong quy trình chuẩn bị AD đã được phê duyệt.
Update-LapsADSchema

# Cho máy trong OU cập nhật dữ liệu LAPS của chính nó.
Set-LapsADComputerSelfPermission `
    -Identity 'OU=Workstations,DC=corp,DC=example'
~~~

Cấp self permission không thay thế chính sách tại máy và không chứng minh tất cả máy đã backup. Vẫn phải triển khai cấu hình và kiểm tra kết quả.

### 9.2. Ủy quyền theo nhóm

Giả sử tổ chức đã có:

- `CORP\GG-LAPS-Workstation-Readers`: được truy xuất theo quy trình.
- `CORP\GG-LAPS-Workstation-Resetters`: được yêu cầu hết hạn.

~~~powershell
Set-LapsADReadPasswordPermission `
    -Identity 'OU=Workstations,DC=corp,DC=example' `
    -AllowedPrincipals 'CORP\GG-LAPS-Workstation-Readers'

Set-LapsADResetPasswordPermission `
    -Identity 'OU=Workstations,DC=corp,DC=example' `
    -AllowedPrincipals 'CORP\GG-LAPS-Workstation-Resetters'
~~~

Nếu bật mã hóa AD, cần cấu hình principal giải mã phù hợp trong chính sách Windows LAPS. Hai lệnh ủy quyền trên không tự hoàn tất toàn bộ cấu hình mã hóa và giải mã.

Tên nhóm “Readers” không chứng minh phạm vi đã an toàn. Cần kiểm tra membership, owner, quyền sửa membership và quy trình cấp quyền.

### 9.3. Khảo sát quyền mở rộng

~~~powershell
Find-LapsADExtendedRights `
    -Identity 'OU=Workstations,DC=corp,DC=example'
~~~

Kết quả giúp phát hiện principal có quyền mở rộng trong phạm vi khảo sát. Cần đánh giá thêm kế thừa, nhóm lồng nhau và các quyền cho phép sửa ACL hoặc đối tượng.

Kiểm thử bằng người chỉ có vai trò được ủy quyền: xác nhận họ truy xuất được máy trong phạm vi và bị từ chối ở phạm vi không được phép. Không dùng Domain Admin cho mọi kiểm thử vì quyền rộng có thể che mất lỗi ủy quyền.

### 9.4. Áp dụng chính sách trên nhóm thử nghiệm

Chính sách cần chỉ rõ đích sao lưu, tài khoản, đặc tính mật khẩu, tuổi mật khẩu, mã hóa và hành động sau xác thực.

Nếu dùng tài khoản tùy chỉnh mà không dùng cơ chế tự tạo được hỗ trợ, phải chuẩn bị tài khoản qua quy trình riêng trước khi kiểm tra rotation.

Trên thiết bị thử nghiệm, trong phiên có quyền phù hợp:

~~~powershell
Invoke-LapsPolicyProcessing
~~~

Lệnh yêu cầu xử lý chính sách; không tự chứng minh mọi bước thành công. Kiểm tra kết quả và kênh nhật ký `Microsoft-Windows-LAPS/Operational`.

Không ép xử lý lặp trên hàng nghìn máy khi chưa hiểu lỗi. Nguồn chính sách, quyền hoặc kết nối sai sẽ không được sửa chỉ bằng cách chạy lại nhiều lần.

## 10. Quy trình hỗ trợ có kiểm soát

Tình huống: kỹ thuật viên cần sửa cấu hình trên `WIN-APP-017` mà tài khoản thông thường không đủ quyền.

### 10.1. Trước khi lấy mật khẩu

Cần có ticket, đúng thiết bị, phạm vi thao tác, điều kiện phê duyệt và kênh hỗ trợ phù hợp. Người vận hành cần kế hoạch kết thúc phiên và rotation sau sử dụng.

Xác minh đối tượng máy chính xác, tránh lấy mật khẩu của đối tượng cũ có tên tương tự hoặc đối tượng trước khi máy được cài lại.

### 10.2. Truy xuất trong phiên được phép xử lý bí mật

Ví dụ với AD DS:

~~~powershell
Get-LapsADPassword -Identity 'WIN-APP-017' -AsPlainText
~~~

`-AsPlainText` yêu cầu trả mật khẩu ở dạng đọc được khi người gọi có quyền và dữ liệu có thể được giải mã phù hợp. Đây là thao tác làm lộ bí mật vào phiên hỗ trợ.

Không dùng ví dụ trong terminal mà stdout, transcript hoặc ảnh ghi phiên có thể phát tán mật khẩu. Sử dụng kênh được tổ chức thiết kế để bảo vệ hoặc che bí mật trong khi vẫn giữ bằng chứng truy xuất. Không tự tắt cơ chế audit bắt buộc để thực hiện thao tác.

Không xuất kết quả vào CSV, gửi qua chat, dán vào ticket hoặc đặt mật khẩu trong đối số dòng lệnh. Ticket cần ghi **ai truy xuất, lúc nào, cho máy nào, để làm gì**, không cần chứa mật khẩu.

### 10.3. Sử dụng đúng ngữ cảnh

Khi dùng tài khoản local, chỉ rõ ngữ cảnh phù hợp với công cụ, chẳng hạn `WIN-APP-017\Administrator` hoặc cách biểu diễn tài khoản cục bộ mà công cụ hỗ trợ.

Có mật khẩu không có nghĩa luôn RDP hoặc quản trị từ xa được. Đường truy cập còn phụ thuộc quyền đăng nhập, firewall, chính sách xác thực và các hạn chế khác.

Không mở rộng quyền đăng nhập hoặc tắt kiểm soát bảo mật chỉ để “cho LAPS hoạt động”. LAPS cung cấp credential; đường quản trị vẫn phải tuân thủ kiến trúc được thiết kế.

### 10.4. Kết thúc và yêu cầu rotation

Sau công việc, kết thúc phiên và xử lý bí mật tạm theo quy định. Nếu quy trình yêu cầu, đánh dấu mật khẩu cần hết hạn trong AD:

~~~powershell
Set-LapsADPasswordExpirationTime -Identity 'WIN-APP-017'
~~~

Thao tác cập nhật expiration để thiết bị xử lý tiếp. **Nó không trực tiếp đăng nhập vào máy và đổi mật khẩu ngay.**

Nếu đang vận hành trên chính thiết bị và có quyền phù hợp, có thể yêu cầu reset bằng:

~~~powershell
Reset-LapsPassword
~~~

Xác minh kết quả xử lý và backup. Không ghi “đã rotate” chỉ vì lệnh được gửi hoặc ticket đã đổi trạng thái.

Rotation cũng không thay thế việc kiểm tra phiên còn tồn tại. Với mục tiêu thu hồi truy cập, cần xử lý cả phiên và token phù hợp.

### 10.5. Bằng chứng đóng ticket

Ghi nhận thiết bị, tài khoản, người truy xuất, phê duyệt, thời gian làm việc, yêu cầu rotation và kết quả xác nhận.

Nếu chưa hoàn tất, ghi rõ lỗi, owner và bước xử lý tiếp. Không truy xuất thêm plaintext chỉ để chụp ảnh chứng minh mật khẩu đã đổi; ưu tiên thời gian, trạng thái và sự kiện không chứa bí mật.

## 11. Giám sát và bằng chứng kiểm toán

### 11.1. Kết nối ba lớp

| Lớp | Bằng chứng cần quan sát |
|---|---|
| Thiết bị | Xử lý chính sách, rotation, backup, lỗi, hành động sau xác thực |
| Kho lưu và danh tính | Người đọc credential, thay đổi quyền, nhóm và chính sách |
| Hoạt động quản trị | Đăng nhập và công việc bằng tài khoản local |

Nhật ký LAPS tại máy không tự chứng minh ai đọc mật khẩu trong AD hoặc Entra. Sự kiện đọc credential cũng không chứng minh người đó đăng nhập thành công.

Với AD DS, audit việc truy cập thuộc tính phụ thuộc cấu hình audit, SACL và thu thập sự kiện tại nơi phù hợp. Không giả định mọi lần đọc mật khẩu đều có log chỉ vì LAPS đã bật.

### 11.2. Tín hiệu đáng điều tra

- Một người đọc mật khẩu của nhiều máy trong thời gian ngắn.
- Truy xuất ngoài giờ hoặc thiếu ticket phù hợp.
- Nhóm đọc LAPS được thêm thành viên ngoài quy trình.
- OU nhạy cảm kế thừa quyền rộng ngoài thiết kế.
- Máy không backup hoặc rotate quá ngưỡng vận hành.
- Đổi đích sao lưu, tắt mã hóa hoặc đổi principal giải mã ngoài change.
- Tài khoản LAPS được sử dụng như tài khoản làm việc thường ngày.

Cảnh báo nên gắn ngữ cảnh thiết bị, mức độ nhạy cảm và phạm vi phụ trách. Không cần thu thập plaintext để xây các cảnh báo này.

### 11.3. Chỉ số hữu ích

Theo dõi tỷ lệ thiết bị áp dụng chính sách và có backup hợp lệ; tỷ lệ rotation thành công; số máy ngoại lệ; tài khoản admin ngoài quản lý; số người có quyền đọc thường trực; tỷ lệ truy xuất gắn ticket và có xác minh sau sử dụng.

“Tất cả OU đã link GPO” chỉ phản ánh việc gán cấu hình, chưa chứng minh triển khai thành công trên thiết bị.

## 12. Chẩn đoán lỗi

### 12.1. Không có mật khẩu sao lưu

Kiểm tra theo thứ tự:

1. Nền tảng có hỗ trợ khả năng cần dùng không?
2. Có đang xem đúng thiết bị và đối tượng trong kho lưu không?
3. Chính sách nào có hiệu lực, chọn đích sao lưu nào?
4. Tài khoản được quản lý tồn tại và phù hợp không?
5. Thiết bị có kết nối và quyền ghi cần thiết không?
6. Nhật ký xử lý cho biết lỗi ở bước nào?

Không đặt một mật khẩu dùng chung cho cả nhóm máy để “tạm hoàn tất triển khai”.

### 12.2. Có dữ liệu nhưng không đọc được

Phân biệt thiếu quyền đọc, thiếu khả năng giải mã, principal sai, membership/token chưa phù hợp, công cụ sai thế hệ hoặc nhầm đích sao lưu.

Sửa đúng lớp cấu hình và quyền. Cấp Domain Admin cho helpdesk để vượt lỗi không phải giải pháp ủy quyền phù hợp.

### 12.3. Có mật khẩu nhưng đăng nhập thất bại

Có thể chọn nhầm domain thay vì tài khoản local, tài khoản bị vô hiệu hóa, phương thức đăng nhập không được phép hoặc bản sao lưu không khớp sau restore/reimage.

Kiểm tra tên máy, tài khoản, nguồn mật khẩu, thời gian backup, trạng thái thiết bị và đường truy cập. Không thử nhiều credential đặc quyền trên một máy chưa xác định rõ trạng thái.

Nếu nghi mật khẩu không khớp, dùng kênh phục hồi được phê duyệt để đưa máy về trạng thái quản lý hợp lệ.

### 12.4. Yêu cầu hết hạn nhưng chưa đổi

Máy có thể offline, chưa xử lý chính sách hoặc gặp lỗi quyền và backup. Expiration tại kho lưu không thay thế bằng chứng xử lý tại máy.

Giữ công việc ở trạng thái chờ xác minh, nêu nguyên nhân và owner. Không coi yêu cầu đã gửi là rotation hoàn tất.

### 12.5. Restore, clone và cài lại

Restore có thể đưa mật khẩu local về trạng thái cũ trong khi kho lưu chứa bản mới. Reimage có thể tạo tài khoản hoặc đối tượng máy khác với giả định.

Quy trình cấp phát và khôi phục phải kiểm tra LAPS trở lại trạng thái hợp lệ và không giữ mật khẩu từ image dùng chung. Nếu dùng lịch sử mật khẩu được hỗ trợ, quyền đọc lịch sử cũng phải được kiểm soát như quyền đọc bí mật hiện hành.

## 13. Break-glass và ứng phó sự cố

LAPS có thể hỗ trợ truy cập local khi đường quản trị thông thường gặp lỗi. Tính sẵn sàng phụ thuộc khả năng truy xuất kho lưu, quyền người xử lý và trạng thái đồng bộ gần nhất.

Nếu đường truy xuất phụ thuộc hạ tầng đang hỏng, chỉ nói “đã có LAPS” chưa đủ cho break-glass. Cần diễn tập mất kết nối, không truy cập được AD/Entra hoặc máy lâu không online.

Không giải quyết bằng cách xuất toàn bộ mật khẩu ra bảng tính. Nếu tổ chức dùng cơ chế escrow bổ sung được phê duyệt, cơ chế đó cần mã hóa, kiểm soát truy cập, thời hạn lưu, audit và cập nhật phù hợp.

Khi một máy bị chiếm quyền:

- Không đưa credential quản trị miền giá trị cao vào máy nghi bị kiểm soát.
- Cô lập và điều tra theo quy trình incident response.
- Xác định mật khẩu LAPS có bị đọc hoặc lộ trong phiên hỗ trợ không.
- Rotation và xác minh trong phạm vi ảnh hưởng.
- Xử lý phiên, token và persistence riêng.
- Rà soát quyền đọc nếu nguồn lộ là tài khoản hỗ trợ hoặc kho quản trị.

Mật khẩu riêng từng máy hạn chế tái sử dụng credential giữa các máy; nó không loại bỏ quyền kiểm soát của kẻ đã có đặc quyền cao trên một thiết bị.

## 14. Tình huống thực hành

### 14.1. Bối cảnh và thiết kế

Công ty có 600 workstation. Image cũ chứa một tài khoản local admin dùng chung mật khẩu. Helpdesk cần hỗ trợ một số tác vụ; server do đội khác phụ trách.

Mục tiêu là chấm dứt mật khẩu dùng chung, hỗ trợ được khi cần và có bằng chứng kiểm toán.

Tổ chức chọn tài khoản phù hợp để Windows LAPS quản lý, sao lưu vào AD DS và bật mã hóa khi đáp ứng điều kiện. Helpdesk chỉ được đọc trong phạm vi workstation; nhóm server có quyền riêng.

Máy chưa áp dụng chính sách, tài khoản admin dư thừa và máy lâu không online được theo dõi như ngoại lệ cần xử lý, không loại khỏi mẫu số báo cáo để tăng tỷ lệ hoàn thành.

Quyền đọc gắn vai trò, thời gian và ticket. Sau sử dụng, quy trình yêu cầu rotation và kiểm tra kết quả.

### 14.2. Bài kiểm thử

1. Chọn nhóm máy đại diện cho phiên bản và điều kiện sử dụng.
2. Gán chính sách, kiểm tra tài khoản, backup và nhật ký.
3. Dùng người hỗ trợ đúng quyền để lấy mật khẩu máy thử nghiệm.
4. Xác nhận người không có quyền bị từ chối và helpdesk không đọc được server.
5. Dùng đường hỗ trợ được phép, thực hiện thao tác nhỏ rồi kết thúc phiên.
6. Yêu cầu rotation, xác minh kết quả và kiểm tra hành vi phiên cũ.
7. Thử máy offline hoặc lỗi quyền có kiểm soát để kiểm chứng chẩn đoán.
8. Kiểm tra ticket, log và công cụ ghi phiên có phát tán bí mật không.

Không cần hiển thị hai mật khẩu cạnh nhau để chứng minh khác nhau. Có thể đánh giá vòng đời bằng thời gian, kết quả xử lý và bài kiểm thử xác thực trong lab được kiểm soát.

### 14.3. Điều kiện chấp nhận

- Máy thuộc phạm vi có chính sách và backup được xác nhận.
- Không còn mật khẩu dùng chung hoặc admin bị bỏ quên trong phạm vi nghiệm thu.
- Quyền đọc/giải mã đúng phạm vi và được thử bằng vai trò thực tế.
- Rotation sau sử dụng có kết quả kiểm chứng.
- Log liên kết được truy xuất, đăng nhập và ticket mà không lưu plaintext không cần thiết.
- Quy trình phục hồi được diễn tập và có owner cho ngoại lệ.

Chỉ tạo GPO hoặc thấy thuộc tính có dữ liệu chưa đủ để xác nhận các điều kiện trên.

## 15. Những sai lầm thường gặp

| Sai lầm | Rủi ro | Hướng xử lý |
|---|---|---|
| Tiếp tục dùng chung mật khẩu | Bí mật có thể dùng trên nhiều máy | Quản lý riêng từng thiết bị |
| Cho helpdesk quyền đọc toàn miền | Một danh tính bị lộ ảnh hưởng nhiều tầng | Giới hạn phạm vi và thời gian |
| Dùng mã hóa thay cho ACL | Bỏ sót quyền đọc, giải mã hoặc quản trị | Đánh giá các lớp quyền cùng nhau |
| Chỉ định tài khoản chưa tồn tại | Không quản lý được đúng đối tượng | Chuẩn bị tài khoản phù hợp |
| Dùng tài khoản LAPS chạy dịch vụ | Rotation làm hỏng workload | Tách danh tính dịch vụ |
| Ghi mật khẩu vào ticket | Tăng bản sao và người tiếp cận | Chỉ ghi metadata, bằng chứng |
| Gọi cập nhật expiration là rotation | Bỏ qua máy offline hoặc lỗi | Xác nhận xử lý và backup |
| Cho rằng đổi mật khẩu đóng phiên | Phiên/token cũ có thể còn | Thu hồi phiên riêng |
| Chỉ thử bằng Domain Admin | Che mất lỗi least privilege | Thử bằng vai trò được giao |
| Giữ quyền local admin vì đã có LAPS | Đặc quyền không cần thiết còn nguyên | Phối hợp least privilege/elevation |

## 16. Câu hỏi tự đánh giá

**Hai máy có tài khoản Administrator cùng tên có cùng danh tính không?**

Không. Đó là hai tài khoản local khác nhau. Rủi ro tái sử dụng xuất hiện khi bí mật xác thực được dùng chung.

**Có LAPS thì có thể cho mọi người dùng giữ local admin không?**

Không. Quyền quản trị vẫn cần được cấp theo nhu cầu và thời gian phù hợp.

**Đặt expiration về hiện tại chứng minh gì?**

Nếu thao tác thành công, yêu cầu hết hạn đã được cập nhật tại kho lưu. Cần thiết bị xử lý và có bằng chứng kết quả trước khi kết luận mật khẩu đã đổi.

**Được đọc dữ liệu AD có chắc đọc được plaintext đã mã hóa không?**

Không. Cần xét khả năng giải mã, principal được phép và điều kiện thực tế.

**Hybrid joined có tự backup vào cả AD DS lẫn Entra ID không?**

Không. Phải kiểm tra đích được cấu hình và trạng thái thực tế.

**Vì sao cần rotation sau khi kỹ thuật viên dùng mật khẩu?**

Để giới hạn thời gian một bí mật đã tiết lộ tiếp tục có giá trị. Rotation không thay thế kết thúc phiên.

**Báo cáo kiểm toán có cần chứa mật khẩu không?**

Không. Cần người truy xuất, thiết bị, mục đích, thời gian, quyền và kết quả; plaintext chỉ làm tăng rủi ro.

**LAPS có loại bỏ mã độc trên máy đã bị chiếm quyền không?**

Không. Việc cô lập, điều tra, xử lý persistence và phục hồi vẫn cần quy trình riêng.

LAPS đạt giá trị PAM khi mật khẩu riêng từng thiết bị đi cùng quyền truy xuất hẹp, mục đích rõ ràng, rotation được xác minh và bằng chứng đủ để truy vết.
