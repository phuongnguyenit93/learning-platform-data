# Phối hợp migration với triển khai nhiều bản sao ứng dụng

Trong môi trường production, một ứng dụng thường chạy nhiều bản sao (replica) để tăng khả năng chịu lỗi và mở rộng tải. Khi phát hành phiên bản mới, hệ thống có thể đồng thời tồn tại nhiều pod hoặc instance: một số đang chạy mã cũ, một số đang khởi động mã mới, trong khi database chỉ có một schema dùng chung. Nếu mỗi bản sao tự chạy Liquibase lúc startup, các tiến trình migration có thể tranh nhau khởi tạo schema, chờ khóa và làm thời gian sẵn sàng của ứng dụng tăng mạnh. Nguy hiểm hơn, một thay đổi schema không tương thích có thể khiến các bản sao cũ đang phục vụ request lỗi ngay giữa quá trình rollout.

Cần thiết kế một quy trình phối hợp rõ ràng giữa **migration database** và **triển khai application replicas**. Liquibase có cơ chế khóa để điều phối các runner cùng phạm vi lịch sử, nhưng khóa đó không tự bảo đảm phiên bản ứng dụng cũ và mới tương thích với schema trong suốt rolling deployment. Chiến lược phổ biến là chạy migration bằng một job được điều phối một lần cho mỗi database/release, triển khai thay đổi schema theo hướng tương thích ngược và xuôi, rồi chỉ thực hiện thao tác phá hủy sau khi mọi replica cũ đã được loại bỏ.

Bài thuộc chương **CI/CD** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu module là nắm cách quản lý thay đổi schema và dữ liệu bằng changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài này tập trung vào cách điều phối Liquibase cùng nhiều bản sao ứng dụng trong Kubernetes, container platform hoặc hệ thống deployment tương tự, bao gồm thứ tự phát hành, Liquibase lock, expand-contract, readiness, quyền database và phục hồi khi rollout lỗi.

## 1. Vấn đề khi nhiều replica cùng khởi chạy Liquibase

Giả sử một dịch vụ Spring Boot chạy 8 replica, tất cả kết nối tới cùng database và dùng cùng changelog. Khi triển khai phiên bản mới, Kubernetes có thể khởi tạo nhiều pod mới gần như đồng thời. Nếu mỗi pod đều bật Liquibase auto-configuration, mỗi instance có thể khởi tạo một Liquibase runner.

Một kịch bản điển hình:

1. Pod mới A khởi tạo DataSource và bắt đầu Liquibase.
2. A lấy được DATABASECHANGELOGLOCK và chạy changeset.
3. Pod mới B, C và D cũng khởi tạo Liquibase.
4. Các runner còn lại nhìn thấy lock đang được giữ và phải chờ hoặc thất bại theo timeout/chính sách.
5. ApplicationContext của các pod đang chờ chưa hoàn tất; readiness có thể chưa đạt.
6. Nếu migration dài, pod có thể vượt startup timeout hoặc bị orchestration restart.
7. Khi runner A hoàn tất và nhả lock, runner khác có thể tiếp tục kiểm tra history rồi nhận thấy changeset đã được ghi nhận.

Liquibase lock giúp tránh các runner tuân theo cùng cơ chế ghi đồng thời một changeset trong cùng phạm vi lock. Tuy nhiên, việc để mọi replica khởi chạy migration vẫn gây nhiều kết nối, nhiều lần khởi tạo, thời gian chờ và log nhiễu. Nếu các replica dùng changelog khác phiên bản hoặc cấu hình bảng lock khác nhau, rủi ro còn lớn hơn.

~~~mermaid
sequenceDiagram
    participant A as Pod mới A
    participant B as Pod mới B
    participant C as Pod mới C
    participant L as DATABASECHANGELOGLOCK
    participant DB as Database
    A->>L: Xin lock
    L-->>A: Cấp lock
    B->>L: Xin lock
    L-->>B: Đang bị khóa, phải chờ
    C->>L: Xin lock
    L-->>C: Đang bị khóa, phải chờ
    A->>DB: Thực thi changeset
    A->>L: Giải phóng lock
    L-->>B: Có thể tiếp tục
    B->>DB: Đọc history, thấy changeset đã chạy
~~~

Sơ đồ minh họa hành vi khái quát. Thời gian chờ, retry và cách log phụ thuộc Liquibase version, cấu hình và orchestration. Điểm cần nhớ là lock điều phối migration; nó không biến việc chạy migration ở mọi replica thành một thiết kế triển khai tối ưu.

## 2. Phân biệt ba loại điều phối

Trong hệ thống nhiều replica, có ba lớp điều phối khác nhau:

| Lớp | Trách nhiệm | Cơ chế thường dùng |
|---|---|---|
| Điều phối deployment | Chọn release nào được triển khai trước, tránh hai pipeline đụng nhau | CI/CD concurrency group, deployment lock, release queue |
| Điều phối migration | Không cho nhiều Liquibase runner cùng phạm vi ghi history đồng thời | DATABASECHANGELOGLOCK |
| Điều phối traffic/replica | Kiểm soát replica nào nhận traffic và thời điểm thay thế | Rolling update, readiness, canary, blue-green |

Không dùng một cơ chế thay cho cả ba. DATABASECHANGELOGLOCK không khóa pipeline deployment, không ngăn hai release khác nhau tranh nhau thay đổi database theo thứ tự không mong muốn và không bảo đảm pod cũ tương thích schema mới.

Ví dụ, pipeline release A và release B cùng chạy. Liquibase lock có thể khiến một runner phải chờ, nhưng nếu B lấy lock trước thì changeset của B có thể chạy trước A. Nếu hai artifact không được thiết kế để chạy theo thứ tự đó, kết quả có thể sai dù lock hoạt động đúng. Cần thêm điều phối deployment theo database ở CI/CD.

## 3. Mô hình khuyến nghị: một migration job cho mỗi database và release

Thay vì để từng application replica chạy migration, có thể tạo một bước riêng trong pipeline:

1. Build một artifact changelog bất biến.
2. Chạy validate và preflight.
3. Tạo migration Job với đúng target database.
4. Chờ Job hoàn tất và kiểm tra kết quả.
5. Xác minh schema, dữ liệu và DATABASECHANGELOG.
6. Chỉ khi migration đạt mới bắt đầu rollout application replicas.
7. Các pod ứng dụng chạy với quyền runtime phù hợp, không tự thực hiện DDL.

~~~mermaid
flowchart TD
    A["Build artifact ứng dụng + changelog"] --> B["CI preflight / validate / update-sql"]
    B --> C["Migration Job: một target DB"]
    C --> D{"Migration và post-check PASS?"}
    D -- "Không" --> E["Dừng rollout, điều tra"]
    D -- "Có" --> F["Rolling deploy application replicas"]
    F --> G["Readiness / smoke test"]
    G --> H{"Ứng dụng ổn định?"}
    H -- "Không" --> I["Rollback application hoặc forward-fix"]
    H -- "Có" --> J["Theo dõi release"]
~~~

Migration job là một đơn vị triển khai độc lập, có log, exit code, timeout, retry policy và quyền database riêng. Nếu database có nhiều tenant hoặc nhiều target vật lý, có thể tạo một job cho mỗi target hoặc một orchestration job quản lý danh sách target với trạng thái riêng.

Ưu điểm:

- Migration chỉ chạy một lần theo release/target.
- Application replicas không phải chờ migration lúc startup.
- Có thể cấp quyền DDL riêng cho job.
- Có thể review SQL trước khi chạy.
- Pipeline dừng trước khi rollout nếu migration thất bại.
- Log và kết quả migration không bị trộn với log startup của từng pod.

Đây là mô hình phù hợp với phần lớn hệ thống production có nhiều replica. Nó không loại bỏ nhu cầu Liquibase lock: lock vẫn bảo vệ trường hợp job bị chạy trùng, retry hoặc có một runner khác cùng target.

## 4. Khi nào vẫn để Spring Boot chạy Liquibase lúc startup?

Có những ứng dụng nhỏ hoặc môi trường đơn giản chọn để Spring Boot tự chạy Liquibase khi khởi tạo ApplicationContext. Cách này có thể chấp nhận được nếu:

- Chỉ có một instance khởi động trong giai đoạn migration.
- Mọi replica dùng cùng changelog và cùng database/history/lock.
- Thời gian migration ngắn, có timeout phù hợp.
- Schema thay đổi tương thích với phiên bản ứng dụng đang chạy.
- Readiness và startup probe được cấu hình để không đánh giá nhầm migration hợp lệ là ứng dụng treo.
- Có runbook khi lock bị giữ hoặc migration thất bại.

Khi số replica tăng, migration dài hoặc yêu cầu phân quyền chặt, nên chuyển sang migration job riêng. Nếu chọn job riêng, ứng dụng có thể tắt Liquibase auto-run bằng cấu hình phù hợp:

~~~yaml
spring:
  liquibase:
    enabled: false
~~~

Cấu hình này chỉ là ví dụ cho profile runtime. Migration job phải có cơ chế riêng để chạy đúng changelog và target; không được tắt auto-run rồi quên bước migration trong pipeline.

Có thể dùng một profile chuyên dụng hoặc một image/entrypoint migration riêng. Dù cách nào, hãy bảo đảm job và ứng dụng dùng cùng release artifact hoặc cùng changelog version đã được phê duyệt.

## 5. DATABASECHANGELOGLOCK bảo vệ điều gì?

