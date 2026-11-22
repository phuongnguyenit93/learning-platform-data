# Phân tầng dữ liệu, vòng đời và chính sách lưu giữ

## 1. Vì sao dữ liệu cần nhiều tầng lưu trữ?

Không phải dữ liệu nào cũng có cùng tần suất truy cập, độ trễ chấp nhận được, thời gian tồn tại hay yêu cầu khôi phục. Một ảnh đại diện có thể được đọc liên tục; bản ghi giao dịch cần truy vấn nhanh trong thời gian gần; log vận hành có thể được truy cập nhiều trong vài ngày đầu rồi hiếm khi cần; hồ sơ đã kết thúc có thể phải lưu nhiều năm để phục vụ đối soát hoặc nghĩa vụ pháp lý.

Nếu lưu tất cả dữ liệu trên tầng có độ trễ thấp và chi phí cao, hóa đơn tăng theo dung lượng và thời gian. Nếu chuyển dữ liệu sang tầng rẻ nhất quá sớm, ứng dụng có thể phải chờ hàng giờ để khôi phục một đối tượng, trả phí truy xuất cao hoặc không đáp ứng thời gian phục vụ. Nếu xóa theo tuổi dữ liệu mà không kiểm tra retention, legal hold hay backup, hệ thống có thể mất dữ liệu cần thiết.

**Phân tầng dữ liệu (data tiering)** là sắp xếp dữ liệu vào các loại lưu trữ theo đặc tính truy cập, hiệu năng, độ bền, khả năng sẵn sàng và chi phí. **Vòng đời dữ liệu (data lifecycle)** mô tả dữ liệu được tạo, sử dụng, chuyển tầng, lưu giữ, lưu trữ dài hạn và cuối cùng được xóa như thế nào. **Chính sách lưu giữ (retention policy)** quy định dữ liệu hoặc bản ghi phải được giữ trong bao lâu, tính từ mốc nào, ngoại lệ nào được áp dụng và cách chứng minh việc xóa đã diễn ra.

Ba quyết định liên quan nhưng không đồng nhất:

- Tiering trả lời: **đặt dữ liệu ở đâu** để đáp ứng mẫu truy cập và chi phí?
- Lifecycle trả lời: **dữ liệu thay đổi trạng thái thế nào theo thời gian**?
- Retention trả lời: **dữ liệu phải được giữ trong bao lâu và khi nào được xóa**?

Trong module **CLOUD_ARCHITECTURE**, đây là quyết định cân bằng hiệu năng, khả năng mở rộng, độ tin cậy, bảo mật, chi phí và vận hành. Phải dựa trên dữ liệu và yêu cầu thật của sản phẩm, không chỉ dựa trên tên các storage class.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân loại dữ liệu theo access pattern, độ trễ, kích thước, tuổi và mức độ quan trọng.
2. Chọn hot, warm, cool, cold hoặc archive tier dựa trên tổng chi phí và khả năng truy xuất.
3. Thiết kế lifecycle transition và expiration để dữ liệu chuyển tầng/xóa theo quy tắc xác định.
4. Phân biệt retention, backup, replica, archive và legal hold.
5. Áp dụng chính sách lưu giữ cho object, log, database export và dữ liệu giao dịch.
6. Đánh giá encryption, IAM, audit, versioning, deletion và khôi phục.
7. Xây dựng quy trình kiểm chứng, theo dõi và điều chỉnh chính sách lưu trữ.

## 2. Phân loại dữ liệu trước khi chọn storage tier

Không nên bắt đầu bằng câu hỏi “dịch vụ cloud nào rẻ nhất?”. Trước tiên cần hiểu dữ liệu được tạo ra để làm gì và ai cần truy cập.

### 2.1. Các chiều phân loại quan trọng

| Chiều | Câu hỏi | Ví dụ |
|---|---|---|
| **Access frequency** | Bao lâu có một lần đọc/ghi? | Ảnh listing đọc hàng nghìn lần; log cũ hiếm khi tra cứu |
| **Access latency** | Người dùng chờ bao lâu được? | API cần vài mili giây; archive có thể mất hàng giờ để phục hồi |
| **Data size** | Object nhỏ, file lớn hay nhiều record nhỏ? | JSON vài KB, ảnh vài MB, video vài GB |
| **Change rate** | Dữ liệu có thường xuyên cập nhật không? | Session thay đổi liên tục; hóa đơn đã phát hành ít thay đổi |
| **Retention** | Phải giữ bao lâu? | Cache vài phút; hồ sơ kế toán nhiều năm theo policy |
| **Durability / availability** | Mức mất dữ liệu và downtime chấp nhận được? | Metadata booking cần bảo vệ cao hơn cache có thể tái tạo |
| **Recoverability** | Cần khôi phục nhanh đến mức nào? | DB giao dịch có RTO thấp; archive có thời gian restore dài hơn |
| **Sensitivity** | Dữ liệu chứa PII, thanh toán hoặc bí mật không? | Hộ chiếu, địa chỉ, log có token |
| **Residency / sovereignty** | Dữ liệu được phép lưu ở đâu? | Region hoặc jurisdiction được chỉ định |
| **Deletion** | Khi hết mục đích sử dụng, xóa bằng cách nào? | Xóa object, index, replica, derived copy và backup theo vòng đời |

### 2.2. Phân nhóm theo nhu cầu truy cập

