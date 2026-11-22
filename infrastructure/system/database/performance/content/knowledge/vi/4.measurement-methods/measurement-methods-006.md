# Đo tải đồng thời thay vì suy luận từ một lần chạy đơn lẻ

Một câu SQL chạy nhanh khi chỉ có một phiên kết nối chưa chứng minh rằng hệ thống sẽ đáp ứng tốt khi hàng chục hoặc hàng trăm giao dịch cùng hoạt động. Khi tải đồng thời tăng, các truy vấn bắt đầu chia sẻ CPU, bộ nhớ, bộ đệm, thiết bị lưu trữ, băng thông và các khóa dữ liệu. Thời gian chờ có thể tăng nhanh dù thời gian xử lý riêng của từng câu lệnh gần như không đổi.

Trong module **DATABASE_PERFORMANCE**, tối ưu hiệu năng phải dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Chương **Phương pháp đo** giúp người học thiết kế phép thử đồng thời có thể lặp lại, phân biệt tải kín và tải mở, theo dõi độ trễ ở nhiều phân vị, tìm điểm bão hòa và diễn giải kết quả trong mối liên hệ với SQL, chỉ mục, I/O, bộ nhớ và tranh chấp giao dịch.

Sau bài học, người học có thể:

- Giải thích vì sao một lần chạy đơn lẻ không đại diện cho hiệu năng dưới tải thật.
- Thiết kế tải thử với nhiều phiên, nhiều loại giao dịch và phân bố dữ liệu phù hợp.
- Phân biệt mô hình phát sinh tải kín và tải mở, hiểu ảnh hưởng của từng mô hình đến kết quả.
- Đo thông lượng, p50, p95, p99, lỗi, thời gian chờ và mức sử dụng tài nguyên.
- Nhận biết điểm bão hòa và các dấu hiệu cho thấy tải đang bị giới hạn bởi CPU, bộ nhớ, lưu trữ, mạng hoặc khóa.
- So sánh hai cấu hình dưới điều kiện tương đương và lập báo cáo có thể tái hiện.

## 1. Vì sao cần đo tải đồng thời?

### 1.1. Một lần chạy đơn lẻ chỉ trả lời một phần câu hỏi

Khi chạy một câu truy vấn một lần, ta thường quan sát được thời gian hoàn thành của yêu cầu trong điều kiện cụ thể: số phiên thấp, trạng thái cache tại thời điểm chạy, dữ liệu đang có trên máy và mức tải nền hiện tại. Phép đo này hữu ích để kiểm tra cú pháp, xem kế hoạch thực thi hoặc ước lượng chi phí cơ bản, nhưng không thể trả lời hệ thống sẽ hoạt động thế nào khi nhiều người dùng cùng truy cập.

Ví dụ, một truy vấn tìm đơn hàng theo khách hàng có thể mất 12 ms khi chạy một mình. Khi 80 phiên cùng chạy, thời gian phản hồi có thể tăng lên 180 ms vì các phiên tranh chấp CPU, đọc dữ liệu từ cùng thiết bị, chờ khóa hoặc phải xếp hàng lấy kết nối. Thời gian tăng không nhất thiết do kế hoạch thực thi của truy vấn thay đổi; nguyên nhân có thể nằm ở hàng đợi và tài nguyên dùng chung.

Một phép đo đơn lẻ còn dễ bị ảnh hưởng bởi:

- Cache vừa được làm nóng bởi truy vấn trước.
- Dữ liệu thử quá nhỏ nên gần như luôn nằm trong RAM.
- Tiến trình nền vừa chạy xong hoặc đang hoạt động.
- Kết nối đã được tạo sẵn, trong khi ứng dụng thật phải chờ mở hoặc lấy kết nối từ pool.
- Máy thử tải có cấu hình khác với môi trường thực tế.
- Một lần chạy tình cờ gặp độ trễ mạng thấp hoặc cao.
- Truy vấn được đo không chứa toàn bộ transaction của nghiệp vụ.

Vì thế, cần tách hai câu hỏi: một thao tác tốn bao nhiêu thời gian khi tài nguyên sẵn sàng, và hệ thống phục vụ nhiều thao tác cùng lúc như thế nào.

### 1.2. Tải đồng thời làm thay đổi đường xử lý

Các phiên kết nối dùng chung nhiều thành phần. Khi số phiên hoạt động tăng, những tác động sau có thể xuất hiện:

- CPU phải lập lịch cho nhiều công việc hơn; truy vấn có thể chờ được cấp thời gian xử lý.
- Bộ nhớ cho cache, sort, hash join và trạng thái phiên tăng theo tải.
- Nhiều yêu cầu đọc/ghi cùng lúc làm hàng đợi I/O dài hơn.
- Các phiên cùng cập nhật một dòng hoặc một nhóm dòng có thể phải chờ khóa.
- Số kết nối lớn làm tăng chi phí quản lý phiên và chuyển ngữ cảnh.
- Ứng dụng và DBMS phải truyền nhiều dữ liệu hơn qua mạng.
- Một truy vấn dài có thể giữ tài nguyên hoặc khóa trong lúc các truy vấn ngắn khác đang chờ.

Do đó, thời gian phản hồi dưới tải là kết quả tổng hợp của thời gian phục vụ và thời gian chờ. Chỉ nhìn thời gian thực thi trong một lần chạy riêng lẻ sẽ bỏ qua phần quan trọng này.

### 1.3. Phân biệt độ trễ, thông lượng và mức đồng thời

Ba chỉ số nền tảng cần được theo dõi cùng nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Độ trễ (latency) | Thời gian một yêu cầu cần để hoàn thành | Một transaction mất 120 ms |
| Thông lượng (throughput) | Số yêu cầu hoặc transaction hoàn thành trong một đơn vị thời gian | 450 transaction/giây |
| Mức đồng thời (concurrency) | Số công việc đang hoạt động hoặc đang chờ cùng lúc | 32 client đang phát sinh giao dịch |

Thông lượng cao không đồng nghĩa mọi yêu cầu đều nhanh. Một hệ thống có thể hoàn thành nhiều giao dịch mỗi giây nhưng một nhóm yêu cầu vẫn phải chờ lâu. Ngược lại, độ trễ thấp trong thử nghiệm một client không chứng minh hệ thống có thể duy trì thông lượng cao khi tải tăng.

Cần ghi rõ đơn vị và phạm vi của mỗi chỉ số. “Thời gian truy vấn” có thể là thời gian DBMS thực thi một câu SQL, trong khi “thời gian transaction” gồm nhiều câu lệnh và commit. “Thời gian API” còn có thể gồm thời gian chờ pool, xử lý ứng dụng và truyền kết quả.

