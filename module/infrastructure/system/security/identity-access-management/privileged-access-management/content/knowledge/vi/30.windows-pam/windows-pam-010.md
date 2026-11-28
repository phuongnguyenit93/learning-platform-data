# Group Policy admin control

## 1. Vì sao quyền quản trị Group Policy là quyền đặc biệt?

Trong Active Directory Domain Services (AD DS), Group Policy là cơ chế phân phối cấu hình đến người dùng và máy tính theo phạm vi quản lý. Một Group Policy Object (GPO) có thể ảnh hưởng đến chính sách bảo mật, quyền người dùng, tường lửa, cấu hình dịch vụ, script đăng nhập hoặc khởi động và nhiều thiết lập khác.

Vì vậy, quyền sửa GPO không chỉ là quyền thay đổi một tài liệu cấu hình. Trong một số trường hợp, người có quyền sửa một GPO đang áp dụng cho máy chủ có thể tạo ra thay đổi được thực thi trên máy đó với quyền cao. Nếu GPO tác động đến domain controller hoặc máy trạm quản trị đặc quyền, hậu quả có thể lan đến toàn miền.

**Group Policy admin control** là việc kiểm soát ai được tạo, đọc, sửa, liên kết, thay đổi quyền và xóa GPO; họ được làm việc đó ở phạm vi nào, trong thời gian nào, theo phê duyệt nào và bằng chứng nào được lưu lại.

Trong module Privileged Access Management (PAM), mục tiêu là xác định quyền thực sự cần dùng, cấp quyền tối thiểu, giới hạn thời gian thực hiện, giám sát phiên và xác minh kết quả trên hệ thống đích. Đưa mật khẩu Domain Admin vào vault không tự giải quyết bài toán phân quyền GPO.

Bài học tập trung vào GPO trong môi trường AD DS. Chính sách MDM hoặc Local Group Policy trên một máy riêng có cơ chế quản trị khác; chúng có thể cùng ảnh hưởng đến cấu hình cuối cùng nhưng không được xem là cùng một loại đối tượng quyền.

## 2. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt quyền sửa một GPO với quyền liên kết GPO đến domain hoặc OU.
- Xác định những quyền GPO có thể trở thành đường leo thang đặc quyền.
- Thiết kế phân quyền theo vai trò và mức độ nhạy cảm của hệ thống.
- Tổ chức phiên thay đổi GPO bằng quyền JIT, tài khoản quản trị riêng và PAM.
- Chuẩn bị baseline, thử nghiệm, triển khai theo đợt, kiểm tra và khôi phục.
- Thu thập bằng chứng về người thao tác, nội dung thay đổi và hiệu lực trên máy đích.

## 3. Mô hình GPO: đối tượng, nội dung, liên kết và hiệu lực

### 3.1. Những thành phần cần được bảo vệ

Có thể xem một GPO như một đối tượng logic với hai phần lưu trữ chính, được đưa vào phạm vi triển khai thông qua các liên kết:

| Thành phần | Nơi lưu | Ý nghĩa quản trị |
|---|---|---|
| Group Policy Container | Active Directory | Metadata, trạng thái và các thuộc tính liên quan đến GPO |
| Group Policy Template | SYSVOL | Các tệp cấu hình, script và nội dung phục vụ xử lý policy |
| Liên kết GPO | Site, domain hoặc OU | Xác định phạm vi có thể nhận GPO và thuộc tính của từng liên kết |

Liên kết không đồng nghĩa với quyền sửa GPO. Quyền trên GPO và quyền trên container chứa liên kết là các ranh giới quản trị khác nhau.

Các công cụ được hỗ trợ, như Group Policy Management Console (GPMC), giúp thao tác nhất quán hơn. Chỉnh trực tiếp ACL hoặc nội dung SYSVOL ngoài quy trình có thể tạo ra sai lệch giữa các thành phần và làm mất dấu vết thay đổi.

### 3.2. Luồng từ quản trị viên đến máy đích

~~~mermaid
flowchart LR
    A[Quản trị viên có quyền JIT] --> B[Sửa GPO được giao]
    B --> C[GPO trong AD và SYSVOL]
    D[Quyền quản lý liên kết tại OU] --> E[Liên kết GPO]
    C --> E
    E --> F[Phạm vi và điều kiện áp dụng]
    F --> G[Client xử lý Group Policy]
    G --> H[Cấu hình có hiệu lực]
    H --> I[Kiểm chứng và bằng chứng]
~~~

Một thay đổi được lưu thành công trong GPMC chưa chứng minh rằng máy đích đã nhận hoặc xử lý thành công. Cần xét đến phạm vi, bộ lọc, thứ tự ưu tiên, thời điểm refresh, sao chép AD/SYSVOL và kết quả của từng client-side extension.

### 3.3. Quyền sửa và phạm vi áp dụng tạo thành rủi ro kết hợp

Giả sử tài khoản A có quyền sửa GPO “Server Baseline”, nhưng không có quyền liên kết GPO đến OU mới. Nếu GPO đó đã được liên kết đến OU chứa toàn bộ máy chủ sản xuất, A vẫn có thể ảnh hưởng rộng thông qua liên kết đang tồn tại.

Ngược lại, tài khoản B không sửa được GPO nhưng có quyền quản lý liên kết ở OU quan trọng có thể thay đổi những policy nào được đưa vào phạm vi xử lý của OU đó.

Do đó, kiểm kê phải trả lời cả bốn câu hỏi:

1. Ai có thể thay đổi nội dung hoặc quyền của GPO?
2. Ai có thể thay đổi liên kết, thứ tự và thuộc tính áp dụng ở container?
3. GPO hiện đang ảnh hưởng tới những hệ thống nào?
4. Có tài nguyên phụ thuộc như script hoặc thư mục chia sẻ mà người khác có thể sửa không?

