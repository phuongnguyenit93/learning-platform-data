# Ghi nhận bằng chứng trước và sau cùng điều kiện hoàn tác

Tối ưu hiệu năng cơ sở dữ liệu chỉ có thể được đánh giá đáng tin cậy khi nhóm vận hành ghi nhận được trạng thái trước thay đổi, trạng thái sau thay đổi và điều kiện thử nghiệm tương ứng. Một truy vấn chạy nhanh hơn trong một lần thử chưa đủ chứng minh hệ thống đã được cải thiện: tải có thể đã giảm, bộ nhớ đệm có thể đã nóng lên, dữ liệu kiểm thử có thể khác hoặc một tác vụ nền có thể đã kết thúc. Vì vậy, mỗi lần điều chỉnh cần đi kèm kế hoạch đo, bằng chứng có thể đối chiếu và điều kiện hoàn tác đã được xác định trước.

Nội dung thuộc chương **Phương pháp đo** của module DATABASE_PERFORMANCE. Module rèn phương pháp tối ưu hiệu năng dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; do đó, bằng chứng trước/sau cần phản ánh cả thời gian đáp ứng, thông lượng, tài nguyên, truy vấn và tính đúng đắn của giao dịch. Mục tiêu là giúp nhóm đưa ra quyết định dựa trên dữ liệu, kiểm soát rủi ro và biết rõ khi nào cần dừng hoặc hoàn nguyên một thay đổi.

## 1. Vì sao phải ghi nhận bằng chứng trước và sau?

Một thay đổi hiệu năng có thể tác động đến nhiều phần của hệ thống. Tạo chỉ mục có thể giảm số trang phải đọc cho một truy vấn nhưng làm tăng chi phí ghi và dung lượng lưu trữ. Viết lại SQL có thể giảm thời gian thực thi ở một nhóm tham số nhưng khiến nhóm tham số khác chậm hơn. Rút ngắn giao dịch có thể giảm thời gian giữ khóa, nhưng thay đổi ranh giới giao dịch sai cách có thể làm mất tính nguyên tử của nghiệp vụ.

Ghi nhận bằng chứng trước và sau giúp trả lời những câu hỏi quan trọng:

- Hệ thống ban đầu hoạt động như thế nào trong workload và mức tải đã xác định?
- Thay đổi nào đã được thực hiện, vào thời điểm nào, trên phiên bản ứng dụng hoặc cấu hình nào?
- Các chỉ số mục tiêu đã cải thiện bao nhiêu và kết quả có lặp lại được không?
- Chỉ số phụ như CPU, bộ nhớ, I/O, dung lượng, độ trễ ghi, lock wait hoặc tỷ lệ lỗi có xấu đi không?
- Kết quả dữ liệu và hành vi nghiệp vụ có còn chính xác không?
- Điều kiện nào yêu cầu dừng triển khai hoặc hoàn tác, và nhóm có thể thực hiện việc đó trong thời gian cho phép không?

Không có bằng chứng ban đầu thì không thể phân biệt cải thiện thực sự với dao động tự nhiên. Không có bằng chứng sau thay đổi thì không thể chứng minh hiệu quả hoặc phát hiện tác động phụ. Không có điều kiện hoàn tác thì nhóm có thể tiếp tục triển khai trong khi các chỉ số đang xấu đi.

## 2. Xây dựng đường cơ sở trước thay đổi

Đường cơ sở (baseline) là tập số liệu mô tả trạng thái hệ thống trước khi áp dụng điều chỉnh. Baseline cần gắn với một workload, một khoảng thời gian, một phiên bản ứng dụng và một cấu hình cụ thể. Không nên dùng một con số đơn lẻ như thời gian trung bình của một truy vấn làm đại diện cho toàn bộ hiệu năng.

### Xác định phạm vi đo

Trước khi thu thập, hãy mô tả rõ:

- Cơ sở dữ liệu, instance hoặc cụm được quan sát.
- Dịch vụ, endpoint, giao dịch hoặc fingerprint truy vấn liên quan.
- Môi trường đo: kiểm thử, staging, canary hay production.
- Khoảng thời gian và múi giờ dùng trong log, dashboard và báo cáo.
- Khối lượng dữ liệu, phân bố dữ liệu và trạng thái cache nếu biết.
- Mức tải, số phiên đồng thời, tốc độ yêu cầu và tỷ lệ đọc/ghi.
- Phiên bản ứng dụng, schema, chỉ mục và cấu hình cơ sở dữ liệu.

Phạm vi càng rõ thì càng dễ lặp lại phép đo. Ví dụ, ghi “truy vấn đơn hàng chậm” không đủ để tái hiện; nên ghi fingerprint, database, endpoint gọi truy vấn, khoảng thời gian, số lần thực thi và loại tham số đã được phân nhóm an toàn.

