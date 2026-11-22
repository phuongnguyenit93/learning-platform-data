# Lập ma trận tính năng theo release, COMPATIBLE, edition và giấy phép trong Oracle

## 1. Vì sao cần ma trận tính năng?

Oracle Database có nhiều release, edition, tùy chọn (option), management pack và mô hình cấp phép. Một tính năng có thể xuất hiện trong tài liệu của một release nhưng không có trong release khác; có thể được cài đặt trong binary nhưng không khả dụng ở edition đang dùng; có thể chạy được về mặt kỹ thuật nhưng cần option hoặc management pack riêng; hoặc chỉ được bật khi tham số `COMPATIBLE` đạt mức phù hợp.

Vì vậy, câu hỏi “Database có hỗ trợ tính năng này không?” chưa đủ. Trước khi thiết kế, nâng cấp hoặc bật một tính năng, cần xác định đồng thời:

1. **Release và Release Update (RU):** phiên bản phần mềm cụ thể, bao gồm patch level.
2. **`COMPATIBLE`:** mức tương thích định dạng/khả năng database được cấu hình.
3. **Edition:** bộ tính năng nền tảng của sản phẩm, ví dụ Enterprise Edition hoặc Standard Edition 2 ở release có hỗ trợ.
4. **Option/management pack:** thành phần có thể cần mua và cấp quyền riêng.
5. **License entitlement và metric:** hợp đồng, số lượng, phạm vi triển khai và cách tính license.
6. **Điều kiện kiến trúc:** platform, CDB/PDB, RAC, cloud service, topology và cấu hình triển khai.

Bài học thuộc module **Database Engine Relational Oracle**, chương **Tính năng mở rộng**, tập trung vào **lập ma trận tính năng theo release, COMPATIBLE, edition và giấy phép**.

Mục tiêu là xây dựng được một ma trận có bằng chứng, dùng để ra quyết định kỹ thuật và quản trị license. Các view trong database giúp quan sát cấu hình hoặc việc sử dụng tính năng; chúng không thay thế hợp đồng và không tự chứng minh quyền sử dụng.

## 2. Năm lớp cần phân biệt

Một ma trận tốt không gộp tất cả điều kiện vào một cột “Supported”. Hãy phân biệt các lớp sau.

| Lớp | Câu hỏi cần trả lời | Nguồn bằng chứng chính |
|---|---|---|
| Release/RU | Tính năng có tồn tại và còn được hỗ trợ ở bản này không? | Oracle documentation, release notes, upgrade guide |
| COMPATIBLE | Database compatibility level có cho phép dùng cấu trúc/tính năng cần thiết không? | `V$PARAMETER`, tài liệu parameter của release |
| Edition | Edition đang cài có bao gồm tính năng nền tảng đó không? | Licensing Information User Manual đúng release |
| Option/pack | Có cần option hoặc management pack riêng không? | Licensing manual, product price list, contract |
| Entitlement | Tổ chức có quyền sử dụng ở deployment và metric này không? | Ordering document, license agreement, cloud service terms, license inventory |

Ngoài năm lớp trên, cần kiểm tra kiến trúc: tính năng có thể yêu cầu CDB/PDB, OS/platform, hardware, service configuration hoặc topology nhất định.

### 2.1. Có trong binary không đồng nghĩa có quyền sử dụng

Một option có thể được cài hoặc hiển thị là available trong database home nhưng tổ chức không có entitlement tương ứng. Ngược lại, việc một option không được sử dụng trong môi trường hiện tại không nhất thiết có nghĩa license không cần thiết cho một deployment khác.

**Technical availability** trả lời phần mềm có thể cung cấp chức năng hay không. **License entitlement** trả lời tổ chức có quyền sử dụng chức năng theo hợp đồng và điều kiện triển khai hay không. Đây là hai kết luận riêng.

### 2.2. Có thể sử dụng được không đồng nghĩa nên bật

Ngay cả khi feature được hỗ trợ và đã có entitlement, vẫn phải đánh giá:
- Hiệu năng và tài nguyên.
- Ảnh hưởng tới backup/restore, replication và DR.
- Khả năng tương thích ứng dụng/driver.
- Vận hành, monitoring và kỹ năng đội ngũ.
- Chi phí license và hạ tầng.
- Rủi ro rollback hoặc chuyển đổi dữ liệu.

Ma trận phải có cả trạng thái kỹ thuật lẫn quyết định triển khai.

## 3. Release, Release Update và trạng thái vòng đời tính năng

### 3.1. Release

Release xác định dòng phiên bản Oracle Database, ví dụ 19c, 21c hoặc 23ai. Không chỉ ghi “Oracle 19” trong inventory; cần ghi phiên bản đầy đủ và release family thực tế.

Một tính năng có thể:
- Được giới thiệu ở một release.
- Được mở rộng ở release tiếp theo.
- Có giới hạn theo edition hoặc platform.
- Bị deprecated.
- Bị desupported ở release mới.
- Thay đổi điều kiện cấu hình hoặc cách quản trị.

### 3.2. Release Update (RU)

RU là bản cập nhật định kỳ chứa các sửa lỗi và thay đổi được Oracle phát hành cho release tương ứng. Hai môi trường cùng ghi “19c” vẫn có thể khác RU, one-off patch và SQL patch registry.

Ghi nhận tối thiểu:
- Database release/version.
- RU hoặc patch level.
- SQL patch registry.
- Oracle Home/JDBC client version nếu liên quan.
- Ngày áp dụng và change record.

Không giả định RU chỉ chứa security fix và không ảnh hưởng behavior. Đọc RU README, known issues và bug fix list liên quan đến workload.