## 4. Những thao tác đặc quyền cần tách biệt

### 4.1. Các nhóm quyền thường gặp

GPMC cung cấp các mức quyền và khả năng delegation phục vụ quản trị GPO. Tên hiển thị có thể phụ thuộc ngôn ngữ giao diện, nhưng cần phân biệt ý nghĩa sau:

| Thao tác | Tác động | Cách giới hạn |
|---|---|---|
| Tạo GPO mới | Sinh đối tượng policy mới trong domain | Chỉ cấp cho nhóm có nhu cầu tạo và có quy trình xác định owner |
| Đọc GPO | Xem cấu hình hoặc phục vụ xử lý policy | Không tự coi quyền đọc là quyền quản trị |
| Sửa thiết lập | Thay đổi nội dung cấu hình của GPO | Giao đúng GPO và đúng vai trò; vẫn coi đây là quyền đặc biệt |
| Xóa GPO | Loại bỏ GPO, có thể gây gián đoạn chính sách | Tách khỏi nhu cầu chỉnh cấu hình hằng ngày khi có thể |
| Sửa bảo mật GPO | Đổi DACL, cấp thêm quyền hoặc đổi đối tượng áp dụng | Giới hạn chặt vì có thể mở rộng quyền cho người khác |
| Quản lý liên kết | Thêm, gỡ, sắp xếp hoặc đổi thuộc tính liên kết | Delegation trên đúng site, domain hoặc OU cần quản lý |
| Sửa WMI filter | Thay đổi điều kiện lựa chọn máy áp dụng | Xem là một phần của quyền kiểm soát phạm vi |
| Sửa tài nguyên phụ thuộc | Thay đổi script, gói cài đặt hoặc tệp được policy dùng | Bảo vệ đồng mức với mục đích thực thi của tài nguyên |

Các mức thường gặp trên GPO gồm “Read”, “Edit settings” và “Edit settings, delete, modify security”. Không nên cấp mức cuối cùng chỉ vì người vận hành cần sửa một số thiết lập.

“Edit settings” cũng không phải là quyền an toàn để cấp rộng. Các thiết lập khác nhau trong cùng một GPO có thể tạo ra tác động rất khác nhau. GPMC không cung cấp một mô hình phân quyền tổng quát theo từng ô cấu hình để mặc nhiên bảo đảm người sửa chỉ thay đổi đúng thiết lập đã được phê duyệt.

### 4.2. Tách quyền tạo khỏi quyền liên kết

Thành viên nhóm Group Policy Creator Owners có khả năng tạo GPO theo quyền được cấp trong domain; việc tạo không tự động trao quyền liên kết GPO đến mọi OU. Cần kiểm tra quyền thực tế và chủ sở hữu của các GPO được tạo.

Một thiết kế phổ biến là:

- Nhóm kỹ thuật được phép chuẩn bị GPO trong phạm vi quản trị được giao.
- Nhóm chịu trách nhiệm môi trường sản xuất kiểm soát việc liên kết và triển khai.
- Người duyệt kiểm tra cả nội dung GPO và phạm vi đích trước khi cấp quyền thay đổi.

Sự tách biệt này giảm khả năng một người vừa chuẩn bị nội dung nguy hiểm vừa tự mở rộng phạm vi áp dụng. Tuy nhiên, GPO đã liên kết sẵn vẫn cần kiểm soát quyền sửa nội dung nghiêm ngặt.

### 4.3. Chủ sở hữu và quyền sửa DACL

Chỉ liệt kê các nhóm có quyền “Edit settings” là chưa đủ. Chủ sở hữu đối tượng và các quyền như thay đổi DACL cũng có thể cho phép một chủ thể cấp thêm quyền theo cơ chế bảo mật của Windows.

Khi rà soát, cần xem owner, ACE trực tiếp, ACE kế thừa và thành viên lồng nhau. Một người không xuất hiện trực tiếp trên ACL vẫn có thể nhận quyền thông qua nhiều lớp nhóm.

Không nên dùng hàng loạt deny ACE để bù cho mô hình nhóm quá rộng. Các ACE deny làm việc suy luận quyền hiệu lực khó hơn và có thể gây gián đoạn. Ưu tiên loại bỏ quyền không cần thiết từ nguồn cấp và thiết kế nhóm có phạm vi rõ ràng.

## 5. Phân loại mức độ nhạy cảm

### 5.1. Phân loại theo hệ thống bị ảnh hưởng

Độ nhạy cảm của GPO phụ thuộc vào nơi nó có thể tạo ra thay đổi, không chỉ tên GPO.

| Phạm vi | Ví dụ hệ thống chịu tác động | Yêu cầu quản trị |
|---|---|---|
| Hệ thống định danh trọng yếu | Domain controller, hạ tầng phục hồi AD | Tài khoản và máy quản trị chuyên biệt; phê duyệt chặt |
| Máy chủ nghiệp vụ | Máy chủ ứng dụng, máy chủ quản lý | Quyền theo OU hoặc nhóm hệ thống; triển khai theo đợt |
| Máy trạm người dùng | Endpoint và cấu hình ứng dụng | Tách người duyệt và người thực hiện với thay đổi lớn |
| Môi trường thử nghiệm | OU lab, máy kiểm thử đại diện | Quản lý để không tạo đường truy cập ngược vào sản xuất |

Tên nhóm phân tầng do tổ chức quyết định. Điều quan trọng là tài khoản quản trị máy trạm không được có khả năng sửa policy chi phối hệ thống định danh trọng yếu.

