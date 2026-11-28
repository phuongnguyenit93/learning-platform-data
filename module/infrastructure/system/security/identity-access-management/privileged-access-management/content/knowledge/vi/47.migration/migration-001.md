# Inventory hệ thống cũ trước khi migration PAM

## 1. Inventory phải trả lời điều gì?

Trong migration Privileged Access Management (PAM), inventory là quá trình xác định, đối chiếu và lưu bằng chứng về **các đường truy cập đặc quyền đang tồn tại trong hệ thống cũ**. Kết quả không chỉ là danh sách máy chủ hoặc số tài khoản đã nằm trong vault. Nó phải cho biết ai hoặc workload nào có thể sử dụng quyền gì, trên tài nguyên nào, thông qua credential và đường kết nối nào, dưới sự kiểm soát của ai.

Một máy chủ đã được đưa vào PAM vẫn có thể còn tài khoản quản trị cục bộ dùng chung, SSH key ngoài vault hoặc một đường kết nối trực tiếp chưa bị kiểm soát. Ngược lại, một credential đã được vault quản lý chưa chắc có thể luân chuyển an toàn nếu ứng dụng phụ thuộc vẫn dùng bản sao cũ.

Bài học này xây dựng inventory phục vụ quyết định migration: đối tượng nào có thể chuyển trước, đối tượng nào cần làm rõ phụ thuộc và đối tượng nào phải chặn cho đến khi có owner hoặc phương án phục hồi. Đây là bước thu thập và xác minh hiện trạng; việc đưa account vào vault, đổi mật khẩu hay thu hồi quyền là các thay đổi cần được triển khai ở giai đoạn sau.

### Mục tiêu đầu ra

Sau khi thực hiện inventory, nhóm migration cần trả lời được:

- Có những tài nguyên và tài khoản đặc quyền nào trong phạm vi đã thống nhất?
- Ai là người chịu trách nhiệm nghiệp vụ, vận hành và phê duyệt từng đối tượng?
- Những người, ứng dụng và tác vụ nào đang sử dụng credential đó?
- Quyền hiệu lực và đường truy cập thực tế khác tài liệu hiện có ở đâu?
- Hệ thống PAM cũ đang quản lý những thành phần, policy và cơ chế tích hợp nào?
- Những điều chưa biết là gì, được giao cho ai và có ảnh hưởng thế nào đến migration?

Inventory là một sản phẩm có phiên bản và ngày chốt dữ liệu. Hạ tầng tiếp tục thay đổi trong lúc migration diễn ra, nên danh sách không có cơ chế cập nhật sẽ nhanh chóng mất giá trị.

## 2. Đơn vị kiểm kê: quan hệ truy cập, không chỉ từng đối tượng

Có thể biểu diễn một đường truy cập đặc quyền như sau:

```text
Người hoặc workload
        |
        | được phép dùng
        v
Account hoặc role ---- có quyền ----> Tài nguyên
        |
        | xác thực bằng
        v
Credential ---- được lưu/phân phối bởi ----> Vault hoặc cơ chế cũ
        ^
        | được lấy và sử dụng bởi
        |
Consumer ---- kết nối qua ----> Gateway / bastion / proxy / đường trực tiếp
```

Một account có thể có nhiều credential; một credential có thể bị nhiều consumer dùng chung. Quan hệ giữa các đối tượng thường quan trọng hơn tổng số đối tượng.

Ví dụ, account `svc_backup_prod` có thể xuất hiện trên tám máy chủ. Nếu đây là tám account cục bộ khác nhau, mỗi account có vòng đời riêng. Nếu đây là một identity tập trung được cấp quyền trên tám máy chủ, identity chỉ có một bản ghi nhưng có ít nhất tám quan hệ quyền. Không phân biệt hai trường hợp sẽ làm sai kế hoạch rotation và đánh giá phạm vi ảnh hưởng.

### Các nhóm đối tượng tối thiểu

| Nhóm | Nội dung cần kiểm kê | Câu hỏi quyết định |
|---|---|---|
| Tài nguyên đích | Máy chủ, thiết bị mạng, cơ sở dữ liệu, nền tảng cloud, cluster, ứng dụng quản trị | Quyền đặc biệt được thực thi ở đâu? |
| Identity và account | Admin cá nhân, account dùng chung, service account, role, workload identity, break-glass | Chủ thể nào được cấp hoặc sử dụng quyền? |
| Quyền và policy | Nhóm quản trị, role binding, sudo, quyền database, policy kích hoạt quyền | Quyền hiệu lực đến từ những quan hệ nào? |
| Credential | Password, SSH key, certificate, token, API key, cơ chế cấp credential động | Credential được phát hành, giữ và thay đổi ra sao? |
| Consumer | Service, scheduled job, pipeline, agent, script, ứng dụng, người vận hành | Ai sẽ bị ảnh hưởng khi cách lấy credential thay đổi? |
| Đường truy cập | Gateway, session proxy, bastion, VPN, kết nối trực tiếp, console ngoài băng | Có thể đi vòng đường PAM dự kiến hay không? |
| Control plane PAM cũ | Vault, connector, tài khoản quản trị PAM, identity máy dịch vụ, chứng thư, tích hợp | Migration phụ thuộc vào thành phần quản trị nào? |
| Bằng chứng và vận hành | Log, session record, ticket, runbook, lịch sử rotation, backup, giám sát | Có thể chứng minh hiện trạng và phục hồi khi lỗi bằng gì? |

