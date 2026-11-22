# Chỉ cho phép một tác vụ migration trên cùng cơ sở dữ liệu

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chúng ta quản lý thay đổi schema và dữ liệu bằng **changelog**, **changeset**, **precondition**, **checksum** và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Bài thuộc chương **CI/CD** này trình bày cách bảo đảm tại một thời điểm chỉ có **một tác vụ thay đổi schema được phép sở hữu cùng một database**.

Khi nhiều pipeline, nhiều nhóm hoặc nhiều replica ứng dụng cùng khởi chạy Liquibase, các tiến trình có thể cùng nhìn thấy changeset pending và cố gắng thay đổi một database. Cơ chế khóa của Liquibase giúp tuần tự hóa các lần cập nhật dùng chung bảng lock; CI/CD và bộ điều phối cần bổ sung một lớp khóa theo danh tính database để kiểm soát cả những tiến trình không dùng chung metadata.

Nguyên tắc vận hành là **single writer cho migration trên mỗi database**: một tác vụ được quyền thực thi thay đổi tại một thời điểm; các tác vụ khác phải xếp hàng, chờ hoặc kết thúc với trạng thái rõ ràng. Điều này áp dụng cho update, rollback và các thao tác khác có thể thay đổi schema hoặc lịch sử Liquibase. Những lệnh chỉ đọc vẫn cần giới hạn tải, nhưng không nhất thiết chiếm khóa migration độc quyền.

## 1. Vì sao phải giới hạn một migration task trên mỗi database?

Giả sử hai pipeline chạy gần như đồng thời:

- Pipeline A triển khai release 2.4, thêm cột orders.status.
- Pipeline B triển khai hotfix 2.4.1, tạo index trên orders.status.
- Cả hai cùng đọc trạng thái changelog trước khi có migration nào hoàn tất.
- Pipeline B có thể bắt đầu khi cột status chưa tồn tại; hoặc một công cụ khác chạy DDL trong khi A đang cập nhật.
- Kết quả có thể là lỗi thiếu cột, lock conflict, partial execution hoặc báo cáo release không phản ánh đúng thứ tự.

Các tình huống thực tế thường gặp:

1. Hai lần chạy CI/CD được kích hoạt bởi hai lần merge hoặc release gần nhau.
2. Một pipeline production và một pipeline hotfix cùng nhắm đến một database.
3. Hai repository khác nhau cùng quản lý schema dùng chung.
4. Nhiều replica Spring Boot khởi động và tự chạy Liquibase.
5. Một người vận hành chạy CLI trong lúc pipeline đang update.
6. Một job rollback chạy đồng thời với job update.
7. Một orchestrator chạy nhiều tenant schema trên cùng database vật lý.
8. Hai URL khác nhau thực chất trỏ đến cùng một database qua proxy hoặc DNS alias.

Nếu không có cơ chế điều phối chung, việc mỗi pipeline tự kiểm tra trạng thái rồi chạy update là chưa đủ. Hai tiến trình có thể cùng vượt qua preflight trước khi một bên kịp ghi lịch sử.

**Một tác vụ migration tại một thời điểm** giúp bảo đảm thứ tự thay đổi rõ ràng, giảm cạnh tranh DDL và giữ lịch sử triển khai có thể truy vết.

## 2. Phân biệt ba lớp điều phối

Không nên kỳ vọng một cơ chế khóa duy nhất giải quyết mọi tình huống. Một kiến trúc an toàn thường có ba lớp:

| Lớp | Phạm vi bảo vệ | Cơ chế thường dùng |
|---|---|---|
| **CI/CD concurrency** | Các job trong cùng workflow/repository hoặc phạm vi mà nền tảng hỗ trợ | Concurrency group, resource group, lockable resource |
| **Database-level migration lock** | Các tiến trình Liquibase cùng sử dụng một bảng DATABASECHANGELOGLOCK | Liquibase lock service |
| **Global orchestration lock** | Nhiều pipeline/repository, công cụ hoặc schema metadata khác nhau cùng nhắm đến một database | Lock service tập trung, advisory lock hoặc lock registry |

Sự phối hợp giữa ba lớp quan trọng hơn việc bật tất cả một cách độc lập:

- CI/CD giúp xếp hàng job và tránh khởi chạy nhiều lần không cần thiết.
- Liquibase DATABASECHANGELOGLOCK bảo vệ những tiến trình Liquibase dùng chung lock table.
- Global lock bảo vệ chính sách một migration trên database ngay cả khi các tiến trình sử dụng metadata schema hoặc công cụ khác nhau.

Một migration owner nên nắm quyền từ lúc bắt đầu bước thay đổi cho đến khi xác minh xong kết quả. Nếu chỉ khóa trong lúc gọi liquibase update nhưng bỏ khóa trước postflight, một pipeline khác có thể bắt đầu thay đổi tiếp trong khi tác vụ trước vẫn đang xác minh trạng thái.

## 3. DATABASECHANGELOGLOCK hoạt động thế nào?

Liquibase sử dụng bảng **DATABASECHANGELOGLOCK** để điều phối các lần thực thi migration trên cùng phạm vi metadata lock. Bảng mặc định thường có một dòng khóa, với các thông tin như ID của lock record, trạng thái LOCKED, thời điểm lock được cấp và thông tin tiến trình/host giữ lock.

Khi một lệnh thay đổi như update cần thực thi, Liquibase cố gắng lấy lock. Nếu một tiến trình khác đã giữ lock, tiến trình sau sẽ chờ theo chính sách cấu hình hoặc kết thúc khi hết thời gian chờ.

