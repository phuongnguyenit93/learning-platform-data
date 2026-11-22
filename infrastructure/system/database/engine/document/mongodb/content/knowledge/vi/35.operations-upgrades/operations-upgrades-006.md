# Nâng cấp lần lượt, Feature Compatibility Version và điều kiện hạ phiên bản trong MongoDB

## 1. Vì sao nâng cấp MongoDB không chỉ là thay một tệp nhị phân?

Hãy hình dung một ứng dụng đặt hàng đang chạy MongoDB replica set gồm ba node:

```text
                     Application
                          |
                          v
                  MongoDB Replica Set
                          |
          +---------------+---------------+
          |               |               |
          v               v               v
      Node A          Node B          Node C
      PRIMARY         SECONDARY       SECONDARY
      MongoDB 7.0     MongoDB 7.0     MongoDB 7.0
```

Đội vận hành muốn nâng lên MongoDB 8.0 để nhận bản vá, cải thiện hiệu năng và dùng tính năng mới. Nếu dừng cả ba node cùng lúc rồi cài 8.0, toàn bộ hệ thống có thể ngừng phục vụ. Nếu chỉ nâng một node nhưng không kiểm tra khả năng tương thích, một node có thể không khởi động hoặc không tiếp tục replication.

Ngay cả khi cả ba process đều chạy MongoDB 8.0, câu chuyện chưa kết thúc: database có thể vẫn dùng **Feature Compatibility Version (FCV) 7.0**. Khi quyết định nâng FCV lên 8.0, một số tính năng có thể bắt đầu ghi metadata/dữ liệu theo dạng không tương thích với phiên bản cũ. Điều này làm **hạ phiên bản** phức tạp hơn hoặc không còn là thao tác được hỗ trợ theo chính sách của release.

Bài học này làm rõ ba hoạt động có quan hệ nhưng **không giống nhau**:

1. **Rolling upgrade (nâng cấp lần lượt):** thay binary trên từng member theo trình tự để duy trì quorum và giảm gián đoạn.
2. **Nâng FCV:** kích hoạt các tính năng hoặc định dạng dữ liệu mới có thể không tương thích ngược, sau khi cả deployment đã nâng phiên bản.
3. **Downgrade/rollback:** đưa hệ thống về phiên bản cũ **chỉ khi đường hạ phiên bản được nhà cung cấp hỗ trợ và các điều kiện dữ liệu, FCV, topology đã đáp ứng**.

> **Nguyên tắc quan trọng:** phiên bản binary đang chạy, FCV và khả năng hạ phiên bản là ba thứ cần kiểm tra riêng. Không thể kết luận “rollback được” chỉ vì mới thay binary hoặc chỉ vì vẫn còn bản backup.

---

## 2. Phạm vi và lưu ý về phiên bản

Các ví dụ minh họa chính sử dụng nâng cấp **MongoDB 7.0 → 8.0** trên **self-managed replica set** vì đây là một quy trình rolling upgrade rõ ràng trong tài liệu chính thức.

Bài cũng trình bày các thay đổi chính sách của dòng **8.3 và 9.0**, nhưng không dùng một runbook bất biến cho mọi release:

- Với **MongoDB 8.0 → 7.0**, tài liệu phiên bản 8.0 quy định **Community Edition không hỗ trợ binary downgrade**, còn Enterprise cần làm việc với MongoDB Support.
- **Bắt đầu từ MongoDB 8.3**, tài liệu công bố khả năng downgrade đến một phiên bản minor/major liền kề theo đường hỗ trợ.
- Với **MongoDB 9.0**, đường downgrade có những tài liệu riêng cho mục tiêu 8.3 hoặc đường 8.0 trong điều kiện được mô tả.
- MongoDB Atlas, Ops Manager và Cloud Manager có **quy trình quản lý phiên bản riêng**, không nên áp toàn bộ câu lệnh self-managed vào cluster được quản lý.
- Các phiên bản có thể thay đổi tính năng, điều kiện FCV, các tham số bắt buộc và hỗ trợ topology.

**Không dùng bài này làm script tự động nâng/hạ production.** Trước khi thao tác phải đọc tài liệu ứng với **phiên bản nguồn, phiên bản đích, edition, deployment type, FCV và các tính năng đang sử dụng**.

---

## 3. Các khái niệm cốt lõi

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Binary version** | Phiên bản phần mềm `mongod`/`mongos` đang chạy | `8.0.x` |
| **Patch release** | Bản sửa lỗi trong cùng release series | `8.0.a → 8.0.b` |
| **Major/minor release** | Mốc cập nhật có thể có thay đổi tính năng/compatibility | `7.0 → 8.0` |
| **FCV** | Feature Compatibility Version, kiểm soát các tính năng ghi dữ liệu không tương thích với phiên bản trước | `"7.0"` hoặc `"8.0"` |
| **Rolling upgrade** | Nâng từng node, chờ node ổn định trước khi nâng node tiếp theo | Secondary B, secondary C, former primary A |
| **Mixed-version state** | Các members tạm thời có binary versions khác nhau trong quá trình nâng | A=7.0; B/C=8.0 |
| **Primary stepdown** | Đưa primary về secondary để replica set bầu primary mới | `rs.stepDown()` |
| **Quorum/majority** | Số thành viên có quyền biểu quyết cần cho election, và majority data-bearing cho một số hoạt động | 2/3 voting members |
| **Burn-in period** | Giai đoạn theo dõi binary mới trước khi bật FCV mới | Vài ngày theo policy |
| **Downgrade path** | Đường đưa version xuống được chính thức hỗ trợ | Phụ thuộc release/edition |
| **Rollback plan** | Phương án ứng phó nếu upgrade lỗi, không đồng nghĩa luôn được downgrade binary | Sửa config, thay node, restore |
| **Backup restore** | Khôi phục trạng thái từ backup, có thể là cách phục hồi khi không thể hạ binary | Snapshot + PITR |

### 3.1. Rollback trong tài liệu nâng cấp khác replication rollback

MongoDB dùng từ **rollback** cho cả việc một node replica set phải loại bỏ những writes chưa được xác nhận khi replication history thay đổi. Đó là **replica set rollback**.

Trong bài này, “rollback nâng cấp” nghĩa là **quay về trạng thái/phiên bản triển khai trước**. Hai quy trình không cùng semantics và không thể dùng một thao tác để thay thao tác còn lại.

---

## 4. Tách binary version với Feature Compatibility Version

Một deployment có thể có:

```text
mongod binary: MongoDB 8.0.x
FCV:           7.0
```

Đây là trạng thái **có chủ đích sau khi nâng binary từ 7.0 lên 8.0**. Tài liệu cho phép chạy binary 8.0 với FCV cũ trong giai đoạn đánh giá trước khi kích hoạt các tính năng ghi dữ liệu không tương thích với 7.0.

Sau giai đoạn burn-in, người vận hành có thể nâng:

```text
mongod binary: MongoDB 8.0.x
FCV:           8.0
```

Bây giờ các tính năng dựa trên FCV 8.0 có thể được bật theo quy định.

### 4.1. Vì sao MongoDB cần FCV?

Nếu binary mới lập tức sử dụng cấu trúc catalog, index hoặc metadata chỉ phiên bản mới hiểu, việc quay về binary cũ sẽ bị cản trở ngay từ lần khởi động.

FCV tạo một **giai đoạn chuyển tiếp có kiểm soát**:

```text
        Replace binaries             Enable incompatible features
              |                                 |
              v                                 v

7.0 binary / 7.0 FCV
          |
          v
8.0 binary / 7.0 FCV  ---- burn-in ---->  8.0 binary / 8.0 FCV
          |                                 |
          |                           Downgrade risk grows
          v
Potential fallback, only when
release policy permits
```

### 4.2. FCV không phải giả lập đầy đủ binary cũ

Chạy MongoDB 8.0 ở FCV 7.0 **không làm 8.0 trở thành MongoDB 7.0**:

- Runtime và query planner có thể đã thay đổi.
- Một số behavior/bug fixes của 8.0 vẫn hiện diện.
- Protocol, startup options hoặc driver interactions vẫn cần kiểm chứng.
- Không phải mọi tính năng mới đều được gate bởi FCV.
- FCV cũ không tự bảo đảm binary downgrade hợp lệ theo chính sách.

---

## 5. Kiểm tra phiên bản binary và FCV

### 5.1. Xem binary server

Trong `mongosh`:

```javascript
db.version();
```

Hoặc:

```javascript
db.adminCommand({ buildInfo: 1 });
```

Trên host self-managed:

```bash
mongod --version
mongos --version
```

**Lưu ý:** đường PATH có thể trỏ tới binary đã cài mà **process đang chạy** vẫn là binary khác. Để biết effective running version, kiểm tra server qua kết nối tới node tương ứng và service process information.

### 5.2. Xem FCV

Chạy trong `mongosh` với quyền được cấp:

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

Kết quả điển hình ở trạng thái ổn định:

```javascript
{
  featureCompatibilityVersion: {
    version: "7.0"
  },
  ok: 1
}
```

Trong quá trình transition, output có thể chứa các trường như `targetVersion` hoặc trạng thái trung gian tùy release. Không chỉ đọc `version` rồi mặc định quá trình đã hoàn thành.

### 5.3. Kiểm tra tất cả replica set members

Chạy trên từng node hoặc dùng automation phù hợp:

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

Điều cần xác nhận là **tất cả members có FCV mong đợi và không mắc trạng thái transition kéo dài**.

---

## 6. Nâng cấp lần lượt là gì?

Với replica set ba data-bearing members:

```text
Trước upgrade:
  A PRIMARY  7.0
  B SECONDARY 7.0
  C SECONDARY 7.0

Bước 1:
  A PRIMARY  7.0
  B SECONDARY 8.0
  C SECONDARY 7.0

Bước 2:
  A PRIMARY  7.0
  B SECONDARY 8.0
  C SECONDARY 8.0

Bước 3:
  Step down A, bầu B/C làm PRIMARY.

Bước 4:
  A SECONDARY 8.0
  B/C chạy 8.0

Bước 5:
  Ổn định, theo dõi, sau đó nâng FCV lên 8.0.
```

Điểm quan trọng là **không tắt quá nhiều node cùng lúc**. Replica set cần đủ members để duy trì primary và đáp ứng write concern mà ứng dụng yêu cầu.

### 6.1. Rolling upgrade giảm downtime, không hứa zero interruption

Khi stepdown primary:

- Một cuộc election có thể làm gián đoạn writes ngắn.
- Existing TCP connections/cursors/transactions có thể bị ảnh hưởng.
- Driver cần server discovery và retry phù hợp.
- Những thao tác không idempotent cần được xử lý cẩn thận.
- Một số change streams có thể cần resume.

Vì vậy “rolling” có nghĩa **tránh dừng toàn bộ deployment theo kế hoạch**, không có nghĩa mọi request hoàn toàn không bị ảnh hưởng.

---

## 7. Trước khi nâng: một baseline đáng tin

Ghi nhận thông tin hiện hành:

| Nhóm | Cần lưu |
| --- | --- |
| Versions | Binary từng node, FCV, driver versions, tools |
| Topology | Node names, PRIMARY/SECONDARY, votes, priorities, hidden/delayed members |
| Replication | Majority availability, replication lag, oplog window |
| Storage | Free disk, IOPS, WiredTiger cache, filesystem |
| Query | p50/p95/p99, slow queries, index usage |
| Cluster workload | Read/write throughput, transactions, connections |
| Security | TLS, auth, KMIP/KMS, audit |
| Backup | Last successful backup, PITR window, restore drill |
| Applications | Driver/ORM compatibility, deprecations, feature usage |
| Automation | Package repositories, config files, service managers, IaC |
| External integrations | CDC connectors, BI, ETL, Search, monitoring, backup agents |

