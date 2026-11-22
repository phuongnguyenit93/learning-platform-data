# Quy trình ứng phó sự cố và bảo toàn bằng chứng trên OCI

## 1. Mục tiêu và phạm vi

Trong chương **An toàn thông tin và kiểm toán** của module Oracle Cloud Infrastructure (OCI), bài này hướng dẫn tổ chức ứng phó sự cố từ lúc nhận tín hiệu đến khi khôi phục dịch vụ và hoàn tất hồ sơ bằng chứng.

Phạm vi bao gồm tenancy, compartment, IAM, VCN, Compute, Object Storage và các dịch vụ cơ sở dữ liệu Oracle. Trọng tâm là phối hợp hành động kỹ thuật với khả năng giải thích: ai đã quyết định, đã thay đổi gì, dữ liệu được thu từ đâu và còn giới hạn nào khi kết luận.

Sau bài học, người học có thể:

- Phân loại tín hiệu, xác định phạm vi và phân công người xử lý.
- Chọn hành động cô lập phù hợp với loại tài nguyên và credential.
- Thu thập log, cấu hình và bản sao volume mà vẫn ghi nhận tác động lên hệ thống.
- Lập manifest, tính SHA-256 và duy trì chuỗi bàn giao bằng chứng.
- Thiết kế nơi lưu bằng chứng với phân quyền, retention và khả năng giải mã.
- Thực hành xuất Audit bằng OCI CLI trên PowerShell và kiểm tra bản lưu.
- Đặt tiêu chí khôi phục cùng các chỉ số cải thiện sau sự cố.

Các biểu mẫu, vai trò, mức ưu tiên và tiêu chí trong bài là phương án vận hành đề xuất. Chúng cần được điều chỉnh theo cơ cấu và yêu cầu thực tế của tổ chức.

## 2. Những khái niệm cần phân biệt

| Khái niệm | Ý nghĩa trong quy trình | Ví dụ |
| --- | --- | --- |
| Event | Một sự kiện được ghi lại | Một API được gọi |
| Alert hoặc finding | Tín hiệu cần xem xét | Cloud Guard báo cấu hình đáng chú ý |
| Incident | Sự cố đã được đánh giá là cần quy trình ứng phó | Credential bị sử dụng trái phép |
| Artifact | Dữ liệu thu được trong điều tra | File log, cấu hình NSG, backup volume |
| Evidence | Artifact được quản lý cùng nguồn gốc và hồ sơ bảo quản | Bản xuất Audit có phạm vi, hash và người thu |
| Containment | Hạn chế tổn hại tiếp diễn | Thu hồi credential hoặc chặn luồng truy cập |
| Eradication | Loại bỏ nguyên nhân và cơ chế duy trì truy cập | Gỡ quyền trái phép, triển khai lại từ nguồn tin cậy |
| Recovery | Đưa dịch vụ trở lại có kiểm chứng | Chuyển lưu lượng sang hệ thống sạch |

Một cảnh báo chưa chứng minh có xâm nhập. Ngược lại, việc không thấy cảnh báo chưa đủ chứng minh không có hoạt động trái phép.

Trong hồ sơ, tách ba loại phát biểu:

~~~text
Dữ kiện: API cập nhật cấu hình được ghi nhận lúc 02:12Z.
Giả thuyết: Credential của pipeline có thể đã bị lộ.
Kết luận tạm thời: Cần kiểm tra credential và nguồn gọi trước khi quy trách nhiệm.
~~~

Định danh principal cho biết danh tính kỹ thuật đã được sử dụng; muốn xác định người thực hiện còn cần đối chiếu hệ thống xác thực, pipeline, máy quản trị và bối cảnh quyền truy cập.

## 3. Chuẩn bị trước khi có sự cố

### 3.1. Vai trò và quyền quyết định