### Chọn chỉ số phản ánh mục tiêu

Các chỉ số cần theo dõi phụ thuộc vào thay đổi và mục tiêu dịch vụ. Một bộ chỉ số cơ bản có thể gồm:

| Nhóm | Chỉ số thường dùng | Ý nghĩa |
| --- | --- | --- |
| Trải nghiệm | p50, p95, p99, timeout, tỷ lệ lỗi | Thời gian người dùng chờ và mức ổn định |
| Khối lượng | QPS/TPS, số yêu cầu, số giao dịch, số lần gọi truy vấn | Workload đã tạo ra trong thời gian đo |
| Truy vấn | Tổng thời gian, thời gian mỗi lần, số dòng đọc/trả về, logical reads | Chi phí và lượng công việc của truy vấn |
| Kế hoạch | Plan ID, loại toán tử, số dòng ước lượng/thực tế nếu có | Phát hiện thay đổi kế hoạch hoặc ước lượng sai |
| Tài nguyên | CPU, bộ nhớ, cache hit, IOPS, độ trễ đọc/ghi | Nhận diện tài nguyên đang chịu áp lực |
| Đồng thời | Số phiên hoạt động, lock wait, deadlock, thời gian giữ giao dịch | Phát hiện tranh chấp |
| Dung lượng | Kích thước bảng/chỉ mục, dữ liệu tạm, log phát sinh | Theo dõi chi phí lưu trữ và vận hành |

Không phải mọi bài tối ưu đều cần mọi chỉ số. Khi thay đổi chỉ mục, cần chú ý cả truy vấn đọc, tốc độ ghi, dung lượng chỉ mục và I/O. Khi rút ngắn giao dịch, cần đo thời gian giữ khóa, deadlock, độ trễ giao dịch và tính đúng đắn nghiệp vụ. Khi điều chỉnh connection pool, cần theo dõi thời gian chờ pool, số kết nối hoạt động, tải cơ sở dữ liệu và tỷ lệ timeout.

### Thu thập đủ lâu và đủ đại diện

Khoảng đo phải bao phủ workload có liên quan. Với hệ thống có chu kỳ theo giờ hoặc theo ngày, đo trong một khoảng quá ngắn có thể bỏ lỡ đỉnh tải hoặc tác vụ định kỳ. Nên xác định thời lượng dựa trên chu kỳ nghiệp vụ, số lượng mẫu cần thiết và khả năng tái tạo tải.

Phân vị độ trễ cần đủ mẫu để có ý nghĩa. Nếu chỉ có vài yêu cầu, p99 có thể gần như trùng với giá trị lớn nhất và không ổn định. Hãy ghi số lượng mẫu cùng phân vị, không chỉ ghi p95 hoặc p99. Nếu nguồn chỉ cung cấp tổng thời gian và số lần thực thi, có thể tính trung bình nhưng không thể suy ra phân vị chính xác từ hai số đó.

## 3. Ghi lại điều kiện thử nghiệm

Hai phép đo chỉ có thể so sánh khi các điều kiện quan trọng tương đương hoặc khác biệt đã được ghi nhận và giải thích. Đây là phần thường bị bỏ qua khi báo cáo chỉ nêu “trước: 800 ms, sau: 300 ms”.

### Các biến cần kiểm soát

| Điều kiện | Cách ghi nhận hoặc kiểm soát |
| --- | --- |
| Dữ liệu | Kích thước bảng, số dòng, phân bố giá trị, tỷ lệ bản ghi nóng và dữ liệu mới |
| Workload | Tập truy vấn, tỷ lệ đọc/ghi, tần suất, kích thước kết quả và thứ tự thao tác |
| Đồng thời | Số client, số worker, tốc độ yêu cầu và giới hạn kết nối |
| Cache | Cache nóng/lạnh, thời điểm khởi động hoặc làm mới cache nếu có |
| Phần mềm | Phiên bản ứng dụng, driver, ORM, hệ quản trị và bản vá |
| Cấu hình | Bộ nhớ, connection pool, timeout, tham số cơ sở dữ liệu và cấu hình lưu trữ |
| Hạ tầng | CPU, bộ nhớ, loại lưu trữ, vị trí mạng và các tải nền |
| Đo lường | Công cụ, phiên bản, sampling, khoảng lấy mẫu và cách tính số liệu |

Không phải lúc nào cũng có thể giữ mọi biến hoàn toàn giống nhau. Nếu dữ liệu tăng giữa hai lần đo, hãy ghi nhận mức tăng và dùng workload hoặc tập dữ liệu đại diện để so sánh. Nếu không thể tái tạo chính xác điều kiện, cần nêu rõ giới hạn và tránh kết luận quá mức.

