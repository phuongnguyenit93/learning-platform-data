# Đánh đổi giữa tốc độ đọc, tốc độ ghi, dung lượng, tính nhất quán và độ bền dữ liệu

Hiệu năng cơ sở dữ liệu không phải là làm cho mọi thao tác đều nhanh nhất có thể. Một hệ thống thường phải phục vụ nhiều kiểu tải cùng lúc: đọc một bản ghi, lọc và phân trang, tổng hợp báo cáo, thêm dữ liệu, cập nhật trạng thái và xử lý nhiều giao dịch đồng thời. Mỗi quyết định thiết kế đều làm thay đổi chi phí của một hoặc nhiều thao tác.

Thêm chỉ mục có thể giảm thời gian đọc nhưng làm chậm ghi và tăng dung lượng lưu trữ. Lưu bộ nhớ đệm có thể giảm I/O nhưng tiêu tốn RAM và tạo thêm vấn đề về dữ liệu cũ. Ghi dữ liệu đã chuẩn hóa giúp duy trì tính nhất quán nhưng có thể cần nhiều phép nối khi đọc. Xác nhận giao dịch sau khi dữ liệu đã được ghi bền vững giúp bảo vệ dữ liệu nhưng thường làm tăng độ trễ commit.

Vì vậy, tối ưu hiệu năng cơ sở dữ liệu là quá trình xác định workload, đo chi phí, chọn đánh đổi phù hợp với yêu cầu nghiệp vụ và kiểm chứng kết quả sau điều chỉnh.

## 1. Xác định workload trước khi tối ưu

Workload là tập hợp các thao tác thực tế mà cơ sở dữ liệu phải xử lý. Hai hệ thống có cùng số lượng bản ghi vẫn có thể cần thiết kế rất khác nhau nếu một hệ thống chủ yếu đọc còn hệ thống kia thường xuyên cập nhật.

Khi khảo sát workload, cần làm rõ:

- **Tỷ lệ đọc và ghi:** số lần `SELECT`, `INSERT`, `UPDATE`, `DELETE` trong một khoảng thời gian.
- **Kiểu truy cập:** tra cứu theo khóa chính, lọc theo nhiều cột, truy vấn theo khoảng thời gian, sắp xếp, phân trang hay tổng hợp.
- **Mức đồng thời:** số giao dịch hoạt động cùng lúc, số kết nối và các điểm dữ liệu thường bị nhiều giao dịch truy cập.
- **Kích thước dữ liệu:** số bản ghi, kích thước hàng, số lượng chỉ mục, tốc độ tăng trưởng và tỷ lệ dữ liệu nóng so với dữ liệu ít dùng.
- **Yêu cầu nhất quán:** thao tác nào phải nhìn thấy dữ liệu mới nhất, thao tác nào có thể chấp nhận dữ liệu trễ trong một khoảng thời gian.
- **Yêu cầu độ bền:** khi hệ thống xác nhận thành công, dữ liệu phải được bảo vệ trước những loại sự cố nào.

Không nên chỉ dùng thời gian trung bình để mô tả hiệu năng. Trung bình có thể che giấu một nhóm yêu cầu rất chậm. Hãy theo dõi ít nhất p50, p95 và p99 cùng thông lượng. p95 là mức thời gian mà 95% yêu cầu hoàn thành không vượt quá; p99 giúp nhận ra các đuôi độ trễ ảnh hưởng đến một nhóm người dùng nhỏ nhưng đáng kể.

Một bộ số liệu cơ bản gồm:

| Nhóm | Chỉ số cần theo dõi | Điều chỉ số giúp nhận diện |
|---|---|---|
| Ứng dụng và truy vấn | p50, p95, p99, số truy vấn/giây | Độ trễ và thông lượng thực tế |
| CPU | Mức sử dụng CPU, thời gian CPU theo truy vấn | Tính toán, sắp xếp, join hoặc xử lý biểu thức tốn kém |
| I/O | Đọc/ghi vật lý, độ trễ lưu trữ, hàng đợi I/O | Truy vấn phải lấy quá nhiều trang dữ liệu hoặc thiết bị lưu trữ bị bão hòa |
| Bộ nhớ | Cache hit, buffer pool, áp lực bộ nhớ, spill ra đĩa | Dữ liệu nóng không nằm trong bộ nhớ hoặc truy vấn dùng quá nhiều bộ nhớ |
| Giao dịch | Thời gian giữ khóa, lock wait, deadlock, rollback | Tranh chấp giữa các giao dịch |
| Ghi bền vững | Độ trễ commit, thời gian flush log, replication lag | Chi phí ghi log và đồng bộ bản sao |
| Dung lượng | Kích thước bảng, chỉ mục, log và tốc độ tăng trưởng | Chi phí lưu trữ và nguy cơ tăng trưởng ngoài dự kiến |

