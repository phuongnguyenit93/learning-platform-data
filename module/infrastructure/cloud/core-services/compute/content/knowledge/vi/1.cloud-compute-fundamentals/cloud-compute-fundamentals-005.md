# Phân loại workload theo thời gian chạy, trạng thái và nhu cầu tài nguyên

Khi triển khai một ứng dụng trên đám mây, câu hỏi đầu tiên không nên chỉ là “cần bao nhiêu máy ảo?”. Cần hiểu ứng dụng thực hiện công việc gì, chạy trong bao lâu, giữ trạng thái ở đâu và tiêu thụ tài nguyên theo cách nào. Những đặc điểm này quyết định mô hình tính toán phù hợp, cách mở rộng tải, cách bảo đảm tính sẵn sàng và tổng chi phí vận hành.

Trong bài học về nền tảng cloud compute, **workload** (khối lượng công việc) là một dịch vụ, tiến trình hoặc nhóm tác vụ sử dụng tài nguyên tính toán để xử lý yêu cầu hay dữ liệu. Một hệ thống thực tế thường gồm nhiều workload khác nhau. Ví dụ, một cửa hàng trực tuyến có API phục vụ người dùng, cơ sở dữ liệu lưu đơn hàng, tác vụ xử lý ảnh và quy trình tổng hợp báo cáo ban đêm. Các thành phần này có đặc tính khác nhau nên có thể cần những mô hình triển khai khác nhau.

Bài học này trình bày ba trục phân loại chính:

- **Thời gian chạy:** workload chạy trong thời gian ngắn, theo lô, liên tục hay theo luồng sự kiện.
- **Trạng thái:** workload có cần giữ dữ liệu qua nhiều lần thực thi hay không, và dữ liệu đó cần được bảo toàn ở mức nào.
- **Nhu cầu tài nguyên:** workload chủ yếu cần CPU, bộ nhớ, lưu trữ, mạng hay bộ tăng tốc như GPU.

Ba trục này độc lập tương đối. Một tác vụ chạy vài phút vẫn có thể cần nhiều RAM; một dịch vụ chạy liên tục có thể hoàn toàn stateless; một workload dùng GPU có thể là tác vụ batch hoặc dịch vụ tương tác. Phân loại đúng từng trục giúp chọn VM, container, serverless hoặc dịch vụ quản lý phù hợp.

## 1. Hiểu workload trước khi chọn mô hình compute

Workload mô tả **mẫu sử dụng tài nguyên và hành vi thực thi**, không đồng nghĩa với một máy chủ hay một công nghệ cụ thể. Một workload có thể chạy trên máy ảo, trong container hoặc trên nền tảng serverless tùy yêu cầu.

Khi khảo sát một workload, hãy trả lời các câu hỏi sau:

1. Công việc được kích hoạt bởi yêu cầu của người dùng, lịch định kỳ, thông điệp trong hàng đợi hay một luồng dữ liệu?
2. Một lần thực thi kéo dài bao lâu? Tiến trình kết thúc sau khi hoàn thành hay phải chạy liên tục?
3. Nếu tiến trình bị khởi động lại, dữ liệu nào phải còn nguyên? Có thể chạy lại tác vụ an toàn không?
4. Thành phần nào giới hạn hiệu năng: CPU, RAM, tốc độ đọc ghi, băng thông mạng hay GPU?
5. Tải ổn định hay biến động mạnh? Hệ thống ưu tiên độ trễ thấp, thông lượng cao hay chi phí thấp?
6. Workload cần quyền truy cập, kết nối mạng và mức cô lập nào?

Không nên phân loại chỉ dựa vào tên ứng dụng. Một ứng dụng có thể chứa nhiều loại workload. Ví dụ, cùng một hệ thống có thể có API tương tác, worker xử lý hàng đợi, tác vụ batch và cơ sở dữ liệu stateful.

## 2. Phân loại theo thời gian chạy

Thời gian chạy cho biết workload tồn tại trong bao lâu và cách nó bắt đầu, kết thúc. Đây là cơ sở để lựa chọn cách cấp phát tài nguyên, cơ chế điều phối và chính sách mở rộng.

| Loại workload | Đặc điểm | Ví dụ | Yêu cầu thường gặp |
|---|---|---|---|
| Tương tác hoặc theo yêu cầu | Xử lý một yêu cầu rồi trả kết quả; thường cần phản hồi nhanh | API, truy vấn tìm kiếm, xác thực | Độ trễ thấp, sẵn sàng liên tục, mở rộng theo lưu lượng |
| Tác vụ ngắn hạn | Chạy trong thời gian ngắn rồi kết thúc | Gửi email, tạo thumbnail, kiểm tra dữ liệu | Khởi động nhanh, thực thi đáng tin cậy, xử lý lỗi và chạy lại |
| Batch (xử lý theo lô) | Xử lý một tập dữ liệu hoặc danh sách công việc; có điểm bắt đầu và kết thúc | Tính lương, tổng hợp báo cáo, nhập dữ liệu | Thông lượng, hàng đợi, checkpoint và khả năng chạy lại |
| Dịch vụ dài hạn | Tiến trình chạy liên tục để nhận và xử lý yêu cầu | Web server, API backend, worker nền | Giám sát sức khỏe, triển khai cập nhật, mở rộng và phục hồi |
| Streaming (xử lý luồng) | Tiếp nhận dữ liệu liên tục, xử lý sự kiện theo thời gian | Phân tích clickstream, giám sát cảm biến, phát hiện gian lận | Thông lượng ổn định, độ trễ xử lý, quản lý offset và trạng thái cửa sổ |
| Tác vụ theo lịch | Bắt đầu tại thời điểm hoặc chu kỳ xác định | Sao lưu, đồng bộ, báo cáo hằng ngày | Lịch chạy tin cậy, tránh chạy trùng, theo dõi lần chạy thất bại |

