# MySQL Shell dump/load, xử lý song song và metadata tương thích

MySQL Shell cung cấp các tiện ích dump và load để xuất, chuyển và nạp dữ liệu MySQL với khả năng xử lý song song. Các tiện ích `util.dumpInstance()`, `util.dumpSchemas()` và `util.dumpTables()` tạo bộ dump gồm dữ liệu, DDL và metadata; `util.loadDump()` đọc bộ dump đó, kiểm tra thông tin và nạp vào server đích. Chúng phù hợp cho migration, tạo bản sao môi trường, provision replica từ backup logic và di chuyển workload giữa các máy chủ.

Một bộ dump không chỉ là các file dữ liệu. Metadata mô tả cấu trúc dump, phiên bản nguồn, đối tượng được xuất và cách các phần dữ liệu liên hệ với nhau. Khi nạp, MySQL Shell dùng metadata này để phối hợp các worker, sắp xếp thứ tự tạo đối tượng và xử lý dữ liệu theo cấu hình. Bỏ qua metadata hoặc tự sửa file dump có thể khiến quá trình load sai thứ tự, mất khả năng tiếp tục hoặc không tương thích với server đích.

Bài học thuộc chương **Nhập xuất và di chuyển** của module `DATABASE_MYSQL`. Module bao quát thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, phân quyền, sao lưu và vận hành cơ sở dữ liệu quan hệ. Nội dung tập trung vào MySQL Shell dump/load trên MySQL 8.0; kiểm tra tài liệu của đúng phiên bản MySQL Server và MySQL Shell trước khi dùng trong production.

Sau bài học, bạn có thể:

- Chọn đúng tiện ích dump theo phạm vi instance, schema hoặc table.
- Tạo bộ dump nhất quán và hiểu cấu trúc file cùng metadata.
- Điều chỉnh threads, chunking, kích thước chunk và tốc độ truyền.
- Nạp dump song song, xem trước bằng dry run và tiếp tục load khi phù hợp.
- Đánh giá tương thích phiên bản, charset, collation, engine và tính năng SQL.
- Xử lý quyền, GTID, users, definer và các rủi ro khi chuyển môi trường.
- Lập quy trình kiểm chứng dữ liệu sau migration.

## 1. MySQL Shell và dump/load utilities

MySQL Shell là client quản trị MySQL có chế độ JavaScript, Python và SQL. Các tiện ích dump/load được gọi trong chế độ JavaScript hoặc Python, thông qua đối tượng toàn cục `util`.

Các tiện ích chính:

| Tiện ích | Phạm vi | Trường hợp sử dụng |
|---|---|---|
| `util.dumpInstance()` | Toàn instance, theo phạm vi đối tượng mà tiện ích hỗ trợ | Tạo dump logic cho một server hoặc làm nguồn provision một instance mới. |
| `util.dumpSchemas()` | Một hoặc nhiều schema | Di chuyển một nhóm database ứng dụng. |
| `util.dumpTables()` | Một tập table trong một schema | Trích xuất một phần dữ liệu hoặc chuyển một nhóm bảng cụ thể. |
| `util.loadDump()` | Nạp bộ dump được tạo bởi các tiện ích tương ứng | Phục hồi logic hoặc nạp dữ liệu sang server đích. |

Các lệnh trên là tiện ích MySQL Shell, không phải câu SQL chạy trong mysql client. Mở MySQL Shell ở chế độ JavaScript, kết nối tới server nguồn rồi gọi tiện ích.

Ví dụ kết nối và kiểm tra phiên bản:

~~~text
mysqlsh
MySQL JS> \connect backup_user@mysql-source.example.internal:3306
MySQL JS> shell.version
MySQL JS> session.runSql("SELECT VERSION()");
~~~

Trong môi trường thực tế, dùng tài khoản riêng cho backup và migration, xác thực an toàn và TLS khi kết nối qua mạng. Không ghi mật khẩu thật trong script, command history hoặc file dump.

## 2. Chọn phạm vi dump

### 2.1. Dump toàn instance

`util.dumpInstance()` phù hợp khi cần chuyển một instance hoặc tạo bộ dump đầy đủ cho một môi trường mới. Tiện ích xử lý các schema và đối tượng được hỗ trợ, đồng thời ghi metadata để `util.loadDump()` có thể dựng lại chúng.

~~~javascript
util.dumpInstance("/backup/mysql-full", {
  threads: 8
});
~~~

Thư mục đích phải được chuẩn bị theo yêu cầu của tiện ích. Không ghi dump đè lên một bộ dump cũ đang được dùng bởi quy trình khác. Nếu cần lưu nhiều phiên bản backup, đặt thư mục theo ngày, mã lần chạy hoặc snapshot ID.

Dump toàn instance không đồng nghĩa mọi trạng thái bên ngoài database đều được sao chép. Hãy xác định riêng các thành phần cần chuyển như cấu hình server, plugin, keyring, chứng thư TLS, tài khoản hệ điều hành, job ngoài MySQL và các file ứng dụng.

### 2.2. Dump một hoặc nhiều schema

Khi chỉ cần một số database ứng dụng, dùng `util.dumpSchemas()`:

~~~javascript
util.dumpSchemas(
  ["sales", "inventory"],
  "/backup/sales-inventory",
  {threads: 8}
);
~~~

Cách này giảm thời gian và dung lượng so với dump toàn instance. Tuy nhiên, phải kiểm tra dependency ngoài phạm vi đã chọn: view có tham chiếu schema khác, routine gọi bảng ở database khác, foreign key liên schema hoặc ứng dụng dựa trên dữ liệu dùng chung.

### 2.3. Dump một nhóm table

Dùng `util.dumpTables()` khi cần chuyển một phần table trong schema:

~~~javascript
util.dumpTables(
  "sales",
  ["orders", "order_items"],
  "/backup/sales-orders",
  {threads: 4}
);
~~~

Dump một nhóm table chỉ đảm bảo phạm vi đã chọn. Nó không tự động mang theo mọi bảng phụ thuộc, dữ liệu tham chiếu, quyền ứng dụng hoặc cấu hình bên ngoài. Trước khi nạp vào môi trường đích, hãy kiểm tra khóa ngoại, trigger, view, routine và các quan hệ dữ liệu có liên quan.

### 2.4. So sánh cách chọn phạm vi

| Nhu cầu | Tiện ích gợi ý | Kiểm tra bổ sung |
|---|---|---|
| Di chuyển một server ứng dụng | `dumpInstance()` | Users, schema hệ thống, cấu hình, plugin và GTID. |
| Chuyển một số database | `dumpSchemas()` | Dependency liên schema, users và quyền truy cập. |
| Chuyển vài bảng lớn | `dumpTables()` | DDL, foreign key, trigger, view và dữ liệu tham chiếu. |
| Tạo môi trường kiểm thử nhỏ | `dumpSchemas()` hoặc `dumpTables()` | Ẩn danh dữ liệu nhạy cảm và loại bỏ secret. |

## 3. Cấu trúc bộ dump và vai trò metadata

Các tiện ích dump của MySQL Shell tạo một bộ file trong thư mục hoặc đích lưu trữ được chỉ định. Tùy phạm vi và phiên bản, bộ dump thường chứa:

- Metadata ở cấp dump mô tả phiên bản, tùy chọn, phạm vi và định dạng.
- File DDL cho schema, table, view, routine, trigger hoặc event được xuất.
- File dữ liệu cho table; table lớn có thể được chia thành nhiều chunk.
- File mô tả table và metadata phục vụ việc ánh xạ dữ liệu.
- Các file trạng thái hoặc thông tin hoàn tất do tiện ích tạo.

Tên và cấu trúc file có thể thay đổi theo phiên bản MySQL Shell. Hãy coi thư mục dump là một đơn vị hoàn chỉnh và dùng `util.loadDump()` để đọc metadata. Không tự đổi tên, xóa hoặc chỉnh sửa các file metadata nếu không hiểu tác động tới loader.

Metadata quan trọng vì nó giúp loader biết:

1. Bộ dump được tạo bởi phiên bản tiện ích nào.
2. Những schema/table và đối tượng nào thuộc bộ dump.
3. DDL nào phải được chạy trước khi nạp dữ liệu.
4. Dữ liệu table được chia thành những file hoặc chunk nào.
5. Những tùy chọn tương thích nào đã được áp dụng khi xuất.
6. Trạng thái tiến trình nào đã được ghi nhận trong một lần load.

Metadata không thay thế kiểm tra nghiệp vụ. Một bộ dump có thể được loader đọc thành công nhưng vẫn thiếu bảng phụ thuộc do phạm vi dump được chọn không đầy đủ.

## 4. Tính nhất quán của dump

Khi dump database đang có ghi, dữ liệu cần phản ánh một mốc nhất quán. Với InnoDB, dump utility hỗ trợ cơ chế snapshot nhất quán để các bảng được xuất từ cùng một trạng thái logic trong phạm vi tiện ích và điều kiện đã cấu hình.

Trước khi dump, kiểm tra:

- Các table cần chuyển có dùng InnoDB hay engine khác.
- Có DDL như ALTER, DROP, RENAME đang chạy hoặc được lên lịch trong thời gian dump không.
- Tài khoản backup có đủ quyền và cơ chế khóa/snapshot cần thiết không.
- Có workload ghi lớn làm tăng thời gian dump hoặc dung lượng file tạm không.
- Backup có cần bao gồm users, routines, events và triggers không.

Snapshot nhất quán của InnoDB không tự bảo vệ các table nontransactional theo cùng cách. DDL đồng thời có thể làm gián đoạn hoặc làm thay đổi cấu trúc mà dump đang đọc. Với migration quan trọng, điều phối DDL trong một cửa sổ phù hợp và kiểm tra thông báo của tiện ích trước khi tiếp tục.

Một lệnh dump có thể chạy nhiều worker. Điều đó không có nghĩa mọi worker tự tạo một snapshot độc lập. Hãy để tiện ích quản lý tiến trình nhất quán theo thiết kế của nó; không tự chia một lần dump thành nhiều lệnh độc lập nếu chưa xác định cách đồng bộ snapshot giữa chúng.

## 5. Xử lý song song khi dump