~~~text
Liquibase process A             Liquibase process B
        |                               |
        v                               v
  Request lock                    Request lock
        |                               |
        v                               v
  Lock available?                 Lock already held
        |                               |
        v                               v
  Acquire lock                    Wait / poll
        |
        v
  Execute changesets
        |
        v
  Record history
        |
        v
  Release lock
                                        |
                                        v
                                  Acquire lock
                                        |
                                        v
                                  Execute pending work
~~~

Lock này giúp các tiến trình Liquibase cùng dùng một bảng khóa không đồng thời sở hữu lượt update. Nó không tự khóa toàn bộ database khỏi mọi DDL bên ngoài Liquibase.

### Phạm vi của lock table

Một điểm dễ bỏ sót là **DATABASECHANGELOGLOCK có phạm vi theo chính bảng metadata mà Liquibase được cấu hình sử dụng**.

Nếu hai pipeline cùng kết nối một database nhưng cấu hình khác liquibaseSchemaName, khác databaseChangeLogLockTableName hoặc dùng hai bộ metadata độc lập, chúng có thể không tranh cùng một lock record. Tương tự, một công cụ migration khác như Flyway hoặc SQL thủ công không tự động tuân theo DATABASECHANGELOGLOCK.

Nếu chính sách yêu cầu một tác vụ trên toàn database, cần bảo đảm mọi luồng migration cùng dùng một lock domain hoặc phải có global lock bên ngoài Liquibase.

### DATABASECHANGELOG và DATABASECHANGELOGLOCK có vai trò khác nhau

- **DATABASECHANGELOG** lưu lịch sử changeset đã được ghi nhận.
- **DATABASECHANGELOGLOCK** điều phối quyền thực thi migration tại một thời điểm.

Không xóa hoặc sửa DATABASECHANGELOG để giải quyết lock. Không dùng clear-checksums như cách giải phóng lock. Hai bảng có mục đích và quy trình xử lý riêng.

## 4. Chuẩn hóa danh tính database để tạo lock key

Global lock chỉ có tác dụng nếu mọi pipeline nhận ra rằng chúng đang nhắm đến cùng một database.

Không nên tạo lock key chỉ từ chuỗi JDBC URL. Cùng một database có thể được truy cập bằng DNS alias khác nhau, proxy hoặc load balancer khác nhau, hostname nội bộ và hostname managed service, connection string có tham số khác nhau hoặc tài khoản migration khác nhau.

Hãy dùng một **database identity** ổn định từ inventory/hạ tầng:

~~~yaml
database_identity:
  platform: postgres
  environment: production
  cluster_id: pg-commerce-prod-01
  database_name: commerce
~~~

Lock key có thể được chuẩn hóa thành:

~~~text
migration:postgres:production:pg-commerce-prod-01:commerce
~~~

Không đưa username, password, token hoặc URL chứa secret vào lock key.

### Chọn đúng độ hạt khóa

| Tình huống | Khóa nên dùng |
|---|---|
| Một database PostgreSQL, nhiều schema nghiệp vụ | Khóa ở mức database nếu policy yêu cầu chỉ một migration trên database |
| Schema-per-tenant trong cùng database | Khóa database chung nếu DDL có thể ảnh hưởng cùng tài nguyên hoặc quy tắc yêu cầu tuần tự |
| Database-per-tenant, mỗi tenant là database độc lập | Khóa riêng theo database; có thể chạy song song giữa các database |
| Nhiều database dùng chung một cluster, migration tiêu tốn tài nguyên lớn | Cân nhắc thêm giới hạn ở mức cluster |
| DDL tác động tài nguyên toàn instance | Cân nhắc khóa ở mức instance/server theo runbook |

Không gộp mọi database vào một khóa toàn hệ thống nếu chúng có thể triển khai độc lập; điều đó làm giảm throughput không cần thiết. Ngược lại, không dùng schema làm lock key khi yêu cầu thực tế là tuần tự hóa toàn database.

Nếu một endpoint có thể chuyển hướng giữa primary/replica hoặc failover cluster, identity phải đại diện cho logical database/cluster ổn định, không phải IP tạm thời của node.

## 5. Khi nào DATABASECHANGELOGLOCK là đủ?

Lock của Liquibase thường đủ để tuần tự hóa những lần chạy Liquibase nếu tất cả tiến trình:

1. Kết nối cùng một database vật lý.
2. Dùng cùng schema và cùng bảng DATABASECHANGELOGLOCK.
3. Không có cấu hình metadata độc lập làm tách lock domain.
4. Dùng phiên bản Liquibase có hành vi lock tương thích.
5. Không có công cụ khác thay đổi schema mà bỏ qua lock table.

Ví dụ, hai pipeline cùng chạy một master changelog và dùng chung liquibaseSchemaName, databaseChangeLogLockTableName sẽ tranh cùng lock record.

Tuy nhiên, lock table không bảo đảm:

- Một pipeline rollback không chạy song song với công cụ DDL thủ công.
- Flyway hoặc tool khác tự chờ Liquibase lock.
- Hai schema tenant có metadata riêng tự tuần tự hóa ở mức database.
- Job CI/CD thứ hai không bắt đầu các bước chuẩn bị hoặc postflight cùng lúc.
- Một tác vụ được phép chạy trên đúng database mục tiêu.
- Fairness/FIFO giữa các job chờ.

