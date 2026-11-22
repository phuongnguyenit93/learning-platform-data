# Tích hợp kiểm tra cơ sở dữ liệu vào CI và quản lý môi trường cô lập

Cơ sở dữ liệu là một phần của ứng dụng. Kiểm thử mã nguồn mà không kiểm tra cách ứng dụng làm việc với PostgreSQL sẽ bỏ sót nhiều lỗi: migration không chạy được, truy vấn sai kiểu dữ liệu, constraint từ chối dữ liệu, quyền truy cập không phù hợp hoặc hành vi giao dịch khác với giả định của ứng dụng. Tích hợp kiểm tra database vào quy trình tích hợp liên tục (CI) giúp phát hiện những lỗi này ngay khi thay đổi được gửi lên kho mã.

Để kết quả đáng tin cậy, mỗi lần chạy cần có một môi trường database có thể tạo mới, cấu hình được, có dữ liệu kiểm thử xác định và được hủy sau khi hoàn thành. Bài này trình bày cách tổ chức các tầng kiểm thử PostgreSQL trong CI, tạo môi trường cô lập, chạy migration, chuẩn bị dữ liệu, hỗ trợ chạy song song và thu thập thông tin khi kiểm thử thất bại.

## 1. Vì sao cần kiểm tra PostgreSQL trong CI?

Kiểm thử đơn vị thường xác minh logic của một hàm hoặc thành phần riêng lẻ. Chúng nhanh và dễ chạy, nhưng không thay thế được kiểm thử trên PostgreSQL thật. Nhiều hành vi chỉ xuất hiện khi truy vấn được thực thi trên database:

- Kiểu dữ liệu, phép ép kiểu, NULL, collation và múi giờ có thể tạo ra kết quả khác với giả định của mã ứng dụng.
- Constraint, foreign key, unique index, trigger và default có thể từ chối hoặc biến đổi dữ liệu.
- Migration có thể lỗi khi áp dụng lên schema thực tế hoặc khi nâng cấp từ phiên bản trước.
- Vai trò database và quyền trên schema, table, sequence hoặc function có thể khác quyền của tài khoản quản trị.
- Giao dịch, khóa, mức cô lập và truy vấn đồng thời có thể bộc lộ lỗi mà unit test không mô phỏng được.
- Extension hoặc tính năng theo phiên bản PostgreSQL có thể không tồn tại trong môi trường của một số thành viên.

CI tạo một lần chạy kiểm thử có thể lặp lại trên mỗi pull request hoặc commit. Khi thay đổi làm hỏng migration, câu SQL, constraint hoặc luồng ghi đọc dữ liệu, pipeline phát hiện trước khi thay đổi được đưa vào nhánh chính.

Một pipeline tốt cần xác định rõ database được tạo từ cấu hình nào, kiểm thử chạy trên trạng thái schema nào và dữ liệu nào được dùng. Nếu không xác định được các yếu tố này, một bài kiểm thử thành công có thể chỉ là kết quả tình cờ của dữ liệu hoặc trạng thái database còn sót lại.

## 2. Các tầng kiểm thử có thể chạy trong CI

Không phải mọi thay đổi đều cần chạy một bộ kiểm thử tích hợp lớn. Có thể chia kiểm thử theo phạm vi và chi phí để pipeline phản hồi nhanh trong khi vẫn kiểm tra được hành vi quan trọng.

### 2.1. Kiểm thử migration

Tạo database trống rồi áp dụng toàn bộ migration từ đầu. Cách này xác minh một môi trường mới có thể được tạo đúng từ lịch sử migration trong repository.

Ngoài đường đi từ database trống, nên kiểm tra nâng cấp từ schema phiên bản trước. Ví dụ, tạo database bằng migration đến phiên bản N, nạp dữ liệu đại diện, rồi áp dụng migration N+1. Điều này phát hiện lỗi chỉ xuất hiện khi bảng đã có dữ liệu, chẳng hạn thêm cột NOT NULL mà không có default hoặc thay đổi kiểu dữ liệu không tương thích.

### 2.2. Kiểm thử truy vấn và repository

Chạy truy vấn thực tế trên PostgreSQL để kiểm tra kết quả đọc ghi, lọc, sắp xếp, phân trang, join, aggregate và xử lý NULL. Nên dùng dữ liệu nhỏ nhưng có chủ đích: bản ghi ở biên thời gian, giá trị trùng, quan hệ thiếu, chuỗi rỗng, giá trị NULL và trường hợp có thể vi phạm constraint.

