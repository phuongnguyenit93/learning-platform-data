# Số yêu cầu đồng thời, độ dài hàng đợi và mức bão hòa tài nguyên

Trong hệ thống cơ sở dữ liệu, số yêu cầu đang được xử lý cùng lúc, số yêu cầu phải chờ và mức sử dụng tài nguyên cho biết hệ thống còn khả năng tiếp nhận tải hay đã tiến gần giới hạn. Ba nhóm chỉ số này cần được đọc cùng nhau: số yêu cầu đồng thời mô tả lượng công việc đang hiện diện, hàng đợi cho biết phần công việc chưa được phục vụ, còn mức bão hòa cho biết tài nguyên nào đang thiếu năng lực phục vụ.

Bài học này thuộc chương **Chỉ số và mục tiêu** của module **DATABASE_PERFORMANCE**. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung module bao gồm thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, các chỉ số dưới đây được dùng để xác định nơi công việc đang chờ, tài nguyên nào đang chịu áp lực và thay đổi tối ưu có cải thiện năng lực phục vụ thực tế hay không.

## 1. Vì sao phải theo dõi cả ba nhóm chỉ số?

Giả sử một ứng dụng gửi nhiều truy vấn đến cơ sở dữ liệu. Một số truy vấn đang chạy trên CPU, một số chờ đọc dữ liệu từ đĩa, một số chờ khóa do giao dịch khác nắm giữ, và một số chưa lấy được kết nối từ connection pool. Nếu chỉ nhìn CPU, ta có thể kết luận máy chủ còn rảnh trong khi người dùng vẫn phải chờ lâu vì khóa hoặc vì pool đã hết kết nối.

Ba câu hỏi cần trả lời là:

1. **Có bao nhiêu công việc đang diễn ra?** Đây là góc nhìn về yêu cầu đồng thời và phiên làm việc đang hoạt động.
2. **Có bao nhiêu công việc đang chờ, và chờ bao lâu?** Đây là góc nhìn về hàng đợi tại ứng dụng, connection pool, cơ sở dữ liệu hoặc thiết bị lưu trữ.
3. **Tài nguyên nào đang gần hết khả năng phục vụ?** Đây là góc nhìn về CPU, bộ nhớ, I/O, số kết nối, khóa và các giới hạn cấu hình.

Một hệ thống có thể có mức sử dụng CPU thấp nhưng vẫn bị bão hòa ở connection pool hoặc bị nghẽn bởi khóa. Ngược lại, CPU có thể bận cao trong một khoảng ngắn mà hàng đợi vẫn được giải phóng nhanh. Vì thế, không nên dùng riêng một tỷ lệ sử dụng tài nguyên để kết luận hiệu năng.

## 2. Hiểu đúng từng khái niệm

### 2.1. Số yêu cầu đồng thời

Số yêu cầu đồng thời là số đơn vị công việc đang tồn tại trong hệ thống tại cùng một thời điểm. Tùy điểm đo, đơn vị đó có thể là yêu cầu HTTP, tác vụ trong worker, truy vấn đang thực thi, giao dịch đang mở hoặc phiên cơ sở dữ liệu đang hoạt động.

Các khái niệm này có liên quan nhưng không đồng nhất:

- **Kết nối đang mở** cho biết số kết nối được thiết lập. Một kết nối có thể đang rảnh, đang chạy truy vấn hoặc đang giữ giao dịch.
- **Phiên đang hoạt động** cho biết phiên hiện đang thực hiện công việc hoặc đang ở một trạng thái chờ được hệ quản trị ghi nhận.
- **Truy vấn đang thực thi** là công việc SQL đang được xử lý. Một phiên có thể thực hiện nhiều truy vấn theo thời gian, nhưng thông thường không chạy nhiều câu lệnh đồng thời trên cùng một luồng giao dịch.
- **Giao dịch đang mở** có thể tồn tại lâu hơn thời gian chạy một câu SQL. Giao dịch dài có thể giữ khóa hoặc phiên bản dữ liệu, làm tăng tranh chấp và chi phí dọn dẹp.

