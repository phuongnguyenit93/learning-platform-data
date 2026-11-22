# Kiểm thử rollback và tính tương thích ứng dụng

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, mục tiêu là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Với bài kiểm thử này, trọng tâm là xác minh hai khả năng có liên quan chặt chẽ: **database có thể được phục hồi an toàn khi migration cần đảo ngược hay không, và các phiên bản ứng dụng có tiếp tục hoạt động đúng trong suốt quá trình thay đổi schema hay không**.

Rollback thường bị hiểu đơn giản là chạy lệnh Liquibase để đảo changeset. Trong thực tế, rollback database và rollback ứng dụng là hai hành động riêng. Đưa binary ứng dụng về phiên bản cũ không tự khôi phục schema hoặc dữ liệu. Ngược lại, rollback schema có thể làm phiên bản ứng dụng mới không còn hoạt động. Một migration có thể đảo ngược về mặt DDL nhưng không thể khôi phục dữ liệu đã bị xóa hoặc biến đổi mất thông tin.

Vì vậy, kiểm thử phải bao phủ cả vòng đời phát hành: trạng thái trước migration, trạng thái sau migration, các phiên bản ứng dụng cùng tồn tại, đường rollback, dữ liệu phát sinh trong thời gian chuyển tiếp và khả năng forward-fix khi rollback không còn an toàn.

## 1. Phân biệt rollback database và rollback ứng dụng

Có ít nhất ba thành phần có thể cần quay lại:

- **Application artifact:** JAR, image hoặc phiên bản service đang chạy.
- **Database schema:** bảng, cột, index, constraint, view, function và metadata.
- **Database data:** các giá trị đã được insert, update, chuyển đổi hoặc xóa.

Các thành phần này không tự động quay lại cùng nhau.

| Hành động | Thay đổi gì | Điều không tự động được khôi phục |
|---|---|---|
| Rollback application | Đưa code về bản cũ | Schema và dữ liệu database |
| Liquibase rollback | Thực thi rollback logic của changeset được chọn | Mọi dữ liệu đã mất hoặc side effect ngoài database |
| Restore/PITR | Khôi phục database về thời điểm/backup | Giao dịch sau điểm khôi phục và trạng thái ứng dụng |
| Forward-fix | Thêm migration mới để đưa database tới trạng thái đúng | Không đưa hệ thống về schema cũ |
| Redeploy artifact cũ | Khởi chạy binary cũ | Không đảo DDL/DML đã chạy |

Một kế hoạch release phải chỉ rõ thành phần nào sẽ được rollback và thành phần nào sẽ được giữ nguyên. Không dùng cụm từ “rollback release” nếu chưa xác định database, application và dữ liệu sẽ được xử lý thế nào.

## 2. Tính tương thích giữa ứng dụng và schema

Ứng dụng truy cập database thông qua hợp đồng schema: tên bảng/cột, kiểu dữ liệu, nullability, constraint, index, view, function và semantics của dữ liệu.

Một thay đổi schema có thể ảnh hưởng tới:

- Code đọc cột hoặc bảng.
- Code ghi giá trị vào cột.
- ORM mapping và validation.
- Stored procedure, view, trigger.
- Batch job, ETL, báo cáo và consumer khác.
- Phiên bản ứng dụng cũ đang chạy trong rolling deployment.

Cần kiểm tra cả hai chiều:

1. Ứng dụng cũ có hoạt động với schema sau khi mở rộng không?
2. Ứng dụng mới có hoạt động với schema trước khi contract hoàn tất không?

Không phải mọi release đều cần hỗ trợ hai chiều hoàn toàn. Nhưng trong giai đoạn rolling deployment, thường có thời điểm code cũ và mới cùng truy cập một schema. Hợp đồng chuyển tiếp phải được thiết kế cho khoảng thời gian đó.

### 2.1. Compatibility matrix

Ví dụ thay đổi thêm cột delivery_status:

| Ứng dụng | Schema cũ | Schema sau expand | Schema sau contract |
|---|---:|---:|---:|
| App 1.8 | PASS | PASS nếu cột mới nullable và code cũ không phụ thuộc thay đổi | Có thể FAIL nếu code cũ còn cần cột cũ |
| App 1.9 | Không nhất thiết PASS | PASS, đọc/ghi cột mới | PASS |
| App 2.0 | Không nhất thiết PASS | PASS | PASS sau khi cột cũ được loại bỏ |

Bảng này là ví dụ. Mỗi thay đổi cần ma trận riêng dựa trên truy vấn và hành vi thật. Đừng giả định “cột mới không bắt buộc” đồng nghĩa mọi ứng dụng cũ đều tương thích: trigger, view, SELECT *, mapping ORM hoặc stored procedure có thể bị ảnh hưởng.

