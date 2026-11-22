# Đối chiếu edition, tính năng, option và management pack trước khi sử dụng Oracle Database

## 1. Vì sao phải đối chiếu trước khi triển khai?

Oracle Database có nhiều khả năng được **cài đặt sẵn, xuất hiện trong giao diện quản trị hoặc trả về trạng thái `TRUE`**, nhưng quyền được sử dụng chúng phụ thuộc vào **edition**, **phiên bản/release**, **mô hình triển khai**, **option/management pack được cấp quyền** và **điều khoản hợp đồng**. Một câu lệnh chạy thành công không chứng minh rằng việc dùng tính năng đó đã được cấp phép.

Ví dụ, hai máy chủ cùng chạy Oracle Database Enterprise Edition (EE) có thể có quyền sử dụng khác nhau:

- Máy A có quyền dùng EE cơ bản, chưa mua Oracle Partitioning hoặc Diagnostics Pack.
- Máy B có EE, Oracle Partitioning và Diagnostics Pack được cấp phép theo phạm vi thích hợp.

Một bảng partition hoặc báo cáo AWR có thể chạy được trên cả hai máy, nhưng **không được suy ra** rằng cả hai máy đều có quyền sử dụng. Ngoài ra, tính năng được bao gồm trong một dịch vụ Oracle Cloud cụ thể chưa chắc được bao gồm khi sử dụng giấy phép on-premises theo hình thức Bring Your Own License (BYOL).

**Mục tiêu học tập:** Sau bài này, bạn có thể xác định chính xác môi trường Oracle đang xét, phân biệt *feature* với *option* và *management pack*, đọc bảng quyền sử dụng trong tài liệu chính thức, kiểm tra các dấu hiệu kỹ thuật một cách an toàn và lập quyết định **cho phép / chưa cho phép / cần xác minh thêm** trước khi triển khai.

> **Phạm vi:** Đây là hướng dẫn kỹ thuật để ra quyết định và thu thập bằng chứng. Quyền sử dụng cuối cùng phải đối chiếu với hợp đồng, đơn hàng, chính sách cấp phép áp dụng cho hệ thống và **Licensing Information User Manual của đúng release**. Không dùng bài học như một bản xác nhận giấy phép hay bảng giá.

## 2. Năm lớp thông tin cần tách biệt

| Lớp | Câu hỏi phải trả lời | Ví dụ |
| --- | --- | --- |
| **Database offering / edition** | Đang chạy sản phẩm nào? | Standard Edition 2 (SE2), Enterprise Edition (EE), Oracle AI Database Free, EE trên engineered systems |
| **Release và môi trường** | Phiên bản nào, triển khai ở đâu? | Oracle Database 19c on-premises, Oracle AI Database 26ai trên OCI Base Database Service, OCI BYOL |
| **Feature** | Muốn dùng khả năng cụ thể nào? | Tạo partition, mở standby chỉ đọc trong khi redo vẫn được apply, tạo báo cáo AWR |
| **Option** | Feature này có thuộc một option được cấp phép riêng không? | Oracle Partitioning, Active Data Guard, Advanced Security, Advanced Compression, Real Application Clusters (RAC) |
| **Management pack** | Thao tác quản trị/giám sát có cần một pack riêng? | Oracle Diagnostics Pack, Oracle Tuning Pack, các pack quản trị khác trong Enterprise Manager |

**Edition** là phạm vi sản phẩm cơ sở. **Feature** là hành vi cụ thể. **Option** mở rộng nhóm năng lực thường phải mua thêm trên EE on-premises. **Management pack** là quyền dùng một nhóm công cụ, báo cáo, API hoặc màn hình quản trị. Việc dùng một API trực tiếp có thể vẫn thuộc cùng pack với việc nhấn nút tương ứng trong Enterprise Manager.

Quan hệ cần suy luận là:

```text
Nhu cầu nghiệp vụ
    │
    ▼
Feature / thao tác cụ thể
    │
    ▼
Tài liệu Licensing Information của đúng release
    │
    ├── Có sẵn trong offering/edition? ──► Kiểm tra giới hạn & điều kiện
    │
    ├── Thuộc option? ────────────────────► Xác minh quyền option
    │
    └── Thuộc management pack? ──────────► Xác minh quyền pack & điều kiện tiên quyết
    │
    ▼
Hợp đồng + mô hình triển khai + phạm vi máy chủ/processor/user
    │
    ▼
Quyết định và ghi bằng chứng trước khi bật/sử dụng
```

Không được bỏ qua bước giữa với giả định “có EE là có tất cả” hoặc “giao diện hiển thị thì được phép dùng”.

## 3. Xác định đúng offering trước khi đọc bảng tính năng

### 3.1. Các loại thường gặp