Không phải mọi secret đều là credential đặc quyền. Cần ghi rõ tiêu chí xác định đặc quyền theo từng loại tài nguyên, chẳng hạn khả năng thay đổi cấu hình bảo mật, quản lý người dùng, truy cập dữ liệu nhạy cảm hoặc thực thi lệnh quản trị. Tiêu chí này giúp tránh vừa bỏ sót workload identity mạnh, vừa đưa mọi secret ứng dụng vào cùng một nhóm rủi ro.

## 3. Chốt phạm vi và nguyên tắc thu thập

### 3.1. Phạm vi cần được mô tả rõ

Trước khi thu thập, xác định:

1. Môi trường: production, staging, development, disaster recovery và phòng lab nếu có liên hệ tin cậy.
2. Đơn vị: công ty, chi nhánh, tenant, subscription, account cloud hoặc vùng quản trị.
3. Công nghệ: hệ điều hành, cơ sở dữ liệu, thiết bị mạng, cloud, container và nền tảng ứng dụng.
4. Loại identity: người dùng nội bộ, nhà cung cấp, account khẩn cấp và identity phi con người.
5. Hệ thống PAM hiện hữu: sản phẩm cũ, vault tự xây dựng, password manager hoặc quy trình thủ công.
6. Khoảng thời gian quan sát và thời điểm chốt snapshot.
7. Ngoại lệ được loại khỏi đợt này, lý do và người chịu trách nhiệm rủi ro còn lại.

Một hệ thống bị loại khỏi wave migration hiện tại vẫn có thể nằm trong inventory. Ví dụ, thiết bị chưa được connector mới hỗ trợ cần được ghi nhận như một ngoại lệ có owner, không bị xóa khỏi danh sách để làm tỷ lệ hoàn thành đẹp hơn.

### 3.2. Ghi metadata, không tạo kho secret thứ hai

Inventory thường chứa thông tin nhạy cảm về cấu trúc hạ tầng, tài khoản mạnh và đường truy cập. Quyền đọc inventory cần được giới hạn theo nhiệm vụ; các bản xuất và bản chia sẻ cũng phải được quản lý.

Đối với credential, ghi loại, vị trí tham chiếu, trạng thái quản lý và bằng chứng xác minh. Không đưa vào inventory:

- Mật khẩu dạng rõ.
- Private key hoặc khóa giải mã.
- Token có thể sử dụng trực tiếp.
- Bản ghi session hoặc log chứa credential chưa được xử lý.
- Bản xuất vault chứa secret chỉ để đếm số lượng.

Một trường như `credential_ref: legacy-vault://safe-ops/account-042` là tham chiếu minh họa đến bản ghi được bảo vệ, không phải giá trị credential. Nếu tham chiếu chứa thông tin hạ tầng nhạy cảm, chính nó cũng cần kiểm soát truy cập.

Với SSH key hoặc certificate, fingerprint có thể hỗ trợ đối chiếu mà không thu thập private key. Tuy nhiên, fingerprint chỉ nhận diện vật liệu khóa; nó không tự chứng minh ai đang dùng khóa hoặc toàn bộ nơi khóa được tin cậy.

### 3.3. Thu thập hiện trạng không đồng nghĩa được phép thay đổi

Ưu tiên nguồn metadata và cơ chế đọc đã được phê duyệt. Nếu cần truy vấn trực tiếp hệ thống đích, xác định trước tài khoản đọc, phạm vi, tần suất và tác động.

Trong bước inventory, không tự động thử đăng nhập hàng loạt, đoán mật khẩu, đổi credential, bật rotation hoặc quét toàn mạng. Các thao tác đó có thể gây lockout, ảnh hưởng tải hoặc tạo thay đổi ngoài mục tiêu kiểm kê.

Một phép thử đăng nhập thành công cũng chỉ chứng minh một đường xác thực tại thời điểm thử. Nó không chứng minh account có đúng toàn bộ quyền cần thiết, không có đường truy cập khác hoặc mọi consumer sẽ chịu được rotation.

## 4. Mô hình dữ liệu đủ dùng cho migration

Không nên dồn mọi thứ vào một hàng rất dài mang tên “server”. Có thể dùng nhiều bảng hoặc các tập dữ liệu có liên kết ổn định.

### 4.1. Bộ dữ liệu lõi

