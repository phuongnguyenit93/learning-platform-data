# Quản lý phiên bản lược đồ cùng dữ liệu sao lưu

Một bản sao lưu database được tạo vào thứ Hai khi ứng dụng Java dùng lược đồ v12. Đến thứ Tư, hệ thống đã triển khai lược đồ v15: đổi cách lưu giá tiền, thêm ràng buộc và chuyển dữ liệu lịch sử sang bảng mới. Thứ Năm, một thao tác nhầm khiến hệ thống cần phục hồi từ backup thứ Hai. Nếu chỉ khôi phục dữ liệu v12 rồi khởi động trực tiếp ứng dụng v15, liệu hệ thống có chạy đúng? Nếu chạy lại migration v13–v15, những script đó có còn an toàn với dữ liệu và môi trường đã khôi phục? Liệu rollback ứng dụng về bản cũ có hiểu được các giao dịch đã phát sinh theo lược đồ mới?

**Quản lý phiên bản lược đồ cùng dữ liệu sao lưu** là việc gắn trạng thái dữ liệu đã được chụp với **định nghĩa schema**, **lịch sử migration**, **phiên bản ứng dụng/driver**, **khả năng của DBMS** và **kịch bản khôi phục**. Mục tiêu không chỉ là giữ một file có thể giải nén hoặc nạp vào database. Mục tiêu là có thể dựng lại một hệ thống **hiểu đúng ý nghĩa dữ liệu**, bảo toàn các ràng buộc và phục hồi các hành vi nghiệp vụ trong phạm vi RPO/RTO đã được chọn.

Bài thuộc chương **Sao lưu và khôi phục** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Phạm vi liên quan trực tiếp đến thiết kế persistence cho Java: chọn schema và model, truy vấn và chỉ mục, transaction và isolation, xử lý lỗi kết nối, tiến hóa lược đồ, bảo mật backup và kiểm chứng hiệu năng khi restore. Đây là bài về **hợp đồng phiên bản và khả năng phục hồi**, không đơn giản là hướng dẫn cách chạy một lệnh `pg_dump`.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vì sao một tập backup cần gắn với **schema version, migration history, database engine version và application compatibility**.
2. Phân biệt **phiên bản schema**, **phiên bản dữ liệu/định dạng**, **phiên bản code**, **phiên bản DBMS** và **điểm khôi phục**.
3. Hiểu giới hạn của logical dump, physical backup, snapshot và WAL/PITR đối với việc tái tạo lược đồ ở một thời điểm.
4. Thiết kế manifest/metadata có thể kiểm chứng để xác định đúng backup, checksum, schema state và các phụ thuộc phục hồi.
5. Sắp xếp đúng thứ tự restore, xác minh, migration, khởi động ứng dụng và mở lại traffic.
6. Nhận diện trường hợp migration version đã áp dụng nhưng backfill dữ liệu chưa hoàn tất.
7. Kiểm soát nguy cơ schema drift, migration checksum mismatch, ứng dụng cũ/mới không tương thích.
8. Thiết kế migration forward có giới hạn rủi ro khi khôi phục từ backup cũ.
9. Kiểm thử restore thực tế cho cả schema, dữ liệu, quyền truy cập, kết nối Java, outbox và projection.
10. Lập runbook phục hồi có kịch bản, vai trò, tiêu chí dừng và bằng chứng hoàn thành.

## 2. Một “phiên bản database” thực ra có nhiều lớp

Trong trao đổi hằng ngày, nhóm phát triển thường nói “database đang ở version 15”. Câu này chỉ có nghĩa nếu biết **version 15 của cái gì**.

| Trục phiên bản | Ví dụ | Câu hỏi cần trả lời khi restore |
|---|---|---|
| **Schema/migration version** | Flyway `V15` hoặc Liquibase changeset mới nhất | Những bảng/cột/ràng buộc nào hiện có? |
| **Data format/semantic version** | Trước lưu `amount` theo VND; sau lưu kèm `currency` | Giá trị lịch sử được diễn giải thế nào? |
| **Backfill state** | 83% hàng đã được chuyển; một số hàng còn `NULL` | Mọi bản ghi đã được biến đổi hay chưa? |
| **Application release** | Backend `orders-service 2.4.0` | Bản code nào đọc/ghi đúng schema và dữ liệu này? |
| **DBMS version** | PostgreSQL major/minor version | Backup có thể khôi phục bằng engine/công cụ nào? |
| **Extension/collation** | Extension version, collation/locale | Kiểu, hàm, index và phép so sánh còn đúng không? |
| **Recovery point** | Thời điểm/LSN/timeline đã chụp | Những transaction nào được xem là đã commit? |
| **External dependency version** | Event schema, search mapping, object-store state | Bản sao bên ngoài đã tương ứng với DB chưa? |

Một tập backup tốt cần đủ thông tin để tái tạo hoặc xác minh từng trục **có liên quan đến nghiệp vụ**. Không nhất thiết nhét mọi thông tin vào tên file, nhưng cần có **danh mục và manifest nhất quán**, được bảo vệ và kiểm tra định kỳ.

### 2.1. Dữ liệu thường tồn tại lâu hơn code

~~~text
Thời gian ------------------------------------------------------------>

App release:        A1 -------- A2 ---------- A3 ---------- A4
Schema:             V10 ------- V11 -- V12 ---- V13 -------- V14
Backfill:                         [bắt đầu ----- hoàn tất]
Backup:             B1            B2               B3
Các hàng dữ liệu:   dữ liệu từ A1, A2, A3 cùng tồn tại
~~~

Trong thực tế, một backup được chụp tại B2 có thể gồm schema V12 nhưng dữ liệu mới chỉ được backfill một phần. Hệ thống A3 có thể xử lý trạng thái trung gian đó nhờ cơ chế đọc tương thích, còn A1 không thể. Vì vậy một số phiên bản schema trong metadata không thay thế **hợp đồng dữ liệu lịch sử**.

### 2.2. “Application version” cũng không đủ để xác định schema

Một service release có thể:

- Được deploy ở nhiều instance theo kiểu rolling update.
- Có feature flag bật/tắt đường ghi định dạng mới.
- Dùng một cấu trúc DB được chia sẻ với các service khác.
- Có batch worker, data pipeline, admin tool và báo cáo ở phiên bản khác nhau.
- Chạy migration tách khỏi quy trình khởi động.

Một tên release không chứng minh schema đã lên phiên bản tương ứng hay mọi writer đều đã sẵn sàng cho định dạng mới. Cần có **hợp đồng tương thích rõ ràng** giữa các phiên bản và giai đoạn rollout.

### 2.3. Recovery point không tự tương đương thời điểm file được tạo

Với logical dump, dữ liệu thường đến từ một snapshot giao dịch của database; thời gian file hoàn tất không nhất thiết là thời điểm snapshot được lấy. Với PITR, tập base backup + WAL có thể được phát lại tới một **điểm phục hồi được chọn**. Với snapshot của nền tảng storage, cần hiểu lúc nào có trạng thái ứng dụng nhất quán và liệu các volume được chụp đồng bộ.

Trong runbook phải tách:

- Lúc bắt đầu công việc sao lưu.
- Thời điểm/snapshot/LSN đại diện cho dữ liệu được sao lưu.
- Lúc file/tập backup hoàn tất và được xác minh.
- Điểm khôi phục thực sự được chọn khi restore.

Nếu chỉ đặt tên file theo giờ upload hoàn tất, có thể nhầm lẫn trạng thái schema hoặc transaction mà bản sao đại diện.

## 3. Điều gì xảy ra nếu dữ liệu backup và schema không khớp?

Giả sử dịch vụ quản lý đơn hàng có ba giai đoạn:

~~~text
V1: orders(id, amount)
    amount được hiểu là VND.

V2: thêm orders.currency (nullable),
    reader hiểu NULL là VND, writer mới ghi currency.

V3: backfill xong và siết NOT NULL,
    cho phép đơn bằng USD.

V4: tách amount/currency sang bảng order_totals,
    code mới không còn dùng cột amount.
~~~

Với backup ở V1, V2 hoặc V3, các cách khôi phục có rủi ro khác nhau.

| Backup | Code khởi động | Kết quả có thể gặp |
|---|---|---|
| V1 | Chạy ngay code V4 | Thiếu bảng/cột nên SQL/JPA mapping lỗi |
| V1 | Chạy migration V2–V4 rồi code V4 | Có thể đúng **nếu** migration/backfill tương thích với dữ liệu và code thực |
| V2, backfill dở | Chạy code V3 chỉ đọc non-null currency | Một phần hàng có thể lỗi hoặc bị hiểu sai |
| V3, đã ghi USD | Chạy code V1 coi mọi amount là VND | SQL có thể vẫn chạy, nhưng sai ý nghĩa tiền tệ |
| V4 | Chạy code V2 | Code cũ có thể truy cập cột đã bị bỏ |
| V3 | Khôi phục từ backup và replay WAL đến V4 | Phải xem schema/migration sẽ thay đổi theo WAL và dữ liệu đến điểm đích |

Đây là ba loại lỗi khác nhau:

1. **Không tương thích cấu trúc:** bảng/cột/kiểu/constraint hoặc function thiếu.
2. **Không tương thích ngữ nghĩa:** dữ liệu được parse nhưng mang nghĩa khác, nguy hiểm vì không chắc có exception.
3. **Không tương thích trạng thái chuyển tiếp:** schema cho phép cả cũ và mới, nhưng backfill và writer chưa đạt điều kiện để bỏ fallback.

Chỉ nhìn `SELECT version FROM schema_history` không đủ bắt cả ba.

## 4. Thông tin phiên bản nào nên đi cùng tập backup?

### 4.1. Manifest là bằng chứng mô tả, không tự là nguồn sự thật

Một backup manifest có thể là JSON hoặc YAML được tạo bởi quy trình backup, lưu trong vùng được bảo vệ. Ví dụ **minh họa**, không phải định dạng bắt buộc của Flyway/PostgreSQL:

~~~yaml
backupId: orders-db-2026-11-22-sample
backupKind: logical-pg-dump-custom
database:
  engine: postgresql
  engineVersion: "16.x-example"
  databaseName: orders_db
  schemaVersion: "V15"
  migrationTool: flyway
  migrationHistoryDigest: "sha256:illustrative-not-a-real-hash"
  backfillState:
    currencyBackfill: complete
    previousFieldDualWrite: disabled
application:
  minimumCompatibleRelease: "orders-service-2.4.0"
  testedRestoreRelease: "orders-service-2.4.2"
recovery:
  logicalSnapshotRecordedAt: "2026-11-22T01:00:00Z"
  restorePoint: "logical-snapshot"
artifacts:
  dumpFile: "orders-db.dump"
  sha256: "illustrative-real-manifest-needs-hash"
security:
  classification: confidential
  encryptionKeyReference: "kms-key-version-reference"
  retentionClass: "daily"
restoreValidation:
  status: "not-yet-tested"
~~~

Những chuỗi `example`/`illustrative` ở trên là **giá trị trình bày**, không dùng để tự động hóa thật. Manifest thực phải được sinh từ hệ thống xác minh, không tự gõ “complete” khi không có phép kiểm được ghi nhận.

Cần tách hai loại thông tin:

- **Thực tế đo được:** engine version, thời điểm chụp, hash file, schema history đọc từ DB, trạng thái validation.
- **Hợp đồng vận hành:** các app release được phép dùng, trình tự migration, chính sách retention, vai trò cần phê duyệt.

Một trường như `minimumCompatibleRelease` không thể suy ra chắc chắn chỉ từ version Flyway; nó phải được xác lập bằng kiểm thử hoặc tài liệu release.

### 4.2. Những điều manifest cần liên kết

- **Backup set ID** và danh mục các file/thành phần thực sự có mặt.
- **Digest/checksum** của file/tập file, kích thước và thời gian tạo.
- **Snapshot/recovery point** theo cơ chế backup đang dùng.
- **Engine và tool version** như PostgreSQL, `pg_dump`, `pg_restore`, backup agent, extension quan trọng.
- **Schema migration state**: version, checksum/history, lỗi/pending và vị trí bảng lịch sử nếu dùng.
- **Trạng thái dữ liệu chuyển tiếp** nếu có các job backfill riêng.
- **App compatibility matrix** hoặc reference tới release manifest đã kiểm chứng.
- **Dependency**: roles/global objects, sequence, object store, broker, encryption key, WAL segments, collations.
- **Encryption/key reference**, policy truy cập và retention, nhưng **không lưu plaintext secret**.
- **Kết quả restore drill**: ngày, môi trường, bằng chứng test và hạn tin cậy.

Không công khai manifest nếu trong đó có thông tin nội bộ nhạy cảm như tên nguồn, sơ đồ hệ thống hoặc identifier của backup; không ghi password hay data key dưới dạng rõ.

### 4.3. Checksum file và checksum migration có vai trò khác nhau

**Checksum của backup file** giúp phát hiện byte thay đổi ngoài ý muốn sau khi tạo: bảo vệ một phần tính toàn vẹn bản sao. Nếu attacker sửa cả file và checksum metadata, vẫn cần cơ chế bảo vệ manifest, chữ ký hoặc kho bất biến.

**Checksum migration** do Flyway/Liquibase quản lý giúp phát hiện file migration đã áp dụng bị thay đổi nội dung theo cách công cụ hỗ trợ. Nó **không chứng minh dữ liệu backup còn nguyên**, và cũng không thay thế checksum của dump/WAL.

Cần lưu hai loại bằng chứng riêng thay vì dùng tên “checksum” chung cho mọi kiểm tra.

## 5. Schema history nằm đâu và có được sao lưu không?

### 5.1. Flyway: lịch sử migration nằm trong database được cấu hình

Trong cách dùng Flyway phổ biến, một bảng lịch sử như `flyway_schema_history` lưu trạng thái migration đã áp dụng, phiên bản và checksum theo schema cấu hình. Nếu `pg_dump` sao lưu toàn bộ database chứa bảng này, **thông tin trong bảng tại snapshot sẽ được đưa vào dump**, trừ khi pipeline chủ ý loại trừ schema/bảng đó.

Nhưng có nhiều ngoại lệ cần kiểm tra:

- Chỉ dump một vài table, bỏ qua schema chứa lịch sử.
- Công cụ migration dùng database hoặc schema quản trị khác.
- Lịch sử migration được sửa bằng `repair` hoặc thủ tục quản trị; dữ liệu lịch sử có thể không phản ánh toàn bộ thay đổi ngoài tool.
- DDL được chạy thủ công ngoài Flyway.
- Một số backfill hoặc quá trình tạo index có pipeline riêng không được ghi trong bảng lịch sử.

**Bảng history là manh mối quan trọng, không phải chứng cứ tuyệt đối** rằng schema/data tương ứng với code hiện tại.

### 5.2. Liquibase: changeset, checksum và lock

Liquibase thường lưu thông tin changeset trong các bảng quản trị như `DATABASECHANGELOG`, dùng cơ chế lock phù hợp để điều phối thực thi. Điều cần kiểm tra tương tự: bảng history nào được backup, changeLog đang được dùng là bản nào và changeset có tương thích với môi trường restore.

Không xem việc table đã có record “executed” là bằng chứng mọi phần dữ liệu mà change đó dự định chuyển đổi **đã hoàn tất**, nếu bản thân job backfill chạy bên ngoài migration tool.

### 5.3. Phát hiện schema drift

**Schema drift** xảy ra khi cấu trúc đang chạy không khớp trạng thái được kỳ vọng từ các migration có version. Các nguyên nhân:

- DBA sửa một constraint trực tiếp.
- Một môi trường chạy DDL thủ công không được commit vào repository.
- Migration thất bại một phần trên DBMS/DDL không có transaction như kỳ vọng.
- Công cụ auto-DDL của ORM bổ sung cột khi khởi động.
- Restore chỉ chọn một vài bảng vào database đã có cấu trúc khác.

Một bước xác minh cần so sánh **schema thực**, **history**, **DDL source đã versioned** và **mapping ứng dụng**. Ví dụ JPA schema validation phát hiện một số lỗi cột/kiểu, nhưng không kiểm tra được tất cả trigger, index, privilege và bất biến nghiệp vụ.

## 6. Logical backup: sao lưu schema và dữ liệu nhất quán ở mức nào?

### 6.1. PostgreSQL `pg_dump`

Một ví dụ sao lưu logic **một database** trong môi trường được cấp quyền:

~~~bash
pg_dump \
  --dbname="orders_db" \
  --format=custom \
  --file="/secure-backups/orders-db.dump"
~~~

Đây là lệnh minh họa, không phải runbook production đầy đủ: host, xác thực, mã hóa, quyền thư mục và tính nhất quán của hệ thống bên ngoài phải được cấu hình qua đường được phê duyệt.

Điểm cần hiểu:

1. `pg_dump` có thể tạo bản chụp logic nhất quán giao dịch của một database, gồm định nghĩa schema và dữ liệu đối tượng được chọn.
2. Nếu dump toàn database, các bảng ứng dụng và bảng lịch sử migration nằm trong phạm vi dump theo cơ chế và quyền phù hợp.
3. Một custom dump cần công cụ restore tương thích, thường dùng `pg_restore`.
4. `pg_dump` không tự chứa tất cả global objects của PostgreSQL cluster, chẳng hạn role/ tablespace definitions ở cấp cluster; phải có chiến lược riêng.
5. Dump không tự sao lưu object storage, event broker, cache hoặc search index.
6. Dump không tương đương base backup + WAL cho nhu cầu **PITR**, cũng không thể suy ra mọi transaction sau snapshot có mặt.

Với nhiều schema hoặc nhiều database, cần xác minh ranh giới nhất quán. Một lần dump từng database độc lập không tự tạo snapshot toàn cục đồng thời của cả hệ thống.

### 6.2. DDL xảy ra đồng thời với backup thì sao?

Trong khi `pg_dump` chạy, một migration có thể muốn thay bảng đang được dump. PostgreSQL sử dụng cơ chế snapshot và lock thích hợp cho `pg_dump`; DDL có thể bị chặn hoặc công cụ phát hiện xung đột tùy thao tác/cách chạy. **Không nên** thiết kế theo giả định rằng bất kỳ DDL nào trong lúc dump cũng vô hại.

Quy trình production có thể:

- Định thời gian backup theo lịch và tránh những DDL phá cấu trúc ở thời điểm nhạy cảm.
- Dùng orchestration để biết có migration đang thực thi.
- Ghi nhận điểm snapshot, phiên bản schema và kết quả dump.
- Kiểm tra restore thay vì chỉ tin rằng dump đã thành công.
- Đặt timeout/giám sát lock hợp lý, tránh backup và migration gây nghẽn lẫn nhau.

Nếu pipeline gắn `schemaVersion=V15` **sau khi** dump đã hoàn tất nhưng migration V15 chạy giữa quá trình backup, metadata có thể không còn mô tả đúng snapshot. Cần lấy thông tin schema history và dữ liệu **trong cùng ngữ cảnh snapshot** hoặc ghi nhận điểm thời gian có thể đối chiếu, rồi xác minh từ bản restore.

### 6.3. Không trộn dump schema và dump data ở hai thời điểm tùy tiện

Một thiết kế dễ sai:

~~~text
01:00: pg_dump --schema-only -> schema V10
01:05: migration V11 thêm cột và writer bắt đầu ghi dữ liệu mới
01:10: pg_dump --data-only   -> data đã theo V11
Restore: schema V10 + data V11 -> lỗi hoặc sai ánh xạ
~~~

Với full dump, công cụ quản lý snapshot logic trong phạm vi được hỗ trợ. Nếu bắt buộc tách schema và data, phải có **snapshot coordination** phù hợp và cơ chế xác minh, không chỉ đặt hai file cùng ngày rồi coi như một backup set.

PostgreSQL có cơ chế exported/synchronized snapshots cho một số luồng sao lưu song song theo điều kiện cụ thể; chi tiết phải dùng đúng tài liệu công cụ/phiên bản. Nếu không chắc, ưu tiên tập backup được tạo theo một quy trình đã được thử restore toàn vẹn.

## 7. Physical backup, engine version và PITR

### 7.1. Physical backup chứa trạng thái vật lý và catalog

Một physical/base backup của PostgreSQL theo cơ chế được hỗ trợ giữ cấu trúc file dữ liệu/catalog cần thiết cho việc khôi phục cluster. Đó không phải tập các câu `CREATE TABLE` và `INSERT` độc lập với engine.

Khi restore:

- Cần **DBMS version tương thích với dạng physical data files**; không coi việc copy data directory sang một major version khác là phương pháp nâng cấp.
- Cần cấu hình và extension/binary tương ứng.
- Nếu phục hồi bằng WAL, cần đúng chuỗi WAL, timeline và recovery target.
- Cần tính đến quyền file, tablespace, key mã hóa, collation/locale và cấu hình.
- Khi thay engine major version, sử dụng quy trình nâng cấp/logic export/import do vendor hỗ trợ, không suy đoán binary compatibility.

### 7.2. PITR sẽ tái tạo cả DDL nếu nằm trong WAL được replay

Giả sử:

~~~text
10:00: base backup (schema V20)
10:10: migration V21 COMMIT
10:25: UPDATE hàng nghiệp vụ theo V21
10:40: migration V22 COMMIT
11:00: phát hiện cập nhật sai

Recovery target A = 10:05 -> schema V20
Recovery target B = 10:30 -> schema V21 + các thay đổi đã commit
Recovery target C = 10:50 -> schema V22
~~~

Trong PostgreSQL PITR, hệ thống replay WAL tới điểm được chọn. Các thay đổi DDL và dữ liệu đã commit có mặt trong WAL tương ứng sẽ được khôi phục theo cơ chế recovery, không yêu cầu chạy lại Flyway để “đến V21” nếu migration đã nằm trong chuỗi WAL được replay đến B.

**Điểm đặc biệt quan trọng:** nếu restore đến B rồi *chạy lại migration V21* không kiểm tra bảng history và schema, có thể gây lỗi trùng cột, phá dữ liệu hoặc thay đổi sai. Phải **inspect trạng thái phục hồi trước** khi quyết định migration cần tiếp tục từ đâu.

### 7.3. Timeline và thứ tự các thay đổi

Một trường hợp hệ thống trải qua failover/PITR nhiều lần có thể có các timeline WAL khác nhau. Không được ghép các WAL segment từ nhánh lịch sử không tương ứng với base backup/recovery target một cách tùy tiện.

Manifest và runbook của physical/PITR backup phải xác định rõ base backup nào, WAL archive nào, timeline/restore target nào và điều kiện khôi phục. Cách đặt tham số recovery phụ thuộc phiên bản PostgreSQL; nên dùng tài liệu vận hành đúng phiên bản thay vì một lệnh copy dữ liệu đơn giản.

### 7.4. Replication không thay thế lịch sử migration và backup

Read replica thường nhận DDL và ghi dữ liệu từ primary theo cơ chế replication. Nếu người vận hành xóa nhầm một cột hoặc chạy migration sai, replica có thể cũng phản ánh sai lầm đó. Dùng replica để tạo backup có thể giảm tải primary theo điều kiện nền tảng, nhưng vẫn cần bảo đảm snapshot nhất quán, WAL và tập dependency.

**Có replica** không đồng nghĩa **có khả năng phục hồi về schema/data trước sai lầm**.

## 8. Restore phải chọn đường tương thích trước khi chạy mã ứng dụng

Trước khi restore dữ liệu cũ, hãy đưa ra hai quyết định tách biệt:

1. **Mục tiêu phục hồi là gì?** Khôi phục hệ thống như thời điểm cũ, hay phục hồi dữ liệu cũ vào release hiện tại?
2. **Đường tiến hóa là gì?** Chạy ứng dụng tương thích với backup trước, hoặc áp dụng migration lên bản restore để đưa dữ liệu lên schema mới?

Không tự động cho một bản code mới nhất chạy migration trên bản restore **chưa được xác minh** chỉ vì hệ thống từng chạy ổn với một database mới tạo.

### 8.1. Hai chiến lược phục hồi phổ biến

| Chiến lược | Dùng khi | Điều cần kiểm tra |
|---|---|---|
| **Khôi phục cùng thế hệ** | Muốn tái tạo trạng thái ở thời điểm backup/PITR | Release ứng dụng, engine, schema và dependencies phù hợp với thời điểm đó |
| **Restore rồi roll-forward** | Muốn đưa dữ liệu cũ lên release hiện tại | Chuỗi migration còn sẵn, backfill đúng, không mất ngữ nghĩa, kiểm thử với dữ liệu backup |
| **PITR rồi kiểm tra migration đã replay** | Muốn loại bỏ giao dịch sai nhưng giữ các thay đổi đã commit trước điểm recovery | Schema history và DDL tại recovery target, không chạy lại migration đã replay |
| **Khôi phục chọn lọc** | Muốn lấy lại một bảng/hàng bị xóa nhầm | Khác biệt schema và FK giữa nguồn backup với database đang chạy, đối soát xung đột |
| **Blue/green restore** | Muốn kiểm tra hệ mới trước chuyển traffic | Chuyển tiếp thay đổi, cutover, rollback, đồng bộ hệ ngoài |

Quyết định phải dựa trên tính đúng đắn nghiệp vụ, RPO/RTO, quyền và rủi ro dữ liệu mới bị mất khi restore. Một phương án có thể restore nhanh nhưng vẫn không phù hợp nếu xóa mất các đơn hợp lệ sau thời điểm backup.

### 8.2. Ma trận version tối thiểu cần thử

| Backup | Schema tại backup | App định chạy | Cần làm gì? |
|---|---|---|---|
| B10 | V10 | App A10 | Kiểm tra restore nguyên trạng, dữ liệu và quyền |
| B10 | V10 | App A13 | Chạy migration V11–V13 có kiểm chứng, kiểm tra dữ liệu cũ |
| B12 | V12 + backfill dở | App A13 | Chạy/tiếp tục backfill, giữ fallback khi còn hàng cũ |
| B13 | V13 đã ghi format mới | App A10 | Có thể **không tương thích ngữ nghĩa**, không tự rollback |
| PITR-12 | V12 qua WAL | App A12 | Xác minh lịch sử migration đã replay; không chạy lại V12 |
| B13 | V13 | App A14 | Chỉ deploy khi schema V13 thuộc tập mà A14 có thể đọc/migrate |

Không thể xây bảng này chính xác chỉ từ ngày deploy. Nên được sinh từ **release compatibility contract**, trạng thái dữ liệu và kết quả rehearsal.

## 9. Quy trình restore an toàn với môi trường cách ly

Một khung logic:

~~~mermaid
flowchart TD
    A["Sự cố / yêu cầu phục hồi"] --> B["Chọn recovery point và backup set"]
    B --> C["Xác minh manifest, checksum, key, công cụ"]
    C --> D["Restore vào môi trường cách ly"]
    D --> E["Kiểm tra engine, schema thực, migration history"]
    E --> F{"Schema/data tương thích app mục tiêu?"}
    F -->|"Có"| G["Validation dữ liệu + kiểm thử Java"]
    F -->|"Không"| H["Lập kế hoạch migration và backfill có kiểm chứng"]
    H --> I["Chạy migration trong bản clone và kiểm tra lại"]
    I --> G
    G --> J{"Đạt RPO/RTO, bất biến và security?"}
    J -->|"Không"| K["Dừng, sửa kế hoạch hoặc chọn recovery point khác"]
    J -->|"Có"| L["Cutover có kiểm soát và giám sát"]