### 2.1. Workload tương tác

Workload tương tác thường nằm trên đường đi trực tiếp của người dùng. Khi người dùng mở trang sản phẩm, API phải phản hồi trong khoảng thời gian chấp nhận được. Một tiến trình xử lý chậm có thể làm tăng độ trễ của toàn bộ yêu cầu, ngay cả khi CPU chưa đạt mức sử dụng tối đa.

Vì vậy, cần đo độ trễ theo phân vị như p95 hoặc p99, số yêu cầu mỗi giây, số kết nối đồng thời và tỷ lệ lỗi. Trung bình độ trễ có thể che khuất một nhóm nhỏ yêu cầu rất chậm. Các API thường được triển khai thành nhiều bản sao để có thể phân phối tải và tiếp tục phục vụ khi một bản sao gặp lỗi.

### 2.2. Tác vụ ngắn hạn và batch

Tác vụ ngắn hạn thường được kích hoạt bởi sự kiện hoặc thông điệp. Tác vụ batch xử lý một khối lượng công việc hữu hạn, có thể mất vài phút hoặc vài giờ. Cả hai loại đều cần xác định rõ điều gì xảy ra khi tiến trình dừng giữa chừng.

Một thiết kế bền vững thường đưa công việc vào hàng đợi, để worker lấy từng phần việc và xác nhận hoàn thành sau khi xử lý thành công. Nếu worker bị lỗi, thông điệp có thể được giao lại. Do đó, thao tác xử lý nên **idempotent** (có thể thực hiện lặp lại mà không tạo ra kết quả sai hoặc hiệu ứng phụ trùng lặp). Với batch lớn, checkpoint giúp tiếp tục từ vị trí đã xử lý thay vì bắt đầu lại toàn bộ.

Không phải mọi tác vụ batch đều phù hợp với một hàm serverless. Cần kiểm tra giới hạn thời gian thực thi, bộ nhớ, kích thước dữ liệu, thời gian khởi động và khả năng checkpoint của nền tảng. Tác vụ dài hoặc cần môi trường đặc biệt có thể phù hợp hơn với container job, dịch vụ batch được quản lý hoặc VM.

### 2.3. Dịch vụ dài hạn và streaming

Dịch vụ dài hạn duy trì tiến trình để liên tục nhận yêu cầu hoặc công việc. Chúng cần cơ chế kiểm tra sức khỏe, xử lý tín hiệu dừng, cập nhật phiên bản và khởi động lại khi có lỗi. Khi triển khai nhiều bản sao, ứng dụng phải xử lý được việc một bản sao biến mất bất kỳ lúc nào.

Streaming cũng chạy liên tục, nhưng trọng tâm là tiếp nhận và xử lý chuỗi sự kiện. Hệ thống phải theo dõi vị trí đã đọc, xử lý sự kiện đến trễ hoặc trùng lặp và kiểm soát tốc độ tiêu thụ. Nếu tốc độ dữ liệu đầu vào cao hơn tốc độ xử lý trong thời gian dài, hàng đợi hoặc độ trễ xử lý sẽ tăng. Đây là tín hiệu cần tăng năng lực xử lý, giảm chi phí mỗi sự kiện hoặc áp dụng backpressure (điều tiết luồng đầu vào).

## 3. Phân loại theo trạng thái

**Trạng thái (state)** là dữ liệu mà workload cần ghi nhớ giữa các yêu cầu, giữa các lần xử lý hoặc qua các lần khởi động. Phân biệt stateless và stateful giúp quyết định cách mở rộng, lưu trữ và phục hồi.

### 3.1. Stateless workload

Một workload stateless không cần giữ trạng thái nghiệp vụ cục bộ giữa hai lần xử lý. Mỗi yêu cầu có thể được xử lý bởi bất kỳ bản sao nào, miễn là bản sao đó có đủ dữ liệu đầu vào và có thể truy cập các dịch vụ phụ thuộc.

Ví dụ, API nhận mã đơn hàng, đọc thông tin từ cơ sở dữ liệu và trả kết quả. Nếu API không lưu phiên người dùng trong bộ nhớ cục bộ, nhiều bản sao có thể phục vụ cùng một loại yêu cầu. Khi một bản sao bị thay thế, yêu cầu tiếp theo được chuyển sang bản sao còn khỏe mạnh.

Stateless thường thuận lợi cho mở rộng ngang (horizontal scaling), cân bằng tải và triển khai cuốn chiếu. Tuy vậy, stateless không có nghĩa là toàn hệ thống không có dữ liệu trạng thái. Trạng thái có thể được lưu trong cơ sở dữ liệu, cache dùng chung, object storage hoặc dịch vụ quản lý phiên.

### 3.2. Stateful workload

Workload stateful cần duy trì trạng thái qua nhiều lần thực thi. Ví dụ gồm cơ sở dữ liệu, hệ thống quản lý phiên, message broker, bộ xử lý streaming có cửa sổ trạng thái và ứng dụng ghi dữ liệu vào ổ đĩa cục bộ.

Khi mở rộng hoặc thay thế một bản sao stateful, cần biết dữ liệu đang nằm ở đâu, bản sao nào có quyền ghi và cách khôi phục dữ liệu. Những yêu cầu thường gặp gồm:

- **Độ bền dữ liệu:** dữ liệu có phải tồn tại sau khi VM hoặc container bị xóa không?
- **Tính nhất quán:** các bản sao cần nhìn thấy cùng một phiên bản dữ liệu ở thời điểm nào?
- **Sao lưu và phục hồi:** có bản sao lưu định kỳ, bản sao ở vùng khác và quy trình khôi phục đã được thử nghiệm không?
- **Phân vùng dữ liệu:** dữ liệu được chia shard hoặc partition như thế nào khi tải tăng?
- **Khả năng chịu lỗi:** nếu nút đang giữ dữ liệu chính bị lỗi, nút khác tiếp quản ra sao?

Một container có thể chạy ứng dụng stateful, nhưng container tự nó không bảo đảm dữ liệu bền vững. Dữ liệu cần được đặt trên persistent volume hoặc dịch vụ lưu trữ phù hợp. Với cơ sở dữ liệu quan trọng, dịch vụ cơ sở dữ liệu được quản lý thường giảm gánh nặng vận hành về sao lưu, bản vá và chuyển đổi dự phòng.

### 3.3. Trạng thái tạm thời và trạng thái bền vững

Không phải mọi dữ liệu trong bộ nhớ đều cần lưu lâu dài. Có thể chia dữ liệu thành:

- **Dữ liệu tạm thời:** cache, file trung gian, dữ liệu tính toán có thể tạo lại. Mất dữ liệu thường chỉ làm tăng thời gian xử lý.
- **Dữ liệu phiên:** thông tin đăng nhập hoặc giỏ hàng cần tồn tại qua nhiều yêu cầu, nhưng có thể có thời hạn hết hạn.
- **Dữ liệu nghiệp vụ bền vững:** đơn hàng, thanh toán, hồ sơ khách hàng hoặc kết quả xử lý cần được bảo toàn và sao lưu.
- **Trạng thái tiến trình:** offset, checkpoint, trạng thái cửa sổ hoặc vị trí xử lý để tiếp tục công việc sau khi khởi động lại.

Hãy xác định rõ loại dữ liệu trước khi chọn ổ đĩa, volume hoặc dịch vụ lưu trữ. Lưu dữ liệu nghiệp vụ quan trọng trên ổ đĩa tạm của một máy tính toán có thể khiến dữ liệu mất khi máy bị thay thế.

## 4. Phân loại theo nhu cầu tài nguyên

Hai workload có cùng thời gian chạy và cùng trạng thái vẫn có thể cần cấu hình compute rất khác nhau. Cần tìm tài nguyên đang giới hạn hiệu năng (bottleneck) thay vì chỉ tăng số CPU theo cảm tính.

| Nhóm tài nguyên | Dấu hiệu workload bị giới hạn | Ví dụ | Hướng tối ưu |
|---|---|---|---|
| CPU-bound | CPU sử dụng cao; thời gian xử lý chủ yếu dành cho tính toán | Nén dữ liệu, mã hóa, tính toán mô phỏng | Tăng năng lực CPU, tối ưu thuật toán và mức song song |
| Memory-bound | Working set lớn; áp lực bộ nhớ, garbage collection hoặc lỗi hết bộ nhớ | Phân tích dữ liệu trong RAM, cache lớn | Tăng RAM, giảm bản sao dữ liệu, xử lý theo luồng hoặc theo lô nhỏ |
| Storage I/O-bound | Độ trễ đọc ghi hoặc hàng đợi đĩa cao; CPU có thể vẫn nhàn rỗi | Cơ sở dữ liệu, xử lý file lớn | Chọn loại lưu trữ phù hợp, cải thiện truy vấn, cache và bố trí dữ liệu |
| Network I/O-bound | Chờ mạng nhiều, băng thông hoặc số kết nối là giới hạn | Proxy, API tích hợp, truyền file | Kiểm tra băng thông, độ trễ, số kết nối, vị trí vùng và giới hạn dịch vụ |
| GPU/accelerator-bound | Tính toán song song phù hợp với bộ tăng tốc; CPU không phải giới hạn chính | Huấn luyện mô hình, suy luận AI, xử lý ảnh/video | Chọn GPU phù hợp, tối ưu batch size, bộ nhớ GPU và mức sử dụng thiết bị |
| Hỗn hợp | Nhiều tài nguyên cùng ảnh hưởng hoặc bottleneck thay đổi theo giai đoạn | Pipeline dữ liệu, ứng dụng phân tích | Đo theo từng giai đoạn và tách workload nếu cần |

### 4.1. CPU-bound

CPU-bound workload cần nhiều chu kỳ xử lý. Ví dụ là mã hóa video, nén dữ liệu, tính toán khoa học hoặc xử lý logic phức tạp. Tăng số vCPU có thể cải thiện thông lượng nếu chương trình tận dụng được song song. Nếu phần lớn công việc chạy tuần tự, tăng vCPU có thể không làm chương trình nhanh hơn đáng kể.

Hãy đo mức sử dụng CPU, thời gian CPU trên mỗi tác vụ, độ trễ và mức song song thực tế. Ngoài số lượng vCPU, hiệu năng mỗi lõi và kiến trúc CPU cũng có thể ảnh hưởng kết quả.

### 4.2. Memory-bound