| Tập dữ liệu | Khóa gợi ý | Một số trường quan trọng |
|---|---|---|
| Asset | `asset_id` | Loại tài nguyên, môi trường, định danh nguồn, độ quan trọng, owner, trạng thái vận hành |
| Identity | `identity_id` | Loại identity, miền hoặc tenant, định danh bất biến nếu có, owner, trạng thái vòng đời |
| Entitlement | `entitlement_id` | Identity, asset hoặc phạm vi tài nguyên, quyền, nguồn cấp quyền, điều kiện sử dụng |
| Credential | `credential_id` | Identity liên quan, loại credential, tham chiếu bảo mật, khả năng rotation, ngày xác minh |
| Consumer | `consumer_id` | Ứng dụng hoặc job, owner, môi trường, lịch chạy, cách lấy credential, yêu cầu khởi động lại |
| Dependency | `dependency_id` | Consumer, credential hoặc identity, mục đích, mức ảnh hưởng, bằng chứng |
| Access path | `path_id` | Điểm vào, thành phần trung gian, đích, giao thức, kiểm soát phiên, đường đi vòng |
| Finding | `finding_id` | Thiếu sót, mức ưu tiên, người xử lý, hạn xử lý, trạng thái, liên kết bằng chứng |

Dùng khóa nội bộ ổn định và lưu các định danh nguồn kèm theo. Tên hiển thị, hostname và địa chỉ IP đều có thể thay đổi hoặc trùng giữa các môi trường.

Không ghép hai account chỉ vì cùng tên `admin`. Các account `admin` trên hai thiết bị độc lập có thể có credential và owner khác nhau. Ngược lại, hai cách viết của cùng một identity tập trung có thể cần được hợp nhất sau khi đối chiếu định danh nguồn.

### 4.2. Trường nguồn gốc và độ tin cậy

Mỗi kết luận quan trọng nên có:

- `source_system`: nguồn cung cấp thông tin.
- `observed_at`: thời điểm dữ liệu được quan sát.
- `collected_at`: thời điểm thu thập bản xuất hoặc kết quả truy vấn.
- `evidence_ref`: tham chiếu đến bằng chứng được lưu có kiểm soát.
- `verification_state`: chưa xác minh, đã đối chiếu hoặc còn mâu thuẫn.
- `verified_by` và `verified_at`: người và thời điểm xác nhận khi có.
- `next_review_at`: thời điểm cần kiểm tra lại nếu dữ liệu có thể thay đổi.

Phân biệt thời điểm quan sát với thời điểm lấy bản xuất. Một file nhận hôm nay có thể được tạo từ snapshot đã cũ nhiều tuần.

Có thể áp dụng các mức độ tin cậy theo quy ước nội bộ, ví dụ:

| Mức | Ý nghĩa minh họa | Cách dùng |
|---|---|---|
| Chưa xác minh | Chỉ có khai báo hoặc tài liệu chưa đối chiếu | Dùng làm đầu mối điều tra |
| Đã đối chiếu | Hai nguồn độc lập phù hợp, hoặc nguồn đích phù hợp với xác nhận owner | Dùng cho thiết kế migration trong phạm vi bằng chứng |
| Còn mâu thuẫn | Nguồn dữ liệu khác nhau hoặc phát hiện quan hệ chưa giải thích được | Mở finding và chặn quyết định phụ thuộc vào thông tin đó |

Đây là quy ước của dự án, không phải thang đo bảo đảm tuyệt đối. Hai báo cáo lấy từ cùng một nguồn gốc không trở thành hai bằng chứng độc lập chỉ vì được xuất bằng hai công cụ.

### 4.3. Tách trạng thái hiện tại khỏi trạng thái mong muốn

Inventory phải phản ánh điều đang tồn tại. Các mục tiêu như “chỉ cho phép JIT” hoặc “mọi phiên phải qua gateway mới” nên được ghi ở trường thiết kế đích riêng.

Ví dụ:

```yaml
current_state:
  access_mode: shared_local_admin
  credential_management: manual
  session_recording: not_verified
target_state:
  proposed_access_mode: named_identity_with_controlled_elevation
migration_state:
  readiness: blocked
  blocker_ref: FIND-017
```

Nếu ghi ngay `access_mode: JIT` vì đó là mục tiêu migration, nhóm vận hành có thể hiểu sai rằng quyền thường trực đã được gỡ bỏ.

## 5. Nguồn dữ liệu và cách đối chiếu

Không có một nguồn duy nhất luôn đầy đủ. Mỗi nguồn phản ánh một phần hiện trạng và có giới hạn riêng.

| Nguồn | Thông tin hữu ích | Giới hạn cần kiểm tra |
|---|---|---|
| CMDB hoặc danh mục tài sản | Owner, môi trường, mức quan trọng, vòng đời | Có thể thiếu tài sản mới, tài sản ngoài quy trình hoặc owner đã đổi |
| Directory và nhà cung cấp identity | Identity, nhóm, role, quan hệ thành viên | Thành viên nhóm chưa mô tả hết quyền trên hệ thống đích |
| Cấu hình và metadata trên đích | Account cục bộ, quyền, chính sách xác thực, key được tin cậy | Cần quyền đọc phù hợp; snapshot không phản ánh thay đổi sau đó |
| Vault hoặc PAM cũ | Account đã onboard, safe, policy, connector, rotation | Không phản ánh đầy đủ credential nằm ngoài phạm vi quản lý |
| Log xác thực và log phiên | Đường truy cập, thời điểm sử dụng, identity nguồn | Thiếu log hoặc thời gian lưu ngắn có thể làm sai kết luận |
| Scheduler, service manager, pipeline | Consumer, lịch chạy, cách nhận secret | Cấu hình có thể tham chiếu gián tiếp qua biến hoặc secret store khác |
| Tài liệu và phỏng vấn owner | Quy trình, trường hợp khẩn cấp, phụ thuộc ngầm | Cần xác nhận bằng nguồn kỹ thuật hoặc ghi rõ chưa xác minh |
| Ticket và lịch sử thay đổi | Mục đích cấp quyền, ngoại lệ, thay đổi credential | Ticket đã đóng chưa chắc hiện trạng trên đích đã thay đổi tương ứng |

