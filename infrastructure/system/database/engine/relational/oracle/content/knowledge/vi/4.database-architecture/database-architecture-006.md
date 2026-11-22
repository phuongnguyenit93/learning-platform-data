# Bộ nhớ PGA, vùng làm việc và xử lý sắp xếp hoặc băm trong Oracle Database

Một câu lệnh SQL có thể đọc dữ liệu rất nhanh nhưng mất nhiều thời gian để **sắp xếp**, **ghép hai bảng** hoặc **gom nhóm**. Nguyên nhân không nhất thiết nằm ở tốc độ đọc bảng: Oracle phải dành bộ nhớ để xử lý các thao tác trung gian. Nếu lượng dữ liệu vượt khả năng xử lý trong bộ nhớ được cấp, Oracle có thể ghi những phần trung gian xuống **temporary tablespace (TEMP)** rồi đọc lại, khiến truy vấn phát sinh thêm I/O và chậm đi.

Trong kiến trúc Oracle, vùng bộ nhớ riêng của tiến trình phục vụ SQL được gọi là **PGA (Program Global Area)**. Bên trong phạm vi bộ nhớ do Oracle quản lý có các **SQL work area** dành cho thao tác như sort hoặc hash join. Hiểu được PGA và work area giúp giải thích các câu hỏi thực tế:

- Vì sao hai câu `SELECT` cùng số dòng trả về lại tiêu thụ bộ nhớ rất khác nhau?
- Vì sao `ORDER BY` hoặc `HASH JOIN` có lúc chạy hoàn toàn trong bộ nhớ, có lúc sử dụng nhiều TEMP?
- Vì sao một truy vấn nhanh khi chạy một mình lại chậm khi nhiều người chạy đồng thời?
- `PGA_AGGREGATE_TARGET`, `PGA_AGGREGATE_LIMIT` và `WORKAREA_SIZE_POLICY` có ý nghĩa gì?
- Quan sát loại work area và số lần ghi/đọc TEMP bằng công cụ nào?

Bài này giải thích đường đi của dữ liệu từ thao tác thực thi SQL đến PGA/TEMP, có ví dụ Oracle SQL, truy vấn quan sát và hướng xử lý khi sort/hash tiêu tốn quá nhiều tài nguyên.

## 1. Đặt PGA vào kiến trúc bộ nhớ Oracle

Oracle Database sử dụng **bộ nhớ dùng chung của instance** và **bộ nhớ riêng của các tiến trình**. Hai phạm vi quan trọng là SGA và PGA.

| Thành phần | Bản chất | Nội dung/vai trò điển hình | Đặc điểm chia sẻ |
|---|---|---|---|
| **SGA — System Global Area** | Bộ nhớ dùng chung ở cấp instance | Database buffer cache, shared pool, redo log buffer và các pool khác tùy cấu hình | Nhiều tiến trình của instance truy cập |
| **PGA — Program Global Area** | Bộ nhớ riêng của một tiến trình Oracle | Dữ liệu phục vụ quá trình xử lý riêng: SQL work areas, vùng cấp phát cho tiến trình và cấu trúc riêng khác | Không phải một cache dữ liệu dùng chung cho nhiều server process |
| **UGA — User Global Area** | Vùng lưu trạng thái liên quan đến session | Thông tin trạng thái session, một phần thông tin cursor/private SQL area, v.v. | Vị trí phụ thuộc kiến trúc kết nối: với dedicated server thường nằm trong PGA; với shared server thường nằm trong SGA, có thể ở large pool khi cấu hình |
| **TEMP tablespace** | Không gian lưu trữ tạm trên đĩa hoặc hệ thống storage tương ứng | Các phân đoạn tạm khi một số thao tác không thể xử lý hoàn toàn trong bộ nhớ | Không phải một phần của PGA; được Oracle quản lý trên storage |

Sơ đồ ý niệm với **dedicated server**:

~~~text
                  ORACLE INSTANCE
        +--------------------------------+
        |             SGA                |
        | buffer cache / shared pool /   |
        | redo log buffer / ...          |
        +--------------------------------+
             ^                 ^
             |                 |
     +-------+------+   +------+-------+
     | Server       |   | Server       |
     | Process A    |   | Process B    |
     |              |   |              |
     | PGA A        |   | PGA B        |
     | - SQL area   |   | - SQL area   |
     | - work area  |   | - work area  |
     +-------+------+   +------+-------+
             |                 |
             +--------+--------+
                      v
               TEMP tablespace
         (khi thao tác cần spill)
~~~

Hình mô tả quan hệ kiến trúc, không ngụ ý mỗi tiến trình luôn có đúng một work area hay luôn phải dùng TEMP. Một execution plan có thể cần nhiều work area; nhiều câu lệnh cũng có thể thực thi trong các thời điểm khác nhau trên cùng tiến trình.

### 1.1 PGA thuộc tiến trình, không phải một khối cố định cấp cho từng user

PGA là vùng nhớ **riêng của server/background process**. Với kiểu dedicated server thường thấy, một session làm việc với server process chuyên trách và bộ nhớ PGA của process đó phục vụ các thao tác cần bộ nhớ riêng. Với shared server, nhiều session có thể được phục vụ luân phiên bởi các shared server process; vị trí UGA và cách ánh xạ session với process khác dedicated server.

Do đó không nên diễn giải đơn giản rằng “mỗi user nhận đúng 100 MB PGA”, “mọi session có một PGA riêng biệt bằng nhau” hoặc “đặt PGA 8 GB nghĩa là mỗi câu SQL được dùng 8 GB”. Dung lượng bộ nhớ cấp phát thực tế biến đổi theo:

- Số process và số thao tác SQL đang thực thi.
- Loại operation cần sort/hash và kích thước dữ liệu trung gian.
- Chính sách quản lý work area cùng áp lực bộ nhớ toàn instance.
- Mức độ song song của truy vấn.
- Các loại cấp phát PGA khác ngoài SQL work area.

Oracle quản lý tổng nhu cầu trên nhiều process; việc cấp phát và thu hồi bộ nhớ không giống việc chia sẵn một phần cố định cho từng kết nối.

### 1.2 PGA không thay thế buffer cache

SGA buffer cache giữ các bản sao block dữ liệu được đọc/ghi để nhiều SQL tận dụng. PGA work area chủ yếu chứa **dữ liệu trung gian phục vụ thuật toán thực thi**, chẳng hạn các hàng/khóa cần sắp xếp hoặc bảng băm của một phía phép join.

Ví dụ câu SQL đọc 100.000 hàng từ bảng:

- Block chứa dữ liệu bảng có thể được truy cập qua buffer cache của SGA hoặc cơ chế đọc thích hợp khác.
- Nếu SQL cần sắp xếp 100.000 hàng, thao tác sort có thể dùng SQL work area trong PGA của process phục vụ.
- Nếu work area không đủ cho toàn bộ thao tác, Oracle có thể sinh các run/partition trung gian ở TEMP.

Như vậy, vấn đề thiếu buffer cache và vấn đề thiếu work area **khác nguyên nhân, khác cách quan sát và khác cách điều chỉnh**.

## 2. SQL work area là gì?

**SQL work area** là vùng bộ nhớ do một thao tác trong execution plan sử dụng để xử lý các tập dữ liệu trung gian. Nó là một phần quan trọng của hoạt động dùng PGA, nhưng **không phải toàn bộ PGA**.

Trong execution plan, một số operation thường cần work area:

| Operation trong execution plan | Mục tiêu | Loại dữ liệu trung gian thường cần bộ nhớ |
|---|---|---|
| `SORT ORDER BY` | Sắp xếp dữ liệu theo `ORDER BY` | Hàng/khóa sắp xếp và thông tin liên kết tới hàng |
| `SORT GROUP BY` | Gom nhóm bằng thuật toán sort | Các hàng hoặc khóa nhóm theo thứ tự cần xử lý |
| `SORT UNIQUE` | Loại các giá trị trùng theo cách sort | Giá trị/khóa cần so sánh và khử trùng lặp |
| `WINDOW SORT` | Phục vụ một số analytic/window function | Dữ liệu trong các partition/order phục vụ window |
| `HASH JOIN` | Ghép dữ liệu thông qua bảng băm | Hash table của phía build và các partition nếu cần |
| `HASH GROUP BY` | Gom nhóm dựa trên cấu trúc hash | Hash table chứa khóa nhóm và các giá trị tổng hợp |

Đây là **các operation có thể xuất hiện**, không phải danh sách bắt buộc của mọi `ORDER BY`, `JOIN` hay `GROUP BY`. Optimizer có thể chọn thuật toán khác: chẳng hạn một truy vấn đã lấy dữ liệu theo thứ tự từ index có thể không cần sort độc lập, hoặc phép join nhỏ/chọn lọc có thể dùng nested loops thay vì hash join.

### 2.1 Một câu SQL có thể có nhiều work area

Xét:

~~~sql
SELECT c.region,
       SUM(s.amount) AS sales_amount
FROM sales s
JOIN customers c
  ON c.customer_id = s.customer_id
WHERE s.sale_date >= DATE '2026-01-01'
GROUP BY c.region
ORDER BY sales_amount DESC;
~~~

Một execution plan hợp lệ có thể gồm:

~~~text
SORT ORDER BY                <- sắp xếp tổng doanh thu theo thứ tự giảm
  HASH GROUP BY              <- tính SUM theo region
    HASH JOIN                <- ghép SALES với CUSTOMERS
      TABLE ACCESS ... SALES
      TABLE ACCESS ... CUSTOMERS
~~~

Nếu optimizer chọn cấu trúc này, SQL có các operation có khả năng cần work area: `HASH JOIN`, `HASH GROUP BY` và `SORT ORDER BY`. Chúng không nhất thiết dùng cùng lúc toàn bộ bộ nhớ cực đại; thời điểm hoạt động phụ thuộc cách engine thực thi plan.

Điều quan trọng là **số work area liên quan đến physical operations và các execution instance thực tế**, không chỉ số câu SQL hoặc số bảng trong truy vấn.

### 2.2 Work area thường được cấp phát động

Với chính sách tự động, Oracle ước lượng và quản lý lượng bộ nhớ phù hợp với operation, đồng thời điều chỉnh theo nhu cầu chung. Một work area nhỏ có thể hoàn thành trong PGA. Cùng operation đó dưới tải đồng thời cao có thể được cấp ít bộ nhớ hơn và phải đọc/ghi TEMP.

Một work area đã xử lý xong không có nghĩa toàn bộ PGA của server process lập tức trả lại cho hệ điều hành. Oracle và bộ cấp phát bộ nhớ có thể tái sử dụng vùng đã cấp phát; vì vậy **PGA allocated** và **PGA currently used** là hai khái niệm cần phân biệt.

## 3. Điều gì xảy ra khi Oracle sắp xếp dữ liệu?

Giả sử:

~~~sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE order_date >= DATE '2026-01-01'
ORDER BY total_amount DESC, order_id;
~~~

Oracle phải cung cấp kết quả theo thứ tự yêu cầu. Nếu đường truy cập không tạo sẵn đúng thứ tự cần thiết, execution plan có thể chứa `SORT ORDER BY`.

### 3.1 Trường hợp đủ bộ nhớ: in-memory sort

Quá trình ở mức khái niệm:

1. Oracle lấy những hàng thuộc kết quả sau khi áp dụng các điều kiện có thể đẩy xuống.
2. Operation sort giữ cấu trúc cần thiết trong work area.
3. Oracle so sánh các khóa `total_amount` và `order_id` theo thứ tự được yêu cầu.
4. Hàng được trả về theo thứ tự đã sắp xếp.

Khi bộ nhớ đủ cho thuật toán thực thi, thao tác có thể hoàn tất **không cần ghi dữ liệu sort trung gian xuống TEMP**. Đây thường được gọi là thực thi **optimal** của work area. “Optimal” ở đây là phân loại theo nhu cầu bộ nhớ/TEMP của operation, không phải khẳng định toàn bộ SQL đã có execution plan tối ưu nhất.

### 3.2 Trường hợp thiếu bộ nhớ: external sort và TEMP

Khi work area không chứa đủ dữ liệu:

1. Oracle sắp xếp được một phần dữ liệu trong bộ nhớ.
2. Các phần đã xử lý có thể được ghi thành những đoạn trung gian ở TEMP.
3. Oracle đọc/merge các đoạn để tạo kết quả có thứ tự.
4. Nếu lượng bộ nhớ quá ít so với dữ liệu, quá trình có thể phải đọc/ghi qua nhiều lượt.

~~~text
Nguồn dữ liệu nhiều hàng
         |
         v
    SORT work area (PGA)
         |
   +-----+------+
   |            |
Đủ bộ nhớ    Không đủ bộ nhớ
   |            |
Sort trong   Tạo các run và
PGA          ghi xuống TEMP
   |            |
   |       Đọc/merge từ TEMP
   |            |
   +-----+------+
         v
     Kết quả ORDER BY
~~~

Dữ liệu ở TEMP trong tình huống này là **trung gian để tính toán**, không phải bản sao dữ liệu nghiệp vụ dùng lâu dài. Sau khi operation và tài nguyên liên quan kết thúc, Oracle quản lý giải phóng/tái sử dụng vùng tạm theo cơ chế của nó.

### 3.3 Những yếu tố làm sort tốn bộ nhớ

Sort trên 10.000 khóa nhỏ không tương đương sort trên 10.000 hàng rộng. Nhu cầu work area phụ thuộc đáng kể vào:

- **Số hàng đầu vào** sau khi lọc, không chỉ số hàng hiển thị trên màn hình.
- **Kích thước hàng và biểu thức sort** mà plan phải mang theo.
- **Số cột và quy tắc thứ tự**, việc cần phân biệt nhiều giá trị bằng nhau.
- **Các operation đứng trước/sau sort**, chẳng hạn join mở rộng tập dữ liệu.
- **Số execution đồng thời** và tài nguyên mà Oracle có thể cấp cho work area.

Ví dụ `SELECT * ... ORDER BY ...` trên hàng chứa nhiều cột lớn có thể tạo nhu cầu xử lý khác đáng kể so với việc chỉ sắp xếp các khóa hẹp. Tuy nhiên optimizer có thể trì hoãn lấy cột hoặc chọn các biến thể plan khác, nên phải dựa trên **plan thực tế** thay vì tự nhân số hàng với kích thước dòng rồi coi đó là lượng PGA chính xác.

### 3.4 Có phải cứ ORDER BY là tạo SORT ORDER BY?

Không. Một index có thể cung cấp thứ tự phù hợp với điều kiện lọc và hướng sắp xếp. Ví dụ:

~~~sql
CREATE INDEX idx_orders_customer_date
ON orders (customer_id, order_date DESC, order_id DESC);

SELECT order_id, order_date, total_amount
FROM orders
WHERE customer_id = :p_customer_id
ORDER BY order_date DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Trong trường hợp phù hợp, Oracle có thể tận dụng thứ tự index để lấy các bản ghi gần nhất của một khách hàng mà không sort toàn bộ tập kết quả. Nhưng nó **không bắt buộc** phải chọn index này: quyết định còn phụ thuộc thống kê, độ chọn lọc và chi phí.

Truy vấn dùng `FETCH FIRST 20 ROWS ONLY` có thể được tối ưu bằng các phương án top-N như `SORT ORDER BY STOPKEY`; điều đó khác sort toàn bộ kết quả để trả tất cả hàng. Tạo index chỉ để bỏ sort cũng có giá: lưu trữ, bảo trì khi DML, và đôi khi hiệu quả kém với báo cáo đọc phần lớn bảng.