### 3.3. Feature lifecycle

Trong ma trận, dùng các trạng thái có nghĩa rõ:

| Trạng thái | Ý nghĩa |
|---|---|
| Available | Có trong release và điều kiện edition/architecture cho phép |
| Available with restriction | Có nhưng bị giới hạn bởi edition, platform, topology hoặc cấu hình |
| Requires option/pack | Cần thành phần cấp phép riêng |
| Requires COMPATIBLE | Chỉ khả dụng khi `COMPATIBLE` đạt điều kiện |
| Deprecated | Còn tồn tại nhưng Oracle khuyến nghị không dùng và có thể bị loại ở release sau |
| Desupported | Không còn được hỗ trợ trong release đó |
| Not available | Không có trong release/edition/architecture đang xét |
| Unknown / verify | Chưa đủ bằng chứng để kết luận |

Đừng dùng một ô “No” cho cả not available, chưa được license và chưa kiểm tra. Những trạng thái này đòi hỏi hành động khác nhau.

## 4. `COMPATIBLE` kiểm soát điều gì?

Tham số initialization `COMPATIBLE` xác định mức tương thích mà database duy trì cho cấu trúc và behavior được phép sử dụng. Nó giúp database có thể được nâng software trước, sau đó mới nâng mức tương thích dữ liệu khi đã sẵn sàng.

Kiểm tra giá trị:

```sql
SELECT name,
       value,
       isdefault,
       issys_modifiable,
       ispdb_modifiable
FROM v$parameter
WHERE name = 'compatible';
```

Có thể xem cấu hình trong SPFILE:

```sql
SHOW PARAMETER compatible;
```

Cột và khả năng hiển thị tùy quyền và phiên bản.

### 4.1. Database release khác COMPATIBLE

Ví dụ một database đã chạy Oracle software release mới nhưng `COMPATIBLE` vẫn giữ giá trị thấp hơn trong giai đoạn chuyển đổi. Một số khả năng mới có thể chưa được phép sử dụng vì database vẫn duy trì compatibility level cũ.

Vì vậy, không suy ra feature availability chỉ từ `V$VERSION`. Cần ghi cả:
- Software release.
- RU.
- `COMPATIBLE`.
- Edition.
- Option/pack.
- Cấu hình database.

### 4.2. Nâng COMPATIBLE cần change plan riêng

Thay đổi `COMPATIBLE` thường là thay đổi tĩnh, cần cấu hình SPFILE và restart theo quy trình release. Ví dụ minh họa:

```sql
ALTER SYSTEM SET compatible = '19.0.0' SCOPE = SPFILE;
```

Không chạy câu lệnh này chỉ vì database software đã nâng lên 19c. Giá trị hợp lệ và quy trình cần theo upgrade guide của đúng release.

Trước khi tăng:
- Xác nhận upgrade hoàn tất.
- Hoàn tất kiểm thử ứng dụng và workload.
- Kiểm tra backup/recovery.
- Kiểm tra downgrade path.
- Đọc yêu cầu của feature cần bật.
- Có phê duyệt và cửa sổ thay đổi.

### 4.3. Tăng COMPATIBLE có thể giới hạn downgrade

Sau khi nâng compatibility level và database sử dụng các cấu trúc mới, quay lại release cũ có thể không còn được hỗ trợ. Khả năng downgrade phụ thuộc release, trạng thái upgrade, feature đã dùng và hướng dẫn Oracle.

Không coi đổi lại giá trị parameter là rollback đầy đủ. Cần kiểm tra downgrade guide hoặc restore từ backup đã được xác nhận.

### 4.4. COMPATIBLE không phải license switch

Đặt `COMPATIBLE` cao không cấp quyền sử dụng option. Đặt thấp cũng không tự chứng minh rằng không có feature được sử dụng hoặc không cần license. Nó là một điều kiện kỹ thuật trong ma trận, không thay thế hợp đồng.

## 5. Edition, option và management pack

### 5.1. Edition

Edition xác định tập khả năng nền tảng được cung cấp trong sản phẩm. Tên edition và feature matrix thay đổi theo release, platform và mô hình phân phối.

Khi lập ma trận, ghi chính xác edition đang chạy và edition được mua. Không suy luận edition chỉ từ một option hiển thị trong `V$OPTION`.

### 5.2. Database options

Một số khả năng được đóng gói thành option riêng. Ví dụ các nhóm thường cần kiểm tra license riêng theo release và hợp đồng:
- Partitioning.
- Advanced Compression.
- Advanced Security.
- Database In-Memory.
- Real Application Clusters.
- Active Data Guard.
- Multitenant ở các mô hình/release có điều kiện cấp phép tương ứng.
- Các option khác được liệt kê trong Licensing Information User Manual.

Danh sách này là ví dụ để lập inventory, không phải tuyên bố rằng mọi option đều có cùng điều kiện ở mọi release hoặc cloud service.

### 5.3. Management packs

Management pack là nhóm công cụ quản trị/diagnostics/tuning có điều kiện cấp phép riêng theo sản phẩm và release. Ví dụ:
- Diagnostics Pack.
- Tuning Pack.
- Các pack quản trị khác được tài liệu licensing liệt kê.

Các tính năng như AWR, ASH, ADDM, SQL Tuning Advisor hoặc SQL Monitoring có thể liên quan đến pack tương ứng. Phải đối chiếu đúng tính năng, release, điều kiện và contract; không mặc định mọi công cụ chẩn đoán đều miễn phí hoặc mọi truy vấn dictionary đều cần pack.

### 5.4. Enterprise Edition không đồng nghĩa mọi option đều được cấp phép