### 1.4. Định luật Little và số công việc trong hệ thống

Trong trạng thái ổn định, định luật Little mô tả quan hệ giữa số công việc trung bình trong hệ thống, tốc độ hoàn thành và thời gian một công việc ở trong hệ thống:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\): số yêu cầu trung bình đang ở trong hệ thống.
- \(\lambda\): thông lượng, tính bằng yêu cầu mỗi giây.
- \(W\): thời gian trung bình mỗi yêu cầu ở trong hệ thống, tính bằng giây.

Ví dụ, nếu hệ thống hoàn thành 100 transaction/giây và mỗi transaction mất trung bình 0,2 giây, số transaction trung bình đang ở trong hệ thống xấp xỉ 20.

Quan hệ này giúp ước lượng mức công việc đồng thời cần thiết để duy trì một thông lượng mục tiêu. Tuy nhiên, nó không cho biết mức đồng thời tối đa mà DBMS xử lý hiệu quả. Khi tải vượt năng lực phục vụ, thời gian chờ tăng, số yêu cầu đang tồn tại tăng và hệ thống có thể rơi vào trạng thái quá tải.

Nếu ứng dụng có thời gian nghĩ giữa hai giao dịch, hoặc một client chỉ gửi giao dịch tiếp theo sau khi hoàn tất giao dịch trước, cần phân biệt thời gian DBMS xử lý với thời gian client chờ hoặc nghỉ. Đừng áp dụng một con số concurrency duy nhất cho mọi mô hình tải.

## 2. Thiết kế tải thử nghiệm đại diện

### 2.1. Bắt đầu từ hành vi nghiệp vụ

Một phép thử hữu ích mô phỏng các thao tác mà hệ thống thực sự phải phục vụ. Với ứng dụng bán hàng, tải có thể gồm:

- Đọc danh sách sản phẩm và chi tiết sản phẩm.
- Tìm kiếm đơn hàng theo mã hoặc khách hàng.
- Thêm mặt hàng vào giỏ.
- Xác nhận đơn và trừ tồn kho.
- Cập nhật trạng thái thanh toán.
- Tác vụ nền tổng hợp hoặc đồng bộ dữ liệu.

Không nên chọn một truy vấn dễ chạy rồi dùng nó đại diện cho toàn bộ hệ thống. Tỷ lệ đọc/ghi, kích thước kết quả, số câu SQL trong transaction và mức độ tranh chấp dữ liệu có thể làm thay đổi hoàn toàn đặc tính tải.

Hãy xác định các nhóm thao tác quan trọng, sau đó gán trọng số theo tỷ lệ quan sát được hoặc theo mục tiêu kiểm thử. Ví dụ, một kịch bản có thể gồm 70% thao tác đọc danh mục, 20% tra cứu đơn hàng và 10% transaction tạo đơn. Đây chỉ là một cấu hình minh họa; tỷ lệ thật cần lấy từ log, APM, thống kê DBMS hoặc yêu cầu nghiệp vụ.

### 2.2. Dữ liệu thử phải phản ánh quy mô và phân bố thật

Kích thước và cách phân bố dữ liệu ảnh hưởng trực tiếp đến cache, kế hoạch thực thi, số trang phải đọc và mức tranh chấp khóa.

Cần xem xét:

- Tổng số dòng và kích thước bảng.
- Số lượng giá trị phân biệt của các cột lọc và nối.
- Phân bố dữ liệu đều hay lệch về một số giá trị.
- Tỷ lệ bản ghi mới, cũ và thường xuyên được cập nhật.
- Tỷ lệ truy cập vào các bản ghi nóng.
- Kích thước chỉ mục so với bộ nhớ khả dụng.
- Tốc độ tăng dữ liệu trong thời gian thử nghiệm.

Ví dụ, tạo 100.000 tài khoản với tần suất truy cập đồng đều sẽ khác với tải thật khi phần lớn giao dịch tập trung vào một số ít tài khoản hoặc sản phẩm phổ biến. Phân bố lệch có thể làm xuất hiện khóa nóng và làm sai lệch kết quả nếu dữ liệu thử không phản ánh điều đó.

Dữ liệu thử cũng cần đủ lớn để thể hiện hành vi lưu trữ dự kiến. Nếu toàn bộ bảng và chỉ mục nằm gọn trong cache, phép đo có thể đánh giá thấp chi phí đọc trên môi trường có working set lớn hơn RAM.

### 2.3. Mô tả transaction thay vì chỉ liệt kê câu SQL

Một nghiệp vụ thường gồm nhiều câu SQL nằm trong cùng transaction. Đo từng câu riêng rẽ có thể bỏ sót thời gian giữa các câu, chi phí commit, khóa được giữ trong suốt transaction và tác động của thứ tự truy cập.

Ví dụ, xác nhận đơn hàng có thể gồm:

1. Đọc thông tin giỏ hàng.
2. Kiểm tra và cập nhật tồn kho.
3. Ghi đơn hàng và chi tiết đơn hàng.
4. Ghi trạng thái thanh toán hoặc bản ghi chờ thanh toán.
5. Commit transaction.

Khi đo, cần biết các câu lệnh nào nằm trong cùng transaction, thao tác nào có thể chờ khóa và phần nào xảy ra ngoài DBMS. Nếu ứng dụng gọi dịch vụ thanh toán trong khi transaction đang mở, thời gian giữ khóa có thể dài hơn nhiều so với thời gian thực thi SQL.

Mỗi nhóm thao tác nên có định nghĩa rõ: dữ liệu đầu vào, số câu lệnh, phạm vi transaction, điều kiện thành công, kết quả trả về và cách xử lý lỗi.

### 2.4. Giữ các điều kiện thử nghiệm có thể tái lập

Một kết quả chỉ có thể so sánh khi biết chính xác điều kiện đã tạo ra nó. Ghi lại:

- Phiên bản DBMS và cấu hình liên quan.
- CPU, RAM, loại lưu trữ, giới hạn IOPS và mạng.
- Phiên bản ứng dụng, driver và connection pool.
- Kích thước dữ liệu, trạng thái chỉ mục và thống kê optimizer.
- Kịch bản giao dịch, tỷ lệ đọc/ghi và phân bố khóa.
- Số client, số luồng tạo tải và mô hình phát sinh tải.
- Thời gian làm nóng, thời gian đo và khoảng lấy mẫu.
- Tác vụ nền đang chạy trong lúc đo.
- Các thay đổi cấu hình giữa những lần thử.

