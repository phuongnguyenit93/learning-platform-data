# Đánh giá pt-online-schema-change/gh-ost theo điều kiện và giới hạn

Thay đổi cấu trúc bảng lớn trên MySQL có thể làm ứng dụng chờ lâu nếu dùng ALTER TABLE theo cách truyền thống. Các công cụ online schema change như **pt-online-schema-change** và **gh-ost** giảm thời gian gián đoạn bằng cách tạo một bảng mới, sao chép dữ liệu theo từng phần, đồng bộ các thay đổi phát sinh trong lúc sao chép rồi chuyển tên bảng ở giai đoạn cutover.

Hai công cụ cùng giải quyết một bài toán nhưng dùng cơ chế đồng bộ khác nhau. pt-online-schema-change (pt-osc) dùng trigger trên bảng nguồn để phản ánh các thay đổi sang bảng mới. gh-ost đọc binary log để thu thập thay đổi và áp dụng vào bảng mới. Cơ chế đó quyết định điều kiện tương thích, tải phát sinh, giới hạn với trigger/foreign key và cách kiểm soát khi chạy.

Bài học thuộc module **DATABASE_MYSQL**, tập trung vào thay đổi schema an toàn: đánh giá công cụ theo cấu trúc bảng, phiên bản MySQL, topology replication, tải ghi, dung lượng, ràng buộc dữ liệu và khả năng phục hồi. Không có công cụ nào bảo đảm ALTER hoàn toàn không khóa; cả hai vẫn cần một khoảng metadata lock ngắn khi cutover.

## 1. Vì sao cần online schema change?

Một lệnh ALTER TABLE trên bảng lớn có thể phải xây lại bảng, tạo index hoặc chuyển đổi dữ liệu. Tùy engine, loại ALTER và phiên bản MySQL, thao tác có thể:

- Chặn ghi hoặc đọc trong một khoảng thời gian.
- Giữ metadata lock và làm các truy vấn khác xếp hàng.
- Tạo tải I/O, CPU và redo/undo log lớn.
- Tạo binary log lớn, làm replica lag tăng.
- Cần thêm dung lượng tạm gần bằng kích thước bảng, thậm chí cao hơn khi tạo index hoặc giữ bản cũ.

MySQL hỗ trợ nhiều thuật toán DDL như INSTANT, INPLACE và COPY. Trước khi chọn công cụ bên ngoài, hãy kiểm tra xem thay đổi có thể dùng DDL online gốc của MySQL hay không:

~~~sql
ALTER TABLE app.orders
  ADD COLUMN source_tag VARCHAR(32) NULL,
  ALGORITHM=INSTANT;
~~~

Ví dụ trên chỉ phù hợp với các thay đổi và phiên bản có hỗ trợ INSTANT. Nếu MySQL báo không hỗ trợ thuật toán chỉ định, hãy đánh giá lại DDL và phiên bản thay vì tự động bỏ ALGORITHM rồi giả định thao tác vẫn không khóa.

Online schema change là phương án cho những thay đổi không thể thực hiện an toàn bằng thuật toán DDL gốc hoặc khi cần kiểm soát chi tiết quá trình sao chép. Nó không biến một thay đổi không tương thích thành thay đổi không rủi ro.

## 2. Cơ chế của pt-online-schema-change

pt-online-schema-change thuộc bộ Percona Toolkit. Công cụ tạo một bảng mới có cấu trúc đã chỉnh sửa, sao chép dữ liệu từ bảng nguồn theo từng chunk và dùng trigger để giữ bảng mới cập nhật khi ứng dụng tiếp tục ghi vào bảng nguồn.

Quy trình ở mức khái quát:

1. Đọc định nghĩa bảng nguồn và tạo bảng đích với thay đổi DDL.
2. Tạo các trigger trên bảng nguồn để phản ánh INSERT, UPDATE và DELETE sang bảng đích.
3. Sao chép dữ liệu hiện có theo từng chunk.
4. Theo dõi tải và replication lag; giảm tốc độ hoặc tạm dừng khi vượt ngưỡng.
5. Khi dữ liệu đã đồng bộ, đổi tên bảng trong giai đoạn cutover.
6. Xử lý bảng cũ theo chính sách giữ lại hoặc xóa sau khi xác minh.

Trigger giúp pt-osc bắt được các thay đổi xảy ra đồng thời với quá trình copy. Tuy nhiên, trigger chạy trong đường ghi của ứng dụng. Vì vậy, mỗi INSERT/UPDATE/DELETE trên bảng nguồn có thể phát sinh thêm công việc ghi vào bảng mới. Với bảng có lưu lượng ghi cao, chi phí trigger có thể ảnh hưởng trực tiếp đến độ trễ giao dịch.

### Điều kiện và giới hạn cần đánh giá