Liquibase sử dụng bảng DATABASECHANGELOGLOCK để điều phối các tiến trình migration cùng phạm vi lock. Khi runner lấy được lock, runner khác dùng cùng bảng khóa sẽ không đồng thời thực hiện update trong phạm vi đó.

Các điều kiện để cơ chế này có ý nghĩa:

- Các runner cùng trỏ tới đúng database hoặc cùng kho trạng thái lock được thiết kế.
- Cùng sử dụng đúng schema và tên bảng lock.
- Không có runner khác cố ý bỏ qua cơ chế lock.
- Quyền đọc/ghi bảng lock hoạt động.
- Lock được giữ và giải phóng theo vòng đời thực thi.

Nếu mỗi replica dùng một schema metadata hoặc tên bảng lock riêng ngoài ý muốn, chúng không còn phối hợp qua cùng một lock. Ngược lại, nếu nhiều database độc lập chia sẻ history/lock sai cách, lịch sử của một target có thể ảnh hưởng target khác.

### 5.1. Kiểm tra lock trước và sau migration

Có thể truy vấn trạng thái lock trong database, điều chỉnh schema theo cấu hình thực tế:

~~~sql
SELECT id, locked, lockgranted, lockedby
FROM databasechangeloglock;
~~~

Trước khi migration bắt đầu, xác nhận không có tiến trình cũ giữ lock bất thường. Sau khi job hoàn tất, xác minh lock đã được giải phóng.

Không tự cập nhật LOCKED=false bằng SQL chỉ vì pod đang chờ. Trước tiên phải xác định runner nào đang giữ lock, process/pod đó còn hoạt động không, DBMS session có đang chạy DDL/DML không và trạng thái database có an toàn không. Việc giải phóng lock trong khi migration vẫn chạy có thể cho phép một runner khác bắt đầu và gây xung đột.

### 5.2. Lock không thay thế deployment lock

Liquibase lock chỉ bảo vệ các runner cùng phạm vi bảng lock. Nó không đảm bảo release A phải chạy trước release B. CI/CD nên có concurrency group hoặc cơ chế xếp hàng theo database/target để tránh hai release cùng chạy migration với artifact khác nhau.

## 6. Tương thích schema trong thời gian rolling deployment

Trong rolling deployment, ứng dụng cũ và mới có thể chạy cùng lúc. Vì vậy, schema phải hỗ trợ cả hai phiên bản trong khoảng chuyển tiếp.

Ví dụ phiên bản cũ đọc cột customer.full_name. Phiên bản mới muốn tách thành first_name và last_name. Nếu migration xóa full_name ngay trước khi rollout, các pod cũ sẽ lỗi khi truy vấn.

Chiến lược **expand-contract** giải quyết vấn đề bằng cách chia thay đổi thành nhiều release:

- Expand: thêm cấu trúc mới nhưng giữ cấu trúc cũ.
- Migrate: chuyển dữ liệu và ứng dụng dần sang cấu trúc mới.
- Contract: xóa cấu trúc cũ sau khi không còn consumer.

~~~mermaid
flowchart LR
    A["Release 1<br/>Expand schema"] --> B["Release 2<br/>Dual read/write + backfill"]
    B --> C["Release 3<br/>Dùng schema mới"]
    C --> D["Release 4<br/>Contract schema cũ"]
~~~

Điều quan trọng là mỗi giai đoạn phải tương thích với phiên bản ứng dụng có thể đang chạy. Không gộp thêm cột, đổi code, xóa cột và deploy cùng một thời điểm nếu rolling deployment tạo ra khoảng thời gian hai phiên bản cùng truy cập database.

## 7. Ví dụ expand-contract cho việc đổi tên cột

Giả sử bảng customer có cột email. Phiên bản mới muốn dùng email_address.

### Release A — Expand

Thêm cột mới nullable, vẫn giữ cột cũ:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 100-add-email-address
      author: database-team
      changes:
        - addColumn:
            tableName: customer
            columns:
              - column:
                  name: email_address
                  type: VARCHAR(255)
                  constraints:
                    nullable: true
~~~

Phiên bản ứng dụng cũ vẫn đọc/ghi email. Schema mới đã có email_address nhưng chưa bắt buộc sử dụng.

### Release B — Dual write và backfill

Triển khai phiên bản ứng dụng có thể ghi cả email và email_address trong giai đoạn chuyển tiếp. Backfill dữ liệu cũ sang cột mới theo batch và có khả năng resume.

~~~sql
UPDATE customer
SET email_address = email
WHERE email_address IS NULL
  AND email IS NOT NULL;
~~~

Trên bảng lớn, không chạy một update khổng lồ nếu có thể gây transaction/lock/WAL quá lớn. Chia batch theo khóa, đo tải và kiểm tra số dòng còn thiếu.

### Release C — Chuyển đọc sang cột mới

Sau khi backfill hoàn tất và dữ liệu đã được xác minh, triển khai ứng dụng đọc email_address. Có thể vẫn dual write trong một khoảng để hỗ trợ rollback ứng dụng về phiên bản cũ.

