# Xây dựng pipeline kiểm thử và triển khai migration

## 1. Mục tiêu và kết quả cần đạt

Trong dự án thực tế, việc viết được một changeset Liquibase chưa đủ để đưa thay đổi database vào production. Cần quy trình tự động phát hiện lỗi trước khi merge, thử migration trên database đại diện, xem SQL dự kiến, kiểm soát quyền và thứ tự triển khai, rồi xác minh trạng thái thật sau update. Nếu chỉ chạy lệnh từ máy developer, đội khó biết ai đã triển khai, dùng changelog nào, ở môi trường nào và database đang ở trạng thái nào sau lỗi.

Bài thực hành này xây dựng pipeline gồm **CI kiểm thử migration** trên PostgreSQL tạm và **CD triển khai migration** tới staging hoặc production có approval. Pipeline dùng cùng artifact/changelog nhưng tách credential và đích kết nối theo môi trường. Ví dụ sử dụng Liquibase CLI và GitHub Actions; nguyên tắc có thể áp dụng tương tự với GitLab CI, Jenkins hoặc công cụ điều phối khác.

Bài học thuộc chương **Thực hành** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Module hướng dẫn quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Trọng tâm ở đây là biến kiến thức đó thành một pipeline có thể kiểm chứng và vận hành.

Sau bài học, người đọc có thể:

1. Tổ chức changelog và các assertion phục vụ CI.
2. Chạy Liquibase trên PostgreSQL tạm, kiểm tra schema, lịch sử và khả năng không chạy lặp.
3. Sinh SQL preview và giải thích giới hạn của việc xem trước.
4. Tạo deployment job với environment secrets, kiểm tra database đích và approval.
5. Phối hợp schema migration với Spring Boot, rolling deployment và expand–contract.
6. Diễn tập thất bại, rollback/forward fix, ghi audit và chuẩn bị runbook.

**Phạm vi:** các file và lệnh trong bài là mẫu để học viên tự áp dụng vào repository. Không thực thi trên database production nếu chưa thay thế placeholder, khóa phiên bản, kiểm chứng quyền và phê duyệt theo quy trình tổ chức.

## 2. Sơ đồ quy trình

~~~text
Pull request
    |
    v
Lint / validate changelog
    |
    v
PostgreSQL tạm trong CI
    |
    v
Preview SQL + chạy update
    |
    v
Assert schema / data / DATABASECHANGELOG
    |
    v
Chạy update lần hai, kiểm tra idempotence
    |
  PASS
    |
    v
Review và merge
    |
    v
Plan migration trên staging
    |
    v
Approval + chạy staging + verify
    |
    v
Plan migration trên production
    |
    v
Review SQL / backup / compatibility
    |
    v
Approval + update production
    |
    v
Verify schema / data / history
    |
    v
Rollout app tương thích + smoke test
~~~

Cần phân biệt ba gate: **CI gate** chứng minh changelog hợp lệ và chạy được trên database test; **migration gate** chứng minh đúng target, quyền, artifact, SQL dự kiến và điều kiện chạy; **application gate** chứng minh ứng dụng mới tương thích và đủ sẵn sàng để phục vụ traffic. CI pass không đồng nghĩa production an toàn, vì production có dữ liệu cũ, tải đồng thời, lock, replication lag hoặc DBMS/version khác.

## 3. Điều kiện và cấu trúc repository

Môi trường lab cần Git, Docker trên runner Linux, một Liquibase CLI image có PostgreSQL JDBC driver, PostgreSQL để chạy test, và GitHub Actions. Với ứng dụng Spring Boot, cần thêm integration test dùng cùng schema.

Ví dụ cấu trúc:

~~~text
orders-service/
├── db/
│   └── changelog/
│       ├── db.changelog-master.yaml
│       └── changes/
│           ├── 001-create-orders.yaml
│           └── 002-add-order-status.yaml
├── src/
│   └── main/
│       └── resources/
│           └── application.yaml
└── .github/
    └── workflows/
        └── liquibase.yml
~~~

Trong ví dụ, changelog được lưu cùng repository ứng dụng để code và schema cùng được review theo commit. Với monorepo hoặc repository migration riêng, vẫn cần gắn changelog artifact với phiên bản ứng dụng được triển khai. Đường dẫn file Liquibase nằm trong định danh changeset theo mặc định, vì vậy không đổi tên/di chuyển changelog đã phát hành tùy tiện.

### 3.1. Phiên bản toolchain

Khóa Liquibase image, JDBC driver và PostgreSQL test image ở phiên bản đã kiểm chứng. Trong production nên pin image digest và action commit SHA, không dùng tag latest. Lệnh Docker ở ví dụ dùng host networking của runner Linux; nếu dùng Docker Desktop hoặc runner khác, thay bằng network service thích hợp. Không giả định image Liquibase bất kỳ đều có JDBC driver mong muốn.

## 4. Tạo changelog và hai changeset đầu tiên

File <code>db/changelog/db.changelog-master.yaml</code>:

~~~yaml
databaseChangeLog:
  - include:
      file: changes/001-create-orders.yaml
      relativeToChangelogFile: true
  - include:
      file: changes/002-add-order-status.yaml
      relativeToChangelogFile: true
~~~

File <code>db/changelog/changes/001-create-orders.yaml</code>:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-orders
      author: orders-team
      comment: Create initial orders table
      changes:
        - createTable:
            tableName: orders
            columns:
              - column:
                  name: id
                  type: BIGINT
                  autoIncrement: true
                  constraints:
                    primaryKey: true
                    primaryKeyName: pk_orders
                    nullable: false
              - column:
                  name: customer_ref
                  type: VARCHAR(64)
                  constraints:
                    nullable: false
              - column:
                  name: created_at
                  type: TIMESTAMP
                  defaultValueComputed: CURRENT_TIMESTAMP
                  constraints:
                    nullable: false
      rollback:
        - dropTable:
            tableName: orders
~~~