## 4. Hash join: work area lưu bảng băm như thế nào?

Khi nối hai tập dữ liệu có điều kiện bằng nhau, optimizer có thể chọn **hash join**. Mô hình đơn giản thường có hai bước:

1. **Build:** lấy một phía join, thường là phía dự đoán nhỏ hơn hoặc phù hợp làm build input, tạo hash table theo khóa join trong work area.
2. **Probe:** đọc phía còn lại; từ khóa join tính hash rồi tìm các hàng tương ứng trong hash table, kiểm tra điều kiện join để tạo kết quả.

Ví dụ:

~~~sql
SELECT c.segment, SUM(s.amount) AS total_amount
FROM sales s
JOIN customers c
  ON s.customer_id = c.customer_id
GROUP BY c.segment;
~~~

Giả sử `CUSTOMERS` nhỏ và `SALES` lớn:

~~~text
CUSTOMERS (build input)                 SALES (probe input)
        |                                      |
        v                                      |
Tạo hash table trong SQL work area (PGA)       |
        |                                      |
        +------------- HASH JOIN <-------------+
                           |
                           v
                    Dữ liệu ghép hàng
                           |
                           v
                    HASH GROUP BY
~~~

Đây là luồng minh họa cho plan có hash join; optimizer có quyền chọn thứ tự build/probe và chiến lược khác. Hash join đặc biệt hấp dẫn khi cần nối những tập dữ liệu tương đối lớn, trong khi nested loops có thể tốt hơn nếu phía ngoài nhỏ và phía trong có index truy cập rất chọn lọc.

### 4.1 Khi hash table vừa trong PGA

Oracle có thể giữ cấu trúc hash cần thiết trong work area và probe trực tiếp. Đây là tình huống tránh I/O trung gian do hash join gây ra, giúp thao tác nhanh khi các điều kiện khác tương đương.

### 4.2 Khi hash table lớn hơn bộ nhớ được cấp

Oracle có thể chia các dữ liệu tham gia join thành **hash partitions**, ghi một phần partition trung gian xuống TEMP, rồi xử lý từng phần khi có đủ bộ nhớ:

~~~text
Build + Probe inputs
        |
        v
  Hash partitioning
        |
        +----> Partitions xử lý trong PGA
        |
        +----> Partitions ghi xuống TEMP
                              |
                         đọc lại / join
                              |
                              v
                         Kết quả join
~~~

Nếu work area bị giới hạn nhiều, các partition có thể tiếp tục cần chia lại hoặc xử lý qua nhiều lượt. Số lần đọc/ghi trung gian tăng là một trong các nguyên nhân hash join chậm khi áp lực PGA cao.

**Một truy vấn hash join dùng TEMP không có nghĩa bảng dữ liệu gốc được “chuyển sang TEMP”.** Oracle chỉ đang dùng TEMP cho dữ liệu trung gian của thuật toán.

### 4.3 Dữ liệu và thống kê ảnh hưởng phép hash join

Các yếu tố quan trọng gồm:

- Kích thước thực của build input sau filter và projection.
- Độ phân bố khóa join, bao gồm các khóa quá phổ biến gây skew.
- Chênh lệch giữa số hàng optimizer ước lượng và số hàng thực tế.
- Chi phí nối so với các lựa chọn như nested loops hoặc sort merge join.
- Khả năng cấp work area khi số truy vấn đồng thời thay đổi.
- Parallel execution có thể tạo thêm work area ở nhiều parallel execution server.

Nếu optimizer ước lượng sai độ lớn dữ liệu, plan có thể chọn một chiến lược kém phù hợp. Việc đầu tiên nên xem là **thống kê và cardinality thực tế**, không tự động tăng PGA hoặc ép hint `USE_HASH` cho mọi join.

## 5. Hash group by, sort group by và dữ liệu phân tích

Phép `GROUP BY` có thể được thực thi theo nhiều cách. Hai loại phổ biến là:

**Hash group by:** tạo cấu trúc hash theo khóa nhóm; với mỗi hàng đầu vào, tìm/tạo nhóm rồi cập nhật các đại lượng như `SUM`, `COUNT`, `MIN`, `MAX`. Work area có thể tăng đáng kể khi số nhóm khác nhau rất lớn hoặc trạng thái tổng hợp phức tạp.

**Sort group by:** sắp xếp theo khóa nhóm rồi xử lý các hàng cùng nhóm ở gần nhau. Chi phí phụ thuộc số hàng/khóa và phương án sort.

Ví dụ:

~~~sql
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM orders
WHERE order_date >= DATE '2026-01-01'
GROUP BY customer_id;
~~~

Nếu có một triệu đơn nhưng chỉ 200 khách hàng, số nhóm cuối tương đối ít. Nếu có một triệu đơn tương ứng gần một triệu khách hàng, số nhóm rất lớn. Hai trường hợp cùng số hàng đầu vào nhưng yêu cầu bộ nhớ cho hash aggregation có thể khác đáng kể.

Sau `GROUP BY`, `ORDER BY total_amount DESC` còn có thể tạo **một operation sort khác** để sắp xếp các nhóm theo kết quả tổng. Đừng nhầm việc dùng hash group by với việc kết quả đã được sắp xếp: **GROUP BY không đảm bảo thứ tự đầu ra**. Chỉ dùng `ORDER BY` khi nghiệp vụ thực sự cần thứ tự.

Các thao tác `DISTINCT`, một số phép toán tập hợp hoặc window function cũng có thể đòi hỏi sort/hash tương tự. Tuy nhiên cùng cú pháp SQL không cố định thành một operator duy nhất: hãy đọc actual execution plan của bản Oracle và dữ liệu đang chạy.

## 6. Ba chế độ thực thi work area: optimal, one-pass, multi-pass

Oracle thường phân loại một lần thực thi work area theo lượng bộ nhớ được cấp so với nhu cầu operation:

| Chế độ | Diễn giải ý niệm | Tác động thường thấy |
|---|---|---|
| **Optimal** | Operation được xử lý trong bộ nhớ được cấp, không cần ghi/đọc TEMP cho dữ liệu trung gian của operation đó | Ít I/O trung gian, thường nhanh nhất trong cùng điều kiện |
| **One-pass** | Bộ nhớ không đủ giữ mọi dữ liệu trung gian; operation dùng TEMP nhưng có thể hoàn tất phần xử lý cần thiết với một lượt xử lý bổ sung theo thuật toán | Có thêm I/O TEMP và thời gian chờ |
| **Multi-pass** | Bộ nhớ quá nhỏ so với dữ liệu/thuật toán, phải lặp việc phân hoạch/merge qua nhiều lượt | I/O trung gian tăng đáng kể, thường là dấu hiệu cần điều tra |

Đây là cách phân nhóm tổng quát, không phải công thức “optimal = 1 lần quét bảng, one-pass = 2 lần quét bảng”. Các pass liên quan **xử lý dữ liệu trung gian của work area**, không nhất thiết đếm số lần quét bảng gốc. Thuật toán sort và hash cũng không có quá trình thực thi giống hệt nhau.

### 6.1 Ví dụ cùng SQL, điều kiện bộ nhớ khác nhau

Một báo cáo nhóm theo khách hàng có thể chạy như sau:

~~~text
                       CÙNG MỘT SQL
                              |
         +--------------------+--------------------+
         |                    |                    |
 Nhiều bộ nhớ còn rảnh   Tải đồng thời tăng    Giới hạn bộ nhớ cao áp lực
         |                    |                    |
 Work area đủ          Work area nhỏ hơn       Work area rất nhỏ
         |                    |                    |
      OPTIMAL              ONE-PASS             MULTI-PASS
         |                    |                    |
 Ít/không TEMP của      Đọc/ghi TEMP          Nhiều lần xử lý
 operation              bổ sung                qua TEMP
