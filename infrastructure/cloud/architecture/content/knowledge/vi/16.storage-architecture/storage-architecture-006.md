# Phiên bản đối tượng, tính bất biến và chống xóa nhầm

Object storage thường được dùng để lưu ảnh, video, tài liệu, bản xuất dữ liệu, log và backup với dung lượng lớn. Khả năng mở rộng và độ bền của dịch vụ không tự bảo vệ dữ liệu khỏi mọi thao tác sai. Một người dùng có quyền hợp lệ vẫn có thể ghi đè nhầm object, xóa nhầm cả prefix, chạy nhầm lifecycle rule hoặc bị chiếm credential rồi xóa dữ liệu hàng loạt. Replication cũng có thể sao chép một thao tác xóa hoặc nội dung độc hại sang nơi khác.

Để bảo vệ dữ liệu, kiến trúc lưu trữ cần thiết kế cùng lúc **versioning, tính bất biến (immutability), retention, legal hold, soft delete, Object Lock, quyền truy cập và quy trình phục hồi**. Các cơ chế này có quan hệ nhưng không thay thế lẫn nhau. Versioning giữ các phiên bản; immutability ngăn sửa/xóa trong một khoảng thời gian hoặc theo chính sách; retention và legal hold quyết định thời gian phải bảo toàn; soft delete tạo khoảng phục hồi sau thao tác xóa; Object Lock là một nhóm khả năng bảo vệ object mà một số dịch vụ cung cấp.

Trong module **CLOUD_ARCHITECTURE**, bài học này giúp thiết kế lưu trữ đáp ứng độ tin cậy, bảo mật, chi phí và vận hành theo tư duy Well-Architected. Mục tiêu là trả lời được: **nếu object bị ghi đè, xóa nhầm, tài khoản production bị chiếm hoặc có yêu cầu pháp lý giữ dữ liệu, tổ chức có thể chứng minh dữ liệu còn nguyên và phục hồi đúng phạm vi hay không?**

## 1. Phân biệt object versioning, immutability và retention

| Khái niệm | Điều nó làm | Điều nó không tự bảo đảm |
| --- | --- | --- |
| **Object versioning** | Lưu nhiều phiên bản của cùng một object key khi được bật và cấu hình đúng | Không ngăn người có quyền xóa mọi phiên bản hoặc xóa cả bucket |
| **Immutability** | Ngăn object/version bị sửa hoặc xóa trong điều kiện được policy bảo vệ | Không tự ngăn xóa metadata khác, xóa bucket hoặc phá ứng dụng đọc |
| **Retention** | Xác định thời gian tối thiểu dữ liệu phải được giữ | Không đồng nghĩa dữ liệu phải được giữ vĩnh viễn |
| **Legal hold** | Giữ object cho tới khi được gỡ hold hợp lệ, thường phục vụ nghĩa vụ pháp lý/điều tra | Không tự xác định thời hạn retention hoặc ai có quyền phê duyệt |
| **Soft delete** | Đánh dấu dữ liệu đã xóa để có thể phục hồi trong một khoảng thời gian | Không phải backup độc lập và có thể cùng chịu ảnh hưởng của quyền quản trị |
| **Object Lock / WORM** | Cơ chế khóa object để ngăn ghi đè/xóa theo retention hoặc hold | Không tự bảo vệ credential, encryption key, ứng dụng hay mọi bản sao khác |
| **Replication** | Sao chép object/version sang bucket, account hoặc region khác | Không tự tạo bản backup độc lập; thao tác xóa có thể được sao chép |
| **Backup** | Tạo bản sao phục vụ khôi phục theo thời điểm/phạm vi | Không có giá trị nếu không kiểm thử restore và kiểm soát quyền xóa |

**WORM (Write Once, Read Many)** là nguyên tắc ghi một lần, sau đó chỉ đọc trong phạm vi bảo vệ. Một hệ thống WORM không cho phép sửa nội dung đã khóa trong thời gian quy định, kể cả khi một người dùng có quyền ghi thông thường muốn thay thế nó. Cơ chế cụ thể phụ thuộc dịch vụ: có nơi khóa theo object version, có nơi dùng retention policy ở cấp container/bucket hoặc immutable backup vault.

### Vì sao cần nhiều lớp?

Một bản ghi hóa đơn có thể có versioning bật. Điều này giúp phục hồi khi bị ghi đè, nhưng người dùng có quyền xóa mọi version vẫn có thể xóa sạch. Nếu version hiện tại được bảo vệ bằng retention, việc xóa version bị chặn trong thời hạn đó. Nếu có legal hold, dữ liệu tiếp tục được giữ theo yêu cầu pháp lý ngay cả khi thời hạn retention thông thường đã tới. Một bản sao trong account khác còn giúp phục hồi khi account production bị xâm phạm.

## 2. Object key, version ID và vòng đời phiên bản

Trong object storage, object thường được định danh bởi bucket/container và key. Khi versioning được bật, một key có thể có nhiều phiên bản; mỗi version có định danh riêng. Một thao tác PUT mới thường tạo phiên bản mới thay vì sửa nội dung version cũ. Thao tác DELETE có thể tạo delete marker hoặc soft-delete state tùy dịch vụ.

~~~mermaid
flowchart TB
    KEY["Object key: invoices/2026/INV-001.pdf"]
    KEY --> V1["Version v1"]
    KEY --> V2["Version v2"]
    KEY --> V3["Version v3 (current)"]
    KEY --> DM["Delete marker / soft-deleted state"]
    V1 -->|Có thể khôi phục| RESTORE["Restore version"]
    V2 -->|Có thể khôi phục| RESTORE
    V3 -->|Đọc version hiện tại| CURRENT["Current object"]
~~~

Hình mô tả khái niệm. Tên version, delete marker, soft delete và thao tác đọc version cụ thể khác nhau giữa nhà cung cấp. Phải xác minh hành vi API và policy trước khi xây runbook.

### Các thao tác thường gặp

- **PUT/overwrite:** ghi object mới cùng key; nếu versioning bật, có thể tạo version mới.
- **GET current:** đọc phiên bản hiện hành theo quy tắc dịch vụ.
- **GET specific version:** đọc phiên bản xác định bằng version ID hoặc generation.
- **DELETE:** có thể tạo delete marker/soft-delete marker thay vì xóa vật lý ngay.
- **Delete specific version:** xóa chính xác một phiên bản; có thể bị retention/object lock chặn.
- **List versions:** liệt kê current và noncurrent versions để kiểm kê/khôi phục/lifecycle.

### Versioning có chi phí

Mỗi lần upload hoặc overwrite có thể giữ thêm dung lượng. Nếu ứng dụng liên tục ghi object cùng key, số phiên bản có thể tăng nhanh; file tạm, multipart upload dở và delete marker cũng có thể làm tăng chi phí quản trị. Cần lifecycle policy cho noncurrent versions, nhưng policy không được xóa phiên bản còn trong retention hoặc đang legal hold.

### Chọn object key để giảm rủi ro

Với dữ liệu quan trọng, key bất biến hoặc có version định danh thường dễ audit hơn key ghi đè liên tục. Ví dụ lưu file theo UUID/content hash và giữ một metadata pointer trỏ tới version hiện tại. Cần đảm bảo pointer update có concurrency control; không nên coi key ngẫu nhiên là bảo vệ truy cập thay cho IAM.

## 3. Bật versioning và hiểu delete marker

Versioning giúp phục hồi lỗi thao tác khi các phiên bản cũ vẫn còn. Một số lưu ý:

1. Versioning thường phải được bật trước khi xảy ra thao tác ghi/xóa cần phục hồi; bật sau không tạo lại các phiên bản đã mất.
2. Versioning ở trạng thái suspended/disabled có semantics khác active; kiểm tra trạng thái chính xác.
3. Delete có thể tạo delete marker khiến object không còn hiển thị qua thao tác GET mặc định, trong khi version cũ vẫn còn.
4. Xóa delete marker có thể làm phiên bản trước trở thành current trở lại; thao tác này phải có kiểm soát.
5. Người có quyền xóa version cụ thể có thể loại bỏ khả năng phục hồi nếu không có retention/immutability bảo vệ.

### Kịch bản overwrite nhầm

Một ứng dụng upload file hóa đơn sai nội dung vào key đã tồn tại. Khi versioning bật:

- Phiên bản mới trở thành current.
- Phiên bản cũ vẫn có thể đọc bằng version ID.
- Người vận hành xác minh đúng version từ audit/log/metadata rồi khôi phục hoặc tạo bản current mới từ nội dung đúng.
- Không xóa version sai nếu nó là bằng chứng phục vụ điều tra hoặc nằm trong retention/legal hold.

### Kịch bản delete nhầm

Người dùng xóa một prefix chứa nhiều file. Với versioning, delete marker có thể được tạo cho từng key hoặc có semantics riêng theo dịch vụ. Người vận hành cần:

- Xác định chính xác bucket, prefix, khoảng thời gian và actor.
- Liệt kê versions/delete markers.
- Kiểm tra retention/legal hold.
- Khôi phục theo tập key đã kiểm chứng, tránh xóa marker hoặc copy nhầm dữ liệu.
- Đối chiếu số object và checksum sau restore.

Không nên viết một script xóa delete marker đại trà khi chưa chạy dry-run và xác minh phạm vi.

## 4. Immutability, WORM và Object Lock

Immutability bảo vệ nội dung khỏi thay đổi hoặc xóa trong khoảng thời gian/điều kiện được quy định. Với object storage, một cách triển khai phổ biến là Object Lock/WORM theo từng object version hoặc storage container.

Hai kiểu retention thường gặp:

- **Governance mode:** một số thao tác đặc quyền có thể bypass hoặc thay đổi bảo vệ nếu người gọi có quyền phù hợp và cung cấp điều kiện bắt buộc. Mode này hữu ích cho quản trị có kiểm soát nhưng không phải bảo vệ tuyệt đối trước admin có quyền bypass.
- **Compliance mode:** object được bảo vệ nghiêm ngặt hơn; trong thời gian retention, ngay cả quyền quản trị cao cũng không thể rút ngắn/xóa theo semantics của dịch vụ. Chỉ chọn khi yêu cầu pháp lý và quy trình dữ liệu đã được xác nhận.

Một số dịch vụ cung cấp tên gọi hoặc mức kiểm soát khác nhau. Không mặc định governance/compliance trên mọi cloud có semantics giống nhau; cần đọc tài liệu của dịch vụ và kiểm tra bằng tài khoản thử nghiệm.

### Object Lock theo version

Một object version được khóa có thể không bị overwrite/xóa vật lý trong thời hạn bảo vệ. Một lần PUT cùng key có thể tạo version mới tùy service, nhưng bản version đã khóa vẫn phải được bảo toàn. Vì vậy cần phân biệt:

- **Tên key hiện tại** người dùng nhìn thấy.
- **Version đang current** sau lần upload mới.
- **Version đã được Object Lock bảo vệ**.
- **Delete marker** che object trong truy vấn mặc định.

Khóa một version không có nghĩa toàn bộ key, bucket hoặc metadata bên ngoài đều bất biến. Phải kiểm tra chính xác phạm vi enforcement.

### Default retention và per-object retention

Một bucket/container có thể đặt retention mặc định, áp dụng cho object mới. Một số dịch vụ cho phép retention khác nhau theo từng version hoặc policy. Default retention giúp giảm nguy cơ developer quên khóa, nhưng có thể giữ file tạm, dữ liệu sai hoặc dữ liệu nhạy cảm lâu hơn yêu cầu. Cần chọn policy theo loại dữ liệu và data classification.

### Retention không phải backup

Object Lock ngăn xóa/sửa trong một thời hạn, nhưng không đảm bảo ứng dụng có thể tìm thấy object, key mã hóa còn dùng được, bucket không bị mất quyền truy cập hoặc một lỗi logic không làm dữ liệu mới ghi sai. Cần backup/replication, catalog, kiểm tra tính toàn vẹn và restore test.

## 5. Retention policy và legal hold

Retention policy xác định thời gian dữ liệu phải được giữ. Thời hạn có thể tính từ lúc object được tạo, lúc version được khóa, hoặc một mốc sự kiện do tổ chức định nghĩa. Cần thống nhất cách tính giữa nghiệp vụ, pháp chế, compliance và đội vận hành.

Ví dụ minh họa:

| Loại dữ liệu | Retention tham khảo | Cân nhắc |
| --- | --- | --- |
| Hóa đơn/chứng từ | Theo nghĩa vụ kế toán/pháp lý áp dụng | Không tự chọn số năm nếu chưa xác nhận quy định và loại hình tổ chức |
| Log bảo mật | Theo mức rủi ro và chính sách điều tra | Dung lượng, quyền truy cập, dữ liệu cá nhân |
| Backup database | Theo RPO/RTO và khả năng point-in-time recovery | Bản đầy đủ, incremental, transaction log |
| File upload tạm | Ngắn hạn theo quy trình xử lý | Không giữ vô hạn; phải xóa an toàn khi hết hạn |
| Hồ sơ hợp đồng | Theo thời hạn hợp đồng và nghĩa vụ sau kết thúc | Legal hold có thể kéo dài hơn retention thường |

Các khoảng thời gian là quyết định chính sách, không phải giá trị mặc định kỹ thuật. Cần có owner phê duyệt, tài liệu hóa nguồn yêu cầu và cơ chế xem xét khi quy định thay đổi.

### Legal hold là gì?

Legal hold là yêu cầu bảo toàn dữ liệu liên quan đến tranh chấp, điều tra, kiểm toán hoặc nghĩa vụ pháp lý. Trong thời gian hold, dữ liệu không được xóa theo lifecycle thông thường dù retention mặc định đã hết. Hold có thể áp dụng cho một object, một nhóm dữ liệu hoặc một tập hồ sơ đã xác định.

Quy trình quản lý legal hold cần trả lời:

1. Ai có quyền tạo, xem và gỡ hold?
2. Hold áp dụng lên object/version nào và theo tiêu chí tìm kiếm nào?
3. Làm sao đảm bảo object mới liên quan được đưa vào hold?
4. Lifecycle rule có kiểm tra hold trước khi xóa không?
5. Ai phê duyệt việc gỡ hold và bằng chứng phê duyệt được lưu ở đâu?
6. Có audit trail đầy đủ cho mọi lần tạo/gỡ hold không?

Không nên cấp quyền gỡ legal hold rộng cho ứng dụng upload thông thường. Nên dùng vai trò tách biệt, phê duyệt nhiều bước và ghi audit ở hệ thống độc lập.

### Retention lock và policy drift

Một số dịch vụ cho phép khóa cấu hình retention ở cấp bucket/container để ngăn giảm thời hạn sau khi đã bắt đầu bảo vệ dữ liệu. Điều này hữu ích cho compliance nhưng làm sai cấu hình ban đầu khó sửa. Cần:

- Thử policy trên môi trường không chứa dữ liệu thật.
- Xác nhận timezone, mốc bắt đầu và hành vi object version.
- Kiểm tra policy có áp cho object đã tồn tại hay chỉ object mới.
- Kiểm soát ai có thể đổi default retention, mode và thời hạn.
- Dùng IaC/policy-as-code để phát hiện drift.

## 6. Soft delete và khoảng phục hồi

Soft delete thường giữ object hoặc metadata đã xóa trong một khoảng thời gian trước khi xóa vĩnh viễn. Tùy dịch vụ, nó có thể được gọi là deleted-object retention, recycle bin, recoverable delete hoặc version/delete marker behavior.

Soft delete hữu ích khi:

- Người dùng xóa nhầm file hoặc thư mục.
- Một thao tác batch xóa nhầm prefix.
- Ứng dụng lỗi thực hiện delete trước khi hoàn tất workflow.
- Quản trị viên cần phục hồi dữ liệu trong cửa sổ ngắn.

Nhưng soft delete không bảo vệ mọi failure mode:

- Người có quyền đặc biệt có thể xóa vĩnh viễn hoặc rút ngắn cửa sổ phục hồi.
- Retention hết hạn thì dữ liệu có thể bị xóa theo policy.
- Malware có thể mã hóa object rồi ghi version mới; soft delete không tự nhận biết nội dung tốt/xấu.
- Nếu quyền truy cập, account hoặc encryption key bị xâm phạm, dữ liệu có thể không còn đọc được dù vẫn tồn tại.
- Nhiều object bị xóa có thể làm việc phục hồi hàng loạt khó khăn và tốn phí.

### Soft delete và versioning phối hợp

Khi cả hai cùng bật, cần kiểm tra thứ tự hành vi:

1. DELETE object có tạo delete marker, soft-delete record hay cả hai?
2. Version cũ được giữ ở đâu và có thể đọc trực tiếp bằng version ID không?
3. Khôi phục object có xóa marker hay tạo một version mới?
4. Lifecycle rule có áp cho noncurrent versions, marker và soft-deleted objects không?
5. Retention/Object Lock có ngăn xóa vật lý sau khi hết soft-delete window không?

Không có semantics phổ quát cho mọi nhà cung cấp. Viết test case theo dịch vụ cụ thể và lưu lại kết quả để runbook không dựa vào giả định.

## 7. Replication không tự đồng nghĩa backup

Replication sao chép object hoặc thay đổi sang một bucket/container khác. Nó có thể hỗ trợ khả năng truy cập, gần người dùng, phân tích hoặc DR. Nhưng nếu cấu hình replicate delete marker, overwrite hoặc nội dung mã hóa độc hại, bản sao cũng có thể bị ảnh hưởng.

| Cơ chế | Mục đích | Cần kiểm tra |
| --- | --- | --- |
| **Same-region replication** | Tạo bản sao trong cùng khu vực hoặc domain dịch vụ | Phạm vi failure domain, consistency và phí |
| **Cross-region replication** | Duy trì bản sao ở region khác, hỗ trợ DR và locality | Replication lag, residency, encryption key, delete semantics |
| **Cross-account replication** | Tách quyền sở hữu và blast radius | IAM trust, destination ownership, account admin và policy |
| **Backup copy** | Giữ điểm phục hồi theo lịch/chính sách riêng | Retention, immutable vault, catalog và restore |

### Kịch bản xóa nhầm lan sang bản sao

Ứng dụng có quyền xóa object và replication được cấu hình sao chép delete marker. Người dùng xóa nhầm prefix ở bucket nguồn; marker được chuyển tới bucket đích, khiến object không còn hiện qua GET mặc định ở cả hai nơi. Nếu destination cũng cho phép xóa version và dùng chung danh tính quản trị, một thao tác sai có thể ảnh hưởng cả hai.

Các biện pháp giảm rủi ro:

- Tách account và role sở hữu destination; source workload không có quyền xóa bản sao.
- Dùng retention/Object Lock tại destination khi cần bảo vệ.
- Xác định có replicate delete marker không; có thể dùng cấu hình chỉ replicate object/version theo yêu cầu.
- Giữ backup theo lịch với quyền và retention độc lập.
- Diễn tập phục hồi khi source bị xóa, bị khóa account hoặc bị compromise.

### Replication lag và consistency

Cross-region replication thường bất đồng bộ; object mới ghi có thể chưa xuất hiện ở destination ngay lập tức. Ứng dụng không nên trả lời người dùng rằng bản sao đã có ở region khác nếu chưa có xác nhận tương ứng. Theo dõi replication pending bytes, object age/lag, failure count và policy conflict nếu dịch vụ hỗ trợ.

## 8. Backup độc lập và immutable backup

Backup khác với versioning ở mục tiêu và phạm vi:

- Versioning giúp khôi phục phiên bản object trước đó trong cùng hệ thống.
- Backup tạo bản sao phục vụ khôi phục theo lịch, tập dữ liệu và điểm thời gian đã định.
- Immutable backup bảo vệ bản backup khỏi bị thay đổi/xóa trong thời hạn giữ.

Một thiết kế backup có thể sử dụng:

1. Tài khoản/bucket backup do vai trò riêng quản lý.
2. Quyền ghi backup từ production nhưng hạn chế quyền xóa hoặc thay đổi retention.
3. Object Lock/immutable retention ở đích nếu yêu cầu.
4. Mã hóa bằng khóa có vòng đời và quyền truy cập được kiểm soát riêng.
5. Catalog hoặc manifest để biết backup chứa object nào và thời điểm nào.
6. Kiểm tra checksum, inventory và báo cáo backup thành công/thất bại.
7. Restore vào vùng cô lập để kiểm tra khả năng đọc và tính toàn vẹn.

### Backup không được phụ thuộc hoàn toàn vào credential production

Nếu ransomware chiếm một workload role có quyền xóa object nguồn và bản backup cùng account, tổ chức có thể mất cả hai. Tách account, permission boundary, vault policy, MFA/approval cho thao tác phá hủy và immutable retention giúp giảm blast radius. Cần kiểm tra cả quyền của organization administrator/cloud root; không chỉ IAM role của ứng dụng.
## 9. Lifecycle policy: tự động hóa nhưng không phá dữ liệu cần giữ

Lifecycle policy tự động chuyển tier, hết hạn, xóa phiên bản cũ hoặc dọn multipart upload chưa hoàn tất. Nó giúp giảm chi phí và công việc thủ công, nhưng một rule sai có thể xóa hàng loạt dữ liệu.

Các hành động thường gặp:

- Chuyển current object sang storage tier có chi phí lưu thấp hơn sau một số ngày.
- Chuyển noncurrent version sang tier archive.
- Xóa noncurrent version sau khi hết retention.
- Xóa delete marker khi không còn version cũ phù hợp.
- Dọn multipart upload chưa hoàn tất.
- Xóa object hết hạn theo prefix/tag.

### Nguyên tắc thiết kế lifecycle

1. **Phân loại trước:** bucket/prefix/tag cần phân biệt dữ liệu tạm, nội dung người dùng, chứng từ, backup và log.
2. **Retention ưu tiên:** lifecycle không được làm mất dữ liệu còn trong retention hoặc legal hold; xác minh dịch vụ có enforce tự động hay policy cần thiết kế riêng.
3. **Mô phỏng trước:** xem danh sách object sẽ bị chuyển/xóa bằng inventory, dry-run hoặc công cụ preview nếu có.
4. **Canary theo phạm vi:** áp policy lên một prefix/nhóm object trước, sau đó mở rộng.
5. **Theo dõi sau rollout:** số lượng object/version bị chuyển/xóa, chi phí, lỗi đọc từ tier archive và khả năng phục hồi.
6. **Kiểm soát thay đổi:** policy được review như code, không để mỗi nhóm tự thêm rule rộng trên bucket dùng chung.