### 7.1. Cần biết những thứ không được phép thay đổi

Ví dụ:

- Không làm mất khả năng đa số members xác nhận writes.
- Không chấp nhận replication lag vượt RPO policy.
- Không thay đổi TLS/key permissions giữa rollout thiếu kiểm chứng.
- Không bật tính năng mới/FCV mới trước khi binary upgrade hoàn tất.
- Không hạ binary khi policy không hỗ trợ.

---

## 8. Lập đường nâng phiên bản hợp lệ

Không tùy ý nhảy từ binary quá cũ sang binary mới bằng cách thay executable.

Ví dụ cho nhánh **7.0 → 8.0**:

```text
MongoDB 6.0
    |
    v
MongoDB 7.0
    |
    v
MongoDB 8.0
```

Tài liệu 8.0 yêu cầu nguồn phải là **7.0-series** trước khi nâng lên 8.0. Nếu đang chạy 6.0, cần nâng từng release step như quy định.

### 8.1. Dòng 8.x và 9.0 có release cadence thay đổi

MongoDB hiện phân biệt major, minor, feature update và patch releases. Khi lập đường nâng:

- Kiểm tra phiên bản nguồn và target có phải adjacent releases không.
- Xem release có dành cho self-managed hay chỉ cho một số Atlas tracks.
- Xem liệu có bước minor trung gian bắt buộc theo chính sách từng dòng.
- Không suy ra từ tên version rằng có thể bỏ qua mọi bản trung gian.
- Dùng target patch release được khuyến nghị và còn hỗ trợ.

Ví dụ với 9.0, tài liệu có hướng dẫn lên 9.0 từ các nhánh nguồn được hỗ trợ. Luôn chọn **đúng trang upgrade procedure** cho nguồn/đích của mình.

### 8.2. Driver version khác Server version

Java MongoDB Sync Driver có version riêng; không nhất thiết trùng số với server. Một driver 5.x có thể hỗ trợ nhiều server releases, nhưng cần kiểm tra matrix.

Bài học:

- Không nâng driver bằng cách “đổi số cho giống MongoDB server”.
- Xem driver compatibility, API deprecations, connection settings, TLS/SSL requirements.
- Đánh giá ORM/framework wrappers (Spring Data MongoDB, Quarkus, Micronaut, Mongoose...).
- Kiểm tra các external tools như mongosh, mongodump, mongorestore, mongosync riêng.

---

## 9. Kiểm tra backup và khả năng phục hồi trước upgrade

Một checklist nâng cấp phải có câu trả lời cho:

1. Backup gần nhất có thành công không?
2. Có backup được phục hồi thử trên môi trường riêng không?
3. Backup có đúng version/topology mục tiêu khôi phục không?
4. Có lưu KMS/CMK/key versions cần giải mã backup không?
5. Nếu phát sinh lỗi sau FCV upgrade, có phương án restore sang deployment tương thích không?
6. Có snapshot/PITR window bao trùm thời điểm trước nâng cấp không?
7. Nếu dùng GridFS, dữ liệu files/chunks có được backup đầy đủ không?
8. Nếu dùng sharding, backup có consistent giữa shards/config servers không?

### 9.1. Backup khác downgrade binary

Giả sử binary downgrade không được hỗ trợ:

- Bạn **không nên** thay binary cũ trực tiếp trên data files của server mới.
- Có thể cần khôi phục snapshot đã tạo **trước upgrade** trên deployment có version phù hợp.
- Restore như vậy có thể mất các writes hợp lệ sau snapshot nếu không có PITR/reconciliation.
- Kế hoạch phải xử lý external systems, backup encryption và application traffic.

### 9.2. Snapshot không phải nút Undo toàn hệ thống

Một upgrade đã chạy được hai ngày rồi mới phát hiện query behavior không tương thích. Backup cũ có thể tồn tại, nhưng cutover về backup cần tính lượng dữ liệu mới đã phát sinh và các side effects ngoài MongoDB.

---

## 10. Trạng thái replica set cần đạt trước rollout

Chạy trên primary:

```javascript
rs.status();
```

Hoặc:

```javascript
db.adminCommand({
  replSetGetStatus: 1
});
```

Quan sát:

- Có đúng một PRIMARY không?
- Các data-bearing secondaries có `SECONDARY` và healthy không?
- Có member ở `RECOVERING`, `ROLLBACK` hoặc initial sync không?
- Majority voting members có khả dụng không?
- Secondary nào có replication lag?
- Có delayed/hidden members cần phối hợp riêng không?

### 10.1. Không nâng khi cluster chưa ổn định

Nếu một replica set ba nodes đã mất một node, ngắt thêm một node khác có thể khiến majority không đủ và mất khả năng ghi. Cần sửa tình trạng replication trước khi nâng.

### 10.2. Arbiter không thay data-bearing members

Arbiter tham gia voting/election nhưng **không có dữ liệu để xác nhận majority data writes theo cách một secondary data-bearing làm**. Một topology Primary + Secondary + Arbiter có khả năng chịu lỗi và durability khác với ba data-bearing members.

Không tính “2/3 nodes vẫn lên” mà bỏ qua writeConcern/replication capacity.

---

## 11. Kiểm tra FCV trước khi nâng 7.0 → 8.0

Với deployment 7.0, FCV cần ở trạng thái 7.0 ổn định trước bước nâng binary, theo hướng dẫn 8.0.

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

Kỳ vọng:

```javascript
{
  featureCompatibilityVersion: {
    version: "7.0"
  },
  ok: 1
}
```

Nếu output đang transition hoặc phiên bản khác, **dừng thay binary**, xác định nguyên nhân và xử lý theo hướng dẫn riêng.

### 11.1. Không nâng FCV lên 8.0 khi còn members 7.0

Bật FCV 8.0 có thể cho phép định dạng dữ liệu/metadata không tương thích với binary 7.0. Chỉ thực hiện sau khi **tất cả members đã nâng lên 8.0 và ổn định**.

### 11.2. Không coi FCV 7.0 là lý do trì hoãn upgrade vô hạn

Giai đoạn giữ FCV cũ nhằm kiểm chứng/giảm rủi ro ngắn hạn. Để sử dụng những tính năng FCV 8.0 cần nâng FCV khi đã sẵn sàng, với approvals phù hợp.

---

## 12. Rolling upgrade replica set: quy trình tổng quát

Ví dụ này áp dụng về mặt logic cho self-managed **7.0 → 8.0** theo MongoDB Manual.

### Giai đoạn 1 — nâng các SECONDARY lần lượt

Với secondary B:

1. Xác minh B thật sự ở `SECONDARY`, không initial sync hoặc rollback.
2. Kiểm tra A/C vẫn healthy và đủ majority.
3. Ngừng `mongod` B một cách graceful theo service runbook.
4. Thay binary/package của B sang phiên bản 8.0 được hỗ trợ.
5. Giữ đúng đường dẫn `dbPath`, certificate, keyfile, port, replica set name và storage config.
6. Khởi động B.
7. Chờ B nhận trạng thái `SECONDARY` và replication lag trở về ngưỡng chấp nhận được.
8. Kiểm tra logs, FCV và metrics.
9. Chỉ tiếp tục với C khi B ổn định.

Lặp lại cho C, mỗi lần **một node**.

### 12.1. Tại sao không nâng SECONDARY đồng thời?

Ngắt B và C cùng lúc để lại A một mình. Replica set có thể mất majority, không bầu/duy trì primary hữu dụng cho writes theo policy, và khả năng failover biến mất.

### 12.2. Command graceful shutdown

Trong `mongosh` kết nối **đúng secondary**:

```javascript
db.adminCommand({
  shutdown: 1
});
```

Hoặc dùng service manager:

```bash
# Ví dụ Linux systemd, chỉ thực hiện trong maintenance window
sudo systemctl stop mongod
```

Cả hai đều có thể ảnh hưởng trực tiếp đến availability. Không sao chép chạy trên mọi nodes.

---

## 13. Thay binary/package: giữ nguyên cấu hình và an toàn dữ liệu

Nếu cài qua package manager:

- Chọn đúng repository/version.
- Xác nhận architecture và OS hỗ trợ.
- Pin target version.
- Kiểm tra service unit, config file path, data dir owner, permissions.
- Tránh package install script tự restart nhiều instances cùng lúc.
- Giữ binary/source packages để có phương án khôi phục hợp lệ nếu release hỗ trợ.

Ví dụ:

```bash
mongod --version

# Dùng package manager phù hợp distro để cài đúng release,
# sau đó khởi động service theo runbook.
sudo systemctl start mongod
```

**Không** chạy một script thay binary trên cả replica set chỉ vì config management có khả năng song song.

### 13.1. Giữ đúng key và certificate

MongoDB có thể không khởi động nếu:

- Mất `security.keyFile` phục vụ internal authentication.
- Chứng chỉ TLS không phù hợp.
- KMIP/ESE key không truy cập được.
- File permissions của `dbPath` sai.
- Package tự thay đổi configuration default.
- Bind IP/port không như trước.

Thay binary là bước cần thiết, nhưng **không được làm mất khả năng node tham gia replica set**.

---

## 14. Sau mỗi secondary: kiểm tra khả năng bắt kịp

Trên primary hoặc member phù hợp:

```javascript
rs.status();
```

Các điều kiện vận hành:

- Node trở lại `SECONDARY`.
- Không có continuous restart loop.
- Replication lag nằm trong mục tiêu.
- Không có `ROLLBACK`/`RECOVERING` kéo dài.
- Oplog window đủ để node bắt kịp.
- Error rate, disk usage, write concern timeouts không tăng bất thường.

### 14.1. Secondary bắt kịp không có nghĩa ứng dụng hoàn toàn ổn

Primary có thể chưa chạy binary mới. Ứng dụng cần được kiểm tra **sau khi một 8.0 secondary trở thành primary** để phát hiện behavior khác biệt thực tế.

### 14.2. Chọn thời điểm nâng node tiếp theo

Một lựa chọn vận hành an toàn là chờ node ổn định nhiều chu kỳ metrics, không chỉ thấy status SECONDARY trong một lần đọc. Với tải lớn hoặc nhiều indexes, có thể cần thời gian lâu hơn.

---

## 15. Primary stepdown: giai đoạn gây gián đoạn có chủ đích

Khi các secondaries đã nâng và khỏe, đưa primary cũ xuống bằng:

```javascript
rs.stepDown();
```

Thao tác có thể làm session hiện tại bị ngắt hoặc trả lỗi kết nối vì node không còn là primary. Cần **kết nối lại** sau election.

### 15.1. Vì sao stepdown trước khi thay primary?

Nếu tắt thẳng primary cũ, replica set cũng có thể election, nhưng việc stepdown có kiểm soát giúp:

- Xác minh thành viên mới đã sẵn sàng lên primary.
- Theo dõi failover.
- Giảm bất ngờ cho application.
- Giới hạn thao tác quản trị trong maintenance window.

### 15.2. Điều kiện trước stepdown

- Majority khỏe.
- At least one upgraded secondary eligible làm primary.
- Có đủ oplog/replication synchronization.
- Write concern/driver retry policy phù hợp.
- Không có transaction/background maintenance quan trọng cần tránh.
- Các application owners biết có thể có transient errors.

### 15.3. Sau stepdown