### Kiểm soát cache và thứ tự chạy

Cache có thể làm kết quả thay đổi đáng kể. Lần chạy đầu tiên có thể phải đọc dữ liệu từ lưu trữ; các lần tiếp theo có thể lấy dữ liệu từ bộ nhớ đệm. Nếu chỉ đo lần đầu trước thay đổi và lần chạy thứ năm sau thay đổi, kết quả sẽ không công bằng.

Có thể chọn một trong hai cách tiếp cận phù hợp:

- **Đo trạng thái cache nóng:** chạy warm-up theo quy trình cố định, sau đó lấy mẫu trong cùng điều kiện. Cách này phù hợp nếu workload thực tế thường truy cập dữ liệu đã nằm trong cache.
- **Đo trạng thái cache lạnh:** sử dụng môi trường kiểm thử và quy trình làm sạch hoặc khởi tạo cache có kiểm soát nếu hệ quản trị cho phép. Không tùy tiện xóa cache trên production vì có thể gây tăng I/O và làm suy giảm dịch vụ.

Nếu mục tiêu là đánh giá cả hai trạng thái, hãy tách kết quả thành hai bộ số liệu. Lặp lại nhiều lượt và có thể đổi thứ tự chạy các phương án để giảm ảnh hưởng của xu hướng tải theo thời gian. Ghi rõ warm-up, thời gian chờ ổn định và số lần lặp.

### Giữ workload và mức tải tương đương

Dùng cùng một tập truy vấn hoặc kịch bản tạo tải, cùng tỷ lệ đọc/ghi và cùng cách phân phối tham số. Một bài kiểm thử chỉ chạy truy vấn phổ biến có thể không phản ánh các tham số hiếm gây quét nhiều dòng. Cần bao gồm các nhóm tham số đại diện, đồng thời tránh lưu dữ liệu nhạy cảm trong kịch bản.

Tốc độ yêu cầu cần đủ để tái tạo mức tải mục tiêu nhưng không vượt quá giới hạn an toàn của môi trường. Ghi lại số client, tốc độ yêu cầu, thời gian ramp-up, thời gian giữ tải ổn định và thời gian giảm tải. Nếu công cụ tạo tải không giữ được tốc độ dự kiến do chính client bị bão hòa, kết quả thông lượng không đại diện cho năng lực cơ sở dữ liệu.

## 4. Lập kế hoạch bằng chứng cho từng thay đổi

Trước khi thực hiện điều chỉnh, hãy viết rõ giả thuyết và cách chứng minh. Một kế hoạch đo tốt kết nối thay đổi với chỉ số dự kiến cải thiện và các chỉ số có nguy cơ xấu đi.

Ví dụ:

| Thành phần | Nội dung |
| --- | --- |
| Vấn đề | Truy vấn lấy đơn hàng đọc nhiều dòng và p95 tăng khi bảng lớn |
| Giả thuyết | Chỉ mục phù hợp với điều kiện lọc và thứ tự sắp xếp sẽ giảm lượng đọc |
| Thay đổi | Tạo chỉ mục kết hợp trên môi trường thử nghiệm |
| Chỉ số chính | p95 truy vấn, logical reads, tổng thời gian của fingerprint |
| Chỉ số bảo vệ | p95 thao tác ghi, CPU, I/O, dung lượng chỉ mục, tỷ lệ lỗi |
| Điều kiện so sánh | Cùng dữ liệu, workload, mức đồng thời, trạng thái cache |
| Tiêu chí đạt | Chỉ số chính cải thiện theo mục tiêu đã đặt và các chỉ số bảo vệ nằm trong giới hạn |
| Điều kiện dừng/hoàn tác | Độ trễ hoặc lỗi vượt ngưỡng, thao tác ghi suy giảm đáng kể, dữ liệu sai hoặc tài nguyên mất ổn định |

Giả thuyết nên có thể bị bác bỏ. Nếu dự đoán chỉ mục giảm logical reads nhưng số đọc không thay đổi, có thể truy vấn không sử dụng chỉ mục hoặc nút thắt nằm ở nơi khác. Nếu p95 giảm nhưng I/O ghi tăng vượt ngưỡng, thay đổi có thể không phù hợp với workload tổng thể.

### Chụp bằng chứng trước thay đổi

Trước khi thay đổi, lưu lại:

1. Snapshot dashboard hoặc dữ liệu metric gốc trong khoảng đo.
2. Kết quả thống kê fingerprint và số lần thực thi.
3. Kế hoạch thực thi, Plan ID và số dòng ước lượng/thực tế nếu công cụ hỗ trợ.
4. Trạng thái schema, chỉ mục và cấu hình có liên quan.
5. Kịch bản tải, dữ liệu kiểm thử và tham số đã phân loại.
6. Phiên bản ứng dụng, migration hoặc commit sẽ được triển khai.
7. Thời điểm bắt đầu/kết thúc đo và người hoặc hệ thống thực hiện thay đổi.

Lưu bằng chứng ở nơi có quyền truy cập phù hợp, có tên và thời điểm rõ ràng. Không đưa mật khẩu, token hoặc giá trị tham số nhạy cảm vào ảnh chụp, log hay báo cáo.

## 5. Đo sau thay đổi và đối chiếu kết quả

Sau khi thay đổi, hãy chạy lại đúng kịch bản đo đã xác định. Giữ cùng thời gian warm-up, số lần lặp, thời lượng giữ tải, số client và cách tổng hợp số liệu. Ghi lại phiên bản, cấu hình và thời điểm mới để người khác có thể tái hiện.

### So sánh cùng chỉ số và cùng phạm vi

Một bảng đối chiếu nên có giá trị trước, giá trị sau, mức thay đổi, số mẫu và điều kiện đo:

| Chỉ số | Trước | Sau | Diễn giải |
| --- | ---: | ---: | --- |
| p95 truy vấn mục tiêu | 420 ms | 180 ms | Giảm 57% trong kịch bản minh họa |
| Số dòng đọc trung bình | 8.000 | 900 | Giảm lượng dữ liệu phải đọc |
| QPS ở mức tải thử | 500 | 500 | Mức tải đầu vào tương đương |
| p95 thao tác ghi | 35 ms | 42 ms | Cần xem xét chi phí ghi tăng |
| CPU trung bình | 62% | 66% | Tăng nhẹ, cần đối chiếu với giới hạn |
| Tỷ lệ lỗi | 0,1% | 0,1% | Không thay đổi trong mẫu đo |

Các con số trên chỉ là ví dụ, không phải kết quả thực tế hay ngưỡng áp dụng chung. Một báo cáo tốt cần ghi thêm số lượng mẫu, khoảng đo, mức đồng thời, trạng thái cache và nguồn số liệu. Nếu p95 giảm nhưng QPS đầu vào cũng giảm, chưa thể kết luận thay đổi đã cải thiện hiệu năng.

Có thể tính mức thay đổi tương đối của một chỉ số:

\[
\text{Mức thay đổi (\%)} =
\frac{\text{Giá trị sau} - \text{Giá trị trước}}
{\text{Giá trị trước}} \times 100
\]

Với chỉ số mà giá trị thấp hơn là tốt hơn, kết quả âm thể hiện mức giảm. Với chỉ số mà giá trị cao hơn là tốt hơn, chẳng hạn thông lượng trong một điều kiện tải cố định, cách diễn giải sẽ khác. Luôn ghi rõ chiều tốt/xấu của chỉ số và tránh chỉ trình bày phần trăm mà không nêu giá trị gốc.

### Xem xét cả hiệu năng và tính đúng đắn

Hiệu năng tốt hơn không có ý nghĩa nếu kết quả nghiệp vụ bị sai. Sau mỗi thay đổi, cần xác nhận:

- Số lượng và nội dung bản ghi trả về đúng với điều kiện truy vấn.
- Thứ tự kết quả và quy tắc phân trang vẫn được bảo toàn.
- INSERT, UPDATE, DELETE và các ràng buộc dữ liệu vẫn hoạt động đúng.
- Giao dịch giữ nguyên tính nguyên tử và nhất quán theo yêu cầu nghiệp vụ.
- Không xuất hiện bản ghi thiếu, trùng, cập nhật một phần hoặc mất đồng bộ giữa các bảng.
- Các luồng đọc/ghi khác dùng chung bảng hoặc chỉ mục không bị suy giảm ngoài giới hạn.

Đối với thay đổi schema hoặc dữ liệu, cần chạy kiểm tra tính toàn vẹn và đối chiếu số lượng hoặc checksum theo cách phù hợp. Một truy vấn benchmark nhanh hơn không thay thế được kiểm thử chức năng và xác nhận dữ liệu.

### Đánh giá độ ổn định của kết quả

Một lần chạy tốt có thể là ngẫu nhiên. Hãy lặp lại phép đo, quan sát dao động và so sánh các khoảng thời gian tương đương. Khi có đủ dữ liệu, dùng phân bố hoặc khoảng tin cậy thay vì chỉ so sánh một giá trị trung bình. Nếu tải nền hoặc hạ tầng thay đổi trong lúc đo, đánh dấu mẫu bị ảnh hưởng và thực hiện lại khi điều kiện ổn định.

