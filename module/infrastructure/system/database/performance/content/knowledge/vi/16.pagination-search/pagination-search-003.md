# Khóa sắp xếp ghép, giá trị trùng và thứ tự ổn định

Phân trang thường bắt đầu bằng một câu truy vấn có `ORDER BY` và giới hạn số hàng trả về. Tuy nhiên, nếu cột sắp xếp có nhiều giá trị trùng nhau, thứ tự giữa các hàng cùng giá trị không được xác định đầy đủ. Khi đó, hai lần chạy cùng một truy vấn có thể trả các hàng ở ranh giới trang theo thứ tự khác nhau. Người dùng có thể thấy một bản ghi xuất hiện ở hai trang hoặc bị bỏ qua khi chuyển trang.

Để phân trang ổn định, truy vấn cần một **thứ tự toàn phần** (*total order*): mọi hàng trong tập kết quả đều có vị trí xác định duy nhất. Cách phổ biến là dùng khóa sắp xếp ghép, trong đó các cột nghiệp vụ quyết định thứ tự chính và một khóa duy nhất làm tiêu chí phân xử cuối cùng (*tie-breaker*). Thiết kế này cũng là nền tảng của keyset pagination, hay còn gọi là seek pagination, giúp lấy trang tiếp theo theo vị trí khóa thay vì bỏ qua một số lượng lớn hàng.

Trong module **DATABASE_PERFORMANCE**, cần hiểu giá trị trùng ảnh hưởng thế nào đến phân trang, cách xây dựng thứ tự ổn định, cách tạo điều kiện tiếp tục cho khóa ghép, và cách kết hợp thứ tự với chỉ mục. Cần xem xét cả `NULL`, collation, hướng tăng/giảm, phép nối một-nhiều và dữ liệu thay đổi giữa các lần gọi trang. Một thứ tự ổn định giải quyết tính xác định của sắp xếp; tính nhất quán của toàn bộ tập dữ liệu còn phụ thuộc transaction và snapshot.

## 1. Vì sao ORDER BY một cột chưa chắc tạo thứ tự ổn định?

Giả sử trang đơn hàng được sắp xếp theo thời gian tạo mới nhất:

```sql
SELECT order_id, customer_id, created_at
FROM orders
ORDER BY created_at DESC
FETCH FIRST 20 ROWS ONLY;
```

Nếu nhiều đơn hàng có cùng `created_at`, câu lệnh chỉ xác định thứ tự giữa các nhóm thời gian. Nó không xác định đơn hàng nào đứng trước trong cùng một nhóm. Hệ quản trị có thể trả các hàng đồng hạng theo thứ tự khác nhau tùy kế hoạch, cách đọc chỉ mục, mức song song, thay đổi dữ liệu hoặc phiên bản.

Điều này trở nên rõ ở ranh giới trang. Giả sử hàng thứ 20 và hàng thứ 21 có cùng timestamp. Nếu thứ tự nội bộ của nhóm đồng hạng thay đổi giữa hai lần thực thi, một hàng có thể chuyển từ trang đầu sang trang kế tiếp hoặc ngược lại. Khi ứng dụng dùng `OFFSET` để lấy trang kế tiếp, kết quả có thể lặp hoặc thiếu hàng.

### Ví dụ có giá trị trùng

| order_id | created_at | Vị trí khi chỉ sắp xếp theo created_at |
|---:|---|---|
| 105 | 2026-11-19 10:00:00 | Cùng nhóm |
| 108 | 2026-11-19 10:00:00 | Cùng nhóm |
| 111 | 2026-11-19 10:00:00 | Cùng nhóm |
| 117 | 2026-11-19 09:59:00 | Nhóm kế tiếp |

Nếu trang cắt giữa ba hàng đầu, chỉ `created_at DESC` chưa đủ để xác định hàng nào thuộc trang trước. Bổ sung `order_id` làm khóa phân xử:

```sql
SELECT order_id, customer_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Giả sử `order_id` là duy nhất, mỗi hàng có một vị trí duy nhất theo cặp `(created_at, order_id)`. Khi timestamp trùng, `order_id DESC` quyết định thứ tự trong nhóm.

## 2. Thứ tự toàn phần và khóa sắp xếp ghép

Thứ tự toàn phần phải xác định được quan hệ trước/sau cho mọi cặp hàng khác nhau. Trong SQL, có thể tạo thứ tự này bằng nhiều biểu thức trong `ORDER BY`:

```sql
ORDER BY business_priority DESC,
         created_at DESC,
         order_id DESC
