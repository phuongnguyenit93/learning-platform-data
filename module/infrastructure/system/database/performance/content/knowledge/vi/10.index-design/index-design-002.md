# Chỉ mục nhiều cột: thứ tự cột, tiền tố và phạm vi tìm kiếm

Chỉ mục nhiều cột (composite index hoặc multicolumn index) lưu khóa được tạo từ nhiều cột theo một thứ tự xác định. Nó có thể giúp hệ quản trị tìm đúng nhóm hàng, hỗ trợ phép nối, trả kết quả theo thứ tự và giảm lượng dữ liệu phải đọc. Tuy nhiên, chỉ mục nhiều cột chỉ phát huy tác dụng khi thứ tự khóa phù hợp với điều kiện lọc, phạm vi tìm kiếm và cách truy vấn sử dụng dữ liệu.

Trong chương **Thiết kế chỉ mục** của module **DATABASE_PERFORMANCE**, bài học này giải thích cách chọn thứ tự cột, quy tắc tiền tố trái, ảnh hưởng của điều kiện bằng và điều kiện khoảng, cũng như cách tận dụng chỉ mục cho ORDER BY và giới hạn hàng. Module rèn phương pháp tối ưu hiệu năng dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Vì vậy, thiết kế chỉ mục phải xuất phát từ workload thực tế, được kiểm tra bằng kế hoạch thực thi và được đánh giá cùng chi phí ghi, bộ nhớ và lưu trữ.

## 1. Chỉ mục nhiều cột lưu trữ dữ liệu theo thứ tự nào?

Với chỉ mục B-tree nhiều cột, các khóa thường được sắp xếp theo thứ tự từ cột đầu tiên đến cột cuối cùng. Có thể hình dung chỉ mục trên (tenant_id, status, created_at) được sắp theo tenant_id trước; trong cùng một tenant, các khóa được sắp theo status; trong cùng một cặp tenant_id và status, các khóa được sắp theo created_at.

Ví dụ, bảng orders có dữ liệu:

| tenant_id | status | created_at | order_id |
|---:|---|---|---:|
| 10 | PAID | 2026-01-02 | 501 |
| 10 | PAID | 2026-01-05 | 509 |
| 10 | PENDING | 2026-01-01 | 490 |
| 20 | PAID | 2026-01-03 | 610 |
| 20 | PENDING | 2026-01-04 | 615 |

Với chỉ mục theo thứ tự (tenant_id, status, created_at), các khóa được nhóm theo tenant_id, sau đó theo status và cuối cùng theo thời gian. Đây là thứ tự từ điển (lexicographic order), không phải ba danh sách được sắp xếp độc lập.

Điều này có ý nghĩa lớn đối với tìm kiếm. Khi truy vấn biết tenant_id và status, hệ quản trị có thể xác định một vùng khóa liên tiếp tương ứng với cặp giá trị đó. Nếu truy vấn chỉ biết status mà không biết tenant_id, các hàng có cùng status có thể nằm rải rác trong nhiều nhóm tenant, nên chỉ mục này không nhất thiết tạo ra một vùng tìm kiếm liên tục cho status.

Quy tắc trên mô tả hành vi điển hình của B-tree. Các loại chỉ mục khác như hash, bitmap, inverted hoặc columnstore có cấu trúc và khả năng khác. Ngay cả giữa các hệ quản trị B-tree, chi tiết tối ưu hóa như skip scan, xử lý NULL, thứ tự NULL và cách kết hợp điều kiện cũng có thể khác nhau.

## 2. Quy tắc tiền tố trái

Với chỉ mục B-tree trên (a, b, c), các tiền tố liên tiếp từ trái thường là những nhóm điều kiện dễ tận dụng nhất:

- a
- a và b
- a, b và c

Ví dụ:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at);
~~~

Một số mẫu truy vấn:

| Điều kiện truy vấn | Khả năng tận dụng tiền tố của chỉ mục |
|---|---|
| tenant_id = ? | Có thể tìm theo cột đầu tiên |
| tenant_id = ? AND status = ? | Có thể tìm theo hai cột đầu |
| tenant_id = ? AND status = ? AND created_at >= ? | Có thể tìm theo cả ba cột, với phạm vi ở cột cuối |
| tenant_id = ? AND created_at >= ? | Có thể dùng tiền tố tenant_id; created_at có thể phải lọc thêm hoặc cần khả năng tối ưu riêng |
| status = ? | Không có tiền tố trái; thường không phải đường tìm kiếm hiệu quả bằng chỉ mục này |
| created_at >= ? | Không có tiền tố trái; thường không thể tìm một vùng liên tiếp trực tiếp theo created_at |