### 5.2. Những đường vượt ranh giới dễ bị bỏ sót

Cần đặc biệt chú ý:

- GPO dùng chung được liên kết vào nhiều OU thuộc các mức độ nhạy cảm khác nhau.
- Script được lưu tại một share mà nhóm ít đặc quyền hơn có quyền ghi.
- GPO dành cho máy trạm quản trị nhưng do cùng nhóm endpoint thông thường chỉnh sửa.
- GPO vô tình thay đổi thành viên nhóm quản trị cục bộ trên máy chủ ngoài phạm vi.
- GPO có quyền sửa bảo mật được giao cho nhóm chứa tài khoản người dùng thường.

Nếu một GPO phục vụ các hệ thống có mức độ nhạy cảm khác nhau, phải bảo vệ GPO theo mức cao nhất trong phạm vi ảnh hưởng, hoặc tách thành các GPO có owner và vòng đời độc lập.

## 6. Phạm vi áp dụng: không nhầm với quyền chỉnh sửa

### 6.1. Thứ tự xử lý và kế thừa

Mô hình cơ bản của Group Policy là xử lý theo Local, Site, Domain rồi OU, với OU cha trước OU con. Khi nhiều policy cùng cấu hình một thiết lập, thứ tự và hành vi của thiết lập quyết định kết quả cuối cùng.

Trong cùng một container, thứ tự liên kết ảnh hưởng đến ưu tiên; liên kết có thứ tự 1 thường có ưu tiên cao nhất trong container đó. “Enforced” và “Block Inheritance” làm thay đổi cách kế thừa được xử lý. Một GPO còn có thể tắt phần Computer Configuration hoặc User Configuration.

Đây là mô hình nền để phân tích, không thay cho kiểm tra Resultant Set of Policy. Một số thiết lập có hành vi cộng dồn, yêu cầu đăng nhập lại hoặc khởi động lại, hoặc được xử lý theo cơ chế riêng của extension.

Enforced là thuộc tính của liên kết, không phải một cách cấp quyền sửa GPO. Block Inheritance tại OU cũng không phải biện pháp tước quyền quản trị của người đang sửa được GPO.

### 6.2. Security filtering

Để một đối tượng nhận GPO, các điều kiện về phạm vi và quyền xử lý phải phù hợp. Các quyền “Read” và “Apply Group Policy” có ý nghĩa khác nhau:

- “Read” cho phép đọc đối tượng hoặc nội dung theo quyền tương ứng.
- “Apply Group Policy” tham gia quyết định đối tượng có được áp dụng GPO hay không.
- Có quyền sửa GPO không đồng nghĩa với máy hoặc người dùng đó là đích áp dụng.

Không xóa Authenticated Users một cách máy móc chỉ vì muốn thu hẹp đối tượng áp dụng. Khi dùng security filtering cho user policy, còn phải bảo đảm máy tính liên quan có quyền đọc cần thiết trong luồng xử lý. Có thể giữ quyền đọc cho một nhóm thích hợp và cấp quyền áp dụng cho nhóm đích, nhưng phải kiểm tra bằng tài khoản và máy đại diện.

Phần Scope và Delegation trong GPMC cần được đọc cùng nhau. Việc đổi bộ lọc có thể đồng thời làm thay đổi quyền đọc hoặc quyền áp dụng theo thao tác đã thực hiện.

### 6.3. WMI filter và loopback processing

WMI filter giới hạn máy nào đáp ứng điều kiện để xử lý GPO. Điều kiện sai có thể khiến policy không áp dụng; truy vấn phức tạp còn có thể ảnh hưởng thời gian xử lý.

Loopback processing thay đổi cách chọn user policy theo vị trí của máy tính, thường xuất hiện ở máy dùng chung hoặc môi trường truy cập đặc biệt. Vì vậy, chỉ xem OU của người dùng có thể bỏ sót tác động thực tế.

Quy trình thay đổi phải ghi rõ security filter, WMI filter, loopback và các thuộc tính liên kết liên quan. Đây là những thành phần của phạm vi triển khai, không phải chi tiết phụ.

## 7. Thiết kế delegation theo least privilege

### 7.1. Một mô hình vai trò tham khảo

Giả sử tổ chức có OU “Workstations”, OU “Application Servers” và phạm vi domain controller được bảo vệ riêng.

| Vai trò | Được làm | Quyền cần tránh cấp mặc nhiên |
|---|---|---|
| Người xem và kiểm toán | Đọc cấu hình, xem báo cáo được cho phép | Chỉnh nội dung hoặc thay đổi ACL |
| Người chuẩn bị cấu hình | Sửa các GPO thử nghiệm được chỉ định | Sửa GPO sản xuất hoặc liên kết tại domain root |
| Người triển khai endpoint | Thay đổi GPO và liên kết trong phạm vi endpoint đã duyệt | Quyền đối với GPO máy chủ hoặc domain controller |
| Người triển khai máy chủ | Sửa GPO máy chủ được chỉ định theo change | Sửa bảo mật mọi GPO trong domain |
| Người quản trị nền tảng GPO | Quản lý delegation, owner và cấu trúc theo nhiệm vụ | Quyền thường trực không có giám sát |
| Người ứng cứu khẩn cấp | Quyền tạm thời theo quy trình break-glass | Bỏ qua bằng chứng và hậu kiểm |

Các vai trò cần được triển khai thành nhóm có owner, danh sách thành viên, quy tắc phê duyệt và chu kỳ rà soát.

### 7.2. Cấp quyền qua nhóm chuyên dụng

Một mẫu tên nhóm có thể là:

~~~text
GG-PAM-GPO-WS-EDIT-JIT
GG-PAM-GPO-WS-LINK-JIT
GG-PAM-GPO-SRV-EDIT-JIT
GG-PAM-GPO-SECURITY-ADMIN-JIT
~~~