Memory-bound workload cần giữ một tập dữ liệu lớn trong RAM hoặc tạo nhiều đối tượng trong quá trình xử lý. Thiếu RAM có thể khiến hệ điều hành dùng swap, làm độ trễ tăng mạnh, hoặc khiến container/tiến trình bị kết thúc do vượt giới hạn bộ nhớ.

Nên đo working set, mức sử dụng bộ nhớ cực đại, tốc độ tăng bộ nhớ theo thời gian và hành vi khi tải tăng. Cần dành khoảng trống cho bộ nhớ runtime, cache, kết nối và đỉnh tải. Cấp phát RAM quá sát mức trung bình dễ gây lỗi khi có nhiều yêu cầu đồng thời.

### 4.3. Storage I/O-bound

Workload I/O-bound thường chờ đọc hoặc ghi dữ liệu. Với cơ sở dữ liệu, các chỉ số như độ trễ I/O, IOPS, thông lượng và độ sâu hàng đợi có thể quan trọng hơn CPU. Lưu trữ có IOPS cao nhưng độ trễ không phù hợp hoặc dung lượng không đủ vẫn có thể làm ứng dụng chậm.

Phân biệt dữ liệu cần truy cập nhanh với dữ liệu lưu trữ dài hạn. Có thể dùng cache cho dữ liệu đọc thường xuyên, tối ưu truy vấn, gom các thao tác ghi hoặc chuyển file lớn sang object storage. Không nên dùng một loại ổ đĩa cho mọi mục đích chỉ vì đơn giá thấp.

### 4.4. Network I/O-bound

Workload mạng phụ thuộc băng thông, độ trễ, số kết nối đồng thời và khoảng cách giữa các thành phần. Một API gọi nhiều dịch vụ ở các vùng khác nhau có thể chậm dù CPU và RAM còn dư. Truyền dữ liệu lớn ra ngoài đám mây cũng có thể tạo chi phí đáng kể.

Hãy đo thời gian chờ mạng, tỷ lệ timeout, số kết nối, lưu lượng vào/ra và chi phí truyền dữ liệu. Đặt các thành phần trao đổi dữ liệu thường xuyên gần nhau về mặt vùng triển khai, đồng thời giới hạn retry để tránh khuếch đại tải khi dịch vụ phụ thuộc gặp sự cố.

### 4.5. GPU và bộ tăng tốc

GPU phù hợp với một số phép tính song song lớn như huấn luyện mô hình học máy, suy luận AI hoặc xử lý hình ảnh. GPU thường có chi phí cao hơn tài nguyên CPU thông thường và có bộ nhớ riêng. Chọn GPU cần dựa trên loại phép tính, dung lượng bộ nhớ thiết bị, độ chính xác số, khả năng tương thích phần mềm và mức sử dụng dự kiến.

Nếu workload chỉ dùng GPU trong một phần ngắn của quy trình, có thể tách giai đoạn đó thành job riêng. Cách này giúp các bước tiền xử lý hoặc hậu xử lý không phải giữ GPU trong lúc chờ I/O.

## 5. Xem thêm hình dạng tải và mục tiêu dịch vụ

Ba trục thời gian chạy, trạng thái và tài nguyên là nền tảng, nhưng chưa đủ để chọn cấu hình cuối cùng. Cần xem tải thay đổi ra sao:

- **Tải ổn định:** nhu cầu tương đối đều; phù hợp với năng lực nền được cấp phát ổn định.
- **Tải đột biến:** có các đỉnh ngắn; cần khả năng mở rộng nhanh, hàng đợi hoặc giới hạn tốc độ.
- **Tải theo mùa hoặc theo lịch:** tăng vào giờ cao điểm, chiến dịch bán hàng hoặc cuối kỳ; cần lập kế hoạch trước và tự động co giãn.
- **Tải khó dự đoán:** có thể phù hợp với mô hình tính phí theo mức sử dụng, nhưng vẫn phải kiểm soát giới hạn, độ trễ khởi động và chi phí cực đại.

Mục tiêu dịch vụ cũng ảnh hưởng lựa chọn. Workload cần phản hồi trong vài chục mili giây có yêu cầu khác với batch có thể hoàn thành trong vài giờ. Hãy xác định SLA/SLO phù hợp, ví dụ độ sẵn sàng, độ trễ p95, tỷ lệ xử lý thành công và thời gian khôi phục.

## 6. Ghép đặc tính workload với mô hình cloud compute

Các mô hình compute phổ biến có ưu và nhược điểm khác nhau. Việc chọn mô hình nên dựa trên đặc tính workload và mức kiểm soát hạ tầng cần thiết.

| Mô hình | Phù hợp khi | Điểm cần cân nhắc |
|---|---|---|
| Virtual Machine (VM) | Cần kiểm soát hệ điều hành, kernel, phần mềm cũ, cấu hình máy đặc biệt hoặc tiến trình dài hạn | Phải quản lý bản vá, hệ điều hành, dung lượng dự phòng và khả năng mở rộng |
| Container | Muốn đóng gói ứng dụng nhất quán, triển khai nhiều bản sao, chạy dịch vụ hoặc job trên môi trường điều phối | Cần quản lý image, tài nguyên, mạng, lưu trữ và nền tảng điều phối |
| Serverless function | Tác vụ ngắn, kích hoạt theo sự kiện, tải biến động và ít cần quản lý máy chủ | Có giới hạn thời gian, bộ nhớ, kích thước gói, thời gian khởi động và khả năng lưu trạng thái tùy nền tảng |
| Serverless container hoặc application platform | API, worker hoặc job cần môi trường container nhưng muốn giảm công việc quản lý máy chủ | Kiểm tra khả năng chạy liên tục, cấu hình mạng, giới hạn tài nguyên và mô hình tính phí |
| Dịch vụ batch/stream được quản lý | Cần lập lịch job, xử lý hàng đợi hoặc luồng dữ liệu ở quy mô lớn | Phụ thuộc tính năng, giới hạn và chi phí của dịch vụ; cần thiết kế retry và quan sát phù hợp |