Nếu có thể, dùng nhóm đối chứng hoặc canary để so sánh phiên bản cũ và mới dưới cùng thời điểm và workload. Với production, chia tỷ lệ lưu lượng tăng dần giúp phát hiện vấn đề trước khi mở rộng. Cần đảm bảo nhóm đối chứng và nhóm canary nhận workload tương đương; nếu phân phối yêu cầu khác nhau, so sánh trực tiếp có thể sai lệch.

## 6. Đặt điều kiện hoàn tác trước khi triển khai

Hoàn tác (rollback) là hành động đưa hệ thống về trạng thái hoạt động an toàn trước thay đổi hoặc chuyển sang một trạng thái đã được chuẩn bị để khôi phục dịch vụ. Điều kiện hoàn tác cần được định nghĩa trước khi triển khai, có thể đo được và gắn với người chịu trách nhiệm ra quyết định.

Không nên đợi đến khi sự cố xảy ra mới thảo luận ngưỡng hoàn tác. Khi hệ thống đang suy giảm, việc xác định ai quyết định, thao tác nào được thực hiện và bằng chứng nào cần lưu sẽ mất thêm thời gian.

### Phân loại điều kiện hoàn tác

Có thể chia điều kiện thành các nhóm:

- **Hiệu năng:** p95/p99 vượt ngưỡng đã thống nhất trong nhiều cửa sổ đo liên tiếp; thông lượng giảm tại cùng mức tải; thời gian truy vấn hoặc thời gian chờ tăng đáng kể.
- **Độ tin cậy:** tỷ lệ lỗi, timeout, deadlock hoặc retry vượt giới hạn.
- **Tài nguyên:** CPU, bộ nhớ, I/O, dung lượng log hoặc hàng đợi vượt ngưỡng vận hành an toàn.
- **Tính đúng đắn:** kết quả truy vấn sai, vi phạm ràng buộc, mất dữ liệu, dữ liệu trùng hoặc trạng thái giao dịch không nhất quán.
- **Ảnh hưởng chéo:** endpoint hoặc workload quan trọng khác suy giảm do thay đổi mới.
- **Khả năng vận hành:** thời gian triển khai vượt giới hạn, migration không hoàn tất hoặc không thể quan sát được chỉ số cần thiết.

Các ngưỡng phải dựa trên SLA/SLO, đường cơ sở và khả năng chịu tải của hệ thống. Không có một con số p95, CPU hay I/O chung áp dụng cho mọi cơ sở dữ liệu. Cần chỉ rõ cửa sổ đo, số mẫu tối thiểu, thời gian duy trì ngưỡng và mức nghiêm trọng.

### Ví dụ về tiêu chí dừng

Một kế hoạch triển khai có thể đặt các điều kiện minh họa như sau:

| Điều kiện | Hành động |
| --- | --- |
| p95 endpoint tăng hơn 30% so với baseline trong 3 cửa sổ 5 phút liên tiếp, với mức tải tương đương | Dừng mở rộng canary và điều tra |
| Tỷ lệ lỗi vượt SLO hoặc xuất hiện lỗi dữ liệu | Dừng ngay, kích hoạt quy trình xử lý sự cố |
| p95 thao tác ghi vượt giới hạn bảo vệ trong thời gian duy trì đã định | Đánh giá hoàn tác thay đổi chỉ mục hoặc cấu hình |
| CPU/I/O duy trì trên ngưỡng an toàn và hàng đợi tiếp tục tăng | Dừng rollout, giảm tải hoặc hoàn tác theo runbook |
| Kết quả dữ liệu không nhất quán | Ngừng triển khai, bảo toàn bằng chứng và thực hiện quy trình phục hồi dữ liệu |

Các ngưỡng 30%, 3 cửa sổ và 5 phút chỉ minh họa cách diễn đạt một điều kiện có thể đo. Nhóm phải chọn con số phù hợp với hệ thống và thỏa thuận vận hành thực tế. Điều kiện liên quan đến sai lệch dữ liệu cần được xem là nghiêm trọng, không chờ đủ nhiều cửa sổ đo.

## 7. Thiết kế phương án hoàn tác theo loại thay đổi

Hoàn tác không phải lúc nào cũng là chạy một lệnh ngược lại. Một số thay đổi có thể đảo ngược nhanh, trong khi thay đổi cấu trúc hoặc dữ liệu có thể không thể khôi phục chỉ bằng một thao tác.