Do đó, không được lấy tổng số kết nối đang mở làm đại diện trực tiếp cho số truy vấn đồng thời. Khi phân tích, cần ghi rõ đang đếm yêu cầu ở tầng nào và trạng thái nào được xem là hoạt động.

### 2.2. Độ dài hàng đợi

Hàng đợi là tập công việc đã đến nhưng chưa được cấp tài nguyên hoặc chưa được phục vụ. Hàng đợi có thể xuất hiện ở nhiều tầng:

- Ứng dụng đang chờ worker xử lý.
- Yêu cầu đang chờ lấy kết nối từ connection pool.
- Truy vấn hoặc giao dịch đang chờ khóa.
- Tiến trình cơ sở dữ liệu đang chờ CPU, I/O hoặc một tài nguyên nội bộ.
- Yêu cầu đọc/ghi đang chờ thiết bị lưu trữ hoàn tất.

Độ dài hàng đợi là số công việc đang chờ tại thời điểm đo. Một ảnh chụp tức thời có thể dao động mạnh; nên quan sát thêm giá trị trung bình, phân vị cao, thời gian chờ và tuổi của yêu cầu lâu nhất. Hàng đợi ngắn nhưng tồn tại dai dẳng vẫn có thể làm tăng độ trễ. Hàng đợi dài trong một đợt ngắn có thể được giải phóng nhanh nếu hệ thống còn đủ năng lực dự phòng.

Không phải mọi trạng thái chờ đều xuất hiện dưới dạng một hàng đợi có bộ đếm dễ quan sát. Ví dụ, số phiên chờ khóa có thể phản ánh tranh chấp; thời gian chờ theo loại sự kiện giúp giải thích nguyên nhân ngay cả khi không có một chỉ số queue depth duy nhất.

### 2.3. Mức bão hòa tài nguyên

Bão hòa xảy ra khi nhu cầu sử dụng một tài nguyên tiến sát hoặc vượt khả năng phục vụ của tài nguyên đó. Khi không còn đủ năng lực dự phòng, công việc mới phải chờ, bị từ chối hoặc hết thời gian chờ.

Các tài nguyên thường cần theo dõi gồm:

| Tài nguyên hoặc giới hạn | Dấu hiệu có thể quan sát | Hệ quả thường gặp |
|---|---|---|
| CPU | CPU bận kéo dài, run queue tăng, thời gian xử lý CPU cao | Truy vấn và tác vụ nền phải cạnh tranh thời gian xử lý |
| Bộ nhớ | Áp lực bộ nhớ, page fault, swap hoặc bộ nhớ cache giảm | Đọc dữ liệu chậm hơn, phát sinh I/O phụ hoặc nguy cơ bị hệ điều hành kết thúc tiến trình |
| Lưu trữ | Độ trễ đọc/ghi, hàng đợi I/O và thời gian chờ I/O tăng | Truy vấn quét nhiều dữ liệu hoặc ghi nhiều bị kéo dài |
| Kết nối | Pool hết kết nối khả dụng, số yêu cầu chờ lấy kết nối tăng | Ứng dụng chờ trước khi truy vấn đến cơ sở dữ liệu |
| Khóa và giao dịch | Thời gian chờ khóa, giao dịch dài, deadlock hoặc timeout tăng | Truy vấn bị chặn dù CPU và đĩa có thể chưa bận cao |
| Giới hạn nội bộ | Hàng đợi worker, giới hạn tác vụ hoặc giới hạn phiên đạt ngưỡng | Công việc không được tiếp nhận hoặc phải xếp hàng |

Mức sử dụng (utilization) và mức bão hòa (saturation) là hai khái niệm khác nhau. Mức sử dụng mô tả phần năng lực đang được dùng; mức bão hòa phản ánh nhu cầu chưa được đáp ứng và áp lực chờ. CPU có thể bận 80% nhưng không có hàng đợi đáng kể, trong khi connection pool có thể đã bão hòa dù CPU chỉ bận 30%.

## 3. Mối quan hệ giữa tải, thời gian xử lý và số yêu cầu đồng thời

Định luật Little giúp liên hệ lượng công việc trong hệ thống với tốc độ đến và thời gian lưu lại:

\[
L = \lambda \times W
\]

Trong đó:

- `L` là số công việc trung bình trong hệ thống.
- `λ` là tốc độ công việc đi vào hệ thống, thường đo bằng yêu cầu mỗi giây.
- `W` là thời gian trung bình một công việc ở trong hệ thống, tính bằng giây.

Nếu chỉ xét phần đang chờ, có thể áp dụng tương tự:

\[
L_q = \lambda \times W_q
\]

Với `Lq` là số công việc chờ trung bình và `Wq` là thời gian chờ trung bình. Cần dùng cùng một phạm vi đo và cùng đơn vị thời gian; không ghép tốc độ yêu cầu ở tầng HTTP với thời gian chờ riêng ở tầng database nếu chưa xác định tỷ lệ yêu cầu thực sự truy cập cơ sở dữ liệu.

**Ví dụ:** hệ thống xử lý trung bình 10 truy vấn mỗi giây. Nếu mỗi truy vấn ở trong phạm vi đo trung bình 0,2 giây, số truy vấn trung bình trong phạm vi đó là:

\[
L = 10 \times 0{,}2 = 2 \text{ truy vấn}
\]

Nếu thời gian tăng lên 1,5 giây trong khi tốc độ xử lý vẫn là 10 truy vấn mỗi giây, số truy vấn trung bình trong hệ thống tăng lên 15. Tải đến không đổi nhưng thời gian lưu lại dài hơn khiến số công việc đồng thời tăng. Nếu các truy vấn này tiếp tục giữ kết nối, khóa hoặc bộ nhớ, chúng có thể làm giảm năng lực phục vụ các truy vấn mới.

Định luật Little mô tả quan hệ trung bình trong một hệ thống ổn định; nó không tự xác định nguyên nhân làm thời gian tăng và không thay thế phép đo phân vị. Khi tải đến vượt năng lực phục vụ trong thời gian dài, hàng đợi có xu hướng tăng liên tục và giả định ổn định không còn phù hợp.

### 3.1. Tốc độ đến và năng lực phục vụ

Gọi `λ` là tốc độ công việc đến và `μ` là năng lực phục vụ tối đa trong cùng phạm vi. Nếu tải đến duy trì thấp hơn năng lực phục vụ, hệ thống có cơ hội xử lý hết công việc. Khi tải tiến gần năng lực tối đa, phần dự phòng giảm và những dao động nhỏ của thời gian xử lý cũng có thể làm hàng đợi tăng mạnh.

Nếu `λ ≥ μ` kéo dài, hệ thống không thể giải quyết hết lượng công việc đến. Hàng đợi sẽ tăng, độ trễ tăng hoặc hệ thống phải từ chối/giới hạn tải. Trong thực tế, `μ` không phải một hằng số cố định: nó phụ thuộc loại truy vấn, dữ liệu, cache, kích thước giao dịch, mức cạnh tranh và cấu hình tài nguyên.

Vì vậy, mục tiêu vận hành không nên là duy trì mọi tài nguyên ở 100% sử dụng. Cần có khoảng dự phòng đủ để hấp thụ đợt tăng tải và biến động của truy vấn. Khoảng dự phòng phù hợp phải được xác định bằng thử tải và quan sát hệ thống thực tế.

## 4. Bộ chỉ số nên thu thập

Để chẩn đoán được nguyên nhân, hãy kết hợp chỉ số về lượng tải, thời gian, hàng đợi và tài nguyên. Tên metric cụ thể phụ thuộc hệ quản trị cơ sở dữ liệu và nền tảng giám sát, nhưng ý nghĩa cần đo nên tương đương.

| Nhóm | Chỉ số cần theo dõi | Câu hỏi cần trả lời |
|---|---|---|
| Tải vào | Số yêu cầu/truy vấn mỗi giây, số giao dịch mỗi giây | Tải đến đang tăng hay giảm? |
| Đồng thời | Truy vấn đang chạy, phiên hoạt động, giao dịch đang mở | Bao nhiêu công việc đang chiếm tài nguyên? |
| Hàng đợi | Độ sâu hàng đợi, số yêu cầu chờ lấy kết nối, số phiên chờ khóa, hàng đợi I/O | Công việc đang chờ ở tầng nào? |
| Thời gian | Thời gian chờ, thời gian thực thi, độ trễ p50/p95/p99 | Người dùng hoặc truy vấn chậm đến mức nào? |
| Tài nguyên | CPU, bộ nhớ, cache, IOPS, thông lượng và độ trễ lưu trữ | Tài nguyên nào đang gần giới hạn? |
| Kết quả | Timeout, lỗi kết nối, deadlock, truy vấn bị hủy | Hệ thống có đang từ chối hoặc không hoàn thành công việc? |

