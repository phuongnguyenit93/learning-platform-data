# Đọc cây thực thi, thứ tự xử lý và quan hệ giữa các nhánh

Execution plan của Oracle mô tả cách Optimizer dự định lấy dữ liệu, kết hợp các row source và trả kết quả cho câu SQL. Khi đọc plan, điều quan trọng nhất là hiểu **cấu trúc cây**: mỗi operation là một nút, các operation con cung cấp đầu vào cho operation cha, còn operation cha xử lý hoặc kết hợp các dòng nhận được.

Plan không phải danh sách lệnh được thực hiện lần lượt từ dòng trên xuống dòng dưới. Cột `Id` là mã định danh operation trong plan; thứ tự số không phải thứ tự thời gian. Thụt lề trong output của `DBMS_XPLAN` thể hiện quan hệ cha-con. Khi chạy thực tế, các row source thường hoạt động theo kiểu iterator: operation cha yêu cầu dòng từ operation con khi cần. Vì vậy, một nhánh có thể được đọc nhiều lần, một nhánh có thể chỉ chạy khi nhánh khác tạo ra dữ liệu, và một số operation có thể xử lý theo luồng thay vì đợi toàn bộ dữ liệu được đọc xong.

Muốn đọc đúng execution plan, cần kết hợp ba góc nhìn:

- **Cấu trúc:** operation nào là cha, operation nào là con, một nhánh kết thúc ở đâu và các nhánh hội tụ ở operation nào.
- **Luồng dữ liệu:** mỗi operation lấy dòng từ đâu, lọc hoặc kết hợp chúng như thế nào, rồi chuyển kết quả cho operation nào.
- **Hành vi thực tế:** operation đã khởi chạy bao nhiêu lần, ước lượng bao nhiêu dòng và thực tế tạo ra bao nhiêu dòng.

## 1. Execution plan là một cây row source

Oracle biểu diễn phần lớn execution plan dưới dạng cây. Nút trên nhận đầu vào từ một hoặc nhiều nút con. Nút lá là nơi bắt đầu lấy dữ liệu, ví dụ đọc bảng hoặc index. Các nút ở phía trên có thể lọc, sắp xếp, join hoặc hợp nhất dữ liệu trước khi trả kết quả.

Ví dụ rút gọn:

```text
SELECT STATEMENT
  NESTED LOOPS
    TABLE ACCESS BY INDEX ROWID ORDERS
      INDEX RANGE SCAN ORDERS_STATUS_IX
    TABLE ACCESS BY INDEX ROWID CUSTOMERS
      INDEX UNIQUE SCAN CUSTOMERS_PK
```

Có thể đọc quan hệ giữa các nút như sau:

1. `INDEX RANGE SCAN ORDERS_STATUS_IX` lấy các key và rowid của đơn hàng phù hợp.
2. `TABLE ACCESS BY INDEX ROWID ORDERS` dùng rowid để lấy các dòng đơn hàng từ bảng.
3. `NESTED LOOPS` nhận dòng đơn hàng và dùng giá trị liên quan để tra cứu khách hàng ở nhánh còn lại.
4. `INDEX UNIQUE SCAN CUSTOMERS_PK` tìm dòng khách hàng theo khóa duy nhất.
5. `TABLE ACCESS BY INDEX ROWID CUSTOMERS` lấy dữ liệu khách hàng tương ứng.
6. `NESTED LOOPS` kết hợp các dòng từ hai nhánh và chuyển kết quả lên operation cha.

Đây là cách minh họa một nested loops join thường gặp. Plan thực tế có thể có thêm filter, projection, view, partition iterator hoặc các operation khác.

### 1.1. Nút cha và nút con

Trong output dạng cây, nút có mức thụt lề ít hơn thường là nút cha; các dòng thụt vào bên dưới là những nhánh con của nó. Ví dụ:

```text
Id  Operation
--  ----------------------------------
 0  SELECT STATEMENT
  1   HASH JOIN
  2    TABLE ACCESS FULL CUSTOMERS
  3    TABLE ACCESS FULL ORDERS
```

`SELECT STATEMENT` là nút gốc. `HASH JOIN` là đầu vào trực tiếp của nút gốc. Hai `TABLE ACCESS FULL` là hai đầu vào của phép hash join. Không được hiểu rằng operation có `Id = 2` luôn chạy trước operation có `Id = 3` chỉ vì số nhỏ hơn; cần xem loại join và cách operation tiêu thụ dữ liệu.

Một cây khác có thể có nhiều tầng:

```text
SELECT STATEMENT
  HASH JOIN
    NESTED LOOPS
      TABLE ACCESS BY INDEX ROWID ORDERS
        INDEX RANGE SCAN ORDERS_DATE_IX
      TABLE ACCESS BY INDEX ROWID CUSTOMERS
        INDEX UNIQUE SCAN CUSTOMERS_PK
    TABLE ACCESS FULL PRODUCTS
```

Ở đây, `HASH JOIN` có hai nhánh con trực tiếp. Nhánh thứ nhất lại là một `NESTED LOOPS` có hai nhánh con riêng. Nhánh thứ hai là một phép đọc toàn bộ `PRODUCTS`. Có thể hiểu cây theo từng tầng:

- Nhánh `ORDERS` và `CUSTOMERS` tạo ra kết quả join bằng nested loops.
- Kết quả đó trở thành một đầu vào của hash join bên ngoài.
- Nhánh `PRODUCTS` là đầu vào còn lại của hash join bên ngoài.
- Hash join tạo kết quả cho nút gốc.

Không nên gộp tất cả các operation thành một chuỗi duy nhất. Việc giữ ranh giới từng nhánh giúp xác định đúng operation nào cung cấp dữ liệu cho operation nào.

### 1.2. `Id` không phải thứ tự thực thi

`Id` nhận diện một dòng operation trong plan. Các ID thường được đánh theo cách duyệt cây, vì vậy có thể tăng dần khi đi sâu vào các nhánh. Chúng hữu ích để liên hệ với `Predicate Information`, `V$SQL_PLAN` và các thông tin runtime.

Không nên diễn giải:

- `Id = 1` chắc chắn chạy trước `Id = 2`.
- `Id` lớn nhất là operation chạy đầu tiên.
- Operation ở cuối output luôn hoàn tất trước tất cả operation khác.
- Cứ đọc từ dưới lên là có thể suy ra toàn bộ trình tự runtime.

Đọc từ các nút lá lên giúp nhận biết nguồn dữ liệu và quan hệ đầu vào. Nhưng thứ tự runtime phụ thuộc loại operation. Nested loops có thể yêu cầu nhánh trong nhiều lần; hash join thường phải xây dựng hash table từ một đầu vào trước khi xử lý đầu vào còn lại; pipeline có thể chuyển dòng ngay khi có dòng sẵn sàng.

### 1.3. Cách xác định quan hệ cha-con trong metadata

Trong các view kế hoạch như `V$SQL_PLAN`, Oracle cung cấp các cột `ID`, `PARENT_ID`, `DEPTH` và `POSITION` để biểu diễn quan hệ trong cây. Có thể truy vấn một cursor cụ thể:

```sql
SELECT id,
       parent_id,
       depth,
       position,
       operation,
       options,
       object_owner,
       object_name
FROM v$sql_plan
WHERE sql_id = :sql_id
  AND child_number = :child_number
ORDER BY id;
```

