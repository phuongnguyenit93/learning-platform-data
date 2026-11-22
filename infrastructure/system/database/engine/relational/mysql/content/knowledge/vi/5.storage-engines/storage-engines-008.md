# Chọn engine theo toàn vẹn, đồng thời, độ bền và nhu cầu truy vấn

Storage engine quyết định cách MySQL lưu trữ và truy cập dữ liệu của từng bảng. Chọn engine vì thế ảnh hưởng trực tiếp đến transaction, khóa, kiểm soát đồng thời, khả năng phục hồi sau sự cố, loại index và hiệu năng của workload. Một lựa chọn phù hợp phải xuất phát từ yêu cầu dữ liệu và cách ứng dụng truy vấn, không chỉ từ một phép đo tốc độ đơn lẻ.

Trong module **DATABASE_MYSQL**, thiết kế bảng, kiểu dữ liệu, khóa, SQL, index, transaction và vận hành đều liên quan đến storage engine. Ví dụ, InnoDB cung cấp transaction và foreign key cho dữ liệu quan hệ; engine khác có thể phù hợp với dữ liệu tạm, dữ liệu lưu trữ nén hoặc một hệ thống cluster chuyên biệt. Bài học này xây dựng cách đánh giá và lựa chọn engine theo bốn nhóm tiêu chí: **toàn vẹn dữ liệu, đồng thời, độ bền và nhu cầu truy vấn**.

## 1. Bắt đầu từ yêu cầu của workload

Trước khi chọn engine, hãy mô tả dữ liệu và cách ứng dụng sử dụng dữ liệu đó. Bốn câu hỏi sau là điểm khởi đầu.

### 1.1. Toàn vẹn dữ liệu

Dữ liệu có cần các transaction nguyên tử không? Một nghiệp vụ có cập nhật nhiều hàng hoặc nhiều bảng và cần tất cả cùng thành công hoặc cùng thất bại không? Có cần foreign key để bảo vệ quan hệ giữa các bảng không? Ứng dụng có cần rollback khi một bước nghiệp vụ lỗi không?

Nếu câu trả lời là có, engine phải hỗ trợ transaction và các ràng buộc cần thiết. Với hệ thống giao dịch quan hệ thông thường, InnoDB là lựa chọn mặc định hợp lý.

### 1.2. Đồng thời

Có bao nhiêu client đọc và ghi cùng lúc? Nhiều transaction có thể cập nhật cùng một hàng, cùng một nhóm hàng hoặc các khoảng khóa giao nhau không? Hệ thống có nhiều truy vấn đọc dài trong lúc ghi dữ liệu không?

Cần xem cơ chế khóa, isolation level, MVCC và khả năng xử lý xung đột của engine. Khóa dòng có thể giảm phạm vi xung đột so với khóa bảng, nhưng không có nghĩa mọi thao tác chỉ khóa đúng một hàng. Index và execution plan có thể làm thay đổi số bản ghi hoặc khoảng index bị khóa.

### 1.3. Độ bền và phục hồi

Khi server hoặc hệ điều hành gặp sự cố, dữ liệu đã commit cần được bảo vệ đến mức nào? Hệ thống chấp nhận mất dữ liệu trong một khoảng thời gian ngắn hay yêu cầu xác nhận commit chỉ sau khi log được flush theo cấu hình bền vững? Có cần phục hồi tới một thời điểm dựa trên backup và binary log không?

Engine có cơ chế phục hồi riêng, nhưng độ bền cuối cùng còn phụ thuộc cấu hình server, hệ điều hành, thiết bị lưu trữ và quy trình backup. Chọn InnoDB không tự động thay thế việc cấu hình durability và thử khôi phục.

### 1.4. Nhu cầu truy vấn

Ứng dụng chủ yếu đọc, ghi nối tiếp, cập nhật thường xuyên, tìm kiếm toàn văn, phân tích dữ liệu hay lưu trữ dữ liệu ít thay đổi? Truy vấn có cần join, lọc theo nhiều cột, sắp xếp, tổng hợp hoặc tìm kiếm theo index không?

