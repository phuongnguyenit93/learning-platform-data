# Đổi tên bảng, đổi tên cột và tác động tới mã ứng dụng

Trong chương **Thay đổi bảng** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, đổi tên bảng hoặc cột là một migration có vẻ đơn giản về SQL nhưng thường có rủi ro tương thích cao hơn thêm một đối tượng mới. Liquibase cung cấp các change type **renameTable** và **renameColumn** để mô tả thay đổi một cách có cấu trúc, theo dõi bằng changelog, changeset, checksum và bảng lịch sử DATABASECHANGELOG. Tuy nhiên, database đổi tên thành công chưa có nghĩa ứng dụng, báo cáo, tác vụ nền và các hệ thống tích hợp vẫn hoạt động.

Bài học hướng dẫn cách viết migration đổi tên, kiểm tra trạng thái hiện có bằng precondition, lập kế hoạch rollback, đánh giá các phụ thuộc và phối hợp phát hành trên development, staging, production qua Spring Boot hoặc CI/CD. Trọng tâm là phân biệt **thay đổi tên vật lý trong database** với **thay đổi giao ước mà mã ứng dụng đang sử dụng**.

## 1. Bối cảnh và mục tiêu

Giả sử ứng dụng đang dùng bảng customer với các cột id, full_name, email. Sau khi thống nhất lại mô hình nghiệp vụ, nhóm muốn:

- Đổi tên bảng **customer** thành **customer_account**.
- Đổi tên cột **full_name** thành **display_name**.
- Giữ dữ liệu khách hàng, các quan hệ và tính toàn vẹn.
- Cập nhật ứng dụng Java/Spring Boot cùng các truy vấn liên quan.
- Không để những instance ứng dụng phiên bản cũ gặp lỗi trong lúc triển khai, nếu hệ thống yêu cầu rolling deployment.

Đây là hai tác vụ kỹ thuật khác nhau:

1. **Schema migration:** thay đổi tên đối tượng trên database, ghi nhận trong DATABASECHANGELOG.
2. **Application migration:** thay đổi mapping ORM, native SQL, truy vấn/report, API/DTO và các thành phần tiêu thụ dữ liệu.

Nếu chỉ làm bước 1, SQL của ứng dụng cũ có thể báo lỗi vì không còn bảng/cột theo tên cũ. Nếu chỉ làm bước 2, ứng dụng mới có thể báo lỗi vì tên mới chưa tồn tại. Vì thế, lựa chọn thứ tự triển khai là một phần của thiết kế migration.

## 2. Rename khác với tạo mới và sao chép dữ liệu

Các thao tác dễ bị nhầm:

| Thao tác | Ý nghĩa | Rủi ro chính |
|---|---|---|
| renameTable | Đổi tên một bảng hiện có | Mã SQL và các hệ thống phụ thuộc tên bảng có thể hỏng |
| renameColumn | Đổi tên cột trong bảng hiện có | ORM mapping, SELECT/INSERT/UPDATE và contract dữ liệu có thể hỏng |
| createTable rồi copy dữ liệu | Tạo bảng mới, chuyển dữ liệu sang | Cần đồng bộ dữ liệu, khóa ngoại và chiến lược chuyển đổi |
| addColumn + backfill | Tạo cột mới, điền dữ liệu cũ | Phải quản lý đọc/ghi đồng thời và dữ liệu phát sinh trong quá trình chuyển |
| dropTable/dropColumn | Xóa đối tượng | Có thể mất dữ liệu và làm hỏng ứng dụng không tương thích |

Một lệnh đổi tên thường không cần chép toàn bộ dữ liệu sang đối tượng khác. Nhưng tác động chi tiết lên khóa, view, trigger, quyền, cache truy vấn và transaction phụ thuộc DBMS. Đừng suy luận rằng mọi hệ quản trị đều xử lý rename giống nhau chỉ vì cú pháp Liquibase tương tự.

## 3. Rename bảng bằng renameTable

### Changelog YAML cơ bản

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-rename-customer-table"
      author: "team-db"
      comment: "Đổi tên bảng customer thành customer_account"
      changes:
        - renameTable:
            schemaName: app
            oldTableName: customer
            newTableName: customer_account
      rollback:
        - renameTable:
            schemaName: app
            oldTableName: customer_account
            newTableName: customer
~~~

Những thuộc tính quan trọng:

- **oldTableName:** tên bảng tại thời điểm changeset bắt đầu.
- **newTableName:** tên bảng mong muốn sau khi chạy.
- **schemaName:** schema chứa bảng, nên chỉ rõ khi database có nhiều schema.
- **catalogName:** có thể cần nếu DBMS tổ chức đối tượng theo catalog.
- **id, author và đường dẫn changelog:** cùng tạo thành định danh lịch sử changeset.

Trong ví dụ, rollback đổi tên theo chiều ngược lại. Liquibase có thể hỗ trợ rollback tự động cho một số thay đổi đổi tên, nhưng khai báo rollback tường minh giúp người review nhìn thấy rõ ý định. **Rollback đổi tên bảng không tự sửa mã ứng dụng đã phát hành**, cũng không đảm bảo mọi đối tượng phụ thuộc đều hoạt động sau khi đổi lại.

### Thêm precondition để kiểm tra trạng thái

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-001-rename-customer-table"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - and:
            - tableExists:
                schemaName: app
                tableName: customer
            - not:
                - tableExists:
                    schemaName: app
                    tableName: customer_account
      changes:
        - renameTable:
            schemaName: app
            oldTableName: customer
            newTableName: customer_account
      rollback:
        - renameTable:
            schemaName: app
            oldTableName: customer_account
            newTableName: customer