### 5.1. Các phép đối chiếu có giá trị

**CMDB với hệ thống đích:** Có tài nguyên hoạt động nhưng không có trong CMDB không? Có tài nguyên được ghi là đã hủy nhưng vẫn phát sinh truy cập không?

**Directory với quyền trên đích:** Account không còn trong nhóm quản trị trung tâm có còn quyền cục bộ, role trực tiếp hoặc SSH key được tin cậy không?

**PAM cũ với cấu hình đích:** Account được vault ghi nhận có thực sự tồn tại và có trạng thái phù hợp không? Có account đặc quyền trên đích chưa được PAM ghi nhận không?

**Credential với consumer:** Mỗi credential có các consumer đã biết nào? Có job theo tháng hoặc theo quý mà cửa sổ quan sát chưa bao phủ không?

**Đường truy cập dự kiến với log:** Có phiên trực tiếp từ mạng quản trị, console ngoài băng hoặc tài khoản của nhà cung cấp không đi qua cơ chế ghi phiên không?

### 5.2. Không có log không có nghĩa là không được dùng

Một account không phát sinh log trong 30 ngày có thể là account khẩn cấp, job cuối quý hoặc tài khoản chỉ dùng trong khôi phục sau sự cố. Nó cũng có thể thực sự không còn cần thiết.

Phân loại ban đầu là “chưa quan sát thấy sử dụng trong khoảng thời gian xác định”, sau đó đối chiếu lịch công việc, owner và chức năng dự phòng. Không tự chuyển kết luận đó thành “an toàn để xóa”.

Tương tự, trường `last_rotation_at` trống có thể do chưa rotation, do nền tảng không xuất dữ liệu hoặc do mất lịch sử khi nâng cấp. Cần ghi điều chưa biết và nguồn thiếu, thay vì tự thay bằng một ngày phỏng đoán.

## 6. Quy trình thực hiện inventory

### Bước 1 — Định nghĩa tiêu chí và trách nhiệm

Thống nhất tiêu chí đặc quyền, các loại đối tượng, phạm vi môi trường và cấu trúc dữ liệu. Chỉ định người chịu trách nhiệm cho từng nguồn thu thập và từng nhóm tài sản.

Nên phân biệt các vai trò:

- Business owner chịu trách nhiệm về nhu cầu và ảnh hưởng nghiệp vụ.
- Technical owner hiểu cấu hình, phụ thuộc và cách vận hành.
- Người phê duyệt truy cập quyết định ai được sử dụng quyền.
- Nhóm PAM chịu trách nhiệm nền tảng và cơ chế kiểm soát.
- Người quản lý inventory điều phối đối chiếu và chất lượng bản ghi.

Một người có thể giữ nhiều vai trò trong đơn vị nhỏ, nhưng các trách nhiệm vẫn phải được nêu rõ. Không mặc định nhóm PAM là owner nghiệp vụ của mọi service account.

### Bước 2 — Thu thập baseline theo nguồn

Thu thập metadata từ nguồn đã được chấp thuận. Lưu phạm vi truy vấn, thời điểm, định danh snapshot và vị trí bằng chứng.

Ví dụ, bản xuất account từ vault cần ghi rõ đã bao phủ safe nào, có loại trừ safe lưu trữ hay không và có bỏ qua bản ghi mà người thu thập không có quyền nhìn thấy hay không.

Khi một nguồn không truy cập được, ghi thành finding có owner và ảnh hưởng. Không thay một khu vực không thu thập được bằng số lượng bằng không.

### Bước 3 — Chuẩn hóa và hợp nhất có kiểm soát

Chuẩn hóa cách biểu diễn môi trường, tenant, miền, loại credential và owner. Giữ lại giá trị gốc hoặc liên kết đến dữ liệu nguồn để có thể truy ngược.

Các nguyên tắc hợp nhất:

1. Ưu tiên định danh ổn định do hệ thống nguồn cung cấp.
2. Dùng tổ hợp phạm vi và định danh khi tên có thể trùng.
3. Ghi lại alias đã được xác minh.
4. Không tự hợp nhất các bản ghi còn mâu thuẫn.
5. Phân biệt duplicate của bản ghi với việc credential thực sự bị dùng chung.

Hai bản ghi cùng fingerprint có thể cho thấy cùng khóa được dùng ở nhiều nơi; việc xóa một bản ghi duplicate không làm biến mất rủi ro tái sử dụng khóa trên các tài nguyên khác.

### Bước 4 — Lập quan hệ quyền và phụ thuộc