Hãy đo trên dữ liệu và mẫu truy vấn gần với môi trường thật. Một phép thử nhỏ với ít kết nối có thể cho kết quả tốt nhưng không phản ánh tranh chấp khóa, cache miss hoặc hàng đợi I/O khi tải tăng.

## 2. Chỉ mục: đọc nhanh hơn, ghi tốn kém hơn

Chỉ mục giúp cơ sở dữ liệu tìm hàng phù hợp mà không phải quét toàn bộ bảng. Với chỉ mục B-tree, cơ sở dữ liệu có thể tìm theo giá trị, khoảng giá trị và thứ tự khóa. Đây là lựa chọn phổ biến cho các điều kiện bằng, so sánh và sắp xếp phù hợp với thứ tự cột của chỉ mục.

Ví dụ, ứng dụng thường truy vấn đơn hàng của một khách hàng theo thời gian mới nhất:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = ?
ORDER BY created_at DESC
LIMIT 20;
```

Một chỉ mục ghép theo khách hàng rồi đến thời gian có thể hỗ trợ cả điều kiện lọc và thứ tự kết quả:

```sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at DESC);
```

Thứ tự cột rất quan trọng. Với chỉ mục ghép `(customer_id, created_at)`, truy vấn lọc theo `customer_id` thường tận dụng được phần đầu của chỉ mục. Truy vấn chỉ lọc theo `created_at` có thể không tận dụng chỉ mục này hiệu quả như một chỉ mục bắt đầu bằng `created_at`. Hãy thiết kế theo các truy vấn thực tế thay vì chỉ nhìn vào danh sách cột của bảng.

Đổi lại, mỗi chỉ mục cần dung lượng và công việc bảo trì:

- Khi thêm hàng, cơ sở dữ liệu phải cập nhật các chỉ mục liên quan.
- Khi xóa hàng, các mục chỉ mục tương ứng cũng phải được xử lý.
- Khi cập nhật cột nằm trong khóa chỉ mục, cấu trúc chỉ mục có thể phải thay đổi.
- Chỉ mục rộng làm tăng số trang cần lưu, đọc và ghi; chúng cũng có thể làm giảm số mục nằm trên một trang.
- Nhiều chỉ mục trùng lặp hoặc ít được sử dụng làm tăng chi phí mà không đem lại lợi ích tương xứng.

Chỉ mục bao phủ (covering index) lưu thêm các cột cần trả về để một số truy vấn có thể lấy kết quả từ chỉ mục mà không phải đọc hàng trong bảng. Ví dụ, một số hệ quản trị hỗ trợ cú pháp `INCLUDE`:

```sql
CREATE INDEX idx_orders_customer_created_cover
ON orders (customer_id, created_at DESC)
INCLUDE (total_amount);
```

Truy vấn ví dụ có thể được phục vụ bằng chỉ mục nếu hệ quản trị và trạng thái dữ liệu cho phép. Tuy nhiên, cột được thêm vào chỉ mục vẫn chiếm dung lượng; nếu cột đó thường xuyên thay đổi, thao tác cập nhật cũng phải trả thêm chi phí. Không nên thêm mọi cột của bảng vào chỉ mục chỉ để cố tránh đọc bảng.

Chỉ mục một phần (partial index), nếu hệ quản trị hỗ trợ, có thể chỉ lưu các hàng thỏa điều kiện. Ví dụ, chỉ mục cho các đơn hàng đang mở có thể nhỏ hơn chỉ mục trên toàn bộ bảng. Nhưng khi trạng thái thay đổi làm hàng đi vào hoặc ra khỏi tập điều kiện, chỉ mục vẫn phải được cập nhật.

Trước khi thêm chỉ mục, hãy kiểm tra kế hoạch thực thi và thống kê sử dụng chỉ mục hiện có. Một lần quét tuần tự không nhất thiết là lỗi: nếu truy vấn cần phần lớn hàng trong bảng, quét tuần tự có thể rẻ hơn việc đi qua chỉ mục rồi đọc từng hàng riêng lẻ.

## 3. Chuẩn hóa, phi chuẩn hóa và chi phí đọc

Thiết kế chuẩn hóa giảm việc lặp dữ liệu và giúp cập nhật một sự thật tại một nơi. Ví dụ, thông tin khách hàng được lưu trong bảng `customers`, còn bảng `orders` chỉ lưu khóa tham chiếu đến khách hàng. Khi địa chỉ khách hàng thay đổi, ứng dụng chỉ cần cập nhật một bản ghi.

Khi đọc, ứng dụng có thể phải join nhiều bảng. Với workload đọc nhiều và báo cáo thường xuyên, số phép nối hoặc phép tổng hợp lặp lại có thể trở thành chi phí đáng kể.

Phi chuẩn hóa là lưu thêm dữ liệu đã tính hoặc dữ liệu được sao chép để truy vấn đọc nhanh hơn. Ví dụ, bảng đơn hàng có thể lưu tên khách hàng tại thời điểm đặt hàng, hoặc bảng tổng hợp có thể lưu tổng doanh thu theo ngày. Cách này giảm số phép nối hoặc phép tính khi đọc, nhưng làm tăng trách nhiệm cập nhật:

- Mọi nơi ghi dữ liệu phải duy trì các bản sao liên quan.
- Một thay đổi có thể cần cập nhật nhiều hàng hoặc nhiều bảng.
- Nếu cập nhật bất đồng bộ, dữ liệu tổng hợp có thể trễ so với dữ liệu gốc.
- Nếu cập nhật đồng bộ trong cùng giao dịch, thời gian giữ khóa và chi phí ghi có thể tăng.

Với dữ liệu lịch sử, sao chép một giá trị tại thời điểm phát sinh nghiệp vụ có thể là yêu cầu đúng về mặt mô hình, không chỉ là mẹo hiệu năng. Ví dụ, giá bán trên hóa đơn thường cần giữ nguyên giá tại thời điểm mua, ngay cả khi giá hiện tại của sản phẩm thay đổi.

Khung nhìn vật hóa (materialized view) lưu kết quả của truy vấn để đọc nhanh hơn. Đổi lại, kết quả phải được làm mới theo lịch hoặc theo cơ chế mà hệ quản trị cung cấp. Cần xác định rõ độ trễ dữ liệu được chấp nhận, chi phí làm mới và cách xử lý khi quá trình làm mới thất bại.

Chỉ phi chuẩn hóa sau khi đã xác định truy vấn đọc thực sự tốn kém và có quy tắc rõ ràng để duy trì dữ liệu sao chép. Nếu không, hệ thống có thể đổi một truy vấn chậm lấy nhiều đường ghi khó kiểm soát.

## 4. Bộ nhớ đệm: giảm I/O và đánh đổi độ mới

Hệ quản trị cơ sở dữ liệu thường dùng bộ nhớ đệm trang hoặc buffer pool để giữ dữ liệu và chỉ mục thường xuyên truy cập trong RAM. Khi dữ liệu đã nằm trong bộ nhớ, truy vấn có thể tránh được một lần đọc từ thiết bị lưu trữ. Ứng dụng cũng có thể dùng cache riêng để tránh gửi lại các truy vấn lặp.

Cache hữu ích khi:

- Một tập dữ liệu nhỏ được đọc lặp lại nhiều lần.
- Dữ liệu ít thay đổi so với tần suất đọc.
- Chi phí truy vấn hoặc phép tính để tạo dữ liệu đủ lớn.
- Có thể xác định chính xác thời điểm dữ liệu cache cần hết hạn hoặc bị vô hiệu hóa.

Cache làm giảm tải đọc nhưng cần bộ nhớ. Nếu cache quá lớn, nó có thể cạnh tranh RAM với buffer pool, hệ điều hành và các truy vấn đang chạy. Nếu cache quá nhỏ hoặc dữ liệu có tính phân tán cao, tỷ lệ cache hit thấp và chi phí quản lý cache có thể không đáng.

Cache ở tầng ứng dụng còn tạo ra vấn đề nhất quán. Sau khi một giao dịch cập nhật dữ liệu, bản cache có thể vẫn giữ giá trị cũ. Các chiến lược thường dùng gồm:

- **TTL:** dữ liệu hết hạn sau một khoảng thời gian. Cách này đơn giản nhưng chấp nhận một khoảng thời gian dữ liệu có thể cũ.
- **Invalidation khi ghi:** sau khi cập nhật thành công, xóa hoặc thay thế khóa cache liên quan.
- **Version key:** gắn phiên bản vào khóa cache để dữ liệu phiên bản cũ không còn được đọc.
- **Cập nhật theo sự kiện:** phát sự kiện sau commit và cập nhật cache ở consumer. Cách này cần xử lý giao nhận lặp, thứ tự sự kiện và độ trễ.

Không nên dùng cache để thay thế kiểm tra ràng buộc nghiệp vụ trong cơ sở dữ liệu. Những thao tác như trừ số lượng tồn kho, chuyển tiền hoặc giữ chỗ cần được bảo vệ bằng giao dịch và cơ chế nhất quán phù hợp. Cache có thể hỗ trợ hiển thị, nhưng không nên trở thành nguồn quyết định cuối cùng cho các bất biến quan trọng.

## 5. Giao dịch đồng thời và mức độ nhất quán

Khi nhiều giao dịch truy cập cùng dữ liệu, cơ sở dữ liệu phải điều phối để tránh các kết quả không hợp lệ. Cơ chế khóa, MVCC (Multi-Version Concurrency Control) và mức cô lập giao dịch đều ảnh hưởng đến độ trễ.

Khóa giúp bảo vệ dữ liệu khi có ghi đồng thời. Tuy nhiên, giao dịch giữ khóa quá lâu có thể khiến giao dịch khác phải chờ. Một giao dịch đọc dữ liệu rồi gọi dịch vụ bên ngoài trước khi commit có thể giữ tài nguyên lâu hơn cần thiết. Deadlock xảy ra khi các giao dịch chờ khóa theo vòng; hệ quản trị thường phải hủy một giao dịch để phá vòng chờ.

MVCC cho phép nhiều giao dịch đọc các phiên bản dữ liệu phù hợp với snapshot của chúng. Điều này có thể giảm xung đột giữa đọc và ghi, nhưng không loại bỏ mọi tranh chấp. Giao dịch cập nhật cùng một hàng vẫn có thể phải chờ; các phiên bản cũ cũng cần được dọn dẹp theo cơ chế của hệ quản trị.

Mức cô lập xác định những thay đổi đồng thời mà giao dịch có thể quan sát. Tên mức và chi tiết triển khai khác nhau giữa các hệ quản trị, nhưng có thể hiểu khái quát:

| Mức cô lập | Đặc điểm | Đánh đổi thường gặp |
|---|---|---|
| Read Uncommitted | Có thể cho phép đọc dữ liệu chưa commit ở hệ quản trị hỗ trợ đúng nghĩa | Ít điều phối hơn nhưng có nguy cơ đọc dữ liệu chưa được xác nhận |
| Read Committed | Mỗi câu lệnh chỉ đọc dữ liệu đã commit theo quy tắc snapshot của hệ quản trị | Thường phù hợp với nhiều ứng dụng; hai lần đọc trong một giao dịch có thể thấy kết quả khác nhau |
| Repeatable Read | Duy trì khả năng đọc lặp lại theo snapshot hoặc quy tắc tương ứng | Tính ổn định khi đọc cao hơn; xung đột ghi và chi phí quản lý phiên bản có thể tăng |
| Serializable | Bảo đảm kết quả tương đương một thứ tự thực thi tuần tự | Bảo vệ mạnh hơn các bất biến nhưng có thể phát sinh chờ hoặc giao dịch phải thử lại |

Không nên chọn mức cô lập thấp nhất chỉ vì muốn giảm độ trễ. Trước hết hãy xác định bất biến nghiệp vụ. Ví dụ, hai yêu cầu đồng thời cùng mua sản phẩm cuối cùng không được phép cùng thành công nếu quy tắc tồn kho không cho phép. Cần bảo vệ quy tắc đó bằng một giao dịch, câu lệnh cập nhật có điều kiện, khóa phù hợp hoặc cơ chế cô lập thích hợp.

Một số cách giảm tranh chấp mà không làm suy yếu tính nhất quán:

1. Giữ giao dịch ngắn; không thực hiện gọi mạng hoặc công việc chậm trong khi đang giữ khóa.
2. Truy cập các hàng theo cùng một thứ tự giữa các luồng xử lý để giảm nguy cơ deadlock.
3. Cập nhật đúng hàng và đúng cột cần thiết; tránh khóa phạm vi dữ liệu rộng không cần thiết.
4. Dùng cập nhật nguyên tử có điều kiện khi quy tắc nghiệp vụ có thể biểu diễn trong một câu lệnh.
5. Thiết kế retry có giới hạn cho lỗi deadlock hoặc serialization failure; chỉ thử lại giao dịch có thể chạy lại an toàn.
6. Theo dõi thời gian chờ khóa và giao dịch dài, thay vì chỉ nhìn vào thời gian thực thi SQL.

Ví dụ cập nhật tồn kho theo điều kiện:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = ?
  AND quantity >= 1;
```