Xác nhận một node 8.0 đã lên `PRIMARY`, rồi mới ngừng và nâng **former primary** từ 7.0 lên 8.0.

---

## 16. Nâng former primary và hoàn tất binary phase

Sau khi primary cũ A đã trở thành SECONDARY:

1. Ngừng A.
2. Thay binary 7.0 bằng 8.0.
3. Khởi động lại với cấu hình giữ nguyên.
4. Chờ A trở về `SECONDARY`.
5. Kiểm tra B/C đang chạy cùng release 8.0 và FCV vẫn ở 7.0 trong giai đoạn đầu.
6. Ghi lại completion marker.

```text
Binary phase completed:

A SECONDARY  8.0
B PRIMARY    8.0
C SECONDARY  8.0

Feature Compatibility Version:
             7.0
```

Đây là trạng thái mong đợi trước khi bật những features mới cần FCV 8.0.

---

## 17. FCV sau binary upgrade: tại sao cần giai đoạn burn-in?

Tài liệu MongoDB khuyến nghị không bật ngay backwards-incompatible features sau khi thay binary. Một **burn-in period** cho phép:

- Theo dõi query regressions và CPU.
- Kiểm thử Java/Node/Python drivers khi primary thực sự là binary mới.
- Quan sát transactions, failover và replication.
- Xem backup/restore hooks hoạt động bình thường.
- Xác nhận các agents/monitoring/tools tương thích.
- Đánh giá schema/index feature behavior trước khi cho phép dùng các tính năng không tương thích ngược.

### 17.1. Burn-in không phải yêu cầu tính theo một số ngày cố định

Một tổ chức có thể chọn nhiều giờ hoặc vài ngày tùy:

- Criticality.
- Deployment size.
- Traffic seasonality.
- Có giờ cao điểm/low peak.
- SLAs.
- Khả năng tổ chức diễn tập rollback.

Không có con số “phải chờ 48 giờ” áp dụng cho mọi deployment.

### 17.2. Quan trọng với release policy

Giữ FCV cũ có thể tạo **khoảng an toàn kỹ thuật** đối với một số định dạng, nhưng **không tự tạo quyền downgrade** nếu edition/release không hỗ trợ. Vì vậy kết quả của burn-in có thể là tiếp tục FCV upgrade hoặc **khôi phục qua backup/đường hỗ trợ**, không nhất thiết thay binary ngược.

---

## 18. Bật FCV 8.0 sau khi sẵn sàng

Trên **PRIMARY** của replica set MongoDB 8.0, trong database `admin`:

```javascript
db.adminCommand({
  setFeatureCompatibilityVersion: "8.0",
  confirm: true
});
```

Từ MongoDB 7.0, tham số `confirm: true` là bắt buộc khi thay đổi FCV.

### 18.1. Kiểm tra lại

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

Kỳ vọng:

```javascript
{
  featureCompatibilityVersion: {
    version: "8.0"
  },
  ok: 1
}
```

Với replica set, phải xác nhận các data-bearing members đã nhận FCV mới theo cơ chế replication và không còn transition.

### 18.2. Lệnh không chỉ là đổi một nhãn

`setFeatureCompatibilityVersion` có thể:

- Ghi vào các system collections.
- Cần majority of data-bearing replica set members.
- Thực hiện thao tác cấu hình nội bộ tương ứng release.
- Chờ các thay đổi được truyền tới majority.
- Bị ngăn bởi một số background operations.
- Gặp lỗi nếu cluster có data/catalog không tương thích.

Ví dụ tài liệu 8.0 nói khi nâng FCV lên 8.0, replica set config được cập nhật thêm trường `term` theo cơ chế nội bộ.

### 18.3. Idempotency không có nghĩa có thể chạy vô hạn

Tài liệu mô tả command FCV có thể retry khi không hoàn tất vì idempotent trong ngữ cảnh tương ứng. Tuy nhiên:

- Phải xác định đúng primary/mongos.
- Kiểm tra có ongoing transition hay lỗi khác.
- Không retry storm khi member unavailable hoặc index build chưa xong.
- Không chạy song song nhiều thay đổi FCV vì nghĩ “retry được”.

---

## 19. FCV trong trạng thái chuyển tiếp

Khi FCV thay đổi, không phải lúc nào mọi thành viên có trạng thái ổn định ngay.

Có thể thấy:

```javascript
{
  featureCompatibilityVersion: {
    version: "7.0",
    targetVersion: "8.0"
  }
}
```

Đây là **cấu trúc minh họa** về một trạng thái trung gian; schema output chi tiết phụ thuộc MongoDB version.

### 19.1. Nếu command thất bại giữa chừng

Không tự sửa tài liệu nội bộ FCV trong `admin.system.version` bằng `updateOne`.

Nên:

1. Giữ logs và command result.
2. Xem `getParameter` trả trạng thái gì.
3. Kiểm tra majority và replica set health.
4. Kiểm tra background operations, initial sync, schema/index requirements.
5. Theo hướng dẫn chính thức của release đang dùng, retry command hoặc khôi phục quá trình transition.
6. Liên hệ Support nếu trạng thái bất thường không có runbook rõ.

### 19.2. Initial sync và FCV

MongoDB khuyến nghị **không đổi FCV khi initial sync đang chạy**; lệnh có thể làm initial sync restart hoặc gây lỗi tương thích lúc replay oplog.

### 19.3. Index build đang chạy

Từ các release mới như 9.0, `setFeatureCompatibilityVersion` có thể fail sớm nếu một index build đang chạy. Trước khi thao tác FCV, lên kế hoạch tránh concurrent index builds/maintenance.

---

## 20. Trường hợp MongoDB 8.3: điểm khác cần nhận biết

Không áp lệnh của 7.0/8.0 cho mọi MongoDB 8.x release vì FCV và downgrade policy đã thay đổi.

Theo tài liệu mới:

- Bắt đầu **8.3**, đường downgrade phiên bản liền kề được hỗ trợ theo điều kiện của từng release.
- `setFeatureCompatibilityVersion` có thêm tùy chọn `dryRun` ở 8.3 để đánh giá dữ liệu không tương thích trong một số bước nâng/hạ FCV.
- Không dùng `dryRun` trong lệnh minh họa 7.0 → 8.0 vì cú pháp này không tồn tại như một khả năng chung trên mọi bản cũ.
- Cần theo tài liệu riêng của 8.2/8.3 nếu chạy trong chuỗi 8.x.

### 20.1. Ý tưởng dry-run ở bản hỗ trợ

Ví dụ **chỉ cho release hỗ trợ**:

```javascript
db.adminCommand({
  setFeatureCompatibilityVersion: "<supported-target>",
  confirm: true,
  dryRun: true
});
```

`"<supported-target>"` là placeholder. **Không chạy** lệnh này khi chưa biết đích FCV hợp lệ và server version thực tế.

### 20.2. Dry-run không thay restore drill

Một dry-run giúp sớm phát hiện dữ liệu không tương thích, nhưng không chứng minh:

- Driver ứng dụng tương thích.
- Binary downgrade sẽ thành công.
- KMS/backup restore ổn.
- App latency/consistency đáp ứng SLA.
- Mọi external tool hoạt động.

---

## 21. Nâng cấp sharded cluster: trình tự khác replica set đơn

Một sharded cluster có:

```text
                      Applications
                           |
                     mongos routers
                           |
              +------------+------------+
              |                         |
         Shard replica set A       Shard replica set B
              |
              +---- Config Server Replica Set (CSRS)
```

Với **MongoDB 7.0 → 8.0**, tài liệu chính thức chỉ rõ thứ tự:

1. Tạm dừng **balancer**.
2. Nâng **config server replica set**.
3. Nâng **mỗi shard replica set**, từng shard một.
4. Nâng **mongos routers**.
5. Bật lại **balancer**.
6. Khi tất cả binary đã đồng bộ và burn-in xong, nâng **FCV qua mongos**.

**Không được áp thứ tự “nâng shard bất kỳ trước rồi mongos, sau cùng config server”**. Compatibility giữa router, config metadata và shards rất quan trọng.

---

## 22. Tạm dừng balancer trong sharded cluster

Kết nối tới một `mongos`:

```javascript
sh.stopBalancer();
```

Kiểm tra:

```javascript
sh.getBalancerState();
sh.isBalancerRunning();
```

Ý nghĩa:

- `sh.getBalancerState()` cho biết balancer được bật/tắt.
- `sh.isBalancerRunning()` giúp biết có balancing operation đang chạy hay không theo semantics của release.
- Nếu migration đang thực hiện, việc tắt balancer có thể chờ hoạt động đó hoàn tất.

### 22.1. Tại sao tạm dừng balancer?

Chunk migrations/placement changes trong lúc nâng metadata và binary có thể gây trạng thái phức tạp hoặc ảnh hưởng thời gian rollout.

### 22.2. Không tắt quá lâu vô điều kiện

Một cluster có dữ liệu liên tục tăng có thể mất cân bằng phân bố khi balancer bị tắt lâu. Ghi nhận thời điểm tắt và kế hoạch bật lại sau upgrade.

### 22.3. Các hoạt động sharding khác

Dù tắt balancer, vẫn cần kiểm soát:

- Resharding.
- Shard add/remove.
- FCV transition.
- Index builds đang chạy.
- DDL/collection migration lớn.
- Background restores/backups.

Tránh trộn nhiều thay đổi topology với major version upgrade nếu chưa có runbook hỗ trợ.

---

## 23. Nâng Config Server Replica Set (CSRS)

Config servers lưu metadata quan trọng của sharded cluster. Theo quy trình 7.0 → 8.0:

1. Nâng các CSRS SECONDARIES từng node một.
2. Sau mỗi node chờ `SECONDARY` và đủ majority.
3. Step down CSRS PRIMARY.
4. Nâng former CSRS PRIMARY.
5. Xác minh CSRS healthy, cùng binary version.

### 23.1. Vì sao CSRS phải trước shards?

Router/shard operations phụ thuộc config metadata. MongoDB quy định thứ tự để tránh kết hợp binary và metadata không được hỗ trợ.

### 23.2. Không coi CSRS là replica set nghiệp vụ bình thường về chức năng

CSRS còn quản lý sharding metadata, nên outage/upgrade của nó có thể ảnh hưởng routing và cluster metadata operations.

### 23.3. Config shard ở các phiên bản mới

MongoDB 8.0+ có các khái niệm config shard / dedicated config server; một số đường nâng/hạ có điều kiện riêng cho topology này.

**Không làm theo các bước dedicated CSRS nếu topology đang là config shard mà không kiểm tra hướng dẫn release cụ thể.**

---

## 24. Nâng shard replica sets

Với từng shard:

1. Kiểm tra shard đang healthy, có PRIMARY và secondaries đồng bộ.
2. Nâng shard SECONDARIES lần lượt.
3. Step down shard PRIMARY.
4. Nâng former shard PRIMARY.
5. Chờ toàn bộ shard trở lại healthy và replication lag đạt ngưỡng.
6. Tiếp tục shard kế tiếp.

```text
CSRS all 8.0

Shard A:
  A1 primary 7.0
  A2 secondary 7.0
  A3 secondary 7.0

Step 1 A2 -> 8.0
Step 2 A3 -> 8.0
Step 3 stepdown A1
Step 4 A1 -> 8.0

Then Shard B ... 
```

### 24.1. Không nâng mọi shard primary cùng lúc

Dù mỗi shard có majority độc lập, nhiều elections đồng thời có thể làm ứng dụng nhận lỗi rộng khắp. Rolling per-shard giúp hạn chế blast radius và dễ điều tra regressions.