- Công cụ cần tạo trigger trên bảng nguồn; kiểm tra quyền TRIGGER và quyền DDL/DML cần thiết.
- Mặc định, trigger hiện có có thể khiến pt-osc không chạy được vì công cụ cũng cần tạo trigger riêng. Tùy chọn **--preserve-triggers** hỗ trợ bảo toàn trigger hiện có từ MySQL 5.7.2 trở lên, nhưng phải kiểm tra trigger có tham chiếu cột bị xóa/đổi tên hay không và thử đúng phiên bản toolkit.
- Bảng cần có primary key hoặc unique key phù hợp để chia chunk và xác định hàng.
- Bảng có foreign key tham chiếu đến nó cần phương án xử lý riêng khi đổi bảng. pt-osc có các lựa chọn như rebuild constraint hoặc drop/rename trong một số tình huống; mỗi lựa chọn có tác động và giới hạn khác nhau.
- Trigger bổ sung làm tăng tải ghi, có thể kéo dài transaction hoặc gây vấn đề với workload nhạy cảm về latency.
- Các thay đổi DDL phức tạp, generated column, partition, view, trigger, constraint và kiểu dữ liệu cần được thử với đúng phiên bản công cụ.

### Foreign key với pt-osc

Foreign key là một trong các điều kiện quyết định có thể dùng pt-osc hay không. Khi bảng nguồn được tham chiếu bởi bảng con, việc đổi sang bảng mới có thể yêu cầu cập nhật lại constraint ở các bảng con.

pt-osc cung cấp các phương án qua tùy chọn **--alter-foreign-keys-method**. Các phương án thường được cân nhắc gồm:

- **rebuild_constraints:** thay đổi constraint ở các bảng con để tham chiếu bảng mới. Có thể cần ALTER trên bảng con, tạo tải và metadata lock; bảng con lớn làm cutover phức tạp hơn.
- **drop_swap:** dùng thao tác drop/rename trong quy trình đổi bảng. Phương án này có rủi ro cao hơn nếu quá trình bị gián đoạn ở thời điểm nhạy cảm; không chọn nếu chưa hiểu rõ cửa sổ mà bảng nguồn có thể không tồn tại và chưa có phương án khôi phục.

Tên và hành vi tùy chọn phải được xác nhận bằng tài liệu của phiên bản Percona Toolkit đang cài. Phương án **drop_swap** tắt kiểm tra foreign key, drop bảng nguồn rồi mới rename bảng mới vào vị trí; trong khoảng giữa hai thao tác, bảng không tồn tại và lỗi rename có thể khiến bảng cũ mất vĩnh viễn. Chỉ cân nhắc khi đã chấp nhận rõ rủi ro này và có phương án phục hồi đã kiểm chứng. Trước khi chạy, liệt kê toàn bộ bảng con và constraint tham chiếu đến bảng nguồn, ước lượng kích thước và thời gian ALTER của từng bảng con.

### Ví dụ chạy thử

~~~bash
pt-online-schema-change \
  --alter "ADD COLUMN source_tag VARCHAR(32) NULL" \
  D=app,t=orders \
  --dry-run
~~~

**--dry-run** chỉ tạo và ALTER bảng mới để kiểm tra DDL; nó không tạo trigger, không copy dữ liệu và không thực hiện cutover. Vì vậy, dry-run không đo được thời gian copy hoặc tải thực tế. Muốn diễn tập copy gần thực tế hơn, có thể đánh giá **--no-swap-tables** trên môi trường kiểm thử; tùy chọn này vẫn tạo bảng mới và copy dữ liệu, sau đó dọn bảng mới mà không đổi bảng nguồn. Cần xác nhận hành vi cleanup và tác động theo phiên bản trước khi chạy.

Sau khi xem log, kiểm tra quyền, trigger, tải và phương án cutover, có thể lập lệnh thực thi riêng:

~~~bash
pt-online-schema-change \
  --alter "ADD COLUMN source_tag VARCHAR(32) NULL" \
  D=app,t=orders \
  --max-load Threads_running=25 \
  --critical-load Threads_running=50 \
  --chunk-time 0.5 \
  --max-lag 2 \
  --execute
~~~

Đây là cấu hình minh họa. Giá trị tải phải được chọn theo baseline của hệ thống; ngưỡng quá thấp có thể khiến tiến trình liên tục dừng, còn ngưỡng quá cao có thể làm ảnh hưởng ứng dụng. Tên tùy chọn, đơn vị và hành vi có thể khác theo phiên bản toolkit.

## 3. Cơ chế của gh-ost

gh-ost là công cụ online schema migration cho MySQL, dùng binary log để thu thập các thay đổi phát sinh trên bảng nguồn và áp dụng chúng vào bảng đích. Công cụ tạo bảng ghost, copy dữ liệu theo chunk, đọc sự kiện thay đổi và đồng bộ dữ liệu trước khi cutover.

Quy trình khái quát:

1. Kết nối đến topology MySQL và xác định nguồn binary log phù hợp.
2. Tạo bảng ghost với cấu trúc mới theo câu lệnh ALTER được yêu cầu.
3. Copy các hàng hiện có theo chunk.
4. Đọc row event từ binary log và áp dụng các thay đổi tương ứng vào bảng ghost.
5. Điều chỉnh tốc độ copy, theo dõi độ trễ và chờ đến khi bảng ghost bắt kịp.
6. Thực hiện cutover bằng thao tác đổi tên bảng.
7. Giữ hoặc dọn bảng cũ theo cấu hình và quy trình vận hành.

