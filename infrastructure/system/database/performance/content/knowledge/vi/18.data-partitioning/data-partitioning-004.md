# Chỉ mục cục bộ, chỉ mục toàn cục và ràng buộc theo hệ quản trị

Khi một bảng lớn được chia thành nhiều phân vùng, chỉ mục cũng cần được tổ chức phù hợp với cách dữ liệu được chia và cách truy vấn truy cập dữ liệu. Một chỉ mục có thể được chia thành các phần tương ứng với từng phân vùng của bảng, hoặc được tổ chức độc lập trên phạm vi nhiều phân vùng. Hai cách này tạo ra khác biệt về tốc độ tìm kiếm, khả năng bảo trì, tính duy nhất và các thao tác quản lý phân vùng.

Trong chương **Phân vùng dữ liệu** của module **DATABASE_PERFORMANCE**, bài học này giải thích chỉ mục cục bộ (local index), chỉ mục toàn cục (global index) và các ràng buộc mà hệ quản trị áp dụng khi bảng được phân vùng. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung bao gồm thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng sau điều chỉnh. Vì vậy, lựa chọn cấu trúc chỉ mục phải cân bằng giữa truy vấn, quy tắc toàn vẹn, chi phí ghi và thao tác vòng đời phân vùng.

## 1. Vì sao chỉ mục cần được thiết kế cùng với phân vùng?

Partitioning chia một bảng logic thành nhiều phân vùng được quản lý riêng theo một khóa, chẳng hạn thời gian, tenant hoặc vùng dữ liệu. Một truy vấn có điều kiện phù hợp trên khóa phân vùng có thể loại bỏ những phân vùng không liên quan (partition pruning), nhờ đó giảm số dữ liệu cần đọc.

Chỉ mục cung cấp đường truy cập đến hàng trong bảng. Khi bảng được phân vùng, hệ quản trị cần xác định cách chỉ mục tương ứng với các phân vùng đó. Cách tổ chức này ảnh hưởng đến:

- Số cấu trúc chỉ mục cần mở hoặc quét khi truy vấn.
- Khả năng tìm kiếm khi điều kiện không chứa khóa phân vùng.
- Khả năng giữ chỉ mục nhất quán khi thêm, xóa, truncate, detach hoặc switch partition.
- Việc thực thi UNIQUE và PRIMARY KEY trên toàn bảng.
- Chi phí tạo, rebuild, cập nhật và phục hồi chỉ mục.
- Khả năng nạp dữ liệu hoặc loại bỏ phân vùng nhanh chóng.
- Mức độ song song hóa và bảo trì từng phân vùng.

Không có một loại chỉ mục tốt nhất cho mọi workload. Truy vấn chủ yếu lọc theo tháng có thể phù hợp với chỉ mục cục bộ gắn với từng phân vùng thời gian. Truy vấn tìm một mã đơn hàng duy nhất mà không biết thời gian có thể cần cấu trúc chỉ mục có thể tìm trên toàn bộ bảng logic. Quyết định phải dựa trên mẫu truy vấn và thao tác vận hành thực tế.

## 2. Chỉ mục cục bộ (local index)

Chỉ mục cục bộ là chỉ mục được chia thành các phần tương ứng với phân vùng của bảng. Mỗi phân vùng bảng có phần chỉ mục riêng chứa khóa của các hàng trong phân vùng đó. Khi một phân vùng được thêm hoặc loại bỏ, hệ quản trị có thể quản lý phần chỉ mục tương ứng độc lập theo quy tắc của nền tảng.

Mô hình khái niệm:

~~~text
Bảng ORDERS được chia theo tháng
|
+-- PARTITION_2026_01
|   +-- LOCAL INDEX PART_2026_01
|
+-- PARTITION_2026_02
|   +-- LOCAL INDEX PART_2026_02
|
+-- PARTITION_2026_03
    +-- LOCAL INDEX PART_2026_03
~~~

Đặc điểm thường gặp:

- Mỗi phân vùng có cấu trúc chỉ mục riêng.
- Truy vấn đã xác định được phân vùng có thể chỉ truy cập phần chỉ mục của phân vùng đó.
- Việc bảo trì một phân vùng có thể giới hạn ở phần chỉ mục tương ứng.
- Kích thước và mức sử dụng của từng phần chỉ mục có thể khác nhau.
- Truy vấn không có điều kiện trên khóa phân vùng có thể cần tìm trong nhiều phần chỉ mục.

Chỉ mục cục bộ thường phù hợp với bảng lịch sử hoặc bảng sự kiện được chia theo thời gian, nơi truy vấn chủ yếu đọc một vài khoảng thời gian và dữ liệu cũ thường được lưu trữ hoặc loại bỏ theo phân vùng.

### 2.1. Lợi ích trong bảo trì phân vùng

Giả sử bảng orders được chia theo tháng. Khi hết thời hạn lưu giữ, hệ thống cần loại bỏ phân vùng của tháng cũ. Với cấu trúc chỉ mục cục bộ được hệ quản trị hỗ trợ đầy đủ, phần chỉ mục gắn với phân vùng đó có thể được xử lý cùng phân vùng, tránh phải duy trì một cấu trúc chỉ mục toàn cục lớn chứa tham chiếu đến dữ liệu vừa bị loại bỏ.

