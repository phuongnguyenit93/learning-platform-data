# Tách domain admin khỏi server admin trong PAM

## 1. Mục tiêu của việc tách hai vai trò

Trong môi trường Active Directory Domain Services, quản trị domain và quản trị member server có phạm vi ảnh hưởng khác nhau.

**Domain admin** trong bài này chỉ vai trò có quyền quản trị rất cao đối với domain và các thành phần điều khiển danh tính liên quan. Nhóm Domain Admins là một ví dụ quan trọng, nhưng không phải nguồn duy nhất tạo ra quyền ảnh hưởng tương đương.

**Server admin** là vai trò vận hành một tập máy chủ hoặc dịch vụ: cập nhật, cấu hình, chẩn đoán, khởi động dịch vụ và các tác vụ được ủy quyền trên phạm vi đó.

Tách hai vai trò nhằm:

- Không dùng quyền quản trị domain cho công việc member server thường lệ.
- Giảm nơi credential và phiên có quyền cao nhất xuất hiện.
- Hạn chế khả năng một member server bị ảnh hưởng dẫn tới kiểm soát danh tính.
- Tách phạm vi quyền, máy nguồn, công cụ và luồng PAM.
- Giữ khả năng quy trách nhiệm và thu hồi theo từng loại công việc.

Ví dụ, kỹ sư cần khởi động lại một dịch vụ trên APP-A-01 không mặc nhiên cần quyền thay đổi nhóm đặc quyền hoặc policy của domain.

Việc tách không chỉ là tạo hai tên tài khoản. Các đường sử dụng và điều khiển thực tế phải phù hợp với ranh giới đó.

## 2. Domain admin không đồng nghĩa với mọi tài khoản admin

### 2.1. Phạm vi quản trị domain

Trong một domain AD DS thông thường, Domain Admins có mức đặc quyền rất cao. Quyền thực tế còn phụ thuộc cấu hình, ACL, các ủy quyền và cơ chế của môi trường.

Không nên đồng nhất quản trị một domain với mọi quyền trong toàn forest hoặc mọi miền tin cậy khác. Các ranh giới domain, forest và quan hệ trust cần được đánh giá riêng.

Những công việc có thể ảnh hưởng mạnh tới miền danh tính gồm:

- Quản lý thành viên hoặc quyền của nhóm đặc quyền.
- Thay đổi policy áp dụng cho thành phần kiểm soát danh tính.
- Quản trị domain controller và những dependency có thể điều khiển nó.
- Quản lý các nguồn khóa, chứng thư hoặc liên kết danh tính có quyền đáng kể.
- Sửa quyền ủy nhiệm hoặc công cụ có khả năng tạo ra thay đổi trên domain.

Ngay trong phạm vi này cũng cần ủy quyền theo tác vụ. Không phải mọi công việc directory đều cần dùng toàn bộ quyền của Domain Admins.

### 2.2. Phạm vi quản trị server

Server admin có thể cần quyền cao trên máy chủ được giao, nhưng phạm vi đó không nên tự mở rộng sang mọi server hoặc sang control plane danh tính.

Cần xác định:

- Tập server hoặc dịch vụ được quản lý.
- Tác vụ cần thực hiện.
- Quyền local, quyền ứng dụng và quyền nâng cao tương ứng.
- Công cụ triển khai, backup và monitoring liên quan.
- Credential hoặc token mà máy chủ có thể tiếp cận.

Một server admin có toàn quyền OS có thể ảnh hưởng ứng dụng và secret trên server đó. Do đó, đây vẫn là đặc quyền quan trọng, cần PAM và least privilege phù hợp.

### 2.3. Domain controller không phải member server thông thường

Domain controller là máy chủ về mặt triển khai, nhưng chức năng kiểm soát danh tính làm nó có phạm vi ảnh hưởng khác.

Không đưa domain controller vào một nhóm “tất cả server” rồi cho nhóm vận hành member server quản trị toàn bộ theo cùng policy.

Tương tự, một server mang tên backup, management hoặc sync có thể có khả năng tác động tới miền danh tính. Phân loại theo quyền kiểm soát thực tế, không chỉ theo loại OS hoặc tên thư mục inventory.

## 3. Vì sao dùng domain admin trên member server gây rủi ro?