Hãy ghi lại truy vấn quan trọng và tần suất chạy. Engine và loại index cần hỗ trợ access pattern thực tế; một engine nhanh trong phép ghi tuần tự có thể không phù hợp với ứng dụng cần transaction, join và cập nhật đồng thời.

## 2. InnoDB: lựa chọn nền tảng cho dữ liệu giao dịch

InnoDB là storage engine mặc định của MySQL trong các phiên bản hiện đại. Nó được thiết kế cho workload giao dịch và cung cấp các khả năng mà phần lớn ứng dụng quản lý dữ liệu quan hệ cần.

### 2.1. Toàn vẹn và transaction

InnoDB hỗ trợ ACID transaction, gồm:

- **Atomicity:** các thay đổi trong transaction được commit như một đơn vị hoặc rollback theo cơ chế transaction.
- **Consistency:** ứng dụng và các ràng buộc được thực thi giúp dữ liệu chuyển từ trạng thái hợp lệ này sang trạng thái hợp lệ khác.
- **Isolation:** các transaction được điều phối theo isolation level và cơ chế kiểm soát đồng thời.
- **Durability:** thay đổi đã commit được bảo vệ theo cấu hình redo log, binlog, hệ điều hành và thiết bị lưu trữ.

InnoDB hỗ trợ foreign key, nhờ đó có thể duy trì quan hệ giữa bảng cha và bảng con ở cấp database. Ví dụ:

```sql
CREATE TABLE customers (
    customer_id BIGINT NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;

CREATE TABLE orders (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer (customer_id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id)
) ENGINE = InnoDB;
```

Với cấu trúc này, InnoDB từ chối ghi một đơn hàng tham chiếu tới customer không tồn tại và ngăn thao tác xóa customer nếu quan hệ còn phụ thuộc theo hành vi constraint được khai báo. Điều đó giúp bảo vệ dữ liệu kể cả khi có nhiều ứng dụng hoặc nhiều đường ghi khác nhau.

Transaction còn cho phép nhóm nhiều thao tác thành một đơn vị nghiệp vụ:

```sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 500000
WHERE account_id = 101;

UPDATE accounts
SET balance = balance + 500000
WHERE account_id = 202;

COMMIT;
```

Ứng dụng thực tế phải kiểm tra số hàng bị tác động, số dư và các điều kiện nghiệp vụ trước khi commit. Nếu một điều kiện không đạt, ứng dụng gọi ROLLBACK. Transaction này chỉ bảo đảm tính nguyên tử cho các thay đổi transactional trên những bảng tham gia.

### 2.2. Đồng thời và MVCC

InnoDB dùng MVCC để cung cấp consistent read cho nhiều truy vấn thông thường. Trong nhiều tình huống, một transaction đọc snapshot mà không cần chặn transaction khác đang ghi cùng dữ liệu. Các thao tác ghi vẫn cần khóa để tránh cập nhật xung đột.

InnoDB hỗ trợ row-level locking cùng các khóa index record và khóa phạm vi như next-key lock trong những trường hợp cần thiết. Phạm vi khóa phụ thuộc vào:

- Câu lệnh là đọc thường, locking read, UPDATE hay DELETE.
- Isolation level của transaction.
- Index được dùng và điều kiện lọc.
- Kế hoạch thực thi và dữ liệu thực tế.

Ví dụ, truy vấn sau yêu cầu khóa các bản ghi phù hợp để ứng dụng xử lý cập nhật trong cùng transaction:

```sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 101
FOR UPDATE;

-- Ứng dụng kiểm tra điều kiện nghiệp vụ ở đây.
UPDATE accounts
SET balance = balance - 100000
WHERE account_id = 101;

COMMIT;
```

