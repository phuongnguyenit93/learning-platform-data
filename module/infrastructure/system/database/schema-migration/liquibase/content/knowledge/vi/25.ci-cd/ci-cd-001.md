# Xây dựng chuỗi validate, kiểm thử và xem trước SQL

## 1. Mục tiêu của pipeline Liquibase

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, Liquibase quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai. Quy trình còn cần migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Để đưa thay đổi database vào release có kiểm soát, pipeline phải trả lời ba câu hỏi:

1. **Changelog có hợp lệ không?** Cấu trúc XML/YAML/JSON/formatted SQL, include, changeset identity và thuộc tính Liquibase có được khai báo đúng không?
2. **Migration có hoạt động trên DBMS đích không?** SQL có chạy được, dữ liệu có đáp ứng precondition, constraint có thể tạo và ứng dụng có tương thích schema mới không?
3. **SQL nào sẽ được thực thi trên database mục tiêu?** Tập changeset pending, context/label/dbms filter, thứ tự và tác động DDL/DML có đúng với release dự kiến không?

Một pipeline chỉ chạy **validate** rồi kết luận migration an toàn là chưa đủ. Lệnh này giúp phát hiện nhiều lỗi cấu trúc changelog, nhưng không chứng minh mọi câu SQL sẽ thực thi thành công trên database production. Ngược lại, chỉ chạy **update-sql** cũng chưa đủ: SQL preview cần được review, kiểm thử với dữ liệu đại diện và đối chiếu trạng thái database thực tế.

Bài học này hướng dẫn xây dựng chuỗi **validate → kiểm thử migration → xem trước SQL → review/phê duyệt → triển khai → hậu kiểm**. Các bước được tổ chức theo hai thời điểm: kiểm tra sớm trong pull request và kiểm soát chặt hơn trước khi triển khai vào môi trường dùng chung.

## 2. Kiến trúc các cổng kiểm tra

Một pipeline tổng quát:

```text
Developer tạo changeset
        |
        v
Pull request
        |
        v
Kiểm tra cấu trúc / lint / Liquibase validate
        |
        v
Build changelog artifact bất biến
        |
        v
Migration integration test
  - database trống
  - nâng cấp từ schema phiên bản trước
  - dữ liệu đại diện
        |
        v
Status + update-sql + rollback preview
        |
        v
Review SQL, rủi ro, thời gian và quyền
        |
        v
Merge / release approval
        |
        v
Preflight trên database mục tiêu
        |
        v
Liquibase update
        |
        v
Hậu kiểm history + schema + dữ liệu
        |
        v
Cho phép rollout ứng dụng
```

Mỗi cổng có mục đích riêng:

| Cổng | Câu hỏi chính | Bằng chứng |
|---|---|---|
| Parse/lint | File có đúng cú pháp định dạng? | Kết quả parser/linter |
| **validate** | Liquibase có đọc và kiểm tra changelog được không? | Exit code, log validation |
| Migration test | Changeset có chạy trên DBMS đích không? | Test result, schema/data assertions |
| **status --verbose** | Changeset nào đang pending? | Danh sách pending theo DB và filters |
| **update-sql** | Liquibase dự kiến gửi SQL nào? | SQL preview đã lưu/review |
| Rollback preview/test | Có thể hoàn tác phần nào và bằng cách nào? | Rollback SQL và kết quả thử nghiệm |
| Approval | Rủi ro đã được người có trách nhiệm xem chưa? | Review/approval record |
| Deploy | Database có đạt trạng thái yêu cầu? | Deployment log và Liquibase history |
| Post-check | Schema/data thực tế có khớp kỳ vọng? | Đối soát sau triển khai |

Không phải mọi dự án cần một job riêng cho từng cổng. Có thể gộp các bước trong một workflow, nhưng kết quả và điều kiện thất bại phải phân biệt rõ. Một cổng chỉ đạt khi đã có bằng chứng tương ứng.

## 3. Phân biệt validate, status và update-sql

Ba lệnh thường xuất hiện trong pipeline nhưng trả lời những câu hỏi khác nhau.

### 3.1. validate: kiểm tra changelog

```bash
liquibase validate
```

**validate** yêu cầu Liquibase đọc và kiểm tra changelog theo các quy tắc mà phiên bản đang dùng hỗ trợ. Nó hữu ích để phát hiện:

- XML/YAML/JSON/formatted SQL sai cấu trúc.
- Include hoặc resource không thể giải quyết.
- Changeset thiếu thông tin bắt buộc.
- Một số thuộc tính hoặc change type không hợp lệ.
- Vấn đề validation mà Liquibase có thể phát hiện trong ngữ cảnh thực thi lệnh.

