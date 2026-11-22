# Thời gian chờ khóa, timeout và giới hạn tài nguyên

## 1. Mục tiêu bài học

Khi Liquibase triển khai migration, một lệnh đơn giản như thêm cột, tạo chỉ mục hay cập nhật dữ liệu có thể phải **chờ khóa**, tiêu thụ CPU/I/O và giữ giao dịch mở lâu hơn dự kiến. Trong khi đó, một tiến trình Liquibase thứ hai có thể đang chờ **khóa lịch sử changelog**, hoàn toàn khác với khóa mà hệ quản trị dùng để bảo vệ bảng và dữ liệu.

Nếu không phân biệt hai cơ chế này, người vận hành có thể xử lý sai: tăng timeout vô hạn, tự giải phóng DATABASECHANGELOGLOCK khi tiến trình khác vẫn hoạt động, hoặc tưởng Liquibase đã hỏng trong khi thực chất câu DDL đang chờ một giao dịch ứng dụng.

Bài thuộc chương **Giao dịch và khóa** của module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**. Mục tiêu module là nắm cách quản lý thay đổi schema và dữ liệu bằng Liquibase với changelog, changeset, precondition, checksum và lịch sử triển khai; thực hành migration có kiểm chứng, rollback, phối hợp nhiều môi trường và tích hợp Spring Boot hoặc CI/CD. Ở đây, trọng tâm là **thời gian chờ khóa, timeout và giới hạn tài nguyên** trong quá trình chạy migration có kiểm chứng.

Học xong bài này, bạn cần:

1. Phân biệt khóa điều phối Liquibase với khóa giao dịch/DDL của DBMS.
2. Xác định những tầng timeout khác nhau: lấy khóa Liquibase, lấy khóa DBMS, thực thi SQL, kết nối JDBC và thời gian chạy của job.
3. Biết cấu hình, quan sát và chẩn đoán lock timeout trên PostgreSQL, đồng thời hiểu rằng các DBMS khác có cơ chế riêng.
4. Ước lượng tác động lên CPU, bộ nhớ, I/O, đĩa, transaction log và connection pool.
5. Thiết kế migration ngắn, có kiểm soát, tránh giữ khóa quá lâu hoặc chạy đồng thời không cần thiết.
6. Biết lúc nào cần dừng, kiểm tra lại trạng thái, rollback, forward fix hoặc chuyển sự cố lên DBA, thay vì giải phóng khóa tùy tiện.
7. Tích hợp budget thời gian và giới hạn tài nguyên vào quy trình Spring Boot/CI/CD.

Các con số trong bài là **ví dụ minh họa cho môi trường học tập**, không phải giá trị mặc định hoặc khuyến nghị chung cho mọi hệ thống. Ngưỡng thật cần được xác lập dựa trên DBMS, workload, kích thước dữ liệu và SLO của từng dịch vụ.

## 2. Có hai hệ thống khóa cần phân biệt

### 2.1. Khóa điều phối changelog của Liquibase

Liquibase thường dùng bảng **DATABASECHANGELOGLOCK** để điều phối những tiến trình cùng muốn cập nhật một database. Bảng mặc định có các thông tin như ID, LOCKED, LOCKGRANTED và LOCKEDBY, tùy DBMS và cách cấu hình tên/schema.

Luồng khái quát:

~~~text
Job A: liquibase update              Job B: liquibase update
           |                                     |
           v                                     v
   Đòi khóa changelog                     Đòi cùng khóa
           |                                     |
           v                                     v
      Lấy được khóa                       Chưa lấy được
           |                                     |
           v                                     v
   Chạy các changeset                     Chờ / thử lại
           |
           v
   Ghi DATABASECHANGELOG
           |
           v
      Trả khóa
                                                 |
                                                 v
                                    Có thể tiếp tục sau khi lấy khóa
~~~

Cơ chế này giúp tránh hai lượt Liquibase cùng sửa lịch sử migration theo cách không phối hợp. Nó **không ngăn một ứng dụng, DBA hoặc công cụ khác chạy SQL trực tiếp**, và cũng không thay thế các khóa vật lý của DBMS.

**DATABASECHANGELOGLOCK khác DATABASECHANGELOG**:

- DATABASECHANGELOGLOCK: phục vụ điều phối lượt chạy Liquibase.
- DATABASECHANGELOG: ghi nhận changeset nào đã được xử lý, thời gian chạy, checksum và loại thực thi.

### 2.2. Khóa do DBMS đặt lên đối tượng/dữ liệu

Khi một changeset thực thi SQL, DBMS vẫn phải bảo vệ trạng thái dữ liệu. Ví dụ PostgreSQL có các chế độ khóa bảng và khóa hàng; một số DDL cần khóa bảng mạnh, có thể chờ các transaction đang đọc/ghi và sau đó chặn những transaction khác.

~~~text
Ứng dụng mở transaction
          |
          v
Giữ khóa trên app.orders
          |
          v
Liquibase chạy ALTER TABLE app.orders ...
          |
          v
Chờ DBMS cấp khóa cần thiết
          |
       [timeout?]
          |
     +----+----+
     |         |
    Có        Không
     |         |
     v         v
  Chạy DDL   Báo lỗi/được hủy theo DBMS
~~~

Một tiến trình Liquibase có thể **đã lấy được DATABASECHANGELOGLOCK** nhưng vẫn **đang chờ khóa của PostgreSQL** để thực thi ALTER TABLE. Trong lúc đó, các tiến trình Liquibase khác có thể đồng thời bị chặn bởi khóa changelog.

### 2.3. Bảng phân biệt nhanh

| Đặc điểm | Khóa Liquibase | Khóa DBMS |
|---|---|---|
| Mục đích | Điều phối các lượt cập nhật changelog | Bảo vệ dữ liệu và đối tượng SQL khi truy cập đồng thời |
| Nơi thường quan sát | DATABASECHANGELOGLOCK, lệnh kiểm tra khóa Liquibase | pg_stat_activity, pg_locks hoặc công cụ DBMS tương ứng |
| Nguồn xung đột | Một tiến trình Liquibase khác | Transaction ứng dụng, SQL từ DBA, migration, query dài |
| Cách kết thúc | Tiến trình Liquibase hoàn tất/giải phóng khóa đúng cách | Transaction kết thúc, câu SQL hủy/lỗi, DBMS giải phóng khóa theo quy tắc |
| Rủi ro xử lý sai | Release khóa Liquibase khi job thực vẫn chạy | Kill session nhầm, mất giao dịch hoặc gián đoạn ứng dụng |
| Timeout tương ứng | Giới hạn chờ để lấy khóa changelog | Lock timeout, statement/query timeout và chính sách DBMS |

**Quy tắc chẩn đoán đầu tiên:** xác định đang chờ **loại khóa nào** rồi mới chọn lệnh hoặc chính sách xử lý.

## 3. Các tầng thời gian chờ trong một lượt migration

Một pipeline thường trải qua nhiều bước, mỗi bước có timeout riêng.

~~~text
CI/CD job timeout (toàn bộ phiên thực thi)
  |
  +-- Kết nối đến database: connect/login timeout
  |
  +-- Chờ khóa Liquibase: changelog lock wait limit
  |
  +-- Đọc changelog và kiểm tra preconditions
  |
  +-- Mỗi câu SQL:
  |     +-- Chờ khóa DBMS: lock timeout
  |     +-- Thực thi câu SQL: statement/query timeout
  |     +-- Giao dịch: transaction / idle-in-transaction policy
  |
  +-- Kiểm chứng schema/dữ liệu sau triển khai
  |
  +-- Ghi log, trạng thái và thông báo kết quả