Do dùng binlog thay vì trigger trên bảng nguồn, gh-ost không thêm trigger đồng bộ vào đường ghi của ứng dụng, nhờ đó tránh được phần chi phí trigger trên mỗi lần ghi. Tuy nhiên, theo tài liệu giới hạn hiện hành, gh-ost không hỗ trợ bảng có trigger; đây không phải lựa chọn thay thế cho pt-osc trên một bảng đang có trigger. Công cụ phụ thuộc chặt vào cấu hình binary log, row event và khả năng đọc log của topology.

### Điều kiện tương thích

Trước khi dùng gh-ost, kiểm tra tối thiểu:

- Binary logging đã bật và công cụ có thể đọc được binary log từ nguồn đã chọn.
- Theo tài liệu yêu cầu của gh-ost, cần ít nhất một máy chủ cung cấp binary log ở định dạng row-based; row image được hỗ trợ là **FULL**. Nếu đọc binlog từ replica, schema bảng trên replica phải giống schema trên source. gh-ost ưu tiên đọc từ replica; trong mô hình này, source có thể vẫn dùng statement-based logging nếu replica cung cấp row-based log phù hợp.
- Tài liệu gh-ost hiện hành yêu cầu MySQL 5.7 trở lên. Xác minh lại phiên bản tối thiểu và matrix hỗ trợ theo bản gh-ost được cài.
- Có đủ binary log liên tục trong suốt thời gian migration; không để retention hoặc purge xóa file mà công cụ còn cần đọc.
- Tài khoản có các quyền đọc metadata, đọc binlog, tạo bảng, ghi dữ liệu và thực hiện cutover theo tài liệu của phiên bản.
- Bảng có primary key hoặc unique key phù hợp để copy và áp dụng thay đổi.
- Topology replication, hostname, channel, replica và nguồn binlog được gh-ost nhận diện đúng.
- Đã đánh giá khả năng tương thích với foreign key, trigger, partition và các đặc điểm DDL của bảng. gh-ost có giới hạn riêng với một số cấu trúc; phải kiểm tra matrix hỗ trợ của phiên bản thay vì suy luận từ việc công cụ kết nối thành công.

gh-ost yêu cầu row-based binary logging và hiện hỗ trợ row image **FULL**. **MINIMAL** chưa được hỗ trợ trong yêu cầu của dự án được tham chiếu. Kiểm tra cấu hình trên máy chủ thực sự được dùng làm nguồn binlog:

~~~sql
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW VARIABLES LIKE 'binlog_row_metadata';
SHOW BINARY LOGS;
~~~

Đối chiếu các giá trị với tài liệu gh-ost đúng phiên bản. Không tự động thay đổi cấu hình binary log trên production chỉ để làm cho công cụ chạy; thay đổi này ảnh hưởng cả replication và các consumer binlog khác.

### Các giới hạn quan trọng của gh-ost

Theo tài liệu yêu cầu và giới hạn của dự án:

- **Foreign key không được hỗ trợ.** Nếu bảng có constraint foreign key, cần chọn phương án khác hoặc thiết kế migration nhiều giai đoạn sau khi đánh giá đầy đủ phụ thuộc.
- **Trigger không được hỗ trợ.** Không dùng gh-ost cho bảng có trigger cần duy trì nếu phiên bản đang chạy vẫn áp dụng giới hạn này.
- Bảng nguồn và bảng đích phải có cùng primary key hoặc unique key dùng làm migration key. Các cột trong khóa này không được chứa NULL; unique key nullable không được chấp nhận mặc định.
- Migration key chứa cột ENUM có thể làm hiệu năng suy giảm đáng kể.
- Binary log mã hóa không được hỗ trợ theo tài liệu hiện hành.
- Multi-source replication khi đọc qua replica không được hỗ trợ. Topology master-master chỉ hỗ trợ active-passive; active-active có ghi đồng thời ở cả hai master không được hỗ trợ.
- Một số loại bảng hoặc thao tác ALTER, chẳng hạn FEDERATED và đổi tên bảng bằng ALTER RENAME, không thuộc phạm vi hỗ trợ.

Các giới hạn này phải được xác nhận lại với phiên bản gh-ost thực tế. Không chọn gh-ost chỉ vì hệ thống có row binlog; foreign key, trigger và topology có thể loại công cụ khỏi danh sách ngay từ bước preflight.

### Throttle và kiểm soát cutover

gh-ost có các cơ chế điều chỉnh tốc độ theo tải máy chủ, replica lag và tín hiệu điều khiển. Có thể kết hợp ngưỡng tải, giới hạn độ trễ, cờ tạm dừng và cờ hoãn cutover để DBA chủ động chọn thời điểm chuyển bảng.

Ví dụ khung lệnh minh họa:

~~~bash
gh-ost \
  --host=mysql-primary.example \
  --database=app \
  --table=orders \
  --alter="ADD COLUMN source_tag VARCHAR(32) NULL" \
  --user=schema_migrator \
  --max-load=Threads_running=25 \
  --critical-load=Threads_running=50 \
  --max-lag-millis=1500 \
  --chunk-size=1000 \
  --postpone-cut-over-flag-file=/tmp/gh-ost.postpone \
  --execute
~~~

Đây là ví dụ minh họa, cần bổ sung tham số topology, xác thực và quyền theo môi trường. Đường dẫn cờ điều khiển phải được tạo và quản lý trên đúng máy chạy gh-ost. Chỉ xóa cờ hoãn cutover sau khi DBA đã xác nhận ứng dụng sẵn sàng chuyển bảng.