## 3. Chiến lược expand-and-contract

Expand-and-contract chia một thay đổi breaking thành nhiều release nhỏ để ứng dụng và database có thời gian chuyển tiếp.

    Trạng thái ban đầu
       |
       v
    EXPAND
    Thêm cấu trúc mới, giữ cấu trúc cũ
       |
       v
    COMPATIBLE APPLICATION
    Deploy code đọc/ghi tương thích
       |
       v
    BACKFILL / RECONCILE
    Chuyển dữ liệu cũ và đối chiếu
       |
       v
    SWITCH
    Chuyển đọc chính sang cấu trúc mới
       |
       v
    OBSERVE
    Xác nhận không còn consumer cũ
       |
       v
    CONTRACT
    Xóa cấu trúc cũ ở release sau

### 3.1. Giai đoạn expand

Chỉ thêm cấu trúc không làm hỏng code đang chạy, chẳng hạn cột nullable, bảng mới hoặc index. Không xóa/đổi tên cột mà phiên bản cũ còn sử dụng.

Kiểm thử:

- App cũ khởi động và chạy truy vấn trên schema đã expand.
- App cũ vẫn ghi dữ liệu đúng.
- Migration có thể chạy lại qua các môi trường mà không tạo cấu trúc sai.
- Không có lock hoặc table rewrite vượt ngưỡng.

### 3.2. Giai đoạn compatible application

Triển khai code mới có thể đọc dữ liệu cũ và mới, hoặc ghi đồng thời theo chiến lược đã định. Nếu dual-write, phải kiểm tra consistency khi một trong hai lần ghi thất bại.

Không bật dual-write một cách tùy tiện. Nếu hai cột được cập nhật trong hai câu lệnh riêng, crash giữa hai câu có thể tạo dữ liệu lệch. Có thể cần một transaction cùng database, outbox, hoặc job reconciliation tùy kiến trúc.

### 3.3. Giai đoạn backfill và reconcile

Chuyển dữ liệu theo batch, có checkpoint, idempotency và giới hạn tải. Đối chiếu số dòng, checksum theo khóa hoặc quy tắc nghiệp vụ phù hợp. Chỉ chuyển consumer sang dữ liệu mới khi hậu điều kiện đạt.

### 3.4. Giai đoạn contract

Chỉ xóa cột/bảng cũ sau khi:

- Không còn phiên bản ứng dụng nào đọc/ghi cấu trúc cũ.
- Batch job và integration đã được chuyển.
- Monitoring không còn truy vấn/traffic cũ.
- Có bản sao/backup hoặc phương án phục hồi đã được kiểm thử.
- Release có thể chấp nhận mất khả năng quay về phiên bản cũ.

Contract thường nên nằm ở release riêng để tạo một khoảng quan sát sau khi switch.

## 4. Xác định rollback contract cho từng changeset

Liquibase hỗ trợ rollback tự động cho nhiều change type, nhưng khả năng này phụ thuộc loại thay đổi và phiên bản. SQL tùy chỉnh thường cần rollback được khai báo rõ. Một rollback statement hợp lệ về cú pháp vẫn có thể không an toàn về dữ liệu.

Trước khi viết changeset, ghi lại:

- Trạng thái trước thay đổi.
- Trạng thái sau thay đổi.
- Rollback statement hoặc rollback procedure.
- Dữ liệu có bị mất không.
- Rollback có phụ thuộc ứng dụng đã ngừng ghi không.
- Có side effect ngoài database không.
- Điều kiện để rollback được phép chạy.
- Hậu điều kiện cần kiểm tra sau rollback.

### 4.1. Phân loại khả năng đảo ngược

| Loại thay đổi | Khả năng rollback thường gặp | Rủi ro |
|---|---|---|
| Thêm cột nullable | Có thể drop cột | Mất dữ liệu mới đã ghi vào cột |
| Thêm index | Có thể drop index | Hiệu năng giảm; drop có thể cần lock |
| Thêm constraint | Có thể drop constraint | Mất bảo vệ dữ liệu |
| Đổi tên cột | Có thể đổi tên ngược | App phiên bản mới có thể vẫn cần tên mới |
| Backfill | Không tự đảo chính xác | Không biết giá trị cũ nếu không lưu |
| Xóa dữ liệu | Thường không thể rollback nếu không có bản lưu | Mất dữ liệu vĩnh viễn |
| Thay đổi kiểu có mất thông tin | Có thể không chuyển ngược | Mất precision, format hoặc leading zero |
| Tạo view/function | Thường có thể drop/restore definition | Consumer có thể đang phụ thuộc |