~~~

Các bước cụ thể:

1. **Đóng băng thay đổi phá vỡ:** kiểm soát migration deploy, writer, feature flags và thao tác DDL khác trong lúc xử lý.
2. **Ghi nhận tình trạng sự cố:** mốc thời gian, nguyên nhân, transaction cần giữ/bỏ và hệ ngoài bị ảnh hưởng.
3. **Chọn backup set/recovery target** dựa trên RPO, tính toàn vẹn và khả năng mất dữ liệu.
4. **Khôi phục trong vùng cách ly** với network egress hạn chế, tắt scheduler/outbox relay và không tái dùng secret production tùy tiện.
5. **Đọc schema thật và history** từ database vừa khôi phục; so với manifest và release target.
6. **Phân loại delta**: migration nào đã có, migration nào thiếu, backfill nào chưa xong, constraint nào cần validate.
7. **Thử migration trên bản clone** trước khi quyết định chạy production cutover; lưu số hàng thay đổi, thời gian và kết quả.
8. **Kiểm thử ứng dụng Java**, repository SQL/JPA mapping, transaction, quyền và dữ liệu liên hệ thống.
9. **Chuyển traffic có kiểm soát** khi tiêu chí về tính đúng đắn, bảo mật, RPO/RTO đạt; chuẩn bị phương án xử lý ghi phát sinh trong lúc cutover.
10. **Theo dõi hậu phục hồi** và lưu bằng chứng, version mới, sự cố đã xử lý.

Không dùng môi trường restore để phát trực tiếp các event/email/payment đến hệ thống thật nếu chưa có chiến lược đối soát và quyền. Khi cần dựng service với dữ liệu production thật, môi trường đó phải được bảo vệ tương đương và các kết nối ra ngoài phải bị kiểm soát.
## 10. Ví dụ kiểm tra phiên bản schema sau khi restore PostgreSQL

Các câu lệnh trong mục này là **minh họa kiểm tra trên database đã được khôi phục cách ly**. Không chạy một quy trình restore vào database đang phục vụ production nếu chưa xác minh chính xác đích, quyền và kế hoạch khôi phục.

### 10.1. Quan sát tập backup trước khi restore

Với một dump custom-format do `pg_dump -Fc` tạo:

~~~bash
pg_restore --list "/secure-backups/orders-db.dump"
~~~

Danh mục có thể cho biết các đối tượng được ghi trong archive và hỗ trợ xem xét khả năng khôi phục. Nhưng lệnh `--list` **không kiểm tra mọi block dữ liệu**, không chứng minh schema tương thích ứng dụng và không thay thế thực hành restore.

Với các bản backup khác, dùng công cụ verification tương ứng của nền tảng. Nếu manifest có checksum SHA-256, hãy so sánh digest thực của **đúng bytes lưu trong backup repository** với digest đã lưu và xác thực nguồn tin cậy của manifest. Không xem một checksum không được bảo vệ là chữ ký bảo mật.

### 10.2. Restore vào database đích đã được xác minh

Ví dụ:

~~~bash
pg_restore \
  --dbname="isolated_orders_restore" \
  --no-owner \
  --no-acl \
  "/secure-backups/orders-db.dump"
~~~

Lệnh này giả định đã tạo database đích riêng, có role/extension phù hợp và đường kết nối được cấu hình bảo mật. `--no-owner` và `--no-acl` bỏ qua một phần ownership/privilege metadata khi restore, có thể phù hợp môi trường test, nhưng **không phải lựa chọn tùy tiện cho khôi phục production** nếu quyền là một phần của hợp đồng phục hồi.

Không dùng `--clean` hoặc `--create` chỉ để cho lệnh “chạy được” nếu chưa hiểu tác động xóa/tạo object và chưa kiểm tra server/database đích. Dump chỉ nên được restore từ nguồn đáng tin và trong môi trường hạn chế quyền, vì nội dung backup có thể chứa định nghĩa object, extension/function hoặc dữ liệu nhạy cảm.

### 10.3. Kiểm tra phiên bản engine và cấu trúc thực

Trong `psql` ở database đã restore:

~~~sql
SELECT current_database(), current_setting('server_version');

SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema NOT IN (
    'pg_catalog', 'information_schema'
)
ORDER BY table_schema, table_name;
~~~

Đây là hai ví dụ kiểm tra tổng quan. Trong một hệ thống thực, còn cần:

- Danh mục extension và phiên bản.
- Sequence, trigger, function, view, materialized view, index.
- Role/privilege, row-level security policies, default privileges.
- Collation và khác biệt locale nếu có text index hoặc unique theo quy tắc ngôn ngữ.
- Các tablespace hoặc cấu hình vật lý có liên quan.
- Những object được ứng dụng/ETL sử dụng nhưng không nằm trong schema mặc định.

Việc một bảng tồn tại không chứng minh đầy đủ cấu trúc của nó. Các bước kiểm tra phải phù hợp với những truy vấn và bất biến thực của module.

### 10.4. Đọc trạng thái Flyway trong bản restore

Nếu dự án dùng bảng mặc định `flyway_schema_history` trong schema tương ứng:

~~~sql
SELECT
    installed_rank,
    version,
    description,
    type,
    checksum,
    success
FROM flyway_schema_history
ORDER BY installed_rank;
~~~

Đọc theo `installed_rank` cho phép quan sát thứ tự ghi nhận các migration. Một số migration có thể là **repeatable** không có `version` theo nghĩa versioned migration; do đó phép `MAX(version)` theo chuỗi không phải cách tổng quát để khẳng định trạng thái đúng nhất.

Cần kiểm tra:

1. Có migration failed hoặc trạng thái bất thường không?
2. Bảng lịch sử có cùng schema/data snapshot đã restore không?
3. Các file migration mà ứng dụng sắp chạy có checksum/description trùng lịch sử không?
4. Có thay đổi schema ngoài migration tool không?
5. Bản khôi phục ở trạng thái **expand**, **backfill dở**, hay **contract**?
6. Có migration repeatable cần chạy lại và có tác dụng phụ nào không?
7. Các version còn thiếu có đường chạy trên DBMS version này không?

Nếu bảng history nằm ở schema khác hoặc tên đã đổi, truy vấn phải được điều chỉnh **theo cấu hình thực tế**. Không tự tạo một bảng history rỗng để làm cho Flyway “bắt đầu từ đầu” trên database đã có dữ liệu.

### 10.5. Trạng thái Liquibase

Với Liquibase, cần đọc đúng những bảng quản trị changeset và lock theo cấu hình của dự án; thông thường có bảng `DATABASECHANGELOG` và `DATABASECHANGELOGLOCK`. Gắn những bản ghi đó với changeLog source được versioned và chiến lược migrations của ứng dụng.

Không mặc định có thể thay qua Flyway mà chỉ sao chép số version. Hai công cụ có mô hình nhận diện, checksum và điều phối khác nhau; khi chuyển công cụ phải có kế hoạch baseline/mapping riêng.

### 10.6. Kiểm tra rằng schema và dữ liệu đã cùng sẵn sàng

Giả sử đã áp dụng migration thêm cột `orders.currency`, nhưng backfill có thể vẫn đang chạy. Kiểm tra trước khi bật code yêu cầu non-null:

~~~sql
SELECT COUNT(*) AS missing_currency
FROM orders
WHERE currency IS NULL;

SELECT currency, COUNT(*) AS row_count
FROM orders
GROUP BY currency
ORDER BY row_count DESC;
~~~

Câu SQL đầu tiên sẽ lỗi nếu cột `currency` chưa tồn tại. Đó là tín hiệu rằng phải chọn đường đọc/migration tương ứng, **không** phải lý do tự tạo cột bằng DDL tùy hứng.

Nếu hàng null còn tồn tại, việc chạy code mới chỉ hỗ trợ currency non-null có thể không an toàn; cần dùng reader tương thích hoặc tiếp tục backfill được thiết kế trước. Ngay cả khi kết quả null là 0, vẫn phải kiểm tra currency code và ý nghĩa số tiền — việc điền giá trị mặc định sai có thể khiến số liệu trông hợp lệ nhưng không chính xác.

## 11. Java: chặn khởi động khi database không tương thích

Trong ứng dụng Java, một lỗi phổ biến là chạy code mới với một database vừa restore có schema cũ, rồi chỉ phát hiện khi request đầu tiên gọi câu SQL không tồn tại. Một **compatibility check** tại thời điểm deploy hoặc khởi động có thể cung cấp tín hiệu sớm.

### 11.1. Định nghĩa hợp đồng tương thích rõ ràng

Ví dụ giả định một release ứng dụng yêu cầu:

~~~text
orders-service release R24:
  - bảng orders phải có cột currency và total_amount
  - orders.currency phải NOT NULL về mặt dữ liệu
  - một nhóm schema migrations tối thiểu đã hoàn tất
  - producer/consumer không được diễn giải amount là VND mặc định
  - version engine/driver và extension thuộc bộ đã kiểm thử
~~~

