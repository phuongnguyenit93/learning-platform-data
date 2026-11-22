# Đổi tên hoặc tách cột qua nhiều phiên bản phát hành

Trong chương **Triển khai an toàn** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, đổi tên hoặc tách một cột là thay đổi có ảnh hưởng trực tiếp đến cả schema lẫn hợp đồng giữa database và ứng dụng. Một thay đổi tưởng như đơn giản — đổi full_name thành display_name hoặc tách full_name thành given_name và family_name — có thể làm hỏng phiên bản ứng dụng cũ đang chạy, job nền, báo cáo, tích hợp bên ngoài và các instance được triển khai lệch thời điểm.

Phạm vi của dịch vụ **DATABASE_SCHEMA_MIGRATION_LIQUIBASE** là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài học áp dụng các nguyên tắc đó cho việc đổi tên hoặc tách cột qua nhiều release, với mục tiêu duy trì khả năng tương thích, bảo toàn dữ liệu và kiểm soát thứ tự triển khai.

Định hướng đầy đủ của dịch vụ: Nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai. Thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD.

Chiến lược phù hợp thường là **expand–migrate–contract**: mở rộng schema để cả code cũ và mới cùng hoạt động, chuyển dữ liệu và lưu lượng đọc/ghi theo từng bước, rồi chỉ loại bỏ cấu trúc cũ khi không còn phiên bản hay thành phần nào phụ thuộc vào nó.

## 1. Vì sao không nên đổi tên cột trực tiếp trong một release?

Giả sử database hiện có bảng customer với cột full_name. Ứng dụng phiên bản 1 đọc và ghi cột này:

~~~sql
SELECT id, full_name
FROM app.customer;
~~~

Một release mới muốn đổi tên thành display_name. Nếu migration thực hiện ngay:

~~~sql
ALTER TABLE app.customer
RENAME COLUMN full_name TO display_name;
~~~

thì các instance phiên bản 1 vẫn đang chạy có thể tiếp tục truy vấn full_name và nhận lỗi column not found. Vấn đề còn xuất hiện ở:

- Các instance cũ trong rolling deployment chưa được thay thế.
- Worker, scheduler hoặc consumer chạy độc lập với web application.
- Báo cáo, BI, ETL, CDC và script vận hành.
- Ứng dụng mobile hoặc đối tác gọi API theo hợp đồng cũ.
- Một job triển khai thất bại khiến cả phiên bản cũ và mới cùng tồn tại lâu hơn dự kiến.
- Quy trình rollback ứng dụng đưa code cũ trở lại sau khi schema đã đổi.

Database không biết mọi nơi đang sử dụng một cột. Liquibase có thể áp dụng DDL thành công nhưng không thể tự chứng minh mọi consumer đã chuyển sang tên mới.

Vì vậy, đổi tên cột trong production nên được xem là thay đổi hợp đồng nhiều giai đoạn. Giữ cột cũ trong thời gian chuyển tiếp giúp các phiên bản ứng dụng có thời gian di chuyển mà không cần một thời điểm dừng toàn bộ hệ thống.

## 2. Expand–migrate–contract là gì?

Ba giai đoạn có mục tiêu khác nhau:

| Giai đoạn | Schema | Ứng dụng và dữ liệu | Điều kiện chuyển tiếp |
|---|---|---|---|
| Expand | Thêm cột hoặc cấu trúc mới, giữ cấu trúc cũ | Code mới có thể đọc/ghi cả hai; code cũ vẫn dùng cấu trúc cũ | Cấu trúc mới tồn tại và tương thích |
| Migrate | Giữ cả hai cấu trúc | Backfill, đồng bộ, chuyển dần đọc/ghi sang cấu trúc mới | Dữ liệu mới đã đầy đủ và được xác minh |
| Contract | Loại bỏ cột cũ hoặc cấu trúc không còn dùng | Tất cả consumer đã chuyển sang cấu trúc mới | Không còn phụ thuộc cũ và đã qua cửa sổ rollback |

Không nhất thiết mỗi giai đoạn tương ứng đúng một release. Một release có thể chỉ thêm schema; release tiếp theo triển khai dual-write; một job riêng backfill dữ liệu; release khác chuyển đọc; và một release sau nữa mới drop cột cũ.

Điểm cốt lõi là **mỗi bước phải tương thích với những phiên bản có thể đang chạy đồng thời**. Không được giả định deployment hoàn tất tức thì hoặc mọi tiến trình đều nâng cấp cùng lúc.

## 3. Lập bản đồ các consumer trước khi thay đổi

Trước khi sửa changelog, cần tìm tất cả nơi phụ thuộc vào cột cũ:

- Entity JPA/Hibernate, repository và native SQL.
- JDBC template, stored procedure và function.
- REST/GraphQL service, serializer và mapper.
- Batch job, scheduler, message consumer và event handler.
- View, trigger, materialized view và generated column.
- Báo cáo, dashboard, data warehouse, ETL và CDC.
- Script quản trị, export/import và tác vụ vận hành.
- Ứng dụng khác hoặc đối tác có quyền truy cập trực tiếp database.

Lập bảng dependency:

| Consumer | Đọc cột cũ | Ghi cột cũ | Có thể nâng cấp độc lập? | Chủ sở hữu |
|---|---:|---:|---:|---|
| API instance | Có | Có | Có | Team application |
| Worker xử lý đơn | Có | Có | Có | Team operations |
| Báo cáo ngày | Có | Không | Có | Data team |
| ETL bên ngoài | Có | Không | Có thể cần lịch phối hợp | Data platform |
| View trong DB | Có | Không | Theo migration | DBA |

Nếu không biết một consumer có tồn tại hay không, không thể kết luận cột cũ đã an toàn để xóa. Có thể cần log truy vấn, audit, query store, tracing hoặc xác nhận từ nhóm sở hữu hệ thống.

Không chỉ tìm tên cột trong repository hiện tại. Consumer có thể nằm ở repository khác hoặc ngoài tổ chức.