### 4.2. Rollback có thể làm mất dữ liệu mới

Ví dụ thêm cột status mới, ứng dụng mới đã ghi giá trị vào cột. Rollback bằng DROP COLUMN sẽ xóa các giá trị đó. Nếu sau đó deploy lại app mới, dữ liệu không còn.

Trước khi cho phép rollback, cần quyết định có chấp nhận mất dữ liệu phát sinh sau migration không. Nếu không, cần giữ cột, chuyển dữ liệu ngược hoặc forward-fix.

## 5. Khai báo rollback trong Liquibase

Ví dụ thêm cột có rollback:

    databaseChangeLog:
      - changeSet:
          id: orders-100-add-delivery-status
          author: database-team
          changes:
            - addColumn:
                schemaName: app
                tableName: orders
                columns:
                  - column:
                      name: delivery_status
                      type: VARCHAR(24)
          rollback:
            - dropColumn:
                schemaName: app
                tableName: orders
                columnName: delivery_status

Rollback này chỉ phù hợp nếu dữ liệu trong cột mới có thể bị loại bỏ. Trong production, phải kiểm tra ứng dụng đã ghi dữ liệu mới chưa và có cần lưu/export dữ liệu trước khi drop không.

### 5.1. Rollback cho SQL tùy chỉnh

Ví dụ tạo view:

    databaseChangeLog:
      - changeSet:
          id: reporting-020-create-open-orders-view
          author: database-team
          changes:
            - sql:
                sql: |
                  CREATE VIEW app.open_orders AS
                  SELECT id, customer_id, created_at
                  FROM app.orders
                  WHERE status = 'OPEN';
          rollback:
            - sql:
                sql: DROP VIEW app.open_orders;

Cú pháp và cách xử lý dependency cần được xác minh trên DBMS mục tiêu. Nếu view được view khác hoặc application phụ thuộc, rollback cần dừng consumer hoặc xử lý thứ tự dependency trước.

### 5.2. Khi nào cần custom rollback?

Cần rollback tùy chỉnh khi:

- SQL change không có rollback tự động phù hợp.
- Dữ liệu cần chuyển ngược theo mapping.
- Phải xóa hoặc phục hồi đối tượng theo thứ tự dependency.
- Cần điều kiện trước khi rollback.
- Có khác biệt DBMS.
- Rollback cần kiểm tra hậu điều kiện nghiệp vụ.

Nếu không thể đảo ngược an toàn, đừng tạo rollback giả chỉ để pipeline có một đoạn rollback. Ghi rõ thao tác cần forward-fix hoặc restore.

## 6. Kiểm thử rollback bằng Liquibase CLI

Các lệnh preview giúp xem SQL trước khi thực thi. Tên command và option có thể khác theo phiên bản Liquibase; hãy dùng help của đúng version đã pin.

Ví dụ luồng kiểm tra:

    liquibase validate
    liquibase status --verbose
    liquibase update-sql

Sau khi cập nhật trên database thử nghiệm và đặt tag tại mốc phù hợp:

    liquibase rollback-sql --tag=before-release-2.1
    liquibase rollback --tag=before-release-2.1

Rollback SQL preview phải được review trước khi chạy. Không chạy rollback trực tiếp trên production chỉ vì lệnh preview trông hợp lý.

### 6.1. Tag phải đặt ở đúng thời điểm

Tag nên đại diện cho mốc database mà release có thể quay về. Cần thống nhất tag được tạo trước hay sau một nhóm changeset và kiểm tra ý nghĩa của tag theo phiên bản Liquibase đang dùng.

Không tái sử dụng tên tag cho các trạng thái khác nhau giữa môi trường. Ghi tag, artifact version, database target và thời điểm vào release record.

### 6.2. Kiểm tra lịch sử sau rollback

Sau khi rollback, xác minh:

- Changeset liên quan được xử lý đúng theo semantics của Liquibase.
- DATABASECHANGELOG phản ánh lịch sử hiện tại.
- Schema thực tế đúng trạng thái mục tiêu.
- Dữ liệu cần giữ vẫn còn.
- Ứng dụng tương thích với schema sau rollback.
- Không còn lock hoặc transaction dang dở.

Không chỉ nhìn output “Rollback completed”. Phải kiểm tra catalog, dữ liệu và ứng dụng.

## 7. Kiểm thử rollback trên database riêng biệt

Mỗi lần kiểm thử rollback nên dùng database có thể reset hoặc restore. Không thử trên database production hoặc môi trường dùng chung nếu chưa có kế hoạch và phê duyệt phù hợp.

Một chu trình test:

1. Tạo database từ trạng thái baseline.
2. Chạy migration đúng artifact/config.
3. Tạo dữ liệu đại diện, gồm dữ liệu mới do app version mới ghi.
4. Chạy rollback SQL preview.
5. Thực hiện rollback.
6. Kiểm tra schema, history và dữ liệu.
7. Chạy phiên bản ứng dụng dự kiến sau rollback.
8. Chạy smoke test và truy vấn nghiệp vụ.
9. Ghi nhận thời gian, lock và lỗi.

Phải test trên đúng DBMS và version production. H2 hoặc một engine khác không mô phỏng đầy đủ transaction DDL, lock, index và constraint của engine thật.

## 8. Kiểm thử fresh install và upgrade path

Fresh install và upgrade path phát hiện hai nhóm lỗi khác nhau.

| Kiểu kiểm thử | Điểm xuất phát | Điều cần chứng minh |
|---|---|---|
| Fresh install | Database trống | Root changelog tạo được schema cuối |
| Upgrade path | Database từ release cũ | Các changeset mới hoạt động trên schema/data đã tồn tại |
| Rollback path | Database sau update | Rollback đưa về trạng thái được định nghĩa |
| Re-upgrade path | Database đã rollback | Có thể triển khai lại nếu release strategy yêu cầu |
| Mixed-version | Schema mở rộng, app cũ và mới cùng chạy | Không có lỗi tương thích trong cửa sổ rolling deployment |

Một migration có thể chạy tốt trên database trống nhưng thất bại trên production vì dữ liệu cũ có NULL, duplicate hoặc orphan. Upgrade path cần dữ liệu đại diện và history thực tế của release được hỗ trợ.

### 8.1. Test mọi đường nâng cấp được hỗ trợ

Nếu ứng dụng hỗ trợ nâng từ nhiều phiên bản cũ, xác định các đường nâng cấp thực tế. Không cần test mọi tổ hợp vô hạn; hãy chọn các mốc được hỗ trợ, schema drift phổ biến và môi trường có dữ liệu đặc biệt.

Ghi rõ baseline database và changeset history để kết quả test có thể tái lập.

## 9. Kiểm thử tính tương thích của ứng dụng

Kiểm thử schema không đủ. Phải chạy application binary thực tế trên từng trạng thái schema quan trọng.

Các loại test:

- Startup test: Spring context và DataSource khởi tạo thành công.
- Repository/DAO test: truy vấn và ghi dữ liệu đúng.
- Contract test: cột, kiểu, nullability và semantics được giữ.
- Integration test: transaction, constraint và trigger hoạt động.
- API regression: request/response không đổi ngoài dự kiến.
- Background job test: batch, scheduler và message consumer tương thích.
- Performance test: query plan và latency không suy giảm ngoài ngưỡng.
- Mixed-version test: app cũ và mới cùng chạy trên schema expand.

Nếu Hibernate dùng validate, xác minh mapping của đúng persistence unit. Không để Hibernate tự update schema trong test rồi nhầm rằng Liquibase migration đã tạo đúng cấu trúc.

### 9.1. Kiểm thử read/write compatibility

Ví dụ khi chuyển từ cột customer_name sang customer_display_name:

- App cũ chỉ đọc/ghi customer_name.
- App mới có thể đọc cả hai và ghi theo chiến lược chuyển tiếp.
- Backfill sao chép dữ liệu.
- Reconcile xác nhận hai cột nhất quán.
- Sau khi mọi writer cũ ngừng hoạt động mới contract cột cũ.

Cần test tình huống app cũ ghi trong lúc backfill, app mới ghi trong lúc app cũ vẫn còn chạy, và retry sau lỗi giữa hai lần ghi. Nếu có dual-write, phải có cách phát hiện và sửa dữ liệu lệch.

## 10. Kiểm thử rolling deployment và mixed-version

Trong rolling deployment, các instance không được thay thế đồng thời. Có thể tồn tại:

- App cũ đang xử lý request.
- App mới vừa khởi động.
- Worker/background job chưa được restart.
- Consumer message có version cũ.
- Scheduled job đang chạy từ trước release.

Vì vậy, schema phải hỗ trợ đồng thời các phiên bản cần thiết.

### 10.1. Trình tự triển khai an toàn

Một ví dụ:

1. Deploy migration expand.
2. Kiểm tra app cũ vẫn hoạt động.
3. Deploy app mới có khả năng tương thích.
4. Chờ tất cả instance/job cũ được thay thế.
5. Backfill và reconcile.
6. Chuyển read path sang cấu trúc mới.
7. Theo dõi đủ thời gian.
8. Contract trong release riêng.

