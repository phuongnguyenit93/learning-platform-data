# Bind peeking, adaptive cursor sharing và nhiều child cursor

## 1. Vì sao một câu SQL có thể cần nhiều execution plan?

Ứng dụng thường gửi cùng một câu SQL nhiều lần nhưng truyền các giá trị bind khác nhau. Ví dụ:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = :status;
```

Giả sử bảng `orders` có phân bố dữ liệu lệch mạnh:

- Chỉ một phần rất nhỏ đơn hàng có `status = 'CANCELLED'`.
- Phần lớn đơn hàng có `status = 'COMPLETED'`.

Với giá trị hiếm, Oracle có thể đọc một vài bản ghi qua index rồi truy cập bảng. Với giá trị phổ biến, đọc nhiều block bằng full table scan có thể rẻ hơn. Cùng một predicate nhưng lượng dữ liệu cần xử lý khác nhau, vì vậy execution plan tốt cho giá trị này chưa chắc tốt cho giá trị khác.

Bind variable giúp ứng dụng tái sử dụng câu SQL và giảm hard parse. Tuy nhiên, nếu mọi giá trị bind đều phải dùng chung một plan thì sự khác biệt về phân bố dữ liệu có thể khiến một số lần chạy kém hiệu quả. Oracle giải quyết bài toán này bằng cơ chế bind peeking và, từ Oracle Database 11g, adaptive cursor sharing (ACS). Kết quả có thể là một parent cursor có nhiều child cursor, mỗi child phục vụ một nhóm điều kiện thực thi phù hợp.

## 2. Bind variable và vòng đời cursor

Bind variable là placeholder trong câu SQL. Ứng dụng truyền giá trị riêng khi thực thi thay vì ghép giá trị trực tiếp vào chuỗi SQL:

```sql
SELECT *
FROM employees
WHERE department_id = :department_id;
```

Khi dùng bind variable đúng cách:

- Câu SQL có thể được tái sử dụng giữa nhiều lần gọi.
- Oracle giảm số lần phải phân tích cú pháp và tối ưu hóa hoàn toàn.
- Ứng dụng tránh phải tạo một chuỗi SQL mới cho từng giá trị dữ liệu.
- Việc truyền dữ liệu dưới dạng bind giúp chống SQL injection đối với các giá trị được bind đúng cách.

Trong library cache, cần phân biệt hai khái niệm:

| Thành phần | Ý nghĩa |
|---|---|
| Parent cursor | Đại diện cho câu SQL đã được nhận diện trong library cache. Các child cursor tương ứng được quản lý bên dưới parent. |
| Child cursor | Một phiên bản có thể thực thi của parent cursor, gắn với thông tin môi trường, bind metadata và execution plan cụ thể. |

Một SQL text được bind nhất quán thường có cùng SQL ID. Dưới SQL ID đó, Oracle có thể lưu nhiều child cursor với các `CHILD_NUMBER` khác nhau. Mỗi child có thể có `PLAN_HASH_VALUE` riêng; trong một số trường hợp nhiều child vẫn dùng cùng plan hash nhưng tồn tại vì lý do tương thích hoặc môi trường.

### Hard parse và soft parse

**Hard parse** xảy ra khi Oracle phải tạo hoặc tối ưu một cursor mới vì không tìm được child cursor có thể chia sẻ phù hợp. Công việc có thể bao gồm phân tích cú pháp, kiểm tra quyền, phân giải đối tượng, ước lượng cardinality và chọn execution plan.

**Soft parse** xảy ra khi Oracle tìm được cursor phù hợp trong library cache và có thể tái sử dụng. Soft parse vẫn có chi phí kiểm tra và tìm cursor; nó không đồng nghĩa với việc hoàn toàn không có công việc parse.

Bind variable thường giúp nhiều lần gọi cùng câu SQL đi qua đường tái sử dụng cursor. Nhưng việc chia sẻ chỉ xảy ra khi các điều kiện tương thích được đáp ứng. Khác biệt về kiểu dữ liệu bind, độ dài bind, optimizer environment, quyền truy cập hoặc trạng thái đối tượng có thể khiến Oracle không thể dùng chung một child cursor.

## 3. Bind peeking hoạt động như thế nào?

Bind peeking là cơ chế Oracle xem giá trị bind có sẵn tại thời điểm hard parse để optimizer dùng giá trị đó khi ước lượng selectivity và cardinality.

Ví dụ:

```sql
SELECT order_id
FROM orders
WHERE status = :status;
```

Giả sử ứng dụng thực hiện hard parse lần đầu với `:status = 'CANCELLED'`. Nếu thống kê và histogram cho optimizer biết giá trị này rất hiếm, optimizer có thể chọn index range scan. Child cursor được tạo từ lần tối ưu hóa đó có thể tiếp tục được tái sử dụng khi câu SQL chạy với `:status = 'COMPLETED'`.

Ở lần thực thi sau, Oracle thường không hard parse lại chỉ để xem giá trị bind mới. Vì thế, plan được chọn khi parse ban đầu có thể không còn phù hợp với một giá trị có selectivity rất khác.

### Vai trò của thống kê và histogram

Optimizer dựa vào thống kê để ước lượng số dòng và chi phí của các phương án. Thống kê cơ bản có thể mô tả số dòng, số block, số giá trị phân biệt và mức độ null. Histogram bổ sung thông tin về phân bố giá trị của một cột, giúp optimizer nhận biết các giá trị phổ biến và hiếm.

Khi dữ liệu phân bố tương đối đồng đều, một ước lượng selectivity chung có thể đủ tốt. Khi dữ liệu lệch mạnh, histogram có thể giúp optimizer ước lượng chính xác hơn cho giá trị bind được peek.

Có thể yêu cầu Oracle đánh giá histogram cho một cột bằng `DBMS_STATS`:

```sql
BEGIN
  DBMS_STATS.GATHER_TABLE_STATS(
    ownname    => USER,
    tabname    => 'ORDERS',
    method_opt => 'FOR COLUMNS SIZE AUTO STATUS',
    cascade    => TRUE
  );