## 4. Xác định hợp đồng dữ liệu mới trước khi thêm cột

Trước khi viết migration, xác định ý nghĩa chính xác của cột mới:

- Cột mới thay thế hoàn toàn cột cũ hay chỉ lưu một phần thông tin?
- Kiểu dữ liệu, độ dài, precision, nullability và default là gì?
- Có chuẩn hóa hoa/thường, khoảng trắng hoặc Unicode không?
- Dữ liệu cũ được chuyển đổi theo quy tắc nào?
- Có thể khôi phục giá trị cũ từ giá trị mới không?
- Có cần giữ cột cũ làm nguồn đối chiếu trong một khoảng thời gian?
- Khi hai cột khác nhau, nguồn nào được coi là đúng?
- Consumer nào cần đọc giá trị cũ và consumer nào cần giá trị mới?

Đổi tên một cột thường là phép sao chép nguyên giá trị. Tách một cột thành nhiều cột thường cần quy tắc chuyển đổi phức tạp hơn. Ví dụ tách full_name thành given_name và family_name không thể luôn thực hiện chính xác bằng cách lấy từ cuối chuỗi vì tên người có nhiều thành phần, tiền tố, hậu tố và quy ước khác nhau.

Nếu không thể chuyển đổi một cách xác định, cần thiết kế bước xác minh hoặc quy trình xử lý ngoại lệ thay vì giả định SQL có thể suy ra dữ liệu chính xác.

## 5. Ví dụ đổi tên cột: full_name thành display_name

Giả sử ứng dụng hiện có:

~~~text
app.customer
  id
  full_name
~~~

Mục tiêu là chuyển sang display_name, nhưng vẫn hỗ trợ phiên bản cũ trong một thời gian.

### Release A — Expand

Thêm cột mới, để nullable và chưa xóa cột cũ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-001-add-customer-display-name"
      author: "team-db"
      comment: "Expand schema để chuyển full_name sang display_name"
      preConditions:
        - onFail: HALT
        - tableExists:
            schemaName: app
            tableName: customer
        - not:
            - columnExists:
                schemaName: app
                tableName: customer
                columnName: display_name
      changes:
        - addColumn:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: display_name
                  type: VARCHAR(200)
                  constraints:
                    nullable: true
~~~

Sau release này:
- Code cũ tiếp tục đọc/ghi full_name.
- Code mới có thể được triển khai nhưng chưa được giả định rằng display_name đã có dữ liệu.
- Không thêm NOT NULL ngay khi cột mới vừa được tạo.
- Không drop full_name.

Precondition giúp dừng khi bảng không tồn tại hoặc cột mới đã tồn tại trong một trạng thái không như mong đợi. Nếu cần hỗ trợ database đã được sửa thủ công, phải có quy trình reconcile riêng; không dùng MARK_RAN để che sự khác biệt.

### Release B — Dual-write và backfill

Ứng dụng mới ghi cùng một giá trị vào cả full_name và display_name trong cùng một transaction:

~~~java
@Transactional
public void updateCustomerName(long customerId, String name) {
    Customer customer = repository.findById(customerId)
        .orElseThrow();

    customer.setFullName(name);
    customer.setDisplayName(name);

    repository.save(customer);
}
~~~

Đoạn mã chỉ minh họa ý tưởng. Cách cập nhật thực tế phụ thuộc entity mapping, optimistic locking và repository. Điều quan trọng là hai giá trị được ghi nguyên tử trong cùng một transaction để tránh một cột thành công còn cột kia thất bại.

Sau khi mọi writer đã hỗ trợ dual-write hoặc có cơ chế đồng bộ tương đương, backfill những hàng cũ còn thiếu:

~~~sql
UPDATE app.customer
SET display_name = full_name
WHERE display_name IS NULL;
~~~

Câu SQL này là ví dụ cho trường hợp đổi tên giữ nguyên giá trị và cột mới nullable. Với bảng lớn, không nên mặc định chạy một UPDATE toàn bảng trong một transaction duy nhất. Có thể cần job theo batch dựa trên khóa chính, giới hạn tốc độ, checkpoint và theo dõi lock/log.

Điều kiện WHERE display_name IS NULL có ích vì không ghi đè những giá trị mới đã được ứng dụng dual-write. Tuy nhiên, phải xác minh race condition theo cách ứng dụng cập nhật đồng thời và isolation level của DBMS.

### Release C — Chuyển đọc sang cột mới

Sau khi backfill xong và dữ liệu được xác minh, ứng dụng có thể đọc display_name. Trong giai đoạn đầu, vẫn có thể giữ dual-write để phiên bản cũ hoặc job cũ chưa được loại bỏ không bị ảnh hưởng.

Không chuyển reader chỉ vì job backfill kết thúc với exit code 0. Phải xác minh không còn hàng thiếu, dữ liệu khớp theo quy tắc và không có writer cũ làm phát sinh sai lệch.

### Release D — Contract

Chỉ khi mọi consumer đã chuyển sang display_name, cột cũ mới được loại bỏ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261210-001-drop-customer-full-name"
      author: "team-db"
      comment: "Contract sau khi mọi consumer đã dùng display_name"
      preConditions:
        - onFail: HALT
        - columnExists:
            schemaName: app
            tableName: customer
            columnName: full_name
      changes:
        - dropColumn:
            schemaName: app
            tableName: customer
            columnName: full_name
~~~

Đây là ví dụ minh họa. Trong production, precondition columnExists chưa đủ để chứng minh mọi consumer đã chuyển đổi. Điều kiện đó cần được xác nhận bằng quy trình phát hành, telemetry, ownership và thời gian quan sát.

Drop cột là bước phá hủy dữ liệu ở cột cũ. Trước khi chạy cần backup/retention phù hợp và chấp nhận rằng rollback ứng dụng về code chỉ biết full_name sẽ không còn hoạt động nếu cột đã bị xóa.

## 6. Tách một cột thành nhiều cột