Điều kiện trên khóa chính giúp InnoDB định vị bản ghi hiệu quả. Nếu truy vấn không có index phù hợp, engine có thể phải duyệt nhiều index record hơn và phạm vi khóa có thể lớn hơn mong muốn. Vì vậy, thiết kế index ảnh hưởng không chỉ tốc độ mà còn khả năng đồng thời.

### 2.3. Index và cấu trúc lưu trữ

InnoDB tổ chức dữ liệu hàng theo clustered index. Nếu bảng có primary key, primary key là clustered index; nếu không có khóa chính phù hợp, InnoDB chọn một unique NOT NULL index phù hợp hoặc tạo khóa hàng nội bộ.

Secondary index lưu khóa index cùng giá trị khóa chính để tìm bản ghi trong clustered index. Do đó, khóa chính rộng làm các secondary index cũng tốn thêm không gian. Với bảng có nhiều index, lựa chọn khóa chính có thể ảnh hưởng đáng kể đến dung lượng và I/O.

InnoDB hỗ trợ các kiểu index và tính năng phù hợp cho ứng dụng giao dịch, bao gồm B-tree, full-text và spatial index theo điều kiện của phiên bản. Cần chọn index theo truy vấn thực tế và xác minh bằng EXPLAIN.

### 2.4. Phục hồi và độ bền

InnoDB dùng redo log để phục hồi thay đổi trang dữ liệu sau crash, undo log để rollback và hỗ trợ MVCC. Buffer pool cache các trang dữ liệu và index trong bộ nhớ; dirty page được ghi xuống storage theo cơ chế flush của engine.

Độ bền khi commit chịu ảnh hưởng bởi cấu hình, đặc biệt là:

- **innodb_flush_log_at_trx_commit:** điều khiển thời điểm ghi và flush redo log. Giá trị 1 là cấu hình thường dùng khi cần độ bền cao: redo log được ghi và flush theo mỗi commit. Giá trị 0 hoặc 2 giảm tần suất flush xuống thiết bị lưu trữ, có thể làm mất các transaction gần nhất khi hệ điều hành hoặc máy chủ gặp sự cố.
- **sync_binlog:** điều khiển đồng bộ binary log. Nếu cần bảo vệ binlog chặt chẽ theo từng transaction, giá trị 1 thường được chọn để đồng bộ sau mỗi commit.

Có thể xem cấu hình hiện tại:

```sql
SHOW VARIABLES
WHERE Variable_name IN (
    'innodb_flush_log_at_trx_commit',
    'sync_binlog',
    'innodb_doublewrite'
);
```

Các giá trị bền vững cần được chọn theo mục tiêu RPO, RTO, tải ghi và năng lực thiết bị lưu trữ. Ngay cả khi cấu hình yêu cầu flush, độ bền còn phụ thuộc việc hệ điều hành, controller và thiết bị thực hiện lệnh flush đúng cam kết. Redo log và doublewrite không thay thế backup độc lập.

## 3. Các engine khác và phạm vi sử dụng

MySQL hỗ trợ kiến trúc pluggable storage engine. Các engine có thể có feature set khác nhau và không phải engine nào cũng được cài đặt hoặc bật trong mọi bản phân phối.