**Điều kiện khởi động** phải được kiểm chứng thay vì suy đoán từ một số version đơn giản. Một số điều kiện có thể kiểm tra bằng metadata và SQL; các điều kiện ngữ nghĩa như “không còn consumer hiểu USD là VND” cần bằng chứng deploy/integration tests và vận hành.

### 11.2. Ví dụ JDBC kiểm tra schema tối thiểu

Ví dụ sau chỉ dùng cho **đường kiểm tra khả năng đọc của release R24**. Nó không chạy migration và không sửa dữ liệu:

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import javax.sql.DataSource;

public final class RestoredDatabaseGuard {
    private final DataSource dataSource;

    public RestoredDatabaseGuard(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void verifyForR24() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setReadOnly(true);

            DatabaseMetaData meta = connection.getMetaData();

            if (!hasColumn(meta, "public", "orders", "currency")) {
                throw new IllegalStateException(
                    "Incompatible schema: orders.currency missing");
            }
            if (!hasColumn(meta, "public", "orders", "total_amount")) {
                throw new IllegalStateException(
                    "Incompatible schema: orders.total_amount missing");
            }

            try (Statement query = connection.createStatement();
                 ResultSet rows = query.executeQuery(
                    """
                    SELECT COUNT(*)
                    FROM public.orders
                    WHERE currency IS NULL
                    """)) {
                if (!rows.next()) {
                    throw new IllegalStateException(
                        "Cannot verify currency backfill");
                }
                if (rows.getLong(1) != 0) {
                    throw new IllegalStateException(
                        "Database contains orders without currency");
                }
            }
        }
    }

    private static boolean hasColumn(
            DatabaseMetaData meta,
            String schema,
            String table,
            String column) throws SQLException {
        try (ResultSet columns =
                 meta.getColumns(null, schema, table, column)) {
            return columns.next();
        }
    }
}
~~~

Một số lưu ý:

- Đây là **guard minh họa**, không phải quy trình xác minh toàn database: metadata không bao phủ mọi ràng buộc, index, function, permission và ý nghĩa dữ liệu.
- `Connection.setReadOnly(true)` là một yêu cầu/hint theo driver và transaction manager; quyền tài khoản phải thực sự là **read-only** nếu cần ngăn thay đổi ở database.
- `SELECT COUNT(*)` trên bảng rất lớn có thể tốn thời gian. Trong production có thể kiểm tra trên một bảng trạng thái backfill được quản lý đáng tin cậy và kết hợp validation offline; đừng biến startup thành quét toàn bộ dữ liệu.
- `DatabaseMetaData` có thể chịu ảnh hưởng cách đặt tên schema, chữ hoa/chữ thường và quyền visibility.
- Khi dùng Spring, tránh để một bộ guard tùy tiện tự mở transaction có quyền ghi hoặc thực hiện auto-migrate trên database restore chưa được duyệt.
- Kiểm tra release–schema theo ma trận tương thích **đã thử nghiệm**, không dựa duy nhất vào con số version “lớn hơn”.

Trong thực tế có thể triển khai bước xác minh này ở **deployment gate** độc lập thay vì chạy trên mọi instance khi startup, nhằm tránh quét lặp và giảm tải DB. Nếu ứng dụng không đủ quyền đọc bảng migration, dùng một identity kiểm tra riêng với quyền tối thiểu.

### 11.3. Không thực hiện migration ngầm khi database vừa restore

Một cấu hình ORM tự cập nhật schema hoặc một ứng dụng tự chạy migration ngay khi mở kết nối có thể khiến hệ thống:

- Bắt đầu DDL khi chưa biết chính xác recovery point.
- Ghi đè trạng thái trung gian còn cần điều tra.
- Chạy lại backfill với dữ liệu chưa phù hợp.
- Tranh chấp giữa nhiều instance cùng khởi động.
- Thay đổi bằng chứng sự cố trước khi hoàn tất forensic hoặc xác định RPO.

Sau restore, nên có một pha **quarantine/read-only validation**, sau đó mới cho phép migration/replay theo runbook và phê duyệt vận hành. Không coi mọi ứng dụng phải tắt tính năng Flyway/Liquibase ở startup vĩnh viễn; điều cốt lõi là **quản lý rõ thời điểm và quyền chạy migration trong kịch bản phục hồi**.

## 12. Quản lý backfill đi cùng version schema

Một migration thường gồm nhiều giai đoạn:

~~~text
V30: ADD COLUMN currency VARCHAR(3) NULL     -> schema mở rộng
Deploy R30: reader chấp nhận cột NULL
Job F30: backfill currency theo lô             -> có thể kéo dài
Deploy R31: mọi writer ghi currency
V31: VALIDATE + SET NOT NULL                  -> schema siết lại
Deploy R32: bật ghi ngoại tệ khi consumer sẵn sàng
~~~

Một bản backup được tạo khi job F30 hoàn tất 40% cần được khôi phục như một trạng thái **chuyển tiếp hợp lệ**, không bị ép qua bước V31 trước khi dữ liệu và writer đáp ứng ràng buộc.

### 12.1. Tách version schema và trạng thái chuyển đổi dữ liệu

Một bảng trạng thái ứng dụng có thể lưu metadata kiểm soát:

~~~sql
CREATE TABLE data_migration_progress (
    migration_key    TEXT PRIMARY KEY,
    phase            TEXT NOT NULL,
    last_committed_id BIGINT,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at     TIMESTAMPTZ
);
~~~

Ví dụ trạng thái:

~~~text
migration_key = "orders-currency-backfill"
phase = "RUNNING"
last_committed_id = 450000
completed_at = NULL
~~~

Tuy nhiên, `last_committed_id` chỉ đáng tin khi cách quét dữ liệu và cách commit được thiết kế đúng. Nếu ứng dụng còn tạo hàng mới với ID thấp hơn hoặc cập nhật hàng cũ trong khi backfill, một checkpoint tuyến tính chưa đủ chứng minh không còn hàng thiếu.

**Quy tắc:** trạng thái “COMPLETED” nên đi kèm phép đối soát số hàng và điều kiện writer đã ngừng tạo dữ liệu dạng cũ. Không đánh dấu hoàn tất chỉ vì job đã đến cuối bảng một lần.

### 12.2. Checkpoint phải được commit với công việc tương ứng

Một trường hợp lỗi:

~~~text
Transaction A: cập nhật 1000 orders -> COMMIT
Process crash trước khi cập nhật checkpoint bên ngoài.
Process restart: chạy lại cùng 1000 orders.
~~~

Nếu thao tác backfill là `SET currency='VND' WHERE currency IS NULL`, lần thử lại có thể không gây hại. Nhưng nếu transform là `balance = balance * factor`, chạy lại có thể **nhân đôi phép chuyển đổi**.

Cần giải pháp phù hợp:

- Idempotent update có điều kiện.
- Gắn data format/version trên từng bản ghi.
- Operation ID và unique constraint.
- Cùng transaction cho dữ liệu và checkpoint nếu có thể.
- Đối soát đầu cuối nếu checkpoint nằm ở hệ thống khác.

Không tính một job đã hoàn tất chỉ vì một bảng control ghi `phase='DONE'` khi chưa đối chiếu dữ liệu đích.

### 12.3. Snapshot của bảng progress và log ngoài DB

Nếu progress nằm trong cùng database, backup/PITR có thể chụp đồng bộ nó với các thay đổi đã commit. Nếu progress lại nằm trong file/queue hoặc monitoring service bên ngoài, trạng thái sau restore có thể lệch.

Ví dụ backup chứa orders mới đến ID 500000, nhưng checkpoint bên ngoài đang là 900000. Nếu job restart từ 900000, nó có thể **bỏ qua 400000 hàng**. Do đó các control-plane metadata quan trọng cần hoặc nằm trong phạm vi backup có nhất quán phù hợp, hoặc có cơ chế **re-derive/reconcile** sau phục hồi.

### 12.4. Thay đổi không thể đảo ngược về ngữ nghĩa

Một khi ứng dụng đã ghi đơn USD, chạy code cũ luôn coi số tiền là VND là không an toàn. Backup cũ chỉ có VND không cho phép ta tự do khởi động bản cũ trên **database hiện tại** đã có dữ liệu mới.

Rollback code, restore data và migration schema là ba hành động khác nhau:

- **Code rollback:** đổi binary/runtime.
- **Data restore:** lấy lại một trạng thái dữ liệu ở recovery point.
- **Schema migration:** chuyển cấu trúc và có thể cả ngữ nghĩa của dữ liệu.

Runbook phải mô tả những kết hợp được phép, cấm hoặc chỉ dùng sau thao tác biến đổi có kiểm chứng.

## 13. Migration files và tính tái lập của đường khôi phục

### 13.1. Không sửa migration đã áp dụng tùy tiện

Một file `V11__add_currency.sql` đã được chạy trong production có thể còn cần để tái dựng bản restore V10. Nếu developer chỉnh nội dung file V11 mà không tạo phiên bản mới, pipeline restore có thể:

- Gặp checksum mismatch.
- Chạy một logic V11 khác với thứ từng chạy ở production.
- Diễn giải dữ liệu lịch sử không theo giả định ban đầu.
- Khó so sánh giữa backup và bản code đang chạy.