File <code>db/changelog/changes/002-add-order-status.yaml</code>:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 002-add-order-status
      author: orders-team
      comment: Add nullable status for compatible rollout
      preConditions:
        - onFail: HALT
        - onError: HALT
        - tableExists:
            tableName: orders
        - not:
            - columnExists:
                tableName: orders
                columnName: status_code
      changes:
        - addColumn:
            tableName: orders
            columns:
              - column:
                  name: status_code
                  type: VARCHAR(24)
      rollback:
        - dropColumn:
            tableName: orders
            columnName: status_code
~~~

Changeset 002 thêm cột nullable để ứng dụng cũ vẫn ghi được khi phiên bản mới đang rollout. Nếu áp NOT NULL ngay, writer cũ không gửi giá trị mới có thể lỗi. Constraint chặt hơn chỉ nên được thêm sau backfill và kiểm chứng toàn bộ writer.

### 4.1. Review changelog

| Thành phần | Cần kiểm tra |
|---|---|
| id, author và file path | Định danh changeset duy nhất, ổn định |
| include order | Bảng được tạo trước khi ALTER |
| preConditions | Dừng khi trạng thái database không như giả định |
| changes | DDL phù hợp DBMS và contract ứng dụng |
| rollback | Hướng đảo DDL có thực tế không; dữ liệu có thể mất |
| checksum | Phát hiện nội dung changeset lịch sử bị sửa |

Chỉ một thay đổi mới được thể hiện bằng changeset mới. Không sửa changeset đã chạy để ép Liquibase áp lại; điều đó làm checksum/historical state lệch giữa các môi trường.

## 5. Những lệnh Liquibase dùng trong pipeline

| Lệnh | Ý nghĩa | Giới hạn |
|---|---|---|
| <code>validate</code> | Kiểm tra cấu trúc changelog theo khả năng Liquibase | Không đo lock hay thực thi SQL |
| <code>status --verbose</code> | Liệt kê changeset pending trên target | Không xác nhận object vật lý chưa bị sửa thủ công |
| <code>update-sql</code> | Sinh SQL dự kiến | Không thực thi và không chứng minh an toàn production |
| <code>update</code> | Áp dụng changeset đủ điều kiện | Có thể fail giữa chừng tùy transaction/DBMS |
| <code>rollback-count-sql</code> | Xem trước SQL rollback số changeset chỉ định | Không phục hồi được mọi dữ liệu |
| <code>rollback-count</code> | Rollback một số changeset | Chỉ thử trước trên database bỏ đi được |

Tên command có thể khác ở một số phiên bản (ví dụ update-sql và updateSQL). Hãy khóa Liquibase version và kiểm tra CLI help của toolchain thực tế.

Khi CLI đã nhận URL, username và password an toàn qua environment:

~~~bash
liquibase --changelog-file=db/changelog/db.changelog-master.yaml validate
liquibase --changelog-file=db/changelog/db.changelog-master.yaml status --verbose
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update-sql
liquibase --changelog-file=db/changelog/db.changelog-master.yaml update
~~~

Không truyền password production trực tiếp trên command line; nó có thể xuất hiện trong shell history, process list hoặc CI logs. SQL preview có thể chứa literal nhạy cảm từ INSERT/UPDATE/SQL thuần, nên cần được bảo vệ.

## 6. Thiết kế tập kiểm thử CI

Một pipeline đủ giá trị không dừng ở parse được YAML. Nên kiểm tra:

1. **Static review:** tên file, id/author/path, include order, secret scanning.
2. **Validate:** Liquibase đọc và xác thực changelog.
3. **Preview:** SQL được sinh cho đúng DBMS/driver; review DDL phá hủy.
4. **Apply:** database tạm từ trạng thái sạch có thể nâng cấp bằng changelog.
5. **Assertion schema:** bảng, cột, khóa và constraint tồn tại đúng.
6. **Assertion history:** DATABASECHANGELOG ghi đúng changeset.
7. **Idempotence:** update lần hai không tạo lịch sử trùng.
8. **Integration:** ứng dụng có thể đọc/ghi với schema đã migrate.
9. **Negative test:** precondition hoặc SQL sai khiến job fail có kiểm soát.
10. **Rollback rehearsal:** chỉ trên database disposable; xem SQL và xác minh hậu quả.

Với hai changeset mẫu, kết quả mong đợi là bảng <code>public.orders</code> có cột status_code, hai bản ghi DATABASECHANGELOG đúng định danh, không có changeset pending và lock được giải phóng sau update. Chạy update lần hai phải giữ nguyên số changeset vì cả hai là changeset thông thường; runAlways/runOnChange có semantics khác.

Không dùng dump production chứa dữ liệu cá nhân làm test fixture. Nếu staging cần dữ liệu gần thực tế, phải masking dữ liệu và kiểm soát quyền/retention theo chính sách.

## 7. Tạo workflow GitHub Actions mẫu

Workflow sau minh họa **CI trên PostgreSQL ephemeral** và **deployment thủ công** tới environment được bảo vệ. Đây là cấu hình học tập cần hiệu chỉnh image digest, runner, private network, credentials và cơ chế review SQL trước khi dùng trên hệ thống thật.

~~~yaml
name: liquibase-migrations

on:
  pull_request:
    paths:
      - "db/**"
      - ".github/workflows/liquibase.yml"
  workflow_dispatch:
    inputs:
      target:
        description: Deployment environment
        required: true
        type: choice
        options:
          - staging
          - production

permissions:
  contents: read

env:
  LIQUIBASE_IMAGE: liquibase/liquibase:4.29.2
  CHANGELOG_FILE: db/changelog/db.changelog-master.yaml