### Release D — Contract

Sau khi chắc chắn không còn replica, worker, batch job hoặc consumer nào sử dụng email, tạo changeset mới để ngừng ghi rồi xóa cột cũ trong release riêng.

Không sửa changeset đã triển khai để thay đổi lại nội dung. Mỗi giai đoạn là changeset/release mới, có thể kiểm tra và truy vết trong DATABASECHANGELOG.

## 8. Thứ tự triển khai: migration trước, application sau

Với migration tương thích ngược, thứ tự phổ biến là:

1. Xác minh target database và artifact.
2. Chạy validate/status/update-sql.
3. Chạy migration expand.
4. Chạy post-check schema/data/history.
5. Bắt đầu rolling deploy application mới.
6. Chờ readiness và smoke test.
7. Theo dõi lỗi ứng dụng và database.
8. Chỉ thực hiện contract trong release sau khi hết phiên bản cũ.

Vì sao migration expand thường chạy trước? Bản mới có thể cần cột/bảng mới ngay khi khởi động. Nếu deploy app trước khi schema tồn tại, pod mới có thể khởi động nhưng request đầu tiên truy vấn cấu trúc chưa có sẽ lỗi.

Tuy nhiên, migration trước chỉ an toàn nếu schema mới vẫn tương thích với app cũ đang chạy. Đây là điều kiện cốt lõi của rolling deployment. Nếu thay đổi không tương thích, cần một quy trình maintenance/cutover có dừng traffic hoặc một kế hoạch chuyển đổi nhiều giai đoạn.

## 9. Cấu hình Kubernetes Job cho migration

Có thể tạo Kubernetes Job riêng để chạy Liquibase. Ví dụ pseudomanifest:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: orders-db-migration-release-2026-11
spec:
  backoffLimit: 0
  activeDeadlineSeconds: 900
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: liquibase
          image: registry.example/orders-service:2026.11
          command:
            - java
            - -jar
            - app.jar
            - --spring.profiles.active=migration
          env:
            - name: DB_URL
              valueFrom:
                secretKeyRef:
                  name: orders-db
                  key: url
            - name: DB_USERNAME
              valueFrom:
                secretKeyRef:
                  name: orders-db
                  key: migration-username
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: orders-db
                  key: migration-password
~~~

Đây là manifest minh họa, không phải cấu hình có thể áp dụng nguyên trạng. Ứng dụng cần có profile migration, entrypoint hoặc cơ chế Liquibase phù hợp để chỉ chạy migration rồi kết thúc process. Biến môi trường phải được ánh xạ đúng vào cấu hình Spring Boot/CLI của dự án. Không để container migration khởi động web server rồi chạy vô hạn nếu Job chỉ cần thực hiện migration.

Các thuộc tính cần cân nhắc:

- backoffLimit: số lần Kubernetes thử lại Job sau lỗi.
- activeDeadlineSeconds: giới hạn tổng thời gian Job.
- restartPolicy: thường dùng Never cho job migration có kiểm soát.
- image: pin theo artifact/release đã review.
- secretKeyRef: lấy thông tin kết nối từ secret store.
- serviceAccount: chỉ cấp quyền Kubernetes cần thiết.
- resources: giới hạn CPU/RAM phù hợp.
- ttlSecondsAfterFinished: dọn Job sau khi giữ đủ log và kết quả.

Nếu Job được tự động retry, phải xác minh changeset trước đó có thể đã commit một phần hay chưa. Không tăng backoffLimit vô hạn cho migration không idempotent.

## 10. CI/CD pipeline với gate giữa migration và rollout

Một pipeline có thể biểu diễn:

~~~yaml
stages:
  - validate
  - migrate
  - verify
  - deploy
  - smoke-test

validate:
  script:
    - liquibase validate
    - liquibase status --verbose
    - liquibase update-sql

migrate:
  needs: [validate]
  script:
    - liquibase update

verify:
  needs: [migrate]
  script:
    - ./verify-schema-and-data.sh

deploy:
  needs: [verify]
  script:
    - kubectl rollout restart deployment/orders-api

smoke-test:
  needs: [deploy]
  script:
    - ./smoke-test.sh
~~~

Đây là pseudopipeline; cú pháp và cơ chế needs/stages phụ thuộc CI provider. Điểm quan trọng là bước deploy phụ thuộc vào migration và post-check thành công.

Không chạy validate bằng một artifact rồi update bằng artifact khác. Các bước phải dùng cùng changelog version, Liquibase version, filter và target. Lưu SQL preview, log, digest artifact và kết quả xác minh làm bằng chứng phát hành.

### 10.1. Serialize pipeline theo database

Thiết lập concurrency group theo target database, ví dụ orders-production. Khi một pipeline đang migrate target đó, release khác phải chờ hoặc bị từ chối theo chính sách.