Vì vậy, khi tổ chức có nhiều repository, nhiều công cụ hoặc schema metadata tách biệt, cần global lock ở tầng điều phối.

## 6. Thiết kế global migration lock

Global lock có thể được triển khai bằng một trong các cơ chế:

- Lockable resource của nền tảng CI/CD.
- Distributed lock service dùng chung giữa repository.
- Advisory lock của DBMS.
- Bảng registry/lease được quản lý nguyên tử.
- Một migration orchestrator duy nhất nhận và xử lý yêu cầu.

Dù chọn cách nào, cơ chế cần đáp ứng:

- **Exclusive ownership:** chỉ một owner được cấp quyền tại một thời điểm.
- **Stable key:** mọi pipeline tạo cùng lock key cho cùng database.
- **Bounded wait:** có thời hạn chờ hoặc chính sách queue rõ ràng.
- **Owner identity:** ghi nhận job/execution ID và release commit.
- **Safe release:** giải phóng khi hoàn tất hoặc khi đã xác minh tiến trình cũ dừng.
- **Crash handling:** có quy trình xử lý owner mất kết nối.
- **Auditability:** có lịch sử acquire, release, timeout và recovery.
- **Cross-tool coverage:** mọi đường migration bắt buộc phải tuân theo lock.

Một lock registry khái niệm có thể chứa:

| Trường | Mục đích |
|---|---|
| lock_key | Database identity đã chuẩn hóa |
| owner_id | Pipeline/job/execution đang giữ quyền |
| acquired_at | Thời điểm lấy lock |
| heartbeat_at | Lần cập nhật trạng thái gần nhất |
| lease_until | Thời hạn lease nếu dùng lease |
| fencing_token | Số thứ tự tăng dần để nhận diện owner mới |
| release_id | Release hoặc hotfix đang triển khai |
| status | HELD, RELEASED, EXPIRED, RECOVERY_REQUIRED |

Đây là mô hình logic; không phải bảng Liquibase mặc định. Nếu tự xây dựng, việc acquire phải nguyên tử, ví dụ dùng unique key và transaction/conditional update, không làm theo kiểu SELECT thấy trống rồi INSERT mà không có ràng buộc cạnh tranh.

### Lease và fencing token

Lease giúp phát hiện owner đã ngừng heartbeat, nhưng lease hết hạn không chứng minh tiến trình cũ đã dừng DDL. Một worker có thể bị pause, lease hết hạn, rồi tiếp tục chạy khi worker mới đã nhận quyền.

Với hệ thống dùng lease, cần fencing token tăng dần hoặc một cơ chế tương đương để ngăn owner cũ tiếp tục tác động sau khi quyền đã chuyển giao. Vì Liquibase không tự động gắn fencing token vào mọi câu DDL, orchestrator phải kiểm soát tiến trình và xác minh worker cũ đã kết thúc trước khi cấp quyền mới. Với DDL dài, session-level advisory lock hoặc lock giữ bằng kết nối sống có thể phù hợp hơn lease thuần túy.

## 7. Khóa CI/CD theo database

Nền tảng CI/CD thường cung cấp concurrency group hoặc resource lock. Tên và phạm vi của cơ chế phụ thuộc sản phẩm; hãy kiểm tra nó có được chia sẻ giữa workflow, branch, repository hoặc project hay không.

Ví dụ cấu hình khái niệm:

~~~yaml
migration_job:
  concurrency:
    group: migration-DATABASE_LOCK_KEY
    cancel-in-progress: false
  steps:
    - validate-changelog
    - acquire-global-database-lock
    - verify-target-again
    - liquibase-update
    - postflight
    - release-global-database-lock
~~~

Đây là pseudo-configuration để minh họa thứ tự, không phải cú pháp dùng trực tiếp cho mọi CI/CD provider.

Ví dụ với GitHub Actions có thể dùng concurrency group ở job:

~~~yaml
jobs:
  migrate-production:
    concurrency:
      group: liquibase-production-commerce
      cancel-in-progress: false
    runs-on: ubuntu-latest
    steps:
      - name: Run database migration
        run: ./scripts/migrate-production.sh
~~~

Cần lưu ý concurrency group của một provider có thể chỉ áp dụng trong phạm vi repository và có quy tắc xử lý pending job riêng. Nó không tự động khóa một database nếu một repository khác hoặc một người vận hành chạy CLI ngoài phạm vi đó. Không coi CI concurrency là global lock khi chưa xác minh phạm vi.

### Không hủy job đang giữ lock một cách tùy tiện

Đặt cancel-in-progress false giúp tránh việc một release mới tự động hủy job migration đang chạy trong một số nền tảng. Nếu cần hủy thủ công, người vận hành phải biết DDL hiện tại có thể bị ngắt an toàn hay không.

Job bị cancel không đồng nghĩa database rollback. Với DDL implicit commit hoặc changeset runInTransaction false, một phần thay đổi có thể đã có hiệu lực.

## 8. Quy trình acquire → verify → migrate → postflight → release

Một tác vụ migration nên tuân theo một vòng đời nhất quán:

~~~text
Pipeline được kích hoạt
       |
       v
Resolve canonical database identity
       |
       v
Queue / acquire global lock
       |
       v
Verify lock owner + target identity
       |
       v
Re-run critical preflight
       |
       v
Acquire / confirm Liquibase lock
       |
       v
Execute one mutating Liquibase task
       |
       v
Verify DATABASECHANGELOG + schema + data
       |
       v