Một database chạy Enterprise Edition không tự động có quyền sử dụng tất cả database options và management packs. Hãy ghi từng entitlement riêng và xác định deployment nào được bao phủ.

### 5.5. Cloud service và license included/BYOL

Các dịch vụ database trên cloud có thể có mô hình:
- License included.
- Bring Your Own License (BYOL).
- Service-specific entitlement.
- Giới hạn theo shape, OCPU/ECPU, region hoặc service tier.

Không áp dụng trực tiếp bảng license on-premises cho cloud service. Dùng service description, cloud contract và licensing terms tương ứng.

## 6. Xây dựng ma trận tính năng

Một dòng trong ma trận đại diện cho một feature hoặc một nhóm capability có cùng điều kiện. Không ghi chung “Oracle advanced features” vì mỗi feature có release, edition và entitlement khác nhau.

### 6.1. Các cột đề xuất

| Cột | Nội dung |
|---|---|
| Feature ID | Mã ổn định để tham chiếu |
| Feature name | Tên chính thức/tên nghiệp vụ |
| Business purpose | Vì sao ứng dụng cần feature |
| Introduced in | Release đầu tiên được hỗ trợ |
| Target release/RU | Release và patch level đang xét |
| Lifecycle | Available/deprecated/desupported |
| Edition | Edition yêu cầu |
| Option/pack | Option hoặc management pack riêng |
| COMPATIBLE | Mức tương thích tối thiểu/điều kiện |
| Architecture | CDB/PDB, RAC, OS, platform, cloud condition |
| License metric | Processor, NUP hoặc metric theo contract |
| Entitlement evidence | Hợp đồng/order/approval |
| Technical evidence | Query, config, test, screenshot/log |
| Owner | DBA, application owner, license owner |
| Decision | Approved, blocked, not used, verify |
| Review date | Ngày rà soát gần nhất |

### 6.2. Ví dụ ma trận trống có thể dùng

| Feature | Release/RU | COMPATIBLE | Edition | Option/pack | Entitlement | Kết quả |
|---|---|---|---|---|---|---|
| Partitioning | Điền bản mục tiêu | Kiểm tra manual | Kiểm tra manual | Kiểm tra license | Đối chiếu contract | Verify |
| Advanced Compression | Điền bản mục tiêu | Kiểm tra manual | Kiểm tra manual | Kiểm tra license | Đối chiếu contract | Verify |
| Database In-Memory | Điền bản mục tiêu | Kiểm tra manual | Kiểm tra manual | Kiểm tra license | Đối chiếu contract | Verify |
| Diagnostics Pack | Điền bản mục tiêu | Theo release | Edition phù hợp | Management pack | Đối chiếu contract | Verify |
| Active Data Guard | Điền bản mục tiêu | Theo release | Edition phù hợp | Option | Đối chiếu contract | Verify |
| Multitenant/PDB | Điền bản mục tiêu | Theo release | Theo service | Điều kiện PDB/option | Đối chiếu contract | Verify |

Đây là mẫu quy trình, không phải feature entitlement matrix chính thức. Không điền “Yes” cho một feature chỉ vì tên nó xuất hiện trong dictionary hoặc tài liệu marketing.

### 6.3. Tách trạng thái kỹ thuật và trạng thái license

Nên có hai cột quyết định riêng:

- `technical_status`: supported, configured, tested, blocked, unknown.
- `license_status`: entitled, not entitled, contract review, not applicable, unknown.

Một feature có thể technical_status = supported nhưng license_status = not entitled. Khi đó quyết định production phải blocked cho đến khi có hướng xử lý được phê duyệt.

## 7. Nguồn tài liệu và thứ tự ưu tiên

Sử dụng tài liệu đúng release và đúng mô hình triển khai.

### 7.1. Oracle Database Licensing Information User Manual

Đây là nguồn quan trọng để xác định:
- Feature nào thuộc edition.
- Option/pack nào có điều kiện cấp phép riêng.
- Các điều kiện và ngoại lệ theo release.
- Một số metric/giới hạn theo mô hình sản phẩm.

Phải chọn manual tương ứng với release và platform đang dùng. Không lấy bảng từ 11g/12c áp dụng nguyên xi cho 19c/23ai hoặc cloud service.

### 7.2. Oracle Database Licensing Guide / License Definitions

Đối chiếu:
- Product/option được đặt hàng.
- Processor hoặc Named User Plus.
- Minimums và metric đặc thù.
- Core factor nếu áp dụng.
- Điều khoản virtualization/cloud.
- Term, territory, entity và deployment scope.

Hợp đồng và ordering documents của tổ chức quyết định entitlement thực tế. Tài liệu public giúp giải thích sản phẩm nhưng không thể thay thế hợp đồng cụ thể.

### 7.3. Database New Features Guide

Dùng để xác định feature được giới thiệu ở release nào, behavior mới và điều kiện kỹ thuật.

### 7.4. Upgrade Guide và Release Notes

Dùng để xác nhận:
- Đường upgrade được hỗ trợ.
- Thay đổi `COMPATIBLE`.
- Deprecated/desupported features.
- RU-specific known issues.
- Post-upgrade actions.
- Platform/architecture restrictions.

### 7.5. My Oracle Support và patch README

Khi có quyền support, kiểm tra bug, one-off patch, known issue và yêu cầu driver/database tương ứng. Patch README của RU/one-off là bằng chứng cần lưu trong change record.

## 8. Thu thập trạng thái kỹ thuật từ database

Các câu SQL dưới đây giúp inventory cấu hình. Chúng không phải công cụ xác nhận license entitlement.

### 8.1. Database version