### 3.1. Môi trường có quyền thấp hơn có thể ảnh hưởng phiên quyền cao

Khi dùng danh tính có quyền quản trị domain trên một máy chủ ứng dụng, tổ chức đưa một ngữ cảnh đặc quyền cao vào môi trường có thể do nhiều nhóm quản lý hoặc có bề mặt tiếp xúc rộng hơn.

Tùy loại đăng nhập, giao thức, cơ chế bảo vệ và cấu hình, có thể xuất hiện credential, token, ticket hoặc khả năng sử dụng danh tính. Một thành phần kiểm soát máy chủ cũng có thể tác động tới input, tiến trình hoặc công cụ của phiên.

Không phải mọi kiểu kết nối đều lưu cùng một loại secret. Vì vậy, không nên diễn giải rằng mọi lần đăng nhập đều chắc chắn để lại cùng một credential có thể dùng lại.

Tuy nhiên, giảm việc đưa danh tính quản trị domain tới môi trường server thông thường vẫn là mục tiêu của ranh giới sử dụng đặc quyền.

### 3.2. Quyền rộng che giấu nhu cầu thực tế

Nếu mọi việc đều chạy bằng domain admin, hệ thống khó biết quyền tối thiểu cần cho một tác vụ. Công cụ và script có thể dần phụ thuộc vào quyền rộng không cần thiết.

Sau đó, việc giảm quyền dễ bị hiểu là “làm công việc không chạy”, dù nguyên nhân có thể là chưa xác định đúng quyền cần ủy nhiệm.

### 3.3. Khó giới hạn khi có sự cố

Một credential được dùng trên nhiều server và có quyền rộng ở domain làm tăng phạm vi cần kiểm tra, thu hồi và khôi phục.

Ngược lại, danh tính server admin được giới hạn theo nhóm target giúp thu hẹp một phần phạm vi. Điều đó chỉ có giá trị nếu không còn đường gián tiếp cho server admin sửa control plane danh tính.

## 4. Tách theo quyền kiểm soát, không chỉ theo nhóm

### 4.1. Tư cách thành viên chỉ là một nguồn quyền

Một tài khoản không nằm trong Domain Admins vẫn có thể có khả năng tạo ra quyền tương đương trong một phạm vi, chẳng hạn do:

- Được sửa một nhóm hoặc đối tượng đặc quyền.
- Có quyền reset hoặc thay phương thức xác thực của danh tính nhạy cảm.
- Có thể sửa policy hoặc công cụ áp dụng lên domain controller.
- Quản lý nền tảng chứa máy ảo hoặc dữ liệu phục hồi của thành phần danh tính.
- Có thể phân phối mã chạy với quyền cao trên thành phần đó.
- Quản lý một hệ thống cấp credential được nhiều tài nguyên tin cậy.

Mỗi khả năng cần được đánh giá theo cấu hình thực tế. Không phải mọi server có tên PKI, backup hoặc monitoring đều mặc nhiên có cùng mức ảnh hưởng; điều quan trọng là nó được làm gì.

### 4.2. Lần theo đường điều khiển

Một câu hỏi hữu ích là:

~~~text
Nếu chủ thể A kiểm soát thành phần B,
A có thể làm B thay đổi C theo cách nào?

Nếu C là thành phần điều khiển danh tính,
đường A → B → C phải nằm trong phạm vi đánh giá.
~~~

Ví dụ, một công cụ triển khai có thể chạy mã trên domain controller. Tài khoản quản trị công cụ đó không nên được đánh giá chỉ như một server admin của giao diện web nơi nó đăng nhập.

### 4.3. Ranh giới thường không đối xứng

Miền danh tính có thể phân phối policy hoặc ảnh hưởng quyền trên member server. Tách tier không có nghĩa mọi khả năng quản trị từ domain xuống server tự biến mất.

Mục tiêu là hạn chế việc sử dụng danh tính mạnh ở môi trường ít được bảo vệ hơn, đồng thời không để quyền server admin tạo một đường đi ngược lên control plane danh tính.

Một domain admin có quyền thay đổi chính policy bảo vệ vẫn là chủ thể rất mạnh. Tiering không thay thế việc kiểm soát, giám sát và hạn chế quyền đó.

## 5. Một người có thể có nhiều danh tính theo tác vụ