| Nhóm dữ liệu | Đặc tính thường gặp | Hướng lưu trữ |
|---|---|---|
| **Operational / hot** | Đọc ghi thường xuyên, cần latency thấp | Database chính, block storage hiệu năng cao hoặc object tier nóng |
| **Warm** | Truy cập định kỳ, vẫn cần online nhanh | Database/read replica, object tier tiêu chuẩn hoặc infrequent-access |
| **Cool** | Ít truy cập, chấp nhận retrieval fee/latency nhỏ | Object storage cool/nearline class |
| **Cold / archive** | Hiếm khi truy cập, phục vụ audit/khôi phục theo yêu cầu | Archive tier với quy trình restore |
| **Ephemeral** | Dữ liệu tạm, có thể tái tạo hoặc hết hạn nhanh | Cache, temporary volume, lifecycle expiration |

Các thuật ngữ hot/warm/cool/cold là mô hình khái niệm. Tên tier, minimum storage duration, retrieval latency, retrieval fee và khả năng chuyển đổi thay đổi theo nhà cung cấp và từng lớp lưu trữ. Cần kiểm tra bảng giá và tài liệu dịch vụ trước khi chọn.

## 3. Mô hình các tầng và đánh đổi

### 3.1. Mô hình minh họa

~~~mermaid
flowchart TD
    Create["Dữ liệu mới được tạo"] --> Hot["HOT: truy cập thường xuyên"]
    Hot -->|Ít truy cập theo ngưỡng| Warm["WARM: truy cập định kỳ"]
    Warm -->|Không còn cần latency thấp| Cool["COOL: ít truy cập"]
    Cool -->|Chỉ cần lưu dài hạn| Archive["COLD / ARCHIVE"]
    Hot -->|Hết hạn và không bị giữ| Delete["Xóa theo policy"]
    Warm -->|Hết hạn và không bị giữ| Delete
    Cool -->|Hết hạn và không bị giữ| Delete
    Archive -->|Hết thời hạn giữ| Delete
    Hold["Legal hold / retention lock"] -. "ngăn xóa theo policy thường" .-> Delete
~~~

*Sơ đồ khái niệm. Transition không nhất thiết chỉ đi một chiều; dữ liệu có thể được restore hoặc rehydrate lên tier online. Legal hold/retention lock phải được kiểm tra theo semantics cụ thể của dịch vụ.*

### 3.2. So sánh các tầng

| Tầng | Tần suất truy cập điển hình | Ưu điểm | Đánh đổi |
|---|---|---|---|
| **Hot** | Hàng ngày hoặc liên tục | Latency thấp, truy xuất trực tiếp | Giá lưu trữ/compute thường cao hơn |
| **Warm** | Định kỳ, theo mùa hoặc theo yêu cầu hỗ trợ | Giảm chi phí so với hot | Retrieval/operation cost có thể cao hơn, SLA khác |
| **Cool** | Hiếm khi truy cập nhưng cần lấy lại online | Chi phí lưu trữ thấp hơn | Phí truy xuất, độ trễ, minimum duration hoặc minimum billable size tùy dịch vụ |
| **Cold** | Rất hiếm khi truy cập, thường phục vụ audit/khôi phục | Chi phí lưu giữ thấp cho dữ liệu lâu năm | Phải lên kế hoạch restore, có thể mất nhiều giờ |
| **Archive / Deep archive** | Gần như không truy cập trong hoạt động thường ngày | Tối ưu lưu giữ dài hạn | Restore chậm, có thể có phí lấy dữ liệu và minimum retention |

Không phải mọi đối tượng đều cần đi qua từng tầng. Ví dụ một log có thể hết hạn sau 30 ngày, không cần archive; một hồ sơ cần lưu 7 năm có thể chuyển từ hot sang cool rồi archive. Dữ liệu cần truy xuất ngay trong audit có thể không phù hợp tầng restore nhiều giờ.

## 4. Chọn loại lưu trữ: object, block, file và database

Phân tầng không chỉ là chuyển object giữa các storage class. Hình dạng và cách ứng dụng sử dụng dữ liệu cũng quyết định công nghệ lưu trữ.

| Loại | Đơn vị truy cập | Phù hợp với | Lưu ý vòng đời |
|---|---|---|---|
| **Object storage** | Object/blob kèm metadata/key | Ảnh, video, tài liệu, log, backup, data lake | Lifecycle theo prefix/tag/age, versioning, storage class |
| **Block storage** | Block device gắn với VM/workload | Disk cho database, filesystem, boot volume | Snapshot, volume tier, resize, backup và xóa volume |
| **File storage** | File/directory qua giao thức chia sẻ | Shared application files, home directory, content workflow | Snapshot, quota, retention file, quyền thư mục |
| **Relational database** | Row/transaction/query | Booking, payment ledger, metadata cần ACID | Partition, index, archive table, backup/PITR và retention record |
| **NoSQL / key-value** | Item/document/key hoặc partition | Session, lookup, workload scale lớn | TTL, partition design, backup và export |
| **Cache** | Entry tạm theo key | Session/cache có thể tái tạo, giảm read load | TTL và eviction; không là nguồn sự thật mặc định |
| **Stream / event log** | Record theo partition/offset | Event và telemetry có replay trong retention window | Retention theo thời gian/size, consumer lag và export dài hạn |

Object storage thường hỗ trợ nhiều storage class và lifecycle policy. Database nóng thường cần thiết kế khác: partitioning theo thời gian, archive table, export sang object storage hoặc data warehouse. Không nên cố chuyển một row trong database sang cold tier mà không xét query, index, foreign key và tính nhất quán của ứng dụng.

## 5. Tổng chi phí lưu trữ: giá mỗi GB chưa đủ

Một storage tier rẻ hơn trên bảng giá có thể tạo tổng chi phí cao nếu dữ liệu thường xuyên bị truy xuất, restore hoặc chuyển tầng.

### 5.1. Các thành phần chi phí

