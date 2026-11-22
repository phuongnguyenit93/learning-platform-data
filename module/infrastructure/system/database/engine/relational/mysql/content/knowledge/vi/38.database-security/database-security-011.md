# DEFINER/INVOKER và rủi ro quyền vượt phạm vi qua stored object

Trong MySQL, một tài khoản có thể được phép gọi một view hoặc stored procedure mà không được cấp quyền trực tiếp trên các bảng bên dưới. Cơ chế này hữu ích khi muốn công bố một giao diện dữ liệu hẹp, nhưng cũng tạo ra rủi ro: stored object có thể thực hiện thao tác bằng quyền của một tài khoản mạnh hơn người gọi.

Hai khái niệm cần phân biệt là **DEFINER** và **INVOKER**. `DEFINER` xác định tài khoản làm cơ sở kiểm tra quyền khi object chạy trong ngữ cảnh definer. `INVOKER` dùng quyền của tài khoản đang gọi object. Lựa chọn này quyết định một lời gọi SQL có thể chạm tới những bảng và dữ liệu nào, vì vậy cần được xem là một phần của thiết kế bảo mật MySQL.

## 1. DEFINER và SQL SECURITY là gì?

Một stored object có thể lưu thông tin về tài khoản định nghĩa nó. Tài khoản này được ghi theo cặp `user` và `host`, ví dụ `'report_owner'@'localhost'`; chỉ so sánh tên user là chưa đủ để xác định đúng tài khoản. Tài khoản trong mệnh đề `DEFINER` cũng không nhất thiết là người đã tạo object.

Với view, stored procedure và stored function, mệnh đề `SQL SECURITY` chọn ngữ cảnh quyền thực thi:

| Chế độ | Ngữ cảnh kiểm tra quyền trên đối tượng được tham chiếu | Ý nghĩa |
|---|---|---|
| `SQL SECURITY DEFINER` | Tài khoản được ghi trong `DEFINER` | Người gọi có thể sử dụng quyền mà definer được cấp thông qua object, dù bản thân họ không có quyền trực tiếp trên bảng bên dưới. |
| `SQL SECURITY INVOKER` | Tài khoản đang gọi object | Người gọi phải có các quyền cần thiết trên những đối tượng mà câu lệnh truy cập. |

Nếu không ghi `SQL SECURITY`, view và stored routine mặc định dùng `DEFINER`. Nên khai báo tường minh để người đọc DDL và người review migration nhìn thấy quyết định bảo mật ngay tại định nghĩa object.

Trigger và event cũng có `DEFINER`, nhưng luôn thực thi trong ngữ cảnh definer; cú pháp của chúng không cung cấp lựa chọn `SQL SECURITY INVOKER`. Đây là điểm quan trọng khi đánh giá các thao tác tự động: một câu `INSERT`, `UPDATE` hoặc `DELETE` của ứng dụng có thể kích hoạt trigger chạy với quyền của một tài khoản khác.

## 2. Quyền được kiểm tra như thế nào?

Hãy hình dung một tài khoản ứng dụng gọi `reporting.open_orders`:

1. MySQL xác thực kết nối và xác định tài khoản gọi.
2. MySQL kiểm tra người gọi có quyền sử dụng object hay không, chẳng hạn `SELECT` trên view hoặc `EXECUTE` trên procedure.
3. MySQL xác định ngữ cảnh bảo mật theo `SQL SECURITY`.
4. Khi câu lệnh bên trong object truy cập bảng hoặc object khác, MySQL kiểm tra quyền theo ngữ cảnh đã chọn.

Với `SQL SECURITY DEFINER`, người gọi vẫn cần quyền trên chính view hoặc routine. Tuy nhiên, quyền đọc hoặc sửa các bảng được tham chiếu đến từ definer. Đây là cách đóng gói một thao tác có kiểm soát: ứng dụng chỉ được gọi một routine đã cấp quyền, thay vì được cấp trực tiếp quyền `UPDATE` trên toàn bộ bảng.

Với `SQL SECURITY INVOKER`, quyền của definer không được dùng để nâng quyền cho lời gọi. Người gọi cần có quyền phù hợp trên các bảng và object được truy cập, bên cạnh quyền cần thiết để gọi view hoặc routine.

Trigger và event có luồng khác: trigger chạy khi thao tác trên bảng kích hoạt nó; event chạy theo lịch khi Event Scheduler thực thi event. Cả hai dùng quyền definer. Vì vậy, khi cấp quyền ghi trên một bảng có trigger, cần đánh giá cả phần thân trigger và các bảng mà trigger có thể đọc hoặc ghi.