Thứ tự cụ thể phụ thuộc thay đổi. Với một số thay đổi, cần deploy app tương thích trước khi bật constraint; với thay đổi khác, database có thể expand trước. Hãy mô tả rõ dependency trong release plan.

### 10.2. Kiểm thử rollback application sau expand

Đây là bài test rất quan trọng: sau khi schema đã expand và app mới đã chạy, thử đưa application về bản cũ trên database vẫn ở trạng thái expand.

Nếu app cũ không khởi động hoặc không thể ghi dữ liệu, schema expand chưa backward-compatible. Cần sửa thiết kế trước khi production rollout.

### 10.3. Kiểm thử rollback application sau backfill

App cũ có thể đọc được schema nhưng hiểu sai dữ liệu mới. Ví dụ code cũ giả định một enum chỉ có ba giá trị, trong khi app mới đã ghi giá trị thứ tư.

Hãy test dữ liệu thực tế được tạo sau migration, không chỉ kiểm tra column existence.

## 11. Kiểm thử thay đổi dữ liệu và khả năng khôi phục

Data migration thường khó rollback hơn DDL vì thông tin cũ có thể bị mất.

Ví dụ chuyển giá trị status từ chuỗi tự do sang mã số:

- Mapping cũ có thể không đơn ánh.
- Nhiều giá trị cũ có thể cùng ánh xạ một mã.
- Giá trị không nhận diện có thể bị thay thành UNKNOWN.
- App mới có thể ghi mã mà app cũ không hiểu.

Nếu cần khả năng đảo ngược, phải lưu đủ thông tin để phục hồi giá trị ban đầu, chẳng hạn bảng mapping/audit hoặc snapshot có retention phù hợp.

### 11.1. Test data rollback với dữ liệu phát sinh mới

Không chỉ test rollback ngay sau migration. Hãy tạo giao dịch mới, cập nhật dữ liệu, chạy job và để app tiếp tục hoạt động trong khoảng thời gian đại diện rồi mới thử rollback.

Điều này giúp phát hiện rollback có làm mất dữ liệu mới hoặc không thể chuyển ngược những giá trị mà app đã ghi hay không.

### 11.2. Backup không thay thế rollback test

Backup chỉ hữu ích khi restore được trong RTO/RPO yêu cầu. Test cần đo thời gian restore, tính toàn vẹn và khả năng replay giao dịch nếu có.

Point-in-time recovery có thể đưa toàn database về thời điểm trước migration, đồng thời làm mất giao dịch hợp lệ sau mốc đó. Phải hiểu tác động tới mọi service dùng chung database.

## 12. Kiểm thử DDL không transactional và partial execution

Một số DDL có thể tự commit hoặc không chạy trong transaction block. Ví dụ tạo index concurrently trên PostgreSQL cần chạy ngoài transaction. Nếu lệnh thất bại, có thể để lại đối tượng ở trạng thái invalid.

Với changeset có runInTransaction=false:

- Giữ một thao tác chính trong changeset.
- Test lỗi trước, trong và sau câu lệnh.
- Kiểm tra trạng thái vật lý sau khi cancel/timeout.
- Xác định retry có an toàn không.
- Xác minh Liquibase history.
- Có repair/cleanup procedure được review.

Không giả định Liquibase sẽ đảo ngược một DDL đã commit chỉ vì changeset báo lỗi. Bài kiểm thử phải mô phỏng partial failure và xác nhận cách phục hồi.

### 12.1. Test lock và timeout

Tạo transaction giữ lock trong database lab, sau đó chạy migration có lock timeout được cấu hình. Xác nhận:

- Migration thất bại đúng thời gian dự kiến.
- Không để lại schema dở dang ngoài dự kiến.
- Ứng dụng không bị treo hàng loạt.
- Liquibase lock được xử lý đúng.
- Retry sau khi blocker kết thúc hoạt động như thiết kế.

Không tạo tải hoặc lock test trên production khi chưa có kế hoạch.

## 13. Test rollback cho các change type phổ biến

| Change type | Bài test update | Bài test rollback |
|---|---|---|
| addColumn | App cũ/new đọc ghi đúng | Xác minh có dữ liệu mới trước khi drop |
| createTable | PK, FK, default, grant đúng | Xác minh bảng không còn consumer và dữ liệu có thể bỏ |
| addNotNullConstraint | Dữ liệu không NULL, writer tương thích | App cũ có thể ghi NULL trở lại không? |
| addForeignKeyConstraint | Orphan không còn, ghi mới bị kiểm soát | Drop FK có làm mất invariant cần thiết không? |
| createIndex | Query plan và write latency | Drop index có ảnh hưởng SLA không? |
| renameColumn | Code chuyển tiếp đọc/ghi đúng | Code cũ hoạt động với tên cũ hay cần view/alias? |
| update/SQL backfill | Mapping và row count đúng | Có thể khôi phục giá trị cũ không? |
| loadData | CSV, key và dữ liệu tham chiếu đúng | Xóa seed có ảnh hưởng dữ liệu đã được sử dụng không? |
| createView/function | Consumer chạy đúng | Có dependency khác cần drop trước không? |

