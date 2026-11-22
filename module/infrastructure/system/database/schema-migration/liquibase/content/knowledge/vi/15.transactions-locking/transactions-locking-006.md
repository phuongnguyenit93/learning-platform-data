# Nhiều tiến trình cùng khởi chạy migration

Trong môi trường phát triển, ta thường chạy Liquibase một lần rồi khởi động ứng dụng. Nhưng khi triển khai hệ thống thực tế, **nhiều tiến trình có thể cùng cố gắng chạy migration trên một database**: ba replica Spring Boot khởi động đồng thời, một job CI/CD đang chạy trong lúc ứng dụng tự khởi tạo Liquibase, hoặc hai bản phát hành được triển khai gần nhau. Nếu hai tiến trình cùng thêm một cột, tạo một index hay cập nhật dữ liệu mà không có cơ chế điều phối, một tiến trình có thể gặp lỗi đối tượng đã tồn tại, deadlock, dữ liệu trùng hoặc trạng thái nửa hoàn tất.

Liquibase sử dụng **bảng DATABASECHANGELOGLOCK** để phối hợp việc thực thi changelog trên cùng phạm vi lưu khóa. Cơ chế này giúp tuần tự hóa các lần chạy migration tham gia cùng một hệ thống khóa, nhưng **không thay thế chiến lược triển khai ứng dụng, transaction, quản lý phiên bản hay tính tương thích schema**.

Bài học thuộc chương **Giao dịch và khóa** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Trong toàn bộ module, người học quản lý thay đổi schema và dữ liệu với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Ở đây, mục tiêu cụ thể là hiểu điều gì xảy ra khi nhiều tiến trình bắt đầu migration cùng lúc, cách nhận diện lock hợp lệ hay lock tồn đọng, và cách thiết kế pipeline an toàn, có thể quan sát và khôi phục.

## 1. Vì sao nhiều tiến trình cùng chạy là tình huống bình thường?

Một deployment có thể tạo ra nhiều tiến trình độc lập nhưng cùng trỏ đến một database:

- **Ứng dụng nhiều replica:** Kubernetes Deployment tăng từ 1 lên 4 pod; mỗi instance Spring Boot có cấu hình Liquibase chạy lúc startup.
- **Pipeline và ứng dụng chồng nhau:** CI/CD job gọi Liquibase update trong khi bản ứng dụng mới đồng thời khởi động và cũng gọi update.
- **Triển khai cuốn chiếu:** Phiên bản cũ đang phục vụ traffic, phiên bản mới khởi động trên cùng database.
- **Tự động thử lại:** Job migration hết thời gian chờ, orchestrator tạo lần chạy mới, trong khi tiến trình cũ có thể chưa thực sự kết thúc.
- **Nhiều dịch vụ dùng chung schema:** Hai dịch vụ cùng mang changelog hoặc những changeset giao nhau, nhưng không có phân định rõ đơn vị sở hữu.

Trong từng trường hợp, cần phân biệt:

1. **Cạnh tranh chạy Liquibase:** tiến trình nào được áp migration trước, tiến trình nào phải chờ.
2. **Cạnh tranh sử dụng database:** ứng dụng vẫn đọc/ghi dữ liệu trong khi DDL hoặc DML của migration diễn ra.

DATABASECHANGELOGLOCK chủ yếu giải quyết loại thứ nhất. Nó không tự cấm giao dịch nghiệp vụ đang chạy hoặc tự bảo đảm mọi phiên bản ứng dụng tương thích với schema mới.

## 2. Hai bảng nội bộ: DATABASECHANGELOG và DATABASECHANGELOGLOCK

Hai bảng có trách nhiệm khác nhau.

| Bảng | Vai trò chính | Thông tin đáng chú ý |
|---|---|---|
| DATABASECHANGELOG | Lịch sử changeset đã áp dụng | ID, AUTHOR, FILENAME, MD5SUM, DATEEXECUTED, ORDEREXECUTED, EXECTYPE... |
| DATABASECHANGELOGLOCK | Trạng thái khóa ngăn các lần chạy Liquibase xung đột trong cùng phạm vi khóa | ID, LOCKED, LOCKGRANTED, LOCKEDBY |

Trong cấu hình mặc định thường gặp, DATABASECHANGELOGLOCK có một hàng quản lý khóa với ID bằng 1. Khi một tiến trình được cấp khóa, cột LOCKED biểu thị trạng thái đang giữ; LOCKGRANTED và LOCKEDBY hỗ trợ chẩn đoán thời điểm và nguồn giữ khóa. Tên bảng hoặc schema chứa các bảng nội bộ có thể được tùy chỉnh; phải kiểm tra cấu hình thực tế thay vì luôn giả định chúng nằm ở public.

Có thể xem trạng thái trong PostgreSQL bằng truy vấn **chỉ đọc**:

~~~sql
SELECT id, locked, lockgranted, lockedby
FROM databasechangeloglock
ORDER BY id;
~~~

Xem lịch sử changeset:

~~~sql
SELECT id, author, filename, exectype,
       dateexecuted, orderexecuted
FROM databasechangelog
ORDER BY orderexecuted;
~~~

**DATABASECHANGELOGLOCK không đồng nghĩa với row lock/table lock do DBMS áp trên bảng nghiệp vụ.** Một tiến trình có thể sở hữu lock của Liquibase nhưng vẫn phải chờ transaction nghiệp vụ nhả khóa trên bảng orders trước khi thực hiện ALTER TABLE. Ngược lại, bảng khóa Liquibase không ngăn ứng dụng khác tự chạy SQL DDL bên ngoài Liquibase.

## 3. Luồng hai tiến trình chạy cùng một changelog

Giả sử phiên bản ứng dụng có changelog 001-create-customer, 002-add-email, 003-create-index. Hai tiến trình A và B cùng chạy update, cùng dùng một database và cùng bảng khóa Liquibase.

~~~mermaid
sequenceDiagram
    participant A as Tiến trình A
    participant L as DATABASECHANGELOGLOCK
    participant B as Tiến trình B
    participant D as Database
    A->>L: Xin quyền giữ khóa
    L-->>A: Cấp khóa
    B->>L: Xin quyền giữ khóa
    L-->>B: Chưa có khóa, phải chờ
    A->>D: Đọc lịch sử, chạy các changeset còn thiếu
    A->>D: Ghi DATABASECHANGELOG
    A->>L: Giải phóng khóa
    B->>L: Thử lại và được cấp khóa
    B->>D: Đọc trạng thái mới của changeset
    Note over B,D: Các changeset đã áp dụng thường được bỏ qua
    B->>L: Giải phóng khóa
~~~

Diễn tiến logic:

1. A và B yêu cầu quyền chạy migration gần cùng thời điểm.
2. Chỉ một tiến trình được phép giữ khóa Liquibase trong cùng phạm vi khóa; giả sử A thắng.
3. B chờ hoặc cuối cùng báo lỗi nếu vượt chính sách chờ.
4. A kiểm tra lịch sử changeset, áp dụng những thay đổi chưa chạy rồi ghi kết quả vào DATABASECHANGELOG.
5. A giải phóng khóa khi kết thúc theo luồng bình thường.
6. B được phép tiếp tục, kiểm tra lịch sử mới và thông thường không chạy lại những changeset A đã hoàn tất.

Điều trên giả định **cùng danh sách changelog, cùng bộ lọc context/label, cùng cấu hình schema và cùng bảng khóa**. Nếu A và B dùng hai artifact khác nhau, sau khi A hoàn tất B vẫn có thể áp dụng changeset khác hoặc gặp checksum mismatch. Khóa chỉ đảm bảo việc thực thi có phối hợp; nó không chứng minh hai bản phát hành tương thích.

## 4. Phạm vi của khóa: khi nào khóa thực sự bảo vệ?

Phải hiểu phạm vi bảo vệ để không có cảm giác an toàn giả tạo.

**Khóa có hiệu lực khi** những tiến trình Liquibase cùng trỏ đến **cùng hệ thống DATABASECHANGELOGLOCK**, với cơ chế khóa do Liquibase quản lý. Ví dụ ba pod cùng datasource và cùng schema đặt bảng khóa có thể tranh chấp một khóa dùng chung.

**Khóa không tự bảo vệ khi**:

- Hai tiến trình ghi lên hai database khác nhau nhưng người vận hành tưởng là một.
- Hai bộ cấu hình trỏ cùng database ứng dụng nhưng dùng **hai schema hoặc tên bảng khóa khác nhau**.
- Một tool bên ngoài chạy SQL DDL trực tiếp mà không xin khóa của Liquibase.
- Một tiến trình Liquibase giữ khóa trong lúc ứng dụng đang ghi dữ liệu nghiệp vụ.
- Hai nhóm dịch vụ sử dụng các changelog khác nhau, mỗi nhóm có bảng khóa riêng nhưng cùng sửa một nhóm bảng ứng dụng.

Vì vậy, trong hệ thống nhiều dịch vụ, phải có **quyền sở hữu schema và migration** rõ ràng. Không nên giải quyết tranh chấp bằng cách tạo thêm bảng khóa riêng để các pipeline “khỏi phải chờ” trong khi chúng vẫn sửa các đối tượng phụ thuộc lẫn nhau.

## 5. Tình huống Spring Boot: nhiều replica tự chạy Liquibase

Giả sử ứng dụng Spring Boot có cấu hình:

~~~properties
spring.liquibase.enabled=true
spring.liquibase.change-log=classpath:/db/changelog/db.changelog-master.yaml
~~~

Một lần scale từ 1 lên 4 replica có thể khiến cả bốn lần khởi tạo Spring context đều cố chạy Liquibase. Nhờ bảng khóa chung, chúng thường không thực hiện cùng một changeset cùng lúc. Nhưng có các hệ quả vận hành:

- Pod giữ khóa có thể chạy DDL lâu vì bảng lớn.
- Các pod còn lại phải chờ khóa và chưa hoàn tất startup.
- Startup probe hoặc liveness probe đặt không phù hợp có thể khiến pod bị restart liên tục dù migration vẫn đang chạy hợp lệ.
- Một lần restart bị cưỡng bức có thể xảy ra đúng lúc changeset đang thực thi.
- Thời gian rollout có thể tăng đáng kể dù chỉ một tiến trình thực sự cần chạy thay đổi.

**Đừng diễn giải “Liquibase có lock” thành “có thể cho mọi replica tự migration mà không cần thiết kế”.** Cơ chế lock giảm nguy cơ chạy trùng, nhưng không loại bỏ thời gian chờ, rủi ro startup thất bại hay sự thiếu tương thích giữa các phiên bản ứng dụng.

### 5.1. Readiness và liveness không có cùng ý nghĩa

- **Readiness:** ứng dụng đã sẵn sàng nhận traffic hay chưa; thông thường không nên nhận traffic nếu schema bắt buộc chưa sẵn sàng.
- **Liveness:** tiến trình có còn hoạt động hay cần khởi động lại; không nên coi một khoảng chờ migration hợp lệ là ứng dụng đã chết.
- **Startup probe:** trong nền tảng hỗ trợ, có thể cho ứng dụng thời gian khởi tạo trước khi liveness trở nên nghiêm ngặt.

Cần thiết kế thời gian chờ dựa trên migration thực tế và ngân sách rollout, không suy đoán rằng mọi migration đều kết thúc trong vài giây.

## 6. Hai mô hình điều phối deployment phổ biến

### Mô hình A — Ứng dụng tự chạy migration

Mỗi instance có Liquibase tích hợp và cùng cấu hình changelog/database/lock.

~~~text
Replica A ─┐
Replica B ─┼──> DATABASECHANGELOGLOCK ──> migration được tuần tự hóa
Replica C ─┘
~~~

**Ưu điểm:** đơn giản ở dự án nhỏ; ứng dụng mang theo đúng changelog và tự đảm bảo đã kiểm tra migration khi startup.

**Nhược điểm:** nhiều tiến trình cùng tranh khóa; thời gian khởi động phụ thuộc DDL; khó chủ động kiểm soát migration dài; phiên bản ứng dụng được triển khai lệch nhau có thể dùng changelog khác nhau.

Mô hình này phù hợp hơn khi migration nhẹ, số replica ít, schema có tương thích ngược, và nhóm đã thử các trường hợp chờ khóa, restart và failed migration.

### Mô hình B — Một job migration được điều phối trước ứng dụng

Pipeline dùng **một công đoạn migration riêng**, hoàn tất có kiểm chứng rồi mới triển khai các replica ứng dụng. Trong ứng dụng runtime có thể cấu hình:

~~~properties
spring.liquibase.enabled=false
~~~

Trong job riêng, dùng Liquibase CLI hoặc một tiến trình chuyên trách với cùng changelog và thông tin kết nối được cấp quyền phù hợp:

~~~bash
liquibase validate
liquibase status --verbose
liquibase update-sql
liquibase update
~~~

Đây là lệnh minh họa; phải cấu hình đúng changelog, JDBC driver, database URL, tài khoản, context/label và phiên bản Liquibase. Lệnh update thực thi thay đổi thật.

**Ưu điểm:** quyền DDL tập trung; một nơi quan sát log, thời gian chờ và kết quả; ứng dụng không cần tự tranh lock khi khởi động; dễ chèn bước phê duyệt hoặc rollback/forward-fix.

**Nhược điểm:** pipeline phải quản lý rõ dependency “job thành công mới rollout”; cần giải pháp cho migration tương thích ứng dụng cũ đang phục vụ traffic; một job bị thử lại vẫn cần cơ chế lock/lịch sử của Liquibase.

Không phải “một Job” đồng nghĩa với “trên toàn hệ thống chắc chắn chỉ có một lần chạy”. Hai pipeline khác nhau, retry hoặc một job cũ chưa dừng vẫn có thể tồn tại đồng thời. Vì thế cơ chế locking của Liquibase vẫn cần thiết ngay cả khi đã có orchestrator.

## 7. Cách chọn mô hình cho từng tình huống

| Hệ thống | Hướng thường phù hợp | Điểm bắt buộc kiểm tra |
|---|---|---|
| Ứng dụng nhỏ, một instance | Chạy Liquibase lúc startup có thể chấp nhận | Rollback, timeout, startup failure |
| Nhiều replica với migration nhỏ | Có thể chạy tại startup nếu đã kiểm thử tranh khóa | Probe, thời gian chờ, đồng nhất artifact |
| Nhiều replica, index/backfill lớn | Ưu tiên job migration có điều phối | Quyền DDL, I/O, lock DBMS, trạng thái job |
| Nhiều microservice chung schema | Có owner migration duy nhất hoặc quy tắc điều phối rõ | Không chạy hai changelog xung đột |
| Triển khai cuốn chiếu/zero-downtime | Migration tách giai đoạn, tương thích ngược | Phiên bản ứng dụng cũ và mới cùng tồn tại |
| Nhiều môi trường | Mỗi database có lịch sử/khóa riêng, pipeline kiểm soát đích | Không trỏ nhầm production hoặc dùng sai schema |