```

Các cột được xét lần lượt từ trái sang phải:

1. So sánh `business_priority`; giá trị ưu tiên cao hơn đứng trước.
2. Nếu hai hàng bằng nhau ở cột đầu, so sánh `created_at`.
3. Nếu cả hai cột đầu đều bằng nhau, so sánh `order_id`.

Nếu `order_id` duy nhất trên toàn tập kết quả, thứ tự ghép là duy nhất. Nếu khóa cuối chỉ duy nhất trong phạm vi tenant hoặc một bảng cha, phải bổ sung các cột còn thiếu để tổ hợp cuối cùng thật sự duy nhất.

### Chọn tie-breaker

Một tie-breaker phù hợp thường là:

- Khóa chính của hàng được phân trang.
- Một khóa duy nhất, ổn định và không thay đổi trong vòng đời bản ghi.
- Tổ hợp nhiều cột tạo thành khóa duy nhất nếu không có một cột đơn phù hợp.

Không nên dùng một cột không duy nhất làm tiêu chí cuối cùng rồi giả định thứ tự đã ổn định. Ví dụ `created_at, status` vẫn có thể trùng ở cả hai cột. Nếu có nhiều hàng trùng toàn bộ khóa sắp xếp, thứ tự vẫn chưa toàn phần.

Nếu truy vấn tạo một hàng kết quả cho mỗi tổ hợp cha-con, khóa chính của bảng cha có thể lặp. Khi đó cần bổ sung khóa con, ví dụ `(order_id, order_item_id)`, để mỗi hàng kết quả có thứ tự duy nhất. Nếu mục tiêu là phân trang theo đơn hàng, hãy phân trang danh sách đơn hàng trước rồi mới lấy các dòng hàng của những đơn hàng đó.

### Không dùng thứ tự vật lý làm tie-breaker

Không dựa vào thứ tự lưu trên đĩa, vị trí trang, thứ tự trả về của index scan hoặc thứ tự tự nhiên khi không có `ORDER BY`. Các chi tiết này có thể thay đổi sau khi cập nhật, vacuum, rebuild index, parallel execution hoặc thay đổi kế hoạch. Chỉ các biểu thức trong `ORDER BY` mới là hợp đồng thứ tự của truy vấn.

## 3. Khóa ghép hoạt động theo thứ tự từ điển

Một khóa sắp xếp ghép được so sánh theo kiểu từ điển (*lexicographic order*). Với thứ tự:

```sql
ORDER BY created_at DESC, order_id DESC
```

Hàng A đứng trước hàng B nếu:

- `A.created_at` mới hơn `B.created_at`; hoặc
- timestamp bằng nhau và `A.order_id` lớn hơn `B.order_id`.

Điều kiện lấy các hàng sau một cursor `(last_created_at, last_order_id)` phải phản ánh đúng quy tắc này:

```sql
WHERE created_at < :last_created_at
   OR (created_at = :last_created_at
       AND order_id < :last_order_id)
ORDER BY created_at DESC, order_id DESC
```

Điều kiện dùng `<` vì cả hai cột đang sắp xếp giảm dần: hàng tiếp theo phải có timestamp cũ hơn, hoặc cùng timestamp nhưng ID nhỏ hơn. Đây là điều kiện keyset cho trang kế tiếp sau hàng cuối của trang hiện tại.

### Ví dụ đầy đủ với keyset pagination

Trang đầu:

```sql
SELECT order_id, customer_id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Giả sử hàng cuối cùng trả về có `created_at = '2026-11-19 10:00:00'` và `order_id = 108`. Cursor của trang kế tiếp chứa đúng hai giá trị này.

Trang kế tiếp:

```sql
SELECT order_id, customer_id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND (
      created_at < :last_created_at
      OR (created_at = :last_created_at
          AND order_id < :last_order_id)
  )
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Truy vấn bắt đầu sau khóa cuối của trang trước. Nó không cần đếm và bỏ qua 20 hàng đầu như `OFFSET 20`; hệ quản trị có thể tìm đến vùng khóa tương ứng rồi đọc tiếp nếu có chỉ mục phù hợp.

`FETCH FIRST` là cú pháp được nhiều hệ quản trị hỗ trợ nhưng cách giới hạn hàng khác nhau theo nền tảng. SQL Server thường dùng `OFFSET ... FETCH NEXT`, PostgreSQL và MySQL thường dùng `LIMIT`, Oracle hỗ trợ cú pháp row limiting tùy phiên bản. Điều kiện cursor và `ORDER BY` mới là phần quyết định ngữ nghĩa phân trang.

## 4. Hướng sắp xếp hỗn hợp

Không phải mọi cột đều có cùng hướng sắp xếp. Ví dụ, ưu tiên cao đứng trước (`priority DESC`), nhưng trong cùng mức ưu tiên thì thời gian cũ đứng trước (`created_at ASC`), sau đó dùng ID tăng dần:

```sql
ORDER BY priority DESC, created_at ASC, task_id ASC
```

Điều kiện lấy hàng sau cursor phải đảo phép so sánh theo từng cột:

```sql
WHERE priority < :last_priority
   OR (priority = :last_priority
       AND created_at > :last_created_at)
   OR (priority = :last_priority
       AND created_at = :last_created_at
       AND task_id > :last_task_id)