Nếu truy vấn chỉ lọc status, chỉ mục bắt đầu bằng tenant_id có thể buộc hệ quản trị quét nhiều nhóm tenant hoặc chọn một đường truy cập khác. Tùy hệ quản trị và dữ liệu, optimizer có thể dùng skip scan hoặc chiến lược tương tự để khai thác cột sau khi cột đầu không có điều kiện. Không nên giả định tính năng này tồn tại hoặc luôn rẻ; hãy xem kế hoạch thực thi và tài liệu của nền tảng.

Quy tắc tiền tố trái là hướng dẫn để hình thành giả thuyết, không phải một luật tuyệt đối áp dụng giống nhau cho mọi loại chỉ mục và mọi bộ tối ưu. Một chỉ mục có thể vẫn giúp truy vấn không lọc đủ các cột đầu nếu hệ quản trị có khả năng quét, skip scan, lọc tại index hoặc tận dụng thứ tự sẵn có. Tuy nhiên, lượng khóa phải đọc có thể lớn hơn đáng kể so với tìm kiếm theo tiền tố đầy đủ.

## 3. Thứ tự cột nên dựa trên mẫu truy vấn

Không có quy tắc đơn giản rằng cột có độ chọn lọc cao nhất luôn phải đứng đầu. Thứ tự tốt phụ thuộc vào các câu truy vấn thực tế cần hỗ trợ, điều kiện lọc, thứ tự sắp xếp, phạm vi giá trị, tần suất và khả năng tái sử dụng tiền tố.

Hãy bắt đầu từ các câu hỏi:

1. Những cột nào thường xuất hiện trong điều kiện bằng?
2. Những cột nào dùng điều kiện khoảng như lớn hơn, nhỏ hơn hoặc BETWEEN?
3. Truy vấn thường lọc theo một cột riêng lẻ hay theo tổ hợp cột?
4. Có truy vấn nào cần ORDER BY hoặc phân trang không?
5. Các truy vấn quan trọng có cùng tiền tố điều kiện hay khác nhau?
6. Dữ liệu có phân bố lệch theo tenant, trạng thái hoặc thời gian không?
7. Chỉ mục sẽ ảnh hưởng đến các thao tác ghi nào và với tần suất bao nhiêu?

Ví dụ, workload có các truy vấn:

~~~sql
-- Truy vấn A
SELECT order_id, created_at, total
FROM orders
WHERE tenant_id = :tenant
  AND status = :status;

-- Truy vấn B
SELECT order_id, created_at, total
FROM orders
WHERE tenant_id = :tenant
  AND status = :status
  AND created_at >= :from_time
ORDER BY created_at DESC;
~~~

Một chỉ mục bắt đầu bằng (tenant_id, status) có thể hỗ trợ cả hai truy vấn và dùng created_at để giới hạn phạm vi hoặc cung cấp thứ tự cho truy vấn B. Nếu có thêm một truy vấn quan trọng chỉ lọc theo tenant_id, tiền tố này cũng có thể hỗ trợ truy vấn đó.

Ngược lại, nếu workload chủ yếu lọc theo status trên toàn bộ tenant, chỉ mục bắt đầu bằng tenant_id có thể không phù hợp. Có thể cần một chỉ mục khác, nhưng chỉ nên tạo khi lợi ích đo được đủ lớn để bù chi phí duy trì.

## 4. Điều kiện bằng và điều kiện khoảng

Một nguyên tắc thiết kế B-tree thường hữu ích là đặt các cột được ràng buộc bằng trước cột đầu tiên có điều kiện khoảng, sau đó đánh giá các cột sắp xếp và cột bổ sung.

Ví dụ truy vấn:

~~~sql
SELECT order_id, created_at, total
FROM orders
WHERE tenant_id = :tenant
  AND status = :status
  AND created_at >= :from_time
  AND created_at < :to_time;
~~~

Chỉ mục ứng viên:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at);
~~~