~~~

Hình chỉ minh họa khả năng thay đổi chế độ thực thi. Oracle có thể thay đổi plan, điều chỉnh phân bổ động, thay đổi DOP hoặc thực hiện tối ưu khác, vì vậy chế độ không chỉ do “RAM còn trống” quyết định.

### 6.2 Khi nào TEMP xuất hiện là vấn đề?

Không phải mọi lần dùng TEMP đều là lỗi. Một báo cáo lịch sử lớn có thể chủ động dùng TEMP để hoàn tất đúng kết quả, trong khi giá thành của việc giữ toàn bộ dữ liệu trung gian trong RAM có thể không hợp lý. Vấn đề cần đánh giá theo:

- SLA thời gian hoàn tất báo cáo.
- Mức I/O TEMP, lượng TEMP tiêu thụ và số pass của work area.
- Có xuất hiện multi-pass hoặc đột biến khi nhiều SQL chạy đồng thời không.
- Ảnh hưởng lên các giao dịch nghiệp vụ cùng instance.
- Bộ nhớ và lưu trữ hiện có, chi phí thay đổi kế hoạch truy vấn.

## 7. Oracle tự quản lý PGA và work area như thế nào?

Ba tham số thường gặp:

### 7.1 PGA_AGGREGATE_TARGET — mục tiêu bộ nhớ toàn instance

`PGA_AGGREGATE_TARGET` định nghĩa **mục tiêu tổng hợp** để Oracle điều phối lượng PGA đối với các thành phần phù hợp, đặc biệt khi quản lý work area tự động. Đây là **mục tiêu (target), không phải hạn mức cứng cho một session, một truy vấn hoặc thậm chí một ngưỡng bất biến tuyệt đối của tổng PGA**.

Ví dụ giả định mục tiêu PGA là 4 GiB:

- Không có nghĩa mỗi session được dùng 4 GiB.
- Không có nghĩa Oracle giữ sẵn đúng 4 GiB RAM để nhàn rỗi.
- Không đảm bảo 10 truy vấn song song mỗi truy vấn có thể lấy 400 MiB.
- Tổng PGA thực tế có thể vượt target do các loại cấp phát và áp lực khác nhau.

Oracle cần cân bằng nhiều process và nhiều operation, vì vậy **tổng tải đồng thời** quan trọng hơn con số bộ nhớ của một câu lệnh chạy đơn lẻ.

### 7.2 WORKAREA_SIZE_POLICY — AUTO và MANUAL

`WORKAREA_SIZE_POLICY` điều khiển cách sizing SQL work areas:

| Giá trị | Ý nghĩa | Tình huống sử dụng |
|---|---|---|
| **AUTO** | Oracle tự quản lý mức bộ nhớ cho các SQL work area theo cơ chế/giới hạn đang cấu hình | Hướng thông dụng và được ưu tiên trong đa số hệ thống hiện đại |
| **MANUAL** | Sizing work area dựa vào các thiết lập thủ công liên quan như `SORT_AREA_SIZE`, `HASH_AREA_SIZE` | Chủ yếu cần hiểu khi vận hành hệ thống legacy hoặc khảo sát có kiểm soát |

Hai tham số `SORT_AREA_SIZE` và `HASH_AREA_SIZE` **không phải núm điều khiển trực tiếp cho từng sort/hash khi đang dùng AUTO**. Việc đổi sang MANUAL chỉ để ép một câu truy vấn nhanh hơn có thể làm quản lý đồng thời kém ổn định, nên không phải hướng tối ưu mặc định.

### 7.3 PGA_AGGREGATE_LIMIT — giới hạn bảo vệ

`PGA_AGGREGATE_LIMIT` đặt một ngưỡng tổng PGA mang tính **giới hạn bảo vệ** theo tính năng và phiên bản Oracle. Khi tổng PGA vượt giới hạn và không thể được khắc phục theo cơ chế quản lý, Oracle có thể hủy call hoặc kết thúc session/process thuộc diện áp dụng; có những loại tiến trình được xử lý khác theo quy định của Oracle.

Điểm khác nhau:

~~~text
PGA_AGGREGATE_TARGET  = mức mục tiêu để Oracle quản lý/cân bằng
PGA_AGGREGATE_LIMIT   = giới hạn bảo vệ tổng PGA, có hậu quả khi vượt
~~~

Không coi `LIMIT` là “mức cấp trước” cho câu SQL; cũng không tăng nó vô hạn chỉ để giấu một truy vấn tiêu tốn bộ nhớ. Nếu gặp lỗi giới hạn PGA, cần điều tra SQL, mức đồng thời, các PGA consumer khác và bộ nhớ khả dụng của máy chủ.

### 7.4 Các chế độ quản lý bộ nhớ tổng thể

Một số triển khai còn dùng `MEMORY_TARGET` để Oracle điều phối bộ nhớ giữa SGA và PGA theo cơ chế Automatic Memory Management. Môi trường khác dùng riêng `SGA_TARGET` và `PGA_AGGREGATE_TARGET` hoặc có cấu hình quản lý bởi dịch vụ database.

Vì vậy, trước khi đề xuất tăng PGA phải kiểm tra **phiên bản, edition, môi trường triển khai (on-premises/managed service), cấu hình bộ nhớ hiện có và giới hạn RAM thực**. Cấu hình hợp lệ ở một Oracle instance không nhất thiết áp dụng nguyên xi cho một instance khác hoặc một PDB trong hệ thống đa tenant.

## 8. Vì sao chạy song song và nhiều session dễ tạo áp lực PGA?

Giả sử một câu SQL dùng hash join và sort sau khi join. Khi một session chạy, Oracle có thể cấp work area đủ để hạn chế TEMP. Nếu có nhiều session chạy đồng thời cùng câu hoặc nhiều báo cáo khác, nhu cầu memory tăng trong toàn instance.

Với **Parallel Query**, một câu SQL có thể được phân chia cho nhiều parallel execution server. Các process đó có thể có work area riêng cho phần việc của chúng, cộng với nhu cầu phối hợp và truyền dữ liệu. Số process, số operation và kiểu plan quyết định mức tiêu thụ thực tế; không thể tính chắc “PGA của câu SQL = DOP × một work area” mà bỏ qua những phần kế hoạch và điều phối khác.

~~~text
                         Một báo cáo
                             |
                    Parallel execution
                  /          |          \
             PX server   PX server   PX server
              PGA          PGA          PGA
           hash/sort     hash/sort     hash/sort
                  \          |          /
                      Kết quả chung

    + Các session OLTP và báo cáo khác đang dùng cùng instance
~~~

Tăng độ song song đôi khi giảm thời gian của **một** báo cáo khi đủ tài nguyên, nhưng cũng có thể làm chậm hệ thống khi nhiều báo cáo chạy một lúc vì CPU, I/O, PGA và TEMP bị cạnh tranh. Đánh giá parallelism phải có kịch bản đồng thời, không chỉ benchmark một query khi máy rảnh.

## 9. Quan sát cấu hình và sử dụng PGA bằng SQL

Các ví dụ sau chủ yếu **đọc thông tin** qua dynamic performance views. Tài khoản bình thường có thể không được cấp quyền xem các view `V$`; hãy sử dụng account được cấp quyền phù hợp hoặc nhờ DBA chạy truy vấn. Không tự cấp quyền `SELECT ANY DICTIONARY` hoặc `SYSDBA` cho một ứng dụng chỉ để chẩn đoán.

### 9.1 Xem các tham số đang có hiệu lực

~~~sql
SELECT name, display_value
FROM v$parameter
WHERE name IN (
    'pga_aggregate_target',
    'pga_aggregate_limit',
    'workarea_size_policy',
    'memory_target',
    'sga_target'
)
ORDER BY name;
~~~