Các tiện ích dump hỗ trợ tham số `threads` để điều khiển số worker thực hiện công việc đồng thời.

~~~javascript
util.dumpInstance("/backup/mysql-full", {
  threads: 8
});
~~~

Tăng số worker có thể cải thiện tốc độ đọc và ghi file nếu CPU, storage và mạng còn dư địa. Tuy nhiên, nhiều worker hơn cũng có thể:

- Tăng I/O đọc trên server nguồn.
- Tăng CPU để serialize, nén và tính toán metadata.
- Tăng số file hoặc chunk được tạo đồng thời.
- Tăng tải mạng khi ghi dump tới nơi lưu trữ từ xa.
- Cạnh tranh với workload production và làm tăng latency ứng dụng.

Không mặc định dùng số thread bằng số core. Hãy bắt đầu với giá trị vừa phải, đo thời gian dump, throughput, CPU, I/O và latency ứng dụng, rồi tăng dần nếu nguồn còn dư năng lực.

### 5.1. Chunking cho table lớn

Với table lớn, chunking chia dữ liệu thành các phần nhỏ hơn để worker có thể xử lý song song. Tùy chọn liên quan có thể gồm bật/tắt chunking và kích thước chunk mục tiêu.

Ví dụ minh họa:

~~~javascript
util.dumpSchemas(
  ["sales"],
  "/backup/sales",
  {
    threads: 8,
    chunking: true,
    bytesPerChunk: "64M"
  }
);
~~~

Chunking có lợi khi table có khóa hoặc cột phù hợp để phân chia phạm vi dữ liệu. Table không có khóa phù hợp, table nhỏ hoặc dữ liệu phân bố lệch có thể không tận dụng được song song hiệu quả.

Một chunk lớn làm giảm số file và overhead metadata, nhưng có thể làm giảm tính linh hoạt của worker và tăng thời gian xử lý lại một phần dữ liệu. Chunk nhỏ tạo nhiều đơn vị công việc hơn, nhưng tăng overhead mở file, metadata, lập lịch và số lượng file cần quản lý.

Kích thước chunk là mục tiêu vận hành, không phải cam kết rằng mọi chunk đều có kích thước giống nhau. Dữ liệu có độ dài hàng biến động hoặc phân bố khóa không đều có thể tạo chunk có kích thước khác nhau.

### 5.2. Chọn khóa phân đoạn

Chunking thường cần một cột hoặc tập cột có thể dùng để phân chia phạm vi hàng. Primary key số tăng dần là trường hợp thuận lợi, nhưng không phải table nào cũng có khóa dạng đó.

Trước khi bật chunking, kiểm tra:

- Table có primary key hoặc unique key thích hợp không.
- Kiểu dữ liệu của khóa có hỗ trợ cách chia chunk của tiện ích không.
- Giá trị khóa có phân bố đều hay tập trung ở một số khoảng.
- Có nhiều hàng rất lớn khiến kích thước chunk khó dự đoán không.
- Table có thay đổi liên tục trong lúc dump không.

Không thêm khóa chỉ để ép dump nhanh hơn mà chưa đánh giá tác động đến ứng dụng, index và replication. Với table không thể chia chunk hiệu quả, có thể để tiện ích xử lý theo cách phù hợp của nó và đo thời gian thực tế.

### 5.3. Giới hạn tốc độ

Khi dump từ production, tốc độ tối đa có thể được giới hạn để giảm ảnh hưởng đến workload. Tùy chọn giới hạn rate có thể dùng để điều tiết lượng dữ liệu đọc hoặc truyền theo cách tiện ích hỗ trợ.

Không đặt giới hạn quá thấp khiến backup không hoàn thành trong cửa sổ được phép; cũng không chạy ở tốc độ tối đa nếu nó làm ảnh hưởng giao dịch trực tuyến. Hãy đo throughput, độ trễ ứng dụng, IOPS và thời gian hoàn thành để tìm mức cân bằng.

## 6. Nén và nơi lưu trữ dump

Nén giúp giảm dung lượng lưu và lưu lượng truyền, đổi lại tốn CPU để nén/giải nén. Chọn thuật toán và mức nén theo phiên bản MySQL Shell, loại dữ liệu và tài nguyên máy.

Dữ liệu dạng văn bản, JSON và giá trị lặp lại thường nén tốt. Dữ liệu đã nén, ảnh hoặc payload nhị phân có thể giảm ít hơn. Hãy đo trên mẫu đại diện thay vì suy ra từ kích thước database.

Nơi lưu dump có thể là filesystem cục bộ, mount mạng hoặc dịch vụ lưu trữ từ xa được phiên bản tiện ích hỗ trợ. Cần xem xét:

- Quyền truy cập thư mục và tài khoản dịch vụ.
- Dung lượng còn trống và quota.
- Throughput, latency và độ ổn định mạng.
- Mã hóa khi lưu và khi truyền.
- Chính sách retention, versioning và xóa bản cũ.
- Cách xác minh file đã được ghi hoàn chỉnh trước khi bắt đầu load.