Record result and evidence
       |
       v
Release Liquibase lock (Liquibase-managed)
       |
       v
Release global lock
       |
       v
Allow next queued task
~~~

### Vì sao cần kiểm tra lại sau khi lấy lock?

Một preflight chạy trước khi vào queue có thể trở nên lỗi thời trong lúc chờ. Một pipeline khác có thể đã triển khai changeset hoặc thay đổi dữ liệu trước khi job hiện tại nhận được quyền.

Vì vậy:

- Có thể chạy kiểm tra tĩnh và validate changelog trước queue.
- Sau khi acquire lock, xác minh lại database identity, DATABASECHANGELOG, checksum, pending changesets và các data precondition quan trọng.
- Chỉ thực thi khi trạng thái vẫn khớp với kế hoạch đã review.

### Giữ khóa trong bao lâu?

Giữ global lock xuyên suốt giai đoạn có thể làm thay đổi database và postflight bắt buộc. Không giải phóng ngay sau khi process Liquibase trả mã 0 nếu còn bước xác minh quyết định release có thành công hay không.

Không nhất thiết giữ khóa trong toàn bộ cửa sổ observation dài sau khi database đã được xác minh và không còn thao tác migration. Cửa sổ quan sát ứng dụng có thể tiếp tục sau khi quyền migration được giải phóng, nếu chính sách cho phép migration kế tiếp.

## 9. Phân biệt migration task với các lệnh chỉ đọc

Không phải mọi lệnh Liquibase đều cần độc quyền migration lock ở cùng mức.

| Lệnh/hoạt động | Có thay đổi database hoặc metadata? | Cách điều phối |
|---|---|---|
| update | Có | Bắt buộc migration lock |
| rollback / rollback theo tag/count/date | Có | Bắt buộc migration lock |
| changelog-sync | Có, ghi nhận history | Bắt buộc migration lock |
| mark-next-changeset-ran | Có, cập nhật history | Bắt buộc migration lock |
| clear-checksums | Có, thay đổi metadata checksum | Bắt buộc kiểm soát độc quyền và approval |
| tag | Có, cập nhật metadata history | Điều phối theo chính sách release |
| release-locks | Có, thay đổi lock metadata | Chỉ dùng trong recovery có kiểm soát |
| diff / snapshot | Chủ yếu đọc metadata | Có thể chạy read-only, giới hạn tải |
| status / validate | Chủ yếu đọc/chạy kiểm tra | Có thể chạy trước queue; lặp lại critical checks sau lock |
| update-sql / rollback SQL preview | Sinh SQL dự kiến, không áp dụng DDL | Có thể review trước, cần đúng target/config |

Danh sách trên mô tả cách phân loại vận hành; kiểm tra hành vi cụ thể theo phiên bản và cấu hình. Một số lệnh đọc có thể tạo metadata hoặc có side effect tùy cách dùng; xác minh trước khi đưa vào nhóm read-only.

**Không cho phép một lệnh chỉ đọc dùng chung lock như thể nó là migration** nếu điều đó gây queue không cần thiết. Nhưng cũng không cho phép một lệnh ghi history chạy ngoài cơ chế điều phối chỉ vì nó không tạo bảng/cột.

## 10. Một database, nhiều schema và metadata Liquibase riêng

Một database PostgreSQL có thể chứa nhiều schema tenant:

~~~text
commerce
  |
  +-- tenant_a
  |     +-- orders
  |     +-- databasechangelog
  |     +-- databasechangeloglock
  |
  +-- tenant_b
  |     +-- orders
  |     +-- databasechangelog
  |     +-- databasechangeloglock
  |
  +-- tenant_c
        +-- orders
        +-- databasechangelog
        +-- databasechangeloglock
~~~

Mỗi schema có bảng DATABASECHANGELOGLOCK riêng, vì vậy Liquibase có thể cho phép một tiến trình chạy trên tenant_a và một tiến trình khác chạy trên tenant_b cùng lúc.

Điều này hợp lý nếu chính sách cho phép migration song song và các thay đổi độc lập. Nhưng nếu yêu cầu là **chỉ một migration trên toàn database**, hai lock table riêng không đáp ứng. Cần thêm khóa ngoài với key ở mức database, hoặc dùng một lock table chung cho tất cả các tác vụ có cùng database scope.

Không nên thay đổi liquibaseSchemaName sang một schema chung chỉ để ép tuần tự nếu điều đó làm trộn lịch sử DATABASECHANGELOG giữa các tenant. Có thể dùng một global mutex riêng để tuần tự hóa, trong khi mỗi tenant vẫn giữ DATABASECHANGELOG độc lập.

Với database-per-tenant, mỗi database có thể có một lock key riêng. Nền tảng có thể chạy song song giữa các database độc lập, nhưng vẫn giới hạn concurrency toàn cluster để bảo vệ tài nguyên.

## 11. Nhiều repository hoặc nhiều công cụ cùng quản lý database

CI concurrency ở một repository không đủ nếu có nhiều nguồn triển khai:

- Repository của service billing.
- Repository của service order.
- Repository platform/DBA.
- Job vận hành thủ công.
- Spring Boot startup migration.
- Flyway hoặc một công cụ DDL khác.

Tất cả phải tuân theo cùng chính sách khóa database. Có thể triển khai một migration gateway/orchestrator làm cổng duy nhất: các pipeline gửi yêu cầu, gateway xác thực release và lấy lock, sau đó chạy công cụ tương ứng.