### 24.2. Replication lag theo từng shard

Không có một giá trị lag tổng nào thay cho theo dõi từng replica set. Một shard có lag lớn có thể bị ảnh hưởng bởi bộ dữ liệu/index hoặc hardware khác.

---

## 25. Nâng mongos và bật lại balancer

Sau khi CSRS và **tất cả shards** chạy 8.0 theo trình tự được hỗ trợ, nâng các `mongos`:

1. Chọn router không phục vụ hoặc ít traffic trước.
2. Drain/constrain incoming requests nếu có load balancer.
3. Thay binary `mongos`.
4. Khởi động lại và kiểm tra routing/query.
5. Chuyển sang router kế tiếp.
6. Xác nhận tất cả routers đã chạy target version.

### 25.1. Tại sao không để mongos cũ mãi?

Tài liệu cảnh báo một `mongos` phiên bản 7.0 có thể **không kết nối được** với MongoDB 8.0 sharded cluster sau khi FCV được nâng lên 8.0. Trước đó với FCV 7.0 có khả năng tương thích tạm thời theo điều kiện.

Vì vậy **tất cả mongos phải được nâng trước khi nâng FCV**.

### 25.2. Bật lại balancer

Sau khi binary phase ổn định:

```javascript
sh.startBalancer();
```

Theo dõi migrations và shard balancing. Không để balancer tắt quên sau maintenance.

---

## 26. FCV trên sharded cluster

Khác với replica set đơn, trên sharded cluster lệnh FCV được thực hiện thông qua **mongos**:

```javascript
db.adminCommand({
  setFeatureCompatibilityVersion: "8.0",
  confirm: true
});
```

Điều kiện:

- Tất cả config servers, shards và mongos đã chạy binary được hỗ trợ.
- Không còn initial sync/rollback/major background operations gây xung đột.
- Có backup và rollback/restore plan.
- Đã qua burn-in.
- Admin đã phê duyệt bật FCV mới.

### 26.1. Hệ quả

- Có thể cập nhật metadata/config liên quan trên shards.
- Cần majority propagation.
- Trong lúc lệnh chạy, chunk migrations/splits/merges có thể gặp `ConflictingOperationInProgress` theo release.
- Không nên để một `mongos` cũ ở ngoài topology mà hệ thống giám sát không biết.

### 26.2. Kiểm tra thành công

- Lệnh FCV trả thành công.
- Mọi shard và config server đã có FCV mục tiêu.
- Không có transition kéo dài.
- Routing, sharded queries, transactions và balancing hoạt động bình thường.

---

## 27. Mức độ gián đoạn: standalone, replica set và sharded cluster

| Topology | Đường nâng cấp | Khả năng gián đoạn |
| --- | --- | --- |
| Standalone | Stop → replace binary → start | Có downtime theo kế hoạch |
| Replica set | Secondary từng node → stepdown primary → former primary | Giảm downtime; election có thể ngắt writes ngắn |
| Sharded cluster | CSRS → shards → mongos theo release procedure | Có thể giữ phục vụ; nhiều điểm cần kiểm soát |
| Atlas managed | UI/API hoặc Auto Upgrades | Nền tảng quản lý rollout; app vẫn cần retry/monitor |
| Ops Manager/Cloud Manager | Automation deployment procedures | Không dùng manual steps bất chấp automation |

### 27.1. Không nâng standalone bằng “rolling”

Standalone chỉ có một `mongod` giữ dữ liệu. Nếu dừng nó để thay binary, dịch vụ không sẵn sàng, trừ khi có chiến lược migration/topology khác.

### 27.2. Rolling không loại bỏ rủi ro client-visible

Dù server có majority, client vẫn có thể thấy:

- `NotWritablePrimary`.
- `InterruptedDueToReplStateChange`.
- Network timeout.
- Transient transaction errors.
- Cursor invalidation.
- Read preference rerouting.

Cần xử lý tại driver/application đúng semantics.

---

## 28. Java MongoDB Sync Driver: sẵn sàng cho election

Với ứng dụng Java:

```java
import com.mongodb.ConnectionString;
import com.mongodb.MongoClientSettings;
import com.mongodb.ReadConcern;
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public final class MongoClientFactory {

    public static MongoClient createClient(
            String uri
    ) {
        ConnectionString cs =
            new ConnectionString(uri);

        MongoClientSettings settings =
            MongoClientSettings.builder()
                .applyConnectionString(cs)
                .retryWrites(true)
                .readConcern(ReadConcern.MAJORITY)
                .writeConcern(WriteConcern.MAJORITY)
                .build();

        return MongoClients.create(settings);
    }
}
```

Đây là ví dụ client configuration, **không phải bảo đảm mọi operation tự retry thành công**. `retryWrites` hỗ trợ những thao tác đủ điều kiện và yêu cầu server/driver phù hợp. Transactions, bulk operations, custom application commands và side effects có retry semantics riêng.

### 28.1. Không tự retry mọi lệnh ghi mà không có idempotency

Nếu API đặt hàng:

1. Trừ tiền ở payment gateway.
2. Ghi order vào MongoDB.
3. Nhận timeout trong lúc stepdown.
4. Client retry toàn bộ request.

Nếu code thực hiện lại bước 1 mà không có idempotency key, người dùng có thể bị thu tiền hai lần. MongoDB retryable writes **không tự làm external payment call trở nên idempotent**.

### 28.2. Kết nối bằng replica set URI

Ví dụ:

```text
mongodb://nodeA:27017,nodeB:27017,nodeC:27017/
  ?replicaSet=rs0&retryWrites=true
```

Trong code thực tế, URI phải viết thành một dòng và quản lý secrets an toàn. Không gắn chết ứng dụng vào một node primary duy nhất nếu deployment đã có replica set.

---

## 29. Theo dõi các signals trong rolling upgrade

| Nhóm | Metrics nên theo dõi |
| --- | --- |
| Availability | PRIMARY có tồn tại, members healthy |
| Replication | Lag, oplog window, majority availability |
| Write behavior | Write errors, writeConcern timeouts, retry counts |
| Read behavior | Read errors, stale reads theo readPreference |
| Latency | p50/p95/p99 của query và HTTP APIs |
| Performance | CPU, WiredTiger cache, IOPS, storage latency |
| Topology | Elections, stepdown count, restarts |
| Resources | Disk free, RAM, connections, open file handles |
| Transactions | Commit/abort/retry rate |
| Drivers | Pool checkout timeout, reconnects, topology changes |
| Logs | Startup warnings, incompatible config/feature errors |
| Sharding | Balancer state, chunk migrations, targeted reads |
| Backup | Snapshot/PITR state, archive lag |
| Search | MongoDB Search/Vector Search index readiness |
| Security | TLS/KMIP/KMS availability, audit alerts |

### 29.1. Theo dõi theo từng node

Không chỉ xem cluster average. Một secondary mới nâng có thể có CPU/disk behavior khác, trong khi primary cũ vẫn ổn. Khi node ấy lên primary, regression mới lộ rõ.

### 29.2. Có ngưỡng dừng rollout

Ví dụ policy:

```text
Stop upgrade if:
  - no healthy majority,
  - replication lag exceeds agreed threshold,
  - persistent write errors,
  - p99 latency breaches SLO for sustained interval,
  - backup/restore capability is lost,
  - a newly upgraded node fails to stay SECONDARY,
  - KMS/TLS or authentication fails.
```

Ngưỡng cụ thể phải được xác định cho ứng dụng, không sao chép tùy ý.

---

## 30. “Hạ phiên bản” thực sự gồm các trường hợp nào?

Có bốn tình huống rất khác nhau:

| Tình huống | Trạng thái | Hướng xử lý |
| --- | --- | --- |
| Binary mới đã cài trên **một secondary**, FCV cũ | Mixed-version upgrade đang dang dở | Dừng rollout, sửa lỗi hoặc dùng rollback được release hỗ trợ |
| Tất cả binaries mới, FCV cũ | Binary phase hoàn tất, chưa bật incompatible features | Có thể có đường hạ nếu edition/release hỗ trợ; kiểm tra policy |
| FCV mới đã bật, dữ liệu/features mới đã được ghi | Backward-incompatible data có thể tồn tại | Cần dọn features, hạ FCV đúng quy trình và kiểm tra support |
| Đường binary downgrade không được hỗ trợ | Dù FCV cũ có thể còn | Sử dụng bản vá/restore/support-approved migration, không force-start binary cũ |

### 30.1. Những cách rollback không an toàn

- Dừng MongoDB 8.0 rồi thay executable 7.0, giữ nguyên data directory mà không theo tài liệu.
- Dùng `--repair` để “ép database xuống version cũ”.
- Cập nhật thủ công `admin.system.version` để đổi FCV.
- Xóa index/collection có vẻ “mới” mà không biết phụ thuộc của ứng dụng.
- Restore trực tiếp vào production mà không ghi nhận writes hợp lệ sau snapshot.
- Hạ toàn cluster đồng thời để “tiết kiệm downtime”.

---

## 31. Chính sách downgrade của các dòng MongoDB

Một điều kiện cực kỳ quan trọng: **khả năng downgrade là chính sách theo release và edition**, không chỉ là tính toán version số học.

### 31.1. Từ MongoDB 7.0 đến những bản 8.0

Tài liệu Downgrade 8.0 to 7.0 ghi:

- **Binary downgrades không được hỗ trợ cho MongoDB Community Edition**.
- **MongoDB Enterprise cần trợ giúp từ MongoDB Support** để downgrade binary.
- Chỉ hỗ trợ downgrade một phiên bản liền kề theo chính sách của dòng.
- Cần loại bỏ dữ liệu/tính năng không tương thích trước khi hạ FCV/binary.

Do đó, ngay cả khi một 8.0 cluster đang ở FCV 7.0, **không thể suy ra Community được phép hạ binary 8.0→7.0** bằng một command.

### 31.2. Bắt đầu từ MongoDB 8.3

Tài liệu hiện hành công bố downgrade về **minor hoặc major liền kề** theo các đường hỗ trợ. Ví dụ 9.0→8.3 có quy trình cụ thể với downgrade FCV và loại bỏ tính năng mới.

Đây **không phải** giấy phép hạ 9.0→6.0 hoặc cho phép mọi topology bằng cách copy data files.

### 31.3. 9.0 có các đường khác nhau

MongoDB có những trang hướng dẫn riêng cho 9.0→8.3 và một số đường tới 8.0 theo điều kiện, không nên tự ghép các bước ở hai trang.

Một runbook phải chọn đúng:

- Source patch version.
- Target patch version.
- FCV đích hợp lệ.
- Replica set vs standalone vs sharded cluster.
- Self-managed vs Atlas.
- Features incompatibility list.

---

## 32. FCV downgrade khác binary downgrade

Giả sử đang chạy MongoDB 9.0 binary + FCV 9.0 và cần về 8.3 theo quy trình được hỗ trợ.

**Thứ tự khái niệm**:

```text
9.0 binary + 9.0 FCV
         |
         | remove 9.0 incompatible features/data
         v
9.0 binary + 8.3 FCV
         |
         | follow supported rolling binary downgrade
         v
8.3 binary + 8.3 FCV
```

Không đảo thứ tự thành:

```text
9.0 binary + 9.0 FCV
         |
         | replace binaries first
         v
8.3 binary + 9.0 FCV   <-- có thể không tương thích
```

### 32.1. Tại sao phải dọn incompatible features?

FCV kiểm soát một số tính năng và persisted formats, nhưng không tự xóa dữ liệu/index/metadata đã tạo bằng tính năng mới.