Ứng dụng cần kiểm tra số hàng được cập nhật. Nếu không có hàng nào được cập nhật, sản phẩm không tồn tại hoặc không đủ hàng theo điều kiện. Câu lệnh này gộp việc kiểm tra và thay đổi vào một thao tác nguyên tử, tránh kiểu đọc số lượng trước rồi cập nhật sau mà không có bảo vệ đồng thời.

## 6. Độ bền dữ liệu và chi phí commit

Độ bền (durability) là thuộc tính bảo đảm rằng giao dịch đã được xác nhận sẽ tồn tại sau các sự cố nằm trong phạm vi cam kết của hệ thống. Để đạt được điều này, nhiều hệ quản trị dùng write-ahead log (WAL) hoặc cơ chế log tương đương.

Với WAL, thay đổi được ghi vào log trước khi trang dữ liệu tương ứng được ghi xuống vị trí lưu trữ chính. Khi phục hồi sau sự cố, hệ quản trị dùng log để tái tạo các thay đổi đã được xác nhận theo quy tắc phục hồi của nó. Cách tổ chức này cho phép gom các lần ghi và tránh phải ghi ngay mọi trang dữ liệu tại thời điểm commit.

Một giao dịch commit có thể phải chờ log được flush tới tầng lưu trữ bền vững. Độ trễ này phụ thuộc vào thiết bị lưu trữ, cấu hình hệ quản trị, kích thước log, cơ chế group commit và tải đồng thời. Group commit cho phép nhiều giao dịch chia sẻ một lần flush log, cải thiện thông lượng ghi trong một số workload.