### Tầng lưu trữ và chi phí truy xuất

Storage tier lạnh có thể rẻ hơn về dung lượng nhưng tốn phí retrieval, có thời gian khôi phục và yêu cầu tối thiểu thời gian lưu. Nếu ứng dụng cần đọc thường xuyên, chuyển sang archive có thể làm tăng latency và chi phí tổng. Dự báo dựa trên access pattern, không chỉ số ngày kể từ khi tạo.

### Ví dụ policy theo nhóm dữ liệu

| Nhóm | Chính sách gợi ý để đánh giá |
| --- | --- |
| Upload tạm | Xóa sau thời gian ngắn đã được nghiệp vụ xác nhận |
| Media công khai ít truy cập | Chuyển tier khi access giảm, giữ phiên bản theo yêu cầu |
| Hóa đơn/chứng từ | Retention/legal hold theo chính sách được phê duyệt, không tự động xóa sớm |
| Backup | Immutable retention, lifecycle sau khi hết cửa sổ phục hồi |
| Log bảo mật | Tier theo độ tuổi, retention theo chính sách, audit quyền truy cập |

Không dùng cùng một lifecycle rule rộng cho bucket chứa nhiều loại dữ liệu với nghĩa vụ lưu giữ khác nhau.

## 10. Quyền truy cập: bảo vệ cả object và khả năng xóa

Object storage có nhiều lớp quyền: bucket/container policy, identity policy, access point, ACL nếu dịch vụ còn hỗ trợ, key policy, retention permission và quyền quản trị account. Cần thiết kế cả quyền đọc/ghi lẫn quyền có thể phá hủy dữ liệu.

### Tách quyền theo vai trò

| Vai trò | Quyền cần thiết | Quyền nên hạn chế |
| --- | --- | --- |
| Ứng dụng upload | Put object vào prefix của mình | List toàn bucket, delete version, đổi retention |
| Ứng dụng đọc | Get object theo prefix cần dùng | Put/delete, đổi policy, xem backup |
| Lifecycle service | Thực hiện hành động lifecycle được phê duyệt | Thay đổi Object Lock/legal hold toàn bucket |
| Backup writer | Ghi bản backup và metadata cần thiết | Xóa backup cũ, rút ngắn retention |
| Restore operator | Đọc backup, tạo target và phục hồi theo phê duyệt | Thay đổi source backup hoặc xóa bản gốc |
| Compliance/legal | Đặt/gỡ legal hold theo quy trình | Quyền quản trị ứng dụng thường ngày |
| Security auditor | Đọc audit, inventory, policy và báo cáo | Sửa object hoặc retention |

### Quyền xóa cần được xem riêng

Trong một số dịch vụ, quyền delete object thường khác với quyền xóa version cụ thể; quyền bypass retention hoặc xóa legal hold có thể là permission độc lập. Tên permission khác theo provider. Đừng chỉ kiểm tra policy có PutObject/GetObject; hãy liệt kê mọi quyền có thể:

- Xóa current object hoặc tạo delete marker.
- Xóa version cụ thể.
- Bypass governance retention.
- Thay đổi hoặc gỡ legal hold.
- Tắt versioning hoặc thay đổi default retention.
- Xóa bucket/container hoặc sửa replication/lifecycle policy.
- Xóa encryption key hoặc thu hồi quyền dùng khóa.

### MFA/approval cho thao tác nhạy cảm

Các hành động như xóa bucket production, xóa nhiều version, rút ngắn retention hoặc gỡ legal hold nên có approval, xác thực tăng cường và audit. Một số cloud cung cấp MFA delete, vault lock, multi-party approval hoặc policy guardrail; phải xác minh sản phẩm hỗ trợ và cách cấu hình. Không coi MFA cho đăng nhập console là đủ nếu API role vẫn có thể thực hiện delete hàng loạt.

## 11. Chống ransomware và xóa nhầm

Ransomware trên object storage có thể biểu hiện dưới dạng mã hóa file rồi ghi đè, đổi metadata, xóa version hoặc xóa key truy cập. Các biện pháp cần phối hợp:

- Versioning để giữ các phiên bản trước.
- Object Lock/immutable backup để bảo vệ bản sao quan trọng.
- Cross-account backup để giảm blast radius.
- IAM least privilege và tách quyền backup writer với backup deleter.
- Phát hiện thao tác bất thường như tăng đột biến PUT/DELETE, xóa version hoặc thay đổi policy.
- Throttle/deny theo điều kiện khi nguồn phát sinh hành vi phá hủy không bình thường nếu nền tảng hỗ trợ.
- Inventory, checksum và baseline số lượng object/phiên bản.
- Quy trình cô lập credential, dừng sync/replication nếu cần, bảo toàn bằng chứng và restore trong vùng sạch.

### Phát hiện sớm

| Tín hiệu | Vì sao quan trọng |
| --- | --- |
| DELETE/DELETE version tăng đột biến | Có thể là thao tác xóa nhầm hoặc credential bị compromise |
| PUT cùng key với tần suất bất thường | Có thể overwrite hàng loạt hoặc mã hóa nội dung |
| Retention/Object Lock policy thay đổi | Có thể đang cố giảm lớp bảo vệ |
| Replication delete marker tăng | Hành động xóa có thể lan sang destination |
| Số version/object tăng bất thường | Có thể phát sinh chi phí hoặc tấn công ghi lặp |
| Lifecycle rule sửa đổi | Có thể tạo điều kiện xóa dữ liệu hàng loạt |
| KMS/key permission thay đổi | Có nguy cơ làm dữ liệu không thể giải mã |

Lưu audit ở nơi có quyền và retention độc lập với bucket dữ liệu. Nếu log chỉ lưu trong cùng tài khoản và role bị xâm phạm có thể xóa, bằng chứng có thể bị phá hủy cùng dữ liệu.

### Kịch bản ứng phó

1. **Cô lập danh tính bị xâm phạm:** thu hồi/rotate credential, disable role hoặc giới hạn network theo quy trình.
2. **Bảo toàn bằng chứng:** giữ audit log, policy version, request ID, actor và thời điểm.
3. **Ngăn lan truyền:** tạm dừng workload/automation hoặc replication liên quan nếu cần và nếu điều đó không phá hủy dữ liệu tốt.
4. **Xác định phạm vi:** bucket, prefix, key, version, delete marker, retention, legal hold và region bị ảnh hưởng.
5. **Chọn nguồn phục hồi đáng tin:** backup immutable hoặc version đã xác minh trước thời điểm sự cố.
6. **Restore vào vùng cô lập:** quét malware, kiểm tra checksum, metadata và tính nhất quán.
7. **Đối soát và mở lại dịch vụ:** ưu tiên tập dữ liệu quan trọng, xác minh ứng dụng đọc/ghi đúng.
8. **Khắc phục nguyên nhân:** thu hẹp quyền, sửa automation, thêm cảnh báo và diễn tập lại.

Không khôi phục trực tiếp lên bucket production đang bị compromise trước khi kiểm soát credential và policy, vì dữ liệu vừa phục hồi có thể bị xóa hoặc mã hóa lần nữa.

## 12. Thiết kế encryption và key management