~~~

| Tầng | Bảo vệ trước | Không bảo đảm |
|---|---|---|
| JDBC connection/login timeout | Không chờ vô hạn để thiết lập kết nối | Không giới hạn thời gian của một câu DDL đã bắt đầu |
| Liquibase changelog lock wait | Không chờ mãi khi một job khác giữ khóa changelog | Không giới hạn khóa bảng của DBMS |
| DBMS lock timeout | Không chờ quá ngưỡng để lấy một khóa DBMS | Không giới hạn tổng thời gian câu SQL sau khi lấy khóa |
| DBMS statement timeout | Hạn chế thời gian câu lệnh theo cơ chế DBMS | Không tự bảo đảm toàn job hoàn thành trong thời gian đó |
| Transaction/idle timeout | Ngăn transaction treo hoặc nhàn rỗi quá lâu theo chính sách | Không tự thay thế kế hoạch rollback và kiểm soát dữ liệu |
| Socket/network read timeout | Không chờ phản hồi mạng vô hạn theo chính sách driver | Có thể không biết câu lệnh trên server đã hoàn tất hay chưa |
| CI/CD job timeout | Chặn một job vượt thời gian chạy chung | Không tự phục hồi schema hay xóa mọi khóa trên server |

Các timeout **không nhất thiết cộng đơn giản**. Ví dụ lock_timeout của PostgreSQL áp dụng theo từng lần cố lấy khóa; một changeset chứa nhiều câu SQL có thể trải qua nhiều lần chờ. Statement timeout cũng có thể được áp dụng theo từng câu lệnh. Vì vậy, phải có cả **ngân sách toàn job** và những giới hạn nhỏ hơn cho từng bước.

## 4. Chờ khóa DATABASECHANGELOGLOCK

### 4.1. Khi nào tiến trình phải chờ?

Các tình huống thường gặp:

- Hai job CI/CD cùng chạy liquibase update cho một database.
- Ứng dụng Spring Boot nhiều replica đồng thời khởi động và kích hoạt Liquibase.
- Một job trước vẫn đang thực thi DDL rất lâu.
- Job trước bị dừng bất thường và trạng thái khóa changelog chưa được giải phóng như mong muốn.
- Cấu hình các job dùng chung database nhưng thiếu điều phối thứ tự triển khai.

Liquibase có cơ chế chờ, thử lấy lại khóa và giới hạn thời gian chờ; **tên thuộc tính, đơn vị và giá trị mặc định phụ thuộc phiên bản Liquibase và cách gọi CLI/API**. Với một số phiên bản CLI, các thiết lập như **changelog lock wait time in minutes** và **changelog lock poll rate** có thể cấu hình được. Đừng sao chép giá trị hoặc tên tùy chọn từ tài liệu phiên bản khác mà chưa kiểm tra.

Có hai câu hỏi vận hành khác nhau:

1. **Chờ tối đa bao lâu?** Đặt một giới hạn phù hợp với lịch phát hành và SLO.
2. **Thử lấy khóa lại bao lâu một lần?** Polling quá sát gây yêu cầu kiểm tra lặp không cần thiết; quá thưa làm chậm việc tiếp tục khi khóa vừa được giải phóng.

### 4.2. Quan sát khóa Liquibase

Ví dụ lệnh CLI thường được dùng:

~~~bash
liquibase --defaults-file=liquibase.properties list-locks
~~~

Lệnh này giúp kiểm tra khóa changelog theo khả năng của phiên bản CLI. Có thể xem thêm bảng DATABASECHANGELOGLOCK bằng truy vấn **chỉ đọc**, nếu policy cho phép:

~~~sql
SELECT id, locked, lockgranted, lockedby
FROM databasechangeloglock;
~~~

Ở PostgreSQL, câu SQL trên dùng tên bảng không đặt dấu nháy; tên bảng/schema thực tế phụ thuộc cấu hình Liquibase và cách DBMS xử lý định danh. Nếu Liquibase dùng một schema riêng cho bảng lịch sử, phải truy vấn đúng schema.

**Không suy luận rằng một bản ghi LOCKED = true luôn là stale lock.** Tiến trình có thể vẫn đang chạy hợp lệ, còn DBMS đang xử lý một câu DDL dài.

### 4.3. Có nên dùng release-locks?

Liquibase có lệnh quản trị **release-locks** cho những trường hợp cần giải phóng khóa changelog sau sự cố. Tuy nhiên:

- Trước tiên phải xác nhận **không còn tiến trình Liquibase nào thực sự đang chạy** trên database đó.
- Phải điều tra các session DBMS và trạng thái migration đang dở.
- Cần quyền hạn và quy trình sự cố phù hợp; hành động giải phóng thủ công phải được ghi log.
- Giải phóng khóa changelog **không tương đương hủy SQL đang chờ khóa DBMS** và **không phục hồi dữ liệu**.
- Sau khi thao tác, cần xác minh DATABASECHANGELOG, schema thực tế và tính nhất quán trước khi chạy update trở lại.

Lệnh có thể được sử dụng sau khi đã xác nhận an toàn:

~~~bash
liquibase --defaults-file=liquibase.properties release-locks
~~~

Đây là **lệnh khắc phục có điều kiện**, không phải bước mặc định của mỗi pipeline. Tuyệt đối không tự động gọi release-locks sau mọi lần timeout: việc đó có thể phá điều phối khi job thực vẫn chưa kết thúc.

## 5. DBMS lock timeout: tránh chờ khóa bảng vô hạn

### 5.1. Ví dụ PostgreSQL

PostgreSQL hỗ trợ tham số **lock_timeout**. Nếu một câu lệnh phải chờ để lấy khóa lâu quá ngưỡng, câu lệnh bị hủy với lỗi tương ứng.

Trong một phiên làm việc PostgreSQL riêng cho thử nghiệm:

~~~sql
SHOW lock_timeout;
SHOW statement_timeout;
SHOW idle_in_transaction_session_timeout;
~~~

Ví dụ áp dụng giới hạn cho **một transaction được kiểm soát**:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '3s';
SET LOCAL statement_timeout = '2min';

-- Chỉ chạy trên database lab; cần xác minh app.orders tồn tại.
ALTER TABLE app.orders
    ADD COLUMN note_for_lab VARCHAR(100);

COMMIT;
~~~

Ở đây:

- **SET LOCAL** có phạm vi trong transaction hiện tại.
- Nếu không lấy được khóa cần thiết trong thời gian quy định, PostgreSQL hủy lệnh và transaction có thể rơi vào trạng thái lỗi, cần **ROLLBACK** trước khi tiếp tục trong cùng session.
- Nếu lệnh mất quá thời gian statement_timeout, PostgreSQL có thể hủy lệnh vì hết thời gian thực thi; đây không phải cùng nguyên nhân với lock_timeout.
- Việc chạy thử phải được giới hạn trong database/schema học tập.

**Điểm dễ nhầm khi đưa ví dụ vào Liquibase:** không thể đặt một SET LOCAL trong changeset A rồi mặc định nó còn hiệu lực tới changeset B. Liquibase thường quản lý transaction ở cấp changeset; sau khi transaction A kết thúc, SET LOCAL hết hiệu lực. Muốn policy timeout áp dụng nhất quán, phải xác định cách nó được cấp cho **chính session/transaction sẽ thực thi DDL**, theo phiên bản Liquibase, JDBC và DBMS đang dùng.