Quyền được gán vào nhóm đúng phạm vi. PAM hoặc quy trình JIT kiểm soát thời gian người quản trị được tham gia nhóm, tùy khả năng của hạ tầng. JIT là cấp quyền đúng lúc; JEA có thể giới hạn các thao tác quản trị được cung cấp qua một endpoint được thiết kế phù hợp.

Không nên xem một phiên GPMC tương tác có quyền chỉnh cả GPO là “JEA theo từng thiết lập”. Nếu cần giới hạn thao tác đến mức đó, phải có cơ chế quản trị trung gian, đầu vào được kiểm tra và quyền nền được thiết kế tương ứng.

Cần phân biệt:

- Thời điểm hệ thống PAM ghi nhận cấp quyền.
- Thời điểm thành viên nhóm được sao chép hoặc nhận diện.
- Thời điểm access token hoặc phiên xác thực mới chứa quyền cần dùng.
- Thời điểm quyền được gỡ và các phiên còn tồn tại được chấm dứt.

Không nên tuyên bố “hết 30 phút là mọi quyền mất ngay” nếu chưa kiểm chứng cách token, ticket, phiên từ xa và thay đổi thành viên nhóm hoạt động trong môi trường cụ thể.

### 7.3. Tài khoản quản trị và môi trường thao tác

Người vận hành sử dụng tài khoản quản trị riêng, không dùng tài khoản đọc email hoặc duyệt web hằng ngày để quản lý GPO nhạy cảm.

Phiên có thể đi qua máy quản trị chuyên dụng hoặc jump host được PAM kiểm soát. Cần bảo vệ cả đường truy cập đến domain controller và share SYSVOL; việc ghi hình cửa sổ GPMC không tự ngăn một đường sửa khác nếu ACL hoặc kết nối vẫn cho phép.

Nếu dùng credential vault, tránh biến một tài khoản dùng chung thành danh tính duy nhất trong log. Hồ sơ phiên PAM phải ánh xạ được người thật, tài khoản được sử dụng, thời gian và change liên quan. Tài khoản định danh riêng thường giúp truy vết rõ hơn khi hạ tầng hỗ trợ.

Với credential được vault quản lý, việc cấp phát, trả lại hoặc luân chuyển phải theo cơ chế hỗ trợ của tài khoản và ứng dụng. Không thay đổi mật khẩu máy móc làm gián đoạn dịch vụ hoặc bỏ qua việc kết thúc phiên đang tồn tại.

## 8. Quy trình thay đổi GPO trong PAM

### 8.1. Hồ sơ trước khi xin quyền

Một yêu cầu thay đổi cần nêu tối thiểu:

~~~text
Change ID: CHG-EXAMPLE-042
Mục tiêu: Điều chỉnh một thiết lập bảo mật đã được duyệt
GPO: Tên hiển thị và GUID chính xác
Phạm vi: OU và nhóm máy đích cụ thể
Thiết lập: Đường dẫn chính sách, giá trị trước và sau
Tác động: Dịch vụ, người dùng, thời điểm có hiệu lực
Quyền cần cấp: Sửa nội dung; quyền liên kết nếu thực sự cần
Thời gian: Cửa sổ thực hiện và thời hạn quyền JIT
Thử nghiệm: Máy đại diện, tiêu chí thành công và thất bại
Khôi phục: Backup, cấu hình trước, cách phục hồi liên kết
Bằng chứng: Báo cáo GPO, log, kết quả client và hồ sơ PAM
~~~

GUID giúp tránh nhầm các GPO có tên giống nhau hoặc đã đổi tên. Tên hiển thị vẫn có ích cho vận hành nhưng không nên là định danh duy nhất trong bằng chứng.

### 8.2. Trình tự vận hành

1. Người yêu cầu mô tả thay đổi và phạm vi.
2. Chủ sở hữu dịch vụ và người duyệt bảo mật đánh giá theo mức rủi ro.
3. Người thực hiện chụp baseline và xác nhận phương án khôi phục.
4. PAM cấp quyền tối thiểu trong cửa sổ đã duyệt.
5. Người thực hiện mở phiên quản trị phù hợp và xác minh danh tính.
6. Thử thay đổi trên phạm vi pilot hoặc GPO thử nghiệm được chuẩn bị trước.
7. Đối chiếu báo cáo trước và sau, rồi triển khai theo đợt.
8. Kiểm tra hiệu lực và sức khỏe dịch vụ trên hệ thống đích.
9. Kết thúc phiên, thu hồi quyền và kiểm tra việc thu hồi.
10. Lưu bằng chứng, xác nhận kết quả và đóng change.

Một người có quyền “Edit settings” vẫn có thể thay đổi nội dung ngoài hồ sơ. Vì vậy, phê duyệt phải đi cùng so sánh nội dung trước và sau, giám sát thao tác và rà soát kết quả.

### 8.3. Thay đổi có nguy cơ khóa đường quản trị

Thay đổi quyền đăng nhập, cấu hình tường lửa, hạn chế truy cập từ xa hoặc nhóm quản trị cục bộ có thể làm mất đường khôi phục.

Trước khi triển khai, cần kiểm tra:

- Đường quản trị dự phòng có thực sự hoạt động hay không.
- Tài khoản phục hồi có chịu ảnh hưởng của cùng GPO hay không.
- Pilot có đại diện cho sản xuất về vai trò, OU và bộ lọc hay không.
- Điều kiện nào buộc dừng triển khai.
- Người chịu trách nhiệm quyết định khôi phục khi phiên chính bị mất.