Không đánh giá rollback chỉ bằng việc câu lệnh chạy thành công. Phải xác minh hậu điều kiện và hành vi ứng dụng.

## 14. Test checksum và tính ổn định lịch sử

Một release có thể chạy ở staging nhưng production thất bại vì changelog khác artifact hoặc changeset đã bị sửa sau khi triển khai.

Kiểm thử cần xác minh:

- Artifact dùng ở test và release có cùng digest.
- Changeset id/author/logical file path ổn định.
- Checksum không thay đổi ngoài dự kiến.
- Không có sửa trực tiếp changeset đã chạy.
- Context/label và DBMS filter giống cấu hình release.
- Rollback/re-upgrade không làm lịch sử bị sai lệch.
- DATABASECHANGELOG phản ánh đúng execution type.

Không dùng clear-checksums để làm cho test pass khi chưa hiểu nguyên nhân mismatch. Hãy điều tra file, artifact, encoding, property substitution và phiên bản Liquibase.

## 15. Kiểm thử nhiều DBMS và nhiều môi trường

Nếu module hỗ trợ nhiều DBMS, rollback và compatibility cần test trên từng engine/version được công bố hỗ trợ. Một câu SQL có thể transactional ở DBMS này nhưng auto-commit ở DBMS khác.

Ma trận test có thể gồm:

| Trục | Ví dụ |
|---|---|
| DBMS | PostgreSQL, MySQL, SQL Server, Oracle |
| Version | Các major/minor được hỗ trợ |
| Môi trường | Local, CI, staging, production-like |
| Database state | Fresh, upgrade từ release cũ, có dữ liệu ngoại lệ |
| Application | Old, compatible, new |
| Migration | Update, rollback, retry, forward-fix |
| Workload | Idle, steady traffic, batch/peak |
| Failure | Lock timeout, constraint violation, connection loss |

Không nhất thiết chạy mọi tổ hợp đầy đủ. Xác định các tổ hợp rủi ro cao, release path được hỗ trợ và engine có semantics khác biệt.

### 15.1. Kiểm thử cấu hình môi trường

Cùng artifact có thể nhận context, label, property hoặc DataSource khác nhau. Kiểm tra staging và production dùng đúng root changelog, filter và migration principal. Không để test dùng schema mặc định khác production mà không có chủ đích.

## 16. Tổ chức integration test với Spring Boot

Với Spring Boot, có thể khởi tạo ứng dụng cùng database ephemeral/container của đúng DBMS. Test cần xác minh Liquibase chạy trước các bean phụ thuộc schema và Hibernate không tự sửa schema.

Các điểm cần kiểm tra:

- DataSource URL và credentials đúng target.
- SpringLiquibase hoặc auto-configuration được tạo đúng.
- Root changelog và include resource có trong artifact.
- Liquibase hoàn tất trước repository/EntityManagerFactory cần schema.
- Application context khởi động thành công.
- Migration failure làm startup thất bại theo chính sách.
- Runtime user không có quyền DDL không cần thiết.
- Rollback được chạy bằng runner/CLI phù hợp và app version mục tiêu vẫn hoạt động.

Nếu dùng nhiều DataSource, test riêng từng target và xác minh mỗi Liquibase bean dùng đúng DataSource/root changelog.

### 16.1. Testcontainers hoặc database ephemeral

Container database giúp tạo môi trường sạch, có thể lặp lại và phù hợp CI. Pin image version/digest của DBMS, đợi health check, tạo database/schema riêng và dọn sau test.

Container test không thay thế performance test trên dữ liệu production-like. Dung lượng, I/O, replication và lock behavior trên máy CI có thể khác nhiều.

### 16.2. Kiểm tra Hibernate

Nếu Liquibase sở hữu schema, cấu hình Hibernate ở chế độ validate hoặc không tự thay đổi schema theo chính sách dự án. Test nên thất bại nếu entity mapping không khớp schema được tạo bởi Liquibase.

Không để Hibernate update tạo cột thiếu rồi khiến bài test tưởng migration đã đúng.

## 17. Test trong CI/CD