| Engine | Đặc điểm chính | Tình huống có thể cân nhắc | Giới hạn cần nhớ |
|---|---|---|---|
| InnoDB | Transaction, MVCC, foreign key, crash recovery, index giao dịch | Ứng dụng OLTP, dữ liệu quan hệ, phần lớn hệ thống production | Cần thiết kế index, transaction và cấu hình durability |
| MyISAM | Không có transaction kiểu InnoDB; khóa bảng; hỗ trợ full-text | Tương thích hệ thống cũ hoặc workload đặc thù không cần transaction | Không rollback; khóa bảng có thể hạn chế ghi đồng thời; khả năng phục hồi hạn chế |
| MEMORY | Dữ liệu bảng nằm trong RAM; hỗ trợ index HASH và BTREE | Dữ liệu tạm, bảng tra cứu nhỏ có thể tái tạo | Dữ liệu mất khi server khởi động lại; dung lượng RAM giới hạn; không dùng làm nơi lưu dữ liệu bền vững |
| ARCHIVE | Tập trung lưu trữ nén, phù hợp dữ liệu thêm vào và đọc lại | Dữ liệu lịch sử hoặc lưu trữ theo kiểu append/read khi feature set đáp ứng | Hạn chế về thao tác cập nhật, index và truy vấn; phải kiểm tra phiên bản |
| NDB Cluster | Engine phân tán, hướng tới tính sẵn sàng cao và dữ liệu phân bố trên các node | Hệ thống thực sự triển khai MySQL NDB Cluster với yêu cầu phân tán | Cần hạ tầng và vận hành NDB Cluster; khác biệt về tính năng và cách tối ưu so với InnoDB |

Bảng trên là định hướng lựa chọn, không phải danh sách đầy đủ hoặc cam kết rằng mọi engine đều có sẵn. Hãy kiểm tra kết quả SHOW ENGINES trên chính server và tài liệu phiên bản đang triển khai.

### 3.1. MyISAM: cân nhắc giới hạn transaction và khóa bảng

MyISAM không hỗ trợ transaction và rollback như InnoDB. Nó sử dụng table-level locking, vì vậy một thao tác ghi có thể chặn các thao tác khác trên cùng bảng theo quy tắc khóa của engine.

Điều này khiến MyISAM không phù hợp với các nghiệp vụ cần nhiều bước cập nhật nguyên tử, foreign key hoặc ghi đồng thời cao. Khi ứng dụng gọi ROLLBACK, các thay đổi đã thực hiện trên bảng MyISAM không được hoàn tác như với InnoDB.

Một hệ thống cũ có thể còn bảng MyISAM vì lịch sử hoặc tính tương thích. Trước khi chuyển sang InnoDB, cần đánh giá schema, index, dung lượng, thời gian chuyển đổi và kế hoạch rollback.

### 3.2. MEMORY: dữ liệu tạm có thể tái tạo

MEMORY lưu dữ liệu bảng trong RAM. Nó có thể hữu ích cho tập dữ liệu tạm thời, nhỏ và có thể tạo lại sau khi server khởi động. Nội dung của bảng MEMORY không bền vững qua lần restart.

Ví dụ:

```sql
CREATE TABLE current_job_cache (
    job_id BIGINT NOT NULL,
    worker_name VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (job_id),
    KEY idx_job_status USING HASH (status)
) ENGINE = MEMORY;
```

Ví dụ này chỉ minh họa cách chỉ định engine và index; cần xác nhận cú pháp index cùng kiểu dữ liệu được engine hỗ trợ ở phiên bản đang chạy. Không lưu trạng thái nghiệp vụ duy nhất trong MEMORY nếu ứng dụng không có nguồn dữ liệu bền vững khác.

### 3.3. ARCHIVE và NDB Cluster: các nhu cầu chuyên biệt

ARCHIVE được thiết kế cho lưu trữ nén và workload ghi thêm, đọc lại. Nó có thể giảm dung lượng lưu trữ cho dữ liệu lịch sử, nhưng không nên chọn trước khi xác minh các thao tác SQL, index và truy vấn mà ứng dụng cần.

NDB Cluster là một kiến trúc cluster với storage engine NDB, hướng tới dữ liệu phân tán và khả năng sẵn sàng cao. NDB cần các thành phần cluster chuyên biệt và quy trình vận hành riêng. Một MySQL Server đơn lẻ không tự trở thành NDB Cluster chỉ bằng cách chỉ định ENGINE=NDB.

## 4. Ma trận chọn engine theo yêu cầu

Có thể dùng ma trận sau để sàng lọc lựa chọn ban đầu:

| Yêu cầu | InnoDB | MyISAM | MEMORY | ARCHIVE | NDB Cluster |
|---|---|---|---|---|---|
| Transaction và rollback | Có | Không | Không | Không | Có hỗ trợ transaction theo mô hình NDB |
| Foreign key | Có | Không | Không | Không | Không nên giả định tương đương InnoDB; kiểm tra feature support |
| MVCC | Có | Không | Không | Không | Cơ chế transaction của NDB có đặc điểm riêng |
| Dữ liệu bền vững trên đĩa | Có | Có | Không đối với nội dung bảng | Có | Có thể cấu hình lưu trữ theo mô hình cluster |
| Row-level concurrency | Có, theo cơ chế khóa InnoDB | Khóa bảng | Khóa bảng | Khả năng giới hạn theo engine | Cơ chế khóa và phân tán riêng |
| Lưu trữ nén chuyên dụng | Không phải mục tiêu chính | Không phải mục tiêu chính | Không | Có | Không phải mục tiêu chính |
| Dữ liệu phân tán trên cluster | Không | Không | Không | Không | Có |

Ma trận chỉ dùng để định hướng. Các khả năng cụ thể, giới hạn của engine và cách server tích hợp thay đổi theo phiên bản. Khi một yêu cầu là bắt buộc, kiểm tra tài liệu và thử nghiệm trên đúng bản phân phối.

### 4.1. Một số tình huống lựa chọn

**Ứng dụng bán hàng:** đơn hàng, thanh toán, tồn kho và khách hàng có quan hệ và phải cập nhật nguyên tử. Chọn InnoDB để dùng transaction, foreign key và khóa phù hợp.

**Bảng cache có thể tạo lại:** dữ liệu được nạp từ nguồn bền vững, kích thước nhỏ và cần truy cập trong RAM. Có thể cân nhắc MEMORY nếu chấp nhận mất dữ liệu khi restart và kiểm soát dung lượng.

**Hệ thống cũ dùng MyISAM:** trước tiên xác định vì sao bảng còn dùng MyISAM, có phụ thuộc vào full-text hoặc hành vi cũ không, và có thể chuyển đổi trong cửa sổ bảo trì nào. Với dữ liệu giao dịch mới, ưu tiên InnoDB.

**Kho dữ liệu lịch sử ít cập nhật:** nếu pattern chủ yếu append/read và khả năng truy vấn phù hợp, có thể đánh giá ARCHIVE hoặc một giải pháp lưu trữ khác. Cần benchmark truy vấn thực tế và kiểm tra yêu cầu báo cáo.

**Hệ thống cluster phân tán:** chỉ chọn NDB khi kiến trúc tổng thể thực sự cần NDB Cluster và đội ngũ có năng lực triển khai, giám sát, backup và phục hồi cluster.

## 5. Nhu cầu truy vấn và index phải đi cùng lựa chọn engine

Engine không thể bù cho schema hoặc index được thiết kế không phù hợp. Khi chọn engine, hãy liệt kê truy vấn trọng yếu:

- Truy vấn theo primary key hoặc unique key.
- Lọc theo một hay nhiều cột.
- Join các bảng có quan hệ.
- Đọc theo khoảng thời gian hoặc thứ tự.
- Tổng hợp và báo cáo.
- Full-text hoặc spatial search nếu ứng dụng cần.
- Các thao tác ghi đồng thời vào cùng dữ liệu.

Với InnoDB, hãy chọn primary key ổn định và đủ gọn, sau đó tạo secondary index theo access pattern. Ví dụ:

```sql
CREATE INDEX idx_orders_status_created
    ON orders (status, created_at);

EXPLAIN
SELECT order_id, customer_id, total_amount
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-01-01'
ORDER BY created_at;
```

Index tổng hợp có thứ tự cột quan trọng. Index bắt đầu bằng status có thể hỗ trợ điều kiện lọc status và khoảng created_at, nhưng hiệu quả thực tế phụ thuộc độ chọn lọc, phân bố dữ liệu, thứ tự sắp xếp và optimizer. Hãy đọc EXPLAIN và đo trên dữ liệu gần với production.