## 3. Dùng DEFINER có chủ đích cho view

Giả sử dữ liệu đơn hàng nằm trong schema `sales`. Tài khoản báo cáo chỉ cần xem danh sách đơn đang mở; nó không cần quyền đọc toàn bộ bảng đơn hàng.

Tạo tài khoản definer chuyên biệt và cấp đúng quyền đọc cần thiết:

```sql
CREATE USER 'report_owner'@'localhost' IDENTIFIED BY 'replace-with-a-managed-secret';

GRANT SELECT ON sales.orders
TO 'report_owner'@'localhost';
```

Tạo view dùng quyền của tài khoản đó:

```sql
CREATE DEFINER = 'report_owner'@'localhost'
SQL SECURITY DEFINER
VIEW reporting.open_orders AS
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM sales.orders
WHERE status = 'OPEN';
```

Sau đó chỉ cấp quyền đọc view cho tài khoản báo cáo:

```sql
GRANT SELECT ON reporting.open_orders
TO 'report_reader'@'%';
```

Nếu `report_reader` không có quyền khác trên `sales.orders`, họ có thể truy vấn view nhưng không thể tự truy vấn bảng gốc. Cách này tạo một bề mặt truy cập nhỏ hơn. Tuy nhiên, view chỉ an toàn khi câu truy vấn thực sự giới hạn đúng cột và hàng cần công bố, đồng thời các quyền khác của người dùng không cho phép họ đi vòng qua view.

Nếu chuyển view sang `SQL SECURITY INVOKER`, người gọi phải có quyền cần thiết trên `sales.orders` để câu truy vấn bên trong view chạy được. Vì vậy, hãy chọn `INVOKER` khi mục tiêu là giữ nguyên quyền của người gọi; chọn `DEFINER` khi muốn công bố một giao diện hẹp bằng quyền tối thiểu của một tài khoản chuyên dụng.

`WITH CHECK OPTION` có thể giới hạn thao tác ghi qua một view có thể cập nhật để hàng được ghi vẫn thỏa điều kiện của view. Nó không thay thế thiết kế phân quyền, và không tự tạo ra chính sách kiểm soát hàng cho mọi đường truy cập vào bảng.

## 4. Stored procedure như một cổng thao tác có quyền cao

Stored procedure `SQL SECURITY DEFINER` có thể thực hiện một thao tác mà người gọi không được phép thực hiện trực tiếp. Ví dụ, một procedure nội bộ đọc bảng lương:

```sql
CREATE DEFINER = 'payroll_owner'@'localhost'
PROCEDURE hr.read_payroll()
SQL SECURITY DEFINER
BEGIN
    SELECT employee_id, salary
    FROM hr.payroll;
END;
```

Tài khoản ứng dụng có thể được cấp quyền gọi procedure:

```sql
GRANT EXECUTE ON PROCEDURE hr.read_payroll
TO 'hr_report_user'@'10.%';
```

Người gọi không cần quyền `SELECT` trực tiếp trên `hr.payroll`, nhưng họ vẫn có thể nhận toàn bộ kết quả mà procedure trả về. Vì vậy, `GRANT EXECUTE` chính là một quyết định cấp quyền dữ liệu. Nếu procedure không lọc theo phạm vi công việc của người gọi, cấp `EXECUTE` quá rộng có thể làm lộ dữ liệu nhạy cảm.

Một procedure có quyền `DEFINER` cần kiểm tra các điều kiện nghiệp vụ bên trong: người gọi được xem hoặc sửa bản ghi nào, trạng thái nào được phép chuyển, số lượng và phạm vi tham số có hợp lệ không. Không nên tin một `actor_id`, `tenant_id` hoặc `role` do client tự gửi lên như bằng chứng về danh tính hay quyền hạn. Với ứng dụng dùng chung một tài khoản kết nối cho nhiều người, MySQL chỉ nhìn thấy tài khoản kết nối dùng chung; việc xác thực người dùng cuối cần được ràng buộc qua một cơ chế ứng dụng đáng tin cậy.

## 5. Các cách quyền vượt phạm vi xuất hiện