| Offering | Ý nghĩa trong thực tế | Điểm cần kiểm tra |
| --- | --- | --- |
| **SE2** | Edition cho các ứng dụng có quy mô và yêu cầu phù hợp giới hạn của SE2 | Giới hạn kỹ thuật, phương thức cấp phép, các tính năng chỉ dành cho EE; không mặc nhiên có option của EE |
| **EE on-premises** | Edition mở rộng, phục vụ workload và yêu cầu cao hơn | EE **không đồng nghĩa** đã mua mọi extra-cost option và pack |
| **EE trên engineered systems** | EE chạy trên Exadata/Oracle Database Appliance hoặc tổ hợp được Oracle định nghĩa | Khả năng và điều kiện cấp phép khác nhau theo hệ thống, cần cột **EE-ES** và chú thích cụ thể |
| **Oracle AI Database Free / các bản Free, XE theo release** | Sản phẩm miễn phí với điều khoản, giới hạn tài nguyên và danh mục tính năng riêng | Đọc đúng điều khoản Free/XE của release, không áp dụng tùy tiện chính sách EE/SE2 |
| **OCI Database Service** | Dịch vụ quản lý có tier như Base Database Service SE, EE, EE-HP, EE-EP; Exadata Database Service | Mỗi tier có danh mục option/pack **được bao gồm** khác nhau; phân biệt license-included với BYOL |
| **Triển khai đám mây khác / BYOL** | Phần mềm và quyền sử dụng đưa lên một môi trường khác | Kiểm tra chính sách cloud và phạm vi quyền BYOL phù hợp; không áp dụng cột dịch vụ OCI một cách máy móc |

Tài liệu **Oracle AI Database 26ai** hiện liệt kê các cột như `Free`, `SE2`, `EE`, `EE-ES`, `BaseDB SE`, `BaseDB EE`, `BaseDB EE-HP`, `BaseDB EE-EP`, `ExaDB`. Chẳng hạn, một option có thể là *extra cost* với EE on-premises nhưng *included* trong một tier OCI. Tài liệu **19c** có danh mục offering khác (bao gồm các offering theo thời điểm release đó); do vậy cần mở đúng manual thay vì ghép các bảng của hai phiên bản.

### 3.2. Định vị thời điểm và phạm vi cấp phép

Trước khi duyệt feature, ghi tối thiểu:

1. **Phiên bản đang chạy:** release và bản cập nhật, ví dụ `19c` cùng Release Update hoặc `26ai`.
2. **Offering:** SE2, EE, EE-ES, Free hay tên service/tier OCI cụ thể.
3. **Nơi chạy:** bare metal, máy ảo, cluster, engineered system hoặc cloud; môi trường production, DR, test hay dev.
4. **Quyền đã mua/được cấp:** tài liệu đơn hàng, hợp đồng, SKU/entitlement, điều khoản BYOL hoặc mục included trong dịch vụ.
5. **Phạm vi tính quyền:** các máy, processor/core, user, môi trường standby/DR và thời gian sử dụng theo hợp đồng.

Các metric như **Processor** và **Named User Plus** hoặc chính sách partitioning/virtualization có thể thay đổi cách xác định phạm vi cần cấp phép. Không thể kết luận đủ license chỉ bằng cách đếm CPU trong `V$OSSTAT` hay đọc tên edition. Cần áp dụng điều khoản và chính sách Oracle có hiệu lực cho triển khai cụ thể.

## 4. Cách đọc ma trận quyền sử dụng của Oracle

Trong *Licensing Information User Manual*, tìm phần **Permitted Features, Options, and Management Packs by ... Offering**. Tài liệu 26ai giải thích:

- **`Y`**: khả năng được liệt kê là khả dụng cho offering đó, **không nhất thiết miễn phí**; phải đọc cột `Notes` xem có yêu cầu option/pack hay điều kiện khác.
- **`N`**: không khả dụng trong offering tương ứng.
- **`N/A`**: không áp dụng trong ngữ cảnh của cột đó.
- **`Extra cost option/pack`**: phải có quyền sử dụng sản phẩm bổ sung tương ứng.
- **`Included option/pack`**: được bao gồm trong offering được chỉ rõ, nhưng vẫn phải tuân thủ giới hạn, điều khoản dịch vụ và trường hợp BYOL.

Một bảng tổng hợp giúp *biết nên kiểm tra mục nào*; nó không thay thế manual. Bảng dưới đây lấy **EE/SE2 on-premises** làm ví dụ phổ biến và chỉ nêu quyền cơ bản của các mục tiêu biểu theo manual hiện hành; khi làm việc phải kiểm tra đúng release:

| Nhu cầu / feature | EE on-premises | SE2 on-premises | Điều cần nhận diện |
| --- | --- | --- | --- |
| `CREATE TABLE` thông thường, transaction, index B-tree | Khả năng cơ sở | Khả năng cơ sở | Vẫn kiểm tra các tính năng nâng cao trong DDL, cấu hình hoặc driver sử dụng |
| **Table partitioning** | Thường yêu cầu **Oracle Partitioning** extra-cost option | Không có Oracle Partitioning option tương ứng | Partition table/index khác với chỉ thiết kế cột ngày và tạo index |
| **RAC nhiều instance** | Thường yêu cầu **Oracle RAC** extra-cost option | Không có RAC của EE | RAC khác Data Guard và không tương đương mọi dạng HA |
| **Data Guard Redo Apply** | Có khả năng Data Guard cơ bản trong EE | Không khả dụng | Phân biệt standby với **Active Data Guard** có tính năng mở rộng |
| **Active Data Guard** | Thường yêu cầu **Active Data Guard** extra-cost option | Không khả dụng | Ví dụ: truy vấn physical standby trong khi redo đang được apply |
| **TDE cột/tablespace** | Thường yêu cầu **Advanced Security** extra-cost option | Không khả dụng như một option SE2 on-premises | Khác với mã hóa mạng TLS/native network encryption |
| **Advanced Row/LOB Compression** | Thường yêu cầu **Advanced Compression** extra-cost option | Không khả dụng | Đừng gom Basic Table Compression, một số chế độ RMAN/Data Pump vào cùng quy tắc |
| **In-Memory Column Store** | Thường yêu cầu **Database In-Memory** option; có quy định riêng cho **In-Memory Base Level** | Không khả dụng | Kiểm tra giới hạn `INMEMORY_SIZE`, chế độ nén và từng release |
| **AWR/ADDM/ASH** | Thường yêu cầu **Diagnostics Pack** | Không được sử dụng pack như EE | Có một số ngoại lệ với view cụ thể; xem phần management pack |
| **SQL Tuning Advisor, SQL Profiles, Real-Time SQL Monitoring** | Thường yêu cầu **Tuning Pack**, và **Diagnostics Pack** là điều kiện tiên quyết | Không được sử dụng pack như EE | Truy cập bằng SQL, PL/SQL API hay giao diện vẫn cần kiểm tra license |