jobs:
  migration-test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: lb_ci
          POSTGRES_USER: lb_ci
          POSTGRES_PASSWORD: ci_ephemeral_only
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U lb_ci -d lb_ci"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 10
    env:
      LIQUIBASE_COMMAND_URL: jdbc:postgresql://127.0.0.1:5432/lb_ci
      LIQUIBASE_COMMAND_USERNAME: lb_ci
      LIQUIBASE_COMMAND_PASSWORD: ci_ephemeral_only
      PGPASSWORD: ci_ephemeral_only
    steps:
      - uses: actions/checkout@v4

      - name: Validate, preview and test update
        shell: bash
        run: |
          set -euo pipefail
          run_lb() {
            docker run --rm --network host \
              -v "$GITHUB_WORKSPACE:/workspace:ro" \
              -w /workspace \
              -e LIQUIBASE_COMMAND_URL \
              -e LIQUIBASE_COMMAND_USERNAME \
              -e LIQUIBASE_COMMAND_PASSWORD \
              "$LIQUIBASE_IMAGE" \
              --changelog-file="$CHANGELOG_FILE" "$@"
          }

          run_lb validate
          run_lb status --verbose
          mkdir -p "$RUNNER_TEMP/liquibase-preview"
          chmod 700 "$RUNNER_TEMP/liquibase-preview"
          run_lb update-sql > "$RUNNER_TEMP/liquibase-preview/plan.sql"
          chmod 600 "$RUNNER_TEMP/liquibase-preview/plan.sql"

          run_lb update

          row_count() {
            docker run --rm --network host \
              -e PGPASSWORD postgres:16 \
              psql -h 127.0.0.1 -U lb_ci -d lb_ci \
              -tA -v ON_ERROR_STOP=1 -c \
              "SELECT COUNT(*) FROM public.databasechangelog"
          }
          before="$(row_count)"
          run_lb update
          after="$(row_count)"
          test "$before" = "2"
          test "$after" = "$before"

          column_count="$(docker run --rm --network host \
            -e PGPASSWORD postgres:16 \
            psql -h 127.0.0.1 -U lb_ci -d lb_ci \
            -tA -v ON_ERROR_STOP=1 -c \
            "SELECT COUNT(*) FROM information_schema.columns
             WHERE table_schema='public'
               AND table_name='orders'
               AND column_name='status_code'")"
          test "$column_count" = "1"

  deploy:
    if: github.event_name == 'workflow_dispatch'
    needs: migration-test
    runs-on: [self-hosted, linux, db-network]
    environment: ${{ inputs.target }}
    steps:
      - uses: actions/checkout@v4

      - name: Apply approved migration
        shell: bash
        env:
          DEPLOY_TARGET: ${{ inputs.target }}
          LIQUIBASE_COMMAND_URL: ${{ vars.DB_JDBC_URL }}
          LIQUIBASE_COMMAND_USERNAME: ${{ secrets.DB_MIGRATION_USERNAME }}
          LIQUIBASE_COMMAND_PASSWORD: ${{ secrets.DB_MIGRATION_PASSWORD }}
        run: |
          set -euo pipefail
          : "${LIQUIBASE_COMMAND_URL:?Missing JDBC URL}"
          : "${LIQUIBASE_COMMAND_USERNAME:?Missing DB username}"
          : "${LIQUIBASE_COMMAND_PASSWORD:?Missing DB secret}"

          case "$DEPLOY_TARGET:$LIQUIBASE_COMMAND_URL" in
            staging:jdbc:postgresql://staging-db.internal:5432/orders) ;;
            production:jdbc:postgresql://prod-db.internal:5432/orders) ;;
            *) echo "Unexpected database target"; exit 1 ;;
          esac

          run_lb() {
            docker run --rm --network host \
              -v "$GITHUB_WORKSPACE:/workspace:ro" \
              -w /workspace \
              -e LIQUIBASE_COMMAND_URL \
              -e LIQUIBASE_COMMAND_USERNAME \
              -e LIQUIBASE_COMMAND_PASSWORD \
              "$LIQUIBASE_IMAGE" \
              --changelog-file="$CHANGELOG_FILE" "$@"
          }
          run_lb validate
          run_lb status --verbose
          run_lb update
~~~

Ví dụ đặt mật khẩu <code>ci_ephemeral_only</code> duy nhất cho **database test bị hủy sau job**. Không dùng mật khẩu này cho staging hoặc production. Trong job deploy, secrets chỉ được inject vào bước chạy migration; job PR không nhận production credentials.

### 7.1. Những điều kiện phải cấu hình bên ngoài workflow

- Tạo protected environments <code>staging</code> và <code>production</code> trên GitHub, với allowed branches và required reviewers thích hợp.
- Khai báo environment variable DB_JDBC_URL và secrets DB_MIGRATION_USERNAME, DB_MIGRATION_PASSWORD cho từng môi trường.
- Provision self-hosted runner có label db-network và kết nối private tới database. Không mở cổng database ra Internet chỉ để chạy CI.
- Kiểm tra Docker có thể chạy trên runner, Liquibase image có JDBC driver PostgreSQL và lệnh CLI đúng phiên bản.
- Thay hostname mẫu staging-db.internal/prod-db.internal bằng target allowlist đã được phê duyệt. Giữ so khớp chặt chẽ, kể cả tham số TLS nếu URL có chúng.
- Pin image theo digest, action theo commit SHA đã review; tag trong bài chỉ là ví dụ dễ đọc.
- Bổ sung plan/review/approval riêng nếu tổ chức yêu cầu xem trước SQL trên chính database đích trước khi apply.

### 7.2. Vì sao Docker nhận biến bằng tên?

Các tùy chọn <code>-e LIQUIBASE_COMMAND_PASSWORD</code> lấy giá trị từ environment của job rồi đưa vào container, thay vì viết password literal vào command line. Điều này giảm rủi ro lộ qua command echo và process arguments, **nhưng không làm environment variable thành vùng lưu trữ hoàn toàn bí mật**. Runner, process diagnostics, crash dump và logs vẫn cần được bảo vệ. Kiểm tra tên biến Liquibase CLI đang hỗ trợ trên phiên bản đã khóa.

### 7.3. Tại sao lưu plan dưới RUNNER_TEMP?

