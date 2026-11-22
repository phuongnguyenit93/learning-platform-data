# Thiết kế giả thuyết và thay đổi từng yếu tố trong mỗi thí nghiệm

Tối ưu hiệu năng cơ sở dữ liệu là quá trình kiểm chứng bằng số liệu. Một thay đổi chỉ đáng giữ lại khi ta có thể giải thích vấn đề cần xử lý, dự đoán tác động, đo kết quả trong điều kiện có thể so sánh và xác nhận rằng hệ thống vẫn trả về dữ liệu đúng. Thiết kế giả thuyết và thay đổi từng yếu tố trong mỗi thí nghiệm giúp tách tác động của một điều chỉnh khỏi ảnh hưởng của tải, dữ liệu, cache, môi trường và những thay đổi khác.

Bài học thuộc chương **Phương pháp đo** của module **DATABASE_PERFORMANCE**. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; các chủ đề liên quan gồm thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, mỗi thí nghiệm trong bài cần gắn một thay đổi kỹ thuật với cơ chế hoạt động của cơ sở dữ liệu và các chỉ số phản ánh cả hiệu năng lẫn chi phí.

## 1. Vì sao cần giả thuyết trước khi thay đổi?

Khi một truy vấn chậm, có nhiều cách can thiệp: thêm chỉ mục, viết lại câu SQL, thay đổi thứ tự phép nối, tăng bộ nhớ, tăng số kết nối hoặc thay đổi mức đồng thời. Nếu thực hiện nhiều thay đổi cùng lúc rồi thấy truy vấn nhanh hơn, ta không biết thay đổi nào tạo ra cải thiện, thay đổi nào không có tác dụng, và thay đổi nào làm phát sinh chi phí khác.

Một giả thuyết tốt giúp trả lời trước khi thử nghiệm:

- **Vấn đề quan sát được là gì?** Ví dụ p95 của một truy vấn đọc tăng, số lần đọc vật lý cao hoặc nhiều phiên chờ cùng một khóa.
- **Nguyên nhân có khả năng là gì?** Ví dụ truy vấn phải quét nhiều hàng do thiếu chỉ mục phù hợp với điều kiện lọc.
- **Ta sẽ thay đổi yếu tố nào?** Ví dụ thêm một chỉ mục có thứ tự cột phù hợp với điều kiện lọc và sắp xếp.
- **Cơ chế nào dự kiến tạo ra tác động?** Bộ tối ưu có thể dùng chỉ mục để tìm tập hàng nhỏ hơn, giảm số trang phải đọc.
- **Kết quả nào xác nhận hoặc bác bỏ giả thuyết?** Ví dụ số hàng/trang đọc giảm và p95 cải thiện trong cùng workload, trong khi chi phí ghi và dung lượng chỉ mục vẫn chấp nhận được.

Giả thuyết không phải lời khẳng định rằng thay đổi chắc chắn thành công. Nó là dự đoán có thể kiểm tra và có tiêu chí để chấp nhận, bác bỏ hoặc yêu cầu thêm dữ liệu. Nếu kết quả không như dự đoán, ta học được điều gì đó về hệ thống thay vì phải đoán nguyên nhân sau sự việc.

## 2. Phân biệt giả thuyết, biến và kết quả

Một thí nghiệm hiệu năng có các thành phần sau:

| Thành phần | Ý nghĩa | Ví dụ trong cơ sở dữ liệu |
|---|---|---|
| Vấn đề | Hiện tượng cần giải quyết, được mô tả bằng số liệu | p95 truy vấn tìm đơn hàng là 900 ms ở tải đỉnh |
| Giả thuyết nguyên nhân | Cơ chế có thể giải thích hiện tượng | Điều kiện lọc làm truy vấn đọc quá nhiều hàng |
| Biến độc lập | Yếu tố chủ động thay đổi | Bổ sung một chỉ mục cho cột lọc và cột sắp xếp |
| Biến phụ thuộc | Kết quả được đo để đánh giá | p95, số hàng đọc, số lần đọc trang, CPU mỗi truy vấn |
| Biến kiểm soát | Điều kiện cần giữ ổn định để so sánh | Dữ liệu, câu truy vấn, tham số, tốc độ tải, phiên bản DB |
| Tiêu chí quyết định | Điều kiện để kết luận | p95 giảm và chi phí ghi/dung lượng tăng trong giới hạn cho phép |