Mã hóa bảo vệ nội dung object nhưng cần quản lý vòng đời khóa cẩn thận. Một object còn tồn tại mà key đã bị xóa hoặc quyền giải mã bị thu hồi có thể trở thành dữ liệu không thể sử dụng.

### Các lựa chọn phổ biến

- **Provider-managed keys:** nhà cung cấp quản lý key material và rotation theo tính năng dịch vụ; giảm việc vận hành khóa nhưng mức kiểm soát trực tiếp thấp hơn.
- **Customer-managed keys (CMK):** tổ chức kiểm soát policy, rotation và audit của khóa thông qua KMS/key vault; cần quản lý availability và quyền dùng khóa.
- **Client-side encryption:** ứng dụng mã hóa trước khi upload; tăng quyền kiểm soát nhưng phải quản lý key distribution, metadata, rotation, recovery và compatibility.

### Điều cần thiết kế

1. Key policy chỉ cho workload/role phù hợp encrypt/decrypt.
2. Rotation không làm mất khả năng đọc các object mã hóa bằng key cũ.
3. Backup và replica có quyền dùng key tương ứng ở destination/region.
4. Xóa key có thời gian chờ, approval và quy trình kiểm tra dependency.
5. Audit truy cập key độc lập với audit object.
6. Restore drill có bước xác minh dữ liệu giải mã được.

### Encryption và immutability là hai lớp khác nhau

Encryption không ngăn người có quyền ghi đè object bằng nội dung khác. Immutability không tự bảo vệ key khỏi bị xóa hoặc thu hồi. Cần cả hai cùng identity, backup và audit. Với client-side encryption, bản backup chỉ có giá trị nếu key và metadata giải mã được bảo vệ độc lập.

## 13. Object Lock và API: những chi tiết cần xác minh

Các dịch vụ object storage có thể cung cấp Object Lock/WORM với mô hình API khác nhau. Một số khái niệm phổ biến:

- Bật khả năng Object Lock ở bucket/container hoặc thời điểm tạo resource.
- Đặt default retention ở cấp bucket/container.
- Đặt retention cho một object version cụ thể.
- Đặt hoặc gỡ legal hold.
- Đọc trạng thái retention/hold trước thao tác xóa.
- Cấu hình replication bảo toàn thuộc tính Object Lock ở destination nếu dịch vụ hỗ trợ.

Một số dịch vụ yêu cầu versioning bật khi dùng Object Lock. Một số cho phép khóa theo governance/compliance; một số có API retention ngày cụ thể. Không sao chép lệnh từ nhà cung cấp này sang nhà cung cấp khác mà chưa kiểm tra semantics.

### Ví dụ policy logic

Một quy trình upload tài liệu có thể:

1. Xác thực danh tính người upload và quyền ghi đúng prefix.
2. Tạo object với key định danh bất biến, checksum và metadata phân loại.
3. Áp default retention hoặc yêu cầu retention theo loại chứng từ.
4. Lưu object version ID và metadata pointer trong database.
5. Ghi audit event cùng operation ID.
6. Xác minh version có retention/hold đúng.

Một quy trình xóa có thể:

1. Kiểm tra role và approval.
2. Xác minh retention/legal hold.
3. Kiểm tra yêu cầu nghiệp vụ và đối chiếu backup.
4. Thực hiện delete theo đúng version/key được phê duyệt.
5. Ghi audit kết quả và kiểm tra phiên bản còn lại.

### Governance bypass và compliance controls

Nếu dùng governance mode, hãy quản lý permission bypass như quyền break-glass. Nó cần vai trò riêng, approval đa bên, thời hạn ngắn, MFA và log gửi sang hệ thống độc lập. Nếu dùng compliance mode, hãy xác minh thời hạn/điều kiện không thể rút ngắn và quy trình trước khi bật, vì một cấu hình sai có thể tạo chi phí lưu giữ hoặc xung đột nghĩa vụ xóa dữ liệu.

## 14. Inventory, checksum và bằng chứng tính toàn vẹn

Versioning và backup cho biết có bản sao, nhưng không nhất thiết chứng minh nội dung không bị hỏng. Cần có inventory và checksum để phát hiện thiếu object, object trùng, thay đổi metadata hoặc nội dung sai.

### Inventory

Inventory định kỳ có thể ghi:

- Bucket/container, key, version ID/generation.
- Kích thước, storage tier, checksum, thời điểm tạo.
- Encryption key/algorithm metadata phù hợp.
- Retention expiration và legal hold state.
- Replication status/destination nếu có.
- Classification tag và owner.

Inventory nên được xuất sang storage có quyền độc lập và retention phù hợp. Nếu chỉ có trong bucket đang bị xóa nhầm, danh sách object cần phục hồi cũng có thể mất.

### Checksum và etag

Checksum như SHA-256 giúp xác minh nội dung object sau upload/replication/restore. Không mặc định ETag luôn là MD5 của toàn bộ object; multipart upload, encryption hoặc dịch vụ cụ thể có thể làm ETag không có semantics đó. Dùng checksum API hoặc metadata checksum được hỗ trợ và lưu thuật toán/giá trị rõ ràng.

### Đối soát sau phục hồi

Một quy trình restore cần so:

- Số lượng object và tổng dung lượng theo prefix/classification.
- Key/version cần thiết đã tồn tại.
- Checksum của nội dung phục hồi so với manifest đáng tin.
- Metadata nghiệp vụ và pointer trong database.
- Khả năng decrypt và đọc ở application.
- Quyền và retention sau restore.

Đừng chỉ dựa vào số object; hai phiên bản có thể cùng số lượng nhưng nội dung khác.

## 15. Thiết kế restore: chọn đúng bản và tránh ghi đè lần hai

Khi có sự cố, phục hồi phải bắt đầu bằng **xác định mốc thời gian đáng tin** và nguồn dữ liệu có thẩm quyền. Không phải version mới nhất luôn là version đúng; cũng không phải version cũ nhất là bản tốt.

### Quy trình restore object đơn lẻ

1. Xác định key, bucket, object version và operation ID bị lỗi.
2. Tìm phiên bản trước sự cố dựa vào audit log, checksum, manifest hoặc bản ghi metadata.
3. Kiểm tra version đó có legal hold, retention và quyền đọc phù hợp.
4. Đọc vào vùng tạm, quét nội dung và xác minh checksum.
5. Khôi phục bằng cách tạo version mới từ bản tốt hoặc cập nhật pointer theo quy trình; không sửa trực tiếp bản bất biến.
6. Xác minh người dùng đọc được version đúng, metadata đồng bộ và audit được lưu.

### Restore số lượng lớn

Với một prefix/bucket lớn, cần manifest của tập object sẽ phục hồi, batch size, giới hạn API, khả năng retry và checkpoint. Chạy dry-run để biết chính xác tác động; restore theo đợt; ghi trạng thái từng object thành công/thất bại; kiểm tra idempotency để chạy lại không tạo bản sao không kiểm soát.

### Restore khi bucket bị xóa hoặc account bị compromise

Nếu bucket nguồn bị xóa, versioning trong bucket đó có thể không đủ để phục hồi; phụ thuộc khả năng khôi phục resource và cách dịch vụ lưu version. Backup ở account khác, immutable vault và IaC để dựng lại bucket policy/DNS/access point có thể quan trọng. Khi account bị compromise, cần kiểm soát identity trước, rồi mới mở quyền restore.

## 16. Xây dựng chính sách dữ liệu theo classification