Không thử thay đổi có khả năng làm khóa toàn bộ đường quản trị trực tiếp trên domain root hoặc toàn bộ OU máy chủ.

## 9. Kiểm kê và tạo bằng chứng bằng công cụ quản trị

Các ví dụ dưới đây giả định Group Policy PowerShell module và RSAT phù hợp đã được cài, tài khoản có quyền cần thiết và thư mục đầu ra được phê duyệt đã tồn tại.

Tên domain, OU, GUID và đường dẫn đều là ví dụ; cần thay bằng giá trị đã xác minh. Báo cáo có thể chứa cấu hình nhạy cảm nên phải lưu tại nơi có ACL phù hợp.

### 9.1. Xác định GPO bằng GUID và xem quyền

~~~powershell
Import-Module GroupPolicy

$gpoId = [guid]'11111111-2222-3333-4444-555555555555'
$domainName = 'corp.example'

Get-GPO -Guid $gpoId -Domain $domainName |
    Select-Object DisplayName, Id, Owner, GpoStatus,
        CreationTime, ModificationTime

Get-GPPermission -Guid $gpoId -Domain $domainName -All |
    Select-Object Trustee, Permission, Inherited
~~~

Kết quả giúp nhận diện các trustee và mức quyền được công cụ biểu diễn. Nó không tự tính đầy đủ mọi đường quyền qua nhóm lồng nhau hoặc thay thế việc kiểm tra quyền trên OU và tài nguyên phụ thuộc.

Để xác nhận quyền hiệu lực, cần kết hợp danh sách thành viên nhóm, ACL thực tế, owner và phạm vi liên kết. Không tự động xóa một ACE chỉ vì tên nhóm lạ; hãy xác định owner và phụ thuộc trước.

### 9.2. Xem kế thừa và liên kết tại OU

~~~powershell
$targetOu = 'OU=Workstations,DC=corp,DC=example'

$inheritance = Get-GPInheritance -Target $targetOu -Domain $domainName

$inheritance |
    Select-Object Path, GpoInheritanceBlocked

$inheritance.GpoLinks |
    Select-Object DisplayName, GpoId, Enabled, Enforced, Order

$inheritance.InheritedGpoLinks |
    Select-Object DisplayName, GpoId, Enabled, Enforced, Order
~~~

Lệnh này cho thông tin liên kết và kế thừa tại phạm vi được hỏi. Không nên lấy một lần đọc tại OU cha rồi kết luận tất cả OU con có cùng kết quả. Quyền delegation trên OU cũng cần được kiểm tra riêng bằng công cụ xem bảo mật AD được phê duyệt.

### 9.3. Xuất báo cáo và tạo backup

Xuất báo cáo là hoạt động đọc cấu hình nhưng ghi tệp bằng chứng. Backup tạo thêm dữ liệu sao lưu; hãy dùng vị trí có kiểm soát truy cập.

~~~powershell
$evidenceDirectory = 'C:\PAM-Evidence\CHG-EXAMPLE-042'
$backupDirectory = 'C:\PAM-Backup\CHG-EXAMPLE-042'

$xmlBefore = Join-Path $evidenceDirectory 'gpo-before.xml'
$htmlBefore = Join-Path $evidenceDirectory 'gpo-before.html'

Get-GPOReport -Guid $gpoId -Domain $domainName -ReportType Xml -Path $xmlBefore
Get-GPOReport -Guid $gpoId -Domain $domainName -ReportType Html -Path $htmlBefore

Backup-GPO -Guid $gpoId -Domain $domainName -Path $backupDirectory
~~~

Nên lưu thêm GUID, domain, thời điểm, người xuất và định danh bản backup. Cấu hình đã xuất có thể tiết lộ đường dẫn nội bộ hoặc chính sách bảo mật, vì vậy không đưa vào kho công khai.

Backup GPO không phải bản sao toàn bộ cấu trúc OU, liên kết, thành viên nhóm và mọi tài nguyên mà policy tham chiếu. Những phần này cần có bằng chứng và phương án phục hồi tương ứng.

Sau thay đổi, xuất báo cáo mới vào tệp riêng và so sánh với baseline. Không ghi đè bản trước; giữ được hai trạng thái giúp đánh giá những thay đổi ngoài yêu cầu.

## 10. Kiểm chứng trên máy đích

### 10.1. Không đồng nhất “đã sửa” với “đã áp dụng”

Bốn mốc cần tách biệt:

| Mốc | Điều được xác nhận | Điều chưa được xác nhận |
|---|---|---|
| Đã lưu | Công cụ quản trị ghi nhận thay đổi | Các domain controller đã hội tụ |
| Đã sao chép phù hợp | AD và SYSVOL được kiểm tra theo quy trình | Client đã nhận và xử lý |
| Đã xử lý trên client | Có kết quả Group Policy và log tương ứng | Dịch vụ nghiệp vụ vẫn hoạt động đúng |
| Đã nghiệm thu | Thiết lập và hành vi trên mẫu kiểm tra đạt yêu cầu | Mọi máy ngoài mẫu đều đã hội tụ |

Triển khai theo đợt giúp tăng dần mức bao phủ kiểm tra mà vẫn kiểm soát tác động.

Nếu trạng thái giữa các domain controller chưa thống nhất, việc kết nối tới các máy chủ khác nhau có thể cho kết quả quan sát khác nhau. Cần xác định domain controller được dùng và phối hợp kiểm tra sao chép thay vì liên tục sửa lại GPO.

### 10.2. Kiểm tra Resultant Set of Policy

Trên máy pilot, với ngữ cảnh và quyền phù hợp:

~~~powershell
gpresult /r
gpresult /h "C:\PAM-Evidence\CHG-EXAMPLE-042\pilot-gpresult.html"
~~~