Nếu một lần thử dùng dữ liệu đã được cache còn lần khác bắt đầu với cache lạnh, hai kết quả không thể được xem là phép so sánh ngang bằng. Cần chủ động xác định muốn đo tình huống cache ấm, cache lạnh hay cả hai.

## 3. Mô hình phát sinh tải: kín và mở

Hai mô hình thường gặp là tải kín (closed workload) và tải mở (open workload). Chọn sai mô hình có thể khiến phép thử tạo ra kết luận sai về khả năng chịu tải.

### 3.1. Tải kín: client chờ xong rồi mới gửi tiếp

Trong mô hình tải kín, mỗi client gửi một yêu cầu, chờ yêu cầu hoàn tất, có thể nghỉ một khoảng thời gian, rồi mới gửi yêu cầu tiếp theo.

Ví dụ, 20 client ảo liên tục thực hiện transaction. Nếu transaction mất 50 ms, mỗi client có thể phát sinh nhiều giao dịch trong một giây. Nếu transaction chậm lên 500 ms, mỗi client sẽ tự giảm tốc độ gửi yêu cầu vì đang chờ kết quả.

Đặc điểm của tải kín:

- Số client được giữ tương đối cố định.
- Tốc độ phát sinh yêu cầu phụ thuộc vào thời gian hoàn thành.
- Khi DBMS chậm, tốc độ gửi mới tự giảm.
- Phù hợp mô phỏng nhóm người dùng hoặc worker luôn chờ phản hồi trước khi thực hiện thao tác kế tiếp.

Tải kín hữu ích để tìm hiểu hệ thống hoạt động ra sao với một số lượng client cụ thể. Tuy nhiên, nó có thể che giấu tình trạng quá tải: khi DBMS chậm, lượng yêu cầu mới giảm theo, khiến hàng đợi không tăng nhanh như tải thực tế có tốc độ đến độc lập.

### 3.2. Tải mở: yêu cầu đến theo tốc độ định trước

Trong mô hình tải mở, bộ tạo tải phát sinh yêu cầu theo lịch hoặc tốc độ đến đã định trước, không đợi yêu cầu trước hoàn thành mới quyết định thời điểm phát sinh yêu cầu tiếp theo.

Ví dụ, hệ thống nhận 300 yêu cầu/giây trong khi mỗi yêu cầu mất trung bình 100 ms. Khi DBMS chậm lên 400 ms nhưng tốc độ đến vẫn là 300 yêu cầu/giây, số yêu cầu đang chờ có thể tăng đáng kể.

Đặc điểm của tải mở:

- Tốc độ đến được điều khiển độc lập với tốc độ hoàn thành.
- Hữu ích để mô phỏng API hoặc hệ thống nhận luồng yêu cầu liên tục.
- Làm lộ rõ hiện tượng hàng đợi tăng khi năng lực phục vụ thấp hơn tốc độ đến.
- Đòi hỏi bộ tạo tải đủ năng lực để duy trì lịch gửi và ghi nhận yêu cầu bị trễ hoặc bỏ lỡ.

Nếu bộ tạo tải không đủ CPU, mạng hoặc số worker để duy trì tốc độ đã đặt, phép thử không còn tạo ra tải như thiết kế. Cần theo dõi cả tốc độ yêu cầu dự kiến và tốc độ yêu cầu thực tế được phát đi.

### 3.3. So sánh hai mô hình

| Thuộc tính | Tải kín | Tải mở |
|---|---|---|
| Cách phát sinh yêu cầu | Client chờ hoàn tất rồi mới gửi tiếp | Theo lịch hoặc tốc độ đến định trước |
| Số lượng client | Thường cố định | Có thể cần nhiều worker để duy trì tốc độ |
| Khi hệ thống chậm | Tốc độ gửi mới thường giảm | Tốc độ đến vẫn giữ theo lịch |
| Hàng đợi | Có thể bị che bớt do client tự giảm tốc | Dễ quan sát tích tụ hàng đợi |
| Dùng khi | Mô phỏng nhóm client có vòng lặp request-response | Mô phỏng luồng yêu cầu đến độc lập |
| Rủi ro diễn giải | Đánh giá thấp độ trễ khi hệ thống quá tải | Bộ tạo tải không theo kịp lịch có thể làm sai kết quả |

Không có mô hình nào phù hợp cho mọi mục tiêu. Nếu ứng dụng thực tế là một nhóm worker xử lý theo vòng lặp, tải kín có thể gần với hành vi đó. Nếu yêu cầu đến từ người dùng hoặc hệ thống bên ngoài theo tốc độ độc lập, tải mở thường phản ánh áp lực đến tốt hơn.

### 3.4. Hiện tượng coordinated omission

Một vấn đề thường gặp khi dùng tải kín là coordinated omission. Khi một yêu cầu mất nhiều thời gian, client đang chờ nên không gửi các yêu cầu tiếp theo theo lịch giả định. Bộ đo chỉ ghi nhận những yêu cầu thực sự được gửi, không phản ánh đầy đủ các thời điểm mà yêu cầu mới lẽ ra đã đến trong khoảng hệ thống bị chậm.

Kết quả là độ trễ đo được có thể lạc quan hơn trải nghiệm của một nguồn yêu cầu đến liên tục. Ví dụ, nếu một client phát sinh yêu cầu mỗi 20 ms theo lịch nhưng một yêu cầu mất 500 ms, một phép đo tải kín đơn giản có thể chỉ ghi nhận một yêu cầu trong khoảng chờ đó. Nó không thể hiện hàng loạt yêu cầu đến trong 500 ms sẽ phải xếp hàng như thế nào.

Để giảm sai lệch:

- Chọn mô hình tải gần với cơ chế đến thực tế.
- Nếu dùng tải mở, đo cả thời điểm dự kiến và thời điểm gửi thật.
- Ghi nhận yêu cầu bị trễ, bỏ qua hoặc không phát sinh đúng lịch.
- Dùng công cụ có hỗ trợ hiệu chỉnh coordinated omission khi phù hợp.
- Báo cáo rõ phương pháp lấy mẫu độ trễ và giới hạn của phép đo.

Không nên chỉ so sánh hai con số p99 nếu cách phát sinh tải và cách ghi nhận độ trễ khác nhau.

## 4. Tăng mức đồng thời theo từng bước

### 4.1. Tìm đường cong tải và điểm bão hòa

Một bài kiểm tra nên quan sát hệ thống ở nhiều mức tải thay vì chọn một số lượng client tùy ý. Có thể bắt đầu từ 1 client, sau đó tăng lên 2, 4, 8, 16, 32 và tiếp tục tùy năng lực môi trường.