**Không áp dụng bảng này cho Oracle AI Database Free hoặc một tier OCI.** Ví dụ, tài liệu 26ai liệt kê **Oracle Partitioning, Advanced Compression, Advanced Security, Diagnostics Pack và Tuning Pack** trong các quyền được bao gồm cho `Free`, song Oracle AI Database Free có điều khoản sử dụng và giới hạn tài nguyên riêng. Tương tự, tier OCI cao hơn có thể bao gồm option nhưng tier khác thì không; BYOL có các quy định đặc thù cần đọc ở mục *Special License Rights*.

### Ví dụ: `Y` vẫn có thể cần mua thêm

Trong bảng tính năng 26ai, Oracle Partitioning có thể được đánh dấu `Y` ở cột `EE`, đồng thời cột ghi chú nói **EE and EE-ES: Extra cost option**. `Y` nói khả năng tồn tại cho edition, **không** nói mọi EE customer đã trả tiền cho option đó.

## 5. Những nhóm option dễ nhầm lẫn

### 5.1. Partitioning: thiết kế bảng khác quyền dùng partition

Về kỹ thuật, partitioning giúp chia dữ liệu thành nhiều phần theo range, list, hash hoặc tổ hợp; thường dùng để quản lý dữ liệu lớn, vòng đời dữ liệu và một số kiểu truy vấn. Tuy nhiên, **DDL dùng `PARTITION BY` trên EE on-premises** là yêu cầu cần đối chiếu Oracle Partitioning trước khi chạy.

```sql
-- Ví dụ minh họa cú pháp; KHÔNG chạy trên hệ thống chưa xác minh quyền Partitioning.
CREATE TABLE sales_events (
    event_id     NUMBER NOT NULL,
    event_date   DATE   NOT NULL,
    total_amount NUMBER(12, 2)
)
PARTITION BY RANGE (event_date) (
    PARTITION p_2026_h1 VALUES LESS THAN (DATE '2026-07-01'),
    PARTITION p_future VALUES LESS THAN (MAXVALUE)
);
```

Nếu chưa có quyền Oracle Partitioning, dùng thiết kế bảng thường, index phù hợp, lưu trữ/archive theo quy trình ứng dụng hoặc cân nhắc thay đổi offering sau khi đánh giá. Việc “bảng partition chạy được” không thay đổi điều khoản licensing.

### 5.2. Data Guard khác Active Data Guard

- **Oracle Data Guard** (ví dụ Redo Apply trên physical standby) là một nhóm cơ chế dự phòng và đồng bộ redo. Tính năng này có mặt trong EE theo bảng quyền của release.
- **Oracle Active Data Guard** bổ sung các khả năng được liệt kê trong option, điển hình **physical standby với real-time query** khi vẫn nhận/apply redo. Dùng khả năng đó trên EE on-premises thường cần extra-cost option.
- Điều kiện cấp quyền có thể liên quan **primary và các standby sử dụng tính năng Active Data Guard**. Không chỉ kiểm tra một server mà phải đối chiếu toàn bộ cấu hình.

Do đó, yêu cầu “có máy dự phòng” vẫn chưa đủ để quyết định dùng Data Guard hay Active Data Guard: cần mô tả **standby có mở đọc trong lúc apply hay không**, topology và SLA cụ thể.

### 5.3. Advanced Security khác mã hóa kết nối

**Transparent Data Encryption (TDE)** cho cột/tablespace, **mã hóa file Data Pump**, **mã hóa bản backup RMAN trên disk** và **Data Redaction** thuộc danh sách Oracle Advanced Security theo manual 26ai/19c. Trái lại, Oracle ghi rõ **network encryption, network integrity, TLS/SSL và một số cơ chế xác thực mạnh không còn thuộc Advanced Security option** trong các licensed edition của release được hỗ trợ.

Điều này có hai hệ quả:

1. Không từ chối thiết lập TLS chỉ vì thiếu Advanced Security khi tài liệu của release cho phép.
2. Không suy từ “đã bật TLS” rằng TDE cũng được cấp phép; đó là hai feature khác nhau.

Quyền TDE có thể được bao gồm hoặc được cấp đặc biệt trong một số offering OCI/BYOL. Cần kiểm tra đúng hàng và ghi chú, không dùng kết luận EE on-premises để áp lên OCI.