| Loại thay đổi | Phương án cần chuẩn bị | Điểm cần kiểm tra |
| --- | --- | --- |
| Cấu hình cơ sở dữ liệu | Lưu giá trị cũ, phạm vi áp dụng và lệnh khôi phục | Thời gian hiệu lực, yêu cầu restart, tác động kết nối |
| SQL hoặc ứng dụng | Giữ phiên bản triển khai trước, feature flag hoặc cách chuyển traffic về phiên bản cũ | Tương thích schema và trạng thái request đang chạy |
| Tạo chỉ mục | Chuẩn bị thao tác gỡ chỉ mục theo khả năng của hệ quản trị và cửa sổ vận hành | Ảnh hưởng trong lúc gỡ, lock, dung lượng và thời gian thực hiện |
| Thay đổi schema | Migration tiến và migration lùi đã được kiểm tra, hoặc kế hoạch khôi phục tương thích | Dữ liệu mới có thể không tương thích với schema cũ |
| Chuyển đổi dữ liệu | Snapshot/backup, đối soát, nhật ký chuyển đổi và quy trình phục hồi | Có thể cần khôi phục từ bản sao lưu hoặc chạy bù dữ liệu |
| Thay đổi pool hoặc concurrency | Lưu cấu hình cũ và giới hạn an toàn để trả lại | Tình trạng kết nối đang mở và tải hiện thời |

Trước khi chạy migration, cần xác định khả năng tương thích giữa phiên bản ứng dụng cũ và schema mới. Một số chiến lược triển khai dùng mô hình mở rộng rồi thu hẹp (expand/contract): bổ sung cấu trúc tương thích trước, triển khai ứng dụng, chuyển dữ liệu, sau đó mới xóa cấu trúc cũ khi đã xác nhận an toàn. Với dữ liệu đã biến đổi hoặc bị xóa, rollback schema đơn thuần không thể tái tạo dữ liệu ban đầu.

### Kiểm tra khả năng hoàn tác trước khi cần dùng

Trong môi trường thử nghiệm, hãy thực hiện diễn tập:

1. Ghi nhận trạng thái ban đầu và xác nhận bản sao lưu hoặc điểm khôi phục có thể sử dụng.
2. Áp dụng thay đổi theo đúng runbook.
3. Kích hoạt điều kiện giả lập để dừng rollout.
4. Thực hiện phương án hoàn tác.
5. Kiểm tra schema, dữ liệu, kết nối, ứng dụng và các giao dịch đang hoạt động.
6. Đo lại các chỉ số quan trọng để xác nhận hệ thống đã trở về trạng thái an toàn.
7. Ghi thời gian thực hiện, bước thất bại và điều chỉnh runbook.

Một phương án hoàn tác chưa từng được thử có thể thất bại do quyền thiếu, lệnh không tương thích phiên bản, lock kéo dài, backup không khôi phục được hoặc ứng dụng cũ không đọc được dữ liệu mới.

## 8. Thứ tự triển khai và điểm kiểm tra

Đối với thay đổi có rủi ro, có thể triển khai theo từng giai đoạn:

1. **Chuẩn bị:** hoàn thiện baseline, kế hoạch đo, tiêu chí đạt, ngưỡng dừng và runbook hoàn tác.
2. **Thử nghiệm:** kiểm tra trên môi trường có dữ liệu và workload đại diện; xác minh tính đúng đắn và khả năng hoàn tác.
3. **Canary:** áp dụng cho phạm vi nhỏ hoặc một phần lưu lượng có thể kiểm soát.
4. **Quan sát:** so sánh chỉ số canary với baseline hoặc nhóm đối chứng trong các cửa sổ đo đã định.
5. **Mở rộng:** chỉ tăng tỷ lệ khi tiêu chí hiệu năng, độ tin cậy và tính đúng đắn đều đạt.
6. **Kết thúc:** ghi lại bằng chứng sau cùng, cấu hình mới, kết quả và quyết định triển khai.

Ở mỗi giai đoạn cần có điểm dừng rõ ràng. Nếu không có đủ số liệu để đánh giá, không nên tự xem việc không thấy lỗi là bằng chứng thành công. Hãy bổ sung quan sát hoặc giữ nguyên phạm vi triển khai cho đến khi có thể đưa ra quyết định.

### Sơ đồ quyết định tổng quát

~~~mermaid
flowchart TD
    A[Chụp baseline và điều kiện đo] --> B[Áp dụng thay đổi trong phạm vi nhỏ]
    B --> C[Thu thập chỉ số và kiểm tra dữ liệu]
    C --> D{Các tiêu chí đều đạt?}
    D -->|Có| E[Mở rộng theo từng giai đoạn]
    D -->|Không| F[Dừng rollout]
    F --> G{Có điều kiện hoàn tác?}
    G -->|Có| H[Thực hiện runbook hoàn tác]
    G -->|Không| I[Kích hoạt phương án phục hồi đã chuẩn bị]
    H --> J[Kiểm tra trạng thái và ghi bằng chứng]
    I --> J
    E --> K[Đo sau cùng và lưu báo cáo]