Tùy hệ quản trị, thao tác có thể là DROP PARTITION, DETACH PARTITION, TRUNCATE PARTITION, SWITCH PARTITION hoặc một quy trình tương đương. Tên lệnh và yêu cầu về trạng thái chỉ mục khác nhau; cần kiểm tra tài liệu trước khi áp dụng.

### 2.2. Giới hạn khi truy vấn không có khóa phân vùng

Nếu bảng chia theo created_at nhưng truy vấn chỉ tìm order_id, hệ quản trị có thể không biết phân vùng nào chứa hàng. Với chỉ mục cục bộ trên order_id, nó có thể cần tìm trong nhiều phần chỉ mục, trừ khi có thêm thông tin giúp loại bỏ phân vùng.

Điều này có thể làm chi phí tăng theo số lượng phân vùng. Một truy vấn tìm theo order_id có thể rất nhanh trên một bảng chưa phân vùng nhưng trở nên tốn kém nếu phải dò hàng trăm chỉ mục cục bộ.

Hãy kiểm tra kế hoạch thực thi để biết có partition pruning hay phải truy cập nhiều phân vùng. Nếu workload thường tìm theo khóa không chứa partition key, hãy đánh giá chỉ mục toàn cục nếu hệ quản trị hỗ trợ, thay đổi khóa phân vùng hoặc thiết kế một cấu trúc tra cứu riêng.

## 3. Chỉ mục toàn cục (global index)

Chỉ mục toàn cục là cấu trúc chỉ mục bao phủ nhiều hoặc toàn bộ phân vùng của bảng, thay vì có một phần chỉ mục độc lập tương ứng với từng phân vùng. Trong các hệ quản trị hỗ trợ thuật ngữ này, chỉ mục có thể tìm khóa trên phạm vi bảng logic mà không cần biết trước khóa phân vùng.

Mô hình khái niệm:

~~~text
BẢNG ORDERS
+-------------------+-------------------+-------------------+
| PARTITION JAN     | PARTITION FEB     | PARTITION MAR     |
+-------------------+-------------------+-------------------+
          \                 |                 /
           \                |                /
            +--------------------------------+
            | GLOBAL INDEX ON ORDER_ID       |
            +--------------------------------+
~~~

Ví dụ, một ứng dụng tìm đơn hàng theo order_id duy nhất nhưng không truyền created_at. Chỉ mục toàn cục trên order_id có thể cung cấp một đường tìm kiếm trực tiếp qua nhiều phân vùng.

Lợi ích tiềm năng:

- Tìm kiếm theo khóa không chứa partition key.
- Có thể thực thi tính duy nhất trên phạm vi nhiều phân vùng.
- Tránh phải dò từng phần chỉ mục cục bộ trong một số truy vấn.
- Hỗ trợ workload truy cập theo mã định danh toàn cục.

Đổi lại, chỉ mục toàn cục có thể khó bảo trì hơn khi một phân vùng bị thay đổi cấu trúc hoặc loại bỏ. Vì chỉ mục chứa mục tham chiếu đến dữ liệu ở nhiều phân vùng, thao tác trên một phân vùng có thể cần cập nhật hoặc rebuild chỉ mục toàn cục.

### 3.1. Global index không đồng nghĩa với một chỉ mục luôn nhanh hơn

Một chỉ mục toàn cục có thể giảm số phần chỉ mục cần dò, nhưng vẫn phải truy cập trang dữ liệu để lấy hàng. Nếu truy vấn cần phần lớn bảng hoặc khóa có độ chọn lọc thấp, quét bảng hoặc quét một số phân vùng có thể rẻ hơn.

Cần xem:

- Điều kiện lọc có chọn lọc không?
- Có biết partition key để pruning không?
- Global index có cần lookup về nhiều phân vùng không?
- Kết quả có tập trung ở một số phân vùng không?
- Chi phí duy trì index khi nạp và loại bỏ phân vùng là bao nhiêu?
- Truy vấn có yêu cầu sắp xếp hoặc lấy một số hàng đầu không?

Chỉ mục toàn cục là một lựa chọn thiết kế theo workload, không phải cách thay thế mặc định cho mọi chỉ mục cục bộ.

## 4. Local prefixed và local nonprefixed index

Trong một số hệ quản trị, đặc biệt là Oracle, chỉ mục cục bộ còn được mô tả theo quan hệ giữa các cột khóa chỉ mục và partition key:

- **Local prefixed index:** partition key là tiền tố của khóa chỉ mục.
- **Local nonprefixed index:** khóa chỉ mục không bắt đầu bằng partition key hoặc không chứa đầy đủ tiền tố phân vùng theo cách được định nghĩa bởi hệ quản trị.

Ví dụ bảng orders phân vùng theo RANGE(created_at):