```

Giải thích:

- `priority` giảm dần nên giá trị nhỏ hơn nằm sau.
- `created_at` tăng dần nên giá trị lớn hơn nằm sau khi priority bằng nhau.
- `task_id` tăng dần nên ID lớn hơn nằm sau khi hai cột trước bằng nhau.

Với khóa có nhiều cột, điều kiện tiếp tục là một chuỗi các nhánh: cột đầu tiên khác cursor theo hướng đi tiếp, hoặc cột trước bằng cursor và cột tiếp theo khác theo hướng đi tiếp. Phải giữ đúng thứ tự và hướng của từng biểu thức trong `ORDER BY`.

### Sai lầm khi dùng một toán tử cho mọi cột

Nếu truy vấn sắp xếp `priority DESC, created_at ASC` nhưng điều kiện cursor dùng `<` cho cả hai cột, các hàng có cùng priority sẽ bị bỏ qua hoặc lặp. Hãy viết điều kiện dựa trên từng hướng sắp xếp, rồi kiểm thử ở các trường hợp bằng nhau trên một, hai và toàn bộ cột khóa.

## 5. Giá trị NULL trong khóa sắp xếp

`NULL` không phải một giá trị thông thường. Phép so sánh `column = NULL`, `column < NULL` hoặc `column > NULL` không trả về true; kết quả thường là `UNKNOWN`. Vì vậy, điều kiện keyset đơn giản có thể không xử lý đúng hàng có khóa null.

Thứ tự mặc định của `NULL` cũng khác nhau giữa các hệ quản trị. Một số hệ đặt null đầu khi sắp xếp tăng dần, một số hệ đặt null cuối; hướng giảm dần cũng có thể khác. Không nên dựa vào mặc định nếu phân trang cần nhất quán giữa môi trường.

### Cách đơn giản nhất: dùng khóa sắp xếp NOT NULL

Nếu nghiệp vụ cho phép, ưu tiên cột sắp xếp và tie-breaker có `NOT NULL`. Ví dụ `created_at` và `order_id` đều bắt buộc có giá trị. Điều này làm điều kiện cursor ngắn gọn và dễ kiểm chứng.

### Xác định vị trí NULL rõ ràng

Nếu cột có thể null, có thể đưa một biểu thức phân nhóm null vào thứ tự:

```sql
ORDER BY
  CASE WHEN due_at IS NULL THEN 1 ELSE 0 END ASC,
  due_at ASC,
  task_id ASC
```

Trong ví dụ, các hàng có `due_at` khác null đứng trước; hàng null đứng sau. Cursor cần chứa cả trạng thái null và các giá trị khóa liên quan. Điều kiện tiếp tục phải tách nhánh cho nhóm null và không null, bởi phép so sánh với `NULL` không dùng được như so sánh thông thường.

Một cách khái quát là dùng `null_rank` như cột đầu của khóa ghép, rồi so sánh `due_at` chỉ khi `null_rank` biểu thị giá trị không null. Với nhóm null, tiếp tục bằng tie-breaker `task_id`. Nếu biểu thức null-rank được dùng thường xuyên, có thể cân nhắc cột sinh hoặc chỉ mục biểu thức nếu hệ quản trị hỗ trợ.

### NULLS FIRST và NULLS LAST

Một số hệ quản trị hỗ trợ cú pháp `NULLS FIRST` hoặc `NULLS LAST` trong `ORDER BY`. Đây là cách làm rõ thứ tự hiển thị, nhưng không tự động giải quyết điều kiện keyset. Cursor predicate vẫn phải mô phỏng cùng quy tắc null. Nếu dùng cú pháp này, kiểm tra khả năng hỗ trợ của phiên bản và sự tương thích với chỉ mục.

## 6. Chuỗi, collation và giá trị được xem là bằng nhau

Khi sắp xếp theo chuỗi, collation quyết định cách so sánh chữ hoa/thường, dấu, ký tự Unicode và thứ tự ngôn ngữ. Với collation không phân biệt hoa thường, `Alpha` và `alpha` có thể được xem là bằng nhau ở tiêu chí tên. Nếu chỉ `ORDER BY name`, thứ tự giữa các chuỗi được xem là tương đương chưa chắc ổn định.

Hãy thêm khóa duy nhất làm tie-breaker:

```sql
ORDER BY customer_name COLLATE <collation_phu_hop> ASC,
         customer_id ASC