Những kiểm thử này xác minh cả SQL lẫn ánh xạ dữ liệu giữa ứng dụng và database. Chúng cũng phát hiện khác biệt giữa cú pháp hoặc hành vi PostgreSQL và database giả lập trong unit test.

### 2.3. Kiểm thử constraint và transaction

Tạo các thao tác ghi có chủ đích để xác minh unique constraint, foreign key, check constraint, trigger và hành vi rollback. Ví dụ, khi ghi một đơn hàng cùng các dòng chi tiết, nếu một dòng không hợp lệ thì transaction cần rollback để không để lại đơn hàng dở dang.

Với luồng có nhiều kết nối hoặc xử lý đồng thời, cần kiểm tra trên các kết nối PostgreSQL riêng. Một kiểm thử chỉ dùng một connection không mô phỏng đầy đủ tranh chấp khóa giữa các transaction.

### 2.4. Kiểm thử tích hợp và smoke test

Kiểm thử tích hợp khởi chạy ứng dụng hoặc thành phần liên quan, kết nối đến database đã được chuẩn bị và thực hiện một luồng nghiệp vụ tiêu biểu. Smoke test có phạm vi nhỏ hơn: xác nhận ứng dụng kết nối được, đọc cấu hình cần thiết và thực hiện một truy vấn cơ bản.

Các bài kiểm thử này chạy sau khi database sẵn sàng và migration đã hoàn thành. Chúng cung cấp bằng chứng rằng ứng dụng, cấu hình kết nối, quyền và schema có thể làm việc cùng nhau.

### 2.5. Kiểm thử hiệu năng có giới hạn

Có thể đưa một số truy vấn trọng yếu vào CI để phát hiện thay đổi bất thường về kế hoạch hoặc thời gian. Tuy nhiên, CI dùng máy chia sẻ thường có tải và tài nguyên biến động. Nên dùng ngưỡng rộng để phát hiện hồi quy lớn, lưu EXPLAIN khi cần và dành benchmark chính xác cho môi trường có tài nguyên ổn định.

## 3. Thiết kế môi trường database cô lập

**Môi trường cô lập** là môi trường kiểm thử có trạng thái dữ liệu và schema độc lập với các lần chạy khác. Một job không nên phụ thuộc vào dữ liệu do job trước tạo ra và cũng không được làm thay đổi database dùng chung của nhóm hoặc môi trường production.

Có một số mức cô lập phổ biến. Lựa chọn phụ thuộc vào thời gian khởi tạo, tài nguyên CI, khả năng chạy song song và mức độ giống môi trường triển khai.

### 3.1. Một PostgreSQL container cho mỗi job

CI khởi chạy một PostgreSQL container riêng cho mỗi job. Khi job kết thúc, container bị hủy và dữ liệu trong container biến mất nếu không gắn volume lưu trữ lâu dài.

Ưu điểm:

- Mỗi job có một instance riêng, dễ tái tạo và dọn dẹp.
- Có thể ghim phiên bản PostgreSQL và cấu hình khởi động.
- Extension, locale và tham số server có thể được chuẩn bị nhất quán.
- Nhiều job có thể chạy song song mà không dùng chung dữ liệu.

Nhược điểm là khởi động container và cài extension có chi phí thời gian. Nếu một bộ kiểm thử gồm nhiều nhóm chạy song song trong cùng job, cần tạo database hoặc schema riêng cho từng nhóm để tránh va chạm.

Đây thường là lựa chọn tốt cho integration test vì môi trường gần với một PostgreSQL server thực tế và có thể được tạo mới ở mỗi lần chạy.

### 3.2. Một database riêng cho mỗi pipeline hoặc worker

Một PostgreSQL instance có thể phục vụ nhiều lần kiểm thử, nhưng mỗi pipeline hoặc worker được cấp một database riêng. Ví dụ, **app_ci_1042** dành cho pipeline 1042 và **app_ci_1043** dành cho pipeline 1043.

Cách này tiết kiệm thời gian khởi tạo server, nhưng cần kiểm soát vòng đời database. Pipeline tạo database trước khi chạy, kết nối đúng database và xóa database khi kết thúc. Việc xóa có thể thất bại nếu vẫn còn kết nối đang mở, do đó cần đóng connection pool trước khi dọn dẹp.

Database riêng cũng giúp kiểm thử các thao tác phụ thuộc vào schema hoặc extension ở cấp database. Cần nhớ một số extension phải được cài riêng trong từng database.

### 3.3. Một schema riêng cho mỗi worker