### 5.4. Advanced Compression: xác định chính xác chế độ

Oracle Advanced Compression bao gồm các khả năng như Advanced Row Compression, Advanced LOB Compression/Deduplication, một số kiểu nén RMAN, nén Data Pump, Advanced Index Compression và các tính năng liên quan. **Không phải mọi chữ `COMPRESS` trong Oracle đều là một license giống nhau.**

Ví dụ, manual 26ai ghi các ngoại lệ cụ thể: `RMAN DEFAULT COMPRESS` không yêu cầu Advanced Compression option và `COMPRESSION=METADATA_ONLY` trong Data Pump không yêu cầu option đó. Điều này **không** có nghĩa các kiểu backup/export compression khác đều miễn phí. Luôn so khớp đúng lệnh, tham số, thuật toán và chú thích của release.

### 5.5. Multitenant: đếm PDB và đọc giới hạn theo offering

Một **CDB** (container database) có thể chứa nhiều **PDB** (pluggable database). Số lượng PDB được phép không thể suy ra từ `MAX_PDBS` hay từ việc Oracle cho phép tạo PDB bằng SQL.

Ví dụ theo manual **26ai**:

- Không có quyền Oracle Multitenant bổ sung, các offering liên quan được phép có tối đa **3 PDB do người dùng tạo** trong mỗi CDB, theo điều kiện manual.
- Trên EE on-premises, Oracle Multitenant là **extra-cost option** nếu cần vượt phạm vi miễn option. Giới hạn theo option và hệ thống có thể khác giữa EE và EE-ES.
- `Free` được manual ghi là **included option** cho tối đa **16 PDB**, nhưng số PDB thực tế còn bị giới hạn bởi tài nguyên Free.
- `BaseDB EE-HP`, `EE-EP`, `ExaDB` có ghi chú riêng; trường hợp **BYOL** có thể giới hạn 3 PDB nếu không có Oracle Multitenant option.

Lưu ý số **PDB do người dùng tạo** và thành phần hệ thống như `PDB$SEED` không nên gộp tùy tiện. Đối với 19c hoặc release khác, phải đọc bảng tại release đó và mọi điều kiện phiên bản/bản cập nhật liên quan.

### 5.6. Database In-Memory và các ngoại lệ có giới hạn

Oracle Database In-Memory thường là option có phí riêng trên EE on-premises. Tuy nhiên manual 26ai cũng mô tả **Database In-Memory Base Level** để thử nghiệm với giới hạn như vùng in-memory tối đa **16 GB mỗi CDB** (mỗi instance trong RAC), chế độ nén cố định và một số khả năng bị vô hiệu hóa. Vì vậy, không nên kết luận mọi trường hợp `INMEMORY_SIZE > 0` đều giống nhau; cần xác minh đúng chế độ và giới hạn được phép.

## 6. Management pack: rủi ro đến từ công cụ quản trị

Một người dùng ứng dụng có thể không hề tạo partition hay bật RAC, nhưng DBA hoặc một bộ công cụ giám sát vẫn có thể vô tình dùng tính năng thuộc management pack. Đây là lý do bước kiểm tra license phải bao gồm **dashboard, script định kỳ, công cụ bên thứ ba và API**.

| Pack | Ví dụ khả năng tiêu biểu | Lưu ý |
| --- | --- | --- |
| **Diagnostics Pack** | Automatic Workload Repository (**AWR**) reports, Automatic Database Diagnostic Monitor (**ADDM**), Active Session History (**ASH**) và các API/view tương ứng | Trên EE on-premises thường là pack mua thêm; không phải mọi dữ liệu lịch sử đều dùng được miễn phí |
| **Tuning Pack** | SQL Tuning Advisor, SQL Access Advisor, SQL Profiles, Real-Time SQL Monitoring và API liên quan | Trên EE on-premises thường là pack mua thêm; **cần quyền Diagnostics Pack** trước |
| **Các Enterprise Manager pack khác** | Database Lifecycle Management, Data Masking and Subsetting, các tính năng quản trị theo từng pack | Phải xem riêng bảng của từng pack, offering, chức năng GUI/API và điều kiện license |

### 6.1. `CONTROL_MANAGEMENT_PACK_ACCESS` kiểm soát điều gì?

Tham số `CONTROL_MANAGEMENT_PACK_ACCESS` có ba giá trị:

| Giá trị | Khả năng pack được bật về mặt kỹ thuật |
| --- | --- |
| `NONE` | Tắt khả năng Diagnostics/Tuning được tham số này quản lý |
| `DIAGNOSTIC` | Bật nhóm Diagnostics, không bật Tuning |
| `DIAGNOSTIC+TUNING` | Bật cả hai nhóm |

Theo **Oracle Database 19c Database Reference**, mặc định cho EE là `DIAGNOSTIC+TUNING`, còn edition khác mặc định `NONE`. Trong tài liệu **26ai**, mặc định `Free` cũng được ghi là `DIAGNOSTIC+TUNING`. **Giá trị mặc định là cấu hình kỹ thuật, không phải bằng chứng đã mua pack.**

Đọc cấu hình hiện tại (chỉ truy vấn):

```sql
SELECT name, value
FROM   v$parameter
WHERE  name = 'control_management_pack_access';
```