## 4. So sánh hai công cụ

| Tiêu chí | pt-online-schema-change | gh-ost |
|---|---|---|
| Cơ chế đồng bộ | Trigger trên bảng nguồn | Đọc binary log và áp dụng row event |
| Tác động lên đường ghi ứng dụng | Trigger làm phát sinh thêm DML | Không thêm trigger đồng bộ vào bảng nguồn |
| Yêu cầu binary log | Không dựa vào binlog để đồng bộ thay đổi bảng theo cơ chế chính | Phụ thuộc row-based binlog và khả năng đọc log |
| Trigger có sẵn | Mặc định không chạy nếu có trigger; có thể đánh giá --preserve-triggers trên MySQL 5.7.2+ và kiểm thử tương thích | Không hỗ trợ trigger theo tài liệu yêu cầu hiện hành |
| Foreign key | Có rebuild_constraints và drop_swap; cả hai cần đánh giá tác động, drop_swap có khoảng thời gian bảng không tồn tại | Không hỗ trợ foreign key theo tài liệu yêu cầu hiện hành |
| Row image | Không dùng row image làm cơ chế đồng bộ chính | Cần row-based binlog với FULL row image theo tài liệu yêu cầu hiện hành |
| Kiểm soát cutover | Công cụ thực hiện rename sau khi đồng bộ | Có cơ chế hoãn cutover bằng flag và điều khiển thời điểm rõ ràng |
| Điều chỉnh tải | Chunk time, max-load, critical-load, max-lag và pause file | Chunk size, max-load, critical-load, replica lag và flag điều khiển |
| Phù hợp khi | Môi trường đáp ứng yêu cầu trigger và FK có phương án an toàn | Có row binlog phù hợp, muốn tránh trigger và cần điều khiển migration qua binlog |

Không có công cụ thắng trong mọi trường hợp. Chọn theo điều kiện thực tế của bảng, phiên bản, topology, tải ghi, ràng buộc và quy trình vận hành.

## 5. Những điều kiện phải kiểm tra trước khi chọn

### Kích thước bảng và dung lượng đĩa

Trong phần lớn quy trình, công cụ phải giữ bảng nguồn và bảng ghost cùng tồn tại trong lúc copy. Dung lượng cần thiết không chỉ bằng kích thước bảng nguồn:

- Bảng ghost sau khi thay đổi có thể lớn hơn do thêm cột hoặc index.
- Index mới cần dung lượng riêng và có thể tạo thêm temporary space.
- Binary log, relay log, redo log và undo log có thể tăng trong quá trình copy.
- Bảng cũ có thể được giữ lại sau cutover để phục hồi hoặc điều tra.

Ước lượng dung lượng cho cả data directory và filesystem chứa binlog. Để có biên an toàn, đo kích thước thực tế và chạy thử trên bản sao dữ liệu đại diện; không dùng một hệ số cố định cho mọi bảng.

### Tốc độ ghi và transaction dài

pt-osc phải thực hiện thêm thao tác trigger cho các DML trên bảng nguồn. gh-ost phải đọc và áp dụng các thay đổi từ binlog trong khi vẫn copy dữ liệu. Cả hai đều chịu ảnh hưởng khi write rate cao hoặc transaction kéo dài.

Nếu tốc độ phát sinh thay đổi vượt khả năng áp dụng của công cụ, backlog sẽ tăng. Điều này kéo dài migration, tăng dung lượng log cần giữ và có thể đẩy replica lag lên cao. Cần đo write rate, kích thước transaction, số hàng cập nhật và thời gian chạy thử để chọn chunk size, chunk time và throttle phù hợp.

### Primary key và unique key

Một khóa ổn định giúp công cụ chia chunk, tìm hàng và áp dụng thay đổi chính xác. Bảng không có primary key hoặc unique key phù hợp làm tăng độ phức tạp và có thể không được hỗ trợ theo cách mong muốn.

Không thêm primary key tùy tiện cùng lúc với một migration lớn nếu chưa phân tích chi phí và cách công cụ xác định hàng. Hãy tách bước thay đổi nếu cần, kiểm thử kế hoạch DDL và đánh giá ảnh hưởng đến replication.

### Foreign key, trigger và partition

Liệt kê các phụ thuộc trước khi chạy:

~~~sql
-- Kiểm tra định nghĩa và index của bảng
SHOW CREATE TABLE app.orders\G
SHOW INDEX FROM app.orders;

-- Tìm các foreign key tham chiếu đến bảng orders
SELECT
  TABLE_SCHEMA,
  TABLE_NAME,
  CONSTRAINT_NAME,
  COLUMN_NAME,
  REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE REFERENCED_TABLE_SCHEMA = 'app'
  AND REFERENCED_TABLE_NAME = 'orders';

-- Kiểm tra trigger gắn với bảng
SHOW TRIGGERS FROM app LIKE 'orders';
~~~

Ngoài ra, kiểm tra partition, generated column, check constraint, view, routine, event và các đối tượng phụ thuộc. Một lệnh ALTER trên bảng không tồn tại độc lập; thay đổi có thể ảnh hưởng các ứng dụng, báo cáo và quy trình ETL.