Nếu dump lưu trên máy trung gian, hãy bảo đảm thư mục chứa đầy đủ bộ dump và metadata. Không copy một phần file khi dump vẫn đang chạy rồi coi bản sao là backup hoàn chỉnh. Sau khi dump hoàn tất, ghi nhận log, kích thước, thời điểm và trạng thái kết thúc của lần chạy.

## 7. Load dump và xử lý song song

`util.loadDump()` đọc bộ dump, kiểm tra metadata và nạp cấu trúc/dữ liệu vào server đích.

~~~javascript
util.loadDump("/backup/mysql-full", {
  threads: 8
});
~~~

Loader có thể dùng nhiều worker để nạp các table hoặc chunk độc lập. Mức song song thực tế phụ thuộc số chunk, dependency DDL, index, foreign key, dung lượng tài nguyên và cấu hình đích.

Trước khi load, xác nhận:

- Server đích đúng phiên bản và có đủ dung lượng.
- Charset, collation, SQL mode và timezone phù hợp.
- Các schema hoặc object trùng tên đã được xử lý theo kế hoạch.
- Tài khoản load có đủ quyền tạo và nạp đối tượng.
- Replication, binary logging và GTID được cấu hình đúng mục tiêu.
- Không có ứng dụng ghi vào database đích trong khi đang nạp dữ liệu.
- Có bản backup hoặc snapshot của trạng thái đích trước khi thay đổi.

### 7.1. Dry run trước khi nạp

Dùng `dryRun` để kiểm tra kế hoạch load mà chưa thực hiện toàn bộ thao tác ghi:

~~~javascript
util.loadDump("/backup/mysql-full", {
  dryRun: true
});
~~~

Dry run giúp phát hiện một số vấn đề về metadata, tương thích và đối tượng đích trước khi nạp. Nó không chứng minh rằng toàn bộ quá trình load sẽ thành công: lỗi quyền phát sinh ở bước thực thi, hết dung lượng, mất kết nối, lỗi dữ liệu hoặc xung đột DDL vẫn có thể xảy ra.

Đọc kỹ output dry run, xác nhận schema đích và các tùy chọn trước khi chạy thật.

### 7.2. Chọn số worker khi load

~~~javascript
util.loadDump("/backup/mysql-full", {
  threads: 12
});
~~~

Load nhiều worker có thể làm tăng tốc độ đọc file và insert, nhưng server đích phải xử lý đồng thời index, constraint, redo/undo, binlog và ghi dữ liệu. Tăng threads quá mức có thể làm CPU, I/O và memory bị bão hòa, khiến thời gian tổng thể dài hơn.

Đo các chỉ số:

- Throughput nạp dữ liệu và số chunk còn lại.
- CPU, memory, IOPS và latency storage.
- InnoDB buffer pool, redo log và dirty page pressure.
- Tỷ lệ chờ khóa và deadlock.
- Binary log growth nếu đích đang ghi binlog.
- Thời gian xây dựng index và hoàn tất DDL.

Bắt đầu với số worker vừa phải rồi tăng theo kết quả đo. Không dùng cùng một cấu hình threads cho mọi kích thước máy hoặc mọi workload.

### 7.3. Hoãn tạo index

Với một số bộ dump và phiên bản, loader hỗ trợ hoãn tạo index để nạp dữ liệu trước rồi xây dựng index sau. Ví dụ:

~~~javascript
util.loadDump("/backup/mysql-full", {
  threads: 8,
  deferTableIndexes: "all"
});
~~~

Cách này có thể tăng tốc nạp dữ liệu lớn vì giảm chi phí cập nhật secondary index cho từng hàng. Tuy nhiên, giai đoạn xây dựng index sau đó có thể cần nhiều CPU, I/O, dung lượng tạm và thời gian. Table chưa có đầy đủ index cũng chưa sẵn sàng cho workload ứng dụng bình thường.

Chỉ dùng tùy chọn hoãn index khi có cửa sổ migration và kế hoạch kiểm tra index sau khi load. Giá trị hỗ trợ và hành vi cụ thể phải được kiểm tra theo phiên bản MySQL Shell.

## 8. Tiếp tục một lần load và quản lý tiến trình

Một lần load có thể kéo dài nhiều giờ. MySQL Shell ghi nhận tiến trình để hỗ trợ tiếp tục trong các trường hợp được tiện ích hỗ trợ. Nếu kết nối bị gián đoạn hoặc lệnh dừng ngoài dự kiến, hãy xem output và trạng thái tiến trình trước khi chạy lại.

Quy trình xử lý:

1. Ghi lại lỗi và thời điểm tiến trình dừng.
2. Kiểm tra server đích còn hoạt động, dung lượng và trạng thái các worker.
3. Kiểm tra thư mục dump vẫn đầy đủ và không bị thay đổi.
4. Xác định loader có thể tiếp tục từ trạng thái đã lưu hay cần xử lý thủ công.
5. Dùng đúng bộ dump và cùng thư mục tiến trình theo yêu cầu của phiên bản.
6. Kiểm tra lại các object đã được nạp trước khi quyết định bỏ qua hoặc thay thế chúng.

Không xóa file trạng thái để buộc loader chạy lại nếu chưa biết trạng thái dữ liệu. Làm vậy có thể khiến loader không còn biết phần nào đã hoàn thành và gây lỗi object tồn tại, dữ liệu lặp hoặc xung đột.