Có thể dùng một database chung và tạo schema riêng như **ci_1042_worker_1**, **ci_1042_worker_2**. Mỗi worker đặt search_path để truy cập schema của mình.

Cách này nhẹ hơn việc tạo nhiều PostgreSQL instance hoặc database. Tuy nhiên, mọi truy vấn và migration phải thực sự dùng đúng schema. Những đối tượng được tham chiếu bằng tên schema cố định, extension ở cấp database hoặc truy vấn bỏ qua search_path có thể phá vỡ sự cô lập.

Không nên chỉ dựa vào schema riêng nếu ứng dụng dùng nhiều schema, tạo đối tượng không qualify tên hoặc có migration thay đổi đối tượng dùng chung. Cần kiểm tra cách ứng dụng chọn schema trong connection.

### 3.4. Transaction rollback cho từng test

Một số bộ kiểm thử bắt đầu transaction trước mỗi test và rollback sau test. Cách này nhanh vì không phải tạo lại toàn bộ database cho mỗi trường hợp.

Tuy nhiên, rollback chỉ dọn được thay đổi thuộc transaction đó và trên kết nối tương ứng. Nếu mã kiểm thử mở connection thứ hai, chạy công việc bất đồng bộ hoặc commit ở transaction khác, thay đổi có thể còn lại. Một số thao tác quản trị database cũng không thể thực hiện bên trong transaction.

Transaction rollback phù hợp cho test đồng bộ, kiểm soát được connection. Với kiểm thử nhiều kết nối hoặc kiểm thử cần tạo database/schema, nên dùng database hoặc schema riêng, hoặc chiến lược dọn dữ liệu khác.

### 3.5. So sánh các mức cô lập

| Cách cô lập | Mức độc lập | Chi phí khởi tạo | Điểm cần chú ý |
|---|---|---|---|
| Container riêng cho mỗi job | Cao, cả instance và dữ liệu | Trung bình | Thời gian khởi động và tải tài nguyên |
| Database riêng trên một instance | Cao ở mức database | Thấp đến trung bình | Quyền tạo/xóa database và kết nối còn mở |
| Schema riêng cho mỗi worker | Trung bình | Thấp | search_path, đối tượng dùng chung và migration |
| Transaction rollback | Phụ thuộc connection/transaction | Rất thấp | Không bao phủ thay đổi đã commit hoặc connection khác |

Nếu CI chạy nhiều job độc lập, container riêng thường dễ hiểu và an toàn nhất. Nếu cần giảm thời gian khởi tạo, database riêng trên một instance có thể là lựa chọn cân bằng. Schema riêng và transaction rollback phù hợp khi bộ kiểm thử được thiết kế để tuân thủ ranh giới cô lập đó.

## 4. Tạo PostgreSQL container có thể tái lập

Docker Compose là cách thuận tiện để tạo PostgreSQL cục bộ hoặc trong job CI. File sau định nghĩa một database phục vụ kiểm thử:

~~~yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: app_test
      POSTGRES_USER: app_test_user
      POSTGRES_PASSWORD: ci_only_password
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app_test_user -d app_test"]
      interval: 2s
      timeout: 3s
      retries: 20
    tmpfs:
      - /var/lib/postgresql/data
~~~

Trong ví dụ này, tmpfs đặt dữ liệu PostgreSQL trên vùng lưu trữ tạm của container. Khi container bị hủy, dữ liệu cũng bị hủy. Nếu môi trường CI không hỗ trợ tmpfs hoặc cần dùng volume thông thường, vẫn có thể dùng container dùng một lần và xóa volume sau job.

Khởi chạy database:

~~~bash
docker compose up -d postgres
~~~

Kiểm tra trạng thái:

~~~bash
docker compose ps
docker compose exec postgres pg_isready -U app_test_user -d app_test
~~~

Khi hoàn tất:

~~~bash
docker compose down -v
~~~

Lệnh cuối xóa container và volume do Compose quản lý cho project đó. Chỉ dùng trong môi trường kiểm thử được tạo riêng; không chạy với project Compose đang chứa dữ liệu cần giữ.

### 4.1. Health check và readiness

Container ở trạng thái running chưa có nghĩa PostgreSQL đã sẵn sàng nhận truy vấn. PostgreSQL cần thời gian khởi tạo cluster, đọc cấu hình và bắt đầu chấp nhận kết nối.

**pg_isready** kiểm tra server có chấp nhận kết nối hay không. Health check trong Compose cho phép service phụ thuộc chờ database đạt trạng thái healthy.