```sql
SELECT banner_full
FROM v$version
ORDER BY banner_full;
```

Hoặc:

```sql
SELECT version,
       version_full
FROM v$instance;
```

Lưu kết quả cùng Oracle Home, RU và platform.

### 8.2. COMPATIBLE

```sql
SELECT name,
       value,
       isdefault,
       issys_modifiable
FROM v$parameter
WHERE name = 'compatible';
```

Ghi nhận cả giá trị cấu hình và thời điểm lấy mẫu.

### 8.3. Options hiển thị trong instance

```sql
SELECT parameter,
       value
FROM v$option
ORDER BY parameter;
```

`V$OPTION` cho biết một số option có được cài/enable trong software/database environment hay không theo semantics của release. Giá trị `TRUE` không chứng minh tổ chức đã mua license; `FALSE` cũng không thay thế việc đọc hợp đồng.

### 8.4. Component registry

```sql
SELECT comp_id,
       comp_name,
       version,
       status
FROM dba_registry
ORDER BY comp_id;
```

View này phản ánh trạng thái component được đăng ký trong database. Không phải mọi database option đều được biểu diễn như một component trong `DBA_REGISTRY`.

### 8.5. SQL patch registry

```sql
SELECT patch_id,
       patch_type,
       action,
       status,
       action_time,
       description
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
```

Dùng kết quả để đối chiếu RU/SQL patch. Kết hợp với inventory Oracle Home và patch README; registry không phải toàn bộ lịch sử patch ở mọi tầng.

### 8.6. Feature usage statistics

```sql
SELECT name,
       detected_usages,
       currently_used,
       first_usage_date,
       last_usage_date,
       version
FROM dba_feature_usage_statistics
ORDER BY name;
```

`DBA_FEATURE_USAGE_STATISTICS` hỗ trợ quan sát một số feature usage được database phát hiện. Cần hiểu giới hạn:
- Có thể có false positive hoặc false negative tùy feature và release.
- Việc feature được phát hiện không tự chứng minh entitlement.
- Không phát hiện usage không tự chứng minh feature chưa từng được dùng.
- Cần đọc feature usage documentation và xác nhận cách Oracle ghi nhận từng feature.
- Không dùng một snapshot duy nhất để thay thế audit dài hạn.

Ở CDB, xem xét view CDB tương ứng nếu release cung cấp và quyền cho phép; phải ghi rõ container/PDB và phạm vi lấy mẫu.

### 8.7. Cấu hình management pack access

Có thể xem parameter liên quan:

```sql
SELECT name, value
FROM v$parameter
WHERE name = 'control_management_pack_access';
```

Parameter này điều khiển một số khả năng truy cập management pack theo release. Nó không phải license key và không cấp entitlement. Đặt giá trị cho phép truy cập không có nghĩa hợp đồng đã bao gồm pack; đặt giá trị hạn chế cũng không thay thế việc inventory usage và entitlement.

### 8.8. Kiểm tra CDB/PDB

```sql
SELECT con_id,
       name,
       open_mode,
       restricted
FROM v$pdbs
ORDER BY con_id;
```

Ghi nhận PDB, service, trạng thái và cách tính entitlement áp dụng cho mô hình multitenant của release/contract. Không suy luận điều kiện license chỉ từ số PDB đang OPEN.

## 9. Vì sao các view không chứng minh license?

Có một số nhầm lẫn phổ biến:

| Quan sát | Có thể kết luận | Không thể kết luận |
|---|---|---|
| `V$OPTION` = TRUE | Option có trạng thái kỹ thuật được hiển thị là available | Tổ chức đã mua option |
| `DBA_REGISTRY` có component | Component được đăng ký/cài đặt | Đã có entitlement cho mọi cách sử dụng |
| Feature usage có `DETECTED_USAGES` | Database ghi nhận một loại usage theo detector | Contract chắc chắn yêu cầu hoặc cho phép một kết luận pháp lý cụ thể |
| `CONTROL_MANAGEMENT_PACK_ACCESS` cho phép | Một số chức năng pack có thể truy cập | License pack đã được mua |
| SQL chạy thành công | Database thực thi được statement | Statement được license trong môi trường đó |
| DBA không thấy usage | Snapshot không ghi nhận usage | Không có usage ở thời điểm khác hoặc đường truy cập khác |

Tách rõ technical evidence, usage evidence và contractual evidence trong báo cáo.

## 10. Xác định edition và entitlement thực tế

### 10.1. Xác định edition kỹ thuật

Dùng version banner, Oracle Home inventory và tài liệu triển khai để xác nhận edition. Không dựa duy nhất vào `V$OPTION`, bởi nhiều option có thể hiện trạng thái độc lập với edition.

Ví dụ lấy banner:

```sql
SELECT banner
FROM v$version
WHERE banner LIKE 'Oracle Database%';
```

Kết hợp thông tin từ:
- Oracle Home inventory.
- Database creation/deployment record.
- Container image hoặc cloud service details.
- Hợp đồng/ordering documents.

### 10.2. License inventory của tổ chức

License owner/asset management nên cung cấp:
- Product SKU và edition.
- Option/management pack được đặt hàng.
- Số lượng license.
- Metric.
- Processor/core factor nếu áp dụng.
- Named User Plus và minimums nếu áp dụng.
- Deployment scope và legal entity.
- Term/expiry/renewal.
- ULA/PULA hoặc điều khoản đặc biệt nếu có.
- Cloud service entitlement hoặc BYOL condition.
- Các amendment/contract change.

Không lưu thông tin hợp đồng nhạy cảm trong file kỹ thuật mở rộng quyền truy cập. Ma trận có thể tham chiếu đến contract ID hoặc kho tài liệu được kiểm soát.