Một số hệ quản trị cho phép cấu hình xác nhận commit trước khi log được flush bền vững. Cách này có thể giảm độ trễ, nhưng nếu máy chủ gặp sự cố trước khi log được ghi bền vững, một số giao dịch vừa được xác nhận có thể bị mất. Đây là thay đổi về cam kết độ bền, không đơn thuần là tinh chỉnh hiệu năng. Chỉ sử dụng khi nghiệp vụ chấp nhận rõ ràng mức rủi ro đó.

Sao chép dữ liệu cũng có hai kiểu đánh đổi phổ biến:

- **Sao chép đồng bộ:** giao dịch có thể phải chờ một hoặc nhiều bản sao xác nhận theo cấu hình. Độ trễ commit thường cao hơn, nhưng có thể giảm nguy cơ mất dữ liệu khi máy chủ chính gặp sự cố.
- **Sao chép bất đồng bộ:** máy chủ chính có thể xác nhận trước khi bản sao nhận đủ dữ liệu. Độ trễ ghi thường thấp hơn, nhưng khi chuyển đổi máy chủ có thể mất các giao dịch chưa được chuyển tới bản sao.

Độ bền tại máy chủ chính và độ sẵn sàng khi chuyển đổi máy chủ là hai vấn đề liên quan nhưng không giống nhau. Cần xác định RPO (mức dữ liệu có thể chấp nhận mất) và RTO (thời gian mục tiêu để khôi phục dịch vụ), sau đó kiểm chứng bằng quy trình phục hồi và chuyển đổi thực tế. Bản sao đồng bộ hay bất đồng bộ cũng không thay thế cho backup có thể khôi phục.