Dù dùng mô hình nào, cùng một phiên bản phát hành cần dùng changelog được version control, có ID/author/path ổn định và được kiểm thử trên database mới lẫn database đã có lịch sử.

## 8. Khi một tiến trình chờ khóa quá lâu

Không phải mọi trường hợp “đang chờ DATABASECHANGELOGLOCK” đều là lỗi. Có ba kịch bản khác nhau:

1. **Khóa hợp lệ, migration đang tiến triển:** một tiến trình khác vẫn đang tạo index hoặc backfill dữ liệu.
2. **Khóa hợp lệ nhưng migration bị treo/chờ DBMS lock:** tiến trình giữ khóa vẫn tồn tại, nhưng câu lệnh đang chờ transaction khác hoặc bị nghẽn tài nguyên.
3. **Khóa tồn đọng (stale lock):** tiến trình giữ khóa đã dừng bất thường, nhưng trạng thái khóa chưa được dọn theo đường kết thúc bình thường.

Cần xác định kịch bản trước khi hành động. **LOCKED=true không tự chứng minh khóa đã stale.** Một migration lớn hợp lệ có thể giữ khóa lâu hơn thời gian bạn mong đợi.

Thời gian đợi, chu kỳ thử lại và cơ chế timeout phụ thuộc phiên bản/cấu hình Liquibase và cách tích hợp. Khi điều chỉnh những tham số đó, phải tra đúng phiên bản đang chạy và thử hành vi thực tế; không nên sao chép các tên thuộc tính hoặc giá trị mặc định không được kiểm chứng từ một dự án khác.

### 8.1. Khung quyết định xử lý

~~~mermaid
flowchart TD
  A["Ứng dụng/job báo đang chờ Liquibase lock"] --> B["Xem holder và thời điểm cấp khóa"]
  B --> C{"Tiến trình giữ khóa còn hoạt động?"}
  C -->|Có| D["Kiểm tra log, tiến độ, DBMS lock và tải"]
  D --> E{"Migration có tiến triển?"}
  E -->|Có| F["Chờ theo chính sách; tránh khởi động lại vô ích"]
  E -->|Không| G["Điều tra query/transaction bị kẹt; can thiệp theo quy trình"]
  C -->|Không chắc hoặc không| H["Xác minh pod/job/session đã dừng thật"]
  H --> I["Đánh giá trạng thái DDL/DML và lịch sử"]
  I --> J["Chỉ sau xác minh mới cân nhắc release-locks"]
~~~

Mấu chốt là **đánh giá holder và trạng thái database trước khi giải phóng**. Xóa khóa khi tiến trình khác vẫn thực thi DDL có thể cho phép migration thứ hai chạy song song và phá vỡ sự phối hợp ban đầu.

## 9. Chẩn đoán lock bằng CLI và SQL chỉ đọc

Liquibase CLI có các lệnh phục vụ quan sát và quản lý lock, trong nhiều phiên bản phổ biến gồm:

~~~bash
liquibase list-locks
~~~

Lệnh hiển thị trạng thái khóa qua cấu hình kết nối đang dùng. Cần bảo đảm CLI trỏ chính xác cùng database và schema chứa bảng khóa mà ứng dụng đang sử dụng.

Trên PostgreSQL, truy vấn:

~~~sql
SELECT id, locked, lockgranted, lockedby
FROM databasechangeloglock;
~~~

Nếu hệ thống có custom schema/tên bảng, cần thay tên bảng tương ứng. Từ kết quả này, đối chiếu:

- **LOCKED:** có trạng thái giữ khóa hay không?
- **LOCKGRANTED:** thời điểm khóa được cấp; thời gian quá lâu là một tín hiệu điều tra, chưa phải kết luận.
- **LOCKEDBY:** thông tin nhận diện nguồn giữ khóa do Liquibase ghi; có thể không đủ để kết luận process hiện còn chạy.

Sau đó kiểm tra log của pod/job holder, timeline pipeline, các session kết nối đến database, hoạt động truy vấn và lock ở DBMS.

### 9.1. Kiểm tra session và câu lệnh chờ trên PostgreSQL

Với tài khoản được phép quan sát hệ thống:

~~~sql
SELECT pid, usename, application_name, state,
       wait_event_type, wait_event,
       query_start, LEFT(query, 200) AS query_preview
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
~~~

Truy vấn chỉ hỗ trợ điều tra. Không phải mọi user đều thấy đầy đủ query của session khác; trường query_preview có thể chứa literal nhạy cảm, nên kiểm soát việc chia sẻ kết quả.