Ở mỗi mức, giữ đủ thời gian để số liệu ổn định và ghi nhận:

- Số yêu cầu hoặc transaction thực sự hoàn thành mỗi giây.
- p50, p95 và p99.
- Số lỗi, timeout và transaction thất bại.
- CPU, bộ nhớ, I/O và mạng.
- Số phiên hoạt động, số phiên chờ và thời gian chờ pool.
- Lock wait, deadlock và transaction kéo dài.
- Hàng đợi ở bộ tạo tải và ứng dụng.

Một hệ thống thường có vùng tải thấp với độ trễ ổn định, vùng tăng tải mà thông lượng còn tăng tốt, sau đó là vùng bão hòa. Ở vùng bão hòa, thêm client có thể không tăng thông lượng đáng kể nhưng làm độ trễ và số lỗi tăng nhanh.

<escape>Biểu đồ khái niệm:</escape>

~~~text
Thông lượng
   ^
   |                         __________
   |                    ____/
   |                ___/
   |            ___/
   |        ___/
   |_______/
   +------------------------------------> Mức tải đồng thời
          vùng tăng tải       vùng bão hòa

Độ trễ
   ^
   |                                  /
   |                               __/
   |                            __/
   |                         __/
   |________________________/
   +------------------------------------> Mức tải đồng thời
          vùng ổn định       độ trễ tăng nhanh
~~~

Đây là hình minh họa khái niệm, không phải số liệu của một DBMS cụ thể. Đường cong thực tế có thể khác tùy tải đọc/ghi, cache, phần cứng, mức khóa và cách ứng dụng tạo tải.

### 4.2. Không nhầm số client với số truy vấn đang chạy

Số client ảo không nhất thiết bằng số truy vấn đang thực thi trong DBMS. Một client có thể:

- Đang chờ kết quả.
- Đang nghỉ theo think time.
- Đang chờ lấy kết nối từ pool.
- Đang xử lý dữ liệu ở ứng dụng.
- Đang chờ mạng.
- Đang thực thi SQL.
- Đang ở giữa các câu lệnh trong transaction.

Do đó, khi nói “thử 100 người dùng đồng thời”, cần xác định 100 là số client ảo, số yêu cầu đang chạy, số kết nối DBMS hay số transaction thực sự hoạt động. Những đại lượng này khác nhau.

Connection pool tạo thêm một lớp điều tiết. Ví dụ, 100 client ứng dụng có thể chia sẻ 20 kết nối DBMS. Khi đó, 80 client có thể phải chờ pool ngay cả khi DBMS còn năng lực. Nếu pool có 200 kết nối, DBMS có thể nhận nhiều truy vấn hơn và phát sinh tranh chấp tài nguyên. Hãy đo cả thời gian chờ pool và số phiên thực tế ở DBMS.

### 4.3. Tăng tải theo bước và giữ thời gian ổn định

Một trình tự thử nghiệm có thể gồm:

1. Chạy mức tải thấp để xác nhận kịch bản và tính đúng của kết quả.
2. Tăng mức đồng thời theo các bậc đã chọn.
3. Ở mỗi bậc, dành thời gian warm-up để cache, connection pool và các thành phần liên quan ổn định.
4. Bắt đầu cửa sổ đo sau warm-up.
5. Giữ mức tải đủ lâu để quan sát xu hướng và các hoạt động định kỳ.
6. Dừng tải có kiểm soát, chờ hệ thống trở lại trạng thái ổn định.
7. Lặp lại các mức quan trọng để kiểm tra độ biến động.

Không nên trộn số liệu warm-up với cửa sổ đo chính nếu mục tiêu là so sánh trạng thái ổn định. Tuy nhiên, warm-up cũng là một phần của trải nghiệm thực tế nếu hệ thống thường xuyên khởi động mới hoặc cache bị làm lạnh; khi đó hãy đo riêng kịch bản khởi động lạnh.

### 4.4. Tách thử nghiệm tải ổn định và thử nghiệm đột biến

Hai tình huống trả lời hai câu hỏi khác nhau:

- **Tải ổn định:** hệ thống phục vụ tốt đến đâu khi nhận một lưu lượng đều trong thời gian đủ dài?
- **Tải đột biến (burst):** hệ thống phản ứng thế nào khi lưu lượng tăng nhanh trong một khoảng ngắn rồi giảm xuống?

Một hệ thống có thể phục vụ tốt tải đều nhưng gặp vấn đề khi nhiều yêu cầu đến cùng lúc vì pool kết nối, hàng đợi hoặc cơ chế autoscaling cần thời gian phản ứng. Ngược lại, hệ thống có thể hấp thụ burst ngắn nhờ buffer nhưng không thể duy trì tải đó lâu dài.

Ghi rõ thời gian tăng tải, thời gian giữ tải và thời gian giảm tải. Nếu chỉ đo một đoạn ngắn, có thể bỏ qua checkpoint, tác vụ nền hoặc sự tăng dần của hàng đợi.

## 5. Đo độ trễ và thông lượng đúng cách

### 5.1. Dùng phân vị thay cho chỉ số trung bình đơn độc

Độ trễ trung bình hữu ích để xem xu hướng tổng quát, nhưng có thể che giấu một nhóm nhỏ yêu cầu rất chậm. Nên ghi ít nhất:

- **p50:** trung vị; một nửa yêu cầu nhanh hơn hoặc bằng giá trị này.
- **p90 hoặc p95:** phản ánh nhóm yêu cầu chậm hơn phần lớn người dùng.
- **p99:** thể hiện phần đuôi chậm, thường hữu ích để phát hiện hàng đợi hoặc tranh chấp xuất hiện không thường xuyên.
- **Giá trị tối đa:** có thể chỉ ra sự cố hoặc ngoại lệ, nhưng rất nhạy với một mẫu đơn lẻ.

Ví dụ:

| Mức tải | Throughput | p50 | p95 | p99 |
|---:|---:|---:|---:|---:|
| 8 client | 120 tx/s | 18 ms | 35 ms | 70 ms |
| 16 client | 230 tx/s | 22 ms | 48 ms | 95 ms |
| 32 client | 390 tx/s | 35 ms | 110 ms | 260 ms |
| 64 client | 405 tx/s | 95 ms | 620 ms | 1.800 ms |

Các số liệu trên chỉ minh họa một hệ thống bắt đầu bão hòa: khi tăng từ 32 lên 64 client, thông lượng gần như không tăng nhưng p95 và p99 tăng mạnh. Không dùng các giá trị này làm ngưỡng chuẩn cho hệ thống khác.

### 5.2. Đo ở cả phía client và DBMS