Thông thường nên coi migration versioned đã áp dụng là **artifact bất biến**, muốn thay đổi tiếp thì tạo migration mới. Trường hợp sửa/repair có thể cần theo chính sách công cụ nhưng phải có quyết định kỹ thuật, review và dấu vết rõ.

### 13.2. Lưu đủ artifact cho restore cũ

Một restore từ V10 lên V15 có thể cần:

- DDL và dữ liệu migration V11–V15.
- Code backfill ngoài Flyway, bao gồm version/commit xác định.
- Cấu hình feature flags của giai đoạn chuyển tiếp.
- Library/driver tương thích.
- Các script xử lý ngoại lệ và dữ liệu bất thường.
- Mapping event schema và adapters cho consumer cũ.
- Tài liệu điều kiện tiên quyết và thứ tự chạy.

Nếu repository hiện tại xóa mất backfill code v11 vì “không còn sử dụng”, ta có thể có bản backup V10 nhưng **không còn khả năng đưa nó lên release hiện tại một cách có kiểm chứng**.

Lưu trữ migration và artifact cần có version control, integrity checking, quyền hẹp và retention phù hợp với **thời hạn phải có khả năng restore**. Dữ liệu bí mật/credential không được đóng gói trực tiếp trong artifact.

### 13.3. Migration repeatable và thay đổi qua thời gian

Một số công cụ cho phép migration repeatable chạy lại khi nội dung đổi. Đây có thể là cơ chế tiện lợi cho view/function, nhưng trong kịch bản restore phải biết:

- Nó có đụng tới dữ liệu hoặc object thật không?
- Nó đã chạy lại sau thời điểm snapshot chưa?
- Bản mới có tương thích với schema vừa restore không?
- Nếu chạy lại, tác động lên index, hiệu năng, quyền và transaction là gì?

Không dùng repeatable migration để lén biến đổi dữ liệu không idempotent mà không có điều kiện và kế hoạch rollback/roll-forward.

## 14. Backup, schema và những phụ thuộc ngoài database

Một backup PostgreSQL có thể tái dựng bảng `orders` và outbox, nhưng hệ thống nghiệp vụ có thể còn lưu:

- File hóa đơn và ảnh trong object storage.
- Event đã publish vào message broker.
- Trạng thái thanh toán tại đối tác.
- Bản sao ở search index.
- Cache và session state.
- Feature flags/config đã dùng lúc dữ liệu được ghi.
- Khóa mã hóa và version của khóa.

### 14.1. Tình huống DB bị restore lùi nhưng broker không lùi

Giả sử lúc 12:00, event `OrderCreated(id=42, version=3)` đã được publish. Vì lỗi dữ liệu, DB được PITR về 11:55, khi đơn này chưa tồn tại. Broker vẫn giữ event và consumer đã xử lý.

Nếu ứng dụng Java phục hồi rồi gửi lại các event cũ từ outbox, có thể có:

- **Duplicate** event hoặc duplicate side effect.
- Consumer giữ đơn 42 trong search dù source DB đã quay về trước lúc tạo.
- Thanh toán bên ngoài đã thực hiện nhưng DB không còn record tương ứng.
- Khóa hoặc ID của một lệnh có thể bị tái sử dụng không đúng nếu sequence/operation ID không được thiết kế.

Restore database **không tự rollback hệ thống phân tán**. Cần chiến lược reconciliation với broker, search, object store, payment và các ledger có thẩm quyền. Đối với thanh toán, không đơn giản “phát lại toàn bộ event” hoặc “gửi lại yêu cầu thu tiền” nếu chưa kiểm tra idempotency và trạng thái phía provider.

### 14.2. Outbox/inbox cần đối soát phiên bản

Transactional outbox được ghi cùng đơn nghiệp vụ trong DB nên phục hồi theo snapshot/PITR cùng DB. Nhưng dấu “đã gửi” trong outbox chỉ nói đến trạng thái lưu trong snapshot, không thể hiện toàn bộ những gì broker/consumer đã nhận ở thời điểm hiện tại.

Sau restore, cần:

1. Xác định những event outbox có thể được gửi lại.
2. Consumer áp dụng **event ID/idempotency**.
3. Phân biệt event cũ, sai thứ tự bằng aggregate version khi phù hợp.
4. Đối chiếu source-of-truth với search/projection.
5. Không tự gửi lại side effect ngoài DB nếu chưa biết kết quả trước restore.
6. Ghi rõ mốc cutover để hỗ trợ điều tra.

### 14.3. Search index và cache có thể cần rebuild

Sau khi DB rollback dữ liệu hoặc schema, search index có thể chứa tài liệu mới hơn, có field không còn trong schema hoặc những record vừa bị xóa trên DB. Cache cũng có thể chứa entity version từ trước PITR.

Chiến lược thường là:

- Vô hiệu hóa hoặc version namespace của cache khi cutover.
- Tạo search index mới từ trạng thái nguồn được khôi phục.
- Bắt kịp thay đổi mới sau điểm cutover bằng outbox/CDC có version.
- Kiểm tra số lượng, checksum/projection fields, stale/missing/extra document.
- Chỉ chuyển alias/read path khi index mới đạt tiêu chí hợp đồng.

Không coi “DB restore thành công” là toàn bộ ứng dụng đã nhất quán.

### 14.4. File/object storage có thể cần điểm khôi phục tương ứng

Nếu hàng `attachments` chứa key trỏ tới object store, restore DB về trước một thay đổi có thể tạo:

- Row trỏ tới object đã bị xóa sau đó.
- Object không còn row tham chiếu (orphan).
- Dữ liệu đã bị thay nhưng DB lưu metadata phiên bản cũ.

Cần object versioning/retention, metadata và chiến lược reconciliation theo nghiệp vụ. Một bản sao lưu DB không tự bao gồm mọi byte của file đính kèm.

## 15. An toàn dữ liệu khi thử restore và migration

Backup thường chứa thông tin nhạy cảm hơn một API thông thường vì có thể bao gồm toàn bộ khách hàng, token đã hết hạn, audit log và dữ liệu lịch sử. Restore drill và test migration phải được tổ chức để **không biến backup thành một kênh rò rỉ**.

### 15.1. Khu vực restore raw phải hạn chế quyền

Một quy trình có thể là:

~~~text
Encrypted backup
    -> isolated restore environment
    -> verify engine/schema/history
    -> run migration/rehearsal under approved identity
    -> sanitize/minimize data for broader QA access
    -> export only approved test dataset
    -> expire and delete all raw temporary copies
~~~

Trước khi bản sao được làm sạch:

- Không cho developer/CI truy cập tự do.
- Không mở public endpoint hoặc kết nối outbound đến email/payment/webhook thật.
- Dùng credential và encryption key qua cơ chế được phê duyệt.
- Không dump dữ liệu nhạy cảm vào log khi migration lỗi.
- Giữ quyền thấp, audit và retention.
- Không bỏ qua kiểm tra quyền chỉ vì môi trường có tên `staging`.

### 15.2. Masking có thể làm hỏng điều kiện migration

Một bẫy ít được chú ý: nếu migration cần xử lý dữ liệu cũ theo định dạng email/địa chỉ hoặc một thuộc tính có phân bố đặc biệt, việc **mask trước** có thể làm mất những ca lỗi thật. Ngược lại, để QA dùng bản raw là rủi ro.

Giải pháp:

1. Chạy phép **rehearsal cần dữ liệu gốc** trong enclave hạn chế, với kiểm soát bảo mật tương đương production.
2. Dùng các kiểm tra/số liệu tổng hợp không làm lộ PII để ghi nhận kết quả.
3. Tạo synthetic/sanitized fixture bao phủ các ca biên để cho đội QA/dev dùng rộng hơn.
4. Khi cần tái hiện một lỗi từ dữ liệu đặc biệt, chỉ chuyển **đặc tính kỹ thuật của lỗi**, không phát tán danh tính thật.

Một dataset đã mask không nhất thiết đại diện chính xác cho workload production khi đo performance, vì độ chọn lọc, skew, độ dài văn bản và tỷ lệ NULL có thể thay đổi; cần thiết kế synthetic data có phân bố phù hợp.

### 15.3. Manifest và log cũng phải được bảo vệ

Ngay cả khi manifest chỉ ghi tên database, schema và địa chỉ bucket, nó có thể giúp kẻ tấn công hiểu hạ tầng. Metadata audit phục hồi phải giới hạn quyền và không chứa mật khẩu, khóa hay connection string có secret.

Các lệnh SQL debug không nên in toàn bộ bản ghi lỗi chứa PII vào hệ thống log tập trung mà môi trường test có quyền rộng hơn. Lưu error class, constraint, migration ID và số hàng theo cách không tiết lộ dữ liệu cá nhân.

## 16. Chỉ số và bằng chứng xác nhận version–backup compatibility

Một dashboard phục hồi không nên chỉ hiển thị “backup job xanh”. Nó cần giúp trả lời **có thể dựng lại service từ backup đó hay không**.