Cần hiểu giới hạn: **validate không phải là một lần triển khai thử**. Nó không chứng minh toàn bộ SQL sẽ chạy thành công trên DBMS production, dữ liệu hiện tại sẽ vượt qua precondition, hoặc migration sẽ hoàn tất trong thời gian cho phép.

### 3.2. status --verbose: xác định changeset pending

```bash
liquibase status --verbose
```

**status --verbose** so sánh changelog hiện tại với lịch sử database được kết nối và cho biết changeset nào còn pending theo cấu hình đang dùng.

Kết quả phụ thuộc vào root changelog và file include, database URL/catalog/schema và bảng metadata, context/label/dbms filter và parameters, Liquibase version và identity changeset, cùng history thực tế trong **DATABASECHANGELOG**.

Một changeset không xuất hiện trong danh sách pending có thể đã được áp dụng, bị filter, không được include hoặc được nhận diện theo identity khác. Đừng coi danh sách ngắn là bằng chứng database đã đúng; cần đối chiếu manifest/release expectation và schema thực tế.

### 3.3. update-sql: xem trước SQL sẽ chạy

```bash
liquibase update-sql
```

**update-sql** sinh SQL mà Liquibase dự kiến thực thi cho các changeset pending theo database và cấu hình hiện tại. Lệnh này hữu ích để review câu DDL/DML được sinh từ change type, thứ tự statement và changeset, schema/catalog được nhắm tới, filter context/label/dbms, câu SQL tùy chỉnh và delimiter, cũng như tác động có thể thấy trước như drop, rewrite, backfill hoặc tạo index.

**update-sql là bước preview, không phải bước thực thi update.** Tuy vậy, nó thường cần kết nối database để đọc history và xác định changeset pending. Vì thế, preview phải chạy với đúng database đích hoặc database đại diện và đúng cấu hình release.

### 3.4. Một lệnh thành công không thay thế các lệnh còn lại

| Kết quả | Điều có thể kết luận | Điều chưa thể kết luận |
|---|---|---|
| **validate** pass | Changelog qua các kiểm tra validation của Liquibase | SQL chắc chắn chạy được |
| **status** không có pending | Không có changeset pending theo cấu hình và DB đang kết nối | Schema không drift hoặc app tương thích |
| **update-sql** sinh SQL | Liquibase đã tạo preview cho tập changeset được chọn | SQL đã chạy thành công hoặc dữ liệu hợp lệ |
| Integration test pass | Bộ migration chạy trong database test cụ thể | Production có cùng version/config/data/permissions |
| Deploy pass | Lệnh triển khai báo thành công | Mọi schema/data invariant và ứng dụng đều đúng nếu chưa hậu kiểm |

Một pipeline tốt ghép các bằng chứng này thay vì dùng một kết quả làm đại diện cho toàn bộ chất lượng migration.

## 4. Chốt đầu vào để các bước dùng cùng một changelog

Một nguyên nhân phổ biến gây sai lệch là mỗi bước kiểm tra dùng một phiên bản file khác nhau. Ví dụ pull request validate working tree, nhưng release job lại tải changelog từ branch mới nhất hoặc một artifact đã được build trước đó.

Hãy xác định đầu vào bất biến cho release:

- Commit SHA đã được review/merge.
- Application artifact hoặc migration artifact.
- Image digest/checksum.
- Root changelog path.
- Liquibase version và JDBC driver.
- DBMS/version mục tiêu.
- Context, label, parameters và default schema.
- Manifest liệt kê changeset dự kiến hoặc schema milestone.

Ví dụ manifest:

```yaml
release:
  service: customer-service
  version: 3.8.0
  commit: 8c2d91a
  migrationArtifact: customer-service-db-3.8.0
  changelog:
    root: db/changelog/db.changelog-master.yaml
    liquibaseVersion: 4.30.0
    contexts:
      - production
    labels:
      - release-3.8
  database:
    engine: PostgreSQL
    majorVersion: 16
```

Các giá trị trên chỉ minh họa. Pipeline phải tạo manifest từ artifact thật và lưu cùng release record. Không tự suy ra phiên bản Liquibase hoặc tập changeset từ tên thư mục.

### 4.1. Không validate một file rồi deploy file khác

Nếu changelog được đóng gói trong JAR, container image hoặc migration bundle, hãy chạy validation trên chính artifact sẽ phát hành hoặc xác nhận nội dung trong artifact có cùng checksum với nội dung đã kiểm tra.

Nếu pipeline build lại artifact sau khi preview, cần chứng minh artifact mới tương đương artifact đã review. Cách đơn giản hơn là build một lần, gắn digest, rồi chuyển cùng artifact qua các stage.

### 4.2. Giữ thay đổi đã triển khai theo quy tắc append-only