Nếu không có gateway, cần quy ước chung về lock key và một dịch vụ lock dùng chung. Các job thủ công cũng phải lấy cùng khóa hoặc được thực hiện trong maintenance window có freeze các pipeline khác.

Không giả định công cụ khác sẽ đọc DATABASECHANGELOGLOCK. Nếu Flyway và Liquibase cùng thay đổi một database, cần global lock ở tầng cao hơn hoặc phân chia ownership rõ ràng theo schema/object và chính sách triển khai.

## 12. Sử dụng advisory lock của DBMS

Một số DBMS có application/advisory lock cho phép ứng dụng giữ một khóa logic mà không cần tạo bảng riêng.

| DBMS | Cơ chế tham khảo | Lưu ý |
|---|---|---|
| PostgreSQL | pg_advisory_lock / pg_try_advisory_lock | Có session-level và transaction-level; khóa gắn với session/database theo semantics của hàm |
| MySQL | GET_LOCK / RELEASE_LOCK | Named lock gắn với session; cần giữ đúng connection và đặt tên có namespace |
| SQL Server | sp_getapplock / sp_releaseapplock | Resource lock có owner mode; xem database principal và lock owner |
| Oracle | DBMS_LOCK | Cần quyền và cấu hình phù hợp; semantics phụ thuộc cách sử dụng |

Đây là các cơ chế DBMS-specific, không phải cú pháp Liquibase portable. Trước khi dùng, DBA cần xác minh quyền, timeout, phạm vi khóa, session lifecycle, failover và cách release.

### Ví dụ PostgreSQL

Một session có thể thử lấy advisory lock:

~~~sql
SELECT pg_try_advisory_lock(741205, 1);
~~~

Nếu trả true, session đã lấy được khóa; false nghĩa là khóa đang được session khác giữ. Khi hoàn tất:

~~~sql
SELECT pg_advisory_unlock(741205, 1);
~~~

Ví dụ dùng hai số khóa cố định để minh họa. Trong hệ thống thật, cần ánh xạ canonical database identity sang khóa không va chạm và có quy ước namespace. Không dùng một cặp số tùy tiện cho mọi database nếu khóa có thể va chạm.

Advisory lock session-level phải được giữ trên **cùng session/connection** trong suốt khoảng cần khóa. Nếu connection bị đóng, lock được giải phóng theo semantics PostgreSQL. Vì Liquibase CLI thường mở connection riêng, một orchestrator có thể giữ advisory lock bằng connection riêng trong khi chạy Liquibase; cần bảo đảm orchestrator không mất session và kiểm soát được process Liquibase. Nếu dùng connection pool, không trả connection giữ lock về pool trước khi release.

Không giữ transaction-level lock rồi commit sớm nếu muốn khóa tồn tại suốt migration. Hãy chọn loại lock theo thời gian sống mong muốn và thử failure path.

## 13. Tránh deadlock giữa các lớp lock

Nếu pipeline phải lấy cả CI lock, global DB lock và Liquibase lock, mọi job cần lấy theo cùng một thứ tự. Ví dụ:

1. CI concurrency/resource group.
2. Global lock theo canonical database identity.
3. Liquibase DATABASECHANGELOGLOCK.

Không có job nào lấy Liquibase lock trước rồi chờ global lock trong khi job khác giữ global lock và chờ Liquibase lock. Thứ tự ngược nhau có thể tạo vòng chờ.

Một số nguyên tắc:

- Quy định một thứ tự acquire thống nhất trong runbook.
- Release theo thứ tự ngược lại.
- Không giữ khóa database trong lúc chờ phê duyệt thủ công kéo dài.
- Nếu phải pause, xác định rõ có thể release lock và chạy lại preflight hay không.
- Dùng timeout có giới hạn ở mỗi lớp.
- Ghi nhận owner và thời điểm lấy từng lock.
- Không dùng một session lock làm bằng chứng cho một job khác không còn kiểm soát.

Nếu job chỉ chạy validate/update-sql, có thể hoàn thành các bước đó trước khi lấy global lock. Sau khi nhận khóa, chạy lại kiểm tra trạng thái quan trọng và mới thực thi update.

## 14. Timeout, queue và xử lý job chờ

Một job chờ lock cần có chính sách rõ:

- **Queue:** giữ job trong hàng đợi và chạy theo thứ tự/ưu tiên đã định.
- **Wait with timeout:** chờ trong một khoảng thời gian tối đa.
- **Fail fast:** kết thúc sớm và báo database đang bận.
- **Coalesce:** gộp nhiều yêu cầu cùng release nếu việc đó an toàn và có audit.

Không để job chờ vô hạn mà không có trạng thái. Một release mới có thể hết hạn hoặc bị thay thế khi vẫn còn trong queue.

### Chọn timeout hợp lý

Timeout cần xét thời gian migration p50/p95 của database, cửa sổ triển khai, số job đang chờ, SLA của release và thời gian có thể chờ trước khi cần hủy hoặc escalation.

Liquibase có tham số cấu hình thời gian chờ lock ở một số phiên bản. Tên tham số và đơn vị cần kiểm tra bằng liquibase --help hoặc tài liệu đúng phiên bản; không hard-code tùy chọn từ phiên bản khác.

Nếu hết timeout:

1. Không chạy DDL.
2. Ghi lock key, owner hiện tại và thời gian chờ.
3. Giữ job ở trạng thái QUEUED/LOCK_TIMEOUT hoặc kết thúc theo policy.
4. Thông báo owner đang giữ lock.
5. Không tự release lock của job khác.