Nên thu thập dữ liệu theo cùng khoảng thời gian và phân tách theo workload, loại truy vấn, endpoint, nhóm người dùng hoặc máy chủ khi phù hợp. Chỉ số tổng hợp toàn hệ thống có thể che khuất một truy vấn nặng hoặc một nhóm giao dịch gây tranh chấp.

### 4.1. Đo thời gian theo phân vị

Giá trị trung bình hữu ích để tính quan hệ tải, nhưng có thể che giấu một nhóm nhỏ yêu cầu rất chậm. Hãy quan sát ít nhất p50, p95 và p99:

- **p50** mô tả trải nghiệm của yêu cầu ở giữa phân bố.
- **p95** cho biết 5% yêu cầu chậm nhất có độ trễ từ ngưỡng này trở lên.
- **p99** giúp nhận diện phần đuôi rất chậm, thường liên quan đến tranh chấp, truy vấn bất thường hoặc biến động tài nguyên.

Ví dụ, p50 là 40 ms nhưng p99 là 4 giây cho thấy phần lớn yêu cầu nhanh trong khi một nhóm nhỏ gặp vấn đề nghiêm trọng. Khi đó cần phân tích truy vấn, trạng thái chờ và workload tương ứng thay vì chỉ nhìn độ trễ trung bình.

### 4.2. Đo hàng đợi theo cả số lượng và thời gian

Độ dài hàng đợi trả lời có bao nhiêu công việc đang chờ; thời gian chờ trả lời công việc phải chờ bao lâu. Hai giá trị này bổ sung cho nhau. Một hàng đợi có 5 yêu cầu nhưng yêu cầu cũ nhất đã chờ 20 giây có thể đáng lo hơn hàng đợi 20 yêu cầu được giải phóng trong vài mili giây.

Với connection pool, nên ghi nhận số kết nối đang dùng, số kết nối khả dụng, số yêu cầu đang chờ, thời gian chờ lấy kết nối và số lần timeout. Với khóa, nên ghi nhận số phiên bị chặn, thời gian chặn, phiên giữ khóa và loại giao dịch liên quan. Với lưu trữ, cần xem độ trễ I/O cùng hàng đợi và thông lượng để tránh kết luận chỉ từ một chỉ số IOPS.

## 5. Cách đọc các tổ hợp chỉ số

Không có một ngưỡng sử dụng chung phù hợp cho mọi hệ thống. Hãy tìm mối tương quan theo thời gian giữa tải đến, hàng đợi, độ trễ và tài nguyên.

| Quan sát | Diễn giải có thể có | Hướng kiểm tra tiếp theo |
|---|---|---|
| Đồng thời tăng, độ trễ tăng, hàng đợi tăng | Năng lực phục vụ không theo kịp tải hoặc thời gian xử lý đã tăng | Xác định hàng đợi nằm ở pool, khóa, CPU hay I/O |
| CPU cao kéo dài, run queue tăng, truy vấn hoạt động nhiều | Cạnh tranh CPU hoặc truy vấn tiêu tốn tính toán | Xem kế hoạch thực thi, phép nối, sắp xếp, biểu thức và truy vấn chạy lặp |
| CPU thấp nhưng chờ I/O và độ trễ đọc/ghi cao | Nút thắt có thể nằm ở lưu trữ hoặc mẫu truy cập dữ liệu | Kiểm tra đọc vật lý, ghi, cache hit, kích thước quét và độ trễ thiết bị |
| Pool hết kết nối, yêu cầu chờ lấy kết nối, DB chưa bận cao | Giới hạn pool, kết nối bị giữ lâu hoặc giao dịch không được đóng đúng lúc | Đo thời gian giữ kết nối, kiểm tra vòng đời giao dịch và truy vấn chậm |
| Nhiều phiên chờ khóa, thời gian giao dịch dài | Tranh chấp ghi hoặc thứ tự truy cập tài nguyên không thuận lợi | Tìm giao dịch giữ khóa lâu, truy vấn cập nhật cùng dữ liệu và deadlock |
| Độ trễ p99 tăng nhưng p50 ổn định | Một nhóm nhỏ truy vấn hoặc thời điểm tải gây chậm | Phân nhóm theo câu SQL, tham số, bảng, máy chủ và thời điểm |
| Hàng đợi tăng dù mức sử dụng trung bình thấp | Có thể có giới hạn cục bộ, phân vùng tải không đều hoặc chờ khóa | Xem theo từng node, pool, shard, worker và loại sự kiện chờ |