Khi tối ưu đường ghi, hãy phân biệt các lựa chọn:

- Gom nhiều thao tác vào một giao dịch có thể giảm chi phí commit lặp lại, nhưng giao dịch quá lớn làm tăng thời gian giữ khóa, lượng log và chi phí rollback.
- Ghi theo lô có thể tăng thông lượng, nhưng kích thước lô quá lớn làm tăng độ trễ của từng phần tử và mức công việc phải thử lại khi lỗi.
- Ghi bất đồng bộ ở tầng ứng dụng có thể giúp phản hồi nhanh hơn, nhưng cần hàng đợi bền vững, cơ chế retry, xử lý trùng lặp và theo dõi trạng thái hoàn tất.

Không được báo cho người dùng rằng một thay đổi đã lưu thành công nếu hệ thống mới chỉ đưa nó vào bộ đệm hoặc hàng đợi mà chưa đáp ứng cam kết lưu trữ của nghiệp vụ.

## 7. Dung lượng lưu trữ, I/O và nén dữ liệu

Dung lượng ảnh hưởng trực tiếp đến chi phí lưu trữ, thời gian sao lưu, phục hồi và lượng dữ liệu phải đọc. Bảng có hàng rộng, nhiều cột ít dùng và nhiều chỉ mục có thể làm tăng số trang cần xử lý.