Không dùng một concurrency group toàn cục cho mọi database độc lập nếu không cần thiết; điều đó làm giảm throughput. Ngược lại, không chỉ khóa theo tên application nếu nhiều ứng dụng cùng thay đổi một database dùng chung.

## 11. Tương thích giữa phiên bản ứng dụng cũ và mới

Trước rollout, lập ma trận tương thích:

| Schema | App cũ | App mới |
|---|---|---|
| Schema cũ | Hoạt động | Có thể chưa hoạt động |
| Schema expand | Phải tiếp tục hoạt động | Hoạt động |
| Schema contract | Không còn hỗ trợ | Hoạt động |

Mục tiêu là schema expand hỗ trợ cả app cũ và mới trong giai đoạn chuyển tiếp. Schema contract chỉ được áp dụng sau khi app cũ không còn tồn tại và các consumer khác đã chuyển đổi.

Cần kiểm tra không chỉ HTTP application replicas mà còn:

- Worker nền.
- Scheduled job.
- Consumer queue.
- Batch ETL.
- Reporting service.
- Script quản trị.
- Phiên bản ứng dụng rollback có thể được khôi phục.

Một cột có thể không còn được web pod sử dụng nhưng vẫn được batch job cũ truy cập. Contract dựa trên việc “pod mới đã ready” là chưa đủ; phải xác định toàn bộ consumer.

## 12. Readiness, liveness và startup probe

Khi migration chạy trong application startup, ApplicationContext có thể chưa hoàn tất cho tới khi Liquibase xong. Khi đó:

- Readiness probe nên giữ pod khỏi nhận traffic cho tới khi ứng dụng thực sự sẵn sàng.
- Startup probe cần đủ thời gian cho khởi động hợp lệ, đặc biệt nếu migration vẫn chạy trong startup.
- Liveness probe không nên giết process chỉ vì migration đang thực hiện hợp lệ.
- Readiness không thay thế post-check database hoặc smoke test.

Nếu migration job riêng, application pod chỉ được triển khai sau khi job thành công. Khi đó startup probe không cần chờ một migration dài chạy trong từng pod, nhưng readiness vẫn phải kiểm tra ứng dụng có kết nối và hoạt động với schema mới.

Không tăng timeout vô hạn để che migration bị block. Theo dõi thời gian, log, DATABASECHANGELOGLOCK và DBMS session để phân biệt khởi động chậm hợp lệ với tiến trình bị treo.

## 13. Tránh hai release cạnh tranh cùng database

Liquibase lock ngăn runner cùng lock table update đồng thời, nhưng không bảo đảm thứ tự nghiệp vụ giữa hai release.

Ví dụ:

- Release A thêm cột status_v2.
- Release B xóa cột status cũ.
- B chạy trước A vì pipeline được khởi chạy đồng thời.
- Liquibase lock có thể tuần tự hóa hai lần chạy, nhưng B vẫn có thể chạy theo thứ tự sai.

CI/CD cần một cơ chế serialize theo database. Có thể dùng:

- Concurrency group trong CI.
- Deployment environment lock.
- Release queue.
- Một migration controller duy nhất.
- Quy tắc chỉ cho một pipeline giữ quyền triển khai database tại một thời điểm.

Cơ chế này phải áp dụng cho tất cả ứng dụng cùng sở hữu database, không chỉ một repository. Nếu nhiều team cùng thay đổi schema, cần quy trình phối hợp release và ownership changeset.

## 14. Quyền database: tách migration role và application role

Application replica thường chỉ cần quyền đọc/ghi dữ liệu nghiệp vụ. Migration job cần quyền DDL và có thể cần quyền đọc metadata hoặc ghi bảng Liquibase history/lock.

Nên tách:

| Tài khoản | Quyền |
|---|---|
| migration user | Quyền DDL/DML cần thiết cho changeset, ghi DATABASECHANGELOG và LOCK |
| application user | Quyền runtime tối thiểu: SELECT/INSERT/UPDATE/DELETE theo chức năng |
| monitoring user | Quyền đọc metrics/session/catalog cần thiết, không có DDL |

Khi migration job riêng, có thể cấp credential DDL trong thời gian triển khai rồi hạn chế truy cập. Không đưa migration password vào mọi pod ứng dụng nếu ứng dụng không cần quyền đó.

Tách quyền giảm tác động khi một replica ứng dụng bị xâm nhập hoặc cấu hình sai. Tuy nhiên, cần kiểm tra migration job có đủ quyền tạo object trong schema và quản lý owner/privileges theo chuẩn DBMS.

## 15. Migration nhiều database hoặc nhiều tenant

Nếu một ứng dụng có nhiều database, mỗi database là một đơn vị migration riêng. Pipeline cần xác định:

- Target ID và database identity.
- Artifact changelog.
- Schema ứng dụng và schema tracking.
- DATABASECHANGELOG/DATABASECHANGELOGLOCK.
- Trạng thái migration và post-check.
- Thứ tự rollout nếu database phụ thuộc nhau.

Không giả định một Job chạy update trên database A có nghĩa database B cũng đã được cập nhật. Lưu trạng thái riêng cho từng target. Chỉ deploy replica của service phụ thuộc database sau khi database tương ứng đạt trạng thái mong muốn.

Với tenant-per-schema trong cùng database, phải xác định lịch sử và lock có được phân vùng theo tenant hay không. Một DATABASECHANGELOG dùng chung có thể không đại diện được việc cùng changeset đã chạy trên từng schema tenant. Thiết kế tracking table theo đơn vị migration và kiểm thử rõ trước rollout.

## 16. Canary và blue-green deployment

Canary triển khai một tỷ lệ nhỏ replica mới trước, theo dõi lỗi rồi tăng dần. Blue-green duy trì hai nhóm ứng dụng và chuyển traffic giữa chúng.

Cả hai đều cần schema tương thích:

- Expand schema trước khi bật nhóm app mới.
- App cũ và mới cùng hoạt động trên schema expand.
- Canary không được chạy migration riêng khi pod canary khởi động.
- Blue và green phải dùng cùng database; schema không thể rollback cùng cách với traffic.
- Contract chỉ chạy sau khi không còn traffic hoặc background consumer dùng schema cũ.

Ví dụ blue-green:

~~~text
                 Database: schema expand
                         |
          +--------------+--------------+
          |                             |
     Blue replicas                 Green replicas
       app v1                         app v2
          |                             |
          +-------- cùng DB ------------+

    Chuyển traffic sau khi Green đạt smoke test.
    Giữ Blue đủ lâu để rollback application nếu cần.
    Contract schema cũ ở release sau.
~~~

Khi chuyển traffic về Blue, Blue vẫn phải tương thích schema expand. Nếu migration đã xóa cột Blue cần dùng, rollback traffic không cứu được ứng dụng.

## 17. Xử lý migration job thất bại

Nếu migration job thất bại, không bắt đầu rollout app mới. Trước tiên:

1. Lưu log, exit code, release ID và target.
2. Xác định changeset cuối đã hoàn tất.
3. Kiểm tra DATABASECHANGELOG.
4. Kiểm tra DATABASECHANGELOGLOCK và process holder.
5. Kiểm tra schema/data thực tế để phát hiện thay đổi một phần.
6. Xem DBMS có transactional DDL cho thao tác đó không.
7. Xác định nguyên nhân: quyền, dữ liệu, SQL, timeout, lock hay resource.
8. Chọn sửa lỗi và retry, forward-fix hoặc restore theo kế hoạch.
9. Chạy post-check trước khi mở gate deployment.

Không tự xóa history hoặc giải phóng lock bằng SQL để làm Job xanh. Nếu DDL đã commit nhưng history chưa được ghi, retry có thể gặp object already exists. Cần reconcile trạng thái theo runbook có kiểm chứng.

Nếu migration expand đã thành công nhưng rollout app thất bại, thường có thể giữ schema expand và rollback application về phiên bản cũ nếu tương thích. Không cần rollback schema ngay lập tức; schema expand được thiết kế để hỗ trợ cả hai phiên bản.

## 18. Rollback application khác rollback database

Hai thao tác này có phạm vi và rủi ro khác nhau:

- **Rollback application:** đưa traffic về image/version trước.
- **Rollback database:** thực thi changeset rollback hoặc phục hồi database.
- **Forward-fix:** phát hành changeset mới để sửa trạng thái hiện tại.

Với chiến lược expand-contract, rollback application thường dễ hơn rollback schema. Cột mới hoặc index mới có thể được giữ lại mà không ảnh hưởng app cũ. Ngược lại, DROP COLUMN có thể làm mất dữ liệu và khiến app cũ không hoạt động nếu rollback ứng dụng.

Trước khi phát hành, phải kiểm tra schema expand tương thích với app cũ. Contract migration thường là bước riêng, sau một khoảng quan sát. Nếu contract đã chạy, rollback app cũ có thể không còn an toàn.

Không coi rollback-count là nút undo toàn bộ release. Kiểm tra SQL rollback, dữ liệu phát sinh sau deploy, dependency và hành vi DBMS.

## 19. Chạy preflight và post-check có cùng target

Trước migration:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
~~~

Các lệnh phải dùng đúng changelog, Liquibase version, context/label, DBMS filter và JDBC URL. Sau migration:

- Đối chiếu changeset mong đợi trong DATABASECHANGELOG.
- Xác nhận DATABASECHANGELOGLOCK đã được giải phóng.
- Kiểm tra bảng/cột/index/constraint.
- Kiểm tra data migration và invariant nghiệp vụ.
- Kiểm tra ứng dụng cũ vẫn chạy được trên schema expand.
- Kiểm tra ứng dụng mới hoạt động với schema mới.
- Lưu kết quả cùng release artifact.