SQL preview có thể chứa literal từ INSERT, UPDATE, loadData hoặc property substitution. Ví dụ lưu trong thư mục tạm được giới hạn quyền và không upload làm artifact công khai. Nếu review/audit cần lưu lại, dùng artifact store có encryption, access control, audit và retention. Không in toàn bộ SQL nhạy cảm lên console chỉ vì thao tác đó dễ thực hiện.

### 7.4. Cảnh báo về gate phê duyệt

Trong ví dụ, protected environment chặn **trước khi job deploy bắt đầu**. Workflow chưa tạo bước tách biệt để một reviewer xem production SQL preview rồi mới approve câu lệnh update. Với migration có rủi ro, thiết kế hai job hoặc hai workflow: plan-production sinh SQL từ đúng target, sau đó approval và apply-production. Không tuyên bố đã có một gate giữa preview và update nếu chúng chạy liền nhau trong một step.

## 8. Đọc kết quả kiểm thử của workflow

### 8.1. Validate và status

<code>validate</code> kiểm tra changelog theo khả năng Liquibase. <code>status --verbose</code> cho biết changeset còn pending trên database CI. Nếu không nhận đúng JDBC URL, cả hai có thể lỗi hoặc đọc sai history. Không dùng exit code của validate như bằng chứng database production có đúng trạng thái.

### 8.2. Preview và thực thi

<code>update-sql</code> sinh câu lệnh dự kiến; <code>update</code> mới thực hiện migration. SQL preview từ database CI sạch không đồng nghĩa preview trên production đã qua nhiều phiên bản hoặc có dữ liệu legacy. CI preview phục vụ kiểm thử; production preview phải gắn với target và snapshot trạng thái gần thời điểm thực thi.

### 8.3. Lịch sử changeset

Sau khi update thành công, kiểm tra:

~~~sql
SELECT id, author, filename, exectype, md5sum, orderexecuted
FROM public.databasechangelog
ORDER BY orderexecuted;
~~~

Trong bài lab, database có đúng hai changeset. <code>FILENAME</code> thuộc định danh changeset cùng id và author. <code>MD5SUM</code> là checksum Liquibase lưu để nhận biết changeset đã được chỉnh sửa theo quy tắc của công cụ. Không cập nhật tay DATABASECHANGELOG hoặc dùng clearCheckSums để che changeset bị sửa thiếu kiểm soát.

### 8.4. Tính không chạy lặp

Workflow chạy <code>update</code> hai lần rồi kiểm tra số bản ghi history trước/sau. Với hai changeset thông thường, số dòng giữ nguyên. Điều này khác với những changeset cố ý khai báo <code>runAlways</code> hoặc <code>runOnChange</code>; cần test riêng semantics của chúng.

Lệnh update chạy lại an toàn không có nghĩa mọi câu SQL thủ công đều idempotent. Nếu dùng SQL INSERT không được quản lý đúng changeset/history, dữ liệu vẫn có thể bị nhân đôi khi chạy lại.

### 8.5. Assertion cấu trúc sâu hơn

Đếm cột là kiểm tra tối thiểu. Nên kiểm tra type, nullability và constraint:

~~~sql
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'orders'
ORDER BY ordinal_position;
~~~

~~~sql
SELECT constraint_name, constraint_type
FROM information_schema.table_constraints
WHERE table_schema = 'public'
  AND table_name = 'orders';
~~~

Không kết luận migration thành công chỉ vì process exit 0. Xác minh những điều kiện schema và dữ liệu mà ứng dụng thực sự cần.

## 9. Tích hợp kiểm thử Spring Boot

Nếu ứng dụng dùng Spring JDBC, Spring Data JPA hoặc native SQL, CI nên chạy integration test trên schema đã được Liquibase tạo.

Quy trình:

1. Khởi động PostgreSQL tạm.
2. Chạy Liquibase từ changelog của release.
3. Khởi động Spring Boot test context với datasource đó.
4. Thử repository/API ghi và đọc bản ghi giả.
5. Xác nhận mapping entity, constraint và index cần thiết.
6. Thử cả đường ghi/đọc cũ và mới khi schema đang mở rộng.

Trong test mà CLI đã migrate database trước, có thể tắt Liquibase auto-run trong Spring Boot test profile:

~~~yaml
spring:
  liquibase:
    enabled: false
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Chỉ dùng cấu hình này khi schema đã được tạo bởi CLI hoặc bước chuẩn bị khác. Nếu tắt Liquibase trên database rỗng, ứng dụng sẽ thiếu bảng. Nên có một test độc lập bật Spring Boot auto-run để kiểm tra integration startup nếu production dự định dùng cách đó.

Tránh dùng Hibernate <code>ddl-auto=update</code> để tự tạo cột còn thiếu khi Liquibase là nguồn quản lý schema: test có thể xanh dù changelog thực chất chưa đầy đủ.

## 10. Kiểm thử tình huống lỗi

### 10.1. Changelog sai cú pháp

Trên nhánh lab, thử làm sai indentation YAML của **một changeset mới chưa triển khai**. Validate phải fail và deployment không được chạy. Sau thí nghiệm, khôi phục file. Không chỉnh changeset lịch sử trên nhánh đã phát hành.

### 10.2. Precondition không đạt

Tạo changeset thử nghiệm có <code>onFail: HALT</code> và điều kiện yêu cầu một bảng không tồn tại. Kết quả kỳ vọng:

- Update exit non-zero, thông báo đủ xác định nguyên nhân.
- Pipeline dừng, không tiếp tục deploy.
- Changeset thất bại không bị đánh dấu là thực thi thành công trong DATABASECHANGELOG.

Không chọn <code>MARK_RAN</code> chỉ để biến CI đỏ thành xanh khi database không đạt trạng thái kỳ vọng.

### 10.3. Job bị kill hoặc timeout

Chỉ thử trong database disposable. Sau khi cố ý ngắt tiến trình, kiểm tra history và object vật lý. DBMS có thể commit DDL một phần hoặc có transaction/implicit commit khác nhau; không suy luận từ exit code rằng mọi thứ đã rollback.