~~~

Điều kiện yêu cầu **bảng cũ có tồn tại** và **bảng mới chưa tồn tại**. Nếu cả hai cùng tồn tại, hoặc cả hai cùng vắng mặt, migration dừng để điều tra thay vì đoán trạng thái. Đây là cách sử dụng an toàn hơn việc gán onFail: MARK_RAN cho mọi trường hợp. MARK_RAN sẽ đánh dấu changeset đã chạy mà không thực hiện rename; như vậy lịch sử có thể không phản ánh cấu trúc mong đợi.

Precondition là thao tác kiểm tra, không phải khóa tuyệt đối để ngăn một tiến trình khác thay schema giữa thời điểm kiểm tra và thực thi. Quy trình phát hành cần hạn chế các thay đổi DDL đồng thời.

## 4. Rename cột bằng renameColumn

### Cú pháp trên bảng đã đổi tên

Sau khi đổi customer thành customer_account, cột full_name có thể được đổi thành display_name:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-002-rename-customer-display-name"
      author: "team-db"
      comment: "Đổi tên cột full_name thành display_name"
      preConditions:
        - onFail: HALT
        - and:
            - tableExists:
                schemaName: app
                tableName: customer_account
            - columnExists:
                schemaName: app
                tableName: customer_account
                columnName: full_name
            - not:
                - columnExists:
                    schemaName: app
                    tableName: customer_account
                    columnName: display_name
      changes:
        - renameColumn:
            schemaName: app
            tableName: customer_account
            oldColumnName: full_name
            newColumnName: display_name
            columnDataType: VARCHAR(150)
      rollback:
        - renameColumn:
            schemaName: app
            tableName: customer_account
            oldColumnName: display_name
            newColumnName: full_name
            columnDataType: VARCHAR(150)
~~~

Các thuộc tính:

- **tableName:** tên bảng hiện hành; ở đây là customer_account, **không còn là customer**.
- **oldColumnName/newColumnName:** tên cũ và mới của cùng một cột.
- **columnDataType:** kiểu dữ liệu hiện có; yêu cầu cung cấp và cách xử lý có thể khác nhau theo DBMS (đáng lưu ý với MySQL/MariaDB). Phải lấy kiểu thực tế của cột, không đoán theo tên.
- **schemaName:** xác định schema chứa bảng.

Nếu bước đổi tên bảng chưa chạy, changeset đổi cột ở ví dụ sẽ không có bảng customer_account để thao tác. Khi triển khai thay đổi có phụ thuộc, phải giữ **thứ tự changelog** phù hợp; Liquibase không sắp xếp lại changeset dựa trên số trong id.

**RenameColumn không phải alterColumnDataType.** Thay tên thường được thiết kế để giữ giá trị và kiểu dữ liệu của cột; nếu cần đổi kiểu hoặc làm sạch dữ liệu, nên mô tả mục tiêu đó thành migration riêng có kiểm chứng.

## 5. Hai cách tổ chức migration đổi tên

### Cách 1: Hai changeset độc lập

Dùng một changeset cho renameTable và một changeset cho renameColumn như phần trước. Ưu điểm:

- Có hai mốc lịch sử rõ ràng trong DATABASECHANGELOG.
- Dễ review SQL của từng thay đổi.
- Có thể tách việc phát hành nếu tương thích ứng dụng cho phép.
- Rollback nhiều changeset thường cần chạy theo thứ tự ngược: đổi tên cột về full_name, sau đó đổi bảng về customer.

Nhược điểm: nếu DBMS không hỗ trợ transaction DDL đầy đủ, changeset đầu có thể thành công trong khi changeset sau thất bại. Database sẽ ở trạng thái trung gian, cần có quy trình khắc phục cụ thể.

### Cách 2: Một changeset gồm hai change

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-003-rename-customer-contract"
      author: "team-db"
      changes:
        - renameTable:
            schemaName: app
            oldTableName: customer
            newTableName: customer_account
        - renameColumn:
            schemaName: app
            tableName: customer_account
            oldColumnName: full_name
            newColumnName: display_name
            columnDataType: VARCHAR(150)
      rollback:
        - renameColumn:
            schemaName: app
            tableName: customer_account
            oldColumnName: display_name
            newColumnName: full_name
            columnDataType: VARCHAR(150)
        - renameTable:
            schemaName: app
            oldTableName: customer_account
            newTableName: customer
~~~

Cách này diễn đạt một thay đổi contract gắn bó chặt chẽ. Tuy nhiên, nếu hai thao tác không thể bảo đảm nguyên tử trên DBMS đích, một lỗi giữa chừng vẫn có thể để lại schema một phần. **Hai mẫu trong bài là lựa chọn thay thế, không được đồng thời chạy trên cùng database như hai migration nối tiếp.**

Việc chia hay gom changeset nên dựa vào ranh giới triển khai, giao dịch, rollback và khả năng giám sát, không chỉ dựa vào số lượng dòng YAML.

## 6. Liquibase tạo SQL khác nhau theo DBMS

Liquibase chuyển các change type renameTable/renameColumn thành SQL mà DBMS đích hiểu. Ví dụ về ý nghĩa thao tác:

~~~sql
-- Minh họa cú pháp trên PostgreSQL; không phải SQL chuẩn cho mọi DBMS.
ALTER TABLE app.customer RENAME TO customer_account;
ALTER TABLE app.customer_account RENAME COLUMN full_name TO display_name;
~~~