Changeset đã chạy nên được xem như lịch sử bất biến. Pipeline có thể kiểm tra diff của commit để phát hiện sửa nội dung changeset cũ, đổi ID/author hoặc di chuyển file. Nếu cần thay đổi logic, tạo changeset mới; nếu cần di chuyển file, bảo toàn logical path theo chính sách đã kiểm chứng.

## 5. Thiết kế pipeline cho pull request

Pull request là nơi phát hiện lỗi sớm và rẻ. Một chuỗi kiểm tra phù hợp:

1. Kiểm tra định dạng và cấu trúc file.
2. Kiểm tra include/resource có tồn tại.
3. Chạy Liquibase **validate**.
4. Build artifact changelog/application.
5. Khởi tạo database thử nghiệm đúng DBMS production.
6. Chạy migration từ database trống.
7. Chạy migration từ snapshot hoặc baseline của release trước.
8. Kiểm tra schema, dữ liệu và **DATABASECHANGELOG**.
9. Sinh **update-sql** và lưu làm artifact review.
10. Kiểm tra rollback preview hoặc thử rollback với thay đổi có rollback được.

Ví dụ pipeline logic:

```yaml
stages:
  - static-check
  - build
  - migration-test
  - sql-preview
  - review
```

Đây là mô hình khái quát, không phải cú pháp cấu hình đầy đủ cho một CI vendor cụ thể. Trong hệ thống thật, từng stage cần khai báo dependency, timeout, artifact và quy tắc khi thất bại.

### 5.1. Kiểm tra nhanh và kiểm tra theo DBMS

Nếu dự án có H2, có thể giữ H2 cho một số test nhanh, nhưng migration integration phải dùng engine production. Nếu production là PostgreSQL, dùng PostgreSQL; nếu production là Oracle hoặc SQL Server, kiểm thử trên engine tương ứng.

Không cho phép container DBMS thật không khởi động rồi tự fallback sang H2. Khi tầng kiểm thử bắt buộc không thể chạy, pipeline phải báo lỗi rõ ràng.

## 6. Migration integration test: database trống và database đã có dữ liệu

Chỉ chạy changelog trên database trống là chưa đủ. Production thường nâng cấp từ schema đã có lịch sử và dữ liệu cũ.

### 6.1. Fresh install

Fresh install kiểm tra toàn bộ root changelog từ đầu:

1. Tạo database trống trên DBMS mục tiêu.
2. Chạy Liquibase với root changelog của artifact.
3. Xác nhận mọi changeset dự kiến đã được ghi nhận.
4. Đối chiếu bảng, cột, kiểu dữ liệu, nullability và default.
5. Kiểm tra primary key, unique, foreign key, check và index.
6. Kiểm tra view, sequence, trigger hoặc object đặc thù nếu có.
7. Chạy một số truy vấn ứng dụng đại diện.

Fresh install giúp phát hiện thiếu include, sai thứ tự, dependency và giả định sai về schema ban đầu.

### 6.2. Upgrade path

Upgrade test mô phỏng database đã chạy release trước:

1. Khởi tạo database từ snapshot hoặc changelog của release cũ.
2. Nạp dữ liệu legacy đại diện.
3. Chạy artifact mới.
4. Xác nhận changeset pending được thực thi đúng thứ tự.
5. Kiểm tra backfill, precondition và constraint.
6. Đối chiếu dữ liệu trước/sau.
7. Kiểm tra **DATABASECHANGELOG**, checksum và EXECTYPE.
8. Chạy smoke test với phiên bản ứng dụng dự kiến.

Dữ liệu test nên có NULL, duplicate, orphan, chuỗi Unicode, timestamp có timezone và giá trị số ở biên nếu những trường hợp đó liên quan tới migration.

### 6.3. Kiểm tra từ nhiều baseline được hỗ trợ

Nếu production có thể đang ở N-1 hoặc N-2, hãy kiểm tra các baseline đó theo chính sách hỗ trợ. Không cần tạo vô hạn tổ hợp; chọn các trạng thái có thể gặp thật và ghi rõ baseline nào đã được xác nhận.

## 7. Tạo database kiểm thử dùng đúng DBMS

Testcontainers hoặc database ephemeral có thể tạo môi trường lặp lại trong CI. Ví dụ PostgreSQL container cho một migration integration test:

```java
@Testcontainers
@SpringBootTest
class LiquibaseMigrationIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
```

Ví dụ là khung minh họa; cần dependency Testcontainers tương thích với Spring Boot/JUnit và pin image đúng major/minor hoặc digest được dự án chấp thuận. Nếu production có extension, collation hoặc cấu hình riêng, container tiêu chuẩn có thể chưa đủ.

### 7.1. Tách tài khoản migration và runtime