Nén dữ liệu thường giảm dung lượng và lượng I/O, đặc biệt với dữ liệu có tính lặp hoặc văn bản. Đổi lại, hệ thống phải dùng CPU để nén và giải nén. Nếu workload bị giới hạn bởi I/O, nén có thể cải thiện hiệu năng; nếu CPU đã bão hòa, nén có thể làm truy vấn chậm hơn. Hiệu quả còn phụ thuộc vào kiểu dữ liệu và cách hệ quản trị tổ chức lưu trữ.

Kho dữ liệu dạng hàng phù hợp với nhiều thao tác giao dịch cần đọc hoặc cập nhật một số cột của một hàng. Kho dạng cột có thể hiệu quả cho truy vấn phân tích đọc một số cột trên lượng lớn hàng. Chọn mô hình lưu trữ theo kiểu truy cập, không chỉ theo kích thước dữ liệu.

Phân vùng (partitioning) chia một bảng lớn thành các phần theo khóa hoặc phạm vi. Khi điều kiện truy vấn khớp với khóa phân vùng, hệ quản trị có thể bỏ qua các phân vùng không liên quan (partition pruning). Phân vùng cũng giúp quản lý dữ liệu theo thời gian, chẳng hạn lưu trữ hoặc xóa dữ liệu cũ theo lô. Tuy nhiên, phân vùng không tự động làm mọi truy vấn nhanh hơn; truy vấn không lọc theo khóa phân vùng vẫn có thể phải truy cập nhiều phân vùng, và mỗi phân vùng có thể tạo thêm chi phí quản trị.

Nên theo dõi riêng dung lượng bảng, chỉ mục, log giao dịch và bản sao. Một chỉ mục mới có thể làm truy vấn nhanh hơn nhưng cũng kéo dài thời gian backup, tăng lượng dữ liệu sao chép và làm tăng I/O ghi. Đánh giá đầy đủ phải tính cả những chi phí vận hành này.

## 8. SQL và kế hoạch thực thi

SQL mô tả kết quả cần lấy; bộ tối ưu truy vấn chọn cách thực hiện dựa trên cấu trúc dữ liệu, chỉ mục, thống kê và ước lượng chi phí. Vì vậy, hai câu SQL có cùng kết quả logic có thể có hiệu năng rất khác nhau.

Một số nguyên tắc thường hữu ích:

- Chỉ chọn các cột cần dùng thay vì luôn dùng `SELECT *`, đặc biệt với bảng có cột lớn.
- Dùng điều kiện có thể tận dụng chỉ mục. Bọc cột trong hàm hoặc chuyển đổi kiểu dữ liệu có thể khiến một số chỉ mục thông thường không được sử dụng.
- Tránh truy vấn N+1 từ tầng ứng dụng; lấy dữ liệu theo lô hoặc dùng join phù hợp khi cần.
- Dùng phân trang theo khóa (keyset pagination) cho tập dữ liệu lớn thay vì bỏ qua một số lượng hàng ngày càng lớn bằng `OFFSET`.
- Kiểm tra kiểu dữ liệu của tham số để tránh ép kiểu không cần thiết trên cột được lọc.
- Chỉ thêm `ORDER BY` khi cần thứ tự xác định; nếu dùng `LIMIT`, thứ tự nên có khóa phân biệt để kết quả ổn định.

Ví dụ phân trang theo khóa:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = ?
  AND (created_at, order_id) < (?, ?)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Truy vấn này cần chỉ mục có thứ tự cột phù hợp, chẳng hạn `(customer_id, created_at DESC, order_id DESC)`. Cú pháp so sánh tuple và cách tối ưu có thể khác nhau giữa các hệ quản trị; hãy xác minh bằng kế hoạch thực thi trên hệ thống đang dùng.

Kế hoạch thực thi cho biết cơ sở dữ liệu dự định hoặc đã thực hiện các bước như quét bảng, quét chỉ mục, join, sort và aggregate. Khi phân tích, cần xem:

1. Loại truy cập dữ liệu: sequential scan, index scan, index-only scan hoặc cách tương đương.
2. Số hàng ước lượng so với số hàng thực tế.
3. Số lần một node được chạy và số hàng đi qua node đó.
4. Chi phí sort, hash join, aggregate và việc tràn dữ liệu trung gian ra đĩa.
5. Thời gian chờ I/O, khóa hoặc các tài nguyên khác nếu công cụ cung cấp.