### Phiên bản MySQL và phiên bản công cụ

Khả năng DDL, metadata lock, hỗ trợ nhiều trigger, row event và quyền quản trị khác nhau giữa các bản MySQL. Percona Toolkit và gh-ost cũng có thay đổi theo phiên bản. Ghi lại chính xác phiên bản server, toolkit, gh-ost và hệ điều hành trong kế hoạch migration.

Không chạy bản công cụ cũ trên server mới chỉ vì câu lệnh có vẻ tương thích. Đọc release notes, kiểm tra các issue đã biết và chạy thử trên bản sao có cùng phiên bản, cấu hình và kích thước dữ liệu.

## 6. Đánh giá DDL có phù hợp với công cụ không?

Không phải mọi ALTER TABLE đều có thể chuyển trực tiếp thành online schema change. Trước khi lập lệnh, phân tích thay đổi dự kiến:

- Thêm hoặc xóa cột, đổi kiểu dữ liệu, đổi charset/collation.
- Thêm, xóa hoặc thay đổi index và unique constraint.
- Thay đổi primary key.
- Thay đổi partition hoặc engine.
- Đổi nullable/default, generated column hoặc biểu thức.
- Thay đổi có làm dữ liệu hiện tại không còn hợp lệ hay không.

Một số thay đổi cần chuyển đổi từng hàng. Ví dụ đổi kiểu cột từ VARCHAR sang kiểu số có thể thất bại hoặc làm mất dữ liệu nếu có giá trị không chuyển đổi được. Công cụ online schema change chỉ thực hiện việc copy và áp dụng DDL; nó không tự xác định ý nghĩa nghiệp vụ của dữ liệu chuyển đổi.

### Kiểm tra dữ liệu trước khi đổi kiểu

Giả sử cần chuyển cột quantity từ VARCHAR sang INT. Trước tiên tìm các giá trị không chuyển đổi được:

~~~sql
SELECT quantity
FROM app.inventory
WHERE quantity IS NOT NULL
  AND quantity NOT REGEXP '^-?[0-9]+$'
LIMIT 100;
~~~

Tiếp tục kiểm tra phạm vi giá trị, NULL, chuỗi rỗng, số vượt giới hạn và các giá trị có khoảng trắng. Xác định cách xử lý dữ liệu lỗi trước khi chạy DDL.

### Không phải ALTER nào cũng nên chạy online

Nếu thay đổi có thể dùng INSTANT hoặc INPLACE an toàn trên đúng phiên bản, DDL gốc của MySQL thường đơn giản hơn và ít thành phần vận hành hơn. Nếu thay đổi yêu cầu COPY, online schema change có thể giảm thời gian chặn ghi nhưng vẫn phải copy toàn bộ dữ liệu và thực hiện cutover.

Đối với thay đổi có chuyển đổi dữ liệu phức tạp, cần viết migration theo nhiều giai đoạn: thêm cột mới, dual-write hoặc backfill có kiểm soát, xác minh dữ liệu, chuyển ứng dụng đọc sang cột mới rồi mới xóa cột cũ. Cách này thường an toàn hơn việc ép một ALTER lớn chuyển đổi toàn bộ bảng.

## 7. Metadata lock và cutover

Điểm quan trọng nhất của cả pt-osc và gh-ost là cutover. Sau khi bảng mới đã được copy và đồng bộ, công cụ cần đổi tên bảng cũ và bảng mới để ứng dụng bắt đầu sử dụng cấu trúc mới.

Thao tác rename cần metadata lock. Nếu có transaction dài, truy vấn giữ metadata lock, hoặc session đang truy cập bảng trong thời điểm cutover, công cụ có thể phải chờ. Một yêu cầu metadata lock đang chờ cũng có thể làm các truy vấn mới xếp hàng phía sau, gây ra hiện tượng ứng dụng tưởng như bị treo dù thời gian đổi tên dự kiến rất ngắn.

Trước cutover:

1. Kiểm tra transaction đang mở và truy vấn chạy lâu.
2. Kiểm tra metadata lock trên bảng nguồn và bảng ghost.
3. Xác nhận replication lag đã trong ngưỡng chấp nhận.
4. Xác nhận bảng ghost đã bắt kịp dữ liệu nguồn.
5. Xác nhận ứng dụng tương thích với schema mới.
6. Chọn thời điểm có lưu lượng thấp và có người theo dõi.

Có thể xem transaction đang mở:

~~~sql
SELECT
  trx_id,
  trx_mysql_thread_id,
  trx_started,
  trx_state,
  trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Metadata lock có thể được quan sát qua Performance Schema:

~~~sql
SELECT
  OBJECT_SCHEMA,
  OBJECT_NAME,
  LOCK_TYPE,
  LOCK_DURATION,
  LOCK_STATUS,
  OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = 'app'
  AND OBJECT_NAME = 'orders';
~~~

Các cột và quyền truy vấn phụ thuộc phiên bản, cấu hình instrumentation và quyền Performance Schema. Cần đối chiếu trạng thái thực tế trước khi cutover.

### Giới hạn của cutover