Trên các DBMS khác, cú pháp có thể khác: một số cần mô tả đầy đủ kiểu cột, một số cung cấp thủ tục riêng để đổi tên hoặc có quy tắc đặc biệt với schema/catalog. Các DBMS cũng khác nhau về:

- Khả năng rollback DDL trong transaction.
- Khóa và thời gian chặn truy vấn khi rename.
- Việc tự cập nhật metadata khóa ngoại, view hoặc stored procedure.
- Cách xử lý tên đối tượng được quote và phân biệt chữ hoa/thường.
- Hỗ trợ và giới hạn của renameColumn/renameTable qua driver.
- Quy tắc đổi tên đối tượng phụ trợ và cấp quyền.

Không ghi đè bằng SQL viết tay chỉ vì thấy nó quen thuộc nếu Liquibase có change type phù hợp. Change type trừu tượng thường dễ bảo trì khi cần hỗ trợ nhiều DBMS, nhưng vẫn phải kiểm tra SQL thực tế bằng **update-sql** trên đúng phiên bản Liquibase và DBMS.

Đặc biệt, một rename có thể là thao tác cập nhật metadata tương đối nhanh nhưng vẫn cần **schema lock** hoặc lock DDL trong một khoảng thời gian. Tốc độ trung bình thấp không đồng nghĩa không ảnh hưởng đến request đang chạy.

## 7. Ảnh hưởng đến ràng buộc và các đối tượng database phụ thuộc

Đổi tên bảng/cột không chỉ liên quan tới chính đối tượng được đổi. Trước migration, phải kiểm kê toàn bộ đối tượng có tham chiếu tới tên cũ.

| Thành phần | Rủi ro cần đánh giá |
|---|---|
| Primary key và unique constraint | Constraint có thể vẫn tồn tại nhưng tên quy ước chứa tên bảng/cột cũ |
| Foreign key | FK có thể được DBMS duy trì qua rename, nhưng tên và các script bên ngoài có thể lỗi |
| Index | Index có thể tiếp tục hoạt động nhưng tên index không tự phản ánh tên mới |
| View/materialized view | Định nghĩa hoặc phụ thuộc có thể được DBMS điều chỉnh, giữ nguyên hoặc trở nên không hợp lệ |
| Trigger/function/procedure | Mã SQL động hoặc text tham chiếu tên cũ có thể hỏng |
| Sequence và default expression | Cần xem phụ thuộc, tên sequence và hành vi identity/serial |
| Permission/grant | Quyền gắn với đối tượng có thể còn hoặc cần cập nhật tùy thao tác và DBMS |
| Partition/table inheritance | Một số DBMS có quy tắc đặc biệt khi đổi tên parent/partition |
| CDC/replication | Event schema, tên bảng trong topic và cấu hình connector có thể thay đổi |
| Job/ETL/report | Script hoặc mô hình BI có thể vẫn tham chiếu tên cũ |

Một tên constraint ví dụ **fk_order_customer** không tự nhất thiết đổi thành **fk_order_customer_account** khi renameTable. Nếu tên đối tượng cần được chuẩn hóa, đó là một thay đổi bổ sung cần được review. Đừng kết luận ràng buộc không còn chỉ vì tên vẫn cũ; hãy truy vấn metadata và kiểm tra các quan hệ thực tế.

### Đối chiếu metadata trước và sau

Với PostgreSQL, có thể dùng các truy vấn chỉ đọc như:

~~~sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = 'app'
  AND table_name IN ('customer', 'customer_account');

SELECT table_schema, table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'app'
  AND table_name IN ('customer', 'customer_account')
  AND column_name IN ('full_name', 'display_name');
~~~

Đối chiếu khóa và index bằng catalog hoặc các công cụ metadata tương ứng. Các truy vấn trên không chứng minh toàn bộ dependency hay tính đúng của dữ liệu; chúng chỉ cho biết một phần tình trạng schema. Khi sử dụng MySQL, SQL Server, Oracle hoặc DBMS khác, cần điều chỉnh truy vấn metadata.

## 8. Tác động trực tiếp tới mã Java/Spring Boot

Nếu ứng dụng dùng JPA/Hibernate, mapping thường chứa tên bảng và cột. Trước migration:

~~~java
@Entity
@Table(name = "customer", schema = "app")
public class Customer {
    @Id
    private Long id;

    @Column(name = "full_name", length = 150)
    private String fullName;

    @Column(name = "email")
    private String email;
}
~~~

Sau khi database đổi tên và ứng dụng mới tương thích:

~~~java
@Entity
@Table(name = "customer_account", schema = "app")
public class Customer {
    @Id
    private Long id;

    @Column(name = "display_name", length = 150)
    private String fullName;

    @Column(name = "email")
    private String email;
}
~~~

Tên thuộc tính Java **fullName** không bắt buộc phải đổi thành displayName. Điều quan trọng đối với ORM là mapping tới cột vật lý đang tồn tại. Nếu muốn đổi tên thuộc tính Java, cần kiểm tra getter/setter, mapper, DTO, JSON serialization, logic nghiệp vụ và contract API liên quan.

Trong Spring Boot, cấu hình kiểm tra schema ví dụ:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
  liquibase:
    enabled: true
    change-log: classpath:db/changelog/db.changelog-master.yaml
~~~

**ddl-auto: validate** giúp Hibernate kiểm tra một phần tính khớp giữa entity mapping và database lúc khởi động, nhưng không thay thế kiểm chứng migration hoặc xác nhận mọi native query. Không nên để Hibernate tự ý sửa schema trong production nhằm “vá” một migration thiếu bước.