END;
/
```

`SIZE AUTO` cho phép Oracle quyết định histogram dựa trên thông tin sử dụng cột và chính sách thống kê. Lệnh trên là ví dụ minh họa; trước khi thu thập lại thống kê trên hệ thống thật cần đánh giá lịch thu thập, mức độ thay đổi dữ liệu và ảnh hưởng của việc cập nhật thống kê đến plan hiện tại.

Histogram không tự động làm mọi truy vấn nhanh hơn. Nó có thể giúp optimizer phân biệt các giá trị có selectivity khác nhau, nhưng cũng có thể làm plan thay đổi khi giá trị bind được peek khác nhau. Cần đánh giá histogram cùng workload thực tế.

### Rủi ro khi chỉ dựa vào bind peeking

Với dữ liệu lệch, kết quả có thể phụ thuộc vào giá trị bind xuất hiện ở lần hard parse:

| Giá trị được peek lúc hard parse | Plan có thể được chọn | Rủi ro khi tái sử dụng |
|---|---|---|
| Giá trị hiếm | Index range scan | Giá trị phổ biến có thể phải đọc quá nhiều row qua index và table lookup. |
| Giá trị phổ biến | Full table scan | Giá trị hiếm có thể phải quét nhiều block dù chỉ cần rất ít row. |

Đây là lý do một câu SQL đôi khi nhanh ở thời điểm này nhưng chậm ở thời điểm khác dù ứng dụng chỉ thay đổi bind value. Không nên kết luận ngay rằng index bị lỗi hoặc bind variable là nguyên nhân duy nhất; cần kiểm tra plan thực tế, thống kê, bind metadata và các lần hard parse.

## 4. Adaptive cursor sharing (ACS)

Adaptive cursor sharing được giới thiệu từ Oracle Database 11g để xử lý trường hợp một câu SQL có bind variable nhưng các giá trị bind tạo ra selectivity khác biệt đáng kể.

ACS cho phép Oracle quan sát hành vi thực thi và dần nhận biết cursor nào nhạy với giá trị bind. Khi có đủ bằng chứng rằng các nhóm giá trị cần cách tối ưu khác nhau, Oracle có thể tạo các child cursor phù hợp với các vùng selectivity khác nhau.

### Các trạng thái thường gặp

Oracle hiển thị hai cờ quan trọng trong `V$SQL`:

- `IS_BIND_SENSITIVE = 'Y'`: cursor được theo dõi vì giá trị bind có thể ảnh hưởng đến selectivity hoặc hiệu quả thực thi.
- `IS_BIND_AWARE = 'Y'`: Oracle đã nhận biết các vùng selectivity khác nhau có thể cần child cursor riêng.

Hai cờ này không phải cam kết rằng mỗi giá trị bind sẽ có một plan riêng. Chúng cho biết trạng thái xử lý của cursor tại thời điểm quan sát.

### Luồng hoạt động khái quát

1. Ứng dụng gửi câu SQL có bind variable. Oracle hard parse và có thể peek giá trị bind hiện tại để chọn plan ban đầu.
2. Nếu predicate phù hợp, Oracle đánh dấu cursor là bind-sensitive và theo dõi các lần thực thi.
3. Oracle thu thập thông tin về selectivity và hiệu quả thực thi của các nhóm giá trị bind.
4. Khi nhận thấy các giá trị có hành vi khác biệt đủ đáng kể, Oracle có thể chuyển cursor sang bind-aware.
5. Oracle có thể tạo thêm child cursor cho các vùng selectivity khác nhau. Những lần thực thi sau được đối chiếu với vùng phù hợp để tái sử dụng child tương ứng.

Đây là cơ chế thích nghi dựa trên quan sát, không phải thao tác tạo ngay một child cursor cho từng bind value. Việc chuyển trạng thái và tạo child phụ thuộc vào workload, thống kê, phiên bản, cấu hình optimizer và bằng chứng thu thập được. Một cursor bind-sensitive không nhất thiết sẽ trở thành bind-aware trong mọi trường hợp.

### Vì sao ACS hữu ích?

Quay lại truy vấn:

```sql
SELECT order_id
FROM orders
WHERE status = :status;
```

Oracle có thể dần nhận ra hai vùng selectivity:

- Nhóm giá trị hiếm: chỉ trả về ít dòng, phù hợp với index access.
- Nhóm giá trị phổ biến: trả về nhiều dòng, có thể phù hợp với full scan.

Khi đã có các child cursor thích hợp, giá trị bind thuộc cùng một vùng selectivity có thể dùng chung child. Oracle không cần tạo một child mới cho mỗi giá trị cụ thể. Điều này cân bằng hai mục tiêu: tái sử dụng cursor và chọn plan phù hợp với phân bố dữ liệu.

ACS không đảm bảo mọi lần chạy đều có plan tối ưu tuyệt đối. Nó cần thời gian và dữ liệu thực thi để nhận biết hành vi; một truy vấn ít được gọi có thể không tạo đủ bằng chứng. Các thay đổi thống kê hoặc môi trường cũng có thể làm plan và child cursor thay đổi.

## 5. Vì sao một SQL ID có nhiều child cursor?

Nhiều child cursor có thể xuất hiện vì hai nhóm nguyên nhân chính:

1. **Khác biệt về selectivity và plan:** ACS tạo hoặc duy trì child cursor để phục vụ các vùng bind khác nhau.
2. **Không tương thích khi chia sẻ cursor:** Oracle cần child riêng vì metadata, môi trường hoặc trạng thái thực thi không giống nhau.

Một số nguyên nhân phổ biến:

| Nguyên nhân | Ví dụ | Hướng kiểm tra |
|---|---|---|
| Bind metadata khác nhau | Ứng dụng lúc bind `VARCHAR2`, lúc bind `NVARCHAR2`; độ dài hoặc kiểu dữ liệu bind không nhất quán. | Kiểm tra cách driver khai báo bind và cờ `BIND_MISMATCH`. |
| Optimizer environment khác nhau | Các session có `OPTIMIZER_MODE`, tham số optimizer hoặc môi trường NLS khác nhau. | So sánh optimizer environment và cờ `OPTIMIZER_MISMATCH`, `LANGUAGE_MISMATCH`. |
| Quyền hoặc schema khác nhau | Các session phân giải đối tượng hoặc kiểm tra quyền theo ngữ cảnh khác nhau. | Kiểm tra schema parse, quyền và cờ liên quan đến authorization. |
| Thông tin đối tượng hoặc thống kê thay đổi | DDL, invalidation hoặc cập nhật thống kê làm cursor cũ không còn phù hợp. | Kiểm tra invalidation, load và lịch thay đổi đối tượng/thống kê. |
| ACS cần vùng selectivity khác | Bind value mới không tương đương với vùng selectivity của child hiện có. | Kiểm tra `IS_BIND_SENSITIVE`, `IS_BIND_AWARE` và `BIND_EQUIV_FAILURE` nếu phiên bản có cột này. |

Do đó, **nhiều child cursor không mặc nhiên là lỗi**. Nhiều child có plan khác nhau có thể là hành vi mong muốn của ACS. Ngược lại, rất nhiều child có cùng plan nhưng khác bind metadata hoặc optimizer environment có thể cho thấy ứng dụng đang tạo ra các ngữ cảnh parse thiếu nhất quán.

Số lượng child cao kéo dài có thể làm tăng bộ nhớ library cache, chi phí parse và áp lực đồng bộ khi nhiều session cùng truy cập cursor. Tuy vậy, chỉ nhìn số child chưa đủ để quyết định phải can thiệp; cần xem nguyên nhân tạo child, tần suất thực thi, plan hash và chi phí thực tế.

## 6. Quan sát bind peeking và child cursor

Các view động sau thường hữu ích khi điều tra:

| View | Thông tin chính |
|---|---|
| `V$SQL` | Một dòng cho mỗi child cursor đang được cache; có SQL ID, child number, plan hash, executions và cờ bind-sensitive/bind-aware. |
| `V$SQLAREA` | Thông tin tổng hợp theo parent SQL, trong đó có `VERSION_COUNT` để xem số child version. |
| `V$SQL_SHARED_CURSOR` | Các cờ giải thích vì sao một child cursor không thể chia sẻ với child khác. |
| `V$SQL_CS_SELECTIVITY` | Các vùng selectivity được ACS theo dõi cho cursor. |
| `V$SQL_CS_STATISTICS` | Thống kê thực thi được ACS dùng khi đánh giá hành vi bind. |
| `V$SQL_CS_HISTOGRAM` | Thông tin histogram nội bộ liên quan đến các lần thực thi được ACS theo dõi. |
| `V$SQL_BIND_CAPTURE` | Các bind value được capture theo cơ chế lấy mẫu; không phải nhật ký đầy đủ của mọi lần thực thi. |

Các view `V$` phản ánh trạng thái trong instance và library cache hiện tại. Cursor có thể bị aging out hoặc invalidation, vì vậy dữ liệu quan sát được có giới hạn theo vòng đời cache. Trong môi trường RAC có thể cần dùng các view `GV$` và đối chiếu `INST_ID`; trong môi trường multitenant cần chú ý `CON_ID`.

### Xem các child cursor của một SQL ID

```sql
SELECT sql_id,
       child_number,
       plan_hash_value,
       executions,
       parse_calls,
       is_bind_sensitive,
       is_bind_aware,
       is_shareable