Với mỗi identity đặc quyền, xác định quyền trực tiếp và quyền gián tiếp qua nhóm, role hoặc cơ chế nâng quyền. Ghi phạm vi tài nguyên, điều kiện cấp quyền và đường truy cập.

Với mỗi credential dùng bởi workload, xác định:

- Consumer cụ thể và owner.
- Nơi consumer tham chiếu hoặc nhận credential.
- Lịch chạy và khoảng gián đoạn chấp nhận được.
- Cách tải lại credential: tự nhận bản mới, reload hay restart.
- Những bản sao hoặc cache đã biết.
- Khả năng kiểm thử sau thay đổi.
- Người có thể quyết định rollback hoặc dừng dịch vụ.

Nếu chưa biết một credential có bao nhiêu consumer, ghi `dependency_state: incomplete`. Không dùng danh sách hiện có như thể đã được chứng minh đầy đủ.

### Bước 5 — Đối chiếu với owner và nguồn kỹ thuật

Gửi owner tập bản ghi liên quan để xác nhận trách nhiệm, mục đích và phụ thuộc. Khi thông tin owner khác dữ liệu kỹ thuật, giữ cả hai dấu vết và mở finding.

Ví dụ, owner cho biết script backup đã bỏ nhưng log còn cho thấy service account xác thực mỗi đêm. Việc xác nhận qua email không đủ để bỏ qua dấu hiệu đó. Cần tìm consumer còn hoạt động hoặc giải thích được nguồn log.

### Bước 6 — Phân loại readiness và rủi ro

Sau đối chiếu, gắn trạng thái sẵn sàng theo tiêu chí đã thống nhất. Một bản ghi có thể đầy đủ về inventory nhưng vẫn chưa sẵn sàng migration vì connector mới chưa được kiểm thử.

Các chiều đánh giá nên tách nhau:

- Mức đầy đủ của inventory.
- Mức rủi ro hiện trạng.
- Độ phức tạp của phụ thuộc.
- Mức sẵn sàng kỹ thuật để migration.
- Mức sẵn sàng vận hành và phê duyệt.

Trộn các chiều này thành một nhãn “xanh” duy nhất làm mất thông tin quan trọng. Một account rủi ro cao có thể cần xử lý sớm nhưng cũng có thể cần một đợt migration riêng do tác động lớn.

### Bước 7 — Chốt phiên bản và theo dõi phần thay đổi

Chốt snapshot với thời điểm rõ ràng, lưu danh sách finding chưa giải quyết và người chịu trách nhiệm. Trong khoảng từ chốt inventory đến cutover, tiếp tục ghi nhận account, quyền, credential và consumer mới hoặc đã thay đổi.

Ngay trước migration một wave, đối chiếu lại các bản ghi thuộc wave đó. Thời hạn kiểm tra lại phụ thuộc mức độ biến động và rủi ro của môi trường; không có một số ngày duy nhất phù hợp cho mọi hệ thống.

## 7. Những phần dễ bỏ sót trong hệ thống cũ

### 7.1. Account cục bộ và quyền gián tiếp

Nhóm quản trị trong directory chỉ là một phần của quyền thực tế. Cần kiểm kê cả account cục bộ, membership trên máy đích, nhóm lồng nhau, role trực tiếp và cơ chế nâng quyền.

Đối với hệ thống kiểu Unix, tên account và UID cần được hiểu trong phạm vi host hoặc nguồn identity tương ứng. Một người có quyền sudo thông qua nhiều rule có thể có quyền hiệu lực rộng hơn nhãn role trong danh mục.

Đối với database và ứng dụng, quyền quản trị có thể phát sinh từ ownership, role kế thừa hoặc khả năng cấp lại quyền. Không suy ra mức quyền chỉ từ tên role như `readonly` hoặc `operator`.

### 7.2. Credential của workload

Service account có thể được dùng trong service, scheduled task, agent, pipeline, file cấu hình, biến môi trường hoặc một secret store trung gian. Cần tìm quan hệ consumer thay vì chỉ tìm chuỗi tên account trong một kho cấu hình.

Nếu nhiều ứng dụng dùng chung một credential, migration cần nhận diện toàn bộ nhóm phụ thuộc. Việc chuyển một ứng dụng sang cơ chế lấy secret mới chưa làm các consumer còn lại sẵn sàng cho rotation.

Đối với credential động hoặc workload identity không dùng password dài hạn, vẫn cần kiểm kê nguồn phát hành, trust policy, quyền được cấp, lifetime, cách gia hạn và khả năng quan sát hoạt động.

### 7.3. SSH key, certificate và token

Với SSH, quan hệ cần biết là khóa công khai nào được tin cậy ở đâu, ai giữ hoặc sử dụng khóa tương ứng và có đường phân phối khóa nào khác. Một private key có thể được chia sẻ ngoài quy trình, nên người tạo ban đầu chưa chắc là consumer hiện tại duy nhất.

Với certificate, ghi issuer, subject hoặc identity được ánh xạ, phạm vi sử dụng, thời điểm hết hạn, owner gia hạn và trust store liên quan. Không cần thu private key để hoàn thành inventory metadata.

