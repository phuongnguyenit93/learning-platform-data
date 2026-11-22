# SQL_ID, PLAN_HASH_VALUE, child cursor và điều kiện tái sử dụng kế hoạch

## 1. Vì sao cần phân biệt SQL_ID, plan hash và child cursor?

Khi điều tra hiệu năng Oracle Database, một câu SQL có thể xuất hiện nhiều lần trong shared pool, có nhiều lần thực thi và thậm chí có nhiều execution plan. Để đọc đúng thông tin trong các view như `V$SQL`, `V$SQLAREA` và `V$SQL_SHARED_CURSOR`, cần phân biệt ba khái niệm:

- **SQL_ID** nhận diện câu SQL trong shared SQL area, dựa trên SQL text.
- **PLAN_HASH_VALUE** là giá trị hash đại diện cho execution plan của một cursor.
- **Child cursor** là phiên bản cursor cụ thể dưới một parent cursor, chứa plan và thông tin thực thi phù hợp với một môi trường/metadata nhất định.

Một `SQL_ID` có thể có nhiều child cursor. Các child có thể dùng cùng `PLAN_HASH_VALUE` hoặc các plan hash khác nhau. Vì vậy, chỉ nhìn SQL_ID hoặc plan hash riêng lẻ chưa đủ để kết luận câu SQL chỉ có một plan hay mọi lần chạy đều dùng cùng một plan.

## 2. SQL_ID và parent cursor

### 2.1. SQL_ID nhận diện điều gì?

Khi Oracle parse một câu SQL, nó tìm hoặc tạo cursor trong library cache thuộc shared pool. `SQL_ID` là định danh dạng ký tự, thường gồm 13 ký tự, được tạo từ SQL text và dùng để tra cứu câu SQL trong các dynamic performance view.

Ví dụ:

```sql
SELECT order_id, customer_id, amount
FROM orders
WHERE customer_id = 1001;
```

Oracle tạo hoặc tìm cursor tương ứng với văn bản SQL này. Có thể tra cứu câu SQL qua `V$SQL`:

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       parse_calls
FROM v$sql
WHERE sql_text LIKE 'SELECT order_id, customer_id, amount%'
ORDER BY sql_id, child_number;
```

Trong thực tế, nên lấy `SQL_ID` từ một lần thực thi đã xác định, từ ứng dụng hoặc từ công cụ giám sát, rồi dùng bind variable khi tra cứu. `SQL_ID` là định danh để quan sát cursor trong Oracle, không phải mã nghiệp vụ hoặc định danh vĩnh viễn của một chức năng ứng dụng.

### 2.2. Parent cursor là gì?

Oracle quản lý cursor theo quan hệ parent-child trong library cache:

```text
SQL text
   |
   v
Parent cursor (SQL_ID)
   |
   +-- Child cursor 0  -> execution plan / execution context
   +-- Child cursor 1  -> execution plan / execution context
   +-- Child cursor 2  -> execution plan / execution context