~~~

Sơ đồ mô tả luồng quyết định chung. Trong thực tế, một lỗi dữ liệu hoặc nguy cơ mất an toàn có thể yêu cầu dừng ngay mà không chờ hết cửa sổ đo hiệu năng.

## 9. Mẫu hồ sơ bằng chứng trước/sau

Mỗi thay đổi nên có một hồ sơ ngắn gọn, đủ để người khác hiểu và lặp lại phép đo. Có thể sử dụng cấu trúc sau:

~~~text
Mã thay đổi:
Mục tiêu nghiệp vụ:
Vấn đề hiệu năng:
Fingerprint / endpoint liên quan:
Giả thuyết tối ưu:

Môi trường và database:
Phiên bản ứng dụng / schema:
Thay đổi dự kiến:
Thời điểm đo và múi giờ:
Workload / mức đồng thời:
Kích thước và phân bố dữ liệu:
Trạng thái cache:
Nguồn metric / công cụ:

BASELINE
- Số mẫu:
- p50 / p95 / p99:
- QPS / TPS:
- Tổng thời gian truy vấn:
- CPU / bộ nhớ / I/O:
- Lock wait / timeout / lỗi:
- Kế hoạch thực thi / Plan ID:

AFTER
- Số mẫu:
- p50 / p95 / p99:
- QPS / TPS:
- Tổng thời gian truy vấn:
- CPU / bộ nhớ / I/O:
- Lock wait / timeout / lỗi:
- Kế hoạch thực thi / Plan ID:
- Kiểm tra tính đúng đắn:

ĐIỀU KIỆN ĐẠT:
ĐIỀU KIỆN DỪNG / HOÀN TÁC:
RUNBOOK HOÀN TÁC:
Kết quả diễn tập hoàn tác:
Quyết định:
Người xác nhận:
Liên kết dashboard / log / báo cáo:
~~~

Hồ sơ có thể lưu trong hệ thống quản lý thay đổi hoặc kho tài liệu vận hành. Dữ liệu gốc nên được giữ theo chính sách lưu trữ và quyền truy cập. Khi chia sẻ ảnh chụp hoặc log, cần loại bỏ thông tin xác thực và dữ liệu nhạy cảm.

## 10. Ví dụ thực hành: đánh giá một thay đổi chỉ mục

Một API tra cứu lịch sử đơn hàng có p95 tăng trong giờ cao điểm. Thống kê cho thấy fingerprint truy vấn theo khách hàng và trạng thái đọc nhiều dòng. Nhóm phát triển giả thuyết rằng chỉ mục kết hợp phù hợp có thể giảm số dòng phải đọc.

### Trước thay đổi

Nhóm ghi nhận trong môi trường thử nghiệm:

- Phiên bản ứng dụng và schema hiện tại.
- Số dòng của bảng đơn hàng và phân bố trạng thái.
- Cùng một bộ truy vấn với nhóm khách hàng có ít, trung bình và nhiều đơn hàng.
- Cùng số client và tốc độ yêu cầu.
- Cache được làm nóng theo cùng quy trình trước khi đo.
- p50/p95/p99, QPS, logical reads, CPU, I/O và thời gian ghi.
- Kế hoạch thực thi hiện tại cùng số dòng ước lượng và thực tế nếu có.

Kết quả giả lập cho thấy p95 truy vấn là 420 ms, logical reads trung bình là 8.000 trang hoặc đơn vị đọc tương ứng của công cụ. Nhóm cũng lưu p95 của thao tác ghi để theo dõi chi phí phát sinh sau khi thêm chỉ mục.

### Thử nghiệm và đo sau

Nhóm tạo chỉ mục trên môi trường thử nghiệm, cập nhật hoặc chờ thống kê theo cơ chế của hệ quản trị, sau đó kiểm tra kế hoạch mới. Cùng workload được chạy lại với cùng thời gian warm-up, số client và thời lượng đo.

Kết quả minh họa cho thấy p95 giảm còn 180 ms, lượng đọc giảm, nhưng p95 thao tác ghi tăng từ 35 ms lên 42 ms và dung lượng lưu trữ tăng. Nhóm kiểm tra thêm tỷ lệ lỗi, CPU, I/O, kế hoạch và kết quả dữ liệu. Nếu các chỉ số bảo vệ vẫn nằm trong giới hạn đã thống nhất, thay đổi có thể được đưa vào canary.

