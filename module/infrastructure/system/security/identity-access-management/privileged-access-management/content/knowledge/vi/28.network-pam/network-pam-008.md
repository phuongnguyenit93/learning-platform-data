# Configuration backup access

Configuration backup access là quyền tạo, đọc, tải xuống, giải mã, chia sẻ hoặc khôi phục bản sao cấu hình của thiết bị mạng. Trong Network PAM, đây không chỉ là quyền xem một tệp: backup có thể chứa thông tin giúp tiếp cận mạng, credential hoặc toàn bộ thiết lập quản trị.

Người không được đăng nhập vào firewall vẫn có thể biết topology, policy và dữ liệu xác thực nếu được đọc backup quá rộng. Người được khôi phục một backup còn có thể thay nhiều cấu hình cùng lúc, bao gồm tài khoản, đường quản trị, policy và audit.

Bài học tập trung vào kiểm kê backup, tách các quyền theo công việc, bảo vệ secret và khóa, cấp truy cập có hạn, giám sát và kiểm thử phục hồi. Ví dụ về manifest, policy và sự kiện trong bài là mô hình đề xuất, không phải định dạng native dùng trực tiếp cho một nhà cung cấp.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận diện dữ liệu nhạy cảm có thể xuất hiện trong backup cấu hình.
- Phân biệt bản phục hồi, bản đã che secret, snapshot và bản xuất một phần.
- Tách quyền export, tải, giải mã, restore và xóa.
- Thiết kế quyền truy cập theo thiết bị, phiên bản backup và mục đích.
- Quản lý credential và khóa để vừa bảo vệ vừa khôi phục được.
- Xác minh nguồn gốc, tính toàn vẹn và khả năng phục hồi.
- Xử lý việc backup bị lộ mà không nhầm thu hồi quyền với thu hồi các bản sao đã tải.
- Ngăn quá trình restore đưa credential, quyền và policy cũ trở lại.

## 2. Vì sao backup cấu hình là tài sản đặc quyền?

### 2.1. Backup có thể chứa nhiều hơn một danh sách rule

Tùy sản phẩm, phạm vi export và cách triển khai, backup có thể chứa:

- Địa chỉ và cấu trúc mạng.
- Policy, NAT, route và object.
- Thiết lập VPN.
- Tài khoản local và thông tin xác thực tương ứng.
- Shared secret dùng với hệ thống khác.
- Cấu hình SNMP hoặc giám sát.
- Tham chiếu hoặc vật liệu chứng thư.
- Thiết lập AAA.
- Đích audit.
- Thông tin HA và hệ thống quản lý.
- Script hoặc automation.
- Metadata thiết bị và phiên bản.

Không khẳng định mọi backup đều có đầy đủ private key hoặc mọi secret. Ngược lại, cũng không được coi chúng đã bị loại bỏ nếu chưa kiểm tra đúng phương thức export.

### 2.2. Quyền đọc có thể tạo khả năng tiếp cận mới

Một tệp có thể giúp người đọc:

- Biết endpoint quản trị.
- Hiểu vùng nào tin vùng nào.
- Nhận diện dịch vụ có thể tiếp cận.
- Biết tên tài khoản và cơ chế xác thực.
- Tìm credential được lưu không phù hợp.
- Chuẩn bị một môi trường khôi phục có cùng danh tính.

Vì vậy, read-only trên kho backup không đồng nghĩa rủi ro thấp. Quyền đọc toàn bộ backup của nhiều thiết bị có thể cho thấy một phần lớn hạ tầng.

### 2.3. Quyền restore là quyền thay đổi hàng loạt

Restore có thể thay:

- Admin và role.
- Password hoặc cơ chế xác thực.
- Địa chỉ quản trị.
- Policy và route.
- VPN.
- Certificate.
- Log destination.
- Thiết lập HA.
- Các điều kiện bảo vệ khác.

Người chỉ được xem một policy không nên tự có quyền đưa một cấu hình hoàn chỉnh lên thiết bị.

### 2.4. Backup có thời gian sống khác credential hiện tại

Một credential đã được đổi trên thiết bị có thể vẫn xuất hiện dưới một hình thức nào đó trong bản cũ. Việc xóa quyền đọc kho không làm các bản đã tải biến mất.

Cần quản lý cả dữ liệu lịch sử và vòng đời quyền hiện tại, thay vì chỉ kiểm tra trạng thái tài khoản đang dùng.

## 3. Phân loại đúng loại bản sao

### 3.1. Không phải tệp cấu hình nào cũng phục hồi được

| Loại | Mục đích | Điều cần biết |
| --- | --- | --- |
| Backup phục hồi | Tái lập cấu hình theo phạm vi đã xác nhận | Có thể cần secret, khóa và thành phần bổ sung |
| Bản đã che secret | Hỗ trợ, rà soát hoặc chia sẻ có giới hạn | Có thể thiếu dữ liệu cần để phục hồi |
| Bản xuất một phần | Xem một bảng hoặc một nhóm cấu hình | Không đại diện toàn bộ thiết bị |
| Bản running | Ghi lại cấu hình hiệu lực theo mô hình sản phẩm | Cần biết thời điểm và phạm vi |
| Bản candidate | Lưu phần đang soạn | Có thể chứa thay đổi chưa được áp dụng |
| Bản startup hoặc persistent | Phục vụ khởi động theo nền tảng | Có thể khác trạng thái đang chạy |
| Rescue hoặc baseline | Quay về một trạng thái đã biết | Không nhất thiết là bản mới nhất |
| Bản snapshot của nền tảng | Sao chụp tài nguyên theo công nghệ | Không mặc định thay thế backup cấu hình chuyên biệt |

Tên tệp như backup-final hoặc latest không chứng minh nguồn và tính đầy đủ.

### 3.2. Ví dụ running và candidate