```

Parent cursor đại diện cho câu SQL và là điểm tập hợp các child cursor tương ứng. Khi SQL text khớp với một parent cursor hiện có, Oracle tiếp tục kiểm tra có child cursor nào phù hợp để tái sử dụng hay không. Nếu không có child tương thích, Oracle có thể tạo child cursor mới dưới cùng parent.

Nếu SQL text khác, Oracle thường xem đó là một câu SQL khác và tạo parent cursor/SQL_ID khác. Các khác biệt về khoảng trắng, chữ hoa/chữ thường, comment hoặc literal có thể khiến văn bản SQL không còn khớp. Cơ chế `CURSOR_SHARING` có thể thay đổi cách xử lý literal, nhưng không nên dựa vào nó để coi mọi câu SQL có cấu trúc gần giống nhau là cùng một cursor.

### 2.3. SQL_ID không đồng nghĩa với một lần thực thi

Một SQL_ID có thể được ứng dụng gọi hàng nghìn lần. Mỗi lần thực thi không nhất thiết tạo một cursor mới. Nhiều lần parse/execute có thể dùng lại cùng child cursor nếu cursor vẫn còn trong shared pool, hợp lệ và tương thích với lần gọi.

Các cột như `EXECUTIONS`, `PARSE_CALLS`, `LOADS` và `INVALIDATIONS` trong `V$SQL` cung cấp thông tin quan sát về cursor. Chúng là số liệu tích lũy theo vòng đời của cursor trong shared pool; nếu cursor bị aged out, invalidated hoặc bị loại khỏi cache rồi được nạp lại, số liệu có thể bắt đầu lại theo cursor mới.

## 3. PLAN_HASH_VALUE

### 3.1. Ý nghĩa

`PLAN_HASH_VALUE` là giá trị số đại diện cho cấu trúc execution plan của một cursor. Nó giúp so sánh nhanh plan của cùng câu SQL giữa các child cursor, lần quan sát hoặc môi trường.

Ví dụ truy vấn:

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
```

Nếu các child của cùng SQL_ID có `PLAN_HASH_VALUE` khác nhau, đó là dấu hiệu chúng có execution plan khác nhau theo phần cấu trúc được plan hash đại diện. Khi đó cần xem chi tiết từng child bằng `DBMS_XPLAN.DISPLAY_CURSOR`.

### 3.2. Cùng PLAN_HASH_VALUE có bảo đảm mọi thứ giống hệt nhau không?

Không. Plan hash là một mã tóm tắt để nhận diện plan, không phải bản mô tả đầy đủ mọi thuộc tính thực thi. Hai cursor có cùng plan hash thường có cấu trúc operation tương ứng, nhưng không thể chỉ từ đó kết luận:

- Bind values của hai lần thực thi giống nhau.
- Số dòng thực tế, số block đọc hoặc thời gian thực thi giống nhau.
- Optimizer environment, thống kê runtime hoặc mọi thuộc tính phụ của plan giống nhau.
- Không có khác biệt về thông tin mà giá trị hash không đại diện.

Ngược lại, hai câu SQL khác nhau vẫn có thể có cùng `PLAN_HASH_VALUE` nếu cấu trúc plan của chúng giống nhau. Do đó, plan hash không phải định danh duy nhất toàn cục cho câu SQL.

Oracle còn cung cấp `FULL_PLAN_HASH_VALUE` trong các phiên bản hỗ trợ. Giá trị này thể hiện chi tiết plan đầy đủ hơn, nhưng không nên so sánh trực tiếp giữa các phiên bản Oracle khác nhau. Khi so sánh giữa môi trường hoặc phiên bản, cần đối chiếu plan text và ngữ cảnh thực thi.

### 3.3. SQL_ID và PLAN_HASH_VALUE bổ sung cho nhau

| Thuộc tính | SQL_ID | PLAN_HASH_VALUE |
|---|---|---|
| Đại diện cho | Câu SQL/cursor parent | Cấu trúc execution plan |
| Kiểu giá trị | Chuỗi định danh | Số hash |
| Một giá trị có thể gắn với nhiều giá trị còn lại? | Một SQL_ID có thể có nhiều plan hash qua các child cursor | Một plan hash có thể xuất hiện ở nhiều SQL_ID |
| Dùng để | Tìm câu SQL và các child cursor | Nhận biết/so sánh plan nhanh |

Khi báo cáo một vấn đề hiệu năng, nên ghi lại ít nhất `SQL_ID`, `CHILD_NUMBER` và `PLAN_HASH_VALUE`. Ba giá trị này xác định rõ hơn cursor/plan đang được quan sát tại thời điểm đó.

## 4. Child cursor và lý do một SQL_ID có nhiều child

### 4.1. Child cursor chứa gì?

Child cursor là cursor thực thi cụ thể dưới parent cursor. Nó gắn với execution plan và các thuộc tính cần thiết để thực thi câu SQL trong một ngữ cảnh tương thích. Trong `V$SQL`, mỗi child cursor được thể hiện bằng một dòng, phân biệt bởi `CHILD_NUMBER` dưới cùng `SQL_ID`.