Ví dụ minh họa:

| Danh tính | Mục đích | Nguồn sử dụng | Phạm vi quyền |
|---|---|---|---|
| an.work | Email và công việc hằng ngày | Máy thường | Không có quyền quản trị đặc biệt theo vai trò này |
| an.server | Vận hành nhóm server ứng dụng A | Môi trường admin cho server | Chỉ target và tác vụ đã được giao |
| an.directory | Công việc quản trị miền danh tính | Môi trường admin phù hợp miền danh tính | Quyền theo tác vụ directory được duyệt |

Tên chỉ là ví dụ. Hệ thống phải liên kết được các danh tính với cùng một con người để quản lý vòng đời và quy trách nhiệm.

Một người có thể được giao cả hai vai trò nếu tổ chức cho phép. Điều đó không loại bỏ nhu cầu tách ngữ cảnh sử dụng, credential và phạm vi phiên.

Nếu một công việc yêu cầu phân tách người thực hiện và người phê duyệt, hai tài khoản của cùng người không trở thành hai người độc lập.

### 5.1. Không dùng chung credential

Không đặt cùng mật khẩu, private key hoặc secret cho các danh tính nhằm tiện chuyển đổi. Một bản sao bị lộ có thể làm suy giảm ranh giới dự kiến.

Tài khoản kỹ thuật ở target cũng cần có owner và mục đích. Không dùng danh tính con người có quyền quản trị domain để chạy dịch vụ hoặc automation lâu dài.

### 5.2. Không đưa trạng thái quyền cao sang môi trường thường

Cần xem xét cookie, token, profile trình duyệt, kho mật khẩu, SSH agent, cấu hình công cụ và các cơ chế đồng bộ.

Tạo tài khoản riêng nhưng sử dụng tất cả trên cùng một OS xử lý email và nội dung bên ngoài chưa đạt cùng mục tiêu với một nguồn quản trị được bảo vệ phù hợp.

## 6. Tách nguồn truy cập và luồng PAM

~~~mermaid
flowchart LR
    U["Cùng một quản trị viên"] --> I1["Danh tính server admin"]
    U --> I2["Danh tính quản trị directory"]
    I1 --> W1["Nguồn admin cho member server"]
    I2 --> W2["Nguồn admin cho miền danh tính"]
    W1 --> P1["Policy và gateway server"]
    W2 --> P2["Policy và gateway directory"]
    P1 --> S["Nhóm member server được giao"]
    P2 --> D["Domain controller và control plane đã phân loại"]
    V1["Credential theo phạm vi server"] --> P1
    V2["Credential theo phạm vi directory"] --> P2
    P1 --> L["Bằng chứng có liên kết danh tính"]
    P2 --> L
~~~

Đây là kiến trúc logic. Có thể dùng nền tảng PAM chung hoặc nhiều thành phần, nhưng ranh giới quyền thực tế cần được xác định.

### 6.1. Nguồn quản trị directory

Nguồn này cần được bảo vệ tương ứng với quyền có thể sử dụng. Cần đánh giá phần mềm, công cụ hỗ trợ từ xa, hệ thống quản lý endpoint, image và quyền phục hồi danh tính.

Không dùng nguồn đó như máy làm việc thường hoặc nơi quản trị member server theo thói quen nếu điều này làm mất ranh giới đã thiết kế.

### 6.2. Nguồn quản trị member server

Nguồn server admin cần đủ công cụ cho nhiệm vụ nhưng không giữ credential hoặc phiên directory admin.

Nếu cần thay đổi directory để phục vụ công việc server, xử lý qua tác vụ ủy nhiệm hoặc một workflow riêng. Không chuyển credential directory admin vào phiên server chỉ để vượt một lỗi thiếu quyền chưa hiểu.

### 6.3. Gateway và vault dùng chung cần được đánh giá

Một gateway có thể lấy secret của cả hai phạm vi sẽ có ảnh hưởng rộng. Quyền quản trị gateway, connector, plugin hoặc vault có thể vượt ranh giới của người dùng thông thường.

Có thể tách connector, kho quyền sử dụng secret, policy hoặc vùng quản lý theo thiết kế. Chỉ tách tên folder trong vault không đủ nếu cùng vai trò quản trị có thể sửa và dùng mọi secret.