### 5.2. SET, SET LOCAL và cấu hình role

| Cách cấu hình PostgreSQL | Phạm vi | Lưu ý |
|---|---|---|
| SET lock_timeout = '3s' | Session hiện tại | Chỉ tác động đến kết nối thực sự nhận lệnh SET |
| SET LOCAL lock_timeout = '3s' | Transaction hiện tại | Hết hiệu lực khi transaction kết thúc; cần nằm trong transaction phù hợp |
| ALTER ROLE ... SET lock_timeout | Những session mới của role theo quy tắc PostgreSQL | Chính sách tồn tại ở cấp DBMS; cần quyền phù hợp và review ảnh hưởng các workload khác |
| Cấu hình connection/session khi tạo JDBC connection | Session JDBC được mở với thông số đã cấp | Phải kiểm tra cú pháp driver, precedence và timeout đã có hiệu lực |

Không nên để profile terminal/psql tạo cảm giác đã cấu hình timeout cho Liquibase: CLI có thể dùng kết nối JDBC hoàn toàn khác. Xác minh bằng **SHOW** hoặc một bước kiểm tra tương đương **trên chính kết nối và vai trò chạy migration**.

### 5.3. Quan hệ giữa lock_timeout và statement_timeout

Trong PostgreSQL, lock_timeout áp dụng cho thời gian cố lấy khóa, còn statement_timeout áp dụng cho thời gian câu lệnh theo cơ chế PostgreSQL. Nếu statement_timeout ngắn hơn hoặc bằng lock_timeout, câu lệnh có thể hết statement_timeout trước, khiến giới hạn lock_timeout không đem lại nhiều thông tin riêng.

Ví dụ minh họa:

~~~text
lock_timeout       = 3 giây
statement_timeout  = 120 giây
CI job timeout     = 20 phút
~~~

Lệnh DDL chờ khóa quá 3 giây sẽ báo lỗi trước khi tới giới hạn 120 giây. Nếu lấy được khóa, nó vẫn có thể bị hủy vì thời gian thực thi quá 120 giây. Đây là ngân sách ví dụ, **không phải** cấu hình mặc định hoặc giá trị phù hợp mọi migration.

**Lưu ý:** lock_timeout có thể áp dụng cho nhiều yêu cầu lấy khóa trong một câu lệnh; không nhất thiết là tổng thời gian chờ khóa tích lũy của toàn migration.

## 6. SQL statement timeout và transaction timeout

### 6.1. Statement timeout

Một câu ALTER TABLE có thể lấy được khóa nhưng sau đó thực hiện quét dữ liệu, kiểm tra ràng buộc hoặc xây dựng cấu trúc tốn thời gian. **statement_timeout** giúp giới hạn thời gian một câu SQL theo chính sách database.

Tuy nhiên:

- Timeout quá ngắn khiến migration đúng bị hủy liên tục.
- Timeout quá dài có thể khiến ứng dụng bị chặn lâu hoặc CI/CD báo sai thời gian kỳ vọng.
- Một câu lệnh bị hủy không bảo đảm mọi thay đổi trước đó trong các changeset khác đã được rollback.
- Với DBMS có DDL tự commit, trạng thái sau lỗi có thể khác PostgreSQL.

Nên kiểm thử trên bản sao dữ liệu có kích thước và index tương đương production để chọn ngưỡng hợp lý, thay vì đặt timeout tùy tiện.

### 6.2. Transaction dài và idle in transaction

Transaction giữ khóa càng lâu càng dễ gây hàng chờ. Đặc biệt, một session PostgreSQL ở trạng thái **idle in transaction** có thể giữ khóa dù không đang chạy câu SQL nào.

Có thể dùng chính sách **idle_in_transaction_session_timeout** để giảm một số trường hợp transaction bỏ quên, nhưng phải hiểu tác động tới ứng dụng, việc kết nối bị ngắt và khả năng rollback của transaction.

Một transaction đang chạy SQL thực sự không phải idle; chính sách idle timeout không thay thế statement_timeout. Với migration, tránh tạo changeset chứa nhiều bước phức tạp và những khoảng đợi thủ công khi transaction vẫn mở.

### 6.3. runInTransaction trong Liquibase

Ở các DBMS có hỗ trợ, Liquibase mặc định thường cố thực thi mỗi changeset trong một transaction theo khả năng của DBMS. Thuộc tính **runInTransaction** có thể thay đổi cơ chế này khi cần.

Ví dụ chú giải cấu hình:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 021-update-order-state
      author: platform-team
      runInTransaction: true
      changes:
        - sql:
            sql: |
              UPDATE app.orders
              SET status = 'ARCHIVED'
              WHERE status = 'LEGACY';
~~~

**Đây chỉ là ví dụ cú pháp**, không khuyến nghị chạy một UPDATE diện rộng như vậy trong production. UPDATE nhiều hàng có thể giữ khóa hàng, phát sinh WAL/redo và làm chậm các giao dịch ứng dụng. Cần đánh giá batch, chỉ mục, số hàng, tác động tới các dịch vụ và quy trình kiểm chứng.

**runInTransaction: false** không phải lựa chọn chung để tránh khóa. Nó có thể khiến các câu lệnh áp dụng một phần khi lỗi, làm việc phục hồi khó hơn. Chỉ dùng khi DBMS yêu cầu cho thao tác cụ thể (ví dụ một số DDL online/concurrent) và đã có kế hoạch dọn dẹp trạng thái dở dang.

## 7. Connection timeout và socket timeout là một vấn đề khác

Trước khi Liquibase đọc changelog hay xin khóa, JDBC phải kết nối được tới database. Một số driver cung cấp tùy chọn giới hạn:

- Thời gian chờ **mở kết nối TCP**.
- Thời gian chờ **đăng nhập/xác thực**.
- Thời gian chờ **đọc phản hồi từ server** qua socket.
- Thời gian chờ lấy connection từ **pool** khi ứng dụng dùng pool.

Những timeout này không tương đương lock_timeout hay statement_timeout. Ví dụ JDBC socket bị ngắt trong lúc database vẫn đang xử lý một DDL có thể tạo tình huống **không chắc lệnh SQL trên server đã hoàn thành hay chưa**. Khi đó, không được lập tức chạy lại update theo thói quen; cần kiểm tra session, trạng thái DB và lịch sử Liquibase.

Trong Spring Boot, **connectionTimeout** của HikariCP (nếu dùng HikariCP) chủ yếu điều khiển thời gian chờ lấy connection từ pool. Nó không tự đặt PostgreSQL lock_timeout cho DDL. Cấu hình giao dịch trên tầng ứng dụng cũng không mặc nhiên áp dụng đúng cho Liquibase nếu Liquibase dùng connection riêng.

**Nguyên tắc:** mỗi timeout phải gắn với đúng tiến trình, kết nối, driver và tác vụ mà nó thực sự điều khiển.

## 8. Job timeout của CI/CD và ngân sách toàn lượt triển khai

Một pipeline cần giới hạn tổng thời gian để tránh một job treo kéo dài ngoài lịch bảo trì. Nhưng hủy job từ bên ngoài không đồng nghĩa DBMS đã hoàn tất rollback hoặc mọi session đã đóng.