### 10.3. Metric không phải lúc nào cũng là số session

Một số license dùng Processor, một số dùng Named User Plus hoặc metric riêng. Không lấy số connection pool, số database user hoặc số CPU nhìn thấy trong VM rồi tự suy ra số license phải mua.

Virtualization, hard partitioning, soft partitioning, cloud infrastructure và core factor có quy tắc riêng. Cần đối chiếu licensing policy/contract và xác nhận với license specialist.

## 11. Ví dụ các nhóm feature cần đưa vào ma trận

Danh sách dưới đây là gợi ý inventory. Điều kiện cụ thể phải được xác minh trong manual đúng release và hợp đồng.

### 11.1. Partitioning

Cần kiểm tra:
- Release có hỗ trợ loại partitioning đang dùng không.
- Edition/option requirement.
- `COMPATIBLE` nếu có điều kiện.
- Table/index partitioning, interval, reference, composite hoặc feature liên quan.
- DDL hiện tại và object thực sự sử dụng.
- License entitlement.

Inventory object:

```sql
SELECT owner,
       table_name,
       partitioning_type,
       subpartitioning_type,
       partition_count
FROM dba_part_tables
ORDER BY owner, table_name;
```

View này cho biết table partitioned, không chứng minh license entitlement. Cần kết hợp DDL, usage và licensing manual.

### 11.2. Advanced Compression

Xem xét:
- Compression type.
- Table/index/LOB usage.
- Backup compression và các feature compression khác có thể thuộc điều kiện khác.
- Edition, option và release.
- Workload CPU/I/O và khả năng giảm storage.
- Feature usage và contract.

Không gộp mọi loại nén thành một feature duy nhất. Basic compression, advanced row compression, hybrid columnar compression và backup compression có điều kiện kỹ thuật/licensing khác nhau theo sản phẩm và release.

### 11.3. Database In-Memory

Cần inventory:
- Edition/release.
- Option entitlement.
- `INMEMORY_SIZE` và cấu hình instance.
- Object có `INMEMORY` attribute.
- In-memory population và memory consumption.
- Workload analytic thực tế.
- Platform/service restriction.

Một object được khai báo `INMEMORY` không tự chứng minh segment đã được populate hoặc workload được tăng tốc. Kiểm tra view runtime phù hợp với release và đo query thực tế.

### 11.4. Real Application Clusters

Kiểm tra:
- Edition/release và option entitlement.
- Clusterware/Grid Infrastructure.
- Instance count và node topology.
- Service configuration.
- FAN/FCF/UCP client support.
- Failover behavior và workload placement.

Có thể xem instance:

```sql
SELECT inst_id,
       instance_name,
       host_name,
       status
FROM gv$instance
ORDER BY inst_id;
```

`GV$INSTANCE` cho thấy instance đang nhìn thấy trong cluster; nó không chứng minh entitlement RAC.

### 11.5. Active Data Guard và Data Guard

Phân biệt khả năng Data Guard cơ bản với các capability bổ sung như real-time query trên standby hoặc feature khác có điều kiện option/license riêng.

Kiểm tra:
- Database role.
- Open mode.
- Transport/apply lag.
- Standby topology.
- Read-only workload.
- Feature thực tế được sử dụng.
- Licensing manual và contract.

Ví dụ:

```sql
SELECT database_role,
       open_mode,
       protection_mode,
       switchover_status
FROM v$database;
```

Không kết luận license chỉ từ việc standby đang MOUNT hoặc OPEN READ ONLY. Xác định chính xác capability và use case.

### 11.6. Diagnostics Pack và Tuning Pack

Inventory các công cụ/workflow:
- AWR reports/snapshots.
- ASH.
- ADDM.
- SQL Tuning Advisor.
- SQL Monitoring.
- Các chức năng khác được licensing manual liệt kê.

Không mặc định mọi view `V$` đều thuộc pack. Cũng không mặc định một chức năng không có giao diện UI thì không bị điều kiện license. Xác nhận từng feature với manual đúng release.

### 11.7. Multitenant

Kiểm tra:
- Release và edition.
- Số PDB và cách sử dụng.
- PDB được tạo, clone, refresh hoặc relocate như thế nào.
- Application root/seed nếu có.
- Điều kiện entitlement theo release/contract.
- Cloud service terms nếu chạy trên cloud.

Không dùng một quy tắc số PDB cố định cho mọi release. Điều kiện multitenant đã thay đổi theo phiên bản và mô hình cấp phép.

## 12. Ma trận ví dụ cho một hệ thống

Giả sử một hệ thống cần các capability sau. Đây là minh họa cấu trúc, không phải kết luận license của một release cụ thể.

| Feature | Mục tiêu | Release/RU | COMPATIBLE | Edition/option | License evidence | Quyết định |
|---|---|---|---|---|---|---|
| Partitioning | Chia bảng giao dịch lớn | Verify | Verify | Verify | Chưa đối chiếu | Blocked |
| Advanced Compression | Giảm storage | Verify | Verify | Verify | Chưa đối chiếu | Blocked |
| RAC | HA instance | Verify | Verify | Verify | Chưa đối chiếu | Blocked |
| Active Data Guard capability | Read-only standby workload | Verify | Verify | Verify | Chưa đối chiếu | Blocked |
| Diagnostics Pack | AWR/ADDM | Verify | Verify | Verify | Chưa đối chiếu | Blocked |
| Tuning Pack | SQL tuning/monitoring | Verify | Verify | Verify | Chưa đối chiếu | Blocked |
| Multitenant | Cô lập workload bằng PDB | Verify | Verify | Verify | Chưa đối chiếu | Blocked |