Báo cáo giúp xác định GPO đã áp dụng, GPO bị lọc và thông tin xử lý của máy hoặc người dùng trong ngữ cảnh được thu thập. Với phần computer và user, phải bảo đảm báo cáo phản ánh đúng đối tượng đang kiểm tra.

Kết hợp báo cáo này với kênh log Microsoft-Windows-GroupPolicy/Operational, log lỗi của extension liên quan và kiểm tra trực tiếp thiết lập hoặc hành vi nghiệp vụ.

Nếu cần chủ động refresh, có thể dùng lệnh như sau trong cửa sổ đã duyệt:

~~~powershell
gpupdate /target:computer
~~~

Một số thay đổi cần đăng xuất hoặc khởi động lại. Refresh không bảo đảm mọi thiết lập có hiệu lực ngay, và ép refresh đồng loạt có thể tạo tải hoặc gián đoạn. Chỉ dùng phạm vi và cách thực hiện phù hợp với change.

### 10.3. Kiểm tra quyền JIT

Ngoài kết quả policy, cần xác minh:

- Người thực hiện chỉ có quyền trên GPO và container được phê duyệt.
- Phiên sử dụng đúng tài khoản và máy quản trị.
- Không có thành viên nhóm hoặc ACL mới ngoài yêu cầu.
- Quyền tạm thời đã được gỡ sau khi hoàn tất.
- Phiên và thông tin xác thực còn hiệu lực được xử lý theo cơ chế thu hồi của PAM.

Không kiểm tra bằng cách cố sửa thử GPO nhạy cảm ngoài phạm vi. Có thể đánh giá quyền bằng công cụ đọc, nhóm thử nghiệm và môi trường đã được cấp phép.

## 11. Bằng chứng và khả năng kiểm toán

### 11.1. Một chuỗi truy vết hoàn chỉnh

Một hồ sơ tốt phải nối được các thông tin:

~~~text
Người thật
  -> yêu cầu thay đổi
  -> người phê duyệt
  -> quyền và thời hạn được cấp
  -> tài khoản cùng phiên quản trị
  -> GUID GPO và phạm vi liên kết
  -> nội dung trước/sau
  -> kết quả trên client
  -> thu hồi quyền và đóng change
~~~

Chỉ có video phiên không đủ để hiểu chính xác trạng thái cấu hình trước và sau. Chỉ có bản diff cũng không đủ để biết người nào thực hiện qua tài khoản dùng chung. Các nguồn bằng chứng bổ sung cho nhau.

Bằng chứng cần có thời gian nhất quán, vị trí lưu được bảo vệ và thời hạn lưu theo quy định nội bộ. Tránh để người có quyền sửa GPO đồng thời tự xóa mọi dấu vết trong kho bằng chứng.

### 11.2. Các nguồn log

Có thể sử dụng:

- Log PAM: phê duyệt, cấp quyền, mở phiên, kết thúc phiên và thu hồi.
- Security log trên domain controller khi audit policy và SACL phù hợp đã được cấu hình.
- Dấu vết thay đổi đối tượng AD, gồm metadata GPO và thuộc tính liên kết.
- Theo dõi thay đổi tệp và quyền trong SYSVOL theo khả năng hệ thống.
- Báo cáo GPO trước và sau.
- Log xử lý Group Policy và kết quả kiểm tra trên máy đích.

Ví dụ, sự kiện Directory Service Changes như 5136 có thể hỗ trợ quan sát thay đổi đối tượng AD khi điều kiện audit phù hợp. Không nên coi một Event ID là nguồn duy nhất hoặc mặc định cho mọi thay đổi GPO. Nội dung trong SYSVOL và liên kết ở container có thể cần nguồn theo dõi riêng.

### 11.3. Những thay đổi cần cảnh báo

Ưu tiên phát hiện:

- Thêm nhóm có quyền sửa GPO hoặc thay đổi bảo mật GPO.
- GPO nhạy cảm được đổi owner.
- Thay đổi script, tác vụ theo lịch hoặc thiết lập có thể thực thi với quyền cao.
- Liên kết GPO mới tại domain root hoặc OU trọng yếu.
- Đổi Enforced, Block Inheritance, security filter hoặc WMI filter ngoài change.
- GPO bị vô hiệu hóa hoặc phần Computer/User bị tắt.
- Người thực hiện thay đổi ngoài phiên hoặc ngoài thời gian được phê duyệt.
- Quyền JIT không được gỡ hoặc nhóm được thêm thành viên thường trực.

Cảnh báo cần kèm GUID, đối tượng bị ảnh hưởng, tài khoản, thời điểm và change liên quan. Chỉ cảnh báo “GPO changed” thường chưa đủ để người trực quyết định mức độ ưu tiên.

## 12. Khôi phục và xử lý sự cố

### 12.1. Khôi phục theo loại thay đổi

Không phải mọi sự cố đều được giải quyết bằng cách gỡ liên kết.

| Sự cố | Hướng xử lý cần đánh giá |
|---|---|
| Thiết lập sai trong GPO | Đưa giá trị về baseline đã duyệt hoặc phục hồi GPO phù hợp |
| Liên kết sai OU | Khôi phục liên kết, thứ tự và thuộc tính trước thay đổi |
| Security filter sai | Phục hồi quyền đọc/áp dụng và kiểm tra lại đối tượng đích |
| ACL GPO bị mở rộng | Thu hồi quyền trái phép, xác minh owner và các đường cấp quyền |
| Script phụ thuộc bị đổi | Phục hồi tài nguyên, kiểm tra quyền ghi và phạm vi thực thi |
| Thay đổi đã tạo hiệu ứng trên máy | Sửa trạng thái còn lại nếu gỡ policy không tự hoàn nguyên |