### Điều kiện hoàn tác

Trước khi canary, nhóm chuẩn bị:

- Ngưỡng p95 API, p95 thao tác ghi và tỷ lệ lỗi cần dừng.
- Dashboard theo dõi cả truy vấn mục tiêu và các thao tác ghi trên bảng đơn hàng.
- Phương án dừng rollout và trả ứng dụng về phiên bản trước nếu có liên quan.
- Runbook gỡ chỉ mục phù hợp với hệ quản trị, bao gồm đánh giá lock và thời gian thực hiện.
- Bằng chứng schema, chỉ mục và số liệu trước thay đổi để đối chiếu.

Nếu p95 thao tác ghi vượt ngưỡng bảo vệ hoặc lỗi tăng trong canary, nhóm dừng mở rộng và đánh giá hoàn tác. Nếu phát hiện kết quả dữ liệu sai, cần kích hoạt quy trình xử lý dữ liệu và bảo toàn bằng chứng; không chỉ gỡ chỉ mục rồi xem sự cố đã được giải quyết.

Ví dụ này cho thấy một thay đổi chỉ được xem là đạt khi chỉ số mục tiêu cải thiện, các chỉ số bảo vệ không vượt giới hạn và tính đúng đắn vẫn được giữ nguyên.

## 11. Những sai lầm thường gặp

- **Không lưu baseline:** sau thay đổi không có dữ liệu gốc để so sánh.
- **So sánh hai workload khác nhau:** số lượng yêu cầu, tham số, dữ liệu hoặc mức đồng thời không tương đương.
- **Bỏ qua trạng thái cache:** lần đo sau được hưởng lợi từ cache nóng nhưng bị hiểu nhầm là tối ưu.
- **Chỉ đo truy vấn mục tiêu:** bỏ qua tác động đến thao tác ghi, giao dịch khác và các dịch vụ dùng chung.
- **Chỉ nhìn trung bình:** p95/p99 hoặc tỷ lệ lỗi có thể xấu đi dù trung bình giảm.
- **Không xác nhận dữ liệu:** truy vấn nhanh nhưng kết quả hoặc trạng thái giao dịch sai.
- **Không định nghĩa ngưỡng dừng:** nhóm tranh luận về mức độ nghiêm trọng khi sự cố đang diễn ra.
- **Rollback chưa được diễn tập:** phương án khôi phục tồn tại trên giấy nhưng không thực hiện được trong thời gian cần thiết.
- **Cho rằng mọi thay đổi đều đảo ngược dễ dàng:** migration dữ liệu hoặc thao tác phá hủy có thể cần phục hồi từ backup hoặc quy trình bù.
- **Không lưu phiên bản và thời điểm:** không thể liên hệ kết quả với thay đổi cụ thể.

Để tránh các lỗi này, hãy coi việc đo, ghi bằng chứng và chuẩn bị hoàn tác là một phần của cùng quy trình thay đổi. Không tách chúng thành công việc tùy chọn sau khi tối ưu đã hoàn tất.

## 12. Nguyên tắc cần ghi nhớ

- Thiết lập baseline trước khi thay đổi và ghi rõ workload, dữ liệu, phiên bản, cấu hình, cache cùng khoảng thời gian đo.
- So sánh trước/sau trên cùng chỉ số, cùng phạm vi và điều kiện tương đương; ghi số mẫu và giới hạn của phép đo.
- Theo dõi đồng thời latency, throughput, lỗi, CPU, bộ nhớ, I/O, lock wait và các chỉ số bảo vệ phù hợp.
- Xác nhận tính đúng đắn của dữ liệu, giao dịch và hành vi ứng dụng sau điều chỉnh.
- Đặt tiêu chí đạt, tiêu chí dừng và điều kiện hoàn tác trước khi triển khai.
- Chuẩn bị runbook theo đúng loại thay đổi; kiểm tra khả năng khôi phục schema và dữ liệu riêng biệt.
- Triển khai theo từng giai đoạn, dùng canary hoặc đối chứng khi phù hợp và chỉ mở rộng khi có đủ bằng chứng.
- Lưu hồ sơ thay đổi, metric, kế hoạch thực thi và quyết định để có thể kiểm tra lại.

Ghi nhận bằng chứng trước và sau giúp biến hoạt động tối ưu hiệu năng thành một quy trình có thể lặp lại và kiểm chứng. Khi điều kiện đo được kiểm soát, tác động phụ được theo dõi và phương án hoàn tác đã sẵn sàng, nhóm có thể cải thiện hiệu năng cơ sở dữ liệu với mức độ tin cậy cao hơn và xử lý nhanh khi kết quả không đạt kỳ vọng.