**Biến độc lập** là yếu tố ta thay đổi có chủ đích. **Biến phụ thuộc** là kết quả có thể bị ảnh hưởng bởi thay đổi đó. **Biến kiểm soát** là các điều kiện cần cố định hoặc ghi nhận để tránh nhầm lẫn. Trong thí nghiệm thực tế, không phải mọi yếu tố đều giữ cố định tuyệt đối được; khi đó cần đo, ghi lại và đưa sai khác vào phần giới hạn của kết luận.

Ví dụ, nếu muốn đánh giá tác động của một chỉ mục, biến độc lập là trạng thái có/không có chỉ mục. Các kết quả có thể đo gồm thời gian thực thi, số hàng đọc, số trang đọc, CPU và độ trễ ở các phân vị. Những điều kiện như dữ liệu, câu SQL, tham số, mức đồng thời, cấu hình máy chủ và trạng thái cache phải tương đương giữa hai lần đo.

## 3. Viết giả thuyết có thể kiểm chứng

Một giả thuyết hữu ích cần cụ thể, có cơ chế hợp lý và có thể bị bác bỏ. Có thể dùng mẫu câu:

> Khi **[điều kiện/workload]**, nếu thay đổi **[một yếu tố]**, thì **[chỉ số/kết quả]** sẽ thay đổi theo **[hướng và mức kỳ vọng]**, vì **[cơ chế kỹ thuật]**. Ta chấp nhận kết quả nếu **[tiêu chí hiệu năng]** đạt được và **[giới hạn về tính đúng đắn/chi phí]** vẫn được đáp ứng.

Ví dụ:

> Với truy vấn tìm đơn hàng theo `customer_id` và sắp xếp theo `created_at`, nếu thêm chỉ mục ghép theo hai cột này, số hàng cần đọc và p95 sẽ giảm vì cơ sở dữ liệu có thể định vị các hàng phù hợp và đọc theo thứ tự chỉ mục. Ta chấp nhận thay đổi nếu p95 giảm rõ ràng ở workload đại diện, kết quả truy vấn không đổi, thời gian ghi và dung lượng chỉ mục vẫn nằm trong ngân sách.

Giả thuyết trên có thể kiểm chứng bằng cách chạy cùng truy vấn trên cùng dữ liệu trước và sau khi thêm chỉ mục, thu thập kế hoạch thực thi và các chỉ số đọc. Nó cũng có thể bị bác bỏ: bộ tối ưu không chọn chỉ mục, số hàng đọc không giảm, truy vấn bị giới hạn bởi I/O khác, hoặc chi phí ghi tăng quá mức.

Tránh những giả thuyết mơ hồ như “thêm chỉ mục sẽ làm database nhanh hơn” hoặc “tăng bộ nhớ sẽ cải thiện hiệu năng”. Chúng không chỉ rõ workload nào, chỉ số nào, cơ chế nào và điều kiện nào quyết định thành công.

### 3.1. Nêu rõ phạm vi và điều kiện áp dụng

Một thay đổi có thể giúp một truy vấn nhưng làm workload tổng thể chậm hơn. Vì vậy, giả thuyết cần xác định phạm vi đo:

- Một câu SQL cụ thể hay toàn bộ nhóm truy vấn?
- Chỉ tải đọc hay cả tải đọc/ghi?
- Dữ liệu nóng trong cache hay dữ liệu lớn hơn bộ nhớ?
- Tải bình thường, tải đỉnh hay mức đồng thời tăng dần?
- Một máy chủ, một shard hay toàn bộ cụm?

Phạm vi càng rõ thì kết luận càng chính xác. Nếu thử nghiệm chỉ chạy một truy vấn đơn lẻ, không được suy ra rằng throughput của toàn hệ thống cũng sẽ tăng. Nếu thay đổi chỉ có tác dụng khi dữ liệu lớn hơn cache, bài thử với tập dữ liệu nhỏ không đủ để kiểm chứng giả thuyết.

## 4. Nguyên tắc thay đổi một yếu tố trong mỗi thí nghiệm

Trong phương pháp một yếu tố mỗi lần (one factor at a time), ta giữ các điều kiện liên quan ổn định và chỉ chủ động thay đổi một yếu tố chính. Sau khi đo xong, ta so sánh kết quả với đường cơ sở.