~~~sql
CREATE INDEX orders_local_prefixed_ix
ON orders (created_at, tenant_id)
LOCAL;
~~~

Chỉ mục trên có created_at làm cột đầu, trùng với partition key. Một ví dụ local nonprefixed:

~~~sql
CREATE INDEX orders_local_nonprefixed_ix
ON orders (tenant_id, status)
LOCAL;
~~~

Chỉ mục nonprefixed vẫn có thể hữu ích cho truy vấn tìm tenant/status trong từng phân vùng. Tuy nhiên, nếu truy vấn không giới hạn created_at, hệ quản trị có thể cần truy cập nhiều phân vùng.

Tên gọi và quy tắc xác định prefixed/nonprefixed có thể khác theo hệ quản trị. Không áp dụng khái niệm Oracle này như một thuộc tính phổ quát của mọi database.

## 5. Tác động đến UNIQUE và PRIMARY KEY

Một câu hỏi quan trọng khi phân vùng là: hệ quản trị có thể bảo đảm một giá trị khóa không bị lặp ở hai phân vùng khác nhau hay không?

Nếu mỗi phân vùng có một chỉ mục duy nhất riêng, từng phần chỉ mục có thể bảo đảm không có giá trị trùng trong chính phân vùng đó. Nhưng nếu cùng một giá trị xuất hiện ở hai phân vùng khác nhau, các chỉ mục riêng lẻ không nhất thiết phát hiện được trùng lặp toàn cục.

Có hai cách tiếp cận phổ biến:

1. Đưa đầy đủ partition key vào khóa UNIQUE/PRIMARY KEY, để mỗi phân vùng có thể kiểm tra phần khóa liên quan và tính duy nhất phù hợp với cấu trúc phân vùng.
2. Dùng một chỉ mục hoặc cơ chế tra cứu toàn cục có thể kiểm tra giá trị trên toàn bảng, nếu hệ quản trị hỗ trợ.

Quy tắc chính xác khác nhau theo hệ quản trị. Đây là lý do không thể sao chép DDL của bảng không phân vùng sang bảng phân vùng mà không xem lại khóa chính và ràng buộc duy nhất.

### 5.1. Khóa nghiệp vụ và partition key

Giả sử order_id phải duy nhất trên toàn hệ thống, còn bảng orders được phân vùng theo created_at. Nếu database chỉ cho phép UNIQUE trên các cột bao gồm created_at, một ràng buộc (order_id, created_at) không bảo đảm order_id đơn lẻ là duy nhất giữa các tháng.

Hai hàng có cùng order_id nhưng created_at khác nhau sẽ có hai tổ hợp khóa khác nhau. Nếu nghiệp vụ yêu cầu order_id duy nhất toàn cục, cần cơ chế bổ sung phù hợp với hệ quản trị, chẳng hạn global unique index ở nền tảng hỗ trợ, một bảng registry chứa order_id duy nhất, hoặc thiết kế ID và khóa khác được bảo đảm duy nhất.

Không nên tự thêm partition key vào PRIMARY KEY rồi kết luận rằng khóa nghiệp vụ cũ vẫn duy nhất. Hãy xác định rõ ràng phạm vi duy nhất mà ứng dụng yêu cầu.

## 6. Oracle: local index và global index

Oracle hỗ trợ rõ ràng chỉ mục cục bộ và toàn cục trên bảng phân vùng. Đây là nền tảng thường dùng hai thuật ngữ này trực tiếp.

### 6.1. Tạo local index

Ví dụ bảng orders phân vùng theo created_at:

~~~sql
CREATE INDEX orders_tenant_created_lix
ON orders (tenant_id, created_at)
LOCAL;
~~~

Oracle tạo các phân vùng chỉ mục tương ứng với phân vùng bảng. Local index có thể được dùng cùng partition pruning để truy cập một hoặc một số phân vùng.

Chỉ mục cục bộ có thể prefixed hoặc nonprefixed tùy thứ tự cột. Chọn thứ tự khóa theo workload, không chỉ theo tên loại index.

### 6.2. Tạo global index

Ví dụ global index không phân vùng:

~~~sql
CREATE INDEX orders_order_id_gix
ON orders (order_id)
GLOBAL;
~~~

Trong Oracle, global index cũng có thể được phân vùng độc lập theo một khóa khác với bảng. Một global partitioned index và một global nonpartitioned index có cách tổ chức, quản lý và chi phí khác nhau.

Global index có thể hỗ trợ tìm order_id mà không cần created_at. Nếu order_id cần UNIQUE trên toàn bảng, global unique index có thể là một phần của cơ chế thực thi ràng buộc, miễn là DDL và quy tắc của Oracle cho phép.

### 6.3. Ràng buộc duy nhất với local index

Một local unique index trên bảng phân vùng cần bao gồm các cột partition key để hệ quản trị có thể bảo đảm tính duy nhất theo từng phân vùng mà không cần dò tất cả phân vùng. Nếu khóa nghiệp vụ không chứa partition key, global unique index có thể là phương án trong Oracle.

Ví dụ, với partition key created_at:

~~~sql
CREATE UNIQUE INDEX orders_id_created_lux
ON orders (order_id, created_at)
LOCAL;
~~~

Chỉ mục này bảo đảm tính duy nhất của cặp (order_id, created_at). Nó không tương đương với UNIQUE(order_id) toàn cục nếu order_id có thể lặp ở hai thời điểm hoặc phân vùng khác nhau.

### 6.4. Bảo trì global index khi thay đổi phân vùng

Các thao tác DROP, TRUNCATE, EXCHANGE hoặc MOVE partition có thể ảnh hưởng trạng thái global index. Oracle có tùy chọn và cơ chế bảo trì index khác nhau tùy lệnh và phiên bản. Nếu không duy trì global index theo cách phù hợp, chỉ mục có thể trở thành UNUSABLE hoặc cần rebuild.

Trước thao tác partition maintenance, hãy kiểm tra:

- Những global index nào phụ thuộc vào bảng.
- Lệnh có cập nhật index tự động hay không.
- Có cần tùy chọn UPDATE GLOBAL INDEXES hoặc cơ chế tương đương không.
- Thời gian, I/O và lock của việc bảo trì.
- Trạng thái index sau thao tác.
- Kế hoạch phục hồi nếu index unusable.

Không dùng cú pháp hoặc giả định từ Oracle cho PostgreSQL, MySQL hay SQL Server.

## 7. PostgreSQL: chỉ mục phân vùng và giới hạn chỉ mục toàn cục

PostgreSQL hỗ trợ bảng partitioned và partitioned index. Khi tạo index trên bảng cha đã phân vùng, PostgreSQL tạo hoặc liên kết các index tương ứng trên các partition con theo quy tắc của phiên bản. Chỉ mục ở bảng cha là đối tượng partitioned index mang tính điều phối; dữ liệu chỉ mục vật lý nằm trên các partition con.

Ví dụ:

~~~sql
CREATE TABLE orders (
    order_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    tenant_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    PRIMARY KEY (order_id, created_at)
) PARTITION BY RANGE (created_at);
~~~

Tạo chỉ mục trên bảng phân vùng:

~~~sql
CREATE INDEX orders_tenant_created_ix
ON orders (tenant_id, created_at);
~~~

PostgreSQL tạo cấu trúc chỉ mục phân vùng và các index tương ứng trên các partition. Khi truy vấn có điều kiện created_at, partition pruning có thể loại bỏ các partition không liên quan; index trên từng partition hỗ trợ tìm kiếm bên trong những partition còn lại.

### 7.1. PostgreSQL không có global index tích hợp cho bảng partitioned

Trong PostgreSQL lõi, index trên bảng partitioned được triển khai theo từng partition; không có global index B-tree tích hợp trải qua tất cả partition như Oracle global index. Do đó, truy vấn theo một khóa không chứa partition key có thể cần truy cập nhiều partition và dùng index cục bộ ở từng partition nếu có.

Nếu muốn ràng buộc UNIQUE hoặc PRIMARY KEY trên bảng partitioned, các cột partition key phải nằm trong khóa ràng buộc theo giới hạn của PostgreSQL. Với partitioning nhiều cấp hoặc partition key gồm nhiều cột, phải đưa đầy đủ các cột partition key cần thiết vào unique key.

Ví dụ PRIMARY KEY (order_id, created_at) ở trên bao gồm created_at, là partition key. Nó không bảo đảm order_id đơn lẻ duy nhất giữa mọi partition.

### 7.2. Thiết kế thay thế khi cần ID duy nhất toàn cục

Nếu ứng dụng cần order_id duy nhất toàn cục nhưng bảng orders phân vùng theo created_at, có thể dùng bảng registry không phân vùng:

~~~sql
CREATE TABLE order_id_registry (
    order_id BIGINT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL
);
~~~

Khi tạo đơn hàng, transaction phải đăng ký order_id vào registry và ghi hàng vào partition tương ứng, với cơ chế bảo đảm tính nguyên tử và xử lý lỗi. Registry có chi phí lưu trữ, ghi và đồng bộ riêng; cần kiểm soát việc xóa, lưu trữ và tính nhất quán giữa hai bảng.

Đây chỉ là một mẫu thiết kế. Có thể dùng UUID hoặc ID sinh từ một hệ thống đảm bảo duy nhất, nhưng nếu không có ràng buộc database toàn cục thì tính duy nhất phải được bảo đảm ở nơi phát sinh ID và được kiểm chứng trong toàn bộ hệ thống.

### 7.3. Foreign key trên bảng partitioned

PostgreSQL hỗ trợ nhiều dạng foreign key liên quan đến bảng partitioned, nhưng khóa được tham chiếu phải đáp ứng yêu cầu PRIMARY KEY/UNIQUE của PostgreSQL. Nếu bảng cha chỉ có unique key chứa partition key, foreign key phải tham chiếu đúng tập cột duy nhất đó. Hãy kiểm tra phiên bản và giới hạn cụ thể, đặc biệt khi có partitioning nhiều cấp.