Ví dụ ngân sách minh họa:

| Hạng mục | Ngưỡng minh họa | Hành động khi vượt |
|---|---:|---|
| Mở kết nối | 10 giây | Báo lỗi kết nối, không thử update vô hạn |
| Chờ khóa changelog | 5 phút | Kiểm tra job giữ khóa; không tự release |
| Chờ một khóa DBMS | 3 giây | Dừng và xác định blocker, không tăng timeout ngay |
| Thực thi một câu SQL | 2 phút | Kiểm tra câu SQL, plan và quy mô dữ liệu |
| Toàn bộ job migration + hậu kiểm | 20 phút | Dừng điều phối, kiểm tra trạng thái trước retry |

Các mốc trên chỉ minh họa sự khác nhau giữa các ngân sách. Một migration có xây dựng index trên bảng lớn có thể cần thời gian hoàn toàn khác, cùng maintenance window và quy trình phê duyệt riêng.

Đừng coi công thức “5 phút chờ changelog + 3 giây lock + 2 phút statement” là **giới hạn tuyệt đối** của job: có thể có nhiều changeset/câu SQL và nhiều lần chờ. Hãy xác lập cả giới hạn tổng thể, số lần retry, khoảng backoff và tiêu chí xác minh sau khi thất bại.

### 8.1. Retry có an toàn không?

Liquibase nhận diện changeset bằng id, author, đường dẫn changelog và lịch sử trong DATABASECHANGELOG. Điều này giúp tránh chạy lại changeset đã hoàn tất hợp lệ. Tuy nhiên, khi một DDL thất bại sau khi thực thi một phần, nhất là trên DBMS không rollback DDL như mong muốn, lịch sử có thể **không khớp hoàn toàn** với đối tượng thật.

Do đó, chỉ retry khi đã:

1. Xác nhận tiến trình trước đã kết thúc.
2. Kiểm tra khóa changelog và các session SQL còn hoạt động.
3. Kiểm tra cấu trúc/dữ liệu được tác động.
4. Đối chiếu changeset pending và DATABASECHANGELOG.
5. Hiểu tác dụng khi thực thi lại từng câu lệnh.

Không tự động retry vô hạn khi gặp timeout, deadlock hoặc mất kết nối.

## 9. Theo dõi session chờ khóa trong PostgreSQL

### 9.1. Quan sát pg_stat_activity

Trên PostgreSQL, có thể kiểm tra các session đang chạy hoặc chờ:

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
~~~

**query_age không phải thời gian chờ khóa chính xác.** Nó đo thời gian từ mốc query_start trong session hiện tại; câu lệnh có thể vừa xử lý vừa chờ. Các trường wait_event_type và wait_event cho biết trạng thái chờ tại thời điểm lấy mẫu. Một số session cần quyền quản trị/quan sát phù hợp để xem đầy đủ thông tin.

Không ghi tràn lan toàn bộ nội dung query trong log giám sát nếu chúng có thể chứa dữ liệu nhạy cảm hoặc literal của khách hàng.

### 9.2. Xác định session đang bị blocker

PostgreSQL cung cấp hàm **pg_blocking_pids** để xác định những session có thể đang chặn một session khác:

~~~sql
SELECT
    a.pid AS waiting_pid,
    a.usename AS waiting_user,
    a.application_name,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    now() - a.query_start AS query_age
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY a.query_start NULLS LAST;
~~~

Kết quả trả về PID chờ cùng mảng PID blocker theo cơ chế PostgreSQL. Người vận hành có thể dùng các PID này để xem trạng thái, loại giao dịch và ứng dụng sở hữu session. Không nên kết luận session nào “có lỗi” chỉ từ việc xuất hiện trong danh sách: có thể một transaction hợp lệ đang xử lý nghiệp vụ.

Một blocking chain có thể hình thành:

~~~text
Transaction A giữ khóa trên app.orders
           |
           +--> Liquibase B chờ ALTER TABLE
                    |
                    +--> Transaction C khác chờ cùng đối tượng
~~~

Nếu chỉ tăng timeout cho B, hàng chờ có thể kéo dài; vấn đề gốc nằm ở transaction A hoặc kế hoạch triển khai thiếu khoảng thời gian an toàn.

### 9.3. pg_locks và metadata

Bảng **pg_locks** cung cấp thông tin về yêu cầu khóa và trạng thái granted. Đây là một nguồn hỗ trợ điều tra ở mức DBMS; không phải mọi hàng trong pg_locks đều có thể diễn giải dễ dàng thành một dòng dữ liệu bị khóa, và row-level locking có những cơ chế hiển thị riêng.

Để xác định nguồn chặn, thường nên bắt đầu bằng **pg_stat_activity + pg_blocking_pids**, sau đó dùng pg_locks, catalog và công cụ giám sát sâu khi cần.

### 9.4. Có nên hủy session blocker?

Chỉ thực hiện hủy truy vấn hoặc chấm dứt session theo quy trình DBA/SRE và sau khi xác định:

- Session thuộc ứng dụng/job nào.
- Transaction đang thực hiện thao tác gì.
- Dữ liệu có thể bị rollback hoặc ảnh hưởng người dùng thế nào.
- Việc chấm dứt có làm giải phóng đúng khóa đang cần hay không.
- Có phương án thông báo và phục hồi nếu ứng dụng gặp lỗi.

Không tự động terminate backend chỉ vì nó giữ khóa lâu. Ưu tiên xử lý transaction ở tầng ứng dụng hoặc lên lịch migration phù hợp trước khi dùng biện pháp can thiệp mạnh.

## 10. Phân biệt timeout, deadlock và lỗi kết nối

| Triệu chứng | Bản chất thường gặp | Cần kiểm tra |
|---|---|---|
| Liquibase chờ DATABASECHANGELOGLOCK | Một Liquibase khác giữ khóa hoặc trạng thái khóa bất thường | list-locks, tiến trình đang chạy, job CI |
| PostgreSQL báo lock timeout | SQL không lấy được khóa DBMS trong ngưỡng | pg_blocking_pids, transaction blocker, lock_timeout |
| PostgreSQL báo statement timeout | Một câu SQL vượt ngưỡng thời gian | query plan, dữ liệu, wait_event, statement_timeout |
| Deadlock detected | Nhiều transaction chờ khóa theo vòng | Câu lệnh và thứ tự khóa của các transaction, retry policy |
| Connection refused/timeout | Lỗi thiết lập kết nối hoặc mạng | host, port, firewall, DB health, driver |
| Socket read timeout | Client không nhận phản hồi đúng hạn | Trạng thái server-side query/session, mạng, log |
| Job timeout | Orchestrator chấm dứt job | Process còn chạy không, DB session có còn không |
| Out of memory/disk full | Tài nguyên DBMS hoặc runner không đủ | CPU, memory, temp files, WAL/redo, dung lượng đĩa |

Trên PostgreSQL, lỗi timeout hoặc deadlock có thể báo các SQLSTATE khác nhau, chẳng hạn **55P03** cho trường hợp lock not available, **57014** cho query canceled và **40P01** cho deadlock detected. Mã và chi tiết phụ thuộc nguyên nhân, DBMS và cách driver chuyển lỗi; hãy xem thông báo gốc trong log trước khi quyết định retry.