### 6.1. Khi nào chọn VM?

VM cung cấp môi trường máy tính ảo với hệ điều hành và tài nguyên được cấp phát. VM phù hợp khi ứng dụng cần quyền kiểm soát sâu, phụ thuộc kernel hoặc thư viện hệ thống đặc biệt, hoặc cần duy trì tiến trình lâu dài. Một số phần mềm cũ cũng dễ chuyển lên VM hơn là viết lại để chạy trong container.

Đổi lại, nhóm vận hành phải chịu trách nhiệm cập nhật hệ điều hành, cấu hình bảo mật, giám sát, sao lưu và mở rộng số lượng máy. Nếu workload chỉ chạy vài giây mỗi giờ, VM luôn bật có thể tạo nhiều thời gian nhàn rỗi.

### 6.2. Khi nào chọn container?

Container đóng gói ứng dụng cùng các phụ thuộc cần thiết để chạy nhất quán trên các môi trường tương thích. Container có thể chạy dịch vụ dài hạn, worker nền hoặc job batch. Khi kết hợp với nền tảng điều phối, hệ thống có thể quản lý replica, phân phối tải, tự phục hồi và mở rộng theo chỉ số.

Container không tự động giải quyết mọi vấn đề vận hành. Cần xác định CPU/RAM, cách ghi log, xử lý tín hiệu dừng, readiness/liveness probe, lưu trữ bền vững và chính sách cập nhật image. Với workload stateful, phải thiết kế volume, sao lưu và cơ chế phục hồi riêng.

### 6.3. Khi nào chọn serverless?

Serverless chuyển phần lớn công việc cấp phát và quản lý máy chủ sang nhà cung cấp. Với function, nhà cung cấp thường kích hoạt mã khi có sự kiện và tính phí theo mức sử dụng theo mô hình của dịch vụ. Đây là lựa chọn phù hợp cho tác vụ ngắn, xử lý sự kiện, webhook hoặc các bước tự động hóa có tải không đều.

Serverless không có nghĩa là không có máy chủ; máy chủ vẫn tồn tại nhưng người dùng ít phải quản lý trực tiếp. Cần kiểm tra giới hạn thời gian chạy, bộ nhớ, concurrency, cold start, mạng riêng, quyền truy cập và chi phí khi lưu lượng lớn. Nếu tác vụ chạy lâu, cần GPU, cần tiến trình liên tục hoặc cần môi trường hệ điều hành đặc biệt, container hay VM có thể phù hợp hơn.

### 6.4. Dùng dịch vụ được quản lý cho phần việc chuyên biệt

Không phải thành phần nào cũng cần tự vận hành trên VM hoặc container. Cơ sở dữ liệu, hàng đợi, object storage và nền tảng streaming được quản lý có thể cung cấp sao lưu, giám sát, nhân bản hoặc mở rộng tích hợp sẵn. Lựa chọn này giúp đội ngũ tập trung vào logic ứng dụng, nhưng cần đánh giá chi phí, giới hạn, khả năng di chuyển và yêu cầu quản trị dữ liệu.

## 7. Bảng quyết định nhanh

Bảng dưới đây đưa ra điểm xuất phát để chọn mô hình triển khai. Đây không phải quy tắc tuyệt đối; hãy kiểm tra giới hạn của nhà cung cấp và thử nghiệm với tải thực tế.

| Đặc tính workload | Điểm xuất phát thường hợp lý | Lý do |
|---|---|---|
| API stateless, chạy liên tục, tải tương đối ổn định | Container hoặc application platform | Dễ chạy nhiều replica và mở rộng theo lưu lượng |
| Webhook hoặc xử lý sự kiện ngắn, tải biến động | Serverless function | Kích hoạt theo sự kiện, giảm tài nguyên nhàn rỗi |
| Batch dài, cần checkpoint hoặc môi trường tùy chỉnh | Container job, dịch vụ batch hoặc VM | Kiểm soát thời gian chạy và tiến trình xử lý |
| Ứng dụng cũ cần hệ điều hành hoặc kernel cụ thể | VM | Giữ được môi trường thực thi cần thiết |
| Cơ sở dữ liệu cần dữ liệu bền vững | Dịch vụ cơ sở dữ liệu được quản lý hoặc VM chuyên dụng | Có thể thiết kế lưu trữ, sao lưu và phục hồi phù hợp |
| Worker streaming chạy liên tục | Container hoặc dịch vụ streaming được quản lý | Hỗ trợ tiến trình dài hạn, trạng thái và điều phối |
| Huấn luyện AI cần GPU trong thời gian dài | VM hoặc container có GPU | Kiểm soát thiết bị, thư viện và thời gian chạy |

Một quy trình lựa chọn đơn giản:

~~~mermaid
flowchart TD
    A["Mô tả workload"] --> B{"Cần tiến trình hoặc môi trường hệ điều hành đặc biệt?"}
    B -- "Có" --> C["Đánh giá VM"]
    B -- "Không" --> D{"Công việc ngắn và được kích hoạt theo sự kiện?"}
    D -- "Có" --> E["Đánh giá serverless function"]
    D -- "Không" --> F{"Cần đóng gói và điều phối dịch vụ hoặc job?"}
    F -- "Có" --> G["Đánh giá container"]
    F -- "Không" --> H["Đánh giá nền tảng hoặc dịch vụ compute được quản lý"]
    C --> I["Kiểm tra state, tài nguyên, bảo mật và chi phí"]
    E --> I
    G --> I
    H --> I
~~~

Sau khi chọn mô hình compute, vẫn cần chọn loại CPU, dung lượng RAM, lưu trữ, cấu hình mạng, vùng triển khai và quyền truy cập. Hai workload cùng chạy trong container có thể cần cấu hình tài nguyên hoàn toàn khác nhau.

## 8. Chọn và giới hạn tài nguyên

Không nên chọn cấu hình chỉ dựa trên mức sử dụng trung bình. Hãy quan sát đỉnh tải, thời gian xử lý, độ trễ và mức đồng thời. Một cấu hình vừa đủ ở tải trung bình có thể thất bại khi nhiều yêu cầu đến cùng lúc.

### 8.1. CPU và bộ nhớ

Với CPU, theo dõi mức sử dụng, thời gian chờ, số tác vụ đồng thời và độ trễ ứng dụng. Với bộ nhớ, theo dõi working set, mức sử dụng cực đại, bộ nhớ tăng theo thời gian và số lần tiến trình bị kết thúc do hết bộ nhớ.

Trong Kubernetes, trường requests biểu thị lượng tài nguyên dùng để lập lịch container; limits đặt giới hạn tài nguyên mà container có thể sử dụng. Ví dụ dưới đây minh họa một dịch vụ API có ba replica, mỗi container yêu cầu 500 millicore CPU và 512 MiB RAM:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: catalog-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: catalog-api
  template:
    metadata:
      labels:
        app: catalog-api
    spec:
      containers:
        - name: api
          image: registry.example/catalog-api:v1
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "1"
              memory: "1Gi"
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
          livenessProbe:
            httpGet:
              path: /health
              port: 8080
~~~

Đây chỉ là cấu hình minh họa, không phải định mức chung cho mọi API. Cần điều chỉnh dựa trên kiểm thử tải. Giới hạn CPU quá thấp có thể làm ứng dụng bị throttling; giới hạn bộ nhớ quá thấp có thể khiến container bị kết thúc. Ngược lại, requests quá cao có thể làm giảm khả năng xếp lịch và tăng chi phí năng lực dự phòng.

### 8.2. Lưu trữ và mạng

Với lưu trữ, xác định dung lượng, độ trễ, IOPS, thông lượng, khả năng mở rộng và thời gian lưu dữ liệu. Tách dữ liệu tạm khỏi dữ liệu cần bảo toàn. Kiểm tra cả tốc độ tăng dữ liệu và chi phí snapshot hoặc backup.

Với mạng, xác định lưu lượng vào/ra, số kết nối, độ trễ tới dịch vụ phụ thuộc, yêu cầu IP riêng, DNS, cân bằng tải và giới hạn kết nối. Nếu workload truyền nhiều dữ liệu giữa các vùng hoặc ra Internet, hãy tính cả chi phí truyền dữ liệu.

### 8.3. Bộ tăng tốc

Với GPU hoặc accelerator, ngoài số thiết bị cần xem dung lượng bộ nhớ thiết bị, khả năng tương thích framework, thời gian nạp dữ liệu và mức sử dụng thực tế. Một GPU đắt tiền nhưng thường xuyên chờ CPU chuẩn bị dữ liệu có thể bị sử dụng kém hiệu quả. Tối ưu pipeline và batch size có thể cải thiện hiệu suất trước khi tăng số GPU.

## 9. Mở rộng tải và bảo đảm tính sẵn sàng

**Mở rộng ngang** là tăng số bản sao workload; **mở rộng dọc** là tăng CPU, RAM hoặc năng lực của một máy. Mở rộng ngang thường phù hợp với workload stateless và có thể phân chia công việc. Mở rộng dọc hữu ích khi ứng dụng khó chia nhỏ hoặc cần tài nguyên lớn trên một nút, nhưng có giới hạn về kích thước máy và có thể yêu cầu khởi động lại.

Nên chọn tín hiệu mở rộng phù hợp với workload:

- API tương tác: số yêu cầu, độ trễ, số request đang xử lý hoặc CPU.
- Worker hàng đợi: độ dài hàng đợi, tuổi của thông điệp cũ nhất và tốc độ xử lý.
- Batch: số job đang chờ, thời hạn hoàn thành và năng lực xử lý mỗi worker.
- Streaming: độ trễ consumer, tốc độ đầu vào/đầu ra và số partition có thể xử lý song song.

CPU không phải lúc nào cũng là chỉ số mở rộng tốt nhất. Một worker có thể dùng ít CPU nhưng bị nghẽn do chờ I/O; khi đó tăng số worker có thể cải thiện thông lượng. Ngược lại, tăng replica vô hạn có thể làm quá tải cơ sở dữ liệu hoặc dịch vụ phụ thuộc. Cần đặt giới hạn concurrency, connection pool và backpressure.

Để tăng tính sẵn sàng, có thể chạy nhiều replica trên các miền lỗi hoặc vùng sẵn sàng khác nhau, đặt health check, dùng cân bằng tải và triển khai cập nhật theo từng phần. Ứng dụng cần dừng mềm (graceful shutdown): ngừng nhận việc mới, hoàn tất hoặc trả lại công việc đang xử lý và đóng kết nối đúng cách.