Các tùy chọn như `ignoreExistingObjects` hoặc `dropExistingObjects` có thể ảnh hưởng mạnh đến kết quả. Không bật chỉ để vượt qua lỗi. `ignoreExistingObjects` có thể khiến loader bỏ qua object hiện có dù object đó không giống bản dump; `dropExistingObjects` có thể xóa object đích trước khi tạo lại. Hãy dùng sau khi xác nhận chính xác tác động trên môi trường thử nghiệm.

## 9. Tương thích phiên bản và metadata

Bộ dump được tạo bởi một phiên bản MySQL Shell và nạp bởi một phiên bản khác cần được kiểm tra tương thích. Khả năng load phụ thuộc cả phiên bản Shell, phiên bản MySQL Server nguồn và đích, cùng tính năng SQL được dùng trong schema.

Trước khi migration, ghi nhận:

~~~sql
SELECT VERSION(), @@version_comment;
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';
SHOW VARIABLES LIKE 'sql_mode';
SHOW VARIABLES LIKE 'lower_case_table_names';
~~~

Ngoài ra, kiểm tra phiên bản MySQL Shell:

~~~javascript
shell.version
~~~

Các điểm cần xem xét:

- Phiên bản nguồn và đích có hỗ trợ cú pháp DDL tương ứng không.
- Kiểu dữ liệu, collation và charset có tồn tại ở server đích không.
- Generated column, functional index, invisible index và CHECK constraint có hành vi tương thích không.
- Plugin, authentication method và storage engine có sẵn trên đích không.
- Định dạng JSON, spatial, temporal và kiểu dữ liệu đặc thù có thay đổi theo phiên bản không.
- SQL mode có làm thay đổi cách diễn giải dữ liệu hoặc câu lệnh không.
- Tên database/table có bị ảnh hưởng bởi khác biệt chữ hoa/chữ thường của hệ điều hành và `lower_case_table_names` không.

Không mặc định dump từ phiên bản mới hơn có thể load an toàn vào phiên bản cũ hơn. Kiểm tra ma trận hỗ trợ của MySQL và thử restore đầy đủ trên một server đích cùng phiên bản dự kiến.

### 9.1. Compatibility options khi dump

MySQL Shell có các tùy chọn tương thích để biến đổi một số DDL hoặc metadata nhằm hỗ trợ đích có giới hạn khác. Tên tùy chọn cụ thể phụ thuộc phiên bản; một số nhóm xử lý thường gặp gồm:

- Loại bỏ DEFINER khỏi view, routine, trigger hoặc event khi không muốn phụ thuộc tài khoản nguồn.
- Chuyển hoặc loại bỏ tablespace clause khi đích không có tablespace tương ứng.
- Điều chỉnh grant hoặc account metadata không tương thích.
- Chuyển engine sang InnoDB khi phù hợp với mục tiêu.
- Tạo invisible primary key cho bảng thiếu primary key khi tính năng và yêu cầu ứng dụng cho phép.

Không bật toàn bộ compatibility options theo thói quen. Mỗi tùy chọn có thể thay đổi hành vi hoặc metadata của schema. Ví dụ, bỏ DEFINER có thể làm thay đổi ngữ cảnh quyền thực thi; ép engine có thể ảnh hưởng tính năng và hiệu năng; thêm primary key có thể tác động kích thước index và replication.

Đọc danh sách tùy chọn của đúng phiên bản bằng trợ giúp trong MySQL Shell:

~~~javascript
util.help("dumpInstance")
util.help("dumpSchemas")
util.help("dumpTables")
util.help("loadDump")
~~~

Đối chiếu từng thay đổi với yêu cầu bảo mật, quyền truy cập và hành vi ứng dụng.

### 9.2. DEFINER và quyền thực thi

View, stored procedure, function, trigger và event có thể gắn với tài khoản DEFINER. Khi chuyển sang server đích, tài khoản đó có thể không tồn tại hoặc không có cùng quyền.

Nếu giữ nguyên DEFINER nhưng tài khoản không tồn tại, object có thể được tạo với cảnh báo hoặc không hoạt động như mong muốn tùy loại object và phiên bản. Nếu loại bỏ DEFINER, MySQL có thể sử dụng ngữ cảnh mặc định hoặc người tạo theo quy tắc tương ứng; điều đó có thể thay đổi quyền truy cập.

Trước khi dump, lập danh sách object có DEFINER và xác định chiến lược:

- Tạo tài khoản DEFINER tương ứng trên đích với quyền tối thiểu.
- Chuyển DEFINER sang tài khoản quản trị ứng dụng phù hợp.
- Dùng compatibility option để strip DEFINER nếu đã đánh giá tác động.
- Kiểm tra lại quyền và thử gọi routine/view bằng tài khoản ứng dụng sau khi load.

Không chuyển mọi object sang `root` chỉ để loại bỏ lỗi DEFINER. Quyền quá rộng làm tăng rủi ro bảo mật.

## 10. Users, grants và đối tượng ngoài schema