Tuy vậy, pg_isready không xác minh migration đã chạy, extension đã có hoặc tài khoản ứng dụng có đủ quyền. Pipeline cần bước riêng để chạy migration và có thể thực hiện truy vấn smoke test sau đó.

### 4.2. Ghim phiên bản và cấu hình

Không nên dùng tag **latest** cho image database trong CI. Hãy chọn phiên bản PostgreSQL cụ thể, chẳng hạn **postgres:16**, và cập nhật có chủ đích khi dự án nâng phiên bản. Nếu cần tính tái lập nghiêm ngặt hơn, có thể ghim image digest.

Ngoài phiên bản, cần thống nhất các yếu tố ảnh hưởng kết quả:

- Extension và phiên bản extension được cài.
- Encoding, locale, collation và timezone.
- Các tham số server cần thiết cho ứng dụng.
- Quyền và vai trò được tạo.
- Script khởi tạo và migration được chạy.

Nếu production dùng extension như pgcrypto, uuid-ossp, PostGIS hoặc extension nội bộ, môi trường CI cần cài đúng extension tương ứng. Image PostgreSQL cơ bản không nhất thiết chứa mọi extension mà ứng dụng sử dụng.

## 5. Tổ chức bước kiểm tra database trong pipeline

Một pipeline có thể chia thành các bước:

1. Lấy mã nguồn và cài công cụ cần thiết.
2. Khởi chạy PostgreSQL hoặc cấp database cô lập.
3. Chờ database sẵn sàng.
4. Tạo role và cấu hình cần thiết cho ứng dụng.
5. Chạy migration.
6. Nạp fixture hoặc dữ liệu kiểm thử.
7. Chạy kiểm thử truy vấn, repository và tích hợp.
8. Thu thập log nếu có lỗi.
9. Đóng connection và hủy môi trường tạm.

Thứ tự này tránh tình trạng ứng dụng bắt đầu kiểm thử khi database chưa sẵn sàng hoặc schema chưa đúng phiên bản.

### 5.1. Ví dụ GitHub Actions với PostgreSQL service

Ví dụ sau minh họa một job CI có PostgreSQL service. Tên lệnh migration và test cần thay bằng script thật của repository:

~~~yaml
name: database-tests

on:
  pull_request:
  push:
    branches: [main]

jobs:
  integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: app_test
          POSTGRES_USER: ci_admin
          POSTGRES_PASSWORD: ci_admin_password
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U ci_admin -d app_test"
          --health-interval 2s
          --health-timeout 3s
          --health-retries 20

    env:
      PGHOST: 127.0.0.1
      PGPORT: 5432
      PGDATABASE: app_test
      PGUSER: ci_admin
      PGPASSWORD: ci_admin_password

    steps:
      - uses: actions/checkout@v4

      - name: Wait for PostgreSQL
        run: |
          for attempt in $(seq 1 30); do
            if pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE"; then
              exit 0
            fi
            sleep 2
          done
          echo "PostgreSQL did not become ready"
          exit 1

      - name: Apply migrations
        run: ./scripts/migrate-test.sh

      - name: Run database integration tests
        run: ./scripts/test-database.sh
~~~

Trong GitHub Actions, service container được cấp cho job và có thể truy cập qua port được ánh xạ. Nếu job cũng chạy bên trong container, hostname và port có thể khác; hãy dùng hostname service theo cấu hình workflow thay vì mặc định 127.0.0.1.

Các giá trị mật khẩu trong ví dụ chỉ dành cho database tạm của CI. Với dịch vụ dùng chung hoặc tài nguyên bên ngoài, lấy secret từ kho secrets của CI và cấp quyền tối thiểu cần thiết. Không ghi mật khẩu thật vào repository hoặc log.

### 5.2. Tạo role ứng dụng với quyền tối thiểu

Có thể dùng một role quản trị riêng để tạo schema và chạy migration, sau đó dùng role ứng dụng với quyền cần thiết để chạy integration test. Cách này phát hiện ứng dụng vô tình dựa vào quyền superuser.

Ví dụ minh họa tạo role ứng dụng:

~~~sql
CREATE ROLE app_runtime LOGIN PASSWORD 'runtime_test_password';

GRANT CONNECT ON DATABASE app_test TO app_runtime;
GRANT USAGE ON SCHEMA public TO app_runtime;

GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA public
TO app_runtime;

GRANT USAGE, SELECT, UPDATE
ON ALL SEQUENCES IN SCHEMA public
TO app_runtime;
~~~