**Deadlock không giống “chờ lâu”.** DBMS có thể phát hiện vòng chờ và chủ động hủy một transaction. Tăng timeout không tự giải quyết nguyên nhân deadlock; cần điều chỉnh thứ tự truy cập/khóa hoặc thiết kế giao dịch.

## 11. Tác động của kiểu migration đến thời gian giữ khóa

| Thao tác | Rủi ro chính | Biện pháp chuẩn bị |
|---|---|---|
| ALTER TABLE thêm cột | Có thể cần khóa bảng mạnh dù thao tác metadata ngắn | Thử trên DBMS/version thật; chọn thời điểm ít giao dịch dài |
| ALTER TABLE thêm NOT NULL/CHECK | Có thể phải kiểm tra dữ liệu hiện có | Làm sạch/backfill trước, đo thời gian validate constraint |
| CREATE INDEX | Dùng I/O, CPU, disk, có thể chặn ghi | Đo thời gian, cân nhắc online/concurrent khi DBMS hỗ trợ |
| DROP INDEX hoặc DROP CONSTRAINT | Phụ thuộc DBMS, có thể ảnh hưởng query và FK | Kiểm tra phụ thuộc và phương án phục hồi |
| UPDATE/DELETE diện rộng | Khóa hàng, WAL/redo, vacuum/undo, replication lag | Batch có kiểm chứng, index phù hợp, hạn chế transaction quá dài |
| Di chuyển/đổi kiểu dữ liệu | Quét bảng, chuyển đổi và log nhiều | Tách bước, làm sạch, thử dữ liệu lớn |
| CREATE OR REPLACE VIEW/FUNCTION | Có thể chờ khóa metadata, ảnh hưởng consumer | Kiểm tra phụ thuộc, hợp đồng cột/chữ ký, lịch phát hành |
| GRANT/REVOKE | Có thể ảnh hưởng truy cập ngay lập tức | Kiểm tra role, quyền hiệu lực, thứ tự triển khai |
| Thêm FOREIGN KEY | Có thể quét dữ liệu và gây khóa | Kiểm tra dữ liệu trước, dùng chiến lược validate theo DBMS |

Một thay đổi “nhanh” trên database rỗng có thể chậm hoặc gây gián đoạn trên database có hàng trăm triệu bản ghi. **Liquibase mô tả và điều phối thay đổi; hành vi khóa và chi phí tài nguyên cuối cùng do DBMS cùng trạng thái dữ liệu quyết định.**

## 12. Giới hạn tài nguyên: không chỉ có thời gian

### 12.1. CPU và bộ nhớ

Tạo index, sắp xếp dữ liệu, quét bảng và kiểm tra ràng buộc có thể dùng CPU và RAM đáng kể. Một số DBMS dùng bộ nhớ theo **mỗi phép toán** hoặc **mỗi worker**, nên cấu hình quá lớn có thể dẫn đến áp lực bộ nhớ khi nhiều phép toán cùng chạy.

Với PostgreSQL, các tham số như work_mem hoặc maintenance_work_mem ảnh hưởng những loại hoạt động khác nhau, nhưng **không phải giới hạn RAM cứng cho toàn database**. Không tự tăng chúng lên rất cao chỉ để một migration chạy nhanh hơn mà chưa đánh giá tổng số kết nối và tác vụ song song.

### 12.2. I/O, temporary files và dung lượng đĩa

Index lớn, sort/hash, cập nhật hàng loạt và việc viết transaction log đều gây I/O. Nếu đĩa lưu data, temporary files hoặc WAL đầy, migration có thể thất bại và ứng dụng cũng chịu ảnh hưởng.

Theo dõi:

- Dung lượng data volume và vùng dành cho index.
- Dung lượng WAL/redo/transaction log và khả năng archive.
- Temporary files, I/O throughput và độ trễ storage.
- Dung lượng dùng bởi bản sao dữ liệu, backup và snapshot.
- Replication lag khi migration tạo nhiều thay đổi.

Không coi statement_timeout là biện pháp giới hạn dung lượng đĩa: một thao tác có thể tiêu thụ tài nguyên đáng kể trước khi hết timeout.

### 12.3. Số kết nối và concurrency

Một CI pipeline chạy nhiều job migration cùng lúc có thể gây chờ khóa dù CPU còn dư. Nhiều replica Spring Boot cùng khởi động có thể thêm kết nối và gây áp lực startup.

Nên:

- Chỉ định **một chủ sở hữu migration** cho từng database/release.
- Giới hạn concurrency ở tầng orchestration, không trông chờ hoàn toàn vào DATABASECHANGELOGLOCK.
- Dùng cấu hình JDBC/pool hợp lý; phân biệt runtime app và job migration.
- Không dùng quá nhiều worker để “tăng tốc” DDL khi DBMS buộc các thao tác phải tuần tự.
- Đặt hạn mức cho mỗi môi trường, đặc biệt production.

### 12.4. Tài nguyên của CI runner

Runner cũng có giới hạn bộ nhớ, CPU, thời gian sống và log artifact. Nếu tiến trình CLI bị kill bởi OOM hoặc job timeout, database có thể còn session/transaction cần kiểm tra. Không kết luận migration đã rollback chỉ từ exit code của runner.

## 13. Điều chỉnh migration để giảm thời gian giữ khóa

### 13.1. Tách thay đổi theo giai đoạn

Chiến lược **expand–migrate–contract** giúp giảm thời gian giữ khóa mạnh và rủi ro xung đột ứng dụng:

1. **Expand:** tạo cấu trúc mới nhưng vẫn tương thích với ứng dụng cũ.
2. **Migrate:** backfill dữ liệu theo kế hoạch, có kiểm tra tiến độ và giới hạn tác động.
3. **Verify:** kiểm tra dữ liệu, dịch vụ, query plan và trạng thái replication.
4. **Contract:** bỏ cấu trúc cũ ở một release sau khi không còn consumer dùng.

Không gom tất cả bước thêm cột, backfill hàng triệu dòng, tạo constraint, đổi tên và drop cột cũ vào một transaction dài chỉ để có một changeset.

### 13.2. Backfill theo batch

Thay vì UPDATE toàn bảng trong một giao dịch, có thể lên kế hoạch các batch nhỏ theo khóa ổn định. Tuy nhiên, cách chia batch, điều kiện dừng, tính lặp lại và checkpoint phải được thiết kế riêng:

- Mỗi batch giới hạn số hàng hoặc khoảng ID.
- Có tiêu chí xác nhận hàng được xử lý và không bỏ sót.
- Giữ tính nhất quán với ứng dụng đang ghi dữ liệu mới.
- Ghi nhận tiến độ ở vị trí tin cậy nếu quy trình cho phép.
- Có khả năng dừng an toàn và tiếp tục sau sự cố.

**Liquibase không tự biến một UPDATE trong changeset thành backfill nhiều transaction nhỏ.** Nếu cần xử lý lớn qua nhiều batch/transaction, có thể cần một job chuyên dụng hoặc chuỗi migration được quản lý rõ, thay vì dùng runInTransaction: false cho một SQL dài.

### 13.3. Chuẩn bị index trước constraint

Một số DBMS cho phép tạo index ít chặn ghi hơn trước rồi dùng index đó để hỗ trợ ràng buộc. Cách này phụ thuộc DBMS/version và yêu cầu SQL đặc thù; phải kiểm tra kỹ transaction boundary và quyền.