### Những nơi dễ bị bỏ sót hơn entity mapping

- Repository dùng **nativeQuery = true** hoặc JDBC template.
- Query trong MyBatis XML, jOOQ code generation hoặc stored procedure.
- Entity relationship với **@JoinColumn** nếu cột FK cũng đổi tên.
- Công cụ sinh code từ schema và các DTO/mapstruct mapping.
- Batch job/cron, consumer event, xuất CSV, BI dashboard.
- Dịch vụ khác gọi trực tiếp database, CDC connector hoặc ETL.
- Test fixtures, seed SQL, migration test, tài liệu SQL vận hành.
- Cấu hình phân quyền theo bảng và quy trình DBA.

Ví dụ một truy vấn cũ:

~~~sql
SELECT id, full_name
FROM app.customer
WHERE id = ?;
~~~

Sẽ không tương thích với schema sau rename. Truy vấn ứng dụng mới cần dùng:

~~~sql
SELECT id, display_name
FROM app.customer_account
WHERE id = ?;
~~~

Để giữ nguyên tên trường trong response của API, có thể dùng alias:

~~~sql
SELECT id, display_name AS full_name
FROM app.customer_account
WHERE id = ?;
~~~

Alias là **tên cột kết quả**, không tái tạo cột full_name trong bảng. Nó giúp một số mapper/DTO tương thích nhưng không giải quyết các câu lệnh INSERT/UPDATE cũ. Không coi alias SELECT là giải pháp đầy đủ cho rolling deployment.

## 9. API contract khác database contract

Một dịch vụ có thể lưu dữ liệu vào cột display_name nhưng vẫn trả JSON field fullName vì API đã công bố tên đó. Ngược lại, đổi tên Java property có thể làm thư viện serialization đổi trường JSON nếu không có cấu hình tường minh.

Hãy tách ba lớp:

1. **Database:** app.customer_account.display_name.
2. **Domain/Java:** Customer.fullName hoặc Customer.displayName.
3. **API/event:** fullName, displayName hay tên trường theo hợp đồng với client.

Không cần thay đồng thời cả ba lớp nếu không có yêu cầu nghiệp vụ. Trong nhiều trường hợp, đổi tên database chỉ là cải tổ kỹ thuật nội bộ. Giữ API ổn định giúp giảm phạm vi thay đổi và rủi ro cho mobile app, frontend hoặc dịch vụ khác.

Nếu API/event cũng cần đổi tên, phải có chính sách versioning hoặc thời gian tương thích. Không sử dụng Liquibase như một cơ chế tự động đổi tên field JSON hoặc topic event.

## 10. Vì sao đổi tên trực tiếp dễ gây lỗi khi rolling deployment?

Xét hai phiên bản ứng dụng:

| Thành phần | Phiên bản cũ A | Phiên bản mới B |
|---|---|---|
| Tên bảng trong query | app.customer | app.customer_account |
| Tên cột trong query | full_name | display_name |
| Schema phù hợp | Trước rename | Sau rename |

Nếu migration rename được chạy **trước khi** tất cả instance A ngừng nhận request, instance A sẽ cố truy cập tên cũ và báo lỗi. Nếu instance B được deploy **trước khi** migration đổi tên, B sẽ truy cập tên mới chưa tồn tại.

Đây là hai chiều mất tương thích trong một bước rename. Việc Liquibase có DATABASECHANGELOGLOCK chỉ bảo đảm điều phối migration của Liquibase trên một database; nó **không khóa hoạt động ứng dụng** và không làm cho hai phiên bản ứng dụng tự tương thích.

Trong hệ thống cho phép downtime, có thể dùng một cửa sổ triển khai phối hợp:

1. Chặn traffic/ghi dữ liệu theo kế hoạch.
2. Dừng hoặc làm rỗng các instance sử dụng schema cũ.
3. Chạy Liquibase rename với SQL đã được review.
4. Khởi động ứng dụng mới và chạy smoke test.
5. Mở lại traffic khi quan sát ổn định.

Với hệ thống yêu cầu rolling/zero-downtime, **direct rename thường không phải bước đầu tiên phù hợp**. Cần thiết kế một giai đoạn tương thích trung gian.

## 11. Chiến lược expand–migrate–contract để đổi tên cột

Phương pháp phổ biến là không đổi tên cột vật lý ngay lập tức, mà chuyển sang cột mới qua các đợt phát hành. Ví dụ full_name -> display_name trong bảng customer.

### Pha 1 — Expand: thêm cột mới

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-010-expand-display-name"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - and:
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
                  type: VARCHAR(150)
~~~

Sau bước này, cả full_name và display_name cùng tồn tại. Instance A tiếp tục chạy với cột cũ; instance B có thể được cập nhật để nhận biết cột mới.

**Không thêm ràng buộc NOT NULL vào display_name ngay** nếu bảng đang có dữ liệu cần backfill hoặc vẫn có phiên bản cũ chỉ ghi full_name. Đặt NOT NULL quá sớm có thể khiến ghi dữ liệu thất bại.

### Pha 2 — Triển khai mã tương thích

Trong giai đoạn chuyển đổi:

- Các writer được nâng cấp để **ghi đồng bộ** full_name và display_name khi có thay đổi.
- Reader mới có thể ưu tiên display_name và fallback sang full_name nếu dữ liệu chưa được chuyển xong.
- Các giao dịch cập nhật phải tránh trạng thái hai cột không nhất quán.
- Nếu còn writer cũ chỉ ghi full_name, cần một cơ chế đồng bộ tương ứng ở tầng DB hoặc chiến lược điều phối rollout; chỉ nâng cấp một số writer là chưa đủ.