Post-check không chỉ là status không còn pending. Status chỉ cho biết changeset theo lịch sử; nó không chứng minh dữ liệu hoặc schema thực tế hoàn toàn đúng.

## 20. Kiểm thử trước release với nhiều replica

Trong môi trường test/staging, nên mô phỏng:

- Nhiều pod cùng khởi động nếu app vẫn auto-run Liquibase.
- Một migration job chạy trước rồi nhiều app replica khởi động.
- Hai pipeline release cùng nhắm một database.
- Migration kéo dài và readiness/startup timeout.
- App cũ và mới chạy đồng thời trên schema expand.
- Rollback application sau khi expand migration thành công.
- Migration thất bại do quyền hoặc dữ liệu.
- Job retry sau lỗi và trạng thái một phần.
- Contract migration chỉ chạy sau khi old replicas và background consumers đã dừng.

Các test này giúp phát hiện vấn đề orchestration mà unit test changelog không thể thấy. Dùng DBMS thực tế hoặc Testcontainers cho các thay đổi phụ thuộc cú pháp/transaction cụ thể.

## 21. Theo dõi rollout và migration

Một dashboard hoặc báo cáo release nên hiển thị:

| Thành phần | Tín hiệu |
|---|---|
| Migration Job | Pending/Running/Completed/Failed |
| Database target | DB identity, schema, release |
| Liquibase | Changeset cuối, pending, lock state |
| Application rollout | Desired/updated/available replicas |
| Readiness | Replica nào đã sẵn sàng |
| Error rate | Tỷ lệ lỗi request theo version |
| DBMS | Lock wait, query duration, connection count |
| Compatibility | App cũ/mới có cùng hoạt động trên schema hiện tại? |

Gắn release ID và image version vào log. Không gắn password hoặc connection string có credentials vào metric. Nếu một pod mới crashloop, xác định nó lỗi do Liquibase startup, datasource, schema mismatch hay application bug.

## 22. Những anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách tổ chức tốt hơn |
|---|---|---|
| Mỗi replica tự chạy migration dài | Nhiều runner chờ lock, startup chậm | Một migration Job có điều phối |
| Dùng lock như deployment queue | Hai release khác thứ tự vẫn có thể chạy sai | CI/CD serialize theo database |
| DROP/rename ngay trong rolling deploy | Replica cũ lỗi giữa rollout | Expand-contract |
| Tắt Liquibase ở app nhưng quên migration job | App mới chạy trên schema cũ | Gate bắt buộc trước deploy |
| Dùng migration credential trong mọi pod | Quyền DDL bị mở rộng không cần thiết | Tách migration/application role |
| Retry vô hạn Job | Lặp thao tác không an toàn, che partial failure | Retry hữu hạn và kiểm tra history/schema |
| Release lock khi runner còn hoạt động | Hai runner có thể cùng sửa database | Xác minh holder trước khi can thiệp |
| Contract ngay sau canary | Replica cũ hoặc worker còn dùng cột cũ | Chờ toàn bộ consumer chuyển đổi |
| Hai pipeline chạy đồng thời | Artifact khác nhau cạnh tranh database | Concurrency group/release queue |
| Chỉ kiểm tra pod Ready | Không chứng minh dữ liệu/schema đúng | Post-check DB và smoke test |

## 23. Runbook triển khai một release nhiều replica

Một quy trình thực tế có thể theo thứ tự:

**Trước release**

1. Chọn changelog artifact bất biến và Liquibase version.
2. Xác định database target và migration owner.
3. Xác minh pipeline khác không giữ deployment lock.
4. Chạy validate, status và update-sql.
5. Review destructive changes, lock impact và thời gian dự kiến.
6. Xác nhận schema expand tương thích app cũ và mới.

**Migration**

7. Khởi chạy một migration Job.
8. Theo dõi log, DATABASECHANGELOG và DATABASECHANGELOGLOCK.
9. Nếu Job thất bại, dừng rollout và điều tra partial changes.
10. Chạy post-check schema/data/history.

**Application rollout**

11. Mở gate cho rolling/canary/blue-green deployment.
12. Theo dõi readiness, error rate và database load.
13. Xác nhận cả phiên bản cũ và mới hoạt động trong giai đoạn chuyển tiếp.
14. Giữ khả năng rollback application khi schema vẫn tương thích.

**Contract**

15. Xác nhận không còn replica, worker, batch hoặc consumer dùng schema cũ.
16. Phát hành changeset contract riêng.
17. Chạy migration và post-check.
18. Cập nhật runbook và trạng thái release.

Không gộp contract vào cùng lần triển khai expand nếu cần khoảng thời gian tương thích cho nhiều replica.

## 24. Bài thực hành: phối hợp migration với ba replica