Trạng thái `Blocked` ở đây có nghĩa chưa đủ bằng chứng để phê duyệt sử dụng. Không có nghĩa feature chắc chắn không được cấp phép.

### 12.1. Thêm bằng chứng vào từng dòng

Ví dụ một dòng hoàn chỉnh nên ghi:
- Tài liệu Oracle và release được đối chiếu.
- Kết quả inventory database.
- DDL/configuration thể hiện feature được dùng.
- Kết quả test và workload.
- Contract/order reference.
- Người phê duyệt kỹ thuật.
- Người phê duyệt license.
- Ngày rà soát.

## 13. Phân loại mức độ cần thiết và quyết định bật feature

Không phải feature nào có trong ma trận cũng cần bật. Thêm các trường:
- Business criticality.
- Expected benefit.
- Alternative without option.
- Operational complexity.
- License cost/impact.
- Rollback method.
- Owner.
- Decision date.

Một feature chỉ nên được đưa vào production khi:
1. Có nhu cầu nghiệp vụ rõ.
2. Release và kiến trúc hỗ trợ.
3. `COMPATIBLE` đáp ứng điều kiện.
4. Edition và option phù hợp.
5. License entitlement được xác nhận.
6. Có test và vận hành.
7. Có rollback/mitigation được phê duyệt.

## 14. Quy trình xác minh feature từ đầu đến cuối

### Bước 1. Viết yêu cầu nghiệp vụ

Mô tả kết quả mong muốn, không bắt đầu bằng tên option. Ví dụ: cần giảm thời gian báo cáo, cần failover instance hoặc cần lưu dữ liệu nhiều tenant.

### Bước 2. Chọn feature ứng viên

Xác định capability Oracle có thể đáp ứng. Ghi các phương án thay thế không cần option tương ứng nếu có.

### Bước 3. Chốt target environment

Ghi:
- Database release/RU.
- Edition.
- Platform.
- CDB/PDB topology.
- `COMPATIBLE`.
- RAC/Data Guard/cloud configuration.
- JDBC/driver/application version nếu có ảnh hưởng.

### Bước 4. Tra tài liệu đúng release

Đọc Licensing Information User Manual, New Features Guide, Upgrade Guide và Release Notes tương ứng. Lưu URL/document version và ngày tra cứu.

### Bước 5. Kiểm tra kỹ thuật

Dùng dictionary/dynamic views, parameter, DDL và test để xác nhận feature có sẵn, cấu hình và hoạt động như yêu cầu.

### Bước 6. Kiểm tra usage

Đối chiếu `DBA_FEATURE_USAGE_STATISTICS` và các bằng chứng runtime. Xác định detector có giới hạn gì; không tự diễn giải số liệu thành kết luận pháp lý.

### Bước 7. Xác nhận entitlement

License owner đối chiếu contract, SKU, metric, deployment scope và cloud terms. Nếu thiếu bằng chứng, trạng thái phải là `Unknown` hoặc `Contract review`.

### Bước 8. Phê duyệt và ghi quyết định

Lưu người phê duyệt kỹ thuật, license owner, ngày, scope và điều kiện. Không bật feature production trước khi hoàn tất gate cần thiết.

### Bước 9. Kiểm thử và giám sát

Test function, performance, backup/restore, HA/DR, monitoring và ứng dụng. Theo dõi usage và tài nguyên sau triển khai.

### Bước 10. Rà soát định kỳ

Rà soát lại khi:
- Upgrade release/RU.
- Đổi edition hoặc platform.
- Chuyển on-premises sang cloud.
- Thêm node/CPU/PDB.
- Bật option hoặc management pack.
- Thay đổi contract/ULA.
- Thay đổi workload hoặc tính năng thực tế sử dụng.

## 15. Kiểm soát `COMPATIBLE` trong vòng đời upgrade

### 15.1. Trước upgrade

- Ghi `COMPATIBLE` hiện tại.
- Đọc compatibility requirement của target release.
- Xác nhận upgrade path và downgrade window.
- Xác định feature cần mức compatibility mới.
- Không nâng tham số trước thời điểm được upgrade guide yêu cầu.

### 15.2. Sau upgrade nhưng trước khi tăng COMPATIBLE

- Xác nhận database ổn định.
- Compile và kiểm tra invalid objects.
- Chạy smoke/regression test.
- Kiểm tra backup/recovery.
- Xác nhận ứng dụng và client tương thích.
- Đánh giá khả năng downgrade còn cần thiết hay không.

### 15.3. Khi quyết định tăng COMPATIBLE

- Có change approval.
- Backup/restore point đã được kiểm tra.
- Hiểu downgrade restriction.
- Đặt giá trị được Oracle hỗ trợ cho release.
- Restart nếu parameter yêu cầu.
- Xác nhận giá trị mới.
- Chạy lại regression test.
- Ghi change record và cập nhật ma trận.

### 15.4. Không dùng COMPATIBLE để che lỗi

Nếu feature không hoạt động, đừng tùy tiện tăng `COMPATIBLE`. Có thể nguyên nhân là edition, option, grant, parameter khác, RU, platform hoặc cấu hình sai. Xác định đúng gate trước khi thay đổi.

## 16. Quản lý license usage và audit evidence

### 16.1. Evidence tối thiểu

Mỗi feature nên có:
- Tên và định nghĩa feature.
- Database/host/cluster/cloud service scope.
- Release/RU và edition.
- COMPATIBLE.
- Option/pack requirement.
- Contract/order reference.
- License metric và số lượng theo người có trách nhiệm.
- Technical configuration/usage evidence.
- Owner kỹ thuật và owner license.
- Ngày xác minh.
- Quyết định và ngoại lệ.