Ví dụ nhóm điều kiện cần rà soát theo release:

- Index types/index options mới.
- Collection configuration/schema validators không tương thích.
- Time-series data/catalog changes.
- Queryable Encryption/CSFLE metadata requirements.
- Sharding/config shard topology features.
- New catalog/config fields.
- Storage/index features không được server cũ hiểu.
- Các tham số startup/feature flags không còn hợp lệ khi hạ.

**Không thực hiện xóa một feature mới khi chưa xác định dữ liệu nghiệp vụ phụ thuộc**; thường phải migrate hoặc export dữ liệu có kiểm soát trước.

---

## 33. Ví dụ có điều kiện: downgrade 9.0 replica set về 8.3

Đây là **mẫu diễn giải thứ tự**, không phải runbook production hoàn chỉnh.

### Giai đoạn A — prerequisites

1. Xác nhận đang theo đúng tài liệu **Downgrade 9.0 Replica Set to 8.3**.
2. Xác minh source/target patch releases.
3. Backup và restore rehearsal.
4. Đảm bảo tất cả replica set members đang chạy/healthy.
5. Xem danh sách 9.0 backward-incompatible features và xử lý.
6. Đảm bảo không initial sync, no `newlyAdded`, no member in `ROLLBACK`/`RECOVERING`.
7. Kiểm tra quyền admin/management indexes.
8. Lên maintenance window và quan sát liên tục.

### Giai đoạn B — hạ FCV trước

Trên primary của 9.0:

```javascript
db.adminCommand({
  setFeatureCompatibilityVersion: "8.3",
  confirm: true
});
```

Đợi completion, kiểm tra trên mọi members:

```javascript
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
```

Kỳ vọng FCV `"8.3"` ở mọi member.

### Giai đoạn C — hạ binaries theo thủ tục

Theo hướng dẫn 9.0→8.3 replica set:

1. Dùng binary 8.3 patch phù hợp.
2. Hạ các secondaries lần lượt và chờ `SECONDARY` sau mỗi node.
3. Nếu có arbiter, tuân thủ **bước arbiter chuyên biệt** được mô tả cho downgrade; không dùng tùy tiện quy trình của data-bearing member.
4. Step down primary cũ.
5. Hạ former primary sau khi primary mới được bầu.
6. Kiểm tra version/FCV, replication, query tests và backup.

Không sao chép bước xóa thư mục của **arbiter** sang data-bearing members: điều đó có thể phá hủy dữ liệu.

### 33.1. Tại sao cần target patch mới nhất?

Các hướng dẫn downgrade thường yêu cầu patch release mới nhất trong target series được hỗ trợ, nhằm giảm lỗi compatibility và nhận fixes.

---

## 34. Downgrade FCV có phải “Undo tất cả” không?

**Không.**

`setFeatureCompatibilityVersion` thay đổi điều kiện sử dụng các tính năng không tương thích, và có thể ghi metadata nội bộ. Nó không tự:

- Undo business writes.
- Xóa mọi index mới không tương thích.
- Đưa application schema trở về phiên bản cũ.
- Phục hồi dữ liệu đã bị xóa.
- Khôi phục backup.
- Đảm bảo binary cũ có thể đọc data files.
- Rollback Search/Vector Search indexes.
- Rollback Kafka events, payments hoặc hệ thống ngoài.

### 34.1. Nếu command báo CannotDowngrade

Nguyên nhân có thể là **persisted backward-incompatible data/features** vẫn tồn tại.

Cách xử lý:

1. Đọc đầy đủ lỗi và danh sách blockers.
2. Đối chiếu release downgrade documentation.
3. Xác định feature/data bị ảnh hưởng.
4. Thiết kế migration hoặc loại bỏ feature có kiểm soát.
5. Test trên staging/restored backup.
6. Chỉ retry khi prerequisites đã đạt.

**Không** xóa bất kỳ data không tương thích nào một cách tùy tiện chỉ để command pass.

---

## 35. Atlas upgrade: cơ chế quản lý khác self-managed

MongoDB Atlas quản lý cluster infrastructure, maintenance và nhiều bước binary rollout.

Tùy deployment:

- **Manual Upgrades:** chủ sở hữu cluster chọn major target và thời điểm.
- **Auto Upgrades:** Atlas có thể tự áp dụng release upgrades theo release track/maintenance windows.
- **FCV trên Auto Upgrades:** Atlas quản lý việc nâng FCV theo cơ chế nền tảng.
- **Atlas Core/Infinite:** có release cadence và feature availability khác nhau.

### 35.1. Không SSH thay mongod trên Atlas

Không có quy trình thay binary từng host bằng package manager của khách hàng khi cluster do Atlas quản lý. Dùng Atlas UI/API và hướng dẫn “Change/Upgrade Major MongoDB Version”.

### 35.2. FCV và “point of no return” trên Atlas

Tài liệu MongoDB Versions and Upgrade Paths nêu: khi FCV trên Atlas được nâng và các tính năng ghi dữ liệu theo định dạng mới được bật, **downgrade không còn khả dụng trên Atlas** theo mô hình upgrade đó.

Vì vậy, trước khi chọn target release và chế độ Auto Upgrades, cần hiểu:

- Người vận hành còn kiểm soát burn-in/FCV hay không?
- Khi nào Atlas tự nâng FCV?
- Khi xảy ra regression, rollback path hợp lệ là gì?
- Có cần restore vào cluster khác thay vì downgrade?
- Có maintenance window và backup/PITR phù hợp?

### 35.3. Atlas rollback phải dựa trên capability thực tế

Đừng nói “Atlas luôn hỗ trợ downgrade một nút” hoặc “restore từ snapshot sẽ giữ mọi writes” khi không có bằng chứng. Hãy sử dụng documentation/Support cho instance đang vận hành.

---

## 36. Ops Manager/Cloud Manager: không phá automation state

Nếu deployment self-managed đang do **Ops Manager** hoặc **Cloud Manager** tự động quản lý:

- Thay đổi phiên bản qua Automation/Upgrade workflows của công cụ.
- Không tự restart/nâng từng node bằng shell nếu automation sẽ tự ghi đè config.
- Kiểm tra agent version, backup agent, automation version và compatibility.
- Đọc maintenance requirements và supported upgrade target.
- Không bật FCV thủ công ngoài workflow khi công cụ quản lý có yêu cầu khác.

### 36.1. “Self-managed” không có nghĩa không dùng automation

Có thể server chạy trong data center của tổ chức nhưng upgrade do automation vận hành. Về mặt quyền điều khiển, phải thống nhất **một nguồn sự thật** cho version và FCV.

---

## 37. Compatibility của ứng dụng và drivers

Những thay đổi cần kiểm chứng:

| Lớp | Ví dụ |
| --- | --- |
| Drivers | Java Sync Driver, Node.js, Python, Go compatibility |
| Connection setup | TLS versions, SCRAM mechanisms, authSource |
| Commands | Deprecated/removed commands hoặc options |
| Queries | Behavioral changes, collation, aggregation semantics |
| Indexes | New types/features, planner behavior |
| Transactions | Error labels, retry semantics, majority availability |
| Change Streams | Resume behavior sau restart/election |
| Time-series | Schema/catalog/FCV-specific changes |
| Sharding | Router/config metadata compatibility |
| Search | mongot/Atlas Search and Vector Search compatibility |
| Backup | Ops Manager/Database Tools compatibility |
| External consumers | Connectors, CDC, BI, ETL, monitoring |

### 37.1. Không chỉ test database connection

Một app có thể kết nối thành công nhưng fail khi:

- Tạo index.
- Chạy aggregation có operators đổi behavior.
- Mở transaction.
- Dùng Change Streams resume token.
- Thực hiện bulk writes.
- Truy cập Search/Vector Search.
- Kết nối dưới TLS/key rotation setup.
- Chạy migration scripts.

Do đó test suite phải bao gồm representative queries và writes.

---

## 38. Stable API không thay FCV

MongoDB có **Stable API** để giúp ứng dụng dựa trên bộ command/behavior có cam kết tương thích theo API version.

Ví dụ Java:

```java
import com.mongodb.MongoClientSettings;
import com.mongodb.ServerApi;
import com.mongodb.ServerApiVersion;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;

public final class MongoClientWithStableApi {

    public static MongoClient create(String uri) {
        ServerApi api = ServerApi.builder()
            .version(ServerApiVersion.V1)
            .strict(true)
            .deprecationErrors(true)
            .build();

        MongoClientSettings settings =
            MongoClientSettings.builder()
                .applyConnectionString(
                    new com.mongodb.ConnectionString(uri)
                )
                .serverApi(api)
                .build();

        return MongoClients.create(settings);
    }
}
```

### 38.1. Stable API giúp gì?

- Giảm rủi ro phụ thuộc vào những features không nằm trong API ổn định.
- Có chế độ strict/deprecation checking.
- Hỗ trợ giữ application behavior cho những API được định nghĩa.

### 38.2. Stable API không giúp gì?

- Không thay binary upgrade prerequisites.
- Không thay FCV.
- Không bảo đảm mọi performance regression biến mất.
- Không giúp driver tương thích nếu server release không hỗ trợ driver đó.
- Không biến transaction/external side effect thành idempotent.
- Không cho phép binary downgrade trái policy.

---

## 39. Mô hình rollout theo môi trường

Một lộ trình tổ chức hợp lý:

```text
Development
   |
   v
Staging with production-like data
   |
   v
DR/backup restore rehearsal
   |
   v
Canary/less-critical production cluster
   |
   v
Main production clusters
   |
   v
FCV enablement after burn-in
```

### 39.1. Đừng dùng dữ liệu staging quá nhỏ

Nếu production có:

- 500 GiB dữ liệu.
- 100 indexes.
- 10.000 requests/s.
- Complex multi-shard transactions.
- Change Streams và Search.

mà staging chỉ có 100 documents, bạn không thể kiểm chứng tương đương về latency, index builds, disk pressure hay replication.

### 39.2. Có data migration/tính năng mới?

Đừng làm đồng thời:

- Major MongoDB upgrade.
- Major driver upgrade.
- Schema migration.
- New sharding key.
- Authentication change.
- FCV enablement.
- Background massive index builds.

Nếu có thể, tách thành waves để dễ tìm nguyên nhân khi lỗi.

---

## 40. Nâng cấp ảnh hưởng đến backup và PITR thế nào?

Một MongoDB deployment thường được backup bằng:

- Atlas Cloud Backup/PITR.
- Ops Manager/Cloud Manager backup.
- Filesystem snapshots.
- Third-party tools.
- `mongodump`/`mongorestore`.

### 40.1. FCV và backup compatibility

Sau khi bật features mới/FCV mới:

- Backup mới có thể chứa định dạng không tương thích với server cũ.
- Restore sang một cluster version thấp hơn có thể bị hạn chế.
- Một số PITR ranges có thể bị giới hạn qua FCV/catalog changes.
- Nếu dùng Search indexes hoặc encrypted metadata, có thể cần rebuild/khóa tương thích.

### 40.2. Chọn snapshot trước bước có rủi ro

Khuyến nghị:

1. Tạo backup/điểm khôi phục trước binary upgrade.
2. Xác nhận backup restoration hoạt động.
3. Ghi lại mốc trước FCV enablement.
4. Giữ rollback/restore runbook tương ứng với từng giai đoạn.
5. Không xóa key versions hoặc backups cũ ngay sau nâng.

### 40.3. Backups phải phục hồi được bằng key