Ví dụ, muốn đánh giá việc bổ sung chỉ mục:

1. Đo truy vấn khi chưa có chỉ mục mới.
2. Ghi lại kế hoạch thực thi, thời gian, số hàng/trang đọc, CPU và các chỉ số liên quan.
3. Tạo đúng một chỉ mục đã nêu trong giả thuyết.
4. Chạy lại cùng truy vấn với cùng tham số và điều kiện tải.
5. Đo lại cùng bộ chỉ số và kiểm tra kế hoạch thực thi.
6. So sánh cả lợi ích đọc lẫn chi phí ghi, dung lượng và thời gian bảo trì chỉ mục.

Nếu cùng lúc thêm chỉ mục, viết lại SQL, tăng bộ nhớ và thay đổi pool kết nối, kết quả không còn cho biết yếu tố nào tạo ra tác động. Bởi vậy, hãy tách chúng thành các thí nghiệm có giả thuyết và đường cơ sở riêng.

“Một yếu tố” ở đây là một thay đổi được xác định rõ về mặt kỹ thuật. Ví dụ tạo một chỉ mục ghép gồm hai cột được xem là một thay đổi cấu trúc chỉ mục, nhưng không nên đồng thời thay đổi câu SQL và cấu hình cache. Nếu một thay đổi bắt buộc phải gồm nhiều bước phụ thuộc để hệ thống hoạt động, cần ghi rõ toàn bộ gói thay đổi là một can thiệp và giới hạn kết luận trong phạm vi gói đó.

### 4.1. Điều kiện cần giữ ổn định

Các yếu tố gây nhiễu thường gặp trong thí nghiệm cơ sở dữ liệu gồm:

| Yếu tố | Cách kiểm soát hoặc ghi nhận |
|---|---|
| Dữ liệu | Dùng cùng snapshot hoặc bản sao dữ liệu tương đương; ghi kích thước bảng và phân bố dữ liệu |
| Truy vấn | Giữ nguyên SQL, tham số, kiểu dữ liệu và cách gọi |
| Tải | Giữ tốc độ đến, tỷ lệ đọc/ghi, số máy khách và thời lượng tương đương |
| Cache | Xác định rõ thử nghiệm cache nóng hay lạnh; áp dụng cùng quy trình giữa các lần đo |
| Môi trường | Giữ phiên bản DB, cấu hình, phần cứng và giới hạn tài nguyên tương đương |
| Trạng thái nền | Ghi nhận backup, vacuum, checkpoint, tác vụ bảo trì và workload khác |
| Thời điểm | Tránh so sánh hai giai đoạn có tải nền khác nhau; ghi lại thời gian chạy |
| Tính đúng đắn | So sánh số hàng, giá trị trả về và các bất biến nghiệp vụ |

Không phải lúc nào cũng có thể đóng băng toàn bộ hệ thống. Nếu workload sản xuất tiếp tục thay đổi, hãy dùng môi trường thử nghiệm có dữ liệu và cấu hình đại diện, hoặc chạy các lần đo xen kẽ đủ gần nhau để giảm ảnh hưởng của xu hướng tải. Ghi lại mọi khác biệt có thể làm thay đổi kết quả.

### 4.2. Thứ tự thử nghiệm và trạng thái cache

Lần chạy đầu có thể chậm do nạp dữ liệu vào cache, biên dịch truy vấn, khởi tạo kết nối hoặc tạo thống kê. Nếu luôn chạy cấu hình A trước và cấu hình B sau, B có thể được hưởng lợi từ cache nóng. Khi phù hợp, hãy chạy giai đoạn làm nóng riêng, lặp lại nhiều lượt và luân phiên thứ tự đo A/B để giảm thiên lệch thứ tự.

Không xóa cache một cách tùy tiện trên hệ thống đang phục vụ người dùng. Nếu mục tiêu là đo cache lạnh, thực hiện trong môi trường kiểm soát và mô tả chính xác cách tạo trạng thái đó. Nếu mục tiêu là mô phỏng hoạt động thường ngày, hãy dùng quy trình warm-up nhất quán và đo khi workload đã đạt trạng thái ổn định.

## 5. Thiết lập đường cơ sở trước khi can thiệp