Các grant trên chỉ áp dụng cho đối tượng hiện có. Để quyền được cấp tự động cho table và sequence tạo sau này, cấu hình default privileges bằng role sở hữu các đối tượng:

~~~sql
ALTER DEFAULT PRIVILEGES FOR ROLE migration_owner
IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_runtime;

ALTER DEFAULT PRIVILEGES FOR ROLE migration_owner
IN SCHEMA public
GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO app_runtime;
~~~

Nếu ứng dụng cần gọi function hoặc dùng schema khác, cần cấp thêm đúng quyền tương ứng. Không nên cấp superuser cho role runtime chỉ để làm cho test chạy qua.

## 6. Chạy và kiểm soát database migration

Migration biến đổi schema theo từng phiên bản. CI nên dùng chính công cụ và quy trình migration mà dự án sử dụng khi triển khai, để kiểm tra đúng đường đi của schema.

Một quy trình phổ biến gồm tạo database trống, chạy toàn bộ migration theo thứ tự, kiểm tra schema, chạy test trên schema mới, sau đó tạo database ở phiên bản trước với dữ liệu đại diện và chạy migration nâng cấp.

Ví dụ dùng psql để chạy một file SQL migration:

~~~bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/001_create_schema.sql
~~~

Tùy chọn ON_ERROR_STOP khiến psql dừng khi gặp lỗi SQL, nhờ đó job thất bại thay vì tiếp tục với schema dở dang. Nếu dự án dùng Flyway, Liquibase hoặc công cụ migration khác, hãy gọi lệnh migration chính thức của công cụ đó.

### 6.1. Kiểm tra database mới và database nâng cấp

Hai đường đi này phát hiện hai nhóm lỗi khác nhau:

- **Fresh install:** kiểm tra toàn bộ lịch sử migration có thể tạo database mới từ đầu.
- **Upgrade path:** kiểm tra migration mới có thể biến đổi schema và dữ liệu đã tồn tại.

Ví dụ, migration thêm cột status NOT NULL có thể chạy được trên bảng trống nhưng thất bại khi bảng đã có hàng. Cần có chiến lược thêm cột, gán giá trị cho dữ liệu hiện tại rồi mới áp dụng NOT NULL.

Một số thay đổi lớn cần nhiều giai đoạn để tương thích với phiên bản ứng dụng đang chạy: thêm cột mới, ghi song song hoặc backfill, chuyển ứng dụng sang cột mới, rồi mới loại bỏ cột cũ trong một lần triển khai sau. CI có thể kiểm tra từng bước để tránh migration phá vỡ ứng dụng đang hoạt động.

### 6.2. Migration phải có thứ tự và cơ chế khóa

Không nên để nhiều job cùng chạy migration trên một database dùng chung. Hai tiến trình có thể cùng cố tạo một đối tượng hoặc cập nhật bảng lịch sử migration, dẫn đến lỗi hoặc trạng thái không nhất quán.

Dùng database riêng cho mỗi job là cách tránh xung đột đơn giản. Nếu dùng database dùng chung, công cụ migration cần cơ chế khóa hoặc bảng lịch sử để chỉ một tiến trình thay đổi schema tại một thời điểm. Không tự chạy lại migration đã thành công bằng cách bỏ qua lịch sử.

### 6.3. Migration không chạy trong transaction

Nhiều câu lệnh DDL PostgreSQL có thể chạy trong transaction, nhưng một số thao tác không thể chạy trong transaction block, ví dụ **CREATE INDEX CONCURRENTLY**. Công cụ migration cần hỗ trợ đánh dấu migration không transactional hoặc chạy riêng theo cách phù hợp.

CI cần thực thi migration bằng đúng công cụ triển khai để phát hiện giới hạn này. Nếu tự bọc mọi migration trong một transaction trong script kiểm thử, kết quả có thể khác với môi trường triển khai.

### 6.4. Xử lý lỗi migration

Khi migration thất bại, lưu log đầy đủ, tên migration, SQLSTATE và trạng thái database. Nếu migration được chạy trong transaction và rollback thành công, có thể sửa migration rồi chạy lại trên database mới. Nếu migration gồm thao tác ngoài transaction hoặc đã commit một phần, cần tạo lại môi trường kiểm thử và xác minh trạng thái trước khi chạy tiếp.

Không sửa trực tiếp schema bằng tay để làm cho test xanh. Mọi thay đổi cần được biểu diễn trong migration để môi trường khác có thể tái tạo cùng kết quả.

## 7. Quản lý dữ liệu kiểm thử