```

Tên collation và cú pháp cụ thể phụ thuộc hệ quản trị; placeholder trên chỉ biểu thị vị trí cấu hình, không phải tên collation có thể chạy trực tiếp. Điều kiện keyset phải dùng cùng quy tắc so sánh với `ORDER BY`. Nếu `ORDER BY` dùng collation không phân biệt dấu nhưng predicate dùng collation khác, phép so sánh bằng trong cursor có thể không chia nhóm giống thứ tự sắp xếp.

Nếu sắp xếp theo biểu thức như `LOWER(customer_name)`, cursor cần lưu giá trị biểu thức đã sắp xếp hoặc có thể tái tạo chính xác biểu thức đó. Predicate tiếp tục cũng phải dùng cùng biểu thức, cùng collation và cùng quy tắc null.

## 7. Khóa sắp xếp nên ổn định theo thời gian

Một thứ tự toàn phần không tự bảo đảm một bản ghi luôn nằm cùng vị trí giữa các lần tải trang. Nếu cột sắp xếp thay đổi, hàng có thể di chuyển qua ranh giới cursor.

Ví dụ, trang được sắp xếp theo `priority DESC, task_id DESC`. Người dùng đã đọc qua cursor có `priority = 5`. Sau đó một tác vụ ở trang sau được tăng priority lên 9; nó có thể chuyển lên trước cursor và không xuất hiện trong các trang tiếp theo. Ngược lại, một hàng từ trước cursor bị giảm priority có thể chuyển xuống sau cursor và xuất hiện lần nữa.

Đối với danh sách cần duyệt ổn định, ưu tiên các khóa:

- Có thứ tự rõ ràng và tie-breaker duy nhất.
- Ít thay đổi sau khi bản ghi được tạo, chẳng hạn `created_at` và ID bất biến.
- Có độ chính xác và kiểu dữ liệu được lưu giữ đầy đủ trong cursor.
- Có cùng ngữ nghĩa giữa `ORDER BY` và điều kiện tiếp tục.

Nếu nghiệp vụ bắt buộc sắp xếp theo trường có thể thay đổi như trạng thái, điểm ưu tiên hoặc số lượt xem, cần chấp nhận rằng các trang được tải ở những thời điểm khác nhau có thể phản ánh thứ tự mới. Nếu cần một kết quả nhất quán như ảnh chụp tại một thời điểm, phải dùng snapshot hoặc chiến lược lưu tập ID theo phiên duyệt.

## 8. Thứ tự ổn định và tính nhất quán khi dữ liệu thay đổi

Có hai vấn đề cần phân biệt:

1. **Tính xác định của thứ tự:** cùng một tập hàng được sắp xếp theo một thứ tự toàn phần, không còn hàng đồng hạng chưa phân xử.
2. **Tính nhất quán của tập dữ liệu:** các trang được lấy ở thời điểm khác nhau có nhìn thấy cùng một tập dữ liệu hay không.

Thêm tie-breaker giải quyết vấn đề thứ nhất. Nó không ngăn bản ghi mới được chèn, bản ghi cũ bị xóa hoặc trường sắp xếp bị cập nhật giữa hai lần gọi API.

### OFFSET chịu ảnh hưởng thế nào?

Giả sử trang đầu lấy 20 hàng theo thứ tự ổn định. Sau khi trang đầu được trả về, một hàng mới được chèn vào đầu danh sách. Khi ứng dụng gọi `OFFSET 20`, hàng mới chiếm một vị trí phía trước và đẩy một hàng cũ sang trang kế tiếp. Người dùng có thể thấy hàng cuối trang đầu lặp lại ở trang hai. Nếu một hàng bị xóa trước vị trí offset, một hàng có thể bị bỏ qua.

### Keyset giảm dịch chuyển do chèn/xóa phía trước cursor

Với keyset, trang tiếp theo được xác định bằng khóa cuối đã đọc thay vì vị trí tuyệt đối. Hàng mới được chèn trước cursor thường không làm dịch chuyển ranh giới của truy vấn tiếp theo; hàng mới nằm sau cursor có thể xuất hiện ở trang sau. Hàng bị xóa trước cursor cũng không làm hệ thống bỏ qua thêm một vị trí như offset.

Tuy vậy, keyset không tạo snapshot tự động. Nếu sort key của một hàng thay đổi từ sau cursor sang trước cursor, hoặc ngược lại, hàng vẫn có thể bị bỏ qua hoặc lặp. Nếu cần snapshot nhất quán, cần thêm cơ chế transaction/snapshot hoặc lưu danh sách khóa của tập kết quả.

### Snapshot và transaction

Một số hệ quản trị cung cấp isolation dựa trên snapshot/MVCC, nhưng việc giữ cùng snapshot qua nhiều yêu cầu HTTP cần thiết kế cẩn thận. Giữ transaction mở lâu có thể giữ phiên bản dữ liệu cũ, làm tăng áp lực lưu trữ phiên bản, giữ tài nguyên kết nối và cản trở vacuum/cleanup tùy hệ quản trị.

Với báo cáo hoặc xuất dữ liệu dài, có thể tạo một tập ID hoặc snapshot nghiệp vụ tại thời điểm bắt đầu rồi phân trang trên tập đó. Với danh sách tương tác thông thường, keyset trên khóa bất biến thường là lựa chọn thực tế hơn; sản phẩm cần định nghĩa rõ việc bản ghi mới có được phép xuất hiện trong các trang tiếp theo hay không.

## 9. OFFSET pagination và keyset pagination

| Tiêu chí | OFFSET/LIMIT | Keyset/seek |
|---|---|---|
| Cách xác định trang | Bỏ qua N hàng rồi lấy số hàng tiếp theo | Bắt đầu sau khóa cuối của trang trước |
| Trang sâu | Có thể tốn chi phí vì phải đi qua nhiều hàng bị bỏ qua | Thường hiệu quả hơn nếu có chỉ mục phù hợp |
| Nhảy đến trang số bất kỳ | Dễ biểu đạt hơn | Khó nếu không biết cursor của trang trước |
| Chèn/xóa trước vị trí trang | Có thể làm hàng lặp hoặc bị bỏ qua | Ít bị dịch chuyển ranh giới bởi thay đổi trước cursor |
| Yêu cầu thứ tự | Cần thứ tự xác định để phân trang đúng | Cần thứ tự toàn phần và cursor chứa đủ khóa |
| Khả năng duyệt tiếp | Dùng offset mới | Dùng giá trị khóa cuối của trang hiện tại |

### Khi OFFSET vẫn phù hợp

OFFSET phù hợp với bảng nhỏ, trang đầu hoặc trang nông, giao diện cần nhảy đến trang bất kỳ, hoặc dữ liệu ít thay đổi. Nếu dùng offset, luôn có `ORDER BY` toàn phần. Tránh dựa vào thứ tự mặc định của bảng.

### Khi keyset phù hợp

Keyset phù hợp với danh sách lớn, cuộn vô hạn, API lấy trang kế tiếp liên tục, dữ liệu có khóa sắp xếp ổn định và có thể xây dựng index hỗ trợ. Nó đặc biệt hữu ích khi người dùng thường đi từ trang hiện tại sang trang kế tiếp thay vì nhảy trực tiếp đến trang rất xa.

## 10. Thiết kế chỉ mục cho khóa sắp xếp ghép

Một chỉ mục B-tree phù hợp có thể hỗ trợ bộ lọc bằng ở đầu và thứ tự sắp xếp tiếp theo. Với truy vấn:

```sql
SELECT order_id, customer_id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