- **Storage capacity:** GB-tháng, có thể khác theo region, class, redundancy và mức sử dụng.
- **Request/operation:** PUT, GET, LIST, lifecycle transition, retrieval request, metadata operation.
- **Retrieval:** phí đọc hoặc phục hồi dữ liệu từ cool/archive tier.
- **Early deletion / minimum duration:** một số class có thời gian lưu tối thiểu được tính phí ngay cả khi xóa sớm.
- **Data transfer:** egress, cross-zone/cross-region, replication và transfer giữa dịch vụ.
- **Restore/rehydration:** tạo bản online tạm thời, thời gian giữ bản restored và công việc vận hành.
- **Monitoring/indexing:** log, inventory, metadata index, catalog và observability.
- **Operational cost:** thiết kế policy, xử lý restore, legal hold, audit và sự cố.

### 5.2. Công thức ước tính đơn giản

\[
Cost_{total} =
Cost_{storage} + Cost_{requests} + Cost_{retrieval}
+ Cost_{transfer} + Cost_{restore} + Cost_{operations}
\]

Ví dụ giả định để so sánh hai tier, không phải báo giá của nhà cung cấp:

| Thành phần trong một tháng | Tier A (online) | Tier B (cool) |
|---|---:|---:|
| Dung lượng 10 TB | 230 đơn vị | 100 đơn vị |
| Request/operation | 10 | 15 |
| Retrieval | 0 | 60 |
| Transfer/khác | 10 | 10 |
| **Tổng minh họa** | **250** | **185** |

Trong ví dụ, Tier B rẻ hơn khi mức truy xuất giả định còn thấp. Nếu retrieval tăng thêm 100 đơn vị, tổng Tier B thành 285 và Tier A có thể rẻ hơn. Vì vậy quyết định cần dựa trên **access pattern đo được**, không chỉ giá lưu trữ.

### 5.3. Ước lượng hòa vốn

Với dung lượng ổn định, có thể tìm mức truy xuất mà tại đó:

\[
StorageSavings \approx RetrievalFees + ExtraOperations + Transfer
\]

Đây là điểm hòa vốn đơn giản. Thực tế cần thêm phân phối kích thước object, số lần đọc, tier minimum duration, restore concurrency và chi phí nhân lực. Nên chạy mô hình theo tháng/quý với nhiều kịch bản truy xuất.

## 6. Thiết kế lifecycle policy

Lifecycle policy tự động áp dụng hành động theo tuổi dữ liệu, prefix, tag, version hoặc điều kiện khác mà dịch vụ hỗ trợ. Mục tiêu là giảm thao tác thủ công và bảo đảm dữ liệu tuân theo quy tắc nhất quán.

### 6.1. Các hành động lifecycle thường gặp

| Hành động | Mục đích | Câu hỏi cần trả lời |
|---|---|---|
| **Transition** | Chuyển object sang storage class khác | Sau bao lâu, có minimum duration/phí transition không? |
| **Expiration** | Xóa object sau thời hạn | Tính tuổi từ lúc tạo hay mốc nghiệp vụ nào? |
| **Noncurrent version expiration** | Xóa phiên bản cũ | Có cần giữ lịch sử/khả năng phục hồi không? |
| **Abort incomplete multipart upload** | Dọn upload dở dang | Bao lâu thì upload được coi là bỏ dở? |
| **Delete marker cleanup** | Dọn marker trong versioned bucket khi phù hợp | Có ảnh hưởng khả năng khôi phục version không? |
| **Archive restore expiry** | Bỏ bản copy online sau thời gian restore | Dữ liệu archive gốc có còn nguyên? |

### 6.2. Mẫu lifecycle minh họa

~~~text
Prefix: reports/monthly/

0-30 ngày: Standard / hot
Sau 30 ngày: Cool / infrequent access
Sau 180 ngày: Archive
Sau 7 năm: Expire, nếu không có legal hold

Incomplete multipart uploads: abort sau 7 ngày
Noncurrent versions: giữ theo retention riêng đã phê duyệt
~~~

Đây là **mẫu chính sách giả định**, không phải thời hạn pháp lý phổ quát. Mốc 7 năm phải xuất phát từ quy định, hợp đồng và policy nội bộ áp dụng cho loại hồ sơ cụ thể; có thể ngắn hoặc dài hơn.

### 6.3. Ví dụ cấu hình lifecycle dạng YAML

~~~yaml
policy:
  name: monthly-report-lifecycle
  scope:
    bucket: reports-prod
    prefix: reports/monthly/
  transitions:
    - after_days: 30
      storage_class: COOL
    - after_days: 180
      storage_class: ARCHIVE
  expiration:
    after_days: 2555
    condition:
      legal_hold: false
  incomplete_uploads:
    abort_after_days: 7
~~~

Schema trên là pseudoconfiguration để mô tả ý định. Mỗi cloud provider có cú pháp và semantics riêng; không thể áp dụng YAML này trực tiếp vào bucket mà không chuyển đổi và xác minh.

### 6.4. Tránh lỗi tính tuổi

Một object có thể có thời điểm tạo, sửa đổi, hoàn tất giao dịch, đóng hồ sơ và ngày bắt đầu thời hạn lưu khác nhau. **Retention thường phải tính theo mốc nghiệp vụ được phê duyệt**, không mặc định tính từ LastModified.

Ví dụ, bản ghi thanh toán cần lưu 7 năm từ ngày kết thúc kỳ kế toán. Nếu object được export lại mỗi ngày, lifecycle theo LastModified có thể làm thời hạn lưu kéo dài vô hạn hoặc sai mốc. Nên lưu metadata như retention-start-date, record-type và legal-hold theo cách không cho workload tùy ý sửa.

## 7. Retention policy: thời hạn, mục đích và ngoại lệ

Retention policy không chỉ ghi “giữ 5 năm”. Một policy có thể cần xác định:

1. **Data owner:** ai chịu trách nhiệm phân loại và phê duyệt thời hạn.
2. **Data category:** loại hồ sơ, log, ảnh, sự kiện hay dữ liệu cá nhân.
3. **Purpose:** vì sao cần giữ dữ liệu (vận hành, hợp đồng, kiểm toán, pháp lý).
4. **Start event:** mốc bắt đầu tính thời hạn (tạo, kết thúc hợp đồng, đóng case, phát hành chứng từ).
5. **Retention period:** thời lượng và cách tính chính xác.
6. **Disposition:** xóa, ẩn danh, tổng hợp hoặc chuyển archive khi hết hạn.
7. **Exception:** legal hold, điều tra, tranh chấp hoặc lệnh bảo toàn.
8. **Evidence:** log và báo cáo chứng minh policy đã được áp dụng.

### 7.1. Ma trận retention minh họa

| Loại dữ liệu | Mục đích | Mốc tính | Policy minh họa |
|---|---|---|---|
| Cache listing | Tăng tốc đọc | Từ lúc ghi cache | TTL phút/giờ, tái tạo được |
| Temporary upload | Tiếp tục upload hoặc xử lý | Từ khi tạo | Xóa sau vài ngày nếu chưa hoàn tất |
| Application debug log | Điều tra lỗi ngắn hạn | Từ thời điểm ghi | Hot ngắn hạn, sau đó expire hoặc lưu theo sự kiện |
| Security audit log | Điều tra và kiểm toán | Theo policy audit được duyệt | Lưu online/cool hoặc archive trong thời hạn phù hợp |
| Booking record | Thực hiện dịch vụ và xử lý tranh chấp | Từ mốc nghiệp vụ được định nghĩa | Online trong vòng đời hoạt động, archive sau khi đóng nếu phù hợp |
| Invoice/payment evidence | Kế toán, đối soát, nghĩa vụ pháp lý | Theo loại hồ sơ/quy định áp dụng | Retention riêng, kiểm soát sửa/xóa |
| Marketing analytics | Đo hiệu quả hoặc phân tích tổng hợp | Theo mục đích và sự đồng ý/chính sách | Giới hạn thời hạn, ẩn danh/tổng hợp khi phù hợp |

Các thời hạn trong ví dụ cần được pháp chế, privacy/data owner và bộ phận nghiệp vụ xác nhận. Không suy ra nghĩa vụ pháp lý cụ thể chỉ từ bảng mẫu.

## 8. Legal hold, retention lock và immutable storage

### 8.1. Legal hold

**Legal hold** là trạng thái tạm dừng việc xóa hoặc thay đổi một tập dữ liệu do yêu cầu điều tra, tranh chấp, kiểm toán hoặc nghĩa vụ bảo toàn. Legal hold có thể áp dụng theo hồ sơ, đối tượng, chủ thể hoặc khoảng thời gian.

Một hệ thống cần:

- Người có thẩm quyền đặt và gỡ hold.
- Lý do, phạm vi, thời điểm, người yêu cầu và approval trail.
- Cách tìm các bản copy, export, replica, version và dữ liệu liên quan.
- Cơ chế ngăn lifecycle expiration/deletion trong phạm vi hold.
- Quy trình rà soát định kỳ và giải phóng hold khi hết hiệu lực.

Không để service account thông thường tự gắn/gỡ legal hold chỉ bằng metadata do ứng dụng gửi.

### 8.2. Retention lock / object lock

Một số object storage hỗ trợ cơ chế bảo vệ object khỏi xóa/sửa trong một khoảng thời gian, có thể ở chế độ governance hoặc compliance tùy nhà cung cấp. **Semantics không giống nhau**: quyền bypass, khả năng gia hạn, version scope và cấu hình bucket có thể khác nhau.

Immutable/WORM storage hữu ích cho hồ sơ cần bảo toàn, nhưng cấu hình sai có thể giữ dữ liệu lâu hơn mức cho phép hoặc làm khó xử lý yêu cầu xóa. Trước khi bật ở production, phải thử vòng đời, versioning, legal hold, expiration và quyền administrator trong môi trường kiểm soát.

### 8.3. Xóa dữ liệu không đơn giản là delete object

Một bản ghi có thể tồn tại trong:

- Bản chính ở database/object storage.
- Replica, read model, search index và cache.
- Version cũ, soft-delete marker và multipart upload.
- Export, data lake, warehouse và bản sao tích hợp.
- Snapshot, backup và archive.

Chính sách xóa cần xác định phạm vi từng bản sao và thời điểm các bản sao hết hạn. Backup immutable/retained có thể chưa xóa ngay; cần tài liệu hóa thời gian dữ liệu sẽ biến mất khỏi chu kỳ backup, đồng thời ngăn phục hồi backup làm sống lại dữ liệu đã có yêu cầu xóa khi không được phép.

## 9. Phân biệt backup, replica, archive và retention

Các cơ chế này không thay thế nhau:

| Cơ chế | Giải quyết vấn đề | Không bảo đảm điều gì? |
|---|---|---|
| **Backup** | Khôi phục dữ liệu sau xóa nhầm, hỏng, ransomware hoặc sự cố | Không nhất thiết là bản mới nhất hoặc có thể truy vấn trực tiếp |
| **Replica** | Tăng availability/đọc hoặc duy trì bản sao gần thời gian thực | Lỗi xóa, corruption hoặc ransomware có thể lan sang replica |
| **Archive** | Lưu dữ liệu ít truy cập với chi phí thấp | Không thay thế backup/PITR hay bảo đảm restore nhanh |
| **Retention** | Xác định dữ liệu phải được giữ bao lâu | Không tự tạo bản sao khôi phục |
| **Legal hold / immutability** | Ngăn sửa/xóa trong phạm vi/thời hạn nhất định | Không thay thế encryption, access control và backup strategy |