FROM   v$sql
WHERE  sql_id = :sql_id
ORDER BY child_number;
```

Khi đọc kết quả:

- So sánh `PLAN_HASH_VALUE` để xem các child có đang dùng plan khác nhau không.
- So sánh `EXECUTIONS` và `PARSE_CALLS` để hiểu mức độ sử dụng.
- Xem `IS_BIND_SENSITIVE` và `IS_BIND_AWARE` để biết Oracle đang xử lý bind sharing như thế nào.
- Kiểm tra `IS_SHAREABLE`; child không shareable có thể không còn được chọn cho lần thực thi mới.

Có thể xem số phiên bản child ở mức parent:

```sql
SELECT sql_id,
       version_count,
       executions,
       parse_calls
FROM   v$sqlarea
WHERE  sql_id = :sql_id;
```

`VERSION_COUNT` cao là tín hiệu để điều tra, không phải kết luận rằng hệ thống đang có lỗi.

### Xem lý do child cursor không chia sẻ

```sql
SELECT child_number,
       bind_mismatch,
       optimizer_mismatch,
       auth_check_mismatch,
       language_mismatch,
       translation_mismatch
FROM   v$sql_shared_cursor
WHERE  sql_id = :sql_id
ORDER BY child_number;
```

Các cột của `V$SQL_SHARED_CURSOR` có thể khác theo phiên bản Oracle. Hãy đối chiếu data dictionary của phiên bản đang chạy trước khi dùng một danh sách cột cố định trong script vận hành. Giá trị cờ giúp khoanh vùng nguyên nhân; cần kết hợp với thông tin bind từ ứng dụng và môi trường session để xác nhận.

Nếu phiên bản cung cấp cột `BIND_EQUIV_FAILURE`, cờ này có thể giúp nhận biết trường hợp bind value không tương đương với vùng selectivity mà child cursor hiện tại phục vụ. Đây là dấu hiệu liên quan đến ACS, khác với `BIND_MISMATCH` vốn chỉ ra khác biệt về metadata bind.

### Xem execution plan thực tế và bind được peek

```sql
SELECT *
FROM TABLE(
  DBMS_XPLAN.DISPLAY_CURSOR(
    :sql_id,
    :child_number,
    'ALLSTATS LAST +PEEKED_BINDS +PREDICATE'
  )
);
```

`DISPLAY_CURSOR` hiển thị plan của child cursor trong cache. `+PEEKED_BINDS` yêu cầu hiển thị bind value được peek khi tối ưu hóa cursor, nếu thông tin đó có sẵn. Giá trị này không nhất thiết là bind value của lần thực thi gần nhất.

`ALLSTATS LAST` hữu ích để so sánh số dòng ước lượng và số dòng thực tế, nhưng cần có runtime plan statistics. Có thể thu thập cho một lần chạy kiểm soát bằng hint `/*+ GATHER_PLAN_STATISTICS */` hoặc cấu hình thống kê phù hợp. Không nên bật thu thập chi tiết trên diện rộng mà chưa đánh giá overhead.

`V$SQL_BIND_CAPTURE` cũng không lưu mọi giá trị của mọi lần thực thi. Đây là dữ liệu capture có lấy mẫu, nên không dùng nó như một audit log đầy đủ của bind variables. Bind value có thể chứa dữ liệu nhạy cảm; cần hạn chế quyền truy cập và tránh đưa giá trị thật vào báo cáo không được bảo vệ.

### Xem thông tin ACS

Khi cần điều tra sâu hơn, có thể lọc các view `V$SQL_CS_*` theo SQL ID và child number:

```sql
SELECT *
FROM   v$sql_cs_selectivity
WHERE  sql_id = :sql_id
ORDER BY child_number, range_id;