Không mặc định cần một sản phẩm riêng cho mỗi tier; cần chứng minh ranh giới thực thi trong kiến trúc được chọn.

## 7. Ủy quyền tác vụ thay vì cấp quyền domain rộng

### 7.1. Công việc server thường lệ

Ví dụ về nhu cầu cần ánh xạ thành quyền cụ thể:

| Công việc | Phạm vi cần tìm hiểu |
|---|---|
| Xem trạng thái dịch vụ | Quyền đọc và truy vấn trên server hoặc ứng dụng |
| Khởi động lại một dịch vụ | Quyền điều khiển dịch vụ đó theo khả năng nền tảng |
| Cài bản cập nhật | Luồng quản lý cập nhật và quyền thực thi tương ứng |
| Thay cấu hình ứng dụng | Quyền trên cấu hình, secret và công cụ triển khai liên quan |
| Quản lý tài khoản local | Phạm vi local và vòng đời credential |
| Đưa máy vào domain theo quy trình | Quyền ủy nhiệm và luồng cấp máy phù hợp |

Bảng không chỉ định rằng mọi tác vụ đều có thể thực hiện bằng một quyền đơn lẻ. Cần kiểm chứng tác vụ thực tế và tác động của các công cụ được dùng.

### 7.2. Công việc directory cũng có thể hẹp hơn

Một tác vụ hỗ trợ danh tính hoặc quản lý một tập đối tượng không mặc nhiên cần toàn bộ quyền domain admin.

Ủy nhiệm phải có phạm vi đối tượng và quyền rõ. Cần đặc biệt chú ý thao tác reset credential, sửa group membership hoặc ACL vì chúng có thể gián tiếp cấp quyền cao hơn.

Không chỉ kiểm tra tác vụ có chạy được. Phải kiểm tra người nhận quyền có thể dùng quyền đó để tác động tới đối tượng đặc quyền ngoài nhiệm vụ hay không.

### 7.3. Xử lý công cụ phụ thuộc quyền rộng

Nếu công cụ chỉ hoạt động khi chạy bằng domain admin, cần xác định vì sao: truy cập tài nguyên nào, gọi API nào, cần quyền gì và có đường triển khai khác không.

Có thể cần sửa công cụ, tách bước, dùng service identity giới hạn hoặc thay quy trình. Không tự coi yêu cầu quyền rộng của một script là căn cứ đủ để bỏ ranh giới tier.

## 8. Hạn chế đăng nhập và đường truy cập

### 8.1. Tách nơi được sử dụng danh tính

Cần quy định loại danh tính nào được đăng nhập hoặc mở phiên tới nhóm tài nguyên nào, từ nguồn nào và bằng giao thức nào.

Ví dụ về ý định:

~~~text
Danh tính quản trị directory:
  chỉ dùng cho tác vụ directory từ nguồn được phép.

Danh tính server admin:
  chỉ dùng cho nhóm member server và tác vụ được giao.

Danh tính thường:
  không tự trở thành nguồn sử dụng credential quản trị.
~~~

Việc thực thi có thể cần phối hợp policy OS, điều kiện PAM, mạng, ứng dụng và công cụ quản lý.

### 8.2. Phân biệt loại đăng nhập

Interactive logon, remote desktop, network access, service và batch có semantics khác nhau. Một hạn chế cho một loại không tự bao phủ mọi loại còn lại.

Khi áp dụng policy, cần kiểm tra group lồng nhau, đối tượng nhận policy và các dependency. Không áp một mẫu deny rộng lên mọi tài khoản rồi vô tình ảnh hưởng account máy, dịch vụ hoặc cơ chế hoạt động của domain.

Các giao thức hạ tầng như xác thực và tra cứu directory phục vụ member server không đồng nghĩa người dùng phải sử dụng danh tính domain admin để vận hành chúng.

### 8.3. Không chỉ bảo vệ RDP hoặc SSH

Web quản trị, API, công cụ triển khai, console hypervisor, remote support và đường ngoài băng có thể tạo tác động tương tự một phiên tương tác.

Tiering cần bao phủ đường điều khiển, không chỉ cổng mạng thường thấy.

Một server admin bị chặn RDP vào domain controller nhưng vẫn sửa được gói triển khai chạy trên nó là một ranh giới chưa hoàn chỉnh.