`PARENT_ID` cho biết nút cha của operation. `DEPTH` thể hiện độ sâu trong cây. `POSITION` biểu diễn vị trí đầu vào của operation trong quan hệ với nút cha. Các cột này hữu ích khi cần phân tích plan bằng SQL hoặc công cụ riêng thay vì chỉ nhìn output đã định dạng.

`V$SQL_PLAN` chứa plan gắn với cursor trong shared pool. User cần quyền đọc dynamic performance views hoặc các view `GV$` tương ứng nếu môi trường RAC. Nếu SQL đã bị loại khỏi shared pool, cursor hoặc child cursor không còn tồn tại, dữ liệu plan có thể không còn truy vấn được theo cách này.

## 2. Hiểu luồng dữ liệu qua operation

Một operation nhận đầu vào, thực hiện công việc và cung cấp dòng cho operation cha. Nhiều operation có thể hoạt động theo cơ chế pull: nút cha yêu cầu nút con trả dòng tiếp theo. Nút con có thể tiếp tục yêu cầu dữ liệu từ nút con của nó.

Ví dụ, khi đọc một bảng qua index:

```text
TABLE ACCESS BY INDEX ROWID ORDERS
  INDEX RANGE SCAN ORDERS_STATUS_IX
```

`INDEX RANGE SCAN` tìm các key phù hợp và tạo rowid. `TABLE ACCESS BY INDEX ROWID` dùng các rowid đó để đọc dòng trong bảng. Dữ liệu từ operation index là đầu vào cho operation table access; operation table access mới trả các cột của dòng bảng cho nút cha.

Khi nhìn thấy operation cha và con, hãy đặt câu hỏi:

1. Operation cha cần loại dữ liệu nào?
2. Nhánh con cung cấp dữ liệu hoặc rowid hay chỉ cung cấp điều kiện?
3. Operation cha có thể xử lý ngay từng dòng hay cần tích lũy toàn bộ một phần dữ liệu?
4. Nhánh con chạy một lần hay có thể bị gọi lặp lại?
5. Dòng được loại bỏ ở operation nào và dòng được chuyển tiếp ở operation nào?

Những câu hỏi này giúp giải thích vì sao một nhánh có thể tốn nhiều tài nguyên dù số dòng cuối cùng trả về rất ít.

### 2.1. Các operation đọc dữ liệu thường gặp

| Operation | Vai trò trong luồng dữ liệu |
|---|---|
| `TABLE ACCESS FULL` | Đọc các block của bảng theo đường full scan và cung cấp dòng thỏa điều kiện cho nút cha |
| `INDEX UNIQUE SCAN` | Tìm key duy nhất, thường trả tối đa một rowid cho mỗi lần tìm |
| `INDEX RANGE SCAN` | Tìm một khoảng key và trả các key/rowid phù hợp |
| `INDEX FULL SCAN` | Đọc toàn bộ index theo thứ tự key, thường có thể cung cấp thứ tự cho nút cha |
| `INDEX FAST FULL SCAN` | Đọc toàn bộ block của index theo cách thiên về scan, không bảo đảm thứ tự key như index full scan |
| `TABLE ACCESS BY INDEX ROWID` | Dùng rowid do index cung cấp để lấy dòng trong bảng |
| `TABLE ACCESS BY INDEX ROWID BATCHED` | Gom một nhóm rowid để cải thiện cách truy cập table block |
| `TABLE ACCESS SAMPLE` | Đọc mẫu dữ liệu theo cơ chế sampling khi truy vấn yêu cầu |
| `EXTERNAL TABLE ACCESS` | Đọc dữ liệu từ external table theo cấu hình của object |

Một nhánh index scan thường không phải kết quả cuối cùng. Nó có thể chỉ cung cấp rowid cho table access. Khi thấy `INDEX RANGE SCAN`, cần nhìn operation cha để biết rowid được sử dụng ra sao và liệu có phải đọc thêm bảng hay không.

### 2.2. Operation lọc, sắp xếp và biến đổi

| Operation | Vai trò |
|---|---|
| `FILTER` | Kiểm tra điều kiện trên dòng nhận được và chỉ chuyển dòng thỏa điều kiện |
| `SORT ORDER BY` | Sắp xếp dòng theo thứ tự yêu cầu của câu SQL |
| `SORT GROUP BY` | Sắp xếp hoặc gom nhóm dữ liệu cho phép tổng hợp |
| `HASH GROUP BY` | Gom nhóm bằng cấu trúc hash |
| `SORT UNIQUE` | Loại dòng trùng dựa trên thao tác sort |
| `HASH UNIQUE` | Loại dòng trùng bằng cấu trúc hash |
| `VIEW` | Đại diện cho một query block/view được sử dụng trong plan |
| `WINDOW SORT` | Chuẩn bị thứ tự dữ liệu cho analytic/window function |
| `COUNT STOPKEY` | Dừng đọc khi đã đạt giới hạn dòng cần thiết trong một số dạng truy vấn |
| `UNION-ALL` | Nhận dữ liệu từ nhiều nhánh và nối kết quả của các nhánh |
| `CONCATENATION` | Hợp nhất các nhánh được tạo bởi một số phép biến đổi truy vấn |

Một operation có thể không tạo ra nhiều dòng hơn đầu vào. Filter thường làm giảm số dòng; sort thường giữ nguyên số dòng nhưng thay đổi thứ tự; group by thường giảm số dòng; union all có thể cộng số dòng của nhiều nhánh.

### 2.3. Operation cha có thể là nơi tiêu thụ dữ liệu

Giả sử plan có dạng:

```text
SORT ORDER BY
  FILTER
    TABLE ACCESS FULL ORDERS
```

Luồng dữ liệu đi từ `TABLE ACCESS FULL` lên `FILTER`, sau đó đến `SORT ORDER BY`. Filter kiểm tra điều kiện và chỉ chuyển các dòng phù hợp. Sort nhận tập dòng đã lọc và sắp xếp chúng.

Không có nghĩa Oracle nhất thiết phải đọc toàn bộ bảng, ghi toàn bộ kết quả trung gian ra đĩa, rồi mới bắt đầu sort. Tùy operation và lượng dữ liệu, Oracle có thể dùng bộ nhớ, temporary segment hoặc xử lý theo luồng. Nếu sort vượt vùng nhớ được cấp, operation có thể spill ra TEMP; cần xem runtime statistics và các dấu hiệu workarea để đánh giá.

## 3. Thứ tự xử lý của các phép JOIN

Join là nơi quan hệ giữa các nhánh trở nên đặc biệt quan trọng. Một join operation có ít nhất hai nhánh đầu vào. Optimizer quyết định bảng hoặc row source nào tham gia trước, cách kết hợp chúng và thứ tự các phép join trong cây.

Cần phân biệt:

- **Join order:** thứ tự các row source được kết hợp với nhau.
- **Join method:** cách kết hợp hai đầu vào, ví dụ nested loops, hash join hoặc sort merge join.
- **Access path:** cách lấy dữ liệu từ từng row source, ví dụ full scan hoặc index scan.

Ba quyết định này liên quan nhưng không phải một. Cùng một join order có thể dùng join method khác nhau; cùng một join method có thể lấy đầu vào bằng full scan hoặc index scan.

### 3.1. Nested loops: nhánh ngoài điều khiển số lần chạy nhánh trong

Nested loops phù hợp khi nhánh ngoài trả về số dòng tương đối nhỏ và nhánh trong có cách tìm dòng hiệu quả, thường qua index.

Ví dụ:

```text
NESTED LOOPS
  TABLE ACCESS BY INDEX ROWID ORDERS
    INDEX RANGE SCAN ORDERS_STATUS_IX
  TABLE ACCESS BY INDEX ROWID CUSTOMERS
    INDEX UNIQUE SCAN CUSTOMERS_PK
```