Giả sử customer có full_name và yêu cầu mới cần given_name cùng family_name.

Schema cũ:

~~~text
customer
  id
  full_name
~~~

Schema mới:

~~~text
customer
  id
  full_name
  given_name
  family_name
~~~

Không nên đổi trực tiếp full_name thành hai cột trong một migration duy nhất. Trước hết phải xác định quy tắc phân tách:

- Tên có thể gồm một, hai hoặc nhiều thành phần.
- Họ có thể gồm nhiều từ.
- Thứ tự tên khác nhau theo quốc gia/ngôn ngữ.
- Có thể có tiền tố, hậu tố hoặc tên đệm.
- Khoảng trắng liên tiếp, dấu câu và Unicode cần được xử lý.
- Một số bản ghi có thể không có đủ thông tin để suy ra hai trường.

Nếu quy tắc nghiệp vụ không thể phân tách chính xác, hãy giữ full_name làm nguồn dữ liệu gốc trong giai đoạn chuyển đổi và yêu cầu người dùng/nguồn dữ liệu xác nhận các bản ghi mơ hồ.

### Expand schema

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-010-add-customer-name-parts"
      author: "team-db"
      changes:
        - addColumn:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: given_name
                  type: VARCHAR(100)
              - column:
                  name: family_name
                  type: VARCHAR(150)
~~~

Không đặt NOT NULL nếu chưa backfill và chưa có quy tắc xử lý hàng thiếu dữ liệu. Kích thước cột phải dựa trên yêu cầu nghiệp vụ và giới hạn DBMS được hỗ trợ.

### Migrate dữ liệu

Có thể dùng SQL nếu quy tắc chuyển đổi đơn giản, xác định và được kiểm thử. Với tên người, thường nên dùng một hàm/domain service có quy tắc rõ ràng hoặc quy trình xác nhận dữ liệu.

Một ví dụ giả định quy tắc đơn giản là chuỗi luôn có dạng "given|family" và dấu phân cách không xuất hiện trong thành phần:

~~~text
full_name = "An|Nguyen"
given_name = "An"
family_name = "Nguyen"
~~~

Đây chỉ là ví dụ dữ liệu đã có định dạng được bảo đảm. Không áp dụng phép split tùy tiện cho dữ liệu tên tự do.

Sau khi backfill:
- Đếm số hàng đã chuyển.
- Đếm số hàng không thể phân tách.
- Kiểm tra giá trị rỗng/NULL.
- Kiểm tra độ dài vượt giới hạn.
- Đối chiếu mẫu dữ liệu với nguồn gốc.
- Lưu báo cáo ngoại lệ và quyết định xử lý.

### Dual-write

Trong giai đoạn chuyển tiếp, writer mới có thể cập nhật full_name, given_name và family_name cùng transaction theo một quy tắc thống nhất. Nếu vẫn có writer cũ chỉ biết full_name, cần có adapter hoặc cơ chế đồng bộ để thay đổi từ writer cũ được phản ánh vào các cột mới.

Không để hai đường ghi độc lập có thể tạo ra xung đột mà không có quy tắc phân xử. Nếu given_name/family_name là nguồn chuẩn mới, phải định nghĩa cách tái tạo full_name trong thời gian code cũ còn hoạt động.

## 7. Dual-read, dual-write và chọn nguồn dữ liệu chuẩn

Dual-write không tự động giải quyết mọi vấn đề. Cần xác định nguồn chuẩn ở từng giai đoạn.

| Giai đoạn | Reader | Writer | Nguồn được coi là chuẩn |
|---|---|---|---|
| Trước expand | Cột cũ | Cột cũ | Cột cũ |
| Sau expand, trước app mới | Cột cũ | Cột cũ | Cột cũ |
| Dual-write | Có thể đọc cũ hoặc fallback mới | Ghi cả hai | Theo quy tắc chuyển tiếp được định nghĩa |
| Chuyển reader | Đọc mới, có thể fallback cũ khi cần | Vẫn ghi cả hai | Cột mới sau khi xác minh |
| Sau contract | Chỉ đọc mới | Chỉ ghi mới | Cột mới |

Các mẫu đọc thường gặp:

**Ưu tiên cột mới, fallback cột cũ:** hữu ích khi backfill chưa hoàn tất, nhưng phải theo dõi số lần fallback và không để fallback che hàng thiếu kéo dài.

**Chỉ đọc cột mới sau khi backfill:** đơn giản hơn nhưng yêu cầu điều kiện chuyển tiếp nghiêm ngặt.

**Dual-read và so sánh:** đọc cả hai để phát hiện khác biệt trong giai đoạn quan sát. Không nên dùng lâu dài nếu tăng tải hoặc tạo logic phức tạp.

Khi hai cột khác nhau, không thể tùy tiện chọn giá trị không NULL. Cần biết ai ghi, thời điểm nào, version nào và quy tắc nghiệp vụ nào có quyền quyết định.

## 8. Xử lý race condition giữa backfill và ghi mới

Một backfill chạy song song với ứng dụng có thể gặp tình huống:

1. Job đọc full_name cũ.
2. Người dùng đổi tên; ứng dụng ghi full_name và display_name mới.
3. Job ghi giá trị cũ vào display_name sau đó.

Nếu job ghi không điều kiện, nó có thể ghi đè dữ liệu mới.

Một số biện pháp:

- Dual-write được triển khai trước khi bắt đầu backfill.
- Backfill chỉ cập nhật hàng mà cột mới còn NULL hoặc chưa có marker hoàn tất.
- Dùng điều kiện cập nhật dựa trên version/updated_at nếu phù hợp.
- Chia batch theo khóa chính và commit ngắn.
- Khóa hàng trong phạm vi batch nếu DBMS và tải cho phép.
- Ghi checkpoint để job có thể tiếp tục.
- Theo dõi số hàng cập nhật và số hàng bị bỏ qua.
- Chạy reconciliation sau backfill để phát hiện sai lệch còn lại.

Ví dụ cập nhật có điều kiện:

~~~sql
UPDATE app.customer
SET display_name = full_name
WHERE id > :last_id
  AND id <= :batch_end
  AND display_name IS NULL;
~~~

Placeholder trên được thay bởi job có kiểm soát. Cú pháp bind parameter thực tế phụ thuộc công cụ chạy. Điều kiện IS NULL tránh ghi đè những hàng đã có giá trị mới, nhưng không thay thế việc xác minh thứ tự writer và backfill.

Nếu ứng dụng dùng optimistic locking với version column, job backfill phải tuân thủ quy tắc version hoặc có cơ chế tương thích. Không cập nhật trực tiếp bỏ qua version nếu điều đó làm mất khả năng phát hiện concurrent modification.

## 9. Backfill lớn: dùng job có thể tiếp tục, không nhất thiết một changeset DML khổng lồ

Liquibase phù hợp để quản lý lịch sử thay đổi, nhưng không phải mọi backfill lớn đều nên là một câu UPDATE duy nhất trong changeset.

Một UPDATE toàn bảng có thể:
- Giữ lock lâu.
- Tạo transaction lớn.
- Tăng WAL/transaction log.
- Gây replication lag.
- Tăng dung lượng undo/temp.
- Làm rollback rất tốn kém.
- Làm thời gian startup/job migration vượt timeout.

Có thể chọn một trong các cách:

| Cách | Phù hợp khi | Điểm cần kiểm soát |
|---|---|---|
| SQL changeset nhỏ | Bảng nhỏ, thao tác nhanh, có thể rollback | Transaction và lock |
| SQL theo batch | DBMS và quy trình cho phép phân đoạn rõ | Checkpoint, retry, tính idempotent |
| Application job | Quy tắc chuyển đổi phức tạp hoặc cần quan sát | Version, concurrency, audit |
| Stored procedure/job DB | Tổ chức quản lý logic trong DB | DBMS-specific và quyền |
| External migration worker | Dữ liệu rất lớn, cần điều tiết tải | Ownership, resume, observability |

Nếu backfill chạy ngoài changeset Liquibase, phải ghi nhận trạng thái hoàn tất theo một cơ chế có thể kiểm toán. Một changeset sau đó có thể dùng precondition hoặc validation để xác nhận backfill đạt yêu cầu trước khi thêm NOT NULL hoặc drop cột cũ.

Không đánh dấu changeset backfill là đã chạy nếu job chưa hoàn tất. Không dùng runAlways để lặp một backfill không được thiết kế idempotent.

## 10. Thiết kế changeset theo từng mốc phát hành

Một chuỗi changeset có thể được tổ chức như sau:

| Mốc | Changeset/job | Mục tiêu |
|---|---|---|
| Release A | add-display-name | Thêm cột mới nullable |
| Release B | application dual-write | Code ghi cả hai cột |
| Job B | backfill-display-name | Sao chép dữ liệu cũ theo batch |
| Release C | validate-display-name | Kiểm tra dữ liệu và chuyển reader |
| Release D | stop-writing-full-name | Ngừng ghi cột cũ sau khi hết consumer cũ |
| Release E | drop-full-name | Xóa cột cũ sau cửa sổ quan sát |

Các mốc ứng dụng không nhất thiết là changeset Liquibase. Liquibase quản lý thay đổi schema; ứng dụng và job dữ liệu cần được phát hành theo pipeline riêng nhưng phải có dependency và tiêu chí hoàn thành rõ.

Mỗi changeset Liquibase nên:
- Có ID/AUTHOR/FILENAME ổn định.
- Mô tả một bước schema có ý nghĩa.
- Có precondition phù hợp.
- Có rollback nếu thực sự an toàn.
- Không sửa sau khi đã triển khai.
- Được kiểm thử trên database có dữ liệu đại diện.
- Được chạy bằng artifact changelog đã review.

## 11. Dùng precondition để bảo vệ từng bước

Ví dụ changeset expand có thể xác nhận bảng cũ tồn tại và cột mới chưa tồn tại:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-020-expand-customer-display-name"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - tableExists:
            schemaName: app
            tableName: customer
        - columnExists:
            schemaName: app
            tableName: customer
            columnName: full_name
        - not:
            - columnExists:
                schemaName: app
                tableName: customer
                columnName: display_name
      changes:
        - addColumn:
            schemaName: app
            tableName: customer
            columns:
              - column:
                  name: display_name
                  type: VARCHAR(200)
~~~

Precondition chỉ xác nhận các object tồn tại theo metadata mà Liquibase đọc được. Nó không chứng minh mọi dữ liệu đã được backfill hoặc mọi writer đã dual-write.

Trước bước contract, có thể dùng precondition sqlCheck để kiểm tra không còn hàng thiếu:

~~~yaml
preConditions:
  - onFail: HALT
  - sqlCheck:
      expectedResult: "0"
      sql: |
        SELECT COUNT(*)
        FROM app.customer
        WHERE display_name IS NULL
~~~

Câu SQL và cách trả kết quả cần được kiểm thử trên DBMS mục tiêu. Ngay cả khi kết quả bằng 0, điều đó không chứng minh không còn writer cũ sẽ tạo dữ liệu thiếu sau thời điểm kiểm tra. Cần dừng writer cũ hoặc bảo đảm mọi writer còn hoạt động đều duy trì cột mới trước khi contract.

Không dùng onFail: MARK_RAN để bỏ qua điều kiện chưa đạt. Nếu cột mới còn NULL, ghi nhận changeset contract như đã chạy sẽ làm lịch sử và schema không nhất quán.

## 12. Kiểm tra dữ liệu trước khi siết constraint

Sau backfill, có thể cần đặt cột mới NOT NULL, UNIQUE hoặc tạo FK. Không thực hiện trước khi kiểm tra:

- Số hàng còn NULL.
- Giá trị rỗng hoặc chỉ chứa khoảng trắng.
- Giá trị vượt chiều dài.
- Dữ liệu trùng theo quy tắc nghiệp vụ.
- Dữ liệu không ánh xạ được.
- FK không có bản ghi cha.
- Các writer đang chạy có tiếp tục tạo dữ liệu không hợp lệ không.