Tài khoản chạy migration thường cần quyền DDL và một số quyền DML. Tài khoản runtime của ứng dụng chỉ nên có quyền nghiệp vụ cần thiết. Pipeline có thể kiểm tra migration bằng tài khoản có quyền gần production và xác nhận app runtime không cần quyền DDL.

Không dùng tài khoản superuser trong test rồi kết luận production role cũng chạy được. Quyền thiếu thường chỉ lộ ra khi migration tạo schema, index, sequence hoặc function.

### 7.2. Kiểm tra lock và chạy đồng thời khi cần

Với hệ thống có nhiều replica hoặc nhiều pipeline có thể tác động cùng database, thêm bài test concurrency trong môi trường lab. Quan sát **DATABASECHANGELOGLOCK**, timeout và hành vi khi một process đang chạy migration. Liquibase lock không điều phối DBA/script ngoài Liquibase, nên vẫn cần quy tắc sở hữu migration.

## 8. Kiểm tra precondition và kết quả dữ liệu

Precondition là một phần của hợp đồng migration. Pipeline cần kiểm tra cả nhánh đạt và không đạt.

Ví dụ changeset thêm unique constraint sau khi kiểm tra duplicate:

```yaml
databaseChangeLog:
  - changeSet:
      id: DB-210-add-unique-email
      author: platform-team
      preConditions:
        - onFail: HALT
        - sqlCheck:
            expectedResult: "0"
            sql: |
              SELECT COUNT(*)
              FROM (
                SELECT email
                FROM customer_account
                WHERE email IS NOT NULL
                GROUP BY email
                HAVING COUNT(*) > 1
              ) duplicates
      changes:
        - addUniqueConstraint:
            tableName: customer_account
            columnNames: email
            constraintName: uq_customer_email
```

Pipeline nên có ít nhất hai tình huống:

- Dữ liệu hợp lệ: precondition đạt, changeset chạy và constraint tồn tại.
- Dữ liệu vi phạm: precondition HALT, migration dừng và pipeline báo lỗi; không đánh dấu release thành công.

Câu SQL precondition phải chạy được trên DBMS đích và phản ánh đúng semantics nghiệp vụ. Một truy vấn chạy trên H2 không đủ chứng minh kết quả giống production nếu khác biệt về NULL, collation hoặc kiểu dữ liệu.

### 8.1. Kiểm tra tác động của backfill

Nếu migration chuyển đổi dữ liệu, kiểm tra số dòng được cập nhật, số dòng còn thiếu, duplicate/orphan và invariant nghiệp vụ. Không chỉ xác nhận changeset có dòng trong **DATABASECHANGELOG**.

Với backfill lớn, kiểm tra batch size, thời gian, lock, khả năng resume và idempotency. Nếu pipeline test chỉ có vài dòng, cần thêm bài kiểm thử hiệu năng với dữ liệu gần thực tế.

## 9. Xem trước SQL trong pipeline

Sau khi changelog parse và migration test đạt, chạy **status --verbose** và **update-sql** với cấu hình của release.

Ví dụ:

```bash
liquibase validate
liquibase status --verbose
liquibase update-sql
```

SQL preview nên được lưu thành artifact của pipeline để reviewer có thể xem lại. Thông tin đi kèm nên gồm commit và artifact digest, root changelog, Liquibase version, DBMS/version và driver, database/schema đích (không chứa secret), context/label/parameters, thời điểm preview và tập changeset pending.

### 9.1. Review SQL theo rủi ro

Reviewer cần chú ý:

- DROP TABLE, DROP COLUMN, truncate hoặc thao tác xóa dữ liệu.
- ALTER TABLE có thể rewrite hoặc khóa bảng.
- Tạo index trên bảng lớn.
- Backfill toàn bảng và câu update không có điều kiện giới hạn.
- Thêm NOT NULL/unique/FK khi dữ liệu cũ chưa được kiểm tra.
- Thay đổi kiểu dữ liệu có thể mất dữ liệu hoặc overflow.
- Stored procedure/function có delimiter hoặc body phức tạp.
- SQL khác nhau theo DBMS, context hoặc label.
- Thứ tự statement và dependency giữa changeset.

Một SQL preview có thể dài. Hãy phân nhóm theo changeset và yêu cầu reviewer xác nhận các thay đổi có rủi ro cao, không chỉ xem dòng đầu và cuối.

### 9.2. SQL preview không dự đoán đầy đủ tác động runtime

Preview cho thấy câu lệnh dự kiến, nhưng không thể dự đoán chính xác thời gian khóa, execution plan, lượng log, dung lượng tạm hoặc tác động lên workload production. Với thay đổi lớn, cần chạy thử trên dữ liệu có quy mô đại diện và đánh giá cửa sổ triển khai.

## 10. Context, label, dbms và parameters phải nhất quán