Với API key và token, ghi issuer, scope, audience nếu áp dụng, thời hạn, cách thu hồi và consumer. Việc đổi mật khẩu của một account không mặc nhiên vô hiệu hóa mọi token, ticket hay phiên đã được phát hành trước đó.

### 7.4. Chính nền tảng PAM cũ

Control plane PAM thường có quyền mạnh đến nhiều hệ thống khác. Inventory cần bao phủ:

- Account quản trị PAM và cơ chế xác thực của chúng.
- Connector hoặc agent identity.
- Cơ chế phát hành, kiểm tra và rotation credential.
- Gateway, session proxy và đường mạng giữa các thành phần.
- Tích hợp với directory, IdP, MFA, ticketing và hệ thống log.
- Chứng thư, trust store, nguồn thời gian và phân giải tên.
- Backup, tài liệu recovery và người có quyền kích hoạt khôi phục.
- Policy phê duyệt, thời hạn truy cập, ngoại lệ và lịch công việc.
- Vị trí lưu session record, thời gian lưu thực tế và cách truy xuất bằng chứng.

Không mặc định có thể xuất mọi secret, khóa hoặc bản ghi phiên từ hệ thống cũ. Cần ghi nhận khả năng hỗ trợ và hạn chế kỹ thuật đã được xác minh. Một cơ chế dùng khóa không xuất được có thể đòi hỏi cấp mới credential hoặc thiết kế lại trust thay vì sao chép nguyên trạng.

### 7.5. Break-glass và truy cập của nhà cung cấp

Account khẩn cấp có thể ít được sử dụng nhưng rất quan trọng cho phục hồi. Cần xác định người chịu trách nhiệm, điều kiện kích hoạt, cách lấy credential khi IdP hoặc PAM gặp sự cố, cách ghi nhận sử dụng và quy trình xử lý sau kích hoạt.

Nhà cung cấp có thể có account riêng, account dùng chung hoặc kết nối qua công cụ từ xa. Ghi rõ thời hạn, phạm vi, người bảo trợ nội bộ và đường truy cập. Không coi việc hợp đồng đã hết hạn là bằng chứng quyền trên đích đã được thu hồi.

## 8. Ví dụ inventory: credential backup trong môi trường cũ

Giả sử một đơn vị đang chuyển từ vault cũ sang PAM mới. Danh mục ban đầu ghi nhận account `svc_backup_prod` trong vault và một máy backup trung tâm. Khi đối chiếu, nhóm phát hiện một job tạo báo cáo cũng sử dụng account này.

Dữ liệu minh họa sau chỉ chứa metadata:

```yaml
inventory_snapshot:
  id: INV-PAM-WAVE-01
  scope: production-backup
  snapshot_at: "2026-11-01T09:00:00+07:00"

identity:
  id: ID-042
  source_id: legacy-directory/account-042
  display_name: svc_backup_prod
  type: service_account
  business_owner: backup-service-owner
  technical_owner: backup-operations
  verification_state: reconciled

credential:
  id: CRED-042-A
  identity_id: ID-042
  type: password
  credential_ref: legacy-vault://safe-backup/account-042
  management_state: vaulted
  rotation_state: manual
  dependency_state: incomplete
  secret_value_collected: false

dependencies:
  - id: DEP-101
    consumer_id: backup-job-nightly
    credential_id: CRED-042-A
    schedule: nightly
    reload_behavior: requires_service_restart
    verification_state: reconciled
    evidence_ref: evidence://INV-PAM-WAVE-01/DEP-101
  - id: DEP-102
    consumer_id: report-job-monthly
    credential_id: CRED-042-A
    schedule: monthly
    reload_behavior: unknown
    verification_state: needs_owner_confirmation
    evidence_ref: evidence://INV-PAM-WAVE-01/DEP-102

access_path:
  id: PATH-019
  source: backup-network
  target_scope: backup-targets-prod
  mediation: direct
  session_visibility: not_verified

findings:
  - id: FIND-017
    subject: CRED-042-A
    issue: monthly_consumer_reload_behavior_unknown
    owner: reporting-operations
    state: open
    migration_effect: blocks_credential_rotation
  - id: FIND-018
    subject: PATH-019
    issue: direct_access_path_requires_target_design_decision
    owner: pam-migration-design
    state: open
    migration_effect: requires_access_path_review

migration:
  readiness: blocked
  blocker_refs:
    - FIND-017
  proposed_wave: wave-02-after-dependency-validation
```

Các nhãn và trạng thái trong ví dụ là schema minh họa của dự án, không phải cú pháp cấu hình một sản phẩm PAM.

### Cách đọc kết quả

Account đã nằm trong vault, nhưng điều đó chỉ xác nhận một phần trạng thái quản lý credential. Nó chưa đủ điều kiện cho rotation tự động vì còn một consumer chưa được xác nhận cách nạp credential mới.

Nhóm không cần đọc password để phát hiện điểm chặn này. Metadata từ scheduler, cấu hình tham chiếu và xác nhận owner đã đủ để hình thành finding.

Đường kết nối trực tiếp cần một quyết định thiết kế riêng. Với workload, không nhất thiết áp dụng cùng cơ chế session proxy như truy cập tương tác của con người. Cần lựa chọn kiểm soát phù hợp với giao thức, consumer và khả năng quan sát; inventory cung cấp bằng chứng cho quyết định đó.