Ví dụ kiểm tra duplicate:

~~~sql
SELECT display_name, COUNT(*)
FROM app.customer
WHERE display_name IS NOT NULL
GROUP BY display_name
HAVING COUNT(*) > 1;
~~~

Đây chỉ là truy vấn minh họa. Nếu tính duy nhất không phân biệt hoa/thường hoặc cần chuẩn hóa Unicode, phép kiểm tra phải dùng cùng quy tắc với constraint/index ở DBMS mục tiêu.

Đối với split column, có thể có quy tắc NOT NULL khác nhau:
- given_name bắt buộc nhưng family_name có thể rỗng.
- Một số loại khách hàng không có tên cá nhân.
- Dữ liệu tổ chức dùng legal_name thay vì given_name/family_name.

Constraint phải phản ánh domain model, không chỉ thuận tiện cho một fixture.

## 13. Đổi tên trong entity JPA và API theo từng release

Nếu ứng dụng dùng JPA, không đổi mapping sang cột mới trước khi cột đã tồn tại trên tất cả database mà instance có thể truy cập.

Ví dụ entity trong giai đoạn dual-write:

~~~java
@Entity
@Table(name = "customer", schema = "app")
public class Customer {
    @Id
    private Long id;

    @Column(name = "full_name")
    private String legacyFullName;

    @Column(name = "display_name")
    private String displayName;
}
~~~

Service có thể ghi cả hai:

~~~java
@Transactional
public void changeDisplayName(Customer customer, String value) {
    customer.setLegacyFullName(value);
    customer.setDisplayName(value);
    repository.save(customer);
}
~~~

Trong giai đoạn chuyển reader, API có thể trả display_name nhưng cần cân nhắc hợp đồng cũ. Nếu JSON field fullName đang được client sử dụng, đổi tên API response là một thay đổi contract riêng. Database column, Java property và JSON property không cần đổi cùng một release.

Có thể giữ tên API cũ tạm thời trong khi mapping database đã chuyển, hoặc hỗ trợ cả hai field response theo thời hạn deprecation. Ghi rõ version API và client nào còn phụ thuộc.

Không để @Column(name="display_name") được triển khai trước changeset expand. Ngược lại, không drop full_name khi còn entity hoặc native query cũ tham chiếu.

## 14. Tách cột và ánh xạ domain model

Với full_name thành given_name/family_name, entity có thể có:

~~~java
@Entity
@Table(name = "customer", schema = "app")
public class Customer {
    @Id
    private Long id;

    @Column(name = "full_name")
    private String legacyFullName;

    @Column(name = "given_name")
    private String givenName;

    @Column(name = "family_name")
    private String familyName;
}
~~~

Trong giai đoạn chuyển tiếp:
- Đọc hai cột mới nếu đã có dữ liệu hợp lệ.
- Có thể fallback full_name cho hàng chưa chuyển.
- Writer phải cập nhật các trường theo quy tắc domain.
- Khi code cũ còn ghi full_name, phải đồng bộ lại các cột mới hoặc tiếp tục giữ cột cũ làm nguồn chuẩn tạm thời.
- Theo dõi số hàng fallback và số hàng không thể phân tách.

Không tự động tách tên trong getter hoặc setter mà không có quy tắc domain rõ. Logic chuyển đổi nên được kiểm thử độc lập với nhiều ngôn ngữ và dữ liệu biên.

Nếu không thể tái tạo full_name từ given_name/family_name theo đúng dữ liệu gốc, giữ bản gốc trong giai đoạn chuyển tiếp hoặc lưu một trường nguồn có chủ đích cho đến khi nghiệp vụ xác nhận không còn cần.

## 15. Kiểm soát thứ tự deployment và rolling release

Một thứ tự triển khai minh họa:

~~~text
1. Release A: migration thêm cột mới
                 |
                 v
2. Release B: deploy code dual-write, vẫn đọc cột cũ
                 |
                 v
3. Job: backfill dữ liệu cũ sang cột mới
                 |
                 v
4. Verify: kiểm tra parity và hàng ngoại lệ
                 |
                 v
5. Release C: chuyển reader sang cột mới
                 |
                 v
6. Observe: theo dõi fallback, lỗi và consumer cũ
                 |
                 v
7. Release D: ngừng dual-write cột cũ
                 |
                 v
8. Release E: migration drop cột cũ
~~~

Không chạy bước 8 chỉ vì bước 5 đã hoàn tất. Cần xác nhận:
- Không còn instance cũ.
- Không còn worker/job cũ.
- Consumer ngoài đã chuyển.
- View/trigger/report không còn tham chiếu.
- Log truy vấn hoặc telemetry không còn truy cập cột cũ trong cửa sổ quan sát đã chọn.
- Có bản backup/retention theo chính sách.
- Kế hoạch rollback ứng dụng không còn phụ thuộc cột cũ hoặc đã hết thời hạn rollback.

Trong hệ thống rolling deployment, có thể cần chờ nhiều chu kỳ release hoặc thời gian dài hơn thời gian sống của job/batch. Không chỉ dựa vào trạng thái deployment của web server.

## 16. Khi nào dùng trigger hoặc view để tương thích?

Trong một số hệ thống, code cũ và mới không thể được nâng cấp đồng thời. Có thể dùng compatibility layer:

- View ánh xạ tên cột cũ sang cột mới.
- Trigger đồng bộ cột cũ và mới.
- Stored procedure làm lớp ghi chung.
- Adapter service chuyển đổi giữa contract cũ và mới.

Các cơ chế này có chi phí:
- Trigger có thể tạo vòng lặp hoặc ghi đè dữ liệu.
- View có thể không hỗ trợ mọi thao tác ghi.
- Trigger semantics và ordering khác giữa DBMS.
- Debug dữ liệu khó hơn vì write path không hiển thị trong application code.
- Khi drop cột cũ, compatibility layer cũng phải được loại bỏ theo thứ tự.