Hai cột đầu có điều kiện bằng; cột created_at có điều kiện khoảng. Trong B-tree, hệ quản trị có thể định vị vùng khóa cho tenant_id và status, rồi tìm phần thời gian nằm trong khoảng yêu cầu.

Nếu thứ tự chỉ mục là (tenant_id, created_at, status), sau khi xác định tenant_id, hệ quản trị có thể tìm phạm vi created_at. Điều kiện status vẫn có thể được kiểm tra bằng dữ liệu chỉ mục hoặc ở bước lọc tiếp theo, tùy hệ quản trị, nhưng thường không thu hẹp được một vùng khóa liên tiếp theo cùng cách như khi status đứng trước cột khoảng.

Đây là lý do điều kiện bằng thường được xếp trước điều kiện khoảng trong một chỉ mục B-tree. Tuy nhiên, nếu workload có các truy vấn khác nhau, cột sắp xếp quan trọng hoặc phân bố dữ liệu đặc biệt, thứ tự tối ưu có thể thay đổi. Cần kiểm tra kế hoạch và số hàng được đọc.

### 4.1. Nhiều điều kiện bằng

Nếu truy vấn luôn có điều kiện bằng trên cả a và b, chỉ mục (a, b) và (b, a) đều có thể hỗ trợ tìm kiếm theo cả hai giá trị bằng. Thứ tự giữa chúng ảnh hưởng đến các truy vấn chỉ dùng một cột hoặc những truy vấn có thêm cột tiếp theo.

Ví dụ:

- (tenant_id, status) hỗ trợ tiền tố tenant_id.
- (status, tenant_id) hỗ trợ tiền tố status.

Nếu workload có nhiều truy vấn chỉ lọc tenant_id, thứ tự tenant_id trước có thể tái sử dụng tốt hơn. Nếu workload thường lọc status độc lập, thứ tự status trước có thể có ích cho nhóm truy vấn đó. Cần xem tần suất, độ chọn lọc và lượng dữ liệu thực tế, không chỉ số giá trị phân biệt.

### 4.2. Nhiều điều kiện khoảng

Nếu có nhiều cột dùng điều kiện khoảng, một B-tree thường chỉ có thể dùng một phạm vi liên tục hiệu quả sau các cột tiền tố được ràng buộc. Các điều kiện khoảng còn lại có thể được kiểm tra như bộ lọc bổ sung hoặc tận dụng tùy khả năng của hệ quản trị.

Ví dụ:

~~~sql
WHERE tenant_id = :tenant
  AND created_at >= :from_time
  AND amount BETWEEN :min_amount AND :max_amount
~~~

Với chỉ mục (tenant_id, created_at, amount), tenant_id có thể xác định tiền tố và created_at xác định phạm vi. amount có thể được kiểm tra thêm trong chỉ mục nếu dữ liệu sẵn có, nhưng không nhất thiết làm giảm đáng kể vùng quét liên tục.

Nếu truy vấn khác thường lọc amount trước created_at, một chỉ mục khác có thể phù hợp hơn. Không nên tạo tất cả hoán vị cột; hãy chọn những mẫu truy vấn có tác động lớn và đánh giá chi phí tổng thể.

## 5. Dùng chỉ mục nhiều cột cho ORDER BY

Chỉ mục B-tree lưu khóa theo thứ tự nên có thể hỗ trợ truy vấn cần sắp xếp, giảm hoặc loại bỏ bước sort nếu các điều kiện và thứ tự cột phù hợp.

Ví dụ:

~~~sql
SELECT order_id, created_at, total
FROM orders
WHERE tenant_id = :tenant
  AND status = :status
ORDER BY created_at DESC
FETCH FIRST 50 ROWS ONLY;
~~~

Chỉ mục ứng viên:

~~~sql
CREATE INDEX idx_orders_tenant_status_created_desc
ON orders (tenant_id, status, created_at DESC);
~~~

Khi tenant_id và status được cố định bằng điều kiện bằng, các khóa trong vùng tương ứng được sắp theo created_at giảm dần. Hệ quản trị có thể đọc từ đầu vùng khóa và dừng sau 50 hàng phù hợp, nếu kế hoạch và điều kiện khác cho phép.

Nếu chỉ mục lưu created_at tăng dần, một số hệ quản trị có thể quét ngược để phục vụ ORDER BY DESC. Vì vậy, không phải lúc nào cũng cần khai báo DESC trong chỉ mục. Tuy nhiên, với nhiều cột sắp xếp có hướng hỗn hợp, hướng từng cột có thể quan trọng.