Với workload có trạng thái, nhiều replica chỉ tăng tính sẵn sàng khi dữ liệu và cơ chế chuyển đổi dự phòng được thiết kế đúng. Sao chép dữ liệu, backup và kiểm thử khôi phục là những phần thiết yếu. Cần xác định RPO (mức mất dữ liệu tối đa chấp nhận được) và RTO (thời gian khôi phục mục tiêu) cho dữ liệu quan trọng.

Khi xử lý sự kiện hoặc thông điệp, retry nên có giới hạn và thường dùng exponential backoff kèm jitter để tránh nhiều worker thử lại cùng lúc. Thông điệp lỗi lặp lại có thể được chuyển sang dead-letter queue để điều tra. Idempotency giúp hệ thống xử lý an toàn khi một thông điệp được giao nhiều lần.

## 10. Bảo mật theo đặc tính workload

Mỗi workload nên có danh tính và quyền truy cập riêng theo nguyên tắc đặc quyền tối thiểu. Một worker chỉ xử lý ảnh không cần quyền đọc toàn bộ dữ liệu thanh toán. Tách quyền theo vai trò giúp giảm tác động khi một thành phần bị xâm nhập.

Các điểm cần kiểm tra gồm:

- **Danh tính và quyền:** dùng IAM role hoặc workload identity khi nền tảng hỗ trợ; tránh chia sẻ khóa truy cập dài hạn giữa nhiều dịch vụ.
- **Bí mật:** lưu mật khẩu, token và chứng chỉ trong secret manager; không ghi bí mật vào source code, image hoặc log.
- **Mạng:** giới hạn luồng kết nối giữa các thành phần, dùng private network khi phù hợp và chỉ công khai endpoint cần thiết.
- **Dữ liệu:** mã hóa khi truyền và khi lưu; phân quyền truy cập dữ liệu theo nhu cầu của workload.
- **Image và hệ điều hành:** cập nhật bản vá, quét lỗ hổng, dùng image có nguồn gốc rõ ràng và giảm các gói không cần thiết.
- **Cô lập:** cân nhắc mức cô lập VM, container hoặc sandbox theo mức độ tin cậy và yêu cầu bảo mật của workload.

Workload chạy ngắn hạn vẫn cần bảo mật. Một function tồn tại vài giây nhưng có quyền truy cập quá rộng vẫn có thể gây rò rỉ dữ liệu. Workload dài hạn cần quy trình cập nhật và vá lỗi thường xuyên vì thời gian tồn tại lâu làm tăng nguy cơ dùng thành phần lỗi thời.

## 11. Tối ưu chi phí vận hành

Chi phí compute không chỉ là giá CPU hoặc VM. Tổng chi phí có thể gồm bộ nhớ, lưu trữ, snapshot, truyền dữ liệu, cân bằng tải, log, giám sát, license và thời gian vận hành.

Một số nguyên tắc thực tế:

1. **Đo trước khi đổi cấu hình.** Xác định bottleneck và mức sử dụng theo thời gian để tránh nâng cấp tài nguyên không cần thiết.
2. **Giảm thời gian nhàn rỗi.** Workload theo sự kiện hoặc tải thất thường có thể phù hợp với serverless hay cơ chế scale-to-zero nếu yêu cầu độ trễ cho phép.
3. **Dùng đúng kích thước.** Tránh cấp phát CPU/RAM quá lớn so với nhu cầu; đồng thời không ép cấu hình quá thấp khiến xử lý kéo dài hoặc lỗi.
4. **Tối ưu dữ liệu truyền.** Đặt các thành phần trao đổi dữ liệu thường xuyên gần nhau, nén dữ liệu khi hợp lý và hạn chế truyền dữ liệu không cần thiết.
5. **Tách workload theo nhu cầu.** Không cần giữ GPU hoặc máy cấu hình lớn trong lúc một giai đoạn khác chỉ chờ I/O.
6. **Đánh giá cam kết sử dụng và tài nguyên có thể bị gián đoạn.** Các lựa chọn giảm giá như cam kết dài hạn hoặc máy có thể thu hồi chỉ phù hợp khi mô hình tải và khả năng chịu gián đoạn cho phép.

Serverless có thể giảm chi phí khi workload ít chạy, nhưng không mặc định rẻ hơn khi tải liên tục hoặc có lưu lượng lớn. VM có thể kinh tế với tải ổn định và mức sử dụng cao. Cần so sánh chi phí trên một đơn vị công việc, chẳng hạn chi phí cho một nghìn yêu cầu hoặc một triệu bản ghi, đồng thời tính cả chi phí vận hành và yêu cầu sẵn sàng.

## 12. Ví dụ thực tế: phân loại workload của cửa hàng trực tuyến

Giả sử một cửa hàng trực tuyến có các thành phần sau:

| Thành phần | Thời gian chạy | Trạng thái | Tài nguyên nổi bật | Mô hình có thể chọn |
|---|---|---|---|---|
| API danh mục và đơn hàng | Dài hạn, tương tác | Stateless ở tầng API; dữ liệu nghiệp vụ nằm trong DB | CPU, mạng, độ trễ | Container hoặc application platform |
| Cơ sở dữ liệu đơn hàng | Dài hạn | Stateful, dữ liệu bền vững | RAM, storage I/O, mạng | Cơ sở dữ liệu được quản lý hoặc VM chuyên dụng |
| Worker xử lý ảnh sản phẩm | Tác vụ ngắn hoặc job theo hàng đợi | Có thể stateless nếu file gốc và kết quả ở object storage | CPU hoặc GPU tùy phép xử lý; I/O | Serverless function hoặc container job |
| Báo cáo doanh thu ban đêm | Batch theo lịch | Có checkpoint; kết quả cần lưu bền vững | CPU, RAM, storage I/O | Dịch vụ batch hoặc container job |
| Phân tích sự kiện người dùng | Streaming | Stateful theo cửa sổ hoặc offset | Mạng, CPU, storage | Dịch vụ streaming được quản lý hoặc container |