Một pipeline kiểm thử migration và rollback có thể gồm:

    Pull request
       |
       v
    Changelog validation + SQL preview
       |
       v
    Fresh install trên DBMS mục tiêu
       |
       v
    Upgrade từ baseline được hỗ trợ
       |
       v
    Application compatibility tests
       |
       v
    Kiểm tra dữ liệu và constraint
       |
       v
    Rollback SQL preview + review
       |
       v
    Thực thi rollback trên database test
       |
       v
    Test app version sau rollback
       |
       v
    Re-upgrade / forward-fix test nếu cần
       |
       v
    Publish test evidence

### 17.1. Không chỉ chạy update thành công

Một pipeline chỉ chạy liquibase update trên database trống không kiểm tra được rollback, dữ liệu cũ, mixed-version hoặc partial execution.

Tùy mức rủi ro, cần các gate riêng:

- Validate changelog.
- SQL preview.
- Fresh install.
- Upgrade path.
- Data invariant.
- Compatibility tests.
- Rollback preview và thực thi.
- Application smoke test.
- Performance/lock test cho DDL lớn.
- Re-upgrade hoặc forward-fix test.

### 17.2. Dùng cùng artifact để test và promote

Không build lại artifact sau khi staging pass. Lưu digest của JAR/image/changelog bundle, Liquibase version, JDBC driver và configuration identifier. Production phải chạy đúng artifact đã được test.

Secret và endpoint khác nhau theo môi trường, nhưng nội dung migration không được âm thầm thay đổi.

## 18. Kiểm thử khả năng quan sát và tiêu chí dừng

Rollback có thể không cần thiết nếu lỗi được phát hiện sớm và forward-fix an toàn; ngược lại, có trường hợp phải dừng rollout trước khi dữ liệu bị ảnh hưởng rộng hơn.

Theo dõi:

- Application error rate và p95/p99 latency.
- Startup/readiness/liveness.
- Database connection pool và timeout.
- Lock waits, deadlocks và long-running transaction.
- Replication lag.
- Query plan và slow query.
- Số dòng backfill, NULL, duplicate, orphan.
- Constraint/index validity.
- Liquibase execution time và changelog lock.
- Consumer lag, batch job và message retry.

Định nghĩa ngưỡng dừng trước deployment. Ví dụ: nếu latency vượt SLO, replication lag tăng liên tục hoặc constraint violation xuất hiện, dừng rollout tiếp theo và xác định trạng thái. Không chờ tới khi toàn bộ instance mới đã triển khai mới bắt đầu điều tra.

## 19. Quyết định rollback hay forward-fix

Rollback phù hợp khi thay đổi có thể đảo ngược, dữ liệu chưa bị biến đổi mất thông tin và phiên bản ứng dụng mục tiêu tương thích với schema sau rollback.

Forward-fix phù hợp khi:

- Migration đã tạo hoặc thay đổi dữ liệu mà app đang sử dụng.
- Rollback sẽ xóa dữ liệu hợp lệ mới phát sinh.
- DDL không thể đảo ngược an toàn.
- Database đã ở trạng thái partial hoặc có nhiều môi trường không đồng nhất.
- Có thể sửa bằng changeset mới mà không phá tương thích.

Restore/PITR phù hợp trong một số sự cố dữ liệu nghiêm trọng, nhưng phải đánh giá RPO/RTO và giao dịch sẽ mất.

| Câu hỏi | Nếu câu trả lời là không |
|---|---|
| Rollback có bảo toàn dữ liệu cần giữ không? | Xem forward-fix hoặc restore |
| App phiên bản cũ có chạy với schema sau rollback không? | Giữ app ở phiên bản tương thích hoặc thiết kế schema chuyển tiếp |
| DDL đã được xác minh có thể đảo ngược không? | Dừng và đánh giá repair |
| Tất cả target có cùng trạng thái lịch sử không? | Xử lý từng database, không rollback đồng loạt mù quáng |
| Có backup/restore đã test không? | Không dựa vào backup chưa kiểm chứng |

## 20. Bài thực hành: kiểm thử rollback và tương thích hai phiên bản

**Mục tiêu:** kiểm chứng migration thêm một cột và chuyển ứng dụng sang sử dụng cột mới. Dùng database lab có thể tạo lại, không dùng production.

### Bước 1. Tạo baseline

Tạo bảng orders có id, status và dữ liệu đại diện. Chạy root changelog baseline và ghi lại DATABASECHANGELOG. Build hoặc chọn app version cũ chỉ đọc/ghi status.

### Bước 2. Expand schema

Tạo changeset thêm cột delivery_status nullable. Có rollback drop cột cho database lab. Chạy validate, update-sql rồi update.

Kiểm tra app cũ vẫn khởi động, đọc và ghi được. Nếu app cũ thất bại do mapping hoặc SELECT *, ghi lại nguyên nhân và sửa chiến lược expand.