Một database có retention 7 năm vẫn cần backup/PITR phù hợp RPO/RTO. Một archive được giữ 7 năm không chắc khôi phục được database đang chạy về trạng thái nhất quán tại một thời điểm.

### 9.1. RPO và RTO

- **Recovery Point Objective (RPO):** mức mất dữ liệu tối đa chấp nhận được, thường diễn đạt bằng thời gian giữa thời điểm sự cố và dữ liệu gần nhất khôi phục được.
- **Recovery Time Objective (RTO):** thời gian mục tiêu để khôi phục dịch vụ/dữ liệu về trạng thái có thể sử dụng.

Lưu archive nhiều năm không đồng nghĩa đạt RPO vài phút. Cần thiết kế backup frequency, transaction log/PITR, replication, restore procedure và kiểm thử thực tế.

## 10. Lifecycle cho object storage

Object storage thường phù hợp với ảnh, video, file export, tài liệu và log vì có thể quản lý object bằng key, metadata, tag, version và storage class.

### 10.1. Prefix và tag

Có thể phân nhóm theo:

- Prefix: uploads/, booking-documents/, reports/, logs/.
- Tag: data-classification, retention-class, owner, environment, legal-hold.
- Thời điểm tạo/metadata nghiệp vụ: created-at, retention-start-date, record-closed-at.

Prefix dễ tổ chức và thường thuận tiện cho policy; tag linh hoạt hơn nhưng cần kiểm soát ai được tạo/sửa tag. Không để user upload tùy ý gắn tag legal-hold=false hoặc đổi retention metadata nếu đó là thuộc tính quản trị.

### 10.2. Versioning

Versioning giúp phục hồi object bị ghi đè/xóa nhầm, nhưng làm tăng dung lượng do giữ nhiều phiên bản. Lifecycle phải xử lý:

- Current version.
- Noncurrent versions.
- Delete markers.
- Incomplete multipart uploads.
- Object lock/legal hold trên version phù hợp.

Một delete trong bucket có versioning có thể chỉ tạo delete marker; các version cũ vẫn còn và có thể tiếp tục tính phí. Cần hiểu chính xác hành vi xóa và truy xuất của provider.

### 10.3. Khôi phục object từ archive

Quy trình tham khảo:

1. Xác nhận owner, lý do và quyền được phép truy xuất.
2. Kiểm tra object/version, retention, hold và trạng thái archive.
3. Tạo restore request với priority/time window phù hợp.
4. Theo dõi trạng thái phục hồi và chi phí.
5. Khi sẵn sàng, đọc dữ liệu, kiểm tra checksum/integrity và quyền truy cập.
6. Hết thời gian cần truy cập, để bản restored hết hạn hoặc chuyển về tier theo policy.
7. Ghi audit về requester, object reference, approval và kết quả.

Không hứa một archive object có thể đọc ngay như Standard tier. Thời gian restore, priority và giá phụ thuộc class cụ thể.

## 11. Lifecycle cho database và dữ liệu có cấu trúc

Database không phải lúc nào cũng hỗ trợ chuyển một row giữa hot/cold class tự động. Có thể dùng các chiến lược:

### 11.1. Time partitioning

Phân vùng bảng theo tháng/quý/năm giúp quản lý dữ liệu lịch sử, index và thao tác archive/drop partition.

~~~sql
-- Minh họa PostgreSQL partition theo tháng.
CREATE TABLE booking_events (
    event_id BIGINT NOT NULL,
    booking_id VARCHAR(40) NOT NULL,
    occurred_at TIMESTAMP NOT NULL,
    event_type VARCHAR(80) NOT NULL
) PARTITION BY RANGE (occurred_at);

CREATE TABLE booking_events_2026_11
PARTITION OF booking_events
FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
~~~

Ví dụ cần điều chỉnh theo database engine và chiến lược partition thực tế. Cần xem unique constraint, primary key, index, query pruning, timezone và maintenance. Không drop partition chỉ vì đã qua tháng nếu retention/legal hold chưa được xác nhận.

### 11.2. Archive table hoặc export

Dữ liệu lịch sử có thể được chuyển sang archive table, object storage, warehouse hoặc analytical store. Quy trình cần bảo đảm:

1. Xác định tập dữ liệu có thể chuyển theo mốc nghiệp vụ.
2. Export nhất quán (snapshot/CDC/transaction boundary phù hợp).
3. Kiểm tra row count, checksum, key và tham chiếu.
4. Chỉ đánh dấu/xóa dữ liệu online sau khi bản archive được xác minh và có thể đọc.
5. Cập nhật truy vấn lịch sử hoặc API tra cứu để biết dữ liệu nằm ở đâu.
6. Theo dõi chi phí và tốc độ restore.

Không làm thao tác “copy rồi delete” thiếu transaction/manifest/đối soát. Nếu job chết giữa chừng, phải biết batch nào hoàn tất, batch nào còn thiếu và cách chạy lại idempotent.

### 11.3. TTL cho dữ liệu hết hạn tự nhiên

TTL phù hợp với session, cache, token phụ, temporary state hoặc dữ liệu có thời hạn nghiệp vụ rõ. Không nên dùng TTL đơn giản cho hồ sơ cần retention pháp lý hoặc có quan hệ với record chính nếu chưa có quy tắc giữ liên quan.

TTL có thể xóa không đúng chính xác tại giây hết hạn; nhiều hệ thống xử lý nền và có độ trễ. Ứng dụng phải ngăn dùng dữ liệu đã hết hạn theo logic nghiệp vụ ngay cả khi record vật lý chưa được dọn.

## 12. Phân tầng log, telemetry và audit

Log thường có access pattern theo thời gian: dữ liệu mới cần truy vấn nhanh để xử lý incident; dữ liệu cũ ít được đọc nhưng có thể cần lưu để audit hoặc điều tra.