## 9. JIT, MFA, JEA và credential trong hai phạm vi

### 9.1. JIT cho quyền directory nhạy cảm

Tổ chức có thể thiết kế chỉ kích hoạt quyền cần thiết cho từng công việc và cửa sổ, khi nền tảng hỗ trợ.

Cần xác định điều kiện cấp, người phê duyệt, target, role, thời hạn và cách thu hồi. Không tự thêm mọi người vào một nhóm đặc quyền vĩnh viễn chỉ vì họ có thể cần tác vụ hiếm gặp.

Thay đổi group membership không tự cập nhật ngay mọi token, ticket hoặc phiên đã được tạo. Vòng đời quyền phải được kiểm chứng ở cả cấp mới và phiên hiện hữu.

### 9.2. MFA không thay ranh giới tier

MFA giúp xác thực chủ thể theo yêu cầu, nhưng một domain admin có MFA đăng nhập vào nguồn bị kiểm soát vẫn có thể gặp rủi ro ở phiên và input.

Cần áp dụng MFA cùng nguồn quản trị phù hợp, quyền hẹp và luồng credential được kiểm soát.

### 9.3. JEA ở member server

Có thể giới hạn tác vụ chẩn đoán hoặc vận hành nếu khả năng đích hỗ trợ và được kiểm chứng. Role server admin không nhất thiết phải là toàn quyền OS cho mọi công việc.

Các công cụ được cho phép vẫn cần đánh giá đường mở shell, chỉnh script, tải plugin hoặc truy cập secret khác. Một nhãn “limited operator” không tự tạo giới hạn.

### 9.4. Credential theo từng phạm vi

Vault hoặc broker cần có policy cho phép đúng thành phần dùng đúng credential. Quyền đọc secret, sửa mapping, thay target hoặc gọi khả năng ký đều cần được xem xét.

Không xuất credential directory admin cho người vận hành server chỉ vì họ đang có một phiên PAM hợp lệ ở phạm vi server.

## 10. Các đường ảnh hưởng gián tiếp thường bị bỏ sót

### 10.1. Hypervisor và nền tảng chứa domain controller

Một nền tảng có khả năng tác động tới máy ảo, disk, snapshot hoặc bộ nhớ của thành phần danh tính có thể có ảnh hưởng cao.

Cần đánh giá quyền thực tế và cơ chế bảo vệ. Không phân loại toàn bộ nhóm quản trị nền tảng đó như nhóm server thông thường nếu họ có thể điều khiển domain controller trong phạm vi của mình.

### 10.2. Backup và phục hồi

Quyền đọc, thay hoặc phục hồi dữ liệu của miền danh tính có thể ảnh hưởng tính bí mật và khả năng kiểm soát hệ thống.

Cần xem xét cả kho backup, khóa giải mã, quyền phục hồi, công cụ và tài khoản thực thi. Một role chỉ xem giao diện backup khác với role có thể lấy hoặc phục hồi dữ liệu nhạy cảm.

### 10.3. Triển khai, patch và agent

Một công cụ cài gói hoặc chạy script trên domain controller trở thành một đường điều khiển cần được bảo vệ tương ứng.

Việc agent phục vụ monitoring không tự làm mọi quyền quản trị agent có rủi ro thấp. Cần biết có thể cập nhật mã, cấu hình hoặc chạy tác vụ gì trên host.

### 10.4. Chứng thư, federation và đồng bộ danh tính

Khả năng cấp chứng thư được chấp nhận cho danh tính đặc quyền, sửa cấu hình federation hoặc thay đổi dữ liệu đồng bộ có thể tạo đường tác động tới miền tin cậy.

Phải đánh giá template, ACL, quyền ký, nguồn phát hành và chiều đồng bộ thực tế. Không gắn một nhãn cố định cho mọi thành phần mà bỏ qua cấu hình.

### 10.5. Quản lý PAW và PAM

Hệ thống điều khiển PAW directory admin hoặc sửa policy PAM cho phạm vi directory có thể ảnh hưởng chính nguồn và điều kiện sử dụng quyền cao.

Ranh giới chỉ có ý nghĩa khi các quyền quản lý này không bị để lại trong một nhóm server admin rộng ngoài ý định.

## 11. Policy minh họa