- Không thể bảo đảm cutover không chờ metadata lock.
- Transaction dài có thể khiến thời gian chờ vượt quá cửa sổ bảo trì.
- Một số thao tác DDL hoặc phụ thuộc foreign key làm rename phức tạp hơn.
- Nếu ứng dụng giữ prepared statement hoặc metadata cache, cần xác minh hành vi sau khi cấu trúc thay đổi.
- Nếu công cụ bị dừng ở giai đoạn cutover, phải đọc trạng thái và log trước khi quyết định chạy tiếp hoặc khôi phục.

Không tự ý kill session chỉ vì thấy metadata lock đang chờ. Xác định chủ sở hữu transaction, tác động nghiệp vụ và quy trình xử lý blocking session trước.

## 8. Throttle, replica lag và tác động lên topology

Copy bảng lớn tạo ra nhiều lần đọc từ bảng nguồn và ghi vào bảng ghost. Các thay đổi được đồng bộ cũng tạo thêm công việc. Trên topology replication, những thao tác này có thể làm tăng binary log, relay log, hàng đợi applier và độ trễ replica.

### Theo dõi tải máy chủ

Chọn các chỉ số có baseline:

- Threads_running và số kết nối đang hoạt động.
- CPU, IOPS, throughput và latency của storage.
- Dung lượng data directory, temporary space và binary log.
- InnoDB history list length, redo pressure và thời gian transaction.
- Replica lag, trạng thái I/O/applier và độ lớn hàng đợi relay log.
- Latency của truy vấn ứng dụng và tỷ lệ timeout.

Không chỉ nhìn một chỉ số. Ví dụ Threads_running có thể thấp trong khi storage latency tăng mạnh; replica lag có thể thấp lúc đầu nhưng tăng nhanh khi tốc độ copy vượt năng lực apply.

### Điều chỉnh tốc độ

Với pt-osc, thường điều chỉnh chunk time, max-load, critical-load, max-lag và pause file. Với gh-ost, thường điều chỉnh chunk size, max-load, critical-load, max-lag và các cờ throttle/cutover. Tên, đơn vị và khả năng của từng tùy chọn cần được xác nhận theo bản công cụ.

Nguyên tắc:

- Bắt đầu với chunk nhỏ và tốc độ thận trọng.
- Quan sát tác động trên nguồn và tất cả replica.
- Tăng tốc từng bước khi latency và lag ổn định.
- Tạm dừng khi vượt ngưỡng; không chờ đến khi hệ thống mất khả năng phục vụ.
- Chỉ tiếp tục sau khi đã xác định nguyên nhân và hệ thống hồi phục.

Nếu công cụ đọc binlog từ replica, vẫn phải kiểm tra replica đó có theo kịp nguồn và giữ đủ log. Việc đọc từ replica có thể giảm một phần tải đọc binlog trên primary nhưng không làm biến mất tải ghi do migration và không loại bỏ tác động replication của bảng ghost.

### Tác động đến backup và PITR

Trong lúc migration, binary log có thể tăng nhanh. Kiểm tra retention, dung lượng và khả năng sao lưu binlog. Không purge log cần thiết cho replica hoặc cửa sổ point-in-time recovery chỉ để giải phóng dung lượng migration.

Nếu có backup đang chạy hoặc backup lock, xác minh công cụ schema change có thể hoạt động cùng quy trình đó không. Tránh để cutover trùng với thao tác backup, DDL khác hoặc chuyển đổi topology chưa được điều phối.

## 9. Quyền và tài khoản vận hành

Không dùng tài khoản ứng dụng production để chạy schema change. Tạo tài khoản migration riêng và cấp quyền theo đúng công cụ, phiên bản, thao tác và topology.

Các quyền thường cần xem xét:

- Đọc metadata và dữ liệu bảng nguồn.
- Tạo, sửa, ghi và xóa bảng ghost.
- Tạo trigger nếu dùng pt-osc.
- Đọc trạng thái replication hoặc binary log nếu dùng gh-ost.
- Thực hiện thao tác rename/cutover và dọn bảng theo chính sách.
- Đọc các bảng Performance Schema hoặc thông tin trạng thái để throttle.

Danh sách quyền chính xác phụ thuộc phiên bản công cụ và cách kết nối. Hãy dùng tài liệu chính thức của phiên bản được cài để lập GRANT tối thiểu, rồi thử trong môi trường kiểm thử. Không cấp SUPER hoặc quyền quản trị toàn cục chỉ để tránh tìm hiểu quyền thực sự cần thiết.

Ví dụ khung tài khoản:

~~~sql
CREATE USER 'schema_migrator'@'10.20.%'
  IDENTIFIED BY 'REPLACE_WITH_SECRET';
~~~

Sau đó cấp từng quyền đã xác định theo công cụ và schema. Bí mật phải được lấy từ secret manager, không đặt trong shell history, script chia sẻ hoặc tài liệu migration.

## 10. Khi nào chọn pt-online-schema-change?

pt-osc có thể là lựa chọn phù hợp khi:

- Môi trường cho phép tạo trigger trên bảng nguồn.
- Không có trigger hiện hữu gây xung đột, hoặc phiên bản toolkit có cách bảo toàn trigger đã được thử nghiệm.
- Foreign key có phương án xử lý rõ ràng, chi phí ALTER bảng con chấp nhận được.
- Không thể hoặc không muốn dựa vào yêu cầu row-based binlog của gh-ost.
- Đội vận hành đã quen Percona Toolkit và có quy trình giám sát chunk, tải, lag và cutover.