Ví dụ một SQL_ID có thể xuất hiện như sau:

| SQL_ID | CHILD_NUMBER | PLAN_HASH_VALUE | Ý nghĩa minh họa |
|---|---:|---:|---|
| `abc...` | 0 | 1234567890 | Child đầu tiên, plan A |
| `abc...` | 1 | 1234567890 | Child khác, nhưng plan hash giống A |
| `abc...` | 2 | 9876543210 | Child khác, plan B |

Đây là dữ liệu minh họa. Child number là số thứ tự trong nhóm child của parent cursor ở thời điểm quan sát; không nên dùng nó như định danh ổn định lâu dài sau khi shared pool thay đổi hoặc instance khởi động lại.

### 4.2. Các nguyên nhân thường tạo child cursor mới

Oracle chỉ tái sử dụng child cursor khi các thuộc tính liên quan tương thích. Một child mới có thể được tạo khi có khác biệt đáng kể, chẳng hạn:

- **Bind metadata không tương thích:** kiểu dữ liệu, độ dài hoặc đặc điểm bind variable khác nhau giữa các lần parse.
- **Optimizer environment khác nhau:** các tham số optimizer/session ảnh hưởng đến quá trình tối ưu hóa khác nhau.
- **Object resolution hoặc authorization khác nhau:** schema phân tích, quyền truy cập, synonym, edition hoặc ngữ cảnh phân giải đối tượng tạo ra khác biệt.
- **Metadata của đối tượng thay đổi:** định nghĩa bảng, cột, index hoặc dependency khiến child cũ không còn phù hợp.
- **Thông tin thống kê hoặc feedback khác nhau:** thay đổi thống kê, cardinality feedback hoặc cơ chế tối ưu hóa thích ứng có thể dẫn đến child/plan khác.
- **Bind peeking và Adaptive Cursor Sharing:** các nhóm bind values có selectivity khác nhau có thể cần plan khác nhau.

Đây là các nhóm nguyên nhân phổ biến; không phải mọi khác biệt session đều chắc chắn tạo child mới. Oracle kiểm tra nhiều điều kiện tương thích nội bộ và các điều kiện cụ thể còn phụ thuộc phiên bản.

### 4.3. VERSION_COUNT

`V$SQLAREA` tổng hợp thông tin theo SQL statement/parent cursor. Cột `VERSION_COUNT` cho biết số phiên bản child cursor được ghi nhận cho câu SQL trong shared pool.

```sql
SELECT sql_id,
       version_count,
       executions,
       parse_calls
FROM v$sqlarea
WHERE sql_id = :sql_id;
```

`VERSION_COUNT` lớn có thể là dấu hiệu SQL đang có nhiều child cursor. Tuy nhiên, không phải cứ nhiều child là lỗi. Có thể nhiều child là cần thiết, ví dụ do adaptive cursor sharing tạo các plan phù hợp với các nhóm bind values khác nhau. Cần tìm nguyên nhân và đánh giá chi phí parse trước khi kết luận có vấn đề.

## 5. Hard parse, soft parse và tái sử dụng cursor

### 5.1. Luồng parse cơ bản

Khi ứng dụng gửi câu SQL, Oracle cần xác định cursor nào sẽ thực thi:

```text
Ứng dụng gửi SQL
       |
       v
Tìm parent cursor theo SQL text
       |
       +-- Không có parent phù hợp
       |       -> hard parse
       |       -> tạo parent/child và chọn execution plan
       |
       +-- Có parent
               |
               v
         Tìm child tương thích
               |
               +-- Có child hợp lệ -> soft parse / tái sử dụng
               |
               +-- Không có child phù hợp
                       -> hard parse để tạo child mới
```