Dump schema và dump user là hai phạm vi khác nhau. Nếu cần chuyển tài khoản và quyền, kiểm tra tùy chọn dump/load users của phiên bản MySQL Shell. Không giả định `dumpTables()` mang theo users, grants hoặc các schema phụ thuộc.

Khi di chuyển user:

- Xác nhận account name và host.
- Kiểm tra authentication plugin trên nguồn và đích.
- Xác nhận plugin cần thiết đã được cài.
- Rà soát role, dynamic privileges và grant option.
- Không xuất hoặc chia sẻ password hash ngoài quy trình bảo mật.
- Kiểm tra account lock, password expiration và TLS requirement.

Sau load, dùng `SHOW GRANTS` để kiểm tra quyền của các tài khoản quan trọng và thử kết nối bằng account ứng dụng. Không chỉ kiểm tra bằng tài khoản quản trị vì nó không phản ánh quyền hiệu lực của ứng dụng.

Một số đối tượng hoặc cấu hình cần quản lý riêng:

- MySQL system variables và file cấu hình server.
- Plugin, component và keyring.
- Event scheduler setting.
- Replication channel và source configuration.
- Certificates, private keys và CA bundle.
- Scheduled task ở hệ điều hành hoặc nền tảng điều phối.
- Secret trong ứng dụng và cấu hình kết nối.

## 11. GTID và binary logging khi load

Khi nạp dump vào một server có bật binary logging, các thay đổi import có thể tạo transaction và GTID mới. Nếu dump được dùng để dựng replica hoặc phục hồi trạng thái GTID của source, phải xác định rõ cách xử lý GTID và binary log.

Các lựa chọn liên quan trong quy trình dump/load có thể gồm:

- Metadata GTID được xuất cùng dump.
- Tùy chọn cập nhật GTID set trong `util.loadDump()`, với hành vi tùy phiên bản.
- Tùy chọn bỏ qua binary logging cho session load nếu được hỗ trợ và có quyền phù hợp.

Không tự chọn chế độ cập nhật GTID. Nếu mục tiêu là provision replica từ backup, GTID set phải phản ánh chính xác transaction đã có trong dữ liệu snapshot. Nếu chỉ chuyển một số schema sang môi trường độc lập, mang toàn bộ GTID của source sang đích có thể đánh dấu nhầm transaction của các schema không được dump.

Trước khi load, xem trợ giúp phiên bản hiện tại:

~~~javascript
util.help("loadDump")
~~~

Sau khi load, kiểm tra:

~~~sql
SELECT @@GLOBAL.gtid_executed, @@GLOBAL.gtid_purged;
SHOW BINARY LOGS;
~~~

Nếu server đích sẽ trở thành replica, chỉ cấu hình auto-position sau khi xác nhận dữ liệu và GTID metadata cùng một mốc logic. Không thêm GTID thủ công để vượt qua lỗi thiếu transaction; GTID chỉ ghi nhận lịch sử, không tái tạo dữ liệu.

## 12. Quyền cần thiết

Dump và load là thao tác có phạm vi lớn. Tài khoản thực hiện cần các quyền tương ứng với đối tượng và cơ chế snapshot, đọc, tạo hoặc thay đổi dữ liệu. Danh sách quyền cụ thể thay đổi theo phiên bản, tiện ích và tùy chọn được bật.

Tài khoản dump thường cần quyền đọc table/view, xem metadata, đọc routine/event/trigger và thực hiện các thao tác khóa hoặc snapshot mà tiện ích sử dụng. Tài khoản load cần quyền tạo schema/table, ghi dữ liệu, tạo index, routine, trigger, event và quản lý users nếu có nạp users.

Cách làm an toàn:

1. Đọc danh sách privilege yêu cầu của đúng tiện ích và phiên bản.
2. Tạo tài khoản backup riêng cho nguồn và tài khoản migration riêng cho đích.
3. Chỉ cấp quyền cần cho phạm vi dump/load.
4. Không dùng tài khoản `root` cho job tự động.
5. Ghi log lần chạy nhưng không ghi secret.
6. Thu hồi quyền tạm sau khi migration hoàn tất nếu tài khoản không cần tiếp tục.

Nếu gặp lỗi quyền, xác định object và thao tác cụ thể bị từ chối. Không giải quyết bằng cách cấp `ALL PRIVILEGES` cho tài khoản ứng dụng.

## 13. Quy trình migration thực tế

Một quy trình migration nên chia thành chuẩn bị, dump, chuyển file, load và kiểm chứng.

### 13.1. Chuẩn bị nguồn và đích

- Ghi nhận phiên bản Server và Shell.
- Kiểm tra schema, engine, charset, collation, SQL mode và timezone.
- Kiểm tra dung lượng nguồn, đích và nơi lưu dump.
- Kiểm tra tài khoản, quyền, users, roles và DEFINER.
- Lập danh sách object và dependency trong phạm vi migration.
- Chọn cửa sổ dump và load phù hợp với tải hệ thống.
- Xác định mục tiêu GTID và replication của server đích.

### 13.2. Dump

Ví dụ dump một số schema:

~~~javascript
util.dumpSchemas(
  ["sales", "inventory"],
  "/backup/migration-2026-11-19",
  {
    threads: 8,
    chunking: true,
    bytesPerChunk: "64M"
  }
);
~~~