Ví dụ:

~~~sql
ORDER BY created_at DESC, order_id ASC
~~~

Một chỉ mục có thứ tự (created_at DESC, order_id ASC) có thể phù hợp trực tiếp. Quét ngược toàn bộ chỉ mục sẽ đảo cả hai hướng, thành created_at ASC và order_id DESC, nên không tương đương. Hãy xem khả năng hỗ trợ hướng sắp xếp của hệ quản trị và kế hoạch thực tế.

### 5.1. ORDER BY có cột tiền tố

Nếu chỉ mục là (tenant_id, status, created_at), truy vấn chỉ có ORDER BY created_at mà không cố định tenant_id và status có thể không nhận được thứ tự toàn cục theo created_at. Chỉ mục nhóm theo tenant_id trước, rồi status, nên created_at chỉ được sắp bên trong từng nhóm tiền tố.

Tương tự, điều kiện bằng trên tiền tố có thể cho phép sử dụng thứ tự của các cột phía sau. Điều kiện khoảng trên cột tiền tố có thể làm thứ tự toàn cục của cột sau không còn phù hợp với ORDER BY.

Hãy kiểm tra thứ tự đầu ra mà truy vấn yêu cầu, không chỉ kiểm tra các cột có mặt trong chỉ mục.

### 5.2. ORDER BY kết hợp giới hạn hàng

Các truy vấn lấy một số hàng đầu tiên thường có thể hưởng lợi lớn từ chỉ mục có thứ tự phù hợp. Khi tìm được đúng vùng khóa và đọc theo thứ tự cần thiết, hệ quản trị có thể dừng sớm mà không phải đọc toàn bộ tập kết quả rồi sort.

Tuy nhiên, nếu điều kiện lọc không khớp tiền tố, hệ quản trị có thể phải đọc nhiều khóa trước khi tìm đủ 50 hàng. Kế hoạch cần cho biết số hàng đã đọc, số hàng bị lọc và số hàng trả về. Chỉ nhìn số hàng cuối cùng không đủ đánh giá lượng công việc.

## 6. Cột khóa và cột bao phủ

Một chỉ mục có thể chứa các cột theo hai vai trò khác nhau:

- **Cột khóa (key column):** tham gia thứ tự sắp xếp và có thể được dùng để tìm kiếm, giới hạn phạm vi hoặc cung cấp thứ tự.
- **Cột bao phủ (included/covering column):** được lưu thêm để truy vấn có thể lấy giá trị từ chỉ mục mà không cần truy cập lại hàng trong bảng, nhưng không tham gia thứ tự khóa.

Ví dụ với cú pháp PostgreSQL:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC)
INCLUDE (order_id, total);
~~~

Truy vấn:

~~~sql
SELECT order_id, created_at, total
FROM orders
WHERE tenant_id = :tenant
  AND status = :status
ORDER BY created_at DESC
LIMIT 50;
~~~

Các cột tenant_id, status và created_at tạo thứ tự khóa. order_id và total được lưu kèm để có thể hỗ trợ truy vấn lấy các giá trị đó từ chỉ mục. Việc có thực sự trở thành index-only scan hay không còn phụ thuộc hệ quản trị, trạng thái visibility, cấu trúc lưu trữ và kế hoạch.

Không nên thêm mọi cột SELECT vào chỉ mục. Cột bao phủ làm chỉ mục rộng hơn, chiếm thêm dung lượng, giảm số khóa trên mỗi trang và tăng chi phí cập nhật khi giá trị thay đổi. Với cột lớn như JSON, text dài hoặc blob, việc đưa vào chỉ mục có thể rất tốn kém hoặc bị giới hạn bởi hệ quản trị.

Cột INCLUDE không có cùng vai trò với cột khóa. Nó không giúp tìm kiếm theo tiền tố và không cung cấp thứ tự sắp xếp. Cú pháp và khả năng này khác nhau giữa các nền tảng; SQL Server có INCLUDE, PostgreSQL có INCLUDE trong B-tree và các hệ quản trị khác có cơ chế tương tự hoặc khác biệt.

## 7. Chọn thứ tự cột theo độ chọn lọc và khả năng tái sử dụng

