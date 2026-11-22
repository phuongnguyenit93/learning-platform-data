# Identity Domains và quản lý vòng đời người dùng

## 1. Mục tiêu và bối cảnh

Trong Oracle Cloud Infrastructure (OCI), một người đăng nhập được vào Console chưa chắc có quyền xem Compute instance, chỉnh sửa VCN hoặc quản lý Autonomous Database. Doanh nghiệp phải quản lý đồng thời danh tính, cách xác thực và quyền truy cập trong suốt thời gian người đó làm việc.

Bài học thuộc chương **Danh tính và phân quyền IAM** của module **CLOUD_PROVIDERS_ORACLE**. Nội dung tập trung vào Identity Domains và vòng đời người dùng, tạo nền tảng để vận hành hạ tầng OCI có phân quyền, giám sát, tự động hóa, kiểm soát chi phí và duy trì khả năng quản trị khi xảy ra sự cố.

Sau bài học, bạn có thể:

- Phân biệt tenancy, compartment, Identity Domain, user và group.
- Giải thích quan hệ giữa đăng nhập, vai trò quản trị domain, IAM policy và quyền trong ứng dụng.
- Thiết kế quy trình tiếp nhận, chuyển vị trí, tạm ngừng và chấm dứt quyền truy cập.
- Phân biệt federation, provisioning và Just-in-Time provisioning.
- Thực hành tạo người dùng thử nghiệm, cấp quyền đọc giới hạn và xác minh việc thu hồi.
- Xác định bằng chứng cần lưu để chứng minh một thay đổi quyền đã có hiệu lực.

Ví dụ xuyên suốt là doanh nghiệp có nhóm phát triển và nhóm vận hành nền tảng. Nhân viên An bắt đầu làm việc trong nhóm phát triển, sau đó chuyển sang nhóm hỗ trợ sản xuất và cuối cùng kết thúc hợp đồng.

## 2. Identity Domain là gì?