Một thiết kế tham khảo:

| Tuổi dữ liệu | Vị trí/lớp | Mục đích |
|---|---|---|
| 0–14 ngày | Log search hot tier | Incident response, debugging và cảnh báo |
| 15–90 ngày | Log storage/cool phù hợp | Điều tra sự kiện gần đây, trend |
| Sau 90 ngày | Object/archive theo policy | Audit hoặc yêu cầu giữ lâu dài |
| Hết retention được duyệt | Expire/delete | Giảm dữ liệu và chi phí |

Các mốc chỉ mang tính ví dụ. Security audit log, application debug log, access log và dữ liệu analytics có mục đích/retention khác nhau. Không gộp tất cả vào một policy chung vì dễ giữ thừa dữ liệu nhạy cảm hoặc xóa thiếu bằng chứng cần thiết.

### Log có thể chứa dữ liệu nhạy cảm

Trước khi archive log, cần masking/redaction token, password, payment data và PII; hạn chế quyền tìm kiếm/restore; mã hóa và audit truy cập. Chuyển một log nhạy cảm sang archive không làm nó bớt nhạy cảm.

## 13. Bảo mật và quản trị dữ liệu ở mọi tier

Phân tầng không làm giảm nghĩa vụ bảo vệ dữ liệu. Các kiểm soát cần theo dữ liệu trong suốt vòng đời:

- **Classification:** public, internal, confidential, restricted hoặc taxonomy của tổ chức.
- **Encryption at rest:** dùng cơ chế mã hóa của storage; quản lý key, rotation và quyền decrypt.
- **Encryption in transit:** TLS hoặc cơ chế tương đương khi di chuyển/restore/replicate.
- **IAM:** quyền read/write/delete/restore/retention administration tách biệt theo vai trò.
- **Network access:** private endpoint, egress path và access control phù hợp.
- **Audit:** ai đọc, tải, restore, đổi tier, xóa, thay retention hoặc đặt/gỡ hold.
- **Integrity:** checksum, versioning, object lock hoặc xác minh dữ liệu tùy yêu cầu.
- **Data minimization:** không lưu nhiều hơn mục đích và thời hạn cần thiết.
- **Residency:** region/replication destination phù hợp yêu cầu tổ chức và pháp lý.

Đặc biệt tách quyền **đọc dữ liệu**, **xóa dữ liệu** và **thay đổi retention/hold**. Một tài khoản vận hành thường ngày không nên đồng thời có quyền xóa backup immutable hoặc gỡ legal hold nếu không có quy trình break-glass và audit.

## 14. Quan sát và quản lý chi phí

Một lifecycle policy chạy đúng về mặt kỹ thuật chưa chắc đạt mục tiêu chi phí hoặc nghiệp vụ. Cần theo dõi:

| Chỉ số | Ý nghĩa | Tín hiệu cần xem |
|---|---|---|
| Dung lượng theo class | Dữ liệu nằm ở tier nào | Hot tăng liên tục có thể do lifecycle không chạy |
| Object/row count theo tuổi | Quy mô dữ liệu lịch sử | Dữ liệu không hết hạn như dự kiến |
| Transition count / failure | Số lượng chuyển tier và lỗi | Rule selector sai hoặc object không đủ điều kiện |
| Retrieval volume/cost | Dữ liệu cool/archive được đọc bao nhiêu | Tier quá lạnh cho access pattern thực |
| Restore time và failure | Khả năng lấy lại dữ liệu | RTO có được đáp ứng không |
| Versioned bytes/delete markers | Phần dung lượng giữ do version | Xóa object nhưng chi phí không giảm |
| Incomplete upload volume | Tài nguyên upload dở dang | Cleanup rule thiếu hoặc sai |
| Retention/hold exceptions | Số record không được xóa | Legal hold thiếu owner hoặc hết thời hạn nhưng chưa rà |
| Cost per retained TB/year | Chi phí lưu giữ | So sánh class, redundancy, request và transfer |

Nên đặt alert khi object hết retention nhưng vẫn còn ngoài dự kiến và không có hold; dung lượng hot tăng bất thường; restore time vượt RTO; retrieval fee/egress tăng đột biến; lifecycle transition/expiration thất bại; hoặc có người thay đổi policy, lock hay retention metadata ngoài quy trình.

## 15. Case study: vòng đời dữ liệu của nền tảng đặt phòng

**Bối cảnh:** một ứng dụng cho thuê chỗ ở lưu booking, chứng từ thanh toán, ảnh listing, log vận hành và file export báo cáo. Lượng ảnh tăng nhanh; log cần tra cứu nhanh khi incident nhưng ít được đọc sau vài tuần; dữ liệu giao dịch phải được giữ theo chính sách đã phê duyệt. Hệ thống cần giảm chi phí mà vẫn có thể tìm và phục hồi hồ sơ.

### 15.1. Phân loại và hướng lưu trữ

| Dữ liệu | Access pattern | Thiết kế lưu trữ tham khảo |
|---|---|---|
| Booking đang hoạt động | Read/write thường xuyên | Primary relational DB, backup/PITR và replica theo RTO/RPO |
| Booking đã kết thúc | Ít cập nhật, thỉnh thoảng tra cứu | Giữ trong DB theo giai đoạn hoạt động; archive export nhất quán cho lịch sử dài hạn nếu cần |
| Payment evidence/invoice | Truy cập đối soát, yêu cầu giữ riêng | Store được bảo vệ, audit, retention và hold theo loại hồ sơ |
| Ảnh listing phổ biến | GET thường xuyên | Object hot/standard, CDN và versioning nếu cần |
| Ảnh listing không hoạt động | Ít đọc nhưng cần phục hồi trong thời gian xác định | Cool tier sau khi listing đóng đủ thời gian |
| Application debug log | Đọc nhiều lúc incident | Log hot ngắn hạn, sau đó expire hoặc archive chọn lọc |
| Security audit log | Ít đọc nhưng có giá trị điều tra | Storage có integrity/access control và retention riêng |
| Báo cáo export | Thường đọc ngay sau khi tạo, sau đó hiếm | Hot → cool → archive; xóa khi hết hạn policy |