~~~yaml
# Mã giả thể hiện ý định, không phải cấu hình sản phẩm.
access_domains:
  directory_administration:
    identities: approved_directory_admin_identities
    source: verified_directory_admin_environment
    targets: reviewed_directory_control_plane
    role: task_scoped_directory_role
    activation: approved_time_bound_grant
    authentication: accepted_privileged_profile
    credential_use: directory_scope_only

  member_server_administration:
    identities: approved_server_admin_identities
    source: verified_server_admin_environment
    targets: assigned_member_server_group
    role: approved_server_task_role
    activation: policy_controlled_grant
    authentication: accepted_privileged_profile
    credential_use: assigned_server_scope_only

boundaries:
  server_role_cannot_modify_directory_admin_authority: required
  directory_identity_not_used_for_routine_member_server_work: required
  evaluate_management_and_recovery_dependencies: required
  evaluate_direct_and_noninteractive_paths: required

evidence:
  link_person_identity_target_grant_and_session: true
  record_boundary_exceptions_and_expiry: true
~~~

Các dòng boundaries là mục tiêu phải được ánh xạ thành kiểm soát và bằng chứng. Chúng không tự chứng minh mọi ACL, group, policy, công cụ triển khai và đường phục hồi đã đúng.

Nếu nền tảng chỉ hạn chế menu PAM, không được kết luận server role không thể tác động directory qua API hoặc công cụ ngoài menu.

## 12. Ví dụ xuyên suốt: quản trị dịch vụ và thay đổi directory

### 12.1. Bối cảnh

An có nhiệm vụ vận hành ứng dụng A. Một sự cố yêu cầu chẩn đoán dịch vụ trên APP-A-01; một thay đổi khác cần cập nhật quyền của một nhóm đối tượng directory theo quy trình.

An được giao hai vai trò hợp lệ nhưng sử dụng danh tính và nguồn quản trị riêng.

### 12.2. Công việc member server

An dùng danh tính server admin từ nguồn được phép, yêu cầu role chẩn đoán đúng APP-A-01 qua PAM.

Gateway dùng credential trong phạm vi server và giữ liên kết tới An. Role tại đích không cho sửa nhóm đặc quyền hoặc công cụ quản lý domain controller.

Nếu một lệnh báo thiếu quyền directory, An xác định nhu cầu và đi qua tác vụ được ủy nhiệm hoặc workflow khác. Không nhập credential directory admin vào phiên APP-A-01 để thử.

### 12.3. Công việc directory

An chuyển sang môi trường quản trị directory phù hợp và dùng danh tính tương ứng. Yêu cầu nêu đối tượng, thao tác, cửa sổ và phê duyệt cần thiết.

Quyền được cấp theo tác vụ nếu nền tảng hỗ trợ, thay vì mặc định dùng toàn bộ quyền domain admin.

Bằng chứng liên kết người dùng với đúng identity và action. Hai tài khoản của An không được tính như hai người độc lập nếu workflow yêu cầu phê duyệt độc lập.

### 12.4. Một phát hiện gián tiếp

Rà soát cho thấy nhóm server admin có thể sửa gói triển khai chạy trên domain controller. Dù họ không nằm trong Domain Admins, đây vẫn là đường ảnh hưởng cần xử lý.

Nhóm owner phân loại lại phạm vi quản lý, giới hạn quyền phân phối và kiểm chứng kết quả. Chỉ bỏ membership của một nhóm trực tiếp sẽ không giải quyết đường này.

### 12.5. Kết thúc công việc

Grant và phiên được xử lý theo vòng đời riêng. Nếu group membership tạm được gỡ, cần biết token, ticket và phiên nào còn ngữ cảnh cũ.

Đóng yêu cầu không tự chứng minh mọi khả năng sử dụng credential đã hết. Những phần chưa xác nhận cần có trạng thái và owner.

## 13. Lộ trình chuyển từ quyền dùng chung sang ranh giới rõ

### 13.1. Kiểm kê hiện trạng

Xác định:

- Ai đang có quyền domain cao, trực tiếp hoặc gián tiếp.
- Ai quản trị từng nhóm member server.
- Nguồn đăng nhập và nơi credential được sử dụng.
- Tài khoản dịch vụ, job và công cụ phụ thuộc quyền rộng.
- Các đường hypervisor, backup, patch, PAW và PAM.
- Đăng nhập trực tiếp ngoài luồng được quản lý.
- Đường khẩn cấp và phục hồi.