Nếu doanh nghiệp không có quyền pack, cần DBA rà soát cấu hình và các đường sử dụng của công cụ quản trị. Việc điều chỉnh tham số là thay đổi hệ thống có ảnh hưởng đến chức năng theo dõi/chẩn đoán; chỉ thực hiện theo quy trình thay đổi đã phê duyệt. Ngược lại, **đặt `NONE` cũng không xóa được lịch sử sử dụng đã phát sinh** và không thay thế việc kiểm kê entitlement.

### 6.2. Không chỉ GUI: package, view và script cũng thuộc phạm vi

Manual 26ai liệt kê, trong phạm vi Diagnostics Pack, các API và đối tượng như `DBMS_WORKLOAD_REPOSITORY`, `DBMS_ADDM`, `V$ACTIVE_SESSION_HISTORY`, nhiều view `DBA_HIST_*` và các script AWR/ASH/ADDM tương ứng. Tuning Pack có thể bao gồm `DBMS_SQLTUNE`, `DBMS_SQL_MONITOR`, `V$SQL_MONITOR`, `V$SQL_PLAN_MONITOR`, tùy quy định và ngoại lệ được nêu.

**Ví dụ phân biệt:**

```text
Yêu cầu: "Tôi muốn xem SQL nào đang chậm"

Đường A: EXPLAIN PLAN / DBMS_XPLAN.DISPLAY cho câu SQL
        → Xem chức năng giải thích plan cơ bản theo manual.

Đường B: AWR report / ASH analytics / ADDM
        → Kiểm tra Diagnostics Pack trước.

Đường C: SQL Tuning Advisor / Real-Time SQL Monitoring
        → Kiểm tra Tuning Pack và điều kiện Diagnostics Pack trước.
```

Không nên tuyên bố “mọi view `DBA_HIST_*` đều bị tính phí”: **manual có liệt kê ngoại lệ cụ thể**, chẳng hạn `DBA_HIST_SNAPSHOT`, `DBA_HIST_DATABASE_INSTANCE`, `DBA_HIST_SNAP_ERROR`, `DBA_HIST_SEG_STAT`, `DBA_HIST_SEG_STAT_OBJ`, `DBA_HIST_UNDOSTAT`. Ngược lại, có quyền `SELECT` một view hoặc `EXECUTE` một package **không** có nghĩa được cấp phép sử dụng mọi chức năng của chúng. Xem đúng danh sách và điều kiện ngoại lệ của release.

## 7. Kiểm tra môi trường bằng SQL: thu thập dấu hiệu, không chứng nhận license

Các truy vấn dưới đây có mục đích **đọc thông tin**. Chúng không tạo option, không bật pack, không thực hiện thao tác có phí. Chạy bằng tài khoản đã được cấp quyền đọc metadata phù hợp; trong CDB nhiều PDB, cần hiểu phạm vi container của phiên truy vấn.

### 7.1. Xác định bản phát hành và edition

```sql
-- Banner sản phẩm; định dạng nội dung thay đổi giữa các release.
SELECT banner
FROM   v$version;

-- Thông tin phiên bản của instance hiện tại.
SELECT instance_name, version, status
FROM   v$instance;
```

Ghi kết quả cùng thông tin Oracle home, RU/patch và offering từ tài liệu triển khai. Không suy ra entitlement từ banner.

### 7.2. Xem những option Oracle báo khả dụng

```sql
SELECT parameter, value
FROM   v$option
WHERE  parameter IN (
           'Partitioning',
           'Real Application Clusters',
           'Advanced Compression'
       )
ORDER BY parameter;
```

`V$OPTION` phản ánh **khả năng/đặc tính của binary hoặc môi trường**, tùy option và release. `TRUE` **không tương đương** “đã mua”, “được phép dùng” hoặc “đã sử dụng”. `FALSE` cũng cần được đọc trong bối cảnh cấu hình và phiên bản. Không dùng view này làm chứng từ cấp phép.

### 7.3. Quan sát PDB và tham số liên quan

```sql
-- Khi có đủ quyền, ưu tiên quan sát từ CDB root để kiểm kê PDB.
SELECT con_id, name, open_mode
FROM   v$pdbs
ORDER BY con_id;

SELECT name, value
FROM   v$parameter
WHERE  name IN (
           'control_management_pack_access',
           'inmemory_size',
           'max_pdbs'
       )
ORDER BY name;
```

Với Multitenant, phải phân biệt `PDB$SEED` và các PDB do người dùng tạo; với RAC, có thể cần tổng hợp theo từng instance. Tham số cho biết trạng thái cấu hình, không đủ để kết luận license.

### 7.4. Tham khảo lịch sử phát hiện feature usage

```sql
SELECT name,
       detected_usages,
       currently_used,
       first_usage_date,
       last_usage_date
FROM   dba_feature_usage_statistics
WHERE  detected_usages > 0
ORDER BY name;
```

`DBA_FEATURE_USAGE_STATISTICS` là **một nguồn dấu hiệu** để điều tra, không phải danh sách hóa đơn hay bằng chứng entitlement. Kết quả có thể phản ánh sử dụng trong quá khứ, sampling, chức năng nội bộ hoặc các ngoại lệ theo version. Dòng `CURRENTLY_USED = 'FALSE'` không chứng minh tính năng chưa từng được dùng; dòng `TRUE` chưa đủ để khẳng định nghĩa vụ cấp phép nếu chưa phân loại feature và ngoại lệ.