Kiểm tra DATABASECHANGELOGLOCK và session còn đang chạy. Không xóa bảng lock hoặc sửa trực tiếp flag locked trong production để bỏ qua timeout.

## 11. Tách môi trường, cấu hình và credential

Pipeline thường có nhiều loại môi trường:

| Môi trường | Database | Credential | Vai trò |
|---|---|---|---|
| CI ephemeral | Database tạo mới theo mỗi job | Test-only credential | Validate, apply và assert |
| Development | Database phát triển | Development identity | Kiểm thử thay đổi |
| Staging | Database gần production | Staging migration identity | Rehearsal và integration |
| Production | Database phục vụ thật | Production migration identity | Triển khai có kiểm soát |

Nguyên tắc:

- Mỗi environment có URL/target alias và secret riêng.
- Production credential chỉ được cấp cho job vào protected environment sau approval.
- Không cho pull request chưa được tin cậy đọc production secret.
- Runtime account và migration account nên tách nếu kiến trúc cho phép.
- Migration identity chỉ cần quyền DDL/DML và quyền metadata Liquibase trong phạm vi service, không mặc định superuser.
- Không lưu password trong changelog, Dockerfile, image, command line, debug log hay SQL preview.
- Nếu nền tảng hỗ trợ OIDC/workload identity, cân nhắc cấp credential ngắn hạn và đúng scope.

### 11.1. Kiểm tra database đích trước update

Không chỉ kiểm tra kết nối thành công. Ví dụ PostgreSQL:

~~~sql
SELECT current_database(), current_user, current_schema();
~~~

Đối chiếu với release manifest và allowlist. Nếu URL, database, principal hoặc schema không khớp kỳ vọng, dừng trước khi chạy DDL. Database name, hostname và schema cũng có thể là thông tin nội bộ nên cần phân loại đầu ra log phù hợp.

### 11.2. Không đưa secret vào image build

Image ứng dụng/Liquibase được promote giữa các môi trường; credential được cấp khi job chạy. Không build image có password staging rồi sử dụng image đó ở production. Artifact digest và changelog cần ổn định giữa plan/apply, còn secret được cấp theo identity của environment tương ứng.

### 11.3. Secret masking không đủ

CI secret masking thường che giá trị khi chúng xuất hiện đúng định dạng, nhưng có thể bỏ sót dữ liệu sau khi encode, chia chuỗi hoặc in qua exception. Vì vậy không echo secret, không chạy <code>env</code> hoặc <code>printenv</code>, không bật shell tracing quanh bước dùng secret, và không upload workspace chứa defaults file có credential.

## 12. Điều phối staging và production

Một release an toàn có thể đi qua các bước:

1. Merge commit đã pass CI và được review.
2. Chốt image digest, changelog root, Liquibase/JDBC driver version.
3. Chạy preflight staging: kết nối, database, schema, credential, quyền và history.
4. Sinh SQL preview từ trạng thái **staging hiện tại**, review và chạy staging update.
5. Verify schema, DATABASECHANGELOG, dữ liệu và ứng dụng staging.
6. Chạy smoke/integration test, kể cả đường đọc/ghi cũ nếu rolling deployment.
7. Sinh SQL preview production từ đúng artifact, target và parameters.
8. Review rủi ro lock, backfill, dữ liệu, backup và giới hạn dừng.
9. Nhận approval theo release/environment.
10. Chạy production update bằng artifact/cấu hình đã phê duyệt.
11. Verify và rollout ứng dụng tương thích, theo dõi metric.

### 12.1. Tạo gate giữa plan và apply

~~~text
plan-production
       |
       v
Verify target + generate SQL preview
       |
       v
Lưu plan trong artifact store hạn chế quyền
       |
       v
Review SQL, lock impact, backup và compatibility
       |
       v
Approval gắn với release + plan digest
       |
       v
apply-production
       |
       v
Recheck target + update
       |
       v
Verify history/schema/data + release report
~~~

GitHub protected environment kiểm soát quyền **trước khi job được chạy**. Để reviewer xem SQL sinh từ production trước khi phê duyệt update, phải tách plan và apply thành hai job hoặc workflow. Một job tạo preview rồi chạy update liên tiếp không tự có approval ở giữa, kể cả job đó bắt đầu sau một environment approval.

### 12.2. Runner production phải được cô lập

Database production thường nằm trên private network. Self-hosted runner cần được quản trị như một hệ thống có quyền cao:

- Không nhận mã pull request không tin cậy trên cùng runner có quyền database production.
- Giới hạn egress/network và quyền Docker/host.
- Vá lỗi, audit truy cập và bảo vệ filesystem tạm.
- Tách runner theo môi trường nếu rủi ro yêu cầu.
- Xóa file secret tạm sau job, không cache credential.

Không mở public database port chỉ để CI runner cloud kết nối dễ hơn.

### 12.3. Application gate sau migration

Chạy xong schema migration chưa có nghĩa app có thể nhận traffic. Đối với Spring Boot, kiểm tra startup/readiness, query, repository, API và tình trạng connection pool. Nếu migration job riêng chịu trách nhiệm DDL, runtime app thường tắt Liquibase auto-run để tránh mọi replica cùng khởi động migration.

## 13. Đảm bảo preview và update dùng cùng artifact

Một lỗi phổ biến là reviewer xem SQL từ commit A nhưng pipeline thực thi changelog từ commit B hoặc dùng context khác.

Lưu release manifest:

| Trường | Nội dung |
|---|---|
| Release id | Ví dụ orders-2026.11.19-1 |
| Git commit | Full commit SHA |
| Changelog | Đường dẫn master changelog |
| Artifact | Image digest chứa changelog và CLI |
| Toolchain | Liquibase version, JDBC driver, DBMS/version |
| Target | Environment và target alias |
| Schema | Default schema, Liquibase metadata schema |
| Filters | Context/label/parameters không bí mật |
| Plan | SQL preview URI hạn chế quyền và hash |
| Approval | Reviewer, thời điểm, change/release ticket |