Chỉ dùng khi cần và phải có test trên DBMS thật. Nếu ứng dụng có thể triển khai dual-write rõ ràng, đó thường là cách dễ quan sát hơn. Không dùng trigger như giải pháp mặc định để che việc thiếu kế hoạch rollout.

## 17. Rollback ở từng giai đoạn

Rollback không giống nhau ở mọi giai đoạn:

| Giai đoạn | Rollback thường khả thi? | Điều kiện |
|---|---|---|
| Chỉ expand, chưa có writer mới | Thường dễ | Drop cột mới nếu chưa chứa dữ liệu cần giữ |
| Dual-write | Có thể | Code cũ còn đọc được và dữ liệu hai cột đã đồng bộ |
| Backfill | Có giới hạn | Biết dữ liệu nào do job tạo, có thể giữ hoặc khôi phục nguồn |
| Đã chuyển reader | Phụ thuộc | Cột cũ còn được đồng bộ và code cũ tương thích |
| Đã ngừng ghi cột cũ | Khó hơn | Phải đồng bộ ngược hoặc có dữ liệu nguồn |
| Đã drop cột cũ | Không thể rollback đơn giản | Cần restore/forward fix và có thể mất dữ liệu lịch sử |

Một rollback Liquibase cho addColumn có thể drop cột mới, nhưng nếu ứng dụng đã ghi dữ liệu vào đó thì rollback sẽ xóa dữ liệu. Vì vậy, rollback DDL không tự động là rollback an toàn.

Sau khi contract:
- Không kỳ vọng chỉ rollback image ứng dụng là đủ.
- Có thể cần restore backup hoặc forward fix.
- Nếu phải tái tạo cột cũ, dữ liệu cũ có thể không khôi phục chính xác từ cột mới.
- Cần xem xét API/event consumer và dữ liệu đã phát sinh trong thời gian chuyển đổi.

Trước contract, giữ dual-write hoặc cơ chế đồng bộ ngược trong thời gian rollback được phê duyệt. Sau contract, xác định rõ điểm không thể quay lại và yêu cầu phê duyệt release.

## 18. Không sửa changeset đã chạy để đổi tên cột

Một sai lầm là quay lại changeset cũ, thay full_name thành display_name hoặc sửa SQL của migration đã chạy.

Điều này có thể gây checksum mismatch vì nội dung changeset khác với MD5SUM đã lưu trong DATABASECHANGELOG. Nó cũng làm lịch sử không còn phản ánh chính xác thao tác đã xảy ra ở môi trường trước.

Cách đúng:
- Giữ changeset cũ bất biến.
- Thêm changeset expand mới.
- Thực hiện backfill bằng changeset hoặc job được quản lý.
- Thêm changeset contract sau khi đủ điều kiện.
- Giữ ID/AUTHOR/FILENAME ổn định.
- Không dùng clear-checksums hoặc validCheckSum để che việc sửa lịch sử.

Nếu một database chưa chạy changeset cũ, không tự ý sửa source chỉ dựa vào môi trường đó. Cần xét mọi môi trường dùng chung và artifact đã phát hành. Một changeset có thể đã chạy ở staging nhưng chưa chạy ở production.

## 19. Kiểm thử migration trên database có dữ liệu

Fresh install không thể phát hiện mọi vấn đề của đổi tên/tách cột. Cần fixture đại diện:

- Bảng rỗng.
- Một hàng có giá trị bình thường.
- Giá trị NULL.
- Chuỗi rỗng và khoảng trắng.
- Giá trị dài sát giới hạn.
- Unicode và dấu.
- Giá trị không theo format chuẩn.
- Nhiều lần cập nhật liên tiếp.
- Hàng được sửa trong lúc backfill.
- Bản ghi được tạo mới trong lúc chuyển tiếp.
- Bản ghi bị xóa hoặc soft-delete.
- Dữ liệu có quan hệ với bảng khác.

Test cần kiểm tra:
1. Cột mới được thêm mà không phá code cũ.
2. Code dual-write ghi đúng cả hai.
3. Backfill không ghi đè thay đổi mới.
4. Job chạy lại không làm dữ liệu sai hoặc nhân đôi.
5. Hàng ngoại lệ được báo cáo.
6. Reader mới xử lý dữ liệu đã chuyển và chưa chuyển theo chính sách.
7. Không còn hàng thiếu trước khi siết constraint.
8. Contract chỉ chạy sau khi điều kiện đạt.
9. Phiên bản ứng dụng cũ không còn truy vấn cột đã drop.
10. History và checksum phản ánh đúng các changeset.

## 20. Kiểm thử tương thích giữa các phiên bản ứng dụng

Trong rolling deployment, các phiên bản có thể cùng chạy. Cần lập ma trận tương thích:

| Schema | App v1 (cũ) | App v2 (dual-write) | App v3 (đọc mới) |
|---|---|---|---|
| S0: chỉ cột cũ | Có | Không | Không |
| S1: cũ + mới | Có | Có | Có nếu có fallback |
| S2: mới đã backfill | Có nếu vẫn duy trì cột cũ | Có | Có |
| S3: cũ đã drop | Không | Không nếu còn ghi cũ | Có |

Ma trận này cần được điều chỉnh theo code thật. Mục tiêu là xác định mọi cặp schema/application có thể cùng tồn tại trong quá trình rollout.

Test nên chạy:
- App cũ trên schema expand.
- App mới dual-write trên schema expand.
- App mới đọc cột mới sau backfill.
- App cũ không được chạy trên schema contract.
- Job cũ và mới cùng hoạt động trong thời gian chuyển tiếp nếu có.
- Rollback code trước và sau mỗi mốc.

Không để schema contract được triển khai khi còn instance cũ trong load balancer, worker đang chạy hoặc job có thể khởi động lại bằng artifact cũ.

## 21. Theo dõi tiến độ và tiêu chí chuyển giai đoạn