Đường cơ sở (baseline) là kết quả đo trước thay đổi, dùng làm mốc so sánh. Một baseline có giá trị cần mô tả workload và điều kiện chạy, không chỉ có một con số thời gian.

Trước thí nghiệm, ghi lại tối thiểu:

- Mục tiêu nghiệp vụ và truy vấn hoặc workload cần cải thiện.
- Câu SQL, tham số đại diện, số hàng dự kiến và kích thước dữ liệu.
- Tốc độ yêu cầu, mức đồng thời, tỷ lệ đọc/ghi và thời lượng đo.
- Kế hoạch thực thi và thống kê quan trọng của truy vấn.
- Thời gian thực thi, p50/p95/p99 nếu có đủ mẫu, throughput và tỷ lệ lỗi.
- CPU, bộ nhớ, cache, đọc/ghi lưu trữ, wait events, khóa và kết nối liên quan.
- Cấu hình DB, phiên bản phần mềm và các tác vụ nền trong thời gian đo.

Chọn chỉ số theo giả thuyết. Nếu nghi ngờ truy vấn đọc quá nhiều trang, số lần đọc logic/vật lý và số hàng được xử lý quan trọng hơn một chỉ số CPU tổng thể. Nếu nghi ngờ tranh chấp khóa, thời gian chờ khóa và giao dịch chặn quan trọng hơn throughput của một truy vấn chạy đơn lẻ.

### 5.1. Dùng nhiều thước đo để tránh kết luận sai

Không nên quyết định chỉ dựa trên thời gian trung bình. Kết hợp các góc nhìn:

- **Độ trễ:** thời gian thực thi và p50/p95/p99 để thấy cả trải nghiệm phổ biến lẫn phần đuôi chậm.
- **Thông lượng:** số truy vấn hoặc giao dịch hoàn thành mỗi giây.
- **Công việc thực hiện:** số hàng đọc, số trang đọc, số lần truy cập bảng, số lần sort hoặc spill ra đĩa.
- **Tài nguyên:** CPU, bộ nhớ, I/O, cache và thời gian chờ.
- **Tác động phụ:** thời gian ghi, dung lượng chỉ mục, deadlock, lỗi, timeout và chi phí bảo trì.

Một truy vấn nhanh hơn khi chạy riêng có thể làm throughput tổng thể giảm nếu nó tiêu thụ nhiều bộ nhớ hoặc tăng tranh chấp. Một chỉ mục có thể giảm thời gian đọc nhưng làm thao tác ghi chậm hơn. Đánh giá phải bao gồm cả workload chịu tác động và giới hạn vận hành.

### 5.2. Đảm bảo phép đo đủ tin cậy

Lặp lại thí nghiệm để quan sát biến động tự nhiên. Số lượt cần thiết tùy độ nhiễu, thời lượng và mức khác biệt cần phát hiện. Với workload ngắn, một vài lần chạy có thể chưa đủ để phân biệt cải thiện thật với dao động ngẫu nhiên. Với tải dài, cần đo trong khoảng đủ để các chu kỳ checkpoint, dọn dẹp hoặc tác vụ nền quan trọng được thể hiện.

Ghi lại số mẫu, thời gian đo và cách tổng hợp. Khi phân tích phân vị, cần đủ số yêu cầu để p95/p99 có ý nghĩa; không suy luận về phần đuôi từ một tập mẫu rất nhỏ. Nếu kết quả dao động lớn giữa các lượt, hãy tìm nguyên nhân dao động trước khi kết luận.

## 6. Ví dụ thực hành: kiểm tra giả thuyết thêm chỉ mục