Nếu phát hiện tiến trình đang chạy ALTER TABLE và chờ lock DBMS, cần tìm transaction chặn và đánh giá tác động, không tự động kill session đang chặn. Việc chấm dứt transaction hoặc migration đòi hỏi thẩm quyền vận hành và phương án khôi phục rõ.

### 9.2. Đối chiếu lịch sử sau một lần chạy bất thường

~~~sql
SELECT id, author, filename, exectype, dateexecuted,
       orderexecuted
FROM databasechangelog
ORDER BY orderexecuted;
~~~

Một changeset chưa xuất hiện trong DATABASECHANGELOG không chắc là nó chưa tác động gì đến database. Trong DBMS có DDL auto-commit hoặc khi dùng runInTransaction=false, thay đổi có thể đã thực hiện một phần rồi tiến trình gặp lỗi trước khi ghi nhận đầy đủ. Bởi vậy phải đối chiếu **lịch sử và trạng thái schema/data thực tế**.

## 10. release-locks: thao tác khẩn cấp có điều kiện

Trong các phiên bản Liquibase hỗ trợ, lệnh:

~~~bash
liquibase release-locks
~~~

được dùng để giải phóng trạng thái khóa của Liquibase. **Không dùng lệnh này chỉ vì thấy pipeline chờ lâu hoặc người dùng muốn deploy nhanh.**

Chỉ cân nhắc sau khi đã xác nhận:

1. Đúng database/schema/tên bảng lock đang liên quan.
2. Tiến trình holder không còn thực thi migration; không còn job/pod/session khác đang sử dụng hợp lệ khóa đó.
3. Trạng thái schema và dữ liệu sau khi holder dừng đã được kiểm tra, nhất là changeset không chạy trong transaction.
4. Biết changeset nào đã ghi nhận lịch sử, changeset nào chưa hoàn thành.
5. Có kế hoạch cho lần retry an toàn, backup hoặc forward-fix khi cần.
6. Hành động được ghi log/runbook và có người chịu trách nhiệm rõ ràng.

Sau release-locks, **không mặc định chạy lại update ngay trên production**. Cần xem liệu một bước đã tạo bảng, index hoặc dữ liệu nhưng chưa ghi vào DATABASECHANGELOG hay không, vì chạy lại có thể báo object already exists hoặc làm dữ liệu trùng.

Tránh sửa cột LOCKED trực tiếp bằng SQL, xóa hàng trong DATABASECHANGELOGLOCK hoặc xóa DATABASECHANGELOG như biện pháp xử lý thông thường. Những thay đổi thủ công vào bảng nội bộ có thể khiến thông tin lịch sử sai lệch và làm tăng rủi ro chạy đồng thời.

## 11. Tiến trình chết giữa changeset: transaction quyết định hậu quả

Giả sử A giữ khóa Liquibase rồi chạy một changeset gồm hai bước:

~~~text
1. Thêm cột orders.new_status
2. Backfill dữ liệu new_status
~~~

Nếu tiến trình bị dừng sau bước 1, hậu quả tùy DBMS và transaction:

| Điều kiện | Khả năng xảy ra |
|---|---|
| DBMS hỗ trợ transactional DDL và changeset chạy trong transaction phù hợp | Các thay đổi chưa commit thường có thể rollback theo transaction |
| DBMS tự commit một số DDL | Cột đã được thêm nhưng changeset có thể chưa được ghi hoàn tất |
| Changeset dùng runInTransaction=false | Không có bảo đảm toàn bộ bước được commit/rollback như một đơn vị |
| Job bị kill nhưng DB session vẫn đang xử lý | Có thể còn truy vấn/transaction đang chạy; phải xác minh thực tế |

Ví dụ PostgreSQL hỗ trợ nhiều DDL transactional, nhưng một số thao tác như CREATE INDEX CONCURRENTLY không được chạy trong transaction block và có quy tắc riêng. Nếu index đồng thời thất bại, có thể để lại index INVALID. Một câu SQL đã tác động một phần là vấn đề riêng của **trạng thái database**, không thể sửa chỉ bằng cách mở khóa Liquibase.

### 11.1. Xử lý thay đổi nửa hoàn tất

1. Dừng việc khởi chạy thêm pipeline/replica migration nếu đang xung đột.
2. Xác định lệnh thay đổi nào đã chạy, lệnh nào chưa, và transaction đã commit hay rollback.
3. Kiểm tra bảng/cột/constraint/index, dữ liệu liên quan và lịch sử DATABASECHANGELOG.
4. Chọn rollback, restore hoặc **forward-fix** dựa trên khả năng phục hồi thực tế.
5. Thử cách sửa trên bản sao có trạng thái tương đương.
6. Chỉ sau khi database về trạng thái nhất quán mới tiếp tục migration theo quy trình.

Tuyệt đối không giả định “mở khóa xong là chạy lại chắc chắn an toàn”.

## 12. Lock không ngăn incompatibility giữa hai phiên bản ứng dụng