Nếu backup/volume được mã hóa bởi CMK, KMS key bị vô hiệu/xóa có thể làm restore thất bại dù snapshot vẫn tồn tại. Version upgrade plan phải bao gồm KMS/certificates/secret management.

---

## 41. MongoDB Search và các thành phần phụ khi nâng cấp

Nếu ứng dụng dùng MongoDB Search/Vector Search hoặc một dịch vụ đồng bộ derived indexes:

- Kiểm tra compatibility với MongoDB binary/version/FCV.
- Xem Search index definitions có được giữ/rebuild khi restore hoặc thay cluster không.
- Giám sát mongot/Atlas Search node availability.
- Không giả định query Search có cùng latency khi MongoDB nodes đang stepdown/restore.
- Tách thử nghiệm Search regression khỏi schema/index migrations nếu có thể.

### 41.1. Derived indexes có thể cần thời gian riêng

Một database restore hoặc upgrade infrastructure hoàn tất không tự chứng minh mọi Search index đã READY. Cần kiểm tra Search readiness theo công cụ tương ứng và tính vào RTO/maintenance.

---

## 42. FCV và tính năng không tương thích ngược: ví dụ tư duy

Giả sử phiên bản N có tính năng mới thay đổi cách lưu metadata trong index:

```text
Binary N+1 có thể đọc:
   old format
   new format

Binary N có thể đọc:
   old format
   nhưng không hỗ trợ new format

FCV=N:
   giữ đường ghi format cũ cho những features bị gate

FCV=N+1:
   cho phép ghi format mới
```

Nếu application đã dùng feature mới để ghi data:

```text
Existing persisted data: new format
Attempt to start old binary: unsafe/unsupported
```

Do đó **thay FCV xuống** có thể cần loại bỏ hoặc chuyển đổi **đối tượng persisted mới** trước.

### 42.1. Không phải mọi feature mới đều chờ FCV

Một số optimizations hoặc behavior changes không nhất thiết phụ thuộc FCV. Vì vậy burn-in vẫn cần test kể cả khi FCV cũ.

---

## 43. Tình huống lỗi: secondary 8.0 không vào SECONDARY

Giả sử B restart sau nâng binary và báo lỗi:

```text
B state: STARTUP2 / RECOVERING / down
Primary A: still healthy
Secondary C: healthy
```

Cần:

1. **Dừng rollout**.
2. Giữ A/C, không tắt thêm nodes.
3. Xem MongoDB process logs và startup config.
4. Kiểm tra dbPath ownership, certificates, keyfile/KMIP.
5. Kiểm tra binary/FCV và patch compatibility.
6. Xem oplog window/initial sync conditions.
7. Phục hồi B theo hướng dẫn chính thức.
8. Chỉ tiếp tục khi B ổn định.

Không làm:
- Xóa dbPath một cách tùy tiện.
- Hạ binary không thuộc đường hỗ trợ.
- Chỉnh raw system collections.
- Bắt A/C cùng restart để “đồng bộ”.

---

## 44. Tình huống lỗi: primary stepdown nhưng chưa bầu được primary mới

Tình huống:

```text
A đã step down
B/C không đủ điều kiện election hoặc bị replication lag
Không có PRIMARY
```

Nguyên nhân có thể:

- Majority không khả dụng.
- Voting/priority config bất thường.
- B/C chưa theo kịp.
- Network partition.
- TLS/internal authentication failure.
- Một member RECOVERING.
- Configuration đang transition.

### 44.1. Cách xử lý

- Theo dõi `rs.status()`.
- Xác minh mạng/TLS, majority và election messages.
- Không thay đổi cấu hình voting tùy tiện khi chưa biết hậu quả.
- Dùng incident runbook và DBA/on-call escalation.

### 44.2. Vì sao không chỉ “force primary”?

Các thao tác ép reconfig/election không phù hợp có thể gây split-brain assumptions hoặc tăng rủi ro rollback dữ liệu chưa được xác nhận. Ưu tiên duy trì đúng semantics của replica set.

---

## 45. Tình huống lỗi: đã bật FCV mới nhưng muốn quay về

Tình huống:

```text
All binary: 8.0
FCV:        8.0
New features already used
Application regression found
```

**Sai lầm:** chỉ chạy:

```javascript
// Không coi đây là full rollback recipe:
db.adminCommand({
  setFeatureCompatibilityVersion: "7.0",
  confirm: true
});
```

rồi thay binary 7.0.

Cần làm đúng:

1. Xem chính sách binary downgrade 8.0→7.0 cho edition.
2. Xem danh sách persisted backward-incompatible features.
3. Với Enterprise 8.0, làm việc với MongoDB Support theo tài liệu.
4. Với Community 8.0, không tự thực hiện binary downgrade vì không được hỗ trợ.
5. Nếu không có đường downgrade, cân nhắc forward fix hoặc restore/migration bằng deployment tương thích.
6. Giữ dữ liệu và backup để điều tra, không force-start binary cũ.

### 45.1. Tắt feature mới không tự chuyển dữ liệu

Một feature flag OFF có thể dừng writes mới nhưng đã tồn tại các documents/indexes cấu trúc mới. FCV downgrade hoặc binary downgrade cần những prerequisites cụ thể khác.

---

## 46. Tình huống: lỗi performance sau nâng nhưng không phải incompatibility

Giả sử:

```text
Before: MongoDB 7.0, p95 query = 25 ms
After:  MongoDB 8.0, p95 query = 80 ms
FCV:    7.0
```

Các giả thuyết:

- Query planner chọn plan khác.
- Index/statistics/workload thay đổi.
- Cache lạnh sau restart.
- Storage I/O backlog từ initial sync/rebuild.
- Driver pool behavior thay đổi.
- Search/index build đang chạy.
- Thay cấu hình hệ điều hành hoặc VM tier cùng lúc.
- Application traffic spike.

**Hướng xử lý**:

- So sánh query shapes/explain.
- Xem disk/cache/CPU/network metrics.
- Kiểm tra topology/connection pools.
- Dùng plan inspection/hint/index experiment có kiểm soát.
- Cân nhắc bugfix patch hoặc support escalation.
- Không coi binary downgrade là thao tác đầu tiên nếu release policy chặn.

---

## 47. Tình huống: FCV upgrade thất bại vì index build

Một index build đang chạy trên collection lớn. Lệnh FCV có thể bị chặn bởi background operations theo release.

### 47.1. Giám sát công việc đang chạy

```javascript
db.currentOp();
```

Hoặc:

```javascript
db.adminCommand({
  currentOp: 1
});
```

Cần quyền thích hợp và hiểu những operations/namespace được trả về. Không tự kill index build chỉ vì FCV cần chạy ngay.

### 47.2. Lựa chọn

- Chờ index build hoàn tất.
- Đánh giá khả năng an toàn của việc hủy build theo business impact.
- Lên lịch FCV khi không có DDL/major background operations.
- Retry có kiểm soát theo lỗi cụ thể.

---

## 48. Hạ phiên bản với Sharded Cluster

Downgrade sharded cluster có prerequisites nhạy cảm hơn:

- FCV trên sharded topology.
- Config server/shard/router version compatibility.
- Balancer state.
- Shard placement metadata và chunk migrations.
- Những tính năng topology mới như config shards.
- Resharding/unshard operations hoặc catalog changes.
- Tình trạng tất cả replica sets.

### 48.1. Không tự đảo thứ tự upgrade

Thứ tự downgrade của từng release có thể khác về chi tiết. Không suy luận “upgrade CSRS→shards→mongos, vậy downgrade chỉ cần mongos→shards→CSRS” nếu không đọc trang downgrade chính thức.

### 48.2. Config shard có thể cần chuyển cấu hình

Trên một số đường FCV downgrade, tài liệu MongoDB yêu cầu chuyển sang dedicated config server trước khi giảm FCV dưới mốc nhất định.

Không tự thực hiện thay đổi config shard trong production chỉ bằng một ví dụ rút gọn; đó là topology transition cần quy trình riêng.

### 48.3. Mongos và FCV

Bảo đảm mọi routers tương thích với FCV thực tế trước khi chuyển version. Không giữ router cũ bị bỏ sót ngoài load balancer/monitoring.

---

## 49. Hạ phiên bản và thao tác migration dữ liệu

Nếu phải bỏ một cấu trúc mới không tương thích:

1. Xác định đối tượng cụ thể.
2. Chụp backup/snapshot trước migration.
3. Lập phương án chuyển dữ liệu sang định dạng cũ.
4. Kiểm tra quyền và invariants nghiệp vụ.
5. Test migration trên bản clone.
6. Tính thêm disk/memory/IOPS cho migration.
7. Thực hiện trong maintenance window.
8. Kiểm tra counts/checksums/indexes.
9. Mới hạ FCV theo procedure được hỗ trợ.
10. Mới hạ binaries nếu edition/release cho phép.

### 49.1. Không xóa index mới mà chưa xét unique constraints

Một index mới có thể bảo vệ tính duy nhất hoặc hỗ trợ query quan trọng. Xóa nó để qua preflight có thể:

- Cho phép duplicate data.
- Làm query chậm.
- Ảnh hưởng application invariants.
- Gây tăng I/O.

Cần lựa chọn index hoặc schema tương đương trên phiên bản đích.

---

## 50. Có nên duy trì phiên bản cũ và mới song song?

Trong một số tổ chức, thay vì downgrade trực tiếp data files, có thể:

```text
Old version cluster          New version cluster
       |                            ^
       |                            |
       +---- data migration --------+
       |
       +---- application canary
```

Một quy trình side-by-side migration có thể tạo lựa chọn cutover/rollback traffic có kiểm soát, nhưng:

- Cần initial sync hoặc migration tool được hỗ trợ.
- Cần quản lý writes xảy ra trong lúc dual running.
- Không đảm bảo bidirectional sync giữa hai versions.
- Change stream/history và schema compatibility quan trọng.
- Có thể cần freeze writes lúc cutover.
- Cần rollback data plan, không chỉ rollback DNS.

**Không coi dual-write cho hai versions là chuyện đơn giản.** Dual writes có thể tạo inconsistency nếu một bên thành công và bên kia lỗi.

---

## 51. Quyết định downgrade hay forward-fix

Sau khi upgrade phát sinh lỗi, có các lựa chọn:

| Lựa chọn | Khi nào phù hợp | Rủi ro |
| --- | --- | --- |
| **Fix config/query** | Hành vi mới có thể điều chỉnh an toàn | Cần chẩn đoán đúng |
| **Upgrade patch** | Lỗi đã được khắc phục ở patch mới | Thêm deployment change |
| **Disable app feature** | Feature ứng dụng gây regression | Có thể giảm chức năng |
| **Restore/cutover** | Bản sao cũ hợp lệ, kiểm soát data loss | Cần reconciliation |
| **Supported downgrade** | Có đường rõ và prerequisites đạt | Phức tạp, outage/compatibility |
| **Support-assisted downgrade** | Bản release yêu cầu vendor support | Phụ thuộc incident coordination |
| **Forward migration** | Data đã không tương thích với binary cũ | Có thể tốn thời gian và resources |

Không có quy tắc “đã nâng thất bại là phải hạ ngay”. Hướng ít rủi ro nhất phụ thuộc mức độ nghiêm trọng, dữ liệu đã ghi và các giới hạn hỗ trợ.

---

## 52. Vai trò của feature flags ở ứng dụng

Một chiến lược giảm rủi ro là không bật ngay tính năng ứng dụng sử dụng server features mới.

Ví dụ cấu hình giả định:

```yaml
application:
  mongoFeatures:
    useNewServerCapability: false
    enableNewIndexPattern: false
```