Ví dụ logic đọc:

~~~sql
SELECT id, COALESCE(display_name, full_name) AS effective_name
FROM app.customer;
~~~

**COALESCE** chỉ fallback khi display_name là NULL. Nó không tự nhận ra giá trị trống, dữ liệu lỗi hoặc trường hợp full_name vừa được writer cũ cập nhật sau khi display_name đã có giá trị. Vì vậy, không xem fallback đọc là giải pháp đồng bộ dữ liệu hoàn chỉnh.

Để tránh mất cập nhật, cần xác định **nguồn dữ liệu chính** trong từng pha. Khi writer cũ vẫn hoạt động, nên giữ full_name là nguồn chính và đồng bộ sang display_name một cách đáng tin cậy. Khi đã nâng cấp tất cả writer, có thể chuyển nguồn chính sang display_name.

### Pha 3 — Backfill dữ liệu

Ví dụ về mục đích cập nhật:

~~~sql
UPDATE app.customer
SET display_name = full_name
WHERE display_name IS NULL;
~~~

Với bảng lớn, không nên mặc định chạy một UPDATE toàn bảng trong một giao dịch dài. Hãy thiết kế backfill theo lô, theo khóa chính, có checkpoint, giám sát lock/replication lag và khả năng chạy lại an toàn. Phải xử lý các row được thêm/sửa **trong lúc** backfill đang chạy.

Một backfill đơn giản với WHERE display_name IS NULL có thể không cập nhật các row đã có display_name cũ khi writer A sửa full_name sau đó. Vì vậy, yêu cầu đồng bộ ghi và thời điểm cutover quan trọng hơn bản thân câu UPDATE.

Nếu cần dùng Liquibase để chạy backfill, có thể tạo changeset riêng hoặc tham chiếu sqlFile. Nhưng với hàng triệu bản ghi và nhiều giờ xử lý, có thể phù hợp hơn khi dùng một job dữ liệu được điều phối riêng, có audit và checkpoint. Việc chọn công cụ phải giữ được khả năng xác nhận tiến độ và phục hồi.

### Pha 4 — Chuyển toàn bộ reader/writer sang tên mới

Chỉ khi kiểm chứng tất cả dịch vụ, worker, báo cáo và consumer không còn phụ thuộc full_name mới được kết thúc giai đoạn tương thích. Nên đo lường truy cập tên cũ bằng log ứng dụng, truy vấn quan sát hoặc các công cụ phù hợp; không chỉ dựa vào việc một bản build đã triển khai thành công.

Có thể thêm kiểm tra dữ liệu:

~~~sql
SELECT COUNT(*) AS missing_new_value
FROM app.customer
WHERE display_name IS NULL AND full_name IS NOT NULL;
~~~

Truy vấn chỉ minh họa một điều kiện đối chiếu. Nếu cho phép cả hai cột NULL hoặc tên có quy tắc chuẩn hóa, cần điều kiện nhất quán theo nghiệp vụ. Việc tất cả row có display_name khác NULL cũng không chứng minh mọi writer đã ngừng ghi cột cũ.

### Pha 5 — Contract: xóa cột cũ

Khi không còn thành phần nào sử dụng full_name, có thể tạo changeset riêng xóa cột:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261119-011-contract-full-name"
      author: "team-db"
      preConditions:
        - onFail: HALT
        - and:
            - columnExists:
                schemaName: app
                tableName: customer
                columnName: display_name
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

**Đây là thao tác có nguy cơ mất dữ liệu**, khác với rename trực tiếp. Trước khi chạy, phải có xác nhận nghiệp vụ, backup/khả năng restore và kế hoạch rollback hoặc forward fix. Không xóa cột ngay sau bước backfill chỉ vì lúc đó dữ liệu đã khớp.

Expand–migrate–contract không phải lúc nào cũng ngắn hơn rename trực tiếp; nó đổi độ phức tạp triển khai lấy khả năng tương thích giữa nhiều phiên bản ứng dụng.

## 12. Thay đổi tên bảng trong hệ thống không downtime

Đổi tên bảng khó tạo giai đoạn tương thích hơn đổi tên cột vì mã cũ và mã mới có thể cùng đọc/ghi **hai tên bảng khác nhau**.

Một số phương án:

**Phương án A — trì hoãn rename vật lý.** Đổi tên entity/domain/API trước, nhưng mapping vật lý vẫn trỏ đến app.customer. Nếu mục tiêu chủ yếu là dễ hiểu trong mã Java, đây thường là cách ít rủi ro nhất. Đổi tên bảng sau khi đã có cửa sổ bảo trì hoặc giải pháp tương thích được kiểm chứng.

**Phương án B — compatibility view/alias.** Một số DBMS cho phép tạo view hoặc synonym mang tên cũ trỏ tới bảng đã đổi tên. Điều này có thể giúp SELECT cũ tiếp tục chạy. Tuy nhiên, khả năng INSERT/UPDATE/DELETE qua view, trigger INSTEAD OF, khóa, quyền, tên cột và hành vi transaction đều phụ thuộc DBMS. Không mặc định một view có thể thay thế đầy đủ bảng cho ứng dụng cũ.