Bước tiếp theo là tìm đúng owner job tháng, xác định cơ chế reload, xây dựng phép kiểm thử trong môi trường phù hợp và hoàn thiện danh sách consumer. Chưa đổi credential hoặc vô hiệu hóa account trong lúc xử lý inventory.

## 9. Từ inventory sang quyết định migration

### 9.1. Một bộ tiêu chí readiness minh họa

| Tiêu chí | Đủ điều kiện về mặt inventory | Ví dụ chưa đủ |
|---|---|---|
| Định danh | Asset và identity được phân biệt rõ trong đúng phạm vi | Hai account cùng tên chưa xác định có phải cùng identity |
| Ownership | Có owner có khả năng xác nhận và phối hợp xử lý | Owner là tên nhóm đã giải thể |
| Quyền | Các quyền liên quan được ghi cùng nguồn cấp và bằng chứng | Chỉ biết tên account, chưa biết quyền trên đích |
| Consumer | Các phụ thuộc trong phạm vi đã được xác nhận hoặc có ngoại lệ được xử lý rõ | Account dùng chung chưa biết hết job |
| Credential | Biết loại, vị trí tham chiếu và giới hạn quản lý | Chưa rõ có thể rotation hay cấp mới bằng cách nào |
| Đường truy cập | Đã nhận diện các đường vào và phần chưa được kiểm soát | Chỉ khảo sát gateway, chưa xem đường trực tiếp |
| Vận hành | Có người kiểm thử, tiêu chí thành công và đầu mối phục hồi | Không có owner chịu trách nhiệm khi ứng dụng lỗi |
| Độ mới | Bản ghi được kiểm tra lại theo yêu cầu của wave | Snapshot cũ, có nhiều thay đổi chưa đối chiếu |

Các tiêu chí trên chỉ xác nhận dữ liệu đủ để lập kế hoạch. Việc cutover còn cần thiết kế, thử nghiệm, phê duyệt và quy trình thay đổi tương ứng.

### 9.2. Rủi ro không chỉ dựa trên mức quyền

Ưu tiên xử lý inventory dựa trên tổ hợp yếu tố:

- Tác động khi credential bị lạm dụng.
- Khả năng truy cập từ những vùng ít được kiểm soát.
- Số người hoặc workload cùng dùng credential.
- Mức quan sát và khả năng truy vết người sử dụng.
- Số lượng và độ phức tạp của phụ thuộc.
- Khả năng rotation, thu hồi và khôi phục.
- Mức quan trọng nghiệp vụ và giới hạn gián đoạn.
- Số khoảng trống dữ liệu còn ảnh hưởng đến quyết định.

Không nên chọn chỉ những account dễ chuyển rồi tuyên bố đã giảm phần lớn rủi ro. Cần trình bày đồng thời số lượng đã xử lý và các đối tượng rủi ro cao vẫn còn ngoài wave.

## 10. Đo mức hoàn thành mà không che khuất phần chưa biết

Một chỉ số inventory phải nêu rõ đối tượng đo, mẫu số, thời điểm và tiêu chí được tính là hoàn thành.

Ví dụ, trong phạm vi đã phát hiện tại snapshot:

```text
120 identity đặc quyền được phát hiện
 96 identity có owner đã xác nhận
 84 identity đã được đối chiếu quyền
 72 identity đã hoàn tất cả owner, quyền và phụ thuộc theo tiêu chí dự án
```

Khi đó:

- Tỷ lệ có owner xác nhận: `96 / 120 = 80%`.
- Tỷ lệ đã đối chiếu quyền: `84 / 120 = 70%`.
- Tỷ lệ hoàn tất bộ tiêu chí inventory: `72 / 120 = 60%`.

Không suy ra rằng 72 identity là giao của hai nhóm đầu nếu chưa kiểm tra dữ liệu từng bản ghi. Con số 72 trong ví dụ là kết quả đánh giá độc lập trên bộ tiêu chí đầy đủ.

Tất cả tỷ lệ trên đều lấy mẫu số là **identity đã phát hiện**, không chứng minh toàn bộ identity thực tế đã được tìm thấy. Nếu một vùng hệ thống chưa thu thập được dữ liệu, báo riêng khoảng trống phạm vi đó.

Một bảng điều hành hữu ích nên thể hiện đồng thời:

1. Bao nhiêu nguồn hoặc vùng phạm vi đã thu thập thành công.
2. Bao nhiêu đối tượng đã phát hiện.
3. Bao nhiêu đối tượng có dữ liệu đủ và đã đối chiếu.
4. Bao nhiêu finding còn mở, đặc biệt finding chặn migration.
5. Bao nhiêu thay đổi mới phát sinh sau snapshot chưa được kiểm tra lại.

Khi phát hiện thêm đối tượng, tỷ lệ hoàn thành có thể giảm dù chất lượng inventory tăng. Đó là tín hiệu cần giải thích bằng thay đổi mẫu số, không phải lý do bỏ đối tượng mới ra khỏi báo cáo.