Theo dõi output đến khi tiện ích xác nhận hoàn tất. Lưu log lần chạy, phiên bản công cụ, cấu hình đã dùng và thời điểm hoàn tất. Xác nhận thư mục có metadata cùng các file DDL/data được tạo.

### 13.3. Chuyển bộ dump

Nếu cần chuyển sang host khác:

- Copy toàn bộ thư mục dump.
- Giữ nguyên tên và cấu trúc file.
- Kiểm tra số lượng file và tổng dung lượng ở hai phía.
- Dùng checksum của hệ điều hành hoặc công cụ lưu trữ để kiểm tra tính toàn vẹn khi truyền.
- Bảo vệ quyền đọc vì dump có thể chứa dữ liệu nhạy cảm.
- Không xóa bản nguồn trước khi bản đích được xác minh.

### 13.4. Load

Trước tiên chạy dry run:

~~~javascript
util.loadDump("/backup/migration-2026-11-19", {
  dryRun: true
});
~~~

Sau khi review output và xác nhận server đích:

~~~javascript
util.loadDump("/backup/migration-2026-11-19", {
  threads: 8
});
~~~

Nếu cần điều chỉnh index hoặc GTID, bổ sung tùy chọn sau khi đã xác nhận hành vi và tác động của chúng theo phiên bản.

### 13.5. Kiểm chứng sau load

Kiểm tra theo nhiều lớp:

- **Schema:** số lượng table, view, routine, trigger và event.
- **Dữ liệu:** row count của các table trọng yếu và các phép đối chiếu tổng hợp.
- **Ràng buộc:** primary key, unique key, foreign key và CHECK constraint.
- **Index:** tên, loại, thứ tự cột, visibility và trạng thái xây dựng.
- **Tài khoản:** users, roles, grants, DEFINER và authentication.
- **Replication:** GTID, binary log và trạng thái replica nếu có.
- **Ứng dụng:** đăng nhập, truy vấn đọc, ghi thử, transaction và luồng nghiệp vụ.
- **Hiệu năng:** execution plan, latency và workload đại diện.

Không chỉ so sánh tổng số hàng. Có thể hai bảng có cùng row count nhưng khác nội dung. Với dữ liệu quan trọng, so sánh theo khóa, tổng số tiền, tổng số lượng, min/max timestamp hoặc checksum theo lô. Chọn phương pháp không gây tải quá lớn trên production.

## 14. Kiểm tra dữ liệu sau migration

### 14.1. Kiểm tra cấu trúc

~~~sql
SHOW TABLES FROM sales;
SHOW CREATE TABLE sales.orders;
SHOW INDEX FROM sales.orders;
~~~

Kiểm tra view và routine:

~~~sql
SHOW FULL TABLES FROM sales;
SHOW PROCEDURE STATUS WHERE Db = 'sales';
SHOW FUNCTION STATUS WHERE Db = 'sales';
~~~

Kết quả cần được so sánh với manifest hoặc danh sách đối tượng đã chốt trước migration. Một số metadata có thể được biến đổi có chủ đích do compatibility option; ghi lại những khác biệt này.

### 14.2. Kiểm tra số lượng và tổng hợp dữ liệu

~~~sql
SELECT COUNT(*) FROM sales.orders;
SELECT COUNT(*) FROM sales.order_items;

SELECT
  COUNT(*) AS order_count,
  SUM(total_amount) AS total_amount,
  MIN(created_at) AS first_order,
  MAX(created_at) AS last_order
FROM sales.orders;
~~~

So sánh kết quả nguồn và đích tại cùng mốc snapshot. Nếu nguồn vẫn nhận ghi sau thời điểm dump, số liệu lấy trực tiếp ở hai thời điểm khác nhau sẽ không thể so sánh chính xác. Dùng snapshot hoặc mốc dữ liệu đã ghi nhận.

### 14.3. Kiểm tra dữ liệu theo khóa

Với table quan trọng, chia dữ liệu thành khoảng khóa và so sánh theo batch. Ví dụ:

~~~sql
SELECT
  MIN(order_id),
  MAX(order_id),
  COUNT(*),
  SUM(total_amount)
FROM sales.orders
WHERE order_id >= 1 AND order_id < 100000;
~~~

Lặp lại cho các khoảng tiếp theo. Với table có dữ liệu nhạy cảm, không xuất toàn bộ row ra file log chỉ để so sánh. Có thể dùng checksum theo batch nếu phương pháp và kiểu dữ liệu hỗ trợ.