Từ bảng này có thể thấy một ứng dụng không nhất thiết phải chạy trên một mô hình compute duy nhất. API cần phản hồi nhanh và chạy liên tục; tác vụ xử lý ảnh chỉ cần tài nguyên khi có ảnh mới; báo cáo có thể chạy theo lịch; cơ sở dữ liệu cần lưu trữ bền vững. Tách workload giúp chọn cấu hình phù hợp cho từng thành phần và giới hạn ảnh hưởng khi một thành phần quá tải.

Ví dụ, khi có chiến dịch bán hàng, số yêu cầu API tăng đột biến. Có thể mở rộng số replica API theo lưu lượng, nhưng đồng thời phải theo dõi số kết nối và năng lực cơ sở dữ liệu. Nếu chỉ tăng API mà không kiểm soát truy vấn, database có thể trở thành bottleneck. Với worker xử lý ảnh, hàng đợi hấp thụ đỉnh tải và cho phép tăng số worker theo độ dài hàng đợi. Nhờ vậy, hệ thống kiểm soát được tốc độ xử lý mà không cần duy trì số worker tối đa cả ngày.

## 13. Quy trình phân loại một workload mới

Có thể dùng quy trình sau khi tiếp nhận một ứng dụng hoặc thành phần mới:

1. **Mô tả công việc:** ghi rõ đầu vào, đầu ra, tác nhân kích hoạt và dịch vụ phụ thuộc.
2. **Xác định thời gian chạy:** tương tác, ngắn hạn, batch, dài hạn, streaming hay theo lịch; ghi lại thời gian thực thi và yêu cầu khởi động.
3. **Xác định trạng thái:** phân loại dữ liệu tạm, dữ liệu phiên, dữ liệu nghiệp vụ và checkpoint; xác định yêu cầu bền vững, backup và phục hồi.
4. **Đo nhu cầu tài nguyên:** kiểm thử CPU, RAM, I/O, mạng và GPU; ghi nhận mức trung bình, đỉnh và bottleneck.
5. **Mô tả hình dạng tải và SLO:** số yêu cầu, concurrency, thông lượng, độ trễ, thời gian hoàn thành và mức sẵn sàng cần đạt.
6. **Chọn mô hình compute:** so sánh VM, container, serverless và dịch vụ được quản lý theo yêu cầu thực tế.
7. **Kiểm thử và tính chi phí:** chạy thử với tải đại diện, kiểm tra lỗi và phục hồi, sau đó so sánh chi phí trên một đơn vị công việc.

Kết quả phân loại nên được ghi thành một hồ sơ ngắn cho từng workload. Hồ sơ này giúp nhóm phát triển, vận hành và bảo mật thống nhất về cấu hình, quyền truy cập, cách mở rộng và tiêu chí đánh giá.

## 14. Những sai lầm thường gặp

- **Chọn compute trước khi hiểu workload:** dẫn đến cấp phát tài nguyên dư thừa hoặc thiếu hụt.
- **Coi container là nơi lưu dữ liệu bền vững:** dữ liệu trong filesystem của container có thể mất khi container bị thay thế.
- **Cho rằng stateless nghĩa là không có trạng thái:** trạng thái có thể nằm ở DB, cache hoặc dịch vụ bên ngoài và vẫn cần thiết kế độ bền.
- **Chỉ theo dõi CPU:** bỏ qua giới hạn RAM, I/O, mạng, hàng đợi hoặc dịch vụ phụ thuộc.
- **Dùng retry không giới hạn:** có thể làm quá tải hệ thống khi lỗi kéo dài và tạo xử lý trùng lặp.
- **Tăng replica mà không kiểm tra bottleneck:** có thể chuyển điểm nghẽn sang database, queue hoặc API phụ thuộc.
- **Chọn serverless chỉ vì tải không đều:** cần kiểm tra giới hạn thực thi, cold start, concurrency và chi phí khi tải tăng.
- **Bỏ qua chi phí dữ liệu và vận hành:** compute rẻ nhưng truyền dữ liệu, lưu trữ hoặc giám sát có thể làm tổng chi phí cao.

## 15. Ghi nhớ

Phân loại workload là bước nền tảng để thiết kế hạ tầng cloud compute. Hãy nhìn workload trên nhiều trục: thời gian chạy cho biết cách khởi chạy và kết thúc; trạng thái cho biết dữ liệu cần được lưu giữ và phục hồi như thế nào; nhu cầu tài nguyên cho biết cấu hình CPU, RAM, lưu trữ, mạng hoặc GPU. Hình dạng tải, SLO, bảo mật và chi phí hoàn thiện quyết định lựa chọn cuối cùng.

Khi hiểu rõ các đặc tính đó, có thể ghép từng thành phần với VM, container, serverless hoặc dịch vụ được quản lý; thiết kế mở rộng và tính sẵn sàng phù hợp; đồng thời tránh trả chi phí cho tài nguyên không cần thiết.