Nếu số hàng thực tế lệch xa ước lượng, thống kê có thể đã cũ hoặc chưa mô tả tốt phân bố dữ liệu. Cập nhật thống kê có thể giúp bộ tối ưu chọn kế hoạch phù hợp hơn. Nhưng không nên ép dùng một chỉ mục chỉ vì tên kế hoạch có vẻ tốt; hãy so sánh thời gian, số hàng đọc và tài nguyên tiêu thụ dưới workload đại diện.

## 9. Ví dụ lựa chọn đánh đổi cho bảng đơn hàng

Giả sử bảng `orders` có các cột `order_id`, `customer_id`, `created_at`, `status` và `total_amount`. Ứng dụng thường hiển thị 20 đơn hàng mới nhất của một khách hàng, đồng thời cập nhật `status` khi đơn hàng chuyển trạng thái.

Một chỉ mục `(customer_id, created_at DESC)` có thể giảm chi phí tìm và sắp xếp 20 đơn hàng mới nhất. Đổi lại, mỗi đơn hàng mới phải cập nhật chỉ mục và chỉ mục chiếm thêm dung lượng.

Nếu thêm `status` và `total_amount` vào chỉ mục bao phủ, truy vấn đọc có thể giảm việc truy cập bảng. Nhưng `status` là cột thường xuyên thay đổi trong workload giả định này; việc đưa nó vào chỉ mục có thể làm tăng chi phí ghi. Có thể chỉ đưa `total_amount` vào nếu dữ liệu này ít thay đổi và lợi ích đọc đã được đo chứng minh.

Nếu tạo bảng tổng hợp số đơn theo trạng thái để phục vụ dashboard, dashboard có thể đọc nhanh hơn. Tuy nhiên, thao tác tạo đơn hoặc đổi trạng thái phải cập nhật số tổng hợp. Nếu cập nhật bất đồng bộ, dashboard có thể hiển thị số liệu trễ; nếu cập nhật đồng bộ, giao dịch ghi có thể dài hơn.

Nếu cache kết quả dashboard trong 30 giây, tải đọc lên cơ sở dữ liệu có thể giảm. Đổi lại, người dùng có thể nhìn thấy số liệu cũ trong khoảng thời gian đó. Khoảng thời gian này chỉ phù hợp nếu nghiệp vụ chấp nhận độ trễ tương ứng.

Ví dụ cho thấy không có một cấu hình tối ưu cho mọi hệ thống. Lựa chọn phụ thuộc vào tần suất đọc, tần suất cập nhật trạng thái, mức mới của dashboard được yêu cầu và ngân sách dung lượng.

## 10. Quy trình chọn và kiểm chứng một thay đổi

Một quy trình tối ưu an toàn nên đi theo các bước có thể lặp lại:

1. **Đặt mục tiêu đo được.** Ví dụ: giảm p95 của truy vấn danh sách đơn hàng từ 450 ms xuống dưới 150 ms ở tải 300 yêu cầu/giây, đồng thời không làm thông lượng ghi giảm quá ngưỡng đã thống nhất.
2. **Ghi nhận baseline.** Lưu thời gian truy vấn, kế hoạch thực thi, số hàng đọc, CPU, I/O, lock wait, cache hit và dung lượng hiện tại.
3. **Xác định nút thắt.** Phân biệt truy vấn đọc nhiều trang, kế hoạch join kém, thiếu bộ nhớ, I/O bão hòa hay tranh chấp giao dịch.
4. **Thay đổi một yếu tố chính.** Có thể thử một chỉ mục, sửa SQL, thay kích thước lô hoặc điều chỉnh cache. Thay từng yếu tố giúp biết nguyên nhân của kết quả.
5. **Đo lại trên cùng điều kiện.** Dùng cùng dữ liệu, mẫu truy vấn, số kết nối và thời gian chạy. Đợi hệ thống đạt trạng thái ổn định để tránh kết quả chỉ phản ánh cache vừa được làm nóng.
6. **Kiểm tra cả mặt trái.** Đo thời gian ghi, dung lượng chỉ mục, log, replication lag, lock wait và tỷ lệ lỗi, không chỉ đo truy vấn được tối ưu.
7. **Kiểm tra tính đúng đắn.** So sánh kết quả truy vấn, kiểm tra ràng buộc nghiệp vụ, thử tải đồng thời và xác minh hành vi sau lỗi nếu thay đổi ảnh hưởng đến commit hoặc sao chép.
8. **Triển khai có khả năng hoàn tác.** Theo dõi chỉ số sau triển khai; giữ phương án gỡ chỉ mục hoặc khôi phục cấu hình nếu mục tiêu không đạt.