Giả sử một màn hình tìm đơn hàng thường xuyên lọc theo khách hàng và hiển thị mới nhất trước. Truy vấn minh họa:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = :customer_id
ORDER BY created_at DESC
LIMIT 50;
```

Kế hoạch hiện tại cho thấy hệ quản trị đọc nhiều hàng của bảng rồi sắp xếp để lấy 50 kết quả. Ta đặt giả thuyết rằng chỉ mục ghép phù hợp với điều kiện lọc và thứ tự sẽ giảm lượng dữ liệu cần đọc.

**Thiết kế thí nghiệm:**

| Thành phần | Thiết lập |
|---|---|
| Vấn đề | Truy vấn có p95 cao và số hàng đọc lớn so với 50 hàng trả về |
| Giả thuyết | Chỉ mục trên `(customer_id, created_at)` giúp định vị và đọc các đơn hàng theo thứ tự cần thiết |
| Yếu tố thay đổi | Chỉ thêm chỉ mục ghép đã chọn |
| Điều kiện giữ nguyên | Dữ liệu, SQL, tham số, tốc độ tải, số máy khách và cấu hình DB |
| Chỉ số chính | p95, thời gian thực thi, số hàng/trang đọc, số lần sort |
| Chỉ số bảo vệ | Thời gian ghi đơn hàng, dung lượng chỉ mục, tốc độ ghi và tính đúng đắn kết quả |
| Tiêu chí quyết định | Cải thiện đọc có thể lặp lại, kết quả không đổi và chi phí ghi/dung lượng chấp nhận được |

Thực hiện theo trình tự:

1. Chạy truy vấn trên tập tham số đại diện trước khi tạo chỉ mục; lưu kế hoạch và số liệu.
2. Chạy workload đủ lâu để đo được phân bố độ trễ, không chỉ một lần thực thi.
3. Tạo chỉ mục trong môi trường thử nghiệm theo cú pháp của hệ quản trị đang dùng.
4. Chờ hệ quản trị hoàn tất tạo chỉ mục và cập nhật thống kê cần thiết theo quy trình vận hành.
5. Chạy lại đúng workload, với cùng dữ liệu và cách khởi tạo cache.
6. So sánh kế hoạch, lượng đọc, sort, p95/p99 và throughput.
7. Đo thêm workload ghi để xác định chi phí duy trì chỉ mục.
8. Kiểm tra kết quả truy vấn trước/sau để chắc chắn không đổi tập hàng hoặc thứ tự theo yêu cầu nghiệp vụ.

Nếu chỉ số đọc cải thiện nhưng workload ghi vượt giới hạn, giả thuyết về lợi ích tổng thể không được chấp nhận nguyên trạng. Có thể cần đánh giá lại thiết kế chỉ mục hoặc phạm vi workload. Nếu kế hoạch không dùng chỉ mục mới, cần xem thống kê, độ chọn lọc, kiểu dữ liệu, thứ tự cột và chi phí ước tính của bộ tối ưu trước khi kết luận.

## 7. Ví dụ thực hành: kiểm tra thay đổi SQL

Một truy vấn dùng hàm trên cột lọc, khiến chỉ mục hiện có khó được sử dụng theo cách mong muốn. Ta muốn thử viết lại điều kiện để giữ nguyên ý nghĩa nhưng cho phép tìm kiếm theo khoảng giá trị.

Trong thí nghiệm này, biến độc lập là cách biểu diễn điều kiện SQL. Giữ nguyên chỉ mục, dữ liệu, tham số, mức tải và cấu hình. Đo kế hoạch thực thi, số hàng đọc, thời gian và kết quả trả về ở cả hai phiên bản.

Không được thay đổi cùng lúc cả SQL và chỉ mục. Nếu làm vậy, ta không xác định được cải thiện đến từ biểu thức mới hay cấu trúc chỉ mục. Cũng cần kiểm tra ngữ nghĩa: xử lý `NULL`, múi giờ, collation, độ chính xác thời gian và ranh giới khoảng có thể khiến câu SQL viết lại trả về tập kết quả khác.

Một thay đổi SQL chỉ được xem là hợp lệ khi vừa cải thiện chỉ số đã chọn, vừa giữ đúng kết quả nghiệp vụ trên các trường hợp biên. Nếu tốc độ tăng nhưng kết quả sai, thí nghiệm thất bại.

## 8. Ví dụ thực hành: kiểm tra tranh chấp giao dịch

Giả sử nhiều phiên cùng cập nhật một bản ghi tổng hợp. Một giả thuyết có thể là thời gian giữ giao dịch dài khiến các phiên khác phải chờ khóa. Thí nghiệm có thể thay đổi duy nhất phạm vi giao dịch để giảm thời gian giữ khóa, trong khi giữ nguyên thứ tự nghiệp vụ và khối lượng yêu cầu.

Đo thời gian giao dịch, thời gian chờ khóa, số phiên bị chặn, deadlock, throughput và độ trễ p95/p99. Đồng thời kiểm tra tính nguyên tử và nhất quán của nghiệp vụ: rút ngắn giao dịch bằng cách đưa thao tác ra ngoài transaction có thể làm lộ trạng thái trung gian hoặc khiến dữ liệu cập nhật không còn nhất quán.

Không thay đổi đồng thời isolation level, thứ tự cập nhật và số kết nối. Mỗi thay đổi này tác động đến cơ chế đồng thời khác nhau và cần giả thuyết riêng. Nếu phải kết hợp nhiều điều chỉnh để đảm bảo tính đúng đắn, ghi rõ chúng là một gói thay đổi có quan hệ phụ thuộc và thiết kế phép đo cho cả gói.

## 9. Đọc kết quả và ra quyết định

Sau khi chạy thí nghiệm, đối chiếu kết quả với giả thuyết và tiêu chí đã xác định trước. Có bốn tình huống thường gặp:

| Kết quả | Cách diễn giải | Hành động tiếp theo |
|---|---|---|
| Chỉ số chính cải thiện, chỉ số bảo vệ vẫn đạt | Giả thuyết được hỗ trợ trong phạm vi đã thử | Lưu cấu hình, ghi kết quả và lên kế hoạch triển khai có kiểm soát |
| Chỉ số chính không đổi | Thay đổi không tác động như dự đoán hoặc phép đo chưa đủ nhạy | Kiểm tra kế hoạch, cơ chế, chất lượng dữ liệu và độ tin cậy phép đo |
| Chỉ số chính xấu đi | Giả thuyết bị bác bỏ hoặc có tác động phụ lớn | Khôi phục trạng thái trước, phân tích nguyên nhân và lưu bài học |
| Có lợi cho một workload nhưng hại workload khác | Tác động phụ thuộc loại tải | Đánh giá trọng số workload và mục tiêu dịch vụ trước khi quyết định |

Không chọn kết quả thuận lợi nhất trong nhiều lần chạy rồi bỏ qua các lần còn lại. Hãy báo cáo số lượt đo, độ biến động và các trường hợp bất thường. Nếu kết quả không nhất quán, ghi nhận là chưa đủ bằng chứng thay vì khẳng định thành công.

### 9.1. Phân biệt tương quan và quan hệ nhân quả

Hai chỉ số cùng thay đổi không chứng minh một chỉ số gây ra chỉ số kia. Ví dụ p95 giảm sau khi thêm chỉ mục có thể trùng với thời điểm tải nền giảm. Để tăng độ tin cậy về quan hệ nhân quả, hãy:

- Chỉ định rõ một yếu tố can thiệp.
- Giữ hoặc đo các điều kiện quan trọng khác.
- Lặp lại trong cùng workload và môi trường tương đương.
- Quan sát cơ chế trung gian mà giả thuyết dự đoán, như số trang đọc hoặc trạng thái chờ.
- Kiểm tra tác động ở các workload liên quan và trong khoảng thời gian đủ dài.

Nếu có thể, dùng môi trường thử nghiệm hoặc nhóm đối chứng phù hợp để so sánh. Không triển khai thử nghiệm có rủi ro dữ liệu trên hệ thống sản xuất chỉ để tạo đối chứng.

### 9.2. Khi các yếu tố tương tác với nhau

Phương pháp thay đổi một yếu tố mỗi lần dễ giải thích và phù hợp cho nhiều bước điều tra ban đầu, nhưng có giới hạn: nó có thể bỏ sót tương tác giữa hai yếu tố. Ví dụ, một chỉ mục chỉ phát huy hiệu quả khi truy vấn được viết lại để dùng điều kiện tương thích; hoặc tăng bộ nhớ chỉ có tác dụng khi workload có đủ tính cục bộ dữ liệu.

Khi đã hiểu từng yếu tố riêng lẻ, nếu nghi ngờ có tương tác, có thể thiết kế thí nghiệm nhiều yếu tố có kiểm soát, chẳng hạn ma trận các tổ hợp cấu hình. Khi đó cần ghi rõ đây là một thiết kế thí nghiệm khác, xác định trước các tổ hợp và cách phân tích. Không nên âm thầm thay nhiều yếu tố trong một lần chạy rồi gọi đó là phép thử một yếu tố.

## 10. Ghi chép thí nghiệm để có thể lặp lại

Một thí nghiệm cần để lại đủ thông tin cho người khác tái hiện và đánh giá. Có thể dùng mẫu sau cho mỗi lần thử:

```text
Mã thí nghiệm:
Ngày/giờ và người thực hiện:
Mục tiêu nghiệp vụ:
Vấn đề và số liệu baseline:
Workload, dữ liệu và tham số:
Giả thuyết nguyên nhân:
Yếu tố duy nhất được thay đổi:
Cơ chế dự kiến:
Điều kiện kiểm soát và sai khác đã biết:
Phiên bản DB, cấu hình và môi trường:
Số lượt chạy, warm-up và thời lượng đo:
Chỉ số chính và tiêu chí thành công:
Chỉ số bảo vệ/tác động phụ:
Kết quả trước và sau:
Kế hoạch thực thi và thống kê liên quan:
Kết luận: được hỗ trợ / bị bác bỏ / chưa đủ bằng chứng:
Quyết định và cách khôi phục:
Giới hạn của phép đo:
```

Lưu cả cấu hình và truy vấn dùng để thử, nhưng tránh ghi thông tin nhạy cảm hoặc dữ liệu định danh vào báo cáo không được bảo vệ. Với workload có tham số nhạy cảm, có thể lưu bộ tham số đã ẩn danh nhưng vẫn giữ đặc tính phân bố cần thiết cho thử nghiệm.

## 11. An toàn khi thực hiện thí nghiệm

Thử nghiệm cơ sở dữ liệu có thể tạo tải, chiếm dung lượng, giữ khóa hoặc thay đổi cấu trúc dữ liệu. Trước khi thực hiện, cần hiểu phạm vi ảnh hưởng và cách khôi phục:

- Ưu tiên môi trường thử nghiệm có dữ liệu đại diện và cấu hình tương đương.
- Với thao tác tạo/xóa chỉ mục hoặc thay đổi cấu trúc, đánh giá dung lượng, thời gian chạy, khóa và ảnh hưởng đến workload đang phục vụ.
- Không dùng dữ liệu sản xuất nhạy cảm ở nơi không được phép; tuân thủ quy trình sao chép và ẩn danh dữ liệu.
- Xác định cách dừng thí nghiệm, rollback hoặc khôi phục cấu hình trước khi bắt đầu.
- Không chạy thử tải vượt giới hạn đã thống nhất trên hệ thống phục vụ người dùng.
- Sau thay đổi, xác nhận tính đúng đắn dữ liệu và theo dõi các chỉ số bảo vệ trước khi mở rộng phạm vi.

Kế hoạch khôi phục là một phần của thiết kế thí nghiệm. Nếu không thể xác định cách quay lại trạng thái ổn định, cần đánh giá lại phạm vi và rủi ro trước khi thực hiện.

## 12. Những sai lầm thường gặp

- **Không có baseline:** không thể biết kết quả sau thay đổi tốt hơn bao nhiêu hoặc có khác biệt thật hay không.
- **Giả thuyết không đo được:** nhận định chung chung khiến tiêu chí thành công thay đổi sau khi đã thấy kết quả.
- **Thay nhiều yếu tố cùng lúc:** không tách được nguyên nhân của cải thiện hoặc suy giảm.
- **Bỏ qua biến gây nhiễu:** cache, tải nền, dữ liệu hoặc tham số khác nhau làm phép so sánh thiếu công bằng.
- **Chạy một lần rồi kết luận:** dao động ngẫu nhiên hoặc warm-up có thể chi phối kết quả.
- **Chỉ đo truy vấn mục tiêu:** bỏ qua chi phí ghi, bộ nhớ, khóa hoặc workload khác bị ảnh hưởng.
- **Chỉ nhìn thời gian trung bình:** phần đuôi p95/p99 có thể xấu đi dù trung bình tốt hơn.
- **Không kiểm tra tính đúng đắn:** truy vấn nhanh hơn nhưng trả về dữ liệu khác không phải là tối ưu hợp lệ.
- **Không lưu cách thử:** kết quả không thể tái hiện hoặc so sánh ở lần thay đổi tiếp theo.
- **Không có kế hoạch khôi phục:** một thử nghiệm thất bại có thể kéo dài sự cố hoặc để lại cấu hình không ổn định.

## 13. Bài tập tự kiểm tra

### Bài tập 1: Viết giả thuyết cho một truy vấn chậm

Một truy vấn lọc theo `account_id`, sắp xếp theo thời gian và trả về 20 bản ghi. Kế hoạch thực thi cho thấy hệ quản trị đọc hàng trăm nghìn hàng trước khi trả kết quả.

**Yêu cầu:** viết một giả thuyết cho việc bổ sung chỉ mục. Nêu yếu tố thay đổi, cơ chế dự kiến, chỉ số chính và ít nhất hai chỉ số bảo vệ.

**Gợi ý trả lời:** giả thuyết có thể dự đoán một chỉ mục phù hợp với điều kiện lọc và thứ tự sẽ giảm số hàng/trang đọc và p95. Chỉ thay đổi chỉ mục; giữ SQL, dữ liệu, tham số và workload ổn định. Chỉ số bảo vệ có thể gồm thời gian ghi và dung lượng chỉ mục. Cần kiểm tra kế hoạch có dùng chỉ mục và kết quả truy vấn không đổi.

### Bài tập 2: Phát hiện thí nghiệm có biến gây nhiễu

Nhóm thử nghiệm thêm chỉ mục và tăng bộ nhớ cùng lúc. Lần đo sau dùng dữ liệu lớn hơn, nhưng chạy vào giờ tải nền thấp hơn. p95 giảm 35%.

**Câu hỏi:** có thể kết luận chỉ mục làm p95 giảm 35% không? Cần thiết kế lại phép thử như thế nào?

**Gợi ý trả lời:** chưa thể kết luận vì có nhiều yếu tố thay đổi. Tách thành thí nghiệm riêng cho chỉ mục và bộ nhớ; dùng cùng snapshot dữ liệu, workload, tham số và điều kiện cache; ghi nhận tải nền; lặp lại nhiều lượt và so sánh cùng bộ chỉ số.

### Bài tập 3: Đánh giá lợi ích và chi phí

Sau khi thêm chỉ mục, p95 truy vấn đọc giảm 40%, nhưng thời gian ghi tăng 18% và dung lượng lưu trữ tăng đáng kể.

**Câu hỏi:** có nên giữ chỉ mục ngay không?

**Gợi ý trả lời:** cần đối chiếu tỷ trọng đọc/ghi, SLO, ngân sách dung lượng và chi phí vận hành. Thử nghiệm đã cho thấy lợi ích đọc nhưng chưa đủ để quyết định tổng thể nếu chi phí ghi hoặc lưu trữ vượt giới hạn. Đo workload hỗn hợp đại diện và xác định tiêu chí chấp nhận trước khi triển khai.

### Checklist trước khi kết luận một thí nghiệm

- [ ] Vấn đề được mô tả bằng số liệu baseline và workload cụ thể.
- [ ] Giả thuyết nêu rõ cơ chế, biến thay đổi và kết quả dự kiến.
- [ ] Mỗi thí nghiệm chỉ thay đổi một yếu tố chính.
- [ ] Dữ liệu, tham số, tải, cache và môi trường được giữ tương đương hoặc ghi nhận sai khác.
- [ ] Chỉ số chính và chỉ số bảo vệ được xác định trước.
- [ ] Có đủ lượt đo và số mẫu để đánh giá biến động.
- [ ] Kế hoạch thực thi, thống kê và trạng thái chờ được xem xét khi phù hợp.
- [ ] Kết quả truy vấn và các bất biến nghiệp vụ được kiểm tra.
- [ ] Chi phí ghi, bộ nhớ, I/O, dung lượng và workload liên quan được đánh giá.
- [ ] Kết luận nêu rõ phạm vi, giới hạn và cách khôi phục.

Thiết kế giả thuyết rõ ràng và thay đổi từng yếu tố giúp biến tối ưu hiệu năng thành quá trình học hỏi có thể lặp lại. Khi mỗi điều chỉnh đều có cơ chế dự kiến, đường cơ sở, điều kiện kiểm soát và tiêu chí quyết định, nhóm có thể giải thích vì sao một thay đổi hiệu quả, nhận ra khi nào nó gây tác động phụ và xây dựng các quyết định tối ưu dựa trên bằng chứng.