### 16.2. Usage monitoring không phải license calculator

`DBA_FEATURE_USAGE_STATISTICS` là một nguồn dữ liệu để điều tra feature usage. Nó không thay thế:
- Oracle license audit process.
- License agreement.
- Ordering document.
- Metric calculation.
- Contract amendment.
- Tư vấn của license specialist.

Không tự tính số license từ `DETECTED_USAGES` hoặc `AUX_COUNT`. Các trường này không phải số license cần mua.

### 16.3. Lưu evidence có kiểm soát

Lưu output SQL, report và contract reference ở kho có quyền phù hợp. Che thông tin nhạy cảm:
- Hostname/IP nếu được phân loại.
- Username/service account.
- Contract price và điều khoản thương mại.
- Serial/asset identifiers.
- Customer data.

Báo cáo kỹ thuật nên chỉ dẫn tới tài liệu hợp đồng được bảo vệ, không copy nội dung thương mại vào log chung.

## 17. Những lỗi thường gặp khi lập ma trận

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ ghi database release | Bỏ qua RU và COMPATIBLE | Ghi đầy đủ release/RU/COMPATIBLE |
| Coi V$OPTION TRUE là đã license | Dùng option không có entitlement | Đối chiếu contract và licensing manual |
| Coi feature usage = số license | Tính metric sai | License owner tính theo hợp đồng |
| Coi Enterprise Edition gồm mọi option | Bật option ngoài entitlement | Kiểm tra từng option/pack |
| Dùng manual của release cũ | Áp dụng sai điều kiện | Chọn đúng manual theo release/platform |
| Dùng quy tắc on-prem cho cloud | Sai metric/entitlement | Kiểm tra service terms và BYOL |
| Không ghi CDB/PDB | Bỏ sót scope multitenant | Inventory đúng container và contract |
| Coi `COMPATIBLE` là license switch | Nhầm kỹ thuật với pháp lý | Tách compatibility và entitlement |
| Bật feature trước khi phê duyệt | Tạo usage ngoài kế hoạch | Có technical/license gate |
| Chỉ kiểm tra feature đang bật | Bỏ sót feature được gọi qua workload khác | Kết hợp configuration, usage và application inventory |
| Không rà soát khi upgrade | Feature có thể deprecated/desupported | Cập nhật ma trận mỗi lần upgrade |
| Coi không thấy usage là không dùng | Bỏ sót detector limitation | Rà soát DDL, SQL, application và audit |
| Không có owner | Không ai chịu trách nhiệm cập nhật | Gán owner kỹ thuật và license |
| Không lưu bằng chứng | Khó chứng minh quyết định | Lưu nguồn, ngày, kết quả và phê duyệt |

## 18. Bài thực hành: lập ma trận cho môi trường Oracle

Bài lab dùng database thử nghiệm hoặc bản clone. Không bật option, thay `COMPATIBLE` hoặc chạy feature có điều kiện license trên production chỉ để thử.

### Bước 1. Ghi nhận môi trường

Thu thập:
- `V$VERSION`.
- `V$INSTANCE`.
- `V$DATABASE`.
- `V$PARAMETER` cho `COMPATIBLE`.
- PDB/service.
- Oracle Home inventory và RU.

### Bước 2. Inventory options/components

Chạy:
- `V$OPTION`.
- `DBA_REGISTRY`.
- `DBA_REGISTRY_SQLPATCH`.

Lưu output, ghi timestamp và container.

### Bước 3. Inventory feature usage

Đọc `DBA_FEATURE_USAGE_STATISTICS` theo release. Ghi rõ đây là usage evidence, không phải entitlement.

### Bước 4. Chọn năm feature nghiệp vụ

Ví dụ:
- Partitioning.
- Advanced Compression.
- RAC.
- Diagnostics Pack.
- Multitenant.

Không bật feature mới trong lab nếu chưa xác nhận quyền sử dụng. Chỉ lập dòng inventory và đánh dấu `Verify`.

### Bước 5. Tra manual đúng release

Mỗi feature tra:
- Availability.
- Edition.
- Option/pack.
- `COMPATIBLE`.
- Platform/architecture restriction.
- Deprecated/desupported status.

Ghi document title, release và ngày tra.

### Bước 6. Đối chiếu license inventory

License owner xác nhận:
- Product SKU.
- Metric.
- Quantity.
- Deployment scope.
- Contract/ordering document.
- Cloud/BYOL terms nếu có.

Nếu chưa có dữ liệu, để `Unknown`, không tự suy đoán.

### Bước 7. Điền ma trận

Mỗi dòng có technical status, license status, evidence và owner. Feature chưa xác nhận phải ở trạng thái `Blocked` hoặc `Contract review`.

### Bước 8. Kiểm tra COMPATIBLE

Đối chiếu compatibility requirement và downgrade plan. Không thay đổi tham số trong lab chỉ để làm cho ma trận có giá trị `Yes`.

### Bước 9. Phê duyệt

DBA/architect xác nhận kỹ thuật; license owner/legal procurement xác nhận entitlement. Ghi ngày và phạm vi phê duyệt.

### Bước 10. Lưu và đặt lịch rà soát

Lưu ma trận trong kho quản trị có version history. Đặt lịch rà soát khi upgrade, thay đổi contract hoặc thay đổi topology.

## 19. Checklist trước khi bật một tính năng