### Bước 3. Deploy app tương thích

Tạo app version mới có thể đọc dữ liệu cũ và mới. Ghi delivery_status theo quy tắc nghiệp vụ. Test app cũ và mới cùng chạy trên schema đã expand.

### Bước 4. Backfill

Chạy job theo batch để chuyển dữ liệu cũ. Ghi checkpoint và đối chiếu số dòng. Tạo một số giao dịch mới trong lúc backfill để xác nhận job không ghi đè giá trị mới.

### Bước 5. Kiểm tra rollback application

Giữ schema ở trạng thái expand và đưa một instance về app cũ. Xác nhận app cũ vẫn hoạt động. Kiểm tra dữ liệu do app mới ghi có được app cũ hiểu đúng hay không.

### Bước 6. Thử rollback database trên bản sao

Tạo bản sao database sau expand/backfill và có dữ liệu mới. Sinh rollback SQL, review rồi chạy trên bản sao. Kiểm tra cột bị drop có làm mất dữ liệu cần giữ không. Nếu dữ liệu cần giữ, ghi nhận rollback này không được phép cho production và thiết kế forward-fix hoặc quy trình chuyển dữ liệu.

### Bước 7. Enforce và contract trong release riêng

Sau khi xác minh không còn writer cũ và dữ liệu đã đạt invariant, thêm NOT NULL hoặc constraint cần thiết. Chuyển toàn bộ consumer sang cột mới. Chỉ xóa cột cũ trong release sau khi monitoring chứng minh không còn truy cập.

### Bước 8. Ghi bằng chứng

Lưu:

- Artifact digest và version ứng dụng.
- Liquibase version và DBMS/version.
- Root changelog và changeset history.
- SQL preview/update/rollback.
- Compatibility matrix và test result.
- Row count/reconciliation result.
- Thời gian migration, lock và latency.
- Kết quả smoke test sau rollback.
- Quyết định rollback/forward-fix và lý do.

## 21. Checklist nghiệm thu rollback và compatibility

- [ ] Đã phân biệt rollback ứng dụng, rollback schema và phục hồi dữ liệu.
- [ ] Có compatibility matrix cho các phiên bản ứng dụng và trạng thái schema.
- [ ] Expand-and-contract được chia thành các release/bước có hậu điều kiện.
- [ ] Mọi changeset có rollback phù hợp hoặc ghi rõ lý do không thể đảo ngược.
- [ ] Đã review rollback SQL trước khi thực thi.
- [ ] Đã test rollback trên database có dữ liệu đại diện.
- [ ] Đã tạo dữ liệu mới sau migration trước khi thử rollback.
- [ ] Đã test app cũ trên schema expand.
- [ ] Đã test app mới trên schema chuyển tiếp.
- [ ] Đã test mixed-version/rolling deployment.
- [ ] Đã test fresh install và upgrade path.
- [ ] Đã test partial execution và DDL không transactional khi có liên quan.
- [ ] Đã xác minh DATABASECHANGELOG, checksum và trạng thái schema sau rollback.
- [ ] Đã kiểm tra dữ liệu không bị mất hoặc có recovery plan.
- [ ] Đã test forward-fix/restore khi rollback không an toàn.
- [ ] DBMS/version trong test đại diện cho production.
- [ ] CI/CD dùng cùng artifact đã test và lưu digest/evidence.
- [ ] Có ngưỡng dừng, monitoring và người chịu trách nhiệm.
- [ ] Không sửa changeset lịch sử hoặc xóa DATABASECHANGELOG tùy tiện.
- [ ] Có phê duyệt cho thao tác contract/destructive.

## 22. Kết luận

Kiểm thử rollback và tính tương thích ứng dụng phải xác minh **toàn bộ trạng thái phối hợp giữa code, schema và dữ liệu**. Liquibase có thể thực thi rollback của changeset, nhưng khả năng phục hồi thực tế phụ thuộc DDL, dữ liệu phát sinh, transaction semantics của DBMS và những phiên bản ứng dụng đang chạy. Vì vậy, cần kiểm tra rollback trên database có dữ liệu đại diện, đồng thời chạy application version cũ/mới trên các trạng thái schema chuyển tiếp.

Expand-and-contract, compatibility matrix, fresh-install/upgrade/rollback test, mixed-version test và hậu kiểm dữ liệu tạo thành một quy trình có thể lặp lại. Khi rollback có nguy cơ mất dữ liệu hoặc phá hợp đồng với ứng dụng, forward-fix hoặc restore có kiểm soát có thể phù hợp hơn. Chỉ phát hành khi SQL preview, migration, rollback path, application smoke test và tiêu chí vận hành đều có bằng chứng rõ ràng.