Hash giúp phát hiện plan bị sửa sau review nhưng không chứng minh SQL an toàn, không chứa secret hoặc chắc chắn tương đương SQL sẽ chạy nếu database đổi trạng thái. Sau approval, cần preflight/status lại trước update để phát hiện drift hoặc writer/DBA thay đổi.

Nếu target, artifact, DBMS, parameters hoặc changelog thay đổi, quay lại bước review thay vì cố dùng approval cũ. Không chuyển nguyên văn JDBC URL chứa credential vào manifest.

### 13.1. Không sửa changeset đã triển khai

Liquibase ghi checksum trong DATABASECHANGELOG. Khi phát hiện mapping hoặc SQL cũ sai, tạo changeset sửa mới hoặc job dữ liệu có kiểm chứng. Việc sửa nội dung changeset lịch sử làm các môi trường có thể sinh checksum mismatch và khiến preview không còn phản ánh bản đã deploy.

### 13.2. Review SQL theo môi trường

SQL preview từ database sạch có thể khác SQL dự kiến khi production có object, context/label, DBMS/version hoặc changeset history khác. Với changeset dùng precondition và dữ liệu thực, preview càng cần được đánh giá trên trạng thái gần production.

## 14. Quan sát migration và lưu bằng chứng

Log nên đủ để điều tra:

- Service, release ID, environment/target alias.
- Changelog root, image digest và Liquibase version.
- Changeset id/author, trạng thái và thời lượng.
- Pending changesets trước update và kết quả sau update.
- Approval reference, verify result và incident reference khi có lỗi.

Không in password/token, full environment dump, datasource object hoặc toàn bộ SQL chứa literal dữ liệu nhạy cảm lên console có quyền truy cập rộng.

### 14.1. Metric cần theo dõi

| Nhóm | Chỉ số hữu ích |
|---|---|
| Liquibase | Migration duration, pending changesets, lock wait |
| Database | Blocked queries, deadlock, DDL lock duration |
| Tài nguyên | CPU, I/O, WAL/redo/binlog, storage |
| Replication | Lag và khả năng phục hồi replica |
| Ứng dụng | Error rate, timeout, p95/p99 latency, connection pool |
| Backfill | Batch throughput, checkpoint, số hàng còn lại, mismatch |

Ngưỡng pause/dừng triển khai phải được đặt trước theo SLO và dữ liệu đại diện. Một index nhỏ trên bảng lab không nói lên thời gian build index của bảng hàng trăm triệu dòng.

### 14.2. Phân biệt loại kết quả job

| Job outcome | Diễn giải | Bước tiếp theo |
|---|---|---|
| Exit 0 | CLI báo thành công | Vẫn verify schema, data, history và app contract |
| Exit non-zero | Có lỗi được phát hiện | Dừng release, kiểm tra trạng thái thật |
| Timeout/kill | Chưa biết transaction cuối có hoàn tất không | Không retry mù quáng; kiểm tra object và history |

Không đánh dấu deployment hoàn tất chỉ dựa vào HTTP 200 từ ứng dụng hoặc chỉ dựa vào Liquibase exit 0.

## 15. Rolling deployment và expand–contract

Trong rolling deployment, app V1 và V2 có thể chạy cùng lúc. Migration phải bảo vệ hợp đồng giữa schema và mọi writer/reader.

Ví dụ:

1. **Expand:** thêm cột <code>status_code</code> nullable; app V1 vẫn hoạt động.
2. **Deploy V2:** code dual-write, đọc fallback và metric so sánh.
3. **Backfill:** điền dữ liệu cũ theo batch có checkpoint, retry và throttle.
4. **Verify:** kiểm tra NULL/mismatch, xử lý giá trị ngoài mapping.
5. **Switch read:** bật đọc cột mới bằng feature flag/canary.
6. **Enforce:** thêm NOT NULL/CHECK sau khi mọi writer tuân thủ.
7. **Contract:** xóa cột cũ ở release sau khi hết pod/job/consumer phụ thuộc.

Nếu V1 còn ghi cột cũ trong khi backfill, cột mới có thể stale ngay sau khi batch đã đi qua. Cần drain writer cũ, bridge/trigger được kiểm thử hoặc reconciliation trước khi chuyển read path.

Liquibase lock phối hợp việc cập nhật history của Liquibase; nó không bảo đảm ứng dụng cũ ngừng đọc/ghi. Vì vậy, đừng đặt dropColumn hoặc constraint phá tương thích vào cùng release đầu chỉ vì SQL đã validate.

### 15.1. Startup migration hay job riêng?

Với local và thay đổi ngắn, Spring Boot auto-run có thể thuận tiện. Production có nhiều replica hoặc DDL dài thường nên cân nhắc job migration riêng để tách quyền DDL, approval và thời gian migration khỏi startup của từng pod.

Nếu job riêng chịu trách nhiệm migration, runtime application có thể cấu hình:

~~~yaml
spring:
  liquibase:
    enabled: false
~~~

Chỉ tắt auto-run khi pipeline đã có chủ thể cập nhật schema rõ ràng. Không tắt cả hai đường rồi deploy code mới cần object chưa được tạo.

## 16. Concurrency, lock và timeout

Liquibase dùng DATABASECHANGELOGLOCK để phối hợp các tiến trình dùng cùng history scope. Với nhiều runner/job:

- Một job có thể giữ lock; job khác chờ hoặc timeout.
- Lock không thay thế approval/leader selection của deployment.
- DDL ngoài Liquibase vẫn có thể xung đột.
- DBMS có thể có transaction/implicit commit khác nhau.
- Retry sau timeout phải dựa trên trạng thái vật lý và history, không chỉ exit code.

Nên có một migration owner rõ cho mỗi target và hạn chế job chạy đồng thời. Ví dụ ý tưởng về concurrency dành riêng production:

~~~yaml
concurrency:
  group: liquibase-production-orders
  cancel-in-progress: false