Liquibase có thể lọc changeset theo context, label và DBMS. Pipeline preview và deploy phải dùng cùng bộ filter, nếu không SQL được review có thể khác SQL thực thi.

Ví dụ:

```yaml
databaseChangeLog:
  - changeSet:
      id: DB-220-seed-reference-data
      author: platform-team
      context: test
      changes:
        - insert:
            tableName: account_status
            columns:
              - column:
                  name: code
                  value: TEST
```

Nếu release production dùng context **production**, changeset **test** có thể không được chọn. Pipeline cần kiểm tra tập changeset được chọn cho từng môi trường, không chỉ một lần preview mặc định.

Parameters cũng có thể thay đổi schema, tên object hoặc dữ liệu. Giá trị preview phải tương ứng với giá trị deploy; không đưa secret vào SQL artifact hoặc log. Nếu parameter thay đổi theo môi trường, ghi nhận tên parameter và nguồn cấu hình mà không tiết lộ giá trị nhạy cảm.

### 10.1. dbms filter không thay thế kiểm thử từng engine

Nếu changelog có changeset **dbms: postgresql**, pipeline PostgreSQL phải xác nhận changeset được chọn. Pipeline H2 hoặc MySQL có thể bỏ qua changeset đó. Mỗi nhánh DBMS được hỗ trợ cần có test tương ứng và manifest chỉ rõ engine mục tiêu.

## 11. Xem trước rollback và đánh giá khả năng phục hồi

Với thay đổi có rollback, có thể dùng lệnh preview rollback phù hợp phiên bản Liquibase và chiến lược rollback của dự án, chẳng hạn **rollback-sql** với tag hoặc mốc được xác định. Cú pháp tham số cần theo CLI version đang dùng.

Rollback preview cần được review cùng update preview:

- Có rollback cho từng changeset không?
- Rollback có làm mất dữ liệu mới được ghi sau migration không?
- DDL của DBMS có thể rollback trong transaction không?
- Rollback có phụ thuộc object hoặc dữ liệu đã bị xóa không?
- Có cần restore backup/PITR hoặc forward fix thay vì rollback?
- App cũ có tương thích với schema sau rollback không?

Không phải mọi thay đổi đều đảo ngược hoàn toàn. Ví dụ drop column đã xóa dữ liệu thì rollback tạo lại cột rỗng không khôi phục giá trị cũ. Pipeline phải ghi rõ giới hạn và phương án phục hồi.

### 11.1. Kiểm thử rollback trên DBMS đích

Nếu rollback là phương án vận hành, chạy thử trên database disposable cùng DBMS và dữ liệu đại diện. Kiểm tra schema, dữ liệu, history và ứng dụng sau rollback. Không dùng H2 làm bằng chứng cho DDL rollback trên PostgreSQL/MySQL/Oracle/SQL Server.

## 12. Bảo vệ credentials và quyền trong pipeline

Pipeline cần kết nối database để đọc history, tạo SQL preview hoặc thực thi migration. Credentials phải được quản lý qua secret store/CI secret mechanism:

- Không commit password vào **liquibase.properties**, changelog hoặc manifest.
- Không in command line đã expand secret ra log.
- Hạn chế quyền đọc secret theo environment/job.
- Dùng tài khoản migration riêng với quyền cần thiết.
- Tách quyền migration khỏi quyền runtime khi phù hợp.
- Xoay vòng credentials và audit việc sử dụng.
- Không gửi SQL preview có literal nhạy cảm vào nơi công khai.

Ví dụ file cấu hình không chứa secret:

```properties
changeLogFile=db/changelog/db.changelog-master.yaml
driver=org.postgresql.Driver
defaultSchemaName=app
liquibaseSchemaName=app_metadata
```

URL/username/password được cung cấp bởi cơ chế bí mật của pipeline theo CLI/runtime version. Không giả định mọi cách inject environment variable có cùng cú pháp; kiểm tra cách Liquibase version của dự án bind property và bảo đảm giá trị không bị log.

### 12.1. Quyền theo từng stage