Môi trường cô lập chỉ giải quyết việc các lần chạy không ảnh hưởng nhau. Dữ liệu kiểm thử vẫn cần được chuẩn bị rõ ràng và lặp lại được.

### 7.1. Fixture và seed data

Fixture là tập dữ liệu cố định được nạp trước test. Seed data thường tạo những bản ghi nền mà nhiều test cần dùng. Có thể lưu fixture dưới dạng SQL, CSV, JSON hoặc tạo bằng factory trong mã kiểm thử.

Dữ liệu nên nhỏ, dễ hiểu và phục vụ một tình huống cụ thể. Ví dụ, để kiểm tra đơn hàng, tạo một khách hàng có hai đơn hàng, một đơn đã thanh toán và một đơn đang chờ. Test kiểm tra tổng tiền, trạng thái và quan hệ mà không phụ thuộc dữ liệu do test khác tạo ra.

Tránh dùng dữ liệu production thật. Nếu cần dữ liệu có cấu trúc giống thực tế, hãy tạo dữ liệu tổng hợp hoặc dùng dữ liệu đã được khử định danh theo quy trình được phê duyệt. Không đưa thông tin cá nhân hoặc credential vào fixture trong repository.

### 7.2. Dữ liệu phải xác định được kết quả

Một test đáng tin cậy cần biết chính xác dữ liệu đầu vào và kết quả kỳ vọng. Tránh phụ thuộc vào thứ tự hàng nếu truy vấn không có ORDER BY. Tránh dùng thời gian hiện tại trực tiếp nếu test cần kết quả cố định; truyền thời điểm rõ ràng hoặc cố định clock của ứng dụng.

Ví dụ:

~~~sql
INSERT INTO customers (customer_id, name)
VALUES
  (101, 'An'),
  (102, 'Binh');

INSERT INTO orders (order_id, customer_id, total, status)
VALUES
  (1001, 101, 150.00, 'paid'),
  (1002, 101, 50.00, 'pending'),
  (1003, 102, 75.00, 'paid');
~~~

Truy vấn tổng hợp doanh thu đã thanh toán:

~~~sql
SELECT customer_id, sum(total) AS paid_total
FROM orders
WHERE status = 'paid'
GROUP BY customer_id
ORDER BY customer_id;
~~~

Kết quả kỳ vọng là khách hàng 101 có 150.00 và khách hàng 102 có 75.00. Vì dữ liệu được tạo ngay trong môi trường kiểm thử, test không phụ thuộc trạng thái từ lần chạy trước.

### 7.3. Dọn dữ liệu sau test

Có nhiều cách dọn dữ liệu:

- Rollback transaction nếu mọi thay đổi nằm trong cùng transaction và cùng connection.
- Xóa các hàng đã tạo theo khóa định danh riêng của test.
- TRUNCATE các bảng trong schema test trước khi nạp fixture.
- Hủy database hoặc schema sau khi worker hoàn tất.

Ví dụ:

~~~sql
TRUNCATE TABLE orders, customers RESTART IDENTITY CASCADE;
~~~

CASCADE có thể tác động đến bảng tham chiếu các bảng được chỉ định, vì vậy chỉ dùng trong schema hoặc database kiểm thử riêng. RESTART IDENTITY đặt lại sequence thuộc các bảng bị truncate. Nếu không cần reset sequence, có thể bỏ tùy chọn này.

Hãy thiết kế dọn dữ liệu sao cho một test thất bại giữa chừng cũng không làm hỏng lần chạy tiếp theo. Với container hoặc database dùng một lần, hủy toàn bộ môi trường sau job thường đơn giản và đáng tin cậy.

## 8. Chạy kiểm thử song song mà không va chạm

CI thường chạy nhiều job hoặc nhiều test worker đồng thời để rút ngắn thời gian. Nếu tất cả cùng dùng một schema và cùng tên fixture, chúng có thể xóa hoặc sửa dữ liệu của nhau.

Có một số cách phân vùng:

- **Database theo pipeline:** mỗi pipeline nhận một database riêng.
- **Schema theo worker:** mỗi worker có schema và search_path riêng.
- **Tên dữ liệu riêng:** mọi bản ghi do test tạo có namespace hoặc mã định danh duy nhất.
- **Container theo job:** mỗi job có PostgreSQL instance riêng.

Ví dụ, tạo schema theo pipeline và worker:

~~~sql
CREATE SCHEMA ci_1042_worker_3;
~~~

Kết nối worker vào schema:

~~~sql
SET search_path TO ci_1042_worker_3, public;
~~~