Độ chọn lọc (selectivity) mô tả mức độ một điều kiện thu hẹp tập dữ liệu. Một điều kiện trả về 10 hàng trong bảng 10 triệu hàng có tính chọn lọc cao; điều kiện trả về 8 triệu hàng có tính chọn lọc thấp.

Độ chọn lọc là yếu tố quan trọng, nhưng không thể dùng một mình để quyết định thứ tự cột.

Khi nhiều cột đều có điều kiện bằng, cả hai thứ tự có thể tìm đúng tổ hợp giá trị. Lựa chọn nên xem xét:

- Truy vấn nào thường chỉ dùng một phần tiền tố?
- Cột nào xuất hiện trong nhiều workload quan trọng?
- Có cần ORDER BY theo một cột sau các điều kiện bằng không?
- Các tenant hoặc trạng thái có phân bố lệch không?
- Cột có kiểu dữ liệu, độ rộng và chi phí lưu trữ khác nhau không?
- Có truy vấn nào cần range scan hoặc phân trang không?

Ví dụ, tenant_id có độ chọn lọc trung bình nhưng xuất hiện ở hầu hết truy vấn; status có độ chọn lọc thấp hơn nhưng thường đi cùng tenant_id. Chỉ mục (tenant_id, status, created_at) có thể phù hợp vì tenant_id là tiền tố dùng chung và status là điều kiện bằng kế tiếp. Nếu có workload báo cáo toàn hệ thống chỉ lọc status, cần đánh giá riêng thay vì cho rằng chỉ mục hiện tại luôn đủ.

Một số hệ quản trị có thể tận dụng skip scan hoặc bitmap combination để kết hợp các điều kiện không khớp tiền tố. Những tính năng này có thể làm một chỉ mục nhiều cột linh hoạt hơn, nhưng không thay thế việc thiết kế tiền tố theo workload chính.

## 8. Điều kiện lọc, biểu thức và kiểu dữ liệu

Chỉ mục chỉ có thể hỗ trợ hiệu quả khi biểu thức truy vấn tương thích với cách khóa được lưu và cách hệ quản trị so sánh giá trị.

Ví dụ, chỉ mục thông thường trên created_at có thể khó được tận dụng nếu truy vấn áp dụng hàm lên cột:

~~~sql
WHERE DATE(created_at) = :target_date
~~~

Một cách viết theo khoảng thời gian thường có thể tận dụng chỉ mục trên created_at tốt hơn:

~~~sql
WHERE created_at >= :day_start
  AND created_at < :next_day_start
~~~

Mốc thời gian phải được tính đúng theo múi giờ và kiểu dữ liệu ứng dụng. Nếu workload thường tìm theo biểu thức, một số hệ quản trị hỗ trợ expression index hoặc computed-column index.

Cũng cần chú ý:

- Ép kiểu ngầm có thể làm thay đổi cách so sánh hoặc cản trở đường truy cập.
- Collation và quy tắc so sánh chuỗi ảnh hưởng thứ tự khóa.
- Điều kiện LIKE có thể tận dụng chỉ mục tùy mẫu tìm kiếm, collation và operator class.
- Điều kiện IS NULL hoặc IS NOT NULL được hỗ trợ khác nhau tùy loại chỉ mục và hệ quản trị.
- OR có thể được xử lý bằng nhiều nhánh, bitmap hoặc đường truy cập khác nhau.
- Hàm không xác định hoặc biểu thức có tác dụng phụ có thể hạn chế biến đổi.

Đừng thêm cột vào chỉ mục chỉ vì nó xuất hiện trong WHERE. Hãy xem biểu thức thực tế, kiểu dữ liệu, kế hoạch và số hàng cần đọc.

## 9. Chỉ mục nhiều cột và phép nối

Chỉ mục nhiều cột có thể hỗ trợ truy vấn nối bảng khi cột khóa nối kết hợp với điều kiện lọc khác.

Ví dụ:

~~~sql
SELECT o.order_id, o.created_at, c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.tenant_id = :tenant
  AND o.status = :status;
~~~

Nếu hệ quản trị bắt đầu từ một tập orders nhỏ theo tenant_id và status, chỉ mục trên orders có thể giúp tìm nhóm hàng đó. Bảng customers thường cần đường truy cập phù hợp trên customer_id, thường là khóa chính hoặc chỉ mục duy nhất.