| Tình huống | Cơ chế gây rủi ro | Hậu quả có thể xảy ra |
|---|---|---|
| Definer có quyền quá rộng | View hoặc routine chạy bằng tài khoản có quyền trên nhiều schema, thậm chí dùng tài khoản quản trị | Người được cấp quyền gọi object có thể gián tiếp đọc hoặc sửa nhiều dữ liệu hơn nhu cầu. |
| Cấp `EXECUTE` quá rộng | Procedure `DEFINER` công bố thao tác nhạy cảm cho nhiều tài khoản hoặc role | Người gọi có thể dùng procedure như một cổng truy cập vào dữ liệu hay thao tác đặc quyền. |
| Dynamic SQL không an toàn | Routine ghép chuỗi đầu vào thành câu SQL rồi chạy trong ngữ cảnh definer | SQL injection có thể biến đầu vào thành câu lệnh đọc hoặc thay đổi dữ liệu bằng quyền của definer. |
| Trigger hoặc event bị bỏ sót khi review | Trigger/event tự động chạy với quyền definer | Một thao tác tưởng như chỉ tác động một bảng có thể tạo thêm thay đổi ở bảng khác hoặc chạy một tác vụ đặc quyền theo lịch. |
| Nhầm danh tính trong routine | Dùng `CURRENT_USER()` như thể luôn là người dùng kết nối | Trong ngữ cảnh `DEFINER`, `CURRENT_USER()` có thể trả về tài khoản definer; kiểm tra quyền theo người gọi có thể sai. |
| Definer bị xóa hoặc thay đổi quyền | Object vẫn lưu tham chiếu đến tài khoản definer | Object có thể lỗi khi chạy nếu tài khoản không còn tồn tại; thay đổi quyền của tài khoản cũng làm thay đổi khả năng thực thi của object. |
| Gán definer tùy ý | Người tạo object có quyền quản trị đặc biệt để chỉ định một tài khoản khác làm definer | Object có thể được tạo để sử dụng quyền của một tài khoản mạnh hơn người tạo. |

### Dynamic SQL trong routine có quyền DEFINER

Không ghép trực tiếp dữ liệu đầu vào vào chuỗi SQL:

```sql
-- Mẫu nguy hiểm: đầu vào có thể thay đổi cấu trúc câu lệnh.
SET @sql = CONCAT(
    'SELECT * FROM sales.orders WHERE customer_name = ''',
    p_customer_name,
    ''''
);
```

Khi cần dynamic SQL trong stored procedure, dùng parameter marker cho giá trị và truyền giá trị bằng `EXECUTE ... USING`. Tên bảng, tên cột hoặc hướng sắp xếp không thể được bind như một giá trị; nếu chúng phải thay đổi, hãy ánh xạ đầu vào qua danh sách cho phép cố định trước khi ghép vào câu lệnh. Luôn kiểm tra độ dài, miền giá trị và ý nghĩa nghiệp vụ của tham số. Parameterization ngăn dữ liệu bị diễn giải như cú pháp SQL, nhưng tự nó không chứng minh người gọi được phép thao tác trên bản ghi đó.

### CURRENT_USER() và USER() không đồng nghĩa

`CURRENT_USER()` thể hiện tài khoản MySQL đang được dùng để kiểm tra quyền trong ngữ cảnh hiện tại. Trong routine hoặc view chạy với `SQL SECURITY DEFINER`, giá trị này có thể là tài khoản definer. `USER()` thể hiện danh tính kết nối mà client cung cấp khi kết nối. Hai giá trị có thể khác nhau; kết nối qua proxy hoặc ứng dụng dùng chung tài khoản còn làm việc suy ra người dùng cuối phức tạp hơn.

Nếu một view dùng `CURRENT_USER()` để lọc hàng, hãy kiểm tra điều kiện đó dưới đúng `SQL SECURITY` đang triển khai. Một bộ lọc được viết với giả định `CURRENT_USER()` luôn là người xem có thể vô tình dùng danh tính của definer và trả dữ liệu sai phạm vi.

## 6. Kiểm kê DEFINER và SQL SECURITY

Không nên chỉ review view và procedure. Hãy kiểm kê cả trigger và event vì chúng cũng có thể thực thi bằng quyền definer.

Liệt kê view và stored routine cùng chế độ bảo mật:

```sql
SELECT
    'VIEW' AS object_type,
    TABLE_SCHEMA AS object_schema,
    TABLE_NAME AS object_name,
    DEFINER,
    SECURITY_TYPE
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA NOT IN ('mysql', 'sys', 'performance_schema', 'information_schema')

UNION ALL

SELECT
    ROUTINE_TYPE AS object_type,
    ROUTINE_SCHEMA AS object_schema,
    ROUTINE_NAME AS object_name,
    DEFINER,
    SECURITY_TYPE
FROM INFORMATION_SCHEMA.ROUTINES
WHERE ROUTINE_SCHEMA NOT IN ('mysql', 'sys', 'performance_schema', 'information_schema')
ORDER BY object_schema, object_type, object_name;
```

Liệt kê trigger và event riêng:

```sql
SELECT
    TRIGGER_SCHEMA,
    TRIGGER_NAME,
    EVENT_OBJECT_TABLE,
    DEFINER
FROM INFORMATION_SCHEMA.TRIGGERS
WHERE TRIGGER_SCHEMA NOT IN ('mysql', 'sys', 'performance_schema', 'information_schema');

SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    DEFINER,
    STATUS
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA NOT IN ('mysql', 'sys', 'performance_schema', 'information_schema');
```

Các view trong `INFORMATION_SCHEMA` chỉ hiển thị những metadata mà tài khoản hiện tại được phép xem. Một kết quả không có dòng không chứng minh hệ thống không có object; hãy chạy kiểm kê bằng tài khoản kiểm toán có phạm vi quyền phù hợp.

Với object đáng ngờ, lấy định nghĩa đầy đủ và quyền của definer:

```sql
SHOW CREATE VIEW reporting.open_orders;
SHOW CREATE PROCEDURE hr.read_payroll;
SHOW CREATE TRIGGER sales.orders_after_update;
SHOW CREATE EVENT maintenance.daily_cleanup;

SHOW GRANTS FOR 'report_owner'@'localhost';
SHOW GRANTS FOR 'hr_report_user'@'10.%';
```

Đọc phần thân object để tìm các bảng được truy cập, dynamic SQL, hàm kiểm tra danh tính, thao tác ghi và lời gọi lồng nhau. Đối chiếu quyền của definer với đúng các thao tác đó; đồng thời kiểm tra quyền trực tiếp và quyền qua role của người gọi để phát hiện đường truy cập vòng.

## 7. Nguyên tắc thiết kế an toàn

1. **Ưu tiên INVOKER khi không cần nâng quyền.** Với view và routine chỉ phục vụ thao tác theo quyền sẵn có của người gọi, khai báo `SQL SECURITY INVOKER` rõ ràng.
2. **Dùng tài khoản definer riêng cho từng mục đích.** Không dùng `root` hoặc tài khoản quản trị làm definer cho ứng dụng. Cấp đúng quyền trên đúng schema, bảng và thao tác cần thiết; tránh quyền toàn cục nếu không có lý do rõ ràng.
3. **Xem EXECUTE là quyền truy cập dữ liệu.** Cấp quyền trên từng procedure cho role hoặc tài khoản cần dùng. Review cả kết quả mà procedure trả về và các thay đổi mà nó có thể thực hiện.
4. **Giữ logic phân quyền trong object.** Kiểm tra phạm vi tenant, chủ sở hữu bản ghi, trạng thái và giới hạn nghiệp vụ ở phía tin cậy. Không dùng tham số do client tự khai báo làm bằng chứng duy nhất về danh tính.
5. **Dùng parameter marker và allowlist.** Không nối trực tiếp đầu vào vào SQL. Nếu cần chọn tên bảng/cột, ánh xạ lựa chọn sang danh sách cố định và từ chối giá trị ngoài danh sách.
6. **Review trigger và event như mã thực thi đặc quyền.** Ghi rõ bảng nguồn, bảng đích, thời điểm kích hoạt, điều kiện chạy và tài khoản definer. Đảm bảo các tác động phụ phù hợp với quyền mà người dùng có thể kích hoạt.
7. **Quản lý vòng đời tài khoản definer.** Trước khi xóa hoặc đổi quyền tài khoản, kiểm tra các object đang tham chiếu đến tài khoản đó. Tài khoản definer không tồn tại có thể khiến object lỗi khi được gọi; nếu tạo lại tài khoản cùng cặp `user`/`host`, hãy review lại quyền mới và mọi object tham chiếu.
8. **Kiểm soát việc chỉ định DEFINER.** Chỉ cấp quyền quản trị cần thiết cho người triển khai schema. Khả năng chỉ định một definer khác tài khoản hiện tại được kiểm soát bằng quyền đặc biệt; tên và yêu cầu quyền thay đổi theo phiên bản MySQL.
9. **Kiểm tra quyền sau khi triển khai.** Đối chiếu DDL, `SHOW GRANTS`, role đang được cấp và kết quả thử bằng tài khoản thực tế. Không dựa riêng vào việc migration chạy thành công.