Không nên bật retention giống nhau cho mọi loại object. Hãy phân loại dữ liệu theo giá trị, mức nhạy cảm, nghĩa vụ pháp lý, khả năng tái tạo và chi phí phục hồi.

| Nhóm dữ liệu | Versioning | Immutability / retention | Soft delete | Backup/replication |
| --- | --- | --- | --- | --- |
| Nội dung người dùng | Thường hữu ích để chống overwrite | Theo yêu cầu hợp đồng/retention | Hữu ích trong cửa sổ phục hồi ngắn | Replication/backup theo mức quan trọng |
| Hóa đơn/chứng từ | Nên cân nhắc giữ version và audit | Có thể cần WORM/legal hold theo quy định | Không thay thế nghĩa vụ giữ | Bản sao độc lập và restore test |
| Log bảo mật | Versioning không phải lúc nào cần cho append-only log | Immutable retention thường đáng cân nhắc | Có thể hỗ trợ chống xóa nhầm | Account/vault độc lập |
| Backup dữ liệu | Giữ bản theo recovery point | Immutable retention theo chính sách backup | Không phải lớp bảo vệ duy nhất | Tách account/region phù hợp RTO/RPO |
| File tạm | Có thể tắt hoặc retention ngắn | Thường không cần WORM | Chỉ giữ ngắn nếu cần | Thường không backup |
| Dataset phân tích | Version hoặc snapshot theo pipeline | Theo khả năng tái tạo và yêu cầu pháp lý | Có thể hữu ích | Snapshot/replication theo chi phí và thời gian rebuild |

Đây là ma trận định hướng, không phải policy mặc định. Một loại dữ liệu có thể chứa trường nhạy cảm khác nhau; classification và retention cần được owner dữ liệu cùng security/legal phê duyệt.

### Data minimization và quyền xóa

Immutability có thể xung đột với yêu cầu xóa dữ liệu cá nhân hoặc nguyên tắc lưu giữ tối thiểu. Cần thiết kế ngay từ đầu:

- Có thật sự cần lưu nội dung gốc hay chỉ cần hash/metadata?
- Có thể tách thông tin định danh khỏi object bất biến?
- Có thể mã hóa từng object bằng data encryption key riêng và hủy key khi hết nghĩa vụ giữ, nếu luật/policy cho phép?
- Khi legal hold xuất hiện, quy trình nào tạm dừng việc xóa?
- Khi retention kết thúc, deletion proof và audit được tạo ra như thế nào?

Không dùng crypto-shredding để né nghĩa vụ pháp lý; khả năng hủy khóa cần được review bởi security/legal và phụ thuộc yêu cầu lưu giữ, khả năng backup/key replication và semantics mã hóa.

## 17. Case study: kho chứng từ và hóa đơn trên cloud

Một nền tảng cho thuê lưu hóa đơn, hợp đồng và biên bản bàn giao dưới dạng PDF. Yêu cầu giả định:

- Mỗi chứng từ có mã định danh và cần truy vết phiên bản.
- Người dùng được phép tải bản mới, nhưng bản đã ký phải được bảo toàn.
- Một số hồ sơ có legal hold.
- Ứng dụng cần đọc bản hiện hành nhanh; đội compliance cần tra cứu phiên bản cũ.
- Production có thể bị compromise; bản backup phải có blast radius riêng.
- Hệ thống cần chứng minh object sau restore đúng với manifest/checksum.

### Thiết kế dữ liệu

Một hướng thiết kế:

1. Bucket nguồn chứa object theo key định danh, không dùng tên file người dùng làm định danh duy nhất.
2. Versioning bật cho nhóm chứng từ cần giữ lịch sử; metadata database lưu document ID, object key, version ID, checksum, owner, classification và trạng thái.
3. Tài liệu đã ký được áp retention/immutability theo chính sách đã phê duyệt; legal hold được điều khiển qua vai trò compliance riêng.
4. Ứng dụng upload chỉ có quyền ghi vào prefix được cấp; không có quyền xóa version hoặc đổi retention.
5. Một pipeline backup copy sang account/vault riêng với policy immutable và key management độc lập.
6. Audit log, inventory và manifest checksum được lưu ở nơi mà ứng dụng production không thể xóa.

~~~mermaid
flowchart TB
    APP["Document API"]
    META["Metadata database"]
    SRC["Source object bucket\nVersioning enabled"]
    LOCK["Retention / Object Lock\nLegal hold"]
    AUDIT["Audit + inventory + checksum"]
    COPY["Backup / replication pipeline"]
    subgraph BACKUP["Backup account / vault"]
        DST["Immutable object copy"]
        KEY["Independent key policy"]
    end
    APP --> SRC
    APP --> META
    SRC --> LOCK
    SRC --> COPY
    COPY --> DST
    DST --> KEY
    SRC --> AUDIT
    DST --> AUDIT
~~~

Sơ đồ mô tả trách nhiệm logic; khả năng replicate Object Lock, version metadata, legal hold và encryption key phụ thuộc dịch vụ. Nếu replication không bảo toàn thuộc tính cần thiết, pipeline phải áp policy tại destination và xác minh sau copy.

### Luồng upload bản mới

1. Client xác thực và gửi document ID, loại chứng từ, checksum và file.
2. API kiểm tra quyền ghi theo document owner và trạng thái legal hold.
3. Object được upload bằng key phù hợp; version ID/generation được lấy từ storage response.
4. Metadata database được cập nhật bằng transaction/version control để trỏ tới object version mới.
5. Audit ghi actor, operation ID, checksum, version và policy.
6. Pipeline backup nhận thay đổi và xác nhận destination có bản copy cùng thuộc tính bảo vệ.

Không nên cập nhật metadata pointer trước khi object đã được upload và xác minh thành công. Nếu database ghi thành công nhưng upload lỗi, pointer có thể trỏ tới object không tồn tại. Nếu object upload thành công nhưng metadata commit lỗi, cần tác vụ reconcile để tìm object mồ côi theo operation ID.

### Luồng thay thế bản hóa đơn sai

Nếu upload nhầm bản mới:

- Không xóa object/version cũ để "dọn sạch".
- Xác định version hợp lệ bằng chứng từ ký, checksum và audit.
- Tạo version hiện hành mới từ bản đúng hoặc cập nhật pointer theo quy trình có kiểm soát.
- Giữ bản sai nếu legal/compliance yêu cầu bảo toàn chứng cứ.
- Ghi audit về việc sửa và liên kết phiên bản.

### Luồng legal hold

Khi có yêu cầu tranh chấp, compliance xác định danh sách document/version, tạo legal hold bằng role được phê duyệt và ghi mã vụ việc, actor, thời điểm, lý do. Lifecycle được kiểm tra không xóa các version đang hold. Khi có phê duyệt gỡ hold, hệ thống ghi audit và xác minh retention thông thường vẫn được tuân thủ.

### Luồng phục hồi sau compromise

1. Thu hồi credential ứng dụng production bị xâm phạm.
2. Giữ audit và inventory ở account độc lập.
3. Tạm dừng pipeline nếu nó đang replicate nội dung độc hại hoặc thao tác xóa.
4. Chọn thời điểm backup trước sự cố.
5. Restore object vào bucket sạch, quét malware và đối chiếu checksum/manifest.
6. Khôi phục metadata pointer, kiểm tra version, retention, legal hold và key.
7. Mở lại quyền đọc/ghi sau khi security xác nhận.

## 18. Đánh đổi chi phí và khả năng vận hành