Sau khi binary và FCV đều ổn định mới bật:

```yaml
application:
  mongoFeatures:
    useNewServerCapability: true
    enableNewIndexPattern: true
```

### 52.1. Đây không phải cú pháp MongoDB

Đó là manifest giả định của ứng dụng, không phải `mongod.conf` hoặc API feature flags của MongoDB.

### 52.2. Vì sao hữu ích?

- Không bật behavior mới ngay trong mixed-version period.
- Dễ canary theo nhóm traffic/tenant.
- Có thể tắt feature ứng dụng nhanh nếu lỗi.
- Giảm số biến thay đổi cùng lúc.

**Nhưng:** tắt application flag sau khi đã ghi persisted data không tự làm data cũ tương thích với binary cũ.

---

## 53. Các chỉ số thành công của một upgrade

Một major upgrade không chỉ thành công khi command trả `ok: 1`.

Định nghĩa các mục tiêu:

| Mục tiêu | Bằng chứng |
| --- | --- |
| Binary đúng version | `buildInfo`/effective process versions |
| FCV đúng dự kiến | `getParameter` trên members |
| Availability | PRIMARY tồn tại, secondaries healthy |
| Durability | Majority writes, replication lag và backup |
| Application | Critical APIs pass smoke/integration tests |
| Query performance | p95/p99 không vượt SLO |
| Transactions | Commit/abort behavior ổn |
| Sharding | Router compatibility, balancer chạy đúng |
| Security | Authentication/TLS/KMS healthy |
| Backup | Snapshot/PITR pipeline hoạt động, restore plan còn hợp lệ |
| Monitoring | Alerting/logs không có errors kéo dài |
| Rollback posture | Biết rõ downgrade còn được hỗ trợ hay không |
| Documentation | Runbook được cập nhật với source/target/FCV |

### 53.1. Success không có nghĩa không có log warning nào

Một upgrade có thể sinh một số warning tạm thời trong mixed-version window. Cần phân loại mức ảnh hưởng, không vì mọi warning mà force rollback. Nhưng những lỗi liên quan FCV/catalog/data corruption/replication phải được xử lý ngay.

---

## 54. Bài tập thực hành — kiểm tra trạng thái

### Bài 1: binary và FCV

Một node có:

```text
Binary: 8.0
FCV:    7.0
```

**Hỏi:** Có chắc đó là lỗi?

**Đáp án:** Không. Đây có thể là trạng thái có chủ đích sau binary upgrade, trước khi nâng FCV.

### Bài 2: FCV nâng quá sớm

Replica set còn một secondary 7.0; những nodes khác đã 8.0. Team muốn bật FCV 8.0.

**Đáp án:** Không. Hoàn tất nâng tất cả members và xác nhận ổn định trước khi đổi FCV.

### Bài 3: thứ tự replica set

Ba members A primary, B/C secondaries.

**Đáp án:** Nâng B rồi C lần lượt, chờ healthy, stepdown A, nâng former primary A, rồi mới xét FCV.

### Bài 4: stepdown

Sau `rs.stepDown()`, kết nối shell báo network/primary error.

**Đáp án:** Có thể là behavior do election; kết nối lại và kiểm tra new primary, không tự coi toàn bộ deployment hỏng.

### Bài 5: đa số

Một secondary đã mất trước maintenance, team muốn tắt secondary còn lại.

**Đáp án:** Dừng nâng cấp; có nguy cơ mất majority và write availability.

### Bài 6: Sharded cluster

Team định nâng các `mongos` lên 8.0 trước mọi shards/config servers trong lộ trình 7→8.

**Đáp án:** Không theo thứ tự chính thức; 7→8 yêu cầu CSRS → shards → mongos, có bước tắt/bật balancer.

### Bài 7: FCV qua đâu?

Sharded cluster đã nâng xong binaries.

**Đáp án:** Thực hiện `setFeatureCompatibilityVersion` thông qua một `mongos` được hỗ trợ.

### Bài 8: retry FCV

Lệnh FCV bị timeout nhưng không rõ thực hiện tới đâu.

**Đáp án:** Đọc trạng thái FCV, kiểm tra health/logs, sau đó retry theo hướng dẫn idempotency nếu phù hợp; không tự sửa system collection.

### Bài 9: Community 8.0 downgrade

Team chạy Community 8.0/FCV 7.0 và muốn thay binary 7.0.

**Đáp án:** Không được kết luận hỗ trợ. Tài liệu 8.0→7.0 không hỗ trợ Community binary downgrade.

### Bài 10: Enterprise 8.0 downgrade

Team dùng Enterprise 8.0 và muốn hạ về 7.0.

**Đáp án:** Tài liệu yêu cầu liên hệ MongoDB Support; không tự thực hiện như quy trình tự do.

### Bài 11: 9.0→8.3

Team đã dùng một feature 9.0 có persisted format không tương thích 8.3.

**Đáp án:** Phải loại bỏ/chuyển đổi feature/data theo tài liệu trước khi hạ FCV/binary.

### Bài 12: Atlas Auto Upgrades

Team muốn tự giữ FCV thấp 30 ngày trên cluster Atlas Auto Upgrades.

**Đáp án:** Không tự giả định có quyền này; Atlas quản lý FCV theo release process của Auto Upgrades.

### Bài 13: FCV 9.0 và 8.3

Một cluster self-managed 9.0 có FCV 9.0; cần downgrade về 8.3.

**Đáp án:** Xem procedure riêng 9.0→8.3, dọn incompatible features, hạ FCV 8.3, verify mọi members rồi hạ binary theo thứ tự được hỗ trợ.

### Bài 14: data backup

Backup đã thành công nhưng key KMS cũ bị hủy.

**Đáp án:** Backup có thể không giải mã được. Kế hoạch upgrade/rollback phải bao gồm key lifecycle.

### Bài 15: backup sau upgrade

Team khôi phục snapshot mới chứa feature 9.0 vào binary 8.3.

**Đáp án:** Không được giả định restore tương thích. Cần xem snapshot/version/FCV và feature formats.

### Bài 16: driver connection

Ứng dụng chỉ kết nối một PRIMARY cụ thể bằng hostname cố định.

**Đáp án:** Dễ lỗi khi election. Dùng replica set connection string/driver server discovery đúng.

### Bài 17: external payment

Trong lúc upgrade, API retry toàn request có gọi payment gateway.

**Đáp án:** Cần idempotency cho external side effect; retryable writes không bảo vệ payment calls.

### Bài 18: Search

MongoDB nodes upgraded xong nhưng Search trả dữ liệu chưa đầy đủ.

**Đáp án:** Xem Search service/index readiness, synchronization và compatibility, không chỉ status mongod.

### Bài 19: cache

Sau nâng/restart, p99 tăng trong 10 phút rồi giảm.

**Đáp án:** Có thể do cache warm-up. Đo disk/cache, không vội kết luận version regression.

### Bài 20: build index đang chạy

`setFeatureCompatibilityVersion` bị chặn bởi background index build.

**Đáp án:** Chờ hoặc xử lý build theo runbook, tránh retry storm; các release mới có preflight chặt hơn.

### Bài 21: downgrade mọi lúc

“Chỉ cần giữ FCV thấp thì có thể hạ binary bao nhiêu lần cũng được.”

**Đáp án:** Sai. Binary downgrade phụ thuộc release/edition/path và persisted features.

### Bài 22: thay trực tiếp dbPath

Một admin định lấy dbPath từ MongoDB 8.0 rồi chạy MongoDB 7.0 binary để “undo”.

**Đáp án:** Không an toàn/không được mặc định hỗ trợ. Phải theo official downgrade procedure hoặc backup restoration.

### Bài 23: version số học

Từ 7.0 muốn chạy thẳng một bản 9.x mà không xem upgrade path.

**Đáp án:** Cần đối chiếu roadmap version và upgrade paths; các bước trung gian/FCV có thể bắt buộc.

### Bài 24: migration cùng upgrade

Team muốn cùng một maintenance window: major upgrade, resharding, schema migration, bật FCV và build 10 indexes.

**Đáp án:** Rủi ro rất cao. Tách waves để giảm concurrent change và dễ rollback/chẩn đoán.

---

## 55. Checklist tiền nâng cấp (preflight)

- [ ] Đã xác nhận source binary/FCV từng node?
- [ ] Đã chọn target release và patch version được hỗ trợ?
- [ ] Đã đọc đúng upgrade procedure theo standalone/replica set/sharded?
- [ ] Đã kiểm tra release notes, deprecations và compatibility changes?
- [ ] Đã kiểm tra driver/ORM/framework/tool compatibility?
- [ ] Đã xác nhận OS/CPU/storage/TLS/KMS requirements?
- [ ] Có restore-tested backup/PITR?
- [ ] Có change ticket, on-call, rollback/restore runbook?
- [ ] Có maintenance window và truyền thông ứng dụng?
- [ ] Replica set healthy, majority available?
- [ ] Không initial sync/rollback/RECOVERING kéo dài?
- [ ] Oplog window và replication lag ổn?
- [ ] Có đủ disk/IOPS/headroom?
- [ ] Đã lưu baseline p50/p95/p99, errors, throughput?
- [ ] Đã thử trên staging với workload đại diện?
- [ ] Có kiểm tra index builds/long-running operations?
- [ ] Đã cân nhắc Search/Vector Search/CDC/connectors?
- [ ] Có plan không sử dụng features mới trong mixed-version window?
- [ ] Nếu sharded: đã biết thứ tự CSRS→shards→mongos?
- [ ] Nếu Atlas: đã hiểu Manual vs Auto Upgrades và FCV ownership?

---

## 56. Checklist trong rolling upgrade

- [ ] Mỗi lần chỉ ngừng một member theo runbook.
- [ ] Nâng SECONDARY trước, chờ đồng bộ.
- [ ] Không tiếp tục nếu node mới ở RECOVERING/ROLLBACK quá lâu.
- [ ] Kiểm tra version thực của node sau restart.
- [ ] Không chỉnh sửa dbPath/system collections thủ công.
- [ ] Kiểm tra TLS/auth/KMS sau mỗi restart.
- [ ] Có healthy majority trước stepdown.
- [ ] Chỉ nâng former primary sau election ổn định.
- [ ] Theo dõi ứng dụng khi node mới lên PRIMARY.
- [ ] Với sharded cluster: balancer và router được quản lý đúng.
- [ ] Tất cả nodes/routers có binary mục tiêu trước FCV enablement.
- [ ] Đã ghi lại marker thời điểm hoàn tất binary phase.
- [ ] Đang giữ FCV cũ trong giai đoạn burn-in theo policy.
- [ ] Không bật features mới chưa được approval.
- [ ] Dừng rollout khi SLO/availability bị vi phạm.

---

## 57. Checklist nâng FCV

- [ ] Đã qua burn-in và app tests?
- [ ] Cluster healthy, no initial sync đang chạy?
- [ ] Không có background index build/DDL gây xung đột?
- [ ] Đã biết FCV target hợp lệ theo version?
- [ ] Mọi binaries đã chạy release tương thích?
- [ ] Có kế hoạch cho mất khả năng binary downgrade?
- [ ] Đã có backup/restoration path phù hợp?
- [ ] Đã kiểm tra release-specific incompatible features?
- [ ] Có phê duyệt nâng FCV?
- [ ] Chạy `confirm: true` trên primary hoặc mongos phù hợp?
- [ ] Đã verify FCV trên tất cả members?
- [ ] Không còn intermediate `targetVersion`?
- [ ] Đã test features cần FCV mới?
- [ ] Đã cập nhật runbook/monitoring và baseline?