một chỉ mục ứng viên là:

```sql
CREATE INDEX ix_orders_tenant_created_id
ON orders (tenant_id, created_at DESC, order_id DESC);
```

`tenant_id` được lọc bằng dấu bằng, tiếp theo là hai khóa sắp xếp. Hệ quản trị có thể tìm vùng của tenant rồi đọc theo thứ tự cần thiết. Nếu chỉ mục chứa đủ các cột truy vấn, một số hệ quản trị có thể giảm truy cập bảng; tuy nhiên, thêm nhiều cột để phủ truy vấn làm index lớn hơn và tăng chi phí ghi.

### Quy tắc chọn thứ tự cột

- Đặt các cột lọc bằng thường xuyên ở đầu nếu phù hợp với workload.
- Đặt các cột sắp xếp theo đúng thứ tự `ORDER BY` sau nhóm điều kiện bằng.
- Bảo đảm tie-breaker nằm trong khóa chỉ mục để hỗ trợ thứ tự toàn phần.
- Xem xét hướng `ASC`/`DESC`, đặc biệt khi các cột có hướng hỗn hợp.
- Đánh giá truy vấn khác dùng cùng chỉ mục; không thiết kế riêng một index quá rộng cho một endpoint nếu có lựa chọn tốt hơn.

B-tree có thể được đọc ngược để đáp ứng một số hướng sắp xếp đảo toàn bộ khóa. Nhưng khi các cột có hướng hỗn hợp, định nghĩa hướng của từng cột trong index có thể quan trọng. Hành vi chính xác tùy hệ quản trị và phiên bản; hãy kiểm tra actual plan.

### Điều kiện lọc nhiều giá trị

Nếu truy vấn có `status IN ('OPEN', 'PENDING')`, một chỉ mục `(tenant_id, status, created_at, order_id)` có thể tạo các vùng khóa riêng cho từng trạng thái. Việc kết hợp các vùng đó thành một thứ tự toàn cục theo thời gian có thể cần merge hoặc sort. Đừng mặc định index ghép sẽ luôn trả kết quả theo `created_at` trên nhiều giá trị status. Hãy kiểm tra kế hoạch và đo.

### Chỉ mục phủ

Nếu trang chỉ trả về vài cột, có thể cân nhắc cột INCLUDE hoặc cơ chế tương đương để giảm lookup. Cột sắp xếp và lọc cần thuộc phần khóa; cột chỉ dùng để hiển thị có thể là cột phủ tùy nền tảng. INCLUDE không thay thế khóa sắp xếp và không làm thay đổi tính duy nhất của phần khóa.