Không nên chọn pt-osc chỉ vì công cụ đã có sẵn trong bộ toolkit. Nếu bảng có lưu lượng ghi rất cao, trigger làm tăng chi phí trên mỗi giao dịch có thể gây tác động lớn. Nếu có nhiều foreign key hoặc trigger phức tạp, cần chạy thử trên bản sao dữ liệu trước khi quyết định.

## 11. Khi nào chọn gh-ost?

gh-ost có thể là lựa chọn phù hợp khi:

- Binary log và topology đáp ứng các yêu cầu của gh-ost.
- Có thể dùng row-based binlog với row image phù hợp.
- Muốn đồng bộ thay đổi qua binlog thay vì thêm trigger vào bảng nguồn.
- Cần điều khiển tốc độ và hoãn cutover cho đến khi có tín hiệu từ người vận hành.
- Các giới hạn về foreign key, trigger, partition và DDL không ảnh hưởng đến bảng được migration.

Không nên chọn gh-ost nếu chưa kiểm tra được luồng binlog, retention, quyền đọc log và topology. Nếu server không đáp ứng row format hoặc log bị purge trước khi công cụ đọc xong, migration có thể thất bại hoặc không bắt kịp thay đổi.

## 12. Quy trình đánh giá trước khi chạy production

**Giai đoạn 1 — Khảo sát bảng**

- Ghi lại DDL, kích thước dữ liệu và index.
- Xác định primary key, unique key, foreign key, trigger và partition.
- Tìm view, routine, event và ứng dụng phụ thuộc.
- Đo write rate, transaction dài, giờ cao điểm và replica lag.
- Xác định DDL có thể dùng INSTANT/INPLACE của MySQL hay không.

**Giai đoạn 2 — Kiểm tra công cụ**

- Ghi lại phiên bản MySQL, Percona Toolkit hoặc gh-ost.
- Kiểm tra ma trận hỗ trợ DDL và cấu trúc bảng.
- Kiểm tra quyền tài khoản migration.
- Với pt-osc, xác minh trigger và phương án foreign key.
- Với gh-ost, xác minh máy chủ cung cấp row-based binlog, binlog_row_image=FULL, nguồn binlog, schema trên replica và retention.

**Giai đoạn 3 — Diễn tập**

- Dùng bản sao dữ liệu có kích thước và write rate gần production.
- Chạy dry run hoặc chế độ kiểm tra được công cụ hỗ trợ.
- Đo thời gian copy, lượng binlog, dung lượng tạm và replica lag.
- Thử dừng, resume, throttle và cutover.
- Kiểm tra hành vi ứng dụng với schema mới.

**Giai đoạn 4 — Chuẩn bị triển khai**

- Có backup hợp lệ và xác minh khả năng phục hồi.
- Có ngưỡng tải, ngưỡng lag và người chịu trách nhiệm dừng migration.
- Có cửa sổ cutover, cách theo dõi metadata lock và kế hoạch xử lý blocker.
- Có kế hoạch giữ bảng cũ, xác minh dữ liệu và rollback.
- Thông báo cho các đội ứng dụng, DBA và vận hành theo quy trình nội bộ.

## 13. Chạy migration và xác minh kết quả

Trong lúc chạy, theo dõi log công cụ và các chỉ số nguồn/replica. Không chỉ chờ tiến trình báo hoàn thành. Trước và sau cutover, cần xác minh:

- Bảng mới có cấu trúc đúng với DDL yêu cầu.
- Số hàng và dữ liệu quan trọng khớp với bảng nguồn.
- Index, constraint, trigger và các đối tượng liên quan tồn tại đúng.
- Ứng dụng đọc/ghi được bằng phiên bản schema mới.
- Replica bắt kịp và không có lỗi SQL applier.
- Query latency, error rate và connection pool trở lại mức bình thường.

Ví dụ kiểm tra cấu trúc và số hàng:

~~~sql
SHOW CREATE TABLE app.orders\G
SHOW INDEX FROM app.orders;
SELECT COUNT(*) FROM app.orders;
~~~

Với bảng lớn, COUNT(*) có thể tốn tài nguyên tùy engine và trạng thái hệ thống. Có thể dùng thống kê, so sánh theo khoảng primary key hoặc checksum theo chunk, nhưng phải hiểu độ chính xác và thời điểm snapshot của từng cách. Không so sánh nguồn đang thay đổi với replica đang lag rồi kết luận ngay rằng migration làm mất dữ liệu.

## 14. Rollback và xử lý migration thất bại

Rollback cần được thiết kế trước khi chạy. Giữ bảng cũ sau cutover có thể giúp điều tra hoặc phục hồi trong một số tình huống, nhưng không tự động tạo ra một phương án quay lui an toàn.

Sau cutover, ứng dụng có thể đã ghi dữ liệu mới vào bảng mới. Nếu đổi tên ngược lại bảng cũ mà không đồng bộ các thay đổi phát sinh, dữ liệu mới sẽ mất. Vì vậy:

- Chỉ giữ bảng cũ theo thời gian đã định và bảo vệ khỏi thao tác xóa nhầm.
- Không coi rename ngược là rollback hoàn chỉnh nếu dữ liệu đã phát sinh sau cutover.
- Nếu phát hiện schema sai nhưng dữ liệu vẫn đúng, đánh giá một migration sửa tiếp hoặc quy trình đồng bộ ngược.
- Nếu có mất dữ liệu hoặc sai lệch, dừng ghi theo quy trình sự cố, bảo toàn log và backup, rồi xác định điểm phục hồi.
- Không xóa bảng cũ hoặc bảng ghost khi chưa xác minh trạng thái cuối cùng.

Nếu công cụ dừng giữa chừng, đọc log và xác định nó đang ở giai đoạn tạo bảng, copy, đồng bộ hay cutover. Không chạy lại ngay với cùng tên bảng phụ trợ nếu chưa xác định các bảng tạm và trigger còn lại. Dùng lệnh cleanup của đúng công cụ và phiên bản sau khi hiểu tác động.

## 15. Bảng quyết định lựa chọn

| Điều kiện môi trường | Hướng đánh giá |
|---|---|
| Bảng có trigger hiện hữu quan trọng | Kiểm tra --preserve-triggers của pt-osc, phiên bản MySQL và trigger có tham chiếu cột bị đổi hay không; gh-ost không hỗ trợ trigger theo tài liệu hiện hành |
| Bảng có foreign key tham chiếu | Phân tích rebuild_constraints hoặc rủi ro drop_swap của pt-osc; gh-ost không hỗ trợ foreign key theo tài liệu hiện hành |
| Binary log không ở ROW hoặc row image không phù hợp | Không chạy gh-ost cho đến khi xử lý điều kiện binlog và đánh giá tác động topology |
| Bảng có write rate cao | Đánh giá chi phí trigger của pt-osc và năng lực đọc/apply binlog của gh-ost; chạy thử với tải thực |
| Replica lag đang cao | Hoãn migration hoặc giảm tốc; không bắt đầu chỉ vì primary còn đủ tài nguyên |
| Không đủ dung lượng cho bảng nguồn và bảng ghost | Không chạy; mở rộng storage hoặc thiết kế migration nhiều giai đoạn |
| DDL hỗ trợ INSTANT an toàn | Ưu tiên đánh giá DDL gốc của MySQL trước |
| Bảng không có khóa duy nhất phù hợp | Thiết kế lại khóa hoặc chọn phương án migration khác sau khi thử nghiệm |
| Cần kiểm soát cutover thủ công | Đánh giá cơ chế postpone-cut-over của gh-ost và quy trình cutover của pt-osc |

Đây là bảng định hướng, không thay thế kiểm tra tài liệu phiên bản. Các giới hạn cụ thể có thể thay đổi giữa các bản phát hành công cụ.

## 16. Checklist cuối cùng

- [ ] Đã xác định ALTER có thể dùng INSTANT/INPLACE của MySQL hay không.
- [ ] Đã đọc DDL và kiểm tra PK/unique key, FK, trigger, partition.
- [ ] Đã xác định phiên bản MySQL và phiên bản công cụ được hỗ trợ.
- [ ] Đã kiểm tra quyền tối thiểu cho tài khoản migration.
- [ ] Đã đo kích thước bảng, dung lượng đĩa và write rate.
- [ ] Đã kiểm tra binlog và topology nếu dùng gh-ost.
- [ ] Đã đánh giá chi phí trigger và phương án FK nếu dùng pt-osc.
- [ ] Đã diễn tập với dữ liệu và tải gần production.
- [ ] Đã đặt ngưỡng load, critical load và replica lag.
- [ ] Đã kiểm tra transaction dài và metadata lock trước cutover.
- [ ] Đã có người quyết định thời điểm cutover và dừng migration.
- [ ] Đã xác minh schema, dữ liệu, index, ứng dụng và replica sau migration.
- [ ] Đã có phương án giữ bảng cũ, backup và phục hồi dữ liệu.

## Tài liệu tham khảo

- [Percona Toolkit — pt-online-schema-change](https://docs.percona.com/percona-toolkit/pt-online-schema-change.html)
- [Percona Toolkit — --alter-foreign-keys-method](https://docs.percona.com/percona-toolkit/pt-online-schema-change.html#alter-foreign-keys-method)
- [GitHub gh-ost — Requirements and limitations](https://github.com/github/gh-ost/blob/master/doc/requirements-and-limitations.md)
- [GitHub gh-ost — User guide](https://github.com/github/gh-ost/blob/master/doc/README.md)

## Kết luận

pt-online-schema-change và gh-ost đều giảm thời gian gián đoạn khi thay đổi bảng lớn bằng cách tạo bảng mới, copy dữ liệu và đồng bộ thay đổi trước cutover. pt-osc dùng trigger nên cần đánh giá tải ghi, trigger hiện hữu và foreign key. gh-ost dùng binary log nên cần row-based logging, row image phù hợp, retention đủ dài và topology được hỗ trợ. Cả hai vẫn có thể chờ metadata lock và tiêu thụ đáng kể tài nguyên. Hãy ưu tiên DDL online gốc khi phù hợp, sau đó chọn công cụ dựa trên điều kiện bảng, diễn tập thực tế, giám sát tải và phương án phục hồi đã được kiểm chứng.