Với PostgreSQL, **CREATE INDEX CONCURRENTLY** giúp giảm một số loại blocking nhưng không chạy được trong transaction block thông thường. Trong Liquibase có thể cần changeset riêng với **runInTransaction: false**. Nếu thất bại, nó có thể để lại index không hợp lệ, cần kiểm tra và dọn dẹp có kiểm soát trước khi retry.

Không mặc định mọi thao tác CREATE INDEX là “online” và không ảnh hưởng ứng dụng.

## 14. Ví dụ thực hành: giả lập chờ khóa trên PostgreSQL lab

**Chỉ thực hiện trên database thử nghiệm có thể hủy**, không áp dụng đoạn giả lập giữ khóa lên production.

Chuẩn bị bảng app.orders trong database lab. Mở **hai session PostgreSQL khác nhau**.

### 14.1. Session A: cố ý giữ khóa bảng

~~~sql
BEGIN;
LOCK TABLE app.orders IN ACCESS EXCLUSIVE MODE;

-- Giữ transaction mở trong thời gian ngắn để thử Session B.
-- Sau thí nghiệm, kết thúc bằng COMMIT hoặc ROLLBACK.
~~~

Session A đã yêu cầu khóa mạnh trên app.orders. Nếu các transaction khác đang dùng bảng, chính lệnh LOCK cũng có thể phải chờ. Vì vậy hãy dùng môi trường lab riêng, không làm cùng lúc với workload thật.

### 14.2. Session B: thử giới hạn chờ khóa

~~~sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '30s';

ALTER TABLE app.orders
    ADD COLUMN lock_demo_flag BOOLEAN;

-- Nếu ALTER TABLE báo timeout, chạy ROLLBACK;
-- Nếu thành công, chỉ COMMIT khi muốn giữ thay đổi trên lab.
~~~

Nếu Session A giữ khóa đối nghịch, Session B thường sẽ không lấy được khóa và nhận lỗi lock timeout. Khi transaction B đã bị đánh dấu lỗi, chạy:

~~~sql
ROLLBACK;
~~~

Sau đó kết thúc transaction A:

~~~sql
COMMIT;
~~~

Nếu cần thử lại, phải xác nhận cột lock_demo_flag đã tồn tại chưa. Không chạy lặp lệnh ALTER TABLE mà chưa kiểm tra trạng thái thực.

### 14.3. Quan sát và giải thích

Trong lúc Session B chờ, có thể dùng một session quan sát riêng để chạy truy vấn **pg_blocking_pids** ở mục 9. Các câu hỏi cần trả lời:

- Session nào đang chờ? Session nào giữ khóa?
- Tại sao giới hạn lock_timeout được kích hoạt thay vì statement_timeout?
- Nếu tăng lock_timeout lên rất cao thì những request ứng dụng khác có thể bị ảnh hưởng thế nào?
- Giới hạn job timeout có tự chấm dứt transaction A không?
- Có nên gọi liquibase release-locks trong tình huống này không?

**Kết luận:** không. Đây là xung đột **khóa DBMS** trong thí nghiệm; release-locks xử lý **khóa changelog Liquibase**, không phải khóa ACCESS EXCLUSIVE của session A.

## 15. Ví dụ Liquibase: kiểm tra chính sách timeout trước DDL

Một changeset có thể yêu cầu phiên PostgreSQL chạy migration đã có lock_timeout không bằng 0. Ví dụ này chỉ là một **hàng rào cấu hình bổ sung**, không tự áp đặt ngưỡng chính xác:

~~~yaml
databaseChangeLog:
  - changeSet:
      id: 015-add-order-note
      author: platform-team
      preConditions:
        - onFail: HALT
        - onError: HALT
        - dbms:
            type: postgresql
        - tableExists:
            schemaName: app
            tableName: orders
        - sqlCheck:
            expectedResult: "1"
            sql: |
              SELECT CASE
                  WHEN current_setting('lock_timeout') <> '0' THEN 1
                  ELSE 0
              END
      changes:
        - addColumn:
            schemaName: app
            tableName: orders
            columns:
              - column:
                  name: note
                  type: VARCHAR(500)
      rollback:
        - dropColumn:
            schemaName: app
            tableName: orders
            columnName: note
~~~

**Giả định:** PostgreSQL nhận diện current_setting('lock_timeout'), bảng/cột phù hợp và kết nối migration đã được cấu hình chính sách timeout. Với PostgreSQL, giá trị **0** biểu thị không giới hạn lock timeout; một giá trị khác 0 cho biết có giới hạn, nhưng không chứng minh nó hợp lý với SLO.

Những điểm cần lưu ý:

- Precondition chỉ kiểm tra giá trị của session đang đánh giá, **không phải** tất cả session khác trên server.
- Nếu một hệ thống cấp timeout bằng SET LOCAL ở transaction khác rồi transaction đó kết thúc, điều kiện có thể không đạt.
- Nếu cột note đã tồn tại nhưng changeset chưa có trong DATABASECHANGELOG, addColumn vẫn có thể lỗi; cần kiểm tra cả trạng thái schema thực.
- Rollback dropColumn có thể xóa dữ liệu được ghi sau khi tạo cột, nên không tự động an toàn trên production.
- Kiểm tra timeout không thay thế đánh giá lock, disk, quyền và độ dài của DDL.

Trong thực tế, nhóm có thể kiểm tra cả **statement_timeout**, phiên bản DBMS, tài khoản và database đích tại một bước preflight riêng. Không nên khiến cùng changelog dùng sai giá trị timeout chỉ để “qua được” precondition.

## 16. Spring Boot và nhiều replica khởi động cùng lúc

Trong một ứng dụng Spring Boot có Liquibase tích hợp, migration có thể chạy vào giai đoạn khởi động ứng dụng. Một cụm có nhiều replica cùng bắt đầu sẽ dẫn đến nhiều tiến trình cố đọc/điều phối cùng changelog.

Các tác động có thể gặp:

- Replica A lấy DATABASECHANGELOGLOCK và đang migrate.
- Replica B/C chờ khóa hoặc thất bại vì vượt giới hạn chờ.
- Startup/liveness/readiness policy của orchestrator có thể khởi động lại replica trong lúc migration chưa xong.
- Khi DDL chờ khóa bảng, ứng dụng cũ vẫn đang phục vụ request và có thể tạo blocking chain.
- Nếu startup job bị kill do timeout, cần kiểm tra trạng thái database trước khi retry.

**Lựa chọn kiến trúc:** nếu migration có rủi ro kéo dài, cân nhắc để pipeline CI/CD chạy Liquibase một lần bằng job được kiểm soát, rồi khởi động các replica ứng dụng đã tắt tự động migration production. Ví dụ thuộc tính Spring Boot:

~~~yaml
spring:
  liquibase:
    enabled: false
~~~

Đây chỉ là **một phần cấu hình ví dụ** cho trường hợp migration do job riêng sở hữu. Với môi trường muốn ứng dụng tự migrate, enabled có thể được bật theo thiết kế, nhưng phải quản lý timeout, readiness, concurrency và quyền của datasource cho Liquibase.

Đừng nhầm timeout của HTTP request, connection pool hoặc annotation transaction trong business code với timeout của lệnh Liquibase. Chúng có thể nằm ở những tầng thực thi và connection khác nhau.

## 17. Quy trình CI/CD có giới hạn rủi ro

Một pipeline sản xuất nên định nghĩa **đầu vào**, **ngưỡng an toàn** và **điểm dừng**:

1. **Cố định artifact:** commit changelog, phiên bản Liquibase/Java/JDBC driver và cấu hình môi trường.
2. **Chỉ định một chủ sở hữu migration:** tránh job song song cho cùng database, đặc biệt khi triển khai nhiều service dùng chung schema.
3. **Kiểm tra đích:** host, database, schema, user và quyền thực tế. Tên job “prod” không đủ chứng minh đúng đích.
4. **Kiểm tra trạng thái khóa:** xem job đang chạy, DATABASECHANGELOGLOCK và các session DBMS chờ lâu.
5. **Validate changelog:** kiểm tra cú pháp, định danh changeset và precondition.
6. **Xem trước thay đổi:** chạy status, update-sql, review DDL, index, backfill và rollback.
7. **Đo trên môi trường đại diện:** kiểm thử thời gian, khóa, disk, CPU, WAL/redo, replication lag.
8. **Đặt timeout theo tầng:** JDBC connection, chờ khóa Liquibase, DBMS lock/statement, transaction policy và toàn job.
9. **Chuẩn bị rollback/forward fix và backup:** xác định khả năng phục hồi từng bước và tác động dữ liệu.
10. **Triển khai được quan sát:** log SQLSTATE hoặc lỗi DBMS, thời gian chờ, số changeset thực thi và session blocking.
11. **Hậu kiểm:** DATABASECHANGELOG, cấu trúc schema, dữ liệu, hiệu năng app và replication.
12. **Kết thúc sự cố có kiểm chứng:** trước khi retry phải xác nhận job/session cũ đã kết thúc và trạng thái DB phù hợp.

Ví dụ CLI minh họa:

~~~bash
liquibase --defaults-file=liquibase.properties validate
liquibase --defaults-file=liquibase.properties status --verbose
liquibase --defaults-file=liquibase.properties update-sql
~~~

Chỉ khi vượt qua review và được phép:

~~~bash
liquibase --defaults-file=liquibase.properties update
~~~

Cú pháp lệnh và tên thiết lập cụ thể có thể khác giữa các phiên bản Liquibase; tài liệu cũ đôi khi dùng updateSQL. **validate không ước lượng thời gian khóa**, còn **update-sql không bảo đảm lệnh thật sẽ lấy được khóa trong ngân sách production**.

## 18. Quan sát các chỉ số cần thiết

| Chỉ số | Tín hiệu | Lý do cần theo dõi |
|---|---|---|
| Thời gian chờ DATABASECHANGELOGLOCK | Đợi quá thời gian dự kiến | Có job song song hoặc khóa chưa được giải phóng |
| Số session DBMS chờ khóa | Tăng hoặc kéo dài | Migration có thể gây blocking hoặc bị blocking |
| Thời gian thực thi SQL | Vượt mức kiểm thử | Khối lượng dữ liệu, plan hoặc tài nguyên đã thay đổi |
| Số connection đang hoạt động | Gần giới hạn | Application startup hoặc migration cạnh tranh connection |
| CPU, RAM, swap | Đạt mức bất thường | Query/index có thể quá tốn tài nguyên |
| Disk/WAL/redo usage | Tăng nhanh, gần đầy | Rủi ro lỗi viết và gián đoạn DBMS |
| Temporary files/I/O latency | Tăng khi sort/hash/index | Cần điều chỉnh phương pháp hoặc thời điểm thực thi |
| Replication lag | Kéo dài trong/sau backfill | Replica chưa bắt kịp log thay đổi |
| Error count, SQLSTATE, timeout loại nào | Tăng so với nền | Chẩn đoán nguyên nhân và quyết định dừng |
| Tình trạng migration sau lỗi | DATABASECHANGELOG vs schema thực tế | Tránh retry khi trạng thái chưa chắc chắn |

Một dashboard tốt cần phân biệt **đang chờ khóa changelog**, **đang chờ khóa DBMS** và **đang thực thi SQL nặng**. Chỉ hiển thị “migration duration = 10 phút” không đủ để biết bước tiếp theo nên làm gì.

## 19. Kế hoạch xử lý sự cố khi migration quá thời gian

### 19.1. Bước 1 — Xác định điểm nghẽn

Đọc log Liquibase và log DBMS để trả lời: đang kết nối, đang xin khóa changelog, đang chờ khóa bảng hay đang xử lý câu SQL? Chỉ sau đó mới chọn công cụ kiểm tra tương ứng.

### 19.2. Bước 2 — Xác minh phiên thực thi trước còn tồn tại

Kiểm tra job CI, process CLI, pod Spring Boot, session JDBC và DBA activity. Nếu một job vẫn đang chạy, không khởi động job khác hoặc giải phóng khóa changelog chỉ vì “không thấy log mới”.

### 19.3. Bước 3 — Đánh giá rủi ro dừng

Một lệnh đang sửa dữ liệu lớn có thể cần rollback dài. Một lệnh CREATE INDEX CONCURRENTLY có thể để lại trạng thái index dở dang. Với DBMS có DDL implicit commit, một phần thay đổi có thể đã được commit. Tham khảo runbook khôi phục đúng loại migration.

### 19.4. Bước 4 — Tạm dừng retry, quan sát trạng thái thật

So sánh:

- Bảng **DATABASECHANGELOGLOCK** còn khóa không?
- **DATABASECHANGELOG** đã ghi những changeset nào?
- Cột/bảng/index/function cần tạo đã tồn tại chưa?
- Dữ liệu có bị chuyển đổi một phần không?
- User/ứng dụng còn gặp lỗi hay lock queue đang tăng?
- Backup, replica và log transaction có đủ để phục hồi?

### 19.5. Bước 5 — Chọn cách tiếp tục

Tùy tình huống:

- Chờ transaction blocker hợp lệ kết thúc trong maintenance window.
- Sắp xếp lại lịch migration để ít xung đột.
- Tối ưu SQL hoặc chia backfill thành batch có checkpoint.
- Tăng timeout **có kiểm chứng** nếu thao tác bình thường nhưng cần thêm thời gian.
- Rollback hoặc forward fix nếu schema đã thay đổi không đúng kỳ vọng.
- Giải phóng **stale DATABASECHANGELOGLOCK** chỉ khi đã xác minh không còn holder.
- Giao DBA/SRE can thiệp session DBMS khi thật sự cần và đã đánh giá rủi ro.

Không mặc định “tăng mọi timeout lên 1 giờ” là sửa đúng gốc rễ.

## 20. Những sai lầm dễ gặp