~~~

Trong workflow nhiều environment, group phải phân biệt target thực tế. Tránh <code>cancel-in-progress: true</code> nếu nó có thể ngắt migration DDL đang chạy giữa chừng.

### 16.1. Khi lock bị kẹt

1. Xác định process giữ lock còn thực thi không.
2. Đọc log và database session tương ứng.
3. Kiểm tra DDL đã thực thi tới đâu và object hiện tại.
4. Chỉ giải phóng lock khi có bằng chứng process cũ đã dừng, theo quy trình được phê duyệt.
5. Kiểm tra DATABASECHANGELOG trước retry.

Không xóa bảng lock hoặc sửa cờ locked thủ công chỉ để cho pipeline xanh.

## 17. Rollback, forward fix và recovery

Không tự động rollback toàn bộ database khi pipeline thất bại. Phải phân biệt lỗi trước update, trong update và sau update.

| Thời điểm | Trạng thái khả dĩ | Hướng xử lý |
|---|---|---|
| Validate/preview lỗi | Chưa có DDL do update | Sửa changelog/cấu hình, chạy lại CI |
| Sai target/credential | Chưa chạy hoặc đã kết nối nhầm | Dừng và kiểm tra audit/target thật |
| Update giữa chừng lỗi | Một số DDL/DML có thể đã commit | Đối chiếu object, history và transaction |
| Job timeout/kill | Không biết chắc câu cuối đã hoàn tất | Không retry mù quáng, xác minh trạng thái |
| Update thành công, verify lỗi | Schema đổi nhưng dữ liệu/app contract chưa đạt | Dừng rollout ứng dụng và điều tra |
| Rollout app lỗi sau migration | Database mới, app cũ có thể còn chạy | Rollback app nếu tương thích; cân nhắc giữ schema expand |

### 17.1. Diễn tập rollback trên database disposable

Với hai changeset mẫu, chỉ trên database lab có thể xóa và tạo lại:

1. Sinh hoặc kiểm tra SQL rollback của changeset cuối bằng command phù hợp Liquibase version.
2. Xác nhận rollback dự kiến sẽ xóa cột <code>status_code</code>.
3. Thử rollback một changeset.
4. Kiểm tra cột đã biến mất và lịch sử rollback được ghi nhận đúng.
5. Chạy lại update và xác minh cột được tạo lại.

Không xem thao tác dropColumn là rollback bảo toàn dữ liệu. Nếu có bản ghi đã điền status_code, xóa cột sẽ mất giá trị đó.

### 17.2. Forward fix thường phù hợp hơn

Khi một changeset đã biến đổi dữ liệu mất thông tin, hoặc DBMS không rollback DDL toàn phần, forward fix bằng changeset mới có thể an toàn hơn. Restore từ backup cần kế hoạch về khoảng thời gian mất dữ liệu và ứng dụng nào phải dừng ghi.

Tag Liquibase không phải snapshot database; rollback image ứng dụng không tự rollback schema. Kế hoạch phải xét đồng thời version ứng dụng, version schema và dữ liệu đã phát sinh.

### 17.3. Runbook khi migration fail

Một runbook thực tế cần ghi:

- Ai là incident owner và người có quyền quyết định retry.
- Cách tìm job, release id, target, changeset id và log.
- Query xác minh catalog, DATABASECHANGELOG và DATABASECHANGELOGLOCK.
- Kiểm tra transaction, DDL lock, replication lag và worker đang ghi.
- Điều kiện dừng rollout và rollback ứng dụng.
- Khi nào dùng forward fix hoặc restore.
- Cách lưu bằng chứng và báo cáo sau khắc phục.

Không sửa DATABASECHANGELOG thủ công để tạo cảm giác mọi thứ đã hoàn tất.

## 18. Mở rộng sang nhiều database và tenant

Nếu một release cập nhật nhiều database/tenant, cần trạng thái riêng theo đích:

~~~text
Release orders-v2
    |
    +--- Tenant A --> validate/update/verify --> PASS
    |
    +--- Tenant B --> validate/update/verify --> PASS
    |
    +--- Tenant C --> validate/update/verify --> FAIL
    |
    +--- Tenant D --> chưa chạy
~~~

Không đánh dấu toàn bộ release thành công khi tenant C/D chưa đạt. Pipeline cần:

- Registry/allowlist target tenant.
- Credential và schema scope đúng từng đích.
- History và lock phù hợp với đơn vị migration.
- Checkpoint, status, SQL preview và verify riêng từng database/tenant.
- Giới hạn concurrency để tránh tạo tải quá lớn.
- Resume từ đích thất bại mà không chạy lại mù quáng ở đích đã hoàn tất.
- Ứng dụng tương thích với tenant đã và chưa nâng cấp trong giai đoạn rollout.

Một DATABASECHANGELOG dùng chung có thể không phù hợp nếu nhiều schema tenant phải áp dụng cùng changeset độc lập; changeset đã ghi ở history chung có thể bị bỏ qua cho tenant khác. Thiết kế history scope trước khi scale pipeline.

### 18.1. Partial failure

Khi tenant C thất bại:

1. Ghi rõ C đang ở changeset nào và đã thay đổi object gì.
2. Kiểm tra DBMS transaction và trạng thái history riêng của C.
3. Không gộp tất cả tenant vào một cờ success/failure không có chi tiết.
4. Quyết định retry, pause toàn bộ hoặc forward fix theo contract ứng dụng.
5. Xác nhận A/B không cần và không bị chạy lặp ngoài mong muốn.