Thời gian người dùng chờ thường khác với thời gian DBMS thực thi câu SQL. Một yêu cầu có thể trải qua:

1. Chờ lấy kết nối từ pool.
2. Chờ gửi yêu cầu qua mạng.
3. Chờ DBMS lập lịch.
4. Chờ khóa hoặc tài nguyên.
5. Thực thi câu SQL.
6. Chờ commit và ghi log bền vững.
7. Truyền kết quả về ứng dụng.
8. Giải mã và xử lý kết quả ở ứng dụng.

Nếu DBMS báo câu SQL chạy 30 ms nhưng ứng dụng ghi nhận transaction mất 250 ms, cần xác định phần thời gian còn lại nằm ở đâu. Đừng cộng hoặc so sánh các số đo có phạm vi khác nhau mà không làm rõ điểm bắt đầu và kết thúc.

Nên ghi dấu thời gian hoặc trace theo request/transaction, đồng thời thu thập thống kê tổng hợp ở DBMS và hệ điều hành. Khi dữ liệu đủ lớn, có thể nhóm theo loại thao tác hoặc fingerprint truy vấn để tránh chỉ nhìn một giá trị tổng.

### 5.3. Ghi cả lỗi và yêu cầu không hoàn thành

Một bài kiểm tra có thể cho thấy latency thấp vì yêu cầu chậm đã timeout hoặc bị loại khỏi phép đo. Do đó, cần báo cáo:

- Tổng số yêu cầu dự kiến.
- Số yêu cầu thực sự được phát đi.
- Số yêu cầu hoàn thành thành công.
- Số lỗi nghiệp vụ, lỗi DBMS và lỗi kết nối.
- Số timeout, retry và transaction bị hủy.
- Số yêu cầu bị bỏ lỡ lịch phát sinh hoặc bị loại khỏi thống kê.

Thông lượng phải được định nghĩa rõ là số transaction thành công hay số lần thử, và có tính cả retry hay không. Với nghiệp vụ ghi dữ liệu, transaction lỗi hoặc bị retry có thể tạo tải đáng kể dù không tạo ra kết quả nghiệp vụ.

### 5.4. Cửa sổ lấy mẫu và cách tổng hợp

Số liệu theo từng giây có thể biến động mạnh. Cần chọn khoảng lấy mẫu phù hợp với mục tiêu và giữ cùng cách lấy mẫu khi so sánh. Ví dụ, lưu throughput và độ trễ theo cửa sổ 10 giây, đồng thời lưu phân vị của toàn bộ lần chạy.

Không lấy trung bình các p95 của nhiều cửa sổ rồi gọi đó là p95 tổng thể. Phân vị không có tính chất cộng gộp đơn giản. Nếu cần phân vị tổng thể, hãy tính trên tập mẫu đầy đủ hoặc dùng histogram có cách gộp tương thích. Khi chỉ có số liệu theo cửa sổ, trình bày rõ đó là phân vị của từng cửa sổ và cách tổng hợp các cửa sổ.

Cũng nên lưu số lượng mẫu trong mỗi cửa sổ. Một p99 được tính từ vài chục yêu cầu không ổn định như p99 từ hàng trăm nghìn yêu cầu.

## 6. Nhận biết giới hạn tài nguyên dưới tải

Khi mức đồng thời tăng, cần liên hệ đường cong throughput/latency với số liệu tài nguyên và wait event. Không có một chỉ số duy nhất đủ để kết luận.

### 6.1. Dấu hiệu CPU

- CPU tiến gần giới hạn trong cùng thời gian độ trễ tăng.
- Hàng đợi runnable hoặc CPU throttling tăng.
- Một số truy vấn có tổng thời gian CPU lớn.
- CPU tăng nhưng thời gian chờ I/O và khóa không giải thích được độ trễ.

Kiểm tra theo tiến trình và từng lõi nếu có thể. CPU toàn máy ở mức trung bình không loại trừ một lõi hoặc quota đã bão hòa.

### 6.2. Dấu hiệu bộ nhớ

- RAM khả dụng giảm mạnh, swap hoặc page fault tăng.
- Cache hit/miss thay đổi cùng với thời gian đọc.
- Sort/hash tạo nhiều dữ liệu tạm.
- Nhu cầu bộ nhớ tăng nhanh theo số phiên hoặc số truy vấn nặng.

Một lần chạy đơn lẻ có thể không bộc lộ vấn đề bộ nhớ vì chỉ có một thao tác sort. Khi nhiều thao tác tương tự chạy cùng lúc, phần bộ nhớ cấp phát cộng dồn có thể gây áp lực.

### 6.3. Dấu hiệu lưu trữ

- Độ trễ đọc/ghi và hàng đợi I/O tăng.
- Throughput hoặc IOPS chạm giới hạn của volume hoặc thiết bị.
- DBMS chờ đọc trang, ghi log hoặc đồng bộ.
- Commit chậm dù câu lệnh cập nhật có ít thao tác tính toán.

Cần phân biệt tải đọc ngẫu nhiên, quét tuần tự, ghi log và ghi dữ liệu. Cùng một mức thông lượng có thể tạo ra độ trễ rất khác tùy kiểu I/O.

### 6.4. Dấu hiệu khóa và tranh chấp giao dịch

- Số phiên chờ khóa tăng theo mức đồng thời.
- Deadlock hoặc serialization failure tăng.
- Transaction giữ khóa lâu.
- Một số khóa hoặc dòng dữ liệu trở thành điểm nóng.
- Throughput dừng tăng dù CPU và I/O chưa bão hòa.

Nếu các phiên chờ khóa chiếm phần lớn thời gian, tăng CPU hoặc lưu trữ thường không giải quyết được giới hạn. Hãy xem giao dịch nào giữ khóa, giao dịch nào chờ và thứ tự truy cập đối tượng.

### 6.5. Dấu hiệu mạng và bộ tạo tải

- DBMS hoàn thành câu lệnh nhanh nhưng thời gian client nhận kết quả cao.
- RTT, retransmission hoặc băng thông tăng.
- Máy tạo tải đạt giới hạn CPU, mạng hoặc số socket.
- Tốc độ yêu cầu thực tế thấp hơn tốc độ đặt trước.

Nếu máy tạo tải là nút thắt, phép thử sẽ đánh giá thấp khả năng của DBMS. Hãy theo dõi tài nguyên ở cả máy tạo tải, ứng dụng và máy chủ cơ sở dữ liệu.

## 7. Thực hiện phép thử với PostgreSQL và pgbench

### 7.1. Vai trò của pgbench