**Cách tra soát được Oracle hướng dẫn:** Manual 26ai giới thiệu script `options_packs_usage_statistics.sql` (My Oracle Support, tài liệu **KB143588**) để tổng hợp usage option/pack và các feature liên quan. Oracle nêu rõ báo cáo này có tính **tham khảo**, không đại diện trực tiếp cho entitlement hay nghĩa vụ cấp phép. Tổ chức cần kiểm tra cách chạy script, phạm vi và quyền truy cập theo quy trình DBA nội bộ; dùng kết quả cùng tài liệu hợp đồng và tư vấn cấp phép khi cần.

### 7.5. Không nhầm giữa năm trạng thái

| Trạng thái | Cách hiểu chính xác |
| --- | --- |
| **Installed** | Thành phần có mặt trong Oracle home hoặc data dictionary |
| **Available / `TRUE`** | Binary/edition cho phép công nghệ hoặc option được đánh dấu khả dụng |
| **Enabled / configured** | Tham số, thành phần hoặc tính năng đã được bật, kể cả giá trị mặc định |
| **Used / detected** | Có quan sát kỹ thuật liên quan đến tính năng trong một phạm vi thời gian |
| **Licensed / entitled** | Có quyền sử dụng theo hợp đồng, offering, điều kiện và phạm vi triển khai |

Năm trạng thái có thể khác nhau. Quyết định triển khai cần trạng thái **entitled**, đối chiếu với khả năng kỹ thuật và feature thực sự sẽ sử dụng.

## 8. Quy trình phê duyệt một tính năng trước khi sử dụng

### Bước 1: Mô tả hành vi cần làm, không chỉ gọi tên công nghệ

Ví dụ, thay vì chỉ ghi “Data Guard”, ghi: “Có một physical standby; cần chạy truy vấn báo cáo trên standby đồng thời tiếp tục apply redo.” Hành vi cụ thể này giúp phân biệt Data Guard cơ bản với Active Data Guard. Thay vì “compression”, ghi rõ Advanced Row Compression, Data Pump `COMPRESSION` ở giá trị nào, hay backup RMAN loại nào.

### Bước 2: Chốt phiên bản và cột offering

Lấy edition từ metadata và đối chiếu tài liệu mua hàng/deployment. Chọn đúng manual 19c, 26ai hoặc release tương ứng; trong bảng tìm chính xác cột `EE`, `SE2`, `Free` hay tên dịch vụ OCI. Đọc cả `Notes`, mục **Options ... and Their Permitted Features**, **Management Packs ... and Their Permitted Features**, **Special License Rights** và **Restricted Use Licenses** khi liên quan.

### Bước 3: Tách quyền sử dụng khỏi bằng chứng kỹ thuật

Tổng hợp SQL quan sát (`V$VERSION`, `V$OPTION`, `DBA_FEATURE_USAGE_STATISTICS`, tham số), tài liệu cấu hình, script/job và công cụ. Dùng bằng chứng này để phát hiện cấu hình/usage cần xem xét; đồng thời lấy chứng từ về quyền sử dụng từ hợp đồng hoặc quản trị license.

### Bước 4: Kiểm tra điều kiện tiên quyết và vùng ảnh hưởng

Ví dụ Tuning Pack phụ thuộc Diagnostics Pack; Active Data Guard có thể liên quan cả primary lẫn standby; RAC/multitenant/virtualization làm phạm vi cần xác minh khác với một instance đơn lẻ. Kiểm tra riêng môi trường development, staging, disaster recovery, cloud và các máy được thêm sau này nếu chúng dùng feature.

### Bước 5: Ra một trong ba quyết định có bằng chứng

| Quyết định | Điều kiện | Hành động |
| --- | --- | --- |
| **APPROVED** | Tài liệu release cho phép và quyền tương ứng đã được đối chiếu, mọi điều kiện đáp ứng | Ghi người phê duyệt, thời điểm, phạm vi rồi triển khai |
| **HOLD / VERIFY** | Thiếu hợp đồng, không rõ SKU, chưa xác định option/pack, hoặc bằng chứng mâu thuẫn | Chưa sử dụng feature; trao đổi với chủ sở hữu license / DBA / Oracle licensing khi cần |
| **NOT PERMITTED** | Offering không hỗ trợ hoặc quyền cần thiết không có | Thiết kế lại bằng tính năng phù hợp, thay offering hoặc bổ sung quyền trước khi dùng |

### Bước 6: Gắn quyết định với quá trình thay đổi

Khi tạo DDL, nâng cấp release, bật job giám sát, chuyển cloud tier, thêm standby, đổi virtualization hoặc tăng số PDB, phải kiểm tra lại vì quyết định cũ có thể chỉ đúng trong phạm vi ban đầu.

## 9. Ví dụ quyết định trong các tình huống thực tế

### Tình huống A — Ứng dụng đang chạy SE2 muốn partition theo tháng

**Nhu cầu:** bảng `orders` lớn, muốn dùng `PARTITION BY RANGE (created_at)` để quản lý dữ liệu theo tháng.

**Đối chiếu:** Oracle Partitioning không khả dụng như option của SE2 trong bảng offering. Việc SQL engine chấp nhận một cú pháp hoặc có thành phần cài sẵn không thay đổi giới hạn.