## 15. Recovery khi lock bị giữ sau sự cố

Một job có thể crash, runner bị mất kết nối hoặc process bị kill. DATABASECHANGELOGLOCK hoặc global lock có thể còn trạng thái đang giữ.

Trước khi giải phóng:

1. Xác định owner ID, lockedBy và thời điểm lock được cấp.
2. Kiểm tra pipeline/job tương ứng còn chạy không.
3. Kiểm tra session database và statement đang hoạt động.
4. Đọc log Liquibase để xác định changeset cuối cùng.
5. Đối chiếu DATABASECHANGELOG với schema/data thực tế.
6. Xác nhận process cũ đã kết thúc và không thể tiếp tục DDL.
7. Chỉ sau đó mới dùng recovery command phù hợp.
8. Chạy lại preflight và reconcile trước khi retry.

Liquibase CLI cung cấp các lệnh như list-locks và release-locks trong các phiên bản hỗ trợ. Kiểm tra cú pháp/version trước khi chạy. release-locks là thao tác quản trị lock, không phải lệnh dọn dẹp định kỳ.

**Không sửa tay LOCKED=false** khi chưa xác minh owner. Nếu process cũ vẫn chạy, việc giải phóng lock có thể cho phép tiến trình mới chạy đồng thời.

Nếu DDL đã commit nhưng DATABASECHANGELOG chưa ghi nhận, cần kiểm tra object thực tế và xác định changeset có thể chạy lại an toàn không. Không retry mù chỉ vì pipeline trước có exit code khác 0.

## 16. Quy trình xử lý khi job bị cancel

Cancel có thể đến từ người vận hành, timeout CI, runner shutdown hoặc chính sách concurrency của nền tảng.

Khi cancel:

- Ghi nhận job ID và thời điểm.
- Xác định Liquibase đang ở changeset nào.
- Kiểm tra session database còn hoạt động không.
- Kiểm tra DDL có transactional, implicit commit hoặc non-transactional không.
- Xem DATABASECHANGELOG và metadata object.
- Phân loại trạng thái: không có tác động, hoàn tất, partial failure hoặc chưa rõ.
- Đánh dấu RECONCILIATION_REQUIRED nếu chưa thể kết luận.
- Chỉ cấp lock cho job kế tiếp sau khi tiến trình cũ được xác nhận đã dừng an toàn.

Không dùng cancel-in-progress để thay thế lock. Một pipeline mới đến không nên hủy job migration hiện tại chỉ vì nó mới hơn.

## 17. Tích hợp Spring Boot: một migration owner

Spring Boot có thể tự chạy Liquibase khi ứng dụng khởi động. Nếu production có nhiều replica, mỗi replica có thể cố khởi tạo migration. DATABASECHANGELOGLOCK có thể tuần tự hóa các lần chạy dùng chung lock table, nhưng nhiều instance vẫn tạo ra startup contention và khó kiểm soát thứ tự release.

Hai mô hình phổ biến:

### Mô hình A — CI/CD sở hữu migration

- Pipeline chạy Liquibase một lần cho target.
- Ứng dụng production không tự chạy migration.
- Sau khi postflight đạt, pipeline mới triển khai hoặc mở traffic ứng dụng.
- Quyền DDL chỉ cấp cho migration job.

Cấu hình Spring Boot minh họa:

~~~yaml
spring:
  liquibase:
    enabled: false
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Ứng dụng không tự chạy migration trong profile này; pipeline sở hữu việc update. ddl-auto validate chỉ kiểm tra mapping theo cấu hình Hibernate, không thay thế Liquibase validation hoặc postflight SQL.

### Mô hình B — Một startup owner có điều phối

- Chỉ một instance/job được quyền kích hoạt migration.
- Các replica khác chờ readiness hoặc chỉ khởi động sau khi schema sẵn sàng.
- Cơ chế leader election/lock phải có owner rõ ràng.
- Không để mọi replica cùng tự quyết định chạy một release không được điều phối.

Mô hình A thường dễ audit và tích hợp approval hơn cho production. Mô hình B có thể phù hợp với hệ thống đã có startup coordination được kiểm chứng. Không để cả pipeline và Spring Boot cùng là migration owner ngoài kế hoạch.

## 18. CI/CD mẫu với global lock và Liquibase lock

Một job minh họa theo dạng pseudo pipeline:

~~~yaml
jobs:
  migrate:
    steps:
      - name: Validate changelog
        run: liquibase validate

      - name: Preview SQL
        run: liquibase update-sql

      - name: Acquire database lock
        run: migration-lock acquire DATABASE_LOCK_KEY

      - name: Verify target and history again
        run: ./scripts/migration-preflight.sh

      - name: Execute migration
        run: liquibase update

      - name: Postflight
        run: ./scripts/migration-postflight.sh

      - name: Record release evidence
        run: ./scripts/record-migration-result.sh

      - name: Release database lock
        if: always()
        run: migration-lock release DATABASE_LOCK_KEY
~~~

Đây là cấu trúc minh họa; lệnh migration-lock đại diện cho dịch vụ khóa do tổ chức cung cấp, không phải lệnh Liquibase tích hợp sẵn.

Trong triển khai thật:

- Dùng secret manager cho credentials.
- Bảo đảm bước release chỉ giải phóng lock do execution hiện tại sở hữu.
- Dùng owner token để tránh job cũ release lock của job mới.
- Nếu job bị kill cứng và không chạy được finally/always, lock service phải có recovery path.
- Không bỏ qua postflight chỉ vì update trả mã 0.
- Nếu postflight FAIL, ghi trạng thái BLOCKED/RECONCILIATION_REQUIRED và xử lý theo runbook.

Một số CI provider hỗ trợ điều kiện always/finally; vẫn cần xác minh behavior khi runner mất hoàn toàn hoặc bị terminate.

## 19. Tác vụ update, rollback và metadata đều phải tuân thủ lock

Chính sách single-writer không chỉ dành cho liquibase update.

Các hoạt động có thể thay đổi database hoặc metadata gồm:

- update.
- rollback theo tag, count, date hoặc release.
- changelog-sync.
- mark-next-changeset-ran.
- clear-checksums.
- tag hoặc thao tác cập nhật metadata history.
- release-locks trong quy trình recovery.
- Các lệnh DDL thủ công hoặc công cụ migration khác.

Nếu rollback chạy đồng thời update, hai tác vụ có thể làm thay đổi schema và history theo thứ tự không xác định. Nếu changelog-sync chạy trong lúc update, DATABASECHANGELOG có thể ghi nhận trạng thái không khớp ý định.

Mọi thao tác quản trị metadata cần có owner, approval và audit. Không chạy clear-checksums như một bước tự động khi pipeline phát hiện mismatch; đó là thay đổi lịch sử cần điều tra và kiểm soát.

## 20. Locking trong database-per-tenant và schema-per-tenant

### Database-per-tenant

Mỗi tenant có database riêng. Nếu mỗi database là một đơn vị độc lập, lock key có thể là tenant database identity. Nền tảng cho phép chạy song song giữa các database nhưng giới hạn concurrency toàn cluster.

~~~text
tenant_a -> lock: db/commerce_a
tenant_b -> lock: db/commerce_b
tenant_c -> lock: db/commerce_c
~~~

Một job cho tenant_a không cần chặn tenant_b nếu không có tài nguyên dùng chung hoặc policy cluster-wide yêu cầu giới hạn.

### Schema-per-tenant

Các tenant dùng chung một database nhưng có schema riêng. Nếu mỗi schema dùng DATABASECHANGELOGLOCK riêng, Liquibase có thể chạy song song. Nếu yêu cầu chỉ một migration trên toàn database, global lock key phải bỏ phần schema và dùng database identity chung:

~~~text
tenant_a -> lock: db/commerce
tenant_b -> lock: db/commerce
tenant_c -> lock: db/commerce
~~~

Như vậy mọi tenant cùng xếp hàng ở một khóa database. Lịch sử DATABASECHANGELOG vẫn có thể độc lập theo tenant schema.

Nếu tổ chức cho phép song song có kiểm soát, có thể dùng lock theo schema cộng thêm semaphore giới hạn số job trên database. Đây là quyết định về policy, không phải hành vi mặc định của Liquibase.

## 21. Kiểm thử cơ chế khóa trước khi dùng production

Không chỉ kiểm tra một job chạy thành công. Cần chứng minh hai job cạnh tranh không thể cùng thực thi migration trên cùng database.

### Test 1 — Hai pipeline cùng database

1. Khởi chạy pipeline A và giữ lock trong môi trường test.
2. Khởi chạy pipeline B với cùng database identity.
3. Xác nhận B ở trạng thái queued/waiting hoặc fail-fast theo policy.
4. Xác nhận chỉ A chạy DDL.
5. A hoàn tất postflight và release.
6. B mới được acquire và chạy preflight lại.

Kết quả mong đợi: không có khoảng thời gian hai owner cùng sở hữu database lock.

### Test 2 — Hai URL, cùng database vật lý

1. Cấu hình URL A qua hostname chính.
2. Cấu hình URL B qua alias/proxy.
3. Cả hai resolve về cùng canonical database identity.
4. Khởi chạy đồng thời.
5. Xác nhận chúng dùng cùng lock key.

Kết quả mong đợi: alias không tạo ra hai khóa độc lập.

### Test 3 — Cùng database, metadata schema khác nhau

1. Chạy hai Liquibase config với liquibaseSchemaName khác nhau.
2. Xác nhận DATABASECHANGELOGLOCK độc lập không ngăn được nhau.
3. Bật global database lock.
4. Chạy lại và xác nhận chỉ một job được thực thi.

Kết quả mong đợi: chứng minh global lock bù được phạm vi giới hạn của Liquibase lock.

### Test 4 — Hai database độc lập

1. Chạy migration cho database A và B với hai lock key riêng.
2. Xác nhận cả hai có thể chạy song song nếu policy cho phép.
3. Kiểm tra giới hạn concurrency cấp cluster.

Kết quả mong đợi: không tuần tự hóa quá mức các database độc lập.

### Test 5 — Crash hoặc cancel

1. Dừng worker trong lúc migration đang chạy trên database test.
2. Kiểm tra owner, session, DATABASECHANGELOGLOCK và object.
3. Xác nhận job mới không được cấp lock khi worker cũ còn có thể chạy.
4. Reconcile trạng thái và thực hiện recovery.
5. Retry sau khi có bằng chứng.

Kết quả mong đợi: không giải phóng lock mù và không chạy DDL chồng lấn.

### Test 6 — Manual migration và công cụ khác