Có thể hình dung cách xử lý:

1. Oracle lấy một dòng từ nhánh ngoài `ORDERS`.
2. Dựa vào `CUSTOMER_ID` của dòng đó, Oracle tìm dòng tương ứng ở nhánh trong `CUSTOMERS`.
3. Hai dòng được kết hợp và chuyển lên operation cha.
4. Oracle lấy dòng tiếp theo từ nhánh ngoài.
5. Quá trình tra cứu nhánh trong tiếp tục lặp lại cho mỗi dòng ngoài cần xử lý.

Nếu nhánh ngoài trả 100 dòng, nhánh trong có thể được khởi chạy khoảng 100 lần. Nếu nhánh ngoài trả 500.000 dòng, cùng một phép tra cứu ở nhánh trong có thể bị lặp lại rất nhiều lần và trở nên tốn kém.

Với nested loops, nhánh con đầu tiên trong cây thường là **outer row source**, còn nhánh con tiếp theo là **inner row source**. Inner row source được gọi theo từng dòng hoặc từng nhóm dòng từ outer row source, tùy cách thực thi và các tối ưu hóa của Oracle.

Khi đọc actual plan, `Starts` của nhánh trong là dấu hiệu quan trọng. Nếu `Starts` rất lớn, hãy kiểm tra số dòng từ nhánh ngoài, chi phí mỗi lần tra cứu và khả năng index lookup. Không nên chỉ nhìn cost tổng thể của operation nested loops.

### 3.2. Hash join: xây dựng hash table rồi dò đầu vào còn lại

Hash join thường phù hợp khi kết hợp tập dữ liệu lớn và điều kiện join là equality predicate. Oracle xây dựng cấu trúc hash từ một đầu vào, sau đó đọc đầu vào còn lại và dò hash table để tìm dòng khớp.

Ví dụ:

```text
HASH JOIN
  TABLE ACCESS FULL CUSTOMERS
  TABLE ACCESS FULL ORDERS
```

Ở dạng hash join điển hình:

1. Oracle đọc đầu vào build và tạo hash table theo join key.
2. Oracle đọc đầu vào probe.
3. Với mỗi dòng probe, Oracle tính hash của join key và tìm các dòng khớp trong hash table.
4. Các dòng khớp được kết hợp và chuyển cho operation cha.

Optimizer thường cân nhắc đầu vào nhỏ hơn làm build input để giảm bộ nhớ, nhưng quyết định thực tế còn phụ thuộc ước lượng, điều kiện join, parallel execution và các yếu tố khác. Khi đọc cây, hãy xác định hai nhánh trực tiếp của `HASH JOIN`; nhánh build/probe được thể hiện theo thứ tự input trong plan. Không nên suy ra nhánh build chỉ từ tên bảng hoặc thứ tự xuất hiện trong câu `FROM`.

Hash join có thể dùng bộ nhớ workarea. Nếu không đủ bộ nhớ, operation có thể chuyển sang xử lý nhiều partition và dùng TEMP. Khi một hash join lớn chạy chậm, cần kiểm tra actual rows, kích thước đầu vào, workarea, TEMP usage và mức độ song song, thay vì chỉ kết luận rằng full scan là xấu.

### 3.3. Sort merge join: kết hợp hai luồng đã được sắp xếp

Sort merge join kết hợp hai đầu vào theo thứ tự join key. Nếu đầu vào chưa được sắp xếp phù hợp, plan có thể chứa operation sort ở một hoặc cả hai nhánh.

```text
MERGE JOIN
  SORT JOIN
    TABLE ACCESS FULL CUSTOMERS
  SORT JOIN
    TABLE ACCESS FULL ORDERS
```

Về ý tưởng:

1. Hai đầu vào được sắp xếp theo join key nếu cần.
2. Oracle đọc hai luồng theo thứ tự key.
3. Các key bằng nhau được kết hợp; khi key thay đổi, luồng tương ứng được tiến lên.
4. Kết quả được chuyển lên operation cha.

Nếu đầu vào đã có thứ tự phù hợp từ index hoặc operation trước đó, Oracle có thể tránh một số bước sort. Ngược lại, sort lớn có thể tốn CPU, bộ nhớ và TEMP.

### 3.4. So sánh ba join method

| Join method | Cách xử lý | Thường phù hợp khi | Dấu hiệu cần xem |
|---|---|---|---|
| Nested loops | Lấy dòng outer rồi tra cứu inner lặp lại | Outer nhỏ, inner lookup có chọn lọc và hiệu quả | `Starts` của inner, số dòng outer, logical reads |
| Hash join | Build hash table từ một đầu vào, probe bằng đầu vào kia | Tập dữ liệu lớn, equality join, scan có thể hiệu quả | Build/probe input, memory, TEMP, actual rows |
| Sort merge join | Sắp xếp hai luồng rồi merge theo key | Hai đầu vào có thứ tự hoặc cần xử lý theo thứ tự | Sort operations, TEMP, thứ tự đầu vào |

Không có join method nào luôn tốt nhất. Một nested loops join với vài dòng và index lookup tốt có thể rất nhanh. Một nested loops join với hàng triệu lần khởi chạy nhánh trong có thể rất chậm. Hash join có thể hiệu quả cho dữ liệu lớn nhưng tốn TEMP nếu workarea thiếu. Sort merge join có thể phù hợp khi dữ liệu đã có thứ tự, nhưng sort mới có thể làm tăng chi phí.

### 3.5. Join order với ba bảng trở lên

Giả sử câu SQL kết hợp `CUSTOMERS`, `ORDERS` và `ORDER_ITEMS`. Optimizer có thể chọn:

```text
          HASH JOIN
          /       \
     JOIN A        ORDER_ITEMS
      /  \
 CUSTOMERS ORDERS
```

Hoặc:

```text
          HASH JOIN
          /       \
   JOIN B          CUSTOMERS
    /  \
 ORDERS ORDER_ITEMS
```

Hai cây có ý nghĩa khác nhau. Ở cây thứ nhất, `CUSTOMERS` và `ORDERS` được kết hợp trước, sau đó kết quả mới join với `ORDER_ITEMS`. Ở cây thứ hai, `ORDERS` và `ORDER_ITEMS` được kết hợp trước rồi mới join với `CUSTOMERS`.

Join order ảnh hưởng đến kích thước tập trung gian. Nếu một điều kiện lọc làm giảm mạnh số dòng của `ORDERS`, kết hợp `ORDERS` với `ORDER_ITEMS` sớm có thể tạo một tập nhỏ hơn cho các bước sau. Nhưng nếu một nhánh có độ chọn lọc thấp hoặc số liệu ước lượng sai, thứ tự được chọn có thể không phù hợp.

Đừng đọc join order từ thứ tự bảng trong `FROM`. Optimizer có thể reorder các phép join trong phạm vi ngữ nghĩa cho phép, dựa trên cost và các ràng buộc của truy vấn.

## 4. Predicate được gắn vào operation nào?

Execution plan thường có phần `Predicate Information`. Phần này gắn điều kiện lọc hoặc điều kiện truy cập với `Id` của operation. Đây là cầu nối giữa câu SQL và từng nút trong cây.

Hai loại predicate thường gặp là:

- **Access predicate:** điều kiện được dùng để xác định vùng dữ liệu hoặc key cần truy cập, ví dụ xác định khoảng key trong index.
- **Filter predicate:** điều kiện được dùng để kiểm tra dòng sau khi operation đã lấy được dòng hoặc ứng viên dòng.