pgbench là công cụ benchmark đi kèm PostgreSQL. Nó có thể khởi tạo dữ liệu mẫu và phát sinh transaction với số client, số luồng và thời lượng được cấu hình. Công cụ phù hợp để khảo sát xu hướng dưới tải và kiểm tra thay đổi trong cùng môi trường.

pgbench không tự động mô phỏng mọi nghiệp vụ ứng dụng. Bộ kịch bản mặc định có thể không phản ánh tỷ lệ đọc/ghi, phân bố dữ liệu nóng, transaction dài hoặc hành vi pool của hệ thống thật. Cần hiểu rõ workload đang chạy trước khi diễn giải số liệu.

### 7.2. Khởi tạo dữ liệu thử

Ví dụ tạo bộ dữ liệu mẫu với scale factor 10:

~~~bash
pgbench -i -s 10 -h localhost -U bench_user performance_db
~~~

Thao tác khởi tạo có thể tạo hoặc thay đổi các bảng benchmark trong database đích. Chỉ chạy trên database thử nghiệm đã được chuẩn bị cho mục đích này. Scale factor ảnh hưởng đến kích thước dữ liệu và cần được chọn sao cho phù hợp với mục tiêu đo.

### 7.3. Tăng dần số client

Chạy thử với 8 client, 2 luồng trong 180 giây:

~~~bash
pgbench -c 8 -j 2 -T 180 -P 10 -r -h localhost -U bench_user performance_db
~~~

Sau đó lặp lại với các mức client khác, chẳng hạn 16, 32 và 64. Giữ nguyên database, script, thời lượng, cấu hình và trạng thái dữ liệu khi so sánh. Tham số:

- **-c**: số client mô phỏng.
- **-j**: số luồng worker của pgbench.
- **-T**: thời gian chạy theo giây.
- **-P**: chu kỳ in tiến độ.
- **-r**: báo cáo độ trễ theo từng lệnh trong script.

Các tùy chọn và báo cáo có thể thay đổi theo phiên bản PostgreSQL. Kiểm tra trợ giúp của phiên bản đang cài trước khi dùng trong môi trường cụ thể.

### 7.4. Phát sinh tải theo tốc độ mục tiêu

pgbench hỗ trợ giới hạn tốc độ phát sinh transaction bằng tùy chọn **-R**. Ví dụ:

~~~bash
pgbench -c 32 -j 4 -T 300 -R 200 -P 10 -r -h localhost -U bench_user performance_db
~~~

Ví dụ này đặt mục tiêu phát sinh 200 transaction/giây trong 300 giây với 32 client và 4 worker thread. Hãy kiểm tra báo cáo để biết tốc độ thực tế, độ trễ, transaction bị trễ hoặc không được thực hiện đúng lịch. Đặt tốc độ mục tiêu không bảo đảm bộ tạo tải hoặc DBMS đạt được tốc độ đó.

So sánh thử nghiệm tải kín và thử nghiệm có giới hạn tốc độ sẽ giúp nhận ra sự khác nhau giữa “32 client liên tục làm việc” và “yêu cầu đến với tốc độ 200 transaction/giây”.

### 7.5. Dùng script riêng cho workload

Có thể tạo file script cho một loại transaction cụ thể. Ví dụ sau mô phỏng một thao tác đọc số dư rồi cập nhật một tài khoản:

~~~sql
\set account_id random(1, 100000)

BEGIN;

SELECT balance
FROM accounts
WHERE account_id = :account_id;

UPDATE accounts
SET balance = balance + 1
WHERE account_id = :account_id;

COMMIT;
~~~

Chạy script bằng tùy chọn **-f**:

~~~bash
pgbench -f account-workload.sql -c 24 -j 4 -T 240 -P 10 -r -h localhost -U bench_user performance_db
~~~

Script chỉ là ví dụ cấu trúc. Bảng, cột, ràng buộc và dữ liệu phải tồn tại trong database thử nghiệm. Nếu muốn đo tranh chấp khóa, hãy thiết kế phân bố account_id để có cả trường hợp truy cập đều và trường hợp nhiều client tập trung vào một nhóm tài khoản nóng. Ghi rõ phân bố này trong báo cáo.

### 7.6. Kết hợp với số liệu của DBMS

Trong khi pgbench phát sinh tải, hãy quan sát số phiên, trạng thái và wait event. Ví dụ:

~~~sql
SELECT
    state,
    wait_event_type,
    wait_event,
    count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY state, wait_event_type, wait_event
ORDER BY sessions DESC;
~~~

Nếu có extension pg_stat_statements, có thể xem các truy vấn đóng góp nhiều tổng thời gian hoặc tạo nhiều dữ liệu tạm. Kết hợp thống kê này với báo cáo pgbench để phân biệt transaction chậm do một câu SQL tốn kém với transaction chậm do chờ khóa hoặc tài nguyên.

pgbench cung cấp số liệu tải ở phía client; pg_stat_activity và các view thống kê cung cấp góc nhìn bên trong PostgreSQL. Số liệu hệ điều hành và lưu trữ bổ sung bằng chứng về CPU, RAM và I/O. Cần lấy các số liệu trong cùng cửa sổ thời gian để đối chiếu.

## 8. Ví dụ thiết kế và diễn giải một bài đo

### 8.1. Bối cảnh

Một dịch vụ đặt hàng có ba nhóm thao tác:

| Nhóm | Tỷ lệ giả định | Đặc điểm |
|---|---:|---|
| Xem danh mục | 65% | Đọc nhiều, ít tranh chấp |
| Tra cứu đơn hàng | 25% | Đọc theo khách hàng và thời gian |
| Xác nhận đơn | 10% | Ghi nhiều bảng, cập nhật tồn kho |

Mục tiêu là xác định hệ thống có thể duy trì bao nhiêu transaction/giây trước khi độ trễ tăng vượt mục tiêu dịch vụ. Đội kỹ thuật tạo dữ liệu đủ lớn, thiết lập các chỉ mục như môi trường thử và xây dựng script theo ba nhóm thao tác.

### 8.2. Kế hoạch thử

- Chạy kiểm tra chức năng với 1 client để xác nhận script và dữ liệu.
- Làm nóng hệ thống trong 2 phút.
- Thử mức 8, 16, 32, 48 và 64 client.
- Giữ mỗi mức trong 5 phút sau warm-up.
- Ghi throughput, p50, p95, p99, lỗi và timeout.
- Thu thập CPU, RAM, I/O, wait event, số kết nối và thời gian chờ pool.
- Lặp lại các mức 32, 48 và 64 để xác nhận xu hướng.
- Thực hiện một kịch bản burst riêng để đánh giá khả năng hấp thụ tăng tải nhanh.