Thử chạy một tác vụ DBA hoặc công cụ migration khác trong lúc pipeline giữ global lock. Xác nhận quy trình tổ chức yêu cầu tác vụ đó acquire cùng lock hoặc bị chặn theo maintenance policy.

## 22. Quan sát và cảnh báo trạng thái lock

Dashboard vận hành nên có:

- Lock key/canonical database identity.
- Owner ID, repository, pipeline và release ID.
- Thời điểm acquire và thời gian đã giữ.
- Heartbeat/lease status nếu dùng.
- Số job đang chờ.
- Thời gian chờ p50/p95.
- Lock timeout/failure count.
- Thời gian migration thực tế.
- DATABASECHANGELOGLOCK state.
- Tình trạng session DDL và lock wait.
- Recovery hoặc manual release events.

Cảnh báo nên phát khi:

- Lock được giữ lâu hơn thời gian dự kiến.
- Job chờ vượt timeout.
- Owner mất heartbeat nhưng database session còn tồn tại.
- Có nhiều lock domain cho cùng canonical database.
- Có DDL session không thuộc migration owner.
- Lock bị release thủ công.
- Một job bị cancel trong lúc DDL đang chạy.

Không log password, token hoặc connection string có credentials. Thông tin database topology cũng cần được phân quyền.

## 23. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Hai pipeline cùng database vẫn chạy song song | Dùng lock table/schema khác nhau | Chuẩn hóa lock domain hoặc thêm global lock |
| Liquibase báo đang chờ lock | Job khác đang giữ DATABASECHANGELOGLOCK | Xác minh owner và chờ theo policy |
| Pipeline B không chờ pipeline A | CI concurrency chỉ có phạm vi repository | Dùng lock service dùng chung giữa repository |
| URL khác nhau tạo lock key khác nhau | Dùng raw JDBC URL thay canonical identity | Chuẩn hóa DB identity từ inventory |
| Job mới chạy sau khi lease hết hạn nhưng job cũ vẫn sống | Lease không có fencing/recovery | Xác minh session cũ, dùng fencing token hoặc session lock |
| Spring Boot replicas tranh migration | Nhiều instance cùng auto-run Liquibase | Chọn một migration owner |
| release-locks làm hai job cùng chạy | Giải phóng lock khi owner cũ chưa dừng | Kiểm tra process/session trước recovery |
| Rollback chạy cùng update | Chỉ khóa update, bỏ quên rollback | Tất cả lệnh mutating dùng cùng lock |
| Schema-per-tenant chạy đồng thời trái policy | Mỗi tenant có lock table riêng | Thêm global lock ở mức database |
| Job bị cancel nhưng database đã đổi một phần | Giả định cancel đồng nghĩa rollback | Reconcile history và schema trước retry |
| Job chờ vô hạn | Không có timeout/queue policy | Đặt bounded wait và trạng thái rõ |

## 24. Checklist triển khai chính sách single-writer

**Danh tính và phạm vi**

- [ ] Có canonical identity cho database/cluster.
- [ ] Các URL/alias cùng database tạo cùng lock key.
- [ ] Chọn granularity database, schema hay cluster theo policy.
- [ ] Không đưa credentials vào lock key hoặc audit.

**Liquibase**

- [ ] Các pipeline cùng database dùng lock table chung khi phù hợp.
- [ ] liquibaseSchemaName và databaseChangeLogLockTableName được kiểm soát.
- [ ] Hiểu rằng DATABASECHANGELOGLOCK chỉ bảo vệ các tiến trình dùng chung lock table.
- [ ] Không trộn lịch sử tenant chỉ để dùng chung DATABASECHANGELOG.
- [ ] Các lệnh update/rollback/changelog-sync/metadata mutation đều có điều phối.

**CI/CD/orchestrator**

- [ ] Concurrency group có phạm vi được xác minh.
- [ ] Có global lock nếu nhiều repository/công cụ cùng target.
- [ ] Acquire theo thứ tự nhất quán.
- [ ] Có queue hoặc timeout hữu hạn.
- [ ] Có owner ID, release ID và audit.
- [ ] Có lease/fencing hoặc session lock phù hợp.
- [ ] Release chỉ do owner hiện tại thực hiện.
- [ ] Có recovery khi runner crash/cancel.

**Vận hành**

- [ ] Re-run critical preflight sau khi lấy lock.
- [ ] Giữ khóa qua execution và postflight bắt buộc.
- [ ] Không giải phóng stale lock khi session cũ chưa dừng.
- [ ] Reconcile DATABASECHANGELOG và schema trước retry.
- [ ] Theo dõi lock age, wait time và DDL session.
- [ ] Kiểm thử hai pipeline cùng database, alias, metadata schema riêng và crash.
- [ ] Tác vụ DBA/manual và công cụ khác tuân theo cùng policy.

Với **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, chỉ cho phép một tác vụ migration trên cùng cơ sở dữ liệu đòi hỏi xác định đúng database identity và phối hợp cả CI/CD, Liquibase cùng lớp điều phối toàn cục. DATABASECHANGELOGLOCK tuần tự hóa các tiến trình Liquibase dùng chung lock table; concurrency group giảm job cạnh tranh trong phạm vi nền tảng; global lock bảo vệ các pipeline, repository và công cụ khác nhau cùng nhắm đến một database. Khi mọi lệnh thay đổi đều tuân thủ một lock domain, có timeout và recovery an toàn, nhóm giữ được thứ tự migration, tránh DDL chồng lấn và duy trì lịch sử triển khai có thể truy vết.