SELECT *
FROM   v$sql_cs_histogram
WHERE  sql_id = :sql_id
ORDER BY child_number, bucket_id;
```

Các view này cho biết cách Oracle theo dõi vùng selectivity và số lần thực thi trong các bucket. Đây là thông tin phục vụ chẩn đoán cơ chế thích nghi; không nên dựa vào một bucket đơn lẻ để kết luận plan nào tốt hơn. Cần đối chiếu với actual rows, buffer gets, elapsed time và workload.

## 7. Quy trình điều tra một truy vấn chạy lúc nhanh lúc chậm

Khi cùng SQL ID có thời gian chạy biến động theo bind value, có thể đi theo trình tự sau:

1. **Xác định đúng SQL ID và phạm vi instance.** Ghi nhận câu SQL, module/action của ứng dụng nếu có, thời điểm chạy và các bind value đại diện. Không ghi log dữ liệu nhạy cảm không cần thiết.
2. **Liệt kê child cursor.** Thu thập `CHILD_NUMBER`, `PLAN_HASH_VALUE`, số lần thực thi, số lần parse và các cờ bind-sensitive/bind-aware.
3. **So sánh plan thực tế.** Dùng `DBMS_XPLAN.DISPLAY_CURSOR` cho từng child. Kiểm tra operation, predicate, access path, estimated rows và actual rows.
4. **So sánh nhóm bind value.** Chọn giá trị phổ biến, hiếm và các giá trị trung gian từ workload thực tế. Kiểm tra kiểu dữ liệu, độ dài và cách driver bind.
5. **Kiểm tra thống kê.** Xem thống kê bảng/cột/index có mới và đại diện cho dữ liệu hiện tại không; xác định histogram có phù hợp với độ lệch dữ liệu và predicate không.
6. **Tìm nguyên nhân child mới.** Đọc các cờ trong `V$SQL_SHARED_CURSOR`; phân biệt child do ACS với child do bind metadata hoặc optimizer environment không tương thích.
7. **Đánh giá chi phí theo workload.** So sánh elapsed time, CPU, buffer gets, số dòng thực tế và tần suất từng nhóm bind. Plan có cost thấp hơn trong một lần chạy chưa chắc làm workload tổng thể tốt hơn.
8. **Thử biện pháp trong môi trường kiểm soát.** Thay đổi thống kê, bind metadata hoặc chính sách plan từng bước; đo lại trên các nhóm bind đại diện trước khi triển khai.

Ví dụ, nếu child 0 dùng index range scan và hoạt động tốt với giá trị hiếm, trong khi child 1 dùng full table scan và hoạt động tốt với giá trị phổ biến, đây có thể là kết quả hợp lý của ACS. Nếu hàng chục child được tạo nhưng plan hash giống nhau và cờ `BIND_MISMATCH` xuất hiện, cần ưu tiên sửa cách ứng dụng bind dữ liệu nhất quán.

## 8. Biện pháp xử lý và những điều cần tránh

### Giữ bind metadata nhất quán

Ứng dụng nên bind cùng một tham số với kiểu dữ liệu và quy tắc độ dài ổn định. Ví dụ, không nên lúc truyền một chuỗi bằng `VARCHAR2`, lúc khác lại bằng `NVARCHAR2` nếu nghiệp vụ và schema không yêu cầu điều đó. Tránh implicit conversion trên cột được lọc vì conversion có thể ảnh hưởng khả năng dùng index và ước lượng cardinality.

### Duy trì thống kê phù hợp

Thu thập thống kê theo lịch và chính sách phù hợp với tốc độ thay đổi dữ liệu. Chỉ dùng histogram khi phân bố dữ liệu và workload cho thấy optimizer cần thông tin đó. Sau khi cập nhật thống kê, kiểm tra các truy vấn quan trọng với nhiều nhóm bind value vì plan có thể thay đổi.

### Để ACS làm công việc thích nghi trước khi can thiệp thủ công

ACS được thiết kế để xử lý trường hợp selectivity của bind khác nhau. Trước khi tắt bind peeking, vô hiệu hóa ACS hoặc áp dụng một plan cố định, hãy xác định Oracle đã tạo các child phù hợp hay chưa và chi phí thực tế của từng child. Các tham số ẩn không phải công cụ điều chỉnh thông thường; không nên thay đổi chúng chỉ để xử lý một SQL chậm.

### Dùng SQL Plan Management khi cần kiểm soát plan

Nếu một hệ thống cần giới hạn thay đổi plan sau nâng cấp hoặc thay đổi thống kê, SQL Plan Management (SPM) có thể giúp quản lý và kiểm soát các plan được chấp nhận. Tuy nhiên, baseline không thay thế việc hiểu selectivity của bind. Cần đánh giá cách baseline tương tác với các child cursor và workload cụ thể trước khi áp dụng.

### Không ép mọi trường hợp dùng chung một plan

Một index plan có thể tốt cho giá trị hiếm nhưng rất tốn kém cho giá trị phổ biến; full scan có thể có đặc tính ngược lại. Ép một plan duy nhất có thể làm một nhóm bind nhanh hơn nhưng khiến nhóm khác chậm đi. Chỉ dùng hint, SQL Patch, baseline hoặc thay đổi SQL sau khi đã đo trên các trường hợp đại diện và xác định rõ mục tiêu vận hành.

### Không coi số child cursor là chỉ số sức khỏe độc lập

Nhiều child cursor có thể là kết quả đúng của ACS. Điều cần quan tâm là child được tạo vì lý do gì, có được tái sử dụng không, plan có phù hợp với bind tương ứng không và chi phí parse/library cache có đáng kể không. Chỉ xóa cursor khỏi shared pool hoặc flush shared pool thường không giải quyết nguyên nhân gốc và có thể gây thêm hard parse trên diện rộng.

## 9. Phân biệt các khái niệm dễ nhầm

| Khái niệm | Điều nó mô tả | Không có nghĩa là |
|---|---|---|
| Bind peeking | Optimizer xem bind value tại thời điểm hard parse để ước lượng và chọn plan. | Oracle thay bind value vào SQL text ở mọi lần chạy. |
| Bind-sensitive | Cursor có bind predicate mà selectivity có thể ảnh hưởng đến hiệu quả; Oracle theo dõi hành vi. | Cursor chắc chắn đã có nhiều plan. |
| Bind-aware | Oracle đã nhận biết các vùng selectivity cần được xử lý bằng child cursor phù hợp. | Mỗi bind value có một child cursor riêng. |
| Child cursor | Một phiên bản cursor cụ thể bên dưới parent cursor. | Mọi child đều được tạo bởi ACS hoặc đều có plan khác nhau. |
| Bind capture | Một số bind value được Oracle capture theo cơ chế lấy mẫu. | Có đầy đủ lịch sử bind value của mọi execution. |
| Adaptive cursor sharing | Cơ chế chọn và chia sẻ child cursor theo vùng selectivity của bind. | Adaptive execution plan nói chung hoặc một bảo đảm rằng mọi truy vấn sẽ tự tối ưu hoàn hảo. |

## 10. Checklist khi vận hành

- [ ] Xác nhận ứng dụng dùng bind variable và bind đúng kiểu dữ liệu.
- [ ] Xác định SQL ID, instance và thời điểm có vấn đề.
- [ ] Kiểm tra số child cursor, plan hash và trạng thái bind-sensitive/bind-aware.
- [ ] So sánh execution plan cùng actual rows và buffer gets của từng child.
- [ ] Kiểm tra histogram, thống kê bảng/cột/index và thời điểm thu thập.
- [ ] Đọc lý do không chia sẻ child trong `V$SQL_SHARED_CURSOR`.
- [ ] Đánh giá các nhóm bind value đại diện cho workload thật.
- [ ] Chỉ thay đổi thống kê hoặc chính sách plan sau khi có phép đo trước/sau.

## Kết luận

Bind peeking giúp optimizer sử dụng giá trị bind tại thời điểm hard parse để chọn plan có cơ sở hơn. Khi phân bố dữ liệu lệch, một plan được chọn từ giá trị đầu tiên có thể không phù hợp với mọi lần thực thi. Adaptive cursor sharing giúp Oracle quan sát selectivity và có thể tạo nhiều child cursor cho các nhóm bind khác nhau. Vì vậy, nhiều child cursor đôi khi là dấu hiệu của tối ưu hóa thích nghi đang hoạt động đúng.

Khi điều tra, hãy kết hợp SQL ID, child number, plan hash, cờ bind-sensitive/bind-aware, lý do không chia sẻ cursor, bind metadata, thống kê và runtime plan statistics. Chỉ sau khi xác định được nguyên nhân mới chọn biện pháp như chuẩn hóa cách bind, cập nhật thống kê, điều chỉnh SQL hoặc quản lý plan.