PAN-OS phân biệt running configuration đã commit và đang hiệu lực với candidate configuration có thêm thay đổi chưa hoạt động. Có thể lưu backup của từng loại để dùng về sau. [Quản lý configuration backup trong PAN-OS](https://docs.paloaltonetworks.com/ngfw/administration/firewall-administration/manage-configuration-backups).

Trong inventory, cần ghi rõ bản nào được lấy. Một tệp candidate không nên được báo như bằng chứng chắc chắn của policy đang xử lý lưu lượng tại thời điểm đó.

### 3.3. Bản che secret không phải bản phục hồi tương đương

FortiOS 7.6.4 hỗ trợ password masking cho backup và thay secret bằng giá trị mask. Tài liệu cảnh báo rằng khôi phục bản đã che có thể đưa chính giá trị mask vào cấu hình, nên không coi bản đó là bản phục hồi đầy đủ. [Configuration backups and reset của FortiOS](https://docs.fortinet.com/document/fortigate/7.6.4/administration-guide/702257/configuration-backups-and-reset).

Điều này dẫn tới hai sản phẩm dữ liệu khác nhau:

~~~text
Cấu hình nguồn
     |
     +--> Backup phục hồi được bảo vệ chặt
     |
     +--> Bản chia sẻ đã xử lý dữ liệu nhạy cảm
~~~

Mỗi bản cần nhãn, quyền và tiêu chí xác minh riêng.

### 3.4. Rescue configuration cần được quản lý vòng đời

Junos có rescue configuration để giữ một cấu hình có trạng thái đã biết phục vụ phục hồi. Việc tải lại và kích hoạt nó vẫn là quá trình quản trị, không chỉ mở một tệp. [Rescue Configuration trong Junos](https://www.juniper.net/documentation/us/en/software/junos/cli/topics/topic-map/junos-rescue-configuration.html).

Một baseline từng hoạt động vẫn có thể thiếu bản vá policy, tài khoản mới hoặc thay đổi trust hiện tại. Cần kiểm tra lại khi dùng nó cho một sự cố mới.

## 4. Mã hóa, hash và che secret là các việc khác nhau

### 4.1. Mã hóa toàn bộ artifact

Mã hóa backup nhằm bảo vệ nội dung đối với người không có khả năng giải mã theo cơ chế được chọn.

Cần phân biệt:

- Mã hóa đường truyền.
- Mã hóa tại lớp lưu trữ.
- Mã hóa tệp export.
- Mã hóa từng trường bên trong cấu hình.
- Quyền sử dụng khóa.

Mã hóa đĩa của máy lưu trữ không tự ngăn người có quyền đọc object thông qua ứng dụng lấy plaintext. Mã hóa đường truyền cũng không bảo vệ tệp sau khi đã được tải xuống.

### 4.2. Hash credential không làm tệp trở thành dữ liệu công khai

Tệp có thể chứa password hash hoặc dạng secret được engine xử lý riêng. Chúng vẫn là dữ liệu nhạy cảm.

Một số dạng lưu credential có thể yếu hoặc có khả năng đảo ngược. Cisco nêu rõ type 7 không phải cơ chế bảo vệ mạnh cho secret trong configuration. Không được suy “không nhìn thấy plaintext” thành “an toàn để chia sẻ”. [Bảo vệ secret trên thiết bị Cisco](https://www.cisco.com/c/en/us/about/trust-center/resilient-infrastructure/protecting-secrets.html).

Không cần thực hiện giải mã hoặc thử password để phân loại một backup là nhạy cảm.

### 4.3. Mã hóa field không đồng nghĩa mã hóa cả tệp

Ngay cả khi một số secret được bảo vệ, tệp vẫn có thể lộ topology, địa chỉ, policy, tài khoản và endpoint nội bộ.

Ngược lại, tệp đã mã hóa hoàn toàn vẫn cần metadata và quyền đọc phù hợp: danh sách tên thiết bị, thời gian thay đổi hoặc cấu trúc kho cũng có thể mang thông tin nội bộ.

### 4.4. Redaction cần được kiểm thử

Che password cần xét nhiều nơi:

- Trường credential chính.
- Shared secret.
- URL có credential.
- Script.
- Comment.
- Vật liệu certificate.
- Giá trị tùy biến.
- Log hoặc thông báo lỗi đi kèm export.

Không chỉ tìm chuỗi password trong tên trường. Các sản phẩm và plugin có thể lưu dữ liệu khác nhau.

Nếu một bản được phép chia sẻ chỉ sau khi sanitization PASS, cần có cách xác minh và xử lý khi phát hiện trường chưa được nhận diện.

## 5. Tách các quyền trong vòng đời backup

### 5.1. Ma trận năng lực

| Năng lực | Ý nghĩa | Rủi ro chính |
| --- | --- | --- |
| Tạo backup | Yêu cầu thiết bị xuất cấu hình | Có thể lấy dữ liệu ngoài phạm vi |
| Ghi artifact | Đưa bản sao vào kho | Có thể ghi đè hoặc chèn bản giả |
| Liệt kê metadata | Xem danh mục và trạng thái | Lộ inventory và lịch sử |
| Tải ciphertext | Nhận artifact mã hóa | Có thể sao chép và phân phối |
| Giải mã hoặc xem nội dung | Tiếp cận cấu hình phục hồi | Lộ secret và topology |
| Tạo bản đã che | Xử lý nội dung cho chia sẻ | Có thể làm lộ trong pipeline trung gian |
| Chia sẻ | Cấp người khác quyền hoặc đường tải | Tăng số bản sao ngoài kiểm soát |
| Restore | Áp cấu hình lên đích | Thay đổi hàng loạt quyền và policy |
| Quản lý retention | Chọn thời gian giữ | Mất khả năng phục hồi hoặc giữ quá mức cần thiết |
| Xóa | Loại bỏ artifact | Phá bằng chứng hoặc recovery |
| Quản trị khóa | Cho phép hoặc ngăn giải mã | Ảnh hưởng toàn bộ các bản phụ thuộc |
| Quản trị connector | Thay đường lấy và dùng backup | Có thể vượt qua nhiều ranh giới khác |

Các quyền này không nhất thiết tách được bằng một nút trong sản phẩm. Cần thiết kế các lớp bổ sung phù hợp khi có yêu cầu phân tách.

### 5.2. Người vận hành backup không mặc định cần đọc plaintext

Một job có thể lấy cấu hình qua đường được kiểm soát, mã hóa và gửi tới đích mà người điều hành job không có quyền tải hoặc giải mã tùy ý.

Khả năng này phụ thuộc công nghệ và tích hợp. Nếu connector thực tế phải xử lý plaintext, cần bảo vệ chính môi trường connector và nêu rõ đó là nơi có dữ liệu nhạy cảm.

Không tuyên bố “không ai thấy secret” khi secret vẫn nằm trong log hoặc tệp tạm của worker.

### 5.3. Người có quyền tải không mặc định có quyền restore

Restore cần một quyết định riêng về:

- Artifact nào.
- Thiết bị đích.
- Mục đích.
- Khả năng tương thích.
- Tác động.
- Người thực hiện.
- Cửa sổ.
- Kiểm thử sau phục hồi.

Quyền đọc kho backup không nên tự mở quyền ghi lên mọi thiết bị mạng.

### 5.4. Quyền xóa và quản trị khóa cần được kiểm soát

Một người không sửa được artifact nhưng có thể xóa khóa giải mã vẫn có khả năng làm mất recovery.

Tương tự, người sửa được retention, lifecycle hoặc quyền truy cập có thể ảnh hưởng dữ liệu theo cách không xuất hiện dưới tên thao tác delete.

Cần đánh giá cả quyền trực tiếp và quyền quản trị các cơ chế xung quanh.

## 6. Inventory backup và phạm vi quản lý

### 6.1. Những nơi cần kiểm kê

Backup có thể nằm ở:

- Thiết bị.
- Hệ thống quản lý tập trung.
- File server.
- Object storage.
- Vault hoặc kho artifact.
- Repository.
- Máy quản trị.
- Runner của pipeline.
- Tệp đính kèm ticket.
- Công cụ hỗ trợ.
- Thiết bị lưu trữ rời.
- Bản sao phục hồi hoặc kho dự phòng.

Một thư mục backup chính được bảo vệ tốt không giải quyết các bản người dùng từng tải về máy cá nhân.

### 6.2. Metadata tối thiểu

Một artifact nên có:

- Device ID và owner.
- Hãng, model hoặc family phù hợp.
- Phiên bản.
- Miền hoặc tenant.
- Môi trường.
- Nguồn running, candidate hoặc loại khác.
- Phạm vi đầy đủ hay một phần.
- Thời điểm thu và múi giờ.
- Revision hoặc trạng thái nguồn nếu có.
- Principal hoặc job đã export.
- Phương thức bảo vệ.
- Tham chiếu khóa theo thiết kế.
- Tính toàn vẹn.
- Trạng thái kiểm thử phục hồi.
- Retention và ngoại lệ.
- Quan hệ tới change hoặc incident.

Không đưa password hoặc khóa giải mã vào metadata dùng cho nhóm rộng.

### 6.3. Manifest minh họa

~~~yaml
backupId: NET-BACKUP-20261126-019
source:
  deviceId: fw-billing-01
  administrativeDomain: billing-production
  configurationOrigin: running
  sourceRevision: revision-042
  softwareFamily: example-network-os
  softwareVersion: lab-version
capture:
  jobId: backup-job-044
  capturedAt: "2026-11-26T07:00:00Z"
  scope: device-configuration
artifact:
  classification: restricted
  protection: encrypted
  locationReference: backup-store/artifact-019
  digestReference: integrity-record-019
key:
  keyReference: recovery-key-version-003
recovery:
  status: not-yet-tested
retention:
  policyReference: network-backup-policy-01
~~~

Đây là schema tự thiết kế. Một trường status hoặc protection trong manifest không chứng minh cơ chế tương ứng đã chạy; cần kết quả kiểm tra và nguồn đáng tin cậy.

### 6.4. Đừng chỉ lưu một tên latest

Cần phân biệt các phiên bản và bảo vệ lịch sử theo yêu cầu. Nếu mọi lần chạy ghi đè cùng tệp mà không có cơ chế lịch sử phù hợp, một cấu hình lỗi hoặc việc export sai có thể thay bản tốt duy nhất.

Lịch sử cũng không nên tăng vô hạn không có owner. Retention phải cân bằng khả năng phục hồi, dữ liệu nhạy cảm và yêu cầu đã xác nhận.

## 7. Kiến trúc backup có phân tách quyền

### 7.1. Luồng tham khảo

~~~text
Thiết bị / manager
        |
        v
Connector export có phạm vi
        |
        v
Bảo vệ artifact và kiểm tra kết quả
        |
        v
Kho backup phục hồi được kiểm soát
        |
        +------------------------------+
        |                              |
        v                              v
Luồng giải mã / restore         Luồng tạo bản đã che
có grant riêng                 cho rà soát hoặc hỗ trợ
        |                              |
        v                              v
Môi trường đích được duyệt      Chia sẻ đúng phạm vi
~~~

Cần theo dõi cả các bước tạm thời. Một bản đã mã hóa ở kho cuối không bảo vệ bản plaintext còn sót ở runner.

### 7.2. Quyền connector trên thiết bị

Xác định quyền tối thiểu thực sự cho phương thức backup. Một số sản phẩm không cung cấp export dưới cùng mức quyền với việc xem một vài cấu hình.

Nếu connector cần quyền cao hơn:

- Giới hạn thiết bị.
- Giới hạn đường gọi.
- Bảo vệ credential.
- Hạn chế người sửa connector.
- Theo dõi từng lần export.
- Không chia sẻ credential với công việc khác.
- Ghi rõ giới hạn của phân tách quyền.

Không sửa một lỗi thiếu quyền bằng cách cấp toàn quyền trên mọi thiết bị mà không đánh giá.

### 7.3. Quyền ghi kho

Collector thường cần ghi bản mới vào đúng phạm vi. Không tự cấp quyền đọc và xóa mọi backup chỉ vì nó chịu trách nhiệm tạo bản sao.

Nếu công nghệ không tách được hoàn toàn, cần ghi rủi ro và biện pháp bảo vệ. Quan trọng là mô hình quyền phản ánh hệ thống thật, không chỉ sơ đồ mong muốn.

### 7.4. Luồng tạo bản đã che

Dịch vụ sanitization có thể cần quyền đọc nội dung nhạy cảm. Cần quản lý như một thành phần đặc quyền:

- Chỉ xử lý artifact được giao.
- Không ghi nội dung vào log.
- Kiểm soát tệp tạm.
- Kiểm tra đầu ra.
- Không tự chia sẻ.
- Theo dõi phiên bản quy tắc.
- Bảo vệ môi trường thực thi.
- Có owner cho trường chưa nhận diện.

Một bản che secret vẫn có thể lộ topology. Phạm vi chia sẻ cần xét toàn bộ dữ liệu còn lại.

## 8. Khóa mã hóa và khả năng phục hồi

### 8.1. Tệp còn tồn tại chưa đủ

Để phục hồi có thể cần:

- Artifact.
- Password hoặc khóa tương ứng.
- Phiên bản công cụ.
- Thiết bị hoặc môi trường tương thích.
- Chứng thư hoặc secret nằm ngoài artifact.
- Quyền truy cập kho.
- Đường quản trị phục hồi.
- Runbook.

Thiếu một thành phần có thể khiến backup không dùng được đúng lúc cần.

### 8.2. Tách khóa và artifact theo ranh giới phù hợp

Không lưu password giải mã ngay trong cùng thư mục và cấp cùng quyền cho mọi người đọc backup.

Một thiết kế có thể để kho giữ artifact, còn vault hoặc hệ thống quản lý khóa giữ khả năng giải mã. Cần kiểm soát quyền dùng khóa, không chỉ quyền nhìn thấy tên khóa.

Sự phân tách chỉ có ý nghĩa nếu cùng principal không dễ dàng tự cấp cả hai quyền bằng một đường quản trị khác.

### 8.3. Phụ thuộc khóa thiết bị và khả năng chuyển sang thiết bị mới

Mã hóa secret bên trong cấu hình có thể phụ thuộc một master key hoặc ngữ cảnh riêng. Cisco mô tả việc chuyển cấu hình có credential type 6 cần xử lý khóa phù hợp hoặc cung cấp lại secret theo cơ chế được quản lý. [Quản lý secret và tính di chuyển của cấu hình Cisco](https://www.cisco.com/c/en/us/about/trust-center/resilient-infrastructure/protecting-secrets.html).

Không suy “restore được trên thiết bị cũ” thành “khôi phục được trên thiết bị thay thế”.

Runbook phải xác nhận những phụ thuộc cụ thể của sản phẩm, không áp một quy tắc cho mọi dạng secret.

### 8.4. Luân chuyển khóa khác luân chuyển credential

Cần phân biệt:

- Khóa bảo vệ artifact.
- Khóa dùng bên trong thiết bị.
- Credential đăng nhập.
- VPN hoặc shared secret.
- Khóa ký manifest nếu có.

Đổi password admin không tự đổi khóa của backup cũ. Đổi khóa mã hóa cũng không tự làm credential bên trong bản cũ phù hợp với hệ thống hiện tại.

### 8.5. Giữ được dữ liệu lịch sử sau rotation

Nếu retention yêu cầu đọc một bản cũ, hệ thống phải giữ khả năng giải mã đúng phiên bản theo policy.

Không xóa mọi khóa cũ ngay sau khi tạo khóa mới mà chưa đánh giá artifact phụ thuộc. Ngược lại, không giữ khóa không giới hạn và không có owner.

Cần thử phục hồi sau rotation, không chỉ thử tạo backup mới.

## 9. JIT cho truy cập backup

### 9.1. Grant theo artifact và mục đích

Một yêu cầu nên xác định:

- Người hoặc workload.
- Mục đích.
- Thiết bị.
- Backup ID hoặc tập phiên bản được phép.
- Cần metadata, bản đã che, ciphertext hay plaintext.
- Có cần export ra ngoài không.
- Đích nhận.
- Thời hạn.
- Phê duyệt theo mức nhạy cảm.
- Bằng chứng và điều kiện cleanup.

Không cấp đọc toàn kho chỉ để người dùng tự tìm một bản của một thiết bị.

### 9.2. Ví dụ grant

~~~yaml
grantId: NET-BACKUP-GRANT-2841
requester: engineer-017
purpose: Kiem tra thay doi policy sau su co
backupScope:
  deviceId: fw-billing-01
  backupIds:
    - NET-BACKUP-20261126-019
capabilities:
  - view-sanitized-configuration
  - compare-approved-revisions
download:
  allowed: false
validity:
  startsAt: "2026-11-26T14:00:00+07:00"
  endsAt: "2026-11-26T14:30:00+07:00"
approvalReference: INC-2841
~~~

Đây là ý định nghiệp vụ, không phải bảo đảm kỹ thuật. Nếu client nhận toàn bộ plaintext thì hạn chế download trên giao diện không ngăn mọi hình thức sao chép.

Cần mô tả đúng cơ chế và mức bảo vệ thực tế.

### 9.3. Hết quyền truy cập không thu hồi được dữ liệu đã xem

Hết grant có thể ngăn đọc hoặc giải mã thêm theo thiết kế. Nó không tự:

- Xóa tệp đã tải.
- Thu hồi ảnh chụp.
- Làm mất dữ liệu người dùng đã sao chép.
- Hủy bản gửi cho bên thứ ba.
- Vô hiệu hóa secret đã bị lộ.

Do đó, hạn chế số lần đưa plaintext ra ngoài ranh giới kiểm soát ngay từ đầu có giá trị lớn.

### 9.4. Link tải cũng là đường truy cập

Nếu dùng link có thời hạn hoặc cơ chế tương tự:

- Chỉ tạo cho đúng artifact.
- Hạn chế thời gian theo nhu cầu.
- Không đưa vào log hoặc chat ngoài phạm vi.
- Xác định ai có thể sử dụng khi có link.
- Theo dõi tải khi nền tảng hỗ trợ.
- Hiểu khả năng thu hồi thật của cơ chế.

Hết hạn link không làm bản đã tải trở nên không đọc được.

## 10. Chia sẻ cho hỗ trợ và bên thứ ba

### 10.1. Chọn dữ liệu tối thiểu đáp ứng câu hỏi

Một vấn đề về một policy có thể chỉ cần:

- Phần cấu hình liên quan.
- Version và model.
- Thông báo lỗi đã xử lý.
- Sơ đồ đã lược thông tin.
- Bản diff phù hợp.

Không mặc định gửi backup phục hồi đầy đủ.

### 10.2. Sanitization không chỉ là password mask

Cần xem xét:

- IP và topology.
- Tên hệ thống.
- Username.
- Tên khách hàng hoặc tenant.
- Endpoint đối tác.
- Certificate hoặc dữ liệu nhận dạng.
- Comment.
- Metadata sự cố.

Masking của nhà cung cấp là một công cụ hỗ trợ, không tự thay thế đánh giá phạm vi được chia sẻ.

### 10.3. Quy trình chia sẻ

1. Xác định bên nhận và câu hỏi cần giải quyết.
2. Chọn artifact hoặc phần dữ liệu.
3. Tạo bản chia sẻ được phân loại.
4. Kiểm tra secret và thông tin ngoài nhu cầu.
5. Phê duyệt theo policy.
6. Gửi qua kênh phù hợp.
7. Ghi nhận artifact, người nhận và thời điểm.
8. Theo dõi xử lý bản sao theo thỏa thuận và khả năng kiểm chứng.

Không dùng tài khoản chia sẻ chung không truy vết để mọi người tải bản phục hồi production.

### 10.4. Tránh lộ qua công cụ trung gian

Kiểm tra:

- Tệp đính kèm ticket.
- Runner log.
- Debug output.
- Clipboard.
- Lịch sử dòng lệnh.
- Trình xem diff.
- Công cụ phân tích tự động.
- Cache và backup của máy quản trị.

Một bản đã che ở nơi cuối không giải quyết việc bản đầy đủ đã bị gửi trước đó tới một hệ thống khác.

## 11. Nguồn gốc và tính toàn vẹn

### 11.1. Hash hỗ trợ điều gì?

Hash của artifact giúp kiểm tra nội dung có khớp bản được đối chiếu hay không.

Nó không tự chứng minh:

- Được lấy từ đúng thiết bị.
- Nguồn chưa bị sửa trái phép trước lúc export.
- Bản đó đã được phê duyệt.
- Artifact có đủ thành phần.
- Secret còn hợp lệ.
- Bản đó có thể restore.

Cần gắn hash với nguồn, thời gian và chuỗi xử lý.

### 11.2. Manifest và bằng chứng nguồn

Nên nối được:

~~~text
Thiết bị và revision
        |
        v
Job export đã xác thực
        |
        v
Artifact và metadata
        |
        v
Kiểm tra toàn vẹn
        |
        v
Kết quả kiểm thử phục hồi
~~~

Nếu dùng chữ ký manifest hoặc cơ chế tương đương, cần bảo vệ quyền ký và quyền sửa hệ thống tạo manifest.

Một pipeline bị kiểm soát có thể tạo bản sai rồi ký hợp lệ. Chữ ký hỗ trợ nguồn gốc theo ranh giới tin cậy, không bảo đảm mọi nội dung là an toàn.

### 11.3. Bảo vệ khỏi ghi đè và xóa

Tùy yêu cầu, có thể dùng versioning, cơ chế lưu giữ hoặc phân tách quyền để giảm rủi ro mất bản tốt.

Cần biết:

- Ai sửa được policy lưu giữ.
- Ai xóa được phiên bản.
- Bản sao ở đâu.
- Có thể phục hồi khi kho chính lỗi không.
- Khóa còn dùng được không.
- Artifact độc hại có thể thay bản baseline không.

Không chỉ kiểm tra người dùng thường không có nút delete rồi bỏ qua admin của kho hoặc khóa.

### 11.4. Bản mới nhất không chắc là bản tốt nhất

Nếu cấu hình bị sửa trái phép rồi hệ thống tự backup, bản mới nhất có thể ghi lại trạng thái không mong muốn.

Cần có baseline đã xác nhận, lịch sử thay đổi và khả năng chọn bản theo nguồn gốc. Đừng chỉ tự động restore latest khi sự cố chưa được xác định.

## 12. Kiểm thử phục hồi

### 12.1. Các mức xác minh

| Mức | Điều đã chứng minh | Điều chưa tự được chứng minh |
| --- | --- | --- |
| Export thành công | Có đầu ra từ tác vụ | Tệp đủ và đúng nguồn |
| Artifact đọc được | Kho trả dữ liệu | Nội dung giải mã và parse đúng |
| Toàn vẹn khớp | Khớp bản được kiểm tra | Cấu hình vận hành an toàn |
| Giải mã thành công | Có khóa phù hợp | Có thể áp lên thiết bị đích |
| Parse hoặc validate PASS | Hợp lệ theo phép kiểm tra đó | Dịch vụ hoạt động đúng |
| Restore trong lab | Có thể nạp trên đích thử | Mọi ranh giới production đều đúng |
| Kiểm thử chức năng và bảo mật | Đạt các tiêu chí đã thử | Không có mọi loại lỗi chưa được kiểm tra |

Báo cáo phải dùng đúng mức đã đạt. Không đổi export-success thành recovery-verified.

### 12.2. Môi trường thử cần được cô lập phù hợp

Backup production có thể mang:

- Địa chỉ thật.
- VPN peer.
- Route.
- Admin.
- Credential.
- Đích gửi log.
- Dịch vụ tự kết nối ra ngoài.

Lab restore không nên tự tham gia mạng production trước khi đánh giá các giá trị này. Có thể cần vùng cô lập và kế hoạch thay thế danh tính, địa chỉ hoặc endpoint.

Cô lập cũng cần bảo vệ dữ liệu trong lab. Không coi thiết bị thử là nơi được phép mở rộng quyền đọc backup.

### 12.3. Tương thích và thành phần ngoài tệp

Xác minh:

- Hãng và model.
- Phiên bản.
- Mode vận hành.
- Virtual domain hoặc tenant.
- Licensing hoặc tính năng cần thiết.
- Phần cứng thay thế.
- Khóa hoặc certificate.
- Dữ liệu nằm ngoài export.
- Cách manager khôi phục quan hệ với thiết bị.

Thông tin “có tệp .conf” không đủ cho kế hoạch thay thiết bị.

### 12.4. Tiêu chí thử

Một lần diễn tập có thể kiểm tra:

- Truy cập được kho khi mất hệ thống chính.
- Lấy đúng key version.
- Định danh đích.
- Đọc và validate artifact.
- Nạp trong vùng cô lập.
- Xác minh quản trị.
- Xác minh policy và lưu lượng lab.
- Xác minh audit.
- Xử lý secret cũ.
- Đo thời gian theo mục tiêu.
- Ghi ngoại lệ.

Không cần tạo lưu lượng hoặc tác động ngoài phạm vi được phép để chứng minh recovery.

## 13. Restore không được đưa quyền cũ trở lại

### 13.1. Rủi ro của bản lịch sử

Một bản cũ có thể chứa:

- Admin đã nghỉ việc.
- Nhóm có quyền rộng.
- Password hoặc key cũ.
- Rule tạm chưa cleanup.
- AAA endpoint không còn dùng.
- Log destination cũ.
- Certificate hết hạn hoặc bị thu hồi.
- Trust không còn được chấp nhận.
- Chính sách xác thực kém hơn hiện tại.

Restore thành công về mặt kỹ thuật chưa đồng nghĩa trạng thái an toàn hiện tại đã được tái lập.

### 13.2. Quy trình kiểm soát trước khi kết nối lại

~~~text
Chọn bản theo sự cố
        |
        v
Đối chiếu nguồn gốc và tương thích
        |
        v
Restore trong ranh giới được kiểm soát
        |
        v
Đối soát admin, credential, trust, policy và audit
        |
        v
Cập nhật theo trạng thái được phép hiện tại
        |
        v
Kiểm thử và cho phép nối vào môi trường đích
~~~

Nếu sản phẩm không cho chỉnh một phần trước khi kích hoạt, runbook phải có phương án giảm tác động phù hợp. Không hứa thực hiện được một thứ tự mà nền tảng không hỗ trợ.

### 13.3. Quyền restore và phê duyệt

Grant restore cần nêu:

- Backup ID.
- Thiết bị đích.
- Lý do.
- Phạm vi ghi đè.
- Cấu hình đang tồn tại.
- Ảnh hưởng tới người dùng.
- Điểm khôi phục nếu sai.
- Người thực hiện.
- Tiêu chí xác minh.
- Điều kiện đóng change.

Người phê duyệt cần biết artifact nào thật sự được áp, không chỉ biết tên tệp cuối cùng.

### 13.4. Đối soát với hệ thống quản lý

Nếu thiết bị được manager quản lý, cần biết sau restore:

- Manager có tự push policy khác không.
- Trạng thái thiết bị và manager có lệch không.
- HA có đồng bộ lại dữ liệu ngoài ý định không.
- Principal nào được manager tạo hoặc gắn lại.
- Bản cấu hình mới sẽ được backup theo cách nào.

Không đóng sự cố chỉ vì thiết bị khởi động được trong khi hệ thống quản lý vẫn ở trạng thái mâu thuẫn.

## 14. Khi backup bị lộ

### 14.1. Ngăn truy cập tiếp khác với thu hồi nội dung

Có thể cần chặn link, quyền kho hoặc phiên giải mã. Nhưng các biện pháp đó không tự lấy lại bản đã tải.

Đánh giá phải xác định:

- Artifact nào.
- Ai có thể đã tiếp cận.
- Bản đó mã hóa ở lớp nào.
- Khóa hoặc password có bị lộ cùng không.
- Loại secret bên trong.
- Những secret nào còn dùng hoặc được tái sử dụng.
- Phạm vi topology và thông tin bị lộ.
- Các bản sao ở công cụ trung gian.

Không kết luận an toàn chỉ vì tệp có phần mở rộng .enc.

### 14.2. Xử lý credential theo phụ thuộc

Nếu cần rotation:

- Xác định hệ thống sử dụng từng credential.
- Lập thứ tự thay đổi.
- Phối hợp các đầu VPN hoặc AAA liên quan.
- Xác minh phiên hoặc kết nối cũ.
- Đảm bảo không làm mất đường phục hồi duy nhất.
- Kiểm tra backup mới và khóa.
- Ghi nhận giá trị cũ đã bị loại khỏi sử dụng tới đâu.

Đổi password admin trên một thiết bị không xử lý mọi shared secret khác có trong artifact.

### 14.3. Không xóa khóa mù để “vô hiệu hóa backup”

Vô hiệu hóa khả năng giải mã có thể ảnh hưởng mọi bản phục hồi phụ thuộc. Nếu plaintext đã bị lấy, hành động đó cũng không thu hồi được plaintext.

Biện pháp với khóa cần dựa trên phạm vi lộ và yêu cầu recovery. Cần có người chịu trách nhiệm và kiểm tra tác động.

### 14.4. Giữ bằng chứng phù hợp

Lưu:

- Nguồn phát hiện.
- Artifact và metadata.
- Access log.
- Phiên giải mã.
- Lần chia sẻ.
- Thời điểm thu hồi.
- Rotation và xác minh.
- Phần dữ liệu còn chưa biết.

Không gửi nguyên backup bị lộ tới nhiều kênh mới trong quá trình điều tra nếu chỉ cần metadata hoặc bản trích có giới hạn.

## 15. Audit cho truy cập backup

### 15.1. Các sự kiện cần quan sát

- Export được yêu cầu và hoàn tất.
- Artifact được tạo.
- Kiểm tra toàn vẹn.
- Giải mã.
- Xem hoặc tải.
- Tạo bản đã che.
- Chia sẻ.
- Restore được yêu cầu và thực hiện.
- Thay retention.
- Xóa hoặc thay quyền.
- Thay khóa.
- Thay connector hoặc rule sanitization.
- Lỗi và ngoại lệ.

Không phải mọi nền tảng tự ghi mọi sự kiện. Cần xác định nguồn và kiểm thử từng khả năng theo phạm vi cần quản lý.

### 15.2. Sự kiện chuẩn hóa minh họa

~~~json
{
  "event": "configuration_backup_access",
  "requester": "engineer-017",
  "grantId": "NET-BACKUP-GRANT-2841",
  "backupId": "NET-BACKUP-20261126-019",
  "sourceDeviceId": "fw-billing-01",
  "action": "view_sanitized",
  "decision": "allow",
  "artifactVariant": "sanitized-019-v2",
  "sanitizationPolicy": "network-config-share-v4",
  "purposeReference": "INC-2841",
  "result": "completed",
  "correlationId": "backup-access-044"
}
~~~

Đây là schema nghiệp vụ đề xuất, không phải log nguyên bản của một sản phẩm. Không lưu secret hoặc nội dung cấu hình đầy đủ vào sự kiện này.

### 15.3. Giám sát bất thường

Các tín hiệu có ích:

- Tải nhiều thiết bị ngoài nhiệm vụ.
- Giải mã bản rất cũ không có lý do.
- Tạo link chia sẻ ngoài quy trình.
- Export tới đích mới.
- Connector lấy phạm vi rộng hơn cấu hình chuẩn.
- Backup không được mã hóa theo yêu cầu.
- Không có bản mới sau thay đổi quan trọng.
- Thay retention hoặc key bất thường.
- Restore ngoài cửa sổ.
- Sanitization lỗi hoặc bị bỏ qua.
- Đích log không nhận sự kiện.

Một tín hiệu không tự chứng minh hành vi xấu. Cần đối chiếu công việc, principal và trạng thái hệ thống.

## 16. Tránh phụ thuộc vòng trong phục hồi

### 16.1. Ví dụ vòng phụ thuộc

~~~text
Muốn lấy backup -> cần vào vault
Muốn vào vault -> cần đi qua VPN
Muốn VPN hoạt động -> cần restore cấu hình firewall
Muốn restore -> cần lấy backup và khóa
~~~

Mọi thành phần đều có thể được bảo vệ riêng nhưng recovery vẫn thất bại do phụ thuộc vòng.

### 16.2. Phương án khẩn cấp có kiểm soát

Cần xác định:

- Cách lấy artifact khi đường mạng chính mất.
- Cách dùng khóa khi dịch vụ danh tính chính không sẵn sàng.
- Người chịu trách nhiệm.
- Phạm vi quyền tạm.
- Cách lưu bằng chứng.
- Cách kết thúc ngoại lệ.
- Bản sao nào đã được kiểm tra gần nhất.

Không giải quyết bằng cách để plaintext backup và password ở một thư mục chung không có giám sát.

### 16.3. Diễn tập theo kịch bản thực tế

Có thể kiểm thử trong môi trường phù hợp:

- Mất manager.
- Mất kho chính.
- Mất đường mạng chính.
- Phải thay thiết bị.
- Khóa đã rotation.
- Mất một thành phần AAA.
- Cần phục hồi từ bản cũ.
- Một artifact không còn dùng được.

Mục tiêu là biết phần nào đã chứng minh hoạt động và phần nào còn phụ thuộc, không chỉ hoàn thành checklist trên giấy.

## 17. Bài thực hành: tách backup phục hồi và bản hỗ trợ

### 17.1. Bối cảnh

Nhóm mạng lưu backup của nhiều firewall trong một thư mục dùng chung. Kỹ sư có quyền tải toàn bộ để mở ticket hỗ trợ.

Tình trạng hiện tại:

- Một số bản có password mask, một số không.
- Tên tệp không ghi nguồn running hay candidate.
- Password giải mã được để trong cùng thư mục.
- Pipeline có quyền ghi đè và xóa mọi bản.
- Chưa từng restore trên thiết bị thay thế.
- Không biết backup cũ có tài khoản đã bị thu hồi hay không.

### 17.2. Thiết kế cần nộp

1. Phân loại artifact và nơi lưu.
2. Inventory secret và phụ thuộc khóa theo phạm vi.
3. Ma trận quyền tạo, tải, giải mã, chia sẻ, restore và xóa.
4. Metadata hoặc manifest.
5. Quy trình tạo bản đã che.
6. Grant truy cập theo công việc.
7. Runbook phục hồi trong vùng cô lập.
8. Đối soát quyền và credential sau restore.
9. Kế hoạch audit và phát hiện lỗi pipeline.
10. Kịch bản backup bị lộ.
11. Phương án khẩn cấp không có phụ thuộc vòng.
12. Kiểm thử trên bản lịch sử và thiết bị thay thế phù hợp.

### 17.3. Câu hỏi phải trả lời

- Người cần gửi ticket có thật sự cần plaintext backup phục hồi không?
- Ai có thể đồng thời tải artifact và dùng khóa?
- Connector có cần quyền xóa lịch sử không?
- Nếu tệp mới nhất là candidate sai, chọn bản phục hồi bằng cách nào?
- Nếu password mask đã thay secret, đâu là bản khôi phục thực sự?
- Nếu key version cũ không còn, artifact nào bị ảnh hưởng?
- Nếu restore đưa lại admin cũ, thành phần nào phát hiện trước khi nối production?
- Nếu backup bị tải ra ngoài, thu hồi link còn bảo đảm gì?

Bài đạt khi quyền truy cập và khả năng phục hồi cùng được chứng minh, không phải hy sinh một phía để làm phía kia đơn giản.

## 18. Ma trận kiểm thử nghiệm thu

| Phép thử | Điều cần chứng minh |
| --- | --- |
| Job export đúng thiết bị | Artifact và metadata khớp nguồn được phép |
| Yêu cầu ngoài miền quản trị | Bị giới hạn theo mô hình quyền |
| Collector thử xóa lịch sử | Bị hạn chế theo thiết kế |
| Người chỉ có metadata thử tải nội dung | Không vượt quyền |
| Người tải ciphertext thử giải mã không có grant | Không dùng được đường giải mã được kiểm soát |
| Bản chia sẻ chứa secret giả ở nhiều vị trí | Sanitization xử lý đúng hoặc báo không đạt |
| Bản masked được chọn để recovery | Phát hiện loại artifact không đáp ứng yêu cầu |
| Giải mã bản cũ sau rotation | Có khả năng phục hồi đúng phạm vi retention |
| Restore trên đích thay thế lab | Xác minh key, phiên bản và thành phần ngoài tệp |
| Restore cấu hình có admin cũ trong lab | Đối soát trước khi cho nối môi trường đích |
| Manifest hoặc artifact bị thay | Cơ chế toàn vẹn phát hiện theo phạm vi |
| Pipeline tạo tệp rỗng hoặc một phần | Không báo backup verified |
| Kho chính hoặc vault mất trong diễn tập | Quy trình khẩn cấp hoạt động đúng ranh giới |
| Hết grant hoặc link | Chặn truy cập tiếp theo thiết kế, không báo đã thu hồi bản sao |
| Truy cập và export bất thường | Có nguồn audit và quy trình đánh giá |
| Thay retention hoặc key | Có kiểm soát và đánh giá artifact phụ thuộc |
| Manager hoặc HA tự đồng bộ sau restore | Xác minh không ghi đè trạng thái ngoài ý định |

Các phép thử dùng môi trường và dữ liệu được phép. Không tạo lộ secret thật chỉ để kiểm tra phát hiện.

## 19. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| Backup cấu hình chỉ là văn bản vận hành | Có thể chứa secret và thông tin mở đường truy cập |
| Có chữ ENC hoặc chuỗi khó đọc thì chia sẻ được | Phải hiểu cơ chế bảo vệ và dữ liệu còn lộ |
| Hash password không nhạy cảm | Vẫn cần bảo vệ theo mô hình đe dọa |
| Password mask là bản phục hồi đầy đủ | Có thể thiếu hoặc thay giá trị cần thiết |
| Tệp còn đọc được nghĩa là restore được | Cần khóa, tương thích và kiểm thử |
| Backup mới nhất chắc là bản tốt nhất | Nó có thể ghi lại trạng thái lỗi hoặc trái phép |
| Người backup cần đọc và xóa mọi bản | Tách quyền theo nhiệm vụ thực tế |
| Có quyền tải thì có quyền restore | Restore là một quyết định ghi cấu hình riêng |
| Hết link là bản đã tải mất hiệu lực | Không thu hồi dữ liệu đã sao chép |
| Đổi password admin giải quyết toàn bộ backup bị lộ | Có thể còn nhiều secret và hệ thống liên quan |
| Xóa khóa là cách xử lý đơn giản | Có thể phá recovery mà không thu hồi plaintext đã lộ |
| Restore thành công là đã an toàn | Phải đối soát quyền, credential, trust và policy hiện tại |

## 20. Chỉ số duy trì kiểm soát

Các chỉ số có ích:

- Tỷ lệ thiết bị có backup đúng phạm vi và owner.
- Tỷ lệ artifact phân biệt được nguồn và loại.
- Tỷ lệ backup đáp ứng cơ chế bảo vệ đã xác nhận.
- Tỷ lệ bản lịch sử còn giải mã và phục hồi được.
- Thời gian từ thay đổi quan trọng tới backup được kiểm tra.
- Số principal có đồng thời quyền đọc plaintext và quản trị kho.
- Số đường chia sẻ ngoài quy trình.
- Tỷ lệ bản hỗ trợ đã qua sanitization.
- Số cleanup hoặc retention exception chưa xử lý.
- Kết quả diễn tập thiết bị thay thế.
- Tỷ lệ restore có đối soát danh tính và secret.
- Thời gian truy xuất artifact trong kịch bản mất hệ thống chính.
- Số phát hiện secret trong log, runner hoặc ticket.

Không dùng số tệp backup làm thước đo duy nhất. Nhiều bản không có khóa, sai loại hoặc chưa từng phục hồi có thể không đáp ứng mục tiêu vận hành.

## 21. Câu hỏi tự kiểm tra

**Vì sao quyền đọc backup được coi là quyền đặc biệt?**

Vì nó có thể cho thấy topology, policy và dữ liệu xác thực có giá trị, ngay cả khi người đọc không đăng nhập trực tiếp thiết bị.

**Bản đã che secret có thể dùng thay bản phục hồi không?**

Chỉ khi đã xác nhận nó đáp ứng đúng mục tiêu và có cách cung cấp phần bị thiếu. Không mặc định tương đương.

**Mã hóa tại kho có ngăn mọi người được cấp quyền đọc lấy plaintext không?**

Không tự bảo đảm. Cần biết lớp nào giải mã và ai có quyền dùng nó.

**Hash artifact có chứng minh bản đó an toàn để restore không?**

Không. Nó hỗ trợ đối chiếu nội dung; nguồn gốc, tính đúng và khả năng phục hồi cần kiểm tra khác.

**Vì sao phải giữ key version theo vòng đời backup?**

Vì một bản cũ có thể phụ thuộc khóa cũ. Nếu mất khóa, việc giữ tệp không còn đủ cho recovery.

**Hết hạn quyền truy cập có xóa được bản đã tải không?**

Không tự làm được. Đây là lý do cần hạn chế việc đưa plaintext ra ngoài ranh giới kiểm soát.

**Vì sao restore cần đối soát tài khoản và audit?**

Vì bản lịch sử có thể đưa lại quyền, credential hoặc cấu hình giám sát đã không còn phù hợp.

**Backup thành công có phải recovery thành công không?**

Không. Phải xác minh các mức từ artifact, khóa và tương thích tới khôi phục chức năng trong phạm vi đã thử.

Configuration backup access cần được quản lý như quyền tiếp cận cả thông tin lẫn khả năng khôi phục đặc quyền. Phân loại đúng artifact, tách quyền sử dụng, bảo vệ khóa và secret, cùng kiểm thử phục hồi có đối soát giúp Network PAM duy trì đồng thời bảo mật và khả năng vận hành khi xảy ra sự cố.