Các diễn giải trong bảng là giả thuyết để điều tra, không phải kết luận tự động. Cần xác nhận bằng kế hoạch thực thi, thống kê truy vấn, wait events, log và dữ liệu tài nguyên ở cùng thời điểm.

## 6. Ví dụ: pool đầy trong khi lưu trữ bị bão hòa

Một dịch vụ có connection pool tối đa 40 kết nối. Trong giờ cao điểm, dashboard ghi nhận:

- 36 kết nối đang được sử dụng và 4 kết nối khả dụng gần như bằng không.
- 22 yêu cầu đang chờ lấy kết nối.
- Độ trễ p95 của thao tác đọc tăng từ 120 ms lên 2,4 giây.
- Nhiều truy vấn đang chờ đọc dữ liệu; độ trễ đọc lưu trữ tăng và thiết bị thường xuyên có hàng đợi.
- CPU của máy chủ cơ sở dữ liệu chỉ ở mức trung bình.

Nếu chỉ nhìn CPU, có thể nghĩ rằng máy chủ còn dư năng lực và tăng pool lên 80. Tuy nhiên, dữ liệu cho thấy truy vấn đang giữ kết nối lâu vì chờ đọc. Tăng số kết nối có thể đưa thêm truy vấn vào cùng thiết bị lưu trữ, làm tăng cạnh tranh I/O, kéo dài thời gian giữ kết nối và khiến hàng đợi lớn hơn.

Quy trình xử lý hợp lý là:

1. Xác định các câu SQL chiếm nhiều thời gian đọc và kiểm tra kế hoạch thực thi.
2. Kiểm tra số hàng được đọc so với số hàng trả về, điều kiện lọc, chỉ mục và khả năng truy vấn quét quá nhiều dữ liệu.
3. Điều chỉnh truy vấn hoặc chỉ mục dựa trên kế hoạch và thống kê; cân nhắc phân trang, giới hạn dữ liệu hoặc giảm truy cập lặp nếu phù hợp với yêu cầu nghiệp vụ.
4. Chạy lại cùng kịch bản tải, giữ nguyên dữ liệu và điều kiện so sánh.
5. Đối chiếu độ trễ p95/p99, số truy vấn đồng thời, thời gian chờ I/O, độ sâu hàng đợi và số yêu cầu chờ connection pool.

Chỉ xem xét thay đổi kích thước pool sau khi đã hiểu năng lực phục vụ của cơ sở dữ liệu và thời gian giữ kết nối. Pool cần đủ để tận dụng tài nguyên nhưng không nên tạo tải đồng thời vượt quá khả năng xử lý của hệ thống.

## 7. Đặt mục tiêu và ngưỡng cảnh báo

Mục tiêu phải gắn với trải nghiệm và yêu cầu nghiệp vụ. Không có một con số phổ quát như CPU dưới 70%, pool dưới 80% hay hàng đợi luôn bằng 0 có thể áp dụng cho mọi cơ sở dữ liệu.

Khi xây dựng mục tiêu, hãy xác định:

1. **Mức tải dự kiến:** tốc độ yêu cầu bình thường, giờ cao điểm, đợt tăng tải và tốc độ tăng trưởng dữ liệu.
2. **Mục tiêu độ trễ:** p95/p99 cho các thao tác quan trọng, thời gian chờ lấy kết nối và thời gian chờ khóa.
3. **Giới hạn chấp nhận được:** timeout, lỗi, deadlock và số yêu cầu bị từ chối.
4. **Khoảng dự phòng:** năng lực còn lại khi hệ thống đang ở mức tải cao đã dự báo.
5. **Thời gian duy trì:** một đỉnh ngắn có thể không cần cảnh báo như tình trạng hàng đợi tăng liên tục trong nhiều phút.

Có thể bắt đầu với mục tiêu thử nghiệm, sau đó hiệu chỉnh theo dữ liệu tải thật. Ví dụ minh họa: một dịch vụ đặt mục tiêu p95 truy vấn đọc dưới 300 ms ở tải đỉnh dự kiến, không có timeout lấy kết nối trong bài thử tải và hàng đợi không tăng liên tục trong giai đoạn ổn định. Đây chỉ là mục tiêu giả định; hệ thống thực tế cần chọn ngưỡng theo SLO, loại truy vấn và năng lực hạ tầng.

Một cảnh báo hữu ích thường kết hợp nhiều điều kiện: hàng đợi tăng, thời gian chờ vượt mục tiêu, độ trễ p95 tăng và tình trạng kéo dài đủ lâu. Cảnh báo theo một mẫu số đơn lẻ có thể tạo nhiều báo động giả, ví dụ CPU tăng ngắn hạn nhưng không làm tăng độ trễ hoặc hàng đợi.

## 8. Quy trình đo và kiểm chứng khi tối ưu

Để biết một thay đổi có cải thiện hiệu năng hay không, cần so sánh trước và sau trong điều kiện tương đương.

1. **Chọn workload đại diện.** Ghi lại loại truy vấn, tỷ lệ đọc/ghi, kích thước dữ liệu, phân bố tham số và mức đồng thời.
2. **Thiết lập đường cơ sở.** Đo throughput, số yêu cầu đồng thời, độ sâu và thời gian chờ, p50/p95/p99, CPU, bộ nhớ, I/O, kết nối và khóa.
3. **Tăng tải có kiểm soát.** Thử từ tải thấp đến tải mục tiêu, sau đó tăng dần để tìm điểm hàng đợi và độ trễ bắt đầu tăng nhanh.
4. **Xác định nơi chờ.** Ghép dữ liệu theo thời gian để tìm xem công việc đang chờ connection pool, khóa, CPU, I/O hay giới hạn khác.
5. **Thay đổi một yếu tố có chủ đích.** Ví dụ sửa kế hoạch truy vấn, bổ sung chỉ mục phù hợp hoặc giảm thời gian giữ giao dịch. Ghi rõ giả thuyết và tác động dự kiến.
6. **Chạy lại cùng kịch bản.** Giữ tương đương dữ liệu, cache, số máy khách, thời lượng và tốc độ tải; ghi lại mọi khác biệt của môi trường.
7. **Đánh giá cả hiệu năng lẫn chi phí.** Kiểm tra throughput, p95/p99, hàng đợi, thời gian chờ, tài nguyên, dung lượng chỉ mục và chi phí ghi.
8. **Kiểm tra tải đỉnh và độ bền.** Một thay đổi có thể tốt trong vài phút nhưng gây tăng bộ nhớ, phình cache hoặc chi phí bảo trì chỉ mục khi chạy lâu.

Không coi việc giảm CPU hoặc giảm số kết nối là thành công nếu throughput giảm hoặc độ trễ người dùng tăng. Kết quả tốt cần cải thiện mục tiêu đã chọn mà vẫn giữ tính đúng đắn dữ liệu và các giới hạn vận hành.

## 9. Những sai lầm thường gặp