Versioning, immutability, replication và backup làm tăng khả năng phục hồi nhưng cũng làm tăng dung lượng, số request, phí retrieval, quản trị key và thời gian restore. Cần tính **tổng chi phí vòng đời dữ liệu**, không chỉ giá lưu một GB.

| Thành phần chi phí | Nguyên nhân | Cách kiểm soát |
| --- | --- | --- |
| Current object storage | Dung lượng object hiện tại | Compression phù hợp, lifecycle tier, xóa file tạm |
| Noncurrent versions | Overwrite và version retention | Noncurrent lifecycle sau khi hết retention/hold |
| Delete markers/metadata | Nhiều thao tác xóa và lịch sử object | Inventory, quy trình marker cleanup đã kiểm chứng |
| Immutable retention | Dữ liệu bắt buộc giữ dù không còn truy cập | Phân loại đúng, thời hạn phê duyệt, capacity forecast |
| Replication | Bản sao vùng/account khác | Chọn tập dữ liệu cần replicate, đo bytes và lag |
| Backup | Bản full/incremental, log/PITR, catalog | Retention theo RPO/RTO, dedupe nếu hỗ trợ |
| Retrieval/archive | Đọc dữ liệu ở tier lạnh | Thử restore, tính phí retrieval và thời gian |
| KMS/key operations | Encrypt/decrypt, audit, rotation | Thiết kế key scope và request pattern phù hợp |
| Inventory/audit | Object listing, event và log | Chọn tần suất, retention, partition và quyền |
| Restore operations | Copy dữ liệu trở lại, compute và egress | Diễn tập, tối ưu batch và ưu tiên dữ liệu |

### Ví dụ tăng dung lượng do versioning

Giả sử 2 triệu object, trung bình 4 MiB/object, mỗi object được ghi đè trung bình 3 lần/tháng và giữ noncurrent version 6 tháng. Nếu mỗi lần ghi tạo một bản đầy đủ mới, không có dedupe/compression:

- Dung lượng một bộ current xấp xỉ \(2.000.000\times4\text{ MiB}=8.000.000\text{ MiB}\), khoảng 7,63 TiB.
- Sáu tháng có thể tạo khoảng 36 triệu noncurrent versions nếu giả định 3 overwrite/object/tháng.
- Nếu mỗi version có cùng kích thước 4 MiB, noncurrent data có thể khoảng 137 TiB trước compression, lifecycle hoặc loại trừ version trùng thực tế.

Đây là kịch bản giả định để thấy versioning có thể tăng dung lượng rất lớn; thực tế có thể thay đổi theo tỉ lệ overwrite, kích thước phiên bản, storage implementation, multipart và policy. Cần dùng inventory/billing để đo trước khi đặt retention rộng.

### Cost control không được phá retention

Không rút ngắn retention hoặc tắt Object Lock chỉ để giảm hóa đơn khi dữ liệu còn nghĩa vụ bảo toàn. Nên tối ưu key design, tránh overwrite không cần thiết, chuyển tier khi phù hợp, dọn dữ liệu tạm không được bảo vệ và đặt lifecycle đúng sau khi hết retention/legal hold.

## 19. Kiểm thử versioning, immutability và phục hồi

Một policy chỉ đáng tin khi đã thử trên môi trường an toàn và có bằng chứng.

| Bài thử | Mô phỏng | Kỳ vọng |
| --- | --- | --- |
| Overwrite object | PUT nội dung mới cùng key | Version cũ còn đọc được theo policy |
| Delete object | Người dùng xóa key | Delete marker/soft delete đúng semantics |
| Delete version | Thử xóa một version chưa hết retention | Bị ngăn theo policy nếu version được bảo vệ |
| Governance bypass | Role thường thử bypass | Bị từ chối; role break-glass có audit |
| Compliance retention | Admin thường thử rút ngắn/xóa | Không thể vi phạm retention theo semantics |
| Legal hold | Đặt hold rồi chạy lifecycle | Object không bị xóa khi hold còn hiệu lực |
| Lifecycle | Dry-run trên prefix thử nghiệm | Chỉ phiên bản đủ điều kiện bị chuyển/xóa |
| Replication delete | Xóa object nguồn | Destination xử lý delete marker đúng cấu hình |
| Credential compromise | Dùng role production thử xóa backup | Destination/immutable vault từ chối |
| Key rotation | Xoay khóa mã hóa | Object cũ và mới vẫn giải mã được |
| Restore | Khôi phục tập object từ backup | Checksum, metadata và ứng dụng xác minh thành công |
| Bulk restore | Phục hồi prefix lớn | Retry idempotent, checkpoint, đúng số lượng |

### Test quyền từ nhiều danh tính

Không chỉ test bằng admin. Tạo các danh tính tương ứng:

- Application upload/read.
- Lifecycle automation.
- Backup writer.
- Backup restore operator.
- Security auditor.
- Compliance/legal hold operator.
- Break-glass administrator.

Kiểm thử positive và negative permission: danh tính nào đọc/ghi được, danh tính nào không thể xóa version, thay retention, gỡ hold hoặc xóa bucket. Điều này giúp phát hiện quyền thừa trước khi có sự cố.

### Test restore theo RTO

Chọn một tập object đại diện (kể cả object lớn, nhiều version, encrypted, legal hold và metadata phụ thuộc). Đo:

- Thời gian tìm manifest và xác định đúng phiên bản.
- Thời gian provision/chuẩn bị destination.
- Throughput copy/restore và throttling.
- Thời gian decrypt, scan và checksum.
- Thời gian cập nhật metadata/application pointer.
- Thời gian xác minh người dùng đọc được dữ liệu.

Một restore hoàn tất copy nhưng ứng dụng không hiểu metadata/version hoặc key không giải mã được vẫn là restore thất bại.

## 20. Những sai lầm thường gặp

1. **Bật versioning rồi cho rằng dữ liệu không thể mất:** quyền xóa version, xóa bucket và lifecycle vẫn có thể phá khả năng phục hồi.
2. **Coi replication là backup:** thao tác xóa, overwrite hoặc nội dung mã hóa độc hại có thể được sao chép sang destination.
3. **Dùng Object Lock mà không phân loại dữ liệu:** file tạm hoặc dữ liệu sai bị khóa lâu, làm tăng chi phí và gây khó xử lý quyền xóa.
4. **Chọn governance mode nhưng cấp quyền bypass rộng:** admin hoặc workload role có thể vượt qua lớp bảo vệ.
5. **Bật compliance retention trước khi thử:** thời hạn sai có thể không rút ngắn được theo semantics dịch vụ.
6. **Không phân biệt object key và version ID:** restore hoặc xóa nhầm phiên bản.
7. **Coi delete marker là dữ liệu đã xóa vật lý:** object version cũ vẫn còn hoặc marker vẫn che object.
8. **Dùng lifecycle rule áp cho toàn bucket:** xóa nhầm chứng từ hoặc backup chưa hết nghĩa vụ giữ.
9. **Không kiểm tra soft delete với versioning:** giả định thứ tự phục hồi sai theo dịch vụ.
10. **Backup cùng account và cùng quyền admin:** compromise production có thể xóa cả backup.
11. **Không bảo vệ encryption key:** object vẫn còn nhưng không giải mã được.
12. **Dựa vào ETag như checksum phổ quát:** multipart hoặc encryption có thể làm ETag không đại diện MD5 toàn object.
13. **Không lưu inventory/manifest độc lập:** sau khi mất bucket không biết chính xác phải phục hồi gì.
14. **Chỉ kiểm tra số lượng object sau restore:** nội dung hoặc metadata có thể sai dù count giống nhau.
15. **Không test negative permissions:** người dùng thường có thể xóa version hoặc đổi retention ngoài ý muốn.
16. **Không tính noncurrent version và retrieval trong TCO:** hóa đơn thực tế vượt dự toán.
17. **Restore trực tiếp về production đang bị compromise:** dữ liệu mới phục hồi có thể bị phá hủy lần nữa.
18. **Không có owner cho legal hold:** dữ liệu bị giữ hoặc gỡ hold sai mà không ai chịu trách nhiệm.