Một engine có thể cung cấp index method khác hoặc giới hạn loại index. Đừng giả định mọi engine hỗ trợ giống nhau chỉ vì câu CREATE INDEX có cú pháp tương tự.

## 6. Cấu hình durability là một phần của quyết định engine

Độ bền là yêu cầu hệ thống, không chỉ là một checkbox trong tên engine. Với InnoDB, cần xác định mục tiêu mất dữ liệu tối đa sau sự cố và cân bằng với hiệu năng ghi.

### 6.1. Hiểu tác động của các biến chính

- **innodb_flush_log_at_trx_commit = 1:** InnoDB ghi và flush redo log theo mỗi commit. Đây thường là cấu hình phù hợp khi ưu tiên độ bền transaction.
- **innodb_flush_log_at_trx_commit = 2:** redo log được ghi vào hệ điều hành theo mỗi commit nhưng flush xuống thiết bị lưu trữ định kỳ. Khi hệ điều hành hoặc máy chủ gặp sự cố, có thể mất các transaction gần nhất chưa được flush.
- **innodb_flush_log_at_trx_commit = 0:** việc ghi và flush redo log được thực hiện định kỳ; rủi ro mất các transaction gần nhất cao hơn.
- **sync_binlog = 1:** đồng bộ binlog theo từng commit, thường được chọn khi cần binlog bền vững cho replication và point-in-time recovery.

Chu kỳ định kỳ thường xấp xỉ một giây nhưng không phải cam kết thời gian tuyệt đối. Cấu hình cụ thể phải dựa trên yêu cầu và tài liệu phiên bản.

### 6.2. Durability không thay thế backup

Redo log phục hồi trạng thái InnoDB sau crash; binary log lưu sự kiện thay đổi phục vụ replica và phục hồi theo thời điểm. Backup là bản sao có thể khôi phục khi mất dữ liệu, hỏng thiết bị hoặc thao tác quản trị sai.

Một quy trình vận hành tốt cần:

1. Xác định RPO (mức mất dữ liệu tối đa chấp nhận được) và RTO (thời gian phục hồi mục tiêu).
2. Chọn cấu hình redo/binlog tương ứng với RPO và yêu cầu hiệu năng.
3. Tạo backup theo lịch, bảo vệ bản backup khỏi sự cố cùng nơi với server.
4. Lưu và quản lý binary log phù hợp với khoảng thời gian point-in-time recovery cần thiết.
5. Thường xuyên thử restore trên môi trường riêng và đo thời gian phục hồi.
6. Kiểm tra tính nhất quán dữ liệu và khả năng ứng dụng hoạt động sau restore.

Không xem một lần backup thành công là bằng chứng đã có thể phục hồi. Cần thực hiện thử khôi phục và ghi nhận kết quả.

## 7. Trộn nhiều storage engine trong một transaction

MySQL cho phép một database chứa bảng dùng engine khác nhau, nhưng không có nghĩa mọi thao tác trên các bảng đó đều có cùng ngữ nghĩa transaction.

Ví dụ:

```sql
CREATE TABLE payment_records (
    payment_id BIGINT PRIMARY KEY,
    amount DECIMAL(12, 2) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE legacy_audit (
    audit_id BIGINT PRIMARY KEY,
    message VARCHAR(255) NOT NULL
) ENGINE = MyISAM;
```

Nếu một transaction cập nhật bảng InnoDB rồi ghi vào bảng MyISAM, thao tác trên InnoDB có thể rollback nhưng thay đổi MyISAM đã thực hiện không được hoàn tác. Vì vậy, một transaction có vẻ bao gồm hai bảng nhưng không bảo đảm atomicity trên cả hai.

Quy tắc thực hành:

- Giữ các bảng cùng một đơn vị nghiệp vụ trong engine transactional tương thích, thường là InnoDB.
- Không dựa vào ROLLBACK để đảo ngược thay đổi trên bảng non-transactional.
- Nếu phải tích hợp hệ thống cũ, thiết kế cơ chế bù trừ hoặc ghi nhận sự kiện phù hợp.
- Kiểm tra engine của từng bảng trước khi kết luận về tính nguyên tử của nghiệp vụ.

## 8. Quy trình đánh giá engine trước khi triển khai

Thực hiện theo các bước sau cho mỗi workload quan trọng:

1. **Mô tả nghiệp vụ và dữ liệu.** Xác định quan hệ, constraint, transaction boundary và yêu cầu nhất quán.
2. **Mô tả concurrency.** Ước lượng số client, tỷ lệ đọc/ghi, điểm nóng và transaction dài.
3. **Đặt mục tiêu durability.** Xác định RPO/RTO, yêu cầu commit, backup và phục hồi.
4. **Liệt kê truy vấn quan trọng.** Lấy truy vấn thực tế, tần suất, dữ liệu đầu vào và kết quả cần trả.
5. **Kiểm tra khả năng engine.** Xác minh transaction, foreign key, index method, kiểu dữ liệu và giới hạn trên phiên bản mục tiêu.
6. **Thiết kế schema và index.** Đặt khóa chính, secondary index và constraint theo workload.
7. **Benchmark có kiểm soát.** Dùng tập dữ liệu và concurrency gần production; đo latency, throughput, I/O, memory, lock wait và dung lượng.
8. **Thử lỗi và phục hồi.** Kiểm tra restart, crash scenario phù hợp, backup/restore và replication nếu có.
9. **Ghi nhận quyết định.** Nêu engine được chọn, lý do, giới hạn chấp nhận và cách theo dõi khi vận hành.

Không chọn engine dựa trên một benchmark đơn giản với vài hàng dữ liệu. Dữ liệu lớn hơn, phân bố khác, index khác và mức đồng thời cao có thể làm kết quả đảo chiều.

## 9. Kiểm tra engine trên MySQL Server

Trước khi tạo bảng hoặc đánh giá một môi trường, kiểm tra engine có được hỗ trợ hay không.

### 9.1. Xem engine được server hỗ trợ

```sql
SHOW ENGINES;
```

Có thể xem engine mặc định:

```sql
SELECT @@default_storage_engine;
```

Hoặc truy vấn các thuộc tính engine:

```sql
SELECT
    ENGINE,
    SUPPORT,
    TRANSACTIONS,
    XA,
    SAVEPOINTS
FROM INFORMATION_SCHEMA.ENGINES
ORDER BY ENGINE;
```

Trạng thái hỗ trợ và thuộc tính được báo cáo bởi server hiện tại. Nếu một engine không khả dụng hoặc bị vô hiệu hóa, câu lệnh tạo bảng chỉ định engine đó có thể thất bại hoặc server xử lý theo cấu hình liên quan. Hãy kiểm tra thông báo thực tế và không dựa vào giả định.

### 9.2. Chỉ định engine khi tạo bảng

```sql
CREATE TABLE event_log (
    event_id BIGINT NOT NULL AUTO_INCREMENT,
    event_type VARCHAR(50) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id),
    KEY idx_event_created (created_at)
) ENGINE = InnoDB;
```

Nên ghi rõ ENGINE trong DDL của các bảng quan trọng để lựa chọn được thể hiện trong schema và review. Nếu bỏ ENGINE, MySQL sử dụng giá trị default_storage_engine hiện tại của server.