## 11. Lỗi thường gặp và cách xử lý

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng bản xuất vault làm toàn bộ inventory | Bỏ sót account và credential ngoài vault | Đối chiếu với đích, directory, consumer và đường truy cập |
| Gộp theo username hoặc IP | Nhầm identity và phạm vi rotation | Dùng định danh nguồn, phạm vi quản trị và khóa nội bộ ổn định |
| Thu password để chứng minh credential tồn tại | Tạo thêm nơi lộ secret | Dùng tham chiếu và bằng chứng metadata phù hợp |
| Coi account ít dùng là account bỏ đi | Làm hỏng tác vụ định kỳ hoặc khả năng recovery | Đối chiếu lịch chạy, owner và mục đích dự phòng |
| Ghi mục tiêu tương lai vào trường hiện trạng | Thiết kế migration dựa trên thông tin sai | Tách current state, target state và readiness |
| Xem owner khai báo là xác nhận đầy đủ | Phụ thuộc ngầm vẫn tồn tại | Đối chiếu với bằng chứng kỹ thuật và lưu mâu thuẫn |
| Bỏ qua nền tảng PAM cũ | Thiếu connector, trust hoặc dữ liệu phục hồi lúc cutover | Kiểm kê control plane và tích hợp liên quan |
| Chốt danh sách một lần rồi dùng nhiều tháng | Bỏ sót thay đổi trong thời gian migration | Theo dõi delta và kiểm tra lại từng wave |
| Xóa duplicate mà không giữ quan hệ | Mất thông tin credential dùng chung | Hợp nhất bản ghi có truy vết, giữ đầy đủ dependency |
| Dùng một tỷ lệ “đã xong” cho mọi chiều | Che rủi ro và khoảng trống phạm vi | Tách coverage, chất lượng dữ liệu và readiness |

## 12. Thực hành trên một phạm vi nhỏ

Chọn một ứng dụng có tài khoản dịch vụ và một nhóm máy chủ đích trong môi trường được phép khảo sát. Không thu giá trị secret và không thực hiện thay đổi cấu hình.

### Nhiệm vụ

1. Mô tả phạm vi, nguồn dữ liệu và tiêu chí xác định quyền đặc biệt.
2. Lập bản ghi asset, identity, credential metadata và consumer.
3. Vẽ ít nhất một đường truy cập cùng các quan hệ quyền.
4. Tìm một điểm có thể đối chiếu giữa hai nguồn khác nhau.
5. Ghi một thông tin còn chưa biết dưới dạng finding, có owner và tác động.
6. Đề xuất trạng thái readiness cùng lý do dựa trên bằng chứng.
7. Xác định những thay đổi nào cần được theo dõi sau snapshot.

### Tình huống để tự kiểm tra cách làm

Một account dịch vụ có trong vault và không có log tương tác trong 45 ngày. Owner cho biết account dùng cho job cuối tháng, nhưng chưa tìm được cấu hình job. Mật khẩu được ghi nhận rotation lần cuối cách đây sáu tháng.

Kết luận phù hợp ở thời điểm inventory là:

- Account đã được phát hiện và có tham chiếu quản lý trong vault.
- Chưa đủ bằng chứng để xác nhận các consumer và lịch sử sử dụng thực tế.
- Chưa thể suy ra account không còn cần thiết từ việc thiếu log tương tác.
- Cần kiểm tra nguồn log workload, scheduler, phạm vi retention và xác nhận kỹ thuật của owner.
- Trạng thái sẵn sàng rotation cần phản ánh phụ thuộc chưa rõ; không đổi mật khẩu chỉ để kiểm tra xem ứng dụng nào bị lỗi.

Kết quả thực hành đạt yêu cầu khi người khác có thể truy từ kết luận đến nguồn bằng chứng, nhận diện phần chưa biết và hiểu điều gì phải được giải quyết trước migration.

## 13. Bộ bàn giao inventory

Bộ bàn giao nên chứa các thành phần sau, dưới quyền truy cập phù hợp:

- Phạm vi và tiêu chí xác định đặc quyền.
- Snapshot có phiên bản, thời điểm chốt và định danh nguồn.
- Các tập dữ liệu cùng quan hệ asset, identity, quyền, credential và consumer.
- Danh sách đường truy cập và phần chưa được xác minh.
- Xác nhận ownership và các mâu thuẫn còn mở.
- Finding có mức ưu tiên, owner, hạn xử lý và ảnh hưởng đến migration.
- Phân loại readiness cùng tiêu chí được áp dụng.
- Danh sách thay đổi phát sinh sau snapshot và quy trình cập nhật.
- Tham chiếu đến bằng chứng, không kèm giá trị credential.

Giá trị của inventory nằm ở khả năng hỗ trợ quyết định có căn cứ. Một danh sách nhỏ, đúng phạm vi và chỉ rõ khoảng trống có ích hơn một danh sách lớn chứa nhiều kết luận không kiểm chứng. Khi biết đầy đủ các quan hệ và phần còn chưa biết, nhóm migration mới có cơ sở chọn wave, thiết kế kiểm soát và kiểm thử việc chuyển đổi PAM an toàn.