Thời gian và mức tải ở đây chỉ là ví dụ. Môi trường thực tế cần chọn dựa trên lưu lượng quan sát, giới hạn hạ tầng và mục tiêu dịch vụ.

### 8.3. Kết quả giả định

| Client | Throughput thành công | p50 | p95 | p99 | Chờ khóa |
|---:|---:|---:|---:|---:|---|
| 8 | 150 tx/s | 20 ms | 42 ms | 85 ms | Thấp |
| 16 | 285 tx/s | 24 ms | 58 ms | 120 ms | Thấp |
| 32 | 470 tx/s | 38 ms | 145 ms | 310 ms | Tăng |
| 48 | 485 tx/s | 82 ms | 510 ms | 1.400 ms | Cao |
| 64 | 490 tx/s | 140 ms | 980 ms | 2.600 ms | Rất cao |

Các số liệu giả định cho thấy throughput gần như không tăng từ 32 lên 64 client trong khi p95, p99 và chờ khóa tăng mạnh. Nếu CPU vẫn còn dư và I/O không bão hòa, nhóm cần xem xét các transaction xác nhận đơn có đang tranh chấp trên những dòng tồn kho nóng hay không.

Một hướng kiểm chứng là chạy cùng workload nhưng thay đổi phân bố khóa: một lần truy cập đều trên nhiều sản phẩm, một lần tập trung vào nhóm sản phẩm phổ biến. Nếu mức chờ khóa tăng mạnh trong trường hợp tập trung, dữ liệu hỗ trợ giả thuyết điểm nóng. Kết quả này có thể dẫn tới việc xem lại thiết kế cập nhật tồn kho hoặc transaction.

### 8.4. Không kết luận từ một lần chạy

Giả sử lần chạy đầu ở 32 client cho p95 là 145 ms nhưng lần thứ hai là 210 ms. Trước khi kết luận cấu hình biến động, hãy kiểm tra:

- Cache có cùng trạng thái hay không.
- Có checkpoint, autovacuum, backup hoặc tác vụ nền trong một lần chạy không.
- Máy tạo tải có đang chạy tiến trình khác không.
- Kết nối có được tạo trước hay phải thiết lập trong cửa sổ đo.
- Dữ liệu và phân bố khóa có giống nhau không.
- Có lỗi hoặc retry làm thay đổi lượng công việc không.

Nếu hai lần thử không có điều kiện tương đương, hãy ghi nhận khác biệt và chạy lại. Không chọn kết quả tốt nhất trong nhiều lần đo để đại diện cho hiệu năng.

## 9. So sánh trước và sau tối ưu

### 9.1. Thay đổi một yếu tố có thể kiểm chứng

Khi đánh giá một chỉ mục mới, thay đổi SQL hoặc cấu hình pool, hãy cố gắng cô lập tác động:

1. Ghi đường cơ sở với workload và dữ liệu cố định.
2. Lưu kế hoạch thực thi và thống kê liên quan.
3. Thay đổi một yếu tố chính.
4. Chạy lại cùng kịch bản và cùng mức tải.
5. So sánh throughput, độ trễ phân vị, lỗi và tài nguyên.
6. Kiểm tra các thao tác khác bị ảnh hưởng.
7. Lặp lại phép đo ở mức tải quan trọng.

Nếu thay đổi đồng thời chỉ mục, bộ nhớ, số kết nối và cấu trúc transaction, sẽ khó biết yếu tố nào tạo ra kết quả. Khi không thể tách riêng, cần ghi rõ các thay đổi cùng lúc và tránh quy kết lợi ích cho một thay đổi cụ thể.

### 9.2. Đánh giá cả lợi ích và chi phí phụ

Một chỉ mục có thể giảm thời gian đọc nhưng tăng chi phí ghi và dung lượng. Tăng kích thước pool có thể giảm thời gian chờ kết nối nhưng làm tăng số phiên cạnh tranh. Batch lớn có thể giảm số lượt trao đổi nhưng kéo dài transaction và giữ khóa lâu hơn.

Do đó, so sánh phải bao gồm các nhóm chỉ số:

| Nhóm | Chỉ số nên ghi |
|---|---|
| Hiệu năng người dùng | p50, p95, p99, thời gian transaction/API |
| Năng lực xử lý | Transaction thành công/giây, số yêu cầu hoàn thành |
| Độ tin cậy | Lỗi, timeout, retry, deadlock, transaction bị hủy |
| CPU | Mức dùng theo tiến trình/lõi, throttling |
| Bộ nhớ | RAM, swap, cache, dữ liệu tạm |
| Lưu trữ | IOPS, throughput, độ trễ đọc/ghi, hàng đợi |
| Đồng thời | Số phiên hoạt động, lock wait, thời gian chờ pool |
| Mạng | RTT, byte gửi/nhận, retransmission |

Chỉ giữ thay đổi khi lợi ích phù hợp mục tiêu và các chỉ số bảo vệ vẫn nằm trong giới hạn chấp nhận được.

### 9.3. Kiểm tra tính đúng đắn dữ liệu

Một bài đo ghi dữ liệu phải kiểm tra kết quả nghiệp vụ. Nếu transaction bị lỗi, retry hoặc rollback, thông lượng yêu cầu có thể cao nhưng số nghiệp vụ thành công thấp. Nếu phép thử tạo dữ liệu không hợp lệ, kết quả hiệu năng không có giá trị.

Ví dụ, với transaction trừ tồn kho, sau khi chạy tải cần kiểm tra:

- Không có tồn kho âm nếu quy tắc nghiệp vụ cấm.
- Số lượng đơn và chi tiết đơn nhất quán.
- Các transaction thất bại được ghi nhận đúng.
- Retry không tạo đơn hoặc giao dịch trùng.
- Dữ liệu được commit và có thể đọc lại theo yêu cầu.

Độ trễ thấp không thể bù cho dữ liệu sai hoặc mất tính nhất quán.

## 10. Những sai lầm thường gặp khi đo tải đồng thời

**Dùng một lần chạy đơn lẻ làm đại diện cho tải thật.**  
Một lần chạy chỉ phản ánh một trạng thái cache, một mức đồng thời và một thời điểm. Hãy thử nhiều mức tải và lặp lại các mức quan trọng.

**Tăng số client mà không theo dõi tốc độ yêu cầu thực tế.**  
Tải kín có thể tự giảm tốc khi hệ thống chậm. Cần hiểu mô hình phát sinh tải và ghi tốc độ đến thực tế.