---

## 58. Checklist hạ phiên bản

- [ ] Đường downgrade có được **release/edition hỗ trợ** không?
- [ ] Đã đọc đúng official procedure cho source→target?
- [ ] Nếu Enterprise release yêu cầu, đã liên hệ MongoDB Support?
- [ ] Đã lưu backup và thử restore trước downgrade?
- [ ] Tất cả members/shards/routers healthy?
- [ ] Có danh sách backward-incompatible features cụ thể?
- [ ] Đã xử lý persisted incompatible features/data có kiểm soát?
- [ ] Đã xét topology config shard/dedicated config server?
- [ ] FCV target hợp lệ và đã hạ đúng thứ tự?
- [ ] Đã verify FCV trên toàn deployment?
- [ ] Không có initial sync/RECOVERING/ROLLBACK/newlyAdded?
- [ ] Có target binaries đúng patch release?
- [ ] Có riêng các bước arbiter nếu tài liệu yêu cầu?
- [ ] Có quy trình rolling binary downgrade đúng topology?
- [ ] Có kế hoạch sửa application driver/feature flags?
- [ ] Có kiểm chứng dữ liệu và critical APIs sau downgrade?
- [ ] Có rollback-of-downgrade/restore plan nếu bước hạ lỗi?
- [ ] Có giữ backup và audit logs trước/sau?

---

## 59. Những ngộ nhận dễ gây sự cố

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Nâng binary là đã nâng FCV.” | Hai bước riêng biệt. |
| “FCV luôn bằng version của mongod.” | Sau binary upgrade, FCV thường giữ version cũ đến khi nâng. |
| “FCV cũ biến binary mới thành binary cũ.” | Runtime/behavior vẫn có thể thay đổi. |
| “FCV mới chỉ sửa một string.” | Có thể ghi metadata/cho phép persisted incompatible features. |
| “FCV có thể đổi ngay giữa initial sync.” | Có thể restart/fail initial sync; nên tránh. |
| “Chỉ cần một primary healthy là đủ khi nâng.” | Phải duy trì majority/quorum và write concern. |
| “Rolling upgrade không gây request error.” | Election/reconnect có thể tạo transient errors. |
| “Nâng các secondaries song song càng nhanh càng tốt.” | Dễ mất majority hoặc gây replication lag. |
| “Thay binary primary trước vì nó quan trọng nhất.” | Với replica set thường nâng secondaries trước. |
| “Stepdown luôn vô hình với application.” | Client cần retry/discovery đúng. |
| “MongoClient kết nối một hostname primary là đủ.” | Replica set URI/discovery mới thích hợp cho failover. |
| “Tất cả versions đều có đường downgrade giống nhau.” | Phụ thuộc release/edition/topology. |
| “MongoDB Community 8→7 chỉ cần giảm FCV.” | Binary downgrade không hỗ trợ trong chính sách 8.0→7.0. |
| “Enterprise 8→7 tự downgrade thoải mái.” | Cần MongoDB Support theo tài liệu. |
| “Bắt đầu 8.3 thì muốn hạ bao nhiêu release cũng được.” | Chỉ đường liền kề được hỗ trợ. |
| “Hạ FCV là tự xóa mọi dữ liệu không tương thích.” | Phải xử lý persisted features/data riêng. |
| “Chạy binary cũ trên dbPath mới là an toàn.” | Có thể không tương thích, hỏng dữ liệu. |
| “Backup thành công là restore chắc được.” | Cần restore rehearsal và keys/version compatibility. |
| “Rollback database sẽ rollback payment/Kafka.” | External side effects cần reconciliation. |
| “Sharded cluster có thể nâng mongos trước tất cả.” | Thứ tự 7→8: CSRS→shards→mongos. |
| “Bật FCV khi còn mongos cũ vẫn ổn.” | Router cũ có thể không tương thích FCV mới. |
| “Balancer tắt rồi không cần bật lại.” | Có thể gây imbalance lâu dài. |
| “Config shard giống dedicated CSRS ở mọi version.” | Có topology-specific procedures. |
| “Nâng xong là không cần monitor.” | Burn-in và post-upgrade validation rất quan trọng. |
| “Stable API thay FCV.” | Hai cơ chế mục đích khác nhau. |
| “Retryable writes làm mọi request idempotent.” | External side effects vẫn cần idempotency. |
| “Patch release nào cũng chỉ sửa UI.” | Có thể sửa server/driver behavior, cần release notes. |
| “Thấy serverStatus healthy thì app chắc đúng.” | Cần business/transaction/search integration tests. |
| “Có thể nâng đồng thời binary, FCV và schema để tiết kiệm thời gian.” | Tăng blast radius và khó tìm nguyên nhân. |
| “Báo lỗi sau upgrade thì giải pháp đầu tiên là downgrade.” | Forward fix/support restore có thể an toàn hơn. |

---

## 60. Runbook rút gọn cho bài thực hành 7.0 → 8.0 replica set

**Chỉ thực hiện trên staging/lab hoặc có phê duyệt production**.

```text
PREPARE
  1. Backup + restore test
  2. Release/driver compatibility
  3. All members 7.0, FCV 7.0
  4. Replica healthy + majority
  5. Baseline metrics

ROLLING BINARIES
  6. Secondary B: stop -> 8.0 -> start -> healthy
  7. Secondary C: stop -> 8.0 -> start -> healthy
  8. rs.stepDown() on primary A
  9. Wait for new PRIMARY
 10. Former primary A: stop -> 8.0 -> start -> healthy

BURN-IN
 11. Confirm all 8.0 binaries, FCV still 7.0
 12. Run app smoke/integration tests
 13. Monitor errors, p99, replication, backup

ENABLE FCV
 14. Approve compatibility boundary
 15. Run setFeatureCompatibilityVersion "8.0"
 16. Verify FCV 8.0 on all members

CLOSE
 17. Validate application and operations
 18. Update runbook/backup plan/metrics
```

Đây là lược đồ học tập; cần xem tài liệu MongoDB 8.0 cụ thể và thêm commands/kiểm tra theo deployment thực tế.

---

## 61. Tài liệu tham khảo chính thức

Các liên kết dưới đây nhằm giúp đối chiếu version-specific behavior:

1. [MongoDB Versions and Upgrade Paths](https://www.mongodb.com/docs/mongodb-versions/) — release cadence, binary upgrade vs FCV và Atlas/self-managed.
2. [Upgrade a Replica Set to 8.0](https://www.mongodb.com/docs/v8.0/release-notes/8.0-upgrade-replica-set/) — 7.0→8.0, SECONDARIES trước, stepdown, FCV.
3. [Upgrade a Sharded Cluster to 8.0](https://www.mongodb.com/docs/v8.0/release-notes/8.0-upgrade-sharded-cluster/) — balancer, CSRS, shards, mongos, FCV.
4. [setFeatureCompatibilityVersion](https://www.mongodb.com/docs/manual/reference/command/setFeatureCompatibilityVersion/) — syntax, confirm, dryRun từ 8.3, hành vi transition.
5. [Downgrade 8.0 to 7.0](https://www.mongodb.com/docs/v8.0/release-notes/8.0-downgrade/) — chính sách Community/Enterprise.
6. [Upgrade Replica Set to 9.0](https://www.mongodb.com/docs/manual/release-notes/9.0-upgrade-replica-set/) — upgrade procedure cho đường nguồn tương ứng.
7. [Upgrade 8.0 Replica Set to 9.0](https://www.mongodb.com/docs/manual/release-notes/9.0-upgrade-from-8.0-replica-set/) — một đường nâng cụ thể.
8. [Upgrade 8.0 Sharded Cluster to 9.0](https://www.mongodb.com/docs/manual/release-notes/9.0-upgrade-from-8.0-sharded-cluster/) — config servers, shards, mongos và FCV.
9. [Downgrade 9.0 Replica Set to 8.3](https://www.mongodb.com/docs/manual/release-notes/9.0-downgrade-replica-set/) — prerequisites, FCV và binary downgrade.
10. [Downgrade 9.0 to 8.0](https://www.mongodb.com/docs/manual/release-notes/9.0-downgrade-to-8.0/) — đường khác có điều kiện riêng.
11. [Replica Set Status](https://www.mongodb.com/docs/manual/reference/method/rs.status/) — kiểm tra members/health.
12. [Replica Set Step Down](https://www.mongodb.com/docs/manual/reference/method/rs.stepDown/) — tác động election.
13. [FCV Compatibility Reference](https://www.mongodb.com/docs/manual/reference/command/getParameter/) — truy vấn effective parameters.
14. [Upgrade Major MongoDB Version for an Atlas Cluster](https://www.mongodb.com/docs/atlas/tutorial/major-version-change/) — quy trình Atlas managed.
15. [MongoDB Release Notes](https://www.mongodb.com/docs/manual/release-notes/) — compatibility changes và prerequisites.
16. [Java Sync Driver Compatibility](https://www.mongodb.com/docs/drivers/java/sync/current/compatibility/) — driver/server version matrix.
17. [MongoDB Server Stable API](https://www.mongodb.com/docs/manual/reference/stable-api/) — cam kết API và giới hạn.
18. [MongoDB Backup Methods](https://www.mongodb.com/docs/manual/core/backups/) — backup/restore cho self-managed.
19. [Sharded Cluster Balancer](https://www.mongodb.com/docs/manual/core/sharding-balancer-administration/) — quản lý balancing trong maintenance.
20. [MongoDB Operations Checklist](https://www.mongodb.com/docs/manual/administration/production-notes/) — triển khai production và các ràng buộc vận hành.

**Lưu ý:** MongoDB đổi chính sách release cadence và downgrade giữa các dòng 8.x/9.x. Một số trang documentation có thể được render theo version selector hoặc thay đổi nội dung theo release. Khi dùng tài liệu cho production, khóa đúng đường dẫn/version selector và xác minh chính xác support matrix, không chỉ dựa vào một trang “current”.

---

## 62. Kết luận

**Nâng cấp lần lượt** trong MongoDB tập trung vào việc giữ replica set hoặc sharded cluster đủ healthy/majority khi thay binaries, đặc biệt nâng **SECONDARIES trước**, rồi step down và nâng former PRIMARY. Với sharded cluster, có trình tự phụ thuộc **config servers → shards → mongos** theo quy trình của release.

**Feature Compatibility Version** là bước quyết định khi nào deployment cho phép sử dụng những tính năng có thể ghi dữ liệu không tương thích ngược. Binary 8.0 vẫn có thể chạy với FCV 7.0 trong burn-in, nhưng nâng FCV lên 8.0 có thể làm đường downgrade khó hơn. FCV không phải công tắc hoàn nguyên toàn bộ dữ liệu.

**Hạ phiên bản** là một quyết định riêng chịu ràng buộc bởi release, edition, topology, persisted features và chính sách MongoDB. Các dòng 8.0 và 8.3/9.0 có khác biệt đáng kể; không được thay binary cũ trực tiếp lên data directory mới chỉ vì muốn rollback.

Một kế hoạch nâng cấp tốt cần **backup có kiểm chứng, đường nâng hợp lệ, driver/app compatibility tests, baseline metrics, healthy majority, giai đoạn burn-in, FCV enablement có phê duyệt, và restore/downgrade runbook thực sự được hỗ trợ**.

**Nâng cấp thành công không chỉ là chạy đúng phiên bản mới; đó là chuyển toàn bộ hệ thống sang trạng thái mới mà vẫn kiểm soát được tính sẵn sàng, tính toàn vẹn dữ liệu, hiệu năng và khả năng phục hồi.**