### 15.2. Luồng lifecycle cho ảnh listing

~~~mermaid
flowchart TD
    Upload["Upload ảnh listing"] --> Validate["Validate, scan, classify"]
    Validate --> Hot["Object hot + CDN"]
    Hot --> Active{"Listing còn hoạt động?"}
    Active -->|Có| Hot
    Active -->|Không đủ điều kiện hiển thị| Cool["Cool tier sau thời gian không hoạt động"]
    Cool --> Restore{"Có yêu cầu dùng lại?"}
    Restore -->|Có| Rehydrate["Restore / chuyển online"]
    Rehydrate --> Hot
    Restore -->|Không, hết retention| Hold{"Legal hold?"}
    Hold -->|Có| Archive["Giữ theo hold"]
    Hold -->|Không| Delete["Xóa object, versions và derived copies"]
~~~

Trước khi xóa ảnh cần xem listing, cache/CDN, thumbnail, bản resize, version cũ và bản sao backup. Nếu ảnh chứa dữ liệu cá nhân, yêu cầu xóa có thể áp dụng tới derived copy theo chính sách.

### 15.3. Luồng retention cho hồ sơ giao dịch

1. Payment service ghi giao dịch và reference bất biến theo thiết kế ledger.
2. Hồ sơ được phân loại và gắn retention start date theo mốc được duyệt.
3. Dữ liệu truy cập thường xuyên ở lớp online có quyền hạn chế.
4. Khi hết giai đoạn vận hành, hồ sơ có thể export/archive theo batch có manifest và checksum.
5. Nếu có tranh chấp, legal hold ngăn expiration của đúng phạm vi.
6. Khi hold được gỡ và hết retention, disposition job xóa các bản sao thuộc phạm vi policy, ghi audit kết quả.

Không coi việc chuyển một bản copy sang archive là cho phép xóa source trước khi export được kiểm tra. Cũng không coi archive là backup đầy đủ cho hệ thống ledger.

### 15.4. Tiêu chí nghiệm thu

- Mỗi nhóm dữ liệu có owner, classification, access pattern và retention start event.
- Tier transition không làm ứng dụng vượt latency/SLO; restore đáp ứng thời gian đã cam kết.
- Dữ liệu có hold không bị lifecycle expiration xóa.
- Export/archive có manifest, checksum và quy trình đọc kiểm thử.
- Backup/PITR được thiết kế theo RPO/RTO riêng, không nhầm với archive.
- Secret/PII được bảo vệ trong log và bản archive.
- Dashboard đo dung lượng, retrieval, restore, transition failure và cost theo data class.

## 16. Thiết kế quy trình chuyển tầng và xóa an toàn

Một policy tốt cần có giai đoạn thử nghiệm và kiểm tra trước khi áp dụng rộng:

1. **Inventory:** lấy danh sách dữ liệu, tuổi, prefix/tag, dung lượng, version và access metrics.
2. **Classify:** gán loại dữ liệu, owner, sensitivity, retention start date và hold status.
3. **Model:** ước lượng storage, requests, retrieval, transfer, restore và operational cost theo kịch bản.
4. **Pilot:** áp policy với prefix/bucket/partition nhỏ, dùng dữ liệu thử hoặc nhóm ít rủi ro.
5. **Verify transition:** kiểm tra class thực tế, quyền truy cập, latency và hóa đơn.
6. **Verify restore:** phục hồi một mẫu, xác nhận checksum/content/metadata và đo thời gian.
7. **Enable expiration:** chỉ bật xóa sau khi policy/hold và khôi phục đã được xác minh.
8. **Monitor:** theo dõi lifecycle failure, exception, retrieval và cost; rà soát định kỳ.

### 16.1. Xóa theo batch có thể chạy lại

Với archive database, mỗi batch nên có manifest ghi partition/key range, count, checksum, thời điểm export, trạng thái copy, verify và disposition. Job cần idempotent để chạy lại không tạo bản sao không kiểm soát hoặc xóa dữ liệu chưa archive thành công.

Ví dụ trạng thái:

~~~text
DISCOVERED
  -> EXPORTED
  -> VERIFIED
  -> ELIGIBLE_FOR_DELETE
  -> DELETED

Nhánh:
VERIFY_FAILED -> RETRY / MANUAL_REVIEW
LEGAL_HOLD     -> ON_HOLD
~~~

Không chuyển thẳng từ DISCOVERED sang DELETED. Bằng chứng VERIFIED phải xác nhận bản archive thực sự có thể sử dụng, không chỉ file tồn tại.