| Sai lầm | Vì sao nguy hiểm? | Hướng làm đúng |
|---|---|---|
| Thấy Liquibase chờ và chạy release-locks ngay | Có thể phá điều phối khi job còn thực thi | Xác minh holder và trạng thái SQL trước |
| Coi DATABASECHANGELOGLOCK là khóa bảng do DDL | Chẩn đoán sai công cụ | Phân biệt Liquibase lock và DBMS lock |
| Coi lock_timeout bằng statement_timeout | Một giới hạn chờ khóa, một giới hạn câu SQL | Xác lập riêng từng ngân sách |
| Tăng timeout khi DBMS bị blocker kéo dài | Có thể kéo dài blocking chain, ảnh hưởng SLO | Xác định blocker và thời điểm triển khai |
| SET LOCAL trong changeset trước rồi kỳ vọng có hiệu lực mãi | SET LOCAL chỉ sống trong transaction | Đặt chính sách trên đúng session/transaction cần dùng |
| Coi JDBC connection timeout là DDL timeout | Kết nối và thực thi là hai giai đoạn khác | Kiểm tra đúng driver, DBMS và job |
| Chạy backfill lớn trong một transaction | Giữ khóa/log lâu, khó rollback | Batch có kiểm chứng, thiết kế idempotency/checkpoint |
| Dùng runInTransaction: false để “nhanh hơn” | Có thể tạo trạng thái áp dụng một phần | Chỉ dùng cho thao tác yêu cầu, có recovery plan |
| Tự động retry sau socket timeout | Không biết server đã hoàn tất SQL hay chưa | Quan sát session, schema và lịch sử trước retry |
| Thử thời gian trên database rỗng rồi áp cho production | Workload, index và data size khác | Thử trên dữ liệu/DBMS đại diện |
| Không đo disk/WAL/replication lag | Có thể hết tài nguyên trước khi timeout | Lập ngân sách I/O và lưu trữ |
| Cho nhiều service migrate cùng database | Tranh khóa và khó điều phối release | Một chủ sở hữu migration và job tuần tự |
| Dùng MARK_RAN để bỏ qua lỗi timeout | Lịch sử có thể đánh dấu sai trạng thái schema | Điều tra và sửa migration có kiểm soát |

## 21. Bài tập phân tích tình huống

**Tình huống A — Hai job cùng cập nhật database**

Pipeline triển khai service A và B đồng thời chạy Liquibase trên cùng database. Job A đang migrate, job B chờ DATABASECHANGELOGLOCK và hết thời gian chờ.

**Phân tích:** trước tiên xác minh A còn hoạt động và lịch sử changelog của từng service có được thiết kế đúng hay không. B không nên giải phóng khóa của A; cần điều phối các job, tránh chạy song song hoặc chọn cách quản lý database ownership rõ ràng. Nếu A đã thất bại, kiểm tra trạng thái thật trước khi cho B retry.

**Tình huống B — DDL nhỏ nhưng lock timeout**

ALTER TABLE ADD COLUMN trên PostgreSQL chỉ cần thay metadata theo kỳ vọng, nhưng luôn lỗi sau 3 giây.

**Phân tích:** nhiều DDL vẫn cần khóa mạnh, có thể phải chờ transaction ứng dụng đang giữ khóa bảng. Dùng pg_blocking_pids và pg_stat_activity để tìm blocker. Giải pháp có thể là xử lý transaction dài, chọn maintenance window hoặc phối hợp ứng dụng; tăng timeout chưa chắc an toàn.

**Tình huống C — Câu UPDATE mất nhiều phút**

Một changeset UPDATE vài triệu bản ghi, chiếm I/O và khiến replication lag tăng mạnh.

**Phân tích:** statement_timeout chỉ giới hạn thời gian câu lệnh, không giảm bản chất khối lượng công việc. Cần xem index, số hàng, batch, WAL, khả năng rollback, replication và lịch ít tải. Có thể chuyển sang backfill chuyên dụng nếu Liquibase một changeset không phù hợp.

**Tình huống D — Runner báo timeout nhưng DBMS vẫn có session**

Job CI bị kill vì quá thời gian; lịch sử DATABASECHANGELOG chưa cập nhật changeset mới, nhưng DBMS vẫn có session chạy SQL hoặc đã có thay đổi một phần.

**Phân tích:** không được retry ngay. Kiểm tra process/session, thay đổi schema và dữ liệu, transaction status, DATABASECHANGELOG và DATABASECHANGELOGLOCK. Chỉ tiếp tục khi có kết luận về mức hoàn tất và đường xử lý trạng thái dở dang.

**Tình huống E — Startup đồng thời nhiều replica Spring Boot**

Năm replica cùng bật Spring Liquibase. Một replica chạy migration lâu; bốn replica khác không sẵn sàng đúng thời hạn và bị orchestrator restart.

**Phân tích:** cần xem lại quyền sở hữu migration, timeout của readiness/startup và cách điều phối rollout. Với DDL dài, job migration riêng trước deploy ứng dụng có thể phù hợp hơn. Không nên tăng thời gian khởi động ứng dụng vô hạn mà không đo ảnh hưởng.

## 22. Checklist trước khi chạy migration có rủi ro khóa

- [ ] Tôi biết database, schema, role và phiên bản DBMS mục tiêu.
- [ ] Tôi phân biệt được DATABASECHANGELOGLOCK và khóa của DBMS.
- [ ] Chỉ có một job được quyền điều phối migration trên database trong lượt phát hành.
- [ ] Tôi đã kiểm tra trạng thái khóa Liquibase và session DBMS trước update.
- [ ] Timeout kết nối, chờ changelog, chờ khóa DBMS, câu SQL và toàn job được xác định theo từng tầng.
- [ ] Chính sách timeout thật sự áp dụng trên kết nối/transaction chạy Liquibase, không chỉ trong terminal khác.
- [ ] Tôi hiểu statement_timeout không thay thế lock_timeout và ngược lại.
- [ ] Các changeset có backfill, index, constraint hoặc DDL dài đã được thử trên dữ liệu đại diện.
- [ ] Có số liệu CPU, RAM, disk, WAL/redo, I/O và replication lag để quyết định dừng.
- [ ] Tôi đã review SQL qua validate, status và update-sql theo phiên bản Liquibase phù hợp.
- [ ] Tôi biết DBMS hỗ trợ DDL transaction ở mức nào và changeset nào dùng runInTransaction: false.
- [ ] Tôi có backup, rollback/forward fix và runbook khi câu SQL bị hủy giữa chừng.
- [ ] Người chịu trách nhiệm có thể nhận diện session blocker qua công cụ DBMS và liên hệ owner.
- [ ] Không tự giải phóng changelog lock, kill DB session hoặc retry khi trạng thái chưa rõ.
- [ ] Sau triển khai có bước kiểm tra schema, dữ liệu, DATABASECHANGELOG và log ứng dụng.
- [ ] Không để secret trong SQL, log hay artifact CI/CD.

## 23. Kết luận

**Thời gian chờ khóa, timeout và giới hạn tài nguyên** là những yếu tố thiết kế của migration, không phải chỉ là tham số chữa cháy khi quá trình triển khai đã treo. Liquibase dùng **DATABASECHANGELOGLOCK** để điều phối các lượt cập nhật, trong khi DBMS áp dụng khóa giao dịch và DDL lên đối tượng/dữ liệu. Từng lớp có timeout, triệu chứng và cách xử lý riêng; một job có thể đã giữ khóa Liquibase nhưng vẫn đang chờ khóa bảng.

Trong module **DATABASE_SCHEMA_MIGRATION_LIQUIBASE**, vận hành migration đáng tin cậy đòi hỏi xác định rõ **ngân sách chờ khóa**, **giới hạn thời gian câu SQL**, **ngân sách CPU/I/O/disk**, **mức song song của các job**, **cách quan sát blocking**, **khả năng rollback hoặc forward fix** và **điều kiện retry**. Khi các thay đổi được thử trên dữ liệu đại diện, triển khai tuần tự và theo dõi cả Liquibase lẫn DBMS, nhóm có thể giảm nguy cơ gián đoạn ứng dụng và giữ lịch sử migration chính xác qua dev, test, production và Spring Boot/CI/CD.

