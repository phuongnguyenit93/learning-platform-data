# Đưa thay đổi lược đồ cơ sở dữ liệu vào quy trình phiên bản

Lược đồ cơ sở dữ liệu thay đổi cùng với ứng dụng: thêm bảng, cột, chỉ mục, ràng buộc, view, stored procedure hoặc điều chỉnh kiểu dữ liệu. Nếu các thay đổi này chỉ được thực hiện thủ công trên từng môi trường, nhóm khó biết môi trường nào đang có cấu trúc gì, thay đổi được áp dụng khi nào và phiên bản ứng dụng nào cần cấu trúc đó.

Đưa thay đổi lược đồ vào hệ thống quản lý phiên bản nghĩa là lưu migration như mã nguồn, review cùng thay đổi ứng dụng, kiểm thử trong CI và áp dụng có kiểm soát qua các môi trường. Mỗi thay đổi có định danh, thứ tự, lịch sử thực thi và bằng chứng. Nhờ đó, database trở thành một phần của quy trình giao phần mềm thay vì một bước vận hành nằm ngoài pipeline.

## 1. Vì sao schema change cần được quản lý phiên bản?

Một thay đổi database có thể ảnh hưởng đến dữ liệu đang tồn tại, nhiều phiên bản ứng dụng và các dịch vụ cùng truy cập. Chạy một câu lệnh DDL trực tiếp trên production mà không có migration được quản lý sẽ tạo ra khoảng cách giữa cấu trúc thực tế và cấu trúc trong repository.

Quản lý migration trong Git mang lại các lợi ích:

- **Lịch sử:** biết thay đổi nào được thêm, ai review và vì sao.
- **Tái lập:** dựng database mới theo cùng một chuỗi migration.
- **Kiểm thử:** xác minh migration trên database tạm trước khi phát hành.
- **Truy vết:** liên kết schema version với commit, artifact và lần triển khai.
- **Kiểm soát:** review SQL, quyền thực thi, lock và tác động lên dữ liệu.
- **Khôi phục:** có thể lập kế hoạch roll-forward hoặc phục hồi theo chiến lược đã chuẩn bị.
- **Đồng bộ môi trường:** giảm khác biệt giữa development, test, staging và production.

Ví dụ, ứng dụng phiên bản 2.8 cần thêm cột `payment_method`. Nếu migration không nằm trong repository, một môi trường có thể đã được thêm cột thủ công, môi trường khác chưa có. Cùng một artifact khi triển khai sẽ có hành vi khác nhau tùy database.

## 2. Migration là gì và gồm những loại thay đổi nào?

Migration là một thay đổi database được mô tả bằng file hoặc changeset có định danh và thứ tự thực thi. Công cụ migration đọc các định nghĩa này, xác định thay đổi nào đã áp dụng và chạy phần còn thiếu.

Các loại thay đổi thường gặp:

| Loại | Ví dụ | Rủi ro cần xem xét |
|---|---|---|
| Schema DDL | CREATE TABLE, ALTER TABLE, DROP COLUMN | Lock, thời gian thực thi, tương thích ứng dụng |
| Index | CREATE INDEX, đổi index | Tải CPU/I/O, lock và thời gian build |
| Constraint | NOT NULL, UNIQUE, FOREIGN KEY | Dữ liệu hiện tại có vi phạm không |
| View/procedure | CREATE VIEW, function, trigger | Thay đổi hành vi truy vấn hoặc ghi dữ liệu |
| Data migration | Chuẩn hóa giá trị, backfill cột mới | Thời gian, tính idempotent và khả năng tiếp tục |
| Reference data | Danh mục trạng thái, loại giao dịch | Đồng bộ giữa môi trường và thay đổi theo phiên bản |
| Permission | GRANT/REVOKE | Phạm vi quyền và ảnh hưởng runtime |

Nên phân biệt schema migration với dữ liệu nghiệp vụ. Dữ liệu do người dùng tạo không phải thứ có thể tái tạo bằng cách chạy lại toàn bộ migration. Migration dữ liệu cần được thiết kế cẩn thận, có checkpoint, batch và cách xử lý khi chạy dở.