| Stage | Quyền phù hợp |
|---|---|
| Parse/lint | Không cần DB credentials |
| **validate** | Tùy kiểm tra/resource; không cấp quyền DDL |
| **status**/**update-sql** | Quyền kết nối và đọc metadata cần thiết |
| Migration integration test | Quyền DDL/DML trên DB test |
| Production preview | Quyền đọc history/metadata và kết nối theo chính sách |
| Production update | Tài khoản migration được phê duyệt, quyền cần thiết |
| Application runtime | Quyền nghiệp vụ tối thiểu, thường không cần DDL |

Quyền cụ thể phụ thuộc DBMS, schema và cách Liquibase tạo metadata. Hãy thử với role tương đương production để phát hiện thiếu quyền trước release.

## 13. Phân biệt pull request pipeline và release pipeline

Không phải mọi bước đều cần chạy với quyền production trong pull request.

### 13.1. Pull request

Pull request nên tập trung vào kiểm tra an toàn, tự động và có thể lặp lại:

- Parse/lint và **validate**.
- Kiểm tra thay đổi changeset cũ.
- Build artifact.
- Migration test trên DB ephemeral.
- Fresh install và upgrade path.
- **update-sql** trên database test với đúng filters.
- Lưu log và SQL preview để reviewer xem.

Pull request không nên có quyền ghi vào production. Dùng database thử nghiệm riêng cho mỗi run hoặc mỗi job để tránh hai pull request tác động cùng một schema.

### 13.2. Main/release pipeline

Release pipeline dùng artifact đã được kiểm tra:

1. Xác minh commit/digest và approval.
2. Kiểm tra database target, Liquibase version và filters.
3. Chạy **status --verbose**.
4. Sinh **update-sql** bằng đúng artifact/cấu hình.
5. So sánh preview với bản đã review nếu quy trình yêu cầu.
6. Kiểm tra backup/restore readiness và maintenance window.
7. Chạy migration với tài khoản được phê duyệt.
8. Hậu kiểm history/schema/data.
9. Chỉ sau đó cho phép rollout ứng dụng hoặc mở traffic theo chiến lược.

### 13.3. Một migration job cho nhiều replica

Với Spring Boot nhiều replica, cân nhắc chạy một migration job riêng trước rollout thay vì để mọi replica cùng chạy migration khi startup. Nếu runtime tắt **spring.liquibase.enabled**, pipeline phải bảo đảm migration job thành công trước khi ứng dụng mới được triển khai.

Liquibase lock hỗ trợ điều phối các process Liquibase cùng database, nhưng không thay thế orchestration, approval hoặc kiểm soát script ngoài Liquibase.

## 14. Quản lý artifact và kết quả kiểm tra

Mỗi pipeline run nên lưu những bằng chứng cần thiết để tái dựng quyết định release:

| Artifact | Nội dung |
|---|---|
| Changelog bundle | Root changelog và file include đã build |
| Build manifest | Commit, version, digest, Liquibase version |
| Validation report | Kết quả validate/lint và phiên bản công cụ |
| Migration test report | DBMS/version, baseline, dữ liệu test và kết quả |
| SQL preview | Update SQL, rollback SQL nếu có |
| Review record | Người review, quyết định và rủi ro |
| Deployment record | Environment, database target ID, thời gian và kết quả |
| Post-check report | History, schema/data assertions và readiness |

Không cần lưu credentials hoặc dữ liệu cá nhân trong artifact. Nếu SQL preview có literal dữ liệu nhạy cảm, cần kiểm tra và áp dụng chính sách bảo vệ trước khi lưu.

### 14.1. So sánh preview với SQL được triển khai

Nếu pipeline tạo preview ở stage A nhưng deploy ở stage B, cần bảo đảm hai stage dùng cùng changelog artifact, Liquibase version, DBMS/driver và cấu hình, root changelog, context/label/parameters, database history snapshot hoặc trạng thái target tương ứng.

Nếu database thay đổi giữa preview và deploy, tập pending có thể khác. Release job nên chạy lại preflight ngay trước update và yêu cầu review lại nếu SQL thay đổi đáng kể.

## 15. Xử lý pipeline thất bại theo từng giai đoạn

| Giai đoạn thất bại | Điều tra | Hành động |
|---|---|---|
| Lint/parse | File, line/column, encoding, cấu trúc | Sửa changelog rồi chạy lại |
| **validate** | Include, change type, property, Liquibase version | Sửa cấu trúc hoặc đồng bộ runtime |
| Build artifact | Resource bị thiếu, path/case sai | Sửa packaging và kiểm tra artifact |
| Migration test | SQL, precondition, constraint, permissions | Kiểm tra DBMS/data và sửa migration |
| **status**/preview | Sai URL, filters, metadata, identity | Xác minh target và cấu hình |
| SQL review | DDL nguy hiểm, thiếu rollback, thời gian dài | Thiết kế lại hoặc bổ sung phương án vận hành |
| Production update | Changeset lỗi, timeout, lock, partial apply | Dừng rollout, kiểm tra history và schema thật |
| Post-check | Schema/data/history không khớp | Giữ release ở trạng thái chưa hoàn tất, điều tra và phục hồi |

Nếu production update thất bại, không tự động retry mù quáng. Các changeset trước có thể đã commit; một số DDL có implicit commit hoặc changeset không chạy transaction. Hãy kiểm tra **DATABASECHANGELOG**, schema và dữ liệu trước khi chạy lại.