## 17. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Chọn tier chỉ dựa trên giá/GB | Retrieval và operation cost làm tổng phí cao hơn | Dùng access pattern thật và mô hình tổng chi phí |
| Archive dữ liệu còn cần latency thấp | API chậm hoặc phải restore ngoài dự kiến | Xác định access SLA và hot read path |
| Xóa theo LastModified mà không hiểu nghiệp vụ | Retention bắt đầu sai mốc hoặc bị kéo dài vô hạn | Lưu retention-start-date theo sự kiện được duyệt |
| Coi archive là backup | Không thể khôi phục DB tới point-in-time | Thiết kế backup/PITR, RPO/RTO riêng |
| Bật expiration ngay khi tạo lifecycle | Xóa nhầm dữ liệu, version hoặc bản chưa archive | Pilot, inventory, restore test và approval |
| Quên noncurrent version/delete marker | Dữ liệu cũ vẫn tồn tại và tiếp tục tính phí | Lifecycle riêng cho version và marker |
| Không tính retrieval/egress | Hóa đơn tăng khi audit hoặc restore | Ước lượng tần suất, kích thước và vùng truy cập |
| Legal hold chỉ là tag tự khai | Người dùng có thể xóa hoặc bypass hold | Dùng cơ chế hold/lock được bảo vệ và audit |
| Giữ log nhạy cảm ở archive không mã hóa/quản lý quyền | Dữ liệu lộ dù hiếm truy cập | Classification, encryption, IAM và redaction |
| Xóa source trước khi verify archive | Mất dữ liệu khi copy lỗi hoặc thiếu | Export manifest, checksum, read-back rồi mới disposition |
| TTL được coi là xóa chính xác ngay lập tức | Dữ liệu hết hạn vẫn có thể còn vật lý | Enforce expiry ở application, hiểu độ trễ cleanup |

## 18. Checklist review kiến trúc lưu trữ

### Phân loại và phân tầng

- [ ] Dữ liệu được phân loại theo owner, mục đích, sensitivity, access frequency và latency.
- [ ] Hot/warm/cool/archive được chọn theo access pattern và SLA truy xuất.
- [ ] Đã tính storage, request, retrieval, transfer, restore và vận hành.
- [ ] Có xem xét minimum duration, minimum billable size và phí chuyển tầng của provider.
- [ ] Database, object, block, file, cache và stream có thiết kế lifecycle phù hợp loại dữ liệu.

### Lifecycle và retention

- [ ] Transition/expiration gắn với mốc nghiệp vụ được xác định.
- [ ] Noncurrent versions, delete markers và multipart uploads có policy.
- [ ] Retention period có owner, purpose, start event, disposition và evidence.
- [ ] Legal hold/retention lock không thể bị workload thông thường sửa/gỡ.
- [ ] Xóa bao phủ replica, index, cache, export và bản sao liên quan theo policy.
- [ ] Policy đã pilot; expiration chỉ bật sau khi kiểm tra phạm vi.

### Backup và khôi phục

- [ ] Backup/PITR độc lập với archive, có RPO/RTO.
- [ ] Đã thử restore, kiểm tra checksum/content và đo thời gian.
- [ ] Có manifest và trạng thái batch cho export/archive.
- [ ] Có phương án reconciliation và manual review nếu copy/verify/delete thất bại.

### Bảo mật và vận hành

- [ ] Encryption at rest/in transit, key management, IAM và network access được thiết kế.
- [ ] Read, delete, restore, retention administration và legal hold có phân quyền phù hợp.
- [ ] Audit log bao phủ truy cập và thay đổi policy.
- [ ] Dashboard theo dung lượng/class, transition, retrieval, restore, retention exception và cost.
- [ ] Có owner/runbook cho legal hold, restore khẩn cấp, lifecycle failure và yêu cầu xóa.

## 19. Bài tập thực hành

**Bối cảnh:** nền tảng đặt phòng lưu năm nhóm dữ liệu: booking đang hoạt động, booking đã kết thúc, ảnh listing, debug log và chứng từ thanh toán. Ảnh tăng 30% mỗi quý; log được truy vấn nhiều trong 10 ngày đầu; bộ phận đối soát cần tra cứu một số chứng từ bất kỳ lúc nào; một phần hồ sơ có thể nằm trong tranh chấp. Chi phí object storage nóng đang tăng.

Hãy xây dựng chính sách:

1. Phân loại từng nhóm theo access frequency, latency, sensitivity và retention purpose.
2. Chọn hot/warm/cool/archive hoặc database/backup phù hợp; giải thích tradeoff.
3. Định nghĩa lifecycle transition và expiration cho ảnh, log và export.
4. Xác định retention start event cho booking và payment evidence; nêu ai phê duyệt thời hạn.
5. Thiết kế legal hold và cách ngăn job expiration xóa hồ sơ bị giữ.
6. Mô tả cách export booking lịch sử sang archive với manifest, checksum và read-back.
7. Phân biệt backup/PITR, replica và archive; đặt RPO/RTO cho dữ liệu vận hành.
8. Ước lượng tổng chi phí gồm storage, requests, retrieval, egress, restore và log.
9. Xác định các dashboard/alert cần có và cách xử lý restore khẩn cấp.
10. Viết điều kiện nghiệm thu trước khi bật expiration tự động.

**Gợi ý tự kiểm tra:** Không archive ảnh chỉ dựa trên tuổi nếu listing còn hoạt động và cần truy cập nhanh. Không xóa booking theo ngày export. Khi có legal hold, phải xác định toàn bộ version/bản sao liên quan. Một object đã nằm trong archive không chứng minh có backup; cần thử restore và kiểm tra tính toàn vẹn.

## 20. Ghi nhớ

**Phân tầng** tối ưu nơi lưu dữ liệu theo access pattern và chi phí; **lifecycle** tự động chuyển/xóa dữ liệu theo điều kiện; **retention** xác định dữ liệu phải được giữ bao lâu và ngoại lệ nào ngăn việc xóa. Ba quyết định phải xuất phát từ phân loại dữ liệu, mốc nghiệp vụ và khả năng truy xuất thật.

Archive không thay thế backup, replica không thay thế version/retention, và xóa một object không đồng nghĩa đã xóa mọi bản sao. Thiết kế tốt kết hợp tier phù hợp, lifecycle có kiểm soát, legal hold, encryption, IAM, audit, RPO/RTO và restore test. Chỉ bật expiration sau khi đã kiểm tra phạm vi, xác minh bản lưu và có thể chứng minh dữ liệu được xử lý theo đúng chính sách.