**Phương án C — bảng mới và đồng bộ dữ liệu.** Tạo bảng mới, backfill, đồng bộ ghi hai chiều hoặc một chiều theo nguồn dữ liệu chính, chuyển dần reader/writer rồi loại bỏ bảng cũ. Cách này có độ phức tạp cao: khóa chính, foreign key, sequence, index, trigger, CDC, độ trễ replication và xử lý xung đột cần được thiết kế cẩn thận.

**Phương án D — dừng ghi ngắn và chuyển có kiểm soát.** Nếu ứng dụng cho phép maintenance window, direct rename với downtime dự đoán được có thể đơn giản và an toàn hơn một hệ thống dual-write phức tạp.

Việc chọn phương án phụ thuộc SLA, độ lớn dữ liệu, số lượng consumer và năng lực vận hành. Không gắn nhãn zero-downtime cho một phương án nếu chưa kiểm tra khả năng chạy đồng thời phiên bản A và B trên database thực tế.

## 13. Rollback không chỉ là đổi tên ngược lại

Với renameTable/renameColumn trực tiếp, rollback cơ bản có thể là thao tác rename ngược. Nhưng phải phân biệt:

1. **Rollback schema:** đưa tên bảng/cột về như trước.
2. **Rollback ứng dụng:** đưa các instance sử dụng tên mới về phiên bản tương thích tên cũ.
3. **Rollback dữ liệu:** đảm bảo các bản ghi được tạo/sửa trong khoảng triển khai không bị mất hoặc không thể đọc.
4. **Rollback tích hợp:** xác nhận BI, batch, ETL, CDC, job và hệ thống ngoài dùng đúng tên sau khôi phục.

Ví dụ, nếu ứng dụng mới đã phát hành và đang dùng app.customer_account, việc chỉ đổi bảng về app.customer có thể làm ứng dụng mới ngừng hoạt động. Ngược lại, nếu rollback ứng dụng trước schema, phiên bản cũ có thể không có bảng customer để truy vấn.

Với expand–migrate–contract, rollback giai đoạn expand thường dễ hơn khi cả hai cột còn tồn tại. Sau pha contract, việc xóa cột cũ làm khôi phục phức tạp hơn nhiều. Một rollback dropColumn không có dữ liệu đầy đủ để tái tạo full_name chỉ bằng một lệnh addColumn.

### Kiểm tra rollback trước khi phát hành

- Xác định version code nào tương thích với schema ở từng mốc.
- Xem câu SQL rollback dự kiến bằng khả năng dry-run/rollback-sql của phiên bản Liquibase đang dùng.
- Kiểm tra quyền, phụ thuộc FK/view, lock và độ dài downtime.
- Thử rollback trong database thử nghiệm có dữ liệu đại diện, không chỉ database rỗng.
- Xác định điểm **không còn rollback đơn giản được** sau khi xóa dữ liệu/đối tượng.
- Chuẩn bị phương án sửa tiến (forward fix) nếu rollback kỹ thuật không còn phù hợp.

Lưu ý rollback của Liquibase gắn với changeset và trạng thái lịch sử. Không nên tự đảo ngược rename bằng SQL client mà không có kế hoạch đồng bộ lại DATABASECHANGELOG.

## 14. Precondition và checksum khi đổi tên

Liquibase định danh một changeset bằng **ID + AUTHOR + FILENAME**. Sau khi changeset đã chạy ở bất kỳ môi trường nào, không tùy tiện sửa id, author, đường dẫn changelog hoặc nội dung để thay đổi tên mới. Liquibase dùng checksum (MD5SUM trong DATABASECHANGELOG) để phát hiện các thay đổi nội dung; sửa changeset cũ có thể dẫn đến lỗi checksum.

Khi cần đổi thêm một lần từ display_name sang preferred_name, hãy viết **changeset mới**:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: "20261120-001-rename-display-name"
      author: "team-db"
      changes:
        - renameColumn:
            schemaName: app
            tableName: customer_account
            oldColumnName: display_name
            newColumnName: preferred_name
            columnDataType: VARCHAR(150)
~~~

Precondition như tableExists, columnExists và not giúp kiểm tra giả định của mỗi lần rename. Nhưng precondition không kiểm tra toàn bộ mapping ứng dụng hoặc sự an toàn của rolling deployment. Không sử dụng clear-checksums hoặc MARK_RAN như đường tắt mặc định để xử lý thay đổi tên đã triển khai sai.

Nếu một môi trường có bảng customer_account nhưng DATABASECHANGELOG không ghi nhận changeset rename tương ứng, phải điều tra: rename đã được DBA chạy tay, baseline sai, hay file/id/author đã thay đổi? Không tự đánh dấu đã chạy trước khi so sánh trạng thái thực tế.

## 15. Triển khai cùng changelog qua nhiều môi trường

Một changelog đổi tên được promote qua development, staging và production phải giữ cùng định danh changeset và nội dung đã review. Tuy nhiên, trạng thái database và thời điểm triển khai code có thể khác nhau.

| Môi trường | Điều cần xác minh trước rename |
|---|---|
| Development | Thử SQL, mapping Hibernate, integration test, giả lập phiên bản cũ/mới |
| Staging | Thử quy trình rolling deploy, thời gian lock, lịch chạy batch và truy vấn/report |
| Production | Phê duyệt cửa sổ chuyển đổi, backup, quan sát, quyền DDL, kế hoạch rollback |

Những biến môi trường như JDBC URL, schema và credentials được cấp cho Liquibase qua CLI hoặc Spring Boot; chúng không tự làm thay đổi nghĩa của renameTable. Nếu schema đích khác nhau, phải dùng cấu hình và changelog parameters được quản lý rõ ràng, rồi kiểm tra generated SQL trước khi chạy.