Ví dụ:

```sql
SELECT o.order_id,
       o.order_date,
       c.customer_name
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id
WHERE o.order_status = 'PENDING'
  AND o.order_date >= DATE '2026-01-01';
```

Giả sử plan rút gọn:

```text
Id  Operation                                      Name
--  ---------------------------------------------  -------------------
 0  SELECT STATEMENT
  1   NESTED LOOPS
  2    TABLE ACCESS BY INDEX ROWID BATCHED         ORDERS
  3     INDEX RANGE SCAN                           ORDERS_STATUS_IX
  4    TABLE ACCESS BY INDEX ROWID                 CUSTOMERS
  5     INDEX UNIQUE SCAN                          CUSTOMERS_PK
```

Phần predicate có thể hiển thị theo dạng:

```text
Predicate Information (identified by operation id):
---------------------------------------------------
  3 - access("O"."ORDER_STATUS"='PENDING')
  2 - filter("O"."ORDER_DATE">=DATE '2026-01-01')
  5 - access("C"."CUSTOMER_ID"="O"."CUSTOMER_ID")
```

Diễn giải:

- Operation 3 dùng `ORDER_STATUS` để tìm key trong index.
- Operation 2 kiểm tra `ORDER_DATE` trên dòng đơn hàng lấy được từ bảng.
- Operation 5 dùng `CUSTOMER_ID` để tìm khách hàng trong primary-key index.
- Operation 1 kết hợp các dòng từ nhánh đơn hàng và khách hàng.

Ví dụ này cho thấy một điều kiện trong `WHERE` có thể được xử lý ở operation index, còn điều kiện khác được áp dụng sau khi đọc bảng. Việc predicate nằm ở operation nào ảnh hưởng số rowid cần đọc, số table block cần truy cập và số dòng chuyển lên join.

### 4.1. Predicate không nhất thiết nằm nguyên tại nơi viết trong SQL

Optimizer có thể đẩy predicate xuống sâu hơn trong cây (*predicate pushdown*) để giảm dữ liệu trung gian. Một điều kiện ở query block bên ngoài có thể được đẩy vào view hoặc subquery nếu phép biến đổi đó bảo toàn ngữ nghĩa.

Ví dụ, truy vấn lọc một view có thể được biến đổi để điều kiện lọc thực hiện trực tiếp trên bảng nền. Khi đó plan có thể không còn thể hiện một bước `VIEW` tách biệt như người đọc mong đợi từ câu SQL ban đầu.

Ngược lại, có những điều kiện cần được áp dụng sau join hoặc sau phép tổng hợp để giữ đúng ngữ nghĩa. Không thể kết luận predicate bị đặt sai chỉ vì nó không nằm đúng vị trí tương ứng với thứ tự văn bản trong SQL.

### 4.2. Phân biệt điều kiện join và điều kiện filter

Điều kiện join thường so sánh các cột từ hai row source, ví dụ:

```sql
o.customer_id = c.customer_id
```

Điều kiện filter thường giới hạn dòng theo một giá trị hoặc khoảng giá trị:

```sql
o.order_status = 'PENDING'
o.order_date >= DATE '2026-01-01'
```

Trong `Predicate Information`, điều kiện join có thể xuất hiện dưới `access()` hoặc `filter()` tùy operation và join method. Không nên suy luận rằng mọi `access()` đều là predicate của index, hoặc mọi điều kiện join đều xuất hiện ở một operation join duy nhất. Hãy đọc cùng loại operation, alias, nhánh con và predicate cụ thể.

### 4.3. Partition pruning trong cây thực thi

Với partitioned table, plan có thể có các operation như `PARTITION RANGE ITERATOR`, `PARTITION RANGE SINGLE`, `PARTITION RANGE ALL` hoặc operation tương ứng với loại partition. Các cột `PSTART` và `PSTOP` cho biết phạm vi partition được truy cập theo cách hiển thị của plan.

Ví dụ rút gọn:

```text
PARTITION RANGE SINGLE
  TABLE ACCESS FULL SALES
```

Operation partition iterator xác định partition cần đọc; operation table access đọc dữ liệu trong partition tương ứng. Nếu plan thể hiện `PARTITION RANGE ALL`, có thể nhiều partition đang được xét. Cần kiểm tra predicate trên partition key và giá trị `PSTART`/`PSTOP` để hiểu pruning có diễn ra như mong đợi hay không.

Với dynamic pruning, phạm vi partition có thể được xác định khi chạy thay vì hoàn toàn cố định lúc parse. Một số plan hiển thị giá trị như `KEY` trong `PSTART`/`PSTOP`. Điều đó không tự động có nghĩa pruning thất bại; cần xem runtime và điều kiện bind thực tế.

## 5. Nhánh của subquery, view và query transformation

SQL có thể chứa nhiều query block: subquery trong `WHERE`, inline view trong `FROM`, CTE (`WITH`), scalar subquery và các nhánh của set operator. Optimizer có thể giữ các query block riêng hoặc biến đổi chúng để tạo plan.

### 5.1. Inline view và operation VIEW

Ví dụ:

```sql
SELECT x.customer_id,
       x.order_count
FROM (
    SELECT customer_id,
           COUNT(*) AS order_count
    FROM orders
    GROUP BY customer_id
) x
WHERE x.order_count > 5;
```

Plan có thể có operation `VIEW`, `HASH GROUP BY` hoặc các operation khác tương ứng với query block bên trong. Nhưng optimizer cũng có thể merge view hoặc biến đổi query block để thực hiện lọc và tổng hợp hiệu quả hơn. Vì vậy, không phải cứ có dấu ngoặc trong SQL thì plan nhất thiết có một nút `VIEW` riêng.

`VIEW` là một row source trong plan, không phải bằng chứng rằng Oracle đã tạo một bảng tạm vật lý. Nếu cần materialize dữ liệu, plan có thể thể hiện các operation liên quan đến temporary table hoặc cơ chế khác. Cần đọc operation thực tế.

### 5.2. Subquery trong điều kiện EXISTS hoặc IN

Ví dụ:

```sql
SELECT c.customer_id
FROM customers c
WHERE EXISTS (
    SELECT 1
    FROM orders o
    WHERE o.customer_id = c.customer_id
);
```

Optimizer có thể biến đổi correlated subquery thành semi join. Plan có thể thể hiện `NESTED LOOPS SEMI`, `HASH JOIN SEMI` hoặc operation tương ứng. Khi đó, subquery không nhất thiết chạy như một truy vấn độc lập hoàn chỉnh cho từng dòng customer; nó có thể trở thành một nhánh join trong cây.

Với `NOT EXISTS` hoặc một số dạng `NOT IN`, Oracle có thể dùng anti join, ví dụ `HASH JOIN ANTI` hoặc `NESTED LOOPS ANTI`, nếu phép biến đổi bảo toàn ngữ nghĩa. Cần đặc biệt lưu ý ngữ nghĩa `NULL` của `NOT IN`; không nên thay thế máy móc bằng `NOT EXISTS` nếu chưa xác nhận tương đương.

### 5.3. Scalar subquery

Scalar subquery trả về một giá trị đơn cho mỗi ngữ cảnh sử dụng. Ví dụ:

```sql
SELECT c.customer_id,
       (SELECT MAX(o.order_date)
        FROM orders o
        WHERE o.customer_id = c.customer_id) AS last_order_date
FROM customers c;
```