## 8. MySQL: index theo partition và yêu cầu unique key

MySQL hỗ trợ partitioning với các chỉ mục được duy trì theo partition. Các index trên partitioned table không phải global index độc lập bao phủ tất cả partition theo cách của Oracle.

Một quy tắc quan trọng của MySQL là mọi cột được dùng trong biểu thức partitioning phải nằm trong mọi unique key của bảng, bao gồm PRIMARY KEY. Quy tắc này giúp hệ thống có thể kiểm tra uniqueness trong phạm vi partition tương ứng.

Ví dụ bảng phân vùng theo RANGE COLUMNS(created_at):

~~~sql
CREATE TABLE orders (
    order_id BIGINT NOT NULL,
    created_at DATETIME(6) NOT NULL,
    tenant_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (order_id, created_at),
    KEY orders_tenant_created_ix (tenant_id, created_at)
)
PARTITION BY RANGE COLUMNS (created_at) (
    PARTITION p2026_01 VALUES LESS THAN ('2026-02-01'),
    PARTITION p2026_02 VALUES LESS THAN ('2026-03-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
~~~

PRIMARY KEY có created_at, là cột partitioning. Nếu chỉ khai báo PRIMARY KEY(order_id), MySQL sẽ từ chối đối với thiết kế partition này vì khóa duy nhất không chứa partition key.

### 8.1. Không có global index như Oracle

Các secondary index trên bảng partitioned của MySQL được tổ chức trong từng partition. Nếu truy vấn chỉ lọc order_id mà không có created_at, hệ quản trị có thể cần tìm trong nhiều partition. Việc thêm index trên order_id không tạo ra một global index duy nhất xuyên qua tất cả partition.

Nếu cần order_id duy nhất toàn cục, có thể phải thiết kế khóa chính chứa partition key cùng một cơ chế ID duy nhất bên ngoài hoặc bảng registry không phân vùng. Hãy bảo đảm transaction và quy trình xóa/archiving giữ được uniqueness.

### 8.2. Foreign key trên bảng partitioned

MySQL có giới hạn quan trọng: các bảng InnoDB được partition theo cơ chế user-defined partitioning không hỗ trợ foreign key constraint theo cách thông thường; chúng cũng không thể được tham chiếu bởi foreign key. Điều này ảnh hưởng thiết kế toàn vẹn dữ liệu.

Nếu hệ thống phụ thuộc foreign key để bảo vệ quan hệ, cần đánh giá lại mô hình partitioning, dùng kiểm tra ở tầng ứng dụng hoặc quy trình đối soát có kiểm soát nếu chọn partitioning. Không coi kiểm tra ở ứng dụng là tương đương hoàn toàn với ràng buộc database khi có nhiều writer đồng thời.

Kiểm tra tài liệu phiên bản MySQL cụ thể trước khi triển khai vì hỗ trợ partitioning và engine có thể thay đổi theo phiên bản.

## 9. SQL Server: aligned và nonaligned index

SQL Server thường mô tả chỉ mục trên bảng phân vùng bằng khái niệm **aligned** và **nonaligned**, thay vì dùng local/global như Oracle.

- **Aligned index:** được phân vùng bằng cùng partition function và partition scheme với bảng. Mỗi partition của index tương ứng với partition của bảng.
- **Nonaligned index:** dùng partition scheme khác hoặc không được phân vùng theo cùng cách. Một nonaligned index có thể giúp tìm kiếm trên phạm vi bảng, nhưng có thể hạn chế các thao tác quản lý phân vùng.

Ví dụ khái niệm tạo partition function và scheme:

~~~sql
CREATE PARTITION FUNCTION pfOrdersByDate (date)
AS RANGE RIGHT FOR VALUES
(
    '2026-02-01',
    '2026-03-01',
    '2026-04-01'
);
GO

CREATE PARTITION SCHEME psOrdersByDate
AS PARTITION pfOrdersByDate
ALL TO ([PRIMARY]);
GO
~~~

Tạo bảng trên partition scheme:

~~~sql
CREATE TABLE dbo.Orders (
    OrderId BIGINT NOT NULL,
    CreatedDate date NOT NULL,
    TenantId BIGINT NOT NULL,
    Status varchar(20) NOT NULL,
    CONSTRAINT PK_Orders
        PRIMARY KEY CLUSTERED (OrderId, CreatedDate)
) ON psOrdersByDate(CreatedDate);
~~~

Ví dụ chỉ mục aligned:

~~~sql
CREATE NONCLUSTERED INDEX IX_Orders_Tenant_Date
ON dbo.Orders (TenantId, CreatedDate)
ON psOrdersByDate(CreatedDate);
~~~

Chỉ mục aligned phù hợp với partition-level maintenance và có thể hỗ trợ partition elimination khi truy vấn có điều kiện trên CreatedDate.

### 9.1. Unique index và partition key

Với một unique index được phân vùng theo partition scheme, partitioning column cần nằm trong khóa duy nhất để bảo đảm uniqueness qua các partition theo cơ chế của SQL Server. Nếu cần uniqueness không chứa partitioning column, có thể cần một unique index nonaligned hoặc một thiết kế khác. Cách triển khai và khả năng partition switching bị ảnh hưởng bởi lựa chọn này.

SQL Server không thường dùng thuật ngữ global index như Oracle. Khi mô tả một index nonaligned hoặc không phân vùng trên bảng partitioned, hãy nêu rõ cấu trúc và phạm vi thực tế thay vì mặc định nó có cùng ngữ nghĩa với Oracle global index.

### 9.2. Partition switching và nonaligned index

Một lợi ích lớn của aligned index là hỗ trợ các thao tác chuyển dữ liệu giữa bảng staging và partition với điều kiện phù hợp. Nonaligned index có thể làm thao tác SWITCH bị hạn chế hoặc không khả dụng do các hàng của một partition không được ánh xạ riêng trong index.

Trước khi tạo nonaligned index, hãy kiểm tra yêu cầu SWITCH, constraint, filegroup và index trên cả bảng nguồn lẫn bảng đích. Nếu quy trình nạp dữ liệu phụ thuộc partition switching, tính tương thích của index là một tiêu chí thiết kế quan trọng.

## 10. So sánh hành vi giữa các hệ quản trị

Các thuật ngữ local và global không mang cùng một mô hình triển khai trên mọi nền tảng.

| Hệ quản trị | Cấu trúc chỉ mục trên bảng phân vùng | Quy tắc uniqueness đáng chú ý | Foreign key và lưu ý |
|---|---|---|---|
| Oracle | Hỗ trợ local và global index; global có thể partitioned hoặc nonpartitioned | Local unique index cần chứa partition key; global unique index có thể bảo đảm uniqueness trên nhiều partition | Global index cần được xem xét khi bảo trì partition |
| PostgreSQL | Partitioned index với index vật lý trên từng partition; không có global index tích hợp trong lõi | UNIQUE/PRIMARY KEY trên partitioned table phải chứa partition key | Hỗ trợ FK theo các khóa duy nhất hợp lệ; kiểm tra giới hạn phiên bản |
| MySQL | Index được duy trì theo từng partition; không có global index như Oracle | Mọi cột trong partitioning expression phải nằm trong mọi unique key | InnoDB user-partitioned tables có giới hạn không hỗ trợ foreign key |
| SQL Server | Aligned hoặc nonaligned index; không dùng cùng mô hình local/global của Oracle | Unique partitioned index cần partitioning column trong key; nonaligned design có quy tắc riêng | Nonaligned index có thể ảnh hưởng partition switching |

Không nên áp dụng một DDL hoặc giả định của Oracle cho PostgreSQL, MySQL hay SQL Server. Trước khi thiết kế, xác định rõ hệ quản trị, phiên bản, storage engine, loại partitioning và thao tác bảo trì cần hỗ trợ.

## 11. Chọn local hay global theo workload

Có thể dùng các câu hỏi sau để định hướng:

**Truy vấn có thường chứa partition key không?** Nếu hầu hết truy vấn lọc theo created_at và chỉ đọc một vài tháng, local/aligned index thường phù hợp vì partition pruning giới hạn phạm vi truy cập.

**Truy vấn có thường tìm theo ID không chứa partition key không?** Nếu cần tìm một order_id bất kỳ qua mọi tháng, global index ở Oracle có thể hữu ích. Với PostgreSQL hoặc MySQL, cần đánh giá việc dò nhiều partition, thay đổi partition key, registry table hoặc thiết kế ID.

**Có yêu cầu uniqueness toàn cục không?** Nếu có, hãy kiểm tra ràng buộc của hệ quản trị trước khi chọn partition key. Đừng mặc định UNIQUE trên ID đơn lẻ vẫn được hỗ trợ.

**Partition có được drop/truncate/switch thường xuyên không?** Nếu có, ưu tiên cấu trúc index giúp thao tác vòng đời đơn giản và có thời gian bảo trì dự đoán được.

**Tỷ lệ đọc/ghi ra sao?** Global index có thể tăng chi phí duy trì khi dữ liệu ở nhiều partition thay đổi. Local index có thể tăng số cấu trúc cần mở hoặc quét khi truy vấn không biết partition key.

**Dữ liệu cũ có bị archive hoặc loại bỏ theo kỳ không?** Cần đánh giá index có thể được loại bỏ cùng partition hay phải bảo trì trên phạm vi toàn cục.

## 12. Partition pruning kết hợp với index

Partition pruning và index access là hai bước bổ sung nhau:

1. Partition pruning xác định những partition có thể chứa hàng cần tìm.
2. Index access tìm khóa trong từng partition còn lại.
3. Table/heap lookup lấy các cột không có trong index nếu cần.

Ví dụ:

~~~sql
SELECT order_id, total
FROM orders
WHERE created_at >= :start_time
  AND created_at < :end_time
  AND tenant_id = :tenant_id;
~~~

Nếu bảng partition theo created_at, điều kiện thời gian có thể loại bỏ nhiều partition. Một local index trên tenant_id hoặc (tenant_id, created_at) có thể giúp tìm trong từng partition được giữ lại, tùy hệ quản trị và kế hoạch.

Nếu bỏ điều kiện created_at và chỉ lọc tenant_id, partition pruning có thể không xảy ra. Local index có thể cần được dò ở nhiều partition. Global index ở nền tảng hỗ trợ có thể thay đổi đường truy cập, nhưng cần cân nhắc chi phí duy trì.

Không đánh giá index chỉ bằng việc có được dùng hay không. Hãy xem số partition được truy cập, số trang đọc trong mỗi partition, số hàng ước lượng/thực tế và lượng lookup về bảng.

## 13. Tác động của partition maintenance đến index

Các thao tác quản lý phân vùng có thể ảnh hưởng trạng thái và chi phí của chỉ mục:

- Thêm partition mới.
- Tách hoặc gộp partition.
- Drop hoặc truncate partition.
- Detach hoặc attach partition.
- Exchange hoặc switch partition.
- Move partition sang tablespace/filegroup khác.
- Rebuild hoặc coalesce index partition.

Với local/aligned index, hệ quản trị thường có thể giới hạn bảo trì ở partition tương ứng, nhưng vẫn cần kiểm tra trạng thái index và điều kiện của lệnh. Với global/nonaligned index, một thao tác thay đổi partition có thể cần cập nhật nhiều entry hoặc rebuild cấu trúc index.

Trước khi chạy maintenance, hãy lập danh sách index bị ảnh hưởng, xác định tùy chọn bảo trì, thời gian dự kiến, dung lượng tạm và trạng thái index sau thao tác. Nếu index trở thành unusable hoặc disabled, truy vấn có thể chuyển sang quét bảng hoặc kế hoạch khác, làm độ trễ tăng mạnh.

## 14. Quy trình thiết kế và kiểm chứng

Một quy trình thực tế:

1. **Xác định hệ quản trị và phiên bản:** ghi rõ engine, edition, partitioning method và giới hạn hỗ trợ.
2. **Mô tả workload:** query fingerprint, tần suất, p95/p99, điều kiện lọc và khóa tìm kiếm.
3. **Xác định partition key:** xem truy vấn, retention, phân bố dữ liệu và cách nạp/xóa theo kỳ.
4. **Liệt kê yêu cầu toàn vẹn:** PRIMARY KEY, UNIQUE, FOREIGN KEY và phạm vi uniqueness toàn cục.
5. **Lập danh mục index hiện có:** key order, filter, include, uniqueness, local/global hoặc aligned/nonaligned.
6. **Chọn loại index:** dựa trên truy vấn có partition key, truy vấn ID toàn cục và thao tác maintenance.
7. **Kiểm tra DDL trên môi trường thử:** xác nhận hệ quản trị chấp nhận constraint và index đúng như dự kiến.
8. **Đo kế hoạch:** xem partition pruning, index access, số partition và actual rows.
9. **Đo chi phí ghi:** insert, update, delete, bulk load và thời gian bảo trì.
10. **Thử thao tác partition:** add, drop, switch, exchange hoặc detach theo quy trình thực tế.
11. **Kiểm tra tính toàn vẹn:** thử giá trị trùng trong cùng partition và khác partition, xác nhận constraint phản ứng đúng.
12. **Theo dõi production:** p50/p95/p99, CPU, I/O, lock, index status và lỗi sau triển khai.

Không chỉ benchmark truy vấn SELECT. Một thiết kế index có thể cải thiện tìm kiếm nhưng làm chậm bulk load hoặc khiến việc drop partition vượt cửa sổ bảo trì.

## 15. Ví dụ thiết kế: orders phân vùng theo tháng

Giả sử orders được chia theo created_at. Workload gồm:

- Liệt kê đơn theo tenant và khoảng thời gian.
- Tìm đơn theo order_id mà không biết ngày tạo.
- Nạp dữ liệu tháng mới theo batch.
- Xóa dữ liệu cũ sau thời hạn lưu giữ.
- Bảo đảm order_id không trùng toàn hệ thống.

### 15.1. Truy vấn theo thời gian

Với truy vấn:

~~~sql
SELECT order_id, total
FROM orders
WHERE tenant_id = :tenant_id
  AND created_at >= :start_time
  AND created_at < :end_time;
~~~

Partition pruning có thể giới hạn các tháng cần đọc. Local/aligned index trên (tenant_id, created_at) có thể hỗ trợ tìm kiếm trong mỗi partition còn lại.

### 15.2. Tìm theo order_id không có thời gian

Nếu truy vấn:

~~~sql
SELECT order_id, created_at, total
FROM orders
WHERE order_id = :order_id;
~~~

không chứa created_at, hệ quản trị có thể cần tìm trên nhiều partition nếu không có global index. Oracle có thể dùng global index trên order_id. PostgreSQL và MySQL cần giải pháp khác như ID có tính duy nhất toàn cục cùng cấu trúc tra cứu riêng, hoặc chấp nhận dò partition khi số lượng và chi phí phù hợp.

### 15.3. Bảo đảm uniqueness

Nếu database yêu cầu PRIMARY KEY chứa created_at do partitioning rule, khóa (order_id, created_at) không đảm bảo order_id đơn lẻ không trùng. Phải bổ sung cơ chế uniqueness toàn cục phù hợp với hệ quản trị và transaction.

### 15.4. Vận hành retention

Khi loại bỏ tháng cũ, local/aligned index thường dễ bảo trì cùng partition. Nếu có global index, cần kiểm tra thao tác drop/truncate có cập nhật hoặc làm index unusable không. Lập kế hoạch rebuild hoặc update index nếu cần.

### 15.5. Kiểm chứng

Đo riêng ba nhóm truy vấn: theo thời gian, theo order_id và batch nạp/xóa partition. So sánh số partition được truy cập, số hàng đọc, I/O, p95/p99 và thời gian maintenance. Chỉ giữ thiết kế khi cả truy vấn lẫn vận hành đáp ứng mục tiêu.

## 16. Các sai lầm thường gặp

- **Cho rằng local và global có cùng ý nghĩa trên mọi database.** PostgreSQL, MySQL và SQL Server có mô hình khác Oracle.
- **Chỉ nhìn số partition mà bỏ qua index.** Truy vấn có thể pruning đúng nhưng vẫn quét nhiều hàng trong từng partition.
- **Cho rằng local index tìm ID toàn cục nhanh như global index.** Có thể phải dò nhiều phần chỉ mục.
- **Tạo global index mà không xem partition maintenance.** Drop/truncate/exchange có thể làm phát sinh chi phí bảo trì hoặc trạng thái index đặc biệt.
- **Thêm partition key vào PRIMARY KEY rồi nghĩ ID đơn lẻ vẫn duy nhất.** Khóa tổng hợp chỉ bảo đảm duy nhất của toàn bộ tổ hợp.
- **Giả định mọi unique constraint được hỗ trợ trên partitioned table.** Mỗi hệ quản trị có giới hạn riêng.
- **Bỏ qua foreign key.** Một số nền tảng hoặc engine có giới hạn rõ rệt với bảng phân vùng.
- **Dùng thuật ngữ Oracle cho SQL Server hoặc PostgreSQL.** Cần nói đúng aligned/nonaligned hoặc partitioned index theo nền tảng.
- **Chỉ đo SELECT.** Index có thể ảnh hưởng bulk load, write throughput và thời gian bảo trì.
- **Không kiểm tra trạng thái index sau partition maintenance.** Index unusable/disabled có thể làm kế hoạch thay đổi.

## 17. Checklist trước khi chọn loại chỉ mục

- [ ] Đã xác định hệ quản trị, phiên bản và engine.
- [ ] Đã xác định partition key và phương pháp partitioning.
- [ ] Đã mô tả truy vấn có và không có điều kiện partition key.
- [ ] Đã phân biệt local/global hoặc aligned/nonaligned theo đúng nền tảng.
- [ ] Đã kiểm tra thứ tự cột, uniqueness, filter và INCLUDE.
- [ ] Đã xác định phạm vi duy nhất nghiệp vụ yêu cầu.
- [ ] Đã kiểm tra PRIMARY KEY, UNIQUE và FOREIGN KEY có được hỗ trợ không.
- [ ] Đã thử trường hợp trùng khóa ở cùng partition và khác partition.
- [ ] Đã đánh giá truy vấn tìm theo khóa không chứa partition key.
- [ ] Đã đánh giá DROP/TRUNCATE/SWITCH/EXCHANGE/DETACH partition.
- [ ] Đã xác định cách duy trì hoặc rebuild global/nonaligned index.
- [ ] Đã đọc EXPLAIN và xác nhận partition pruning cùng index access.
- [ ] Đã đo p50/p95/p99, CPU, I/O, write throughput và thời gian maintenance.
- [ ] Đã có kế hoạch phục hồi nếu index unusable hoặc constraint không đáp ứng.

## 18. Nguyên tắc cần ghi nhớ

Chỉ mục cục bộ gắn với từng phân vùng và thường thuận lợi cho partition pruning cùng bảo trì từng phân vùng. Chỉ mục toàn cục có thể tìm khóa trên phạm vi nhiều phân vùng và hỗ trợ uniqueness không chứa partition key ở những hệ quản trị có cơ chế này, nhưng thường làm tăng yêu cầu bảo trì khi partition thay đổi.

Các hệ quản trị không triển khai cùng một mô hình: Oracle hỗ trợ local/global index; PostgreSQL và MySQL tổ chức index theo partition với giới hạn riêng về global uniqueness; SQL Server dùng khái niệm aligned/nonaligned. Hãy thiết kế theo đúng nền tảng và phiên bản, xác nhận ràng buộc khóa, thử các thao tác quản lý phân vùng và đo cả truy vấn lẫn chi phí ghi/bảo trì. Một thiết kế tốt phải giữ toàn vẹn dữ liệu và đáp ứng workload trong suốt vòng đời phân vùng.