| Tín hiệu | Mục đích |
|---|---|
| Last successful backup age | Backup có đúng lịch và mới đủ theo RPO? |
| Backup set integrity | File/manifest có khớp checksum, còn khóa giải mã? |
| Recovery point/LSN coverage | Chuỗi base backup + WAL có đạt mốc cần khôi phục? |
| Engine version compatibility | Có sẵn image/binary DB tương thích với backup? |
| Schema history snapshot match | History tại restore có giống manifest và source artifact? |
| Missing/failed migrations | Có bước nào cần chạy hoặc đã thất bại? |
| Backfill completion | Dữ liệu có đạt điều kiện schema mới? |
| App compatibility test | Release mục tiêu đọc/ghi đúng dữ liệu vừa restore? |
| Restore drill duration | RTO đạt mức nào? |
| Measured recovery point loss | RPO thực tế so với mục tiêu? |
| Constraint/data invariant checks | FK, unique, số dư, tổng tiền, trạng thái có đúng? |
| External consistency state | Broker, search, object store, payment có cần reconcile? |
| Backup/restore access audit | Ai tải, giải mã, restore hoặc thay quyền? |

### 16.1. Định nghĩa “đã xác minh” theo các cấp độ

| Cấp | Đã làm gì? | Chưa chứng minh được |
|---|---|---|
| 1. File tồn tại | Có backup set và metadata | File nguyên vẹn, đúng DB |
| 2. Integrity check | Đã xác minh bytes/manifest theo cơ chế tin cậy | SQL/schema/ứng dụng chạy được |
| 3. Archive readable | Công cụ đọc được danh mục hoặc header | Mọi hàng/constraint có thể restore |
| 4. Restore thành công | Dựng được DB mới | App, permissions, backfill, business state đúng |
| 5. App integration validated | Service Java chạy các luồng chính | Hệ ngoài đã nhất quán, RTO/RPO đạt |
| 6. Full rehearsal | Đã đo restore + validation + cutover/reconciliation theo kịch bản | Không bảo đảm mọi sự cố tương lai giống kịch bản thử |

Đừng dùng nhãn `RESTORABLE` chỉ dựa vào việc `pg_dump` trả exit code 0 hoặc `pg_restore --list` đọc được archive. Một chu kỳ restore drill với test nghiệp vụ mới cung cấp bằng chứng đầy đủ hơn.

### 16.2. Kiểm tra sự lệch phiên bản có thể tự động hóa

Một deployment/recovery gate có thể thực hiện:

1. Đọc schema version từ restored DB theo công cụ của dự án.
2. So với expected migration set và checksums được ký/versioned.
3. Kiểm tra version DBMS và những extension cần thiết.
4. Xác nhận trạng thái backfill/format migration.
5. Chạy schema validation của JPA/JDBC queries quan trọng.
6. Kiểm thử transaction rollback, unique/FK và một số luồng đọc/ghi có dữ liệu mẫu.
7. Xác minh outbox và external dependency trạng thái đang an toàn để cutover.
8. Ghi report chỉ gồm metadata và số đo, không in dữ liệu nhạy cảm.

Nếu có bất kỳ điều kiện bắt buộc nào thất bại, hệ thống nên **fail closed**: không mở traffic ghi vào bản restore chưa được xác minh.

## 17. Runbook ví dụ cho hai kịch bản

### 17.1. Kịch bản A: phục hồi sau xóa nhầm dữ liệu ở schema hiện tại

Giả sử hệ thống đang ở schema V18, lúc 10:30 có một lệnh `DELETE` nhầm, có backup vật lý + WAL và muốn phục hồi đến 10:29.

**Trước restore:**

- Ngừng các tác vụ tự động có thể ghi dữ liệu sai tiếp.
- Ghi nhận thời gian sự cố, đối tượng bị ảnh hưởng và log/audit có thể dùng.
- Kiểm tra backup set và WAL coverage bao gồm 10:29.
- Xem có giao dịch hợp lệ sau 10:29 cần khôi phục riêng không.

**Trong vùng cách ly:**

1. PITR đến recovery target phù hợp để không áp dụng DELETE sai.
2. Đọc schema/migration history trên bản restore: V18 có thể đã được replay nếu migration V18 diễn ra trước 10:29.
3. Kiểm tra dữ liệu trước/sau điểm lỗi và những bảng liên quan.
4. Không chạy lại V18 nếu đã được replay.
5. Kiểm thử release tương ứng và ràng buộc.
6. Quyết định selective data recovery hay cutover cả database tùy RPO và giao dịch mới.

**Sau khôi phục:**

- Đối soát những giao dịch hợp lệ bị bỏ qua do rollback thời gian.
- Kiểm tra broker/search/object store/outbox.
- Giám sát khác biệt schema, SQL error, replication lag và độ trễ.
- Lưu evidence: recovery point, migration state, app release, các khoản dữ liệu phải reconcile.

### 17.2. Kịch bản B: backup cũ V10, dịch vụ hiện chạy V15

Một backup logic từ ba tháng trước có schema V10; hiện code V15 yêu cầu bảng `order_totals` và currency non-null.

**Không làm:** restore V10 vào DB đang dùng rồi lập tức bật app V15 với ORM auto-update tùy cấu hình.

**Kế hoạch có thể kiểm chứng:**

1. Chọn engine/tool tương thích để restore V10 trong môi trường cách ly.
2. Khôi phục đúng schema/history của V10; xác minh checksum và dữ liệu.
3. Lấy **chuỗi migrations đã versioned V11–V15** cùng backfill artifact/feature contracts.
4. Chạy V11 mở rộng, dùng reader/writer chuyển tiếp thích hợp nếu migration cần.
5. Backfill dữ liệu lịch sử có điều kiện, kiểm chứng kết quả và các hàng ngoại lệ.
6. Chạy constraint/index và migration contract theo thứ tự đã thử nghiệm.
7. Kiểm tra mã tiền tệ, tổng, FK, sequence và quyền.
8. Khởi động release V15 trong vùng cô lập, kiểm thử use cases quan trọng.
9. Đối soát chênh lệch với source-of-truth bên ngoài nếu mục đích là phục hồi dịch vụ hiện tại.
10. Chỉ quyết định cutover khi đã hiểu dữ liệu mới phát sinh trong ba tháng sẽ được xử lý ra sao.

Điểm cuối là quan trọng: “đưa V10 lên schema V15” không làm các transaction **đã xảy ra sau ngày backup** tự xuất hiện. Version schema tương thích là điều kiện cần, không đủ để bảo đảm RPO.

## 18. Câu hỏi kiểm chứng migration khi khôi phục

Trước khi chạy migration trên một bản restored DB, nhóm có thể dùng checklist:

- Đã xác minh backup set ID và recovery point?
- Dữ liệu thuộc đúng tenant/schema/source?
- DBMS major version và extensions phù hợp?
- Đã inspect schema thực và bảng history theo snapshot?
- Có migration nào thực thi DDL ngoài transaction hoặc không thể đảo?
- Có job backfill chưa hoàn thành hoặc ghi vào nguồn khác?
- Có script nào không idempotent khi chạy lại?
- Có generated ID/sequence cần kiểm chứng sau import?
- Có thay đổi amount/currency/timezone/collation làm đổi ý nghĩa dữ liệu?
- Có service/consumer cũ vẫn truy cập schema đang chuyển?
- Có đánh giá lock/rewrite/replication lag và resource budget?
- Có test read/write JPA/JDBC, rollback, ràng buộc và dữ liệu lịch sử?
- Có kế hoạch đối soát broker, search, cache và object store sau restore?
- Có giới hạn quyền truy cập dữ liệu production trong vùng restore?
- Có tiêu chí stop/go được chủ sở hữu dữ liệu và vận hành chấp nhận?

Không phải kịch bản nào cũng cần từng hạng mục với cùng độ sâu, nhưng những ràng buộc ảnh hưởng trực tiếp tới tính đúng đắn không được bỏ qua chỉ vì “file SQL đã có”.

## 19. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý đúng |
|---|---|---|
| Chỉ ghi tên backup và ngày tạo | Không biết schema/app/engine phù hợp | Manifest có recovery point, versions và dependencies |
| Gắn schema version bằng truy vấn sau khi dump, không đồng bộ snapshot | Metadata mô tả sai trạng thái file | Lấy/xác minh version trong cùng snapshot hoặc sau restore |
| Coi phiên bản Flyway là toàn bộ trạng thái dữ liệu | Backfill có thể mới hoàn tất một phần | Theo dõi và validate data migration riêng |
| Khởi động app mới nhất ngay trên backup cũ | SQL thiếu cột hoặc hiểu sai dữ liệu | Deployment gate và migration có kiểm chứng |
| Để ORM tự sửa schema trong lúc khôi phục | Thay đổi bằng chứng/sai thời điểm | Quarantine, inspect, chạy migration theo runbook |
| Chạy lại migration đã có trong PITR WAL | Duplicate DDL hoặc sai dữ liệu | Kiểm tra schema/history sau WAL replay |
| Sửa file migration cũ thay vì thêm migration mới | Checksum mismatch và không tái lập được | Versioned immutable migration + review |
| Chỉ dump data rồi dùng schema hiện tại | Cột/kiểu không khớp | Backup schema+data đồng bộ hoặc có mapping rõ |
| Coi physical backup dùng được trên mọi DB major | File format/catalog khác nhau | Engine version tương thích và quy trình vendor |
| Không backup role, extension hoặc key | Restore SQL có thể thiếu quyền/chức năng | Danh mục dependencies và drill restore |
| Cho rằng restore DB rollback cả broker/payment | Side effect và projection lệch | Reconciliation theo nghiệp vụ và idempotency |
| Đếm file backup mà không thử restore | Backup có thể hỏng/thiếu WAL | Restore drill với ứng dụng thật |
| Restore raw production vào test CI | Lộ dữ liệu lịch sử/secret | Enclave cách ly, masking và cấp quyền sau kiểm chứng |
| Chạy `down migration` để đảo dữ liệu đã đổi nghĩa | Có thể mất thông tin không hồi phục | Roll-forward hoặc restore/reconcile có kế hoạch |
| Không giữ backfill code cũ | Có backup nhưng không thể nâng lên release hiện tại | Lưu artifact đủ vòng đời recovery |
| Nhầm checksum migration với checksum backup | Không phát hiện file bị đổi/hỏng | Hai loại kiểm tra độc lập, manifest bảo vệ |
| Cutover khi còn phiên bản schema chưa xác minh | Ứng dụng ghi dữ liệu sai hoặc hỏng | Stop/go gate dựa trên invariant và compatibility tests |