Plan có thể có operation `SCALAR SUBQUERY` hoặc các operation con được liên kết với query block con. Một scalar subquery tương quan có thể được thực hiện nhiều lần, nhưng Oracle có thể cache hoặc biến đổi tùy trường hợp. Hãy xem `Starts`, actual rows và các query block liên quan để xác định hành vi thực tế.

Nếu nhánh subquery có `Starts` gần bằng số dòng của nhánh ngoài, hãy đánh giá chi phí mỗi lần chạy. Một subquery có thể rất rẻ khi index lookup tốt, nhưng có thể trở thành điểm nghẽn nếu mỗi lần gọi lại quét một lượng dữ liệu lớn.

### 5.4. UNION ALL và các nhánh độc lập

Với set operator, plan thường có operation cha như `UNION-ALL` và nhiều nhánh con:

```text
UNION-ALL
  TABLE ACCESS FULL CURRENT_ORDERS
  TABLE ACCESS FULL ARCHIVED_ORDERS
```

Mỗi nhánh cung cấp một tập dòng. `UNION-ALL` nối các dòng từ các nhánh và giữ cả dòng trùng. Với `UNION`, Oracle cần loại trùng nên plan có thể thêm `SORT UNIQUE` hoặc `HASH UNIQUE`.

Không nên giả định các nhánh luôn chạy tuần tự theo thứ tự ID. Việc đánh giá thứ tự và mức độ chạy phụ thuộc operation, parallel execution và cách tiêu thụ kết quả. Hãy xác định nhánh nào có predicate, nhánh nào quét bảng, nhánh nào có thể được loại bỏ bởi điều kiện hoặc phép biến đổi.

### 5.5. Query block và alias

Khi plan phức tạp, các tên query block và alias giúp xác định operation thuộc phần nào của SQL. Có thể yêu cầu `DBMS_XPLAN` hiển thị thông tin alias và query block:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :sql_id,
        :child_number,
        'ALL +ALIAS +OUTLINE +PREDICATE'
    )
);
```

`ALIAS` giúp liên hệ object trong plan với alias của câu SQL. `OUTLINE` hiển thị các gợi ý tương ứng với plan trong một số định dạng output, hữu ích khi điều tra quyết định của optimizer. Không nên lấy outline rồi áp dụng trực tiếp như một bộ hint cố định nếu chưa hiểu nguyên nhân plan ban đầu.

## 6. Operation có thể xử lý theo luồng hoặc cần tích lũy dữ liệu

Không phải operation nào cũng có cùng cách tiêu thụ dữ liệu. Một số operation có thể trả dòng sớm; một số operation phải đọc và tích lũy một phần hoặc toàn bộ đầu vào trước khi trả kết quả.

| Loại operation | Hành vi thường gặp | Hệ quả khi đọc plan |
|---|---|---|
| Index lookup | Có thể trả key/rowid khi tìm được | Có thể được gọi nhiều lần bởi nested loops |
| Filter | Kiểm tra từng dòng khi dòng đến | Có thể loại dòng sớm trước operation cha |
| Nested loops | Lấy dòng outer rồi yêu cầu inner | Inner có thể có `Starts` cao |
| Hash join | Build hash table rồi probe | Build input cần được xử lý trước giai đoạn probe tương ứng |
| Sort | Cần tổ chức dữ liệu theo thứ tự | Có thể cần tích lũy dữ liệu và dùng TEMP |
| Group by | Gom nhóm theo key | Có thể cần hash/sort và giữ trạng thái tổng hợp |
| UNION ALL | Nhận dữ liệu từ nhiều nhánh | Có thể chuyển dòng từ nhiều nhánh lên nút cha |
| COUNT STOPKEY | Dừng khi đạt giới hạn | Có thể không cần đọc hết nhánh con |

### 6.1. Pipelining

Pipelining nghĩa là operation có thể chuyển dòng cho operation cha ngay khi dòng đó sẵn sàng, thay vì đợi toàn bộ dữ liệu của nhánh hoàn tất. Điều này có thể giúp truy vấn bắt đầu trả kết quả sớm.

Ví dụ, một index range scan có thể tạo rowid, table access lấy dòng, filter kiểm tra và operation phía trên nhận dòng. Chuỗi này có thể tiến triển theo từng dòng hoặc từng batch tùy operation và cách thực thi.

Không phải toàn bộ cây đều pipeline. Sort, hash join build phase, group by và một số phép biến đổi cần tích lũy dữ liệu. Nếu operation phải ghi dữ liệu trung gian ra TEMP, độ trễ và chi phí I/O có thể tăng đáng kể.

### 6.2. STOPKEY và giới hạn dòng

Truy vấn có `ROWNUM`, `FETCH FIRST n ROWS ONLY` hoặc một giới hạn tương tự có thể tạo operation `COUNT STOPKEY` hoặc operation liên quan. Khi đủ số dòng cần thiết, Oracle có thể dừng yêu cầu thêm dữ liệu từ nhánh con.

Điều này có thể khiến một nhánh chỉ đọc một phần dữ liệu. Nhưng nếu truy vấn yêu cầu `ORDER BY` trên cột không có access path cung cấp thứ tự phù hợp, Oracle có thể vẫn phải đọc và sort nhiều dòng trước khi biết top N. Cần đọc cả operation sort và stopkey để hiểu lượng công việc thực tế.

## 7. Đọc chi phí, cardinality và số lần khởi chạy

Execution plan thường hiển thị các cột như `Rows`, `Bytes`, `Cost`, `%CPU`, `Time` hoặc các cột runtime khi dùng `ALLSTATS LAST`. Những số liệu này có ý nghĩa khác nhau.

| Thuộc tính | Ý nghĩa |
|---|---|
| `Rows` / `E-Rows` | Số dòng optimizer ước lượng operation sẽ trả về |
| `Bytes` | Kích thước dữ liệu ước lượng |
| `Cost` | Chi phí tương đối do optimizer tính cho operation/subtree |
| `%CPU` | Thành phần CPU trong cost theo mô hình optimizer |
| `Time` | Thời gian ước lượng được hiển thị trong plan, không phải cam kết runtime |
| `Starts` | Số lần operation được khởi chạy trong runtime statistics |
| `A-Rows` | Số dòng thực tế operation trả ra trong lần thực thi được thống kê |
| `Buffers` | Logical reads được ghi nhận |
| `Reads` | Physical reads được ghi nhận nếu có |
| `A-Time` | Thời gian thực tế được ghi nhận cho operation theo output plan |

### 7.1. Cost không phải thời gian chạy

`Cost` là đại lượng tương đối trong mô hình cost-based optimizer. Không thể đọc `Cost = 100` rồi kết luận truy vấn mất 100 mili giây. Cost giúp optimizer so sánh các phương án trong cùng ngữ cảnh ước lượng.

Cost của operation cha thường bao gồm chi phí của các operation con trong subtree. Không nên cộng cost của tất cả các dòng trong plan để tính tổng cost; điều đó có thể đếm lặp chi phí. Hãy đọc cost ở nút gốc để xem ước lượng tổng thể của plan và đọc các nút con để hiểu nơi chi phí được hình thành.

### 7.2. E-Rows và A-Rows

`E-Rows` là cardinality ước lượng; `A-Rows` là số dòng thực tế. Nếu hai số chênh lệch lớn, optimizer có thể đã đánh giá sai selectivity, phân bố dữ liệu hoặc quan hệ giữa các nhánh.

Ví dụ:

```text
Operation                         Starts   E-Rows   A-Rows
--------------------------------  -------  -------  -------
TABLE ACCESS FULL ORDERS                1    10000   900000
INDEX UNIQUE SCAN CUSTOMERS_PK     900000        1   900000
```

Nếu bảng `ORDERS` thực tế trả 900.000 dòng nhưng optimizer chỉ ước lượng 10.000, các operation join phía trên có thể được chọn dựa trên giả định quá nhỏ. Nhánh inner của nested loops cũng có thể bị gọi hàng trăm nghìn lần.

Với operation có `Starts` lớn hơn 1, cần đọc `E-Rows` cùng `Starts`. Cardinality ước lượng thường biểu diễn số dòng cho mỗi lần start, trong khi `A-Rows` trong runtime output là số dòng tích lũy qua các lần start. Vì vậy, khi đối chiếu có thể cần so sánh `A-Rows / Starts` với `E-Rows`, đồng thời hiểu ngữ cảnh operation và phiên bản output.

Ví dụ, inner index lookup có `E-Rows = 1`, `Starts = 50.000`, `A-Rows = 50.000` là hành vi có thể đúng: mỗi lần lookup trả trung bình một dòng. Nếu chỉ so `E-Rows = 1` với `A-Rows = 50.000`, có thể nhầm rằng cardinality sai nghiêm trọng.

### 7.3. Starts giúp phát hiện nhánh bị chạy lặp lại

`Starts` đặc biệt hữu ích với nested loops, scalar subquery và các nhánh được gọi theo từng dòng. Một operation có `Starts` lớn chưa chắc có vấn đề; nếu mỗi lần chạy rất rẻ và số dòng outer phù hợp, đó có thể là lựa chọn tốt.

Hãy đánh giá đồng thời:

- Số lần start của operation.
- Số dòng thực tế mỗi lần start.
- Số buffer được đọc.
- Thời gian thực tế.
- Số dòng từ nhánh ngoài.
- Predicate và access path được dùng trong nhánh trong.

Nếu inner operation bị gọi quá nhiều lần và mỗi lần đọc nhiều block, cần xem lại join order, index, predicate hoặc cardinality estimates.

## 8. Xem execution plan bằng DBMS_XPLAN

`DBMS_XPLAN` là package chuẩn để hiển thị execution plan theo định dạng dễ đọc. Có thể dùng plan đã lưu từ `EXPLAIN PLAN`, plan của cursor trong shared pool hoặc các nguồn plan khác được hỗ trợ.

### 8.1. EXPLAIN PLAN và DISPLAY

Ví dụ:

```sql
EXPLAIN PLAN FOR
SELECT order_id, order_date
FROM app.orders
WHERE order_status = 'PENDING';
```

Hiển thị plan vừa explain:

```sql
SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` yêu cầu optimizer lập plan cho câu SQL trong ngữ cảnh explain. Plan này hữu ích để xem cấu trúc dự kiến, nhưng có thể khác plan cursor thực sự chạy do bind values, bind peeking, session parameters, quyền, schema resolution, adaptive cursor sharing, statistics hoặc các yếu tố runtime.

### 8.2. DISPLAY_CURSOR để xem plan của cursor thực tế

Sau khi câu SQL đã chạy, có thể xem plan của cursor trong shared pool:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        :sql_id,
        :child_number,
        'ALL +PREDICATE +ALIAS +NOTE'
    )
);
```