Một số thiết lập hoặc hành động do policy kích hoạt có thể để lại trạng thái sau khi policy không còn áp dụng. Vì vậy, “unlink” không đồng nghĩa với “rollback toàn bộ”.

Khi dùng backup, cần kiểm tra đúng domain, GPO, bản backup và trạng thái mục tiêu. Phục hồi một GPO có thể đưa nhiều thiết lập về phiên bản cũ, bao gồm những thay đổi hợp lệ đã diễn ra sau thời điểm backup. Phải xem xét xung đột trước khi thực hiện.

### 12.2. Kịch bản nghi ngờ GPO bị lạm dụng

1. Xác định GPO, liên kết và hệ thống có thể đã chịu ảnh hưởng.
2. Kích hoạt quy trình ứng cứu và phân công người có quyền quyết định.
3. Bảo toàn log, báo cáo và dữ liệu liên quan theo khả năng thực tế.
4. Hạn chế đường chỉnh sửa trái phép, tài khoản hoặc phiên bị nghi ngờ.
5. Ngăn tác động tiếp tục lan rộng bằng biện pháp đã đánh giá về vận hành.
6. Phục hồi cấu hình và tài nguyên liên quan từ baseline đáng tin cậy.
7. Kiểm tra máy đích, thông tin xác thực và dấu hiệu tồn tại dai dẳng.
8. Rà soát nguyên nhân gốc: ACL, nhóm lồng nhau, JIT, máy quản trị hay tài nguyên phụ thuộc.

Không xóa ngay GPO hoặc log chỉ để làm cảnh báo biến mất. Đồng thời, bảo toàn bằng chứng không có nghĩa là phải trì hoãn mọi biện pháp ngăn chặn khi hệ thống vẫn đang bị ảnh hưởng; đội ứng cứu phải cân nhắc hai mục tiêu trong tình huống cụ thể.

Sau sự cố, cần xem lại các quyền thường trực và đường quản trị thay thế. Khôi phục nội dung GPO nhưng giữ nguyên tài khoản hoặc ACL bị xâm phạm có thể cho phép sự cố tái diễn.

## 13. Tình huống thực tế: giao quyền cho đội endpoint

### Bối cảnh

Đội endpoint cần quản lý baseline cho máy trạm. Trước đây, một nhóm quản trị dùng chung có thể sửa nhiều GPO, bao gồm cả GPO máy chủ. Tổ chức muốn chuyển sang PAM và giảm quyền thường trực.

### Phân tích

Chỉ đưa mật khẩu tài khoản chung vào vault chưa giải quyết được phạm vi quyền. Cần xác định các GPO đội endpoint thực sự dùng, nơi chúng được liên kết và những chủ thể khác có thể sửa tài nguyên phụ thuộc.

Đội kiểm kê phát hiện GPO “Common Security Settings” được dùng cho cả máy trạm và máy chủ. Nếu giao quyền sửa GPO này cho đội endpoint, quyền thực tế vẫn vượt quá phạm vi công việc.

### Thiết kế

- Tách baseline theo phạm vi có owner và vòng đời quản trị phù hợp.
- Gán quyền sửa GPO máy trạm vào nhóm JIT chuyên dụng.
- Giao quyền quản lý liên kết tại OU máy trạm cho vai trò được duyệt riêng.
- Giới hạn quyền sửa ACL và xóa GPO cho vai trò nền tảng có kiểm soát.
- Dùng tài khoản quản trị riêng trên môi trường thao tác được bảo vệ.
- Thực hiện pilot và đối chiếu báo cáo trước/sau.
- Theo dõi nội dung, liên kết, quyền và tài nguyên tham chiếu.

### Tiêu chí nghiệm thu

Đội endpoint thực hiện được nhiệm vụ đã duyệt mà không nhận quyền sửa GPO máy chủ; thay đổi có bằng chứng; quyền hết hạn được kiểm chứng; máy pilot và nhóm triển khai đạt tiêu chí kỹ thuật.

Việc tách GPO phải có thử nghiệm vì có thể thay đổi ưu tiên hoặc tương tác cấu hình. Không sao chép, tách rồi liên kết hàng loạt mà bỏ qua phân tích trạng thái có hiệu lực.

## 14. Bài thực hành có kiểm soát

Thực hành trong domain lab hoặc phạm vi được cho phép. Dùng một GPO thử nghiệm, một OU pilot và một thiết lập ít ảnh hưởng do người hướng dẫn lựa chọn.

### Phần A — Lập bản đồ quyền

1. Ghi GUID, owner và trạng thái GPO.
2. Liệt kê trustee có quyền đọc, sửa và sửa bảo mật.
3. Xác định nhóm lồng nhau dẫn đến người vận hành.
4. Liệt kê liên kết và thuộc tính liên kết trong phạm vi lab.
5. Xác định tài khoản có thể quản lý liên kết tại OU pilot.
6. Kiểm tra GPO có tham chiếu tệp hoặc script bên ngoài không.

Sản phẩm là bảng thể hiện rõ “ai có thể đổi nội dung”, “ai có thể đổi phạm vi” và “máy nào có thể chịu ảnh hưởng”.

### Phần B — Thực hiện một change JIT

1. Chuẩn bị yêu cầu với thiết lập trước/sau và tiêu chí kiểm tra.
2. Xuất báo cáo và tạo backup ở nơi được duyệt.
3. Nhận quyền tạm thời cho đúng GPO.
4. Xác minh quyền bằng phiên mới nếu cơ chế xác thực yêu cầu.
5. Sửa đúng thiết lập thử nghiệm và lưu báo cáo sau thay đổi.
6. Kiểm tra kết quả trên máy pilot.
7. Đóng phiên và xác minh thu hồi quyền.