**Identity Domain** là không gian quản lý một tập người dùng cùng các cấu hình nhận dạng và bảo mật liên quan. Domain có thể chứa người dùng, nhóm, ứng dụng, thiết lập đăng nhập, MFA và cấu hình liên kết với nhà cung cấp danh tính bên ngoài. OCI IAM sử dụng Identity Domains cho xác thực, SSO và quản lý vòng đời danh tính của các ứng dụng Oracle cũng như ứng dụng khác. [Oracle: IAM with Identity Domains](https://docs.oracle.com/en-us/iaas/Content/Identity/)

Domain giúp trả lời các câu hỏi:

- Tài khoản nào đại diện cho nhân viên An?
- An đăng nhập bằng tài khoản cục bộ hay thông qua hệ thống doanh nghiệp?
- Những nhóm nào đang chứa An?
- Quy tắc đăng nhập nào áp dụng cho An?
- Ai được phép hỗ trợ tài khoản hoặc quản trị cấu hình của domain?

Domain không phải DNS domain và cũng không phải một mạng riêng chứa Compute instance.

### 2.1. Phân biệt các khái niệm gần nhau

| Khái niệm | Vai trò | Ví dụ trong doanh nghiệp |
| --- | --- | --- |
| Tenancy | Phạm vi tài khoản OCI, trong đó tổ chức quản lý tài nguyên và chính sách | Tài khoản OCI của công ty |
| Compartment | Tổ chức tài nguyên và làm phạm vi áp dụng quyền OCI | Compartment phát triển và compartment sản xuất |
| Identity Domain | Quản lý quần thể danh tính cùng cấu hình nhận dạng | Domain nhân viên hoặc domain đối tác |
| User | Bản ghi tài khoản trong một domain | Tài khoản của An |
| Group | Tập người dùng để tổ chức việc gán quyền hoặc ứng dụng | Nhóm người đọc thông tin Compute |
| Administrator role của domain | Giao nhiệm vụ quản trị danh tính trong domain | Người quản lý user và group |
| IAM policy | Cấp quyền thực hiện thao tác trên tài nguyên OCI | Cho một group đọc instance trong một compartment |
| Application role | Quyền nghiệp vụ hoặc quản trị trong ứng dụng được tích hợp | Vai trò người xem báo cáo trong ứng dụng |

Một tài khoản thuộc domain không có nghĩa các tài nguyên nó sử dụng phải nằm trong một compartment cùng tên. Việc OCI cho phép thao tác trên tài nguyên phụ thuộc vào quyền được cấp cho chủ thể và phạm vi tài nguyên tương ứng.

**Domain là nơi tổ chức danh tính; compartment là nơi tổ chức tài nguyên.** Muốn kết nối hai phía, cần cấu hình quyền phù hợp.

### 2.2. Default domain và các domain bổ sung

Tenancy sử dụng Identity Domains có một **Default identity domain** và có thể có thêm domain cho các quần thể khác. Một phương án thiết kế là tách nhân viên và đối tác khi hai nhóm có người quản trị, nguồn danh tính hoặc quy tắc đăng nhập khác nhau. Oracle cũng mô tả việc tách domain nhằm đáp ứng yêu cầu cô lập quản trị và quần thể người dùng. [Oracle: IAM Security Structure](https://docs.oracle.com/en-us/iaas/Content/cloud-adoption-framework/iam-security-structure.htm), [Oracle: Differences Between Tenancies With and Without Identity Domains](https://docs.oracle.com/en-us/iaas/process-automation/oci-process-automation/differences-tenancies-and-identity-domains.html)

Không cần tạo một domain cho mỗi dự án. Với nhiều nhóm có cùng nguồn danh tính và cùng yêu cầu đăng nhập, group kết hợp compartment có thể là phương án dễ vận hành hơn. Đây là lựa chọn thiết kế cần cân nhắc theo yêu cầu tổ chức.

Trước khi thêm domain, nên xác định:

1. Có quần thể người dùng và trách nhiệm quản trị thực sự khác nhau không?
2. Có cần tách cấu hình IdP, MFA hoặc ứng dụng không?
3. Việc đồng bộ, hỗ trợ và rà soát tài khoản sẽ do ai chịu trách nhiệm?
4. Loại domain được chọn có tính năng, hạn mức và cách tính phí phù hợp không?
5. Việc nhân bản tài khoản giữa nhiều domain có tạo thêm công việc offboarding không?

Không suy ra rằng tách domain sẽ tự động tách toàn bộ tài nguyên, chi phí hoặc quyền OCI. Những yêu cầu đó còn cần compartment, policy và quy trình quản trị tương ứng.

## 3. Ba lớp cần kiểm tra khi đánh giá quyền

Một cách phân tích hữu ích là tách đường truy cập thành ba lớp:

~~~mermaid
flowchart LR
    P["Người dùng"] --> A["Xác thực cục bộ hoặc qua IdP"]
    A --> D["Tài khoản trong Identity Domain"]
    D --> G["Group và vai trò được gán"]
    G --> I["IAM policy trên tài nguyên OCI"]
    G --> R["Quyền quản trị domain"]
    G --> S["Gán ứng dụng và application role"]
    I --> C["Compute, VCN, lưu trữ, dịch vụ Database"]
~~~

Sơ đồ thể hiện quan hệ khái niệm, không mô tả đầy đủ mọi giao thức hay thứ tự xử lý nội bộ.

### 3.1. Xác thực: người này là ai?

Với tài khoản cục bộ, domain quản lý cơ chế đăng nhập tương ứng. Với tài khoản liên kết, IdP bên ngoài xác thực người dùng theo cấu hình federation. MFA bổ sung bằng chứng xác thực, nhưng không tự tạo ra quyền quản lý tài nguyên.

### 3.2. Phân quyền OCI: người này được làm gì?

IAM policy xác định quyền của chủ thể đối với tài nguyên trong tenancy hoặc compartment. Policy OCI có cú pháp cơ bản:

~~~text
Allow <subject> to <verb> <resource-type> in <location>
~~~

Ví dụ, giả sử đã có group và compartment phục vụ thực hành:

~~~text
Allow group 'Default'/'iam-lab-readers' to read instances in compartment iam-lab
~~~

Policy này cấp cho thành viên group quyền đọc tài nguyên loại instance trong phạm vi nêu trên. Nó không cấp quyền tạo instance, cấu hình mạng hoặc quản trị domain. Đọc toàn bộ thông tin liên quan tới một instance có thể cần quyền trên những loại tài nguyên khác, chẳng hạn thông tin mạng hoặc volume; không mở rộng policy chỉ để làm mọi trang Console hiển thị đầy đủ.

Tên domain trong subject giúp chỉ rõ group đang được tham chiếu. Khi dùng domain ngoài Default, cần chỉ rõ domain tương ứng; tránh hiểu rằng hai group cùng tên ở hai domain là cùng một chủ thể. [Oracle: IAM Policies Overview](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/policy-syntax.htm), [Oracle: Subjects](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/subject.htm)

### 3.3. Quản trị domain và quyền trong ứng dụng

Một **User administrator** có thể quản lý user, group và membership trong domain. **Help desk administrator** phục vụ những thao tác hỗ trợ như mở khóa và đặt lại yếu tố xác thực trong phạm vi được giao. **Identity domain administrator** có quyền quản trị rộng trong domain, nên cần giao có chủ đích. [Oracle: Understanding Administrator Roles](https://docs.oracle.com/en-us/iaas/Content/Identity/roles/understand-administrator-roles.htm)

Không xem vai trò quản trị domain là đồng nghĩa với quyền quản trị mọi Compute instance hoặc mọi compartment. Vai trò domain và IAM policy có phạm vi khác nhau, đồng thời phải đánh giá toàn bộ quyền hiện có của người dùng. [Oracle: Security](https://docs.oracle.com/en-us/iaas/Content/Identity/conversion/security.htm)

Tương tự, quyền quản lý dịch vụ Database qua OCI không tự động thay thế quyền bên trong cơ sở dữ liệu. Đăng nhập SQL, vai trò ứng dụng và đăng nhập hệ điều hành của máy chủ là những bề mặt cần quản lý riêng nếu hệ thống sử dụng chúng.

**Hệ quả vận hành:** hỗ trợ thành công một lần đăng nhập chỉ chứng minh lớp xác thực đã hoạt động. Nó chưa chứng minh quyền tài nguyên đúng, đủ và giới hạn như yêu cầu.

## 4. Xác định nguồn dữ liệu danh tính

Trước khi tạo nhiều user, cần quyết định hệ thống nào là nguồn chuẩn cho từng loại dữ liệu.

| Dữ liệu | Nguồn chuẩn gợi ý | Câu hỏi phải giải quyết |
| --- | --- | --- |
| Mã nhân viên, ngày bắt đầu, ngày kết thúc | Hệ thống nhân sự | Sự kiện nghỉ việc được phát ra lúc nào? |
| Tài khoản doanh nghiệp | Directory hoặc IdP của công ty | Ai chịu trách nhiệm xác minh chủ tài khoản? |
| Thuộc tính user trong OCI | Quy tắc đồng bộ đã phê duyệt | Trường nào được sửa cục bộ, trường nào bị ghi đè? |
| Group nghiệp vụ | Danh mục quyền và người phê duyệt | Ai được yêu cầu và duyệt membership? |
| Vai trò quản trị đặc quyền | Quy trình quản trị truy cập | Ai duyệt, ai thực hiện, ai rà soát? |
| Kết quả cấp và thu hồi | Hệ thống thực thi và kiểm tra | Có xác nhận từ hệ thống đích hay chỉ có yêu cầu? |

Bảng trên là gợi ý tổ chức quy trình, không phải tập nguồn dữ liệu mặc định do OCI tự cấu hình.

Nên liên kết bản ghi bằng định danh ổn định của nhân sự hoặc đối tác, thay vì chỉ dùng tên hiển thị. Email có thể đổi khi nhân viên chuyển đơn vị; tên hiển thị có thể trùng nhau. Khi có người quay lại làm việc, cần đối chiếu lịch sử và phê duyệt thay vì tự động khôi phục toàn bộ quyền cũ.

Một thay đổi ở nguồn chuẩn chỉ có giá trị vận hành khi đã được áp dụng và kiểm chứng tại đích. Trạng thái “đã gửi yêu cầu” khác với “đã thu hồi thành công”.

## 5. Mô hình vòng đời người dùng

OCI mô tả vòng đời tài khoản với các giai đoạn chưa tồn tại, bị vô hiệu hóa, được kích hoạt và đã xóa. Việc chuyển trạng thái gắn với sự kiện hoặc thời điểm của tổ chức. [Oracle: Lifecycle for Managing Users](https://docs.oracle.com/en-us/iaas/Content/Identity/users/lifecycle-managing-users.htm)

Có thể xây dựng quy trình nội bộ như sau:

~~~mermaid
flowchart TD
    N["Chưa có tài khoản"] --> C["Tạo tài khoản theo phê duyệt"]
    C --> W["Giữ chưa hoạt động nếu chưa đến ngày làm việc"]
    C --> A["Kích hoạt khi đủ điều kiện"]
    W --> A
    A --> M["Cập nhật quyền khi chuyển vai trò"]
    M --> A
    A --> D["Vô hiệu hóa khi tạm ngừng hoặc nghỉ việc"]
    D --> V["Rà soát trước khi kích hoạt lại"]
    V --> A
    D --> X["Xóa theo quy trình lưu giữ"]
~~~

Các ô “giữ chưa hoạt động”, “rà soát” là bước nghiệp vụ, không phải tên trạng thái bắt buộc xuất hiện trong Console.

Cần phân biệt:

- **Chưa hoàn tất lời mời hoặc thiết lập đăng nhập:** người dùng còn thiếu bước tham gia.
- **Bị khóa do sự cố đăng nhập:** cần xử lý nguyên nhân và xác minh danh tính trước khi mở khóa.
- **Bị quản trị viên vô hiệu hóa:** cần có quyết định cho phép hoạt động trở lại.
- **Bị xóa:** tài khoản đã bị loại bỏ; không nên xem việc tạo một tài khoản cùng tên là hoàn tác đầy đủ lịch sử.

Đặt lại mật khẩu không thay thế quyết định cấp quyền. Mở khóa tài khoản cũng không có nghĩa được phép bỏ qua quy trình nghỉ việc hoặc tạm ngừng truy cập.

## 6. Joiner: tiếp nhận người dùng mới

Mục tiêu của onboarding là tạo đúng tài khoản cho đúng người, cấp bộ quyền tối thiểu cần thiết và kiểm tra được kết quả.

### 6.1. Thông tin cần có trước khi tạo

Với nhân viên An, yêu cầu tiếp nhận nên chứa:

- Định danh nhân sự hoặc đối tác và người quản lý chịu trách nhiệm.
- Domain đích và phương thức xác thực.
- Ngày bắt đầu; ngày kết thúc nếu là hợp đồng có thời hạn.
- Group được duyệt, lý do cần quyền và phạm vi tài nguyên.
- Các ứng dụng cần dùng.
- Phê duyệt riêng cho quyền đặc quyền hoặc quyền sản xuất.

Không dùng chung tài khoản cho cả nhóm. Tài khoản cá nhân giúp truy vết ai đã thực hiện thao tác và thu hồi quyền khi một thành viên rời nhóm.

### 6.2. Trình tự tiếp nhận gợi ý

1. Đối chiếu với nguồn chuẩn để tránh tạo trùng tài khoản.
2. Chọn đúng domain trước khi tạo hoặc đồng bộ user.
3. Tạo tài khoản bằng quy trình được duyệt; thiết lập thời điểm hoạt động phù hợp.
4. Gán những group đã phê duyệt; kiểm tra không có vai trò quản trị ngoài yêu cầu.
5. Hoàn tất lời mời, đăng nhập lần đầu và MFA theo chính sách.
6. Xác minh khả năng truy cập tài nguyên được phép.
7. Xác minh một tình huống ngoài phạm vi phải bị từ chối.
8. Lưu bằng chứng tài khoản, membership, thời điểm và người thực hiện.

Một lời mời được gửi thành công chưa chứng minh nhân viên đã hoàn tất MFA hoặc đã được cấp quyền đúng. Cần ghi nhận riêng kết quả gửi thông báo, kết quả đăng nhập và kết quả kiểm tra quyền.

### 6.3. Bộ quyền mặc định nên nhỏ

Với An thuộc nhóm phát triển, có thể bắt đầu bằng nhóm đọc thông tin cần thiết trong môi trường phát triển. Khi có nhu cầu triển khai hạ tầng, quy trình cấp quyền bổ sung phải xét những thao tác cụ thể trên Compute, VCN, lưu trữ hoặc Database.

Không đưa người dùng vào nhóm quản trị rộng chỉ để giải quyết nhanh lỗi “không nhìn thấy tài nguyên”. Hãy xác minh đúng domain, compartment, region và policy trước.

## 7. Mover: thay đổi vai trò mà không tích lũy quyền

Khi An chuyển từ phát triển sang hỗ trợ sản xuất, chỉ thêm group mới sẽ để lại quyền cũ. Sau nhiều lần chuyển vị trí, quyền thực tế có thể lớn hơn nhiều so với công việc hiện tại.

Cách quản lý tốt hơn là tính chênh lệch giữa bộ quyền hiện tại và bộ quyền đã được duyệt:

~~~text
Quyền cần thêm = Quyền được duyệt mới - Quyền hiện tại
Quyền cần bỏ  = Quyền hiện tại - Quyền được duyệt mới
~~~

Phép tính này cần xét group, vai trò quản trị, ứng dụng và các cơ chế cấp quyền trực tiếp nếu có. Công thức chỉ mô tả mục tiêu quản trị, không thay thế cách OCI đánh giá policy.

Trình tự chuyển vai trò:

1. Xác định trách nhiệm và thời điểm chuyển việc.
2. Lập danh sách quyền hiện có cùng nguồn cấp của từng quyền.
3. Duyệt bộ quyền mới và khoảng thời gian bàn giao nếu cần.
4. Gỡ quyền cũ theo kế hoạch; thêm quyền mới trong khoảng chuyển đổi được duyệt.
5. Kiểm tra thao tác mới được phép và thao tác cũ đã mất quyền.
6. Đặt hạn kết thúc cho ngoại lệ bàn giao và lưu kết quả xác minh.

OCI policy cấp quyền theo các phát biểu cho phép; không thể thêm một phát biểu deny để triệt tiêu tùy ý quyền đã được cho phép bởi policy khác. Vì vậy, nếu gỡ An khỏi một group nhưng quyền còn tồn tại, phải tìm các nguồn cấp khác. [Oracle: IAM Policies Overview](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/policy-syntax.htm)

Ví dụ, An có thể vẫn đọc được tài nguyên phát triển vì một group khác có quyền rộng hơn ở compartment cha. Kiểm tra một membership đơn lẻ không đủ để kết luận đã hoàn tất chuyển quyền.

## 8. Leaver: thu hồi quyền khi nghỉ việc

Offboarding cần xử lý cả đường đăng nhập và các phương tiện truy cập đã cấp trước đó.

### 8.1. Không coi Deactivate là thu hồi mọi thứ

OCI cho phép kích hoạt hoặc vô hiệu hóa tài khoản. Tài liệu Oracle lưu ý rằng một người đã có phiên hoạt động khi bị vô hiệu hóa có thể vẫn truy cập phiên đó với khả năng bị giới hạn; sau khi đăng xuất, họ không thể đăng nhập lại. Do đó, không giả định rằng Deactivate lập tức kết thúc mọi phiên và mọi đường truy cập. [Oracle: Changing a User's Status](https://docs.oracle.com/en-us/iaas/Content/Identity/users/change-status-user-account.htm)

Lập danh mục những bề mặt mà người dùng thực sự có:

| Bề mặt | Việc cần kiểm tra khi thu hồi |
| --- | --- |
| Tài khoản tại IdP doanh nghiệp | Đã chặn xác thực theo quyết định nghỉ việc chưa? |
| User trong Identity Domain | Đã vô hiệu hóa tại đúng domain và đúng định danh chưa? |
| Group, administrator role, gán ứng dụng | Đã bỏ những quyền không còn hợp lệ chưa? |
| Phiên đăng nhập domain | Đã xử lý những loại phiên theo cơ chế được hỗ trợ chưa? |
| Phiên và token của ứng dụng | Ứng dụng đích đã kết thúc hoặc vô hiệu hóa quyền còn lại chưa? |
| Credential OCI gắn với người dùng | Đã kiểm kê và thu hồi API signing key, auth token, customer secret key hoặc loại credential khác đang dùng chưa? |
| Truy cập máy chủ và cơ sở dữ liệu | SSH key, tài khoản hệ điều hành và tài khoản SQL độc lập đã được xử lý chưa? |
| Công cụ tự động hóa | Có pipeline nào đang phụ thuộc vào danh tính hoặc secret cá nhân này không? |

Bảng là danh mục cần kiểm chứng theo hệ thống thực tế. Không phải mỗi người dùng đều có tất cả các loại credential trên.

### 8.2. Phạm vi của thao tác xóa phiên

OCI có thao tác **Clear all signed-in sessions** cho các phiên **Keep me signed-in**, với điều kiện tính năng đó được bật và người dùng có phiên loại này. Không suy diễn tên thao tác thành bảo đảm hủy mọi phiên ứng dụng hoặc mọi token API. [Oracle: Clearing All Keep Me Signed-In Sessions for a User](https://docs.oracle.com/en-us/iaas/Content/Identity/users/clear-signed-in-sessions-for-users.htm)

Runbook offboarding nên ghi rõ từng loại phiên, credential và bằng chứng thu hồi tương ứng. Nếu một ứng dụng duy trì phiên riêng, người vận hành phải kiểm tra cơ chế kết thúc phiên của chính ứng dụng đó.

### 8.3. Trình tự xử lý gợi ý

1. Xác minh quyết định và thời điểm chấm dứt truy cập.
2. Chặn đường xác thực tại nguồn và tại domain theo thiết kế tổ chức.
3. Thu hồi quyền đặc quyền, membership và gán ứng dụng không còn hợp lệ.
4. Xử lý credential, token và phiên còn tồn tại.
5. Thu hồi truy cập vào những hệ thống độc lập như máy chủ hoặc Database.
6. Bàn giao tác vụ tự động hóa và trách nhiệm vận hành tài nguyên.
7. Kiểm tra các đường truy cập quan trọng đã thất bại như mong đợi.
8. Lưu bằng chứng; xóa tài khoản sau khi đáp ứng quy trình lưu giữ.

Với sự cố bảo mật khẩn cấp, cần ưu tiên những đường còn cho phép truy cập trước; thứ tự cụ thể phải nằm trong runbook của tổ chức.

Không giả định việc xóa user sẽ xóa Compute instance, bucket hay cơ sở dữ liệu mà người đó từng tạo. Phải bàn giao tài nguyên và xem xét chi phí tiếp diễn bằng quy trình quản lý tài nguyên riêng.

### 8.4. Kích hoạt lại phải có rà soát quyền

Một tài khoản được vô hiệu hóa để tạm nghỉ có thể được kích hoạt lại khi đủ điều kiện. Trước khi làm, cần kiểm tra quyền được giữ lại trong thời gian nghỉ và đối chiếu với công việc mới.

Đối với người quay lại sau khi đã nghỉ việc, không tái sử dụng quyết định cấp quyền cũ như một phê duyệt hiện hành. Hãy xử lý việc trở lại như một sự kiện nghiệp vụ cần xác minh.

## 9. Federation, provisioning và JIT

Ba khái niệm này liên quan nhau nhưng giải quyết những việc khác nhau.

| Cơ chế | Mục đích chính | Điều không nên mặc định |
| --- | --- | --- |
| Federation/SSO | Cho phép dùng IdP đã cấu hình để xác thực vào dịch vụ | Tự đồng bộ đầy đủ user, group và việc nghỉ việc |
| Provisioning | Tạo, cập nhật, vô hiệu hóa hoặc xóa bản ghi ở hệ thống đích theo cấu hình tích hợp | Một lần đăng nhập thành công chứng minh đồng bộ đang khỏe |
| Just-in-Time provisioning | Tạo hoặc cập nhật danh tính trong luồng đăng nhập theo cấu hình | Sự kiện nghỉ việc luôn được xử lý ngay cả khi người dùng không đăng nhập nữa |

Oracle hỗ trợ liên kết Identity Domain với IdP bên ngoài. SAML JIT có thể tạo tài khoản khi người dùng đăng nhập lần đầu và có thể cập nhật thuộc tính hoặc membership theo cấu hình. [Oracle: Managing Identity Providers](https://docs.oracle.com/en-us/iaas/Content/Identity/identityproviders/manage-identity-providers.htm), [Oracle: Adding a SAML Just-in-Time Identity Provider](https://docs.oracle.com/en-us/iaas/Content/Identity/identityproviders/add-saml-idp-jit-prov.htm)

Ví dụ:

- Công ty xác thực An tại IdP doanh nghiệp.
- Một cơ chế provisioning đã cấu hình đưa bản ghi và membership cần thiết tới domain.
- Khi An đăng nhập, federation thực hiện phần xác thực.
- Khi An nghỉ việc, luồng offboarding phải cập nhật đích và xử lý credential, phiên, ứng dụng liên quan.

Nếu chỉ dựa vào cập nhật trong lần đăng nhập JIT tiếp theo, một người đã nghỉ việc và không đăng nhập nữa có thể không kích hoạt luồng cập nhật mà quy trình đang trông chờ. Vì vậy, cần có luồng thu hồi độc lập và đối soát định kỳ.

**SCIM**, viết tắt của System for Cross-domain Identity Management, là chuẩn hỗ trợ trao đổi và quản lý user, group giữa các hệ thống. Trong tích hợp phù hợp, SCIM giúp tự động hóa provisioning; nó không thay thế cơ chế SSO. Khả năng thao tác và chiều đồng bộ phụ thuộc connector, ứng dụng và cấu hình đã chọn. [Oracle: Integrating Custom Applications with IAM](https://docs.oracle.com/en-us/iaas/Content/Identity/scim/overview.htm)

Trước khi đưa tích hợp vào vận hành, nên kiểm tra:

- Quy tắc ghép bản ghi và cách tránh tạo user trùng.
- Thuộc tính nào bị nguồn chuẩn ghi đè.
- Cách ánh xạ group và xử lý group đặc quyền.
- Sự kiện vô hiệu hóa hoặc xóa tại nguồn được biểu diễn thế nào ở đích.
- Cách xử lý lỗi từng phần, retry và cảnh báo.
- Người chịu trách nhiệm khi credential hoặc chứng chỉ tích hợp sắp hết hạn.

Không ánh xạ group quản trị từ thuộc tính mà người dùng có thể tự sửa. Một lỗi ánh xạ nhóm có thể làm quyền đặc quyền được cấp hàng loạt.

## 10. Tự động hóa theo trạng thái mong muốn

Quy trình tự động hóa nên so sánh trạng thái mong muốn với trạng thái thực tế, áp dụng chênh lệch và kiểm tra lại. Không nên chỉ chạy một chuỗi lệnh “thêm user, thêm group” rồi coi là hoàn tất.

Mã giả sau mô tả ý tưởng, không phải lệnh OCI có thể chạy trực tiếp:

~~~text
nhan_su_kien(event):
    kiem_tra_nguon_va_phe_duyet(event)
    user = tim_theo_dinh_danh_on_dinh(event.person_id, event.domain_id)

    desired = tinh_trang_thai_duoc_duyet(event)
    actual = doc_trang_thai_hien_tai(user)

    changes = so_sanh(actual, desired)
    ap_dung_theo_runbook(changes)

    verified = doc_lai_va_kiem_tra(desired)

    neu verified:
        ghi_nhan_hoan_tat(event)
    neu khong:
        ghi_nhan_chua_hoan_tat_va_canh_bao(event)
~~~

Các thuộc tính thiết kế quan trọng:

- **Idempotent:** xử lý lại cùng sự kiện không tạo thêm user hoặc membership trùng.
- **Có thứ tự:** một sự kiện tiếp nhận đến muộn không được vô tình kích hoạt lại người đã nghỉ.
- **Có đối soát:** phát hiện chênh lệch kể cả khi một sự kiện đồng bộ bị bỏ lỡ.
- **Có kiểm soát ngoại lệ:** quyền tạm thời có chủ sở hữu, phê duyệt và hạn kết thúc.
- **Có retry giới hạn:** phân biệt lỗi tạm thời với lỗi cấu hình cần người xử lý.
- **Có readback:** chỉ xác nhận hoàn tất khi trạng thái tại đích phù hợp.
- **Có bảo vệ dữ liệu:** nhật ký ghi định danh và kết quả cần thiết, không ghi mật khẩu hoặc token bí mật.

Đây là nguyên tắc thiết kế quy trình. Chọn API, connector và credential vận hành theo khả năng của môi trường thực tế.

Với workload trên OCI, nên đánh giá instance principal, resource principal và dynamic group khi được dịch vụ hỗ trợ để giảm phụ thuộc vào credential cá nhân. Danh tính của workload cần được quản lý theo vòng đời workload; không dùng nó để thay thế việc truy vết các thao tác của con người.

## 11. Giám sát và bằng chứng vận hành

Nên theo dõi cả hoạt động đăng nhập và thay đổi quyền. Identity Domain có những báo cáo như đăng nhập thành công, đăng nhập thất bại, user không hoạt động, hoạt động audit và quyền ứng dụng. Quyền xem báo cáo phụ thuộc vai trò được giao. [Oracle: Types of Reports](https://docs.oracle.com/en-us/iaas/Content/Identity/reports/understand-types-reports.htm), [Oracle: Running Reports](https://docs.oracle.com/en-us/iaas/Content/Identity/reports/run-reports.htm)

Một hồ sơ thay đổi quyền nên trả lời được:

| Câu hỏi | Bằng chứng gợi ý |
| --- | --- |
| Ai hoặc hệ thống nào yêu cầu? | Mã yêu cầu và nguồn sự kiện |
| Ai duyệt? | Phê duyệt gắn với phạm vi và thời hạn |
| Thay đổi cho danh tính nào? | Domain, định danh user và định danh nguồn |
| Thay đổi gì? | Trạng thái, group, vai trò hoặc credential trước và sau |
| Khi nào áp dụng? | Dấu thời gian có múi giờ |
| Đã có hiệu lực chưa? | Readback và kiểm tra truy cập phù hợp |
| Có phần nào thất bại? | Hệ thống đích lỗi, người xử lý và hạn xử lý |

Có thể xây dựng các chỉ số vận hành sau; đây là chỉ số tổ chức tự thiết kế, không phải khẳng định rằng OCI có sẵn từng metric:

- Thời gian từ quyết định nghỉ việc đến khi hoàn tất thu hồi.
- Số yêu cầu provisioning chưa thành công.
- Số tài khoản còn hoạt động sau ngày kết thúc hợp đồng.
- Số quyền tạm thời đã quá hạn.
- Số tài khoản hoặc membership không đối chiếu được với nguồn chuẩn.
- Số thay đổi quyền đặc quyền chưa có phê duyệt hợp lệ.

Không dùng riêng báo cáo “không đăng nhập gần đây” để kết luận tài khoản không hoạt động ở mọi kênh. Việc sử dụng API và credential ngoài phiên Console cần được xem xét theo nguồn ghi nhận tương ứng.

Cần chọn nơi lưu bằng chứng và thời gian lưu theo yêu cầu tổ chức cùng khả năng dịch vụ. Không giả định báo cáo trong domain và OCI Audit là cùng một nguồn có phạm vi, thời gian lưu giống nhau.

## 12. Bài thực hành: cấp quyền đọc và kiểm tra thu hồi

### 12.1. Điều kiện chuẩn bị

Dùng môi trường thực hành với:

- Một domain đã được người quản trị cho phép sử dụng, ví dụ Default.
- Một compartment thử nghiệm tên **iam-lab** đã tồn tại.
- Tài khoản quản trị được ủy quyền cho các thao tác user, group và policy cần thiết.
- Một hộp thư thử nghiệm do bạn kiểm soát để hoàn tất bước tham gia khi cần.
- Một phiên quản trị độc lập để tránh tự khóa khả năng quản lý.

Bài này không yêu cầu tạo Compute instance, VCN hoặc Database. Nếu compartment chưa có instance, danh sách trống là kết quả hợp lệ khi kiểm tra quyền liệt kê.

Không thay đổi tài khoản quản trị đang dùng để hoàn thành bài tập. Không dùng tài khoản sản xuất làm đối tượng vô hiệu hóa thử nghiệm.

### 12.2. Các bước thực hiện

**Bước 1 — Xác nhận phạm vi.**

Trong Console, mở khu vực Identity & Security, tìm Domains và chọn domain dự kiến. Ghi lại tên domain, tài khoản quản trị và compartment thực hành. Nhãn hoặc cách bố trí màn hình có thể thay đổi; luôn xác nhận domain trên trang chi tiết trước khi sửa user.

**Bước 2 — Tạo group thực hành.**

Tạo group **iam-lab-readers** trong domain đã chọn. Không gán vai trò quản trị domain cho group này.

**Bước 3 — Tạo tài khoản thử nghiệm.**

Tạo user, ví dụ **an.iam.lab**, với địa chỉ liên hệ do bạn kiểm soát. Nếu môi trường sử dụng federation hoặc provisioning, tạo qua nguồn chuẩn theo quy trình đã cấu hình để tránh bản ghi trùng.

**Bước 4 — Gán membership.**

Thêm user vào group **iam-lab-readers**. Kiểm tra user không thuộc group khác đã có quyền rộng hơn và không có administrator role ngoài dự kiến.

**Bước 5 — Cấp policy giới hạn.**

Người có thẩm quyền tạo policy tại phạm vi phù hợp, ví dụ ở root cho bài thực hành đã được duyệt:

~~~text
Allow group 'Default'/'iam-lab-readers' to read instances in compartment iam-lab
~~~

Nếu domain hoặc compartment có tên khác, thay đúng định danh. Không thay policy của nhóm quản trị hiện có để phục vụ bài tập.

**Bước 6 — Hoàn tất đăng nhập.**

Mở một phiên trình duyệt độc lập, đăng nhập bằng user thử nghiệm và hoàn tất các bước xác thực theo chính sách. Kiểm tra đúng tenancy, domain, region và compartment.

**Bước 7 — Kiểm tra quyền được phép.**

Mở danh sách Compute instance trong compartment thực hành. Ghi lại kết quả:

- Liệt kê thành công, có thể là danh sách trống.
- Không có quyền xem một thành phần khác mà bài tập chưa cấp.
- Hoặc yêu cầu liệt kê instance bị từ chối và cần điều tra.

Chỉ mục đầu chứng minh phép thử đọc đã đạt. Giao diện hiển thị thiếu dữ liệu liên quan không phải lý do tự động cấp thêm quyền rộng.

**Bước 8 — Kiểm tra giới hạn quyền.**

Kiểm tra user không có quyền sửa cấu hình hoặc quản trị user khác. Không tạo tài nguyên tính phí chỉ để thử một thao tác bị từ chối. Có thể dùng bằng chứng policy và một yêu cầu đọc tài nguyên có sẵn ngoài phạm vi do người hướng dẫn chỉ định.

Nếu không có tài nguyên ngoài phạm vi để thử, ghi rõ phần kiểm tra đó chưa thực hiện; không coi danh sách trống là bằng chứng bị từ chối quyền.

**Bước 9 — Thu hồi membership.**

Trong phiên quản trị độc lập, gỡ user khỏi group thực hành. Kiểm tra lại membership và phép đọc trong một phiên phù hợp sau khi thay đổi được áp dụng. Nếu vẫn còn quyền, tìm group khác, policy khác hoặc trạng thái cập nhật chưa phản ánh ở đích.

Không cam kết một số giây cố định cho mọi thay đổi quyền. Khi hết thời gian chờ theo runbook mà kết quả vẫn sai, ghi nhận lỗi để điều tra.

**Bước 10 — Thực hành vô hiệu hóa.**

Vô hiệu hóa user thử nghiệm và kiểm tra một lần đăng nhập mới bị ngăn chặn. Xử lý các phiên hoặc credential đã tạo theo phạm vi bài tập. Kết quả này khác với kiểm tra mất quyền đọc ở bước 9.

**Bước 11 — Dọn dẹp.**

Theo quy trình môi trường, xóa user thử nghiệm sau khi lưu bằng chứng cần thiết, bỏ policy thực hành và xóa group khi không còn được tham chiếu. Chỉ dọn những đối tượng đã tạo cho bài tập; không xóa compartment hoặc tài nguyên dùng chung.

### 12.3. Tiêu chí hoàn thành

Bài thực hành đạt khi có bằng chứng cho cả ba việc:

1. User được nhận dạng trong đúng domain.
2. User chỉ nhận quyền đọc đã duyệt trong phạm vi thực hành.
3. Membership và khả năng đăng nhập được thu hồi bằng các bước kiểm tra riêng.

Không cần chụp hoặc lưu nội dung mật khẩu, secret, mã MFA hay token vào hồ sơ bài tập.

## 13. Chẩn đoán những tình huống thường gặp

| Tình huống | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy user | Đang ở sai domain hoặc đồng bộ chưa hoàn tất | Xác nhận domain và định danh nguồn |
| Đăng nhập được nhưng không thấy instance | Thiếu policy, sai compartment hoặc sai region | Kiểm tra lần lượt phạm vi và quyền |
| Group tồn tại nhưng policy không cấp đúng quyền | Tham chiếu nhầm domain hoặc group | Đối chiếu subject với group thực tế |
| Gỡ một group nhưng user vẫn có quyền | Có nguồn cấp quyền khác | Rà soát toàn bộ membership, role và policy liên quan |
| User vừa bị vô hiệu hóa vẫn có phiên | Phiên đã được thiết lập trước đó | Xử lý từng loại phiên theo cơ chế hỗ trợ |
| Không đăng nhập Console được nhưng truy cập khác còn tồn tại | Credential hoặc tài khoản đích được quản lý riêng | Kiểm kê từng kênh và xác minh việc thu hồi |
| Sửa thuộc tính rồi bị đổi lại | Nguồn provisioning ghi đè | Sửa tại nguồn chuẩn hoặc điều chỉnh quy tắc |
| Nghỉ việc ở hệ thống nhân sự nhưng user OCI còn hoạt động | Lỗi luồng thu hồi hoặc ánh xạ sai bản ghi | Xử lý khẩn theo mức rủi ro và sửa tích hợp |
| User mới có quyền quá rộng | Group mặc định, ánh xạ hoặc role sai | Thu hồi quyền dư và sửa nguyên nhân cấp quyền |
| Mở khóa lặp lại vẫn thất bại | Credential cũ hoặc cấu hình xác thực còn lỗi | Điều tra nguồn đăng nhập trước khi tiếp tục mở khóa |

Khi xử lý lỗi, hãy tách câu hỏi “đã xác thực thành công chưa?” khỏi “đã được cấp phép thao tác này chưa?”. Sự tách biệt đó giúp tránh sửa policy để giải quyết lỗi mật khẩu hoặc đặt lại MFA để giải quyết lỗi thiếu quyền tài nguyên.

## 14. Liên hệ với chi phí và tính sẵn sàng

Quản lý vòng đời danh tính tác động trực tiếp tới vận hành hạ tầng OCI:

- **Chi phí:** quyền tạo tài nguyên quá rộng hoặc tài khoản cũ chưa thu hồi có thể dẫn đến tài nguyên ngoài kế hoạch. Việc xóa user không thay thế kiểm kê tài nguyên và ngân sách.
- **Tính sẵn sàng quản trị:** nếu chỉ có một người giữ quyền hoặc toàn bộ đăng nhập phụ thuộc một tích hợp lỗi, đội vận hành có thể mất khả năng xử lý sự cố.
- **Tính sẵn sàng workload:** pipeline dùng credential cá nhân có thể ngừng chạy khi người sở hữu nghỉ việc.
- **Khả năng điều tra:** tài khoản riêng, dấu vết thay đổi và hồ sơ phê duyệt giúp xác định trách nhiệm khi có sự cố.

Một phương án vận hành nên có nhiều người quản trị được ủy quyền phù hợp, tài khoản khẩn cấp được kiểm soát và quy trình kiểm tra khả năng truy cập khi IdP gặp sự cố. Tài khoản khẩn cấp cần được bảo vệ, giám sát và rà soát; không dùng làm tài khoản công việc hằng ngày.

Trước thay đổi federation hoặc quy tắc đăng nhập quan trọng, nên kiểm tra một nhóm nhỏ và duy trì đường khôi phục được phê duyệt. Đối với tự động hóa, phải xác định chủ sở hữu workload để việc bàn giao không phụ thuộc vào một nhân viên cụ thể.

## 15. Câu hỏi tự kiểm tra

1. Tại sao user trong một Identity Domain không tự có quyền quản lý tài nguyên trong compartment cùng tên?
2. Người có User administrator role có nhất thiết được phép tạo Compute instance không?
3. Nếu An chuyển nhóm, tại sao chỉ thêm membership mới là chưa đủ?
4. Vì sao SSO thành công không chứng minh provisioning và offboarding đang hoạt động?
5. Có thể kết luận mọi kênh truy cập đã bị thu hồi chỉ bằng việc vô hiệu hóa user không?
6. Cần kiểm tra gì nếu đã gỡ group mà user vẫn đọc được tài nguyên?
7. Việc xóa user có xử lý chi phí của các instance hoặc Database đang chạy không?
8. Bộ bằng chứng nào phân biệt một yêu cầu thu hồi đã gửi với việc thu hồi thực sự hoàn tất?

Một thiết kế đạt yêu cầu phải nối được toàn bộ chuỗi: **đúng danh tính → đúng xác thực → đúng quyền → thay đổi theo sự kiện → thu hồi được kiểm chứng**. Với OCI, chuỗi này cần phối hợp Identity Domain, group, administrator role, IAM policy, credential và những hệ thống đích mà người dùng truy cập.