## 11. Phân trang khi truy vấn có JOIN

Một lỗi phổ biến là phân trang sau khi nối bảng cha với bảng con một-nhiều:

```sql
SELECT o.order_id, o.created_at, i.order_item_id, i.product_id
FROM orders AS o
JOIN order_item AS i
  ON i.order_id = o.order_id
ORDER BY o.created_at DESC, o.order_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Truy vấn đang phân trang các hàng kết quả sau join, không phải 20 đơn hàng. Một đơn hàng có nhiều dòng hàng có thể chiếm nhiều vị trí và bị chia giữa hai trang. Nếu mục tiêu là phân trang đơn hàng, hãy lấy trang ID đơn hàng trước rồi mới lấy dòng hàng:

```sql
WITH page_orders AS (
    SELECT o.order_id, o.created_at
    FROM orders AS o
    WHERE o.tenant_id = :tenant_id
    ORDER BY o.created_at DESC, o.order_id DESC
    FETCH FIRST 20 ROWS ONLY
)
SELECT p.order_id, p.created_at,
       i.order_item_id, i.product_id
FROM page_orders AS p
LEFT JOIN order_item AS i
  ON i.order_id = p.order_id
ORDER BY p.created_at DESC, p.order_id DESC,
         i.order_item_id ASC;