## 21. Bài tập thực hành và đáp án định hướng

Một công ty lưu tài liệu hợp đồng và ảnh người dùng trong object storage:

- 800.000 hợp đồng PDF, một số được ký số và phải bảo toàn theo chính sách pháp lý.
- 5 triệu ảnh người dùng có thể thay thế; ứng dụng thường cập nhật ảnh cùng một key.
- Production upload role hiện có quyền PUT, GET và DELETE trên toàn bucket.
- Cross-region replication được bật, bao gồm cả delete marker.
- Backup job chạy hàng đêm nhưng cùng account với production.
- Đội vận hành chưa từng restore hàng loạt và chưa có inventory độc lập.

### Câu 1 — Những rủi ro ưu tiên cần xử lý là gì?

**Đáp án định hướng:** Upload role có quyền xóa toàn bucket; backup cùng account; delete marker được replicate; chưa có inventory và restore test. Hợp đồng ký số cần classification/retention/legal hold riêng. Ảnh người dùng có thể có retention khác và cần kiểm soát quyền xóa theo yêu cầu dữ liệu cá nhân.

### Câu 2 — Có nên bật Object Lock compliance cho toàn bucket không?

**Đáp án:** Không nên áp dụng hàng loạt khi dữ liệu có nghĩa vụ lưu khác nhau. Phân bucket hoặc prefix/policy theo classification, xác nhận retention với pháp chế và thử nghiệm semantics trước. Hợp đồng đã ký có thể cần WORM; ảnh thay đổi thường xuyên có thể cần versioning/soft delete ngắn hạn hoặc policy xóa theo yêu cầu.

### Câu 3 — Nên thay đổi quyền upload thế nào?

**Đáp án định hướng:** Chỉ cho PUT vào prefix của tenant hoặc đường dẫn được cấp; quyền GET chỉ theo nhu cầu; bỏ quyền delete version, đổi retention, gỡ hold, sửa lifecycle/replication và xóa bucket. Dùng role riêng cho lifecycle, backup writer, restore và compliance. Ghi audit độc lập.

### Câu 4 — Replication hiện tại có đủ chống xóa nhầm không?

**Đáp án:** Không. Vì delete marker được replicate, thao tác xóa nguồn có thể che object ở destination. Cần xem xét cấu hình replication, tách account và quyền đích, immutable retention/backup độc lập; vẫn phải kiểm thử hành vi thực tế của dịch vụ.

### Câu 5 — Thiết kế backup cho hợp đồng như thế nào?

**Đáp án định hướng:** Dùng destination account/vault riêng, quyền write-only từ production ở mức cần thiết, immutable retention theo policy, encryption key tách biệt và inventory/manifest độc lập. Chỉ cho restore operator đọc và phục hồi có approval; không cấp quyền xóa backup cho ứng dụng.

### Câu 6 — Nếu một hợp đồng đang legal hold nhưng lifecycle rule muốn xóa noncurrent version thì sao?

**Đáp án:** Hold phải được bảo toàn theo semantics dịch vụ. Kiểm tra policy enforcement và log; lifecycle không được làm mất version đang hold. Cần kiểm thử negative permission và cảnh báo nếu hold bị gỡ hoặc retention thay đổi.

### Câu 7 — Phục hồi 100.000 ảnh đã bị overwrite nhầm cần chuẩn bị gì?

**Đáp án định hướng:** Inventory/version listing, mốc sự cố, manifest key/version đúng, checksum, batch và checkpoint, giới hạn API, retry idempotent và destination tạm. Restore theo dry-run/canary; kiểm tra object count, content checksum, metadata và application pointer trước khi mở lại.

### Câu 8 — Vì sao không thể chỉ so sánh ETag để xác minh mọi object?

**Đáp án:** ETag không nhất thiết là MD5 của toàn bộ object trong multipart upload, encryption hoặc một số implementation. Dùng checksum API/metadata checksum có thuật toán được xác định rõ, đồng thời xác minh sau upload, replication và restore.

## 22. Checklist review kiến trúc object storage

- Dữ liệu đã phân loại theo owner, độ nhạy, khả năng tái tạo và nghĩa vụ lưu giữ chưa?
- Versioning có bật đúng bucket/prefix và semantics delete marker đã kiểm chứng chưa?
- Version ID/generation có được lưu cùng metadata nghiệp vụ không?
- Object nào cần immutability/WORM; retention mode và thời hạn đã được phê duyệt chưa?
- Legal hold có owner, audit, quy trình tạo/gỡ và kiểm tra lifecycle không?
- Soft delete window, versioning và lifecycle phối hợp đúng không?
- Delete version, bypass retention, tắt versioning và xóa bucket có được hạn chế?
- Replication có sao chép delete marker/metadata/retention theo đúng yêu cầu không?
- Destination có khác account/role và có immutable backup độc lập không?
- Backup có checksum, manifest, catalog, key access và restore test không?
- Encryption key có policy, rotation, recovery và quyền tách biệt không?
- Inventory/audit có lưu độc lập với production account không?
- Lifecycle được preview, canary, review và theo dõi sau rollout chưa?
- TCO đã tính current/noncurrent versions, retrieval, replication, backup, audit và restore chưa?
- Có runbook chống ransomware, xóa nhầm, restore đơn lẻ và restore hàng loạt không?
- RTO/RPO cho phục hồi object và tập dữ liệu đã được đo chưa?

## 23. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi | Bằng chứng |
| --- | --- | --- |
| **Độ tin cậy** | Có thể phục hồi overwrite, delete, bucket loss và compromise trong RTO/RPO không? | Versioning, immutable backup, inventory, restore drill |
| **Bảo mật** | Ai có thể đọc, ghi, xóa version, bypass retention, gỡ hold hoặc xóa key? | IAM, key policy, audit, separation of duties |
| **Hiệu năng** | Version listing, retrieval, restore và replication có đáp ứng tải không? | Latency, throughput, API quota, restore benchmark |
| **Tối ưu chi phí** | Có giữ version quá lâu, replica trùng hoặc archive sai dữ liệu không? | Inventory, lifecycle forecast, cost per object/GB |
| **Vận hành xuất sắc** | Có dry-run, approval, runbook, cảnh báo và owner cho retention/legal hold không? | IaC, policy-as-code, alert, audit và diễn tập |
| **Tính bền vững** | Dữ liệu có được giữ đúng thời hạn và xóa an toàn khi hết mục đích không? | Classification, retention, lifecycle, deletion evidence |

Thiết kế tốt cần cân bằng ba mục tiêu: **phục hồi được khi có lỗi, bảo toàn đúng dữ liệu cần giữ và không lưu vô hạn dữ liệu không còn mục đích**. Versioning giúp quay lại phiên bản cũ; immutability và retention ngăn phá hủy trong thời gian yêu cầu; backup độc lập và restore test chứng minh tổ chức có thể phục hồi. Các lớp này chỉ hiệu quả khi được gắn với quyền truy cập, encryption, audit và trách nhiệm vận hành rõ ràng.