**Quyết định:** `NOT PERMITTED` cho thiết kế này trên SE2; cân nhắc index, lưu trữ/archiving theo ứng dụng, thay đổi mô hình dữ liệu hoặc lập phương án EE cùng quyền Partitioning nếu thực sự cần.

### Tình huống B — EE có AWR mặc định nhưng chưa mua Diagnostics Pack

**Nhu cầu:** chạy `awrrpt.sql` hàng ngày, gửi báo cáo cho đội vận hành.

**Quan sát:** tham số `CONTROL_MANAGEMENT_PACK_ACCESS` có thể mặc định `DIAGNOSTIC+TUNING` trên EE, dù hợp đồng chỉ có EE cơ bản.

**Đối chiếu:** `awrrpt.sql` và các tính năng AWR/ADDM/ASH thuộc Diagnostics Pack (trừ ngoại lệ được manual ghi rõ cho từng đối tượng). Cấu hình mặc định không chứng minh entitlement.

**Quyết định:** `HOLD / VERIFY`; chưa bật job AWR mới. DBA và chủ sở hữu license kiểm tra quyền Diagnostics, những job/script đã tồn tại và hướng giám sát phù hợp quyền hiện có.

### Tình huống C — EE cần standby vừa apply redo vừa phục vụ dashboard

**Nhu cầu:** mở standby để dashboard truy vấn dữ liệu gần real-time trong khi redo đang apply.

**Đối chiếu:** đây là ví dụ của **Active Data Guard** với *physical standby real-time query*, khác với Data Guard Redo Apply cơ bản. On-premises EE thường phải có option Active Data Guard, và scope cần xét cả primary lẫn standby đang dùng tính năng đó.

**Quyết định:** chỉ `APPROVED` sau khi xác nhận quyền option, số hệ thống liên quan và điều khoản hợp lệ; nếu không, xem xét kiến trúc standby không sử dụng tính năng bổ sung hoặc hướng báo cáo khác.

### Tình huống D — Lab dùng Oracle AI Database 26ai Free

**Nhu cầu:** thử partitioning, TDE hoặc AWR trong một bài lab với cơ sở dữ liệu Free.

**Đối chiếu:** manual 26ai liệt kê nhiều option/pack được **included** trong `Free`; tuy nhiên Free có giới hạn tài nguyên và điều khoản riêng. Không được lấy quyền của `Free` để kết luận EE on-premises production cũng được dùng những option này miễn phí.

**Quyết định:** xác minh điều khoản Free và giới hạn phù hợp lab trước khi thực hành; khi chuyển bài lab sang môi trường thương mại phải kiểm tra lại từ đầu.

### Tình huống E — Cùng EE nhưng hai tier OCI khác nhau

**Nhu cầu:** nhóm A chạy BaseDB EE, nhóm B chạy BaseDB EE-HP, cả hai muốn bật Advanced Compression.

**Đối chiếu:** theo manual 26ai, Advanced Compression **không được bao gồm** trong `BaseDB EE` cơ bản, nhưng được liệt kê là **included** trong `BaseDB EE-HP` (và một số offering cao hơn). Một thay đổi về tier hoặc BYOL có thể thay đổi quyền tương ứng.

**Quyết định:** không áp dụng chung một chính sách cho cả hai nhóm; đối chiếu chính xác dịch vụ/tier và cơ chế license của từng deployment.

## 10. Mẫu phiếu đối chiếu trước triển khai

Sao chép mẫu sau vào change request, design review hoặc hồ sơ kiểm soát nội bộ:

| Trường | Giá trị ví dụ cần điền |
| --- | --- |
| Hệ thống / môi trường | `order-db-prod`, production, primary + standby |
| Oracle version và RU | `19c`, RU cụ thể |
| Edition / offering | `EE on-premises` hoặc tên service OCI đầy đủ |
| Nhu cầu | “Báo cáo SQL performance trong 7 ngày” |
| Feature/API/screen/script dự định dùng | `awrrpt.sql`; job và người dùng liên quan |
| Option/management pack liên quan | `Diagnostics Pack` |
| Trang/tables trong manual | Link tới release và dòng tính năng/pack cụ thể |
| Quyền theo hợp đồng | ID chứng từ/entitlement, phạm vi processor/user và hệ thống |
| Bằng chứng kỹ thuật | Banner, cấu hình, danh sách job, usage cần xem xét |
| Điều kiện bổ sung | Primary/standby, cloud/BYOL, giới hạn PDB, phụ thuộc pack |
| Quyết định / người duyệt / ngày | `APPROVED`, `HOLD / VERIFY`, `NOT PERMITTED` |
| Điều kiện kiểm tra lại | Đổi release/tier, thêm node/PDB, bật tool, thay kiến trúc |

**Một phiếu đúng** ghi rõ *feature sẽ được sử dụng*, *quyền tương ứng ở đâu* và *phạm vi áp dụng*. Dòng “Oracle EE → OK” hoặc ảnh chụp `V$OPTION = TRUE` là chưa đủ.

## 11. Những hiểu lầm thường gây sai sót