Trong mô hình nhiều instance, **Liquibase startup trong từng ứng dụng** có thể được điều phối bằng DATABASECHANGELOGLOCK, nhưng lock đó không đảm bảo mọi instance đang chạy đã dùng mapping mới. Với migration phá tương thích như rename trực tiếp, thường cần điều phối một job phát hành riêng hoặc một trình tự deploy có kiểm soát rõ ràng thay vì dựa hoàn toàn vào startup migration.

## 16. Quy trình kiểm chứng trước và sau rename

Giả sử changelog đã được cấu hình đúng, có kết nối tới database thử nghiệm:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

- **validate:** kiểm tra cấu trúc changelog và một số ràng buộc metadata mà công cụ có thể kiểm chứng.
- **status --verbose:** xem changeset nào còn pending theo bộ lọc và DATABASECHANGELOG của database đích.
- **update-sql:** xem SQL Liquibase dự kiến sinh ra; đặc biệt kiểm tra schema, tên cũ/tên mới, kiểu cột và tác động DBMS.

Sau review, chạy update trong môi trường đã được phép:

~~~bash
liquibase update
liquibase history
~~~

Sau triển khai, cần xác minh tối thiểu:

1. Bảng hoặc cột mới xuất hiện tại **đúng schema**.
2. Bảng/cột cũ không còn, trừ khi chủ động giữ compatibility layer.
3. Số lượng bản ghi, khóa chính và dữ liệu quan trọng không bị thay đổi ngoài dự kiến.
4. Foreign key, unique constraint, index, view và các phụ thuộc vẫn hoạt động.
5. DATABASECHANGELOG ghi nhận id, author, filename và trạng thái phù hợp.
6. Ứng dụng mới có thể đọc/ghi dữ liệu qua ORM và native SQL.
7. Job, báo cáo, CDC và consumer liên quan không còn lỗi tên đối tượng.
8. Không xuất hiện lỗi relation/table/column not found trong log.
9. Kế hoạch rollback vẫn khả thi với phiên bản code đang chạy.

Ví dụ SQL để xem lịch sử:

~~~sql
SELECT ID, AUTHOR, FILENAME, EXECTYPE, DATEEXECUTED, MD5SUM
FROM DATABASECHANGELOG
WHERE ID IN (
    '20261119-001-rename-customer-table',
    '20261119-002-rename-customer-display-name'
)
ORDER BY DATEEXECUTED, ORDEREXECUTED;
~~~

Dòng trong DATABASECHANGELOG chứng minh Liquibase đã ghi nhận changeset theo cơ chế của nó; **không tự chứng minh mọi query của ứng dụng đã được cập nhật đúng**.

## 17. Các lỗi hay gặp và cách điều tra

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| relation/table customer not found | Ứng dụng cũ còn truy vấn bảng cũ sau rename | Kiểm tra rollout instance, native SQL và job; có kế hoạch compatibility |
| column full_name not found | Mapping hoặc SQL cũ chưa đổi | Sửa entity mapping/query; kiểm tra các component ngoài JPA |
| Hibernate schema validation failed | Entity mới và database ở hai phiên bản khác nhau | Xác nhận thứ tự migration/startup và cấu hình ddl-auto |
| RenameColumn thất bại dù cột cũ tồn tại | tableName/schemaName sai hoặc columnDataType không phù hợp DBMS | Kiểm tra metadata và SQL từ update-sql |
| Database có cả tên cũ và mới | Đang ở pha expand, có đối tượng tạo ngoài Liquibase hoặc migration dang dở | Đối chiếu lịch sử, kế hoạch rollout, xác định trạng thái chính thức |
| FK vẫn hoạt động nhưng tên ràng buộc cũ | DBMS không tự đổi tên constraint | Quyết định có cần rename constraint riêng; kiểm tra metadata |
| View/batch/report bị lỗi | Phụ thuộc dùng tên cũ dưới dạng text/SQL động | Kiểm kê consumer và triển khai bản tương thích |
| Migration bị chặn lâu | DDL lock hoặc transaction dài đang hoạt động | Quan sát lock, chọn maintenance window/timeout thích hợp |
| Rollback schema xong ứng dụng lỗi | Code vẫn trỏ tên mới | Phối hợp rollback ứng dụng với schema; xác minh phiên bản tương thích |
| Changeset rename bị chọn chạy lại | Đã đổi id, author hoặc filename | Đối chiếu khóa lịch sử; không sửa DATABASECHANGELOG tùy tiện |
| Backfill bỏ sót thay đổi | Writer cũ ghi sau đợt backfill, không đồng bộ | Củng cố dual-write/sync, checkpoint và đối chiếu trước contract |
| Production khác staging | Khác version DBMS, schema, dữ liệu, quyền hoặc consumer | Dùng bản thử nghiệm đại diện và cấu hình triển khai được audit |

Khi điều tra, phân biệt lỗi **Liquibase đọc changelog**, lỗi **kết nối/quyền**, lỗi **schema thực tế**, lỗi **mapping ứng dụng** và lỗi **phối hợp phiên bản**. Cùng một thông báo SQL error có thể bắt nguồn từ hai bước triển khai lệch nhau chứ không phải câu lệnh rename sai cú pháp.

## 18. Thực hành: đổi tên có kiểm chứng và đánh giá tương thích

**Đề bài:** một database thử nghiệm có bảng app.customer với các cột id, full_name VARCHAR(150), email. Cần đổi thành app.customer_account với cột display_name và cập nhật một ứng dụng Spring Boot.