Kết quả giúp biết Oracle đang quản lý bộ nhớ theo cấu hình nào. Giá trị hiển thị có thể có đơn vị/định dạng của Oracle; cần quy đổi đúng khi so sánh. Truy vấn này **không thay đổi cấu hình**.

### 9.2 Theo dõi toàn instance bằng V$PGASTAT

~~~sql
SELECT name, value, unit
FROM v$pgastat
WHERE name IN (
    'aggregate PGA target parameter',
    'aggregate PGA auto target',
    'global memory bound',
    'total PGA allocated',
    'total PGA inuse',
    'maximum PGA allocated',
    'over allocation count',
    'cache hit percentage',
    'extra bytes read/written'
)
ORDER BY name;
~~~

Một số giá trị ở `V$PGASTAT` có kiểu tính lũy kế hoặc ý nghĩa phụ thuộc thời điểm khởi động và phiên bản; khi điều tra xu hướng, nên lấy **nhiều mẫu theo thời gian** thay vì suy luận từ một snapshot.

| Chỉ số | Cách đọc khái niệm |
|---|---|
| `total PGA allocated` | Tổng PGA đang được Oracle cấp phát ở thời điểm đo, gồm phần đang sử dụng và phần có thể tái sử dụng |
| `total PGA inuse` | Phần PGA đang được process sử dụng tại thời điểm đo |
| `maximum PGA allocated` | Mức tổng PGA allocated cao nhất đã ghi nhận trong khoảng thống kê |
| `aggregate PGA auto target` | Phần mục tiêu PGA mà Oracle hiện dành cho cơ chế tự quản lý work area |
| `global memory bound` | Mức cận bộ nhớ tính toán cho work area trong cơ chế tự động; giảm xuống có thể phản ánh cạnh tranh bộ nhớ cao |
| `over allocation count` | Bộ đếm phản ánh các lần Oracle phải vượt mục tiêu PGA trong những tình huống tương ứng |
| `extra bytes read/written` | Khối lượng đọc/ghi bổ sung cho các work area không chạy hoàn toàn optimal |
| `cache hit percentage` | Chỉ số tổng hợp hiệu quả work area, **không phải tỉ lệ hit của SGA buffer cache** |

Không dùng một ngưỡng phần trăm cố định để kết luận mọi hệ thống đang “đủ PGA”. Chẳng hạn cache hit percentage cao ở thời điểm vắng tải không nói lên behavior khi nhiều truy vấn phân tích đồng thời. Cần quan sát các bộ đếm, tốc độ tăng, thời gian truy vấn và TEMP.

### 9.3 Quan sát PGA của từng server process

Trong mô hình dedicated server, có thể liên hệ session với process:

~~~sql
SELECT s.sid,
       s.serial#,
       s.username,
       s.program,
       ROUND(p.pga_used_mem / 1024 / 1024, 1) AS pga_used_mb,
       ROUND(p.pga_alloc_mem / 1024 / 1024, 1) AS pga_alloc_mb,
       ROUND(p.pga_max_mem / 1024 / 1024, 1) AS pga_max_mb
FROM v$session s
JOIN v$process p
  ON p.addr = s.paddr
WHERE s.type = 'USER'
ORDER BY p.pga_alloc_mem DESC;
~~~

Các cột `PGA_USED_MEM`, `PGA_ALLOC_MEM` và `PGA_MAX_MEM` thể hiện những góc nhìn khác nhau của mức dùng/cấp phát/đỉnh đã ghi nhận ở cấp process. Với shared server hoặc parallel execution, không nên áp dụng máy móc giả định **một user session = một process = toàn bộ work area của SQL đó**. Một số work area có thể thuộc process khác với process mà người dùng đang nhìn trong session chính.

### 9.4 Xem work area đã thực thi qua V$SQL_WORKAREA

`V$SQL_WORKAREA` cung cấp số liệu tổng hợp theo SQL và operation có sử dụng work area:

~~~sql
SELECT sql_id,
       operation_id,
       operation_type,
       policy,
       last_execution,
       total_executions,
       optimal_executions,
       onepass_executions,
       multipasses_executions,
       ROUND(last_memory_used / 1024 / 1024, 1) AS last_memory_mb,
       ROUND(last_tempseg_size / 1024 / 1024, 1) AS last_temp_mb
FROM v$sql_workarea
WHERE sql_id = :p_sql_id
ORDER BY operation_id;
~~~

Ở đây `:p_sql_id` là **bind parameter** cần được client cung cấp. `SQL_ID` có thể tìm qua thông tin SQL đang chạy, SQL monitoring hoặc view phù hợp nếu có quyền truy cập. Các dòng là số liệu của **work area operations**, không phải tổng bộ nhớ đúng bằng cả câu SQL trong mọi thời điểm.

Các bộ đếm optimal/one-pass/multi-pass cho biết phân bố các lần thực thi theo chế độ, hữu ích hơn việc chỉ nhìn một kết quả gần nhất. `LAST_TEMPSEG_SIZE` có thể là `NULL` nếu không có dữ liệu tạm phù hợp cho operation/lần chạy đó. Khả năng giữ thống kê và quyền đọc phụ thuộc cấu hình, phiên bản và tuổi thọ của cursor trong shared pool.

### 9.5 Xem work area đang hoạt động

Khi muốn tìm thao tác nào đang chiếm bộ nhớ/TEMP ở thời điểm quan sát:

~~~sql
SELECT sid,
       sql_id,
       operation_type,
       ROUND(actual_mem_used / 1024 / 1024, 1) AS actual_mb,
       ROUND(max_mem_used / 1024 / 1024, 1) AS max_mb,
       ROUND(tempseg_size / 1024 / 1024, 1) AS temp_mb,
       number_passes
FROM v$sql_workarea_active
ORDER BY actual_mem_used DESC;
~~~

View này là **ảnh chụp tức thời** của các work area đang hoạt động, nên một truy vấn rất ngắn có thể kết thúc trước lúc lấy mẫu. Không thấy dòng nào không chứng minh rằng trong cả giờ trước không có sort/hash spill.

### 9.6 Quan sát phân đoạn TEMP

TEMP được dùng cho nhiều nhu cầu, trong đó có sort/hash spill. Có thể xem các session đang giữ temporary segments:

~~~sql
SELECT username,
       sql_id,
       tablespace,
       segtype,
       blocks
FROM v$tempseg_usage
ORDER BY blocks DESC;
~~~

`BLOCKS` là số block, không mặc nhiên là số byte hay số MB. Khi quy đổi cần biết kích thước block của tablespace tương ứng; không được nhân cứng với 8 KiB nếu cấu hình chưa xác nhận. Ngoài sort/hash còn có những lý do khác làm TEMP tăng, nên cần kết hợp `SQL_ID`, operation type và plan trước khi quy lỗi cho `ORDER BY`.

## 10. Đọc execution plan để tìm sort, hash và memory/TEMP

Execution plan trả lời **Oracle đã chọn những thao tác vật lý nào** để chạy SQL. Ví dụ:

~~~text
Id  Operation
--  ----------------------------
 0  SELECT STATEMENT
 1   SORT ORDER BY
 2    HASH GROUP BY
 3     HASH JOIN
 4      TABLE ACCESS FULL SALES
 5      TABLE ACCESS FULL CUSTOMERS
~~~

Nếu thấy `SORT ORDER BY`, câu SQL có bước sắp xếp. Nếu thấy `HASH JOIN`, SQL có bước join bằng bảng băm. Tuy nhiên **chỉ nhìn tên operation chưa chứng minh nó đã tràn TEMP** hoặc dùng bao nhiêu PGA.