### Kỹ thuật
- Release/RU chính xác.
- Feature còn được hỗ trợ.
- Edition đáp ứng.
- `COMPATIBLE` đáp ứng.
- Option/pack kỹ thuật đã được cấu hình đúng.
- Platform/topology phù hợp.
- Ứng dụng/driver tương thích.
- Có test và rollback/mitigation.

### License
- Licensing manual đúng release đã được đối chiếu.
- Product SKU/contract đã xác nhận.
- Metric và deployment scope đã xác nhận.
- Option/management pack entitlement đã xác nhận.
- Cloud/BYOL condition đã xác nhận nếu có.
- License owner phê duyệt.
- Evidence được lưu.

### Vận hành
- Có owner.
- Monitoring và usage evidence được bật phù hợp.
- Backup/restore và DR đã đánh giá.
- Tài nguyên và performance đã benchmark.
- Change record ghi rõ thời điểm bật.
- Ma trận được cập nhật.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao cần lập ma trận tính năng thay vì chỉ tra release?

**Trả lời:** Vì khả năng sử dụng phụ thuộc đồng thời release/RU, `COMPATIBLE`, edition, option/pack, entitlement và kiến trúc.

**Câu 2.** `COMPATIBLE` có phải license switch không?

**Trả lời:** Không. Đây là mức tương thích kỹ thuật của database, không cấp quyền sử dụng option.

**Câu 3.** `V$OPTION` cho biết điều gì?

**Trả lời:** Trạng thái kỹ thuật của một số option trong môi trường database; không chứng minh license entitlement.

**Câu 4.** `DBA_FEATURE_USAGE_STATISTICS` có phải license calculator không?

**Trả lời:** Không. Nó ghi nhận một số usage được phát hiện và có giới hạn; không thay thế hợp đồng hoặc metric calculation.

**Câu 5.** Enterprise Edition có bao gồm mọi option không?

**Trả lời:** Không. Nhiều database option và management pack có điều kiện cấp phép riêng.

**Câu 6.** Vì sao phải ghi RU?

**Trả lời:** Cùng release có thể khác patch level, bug fix và behavior; RU là một phần của môi trường cần đối chiếu.

**Câu 7.** Tại sao không nên tăng COMPATIBLE ngay sau upgrade?

**Trả lời:** Việc tăng có thể giới hạn downgrade; cần hoàn tất kiểm thử, backup và change approval trước.

**Câu 8.** License entitlement lấy từ đâu?

**Trả lời:** Từ contract, ordering document, license agreement và cloud service terms có hiệu lực đối với tổ chức/deployment.

**Câu 9.** Diagnostics Pack và Tuning Pack cần được kiểm tra thế nào?

**Trả lời:** Inventory workflow thực tế và đối chiếu tính năng cụ thể với Licensing Information User Manual đúng release và hợp đồng.

**Câu 10.** Vì sao không áp dụng quy tắc multitenant từ release này sang release khác?

**Trả lời:** Điều kiện feature và license có thể thay đổi theo release và mô hình dịch vụ.

**Câu 11.** Technical status và license status nên tách thế nào?

**Trả lời:** Một cột ghi feature có hỗ trợ/cấu hình/test được không; cột khác ghi entitlement đã xác nhận hay chưa.

**Câu 12.** Khi nào feature phải bị Blocked?

**Trả lời:** Khi chưa đủ bằng chứng kỹ thuật, compatibility hoặc entitlement để phê duyệt production.

**Câu 13.** Vì sao cần owner cho mỗi dòng?

**Trả lời:** Để có người chịu trách nhiệm cập nhật feature, bằng chứng, contract và quyết định khi môi trường thay đổi.

**Câu 14.** Có nên bật feature chỉ vì SQL chạy thành công?

**Trả lời:** Không. SQL chạy được chỉ chứng minh khả năng kỹ thuật, không chứng minh quyền sử dụng.

**Câu 15.** Khi nào cần cập nhật ma trận?

**Trả lời:** Khi upgrade release/RU, thay edition/platform, thêm PDB/node, bật option, thay contract hoặc chuyển cloud.

## 21. Kết luận

Ma trận tính năng Oracle phải tách biệt khả năng kỹ thuật và quyền sử dụng. Release/RU xác định phiên bản phần mềm và vòng đời feature; `COMPATIBLE` kiểm soát mức tương thích database; edition xác định tập tính năng nền tảng; option và management pack có thể cần entitlement riêng; hợp đồng và metric quyết định tổ chức được quyền triển khai trong phạm vi nào. Kiến trúc CDB/PDB, RAC, platform và cloud service bổ sung các điều kiện khác.

Dùng `V$VERSION`, `V$PARAMETER`, `V$OPTION`, `DBA_REGISTRY`, `DBA_REGISTRY_SQLPATCH` và `DBA_FEATURE_USAGE_STATISTICS` để thu thập bằng chứng kỹ thuật/usage. Các view này không chứng minh license. Hãy đối chiếu Licensing Information User Manual đúng release với ordering documents, license agreement và cloud terms; gán license owner xác nhận metric và deployment scope. Khi chưa đủ bằng chứng, ghi `Unknown` hoặc `Blocked` thay vì suy đoán.

Mỗi lần bật feature cần qua các gate: nhu cầu nghiệp vụ, release và architecture hỗ trợ, `COMPATIBLE` phù hợp, edition/option đúng, entitlement được phê duyệt, kiểm thử và vận hành sẵn sàng. Cập nhật ma trận mỗi lần nâng cấp, thay đổi topology hoặc hợp đồng. Cách quản lý này giúp đội kỹ thuật chọn đúng capability, tránh nhầm technical availability với license entitlement và giữ được bằng chứng cho quyết định triển khai.