Dùng một ứng dụng Spring Boot, database lab và môi trường Kubernetes local hoặc mô phỏng container. Không dùng production.

### Bước 1 — Chuẩn bị ứng dụng

Tạo một endpoint đọc bảng customer. Phiên bản v1 dùng cột email. Chuẩn bị phiên bản v2 muốn dùng email_address.

### Bước 2 — Tạo expand changeset

Thêm email_address nullable và giữ nguyên email. Chạy migration trên database lab. Xác minh schema có cả hai cột.

### Bước 3 — Chạy nhiều replica v1

Khởi động ba replica v1 cùng database. Gửi request và xác nhận chúng hoạt động trên schema expand.

### Bước 4 — Chạy migration job riêng

Tạo một job chạy Liquibase bằng artifact release. Xác minh chỉ job này thực thi migration; application replicas không dùng quyền DDL. Có thể kiểm tra log và DATABASECHANGELOGLOCK.

### Bước 5 — Triển khai v2 theo rolling update

Cho ba replica v2 lần lượt thay v1. Trong khoảng chuyển tiếp, xác nhận cả v1 và v2 đều hoạt động. Kiểm tra readiness và request error rate.

### Bước 6 — Dual write và backfill

Cho v2 ghi cả hai cột trong giai đoạn tương thích. Backfill dữ liệu cũ sang email_address theo batch. Kiểm tra không còn giá trị thiếu hoặc sai lệch.

### Bước 7 — Thử rollback ứng dụng

Rollback một replica hoặc toàn bộ deployment về v1 khi schema vẫn expand. Xác nhận v1 còn hoạt động vì cột email chưa bị xóa.

### Bước 8 — Contract ở release sau

Sau khi xác nhận không còn consumer dùng email, tạo changeset mới để bỏ cột cũ. Chạy job riêng và kiểm tra không còn app/worker cũ.

### Bước 9 — Mô phỏng hai pipeline cạnh tranh

Khởi chạy hai release giả lập cùng target. Xác nhận CI/CD concurrency group xếp hàng hoặc từ chối release thứ hai. Liquibase lock là lớp bảo vệ bổ sung, không phải thứ tự release duy nhất.

### Bước 10 — Báo cáo

Ghi release ID, artifact, database, changeset, số replica, thời điểm migration, lock state, readiness, error rate và kết quả rollback/contract.

Điều kiện hoàn thành: người học giải thích được vì sao một migration job riêng giảm rủi ro, phân biệt Liquibase lock với deployment lock, thiết kế expand-contract và chứng minh app cũ/mới cùng hoạt động trên schema chuyển tiếp.

## 25. Checklist trước khi triển khai migration với nhiều replica

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Ai sở hữu migration của database? | Job/pipeline hoặc startup policy rõ ràng |
| Chỉ một release được điều phối tại một thời điểm? | CI concurrency group hoặc release queue |
| Các runner cùng dùng đúng history/lock scope? | DATABASECHANGELOG và DATABASECHANGELOGLOCK được xác minh |
| Artifact changelog được pin? | Release ID, digest và Liquibase version |
| Migration job có target identity đúng? | Preflight và database identity |
| Job có quyền DDL riêng? | Migration role tách application role |
| App replicas không tự chạy migration ngoài chủ đích? | Spring profile và auto-configuration được kiểm tra |
| Changeset có tương thích app cũ/mới? | Compatibility matrix và integration test |
| Expand-contract được chia release? | Kế hoạch thêm, chuyển dữ liệu, ngừng dùng và xóa |
| Readiness/startup probe phù hợp? | Timeout và test rollout |
| Job retry có giới hạn? | Backoff/deadline và runbook partial failure |
| Có post-check trước rollout? | Schema/data/history assertions |
| Rollback application có thể thực hiện? | Schema expand giữ tương thích với app cũ |
| Contract chỉ chạy khi consumer cũ đã dừng? | Bằng chứng từ replica, worker và batch |
| Có theo dõi DB lock và request errors? | Dashboard/log/alert |
| Có diễn tập lỗi migration và rollout? | Kết quả test/staging |

**Nguyên tắc cuối cùng:** nhiều replica ứng dụng nên dùng chung một schema được cập nhật theo một quy trình release có điều phối. Hãy chạy migration một lần cho mỗi database/release bằng job chuyên dụng khi phù hợp, dùng DATABASECHANGELOGLOCK như lớp bảo vệ cho các Liquibase runner cùng phạm vi, và dùng CI/CD lock để tuần tự hóa các release. Quan trọng nhất, thiết kế changeset theo expand-contract để phiên bản cũ và mới cùng hoạt động trong suốt rolling deployment. Chỉ xóa cấu trúc cũ sau khi mọi replica và consumer đã chuyển đổi, còn trạng thái database đã được kiểm tra và có phương án phục hồi rõ ràng.