## 19. Lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ chạy validate | SQL thực tế hoặc constraint vẫn có thể lỗi | Apply trên DB tạm và assert |
| Test chỉ trên DB sạch | Không thấy dữ liệu legacy, lock và backfill lớn | Rehearsal staging có dữ liệu đại diện |
| Không kiểm tra history | Bỏ sót changeset hoặc nhầm target | Assert DATABASECHANGELOG và status |
| Không thử update lần hai | Chưa kiểm tra hành vi lặp | Idempotence test |
| Dùng image latest | Toolchain thay đổi giữa các run | Pin version/digest và driver |
| In SQL preview lên console công khai | Lộ literal và metadata | Artifact hạn chế quyền và retention |
| Cấp production secret cho job PR | PR không tin cậy có thể đọc credential | CI ephemeral và protected deployment |
| Không kiểm tra JDBC target | Migration chạy nhầm database | Allowlist, identity check và approval |
| Mở public DB port cho runner | Tăng bề mặt tấn công | Private runner/network |
| Preview artifact A nhưng update artifact B | SQL được review khác SQL thực thi | Gắn commit/digest và parameters |
| Deploy ứng dụng trước migration | App lỗi vì thiếu bảng/cột | Migration gate trước app rollout |
| Contract ngay khi deploy V2 | V1 đang chạy bị phá tương thích | Expand–migrate–contract nhiều release |
| Retry ngay sau timeout | Có thể object đã tạo một phần | Đối chiếu catalog/history trước retry |
| Sửa checksum/history thủ công | Che drift và khó phục hồi | Changeset mới và điều tra gốc lỗi |
| Tự rollback DDL phá hủy | Mất dữ liệu đã ghi sau migration | Review rollback hoặc forward fix |
| Không quan sát replication lag | DB/replica quá tải khi backfill | Throttle, metrics, stop criteria |
| Dùng migration user là superuser mọi DB | Tăng blast radius khi lộ credential | Least privilege, scope từng service |

## 20. Bài thực hành mở rộng

### Bài A — Validate failure

Trong nhánh lab, tạo changeset mới có YAML sai cấu trúc. Chạy CI, xác nhận validate fail và job deploy không được phép chạy. Khôi phục file rồi xác nhận CI pass.

### Bài B — Precondition failure

Tạo changeset thử có <code>onFail: HALT</code> yêu cầu một cột không tồn tại. Xác minh update dừng và không ghi changeset như đã thành công. Không dùng production để tạo lỗi.

### Bài C — Idempotence

Chạy update hai lần trên database sạch. So sánh history, object và checksum. Giải thích vì sao kết quả có thể khác với changeset runAlways/runOnChange.

### Bài D — Rollback rehearsal

Trên database disposable, xem rollback SQL, rollback changeset cuối rồi update lại. Xác minh cột, history và nguy cơ mất dữ liệu khi dropColumn.

### Bài E — Sai target

Đặt URL của database lab thứ hai nhưng giữ target alias không đúng. Preflight phải dừng trước update. Không cho phép fallback sang JDBC URL mặc định khi cấu hình bị thiếu.

### Bài F — Approval và secrets

Tạo staging environment thử nghiệm và production giả lập. Giới hạn production secret cho deployment job có required reviewers. Xác nhận PR không tin cậy không nhận credential này.

### Bài G — Rolling deployment

Thêm cột nullable, mô phỏng ứng dụng V1 và V2 cùng chạy. Thử dual-write, fallback và backfill, sau đó đặt constraint ở release riêng. Xác định release nào còn có thể rollback app cũ.

## 21. Checklist nghiệm thu pipeline

- [ ] Changelog root và include files được version control.
- [ ] Mỗi changeset có id/author/path ổn định.
- [ ] Liquibase CLI, JDBC driver và container image được khóa phiên bản.
- [ ] CI chạy PostgreSQL ephemeral, không dùng production secret.
- [ ] Validate và status chạy đúng target.
- [ ] SQL preview được tạo và bảo vệ quyền truy cập.
- [ ] Update trên DB tạm tạo schema đúng.
- [ ] Assertion kiểm tra bảng, cột, constraint và dữ liệu liên quan.
- [ ] DATABASECHANGELOG ghi đúng changeset và checksum.
- [ ] Update lần hai không chạy lặp changeset thông thường.
- [ ] Có integration test Spring Boot nếu thay đổi ảnh hưởng repository/API.
- [ ] Negative test và rollback rehearsal chạy trên database lab.
- [ ] Staging có secret riêng và kết quả verify.
- [ ] Production có allowlist target, environment approval và network phù hợp.
- [ ] Artifact preview/update là cùng commit/image digest và parameters.
- [ ] Có review SQL preview từ trạng thái database đích hiện tại.
- [ ] Runtime user và migration user được cấp quyền phù hợp.
- [ ] Không log password, token, full environment hoặc dữ liệu nhạy cảm.
- [ ] Không retry tự động khi trạng thái migration chưa rõ.
- [ ] Schema thay đổi tương thích trong rolling deployment.
- [ ] Có giám sát lock, replication lag, latency và error rate.
- [ ] Có runbook rollback app, forward fix và restore đã được diễn tập.
- [ ] Postflight xác minh schema, dữ liệu, history và smoke test.
- [ ] Có owner và bằng chứng release đủ để audit.

## 22. Kết luận

Một pipeline Liquibase đáng tin cần nhiều hơn một lệnh update. CI phải validate, tạo SQL preview, chạy migration trên database tạm, xác minh schema/history và kiểm tra tính không chạy lặp. CD phải kiểm tra đúng target, tách credential theo environment, review SQL cho database đích, nhận phê duyệt, áp dụng cùng artifact rồi kiểm chứng kết quả thật.

DATABASECHANGELOG và DATABASECHANGELOGLOCK giúp quản lý lịch sử và phối hợp các tiến trình Liquibase nhưng không thay thế kiểm thử dữ liệu, điều phối DDL ngoài Liquibase hoặc thiết kế tương thích ứng dụng. Với thay đổi phá hợp đồng, dùng expand–migrate–contract theo nhiều release; với migration lỗi, kiểm tra trạng thái vật lý trước khi retry, rollback hoặc forward fix. Kết hợp changelog, changeset, precondition, checksum, least privilege, audit và CI/CD gates giúp triển khai migration lặp lại được, quan sát được và an toàn hơn qua nhiều môi trường.