Không nên kết luận một thay đổi thành công chỉ vì thời gian một câu SQL giảm trong môi trường phát triển. Kết quả phải được xác nhận dưới tải gần với thực tế và phải xem xét toàn bộ đường đi của dữ liệu.

## 11. Bảng tham khảo các đánh đổi thường gặp

| Lựa chọn | Tác động lên đọc | Tác động lên ghi | Dung lượng và tài nguyên | Điều cần kiểm soát |
|---|---|---|---|---|
| Thêm chỉ mục | Thường nhanh hơn với truy vấn phù hợp | Tốn thêm công cập nhật chỉ mục | Tăng dung lượng và I/O ghi | Mức sử dụng, độ rộng, thứ tự cột |
| Chỉ mục bao phủ | Có thể tránh đọc hàng trong bảng | Tăng chi phí khi cột chỉ mục thay đổi | Tốn thêm dung lượng | Chỉ đưa vào cột thật sự cần thiết |
| Cache | Giảm truy vấn và I/O lặp lại | Cần invalidation hoặc cập nhật cache | Dùng thêm RAM | Độ trễ dữ liệu, cache miss, cache stampede |
| Phi chuẩn hóa | Giảm join và phép tính khi đọc | Tăng công việc duy trì bản sao | Lưu trữ dữ liệu lặp | Quy tắc đồng bộ và tính đúng đắn |
| Khung nhìn vật hóa | Đọc kết quả tổng hợp nhanh | Tốn chi phí làm mới | Lưu thêm kết quả | Lịch làm mới và độ trễ được phép |
| Mức cô lập cao hơn | Có thể tăng thời gian chờ hoặc retry | Có thể giảm thông lượng khi tranh chấp | Tăng công việc điều phối | Bất biến nghiệp vụ và lỗi serialization |
| Commit bền vững, sao chép đồng bộ | Không trực tiếp làm truy vấn đọc nhanh hơn | Có thể tăng độ trễ commit | Tăng hoạt động log và mạng | RPO, RTO và hành vi khi bản sao lỗi |
| Nén dữ liệu | Có thể giảm I/O đọc | Có thể tăng CPU khi ghi | Giảm dung lượng | CPU, kiểu dữ liệu và tỷ lệ nén |
| Phân vùng | Có thể giảm dữ liệu cần quét khi lọc đúng khóa | Có thêm chi phí quản lý phân vùng | Có thể tăng đối tượng quản trị | Partition pruning và phân bố dữ liệu |

## 12. Nguyên tắc ra quyết định

Khi phải lựa chọn giữa đọc, ghi, dung lượng, nhất quán và độ bền, hãy bắt đầu từ yêu cầu nghiệp vụ:

- Nếu người dùng cần tra cứu nhanh và dữ liệu ít thay đổi, chỉ mục phù hợp hoặc cache có thể là lựa chọn tốt.
- Nếu hệ thống ghi liên tục, cần hạn chế chỉ mục không cần thiết, cột chỉ mục thường xuyên cập nhật và giao dịch quá lớn.
- Nếu dashboard chấp nhận số liệu trễ, bảng tổng hợp hoặc cache có thể giảm tải đọc; phải công bố và kiểm soát độ trễ đó.
- Nếu dữ liệu liên quan đến tiền, tồn kho, quyền truy cập hoặc trạng thái đơn hàng, hãy bảo vệ bất biến bằng giao dịch và cơ chế nhất quán phù hợp.
- Nếu xác nhận giao dịch đồng nghĩa với cam kết không mất dữ liệu, không được giảm mức flush hoặc sao chép đồng bộ mà chưa đánh giá lại cam kết độ bền.
- Nếu chi phí lưu trữ tăng nhanh, hãy xem xét chỉ mục dư thừa, dữ liệu lịch sử, nén và chiến lược phân vùng trước khi chỉ mở rộng dung lượng.

Hiệu năng tốt là hiệu năng đáp ứng được SLO của workload với chi phí vận hành và mức rủi ro có thể chấp nhận. Không có chỉ mục, cache, mức cô lập hay cấu hình commit nào luôn tối ưu. Mọi lựa chọn cần được giải thích bằng số đo, kiểm tra tác động lên các thao tác liên quan và xác minh rằng dữ liệu vẫn đúng sau khi thay đổi.