Nếu đang ở cùng session và muốn xem cursor vừa chạy gần nhất, có thể dùng:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'TYPICAL'
    )
);
```

`SQL_ID` xác định câu SQL trong shared pool; `CHILD_NUMBER` xác định child cursor cụ thể. Một SQL có thể có nhiều child cursor do bind metadata, optimizer environment hoặc các lý do khác. Khi điều tra plan, cần chắc chắn đang xem đúng child cursor của lần thực thi cần phân tích.

### 8.3. Thu thập actual row-source statistics

Để xem actual rows và số lần start, hãy yêu cầu Oracle thu thập runtime plan statistics. Có thể dùng hint cho câu SQL cần đo:

```sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       order_date,
       total_amount
FROM app.orders
WHERE order_status = 'PENDING';
```

Sau khi câu lệnh hoàn tất, trong cùng session:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS +NOTE'
    )
);
```

`ALLSTATS LAST` yêu cầu hiển thị runtime statistics của lần thực thi gần nhất được ghi nhận. Nếu chưa bật thu thập runtime statistics, các cột actual có thể không có dữ liệu. Có thể dùng `STATISTICS_LEVEL = ALL` trong session cho mục đích điều tra, nhưng cần cân nhắc overhead và khôi phục cấu hình sau khi đo.

### 8.4. Các format option hữu ích

| Format option | Mục đích |
|---|---|
| `BASIC` | Output tối giản |
| `TYPICAL` | Output thông dụng, có các thông tin plan quan trọng |
| `ALL` | Hiển thị nhiều thông tin hơn |
| `ALLSTATS LAST` | Bổ sung runtime statistics của lần thực thi gần nhất nếu có |
| `+PREDICATE` | Hiển thị access/filter predicates |
| `+ALIAS` | Hiển thị alias và thông tin liên kết object |
| `+NOTE` | Hiển thị note liên quan đến plan |
| `+OUTLINE` | Hiển thị outline hints gắn với plan |
| `+PARTITION` | Hiển thị thông tin partition khi có |
| `+ADAPTIVE` | Bổ sung thông tin adaptive plan trong trường hợp hỗ trợ |
| `+PROJECTION` | Hiển thị các biểu thức/cột được project tại operation |

Không cần bật mọi format option trong mỗi lần đọc. Hãy bắt đầu bằng `TYPICAL` hoặc `ALLSTATS LAST +PREDICATE`, rồi bổ sung `ALIAS`, `PARTITION`, `OUTLINE` hoặc `ADAPTIVE` khi câu hỏi điều tra yêu cầu.

## 9. Đọc ví dụ plan từ đầu đến cuối

Giả sử ứng dụng cần lấy các đơn hàng đang chờ xử lý cùng tên khách hàng:

```sql
SELECT o.order_id,
       o.order_date,
       c.customer_name
FROM app.orders o
JOIN app.customers c
  ON c.customer_id = o.customer_id
WHERE o.order_status = 'PENDING'
  AND o.order_date >= DATE '2026-01-01';
```

Giả sử output rút gọn như sau:

```text
--------------------------------------------------------------------------------
| Id | Operation                               | Name              | E-Rows |
--------------------------------------------------------------------------------
|  0 | SELECT STATEMENT                        |                   |        |
|  1 |  NESTED LOOPS                           |                   |    120 |
|  2 |   TABLE ACCESS BY INDEX ROWID BATCHED   | ORDERS            |    120 |
|  3 |    INDEX RANGE SCAN                     | ORDERS_STATUS_IX  |    800 |
|  4 |   TABLE ACCESS BY INDEX ROWID           | CUSTOMERS         |      1 |
|  5 |    INDEX UNIQUE SCAN                    | CUSTOMERS_PK      |      1 |
--------------------------------------------------------------------------------

Predicate Information:
  3 - access("O"."ORDER_STATUS"='PENDING')
  2 - filter("O"."ORDER_DATE">=DATE '2026-01-01')
  5 - access("C"."CUSTOMER_ID"="O"."CUSTOMER_ID")
```

Đọc theo cấu trúc:

1. `SELECT STATEMENT` là nút gốc, nhận kết quả cuối từ nested loops.
2. `NESTED LOOPS` có hai nhánh trực tiếp: nhánh đơn hàng và nhánh khách hàng.
3. Nhánh đơn hàng gồm index range scan và table access. Index tìm các đơn hàng có trạng thái `PENDING`; table access lấy dòng và filter tiếp theo ngày.
4. Nhánh khách hàng gồm index unique scan và table access. Với mỗi đơn hàng cần kết hợp, index tìm khách hàng theo `CUSTOMER_ID`, rồi table access lấy `CUSTOMER_NAME`.
5. Nested loops ghép dòng đơn hàng với dòng khách hàng và chuyển kết quả lên nút gốc.

Đọc theo luồng xử lý:

- Nhánh đơn hàng là outer row source trong nested loops này.
- Nhánh khách hàng là inner row source, được tra cứu theo `CUSTOMER_ID` của dòng đơn hàng.
- `Starts` của nhánh khách hàng có thể gần với số dòng đơn hàng thực sự được chuyển tới join.
- Nếu predicate ngày loại bỏ phần lớn dòng sau khi đọc bảng, cần xem số rowid và table block đã phải truy cập trước khi filter.

Đọc theo hiệu năng:

- Nếu index range scan trả 800 dòng nhưng table access chỉ chuyển 120 dòng, điều kiện ngày đang loại bỏ một phần đáng kể sau bước truy cập bảng.
- Nếu thực tế có hàng trăm nghìn đơn hàng nhưng `E-Rows` chỉ 120, nested loops có thể bị chọn dựa trên cardinality quá thấp.
- Nếu nhánh khách hàng có `Starts = 120`, `E-Rows = 1` và `A-Rows = 120`, đó có thể là hành vi bình thường: mỗi lần lookup trả một khách hàng.
- Nếu `Starts` của nhánh khách hàng lớn hơn rất nhiều so với 120, cần kiểm tra runtime details, số lần chạy thực tế và các phép biến đổi liên quan.

Ví dụ chỉ minh họa cách đọc. Plan thật có thể dùng hash join, full scan, index khác hoặc predicate được đẩy sang operation khác tùy thống kê, bind values, kích thước dữ liệu và môi trường.

## 10. Adaptive plan và các nhánh thay thế

Trong một số trường hợp, Oracle có thể tạo adaptive plan để trì hoãn một quyết định cho đến khi có thêm thông tin runtime. Ví dụ, optimizer có thể giữ các lựa chọn join method hoặc nhánh xử lý thay thế, rồi quyết định nhánh nào phù hợp dựa trên lượng dữ liệu quan sát được.

Khi hiển thị adaptive plan, output có thể thể hiện cả operation đang hoạt động và operation thay thế không được chọn trong lần chạy đó. Vì vậy, không nên cộng cost hoặc coi tất cả các nhánh hiển thị đều đã chạy. Hãy dùng format hỗ trợ adaptive, đọc note của plan và đối chiếu runtime statistics của cursor.

Adaptive plan cũng không có nghĩa Oracle luôn tự sửa mọi ước lượng sai. Quyết định adaptive chỉ áp dụng cho các tình huống và cấu trúc được hỗ trợ. Nếu cardinality sai ở một nhánh khác hoặc SQL đã chọn child cursor không phù hợp, vẫn cần điều tra statistics, bind values và plan thực tế.

## 11. Đọc nhánh trong parallel execution

Với parallel execution, plan có thể chứa các operation như:

- `PX COORDINATOR`
- `PX SEND` và `PX RECEIVE`
- `PX BLOCK ITERATOR`
- `PX PARTITION RANGE`
- `PX SEND HASH`, `PX SEND BROADCAST` hoặc dạng phân phối khác

Các operation này mô tả việc phân chia công việc và chuyển dữ liệu giữa query coordinator và các parallel execution servers. Một nhánh có thể được chạy đồng thời trên nhiều process; vì vậy, không thể đọc toàn bộ plan như một session đơn thực hiện tuần tự từ một nút đến nút khác.

Ví dụ rút gọn:

```text
PX COORDINATOR
  PX SEND QC (RANDOM)
    HASH GROUP BY
      PX RECEIVE
        PX SEND HASH
          HASH JOIN
            PX BLOCK ITERATOR
              TABLE ACCESS FULL SALES
            PX BLOCK ITERATOR
              TABLE ACCESS FULL PRODUCTS
```

Có thể đọc ở mức khái niệm:

1. Các parallel server đọc các block của `SALES` và `PRODUCTS` theo phạm vi được phân công.
2. Dữ liệu được phân phối giữa các process theo hash hoặc cơ chế được chỉ định.
3. Các process thực hiện join và group by theo các nhánh parallel.
4. Kết quả được gửi về query coordinator để trả cho client.

Các operation `PX SEND`/`PX RECEIVE` thể hiện ranh giới trao đổi dữ liệu giữa các nhóm process. `PX SEND HASH` thường phân phối dòng theo hash của một hoặc nhiều key; `PX SEND BROADCAST` gửi dữ liệu tới nhiều process; `PX SEND QC` chuyển kết quả về query coordinator. Ý nghĩa chi tiết phụ thuộc `IN-OUT`, `PQ Distrib` và cấu trúc plan cụ thể.

Khi đọc parallel plan, hãy xác định:

- Nhánh nào là producer và nhánh nào là consumer.
- Dữ liệu được phân phối theo hash, broadcast hay random.
- Có bước redistributing dữ liệu lớn giữa các process hay không.
- Có mất cân bằng dữ liệu (data skew) khiến một process nhận nhiều dữ liệu hơn các process khác không.
- Có operation sort, hash join hoặc group by dùng TEMP ở từng process không.
- Degree of Parallelism thực tế có đúng với dự kiến không.

Parallel plan có thể giảm thời gian cho workload phù hợp, nhưng cũng tạo chi phí khởi tạo process, trao đổi dữ liệu và tranh chấp tài nguyên. Không nên kết luận cứ có `PX` là truy vấn nhanh hơn.

## 12. Phân biệt plan ước lượng và plan thực tế

Plan được hiển thị từ `EXPLAIN PLAN` là plan được optimizer ước lượng trong ngữ cảnh explain. Plan từ `DISPLAY_CURSOR` là plan gắn với cursor thực tế. Khi điều tra sự cố, cần ưu tiên plan của cursor đã chạy và runtime statistics nếu có.

Các nguyên nhân khiến hai plan khác nhau có thể gồm:

- Bind value khác nhau và bind peeking.
- Adaptive cursor sharing tạo nhiều child cursor.
- Session parameter hoặc optimizer environment khác nhau.
- Schema, quyền, synonym hoặc object resolution khác nhau.
- Statistics thay đổi giữa thời điểm explain và thời điểm chạy.
- Adaptive plan chọn nhánh khác khi có runtime information.
- SQL được rewrite hoặc được thực thi trong context khác.

Để so sánh có ý nghĩa, cần ghi nhận SQL text, SQL ID, child number, plan hash value, bind values phù hợp, optimizer environment và thời điểm lấy statistics. Chỉ so sánh hai output plan mà không biết các yếu tố này có thể dẫn đến kết luận sai.

## 13. Quy trình đọc một execution plan phức tạp

Khi gặp plan dài với nhiều nhánh, hãy đọc theo từng lượt để không bị lẫn giữa cấu trúc, luồng và hiệu năng.

### Bước 1: Xác định nút gốc và loại câu SQL

Tìm `SELECT STATEMENT`, `INSERT STATEMENT`, `UPDATE STATEMENT`, `DELETE STATEMENT` hoặc `MERGE STATEMENT`. Nút gốc cho biết loại thao tác tổng thể. Với DML, plan có thể chứa operation đọc dữ liệu, join và operation ghi dữ liệu.