Sơ đồ mô tả luồng khái quát. Parse thực tế còn chịu ảnh hưởng của session cursor cache, client statement cache, trạng thái library cache và các cơ chế nội bộ của Oracle.

### 5.2. Hard parse

Hard parse xảy ra khi Oracle phải thực hiện công việc parse và tối ưu hóa để tạo cursor/child mới thay vì tái sử dụng một child tương thích. Công việc có thể bao gồm:

- Phân tích cú pháp và ngữ nghĩa.
- Kiểm tra tên đối tượng, quyền và dependency.
- Xác định kiểu dữ liệu, bind metadata và môi trường tối ưu hóa.
- Tạo các phương án thực thi, ước lượng chi phí và chọn execution plan.
- Tạo child cursor và lưu vào library cache nếu thành công.

Hard parse thường tốn CPU và có thể tạo áp lực lên library cache, đặc biệt khi ứng dụng liên tục gửi SQL text khác nhau hoặc tạo nhiều child cursor không cần thiết.

### 5.3. Soft parse

Soft parse xảy ra khi Oracle tìm được cursor phù hợp và có thể dùng lại thay vì tạo một cursor mới qua hard parse. Oracle vẫn cần thực hiện các kiểm tra cần thiết cho lần parse hiện tại; soft parse không có nghĩa là bỏ qua hoàn toàn bước parse.

Tái sử dụng cursor giúp giảm chi phí tối ưu hóa và tạo plan. Tuy vậy, ứng dụng vẫn nên quản lý vòng đời statement đúng cách, đóng cursor khi không còn sử dụng và tránh parse lặp lại không cần thiết.

### 5.4. Cursor còn trong shared pool và còn hợp lệ

Để tái sử dụng, child cursor cần còn hiện diện trong library cache và còn hợp lệ đối với ngữ cảnh parse mới. Cursor có thể không dùng lại được nếu:

- Bị aged out khỏi shared pool do áp lực bộ nhớ.
- Bị invalidated vì thay đổi đối tượng hoặc dependency, thao tác DDL, thay đổi liên quan đến statistics hoặc các nguyên nhân khác.
- Child hiện có không tương thích với bind metadata, optimizer environment, quyền hoặc ngữ cảnh phân giải đối tượng.
- SQL text không khớp với parent cursor hiện có.

Sau khi cursor bị loại khỏi cache hoặc invalidated, lần parse tiếp theo có thể phải nạp lại hoặc tạo child mới. Việc một SQL_ID từng tồn tại trong `V$SQL` không bảo đảm cursor sẽ luôn tồn tại ở đó.

## 6. Bind variables, bind peeking và Adaptive Cursor Sharing

### 6.1. Vì sao bind variables hỗ trợ tái sử dụng?

So sánh hai câu SQL:

```sql
SELECT * FROM orders WHERE customer_id = 1001;
SELECT * FROM orders WHERE customer_id = 1002;
```

Nếu gửi hai câu với literal khác nhau và không có cơ chế chuẩn hóa phù hợp, SQL text khác nhau nên Oracle có thể tạo hai parent cursor riêng. Điều này làm tăng số cursor và công việc hard parse.

Dùng bind variable:

```sql
SELECT *
FROM orders
WHERE customer_id = :customer_id;
```

Ứng dụng bind giá trị `1001`, `1002` vào cùng câu SQL. SQL text có thể được tái sử dụng, giảm số parent cursor và thường giảm hard parse khi các lần gọi tương thích.

Bind variable cũng giúp giảm nguy cơ SQL injection khi được bind đúng cách và tách dữ liệu khỏi cấu trúc câu lệnh. Tuy nhiên, dùng bind không bảo đảm chỉ có một child cursor hoặc một execution plan.

### 6.2. Bind peeking

Khi hard parse một câu SQL có bind variable, Oracle có thể xem giá trị bind tại thời điểm parse để ước lượng selectivity và chọn plan. Cơ chế này gọi là **bind peeking**.

Giả sử `CUSTOMER_ID` có phân bố lệch:

- Một khách hàng lớn có hàng triệu đơn hàng.
- Phần lớn khách hàng khác chỉ có vài chục đơn hàng.

Một plan phù hợp cho khách hàng nhỏ có thể không phù hợp cho khách hàng lớn. Nếu plan ban đầu được chọn dựa trên bind value có selectivity rất cao, plan đó có thể kém hiệu quả khi dùng cho giá trị trả về rất nhiều dòng.

Bind peeking không có nghĩa Oracle đọc lại bind value và hard parse lại ở mọi lần execute. Giá trị được peek tại thời điểm parse có thể ảnh hưởng đến plan được lưu trong child cursor và được tái sử dụng ở những lần sau.

### 6.3. Adaptive Cursor Sharing

Adaptive Cursor Sharing (ACS) cho phép Oracle nhận biết một câu SQL bind-sensitive có thể cần các plan khác nhau cho các vùng selectivity khác nhau. Qua quá trình thực thi và theo dõi, Oracle có thể đánh dấu cursor là bind-aware và tạo hoặc chọn child cursor phù hợp với nhóm bind values.

Ví dụ minh họa:

```text
Một SQL_ID với predicate CUSTOMER_ID = :customer_id
       |
       +-- Child 0: plan phù hợp nhóm khách hàng ít dữ liệu
       |
       +-- Child 1: plan phù hợp nhóm khách hàng nhiều dữ liệu
```

Trong `V$SQL`, các cột `IS_BIND_SENSITIVE` và `IS_BIND_AWARE` giúp quan sát trạng thái liên quan đến ACS:

- `IS_BIND_SENSITIVE = 'Y'`: cursor được theo dõi vì bind value có thể ảnh hưởng đến selectivity.
- `IS_BIND_AWARE = 'Y'`: Oracle có thể chọn child theo vùng bind selectivity phù hợp.

ACS nhằm cải thiện lựa chọn plan cho các phân bố bind khác nhau. Nó không bảo đảm mỗi giá trị bind có một child riêng, cũng không bảo đảm mọi workload đều cần nhiều child. Số child và plan thực tế phụ thuộc dữ liệu, phiên bản, statistics và hành vi của workload.

## 7. Các view dùng để điều tra cursor và plan

### 7.1. V$SQL: xem từng child cursor

`V$SQL` có một dòng cho mỗi child cursor đang được lưu trong shared SQL area. Truy vấn các trường cơ bản:

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       parse_calls,
       loads,
       invalidations,
       is_bind_sensitive,
       is_bind_aware
FROM v$sql
WHERE sql_id = :sql_id
ORDER BY child_number;
```

Các cột hữu ích:

| Cột | Ý nghĩa |
|---|---|
| `SQL_ID` | Định danh câu SQL trong shared SQL area |
| `CHILD_NUMBER` | Số thứ tự child cursor dưới parent |
| `PLAN_HASH_VALUE` | Hash đại diện cho execution plan |
| `EXECUTIONS` | Số lần thực thi được ghi nhận cho child |
| `PARSE_CALLS` | Số lần parse được ghi nhận |
| `LOADS` | Số lần cursor được nạp vào shared pool theo bộ đếm của cursor |
| `INVALIDATIONS` | Số lần cursor bị invalidated theo bộ đếm |
| `IS_BIND_SENSITIVE` | Trạng thái theo dõi bind sensitivity |
| `IS_BIND_AWARE` | Trạng thái adaptive cursor sharing |

Các cột và cách diễn giải chi tiết có thể khác theo phiên bản. Với hệ thống RAC, dùng `GV$SQL` nếu cần tổng hợp cursor trên nhiều instance; nên thêm `INST_ID` vào kết quả để phân biệt instance.

### 7.2. V$SQLAREA: xem tổng quan parent cursor

`V$SQLAREA` tổng hợp thông tin ở mức câu SQL/parent cursor, hữu ích để xem `VERSION_COUNT`:

```sql
SELECT sql_id,
       version_count,
       executions,
       parse_calls,
       loads,
       invalidations