Log sử dụng hỗ trợ phát hiện dependency nhưng không chứng minh đã thấy mọi công việc ít xảy ra. Cần kết hợp owner, cấu hình và kiểm chứng.

### 13.2. Định nghĩa vai trò và quyền cần thiết

Lập ma trận tác vụ, target, role và nguồn. Xác định quyền nào có thể ủy nhiệm, quyền nào cần JIT và quyền nào thực sự thuộc phạm vi directory nhạy cảm.

Không chỉ đổi tên nhóm cũ rồi giữ mọi quyền như trước.

### 13.3. Thử trên phạm vi đại diện

Chọn nhóm server và công việc đại diện trong phạm vi an toàn. Kiểm tra công việc hợp lệ và các đường ngoài phạm vi.

Nếu thất bại, phân loại quyền còn thiếu hoặc dependency chưa biết. Không tự khôi phục domain admin cho toàn bộ nhóm để xử lý một lỗi cục bộ.

### 13.4. Di chuyển credential và automation

Thay danh tính chạy dịch vụ hoặc job khi phù hợp, với kế hoạch kiểm tra consumer và phục hồi. Không khóa hoặc rotation credential dùng chung khi chưa biết tác động cần thiết.

Các tài khoản không còn cần quyền domain phải được xử lý theo kết quả đánh giá, nhưng thay đổi cần bảo toàn khả năng vận hành và phục hồi đã được thiết kế.

### 13.5. Mở rộng và kiểm tra lại

Sau rollout, kiểm tra group lồng nhau, ACL, policy phân phối, nguồn khóa, công cụ hỗ trợ và ngoại lệ.

Thay đổi hệ thống quản lý hoặc thêm domain controller mới có thể tạo lại đường ảnh hưởng. Tiering là một thuộc tính cần được duy trì trong vòng đời thay đổi.

## 14. Ngoại lệ, break-glass và phục hồi

Một số tình huống hiếm gặp có thể cần quyền rộng hoặc cách truy cập khác. Ngoại lệ cần xác định người nhận, nguồn, target, tác vụ, thời hạn, thẩm quyền và bằng chứng.

Không biến một công việc khẩn cấp thành lý do đưa credential domain admin vào mọi máy chủ liên quan.

Đường phục hồi miền danh tính cần được thiết kế cho tình huống các dependency thông thường như IdP, PAM hoặc mạng quản trị gặp sự cố. Cần biết account và credential nào dùng được, giữ ở đâu và ai có quyền tiếp cận.

Tài khoản khẩn cấp không nên trở thành tài khoản dùng chung cho công việc thường lệ. Sau sử dụng, xử lý quyền tạm, credential, phiên và hậu kiểm theo thiết kế.

Nếu một identity domain admin bị nghi ảnh hưởng, phạm vi đánh giá có thể rộng hơn một server. Nếu một server admin bị nghi ảnh hưởng, vẫn cần xem các đường gián tiếp tới control plane; không kết luận đã cô lập chỉ vì tên role là server admin.

## 15. Kiểm chứng ranh giới

| Tình huống | Kết quả cần xác nhận |
|---|---|
| Server admin làm đúng tác vụ trên server được giao | Hoạt động được trong quyền đã định |
| Server admin thử target ngoài nhóm | Không được mở rộng chỉ vì cùng là member server |
| Identity directory admin dùng cho tác vụ server thường lệ | Bị hạn chế hoặc phát hiện theo ranh giới đã thiết kế |
| Server role có quyền sửa nhóm đặc quyền | Được phát hiện như đường ảnh hưởng cần xử lý |
| Server role có thể reset danh tính quản trị directory | Không bỏ sót khỏi đánh giá quyền gián tiếp |
| Nhóm server quản trị công cụ chạy mã trên domain controller | Quyền đó được phân loại và giới hạn tương ứng |
| Công cụ backup hoặc hypervisor có quyền với thành phần danh tính | Phạm vi điều khiển và owner được xác định |
| Người dùng sửa target hoặc credential mapping trong PAM | Không vượt boundary bằng tham số hoặc quyền cấu hình |
| Truy cập qua web, API, service hoặc batch | Không suy từ kết quả chặn RDP |
| Quyền JIT hết hạn | Cấp mới, token hoặc ticket và phiên được xử lý theo semantics riêng |
| Nguồn PAW hoặc gateway không đúng phạm vi | Không được bỏ qua chỉ vì MFA thành công |
| Ngoại lệ kết thúc | Quyền, credential và đường tạm được kiểm tra |
| Thêm server hoặc công cụ quản lý mới | Phân loại và boundary được cập nhật |
| Thu hồi một tài khoản dùng nhiều consumer | Tác động và kết quả được theo dõi theo phạm vi |