### Bước 2: Chia cây thành các nhánh con trực tiếp

Tìm operation lớn ở ngay dưới nút gốc. Với mỗi operation, xác định các nhánh con trực tiếp bằng indentation hoặc `PARENT_ID`. Không đọc sâu tất cả các dòng ngay lập tức.

### Bước 3: Xác định row source của từng nhánh

Tìm operation lá như table access, index access, partition iterator, remote access hoặc external table access. Ghi lại bảng/index nào được đọc, theo access path nào và có predicate gì.

### Bước 4: Đọc operation kết hợp giữa các nhánh

Nhận diện nested loops, hash join, merge join, union all, group by hoặc sort. Với mỗi operation, giải thích dữ liệu từ các nhánh con được tiêu thụ và chuyển tiếp ra sao.

### Bước 5: Gắn predicate vào đúng operation

Đọc `Predicate Information`, xác định access predicate, filter predicate và điều kiện join. Liên hệ operation ID với cây để biết điều kiện làm giảm dữ liệu ở đâu.

### Bước 6: Kiểm tra cardinality và số lần chạy

So sánh `E-Rows`, `A-Rows` và `Starts`. Với operation được gọi nhiều lần, chú ý số dòng trung bình mỗi lần start. Tìm nhánh có chênh lệch lớn hoặc có số lần chạy cao.

### Bước 7: Kiểm tra tài nguyên runtime

Xem `Buffers`, `Reads`, `A-Time`, TEMP, workarea và parallel distribution nếu có. Cost là ước lượng; runtime statistics mới cho biết hoạt động thực tế của lần chạy được đo.

### Bước 8: Kiểm tra yếu tố ngoài cây

Nếu plan vẫn khó giải thích, xem bind values, child cursor, optimizer environment, statistics, partition pruning, adaptive plan và các thông tin note/outline.

## 14. Các lỗi đọc plan thường gặp

| Cách hiểu sai | Cách hiểu đúng |
|---|---|
| Đọc `Id` tăng dần như thứ tự chạy | `Id` là định danh; phải đọc quan hệ cha-con và loại operation |
| Cứ đọc từ dưới lên là biết toàn bộ runtime order | Bottom-up giúp hiểu nguồn dữ liệu; nested loops, hash join và pipeline có cách tiêu thụ khác nhau |
| Bảng đứng đầu `FROM` luôn được đọc trước | Optimizer có thể thay đổi join order trong phạm vi ngữ nghĩa cho phép |
| Mọi operation con chỉ chạy một lần | Inner branch, scalar subquery hoặc operation được gọi lặp có thể có `Starts` lớn |
| `INDEX RANGE SCAN` là kết quả cuối | Thường cần table access bằng rowid hoặc operation cha khác để tạo dòng kết quả |
| Cost là mili giây | Cost là đại lượng tương đối trong mô hình optimizer |
| `E-Rows = 1`, `A-Rows = 100000` chắc chắn sai 100000 lần | Nếu `Starts = 100000`, có thể mỗi lần start trả đúng một dòng |
| Tất cả nhánh hiển thị trong adaptive plan đều đã chạy | Một số nhánh là phương án thay thế; cần xác định nhánh active |
| Mọi operation trong parallel plan chạy tuần tự | Các nhánh có thể chạy đồng thời trên nhiều process và trao đổi dữ liệu |
| Full table scan luôn xấu | Scan có thể phù hợp khi cần đọc phần lớn bảng hoặc bảng nhỏ |
| Index scan luôn tốt | Index lookup lặp lại nhiều lần hoặc clustering factor bất lợi có thể tốn kém |

## 15. Bài thực hành đọc cây thực thi

Giả sử có ba bảng:

- `CUSTOMERS(customer_id, customer_name, region_id)`
- `ORDERS(order_id, customer_id, order_date, order_status)`
- `ORDER_ITEMS(order_id, product_id, quantity, unit_price)`

Ứng dụng cần tính tổng giá trị đơn hàng theo vùng cho các đơn hàng đã thanh toán trong một khoảng thời gian:

```sql
SELECT c.region_id,
       SUM(oi.quantity * oi.unit_price) AS total_amount
FROM customers c
JOIN orders o
  ON o.customer_id = c.customer_id
JOIN order_items oi
  ON oi.order_id = o.order_id
WHERE o.order_status = 'PAID'
  AND o.order_date >= DATE '2026-01-01'
GROUP BY c.region_id;
```

Khi nhận plan, hãy xác định:

1. Nhánh nào đọc `ORDERS`, nhánh nào đọc `ORDER_ITEMS`, nhánh nào đọc `CUSTOMERS`?
2. `ORDER_STATUS` và `ORDER_DATE` được áp dụng tại operation nào?
3. Optimizer join `ORDERS` với `ORDER_ITEMS` trước hay join `ORDERS` với `CUSTOMERS` trước?
4. Join method của từng tầng là nested loops, hash join hay merge join?
5. Nhánh nào là outer/inner nếu có nested loops?
6. Nếu dùng hash join, nhánh build và probe được thể hiện thế nào trong plan?
7. `GROUP BY` được thực hiện bằng sort hay hash aggregation?
8. Có operation sort hoặc hash nào có nguy cơ dùng TEMP không?
9. `E-Rows` và `A-Rows` khác nhau ở operation nào?
10. `Starts` có cho thấy một nhánh bị chạy lặp lại nhiều lần không?

Không có một execution plan duy nhất bắt buộc cho câu SQL này. Kết quả phụ thuộc vào dữ liệu, statistics, index, bind values, optimizer settings và tài nguyên hệ thống. Mục tiêu của bài thực hành là giải thích được cây thực tế mà Oracle chọn, thay vì đoán trước một chuỗi operation cố định.

## 16. Cách trình bày một plan trong tài liệu điều tra

Khi báo cáo một plan cho người khác, nên trình bày theo thứ tự giúp người đọc hiểu nhanh:

1. **Plan identity:** SQL ID, child number, plan hash value và thời điểm lấy plan.
2. **Cấu trúc tổng thể:** nút gốc, các nhánh join/union/group by chính và nguồn dữ liệu của mỗi nhánh.
3. **Luồng xử lý:** nhánh nào cung cấp dữ liệu cho nhánh nào, join order và join method.
4. **Predicate placement:** điều kiện truy cập và lọc nằm ở operation nào.
5. **Ước lượng so với thực tế:** E-Rows, A-Rows, Starts và vị trí bắt đầu chênh lệch.
6. **Tài nguyên:** logical reads, physical reads, elapsed time, TEMP và parallel exchange nếu có.
7. **Giải thích nguyên nhân:** chỉ ra operation hoặc ước lượng nào tạo ra chi phí chính, có bằng chứng runtime kèm theo.

Một mô tả tốt không chỉ nói “plan có full scan” hoặc “plan dùng nested loops”. Nó giải thích vì sao nhánh đó được chọn, dữ liệu đi qua các operation ra sao, nhánh nào được chạy nhiều lần và số liệu thực tế có xác nhận giả định của optimizer hay không.

Đọc cây thực thi đúng cách giúp chuyển từ việc nhìn tên operation sang hiểu cơ chế xử lý dữ liệu. Khi xác định được quan hệ cha-con, luồng dữ liệu, thứ tự join, predicate và runtime starts, người phân tích có thể tìm chính xác nhánh gây tốn kém và lựa chọn hướng điều tra phù hợp.