FROM v$sqlarea
WHERE sql_id = :sql_id;
```

Nếu `VERSION_COUNT` tăng cao, hãy xem các child cụ thể trong `V$SQL`, rồi điều tra nguyên nhân tạo nhiều phiên bản. Không nên xóa shared pool hoặc flush cursor chỉ để làm giảm con số này khi chưa hiểu nguyên nhân và ảnh hưởng.

### 7.3. V$SQL_SHARED_CURSOR: tìm lý do child không được chia sẻ

`V$SQL_SHARED_CURSOR` cung cấp thông tin về lý do một child cursor hiện có không thể được chia sẻ với lần parse mới và Oracle cần child khác. View này có các cột cờ cho nhiều nhóm mismatch, ví dụ liên quan đến bind, optimizer, authorization hoặc translation. Tên và tập cột có thể mở rộng theo phiên bản Oracle.

Có thể bắt đầu bằng:

```sql
SELECT *
FROM v$sql_shared_cursor
WHERE sql_id = :sql_id
ORDER BY child_number;
```

Đọc các cột cờ có giá trị `Y` và mô tả tương ứng trong tài liệu đúng phiên bản. Một số lý do có thể cùng xuất hiện; cần liên hệ child number, thời điểm parse và môi trường session để xác định nguyên nhân thực tế. Không nên kết luận chỉ dựa vào một cờ mà không đối chiếu bind metadata, optimizer environment và plan.

### 7.4. DBMS_XPLAN.DISPLAY_CURSOR: xem plan của child cụ thể

Sau khi xác định `SQL_ID` và `CHILD_NUMBER`, có thể xem execution plan:

```sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    :sql_id,
    :child_number,
    'TYPICAL +PREDICATE +ALIAS'
  )
);
```

Nếu đã thu thập runtime statistics, dùng format như `ALLSTATS LAST` để xem số liệu thực tế:

```sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    :sql_id,
    :child_number,
    'ALLSTATS LAST +PREDICATE +PEEKED_BINDS'
  )
);
```

`PEEKED_BINDS` thể hiện thông tin bind được peek khi parse trong phạm vi Oracle cung cấp, không phải bản ghi đầy đủ mọi bind value của tất cả lần thực thi. Cần cẩn trọng khi chia sẻ output vì bind values có thể chứa dữ liệu nhạy cảm.

Nếu không có quyền đọc các dynamic performance view hoặc thực thi `DBMS_XPLAN`, cần nhờ DBA cấp quyền phù hợp theo chính sách hệ thống.

## 8. Điều kiện để kế hoạch được tái sử dụng

Có thể nhóm điều kiện tái sử dụng child cursor thành bốn phần:

### 8.1. SQL text khớp với parent cursor

Oracle phải tìm được parent cursor phù hợp với SQL text được parse. Khác biệt literal, comment, khoảng trắng hoặc cách viết có thể tạo SQL text khác và dẫn đến SQL_ID/parent khác. Dùng bind variables nhất quán giúp nhiều lần gọi chia sẻ cùng một câu SQL.

### 8.2. Có child cursor tương thích

Child hiện có phải tương thích với lần parse mới. Bind datatype/length, optimizer environment, schema và quyền, object metadata, edition cùng các thuộc tính liên quan phải đáp ứng điều kiện chia sẻ của Oracle. Nếu không, Oracle có thể tạo child mới dù SQL_ID giống nhau.

### 8.3. Cursor còn trong library cache và hợp lệ

Child phải còn được lưu trong shared pool và chưa bị invalidated theo cách khiến nó không thể sử dụng. Áp lực bộ nhớ, DDL, thay đổi dependency hoặc statistics có thể làm cursor bị loại bỏ hoặc invalidated. Khi đó lần parse sau cần nạp lại, hard parse hoặc tạo child mới tùy tình trạng.

### 8.4. Plan hiện có vẫn được chấp nhận cho ngữ cảnh mới

Oracle phải xác định child/plan phù hợp với bind values và điều kiện tối ưu hóa. Với câu SQL bind-sensitive, ACS có thể chọn child khác cho một vùng selectivity khác. Vì vậy, tái sử dụng SQL_ID không đồng nghĩa mọi bind value phải dùng cùng child hoặc cùng plan hash.

## 9. SESSION_CACHED_CURSORS và statement cache

`SESSION_CACHED_CURSORS` điều khiển việc session cache các cursor đã được parse và đóng lặp lại, giúp giảm chi phí parse cho các câu SQL được dùng thường xuyên trong cùng session. JDBC/OCI và một số driver còn có statement cache ở phía client.

Các cơ chế này giúp giảm công việc tìm và parse lại cursor trong những tình huống phù hợp, nhưng không làm cho hai SQL text khác nhau trở thành cùng parent cursor và không loại bỏ các điều kiện tương thích của child cursor. Statement cache phía client cũng không thay thế shared pool: client giữ handle để tái sử dụng, còn Oracle vẫn quản lý parent/child cursor phía server.

Khi tối ưu ứng dụng, nên kết hợp:

- Dùng bind variables và giữ kiểu/độ dài bind nhất quán.
- Tái sử dụng prepared statement hoặc statement cache đúng cách.
- Tránh parse cùng SQL lặp đi lặp lại trong một luồng công việc nếu có thể giữ statement mở hợp lý.
- Theo dõi số hard parse, soft parse, child cursor và `VERSION_COUNT`.
- Không thay đổi tham số optimizer hoặc flush shared pool tùy tiện để xử lý triệu chứng.

## 10. Quy trình điều tra khi một SQL_ID có nhiều child cursor hoặc nhiều plan

1. Lấy SQL_ID của câu SQL thực tế từ ứng dụng hoặc công cụ giám sát.
2. Truy vấn `V$SQL` để liệt kê `CHILD_NUMBER`, `PLAN_HASH_VALUE`, `EXECUTIONS`, `PARSE_CALLS`, `LOADS` và `INVALIDATIONS`.
3. Kiểm tra `V$SQLAREA.VERSION_COUNT` để biết số child cursor đang được ghi nhận ở mức parent.
4. Nếu có nhiều child, xem `V$SQL_SHARED_CURSOR` để tìm mismatch reason; đối chiếu bind datatype/length, parsing schema, quyền, optimizer environment và object metadata.
5. Dùng `DBMS_XPLAN.DISPLAY_CURSOR` với từng child number để so sánh operation, predicate, estimated rows và runtime statistics.
6. Nếu câu SQL dùng bind variable, kiểm tra `IS_BIND_SENSITIVE`, `IS_BIND_AWARE` và xem liệu các nhóm bind values có selectivity khác nhau hay không.
7. Kiểm tra cursor có bị invalidated hoặc aged out, statistics có thay đổi, và ứng dụng có đang gửi SQL text khác nhau do literal hoặc cách sinh câu lệnh hay không.
8. Chỉ thay đổi SQL, bind metadata, statistics, index hoặc cấu hình cache sau khi đã xác định nguyên nhân; đo lại hard parse, số child, plan và hiệu năng sau thay đổi.

Không nên mặc định xóa shared pool, ép một plan hoặc tắt bind peeking/ACS chỉ vì thấy nhiều child cursor. Nhiều child có thể là kết quả đúng của các ngữ cảnh thực thi khác nhau; mục tiêu là loại bỏ child không cần thiết và giữ plan phù hợp với workload.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c Reference — V$SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL.html)
- [Oracle Database 19c Reference — V$SQLAREA](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQLAREA.html)
- [Oracle Database 19c Reference — V$SQL_SHARED_CURSOR](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/V-SQL_SHARED_CURSOR.html)
- [Oracle Database 19c SQL Tuning Guide — Adaptive Cursor Sharing](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/improving-rwp-cursor-sharing.html)
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html)