Khi triển khai trên môi trường mới hoặc khôi phục từ bản dump, cần tạo tài khoản definer và cấp quyền phù hợp trước khi kiểm tra các object phụ thuộc. Bản dump có thể giữ nguyên mệnh đề `DEFINER`; nếu tài khoản đó không có trên máy đích hoặc không còn quyền cần thiết, view, routine, trigger hay event có thể không hoạt động như ở môi trường nguồn. Hãy kiểm tra lại danh sách definer và quyền sau mỗi lần restore hoặc chuyển môi trường.

## 8. Quy trình kiểm thử trước khi phát hành

Với mỗi view hoặc routine dùng `DEFINER`, tạo một ma trận kiểm thử tối thiểu:

| Tài khoản thử | Quyền mong đợi | Điều cần xác nhận |
|---|---|---|
| Tài khoản được cấp quyền trên object | Chỉ thực hiện được chức năng đã công bố | Kết quả không vượt phạm vi hàng/cột; thao tác ghi chỉ thay đổi dữ liệu được phép. |
| Tài khoản không được cấp quyền trên object | Bị từ chối | Không thể gọi view hoặc routine chỉ bằng cách biết tên object. |
| Tài khoản có quyền trực tiếp trên bảng | Theo đúng grants của tài khoản đó | Không nhầm kết quả của quyền trực tiếp với quyền được cấp qua stored object. |
| Tài khoản definer | Có đúng quyền tối thiểu cần dùng | Object không phụ thuộc vào quyền quản trị không cần thiết. |

Trong bài kiểm thử, xác nhận cả đường truy cập trực tiếp và gián tiếp. Thử tham số biên, giá trị không hợp lệ, bản ghi thuộc tenant khác và các trạng thái nghiệp vụ không được phép. Với object có dynamic SQL, thử chuỗi đầu vào chứa dấu nháy và ký tự cú pháp; câu lệnh phải xử lý chúng như dữ liệu hoặc từ chối đầu vào. Với trigger, kiểm tra cả thay đổi chính và các tác động phụ. Với event, xác nhận tài khoản definer, trạng thái event và quyền trên các bảng được tác vụ sử dụng.

Nếu phát hiện một object đang dùng quyền quá rộng, trước hết xác định các ứng dụng và tài khoản phụ thuộc vào object. Sau đó thu hẹp quyền của definer, sửa logic hoặc chuyển sang `INVOKER` khi phù hợp, điều chỉnh grants của người gọi, rồi chạy lại ma trận kiểm thử. Không xóa tài khoản definer một cách đột ngột khi chưa kiểm kê object phụ thuộc, vì việc đó có thể làm hỏng tác vụ đang vận hành.

## 9. Những câu hỏi cần trả lời khi review

- Object có thật sự cần chạy với quyền `DEFINER` không? Nếu có, vì sao `INVOKER` không đáp ứng được?
- Definer là tài khoản `user`/`host` nào, có quyền gì, và quyền nào thực sự được object sử dụng?
- Ai có `SELECT` trên view hoặc `EXECUTE` trên routine? Quyền được cấp trực tiếp hay qua role?
- Object trả về những cột và hàng nào? Người gọi có thể truyền tham số để mở rộng phạm vi không?
- Có dynamic SQL, thao tác ghi, trigger, event hoặc lời gọi stored object khác không?
- Logic có dùng `CURRENT_USER()` hoặc `USER()` không, và giá trị đó có đúng với ngữ cảnh thực thi không?
- Nếu definer bị khóa, đổi quyền, xóa hoặc tạo lại, object sẽ chịu tác động gì?
- Các kiểm thử đã chạy bằng tài khoản ứng dụng thực tế trên môi trường gần với production chưa?

Một thiết kế tốt dùng `DEFINER` như một cơ chế ủy quyền có giới hạn: object công bố một thao tác nhỏ, definer chỉ có quyền cần thiết, và người gọi chỉ được cấp quyền trên đúng object đó. Khi không cần cơ chế ủy quyền này, `INVOKER` giữ việc kiểm tra quyền gắn với tài khoản đang thực hiện truy vấn và thường dễ đánh giá hơn.