Không dùng Domain Admin chỉ để tránh xử lý delegation trong bài tập. Nếu công việc thất bại, xác định thiếu quyền nào trước khi cân nhắc mở rộng quyền.

### Phần C — Diễn tập khôi phục

Khôi phục giá trị thử nghiệm về trạng thái trước đó theo kế hoạch. Nếu có thay đổi liên kết hoặc filter, khôi phục riêng các thành phần đó. Kiểm tra lại cả policy và trạng thái client.

Bằng chứng cuối cùng phải cho thấy người thực hiện, quyền được cấp, nội dung thay đổi, kết quả áp dụng, khôi phục và thu hồi quyền.

## 15. Những lỗi thiết kế thường gặp

| Lỗi | Vì sao có vấn đề | Cách điều chỉnh |
|---|---|---|
| Mọi người quản trị GPO đều là Domain Admin | Quyền vượt xa nhiệm vụ | Delegation theo GPO và container; quyền tạm thời |
| Chỉ kiểm kê GPO ACL | Bỏ sót liên kết, owner và tài nguyên phụ thuộc | Đánh giá toàn bộ đường điều khiển |
| Cho rằng người sửa GPO phải là đích áp dụng | Nhầm quyền quản trị với quyền xử lý policy | Phân tích hai nhóm quyền riêng |
| Cấp “delete, modify security” cho việc chỉnh thiết lập | Có thể mở rộng quyền hoặc xóa ngoài nhu cầu | Cấp mức tối thiểu và kiểm tra quyền hiệu lực |
| Tự động xóa Authenticated Users khỏi mọi GPO | Có thể làm hỏng quyền đọc cần cho xử lý | Thiết kế Read/Apply rõ ràng và thử trên client |
| Dùng chung GPO giữa các phạm vi nhạy cảm | Nhóm ít đặc quyền có thể ảnh hưởng hệ thống nhạy cảm | Tách vòng đời hoặc bảo vệ theo phạm vi cao nhất |
| Chỉ xem video PAM | Không đủ chứng minh cấu hình cuối cùng | Bổ sung báo cáo, diff và kết quả client |
| Hết JIT nhưng giữ phiên quản trị | Token hoặc phiên có thể còn khả năng truy cập | Kiểm chứng thu hồi và kết thúc phiên |
| Có backup GPO nên bỏ qua liên kết | Backup không bao phủ toàn bộ cấu trúc triển khai | Lưu riêng topology, filter và phụ thuộc |
| Unlink được xem là rollback hoàn toàn | Hiệu ứng đã tạo có thể còn lại | Kiểm tra trạng thái thực tế trên máy |

## 16. Câu hỏi tự kiểm tra

**1. Một người không có quyền liên kết GPO có thể ảnh hưởng hàng nghìn máy không?**

Có, nếu họ sửa được GPO đang liên kết và áp dụng trên các máy đó. Phải đánh giá quyền sửa cùng phạm vi liên kết hiện tại.

**2. Vì sao quyền “Edit settings” vẫn phải đi qua PAM?**

Vì nội dung GPO có thể ảnh hưởng đến cấu hình bảo mật và hành vi thực thi trên hệ thống đích. Không có quyền sửa ACL không làm mất rủi ro từ nội dung có thể sửa.

**3. Người được quản lý liên kết OU có cần quyền sửa nội dung GPO để tạo rủi ro không?**

Không nhất thiết. Thay đổi tập GPO được liên kết, thứ tự hoặc thuộc tính áp dụng có thể làm thay đổi cấu hình có hiệu lực, tùy các quyền và điều kiện liên quan.

**4. Vì sao báo cáo trước/sau chưa đủ để đóng change?**

Báo cáo cho biết cấu hình đã lưu, nhưng chưa chứng minh client xử lý thành công hoặc dịch vụ hoạt động đúng. Cần kiểm tra máy đích và xác minh thu hồi quyền.

**5. Nhóm JIT bị xóa thành viên có đồng nghĩa mọi phiên mất quyền ngay không?**

Không thể kết luận như vậy. Cần xét token, ticket, kết nối, sao chép và cơ chế chấm dứt phiên, sau đó kiểm chứng kết quả.

**6. Vì sao cần bảo vệ script được GPO tham chiếu?**

Nếu người khác sửa được script, họ có thể tác động đến nội dung được thực thi mà không cần sửa chính GPO. Quyền ghi tài nguyên phụ thuộc có thể trở thành một đường đặc quyền.

**7. Khi gỡ liên kết, có cần kiểm tra trạng thái máy nữa không?**

Có. Một số cấu hình hoặc hành động có thể để lại hiệu ứng. Phải xác minh trạng thái cuối cùng thay vì chỉ nhìn liên kết.

## 17. Các nguyên tắc cần ghi nhớ

Quyền quản trị Group Policy là quyền đặc biệt vì nó có thể biến thành khả năng điều khiển cấu hình và hành vi của nhiều hệ thống. Mức rủi ro được quyết định bởi quyền trên GPO, quyền trên liên kết, phạm vi đích và tài nguyên phụ thuộc.

Một thiết kế PAM tốt cấp đúng quyền cho đúng GPO và container, giới hạn thời gian, sử dụng danh tính truy vết được, thử nghiệm theo phạm vi nhỏ và kiểm tra cấu hình thực tế trên client.

Một thay đổi chỉ nên được coi là hoàn tất về vận hành khi nội dung, phạm vi, hiệu lực, sức khỏe dịch vụ và thu hồi quyền đều có bằng chứng phù hợp.