Cần đảm bảo ứng dụng mở connection với đúng search_path và migration được chạy trong schema tương ứng. Nếu test dùng tên schema cố định như public.orders, search_path không thể cô lập truy vấn đó.

Không nên để hai worker cùng chạy migration hoặc cùng TRUNCATE một bảng dùng chung. Khi parallel test cần dữ liệu nền lớn, có thể tạo database template đã migrate rồi clone thành database riêng cho từng worker nếu hạ tầng và quyền cho phép. Cần tính cả chi phí dung lượng và thời gian tạo bản sao.

## 9. Dùng Testcontainers để tạo PostgreSQL theo vòng đời test

Với dự án Java, Testcontainers có thể khởi chạy PostgreSQL container ngay trong bộ kiểm thử. Test lấy JDBC URL, username và password từ container đang chạy, sau đó khởi tạo migration và kết nối ứng dụng vào database đó.

Ví dụ với JUnit và Testcontainers:

~~~java
@Testcontainers
class OrderRepositoryIT {
    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16")
            .withDatabaseName("app_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @BeforeAll
    static void configureDatabase() {
        System.setProperty("test.jdbc.url", postgres.getJdbcUrl());
        System.setProperty("test.jdbc.user", postgres.getUsername());
        System.setProperty("test.jdbc.password", postgres.getPassword());
    }

    @Test
    void readsOrdersFromPostgres() {
        // Apply migrations, insert fixture, and run assertions.
    }
}
~~~

Đây là ví dụ rút gọn để minh họa vòng đời container; dự án cần khai báo dependency Testcontainers tương thích, cấu hình JUnit integration và kết nối các giá trị trên với data source thực tế. Trong ứng dụng Spring hoặc framework khác, có thể dùng cơ chế dynamic property tương ứng thay vì system property.

Container có thể được chia sẻ cho cả test class hoặc cả suite để giảm thời gian khởi động. Nếu các test chạy song song và thay đổi cùng dữ liệu, hãy cấp database/schema riêng cho mỗi worker hoặc tắt song song cho nhóm test dùng chung trạng thái.

Lợi ích lớn của Testcontainers là test chạy trên PostgreSQL thực tế với phiên bản được khai báo. Điều này giảm khác biệt giữa máy lập trình viên và CI, đặc biệt với SQL đặc thù PostgreSQL, extension, index, transaction và kiểu dữ liệu.

## 10. Thu thập log và chẩn đoán khi CI thất bại

Một job chỉ báo database test failed sẽ khó điều tra. Khi lỗi xảy ra, pipeline nên lưu những thông tin đủ để xác định giai đoạn và nguyên nhân:

- Log khởi động PostgreSQL và trạng thái health check.
- Phiên bản server, extension và cấu hình liên quan.
- Log migration, bao gồm tên migration cuối cùng chạy thành công.
- SQLSTATE, thông báo lỗi và truy vấn liên quan nếu có thể ghi an toàn.
- Kết quả kiểm thử và tên test thất bại.
- EXPLAIN hoặc EXPLAIN ANALYZE cho truy vấn hiệu năng được chọn.
- Log ứng dụng và thông tin kết nối đã loại bỏ credential.

Có thể xem log container bằng:

~~~bash
docker compose logs --no-color postgres
~~~

Hoặc lấy thông tin phiên bản và extension:

~~~sql
SELECT version();

SELECT extname, extversion
FROM pg_extension
ORDER BY extname;
~~~

Không bật log toàn bộ câu lệnh hoặc bind parameter thiếu kiểm soát nếu chúng có thể chứa mật khẩu, token hoặc dữ liệu cá nhân. Log CI có thể được nhiều người trong tổ chức truy cập; cần giới hạn nội dung nhạy cảm và thời gian lưu.

Nếu test thất bại không ổn định, kiểm tra các nguyên nhân như dữ liệu dùng chung, thứ tự chạy test, thời gian chờ không đủ, connection pool chưa đóng, transaction chưa rollback hoặc test phụ thuộc đồng hồ hệ thống. Một lần chạy lại có thể giúp thu thập thêm bằng chứng, nhưng không nên coi retry thành cách sửa lỗi gốc.

## 11. Các lỗi thiết kế thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Test chạy được ở máy cá nhân nhưng lỗi trong CI | Khác phiên bản PostgreSQL, extension hoặc locale | Ghim image và cấu hình môi trường |
| Migration lỗi chỉ khi database đã có dữ liệu | Chỉ kiểm tra fresh install | Thêm bài kiểm tra nâng cấp từ phiên bản trước |
| Test phụ thuộc thứ tự | Dữ liệu còn sót hoặc test dùng chung trạng thái | Fixture rõ ràng và dọn dữ liệu sau test |
| Test song song thỉnh thoảng thất bại | Nhiều worker cùng sửa một bảng/schema | Database hoặc schema riêng theo worker |
| Container running nhưng ứng dụng không kết nối được | PostgreSQL chưa ready hoặc sai host/port | Health check và kiểm tra kết nối |
| Test thành công dù ứng dụng thiếu quyền | Dùng tài khoản superuser trong mọi test | Chạy bằng role runtime có quyền tối thiểu |
| Test rollback nhưng dữ liệu vẫn còn | Thay đổi được commit trên connection khác | Kiểm soát connection hoặc hủy môi trường |
| CI chạy lâu và tốn tài nguyên | Khởi động instance cho từng test nhỏ | Chia sẻ container theo suite, cô lập database/schema theo worker |

Các cách làm khác dễ tạo kết quả sai:

- Dùng database phát triển dùng chung cho CI khiến trạng thái giữa các lần chạy không xác định.
- Chỉ chạy test trên schema tạo thủ công, bỏ qua migration.
- Chạy migration bằng tài khoản quản trị rồi chạy ứng dụng bằng chính tài khoản đó, khiến thiếu quyền không bị phát hiện.
- Dùng dữ liệu production trực tiếp làm fixture.
- Dùng tag image latest, khiến cùng commit có thể chạy trên phiên bản PostgreSQL khác nhau ở hai thời điểm.
- Xóa dữ liệu bằng TRUNCATE trên database dùng chung mà không giới hạn phạm vi.
- Bỏ qua log khi job thất bại, khiến không thể biết lỗi nằm ở khởi động, migration, kết nối hay truy vấn.

## 12. Tổ chức pipeline theo chi phí và độ tin cậy

Có thể chạy các kiểm tra nhanh trước và kiểm tra tốn tài nguyên sau:

| Giai đoạn | Nội dung | Thời điểm phù hợp |
|---|---|---|
| Kiểm tra nhanh | Kiểm tra cú pháp migration, lint SQL và unit test | Mỗi commit |
| Database cơ bản | Tạo PostgreSQL, chạy migration từ đầu, kiểm tra constraint | Mỗi pull request |
| Integration | Repository, transaction, quyền và luồng ứng dụng | Mỗi pull request hoặc nhánh chính |
| Upgrade | Nâng cấp từ schema phiên bản trước với dữ liệu đại diện | Pull request có migration và lịch chạy định kỳ |
| Hiệu năng | Benchmark truy vấn trọng yếu và kiểm tra kế hoạch | Nhánh chính hoặc pipeline chuyên biệt |

Không phải repository nào cũng cần tách thành đúng năm job. Điều quan trọng là giữ ranh giới giữa kiểm tra nhanh và kiểm tra tích hợp, đồng thời đảm bảo mỗi job có môi trường database xác định.

Khi thay đổi chỉ ảnh hưởng một module, có thể chạy nhóm test liên quan trước để phản hồi nhanh. Tuy nhiên, migration dùng chung hoặc thay đổi kiểu dữ liệu cốt lõi vẫn cần được kiểm tra trên luồng tích hợp phù hợp, vì ảnh hưởng có thể lan sang nhiều thành phần.

## 13. Nguyên tắc duy trì môi trường kiểm thử

Môi trường database trong CI nên được quản lý như một phần của mã nguồn. File Compose, workflow, script migration, fixture và cấu hình extension cần được lưu cùng repository hoặc trong kho cấu hình có phiên bản. Người khác có thể đọc chúng để tái tạo cùng môi trường.

Mỗi lần chạy nên có vòng đời rõ ràng: tạo mới, kiểm tra readiness, chạy migration, nạp dữ liệu, thực thi test, lưu chẩn đoán và hủy tài nguyên tạm. Không để trạng thái của pipeline trước trở thành đầu vào ngầm cho pipeline sau.

Cần ghim phiên bản PostgreSQL và công cụ migration, đồng bộ extension với môi trường đích, kiểm tra cả database mới lẫn database nâng cấp, và chạy test bằng role có quyền gần với ứng dụng thật. Khi test chạy song song, mỗi worker phải có ranh giới dữ liệu riêng. Những quy tắc này giúp CI phát hiện lỗi database sớm và làm cho kết quả kiểm thử có thể lặp lại giữa máy lập trình viên, CI và các môi trường triển khai.