Nếu truy vấn bắt đầu từ customers theo một điều kiện lọc rồi tìm orders theo customer_id, một chỉ mục có customer_id ở vị trí tiền tố có thể hữu ích hơn cho hướng truy cập đó. Không nên chỉ nhìn điều kiện JOIN mà bỏ qua bảng nào được lọc trước và số hàng đầu vào.

Kế hoạch thực thi sẽ cho biết thuật toán nối và đường truy cập thực tế. Với nested loop, chỉ mục trên cột tìm kiếm ở phía trong thường có vai trò quan trọng. Với hash join, quét tuần tự có thể phù hợp hơn khi cần nhiều hàng. Chỉ mục tốt phải hỗ trợ đường truy cập mà bộ tối ưu chọn trong workload thực tế.

## 10. Chi phí duy trì chỉ mục nhiều cột

Mỗi chỉ mục bổ sung tạo thêm công việc cho hệ quản trị:

- INSERT phải thêm khóa vào từng chỉ mục liên quan.
- DELETE phải loại bỏ hoặc đánh dấu khóa tương ứng.
- UPDATE cột khóa có thể phải cập nhật vị trí khóa trong chỉ mục.
- Chỉ mục rộng chiếm thêm dung lượng lưu trữ và cache.
- Nhiều chỉ mục có thể làm tăng thời gian bảo trì, backup, replication và phục hồi.
- Các chỉ mục gần giống nhau có thể trùng lặp phần lớn chi phí.

Một chỉ mục nhiều cột có thể thay thế một số chỉ mục đơn cột trong một số workload, nhưng không phải lúc nào cũng vậy. Chỉ mục (tenant_id, status) hỗ trợ tiền tố tenant_id, nhưng không tự động tương đương chỉ mục đơn trên status. Nếu truy vấn lọc status độc lập rất quan trọng, có thể vẫn cần một chỉ mục khác.

Cần xem tổng workload đọc/ghi, không chỉ tốc độ của một SELECT. Một chỉ mục làm truy vấn báo cáo nhanh hơn nhưng khiến luồng ghi chính chậm đi đáng kể có thể là lựa chọn không phù hợp.

## 11. Quy trình thiết kế chỉ mục nhiều cột

Một quy trình có thể áp dụng:

1. **Thu thập workload:** lấy query fingerprint, tần suất, p95/p99, tổng thời gian và tỷ lệ đọc/ghi.
2. **Chọn truy vấn quan trọng:** ưu tiên thao tác có ảnh hưởng lớn đến người dùng hoặc tiêu thụ nhiều tài nguyên.
3. **Đọc SQL thực tế:** xác định điều kiện bằng, điều kiện khoảng, phép nối, ORDER BY, GROUP BY và LIMIT.
4. **Xem chỉ mục hiện có:** kiểm tra tiền tố, cột khóa, cột bao phủ, trùng lặp và mức sử dụng.
5. **Đề xuất thứ tự cột:** cân nhắc tiền tố dùng chung, điều kiện bằng, phạm vi, thứ tự sắp xếp và các truy vấn liên quan.
6. **Kiểm tra thống kê:** xem số hàng, distinct count, histogram, phân bố lệch và ước lượng cardinality.
7. **Đưa ra giả thuyết:** nêu rõ chỉ mục sẽ giảm số hàng/trang đọc, tránh sort hay hỗ trợ dừng sớm ở đâu.
8. **Thử trong môi trường phù hợp:** tạo một chỉ mục ứng viên và lưu kế hoạch trước/sau.
9. **Đo lại workload:** so sánh p50/p95/p99, số hàng đọc, CPU, I/O, thông lượng ghi và dung lượng chỉ mục.
10. **Kiểm tra nhiều tham số:** thử tenant lớn/nhỏ, trạng thái phổ biến/hiếm và khoảng thời gian khác nhau.
11. **Theo dõi sau triển khai:** quan sát truy vấn liên quan, write amplification, cache và thời gian bảo trì.
12. **Loại bỏ chỉ mục không cần thiết:** chỉ thực hiện sau khi kiểm tra phụ thuộc và tác động trên toàn workload.

Không nên tạo một chỉ mục cho mọi hoán vị của các cột. Số lượng chỉ mục tăng sẽ làm chi phí ghi và quản trị tăng nhanh. Hãy chọn một số chỉ mục đáp ứng các mẫu truy vấn có giá trị cao nhất.