### Phần A — Direct rename trên database thử nghiệm riêng

1. Kiểm tra dữ liệu ban đầu, số lượng row, khóa và index.
2. Tạo hai changeset renameTable/renameColumn theo phần 3 và 4, dùng một changelog gốc.
3. Chạy validate và status --verbose.
4. Chạy update-sql, đọc SQL, xác nhận bảng/cột cũ và mới ở đúng schema.
5. Thực hiện update khi không có ứng dụng thử nghiệm nào đang ghi dữ liệu.
6. Kiểm tra thông tin schema và số lượng bản ghi sau rename.
7. Cập nhật @Table/@Column hoặc SQL truy cập bảng/cột trong Spring Boot.
8. Khởi động ứng dụng với schema validation, chạy test đọc/ghi.
9. Thử rollback trong một database **có thể xóa và khôi phục**, phối hợp phiên bản ứng dụng.

### Phần B — Mô phỏng rolling deployment

Giữ hai bản ứng dụng:

- A: chỉ biết bảng customer và cột full_name.
- B: chỉ biết bảng customer_account và cột display_name.

Hỏi: khi chạy direct rename lúc A và B cùng nhận traffic, có bảo đảm cả hai cùng hoạt động không? **Không.** Mỗi bản dùng tên vật lý khác nhau. Cần cửa sổ bảo trì hoặc một tầng tương thích được thiết kế riêng.

Thử một phương án ít phá tương thích hơn:

1. Giữ tên bảng customer trong giai đoạn đầu.
2. Thêm cột display_name nullable.
3. Đưa bản ứng dụng chuyển tiếp có cơ chế ghi/đọc tương thích, giám sát dữ liệu.
4. Backfill theo lô và đối chiếu dữ liệu.
5. Chuyển toàn bộ reader/writer sang display_name.
6. Chỉ sau khi xác minh không còn consumer cũ mới xóa full_name.
7. Quyết định **riêng** thời điểm và phương án đổi tên bảng customer.

### Câu hỏi tự kiểm tra

- RenameTable có tự đổi tên lớp Java Customer không? **Không.** Tên class độc lập với mapping @Table.
- RenameColumn có bảo đảm mọi native query tự cập nhật không? **Không.**
- Có thể chỉ dựa vào DATABASECHANGELOG để biết rolling deploy an toàn không? **Không.** Phải kiểm chứng consumer ứng dụng.
- Vì sao precondition tableExists + not tableExists phù hợp? **Nó kiểm tra trạng thái đầu vào rõ ràng và dừng khi bất thường.**
- Tại sao dual-write có thể sai dù backfill thành công? **Writer cũ có thể tiếp tục cập nhật cột cũ, khiến hai cột lệch.**
- Tại sao rollback sau dropColumn khó hơn rollback renameColumn? **Dữ liệu cột đã xóa có thể không còn để khôi phục.**

## 19. Checklist thiết kế và review migration đổi tên

- [ ] Đã xác định rõ bảng/cột cũ, bảng/cột mới, schema và DBMS đích.
- [ ] Đã kiểm tra kiểu cột và các phụ thuộc trước khi viết renameColumn.
- [ ] Đã chọn đúng change type renameTable hoặc renameColumn, không nhầm với create/drop.
- [ ] Có precondition kiểm tra đối tượng cũ tồn tại và tên mới chưa tồn tại.
- [ ] Đã review SQL Liquibase sinh ra trên đúng DBMS/version.
- [ ] Đã đánh giá lock DDL, transaction, downtime và khối lượng truy cập.
- [ ] Đã kiểm kê khóa chính, khóa ngoại, index, view, trigger, sequence và permission.
- [ ] Đã rà soát JPA entity, @Table/@Column, repository, native SQL và batch job.
- [ ] Đã rà soát API, event, report, ETL, CDC và mọi dịch vụ phụ thuộc database.
- [ ] Đã quyết định direct rename có downtime hay chiến lược tương thích dần.
- [ ] Nếu dùng expand–migrate–contract, đã thiết kế sync, backfill, cutover và contract riêng.
- [ ] Đã thử cả tình huống nhiều phiên bản ứng dụng hoạt động đồng thời nếu yêu cầu rolling deploy.
- [ ] Đã giữ bất biến id, author, filename và nội dung changeset đã phát hành.
- [ ] Đã thử rollback cùng với phiên bản code phù hợp và dữ liệu đại diện.
- [ ] Đã chuẩn bị backup, quan sát lỗi và phương án khôi phục/sửa tiến.
- [ ] Sau update, đã kiểm chứng DATABASECHANGELOG và dữ liệu/schema thực tế.
- [ ] Artifact/changelog promote qua môi trường không bị chỉnh sửa khác với bản đã kiểm thử.

**Kết luận:** renameTable và renameColumn của Liquibase giải quyết phần thay đổi tên trong database, nhưng không thể tự bảo đảm hợp đồng mà ứng dụng và các hệ thống tích hợp đang sử dụng. Muốn đổi tên an toàn, hãy thiết kế migration cùng kế hoạch phát hành mã ứng dụng: dùng direct rename khi có thể điều phối đồng bộ, hoặc dùng expand–migrate–contract khi phải duy trì tương thích qua nhiều phiên bản. Precondition, checksum, DATABASECHANGELOG, review SQL và thử rollback giúp kiểm chứng từng bước; việc đánh giá phụ thuộc và vận hành mới quyết định liệu thay đổi thực sự an toàn trên production.