1. **“Enterprise Edition có mọi tính năng.”** Sai: nhiều Oracle option/pack vẫn tính phí riêng theo offering.
2. **“`V$OPTION.VALUE = TRUE` là đã có license.”** Sai: đây là dấu hiệu kỹ thuật, không phải chứng từ quyền sử dụng.
3. **“Oracle cài sẵn package nên chạy được.”** Sai: đường truy cập GUI, SQL, PL/SQL, script hay công cụ thứ ba đều có thể thuộc cùng pack.
4. **“Có Tuning Pack thì không cần Diagnostics Pack.”** Sai: Tuning Pack có điều kiện tiên quyết Diagnostics Pack theo manual.
5. **“`DIAGNOSTIC+TUNING` là giá trị mặc định nên miễn phí.”** Sai: default chỉ là trạng thái kỹ thuật của tham số.
6. **“Data Guard và Active Data Guard chỉ khác tên.”** Sai: real-time query trên standby đang apply redo là một ví dụ quan trọng cần xem option Active Data Guard.
7. **“Mọi kiểu compression đều cần Advanced Compression.”** Sai: có ngoại lệ/chế độ riêng; phải đối chiếu thao tác chính xác.
8. **“Free và OCI đã bao gồm nên EE on-premises cũng vậy.”** Sai: quyền gắn với offering, release và mô hình cấp phép cụ thể.
9. **“Không thấy dòng usage nghĩa là hoàn toàn chưa từng dùng.”** Sai: thống kê feature usage có giới hạn theo sampling, thời gian và logic nhận diện.
10. **“Dev, test và standby mặc nhiên miễn giấy phép.”** Không có kết luận chung như vậy; cần xem điều khoản đúng cho từng tình huống.

## 12. Bài thực hành đọc ma trận

Không cần chạy bất kỳ lệnh có tác dụng thay đổi nào. Hãy tự trả lời trước khi xem phần gợi ý:

**Bài 1.** Một database EE on-premises trả về `Partitioning = TRUE` trong `V$OPTION`. Nhóm phát triển muốn tạo bảng phân vùng. Cần thêm bằng chứng nào?

**Bài 2.** Trên EE, `CONTROL_MANAGEMENT_PACK_ACCESS` hiển thị `DIAGNOSTIC+TUNING`, nhưng bộ phận mua sắm chưa cung cấp entitlement. Có thể chạy SQL Tuning Advisor không?

**Bài 3.** Hai môi trường `BaseDB EE` và `BaseDB EE-HP` trong OCI cùng cần Advanced Compression. Có thể lấy một kết luận từ một dòng tên “EE” không?

**Bài 4.** Một CDB dự định tăng số PDB người dùng từ 3 lên 10. Cần biết thêm những yếu tố nào?

<details>
<summary>Gợi ý đáp án</summary>

1. Cần manual đúng release/edition, hàng Oracle Partitioning và quyền mua/bao gồm option có phạm vi thích hợp. `TRUE` chưa đủ.
2. Chưa được kết luận. Tuning Pack yêu cầu quyền Tuning **và** Diagnostics; tham số mặc định không phải entitlement. Đưa vào trạng thái `HOLD / VERIFY`.
3. Không. So sánh cột service/tier chính xác; tài liệu 26ai có khác biệt giữa hai tier. Kiểm tra thêm license-included hay BYOL.
4. Release, offering, giới hạn PDB miễn option, quyền Oracle Multitenant, hệ thống EE/EE-ES/cloud, phương thức BYOL và giới hạn kỹ thuật/điều khoản hiện hành.

</details>

## 13. Tài liệu chính thức để tra cứu

Các đường dẫn dưới đây là điểm bắt đầu; khi mở phải chọn tài liệu tương ứng với **release đang thực sự chạy** và kiểm tra bản cập nhật/chú thích được Oracle công bố:

1. [Oracle AI Database 26ai — Database Licensing Information User Manual](https://docs.oracle.com/en/database/oracle/oracle-database/26/dblic/Licensing-Information.html): bảng offering, permitted features, options, management packs, kiểm tra usage và special license rights.
2. [Oracle Database 19c — Licensing Information](https://docs.oracle.com/en/database/oracle/oracle-database/19/dblic/Licensing-Information.html): tài liệu đối chiếu cho hệ thống 19c, không thay thế bằng bảng 26ai.
3. [Oracle Database 19c — `CONTROL_MANAGEMENT_PACK_ACCESS`](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/CONTROL_MANAGEMENT_PACK_ACCESS.html): giá trị, mặc định và quan hệ giữa Diagnostics/Tuning Pack.
4. [Oracle AI Database 26ai — `CONTROL_MANAGEMENT_PACK_ACCESS`](https://docs.oracle.com/en/database/oracle/oracle-database/26/refrn/CONTROL_MANAGEMENT_PACK_ACCESS.html): chú ý khác biệt mặc định với Free.
5. [My Oracle Support](https://support.oracle.com/) — tìm **KB143588**, script `options_packs_usage_statistics.sql` theo hướng dẫn trong manual 26ai; kết quả chỉ hỗ trợ điều tra usage, không xác nhận entitlement.
6. [Oracle Software Investment Guide / Licensing](https://www.oracle.com/corporate/pricing/): dùng cùng hợp đồng và tài liệu cấp phép do tổ chức lưu trữ để xác minh metric, phạm vi và điều kiện.

**Quy tắc làm việc cuối cùng:** xác định **đúng feature → đúng release → đúng offering → option/pack và giới hạn → entitlement/contract → phạm vi sử dụng**; chỉ triển khai khi các mắt xích đó đã được xác nhận và lưu bằng chứng.