- **Đồng nhất kết nối với truy vấn đồng thời:** nhiều kết nối có thể đang rảnh; ít kết nối vẫn có thể bị giữ lâu bởi giao dịch.
- **Chỉ nhìn giá trị trung bình:** p95/p99 và thời gian chờ lâu nhất có thể cho thấy vấn đề bị che khuất.
- **Chỉ đo một tầng:** ứng dụng có thể chờ pool trong khi cơ sở dữ liệu không có nhiều truy vấn hoạt động.
- **Chỉ nhìn mức sử dụng:** tài nguyên có thể chưa bận cao nhưng một giới hạn cục bộ hoặc khóa đã làm công việc phải chờ.
- **Tăng pool để chữa mọi trường hợp:** nhiều kết nối hơn có thể làm tăng tranh chấp CPU, I/O, bộ nhớ và khóa.
- **Dùng ảnh chụp đơn lẻ:** cần quan sát xu hướng, thời gian duy trì và tương quan giữa các chỉ số.
- **So sánh hai lần thử tải không tương đương:** khác dữ liệu, cache, tốc độ tải hoặc số máy khách có thể làm kết quả sai lệch.
- **Đặt ngưỡng cảnh báo tùy tiện:** ngưỡng cần dựa trên SLO, năng lực đã đo và hậu quả của việc chờ.

## 10. Bài tập tự kiểm tra

### Bài tập 1: Tính số truy vấn trung bình

Một workload xử lý 25 truy vấn mỗi giây. Thời gian trung bình một truy vấn nằm trong phạm vi đo là 0,4 giây. Ước tính số truy vấn trung bình trong hệ thống bằng định luật Little.

**Gợi ý:** nhân tốc độ truy vấn với thời gian lưu lại, nhớ giữ đơn vị giây.

**Đáp án:** `L = 25 × 0,4 = 10`. Có trung bình khoảng 10 truy vấn trong phạm vi đo. Đây không nhất thiết là số phiên kết nối đang mở.

### Bài tập 2: Xác định tầng đang gây chờ

Một ứng dụng báo thời gian phản hồi tăng. Số kết nối đang dùng đạt giới hạn pool và số yêu cầu chờ lấy kết nối tăng. Trong khi đó, CPU database thấp và số truy vấn đang chạy không cao.

**Câu hỏi:** cần kiểm tra gì trước khi tăng kích thước pool?

**Gợi ý trả lời:** đo thời gian giữ kết nối, tìm truy vấn hoặc giao dịch chậm, kiểm tra kết nối có được trả lại sau khi xử lý hay không, và xác định yêu cầu đang chờ ở tầng ứng dụng hay database. Sau đó mới đánh giá liệu cơ sở dữ liệu còn năng lực nhận thêm truy vấn đồng thời.

### Bài tập 3: Phân biệt sử dụng và bão hòa

CPU trung bình chỉ đạt 45%, nhưng hàng đợi I/O tăng và p99 truy vấn đọc tăng mạnh.

**Câu hỏi:** vì sao không thể kết luận hệ thống còn nhiều năng lực chỉ từ CPU?

**Gợi ý trả lời:** CPU không phải tài nguyên duy nhất. Truy vấn có thể đang chờ lưu trữ; cần xem độ trễ đọc/ghi, thông lượng, hàng đợi I/O, lượng dữ liệu đọc vật lý và kế hoạch thực thi.

### Checklist khi đọc dashboard

- [ ] Đã xác định rõ tầng và đơn vị của chỉ số đồng thời.
- [ ] Đã phân biệt kết nối mở, phiên hoạt động, truy vấn chạy và giao dịch mở.
- [ ] Đã đo hàng đợi cùng thời gian chờ hoặc tuổi yêu cầu.
- [ ] Đã xem p50, p95 và p99 bên cạnh giá trị trung bình.
- [ ] Đã đối chiếu tải đến với throughput và tài nguyên đang bão hòa.
- [ ] Đã kiểm tra các trạng thái chờ CPU, I/O, khóa và connection pool.
- [ ] Đã so sánh trước/sau tối ưu trên workload tương đương.

Khi đọc được đồng thời lượng công việc, nơi công việc đang chờ và mức bão hòa của tài nguyên, nhóm vận hành có thể xác định điểm nghẽn bằng bằng chứng. Đây là cơ sở để chọn thay đổi SQL, chỉ mục, giao dịch, cấu hình pool hoặc tài nguyên hạ tầng, rồi kiểm chứng rằng hệ thống phục vụ được nhiều tải hơn với độ trễ và tỷ lệ lỗi nằm trong mục tiêu.