## 20. Bài tập tự kiểm tra

### Bài 1. Backup chứa schema nào?

`pg_dump` bắt đầu lúc 01:00, kết thúc lúc 01:20. Migration V10 chạy lúc 01:10. Có thể gắn `schemaVersion=V10` cho dump chỉ dựa trên thời điểm kết thúc không?

**Gợi ý:** Không. Cần hiểu snapshot và các lock/DDL trong lúc dump, sau đó kiểm tra history/schema từ bản restore hoặc có metadata gắn đúng snapshot.

### Bài 2. Migration version nhưng backfill còn thiếu

Backup có bảng Flyway history tới V13; 20% hàng `orders.currency` vẫn null. App V14 yêu cầu currency non-null. Có thể mở traffic ngay không?

**Gợi ý:** Không. Schema version không bảo đảm data migration hoàn tất. Tiếp tục backfill/validate hoặc chạy reader tương thích theo hợp đồng trước khi bật V14.

### Bài 3. PITR và replay DDL

Base backup ở V20, WAL replay tới thời điểm sau khi migration V21 đã commit. Có cần chạy lại V21 ngay không?

**Gợi ý:** Không tự chạy lại. Kiểm tra schema và history ở bản restore; nếu DDL/migration V21 đã được replay thì cần tiếp tục từ trạng thái đó.

### Bài 4. Khôi phục bản cũ vào code mới

Backup V10 thiếu bảng `order_totals`. Code V15 cần bảng đó. Cần chuẩn bị gì?

**Gợi ý:** Restore cách ly, chuỗi migration V11–V15 và backfill logic, kiểm tra dữ liệu cũ, xác minh schema/app tương thích rồi mới cutover.

### Bài 5. Checksum file và checksum migration

Checksum của `orders-db.dump` hợp lệ nhưng Flyway báo checksum mismatch. Điều đó nói gì?

**Gợi ý:** Backup bytes có thể nguyên vẹn nhưng migration source hiện tại không khớp lịch sử. Cần điều tra file đã sửa/repair và schema drift, không coi một trong hai checksum thay thế được cái còn lại.

### Bài 6. App cũ và currency mới

Sau migration V12, app mới ghi đơn USD; app cũ vẫn hiểu mọi `amount` là VND. Nếu SQL đọc thành công, có thể coi tương thích không?

**Gợi ý:** Không. Cấu trúc có thể đọc được nhưng ngữ nghĩa tiền tệ sai; phải dùng release hỗ trợ currency hoặc giữ feature gate chưa bật.

### Bài 7. Checkpoint ngoài database

Backfill checkpoint lưu ở object store với lastId 900000; backup DB chỉ chứa công việc đã commit tới ID 500000. Có thể tiếp tục từ 900000 không?

**Gợi ý:** Không. Cần đối soát checkpoint với trạng thái data đã restore; một điểm tiến độ ngoài backup không tự nhất quán với DB.

### Bài 8. Physical backup và major version

Physical data directory từ PostgreSQL major version cũ có thể copy trực tiếp sang thư mục dữ liệu của major version mới và khởi động không?

**Gợi ý:** Không mặc định. Physical format/version cần tương thích; dùng phương pháp upgrade hoặc restore được PostgreSQL hỗ trợ.

### Bài 9. Dump toàn database và roles

`pg_dump` full database có mặc nhiên chứa tất cả role và cấu hình global của cluster không?

**Gợi ý:** Không. Cần kế hoạch riêng để bảo toàn global objects cần cho restore, quyền và extension/config.

### Bài 10. Sự kiện sau restore

DB phục hồi về trước lúc tạo order 42, nhưng broker đã nhận `OrderCreated(42)` và search vẫn có tài liệu đó. Có cần xử lý gì?

**Gợi ý:** Có. DB restore không rollback broker/search; cần đối soát source-of-truth, outbox, idempotency và projection.

### Bài 11. Một bản backup nguyên vẹn có đủ không?

Lệnh `pg_restore --list` đọc được archive và checksum đúng. Có thể công bố đạt RTO/RPO production không?

**Gợi ý:** Chưa. Phải restore hoàn chỉnh, kiểm tra ứng dụng, dependency, dữ liệu và đo điểm/thời gian phục hồi trên kịch bản cụ thể.

### Bài 12. File migration cũ bị chỉnh sửa

Developer thay `V11__add_currency.sql` sau khi nó đã chạy production. Tại sao restore từ V10 có thể nguy hiểm?

**Gợi ý:** Bản khôi phục V10 cần chạy V11, nhưng nội dung hiện tại có thể khác hành vi lịch sử, phá tính tái lập và gây mismatch. Nên giữ migration versioned đã áp dụng bất biến và thêm migration mới.

### Bài 13. Restore ở môi trường test

Một nhóm muốn copy backup production nguyên bản vào CI để kiểm thử migration rồi mới mask dữ liệu. Có an toàn không?

**Gợi ý:** Không khi CI chưa được bảo vệ tương đương production. Restore raw ở enclave được kiểm soát, thực hiện kiểm thử nhạy cảm ở đó, làm sạch trước khi mở quyền rộng.

### Bài 14. Đổi ý nghĩa dữ liệu

Một migration chuyển `amount` từ đơn vị nhỏ nhất sang đơn vị chính và làm tròn tới hai chữ số. Có thể chắc chắn viết down migration để phục hồi chính xác mọi giá trị cũ không?

**Gợi ý:** Không. Phép biến đổi có thể mất thông tin/precision. Cần xác định điểm không đảo được, kế hoạch roll-forward và nguồn backup nếu cần đối chiếu.

### Bài 15. Schema mới, dữ liệu cũ thiếu giao dịch

Đưa một backup ba tháng trước từ V10 lên V15 có giúp khôi phục những đơn đã tạo trong ba tháng đó không?

**Gợi ý:** Không. Migration giải quyết khả năng đọc/schema, không tạo ra transaction đã mất. Phải thiết kế RPO/backup/PITR và cơ chế đối soát riêng.

## 21. Tổng kết

- **Backup phải được hiểu như một tập trạng thái có phiên bản.** Nó cần gắn với schema history, data/semantic version, ứng dụng, DBMS, recovery point và những phụ thuộc liên hệ thống.
- **Schema version không đủ mô tả dữ liệu.** Backfill dở dang, feature flags và writer đa phiên bản có thể tạo các trạng thái chỉ một số release mới đọc đúng.
- **Logical dump và physical/PITR có hợp đồng khác nhau.** Logical backup cần schema/data thuộc snapshot đúng; PITR replay WAL có thể đã khôi phục DDL nên không được chạy lại migration thiếu kiểm tra.
- **Manifest và migration history bổ trợ nhau.** Digest backup bảo vệ bytes; checksum migration kiểm soát source migration; kiểm tra schema thực và dữ liệu mới xác định tính tương thích.
- **Restore phải có bước cách ly và xác minh.** Đọc schema/history, chạy migration/backfill có kiểm chứng, kiểm thử ứng dụng Java và điều kiện stop/go trước khi mở traffic.
- **Tái lập được đường nâng cấp rất quan trọng.** Lưu artifact migration cũ, backfill code, release compatibility và runbook đủ lâu cho các backup còn trong thời hạn phục hồi.
- **Đừng quên hệ thống bên ngoài.** Broker, outbox, search, cache, object store và payment có thể ở trạng thái khác điểm khôi phục DB; cần reconciliation và idempotency.
- **Khả năng restore phải được đo.** Một file backup nguyên vẹn chưa chứng minh đạt RPO/RTO hoặc khôi phục được nghiệp vụ; cần restore drill thực sự và bằng chứng kết quả.

Quản lý phiên bản lược đồ cùng dữ liệu sao lưu là một phần của **thiết kế khả năng phục hồi cho hệ thống Java**, không chỉ là quy ước đặt tên file. Khi mỗi tập backup có thể được liên kết với schema, định dạng dữ liệu, lịch sử migration, phiên bản ứng dụng và điểm khôi phục đã kiểm chứng, nhóm vận hành mới có cơ sở đưa hệ thống trở lại trạng thái **đúng nghiệp vụ, có thể giải thích và tiếp tục tiến hóa an toàn**.