### 15.1. Giữ nguyên history

Không xóa record **DATABASECHANGELOG**, sửa **MD5SUM** hoặc đánh dấu changeset đã chạy chỉ để làm pipeline xanh. Nếu changeset chưa từng triển khai, có thể sửa trước release theo quy trình. Nếu đã chạy ở môi trường dùng chung, hãy giữ identity/nội dung lịch sử và tạo changeset mới để sửa kết quả.

### 15.2. Lock sau khi job bị dừng

Nếu pipeline bị hủy trong lúc Liquibase chạy, xác minh process/session còn hoạt động trước khi release lock. Chỉ dùng cơ chế **list-locks**/**release-locks** phù hợp phiên bản khi chắc chắn lock bị bỏ lại. Không cập nhật trực tiếp bảng lock bằng SQL theo phỏng đoán.

## 16. Ví dụ chuỗi kiểm tra bằng Liquibase CLI

Một chuỗi lệnh minh họa cho database test:

```bash
# 1. Validate cấu trúc changelog
liquibase validate

# 2. Xem changeset pending
liquibase status --verbose

# 3. Sinh SQL preview, không cập nhật database
liquibase update-sql

# 4. Chạy migration trên database test
liquibase update

# 5. Kiểm tra history sau khi chạy
liquibase history
```

Các lệnh phải được gọi với cùng defaults/config phù hợp cho từng stage. Ví dụ chỉ thể hiện thứ tự khái niệm; cách truyền URL, credentials, contexts, labels và properties cần theo Liquibase CLI version và CI runner của dự án.

Không chạy **update** trên production ở stage pull request. Lệnh update trong ví dụ chỉ dành cho database test hoặc migration job được phê duyệt.

### 16.1. Lưu output để review

Pipeline có thể chuyển stdout/stderr và SQL preview thành artifact, nhưng cần:

- Loại bỏ credentials và secret.
- Ghi rõ command/tool version.
- Ghi rõ DBMS và target environment.
- Gắn artifact với commit/digest.
- Đặt retention phù hợp.
- Không ghi dữ liệu production nhạy cảm vào log.

Nếu công cụ có thể ghi secret trong exception hoặc JDBC URL, hãy che giá trị trước khi lưu output.

## 17. Tích hợp với Spring Boot

Spring Boot thường chạy Liquibase khi application context khởi tạo nếu dependency và auto-configuration được bật.

Ví dụ:

```yaml
spring:
  liquibase:
    enabled: true
    change-log: classpath:/db/changelog/db.changelog-master.yaml
```

Có hai mô hình phổ biến:

**Application tự chạy migration khi startup:** đơn giản cho môi trường nhỏ hoặc một instance. Pipeline vẫn phải validate và test trước khi phát hành; startup failure phải chặn readiness.

**Migration job riêng:** pipeline chạy Liquibase trước, xác minh schema rồi mới rollout application replicas. Runtime có thể tắt auto-run Liquibase theo profile, nhưng deployment dependency phải bảo đảm migration job hoàn tất trước rollout.

Với cả hai mô hình, changelog trong artifact phải đúng phiên bản đã được kiểm tra. Không để pipeline preview một root changelog nhưng ứng dụng khởi động với root khác.

## 18. Thiết kế tiêu chí pass/fail rõ ràng

Một cổng CI cần có điều kiện thành công có thể kiểm chứng. Ví dụ:

| Cổng | PASS khi | FAIL khi |
|---|---|---|
| Format | Mọi file parse được | Parser/linter báo lỗi |
| Liquibase validation | **validate** exit 0 và log không có lỗi | Có lỗi validation/resource |
| Fresh install | Toàn bộ migration chạy và schema assertion đạt | Có changeset lỗi hoặc schema sai |
| Upgrade | Baseline cũ nâng cấp và data assertion đạt | Precondition/constraint/backfill fail |
| SQL preview | Preview sinh được, đúng tập changeset và đã lưu | Không sinh được hoặc target/filter sai |
| Review | Rủi ro và phương án phục hồi được chấp thuận | Còn thay đổi nguy hiểm chưa giải quyết |
| Deploy | Liquibase update hoàn tất theo release | Update lỗi hoặc trạng thái chưa rõ |
| Post-check | History/schema/data/readiness đạt | Bất kỳ invariant bắt buộc nào không đạt |

Không đặt tiêu chí chỉ dựa vào exit code nếu tool có thể trả warning hoặc skip changeset. Hãy kiểm tra output, tập changeset và các assertion quan trọng.

## 19. Checklist trước khi cho phép release

- [ ] Root changelog và toàn bộ include thuộc đúng artifact đã build.
- [ ] Changeset mới có ID/author/path ổn định; changeset đã triển khai không bị sửa tùy tiện.
- [ ] XML/YAML/JSON/formatted SQL đã qua parser/lint phù hợp.
- [ ] **liquibase validate** đạt trên đúng Liquibase version.
- [ ] Migration test chạy trên đúng DBMS production hoặc engine tương đương.
- [ ] Đã kiểm tra fresh install và upgrade từ baseline được hỗ trợ.
- [ ] Dữ liệu test bao gồm trường hợp biên liên quan precondition/backfill/constraint.
- [ ] **status --verbose** chạy với đúng database, context, label và parameters.
- [ ] **update-sql** được sinh từ đúng artifact và cấu hình release.
- [ ] SQL preview đã được review, nhất là DDL phá hủy, index và backfill lớn.
- [ ] Rollback preview/test hoặc phương án forward recovery đã được đánh giá.
- [ ] Credentials được lấy từ secret store và không xuất hiện trong log/artifact.
- [ ] Migration role có quyền cần thiết; runtime role có quyền tối thiểu.
- [ ] Có timeout, lock handling và kế hoạch xử lý partial apply.
- [ ] Preview và deploy dùng cùng artifact, filters, parameters và Liquibase version.
- [ ] Production preflight được chạy lại ngay trước update.
- [ ] Sau deploy đã đối chiếu DATABASECHANGELOG, schema, dữ liệu và ứng dụng.
- [ ] Chỉ rollout/mở traffic khi migration và hậu kiểm đạt.

## 20. Bài thực hành: xây dựng pipeline cho một release Liquibase

**Bối cảnh:** customer-service chuẩn bị thêm cột **status_code**, backfill dữ liệu cũ và tạo foreign key tới bảng **account_status**. Nhóm dùng PostgreSQL trong production và Spring Boot cho ứng dụng.

### Bước 1. Chuẩn bị changelog

Tạo changeset theo từng giai đoạn: thêm cột nullable, kiểm tra/nạp bảng tham chiếu, backfill, xác minh dữ liệu và thêm foreign key. Khai báo precondition để dừng nếu còn mã trạng thái không hợp lệ.

### Bước 2. Tạo pull request

Pipeline chạy parse/lint, Liquibase **validate**, kiểm tra resource và build migration artifact. Lưu commit SHA và digest để nhận diện đầu vào.

### Bước 3. Chạy migration integration

Khởi chạy PostgreSQL ephemeral cùng version phù hợp production. Chạy fresh install và upgrade từ baseline release trước. Kiểm tra schema, dữ liệu, precondition, constraint và **DATABASECHANGELOG**.

### Bước 4. Sinh SQL preview

Chạy **status --verbose** và **update-sql** với cùng root changelog, context, label và parameters dự kiến dùng khi release. Lưu SQL preview thành artifact review.

### Bước 5. Review và kiểm tra rollback

Reviewer xác nhận thứ tự changeset, DDL, backfill, lock, thời gian và khả năng rollback. Nếu không thể rollback an toàn, ghi rõ forward fix/backup/PITR plan.

### Bước 6. Phê duyệt release

Sau khi pull request được chấp thuận, phát hành artifact bất biến. Release job xác minh digest, target database, credentials, Liquibase version và filters.

### Bước 7. Preflight và deploy

Chạy lại **status --verbose** và **update-sql** trên target để phát hiện history đã thay đổi kể từ preview. Nếu tập SQL khác bản đã review, dừng và yêu cầu đánh giá lại. Khi được phép, chạy **update**.

### Bước 8. Hậu kiểm

Đối chiếu changeset identity/checksum trong **DATABASECHANGELOG**, xác nhận cột và foreign key tồn tại, kiểm tra không còn dữ liệu mồ côi, sau đó rollout ứng dụng và kiểm tra readiness/smoke test.

**Tiêu chí hoàn thành:** pipeline phân biệt được validation, kiểm thử thực thi và SQL preview; mọi stage dùng cùng artifact/cấu hình; migration được thử trên PostgreSQL; SQL có người review; production chỉ update sau preflight và hậu kiểm xác nhận trạng thái.

**Kết luận:** chuỗi CI/CD cho Liquibase cần nhiều lớp bằng chứng. **validate** kiểm tra changelog, migration integration chứng minh changeset hoạt động trên DBMS và dữ liệu đại diện, còn **status --verbose** cùng **update-sql** cho biết tập changeset pending và SQL dự kiến. Hãy dùng cùng một artifact bất biến, cùng filters/parameters và phiên bản Liquibase từ lúc kiểm thử đến lúc deploy; lưu preview để review, bảo vệ credentials, dừng rollout khi có lỗi và đối chiếu history/schema/data sau triển khai. Nhờ đó, migration trở thành một bước release có thể kiểm tra, giải thích và truy vết.