Đây là điểm dễ nhầm nhất khi hệ thống triển khai cuốn chiếu.

Giả sử phiên bản A của ứng dụng còn đọc orders.old_status, còn phiên bản B muốn dùng orders.status. Nếu migration của B xóa old_status ngay lập tức, những replica A chưa được thay thế có thể lỗi dù Liquibase khóa migration hoàn hảo.

Cách thiết kế thường dùng là **expand–migrate–contract**:

~~~text
Giai đoạn 1 — Expand
  Thêm cột mới, giữ cột cũ; thay đổi tương thích ngược

Giai đoạn 2 — Migrate
  Ứng dụng chuyển sang đọc/ghi phù hợp; backfill và xác minh dữ liệu

Giai đoạn 3 — Contract
  Chỉ xóa cột cũ sau khi không còn phiên bản ứng dụng phụ thuộc
~~~

Khóa chỉ giúp các tiến trình Liquibase không đồng thời áp dụng những changeset chung phạm vi khóa. Nó **không đảm bảo schema mới tương thích** với ứng dụng đang chạy. Với migration tạo constraint, đổi kiểu hoặc xóa cột, phải xét các bản ứng dụng và job batch chưa nâng cấp.

## 13. Hai artifact khác nhau cùng tranh khóa: nguy cơ lệch lịch sử

Giả sử pipeline A mang changelog v10 gồm changeset 001–010; pipeline B mang changelog v11 gồm 001–011. Cả hai cùng trỏ database production.

Khóa buộc chúng chạy theo từng lượt. Nhưng nếu B chạy trước:

- B có thể áp dụng changeset 011.
- A sau đó đọc lịch sử và thấy nhiều changeset đã chạy, nhưng phần ứng dụng v10 vẫn có thể không tương thích với schema do 011 tạo ra.
- Nếu hai nhánh cùng sửa changeset ID/author/path nhưng nội dung khác nhau, checksum mismatch có thể xuất hiện.
- Nếu context/label khác nhau, danh sách changeset được áp dụng có thể khác dù đều dùng cùng bảng khóa.

Vì thế phải có **serialization ở cấp phát hành**, không chỉ serialization ở cấp Liquibase. Những giải pháp gồm: pipeline deployment một môi trường chỉ cho một phiên chạy, khóa ở orchestrator, promotion artifact bất biến, quy tắc merge changelog và phê duyệt thứ tự phát hành.

Không viết lại changeset đã chạy để “giải quyết” xung đột. Hãy tạo changeset bổ sung hoặc reconcile theo quy trình có kiểm chứng.

## 14. Lock wait, timeout và chính sách retry

Khi nhiều tiến trình cùng gọi update, phải định nghĩa các hành vi vận hành trước khi xảy ra sự cố:

- Một tiến trình được phép đợi Liquibase lock tối đa bao lâu?
- Sau bao lâu thì job báo lỗi và được thử lại?
- Nếu migration nặng kéo dài, liveness/startup probe có chấp nhận hay không?
- Retry có tạo process mới trong khi process cũ chưa hoàn toàn kết thúc?
- Ai chịu trách nhiệm xác minh stale lock và quyết định release-locks?
- Có cảnh báo khi thời gian giữ khóa vượt ngưỡng vận hành không?

Thông số điều chỉnh thời gian chờ/poll có thể có trong các phiên bản Liquibase, nhưng tên biến và giá trị mặc định thay đổi theo phiên bản/cách tích hợp. Hãy kiểm tra tài liệu của runtime thực tế thay vì sao chép giá trị từ ví dụ không được xác thực.

### 14.1. Retry không phải luôn idempotent ở cấp thay đổi dữ liệu

Liquibase dựa vào lịch sử để không chạy lại changeset đã hoàn tất trong điều kiện bình thường. Nhưng nếu tiến trình chết trước khi ghi nhận lịch sử mà tác động đã được commit, lần retry có thể:

- Gặp lỗi “table already exists”.
- Chèn dữ liệu CSV lần thứ hai và bị vi phạm unique key.
- Tạo index trùng hoặc gặp index INVALID.
- Cập nhật lại dữ liệu đã thay đổi một phần.

Vì vậy, retry chỉ nên được bật sau khi hiểu transaction và khả năng phục hồi của changeset; không dùng policy retry vô hạn để che giấu một database bị kẹt trong trạng thái sai.

## 15. Cấu hình nhiều môi trường và quyền migration

Một kiến trúc an toàn cần phân tách rõ:

**Tài khoản ứng dụng:** quyền cần thiết để đọc/ghi dữ liệu nghiệp vụ, hạn chế DDL nếu có thể.

**Tài khoản migration:** quyền cần để áp dụng schema/data change và quản lý bảng lịch sử/khóa của Liquibase, được cấp riêng cho job hoặc runtime đã được phê duyệt.

**Kết nối chính xác:** xác nhận database URL, schema mặc định, vị trí DATABASECHANGELOG và DATABASECHANGELOGLOCK, context/label, changelog path và version runtime.