**Chỉ xem throughput.**  
Throughput có thể đứng yên trong khi p95/p99 và lỗi tăng mạnh. Luôn xem năng lực xử lý cùng chất lượng phản hồi.

**Chỉ xem latency trung bình.**  
Trung bình có thể che giấu nhóm yêu cầu chậm. Hãy dùng phân vị và ghi số lượng mẫu.

**Dùng dữ liệu thử nhỏ hoặc phân bố quá đều.**  
Dữ liệu nhỏ có thể nằm hết trong cache; phân bố đều có thể che giấu khóa nóng. Cần mô phỏng quy mô và độ lệch truy cập phù hợp.

**Để máy tạo tải trở thành nút thắt.**  
CPU hoặc mạng của load generator có thể không đủ để phát sinh tải dự kiến. Theo dõi máy tạo tải và đối chiếu tốc độ đặt với tốc độ thật.

**Bỏ qua connection pool.**  
Số client ứng dụng không bằng số phiên DBMS. Đo cả thời gian chờ pool và số kết nối hoạt động.

**So sánh hai lần chạy với điều kiện khác nhau.**  
Khác cache, dữ liệu, tác vụ nền, cấu hình hoặc workload đều có thể làm kết quả lệch. Ghi lại điều kiện và chạy lại nếu không tương đương.

**Gộp nhiều loại transaction thành một số tổng duy nhất.**  
Một loại truy vấn chậm có thể bị che khuất bởi nhiều truy vấn nhanh. Hãy phân loại kết quả theo nhóm thao tác hoặc fingerprint truy vấn.

**Không kiểm tra lỗi và tính đúng đắn.**  
Latency thấp do timeout hoặc bỏ yêu cầu không phải là cải thiện. Đếm transaction thành công và kiểm tra dữ liệu sau thử nghiệm.

## 11. Mẫu báo cáo một phép thử

Một báo cáo tốt giúp người khác lặp lại phép đo và hiểu giới hạn của kết luận. Có thể dùng cấu trúc sau:

### Mục tiêu

Nêu câu hỏi cần trả lời, ví dụ: xác định mức đồng thời mà workload đặt hàng duy trì được p95 dưới 250 ms.

### Môi trường

Ghi phiên bản DBMS, cấu hình máy, loại lưu trữ, cấu hình mạng, phiên bản ứng dụng, driver và connection pool.

### Dữ liệu và workload

Mô tả kích thước dữ liệu, phân bố khóa, tỷ lệ đọc/ghi, các loại transaction, thời gian transaction và logic retry.

### Mô hình tải

Ghi tải kín hay tải mở, số client, số worker, tốc độ đến mục tiêu, think time, thời gian warm-up và thời gian đo.

### Kết quả

Báo cáo throughput thành công, p50/p95/p99, lỗi, timeout, retry, lock wait, CPU, RAM, I/O, mạng và thời gian chờ pool. Ghi số mẫu và cách tính phân vị.

### Nhận định

Nêu xu hướng quan sát được, bằng chứng ủng hộ giả thuyết và các yếu tố chưa xác định. Phân biệt rõ điều gì được đo trực tiếp và điều gì mới là giả thuyết.

### Thay đổi và kiểm chứng

Ghi thay đổi đã thực hiện, kết quả trước/sau dưới cùng điều kiện, tác dụng phụ và kết luận giữ hoặc hoàn tác.

Ví dụ kết luận có cơ sở: “Trong workload đọc/ghi đã mô tả, throughput tăng đến khoảng 470 transaction/giây ở mức 32 client. Từ 48 client trở lên, throughput gần như không tăng trong khi p95 và lock wait tăng mạnh. CPU và độ trễ lưu trữ chưa đạt giới hạn quan sát; dữ liệu hiện tại gợi ý tranh chấp trên nhóm dòng tồn kho nóng. Cần thử phân bố khóa khác và đo lại trước khi thay đổi thiết kế.”

Cách kết luận này nêu điều kiện đo, xu hướng và giả thuyết. Nó không biến một lần benchmark thành khẳng định chung cho mọi loại tải.

## 12. Kết luận

Đo tải đồng thời giúp nhìn thấy những chi phí chỉ xuất hiện khi nhiều giao dịch cùng chia sẻ tài nguyên. Một truy vấn nhanh ở một phiên có thể trở nên chậm do hàng đợi CPU, thiếu bộ nhớ, I/O, mạng, connection pool hoặc tranh chấp khóa. Muốn tìm giới hạn thật, cần mô phỏng đúng loại transaction, dữ liệu và cách yêu cầu đến hệ thống.

Một quy trình đáng tin cậy bắt đầu từ workload đại diện, chọn mô hình tải kín hoặc mở theo hành vi thực tế, tăng mức đồng thời theo từng bước, tách warm-up khỏi cửa sổ đo, ghi throughput cùng p50/p95/p99 và lỗi, rồi đối chiếu với thống kê DBMS và tài nguyên hạ tầng. Khi so sánh trước và sau tối ưu, phải giữ điều kiện tương đương, kiểm tra tác dụng phụ và xác nhận tính đúng đắn dữ liệu.

## Câu hỏi tự kiểm tra

1. Vì sao một truy vấn chạy nhanh khi có một client chưa chứng minh hệ thống chịu tải tốt?
2. Tải kín và tải mở khác nhau ở cách phát sinh yêu cầu nào?
3. Coordinated omission có thể khiến kết quả latency lạc quan như thế nào?
4. Vì sao số client ảo không nhất thiết bằng số truy vấn đang chạy trong DBMS?
5. Một hệ thống tăng từ 32 lên 64 client nhưng throughput gần như không đổi, trong khi p99 tăng mạnh. Bạn sẽ kiểm tra những số liệu nào?
6. Vì sao cần dùng dữ liệu có phân bố khóa nóng thay vì chỉ tạo dữ liệu đều?
7. Khi so sánh trước và sau khi thêm chỉ mục, những chỉ số ghi nào cần theo dõi cùng với tốc độ đọc?
8. Làm thế nào để xác định máy tạo tải có trở thành nút thắt?
9. Vì sao không nên lấy trung bình của các p95 theo từng cửa sổ để gọi đó là p95 toàn bộ lần chạy?
10. Hãy đề xuất một workload và kế hoạch tăng mức đồng thời để kiểm tra một dịch vụ cập nhật tồn kho.

Một phép đo có giá trị khi người khác có thể tái tạo điều kiện thử, hiểu được số liệu đã ghi và đánh giá được giới hạn của kết luận. Chỉ khi đó, kết quả mới đủ tin cậy để định hướng thay đổi SQL, chỉ mục, transaction, bộ nhớ hoặc hạ tầng.