### 9.3. Kiểm tra engine thực tế của bảng

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    ENGINE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = DATABASE()
ORDER BY TABLE_NAME;
```

Kiểm tra một bảng cụ thể bằng SHOW CREATE TABLE:

```sql
SHOW CREATE TABLE event_log;
```

Metadata giúp phát hiện bảng bị tạo nhầm engine giữa các môi trường hoặc engine đã thay đổi trong quá trình migration.

### 9.4. Chuyển đổi engine

Có thể chuyển engine bằng ALTER TABLE:

```sql
ALTER TABLE event_log ENGINE = InnoDB;
```

Chuyển đổi có thể xây dựng lại bảng và index, tiêu tốn I/O, dung lượng tạm và thời gian. Tác động khóa và khả năng online phụ thuộc phiên bản, loại thay đổi, engine nguồn/đích và kích thước bảng. Trước khi chuyển đổi trên production, cần:

- Kiểm tra tính năng và constraint có tương thích với engine đích không.
- Đo dung lượng cần thiết và thời gian chuyển đổi.
- Đánh giá lock, thời gian chặn ghi và replication lag.
- Tạo backup có thể restore và thử trước trong staging.
- Chuẩn bị cửa sổ bảo trì cùng phương án quay lui.

Không coi ALTER TABLE đổi engine là thao tác tức thời hoặc luôn không khóa.

## 10. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Chọn engine chỉ vì benchmark nhanh | Workload thật có thể chậm hoặc mất tính năng cần thiết | Đo truy vấn, transaction và concurrency thực tế |
| Dùng engine non-transactional cho nghiệp vụ nhiều bước | Không thể rollback đầy đủ khi lỗi | Dùng InnoDB cho các bảng của transaction |
| Cho rằng mọi engine có foreign key và MVCC | Constraint hoặc isolation không hoạt động như kỳ vọng | Xác minh feature support theo engine |
| Cho rằng InnoDB tự bảo đảm không mất dữ liệu trong mọi sự cố | Cấu hình flush, binlog và phần cứng có thể làm thay đổi durability | Đặt RPO/RTO, kiểm tra cấu hình và thử restore |
| Dùng MEMORY làm nguồn dữ liệu duy nhất | Dữ liệu mất sau restart | Chỉ dùng cho dữ liệu tạm có thể tái tạo |
| Bỏ qua engine thực tế của từng bảng | Một transaction có thể trộn bảng với ngữ nghĩa khác nhau | Kiểm tra INFORMATION_SCHEMA.TABLES |
| Đổi engine trực tiếp trên production mà không đánh giá | Lock, thời gian chuyển đổi hoặc hết dung lượng | Thử staging, backup và lập kế hoạch migration |

## 11. Ghi nhớ

- Chọn engine từ yêu cầu toàn vẹn, concurrency, durability và truy vấn của workload.
- InnoDB là lựa chọn mặc định phù hợp cho phần lớn ứng dụng giao dịch vì có transaction, MVCC, foreign key, khóa phù hợp và crash recovery.
- MyISAM không có transaction kiểu InnoDB và dùng khóa bảng; MEMORY lưu nội dung bảng trong RAM và mất dữ liệu khi restart.
- ARCHIVE và NDB Cluster phục vụ các nhu cầu chuyên biệt; cần kiểm tra feature set, phiên bản và hạ tầng trước khi dùng.
- Độ bền của InnoDB còn phụ thuộc cấu hình redo/binlog, hệ điều hành, thiết bị lưu trữ và backup/restore.
- Index và execution plan ảnh hưởng đến hiệu năng lẫn phạm vi khóa, vì vậy phải đánh giá truy vấn cùng với engine.
- Trộn engine trong một transaction có thể làm mất atomicity trên các bảng non-transactional.
- Xác minh engine bằng SHOW ENGINES, @@default_storage_engine và INFORMATION_SCHEMA.TABLES; ghi rõ ENGINE trong DDL quan trọng.

Với cách đánh giá có hệ thống, bạn có thể chọn engine đáp ứng yêu cầu nghiệp vụ hiện tại, dự đoán được giới hạn của nó và có kế hoạch kiểm thử, triển khai, backup cùng phục hồi phù hợp cho MySQL.