## 15. Sự cố thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Dump báo thiếu privilege | Tài khoản không có quyền đọc object hoặc dùng cơ chế snapshot | Đọc lỗi cụ thể, cấp đúng quyền cho tài khoản backup rồi thử lại trên phạm vi nhỏ. |
| Dump chậm dù threads cao | I/O nguồn, CPU, network hoặc table lớn không chunk hiệu quả | Đo bottleneck, thử chunking và điều chỉnh worker theo tải. |
| Một table tạo ít chunk | Không có khóa phù hợp hoặc table không thích hợp để phân đoạn | Kiểm tra schema và cách tiện ích chia chunk; không giả định mọi table đều song song. |
| Load báo object đã tồn tại | Đích không sạch hoặc lần load trước đã tạo một phần object | Kiểm tra object và tiến trình; quyết định resume, bỏ qua hay dựng lại theo kế hoạch. |
| Load thất bại do DDL | Phiên bản hoặc tính năng schema không tương thích | Xem lỗi DDL, kiểm tra compatibility option và thử trên server đích cùng phiên bản. |
| Routine/view không chạy | DEFINER thiếu hoặc quyền thực thi khác | Kiểm tra DEFINER, SQL SECURITY, grants và account trên đích. |
| Load bị chậm khi tạo index | Index build, I/O hoặc memory là bottleneck | Đo giai đoạn index; cân nhắc defer indexes nếu phù hợp. |
| Đích có GTID ngoài dự kiến | Import ghi vào binlog hoặc metadata GTID được áp dụng sai | Kiểm tra `gtid_executed`, tùy chọn load và mục tiêu replication. |
| File dump thiếu sau khi copy | Copy chưa hoàn tất hoặc bỏ sót metadata/chunk | So sánh file list, kích thước và checksum; copy lại trước khi load. |
| Dry run thành công nhưng load lỗi | Dry run không thực thi toàn bộ thao tác ghi | Kiểm tra quyền, dung lượng, DDL, dữ liệu và trạng thái server trong lúc load. |

## 16. Bài tập thực hành

### Bài 1: Chọn tiện ích dump

Một ứng dụng có database `sales`, `inventory` và `audit`. Môi trường kiểm thử chỉ cần `sales` cùng hai bảng `orders` và `order_items`. Chọn giữa `dumpInstance`, `dumpSchemas` và `dumpTables`; liệt kê dependency cần kiểm tra trước khi xuất.

### Bài 2: Điều chỉnh threads và chunking

Tạo một table lớn có primary key và một table khác không có khóa phù hợp. Thử dump với số threads khác nhau và chunking bật/tắt. Ghi nhận thời gian, dung lượng, CPU và I/O; giải thích vì sao tăng threads không luôn tăng throughput.

### Bài 3: Thực hiện dry run và load

Tạo bộ dump trên môi trường thử nghiệm, chuyển sang server đích cùng phiên bản, chạy `dryRun`, đọc output rồi thực hiện load song song. Kiểm tra schema và row count sau khi hoàn thành.

### Bài 4: Tương thích DEFINER

Tạo view hoặc routine có DEFINER là một account riêng. Dump và load sang instance không có account đó. Quan sát cảnh báo/lỗi và thử các phương án tạo account tương ứng hoặc strip DEFINER. Kiểm tra quyền hiệu lực sau mỗi phương án.

### Bài 5: Kiểm tra GTID

Tạo dump toàn instance và dump một schema trên source có bật GTID. Kiểm tra metadata hoặc SQL đầu ra liên quan GTID, sau đó giải thích vì sao dump một phần không nên tự động được dùng làm trạng thái GTID cho replica toàn instance.

## 17. Checklist trước khi hoàn tất migration

- [ ] Đã chọn đúng phạm vi dump: instance, schema hoặc table.
- [ ] Đã kiểm tra engine, snapshot, DDL đồng thời và tính nhất quán dữ liệu.
- [ ] Đã ghi nhận phiên bản MySQL Server và MySQL Shell.
- [ ] Đã chọn threads, chunking, kích thước chunk và rate theo tải thực tế.
- [ ] Bộ dump chứa metadata cùng đầy đủ file DDL/data.
- [ ] Đã kiểm tra tính toàn vẹn khi chuyển file sang nơi lưu trữ hoặc host đích.
- [ ] Đã chạy dry run và review output.
- [ ] Đã xác nhận quyền và dung lượng server đích.
- [ ] Đã xem xét tương thích charset, collation, SQL mode, engine và DDL.
- [ ] Đã xử lý DEFINER, users, roles và grants theo chính sách bảo mật.
- [ ] Đã xác định cách xử lý binary log và GTID.
- [ ] Đã load thành công và kiểm tra mọi object trọng yếu.
- [ ] Đã đối chiếu row count và dữ liệu theo khóa hoặc checksum phù hợp.
- [ ] Đã chạy thử các luồng nghiệp vụ và truy vấn đại diện.
- [ ] Đã lưu log migration, metadata, thời điểm và kết quả xác minh.
- [ ] Chỉ xóa bản dump hoặc mở ghi ứng dụng sau khi có xác nhận hoàn tất theo quy trình.

MySQL Shell dump/load giúp di chuyển dữ liệu lớn bằng cách kết hợp metadata, chunking và worker song song. Tốc độ tốt chỉ có ý nghĩa khi snapshot nhất quán, bộ dump đầy đủ, đích tương thích và dữ liệu sau load được kiểm chứng. Hãy coi metadata cùng các file dump là một đơn vị, thử dry run trên đích, điều chỉnh worker theo số liệu thực tế và chỉ chuyển ứng dụng sang môi trường mới sau khi hoàn tất kiểm tra cấu trúc, dữ liệu, quyền và replication.