Kiểm chứng quyền có thể bắt đầu từ cấu hình, effective permissions và tác vụ an toàn trong môi trường phù hợp. Không cần thay đổi nhóm domain đặc quyền hoặc chạy thao tác nguy hiểm trên production chỉ để hoàn thành bảng.

Khi chưa có bằng chứng cho một đường, giữ rõ UNKNOWN hoặc NOT_TESTED theo quy trình, không gộp vào kết quả đạt.

## 16. Bằng chứng và chỉ số vận hành

Bằng chứng cần liên kết:

~~~text
Con người hoặc workload.
Danh tính được sử dụng và phạm vi vai trò.
Nguồn thiết bị và gateway.
Target, account và tác vụ.
Entitlement, phê duyệt và grant.
Credential hoặc khả năng ký theo định danh phù hợp.
Phiên và hoạt động quan sát được.
Hết hạn, thu hồi và phần còn chờ.
Ngoại lệ, thay đổi group, ACL hoặc policy liên quan.
~~~

Không lưu secret hoặc ticket xác thực đầy đủ chỉ để chứng minh phiên đã mở. Dùng định danh sự kiện và nguồn log có thể đối chiếu.

Các chỉ số có thể theo dõi gồm:

- Danh tính quản trị domain xuất hiện trên nguồn hoặc target ngoài phạm vi.
- Server role có đường ảnh hưởng tới control plane chưa xử lý.
- Tài khoản dịch vụ còn phụ thuộc quyền domain rộng.
- Credential dùng chung giữa phạm vi directory và server.
- Ngoại lệ quá hạn.
- Gateway hoặc công cụ quản lý có phạm vi rộng hơn thiết kế.
- Grant đã hết hạn nhưng còn kết quả phiên chưa được xác nhận.
- Tài nguyên mới chưa được phân loại.

Mẫu số phải rõ. Giảm số thành viên Domain Admins không tự chứng minh đã giảm mọi quyền tương đương hoặc đã tách hoàn chỉnh hai phạm vi.

## 17. Bài tập áp dụng

Một đội dùng cùng tài khoản domain admin để quản trị ứng dụng, đọc email và vào domain controller. Sau một đợt cải tổ, họ tạo tài khoản server admin riêng và bỏ tài khoản đó khỏi Domain Admins. Tuy nhiên, nhóm server admin vẫn quản trị công cụ triển khai chạy trên domain controller, console backup và PAW của người quản trị directory. Target cũng nhận đăng nhập trực tiếp ngoài PAM.

Hãy phân tích:

1. Những nguồn credential và phiên quyền cao nào đang bị dùng sai phạm vi?
2. Vì sao tạo tài khoản mới và bỏ một membership chưa đủ?
3. Những đường ảnh hưởng gián tiếp nào cần được kiểm kê?
4. Công việc server nào có thể dùng quyền hẹp hoặc ủy nhiệm theo tác vụ?
5. Nguồn PAW, gateway và quyền sử dụng credential cần được tách thế nào?
6. JIT hết hạn đã và chưa chứng minh điều gì với token, ticket và phiên?
7. Cần bằng chứng nào trước khi kết luận server admin không còn đường điều khiển directory ngoài ý định?
8. Đường khẩn cấp phải được vận hành và đóng lại ra sao?

Một thiết kế đạt mục tiêu cần thể hiện đúng quyền kiểm soát, nơi sử dụng danh tính và các dependency. Tách domain admin khỏi server admin có giá trị khi công việc member server không kéo theo việc sử dụng hoặc điều khiển đặc quyền của miền danh tính ngoài phạm vi đã được cấp.