Trong staging, pipeline phải dùng staging DB chứ không phụ thuộc vào biến môi trường mơ hồ. Trong production, secrets phải được quản lý qua công cụ phù hợp; không nhúng mật khẩu vào changelog hoặc log lỗi.

Nếu cấu hình lại tên/schema của bảng DATABASECHANGELOGLOCK, đánh giá tác động tới mọi tiến trình có thể cùng chạy migration. Đổi vị trí bảng lock ở một replica mà không ở replica còn lại có thể vô tình làm mất cơ chế tuần tự hóa mà nhóm đang tin tưởng.

## 16. Quan sát lock và thiết lập runbook

Một vận hành viên cần biết không chỉ “deployment failed” mà còn vì sao.

Thông tin quan sát hữu ích:

- Job/pod/instance nào bắt đầu chạy Liquibase, thời điểm bắt đầu/kết thúc.
- Changelog artifact/version và cấu hình context/label đang dùng.
- Thời gian chờ để lấy lock, thời gian giữ lock, changeset đang thực thi.
- Thông tin holder từ list-locks hoặc bảng DATABASECHANGELOGLOCK.
- Số changeset đã chạy, thất bại hoặc bỏ qua, đối chiếu DATABASECHANGELOG.
- DBMS wait event, query/transaction đang chờ và tình trạng tài nguyên.
- Quyết định release-locks hoặc retry được ghi nhận cùng người thực hiện.

Một runbook ngắn nên có:

~~~text
Triệu chứng: Liquibase cannot acquire change log lock hoặc timeout.
1. Xác minh đúng database/schema và đọc trạng thái lock.
2. Đối chiếu holder với pod/job và log deployment.
3. Xác minh holder còn sống, còn thực hiện SQL hay đang chờ DBMS lock.
4. Nếu còn sống: theo dõi/điều tra, KHÔNG release-locks tùy tiện.
5. Nếu đã chết: kiểm tra schema, dữ liệu, DATABASECHANGELOG.
6. Chỉ sau khi xác minh an toàn mới release-locks theo thẩm quyền.
7. Thử migration phục hồi trên bản sao nếu có trạng thái nửa hoàn tất.
8. Rerun có kiểm soát, xác minh kết quả và ghi nhận sự cố.
~~~

Một dashboard hiển thị thời gian giữ khóa có thể rất hữu ích, nhưng không nên coi LOCKGRANTED cũ là bằng chứng duy nhất để tự động giải phóng lock. Cần bổ sung tín hiệu process và transaction thực tế.

## 17. Kiểm thử khi hai tiến trình cùng chạy trên database lab

Bài thực hành dùng một PostgreSQL lab riêng, không sử dụng database production.

### 17.1. Chuẩn bị

Tạo một changelog đơn giản gồm:

- Changeset tạo bảng lock_demo.
- Changeset bổ sung cột note.
- Changeset tạo index trên note hoặc một thao tác đủ thời gian để hai tiến trình có thể chồng lấn trong lab.

Có thể viết changelog YAML minh họa:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 001-create-lock-demo
      author: lab
      changes:
        - createTable:
            tableName: lock_demo
            columns:
              - column:
                  name: id
                  type: BIGINT
                  constraints:
                    primaryKey: true
                    nullable: false

  - changeSet:
      id: 002-add-note
      author: lab
      changes:
        - addColumn:
            tableName: lock_demo
            columns:
              - column:
                  name: note
                  type: VARCHAR(100)
~~~

Hai CLI hoặc hai tiến trình thử nghiệm phải dùng **cùng JDBC URL, changelog, schema, context/label và cấu hình bảng lock**.

### 17.2. Chạy đồng thời từ hai terminal

Sau khi validate changelog, bắt đầu hai lệnh update gần nhau trên database lab:

~~~bash
liquibase update
~~~

Ở terminal thứ hai, dùng cùng cấu hình:

~~~bash
liquibase update
~~~

Quan sát log: tiến trình nào lấy lock, tiến trình nào đợi, thứ tự changeset được ghi vào DATABASECHANGELOG và trạng thái lock sau khi cả hai kết thúc. Với changeset quá nhanh, có thể không quan sát được thời gian chờ; đó không phải lỗi. Muốn mô phỏng chờ rõ hơn, chỉ thêm bước chậm có kiểm soát trong lab và bảo đảm nó không ảnh hưởng production.

Trong một terminal quan sát riêng:

~~~bash
liquibase list-locks
~~~

Hoặc dùng câu SELECT chỉ đọc trên DATABASECHANGELOGLOCK như mục 9.

### 17.3. Tình huống lỗi để quan sát