Oracle khuyến nghị có kế hoạch ứng phó, quy trình thông tin, cơ chế chuyển cấp và phối hợp với các bên liên quan. Việc bảo toàn bằng chứng cần được đặt trong quy trình đó. [Oracle: Risk and Compliance](https://docs.oracle.com/en-us/iaas/Content/cloud-adoption-framework/risk-and-compliance.htm).

Một mô hình phân công có thể dùng:

| Vai trò | Trách nhiệm |
| --- | --- |
| Incident commander | Chốt mức ưu tiên, phân công và quyết định các đánh đổi |
| Điều tra viên | Thu thập, phân tích và ghi giới hạn của dữ liệu |
| Người quản lý bằng chứng | Quản lý bản lưu, manifest, quyền đọc và bàn giao |
| Chủ dịch vụ | Đánh giá tác động ứng dụng, RTO và tiêu chí phục hồi |
| Quản trị IAM/mạng/DB | Thực hiện thay đổi đúng chuyên môn và phạm vi |
| Đầu mối pháp chế, tuân thủ, truyền thông | Xác định nghĩa vụ thông báo và nội dung được chia sẻ |
| Đầu mối Oracle Support | Chuyển thông tin về phần dịch vụ cần nhà cung cấp hỗ trợ |

Với nhóm nhỏ, một người có thể kiêm nhiệm, nhưng nên có người thứ hai kiểm tra các quyết định có ảnh hưởng lớn hoặc việc tiếp nhận bằng chứng quan trọng.

Runbook cần quy định trước ai được thu hồi credential, cô lập Compute, thay routing, hạn chế database hoặc chuyển dịch vụ sang môi trường phục hồi.

### 3.2. Chuẩn bị công cụ và kho lưu

Chuẩn bị trước các thành phần sau:

- Tài khoản ứng cứu độc lập với credential thường dùng của workload.
- Máy thu thập tin cậy, OCI CLI và công cụ điều tra đã được kiểm chứng.
- Compartment dành cho bằng chứng, nhóm quyền riêng và bucket private.
- Quyền đọc Audit, log và cấu hình trong các compartment, region liên quan.
- Logging cho các nguồn cần thiết; cơ chế xuất và theo dõi lỗi chuyển log.
- Dung lượng, quota và ngân sách dự phòng cho backup, bản phân tích và dịch vụ phục hồi.
- Danh sách liên hệ và kênh phối hợp còn dùng được khi IAM hoặc email bị ảnh hưởng.

Hãy diễn tập tình huống người trực không sử dụng được tài khoản quản trị thường ngày. Quyền ứng cứu cần đủ cho nhiệm vụ, được ghi log và được rà soát sau mỗi lần sử dụng.

### 3.3. Quy tắc ghi nhận thời gian và định danh

Mỗi sự cố nên có mã riêng, ví dụ `IR-2026-0042`. Mỗi artifact có evidence ID, chẳng hạn `E-001`.

Dùng UTC làm mốc đối chiếu và giữ nguyên timestamp gốc trong artifact. Nếu hiển thị giờ Việt Nam, ghi rõ UTC+07:00; không đổi timestamp của file gốc chỉ để làm báo cáo dễ đọc.

Ghi đồng thời:

- Tenancy OCID, compartment OCID và region.
- OCID tài nguyên, principal và credential identifier nếu nguồn có.
- Thời gian sự kiện, thời gian nhận dữ liệu và thời gian thu thập.
- Múi giờ, tình trạng đồng bộ đồng hồ và sai lệch đã biết của máy thu.
- Câu lệnh, phiên bản công cụ và phạm vi truy vấn.

Không dùng display name làm định danh duy nhất vì tên có thể thay đổi hoặc trùng nhau.

## 4. Luồng ứng phó và bằng chứng cần tạo

~~~mermaid
flowchart TD
    A["Tín hiệu từ Cloud Guard, log hoặc người dùng"] --> B["Đánh giá và mở hồ sơ"]
    B --> C{"Có tổn hại đang tiếp diễn?"}
    C -->|"Có"| D["Cô lập ưu tiên theo quyền quyết định"]
    C -->|"Chưa xác định"| E["Thu dữ kiện ban đầu và xác minh"]
    D --> F["Thu thập bằng chứng trong và sau cô lập"]
    E --> F
    F --> G["Phân tích phạm vi và nguyên nhân"]
    G --> H["Loại bỏ nguyên nhân và phục hồi"]
    H --> I["Xác minh, theo dõi và đánh giá sau sự cố"]
    F --> J["Manifest và chuỗi bàn giao"]
    J --> G
~~~

Thu thập và cô lập thường diễn ra song song. Khi có nguy cơ mất dữ liệu hoặc lan rộng đang tiếp diễn, người có thẩm quyền có thể ưu tiên ngăn tổn hại và ghi rõ bằng chứng nào có thể bị mất do quyết định đó.

| Giai đoạn | Câu hỏi chính | Hồ sơ đầu ra |
| --- | --- | --- |
| Tiếp nhận | Tín hiệu có đáng tin và cần chuyển cấp không? | Nguồn báo, thời điểm, người tiếp nhận |
| Đánh giá | Tài nguyên, danh tính và dữ liệu nào liên quan? | Phạm vi ban đầu, dữ kiện và giả thuyết |
| Cô lập | Cách nào hạn chế tổn hại với tác động phù hợp? | Quyết định, cấu hình trước/sau và kết quả kiểm tra |
| Thu thập, phân tích | Dữ liệu có cho phép dựng lại diễn biến không? | Artifact, manifest, timeline, giới hạn |
| Loại bỏ, phục hồi | Nguyên nhân và đường truy cập đã được xử lý chưa? | Bản sửa, nguồn triển khai sạch và kiểm chứng |
| Đánh giá sau sự cố | Cần thay đổi kiểm soát nào? | Nguyên nhân, bài học, người phụ trách và hạn hoàn thành |

Một giai đoạn có thể được mở lại khi phát hiện mới làm thay đổi phạm vi. Ví dụ, thấy credential được dùng ở region khác phải mở rộng điều tra thay vì giữ nguyên kết luận từ region đầu tiên.

## 5. Đánh giá ban đầu: ưu tiên đúng vấn đề

### 5.1. Thu thông tin tối thiểu

Ngay khi mở hồ sơ, ghi:

1. Nguồn tín hiệu, thời điểm phát hiện và mã problem/alert nếu có.
2. Tài nguyên và tài khoản được nhắc đến.
3. Môi trường production, development hay phòng thực hành.
4. Dấu hiệu mất tính bí mật, toàn vẹn hoặc sẵn sàng.
5. Thay đổi hợp lệ gần đây có thể giải thích tín hiệu.
6. Hành động đã xảy ra, kể cả automation và thao tác của người vận hành.

Một thang ưu tiên nội bộ có thể dựa trên các tình huống:

| Tình huống | Ưu tiên đề xuất | Trọng tâm ban đầu |
| --- | --- | --- |
| Đang có truy cập trái phép vào dữ liệu quan trọng | Khẩn cấp | Hạn chế truy cập và bảo toàn dấu vết |
| Credential có quyền quản trị bị nghi lộ | Cao | Kiểm tra phạm vi quyền và mọi đường xác thực |
| Một cấu hình public chưa có bằng chứng truy cập | Theo độ nhạy dữ liệu | Xác minh đối tượng bị phơi bày |
| Hành động quản trị khác thường nhưng trùng thay đổi đã duyệt | Cần xác minh | Đối chiếu định danh, thời gian và request |

Đây không phải phân loại mặc định của OCI. Một tài nguyên nhỏ vẫn có thể dẫn đến sự cố lớn nếu nó nắm credential truy cập hệ thống quan trọng.

### 5.2. Lập ma trận phạm vi

Đánh dấu từng tổ hợp compartment và region là **đã thu**, **đang thu**, **không có nguồn** hoặc **chưa kiểm tra**.

Mở rộng từ tài nguyên đầu tiên sang:

- IAM policies, group membership, dynamic groups và credential liên quan.
- Các Compute, VNIC, volume, bucket hoặc database mà principal có thể truy cập.
- Pipeline, secret, registry và hệ thống ứng dụng sử dụng cùng danh tính.
- Các region khác đã đăng ký và các compartment khác trong phạm vi quyền.

Ghi rõ lý do loại một nhánh khỏi phạm vi. Không coi truy vấn rỗng tại một compartment là bằng chứng cho toàn tenancy.

## 6. Chọn nguồn bằng chứng trên OCI

### 6.1. Bản đồ nguồn và giới hạn

| Nguồn | Câu hỏi hỗ trợ trả lời | Giới hạn cần ghi |
| --- | --- | --- |
| OCI Audit | API nào được gọi, bởi danh tính nào, trên tài nguyên nào? | Không thay thế log bên trong hệ điều hành hoặc SQL audit |
| Cloud Guard | Problem nào xuất hiện và có phản ứng gì? | Finding là điểm bắt đầu điều tra |
| IAM và IdP | Xác thực, credential và quyền đã thay đổi ra sao? | Cần đối chiếu loại tài khoản và nguồn đăng nhập |
| VCN Flow Logs | Lưu lượng nào được ghi nhận trên VNIC? | Có cấu hình capture filter và sampling |
| Object Storage service logs | Hoạt động đọc/ghi object nào được ghi? | Phải kiểm tra category và tình trạng bật log |
| Log hệ điều hành, EDR, ứng dụng | Tiến trình và workload có dấu hiệu gì? | Host bị xâm nhập có thể làm giảm độ tin cậy |
| Backup boot/block volume | Trạng thái dữ liệu đĩa tại một thời điểm | Không thu bộ nhớ đang chạy |
| Database audit và Data Safe | Hoạt động trong database nào được ghi? | Phụ thuộc audit policy và nguồn đã thu |
| Cấu hình hạ tầng, IaC, pipeline | Cấu hình nào được triển khai và bởi ai? | Trạng thái hiện tại có thể đã khác lúc sự kiện |

### 6.2. OCI Audit và log truy cập dữ liệu

OCI Audit tự động ghi các lệnh gọi đến API công khai được hỗ trợ, bao gồm thao tác qua Console, CLI và SDK. Theo tài liệu Oracle, với Object Storage, Audit ghi sự kiện liên quan đến bucket nhưng không ghi sự kiện liên quan đến từng object. [Oracle: Overview of Audit](https://docs.oracle.com/en-us/iaas/Content/Audit/Concepts/auditoverview.htm).

Vì vậy, thấy một sự kiện đổi cấu hình bucket không chứng minh object đã được tải xuống. Cần đối chiếu nguồn log truy cập object.

Object Storage service logs có hai category đọc và ghi. Ví dụ, read log có thể chứa GET/LIST/HEAD; write log có PUT/POST/DELETE. Oracle mô tả cơ chế chuyển các log này là best effort, nên không thể dùng việc thiếu một bản ghi làm kết luận tuyệt đối rằng truy cập chưa xảy ra. [Oracle: Details for Object Storage](https://docs.oracle.com/en-us/iaas/Content/Logging/Reference/details_for_object_storage.htm).

Trong bài điều tra, ghi thời điểm log được bật, category, retention, sự gián đoạn và khoảng dữ liệu thực tế còn giữ. Bật log sau khi xảy ra sự cố không tạo lại những bản ghi chưa từng được thu.

Audit hiện có thời gian lưu 365 ngày; cấu hình này áp dụng cấp tenancy và không thay đổi được. Không suy thời gian đó cho mọi loại log khác trên OCI. [Oracle: Audit Log Retention Period](https://docs.oracle.com/en-us/iaas/Content/Audit/Tasks/settingretentionperiod.htm).

### 6.3. VCN Flow Logs

Flow logs ghi thông tin lưu lượng được chấp nhận hoặc từ chối theo các rule liên quan. Capture filter và tỷ lệ sampling ảnh hưởng những flow được đưa vào log. Khi xuất dữ liệu, thu cả cấu hình filter đang áp dụng. [Oracle: Flow Logs](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/vcn-flow-logs.htm).

Dùng nguồn này để đối chiếu endpoint, hướng lưu lượng và thời điểm, rồi kết hợp với log ứng dụng. Không coi flow log là bản ghi đầy đủ nội dung gói tin hoặc toàn bộ dữ liệu đã truyền.

### 6.4. Bằng chứng cơ sở dữ liệu

Hoạt động gọi API quản lý database và hoạt động SQL bên trong database là hai lớp khác nhau. Điều tra database cần có DBA phối hợp xác định audit policy, audit trail và tình trạng thu thập.

Oracle Data Safe có thể thu audit records từ audit trail của database đã đăng ký, chẳng hạn `UNIFIED_AUDIT_TRAIL`, khi việc thu được bật. Cần ghi target database, trail, cửa sổ thời gian và các gián đoạn thu thập. [Oracle: Audit Trails](https://docs.oracle.com/en-us/iaas/data-safe/doc/audit-trails.html).

Với dịch vụ quản lý như Autonomous Database, sử dụng những nguồn chẩn đoán và audit được dịch vụ cung cấp; không áp quy trình SSH và chụp đĩa của Compute cho mọi loại database.

## 7. Cô lập sự cố mà vẫn giữ khả năng điều tra

### 7.1. Trước mỗi thay đổi

Người thực hiện nên ghi trước:

~~~text
Mục tiêu: Hạn chế đường truy cập nào?
Phạm vi: Tài nguyên và danh tính cụ thể nào?
Hiện trạng: Cấu hình và bằng chứng đã lưu ở đâu?
Tác động: Dịch vụ, phiên kết nối hoặc dữ liệu nào có thể bị ảnh hưởng?
Quyết định: Ai chấp thuận và vào thời điểm nào?
Kiểm chứng: Dùng phép kiểm tra nào để xác nhận đã cô lập?
Khôi phục: Điều kiện nào cho phép đảo thay đổi?
~~~

Nếu tổn hại đang tiếp diễn khiến không thể chụp đủ hiện trạng, ghi rõ quyết định ưu tiên cô lập và phần dữ liệu chưa thu được.

### 7.2. Khi nghi credential bị lộ

Sử dụng một danh tính ứng cứu tin cậy để kiểm tra:

- Principal nào và loại credential nào được dùng.
- Credential có đang được dùng chung bởi nhiều pipeline hoặc dịch vụ không.
- Có credential, phiên đăng nhập hoặc quyền mới được tạo sau thời điểm nghi ngờ không.
- Cần thu hồi, đổi khóa, hạn chế quyền hoặc vô hiệu hóa tài khoản nào.
- Những hệ thống phụ thuộc phải được cập nhật credential thay thế.

OCI có nhiều loại credential như Console password, API signing key, auth token và customer secret key. Xử lý một loại không đồng nghĩa đã xử lý các loại còn lại. [Oracle: Managing User Credentials](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingcredentials.htm).

Với đăng nhập liên kết, phối hợp IdP để xử lý các phiên và yếu tố xác thực liên quan. Với instance/resource principal, kiểm tra chính workload, dynamic group và policy có hiệu lực; không chỉ tìm một API key của người dùng.

Giữ lại fingerprint hoặc credential identifier cần cho đối chiếu, không đưa private key, token hoặc mật khẩu vào manifest và nội dung thông báo.

### 7.3. Khi nghi Compute bị kiểm soát

Mục tiêu thường là hạn chế kết nối độc hại trong khi duy trì đường điều tra đã được kiểm soát.

**Không coi một NSG rỗng là cơ chế phủ định các rule cho phép khác.** Với VNIC, các security list của subnet và các NSG liên quan hợp thành tập rule cho phép. Lưu lượng còn có thể thuộc kết nối stateful đang được theo dõi. [Oracle: Security Rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

Trình tự đề xuất:

1. Ghi instance OCID, tất cả VNIC, địa chỉ, subnet, NSG và volume attachment.
2. Thu cấu hình rule và routing trước thay đổi.
3. Xác định các đường vào/ra thực tế, kể cả VNIC phụ và kết nối nội bộ.
4. Áp dụng phương án cô lập đã chuẩn bị, xem xét mọi rule đang có hiệu lực.
5. Kiểm tra từ nguồn độc lập rằng luồng cần chặn thực sự không còn hoạt động.
6. Ghi ảnh hưởng đến dịch vụ và kênh điều tra còn được phép.

Không xóa security list dùng chung chỉ để cô lập một máy. Việc đó có thể ảnh hưởng các VNIC khác trong subnet.

Việc dừng hoặc reboot máy làm mất trạng thái bộ nhớ đang chạy. Quyết định này cần đặt cạnh nguy cơ tiếp tục mất dữ liệu; không có một thứ tự cố định phù hợp cho mọi sự cố.

### 7.4. Với Object Storage và database

Với bucket nghi bị truy cập trái phép, lưu cấu hình và các định danh liên quan, rồi xem xét public access, IAM, pre-authenticated requests và credential đang được dùng. Tài nguyên vẫn private chưa đủ chứng minh mọi đường truy cập đã được kiểm soát.

Với database, phối hợp DBA để hạn chế tài khoản hoặc đường kết nối liên quan, giữ audit trail và xác định cách phục hồi. Tránh thay đổi hàng loạt audit policy hoặc purge trail ngay giữa điều tra.

Trong cả hai trường hợp, ghi rõ hành động nào xử lý phơi bày hiện tại và hành động nào xử lý nguồn cấu hình có thể tái tạo phơi bày đó.

## 8. Thu thập dữ liệu dễ mất và trạng thái đĩa

### 8.1. Ưu tiên theo độ dễ mất

Một thứ tự cân nhắc có thể là:

| Dữ liệu | Vì sao cần quyết định sớm? | Cách ghi nhận |
| --- | --- | --- |
| RAM, tiến trình, kết nối đang mở | Thay đổi nhanh, mất khi dừng máy | Công cụ, thời điểm và tác động thu thập |
| File tạm và log đang xoay vòng | Có thể bị ghi đè hoặc xóa | Đường dẫn, phạm vi và thời điểm thu |
| Cấu hình mạng/IAM | Có thể bị thay đổi trong cô lập | Bản trước/sau và người thao tác |
| Boot/block volumes | Workload tiếp tục ghi đĩa | Backup/copy OCID và mốc thời gian |
| Log ở dịch vụ tập trung | Có retention và độ trễ riêng | Truy vấn, nguồn và khoảng dữ liệu |

Với thu thập trực tiếp trên máy nghi bị xâm nhập, dùng công cụ đã kiểm chứng và ghi lại mọi thay đổi do công cụ gây ra. Dữ liệu trả về từ hệ điều hành đó cần được đối chiếu nguồn độc lập.

Không cài hàng loạt công cụ mới hoặc chạy nhiều trình quét trước khi quyết định chiến lược thu thập. Những hoạt động này làm thay đổi file, log, bộ nhớ và có thể che dấu diễn biến ban đầu.

### 8.2. Backup boot volume và các data volume

OCI cho phép tạo boot volume backup khi volume đang gắn với instance chạy; bản sao là crash-consistent, tức phản ánh trạng thái đĩa theo cách tương tự sau một lần dừng đột ngột. Nó không phải bản chụp RAM. [Oracle: Boot Volume Backups](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/bootvolumebackups.htm).

Một quy trình bảo quản trạng thái đĩa:

1. Liệt kê boot volume và từng block volume liên quan.
2. Ghi source volume OCID, dung lượng, attachment và khóa mã hóa.
3. Chọn backup hoặc phương thức sao chép phù hợp, ghi rõ lý do.
4. Ghi thời điểm yêu cầu, định danh bản sao và trạng thái hoàn thành.
5. Kiểm tra đủ các volume; một boot backup không tự bao gồm mọi data volume.
6. Hạn chế quyền xóa, chỉnh retention và sử dụng các bản cần giữ.
7. Phục hồi ra bản phân tích riêng trong môi trường điều tra cô lập.

Volume group backup hỗ trợ tính nhất quán qua nhiều volume. Application-consistent backup cần phối hợp ứng dụng như quiesce hoặc flush, nên phải ghi rõ thao tác và tác động. [Oracle: Block Volume Backups](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/blockvolumebackups.htm).

Nếu không thể có tính nhất quán ứng dụng mà không làm thay đổi đáng kể hiện trạng, nêu giới hạn của bản thu thay vì gọi nó là bản sao ứng dụng hoàn hảo.

### 8.3. Bản bảo quản và bản làm việc

Giữ backup hoặc bản thu ban đầu dưới quyền truy cập được kiểm soát. Tạo bản riêng để phân tích.

Không boot trực tiếp từ bản cần bảo quản. Khi phân tích filesystem, dùng cơ chế attachment và mount chỉ đọc phù hợp với nền tảng; xem xét cả khả năng tự động ghi metadata hoặc replay journal của filesystem.

Backup do dịch vụ Block Volume quản lý và object trong bucket bằng chứng của nhóm là hai loại tài nguyên khác nhau. Không suy rằng retention rule của bucket chứa log sẽ bảo vệ cả volume backup.

Với backup retention, deletion prevention hoặc indefinite hold của Block Volume, cần kiểm tra cấu hình và quyền dành riêng cho các tính năng đó. [Oracle: Block Volume Backups — retention permissions](https://docs.oracle.com/en-us/iaas/Content/Block/Concepts/blockvolumebackups.htm).

Một volume backup OCID cũng không thay thế hash của một file ảnh đĩa đã xuất. Nếu không có ảnh đĩa dạng file, ghi đúng loại artifact cùng định danh và hồ sơ dịch vụ, không bịa một SHA-256 cho nội dung chưa thu được.

## 9. Thiết kế nơi lưu bằng chứng

### 9.1. Tách người thu, người phân tích và người quản lý lưu giữ

Một compartment riêng giúp tổ chức tài nguyên và phân quyền, nhưng không tự tạo sự độc lập trước tài khoản có quyền quản trị toàn tenancy.

Có thể chia quyền thành:

| Vai trò | Quyền theo nhiệm vụ |
| --- | --- |
| Người thu thập | Đọc nguồn và tạo artifact tại nơi tiếp nhận |
| Điều tra viên | Đọc bằng chứng được giao, tạo kết quả phân tích riêng |
| Người quản lý lưu giữ | Quản lý thời gian lưu và bàn giao |
| Người kiểm toán | Đọc manifest, lịch sử truy cập và quyết định |
| Người quản trị khóa | Bảo đảm khả năng giải mã theo quy trình riêng |

Kho bằng chứng nên private, có theo dõi truy cập và đường chuyển dữ liệu được kiểm soát. Không dùng liên kết truy cập công khai để bàn giao.

Nếu mô hình đe dọa bao gồm quản trị viên tenancy bị kiểm soát, cần đánh giá nơi lưu độc lập hơn, chẳng hạn hệ thống thu nhận khác được tổ chức quản lý. Việc chọn tenancy hoặc region khác phải đi kèm kiểm tra quyền, đường truyền và quy định nơi lưu dữ liệu.

### 9.2. Retention không giống versioning

Object Storage retention rule bảo vệ object trong thời gian áp dụng. Thời gian của rule có hạn được tính từ Last Modified của từng object. Khóa rule là thao tác không đảo ngược, có thời gian chờ bắt buộc 14 ngày; sau khi khóa chỉ được tăng thời gian lưu. [Oracle: Object Storage Data Retention Rules](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingretentionrules.htm).

Rule có hiệu lực bảo vệ dữ liệu khác với trạng thái khóa cấu hình của chính rule. Vì vậy, ghi cả thời điểm bắt đầu áp dụng và thời điểm khóa thực sự có hiệu lực.

Không thiết kế bucket vừa bật versioning vừa có active retention rules: OCI có ràng buộc giữa hai tính năng này. [Oracle: Object Storage Data Retention Rules — interactions](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingretentionrules.htm).

Versioning giữ các phiên bản nhưng phiên bản vẫn có thể bị xóa vĩnh viễn bởi thao tác và quyền tương ứng. Nó không tự thay thế retention bảo vệ khỏi xóa. [Oracle: Object Storage Versioning](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning.htm).

Với nhu cầu giữ vô thời hạn, OCI có indefinite retention rule; rule này không khóa được. Quyết định thời gian giữ và quyền gỡ rule phải được tổ chức chốt trước khi sử dụng. [Oracle: Creating an Object Storage Data Retention Rule](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingretentionrules_topic-To_create_a_retention_rule.htm).

Trong lab, dùng chính sách lưu đã được chuẩn bị, không thử khóa retention dài hạn trên dữ liệu hoặc tài nguyên cần dọn sau buổi học.

### 9.3. Giữ khả năng giải mã

Ghi Vault/key OCID và các phụ thuộc mã hóa của artifact. Đừng xử lý credential bị lộ bằng cách xóa khóa mã hóa đang bảo vệ bằng chứng.

Oracle nêu rằng dữ liệu được mã hóa bằng key ở trạng thái Pending Deletion trở nên không truy cập được. Quy trình ứng cứu cần bảo vệ cả dữ liệu lẫn khả năng dùng khóa giải mã hợp lệ. [Oracle: Deleting a Key](https://docs.oracle.com/en-us/iaas/Content/KeyManagement/Tasks/managingkeys_topic-To_delete_a_key.htm).

## 10. Manifest và chuỗi bàn giao bằng chứng

### 10.1. Manifest mô tả artifact

Manifest là hồ sơ mô tả một lần thu, không phải nội dung chứng minh mọi giả thuyết. Mẫu đề xuất:

| Trường | Nội dung cần ghi |
| --- | --- |
| Incident ID, evidence ID | Mã hồ sơ và artifact |
| Source | Dịch vụ, tenancy, compartment, region và resource OCID |
| Scope | Khoảng thời gian, filter và phạm vi truy vấn |
| Acquisition | Câu lệnh, phiên bản công cụ, principal thu thập |
| Times | Thời điểm bắt đầu/kết thúc thu theo UTC |
| Artifact | Tên file hoặc backup OCID, kích thước nếu có |
| Integrity | Thuật toán và hash của file đã thu |
| Storage | Bucket, object name, version ID nếu áp dụng |
| Limitations | Dữ liệu thiếu, độ trễ, sampling hoặc thay đổi do thu thập |
| Custody | Người tiếp nhận, mục đích và lần bàn giao |

Với artifact dạng file, tính hash ngay sau khi ghi xong và kiểm tra lại khi sao chép. NIST mô tả việc kiểm chứng tính toàn vẹn và giữ hồ sơ bàn giao như những phần của quy trình điều tra số. [NIST SP 800-86](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-86.pdf).

### 10.2. Hash chứng minh điều gì?

Trong lab, dùng SHA-256 để đối chiếu byte của cùng một file giữa hai lần kiểm tra.

Hash khớp hỗ trợ xác nhận file không đổi so với giá trị hash tin cậy đã ghi. Nó không tự chứng minh:

- Nguồn ban đầu không bị giả mạo.
- Khoảng thu đã bao phủ mọi sự kiện.
- Người thu không thay dữ liệu trước khi tính hash.
- Sự cố hoặc trách nhiệm của một cá nhân đã được xác định.

Không dùng Object Storage ETag như một giá trị SHA-256 mặc định. Lưu riêng hash của artifact, định danh object và metadata dịch vụ.

Nếu artifact và manifest cùng có thể bị thay bởi một người, hai file vẫn có thể bị thay đồng thời. Bảo quản manifest trong hệ thống có kiểm soát thay đổi; có thể ký số manifest theo quy trình của tổ chức.

### 10.3. Ghi từng lần bàn giao

Mỗi lần chuyển artifact hoặc cấp quyền tiếp cận nên có:

~~~text
Evidence ID: E-001
Bên giao / bên nhận: định danh đã được xác thực
Thời gian UTC: thời điểm bàn giao
Mục đích: kiểm tra timeline
Vị trí nguồn / đích: định danh nơi lưu
Hash trước / sau: SHA-256 của file
Kết quả đối chiếu: khớp hoặc mô tả sai khác
Người xác nhận: định danh và bằng chứng chấp thuận
~~~

Để chia sẻ báo cáo đã che dữ liệu nhạy cảm, tạo một bản dẫn xuất, cấp evidence ID hoặc artifact ID riêng, ghi cách xử lý và hash mới. Không sửa trực tiếp file gốc đã bảo quản.

## 11. Thực hành xuất OCI Audit bằng PowerShell

Phần này là hướng dẫn thực hành cho người học, không phải báo cáo đã thực thi trên tenancy. Dùng compartment lab và khoảng thời gian có hoạt động thử nghiệm hợp lệ.

### 11.1. Chuẩn bị quyền và phạm vi

Một policy đọc Audit có thể là:

~~~text
Allow group IncidentAuditReaders to read audit-events in compartment SecurityLab
~~~

Thay tên nhóm và compartment bằng giá trị thật. Quyền đọc Audit không tự cấp quyền xem mọi nguồn log hay tạo backup. [Oracle: Viewing Audit Log Events](https://docs.oracle.com/en-us/iaas/Content/Audit/Tasks/viewinglogevents.htm).

Chuẩn bị profile OCI CLI dành cho thu thập, ví dụ `IR_READONLY`, và một thư mục trên máy thu tin cậy. Các chuỗi `<...>` bên dưới là giá trị cần thay.

### 11.2. Xuất một cửa sổ thời gian

~~~powershell
$ErrorActionPreference = 'Stop'

$incidentId = 'IR-LAB-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$caseDir = Join-Path 'C:/IR-Lab' $incidentId
if (Test-Path -LiteralPath $caseDir) {
    throw 'Thu muc da ton tai; chon ho so thu thap moi.'
}
New-Item -ItemType Directory -Path $caseDir -Force | Out-Null

$readProfile = 'IR_READONLY'
$sourceRegion = '<SOURCE_REGION>'
$compartmentOcid = '<SOURCE_COMPARTMENT_OCID>'
$collectorPrincipalOcid = '<TRUSTED_COLLECTOR_PRINCIPAL_OCID>'

# Khoang thoi gian minh hoa; thay bang cua so can thu.
$startUtc = '2026-11-21T02:00:00Z'
$endUtc = '2026-11-21T03:00:00Z'

$cliVersionLines = & oci --version
if ($LASTEXITCODE -ne 0) {
    throw 'Khong doc duoc phien ban OCI CLI.'
}
$cliVersion = $cliVersionLines -join ' '

$auditFile = Join-Path $caseDir 'E-001-audit-export.json'
$collectionStartedUtc = [DateTimeOffset]::UtcNow.ToString('o')

$auditArgs = @(
    'audit', 'event', 'list',
    '--profile', $readProfile,
    '--compartment-id', $compartmentOcid,
    '--region', $sourceRegion,
    '--start-time', $startUtc,
    '--end-time', $endUtc,
    '--all',
    '--output', 'json'
)

$auditLines = & oci @auditArgs
$auditExitCode = $LASTEXITCODE
$collectionCompletedUtc = [DateTimeOffset]::UtcNow.ToString('o')

if ($auditExitCode -ne 0) {
    throw 'Xuat Audit that bai; khong danh dau thu thap thanh cong.'
}

$auditText = ($auditLines -join [Environment]::NewLine) + [Environment]::NewLine
$null = ConvertFrom-Json -InputObject $auditText -ErrorAction Stop

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($auditFile, $auditText, $utf8NoBom)

$artifactSha256 = (Get-FileHash -LiteralPath $auditFile -Algorithm SHA256).Hash
Write-Output ('Evidence file: ' + $auditFile)
Write-Output ('SHA256: ' + $artifactSha256)
~~~

`--all` lấy mọi trang kết quả cho truy vấn đó; nó không tự truy vấn mọi compartment hoặc region. CLI yêu cầu thời gian có độ chính xác đến phút, với giây và phần giây bằng 0. [Oracle CLI: audit event list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/audit/event/list.html).

File thu được là **bản xuất JSON do CLI biểu diễn**, không phải bản ghi byte của HTTP response gốc. Không dùng `--query` để bỏ bớt trường trước khi lưu bản xuất cần bảo quản.

Audit có độ trễ xử lý. Cần phân biệt cửa sổ truy vấn theo cơ chế của dịch vụ với timestamp sự kiện; thu thêm các cửa sổ lân cận và thực hiện lần thu bổ sung nếu cần. Ghi mỗi lần xuất thành artifact riêng. [Oracle: Viewing Audit Log Events](https://docs.oracle.com/en-us/iaas/Content/Audit/Tasks/viewinglogevents.htm).

### 11.3. Tạo manifest cho file vừa xuất

Tiếp tục trong cùng phiên PowerShell:

~~~powershell
$manifest = [ordered]@{
    IncidentId = $incidentId
    EvidenceId = 'E-001'
    ArtifactType = 'OCI_AUDIT_CLI_EXPORT'
    SourceRegion = $sourceRegion
    SourceCompartmentOcid = $compartmentOcid
    QueryStartUtc = $startUtc
    QueryEndUtc = $endUtc
    CollectionStartedUtc = $collectionStartedUtc
    CollectionCompletedUtc = $collectionCompletedUtc
    CollectorPrincipalOcid = $collectorPrincipalOcid
    CliProfile = $readProfile
    CliVersion = $cliVersion
    CommandArguments = $auditArgs
    FileName = [System.IO.Path]::GetFileName($auditFile)
    LengthBytes = (Get-Item -LiteralPath $auditFile).Length
    HashAlgorithm = 'SHA256'
    Sha256 = $artifactSha256
    Limitations = @(
        'Single compartment and region'
        'Service processing delay must be considered'
        'CLI serialized JSON, not raw HTTP bytes'
    )
}

$manifestFile = Join-Path $caseDir 'E-001-manifest.json'
$manifestText = $manifest | ConvertTo-Json -Depth 8
[System.IO.File]::WriteAllText($manifestFile, $manifestText, $utf8NoBom)

$manifestSha256 = (Get-FileHash -LiteralPath $manifestFile -Algorithm SHA256).Hash
Write-Output ('Manifest SHA256: ' + $manifestSha256)
~~~

Mẫu này không chứa private key hoặc token. Ghi giá trị hash manifest và quyết định tiếp nhận vào nhật ký quản lý bằng chứng đã được bảo vệ.

Nếu truy vấn trả về danh sách sự kiện rỗng, vẫn lưu artifact cùng phạm vi và trạng thái thành công. Sau đó kiểm tra đúng compartment, region, thời gian, quyền và độ trễ trước khi diễn giải kết quả.

## 12. Chuyển bằng chứng lên Object Storage và kiểm tra lại

Dùng bucket evidence private đã được người quản lý chuẩn bị. Profile ghi bằng chứng có thể khác profile đọc nguồn.

### 12.1. Upload với tên riêng cho từng hồ sơ

~~~powershell
$writeProfile = 'IR_EVIDENCE_WRITER'
$storageRegion = '<EVIDENCE_BUCKET_REGION>'
$namespaceName = '<OBJECT_STORAGE_NAMESPACE>'
$bucketName = '<PRIVATE_EVIDENCE_BUCKET>'

foreach ($sourceFile in @($auditFile, $manifestFile)) {
    $objectName = $incidentId + '/' + [System.IO.Path]::GetFileName($sourceFile)

    & oci os object put --profile $writeProfile --region $storageRegion --namespace-name $namespaceName --bucket-name $bucketName --name $objectName --file $sourceFile --no-overwrite

    if ($LASTEXITCODE -ne 0) {
        throw ('Upload that bai: ' + $sourceFile)
    }
}
~~~

`--no-overwrite` yêu cầu không ghi đè object đã có. Ghi kết quả upload, object name và metadata phản hồi vào nhật ký tiếp nhận; vẫn phải kiểm tra lại nội dung sau chuyển. [Oracle CLI: os object put](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/put.html).

Tên object duy nhất, quyền ghi hạn chế và retention phục vụ các lớp kiểm soát khác nhau. Không dùng một cờ CLI làm thay thế toàn bộ thiết kế lưu giữ.

### 12.2. Download ra bản kiểm tra riêng

Profile đọc bằng chứng cần có quyền đọc bucket/object theo thiết kế:

~~~powershell
$verifyProfile = 'IR_EVIDENCE_READER'
$verifyDir = Join-Path $caseDir 'verification'
New-Item -ItemType Directory -Path $verifyDir -ErrorAction Stop | Out-Null

foreach ($sourceFile in @($auditFile, $manifestFile)) {
    $fileName = [System.IO.Path]::GetFileName($sourceFile)
    $objectName = $incidentId + '/' + $fileName
    $downloadFile = Join-Path $verifyDir $fileName
    $expectedHash = (Get-FileHash -LiteralPath $sourceFile -Algorithm SHA256).Hash

    & oci os object get --profile $verifyProfile --region $storageRegion --namespace-name $namespaceName --bucket-name $bucketName --name $objectName --file $downloadFile

    if ($LASTEXITCODE -ne 0) {
        throw ('Download kiem tra that bai: ' + $objectName)
    }

    $actualHash = (Get-FileHash -LiteralPath $downloadFile -Algorithm SHA256).Hash
    if ($actualHash -ne $expectedHash) {
        throw ('Hash khong khop: ' + $objectName)
    }

    Write-Output ('HASH_MATCH: ' + $objectName)
}
~~~

Lệnh `object get` tải nội dung object về file. Nếu đang thu một object nguồn có versioning, ghi version ID và sử dụng đúng phiên bản khi tải để tránh nhầm bản mới nhất. [Oracle CLI: os object get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/get.html).

Ghi hash kiểm tra cùng định danh nguồn tham chiếu tin cậy. Nếu không khớp, giữ cả hai bản và điều tra sai khác; không sửa manifest để làm chúng khớp nhau.

## 13. Dựng timeline và đánh giá giả thuyết

### 13.1. Ghép dữ liệu bằng định danh

Audit có các nhóm thông tin về thời gian, identity, request, response và state change. Những trường như `data.identity.principalId`, `data.request.id`, `data.resourceId` và `data.eventGroupingId` hỗ trợ đối chiếu hoạt động. [Oracle: Contents of an Audit Log Event](https://docs.oracle.com/en-us/iaas/Content/Audit/Reference/logeventreference.htm).

Tên trường trong bản xuất có thể phụ thuộc cách công cụ biểu diễn schema. Giữ file đã thu nguyên vẹn, tạo bản làm việc để chuẩn hóa.

Một bảng timeline đề xuất:

| Mốc UTC | Nguồn/evidence ID | Dữ kiện | Mức tin cậy | Điểm cần xác minh |
| --- | --- | --- | --- | --- |
| T0 | Log xác thực | Một phiên được thiết lập | Theo chất lượng nguồn | Có phải hoạt động được duyệt? |
| T1 | Audit/E-001 | API thay cấu hình được ghi | Đối chiếu request và response | Cấu hình trước/sau có đủ không? |
| T2 | Log ứng dụng | Xuất hiện hoạt động bất thường | Cần đối chiếu độc lập | Máy có bị kiểm soát không? |
| T3 | Nhật ký ứng cứu | Nhóm thực hiện cô lập | Có người thao tác xác nhận | Có còn đường truy cập khác không? |
| T4 | Kiểm tra độc lập | Luồng cần chặn không còn hoạt động | Theo phạm vi phép thử | Các VNIC và region khác đã xét chưa? |

Đây là mẫu ghi nhận, không phải diễn biến của một sự cố thật.

Phân biệt thời điểm API bắt đầu, xử lý hoàn thành và lúc log được thu. Một request có thể tạo nhiều sự kiện; không đếm mỗi dòng là một hành động độc lập khi chưa kiểm tra định danh liên quan.

### 13.2. Phân tích với bằng chứng thiếu

Khi không đủ dữ liệu, mô tả giới hạn cụ thể:

~~~text
Đã thu:
    Audit tại hai compartment, trong các cửa sổ đã ghi.

Chưa có:
    Object read logs trước thời điểm bật logging.

Có thể kết luận:
    Đã có thay đổi cấu hình bucket trong phạm vi dữ liệu đã thu.

Chưa thể kết luận:
    Có hoặc không có object bị tải xuống trong khoảng thiếu log.
~~~

Tương tự, lưu lượng tới một IP đáng chú ý chưa đủ chứng minh dữ liệu nhạy cảm đã bị gửi đi. Cần đối chiếu ứng dụng, dung lượng, quyền truy cập và nguồn dữ liệu khác.

Mỗi kết luận nên dẫn đến evidence ID, mô tả suy luận và ghi mức chắc chắn. Những giả thuyết bị bác bỏ cũng nên được giữ trong ghi chú để tránh lặp lại điều tra.

## 14. Loại bỏ nguyên nhân và phục hồi dịch vụ

### 14.1. Xử lý nguyên nhân ở nguồn

Sau khi xác định phạm vi, lập thay đổi cụ thể:

- Thu hồi hoặc thay credential bị ảnh hưởng và cập nhật hệ thống phụ thuộc.
- Gỡ quyền, tài khoản hoặc cấu hình trái phép.
- Vá điểm vào và xử lý cấu hình trong IaC, pipeline hoặc image nguồn.
- Dựng lại workload từ nguồn tin cậy khi không thể chứng minh host còn toàn vẹn.
- Đối chiếu database, object và dữ liệu ứng dụng để xác định phần cần phục hồi.

Giữ riêng tài nguyên đang điều tra và môi trường phục hồi. Không gắn lại đĩa nghi bị sửa vào production chỉ vì ứng dụng có thể khởi động.

Bản backup gần nhất chưa chắc là bản sạch: cần xác định thời điểm nghi xâm nhập và kiểm tra artifact phục hồi. Trong hồ sơ, ghi lý do chọn recovery point và lượng dữ liệu có thể phải khôi phục bổ sung.

### 14.2. Tiêu chí đưa trở lại phục vụ

Một bộ điều kiện đề xuất:

| Nhóm kiểm chứng | Tiêu chí |
| --- | --- |
| Danh tính | Credential, quyền và phiên liên quan đã được xử lý |
| Cấu hình | Đã so với baseline tin cậy; nguồn triển khai được sửa |
| Dữ liệu | Đã kiểm tra tính toàn vẹn theo nghiệp vụ |
| Ứng dụng | Luồng đọc/ghi và phụ thuộc thiết yếu hoạt động |
| Quan sát | Log và tuyến cảnh báo đã được kiểm tra |
| Tính sẵn sàng | Đáp ứng mức phục vụ và kế hoạch chuyển lưu lượng |
| Điều tra | Bằng chứng cần giữ không bị ghi đè bởi phục hồi |
| Quyết định | Chủ dịch vụ và người phụ trách ứng cứu xác nhận |

Đo RTO bằng thời gian thực tế đưa dịch vụ về mức phục vụ cần thiết; xác định RPO theo dữ liệu phục hồi được. Không dùng trạng thái máy `RUNNING` làm đại diện cho toàn bộ sự sẵn sàng của ứng dụng.

Sau chuyển lưu lượng, tiếp tục theo dõi những dấu hiệu đã dùng để nhận diện sự cố và những đường truy cập đã bị xử lý. Ghi thời hạn theo dõi cùng người phụ trách.

## 15. Tự động hóa, chi phí và kết thúc lab

### 15.1. Tự động hóa theo tác động

Có thể tự động hóa các bước đã kiểm chứng như mở hồ sơ, gắn định danh, đọc cấu hình, xuất log và đối chiếu hash.

Với hành động làm thay đổi tài nguyên, cần đặt giới hạn rõ về principal, compartment, loại tài nguyên và tác động. Nếu automation hoặc responder có thể dừng/xóa tài nguyên, ghi nhận việc thực thi như một phần timeline và đánh giá ảnh hưởng tới bằng chứng.

Một automation nên có:

- Đầu vào và điều kiện thực hiện rõ ràng.
- Cách tránh chạy trùng cho cùng artifact hoặc tài nguyên.
- Nhật ký lỗi, trạng thái từng bước và cơ chế tiếp tục có kiểm soát.
- Điểm chuyển cho người chịu trách nhiệm khi thiếu quyền hoặc phạm vi không rõ.

Không đánh dấu thu thập thành công chỉ vì đã tạo được một file; phải kiểm tra lệnh nguồn, nội dung, manifest và kết quả bảo quản.

### 15.2. Quản lý chi phí mà vẫn giữ dữ liệu cần thiết

Theo dõi riêng dung lượng log, volume backup, volume phân tích, bucket evidence, máy điều tra và môi trường phục hồi.

Khi chọn storage tier, cân nhắc thời gian cần truy xuất. Object ở Archive phải được restore trước khi đọc; vì thế không chuyển ngay dữ liệu đang được điều tra sang tầng này chỉ vì chi phí lưu thấp hơn. [Oracle: Object Storage Storage Tiers](https://docs.oracle.com/en-us/iaas/Content/Object/Concepts/understandingstoragetiers.htm).

Việc giảm chi phí bằng xóa artifact phải tuân theo quyết định lưu giữ đã được phê duyệt. Theo dõi quota và dung lượng còn lại để một lần thu quan trọng không thất bại giữa chừng.

### 15.3. Mốc hoàn thành thực hành

Trong compartment lab, người học nên có:

1. Một hoạt động quản trị hợp lệ có thời điểm và người thực hiện đã ghi.
2. Bản xuất Audit đúng compartment, region và cửa sổ truy vấn.
3. Manifest với nguồn, công cụ, thời gian UTC và SHA-256.
4. Hai object tương ứng với bản xuất và manifest trong bucket private.
5. Bản tải kiểm tra có hash khớp nguồn tham chiếu.
6. Bảng bàn giao và ghi chú về độ trễ, dữ liệu thiếu.
7. Quyết định giữ hoặc dọn tài nguyên lab.

Để kiểm tra hiểu biết về tính toàn vẹn, tạo một bản sao dùng riêng cho thử nghiệm, sửa nội dung của bản sao đó và đối chiếu lại hash. Ghi nó là artifact thử nghiệm, không thay bản đã bảo quản.

Dọn các volume và máy phân tích không còn cần, thu hồi quyền tạm và xác minh các nguồn giám sát vẫn hoạt động. Không xóa artifact đang thuộc quyết định giữ bằng chứng.

## 16. Hồ sơ đóng sự cố và cải tiến

Hồ sơ đóng nên nêu vấn đề, phạm vi đã xác minh, tác động, timeline, nguyên nhân, hành động khắc phục và các câu hỏi chưa có đủ dữ liệu trả lời.

Lưu danh mục evidence ID cùng nơi bảo quản, người quản lý, thời gian giữ và điều kiện cho phép xử lý sau này. Đóng sự cố không mặc nhiên kết thúc yêu cầu giữ bằng chứng.

Các chỉ số nội bộ có thể gồm:

| Chỉ số | Cách dùng |
| --- | --- |
| Thời gian phát hiện đến tiếp nhận | Đánh giá việc trực và tuyến cảnh báo |
| Thời gian đến cô lập hiệu quả | Đánh giá runbook và quyền ứng cứu |
| Thời gian có artifact đầu tiên được kiểm chứng | Đánh giá khả năng thu thập |
| Tỷ lệ nguồn log có dữ liệu đúng phạm vi | Nhận diện khoảng trống quan sát |
| Số lần bàn giao thiếu thông tin hoặc lệch hash | Cải thiện quản lý bằng chứng |
| Thời gian phục hồi và dữ liệu phục hồi | Đối chiếu mục tiêu RTO/RPO |
| Tỷ lệ việc cải tiến được hoàn thành | Theo dõi hành động sau sự cố |

Mỗi vấn đề cải tiến cần có người phụ trách, thời hạn và cách xác minh. Ví dụ: bật read logs cho bucket quan trọng, sửa quyền ứng cứu thiếu, diễn tập cô lập VNIC phụ hoặc thử phục hồi volume trong môi trường điều tra.

Một hồ sơ tốt cho phép người không tham gia sự cố đọc lại và hiểu vì sao nhóm đã hành động, bằng chứng nào hỗ trợ kết luận và những giới hạn nào vẫn còn.