## 3. Lưu migration trong repository

Migration nên nằm trong một thư mục ổn định, gần cấu hình database hoặc module sở hữu schema. Ví dụ với dự án Java dùng Flyway:

~~~text
payments-service/
├── src/
│   └── main/
│       └── resources/
│           └── db/
│               └── migration/
│                   ├── V1__create_payment_table.sql
│                   ├── V2__add_payment_method.sql
│                   └── V3__add_payment_status_index.sql
├── src/test/
├── pom.xml
└── .github/
    └── workflows/
        └── ci.yml
~~~

Tên file cần tuân theo quy ước của công cụ. Với Flyway, versioned migration thường có dạng `V<version>__<description>.sql`. Số version xác định thứ tự; description giúp người đọc hiểu mục đích.

Một migration nhỏ nên thể hiện một thay đổi có ý nghĩa. Không nên gom nhiều thay đổi không liên quan vào một file lớn vì khó review và khó xác định phần gây lỗi. Ngược lại, cũng không cần tạo một migration riêng cho từng câu lệnh nếu chúng luôn cần được áp dụng cùng nhau.

Ví dụ:

~~~sql
-- V1__create_payment_table.sql
CREATE TABLE payment (
    id BIGINT PRIMARY KEY,
    amount DECIMAL(18, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

~~~sql
-- V2__add_payment_method.sql
ALTER TABLE payment
    ADD COLUMN payment_method VARCHAR(40);
~~~

Migration thứ hai thêm cột cho phép NULL để phiên bản ứng dụng cũ vẫn có thể tiếp tục ghi dữ liệu. Nếu thêm ngay NOT NULL mà không có default hoặc backfill phù hợp, thao tác có thể thất bại trên bảng đã có dữ liệu hoặc làm phát sinh lock/chi phí lớn.

## 4. Migration phải có version và thứ tự rõ ràng

Một database cần có một lịch sử migration có thứ tự xác định. Công cụ thường tạo một bảng metadata để lưu các migration đã chạy, ví dụ version, description, checksum, thời điểm và trạng thái thực thi.

Với Flyway, bảng lịch sử mặc định thường là `flyway_schema_history`. Với Liquibase, changelog history được ghi trong các bảng như `DATABASECHANGELOG` và `DATABASECHANGELOGLOCK`.

Các nguyên tắc quan trọng:

- Mỗi versioned migration có định danh duy nhất trong phạm vi schema/database mà công cụ quản lý.
- Version mới phải lớn hơn version đã áp dụng.
- Không sửa nội dung migration đã chạy trên môi trường dùng chung.
- Không tái sử dụng version đã tồn tại.
- Migration phụ thuộc nhau phải có thứ tự rõ.
- Commit chứa migration phải được review cùng thay đổi ứng dụng liên quan.

Nếu hai nhánh phát triển cùng tạo migration version `V12`, khi merge có thể xảy ra xung đột. Nhóm cần quy ước cấp version, kiểm tra trùng trước merge và tạo version tiếp theo cho migration được thêm sau. Không giải quyết bằng cách âm thầm đổi nội dung migration đã áp dụng ở môi trường khác.

## 5. Dùng công cụ migration thay vì chạy SQL thủ công

Có thể tự viết script SQL và lệnh triển khai, nhưng khi hệ thống có nhiều môi trường và nhiều lần phát hành, công cụ migration giúp quản lý lịch sử và thứ tự nhất quán.

Một số lựa chọn phổ biến:

| Công cụ | Cách mô tả migration | Điểm đáng chú ý |
|---|---|---|
| Flyway | SQL versioned/repeatable migration hoặc Java migration | Quy ước version, checksum và lịch sử rõ |
| Liquibase | Changelog XML, YAML, JSON hoặc SQL | Changeset có id, author, context và precondition |
| Rails Active Record Migrations | Migration Ruby | Gắn với hệ sinh thái Rails |
| Django migrations | File migration Python | Theo dõi phụ thuộc giữa app và migration |
| Alembic | Migration Python cho SQLAlchemy | Có revision và dependency graph |

Cần chọn một công cụ làm nguồn thực thi chính cho một schema. Không để Flyway và Liquibase cùng quản lý một tập thay đổi mà không có thiết kế phối hợp rõ ràng, vì hai lịch sử có thể không phản ánh cùng trạng thái.

### 5.1. Ví dụ Flyway

Với Flyway, một cấu trúc thường gặp:

~~~text
src/main/resources/db/migration/
├── V1__create_payment_table.sql
├── V2__add_payment_method.sql
├── V3__add_status_index.sql
└── R__refresh_payment_summary_view.sql
~~~

- Versioned migration bắt đầu bằng `V`, được chạy theo version và ghi nhận trong history.
- Repeatable migration bắt đầu bằng `R`, được chạy lại khi checksum thay đổi, thường dùng cho view hoặc procedure cần đồng bộ định nghĩa.
- Baseline được dùng trong một số trường hợp đưa Flyway vào database đã tồn tại; cần xác minh schema thực tế trước khi baseline.

Repeatable migration không nên được dùng thay cho mọi schema change. Các thay đổi cần lịch sử tuần tự và không được chạy lại tùy ý nên dùng versioned migration.

### 5.2. Ví dụ Liquibase

Một changeset Liquibase có thể khai báo định danh và thay đổi:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 20261118-01
      author: payments-team
      changes:
        - addColumn:
            tableName: payment
            columns:
              - column:
                  name: payment_method
                  type: varchar(40)
                  constraints:
                    nullable: true
~~~

Liquibase nhận diện changeset theo các trường định danh và lưu checksum. Không nên sửa changeset đã được áp dụng rồi kỳ vọng mọi môi trường tự đồng bộ. Khi cần thay đổi tiếp, tạo changeset mới; nếu cần điều chỉnh checksum vì lý do đặc biệt, phải hiểu rõ tác động và thực hiện theo quy trình được kiểm soát.

## 6. Không sửa migration đã được áp dụng

Migration đã chạy trên một môi trường dùng chung là một phần của lịch sử database. Nếu sửa file cũ, checksum có thể thay đổi và công cụ sẽ phát hiện lịch sử không còn khớp.

Ví dụ:

- `V1` đã tạo bảng payment trên development và staging.
- Nhóm phát hiện cần thêm cột `reference_code`.
- Không mở lại `V1` để thêm cột.
- Tạo `V2__add_reference_code.sql` để mô tả thay đổi mới.

Lợi ích của nguyên tắc này:

- Môi trường đã chạy và môi trường mới có cùng chuỗi lịch sử.
- Reviewer có thể đọc thay đổi phát sinh theo thời gian.
- Không tạo khác biệt âm thầm giữa các database.
- Dễ xác định migration nào đã gây ra thay đổi.

Nếu migration chưa từng được áp dụng ở bất kỳ môi trường chia sẻ nào và chưa được phát hành, nhóm có thể sửa trong nhánh làm việc trước khi merge theo quy trình review. Sau khi migration đã được áp dụng hoặc trở thành một phần của release, hãy coi nó là bất biến.

Không dùng lệnh repair hoặc chỉnh trực tiếp bảng history để che checksum mismatch mà chưa điều tra. Repair chỉ phù hợp trong tình huống được hiểu rõ, có backup và có phê duyệt; nó không thay thế việc khôi phục đúng lịch sử.

## 7. Kiểm thử migration trong CI

Migration cần được kiểm tra giống code. Một pipeline nên xác minh cả khả năng tạo database mới lẫn khả năng nâng cấp database có dữ liệu và schema cũ.

Các lớp kiểm tra thường gồm:

1. **Syntax/validation:** file SQL hoặc changelog hợp lệ.
2. **Fresh database test:** chạy toàn bộ migration từ database rỗng.
3. **Upgrade test:** dựng schema từ một phiên bản cũ rồi nâng cấp lên phiên bản mới.
4. **Data preservation test:** xác minh dữ liệu hiện tại được giữ và chuyển đổi đúng.
5. **Application compatibility test:** phiên bản ứng dụng dự kiến hoạt động với schema sau migration.
6. **Performance check:** ước lượng tác động của DDL hoặc backfill trên dữ liệu đủ lớn.
7. **Repeatability/consistency check:** kiểm tra migration history, checksum và trạng thái cuối.

Một database tạm có thể chạy trong container cho mỗi CI job. Ví dụ, test integration khởi động PostgreSQL, chạy Flyway và sau đó chạy test ứng dụng. Database test cần có phiên bản gần với production để tránh khác biệt cú pháp hoặc hành vi.

Không chỉ test từ database rỗng. Nhiều lỗi chỉ xuất hiện khi bảng đã có dữ liệu: thêm constraint, đổi kiểu, tạo unique index hoặc backfill có thể thất bại do dữ liệu cũ.

## 8. Ví dụ pipeline kiểm thử migration với Maven và PostgreSQL

Một quy trình Java có thể khởi động PostgreSQL service, cấu hình kết nối test và chạy Maven verify. Ví dụ GitHub Actions:

~~~yaml
name: Database migration CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify-migration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: app_test
          POSTGRES_USER: app
          POSTGRES_PASSWORD: test-only-password
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U app -d app_test"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Validate and run migration tests
        env:
          DB_URL: jdbc:postgresql://localhost:5432/app_test
          DB_USER: app
          DB_PASSWORD: test-only-password
        run: ./mvnw --batch-mode verify
~~~

Mật khẩu trong ví dụ chỉ dành cho database dùng một lần trong CI; không tái sử dụng ở môi trường khác. Trong dự án thực tế, cấu hình test nên được tách khỏi production config và không ghi credential thật vào repository.

Lệnh `verify` chỉ thực sự kiểm thử migration nếu dự án đã cấu hình Flyway/Liquibase và integration tests để chạy chúng. Pipeline cần có test xác nhận schema cuối, constraint, index quan trọng và hành vi ứng dụng; chỉ khởi động PostgreSQL không đủ chứng minh migration đúng.

## 9. Kiểm thử nâng cấp từ schema cũ và dữ liệu hiện có

Một migration có thể chạy tốt trên database rỗng nhưng thất bại khi nâng cấp production. Vì vậy, cần mô phỏng trạng thái trước migration.

Ví dụ thêm cột `normalized_email`:

~~~sql
ALTER TABLE customer
    ADD COLUMN normalized_email VARCHAR(320);
~~~

Sau đó backfill dữ liệu:

~~~sql
UPDATE customer
SET normalized_email = LOWER(TRIM(email))
WHERE normalized_email IS NULL;
~~~

Nếu bảng có hàng chục triệu bản ghi, một câu UPDATE duy nhất có thể tạo transaction lớn, tăng WAL/redo log, lock và replication lag. Khi đó, nên dùng job backfill theo batch với checkpoint, giới hạn tốc độ và khả năng tiếp tục sau lỗi.

Test upgrade nên có các trường hợp:

- Bảng rỗng.
- Bảng có dữ liệu bình thường.
- Giá trị NULL hoặc dữ liệu bất thường.
- Dữ liệu trùng khi thêm unique constraint.
- Bảng lớn hoặc mô phỏng tải đáng kể.
- Phiên bản ứng dụng cũ vẫn đang chạy trong rollout.
- Migration bị dừng giữa chừng hoặc được chạy lại theo cơ chế an toàn.

Không nên chỉ dùng vài dòng fixture rồi kết luận một migration sẽ an toàn trên bảng production lớn. Hãy ước lượng quy mô, index, lock và thời gian thực thi theo đặc điểm database thật.

## 10. Thiết kế migration tương thích với phiên bản ứng dụng

Trong triển khai rolling hoặc blue/green, phiên bản ứng dụng cũ và mới có thể cùng chạy trong một khoảng thời gian. Migration phải giữ schema tương thích với cả hai phiên bản trong giai đoạn chuyển tiếp.

Một thay đổi phá vỡ tương thích có thể khiến ứng dụng cũ lỗi ngay khi migration hoàn tất. Ví dụ, xóa cột mà phiên bản cũ vẫn đọc là không an toàn.

Mẫu **expand-and-contract** giúp giảm rủi ro:

1. **Expand:** thêm cột/bảng mới theo cách tương thích ngược.
2. Deploy code có thể đọc/ghi cấu trúc cũ và mới.
3. Backfill dữ liệu sang cấu trúc mới.
4. Chuyển ứng dụng sang sử dụng cấu trúc mới.
5. Xác minh không còn instance hoặc consumer dùng cấu trúc cũ.
6. **Contract:** xóa cột/bảng cũ trong một migration riêng sau khi hết nhu cầu rollback.

Ví dụ, đổi từ cột `full_name` sang `display_name`:

| Giai đoạn | Schema | Ứng dụng |
|---|---|---|
| Ban đầu | Có full_name | Code cũ đọc/ghi full_name |
| Expand | Thêm display_name | Code mới hỗ trợ cả hai |
| Backfill | Hai cột có dữ liệu | Job chuyển dữ liệu cũ sang mới |
| Cutover | Hai cột vẫn tồn tại | Code mới ưu tiên display_name |
| Contract | Xóa full_name | Chỉ sau khi mọi consumer đã chuyển đổi |

Không gộp expand và contract vào một lần deploy nếu cần giữ khả năng chạy song song. Việc giữ cấu trúc cũ trong một khoảng thời gian là chi phí có chủ đích để đổi lấy khả năng triển khai an toàn.

## 11. DDL có thể khóa bảng và gây gián đoạn

Không phải mọi câu lệnh ALTER TABLE đều có chi phí giống nhau. Hành vi phụ thuộc hệ quản trị cơ sở dữ liệu, phiên bản, kích thước bảng, index và loại thay đổi.

Các thao tác cần đánh giá kỹ:

- Thêm cột có default trên bảng lớn.
- Đổi kiểu dữ liệu hoặc collation.
- Thêm NOT NULL hoặc CHECK constraint.
- Tạo unique index trên bảng đang có dữ liệu.
- Xóa cột hoặc đổi tên cột đang được nhiều phiên bản ứng dụng dùng.
- Rebuild index hoặc thay đổi partition.
- Backfill hàng triệu bản ghi.

Một số hệ quản trị hỗ trợ thao tác online hoặc concurrent, nhưng cú pháp và giới hạn khác nhau. Ví dụ PostgreSQL hỗ trợ `CREATE INDEX CONCURRENTLY` với điều kiện riêng và không chạy trong transaction block thông thường; MySQL có các thuật toán và lock mode phụ thuộc loại DDL, engine và phiên bản. Cần đọc tài liệu đúng phiên bản database đang chạy và thử trên dữ liệu đại diện.

Trước khi áp dụng migration lớn, hãy xác định:

- Lock nào có thể được lấy và trong bao lâu.
- Có ảnh hưởng đến truy vấn/ghi đang chạy không.
- Dung lượng tạm và I/O cần thiết.
- Replication lag và tác động đến replica.
- Cửa sổ triển khai và timeout.
- Cách hủy hoặc tiếp tục khi thao tác kéo dài.

Không dùng một câu lệnh DDL có thể khóa bảng lâu trong giờ cao điểm nếu chưa có kế hoạch và bằng chứng về thời gian thực thi.

## 12. Quản lý migration dữ liệu theo batch và khả năng tiếp tục

Data migration khác với thay đổi schema đơn giản. Một backfill có thể chạy hàng giờ, xử lý hàng triệu bản ghi và bị gián đoạn bởi deploy, timeout hoặc sự cố hạ tầng.

Một job backfill tốt nên:

- Chia dữ liệu thành batch theo khóa ổn định.
- Ghi checkpoint hoặc watermark đã xử lý.
- Có thể chạy lại mà không tạo kết quả sai.
- Giới hạn tốc độ để không làm quá tải database.
- Có metric số bản ghi đã xử lý, lỗi và thời gian.
- Ghi nhận cách xử lý bản ghi lỗi.
- Cho phép dừng và tiếp tục an toàn.
- Có bước xác minh dữ liệu sau khi hoàn tất.

Ví dụ pseudocode:

~~~text
last_id = load_checkpoint()

while true:
    rows = fetch_next_batch(after_id=last_id, limit=1000)
    if rows is empty:
        break

    transformed = transform(rows)
    write_changes_idempotently(transformed)
    last_id = rows.last_id
    save_checkpoint(last_id)

verify_migration_totals()
~~~

Checkpoint cần được cập nhật nhất quán với thay đổi dữ liệu. Nếu lưu checkpoint trước khi transaction dữ liệu commit, job có thể bỏ qua bản ghi khi chạy lại. Nếu commit dữ liệu nhưng không lưu checkpoint, job có thể xử lý lại batch; vì vậy thao tác ghi cần idempotent.

Không nên đưa một backfill lớn vào startup path của ứng dụng. Nếu mọi instance cùng khởi động và chạy migration dữ liệu, chúng có thể tranh lock, tạo tải đột biến hoặc khiến rollout kéo dài. Hãy chạy data migration như một job có kiểm soát riêng.

## 13. Transaction, lock và tính idempotent

Migration nên có hành vi rõ khi chạy lỗi giữa chừng. Một số database hỗ trợ transaction cho nhiều thao tác DDL; một số thao tác hoặc hệ quản trị có implicit commit, khiến không thể rollback toàn bộ như mong đợi.

Cần phân biệt:

- **Transactional migration:** các thay đổi nằm trong transaction và có thể rollback nếu lỗi trước commit.
- **Non-transactional operation:** thao tác không thể chạy trong transaction hoặc có hành vi commit riêng.
- **Idempotent operation:** chạy lại không tạo thay đổi sai hoặc dữ liệu trùng.
- **Resumable operation:** có thể tiếp tục từ checkpoint sau khi dừng.

Không tự giả định DDL luôn transactional. Kiểm tra tài liệu database và cấu hình công cụ migration. Với thao tác không transactional, cần chia nhỏ bước, kiểm tra trạng thái trước/sau và chuẩn bị cách tiếp tục nếu lần chạy bị ngắt.

Migration versioned thường được thiết kế để chạy một lần theo history, không phải để người vận hành tùy ý chạy lại file SQL. Với script backfill hoặc vận hành cần retry, hãy thiết kế logic idempotent riêng, dùng khóa tự nhiên hoặc điều kiện cập nhật để tránh ghi trùng.

Công cụ migration cũng thường sử dụng lock để tránh hai pipeline cùng áp dụng migration trên một database. Không tắt cơ chế lock chỉ để hai lần deploy chạy song song. Cần có concurrency control ở pipeline và lock ở tầng database.

## 14. Quyền database cho migration và ứng dụng runtime

Tài khoản chạy migration thường cần quyền DDL cao hơn tài khoản runtime. Dùng chung một tài khoản quản trị database cho cả ứng dụng và pipeline làm tăng phạm vi ảnh hưởng khi ứng dụng bị xâm nhập.

Nên tách:

| Danh tính | Quyền thường cần |
|---|---|
| Migration job | DDL và DML cần cho migration trên schema được quản lý |
| Runtime application | Quyền đọc/ghi dữ liệu nghiệp vụ cần thiết |
| Read-only reporting | SELECT trên phạm vi dữ liệu được phép |
| Backup/restore operator | Quyền backup hoặc phục hồi theo nhiệm vụ |
| Developer local | Quyền trên database development, không phải production |

Credential migration chỉ được cấp cho job triển khai migration sau khi quality gate và approval đạt. Secret nên lấy từ secret manager qua workload identity, có scope theo môi trường và không lưu trong repository.

Không để ứng dụng runtime có quyền CREATE/DROP/ALTER nếu không cần. Nếu ứng dụng tự động chạy migration khi khởi động, mọi replica có thể cần quyền DDL; điều này làm tăng quyền runtime và khó kiểm soát thứ tự. Với production, thường nên có migration job riêng chạy trước hoặc theo orchestration có kiểm soát.

## 15. Trình tự đưa migration vào pipeline phát hành

Một pipeline tham khảo có thể đi theo trình tự:

~~~mermaid
flowchart TD
    A[Pull request chứa migration] --> B[Review SQL và schema impact]
    B --> C[Validate changelog và version]
    C --> D[Fresh database migration test]
    D --> E[Upgrade test từ schema cũ]
    E --> F[Application integration tests]
    F --> G[Build artifact và ghi provenance]
    G --> H[Deploy migration job]
    H --> I[Verify schema version và dữ liệu]
    I --> J[Deploy application]
    J --> K[Post-deploy verification]
~~~

Trình tự cụ thể phụ thuộc thay đổi và chiến lược tương thích. Với expand-and-contract, migration mở rộng có thể chạy trước ứng dụng mới; migration contract thường chạy sau khi tất cả consumer cũ đã được loại bỏ.

Các điểm kiểm soát:

- Migration thuộc commit đã review.
- CI chạy trên database cùng engine và phiên bản phù hợp.
- Có test upgrade, không chỉ fresh install.
- Pipeline lưu migration version và checksum.
- Job migration có identity và quyền riêng.
- Chỉ một pipeline thay đổi cùng database tại một thời điểm.
- Ứng dụng chỉ được triển khai khi schema đạt version yêu cầu.
- Sau deploy có kiểm tra trạng thái schema và ứng dụng.

Không nên để job deploy ứng dụng tự suy ra rằng migration đã chạy chỉ vì job migration được lên lịch. Cần kiểm tra kết quả thực tế và version trong migration history.

## 16. Rollback migration không giống rollback ứng dụng

Rollback database thường khó hơn rollback binary. Khi schema đã thay đổi và dữ liệu đã được ghi theo cấu trúc mới, việc chạy ngược DDL có thể làm mất dữ liệu hoặc không khôi phục được trạng thái ban đầu.

Có ba cách xử lý thường gặp:

- **Down migration:** script đảo ngược thay đổi khi thao tác thực sự có thể đảo ngược và dữ liệu chưa bị mất.
- **Roll-forward migration:** tạo migration mới sửa trạng thái sai hoặc bổ sung thay đổi cần thiết.
- **Backup/PITR restore:** phục hồi database về thời điểm trước sự cố khi cần, với kế hoạch xử lý dữ liệu phát sinh sau thời điểm đó.

Ví dụ thêm một cột nullable thường có thể xóa lại nếu chưa có dữ liệu cần giữ. Nhưng gộp hai cột, chuẩn hóa dữ liệu rồi xóa giá trị gốc có thể không đảo ngược được nếu không lưu bản sao.

Không nên coi down migration là bảo đảm rollback an toàn. Với production, cần xác định trước migration có thể đảo ngược hay không, dữ liệu nào có thể mất và điều kiện nào bắt buộc phải dùng roll-forward hoặc restore.

Trước migration rủi ro cao, cần backup hoặc xác nhận cơ chế point-in-time recovery hoạt động. Backup chỉ hữu ích khi đã kiểm tra khả năng restore, thời gian phục hồi và tác động đến giao dịch sau thời điểm backup.

## 17. Theo dõi schema drift giữa các môi trường

Schema drift là tình trạng cấu trúc database thực tế khác với cấu trúc được mong đợi từ lịch sử migration hoặc định nghĩa trong repository.

Nguyên nhân thường gặp:

- Người vận hành chạy SQL thủ công.
- Một môi trường bỏ lỡ migration.
- Migration bị đánh dấu applied nhưng thay đổi thực tế không hoàn chỉnh.
- Công cụ khác thay đổi object ngoài quy trình.
- Khác biệt cấu hình hoặc extension giữa môi trường.
- Restore database từ backup cũ mà không đồng bộ migration history.

Cần có cách phát hiện drift:

- So sánh schema thực tế với migration history.
- Dùng schema diff hoặc công cụ kiểm tra drift theo database engine.
- Kiểm tra migration version ở từng môi trường.
- Review thay đổi thủ công và ghi thành migration có kiểm soát.
- Cảnh báo khi production có object không được quản lý.

Migration history chỉ ghi công cụ đã chạy gì; nó không luôn chứng minh schema hiện tại vẫn đúng. Nếu ai đó sửa trực tiếp bảng sau migration, history có thể vẫn xanh trong khi cấu trúc đã drift.

Không tự động ghi đè schema production khi phát hiện drift. Trước tiên cần xác định thay đổi nào đã xảy ra, dữ liệu có bị ảnh hưởng không và migration nào sẽ đưa trạng thái về chuẩn.

## 18. Baseline cho database đã tồn tại

Khi đưa công cụ migration vào một hệ thống đã chạy nhiều năm, database có thể không bắt đầu từ schema rỗng. Nhóm cần xác định trạng thái hiện tại và tạo baseline có kiểm chứng.

Quy trình tham khảo:

1. Chọn database đại diện và thu thập schema hiện tại.
2. So sánh development, staging và production để phát hiện khác biệt.
3. Xác định phiên bản schema chuẩn mà các môi trường sẽ bắt đầu theo dõi.
4. Tạo baseline hoặc changelog ban đầu theo công cụ.
5. Kiểm tra baseline không vô tình chạy lại thao tác tạo/xóa dữ liệu hiện có.
6. Thử trên bản clone hoặc database staging được phục hồi từ backup.
7. Ghi nhận baseline version và checksum.
8. Từ thời điểm đó, mọi thay đổi mới phải đi qua migration được review.

Không tạo một migration lịch sử giả rồi chạy nó lên production nếu các object đã tồn tại, vì có thể gây lỗi hoặc thay đổi dữ liệu. Baseline là cách công cụ bắt đầu quản lý một trạng thái đã có; nó cần dựa trên bằng chứng schema thật.

## 19. Lưu bằng chứng và truy vết migration

Mỗi lần triển khai nên lưu:

- Migration version hoặc changeset ID.
- Checksum và trạng thái thực thi.
- Database engine và version.
- Target environment và database identity.
- Pipeline run ID, commit SHA và artifact digest.
- Thời điểm bắt đầu/kết thúc, thời lượng và kết quả.
- Người hoặc workflow yêu cầu.
- Approval record.
- Log và lỗi nếu migration thất bại.
- Schema version sau khi triển khai.

Không ghi password hoặc dữ liệu nhạy cảm trong migration log. Với migration dữ liệu, tránh log nội dung từng bản ghi; chỉ ghi số lượng, checkpoint và thống kê cần thiết.

Những thông tin này giúp trả lời database đã được nâng lên version nào, bằng release nào và ứng dụng nào được triển khai sau đó. Khi điều tra lỗi, có thể đối chiếu schema version với thời điểm phát sinh sự cố.

## 20. Checklist đưa schema change vào quản lý phiên bản

Trước khi merge migration hoặc triển khai lên môi trường dùng chung, hãy kiểm tra:

- [ ] Migration nằm trong repository và đúng thư mục quy ước.
- [ ] File có version/ID duy nhất và thứ tự xác định.
- [ ] Migration đã được review về dữ liệu, lock, index và tương thích.
- [ ] Migration đã áp dụng không bị sửa hoặc tái sử dụng version.
- [ ] Công cụ migration là nguồn thực thi chính cho schema.
- [ ] CI kiểm tra database mới từ trạng thái rỗng.
- [ ] CI kiểm tra nâng cấp từ schema cũ có dữ liệu đại diện.
- [ ] Có kiểm tra ứng dụng cũ/mới cùng tồn tại nếu dùng rolling deployment.
- [ ] Backfill lớn có batch, checkpoint, idempotency và giới hạn tốc độ.
- [ ] Đã đánh giá transaction, lock và hành vi DDL theo database engine.
- [ ] Migration job dùng credential riêng và quyền tối thiểu.
- [ ] Pipeline không chạy migration đồng thời trên cùng database.
- [ ] Có kế hoạch expand-and-contract khi thay đổi phá vỡ tương thích.
- [ ] Có chiến lược down migration, roll-forward hoặc restore phù hợp.
- [ ] Backup/PITR và khả năng restore đã được xác minh khi cần.
- [ ] Có kiểm tra schema drift và migration history.
- [ ] Deployment record lưu version, checksum, commit và run ID.

Khi schema change được lưu trong Git và thực thi qua pipeline, mỗi môi trường có thể được nâng cấp theo một lịch sử xác định. Migration được review, kiểm thử trên dữ liệu đại diện, áp dụng bằng danh tính riêng và gắn với artifact phát hành. Điều đó giúp thay đổi database trở thành một phần có thể kiểm soát và truy vết của quy trình CI/CD.