1. **Đồng thời bình thường:** kỳ vọng changeset chỉ được áp dụng một lần và cả hai tiến trình không cùng thực hiện DDL.
2. **Một tiến trình chờ dài:** theo dõi thời gian và xác nhận holder còn tiến triển.
3. **Cùng database nhưng khác changelog version:** dùng bản sao lab, thử một changeset bổ sung ở tiến trình thứ hai và giải thích vì sao lock không bảo đảm tương thích ứng dụng.
4. **Khác lock schema/table:** chỉ mô phỏng trên database có thể xóa bỏ để quan sát nguy cơ hai tiến trình không còn phối hợp; không thử kiểu này trên production.
5. **Dừng bất thường:** nếu tạo tình huống kết thúc cưỡng bức trong lab, đối chiếu trạng thái lock, schema và lịch sử trước khi quyết định phục hồi. Không tự động giải phóng khóa.

Điều kiện hoàn thành: người học giải thích được thứ tự lấy/nhả khóa, phân biệt live lock và stale lock, hiểu giới hạn của lock Liquibase, và đề xuất được pipeline an toàn cho nhiều replica.

## 18. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Khả năng gây ra | Cách xử lý |
|---|---|---|
| Liquibase cannot acquire change log lock | Tiến trình khác đang giữ khóa hoặc lock chưa được giải phóng | Xem list-locks, đối chiếu holder và log |
| Nhiều pod chờ startup | Tất cả bật Liquibase khi migration nặng | Tối ưu mô hình điều phối; cân nhắc migration job riêng |
| Pod restart liên tục | Probe/timeout không phù hợp thời gian chờ hoặc runtime lỗi thật | Điều chỉnh theo kết quả đo, xác minh startup/liveness |
| Lock giữ lâu dù job đã báo thất bại | Holder còn chạy, DB session chưa dừng hoặc stale lock | Kiểm tra process, transaction, schema và lịch sử trước release |
| Hai pipeline đều chạy DDL gần cùng lúc | Không dùng chung DB lock table hoặc có tool ngoài Liquibase | Kiểm tra cấu hình schema/table và ownership |
| DDL lỗi sau khi được lock | DBMS lock, dữ liệu vi phạm, thiếu quyền, không tương thích SQL | Điều tra câu SQL và trạng thái DB, không coi là lỗi lock Liquibase |
| Table already exists khi retry | Thay đổi đã commit một phần nhưng chưa được ghi nhận | Kiểm tra schema thực tế và DATABASECHANGELOG |
| Checksum mismatch sau deployment khác phiên bản | Hai artifact có nội dung changeset không khớp | Giữ immutable changelog, reconcile bằng changeset mới |
| Ứng dụng cũ lỗi sau migration mới | Thay đổi phá tương thích schema khi rollout cuốn chiếu | Áp dụng expand–migrate–contract |
| release-locks xong vẫn lỗi | Lỗi gốc là migration nửa hoàn tất hoặc DDL bị chặn | Sửa trạng thái database theo kế hoạch, không chỉ mở khóa |

## 19. Checklist trước khi triển khai có nhiều tiến trình

| Câu hỏi kiểm tra | Bằng chứng cần có |
|---|---|
| Ai chịu trách nhiệm chạy migration? | Một mô hình rõ: startup hoặc job riêng |
| Mọi tiến trình cùng database có dùng đúng lock table? | JDBC URL, schema và tên bảng lock được đối chiếu |
| Changelog artifact/phiên bản có thống nhất? | Changelog và cấu hình context/label được version control |
| Có pipeline khác cùng triển khai vào môi trường này không? | Cơ chế điều phối release và retry |
| Thời gian chờ lock phù hợp? | Kết quả đo migration, chính sách timeout |
| Startup/liveness/readiness có hợp với migration dài? | Probe và rollout được thử với delay thực tế |
| DBMS DDL lock và transaction có được xem xét? | Đã đo workload, kiểm tra các thao tác không transactional |
| Fresh install và upgrade đều thành công? | Bài thử trên database sạch và bản trước |
| Changeset có thể phục hồi nếu chết giữa chừng? | Kế hoạch rollback/restore/forward-fix rõ ràng |
| Có thể xác định ai đang giữ lock? | list-locks, log pod/job, quyền xem DB activity |
| Có quy trình release-locks an toàn? | Runbook xác minh holder đã chết và DB nhất quán |
| Schema mới tương thích ứng dụng cũ đang chạy? | Kế hoạch expand–migrate–contract |
| Kết quả cuối cùng có được xác minh? | DATABASECHANGELOG, schema và dữ liệu thực tế |

**Nguyên tắc cốt lõi:** DATABASECHANGELOGLOCK giúp Liquibase phối hợp các tiến trình migration dùng chung một phạm vi khóa; DATABASECHANGELOG giúp mỗi tiến trình nhận ra changeset đã được áp dụng. Hai cơ chế đó rất cần nhưng chưa đủ: hệ thống nhiều replica còn cần quản lý phiên bản changelog, transaction/DDL, lịch triển khai, readiness và khả năng khôi phục khi tiến trình dừng giữa chừng. Trong production, ưu tiên một mô hình migration có quyền sở hữu rõ, quan sát được trạng thái lock, không release khóa khi chưa xác minh holder và luôn kiểm thử cả database mới lẫn database đã có lịch sử.