### 10.1 EXPLAIN PLAN và actual execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT customer_id, SUM(total_amount) AS total_amount
FROM orders
GROUP BY customer_id
ORDER BY total_amount DESC;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` mô tả một plan ước lượng theo ngữ cảnh giải thích, không phải bằng chứng toàn bộ các operation đã thực thi hoặc đã cấp bao nhiêu PGA. Nó có thể khác với plan của câu SQL thực tế, nhất là khi điều kiện bind và số liệu thống kê khác.

Muốn quan sát actual runtime statistics, có thể thu thập cho một truy vấn thực hành:

~~~sql
SELECT /*+ gather_plan_statistics */
       customer_id,
       SUM(total_amount) AS total_amount
FROM orders
GROUP BY customer_id
ORDER BY total_amount DESC;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(NULL, NULL, 'ALLSTATS LAST +MEMSTATS')
);
~~~

Tùy phiên bản và quyền xem cursor, kết quả có thể chứa thông tin ước lượng/thực tế theo operation và các cột memory/TEMP như `OMem`, `1Mem`, `Used-Mem`, `Used-Tmp`. Việc xuất các cột này phụ thuộc plan, hoạt động thống kê và tính năng được hỗ trợ. Nếu truy vấn cần fetch hết kết quả để hoàn tất operation, việc chỉ lấy vài dòng đầu có thể làm số liệu runtime chưa phản ánh toàn bộ lần chạy.

`DBMS_XPLAN.DISPLAY_CURSOR` có thể cần quyền đọc các dynamic performance views liên quan. Nếu câu lệnh “last cursor” không trỏ đến truy vấn cần xem, hãy xác định đúng `SQL_ID` và child cursor qua công cụ giám sát rồi truyền hai giá trị đó cho `DISPLAY_CURSOR`.

### 10.2 Đọc số hàng ước lượng và thực tế

Khi có thống kê thực thi, so sánh số hàng được optimizer dự đoán với số hàng thực tế ở từng nhánh plan:

- Ước lượng số hàng phía build của hash join quá thấp có thể dẫn tới lựa chọn thuật toán kém phù hợp.
- Filter không đủ chọn lọc khiến số hàng đi vào sort lớn hơn dự kiến.
- Nhiều phép nối trước `GROUP BY` có thể nhân số hàng trung gian trước khi tổng hợp.
- Một nhóm khóa có độ phân bố lệch có thể ảnh hưởng hiệu quả join/aggregation.

Nên điều tra thống kê bảng/cột, predicate, index và bản chất dữ liệu trước khi cố tăng bộ nhớ.

## 11. Thực hành trên schema Oracle riêng

Phần này dùng **dữ liệu giả lập** để quan sát các operation mà optimizer có thể chọn. Chỉ chạy DDL trong schema thực hành được cấp quyền; không chạy trên schema nghiệp vụ đang có dữ liệu thật. Các lệnh tạo bảng có implicit commit, vì vậy `ROLLBACK` không dùng để hủy một bảng đã `CREATE TABLE` thành công.

### 11.1 Tạo hai bảng mẫu

~~~sql
CREATE TABLE pga_lab_customers AS
SELECT LEVEL AS customer_id,
       CASE MOD(LEVEL, 4)
           WHEN 0 THEN 'RETAIL'
           WHEN 1 THEN 'SMB'
           WHEN 2 THEN 'ENTERPRISE'
           ELSE 'PARTNER'
       END AS segment
FROM dual
CONNECT BY LEVEL <= 1000;

CREATE TABLE pga_lab_sales AS
SELECT LEVEL AS sale_id,
       MOD(LEVEL - 1, 1000) + 1 AS customer_id,
       DATE '2026-01-01' + MOD(LEVEL, 300) AS sold_on,
       ROUND(MOD(LEVEL * 37, 10000) / 100, 2) AS amount,
       RPAD('X', 120, 'X') AS note
FROM dual
CONNECT BY LEVEL <= 100000;
~~~

Bảng `PGA_LAB_CUSTOMERS` có 1.000 hàng; `PGA_LAB_SALES` có 100.000 hàng, mỗi hàng có dữ liệu mô phỏng doanh số. Số lượng này chỉ mang tính minh họa; trên cấu hình có nhiều RAM, cả hai truy vấn có thể hoàn tất không cần TEMP.

Nếu schema cho phép, có thể thu thập thống kê để optimizer có số liệu:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(USER, 'PGA_LAB_CUSTOMERS');
    DBMS_STATS.GATHER_TABLE_STATS(USER, 'PGA_LAB_SALES');
END;
/
~~~

Việc tạo dữ liệu, thu thập thống kê và chạy câu SQL lớn phải tuân thủ quota/giới hạn tài nguyên của môi trường học. Không cố tình đặt `PGA_AGGREGATE_TARGET` cực thấp hoặc làm đầy TEMP để “kích hoạt lỗi” trên một database dùng chung.

### 11.2 Truy vấn có thể cần SORT ORDER BY

~~~sql
SELECT /*+ gather_plan_statistics */
       sale_id,
       amount,
       note
FROM pga_lab_sales
ORDER BY amount DESC, sale_id;
~~~

Khi không có đường truy cập đã tạo thứ tự yêu cầu, plan có thể hiển thị `SORT ORDER BY`. Bản thân ví dụ trả về nhiều hàng, nên chỉ chạy khi chấp nhận lượng output và tài nguyên tương ứng. Một ứng dụng thường chỉ cần top-N hoặc phân trang, cần thiết kế lại truy vấn thay vì tải mọi hàng ra UI.

Sau khi chạy và fetch đủ dữ liệu, dùng `DBMS_XPLAN.DISPLAY_CURSOR` theo hướng dẫn ở phần 10 để xem actual plan/memory nếu có quyền.

Nếu chỉ muốn xem số lượng ít:

~~~sql
SELECT sale_id, amount
FROM pga_lab_sales
ORDER BY amount DESC, sale_id
FETCH FIRST 20 ROWS ONLY;
~~~

Optimizer có thể sử dụng top-N optimization. Hai truy vấn **không có cùng yêu cầu vật lý**, do đó không nên lấy memory stats của câu top-N rồi kết luận chi phí sort cho việc trả toàn bộ 100.000 hàng.

### 11.3 Truy vấn có thể dùng HASH JOIN và HASH GROUP BY

~~~sql
SELECT /*+ gather_plan_statistics */
       c.segment,
       COUNT(*) AS sale_count,
       SUM(s.amount) AS total_amount
FROM pga_lab_sales s
JOIN pga_lab_customers c
  ON c.customer_id = s.customer_id
GROUP BY c.segment
ORDER BY total_amount DESC;
~~~

Quan sát plan thực tế. Có thể thấy `HASH JOIN`, `HASH GROUP BY`, `SORT ORDER BY`, hoặc một phương án tương đương khác. Điều này phụ thuộc phiên bản, optimizer, thống kê và môi trường; không coi việc thiếu một operator là SQL sai.

Nếu có quyền trên `V$SQL_WORKAREA`, tìm đúng `SQL_ID` của câu trên rồi đọc cột `OPERATION_TYPE`, `LAST_EXECUTION` và các bộ đếm optimal/one-pass/multi-pass. Đó là cách gắn khái niệm work area với operation đã chạy.

### 11.4 Các quan sát cần ghi lại

| Câu hỏi quan sát | Nơi xem | Cách kết luận phù hợp |
|---|---|---|
| SQL dùng sort hay hash? | Actual execution plan | Xác định operation cụ thể, không suy từ cú pháp SQL |
| Có TEMP cho operation không? | Memory stats, `V$SQL_WORKAREA`, `V$SQL_WORKAREA_ACTIVE` | Đọc lượng TEMP và chế độ thực thi nếu số liệu có sẵn |
| Tại thời điểm chạy, instance dùng PGA bao nhiêu? | `V$PGASTAT` | Đọc snapshot hoặc so sánh chuỗi mẫu, phân biệt allocated và inuse |
| Có áp lực TEMP toàn database? | `V$TEMPSEG_USAGE`, số liệu storage của DBA | Gắn tiêu thụ TEMP với session/SQL/operator phù hợp |
| Có nghẽn khi nhiều người chạy không? | Thời gian SQL, CPU, I/O, hoạt động PGA/TEMP | So sánh khi chạy một mình và khi có concurrency |

Sau bài thực hành, nếu cần dọn bảng thì thực hiện theo quy trình quản lý schema thực hành và xác nhận không còn ai sử dụng. Không chép lệnh xóa dữ liệu nguy hiểm vào script production chỉ để dọn lab.

## 12. Tối ưu sort/hash tiêu tốn PGA hoặc TEMP

Khi thấy một truy vấn có `SORT ORDER BY` hay `HASH JOIN` dùng TEMP rất lớn, thứ tự suy luận nên xuất phát từ **dữ liệu và yêu cầu thực sự của SQL**.

### 12.1 Giảm dữ liệu phải đi vào work area

Ví dụ truy vấn sắp xếp tất cả đơn hàng:

~~~sql
SELECT order_id, customer_id, total_amount
FROM orders
ORDER BY created_at DESC;
~~~

Nếu người dùng chỉ cần đơn của một khách hàng trong 30 ngày và 20 dòng mới nhất, có thể diễn đạt đúng nhu cầu:

~~~sql
SELECT order_id, customer_id, total_amount
FROM orders
WHERE customer_id = :p_customer_id
  AND created_at >= :p_from_date
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Lợi ích có thể đến từ filter sớm, ít hàng hơn, phương án top-N và index phù hợp. Việc sửa yêu cầu truy vấn thường tốt hơn cố tìm đủ RAM để sort toàn bộ bảng.

### 12.2 Chọn đường truy cập và thuật toán phù hợp

- **Index phục vụ lọc và thứ tự:** có thể tránh hoặc giảm sort, đặc biệt với giao dịch lấy vài dòng. Nhưng index có chi phí DML và không hợp lý cho mọi báo cáo quét lớn.
- **Kiểm tra điều kiện join:** tránh join không đủ điều kiện hoặc làm số hàng tăng ngoài mong muốn, gây phình hash table và dữ liệu cho bước sort sau.
- **Thống kê optimizer:** thông tin cardinality và phân bố dữ liệu giúp chọn thứ tự join và phương pháp truy cập phù hợp.
- **Giảm độ rộng tập trung gian:** chỉ mang cột cần thiết qua các bước, khi ngữ nghĩa truy vấn cho phép.
- **Phân vùng hoặc tổng hợp trước:** với dữ liệu lịch sử lớn, partition pruning hoặc materialized view/mô hình phân tích có thể giảm hàng phải xử lý.

Không nên buộc optimizer dùng nested loops, hash join hoặc index trên mọi câu truy vấn bằng hint chỉ vì một plan đơn lẻ trông chậm. Phải so sánh khi dữ liệu, bind và mức đồng thời tương tự production.

### 12.3 Phân biệt ba hướng xử lý

| Dấu hiệu | Khả năng nguyên nhân | Hướng kiểm tra đầu tiên |
|---|---|---|
| Sort trên tập kết quả quá lớn | Truy vấn thiếu filter/phân trang; cần order toàn bộ | Xác nhận nhu cầu, predicate, index, top-N |
| Hash join build input lớn bất thường | Join order/cardinality dự đoán sai, dữ liệu skew | Actual rows, thống kê, filter và cấu trúc join |
| Query nhanh khi một mình nhưng spill khi nhiều người chạy | Cạnh tranh work area/PGA; áp lực toàn instance | Concurrency, `V$PGASTAT`, `V$SQL_WORKAREA`, parallelism |
| TEMP tăng nhanh khi chạy phân tích | Sort/hash spill hoặc operation khác dùng TEMP | `V$TEMPSEG_USAGE`, actual plan và operator |
| PGA allocated lớn nhưng PGA inuse thấp hơn đáng kể | Process giữ vùng cấp phát có thể tái sử dụng | Phân biệt allocated/inuse và chuỗi xu hướng, tránh kết luận rò rỉ chỉ từ một snapshot |
| Có lỗi vượt giới hạn PGA | Mức sử dụng tổng quá cao so với chính sách giới hạn | Process/session tiêu thụ nhiều, cấu hình target/limit, truy vấn nặng |

### 12.4 Khi nào điều chỉnh bộ nhớ?

Chỉ cân nhắc tăng ngân sách PGA khi đã có bằng chứng cho thấy:

1. Nhiều operation hợp lý về nghiệp vụ liên tục chạy one-pass/multi-pass.
2. CPU/I/O và đặc biệt TEMP cho thấy chi phí trung gian đáng kể.
3. Máy chủ còn bộ nhớ vật lý phù hợp sau khi tính SGA, hệ điều hành và các process khác.
4. Thay đổi không làm xấu ổn định của tải đồng thời hoặc các ứng dụng cùng dùng instance.

Tăng `PGA_AGGREGATE_TARGET` có thể giảm spill trong một số hệ thống, nhưng **không đảm bảo mỗi query sẽ nhận đủ memory**; mức đồng thời, giới hạn và thuật toán vẫn chi phối kết quả. Mặt khác, tăng quá mức so với RAM thật có thể đẩy máy chủ vào swapping/paging hoặc cạnh tranh bộ nhớ với SGA/OS, khiến toàn hệ thống chậm hơn.

Thay đổi các tham số instance/PDB là công việc có tác động vận hành, cần DBA đánh giá và thực hiện theo quy trình. Bài học này chỉ sử dụng các câu SQL đọc/quan sát cấu hình, không đưa ra lệnh `ALTER SYSTEM` áp dụng mù quáng.

## 13. Phân biệt PGA/TEMP với các lỗi và hiện tượng khác

### ORA-01652: không thể mở rộng temporary segment

Lỗi có thể xảy ra khi operation cần thêm không gian tạm mà tablespace tương ứng không cấp được. Nguyên nhân có thể là TEMP thiếu dung lượng, giới hạn tăng file, nhiều session chiếm TEMP hoặc truy vấn tạo dữ liệu trung gian quá lớn. **Không tự kết luận rằng chỉ cần tăng PGA là hết lỗi**: cần biết ai đang dùng TEMP, plan và chính sách lưu trữ.

### ORA-04036: PGA memory used by the instance exceeds PGA_AGGREGATE_LIMIT

Đây là dấu hiệu liên quan đến giới hạn tổng PGA. Cần xem pressure tại thời điểm lỗi, process/session tiêu thụ, các operation SQL, parallelism và chính sách giới hạn. Nó khác tình huống thiếu dung lượng TEMP.

### ORA-04030: out of process memory

Có thể liên quan đến thất bại cấp phát bộ nhớ cho một process; không nên đồng nhất với việc một sort vừa spill xuống TEMP. Điều tra lỗi và thông tin trace/diagnostic trong điều kiện vận hành thực tế.

### ORA-01555: snapshot too old

Đây là lỗi liên quan khả năng cung cấp ảnh đọc nhất quán từ UNDO cho truy vấn, thường gặp trong bối cảnh truy vấn dài và thay đổi dữ liệu đồng thời. Nó **khác** lỗi thiếu PGA hay thiếu TEMP. Một truy vấn có thể kéo dài do sort/hash và gián tiếp làm tăng cửa sổ rủi ro, nhưng không có quan hệ đồng nhất “sort spill = ORA-01555”.

### SQL chậm dù không có spill

Ngay cả operation `OPTIMAL` vẫn có thể chậm do đọc nhiều dữ liệu gốc, dùng CPU lớn, I/O cao, chờ khóa, network/fetch hoặc kế hoạch truy vấn không phù hợp. Tối ưu PGA chỉ là một phần của tuning SQL.

## 14. Các ngộ nhận dễ mắc

**“PGA là cache chung cho mọi SQL, giống buffer cache.”** Không đúng. PGA là bộ nhớ riêng theo process; buffer cache thuộc SGA dùng chung. Work area xử lý dữ liệu trung gian, không thay thế SGA.

**“PGA_AGGREGATE_TARGET = 8 GB thì câu SQL nào cũng có thể dùng 8 GB.”** Không đúng. Đó là mục tiêu tổng hợp cho toàn instance theo cơ chế quản lý, chịu ảnh hưởng của nhiều process và workload đồng thời.

**“Mọi ORDER BY đều ghi TEMP.”** Không đúng. Có thể sort trong PGA, có thể tối ưu top-N, hoặc truy cập dữ liệu theo thứ tự thích hợp mà không cần sort riêng.

**“HASH JOIN luôn nhanh hơn NESTED LOOPS.”** Không đúng. Hash join thường phù hợp với tập dữ liệu lớn theo những điều kiện nhất định; nested loops có thể hiệu quả hơn với tập ngoài nhỏ và index chọn lọc tốt.

**“Có TEMP nghĩa là Oracle không còn RAM.”** Không đúng. Một operation có thể được cấp work area nhỏ trong áp lực đồng thời hoặc theo giới hạn quản lý dù toàn máy còn bộ nhớ; cũng có nhiều lý do dùng TEMP khác nhau.

**“ONE-PASS có nghĩa Oracle quét bảng gốc đúng một lần.”** Không đúng. Phân loại pass mô tả cách xử lý dữ liệu trung gian với bộ nhớ có sẵn, không phải số vòng đọc bảng gốc.

**“Tăng PARALLEL sẽ làm báo cáo nhanh mà không ảnh hưởng OLTP.”** Không đúng. Parallel execution có thể tăng cạnh tranh CPU, PGA, I/O và TEMP với các câu SQL khác.

**“Cứ tăng PGA là truy vấn được tối ưu.”** Không đúng. Nếu SQL đang join dư hàng hoặc sort nhiều dữ liệu không cần thiết thì cấp thêm RAM chỉ làm giảm một phần chi phí của kế hoạch chưa phù hợp.

## 15. Tình huống tổng hợp: báo cáo doanh thu làm API chậm

Giả sử ứng dụng đặt hàng dùng Oracle Database phục vụ hai workload:

- API tạo đơn chạy liên tục, cần độ trễ thấp.
- Một báo cáo doanh thu chạy `JOIN` giữa nhiều bảng lớn, `GROUP BY` theo khách hàng rồi `ORDER BY` theo doanh thu.

Khi báo cáo chạy một mình, thời gian xử lý chấp nhận được. Đến giờ cao điểm, nhiều phiên dashboard cùng chạy và `V$SQL_WORKAREA` cho thấy tỉ lệ one-pass/multi-pass tăng; `V$TEMPSEG_USAGE` ghi nhận nhiều phân đoạn TEMP; độ trễ API cũng tăng, dù không có nhiều row lock wait.

Hướng phân tích:

1. **Xác nhận hoạt động thực tế:** SQL_ID, plan, số hàng qua từng join, loại work area, thời gian thực thi và số liệu TEMP; so sánh thời điểm rảnh và giờ cao điểm.
2. **Kiểm tra ngữ nghĩa báo cáo:** dashboard có cần quét toàn bộ lịch sử và sort mọi khách hàng hay chỉ lấy top 20 của tháng hiện tại?
3. **Đánh giá join và aggregation:** có filter sớm, thống kê phù hợp, dữ liệu bị nhân hàng do join thiếu điều kiện, hoặc số nhóm lớn bất thường?
4. **Đánh giá concurrency và parallelism:** có quá nhiều phiên chạy cùng SQL hoặc DOP làm tăng nhu cầu memory/CPU/TEMP?
5. **Chọn chiến lược:** tối ưu truy vấn và index, giới hạn đồng thời, materialized view/bảng tổng hợp, tách workload phân tích hoặc điều chỉnh PGA nếu có đủ bằng chứng và nguồn lực.
6. **Đo lại cùng tải:** thời gian hoàn tất báo cáo, độ trễ API (đặc biệt p95/p99), PGA allocated/inuse, số pass và lượng I/O TEMP.

Sự cải thiện chỉ có ý nghĩa khi báo cáo **đúng số liệu**, đáp ứng độ mới yêu cầu và API không bị suy giảm vượt ngưỡng chấp nhận. Đạt chế độ optimal cho một phép sort không tự nó chứng minh toàn hệ thống đã được tối ưu.

## 16. Câu hỏi tự luyện

**Câu 1.** Hai truy vấn trả về 100 dòng nhưng truy vấn A đọc 100 dòng từ index, còn truy vấn B quét 5 triệu dòng và lấy top 100 sau khi sort. PGA của chúng có bắt buộc giống nhau không?

*Gợi ý:* Không. Số hàng trả về cho client không phản ánh trực tiếp số hàng và dạng dữ liệu phải đi qua các operator trước đó. B có thể dùng work area lớn hơn, dù có top-N optimization.

**Câu 2.** Một SQL có `HASH JOIN` và `SORT ORDER BY` nhưng `V$SQL_WORKAREA` cho thấy cả hai lần gần nhất đều optimal. Có thể kết luận SQL không hề dùng PGA?

*Gợi ý:* Không. Optimal chính là xử lý operation bằng bộ nhớ phù hợp; không phải “không dùng bộ nhớ”. PGA còn chứa những phần khác ngoài work area.

**Câu 3.** Khi tăng từ một báo cáo lên 30 báo cáo đồng thời, số lần one-pass tăng. Có nên tăng `SORT_AREA_SIZE` ngay?

*Gợi ý:* Hãy kiểm tra `WORKAREA_SIZE_POLICY`, áp lực PGA toàn instance và số process/parallelism. Với AUTO, `SORT_AREA_SIZE` không phải nút điều chỉnh trực tiếp theo cách nghĩ này. Cần giảm tải/điều chỉnh workload và chỉ cân nhắc ngân sách PGA có cơ sở.

**Câu 4.** Vì sao `ORA-01652` và `ORA-04036` không thể xử lý bằng một phương án chung?

*Gợi ý:* Một lỗi liên quan không gian temporary segment; lỗi kia liên quan giới hạn tổng PGA của instance. Chúng có thể cùng xuất hiện trong workload nặng nhưng cần quan sát và biện pháp riêng.

**Câu 5.** Khi xem `EXPLAIN PLAN` thấy `HASH JOIN`, vì sao chưa thể kết luận hash join vừa spill 2 GiB xuống TEMP?

*Gợi ý:* EXPLAIN PLAN là kế hoạch ước lượng; lượng memory/TEMP là số liệu runtime. Cần actual plan, workarea statistics và thông tin sử dụng TEMP liên quan đến lần chạy cụ thể.

## 17. Kết luận

Trong Oracle, **PGA** là bộ nhớ riêng của process, còn **SQL work area** là phần bộ nhớ phục vụ những thao tác như `SORT ORDER BY`, `HASH JOIN` và `HASH GROUP BY`. Một operation có thể hoàn tất trong bộ nhớ (**optimal**) hoặc phải dùng **TEMP** và xử lý qua một/nhiều pass khi bộ nhớ không đủ. Mức dùng PGA và TEMP biến đổi theo kích thước dữ liệu trung gian, execution plan, tài nguyên và workload đồng thời.

Để xử lý một truy vấn sort/hash chậm, hãy xác định đúng operation trong **actual execution plan**, đối chiếu **PGA/workarea statistics và TEMP usage**, rồi tối ưu lượng dữ liệu, join, group by và concurrency. Chỉ điều chỉnh ngân sách PGA sau khi đã hiểu nhu cầu thực tế và khả năng bộ nhớ của môi trường. Cách tiếp cận đó giải quyết nguyên nhân chậm và tránh việc cải thiện một câu SQL bằng cách gây áp lực cho toàn bộ Oracle Database.