Không chuyển từ migrate sang contract dựa trên cảm giác. Cần metric và điều kiện rõ.

Các metric hữu ích:
- Tổng số hàng.
- Số hàng đã backfill.
- Số hàng còn NULL ở cột mới.
- Số hàng có hai cột khác nhau theo quy tắc chuẩn.
- Số lỗi chuyển đổi.
- Thời gian xử lý mỗi batch.
- Lock wait và transaction duration.
- Replication lag.
- Số lần reader fallback sang cột cũ.
- Số truy vấn/consumer còn sử dụng cột cũ.
- Tỷ lệ lỗi ứng dụng và job.

Ví dụ tiêu chí:
- 100% hàng thuộc phạm vi đã có giá trị mới hợp lệ hoặc ngoại lệ được phê duyệt.
- Không có chênh lệch chưa giải thích giữa cột cũ và mới.
- Không có reader fallback trong cửa sổ quan sát đã định.
- Không có writer cũ trong thời gian ít nhất bằng vòng đời dài nhất của job/consumer.
- Tất cả instance và worker đã chạy version tương thích.
- Backup/restore và kế hoạch recovery đã được xác nhận.

Ngưỡng và cửa sổ quan sát phụ thuộc workload, SLA và thời gian sống của consumer. Không đặt một con số cố định cho mọi hệ thống.

## 22. Tạo changeset contract có kiểm soát

Một changeset drop cột nên được đặt ở release riêng và có precondition:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261210-010-contract-customer-full-name"
      author: "team-db"
      comment: "Drop cột cũ sau khi hoàn tất chuyển đổi"
      preConditions:
        - onFail: HALT
        - columnExists:
            schemaName: app
            tableName: customer
            columnName: full_name
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM app.customer
              WHERE display_name IS NULL
      changes:
        - dropColumn:
            schemaName: app
            tableName: customer
            columnName: full_name
~~~

SQL check chỉ xác minh không còn display_name NULL tại thời điểm đánh giá. Nó không chứng minh mọi consumer đã dừng đọc full_name hoặc không có writer cũ tiếp tục chạy. Những điều kiện đó phải được xác minh ngoài database bằng release gate và telemetry.

Rollback dropColumn tự động không thể khôi phục dữ liệu đã mất nếu không có bản sao. Có thể để rollback không khai báo và quy định forward recovery, hoặc lưu trữ dữ liệu cũ theo chính sách trước khi drop. Không khai báo rollback giả tạo chỉ để checklist có dấu tích.

## 23. Dùng tag và release gate để kiểm soát mốc

Liquibase có thể dùng tag hoặc changeset marker để đánh dấu một mốc triển khai. Tag giúp xác định mốc lịch sử, nhưng không thay thế điều kiện vận hành.

Một release gate cho contract có thể yêu cầu:
- Tag của release expand và migrate đã được triển khai.
- Backfill job hoàn tất.
- Báo cáo parity đạt.
- Consumer inventory đã được xác nhận.
- Không còn query cột cũ trong thời gian quan sát.
- Application version mới đã ổn định.
- Có phê duyệt của owner database và application.

Pipeline có thể chạy validate, status, update-sql trước khi update. Nhưng các điều kiện consumer/telemetry phải được đánh giá bởi job hoặc quy trình có dữ liệu tương ứng; Liquibase precondition không tự biết trạng thái của mọi service bên ngoài.

Không dùng context/label như cơ chế duy nhất để ngăn contract sớm. Một filter bị cấu hình sai có thể làm migration chạy trên môi trường không dự kiến.

## 24. Các tình huống lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| App cũ lỗi column not found | Drop/rename cột trước khi hết instance cũ | Khôi phục compatibility nếu có thể; triển khai theo giai đoạn |
| Cột mới còn NULL sau backfill | Hàng ngoại lệ, job bỏ sót hoặc writer cũ | Audit theo khóa, xử lý ngoại lệ và chạy reconciliation |
| Hai cột khác nhau | Dual-write không nguyên tử hoặc nhiều writer | Xác định nguồn chuẩn, sửa write path và đối chiếu dữ liệu |
| Backfill ghi đè giá trị mới | Update không có điều kiện hoặc race | Dùng điều kiện/version/locking và chạy lại audit |
| Job backfill chạy mãi | Batch lớn, index thiếu, lock hoặc query kém | Đo execution plan, chia batch, giới hạn tải |
| NOT NULL thất bại | Vẫn còn NULL hoặc writer chưa chuyển | Không bỏ qua; xử lý dữ liệu và writer |
| Drop column bị chặn | View/FK/index/routine còn dependency | Liệt kê dependency và triển khai thay đổi theo thứ tự |
| Rollback app nhưng schema không tương thích | Cột cũ đã drop hoặc ngừng đồng bộ | Forward fix/restore; không chỉ rollback image |
| Checksum mismatch | Sửa changeset đã triển khai | Khôi phục migration cũ và thêm changeset mới |
| Báo cáo vẫn dùng cột cũ | Consumer ngoài chưa được inventory | Phối hợp owner và trì hoãn contract |
| API field đổi làm client lỗi | Thay đổi database và API cùng lúc | Version/deprecate API độc lập |
| Trigger đồng bộ tạo vòng lặp | Hai chiều ghi không có quy tắc | Sửa trigger hoặc dùng một nguồn chuẩn |
| Job cũ chạy lại sau contract | Scheduler/worker artifact cũ còn tồn tại | Chặn artifact cũ và xác minh mọi consumer |
| Backfill hoàn tất nhưng dữ liệu sai | Quy tắc tách/chuẩn hóa không chính xác | Dừng cutover, khôi phục nguồn và xử lý ngoại lệ |

Khi có lỗi, xác định giai đoạn đang chạy và trạng thái thật của cả hai cột trước khi retry. Không drop hoặc rename thêm object chỉ để làm pipeline xanh.

## 25. Bài thực hành: đổi tên cột qua ba release