```

Truy vấn bên trong xác định 20 đơn hàng theo khóa ghép ổn định. Truy vấn ngoài lấy chi tiết cho đúng tập đơn hàng đó. Nếu kết quả cuối cần phân trang theo từng dòng hàng, phải đưa `order_item_id` vào khóa sắp xếp và cursor để mỗi hàng kết quả có vị trí duy nhất.

Nếu bảng con chỉ dùng để lọc sự tồn tại, cân nhắc `EXISTS` thay vì join để tránh nhân bản hàng cha. Khi cần dữ liệu bảng con, hãy xác định rõ đơn vị phân trang là cha hay tổ hợp cha-con.

## 12. Cursor của keyset pagination

Cursor là thông tin cho biết vị trí cuối cùng đã đọc. Với khóa ghép `(created_at DESC, order_id DESC)`, cursor phải chứa cả timestamp và order ID. Chỉ lưu timestamp là không đủ vì nhiều hàng có thể trùng timestamp.

Một cursor logic có thể chứa:

```json
{
  "created_at": "2026-11-19T10:00:00.123456Z",
  "order_id": 108
}
```

Đây là ví dụ cấu trúc; API có thể mã hóa nội dung thành chuỗi opaque. Các giá trị phải giữ nguyên độ chính xác và kiểu dữ liệu của khóa trong cơ sở dữ liệu. Nếu timestamp có microsecond nhưng cursor chỉ giữ millisecond, điều kiện tiếp tục có thể tạo trùng hoặc bỏ sót.

### Cursor phải phản ánh đúng truy vấn

Cursor nên gắn với:

- Toàn bộ giá trị khóa sắp xếp, theo đúng thứ tự và hướng.
- Phiên bản định nghĩa sort nếu API cho phép nhiều kiểu sắp xếp.
- Bộ lọc hoặc ngữ cảnh truy vấn cần thiết để tránh dùng cursor của một tập dữ liệu cho truy vấn khác.
- Quy tắc xử lý null và collation nếu khóa có các đặc điểm này.

Không nên để client tự thay đổi tùy ý các giá trị khóa trong cursor nếu điều đó có thể làm sai phạm vi dữ liệu. Có thể mã hóa hoặc ký cursor để phát hiện sửa đổi; cursor vẫn không thay thế kiểm tra quyền truy cập và tenant ở phía máy chủ.

### Xử lý trang đầu và trang cuối

Trang đầu không có cursor nên dùng truy vấn không có điều kiện tiếp tục. Trang kế tiếp dùng khóa cuối của trang trước. Để biết còn dữ liệu hay không, một cách phổ biến là lấy `page_size + 1` hàng; nếu có hàng dư, trả `has_next = true` và chỉ gửi `page_size` hàng. Cursor tiếp theo được tạo từ hàng cuối thực sự trả về, không phải hàng dư.

Đối với điều hướng ngược về trang trước, cần xây dựng điều kiện theo hướng ngược, đảo hướng sắp xếp trong truy vấn lấy dữ liệu rồi đảo thứ tự kết quả ở tầng ứng dụng nếu cần. Không nên chỉ đổi toán tử `<` thành `>` mà quên đảo thứ tự `ORDER BY`.

## 13. Thay đổi bộ lọc và thứ tự giữa các trang

Cursor chỉ có ý nghĩa trong cùng một định nghĩa truy vấn. Nếu trang đầu lọc `status = 'OPEN'` nhưng trang sau đổi thành `status = 'PENDING'`, cursor cũ không còn đại diện cho cùng tập dữ liệu. Tương tự, thay đổi `ORDER BY` hoặc collation giữa các lần gọi có thể làm điều kiện tiếp tục không chính xác.

API nên giữ các bộ lọc và thứ tự nhất quán trong suốt một lượt duyệt. Nếu client thay đổi tìm kiếm, sắp xếp hoặc tenant, hãy bắt đầu lượt phân trang mới và bỏ cursor cũ. Server có thể lưu một mã phiên truy vấn hoặc ký thông tin filter/sort trong cursor để phát hiện sử dụng sai.

Nếu dữ liệu mới được thêm sau khi trang đầu được trả về, sản phẩm cần quyết định có cho phép các hàng mới xuất hiện ở trang tiếp theo không. Với keyset trên `created_at` giảm dần, hàng mới hơn cursor thường nằm trước vị trí đã đọc nên không xuất hiện trong phần còn lại; hàng có timestamp cũ hơn cursor có thể xuất hiện. Nếu yêu cầu là snapshot tại thời điểm bắt đầu, cần thêm giới hạn high-water mark hoặc snapshot dữ liệu được quản lý rõ ràng.

## 14. Khác biệt cú pháp phân trang theo hệ quản trị

Điều kiện keyset có thể dùng chung về mặt logic, nhưng cú pháp giới hạn số hàng khác nhau:

| Hệ quản trị | Cú pháp thường dùng | Ví dụ giới hạn trang |
|---|---|---|
| PostgreSQL | `LIMIT` / `FETCH FIRST` | `LIMIT 20` |
| MySQL | `LIMIT` | `LIMIT 20` |
| SQL Server | `OFFSET ... FETCH NEXT` hoặc `TOP` trong một số trường hợp | `OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY` |
| Oracle Database | `FETCH FIRST ... ROWS ONLY` hoặc row limiting theo phiên bản | `FETCH FIRST 20 ROWS ONLY` |

Ví dụ PostgreSQL/MySQL cho keyset:

```sql
SELECT order_id, created_at
FROM orders
WHERE tenant_id = ?
  AND (
      created_at < ?
      OR (created_at = ? AND order_id < ?)
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Ví dụ SQL Server dùng cùng điều kiện:

```sql
SELECT order_id, created_at
FROM dbo.Orders
WHERE tenant_id = @tenant_id
  AND (
      created_at < @last_created_at
      OR (created_at = @last_created_at
          AND order_id < @last_order_id)
  )
ORDER BY created_at DESC, order_id DESC
OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY;
```

`OFFSET 0` trong ví dụ SQL Server chỉ dùng cú pháp giới hạn hàng; điều kiện keyset vẫn xác định vị trí bắt đầu. Cần dùng parameter type tương thích với cột để tránh implicit conversion làm giảm khả năng dùng index.

## 15. Đo hiệu năng và xác minh thứ tự ổn định

Trước khi thay đổi, hãy thu thập baseline cho cả trang đầu và trang sâu. Với OFFSET, đo chi phí khi offset tăng từ nhỏ lên lớn. Với keyset, đo trang đầu và các cursor nằm ở vùng đầu, giữa và cuối dữ liệu.

Các chỉ số cần xem:

- Actual execution plan và access path của chỉ mục.
- Estimated rows so với actual rows.
- Số hàng phải đọc hoặc bỏ qua để trả một trang.
- Logical reads, physical reads, CPU và elapsed time.
- p95/p99 khi có nhiều yêu cầu phân trang đồng thời.
- Throughput và chi phí cập nhật chỉ mục trong workload ghi.
- Sort, memory grant và spill nếu hệ quản trị phải sắp xếp ngoài index order.

### Kiểm thử tính đúng của phân trang

Không chỉ đo tốc độ. Hãy tạo bộ dữ liệu kiểm thử có:

1. Nhiều hàng cùng giá trị ở cột sắp xếp chính.
2. Nhiều hàng trùng trên nhiều cột đầu của khóa ghép.
3. Giá trị `NULL` nếu schema cho phép.
4. Chuỗi khác nhau về hoa/thường, dấu và Unicode nếu sắp xếp văn bản.
5. Các hàng có cùng khóa cha nhưng khác khóa con khi có join.
6. Giá trị timestamp ở độ chính xác tối đa mà hệ thống lưu.

Chạy liên tục qua tất cả trang và kiểm tra rằng không có khóa kết quả bị lặp hoặc thiếu trong một snapshot cố định. Sau đó thử chèn, xóa và cập nhật dữ liệu giữa hai lần gọi để quan sát đúng hành vi mà sản phẩm đã chọn. Nếu cần snapshot, kiểm tra riêng cơ chế snapshot/high-water mark.

### So sánh trước và sau

| Chỉ số | OFFSET trang sâu | Keyset có index phù hợp |
|---|---|---|
| Số hàng bỏ qua | Có thể tăng theo số trang | Không cần bỏ qua các trang trước |
| Access path | Có thể scan nhiều khóa trước khi trả kết quả | Có thể seek/range scan từ cursor |
| Độ trễ trang sâu | Thường tăng khi offset lớn | Thường ổn định hơn nếu phân bố và index phù hợp |
| Độ đúng khi có tie | Cần total order | Cần total order và cursor đủ mọi khóa |
| Ảnh hưởng dữ liệu thay đổi | Chèn/xóa trước offset dễ dịch chuyển vị trí | Ít bị ảnh hưởng bởi thay đổi trước cursor; vẫn nhạy với sort key thay đổi |

Đây là xu hướng phổ biến, không phải bảo đảm cho mọi workload. Nếu điều kiện lọc rất rộng, index không phù hợp hoặc trang trả về nhiều dữ liệu, keyset vẫn có thể tốn kém. Hãy đo trên dữ liệu và kế hoạch thực tế.

## 16. Những sai lầm thường gặp

1. **ORDER BY chỉ theo cột không duy nhất:** các hàng đồng hạng không có thứ tự xác định.
2. **Dùng tie-breaker vẫn có thể trùng:** khóa cuối phải làm cho toàn bộ tổ hợp sắp xếp duy nhất trên tập kết quả.
3. **Cursor chỉ lưu cột đầu:** không thể phân biệt vị trí giữa các hàng có cùng giá trị cột đầu.
4. **Dùng cùng toán tử cho mọi cột:** điều kiện keyset sai khi hướng ASC/DESC hỗn hợp.
5. **Bỏ qua NULL:** so sánh thông thường với null là UNKNOWN và thứ tự mặc định khác nhau giữa hệ quản trị.
6. **Không thống nhất collation:** ORDER BY và cursor predicate có thể nhóm giá trị chuỗi khác nhau.
7. **Làm tròn timestamp trong cursor:** mất độ chính xác có thể tạo hàng lặp hoặc bị bỏ qua.
8. **Dùng khóa có thể thay đổi:** bản ghi có thể di chuyển qua cursor giữa hai trang.
9. **Phân trang sau join một-nhiều:** một thực thể cha có thể chiếm nhiều vị trí hoặc bị chia giữa trang.
10. **Coi keyset là snapshot:** keyset không tự đóng băng dữ liệu giữa các lần gọi.
11. **Tạo index nhưng không đo:** optimizer có thể không dùng index hoặc index làm chi phí ghi tăng.
12. **Dùng cursor với filter/sort khác:** vị trí cursor không còn phù hợp với tập kết quả mới.

## 17. Danh sách kiểm tra trước khi triển khai

- [ ] Đã xác định đơn vị phân trang: hàng bảng, thực thể cha hay tổ hợp sau join.
- [ ] Đã tạo `ORDER BY` toàn phần với tie-breaker duy nhất.
- [ ] Đã xác minh tổ hợp khóa duy nhất trên toàn bộ tập kết quả.
- [ ] Đã ghi rõ hướng ASC/DESC cho từng cột và viết predicate cursor tương ứng.
- [ ] Đã xác định thứ tự `NULL` và dùng cùng quy tắc trong cursor.
- [ ] Đã thống nhất collation, biểu thức và kiểu dữ liệu giữa ORDER BY và predicate.
- [ ] Cursor giữ đủ giá trị khóa và độ chính xác nguyên vẹn.
- [ ] Bộ lọc và thứ tự được giữ nguyên giữa các trang của cùng lượt duyệt.
- [ ] Đã chọn index phù hợp với điều kiện bằng và khóa sắp xếp ghép.
- [ ] Đã kiểm thử dữ liệu trùng, null, Unicode, timestamp và join một-nhiều.
- [ ] Đã đo trang sâu, actual plan, logical reads, CPU và p95/p99.
- [ ] Đã xác định yêu cầu snapshot khi dữ liệu thay đổi giữa các lần gọi.

Khóa sắp xếp ghép giải quyết trường hợp nhiều hàng có cùng giá trị ở cột sắp xếp chính bằng cách thêm các tiêu chí phân xử cho đến khi mỗi hàng có một vị trí duy nhất. Tie-breaker phải thật sự duy nhất trên tập kết quả, và cursor của keyset phải lưu đầy đủ mọi thành phần khóa theo đúng hướng sắp xếp. Hãy xử lý rõ `NULL`, collation, độ chính xác kiểu dữ liệu và phép nối một-nhiều; sau đó thiết kế chỉ mục khớp bộ lọc cùng thứ tự. Thứ tự toàn phần làm phân trang xác định, còn việc giữ nguyên tập dữ liệu giữa các trang cần một chiến lược snapshot riêng nếu nghiệp vụ yêu cầu.