## 12. Ví dụ thực tế: chọn thứ tự khóa cho danh sách đơn hàng

Giả sử ứng dụng có ba truy vấn thường gặp:

~~~sql
-- A: Liệt kê đơn hàng theo tenant và trạng thái
SELECT order_id, created_at, total
FROM orders
WHERE tenant_id = :tenant
  AND status = :status;

-- B: Lấy 50 đơn hàng mới nhất theo tenant và trạng thái
SELECT order_id, created_at, total
FROM orders
WHERE tenant_id = :tenant
  AND status = :status
ORDER BY created_at DESC
LIMIT 50;

-- C: Báo cáo số đơn hàng theo tenant trong một khoảng thời gian
SELECT status, COUNT(*)
FROM orders
WHERE tenant_id = :tenant
  AND created_at >= :from_time
  AND created_at < :to_time
GROUP BY status;
~~~

Một chỉ mục ứng viên cho A và B:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC);
~~~

Chỉ mục này có tiền tố tenant_id cho truy vấn lọc theo tenant. Khi có cả tenant_id và status, nó có thể xác định vùng khóa hẹp hơn. created_at được sắp xếp giảm dần trong từng cặp tenant/status, nên có thể hỗ trợ truy vấn B lấy các hàng mới nhất và dừng sớm sau khi đủ 50 hàng.

Truy vấn C lọc tenant_id và khoảng created_at nhưng không có điều kiện status. Với chỉ mục trên, tenant_id là tiền tố phù hợp, còn created_at nằm sau status. Hệ quản trị có thể phải đọc một vùng lớn của tenant rồi lọc thời gian, hoặc chọn kế hoạch khác. Một chỉ mục (tenant_id, created_at) có thể hỗ trợ C tốt hơn.

Có nên tạo cả hai chỉ mục? Cần đo:

- Tần suất và tổng thời gian của A, B, C.
- Số hàng mỗi truy vấn đọc và trả về.
- Độ chọn lọc của tenant, status và khoảng thời gian.
- Chi phí INSERT/UPDATE/DELETE trên orders.
- Dung lượng tăng thêm và mức sử dụng cache.
- Khả năng một chỉ mục hiện có đã đáp ứng một phần workload.

Nếu A và B chiếm phần lớn tải và C ít chạy, chỉ mục đầu có thể là lựa chọn hợp lý. Nếu C là báo cáo quan trọng và thường xuyên, chỉ mục thứ hai có thể đáng cân nhắc. Quyết định phải dựa trên toàn workload thay vì chỉ tối ưu một truy vấn mẫu.

## 13. Kiểm chứng bằng kế hoạch và số liệu thực tế

Sau khi tạo chỉ mục, hãy dùng EXPLAIN hoặc công cụ tương đương để xem hệ quản trị có sử dụng chỉ mục và có giảm công việc hay không.

Ví dụ:

~~~sql
EXPLAIN
SELECT order_id, created_at, total
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
~~~

Khi đọc kế hoạch, hãy kiểm tra:

- Chỉ mục có được dùng không và dùng ở bước nào?
- Có bao nhiêu hàng được ước lượng và thực tế?
- Có bước sort còn lại không?
- Có bao nhiêu hàng hoặc trang phải đọc trước khi trả 50 hàng?
- Có heap/table lookup bổ sung cho từng khóa không?
- Kế hoạch có thay đổi với tenant lớn hoặc status phổ biến không?
- CPU, I/O, buffer read và thời gian chờ có giảm không?

EXPLAIN thường cho kế hoạch ước lượng. EXPLAIN ANALYZE hoặc chế độ tương đương có thể thực thi câu lệnh để lấy số liệu thực tế. Với câu lệnh ghi, cần kiểm tra tác động và dùng môi trường hoặc cơ chế giao dịch an toàn. Không thực hiện phép đo có thể gây thay đổi dữ liệu trên production khi chưa đánh giá.

Một chỉ mục có thể được dùng nhưng truy vấn vẫn chậm nếu phải đọc quá nhiều hàng, truy cập bảng ngẫu nhiên, thực hiện nhiều lần lặp hoặc bị giới hạn bởi khóa/I/O. Ngược lại, hệ quản trị có thể chọn quét tuần tự vì truy vấn cần phần lớn bảng. Đừng đánh giá thành công chỉ bằng việc kế hoạch có tên index scan.