**Bối cảnh:** bảng app.customer có full_name. Sản phẩm muốn dùng display_name và cần hỗ trợ rolling deployment.

### Phần A — Release expand

1. Tạo changeset add-display-name.
2. Chạy validate và update-sql.
3. Áp dụng trên database test có dữ liệu.
4. Xác minh full_name vẫn còn và display_name mới nullable.
5. Chạy app cũ trên schema mới, xác nhận không lỗi.

### Phần B — Release dual-write và backfill

1. Triển khai code ghi cả full_name và display_name trong cùng transaction.
2. Tạo dữ liệu mới và cập nhật dữ liệu cũ.
3. Chạy backfill theo batch chỉ cập nhật display_name còn NULL.
4. Mô phỏng một update đồng thời khi backfill đang chạy.
5. Xác minh job không ghi đè giá trị mới.
6. Đếm hàng NULL và so sánh hai cột.

### Phần C — Chuyển reader

1. Chạy app version mới đọc display_name.
2. Theo dõi fallback sang full_name.
3. Kiểm tra worker, report và consumer ngoài.
4. Chạy smoke test và theo dõi lỗi.
5. Chỉ ngừng dual-write khi đã hết mọi reader/writer cũ và đã có quyết định về rollback.

### Phần D — Contract

1. Xác nhận không còn consumer dùng full_name.
2. Kiểm tra dependency database.
3. Backup/retention theo chính sách.
4. Chạy precondition và update-sql.
5. Review changeset dropColumn.
6. Chạy migration trên database test.
7. Xác minh ứng dụng mới hoạt động.
8. Thử phương án recovery; ghi rõ dữ liệu không thể khôi phục bằng rollback tự động.

### Câu hỏi tự kiểm tra

- Vì sao không rename cột ngay trong release đầu? **Vì phiên bản ứng dụng cũ có thể vẫn đọc/ghi tên cột cũ trong rolling deployment.**
- Vì sao thêm cột mới nullable trước? **Để code cũ vẫn hoạt động và dữ liệu có thời gian được backfill.**
- Dual-write phải thực hiện thế nào? **Cập nhật hai cột theo một transaction hoặc cơ chế đồng bộ có tính nhất quán tương đương.**
- Backfill có thể ghi đè dữ liệu mới không? **Có nếu update không có điều kiện hoặc không xử lý race condition.**
- Khi nào chuyển reader sang cột mới? **Sau khi backfill và reconciliation đạt, đồng thời writer duy trì dữ liệu mới.**
- Khi nào drop cột cũ? **Sau khi mọi consumer đã chuyển, hết cửa sổ rollback và release gate được phê duyệt.**
- Có thể rollback ứng dụng sau khi drop cột cũ không? **Không thể giả định như vậy; cần schema tương thích, forward fix hoặc restore.**
- Có nên sửa changeset expand đã chạy để đổi tên cột không? **Không.** Giữ changeset bất biến và thêm changeset mới cho từng giai đoạn.

## 26. Checklist trước khi đổi tên hoặc tách cột

**Khảo sát và thiết kế**
- [ ] Đã inventory mọi reader/writer, job, report, view và consumer ngoài.
- [ ] Đã xác định ý nghĩa, kiểu, nullability và quy tắc chuyển đổi của cột mới.
- [ ] Đã xác định nguồn dữ liệu chuẩn trong từng giai đoạn.
- [ ] Đã phân tích dữ liệu mơ hồ và trường hợp không thể đảo ngược.
- [ ] Đã lập ma trận tương thích schema/application versions.

**Expand và migrate**
- [ ] Changeset chỉ thêm cấu trúc mới, chưa xóa cấu trúc cũ.
- [ ] Cột mới có nullability phù hợp với dữ liệu hiện tại.
- [ ] Code dual-write được triển khai trước hoặc cùng thời điểm bắt đầu backfill.
- [ ] Backfill có batch/checkpoint và có thể tiếp tục sau gián đoạn.
- [ ] Điều kiện update không ghi đè giá trị mới hơn.
- [ ] Có metric số hàng hoàn tất, NULL, mismatch và lỗi chuyển đổi.
- [ ] Đã kiểm tra dữ liệu biên và concurrency.

**Cutover và contract**
- [ ] Reader mới đã được triển khai và quan sát ổn định.
- [ ] Không còn consumer cũ trong thời gian quan sát phù hợp.
- [ ] Không còn dependency trong view, trigger, routine, report hoặc ETL.
- [ ] Precondition và release gate đã được kiểm tra.
- [ ] SQL contract được review trên đúng DBMS.
- [ ] Backup/retention và phương án recovery được xác nhận.
- [ ] Changeset drop cột nằm trong release riêng và có phê duyệt.

**Lịch sử và vận hành**
- [ ] Không sửa changeset đã triển khai.
- [ ] ID/AUTHOR/FILENAME ổn định.
- [ ] Checksum và DATABASECHANGELOG được kiểm tra sau mỗi bước.
- [ ] Rollback được đánh giá theo từng giai đoạn.
- [ ] Có forward fix khi thay đổi không thể đảo ngược.
- [ ] CI/CD triển khai theo đúng thứ tự và dùng cùng artifact đã kiểm thử.
- [ ] Đã xác minh không còn ứng dụng/job cũ sau contract.

**Kết luận:** đổi tên hoặc tách cột an toàn là một quá trình chuyển hợp đồng giữa database và các phiên bản ứng dụng. Expand schema trước để code cũ tiếp tục hoạt động; migrate dữ liệu bằng backfill có kiểm soát và dual-write; chuyển reader sau khi xác minh; chỉ contract khi không còn consumer cũ và đã qua cửa sổ rollback. Liquibase ghi nhận từng bước bằng changeset bất biến, precondition và lịch sử triển khai, còn CI/CD, telemetry và kiểm thử dữ liệu xác nhận thời điểm chuyển giai đoạn. Cách làm này giảm downtime, bảo toàn dữ liệu và giúp rolling deployment có thể diễn ra qua nhiều release.