## 14. Các sai lầm thường gặp

- **Đặt cột có độ chọn lọc cao nhất lên đầu trong mọi trường hợp.** Điều này bỏ qua tiền tố dùng chung, điều kiện truy vấn và ORDER BY.
- **Cho rằng chỉ mục nhiều cột hỗ trợ mọi cột riêng lẻ.** Các cột sau tiền tố thường không tạo vùng tìm kiếm liên tục khi thiếu điều kiện ở cột trước.
- **Cho rằng điều kiện sau cột khoảng luôn thu hẹp phạm vi tìm kiếm.** Nó có thể chỉ là bộ lọc bổ sung, tùy cấu trúc và hệ quản trị.
- **Tạo chỉ mục theo đúng thứ tự cột trong WHERE.** Thứ tự viết điều kiện không quyết định thứ tự khóa tối ưu.
- **Bỏ qua ORDER BY và LIMIT.** Một chỉ mục phù hợp có thể tránh sort và cho phép dừng sớm.
- **Đưa tất cả cột SELECT vào khóa.** Cột bao phủ có thể phù hợp hơn, nhưng vẫn làm chỉ mục rộng và tốn chi phí.
- **Tạo chỉ mục cho mọi tổ hợp cột.** Điều này làm tăng write amplification, dung lượng và công việc bảo trì.
- **Cho rằng index scan luôn nhanh hơn sequential scan.** Số hàng cần đọc và tính chất I/O quyết định lựa chọn.
- **Chỉ thử một tenant hoặc một giá trị trạng thái.** Phân bố lệch có thể khiến kế hoạch thay đổi đáng kể.
- **Không đo tác động ghi.** Lợi ích đọc cần được so sánh với chi phí duy trì chỉ mục.

## 15. Checklist thiết kế chỉ mục nhiều cột

- [ ] Đã xác định các query fingerprint và workload quan trọng.
- [ ] Đã phân biệt điều kiện bằng, điều kiện khoảng và điều kiện lọc bổ sung.
- [ ] Đã xem tiền tố trái mà các truy vấn thực sự sử dụng.
- [ ] Đã xác định các cột cần hỗ trợ ORDER BY, phân trang hoặc giới hạn hàng.
- [ ] Đã xem hướng sắp xếp ASC/DESC và thứ tự nhiều cột.
- [ ] Đã đánh giá độ chọn lọc, phân bố lệch và tham số đại diện.
- [ ] Đã kiểm tra biểu thức, kiểu dữ liệu, collation và xử lý NULL.
- [ ] Đã cân nhắc cột khóa so với cột bao phủ.
- [ ] Đã kiểm tra chỉ mục hiện có và nguy cơ trùng lặp.
- [ ] Đã xem xét chi phí INSERT, UPDATE, DELETE, lưu trữ và cache.
- [ ] Đã ghi lại kế hoạch trước và sau khi tạo chỉ mục.
- [ ] Đã đo p50/p95/p99, số hàng đọc, CPU, I/O và thông lượng ghi.
- [ ] Đã kiểm tra nhiều nhóm tham số và truy vấn liên quan.
- [ ] Đã có căn cứ rõ ràng để giữ, thay đổi hoặc loại bỏ chỉ mục.

## 16. Nguyên tắc cần ghi nhớ

Chỉ mục nhiều cột là một cấu trúc khóa có thứ tự. Với B-tree, thứ tự cột quyết định tiền tố nào có thể được tìm kiếm hiệu quả, phạm vi nào có thể được quét liên tục và thứ tự đầu ra nào có thể được tận dụng. Các điều kiện bằng thường được đặt trước cột khoảng; các cột sau đó có thể hỗ trợ lọc hoặc bao phủ, nhưng không phải lúc nào cũng thu hẹp vùng tìm kiếm.

Hãy thiết kế từ workload thật: xem các tiền tố thường dùng, điều kiện lọc, thứ tự sắp xếp, phân bố dữ liệu và chi phí ghi. Sau đó kiểm tra kế hoạch, số hàng/trang đọc và độ trễ trên nhiều giá trị tham số. Chỉ mục tốt là chỉ mục cải thiện các thao tác quan trọng trong toàn hệ thống mà vẫn giữ chi phí lưu trữ và duy trì ở mức chấp nhận được.
